"""Phase 23, Part 0: diagnose why cube_final pulls filtered on itemcode returned zero rows for
the 351-item PEM101/PEM103/PEM107 scope (DATA_MAP.md Sec.4 Trap 7), find the join that works, and
report match rates in both directions.

DATABASE ACCESS RULE: ONE connection attempt for this whole script. On a failed login, stop and
report the verbatim error -- do not retry. All SELECTs below run over the same connection/session.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase23_part0")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")

CUBE_FINAL_TABLE = "[salewarehouse].[dbo].[cube_final]"
CUBE_SALE_APD_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"


def main():
    scope = pd.read_csv(SCOPE_FILE)
    codes = sorted(scope["code"].unique())
    code_list = "','".join(codes)
    logger.info("Scope: %d item codes across PEM101/PEM103/PEM107", len(codes))

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt now. No retry on failure.")
    try:
        engine = get_connection()
        conn = engine.connect()
    except Exception as exc:
        logger.error("Connection FAILED -- STOPPING, not retrying. Verbatim error: %r", exc)
        print(f"CONNECTION FAILED: {exc!r}")
        return
    logger.info("Connected successfully. Running all queries in this one session.")

    results = {}
    try:
        # --- Step 1: re-run the exact itemcode join that previously returned 0 rows ---
        sql1 = f"SELECT * FROM {CUBE_FINAL_TABLE} WHERE itemcode IN ('{code_list}')"
        step1 = pd.read_sql(sql1, conn)
        results["step1_itemcode_join"] = step1
        logger.info("Step 1 (itemcode IN scope, no date filter): %d rows, %d distinct itemcodes",
                    len(step1), step1["itemcode"].nunique() if len(step1) else 0)

        # --- Step 2: INFORMATION_SCHEMA.COLUMNS for cube_Sale_APD ---
        sql2 = """
            SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'cube_Sale_APD'
            ORDER BY ORDINAL_POSITION
        """
        apd_cols = pd.read_sql(sql2, conn)
        results["apd_columns"] = apd_cols
        apd_cols.to_csv(os.path.join(SUMMARY_DIR, "phase23_part0_cube_sale_apd_columns.csv"), index=False)
        product_like = apd_cols[apd_cols["COLUMN_NAME"].str.contains(
            "product|Product|PID|SKU|item", case=False, na=False)]
        logger.info("cube_Sale_APD has %d columns. Product/item-like column names: %s",
                    len(apd_cols), product_like["COLUMN_NAME"].tolist())

        # --- Step 3: fresh sample of cube_Sale_APD.itemcode and cube_final.itemcode for format check ---
        sql3a = f"SELECT DISTINCT TOP 50 itemcode FROM {CUBE_SALE_APD_TABLE}"
        apd_sample = pd.read_sql(sql3a, conn)
        sql3b = f"SELECT DISTINCT TOP 50 itemcode FROM {CUBE_FINAL_TABLE} ORDER BY itemcode DESC"
        cf_sample = pd.read_sql(sql3b, conn)
        results["apd_itemcode_sample"] = apd_sample
        results["cf_itemcode_sample"] = cf_sample

        def fmt_stats(s, label):
            s = s.astype(str)
            logger.info("%s: n=%d, len min/max=%d/%d, any_leading_ws=%s, any_trailing_ws=%s, "
                        "any_lower=%s, any_upper=%s",
                        label, len(s), s.str.len().min(), s.str.len().max(),
                        (s != s.str.lstrip()).any(), (s != s.str.rstrip()).any(),
                        s.str.contains(r"[a-z]").any(), s.str.contains(r"[A-Z]").any())

        fmt_stats(apd_sample["itemcode"], "cube_Sale_APD.itemcode sample")
        fmt_stats(cf_sample["itemcode"], "cube_final.itemcode sample")

        # --- Step 4: reverse direction -- distinct itemcodes in cube_final table-wide ---
        sql4 = f"SELECT itemcode, COUNT(*) AS n FROM {CUBE_FINAL_TABLE} GROUP BY itemcode"
        cf_distinct = pd.read_sql(sql4, conn)
        results["cf_distinct_itemcodes"] = cf_distinct
        cf_distinct.to_csv(os.path.join(SUMMARY_DIR, "phase23_part0_cf_distinct_itemcodes.csv"), index=False)
        logger.info("cube_final has %d distinct itemcodes table-wide (%d total rows)",
                    len(cf_distinct), cf_distinct["n"].sum())

        scope_set = set(codes)
        cf_set = set(cf_distinct["itemcode"].astype(str))
        reverse_match = cf_set & scope_set
        logger.info("REVERSE: %d of %d distinct cube_final itemcodes are in-scope (%.2f%%)",
                    len(reverse_match), len(cf_set), 100 * len(reverse_match) / len(cf_set) if cf_set else 0)

        # --- Step 5: forward match rate per division ---
        step1_codes = set(step1["itemcode"].astype(str)) if len(step1) else set()
        for div in ["PEM101", "PEM103", "PEM107"]:
            div_codes = set(scope[scope["division"] == div]["code"])
            matched = div_codes & step1_codes
            logger.info("FORWARD %s: %d of %d in-scope items have >=1 cube_final row (%.2f%%)",
                        div, len(matched), len(div_codes), 100 * len(matched) / len(div_codes) if div_codes else 0)
        matched_all = scope_set & step1_codes
        logger.info("FORWARD combined: %d of %d in-scope items have >=1 cube_final row (%.2f%%)",
                    len(matched_all), len(scope_set), 100 * len(matched_all) / len(scope_set))

        if len(step1) > 0:
            step1.to_csv(os.path.join(SUMMARY_DIR, "phase23_part0_cubefinal_scope_pull.csv"), index=False)
            logger.info("Saved step1 pull (%d rows) to phase23_part0_cubefinal_scope_pull.csv "
                        "(contains customer_name -- gitignored, never commit/quote)", len(step1))

    finally:
        conn.close()
        logger.info("Connection closed.")

    print("\n=== SUMMARY ===")
    print(f"Step 1 (itemcode IN scope, unfiltered by date): {len(results['step1_itemcode_join'])} rows")
    print(f"cube_Sale_APD columns: {len(results['apd_columns'])}")
    print(f"cube_final distinct itemcodes table-wide: {len(results['cf_distinct_itemcodes'])}")


if __name__ == "__main__":
    main()
