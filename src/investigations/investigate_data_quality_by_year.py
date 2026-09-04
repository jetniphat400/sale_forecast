"""Tests whether older years of cube_Sale_APD are trustworthy under the
current PEM101/Omni Channel filtering approach: completeness by column,
stability of division/revenue_type/status value sets, and discontinuities.

Investigation only. Does not change the analysis period or config.yaml.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_data_quality_by_year")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

COLUMNS_TO_CHECK = [
    "itemcode", "createDate", "qty", "sale", "status", "division", "revenue_type",
    "customerid", "contractid", "jobcode", "forecast_date", "productCateName", "productTypeName",
]

if __name__ == "__main__":
    # --- Completeness per column per year ---
    completeness_records = []
    total_per_year = run_query("SELECT YEAR(createDate) AS yr, COUNT(*) AS n FROM cube_Sale_APD GROUP BY YEAR(createDate)").set_index("yr")["n"]
    for col in COLUMNS_TO_CHECK:
        r = run_query(f"SELECT YEAR(createDate) AS yr, COUNT({col}) AS non_null FROM cube_Sale_APD GROUP BY YEAR(createDate)")
        for _, row in r.iterrows():
            yr = row["yr"]
            pct = row["non_null"] / total_per_year[yr] * 100 if total_per_year[yr] else None
            completeness_records.append({"column": col, "year": yr, "pct_non_null": round(pct, 1) if pct is not None else None})
    completeness_df = pd.DataFrame(completeness_records).pivot(index="column", columns="year", values="pct_non_null")
    completeness_df.to_csv(os.path.join(SUMMARY_DIR, "part2_column_completeness_by_year.csv"))
    logger.info("Column completeness (%% non-null) by year:\n%s", completeness_df.to_string())

    # --- division / revenue_type / status distinct values per year ---
    for col in ["division", "revenue_type", "status"]:
        r = run_query(f"SELECT YEAR(createDate) AS yr, {col}, COUNT(*) AS n FROM cube_Sale_APD GROUP BY YEAR(createDate), {col} ORDER BY yr, n DESC")
        r.to_csv(os.path.join(SUMMARY_DIR, f"part2_{col}_by_year.csv"), index=False)
        logger.info("%s distinct values by year:\n%s", col, r.to_string(index=False))

    # --- discontinuity: row count, item count, customer count, value by year+month ---
    monthly_break = run_query("""
        SELECT YEAR(createDate) AS yr, MONTH(createDate) AS mo, COUNT(*) AS n_rows,
               COUNT(DISTINCT itemcode) AS n_items, COUNT(DISTINCT customerid) AS n_customers,
               SUM(sale) AS total_sale
        FROM cube_Sale_APD GROUP BY YEAR(createDate), MONTH(createDate) ORDER BY yr, mo
    """)
    monthly_break.to_csv(os.path.join(SUMMARY_DIR, "part2_monthly_breakdown_whole_table.csv"), index=False)
    logger.info("Monthly breakdown (whole table), first 40 rows:\n%s", monthly_break.head(40).to_string(index=False))

    print("\n=== Column completeness (%% non-null) by year ===")
    print(completeness_df.to_string())
