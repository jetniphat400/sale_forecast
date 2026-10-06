"""Operation plan v1 for PEM101 and PEM107 (week 2; METRICS.md Sec.42).

For every forecast-status item of the two divisions, month by month from the current month to the end of the latest production forecast:
  * demand = the larger of the item's forecast and its confirmed orders not yet delivered (Cube_CES Status 'Backlog') due that month;
    backlog due before the current month goes into the first month;
  * items with a Min and Max (class stock_policy), part A: the Min and Max the Min-Max page shows on load; opening stock is the sellable
    on-hand of the latest daily stock pull; closing = opening - demand + open orders; below Min, production brings the closing position up to Max;
  * items without a Min and Max (confirmed_to_order, conflict), part B: the month's production load equals the month's demand;
  * part C: per division and month, planned production plus load against the highest sustained monthly output (cube_final transfer_qty), a lower bound.

Everything is read from recorded files (the built page, the forward-test log with its hash check, saved pulls, config); no database. Outputs are
recorded with a SHA-256 (`operation_plan_v1_integrity.json`) and verified before they are read back. The module never writes under a tracked path.
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
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
logger = logging.getLogger("operation_plan")

ITEM_MONTH_COLUMNS = ["division", "item", "class", "min_max_source", "month", "forecast", "backlog_due", "demand", "demand_source", "opening",
                      "open_orders", "min", "max", "planned_production", "closing", "load"]
DIVISION_MONTH_COLUMNS = ["division", "month", "planned_production_stock", "load_confirmed_to_order", "load_conflict", "total_load", "capacity",
                          "share_of_capacity", "above_capacity"]


class OperationPlanError(Exception):
    """An input is missing, does not hash to its recorded value, or does not hold what the plan needs; the build stops."""


# ------------------------------------------------------------------ config and files
def load_full_config(root: str = PROJECT_ROOT) -> dict:
    with open(os.path.join(root, "config", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(root: str = PROJECT_ROOT) -> dict:
    return load_full_config(root)["operation_plan"]


def path_of(root: str, rel: str) -> str:
    return os.path.join(root, *rel.split("/"))


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sha256_of_text_readback(path: str) -> str:
    """SHA-256 of the file as text read back and re-encoded, as the lead-time output does (line endings do not change it)."""
    with open(path, encoding="utf-8", newline=None) as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ the page's Min and Max on load
def read_page_data(page_path: str) -> dict:
    """The embedded data of forecast/inventory.html as a dict."""
    with open(page_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'<script[^>]*id="inventory-data"[^>]*>(.*?)</script>', text, re.DOTALL)
    if not m:
        raise OperationPlanError(f"no embedded inventory data in {page_path}")
    return json.loads(m.group(1))


def interpolate_grid(grid: list, target: float) -> dict:
    """Python port of the page's interpolateGridAtNotLate: per item Min and Max_median at a target not_late, linear between grid points,
    the end point outside the grid's range."""
    def as_result(g):
        return {it["code"]: (it["Min"], it["Max_median"]) for it in g["items"]}
    if target <= grid[0]["not_late_median_pct"]:
        return as_result(grid[0])
    if target >= grid[-1]["not_late_median_pct"]:
        return as_result(grid[-1])
    for a, b in zip(grid[:-1], grid[1:]):
        if a["not_late_median_pct"] <= target <= b["not_late_median_pct"]:
            span = b["not_late_median_pct"] - a["not_late_median_pct"]
            t = (target - a["not_late_median_pct"]) / span
            bi = {it["code"]: it for it in b["items"]}
            return {ai["code"]: (ai["Min"] + (bi[ai["code"]]["Min"] - ai["Min"]) * t,
                                 ai["Max_median"] + (bi[ai["code"]]["Max_median"] - ai["Max_median"]) * t) for ai in a["items"]}
    raise OperationPlanError("the target not_late is inside the grid but no segment holds it")


def page_default_min_max(data: dict, division: str) -> pd.DataFrame:
    """Per forecast-status item of `division`: class (policy), Min, Max and where they come from, as the page shows them on load.

    * a division with a calibrated section (curve_target; PEM101): the section's item table at its default preset (the one the page applies on
      load, `today_lowest_stock`), Min and the median Max;
    * any other division (PEM107): the item table at the default controls (`tier_a_defaults`), the Python mirror of the page's engine.
    Items with no Min or Max (not computable) carry NaN."""
    import inventory_recompute_reference as ref
    div = data["divisions"][division]
    ct = div.get("curve_target")
    rows = []
    if ct:
        target = ct["presets"]["today_lowest_stock"]["not_late_pct"]
        mm = interpolate_grid(ct["grid"], target)
        source = "calibrated_section_default"
        for it in div["items"]:
            lo, hi = mm.get(it["code"], (np.nan, np.nan)) if it["policy"] == "stock_policy" else (np.nan, np.nan)
            rows.append({"division": division, "item": it["code"], "class": it["policy"], "min": lo, "max": hi,
                         "min_max_source": source if it["policy"] == "stock_policy" else ""})
    else:
        controls, dpm = data["tier_a_defaults"], data["days_per_month"]
        for it in div["items"]:
            lo = hi = np.nan
            if ref.gets_min_max(it):
                r = ref.compute_item_min_max(it, controls, dpm)
                if r["min"] is not None:
                    lo, hi = r["min"], r["max"]
            rows.append({"division": division, "item": it["code"], "class": it["policy"], "min": lo, "max": hi,
                         "min_max_source": "main_table_default" if ref.gets_min_max(it) else ""})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ the production forecast
def latest_vintage_forecast(root: str, cfg: dict) -> tuple:
    """(forecast frame item x month, vintage id, target months, row hash verified True). Reads the forward-test log, takes the latest vintage's
    Item-level rows, and checks that vintage's rows against the hash recorded in the log's metadata (stops on a difference)."""
    import forward_test_common as ftc
    log = ftc.read_forward_test_log(path_of(root, cfg["forecast_log_file"]))
    meta = ftc.load_metadata(path_of(root, cfg["forecast_log_metadata_file"]))
    vid = int(log["vintage_id"].max())
    rows = log[log["vintage_id"] == vid]
    entry = meta[str(vid)] if str(vid) in meta else meta[vid]
    scheme = entry.get("row_hash_scheme", ftc.HASH_SCHEME_CSV_READBACK)
    if ftc.compute_row_integrity_hash(rows, scheme) != entry["row_integrity_hash"]:
        raise OperationPlanError(f"vintage {vid} of the forward-test log does not hash to the value recorded in its metadata")
    item_rows = rows[rows["level"] == cfg["forecast_level"]]
    wide = item_rows.pivot_table(index="itemcode", columns="target_month", values="forecast_qty", aggfunc="sum")
    return wide, vid, sorted(item_rows["target_month"].unique()), True


def plan_months(vintage_months: list, today: pd.Timestamp) -> list:
    """The vintage's target months from the current month onward."""
    current = today.strftime("%Y-%m")
    months = [m for m in vintage_months if m >= current]
    if not months:
        raise OperationPlanError(f"the latest vintage covers {vintage_months[0]} to {vintage_months[-1]}, nothing from {current} onward")
    return months


# ------------------------------------------------------------------ saved pulls
def pull_meta(pull_dir: str) -> dict:
    with open(os.path.join(pull_dir, "pull_meta.json"), encoding="utf-8") as f:
        return json.load(f)


def latest_pull_dir(root: str, rel_dirs: list) -> str:
    """The saved pull with the latest pulled_at_local among the directories that hold one."""
    found = []
    for rel in rel_dirs:
        d = path_of(root, rel)
        if os.path.exists(os.path.join(d, "pull_meta.json")):
            found.append((pull_meta(d)["pulled_at_local"], d))
    if not found:
        raise OperationPlanError(f"no saved pull in {rel_dirs}")
    return max(found)[1]


def sellable_on_hand(inventory: pd.DataFrame, division_items: dict, sellable: dict) -> pd.Series:
    """Per item, the stock summed over the division's configured sellable warehouses. `division_items` maps division -> item codes."""
    inv = inventory.copy()
    inv["itemcode"] = inv["itemcode"].astype(str).str.strip()
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    out = {}
    for division, items in division_items.items():
        sub = inv[inv["itemcode"].isin(items) & inv["warehouse"].isin(sellable[division])]
        s = sub.groupby("itemcode")["stock"].sum()
        for c in items:
            out[(division, c)] = float(s.get(c, 0.0))
    return pd.Series(out)


def backlog_by_month(backlog: pd.DataFrame, months: list) -> pd.DataFrame:
    """Confirmed quantity (ActualQty + BacklogQty) of Cube_CES Status = 'Backlog' rows per item and plan month by ForecastDelDate month;
    a date before the first plan month goes into it; a date after the last month is left out and counted. Returns (frame item x month, n_after)."""
    b = backlog.copy()
    b["qty"] = b["ActualQty"].fillna(0) + b["BacklogQty"].fillna(0)
    b["ym"] = pd.to_datetime(b["ForecastDelDate"]).dt.strftime("%Y-%m")
    n_after = int((b["ym"] > months[-1]).sum())
    b = b[b["ym"] <= months[-1]].copy()
    b["month"] = b["ym"].where(b["ym"] >= months[0], months[0])
    wide = b.pivot_table(index="ItemCode", columns="month", values="qty", aggfunc="sum").reindex(columns=months).fillna(0.0)
    return wide, n_after


# ------------------------------------------------------------------ the simulation
def simulate_item(opening: float, demand: list, min_qty: float, max_qty: float, open_orders: list = None, tol: float = 1e-9) -> list:
    """Month by month: closing = opening - demand + open orders; when closing < Min, production = Max - closing and the closing position is Max.
    Returns one dict per month: opening, demand, open_orders, planned_production, closing."""
    open_orders = open_orders or [0.0] * len(demand)
    rows, stock = [], float(opening)
    for d, o in zip(demand, open_orders):
        closing = stock - d + o
        produce = 0.0
        if closing < min_qty - tol:
            produce = max_qty - closing
            closing = max_qty
        rows.append({"opening": stock, "demand": d, "open_orders": o, "planned_production": produce, "closing": closing})
        stock = closing
    return rows


# ------------------------------------------------------------------ capacity
def capacity_reference(cube_final_path: str, item_division_path: str, cfg_capacity: dict, divisions: list) -> dict:
    """Highest sustained monthly output per division, by the method of DATA_MAP.md (cube_final entry): transfer_qty summed by the calendar month
    of final_date, items joined to their division by the item-division map; the highest month, passing over an isolated spike (a month at least
    spike_ratio times the next-highest). Returns {division: {"capacity", "month", "passed_over", "top5"}}."""
    cf = pd.read_csv(cube_final_path, usecols=["itemcode", cfg_capacity["date_column"], cfg_capacity["quantity_column"]])
    m = pd.read_csv(item_division_path).set_index("code")["item_division"]
    cf = cf.merge(m.rename("division"), left_on="itemcode", right_index=True)
    cf["month"] = pd.to_datetime(cf[cfg_capacity["date_column"]]).dt.strftime("%Y-%m")
    monthly = cf.groupby(["division", "month"])[cfg_capacity["quantity_column"]].sum().reset_index()
    out = {}
    for division in divisions:
        x = monthly[monthly["division"] == division].sort_values(cfg_capacity["quantity_column"], ascending=False).reset_index(drop=True)
        q = x[cfg_capacity["quantity_column"]].tolist()
        pick, passed = 0, []
        while pick + 1 < len(q) and q[pick] >= cfg_capacity["spike_ratio"] * q[pick + 1]:
            passed.append(x.loc[pick, "month"])
            pick += 1
        out[division] = {"capacity": float(q[pick]), "month": x.loc[pick, "month"], "passed_over": passed,
                         "top5": [[x.loc[i, "month"], float(q[i])] for i in range(min(5, len(x)))]}
    return out


# ------------------------------------------------------------------ the plan
def build_plan(root: str = PROJECT_ROOT, today: pd.Timestamp = None, open_orders: pd.DataFrame = None, cfg: dict = None,
               full_cfg: dict = None, page_path: str = None) -> dict:
    """Computes the plan from the recorded inputs under `root`. `open_orders` (columns item, month, qty) is added to the simulation only when
    config open_orders_usable is true; otherwise it is ignored and the result says none were counted. Returns
    {"item_month": DataFrame, "division_month": DataFrame, "meta": dict}. `page_path` replaces the configured page (the runner passes the page it just built)."""
    full_cfg = full_cfg or load_full_config(root)
    cfg = cfg or full_cfg["operation_plan"]
    today = pd.Timestamp(today) if today is not None else pd.Timestamp(datetime.now().date())
    tol = float(cfg["tolerance_units"])
    data = read_page_data(page_path or path_of(root, cfg["inventory_page_file"]))
    min_max = pd.concat([page_default_min_max(data, d) for d in cfg["divisions"]], ignore_index=True)

    forecast, vid, vintage_months, _ = latest_vintage_forecast(root, cfg)
    months = plan_months(vintage_months, today)
    backlog_dir = latest_pull_dir(root, cfg["backlog_pull_dirs"])
    stock_dir = path_of(root, cfg["stock_pull_dir"])
    import build_inventory_dataset as bid
    b_frames, b_meta = bid.load_pulls(backlog_dir)
    s_frames, s_meta = bid.load_pulls(stock_dir)
    backlog, n_backlog_after = backlog_by_month(b_frames["backlog_ces"], months)
    division_items = {d: min_max[min_max["division"] == d]["item"].tolist() for d in cfg["divisions"]}
    sellable = full_cfg["phase_e1_assumptions"]["sellable_warehouse_codes"]
    on_hand = sellable_on_hand(s_frames["inventory"], division_items, sellable)
    use_open = bool(cfg["open_orders_usable"]) and open_orders is not None
    oo = {}
    if use_open:
        for (item, month), q in open_orders.groupby(["item", "month"])["qty"].sum().items():
            oo[(item, month)] = float(q)

    rows, no_min_max = [], []
    for _, r in min_max.iterrows():
        d, item, cls = r["division"], r["item"], r["class"]
        f = [float(forecast.loc[item, m]) if item in forecast.index and m in forecast.columns and pd.notna(forecast.loc[item, m]) else 0.0 for m in months]
        b = [float(backlog.loc[item, m]) if item in backlog.index else 0.0 for m in months]
        dem = [max(x, y) for x, y in zip(f, b)]
        src = ["backlog" if y > x else "forecast" for x, y in zip(f, b)]
        has_mm = cls in cfg["classes_with_min_max"] and pd.notna(r["min"]) and pd.notna(r["max"])
        if cls in cfg["classes_with_min_max"] and not has_mm:
            no_min_max.append(item)
        if has_mm:
            sim = simulate_item(on_hand[(d, item)], dem, float(r["min"]), float(r["max"]), [oo.get((item, m), 0.0) for m in months], tol)
        for i, m in enumerate(months):
            row = {"division": d, "item": item, "class": cls, "min_max_source": r["min_max_source"], "month": m, "forecast": f[i],
                   "backlog_due": b[i], "demand": dem[i], "demand_source": src[i]}
            if has_mm:
                row.update({"opening": sim[i]["opening"], "open_orders": sim[i]["open_orders"], "min": float(r["min"]), "max": float(r["max"]),
                            "planned_production": sim[i]["planned_production"], "closing": sim[i]["closing"], "load": np.nan})
            else:
                row.update({"opening": np.nan, "open_orders": np.nan, "min": np.nan, "max": np.nan, "planned_production": np.nan,
                            "closing": np.nan, "load": dem[i]})
            rows.append(row)
    item_month = pd.DataFrame(rows, columns=ITEM_MONTH_COLUMNS)

    cap = capacity_reference(path_of(root, cfg["capacity"]["cube_final_file"]), path_of(root, cfg["capacity"]["item_division_file"]),
                             cfg["capacity"], cfg["divisions"])
    drows = []
    for d in cfg["divisions"]:
        for m in months:
            sub = item_month[(item_month["division"] == d) & (item_month["month"] == m)]
            prod = float(sub["planned_production"].sum())
            cto = float(sub.loc[sub["class"] == "confirmed_to_order", "load"].sum())
            cfl = float(sub.loc[sub["class"] == "conflict", "load"].sum())
            total = prod + cto + cfl
            c = cap[d]["capacity"]
            drows.append({"division": d, "month": m, "planned_production_stock": prod, "load_confirmed_to_order": cto, "load_conflict": cfl,
                          "total_load": total, "capacity": c, "share_of_capacity": total / c, "above_capacity": bool(total > c)})
    division_month = pd.DataFrame(drows, columns=DIVISION_MONTH_COLUMNS)

    a_items = item_month[item_month["planned_production"].notna()]
    produced = a_items.groupby("item")["planned_production"].sum()
    by_month = a_items.groupby("month")["planned_production"].sum()
    meta = {
        "built_at": datetime.now().isoformat(timespec="seconds"), "today": str(today.date()), "months": months,
        "vintage_id": vid, "vintage_months": vintage_months, "forecast_vintage_hash_verified": True,
        "stock_pull": {"dir": cfg["stock_pull_dir"], "pulled_at_local": s_meta["pulled_at_local"]},
        "backlog_pull": {"dir": os.path.relpath(backlog_dir, root).replace("\\", "/"), "pulled_at_local": b_meta["pulled_at_local"]},
        "page": {"file": cfg["inventory_page_file"], "built_at": data.get("page_built_at"),
                 "default_not_late_pct": data["divisions"]["PEM101"]["curve_target"]["presets"]["today_lowest_stock"]["not_late_pct"]},
        "counts": {"items": int(item_month["item"].nunique()),
                   "by_division": {d: int(item_month[item_month["division"] == d]["item"].nunique()) for d in cfg["divisions"]},
                   "with_min_max": {d: int(a_items[a_items["division"] == d]["item"].nunique()) for d in cfg["divisions"]},
                   "without_min_max": int(item_month[item_month["planned_production"].isna()]["item"].nunique()),
                   "stock_policy_without_min_max": sorted(no_min_max),
                   "items_needing_production": int((produced > tol).sum()),
                   "item_months_backlog_above_forecast": int((item_month["backlog_due"] > item_month["forecast"]).sum()),
                   "backlog_rows_after_last_month": n_backlog_after},
        "replenishment_by_month": {m: float(by_month.get(m, 0.0)) for m in months},
        "capacity": cap,
        "open_orders": {"usable": bool(cfg["open_orders_usable"]), "counted": bool(use_open),
                        "n_rows": int(len(open_orders)) if use_open else 0},
        "assumptions": ["open production orders are not counted (Part 1 test)", "sellable warehouses are the configured assumption (phase_e1_assumptions)",
                        "capacity is a lower bound: the highest sustained monthly output seen, units summed across products",
                        "PEM101 Min and Max are those of the calibrated section on load (lead time free, 36 members); PEM107 those of the item table on load",
                        "production quantity is not rounded and has no minimum lot or batch size",
                        "stock at the start is the sellable on-hand of the latest daily pull; no in-process or open production adds to it"],
    }
    return {"item_month": item_month, "division_month": division_month, "meta": meta}


# ------------------------------------------------------------------ recorded outputs
def write_outputs(plan: dict, root: str = PROJECT_ROOT, cfg: dict = None, out_dir: str = None) -> dict:
    """Writes the two CSVs, the meta JSON and the integrity file (SHA-256 of each file's bytes). `out_dir` replaces the folder of the configured
    paths (for the runner's temporary copy and for tests)."""
    cfg = cfg or load_config(root)

    def target(key):
        p = path_of(root, cfg[key])
        return os.path.join(out_dir, os.path.basename(p)) if out_dir else p
    paths = {k: target(k) for k in ("output_item_month_file", "output_division_month_file", "output_meta_file", "output_integrity_file")}
    os.makedirs(os.path.dirname(paths["output_item_month_file"]), exist_ok=True)
    plan["item_month"].to_csv(paths["output_item_month_file"], index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f")
    plan["division_month"].to_csv(paths["output_division_month_file"], index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f")
    with open(paths["output_meta_file"], "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan["meta"], f, indent=1, ensure_ascii=False, default=str)
        f.write("\n")
    integrity = {"recorded_at": datetime.now().isoformat(timespec="seconds"),
                 "files": {os.path.basename(paths[k]): {"sha256": sha256_file(paths[k])}
                           for k in ("output_item_month_file", "output_division_month_file", "output_meta_file")}}
    with open(paths["output_integrity_file"], "w", encoding="utf-8", newline="\n") as f:
        json.dump(integrity, f, indent=1)
    return {"paths": paths, "integrity": integrity}


def verify_outputs(root: str = PROJECT_ROOT, cfg: dict = None, out_dir: str = None) -> dict:
    """Checks the recorded outputs against their SHA-256; raises OperationPlanError on a missing file or a hash that differs."""
    cfg = cfg or load_config(root)
    integ = path_of(root, cfg["output_integrity_file"])
    if out_dir:
        integ = os.path.join(out_dir, os.path.basename(integ))
    if not os.path.exists(integ):
        raise OperationPlanError(f"integrity file missing: {integ}")
    with open(integ, encoding="utf-8") as f:
        rec = json.load(f)
    for name, v in rec["files"].items():
        p = os.path.join(os.path.dirname(integ), name)
        if not os.path.exists(p):
            raise OperationPlanError(f"recorded output missing: {p}")
        if sha256_file(p) != v["sha256"]:
            raise OperationPlanError(f"{name} does not hash to the value recorded in {os.path.basename(integ)}")
    return rec


def read_outputs(root: str = PROJECT_ROOT, cfg: dict = None, out_dir: str = None) -> tuple:
    """(item_month, division_month, meta) after the hash check."""
    cfg = cfg or load_config(root)
    verify_outputs(root, cfg, out_dir)

    def target(key):
        p = path_of(root, cfg[key])
        return os.path.join(out_dir, os.path.basename(p)) if out_dir else p
    with open(target("output_meta_file"), encoding="utf-8") as f:
        meta = json.load(f)
    return (pd.read_csv(target("output_item_month_file")), pd.read_csv(target("output_division_month_file")), meta)


def _display_path(path: str, root: str) -> str:
    """Path relative to the project root when it is inside it, otherwise as given."""
    try:
        return os.path.relpath(path, root).replace("\\", "/") if os.path.commonpath([path, root]) == root else path
    except ValueError:
        return path


def run(root: str = PROJECT_ROOT, today: pd.Timestamp = None, out_dir: str = None, page_path: str = None) -> dict:
    """Builds, writes, verifies and summarises the plan; the runner's step calls this."""
    plan = build_plan(root, today, page_path=page_path)
    written = write_outputs(plan, root, out_dir=out_dir)
    verify_outputs(root, out_dir=out_dir)
    meta = plan["meta"]
    return {"months": meta["months"], "counts": meta["counts"], "capacity": {d: v["capacity"] for d, v in meta["capacity"].items()},
            "capacity_matches_data_map": capacity_matches_data_map(meta["capacity"], load_config(root)),
            "months_above_capacity": plan["division_month"].loc[plan["division_month"]["above_capacity"], ["division", "month"]].values.tolist(),
            "open_orders_counted": meta["open_orders"]["counted"], "written_to": {k: _display_path(v, root) for k, v in written["paths"].items()}}


def capacity_matches_data_map(capacity: dict, cfg: dict) -> bool:
    ref = cfg["capacity"]["data_map_reference"]
    return all(abs(capacity[d]["capacity"] - float(ref[d])) < 0.5 for d in ref)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(run(), indent=1, default=str))
