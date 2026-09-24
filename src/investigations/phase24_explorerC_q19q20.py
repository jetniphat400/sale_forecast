"""Phase 24, Explorer C: test whether cube_final's undiscussed production-stage date columns can
answer Q19 (assembly/inspection duration) and give a capacity proxy for Q20.

DATABASE ACCESS RULE: ONE connection attempt for this whole script. On a failed login, stop and
report the verbatim error -- do not retry. All SELECTs below run over the same connection/session.

Reuses the existing 2026-09-24 same-day pull `output/summary/phase23_part0_cubefinal_scope_pull.csv`
(28,005 rows, full 35-column schema, 351-item PEM101/PEM103/PEM107 scope) instead of re-pulling it --
this script's one connection is spent on (a) a fresh live INFORMATION_SCHEMA.COLUMNS check and
(b) pulling the 12-item PEM104 scope, which the existing file does not cover.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_connection
from cube_final_pull import CUBE_FINAL_COLUMNS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase24_explorerC")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

SCOPE_351_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")
PEM104_CODES_FILE = os.path.join(SUMMARY_DIR, "phaseC_PEM104_item_codes.txt")
EXISTING_PULL_351 = os.path.join(SUMMARY_DIR, "phase23_part0_cubefinal_scope_pull.csv")
CACHED_COLUMNS_FILE = os.path.join(SUMMARY_DIR, "phase22_cubefinal_columns.csv")

CUBE_FINAL_TABLE = "[salewarehouse].[dbo].[cube_final]"


def main():
    with open(PEM104_CODES_FILE) as f:
        pem104_codes = [line.strip() for line in f if line.strip()]
    logger.info("PEM104 scope: %d item codes", len(pem104_codes))

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt now. No retry on failure.")
    try:
        engine = get_connection()
        conn = engine.connect()
    except Exception as exc:
        logger.error("Connection FAILED -- STOPPING, not retrying. Verbatim error: %r", exc)
        print(f"CONNECTION FAILED: {exc!r}")
        return
    logger.info("Connected successfully. Running all queries in this one session.")

    try:
        # --- Step 1: fresh live INFORMATION_SCHEMA.COLUMNS check for cube_final ---
        sql_cols = """
            SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'cube_final'
            ORDER BY ORDINAL_POSITION
        """
        live_cols = pd.read_sql(sql_cols, conn)
        live_cols.to_csv(os.path.join(SUMMARY_DIR, "phase24_explorerC_live_columns.csv"), index=False)
        cached_cols = pd.read_csv(CACHED_COLUMNS_FILE)
        # normalize dtype for comparison
        live_cmp = live_cols[["COLUMN_NAME", "DATA_TYPE", "ORDINAL_POSITION"]].reset_index(drop=True)
        cached_cmp = cached_cols[["COLUMN_NAME", "DATA_TYPE", "ORDINAL_POSITION"]].reset_index(drop=True)
        schema_matches = live_cmp.equals(cached_cmp)
        logger.info("Live cube_final schema: %d columns. Matches cached phase22 schema exactly: %s",
                    len(live_cols), schema_matches)
        if not schema_matches:
            logger.warning("SCHEMA DIFFERS from cached file -- diffing.")
            logger.warning("Live:\n%s", live_cmp.to_string())
            logger.warning("Cached:\n%s", cached_cmp.to_string())

        # --- Step 2: pull PEM104's 12 items (not covered by the existing 351-item pull) ---
        code_list = "','".join(pem104_codes)
        col_list = ", ".join(CUBE_FINAL_COLUMNS)
        sql_pem104 = f"""
            SELECT {col_list}
            FROM {CUBE_FINAL_TABLE}
            WHERE itemcode IN ('{code_list}')
        """
        pem104_pull = pd.read_sql(sql_pem104, conn)
        logger.info("PEM104 pull: %d rows, %d distinct itemcodes (of %d scope items)",
                    len(pem104_pull), pem104_pull["itemcode"].nunique() if len(pem104_pull) else 0,
                    len(pem104_codes))
        pem104_pull.to_csv(os.path.join(SUMMARY_DIR, "phase24_explorerC_pem104_pull.csv"), index=False)

        # --- Step 3: table-wide row count and date-column non-null counts, for context on step 2 checks ---
        sql_rowcount = f"SELECT COUNT(*) AS n FROM {CUBE_FINAL_TABLE}"
        rowcount = pd.read_sql(sql_rowcount, conn)
        logger.info("cube_final table-wide row count: %d", rowcount["n"].iloc[0])

    finally:
        conn.close()
        logger.info("Connection closed.")

    print("\n=== SUMMARY ===")
    print(f"Live schema matches cached: {schema_matches}")
    print(f"PEM104 pull: {len(pem104_pull)} rows")
    print(f"cube_final table-wide rows: {rowcount['n'].iloc[0]}")


if __name__ == "__main__":
    main()
