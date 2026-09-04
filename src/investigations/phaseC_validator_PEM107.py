"""Phase C Validator — PEM107 data-quality checks (8 checks per AGENTS.md/STATUS.md
Phase C task spec). Independent of the other four parallel Validators (PEM102, PEM103,
PEM104, CI101). Writes CSVs to output/summary/ with a phaseC_PEM107_ prefix.

Read-only: never writes to config.yaml or any pipeline code, never modifies DB data.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_PEM107")

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PREFIX = "phaseC_PEM107_"

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def out(name):
    return os.path.join(SUMMARY_DIR, f"{PREFIX}{name}")


def save(df, name):
    path = out(name)
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d rows)", path, len(df))
    return path


def q(sql):
    logger.info("Query: %s", sql[:300].replace("\n", " "))
    return run_query(sql)


def code_list_sql(codes):
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


if __name__ == "__main__":
    # ================================================================
    # Step 0: get PEM107 item codes from pricelist
    # ================================================================
    pricelist = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    pem107 = pricelist[pricelist["business"] == "PEM107"].copy()
    logger.info("Pricelist rows with business == 'PEM107': %d", len(pem107))
    logger.info("Distinct sheets carrying these rows: %s", pem107["sheet"].unique().tolist())
    save(pem107, "pricelist_rows.csv")

    codes = sorted(pem107["code"].unique().tolist())
    n_dupe_rows = len(pem107) - len(codes)
    logger.info("Distinct PEM107 item codes: %d (row count %d, within-sheet dup rows: %d)",
                len(codes), len(pem107), n_dupe_rows)

    with open(out("item_codes.txt"), "w") as f:
        f.write("\n".join(codes))

    code_sql = code_list_sql(codes)

    # ================================================================
    # CHECK 1: Filter definition — all (division, revenue_type) pairs
    # ================================================================
    logger.info("=== CHECK 1: filter definition ===")
    sql1 = f"""
    SELECT division, revenue_type, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql})
    GROUP BY division, revenue_type
    ORDER BY sum_sale DESC
    """
    df1 = q(sql1)
    save(df1, "check1_division_revenuetype_pairs.csv")

    # Also check legacy PEM107-OLD specifically for these item codes
    sql1b = f"""
    SELECT division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql}) AND division = 'PEM107-OLD'
    GROUP BY division
    """
    df1b = q(sql1b)
    save(df1b, "check1_pem107old_check.csv")

    # ================================================================
    # CHECK 2: usable date range
    # ================================================================
    logger.info("=== CHECK 2: usable date range ===")
    # Filtered view: division PEM107 (and PEM107-OLD if found relevant), revenue_type Omni Channel
    sql2_filtered = f"""
    SELECT YEAR(createDate) AS yr, MONTH(createDate) AS mo, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql}) AND division = 'PEM107' AND revenue_type = 'Omni Channel'
    GROUP BY YEAR(createDate), MONTH(createDate)
    ORDER BY yr, mo
    """
    df2f = q(sql2_filtered)
    save(df2f, "check2_monthly_filtered.csv")

    # Unfiltered (any division, any revenue_type) for these item codes
    sql2_unfiltered = f"""
    SELECT YEAR(createDate) AS yr, MONTH(createDate) AS mo, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql})
    GROUP BY YEAR(createDate), MONTH(createDate)
    ORDER BY yr, mo
    """
    df2u = q(sql2_unfiltered)
    save(df2u, "check2_monthly_unfiltered.csv")

    # Column completeness per year (unfiltered scope, all division/revenue_type)
    sql2_completeness = f"""
    SELECT YEAR(createDate) AS yr,
        COUNT(*) AS n_rows,
        100.0 * SUM(CASE WHEN revenue_type IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) AS pct_revenue_type,
        100.0 * SUM(CASE WHEN forecast_date IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) AS pct_forecast_date,
        100.0 * SUM(CASE WHEN division IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) AS pct_division,
        100.0 * SUM(CASE WHEN status IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) AS pct_status,
        100.0 * SUM(CASE WHEN productCateName IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) AS pct_productCateName,
        100.0 * SUM(CASE WHEN productTypeName IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) AS pct_productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql})
    GROUP BY YEAR(createDate)
    ORDER BY yr
    """
    df2c = q(sql2_completeness)
    save(df2c, "check2_column_completeness_by_year.csv")

    # ================================================================
    # CHECK 3: name and code collisions
    # ================================================================
    logger.info("=== CHECK 3: name and code collisions ===")
    # 3a: distinct productCateName / productTypeName carried by PEM107's items (in PEM107 rows)
    sql3a = f"""
    SELECT DISTINCT productCateName, productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql}) AND division = 'PEM107'
    """
    df3a = q(sql3a)
    save(df3a, "check3_pem107_cate_type_names.csv")

    cate_names = [c for c in df3a["productCateName"].dropna().unique().tolist()]
    type_names = [t for t in df3a["productTypeName"].dropna().unique().tolist()]

    if cate_names:
        cate_sql = code_list_sql(cate_names)
        sql3b = f"""
        SELECT productCateName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productCateName IN ({cate_sql})
        GROUP BY productCateName, division
        ORDER BY productCateName, sum_sale DESC
        """
        df3b = q(sql3b)
        save(df3b, "check3_category_name_by_division.csv")
    else:
        df3b = pd.DataFrame()
        logger.info("No productCateName values found for PEM107 items under division='PEM107' — skipping 3b")

    if type_names:
        type_sql = code_list_sql(type_names)
        sql3b2 = f"""
        SELECT productTypeName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productTypeName IN ({type_sql})
        GROUP BY productTypeName, division
        ORDER BY productTypeName, sum_sale DESC
        """
        df3b2 = q(sql3b2)
        save(df3b2, "check3_type_name_by_division.csv")

    # 3c: for every PEM107 item code, does it appear under a DIFFERENT division anywhere?
    sql3c = f"""
    SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql})
    GROUP BY itemcode, division
    ORDER BY itemcode, sum_sale DESC
    """
    df3c = q(sql3c)
    save(df3c, "check3_itemcode_by_division.csv")

    # ================================================================
    # CHECK 4: duplicates and split lots
    # ================================================================
    logger.info("=== CHECK 4: duplicates and split lots ===")
    sql4 = f"""
    SELECT contractid, itemcode, createDate, qty, sale, status, forecast_date
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql}) AND division = 'PEM107' AND revenue_type = 'Omni Channel'
    """
    df4 = q(sql4)
    save(df4, "check4_raw_rows_for_grouping.csv")

    if len(df4):
        grp_cols = ["contractid", "itemcode", "createDate", "qty", "sale", "status"]
        df4["createDate"] = pd.to_datetime(df4["createDate"])
        counts = df4.groupby(grp_cols, dropna=False).size().reset_index(name="n_rows")
        dup_groups = counts[counts["n_rows"] > 1]
        save(dup_groups, "check4_duplicate_groups.csv")

        results = []
        for _, row in dup_groups.iterrows():
            mask = True
            for c in grp_cols:
                if pd.isna(row[c]):
                    mask = mask & df4[c].isna()
                else:
                    mask = mask & (df4[c] == row[c])
            sub = df4[mask]
            fd_nunique = sub["forecast_date"].nunique(dropna=False)
            bucket = "split_lot_candidate (forecast_date differs)" if fd_nunique > 1 else "unexplained_duplicate (forecast_date identical)"
            results.append({
                **{c: row[c] for c in grp_cols},
                "n_rows": row["n_rows"],
                "n_distinct_forecast_date": fd_nunique,
                "bucket": bucket,
                "group_sale_value": sub["sale"].sum(),
            })
        df4res = pd.DataFrame(results)
        save(df4res, "check4_group_classification.csv")

        if len(df4res):
            summary4 = df4res.groupby("bucket").agg(
                n_groups=("bucket", "size"),
                total_rows=("n_rows", "sum"),
                total_value=("group_sale_value", "sum"),
            ).reset_index()
        else:
            summary4 = pd.DataFrame()
        save(summary4, "check4_bucket_summary.csv")
    else:
        logger.info("No rows found for Check 4 grouping under division=PEM107/Omni Channel filter")
        dup_groups = pd.DataFrame()
        df4res = pd.DataFrame()
        summary4 = pd.DataFrame()

    # ================================================================
    # CHECK 5: pricelist agreement
    # ================================================================
    logger.info("=== CHECK 5: pricelist agreement ===")
    sql5 = f"""
    SELECT DISTINCT itemcode, productCateName, productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql}) AND division = 'PEM107'
    """
    df5db = q(sql5)
    save(df5db, "check5_db_cate_type_per_item.csv")

    pl5 = pem107[["code", "category", "type"]].rename(columns={"code": "itemcode", "category": "pl_category", "type": "pl_type"})
    db_agg = df5db.groupby("itemcode").agg(
        db_categories=("productCateName", lambda x: sorted(set(x.dropna()))),
        db_types=("productTypeName", lambda x: sorted(set(x.dropna()))),
    ).reset_index()
    merged5 = pl5.merge(db_agg, on="itemcode", how="left")

    def cat_match(row):
        if not isinstance(row["db_categories"], list) or len(row["db_categories"]) == 0:
            return "no_db_data"
        if row["pl_category"] in row["db_categories"]:
            return "match" if len(row["db_categories"]) == 1 else "match_plus_extra"
        return "mismatch"

    def type_match(row):
        if not isinstance(row["db_types"], list) or len(row["db_types"]) == 0:
            return "no_db_data"
        if row["pl_type"] in row["db_types"]:
            return "match" if len(row["db_types"]) == 1 else "match_plus_extra"
        return "mismatch"

    merged5["category_agreement"] = merged5.apply(cat_match, axis=1)
    merged5["type_agreement"] = merged5.apply(type_match, axis=1)
    save(merged5, "check5_pricelist_vs_db_agreement.csv")

    mismatches5 = merged5[(merged5["category_agreement"] == "mismatch") | (merged5["type_agreement"] == "mismatch")]
    save(mismatches5, "check5_mismatches_only.csv")

    # ================================================================
    # CHECK 6: items without history
    # ================================================================
    logger.info("=== CHECK 6: items without history ===")
    sql6 = f"""
    SELECT itemcode, COUNT(*) AS n_rows
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql})
    GROUP BY itemcode
    """
    df6 = q(sql6)
    codes_with_rows = set(df6["itemcode"].tolist())
    no_history_codes = sorted(set(codes) - codes_with_rows)
    logger.info("Items with ZERO rows in cube_Sale_APD (any filter): %d of %d", len(no_history_codes), len(codes))

    no_history_results = []
    if no_history_codes:
        nh_sql = code_list_sql(no_history_codes)

        ces6 = q(f"""
        SELECT ItemCode, COUNT(*) AS n_rows
        FROM [salewarehouse].[dbo].[Cube_CES]
        WHERE ItemCode IN ({nh_sql})
        GROUP BY ItemCode
        """)
        inv6 = q(f"""
        SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Cube_Inventory_Exact'
        """)
        logger.info("Cube_Inventory_Exact columns: %s", inv6["COLUMN_NAME"].tolist())
        # find itemcode-like column
        inv_item_col = None
        for cand in ["ItemCode", "itemcode", "Item_Code", "item_code"]:
            if cand in inv6["COLUMN_NAME"].tolist():
                inv_item_col = cand
                break
        if inv_item_col:
            invq = q(f"""
            SELECT [{inv_item_col}] AS ItemCode, COUNT(*) AS n_rows
            FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
            WHERE [{inv_item_col}] IN ({nh_sql})
            GROUP BY [{inv_item_col}]
            """)
        else:
            invq = pd.DataFrame(columns=["ItemCode", "n_rows"])
            logger.warning("No itemcode-like column found in Cube_Inventory_Exact")

        quot6 = q(f"""
        SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Cube_Quotation'
        """)
        logger.info("Cube_Quotation columns: %s", quot6["COLUMN_NAME"].tolist())
        quot_item_col = None
        for cand in ["itemcode", "ItemCode", "Item_Code", "item_code"]:
            if cand in quot6["COLUMN_NAME"].tolist():
                quot_item_col = cand
                break
        if quot_item_col:
            quotq = q(f"""
            SELECT [{quot_item_col}] AS ItemCode, COUNT(*) AS n_rows
            FROM [salewarehouse].[dbo].[Cube_Quotation]
            WHERE [{quot_item_col}] IN ({nh_sql})
            GROUP BY [{quot_item_col}]
            """)
        else:
            quotq = pd.DataFrame(columns=["ItemCode", "n_rows"])
            logger.warning("No itemcode-like column found in Cube_Quotation")

        for code in no_history_codes:
            no_history_results.append({
                "itemcode": code,
                "cube_Sale_APD_rows": 0,
                "Cube_CES_rows": int(ces6[ces6["ItemCode"] == code]["n_rows"].sum()) if len(ces6) else 0,
                "Cube_Inventory_Exact_rows": int(invq[invq["ItemCode"] == code]["n_rows"].sum()) if len(invq) else 0,
                "Cube_Quotation_rows": int(quotq[quotq["ItemCode"] == code]["n_rows"].sum()) if len(quotq) else 0,
            })
    df6res = pd.DataFrame(no_history_results)
    save(df6res, "check6_no_history_items_trace.csv")

    # ================================================================
    # CHECK 7: cross-check against Cube_CES
    # ================================================================
    logger.info("=== CHECK 7: cross-check against Cube_CES ===")
    # Determine usable-from date first based on check 2 results (done after seeing df2f/df2c below in report,
    # but for the query we pull APD rows under the filter and Cube_CES rows, matching PEM101's method:
    # (contractid, itemcode, createDate/CtrDate, mapped status, qty)
    sql7_apd = f"""
    SELECT contractid, itemcode, createDate, status, qty, sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql}) AND division = 'PEM107' AND revenue_type = 'Omni Channel'
      AND status IN ('Actual','MPS')
    """
    df7apd = q(sql7_apd)
    save(df7apd, "check7_apd_rows.csv")

    sql7_ces = f"""
    SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty, PlanQty
    FROM [salewarehouse].[dbo].[Cube_CES]
    WHERE ItemCode IN ({code_sql})
    """
    df7ces = q(sql7_ces)
    save(df7ces, "check7_ces_rows.csv")

    if len(df7apd):
        df7apd["createDate"] = pd.to_datetime(df7apd["createDate"]).dt.date
        df7apd["mapped_status"] = df7apd["status"].map({"Actual": "Actual", "MPS": "Backlog"})
        df7ces["CtrDate"] = pd.to_datetime(df7ces["CtrDate"]).dt.date
        # qty to match: for Actual use ActualQty, for Backlog use BacklogQty
        df7ces["match_qty"] = np.where(df7ces["Status"] == "Actual", df7ces["ActualQty"], df7ces["BacklogQty"])

        merge7 = df7apd.merge(
            df7ces,
            left_on=["contractid", "itemcode", "createDate", "mapped_status", "qty"],
            right_on=["ContractID", "ItemCode", "CtrDate", "Status", "match_qty"],
            how="left",
            indicator=True,
        )
        matched = (merge7["_merge"] == "both").sum()
        total = len(merge7)
        match_rate = 100.0 * matched / total if total else None
        logger.info("Check 7: matched %d of %d APD rows to Cube_CES on 5-field key (%.2f%%)", matched, total, match_rate or 0)
        save(merge7, "check7_merge_detail.csv")
        summary7 = pd.DataFrame([{"n_apd_rows": total, "n_matched": matched, "match_rate_pct": match_rate}])
        save(summary7, "check7_match_rate_summary.csv")
    else:
        logger.info("No APD rows under filter for Check 7 — skipping match rate computation")
        summary7 = pd.DataFrame([{"n_apd_rows": 0, "n_matched": 0, "match_rate_pct": None}])
        save(summary7, "check7_match_rate_summary.csv")

    # ================================================================
    # CHECK 8: demand profile
    # ================================================================
    logger.info("=== CHECK 8: demand profile ===")
    # Uses the filtered view (division=PEM107, revenue_type=Omni Channel, status Actual+MPS)
    sql8 = f"""
    SELECT itemcode, YEAR(createDate) AS yr, MONTH(createDate) AS mo, SUM(qty) AS qty, SUM(sale) AS sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql}) AND division = 'PEM107' AND revenue_type = 'Omni Channel'
      AND status IN ('Actual','MPS')
    GROUP BY itemcode, YEAR(createDate), MONTH(createDate)
    ORDER BY itemcode, yr, mo
    """
    df8 = q(sql8)
    save(df8, "check8_raw_item_month_qty.csv")

    print("\n" + "=" * 78)
    print("PEM107 VALIDATOR — raw query results captured. See report script / manual")
    print("analysis for month-range determination, classification build, and narrative.")
    print("=" * 78)
