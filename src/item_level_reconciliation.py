"""Phase B, task B3: how aggregate levels should support item-level forecasting.

Compares three approaches, all measured at ITEM level on the held-out test set (months 26-31 of
31, i.e. TRAIN=19+VAL=6 to fit, TEST=6 to score — identical split to the rest of Phase B):

  - Direct: Combination forecast applied to each item's own series independently.
  - Top-down: Combination forecast at Type level, allocated to items by each item's historical
    share of its Type's total qty over the fitting window (train+val, 25 months).
  - Reconciled: each item forecast directly (= the Direct forecast), then scaled per Type per
    month so the items in a Type sum exactly to that Type's own Combination forecast for that
    month (a standard proportional top-down reconciliation of bottom-up forecasts).

Uses the forecast_date-keyed series (output/data/processed_full_category_sales_monthly_
forecastDate.csv) — Phase B1 found this is the field inventory planning should be keyed on, so
this is evaluated on what is now recommended as the correct series, not the old createDate one.
This is a stated scope choice, not re-tested against createDate here (flagged as not done, per
the stopping rule, rather than silently expanding scope further).

Also computes each approach's VALIDATION-stage forecast (fit on train only, 19 months, predicting
val, 6 months) so a validation-to-test gap can be reported per approach, and runs the same paired
t-test methodology as src/strategy_gap_and_bias_report.py (same series, two approaches, paired by
item) to test whether differences are statistically distinguishable.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import MA_WINDOWS, TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS, VAL_MONTHS, compute_metrics
from models import combination_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("item_level_reconciliation")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

DATE_KEY = "forecastDate"
FOCUS_ITEMS = {"EEE-F-FC-1040010002": "dominant (~60% of its Type's value)",
               "HS-F-99-02110": "mid-rank in its Type", "HS-F-99-0213": "mid-rank in its Type"}


def build_item_series(monthly: pd.DataFrame, scope: pd.DataFrame) -> dict:
    """{itemcode: (qty_array, type, category)} for items with a full TOTAL_MONTHS history."""
    out = {}
    items_with_history = set(monthly["itemcode"].unique())
    for _, row in scope.iterrows():
        code = row["code"]
        if code not in items_with_history:
            continue
        g = monthly[monthly["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        if len(qty) == TOTAL_MONTHS:
            out[code] = (qty, row["type"], row["category"])
    return out


def build_type_series(monthly: pd.DataFrame) -> dict:
    out = {}
    for typ, g in monthly.groupby("type"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        if len(qty) == TOTAL_MONTHS:
            out[typ] = qty
    return out


def forecast_all_approaches(item_series: dict, type_series: dict, fit_end: int, horizon: int) -> dict:
    """Returns {approach: {itemcode: forecast_array}} for the three approaches, fitting on
    qty[:fit_end] and forecasting `horizon` periods ahead. fit_end=TRAIN_MONTHS for the
    validation stage, fit_end=TRAIN_MONTHS+VAL_MONTHS for the test stage."""
    # Direct: per-item combination forecast
    direct = {}
    for item, (qty, typ, cat) in item_series.items():
        train = qty[:fit_end]
        direct[item] = np.clip(combination_forecast(train, horizon, MA_WINDOWS), 0, None)

    # Type-level combination forecast (needed for Top-down and Reconciled)
    type_forecast = {}
    for typ, qty in type_series.items():
        train = qty[:fit_end]
        type_forecast[typ] = np.clip(combination_forecast(train, horizon, MA_WINDOWS), 0, None)

    # Top-down: allocate Type forecast to items by historical share over the FITTING window
    topdown = {}
    items_by_type = {}
    for item, (qty, typ, cat) in item_series.items():
        items_by_type.setdefault(typ, []).append(item)
    for typ, items in items_by_type.items():
        totals = {item: item_series[item][0][:fit_end].sum() for item in items}
        grand_total = sum(totals.values())
        for item in items:
            share = totals[item] / grand_total if grand_total > 0 else 1.0 / len(items)
            topdown[item] = type_forecast.get(typ, np.zeros(horizon)) * share

    # Reconciled: Direct forecasts, rescaled per Type per period to sum to the Type forecast
    reconciled = {}
    for typ, items in items_by_type.items():
        direct_sum = np.sum([direct[item] for item in items], axis=0)
        type_fc = type_forecast.get(typ, np.zeros(horizon))
        with np.errstate(divide="ignore", invalid="ignore"):
            scale = np.where(direct_sum > 0, type_fc / direct_sum, 1.0)
        for item in items:
            reconciled[item] = direct[item] * scale

    return {"Direct": direct, "Top-down": topdown, "Reconciled": reconciled}


def score_approaches(item_series: dict, forecasts_by_stage: dict, actual_slice: slice, scale_slice: slice) -> pd.DataFrame:
    rows = []
    for approach, per_item_fc in forecasts_by_stage.items():
        for item, fc in per_item_fc.items():
            qty, typ, cat = item_series[item]
            actual = qty[actual_slice]
            scale_series = qty[scale_slice]
            m = compute_metrics(actual, fc, scale_series)
            rows.append({"approach": approach, "itemcode": item, "type": typ, "category": cat, **m})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, f"processed_full_category_sales_monthly_{DATE_KEY}.csv"))
    logger.info("Using the %s-keyed series (Phase B1's recommended key) — not re-tested against "
                "createDate in this task, a stated scope choice.", DATE_KEY)

    item_series = build_item_series(monthly, scope)
    type_series = build_type_series(monthly)
    logger.info("%d items with full %d-month history, across %d Types", len(item_series), TOTAL_MONTHS, len(type_series))

    # ---- Test stage: fit on train+val (25 months), forecast/score test (6 months) ----
    fc_test = forecast_all_approaches(item_series, type_series, TRAIN_MONTHS + VAL_MONTHS, TEST_MONTHS)
    test_scores = score_approaches(item_series, fc_test,
                                    actual_slice=slice(TRAIN_MONTHS + VAL_MONTHS, TOTAL_MONTHS),
                                    scale_slice=slice(0, TRAIN_MONTHS + VAL_MONTHS))
    test_scores.to_csv(os.path.join(SUMMARY_DIR, "b3_item_level_test_scores.csv"), index=False)

    # ---- Validation stage: fit on train only (19 months), forecast/score val (6 months) ----
    fc_val = forecast_all_approaches(item_series, type_series, TRAIN_MONTHS, VAL_MONTHS)
    val_scores = score_approaches(item_series, fc_val,
                                   actual_slice=slice(TRAIN_MONTHS, TRAIN_MONTHS + VAL_MONTHS),
                                   scale_slice=slice(0, TRAIN_MONTHS))
    val_scores.to_csv(os.path.join(SUMMARY_DIR, "b3_item_level_val_scores.csv"), index=False)

    # ---- Summary: mean MAE/RMSE/Bias/MASE per approach, item level ----
    summary = test_scores.groupby("approach", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    summary.to_csv(os.path.join(SUMMARY_DIR, "b3_item_level_summary.csv"), index=False)

    gap_rows = []
    for approach in ["Direct", "Top-down", "Reconciled"]:
        v = val_scores[val_scores["approach"] == approach]["MAE"].mean()
        t = test_scores[test_scores["approach"] == approach]["MAE"].mean()
        gap_rows.append({"approach": approach, "val_MAE": v, "test_MAE": t, "gap": t - v,
                          "gap_pct": 100 * (t - v) / v if v else np.nan})
    gap_df = pd.DataFrame(gap_rows)
    gap_df.to_csv(os.path.join(SUMMARY_DIR, "b3_val_test_gap.csv"), index=False)

    # ---- Paired significance test (same series/item, two approaches — same methodology as
    # src/strategy_gap_and_bias_report.py's winner-margin paired t-test) ----
    pairs = [("Direct", "Top-down"), ("Direct", "Reconciled"), ("Top-down", "Reconciled")]
    sig_rows = []
    for a, b in pairs:
        pa = test_scores[test_scores["approach"] == a][["itemcode", "MAE"]].rename(columns={"MAE": "MAE_a"})
        pb = test_scores[test_scores["approach"] == b][["itemcode", "MAE"]].rename(columns={"MAE": "MAE_b"})
        paired = pa.merge(pb, on="itemcode")
        paired["diff"] = paired["MAE_b"] - paired["MAE_a"]
        n = len(paired)
        mean_diff = paired["diff"].mean()
        se_diff = paired["diff"].std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
        t_stat = mean_diff / se_diff if se_diff else np.nan
        sig_rows.append({"approach_a": a, "approach_b": b, "n_paired_items": n,
                          "mean_MAE_a": pa["MAE_a"].mean(), "mean_MAE_b": pb["MAE_b"].mean(),
                          "mean_diff_b_minus_a": mean_diff, "paired_se": se_diff, "paired_t_stat": t_stat})
    sig_df = pd.DataFrame(sig_rows)
    sig_df.to_csv(os.path.join(SUMMARY_DIR, "b3_paired_significance.csv"), index=False)

    # ---- By item's share-of-type rank (dominant vs minor items behave differently?) ----
    share_rows = []
    for item, (qty, typ, cat) in item_series.items():
        type_total = sum(item_series[i][0][:TRAIN_MONTHS + VAL_MONTHS].sum() for i, (q, t, c) in item_series.items() if t == typ)
        item_total = qty[:TRAIN_MONTHS + VAL_MONTHS].sum()
        share_rows.append({"itemcode": item, "type": typ, "share_of_type": item_total / type_total if type_total else np.nan})
    share_df = pd.DataFrame(share_rows)
    test_scores_with_share = test_scores.merge(share_df, on=["itemcode", "type"])
    test_scores_with_share["dominant_item"] = test_scores_with_share["share_of_type"] >= 0.30
    by_dominance = test_scores_with_share.groupby(["approach", "dominant_item"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
    by_dominance.to_csv(os.path.join(SUMMARY_DIR, "b3_by_dominance.csv"), index=False)

    # ---- Focus items individually ----
    focus_df = test_scores[test_scores["itemcode"].isin(FOCUS_ITEMS.keys())].merge(share_df, on=["itemcode", "type"])
    focus_df.to_csv(os.path.join(SUMMARY_DIR, "b3_focus_items.csv"), index=False)

    # ============================= CHARTS =============================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for item in FOCUS_ITEMS:
        if item not in item_series:
            continue
        qty, typ, cat = item_series[item]
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(range(TOTAL_MONTHS), qty, label="Actual", color="black", linewidth=1.5)
        colors = {"Direct": "tab:red", "Top-down": "tab:blue", "Reconciled": "tab:green"}
        for approach, per_item_fc in fc_test.items():
            fc = per_item_fc[item]
            ax.plot(range(TRAIN_MONTHS + VAL_MONTHS, TOTAL_MONTHS), fc, label=approach,
                     color=colors[approach], marker="o", linewidth=1.5)
        ax.axvline(TRAIN_MONTHS + VAL_MONTHS, color="gray", linestyle="--", linewidth=1)
        ax.set_title(f"{item} ({FOCUS_ITEMS[item]}, Type={typ})\nDirect vs Top-down vs Reconciled, forecast_date-keyed")
        ax.set_xlabel("Month index (0-30)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, f"b3_{item.replace('/', '_')}_approach_comparison.png"), dpi=120)
        plt.close(fig)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 92)
    print("# B3: DIRECT vs TOP-DOWN vs RECONCILED — item-level test-set comparison")
    print("#" * 92)
    print(f"\nDate key used: {DATE_KEY} (Phase B1's recommendation). {len(item_series)} items scored, "
          f"across {len(type_series)} Types.")

    print("\n--- MEAN MAE/RMSE/Bias/MASE per approach (item level, test set) ---")
    print(summary.round(2).to_string(index=False))

    print("\n--- VALIDATION-TO-TEST GAP per approach ---")
    print(gap_df.round(2).to_string(index=False))

    print("\n--- PAIRED SIGNIFICANCE TEST (same methodology as the prior winner-margin check) ---")
    print(sig_df.round(3).to_string(index=False))
    for _, r in sig_df.iterrows():
        t = r["paired_t_stat"]
        verdict = "plausibly a real, consistent difference (|t|>2)" if pd.notna(t) and abs(t) > 2 else "could plausibly be chance/noise (|t|<=2)"
        print(f"  {r['approach_a']} vs {r['approach_b']}: paired t={t:.2f} on {int(r['n_paired_items'])} items — {verdict}")

    print("\n--- BY ITEM DOMINANCE WITHIN ITS TYPE (share >= 30% of Type's train+val qty = 'dominant') ---")
    print(by_dominance.round(2).to_string(index=False))

    print("\n--- FOCUS ITEMS INDIVIDUALLY ---")
    print(focus_df[["approach", "itemcode", "type", "share_of_type", "MAE", "RMSE", "Bias", "MASE"]].round(3).to_string(index=False))

    best_overall = summary.loc[summary["MAE"].idxmin(), "approach"]
    print(f"\nBest by mean item-level MAE: {best_overall}.")
    print("See the assistant's chat message for the full synthesis of what this does and does not support.")

    print("\nOutputs: output/summary/b3_item_level_test_scores.csv, b3_item_level_val_scores.csv, "
          "b3_item_level_summary.csv, b3_val_test_gap.csv, b3_paired_significance.csv, b3_by_dominance.csv, "
          "b3_focus_items.csv")
    print("Charts: output/charts/b3_<item>_approach_comparison.png")
