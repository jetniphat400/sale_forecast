"""Task 3 (Modeler): build and test a "Conditional" item-level forecasting policy (Top-down for
an item's share-dominant items, Direct otherwise), extending B3's single train/val/test comparison
(src/item_level_reconciliation.py: Direct / Top-down / Reconciled, scored only on the last 6-of-31
months) to ALL 7 rolling origins (src/backtest_rekeyed.py's get_origins/HOLDOUT mechanics), with
each item's share-of-Type and each Type's forecast recomputed FRESH at every origin's own training
window -- never a fixed global share.

Date key: forecast_date-keyed series (DATE_KEY below), matching B3's own choice, so Direct/
Top-down/Reconciled numbers here are directly comparable to output/summary/b3_item_level_summary.csv
et al. -- NOT re-tested against createDate here (a stated scope choice, same convention B3 itself
used and stated explicitly). IMPORTANT CAVEAT, addressed explicitly in this task's report because
it bears directly on how these numbers should be read: Task 1
(output/summary/task1_reversal_verdict.csv, output/summary/b4_per_origin_comparison.csv) found
forecast_date's apparent advantage over createDate is concentrated in ONE specific rolling-origin
window (origin 7, the exact window B3's single train/val/test split used) and does NOT generalise
across the other 6 origins, where forecast_date is often WORSE. This means forecast_date's
ABSOLUTE performance level should not be over-trusted at any single origin -- which is exactly why
this task treats rolling-origin (all 7 origins) as the PRIMARY evaluation and the single
train/val/test split as SECONDARY ONLY, per instruction, rather than picking a policy off the one
window Task 1 already flagged as unrepresentative.

Reuses (does not reimplement): src/item_level_reconciliation.py's build_item_series,
build_type_series, forecast_all_approaches, score_approaches; src/backtest_rekeyed.py's
get_origins, HOLDOUT, compute_metrics, MA_WINDOWS, TOTAL_MONTHS/TRAIN_MONTHS/VAL_MONTHS/TEST_MONTHS;
src/leakage_guard.py's check_window_closed/load_min_margin_days (same guard as Task 2, applied
here too for consistency even though this task's own custom rolling-origin loop does not go
through backtest_rekeyed.run_rolling_origin directly).

No policy choice is written to config/config.yaml, per instruction -- this is a Modeler report,
the choice belongs to the Orchestrator/human.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml
from scipy import stats as scipy_stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from backtest_rekeyed import (HOLDOUT, MA_WINDOWS, TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS,
                               VAL_MONTHS, get_origins)
from item_level_reconciliation import build_item_series, build_type_series, score_approaches
from leakage_guard import check_window_closed, load_min_margin_days
from models import combination_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task3_conditional_item_policy")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

DATE_KEY = "forecastDate"
FOCUS_ITEMS = {"EEE-F-FC-1040010002": "dominant (~48% of its Type)",
               "HS-F-99-02110": "mid-rank in its Type", "HS-F-99-0213": "mid-rank in its Type"}

# Thresholds spread across the OBSERVED share-of-type distribution (computed below, at the
# train+val=25-month window, same as B3's own share_of_type definition), chosen so each threshold
# actually classifies a different number of items as "Top-down-eligible" -- B3's single 30%
# threshold alone does not demonstrate this. Direct recomputation of B3's own methodology (this
# script) finds 7 of 113 items >=30% share at that window, not the "only 1" the task brief states
# -- flagged explicitly as a discrepancy from the brief's framing (does not change the instruction
# to test several thresholds, only the stated count).
THRESHOLDS = [0.05, 0.10, 0.20, 0.30, 0.50]


def share_of_type_at(item_series: dict, fit_end: int) -> dict:
    """Each item's share of its Type's total qty over qty[:fit_end] -- recomputed fresh for
    whatever fit_end (training window) is passed in, never a fixed global share."""
    items_by_type = {}
    for item, (qty, typ, cat) in item_series.items():
        items_by_type.setdefault(typ, []).append(item)
    shares = {}
    for typ, items in items_by_type.items():
        totals = {item: item_series[item][0][:fit_end].sum() for item in items}
        grand_total = sum(totals.values())
        for item in items:
            shares[item] = totals[item] / grand_total if grand_total > 0 else 1.0 / len(items)
    return shares


def forecast_direct_topdown(item_series: dict, type_series: dict, fit_end: int, horizon: int) -> dict:
    """Direct (per-item Combination) and Top-down (Type Combination forecast allocated by each
    item's CURRENT fit-window share) forecasts. Same recipe as
    item_level_reconciliation.forecast_all_approaches's Direct/Top-down branches, kept local here
    (not imported) only so this function can also return the shares used, needed to build the
    Conditional approach without recomputing them twice."""
    direct = {}
    for item, (qty, typ, cat) in item_series.items():
        train = qty[:fit_end]
        direct[item] = np.clip(combination_forecast(train, horizon, MA_WINDOWS), 0, None)

    type_forecast = {}
    for typ, qty in type_series.items():
        train = qty[:fit_end]
        type_forecast[typ] = np.clip(combination_forecast(train, horizon, MA_WINDOWS), 0, None)

    shares = share_of_type_at(item_series, fit_end)
    topdown = {}
    for item, (qty, typ, cat) in item_series.items():
        topdown[item] = type_forecast.get(typ, np.zeros(horizon)) * shares[item]

    return {"Direct": direct, "Top-down": topdown}, shares


def build_conditional(direct: dict, topdown: dict, shares: dict, thresholds: list) -> dict:
    out = {}
    for th in thresholds:
        out[f"Conditional_{int(th*100)}pct"] = {
            item: (topdown[item] if shares[item] >= th else direct[item]) for item in direct
        }
    return out


def run_rolling_origin_item_level(item_series: dict, type_series: dict, thresholds: list,
                                   months: list, pull_date, min_margin_days: int) -> tuple:
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)
    all_scores, all_shares = [], []
    for origin_idx, train_size in enumerate(origins, start=1):
        window_end_month = months[train_size + HOLDOUT - 1]
        check_window_closed(window_end_month, pull_date, min_margin_days)

        direct_topdown, shares = forecast_direct_topdown(item_series, type_series, train_size, HOLDOUT)
        conditional = build_conditional(direct_topdown["Direct"], direct_topdown["Top-down"], shares, thresholds)
        forecasts = {**direct_topdown, **conditional}

        scored = score_approaches(item_series, forecasts,
                                   actual_slice=slice(train_size, train_size + HOLDOUT),
                                   scale_slice=slice(0, train_size))
        scored["origin"] = origin_idx
        scored["train_size"] = train_size
        all_scores.append(scored)

        for item, share in shares.items():
            all_shares.append({"origin": origin_idx, "train_size": train_size, "itemcode": item, "share_of_type": share})

    return pd.concat(all_scores, ignore_index=True), pd.DataFrame(all_shares)


def paired_ttest(scores: pd.DataFrame, group_cols: list, value_col: str, a: str, b: str) -> dict:
    """Paired t-test (b - a), same methodology as item_level_reconciliation.py /
    strategy_gap_and_bias_report.py. `group_cols` defines the unit of pairing (e.g. ['itemcode']
    for mean-per-item-across-origins, or ['itemcode', 'origin'] for item x origin grain)."""
    pa = scores[scores["approach"] == a].groupby(group_cols, as_index=False)[value_col].mean().rename(columns={value_col: "a"})
    pb = scores[scores["approach"] == b].groupby(group_cols, as_index=False)[value_col].mean().rename(columns={value_col: "b"})
    paired = pa.merge(pb, on=group_cols)
    diff = paired["b"] - paired["a"]
    n = len(paired)
    mean_diff = diff.mean()
    se_diff = diff.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    t_stat = mean_diff / se_diff if se_diff else np.nan
    return {"a": a, "b": b, "n": n, "mean_a": pa["a"].mean(), "mean_b": pb["b"].mean(),
            "mean_diff_b_minus_a": mean_diff, "se": se_diff, "t_stat": t_stat}


if __name__ == "__main__":
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, f"processed_full_category_sales_monthly_{DATE_KEY}.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    months = sorted(monthly["year_month"].unique())
    logger.info("Using %s-keyed series (B3's date key). %d months, %s to %s. pull_date=%s, min_margin_days=%d",
                DATE_KEY, len(months), months[0], months[-1], pull_date, min_margin_days)

    item_series = build_item_series(monthly, scope)
    type_series = build_type_series(monthly)
    logger.info("%d items with full %d-month history, %d Types", len(item_series), TOTAL_MONTHS, len(type_series))

    # ============================= SHARE DISTRIBUTION (for threshold context) =============================
    shares_at_25 = share_of_type_at(item_series, TRAIN_MONTHS + VAL_MONTHS)
    shares_series = pd.Series(shares_at_25)
    print("\n" + "#" * 100)
    print("# TASK 3: CONDITIONAL ITEM-LEVEL POLICY")
    print("#" * 100)
    print(f"\nShare-of-Type distribution across {len(shares_series)} items (at train+val=25mo window, B3's own convention):")
    print(shares_series.describe())
    print(shares_series.quantile([0.5, 0.75, 0.8, 0.85, 0.9, 0.95, 0.99]))
    for th in THRESHOLDS:
        print(f"  threshold {th:.0%}: {int((shares_series >= th).sum())} of {len(shares_series)} items classified Top-down-eligible")

    # ============================= PRIMARY: ROLLING ORIGIN (all 7 origins) =============================
    print("\n" + "=" * 100)
    print("PRIMARY EVALUATION: rolling-origin, all 7 origins")
    print("=" * 100)
    ro_scores, ro_shares = run_rolling_origin_item_level(item_series, type_series, THRESHOLDS, months, pull_date, min_margin_days)
    ro_scores.to_csv(os.path.join(SUMMARY_DIR, "task3_rolling_origin_item_scores.csv"), index=False)
    ro_shares.to_csv(os.path.join(SUMMARY_DIR, "task3_rolling_origin_shares_by_origin.csv"), index=False)

    ro_summary_by_origin = ro_scores.groupby(["approach", "origin", "train_size"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    ro_summary_by_origin.to_csv(os.path.join(SUMMARY_DIR, "task3_rolling_origin_summary_by_origin.csv"), index=False)

    ro_summary_overall = ro_scores.groupby("approach", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    ro_summary_overall.to_csv(os.path.join(SUMMARY_DIR, "task3_rolling_origin_summary_overall.csv"), index=False)
    print("\n--- Mean MAE/RMSE/Bias/MASE per approach, POOLED across all 7 origins x all items ---")
    print(ro_summary_overall.round(2).to_string(index=False))

    print("\n--- Mean MAE per approach, PER ORIGIN ---")
    pivot = ro_summary_by_origin.pivot(index=["origin", "train_size"], columns="approach", values="MAE")
    print(pivot.round(1).to_string())

    # ============================= SECONDARY: TRAIN/VAL/TEST (single split, B3's original window) =============================
    print("\n" + "=" * 100)
    print("SECONDARY EVALUATION (labelled secondary per instruction): single train/val/test split "
          "(fit on 25mo, score last 6mo -- B3's original window, ALSO the exact window Task 1 flagged "
          "as the one non-representative origin)")
    print("=" * 100)
    direct_topdown_test, shares_test = forecast_direct_topdown(item_series, type_series, TRAIN_MONTHS + VAL_MONTHS, TEST_MONTHS)
    conditional_test = build_conditional(direct_topdown_test["Direct"], direct_topdown_test["Top-down"], shares_test, THRESHOLDS)
    forecasts_test = {**direct_topdown_test, **conditional_test}
    test_scores = score_approaches(item_series, forecasts_test,
                                    actual_slice=slice(TRAIN_MONTHS + VAL_MONTHS, TOTAL_MONTHS),
                                    scale_slice=slice(0, TRAIN_MONTHS + VAL_MONTHS))
    test_scores.to_csv(os.path.join(SUMMARY_DIR, "task3_single_split_test_scores.csv"), index=False)
    test_summary = test_scores.groupby("approach", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    test_summary.to_csv(os.path.join(SUMMARY_DIR, "task3_single_split_summary.csv"), index=False)
    print(test_summary.round(2).to_string(index=False))

    # ============================= SIGNIFICANCE TESTING =============================
    print("\n" + "=" * 100)
    print("SIGNIFICANCE TESTING (rolling-origin scores, PRIMARY aggregation = mean-per-item-across-"
          "origins before pairing; the 7 origins for the same item are NOT independent draws "
          "(overlapping/adjacent training windows over the same autocorrelated series), so pairing "
          "at item x origin grain would pseudo-replicate and understate the true standard error. "
          "Averaging each item's MAE across its 7 origins first, THEN pairing across the 113 items, "
          "treats the item as the true unit of replication -- more conservative, reported as PRIMARY. "
          "Item x origin pairing is ALSO computed below as a robustness/sensitivity check, flagged "
          "explicitly as likely anti-conservative (inflated |t|), not used to decide anything.)")
    print("=" * 100)

    approaches_to_test = ["Direct", "Top-down"] + [f"Conditional_{int(th*100)}pct" for th in THRESHOLDS]
    pairs = [("Direct", "Top-down")] + [("Direct", f"Conditional_{int(th*100)}pct") for th in THRESHOLDS] + \
            [("Top-down", f"Conditional_{int(th*100)}pct") for th in THRESHOLDS]

    sig_primary_rows = [paired_ttest(ro_scores, ["itemcode"], "MAE", a, b) for a, b in pairs]
    sig_primary_df = pd.DataFrame(sig_primary_rows)
    sig_primary_df.to_csv(os.path.join(SUMMARY_DIR, "task3_paired_significance_primary_per_item.csv"), index=False)
    print("\n--- PRIMARY: paired t-test, mean-per-item-across-origins (n=113 items) ---")
    print(sig_primary_df.round(3).to_string(index=False))

    sig_robust_rows = [paired_ttest(ro_scores, ["itemcode", "origin"], "MAE", a, b) for a, b in pairs]
    sig_robust_df = pd.DataFrame(sig_robust_rows)
    sig_robust_df.to_csv(os.path.join(SUMMARY_DIR, "task3_paired_significance_robustness_item_x_origin.csv"), index=False)
    print("\n--- ROBUSTNESS CHECK ONLY: paired t-test, item x origin grain (n up to 113x7=791, likely anti-conservative) ---")
    print(sig_robust_df.round(3).to_string(index=False))

    any_significant = False
    print("\n--- Verdicts (PRIMARY, |t|>2 = plausibly real) ---")
    for _, r in sig_primary_df.iterrows():
        sig = pd.notna(r["t_stat"]) and abs(r["t_stat"]) > 2
        any_significant = any_significant or sig
        print(f"  {r['a']} vs {r['b']}: mean_diff={r['mean_diff_b_minus_a']:.2f}, t={r['t_stat']:.2f} on n={int(r['n'])} -- "
              f"{'PLAUSIBLY REAL (|t|>2)' if sig else 'could be chance/noise (|t|<=2)'}")

    # ============================= FULL PER-ITEM CLASSIFICATION TABLE =============================
    print("\n" + "=" * 100)
    print("PER-ITEM CLASSIFICATION (all thresholds), share computed at train+val=25mo window")
    print("=" * 100)
    classification_rows = []
    for item, (qty, typ, cat) in item_series.items():
        row = {"itemcode": item, "type": typ, "category": cat, "share_of_type_25mo": shares_at_25[item]}
        for th in THRESHOLDS:
            row[f"classification_{int(th*100)}pct"] = "Top-down" if shares_at_25[item] >= th else "Direct"
        classification_rows.append(row)
    classification_df = pd.DataFrame(classification_rows).sort_values("share_of_type_25mo", ascending=False)

    # Add the 15 of 128 scope codes with ZERO sales history anywhere (has_any_history=False in
    # part1_category_scope_all_codes.csv) so the classification table covers the FULL 128-code
    # scope, not silently just the 113 with full history -- same "kept for the record, not
    # forecastable" convention as src/load_data.py's excluded_items_no_history.csv.
    no_history = scope[~scope["code"].isin(classification_df["itemcode"])]
    no_history_rows = [{"itemcode": r["code"], "type": r["type"], "category": r["category"],
                         "share_of_type_25mo": np.nan,
                         **{f"classification_{int(th*100)}pct": "No history (excluded from forecasting)" for th in THRESHOLDS}}
                        for _, r in no_history.iterrows()]
    classification_df = pd.concat([classification_df, pd.DataFrame(no_history_rows)], ignore_index=True)
    classification_df.to_csv(os.path.join(SUMMARY_DIR, "task3_per_item_classification.csv"), index=False)
    print(f"\nFull table written for all {len(classification_df)} of 128 scope codes ({len(no_history_rows)} have zero "
          f"sales history anywhere and are marked excluded, same convention as src/load_data.py) -- "
          f"output/summary/task3_per_item_classification.csv")
    print(classification_df.head(20).round(4).to_string(index=False))

    # ============================= FOCUS ITEMS =============================
    print("\n--- FOCUS ITEMS (rolling-origin, pooled across 7 origins) ---")
    focus_ro = ro_scores[ro_scores["itemcode"].isin(FOCUS_ITEMS.keys())].groupby(
        ["approach", "itemcode"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    focus_ro.to_csv(os.path.join(SUMMARY_DIR, "task3_focus_items_rolling_origin.csv"), index=False)
    print(focus_ro.round(2).to_string(index=False))

    # ============================= CHARTS =============================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5.5))
    plot_approaches = ["Direct", "Top-down"] + [f"Conditional_{int(th*100)}pct" for th in THRESHOLDS]
    x = np.arange(len(get_origins(TOTAL_MONTHS, HOLDOUT)))
    for appr in plot_approaches:
        sub = ro_summary_by_origin[ro_summary_by_origin["approach"] == appr].sort_values("train_size")
        ax.plot(sub["train_size"], sub["MAE"], marker="o", label=appr)
    ax.set_xlabel("Train size (months) at this origin")
    ax.set_ylabel("Mean item-level MAE")
    ax.set_title("Task 3: item-level MAE per origin, Direct vs Top-down vs Conditional thresholds (forecast_date-keyed)")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "task3_rolling_origin_approach_comparison.png"), dpi=130)
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(8, 4.5))
    ax2.hist(shares_series, bins=30, color="tab:blue")
    for th in THRESHOLDS:
        ax2.axvline(th, color="tab:red", linestyle="--", linewidth=1)
    ax2.set_title("Distribution of item share-of-Type (train+val=25mo window), with candidate thresholds")
    ax2.set_xlabel("Share of Type's train+val qty")
    ax2.set_ylabel("Number of items")
    fig2.tight_layout()
    fig2.savefig(os.path.join(CHARTS_DIR, "task3_share_distribution.png"), dpi=130)
    plt.close(fig2)

    # ============================= OVERALL VERDICT =============================
    print("\n" + "=" * 100)
    print("OVERALL VERDICT")
    print("=" * 100)
    best_ro = ro_summary_overall.loc[ro_summary_overall["MAE"].idxmin(), "approach"]
    print(f"Lowest pooled rolling-origin MAE: {best_ro} ({ro_summary_overall['MAE'].min():.2f}) -- "
          f"POINT ESTIMATE ONLY, see significance tests above for whether this is distinguishable from chance.")
    if not any_significant:
        print("NO pairwise comparison (Direct vs Top-down, Direct vs any Conditional threshold, Top-down vs any "
              "Conditional threshold) clears |t|>2 on the PRIMARY (mean-per-item-across-origins) test. "
              "STATED DIRECTLY, PER INSTRUCTION: no Conditional threshold earns its added complexity over the "
              "simpler pure Direct or pure Top-down alternatives with statistical confidence in this rolling-"
              "origin evaluation -- no policy is recommended here.")
    else:
        print("At least one pairwise comparison clears |t|>2 -- see the verdict list above for which.")

    print("\nOutputs: output/summary/task3_rolling_origin_item_scores.csv, "
          "task3_rolling_origin_shares_by_origin.csv, task3_rolling_origin_summary_by_origin.csv, "
          "task3_rolling_origin_summary_overall.csv, task3_single_split_test_scores.csv, "
          "task3_single_split_summary.csv, task3_paired_significance_primary_per_item.csv, "
          "task3_paired_significance_robustness_item_x_origin.csv, task3_per_item_classification.csv, "
          "task3_focus_items_rolling_origin.csv")
    print("Charts: output/charts/task3_rolling_origin_approach_comparison.png, task3_share_distribution.png")
