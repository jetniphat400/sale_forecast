"""Phase C Validator — PEM102, part 2: checks 4 (duplicates), 5 (pricelist agreement),
7 (Cube_CES cross-check), 8 (demand profile). Continues from
phaseC_validator_PEM102.py using the concluded filter: division='PEM102',
revenue_type='Omni Channel', status IN ('Actual','MPS'), createDate >= 2024-01-01.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_validator_PEM102_part2")

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
    pricelist = load_visible_product_rows("reference/pricelist.xlsx")
    pem102 = pricelist[pricelist["business"] == "PEM102"].copy()
    codes = sorted(pem102["code"].unique().tolist())
    codes_in = sql_in_list(codes)

    # Concluded filter (Check 1): division=PEM102, revenue_type=Omni Channel,
    # status IN (Actual, MPS), createDate >= 2024-01-01
    sql_filtered = f"""
    SELECT itemcode, contractid, createDate, forecast_date, qty, sale, status, division,
           revenue_type, productCateName, productTypeName, quotationid
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({codes_in})
      AND division = 'PEM102'
      AND revenue_type = 'Omni Channel'
      AND status IN ('Actual', 'MPS')
      AND createDate >= '2024-01-01'
    """
    df = run_query(sql_filtered)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])
    df.to_csv(outpath("filtered_scope_rows.csv"), index=False)
    logger.info("Filtered scope: %d rows, %d items", len(df), df["itemcode"].nunique())

    # ============================================================
    # CHECK 4: Duplicates and split lots
    # ============================================================
    logger.info("CHECK 4: duplicates and split lots")
    grp_cols = ["contractid", "itemcode", "createDate", "qty", "sale", "status"]
    df["_key"] = df[grp_cols].astype(str).agg("|".join, axis=1)
    grp_sizes = df.groupby("_key").size()
    dup_keys = grp_sizes[grp_sizes > 1].index
    dup_rows = df[df["_key"].isin(dup_keys)].copy()
    logger.info("%d rows across %d duplicate groups (n>1)", len(dup_rows), len(dup_keys))

    bucket_rows = []
    for key, g in dup_rows.groupby("_key"):
        n_distinct_fd = g["forecast_date"].nunique(dropna=False)
        bucket = "split_lot_plausible" if n_distinct_fd > 1 else "unexplained_duplicate"
        bucket_rows.append({
            "key": key, "n_rows": len(g), "n_distinct_forecast_date": n_distinct_fd,
            "bucket": bucket, "sum_sale": g["sale"].sum(), "sum_qty": g["qty"].sum(),
            "contractid": g["contractid"].iloc[0], "itemcode": g["itemcode"].iloc[0],
        })
    dup_summary = pd.DataFrame(bucket_rows)
    dup_summary.to_csv(outpath("check4_duplicate_groups.csv"), index=False)

    if len(dup_summary):
        agg = dup_summary.groupby("bucket").agg(
            n_groups=("key", "count"), n_rows=("n_rows", "sum"), total_sale=("sum_sale", "sum")
        )
        print("\n=== CHECK 4: duplicate group buckets ===")
        print(agg.to_string())
    else:
        print("\n=== CHECK 4: no duplicate groups (n>1) found ===")
    dup_summary_agg = dup_summary.groupby("bucket").agg(
        n_groups=("key", "count"), n_rows=("n_rows", "sum"), total_sale=("sum_sale", "sum")
    ).reset_index() if len(dup_summary) else pd.DataFrame()
    dup_summary_agg.to_csv(outpath("check4_duplicate_bucket_summary.csv"), index=False)

    # ============================================================
    # CHECK 5: Pricelist agreement
    # ============================================================
    logger.info("CHECK 5: pricelist agreement")
    db_names = df.groupby("itemcode").agg(
        db_categories=("productCateName", lambda x: sorted(set(x.dropna()))),
        db_types=("productTypeName", lambda x: sorted(set(x.dropna()))),
    ).reset_index()

    pl_names = pem102[["code", "category", "type"]].drop_duplicates()
    merged = pl_names.merge(db_names, left_on="code", right_on="itemcode", how="left")
    merged["db_categories"] = merged["db_categories"].apply(lambda x: x if isinstance(x, list) else [])
    merged["db_types"] = merged["db_types"].apply(lambda x: x if isinstance(x, list) else [])

    def cat_mismatch(row):
        if not row["db_categories"]:
            return "no_db_rows_in_scope"
        return "MATCH" if row["category"] in row["db_categories"] else "MISMATCH"

    def type_mismatch(row):
        if not row["db_types"]:
            return "no_db_rows_in_scope"
        return "MATCH" if row["type"] in row["db_types"] else "MISMATCH"

    merged["category_status"] = merged.apply(cat_mismatch, axis=1)
    merged["type_status"] = merged.apply(type_mismatch, axis=1)
    merged["multi_category_in_db"] = merged["db_categories"].apply(lambda x: len(x) > 1)
    merged["multi_type_in_db"] = merged["db_types"].apply(lambda x: len(x) > 1)
    merged.to_csv(outpath("check5_pricelist_agreement.csv"), index=False)

    print("\n=== CHECK 5: pricelist agreement summary ===")
    print(merged["category_status"].value_counts().to_string())
    print()
    print(merged["type_status"].value_counts().to_string())
    print("\nMismatches / multi-value detail:")
    print(merged[(merged["category_status"] != "MATCH") | (merged["type_status"] != "MATCH")
                 | merged["multi_category_in_db"] | merged["multi_type_in_db"]]
          [["code", "category", "db_categories", "category_status", "type", "db_types", "type_status"]]
          .to_string(index=False))

    # ============================================================
    # CHECK 7: Cross-check against Cube_CES
    # ============================================================
    logger.info("CHECK 7: Cube_CES cross-check")
    sql_ces = f"""
    SELECT ContractID, ItemCode, CtrDate, ForecastDelDate, PlanQty, ActualQty, BacklogQty, Status
    FROM [salewarehouse].[dbo].[Cube_CES]
    WHERE ItemCode IN ({codes_in})
      AND ManuDivision = 'PEM102'
      AND RevenueType = 'Omni Channel'
      AND CtrDate >= '2024-01-01'
      AND Status IN ('Actual', 'Backlog')
    """
    ces = run_query(sql_ces)
    ces.to_csv(outpath("check7_ces_raw.csv"), index=False)
    logger.info("Cube_CES pull: %d rows", len(ces))

    # Map cube_Sale_APD status MPS -> Cube_CES Backlog, Actual -> Actual (per PEM101 finding)
    df["_mapped_status"] = df["status"].map({"MPS": "Backlog", "Actual": "Actual"})
    df["_match_key"] = (
        df["contractid"].astype(str) + "|" + df["itemcode"].astype(str) + "|"
        + df["createDate"].dt.strftime("%Y-%m-%d") + "|" + df["_mapped_status"].astype(str) + "|"
        + df["qty"].astype(str)
    )
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"])
    ces["_match_key"] = (
        ces["ContractID"].astype(str) + "|" + ces["ItemCode"].astype(str) + "|"
        + ces["CtrDate"].dt.strftime("%Y-%m-%d") + "|" + ces["Status"].astype(str) + "|"
        + ces["ActualQty"].fillna(0).astype(str)
    )
    # For Backlog rows, ActualQty is usually 0 and BacklogQty holds the amount -- build alt key
    ces["_qty_for_match"] = np.where(ces["Status"] == "Backlog", ces["BacklogQty"], ces["ActualQty"])
    ces["_match_key2"] = (
        ces["ContractID"].astype(str) + "|" + ces["ItemCode"].astype(str) + "|"
        + ces["CtrDate"].dt.strftime("%Y-%m-%d") + "|" + ces["Status"].astype(str) + "|"
        + ces["_qty_for_match"].astype(str)
    )

    ces_keys = set(ces["_match_key2"])
    df["_matched_in_ces"] = df["_match_key"].isin(ces_keys)
    match_rate = df["_matched_in_ces"].mean() * 100
    print(f"\n=== CHECK 7: row-level match rate cube_Sale_APD -> Cube_CES ===")
    print(f"{df['_matched_in_ces'].sum()} of {len(df)} rows match on (ContractID, ItemCode, CtrDate, mapped Status, Qty): {match_rate:.2f}%")

    df[["itemcode", "contractid", "createDate", "status", "qty", "sale", "_matched_in_ces"]].to_csv(
        outpath("check7_row_level_match_detail.csv"), index=False
    )

    # Contract-item level qty reconciliation
    apd_ci = df.groupby(["contractid", "itemcode"])["qty"].sum().reset_index().rename(columns={"qty": "apd_qty"})
    ces["_qty2"] = np.where(ces["Status"] == "Backlog", ces["BacklogQty"], ces["ActualQty"])
    ces_ci = ces.groupby(["ContractID", "ItemCode"])["_qty2"].sum().reset_index().rename(
        columns={"ContractID": "contractid", "ItemCode": "itemcode", "_qty2": "ces_qty"})
    recon = apd_ci.merge(ces_ci, on=["contractid", "itemcode"], how="outer", indicator=True)
    recon["qty_match"] = np.isclose(recon["apd_qty"].fillna(-1), recon["ces_qty"].fillna(-2))
    recon.to_csv(outpath("check7_contract_item_reconciliation.csv"), index=False)
    both = recon[recon["_merge"] == "both"]
    print(f"\nContract-item pairs: {len(recon)} total, {len(both)} in both sources, "
          f"{both['qty_match'].sum()} ({100*both['qty_match'].mean():.2f}%) with exact qty match, "
          f"{(recon['_merge']=='left_only').sum()} only in cube_Sale_APD, "
          f"{(recon['_merge']=='right_only').sum()} only in Cube_CES")

    # ============================================================
    # CHECK 8: Demand profile
    # ============================================================
    logger.info("CHECK 8: demand profile")
    max_date = df["createDate"].max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_month = pd.Period(max_date, freq="M")
    df["year_month"] = df["createDate"].dt.to_period("M").astype(str)

    monthly_complete = df.copy()
    if max_date < month_end:
        logger.info("Latest month %s partial (data ends %s) -- excluded from demand profile", latest_month, max_date.date())
        monthly_complete = monthly_complete[monthly_complete["year_month"] != str(latest_month)]

    all_months = sorted(monthly_complete["year_month"].unique())
    logger.info("Demand profile window: %s to %s (%d months)", all_months[0], all_months[-1], len(all_months))

    monthly_qty = monthly_complete.groupby(["itemcode", "year_month"])["qty"].sum().reset_index()
    # build a complete item x month grid (fill zeros)
    full_index = pd.MultiIndex.from_product([codes, all_months], names=["itemcode", "year_month"])
    grid = monthly_qty.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0).reset_index()
    grid.to_csv(outpath("check8_monthly_qty_grid.csv"), index=False)

    item_rows = []
    for item, g in grid.groupby("itemcode"):
        g = g.sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        cls, adi, cv2 = classify_demand(qty)
        n_zero = int((qty == 0).sum())
        item_rows.append({
            "itemcode": item, "n_periods": len(qty), "n_zero_periods": n_zero,
            "pct_zero": round(100 * n_zero / len(qty), 1),
            "ADI": round(adi, 3) if adi is not None else None,
            "CV2": round(cv2, 3) if cv2 is not None else None,
            "classification": cls, "total_qty": float(qty.sum()),
        })
    item_stats = pd.DataFrame(item_rows)
    item_stats.to_csv(outpath("check8_item_demand_classification.csv"), index=False)

    total_value = df["sale"].sum()
    n_with_sales = (item_stats["classification"] != "NoSale").sum()
    print(f"\n=== CHECK 8: demand profile ({all_months[0]} to {all_months[-1]}, {len(all_months)} months) ===")
    print(f"Total value (THB): {total_value:,.2f}")
    print(f"Items with any sales: {n_with_sales} of {len(item_stats)}")
    print(f"Mean %% zero item-months: {item_stats['pct_zero'].mean():.1f}%")
    print("\nClassification counts:")
    print(item_stats["classification"].value_counts().to_string())
    has_sales = item_stats[item_stats["classification"] != "NoSale"]
    print(f"\nMean ADI (excl. NoSale): {has_sales['ADI'].mean():.3f}")
    print(f"Mean CV2 (excl. NoSale): {has_sales['CV2'].mean():.3f}")

    logger.info("Part 2 complete.")


if __name__ == "__main__":
    main()
