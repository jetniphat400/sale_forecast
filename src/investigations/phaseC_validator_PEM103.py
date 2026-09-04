"""Phase C Validator — division PEM103 data-quality checks (8 checks per the assignment).

Investigation script only (not a pipeline component) — writes all outputs to
output/summary/, prefixed phaseC_PEM103_, per AGENTS.md rule 5.

Run: python src/investigations/phaseC_validator_PEM103.py
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("phaseC_PEM103")

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DIVISION = "PEM103"
ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def out(name):
    return os.path.join(SUMMARY_DIR, f"phaseC_PEM103_{name}")


def sql_in_list(codes):
    esc = [c.replace("'", "''") for c in codes]
    return "(" + ",".join(f"'{c}'" for c in esc) + ")"


def get_item_codes():
    df = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    pem = df[df["business"] == DIVISION].copy()
    n_rows = len(pem)
    n_codes = pem["code"].nunique()
    logger.info("PEM103 pricelist rows=%d distinct codes=%d sheets=%s", n_rows, n_codes,
                sorted(pem["sheet"].unique()))
    pem.to_csv(out("pricelist_rows.csv"), index=False)
    return sorted(pem["code"].unique()), pem


def check1(codes_sql):
    logger.info("CHECK 1: filter definition")
    sql = f"""
    SELECT division, revenue_type, COUNT(*) AS row_count, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql}
    GROUP BY division, revenue_type
    ORDER BY sum_sale DESC
    """
    df = run_query(sql)
    df.to_csv(out("check1_division_revenuetype_pairs.csv"), index=False)
    logger.info("Check1: %d distinct (division, revenue_type) pairs", len(df))
    print(df.to_string(index=False))
    return df


def check2(codes_sql, div_filter_sql):
    logger.info("CHECK 2: usable date range")
    # Monthly rows/value under division=PEM103 only (all revenue types) to see the full picture
    sql_monthly = f"""
    SELECT YEAR(createDate) AS yr, MONTH(createDate) AS mo, division, revenue_type,
           COUNT(*) AS row_count, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql}
    GROUP BY YEAR(createDate), MONTH(createDate), division, revenue_type
    ORDER BY yr, mo
    """
    df_monthly = run_query(sql_monthly)
    df_monthly.to_csv(out("check2_monthly_by_division_revtype.csv"), index=False)

    # Overall monthly (no division/revtype breakdown), unfiltered
    sql_monthly_all = f"""
    SELECT YEAR(createDate) AS yr, MONTH(createDate) AS mo,
           COUNT(*) AS row_count, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql}
    GROUP BY YEAR(createDate), MONTH(createDate)
    ORDER BY yr, mo
    """
    df_monthly_all = run_query(sql_monthly_all)
    df_monthly_all.to_csv(out("check2_monthly_unfiltered.csv"), index=False)

    # Column completeness per year (unfiltered by division/revtype, itemcode-only scope)
    sql_completeness = f"""
    SELECT YEAR(createDate) AS yr,
           COUNT(*) AS n_rows,
           100.0*SUM(CASE WHEN revenue_type IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_revenue_type,
           100.0*SUM(CASE WHEN forecast_date IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_forecast_date,
           100.0*SUM(CASE WHEN division IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_division,
           100.0*SUM(CASE WHEN status IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_status,
           100.0*SUM(CASE WHEN productCateName IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_productCateName,
           100.0*SUM(CASE WHEN productTypeName IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) AS pct_productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql}
    GROUP BY YEAR(createDate)
    ORDER BY yr
    """
    df_comp = run_query(sql_completeness)
    df_comp.to_csv(out("check2_completeness_by_year.csv"), index=False)

    print("\n--- Monthly (unfiltered by division/revtype) ---")
    print(df_monthly_all.to_string(index=False))
    print("\n--- Completeness by year ---")
    print(df_comp.to_string(index=False))

    return df_monthly, df_monthly_all, df_comp


def check3(codes_sql, codes_list):
    logger.info("CHECK 3: name/code collisions")
    # distinct productCateName/productTypeName this division's items carry
    sql_names = f"""
    SELECT DISTINCT productCateName, productTypeName
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql} AND division = '{DIVISION}'
    """
    df_names = run_query(sql_names)
    df_names.to_csv(out("check3_names_carried.csv"), index=False)
    print("\n--- productCateName/productTypeName carried by PEM103 items (division=PEM103 rows) ---")
    print(df_names.to_string(index=False))

    cates = df_names["productCateName"].dropna().unique().tolist()
    types = df_names["productTypeName"].dropna().unique().tolist()

    rows = []
    for cat in cates:
        cat_esc = cat.replace("'", "''")
        sql = f"""
        SELECT division, COUNT(*) AS row_count, SUM(sale) AS sum_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productCateName = '{cat_esc}'
        GROUP BY division ORDER BY sum_sale DESC
        """
        d = run_query(sql)
        d["productCateName"] = cat
        rows.append(d)
    df_cat_divisions = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    df_cat_divisions.to_csv(out("check3_category_name_by_division.csv"), index=False)

    rows2 = []
    for typ in types:
        typ_esc = typ.replace("'", "''")
        sql = f"""
        SELECT division, COUNT(*) AS row_count, SUM(sale) AS sum_sale
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE productTypeName = '{typ_esc}'
        GROUP BY division ORDER BY sum_sale DESC
        """
        d = run_query(sql)
        d["productTypeName"] = typ
        rows2.append(d)
    df_type_divisions = pd.concat(rows2, ignore_index=True) if rows2 else pd.DataFrame()
    df_type_divisions.to_csv(out("check3_type_name_by_division.csv"), index=False)

    n_cat_shared = df_cat_divisions.groupby("productCateName")["division"].nunique()
    n_cat_shared_count = (n_cat_shared > 1).sum()
    n_type_shared = df_type_divisions.groupby("productTypeName")["division"].nunique()
    n_type_shared_count = (n_type_shared > 1).sum()
    logger.info("Category names shared across >1 division: %d of %d", n_cat_shared_count, len(cates))
    logger.info("Type names shared across >1 division: %d of %d", n_type_shared_count, len(types))

    # itemcode appearing under other divisions
    sql_item_div = f"""
    SELECT itemcode, division, COUNT(*) AS row_count, SUM(sale) AS sum_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql}
    GROUP BY itemcode, division
    ORDER BY itemcode, sum_sale DESC
    """
    df_item_div = run_query(sql_item_div)
    df_item_div.to_csv(out("check3_itemcode_by_division.csv"), index=False)

    per_item_div_count = df_item_div.groupby("itemcode")["division"].nunique()
    cross_div_items = per_item_div_count[per_item_div_count > 1].index.tolist()
    logger.info("Item codes appearing under >1 division: %d of %d", len(cross_div_items), len(codes_list))

    this_div_value = df_item_div[df_item_div["division"] == DIVISION]["sum_sale"].sum()
    other_div_value = df_item_div[df_item_div["division"] != DIVISION]["sum_sale"].sum()
    logger.info("Value split: PEM103=%.2f other-divisions=%.2f", this_div_value, other_div_value)

    summary = {
        "n_category_names": len(cates), "n_category_names_shared": int(n_cat_shared_count),
        "n_type_names": len(types), "n_type_names_shared": int(n_type_shared_count),
        "n_items_cross_division": len(cross_div_items),
        "n_items_total": len(codes_list),
        "value_this_division_thb": float(this_div_value),
        "value_other_divisions_thb": float(other_div_value),
    }
    pd.DataFrame([summary]).to_csv(out("check3_summary.csv"), index=False)
    print("\n--- Check 3 summary ---")
    print(summary)
    return df_cat_divisions, df_type_divisions, df_item_div, summary


def check4(codes_sql, div_filter_where):
    logger.info("CHECK 4: duplicates and split lots")
    sql = f"""
    SELECT contractid, itemcode, createDate, qty, sale, status, forecast_date
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql} {div_filter_where}
    """
    df = run_query(sql)
    df.to_csv(out("check4_raw_rows.csv"), index=False)
    logger.info("Check4: %d raw rows under check1 filter", len(df))

    grp_cols = ["contractid", "itemcode", "createDate", "qty", "sale", "status"]
    df["createDate"] = pd.to_datetime(df["createDate"])
    grouped = df.groupby(grp_cols, dropna=False)

    dup_rows = []
    for key, g in grouped:
        if len(g) > 1:
            fdates = g["forecast_date"].astype(str).unique()
            differs = len(fdates) > 1
            dup_rows.append({
                "contractid": key[0], "itemcode": key[1], "createDate": key[2],
                "qty": key[3], "sale": key[4], "status": key[5],
                "n_rows": len(g), "n_distinct_forecast_date": len(fdates),
                "forecast_dates": ";".join(fdates),
                "bucket": "plausible_split_lot" if differs else "unexplained_duplicate",
                "group_value_sale": g["sale"].sum(),
            })
    dup_df = pd.DataFrame(dup_rows)
    dup_df.to_csv(out("check4_duplicate_groups.csv"), index=False)

    if len(dup_df):
        summary = dup_df.groupby("bucket").agg(
            n_groups=("bucket", "count"),
            n_rows=("n_rows", "sum"),
            total_value_thb=("group_value_sale", "sum"),
        ).reset_index()
    else:
        summary = pd.DataFrame(columns=["bucket", "n_groups", "n_rows", "total_value_thb"])
    summary.to_csv(out("check4_summary.csv"), index=False)
    print("\n--- Check 4: duplicate group summary ---")
    print(summary.to_string(index=False))
    print(f"Total rows: {len(df)}, groups with >1 row: {len(dup_df)}")
    return df, dup_df, summary


def check5(codes_list, pem_pricelist_df, div_filter_where):
    logger.info("CHECK 5: pricelist agreement")
    codes_sql = sql_in_list(codes_list)
    sql = f"""
    SELECT itemcode, productCateName, productTypeName, COUNT(*) AS row_count, SUM(sale) AS sum_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql} {div_filter_where}
    GROUP BY itemcode, productCateName, productTypeName
    ORDER BY itemcode
    """
    df_db = run_query(sql)
    df_db.to_csv(out("check5_db_category_type_per_item.csv"), index=False)

    pl = pem_pricelist_df[["code", "category", "type"]].drop_duplicates()
    merged = df_db.merge(pl, left_on="itemcode", right_on="code", how="outer", indicator=True)
    merged.to_csv(out("check5_merged.csv"), index=False)

    # items with more than one DB cate/type
    multi = df_db.groupby("itemcode")[["productCateName", "productTypeName"]].nunique()
    multi_items = multi[(multi["productCateName"] > 1) | (multi["productTypeName"] > 1)]
    multi_items.to_csv(out("check5_items_with_multiple_db_values.csv"))

    mismatches = merged[
        (merged["_merge"] == "both") &
        ((merged["category"].astype(str).str.strip().str.lower() != merged["productCateName"].astype(str).str.strip().str.lower()) |
         (merged["type"].astype(str).str.strip().str.lower() != merged["productTypeName"].astype(str).str.strip().str.lower()))
    ]
    mismatches.to_csv(out("check5_mismatches.csv"), index=False)

    print(f"\n--- Check 5: {len(mismatches)} item-DB-row mismatches (case/whitespace-insensitive compare) ---")
    print(mismatches[["itemcode", "category", "productCateName", "type", "productTypeName"]].to_string(index=False))
    print(f"\nItems with >1 distinct DB category or type value: {len(multi_items)}")
    return df_db, merged, mismatches, multi_items


def check6(codes_list, codes_sql):
    logger.info("CHECK 6: items without history")
    sql = f"""
    SELECT itemcode, COUNT(*) AS row_count
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql}
    GROUP BY itemcode
    """
    df = run_query(sql)
    present = set(df["itemcode"])
    missing = sorted(set(codes_list) - present)
    logger.info("Items with zero rows in cube_Sale_APD (any filter): %d of %d", len(missing), len(codes_list))

    results = []
    if missing:
        codes_sql_missing = sql_in_list(missing)
        ces = run_query(f"""
            SELECT ItemCode, COUNT(*) AS n FROM [salewarehouse].[dbo].[Cube_CES]
            WHERE ItemCode IN {codes_sql_missing} GROUP BY ItemCode
        """)
        inv = run_query(f"""
            SELECT itemcode, COUNT(*) AS n FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
            WHERE itemcode IN {codes_sql_missing} GROUP BY itemcode
        """)
        quo = run_query(f"""
            SELECT itemcode, COUNT(*) AS n FROM [salewarehouse].[dbo].[Cube_Quotation]
            WHERE itemcode IN {codes_sql_missing} GROUP BY itemcode
        """)
        ces_d = dict(zip(ces.get("ItemCode", []), ces.get("n", [])))
        inv_d = dict(zip(inv.get("itemcode", []), inv.get("n", [])))
        quo_d = dict(zip(quo.get("itemcode", []), quo.get("n", [])))
        for c in missing:
            results.append({
                "itemcode": c,
                "cube_ces_rows": ces_d.get(c, 0),
                "cube_inventory_exact_rows": inv_d.get(c, 0),
                "cube_quotation_rows": quo_d.get(c, 0),
            })
    df_missing = pd.DataFrame(results)
    df_missing.to_csv(out("check6_no_history_items.csv"), index=False)
    print(f"\n--- Check 6: {len(missing)} items with zero rows in cube_Sale_APD ---")
    print(df_missing.to_string(index=False) if len(df_missing) else "(none)")
    return missing, df_missing


def check7(codes_sql, usable_from_date):
    logger.info("CHECK 7: cross-check against Cube_CES (row-level match, PEM101 methodology)")
    # cube_Sale_APD side
    sql_apd = f"""
    SELECT contractid, itemcode, createDate, status, qty, sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql} AND division = '{DIVISION}' AND revenue_type = 'Omni Channel'
      AND status IN ('Actual','MPS') AND createDate >= '{usable_from_date}'
    """
    apd = run_query(sql_apd)
    apd["mapped_status"] = apd["status"].map({"Actual": "Actual", "MPS": "Backlog"})
    apd["createDate"] = pd.to_datetime(apd["createDate"]).dt.date

    sql_ces = f"""
    SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty
    FROM [salewarehouse].[dbo].[Cube_CES]
    WHERE ItemCode IN {codes_sql} AND ManuDivision = '{DIVISION}' AND RevenueType = 'Omni Channel'
      AND Status IN ('Actual','Backlog') AND CtrDate >= '{usable_from_date}'
    """
    ces = run_query(sql_ces)
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"]).dt.date
    ces["ces_qty"] = np.where(ces["Status"] == "Actual", ces["ActualQty"], ces["BacklogQty"])

    apd.to_csv(out("check7_apd_rows.csv"), index=False)
    ces.to_csv(out("check7_ces_rows.csv"), index=False)

    # PEM101 methodology (STATUS.md Phase 1.5 Part 2): match on FIVE fields --
    # (contractid, itemcode, createDate/CtrDate, mapped status, qty). Replicated here for
    # comparability, but counted via a GROUP-BY-and-take-min-count approach rather than a plain
    # pandas outer merge on the key: a plain merge fans out combinatorially whenever either side
    # has more than one row sharing the same 5-field key (confirmed to happen here -- an initial
    # merge produced 1,298 "matched" rows against only 1,257 apd rows, a >100% rate, i.e. fan-out
    # artifact, not a real result; discarded, not reported as a finding).
    apd_key = apd.rename(columns={"contractid": "ContractID", "itemcode": "ItemCode",
                                    "createDate": "CtrDate", "mapped_status": "Status", "qty": "apd_qty"})
    apd_key = apd_key[["ContractID", "ItemCode", "CtrDate", "Status", "apd_qty"]].rename(columns={"apd_qty": "qty"})
    ces_key = ces[["ContractID", "ItemCode", "CtrDate", "Status", "ces_qty"]].rename(columns={"ces_qty": "qty"})

    apd_counts = apd_key.groupby(["ContractID", "ItemCode", "CtrDate", "Status", "qty"]).size().reset_index(name="n_apd")
    ces_counts = ces_key.groupby(["ContractID", "ItemCode", "CtrDate", "Status", "qty"]).size().reset_index(name="n_ces")
    merged = apd_counts.merge(ces_counts, on=["ContractID", "ItemCode", "CtrDate", "Status", "qty"], how="outer")
    merged["n_apd"] = merged["n_apd"].fillna(0)
    merged["n_ces"] = merged["n_ces"].fillna(0)
    merged["n_matched"] = merged[["n_apd", "n_ces"]].min(axis=1)
    merged.to_csv(out("check7_merged.csv"), index=False)

    n_apd = int(apd_counts["n_apd"].sum())
    n_matched_5field = int(merged["n_matched"].sum())
    match_rate = 100.0 * n_matched_5field / n_apd if n_apd else None

    summary = {
        "usable_from_date": usable_from_date,
        "n_apd_rows": n_apd,
        "n_ces_rows": int(ces_counts["n_ces"].sum()),
        "n_matched_on_5fields": n_matched_5field,
        "row_level_match_rate_pct": round(match_rate, 2) if match_rate is not None else None,
        "apd_only_rows": int((merged["n_apd"] - merged["n_matched"]).sum()),
        "ces_only_rows": int((merged["n_ces"] - merged["n_matched"]).sum()),
    }
    pd.DataFrame([summary]).to_csv(out("check7_summary.csv"), index=False)
    print("\n--- Check 7 summary ---")
    print(summary)
    return merged, summary


def check8(codes_sql, usable_from_date, div_filter_where):
    logger.info("CHECK 8: demand profile")
    sql = f"""
    SELECT itemcode, YEAR(createDate) AS yr, MONTH(createDate) AS mo, SUM(qty) AS qty, SUM(sale) AS sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql} {div_filter_where} AND createDate >= '{usable_from_date}'
    GROUP BY itemcode, YEAR(createDate), MONTH(createDate)
    ORDER BY itemcode, yr, mo
    """
    df = run_query(sql)
    df.to_csv(out("check8_raw_monthly.csv"), index=False)

    if df.empty:
        logger.warning("Check8: no rows returned under filter")
        return df, pd.DataFrame(), {}

    df["year_month"] = df["yr"].astype(str) + "-" + df["mo"].astype(str).str.zfill(2)

    # Exclude the latest calendar month if it is incomplete (project convention, see
    # src/aggregate_levels.py determine_complete_months): find the max createDate under this
    # scope/filter and check whether it reaches that month's own last day.
    sql_maxdate = f"""
    SELECT MAX(createDate) AS mx FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN {codes_sql} {div_filter_where} AND createDate >= '{usable_from_date}'
    """
    max_date = pd.to_datetime(run_query(sql_maxdate)["mx"].iloc[0])
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_period = str(pd.Period(max_date, freq="M"))
    if max_date < month_end:
        logger.info("Latest month %s is partial (data ends %s, month ends %s) -- excluded from demand profile",
                    latest_period, max_date.date(), month_end.date())
        df = df[df["year_month"] != latest_period]
    else:
        logger.info("Latest month %s is complete -- kept", latest_period)

    all_months = sorted(df["year_month"].unique())
    all_items = sorted(df["itemcode"].unique())

    # build full item x month grid (zero-fill)
    idx = pd.MultiIndex.from_product([all_items, all_months], names=["itemcode", "year_month"])
    grid = df.groupby(["itemcode", "year_month"])["qty"].sum().reindex(idx, fill_value=0).reset_index()

    rows = []
    for item, g in grid.groupby("itemcode"):
        qty = g.sort_values("year_month")["qty"].to_numpy(dtype=float)
        n_periods = len(qty)
        nonzero = qty[qty > 0]
        n_nonzero = len(nonzero)
        pct_zero = 100.0 * (n_periods - n_nonzero) / n_periods
        if n_nonzero == 0:
            cls, adi, cv2 = "NoSale", None, None
        else:
            adi = n_periods / n_nonzero
            mean_d = nonzero.mean()
            std_d = nonzero.std(ddof=1) if n_nonzero > 1 else 0.0
            cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
            if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
                cls = "Smooth"
            elif adi < ADI_THRESHOLD:
                cls = "Erratic"
            elif cv2 < CV2_THRESHOLD:
                cls = "Intermittent"
            else:
                cls = "Lumpy"
        rows.append({"itemcode": item, "n_periods": n_periods, "n_nonzero_periods": n_nonzero,
                     "pct_zero": round(pct_zero, 1), "ADI": adi, "CV2": cv2, "classification": cls,
                     "total_qty": float(qty.sum())})
    stats_df = pd.DataFrame(rows)
    stats_df.to_csv(out("check8_item_classification.csv"), index=False)

    n_any_sales = (stats_df["classification"] != "NoSale").sum()
    total_value_thb = df["sale"].sum()
    class_counts = stats_df["classification"].value_counts().to_dict()
    excl_nosale = stats_df[stats_df["classification"] != "NoSale"]
    mean_adi = excl_nosale["ADI"].mean()
    mean_cv2 = excl_nosale["CV2"].mean()
    overall_pct_zero = stats_df["pct_zero"].mean()

    summary = {
        "usable_from_date": usable_from_date,
        "n_months": len(all_months),
        "n_items_with_pricelist_codes": len(codes_sql.split(",")),  # rough
        "n_items_any_sales": int(n_any_sales),
        "n_items_no_sale": int((stats_df["classification"] == "NoSale").sum()),
        "total_value_thb": float(total_value_thb),
        "mean_pct_zero_item_months": round(float(overall_pct_zero), 1),
        "mean_ADI_excl_nosale": round(float(mean_adi), 3) if pd.notna(mean_adi) else None,
        "mean_CV2_excl_nosale": round(float(mean_cv2), 3) if pd.notna(mean_cv2) else None,
        **{f"class_{k}": int(v) for k, v in class_counts.items()},
    }
    pd.DataFrame([summary]).to_csv(out("check8_summary.csv"), index=False)
    print("\n--- Check 8 summary ---")
    print(summary)
    return df, stats_df, summary


if __name__ == "__main__":
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    codes, pem_pricelist_df = get_item_codes()
    codes_sql = sql_in_list(codes)

    c1 = check1(codes_sql)
    c2 = check2(codes_sql, f"AND division = '{DIVISION}'")
    c3 = check3(codes_sql, codes)

    # Concluded in-scope filter (matching project-wide convention): division=PEM103,
    # revenue_type='Omni Channel', status IN ('Actual','MPS'). Usable-from date 2024-01-01
    # (whole-table min createDate for these 87 codes is 2024-01-03 -- no earlier rows exist
    # at all, confirmed by ad hoc query, see report).
    USABLE_FROM = "2024-01-01"
    div_filter_where = f"AND division = '{DIVISION}' AND revenue_type = 'Omni Channel' AND status IN ('Actual','MPS')"

    c4 = check4(codes_sql, div_filter_where)
    c5 = check5(codes, pem_pricelist_df, div_filter_where)
    c6 = check6(codes, codes_sql)
    c7 = check7(codes_sql, USABLE_FROM)
    c8 = check8(codes_sql, USABLE_FROM, div_filter_where)

    print("\n\nAll 8 checks complete.")
