"""Phase C step 2: Category/Type-level Combination backtest across all five in-scope divisions
(PEM101, PEM102, PEM103, PEM107, CI101 — PEM104 contributes no forecast-status items), on the
335-item scope built by src/load_data_all_divisions.py.

Reuses src/backtest_rekeyed.py's tested rolling-origin/train-val-test machinery UNCHANGED
(run_rolling_origin, run_train_val_test, compute_metrics, get_origins, the leakage guard
integration) rather than reimplementing it — imported, not copied. The only new logic here is
building the (level, key, category) series dict with DIVISION folded into the key/category
strings ("DIVISION::name"), so a Category or Type name that happens to collide across divisions
(already documented repeatedly in STATUS.md, e.g. "Fuse" existing under many divisions for
unrelated products) is never silently pooled across divisions.

Runs on EITHER qty or sale as the value column (Part 2 of this task: value-based aggregation
comparison) — pass --value-col qty|sale. Same backtest, same models, same evaluation policy,
different value column; this is the whole point of the value-vs-quantity comparison.
"""
import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import (HOLDOUT, MA_WINDOWS, TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS,
                               VAL_MONTHS, compute_metrics, get_origins, run_rolling_origin,
                               run_train_val_test)
from leakage_guard import load_min_margin_days
from models import get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backtest_all_divisions")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]


def build_level_series_by_division(monthly: pd.DataFrame, scope: pd.DataFrame, value_col: str) -> dict:
    """Returns {(level, key, cat): (values_array, months_list)} for Category, Type and Item level,
    with `key` and `cat` prefixed "DIVISION::name" so no name collision across divisions is ever
    pooled. Item level includes ALL scope codes (no-history items get an empty placeholder,
    consistent with backtest_rekeyed.py's own convention)."""
    series = {}
    for (div, cat), g in monthly.groupby(["division", "category"]):
        agg = g.groupby("year_month", as_index=False)[value_col].sum().sort_values("year_month")
        key = f"{div}::{cat}"
        series[("Category", key, key)] = (agg[value_col].to_numpy(dtype=float), agg["year_month"].astype(str).tolist())
    for (div, cat, typ), g in monthly.groupby(["division", "category", "type"]):
        agg = g.groupby("year_month", as_index=False)[value_col].sum().sort_values("year_month")
        type_key = f"{div}::{typ}"
        cat_key = f"{div}::{cat}"
        series[("Type", type_key, cat_key)] = (agg[value_col].to_numpy(dtype=float), agg["year_month"].astype(str).tolist())
    items_with_history = set(monthly.loc[monthly[value_col] != 0, "itemcode"].unique()) | set(monthly["itemcode"].unique())
    for _, row in scope.iterrows():
        code, div, cat = row["code"], row["division"], row["category"]
        g = monthly[monthly["itemcode"] == code].sort_values("year_month")
        cat_key = f"{div}::{cat}"
        if len(g):
            series[("Item", code, cat_key)] = (g[value_col].to_numpy(dtype=float), g["year_month"].astype(str).tolist())
        else:
            series[("Item", code, cat_key)] = (np.array([]), [])
    return series


def rolling_origin_winner_stability(ro: pd.DataFrame) -> pd.DataFrame:
    """For each (level, key), find the model with the lowest MEAN MAE across all origins (the
    'winner'), then report on how many of that series' origins that same model was ALSO the
    single best (stability of the winner across origins) -- not assumed stable, measured."""
    rows = []
    for (level, key), g in ro.groupby(["level", "key"]):
        mean_by_model = g.groupby("model")["MAE"].mean()
        winner = mean_by_model.idxmin()
        n_origins = g["origin"].nunique()
        best_per_origin = g.loc[g.groupby("origin")["MAE"].idxmin()]
        n_origins_winner_was_best = (best_per_origin["model"] == winner).sum()
        rows.append({
            "level": level, "key": key, "winner": winner, "winner_mean_MAE": mean_by_model[winner],
            "n_origins": n_origins, "n_origins_winner_was_best": n_origins_winner_was_best,
            "winner_stability_pct": 100 * n_origins_winner_was_best / n_origins if n_origins else np.nan,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--value-col", choices=["qty", "sale"], default="qty")
    args = parser.parse_args()
    value_col = args.value_col

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, f"processed_all_divisions_monthly_{value_col}.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    models = get_models(MA_WINDOWS)
    logger.info("[%s] %d items across %d divisions. Leakage guard min_margin_days=%d, pull_date=%s",
                value_col, len(scope), scope["division"].nunique(), min_margin_days, pull_date)

    series = build_level_series_by_division(monthly, scope, value_col)
    n_cat = sum(1 for k in series if k[0] == "Category")
    n_typ = sum(1 for k in series if k[0] == "Type")
    n_item = sum(1 for k in series if k[0] == "Item" and len(series[k][0]) > 0)
    logger.info("[%s] Series built: %d Category, %d Type, %d Item (with history)", value_col, n_cat, n_typ, n_item)

    ro = run_rolling_origin(series, models, pull_date, min_margin_days)
    ro["division"] = ro["key"].str.split("::").str[0]
    ro["name"] = ro["key"].str.split("::").str[1]
    ro.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_rolling_origin_{value_col}.csv"), index=False)

    val_df, test_df = run_train_val_test(series, models, pull_date, min_margin_days)
    for df_ in (val_df, test_df):
        df_["division"] = df_["key"].str.split("::").str[0]
        df_["name"] = df_["key"].str.split("::").str[1]
    val_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_val_{value_col}.csv"), index=False)
    test_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_test_{value_col}.csv"), index=False)

    # ---- Per-division, per-Type summary (Combination only) ----
    # METRICS.md Sec.39: "every reported figure states the window's first and last test months" --
    # a summary pooling K origins states the SPAN it pools (earliest origin's first test month to
    # the last origin's last test month), not a single origin's own window.
    combo_ro = ro[ro["model"] == "Combination"]
    per_type_summary = combo_ro[combo_ro["level"] == "Type"].groupby(["division", "name"], as_index=False).agg(
        MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), Bias=("Bias", "mean"), MASE=("MASE", "mean"),
        n_origins=("origin", "nunique"),
        rolling_origin_first_test_month=("first_test_month", "min"),
        rolling_origin_last_test_month=("last_test_month", "max"))
    n_items_per_type = scope.groupby(["division", "type"], as_index=False).size().rename(
        columns={"type": "name", "size": "n_items"})
    per_type_summary = per_type_summary.merge(n_items_per_type, on=["division", "name"], how="left")
    per_type_summary.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_per_type_summary_{value_col}.csv"), index=False)

    per_division_summary = combo_ro[combo_ro["level"] == "Type"].groupby("division", as_index=False).agg(
        MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), Bias=("Bias", "mean"), MASE=("MASE", "mean"),
        n_origins=("origin", "nunique"),
        rolling_origin_first_test_month=("first_test_month", "min"),
        rolling_origin_last_test_month=("last_test_month", "max"))
    n_items_per_division = scope.groupby("division", as_index=False).size().rename(columns={"size": "n_items"})
    per_division_summary = per_division_summary.merge(n_items_per_division, on="division", how="left")
    per_division_summary.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_per_division_summary_{value_col}.csv"), index=False)

    # ---- Rolling-origin winner stability (Type level) ----
    stability = rolling_origin_winner_stability(ro[ro["level"] == "Type"])
    stability["division"] = stability["key"].str.split("::").str[0]
    stability["name"] = stability["key"].str.split("::").str[1]
    stability.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_winner_stability_{value_col}.csv"), index=False)

    # ---- Validation-to-test gap, Combination, per division (Type level) ----
    gap_rows = []
    for div in scope["division"].unique():
        v = val_df[(val_df["division"] == div) & (val_df["level"] == "Type") & (val_df["model"] == "Combination")]["MAE"].mean()
        t = test_df[(test_df["division"] == div) & (test_df["level"] == "Type") & (test_df["model"] == "Combination")]["MAE"].mean()
        gap_rows.append({"division": div, "val_MAE": v, "test_MAE": t, "gap": t - v,
                          "gap_pct": 100 * (t - v) / v if v else np.nan})
    gap_df = pd.DataFrame(gap_rows)
    gap_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_val_test_gap_{value_col}.csv"), index=False)

    # ---- Zero-inflation at Category/Type level (value col) ----
    zero_rows = []
    for level in ["Category", "Type"]:
        vals = []
        for k, (arr, months) in series.items():
            if k[0] == level and len(arr) > 0:
                vals.extend(arr.tolist())
        vals = np.array(vals)
        zero_rows.append({"level": level, "pct_zero": 100 * (vals == 0).mean() if len(vals) else np.nan, "n_values": len(vals)})
    zero_df = pd.DataFrame(zero_rows)
    zero_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_zero_inflation_{value_col}.csv"), index=False)

    # ---- Focus items (Item level, Combination, test set) ----
    focus_rows = []
    for item in FOCUS_ITEMS:
        g = test_df[(test_df["level"] == "Item") & (test_df["key"] == item) & (test_df["model"] == "Combination")]
        if len(g):
            focus_rows.append({"itemcode": item, **g.iloc[0][["MAE", "RMSE", "Bias", "MASE"]].to_dict()})
    focus_df = pd.DataFrame(focus_rows)
    focus_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseC_step2_focus_items_{value_col}.csv"), index=False)

    print("\n" + "=" * 92)
    print(f"PHASE C STEP 2 BACKTEST — value_col={value_col}")
    print("=" * 92)
    print(f"\n--- Per-division summary (Type level, Combination, rolling-origin) ---")
    print(per_division_summary.round(2).to_string(index=False))
    print(f"\n--- Validation-to-test gap per division (Type level, Combination) ---")
    print(gap_df.round(2).to_string(index=False))
    print(f"\n--- Zero-inflation ---")
    print(zero_df.round(2).to_string(index=False))
    print(f"\n--- Focus items (test set, Combination) ---")
    print(focus_df.round(2).to_string(index=False))
    print(f"\nOutputs: phaseC_step2_rolling_origin_{value_col}.csv, _val_{value_col}.csv, _test_{value_col}.csv, "
          f"_per_type_summary_{value_col}.csv, _per_division_summary_{value_col}.csv, "
          f"_winner_stability_{value_col}.csv, _val_test_gap_{value_col}.csv, _zero_inflation_{value_col}.csv, "
          f"_focus_items_{value_col}.csv")
