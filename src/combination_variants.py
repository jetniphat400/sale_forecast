"""Task (2026-09-01), Part 1: tests combination-forecast VARIANTS against the
current arithmetic-mean combination, at Category, Type and Item level.

Motivation (given by the user): the combination-forecasting literature
reports that median, trimmed-mean and winsorized-mean combinations can
outperform the arithmetic mean because they resist outliers, and a median
combination of four simple models placed 6th in the M4 competition
(Makridakis, Spyros, Spiliotis & Assimakopoulos, "The M4 Competition: 100,000
time series and 61 forecasting methods", Int. J. Forecasting 36(1), 2020 —
Table 5 lists "Simple median (4 methods)" among the top submissions). Our
demand series carry frequent large-order spikes (STATUS.md, investigate_spikes.py:
62 spike months across 26 of 58 pilot items), so an outlier-resistant
combination is a reasonable hypothesis to test.

Reuses the EXISTING infrastructure exactly, not rebuilt:
  - src/feature_analysis.py: build_all_series() / determine_complete_months()
    for the same 128-item, Category/Type/Item series construction.
  - src/models.py: get_models() for the same 6 base candidates
    (Naive, MA3, MA6, MA12, Croston, SBA).
  - src/evaluate_strategies.py: identical TRAIN=19 / VAL=6 / TEST=6 month
    split and the same compute_metrics() (MAE, RMSE, Bias, MASE — MASE scaled
    by the mean absolute first difference of the train+val series, exactly
    matching the existing convention).

Combination variants tested, all built from the SAME 6 base forecasts per
series/period (no new models introduced):
  1. Mean       - arithmetic mean of all 6 forecasts (the CURRENT approach,
                  models.combination_forecast).
  2. Median      - median of all 6 forecasts.
  3. TrimmedMean - drops the single highest and single lowest forecast, means
                  the remaining 4 (a "trim 1 of 6" trimmed mean).
  4. RobustSubsetMedian - median of a smaller SUBSET: {Naive, MA3, MA6, MA12}
                  (the 4 non-intermittent-specific models), explicitly
                  EXCLUDING Croston and SBA. Reason, evidenced from this
                  project's own prior work (STATUS.md, investigate_spikes.py
                  Task 5): Croston/SBA showed erratic, slow-adapting behaviour
                  on this dataset's Intermittent items — 16 of 18 Intermittent
                  items had Croston forecasting a positive constant (up to
                  470.8) driven by one old large-demand event, while Naive/MA
                  correctly tracked the recent zero-run; Bias analysis also
                  found Croston/SBA over-forecast Intermittent demand by +25
                  to +27 units/month vs. Naive/MA's near-zero bias. Naive and
                  the three MA windows are the four models with no such
                  documented instability on this data, making them the
                  better-evidenced "robust subset" choice for THIS dataset
                  (not a generic literature recommendation — stated as our
                  own reasoned choice, per the module docstring convention
                  used throughout this project).

For every series and both evaluation stages (train-19 -> val-6, and
train+val-25 -> test-6), computes all 4 variants' MAE/RMSE/Bias/MASE, the
validation-to-test gap, and a paired-t significance check of every variant
against the Mean (current) baseline, at each level — matching the exact
paired-t methodology already used in src/strategy_gap_and_bias_report.py.

Presents results only. No model choice is written to config.yaml.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from feature_analysis import build_all_series, determine_complete_months
from models import get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("combination_variants")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

MA_WINDOWS = [3, 6, 12]
TRAIN_MONTHS, VAL_MONTHS, TEST_MONTHS = 19, 6, 6
ROBUST_SUBSET = ["Naive", "MA3", "MA6", "MA12"]

VARIANTS = ["Mean", "Median", "TrimmedMean", "RobustSubsetMedian"]


def compute_metrics(actual: np.ndarray, forecast: np.ndarray, train_scale_series: np.ndarray) -> dict:
    """Identical to evaluate_strategies.compute_metrics: MAE, RMSE, Bias, and
    MASE scaled by the mean absolute first difference of the fitting series."""
    errors = forecast - actual
    mae = float(np.abs(errors).mean())
    rmse = float(np.sqrt((errors ** 2).mean()))
    bias = float(errors.mean())
    naive_diffs = np.abs(np.diff(train_scale_series))
    scale = naive_diffs.mean()
    mase = mae / scale if scale > 0 else np.nan
    return {"MAE": mae, "RMSE": rmse, "Bias": bias, "MASE": mase}


def base_forecasts(train: np.ndarray, horizon: int, models: dict) -> dict:
    """Returns {model_name: forecast_array}, skipping any model that fails
    (identical fallback behaviour to models.combination_forecast)."""
    out = {}
    for name, fn in models.items():
        try:
            out[name] = np.clip(fn(train, horizon), 0, None)
        except Exception as e:
            logger.warning("Model %s failed (%s) — excluded from this combination", name, e)
    return out


def combine(forecasts: dict, variant: str) -> np.ndarray:
    if variant == "Mean":
        stacked = np.array(list(forecasts.values()))
        return stacked.mean(axis=0)
    if variant == "Median":
        stacked = np.array(list(forecasts.values()))
        return np.median(stacked, axis=0)
    if variant == "TrimmedMean":
        stacked = np.array(list(forecasts.values()))  # shape (n_models, horizon)
        sorted_stack = np.sort(stacked, axis=0)
        if sorted_stack.shape[0] <= 2:
            return sorted_stack.mean(axis=0)  # too few models to trim 1 each side — fall back to mean
        trimmed = sorted_stack[1:-1]  # drop lowest and highest per period
        return trimmed.mean(axis=0)
    if variant == "RobustSubsetMedian":
        subset = {k: v for k, v in forecasts.items() if k in ROBUST_SUBSET}
        if not subset:
            raise ValueError("RobustSubsetMedian: none of the robust-subset models produced a forecast")
        stacked = np.array(list(subset.values()))
        return np.median(stacked, axis=0)
    raise ValueError(f"Unknown variant {variant}")


def run_stage(series: dict, models: dict, train_len: int, horizon: int, stage_name: str) -> pd.DataFrame:
    rows = []
    for (level, key, cat), (qty, months) in series.items():
        total_needed = TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS
        if len(qty) != total_needed or qty.sum() == 0:
            continue
        train = qty[:train_len]
        actual = qty[train_len:train_len + horizon]
        forecasts = base_forecasts(train, horizon, models)
        for variant in VARIANTS:
            fc = np.clip(combine(forecasts, variant), 0, None)
            metrics = compute_metrics(actual, fc, train)
            rows.append({"stage": stage_name, "level": level, "key": key, "category": cat,
                         "variant": variant, **metrics})
    return pd.DataFrame(rows)


def paired_significance(test_df: pd.DataFrame, baseline: str = "Mean") -> pd.DataFrame:
    """Paired t-test of each variant's per-series MAE against the baseline
    (Mean, the current approach), per level — identical methodology to
    strategy_gap_and_bias_report.py's winner-margin check: paired because
    both variants are scored on the exact same series, and their errors are
    likely correlated, so an unpaired spread would overstate uncertainty."""
    rows = []
    for level in test_df["level"].unique():
        base = test_df[(test_df["level"] == level) & (test_df["variant"] == baseline)][["key", "MAE"]]
        for variant in VARIANTS:
            if variant == baseline:
                continue
            other = test_df[(test_df["level"] == level) & (test_df["variant"] == variant)][["key", "MAE"]]
            paired = base.merge(other, on="key", suffixes=("_base", "_other"))
            n = len(paired)
            if n < 2:
                rows.append({"level": level, "variant": variant, "baseline": baseline, "n_paired": n,
                             "mean_diff_(base-other)": np.nan, "t_stat": np.nan, "note": "too few series to test"})
                continue
            diff = paired["MAE_base"] - paired["MAE_other"]  # positive = variant beats baseline (lower MAE)
            mean_diff = diff.mean()
            se = diff.std(ddof=1) / np.sqrt(n)
            t_stat = mean_diff / se if se else np.nan
            rows.append({"level": level, "variant": variant, "baseline": baseline, "n_paired": n,
                         "mean_diff_(base-other)": mean_diff, "t_stat": t_stat,
                         "note": "positive mean_diff = variant has LOWER (better) MAE than baseline"})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    series = build_all_series(monthly, scope)

    models = get_models(MA_WINDOWS)
    logger.info("Base candidate models: %s. Robust subset for RobustSubsetMedian: %s", list(models), ROBUST_SUBSET)

    n_series_usable = sum(1 for (qty, _) in series.values() if len(qty) == TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS and qty.sum() > 0)
    logger.info("%d of %d series have the full %d-month history with nonzero demand and are usable "
                "(NoSale / too-short series are excluded, matching evaluate_strategies.py's convention)",
                n_series_usable, len(series), TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS)

    val_df = run_stage(series, models, TRAIN_MONTHS, VAL_MONTHS, "validation")
    val_df.to_csv(os.path.join(SUMMARY_DIR, "combo_variant_validation_results.csv"), index=False)

    test_df = run_stage(series, models, TRAIN_MONTHS + VAL_MONTHS, TEST_MONTHS, "test")
    test_df.to_csv(os.path.join(SUMMARY_DIR, "combo_variant_test_results.csv"), index=False)

    # ---- summary by level x variant ----
    summary_val = val_df.groupby(["level", "variant"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    summary_test = test_df.groupby(["level", "variant"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    summary_val.to_csv(os.path.join(SUMMARY_DIR, "combo_variant_summary_validation.csv"), index=False)
    summary_test.to_csv(os.path.join(SUMMARY_DIR, "combo_variant_summary_test.csv"), index=False)

    # ---- validation-to-test gap per level x variant ----
    gap_rows = []
    for level in test_df["level"].unique():
        for variant in VARIANTS:
            v_mae = summary_val[(summary_val["level"] == level) & (summary_val["variant"] == variant)]["MAE"]
            t_mae = summary_test[(summary_test["level"] == level) & (summary_test["variant"] == variant)]["MAE"]
            if v_mae.empty or t_mae.empty:
                continue
            v_mae, t_mae = float(v_mae.iloc[0]), float(t_mae.iloc[0])
            gap = t_mae - v_mae
            gap_pct = 100 * gap / v_mae if v_mae else np.nan
            gap_rows.append({"level": level, "variant": variant, "val_MAE": v_mae, "test_MAE": t_mae,
                              "gap": gap, "gap_pct": gap_pct})
    gap_df = pd.DataFrame(gap_rows)
    gap_df.to_csv(os.path.join(SUMMARY_DIR, "combo_variant_val_test_gap.csv"), index=False)

    # ---- paired significance vs. the current Mean approach, on the TEST set ----
    sig_df = paired_significance(test_df, baseline="Mean")
    sig_df.to_csv(os.path.join(SUMMARY_DIR, "combo_variant_significance_vs_mean.csv"), index=False)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 92)
    print("# PART 1: COMBINATION-FORECAST VARIANTS vs. THE CURRENT ARITHMETIC MEAN")
    print("#" * 92)
    print(f"\nSeries usable (full {TRAIN_MONTHS+VAL_MONTHS+TEST_MONTHS}-month history, nonzero demand): {n_series_usable} of {len(series)}")
    print(f"Base candidates combined: {list(models)}")
    print(f"RobustSubsetMedian uses: {ROBUST_SUBSET} (Croston/SBA excluded — see module docstring for the evidenced reason)")

    for level in ["Category", "Type", "Item"]:
        sub = summary_test[summary_test["level"] == level].sort_values("MAE")
        if sub.empty:
            continue
        print(f"\n--- {level} level — TEST-SET metrics, mean across series (best MAE first) ---")
        print(sub.to_string(index=False))
        gap_sub = gap_df[gap_df["level"] == level].sort_values("variant")
        print(f"\n{level}: validation-to-test gap per variant:")
        print(gap_sub.to_string(index=False))
        sig_sub = sig_df[sig_df["level"] == level]
        print(f"\n{level}: paired t-test of each variant vs. Mean (current), on per-series TEST MAE:")
        print(sig_sub[["variant", "n_paired", "mean_diff_(base-other)", "t_stat", "note"]].to_string(index=False))
        for _, r in sig_sub.iterrows():
            if pd.isna(r["t_stat"]):
                continue
            verdict = "statistically distinguishable (|t|>~2)" if abs(r["t_stat"]) > 2 else "NOT statistically distinguishable from Mean (|t|<~2) — could be noise"
            print(f"  Mean vs {r['variant']}: {verdict} (t={r['t_stat']:.2f}, n={int(r['n_paired'])})")

    print("\n" + "=" * 92)
    print("BOTTOM LINE")
    print("=" * 92)
    for level in ["Category", "Type", "Item"]:
        sub = summary_test[summary_test["level"] == level].sort_values("MAE")
        if sub.empty:
            continue
        winner = sub.iloc[0]
        mean_row = sub[sub["variant"] == "Mean"].iloc[0]
        if winner["variant"] == "Mean":
            print(f"{level}: the current arithmetic Mean is NOT beaten on MAE — it remains the best point estimate "
                  f"(MAE={winner['MAE']:.2f}).")
        else:
            improvement_pct = 100 * (mean_row["MAE"] - winner["MAE"]) / mean_row["MAE"] if mean_row["MAE"] else np.nan
            print(f"{level}: {winner['variant']} has the best point-estimate MAE ({winner['MAE']:.2f} vs. Mean's "
                  f"{mean_row['MAE']:.2f}, {improvement_pct:+.1f}%) — see the paired t-test above for whether this "
                  f"margin is statistically distinguishable from noise before treating it as a real improvement.")

    print("\nFull detail: output/summary/combo_variant_validation_results.csv, combo_variant_test_results.csv,")
    print("combo_variant_summary_validation.csv, combo_variant_summary_test.csv, combo_variant_val_test_gap.csv,")
    print("combo_variant_significance_vs_mean.csv")
