"""Investigates how far back usable sales history extends, and whether older
years are trustworthy under the current PEM101/Omni Channel filtering
approach. Investigation only — does not modify the analysis period or config.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_history_depth")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def get_58_item_codes():
    pilot = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    codes68 = sorted(pilot[pilot["type"].isin(["High Voltage Distribution Fuse Cutout", "Medium Voltage Surge Arrester"])]["code"].unique())
    code_list = "','".join(codes68)
    present = run_query(f"SELECT DISTINCT itemcode FROM cube_Sale_APD WHERE itemcode IN ('{code_list}')")
    return sorted(present["itemcode"])


if __name__ == "__main__":
    item_codes = get_58_item_codes()
    logger.info("58 pilot item codes confirmed live: %d", len(item_codes))
    code_list = "','".join(item_codes)

    # --- cube_Sale_APD year-by-year, whole table ---
    apd_yearly = run_query("""
        SELECT YEAR(createDate) AS yr, COUNT(*) AS n_rows,
               COUNT(DISTINCT itemcode) AS n_items, COUNT(DISTINCT customerid) AS n_customers,
               SUM(sale) AS total_sale
        FROM cube_Sale_APD GROUP BY YEAR(createDate) ORDER BY yr
    """)
    apd_yearly.to_csv(os.path.join(SUMMARY_DIR, "part1_apd_yearly_whole_table.csv"), index=False)
    logger.info("cube_Sale_APD yearly breakdown (whole table):\n%s", apd_yearly.to_string(index=False))

    # --- Cube_CES year-by-year, whole table ---
    ces_yearly = run_query("""
        SELECT YEAR(CtrDate) AS yr, COUNT(*) AS n_rows,
               COUNT(DISTINCT ItemCode) AS n_items, COUNT(DISTINCT CustomerID) AS n_customers,
               SUM(ContractPrice) AS total_contract_price
        FROM Cube_CES GROUP BY YEAR(CtrDate) ORDER BY yr
    """)
    ces_yearly.to_csv(os.path.join(SUMMARY_DIR, "part1_ces_yearly_whole_table.csv"), index=False)
    logger.info("Cube_CES yearly breakdown (whole table):\n%s", ces_yearly.to_string(index=False))

    # --- 58 pilot items, per year in cube_Sale_APD ---
    pilot_yearly = run_query(f"""
        SELECT YEAR(createDate) AS yr, COUNT(*) AS n_rows,
               COUNT(DISTINCT itemcode) AS n_items_with_rows,
               SUM(qty) AS total_qty, SUM(sale) AS total_sale
        FROM cube_Sale_APD WHERE itemcode IN ('{code_list}')
        GROUP BY YEAR(createDate) ORDER BY yr
    """)
    pilot_yearly.to_csv(os.path.join(SUMMARY_DIR, "part1_pilot58_yearly.csv"), index=False)
    logger.info("58 pilot items yearly breakdown (all divisions/revenue_type/status, unfiltered):\n%s", pilot_yearly.to_string(index=False))

    # --- per-item first and last year seen (any division/revenue_type/status) ---
    item_span = run_query(f"""
        SELECT itemcode, MIN(YEAR(createDate)) AS first_year, MAX(YEAR(createDate)) AS last_year,
               COUNT(DISTINCT YEAR(createDate)) AS n_distinct_years
        FROM cube_Sale_APD WHERE itemcode IN ('{code_list}')
        GROUP BY itemcode ORDER BY first_year, itemcode
    """)
    item_span.to_csv(os.path.join(SUMMARY_DIR, "part1_pilot58_item_first_last_year.csv"), index=False)
    logger.info("Item-level first/last year: %d of 58 items have any row at all in cube_Sale_APD", len(item_span))

    print("\n=== cube_Sale_APD whole-table yearly ===")
    print(apd_yearly.to_string(index=False))
    print("\n=== Cube_CES whole-table yearly ===")
    print(ces_yearly.to_string(index=False))
    print("\n=== 58 pilot items yearly (unfiltered by division/revenue_type/status) ===")
    print(pilot_yearly.to_string(index=False))
    print("\n=== Items with earliest first_year (long-history items) ===")
    print(item_span.sort_values("first_year").head(15).to_string(index=False))
    print("\n=== Items with latest first_year (recent-only items) ===")
    print(item_span.sort_values("first_year", ascending=False).head(15).to_string(index=False))
