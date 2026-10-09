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
            # METRICS.md Sec.39: "every reported figure states the window's first and last test
            # months".
            first_test_month = months[train_size]
            last_test_month = window_end_month

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
                                 "origin": origin_idx, "train_size": train_size, "approach": approach,
                                 "first_test_month": first_test_month, "last_test_month": last_test_month, **m})
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Accuracy against Naive (METRICS.md Sec.48): the cells behind the main table, with Naive on the same cells, per horizon.
# ---------------------------------------------------------------------------------------------------------------------------------------------

def topdown_naive_cells(item_series: dict, type_series: dict, pull_date, min_margin_days: int) -> list:
    """The cells of the main table (an item x an origin with a Top-down forecast), each with the six horizons of the Top-down forecast, of Naive (last month before the origin) and of the
    actual. Same loop, same clipping and same skips as run_transferability_rolling_origin, so the mean window MAE of a division's cells is the main table's Top-down MAE exactly.
    Returns [{division, itemcode, type_key, origin, train_size, first_test_month, fc, nv, act}] (arrays of length HOLDOUT)."""
    cells = []
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)
    for code, (qty, months, type_key, div, cat) in item_series.items():
        if len(qty) != TOTAL_MONTHS or qty.sum() == 0:
            continue
        type_qty, _ = type_series[type_key]
        for origin_idx, train_size in enumerate(origins, start=1):
            train = qty[:train_size]
            test = qty[train_size:train_size + HOLDOUT]
            if len(test) < HOLDOUT:
                continue
            check_window_closed(months[train_size + HOLDOUT - 1], pull_date, min_margin_days)
            type_train = type_qty[:train_size]
            share = train.sum() / type_train.sum() if type_train.sum() > 0 else np.nan
            if pd.isna(share):
                continue
            fc = np.clip(combination_forecast(type_train, HOLDOUT, MA_WINDOWS), 0, None) * share
            if np.any(np.isnan(fc)):
                continue
            nv = np.clip(naive_forecast(train, HOLDOUT), 0, None)
            cells.append({"division": div, "itemcode": code, "type_key": type_key, "origin": origin_idx, "train_size": train_size,
                          "first_test_month": months[train_size], "fc": fc, "nv": nv, "act": test.astype(float)})
    return cells


def group_cells(type_qty: np.ndarray, months: list, pull_date, min_margin_days: int) -> list:
    """One cell per origin for a group's series (the Type series, the pilot-group block's series_own): the Type's Combination forecast (clipped), Naive and the actual, six horizons."""
    cells = []
    for origin_idx, train_size in enumerate(get_origins(TOTAL_MONTHS, HOLDOUT), start=1):
        train = type_qty[:train_size]
        test = type_qty[train_size:train_size + HOLDOUT]
        if len(test) < HOLDOUT:
            continue
        check_window_closed(months[train_size + HOLDOUT - 1], pull_date, min_margin_days)
        cells.append({"origin": origin_idx, "train_size": train_size, "first_test_month": months[train_size],
                      "fc": np.clip(combination_forecast(train, HOLDOUT, MA_WINDOWS), 0, None), "nv": np.clip(naive_forecast(train, HOLDOUT), 0, None),
                      "act": test.astype(float)})
    return cells


def relative_mae(cells: list, horizon: int = None) -> dict:
    """Relative MAE of a set of cells: the model's summed window MAE over Naive's, or (horizon = 1..6) the summed absolute errors of that horizon only. Returns
    {n_cells, mae, mae_naive, relative_mae}; relative_mae is None when Naive's errors are all 0."""
    if not cells:
        return {"n_cells": 0, "mae": None, "mae_naive": None, "relative_mae": None}
    if horizon is None:
        m = [float(np.abs(c["fc"] - c["act"]).mean()) for c in cells]
        n = [float(np.abs(c["nv"] - c["act"]).mean()) for c in cells]
    else:
        h = horizon - 1
        m = [float(abs(c["fc"][h] - c["act"][h])) for c in cells]
        n = [float(abs(c["nv"][h] - c["act"][h])) for c in cells]
    sm, sn = sum(m), sum(n)
    return {"n_cells": len(cells), "mae": sm / len(cells), "mae_naive": sn / len(cells), "relative_mae": (sm / sn) if sn > 0 else None}


def tracking_signal(errors: list) -> dict:
    """Tracking Signal = sum e / mean |e| over the points in the order given; None when every e is 0. Returns {n_points, tracking_signal}."""
    e = [float(x) for x in errors]
    mean_abs = sum(abs(x) for x in e) / len(e) if e else 0.0
    return {"n_points": len(e), "tracking_signal": (sum(e) / mean_abs) if mean_abs > 0 else None}


def horizon1_errors_by_origin(cells: list) -> dict:
    """{origin: sum of (forecast - actual) at horizon 1 over the cells} in origin order, for a division's cells or a group's single cell per origin."""
    out = {}
    for c in sorted(cells, key=lambda c: c["origin"]):
        out[c["origin"]] = out.get(c["origin"], 0.0) + float(c["fc"][0] - c["act"][0])
    return out


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
    # METRICS.md Sec.39: states the SPAN of test months pooled across the origins scored into
    # this mean (earliest origin's first test month to the last origin's last test month).
    per_division = results.groupby(["division", "approach"], as_index=False).agg(
        MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), Bias=("Bias", "mean"), MASE=("MASE", "mean"),
        n_scored=("MAE", "size"),
        first_test_month=("first_test_month", "min"), last_test_month=("last_test_month", "max"))
    # snapshot_pull_date recorded so a consuming page can show WHEN the data was pulled, never a
    # file mtime proxy (task 2cfix2, Part 3) -- same pull that produced
    # processed_all_divisions_monthly_qty.csv, read above.
    per_division["snapshot_pull_date"] = pull_date
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
