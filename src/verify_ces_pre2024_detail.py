"""Detailed month-by-month examination of Cube_CES 2018-2023 data for the 58
pilot items: gaps, level breaks, unit-price comparison, and column
completeness vs. 2024+. Verification only.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("verify_ces_pre2024_detail")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def get_58_item_codes():
    pilot = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    codes68 = sorted(pilot[pilot["type"].isin(["High Voltage Distribution Fuse Cutout", "Medium Voltage Surge Arrester"])]["code"].unique())
    code_list = "','".join(codes68)
    present = run_query(f"SELECT DISTINCT itemcode FROM cube_Sale_APD WHERE itemcode IN ('{code_list}')")
    return sorted(present["itemcode"])


if __name__ == "__main__":
    item_codes = get_58_item_codes()
    code_list = "','".join(item_codes)

    # Month-by-month breakdown, 2018-2026 (using Actual+Backlog, matching Part 1's verified mapping)
    monthly = run_query(f"""
        SELECT YEAR(CtrDate) AS yr, MONTH(CtrDate) AS mo, COUNT(*) AS n_rows,
               COUNT(DISTINCT ItemCode) AS n_items, COUNT(DISTINCT CustomerID) AS n_customers,
               COUNT(DISTINCT ContractID) AS n_contracts,
               SUM(ActualQty)+SUM(BacklogQty) AS total_qty,
               SUM(ActualPrice)+SUM(BacklogPrice) AS total_value,
               SUM(CASE WHEN Status='Actual' THEN 1 ELSE 0 END) AS n_actual,
               SUM(CASE WHEN Status='Backlog' THEN 1 ELSE 0 END) AS n_backlog
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2018-01-01' AND CtrDate < '2026-08-01'
        GROUP BY YEAR(CtrDate), MONTH(CtrDate) ORDER BY yr, mo
    """)
    monthly.to_csv(os.path.join(SUMMARY_DIR, "part3_ces_monthly_2018_2026.csv"), index=False)
    logger.info("Monthly breakdown 2018-01 to 2026-07: %d months present of a possible 103", len(monthly))

    all_months = pd.period_range("2018-01", "2026-07", freq="M")
    present_months = set((r["yr"], r["mo"]) for _, r in monthly.iterrows())
    missing_months = [str(m) for m in all_months if (m.year, m.month) not in present_months]
    logger.info("Months with ZERO rows for the 58 pilot items (division/revenue_type/status filter applied): %d -> %s",
                len(missing_months), missing_months)

    # Unit price per item per year, 2018-2026, compared
    price = run_query(f"""
        SELECT YEAR(CtrDate) AS yr, ItemCode AS itemcode,
               SUM(ActualQty)+SUM(BacklogQty) AS total_qty,
               SUM(ActualPrice)+SUM(BacklogPrice) AS total_value
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2018-01-01' AND CtrDate < '2026-08-01'
        GROUP BY YEAR(CtrDate), ItemCode
        HAVING SUM(ActualQty)+SUM(BacklogQty) > 0
    """)
    price["unit_price"] = price["total_value"] / price["total_qty"]
    price.to_csv(os.path.join(SUMMARY_DIR, "part3_ces_unit_price_by_item_year.csv"), index=False)

    # Compare each item's pre-2024 average unit price against its 2024+ average
    pre = price[price["yr"] < 2024].groupby("itemcode").apply(lambda g: (g["total_value"].sum() / g["total_qty"].sum())).rename("pre2024_unit_price")
    post = price[price["yr"] >= 2024].groupby("itemcode").apply(lambda g: (g["total_value"].sum() / g["total_qty"].sum())).rename("post2024_unit_price")
    price_compare = pd.concat([pre, post], axis=1).dropna()
    price_compare["ratio"] = price_compare["post2024_unit_price"] / price_compare["pre2024_unit_price"]
    price_compare.to_csv(os.path.join(SUMMARY_DIR, "part3_ces_price_pre_vs_post_2024.csv"))
    logger.info("Unit price ratio (2024+ / pre-2024) stats: min=%.2f, median=%.2f, max=%.2f, n_items=%d",
                price_compare["ratio"].min(), price_compare["ratio"].median(), price_compare["ratio"].max(), len(price_compare))

    print("\n=== Monthly breakdown, first 30 rows (2018-01 onward) ===")
    print(monthly.head(30).to_string(index=False))
    print(f"\nMissing months (zero rows): {len(missing_months)} -> {missing_months}")
    print("\n=== Unit price ratio (2024+ vs pre-2024), by item ===")
    print(price_compare.sort_values("ratio").to_string())
