"""Backtests Naive, Moving Average, Croston and SBA against a holdout for
every pilot item.

Metrics are MAE, RMSE and Bias — not MAPE, since zero-demand months make it
undefined (see STATUS.md / config.yaml). Presents results only; does not
select or write a final model choice anywhere.
"""
import logging
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from models import get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backtest")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def determine_complete_months(monthly_df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    """Drops the latest month from the monthly frame if it is not a complete
    calendar month in the raw data (its max date is not that month's last day).
    Determined from the actual data, not assumed from the wall clock.
    """
    max_date = pd.to_datetime(raw_df["createDate"]).max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_month = pd.Period(max_date, freq="M")
    if max_date < month_end:
        logger.info(
            "Latest month %s is partial (data ends %s, month ends %s) — excluded from backtesting",
            latest_month, max_date.date(), month_end.date(),
        )
        monthly_df = monthly_df[monthly_df["year_month"] != str(latest_month)]
    else:
        logger.info("Latest month %s is complete (data ends on the month's last day) — kept", latest_month)
    return monthly_df


def classify_demand(qty_series: np.ndarray):
    """Classify demand pattern via ADI and CV-squared (Syntetos-Boylan thresholds),
    using the full available series for the item."""
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


def compute_metrics(actual: np.ndarray, forecast: np.ndarray) -> dict:
    errors = forecast - actual
    return {
        "MAE": float(np.abs(errors).mean()),
        "RMSE": float(np.sqrt((errors ** 2).mean())),
        "Bias": float(errors.mean()),
    }


def run_backtest(monthly_df: pd.DataFrame, item_codes: list, holdout_months: int, ma_windows: list):
    models = get_models(ma_windows)
    results = []
    dropped_items = []

    for item in item_codes:
        item_df = monthly_df[monthly_df["itemcode"] == item].sort_values("year_month")
        qty_series = item_df["qty"].to_numpy(dtype=float)
        n = len(qty_series)
        if n <= holdout_months:
            dropped_items.append((item, f"only {n} months available, need more than {holdout_months}"))
            continue

        train = qty_series[: n - holdout_months]
        test = qty_series[n - holdout_months:]
        cls, adi, cv2 = classify_demand(qty_series)

        for model_name, model_fn in models.items():
            try:
                forecast = model_fn(train, holdout_months)
            except Exception as e:
                logger.warning("Model %s failed for item %s: %s — skipped, not silently zero-filled", model_name, item, e)
                continue

            n_negative = int((forecast < 0).sum())
            if n_negative > 0:
                logger.warning("Model %s produced %d negative forecast values for item %s — clipped to 0 (forecasts must never be negative)", model_name, n_negative, item)
                forecast = np.clip(forecast, a_min=0, a_max=None)

            metrics = compute_metrics(test, forecast)
            results.append({
                "itemcode": item, "model": model_name, "classification": cls,
                "adi": adi, "cv2": cv2, **metrics,
            })

    logger.info(
        "Backtest complete: %d item-model rows produced, %d items dropped (%s)",
        len(results), len(dropped_items), dropped_items,
    )
    return pd.DataFrame(results), dropped_items


def summarize_winners(results_df: pd.DataFrame) -> pd.DataFrame:
    """One row per item: the model with the lowest MAE for that item."""
    idx = results_df.groupby("itemcode")["MAE"].idxmin()
    return results_df.loc[idx, ["itemcode", "classification", "model", "MAE", "RMSE", "Bias"]].rename(
        columns={"model": "winning_model"}
    )


def summarize_by_classification(results_df: pd.DataFrame) -> pd.DataFrame:
    return results_df.groupby(["classification", "model"], as_index=False).agg(
        n_items=("itemcode", "nunique"), mean_MAE=("MAE", "mean"), mean_RMSE=("RMSE", "mean"), mean_Bias=("Bias", "mean")
    )


def summarize_win_counts(winners_df: pd.DataFrame) -> pd.DataFrame:
    return winners_df["winning_model"].value_counts().rename_axis("model").reset_index(name="n_items_won")


def summarize_beats_naive(results_df: pd.DataFrame) -> pd.DataFrame:
    naive = results_df[results_df["model"] == "Naive"][["itemcode", "MAE"]].rename(columns={"MAE": "naive_MAE"})
    merged = results_df.merge(naive, on="itemcode")
    merged["beats_naive"] = merged["MAE"] < merged["naive_MAE"]
    summary = merged[merged["model"] != "Naive"].groupby("model", as_index=False).agg(
        n_items=("itemcode", "nunique"), n_beats_naive=("beats_naive", "sum")
    )
    summary["pct_beats_naive"] = (summary["n_beats_naive"] / summary["n_items"] * 100).round(1)
    return summary


def plot_pilot_codes(monthly_df: pd.DataFrame, item_codes: list, holdout_months: int, ma_windows: list):
    models = get_models(ma_windows)
    for item in item_codes:
        item_df = monthly_df[monthly_df["itemcode"] == item].sort_values("year_month")
        if item_df.empty:
            logger.warning("Pilot code %s not found in monthly data (excluded item?) — skipping plot", item)
            continue
        qty_series = item_df["qty"].to_numpy(dtype=float)
        months = item_df["year_month"].astype(str).tolist()
        n = len(qty_series)
        if n <= holdout_months:
            logger.warning("Pilot code %s has only %d months, cannot backtest with holdout=%d — skipping plot", item, n, holdout_months)
            continue
        train = qty_series[: n - holdout_months]
        test = qty_series[n - holdout_months:]
        test_months = months[n - holdout_months:]

        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.plot(months, qty_series, label="Actual", color="black", marker="o", markersize=3)
        for model_name, model_fn in models.items():
            forecast = np.clip(model_fn(train, holdout_months), 0, None)
            ax.plot(test_months, forecast, label=model_name, linestyle="--", marker="x", markersize=4)
        ax.set_title(f"Forecast vs Actual — {item}")
        ax.set_ylabel("Monthly qty")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=8)
        fig.tight_layout()
        safe_name = item.replace("/", "_")
        fig.savefig(os.path.join(CHARTS_DIR, f"forecast_vs_actual_{safe_name}.png"))
        plt.close(fig)
        logger.info("Saved chart for %s", item)


if __name__ == "__main__":
    config = load_config()
    holdout_months = config["backtest_holdout_months"]
    ma_windows = config["moving_average_windows"]
    pilot_item_codes = config["pilot_item_codes"]

    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly.csv"))
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_pilot_sales_58items.csv"))
    monthly = determine_complete_months(monthly, raw)
    item_codes = sorted(monthly["itemcode"].unique())
    logger.info("Backtesting %d items with a %d-month holdout, MA windows=%s", len(item_codes), holdout_months, ma_windows)

    results_df, dropped_items = run_backtest(monthly, item_codes, holdout_months, ma_windows)
    results_df.to_csv(os.path.join(SUMMARY_DIR, "backtest_results_per_item_model.csv"), index=False)

    winners_df = summarize_winners(results_df)
    winners_df.to_csv(os.path.join(SUMMARY_DIR, "backtest_winning_model_per_item.csv"), index=False)

    by_class_df = summarize_by_classification(results_df)
    by_class_df.to_csv(os.path.join(SUMMARY_DIR, "backtest_summary_by_classification.csv"), index=False)

    win_counts_df = summarize_win_counts(winners_df)
    win_counts_df.to_csv(os.path.join(SUMMARY_DIR, "backtest_win_counts.csv"), index=False)

    beats_naive_df = summarize_beats_naive(results_df)
    beats_naive_df.to_csv(os.path.join(SUMMARY_DIR, "backtest_beats_naive.csv"), index=False)

    plot_pilot_codes(monthly, pilot_item_codes, holdout_months, ma_windows)

    pilot_results = results_df[results_df["itemcode"].isin(pilot_item_codes)]
    pilot_results.to_csv(os.path.join(SUMMARY_DIR, "backtest_pilot_codes_detail.csv"), index=False)

    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)
    print(f"Items backtested: {len(item_codes) - len(dropped_items)} of {len(item_codes)}")
    if dropped_items:
        print(f"Items dropped (insufficient history): {dropped_items}")
    print("\nWin counts (lowest MAE per item):")
    print(win_counts_df.to_string(index=False))
    print("\nHow often each model beats Naive:")
    print(beats_naive_df.to_string(index=False))
    print("\nSummary by demand classification:")
    print(by_class_df.sort_values(["classification", "mean_MAE"]).to_string(index=False))
    print("\nPilot codes detail:")
    print(pilot_results.sort_values(["itemcode", "MAE"]).to_string(index=False))
