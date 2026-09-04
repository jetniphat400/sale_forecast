"""Phase C Validator — PEM102 data-quality checks (8 checks per AGENTS.md Validator role).

One of five parallel Validators (PEM102/PEM103/PEM104/PEM107/CI101) running identical,
independent data-quality checks extending the forecasting method proven on PEM101 (128 items)
to the full 445-item pricelist. This script covers division PEM102 (26 item codes).

Writes CSVs to output/summary/, all prefixed phaseC_PEM102_. Investigation only — no pipeline
code touched, no config.yaml changes, no data modified.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_validator_PEM102")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PREFIX = "phaseC_PEM102_"

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def outpath(name):
    return os.path.join(SUMMARY_DIR, f"{PREFIX}{name}")


def sql_in_list(codes):
    return ",".join("'" + c.replace("'", "''") + "'" for c in codes)


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
    # ---- Setup: get item codes ----
    pricelist = load_visible_product_rows("reference/pricelist.xlsx")
    pem102 = pricelist[pricelist["business"] == "PEM102"].copy()
    codes = sorted(pem102["code"].unique().tolist())
    logger.info("PEM102: %d rows, %d distinct item codes", len(pem102), len(codes))
    pem102.to_csv(outpath("pricelist_rows.csv"), index=False)
    codes_in = sql_in_list(codes)

    # ============================================================
    # CHECK 1: Filter definition — all (division, revenue_type) pairs for our items
    # ============================================================
    logger.info("CHECK 1: filter definition")
    sql1 = f"""
    SELECT division, revenue_type, COUNT(*) AS n_rows, SUM(sale) AS total_sale, SUM(qty) AS total_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
    GROUP BY division, revenue_type
    ORDER BY n_rows DESC
    """
    df1 = run_query(sql1)
    df1.to_csv(outpath("check1_division_revenue_pairs.csv"), index=False)
    print("\n=== CHECK 1: division/revenue_type pairs ===")
    print(df1.to_string(index=False))

    # Check for PEM102-OLD specifically among our item codes
    sql1b = f"""
    SELECT division, COUNT(*) AS n_rows, SUM(sale) AS total_sale, COUNT(DISTINCT itemcode) AS n_items
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in}) AND division LIKE '%OLD%'
    GROUP BY division
    """
    df1b = run_query(sql1b)
    df1b.to_csv(outpath("check1_OLD_division_check.csv"), index=False)
    print("\n=== CHECK 1b: legacy '-OLD' division rows among PEM102 items ===")
    print(df1b.to_string(index=False) if len(df1b) else "None found")

    # ============================================================
    # CHECK 2: Usable date range — monthly row count/value, unfiltered and filtered
    # ============================================================
    logger.info("CHECK 2: usable date range")
    sql2_unfiltered = f"""
    SELECT YEAR(createDate) AS yr, MONTH(createDate) AS mo, COUNT(*) AS n_rows,
           SUM(sale) AS total_sale, SUM(qty) AS total_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
    GROUP BY YEAR(createDate), MONTH(createDate)
    ORDER BY yr, mo
    """
    df2u = run_query(sql2_unfiltered)
    df2u.to_csv(outpath("check2_monthly_unfiltered.csv"), index=False)

    # Column completeness per year (unfiltered, all PEM102 item rows)
    sql2_completeness = f"""
    SELECT YEAR(createDate) AS yr,
           COUNT(*) AS n_rows,
           100.0*SUM(CASE WHEN revenue_type IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_revenue_type,
           100.0*SUM(CASE WHEN forecast_date IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_forecast_date,
           100.0*SUM(CASE WHEN division IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_division,
           100.0*SUM(CASE WHEN status IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_status,
           100.0*SUM(CASE WHEN productCateName IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_productCateName,
           100.0*SUM(CASE WHEN productTypeName IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
    GROUP BY YEAR(createDate)
    ORDER BY yr
    """
    df2c = run_query(sql2_completeness)
    df2c.to_csv(outpath("check2_column_completeness_by_year.csv"), index=False)
    print("\n=== CHECK 2: column completeness by year (unfiltered) ===")
    print(df2c.to_string(index=False))

    # distinct revenue_type values by year, to find the equivalent of 'Omni Channel'
    sql2_revtype_year = f"""
    SELECT YEAR(createDate) AS yr, revenue_type, COUNT(*) AS n_rows, SUM(sale) AS total_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
    GROUP BY YEAR(createDate), revenue_type
    ORDER BY yr, n_rows DESC
    """
    df2r = run_query(sql2_revtype_year)
    df2r.to_csv(outpath("check2_revenue_type_by_year.csv"), index=False)
    print("\n=== CHECK 2: revenue_type by year (unfiltered) ===")
    print(df2r.to_string(index=False))

    # ============================================================
    # CHECK 3: Name and code collisions
    # ============================================================
    logger.info("CHECK 3: name and code collisions")
    # distinct category/type our items carry
    sql3_names = f"""
    SELECT DISTINCT productCateName, productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
    """
    df3names = run_query(sql3_names)
    df3names.to_csv(outpath("check3_our_names.csv"), index=False)
    print("\n=== CHECK 3: distinct productCateName/productTypeName carried by PEM102 items ===")
    print(df3names.to_string(index=False))

    cate_names = [c for c in df3names["productCateName"].dropna().unique().tolist()]
    type_names = [c for c in df3names["productTypeName"].dropna().unique().tolist()]

    if cate_names:
        cate_in = sql_in_list(cate_names)
        sql3_cate_collision = f"""
        SELECT productCateName, division, COUNT(*) AS n_rows, SUM(sale) AS total_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productCateName IN ({cate_in})
        GROUP BY productCateName, division
        ORDER BY productCateName, n_rows DESC
        """
        df3cate = run_query(sql3_cate_collision)
        df3cate.to_csv(outpath("check3_category_name_collisions.csv"), index=False)
        n_cate_other_div = df3cate[df3cate["division"] != "PEM102"]["productCateName"].nunique()
        print(f"\n=== CHECK 3: category-name collisions — {n_cate_other_div} of {len(cate_names)} category names also appear under other divisions ===")

    if type_names:
        type_in = sql_in_list(type_names)
        sql3_type_collision = f"""
        SELECT productTypeName, division, COUNT(*) AS n_rows, SUM(sale) AS total_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productTypeName IN ({type_in})
        GROUP BY productTypeName, division
        ORDER BY productTypeName, n_rows DESC
        """
        df3type = run_query(sql3_type_collision)
        df3type.to_csv(outpath("check3_type_name_collisions.csv"), index=False)
        n_type_other_div = df3type[df3type["division"] != "PEM102"]["productTypeName"].nunique()
        print(f"=== CHECK 3: type-name collisions — {n_type_other_div} of {len(type_names)} type names also appear under other divisions ===")

    # itemcode appearing under other divisions
    sql3_itemcode = f"""
    SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS total_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
    GROUP BY itemcode, division
    ORDER BY itemcode, n_rows DESC
    """
    df3item = run_query(sql3_itemcode)
    df3item.to_csv(outpath("check3_itemcode_division_split.csv"), index=False)
    codes_with_other_div = sorted(df3item[df3item["division"] != "PEM102"]["itemcode"].unique().tolist())
    print(f"\n=== CHECK 3: {len(codes_with_other_div)} of {len(codes)} item codes appear under a division other than PEM102 ===")
    print(codes_with_other_div)
    pem102_val = df3item[df3item["division"] == "PEM102"]["total_sale"].sum()
    other_val = df3item[df3item["division"] != "PEM102"]["total_sale"].sum()
    print(f"Value split: PEM102={pem102_val:,.2f}  Other-division={other_val:,.2f}")

    # ============================================================
    # CHECK 4: Duplicates and split lots (needs Check-1 filter; computed after we conclude it below,
    # but pull raw rows now under itemcode-only scope, filter applied in analysis stage)
    # ============================================================
    logger.info("CHECK 4/pull raw rows for duplicate + demand-profile analysis")
    sql_raw = f"""
    SELECT itemcode, contractid, createDate, forecast_date, qty, sale, status, division, revenue_type,
           productCateName, productTypeName, quotationid
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
    """
    raw = run_query(sql_raw)
    raw.to_csv(outpath("raw_all_rows_itemcode_scope.csv"), index=False)
    logger.info("Raw pull: %d rows", len(raw))

    # ============================================================
    # CHECK 6: Items without history
    # ============================================================
    logger.info("CHECK 6: items without history")
    codes_with_rows = set(raw["itemcode"].unique().tolist())
    codes_no_history = sorted(set(codes) - codes_with_rows)
    print(f"\n=== CHECK 6: {len(codes_no_history)} of {len(codes)} item codes have ZERO rows in cube_Sale_APD (any filter) ===")
    print(codes_no_history)

    no_hist_rows = []
    if codes_no_history:
        nh_in = sql_in_list(codes_no_history)
        sql6_ces = f"""
        SELECT ItemCode, COUNT(*) AS n_rows, MIN(CtrDate) AS min_date, MAX(CtrDate) AS max_date
        FROM [salewarehouse].[dbo].[Cube_CES]
        WHERE ItemCode IN ({nh_in})
        GROUP BY ItemCode
        """
        df6ces = run_query(sql6_ces)
        sql6_inv = f"""
        SELECT itemcode, COUNT(*) AS n_rows, SUM(stock) AS total_stock
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
        WHERE itemcode IN ({nh_in})
        GROUP BY itemcode
        """
        df6inv = run_query(sql6_inv)
        sql6_quo = f"""
        SELECT itemcode, COUNT(*) AS n_rows, MIN(create_date) AS min_date, MAX(create_date) AS max_date
        FROM [salewarehouse].[dbo].[Cube_Quotation]
        WHERE itemcode IN ({nh_in})
        GROUP BY itemcode
        """
        df6quo = run_query(sql6_quo)

        for c in codes_no_history:
            ces_row = df6ces[df6ces["ItemCode"] == c]
            inv_row = df6inv[df6inv["itemcode"] == c]
            quo_row = df6quo[df6quo["itemcode"] == c]
            no_hist_rows.append({
                "itemcode": c,
                "ces_n_rows": int(ces_row["n_rows"].iloc[0]) if len(ces_row) else 0,
                "ces_date_range": f"{ces_row['min_date'].iloc[0]} to {ces_row['max_date'].iloc[0]}" if len(ces_row) else None,
                "inv_n_rows": int(inv_row["n_rows"].iloc[0]) if len(inv_row) else 0,
                "inv_total_stock": float(inv_row["total_stock"].iloc[0]) if len(inv_row) and inv_row["total_stock"].iloc[0] is not None else None,
                "quo_n_rows": int(quo_row["n_rows"].iloc[0]) if len(quo_row) else 0,
                "quo_date_range": f"{quo_row['min_date'].iloc[0]} to {quo_row['max_date'].iloc[0]}" if len(quo_row) else None,
            })
    df6 = pd.DataFrame(no_hist_rows)
    df6.to_csv(outpath("check6_no_history_items_crosscheck.csv"), index=False)
    print("\n=== CHECK 6: cross-check of no-history items against CES/Inventory/Quotation ===")
    print(df6.to_string(index=False) if len(df6) else "N/A (no no-history items)")

    logger.info("Script part 1 complete. Continue with analysis-stage checks (2/3 conclusions, 4, 5, 7, 8) in follow-up.")

    return {
        "codes": codes,
        "raw": raw,
        "df1": df1,
        "df2u": df2u,
        "df2c": df2c,
        "df2r": df2r,
        "pem102": pem102,
        "codes_no_history": codes_no_history,
    }


if __name__ == "__main__":
    main()
