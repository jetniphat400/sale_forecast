"""Build-time values for reader text on forecast/sales_report.html and forecast/inventory.html.

CONVENTIONS.md "Dynamic values": every number a dashboard reader sees is computed at build time
from verified data, config or a verified recorded output file; none is typed into reader text.
Each function below names its source. A recorded output file must exist in the repository, and
its value was verified by an earlier task (cited in the function's docstring); a missing file
raises, it never falls back to a typed number.
"""
import os
import re

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SEGMENTATION_SCRIPT = os.path.join(PROJECT_ROOT, "src", "investigations", "task2b_part2_fulfilment_segmentation.py")


class ReaderValueError(Exception):
    """A value for reader text could not be computed from its source; the build stops."""


def _read_csv(name: str) -> pd.DataFrame:
    path = os.path.join(SUMMARY_DIR, name)
    if not os.path.exists(path):
        raise ReaderValueError(f"Recorded output file missing: output/summary/{name} -- refusing to "
                               f"render a typed number in its place.")
    return pd.read_csv(path)


def backtest_settings(config: dict) -> dict:
    """config.yaml backtest block (METRICS.md Sec.39): months and origin spacing."""
    b = config["backtest"]
    total = b["train_months"] + b["val_months"] + b["test_months"]
    return {"total_months": total, "holdout": b["holdout_months"],
            "min_train": b["min_train_months"], "step": b["origin_step_months"]}


def backtest_rounds(config: dict) -> int:
    """Number of rolling origins, from config.yaml's backtest block; same construction as
    src/backtest_rekeyed.get_origins (tests/test_reader_values.py checks the two agree)."""
    s = backtest_settings(config)
    last_train = s["total_months"] - s["holdout"]
    origins = list(range(s["min_train"], last_train + 1, s["step"]))
    if origins[-1] != last_train:
        origins.append(last_train)
    return len(origins)


def total_history_months(config: dict) -> int:
    """Months of history in the series (config.yaml backtest block: train + validation + test)."""
    return backtest_settings(config)["total_months"]


def count_no_current_minmax() -> tuple:
    """(items with no current Min/Max setting, items in the pilot scope) from
    output/summary/phaseE1fix_2_current_minmax.csv (column has_current_setting; 128 pilot items).
    Figure first stated in STATUS.md Phase E1-fix-2 and re-derived directly from this file."""
    df = _read_csv("phaseE1fix_2_current_minmax.csv")
    return int((~df["has_current_setting"].astype(bool)).sum()), int(len(df))


def forecast_date_disagreement_pct() -> float:
    """Share of rows where forecast_date disagrees with PlanDelDate, in percent: rows in
    output/summary/phaseA_a1_task2_plandeldate_disagreement_rows.csv over the full-scope row count
    in phaseA_a1_task2_join_match_summary.csv (n_apd_rows_forecast_date_notnull). Verified by the
    Phase A forecast_date task (docs/reports/summary/phaseA_a1_forecastdate_revision_findings.md,
    STATUS.md Phase A verification)."""
    rows = _read_csv("phaseA_a1_task2_plandeldate_disagreement_rows.csv")
    summ = _read_csv("phaseA_a1_task2_join_match_summary.csv")
    full = summ[summ["scope"] == "full_128_scope"]
    if full.empty:
        raise ReaderValueError("phaseA_a1_task2_join_match_summary.csv has no full_128_scope row")
    return 100.0 * len(rows) / float(full["n_apd_rows_forecast_date_notnull"].iloc[0])


def fulfilment_notice_threshold_days() -> int:
    """S3_THRESHOLD_DAYS of the segmentation that produced the item classes (METRICS.md Sec.23),
    read from src/investigations/task2b_part2_fulfilment_segmentation.py."""
    with open(SEGMENTATION_SCRIPT, encoding="utf-8") as f:
        m = re.search(r"^S3_THRESHOLD_DAYS\s*=\s*(\d+)", f.read(), re.M)
    if not m:
        raise ReaderValueError("S3_THRESHOLD_DAYS not found in the segmentation script")
    return int(m.group(1))


def fulfilment_signal_count() -> int:
    """Number of behaviour signals (S1, S2, S3, ...) in output/summary/task2b_part2_item_level.csv."""
    df = _read_csv("task2b_part2_item_level.csv")
    return len([c for c in df.columns if re.fullmatch(r"S\d+", c)])


def staleness_threshold_days(config: dict) -> int:
    """config.yaml page_timestamps.staleness_threshold_days (METRICS.md Sec.26)."""
    return int(config["page_timestamps"]["staleness_threshold_days"])


def pipeline_gap_pct(pem101: dict, controls: dict, days_per_month: float) -> float:
    """Gap between the page's monthly-prorated stock value and the server-side daily-window
    figure for PEM101, in percent (absolute), at the default scenario, like for like: the items
    that the page gives a Min/Max AND that appear in output/summary/phaseE1fix_2_minmax_stockvalue.csv
    (column stock_value_contribution; Modeler/Validator agreement on its total recorded in
    STATUS.md Phase E1-fix-2, 0.09% apart)."""
    from inventory_recompute_reference import compute_all
    ref = _read_csv("phaseE1fix_2_minmax_stockvalue.csv").set_index("code")["stock_value_contribution"]
    page = compute_all(pem101, controls, days_per_month)
    rows = [p for p in page["per_item"] if p["stock_value_contribution"] > 0 and p["code"] in ref.index]
    page_total = sum(p["stock_value_contribution"] for p in rows)
    ref_total = float(ref.loc[[p["code"] for p in rows]].sum())
    if ref_total <= 0:
        raise ReaderValueError("recorded pipeline stock value is zero -- gap not computable")
    return abs(100.0 * (page_total - ref_total) / ref_total)


# Standard Thai month abbreviations (used for the month names of dates computed at build time). The year
# printed with them is the Gregorian year plus 543.
THAI_MONTH_ABBR = {1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.", 5: "พ.ค.", 6: "มิ.ย.",
                   7: "ก.ค.", 8: "ส.ค.", 9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."}


def thai_month_year(iso_date: str) -> str:
    """'2026-05-01' -> 'พ.ค. 2569' (Buddhist year = Gregorian + 543)."""
    y, m = int(iso_date[:4]), int(iso_date[5:7])
    return f"{THAI_MONTH_ABBR[m]} {y + 543}"


def intermittent_lumpy_share_pct() -> float:
    """Share (percent) of forecast-status items whose demand is Intermittent or Lumpy, by METRICS.md
    Sec.29 (ADI = months / months with sales; CV2 = population variance of the non-zero months over
    their mean squared; Intermittent ADI >= 1.32 and CV2 < 0.49, Lumpy ADI >= 1.32 and CV2 >= 0.49).
    Computed from output/data/processed_all_divisions_monthly_qty.csv (Actual+MPS quantity, the 31
    months of the series) for the items with status_category == 'forecast' in
    output/summary/phaseC_step1revised_item_status_445.csv. Items with no sales in the window
    (no ADI) are left out of the denominator. The Sec.29 formula was checked item by item against the
    dashboard's own classification (0 mismatches, METRICS.md Sec.29)."""
    monthly = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "data", "processed_all_divisions_monthly_qty.csv"))
    status = _read_csv("phaseC_step1revised_item_status_445.csv")
    forecast_codes = set(status[status["status_category"] == "forecast"]["itemcode"])
    n_classified = n_hit = 0
    for _code, g in monthly[monthly["itemcode"].isin(forecast_codes)].groupby("itemcode"):
        q = g["qty"].to_numpy(dtype=float)
        nonzero = q[q > 0]
        if len(nonzero) == 0:
            continue
        adi = len(q) / len(nonzero)
        cv2 = float(nonzero.var() / nonzero.mean() ** 2)
        n_classified += 1
        if adi >= 1.32:
            n_hit += 1        # Intermittent (CV2 < 0.49) or Lumpy (CV2 >= 0.49)
    if not n_classified:
        raise ReaderValueError("no forecast-status item has sales in the monthly series")
    return 100.0 * n_hit / n_classified


def first_scoring_month_label(config: dict) -> str:
    """Thai month and year of the first forward-test scoring round: the month of the first day after the
    first target month of output/summary/forward_test_log_all_divisions.csv has closed plus the leakage
    margin (config.yaml leakage_guard.min_margin_days), the same date step 6 of src/monthly_refresh.py
    reports as first_eligible_date."""
    log = pd.read_csv(os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions.csv"), usecols=["target_month"])
    first_target = sorted(log["target_month"].unique())[0]
    window_end = pd.Period(first_target, freq="M").end_time.normalize()
    eligible = window_end + pd.Timedelta(int(config["leakage_guard"]["min_margin_days"]), unit="D")
    return thai_month_year(str((eligible + pd.Timedelta(1, unit="D")).date()))




# ---------------------------------------------------------------------------------------------------------------------------------
# One shared formatter for the dates the dashboard pages write (decision of the prompt of 2026-10-08): a round ('ต.ค. 69'), a month
# ('ส.ค. 69') and a date-time ('8 ต.ค. 69 08:01'), Buddhist year as two digits. The Min-Max page's script writes the same date-time form
# with the same month list (tests/test_inventory_page_browser.py checks the two agree); every Python page builder imports these.

def thai_month_short(ym: str) -> str:
    """'2026-10' (or any 'YYYY-MM...' text) -> 'ต.ค. 69'."""
    y, m = int(str(ym)[:4]), int(str(ym)[5:7])
    return f"{THAI_MONTH_ABBR[m]} {str(y + 543)[-2:]}"


def thai_datetime_short(s) -> str:
    """'2026-10-06 08:00:40' -> '6 ต.ค. 69 08:00' (d MMM yy HH:mm, this machine's own clock, Buddhist year)."""
    t = pd.Timestamp(str(s)[:19])
    return f"{t.day} {THAI_MONTH_ABBR[t.month]} {str(t.year + 543)[-2:]} {t.strftime('%H:%M')}"


def vintage_facts(root: str = PROJECT_ROOT) -> dict:
    """What a page states about the latest forecast vintage it uses, read from the forward-test log and its metadata after the same hash check the plan
    uses (operation_plan.latest_vintage_forecast): vintage id, run date, the fit window (first and last month of the series the vintage was fitted on) and
    the forecast months, the forecast per item and month and the Item rows of the vintage (division and Type of each item). Stops when the metadata does not
    name the fit window."""
    import forward_test_common as ftc
    import operation_plan as op
    cfg = op.load_config(root)
    wide, vid, months, _ = op.latest_vintage_forecast(root, cfg)
    log = ftc.read_forward_test_log(op.path_of(root, cfg["forecast_log_file"]))
    meta = ftc.load_metadata(op.path_of(root, cfg["forecast_log_metadata_file"]))
    entry = meta[str(vid)] if str(vid) in meta else meta[vid]
    dates = sorted(set(log.loc[log["vintage_id"] == vid, "forecast_run_date"]))
    if len(dates) != 1:
        raise ReaderValueError(f"vintage {vid} has {len(dates)} run dates in the forward-test log: {dates}")
    for k in ("fit_first_month", "fit_last_month"):
        if not entry.get(k):
            raise ReaderValueError(f"the forward-test metadata of vintage {vid} has no {k}")
    item_rows = log[(log["vintage_id"] == vid) & (log["level"] == cfg["forecast_level"])][["itemcode", "division", "type", "target_month", "forecast_qty"]]
    return {"vintage_id": int(vid), "run_date": str(dates[0]), "fit_first": str(entry["fit_first_month"]), "fit_last": str(entry["fit_last_month"]),
            "forecast_months": [str(m) for m in months], "forecast": wide, "item_rows": item_rows}


# The bar of tabs on index.html and the four working pages, in task order (decision of the prompt of 2026-10-08): sales history, forecast, stock
# policy, stock today, production, materials; the reference tabs sit apart after a separator. `key` names the page; `fragment` is the index.html tab
# a label opens; a working page's key has a `page` file inside forecast/.
NAV_TABS = [
    {"key": "trend", "label": "ยอดขายย้อนหลัง", "fragment": "trend"},
    {"key": "sales", "label": "พยากรณ์ยอดขาย ↗", "page": "sales_report.html"},
    {"key": "inventory", "label": "แผนสต็อก ↗", "page": "inventory.html"},
    {"key": "stock", "label": "สต็อกวันนี้", "fragment": "stock"},
    {"key": "operation", "label": "แผนการผลิต ↗", "page": "operation_plan.html"},
    {"key": "material", "label": "แผนวัตถุดิบ ↗", "page": "material_plan.html"},
    {"key": "|"},
    {"key": "assumptions", "label": "สมมติฐานที่ใช้อยู่", "fragment": "assumptions"},
    {"key": "manual", "label": "คู่มือการใช้งาน", "fragment": "manual"},
    {"key": "sop", "label": "S&OP Plan (เดิม)", "fragment": "sop"},
]
NAV_CSS = """
  .page-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; margin: 6px 0 12px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
  .page-nav a { color: var(--series-1); text-decoration: none; }
  .page-nav a:hover { text-decoration: underline; }
  .page-nav b { color: var(--text-primary); }
  .page-nav .nav-sep { color: var(--muted); font-weight: 700; }
"""


def nav_bar_html(current: str) -> str:
    """The tab bar for a working page (a file in forecast/): the current page's label is bold and not a link, the other pages link to their files, the
    index.html tabs to index.html#<fragment>."""
    import html as _html
    parts = []
    for t in NAV_TABS:
        if t["key"] == "|":
            parts.append('<span class="nav-sep" aria-hidden="true">‖</span>')
            continue
        label = _html.escape(t["label"])
        if t["key"] == current:
            parts.append(f'<b data-nav="{t["key"]}">{label}</b>')
        else:
            href = t["page"] if "page" in t else f'../index.html#{t["fragment"]}'
            parts.append(f'<a data-nav="{t["key"]}" href="{href}">{label}</a>')
    return f'<nav class="page-nav" id="page-nav">{"".join(parts)}</nav>'
