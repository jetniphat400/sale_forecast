"""Phase C Validator — division CI101. Data-quality checks, independent of the other four
parallel Validators (PEM102/PEM103/PEM104/PEM107). See STATUS.md Phase C and AGENTS.md
Validator role. Investigation script only — no pipeline code touched.

Writes CSVs to output/summary/ prefixed phaseC_CI101_ and prints results for the report.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("phaseC_CI101")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
os.makedirs(SUMMARY_DIR, exist_ok=True)

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def out(name):
    return os.path.join(SUMMARY_DIR, f"phaseC_CI101_{name}")


def classify_demand(qty_series: np.ndarray):
    n_periods = len(qty_series)
    nonzero = qty_series[qty_series > 0]
    if len(nonzero) == 0:
        return "NoSale", None, None
    adi = n_periods / len(nonzero)
    mean_d = nonzero.mean()
    std_d = nonzero.std(ddof=1) if len(nonzero) > 1 else 0.0
    cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        cls = "Smooth"
    elif adi < ADI_THRESHOLD:
        cls = "Erratic"
    elif cv2 < CV2_THRESHOLD:
        cls = "Intermittent"
    else:
        cls = "Lumpy"
    return cls, adi, cv2


def main():
    # ---- Step 0: pricelist rows ----
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    ci = pl[pl["business"] == "CI101"].copy()
    logger.info("CI101 pricelist rows: %d, distinct codes: %d", len(ci), ci["code"].nunique())
    ci.to_csv(out("00_pricelist_rows.csv"), index=False)

    codes = sorted(ci["code"].unique().tolist())
    codes_sql_list = ", ".join(f"'{c}'" for c in codes)
    logger.info("Distinct item codes (%d): %s", len(codes), codes)

    # =====================================================================
    # CHECK 1 — filter definition: distinct (division, revenue_type) pairs
    # =====================================================================
    logger.info("CHECK 1: filter definition")
    q1 = f"""
    SELECT division, revenue_type, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_sql_list})
    GROUP BY division, revenue_type
    ORDER BY sum_sale DESC
    """
    df1 = run_query(q1)
    df1.to_csv(out("check1_division_revenuetype_pairs.csv"), index=False)
    print(df1.to_string())

    # Also: does division='CI101' appear at all, any itemcode
    q1b = """
    SELECT DISTINCT division FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE division LIKE 'CI%'
    """
    df1b = run_query(q1b)
    df1b.to_csv(out("check1_ci_prefixed_divisions.csv"), index=False)
    print("\nDivisions LIKE 'CI%':")
    print(df1b.to_string())

    # =====================================================================
    # CHECK 2 — usable date range, per month, both filtered and unfiltered
    # =====================================================================
    logger.info("CHECK 2: usable date range")
    q2_unfiltered = f"""
    SELECT
        YEAR(createDate) AS yr, MONTH(createDate) AS mo,
        COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_sql_list})
    GROUP BY YEAR(createDate), MONTH(createDate)
    ORDER BY yr, mo
    """
    df2u = run_query(q2_unfiltered)
    df2u.to_csv(out("check2_monthly_unfiltered.csv"), index=False)
    print("\nMonthly (unfiltered):")
    print(df2u.to_string())

    # Column completeness per year (unfiltered, since we don't yet know the filter)
    q2_completeness = f"""
    SELECT
        YEAR(createDate) AS yr,
        COUNT(*) AS n_rows,
        SUM(CASE WHEN revenue_type IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_revenue_type,
        SUM(CASE WHEN forecast_date IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_forecast_date,
        SUM(CASE WHEN division IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_division,
        SUM(CASE WHEN status IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_status,
        SUM(CASE WHEN productCateName IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_productCateName,
        SUM(CASE WHEN productTypeName IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_sql_list})
    GROUP BY YEAR(createDate)
    ORDER BY yr
    """
    df2c = run_query(q2_completeness)
    df2c.to_csv(out("check2_column_completeness_by_year.csv"), index=False)
    print("\nColumn completeness by year (unfiltered):")
    print(df2c.to_string())

    # =====================================================================
    # CHECK 3 — name/code collisions with other divisions
    # =====================================================================
    logger.info("CHECK 3: name and code collisions")
    # distinct productCateName / productTypeName carried by these items
    q3_names = f"""
    SELECT DISTINCT productCateName, productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_sql_list})
    """
    df3_names = run_query(q3_names)
    df3_names.to_csv(out("check3_names_carried.csv"), index=False)
    print("\nDistinct productCateName/productTypeName carried by CI101 items:")
    print(df3_names.to_string())

    cate_names = [c for c in df3_names["productCateName"].dropna().unique().tolist()]
    type_names = [t for t in df3_names["productTypeName"].dropna().unique().tolist()]

    if cate_names:
        cate_list_sql = ", ".join("'" + c.replace("'", "''") + "'" for c in cate_names)
        q3_cate_other = f"""
        SELECT productCateName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productCateName IN ({cate_list_sql})
        GROUP BY productCateName, division
        ORDER BY productCateName, sum_sale DESC
        """
        df3_cate_other = run_query(q3_cate_other)
        df3_cate_other.to_csv(out("check3_category_name_by_division.csv"), index=False)
        print("\nCategory names — division breakdown:")
        print(df3_cate_other.to_string())

    if type_names:
        type_list_sql = ", ".join("'" + t.replace("'", "''") + "'" for t in type_names)
        q3_type_other = f"""
        SELECT productTypeName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productTypeName IN ({type_list_sql})
        GROUP BY productTypeName, division
        ORDER BY productTypeName, sum_sale DESC
        """
        df3_type_other = run_query(q3_type_other)
        df3_type_other.to_csv(out("check3_type_name_by_division.csv"), index=False)
        print("\nType names — division breakdown:")
        print(df3_type_other.to_string())

    # itemcode appearing under other divisions
    q3_itemcode_div = f"""
    SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_sql_list})
    GROUP BY itemcode, division
    ORDER BY itemcode, sum_sale DESC
    """
    df3_itemcode_div = run_query(q3_itemcode_div)
    df3_itemcode_div.to_csv(out("check3_itemcode_by_division.csv"), index=False)
    print("\nItemcode — division breakdown:")
    print(df3_itemcode_div.to_string())

    # =====================================================================
    # CHECK 4 — duplicates and split lots (needs Check-1 filter; done after we know it)
    # placeholder query pulls raw rows for these items, all fields needed
    # =====================================================================
    logger.info("CHECK 4/5/6/7/8 support: pulling all raw rows for these items (any division/filter)")
    q_raw_all = f"""
    SELECT itemcode, createDate, forecast_date, qty, sale, status, division, revenue_type,
           productCateName, productTypeName, contractid, quotationid, jobcode, timeStamp
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_sql_list})
    """
    raw_all = run_query(q_raw_all)
    raw_all.to_csv(out("raw_all_rows_any_filter.csv"), index=False)
    logger.info("Raw rows pulled (any division/filter): %d", len(raw_all))

    return codes, raw_all, df1, df2u, df2c


if __name__ == "__main__":
    main()
