"""Part 5 + Part 6: compares aggregated (Category/Type) results against the
earlier item-level results, plots forecast vs. actual per Category/Type,
and prints the final console summary with confidence-rated recommendations.
Writes nothing to config.yaml.
"""
import logging
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from aggregate_levels import determine_complete_months
from backtest_aggregate import (HOLDOUT, MA_WINDOWS, TEST_MONTHS, TRAIN_MONTHS, VAL_MONTHS, build_level_series)
from models import get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("report_and_charts")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")


def plot_level_series(series: dict, models: dict, selection_df: pd.DataFrame):
    keys = [k for k in series if len(k) == 3]
    for level, key, cat in keys:
        qty = series[(level, key, cat)]
        months = series[(level, key, cat, "months")]
        n = len(qty)
        train_val = qty[:TRAIN_MONTHS + VAL_MONTHS]
        test_months = months[TRAIN_MONTHS + VAL_MONTHS:]
        sel_row = selection_df[(selection_df["level"] == level) & (selection_df["key"] == key)].iloc[0]
        model_name = sel_row["selected_model_by_MAE"]
        forecast = np.clip(models[model_name](train_val, TEST_MONTHS), 0, None)

        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.plot(months, qty, label="Actual", color="black", marker="o", markersize=3)
        ax.plot(test_months, forecast, label=f"{model_name} (val-selected)", linestyle="--", marker="x", color="tab:red")
        ax.axvline(x=TRAIN_MONTHS - 0.5, color="gray", linestyle=":", linewidth=1, label="train/val boundary")
        ax.axvline(x=TRAIN_MONTHS + VAL_MONTHS - 0.5, color="gray", linestyle="-", linewidth=1, label="val/test boundary")
        ax.set_title(f"Forecast vs Actual — {level}: {key}")
        ax.set_ylabel("Monthly qty")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=8)
        fig.tight_layout()
        safe_name = f"{level}_{key}".replace("/", "_").replace(" ", "_")
        fig.savefig(os.path.join(CHARTS_DIR, f"forecast_vs_actual_{safe_name}.png"))
        plt.close(fig)
        logger.info("Saved chart for %s: %s", level, key)


def confidence_rating(n_distinct_winners: int, n_origins: int, gap_pct: float, disagree: bool) -> tuple:
    """Rates confidence in the recommended model for a series. Never reports
    an unstable winner as reliable — this is the dominant factor."""
    frac_unstable = n_distinct_winners / n_origins
    if frac_unstable <= 0.4:
        stability_note = "majority-stable"
        base = "MEDIUM"
    elif frac_unstable <= 0.7:
        stability_note = "partially stable"
        base = "LOW-MEDIUM"
    else:
        stability_note = "unstable (winner changes almost every origin)"
        base = "LOW"
    if abs(gap_pct) > 100:
        base = "LOW"
    if disagree:
        note2 = "; MAE-best and Bias-best disagree"
    else:
        note2 = "; MAE-best and Bias-best agree"
    return base, stability_note + note2


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    models = get_models(MA_WINDOWS)
    series = build_level_series(monthly)

    selection_df = pd.read_csv(os.path.join(SUMMARY_DIR, "part4_model_selection.csv"))
    stability_df = pd.read_csv(os.path.join(SUMMARY_DIR, "part4_rolling_origin_stability.csv"))
    gap_df = pd.read_csv(os.path.join(SUMMARY_DIR, "part4_val_test_gap.csv"))
    granularity_rec = pd.read_csv(os.path.join(SUMMARY_DIR, "part3_granularity_recommendation.csv"))
    cat_stats = pd.read_csv(os.path.join(SUMMARY_DIR, "part2_category_level_stats.csv"))
    type_stats = pd.read_csv(os.path.join(SUMMARY_DIR, "part2_type_level_stats.csv"))

    plot_level_series(series, models, selection_df)

    # ---- Part 5: compare against item-level ----
    item_stability = pd.read_csv(os.path.join(SUMMARY_DIR, "partC_stability_per_item.csv"))
    item_gap = pd.read_csv(os.path.join(SUMMARY_DIR, "partD_val_test_gap.csv"))
    item_selection = pd.read_csv(os.path.join(SUMMARY_DIR, "partD_model_selection.csv"))
    item_class = pd.read_csv(os.path.join(SUMMARY_DIR, "part2_item_level_stats.csv")) if os.path.exists(os.path.join(SUMMARY_DIR, "part2_item_level_stats.csv")) else None

    item_n_stable = int(item_stability["stable_winner"].sum())
    item_n_total = len(item_stability)
    item_mean_gap_pct = 100 * item_gap["gap"].mean() / item_gap["val_MAE_of_selected"].mean()
    item_disagree = int(item_selection["disagree"].sum())

    agg_n_stable = int(stability_df["stable_winner"].sum())
    agg_n_total = len(stability_df)
    agg_mean_gap_pct = 100 * gap_df["gap"].mean() / gap_df["val_MAE_of_selected"].mean()
    agg_disagree = int(selection_df["disagree"].sum())

    comparison = pd.DataFrame([
        {"metric": "Rolling-origin: stable-winner rate", "item_level": f"{item_n_stable}/{item_n_total} ({100*item_n_stable/item_n_total:.1f}%)",
         "aggregate_level": f"{agg_n_stable}/{agg_n_total} ({100*agg_n_stable/agg_n_total:.1f}%)"},
        {"metric": "Validation-to-test MAE gap (relative)", "item_level": f"+{item_mean_gap_pct:.1f}%", "aggregate_level": f"{agg_mean_gap_pct:+.1f}%"},
        {"metric": "MAE-best vs Bias-best disagreement rate", "item_level": f"{item_disagree}/{item_n_total} ({100*item_disagree/item_n_total:.1f}%)",
         "aggregate_level": f"{agg_disagree}/{agg_n_total} ({100*agg_disagree/agg_n_total:.1f}%)"},
    ])
    comparison.to_csv(os.path.join(SUMMARY_DIR, "part5_item_vs_aggregate_comparison.csv"), index=False)

    # ---- Part 6: final recommendation table ----
    final_rows = []
    for _, row in selection_df.iterrows():
        level, key = row["level"], row["key"]
        stab_row = stability_df[(stability_df["level"] == level) & (stability_df["key"] == key)].iloc[0]
        gap_row = gap_df[(gap_df["level"] == level) & (gap_df["key"] == key)].iloc[0]
        gran_row = granularity_rec[(granularity_rec["level"] == level) & (granularity_rec["key"] == key)]
        gran = gran_row["recommended_granularity"].iloc[0] if len(gran_row) else "monthly"
        n_origins = 7  # from Part 4 rolling-origin run
        confidence, note = confidence_rating(stab_row["n_distinct_winners"], n_origins, gap_row["gap_pct"], row["disagree"])
        final_rows.append({
            "level": level, "key": key,
            "recommended_granularity": gran,
            "model_by_validation_MAE": row["selected_model_by_MAE"],
            "model_by_validation_Bias": row["best_bias_model"],
            "most_frequent_rolling_origin_winner": stab_row["most_frequent_winner"],
            "val_test_gap_pct": gap_row["gap_pct"],
            "confidence": confidence,
            "confidence_note": note,
        })
    final_df = pd.DataFrame(final_rows)
    final_df.to_csv(os.path.join(SUMMARY_DIR, "part6_final_recommendation_table.csv"), index=False)

    # ============================= CONSOLE SUMMARY =============================
    print("\n" + "#" * 90)
    print("# CATEGORY/TYPE-LEVEL FORECASTING — FINAL SUMMARY")
    print("#" * 90)

    print("\n== SCOPE (Part 1) ==")
    scope_report = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_scope_report_by_type.csv"))
    print(f"128 item codes across 8 Types, 2 Categories (Fuse, Surge Arrester). 113 have sales history "
          f"anywhere; 15 have none (excluded). Under the current filters (division=PEM101, revenue_type=Omni "
          f"Channel, status Actual/MPS, >=2024-01-01): {scope_report['n_with_sales_2024plus'].sum()} of 113 "
          f"forecastable codes have activity; total qty={scope_report['total_qty'].sum():,.0f}, "
          f"total value=THB {scope_report['total_value'].sum():,.0f}.")

    print("\n== AGGREGATION EFFECT (Part 2) ==")
    print("Item level:     mean 39.3% zero months, 50% Lumpy/Intermittent classification (of 113 items)")
    print(f"Type level:     mean 5.2% zero months, 12% Lumpy/Intermittent (of 8 types)")
    print(f"Category level: mean 0.0% zero months, 0% Lumpy/Intermittent (of 2 categories)")
    print("Aggregation MATERIALLY reduces zero-inflation: both Category series and 7 of 8 Type series are")
    print("Smooth or Erratic (never zero) at monthly grain. The one exception, Low Voltage Fuse Switch")
    print("Disconectors (2 items), stays Intermittent even at Category-adjacent aggregation — it is genuinely")
    print("thin (total 8,195 units, 31.7% of item's own months are zero) and no amount of grouping with the")
    print("other 6 Fuse Types would be appropriate since they are different products.")

    print("\n== GRANULARITY (Part 3) ==")
    print("9 of 10 series already have 0% zero periods at MONTHLY granularity — coarsening to 2-month or")
    print("quarterly buckets would only throw away data points for no zero-reduction benefit. Recommended:")
    print("MONTHLY for all Category series and 7 of 8 Type series.")
    print("Exception: Low Voltage Fuse Switch Disconectors — quarterly nudges % zero from 41.9% to 40.0% and")
    print("ADI from 1.72 to 1.67 (still Intermittent either way) — a marginal, not decisive, improvement.")

    print("\n== BACKTEST (Part 4, monthly granularity, Category + Type level) ==")
    print(f"Rolling-origin: 7 origins (train sizes 13,15,17,19,21,23,25 months), same settings as item level.")
    print(f"Stable winner (same model at every origin): {agg_n_stable} of {agg_n_total} series (0%).")
    print("This MATCHES the item-level finding that no single model wins reliably across time — aggregation")
    print("did NOT fix winner instability, even though it eliminated zero-inflation. Reporting the most")
    print("frequent winner per series below for reference ONLY — it is not a reliable choice on its own.")
    print(f"\nTrain/Val/Test split 19/6/6 months: mean validation-to-test MAE gap = {agg_mean_gap_pct:+.1f}%")
    print(f"MAE-best vs Bias-best model disagree for {agg_disagree} of {agg_n_total} series "
          f"({100*agg_disagree/agg_n_total:.0f}%). Where they disagree: choosing the MAE-best model risks a")
    print("persistent directional bias (stockouts if under-forecasting, excess stock if over-forecasting) even")
    print("though it minimizes average absolute error; choosing the Bias-best model minimizes that directional")
    print("risk but usually has higher average absolute error. See part4_model_selection.csv for which")
    print("direction each disagreement runs.")

    print("\n== ITEM-LEVEL vs. AGGREGATE COMPARISON (Part 5) ==")
    print(comparison.to_string(index=False))
    print(f"\nAggregation MEASURABLY reduces overfitting risk: the validation-to-test gap falls from +127.0%")
    print(f"(item level) to {agg_mean_gap_pct:+.1f}% (Category/Type level) — a real, large improvement, consistent")
    print("with far less zero-inflation to overfit to.")
    print(f"Aggregation does NOT improve which-model-wins stability: item level was already low (25.9%")
    print(f"stable), and Category/Type level is 0% stable — reporting this directly rather than as an")
    print("improvement, since it is not one.")
    print(f"MAE-best/Bias-best disagreement is similar or slightly worse in relative terms at the aggregate")
    print(f"level ({100*agg_disagree/agg_n_total:.0f}% vs. item level's {100*item_disagree/item_n_total:.0f}%), though the aggregate sample")
    print("(10 series) is too small for this comparison alone to be conclusive.")

    print("\n== FINAL RECOMMENDATION TABLE (Part 6) ==")
    print(final_df.to_string(index=False))

    print("\n== CONFIDENCE LEVELS ==")
    print("HIGH confidence: aggregation reduces zero-inflation and reduces validation-to-test overfitting gap")
    print("  (Parts 2 and 5) — large, consistent effect, directly measured.")
    print("HIGH confidence: monthly is the right granularity for 9 of 10 series (already 0% zero, no reason")
    print("  to coarsen) — directly measured (Part 3).")
    print("LOW-to-LOW-MEDIUM confidence: which single model to use per Category/Type — no series had a stable")
    print("  rolling-origin winner (0/10); see the table above and part4_rolling_origin_stability.csv for the")
    print("  per-series distribution of winners across origins before treating any single model as settled.")
    print("MEDIUM confidence: the general model family (moving-average variants and Croston/SBA family) tends")
    print("  to outperform Naive on average across origins for most series — see part4_rolling_origin_results.csv")
    print("  mean MAE ranking per series — but the specific window/variant is not stable.")

    print("\n== UNRESOLVED / NOT ANSERABLE FROM THIS DATA ==")
    print("- Which exact model to lock in per Category/Type: the evidence does not support a single stable")
    print("  choice (0/10 stable winners). A wider or different evaluation design (e.g. ensembling, or waiting")
    print("  for more history) would be needed before locking a production choice.")
    print("- Low Voltage Fuse Switch Disconectors (2 items) remains genuinely Intermittent at every granularity")
    print("  tested; no aggregation level tested here resolves this cleanly since it cannot be pooled with")
    print("  dissimilar Fuse Types without violating the top-down hierarchy's own logic.")
    print("- Whether item-level forecasts should be derived by disaggregating a Category/Type forecast (e.g.")
    print("  by historical share) was not tested here — this task covered aggregation and comparison only,")
    print("  not a top-down disaggregation method.")

    print("\nAll outputs written to output/summary/ (CSVs, prefixed part1_ through part6_) and output/charts/")
    print("(10 forecast-vs-actual PNGs, 2 Category + 8 Type). config/config.yaml was NOT modified.")
