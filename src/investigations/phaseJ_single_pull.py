"""Phase J -- THE single database connection attempt for this task.

Phase I already cached raw cube_Sale_APD rows (output/data/phaseI_raw_sales_351items.csv) and
Cube_Inventory_Exact rows (output/data/phaseI_inventory_exact_351items.csv) for the same combined
351-item scope (PEM101 128-item pilot + PEM103 87 + PEM107 136, 0 overlaps) -- both are REUSED
here unchanged, no re-pull. The one thing this task needs that Phase I never pulled is Cube_CES
(METRICS.md Sec.18's actual_on_time source: ActualDelDate vs ForecastDelDate).

DATABASE ACCESS RULE: one connection attempt only, for this task -- on failure stop and report.
Covers ONLY the Cube_CES pull (a single query, single connection).

No ManuDivision filter (CONVENTIONS.md: division source-of-truth is the pricelist, never a
database division column) -- division is attached afterward from the already-cached combined
scope file. RevenueType='Omni Channel' and Status IN ('Actual','Backlog') match this project's
existing Cube_CES convention (src/investigations/delivery_performance.py,
src/investigations/investigate_cube_ces.py). No CtrDate lower bound at pull time -- the replay
horizon filter (ForecastDelDate in [2024-01-01, 2026-07-31], the same window as the daily demand
series) is applied afterward in pandas, not in SQL, so the raw cache stays maximally reusable.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_connection
from phaseE1_common import PROJECT_ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ_single_pull")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"
COMBINED_SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")
CES_OUT = os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv")


def main():
    combined = pd.read_csv(COMBINED_SCOPE_FILE)
    codes = sorted(combined["code"].unique())
    code_list = "','".join(codes)

    sql = f"""
        SELECT ContractID, ItemCode, CtrDate, PlanDelDate, ForecastDelDate, ActualDelDate,
               Status, PlanQty, ActualQty, BacklogQty, RevenueType
        FROM {CES_TABLE}
        WHERE ItemCode IN ('{code_list}')
          AND RevenueType = 'Omni Channel'
          AND Status IN ('Actual','Backlog')
    """
    logger.info("DATABASE ACCESS RULE: opening the single connection attempt for this task now "
                "(%d codes, Cube_CES only -- cube_Sale_APD/Cube_Inventory_Exact reused from "
                "Phase I's cache). No retry on failure.", len(codes))
    try:
        engine = get_connection()
        with engine.connect() as conn:
            ces = pd.read_sql(sql, conn)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: the single connection attempt failed -- STOPPING, "
                      "not retrying. Error: %r", exc)
        raise

    ces.to_csv(CES_OUT, index=False)
    logger.info("Pulled %d Cube_CES rows for %d codes. Cached to %s", len(ces), len(codes), CES_OUT)
    print(f"OK: cube_ces={len(ces)} rows, codes={len(codes)}")


if __name__ == "__main__":
    main()
