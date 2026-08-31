"""Tests whether coarser time granularity (2-month, quarterly, 6-month)
reduces the zero-inflation problem seen at monthly granularity, across the
58 pilot items. Investigation only — does not implement any change.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_granularity")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49

# Severity rank used only to detect "moved to a calmer class": Smooth is easiest to
# forecast, Lumpy hardest, Erratic/Intermittent in between. NoSale is excluded from
# the calmer-class comparison (a change of period count changes what counts as "no sale").
SEVERITY_RANK = {"Smooth": 0, "Intermittent": 1, "Erratic": 1, "Lumpy": 2}

GRANULARITIES = {
    "monthly": 1,
    "2-month": 2,
    "quarterly": 3,
    "6-month": 6,
}


def classify(adi, cv2):
    if adi is None:
        return "NoSale"
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        return "Smooth"
    if adi < ADI_THRESHOLD:
        return "Erratic"
    if cv2 < CV2_THRESHOLD:
        return "Intermittent"
    return "Lumpy"


def compute_adi_cv2(period_qty: np.ndarray):
    n = len(period_qty)
    nonzero = period_qty[period_qty > 0]
    if len(nonzero) == 0:
        return None, None
    adi = n / len(nonzero)
    mean_d = nonzero.mean()
    std_d = nonzero.std(ddof=1) if len(nonzero) > 1 else 0.0
    cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
    return adi, cv2


def bucket_series(monthly_qty: np.ndarray, months_per_bucket: int) -> np.ndarray:
    """Sums consecutive months into buckets. Drops a final partial bucket
    (fewer than months_per_bucket months) rather than padding with a guess."""
    n_complete_buckets = len(monthly_qty) // months_per_bucket
    usable = monthly_qty[: n_complete_buckets * months_per_bucket]
    return usable.reshape(n_complete_buckets, months_per_bucket).sum(axis=1)


if __name__ == "__main__":
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly.csv"))
    monthly = monthly[monthly["year_month"] != "2026-08"]  # exclude partial month
    item_codes = sorted(monthly["itemcode"].unique())
    n_months_available = monthly[monthly["itemcode"] == item_codes[0]]["year_month"].nunique()
    logger.info("58 items, %d complete months available (2024-01 through 2026-07)", n_months_available)
    logger.info("Part 2 established usable history begins 2024-01-01, and the 58 pilot items have zero rows "
                "before 2024 in cube_Sale_APD anyway, so the '2024 onward' and 'full usable history' scenarios "
                "asked for in Part 3 are IDENTICAL for this dataset — both are the same 31 months.")

    records = []
    class_change_records = []
    for item in item_codes:
        item_df = monthly[monthly["itemcode"] == item].sort_values("year_month")
        qty_monthly = item_df["qty"].to_numpy(dtype=float)
        adi_m, cv2_m = compute_adi_cv2(qty_monthly)
        cls_m = classify(adi_m, cv2_m)

        for gran_name, months_per_bucket in GRANULARITIES.items():
            bucketed = bucket_series(qty_monthly, months_per_bucket)
            n_periods = len(bucketed)
            pct_zero = (bucketed == 0).mean() * 100 if n_periods else None
            adi, cv2 = compute_adi_cv2(bucketed)
            cls = classify(adi, cv2)
            records.append({
                "itemcode": item, "granularity": gran_name, "n_periods": n_periods,
                "pct_zero_periods": round(pct_zero, 1) if pct_zero is not None else None,
                "adi": adi, "cv2": cv2, "classification": cls,
            })
            if gran_name != "monthly":
                rank_m = SEVERITY_RANK.get(cls_m)
                rank_this = SEVERITY_RANK.get(cls)
                moved_calmer = (rank_m is not None and rank_this is not None and rank_this < rank_m)
                class_change_records.append({
                    "itemcode": item, "granularity": gran_name,
                    "classification_monthly": cls_m, "classification_this_granularity": cls,
                    "moved_to_calmer_class": moved_calmer,
                })

    results_df = pd.DataFrame(records)
    results_df.to_csv(os.path.join(SUMMARY_DIR, "part3_granularity_results.csv"), index=False)

    # Summary: % zero periods and classification distribution per granularity
    summary = results_df.groupby("granularity").agg(
        mean_pct_zero=("pct_zero_periods", "mean"), mean_n_periods=("n_periods", "mean")
    ).reindex(list(GRANULARITIES.keys()))
    summary.to_csv(os.path.join(SUMMARY_DIR, "part3_granularity_summary.csv"))

    class_dist = results_df.groupby(["granularity", "classification"]).size().unstack(fill_value=0).reindex(list(GRANULARITIES.keys()))
    class_dist.to_csv(os.path.join(SUMMARY_DIR, "part3_classification_distribution.csv"))

    # Movement relative to monthly, per granularity
    change_df = pd.DataFrame(class_change_records)
    change_df.to_csv(os.path.join(SUMMARY_DIR, "part3_classification_change_vs_monthly.csv"), index=False)
    move_summary = change_df.groupby("granularity")["moved_to_calmer_class"].sum().reindex(["2-month", "quarterly", "6-month"])

    print("\n=== PART 3: GRANULARITY COMPARISON ===")
    print("\nMean %% zero periods and mean periods available, by granularity:")
    print(summary.to_string())
    print("\nClassification distribution by granularity:")
    print(class_dist.to_string())
    print("\nItems moved to a calmer classification vs monthly baseline:")
    print(move_summary.to_string())
    print(f"\nData points per item: monthly={n_months_available}, 2-month={n_months_available//2}, "
          f"quarterly={n_months_available//3}, 6-month={n_months_available//6}")
    print("(same under both the '2024 onward' and 'full usable history' scenarios per Part 2's finding)")
