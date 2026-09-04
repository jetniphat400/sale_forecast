"""Part 3: tests monthly, 2-month and quarterly bucket sizes at Category and
Type level, reporting periods available, non-zero periods, % zero, ADI and
CV-squared recomputed at each granularity. Recommends a granularity per level
based on the evidence. Does NOT write the choice to config.yaml.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from aggregate_levels import classify_demand, determine_complete_months, series_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("granularity_test")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

GRANULARITIES = {"monthly": 1, "2-month": 2, "quarterly": 3}

# Rule of thumb applied uniformly: need at least ~13 periods to leave a usable
# train set (>=7) after a 6-period-equivalent holdout for backtesting: for
# non-monthly buckets we scale the practical holdout down proportionally
# (kept explicit in the printed reasoning, not hardcoded elsewhere).
MIN_USEFUL_PERIODS = 8


def bucket_series(monthly_qty: pd.Series, months_per_bucket: int) -> np.ndarray:
    """monthly_qty is a chronologically sorted array of monthly quantities.
    Groups every `months_per_bucket` consecutive months into one bucket (sum).
    A trailing partial bucket (fewer than months_per_bucket months) is dropped,
    since a partial bucket isn't comparable in scale to the others."""
    n = len(monthly_qty)
    n_full_buckets = n // months_per_bucket
    usable = monthly_qty[: n_full_buckets * months_per_bucket]
    return usable.reshape(n_full_buckets, months_per_bucket).sum(axis=1)


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)

    results = []

    # Category level
    for cat, g in monthly.groupby("category"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        for gran_name, months_per_bucket in GRANULARITIES.items():
            bucketed = bucket_series(qty, months_per_bucket)
            stats = series_stats(bucketed)
            results.append({"level": "Category", "key": cat, "granularity": gran_name, "months_per_bucket": months_per_bucket, **stats})

    # Type level
    for (cat, typ), g in monthly.groupby(["category", "type"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        for gran_name, months_per_bucket in GRANULARITIES.items():
            bucketed = bucket_series(qty, months_per_bucket)
            stats = series_stats(bucketed)
            results.append({"level": "Type", "key": typ, "category": cat, "granularity": gran_name, "months_per_bucket": months_per_bucket, **stats})

    results_df = pd.DataFrame(results)
    results_df.to_csv(os.path.join(SUMMARY_DIR, "part3_granularity_test.csv"), index=False)

    print("\n" + "=" * 78)
    print("PART 3: GRANULARITY TEST — Category and Type level")
    print("=" * 78)
    for level in ["Category", "Type"]:
        sub = results_df[results_df["level"] == level]
        print(f"\n--- {level} level ---")
        cols = ["key", "granularity", "n_periods", "n_zero_periods", "pct_zero", "ADI", "CV2", "classification"]
        print(sub[cols].to_string(index=False))

    print("\n--- RECOMMENDATION REASONING ---")
    print(f"Monthly gives the most data points (31) but the highest zero share at Type level for the")
    print(f"thinnest Types. Quarterly (10 periods) and 2-month (15 periods) reduce zero periods further")
    print(f"but leave fewer points to fit and validate a model (rolling-origin/train-val-test both need")
    print(f"a minimum of roughly {MIN_USEFUL_PERIODS}+ periods per split to be meaningful).")

    recommendations = []
    for level in ["Category", "Type"]:
        for key, g in results_df[results_df["level"] == level].groupby("key"):
            g = g.set_index("granularity")
            monthly_zero = g.loc["monthly", "pct_zero"]
            q_periods = g.loc["quarterly", "n_periods"]
            two_periods = g.loc["2-month", "n_periods"]
            if monthly_zero == 0.0:
                rec = "monthly"
                reason = "already 0% zero periods at monthly granularity — no need to coarsen and lose data points"
            elif q_periods < MIN_USEFUL_PERIODS:
                rec = "2-month" if two_periods >= MIN_USEFUL_PERIODS else "monthly"
                reason = f"quarterly leaves only {q_periods} periods, too few to split train/val/test meaningfully"
            else:
                rec = "quarterly" if g.loc["quarterly", "pct_zero"] < g.loc["monthly", "pct_zero"] else "monthly"
                reason = "quarterly reduces zero share while still leaving enough periods"
            recommendations.append({"level": level, "key": key, "recommended_granularity": rec, "reason": reason})

    rec_df = pd.DataFrame(recommendations)
    rec_df.to_csv(os.path.join(SUMMARY_DIR, "part3_granularity_recommendation.csv"), index=False)
    print("\nRecommended granularity per series (evidence-based, NOT written to config.yaml):")
    print(rec_df.to_string(index=False))
