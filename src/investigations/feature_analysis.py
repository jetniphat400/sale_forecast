"""Rule-based selection task, Parts 1-2: measure series characteristics at
Category, Type and Item level, and test their stability across windows
(first 12 months, first 24 months, full history).

Investigation/measurement only. Does not select or write any model choice.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from series_features import compute_all_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("feature_analysis")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

WINDOWS = {"first_12": 12, "first_24": 24, "full": None}


def determine_complete_months(monthly_df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    max_date = pd.to_datetime(raw_df["createDate"]).max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_month = pd.Period(max_date, freq="M")
    if max_date < month_end:
        logger.info("Latest month %s is partial (data ends %s, month ends %s) — excluded",
                     latest_month, max_date.date(), month_end.date())
        monthly_df = monthly_df[monthly_df["year_month"].astype(str) != str(latest_month)]
    return monthly_df


def build_all_series(monthly: pd.DataFrame, scope: pd.DataFrame) -> dict:
    """Returns {(level, key, category): (qty_array, months_list)} for Category,
    Type and Item levels. Item level includes ALL 128 scope codes — those with
    no history at all get an empty/all-zero placeholder, flagged separately."""
    series = {}

    for cat, g in monthly.groupby("category"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        series[("Category", cat, cat)] = (agg["qty"].to_numpy(dtype=float), agg["year_month"].astype(str).tolist())

    for (cat, typ), g in monthly.groupby(["category", "type"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        series[("Type", typ, cat)] = (agg["qty"].to_numpy(dtype=float), agg["year_month"].astype(str).tolist())

    all_months = sorted(monthly["year_month"].unique())
    items_with_history = set(monthly["itemcode"].unique())
    for _, row in scope.iterrows():
        code, cat = row["code"], row["category"]
        if code in items_with_history:
            g = monthly[monthly["itemcode"] == code].sort_values("year_month")
            series[("Item", code, cat)] = (g["qty"].to_numpy(dtype=float), g["year_month"].astype(str).tolist())
        else:
            series[("Item", code, cat)] = (np.array([]), [])  # no history at all — flagged in features

    return series


def features_for_window(qty: np.ndarray, months: list, window_months) -> dict:
    if len(qty) == 0:
        return {"n_periods": 0, "classification": "NoSale", "note": "zero sales history at all under current filters"}
    if window_months is not None:
        if len(qty) < window_months:
            return {"n_periods": len(qty), "classification": None,
                    "note": f"series has only {len(qty)} months, fewer than the {window_months}-month window — not computed"}
        qty_w, months_w = qty[:window_months], months[:window_months]
    else:
        qty_w, months_w = qty, months
    return compute_all_features(qty_w, months_w)


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))

    total_months = monthly["year_month"].nunique()
    logger.info("Working with %d complete months (%s to %s)", total_months, monthly["year_month"].min(), monthly["year_month"].max())

    series = build_all_series(monthly, scope)
    logger.info("Built %d series: %d Category, %d Type, %d Item",
                len(series), sum(1 for k in series if k[0] == "Category"),
                sum(1 for k in series if k[0] == "Type"), sum(1 for k in series if k[0] == "Item"))

    # ================= PART 1: full-history features =================
    part1_rows = []
    for (level, key, cat), (qty, months) in series.items():
        feat = features_for_window(qty, months, None)
        part1_rows.append({"level": level, "key": key, "category": cat, **feat})
    part1_df = pd.DataFrame(part1_rows)
    part1_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part1_series_features_full_history.csv"), index=False)

    # ================= PART 2: stability across windows =================
    part2_rows = []
    for (level, key, cat), (qty, months) in series.items():
        for window_name, window_months in WINDOWS.items():
            feat = features_for_window(qty, months, window_months)
            part2_rows.append({"level": level, "key": key, "category": cat, "window": window_name, **feat})
    part2_df = pd.DataFrame(part2_rows)
    part2_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part2_features_by_window.csv"), index=False)

    # Stability: does classification stay the same across first_12, first_24, full
    # (only where all three windows were computable — i.e., series has >= 24 months)
    stability_rows = []
    for (level, key, cat), (qty, months) in series.items():
        cls_by_window = {}
        for window_name, window_months in WINDOWS.items():
            feat = features_for_window(qty, months, window_months)
            cls_by_window[window_name] = feat.get("classification")
        computable = {w: c for w, c in cls_by_window.items() if c is not None}
        distinct = set(computable.values())
        stability_rows.append({
            "level": level, "key": key, "category": cat,
            "cls_first_12": cls_by_window.get("first_12"), "cls_first_24": cls_by_window.get("first_24"),
            "cls_full": cls_by_window.get("full"),
            "n_windows_computable": len(computable),
            "stable": len(distinct) == 1 if len(computable) == 3 else None,
            "note": "all 3 windows computable" if len(computable) == 3 else f"only {len(computable)} of 3 windows computable (series too short)",
        })
    stability_df = pd.DataFrame(stability_rows)
    stability_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part2_stability_summary.csv"), index=False)

    print("\n" + "=" * 90)
    print("PART 1: SERIES CHARACTERISTICS (full history) — summary by level")
    print("=" * 90)
    for level in ["Category", "Type", "Item"]:
        sub = part1_df[part1_df["level"] == level]
        print(f"\n--- {level} level ({len(sub)} series) ---")
        if level != "Item":
            print(sub[["key", "n_periods", "pct_zero", "ADI", "CV2", "classification",
                        "trend_direction", "level_shift_detected", "month_of_year_strength"]].to_string(index=False))
        else:
            print("Classification distribution:")
            print(sub["classification"].value_counts(dropna=False).to_string())
            print(f"\nTrend direction distribution:")
            print(sub["trend_direction"].value_counts(dropna=False).to_string())
            print(f"\nLevel shift detected: {sub['level_shift_detected'].sum()} of {sub['level_shift_detected'].notna().sum()} testable series")

    print("\n" + "=" * 90)
    print("PART 2: CLASSIFICATION STABILITY ACROSS WINDOWS (first 12 vs first 24 vs full)")
    print("=" * 90)
    for level in ["Category", "Type", "Item"]:
        sub = stability_df[stability_df["level"] == level]
        testable = sub[sub["n_windows_computable"] == 3]
        n_stable = testable["stable"].sum()
        n_testable = len(testable)
        n_untestable = len(sub) - n_testable
        print(f"\n{level}: {n_stable} of {n_testable} testable series ({100*n_stable/n_testable:.1f}%) keep the "
              f"SAME classification across all 3 windows. {n_untestable} series could not be tested "
              f"(too short for the first_24 window, i.e. < 24 months of history).")
        unstable = testable[testable["stable"] == False]
        if len(unstable):
            print(f"Unstable series (classification changes across windows):")
            print(unstable[["key", "cls_first_12", "cls_first_24", "cls_full"]].to_string(index=False))

    print("\nFull detail written to output/summary/rule_part1_series_features_full_history.csv, "
          "rule_part2_features_by_window.csv, rule_part2_stability_summary.csv")
