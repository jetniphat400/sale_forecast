"""Builds the data of the Trend tab of index.html ("Trend Pricelist Omni 2024-2026") from a saved pull of cube_Sale_APD.

Two stages, both run by the monthly runner (src/monthly_refresh.py):
  --pull   one read-only database session: three aggregate queries over the tab's scope (rows grouped by item, day and status; the most frequent
           product name per item; one completeness query), saved under output/data/trend_pull/ (untracked).
  --build  reads the saved pull and the price list, computes the tab's data, checks it against the completeness query and writes it into index.html between
           the markers TREND-DATA-BEGIN and TREND-DATA-END. Nothing else of index.html is touched. Makes no database connection.

Scope (as built in August 2026, kept): Price List items of the visible sheets; cube_Sale_APD rows with revenue_type 'Omni Channel', status Actual and MPS
(kept apart as qty and sale columns), createDate from the configured start date (config trend_tab, source_table, status_basis, date_range). The time axis is
createDate (PO receipt date). Grain of the pull: item x calendar day x status; the months of the tab are summed from those daily rows, so the daily drill-down
and the months agree. The month of the pull date is incomplete: shown faded and left out of ADI and CV2 (Syntetos-Boylan cut-offs from config trend_tab).

The spec remark of every item (ok / conflict / nospec / nodata) follows the August 2026 logic (specs()); the database name shown in the tooltip is the item's
most frequent product name in the scope.
"""
import argparse
import json
import logging
import math
import os
import re
import sys
from datetime import datetime

import pandas as pd
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger("build_trend_tab")

BEGIN_MARK = "/* TREND-DATA-BEGIN */"
END_MARK = "/* TREND-DATA-END */"
CODE_PATTERN = re.compile(r"^[A-Za-z0-9._\-]+$")


class TrendTabError(Exception):
    """The Trend tab's data could not be built or failed its check; nothing is written."""


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Spec remark (August 2026 logic, used as given)
# ---------------------------------------------------------------------------------------------------------------------------------------------

TH = [('เควี', 'kv'), ('กิโลโวลท์', 'kv'), ('กิโลโวลต์', 'kv'), ('แอมป์', 'a'), ('แอมแปร์', 'a'), ('โวลท์', 'v'), ('โวลต์', 'v'), ('เฮิรตซ์', 'hz')]
UNIT = r'(?:kvar|kva|kv|ka|ma|amps?|a|var|va|v|hz|kw|w|mm2|mm|m)'
K = {'kv': ('v', 1000), 'ka': ('a', 1000), 'kva': ('va', 1000), 'kvar': ('var', 1000), 'kw': ('w', 1000), 'amp': ('a', 1), 'amps': ('a', 1), 'ma': ('a', 0.001)}


def specs(s: str) -> set:
    """The numeric specs written in a product description or name, as {'22000v', '630a', ...} (units folded to v, a, va, var, w; kV x 1000)."""
    s = s.lower()
    s = re.sub(r'(\d),(?=\d{3})', r'\1', s)
    s = s.replace('√3', '').replace('/3', '')
    for th, en in TH:
        s = s.replace(th, ' ' + en)
    s = re.sub(r'(\d)[\s\.]*(' + UNIT + r')(?![a-z0-9])', r'\1\2', s)
    out = set()
    for num, unit in re.findall(r'(\d+(?:\.\d+)?)(' + UNIT + r')(?![a-z0-9])', s):
        v = float(num)
        if unit in K:
            u, m = K[unit]
            v *= m
            unit = u
        out.add(f'{v:g}{unit}')
    return out


_UNIT_ORDER = ["v", "a", "va", "var", "w", "hz", "mm2", "mm", "m"]
_UNIT_LABEL = {"v": "V", "a": "A", "va": "VA", "var": "VAR", "w": "W", "hz": "HZ", "mm2": "mm2", "mm": "mm", "m": "m"}
_KILO = {"v": "kV", "a": "kA", "va": "kVA", "var": "kVAR", "w": "kW"}


def format_specs(values: set) -> str:
    """A spec set for the tooltip in plain string order, for example '22kV, 630A' (v, a, va, var and w from 1000 up are shown in k units)."""
    parsed = []
    for x in values:
        m = re.match(r'(\d+(?:\.\d+)?)([a-z0-9]+)$', x)
        parsed.append((_UNIT_ORDER.index(m.group(2)) if m.group(2) in _UNIT_ORDER else 99, float(m.group(1)), m.group(2)))
    out = []
    for _, num, unit in parsed:
        out.append(f"{num / 1000:g}{_KILO[unit]}" if unit in _KILO and num >= 1000 else f"{num:g}{_UNIT_LABEL.get(unit, unit)}")
    return ", ".join(sorted(out))


def spec_status(pl_descriptions: list, db_name, has_sales: bool) -> tuple:
    """(status, price-list specs, database specs): nodata when the item has no sales in the scope; nospec when either side has no spec; ok when the two are equal or
    one is contained in the other; conflict otherwise."""
    if not has_sales:
        return "nodata", set(), set()
    sp_pl = specs(" / ".join(pl_descriptions))
    sp_db = specs(db_name or "")
    if not sp_pl or not sp_db:
        return "nospec", sp_pl, sp_db
    if sp_pl == sp_db or sp_pl <= sp_db or sp_db <= sp_pl:
        return "ok", sp_pl, sp_db
    return "conflict", sp_pl, sp_db


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Demand classes
# ---------------------------------------------------------------------------------------------------------------------------------------------

def demand_stats(qty_complete: list) -> tuple:
    """(ADI, CV2) over the complete months: ADI = months / months with qty > 0; CV2 = population variance / mean^2 of qty over months with qty > 0. (None, None) when no month has qty > 0."""
    nz = [float(x) for x in qty_complete if x > 0]
    if not nz:
        return None, None
    adi = len(qty_complete) / len(nz)
    mean = sum(nz) / len(nz)
    var = sum((x - mean) ** 2 for x in nz) / len(nz)
    return adi, var / (mean * mean)


def demand_class(adi: float, cv2: float, adi_cut: float, cv2_cut: float) -> str:
    """Syntetos-Boylan: Smooth (ADI below, CV2 below), Erratic (ADI below, CV2 at or above), Intermittent (ADI at or above, CV2 below), Lumpy (both at or above)."""
    if adi < adi_cut:
        return "Smooth" if cv2 < cv2_cut else "Erratic"
    return "Intermittent" if cv2 < cv2_cut else "Lumpy"


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Configuration and the price list
# ---------------------------------------------------------------------------------------------------------------------------------------------

def load_config(root: str = PROJECT_ROOT) -> dict:
    with open(os.path.join(root, "config", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def pricelist_rows(root: str, config: dict) -> pd.DataFrame:
    """The visible-sheet rows of the price list with the division of the sheet (config sheet_to_division) and a cleaned description."""
    sys.path.insert(0, os.path.join(root, "src"))
    from pricelist_reader import load_visible_product_rows
    pl = load_visible_product_rows(os.path.join(root, "reference", "pricelist.xlsx"))
    to_div = config["sheet_to_division"]
    missing = set(pl["sheet"].unique()) - set(to_div)
    if missing:
        raise TrendTabError(f"sheets with product rows and no sheet_to_division entry: {sorted(missing)}")
    pl = pl.assign(division=pl["sheet"].map(to_div))
    for col in ("category", "type", "description"):
        pl[col] = pl[col].map(lambda v: " ".join(str(v).split()) if pd.notna(v) else "")
    return pl


def pricelist_label(root: str) -> str:
    """The quarter label of the price list (for example Q3'2026), read from the title cell of every visible product sheet; the sheets must agree."""
    import openpyxl
    wb = openpyxl.load_workbook(os.path.join(root, "reference", "pricelist.xlsx"), read_only=True, data_only=True)
    labels = set()
    for name in wb.sheetnames:
        ws = wb[name]
        if ws.sheet_state != "visible":
            continue
        rows = list(ws.iter_rows(min_row=1, max_row=3, values_only=True))
        if len(rows) < 3 or not any(h and "product code" in str(h).lower() for h in rows[2]):
            continue
        title = " ".join(str(v) for v in rows[0] if v)
        m = re.search(r"Price List\s+(\S+)", title)
        if not m:
            raise TrendTabError(f"price list sheet {name!r} has no 'Price List <label>' in its title row")
        labels.add(m.group(1))
    if len(labels) != 1:
        raise TrendTabError(f"the visible product sheets name {len(labels)} different price list labels: {sorted(labels)}")
    return labels.pop()


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Pull (one read-only session, aggregate queries only)
# ---------------------------------------------------------------------------------------------------------------------------------------------

def scope_where(codes: list, config: dict) -> str:
    """The WHERE clause of the tab's scope; item codes come from the price list and are checked against a strict pattern before they are written into SQL."""
    bad = [c for c in codes if not CODE_PATTERN.match(c)]
    if bad:
        raise TrendTabError(f"item codes with characters outside the allowed set: {bad[:5]}")
    t = config["trend_tab"]
    code_list = "','".join(sorted(codes))
    status_list = "','".join(config["status_basis"])
    return (f"revenue_type = '{t['revenue_type']}' AND status IN ('{status_list}') AND createDate >= '{config['date_range']['start']}' "
            f"AND itemcode IN ('{code_list}')")


def pull(root: str = PROJECT_ROOT, queries_extra=None) -> dict:
    """Runs the three queries in ONE session (no retry: a login failure raises), saves them under config trend_tab.pull_dir and returns them.
    `queries_extra(run_query)` may run further aggregate queries inside the same session (used once, by the task that proved the VAT treatment)."""
    import db
    config = load_config(root)
    pl = pricelist_rows(root, config)
    codes = sorted(pl["code"].unique())
    where = scope_where(codes, config)
    table = config["source_table"]
    out_dir = os.path.join(root, *config["trend_tab"]["pull_dir"].split("/"))
    os.makedirs(out_dir, exist_ok=True)
    extra = None
    with db.session():
        pulled_at = datetime.now().isoformat(timespec="seconds")
        daily = db.run_query(f"SELECT itemcode, CAST(createDate AS date) AS d, status, SUM(qty) AS q, SUM(sale) AS s, COUNT(*) AS n FROM {table} WHERE {where} "
                             f"GROUP BY itemcode, CAST(createDate AS date), status")
        names = db.run_query(f"SELECT itemcode, productName, COUNT(*) AS n FROM {table} WHERE {where} GROUP BY itemcode, productName")
        total = db.run_query(f"SELECT COUNT(*) AS n_rows, SUM(qty) AS q, SUM(sale) AS s, MIN(CAST(createDate AS date)) AS first_d, MAX(CAST(createDate AS date)) AS last_d "
                             f"FROM {table} WHERE {where}")
        if queries_extra is not None:
            extra = queries_extra(db.run_query, table, where)
    completeness = {"pulled_at": pulled_at, "n_rows": int(total["n_rows"].iloc[0]), "qty": float(total["q"].iloc[0]), "sale": float(total["s"].iloc[0]),
                    "first_date": str(total["first_d"].iloc[0])[:10], "last_date": str(total["last_d"].iloc[0])[:10], "n_codes_in_scope": len(codes)}
    daily["d"] = daily["d"].astype(str).str[:10]
    daily.to_csv(os.path.join(out_dir, "daily.csv"), index=False, encoding="utf-8")
    names.to_csv(os.path.join(out_dir, "names.csv"), index=False, encoding="utf-8")
    with open(os.path.join(out_dir, "completeness.json"), "w", encoding="utf-8") as f:       # written last: the runner reads its time as "pull finished"
        json.dump(completeness, f, ensure_ascii=False, indent=1)
    logger.info("Trend tab pull saved: %d daily rows, %d name rows, completeness %s", len(daily), len(names), completeness)
    return {"daily": daily, "names": names, "completeness": completeness, "extra": extra}


def read_pull(root: str, config: dict) -> tuple:
    d = os.path.join(root, *config["trend_tab"]["pull_dir"].split("/"))
    paths = [os.path.join(d, n) for n in ("daily.csv", "names.csv", "completeness.json")]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise TrendTabError(f"the saved Trend pull is missing: {[os.path.basename(p) for p in missing]} (run build_trend_tab.py --pull)")
    daily = pd.read_csv(paths[0], dtype={"itemcode": str, "status": str}).fillna({"q": 0.0, "s": 0.0})
    names = pd.read_csv(paths[1], dtype={"itemcode": str}, keep_default_na=False)
    with open(paths[2], encoding="utf-8") as f:
        completeness = json.load(f)
    return daily, names, completeness


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------------------------------------------------------------------------

def month_range(first: str, last: str) -> list:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def top_names(names: pd.DataFrame) -> tuple:
    """({itemcode: most frequent product name}, number of items whose top count is shared by more than one name). A tie is broken by the name in alphabetical order."""
    best, ties = {}, 0
    for code, g in names.groupby("itemcode"):
        g = g.assign(productName=g["productName"].astype(str)).sort_values(["n", "productName"], ascending=[False, True], kind="mergesort")
        if len(g) > 1 and g["n"].iloc[0] == g["n"].iloc[1]:
            ties += 1
        best[code] = " ".join(g["productName"].iloc[0].split())
    return best, ties


def build_data(daily: pd.DataFrame, names: pd.DataFrame, completeness: dict, pl: pd.DataFrame, config: dict, pricelist_quarter: str) -> tuple:
    """(OMNI dict, MATCH dict, report dict) from the saved pull and the price list. Stops (TrendTabError) when the totals of the data differ from the completeness
    query, when a daily row falls outside the months, or when a day's rows do not sum to the item's months."""
    import reader_values as rv
    t = config["trend_tab"]
    pulled_at = pd.Timestamp(completeness["pulled_at"])
    first_month = str(config["date_range"]["start"])[:7]
    last_month = f"{pulled_at.year:04d}-{pulled_at.month:02d}"
    months = month_range(first_month, last_month)
    midx = {m: i for i, m in enumerate(months)}
    n_months = len(months)
    n_complete = n_months - 1                                   # the month of the pull date is incomplete
    daily = daily.copy()
    daily["ym"] = daily["d"].astype(str).str[:7]
    outside = daily[~daily["ym"].isin(midx)]
    if len(outside):
        raise TrendTabError(f"{len(outside)} daily rows fall outside the months {months[0]}..{months[-1]} (latest {outside['d'].max()})")
    codes = sorted(pl["code"].unique())
    best_name, n_ties = top_names(names)
    items, match = [], {}
    by_item = {c: g for c, g in daily.groupby("itemcode")}
    n_multi_sheet = int((pl.drop_duplicates(["sheet", "code"]).groupby("code")["sheet"].nunique() > 1).sum())
    n_multi_row = int((pl.groupby("code").size() > 1).sum())
    adi_cut, cv2_cut = float(t["sb_adi_cutoff"]), float(t["sb_cv2_cutoff"])
    dec = int(t["decimals"])
    tot_q = tot_s = tot_n = 0.0
    for code in codes:
        rows = pl[pl["code"] == code]
        first = rows.iloc[0]
        qa, qm, sa, sm = ([0.0] * n_months for _ in range(4))
        dd = {}
        g = by_item.get(code)
        n_rows_item = 0
        if g is not None:
            for r in g.itertuples():
                i = midx[r.ym]
                if r.status == "Actual":
                    qa[i] += float(r.q); sa[i] += float(r.s); k = (1, 2)
                else:
                    qm[i] += float(r.q); sm[i] += float(r.s); k = (3, 4)
                day = r.d[2:4] + r.d[5:7] + r.d[8:10]
                rec = dd.setdefault(int(day), [int(day), 0.0, 0.0, 0.0, 0.0])
                rec[k[0]] += float(r.q); rec[k[1]] += float(r.s)
                n_rows_item += int(r.n)
                tot_q += float(r.q); tot_s += float(r.s); tot_n += int(r.n)
        dd_list = [[d[0]] + [round(x, 4) for x in d[1:]] for _, d in sorted(dd.items())]
        qty_all = [a + b for a, b in zip(qa, qm)]
        has_sales = n_rows_item > 0
        adi, cv2 = demand_stats(qty_all[:n_complete])
        if sum(qty_all) == 0 and not has_sales:
            cls = "NoSale"
        elif adi is None:
            cls = "NoSale31M"                                    # sales only in the incomplete month: no ADI and CV2
        else:
            cls = demand_class(adi, cv2, adi_cut, cv2_cut)
        name = " / ".join(dict.fromkeys(rows["description"]))
        item = {"c": code, "n": name, "cat": first["category"] or "-", "pt": first["type"] or "-", "sh": sorted(rows["division"].unique()), "cls": cls,
                "adi": None if adi is None else round(adi, dec), "cv2": None if cv2 is None else round(cv2, dec),
                "qa": [round(x, 4) for x in qa], "qm": [round(x, 4) for x in qm], "sa": [round(x, 2) for x in sa], "sm": [round(x, 2) for x in sm], "dd": dd_list}
        if has_sales:
            item["dbn"] = best_name.get(code, "")
        if len(rows) > 1:
            item["rk"] = f"รหัสเดียวมี {len(rows)} รายการใน pricelist"
        # the daily rows of the item sum to its months, exactly (to the cent / to 4 decimals)
        dq = sum(d[1] + d[3] for d in dd_list); ds = sum(d[2] + d[4] for d in dd_list)
        if abs(dq - sum(qty_all)) > 1e-3 or abs(ds - (sum(sa) + sum(sm))) > 0.05:
            raise TrendTabError(f"{code}: the daily rows do not sum to the months")
        items.append(item)
        status, sp_pl, sp_db = spec_status(list(dict.fromkeys(rows["description"])), item.get("dbn"), has_sales)
        entry = {"s": status}
        if has_sales:
            entry["dbn"] = item["dbn"]
        if status == "conflict":
            entry["pl_spec"], entry["db_spec"] = format_specs(sp_pl), format_specs(sp_db)
        match[code] = entry
    # the tab's totals equal the completeness query, exactly (rows; qty to 4 decimals; sale to the cent)
    items_q = sum(sum(i["qa"]) + sum(i["qm"]) for i in items); items_s = sum(sum(i["sa"]) + sum(i["sm"]) for i in items)
    checks = {"rows": (int(tot_n), completeness["n_rows"]), "qty": (round(tot_q, 4), round(completeness["qty"], 4)), "sale": (round(tot_s, 2), round(completeness["sale"], 2)),
              "items_qty": (round(items_q, 3), round(completeness["qty"], 3)), "items_sale": (round(items_s, 1), round(completeness["sale"], 1))}
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        raise TrendTabError(f"the Trend tab's totals differ from the completeness query: {bad}")
    omni = {"months": months, "n31": n_complete, "cates": sorted({i["cat"] for i in items}), "types": sorted({i["pt"] for i in items}), "items": items,
            "meta": {"pull": rv.thai_date_short(completeness["pulled_at"]), "pull_iso": completeness["pulled_at"][:10], "pricelist": pricelist_quarter,
                     "first_year": int(months[0][:4]), "last_year": int(months[-1][:4])}}
    report = {"n_items": len(items), "n_months": n_months, "n_complete": n_complete, "months": [months[0], months[-1]], "n_codes_on_more_than_one_sheet": n_multi_sheet,
              "n_codes_with_more_than_one_row": n_multi_row, "n_name_ties": n_ties, "totals": {"rows": int(tot_n), "qty": tot_q, "sale": tot_s},
              "classes": pd.Series([i["cls"] for i in items]).value_counts().to_dict(), "spec": pd.Series([m["s"] for m in match.values()]).value_counts().to_dict(),
              "pull_date": completeness["pulled_at"]}
    return omni, match, report


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def write_index(index_path: str, omni: dict, match: dict) -> None:
    """Replaces the two data blocks of the Trend tab between the markers. The first run wraps the existing `const MATCH = ...;` and `const OMNI = ...;` lines in the markers."""
    with open(index_path, encoding="utf-8", newline="") as f:
        text = f.read()
    block = f"{BEGIN_MARK}\nconst MATCH = {_json(match)};\nconst OMNI = {_json(omni)};\n{END_MARK}"
    if BEGIN_MARK in text:
        if text.count(BEGIN_MARK) != 1 or text.count(END_MARK) != 1:
            raise TrendTabError("index.html holds the data markers more than once")
        a, b = text.index(BEGIN_MARK), text.index(END_MARK) + len(END_MARK)
        new = text[:a] + block + text[b:]
    else:
        m = re.search(r"^const MATCH = \{.*?\};\r?\nconst OMNI = \{.*?\};", text, re.S | re.M)
        if not m or text.count("const OMNI = ") != 1:
            raise TrendTabError("index.html: the existing MATCH and OMNI data blocks were not found where expected")
        new = text[:m.start()] + block + text[m.end():]
    with open(index_path, "w", encoding="utf-8", newline="") as f:
        f.write(new)


def run_build(root: str = PROJECT_ROOT, index_path: str = None) -> dict:
    """Builds the tab's data from the saved pull and writes it into index.html (or `index_path`). Returns the report of the build."""
    config = load_config(root)
    daily, names, completeness = read_pull(root, config)
    pl = pricelist_rows(root, config)
    omni, match, report = build_data(daily, names, completeness, pl, config, pricelist_label(root))
    path = index_path or os.path.join(root, config["trend_tab"]["index_file"])
    write_index(path, omni, match)
    report["written_to"] = os.path.relpath(path, root) if path.startswith(root) else path
    logger.info("Trend tab data written: %s", {k: v for k, v in report.items() if k != "totals"})
    return report


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pull", action="store_true", help="one read-only database session; saves the pull")
    ap.add_argument("--build", action="store_true", help="builds the data from the saved pull into index.html")
    a = ap.parse_args(argv)
    if not (a.pull or a.build):
        ap.error("give --pull and/or --build")
    try:
        if a.pull:
            pull()
        if a.build:
            run_build()
    except TrendTabError as e:
        logger.error("TREND TAB: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
