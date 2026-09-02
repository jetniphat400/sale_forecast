"""Rule-based selection task, Part 4: evaluates four model-selection
strategies on the untouched test set — rule-based (SBC/KH/PK), empirical
(validation-selected, as used throughout this project previously),
combination (equal-weight average of Naive/MA3/MA6/MA12/Croston/SBA), and
Naive alone as the floor.

Split: train=19, validation=6, test=6 months (identical to this project's
prior train/val/test work, for direct comparability). Rule-based
classification uses ONLY train+validation (25 months) — never the test set —
matching how empirical selection is also restricted to train+validation.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from feature_analysis import build_all_series, determine_complete_months
from models import get_extended_models, get_models
from rule_based_selection import select_models_for_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("evaluate_strategies")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

TRAIN_MONTHS, VAL_MONTHS, TEST_MONTHS = 19, 6, 6
MA_WINDOWS = [3, 6, 12]


def compute_metrics(actual: np.ndarray, forecast: np.ndarray, train_scale_series: np.ndarray) -> dict:
    errors = forecast - actual
    mae = float(np.abs(errors).mean())
    rmse = float(np.sqrt((errors ** 2).mean()))
    bias = float(errors.mean())
    naive_diffs = np.abs(np.diff(train_scale_series))
    scale = naive_diffs.mean()
    mase = mae / scale if scale > 0 else np.nan
    return {"MAE": mae, "RMSE": rmse, "Bias": bias, "MASE": mase}


def empirical_select(qty: np.ndarray, models: dict) -> str:
    train, val = qty[:TRAIN_MONTHS], qty[TRAIN_MONTHS:TRAIN_MONTHS + VAL_MONTHS]
    best_model, best_mae = None, np.inf
    for name, fn in models.items():
        try:
            fc = np.clip(fn(train, VAL_MONTHS), 0, None)
        except Exception:
            continue
        mae = np.abs(fc - val).mean()
        if mae < best_mae:
            best_mae, best_model = mae, name
    return best_model


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    series = build_all_series(monthly, scope)

    total_months = TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS
    base_models = get_models(MA_WINDOWS)
    ext_models = get_extended_models(MA_WINDOWS)

    results, selections, skipped = [], [], []
    for (level, key, cat), (qty, months) in series.items():
        if len(qty) != total_months:
            skipped.append((level, key, len(qty)))
            continue
        if qty.sum() == 0:
            skipped.append((level, key, "all-zero (NoSale)"))
            continue

        train_val = qty[:TRAIN_MONTHS + VAL_MONTHS]
        test = qty[TRAIN_MONTHS + VAL_MONTHS:]

        # --- Rule-based (classification on train+val only, no test leakage) ---
        rule_choice = select_models_for_series(train_val, months[:TRAIN_MONTHS + VAL_MONTHS])
        for rule_name in ["SBC_final", "KH_final", "PK_final"]:
            model_name = rule_choice.get(rule_name, "Naive")
            try:
                fc = np.clip(ext_models[model_name](train_val, TEST_MONTHS), 0, None)
            except Exception as e:
                logger.warning("%s/%s: rule model %s failed (%s) — falling back to Naive", level, key, model_name, e)
                model_name = "Naive"
                fc = np.clip(ext_models["Naive"](train_val, TEST_MONTHS), 0, None)
            metrics = compute_metrics(test, fc, train_val)
            strategy_label = {"SBC_final": "Rule-SBC", "KH_final": "Rule-KH", "PK_final": "Rule-PK"}[rule_name]
            results.append({"level": level, "key": key, "category": cat, "strategy": strategy_label,
                             "model_used": model_name, **metrics})

        # --- Empirical (validation-selected among the 6 base candidates) ---
        emp_model = empirical_select(qty, base_models)
        fc_emp = np.clip(base_models[emp_model](train_val, TEST_MONTHS), 0, None)
        metrics_emp = compute_metrics(test, fc_emp, train_val)
        results.append({"level": level, "key": key, "category": cat, "strategy": "Empirical",
                         "model_used": emp_model, **metrics_emp})

        # --- Combination (equal-weight average of the 6 base candidates) ---
        fc_combo = np.mean([np.clip(fn(train_val, TEST_MONTHS), 0, None) for fn in base_models.values()], axis=0)
        metrics_combo = compute_metrics(test, fc_combo, train_val)
        results.append({"level": level, "key": key, "category": cat, "strategy": "Combination",
                         "model_used": "avg(Naive,MA3,MA6,MA12,Croston,SBA)", **metrics_combo})

        # --- Naive floor ---
        fc_naive = np.clip(base_models["Naive"](train_val, TEST_MONTHS), 0, None)
        metrics_naive = compute_metrics(test, fc_naive, train_val)
        results.append({"level": level, "key": key, "category": cat, "strategy": "Naive",
                         "model_used": "Naive", **metrics_naive})

        selections.append({
            "level": level, "key": key, "SBC_model": rule_choice.get("SBC_final"),
            "KH_model": rule_choice.get("KH_final"), "PK_model": rule_choice.get("PK_final"),
            "empirical_model": emp_model, "classification_on_train_val": rule_choice.get("classification"),
        })

    results_df = pd.DataFrame(results)
    results_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part4_test_results_per_series.csv"), index=False)
    selections_df = pd.DataFrame(selections)
    selections_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part4_model_selections.csv"), index=False)

    logger.info("Evaluated %d series (%d skipped: %s)", len(selections), len(skipped), skipped[:10])

    # Mean metrics per level x strategy
    summary = results_df.groupby(["level", "strategy"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    summary.to_csv(os.path.join(SUMMARY_DIR, "rule_part4_summary_by_level_strategy.csv"), index=False)

    print("\n" + "=" * 90)
    print("PART 4: STRATEGY COMPARISON ON THE TEST SET (mean MAE/RMSE/Bias/MASE)")
    print("=" * 90)
    for level in ["Category", "Type", "Item"]:
        sub = summary[summary["level"] == level].sort_values("MASE")
        print(f"\n--- {level} level ---")
        print(sub.to_string(index=False))

    # MAE-best vs Bias-best (|Bias| smallest) strategy, per series
    print("\n" + "=" * 90)
    print("MAE-BEST vs BIAS-BEST STRATEGY DISAGREEMENT (per series)")
    print("=" * 90)
    disagreements = []
    for (level, key), g in results_df.groupby(["level", "key"]):
        mae_best = g.loc[g["MAE"].idxmin(), "strategy"]
        g = g.copy()
        g["abs_bias"] = g["Bias"].abs()
        bias_best = g.loc[g["abs_bias"].idxmin(), "strategy"]
        disagreements.append({"level": level, "key": key, "MAE_best_strategy": mae_best,
                               "Bias_best_strategy": bias_best, "disagree": mae_best != bias_best})
    disagree_df = pd.DataFrame(disagreements)
    disagree_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part4_mae_vs_bias_best.csv"), index=False)
    for level in ["Category", "Type", "Item"]:
        sub = disagree_df[disagree_df["level"] == level]
        n_dis = sub["disagree"].sum()
        print(f"{level}: {n_dis} of {len(sub)} series disagree ({100*n_dis/len(sub):.1f}%)")

    print("\nWhere MAE-best and Bias-best disagree: the MAE-best strategy minimises average absolute error but")
    print("may carry a persistent directional bias (stockouts if under-forecasting, excess stock if")
    print("over-forecasting); the Bias-best strategy minimises that directional risk but usually has higher")
    print("average absolute error. See rule_part4_mae_vs_bias_best.csv for which strategy wins each way, per series.")

    print("\nFull detail: output/summary/rule_part4_test_results_per_series.csv, "
          "rule_part4_model_selections.csv, rule_part4_summary_by_level_strategy.csv")
