"""Part 4: backtests Naive, MA3/MA6/MA12, Croston and SBA at Category and
Type level, using monthly granularity (Part 3 found quarterly/2-month give
no material benefit at 9 of 10 series — see part3_granularity_recommendation.csv;
using monthly uniformly keeps Category and Type results directly comparable).

Two evaluation methodologies, matching the item-level backtest exactly for
comparability (src/rolling_origin.py, src/train_val_test.py):
  1. Rolling-origin: MIN_TRAIN_MONTHS=13, ORIGIN_STEP=2, holdout=6 months.
  2. Train/validation/test: 19 / 6 / 6 months, select on validation only,
     measure once on test, report the validation-to-test gap.

Reports MAE, RMSE, Bias for every combination. Presents results only —
selects nothing into config.yaml.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from aggregate_levels import determine_complete_months
from models import get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backtest_aggregate")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

MA_WINDOWS = [3, 6, 12]
HOLDOUT = 6
MIN_TRAIN_MONTHS = 13
ORIGIN_STEP = 2
TRAIN_MONTHS = 19
VAL_MONTHS = 6
TEST_MONTHS = 6


def compute_metrics(actual: np.ndarray, forecast: np.ndarray) -> dict:
    errors = forecast - actual
    return {"MAE": float(np.abs(errors).mean()), "RMSE": float(np.sqrt((errors ** 2).mean())), "Bias": float(errors.mean())}


def get_origins(total_months: int, holdout: int) -> list:
    last_train = total_months - holdout
    origins = list(range(MIN_TRAIN_MONTHS, last_train + 1, ORIGIN_STEP))
    if origins[-1] != last_train:
        origins.append(last_train)
    return origins


def build_level_series(monthly: pd.DataFrame) -> dict:
    """Returns {(level, key, category): np.ndarray} for Category and Type level series."""
    series = {}
    for cat, g in monthly.groupby("category"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        series[("Category", cat, cat)] = agg["qty"].to_numpy(dtype=float)
        series[("Category", cat, cat, "months")] = agg["year_month"].astype(str).tolist()
    for (cat, typ), g in monthly.groupby(["category", "type"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        series[("Type", typ, cat)] = agg["qty"].to_numpy(dtype=float)
        series[("Type", typ, cat, "months")] = agg["year_month"].astype(str).tolist()
    return series


def run_rolling_origin(series: dict, models: dict) -> pd.DataFrame:
    results = []
    keys = [k for k in series if len(k) == 3]
    for level, key, cat in keys:
        qty = series[(level, key, cat)]
        n = len(qty)
        origins = get_origins(n, HOLDOUT)
        for origin_idx, train_size in enumerate(origins, start=1):
            train = qty[:train_size]
            test = qty[train_size:train_size + HOLDOUT]
            if len(test) < HOLDOUT:
                continue
            for model_name, model_fn in models.items():
                try:
                    forecast = np.clip(model_fn(train, HOLDOUT), 0, None)
                except Exception as e:
                    logger.warning("Model %s failed for %s/%s at origin %d: %s", model_name, level, key, origin_idx, e)
                    continue
                metrics = compute_metrics(test, forecast)
                results.append({"level": level, "key": key, "category": cat, "origin": origin_idx, "train_size": train_size, "model": model_name, **metrics})
    return pd.DataFrame(results)


def summarize_stability(results_df: pd.DataFrame):
    idx = results_df.groupby(["level", "key", "origin"])["MAE"].idxmin()
    winners = results_df.loc[idx, ["level", "key", "origin", "model", "MAE"]]
    per_series = winners.groupby(["level", "key"])["model"].agg(lambda s: s.nunique())
    stability = per_series.reset_index().rename(columns={"model": "n_distinct_winners"})
    most_frequent = winners.groupby(["level", "key"])["model"].agg(lambda s: s.value_counts().idxmax())
    stability = stability.merge(most_frequent.reset_index().rename(columns={"model": "most_frequent_winner"}), on=["level", "key"])
    stability["stable_winner"] = stability["n_distinct_winners"] == 1
    return stability, winners


def run_train_val_test(series: dict, models: dict):
    val_records, test_records = [], []
    keys = [k for k in series if len(k) == 3]
    for level, key, cat in keys:
        qty = series[(level, key, cat)]
        n = len(qty)
        if n != TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS:
            raise ValueError(f"{level}/{key} has {n} months, expected {TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS}")
        train = qty[:TRAIN_MONTHS]
        val = qty[TRAIN_MONTHS:TRAIN_MONTHS + VAL_MONTHS]
        for model_name, model_fn in models.items():
            fc_val = np.clip(model_fn(train, VAL_MONTHS), 0, None)
            m = compute_metrics(val, fc_val)
            val_records.append({"level": level, "key": key, "category": cat, "model": model_name, **m})
    val_df = pd.DataFrame(val_records)

    selection = []
    for (level, key), grp in val_df.groupby(["level", "key"]):
        best_mae_row = grp.loc[grp["MAE"].idxmin()]
        grp2 = grp.copy()
        grp2["abs_Bias"] = grp2["Bias"].abs()
        best_bias_row = grp2.loc[grp2["abs_Bias"].idxmin()]
        selection.append({
            "level": level, "key": key,
            "selected_model_by_MAE": best_mae_row["model"], "val_MAE_of_selected": best_mae_row["MAE"], "val_Bias_of_selected": best_mae_row["Bias"],
            "best_bias_model": best_bias_row["model"], "best_bias_value": best_bias_row["Bias"],
            "disagree": best_mae_row["model"] != best_bias_row["model"],
        })
    selection_df = pd.DataFrame(selection)

    for level, key, cat in keys:
        qty = series[(level, key, cat)]
        train_val = qty[:TRAIN_MONTHS + VAL_MONTHS]
        test = qty[TRAIN_MONTHS + VAL_MONTHS:]
        selected_model = selection_df.loc[(selection_df["level"] == level) & (selection_df["key"] == key), "selected_model_by_MAE"].iloc[0]
        fc_test = np.clip(models[selected_model](train_val, TEST_MONTHS), 0, None)
        m = compute_metrics(test, fc_test)
        test_records.append({"level": level, "key": key, "category": cat, "model": selected_model, **m})
    test_df = pd.DataFrame(test_records)
    return val_df, selection_df, test_df


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    total_months = monthly["year_month"].nunique()
    models = get_models(MA_WINDOWS)
    series = build_level_series(monthly)

    origins = get_origins(total_months, HOLDOUT)
    logger.info("Total months: %d. Rolling-origin: %d origins (train sizes %s), step=%d, min_train=%d, holdout=%d",
                total_months, len(origins), origins, ORIGIN_STEP, MIN_TRAIN_MONTHS, HOLDOUT)
    logger.info("Reasoning: identical settings to the item-level rolling-origin backtest, so origin counts "
                "and train sizes are directly comparable across levels.")

    ro_results = run_rolling_origin(series, models)
    ro_results.to_csv(os.path.join(SUMMARY_DIR, "part4_rolling_origin_results.csv"), index=False)
    stability_df, winners_df = summarize_stability(ro_results)
    stability_df.to_csv(os.path.join(SUMMARY_DIR, "part4_rolling_origin_stability.csv"), index=False)
    winners_df.to_csv(os.path.join(SUMMARY_DIR, "part4_rolling_origin_winners_per_origin.csv"), index=False)

    if total_months != TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS:
        raise ValueError(f"Split sizes ({TRAIN_MONTHS}+{VAL_MONTHS}+{TEST_MONTHS}) don't match available months ({total_months})")
    val_df, selection_df, test_df = run_train_val_test(series, models)
    val_df.to_csv(os.path.join(SUMMARY_DIR, "part4_validation_results.csv"), index=False)
    selection_df.to_csv(os.path.join(SUMMARY_DIR, "part4_model_selection.csv"), index=False)
    test_df.to_csv(os.path.join(SUMMARY_DIR, "part4_test_results.csv"), index=False)

    merged = selection_df[["level", "key", "selected_model_by_MAE", "val_MAE_of_selected"]].merge(
        test_df[["level", "key", "MAE"]].rename(columns={"MAE": "test_MAE"}), on=["level", "key"]
    )
    merged["gap"] = merged["test_MAE"] - merged["val_MAE_of_selected"]
    merged["gap_pct"] = (merged["gap"] / merged["val_MAE_of_selected"] * 100).round(1)
    merged.to_csv(os.path.join(SUMMARY_DIR, "part4_val_test_gap.csv"), index=False)

    print("\n" + "=" * 78)
    print("PART 4: BACKTEST — Category and Type level (monthly granularity)")
    print("=" * 78)
    print(f"\nRolling-origin: {len(origins)} origins used (train sizes {origins}); step={ORIGIN_STEP} months, "
          f"min_train={MIN_TRAIN_MONTHS}, holdout={HOLDOUT} — identical settings to the item-level backtest.")
    print("\nWinner stability across origins (per Category/Type series):")
    print(stability_df.sort_values(["level", "key"]).to_string(index=False))
    n_stable = stability_df["stable_winner"].sum()
    print(f"\nStable winner: {n_stable} of {len(stability_df)} series ({100*n_stable/len(stability_df):.0f}%)")

    print(f"\nTrain/Val/Test split: {TRAIN_MONTHS}/{VAL_MONTHS}/{TEST_MONTHS} months (identical to item-level).")
    print("\nModel selection (validation) vs. Bias-best, and disagreement:")
    print(selection_df.sort_values(["level", "key"]).to_string(index=False))
    n_disagree = selection_df["disagree"].sum()
    print(f"\nMAE-best and Bias-best disagree for {n_disagree} of {len(selection_df)} series")

    print("\nValidation-to-test gap per series:")
    print(merged.sort_values(["level", "key"]).to_string(index=False))
    mean_gap_pct = merged["gap_pct"].mean()
    print(f"\nMean gap: {merged['gap'].mean():.2f} ({mean_gap_pct:+.1f}% relative to validation MAE)")

    print("\nFull rolling-origin results (MAE/RMSE/Bias per level/key/model, averaged across origins):")
    ro_avg = ro_results.groupby(["level", "key", "model"], as_index=False)[["MAE", "RMSE", "Bias"]].mean()
    print(ro_avg.sort_values(["level", "key", "MAE"]).to_string(index=False))
