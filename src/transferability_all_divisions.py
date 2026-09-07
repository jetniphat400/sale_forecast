"""Phase C step 2, Part 3: per-division transferability of Top-down combination.

Compares Top-down (Type-level Combination, allocated to items by historical qty share, refit at
EVERY rolling-origin -- not a single fixed-split allocation) against Direct (item-level
Combination) and Naive (item-level), using the SAME rolling-origin methodology as
src/backtest_rekeyed.py (get_origins, compute_metrics, the leakage guard) — imported, not
reimplemented, so results are directly comparable to Part 1's Category/Type backtest.

Division is folded into the Type key ("DIVISION::type"), same convention as
src/backtest_all_divisions.py, so Top-down allocation never pools an item into another
division's same-named Type.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import HOLDOUT, MA_WINDOWS, TOTAL_MONTHS, compute_metrics, get_origins
from leakage_guard import check_window_closed, load_min_margin_days
from models import combination_forecast, naive_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("transferability_all_divisions")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def build_item_and_type_series(monthly: pd.DataFrame, scope: pd.DataFrame) -> tuple:
    """item_series: {code: (qty_array, months, type_key, division, category)}.
    type_series: {type_key: (qty_array, months)}, type_key = 'DIVISION::type'."""
    item_series = {}
    for _, row in scope.iterrows():
        code, div, cat, typ = row["code"], row["division"], row["category"], row["type"]
        g = monthly[monthly["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        months = g["year_month"].astype(str).tolist()
        type_key = f"{div}::{typ}"
        item_series[code] = (qty, months, type_key, div, cat)

    type_series = {}
    for (div, typ), g in monthly.groupby(["division", "type"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        type_key = f"{div}::{typ}"
        type_series[type_key] = (agg["qty"].to_numpy(dtype=float), agg["year_month"].astype(str).tolist())
    return item_series, type_series


def run_transferability_rolling_origin(item_series: dict, type_series: dict, pull_date, min_margin_days: int) -> pd.DataFrame:
    """At every rolling-origin (get_origins(TOTAL_MONTHS, HOLDOUT), same origins as Part 1's
    Category/Type backtest), scores Direct, Top-down and Naive for every item with a
    full-length series, per this project's established 6-month holdout convention."""
    results = []
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)
    for code, (qty, months, type_key, div, cat) in item_series.items():
        if len(qty) != TOTAL_MONTHS or qty.sum() == 0:
            continue
        type_qty, type_months = type_series[type_key]
        for origin_idx, train_size in enumerate(origins, start=1):
            train = qty[:train_size]
            test = qty[train_size:train_size + HOLDOUT]
            if len(test) < HOLDOUT:
                continue
            window_end_month = months[train_size + HOLDOUT - 1]
            check_window_closed(window_end_month, pull_date, min_margin_days)

            direct_fc = np.clip(combination_forecast(train, HOLDOUT, MA_WINDOWS), 0, None)
            naive_fc = np.clip(naive_forecast(train, HOLDOUT), 0, None)

            type_train = type_qty[:train_size]
            type_fc = np.clip(combination_forecast(type_train, HOLDOUT, MA_WINDOWS), 0, None)
            type_total = type_train.sum()
            item_total = train.sum()
            share = item_total / type_total if type_total > 0 else np.nan
            topdown_fc = type_fc * share if pd.notna(share) else np.full(HOLDOUT, np.nan)

            for approach, fc in [("Direct", direct_fc), ("Naive", naive_fc), ("Top-down", topdown_fc)]:
                if np.any(np.isnan(fc)):
                    continue
                m = compute_metrics(test, fc, train)
                results.append({"division": div, "category": cat, "type_key": type_key, "itemcode": code,
                                 "origin": origin_idx, "train_size": train_size, "approach": approach, **m})
    return pd.DataFrame(results)


if __name__ == "__main__":
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    logger.info("%d items, %d divisions. Leakage guard min_margin_days=%d, pull_date=%s",
                len(scope), scope["division"].nunique(), min_margin_days, pull_date)

    item_series, type_series = build_item_and_type_series(monthly, scope)
    logger.info("%d item series (full-length), %d Type series", len(item_series), len(type_series))

    results = run_transferability_rolling_origin(item_series, type_series, pull_date, min_margin_days)
    results.to_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_item_rolling_origin.csv"), index=False)
    logger.info("%d item x origin x approach rows scored.", len(results))

    # ---- Per-division summary: mean MAE per approach ----
    per_division = results.groupby(["division", "approach"], as_index=False).agg(
        MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), Bias=("Bias", "mean"), MASE=("MASE", "mean"),
        n_scored=("MAE", "size"))
    per_division.to_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_per_division.csv"), index=False)

    # ---- Verdict per division: does Top-down hold its advantage over Direct, and over Naive? ----
    verdict_rows = []
    for div, g in per_division.groupby("division"):
        mae = dict(zip(g["approach"], g["MAE"]))
        td, direct, naive = mae.get("Top-down"), mae.get("Direct"), mae.get("Naive")
        if td is None or direct is None or naive is None:
            continue
        beats_direct = td < direct
        beats_naive = td < naive
        if beats_direct and beats_naive:
            verdict = "Top-down holds its advantage (beats both Direct and Naive)"
        elif beats_naive and not beats_direct:
            verdict = "Top-down beats Naive but loses its edge over Direct"
        elif not beats_naive:
            verdict = "Top-down FALLS BEHIND Naive"
        else:
            verdict = "mixed"
        verdict_rows.append({"division": div, "MAE_Top-down": td, "MAE_Direct": direct, "MAE_Naive": naive,
                              "topdown_vs_direct_pct": 100 * (td - direct) / direct if direct else np.nan,
                              "topdown_vs_naive_pct": 100 * (td - naive) / naive if naive else np.nan,
                              "verdict": verdict})
    verdict_df = pd.DataFrame(verdict_rows)
    verdict_df.to_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_verdict.csv"), index=False)

    # ---- Paired significance (Top-down vs Direct, Top-down vs Naive), per division, item-mean-first ----
    sig_rows = []
    for div in scope["division"].unique():
        sub = results[results["division"] == div]
        item_means = sub.groupby(["itemcode", "approach"])["MAE"].mean().unstack()
        for a, b in [("Top-down", "Direct"), ("Top-down", "Naive")]:
            if a not in item_means.columns or b not in item_means.columns:
                continue
            paired = item_means[[a, b]].dropna()
            diff = paired[a] - paired[b]
            n = len(diff)
            if n < 2:
                continue
            se = diff.std(ddof=1) / np.sqrt(n)
            t_stat = diff.mean() / se if se else np.nan
            sig_rows.append({"division": div, "approach_a": a, "approach_b": b, "n_items": n,
                              "mean_diff_a_minus_b": diff.mean(), "t_stat": t_stat})
    sig_df = pd.DataFrame(sig_rows)
    sig_df.to_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_significance.csv"), index=False)

    print("\n" + "=" * 92)
    print("PHASE C STEP 2, PART 3: TRANSFERABILITY — Top-down vs Direct vs Naive, rolling-origin, per division")
    print("=" * 92)
    print(per_division.round(2).to_string(index=False))
    print("\n--- Verdict per division ---")
    print(verdict_df.round(2).to_string(index=False))
    print("\n--- Paired significance (|t|>2 suggests a real, consistent difference) ---")
    print(sig_df.round(3).to_string(index=False))
    print("\nOutputs: phaseC_step2_transferability_item_rolling_origin.csv, "
          "_per_division.csv, _verdict.csv, _significance.csv")
