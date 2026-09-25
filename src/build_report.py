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
import os
import sys
from datetime import datetime

import pandas as pd
import yaml

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
STALENESS_THRESHOLD_DAYS = 7  # METRICS.md Sec.26

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
    ontime = ontime[ontime["year"].isin([2023, 2024, 2025, 2026])].sort_values("year")
    if ontime.empty:
        raise ReportSourceError("delivery_by_year.csv has no rows for 2023-2026.")

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

    sig = load_csv("b3_paired_significance.csv", "Results §6 significance statement")
    for col in ["approach_a", "approach_b", "paired_t_stat", "mean_diff_b_minus_a"]:
        require_col(sig, col, "b3_paired_significance.csv", "significance statement")
    sig_row = sig[(sig["approach_a"] == "Direct") & (sig["approach_b"] == "Top-down")]
    if sig_row.empty:
        raise ReportSourceError("b3_paired_significance.csv has no Direct-vs-Top-down row.")

    return {
        "per_division": per_division,
        "rolling_type": rolling_type,
        "sig_row": sig_row.iloc[0],
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


def gather_usable_range_end(config: dict) -> str:
    """Last calendar month ACTUALLY PRESENT in the pipeline's own monthly series -- replaces the
    hand-maintained config.yaml date_range.end (STATUS.md Sec.10 item 3 / manual_factsheet.md
    Part 5 item 3: that value had gone stale). date_range.start remains config -- it is real
    project-wide filtering (used by src/load_data_full.py and others), never just display."""
    path = os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")
    if not os.path.exists(path):
        raise ReportSourceError(
            f"Required source file missing: {path} (needed to derive the Usable range end date). "
            f"Run src/load_data_full.py first."
        )
    df = pd.read_csv(path, usecols=["year_month"])
    if df.empty:
        raise ReportSourceError(f"{path} has no rows -- cannot derive the usable range end date.")
    return str(df["year_month"].max())


def gather_freshness() -> dict:
    """data_pulled_at per section, cited to the exact file/column it comes from (never typed),
    per METRICS.md Sec.26. Multiple source files feed this one page at different ages -- the
    headline `data_pulled_at` is the OLDEST of them (a page is only as fresh as its stalest
    input), with every section's own date reported alongside so nothing is hidden."""
    monthly_path = os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")
    monthly = pd.read_csv(monthly_path, usecols=["snapshot_pull_date"])
    main_pull = str(monthly["snapshot_pull_date"].iloc[0])

    sections = {
        "หลัก (forecast/actual, scope, ช่วงข้อมูล) -- snapshot_pull_date":
            main_pull,
        "ตารางผลลัพธ์ต่อฝ่าย (phaseC_step2_transferability_per_division.csv / "
        "phaseC_step2_per_division_summary_qty.csv) -- snapshot_pull_date":
            _source_pull_date("phaseC_step2_per_division_summary_qty.csv"),
        "Rolling-origin chart (phaseC_step2_rolling_origin_qty.csv) -- snapshot_pull_date":
            _source_pull_date("phaseC_step2_rolling_origin_qty.csv"),
        "Notice-period chart (leadtime_notice_buckets_overall.csv) -- snapshot_pull_date":
            _source_pull_date("leadtime_notice_buckets_overall.csv"),
        "โมเดลพื้นฐาน chart (focus_items_test_all.csv) -- snapshot_pull_date":
            _source_pull_date("focus_items_test_all.csv"),
        "On-time exact (delivery_by_year.csv) -- snapshot_pull_date":
            _source_pull_date("delivery_by_year.csv"),
        "Not-late (delivery_not_late_by_year.csv) -- snapshot_pull_date, itself read forward "
        "from the same Cube_CES pull as the on-time chart above (no new DB call)":
            _source_pull_date("delivery_not_late_by_year.csv"),
    }
    data_pulled_at_min = min(sections.values())
    return {"sections": sections, "data_pulled_at_min": data_pulled_at_min}


def gather_primary_results() -> pd.DataFrame:
    """Per-division Top-down rolling-origin figures (MAE/RMSE/Bias/MASE/n_scored) -- item-level,
    the Top-down method this project actually adopted (STATUS.md Locked Decisions, "Final
    forecasting method"), NOT the Type-level/Combination-only secondary table below. Source:
    src/transferability_all_divisions.py (item-level rolling-origin scoring at every one of the
    project's standard 7 origins), aggregated into
    output/summary/phaseC_step2_transferability_per_division.csv, documented in
    output/summary/phaseC_step2_report.md Part 3 (confirmed this task by reading both the
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
    return df[df["year"].isin([2023, 2024, 2025, 2026])].sort_values("year")


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
    usable_range_end = gather_usable_range_end(config)
    freshness = gather_freshness()
    backtest_window = gather_backtest_window(primary_results, results["per_division"])

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
        f"<tr><td>{html.escape(label)}</td><td>{value}</td>"
        f"<td>{f'⚠ เก่ากว่า {STALENESS_THRESHOLD_DAYS} วัน ({section_ages[label]} วัน)' if label in stale_sections else 'ทันสมัย (ok)'}</td></tr>"
        for label, value in freshness["sections"].items()
    )
    staleness_html = (
        f"""<p class="note-box"><b>⚠ บางส่วนของหน้านี้ใช้ข้อมูลเก่ากว่า {STALENESS_THRESHOLD_DAYS} วัน (ประเมินแยกทีละส่วน):</b>
        {"; ".join(html.escape(s) for s in stale_sections)} — ส่วนอื่นของหน้านี้ที่ไม่อยู่ในรายการนี้
        ยังคงใช้ข้อมูลที่ทันสมัย (ไม่ถือว่าทั้งหน้าเก่าเพียงเพราะส่วนใดส่วนหนึ่งเก่า, METRICS.md §26)</p>"""
        if stale_sections else ""
    )
    timestamps_html = f"""
    <details class="note-box" style="margin:10px 0">
      <summary style="cursor:pointer"><b>data_pulled_at:</b> {data_pulled_at} {ICT_LABEL}
        (เก่าที่สุดในหน้านี้, ดูรายละเอียดต่อส่วนด้านล่าง) &nbsp;|&nbsp; <b>page_built_at:</b> {page_built_at} {ICT_LABEL}
        &nbsp;<!-- source: src/build_report.py gather_freshness()/datetime.now(), this build run --></summary>
      <table class="report-table" style="margin-top:8px">
        <thead><tr><th>ส่วนของหน้า / แหล่งข้อมูล</th><th>data_pulled_at (snapshot_pull_date)</th><th>สถานะ (ประเมินแยกทีละส่วน)</th></tr></thead>
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

    ontime_2026_val = biz["ontime_by_year"][biz["ontime_by_year"]["year"] == 2026]["pct_on_time"].iloc[0]

    # ---- Section 1: Executive summary ----
    sec1 = f"""
    <section id="exec-summary">
      <h2>1. บทสรุปผู้บริหาร (Executive Summary)</h2>
      <p>{html.escape(report['model_description'])}</p>
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
        อัตราการส่งมอบตรงเวลาปรับตัวขึ้นจาก 57.8% (2023) เป็น
        <b>{fmt_num(ontime_2026_val, 1)}%</b> ในปี 2026 (ข้อมูลบางส่วน)
      </p>
    </section>"""

    # ---- Section 2: Scope ----
    scope_rows = "".join(
        f"<tr><td>{div}</td><td>{cite('phaseC_step1revised_item_status_445.csv', 'status_category')}{int(row['forecast'])}</td>"
        f"<td>{int(row['placeholder'])}</td><td>{int(row['excluded'])}</td><td>{int(row.sum())}</td></tr>"
        for div, row in scope_table.iterrows()
    )
    sec2 = f"""
    <section id="scope">
      <h2>2. ขอบเขตข้อมูล (Scope)</h2>
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
      <h2>3. ข้อค้นพบทางธุรกิจ (Business Findings)</h2>
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
      <h3>สัดส่วนส่งมอบตรงวันครบกำหนดเป๊ะ vs. ส่งไม่ล่าช้า (2023-2026)</h3>
      <p class="hint">
        <b>on_time_exact</b> = ส่งมอบตรงวันครบกำหนดพอดี (PlanDelDate), นับตามจำนวนออเดอร์ (row-weighted),
        ขอบเขต PEM101 128 รายการ — <code>src/investigations/delivery_performance.py:71-75</code>
        (<code>classify_delay</code>) และบรรทัด 155-161 (<code>by_year</code> aggregation, คอลัมน์
        <code>pct_on_time</code>) &mdash; METRICS.md §19 ห้ามใช้ตัวเลขนี้เป็น fill-rate benchmark
        เพียงลำพัง (เหตุการณ์ 73.2% เดิม) จึงแสดง <b>not_late</b> ควบคู่กัน<br>
        <b>not_late</b> = ส่งมอบตรงหรือก่อนกำหนด (ForecastDelDate), <b>ถ่วงน้ำหนักตามจำนวนหน่วย
        (unit-weighted, ActualQty)</b> ไม่ใช่ตามจำนวนออเดอร์ — เลือกใช้ unit-weighted เพราะ
        METRICS.md §10 (fill_rate) นิยามเป็น unit-based ไม่ใช่ order-based โดยตรง และเลขนี้ควรอ่าน
        คู่กับ fill_rate/service-level ของโครงการ ไม่ใช่สัดส่วนนับออเดอร์
        (<code>src/investigations/task2a_delivery_notlate_by_year.py</code>, คำนวณจากข้อมูล
        Cube_CES ชุดเดียวกับ on_time_exact ไม่ได้ดึงข้อมูลใหม่)
      </p>
      {cite('delivery_by_year.csv', 'year / pct_on_time')}
      {cite('delivery_not_late_by_year.csv', 'year / not_late_pct_unit_weighted')}
      <div id="chart-ontime" class="plotly-chart"></div>
    </section>"""

    # ---- Section 4: Data ----
    sec4 = f"""
    <section id="data">
      <h2>4. ข้อมูลที่ใช้ (Data)</h2>
      <table class="report-table">
        <tbody>
          <tr><td>แหล่งข้อมูล (Source table)</td><td>{cite_config('source_table')}<code>{html.escape(str(config['source_table']))}</code></td></tr>
          <tr><td>ช่วงข้อมูลที่ใช้ได้ (Usable range)</td><td>{cite_config('date_range.start')}<!-- source: output/data/processed_full_category_sales_monthly_forecastDate.csv, column year_month (max) -->{config['date_range']['start']} — {usable_range_end}
            <span class="hint">(เดือนสุดท้ายที่มีข้อมูลจริง คำนวณตอน build — ไม่ใช่ค่าที่พิมพ์ไว้ใน config.yaml อีกต่อไป)</span></td></tr>
          <tr><td>Split lots</td><td>รายการที่ดูเหมือนซ้ำแต่เป็นการแบ่งส่งมอบจริง (split lots) ยังคงเก็บไว้ทั้งหมด ไม่ถูกลบออก (STATUS.md, Locked Decisions)</td></tr>
          <tr><td>MPS retained</td><td>สถานะ MPS (PO ที่รับแล้ว รอส่งมอบ) ถือเป็นยอดขายที่ยืนยันแล้ว (confirmed demand) ต้องไม่ถูกตัดออกจากการพยากรณ์ (STATUS.md, Locked Decisions)</td></tr>
          <tr><td>forecast_date keying</td><td>Series การพยากรณ์ใช้ forecast_date (วันที่ส่งมอบตามสัญญา) เป็น key แบบ frozen snapshot ไม่ query สดทุกครั้ง (STATUS.md, Locked Decisions)</td></tr>
          <tr><td>Pricelist as division source</td><td>Price List คือแหล่งอ้างอิงหลักของฝ่าย (division) ของสินค้า ไม่ใช้คอลัมน์ division ในฐานข้อมูลกรองข้อมูล (STATUS.md, CONVENTIONS.md)</td></tr>
        </tbody>
      </table>
    </section>"""

    # ---- Section 5: Model (Plotly, legend-toggle bar chart) ----
    sec5 = f"""
    <section id="model">
      <h2>5. โมเดลพยากรณ์ (Model)</h2>
      <p>{html.escape(report['model_description'])}</p>
      <p>{html.escape(report['why_not_single_model'])}</p>
      <p>{html.escape(report['why_not_ml'])}</p>
      <h3>MAE ของโมเดลพื้นฐาน 6 แบบ เทียบกับ Combination และ Top-down (3 focus codes)</h3>
      <p class="hint">คลิกที่ legend เพื่อซ่อน/แสดงแต่ละโมเดล</p>
      {cite('focus_items_test_all.csv', 'model / MAE')}
      <div id="chart-model" class="plotly-chart"></div>
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

    sig = results["sig_row"]
    sec6 = f"""
    <section id="results">
      <h2>6. ผลลัพธ์ (Results)</h2>
      <p class="hint">
        {cite('phaseC_step2_transferability_per_division.csv', 'first_test_month / last_test_month')}
        <b>หน้าต่างทดสอบ backtest (rolling-origin, {backtest_window['n_origins']} origins):</b>
        เดือนทดสอบตั้งแต่ <b>{backtest_window['first_test_month']}</b> ถึง <b>{backtest_window['last_test_month']}</b>
        (METRICS.md §39 -- ทุกตัวเลข MAE/RMSE/Bias/MASE ด้านล่างนี้มาจากช่วงหน้าต่างนี้)
      </p>
      <div class="controls">
        <label>ฝ่าย (Division): <select id="filterDivision"><option value="__all__">ทั้งหมด</option>{div_options}</select></label>
        <label>ประเภท (Type): <select id="filterType"><option value="__all__">ทั้งหมด</option></select></label>
      </div>
      <h3>PRIMARY — MAE / RMSE / Bias / MASE ต่อฝ่าย, วิธี Top-down ระดับรายการสินค้า (item-level, rolling-origin)</h3>
      <p class="hint">
        นี่คือวิธี <b>Top-down</b> ที่โครงการนำมาใช้จริง (STATUS.md Locked Decisions, "Final
        forecasting method") — พยากรณ์ที่ระดับ Type แล้วปันส่วนลงระดับรายการสินค้าตามส่วนแบ่งยอด
        ขายย้อนหลัง คำนวณใหม่ทุก rolling origin (ไม่ใช่ปันส่วนแบบตายตัวครั้งเดียว), ให้คะแนนที่
        <b>ระดับรายการสินค้าแต่ละชิ้น</b> ทั้ง 7 origins มาตรฐานของโครงการ —
        <code>src/transferability_all_divisions.py</code>, สรุปที่
        <code>output/summary/phaseC_step2_transferability_per_division.csv</code>
        (ดูรายละเอียดวิธีที่ <code>output/summary/phaseC_step2_report.md</code> Part 3)
      </p>
      {cite('phaseC_step2_transferability_per_division.csv', 'MAE / RMSE / Bias / MASE / n_scored')}
      <!-- filtered to rows where approach == 'Top-down' -->
      <table class="report-table" id="primary-results-table">
        <thead><tr><th>ฝ่าย</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>MASE</th><th>n_scored (item × origin)</th></tr></thead>
        <tbody></tbody>
      </table>
      <h3>SECONDARY — MAE / RMSE / MASE / Bias ต่อฝ่าย, วิธี Combination ระดับ Type เท่านั้น (ค่าเฉลี่ยข้าม Type และ origin)</h3>
      <p class="hint">
        <b>ตารางนี้ไม่ใช่วิธี Top-down ที่โครงการนำมาใช้</b> — เป็นตัวเลขโมเดล
        <b>Combination เท่านั้น</b> ที่ระดับ <b>Type</b> (ไม่ใช่ระดับรายการสินค้า), เฉลี่ยข้ามทุก
        Type และทั้ง 7 rolling origins ต่อฝ่าย — <code>src/backtest_all_divisions.py:126-139</code>
        (ค้นพบ/เปิดเผยครั้งแรก: <code>output/summary/manual_factsheet.md</code> Part 5 ข้อ 2)
        เก็บไว้เพื่อเทียบเคียง ไม่ใช่ตารางหลักอีกต่อไป
      </p>
      {cite('phaseC_step2_per_division_summary_qty.csv', 'MAE / RMSE / Bias / MASE / n_items')}
      <table class="report-table" id="div-results-table">
        <thead><tr><th>ฝ่าย</th><th>MAE</th><th>RMSE</th><th>MASE</th><th>Bias</th><th>จำนวนสินค้า</th></tr></thead>
        <tbody></tbody>
      </table>
      <h3>Rolling-origin MAE (Type level) — คลิก legend เพื่อซ่อน/แสดงแต่ละโมเดล</h3>
      {cite('phaseC_step2_rolling_origin_qty.csv', 'origin / model / MAE')}
      <div id="chart-rolling" class="plotly-chart"></div>
      <h3>Forecast เทียบกับ Actual — เลือกสินค้าและ rolling origin</h3>
      <p class="scope-note">ขอบเขตของกราฟนี้: สินค้ากลุ่มนำร่อง PEM101 ({len(fva_items)} รหัส, Fuse Cutout + Surge Arrester)
        — มาตรฐาน 7 rolling origins แบบเดียวกับที่ใช้ทั่วทั้งโครงการ (get_origins(31,6), src/backtest_rekeyed.py),
        ไม่ใช่ 9 origins แบบเดิม (ดูหมายเหตุด้านล่าง)</p>
      <div class="controls">
        <label>Rolling origin: <select id="filterOrigin">{"".join(f'<option value="{o}">{o}</option>' for o in range(1, 8))}</select></label>
      </div>
      <div class="item-check-list">{item_checkboxes}</div>
      {cite('report_item_forecast_vs_actual_by_origin.csv', 'origin / month_in_horizon / actual_qty / forecast_qty')}
      <div id="chart-fva" class="plotly-chart"></div>
      <p class="note-box">
        <b>หมายเหตุเกี่ยวกับแกน X เดิม (1-9):</b> กราฟเดิมใช้ข้อมูลจาก
        <code>phaseE1_2_rolling_origin_cumulative.csv</code> ซึ่งคำนวณจาก rolling-origin scheme
        ของ Phase E1.2 เอง (protection period 4 เดือน) ทำให้ได้ 9 origins ไม่ใช่ 7 origins ตาม
        rolling-origin evaluation มาตรฐานของโครงการ (6-month holdout) และแสดงเฉพาะ actual
        ไม่มีเส้น forecast เปรียบเทียบ กราฟด้านบนนี้คำนวณใหม่ด้วย scheme มาตรฐาน 7 origins
        (src/build_report_data.py) และแสดงทั้ง forecast และ actual
      </p>
      <p>
        {cite('b3_paired_significance.csv', 'paired_t_stat')}
        <b>ข้อค้นพบที่บันทึกไว้ (recorded finding):</b> ความได้เปรียบของ Top-down เทียบกับ Direct
        ไม่มีนัยสำคัญทางสถิติ (paired t = {fmt_num(sig['paired_t_stat'], 3)}, |t| &lt; 2, ค่าความ
        แตกต่างเฉลี่ย {fmt_num(sig['mean_diff_b_minus_a'], 2)}) — เลือกใช้ Top-down เพราะเป็น
        แนวทางที่ตรงไปตรงมาที่สุดในเชิงโครงสร้าง ไม่ใช่เพราะพิสูจน์แล้วว่าแม่นยำกว่าอย่างมี
        นัยสำคัญ
      </p>
    </section>"""

    # ---- Section 7: Limitations ----
    limitations_html = "".join(f"<li>{html.escape(x)}</li>" for x in report["limitations"])
    sec7 = f"""
    <section id="limitations">
      <h2>7. ข้อจำกัด (Limitations)</h2>
      <ul>{limitations_html}</ul>
    </section>"""

    # ---- Section 8: Next steps ----
    next_steps_html = "".join(f"<li>{html.escape(x)}</li>" for x in report["next_steps"])
    sec8 = f"""
    <section id="next-steps">
      <h2>8. ขั้นตอนต่อไป (Next Steps)</h2>
      <ul>{next_steps_html}</ul>
    </section>"""

    controls_note = f"""
    <div class="controls-note">
      <b>หมายเหตุ:</b> ตัวควบคุมบนหน้านี้ (Division/Type/Item/Origin selectors, legend toggles)
      เปลี่ยนเฉพาะ<b>มุมมองที่แสดง</b> ไม่ได้เปลี่ยนตัวโมเดลหรือค่าพยากรณ์ที่คำนวณไว้แล้ว —
      การเปลี่ยนแปลงเชิงโครงสร้าง (เช่น พารามิเตอร์ Tier B: base models, combination method,
      scope, series key, aggregation level) ต้องแก้ไขที่ <code>config.yaml</code> และรัน
      pipeline ใหม่ ตามการจัดกลุ่มพารามิเตอร์ Tier A/B/C ที่บันทึกไว้ใน <code>config.yaml</code>
      <!-- source: config.yaml, comment block "Three-tier parameter classification" (Tier A/B/C) -->
      (ดู <code>config.yaml</code> — comment block "Three-tier parameter classification")
    </div>"""

    body = sec1 + sec2 + sec3 + sec4 + sec5 + controls_note + sec6 + sec7 + sec8

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
  p.hint, p.scope-note {{ font-size: 12px; color: var(--muted); }}
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
  .controls {{ display:flex; gap:16px; flex-wrap:wrap; margin: 10px 0; font-size:13px; }}
  .controls select {{ margin-left:4px; padding:3px 6px; }}
  .controls-note {{ background:#eef4fb; border:1px solid var(--border); border-radius:6px;
    padding:10px 12px; font-size:12.5px; margin: 20px 0; }}
  .item-check-list {{ display:flex; gap:12px; flex-wrap:wrap; margin: 6px 0; font-size:12.5px; }}
  label.item-check {{ background:#f0efec; border-radius: 4px; padding: 2px 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back-link" href="../index.html">&larr; กลับหน้าหลัก</a>
  <h1>รายงานการพยากรณ์ยอดขาย (Sales Forecast Report) — PEM Group</h1>
  <p style="color:var(--text-secondary);font-size:12px;">
    สร้างโดย src/build_report.py — ทุกตัวเลขมีที่มาระบุไว้ในซอร์สโค้ด HTML (ดู &lt;!-- source: ... --&gt;)
  </p>
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
</body>
</html>"""


def render_client_js() -> str:
    """Vanilla JS (no framework) that reads #report-data, wires up the controls in Section 6,
    and draws every Plotly chart. Kept as a plain <script> block, consistent with this project's
    'no separate build toolchain' style (CONVENTIONS.md doesn't require a JS bundler and this
    project has never used one)."""
    return """
const REPORT_DATA = JSON.parse(document.getElementById('report-data').textContent);
const MODEL_COLORS = """ + json.dumps(MODEL_COLORS) + """;
const PLOT_CONFIG = {responsive: true, displaylogo: false};
const LAYOUT_BASE = {
  font: {family: 'system-ui, sans-serif', size: 12, color: '#0b0b0b'},
  margin: {l: 50, r: 20, t: 10, b: 40},
  paper_bgcolor: '#fcfcfb', plot_bgcolor: '#fcfcfb',
  legend: {orientation: 'h', y: -0.25}
};

function drawNotice() {
  Plotly.newPlot('chart-notice', [{
    x: REPORT_DATA.notice.labels, y: REPORT_DATA.notice.values, type: 'bar',
    marker: {color: '#eb6834'}, hovertemplate: '%{x}: %{y:.1f}%<extra></extra>'
  }], Object.assign({}, LAYOUT_BASE, {yaxis: {title: '% ของออเดอร์'}}), PLOT_CONFIG);
}

function drawOntime() {
  Plotly.newPlot('chart-ontime', [
    {
      x: REPORT_DATA.ontime.years, y: REPORT_DATA.ontime.values, type: 'scatter', mode: 'lines+markers',
      name: 'on_time_exact (row-weighted)', line: {color: '#2a78d6'},
      hovertemplate: '%{x}: %{y:.1f}%<extra>on_time_exact</extra>'
    },
    {
      x: REPORT_DATA.notlate.years, y: REPORT_DATA.notlate.values, type: 'scatter', mode: 'lines+markers',
      name: 'not_late (unit-weighted)', line: {color: '#1baf7a'},
      hovertemplate: '%{x}: %{y:.1f}%<extra>not_late</extra>'
    }
  ], Object.assign({}, LAYOUT_BASE, {yaxis: {title: '%'}}), PLOT_CONFIG);
}

function drawModelChart() {
  const items = REPORT_DATA.focus_items;
  const models = REPORT_DATA.base_models.concat(['Combination', 'Top-down']);
  const traces = models.map(m => ({
    x: items, y: items.map(it => REPORT_DATA.model_bar[m][it]), type: 'bar', name: m,
    marker: {color: MODEL_COLORS[m]}, hovertemplate: '%{x}<br>' + m + ': %{y:.1f}<extra></extra>'
  }));
  Plotly.newPlot('chart-model', traces, Object.assign({}, LAYOUT_BASE, {barmode: 'group', yaxis: {title: 'MAE'}}), PLOT_CONFIG);
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
    {xaxis: {title: 'Rolling origin', dtick: 1}, yaxis: {title: 'Mean MAE'}}), PLOT_CONFIG);
}

function selectedFvaItems() {
  return [...document.querySelectorAll('.fva-item:checked')].map(cb => cb.value);
}

function drawFvaChart() {
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
    {xaxis: {title: 'Month in horizon (origin ' + origin + ')', dtick: 1}, yaxis: {title: 'Quantity'}}), PLOT_CONFIG);
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
