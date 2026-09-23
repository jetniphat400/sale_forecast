"""Phase J2 Explorer B -- THE single database connection attempt for this task.

Hypothesis B: due dates are set/moved to match actual delivery (measurement artifact), not
evidence of genuine on-time delivery. Primary source: Cube_CES.

DATABASE ACCESS RULE: one connection attempt only, for this task. On failure: stop, report,
do not retry. This script opens ONE engine/connection and runs every SELECT needed over that
same connection (schema verification + main pull), per src/investigations/phaseJ_single_pull.py
precedent.

Scope: PEM101/PEM103/PEM107 item codes (output/data/phaseI_combined_scope_351items.csv, 351
codes), CtrDate >= 2024-01-01.
"""
import logging
import os
import sys

import pandas as pd

PROJECT_ROOT = r"D:\sale_forecast"
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
from db import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ2_explorerB_pull")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"
COMBINED_SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")
OUT_MAIN = os.path.join(DATA_DIR, "phaseJ2_explorerB_cube_ces_351items_2024on.csv")
OUT_TOP5 = os.path.join(DATA_DIR, "phaseJ2_explorerB_top5_schema_check.csv")
OUT_REVTYPE = os.path.join(DATA_DIR, "phaseJ2_explorerB_revenuetype_status_counts.csv")


def main():
    combined = pd.read_csv(COMBINED_SCOPE_FILE)
    codes = sorted(combined["code"].unique())
    code_list = "','".join(codes)
    logger.info("Loaded %d item codes from combined scope file.", len(codes))

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt for this task now. "
                "No retry on failure.")
    try:
        engine = get_connection()
        conn = engine.connect()
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: the single connection attempt FAILED -- STOPPING, "
                     "not retrying. Error: %r", exc)
        raise

    try:
        # 1. Schema verification -- confirm columns actually exist, don't just trust the task
        #    description.
        top5 = pd.read_sql(f"SELECT TOP 5 * FROM {CES_TABLE}", conn)
        top5.to_csv(OUT_TOP5, index=False)
        logger.info("Schema check: columns = %s", list(top5.columns))

        # 2. Check RevenueType / Status distribution within scope+date filter, to decide/report
        #    what filter to apply (project convention elsewhere is RevenueType='Omni Channel').
        revtype_sql = f"""
            SELECT RevenueType, Status, COUNT(*) AS n_rows
            FROM {CES_TABLE}
            WHERE ItemCode IN ('{code_list}')
              AND CtrDate >= '2024-01-01'
            GROUP BY RevenueType, Status
            ORDER BY RevenueType, Status
        """
        revtype = pd.read_sql(revtype_sql, conn)
        revtype.to_csv(OUT_REVTYPE, index=False)
        logger.info("RevenueType/Status breakdown (scope+date filter only):\n%s", revtype.to_string())

        # 3. Main pull -- all columns needed for the hypothesis test, scope + date filter,
        #    no RevenueType/Status filter applied at SQL level (applied later in pandas, so the
        #    cache stays maximally usable and the filter decision is visible/auditable).
        main_sql = f"""
            SELECT ContractID, ItemCode, CtrDate, PlanDelDate, ForecastDelDate, ActualDelDate,
                   Status, PlanQty, ActualQty, BacklogQty, RevenueType, CustomerID, CustomerName
            FROM {CES_TABLE}
            WHERE ItemCode IN ('{code_list}')
              AND CtrDate >= '2024-01-01'
        """
        main = pd.read_sql(main_sql, conn)
        main.to_csv(OUT_MAIN, index=False)
        logger.info("Main pull: %d rows, %d distinct ItemCode, %d distinct ContractID",
                    len(main), main["ItemCode"].nunique(), main["ContractID"].nunique())
    finally:
        conn.close()
        engine.dispose()

    print(f"OK: top5_cols={list(top5.columns)}")
    print(f"OK: main_rows={len(main)}")


if __name__ == "__main__":
    main()
