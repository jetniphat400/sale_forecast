"""Three-way train/validation/test split: choose the winning model per item
using validation only, then measure the chosen model on test (touched only
once, for final measurement). Reports the validation-to-test performance gap
as the estimate of how optimistic the single-holdout backtest was.

Selection uses both MAE and Bias — reports where they disagree.
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
logger = logging.getLogger("train_val_test")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

TRAIN_MONTHS = 19
VAL_MONTHS = 6
TEST_MONTHS = 6  # TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS must equal the total months available (31)


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


def run_split(monthly: pd.DataFrame, item_codes: list, ma_windows: list):
    models = get_models(ma_windows)
    val_records = []
    test_records = []

    for item in item_codes:
        item_df = monthly[monthly["itemcode"] == item].sort_values("year_month")
        qty = item_df["qty"].to_numpy(dtype=float)
        n = len(qty)
        if n != TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS:
            raise ValueError(f"Item {item} has {n} months, expected exactly {TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS}")

        train = qty[:TRAIN_MONTHS]
        val = qty[TRAIN_MONTHS:TRAIN_MONTHS + VAL_MONTHS]
        train_val = qty[:TRAIN_MONTHS + VAL_MONTHS]
        test = qty[TRAIN_MONTHS + VAL_MONTHS:]

        for model_name, model_fn in models.items():
            fc_val = np.clip(model_fn(train, VAL_MONTHS), 0, None)
            m = compute_metrics(val, fc_val)
            val_records.append({"itemcode": item, "model": model_name, **m})

    val_df = pd.DataFrame(val_records)

    # Select per item: lowest MAE, and separately lowest |Bias|, report where they disagree
    selection = []
    for item, grp in val_df.groupby("itemcode"):
        best_mae_row = grp.loc[grp["MAE"].idxmin()]
        grp = grp.copy()
        grp["abs_Bias"] = grp["Bias"].abs()
        best_bias_row = grp.loc[grp["abs_Bias"].idxmin()]
        selection.append({
            "itemcode": item,
            "selected_model_by_MAE": best_mae_row["model"], "val_MAE_of_selected": best_mae_row["MAE"], "val_Bias_of_selected": best_mae_row["Bias"],
            "best_bias_model": best_bias_row["model"], "best_bias_value": best_bias_row["Bias"],
            "disagree": best_mae_row["model"] != best_bias_row["model"],
        })
    selection_df = pd.DataFrame(selection)

    # Refit the MAE-selected model on train+val, forecast test, score
    for item in item_codes:
        item_df = monthly[monthly["itemcode"] == item].sort_values("year_month")
        qty = item_df["qty"].to_numpy(dtype=float)
        train_val = qty[:TRAIN_MONTHS + VAL_MONTHS]
        test = qty[TRAIN_MONTHS + VAL_MONTHS:]
        selected_model = selection_df.loc[selection_df["itemcode"] == item, "selected_model_by_MAE"].iloc[0]
        fc_test = np.clip(models[selected_model](train_val, TEST_MONTHS), 0, None)
        m = compute_metrics(test, fc_test)
        test_records.append({"itemcode": item, "model": selected_model, **m})

    test_df = pd.DataFrame(test_records)
    return val_df, selection_df, test_df


if __name__ == "__main__":
    config = load_config()
    ma_windows = config["moving_average_windows"]

    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly.csv"))
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_pilot_sales_58items.csv"))
    max_date = pd.to_datetime(raw["createDate"]).max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    if max_date < month_end:
        latest_month = str(pd.Period(max_date, freq="M"))
        monthly = monthly[monthly["year_month"] != latest_month]

    item_codes = sorted(monthly["itemcode"].unique())
    total_months = monthly[monthly["itemcode"] == item_codes[0]]["year_month"].nunique()
    logger.info("Total months: %d. Split: train=%d, validation=%d, test=%d",
                total_months, TRAIN_MONTHS, VAL_MONTHS, TEST_MONTHS)
    if total_months != TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS:
        raise ValueError(f"Split sizes ({TRAIN_MONTHS}+{VAL_MONTHS}+{TEST_MONTHS}) don't match available months ({total_months})")

    val_df, selection_df, test_df = run_split(monthly, item_codes, ma_windows)
    val_df.to_csv(os.path.join(SUMMARY_DIR, "partD_validation_results.csv"), index=False)
    selection_df.to_csv(os.path.join(SUMMARY_DIR, "partD_model_selection.csv"), index=False)
    test_df.to_csv(os.path.join(SUMMARY_DIR, "partD_test_results.csv"), index=False)

    n_disagree = selection_df["disagree"].sum()
    logger.info("MAE-best and Bias-best model disagree for %d of %d items", n_disagree, len(selection_df))

    # Validation-to-test gap: for each item, compare val MAE of the selected model to its test MAE
    merged = selection_df[["itemcode", "selected_model_by_MAE", "val_MAE_of_selected"]].merge(
        test_df[["itemcode", "MAE"]].rename(columns={"MAE": "test_MAE"}), on="itemcode"
    )
    merged["gap"] = merged["test_MAE"] - merged["val_MAE_of_selected"]
    merged.to_csv(os.path.join(SUMMARY_DIR, "partD_val_test_gap.csv"), index=False)

    mean_val_mae = merged["val_MAE_of_selected"].mean()
    mean_test_mae = merged["test_MAE"].mean()
    mean_gap = merged["gap"].mean()

    print("\n" + "=" * 70)
    print("PART D: TRAIN/VALIDATION/TEST SUMMARY")
    print("=" * 70)
    print(f"Split: train={TRAIN_MONTHS} months, validation={VAL_MONTHS} months, test={TEST_MONTHS} months")
    print(f"\nMean validation MAE (across 58 items, selected models): {mean_val_mae:.2f}")
    print(f"Mean test MAE (same selected models, unseen data): {mean_test_mae:.2f}")
    print(f"Mean gap (test - validation): {mean_gap:.2f} ({'test worse' if mean_gap > 0 else 'test better'})")
    print(f"\nMAE-best and Bias-best model disagree for {n_disagree} of {len(selection_df)} items:")
    print(selection_df[selection_df["disagree"]].to_string(index=False))
