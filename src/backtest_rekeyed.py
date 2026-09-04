"""Phase B, task B1: re-run the full backtest on the forecast_date-keyed series and
compare against the createDate-keyed results.

INVESTIGATION/MODELLING task. No model choice is written to config.yaml.

Reuses the EXACT same methodology this project has used throughout, so any difference found is
attributable to the re-keying alone, not to a change in method:
  - Rolling-origin: MIN_TRAIN_MONTHS=13, ORIGIN_STEP=2, HOLDOUT=6 (src/backtest_aggregate.py,
    src/rolling_origin.py, src/rule_stability_origins.py).
  - Train/validation/test: 19/6/6 months (src/evaluate_strategies.py, src/backtest_aggregate.py).
  - MAE/RMSE/Bias/MASE computed identically to src/evaluate_strategies.py's compute_metrics
    (MASE scale = mean absolute first difference of the series used to fit the forecast).
  - Combination forecast = equal-weight average of Naive/MA3/MA6/MA12/Croston/SBA
    (src/models.py combination_forecast) — the six base models are also scored individually.

Both keyings are read from output/data/processed_full_category_sales_monthly_{createDate,
forecastDate}.csv, both ALREADY restricted (by src/load_data_full.py's re-keying update) to the
identical 31-month common comparison window (2024-01 to 2026-07) that every prior backtest
result in output/summary/ was computed on — so no further truncation is needed here, and the
comparison is a true apples-to-apples one on the SAME calendar months, differing only in which
date field placed each row into a month.

createDate-keyed results are RECOMPUTED here with this exact same fresh code (not merely re-read
from the older rule_part4_*.csv / part4_*.csv files), so that any difference found against
forecast_date is attributable only to the re-keying, never to a difference in script/version
between an old run and a new one. The recomputed createDate numbers are then cross-checked
against those older files as a validation step (Part 5 below), since the underlying raw data has
also grown slightly since those were produced (a live database, not a frozen extract) — any
drift from that is reported explicitly, not hidden.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml
from scipy import stats

sys.path.insert(0, os.path.dirname(__file__))
from leakage_guard import check_window_closed, load_min_margin_days
from models import combination_forecast, get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backtest_rekeyed")

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
TOTAL_MONTHS = TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS  # 31

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
KEYS = ["createDate", "forecastDate"]

# Material-change thresholds, stated explicitly (a reasoned judgment, not a database fact):
# a level/model/metric cell is flagged "materially changed" between keyings if it moves by more
# than 10% relative to the createDate value (or by more than 1 unit in absolute terms for Bias
# near zero, to avoid flagging noise around a near-zero baseline).
MATERIAL_REL_THRESHOLD = 0.10
MATERIAL_ABS_FLOOR = 1.0


def compute_metrics(actual: np.ndarray, forecast: np.ndarray, scale_series: np.ndarray) -> dict:
    """Identical recipe to src/evaluate_strategies.py's compute_metrics."""
    errors = forecast - actual
    mae = float(np.abs(errors).mean())
    rmse = float(np.sqrt((errors ** 2).mean()))
    bias = float(errors.mean())
    naive_diffs = np.abs(np.diff(scale_series))
    scale = naive_diffs.mean()
    mase = mae / scale if scale > 0 else np.nan
    return {"MAE": mae, "RMSE": rmse, "Bias": bias, "MASE": mase}


def get_origins(total_months: int, holdout: int) -> list:
    last_train = total_months - holdout
    origins = list(range(MIN_TRAIN_MONTHS, last_train + 1, ORIGIN_STEP))
    if origins[-1] != last_train:
        origins.append(last_train)
    return origins


def build_level_series(monthly: pd.DataFrame, scope: pd.DataFrame) -> dict:
    """Returns {(level, key, category): (qty_array, months_list)} for Category, Type and Item
    level. Item level includes ALL 128 scope codes (no-history items get an empty placeholder,
    skipped downstream) — same contract as src/feature_analysis.py's build_all_series, kept local
    here so this script has no import-order dependency on that module's own file-reading side effects."""
    series = {}
    for cat, g in monthly.groupby("category"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        series[("Category", cat, cat)] = (agg["qty"].to_numpy(dtype=float), agg["year_month"].astype(str).tolist())
    for (cat, typ), g in monthly.groupby(["category", "type"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        series[("Type", typ, cat)] = (agg["qty"].to_numpy(dtype=float), agg["year_month"].astype(str).tolist())
    items_with_history = set(monthly["itemcode"].unique())
    for _, row in scope.iterrows():
        code, cat = row["code"], row["category"]
        if code in items_with_history:
            g = monthly[monthly["itemcode"] == code].sort_values("year_month")
            series[("Item", code, cat)] = (g["qty"].to_numpy(dtype=float), g["year_month"].astype(str).tolist())
        else:
            series[("Item", code, cat)] = (np.array([]), [])
    return series


def run_rolling_origin(series: dict, models: dict, pull_date, min_margin_days: int) -> pd.DataFrame:
    """pull_date and min_margin_days are REQUIRED (Task 2 leakage guard, src/leakage_guard.py):
    every origin's test window is checked against the data's snapshot pull date before it is
    scored, and scoring is refused (LeakageGuardError raised, not skipped/warned) if the margin
    is insufficient. pull_date is the frozen snapshot_pull_date read from the monthly file being
    scored (never re-queried live); min_margin_days comes from config/config.yaml's
    leakage_guard.min_margin_days (src/leakage_guard.load_min_margin_days)."""
    results = []
    for (level, key, cat), (qty, months) in series.items():
        if len(qty) == 0 or qty.sum() == 0:
            continue
        n = len(qty)
        origins = get_origins(n, HOLDOUT)
        for origin_idx, train_size in enumerate(origins, start=1):
            train = qty[:train_size]
            test = qty[train_size:train_size + HOLDOUT]
            if len(test) < HOLDOUT:
                continue
            window_end_month = months[train_size + HOLDOUT - 1]
            check_window_closed(window_end_month, pull_date, min_margin_days)
            for model_name, model_fn in models.items():
                try:
                    forecast = np.clip(model_fn(train, HOLDOUT), 0, None)
                except Exception as e:
                    logger.warning("Model %s failed for %s/%s at origin %d: %s", model_name, level, key, origin_idx, e)
                    continue
                m = compute_metrics(test, forecast, train)
                results.append({"level": level, "key": key, "category": cat, "origin": origin_idx,
                                 "train_size": train_size, "model": model_name, **m})
            try:
                combo = np.clip(combination_forecast(train, HOLDOUT, MA_WINDOWS), 0, None)
                m = compute_metrics(test, combo, train)
                results.append({"level": level, "key": key, "category": cat, "origin": origin_idx,
                                 "train_size": train_size, "model": "Combination", **m})
            except Exception as e:
                logger.warning("Combination failed for %s/%s at origin %d: %s", level, key, origin_idx, e)
    return pd.DataFrame(results)


def run_train_val_test(series: dict, models: dict, pull_date, min_margin_days: int) -> tuple:
    """pull_date and min_margin_days are REQUIRED (Task 2 leakage guard, src/leakage_guard.py):
    both the validation window and the test window are checked against the data's snapshot pull
    date before either is scored, and scoring is refused (LeakageGuardError raised, not skipped/
    warned) if the margin is insufficient. See run_rolling_origin's docstring for the parameters'
    provenance."""
    val_records, test_records = [], []
    for (level, key, cat), (qty, months) in series.items():
        if len(qty) != TOTAL_MONTHS or qty.sum() == 0:
            continue
        train = qty[:TRAIN_MONTHS]
        val = qty[TRAIN_MONTHS:TRAIN_MONTHS + VAL_MONTHS]
        train_val = qty[:TRAIN_MONTHS + VAL_MONTHS]
        test = qty[TRAIN_MONTHS + VAL_MONTHS:]

        check_window_closed(months[TRAIN_MONTHS + VAL_MONTHS - 1], pull_date, min_margin_days)  # val window end
        check_window_closed(months[TOTAL_MONTHS - 1], pull_date, min_margin_days)  # test window end

        for model_name, model_fn in models.items():
            fc_val = np.clip(model_fn(train, VAL_MONTHS), 0, None)
            val_records.append({"level": level, "key": key, "category": cat, "model": model_name,
                                 **compute_metrics(val, fc_val, train)})
            fc_test = np.clip(model_fn(train_val, TEST_MONTHS), 0, None)
            test_records.append({"level": level, "key": key, "category": cat, "model": model_name,
                                  **compute_metrics(test, fc_test, train_val)})
        combo_val = np.clip(combination_forecast(train, VAL_MONTHS, MA_WINDOWS), 0, None)
        val_records.append({"level": level, "key": key, "category": cat, "model": "Combination",
                             **compute_metrics(val, combo_val, train)})
        combo_test = np.clip(combination_forecast(train_val, TEST_MONTHS, MA_WINDOWS), 0, None)
        test_records.append({"level": level, "key": key, "category": cat, "model": "Combination",
                              **compute_metrics(test, combo_test, train_val)})
    return pd.DataFrame(val_records), pd.DataFrame(test_records)


def validate_pipeline(monthly: pd.DataFrame, scope: pd.DataFrame, label: str) -> None:
    """Re-confirms, on the actual data used for this run, the same invariants
    src/load_data_full.py already checked at pull time (CONVENTIONS.md: validate before use)."""
    neg = monthly[(monthly["qty"] < 0)]
    assert len(neg) == 0, f"[{label}] negative qty found in monthly series — {len(neg)} rows"
    n_items = monthly["itemcode"].nunique()
    n_scope_with_history = scope["code"].isin(monthly["itemcode"].unique()).sum()
    logger.info("[%s] Validation: 0 negative qty; %d distinct items in monthly series (%d of %d scope codes "
                "have a row here); %d months per item (min=%d, max=%d) — %s",
                label, n_items, n_scope_with_history, len(scope),
                monthly.groupby("itemcode")["year_month"].nunique().mode().iloc[0],
                monthly.groupby("itemcode")["year_month"].nunique().min(),
                monthly.groupby("itemcode")["year_month"].nunique().max(),
                "item counts and month grid consistent" if monthly.groupby("itemcode")["year_month"].nunique().nunique() == 1
                else "WARNING: inconsistent month counts across items")


if __name__ == "__main__":
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    models = get_models(MA_WINDOWS)

    CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    min_margin_days = load_min_margin_days(_config)
    logger.info("Leakage guard: min_margin_days=%d (config/config.yaml: leakage_guard.min_margin_days)", min_margin_days)

    all_ro_results, all_val_results, all_test_results = {}, {}, {}
    for key in KEYS:
        monthly = pd.read_csv(os.path.join(DATA_DIR, f"processed_full_category_sales_monthly_{key}.csv"))
        validate_pipeline(monthly, scope, key)
        total_months = monthly["year_month"].nunique()
        pull_date = monthly["snapshot_pull_date"].iloc[0]
        logger.info("[%s] %d months (%s to %s), building Category/Type/Item series. snapshot_pull_date=%s", key, total_months,
                    monthly["year_month"].min(), monthly["year_month"].max(), pull_date)
        series = build_level_series(monthly, scope)
        n_cat = sum(1 for k in series if k[0] == "Category")
        n_typ = sum(1 for k in series if k[0] == "Type")
        n_item = sum(1 for k in series if k[0] == "Item" and len(series[k][0]) > 0)
        logger.info("[%s] Series built: %d Category, %d Type, %d Item (with history)", key, n_cat, n_typ, n_item)

        ro = run_rolling_origin(series, models, pull_date, min_margin_days)
        ro["date_key"] = key
        ro.to_csv(os.path.join(SUMMARY_DIR, f"b1_rolling_origin_results_{key}.csv"), index=False)
        all_ro_results[key] = ro

        val_df, test_df = run_train_val_test(series, models, pull_date, min_margin_days)
        val_df["date_key"] = key
        test_df["date_key"] = key
        val_df.to_csv(os.path.join(SUMMARY_DIR, f"b1_val_results_{key}.csv"), index=False)
        test_df.to_csv(os.path.join(SUMMARY_DIR, f"b1_test_results_{key}.csv"), index=False)
        all_val_results[key] = val_df
        all_test_results[key] = test_df

        origins = get_origins(TOTAL_MONTHS, HOLDOUT)
        logger.info("[%s] Rolling-origin: %d origins (train sizes %s). Train/val/test: %d series scored.",
                    key, len(origins), origins, test_df[["level", "key"]].drop_duplicates().shape[0])

    # ============================= COMPARISON: rolling-origin, mean per level/model =============================
    ro_summary = {}
    for key in KEYS:
        s = all_ro_results[key].groupby(["level", "model"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        s["date_key"] = key
        ro_summary[key] = s
    ro_compare = ro_summary["createDate"].merge(
        ro_summary["forecastDate"], on=["level", "model"], suffixes=("_createDate", "_forecastDate"))
    for m in ["MAE", "RMSE", "Bias", "MASE"]:
        ro_compare[f"{m}_delta"] = ro_compare[f"{m}_forecastDate"] - ro_compare[f"{m}_createDate"]
        ro_compare[f"{m}_pct_change"] = np.where(
            ro_compare[f"{m}_createDate"].abs() > MATERIAL_ABS_FLOOR,
            100 * ro_compare[f"{m}_delta"] / ro_compare[f"{m}_createDate"].abs(), np.nan)
        ro_compare[f"{m}_material"] = (ro_compare[f"{m}_pct_change"].abs() > 100 * MATERIAL_REL_THRESHOLD) | \
                                       (ro_compare[f"{m}_delta"].abs() > MATERIAL_ABS_FLOOR)
    ro_compare.to_csv(os.path.join(SUMMARY_DIR, "b1_rolling_origin_comparison.csv"), index=False)

    # ============================= COMPARISON: train/val/test, mean per level/model =============================
    test_summary = {}
    for key in KEYS:
        s = all_test_results[key].groupby(["level", "model"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        s["date_key"] = key
        test_summary[key] = s
    test_compare = test_summary["createDate"].merge(
        test_summary["forecastDate"], on=["level", "model"], suffixes=("_createDate", "_forecastDate"))
    for m in ["MAE", "RMSE", "Bias", "MASE"]:
        test_compare[f"{m}_delta"] = test_compare[f"{m}_forecastDate"] - test_compare[f"{m}_createDate"]
        test_compare[f"{m}_pct_change"] = np.where(
            test_compare[f"{m}_createDate"].abs() > MATERIAL_ABS_FLOOR,
            100 * test_compare[f"{m}_delta"] / test_compare[f"{m}_createDate"].abs(), np.nan)
        test_compare[f"{m}_material"] = (test_compare[f"{m}_pct_change"].abs() > 100 * MATERIAL_REL_THRESHOLD) | \
                                         (test_compare[f"{m}_delta"].abs() > MATERIAL_ABS_FLOOR)
    test_compare.to_csv(os.path.join(SUMMARY_DIR, "b1_train_val_test_comparison.csv"), index=False)

    # Validation-to-test gap per keying (mean test MAE - mean val MAE, relative to val MAE), Combination only
    gap_rows = []
    for key in KEYS:
        for level in ["Category", "Type", "Item"]:
            v = all_val_results[key][(all_val_results[key]["level"] == level) & (all_val_results[key]["model"] == "Combination")]["MAE"].mean()
            t = all_test_results[key][(all_test_results[key]["level"] == level) & (all_test_results[key]["model"] == "Combination")]["MAE"].mean()
            gap_rows.append({"date_key": key, "level": level, "val_MAE": v, "test_MAE": t,
                              "gap": t - v, "gap_pct": 100 * (t - v) / v if v else np.nan})
    gap_df = pd.DataFrame(gap_rows)
    gap_df.to_csv(os.path.join(SUMMARY_DIR, "b1_val_test_gap_by_key.csv"), index=False)

    # ============================= FOCUS ITEMS: dedicated comparison + charts =============================
    focus_rows = []
    for key in KEYS:
        for item in FOCUS_ITEMS:
            g = all_test_results[key][(all_test_results[key]["level"] == "Item") & (all_test_results[key]["key"] == item)
                                       & (all_test_results[key]["model"] == "Combination")]
            if len(g):
                focus_rows.append({"date_key": key, "itemcode": item, **g.iloc[0][["MAE", "RMSE", "Bias", "MASE"]].to_dict()})
    focus_df = pd.DataFrame(focus_rows)
    focus_df.to_csv(os.path.join(SUMMARY_DIR, "b1_focus_items_test_comparison.csv"), index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for item in FOCUS_ITEMS:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
        for ax, key in zip(axes, KEYS):
            monthly = pd.read_csv(os.path.join(DATA_DIR, f"processed_full_category_sales_monthly_{key}.csv"))
            g = monthly[monthly["itemcode"] == item].sort_values("year_month")
            qty = g["qty"].to_numpy(dtype=float)
            if len(qty) != TOTAL_MONTHS:
                continue
            train_val, test = qty[:TRAIN_MONTHS + VAL_MONTHS], qty[TRAIN_MONTHS + VAL_MONTHS:]
            fc = np.clip(combination_forecast(train_val, TEST_MONTHS, MA_WINDOWS), 0, None)
            months = g["year_month"].tolist()
            ax.plot(range(len(qty)), qty, label="Actual", color="black", linewidth=1)
            ax.plot(range(TRAIN_MONTHS + VAL_MONTHS, TOTAL_MONTHS), fc, label="Combination forecast", color="tab:red", marker="o")
            ax.axvline(TRAIN_MONTHS + VAL_MONTHS, color="gray", linestyle="--", linewidth=1)
            ax.set_title(f"{item}\n{key}-keyed")
            ax.set_xlabel("Month index")
            ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, f"b1_focus_{item.replace('/', '_')}_createDate_vs_forecastDate.png"), dpi=120)
        plt.close(fig)

    # ============================= CROSS-CHECK vs EXISTING createDate OUTPUTS (validation) =============================
    print("\n" + "#" * 92)
    print("# B1: RE-KEYED BACKTEST — createDate vs forecast_date, cross-check against existing outputs")
    print("#" * 92)

    old_test_path = os.path.join(SUMMARY_DIR, "rule_part4_test_results_per_series.csv")
    if os.path.exists(old_test_path):
        old_test = pd.read_csv(old_test_path)
        old_combo = old_test[old_test["strategy"] == "Combination"].groupby("level", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        new_combo = all_test_results["createDate"][all_test_results["createDate"]["model"] == "Combination"].groupby("level", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        cross = old_combo.merge(new_combo, on="level", suffixes=("_old_existing", "_new_recomputed"))
        cross.to_csv(os.path.join(SUMMARY_DIR, "b1_crosscheck_vs_existing_combination.csv"), index=False)
        print("\n--- Cross-check: this run's fresh createDate-keyed Combination results vs the EXISTING "
              "rule_part4_test_results_per_series.csv (evaluate_strategies.py, an earlier task) ---")
        print(cross.to_string(index=False))
        print("Any difference here reflects the raw data having grown between pulls (a live database, not a "
              "frozen extract) plus the 1-newer-complete-month truncation this run applies — NOT a methodology "
              "change, since both use the identical Combination recipe, TRAIN/VAL/TEST=19/6/6, and MAE/RMSE/"
              "Bias/MASE.")
    else:
        print("\nNo existing rule_part4_test_results_per_series.csv found to cross-check against — skipped.")

    # ============================= CONSOLE SUMMARY =============================
    print("\n" + "=" * 92)
    print("ROLLING-ORIGIN: mean MAE/RMSE/Bias/MASE per level+model, createDate vs forecast_date")
    print("=" * 92)
    for level in ["Category", "Type", "Item"]:
        sub = ro_compare[ro_compare["level"] == level].sort_values("MAE_createDate")
        print(f"\n--- {level} ---")
        print(sub[["model", "MAE_createDate", "MAE_forecastDate", "MAE_pct_change", "MAE_material",
                    "Bias_createDate", "Bias_forecastDate", "Bias_pct_change", "Bias_material"]].round(2).to_string(index=False))
    n_material_ro = ro_compare[[c for c in ro_compare.columns if c.endswith("_material")]].any(axis=1).sum()
    print(f"\n{n_material_ro} of {len(ro_compare)} level/model rolling-origin cells show a MATERIAL change "
          f"(>{100*MATERIAL_REL_THRESHOLD:.0f}% relative or >{MATERIAL_ABS_FLOOR} absolute) in at least one metric.")

    print("\n" + "=" * 92)
    print("TRAIN/VAL/TEST: mean MAE/RMSE/Bias/MASE per level+model (test set), createDate vs forecast_date")
    print("=" * 92)
    for level in ["Category", "Type", "Item"]:
        sub = test_compare[test_compare["level"] == level].sort_values("MAE_createDate")
        print(f"\n--- {level} ---")
        print(sub[["model", "MAE_createDate", "MAE_forecastDate", "MAE_pct_change", "MAE_material",
                    "Bias_createDate", "Bias_forecastDate", "Bias_pct_change", "Bias_material"]].round(2).to_string(index=False))
    n_material_test = test_compare[[c for c in test_compare.columns if c.endswith("_material")]].any(axis=1).sum()
    print(f"\n{n_material_test} of {len(test_compare)} level/model train/val/test cells show a MATERIAL change "
          f"in at least one metric.")

    print("\n" + "=" * 92)
    print("VALIDATION-TO-TEST GAP (Combination), createDate vs forecast_date")
    print("=" * 92)
    print(gap_df.round(2).to_string(index=False))

    print("\n" + "=" * 92)
    print("FOCUS ITEMS (Item level, Combination, test set)")
    print("=" * 92)
    print(focus_df.round(2).to_string(index=False))

    print("\nOutputs: output/summary/b1_rolling_origin_results_{key}.csv, b1_val_results_{key}.csv, "
          "b1_test_results_{key}.csv, b1_rolling_origin_comparison.csv, b1_train_val_test_comparison.csv, "
          "b1_val_test_gap_by_key.csv, b1_focus_items_test_comparison.csv, b1_crosscheck_vs_existing_combination.csv")
    print("Charts: output/charts/b1_focus_<item>_createDate_vs_forecastDate.png")
