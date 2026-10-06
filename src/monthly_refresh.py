"""Monthly refresh runner -- implements METRICS.md Sec.28's `monthly_refresh`, 11 steps, IN
ORDER, exactly as specified there:

    1 pull data — one connection attempt, abort on failure, no retry
    2 validate — zero-row guard and data invariants
    3 rebuild the forecast_date-keyed series as a frozen snapshot
    4 re-run the sales-model backtest; record each division's change against the previous run
    5 append a new forward-test vintage per section 27 -- ONE VINTAGE PER CALENDAR MONTH (task
      2cfix2, Part 2): if the log already has a vintage whose forecast_run_date falls in the
      current calendar month, a real run skips computing/appending a new one (every other step
      still runs) and records why; --force-new-vintage overrides this for a deliberate same-month
      re-run
    6 fill actual_qty and score any months that became eligible
    7 rebuild every page with section 26 timestamps
    7b recompute operation plan v1 (METRICS.md Sec.42) from the page just built and the saved pulls, then build
      forecast/operation_plan.html from it
    7c recompute material plan v1 (METRICS.md Sec.43) from the operation plan just recorded and the saved week 3 pulls, then build
      forecast/material_plan.html from it
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
  - Step 7 rebuilds forecast/sales_report.html (src/build_report.py) and forecast/inventory.html
    (src/build_inventory_page.py). index.html has NO generator script anywhere in the repo
    (STATUS.md, confirmed by repeated repo-wide search) -- it is hand-maintained and out of this
    runner's reach. The inventory page's PEM103/PEM107 sales come from this run's own step-1 pull
    (output/data/raw_all_divisions_sales.csv); the runner makes no stock pull (that would be a
    second connection), so stock is the latest saved pull under output/snapshots/, and the page
    shows the older of the two pull times (src/inventory_page_sources.py).

DRY RUN ISOLATION (task M2): a dry run changes nothing outside a temporary folder. It copies the
project (config, code, tests, pages and the inputs under output/data, output/summary and
output/snapshots) into a temporary root and runs steps 1-10 there exactly as a real run would, so
every write (refreshed analysis inputs, snapshots, forward-test rows, rebuilt pages) lands in the
copy and every later step reads it from there. Step 11 only reports. The one thing written to the
real project is the run log under output/runs/. tests/test_monthly_refresh_dry_run_isolation.py
hashes every file under output/ and every tracked page before and after a dry run.

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
import contextlib
import io
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
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
import forward_test_scoring as fts
from forward_test_common import (append_vintage_and_hash, compute_scope_hash, load_metadata,
                                 read_forward_test_log, save_metadata)
from item_level_reconciliation import forecast_all_approaches
import ma_comparator
import vintage_series
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
STOCK_JSON_PATH = os.path.join(PROJECT_ROOT, "data", "stock_daily.json")       # the Min-Max page's stock file (src/stock_daily.py)
COMPARATOR_LOG_PATH = ma_comparator.COMPARATOR_LOG_PATH             # moving-average comparator, METRICS.md Sec.27
COMPARATOR_METADATA_PATH = ma_comparator.COMPARATOR_METADATA_PATH
SCORE_RECORD_PATH = os.path.join(SUMMARY_DIR, "forward_test_scores.csv")
SCORE_INTEGRITY_PATH = os.path.join(SUMMARY_DIR, "forward_test_scores_integrity.json")
RAW_HISTORY_PATH = os.path.join(PROJECT_ROOT, "output", "data", "raw_all_divisions_sales.csv")
INVENTORY_PULL_DIR = os.path.join(PROJECT_ROOT, "output", "data", "inventory_pull")
PILOT_MONTHLY_PATH = os.path.join(PROJECT_ROOT, "output", "data", "processed_full_category_sales_monthly_forecastDate.csv")
SALES_REPORT_PATH = os.path.join(FORECAST_DIR, "sales_report.html")

SENSITIVE_PATTERNS = [
    (r"DB_PASSWORD\s*=\s*\S+", "DB_PASSWORD assignment"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", "api_key-looking literal"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "PEM private key block"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id pattern"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{4,}['\"]", "hardcoded password literal"),
]


STEP_ORDER = ["1_pull_data", "2_validate", "3_frozen_snapshot", "4_backtest", "5_new_forward_test_vintage",
              "6_fill_and_score", "7_rebuild_pages", "7b_operation_plan", "7c_material_plan", "8_run_tests", "9_scan_sensitive_content",
              "10_change_magnitude", "11_commit_and_push"]


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
    # Child output is UTF-8 (Thai log text); decode it as UTF-8 whatever the console code page is (a Scheduled
    # Task started from C:\Windows\system32 uses cp874, which raised UnicodeDecodeError and aborted step 1).
    cmd = [sys.executable, os.path.join(SRC_DIR, script_name)] + (args or [])
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
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


def _pull_stage(label: str, script: str, output_path: str, args: list = None) -> dict:
    """One pull script of step 1 beyond the main pull. refreshed is True only if the script exited 0 and its
    output file is newer than before it ran."""
    before = os.path.getmtime(output_path) if os.path.exists(output_path) else None
    proc = run_script(script, args)
    after = os.path.getmtime(output_path) if os.path.exists(output_path) else None
    ok = proc.returncode == 0 and after is not None and after != before
    out = {"label": label, "script": script, "returncode": proc.returncode, "refreshed": ok}
    if not ok:
        out["not_refreshed_reason"] = (f"script exited {proc.returncode}" if proc.returncode else "output file not rewritten")
        out["stderr_tail"] = proc.stderr[-1500:]
        logger.warning("Step 1: %s NOT refreshed (%s); the earlier file stays in place.", label, out["not_refreshed_reason"])
    return out


def step1_pull_data(dry_run: bool, offline: bool = False) -> dict:
    if offline:
        # Test/offline mode: no connection at all; the data already under output/data is used as this run's pull.
        monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
        return {"offline_reused_existing_pull": True, "rows_pulled": len(monthly),
                "pilot_128item_refresh": {"refreshed": False, "not_refreshed_reason": "offline mode: no database connection"},
                "inventory_pull": {"refreshed": False, "not_refreshed_reason": "offline mode: no database connection"},
                "snapshot_pull_date": str(monthly["snapshot_pull_date"].iloc[0]),
                "n_items": monthly["itemcode"].nunique(), "n_divisions": monthly["division"].nunique()}
    from dotenv import load_dotenv
    # Explicit absolute path -- see src/db.py's own identical fix, this task. A bare load_dotenv()
    # searches from the CURRENT WORKING DIRECTORY, not this file's location; a Scheduled Task
    # invoking this script from e.g. C:\Windows\system32 would silently fail to find .env.
    load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"))
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
    # ---- the other pulls the pages need, in the same pull stage (C-fix Parts 1 and 2). Each is recorded and
    # never aborts the run: a failure leaves the older file in place and the run log says "not refreshed".
    result["pilot_128item_refresh"] = _pull_stage("128-item pilot monthly file", "load_data_full.py", PILOT_MONTHLY_PATH)
    result["inventory_pull"] = _pull_stage("inventory.json pulls", "build_inventory_dataset.py",
                                           os.path.join(INVENTORY_PULL_DIR, "pull_meta.json"),
                                           args=["--save-pulls", INVENTORY_PULL_DIR])
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

def run_log_records_success(log: dict) -> bool:
    """True only for a real run that completed every step and pushed (C-fix Part 4). A dry run, a run that aborted
    or failed, and a run whose gates held the commit back never count: their outputs were not accepted."""
    if not isinstance(log, dict) or log.get("dry_run") or log.get("dry_run_in_temporary_copy"):
        return False
    if "aborted_at_step" in log or "failed_step" in log:
        return False
    steps = log.get("steps", {})
    if [k for k in STEP_ORDER if steps.get(k, {}).get("status") == "ok"] != STEP_ORDER:
        return False
    final = steps["11_commit_and_push"].get("result", {})
    return final.get("pushed") is True or final.get("nothing_to_commit") is True


def find_last_successful_run(runs_dir: str = None) -> dict:
    """The most recent run log (by its own started_at) that records success, or None. Runs that left no log (the
    2026-10-02 07:45 run failed before failure logs existed) are not successes."""
    runs_dir = runs_dir or RUNS_DIR
    best = None
    if not os.path.isdir(runs_dir):
        return None
    for name in os.listdir(runs_dir):
        if not (name.startswith("monthly_refresh_") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(runs_dir, name), encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, ValueError):
            continue
        if run_log_records_success(log) and (best is None or log.get("started_at", "") > best.get("started_at", "")):
            best = log
    return best


def baseline_from_run_log(log: dict) -> dict:
    """{division: {MAE, RMSE, Bias, MASE}} -- the Top-down backtest figures the given successful run produced
    (its step 4's `new_*` values), i.e. the figures that were live after that run."""
    comparison = log["steps"]["4_backtest"]["result"]["per_division_comparison_topdown"]
    return {e["division"]: {"MAE": float(e["new_MAE"]), "RMSE": float(e["new_RMSE"]),
                            "Bias": float(e["new_Bias"]), "MASE": float(e["new_MASE"])} for e in comparison}


def _archive_if_exists(path: str, run_id: str) -> str:
    if not os.path.exists(path):
        return None
    archive_dir = os.path.join(SUMMARY_DIR, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(path))
    archive_path = os.path.join(archive_dir, f"{base}_pre_monthly_refresh_{run_id}{ext}")
    pd.read_csv(path).to_csv(archive_path, index=False)
    return archive_path


def _run_regeneration_step(label: str, script_name: str, output_rel_path: str, skip_reason: str = None) -> dict:
    """Runs one analysis-input regeneration script (src/*.py or src/investigations/*.py) as a
    subprocess, same run_script() pattern as the rest of this runner. NEVER aborts the whole run
    on failure -- METRICS.md Sec.28's own instruction: 'An input the pipeline cannot regenerate is
    listed in the run log and labelled on its page as not refreshed', so a failure here is
    recorded and the (possibly-stale) existing output file is left in place, not treated as a
    step-4 abort. DATABASE ACCESS rule: each of these scripts makes at most its own single,
    never-retried connection attempt if it needs one -- multiple such stages within this one
    monthly_refresh.py run/session count as one attempt, same as step 1's own docstring already
    states for this runner's design."""
    out_path = os.path.join(SUMMARY_DIR, output_rel_path)
    if skip_reason:
        return {"label": label, "script": script_name, "output_file": output_rel_path, "returncode": None,
                "refreshed": False, "not_refreshed_reason": skip_reason}
    mtime_before = os.path.getmtime(out_path) if os.path.exists(out_path) else None
    proc = run_script(script_name)
    mtime_after = os.path.getmtime(out_path) if os.path.exists(out_path) else None
    succeeded = proc.returncode == 0 and mtime_after is not None and mtime_after != mtime_before
    result = {
        "label": label, "script": script_name, "output_file": output_rel_path,
        "returncode": proc.returncode, "refreshed": succeeded,
    }
    if not succeeded:
        result["not_refreshed_reason"] = (
            f"script exited {proc.returncode}" if proc.returncode != 0
            else "output file mtime did not change -- script may not have written it"
        )
        result["stderr_tail"] = proc.stderr[-1500:]
        logger.warning("Step 4: %s NOT refreshed (%s) -- existing %s left in place, labelled "
                        "'not refreshed' on its page.", label, result["not_refreshed_reason"], output_rel_path)
    else:
        logger.info("Step 4: %s refreshed (%s).", label, output_rel_path)
    return result


def step4_backtest(run_id: str, offline: bool = False) -> dict:
    # The comparison base is the figures of the most recent run whose log records success (C-fix Part 4), never the
    # current output files: a failed run in between may already have overwritten those (task C2, 2026-10-02).
    last_success = find_last_successful_run()
    baseline = baseline_from_run_log(last_success) if last_success else None
    baseline_note = (f"compared with the outputs of run {last_success['run_id']} (started {last_success['started_at']}), "
                     f"the most recent run whose log records success" if last_success else
                     "no earlier run log records success: nothing to compare with, change percentages are empty")

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
        if baseline is not None and div in baseline:
            prev = baseline[div]
            entry["previous_MAE"] = prev["MAE"]
            entry["previous_RMSE"] = prev["RMSE"]
            entry["previous_Bias"] = prev["Bias"]
            entry["previous_MASE"] = prev["MASE"]
            entry["MAE_change_pct"] = (100 * (entry["new_MAE"] - entry["previous_MAE"]) / entry["previous_MAE"]
                                       if entry["previous_MAE"] else None)
        comparison.append(entry)

    # ---- Also regenerate every OTHER analysis input forecast/sales_report.html displays that
    # wasn't already covered above (METRICS.md Sec.28: "Step 4 also regenerates every analysis
    # input the pages display, including the order-notice distribution and delivery timeliness by
    # year, so that a monthly run leaves no section stale by design. An input the pipeline cannot
    # regenerate is listed in the run log and labelled on its page as not refreshed."). Each call
    # is independently fault-tolerant (see _run_regeneration_step) -- one failing does not abort
    # step 4 or the run; it is recorded and the page's per-section staleness machinery (Part 2,
    # src/build_report.py gather_freshness()) will show that one section as stale/behind, never
    # the whole page.
    analysis_inputs_refreshed = [
        # Model section §5 chart (focus_items_test_all.csv) -- no DB call, reuses
        # processed_all_divisions_monthly_qty.csv already refreshed by this run's step 1.
        _run_regeneration_step("Model section base-model comparison (focus_items_test_all.csv)",
                                "focus_item_model_selection.py", "focus_items_test_all.csv"),
        # Order-notice distribution -- makes its own single DB connection (cube_Sale_APD, PEM101
        # 128-item scope); part of this run's one-session DB-access budget, not a second attempt.
        _run_regeneration_step("Order-notice distribution (leadtime_notice_buckets_overall.csv)",
                                os.path.join("investigations", "order_leadtime.py"),
                                "leadtime_notice_buckets_overall.csv",
                                skip_reason="offline mode: this script opens its own database connection" if offline else None),
        # Delivery timeliness by year, on_time_exact -- makes its own single DB connection
        # (Cube_CES, PEM101 128-item scope).
        _run_regeneration_step("Delivery timeliness by year, on_time_exact (delivery_by_year.csv)",
                                os.path.join("investigations", "delivery_performance.py"),
                                "delivery_by_year.csv",
                                skip_reason="offline mode: this script opens its own database connection" if offline else None),
    ]
    # Pilot-scope inputs derived from the 128-item monthly file step 1 refreshed (C-fix Part 2); no database.
    analysis_inputs_refreshed.append(
        _run_regeneration_step("Item forecast vs actual by origin (report_item_forecast_vs_actual_by_origin.csv)",
                                "build_report_data.py", "report_item_forecast_vs_actual_by_origin.csv"))
    analysis_inputs_refreshed.append(
        _run_regeneration_step("Item-level reconciliation, paired significance (b3_paired_significance.csv)",
                                "item_level_reconciliation.py", "b3_paired_significance.csv"))
    # Moving-average window per division, chosen from the backtest just written (METRICS.md Sec.27); recorded for inspection,
    # the vintage computation re-reads the backtest itself. No database.
    analysis_inputs_refreshed.append(
        _run_regeneration_step("Moving-average comparator window per division (ma_comparator_windows.csv)",
                                "ma_comparator.py", "ma_comparator_windows.csv"))
    # Top-down against Direct and Naive, per division, on the backtest step 4 just wrote (METRICS.md Sec.41); the sales
    # report's significance block reads it. No database; runs in dry runs and offline runs too.
    analysis_inputs_refreshed.append(
        _run_regeneration_step("Top-down significance per division (topdown_significance.csv)",
                                "significance_topdown.py", "topdown_significance.csv"))
    # not_late (delivery_not_late_by_year.csv) reuses delivery_performance.py's OWN raw pull
    # (output/data/raw_cube_ces_delivery_128items.csv) -- no new DB call -- so it must run AFTER
    # delivery_performance.py above, never before/independently.
    analysis_inputs_refreshed.append(
        _run_regeneration_step("Delivery timeliness by year, not_late (delivery_not_late_by_year.csv)",
                                os.path.join("investigations", "task2a_delivery_notlate_by_year.py"),
                                "delivery_not_late_by_year.csv")
    )

    return {
        "comparison_base": baseline_note,
        "comparison_base_run_id": last_success["run_id"] if last_success else None,
        "archived_previous_per_division_summary": archived_per_division,
        "archived_previous_transferability": archived_transferability,
        "per_division_comparison_topdown": comparison,
        "new_per_division_summary_rows": len(new_per_division),
        "new_transferability_rows": len(new_transferability),
        "analysis_inputs_refreshed": analysis_inputs_refreshed,
    }


# ---------------------------------------------------------------------------------------------
# Step 5: append a new forward-test vintage per section 27 (computed always; WRITTEN only if
# not dry_run) -- ONE VINTAGE PER CALENDAR MONTH guard (Part 2, task 2cfix2): a second real run
# in the same calendar month must not silently append vintage 3, vintage 4, etc.
# ---------------------------------------------------------------------------------------------

def find_existing_vintage_this_month(log_path: str, now: pd.Timestamp) -> dict:
    """Returns {'vintage_id', 'forecast_run_date'} for the MOST RECENT vintage already recorded
    in `log_path` whose own `forecast_run_date` falls in the CURRENT calendar month, per `now`
    (the run's own clock at the time it runs -- never the scheduled date, so a run that happens
    to execute a day late/early is judged by when it actually runs). Returns None if the log
    doesn't exist yet or has no such row. Takes an explicit `log_path`/`now` (rather than reading
    the module-level FORWARD_TEST_LOG_PATH/datetime.now() directly) so tests can exercise this
    against a synthetic/temporary log file, never the real tracked one (this task's own
    instruction)."""
    if not os.path.exists(log_path):
        return None
    log = pd.read_csv(log_path, usecols=["vintage_id", "forecast_run_date"])
    if log.empty:
        return None
    run_dates = pd.to_datetime(log["forecast_run_date"])
    current_month = pd.Period(now, freq="M")
    same_month_mask = run_dates.dt.to_period("M") == current_month
    if not same_month_mask.any():
        return None
    same_month = log[same_month_mask].assign(_run_date=run_dates[same_month_mask])
    row = same_month.sort_values(["vintage_id"]).iloc[-1]
    return {"vintage_id": int(row["vintage_id"]), "forecast_run_date": str(row["_run_date"].date())}


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
    # the vintage reads exactly these bytes, and step 5 saves them (src/vintage_series.py), so the series can be re-read and hash-checked
    with open(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"), "rb") as f:
        fit_series_bytes = f.read()
    monthly = pd.read_csv(io.BytesIO(fit_series_bytes))
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

    # Moving-average comparator (METRICS.md Sec.27): the window per division comes from the CURRENT backtest only.
    window_choice = ma_comparator.current_choice(config)
    windows_by_division = ma_comparator.chosen_windows(window_choice)
    missing_divisions = set(scope["division"]) - set(windows_by_division)
    if missing_divisions:
        raise MonthlyRefreshAbort(f"Step 5 ABORTED: the backtest gives no moving-average window for {sorted(missing_divisions)}.")
    comparator_records = ma_comparator.moving_average_rows(
        item_series, item_to_info, windows_by_division, target_months,
        lambda code, division, level, category, type_: {**base_row(code, division, level, category, type_, next_vintage_id),
                                                         "provenance": "computed at the vintage's run"},
        no_history_codes)
    comparator_df = pd.DataFrame(comparator_records)

    metadata_entry = {
        "log_file": os.path.relpath(FORWARD_TEST_LOG_PATH, PROJECT_ROOT).replace("\\", "/"),
        "generated_by_script": "src/monthly_refresh.py (compute_new_vintage)",
        "forecast_run_date": run_date, "config_version": cfg_ver, "date_key": "forecastDate",
        "item_level_approach": approach_label, "scope_hash": scope_hash, "scope_n_items": n_scope_items,
        "vintage_id": next_vintage_id,    # row_integrity_hash and row_hash_scheme are added by append_vintage_and_hash
                                          # after the rows are written to the log and read back
        "fit_first_month": fit_first_month, "fit_last_month": fit_last_month, "fit_n_months": n_fit_months,
        "horizon_months": horizon, "target_months": target_months,
        "leakage_guard_min_margin_days": min_margin_days, "leakage_guard_actual_margin_days": actual_margin_days,
        "n_total_rows": len(rows_df), "divisions": sorted(scope["division"].unique().tolist()),
        **vintage_series.metadata_fields(fit_series_bytes, next_vintage_id),
    }
    six_month_totals_by_division = rows_df[rows_df["level"] == "Item"].groupby("division")["forecast_qty"].sum().to_dict()
    comparator_entry = {**metadata_entry, "log_file": os.path.relpath(COMPARATOR_LOG_PATH, PROJECT_ROOT).replace("\\", "/"),
                        "generated_by_script": "src/monthly_refresh.py (compute_new_vintage, moving-average comparator)",
                        "model_family": "moving_average", "n_total_rows": len(comparator_df), "n_item_rows": len(comparator_df),
                        "ma_window_by_division": windows_by_division,
                        "ma_window_source_file": str(window_choice["source_file"].iloc[0]),
                        "ma_window_source_pull_date": str(window_choice["snapshot_pull_date"].iloc[0]),
                        "ma_window_rule": "lowest mean item-level MAE over the current backtest's rolling origins; a tie goes to the shorter window; "
                                          "never chosen from forward-test results",
                        "provenance": "computed at the vintage's run"}
    for k in ("n_type_rows", "n_category_rows", "n_items_with_history", "n_items_no_history_zero_forecast"):
        comparator_entry.pop(k, None)
    return {"vintage_id": next_vintage_id, "rows_df": rows_df, "metadata_entry": metadata_entry,
            "fit_series_bytes": fit_series_bytes,
            "comparator_rows_df": comparator_df, "comparator_metadata_entry": comparator_entry,
            "ma_window_choice": window_choice,
            "n_rows": len(rows_df), "six_month_item_forecast_total_by_division": six_month_totals_by_division}


def rehearse_vintage_write_and_reread(computed: dict) -> dict:
    """Dry runs: append the new vintage to a TEMPORARY copy of the forward-test log, read it back from the file,
    record its hash from the read-back rows, and run the same verification step 6 runs on the real log. The
    real log and metadata are never touched. A failure raises, exactly as it would in a real run."""
    from score_forward_test_all_divisions import verify_consistency
    with tempfile.TemporaryDirectory(prefix="vintage_rehearsal_") as tmp:
        tmp_log = os.path.join(tmp, "forward_test_log_all_divisions.csv")
        if os.path.exists(FORWARD_TEST_LOG_PATH):
            shutil.copy2(FORWARD_TEST_LOG_PATH, tmp_log)
        entry = append_vintage_and_hash(tmp_log, computed["rows_df"], computed["metadata_entry"])
        metadata = {**load_metadata(FORWARD_TEST_METADATA_PATH), str(computed["vintage_id"]): entry}
        verify_consistency(read_forward_test_log(tmp_log), metadata)
        # the comparator log the same way, against its own metadata
        tmp_cmp = os.path.join(tmp, "forward_test_comparator_log.csv")
        if os.path.exists(COMPARATOR_LOG_PATH):
            shutil.copy2(COMPARATOR_LOG_PATH, tmp_cmp)
        cmp_entry = append_vintage_and_hash(tmp_cmp, computed["comparator_rows_df"], computed["comparator_metadata_entry"])
        cmp_meta = {**(load_metadata(COMPARATOR_METADATA_PATH) if os.path.exists(COMPARATOR_METADATA_PATH) else {}),
                    str(computed["vintage_id"]): cmp_entry}
        verify_consistency(read_forward_test_log(tmp_cmp), cmp_meta)
        # the fit series the same way: saved to the temporary folder, then checked against the hash in the metadata entry
        series_dir = os.path.join(tmp, "vintage_series")
        vintage_series.save_series(computed["fit_series_bytes"], computed["vintage_id"], series_dir)
        series_check = vintage_series.verify_series({str(computed["vintage_id"]): entry}, series_dir)
        if series_check["verified"] != [computed["vintage_id"]]:
            raise MonthlyRefreshAbort("Step 5 rehearsal: the vintage's saved fit series did not verify against its metadata")
    return {"verified": True, "fit_series_verified": True, "vintage_id": computed["vintage_id"], "row_hash_scheme": entry["row_hash_scheme"],
            "comparator_verified": True, "comparator_row_hash_scheme": cmp_entry["row_hash_scheme"],
            "note": "the new vintage and its moving-average comparator rows were appended to temporary copies of the logs, "
                    "read back and verified; the real logs were not touched."}


_LAST_COMPUTED_VINTAGE = None  # cache so step 6 (dry-run preview) never recomputes step 5's
# forecasts -- None means "step 5 computed nothing new this run" (either the guard skipped it, or
# this run hasn't reached step 5 yet); only ever set to a real computed-vintage dict, never {}.


def step5_new_vintage(dry_run: bool, force_new_vintage: bool = False) -> dict:
    """Part 2, task 2cfix2: ONE VINTAGE PER CALENDAR MONTH. If the forward-test log already has a
    vintage whose forecast_run_date falls in the CURRENT calendar month (per this run's own
    clock -- see find_existing_vintage_this_month()), a real run does NOT compute or append a new
    vintage; every other monthly_refresh step still runs normally. `force_new_vintage=True`
    (the --force-new-vintage CLI flag) deliberately overrides the guard for an intentional
    same-month re-run, and its use is recorded in the returned result (and therefore the run
    log) either way."""
    global _LAST_COMPUTED_VINTAGE
    now = pd.Timestamp.now()
    existing_this_month = find_existing_vintage_this_month(FORWARD_TEST_LOG_PATH, now)

    if existing_this_month is not None and not force_new_vintage:
        _LAST_COMPUTED_VINTAGE = None
        return {
            "skipped": True, "written": False,
            "reason": (
                f"one-vintage-per-calendar-month guard: a vintage already exists for "
                f"{now.strftime('%Y-%m')} (vintage_id={existing_this_month['vintage_id']}, "
                f"forecast_run_date={existing_this_month['forecast_run_date']}) -- no new "
                f"vintage computed or appended this run. Pass --force-new-vintage to override "
                f"for a deliberate same-month re-run."
            ),
            "existing_vintage_id_this_month": existing_this_month["vintage_id"],
            "existing_forecast_run_date_this_month": existing_this_month["forecast_run_date"],
            "force_new_vintage": False,
        }

    try:
        computed = compute_new_vintage()
    except LeakageGuardError as e:
        raise MonthlyRefreshAbort(f"Step 5 ABORTED: leakage guard refused the new vintage's fit window: {e}")
    _LAST_COMPUTED_VINTAGE = computed

    result = {"skipped": False, "vintage_id": computed["vintage_id"], "n_rows_computed": computed["n_rows"],
              "comparator_n_rows_computed": int(len(computed["comparator_rows_df"])),
              "ma_window_by_division": computed["comparator_metadata_entry"]["ma_window_by_division"],
              "six_month_item_forecast_total_by_division": computed["six_month_item_forecast_total_by_division"],
              "written": False, "force_new_vintage": force_new_vintage}
    if existing_this_month is not None:
        # force_new_vintage=True got us here despite a same-month vintage already existing --
        # record the override explicitly (this task's own instruction: "record its use in the
        # log when set").
        result["force_override_used"] = True
        result["overridden_existing_vintage_id"] = existing_this_month["vintage_id"]
        result["overridden_existing_forecast_run_date"] = existing_this_month["forecast_run_date"]
    if dry_run:
        result["note"] = "dry-run: vintage computed but NOT appended to the real forward-test log."
        result["rehearsal"] = rehearse_vintage_write_and_reread(computed)
        return result

    # Write the rows, read the log back, and compute the integrity hash from what was read back, so the stored
    # hash is the one verification will recompute (task C2b).
    vintage_series.save_series(computed["fit_series_bytes"], computed["vintage_id"])   # before the log: no vintage without its series
    result["fit_series_file"] = computed["metadata_entry"]["fit_series_file"]
    entry = append_vintage_and_hash(FORWARD_TEST_LOG_PATH, computed["rows_df"], computed["metadata_entry"])
    metadata = load_metadata(FORWARD_TEST_METADATA_PATH)
    metadata[str(computed["vintage_id"])] = entry
    save_metadata(FORWARD_TEST_METADATA_PATH, metadata)
    result["written"] = True
    result["row_hash_scheme"] = entry["row_hash_scheme"]
    # the moving-average comparator rows of the same vintage, in their own append-only log with their own hashes
    cmp_entry = append_vintage_and_hash(COMPARATOR_LOG_PATH, computed["comparator_rows_df"], computed["comparator_metadata_entry"])
    cmp_meta = load_metadata(COMPARATOR_METADATA_PATH) if os.path.exists(COMPARATOR_METADATA_PATH) else {}
    cmp_meta[str(computed["vintage_id"])] = cmp_entry
    save_metadata(COMPARATOR_METADATA_PATH, cmp_meta)
    result["comparator"] = {"written": True, "n_rows": int(len(computed["comparator_rows_df"])),
                            "ma_window_by_division": computed["comparator_metadata_entry"]["ma_window_by_division"],
                            "row_hash_scheme": cmp_entry["row_hash_scheme"]}
    return result


# ---------------------------------------------------------------------------------------------
# Step 6: fill actual_qty and score any months that became eligible
# ---------------------------------------------------------------------------------------------

def step6_fill_and_score(dry_run: bool, computed_vintage: dict = None, offline: bool = False, run_id: str = None) -> dict:
    """Fills actual_qty for every month that is safe to score, then appends the forward-test scores of every fully
    actualised (vintage, target month, horizon) not yet in the append-only score record (C-fix Part 5)."""
    result = _fill_actuals(dry_run, computed_vintage, offline)
    log = read_forward_test_log(FORWARD_TEST_LOG_PATH)
    result["comparator"] = verify_comparator_log()
    try:
        result["fit_series"] = vintage_series.verify_series(load_metadata(FORWARD_TEST_METADATA_PATH))
    except vintage_series.VintageSeriesError as e:
        raise MonthlyRefreshAbort(f"Step 6 ABORTED: a vintage's saved fit series failed its hash check: {e}")
    comparator_log = comparator_meta = None
    if result["comparator"]["exists"]:
        comparator_log, comparator_meta = read_forward_test_log(COMPARATOR_LOG_PATH), load_metadata(COMPARATOR_METADATA_PATH)
    result["score_record"] = fts.record_scores(log, load_metadata(FORWARD_TEST_METADATA_PATH),
                                               run_id or datetime.now().strftime("%Y%m%dT%H%M%S"),
                                               raw_path=RAW_HISTORY_PATH, scores_path=SCORE_RECORD_PATH,
                                               integrity_path=SCORE_INTEGRITY_PATH,
                                               comparator_log=comparator_log, comparator_metadata=comparator_meta)
    return result


def verify_comparator_log() -> dict:
    """The moving-average comparator log against its own metadata (hash of its rows, internal consistency), and every vintage in it
    must also exist in the forward-test log's metadata. No comparator log yet is a normal state: vintages 1 and 2 predate it and
    the monthly series they were fitted on was not saved, so the comparison starts with the next vintage."""
    if not os.path.exists(COMPARATOR_LOG_PATH):
        return {"exists": False, "note": "no comparator vintage yet: the comparison starts with the next vintage "
                                         "(vintages 1 and 2 predate it; their fitted series is not saved, so they are not reconstructed)"}
    log = read_forward_test_log(COMPARATOR_LOG_PATH)
    verify_consistency(log, load_metadata(COMPARATOR_METADATA_PATH))
    main_meta = load_metadata(FORWARD_TEST_METADATA_PATH)
    orphans = [int(v) for v in log["vintage_id"].unique() if str(int(v)) not in main_meta]
    if orphans:
        raise MonthlyRefreshAbort(f"the comparator log holds vintage(s) {orphans} that the forward-test log's metadata does not know")
    return {"exists": True, "vintages": sorted(int(v) for v in log["vintage_id"].unique()), "verified": True}


def fill_comparator_actuals(main_log: pd.DataFrame) -> dict:
    """Copies each month's actual quantity from the forward-test log into the comparator log's empty actual_qty cells (the one column
    allowed to change after a vintage is written); the actual of an item and month is the same whichever vintage forecast it."""
    if not os.path.exists(COMPARATOR_LOG_PATH):
        return {"filled": 0, "note": "no comparator log yet"}
    items = main_log[(main_log["level"] == "Item") & main_log["actual_qty"].notna() & (main_log["actual_qty"].astype(str) != "")]
    actual = {(r.itemcode, r.target_month): r.actual_qty for r in items.drop_duplicates(["itemcode", "target_month"]).itertuples()}
    cmp_log = pd.read_csv(COMPARATOR_LOG_PATH)
    empty = cmp_log["actual_qty"].isna() | (cmp_log["actual_qty"].astype(str) == "")
    new = [actual.get((c, m)) for c, m in zip(cmp_log.loc[empty, "itemcode"], cmp_log.loc[empty, "target_month"])]
    cmp_log["actual_qty"] = cmp_log["actual_qty"].astype(object)
    cmp_log.loc[empty, "actual_qty"] = new
    cmp_log.to_csv(COMPARATOR_LOG_PATH, index=False)
    return {"filled": int(sum(v is not None for v in new)), "written": True}


def _fill_actuals(dry_run: bool, computed_vintage: dict = None, offline: bool = False) -> dict:
    config = load_config()
    metadata = load_metadata(FORWARD_TEST_METADATA_PATH)
    existing_log = read_forward_test_log(FORWARD_TEST_LOG_PATH)
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

    if offline:
        result["note"] = "offline mode: months are eligible but the actuals pull (a database connection) was skipped."
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
        result["comparator_actuals"] = fill_comparator_actuals(existing_log)
    return result


# ---------------------------------------------------------------------------------------------
# Step 7: rebuild every page with section 26 timestamps (forecast/sales_report.html only -- see
# module docstring for scope)
# ---------------------------------------------------------------------------------------------

def regenerate_inventory_json(step1_result: dict = None) -> dict:
    """Rebuilds data/inventory.json from the pulls step 1 saved (C-fix Part 1), so index.html's stock panel shows this
    run's pull time. Without a saved pull the file is left as it is and the run log says so."""
    meta_path = os.path.join(INVENTORY_PULL_DIR, "pull_meta.json")
    pull = (step1_result or {}).get("inventory_pull", {})
    if not os.path.exists(meta_path):
        return {"regenerated": False, "reason": "no saved inventory pull exists (output/data/inventory_pull): "
                                                "data/inventory.json left as it was"}
    if not pull.get("refreshed") and not (step1_result or {}).get("offline_reused_existing_pull"):
        return {"regenerated": False, "reason": "step 1 did not refresh the inventory pull this run "
                                                f"({pull.get('not_refreshed_reason', 'not attempted')}): data/inventory.json left as it was"}
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    proc = run_script("build_inventory_dataset.py", ["--from-pulls", INVENTORY_PULL_DIR])
    if proc.returncode != 0:
        return {"regenerated": False, "reason": f"build_inventory_dataset.py exited {proc.returncode}",
                "stderr_tail": proc.stderr[-1500:]}
    with open(INVENTORY_JSON_PATH, encoding="utf-8") as f:
        written = json.load(f)["snapshot"]["generated_at"]
    if written != meta["pulled_at_utc"]:
        raise MonthlyRefreshAbort(f"Step 7 ABORTED: data/inventory.json says it was generated at {written}, the saved "
                                  f"pull is from {meta['pulled_at_utc']}.")
    import stock_daily
    write_stock_json(INVENTORY_PULL_DIR, meta, STOCK_JSON_PATH)
    return {"regenerated": True, "data_pulled_at_utc": written, "data_pulled_at_local": meta.get("pulled_at_local"),
            "stock_json_written": stock_daily.STOCK_JSON_RELATIVE}


def write_stock_json(pull_dir: str, meta: dict, path: str = None) -> str:
    """The Min-Max page's stock file (data/stock_daily.json), from the same saved pull and the same builder
    (src/stock_daily.py) the daily job uses, so the same pull gives byte-identical JSON on both paths."""
    import stock_daily
    payload = stock_daily.from_pulls(pull_dir)
    if payload["pull_time"] != str(meta["pulled_at_local"])[:19]:
        raise MonthlyRefreshAbort(f"Step 7 ABORTED: the stock file would say it was pulled at {payload['pull_time']}, the saved "
                                  f"pull is from {meta['pulled_at_local']}.")
    return stock_daily.write_payload(payload, path or stock_daily.STOCK_JSON_PATH)


def step7_rebuild_pages(dry_run: bool, staged_dir: str, step1_result: dict = None) -> dict:
    """Rebuilds forecast/sales_report.html and forecast/inventory.html (METRICS.md Sec.28 step 7).

    The inventory page's PEM103/PEM107 sales come from this run's own step-1 pull
    (output/data/raw_all_divisions_sales.csv). The runner makes no stock pull; stock is the latest daily
    snapshot written by src/snapshot_daily.py (output/snapshots/inventory_daily_*.csv), and the page shows
    that snapshot's own load time as the stock section's data-pulled time, with the staleness notice when
    it is older than the configured threshold (src/inventory_page_sources.py). A dry run never reaches this
    function with dry_run=True: it runs inside a temporary copy of the project, where these are ordinary
    writes."""
    import build_inventory_page
    import build_report
    import inventory_page_sources
    inventory_json = regenerate_inventory_json(step1_result)
    if dry_run:
        out_path = build_report.build_report(output_path=os.path.join(staged_dir, "sales_report.html"))
    else:
        out_path = build_report.build_report()
    pull_time = (step1_result or {}).get("snapshot_pull_date")
    if not pull_time:
        raise MonthlyRefreshAbort("Step 7 ABORTED: step 1 recorded no snapshot_pull_date, so the inventory page's "
                                  "sales pull time is unknown.")
    sources = inventory_page_sources.daily_snapshot_sources(pull_time)
    page = build_inventory_page.build_page(**sources)
    inv_path = os.path.join(staged_dir, "inventory.html") if dry_run else build_inventory_page.OUT_PATH
    with open(inv_path, "w", encoding="utf-8") as f:
        f.write(page)
    # The in-use assumptions the index.html tab reads at runtime (src/maxmin_v1.py), computed from the recorded outputs and config.
    import maxmin_v1
    assumptions_path = maxmin_v1.write_assumptions(os.path.join(staged_dir, "assumptions.json") if dry_run else None)
    return {"inventory_json": inventory_json, "assumptions_written_to": assumptions_path,
            "rendered_path": out_path, "inventory_rendered_path": inv_path,
            "inventory_sales_pull_time": str(pull_time),
            "inventory_pilot_pull_label": sources["pull_labels"]["PEM103"],
            "inventory_stock_snapshot": sources["stock_meta"],
            "inventory_stock_pulled_at": sources["stock_pulled_at"],
            "written_to_tracked_path": not dry_run and not IN_SANDBOX,
            "written_to": "temporary copy of the project (dry run)" if IN_SANDBOX else
                          ("staging folder" if dry_run else "tracked pages")}


# ---------------------------------------------------------------------------------------------
# Step 7b: operation plan v1 (METRICS.md Sec.42)
# ---------------------------------------------------------------------------------------------

def step7b_operation_plan(dry_run: bool, staged_dir: str, step7_result: dict = None) -> dict:
    """Recomputes the operation plan from the inventory page step 7 just built and the saved pulls, verifies the recorded outputs against their
    SHA-256 and reports the months, the counts, the capacity reference and the months above it. In a dry run the whole run is inside a temporary
    copy of the project, so the plan is written there; a staged (non-copy) dry run writes under its staging folder. Makes no database connection."""
    import build_operation_plan_page
    import operation_plan
    page = (step7_result or {}).get("inventory_rendered_path")
    plan_dir = os.path.join(staged_dir, "operation_plan") if dry_run else None
    result = operation_plan.run(PROJECT_ROOT, today=pd.Timestamp(datetime.now().date()), out_dir=plan_dir, page_path=page)
    # The planners' page, built from the plan just recorded (forecast/operation_plan.html; a staged dry run writes it under the staging folder).
    result["operation_plan_page"] = build_operation_plan_page.build_page(
        PROJECT_ROOT, out_dir=plan_dir, out_path=os.path.join(plan_dir, "operation_plan.html") if dry_run else None)
    result["written_to_tracked_path"] = False
    result["written_to"] = ("temporary copy of the project (dry run)" if IN_SANDBOX else
                            ("staging folder" if dry_run else "output/summary (untracked)"))
    return result


# ---------------------------------------------------------------------------------------------
# Step 7c: material plan v1 (METRICS.md Sec.43)
# ---------------------------------------------------------------------------------------------

def step7c_material_plan(dry_run: bool, staged_dir: str) -> dict:
    """Recomputes the material plan from the operation plan step 7b just recorded (hash-checked) and the saved week 3 pulls, records its two outputs with
    their SHA-256 and builds forecast/material_plan.html. In a dry run the whole run is inside a temporary copy of the project; a staged (non-copy) dry
    run writes under its staging folder. Makes no database connection."""
    import build_material_plan_page
    import material_plan
    plan_dir = os.path.join(staged_dir, "operation_plan") if dry_run else None
    result = material_plan.run(PROJECT_ROOT, today=pd.Timestamp(datetime.now().date()), out_dir=plan_dir, op_out_dir=plan_dir)
    result["material_plan_page"] = build_material_plan_page.build_page(
        PROJECT_ROOT, out_dir=plan_dir, out_path=os.path.join(plan_dir, "material_plan.html") if dry_run else None)
    result["written_to_tracked_path"] = False
    result["written_to"] = ("temporary copy of the project (dry run)" if IN_SANDBOX else
                            ("staging folder" if dry_run else "output/summary (untracked)"))
    return result


# ---------------------------------------------------------------------------------------------
# Step 8: run the full test suite
# ---------------------------------------------------------------------------------------------

def step8_run_tests(skip_tests: bool = False) -> dict:
    if skip_tests:
        # Only for tests of the runner itself (the suite would otherwise run inside its own test).
        return {"skipped": True, "passed": None, "summary_line": "step 8 skipped (--skip-tests)"}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=PROJECT_ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return {"returncode": proc.returncode, "passed": proc.returncode == 0,
            "summary_line": tail, "stdout_tail": proc.stdout[-3000:]}


# ---------------------------------------------------------------------------------------------
# Step 9: scan staged files for sensitive content
# ---------------------------------------------------------------------------------------------

def _sandbox_changed_files(started_at: float) -> list:
    """Inside a dry-run copy there is no git repository: files (outside output/) written since the run started."""
    changed = []
    for base in ("forecast", "docs", "config", "src", "tests", "data"):
        for dirpath, _dirs, files in os.walk(os.path.join(PROJECT_ROOT, base)):
            if "__pycache__" in dirpath:
                continue
            for f in files:
                full = os.path.join(dirpath, f)
                if os.path.getmtime(full) >= started_at:
                    changed.append(os.path.relpath(full, PROJECT_ROOT))
    return changed


def step9_scan_sensitive_content(sandbox_started_at: float = None) -> dict:
    if sandbox_started_at is not None:
        changed_paths = _sandbox_changed_files(sandbox_started_at)
        findings = []
        for rel_path in changed_paths:
            try:
                with open(os.path.join(PROJECT_ROOT, rel_path), "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            for pattern, label in SENSITIVE_PATTERNS:
                if re.search(pattern, text):
                    findings.append({"path": rel_path, "pattern_matched": label})
        return {"n_changed_files_scanned": len(changed_paths), "changed_files": changed_paths,
                "findings": findings, "passed": len(findings) == 0, "scanned_in": "dry-run copy"}
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
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

GATE_PASSED, GATE_FAILED, GATE_NOT_TESTED = "passed", "failed", "not_tested"


def _gate(status: str, reason: str, **extra) -> dict:
    return {"status": status, "reason": reason, **extra}


def count_gates(gates: dict) -> dict:
    """{'passed': n, 'failed': n, 'not_tested': n} over a {name: gate} dict; a gate that tested nothing is never counted as passed."""
    counts = {GATE_PASSED: 0, GATE_FAILED: 0, GATE_NOT_TESTED: 0}
    for g in gates.values():
        counts[g["status"]] += 1
    return counts


def last_daily_stock_baseline() -> dict:
    """The on-hand total the latest successful daily stock run published (its sum of stock over the pull it published), or None
    when no daily run has succeeded yet (output/runs/daily/last_success.json, written by src/daily_stock_job.py)."""
    path = os.path.join(PROJECT_ROOT, load_config()["daily_stock"]["last_success_file"])
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    return {"on_hand_total": float(rec["on_hand_total"]), "pull_time": rec.get("pull_time"), "run_id": rec.get("run_id")}


def monthly_pull_on_hand_total() -> float:
    """Total on-hand units of the stock pull this run's step 1 saved (output/data/inventory_pull), or None when there is none."""
    path = os.path.join(INVENTORY_PULL_DIR, "inventory.pkl")
    if not os.path.exists(path):
        return None
    return float(pd.read_pickle(path)["stock"].sum())


def step10_change_magnitude(config: dict, step4_result: dict, step5_result: dict) -> dict:
    """Three gates, each recorded as passed, failed or not tested with its reason (METRICS.md Sec.28). A gate that could not compare
    anything is `not_tested`, never `passed`; the step passes when no gate failed, and the run log counts not-tested gates separately."""
    thresholds = config["monthly_refresh"]
    six_mo_threshold = thresholds["six_month_forecast_change_pct"]
    mae_threshold = thresholds["backtest_mae_change_pct"]
    stock_threshold = thresholds["total_on_hand_stock_change_pct"]

    violations = []
    gates = {}

    # ---- (a) six-month total forecast per division, against vintage 1 ----
    new_totals = step5_result.get("six_month_item_forecast_total_by_division", {})
    six_mo_report = {}
    if step5_result.get("skipped"):
        gates["six_month_forecast"] = _gate(GATE_NOT_TESTED, "step 5 skipped, so no new vintage was computed to compare: "
                                            + str(step5_result.get("reason", ""))[:200])
    elif not new_totals or not os.path.exists(FORWARD_TEST_LOG_PATH):
        gates["six_month_forecast"] = _gate(GATE_NOT_TESTED, "no new six-month totals or no forward-test log to compare with")
    else:
        existing_log = pd.read_csv(FORWARD_TEST_LOG_PATH)
        vintage_1 = existing_log[(existing_log["vintage_id"] == 1) & (existing_log["level"] == "Item")]
        prev_totals = vintage_1.groupby("division")["forecast_qty"].sum().to_dict()
        failed = []
        for div, new_total in new_totals.items():
            prev_total = prev_totals.get(div)
            pct = 100 * (new_total - prev_total) / prev_total if prev_total else None
            six_mo_report[div] = {"previous_vintage1_total": prev_total, "new_vintage_total": new_total, "change_pct": pct}
            if pct is not None and abs(pct) > six_mo_threshold:
                failed.append(f"{div}: six-month total forecast changed {pct:.1f}% (> {six_mo_threshold}% threshold)")
        compared = [d for d, r in six_mo_report.items() if r["change_pct"] is not None]
        violations += failed
        gates["six_month_forecast"] = (_gate(GATE_FAILED, "; ".join(failed)) if failed else
                                       _gate(GATE_PASSED, f"{len(compared)} divisions within {six_mo_threshold}% of vintage 1") if compared else
                                       _gate(GATE_NOT_TESTED, "vintage 1 holds no total for any division in the new vintage"))

    # ---- (b) backtest MAE per division (Top-down, transferability primary table) ----
    mae_report = {}
    mae_failed = []
    for entry in step4_result.get("per_division_comparison_topdown", []):
        div = entry["division"]
        pct = entry.get("MAE_change_pct")
        mae_report[div] = pct
        if pct is not None and abs(pct) > mae_threshold:
            mae_failed.append(f"{div}: backtest MAE changed {pct:.1f}% (> {mae_threshold}% threshold)")
    violations += mae_failed
    mae_compared = [d for d, p in mae_report.items() if p is not None]
    gates["backtest_mae"] = (_gate(GATE_FAILED, "; ".join(mae_failed)) if mae_failed else
                             _gate(GATE_PASSED, f"{len(mae_compared)} divisions within {mae_threshold}% of the last successful run") if mae_compared else
                             _gate(GATE_NOT_TESTED, step4_result.get("comparison_base", "no earlier run log to compare with")))

    # ---- (c) total on-hand stock: this run's stock pull against the latest successful daily stock run's published stock ----
    stock_report = {"threshold_pct": stock_threshold}
    baseline = last_daily_stock_baseline()
    new_total = monthly_pull_on_hand_total()
    if baseline is None:
        gates["on_hand_stock"] = _gate(GATE_NOT_TESTED, "no successful daily stock run is recorded (output/runs/daily/last_success.json), so there is no baseline")
    elif new_total is None:
        gates["on_hand_stock"] = _gate(GATE_NOT_TESTED, "this run saved no stock pull (output/data/inventory_pull), so there is no new total")
    elif not baseline["on_hand_total"]:
        gates["on_hand_stock"] = _gate(GATE_NOT_TESTED, "the daily baseline total is zero, so a change cannot be expressed as a percentage")
    else:
        pct = 100 * (new_total - baseline["on_hand_total"]) / baseline["on_hand_total"]
        stock_report.update({"baseline_on_hand_total": baseline["on_hand_total"], "baseline_pull_time": baseline["pull_time"],
                             "baseline_daily_run_id": baseline["run_id"], "new_on_hand_total": new_total, "change_pct": pct})
        if abs(pct) > stock_threshold:
            msg = f"total on-hand stock changed {pct:.1f}% against the daily run of {baseline['pull_time']} (> {stock_threshold}% threshold)"
            violations.append(msg)
            gates["on_hand_stock"] = _gate(GATE_FAILED, msg)
        else:
            gates["on_hand_stock"] = _gate(GATE_PASSED, f"{pct:+.1f}% against the daily run of {baseline['pull_time']} (threshold {stock_threshold}%)")
    if os.path.exists(INVENTORY_JSON_PATH):
        with open(INVENTORY_JSON_PATH, "r", encoding="utf-8") as f:
            stock_report["current_totals"] = json.load(f).get("totals")

    counts = count_gates(gates)
    return {
        "thresholds": {"six_month_forecast_change_pct": six_mo_threshold,
                        "backtest_mae_change_pct": mae_threshold,
                        "total_on_hand_stock_change_pct": stock_threshold},
        "gates": gates,
        "gate_counts": counts,
        "six_month_forecast_by_division": six_mo_report,
        "backtest_mae_change_pct_by_division": mae_report,
        "total_on_hand_stock": stock_report,
        "violations": violations,
        "passed": counts[GATE_FAILED] == 0,
    }


def gate_outcomes(step8: dict, step9: dict, step10: dict) -> dict:
    """Every gate of the run (tests, sensitive-content scan, the three change-magnitude gates) as passed, failed or not tested, with
    the counts. A skipped test run is not tested, not passed."""
    gates = {"tests": (_gate(GATE_NOT_TESTED, step8.get("summary_line", "tests skipped")) if step8.get("skipped") else
                       _gate(GATE_PASSED if step8.get("passed") else GATE_FAILED, step8.get("summary_line", ""))),
             "sensitive_content_scan": _gate(GATE_PASSED if step9.get("passed") else GATE_FAILED,
                                             f"{len(step9.get('findings', []))} findings in {step9.get('n_changed_files_scanned', 0)} files")}
    for name, g in step10.get("gates", {}).items():
        gates["step10_" + name] = g
    return {"gates": gates, "counts": count_gates(gates), "not_tested": sorted(n for n, g in gates.items() if g["status"] == GATE_NOT_TESTED)}


# ---------------------------------------------------------------------------------------------
# Step 11: commit and push only if steps 8 to 10 all pass
# ---------------------------------------------------------------------------------------------

# The only tracked files a run generates (step 7; step 11 stages exactly these, never `git add -A`).
GENERATED_PATHS = ["forecast/sales_report.html", "forecast/inventory.html", "forecast/operation_plan.html", "forecast/material_plan.html",
                   "data/inventory.json", "data/stock_daily.json", "data/assumptions.json"]


def _git_status_lines() -> list:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=PROJECT_ROOT,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def _porcelain_path(line: str) -> str:
    path = line[3:]
    return path.split(" -> ")[-1].strip().strip('"').replace("\\", "/")


def stray_changes_outside_generated_list() -> list:
    """Tracked paths that are staged, modified, deleted or renamed and are not in GENERATED_PATHS (untracked files
    are never staged by an explicit add, so they are not stray here)."""
    return sorted({_porcelain_path(l) for l in _git_status_lines()} - set(GENERATED_PATHS))


def _git_path_changed(path: str) -> bool:
    return any(_porcelain_path(l) == path for l in _git_status_lines())


def step11_commit_and_push(dry_run: bool, step8: dict, step9: dict, step10: dict) -> dict:
    gates_passed = bool(step8["passed"] and step9["passed"] and step10["passed"])
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
    stray = stray_changes_outside_generated_list()
    if stray:
        raise MonthlyRefreshAbort(
            "Step 11 STOPPED before staging: these paths are staged or modified but are not on the list of files the "
            "run generates (GENERATED_PATHS): " + ", ".join(stray) + ". Nothing was staged, committed or pushed; "
            "a person must look at them.")
    to_stage = [p for p in GENERATED_PATHS if _git_path_changed(p)]
    if not to_stage:
        return {"pushed": False, "committed": False, "nothing_to_commit": True,
                "reason": "nothing the run generates has changed -- no commit."}
    subprocess.run(["git", "add", "--"] + to_stage, cwd=PROJECT_ROOT, check=True)
    subprocess.run(["git", "commit", "-m", "Automated monthly refresh"], cwd=PROJECT_ROOT, check=True)
    push = subprocess.run(["git", "push", "origin", "main"], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"pushed": push.returncode == 0, "reason": push.stdout + push.stderr}


# ---------------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------------

COPY_SKIP_TOP = {".git", ".pytest_cache", "node_modules", ".claude", "__pycache__"}
COPY_SKIP_OUTPUT = {"runs", "charts"}   # charts is recreated empty: regeneration scripts save their figures there
IN_SANDBOX = os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1"


def _copy_project(dst: str) -> None:
    os.makedirs(os.path.join(dst, "output", "charts"), exist_ok=True)
    """Copies what a run reads and writes into `dst`: everything at the project root except version
    control and caches, and under output/ only data, summary (without its archive) and snapshots."""
    for name in os.listdir(PROJECT_ROOT):
        if name in COPY_SKIP_TOP:
            continue
        src = os.path.join(PROJECT_ROOT, name)
        if name == "output":
            for sub in os.listdir(src):
                if sub in COPY_SKIP_OUTPUT:
                    continue
                sub_src = os.path.join(src, sub)
                sub_dst = os.path.join(dst, "output", sub)
                if os.path.isdir(sub_src):
                    shutil.copytree(sub_src, sub_dst, ignore=shutil.ignore_patterns("archive", "__pycache__"))
                else:
                    os.makedirs(os.path.dirname(sub_dst), exist_ok=True)
                    shutil.copy2(sub_src, sub_dst)
        elif os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, name), ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copy2(src, os.path.join(dst, name))


def _copy_run_logs(dst: str) -> None:
    """Step 10 and step 4 read the last successful run's log: the temporary copy gets the real run logs (read-only use)."""
    out = os.path.join(dst, "output", "runs")
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(RUNS_DIR) if os.path.isdir(RUNS_DIR) else []:
        if name.startswith("monthly_refresh_") and name.endswith(".json"):
            shutil.copy2(os.path.join(RUNS_DIR, name), os.path.join(out, name))
    # step 10's on-hand gate compares with the latest successful daily stock run (its last_success.json)
    last_success = os.path.join(PROJECT_ROOT, load_config()["daily_stock"]["last_success_file"])
    if os.path.exists(last_success):
        target = os.path.join(dst, load_config()["daily_stock"]["last_success_file"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(last_success, target)


def run_dry_run_in_sandbox(force_new_vintage: bool = False, offline: bool = False, skip_tests: bool = False) -> dict:
    """A dry run: everything runs inside a temporary copy of the project; only the run log is written to the real output/runs/."""
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    temp_root = tempfile.mkdtemp(prefix="monthly_refresh_dry_")
    logger.info("Dry run: working in a temporary copy at %s (removed afterwards).", temp_root)
    try:
        _copy_project(temp_root)
        _copy_run_logs(temp_root)
        cmd = [sys.executable, os.path.join(temp_root, "src", "monthly_refresh.py"), "--dry-run", "--in-sandbox",
               "--run-id", run_id, "--run-log-dir", RUNS_DIR]
        if force_new_vintage:
            cmd.append("--force-new-vintage")
        if offline:
            cmd.append("--offline")
        if skip_tests:
            cmd.append("--skip-tests")
        env = dict(os.environ, MONTHLY_REFRESH_SANDBOX="1", PYTHONIOENCODING="utf-8")
        proc = subprocess.run(cmd, cwd=temp_root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log_path = os.path.join(RUNS_DIR, f"monthly_refresh_{run_id}.json")
        if not os.path.exists(log_path):
            raise MonthlyRefreshAbort(f"Dry run ABORTED before it wrote a run log (exit {proc.returncode}).\n"
                                      f"{proc.stderr[-2500:]}")
        with open(log_path, encoding="utf-8") as f:
            log = json.load(f)
        if proc.returncode != 0 and "aborted_at_step" not in log:
            raise MonthlyRefreshAbort(f"Dry run exited {proc.returncode}: {proc.stderr[-2500:]}")
        return log
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main(dry_run: bool, force_new_vintage: bool = False, sandbox: bool = False, run_id: str = None,
         run_log_dir: str = None, offline: bool = False, skip_tests: bool = False) -> dict:
    if dry_run and not sandbox:
        return run_dry_run_in_sandbox(force_new_vintage, offline, skip_tests)
    run_id = run_id or datetime.now().strftime("%Y%m%dT%H%M%S")
    started_mtime = datetime.now().timestamp()
    staged_dir = os.path.join(RUNS_DIR, run_id, "staged")
    os.makedirs(staged_dir, exist_ok=True)
    config = load_config()
    # Inside a dry-run copy every step writes for real (into the copy); only step 11 stays a dry run.
    steps_dry = dry_run and not sandbox

    run_log = {"run_id": run_id, "dry_run": dry_run, "dry_run_in_temporary_copy": sandbox, "offline": offline,
               "force_new_vintage": force_new_vintage,
               "started_at": datetime.now().isoformat(timespec="seconds"), "steps": {}}

    def record(step_name, fn, *args, **kwargs):
        """Runs one step. Any failure -- a deliberate abort or an uncaught exception -- ends the run with a run
        log naming the failed step, the error and the steps not run (METRICS.md Sec.28: a failed run is reported
        in the log, never silently skipped); nothing is committed or pushed; the exception is re-raised so the
        process exits non-zero."""
        try:
            outcome = fn(*args, **kwargs)
            run_log["steps"][step_name] = {"status": "ok", **({"result": outcome} if outcome is not None else {})}
            return outcome
        except Exception as e:      # noqa: BLE001 -- every failure must reach the run log
            aborted = isinstance(e, MonthlyRefreshAbort)
            run_log["steps"][step_name] = {"status": "ABORTED" if aborted else "FAILED",
                                           "reason" if aborted else "error": str(e)}
            run_log["aborted_at_step"] = step_name
            run_log["failed_step"] = step_name
            run_log["error"] = {"type": type(e).__name__, "message": str(e)[:4000],
                                "traceback_tail": traceback.format_exc()[-3000:]}
            run_log["steps_not_run"] = STEP_ORDER[STEP_ORDER.index(step_name) + 1:]
            run_log["committed"] = False
            run_log["pushed"] = False
            run_log["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_run_log(run_log, run_id, run_log_dir)
            raise

    step1 = record("1_pull_data", step1_pull_data, steps_dry, offline)
    record("2_validate", step2_validate)
    record("3_frozen_snapshot", step3_frozen_snapshot)
    step4 = record("4_backtest", step4_backtest, run_id, offline)
    step5 = record("5_new_forward_test_vintage", step5_new_vintage, steps_dry, force_new_vintage)
    computed_vintage_for_preview = _LAST_COMPUTED_VINTAGE if steps_dry else None
    record("6_fill_and_score", step6_fill_and_score, steps_dry, computed_vintage_for_preview, offline, run_id)
    step7 = record("7_rebuild_pages", step7_rebuild_pages, steps_dry, staged_dir, step1)
    record("7b_operation_plan", step7b_operation_plan, steps_dry, staged_dir, step7)
    record("7c_material_plan", step7c_material_plan, steps_dry, staged_dir)
    step8 = record("8_run_tests", step8_run_tests, skip_tests)
    step9 = record("9_scan_sensitive_content", step9_scan_sensitive_content, started_mtime if sandbox else None)
    step10 = record("10_change_magnitude", step10_change_magnitude, config, step4, step5)
    step11 = record("11_commit_and_push", step11_commit_and_push, dry_run, step8, step9, step10)

    run_log["gate_outcomes"] = gate_outcomes(step8, step9, step10)
    run_log["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_run_log(run_log, run_id, run_log_dir)
    return run_log


def _write_run_log(run_log: dict, run_id: str, run_log_dir: str = None) -> str:
    out_dir = run_log_dir or RUNS_DIR
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"monthly_refresh_{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, indent=2, default=str)
    logger.info("Run log written: %s", path)
    return path


@contextlib.contextmanager
def _runner_lock(real_run: bool):
    """While a real run is in progress its lock file names its process, so the daily stock job can see the monthly
    runner is running and skip publishing (config daily_stock.monthly_lock_file). Dry runs and offline runs write none."""
    if not real_run:
        yield
        return
    path = os.path.join(PROJECT_ROOT, load_config()["daily_stock"]["monthly_lock_file"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "started_at": datetime.now().isoformat(timespec="seconds")}, f)
    try:
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def cli(argv=None) -> int:
    """Command line entry. Exit code 0 only for a run that completed every step; any abort or failure returns 1
    (the run log has already been written by main())."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Exercise every step's logic without writing/committing/pushing anything tracked.")
    parser.add_argument("--force-new-vintage", action="store_true",
                         help="Override the one-vintage-per-calendar-month guard (Part 2, "
                              "task 2cfix2) for a deliberate second real run in the same month. "
                              "Its use is recorded in the run log.")
    parser.add_argument("--in-sandbox", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--run-log-dir", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--offline", action="store_true",
                         help="Make no database connection (for tests): step 1 reuses the data already under "
                              "output/data and the regenerations that connect are skipped and recorded.")
    parser.add_argument("--skip-tests", action="store_true",
                         help="Skip step 8 (for tests of the runner itself; recorded in the run log).")
    args = parser.parse_args(argv)
    try:
        with _runner_lock(real_run=not (args.dry_run or args.in_sandbox or args.offline)):
            log = main(dry_run=args.dry_run, force_new_vintage=args.force_new_vintage, sandbox=args.in_sandbox,
                       run_id=args.run_id, run_log_dir=args.run_log_dir, offline=args.offline, skip_tests=args.skip_tests)
    except Exception as e:      # noqa: BLE001 -- the run log was written where the failure happened
        logger.error("MONTHLY REFRESH FAILED: %s: %s", type(e).__name__, e)
        return 1
    print(json.dumps(log, indent=2, default=str))
    return 1 if "aborted_at_step" in log else 0


if __name__ == "__main__":
    sys.exit(cli())
