"""Scores output/summary/forward_test_log_all_divisions.csv (335 items, 5 divisions) against
realised actuals, for whichever target months have since become available AND safely closed in
the database.

Reuses src/score_forward_test_v2.py's two innovations UNCHANGED in spirit, adapted for the new
schema/scope:
  1. CONSISTENCY CHECK, extended with a `divisions` check (the new log's `division` column has no
     equivalent in v2's schema) alongside config_version/date_key/item_level_approach/scope_hash/
     scope_n_items — refuses to score (raises ForwardTestConsistencyError) if the log's own
     recorded metadata no longer matches config.yaml or the current 335-item scope file
     (output/summary/phaseC_step2_scope_335items.csv), so this script can never be pointed at a
     stale or mismatched log. In particular, this MUST refuse to score the archived 128-item log
     (output/summary/archive/forward_test_log_v2_128items_superseded_2026-09-07.csv) — its
     recorded scope_hash/scope_n_items belong to the 128-item scope, not the current 335.
  2. LEAKAGE-MARGIN-AWARE completeness (src/leakage_guard.check_window_closed) — a target month
     is only scored once min_margin_days have cleared past its calendar end, not merely once
     today's date has passed it.

DIVISION-AWARE ACTUALS PULL: Type/Category level rows in the new log are keyed by (itemcode=name,
division), not by name alone (STATUS.md: Category/Type names collide across divisions) — so
actuals are aggregated by (division, type) / (division, category), matching the log's own
`division` column, and merged on (itemcode, division, level, target_month), not just
(itemcode, level, target_month) as v2 did (v2 had only one division, so needed no such key).
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
logger = logging.getLogger("score_forward_test_all_divisions")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DEFAULT_LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions.csv")
DEFAULT_METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions_metadata.json")
DEFAULT_SCORED_OUTPUT = os.path.join(SUMMARY_DIR, "forward_test_scored_all_divisions.csv")
DEFAULT_SUMMARY_OUTPUT = os.path.join(SUMMARY_DIR, "forward_test_model_summary_all_divisions.csv")
SCOPE_FILE = os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def verify_consistency(metadata: dict, current_config: dict, current_scope_codes: list,
                        current_divisions: list) -> None:
    """Raises ForwardTestConsistencyError (never returns a bool/warning) if ANY of
    config_version, date_key, item_level_approach, scope_hash, scope_n_items, or divisions
    recorded in `metadata` at generation time no longer matches the CURRENT config.yaml / CURRENT
    335-item scope. Returns None if everything matches."""
    current_cfg_ver = config_version()
    current_date_key = current_config.get("adopted_series_key")
    current_approach = current_config.get("adopted_item_level_approach")
    current_scope_codes = sorted(set(current_scope_codes))
    current_scope_hash = compute_scope_hash(current_scope_codes)
    current_n_items = len(current_scope_codes)
    current_divisions_sorted = sorted(set(current_divisions))

    recorded_divisions = metadata.get("divisions")
    recorded_divisions_sorted = sorted(recorded_divisions) if recorded_divisions else None

    checks = [
        ("config_version", metadata.get("config_version"), current_cfg_ver),
        ("date_key", metadata.get("date_key"), current_date_key),
        ("item_level_approach", metadata.get("item_level_approach"), current_approach),
        ("scope_hash", metadata.get("scope_hash"), current_scope_hash),
        ("scope_n_items", metadata.get("scope_n_items"), current_n_items),
        ("divisions", recorded_divisions_sorted, current_divisions_sorted),
    ]
    failures = [(name, recorded, current) for name, recorded, current in checks if str(recorded) != str(current)]
    if failures:
        lines = "\n".join(f"  - {name}: log/metadata recorded '{recorded}', CURRENT value is '{current}'"
                           for name, recorded, current in failures)
        raise ForwardTestConsistencyError(
            "REFUSING TO SCORE -- this forward-test log's recorded configuration does not match the "
            "CURRENT project state:\n" + lines + "\n"
            "A log whose recorded config_version, series key, adopted approach, item scope, or "
            "division set does not match what is CURRENTLY configured cannot be safely scored. "
            "Regenerate the log with src/forward_test_all_divisions.py before scoring, or "
            "investigate why config.yaml / the scope file drifted since this log was generated."
        )
    logger.info("Consistency check PASSED: config_version=%s, date_key=%s, item_level_approach=%s, "
                "scope_hash=%s (%d items, divisions %s) all match the CURRENT config.yaml / "
                "%s.", current_cfg_ver, current_date_key, current_approach, current_scope_hash,
                current_n_items, current_divisions_sorted, SCOPE_FILE)


def target_month_safe_to_score(target_month: str, now: pd.Timestamp, min_margin_days: int) -> bool:
    try:
        check_window_closed(target_month, now, min_margin_days)
        return True
    except LeakageGuardError:
        return False


def pull_actuals_forecastDate(config: dict, scope: pd.DataFrame, target_months: list) -> pd.DataFrame:
    """Pulls forecast_date-keyed actual qty for every item in `scope` (all 335 codes), for the
    given (already leakage-margin-cleared) target_months, then rolls item-level actuals up to
    division-qualified Type and Category level. Returns columns: itemcode, division, level,
    target_month, realised_actual_qty. No division filter on the query itself (2026-09-04
    correction) -- division is attached from `scope`, exactly as every other script in this
    project's corrected pipeline does."""
    source_table = config["source_table"]
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    item_codes = sorted(scope["code"].unique())
    code_list = "','".join(item_codes)
    status_list = "','".join(statuses)
    min_month, max_month = min(target_months), max(target_months)
    sql = f"""
        SELECT itemcode, forecast_date, qty
        FROM {source_table}
        WHERE itemcode IN ('{code_list}') AND revenue_type = '{revenue_type}'
          AND status IN ('{status_list}')
          AND forecast_date >= '{min_month}-01' AND forecast_date < DATEADD(MONTH, 1, '{max_month}-01')
    """
    raw = run_query(sql)
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"])
    raw["target_month"] = raw["forecast_date"].dt.to_period("M").astype(str)
    item_actual = raw.groupby(["itemcode", "target_month"], as_index=False)["qty"].sum()

    full_index = pd.MultiIndex.from_product([item_codes, target_months], names=["itemcode", "target_month"])
    item_actual = pd.DataFrame(index=full_index).reset_index().merge(
        item_actual, on=["itemcode", "target_month"], how="left")
    item_actual["qty"] = item_actual["qty"].fillna(0.0)
    item_actual = item_actual.merge(scope[["code", "division", "category", "type"]],
                                     left_on="itemcode", right_on="code")

    type_actual = item_actual.groupby(["division", "type", "target_month"], as_index=False)["qty"].sum().rename(
        columns={"type": "itemcode"})
    cat_actual = item_actual.groupby(["division", "category", "target_month"], as_index=False)["qty"].sum().rename(
        columns={"category": "itemcode"})

    item_actual["level"] = "Item"
    type_actual["level"] = "Type"
    cat_actual["level"] = "Category"

    combined = pd.concat([
        item_actual[["itemcode", "division", "level", "target_month", "qty"]],
        type_actual[["itemcode", "division", "level", "target_month", "qty"]],
        cat_actual[["itemcode", "division", "level", "target_month", "qty"]],
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
        logger.warning("Forward-test log or metadata not found (%s / %s) -- run "
                        "forward_test_all_divisions.py first", args.log_path, args.metadata_path)
        sys.exit(0)

    config = load_config()
    metadata = load_metadata(args.metadata_path)
    scope = pd.read_csv(SCOPE_FILE)

    # ---- STEP 1: consistency check -- raises and halts on mismatch ----
    verify_consistency(metadata, config, scope["code"].tolist(), scope["division"].tolist())

    log = pd.read_csv(args.log_path, dtype=str)
    log["forecast_qty"] = log["forecast_qty"].astype(float)
    log["horizon"] = log["horizon"].astype(int)

    min_margin_days = load_min_margin_days(config)
    now = pd.Timestamp.now()
    target_months = sorted(log["target_month"].unique())
    safe_months = [m for m in target_months if target_month_safe_to_score(m, now, min_margin_days)]
    unsafe_months = [m for m in target_months if m not in safe_months]

    logger.info("Forward-test log (all divisions) has %d rows covering target months %s", len(log), target_months)
    logger.info("%d target months are safe to score now (>= %d days past month-end, leakage-guard margin): %s",
                len(safe_months), min_margin_days, safe_months)
    if unsafe_months:
        logger.info("%d target months are not yet safe to score (calendar-complete but inside the "
                    "%d-day leakage margin, or not yet complete at all) -- left unscored, not fabricated: %s",
                    len(unsafe_months), min_margin_days, unsafe_months)

    if not safe_months:
        logger.info("No target months are safe to score yet. Re-run this script after time has passed.")
        log.to_csv(args.scored_output, index=False)
        print(f"No safe-to-score target months yet -- nothing scored. "
              f"First scoreable month and readiness date are reported below regardless.")
        first_target = target_months[0]
        window_end = pd.Period(first_target, freq="M").end_time.normalize()
        ready_date = window_end + pd.Timedelta(days=int(min_margin_days))
        print(f"First target month: {first_target} (month-end {window_end.date()}). "
              f"Leakage-guard margin ({min_margin_days} days) clears on {ready_date.date()}.")
        sys.exit(0)

    actuals = pull_actuals_forecastDate(config, scope, safe_months)
    scored = log.merge(actuals, on=["itemcode", "division", "level", "target_month"], how="left")
    scoreable_mask = scored["target_month"].isin(safe_months)
    scored.loc[scoreable_mask, "actual_qty"] = scored.loc[scoreable_mask, "realised_actual_qty"].fillna(0.0)
    scored["error"] = scored["forecast_qty"] - pd.to_numeric(scored["actual_qty"], errors="coerce")
    scored["abs_error"] = scored["error"].abs()

    scored.to_csv(args.scored_output, index=False)
    logger.info("Wrote scored output: %s", args.scored_output)

    scoreable = scored[scoreable_mask].dropna(subset=["error"])
    if len(scoreable):
        summary = scoreable.groupby(["division", "level", "model"], as_index=False).agg(
            MAE=("abs_error", "mean"), Bias=("error", "mean"), n=("error", "size")
        ).sort_values(["division", "level", "MAE"])
        summary.to_csv(args.summary_output, index=False)
        print("\nForward-test scoring (all divisions, real future periods only, leakage-margin-cleared):")
        print(summary.to_string(index=False))
    else:
        print("Target months are marked safe but no matching actuals were found in the database.")
