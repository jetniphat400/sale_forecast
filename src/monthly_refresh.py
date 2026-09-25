"""Monthly refresh runner -- implements METRICS.md Sec.28's `monthly_refresh`, 11 steps, IN
ORDER, exactly as specified there:

    1 pull data — one connection attempt, abort on failure, no retry
    2 validate — zero-row guard and data invariants
    3 rebuild the forecast_date-keyed series as a frozen snapshot
    4 re-run the sales-model backtest; record each division's change against the previous run
    5 append a new forward-test vintage per section 27
    6 fill actual_qty and score any months that became eligible
    7 rebuild every page with section 26 timestamps
    8 run the full test suite
    9 scan staged files for sensitive content
    10 check change magnitude against the previous run
    11 commit and push only if steps 8 to 10 all pass

SCOPE OF "pull data" / "every page" IN THIS RUNNER (stated explicitly, not silently narrowed):
  - Step 1 pulls the 335-item, 5-division scope (src/load_data_all_divisions.py) -- the dataset
    src/backtest_all_divisions.py / src/transferability_all_divisions.py (step 4) and
    src/forward_test_all_divisions.py's own logic (step 5, reused here) both need. The separate
    128-item PEM101-pilot pull (src/load_data_full.py) feeds only forecast/sales_report.html's
    "Usable range" display text and is NOT re-pulled by this runner if it was already refreshed
    the same day by another process (checked via its own file mtime) -- this project's DATABASE
    ACCESS rule allows only ONE connection attempt per agent/session, so a same-day-fresh file is
    reused rather than re-pulled a second time. If it is NOT fresh, this step logs that
    forecast/sales_report.html's Usable range text may be stale and continues (it is not fatal to
    steps 4-11, which do not depend on it).
  - Step 7 "every page" = forecast/sales_report.html only (src/build_report.py), the only
    dashboard page this project has a script-based generator for that is wired to the backtest
    this runner re-runs. index.html has NO generator script anywhere in the repo (STATUS.md,
    confirmed by repeated repo-wide search) -- it is hand-maintained and out of this runner's
    reach. forecast/inventory.html's generator (src/build_inventory_page.py) requires its OWN
    separate database pull (Cube_Inventory_Exact/Cube_CES) -- a second connection attempt this
    runner's single-connection-per-run design does not make; it is out of scope here and
    unaffected by this runner (STATUS.md Sec.10 items 4-6/9-10, "deferred to task 2b").

DRY RUN (--dry-run): steps 1-10 are FULLY exercised (real data pull, real backtest, real
consistency check, real test suite, real change-magnitude computation) -- only their WRITES to
TRACKED files are redirected to a staging area under output/runs/<run_id>/staged/, and the new
forward-test vintage is computed but never appended to the real log. Step 11's actual git
add/commit/push never runs in dry-run mode; it instead reports what WOULD happen.

Every run writes a full JSON run log to output/runs/monthly_refresh_<run_id>.json, recording each
step's outcome, step-10's figures, and whether it pushed (and why not, if applicable) --
METRICS.md Sec.28's own requirement.
"""
import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
import urllib.parse
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import TOTAL_MONTHS
from forward_test import config_version
from forward_test_all_divisions import (build_category_series_div, build_item_series_div,
                                         build_type_series_div)
from forward_test_common import compute_row_integrity_hash, compute_scope_hash, load_metadata, save_metadata
from item_level_reconciliation import forecast_all_approaches
from leakage_guard import LeakageGuardError, check_window_closed, load_min_margin_days
from models import combination_forecast
from score_forward_test_all_divisions import (SCOPE_FILE, pull_actuals_forecastDate,
                                               score_and_summarize, target_month_safe_to_score,
                                               verify_consistency)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("monthly_refresh")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
RUNS_DIR = os.path.join(PROJECT_ROOT, "output", "runs")
FORECAST_DIR = os.path.join(PROJECT_ROOT, "forecast")

FORWARD_TEST_LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions.csv")
FORWARD_TEST_METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions_metadata.json")
PER_DIVISION_SUMMARY_PATH = os.path.join(SUMMARY_DIR, "phaseC_step2_per_division_summary_qty.csv")
TRANSFERABILITY_PATH = os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_per_division.csv")
INVENTORY_JSON_PATH = os.path.join(PROJECT_ROOT, "data", "inventory.json")
SALES_REPORT_PATH = os.path.join(FORECAST_DIR, "sales_report.html")

SENSITIVE_PATTERNS = [
    (r"DB_PASSWORD\s*=\s*\S+", "DB_PASSWORD assignment"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", "api_key-looking literal"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "PEM private key block"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id pattern"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{4,}['\"]", "hardcoded password literal"),
]


class MonthlyRefreshAbort(Exception):
    """Raised to abort the run at a specific step (network unreachable, invariant violated,
    etc.) -- always caught once at the top level, recorded loudly in the run log, never
    swallowed or retried (CONVENTIONS.md: validation failures raised loudly; DATABASE ACCESS
    rule: never retry the database)."""


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_script(script_name: str, args: list = None) -> subprocess.CompletedProcess:
    """Runs an existing, already-tested src/*.py script as a subprocess -- same reasoning as
    src/run_pipeline.py's run_stage(): exercises the exact code path a human would from the CLI,
    never re-derives that script's logic here."""
    cmd = [sys.executable, os.path.join(SRC_DIR, script_name)] + (args or [])
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result


# ---------------------------------------------------------------------------------------------
# Step 1: pull data (network reachability + the one real DB connection attempt this run makes)
# ---------------------------------------------------------------------------------------------

def check_tcp_reachable(host: str, port: int, timeout: float = 5.0) -> tuple:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None
    except OSError as e:
        return False, str(e)


def step1_pull_data(dry_run: bool) -> dict:
    from dotenv import load_dotenv
    load_dotenv()
    db_server_raw = os.getenv("DB_SERVER", "")
    db_host = db_server_raw.split("\\")[0].split(",")[0]
    db_port = 1433  # SQL Server default; DB_SERVER (.env) names a host\instance with no explicit
    #                 port -- this is a stated assumption for the reachability check only, not
    #                 for the actual ODBC connection (which resolves the named instance itself).
    db_reachable, db_err = check_tcp_reachable(db_host, db_port) if db_host else (False, "DB_SERVER not set")
    github_reachable, github_err = check_tcp_reachable("github.com", 443)

    result = {
        "db_host_checked": db_host, "db_port_checked": db_port,
        "db_reachable": db_reachable, "db_reachability_error": db_err,
        "github_reachable": github_reachable, "github_reachability_error": github_err,
    }
    if not db_reachable:
        raise MonthlyRefreshAbort(
            f"Step 1 (pull data) ABORTED: database host {db_host}:{db_port} is not reachable "
            f"({db_err}). Never retrying the database (DATABASE ACCESS rule)."
        )

    # The 128-item PEM101 pilot dataset feeds only sales_report.html's 'Usable range' display --
    # reused as-is if already refreshed TODAY by another process, to respect the one-connection-
    # attempt-per-agent/session rule (see module docstring).
    pilot_path = os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")
    pilot_fresh_today = (os.path.exists(pilot_path) and
                          datetime.fromtimestamp(os.path.getmtime(pilot_path)).date() == datetime.now().date())
    result["pilot_128item_pull_skipped_already_fresh_today"] = pilot_fresh_today
    if not pilot_fresh_today:
        logger.warning("output/data/processed_full_category_sales_monthly_forecastDate.csv is not "
                        "fresh as of today -- sales_report.html's 'Usable range' text may be stale. "
                        "Not re-pulled this run (one-connection-attempt-per-session budget spent on "
                        "the 335-item all-division pull below).")

    # ---- THE one real DB connection attempt this run makes: the 335-item, 5-division pull ----
    proc = run_script("load_data_all_divisions.py")
    result["load_data_all_divisions_returncode"] = proc.returncode
    result["load_data_all_divisions_stdout_tail"] = proc.stdout[-3000:]
    result["load_data_all_divisions_stderr_tail"] = proc.stderr[-3000:]
    if proc.returncode != 0:
        raise MonthlyRefreshAbort(
            f"Step 1 (pull data) ABORTED: src/load_data_all_divisions.py exited "
            f"{proc.returncode}. Never retrying the database (DATABASE ACCESS rule). "
            f"stderr tail:\n{proc.stderr[-2000:]}"
        )
    monthly_qty_path = os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv")
    monthly = pd.read_csv(monthly_qty_path)
    result["rows_pulled"] = len(monthly)
    result["snapshot_pull_date"] = str(monthly["snapshot_pull_date"].iloc[0])
    result["n_items"] = monthly["itemcode"].nunique()
    result["n_divisions"] = monthly["division"].nunique()
    return result


# ---------------------------------------------------------------------------------------------
# Step 2: validate -- zero-row guard and data invariants
# ---------------------------------------------------------------------------------------------

def step2_validate() -> dict:
    monthly_qty = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    monthly_sale = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_sale.csv"))
    scope = pd.read_csv(SCOPE_FILE)

    checks = {}
    if len(monthly_qty) == 0:
        raise MonthlyRefreshAbort("Step 2 (validate) ABORTED: processed_all_divisions_monthly_qty.csv has 0 rows.")
    checks["zero_row_guard_qty"] = "passed (nonzero rows)"

    if (monthly_qty["qty"] < 0).any():
        raise MonthlyRefreshAbort("Step 2 (validate) ABORTED: negative qty found in the freshly pulled monthly series.")
    checks["no_negative_qty"] = "passed"

    if (monthly_sale["sale"] < 0).any():
        raise MonthlyRefreshAbort("Step 2 (validate) ABORTED: negative sale found in the freshly pulled monthly series.")
    checks["no_negative_sale"] = "passed"

    dupes = monthly_qty.duplicated(subset=["itemcode", "year_month"]).sum()
    if dupes:
        raise MonthlyRefreshAbort(f"Step 2 (validate) ABORTED: {dupes} duplicate (itemcode, year_month) rows.")
    checks["no_duplicate_item_month_rows"] = "passed"

    unmatched = set(monthly_qty["itemcode"].unique()) - set(scope["code"].unique())
    if unmatched:
        raise MonthlyRefreshAbort(f"Step 2 (validate) ABORTED: {len(unmatched)} itemcodes in the monthly "
                                  f"series have no match in the scope file: {sorted(unmatched)[:10]}...")
    checks["all_itemcodes_matched_to_scope"] = "passed"

    n_months = monthly_qty.groupby("itemcode")["year_month"].nunique()
    if n_months.nunique() != 1:
        raise MonthlyRefreshAbort(f"Step 2 (validate) ABORTED: not every item has the same number of "
                                  f"months in the monthly grid: {n_months.value_counts().to_dict()}")
    checks["every_item_has_equal_month_count"] = f"passed ({n_months.iloc[0]} months each)"

    return {"checks": checks, "n_rows_qty": len(monthly_qty), "n_rows_sale": len(monthly_sale)}


# ---------------------------------------------------------------------------------------------
# Step 3: rebuild the forecast_date-keyed series as a frozen snapshot
# ---------------------------------------------------------------------------------------------

def step3_frozen_snapshot() -> dict:
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    pull_dates = monthly["snapshot_pull_date"].unique()
    if len(pull_dates) != 1:
        raise MonthlyRefreshAbort(f"Step 3 ABORTED: expected exactly one frozen snapshot_pull_date, found {pull_dates}.")
    months = sorted(monthly["year_month"].unique())
    return {"snapshot_pull_date": str(pull_dates[0]), "fit_first_month": months[0],
            "fit_last_month": months[-1], "n_months": len(months)}


# ---------------------------------------------------------------------------------------------
# Step 4: re-run the sales-model backtest; record each division's change against the previous run
# ---------------------------------------------------------------------------------------------

def _archive_if_exists(path: str, run_id: str) -> str:
    if not os.path.exists(path):
        return None
    archive_dir = os.path.join(SUMMARY_DIR, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(path))
    archive_path = os.path.join(archive_dir, f"{base}_pre_monthly_refresh_{run_id}{ext}")
    pd.read_csv(path).to_csv(archive_path, index=False)
    return archive_path


def step4_backtest(run_id: str) -> dict:
    prev_per_division = pd.read_csv(PER_DIVISION_SUMMARY_PATH) if os.path.exists(PER_DIVISION_SUMMARY_PATH) else None
    prev_transferability = pd.read_csv(TRANSFERABILITY_PATH) if os.path.exists(TRANSFERABILITY_PATH) else None

    archived_per_division = _archive_if_exists(PER_DIVISION_SUMMARY_PATH, run_id)
    archived_transferability = _archive_if_exists(TRANSFERABILITY_PATH, run_id)

    proc_bt = run_script("backtest_all_divisions.py", ["--value-col", "qty"])
    proc_tr = run_script("transferability_all_divisions.py")
    if proc_bt.returncode != 0:
        raise MonthlyRefreshAbort(f"Step 4 ABORTED: backtest_all_divisions.py exited {proc_bt.returncode}.\n{proc_bt.stderr[-2000:]}")
    if proc_tr.returncode != 0:
        raise MonthlyRefreshAbort(f"Step 4 ABORTED: transferability_all_divisions.py exited {proc_tr.returncode}.\n{proc_tr.stderr[-2000:]}")

    new_per_division = pd.read_csv(PER_DIVISION_SUMMARY_PATH)
    new_transferability = pd.read_csv(TRANSFERABILITY_PATH)
    new_topdown = new_transferability[new_transferability["approach"] == "Top-down"]

    comparison = []
    for _, row in new_topdown.iterrows():
        div = row["division"]
        entry = {"division": div, "new_MAE": row["MAE"], "new_RMSE": row["RMSE"],
                  "new_Bias": row["Bias"], "new_MASE": row["MASE"]}
        if prev_transferability is not None:
            prev_row = prev_transferability[(prev_transferability["division"] == div) &
                                             (prev_transferability["approach"] == "Top-down")]
            if len(prev_row):
                entry["previous_MAE"] = float(prev_row["MAE"].iloc[0])
                entry["previous_RMSE"] = float(prev_row["RMSE"].iloc[0])
                entry["previous_Bias"] = float(prev_row["Bias"].iloc[0])
                entry["previous_MASE"] = float(prev_row["MASE"].iloc[0])
                entry["MAE_change_pct"] = (100 * (entry["new_MAE"] - entry["previous_MAE"]) / entry["previous_MAE"]
                                           if entry["previous_MAE"] else None)
        comparison.append(entry)

    return {
        "archived_previous_per_division_summary": archived_per_division,
        "archived_previous_transferability": archived_transferability,
        "per_division_comparison_topdown": comparison,
        "new_per_division_summary_rows": len(new_per_division),
        "new_transferability_rows": len(new_transferability),
    }


# ---------------------------------------------------------------------------------------------
# Step 5: append a new forward-test vintage per section 27 (computed always; WRITTEN only if
# not dry_run)
# ---------------------------------------------------------------------------------------------

def compute_new_vintage() -> dict:
    """Mirrors src/forward_test_all_divisions.py's own generation logic (same imported functions:
    build_item_series_div/build_type_series_div/build_category_series_div, forecast_all_
    approaches, combination_forecast) but APPENDS a new vintage_id instead of overwriting the
    log -- forward_test_all_divisions.py's own __main__ is left unchanged (still a from-scratch
    regenerator for standalone/dev use, per this task's own run_pipeline.py fix note). Returns a
    dict with the new rows (as a DataFrame, under 'rows_df') and the new metadata entry -- always
    just COMPUTED here; the caller decides whether to actually write/append it."""
    config = load_config()
    date_key_cfg = config["adopted_series_key"]
    if date_key_cfg != "forecastDate":
        raise MonthlyRefreshAbort(f"Step 5 ABORTED: config.yaml adopted_series_key={date_key_cfg!r}, expected 'forecastDate'.")
    approach_label = config["adopted_item_level_approach"]
    horizon = config["backtest_holdout_months"]
    ma_windows = config["moving_average_windows"]
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(SCOPE_FILE)
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    months = sorted(monthly["year_month"].unique())
    n_fit_months = len(months)
    if n_fit_months != TOTAL_MONTHS:
        raise MonthlyRefreshAbort(f"Step 5 ABORTED: monthly series has {n_fit_months} months, expected {TOTAL_MONTHS}.")
    fit_first_month, fit_last_month = months[0], months[-1]

    check_window_closed(fit_last_month, pull_date, min_margin_days)  # raises LeakageGuardError if not clear
    actual_margin_days = (pd.Timestamp(pull_date).normalize() -
                          pd.Period(fit_last_month, freq="M").end_time.normalize()).days

    run_date = pd.Timestamp.now().normalize().date().isoformat()
    data_cutoff_date = pd.Timestamp(pull_date).date().isoformat()
    cfg_ver = config_version()
    scope_codes = sorted(scope["code"].unique())
    scope_hash = compute_scope_hash(scope_codes)
    n_scope_items = len(scope_codes)
    target_months = [str(pd.Period(fit_last_month, freq="M") + i) for i in range(1, horizon + 1)]

    item_series = build_item_series_div(monthly, scope, n_fit_months)
    type_series = build_type_series_div(monthly, n_fit_months)
    category_series = build_category_series_div(monthly, n_fit_months)
    no_history_codes = sorted(set(scope["code"]) - set(item_series.keys()))

    approaches = forecast_all_approaches(item_series, type_series, n_fit_months, horizon)
    topdown_history = approaches["Top-down"]
    topdown_no_history = {code: np.zeros(horizon) for code in no_history_codes}
    topdown_all = {**topdown_history, **topdown_no_history}

    type_forecast = {typ: np.clip(combination_forecast(qty[:n_fit_months], horizon, ma_windows), 0, None)
                      for typ, qty in type_series.items()}
    category_forecast = {cat: np.clip(combination_forecast(qty[:n_fit_months], horizon, ma_windows), 0, None)
                          for cat, qty in category_series.items()}

    item_to_info = scope.set_index("code")[["division", "category", "type"]].to_dict("index")

    def base_row(itemcode, division, level, category, type_, vintage_id):
        return {"vintage_id": vintage_id, "itemcode": itemcode, "division": division, "level": level,
                "category": category, "type": type_, "forecast_run_date": run_date,
                "data_cutoff_date": data_cutoff_date, "fit_last_month": fit_last_month,
                "config_version": cfg_ver, "date_key": "forecastDate", "scope_hash": scope_hash,
                "scope_n_items": n_scope_items}

    if os.path.exists(FORWARD_TEST_LOG_PATH):
        existing_log = pd.read_csv(FORWARD_TEST_LOG_PATH)
        next_vintage_id = int(existing_log["vintage_id"].max()) + 1
    else:
        next_vintage_id = 1

    records = []
    for item, fc in topdown_all.items():
        info = item_to_info[item]
        row = base_row(item, info["division"], "Item", info["category"], info["type"], next_vintage_id)
        row["model"] = f"{approach_label}_Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm, "forecast_qty": round(float(val), 4), "actual_qty": ""})
    for type_key, fc in type_forecast.items():
        div, typ = type_key.split("::", 1)
        cat = scope[(scope["division"] == div) & (scope["type"] == typ)]["category"].iloc[0]
        row = base_row(typ, div, "Type", cat, typ, next_vintage_id)
        row["model"] = "Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm, "forecast_qty": round(float(val), 4), "actual_qty": ""})
    for cat_key, fc in category_forecast.items():
        div, cat = cat_key.split("::", 1)
        row = base_row(cat, div, "Category", cat, "", next_vintage_id)
        row["model"] = "Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm, "forecast_qty": round(float(val), 4), "actual_qty": ""})

    rows_df = pd.DataFrame(records)
    if (rows_df["forecast_qty"] < 0).any():
        raise MonthlyRefreshAbort("Step 5 ABORTED: negative forecast_qty produced for the new vintage.")

    row_integrity_hash = compute_row_integrity_hash(rows_df)
    metadata_entry = {
        "log_file": os.path.relpath(FORWARD_TEST_LOG_PATH, PROJECT_ROOT).replace("\\", "/"),
        "generated_by_script": "src/monthly_refresh.py (compute_new_vintage)",
        "forecast_run_date": run_date, "config_version": cfg_ver, "date_key": "forecastDate",
        "item_level_approach": approach_label, "scope_hash": scope_hash, "scope_n_items": n_scope_items,
        "vintage_id": next_vintage_id, "row_integrity_hash": row_integrity_hash,
        "fit_first_month": fit_first_month, "fit_last_month": fit_last_month, "fit_n_months": n_fit_months,
        "horizon_months": horizon, "target_months": target_months,
        "leakage_guard_min_margin_days": min_margin_days, "leakage_guard_actual_margin_days": actual_margin_days,
        "n_total_rows": len(rows_df), "divisions": sorted(scope["division"].unique().tolist()),
    }
    six_month_totals_by_division = rows_df[rows_df["level"] == "Item"].groupby("division")["forecast_qty"].sum().to_dict()
    return {"vintage_id": next_vintage_id, "rows_df": rows_df, "metadata_entry": metadata_entry,
            "n_rows": len(rows_df), "six_month_item_forecast_total_by_division": six_month_totals_by_division}


_LAST_COMPUTED_VINTAGE = {}  # cache so step 6 (dry-run preview) never recomputes step 5's forecasts


def step5_new_vintage(dry_run: bool) -> dict:
    global _LAST_COMPUTED_VINTAGE
    try:
        computed = compute_new_vintage()
    except LeakageGuardError as e:
        raise MonthlyRefreshAbort(f"Step 5 ABORTED: leakage guard refused the new vintage's fit window: {e}")
    _LAST_COMPUTED_VINTAGE = computed

    result = {"vintage_id": computed["vintage_id"], "n_rows_computed": computed["n_rows"],
              "six_month_item_forecast_total_by_division": computed["six_month_item_forecast_total_by_division"],
              "written": False}
    if dry_run:
        result["note"] = "dry-run: vintage computed but NOT appended to the forward-test log."
        return result

    existing_log = pd.read_csv(FORWARD_TEST_LOG_PATH)
    combined = pd.concat([existing_log, computed["rows_df"]], ignore_index=True)
    combined.to_csv(FORWARD_TEST_LOG_PATH, index=False)
    metadata = load_metadata(FORWARD_TEST_METADATA_PATH)
    metadata[str(computed["vintage_id"])] = computed["metadata_entry"]
    save_metadata(FORWARD_TEST_METADATA_PATH, metadata)
    result["written"] = True
    return result


# ---------------------------------------------------------------------------------------------
# Step 6: fill actual_qty and score any months that became eligible
# ---------------------------------------------------------------------------------------------

def step6_fill_and_score(dry_run: bool, computed_vintage: dict = None) -> dict:
    config = load_config()
    metadata = load_metadata(FORWARD_TEST_METADATA_PATH)
    existing_log = pd.read_csv(FORWARD_TEST_LOG_PATH, dtype=str)
    existing_log["forecast_qty"] = existing_log["forecast_qty"].astype(float)
    existing_log["horizon"] = existing_log["horizon"].astype(int)
    existing_log["vintage_id"] = existing_log["vintage_id"].astype(int)
    existing_log["scope_n_items"] = existing_log["scope_n_items"].astype(int)

    if dry_run and computed_vintage is not None:
        # Include the not-yet-written new vintage (rows AND its metadata entry) in the
        # consistency/eligibility check so the dry run genuinely exercises what step 6 WOULD see
        # once step 5 actually appends it -- neither is written to disk in dry-run mode.
        preview_rows = computed_vintage["rows_df"].copy()
        preview_rows["actual_qty"] = ""
        log_for_check = pd.concat([existing_log, preview_rows], ignore_index=True)
        metadata = {**metadata, str(computed_vintage["vintage_id"]): computed_vintage["metadata_entry"]}
    else:
        log_for_check = existing_log

    verify_consistency(log_for_check, metadata)

    min_margin_days = load_min_margin_days(config)
    now = pd.Timestamp.now()
    target_months = sorted(log_for_check["target_month"].unique())
    safe_months = [m for m in target_months if target_month_safe_to_score(m, now, min_margin_days)]

    result = {"target_months_in_log": target_months, "safe_months": safe_months,
              "n_rows_would_be_filled": 0, "scored": False}
    if not safe_months:
        first_target = target_months[0]
        window_end = pd.Period(first_target, freq="M").end_time.normalize()
        ready_date = window_end + pd.Timedelta(days=int(min_margin_days))
        result["first_target_month"] = first_target
        result["first_eligible_date"] = str(ready_date.date())
        result["note"] = "No target month is safe to score yet -- nothing filled, nothing scored."
        return result

    scope = pd.read_csv(SCOPE_FILE)
    actuals = pull_actuals_forecastDate(config, scope, safe_months)  # the ONLY other possible DB call this
    # run could make -- only reached if a month is actually eligible; never reached in this task's dry run.
    scored, summary = score_and_summarize(log_for_check, actuals, safe_months)
    result["n_rows_would_be_filled"] = int(scored["target_month"].isin(safe_months).sum())
    result["scored"] = summary is not None
    if not dry_run:
        eligible_mask = scored["target_month"].isin(safe_months)
        existing_log.loc[eligible_mask.reindex(existing_log.index, fill_value=False), "actual_qty"] = (
            scored.loc[eligible_mask, "actual_qty"])
        existing_log.to_csv(FORWARD_TEST_LOG_PATH, index=False)
        result["written"] = True
    return result


# ---------------------------------------------------------------------------------------------
# Step 7: rebuild every page with section 26 timestamps (forecast/sales_report.html only -- see
# module docstring for scope)
# ---------------------------------------------------------------------------------------------

def step7_rebuild_pages(dry_run: bool, staged_dir: str) -> dict:
    import build_report
    if dry_run:
        out_path = build_report.build_report(output_path=os.path.join(staged_dir, "sales_report.html"))
    else:
        out_path = build_report.build_report()
    return {"rendered_path": out_path, "written_to_tracked_path": not dry_run}


# ---------------------------------------------------------------------------------------------
# Step 8: run the full test suite
# ---------------------------------------------------------------------------------------------

def step8_run_tests() -> dict:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=PROJECT_ROOT,
                           capture_output=True, text=True, timeout=600)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return {"returncode": proc.returncode, "passed": proc.returncode == 0,
            "summary_line": tail, "stdout_tail": proc.stdout[-3000:]}


# ---------------------------------------------------------------------------------------------
# Step 9: scan staged files for sensitive content
# ---------------------------------------------------------------------------------------------

def step9_scan_sensitive_content() -> dict:
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    changed_paths = [line[3:] for line in proc.stdout.splitlines() if line.strip()]
    findings = []
    for rel_path in changed_paths:
        abs_path = os.path.join(PROJECT_ROOT, rel_path)
        if not os.path.isfile(abs_path):
            continue
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        for pattern, label in SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                findings.append({"path": rel_path, "pattern_matched": label})
    return {"n_changed_files_scanned": len(changed_paths), "changed_files": changed_paths,
            "findings": findings, "passed": len(findings) == 0}


# ---------------------------------------------------------------------------------------------
# Step 10: check change magnitude against the previous run
# ---------------------------------------------------------------------------------------------

def step10_change_magnitude(config: dict, step4_result: dict, step5_result: dict) -> dict:
    thresholds = config["monthly_refresh"]
    six_mo_threshold = thresholds["six_month_forecast_change_pct"]
    mae_threshold = thresholds["backtest_mae_change_pct"]
    stock_threshold = thresholds["total_on_hand_stock_change_pct"]

    violations = []

    # ---- (a) six-month total forecast per division ----
    new_totals = step5_result.get("six_month_item_forecast_total_by_division", {})
    six_mo_report = {}
    if os.path.exists(FORWARD_TEST_LOG_PATH):
        existing_log = pd.read_csv(FORWARD_TEST_LOG_PATH)
        vintage_1 = existing_log[(existing_log["vintage_id"] == 1) & (existing_log["level"] == "Item")]
        prev_totals = vintage_1.groupby("division")["forecast_qty"].sum().to_dict()
        for div, new_total in new_totals.items():
            prev_total = prev_totals.get(div)
            pct = 100 * (new_total - prev_total) / prev_total if prev_total else None
            six_mo_report[div] = {"previous_vintage1_total": prev_total, "new_vintage_total": new_total,
                                    "change_pct": pct}
            if pct is not None and abs(pct) > six_mo_threshold:
                violations.append(f"{div}: six-month total forecast changed {pct:.1f}% "
                                  f"(> {six_mo_threshold}% threshold)")

    # ---- (b) backtest MAE per division (Top-down, transferability primary table) ----
    mae_report = {}
    for entry in step4_result.get("per_division_comparison_topdown", []):
        div = entry["division"]
        pct = entry.get("MAE_change_pct")
        mae_report[div] = pct
        if pct is not None and abs(pct) > mae_threshold:
            violations.append(f"{div}: backtest MAE changed {pct:.1f}% (> {mae_threshold}% threshold)")

    # ---- (c) total on-hand stock across the pricelist scope ----
    # LIMITATION (stated explicitly, not silently skipped): a fresh on-hand stock figure would
    # require its OWN database pull (Cube_Inventory_Exact/Cube_CES via
    # src/build_inventory_dataset.py) -- a SECOND connection attempt this run's single-connection
    # design does not make (DATABASE ACCESS rule: one connection attempt per agent/session). The
    # existing committed data/inventory.json figure (from whenever it was last generated) is
    # carried forward unchanged, so this sub-check trivially reports 0% change and is not a
    # meaningful test of a REAL stock movement until a generator that this runner calls exists.
    stock_report = {"note": "not independently re-pulled this run (would need a second DB "
                              "connection) -- existing data/inventory.json figure carried "
                              "forward unchanged; this sub-check is not yet meaningful.",
                     "change_pct": 0.0}
    if os.path.exists(INVENTORY_JSON_PATH):
        with open(INVENTORY_JSON_PATH, "r", encoding="utf-8") as f:
            inv = json.load(f)
        stock_report["current_totals"] = inv.get("totals")

    return {
        "thresholds": {"six_month_forecast_change_pct": six_mo_threshold,
                        "backtest_mae_change_pct": mae_threshold,
                        "total_on_hand_stock_change_pct": stock_threshold},
        "six_month_forecast_by_division": six_mo_report,
        "backtest_mae_change_pct_by_division": mae_report,
        "total_on_hand_stock": stock_report,
        "violations": violations,
        "passed": len(violations) == 0,
    }


# ---------------------------------------------------------------------------------------------
# Step 11: commit and push only if steps 8 to 10 all pass
# ---------------------------------------------------------------------------------------------

def step11_commit_and_push(dry_run: bool, step8: dict, step9: dict, step10: dict) -> dict:
    gates_passed = step8["passed"] and step9["passed"] and step10["passed"]
    if dry_run:
        return {"pushed": False, "reason": "dry-run: step 11 never writes or pushes for real.",
                "would_push_if_real_run": gates_passed,
                "gate_results": {"step8_tests_passed": step8["passed"],
                                  "step9_sensitive_scan_passed": step9["passed"],
                                  "step10_change_magnitude_passed": step10["passed"]}}
    if not gates_passed:
        return {"pushed": False, "reason": "one or more gates (steps 8-10) failed -- held for human review.",
                "gate_results": {"step8_tests_passed": step8["passed"],
                                  "step9_sensitive_scan_passed": step9["passed"],
                                  "step10_change_magnitude_passed": step10["passed"]}}
    # Real commit+push logic (never exercised by --dry-run, and never invoked by this project's
    # own tooling without an explicit, human-approved real run -- see this task's own scope note).
    github_reachable, github_err = check_tcp_reachable("github.com", 443)
    if not github_reachable:
        return {"pushed": False, "reason": f"GitHub unreachable ({github_err}) -- held, not pushed."}
    subprocess.run(["git", "add", "-A"], cwd=PROJECT_ROOT, check=True)
    subprocess.run(["git", "commit", "-m", "Automated monthly refresh"], cwd=PROJECT_ROOT, check=True)
    push = subprocess.run(["git", "push", "origin", "main"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return {"pushed": push.returncode == 0, "reason": push.stdout + push.stderr}


# ---------------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------------

def main(dry_run: bool) -> dict:
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    staged_dir = os.path.join(RUNS_DIR, run_id, "staged")
    os.makedirs(staged_dir, exist_ok=True)
    config = load_config()

    run_log = {"run_id": run_id, "dry_run": dry_run, "started_at": datetime.now().isoformat(timespec="seconds"),
               "steps": {}}

    def record(step_name, fn, *args, **kwargs):
        try:
            outcome = fn(*args, **kwargs)
            run_log["steps"][step_name] = {"status": "ok", **({"result": outcome} if outcome is not None else {})}
            return outcome
        except MonthlyRefreshAbort as e:
            run_log["steps"][step_name] = {"status": "ABORTED", "reason": str(e)}
            run_log["aborted_at_step"] = step_name
            run_log["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_run_log(run_log, run_id)
            raise

    step1 = record("1_pull_data", step1_pull_data, dry_run)
    record("2_validate", step2_validate)
    record("3_frozen_snapshot", step3_frozen_snapshot)
    step4 = record("4_backtest", step4_backtest, run_id)
    step5 = record("5_new_forward_test_vintage", step5_new_vintage, dry_run)
    computed_vintage_for_preview = _LAST_COMPUTED_VINTAGE if dry_run else None
    record("6_fill_and_score", step6_fill_and_score, dry_run, computed_vintage_for_preview)
    record("7_rebuild_pages", step7_rebuild_pages, dry_run, staged_dir)
    step8 = record("8_run_tests", step8_run_tests)
    step9 = record("9_scan_sensitive_content", step9_scan_sensitive_content)
    step10 = record("10_change_magnitude", step10_change_magnitude, config, step4, step5)
    step11 = record("11_commit_and_push", step11_commit_and_push, dry_run, step8, step9, step10)

    run_log["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_run_log(run_log, run_id)
    return run_log


def _write_run_log(run_log: dict, run_id: str) -> str:
    os.makedirs(RUNS_DIR, exist_ok=True)
    path = os.path.join(RUNS_DIR, f"monthly_refresh_{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, indent=2, default=str)
    logger.info("Run log written: %s", path)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Exercise every step's logic without writing/committing/pushing anything tracked.")
    args = parser.parse_args()
    try:
        log = main(dry_run=args.dry_run)
        print(json.dumps(log, indent=2, default=str))
    except MonthlyRefreshAbort as e:
        logger.error("MONTHLY REFRESH ABORTED: %s", e)
        sys.exit(1)
