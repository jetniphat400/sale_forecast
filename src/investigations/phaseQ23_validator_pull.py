"""Q23 Validator -- Part 6, independent recomputation. Data-access module ONLY (CONVENTIONS.md:
separate data access from computation). Pulls this Validator's OWN fresh copy of the data needed
for all three checks (channel mix, Part-2 same-target accuracy comparison, Part-3 PEM103 combined-
demand calibration) -- does NOT read any cached scope/raw file another agent built this session
(explicit task instruction). Scope codes are pulled directly from reference/pricelist.xlsx via
src/pricelist_reader.py + config['sheet_to_division'], exactly as CONVENTIONS.md requires (pricelist
is authoritative for division; the database's own `division` column is never a filter).

DATABASE ACCESS RULE: exactly one connection attempt. If the first query fails, stop -- do not
retry. Once connected, further queries in the same session are fine (this script issues only one
query, covering everything this task needs in a single pull).
"""
import logging
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import run_query
from pricelist_reader import load_visible_product_rows
from division_utils import assert_no_code_on_multiple_sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseQ23_validator_pull")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"

DIVISIONS = ["PEM101", "PEM103", "PEM107"]
PULL_START = "2023-01-01"  # covers 2023 so the "zero usable rows in 2023" claim is CONFIRMED, not assumed


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_division_scope(config: dict) -> pd.DataFrame:
    """Full pricelist scope for PEM101 (171), PEM103 (87), PEM107 (136) -- code/type/category/division,
    pulled fresh from reference/pricelist.xlsx (visible sheets only), never from a cached scope CSV
    another agent produced this session."""
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    assert_no_code_on_multiple_sheets(pl)
    pl = pl.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    pl["division"] = pl["sheet"].map(config["sheet_to_division"])
    scope = pl[pl["division"].isin(DIVISIONS)][["code", "type", "category", "division"]].copy()
    counts = scope["division"].value_counts().to_dict()
    logger.info("Pricelist scope pulled fresh: %s (expected PEM101=171, PEM103=87, PEM107=136)", counts)
    for div, expected in {"PEM101": 171, "PEM103": 87, "PEM107": 136}.items():
        actual = counts.get(div, 0)
        if actual != expected:
            logger.warning("Division %s: expected %d codes, got %d -- reported as found, not silently corrected.",
                            div, expected, actual)
    return scope


def pull_raw_sales(codes: list) -> pd.DataFrame:
    """ONE query, ALL revenue_type values, NO division filter (division is attached from the
    pricelist scope afterward, per CONVENTIONS.md), status IN ('Actual','MPS'), createDate >=
    2023-01-01 (no upper bound -- pulls everything available as of today, 2026-09-24)."""
    code_list = "','".join(sorted(codes))
    sql = f"""
        SELECT itemcode, createDate, forecast_date, qty, sale, cost, revenue_type, status, contractid
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND status IN ('Actual','MPS')
          AND createDate >= '{PULL_START}'
    """
    logger.info("DATABASE ACCESS RULE: single connection attempt, %d item codes, ALL revenue_type, "
                "no division filter, createDate >= %s.", len(codes), PULL_START)
    try:
        df = run_query(sql)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: first-query connection FAILED -- stopping, not retrying. Error: %r", exc)
        raise
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    neg_qty = df[df["qty"] < 0]
    if len(neg_qty):
        logger.warning("%d rows with negative qty pulled -- kept, flagged for inspection, not silently dropped.",
                        len(neg_qty))
    logger.info("Pulled %d raw rows for %d item codes. revenue_type values seen: %s",
                len(df), len(codes), sorted(df["revenue_type"].dropna().unique().tolist()))
    return df


def main():
    config = load_config()
    scope = load_division_scope(config)
    scope.to_csv(os.path.join(DATA_DIR, "phaseQ23_validator_scope_394items.csv"), index=False)

    codes = sorted(scope["code"].unique())
    raw = pull_raw_sales(codes)
    raw.to_csv(os.path.join(DATA_DIR, "phaseQ23_validator_raw_394items.csv"), index=False)

    n2023 = int((raw["createDate"].dt.year == 2023).sum())
    logger.info("Rows with createDate in 2023: %d (of %d total) -- see report for the 'zero usable rows in "
                "2023' confirmation, which also checks forecast_date-keyed usability, not just createDate.", n2023, len(raw))

    print(f"Scope: {scope['division'].value_counts().to_dict()}")
    print(f"Raw rows pulled: {len(raw)}; max createDate: {raw['createDate'].max()}; "
          f"revenue_type values: {sorted(raw['revenue_type'].dropna().unique().tolist())}")
    print(f"Rows with createDate in 2023: {n2023}")
    print("Saved: output/data/phaseQ23_validator_scope_394items.csv, phaseQ23_validator_raw_394items.csv")


if __name__ == "__main__":
    main()
