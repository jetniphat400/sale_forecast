"""Compares stored forward-test forecasts (output/summary/forward_test_log.csv)
against realised actuals, for whichever target months have since become
available in the database. Run this periodically as time passes.

Never fabricates an actual for a period that has not yet completed — rows
whose target_month has no available complete data are left unscored and
reported separately, not silently dropped or guessed at.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("score_forward_test")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
FORWARD_TEST_LOG = os.path.join(SUMMARY_DIR, "forward_test_log.csv")
SCORED_OUTPUT = os.path.join(SUMMARY_DIR, "forward_test_scored.csv")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def month_is_complete(target_month: str) -> bool:
    period = pd.Period(target_month, freq="M")
    return pd.Timestamp.now().normalize() > period.end_time


def pull_actuals(config: dict, item_codes: list, target_months: list) -> pd.DataFrame:
    source_table = config["source_table"]
    division = config["division"]
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    code_list = "','".join(item_codes)
    status_list = "','".join(statuses)
    min_month = min(target_months)
    max_month = max(target_months)
    sql = f"""
        SELECT itemcode, createDate, qty
        FROM {source_table}
        WHERE itemcode IN ('{code_list}') AND division = '{division}' AND revenue_type = '{revenue_type}'
          AND status IN ('{status_list}')
          AND createDate >= '{min_month}-01' AND createDate < DATEADD(MONTH, 1, '{max_month}-01')
    """
    df = run_query(sql)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["target_month"] = df["createDate"].dt.to_period("M").astype(str)
    return df.groupby(["itemcode", "target_month"])["qty"].sum().reset_index().rename(columns={"qty": "realised_actual_qty"})


if __name__ == "__main__":
    if not os.path.exists(FORWARD_TEST_LOG):
        logger.warning("No forward-test log found at %s — run forward_test.py first", FORWARD_TEST_LOG)
        sys.exit(0)

    config = load_config()
    log = pd.read_csv(FORWARD_TEST_LOG, dtype=str)
    log["forecast_qty"] = log["forecast_qty"].astype(float)

    target_months = sorted(log["target_month"].unique())
    complete_months = [m for m in target_months if month_is_complete(m)]
    incomplete_months = [m for m in target_months if m not in complete_months]

    logger.info("Forward-test log has %d rows covering target months %s", len(log), target_months)
    logger.info("%d target months are complete and scoreable: %s", len(complete_months), complete_months)
    if incomplete_months:
        logger.info("%d target months have not completed yet — left unscored, not fabricated: %s",
                    len(incomplete_months), incomplete_months)

    if not complete_months:
        logger.info("No target months are complete yet. Nothing to score. This is expected immediately "
                    "after the first forecast run — re-run this script after time has passed.")
        log.to_csv(SCORED_OUTPUT, index=False)
        print("No complete target months yet — nothing scored. This is expected on first run.")
        sys.exit(0)

    item_codes = sorted(log["itemcode"].unique())
    actuals = pull_actuals(config, item_codes, complete_months)

    scored = log.merge(actuals, on=["itemcode", "target_month"], how="left")
    scoreable_mask = scored["target_month"].isin(complete_months)
    scored.loc[scoreable_mask, "actual_qty"] = scored.loc[scoreable_mask, "realised_actual_qty"].fillna(0.0)
    scored["error"] = scored["forecast_qty"] - pd.to_numeric(scored["actual_qty"], errors="coerce")
    scored["abs_error"] = scored["error"].abs()

    scored.to_csv(SCORED_OUTPUT, index=False)
    logger.info("Wrote scored output: %s", SCORED_OUTPUT)

    scoreable = scored[scoreable_mask].dropna(subset=["error"])
    if len(scoreable):
        summary = scoreable.groupby("model").agg(
            MAE=("abs_error", "mean"), Bias=("error", "mean"), n=("error", "size")
        ).reset_index().sort_values("MAE")
        summary.to_csv(os.path.join(SUMMARY_DIR, "forward_test_model_summary.csv"), index=False)
        print("\nForward-test scoring (real future periods only):")
        print(summary.to_string(index=False))
    else:
        print("Target months are marked complete but no matching actuals were found in the database.")
