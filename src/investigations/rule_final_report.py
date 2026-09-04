"""Rule-based selection task, Part 6: final report — combines Parts 1-5 into
one table per level/series, produces charts, and prints the console summary
with confidence levels. Writes nothing to config.yaml.
"""
import logging
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from evaluate_strategies import TEST_MONTHS, TRAIN_MONTHS, VAL_MONTHS
from feature_analysis import build_all_series, determine_complete_months
from models import get_extended_models, get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("rule_final_report")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")
MA_WINDOWS = [3, 6, 12]


def plot_category_type_series(series: dict, selections: pd.DataFrame):
    base_models = get_models(MA_WINDOWS)
    ext_models = get_extended_models(MA_WINDOWS)
    for (level, key, cat), (qty, months) in series.items():
        if level not in ("Category", "Type"):
            continue
        train_val = qty[:TRAIN_MONTHS + VAL_MONTHS]
        test_months = months[TRAIN_MONTHS + VAL_MONTHS:]
        combo_fc = np.mean([np.clip(fn(train_val, TEST_MONTHS), 0, None) for fn in base_models.values()], axis=0)
        sel_row = selections[(selections["level"] == level) & (selections["key"] == key)]
        rule_model = sel_row.iloc[0]["KH_model"] if len(sel_row) else "Naive"
        emp_model = sel_row.iloc[0]["empirical_model"] if len(sel_row) else "Naive"
        rule_fc = np.clip(ext_models.get(rule_model, ext_models["Naive"])(train_val, TEST_MONTHS), 0, None)
        emp_fc = np.clip(base_models.get(emp_model, base_models["Naive"])(train_val, TEST_MONTHS), 0, None)

        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.plot(months, qty, label="Actual", color="black", marker="o", markersize=3)
        ax.plot(test_months, combo_fc, label="Combination", linestyle="--", marker="s", color="tab:green")
        ax.plot(test_months, rule_fc, label=f"Rule-KH ({rule_model})", linestyle="--", marker="^", color="tab:blue")
        ax.plot(test_months, emp_fc, label=f"Empirical ({emp_model})", linestyle="--", marker="x", color="tab:red")
        ax.axvline(x=TRAIN_MONTHS + VAL_MONTHS - 0.5, color="gray", linestyle=":", linewidth=1)
        ax.set_title(f"Strategy comparison — {level}: {key}")
        ax.set_ylabel("Monthly qty")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=8)
        fig.tight_layout()
        safe_name = f"{level}_{key}".replace("/", "_").replace(" ", "_")
        fig.savefig(os.path.join(CHARTS_DIR, f"rule_strategy_comparison_{safe_name}.png"))
        plt.close(fig)
        logger.info("Saved chart for %s: %s", level, key)


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    series = build_all_series(monthly, scope)

    features_df = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part1_series_features_full_history.csv"))
    stability_p2 = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part2_stability_summary.csv"))
    assignments = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part3_model_assignments.csv"))
    test_results = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_test_results_per_series.csv"))
    selections = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_model_selections.csv"))
    summary_strategy = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_summary_by_level_strategy.csv"))
    origin_stability = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part5_stability_summary.csv"))
    mae_bias = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_mae_vs_bias_best.csv"))

    plot_category_type_series(series, selections)

    # ---- Final combined table (Category + Type; item-level kept in its own CSV, too large to print) ----
    final_rows = []
    for level in ["Category", "Type"]:
        feat_sub = features_df[features_df["level"] == level]
        for _, f in feat_sub.iterrows():
            key = f["key"]
            assign = assignments[(assignments["level"] == level) & (assignments["key"] == key)]
            test_sub = test_results[(test_results["level"] == level) & (test_results["key"] == key)]
            best_strategy = test_sub.loc[test_sub["MAE"].idxmin(), "strategy"] if len(test_sub) else None
            best_mae = test_sub["MAE"].min() if len(test_sub) else None
            row = {
                "level": level, "key": key, "n_periods": f["n_periods"], "pct_zero": f["pct_zero"],
                "ADI": f["ADI"], "CV2": f["CV2"], "classification": f["classification"],
                "trend_direction": f["trend_direction"], "level_shift_detected": f["level_shift_detected"],
                "SBC_model": assign.iloc[0]["SBC_final"] if len(assign) else None,
                "KH_model": assign.iloc[0]["KH_final"] if len(assign) else None,
                "PK_model": assign.iloc[0]["PK_final"] if len(assign) else None,
                "best_test_strategy": best_strategy, "best_test_MAE": round(best_mae, 1) if best_mae else None,
            }
            final_rows.append(row)
    final_df = pd.DataFrame(final_rows)
    final_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part6_final_table_category_type.csv"), index=False)

    item_final = features_df[features_df["level"] == "Item"].merge(
        assignments[["level", "key", "SBC_final", "KH_final", "PK_final"]], on=["level", "key"], how="left"
    )
    item_final.to_csv(os.path.join(SUMMARY_DIR, "rule_part6_final_table_item.csv"), index=False)

    # ============================= CONSOLE SUMMARY =============================
    print("\n" + "#" * 92)
    print("# RULE-BASED MODEL SELECTION — FINAL SUMMARY")
    print("#" * 92)

    print("\n== SCOPE ==")
    print("138 series: 2 Category, 8 Type, 128 Item (of which 16 items have zero sales history — 'NoSale',")
    print("no model applies; 122 series carry the analysis through).")

    print("\n== PART 1-2: CHARACTERISTICS & STABILITY ==")
    print("All series have 31 months of history (2024-01 to 2026-07, latest month excluded as partial).")
    print("Classification is STABLE (same SBC quadrant across first-12/first-24/full-history windows) for:")
    print("  Category: 2/2 (100%)   Type: 7/8 (87.5%)   Item: 83/128 (64.8%)")
    print("Both Category series and 7 of 8 Types are 'Smooth' with an Increasing trend (Category level) or")
    print("mixed trend (Type level) — see rule_part1_series_features_full_history.csv for full detail.")
    print("Month-of-year strength is reported as an OBSERVATION ONLY — 2 complete years cannot confirm it.")

    print("\n== PART 3: RULE-SET MODEL ASSIGNMENTS ==")
    print("SBC (Syntetos-Boylan-Croston 2005): Croston for Smooth only, SBA otherwise (VERIFIED against the")
    print("primary source — note this is the opposite of what an earlier draft of this task's instructions")
    print("stated; the primary source was checked and the user confirmed to follow it).")
    print("KH (Kostenko-Hyndman 2006): exact non-linear boundary, using a per-series fitted interval-smoothing")
    print("parameter alpha. PK (Petropoulos-Kourentzes 2015): same boundary, SES override when ADI<=1.")
    print("Extended layer (our own addition, not from the papers): Naive when history <24 months or")
    print("classification is unstable; SES/Holt (by trend) for the Smooth quadrant, generalising P&K's ADI<=1")
    print("principle. NOTE: because Smooth is exactly where SBC/KH assign Croston, the extended layer means")
    print("plain 'Croston' never survives as a final recommendation under any rule set once layered — see")
    print("rule_part3_model_assignments.csv's *_base columns for the un-layered literature rule if needed.")
    print("SBC and KH's BASE rule disagree (Croston vs SBA) on only 4 of 122 series (3.3%) — the corrected")
    print("boundary rarely changes the outcome in this dataset.")

    print("\n== PART 4: STRATEGY COMPARISON ON THE TEST SET ==")
    print(summary_strategy.sort_values(["level", "MASE"]).to_string(index=False))
    print("\nCOMBINATION forecasting has the best (lowest) MAE and RMSE at ALL THREE levels, and the best MASE")
    print("at Category and Type level. Rule-based selection (SBC/KH/PK, nearly identical to each other) does")
    print("NOT outperform Combination, and is WORSE than plain Naive on MASE at Type and Item level. This is")
    print("stated directly, not softened: rule-based selection does not win this comparison.")
    for level in ["Category", "Type", "Item"]:
        sub = mae_bias[mae_bias["level"] == level]
        n_dis = sub["disagree"].sum()
        print(f"MAE-best vs Bias-best strategy disagree: {level} {n_dis}/{len(sub)} ({100*n_dis/len(sub):.1f}%)")
    print("Where they disagree, choosing the MAE-best strategy risks a persistent directional bias (stockouts")
    print("if under-forecasting, excess stock if over-forecasting); the Bias-best strategy trades higher average")
    print("error for less directional risk. See rule_part4_mae_vs_bias_best.csv for which strategy wins each way.")

    print("\n== PART 5: RULE STABILITY ACROSS 7 ROLLING ORIGINS ==")
    print("The BASE (un-gated) classification-driven choice is genuinely much more stable than empirical")
    print("selection was in prior work on this project:")
    for rule in ["SBC", "KH", "PK"]:
        base = origin_stability[(origin_stability["rule_set"] == rule) & (origin_stability["layer"] == "base")]
        for level in ["Category", "Type", "Item"]:
            sub = base[base["level"] == level]
            print(f"  {rule} [base], {level}: {100*sub['stable'].sum()/len(sub):.1f}% stable "
                  f"(vs. empirical selection's ~26% at item level, ~0% at Category/Type level, established previously)")
        break  # SBC/KH/PK base stability is nearly identical — printed once to avoid repetition; full detail in CSV
    print("However, the FINAL (practically deployable) layered choice is much less stable (0-32%), because our")
    print("own data-sufficiency gate (Naive whenever history <24 months) mechanically forces a Naive->non-Naive")
    print("flip once a series crosses the 24-month mark. This is an artifact of OUR gate design, not evidence")
    print("that the underlying rule is unstable — but it means the practical, deployable version of these rules")
    print("does NOT yet deliver the stability advantage the literature's premise would predict; a differently")
    print("designed sufficiency gate (e.g. a rolling/expanding-window confidence check rather than a hard")
    print("24-month cutoff) would be needed to realise it in practice.")

    print("\n== PART 6: WHAT THE EVIDENCE SUPPORTS ==")
    print("Category and Type level:")
    print(final_df[["level", "key", "classification", "trend_direction", "KH_model", "best_test_strategy", "best_test_MAE"]].to_string(index=False))

    print("\n" + "=" * 92)
    print("CONFIDENCE LEVELS")
    print("=" * 92)
    print("HIGH: Combination forecasting beats rule-based selection and Naive on MAE/RMSE at all 3 levels —")
    print("  large, consistent, directly measured (Part 4).")
    print("HIGH: the underlying SBC/KH/PK classification (ADI/CV2-driven, before our sufficiency gate) is far")
    print("  more stable across rolling origins than empirical validation-based selection was — 84-100% vs")
    print("  ~0-26% (Part 5, base layer) — this specific literature premise IS supported by the evidence.")
    print("MEDIUM: whether a PRACTICALLY DEPLOYABLE rule-based system (i.e., with a working sufficiency gate)")
    print("  would retain that stability advantage — our specific gate design does not, but this reflects our")
    print("  own implementation choice, not a re-test of a published, validated gate design.")
    print("MEDIUM: the Kostenko-Hyndman formula's fitted alpha, estimated via statsforecast's golden-section")
    print("  optimiser on 25-31 data points — short-series alpha estimates carry real uncertainty not")
    print("  propagated into the model choice (a threshold is a threshold, regardless of estimation noise).")
    print("LOW: whether 'Croston never survives the layered recommendation' is desirable versus an artifact of")
    print("  our own layer design choice to route the whole Smooth quadrant to SES/Holt — this was OUR")
    print("  reasoned extension, not verified against a published source, and is flagged as such throughout.")

    print("\n" + "=" * 92)
    print("UNRESOLVED")
    print("=" * 92)
    print("- The exact sufficiency-gate design that would let rule-based selection realise its stability")
    print("  advantage in practice (ours does not) — not attempted here, would need further design work.")
    print("- Whether trend (Holt) and non-intermittent (SES) routing for the Smooth quadrant is itself the best")
    print("  choice, versus, e.g., only applying it at the literal ADI<=1 boundary P&K specify — both are")
    print("  defensible; only the broader version was tested here.")
    print("- Whether a different combination weighting (e.g. trimmed mean, inverse-error weighting) would beat")
    print("  the simple equal-weight average tested here — not tested, out of scope.")
    print("- Month-of-year (seasonal) strength is reported as observation only; genuinely unconfirmable with 2")
    print("  complete years, not a gap that more analysis of THIS dataset could close.")

    print("\nAll outputs in output/summary/ (rule_part1_ through rule_part6_ prefixes) and output/charts/")
    print("(rule_strategy_comparison_*.png, 2 Category + 8 Type). config/config.yaml NOT modified. No model")
    print("choice was written to config.")
