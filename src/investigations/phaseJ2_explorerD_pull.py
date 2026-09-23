"""Phase J2 -- Explorer D -- THE single database connection attempt for this task.

Hypothesis D: production runs in batches ahead of orders (jobcode/OLMJobCode/cube_final.jobno
values are production batch references, one itemcode per jobno in ~99.5% of cases, reused across
many unrelated contracts -- STATUS.md ~line 1517-1535). This script pulls the raw data needed to
test that hypothesis for the PEM101/PEM103/PEM107 combined 351-item scope
(output/data/phaseI_combined_scope_351items.csv), 2024 onward.

DATABASE ACCESS RULE (binding, per this task's brief): ONE connection attempt for the whole task.
All SELECTs below run over the SAME engine/connection (see src/investigations/phaseJ_single_pull.py
for precedent). If the initial connection fails, STOP -- do not retry.

Queries (read-only SELECT only):
  0. SELECT TOP 5 * FROM cube_final            -- schema probe: confirm columns, inspect whether
     final_date looks like a production-completion timestamp vs. a document-finalization stamp,
     and check for any OTHER date column not in the brief's known-schema list.
  1. cube_final rows for the 351-item scope (itemcode filter) -- the batch-to-contract allocation
     table itself (jobno, ctrno, itemcode, final_date, job_qty, pono, customer_name, project,
     descriptions).
  2. Cube_CES rows for the 351-item scope (itemcode filter), RevenueType='Omni Channel', including
     OLMJobCode -- used both to verify the ctrno<->ContractID join and, independently, to trace
     OLMJobCode->cube_final.jobno directly (reverse-direction test, task step 3). No Status filter
     at pull time (both 'Actual' and 'Backlog' kept; 'Actual' rows only are used for the
     delivered-contract reverse-direction share) and no CtrDate floor at pull time -- the "2024
     onward" scope filter is applied afterward in pandas so the raw cache stays maximally reusable
     (matches phaseJ_single_pull.py's convention).

cube_Sale_APD (createDate) is NOT re-pulled -- output/data/phaseI_raw_sales_351items.csv already
holds itemcode/createDate/contractid for the same 351-item scope from Phase I and is reused
unchanged as a second PO-date source for the lag calculation.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ2_explorerD_pull")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")

CUBE_FINAL_TABLE = "[salewarehouse].[dbo].[cube_final]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"

CUBE_FINAL_OUT = os.path.join(SUMMARY_DIR, "phaseJ2_explorerD_cube_final_raw.csv")
CUBE_FINAL_SAMPLE_OUT = os.path.join(SUMMARY_DIR, "phaseJ2_explorerD_cube_final_schema_sample.csv")
CES_OUT = os.path.join(SUMMARY_DIR, "phaseJ2_explorerD_cube_ces_raw.csv")


def main():
    scope = pd.read_csv(SCOPE_FILE)
    codes = sorted(scope["code"].unique())
    code_list = "','".join(codes)
    logger.info("Scope: %d item codes (PEM101/PEM103/PEM107 combined, from %s)", len(codes), SCOPE_FILE)

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt for this task now. "
                "No retry on failure.")
    try:
        engine = get_connection()
        with engine.connect() as conn:
            # Query 0: schema probe
            sample = pd.read_sql(f"SELECT TOP 5 * FROM {CUBE_FINAL_TABLE}", conn)
            sample.to_csv(CUBE_FINAL_SAMPLE_OUT, index=False)
            logger.info("cube_final columns: %s", list(sample.columns))

            # Query 1: cube_final for scope items
            cf_sql = f"""
                SELECT jobno, ctrno, customer_name, project, descriptions, final_date,
                       itemcode, pono, job_qty
                FROM {CUBE_FINAL_TABLE}
                WHERE itemcode IN ('{code_list}')
            """
            cube_final = pd.read_sql(cf_sql, conn)
            cube_final.to_csv(CUBE_FINAL_OUT, index=False)
            logger.info("Pulled %d cube_final rows for %d scope items", len(cube_final), len(codes))

            # Query 2: Cube_CES for scope items, with OLMJobCode
            ces_sql = f"""
                SELECT ContractID, ItemCode, OLMJobCode, CtrDate, ForecastDelDate, ActualDelDate,
                       Status, PlanQty, ActualQty, BacklogQty, RevenueType
                FROM {CES_TABLE}
                WHERE ItemCode IN ('{code_list}')
                  AND RevenueType = 'Omni Channel'
            """
            ces = pd.read_sql(ces_sql, conn)
            ces.to_csv(CES_OUT, index=False)
            logger.info("Pulled %d Cube_CES rows for %d scope items", len(ces), len(codes))
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: the single connection attempt failed -- STOPPING, "
                     "not retrying. Error: %r", exc)
        raise

    print(f"OK: cube_final={len(cube_final)} rows, cube_ces={len(ces)} rows, "
          f"schema_sample_cols={list(sample.columns)}")


if __name__ == "__main__":
    main()
