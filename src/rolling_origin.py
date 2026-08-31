"""Rolling-origin backtest: evaluates every model at multiple successive
cutoff points instead of a single holdout, to check whether a model's win
is consistent or just a product of which 6 months happened to be held out.

Investigation only — does not replace or modify the original single-holdout
backtest outputs.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from models import get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("rolling_origin")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

MIN_TRAIN_MONTHS = 13  # smallest training window; ensures MA12 has more than just its own window
ORIGIN_STEP = 2  # months between successive origins


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_metrics(actual: np.ndarray, forecast: np.ndarray) -> dict:
    errors = forecast - actual
    return {
        "MAE": float(np.abs(errors).mean()),
        "RMSE": float(np.sqrt((errors ** 2).mean())),
        "Bias": float(errors.mean()),
    }


def get_origins(total_months: int, holdout: int) -> list:
    """Train sizes for each origin: from MIN_TRAIN_MONTHS up to (total_months - holdout),
    stepping by ORIGIN_STEP. The last origin always matches the original single-holdout split."""
    last_train = total_months - holdout
    origins = list(range(MIN_TRAIN_MONTHS, last_train + 1, ORIGIN_STEP))
    if origins[-1] != last_train:
        origins.append(last_train)
    return origins


def run_rolling_origin(monthly: pd.DataFrame, item_codes: list, holdout: int, ma_windows: list):
    models = get_models(ma_windows)
    results = []
    for item in item_codes:
        item_df = monthly[monthly["itemcode"] == item].sort_values("year_month")
        qty = item_df["qty"].to_numpy(dtype=float)
        n = len(qty)
        origins = get_origins(n, holdout)
        for origin_idx, train_size in enumerate(origins, start=1):
            train = qty[:train_size]
            test = qty[train_size:train_size + holdout]
            if len(test) < holdout:
                continue
            for model_name, model_fn in models.items():
                try:
                    forecast = np.clip(model_fn(train, holdout), 0, None)
                except Exception as e:
                    logger.warning("Model %s failed for %s at origin %d: %s", model_name, item, origin_idx, e)
                    continue
                metrics = compute_metrics(test, forecast)
                results.append({
                    "itemcode": item, "origin": origin_idx, "train_size": train_size,
                    "model": model_name, **metrics,
                })
    return pd.DataFrame(results), get_origins(monthly["itemcode"].value_counts().iloc[0] if len(monthly) else 0, holdout)


def summarize_stability(results_df: pd.DataFrame) -> pd.DataFrame:
    """Per item: winning model at each origin, and whether the winner is stable."""
    idx = results_df.groupby(["itemcode", "origin"])["MAE"].idxmin()
    winners = results_df.loc[idx, ["itemcode", "origin", "model", "MAE"]]
    per_item = winners.groupby("itemcode")["model"].agg(lambda s: s.nunique())
    stability = per_item.reset_index().rename(columns={"model": "n_distinct_winners"})
    n_origins_per_item = winners.groupby("itemcode")["origin"].nunique().reset_index().rename(columns={"origin": "n_origins"})
    stability = stability.merge(n_origins_per_item, on="itemcode")
    stability["stable_winner"] = stability["n_distinct_winners"] == 1
    most_frequent = winners.groupby("itemcode")["model"].agg(lambda s: s.value_counts().idxmax())
    stability = stability.merge(most_frequent.reset_index().rename(columns={"model": "most_frequent_winner"}), on="itemcode")
    return stability, winners


if __name__ == "__main__":
    config = load_config()
    holdout = config["backtest_holdout_months"]
    ma_windows = config["moving_average_windows"]

    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly.csv"))
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_pilot_sales_58items.csv"))
    max_date = pd.to_datetime(raw["createDate"]).max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    if max_date < month_end:
        latest_month = str(pd.Period(max_date, freq="M"))
        monthly = monthly[monthly["year_month"] != latest_month]
        logger.info("Excluded partial month %s (data ends %s, before month end %s)", latest_month, max_date.date(), month_end.date())

    item_codes = sorted(monthly["itemcode"].unique())
    total_months = monthly[monthly["itemcode"] == item_codes[0]]["year_month"].nunique()
    origins = get_origins(total_months, holdout)
    logger.info("Total months available: %d. Origins used: %d (train sizes %s), step=%d months, min_train=%d, holdout=%d",
                total_months, len(origins), origins, ORIGIN_STEP, MIN_TRAIN_MONTHS, holdout)
    logger.info("Reasoning: with %d months of history and a %d-month holdout, a full evaluation window per origin "
                "leaves at most (%d - %d)=%d usable origin points; stepping every %d months keeps origins from "
                "overlapping too heavily while still giving multiple independent-ish checks. The last origin "
                "matches the original single-holdout split for direct comparison.",
                total_months, holdout, total_months - holdout, MIN_TRAIN_MONTHS, len(origins), ORIGIN_STEP)

    results_df, _ = run_rolling_origin(monthly, item_codes, holdout, ma_windows)
    results_df.to_csv(os.path.join(SUMMARY_DIR, "partC_rolling_origin_results.csv"), index=False)

    stability_df, winners_df = summarize_stability(results_df)
    stability_df.to_csv(os.path.join(SUMMARY_DIR, "partC_stability_per_item.csv"), index=False)
    winners_df.to_csv(os.path.join(SUMMARY_DIR, "partC_winners_per_origin.csv"), index=False)

    n_stable = stability_df["stable_winner"].sum()
    n_total = len(stability_df)
    win_counts_aggregate = winners_df["model"].value_counts().rename_axis("model").reset_index(name="n_origin_wins")
    win_counts_aggregate.to_csv(os.path.join(SUMMARY_DIR, "partC_aggregate_win_counts.csv"), index=False)

    print("\n" + "=" * 70)
    print("PART C: ROLLING-ORIGIN SUMMARY")
    print("=" * 70)
    print(f"Origins used: {len(origins)} (train sizes: {origins})")
    print(f"\nItems with a STABLE winner (same model at every origin): {n_stable} of {n_total}")
    print(f"Items with an UNSTABLE winner (different model at different origins): {n_total - n_stable} of {n_total}")
    print("\nAggregate win counts across all origins (NOT the same as 'best' model — see stability above):")
    print(win_counts_aggregate.to_string(index=False))
    print("\nDistribution of n_distinct_winners per item (1 = fully stable):")
    print(stability_df["n_distinct_winners"].value_counts().sort_index())
