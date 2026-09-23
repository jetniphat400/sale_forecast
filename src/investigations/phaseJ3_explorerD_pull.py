"""Phase J3 -- Explorer D -- THE single database connection attempt for this task.

Follow-up to Phase J2 Explorer D (STATUS.md ~line 1262-1273; output/summary/phaseJ2_explorerD_report.md;
DATA_MAP.md Sec.1 cube_final trust note, Sec.4 Trap 7, Sec.5 item 14). That session's cube_final
pull returned ZERO rows for the 351-item scope -- verified an artifact of the pulling agent being
killed mid-task by an infrastructure rate-limit, not a real absence of data (the query is verified
correct and cube_final is known to hold matching item codes from an earlier, separate
investigation, STATUS.md ~line 1584-1601). This script re-runs that exact query with a fresh
connection, pulling EVERY column (not just the original 9) so the production-stage date fields
(finalcheck_date, finalreceive_date, fg_check_date, fg_pack_date, fg_final_date, qacheck_date)
discovered in the schema probe (output/summary/phaseJ2_explorerD_cube_final_schema_sample.csv) are
available to determine which one is the real batch-availability date.

DATABASE ACCESS RULE (binding, per this task's brief): ONE connection attempt for the whole task.
All SELECTs below run over the SAME engine/connection. If the connection fails, STOP -- do not
retry, do not fall back.

Cube_CES (with OLMJobCode), cube_Sale_APD (createDate/contractid) and the 351-item scope file are
all already cached from Phase I/J/J2 (output/data/phaseJ_cube_ces_351items.csv,
output/data/phaseI_raw_sales_351items.csv, output/data/phaseI_combined_scope_351items.csv) and are
reused unchanged -- no new query needed for those.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ3_explorerD_pull")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")

CUBE_FINAL_TABLE = "[salewarehouse].[dbo].[cube_final]"

CUBE_FINAL_OUT = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_cube_final_raw.csv")


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
            # Full-column pull for the 351-item scope -- every column found in the prior
            # schema probe, not just the original 9.
            cf_sql = f"""
                SELECT *
                FROM {CUBE_FINAL_TABLE}
                WHERE itemcode IN ('{code_list}')
            """
            cube_final = pd.read_sql(cf_sql, conn)
            cube_final.to_csv(CUBE_FINAL_OUT, index=False)
            logger.info("Pulled %d cube_final rows (%d columns) for %d scope items",
                        len(cube_final), cube_final.shape[1], len(codes))
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: the single connection attempt failed -- STOPPING, "
                     "not retrying. Error: %r", exc)
        raise

    print(f"OK: cube_final={len(cube_final)} rows, columns={list(cube_final.columns)}")


if __name__ == "__main__":
    main()
