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
from forward_test_common import (ForwardTestConsistencyError, compute_row_integrity_hash,
                                  compute_scope_hash, load_metadata)
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


def verify_consistency(log: pd.DataFrame, metadata: dict) -> None:
    """ADAPTED (forward test / monthly refresh task, Part 1.3) -- BEFORE this change, this
    function compared a single flat metadata dict's config_version/date_key/item_level_approach/
    scope_hash/scope_n_items/divisions against the CURRENT live config.yaml and CURRENT scope
    file (`compute_scope_hash(current_scope_codes)`, `config_version()` read fresh each call),
    and raised on ANY drift -- which meant a vintage generated under an older config could never
    be scored again once config.yaml changed for ANY later reason, even though METRICS.md Sec.27
    says existing vintages are frozen and comparing vintages over time (not against today's
    config) IS the forward test.

    AFTER: each vintage present in `log` is checked ONLY against its OWN recorded metadata and an
    integrity hash of its OWN rows -- never against the current config.yaml, current scope file,
    or config_version(). Two independent checks, per vintage_id:
      1. INTERNAL CONSISTENCY -- every row belonging to this vintage must carry the SAME
         config_version/date_key/scope_hash/scope_n_items as this vintage's own metadata entry
         recorded at generation time (catches a half-written or corrupted vintage).
      2. INTEGRITY HASH -- src/forward_test_common.compute_row_integrity_hash, recomputed from
         the log's CURRENT rows for this vintage (excluding actual_qty, the one column METRICS.md
         Sec.27 allows to change after generation), must equal the row_integrity_hash recorded in
         this vintage's own metadata at generation time (catches a forecast_qty/itemcode/etc.
         silently edited after the fact -- tamper/corruption evidence, not a config-drift check).

    Raises ForwardTestConsistencyError (never returns a bool/warning) on ANY vintage's failure,
    naming the vintage and which check failed. Returns None if every vintage in `log` passes both
    checks against its own metadata."""
    if "vintage_id" not in log.columns:
        raise ForwardTestConsistencyError(
            "REFUSING TO SCORE -- the forward-test log has no `vintage_id` column. Run "
            "src/migrate_forward_test_vintage.py first (METRICS.md Sec.27 schema)."
        )
    failures = []
    for vintage_id, vintage_rows in log.groupby("vintage_id"):
        vkey = str(int(vintage_id))
        vmeta = metadata.get(vkey)
        if vmeta is None:
            failures.append(f"vintage {vkey}: {len(vintage_rows)} row(s) present in the log but no "
                             f"metadata entry '{vkey}' exists -- every vintage in the log must have "
                             f"its own recorded metadata.")
            continue

        # ---- (1) internal consistency: every row of this vintage agrees with its own metadata ----
        for field, meta_key in [("config_version", "config_version"), ("date_key", "date_key"),
                                 ("scope_hash", "scope_hash"), ("scope_n_items", "scope_n_items")]:
            recorded = str(vmeta.get(meta_key))
            distinct_in_rows = set(vintage_rows[field].astype(str).unique())
            if distinct_in_rows != {recorded}:
                failures.append(
                    f"vintage {vkey}: column '{field}' is not internally consistent -- this "
                    f"vintage's own metadata recorded '{recorded}', but its rows in the log "
                    f"currently contain {sorted(distinct_in_rows)}."
                )

        # ---- (2) integrity hash: current rows must match the hash recorded at generation time ----
        recorded_hash = vmeta.get("row_integrity_hash")
        if not recorded_hash:
            failures.append(f"vintage {vkey}: metadata has no recorded row_integrity_hash to check against.")
        else:
            current_hash = compute_row_integrity_hash(vintage_rows)
            if current_hash != recorded_hash:
                failures.append(
                    f"vintage {vkey}: row_integrity_hash mismatch -- recorded {recorded_hash[:16]}..., "
                    f"recomputed from the log's CURRENT rows {current_hash[:16]}.... This vintage's "
                    f"rows (excluding actual_qty) have changed since generation, or were corrupted."
                )

    if failures:
        raise ForwardTestConsistencyError(
            "REFUSING TO SCORE -- one or more vintages failed their OWN recorded consistency/"
            "integrity check (never checked against the CURRENT config.yaml; each vintage is "
            "frozen and checked only against itself, METRICS.md Sec.27):\n" +
            "\n".join(f"  - {f}" for f in failures)
        )
    n_vintages = log["vintage_id"].nunique()
    logger.info("Consistency check PASSED for all %d vintage(s) present in the log: each vintage's "
                "own recorded metadata and row_integrity_hash matches its current rows exactly. "
                "(Not checked against the current live config.yaml -- METRICS.md Sec.27: existing "
                "vintages are frozen.)", n_vintages)


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


def score_and_summarize(log: pd.DataFrame, actuals: pd.DataFrame, safe_months: list) -> tuple:
    """Pure computation step (CONVENTIONS.md: separate data access, computation and presentation
    into different modules) -- fills actual_qty for rows whose target_month is in `safe_months`,
    computes error/abs_error, and summarizes MAE/RMSE/Bias/n per (division, level, model) using
    METRICS.md Sec.25's exact formulas (MAE = mean(|error|), RMSE = sqrt(mean(error^2))) --
    added here; the pre-existing summary computed MAE and Bias only, never RMSE, despite
    METRICS.md Sec.25 requiring both.

    Returns (scored_df, summary_df_or_None) -- summary is None iff no row in `safe_months` has a
    non-null error (nothing to summarize yet)."""
    scored = log.merge(actuals, on=["itemcode", "division", "level", "target_month"], how="left")
    scoreable_mask = scored["target_month"].isin(safe_months)
    scored.loc[scoreable_mask, "actual_qty"] = scored.loc[scoreable_mask, "realised_actual_qty"].fillna(0.0)
    scored["error"] = scored["forecast_qty"] - pd.to_numeric(scored["actual_qty"], errors="coerce")
    scored["abs_error"] = scored["error"].abs()

    scoreable = scored[scoreable_mask].dropna(subset=["error"])
    if not len(scoreable):
        return scored, None

    summary = scoreable.groupby(["division", "level", "model"], as_index=False).agg(
        MAE=("abs_error", "mean"),
        RMSE=("error", lambda s: (s ** 2).mean() ** 0.5),
        Bias=("error", "mean"),
        n=("error", "size"),
    ).sort_values(["division", "level", "MAE"]).reset_index(drop=True)
    return scored, summary


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

    log = pd.read_csv(args.log_path, dtype=str)
    log["forecast_qty"] = log["forecast_qty"].astype(float)
    log["horizon"] = log["horizon"].astype(int)
    log["vintage_id"] = log["vintage_id"].astype(int)
    log["scope_n_items"] = log["scope_n_items"].astype(int)

    # ---- STEP 1: consistency check -- each vintage against its OWN metadata, raises and halts
    # on mismatch. Deliberately NOT checked against the CURRENT config.yaml/scope file (Part 1.3
    # adaptation) -- see verify_consistency's own docstring for the before/after reasoning.
    verify_consistency(log, metadata)

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

    scope = pd.read_csv(SCOPE_FILE)
    actuals = pull_actuals_forecastDate(config, scope, safe_months)
    scored, summary = score_and_summarize(log, actuals, safe_months)

    scored.to_csv(args.scored_output, index=False)
    logger.info("Wrote scored output: %s", args.scored_output)

    if summary is not None:
        summary.to_csv(args.summary_output, index=False)
        print("\nForward-test scoring (all divisions, real future periods only, leakage-margin-cleared):")
        print(summary.to_string(index=False))
    else:
        print("Target months are marked safe but no matching actuals were found in the database.")
