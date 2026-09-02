"""Part 2: builds monthly series at Category, Type and Item level from the
full Fuse + Surge Arrester scope, and compares % zero periods, ADI, CV-squared
and demand classification side by side, to see whether aggregation reduces
zero-inflation and volatility relative to item-level series.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aggregate_levels")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


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


def determine_complete_months(monthly_df: pd.DataFrame, raw_df: pd.DataFrame, date_col="createDate") -> pd.DataFrame:
    max_date = pd.to_datetime(raw_df[date_col]).max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_month = pd.Period(max_date, freq="M")
    if max_date < month_end:
        logger.info("Latest month %s is partial (data ends %s, month ends %s) — excluded", latest_month, max_date.date(), month_end.date())
        monthly_df = monthly_df[monthly_df["year_month"].astype(str) != str(latest_month)]
    else:
        logger.info("Latest month %s is complete — kept", latest_month)
    return monthly_df


def series_stats(qty: np.ndarray) -> dict:
    n = len(qty)
    n_zero = int((qty == 0).sum())
    cls, adi, cv2 = classify_demand(qty)
    return {
        "n_periods": n, "n_zero_periods": n_zero, "pct_zero": round(100 * n_zero / n, 1) if n else None,
        "ADI": round(adi, 3) if adi is not None else None, "CV2": round(cv2, 3) if cv2 is not None else None,
        "classification": cls, "total_qty": float(qty.sum()), "mean_qty": round(float(qty.mean()), 2),
    }


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    item_codes = sorted(monthly["itemcode"].unique())
    logger.info("Working with %d items, %d complete months", len(item_codes), monthly["year_month"].nunique())

    scope = monthly[["itemcode", "category", "type"]].drop_duplicates()

    # ---- ITEM level ----
    item_rows = []
    for item, g in monthly.groupby("itemcode"):
        g = g.sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        cat = g["category"].iloc[0]
        typ = g["type"].iloc[0]
        item_rows.append({"level": "Item", "key": item, "category": cat, "type": typ, **series_stats(qty)})
    item_df = pd.DataFrame(item_rows)

    # ---- TYPE level ----
    type_rows = []
    for (cat, typ), g in monthly.groupby(["category", "type"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        n_items = g["itemcode"].nunique()
        type_rows.append({"level": "Type", "key": typ, "category": cat, "type": typ, "n_items_aggregated": n_items, **series_stats(qty)})
    type_df = pd.DataFrame(type_rows)

    # ---- CATEGORY level ----
    cat_rows = []
    for cat, g in monthly.groupby("category"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        n_items = g["itemcode"].nunique()
        cat_rows.append({"level": "Category", "key": cat, "category": cat, "type": None, "n_items_aggregated": n_items, **series_stats(qty)})
    cat_df = pd.DataFrame(cat_rows)

    item_df.to_csv(os.path.join(SUMMARY_DIR, "part2_item_level_stats.csv"), index=False)
    type_df.to_csv(os.path.join(SUMMARY_DIR, "part2_type_level_stats.csv"), index=False)
    cat_df.to_csv(os.path.join(SUMMARY_DIR, "part2_category_level_stats.csv"), index=False)

    combined = pd.concat([cat_df, type_df, item_df], ignore_index=True, sort=False)
    combined.to_csv(os.path.join(SUMMARY_DIR, "part2_all_levels_combined.csv"), index=False)

    print("\n" + "=" * 78)
    print("PART 2: AGGREGATION COMPARISON — Category vs Type vs Item level")
    print("=" * 78)

    print("\n--- CATEGORY level (2 series) ---")
    print(cat_df[["key", "n_items_aggregated", "n_periods", "pct_zero", "ADI", "CV2", "classification", "total_qty"]].to_string(index=False))

    print("\n--- TYPE level (8 series) ---")
    print(type_df[["key", "category", "n_items_aggregated", "n_periods", "pct_zero", "ADI", "CV2", "classification", "total_qty"]].to_string(index=False))

    print(f"\n--- ITEM level ({len(item_df)} series) — summary distribution ---")
    print("Classification counts:")
    print(item_df["classification"].value_counts().to_string())
    print(f"\nMean pct_zero across items: {item_df['pct_zero'].mean():.1f}%   Median: {item_df['pct_zero'].median():.1f}%")
    print(f"Mean ADI across items (excl. NoSale): {item_df.loc[item_df['classification']!='NoSale','ADI'].mean():.2f}")
    print(f"Mean CV2 across items (excl. NoSale): {item_df.loc[item_df['classification']!='NoSale','CV2'].mean():.2f}")

    # ---- Explicit reduction comparison ----
    item_mean_pct_zero = item_df["pct_zero"].mean()
    type_mean_pct_zero = type_df["pct_zero"].mean()
    cat_mean_pct_zero = cat_df["pct_zero"].mean()
    item_lumpy_intermittent_pct = 100 * item_df["classification"].isin(["Lumpy", "Intermittent"]).mean()
    type_lumpy_intermittent_pct = 100 * type_df["classification"].isin(["Lumpy", "Intermittent"]).mean()
    cat_lumpy_intermittent_pct = 100 * cat_df["classification"].isin(["Lumpy", "Intermittent"]).mean()

    print("\n--- ZERO-INFLATION REDUCTION FROM AGGREGATION ---")
    print(f"Item level:     mean % zero periods = {item_mean_pct_zero:.1f}%   ({item_lumpy_intermittent_pct:.0f}% of series are Lumpy/Intermittent)")
    print(f"Type level:     mean % zero periods = {type_mean_pct_zero:.1f}%   ({type_lumpy_intermittent_pct:.0f}% of series are Lumpy/Intermittent)")
    print(f"Category level: mean % zero periods = {cat_mean_pct_zero:.1f}%   ({cat_lumpy_intermittent_pct:.0f}% of series are Lumpy/Intermittent)")
    print(f"\nReduction, Item -> Type: {item_mean_pct_zero - type_mean_pct_zero:+.1f} percentage points")
    print(f"Reduction, Item -> Category: {item_mean_pct_zero - cat_mean_pct_zero:+.1f} percentage points")
