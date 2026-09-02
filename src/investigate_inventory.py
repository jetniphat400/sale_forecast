"""Phase 4 groundwork survey, Parts 1-2: Cube_Inventory_Exact and
Cube_Inventory_Aging structure, coverage against the 128 Fuse/Surge Arrester
item codes, and current min/max values expressed against recent sales.

Investigation only. Does not calculate new min/max values, does not modify
config.yaml, does not build or change any model.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_inventory")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def get_128_codes():
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))["code"].tolist()


def report_structure(table_name):
    cols = run_query(f"""
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
        FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{table_name}' ORDER BY ORDINAL_POSITION
    """)
    n_rows = run_query(f"SELECT COUNT(*) AS n FROM {table_name}").iloc[0]["n"]
    sample = run_query(f"SELECT TOP 5 * FROM {table_name}")
    return cols, n_rows, sample


if __name__ == "__main__":
    codes = get_128_codes()
    code_list = "','".join(codes)
    logger.info("Working with %d item codes (Fuse + Surge Arrester categories)", len(codes))

    # ================= PART 1: Cube_Inventory_Exact =================
    print("\n" + "=" * 90)
    print("PART 1: Cube_Inventory_Exact — structure")
    print("=" * 90)
    cols, n_rows, sample = report_structure("Cube_Inventory_Exact")
    cols.to_csv(os.path.join(SUMMARY_DIR, "phase4_part1_inventory_exact_structure.csv"), index=False)
    print(cols.to_string(index=False))
    print(f"\nTotal rows: {n_rows}")
    print("\nSample rows:")
    print(sample.to_string())

    ts = run_query("SELECT MIN(timestamp) mn, MAX(timestamp) mx, COUNT(DISTINCT timestamp) n_distinct_ts, "
                    "COUNT(DISTINCT CAST(timestamp AS DATE)) n_distinct_dates FROM Cube_Inventory_Exact")
    print("\nTimestamp column range:")
    print(ts.to_string(index=False))
    n_dates = ts.iloc[0]["n_distinct_dates"]
    if n_dates == 1:
        print(f"\nFINDING: only 1 distinct calendar date ({ts.iloc[0]['mn']} to {ts.iloc[0]['mx']}, same day) — "
              f"this table is a SINGLE CURRENT-STATE SNAPSHOT, not a time series. The many distinct `timestamp` "
              f"values within that one day are row-insert times from a single batch load, not separate snapshots.")
    else:
        print(f"\nFINDING: {n_dates} distinct calendar dates present — this table DOES carry a time dimension.")

    inv = run_query(f"SELECT * FROM Cube_Inventory_Exact WHERE itemcode IN ('{code_list}')")
    inv["warehouse"] = inv["warehouse"].str.strip()
    inv.to_csv(os.path.join(DATA_DIR, "raw_inventory_exact_128items.csv"), index=False)

    print(f"\n--- Coverage against 128 items ---")
    n_items_present = inv["itemcode"].nunique()
    print(f"Items appearing in Cube_Inventory_Exact (any warehouse row): {n_items_present} of {len(codes)}")
    missing = sorted(set(codes) - set(inv["itemcode"].unique()))
    print(f"Items with ZERO rows in this table: {len(missing)} -> {missing}")

    # Category mismatch: the item code appears here under a DIFFERENT product_category
    # than Fuse/Surge Arrester — flags itemcode ambiguity/reuse, same class of issue as
    # the earlier pricelist-vs-database Surge Arrester voltage-tier disagreement.
    mismatch = inv[~inv["product_category"].isin(["Fuse", "Surge Arrester"])]
    mismatch_items = sorted(mismatch["itemcode"].unique())
    if mismatch_items:
        print(f"\nFINDING (data-quality caveat): {len(mismatch_items)} of {n_items_present} matched items carry a "
              f"DIFFERENT product_category in THIS table than Fuse/Surge Arrester: {mismatch_items}")
        print(mismatch[["itemcode", "product_category", "product_type"]].drop_duplicates("itemcode").to_string(index=False))
        print("These itemcodes may be reused/collided between unrelated products in this system — treat their "
              "inventory rows with caution, not as reliable Fuse/Surge Arrester stock records.")
    mismatch.drop_duplicates("itemcode")[["itemcode", "product_category", "product_type"]].to_csv(
        os.path.join(SUMMARY_DIR, "phase4_part1_category_mismatch_items.csv"), index=False)

    # Nonzero minimum/maximum coverage, at the (item, warehouse) row grain — min/max are
    # set PER WAREHOUSE, not a single value per item (verified: they vary across warehouse
    # rows for the same item in 81 of 119 multi-warehouse items).
    n_rows_total = len(inv)
    n_nonzero_min = int((inv["minimum"] > 0).sum())
    n_nonzero_max = int((inv["maximum"] > 0).sum())
    n_items_any_nonzero_min = inv.groupby("itemcode")["minimum"].apply(lambda s: (s > 0).any()).sum()
    n_items_any_nonzero_max = inv.groupby("itemcode")["maximum"].apply(lambda s: (s > 0).any()).sum()
    print(f"\n--- Minimum/Maximum coverage ({n_rows_total} item-warehouse rows across {n_items_present} items) ---")
    print(f"Rows with minimum > 0: {n_nonzero_min} of {n_rows_total} ({100*n_nonzero_min/n_rows_total:.1f}%)")
    print(f"Rows with maximum > 0: {n_nonzero_max} of {n_rows_total} ({100*n_nonzero_max/n_rows_total:.1f}%)")
    print(f"Items with AT LEAST ONE warehouse row having minimum > 0: {n_items_any_nonzero_min} of {n_items_present}")
    print(f"Items with AT LEAST ONE warehouse row having maximum > 0: {n_items_any_nonzero_max} of {n_items_present}")

    warehouse_variation = inv.groupby("itemcode").agg(n_warehouses=("warehouse", "nunique"),
                                                        n_distinct_min=("minimum", "nunique"),
                                                        n_distinct_max=("maximum", "nunique"))
    n_multi_wh = (warehouse_variation["n_warehouses"] > 1).sum()
    n_min_varies = ((warehouse_variation["n_warehouses"] > 1) & (warehouse_variation["n_distinct_min"] > 1)).sum()
    print(f"\nFINDING: minimum/maximum are set PER WAREHOUSE, not a single value per item. Of {n_multi_wh} items "
          f"stocked in more than one warehouse, {n_min_varies} have DIFFERENT minimum values across their "
          f"warehouse rows. There is no single authoritative 'the' minimum/maximum per item without a business "
          f"decision on which warehouse(s) matter for Max-Min planning (e.g. 'FG' appeared for {int((inv['warehouse']=='FG').sum())} "
          f"of {n_items_present} items and may be the primary finished-goods location, but this is inferred from "
          f"the warehouse code, not confirmed).")

    # Sum across warehouses per item, as one honest aggregate view (labelled, not authoritative)
    per_item_sum = inv.groupby("itemcode", as_index=False).agg(
        total_stock=("stock", "sum"), total_minimum=("minimum", "sum"), total_maximum=("maximum", "sum"),
        n_warehouse_rows=("warehouse", "nunique"),
    )

    # ---- Recent average monthly sales, from the already-validated Part-1 sales pull ----
    sales_monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    raw_sales = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    max_date = pd.to_datetime(raw_sales["createDate"]).max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    if max_date < month_end:
        latest_month = str(pd.Period(max_date, freq="M"))
        sales_monthly = sales_monthly[sales_monthly["year_month"] != latest_month]
    RECENT_N_MONTHS = 6
    recent_avg = (
        sales_monthly.sort_values("year_month")
        .groupby("itemcode")
        .apply(lambda g: g.tail(RECENT_N_MONTHS)["qty"].mean())
        .rename("recent_avg_monthly_qty")
        .reset_index()
    )
    logger.info("Recent average monthly sales computed over the last %d complete months per item "
                "(from the already-validated Part 1 monthly series, not recalculated here).", RECENT_N_MONTHS)

    combined = per_item_sum.merge(recent_avg, on="itemcode", how="left")
    combined["min_months_of_cover"] = combined.apply(
        lambda r: round(r["total_minimum"] / r["recent_avg_monthly_qty"], 2)
        if r["recent_avg_monthly_qty"] and r["recent_avg_monthly_qty"] > 0 else None, axis=1)
    combined["max_months_of_cover"] = combined.apply(
        lambda r: round(r["total_maximum"] / r["recent_avg_monthly_qty"], 2)
        if r["recent_avg_monthly_qty"] and r["recent_avg_monthly_qty"] > 0 else None, axis=1)
    combined.to_csv(os.path.join(SUMMARY_DIR, "phase4_part1_minmax_vs_sales.csv"), index=False)

    has_nonzero_minmax = combined[(combined["total_minimum"] > 0) | (combined["total_maximum"] > 0)]
    print(f"\n--- Existing min/max expressed as months of recent sales cover (sum across warehouses per item) ---")
    print(f"{len(has_nonzero_minmax)} of {n_items_present} items have any nonzero min or max set at all.")
    print(has_nonzero_minmax[["itemcode", "total_minimum", "total_maximum", "recent_avg_monthly_qty",
                               "min_months_of_cover", "max_months_of_cover"]].sort_values("itemcode").to_string(index=False))

    no_sales_but_minmax = has_nonzero_minmax[has_nonzero_minmax["recent_avg_monthly_qty"].isna() | (has_nonzero_minmax["recent_avg_monthly_qty"] == 0)]
    if len(no_sales_but_minmax):
        print(f"\nFINDING: {len(no_sales_but_minmax)} items have a nonzero minimum/maximum setting but ZERO recent "
              f"average monthly sales — cover cannot be expressed as a multiple (division by zero), and this is a "
              f"concrete sign the setting may be STALE rather than reflecting current demand:")
        print(no_sales_but_minmax[["itemcode", "total_minimum", "total_maximum"]].to_string(index=False))

    # ================= PART 2: Cube_Inventory_Aging =================
    print("\n" + "=" * 90)
    print("PART 2: Cube_Inventory_Aging — structure")
    print("=" * 90)
    cols2, n_rows2, sample2 = report_structure("Cube_Inventory_Aging")
    cols2.to_csv(os.path.join(SUMMARY_DIR, "phase4_part2_inventory_aging_structure.csv"), index=False)
    print(cols2.to_string(index=False))
    print(f"\nTotal rows: {n_rows2}")
    print("\nSample rows:")
    print(sample2.to_string())

    date_cols = [c for c in cols2["COLUMN_NAME"] if "date" in c.lower() or "time" in c.lower()]
    print(f"\nColumns that look date/time-related: {date_cols}")
    for c in date_cols:
        d = run_query(f"SELECT MIN({c}) mn, MAX({c}) mx, COUNT(DISTINCT CAST({c} AS DATE)) n_dates FROM Cube_Inventory_Aging")
        print(f"  {c}: min={d.iloc[0]['mn']}, max={d.iloc[0]['mx']}, distinct dates={d.iloc[0]['n_dates']}")

    for cat_col in ["Condition", "Type", "ItemStatus", "Assortment"]:
        if cat_col in cols2["COLUMN_NAME"].values:
            dv = run_query(f"SELECT {cat_col}, COUNT(*) AS n FROM Cube_Inventory_Aging GROUP BY {cat_col} ORDER BY n DESC")
            print(f"\nDistinct values of {cat_col} (whole table):")
            print(dv.to_string(index=False))

    aging = run_query(f"SELECT * FROM Cube_Inventory_Aging WHERE ItemCode IN ('{code_list}')")
    aging.to_csv(os.path.join(DATA_DIR, "raw_inventory_aging_128items.csv"), index=False)
    n_items_aging = aging["ItemCode"].nunique()
    print(f"\n--- Coverage against 128 items ---")
    print(f"Items appearing in Cube_Inventory_Aging: {n_items_aging} of {len(codes)}")
    missing_aging = sorted(set(codes) - set(aging["ItemCode"].unique())) if n_items_aging else codes
    print(f"Items with ZERO rows: {len(missing_aging)}")
    if n_items_aging:
        print("\nSample of matched rows:")
        print(aging.head(20).to_string())
        print("\nCondition/Type/ItemStatus distribution WITHIN the 128-item matches:")
        for cat_col in ["Condition", "Type", "ItemStatus"]:
            if cat_col in aging.columns:
                print(f"  {cat_col}:")
                print(aging[cat_col].value_counts(dropna=False).to_string())
