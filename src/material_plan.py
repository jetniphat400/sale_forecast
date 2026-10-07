"""Material plan v1 (week 3; METRICS.md Sec.43).

The operation plan's production quantities (replenishment of stock items and the made-to-order load, every division, items marked
no_production_in_system left out) are exploded through the bill of materials level by level: an in-house sub-assembly is expanded to its own
components, a purchased material is a requirement, Machine Hour lines are not materials. Per material and month:

    gross requirement   = the exploded quantity
    available           = raw-material stock in the proven warehouses (config material_plan.rm_warehouses) plus the open orders (Cube_tobe_received)
                          whose expected date has arrived by the end of the month (an expected date before the plan's first month counts in it)
    net requirement     = the running maximum of max(0, cumulative gross - available): a surplus that arrives later does not cancel an earlier shortage
    latest order date   = first day of a month with a net requirement minus the material's lead time (days); the material is to order now when the
                          first such date has passed

Lead time per material uses the order of sources of METRICS.md Sec.5 (observed purchase orders, supplier quoted, assumed) through `lead_time_v1`.
Everything is read from recorded files (the operation plan after its SHA-256 check and the saved week 3 pulls); no database. Outputs are recorded
with a SHA-256 in the operation plan's integrity file under "material_plan" and verified before they are read back.
"""
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import operation_plan as op  # noqa: E402
import lead_time_v1 as lt  # noqa: E402

logger = logging.getLogger("material_plan")

MONTH_COLUMNS = ["material", "month", "gross", "stock_available", "open_orders_cum", "net_cum", "net_month", "order_date"]
SUMMARY_COLUMNS = ["material", "name", "used_in", "n_products", "bom_unit", "stock_unit", "purchase_unit", "unit_vs_stock", "unit_vs_purchase", "stock_now",
                   "open_orders_total",
                   "lead_days", "lead_source", "total_gross", "total_net", "first_short_month", "latest_order_date", "to_order_now",
                   "qty_to_order_now", "also_has_bom"]
SOURCE_LABELS = {"observed": "observed", "supplier_quoted": "supplier_quoted", "assumed": "assumed"}


class MaterialPlanError(Exception):
    """An input is missing or does not hold what the plan needs; the build stops."""


def load_config(root: str = PROJECT_ROOT) -> dict:
    full = op.load_full_config(root)
    return {**full["material_plan"], "lead_time_v1": full["lead_time_v1"], "operation_plan": full["operation_plan"]}


def key(s) -> str:
    """The key a code is matched on: stripped and upper-cased (as lead_time_v1 does)."""
    return str(s).strip().upper()


# ------------------------------------------------------------------ the bill of materials
def bom_component_lines(bom: pd.DataFrame) -> pd.DataFrame:
    """One row per (parent, component): quantity per unit of the parent and its unit. The header row (Sequenceno 0 or a blank component) and the time
    pseudo-codes are not components: a BOM line whose Type contains 'hour' ('Machine Hour' and 'Labor hour', unit hour, no purchase record); a repeated
    (parent, component) pair is summed."""
    b = bom.copy()
    b["parent"] = b["ItemFG"].map(key)
    b["comp"] = b["ItemRawmat"].map(lambda x: "" if pd.isna(x) else key(x))
    b["seq"] = pd.to_numeric(b["Sequenceno"], errors="coerce").fillna(0)
    b["qty"] = pd.to_numeric(b["Quantity"], errors="coerce").fillna(0.0)
    b = b[(b["comp"] != "") & (b["comp"] != "NAN") & (b["seq"] != 0) & ~b["Type"].astype(str).str.lower().str.contains("hour")]
    g = b.groupby(["parent", "comp"], as_index=False).agg(qty=("qty", "sum"), unit=("Unit", "first"))
    g["unit"] = g["unit"].astype(str).str.strip()
    return g


def parents_with_bom(bom: pd.DataFrame) -> set:
    """Items that have a BOM entry of any kind (header rows included): the in-house candidates."""
    return set(bom["ItemFG"].map(key))


def purchased_codes(po: pd.DataFrame, receipts: pd.DataFrame) -> set:
    """Items with a purchase record in the saved history: a purchase order line or a receipt."""
    return set(po["item_code"].map(key)) | set(receipts["Itemcode"].map(key))


def is_in_house(code: str, has_bom: set, purchased: set) -> bool:
    """An in-house sub-assembly: it has its own BOM and no purchase record. Observed behaviour decides: a code with a purchase record is a purchased
    material even if a BOM entry exists, and a code with neither is treated as a purchased material of unknown supply."""
    return code in has_bom and code not in purchased


def explode(demand: dict, lines: pd.DataFrame, has_bom: set, purchased: set, n_months: int, max_levels: int = 25, stock: dict = None, plan_used_stock: set = None) -> dict:
    """Through the bill of materials, parents before children: `demand` maps a finished item to its monthly production vector. An in-house sub-assembly is expanded to its
    own components after the requirement that its parents put on it has been netted against its on-hand stock (`stock`, per item; the same net-requirement rule as a
    purchased material, with no arrivals: a cumulative shortfall, so stock covers the earliest months first); the finished items' own plan quantities are not netted
    (the operation plan already starts from their stock). A finished item that is also a component of another plan item has the requirement its parents put on it netted against its
    stock only when the operation plan has not used that stock, that is only when it has no Min and Max: `plan_used_stock` is the set of items with a Min and Max, whose component
    requirement is not netted (decision of 2026-10-07). Without `stock` nothing is netted. A node is processed once all the demand on it has been added (so a
    sub-assembly used at several levels is netted once). Returns {"gross": {material: vector}, "roots": {material: {finished item: units of the material that item
    needs, after netting}}, "levels": the longest chain, "in_house_expanded": set, "no_bom": set of items without a BOM line}. A BOM with a loop, or a chain longer than
    `max_levels`, stops the build."""
    children = {p: list(zip(g["comp"], g["qty"])) for p, g in lines.groupby("parent")}
    inhouse = lambda c: is_in_house(c, has_bom, purchased)
    stock = stock or {}
    roots_demand = {k: np.asarray(v, dtype=float) for k, v in demand.items() if float(np.sum(v)) > 0}
    reach, stack = set(roots_demand), list(roots_demand)
    while stack:
        n = stack.pop()
        for c, _ in children.get(n, []):
            if inhouse(c) and c not in reach:
                reach.add(c)
                stack.append(c)
    indeg = {n: 0 for n in reach}
    for n in reach:
        for c, _ in children.get(n, []):
            if c in indeg:
                indeg[c] += 1
    need = {n: np.zeros(n_months) for n in reach}                       # the requirement parents put on a node
    shares = {n: {} for n in reach}                                      # per finished item: units of the node its parents need for it
    for k, v in roots_demand.items():
        shares[k][k] = float(v.sum())
    depth = {n: 1 for n in reach}
    gross, roots, expanded, no_bom = {}, {}, set(), set()
    ready, done, longest = [n for n in reach if indeg[n] == 0], 0, (1 if roots_demand else 0)
    while ready:
        n = ready.pop()
        done += 1
        parent_need, share = need[n], dict(shares[n])
        if n in stock and float(parent_need.sum()) > 0 and n not in (plan_used_stock or ()):                  # net the parents' requirement against the node's stock
            net = net_requirement(parent_need, float(stock[n]), np.zeros(n_months))[2]
            factor = float(net.sum()) / float(parent_need.sum())
            vec, share = net, {r: u * factor if r not in roots_demand or r != n else u for r, u in share.items()}
        else:
            vec = parent_need
        vec = vec + roots_demand.get(n, 0.0)
        kids = children.get(n)
        if not kids:
            no_bom.add(n)
            continue
        expanded.add(n)
        longest = max(longest, depth[n])
        for comp, q in kids:
            cvec, cshare = vec * q, {r: u * q for r, u in share.items()}
            if comp in indeg:
                need[comp] += cvec
                for r, u in cshare.items():
                    shares[comp][r] = shares[comp].get(r, 0.0) + u
                depth[comp] = max(depth[comp], depth[n] + 1)
                indeg[comp] -= 1
                if indeg[comp] == 0:
                    ready.append(comp)
            else:
                gross.setdefault(comp, np.zeros(n_months))
                gross[comp] += cvec
                rr = roots.setdefault(comp, {})
                for r, u in cshare.items():
                    rr[r] = rr.get(r, 0.0) + u
        if longest > max_levels:
            raise MaterialPlanError(f"the bill of materials does not end within {max_levels} levels (a chain through {sorted(n for n in reach if depth[n] > max_levels)[:5]})")
    if done < len(reach):
        raise MaterialPlanError(f"the bill of materials does not end: a loop through {sorted(n for n in reach if indeg[n] > 0)[:5]}")
    return {"gross": gross, "roots": roots, "levels": longest, "in_house_expanded": expanded - set(roots_demand), "no_bom": no_bom}


# ------------------------------------------------------------------ availability and netting
def month_start(ym: str) -> pd.Timestamp:
    return pd.Timestamp(f"{ym}-01")


def open_orders_by_month(tobe: pd.DataFrame, months: list) -> tuple:
    """(arrivals {material: vector by month}, total quantity per material, number of lines after the last month): an open order's quantity arrives
    in the month of its expected date; an expected date before the first month counts in the first month; after the last month it arrives outside the
    horizon (counted in the total only)."""
    t = tobe.copy()
    t["m"] = t["itemcode"].map(key)
    t["q"] = pd.to_numeric(t["quantity"], errors="coerce").fillna(0.0)
    t["ym"] = pd.to_datetime(t["fulfill_date"], errors="coerce").dt.strftime("%Y-%m")
    arrivals, totals, n_after = {}, {}, 0
    for _, r in t.iterrows():
        totals[r["m"]] = totals.get(r["m"], 0.0) + r["q"]
        if pd.isna(r["ym"]):
            continue
        ym = months[0] if r["ym"] < months[0] else r["ym"]
        if ym > months[-1]:
            n_after += 1
            continue
        arrivals.setdefault(r["m"], np.zeros(len(months)))[months.index(ym)] += r["q"]
    return arrivals, totals, n_after


def raw_material_stock(inv: pd.DataFrame, warehouses: list) -> dict:
    """Per material, the stock summed over the proven raw-material warehouses (a negative total counts as zero)."""
    i = inv.copy()
    i["m"] = i["itemcode"].map(key)
    i["w"] = i["warehouse"].astype(str).str.strip()
    i["s"] = pd.to_numeric(i["stock"], errors="coerce").fillna(0.0)
    s = i[i["w"].isin(warehouses)].groupby("m")["s"].sum()
    return {m: max(0.0, float(v)) for m, v in s.items()}


def net_requirement(gross: np.ndarray, stock: float, arrivals: np.ndarray) -> tuple:
    """(available cumulative, net cumulative, net per month). net cumulative = the running maximum of max(0, cumulative gross - stock - cumulative
    arrivals): a later surplus does not cancel a shortage already ordered for."""
    cum_gross = np.cumsum(gross)
    avail = stock + np.cumsum(arrivals)
    short = np.maximum(0.0, cum_gross - avail)
    net_cum = np.maximum.accumulate(short)
    net_month = np.diff(net_cum, prepend=0.0)
    return avail, net_cum, net_month


def order_dates(net_month: np.ndarray, months: list, lead_days: float) -> list:
    """Per month, the latest order date (first day of the month minus the lead time) where there is a net requirement, otherwise None."""
    return [(month_start(m) - pd.to_timedelta(float(lead_days), unit="D")).date() if n > 1e-9 else None for m, n in zip(months, net_month)]


# ------------------------------------------------------------------ lead time per material
def material_lead_times(materials: list, po: pd.DataFrame, receipts: pd.DataFrame, price: pd.DataFrame, fallback_days: float, usable: list) -> dict:
    """{material: (days, source)} in the order observed, supplier quoted, assumed (lead_time_v1; METRICS.md Sec.5). The observed value is the median
    over the material's purchase orders of the days from the PO date to the first receipt, usable between `usable` days."""
    lt.USABLE_MIN_DAYS, lt.USABLE_MAX_DAYS = int(usable[0]), int(usable[1])
    obs_df = lt.observed_lead_times(po, receipts)
    observed = obs_df.groupby("item")["lead_days"].median().to_dict()
    quoted = lt.quoted_days_by_material(price)
    return {m: lt.material_lead_time(m, observed, quoted, fallback_days) for m in materials}


# ------------------------------------------------------------------ units
UNIT_ALIASES = {"PCS": "PC", "PIECE": "PC", "UNIT": "PC", "M": "METRE", "METER": "METRE", "MTR": "METRE", "SETS": "SET", "LITER": "LITRE", "EA": "PC"}
UNKNOWN_UNITS = {"", "-", "NAN"}


def norm_unit(u) -> str:
    """A unit text normalised for comparison: stripped, upper-cased, a trailing full stop removed, a few spellings of the same unit joined."""
    s = str(u).strip().upper().rstrip(".")
    return UNIT_ALIASES.get(s, s)


def unit_check(bom_unit, other_units) -> str:
    """'same' when every known unit among `other_units` equals the BOM unit, 'differs' when one known unit differs, 'unknown' when none is known."""
    known = {norm_unit(u) for u in other_units if norm_unit(u) not in UNKNOWN_UNITS}
    b = norm_unit(bom_unit)
    if not known or b in UNKNOWN_UNITS:
        return "unknown"
    return "same" if known == {b} else "differs"


# ------------------------------------------------------------------ the plan
def demand_from_operation_plan(item_month: pd.DataFrame, months: list) -> dict:
    """{item: monthly production vector}: planned production of an item with a Min and Max, the load of every other item; rows of items marked
    no_production_in_system are left out."""
    im = item_month[item_month["counted"]].copy()
    im["qty"] = im["planned_production"].where(im["planned_production"].notna(), im["load"]).fillna(0.0)
    out = {}
    for item, g in im.groupby("item"):
        v = g.set_index("month")["qty"].reindex(months).fillna(0.0).to_numpy()
        if v.sum() > 0:
            out[key(item)] = v
    return out


def items_with_min_max(item_month: pd.DataFrame) -> set:
    """Items of the counted rows with a Min and Max: the operation plan gives them a planned production, starting from their stock."""
    im = item_month[item_month["counted"]]
    return {key(i) for i in im.loc[im["planned_production"].notna(), "item"]}


def build(root: str = PROJECT_ROOT, today: pd.Timestamp = None, op_out_dir: str = None, cfg: dict = None) -> dict:
    """The material plan from the recorded operation plan (hash-checked) and the saved week 3 pulls. Returns {"material_month", "summary", "meta"}."""
    cfg = cfg or load_config(root)
    today = pd.Timestamp(today) if today is not None else pd.Timestamp(datetime.now().date())
    im, dm, op_meta = op.read_outputs(root, cfg["operation_plan"], op_out_dir)
    months = list(op_meta["months"])
    w3 = op.load_week3_inputs(root, cfg["operation_plan"])
    if not cfg["rm_warehouses"]:
        raise MaterialPlanError("config material_plan.rm_warehouses is empty: the raw-material warehouses have not been proven")
    demand = demand_from_operation_plan(im, months)
    lines = bom_component_lines(w3["bom_tree"])
    has_bom = parents_with_bom(w3["bom_tree"])
    purchased = purchased_codes(w3["po_lines"], w3["receipts"])
    rm_list = [str(w).strip() for w in cfg["rm_warehouses"]]
    ex = explode(demand, lines, has_bom, purchased, len(months), int(cfg["max_bom_levels"]), stock=raw_material_stock(w3["rm_inventory"], rm_list),
                 plan_used_stock=items_with_min_max(im))
    materials = sorted(ex["gross"])
    leads = material_lead_times(materials, w3["po_lines"], w3["receipts"], w3["price"], float(cfg["lead_time_v1"]["fallback_material_days"]),
                                cfg["usable_lead_days"])
    stock = raw_material_stock(w3["rm_inventory"], [str(w).strip() for w in cfg["rm_warehouses"]])
    use_open = bool(cfg["open_orders_usable"])
    arrivals, oo_total, n_after = open_orders_by_month(w3["open_orders"], months) if use_open else ({}, {}, 0)
    names = {key(c): " ".join(str(n).split()) for c, n in zip(w3["item_names"]["ItemCode"], w3["item_names"]["Description"]) if pd.notna(n)}
    bom_unit = lines.groupby("comp")["unit"].first().to_dict()
    inv_units = w3["rm_inventory"].assign(m=w3["rm_inventory"]["itemcode"].map(key)).groupby("m")["unit"].agg(lambda s: set(s)).to_dict()
    price_units = w3["price"].assign(m=w3["price"]["ItemCode"].map(key)).groupby("m")["Unit"].agg(lambda s: set(s)).to_dict()
    tobe_units = w3["open_orders"].assign(m=w3["open_orders"]["itemcode"].map(key)).groupby("m")["unit"].agg(lambda s: set(s)).to_dict()
    rows, summ = [], []
    for m in materials:
        g = ex["gross"][m]
        arr = arrivals.get(m, np.zeros(len(months)))
        avail, net_cum, net_month = net_requirement(g, stock.get(m, 0.0), arr)
        days, src = leads[m]
        dates = order_dates(net_month, months, days)
        for i, ym in enumerate(months):
            rows.append({"material": m, "month": ym, "gross": float(g[i]), "stock_available": float(stock.get(m, 0.0)),
                         "open_orders_cum": float(np.cumsum(arr)[i]), "net_cum": float(net_cum[i]), "net_month": float(net_month[i]),
                         "order_date": dates[i]})
        short = [i for i in range(len(months)) if net_month[i] > 1e-9]
        first_date = dates[short[0]] if short else None
        now = [i for i in short if pd.Timestamp(dates[i]) <= today]
        top = sorted(ex["roots"][m].items(), key=lambda kv: (-kv[1], kv[0]))
        stock_u, purch_u = list(inv_units.get(m, set())), list(price_units.get(m, set())) + list(tobe_units.get(m, set()))
        summ.append({"material": m, "name": names.get(m, ""), "used_in": " ".join(r for r, _ in top[: int(cfg["used_in_max_items"])]), "n_products": len(top),
                     "bom_unit": bom_unit.get(m, ""), "stock_unit": " ".join(sorted({norm_unit(u) for u in stock_u} - UNKNOWN_UNITS)),
                     "purchase_unit": " ".join(sorted({norm_unit(u) for u in purch_u} - UNKNOWN_UNITS)),
                     "unit_vs_stock": unit_check(bom_unit.get(m, ""), stock_u), "unit_vs_purchase": unit_check(bom_unit.get(m, ""), purch_u), "stock_now": float(stock.get(m, 0.0)), "open_orders_total": float(oo_total.get(m, 0.0)),
                     "lead_days": float(days), "lead_source": src, "total_gross": float(g.sum()), "total_net": float(net_month.sum()),
                     "first_short_month": months[short[0]] if short else "", "latest_order_date": first_date,
                     "to_order_now": bool(first_date is not None and pd.Timestamp(first_date) <= today),
                     "qty_to_order_now": float(sum(net_month[i] for i in now)), "also_has_bom": bool(m in has_bom)})
    material_month = pd.DataFrame(rows, columns=MONTH_COLUMNS)
    summary = pd.DataFrame(summ, columns=SUMMARY_COLUMNS)
    meta = {"built_at": datetime.now().isoformat(timespec="seconds"), "today": str(today.date()), "months": months,
            "operation_plan_today": op_meta["today"], "operation_plan_built_at": op_meta["built_at"],
            "rm_pulled_at_local": str(w3["rm_pulled_at_local"]), "rm_warehouses": [str(w).strip() for w in cfg["rm_warehouses"]],
            "divisions": list(cfg["operation_plan"]["divisions"]),
            "open_orders_used": use_open, "open_orders_lines_after_last_month": n_after,
            "levels": ex["levels"], "n_in_house_expanded": len(ex["in_house_expanded"]), "subassembly_stock_netted": True, "items_without_bom": sorted(ex["no_bom"]),
            "n_items_exploded": len(demand), "n_materials": len(materials),
            "n_to_order_now": int(summary["to_order_now"].sum()) if len(summary) else 0,
            "lead_sources": summary["lead_source"].value_counts().to_dict() if len(summary) else {},
            "assumptions": ["open orders count in the month of their expected date; an expected date before the first month counts in it",
                            "stock is the raw-material warehouses' stock of the pull; stock of in-house sub-assemblies is not netted",
                            "net requirement is the running maximum of the cumulative shortfall; a later surplus does not cancel it",
                            "no minimum order quantity or lot size; units are the BOM's, with the unit check beside each material"]}
    return {"material_month": material_month, "summary": summary, "meta": meta}


# ------------------------------------------------------------------ recorded outputs
def _paths(root: str, cfg: dict, out_dir: str = None) -> dict:
    def target(rel):
        p = op.path_of(root, rel)
        return os.path.join(out_dir, os.path.basename(p)) if out_dir else p
    return {"month": target(cfg["output_material_month_file"]), "summary": target(cfg["output_material_summary_file"]),
            "meta": target(cfg["output_material_month_file"].replace("_material_month.csv", "_meta.json")),
            "integrity": target(cfg["operation_plan"]["output_integrity_file"])}


def write_outputs(result: dict, root: str = PROJECT_ROOT, cfg: dict = None, out_dir: str = None) -> dict:
    """Writes the two CSVs and records their SHA-256 in the operation plan's integrity file under "material_plan". `out_dir` replaces the folder of
    the configured paths (the runner's temporary copy, tests). The meta stays inside the hashed month file's neighbour only as the returned dict:
    the summary and month files are the two recorded outputs."""
    cfg = cfg or load_config(root)
    p = _paths(root, cfg, out_dir)
    os.makedirs(os.path.dirname(p["month"]), exist_ok=True)
    result["material_month"].to_csv(p["month"], index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f")
    result["summary"].to_csv(p["summary"], index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f")
    if not os.path.exists(p["integrity"]):
        raise MaterialPlanError(f"the operation plan's integrity file is missing: {p['integrity']} (the operation plan must be recorded first)")
    with open(p["integrity"], encoding="utf-8") as f:
        rec = json.load(f)
    rec["material_plan"] = {"recorded_at": datetime.now().isoformat(timespec="seconds"),
                            "files": {os.path.basename(p[k]): {"sha256": op.sha256_file(p[k])} for k in ("month", "summary")},
                            "meta": result["meta"]}
    with open(p["integrity"], "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, indent=1, default=str)
    return {"paths": p}


def verify_outputs(root: str = PROJECT_ROOT, cfg: dict = None, out_dir: str = None) -> dict:
    """Checks the two material-plan files against the hashes recorded in the integrity file; raises MaterialPlanError on a missing entry or file or a
    hash that differs. Returns the recorded section."""
    cfg = cfg or load_config(root)
    p = _paths(root, cfg, out_dir)
    if not os.path.exists(p["integrity"]):
        raise MaterialPlanError(f"integrity file missing: {p['integrity']}")
    with open(p["integrity"], encoding="utf-8") as f:
        rec = json.load(f).get("material_plan")
    if not rec:
        raise MaterialPlanError("the integrity file has no material_plan section")
    for name, v in rec["files"].items():
        path = os.path.join(os.path.dirname(p["month"]), name)
        if not os.path.exists(path):
            raise MaterialPlanError(f"recorded output missing: {path}")
        if op.sha256_file(path) != v["sha256"]:
            raise MaterialPlanError(f"{name} does not hash to the value recorded in the integrity file")
    return rec


def read_outputs(root: str = PROJECT_ROOT, cfg: dict = None, out_dir: str = None) -> tuple:
    """(material_month, summary, meta) after the hash check."""
    cfg = cfg or load_config(root)
    rec = verify_outputs(root, cfg, out_dir)
    p = _paths(root, cfg, out_dir)
    return (pd.read_csv(p["month"], dtype={"order_date": str}), pd.read_csv(p["summary"], dtype={"latest_order_date": str}), rec["meta"])


def run(root: str = PROJECT_ROOT, today: pd.Timestamp = None, out_dir: str = None, op_out_dir: str = None) -> dict:
    """Builds, writes and verifies the material plan; the runner's step calls this after the operation plan. Returns a short summary."""
    cfg = load_config(root)
    result = build(root, today, op_out_dir if op_out_dir is not None else out_dir, cfg)
    written = write_outputs(result, root, cfg, out_dir)
    verify_outputs(root, cfg, out_dir)
    m = result["meta"]
    return {"months": m["months"], "n_materials": m["n_materials"], "n_to_order_now": m["n_to_order_now"], "levels": m["levels"],
            "open_orders_used": m["open_orders_used"], "rm_warehouses": m["rm_warehouses"],
            "written_to": {k: op._display_path(v, root) for k, v in written["paths"].items() if k != "integrity"}}


# ------------------------------------------------------------------ the proofs (Part 6: each source is used only if its test supports it)
def rm_warehouse_proof(tran_agg: pd.DataFrame, inventory: pd.DataFrame, min_share: float) -> dict:
    """Which warehouses hold raw materials and components. `tran_agg` is cube_inventory_tran grouped by warehouse and transtype for the BOM components over
    12 months (columns warehouse, transtype, n); `inventory` is Cube_Inventory_Exact for the same codes (warehouse, itemcode, stock). A warehouse is a
    raw-material warehouse when its type B issues (issues to production jobs) are at least `min_share` of all type B issues. Purchases (type A) are
    received in the warehouse that holds most of them (the inspection warehouse), which does not issue to production and is reported apart."""
    t = tran_agg.copy()
    t["warehouse"] = t["warehouse"].astype(str).str.strip()
    t["n"] = pd.to_numeric(t["n"])
    b = t[t["transtype"].astype(str) == "B"].groupby("warehouse")["n"].sum()
    a = t[t["transtype"].astype(str) == "A"].groupby("warehouse")["n"].sum()
    share_b = (b / b.sum()).sort_values(ascending=False)
    rm = sorted(share_b[share_b >= min_share].index)
    inv = inventory.copy()
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    inv["stock"] = pd.to_numeric(inv["stock"], errors="coerce").fillna(0.0)
    stock = inv[inv["stock"] > 0].groupby("warehouse")["stock"].sum()
    receiving = a.sort_values(ascending=False)
    return {"rm_warehouses": rm, "share_of_issues": {w: float(v) for w, v in share_b.items()}, "n_issue_rows": int(b.sum()),
            "purchase_receipt_warehouse": str(receiving.index[0]) if len(receiving) else None,
            "purchase_receipt_share": float(receiving.iloc[0] / receiving.sum()) if len(receiving) else None,
            "issues_from_receipt_warehouse": int(b.get(str(receiving.index[0]), 0)) if len(receiving) else 0,
            "stock_units_in_rm": float(stock.reindex(rm).fillna(0).sum()), "stock_units_elsewhere": float(stock.drop(rm, errors="ignore").sum()),
            "stock_units_in_receipt_warehouse": float(stock.get(str(receiving.index[0]), 0.0)) if len(receiving) else 0.0}


def open_orders_proof(tobe: pd.DataFrame, po: pd.DataFrame, receipts: pd.DataFrame, cfg: dict) -> dict:
    """Whether Cube_tobe_received identifies the quantity ordered and not yet received, with an expected date that matches the actual receipts.
    Criteria (config material_plan.open_orders_*, fixed before the test): (a) the share of its lines that match a purchase-order line (PO number and item);
    (b) of those, the share whose quantity equals the ordered minus the received quantity; (c) the share whose expected date equals the PO's planned date;
    (d) on purchase-order lines already received (PO date from 2023), the share whose first receipt falls within `open_orders_within_days` of the planned date,
    which must reach `open_orders_min_share`."""
    t = tobe.copy()
    t["po"], t["item"] = t["po_number"].astype(str).str.strip(), t["itemcode"].map(key)
    t["qty"] = pd.to_numeric(t["quantity"], errors="coerce")
    t["fd"] = pd.to_datetime(t["fulfill_date"], errors="coerce")
    p = po.copy()
    p["po"], p["item"] = p["po_no"].astype(str).str.strip(), p["item_code"].map(key)
    p["pq"], p["rq"] = pd.to_numeric(p["po_quantity"], errors="coerce"), pd.to_numeric(p["received_quantity"], errors="coerce")
    p["planed"], p["pod"] = pd.to_datetime(p["planed_date"], errors="coerce"), pd.to_datetime(p["po_date"], errors="coerce")
    pl = p.groupby(["po", "item"]).agg(pq=("pq", "sum"), rq=("rq", "sum"), planed=("planed", "min"), pod=("pod", "min")).reset_index()
    tl = t.groupby(["po", "item"]).agg(qty=("qty", "sum"), fd=("fd", "min")).reset_index()
    j = tl.merge(pl, on=["po", "item"], how="left", indicator=True)
    matched = j[j["_merge"] == "both"]
    r = receipts.copy()
    r["po"], r["item"] = r["PO"].astype(str).str.strip(), r["Itemcode"].map(key)
    first = r.assign(d=pd.to_datetime(r["Receive_date"], errors="coerce")).groupby(["po", "item"])["d"].min().rename("first_rcv").reset_index()
    h = pl.merge(first, on=["po", "item"])
    h = h[(h["pod"] >= pd.Timestamp("2023-01-01")) & (h["pq"] > 0) & h["planed"].notna()]
    diff = (h["first_rcv"] - h["planed"]).dt.days
    out = {"n_lines": int(len(tl)), "match_share": float(len(matched) / len(tl)) if len(tl) else 0.0,
           "quantity_share": float(np.isclose(matched["qty"], matched["pq"] - matched["rq"], atol=1e-6).mean()) if len(matched) else 0.0,
           "date_share": float((matched["fd"] == matched["planed"]).mean()) if len(matched) else 0.0,
           "n_received_lines": int(len(h)), "median_days_receipt_minus_planned": float(diff.median()) if len(diff) else None,
           "within_days_share": float((diff.abs() <= cfg["open_orders_within_days"]).mean()) if len(diff) else 0.0,
           "within_days": int(cfg["open_orders_within_days"]),
           "share_received_more_than_within_days_late": float((diff > cfg["open_orders_within_days"]).mean()) if len(diff) else 0.0,
           "n_expected_before_first_month": None}
    out["usable"] = bool(out["match_share"] >= cfg["open_orders_min_match_share"] and out["quantity_share"] >= cfg["open_orders_min_quantity_share"]
                         and out["date_share"] >= cfg["open_orders_min_date_share"] and out["within_days_share"] >= cfg["open_orders_min_share"])
    return out


def bom_source_proof(v1_lines: pd.DataFrame, v2_lines: pd.DataFrame, jobs: pd.DataFrame, issues: pd.DataFrame, tolerance: float = 0.05) -> dict:
    """How Cube_BOM_Exact_V2 differs from Cube_BOM_Exact and which matches recent production consumption. `v1_lines` and `v2_lines` hold (parent, comp, qty)
    per source (header rows and Machine Hour lines removed); `jobs` holds (order, item, qty) of production orders with their produced quantity (Cube_JobCost);
    `issues` holds (order, mat, used[, unit]) of the materials actually used per order (Cube_JobCost_Detail actual quantity, equal to the type B issues). For each
    source: the share of issued (order, material) pairs that are a line of the order item's BOM, the share of those whose issued quantity is within
    `tolerance` of produced quantity x BOM quantity, and the share of orders whose every issued material is a BOM line."""
    if "unit" in issues.columns:      # labour and machine hours are recorded beside the materials; they are not materials
        issues = issues[issues["unit"].astype(str).str.strip().str.lower() != "hour"]

    def side(lines):
        x = jobs.merge(issues, on="order").merge(lines.rename(columns={"parent": "item", "comp": "mat", "qty": "bq"}), on=["item", "mat"], how="left")
        d = x[x["used"] > 0]
        found = d[d["bq"].notna()]
        exp = found["qty"] * found["bq"]
        within = float((np.abs(exp - found["used"]) <= tolerance * found["used"]).mean()) if len(found) else 0.0
        per_order = d.groupby(["order", "item"])["bq"].apply(lambda s: bool(s.notna().all()))
        return {"pairs_found_share": float(len(found) / len(d)) if len(d) else 0.0, "n_pairs": int(len(d)), "n_found": int(len(found)),
                "within_tolerance_share": within, "orders_fully_covered_share": float(per_order.mean()) if len(per_order) else 0.0, "n_orders": int(len(per_order))}
    both = v1_lines.merge(v2_lines, on=["parent", "comp"], how="outer", suffixes=("_v1", "_v2"), indicator=True)
    shared_parents = set(v1_lines["parent"]) & set(v2_lines["parent"])
    sub = both[both["parent"].isin(shared_parents)]
    sets_equal = sub.groupby("parent")["_merge"].apply(lambda s: bool((s == "both").all()))
    in_both = sub[sub["_merge"] == "both"]
    return {"v1_lines": int(len(v1_lines)), "v2_lines": int(len(v2_lines)), "items_in_both": len(shared_parents),
            "line_share_in_both": float((sub["_merge"] == "both").mean()) if len(sub) else 0.0,
            "lines_only_v1": int((sub["_merge"] == "left_only").sum()), "lines_only_v2": int((sub["_merge"] == "right_only").sum()),
            "quantity_equal_share": float(np.isclose(in_both["qty_v1"], in_both["qty_v2"], rtol=1e-6).mean()) if len(in_both) else 0.0,
            "items_identical_sets_share": float(sets_equal.mean()) if len(sets_equal) else 0.0, "v1": side(v1_lines), "v2": side(v2_lines)}


def unit_proof(summary: pd.DataFrame) -> dict:
    """BOM unit against the stock unit and against the purchase unit (price list and open orders), over the materials of the plan: counts of same, differs and
    unknown (a blank or '-' unit), the unit pairs that differ, and the share of the plan's gross requirement the differing materials carry."""
    out = {"n_materials": int(len(summary))}
    for col in ("unit_vs_stock", "unit_vs_purchase"):
        vc = summary[col].value_counts().to_dict()
        d = summary[summary[col] == "differs"]
        other = "stock_unit" if col == "unit_vs_stock" else "purchase_unit"
        out[col] = {"same": int(vc.get("same", 0)), "differs": int(vc.get("differs", 0)), "unknown": int(vc.get("unknown", 0)),
                    "gross_share_of_differing": float(d["total_gross"].sum() / summary["total_gross"].sum()) if summary["total_gross"].sum() else 0.0,
                    "pairs": {f"{norm_unit(b)} -> {o}": int(n) for (b, o), n in d.groupby([d["bom_unit"], d[other]]).size().sort_values(ascending=False).items()}}
    return out


# ------------------------------------------------------------------ the pulls the plan reads (METRICS.md Sec.43, "Inputs")
CHUNK = 1300           # codes per IN list


def _in_list(codes) -> str:
    return "','".join(sorted(str(c).replace("'", "") for c in codes))


def _chunks(codes: list) -> list:
    codes = sorted(codes)
    return [codes[i:i + CHUNK] for i in range(0, len(codes), CHUNK)]


def pull_material_inputs(root_codes: list, since: str, max_levels: int = 25) -> dict:
    """Reads, through the open database session (db.run_query; the caller owns the session; read-only), what the material plan needs for the items `root_codes`:
    the BOM tree (Cube_BOM_Exact, level by level: every component code is looked up as a parent until none is new), raw-material stock (Cube_Inventory_Exact),
    open purchase orders (Cube_tobe_received), purchase orders and receipts since `since` (lead times and purchase evidence), the price list (quoted delivery
    times) and the item master (names) for every component code. Returns raw frames {bom_tree, inventory, tobe, po, receipts, price, item}."""
    from db import run_query
    cols = "ItemFG, ItemRawmat, Quantity, Unit, Sequenceno, Type, Status, Warehouse, Division, ItemGroup, version, [Timestamp]"
    have, frames, frontier, level = set(), [], sorted(root_codes), 0
    while frontier:
        level += 1
        if level > max_levels:
            raise MaterialPlanError(f"the bill of materials does not end within {max_levels} levels while it is pulled")
        got = pd.concat([run_query(f"SELECT {cols} FROM Cube_BOM_Exact WHERE ItemFG IN ('{_in_list(ch)}')") for ch in _chunks(frontier)], ignore_index=True)
        have |= set(frontier)
        frames.append(got)
        lines = bom_component_lines(got) if len(got) else pd.DataFrame(columns=["comp"])
        frontier = sorted({c for c in lines["comp"] if c not in have and c not in {key(x) for x in have}})
    bom = pd.concat(frames, ignore_index=True)
    comps = sorted(set(bom_component_lines(bom)["comp"]) | {str(c).strip() for c in bom["ItemRawmat"].dropna()} - {""})

    def many(sql_tmpl):
        return pd.concat([run_query(sql_tmpl.format(codes=_in_list(ch))) for ch in _chunks(comps)], ignore_index=True)
    return {"bom_tree": bom,
            "inventory": many("SELECT warehouse, itemcode, stock, unit FROM Cube_Inventory_Exact WHERE itemcode IN ('{codes}')"),
            "tobe": many("SELECT fulfill_date, po_number, itemcode, quantity, unit, warehouse, order_date FROM Cube_tobe_received WHERE itemcode IN ('{codes}')"),
            "po": many(f"SELECT po_no, item_code, po_date, planed_date, po_quantity, received_quantity FROM Cube_PO_Exact WHERE item_code IN ('{{codes}}') AND po_date >= '{since}'"),
            "receipts": many(f"SELECT PO, Itemcode, Receive_date, Items_Received FROM Cube_ReceiveRM WHERE Itemcode IN ('{{codes}}') AND Receive_date >= '{since}'"),
            "price": many("SELECT ItemCode, SupplierNumber, Unit, DeliveryTime FROM Cube_PriceList WHERE ItemCode IN ('{codes}')"),
            "item": many("SELECT ItemCode, Description FROM Cube_ItemList WHERE ItemCode IN ('{codes}')")}


def assemble_inputs(material: dict, ces: pd.DataFrame, backlog_pulled_at: str, rm_pulled_at: str) -> dict:
    """The dict of DataFrames the offline plan reads, from `pull_material_inputs`' frames and the Cube_CES frame of the class evidence (its Status 'Backlog' rows
    with RevenueType are the confirmed orders). Keeps only the columns the plan uses."""
    b = ces[ces["Status"] == "Backlog"][["ContractID", "ItemCode", "ForecastDelDate", "PlanDelDate", "ActualQty", "BacklogQty", "RevenueType"]].copy()
    return {"backlog_ces": b.reset_index(drop=True), "backlog_pulled_at_local": backlog_pulled_at,
            "bom_tree": material["bom_tree"][["ItemFG", "ItemRawmat", "Quantity", "Unit", "Sequenceno", "Type"]].reset_index(drop=True),
            "rm_inventory": material["inventory"][["warehouse", "itemcode", "stock", "unit"]], "rm_pulled_at_local": rm_pulled_at,
            "open_orders": material["tobe"][["fulfill_date", "po_number", "itemcode", "quantity", "unit", "warehouse", "order_date"]],
            "po_lines": material["po"][["po_no", "item_code", "po_date", "planed_date", "po_quantity", "received_quantity"]],
            "receipts": material["receipts"][["PO", "Itemcode", "Receive_date", "Items_Received"]],
            "price": material["price"][["ItemCode", "SupplierNumber", "Unit", "DeliveryTime"]],
            "item_names": material["item"][["ItemCode", "Description"]]}


def pull_and_save(root: str = PROJECT_ROOT, in_open_session: bool = False) -> dict:
    """The runner's pull stage for the material plan, inside ONE database session opened here (login failure raises, no retry; `in_open_session` True when the caller
    already holds the session): the class evidence of METRICS.md Sec.23 and the material plan's inputs are read, saved under the folder of config
    `operation_plan.week3_inputs_file` (the plan's input bundle and the class evidence), and the item-level class file is recomputed from the class evidence.
    Returns the counts."""
    import contextlib
    import db
    sys.path.insert(0, os.path.join(HERE, "investigations"))
    import task2b_part2_fulfilment_segmentation as seg
    cfg = load_config(root)
    codes = seg.class_evidence_codes()
    started = datetime.now()
    with (contextlib.nullcontext() if in_open_session else db.session()):
        evidence = seg.pull_class_evidence(codes)
        material = pull_material_inputs(codes, cfg["purchase_evidence_since"], int(cfg["max_bom_levels"]))
    pulled_at = started.strftime("%Y-%m-%d %H:%M:%S")
    bundle = assemble_inputs(material, evidence["p2_ces"], pulled_at, pulled_at)
    out = op.path_of(root, cfg["operation_plan"]["week3_inputs_file"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pd.to_pickle(bundle, out)
    pd.to_pickle({"pulled_at_local": pulled_at, **evidence}, os.path.join(os.path.dirname(out), "class_evidence.pkl"))
    result = seg.run_from_frames(evidence, op.path_of(root, cfg["operation_plan"]["item_class_file"]), pd.Timestamp(started.date()), write=True)
    return {"pulled_at_local": pulled_at, "rows": {k: int(len(v)) for k, v in {**evidence, **material}.items()}, "n_items": int(len(result["table"])),
            "written_to": op._display_path(out, root)}


# ------------------------------------------------------------------ the saved pulls (offline use, tests and the one-off bundle of week 3)
def build_inputs_bundle(pull_dir: str, pulled_at: dict) -> dict:
    """The dict of DataFrames the offline plan reads, from pulls saved in `pull_dir` (csv files named as the pulls were: p2_ces, p6_bom_tree_rows,
    p6_inv_*, p6_tobe_*, p6_po_*, p6_rcv_*, p6_price_*, p6_item_*). `pulled_at` gives {"backlog": ..., "rm": ...} local pull times. Keeps only the columns
    the plan uses."""
    import glob

    def cat(prefix):
        return pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False) for f in sorted(glob.glob(os.path.join(pull_dir, prefix + "_*.csv")))], ignore_index=True)
    ces = pd.read_csv(os.path.join(pull_dir, "p2_ces.csv"))
    b = ces[ces["Status"] == "Backlog"][["ContractID", "ItemCode", "ForecastDelDate", "PlanDelDate", "ActualQty", "BacklogQty", "RevenueType"]].copy()
    bom = pd.read_csv(os.path.join(pull_dir, "p6_bom_tree_rows.csv"), dtype=str, keep_default_na=False)[["ItemFG", "ItemRawmat", "Quantity", "Unit", "Sequenceno", "Type"]]
    inv, tobe, po, rcv, price, item = cat("p6_inv"), cat("p6_tobe"), cat("p6_po"), cat("p6_rcv"), cat("p6_price"), cat("p6_item")
    return {"backlog_ces": b.reset_index(drop=True), "backlog_pulled_at_local": pulled_at["backlog"], "bom_tree": bom,
            "rm_inventory": inv[["warehouse", "itemcode", "stock", "unit"]], "rm_pulled_at_local": pulled_at["rm"],
            "open_orders": tobe[["fulfill_date", "po_number", "itemcode", "quantity", "unit", "warehouse", "order_date"]],
            "po_lines": po[["po_no", "item_code", "po_date", "planed_date", "po_quantity", "received_quantity"]],
            "receipts": rcv[["PO", "Itemcode", "Receive_date", "Items_Received"]],
            "price": price[["ItemCode", "SupplierNumber", "Unit", "DeliveryTime"]],
            "item_names": item[["ItemCode", "Description"]]}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--pull" in sys.argv[1:]:           # the monthly runner's pull stage (one database session; read-only)
        print(json.dumps(pull_and_save(), indent=1, default=str))
    else:
        print(json.dumps(run(), indent=1, default=str))
