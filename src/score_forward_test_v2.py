"""Scores output/summary/forward_test_log_v2.csv against realised actuals, for whichever target
months have since become available AND safely closed in the database.

Supersedes src/score_forward_test.py for the current (v2, 128-item, Top-down, forecast_date-
keyed) log -- src/score_forward_test.py is left unmodified so it can still score the archived
58-item createDate log if ever needed for historical reference (see
output/summary/archive/SUPERSEDED_forward_test_log_58items_createDate_README.txt), but it must
NEVER be pointed at forward_test_log_v2.csv: it pulls actuals keyed on createDate and has no
consistency check, both wrong for this log.

TWO THINGS THIS SCRIPT DOES THAT src/score_forward_test.py DID NOT
-------------------------------------------------------------------
1. CONSISTENCY CHECK (this task's new requirement). Before scoring anything, verifies the log's
   companion metadata file (forward_test_log_v2_metadata.json: config_version, date_key,
   item_level_approach, scope_hash, scope_n_items) matches, right now:
     - config_version: md5 of the CURRENT config/config.yaml (src/forward_test.config_version).
     - date_key / item_level_approach: config.yaml's CURRENT adopted_series_key /
       adopted_item_level_approach (added to config.yaml by this task, see its comments there).
     - scope_hash / scope_n_items: recomputed from the CURRENT
       output/summary/part1_category_scope_all_codes.csv item-code set
       (src/forward_test_common.compute_scope_hash).
   Any mismatch raises ForwardTestConsistencyError with a message stating exactly which field(s)
   mismatched and what the recorded vs. current values are -- refuses to score, never scores a
   stale/mismatched log silently. See src/forward_test_common.py for the exception and the
   verify_consistency() function below for the check itself.
2. LEAKAGE-MARGIN-AWARE completeness, not just calendar completeness. The original
   score_forward_test.py's month_is_complete() only checked whether today's calendar date has
   passed a target month's end. For a forecast_date-keyed series that is NOT sufficient (Phase A;
   src/leakage_guard.py; config.yaml leakage_guard.min_margin_days): forecast_date-keyed rows for
   an already-elapsed calendar month can still be entered/revised for some time after that month
   closes, so a query run the day after month-end could under-count that month's true total. This
   script instead reuses src/leakage_guard.check_window_closed with the SAME min_margin_days
   config value the rest of this project's backtests already enforce, requiring that many days of
   clearance between "now" (the actuals pull) and a target month's end before treating it as safe
   to score. A target month can therefore be calendar-complete but still correctly held back here.
"""
import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from forward_test import config_version
from forward_test_common import ForwardTestConsistencyError, compute_scope_hash, load_metadata
from leakage_guard import LeakageGuardError, check_window_closed, load_min_margin_days

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("score_forward_test_v2")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DEFAULT_LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_v2.csv")
DEFAULT_METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_v2_metadata.json")
DEFAULT_SCORED_OUTPUT = os.path.join(SUMMARY_DIR, "forward_test_scored_v2.csv")
DEFAULT_SUMMARY_OUTPUT = os.path.join(SUMMARY_DIR, "forward_test_model_summary_v2.csv")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def verify_consistency(metadata: dict, current_config: dict, current_scope_codes: list) -> None:
    """Raises ForwardTestConsistencyError (never returns a bool/warning -- CONVENTIONS.md:
    validation failures must be raised loudly) if ANY of config_version, date_key,
    item_level_approach, scope_hash, scope_n_items recorded in `metadata` at generation time no
    longer matches the CURRENT config.yaml / CURRENT scope. Returns None if everything matches."""
    current_cfg_ver = config_version()
    current_date_key = current_config.get("adopted_series_key")
    current_approach = current_config.get("adopted_item_level_approach")
    current_scope_codes = sorted(set(current_scope_codes))
    current_scope_hash = compute_scope_hash(current_scope_codes)
    current_n_items = len(current_scope_codes)

    checks = [
        ("config_version", metadata.get("config_version"), current_cfg_ver),
        ("date_key", metadata.get("date_key"), current_date_key),
        ("item_level_approach", metadata.get("item_level_approach"), current_approach),
        ("scope_hash", metadata.get("scope_hash"), current_scope_hash),
        ("scope_n_items", metadata.get("scope_n_items"), current_n_items),
    ]
    failures = [(name, recorded, current) for name, recorded, current in checks if str(recorded) != str(current)]
    if failures:
        lines = "\n".join(f"  - {name}: log/metadata recorded '{recorded}', CURRENT value is '{current}'"
                           for name, recorded, current in failures)
        raise ForwardTestConsistencyError(
            "REFUSING TO SCORE -- this forward-test log's recorded configuration does not match the "
            "CURRENT project state:\n" + lines + "\n"
            "A log whose recorded config_version, series key, adopted approach, or item scope does not "
            "match what is CURRENTLY configured cannot be safely scored: it would compare forecasts built "
            "under a different method, series key, or item scope to actuals pulled under today's. "
            "Regenerate the log with src/forward_test_v2.py (it recomputes all of the above from the "
            "live current state) before scoring, or investigate why config.yaml / the scope file drifted "
            "since this log was generated."
        )
    logger.info("Consistency check PASSED: config_version=%s, date_key=%s, item_level_approach=%s, "
                "scope_hash=%s (%d items) all match the CURRENT config.yaml / "
                "part1_category_scope_all_codes.csv.", current_cfg_ver, current_date_key,
                current_approach, current_scope_hash, current_n_items)


def target_month_safe_to_score(target_month: str, now: pd.Timestamp, min_margin_days: int) -> bool:
    """A target month is safe to pull actuals for only once at least min_margin_days have
    elapsed since that month's calendar end (src/leakage_guard.py's own margin, reused here --
    NOT the original score_forward_test.py's plain "today > month end" check, which is too loose
    for a forecast_date-keyed series; see this module's docstring, point 2)."""
    try:
        check_window_closed(target_month, now, min_margin_days)
        return True
    except LeakageGuardError:
        return False


def pull_actuals_forecastDate(config: dict, scope: pd.DataFrame, target_months: list) -> pd.DataFrame:
    """Pulls forecast_date-keyed actual qty for every item in `scope` (all 128 codes, not just
    the 113 with prior history -- a previously-zero-history item could have its first-ever sale
    land in a forward-test target month), for the given (already leakage-margin-cleared)
    target_months, then rolls the item-level actuals up to Type and Category level too, so all
    three levels present in forward_test_log_v2.csv can be scored consistently.
    Returns columns: itemcode, level, target_month, realised_actual_qty.
    """
    source_table = config["source_table"]
    division = config["division"]
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    item_codes = sorted(scope["code"].unique())
    code_list = "','".join(item_codes)
    status_list = "','".join(statuses)
    min_month, max_month = min(target_months), max(target_months)
    sql = f"""
        SELECT itemcode, forecast_date, qty
        FROM {source_table}
        WHERE itemcode IN ('{code_list}') AND division = '{division}' AND revenue_type = '{revenue_type}'
          AND status IN ('{status_list}')
          AND forecast_date >= '{min_month}-01' AND forecast_date < DATEADD(MONTH, 1, '{max_month}-01')
    """
    raw = run_query(sql)
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"])
    raw["target_month"] = raw["forecast_date"].dt.to_period("M").astype(str)
    item_actual = raw.groupby(["itemcode", "target_month"], as_index=False)["qty"].sum()

    # Full grid (every scope item x every target month), zero-filled where no matching rows --
    # matches this project's convention elsewhere (e.g. load_data_full.py's reindexed monthly
    # grid) of representing "no demand" as an explicit 0, not a missing row.
    full_index = pd.MultiIndex.from_product([item_codes, target_months], names=["itemcode", "target_month"])
    item_actual = pd.DataFrame(index=full_index).reset_index().merge(
        item_actual, on=["itemcode", "target_month"], how="left")
    item_actual["qty"] = item_actual["qty"].fillna(0.0)
    item_actual = item_actual.merge(scope[["code", "category", "type"]], left_on="itemcode", right_on="code")

    type_actual = item_actual.groupby(["type", "target_month"], as_index=False)["qty"].sum().rename(columns={"type": "itemcode"})
    cat_actual = item_actual.groupby(["category", "target_month"], as_index=False)["qty"].sum().rename(columns={"category": "itemcode"})

    item_actual["level"] = "Item"
    type_actual["level"] = "Type"
    cat_actual["level"] = "Category"

    combined = pd.concat([
        item_actual[["itemcode", "level", "target_month", "qty"]],
        type_actual[["itemcode", "level", "target_month", "qty"]],
        cat_actual[["itemcode", "level", "target_month", "qty"]],
    ], ignore_index=True)
    return combined.rename(columns={"qty": "realised_actual_qty"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    parser.add_argument("--metadata-path", default=DEFAULT_METADATA_PATH)
    parser.add_argument("--scored-output", default=DEFAULT_SCORED_OUTPUT)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    args = parser.parse_args()

    if not os.path.exists(args.log_path) or not os.path.exists(args.metadata_path):
        logger.warning("Forward-test log or metadata not found (%s / %s) -- run forward_test_v2.py first",
                        args.log_path, args.metadata_path)
        sys.exit(0)

    config = load_config()
    metadata = load_metadata(args.metadata_path)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))

    # ---- STEP 1: consistency check (this task's new requirement) -- raises and halts on mismatch ----
    verify_consistency(metadata, config, scope["code"].tolist())

    log = pd.read_csv(args.log_path, dtype=str)
    log["forecast_qty"] = log["forecast_qty"].astype(float)
    log["horizon"] = log["horizon"].astype(int)

    min_margin_days = load_min_margin_days(config)
    now = pd.Timestamp.now()
    target_months = sorted(log["target_month"].unique())
    safe_months = [m for m in target_months if target_month_safe_to_score(m, now, min_margin_days)]
    unsafe_months = [m for m in target_months if m not in safe_months]

    logger.info("Forward-test log v2 has %d rows covering target months %s", len(log), target_months)
    logger.info("%d target months are safe to score now (>= %d days past month-end, leakage-guard margin): %s",
                len(safe_months), min_margin_days, safe_months)
    if unsafe_months:
        logger.info("%d target months are not yet safe to score (calendar-complete but inside the "
                    "%d-day leakage margin, or not yet complete at all) -- left unscored, not fabricated: %s",
                    len(unsafe_months), min_margin_days, unsafe_months)

    if not safe_months:
        logger.info("No target months are safe to score yet. This is expected immediately after the first "
                    "forecast run -- re-run this script after time has passed.")
        log.to_csv(args.scored_output, index=False)
        print("No safe-to-score target months yet -- nothing scored. This is expected on first run.")
        sys.exit(0)

    actuals = pull_actuals_forecastDate(config, scope, safe_months)
    scored = log.merge(actuals, on=["itemcode", "level", "target_month"], how="left")
    scoreable_mask = scored["target_month"].isin(safe_months)
    scored.loc[scoreable_mask, "actual_qty"] = scored.loc[scoreable_mask, "realised_actual_qty"].fillna(0.0)
    scored["error"] = scored["forecast_qty"] - pd.to_numeric(scored["actual_qty"], errors="coerce")
    scored["abs_error"] = scored["error"].abs()

    scored.to_csv(args.scored_output, index=False)
    logger.info("Wrote scored output: %s", args.scored_output)

    scoreable = scored[scoreable_mask].dropna(subset=["error"])
    if len(scoreable):
        summary = scoreable.groupby(["level", "model"], as_index=False).agg(
            MAE=("abs_error", "mean"), Bias=("error", "mean"), n=("error", "size")
        ).sort_values(["level", "MAE"])
        summary.to_csv(args.summary_output, index=False)
        print("\nForward-test v2 scoring (real future periods only, leakage-margin-cleared):")
        print(summary.to_string(index=False))
    else:
        print("Target months are marked safe but no matching actuals were found in the database.")
