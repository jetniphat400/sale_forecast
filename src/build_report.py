"""Builds forecast/sales_report.html from config.yaml['report'] text and files under
output/summary/. Every rendered number is preceded by an HTML comment naming its exact source
file and column, so a reader of the page source can trace it (CONVENTIONS.md: "every number
delivered must be verifiable against a direct recomputation").

CONVENTIONS.md's "validation failures must be raised loudly, never silently skipped" applies
here as a report-correctness rule: if a required source file or column is missing, this script
raises ReportSourceError naming exactly what is missing and refuses to render a blank,
placeholder, or remembered value in its place.

CHARTING LIBRARY (changed in the Phase E1 report rework -- see STATUS.md): this project's own
dashboard (index.html) draws hand-built inline SVG and has never depended on any third-party JS
library. This report now loads Plotly from cdnjs.cloudflare.com at a PINNED version via a plain
<script> tag (no bundling into the repo -- the page is served from GitHub Pages, where a CDN load
is acceptable) specifically so charts can be interactive (hover tooltips, legend toggles,
selector-driven re-plotting) in a way static inline SVG cannot support. This is a stated deviation
from index.html's own dependency-free approach, introduced deliberately for this one page, not
silently. The static-table/text sections (Scope, Data, Limitations, Next steps) are unchanged --
only the charted sections now use Plotly.

DATA EMBEDDING: every chart's underlying data is embedded once, as a single
<script type="application/json" id="report-data"> block built directly from output/summary/ and
config.yaml by this script (see embed_report_data()) -- the page's own JS only filters/re-plots
this embedded data client-side; it never re-derives a number. tests/test_build_report.py asserts
the embedded JSON's values equal their source files' values exactly, so the page cannot drift
from the pipeline.
"""
import html
import json
import logging
import math
import os
import sys
from datetime import datetime

import pandas as pd
import yaml

import reader_values as rv
from manual_notes import load_manual_notes, render_notes_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_report")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
FORECAST_DIR = os.path.join(PROJECT_ROOT, "forecast")
OUT_PATH = os.path.join(FORECAST_DIR, "sales_report.html")

# METRICS.md Sec.26 (page_timestamps): every page shows data_pulled_at/page_built_at in Thai
# local time, UTC+7. This machine's own clock is already ICT (confirmed this task via
# `date`/Get-Date, both returning +0700), so datetime.now() needs no timezone conversion --
# it is labelled ICT directly, never silently assumed.
ICT_LABEL = "ICT (UTC+7)"

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
BASE_MODELS = ["Naive", "MA3", "MA6", "MA12", "Croston", "SBA"]

# Pinned Plotly version -- update deliberately, never "@latest" (CONVENTIONS.md: pin library
# versions for reproducibility). Verified reachable directly (curl -> HTTP 200) and confirmed as
# cdnjs's current listed version for plotly.js (https://api.cdnjs.com/libraries/plotly.js) before
# being pinned here -- an earlier pin (2.35.2) was never checked this way and turned out to be a
# nonexistent path (HTTP 404), which silently broke every chart on the page (Plotly undefined) --
# caught only by the mandatory Part 4 browser verification, not by any earlier check.
PLOTLY_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/4.1.1/plotly.min.js"

# Same palette as index.html's :root custom properties -- copied as literal values here since
# this file is generated standalone (no shared stylesheet import mechanism exists in this
# project) and must render identically without depending on index.html being present.
COLORS = {
    "page": "#f9f9f7", "surface": "#fcfcfb", "text_primary": "#0b0b0b",
    "text_secondary": "#52514e", "muted": "#898781", "gridline": "#e1e0d9",
    "border": "rgba(11,11,11,0.10)",
    "series1": "#2a78d6", "series2": "#eb6834", "series3": "#1baf7a", "series4": "#eda100",
    "good": "#0ca30c", "critical": "#d03b3b",
}
MODEL_COLORS = {
    "Naive": "#898781", "MA3": "#eda100", "MA6": "#c98400", "MA12": "#a56c00",
    "Croston": "#eb6834", "SBA": "#c94e1f",
    "Combination": "#2a78d6", "Top-down": "#1baf7a",
}


class ReportSourceError(Exception):
    """Raised when a figure this report needs cannot be traced to a real source file/column/
    config field. Never caught anywhere -- CONVENTIONS.md requires validation failures to stop
    the build loudly, not render a blank or guessed value."""


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def require_config_path(config: dict, dotted_path: str):
    node = config
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ReportSourceError(
                f"Required config.yaml field '{dotted_path}' is missing -- cannot render the "
                f"report without it. Add it to config.yaml (see src/build_report.py's docstring)."
            )
        node = node[part]
    return node


def load_csv(rel_path: str, needed_for: str) -> pd.DataFrame:
    abs_path = os.path.join(SUMMARY_DIR, rel_path)
    if not os.path.exists(abs_path):
        raise ReportSourceError(
            f"Required source file missing: output/summary/{rel_path} (needed for {needed_for}). "
            f"Re-run the pipeline stage that produces it before building the report."
        )
    return pd.read_csv(abs_path)


def require_col(df: pd.DataFrame, col: str, source_label: str, needed_for: str):
    if col not in df.columns:
        raise ReportSourceError(
            f"Required column '{col}' is missing from {source_label} (needed for {needed_for}). "
            f"Found columns: {list(df.columns)}."
        )
    return df[col]


def cite(path: str, column: str) -> str:
    """HTML comment naming a figure's exact source, placed immediately before that figure."""
    return f"<!-- source: output/summary/{path}, column {column} -->"


def cite_config(dotted_path: str) -> str:
    return f"<!-- source: config.yaml, field {dotted_path} -->"


def fmt_num(x, decimals=1) -> str:
    return f"{x:,.{decimals}f}"


# ============================= DATA GATHERING (fail loudly if missing) =====================

def gather_scope_table() -> pd.DataFrame:
    """Per-division forecast/placeholder/excluded counts, from the final consolidated 445-item
    status file (STATUS.md, Current Status Summary, "Consolidated item status, all 445 codes")."""
    df = load_csv("phaseC_step1revised_item_status_445.csv", "Scope section (§2)")
    require_col(df, "division", "phaseC_step1revised_item_status_445.csv", "Scope section")
    require_col(df, "status_category", "phaseC_step1revised_item_status_445.csv", "Scope section")
    bucket_map = {
        "forecast": "forecast",
        "placeholder - pending method": "placeholder",
        "placeholder - method already assigned": "placeholder",
        "excluded - division excluded from forecasting (data volume)": "excluded",
        "excluded - listed but never sold, no plan-against basis": "excluded",
    }
    unmapped = set(df["status_category"].unique()) - set(bucket_map)
    if unmapped:
        raise ReportSourceError(
            f"phaseC_step1revised_item_status_445.csv has status_category value(s) this report "
            f"does not know how to bucket: {unmapped}. Update build_report.py's bucket_map."
        )
    df = df.copy()
    df["bucket"] = df["status_category"].map(bucket_map)
    table = pd.crosstab(df["division"], df["bucket"]).reindex(
        columns=["forecast", "placeholder", "excluded"], fill_value=0)
    if int(table.values.sum()) != 445:
        raise ReportSourceError(
            f"Scope table reconciliation failed: bucket totals sum to {int(table.values.sum())}, "
            f"expected 445 (the full pricelist universe)."
        )
    return table


def gather_business_findings(config: dict) -> dict:
    notice_dist = load_csv("leadtime_overall_distribution.csv", "Business findings §3, median notice")
    median_notice = require_col(notice_dist, "median", "leadtime_overall_distribution.csv",
                                 "median notice").iloc[0]

    buckets = load_csv("leadtime_notice_buckets_overall.csv", "Business findings §3, notice share >=1 month")
    require_col(buckets, "min_notice_days", "leadtime_notice_buckets_overall.csv", "notice buckets")
    require_col(buckets, "pct_of_orders", "leadtime_notice_buckets_overall.csv", "notice buckets")
    one_month_row = buckets[buckets["min_notice_days"] == 30]
    if one_month_row.empty:
        raise ReportSourceError(
            "leadtime_notice_buckets_overall.csv has no min_notice_days=30 row -- cannot report "
            "the share of orders with at least one month's notice."
        )
    pct_one_month = one_month_row["pct_of_orders"].iloc[0]

    ontime = load_csv("delivery_by_year.csv", "Business findings §3, on-time trend")
    require_col(ontime, "year", "delivery_by_year.csv", "on-time trend")
    require_col(ontime, "pct_on_time", "delivery_by_year.csv", "on-time trend")
    ontime = ontime.sort_values("year")   # every year present in the data
    if ontime.empty:
        raise ReportSourceError("delivery_by_year.csv has no rows.")

    lead_grid = require_config_path(config, "phase_e1_assumptions.procurement_lead_time_days_grid")
    lead_default = require_config_path(config, "phase_e1_assumptions.procurement_lead_time_days_default")

    return {
        "median_notice": median_notice,
        "pct_one_month": pct_one_month,
        "buckets": buckets,
        "ontime_by_year": ontime,
        "lead_grid": lead_grid,
        "lead_default": lead_default,
    }


def gather_model_chart() -> pd.DataFrame:
    """Six base models plus Combination AND Top-down (the legend-toggle chart needs Top-down
    present, not just Combination -- Part 2's control spec: 'toggle base models against
    combination and Top-down')."""
    df = load_csv("focus_items_test_all.csv", "Model section §5 chart")
    require_col(df, "model", "focus_items_test_all.csv", "model chart")
    require_col(df, "MAE", "focus_items_test_all.csv", "model chart")
    require_col(df, "itemcode", "focus_items_test_all.csv", "model chart")
    wanted_models = BASE_MODELS + ["Combination", "Top-down"]
    sub = df[df["model"].isin(wanted_models) & df["itemcode"].isin(FOCUS_ITEMS)]
    missing = set(wanted_models) - set(sub["model"].unique())
    if missing:
        raise ReportSourceError(
            f"focus_items_test_all.csv is missing model(s) {missing} for the model-comparison chart."
        )
    return sub


# The two comparisons of the significance block, in the order shown, with the approved line openings.
SIGNIFICANCE_LINES = {
    "Direct": "เทียบกับการทายรายรหัสตรงๆ:",
    "Naive": "เทียบกับการใช้ยอดเดือนล่าสุดเป็นค่าทาย:",
}
SIGNIFICANCE_HEADING = "ใช้วิธี Top-down ดีกว่าวิธีอื่นไหม"
SIGNIFICANCE_CLOSING = "ที่เลือกใช้ Top-down เพราะแม่นใกล้เคียงหรือดีกว่าวิธีอื่น และใช้วิธีเดียวได้ทุกฝ่าย"
NL_INDENT = "\n      "
SMALL_DIFFERENCE_PCT = 5      # below this absolute relative difference the phrase "แม้จะเล็ก" is added (approved wording rule)


def significance_pct_text(rel_diff_pct: float) -> str:
    """Absolute relative difference: a whole number, or one decimal when below 10."""
    a = abs(float(rel_diff_pct))
    text = f"{a:.1f}"
    return text if a < 10 and float(text) < 10 else f"{a:.0f}"


def significance_line(rows: pd.DataFrame, other: str) -> str:
    """One line of the block for one comparison: better phrases (one per division), then worse phrases, then one phrase for
    all unclear divisions, joined by ' · '. Rows are that comparison's per-division results (verdict, rel_diff_pct)."""
    phrases = []
    for verdict, word in (("better", "น้อยกว่า"), ("worse", "มากกว่า")):
        for _, r in rows[rows["verdict"] == verdict].iterrows():
            small = " แม้จะเล็ก" if abs(float(r["rel_diff_pct"])) < SMALL_DIFFERENCE_PCT else ""
            phrases.append(f"{r['division']} ทายพลาด{word}ประมาณ {significance_pct_text(r['rel_diff_pct'])}% ทดสอบแล้วความต่างนี้เกิดจริง{small}")
    unclear = list(rows[rows["verdict"] == "unclear"]["division"])
    if unclear:
        phrases.append(", ".join(unclear) + " ใกล้เคียงกันจนบอกไม่ได้ว่าวิธีไหนดีกว่า")
    return SIGNIFICANCE_LINES[other] + " " + " · ".join(phrases)


def significance_block_html(sig: pd.DataFrame) -> str:
    """The sales report's block 'does Top-down beat the others' from topdown_significance.csv (src/significance_topdown.py)."""
    lines = []
    for other in SIGNIFICANCE_LINES:
        rows = sig[sig["other_method"] == other]
        if len(rows):
            lines.append(f"<p>{html.escape(significance_line(rows, other))}</p>")
    first, last = sig["first_test_month"].min(), sig["last_test_month"].max()
    rule = (f"source: output/summary/topdown_significance.csv, written every monthly run by src/significance_topdown.py (METRICS.md Sec.41); "
            f"item-level pairs on the backtest of {first} to {last} ({int(sig['n_origins'].max())} origins), difference = Top-down minus the other "
            f"method; verdict better/worse only when |t| >= {sig['t_threshold'].iloc[0]:g}, Wilcoxon p < {sig['wilcoxon_p_threshold'].iloc[0]:g} and the "
            f"signs of t and of the median difference agree, otherwise unclear")
    joined = NL_INDENT.join(lines)
    return (f"<h3>{html.escape(SIGNIFICANCE_HEADING)}</h3>{NL_INDENT}<!-- {html.escape(rule, quote=False)} -->{NL_INDENT}{joined}"
            f"{NL_INDENT}<p>{html.escape(SIGNIFICANCE_CLOSING)}</p>")


def gather_results(config: dict) -> dict:
    per_division = load_csv("phaseC_step2_per_division_summary_qty.csv", "Results §6 table")
    for col in ["division", "MAE", "RMSE", "Bias", "MASE", "n_items", "n_origins",
                "rolling_origin_first_test_month", "rolling_origin_last_test_month"]:
        require_col(per_division, col, "phaseC_step2_per_division_summary_qty.csv", "Results table")

    rolling = load_csv("phaseC_step2_rolling_origin_qty.csv", "Results §6 rolling-origin chart")
    for col in ["level", "division", "name", "model", "origin", "MAE"]:
        require_col(rolling, col, "phaseC_step2_rolling_origin_qty.csv", "rolling-origin chart")
    rolling_type = rolling[rolling["level"] == "Type"].copy()
    if rolling_type.empty:
        raise ReportSourceError(
            "phaseC_step2_rolling_origin_qty.csv has no Type-level rows for the rolling-origin chart."
        )

    # Top-down against Direct and against Naive, per division: computed every monthly run by src/significance_topdown.py
    # (METRICS.md Sec.41) on the current backtest rows; the report's "does Top-down beat the others" block reads it.
    sig = load_csv("topdown_significance.csv", "Results Sec.6 significance block")
    for col in ["division", "other_method", "rel_diff_pct", "verdict", "t_stat", "wilcoxon_p"]:
        require_col(sig, col, "topdown_significance.csv", "significance block")
    if set(sig["other_method"]) != set(SIGNIFICANCE_LINES):
        raise ReportSourceError("topdown_significance.csv must hold the comparisons " + ", ".join(SIGNIFICANCE_LINES) + ".")

    return {
        "per_division": per_division,
        "rolling_type": rolling_type,
        "topdown_sig": sig,
    }


def gather_forecast_vs_actual() -> pd.DataFrame:
    """Standard 7-origin, 6-month-holdout Top-down forecast vs. actual, per item per origin per
    month-in-horizon -- src/build_report_data.py's output (see that script's docstring for why
    this replaced the old 9-origin, actual-only phaseE1_2_rolling_origin_cumulative.csv chart)."""
    path = os.path.join(SUMMARY_DIR, "report_item_forecast_vs_actual_by_origin.csv")
    if not os.path.exists(path):
        raise ReportSourceError(
            "Required source file missing: output/summary/report_item_forecast_vs_actual_by_origin.csv "
            "(needed for the Results §6 forecast-vs-actual chart). Run "
            "`python src/build_report_data.py` first."
        )
    df = pd.read_csv(path)
    for col in ["itemcode", "category", "type", "origin", "month_in_horizon", "actual_qty", "forecast_qty"]:
        require_col(df, col, "report_item_forecast_vs_actual_by_origin.csv", "forecast-vs-actual chart")
    missing_focus = set(FOCUS_ITEMS) - set(df["itemcode"].unique())
    if missing_focus:
        raise ReportSourceError(
            f"report_item_forecast_vs_actual_by_origin.csv is missing focus item(s) {missing_focus}."
        )
    return df


def _source_pull_date(rel_path: str, column: str = "snapshot_pull_date") -> str:
    """The recorded pull time for a source file, read from its own `column` -- METRICS.md
    Sec.26's 'source table's load timestamp' proxy. FIXED (task 2cfix2, Part 3): this used to be
    a file MODIFICATION TIME (os.path.getmtime), which reflects when the file was last WRITTEN TO
    DISK on this machine, not when the underlying data was actually queried from the database --
    task 2cfix's own Validator found a real case where these diverge (a dry run's staged-vs-
    tracked timing gap, STATUS.md Sec.12). All 6 files this function is called on now carry their
    own snapshot_pull_date column, written by their generating script at the moment of its DB
    pull (or, for files derived from output/data/processed_all_divisions_monthly_qty.csv, copied
    forward from THAT file's own snapshot_pull_date) -- never a file mtime proxy, for any of
    them, any more. This machine's clock is ICT (confirmed via `date`, task 2a)."""
    abs_path = os.path.join(SUMMARY_DIR, rel_path)
    if not os.path.exists(abs_path):
        raise ReportSourceError(f"Cannot compute freshness: {abs_path} does not exist.")
    df = pd.read_csv(abs_path, usecols=lambda c: c == column)
    if column not in df.columns or df.empty:
        raise ReportSourceError(
            f"{abs_path} has no '{column}' column -- cannot compute freshness from a recorded "
            f"pull time. Re-run the script that generates this file (it must now write this "
            f"column -- task 2cfix2, Part 3)."
        )
    value = str(df[column].iloc[0])
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M")


def gather_forward_forecast(vf: dict, scope_table: pd.DataFrame) -> dict:
    """The forward forecast table's data: the latest vintage's Item rows of the forward-test log (read after the hash check, `rv.vintage_facts`), the very rows G2
    (src/build_inventory_page_data.py latest_vintage_item_forecasts) and G3 (src/operation_plan.py latest_vintage_forecast) read. Per division in the operation
    plan's order: Types (descending by their total over the months) with their items. Product names come from the price list. A Type's month value is the sum of
    its items' values; no division total is made. `n_without_forecast` = placeholder + excluded codes of the scope table."""
    import operation_plan as op
    from pricelist_reader import load_visible_product_rows
    rows = vf["item_rows"].copy()
    months = vf["forecast_months"]
    wide = rows.pivot_table(index=["division", "type", "itemcode"], columns="target_month", values="forecast_qty", aggfunc="sum").reindex(columns=months)
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")).drop_duplicates("code")
    names = {c: " ".join(str(n).split()) if pd.notna(n) else "" for c, n in zip(pl["code"], pl["description"])}
    order = [d for d in op.load_config(PROJECT_ROOT)["divisions"] if d in set(wide.index.get_level_values(0))]
    divisions = {}
    for d in order:
        w = wide.loc[d]
        types = []
        for t, g in w.groupby(level=0):
            g = g.droplevel(0)
            g = g.loc[g.sum(axis=1).sort_values(ascending=False, kind="mergesort").index]
            types.append({"type": t, "values": [float(x) for x in g.sum(axis=0)], "items": [{"item": c, "name": names.get(c, ""), "values": [float(x) for x in g.loc[c]]} for c in g.index]})
        types.sort(key=lambda r: (-sum(r["values"]), r["type"]))
        divisions[d] = types
    n_without = int(scope_table["placeholder"].sum() + scope_table["excluded"].sum())
    return {"months": months, "divisions": divisions, "n_without_forecast": n_without}


def _baht(units: float, price: float) -> int:
    """Whole baht of `units` at `price`: rounded half up at item and month level, so every total of the baht view is a sum of whole numbers and adds up exactly."""
    return int(math.floor(float(units) * float(price) + 0.5))


def gather_baht(forward: dict, price_info: dict) -> dict:
    """The baht view of the forward forecast table: per item and month `round(units x unit price)` (unit price by config report.price_basis, see
    reader_values.unit_prices), a Type's value the sum of its items', a division's the sum of its Types', 'all' the sum of the divisions'. An item with no price has
    values None, is left out of every sum, and is listed in `no_price` (code, name, division). `market_items` = items priced at Market Price;
    `market_first_month_baht` = the first forecast month's baht that comes from them."""
    prices = price_info["prices"]
    n = len(forward["months"])
    divisions, no_price, market_items, market_first = {}, [], [], 0
    grand = [0] * n
    for d, types in forward["divisions"].items():
        d_tot, d_types = [0] * n, []
        for t in types:
            t_tot, t_items = [0] * n, []
            for it in t["items"]:
                pr = prices[it["item"]]
                if pr["price"] is None:
                    no_price.append({"item": it["item"], "name": it["name"], "division": d})
                    t_items.append({"item": it["item"], "name": it["name"], "values": None})
                    continue
                vals = [_baht(v, pr["price"]) for v in it["values"]]
                if pr["source"] == "market_price":
                    market_items.append(it["item"])
                    market_first += vals[0]
                t_items.append({"item": it["item"], "name": it["name"], "values": vals})
                t_tot = [a + b for a, b in zip(t_tot, vals)]
            d_tot = [a + b for a, b in zip(d_tot, t_tot)]
            d_types.append({"type": t["type"], "values": t_tot, "items": t_items})
        divisions[d] = {"types": d_types, "total": d_tot}
        grand = [a + b for a, b in zip(grand, d_tot)]
    return {"divisions": divisions, "all": grand, "no_price": no_price, "market_items": market_items, "market_first_month_baht": market_first}


def attach_scored_baht(scored: pd.DataFrame, prices: dict) -> pd.DataFrame:
    """Adds `baht_forecast`, `baht_actual`, `baht_diff` (forecast minus actual, the sign of the page's Bias) and `n_no_price` to the scored months table.

    For each scored row (vintage, division, month, horizon 1) the items are those the score itself used: the Item rows of the forward-test log of that vintage and
    month whose fit series (the vintage's fit window, from the raw history) is not all zero (forward_test_scoring.score_items). Each item's forecast and actual units
    are valued at the item's unit price of the page (`prices`, {code: {'price', 'source'}}); an item without a price is left out and counted in `n_no_price`.
    The mean of (forecast - actual) units over the same items is checked against the recorded Bias of the row; a difference stops the build."""
    import forward_test_common as ftc
    import forward_test_scoring as fts
    import operation_plan as op
    cfg = op.load_config(PROJECT_ROOT)
    log = ftc.read_forward_test_log(op.path_of(PROJECT_ROOT, cfg["forecast_log_file"]))
    meta = ftc.load_metadata(op.path_of(PROJECT_ROOT, cfg["forecast_log_metadata_file"]))
    raw = pd.read_csv(fts.RAW_HISTORY_PATH, usecols=["itemcode", "createDate", "forecast_date", "qty"])
    items = log[log["level"] == "Item"].copy()
    items["actual_num"] = pd.to_numeric(items["actual_qty"], errors="coerce")
    rows = []
    for r in scored.itertuples():
        g = items[(items["vintage_id"] == r.vintage_id) & (items["target_month"] == r.target_month) & (items["horizon"] == 1) & (items["division"] == r.division)]
        vm = meta[str(int(r.vintage_id))]
        series = fts.fit_series_from_raw(raw, g["itemcode"].unique(), vm["fit_first_month"], vm["fit_last_month"])
        used = fts.score_items(g.assign(actual_qty=g["actual_num"]), series)["itemcode"]
        g = g[g["itemcode"].isin(set(used))]
        bias = float((g["forecast_qty"] - g["actual_num"]).mean())
        if abs(bias - float(r.Bias)) > 1e-6:
            raise ReportSourceError(f"{r.division} {r.target_month}: mean(forecast - actual) of the scored items is {bias}, the recorded Bias is {r.Bias}; the baht difference cannot take the sign of Bias.")
        f_b = a_b = n_no = 0
        for c, f, a in zip(g["itemcode"], g["forecast_qty"], g["actual_num"]):
            pr = prices[c]["price"] if c in prices else None
            if pr is None:
                n_no += 1
                continue
            f_b += _baht(f, pr)
            a_b += _baht(a, pr)
        rows.append({"baht_forecast": f_b, "baht_actual": a_b, "baht_diff": f_b - a_b, "n_no_price": n_no})
    return pd.concat([scored.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def fmt_ratio(x, digits: int) -> str:
    """A ratio or signal for a table cell with `digits` decimals; '-' when it is undefined (None or NaN)."""
    return "-" if x is None or pd.isna(x) else f"{x:.{digits}f}"


def verdict_relative(value, good: float, passing: float) -> str:
    """ดี below the good threshold, ผ่าน below the pass threshold, otherwise ไม่ผ่าน (draft criteria, METRICS.md Sec.48); '-' when the ratio is undefined."""
    if value is None:
        return "-"
    return "ดี" if value < good else ("ผ่าน" if value < passing else "ไม่ผ่าน")


def verdict_tracking(value, limit: float) -> str:
    """เตือน when |Tracking Signal| is above the limit, otherwise ปกติ; '-' when undefined."""
    if value is None:
        return "-"
    return "เตือน" if abs(value) > limit else "ปกติ"


def gather_accuracy_vs_naive(config: dict, primary_results: pd.DataFrame) -> dict:
    """Relative MAE against Naive (all horizons and Horizon 3), Tracking Signal and the draft verdicts, per forecast division and per pilot group (METRICS.md Sec.48), and Naive on
    the scored forward months. Backtest cells are recomputed from the saved monthly series with the functions of the main table (src/transferability_all_divisions.py); the model
    MAE of a division recomputed from its cells must equal the main table's MAE (and the cell count its n_scored), otherwise the build stops.
    Returns {"rows": [...], "forward_by_division": DataFrame, "items_beyond_limit": {division: share}, "thresholds": {...}}."""
    import forward_test_common as ftc
    import forward_test_scoring as fts
    import operation_plan as op
    import transferability_all_divisions as ta
    from leakage_guard import load_min_margin_days
    crit = config["maxmin_v1"]["pending_criteria_values"]
    good, passing, limit = float(crit["relative_mae_good"]), float(crit["relative_mae_pass"]), float(crit["tracking_signal_limit"])
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    margin = load_min_margin_days(config)
    item_series, type_series = ta.build_item_and_type_series(monthly, scope)
    cells = ta.topdown_naive_cells(item_series, type_series, pull_date, margin)
    # forward months: Naive on the scored Item rows
    ocfg = op.load_config(PROJECT_ROOT)
    log = ftc.read_forward_test_log(op.path_of(PROJECT_ROOT, ocfg["forecast_log_file"]))
    meta = ftc.load_metadata(op.path_of(PROJECT_ROOT, ocfg["forecast_log_metadata_file"]))
    raw = pd.read_csv(fts.RAW_HISTORY_PATH, usecols=["itemcode", "createDate", "forecast_date", "qty"])
    fitems = fts.forward_naive_items(log, meta, raw)
    fdiv = fts.forward_naive_by_division(fitems)
    order = [d for d in op.load_config(PROJECT_ROOT)["divisions"] if d in set(primary_results["division"])]
    main = primary_results.set_index("division")
    rows, beyond = [], {}
    for d in order:
        cs = [c for c in cells if c["division"] == d]
        r_all, r_h3 = ta.relative_mae(cs), ta.relative_mae(cs, 3)
        if len(cs) != int(main.loc[d, "n_scored"]) or abs(r_all["mae"] - float(main.loc[d, "MAE"])) > 1e-9:
            raise ReportSourceError(f"{d}: the model MAE of the {len(cs)} recomputed cells ({r_all['mae']}) differs from the main table's MAE ({main.loc[d, 'MAE']}, n_scored {main.loc[d, 'n_scored']}).")
        e = list(ta.horizon1_errors_by_origin(cs).values()) + [float(x) for x in fdiv[fdiv["division"] == d].sort_values(["target_month", "vintage_id"])["e_total"]]
        ts = ta.tracking_signal(e)
        rows.append({"label": d, "kind": "division", "relative_mae": r_all["relative_mae"], "relative_mae_h3": r_h3["relative_mae"], "tracking_signal": ts["tracking_signal"],
                     "n_points": ts["n_points"], "mae": r_all["mae"], "mae_naive": r_all["mae_naive"], "n_cells": r_all["n_cells"]})
        # report only: the share of the division's items whose own horizon-1 Tracking Signal is beyond the limit
        item_e = {}
        for c in sorted(cs, key=lambda c: c["origin"]):
            item_e.setdefault(c["itemcode"], []).append(float(c["fc"][0] - c["act"][0]))
        for r in fitems[fitems["division"] == d].sort_values(["target_month", "vintage_id"]).itertuples():
            item_e.setdefault(r.itemcode, []).append(r.e_model)
        sigs = [ta.tracking_signal(v)["tracking_signal"] for v in item_e.values()]
        sigs = [x for x in sigs if x is not None]
        beyond[d] = {"n_items": len(sigs), "n_beyond": sum(1 for x in sigs if abs(x) > limit), "share": (sum(1 for x in sigs if abs(x) > limit) / len(sigs)) if sigs else None}
    # pilot groups: the Type series (sum of the group's items), the Type's Combination forecast, as the pilot-group block
    for key, label in config["report"]["pilot_labels"].items():
        type_name = config["pilot_categories"][key]
        sub = scope[scope["type"] == type_name]
        if sub["division"].nunique() != 1:
            raise ReportSourceError(f"pilot group {key}: its Type {type_name!r} is on {sub['division'].nunique()} divisions in the scope, expected 1")
        div = sub["division"].iloc[0]
        qty, months = type_series[f"{div}::{type_name}"]
        gc = ta.group_cells(qty, months, pull_date, margin)
        r_all, r_h3 = ta.relative_mae(gc), ta.relative_mae(gc, 3)
        fg = fitems[(fitems["division"] == div) & (fitems["type"].str.strip() == type_name)]
        e = list(ta.horizon1_errors_by_origin(gc).values()) + [float(x) for x in fg.groupby(["target_month", "vintage_id"])["e_model"].sum().sort_index()]
        ts = ta.tracking_signal(e)
        rows.append({"label": label, "kind": "group", "relative_mae": r_all["relative_mae"], "relative_mae_h3": r_h3["relative_mae"], "tracking_signal": ts["tracking_signal"],
                     "n_points": ts["n_points"], "mae": r_all["mae"], "mae_naive": r_all["mae_naive"], "n_cells": r_all["n_cells"]})
    for r in rows:
        r["verdict_relative"] = verdict_relative(r["relative_mae"], good, passing)
        r["verdict_relative_h3"] = verdict_relative(r["relative_mae_h3"], good, passing)
        r["verdict_tracking"] = verdict_tracking(r["tracking_signal"], limit)
    return {"rows": rows, "forward_by_division": fdiv, "forward_items": fitems, "items_beyond_limit": beyond, "thresholds": {"good": good, "pass": passing, "limit": limit}}


def items_not_flat(forward: dict) -> list:
    """Items whose forecast differs between the forecast months of the vintage (exact comparison); empty when every item has one value for all months."""
    return sorted(it["item"] for ts in forward["divisions"].values() for t in ts for it in t["items"] if len(set(it["values"])) > 1)


def shadow_line_text(config: dict, scores_path: str = None) -> str:
    """The one line of the pilot-group block about the Surge Arrester shadow forecast (METRICS.md Sec.51): method, status, and per scored month the MAE of the shadow method against the current
    method's; while nothing is scored, the date of the first run that can give a result. Every number and date comes from the score record and the guard at build time (forward_test_scoring.shadow_rule_status)."""
    import forward_test_scoring as fts
    report = config["report"]
    status = fts.shadow_rule_status(config, scores_path) if scores_path else fts.shadow_rule_status(config)
    parts = []
    for g in status.values():
        scored = [m for m in g["months"] if m["scored"]]
        unscored = [m for m in g["months"] if not m["scored"]]
        if g["state"] == "evaluated":
            state = report["shadow_status_" + g["outcome"]].format(method=g["method"])
        elif scored:
            state = report["shadow_status_partial"].format(n=len(scored), total=g["n_months"])
        else:
            state = report["shadow_status_pending"].format(first_run=rv.thai_date_short(min(m["scoreable_run"] for m in unscored)))
        pieces = [report["shadow_head"].format(group=g["label"], method=g["method"]), state]
        pieces += [report["shadow_month"].format(month=rv.thai_month_short(m["month"]), method=g["method"], h=f"{m['holt_mae']:.1f}", c=f"{m['current_mae']:.1f}") for m in scored]
        if scored and unscored:
            pieces.append(report["shadow_next"].format(month=rv.thai_month_short(unscored[0]["month"]), run=rv.thai_date_short(unscored[0]["scoreable_run"])))
        pieces.append(report["shadow_not_in_plan"])
        parts.append(" · ".join(pieces))
    return " ".join(parts)


def gather_pilot_groups(config: dict) -> list:
    """MAE and Bias of the two pilot groups, recomputed here from the saved series by the pilot-category view builder (src/focus_item_model_selection.py
    build_pilot_view_payload; groups defined by config pilot_categories, the Surge Arrester group being the Medium Voltage Type). The group is scored as the
    Type's own Combination forecast over the project's rolling-origin backtest (`series_own`): errors are forecast minus actual (src/backtest_rekeyed.py
    compute_metrics), so a negative Bias is a forecast below the actual. Returns [{key, label, MAE, Bias}] in the order of the config."""
    import focus_item_model_selection as fims
    report = require_config_path(config, "report")
    payload_keys = {"fuse_cutout": "Drop-out Fuse Cutout", "surge_arrester": "Surge Arrester"}
    units = fims.build_pilot_view_payload()["units"]
    out = []
    for key, label in report["pilot_labels"].items():
        own = units[payload_keys[key]]["series_own"]
        out.append({"key": key, "label": label, "MAE": float(own["MAE"]), "Bias": float(own["Bias"])})
    return out


def gather_scored_months(primary_results: pd.DataFrame) -> pd.DataFrame:
    """Forecast against actual per division and month at horizon 1, from the recorded forward-test scores (output/summary/forward_test_scores.csv, scored by
    src/forward_test_scoring.py after its integrity check; scope 'division'), with the backtest MAE of the same division (the main table's Top-down MAE).
    Stops when no scored month is recorded."""
    import forward_test_scoring as fts
    fts.verify_score_record()
    s = pd.read_csv(fts.SCORES_PATH)
    s = s[(s["scope"] == "division") & (s["horizon"] == 1)]
    if s.empty:
        raise ReportSourceError("output/summary/forward_test_scores.csv holds no scored division row at horizon 1: the forecast-versus-actual table cannot be built.")
    back = primary_results.set_index("division")["MAE"]
    missing = sorted(set(s["key"]) - set(back.index))
    if missing:
        raise ReportSourceError(f"no backtest MAE for division(s) {missing} in the main results table")
    out = s[["key", "vintage_id", "target_month", "MAE", "Bias"]].rename(columns={"key": "division"}).copy()
    out["MAE_backtest"] = out["division"].map(back)
    return out.sort_values(["target_month", "division"], kind="mergesort").reset_index(drop=True)


def gather_freshness() -> dict:
    """data_pulled_at per section, cited to the exact file/column it comes from (never typed),
    per METRICS.md Sec.26. Multiple source files feed this one page at different ages -- the
    headline `data_pulled_at` is the OLDEST of them (a page is only as fresh as its stalest
    input), with every section's own date reported alongside so nothing is hidden."""
    monthly_path = os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")
    monthly = pd.read_csv(monthly_path, usecols=["snapshot_pull_date"])
    main_pull = str(monthly["snapshot_pull_date"].iloc[0])

    # Reader-facing label -> pull time; each label's source note stays off screen, in an HTML comment.
    sections = {
        "ช่วงข้อมูลหลัก": main_pull,
        "ผลทดสอบต่อฝ่าย": _source_pull_date("phaseC_step2_per_division_summary_qty.csv"),
        "กราฟ Rolling-origin": _source_pull_date("phaseC_step2_rolling_origin_qty.csv"),
        "กราฟระยะเวลาแจ้งล่วงหน้า": _source_pull_date("leadtime_notice_buckets_overall.csv"),
        "กราฟ MAE โมเดลพื้นฐาน": _source_pull_date("focus_items_test_all.csv"),
        "กราฟส่งตรงวันพอดี": _source_pull_date("delivery_by_year.csv"),
        "กราฟส่งไม่ช้า": _source_pull_date("delivery_not_late_by_year.csv"),
    }
    section_sources = {
        "ช่วงข้อมูลหลัก": "output/data/processed_full_category_sales_monthly_forecastDate.csv (forecast/actual, scope, usable range), column snapshot_pull_date",
        "ผลทดสอบต่อฝ่าย": "phaseC_step2_transferability_per_division.csv / phaseC_step2_per_division_summary_qty.csv, column snapshot_pull_date",
        "กราฟ Rolling-origin": "phaseC_step2_rolling_origin_qty.csv, column snapshot_pull_date",
        "กราฟระยะเวลาแจ้งล่วงหน้า": "leadtime_notice_buckets_overall.csv, column snapshot_pull_date",
        "กราฟ MAE โมเดลพื้นฐาน": "focus_items_test_all.csv, column snapshot_pull_date",
        "กราฟส่งตรงวันพอดี": "delivery_by_year.csv, column snapshot_pull_date",
        "กราฟส่งไม่ช้า": "delivery_not_late_by_year.csv, column snapshot_pull_date, itself read forward from the same Cube_CES pull as the on-time chart (no new DB call)",
    }
    data_pulled_at_min = min(sections.values())
    return {"sections": sections, "section_sources": section_sources, "data_pulled_at_min": data_pulled_at_min}


def gather_primary_results() -> pd.DataFrame:
    """Per-division Top-down rolling-origin figures (MAE/RMSE/Bias/MASE/n_scored) -- item-level,
    the Top-down method this project actually adopted (STATUS.md Locked Decisions, "Final
    forecasting method"), NOT the Type-level/Combination-only secondary table below. Source:
    src/transferability_all_divisions.py (item-level rolling-origin scoring at every one of the
    project's standard 7 origins), aggregated into
    output/summary/phaseC_step2_transferability_per_division.csv, documented in
    docs/reports/summary/phaseC_step2_report.md Part 3 (confirmed this task by reading both the
    generator script and that report)."""
    df = load_csv("phaseC_step2_transferability_per_division.csv", "Results §6 PRIMARY table (Top-down)")
    for col in ["division", "approach", "MAE", "RMSE", "Bias", "MASE", "n_scored",
                "first_test_month", "last_test_month"]:
        require_col(df, col, "phaseC_step2_transferability_per_division.csv", "primary results table")
    topdown = df[df["approach"] == "Top-down"].copy()
    if topdown.empty:
        raise ReportSourceError(
            "phaseC_step2_transferability_per_division.csv has no approach=='Top-down' rows."
        )
    return topdown


def gather_backtest_window(primary_results: pd.DataFrame, per_division: pd.DataFrame) -> dict:
    """METRICS.md Sec.39: 'every reported figure states the window's first and last test months'.
    Both the item-level PRIMARY table (transferability_all_divisions.py) and the Type-level
    SECONDARY table (backtest_all_divisions.py) run the SAME get_origins(TOTAL_MONTHS, HOLDOUT)
    scheme over the same calendar grid, so every division/approach row is expected to state the
    identical span -- checked here, not assumed, since a real per-division difference would be a
    genuine bug (e.g. an item/division with a shorter series)."""
    first_months = set(primary_results["first_test_month"].unique()) | set(per_division["rolling_origin_first_test_month"].unique())
    last_months = set(primary_results["last_test_month"].unique()) | set(per_division["rolling_origin_last_test_month"].unique())
    if len(first_months) != 1 or len(last_months) != 1:
        raise ReportSourceError(
            f"Backtest window is not uniform across divisions/tables (first_test_month values: "
            f"{first_months}, last_test_month values: {last_months}) -- cannot state a single "
            f"window statement per METRICS.md Sec.39 without investigating this discrepancy first."
        )
    n_origins = int(per_division["n_origins"].iloc[0]) if "n_origins" in per_division.columns else None
    return {"first_test_month": first_months.pop(), "last_test_month": last_months.pop(), "n_origins": n_origins}


def gather_notlate() -> pd.DataFrame:
    """not_late (delivered on or before ForecastDelDate, METRICS.md Sec.19), unit-weighted
    (weighted by ActualQty -- METRICS.md Sec.10 fill_rate is explicitly unit-based, "not
    order-based", and this figure is meant to be read alongside fill_rate elsewhere in this
    project). Source: src/investigations/task2a_delivery_notlate_by_year.py, which reuses the
    SAME already-pulled Cube_CES raw data as the existing on_time_exact chart (no new DB pull)."""
    df = load_csv("delivery_not_late_by_year.csv", "Business findings §3, not_late trend")
    for col in ["year", "not_late_pct_unit_weighted", "not_late_pct_row_weighted"]:
        require_col(df, col, "delivery_not_late_by_year.csv", "not_late trend")
    return df.sort_values("year")   # every year present in the data


# ============================= EMBEDDED JSON DATA (client-side charts read only this) ========

def embed_report_data(scope_table, biz, model_chart, results, fva, primary_results, notlate, backtest_window) -> dict:
    """Everything the page's client-side JS needs to draw/filter every Plotly chart, built
    directly from the same dataframes the server-rendered text/tables use above -- so the
    embedded JSON and the rendered text are always the same numbers, never two independent
    reads of the same file. tests/test_build_report.py checks this dict's values against the
    source files directly, not just against this function's own output."""
    notice = {
        "labels": [f">= {int(d)}d" for d in biz["buckets"]["min_notice_days"]],
        "values": [float(v) for v in biz["buckets"]["pct_of_orders"]],
    }
    ontime = {
        "years": [int(y) for y in biz["ontime_by_year"]["year"]],
        "values": [float(v) for v in biz["ontime_by_year"]["pct_on_time"]],
    }
    model_bar = {}
    for model in BASE_MODELS + ["Combination", "Top-down"]:
        sub = model_chart[model_chart["model"] == model]
        model_bar[model] = {row["itemcode"]: float(row["MAE"]) for _, row in sub.iterrows()}

    rolling = results["rolling_type"]
    rolling_records = rolling[["division", "name", "model", "origin", "MAE"]].rename(
        columns={"name": "type"}).to_dict(orient="records")
    rolling_records = [{"division": r["division"], "type": r["type"], "model": r["model"],
                         "origin": int(r["origin"]), "MAE": float(r["MAE"])} for r in rolling_records]

    per_division_records = results["per_division"][["division", "MAE", "RMSE", "Bias", "MASE", "n_items"]].to_dict(orient="records")
    per_division_records = [{"division": r["division"], "MAE": float(r["MAE"]), "RMSE": float(r["RMSE"]),
                              "MASE": (None if pd.isna(r["MASE"]) else float(r["MASE"])),
                              "Bias": float(r["Bias"]), "n_items": int(r["n_items"])} for r in per_division_records]

    fva_records = fva.to_dict(orient="records")
    fva_records = [{"itemcode": r["itemcode"], "category": r["category"], "type": r["type"],
                     "origin": int(r["origin"]), "month_in_horizon": int(r["month_in_horizon"]),
                     "actual_qty": float(r["actual_qty"]),
                     "forecast_qty": (float(r["forecast_qty"]) if pd.notna(r["forecast_qty"]) else None)}
                    for r in fva_records]

    scope_records = {div: {"forecast": int(row["forecast"]), "placeholder": int(row["placeholder"]),
                            "excluded": int(row["excluded"])} for div, row in scope_table.iterrows()}

    def _mase_or_undefined(v):
        return None if pd.isna(v) else float(v)

    primary_records = [
        {"division": r["division"], "MAE": float(r["MAE"]), "RMSE": float(r["RMSE"]),
         "Bias": float(r["Bias"]), "MASE": _mase_or_undefined(r["MASE"]), "n_scored": int(r["n_scored"])}
        for _, r in primary_results.iterrows()
    ]

    notlate_records = {
        "years": [int(y) for y in notlate["year"]],
        "values": [float(v) for v in notlate["not_late_pct_unit_weighted"]],
    }

    return {
        "focus_items": FOCUS_ITEMS,
        "base_models": BASE_MODELS,
        "scope_table": scope_records,
        "notice": notice,
        "ontime": ontime,
        "notlate": notlate_records,
        "model_bar": model_bar,
        "rolling_origin": rolling_records,
        "per_division": per_division_records,
        "primary_results": primary_records,
        "backtest_window": backtest_window,
        "forecast_vs_actual": fva_records,
    }


# ============================= SECTION RENDERERS =============================================

def render_page(config: dict) -> str:
    report = require_config_path(config, "report")
    scope_table = gather_scope_table()
    biz = gather_business_findings(config)
    model_chart = gather_model_chart()
    results = gather_results(config)
    fva = gather_forecast_vs_actual()
    primary_results = gather_primary_results()
    notlate = gather_notlate()
    vf = rv.vintage_facts(PROJECT_ROOT)
    freshness = gather_freshness()
    backtest_window = gather_backtest_window(primary_results, results["per_division"])

    # Staleness threshold (METRICS.md Sec.26): read from config.yaml page_timestamps at build time.
    STALENESS_THRESHOLD_DAYS = rv.staleness_threshold_days(config)
    page_built_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    built_dt = datetime.strptime(page_built_at, "%Y-%m-%d %H:%M")
    data_pulled_at = freshness["data_pulled_at_min"]

    # METRICS.md Sec.26 (amended 2026-09-25, per-section staleness): "the staleness notice is
    # evaluated per section, not from the single oldest input on the page, so one stale section
    # never marks a whole page stale." Each section's own age against page_built_at is checked
    # independently -- no single global is_stale flag any more.
    section_ages = {label: (built_dt - datetime.strptime(pulled_at[:16], "%Y-%m-%d %H:%M")).days
                     for label, pulled_at in freshness["sections"].items()}
    stale_sections = [label for label, age in section_ages.items() if age > STALENESS_THRESHOLD_DAYS]

    freshness_rows = "".join(
        f"<tr><td><!-- source: {freshness['section_sources'][label]} -->{html.escape(label)}</td><td>{value}</td>"
        f"<td>{f'เก่ากว่า {STALENESS_THRESHOLD_DAYS} วัน' if label in stale_sections else 'ใหม่'}</td></tr>"
        for label, value in freshness["sections"].items()
    )
    staleness_html = (
        f"""<p class="note-box"><b>⚠ บางส่วนของหน้านี้ใช้ข้อมูลเก่ากว่า {STALENESS_THRESHOLD_DAYS} วัน (ประเมินแยกทีละส่วน):</b>
        {"; ".join(html.escape(s) for s in stale_sections)} — ส่วนอื่นของหน้านี้ที่ไม่อยู่ในรายการนี้
        ยังคงใช้ข้อมูลที่ทันสมัย (ไม่ถือว่าทั้งหน้าเก่าเพียงเพราะส่วนใดส่วนหนึ่งเก่า)<!-- METRICS.md §26 --></p>"""
        if stale_sections else ""
    )
    freshness_line = report["freshness_line"].format(round=rv.thai_month_short(vf["run_date"]), fit_last=rv.thai_month_short(vf["fit_last"]),
                                                     built_at=rv.thai_datetime_short(page_built_at))
    timestamps_html = f"""
    <details class="note-box" style="margin:10px 0" id="page-data-line">
      <summary style="cursor:pointer"><!-- round = run month of vintage {vf['vintage_id']} of the forward-test log; fit_last = that vintage's last fit month; built_at = page_built_at; oldest data_pulled_at of the page: {data_pulled_at} {ICT_LABEL}, per section below
        --><span id="freshness-line">{html.escape(freshness_line)}</span><!-- source: src/build_report.py rv.vintage_facts()/datetime.now(), this build run --></summary>
      <h3 style="margin-top:10px">ข้อมูลแต่ละส่วนดึงเมื่อ</h3>
      <table class="report-table" style="margin-top:8px">
        <thead><tr><th>ส่วน</th><th>ดึงเมื่อ</th><th>สถานะ</th></tr></thead>
        <tbody>{freshness_rows}</tbody>
      </table>
    </details>
    {staleness_html}"""

    report_data = embed_report_data(scope_table, biz, model_chart, results, fva, primary_results, notlate, backtest_window)
    report_data_json = json.dumps(report_data, ensure_ascii=False)

    forecast_total = int(scope_table["forecast"].sum())
    placeholder_total = int(scope_table["placeholder"].sum())
    excluded_total = int(scope_table["excluded"].sum())
    total_codes = int(scope_table.values.sum())

    # First and last year shown come from the data (the years present in the trend), not typed.
    ontime_first_year = int(biz["ontime_by_year"]["year"].min())
    ontime_last_year = int(biz["ontime_by_year"]["year"].max())
    ontime_2026_val = biz["ontime_by_year"][biz["ontime_by_year"]["year"] == ontime_last_year]["pct_on_time"].iloc[0]
    ontime_2023_val = biz["ontime_by_year"][biz["ontime_by_year"]["year"] == ontime_first_year]["pct_on_time"].iloc[0]
    n_rounds = rv.backtest_rounds(config)
    buckets = sorted(int(d) for d in biz["buckets"]["min_notice_days"])
    note_values = {
        "notice_bucket_first": buckets[0], "notice_bucket_second": buckets[1], "notice_bucket_last": buckets[-1],
        "n_delivery_lines": len([1 for series in (biz["ontime_by_year"], notlate) if len(series)]),
        "n_focus_items": len(FOCUS_ITEMS), "n_rounds": n_rounds, "holdout_months": config["backtest"]["holdout_months"],
    }
    n_no_minmax, n_scope_items = rv.count_no_current_minmax()
    report_values = {
        "forecast_date_revision_share_pct": f"{rv.forecast_date_disagreement_pct():.1f}",
        "n_no_minmax": n_no_minmax, "n_scope_items": n_scope_items,
        "history_months": rv.total_history_months(config), "n_base_models": len(BASE_MODELS),
        "intermittent_lumpy_share_pct": f"{rv.intermittent_lumpy_share_pct():.0f}",
        "first_scoring_month": rv.first_scoring_month_label(config),
    }

    # ---- values of the sections added 2026-10-08 ----
    forward = gather_forward_forecast(vf, scope_table)
    pilot_groups = gather_pilot_groups(config)
    scored = gather_scored_months(primary_results)
    accuracy = gather_accuracy_vs_naive(config, primary_results)
    scored = scored.merge(accuracy["forward_by_division"][["vintage_id", "target_month", "division", "MAE_naive", "relative_mae"]], on=["vintage_id", "target_month", "division"], how="left")
    price_basis = require_config_path(config, "report.price_basis")
    price_info = rv.unit_prices(sorted({it["item"] for ts in forward["divisions"].values() for t in ts for it in t["items"]}), price_basis,
                                vf["fit_first"], vf["fit_last"], os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"), PROJECT_ROOT)
    back = rv.price_back_check(price_info, price_basis, PROJECT_ROOT)
    if back["outside"]:
        raise ReportSourceError(f"the baht view is not published: sum(actual qty x unit price) / sum(actual sale) is outside {price_basis['back_check_low']}..{price_basis['back_check_high']} for {back['outside']}; the price rule or its scope may be wrong.")
    baht = gather_baht(forward, price_info)
    scored = attach_scored_baht(scored, price_info["prices"])
    note_values["n_scored_months"] = int(scored["target_month"].nunique())
    fwd_first, fwd_last = rv.thai_month_short(forward["months"][0]), rv.thai_month_short(forward["months"][-1])

    # ---- Section 1: Executive summary ----
    sec1 = f"""
    <section id="exec-summary">
      <h2>1. บทสรุปผู้บริหาร (Executive Summary)</h2>
      <p>{html.escape(report['model_description'].format(**report_values))}</p>
      <p>
        {cite('phaseC_step1revised_item_status_445.csv', 'status_category')}
        โครงการนี้ครอบคลุมสินค้าทั้งหมด <b>{total_codes}</b> รหัส ใน Omni Channel ทุกฝ่าย
        (PEM101/PEM102/PEM103/PEM104/PEM107/CI101) โดย <b>{forecast_total}</b> รหัสมีประวัติขาย
        เพียงพอสำหรับการพยากรณ์ <b>{placeholder_total}</b> รหัสไม่มีประวัติเพียงพอและใช้ค่า
        Placeholder แทน และ <b>{excluded_total}</b> รหัสถูกตัดออกจากการพยากรณ์
        {cite('leadtime_overall_distribution.csv', 'median')}
        ลูกค้าให้เวลาแจ้งล่วงหน้าก่อนส่งมอบเพียง <b>{fmt_num(biz['median_notice'], 0)}</b> วัน
        (median) ซึ่งสั้นกว่าระยะเวลาจัดหาวัตถุดิบมาก
        {cite('delivery_by_year.csv', 'pct_on_time')}
        สัดส่วนส่งตรงวันพอดี (exact-day delivery: ส่งวันนัดเป๊ะ ไม่นับส่งก่อน) ปรับตัวขึ้นจาก {fmt_num(ontime_2023_val, 1)}% ({ontime_first_year}) เป็น
        <b>{fmt_num(ontime_2026_val, 1)}%</b> ในปี {ontime_last_year} (ข้อมูลบางส่วน)
      </p>
    </section>"""

    # ---- Section 2: forward forecast (the latest vintage of the forward-test log, the rows G2 and G3 read) ----
    month_heads = "".join(f"<th>{html.escape(rv.thai_month_short(m))}</th>" for m in forward["months"])

    def _cells(values):
        return "".join(f"<td>{fmt_cell(v)}</td>" for v in values)
    fwd_tables = []
    for d_i, (d, types) in enumerate(forward["divisions"].items()):
        body_rows = []
        for t_i, t in enumerate(types):
            rid = f"fwd-{d}-{t_i}"
            body_rows.append(f'<tr class="fwd-type" id="{rid}" data-division="{html.escape(d)}" tabindex="0" role="button" aria-expanded="false">'
                             f'<td>{html.escape(t["type"])}</td>{_cells(t["values"])}</tr>')
            for it in t["items"]:
                label = html.escape(it["item"]) + (f' <span class="fwd-name">{html.escape(it["name"])}</span>' if it["name"] else "")
                body_rows.append(f'<tr class="fwd-item" data-parent="{rid}" data-division="{html.escape(d)}" hidden><td>{label}</td>{_cells(it["values"])}</tr>')
        fwd_tables.append(f'<div class="table-scroll fwd-table-wrap" data-division="{html.escape(d)}"{"" if d_i == 0 else " hidden"}>'
                          f'<table class="report-table fwd-table" id="fwd-table-{html.escape(d)}"><thead><tr><th>{html.escape(report["forward_table_head"])}</th>{month_heads}</tr></thead>'
                          f'<tbody>{"".join(body_rows)}</tbody></table></div>')
    fwd_division_options = "".join(f'<option value="{html.escape(d)}">{html.escape(d)}</option>' for d in forward["divisions"])
    forward_missing = html.escape(report["forward_missing_line"]).format(
        n=forward["n_without_forecast"], scope_link=f'<a href="#scope">{html.escape(report["forward_scope_link_text"])}</a>')

    # Baht view (shown only when the unit switch is on baht): label, explanation, items without a price, summary table, one per-Type table per division.
    def _bcell(v):
        return "<td>-</td>" if v is None else f"<td>{v:,}</td>"

    def _bcells(values):
        return "".join(_bcell(v) for v in values)
    baht_tables = []
    for d_i, (d, bd) in enumerate(baht["divisions"].items()):
        b_rows = []
        for t_i, t in enumerate(bd["types"]):
            rid = f"fwdb-{d}-{t_i}"
            b_rows.append(f'<tr class="fwd-btype" id="{rid}" tabindex="0" role="button" aria-expanded="false"><td>{html.escape(t["type"])}</td>{_bcells(t["values"])}</tr>')
            for it in t["items"]:
                label = html.escape(it["item"]) + (f' <span class="fwd-name">{html.escape(it["name"])}</span>' if it["name"] else "")
                b_rows.append(f'<tr class="fwd-bitem" data-parent="{rid}" hidden><td>{label}</td>{_bcells(it["values"] if it["values"] is not None else [None] * len(forward["months"]))}</tr>')
        b_rows.append(f'<tr class="total-row"><td>{html.escape(report["baht_division_total_row"].format(division=d))}</td>{_bcells(bd["total"])}</tr>')
        baht_tables.append(f'<div class="table-scroll fwd-baht-wrap" data-division="{html.escape(d)}"{"" if d_i == 0 else " hidden"}>'
                           f'<table class="report-table fwd-table" id="fwd-baht-table-{html.escape(d)}"><thead><tr><th>{html.escape(report["forward_table_head"])}</th>{month_heads}</tr></thead>'
                           f'<tbody>{"".join(b_rows)}</tbody></table></div>')
    summary_rows = "".join(f'<tr><td>{html.escape(d)}</td>{_bcells(bd["total"])}</tr>' for d, bd in baht["divisions"].items())
    summary_rows += f'<tr class="total-row"><td>{html.escape(report["baht_all_divisions_row"])}</td>{_bcells(baht["all"])}</tr>'
    baht_summary = (f'<h3 id="baht-summary-title">{html.escape(report["baht_summary_title"])}</h3>'
                    f'<div class="table-scroll"><table class="report-table fwd-table" id="baht-summary-table"><thead><tr><th>{html.escape(report["forward_division_label"])}</th>{month_heads}</tr></thead>'
                    f'<tbody>{summary_rows}</tbody></table></div>')
    n_market = len(baht["market_items"])
    baht_label = report["baht_label"].format(first_month=rv.thai_month_short(price_info["recent"][0]), last_month=rv.thai_month_short(price_info["recent"][-1]))
    if n_market:
        baht_label += report["baht_label_market_part"].format(m=n_market)
    no_price_html = ""
    if baht["no_price"]:
        np_rows = "".join(f'<tr><td>{html.escape(r["item"])}</td><td>{html.escape(r["name"])}</td><td>{html.escape(r["division"])}</td></tr>' for r in baht["no_price"])
        np_head = "".join(f"<th>{html.escape(c)}</th>" for c in report["baht_no_price_columns"])
        no_price_html = (f'<details id="baht-no-price"><summary class="hint">{html.escape(report["baht_no_price_line"].format(n=len(baht["no_price"])))}</summary>'
                         f'<div class="table-scroll"><table class="report-table" id="baht-no-price-table"><thead><tr>{np_head}</tr></thead><tbody>{np_rows}</tbody></table></div></details>')
    not_flat = items_not_flat(forward)
    if not_flat:
        logger.warning("The flat-forecast line is not added: %d items differ between the forecast months (first: %s).", len(not_flat), not_flat[:5])
    flat_line_html = "" if not_flat else f'<p class="hint" id="flat-forecast-line"><!-- verified at build: every item has one forecast value for all months of the vintage -->{html.escape(report["flat_forecast_line"])}</p>'
    unit_switch = (f'<span class="unit-switch" id="unitSwitch" role="group" aria-label="{html.escape(report["unit_switch_label"])}">{html.escape(report["unit_switch_label"])} '
                   f'<button type="button" data-unit="pieces" aria-pressed="true">{html.escape(report["unit_switch_pieces"])}</button> {html.escape(report["unit_switch_separator"])} '
                   f'<button type="button" data-unit="baht" aria-pressed="false">{html.escape(report["unit_switch_baht"])}</button></span>'
                   f'<span class="hint">({html.escape(report["unit_switch_hint"])})</span>')
    sec_fwd = f"""
    <section id="forward-forecast">
      <h2>2. {html.escape(report['forward_heading'].format(first_month=fwd_first, last_month=fwd_last))}</h2>
      <!-- source: the Item rows of vintage {vf['vintage_id']} (the latest) of output/summary/forward_test_log_all_divisions.csv after the hash check, the same rows the Min-Max page and the operation plan read; a Type's value is the sum of its items'. -->
      <!-- baht: round(units x unit price) per item and month; unit price = sum of sale / sum of qty of the item over the months {price_info['recent'][0]} to {price_info['recent'][-1]} of the saved monthly series (config report.price_basis), else over the fit window {price_info['fit'][0]} to {price_info['fit'][-1]}, else the Market Price of the price list (columns found per sheet: {price_info['market_columns']}), else no price. -->
      <p class="hint baht-only" id="baht-label">{html.escape(baht_label)}</p>
      <p class="hint baht-only" id="baht-explanation">{html.escape(report['baht_explanation'])}</p>
      <div class="pieces-only">{render_notes_html('sales_report.html', 'forward-forecast', values=note_values)}</div>
      <p class="hint" id="forward-missing">{forward_missing}</p>
      <div class="controls">
        <label>{html.escape(report['forward_division_label'])}: <select id="fwdDivision">{fwd_division_options}</select></label>
        <span class="hint">({html.escape(report['forward_division_hint'])})</span>
        {unit_switch}
      </div>
      <div class="baht-only">{no_price_html}{baht_summary}</div>
      <div class="pieces-only">{"".join(fwd_tables)}</div>
      <div class="baht-only">{"".join(baht_tables)}</div>
      {flat_line_html}
    </section>"""

    # ---- Section 3: Scope ----
    scope_rows = "".join(
        f"<tr><td>{div}</td><td>{cite('phaseC_step1revised_item_status_445.csv', 'status_category')}{int(row['forecast'])}</td>"
        f"<td>{int(row['placeholder'])}</td><td>{int(row['excluded'])}</td><td>{int(row.sum())}</td></tr>"
        for div, row in scope_table.iterrows()
    )
    sec2 = f"""
    <section id="scope">
      <h2>3. ขอบเขตข้อมูล (Scope)</h2>
      <p>ขอบเขต Omni Channel ครอบคลุมสินค้าทุกฝ่ายตาม Price List รวม {total_codes} รหัส</p>
      <table class="report-table">
        <thead><tr><th>ฝ่าย (Division)</th><th>พยากรณ์ (Forecast)</th><th>Placeholder</th><th>ตัดออก (Excluded)</th><th>รวม</th></tr></thead>
        <tbody>{scope_rows}
        <tr class="total-row"><td>รวมทั้งหมด</td><td>{forecast_total}</td><td>{placeholder_total}</td><td>{excluded_total}</td><td>{total_codes}</td></tr>
        </tbody>
      </table>
    </section>"""

    # ---- Section 3: Business findings (Plotly) ----
    sec3 = f"""
    <section id="business-findings">
      <h2>4. ข้อค้นพบทางธุรกิจ (Business Findings)</h2>
      <p>
        {cite('leadtime_overall_distribution.csv', 'median')}
        Median customer notice: <b>{fmt_num(biz['median_notice'], 0)}</b> วัน &nbsp;|&nbsp;
        {cite('leadtime_notice_buckets_overall.csv', 'pct_of_orders')}
        สัดส่วนออเดอร์ที่แจ้งล่วงหน้า &ge; 1 เดือน: <b>{fmt_num(biz['pct_one_month'], 2)}%</b> &nbsp;|&nbsp;
        {cite_config('phase_e1_assumptions.procurement_lead_time_days_grid')}
        ระยะเวลาจัดหาวัตถุดิบ (Procurement lead time): <b>{biz['lead_grid'][0]}-{biz['lead_grid'][-1]}</b> วัน
        (ค่ากลาง {biz['lead_default']} วัน)
      </p>
      <h3>การกระจายของระยะเวลาแจ้งล่วงหน้า (Notice period)</h3>
      {cite('leadtime_notice_buckets_overall.csv', 'min_notice_days / pct_of_orders')}
      <div id="chart-notice" class="plotly-chart"></div>
      {render_notes_html('sales_report.html', 'chart-notice', values=note_values)}
      <h3>สัดส่วนส่งมอบตรงวันครบกำหนดเป๊ะ vs. ส่งไม่ล่าช้า ({ontime_first_year}-{ontime_last_year})</h3>
      <!-- Previous wording, kept off screen: on_time_exact = delivered exactly on the due date (PlanDelDate), counted by number of orders (row-weighted), PEM101 128 items -- src/investigations/delivery_performance.py:71-75 (classify_delay) and lines 155-161 (by_year aggregation, column pct_on_time); METRICS.md §19 forbids using this figure alone as a fill-rate benchmark (the earlier 73.2% incident), so not_late is shown alongside. not_late = delivered on or before ForecastDelDate, unit-weighted (ActualQty), not by order count; unit-weighted because METRICS.md §10 (fill_rate) is defined as unit-based, not order-based, and the figure is read alongside fill_rate/service level (src/investigations/task2a_delivery_notlate_by_year.py, computed from the same Cube_CES data as on_time_exact, no new pull). -->
      <p class="hint">เส้นส่งไม่ช้านับเป็นชิ้น เพราะสิ่งที่ลูกค้าสนใจคือได้ของครบทันไหม ไม่ใช่จำนวนใบสั่ง</p>
      {cite('delivery_by_year.csv', 'year / pct_on_time')}
      {cite('delivery_not_late_by_year.csv', 'year / not_late_pct_unit_weighted')}
      <div id="chart-ontime" class="plotly-chart"></div>
      {render_notes_html('sales_report.html', 'chart-ontime', values=note_values)}
    </section>"""

    # ---- Section 4: Data ----
    sec4 = f"""
    <section id="data">
      <h2>5. ข้อมูลที่ใช้ (Data)</h2>
      <table class="report-table">
        <tbody>
          <tr><td>แหล่งข้อมูล (Source table)</td><td>{cite_config('source_table')}<!-- table: {html.escape(str(config['source_table']))} -->ระบบขายของบริษัท</td></tr>
          <!-- source: the fit window (first and last month) of vintage {vf['vintage_id']} of the forward-test log metadata, the series every figure of this page's forecast is fitted on -->
          <tr><td colspan="2" id="fit-range-line">{html.escape(report['fit_range_line'].format(first_month=rv.thai_month_short(vf['fit_first']), last_month=rv.thai_month_short(vf['fit_last'])))}</td></tr>
          <!-- Split lots; STATUS.md, Locked Decisions -->
          <tr><td colspan="2">รายการที่ดูเหมือนซ้ำแต่เป็นการแบ่งส่งหลายงวด นับครบทุกงวด</td></tr>
          <!-- MPS retained; STATUS.md, Locked Decisions -->
          <tr><td colspan="2">MPS (open PO: PO ที่รับแล้วแต่ยังไม่ส่ง) นับรวมในยอดที่ใช้ทาย (Actual + MPS) เพราะลูกค้าสั่งแล้วจริง แต่ยังไม่ใช่ยอดที่ส่งมอบแล้ว</td></tr>
          <!-- forecast_date keying: the series is keyed on forecast_date, a frozen snapshot, not queried live each time; STATUS.md, Locked Decisions -->
          <tr><td colspan="2">ยอดขายนับตามเดือนที่ต้องส่งของตามสัญญา ไม่ใช่เดือนที่รับ PO</td></tr>
          <!-- Pricelist as division source; the database division column is not used to filter; STATUS.md, CONVENTIONS.md -->
          <tr><td colspan="2">ฝ่ายของสินค้ายึดตาม Price List</td></tr>
        </tbody>
      </table>
    </section>"""

    # ---- Section 5: Model (Plotly, legend-toggle bar chart) ----
    sec5 = f"""
    <section id="model">
      <h2>6. โมเดลพยากรณ์ (Model)</h2>
      <p>{html.escape(report['model_description'].format(**report_values))}</p>
      <p>{html.escape(report['why_not_single_model'].format(**report_values))}</p>
      <p>{html.escape(report['why_not_ml'].format(**report_values))}</p>
      <h3>MAE ของโมเดลพื้นฐาน {len(BASE_MODELS)} แบบ เทียบกับ Combination และ Top-down ({len(FOCUS_ITEMS)} focus codes)</h3>
      <p class="hint">คลิกที่ legend เพื่อซ่อน/แสดงแต่ละโมเดล</p>
      {cite('focus_items_test_all.csv', 'model / MAE')}
      <div id="chart-model" class="plotly-chart"></div>
      {render_notes_html('sales_report.html', 'chart-model', values=note_values)}
    </section>"""

    # ---- Section 6: Results (Plotly, with Division/Type/Item/Origin controls) ----
    divisions = sorted(set(r["division"] for r in report_data["rolling_origin"]))
    div_options = "".join(f'<option value="{html.escape(d)}">{html.escape(d)}</option>' for d in divisions)
    fva_items = sorted(set(fva["itemcode"].unique()))
    item_checkboxes = "".join(
        f'<label class="item-check"><input type="checkbox" class="fva-item" value="{html.escape(it)}"'
        f'{" checked" if it in FOCUS_ITEMS else ""}> {html.escape(it)}</label>'
        for it in fva_items
    )

    significance_html = significance_block_html(results["topdown_sig"])

    # Pilot groups: MAE and Bias of the group's own forecast; one sentence per group whose Bias is negative (a forecast below the actual).
    negative = [g for g in pilot_groups if g["Bias"] < 0]
    pilot_lines = list(load_manual_notes()["sales_report.html"]["pilot-group"])
    pilot_lines += [report["pilot_group_line"].format(group=g["label"], x=f"{abs(g['Bias']):.1f}") for g in negative]
    if negative:
        pilot_lines.append(report["pilot_warn_line"])
    pilot_rows = "".join(f"<tr><td>{html.escape(g['label'])}</td><td>{g['MAE']:.1f}</td><td>{g['Bias']:.1f}</td></tr>" for g in pilot_groups)
    pilot_head = "".join(f"<th>{html.escape(c)}</th>" for c in report["pilot_columns"])
    pilot_html = f"""<h3 id="pilot-groups">{html.escape(report['pilot_heading'])}</h3>
      <!-- source: build_pilot_view_payload() (src/focus_item_model_selection.py), units[..].series_own, groups from config pilot_categories; Bias = forecast minus actual -->
      <p class="hint" id="pilot-notes">{"<br>".join(html.escape(l) for l in pilot_lines)}</p>
      <table class="report-table" id="pilot-table"><thead><tr>{pilot_head}</tr></thead><tbody>{pilot_rows}</tbody></table>
      <p class="hint" id="pilot-scope-note">{html.escape(report['pilot_scope_note'])}</p>
      <!-- source: output/summary/forward_test_scores.csv (scope shadow_group) and config shadow, via shadow_rule_status(); METRICS.md Sec.51 -->
      <p class="hint" id="pilot-shadow">{html.escape(shadow_line_text(config))}</p>"""

    # Against the draft criteria: Relative MAE (all horizons and Horizon 3) and Tracking Signal per division and pilot group (METRICS.md Sec.48).
    th = accuracy["thresholds"]
    crit_rows = "".join(
        f"<tr><td>{html.escape(r['label'])}</td><td>{fmt_ratio(r['relative_mae'], 2)}</td><td>{html.escape(report['verdict_words'].get(r['verdict_relative'], r['verdict_relative']))}</td>"
        f"<td>{fmt_ratio(r['relative_mae_h3'], 2)}</td><td>{html.escape(report['verdict_words'].get(r['verdict_relative_h3'], r['verdict_relative_h3']))}</td>"
        f"<td>{fmt_ratio(r['tracking_signal'], 1)}</td><td>{r['verdict_tracking']}</td></tr>" for r in accuracy["rows"])
    crit_head = "".join(f"<th>{html.escape(c)}</th>" for c in report["criteria_columns"])
    crit_values = {"pass_value": f"{th['pass']:g}", "good_value": f"{th['good']:g}", "warn_value": f"{th['limit']:g}", "n_rounds": str(rv.backtest_rounds(config)),
                   "decision_date": rv.thai_date_short(config["maxmin_v1"]["pending_criteria_values"]["decision_date"])}
    criteria_html = f"""<h3 id="criteria-vs-draft">{html.escape(report['criteria_heading'])}</h3>
      <!-- source: Relative MAE, Horizon 3 and Tracking Signal recomputed at build from the saved monthly series with the functions of the main table (src/transferability_all_divisions.py), Naive = the last month before each origin; the forward months from the forward-test log (src/forward_test_scoring.py forward_naive_items); thresholds: config maxmin_v1.pending_criteria_values (draft). METRICS.md Sec.48. Tracking Signal points used per row: {", ".join(f"{r['label']} {r['n_points']}" for r in accuracy["rows"])}. -->
      {render_notes_html('sales_report.html', 'criteria-comparison', values=crit_values)}
      <div class="table-scroll"><table class="report-table" id="criteria-table"><thead><tr>{crit_head}</tr></thead><tbody>{crit_rows}</tbody></table></div>"""

    # Forecast against actual, month by month, from the recorded forward-test scores.
    scored_rows = "".join(f"<tr><td>{html.escape(r.division)}</td><td>{html.escape(rv.thai_month_short(r.target_month))}</td><td>{r.MAE:.1f}</td><td>{r.MAE_naive:.1f}</td><td>{fmt_ratio(r.relative_mae, 2)}</td><td>{r.Bias:.1f}</td>"
                          f"<td>{r.MAE_backtest:.1f}</td>"
                          f"<td>{r.baht_forecast:,}</td><td>{r.baht_actual:,}</td><td>{r.baht_diff:,}</td></tr>" for r in scored.itertuples())
    scored_head = "".join(f"<th>{html.escape(c)}</th>" for c in report["scored_columns"])
    scored_html = f"""<h3 id="scored-months">{html.escape(report['scored_heading'])}</h3>
      <!-- source: output/summary/forward_test_scores.csv (scope division, horizon 1, integrity-checked); backtest MAE = the main table's Top-down MAE of the division -->
      {render_notes_html('sales_report.html', 'forecast-vs-actual-monthly', values=note_values)}
      <div class="table-scroll"><table class="report-table" id="scored-table"><thead><tr>{scored_head}</tr></thead><tbody>{scored_rows}</tbody></table></div>
      <!-- baht: items = the items the row's MAE is computed over; forecast and actual units of each item x its unit price (as section 2); difference = forecast minus actual, the sign of Bias. Items without a price in these rows: {int(scored['n_no_price'].sum())}. -->
      <p class="hint" id="scored-baht-note">{html.escape(report['scored_baht_note'])}</p>"""
    sec6 = f"""
    <section id="results">
      <h2>7. ผลลัพธ์ (Results)</h2>
      {cite('phaseC_step2_transferability_per_division.csv', 'first_test_month / last_test_month')}
      <!-- rolling-origin backtest window, {backtest_window['n_origins']} origins; METRICS.md §39 -->
      <p class="hint">ตัวเลขทุกตัวด้านล่างมาจากการทดสอบช่วง {backtest_window['first_test_month']} ถึง {backtest_window['last_test_month']}</p>
      <div class="controls">
        <label>ฝ่าย (Division): <select id="filterDivision"><option value="__all__">ทั้งหมด</option>{div_options}</select></label>
        <span class="hint">(มีผลกับตารางหลัก ตารางรอง และกราฟ Rolling-origin · ไม่มีผลกับกราฟ Forecast vs Actual)</span>
        <label>ประเภท (Type): <select id="filterType"><option value="__all__">ทั้งหมด</option></select></label>
        <span class="hint">(มีผลกับกราฟ Rolling-origin เท่านั้น · ไม่มีผลกับตารางหลักและตารางรอง)</span>
      </div>
      <h3>ตารางหลัก — ความแม่นของวิธี Top-down (วิธีที่ใช้จริง) ต่อฝ่าย</h3>
      <!-- Previous wording, kept off screen: this is the Top-down method the project adopted (STATUS.md Locked Decisions, "Final forecasting method"): forecast at Type level, then allocate to items by trailing sales share, recomputed at every rolling origin (not a one-time fixed allocation), scored at item level across the project's standard 7 origins -- src/transferability_all_divisions.py, summary in output/summary/phaseC_step2_transferability_per_division.csv (method detail in docs/reports/summary/phaseC_step2_report.md Part 3). -->
      <p class="hint">ทายยอดรวมระดับประเภทสินค้าก่อน แล้วแบ่งให้แต่ละรหัสตามสัดส่วนที่เคยขาย ทดสอบย้อนหลัง {n_rounds} รอบ</p>
      {cite('phaseC_step2_transferability_per_division.csv', 'MAE / RMSE / Bias / MASE / n_scored')}
      <!-- filtered to rows where approach == 'Top-down' -->
      <table class="report-table" id="primary-results-table">
        <thead><tr><th>ฝ่าย</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>MASE</th><th>n_scored (item × origin)</th></tr></thead>
        <tbody></tbody>
      </table>
      <h3>ตารางรอง — วิธี Combination ระดับประเภทสินค้า</h3>
      <!-- Previous wording, kept off screen: Combination model only, at Type level (not item level), averaged across all Types and the 7 rolling origins per division -- src/backtest_all_divisions.py:126-139 (first disclosed in output/summary/manual_factsheet.md Part 5 item 2); kept for comparison, no longer the primary table. -->
      <p class="hint">ผลของส่วน Combination ก่อนแบ่งลงรหัสสินค้า ใช้เทียบเท่านั้น ตัวเลขที่ใช้วางแผนคือตารางหลัก</p>
      {cite('phaseC_step2_per_division_summary_qty.csv', 'MAE / RMSE / Bias / MASE / n_items')}
      <table class="report-table" id="div-results-table">
        <thead><tr><th>ฝ่าย</th><th>MAE</th><th>RMSE</th><th>MASE</th><th>Bias</th><th>จำนวนสินค้า</th></tr></thead>
        <tbody></tbody>
      </table>
      {pilot_html}
      {criteria_html}
      <h3>Rolling-origin MAE (Type level) — คลิก legend เพื่อซ่อน/แสดงแต่ละโมเดล</h3>
      {cite('phaseC_step2_rolling_origin_qty.csv', 'origin / model / MAE')}
      <div id="chart-rolling" class="plotly-chart"></div>
      {render_notes_html('sales_report.html', 'chart-rolling', values=note_values)}
      <h3>Forecast เทียบกับ Actual — เลือกสินค้าและ rolling origin</h3>
      <!-- Previous wording, kept off screen: scope of this chart is the PEM101 pilot group ({len(fva_items)} codes, Fuse Cutout + Surge Arrester), the standard 7 rolling origins used across the project (get_origins(31,6), src/backtest_rekeyed.py), not the earlier 9 origins. -->
      <p class="scope-note">ทดสอบ {n_rounds} รอบแบบเดียวกับตารางด้านบน · มีเฉพาะสินค้า PEM101 กลุ่มนำร่อง</p>
      <div class="controls">
        <label>Rolling origin: <select id="filterOrigin">{"".join(f'<option value="{o}">{o}</option>' for o in range(1, n_rounds + 1))}</select></label>
        <span class="hint">(ตัวกรอง ฝ่าย/ประเภท ด้านบนไม่มีผลกับกราฟนี้ — กราฟนี้มีเฉพาะสินค้า PEM101 กลุ่มนำร่องเท่านั้น)</span>
      </div>
      <div class="item-check-list">{item_checkboxes}</div>
      {cite('report_item_forecast_vs_actual_by_origin.csv', 'origin / month_in_horizon / actual_qty / forecast_qty')}
      <div id="chart-fva" class="plotly-chart"></div>
      {render_notes_html('sales_report.html', 'chart-fva', values=note_values)}
      {cite('topdown_significance.csv', 'verdict / rel_diff_pct')}
      {significance_html}
      {scored_html}
    </section>"""

    # ---- Section 7: Limitations ----
    limitations_html = "".join(f"<li>{html.escape(x.format(**report_values))}</li>" for x in report["limitations"])
    sec7 = f"""
    <section id="limitations">
      <h2>8. ข้อจำกัด (Limitations)</h2>
      <ul>{limitations_html}</ul>
    </section>"""

    # ---- Section 8: Next steps ----
    next_steps_html = "".join(f"<li>{html.escape(x.format(**report_values))}</li>" for x in report["next_steps"])
    sec8 = f"""
    <section id="next-steps">
      <h2>9. ขั้นตอนต่อไป (Next Steps)</h2>
      <ul>{next_steps_html}</ul>
    </section>"""

    controls_note = f"""
    <!-- Previous wording, kept off screen: the controls on this page (Division/Type/Item/Origin selectors, legend toggles) change only the view shown, not the model or the forecasts already computed; structural changes (Tier B parameters: base models, combination method, scope, series key, aggregation level) are made in config.yaml and need a pipeline re-run, per the Tier A/B/C grouping in config.yaml's comment block "Three-tier parameter classification". -->
    <div class="controls-note">ตัวกรองในส่วนนี้เปลี่ยนแค่สิ่งที่แสดง ไม่ได้เปลี่ยนการทาย</div>"""

    body = sec1 + sec_fwd + sec2 + sec3 + sec4 + sec5 + controls_note + sec6 + sec7 + sec8

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>รายงานการพยากรณ์ยอดขาย — PEM Group</title>
<!-- Plotly, pinned version, loaded from cdnjs.cloudflare.com -- CDN load only, not bundled into
     this repo. This page is served from GitHub Pages, where a CDN <script> is acceptable. This
     is a deliberate deviation from index.html's own dependency-free inline-SVG approach (see this
     file's module docstring), introduced only for this page's interactive charts. -->
<script src="{PLOTLY_CDN_URL}"></script>
<style>
  :root {{
    color-scheme: light;
    --page: {COLORS['page']}; --surface: {COLORS['surface']};
    --text-primary: {COLORS['text_primary']}; --text-secondary: {COLORS['text_secondary']};
    --muted: {COLORS['muted']}; --gridline: {COLORS['gridline']}; --border: {COLORS['border']};
    --series-1: {COLORS['series1']}; --series-2: {COLORS['series2']};
    --series-3: {COLORS['series3']}; --series-4: {COLORS['series4']};
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--page); color:var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size:14px; line-height:1.6; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 24px 80px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 17px; margin: 32px 0 10px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  h3 {{ font-size: 13px; color: var(--text-secondary); margin: 18px 0 6px; }}
  p {{ margin: 6px 0; }}
  p.hint, p.scope-note, span.hint, span.scope-note {{ font-size: 12px; color: var(--muted); }}
  p.note-box {{ font-size: 12px; color: var(--text-secondary); background: #f0efec; border-radius: 6px; padding: 8px 10px; }}
  code {{ background: var(--gridline); padding: 1px 5px; border-radius: 4px; }}
  .report-table {{ width:100%; border-collapse: collapse; font-size: 13px; margin: 6px 0 16px; }}
  .report-table th, .report-table td {{ border: 1px solid var(--border); padding: 6px 8px; text-align: left; }}
  .report-table thead th {{ background: #f0efec; }}
  .report-table .total-row td {{ font-weight: 700; background: #f0efec; }}
  ul {{ margin: 6px 0; padding-left: 22px; }}
  li {{ margin-bottom: 6px; }}
  a.back-link {{ color: var(--series-1); text-decoration: none; font-size: 13px; }}
  .plotly-chart {{ width:100%; min-height: 260px; margin: 6px 0 14px; }}
  .chart-fail {{ padding: 24px 12px; text-align: center; background: #f0efec; border-radius: 6px; }}
  .controls {{ display:flex; gap:16px; flex-wrap:wrap; margin: 10px 0; font-size:13px; }}
  .controls select {{ margin-left:4px; padding:3px 6px; }}
  .controls-note {{ background:#eef4fb; border:1px solid var(--border); border-radius:6px;
    padding:10px 12px; font-size:12.5px; margin: 20px 0; }}
  .item-check-list {{ display:flex; gap:12px; flex-wrap:wrap; margin: 6px 0; font-size:12.5px; }}
  label.item-check {{ background:#f0efec; border-radius: 4px; padding: 2px 8px; }}
  .fwd-table td:not(:first-child), .fwd-table th:not(:first-child) {{ text-align: right; white-space: nowrap; }}
  .fwd-type {{ cursor: pointer; font-weight: 600; }}
  .fwd-type td:first-child::before {{ content: "▸ "; color: var(--muted); }}
  .fwd-type[aria-expanded="true"] td:first-child::before {{ content: "▾ "; }}
  .fwd-name {{ color: var(--muted); font-size: 12px; }}
  .table-scroll {{ overflow-x: auto; max-width: 100%; }}
  #forward-forecast:not([data-unit="baht"]) .baht-only {{ display: none; }}
  #forward-forecast[data-unit="baht"] .pieces-only {{ display: none; }}
  .unit-switch button {{ font: inherit; font-size: 13px; padding: 2px 10px; border: 1px solid var(--border); background: #fcfcfb; border-radius: 4px; cursor: pointer; }}
  .unit-switch button[aria-pressed="true"] {{ background: #eef4fb; font-weight: 700; border-color: var(--series-1); }}
  .fwd-btype {{ cursor: pointer; font-weight: 600; }}
  .fwd-btype td:first-child::before {{ content: "▸ "; color: var(--muted); }}
  .fwd-btype[aria-expanded="true"] td:first-child::before {{ content: "▾ "; }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back-link" href="../index.html">&larr; กลับหน้าหลัก</a>
  <h1>รายงานการพยากรณ์ยอดขาย (Sales Forecast Report) — PEM Group</h1>
  <!-- สร้างโดย src/build_report.py — ทุกตัวเลขมีที่มาระบุไว้ในซอร์สโค้ด HTML (ดู source comments) -->
  {timestamps_html}
  {body}
</div>
<!-- source: output/summary/*.csv (see gather_* functions in src/build_report.py) and
     config.yaml, field report -- assembled by embed_report_data() into one JSON block so every
     client-side chart reads exactly the same numbers the server-rendered text above cites. -->
<script type="application/json" id="report-data">{report_data_json}</script>
<script>
{render_client_js()}
</script>
<script>
{FORWARD_TABLE_JS}
</script>
</body>
</html>"""


# The forward forecast tables (pieces and baht): one division shown at a time (the selector), a click or Enter on a Type row shows or hides its item rows, the unit switch shows
# the pieces or the baht view of the section and leaves the division selection as it is. No number is computed here.
FORWARD_TABLE_JS = """
(function () {
  var sel = document.getElementById('fwdDivision');
  var section = document.getElementById('forward-forecast');
  function showDivision() {
    document.querySelectorAll('.fwd-table-wrap, .fwd-baht-wrap').forEach(function (w) { w.hidden = (w.dataset.division !== sel.value); });
  }
  function toggle(row) {
    var open = row.getAttribute('aria-expanded') !== 'true';
    row.setAttribute('aria-expanded', open ? 'true' : 'false');
    document.querySelectorAll('tr.fwd-item[data-parent="' + row.id + '"], tr.fwd-bitem[data-parent="' + row.id + '"]').forEach(function (r) { r.hidden = !open; });
  }
  function setUnit(unit) {
    section.dataset.unit = unit;
    document.querySelectorAll('#unitSwitch button').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.unit === unit ? 'true' : 'false'); });
  }
  if (sel) sel.addEventListener('change', showDivision);
  document.querySelectorAll('#unitSwitch button').forEach(function (b) { b.addEventListener('click', function () { setUnit(b.dataset.unit); }); });
  document.querySelectorAll('tr.fwd-type, tr.fwd-btype').forEach(function (row) {
    row.addEventListener('click', function () { toggle(row); });
    row.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(row); } });
  });
  if (sel) showDivision();
})();
"""


def fmt_cell(x: float) -> str:
    """A forecast cell: whole units from 10 up, one decimal below, a hyphen for none (the operation plan page's cell format)."""
    x = float(x)
    if abs(x) < 1e-9:
        return "-"
    return f"{x:,.1f}" if abs(x) < 10 else f"{int(round(x)):,}"


def render_client_js() -> str:
    """Vanilla JS (no framework) that reads #report-data, wires up the controls in Section 6,
    and draws every Plotly chart. Kept as a plain <script> block, consistent with this project's
    'no separate build toolchain' style (CONVENTIONS.md doesn't require a JS bundler and this
    project has never used one)."""
    return """
const REPORT_DATA = JSON.parse(document.getElementById('report-data').textContent);
const MODEL_COLORS = """ + json.dumps(MODEL_COLORS) + """;
const PLOT_CONFIG = {responsive: true, displaylogo: false};
const CHART_FAIL_MSG = 'กราฟโหลดไม่ได้ เครือข่ายอาจบล็อกไลบรารีกราฟ · ตัวเลขและตารางยังใช้ได้ตามปกติ';
// Text, tables and the data-date table never depend on the charting library: when it did not load, each chart
// area shows the message instead and the rest of the page carries on.
function chartLibraryOk(id) {
  if (typeof Plotly !== 'undefined') return true;
  document.getElementById(id).innerHTML = '<p class="hint chart-fail">' + CHART_FAIL_MSG + '</p>';
  return false;
}
const LAYOUT_BASE = {
  font: {family: 'system-ui, sans-serif', size: 12, color: '#0b0b0b'},
  // b:40 -> b:80 (this task): the old margin only fit tick labels + the horizontal legend row;
  // once axis titles actually render (see the title:{text:...} fix below -- this Plotly build
  // silently drops the plain-string title:'...' shorthand, so no axis title had ever visibly
  // drawn on this page), the extra vertical space is needed so the title doesn't overlap the
  // legend directly beneath it.
  margin: {l: 60, r: 20, t: 10, b: 80},
  paper_bgcolor: '#fcfcfb', plot_bgcolor: '#fcfcfb',
  legend: {orientation: 'h', y: -0.32}
};

function drawNotice() {
  if (!chartLibraryOk('chart-notice')) return;
  Plotly.newPlot('chart-notice', [{
    x: REPORT_DATA.notice.labels, y: REPORT_DATA.notice.values, type: 'bar',
    marker: {color: '#eb6834'}, hovertemplate: '%{x}: %{y:.1f}%<extra></extra>'
  }], Object.assign({}, LAYOUT_BASE, {xaxis: {title: {text: 'ระยะแจ้งล่วงหน้าขั้นต่ำ (วัน)'}}, yaxis: {title: {text: '% ของออเดอร์'}}}), PLOT_CONFIG);
}

function drawOntime() {
  if (!chartLibraryOk('chart-ontime')) return;
  Plotly.newPlot('chart-ontime', [
    {
      x: REPORT_DATA.ontime.years, y: REPORT_DATA.ontime.values, type: 'scatter', mode: 'lines+markers',
      name: 'ส่งตรงวันพอดี (นับเป็นรายการ)', line: {color: '#2a78d6'},
      hovertemplate: '%{x}: %{y:.1f}%<extra>ส่งตรงวันพอดี (นับเป็นรายการ)</extra>'
    },
    {
      x: REPORT_DATA.notlate.years, y: REPORT_DATA.notlate.values, type: 'scatter', mode: 'lines+markers',
      name: 'ส่งไม่ช้า (นับเป็นชิ้น)', line: {color: '#1baf7a'},
      hovertemplate: '%{x}: %{y:.1f}%<extra>ส่งไม่ช้า (นับเป็นชิ้น)</extra>'
    }
  ], Object.assign({}, LAYOUT_BASE, {xaxis: {title: {text: 'ปี'}}, yaxis: {title: {text: '%'}}}), PLOT_CONFIG);
}

function drawModelChart() {
  if (!chartLibraryOk('chart-model')) return;
  const items = REPORT_DATA.focus_items;
  const models = REPORT_DATA.base_models.concat(['Combination', 'Top-down']);
  const traces = models.map(m => ({
    x: items, y: items.map(it => REPORT_DATA.model_bar[m][it]), type: 'bar', name: m,
    marker: {color: MODEL_COLORS[m]}, hovertemplate: '%{x}<br>' + m + ': %{y:.1f}<extra></extra>'
  }));
  Plotly.newPlot('chart-model', traces, Object.assign({}, LAYOUT_BASE, {barmode: 'group', xaxis: {title: {text: 'รหัสสินค้า'}}, yaxis: {title: {text: 'MAE (ชิ้นต่อเดือน)'}}}), PLOT_CONFIG);
}

function currentDivision() { return document.getElementById('filterDivision').value; }
function currentType() { return document.getElementById('filterType').value; }

function populateTypeOptions() {
  const div = currentDivision();
  const sel = document.getElementById('filterType');
  const prev = sel.value;
  const types = [...new Set(REPORT_DATA.rolling_origin
    .filter(r => div === '__all__' || r.division === div)
    .map(r => r.type))].sort();
  sel.innerHTML = '<option value="__all__">ทั้งหมด</option>' +
    types.map(t => `<option value="${t}">${t}</option>`).join('');
  if (types.includes(prev)) sel.value = prev;
}

function fmtMase(v) {
  return (v === null || v === undefined || Number.isNaN(v)) ? 'MASE_undefined' : v.toFixed(3);
}

function drawDivTable() {
  const div = currentDivision();
  const rows = REPORT_DATA.per_division.filter(r => div === '__all__' || r.division === div);
  const tbody = document.querySelector('#div-results-table tbody');
  tbody.innerHTML = rows.map(r =>
    `<tr><td>${r.division}</td><td>${r.MAE.toFixed(1)}</td><td>${r.RMSE.toFixed(1)}</td><td>${fmtMase(r.MASE)}</td><td>${r.Bias.toFixed(1)}</td><td>${r.n_items}</td></tr>`
  ).join('');
}

function drawPrimaryTable() {
  const div = currentDivision();
  const rows = REPORT_DATA.primary_results.filter(r => div === '__all__' || r.division === div);
  const tbody = document.querySelector('#primary-results-table tbody');
  tbody.innerHTML = rows.map(r =>
    `<tr><td>${r.division}</td><td>${r.MAE.toFixed(1)}</td><td>${r.RMSE.toFixed(1)}</td><td>${r.Bias.toFixed(1)}</td><td>${fmtMase(r.MASE)}</td><td>${r.n_scored}</td></tr>`
  ).join('');
}

function drawRollingChart() {
  if (!chartLibraryOk('chart-rolling')) return;
  const div = currentDivision(), typ = currentType();
  const filtered = REPORT_DATA.rolling_origin.filter(r =>
    (div === '__all__' || r.division === div) && (typ === '__all__' || r.type === typ));
  const models = [...new Set(filtered.map(r => r.model))];
  const traces = models.map(m => {
    const rows = filtered.filter(r => r.model === m);
    const byOrigin = {};
    rows.forEach(r => { byOrigin[r.origin] = byOrigin[r.origin] || []; byOrigin[r.origin].push(r.MAE); });
    const origins = Object.keys(byOrigin).map(Number).sort((a, b) => a - b);
    const means = origins.map(o => byOrigin[o].reduce((a, b) => a + b, 0) / byOrigin[o].length);
    return {x: origins, y: means, type: 'scatter', mode: 'lines+markers', name: m,
            marker: {color: MODEL_COLORS[m] || '#898781'}, line: {color: MODEL_COLORS[m] || '#898781'},
            hovertemplate: 'origin %{x}<br>' + m + ': %{y:.1f}<extra></extra>'};
  });
  Plotly.newPlot('chart-rolling', traces, Object.assign({}, LAYOUT_BASE,
    {xaxis: {title: {text: 'Rolling origin'}, dtick: 1}, yaxis: {title: {text: 'Mean MAE'}}}), PLOT_CONFIG);
}

function selectedFvaItems() {
  return [...document.querySelectorAll('.fva-item:checked')].map(cb => cb.value);
}

function drawFvaChart() {
  if (!chartLibraryOk('chart-fva')) return;
  const origin = parseInt(document.getElementById('filterOrigin').value, 10);
  const items = selectedFvaItems();
  const traces = [];
  const colors = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#c94e1f', '#898781'];
  items.forEach((it, i) => {
    const rows = REPORT_DATA.forecast_vs_actual
      .filter(r => r.itemcode === it && r.origin === origin)
      .sort((a, b) => a.month_in_horizon - b.month_in_horizon);
    if (!rows.length) return;
    const x = rows.map(r => r.month_in_horizon);
    traces.push({x, y: rows.map(r => r.actual_qty), type: 'scatter', mode: 'lines+markers',
      name: it + ' (actual)', line: {color: colors[i % colors.length]},
      hovertemplate: 'month %{x}<br>actual: %{y:.0f}<extra></extra>'});
    traces.push({x, y: rows.map(r => r.forecast_qty), type: 'scatter', mode: 'lines+markers',
      name: it + ' (forecast)', line: {color: colors[i % colors.length], dash: 'dot'},
      hovertemplate: 'month %{x}<br>forecast: %{y:.0f}<extra></extra>'});
  });
  const el = document.getElementById('chart-fva');
  if (!traces.length) {
    el.innerHTML = '<p style="color:#898781;font-size:12px;">ไม่มีข้อมูลระดับสินค้าสำหรับฝ่าย/ประเภทที่เลือก (ขอบเขตกราฟนี้คือ PEM101 pilot 113 รหัสเท่านั้น) — กรุณาเลือกสินค้าจากรายการด้านบน</p>';
    return;
  }
  Plotly.newPlot('chart-fva', traces, Object.assign({}, LAYOUT_BASE,
    {xaxis: {title: {text: 'Month in horizon (origin ' + origin + ')'}, dtick: 1}, yaxis: {title: {text: 'Quantity'}}}), PLOT_CONFIG);
}

function redrawResultsSection() {
  drawPrimaryTable();
  drawDivTable();
  drawRollingChart();
  drawFvaChart();
}

document.addEventListener('DOMContentLoaded', function () {
  drawNotice();
  drawOntime();
  drawModelChart();
  populateTypeOptions();
  redrawResultsSection();

  document.getElementById('filterDivision').addEventListener('change', function () {
    populateTypeOptions();
    redrawResultsSection();
  });
  document.getElementById('filterType').addEventListener('change', redrawResultsSection);
  document.getElementById('filterOrigin').addEventListener('change', drawFvaChart);
  document.querySelectorAll('.fva-item').forEach(cb => cb.addEventListener('change', drawFvaChart));
});
"""


def build_report(output_path: str = None) -> str:
    """Renders and writes forecast/sales_report.html. `output_path` defaults to the real, TRACKED
    production path (OUT_PATH) -- pass an explicit override (e.g. a pytest tmp_path, or
    src/monthly_refresh.py's --dry-run staging path) to render without touching the tracked file.

    FIXED (forward test / monthly refresh task, Part 1/Part 3): previously this function took NO
    parameters and always wrote OUT_PATH, so tests/test_build_report.py's
    test_report_builds_without_error_from_current_outputs() and
    tests/test_page_timestamps.py's test_embedded_json_never_contains_literal_nan_for_mase()
    (the only two callers found by a repo-wide search of every test for a build_report()/
    build_inventory_page()-style call with no override) regenerated the real tracked HTML on
    every pytest run, changing only page_built_at each time (commits 5c17ea4/da5aedd) -- exactly
    what METRICS.md Sec.28's last bullet ("Tests must not modify tracked output files; a test
    that regenerates a page writes to a temporary location") forbids. Both tests now pass
    tmp_path explicitly."""
    out_path = output_path if output_path is not None else OUT_PATH
    config = load_config()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    html_out = render_page(config)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    logger.info("Report written: %s (%d bytes)", out_path, len(html_out.encode("utf-8")))
    return out_path


if __name__ == "__main__":
    try:
        build_report()
    except ReportSourceError as e:
        logger.error("REPORT BUILD FAILED: %s", e)
        sys.exit(1)
