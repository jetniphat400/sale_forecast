"""Phase I (decision-sensitivity sweep) -- THE single database connection attempt for this whole
task, covering PEM101 (128-item pilot scope), PEM103 (87 items) and PEM107 (136 items), 351 codes
total, no overlaps (verified: assert_no_code_on_multiple_sheets already guarantees this at the
pricelist level).

DATABASE ACCESS RULE (per task instruction): one connection attempt only; on failure stop and
report -- do not retry, do not fall back to a different query. Both queries below run over the
SAME sqlalchemy engine/connection object (opened once), not two separate connection attempts.

Pulls everything the entire Phase I sweep needs so no further DB access is required afterward --
every swept assumption (lead time, assembly, review, service level, sellable warehouses, unit-cost
window, frequency threshold, concentration threshold) is recomputed purely from these two cached
CSVs plus the pricelist (local file, no DB).

Columns pulled beyond the existing pipeline's per-script queries (union of everything
phaseE1fix_recompute / phaseE2_pilot_recompute need across their several separate live queries):
  raw sales : itemcode, createDate, forecast_date, qty, sale, cost, status, contractid,
              revenue_type -- serves monthly series, daily series, order-level frequency
              (contractid+createDate), and unit_cost (cost/qty) all from ONE pull.
  inventory : company, warehouse, itemcode, stock, minimum, maximum, reserve_bywa, timestamp --
              serves sellable-stock sweep (different warehouse-code definitions) and the current
              Min/Max comparison baseline.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_connection
from phaseE1_common import PROJECT_ROOT, load_config, load_scope
from phaseE2_pilot_recompute import load_division_scope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseI_single_pull")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"

RAW_SALES_OUT = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")
INV_OUT = os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv")
CODES_OUT = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")


def build_combined_scope(config: dict) -> pd.DataFrame:
    s101 = load_scope(config).assign(division="PEM101")
    s103 = load_division_scope(config, "PEM103").assign(division="PEM103")
    s107 = load_division_scope(config, "PEM107").assign(division="PEM107")
    combined = pd.concat([
        s101[["code", "type", "category", "division", "is_excluded", "is_placeholder", "eligible_for_policy"]],
        s103[["code", "type", "category", "division", "is_excluded", "is_placeholder", "eligible_for_policy"]],
        s107[["code", "type", "category", "division", "is_excluded", "is_placeholder", "eligible_for_policy"]],
    ], ignore_index=True)
    dupes = combined["code"][combined["code"].duplicated()]
    if len(dupes):
        raise ValueError(f"{len(dupes)} codes appear in more than one division's scope -- unexpected: {sorted(set(dupes))}")
    logger.info("Combined scope: %d codes (PEM101=%d, PEM103=%d, PEM107=%d), 0 overlaps confirmed.",
                len(combined), len(s101), len(s103), len(s107))
    return combined


def main():
    config = load_config()
    combined = build_combined_scope(config)
    codes = sorted(combined["code"].unique())
    combined.to_csv(CODES_OUT, index=False)

    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    start_date = config["date_range"]["start"]
    code_list = "','".join(codes)
    status_list = "','".join(statuses)

    sales_sql = f"""
        SELECT itemcode, createDate, forecast_date, qty, sale, cost, status, contractid, revenue_type
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{revenue_type}'
          AND status IN ('{status_list}')
          AND createDate >= '{start_date}'
    """
    inv_sql = f"""
        SELECT company, warehouse, itemcode, stock, minimum, maximum, reserve_bywa, timestamp
        FROM {INV_TABLE} WHERE itemcode IN ('{code_list}')
    """

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt for this task now "
                "(%d codes, both queries over the same connection). No retry on failure.", len(codes))
    try:
        engine = get_connection()
        with engine.connect() as conn:
            raw_sales = pd.read_sql(sales_sql, conn)
            inv = pd.read_sql(inv_sql, conn)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: the single connection attempt failed -- STOPPING, "
                      "not retrying. Error: %r", exc)
        raise

    neg_qty = raw_sales[raw_sales["qty"] < 0]
    if len(neg_qty):
        raise ValueError(f"{len(neg_qty)} rows with negative qty -- must be reviewed, not silently dropped.")

    raw_sales.to_csv(RAW_SALES_OUT, index=False)
    inv.to_csv(INV_OUT, index=False)
    logger.info("Pulled %d raw sales rows and %d inventory rows for %d codes. Cached to:\n  %s\n  %s",
                len(raw_sales), len(inv), len(codes), RAW_SALES_OUT, INV_OUT)
    print(f"OK: raw_sales={len(raw_sales)} rows, inventory={len(inv)} rows, codes={len(codes)}")


if __name__ == "__main__":
    main()
