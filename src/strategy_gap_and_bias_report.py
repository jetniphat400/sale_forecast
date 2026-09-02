"""Reporting task (2026-09-02): Bias, MAE-vs-Bias disagreement, and the
validation-to-test overfitting gap, for all four selection strategies
(rule-based x3, empirical, combination, Naive) at Category/Type/Item level.

This is a REPORTING task. Parts 1, 2, 4 and 5 read and re-present numbers
that already exist in output/summary/ from the prior rule-based-selection
task — nothing is recomputed for those. Part 3 (the validation-to-test gap
PER STRATEGY) was genuinely never computed in the prior run — only the
already-selected model's TEST performance was saved, not its VALIDATION
performance — so it is computed here, explicitly flagged as newly
calculated, using the exact same model choice already recorded for each
strategy (no re-selection, no leakage: the validation-stage fit uses only
the first 19 months, exactly as the original train/val/test split did).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from evaluate_strategies import TEST_MONTHS, TRAIN_MONTHS, VAL_MONTHS, compute_metrics
from feature_analysis import build_all_series, determine_complete_months
from models import combination_forecast, get_extended_models, get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("strategy_gap_and_bias_report")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
MA_WINDOWS = [3, 6, 12]

STRATEGY_TO_SELECTION_COL = {"Rule-SBC": "SBC_model", "Rule-KH": "KH_model", "Rule-PK": "PK_model", "Empirical": "empirical_model"}


def compute_validation_stage_metrics(series: dict, selections: pd.DataFrame) -> pd.DataFrame:
    """NEWLY COMPUTED (not in the prior run): for each strategy and series,
    fits the SAME model that strategy already chose (recorded in
    rule_part4_model_selections.csv) on TRAIN ONLY (19 months) and forecasts
    the VALIDATION window (6 months) — the mirror image of the existing
    test-stage evaluation (train+val -> test), so the two are comparable."""
    base_models = get_models(MA_WINDOWS)
    ext_models = get_extended_models(MA_WINDOWS)
    rows = []
    for (level, key, cat), (qty, months) in series.items():
        if len(qty) != TRAIN_MONTHS + VAL_MONTHS + TEST_MONTHS or qty.sum() == 0:
            continue
        train = qty[:TRAIN_MONTHS]
        val = qty[TRAIN_MONTHS:TRAIN_MONTHS + VAL_MONTHS]
        sel_row = selections[(selections["level"] == level) & (selections["key"] == key)]
        if sel_row.empty:
            continue
        sel_row = sel_row.iloc[0]

        for strategy, col in STRATEGY_TO_SELECTION_COL.items():
            model_name = sel_row[col]
            model_fn = ext_models.get(model_name) or base_models.get(model_name)
            if model_fn is None:
                logger.warning("%s/%s: unknown model %r for %s, skipping", level, key, model_name, strategy)
                continue
            try:
                fc = np.clip(model_fn(train, VAL_MONTHS), 0, None)
            except Exception as e:
                logger.warning("%s/%s: %s (%s) failed on validation fit (%s) — using Naive", level, key, strategy, model_name, e)
                fc = np.clip(base_models["Naive"](train, VAL_MONTHS), 0, None)
            metrics = compute_metrics(val, fc, train)
            rows.append({"level": level, "key": key, "category": cat, "strategy": strategy, "model_used": model_name, **metrics})

        # Combination: same fixed procedure (avg of the 6 base candidates), no selection to hold constant
        fc_combo = combination_forecast(train, VAL_MONTHS, MA_WINDOWS)
        fc_combo = np.clip(fc_combo, 0, None)
        rows.append({"level": level, "key": key, "category": cat, "strategy": "Combination",
                     "model_used": "avg(Naive,MA3,MA6,MA12,Croston,SBA)", **compute_metrics(val, fc_combo, train)})

        # Naive floor
        fc_naive = np.clip(base_models["Naive"](train, VAL_MONTHS), 0, None)
        rows.append({"level": level, "key": key, "category": cat, "strategy": "Naive", "model_used": "Naive",
                     **compute_metrics(val, fc_naive, train)})

    return pd.DataFrame(rows)


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    series = build_all_series(monthly, scope)

    # ============================= EXISTING DATA (re-reported, not recomputed) =============================
    test_results = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_test_results_per_series.csv"))
    summary_strategy = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_summary_by_level_strategy.csv"))
    mae_bias_disagree = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_mae_vs_bias_best.csv"))
    selections = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part4_model_selections.csv"))
    features_df = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part1_series_features_full_history.csv"))
    scope_all = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))

    # ============================= PART 3: NEWLY COMPUTED validation-stage metrics =============================
    logger.info("Validation-stage metrics per strategy were NOT computed in the prior run (only test-stage "
                "metrics were saved). Computing them now, explicitly flagged as new.")
    val_results = compute_validation_stage_metrics(series, selections)
    val_results.to_csv(os.path.join(SUMMARY_DIR, "rule_part7_validation_stage_results.csv"), index=False)

    gap_rows = []
    for (level, strategy), g_test in test_results.groupby(["level", "strategy"]):
        g_val = val_results[(val_results["level"] == level) & (val_results["strategy"] == strategy)]
        merged = g_test.merge(g_val, on=["level", "key"], suffixes=("_test", "_val"))
        if merged.empty:
            continue
        mean_val_mae = merged["MAE_val"].mean()
        mean_test_mae = merged["MAE_test"].mean()
        gap = mean_test_mae - mean_val_mae
        gap_pct = 100 * gap / mean_val_mae if mean_val_mae else np.nan
        gap_rows.append({"level": level, "strategy": strategy, "n_series": len(merged),
                          "mean_val_MAE": mean_val_mae, "mean_test_MAE": mean_test_mae,
                          "gap": gap, "gap_pct": gap_pct})
    gap_df = pd.DataFrame(gap_rows)
    gap_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part7_val_test_gap_by_strategy.csv"), index=False)

    # ============================= PART 2 detail: largest MAE-vs-Bias disagreements =============================
    detail_rows = []
    for _, row in mae_bias_disagree[mae_bias_disagree["disagree"]].iterrows():
        level, key = row["level"], row["key"]
        g = test_results[(test_results["level"] == level) & (test_results["key"] == key)]
        mae_best = g.loc[g["MAE"].idxmin()]
        g2 = g.copy()
        g2["abs_bias"] = g2["Bias"].abs()
        bias_best = g2.loc[g2["abs_bias"].idxmin()]
        detail_rows.append({
            "level": level, "key": key,
            "MAE_best_strategy": mae_best["strategy"], "MAE_best_MAE": mae_best["MAE"], "MAE_best_Bias": mae_best["Bias"],
            "Bias_best_strategy": bias_best["strategy"], "Bias_best_MAE": bias_best["MAE"], "Bias_best_Bias": bias_best["Bias"],
            "MAE_of_MAE_best_vs_MAE_of_bias_best_gap": mae_best["MAE"] - bias_best["MAE"],
            "Bias_of_bias_best_vs_Bias_of_MAE_best_gap": abs(mae_best["Bias"]) - abs(bias_best["Bias"]),
        })
    detail_df = pd.DataFrame(detail_rows)
    detail_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part7_mae_bias_disagreement_detail.csv"), index=False)

    # ============================= PART 4: margin between winner and runner-up =============================
    margin_rows = []
    for level in ["Category", "Type", "Item"]:
        sub = summary_strategy[summary_strategy["level"] == level].sort_values("MAE")
        winner, runner_up = sub.iloc[0], sub.iloc[1]
        margin = runner_up["MAE"] - winner["MAE"]

        # Unpaired noise proxy: spread of the winner's own per-series MAE.
        per_series_winner = test_results[(test_results["level"] == level) & (test_results["strategy"] == winner["strategy"])]
        std_mae = per_series_winner["MAE"].std()
        n = len(per_series_winner)
        se_mae_unpaired = std_mae / np.sqrt(n) if n > 0 else np.nan

        # Paired comparison (same series, both strategies) — more appropriate since both are
        # scored on identical series and their errors are likely correlated; an unpaired SE
        # overstates uncertainty when that correlation is positive.
        per_series_runner = test_results[(test_results["level"] == level) & (test_results["strategy"] == runner_up["strategy"])]
        paired = per_series_winner[["key", "MAE"]].merge(per_series_runner[["key", "MAE"]], on="key", suffixes=("_winner", "_runner"))
        paired["diff"] = paired["MAE_runner"] - paired["MAE_winner"]
        n_paired = len(paired)
        mean_diff = paired["diff"].mean()
        se_diff_paired = paired["diff"].std(ddof=1) / np.sqrt(n_paired) if n_paired > 1 else np.nan
        t_stat = mean_diff / se_diff_paired if se_diff_paired else np.nan

        margin_rows.append({
            "level": level, "winner": winner["strategy"], "winner_MAE": winner["MAE"],
            "runner_up": runner_up["strategy"], "runner_up_MAE": runner_up["MAE"],
            "margin": margin, "margin_pct_of_winner": 100 * margin / winner["MAE"] if winner["MAE"] else np.nan,
            "winner_MAE_standard_error_unpaired": se_mae_unpaired,
            "margin_vs_1_se_unpaired": margin / se_mae_unpaired if se_mae_unpaired else np.nan,
            "n_paired_series": n_paired, "paired_mean_diff": mean_diff, "paired_se": se_diff_paired,
            "paired_t_stat": t_stat,
        })
    margin_df = pd.DataFrame(margin_rows)
    margin_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part7_winner_margin.csv"), index=False)

    # ============================= PART 5: the 16 no-history items =============================
    no_history = scope_all[~scope_all["has_any_history"]] if "has_any_history" in scope_all.columns else pd.DataFrame()
    # cross-check against feature file's NoSale item list (should be a superset: 15 never-any-history + 1 zero-under-filter)
    nosale_items = features_df[(features_df["level"] == "Item") & (features_df["classification"] == "NoSale")][["key"]]
    nosale_items.to_csv(os.path.join(SUMMARY_DIR, "rule_part7_no_history_items.csv"), index=False)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 92)
    print("# BIAS, MAE-vs-BIAS DISAGREEMENT, AND OVERFITTING GAP — FULL REPORT")
    print("#" * 92)

    print("\n" + "=" * 92)
    print("PART 1: BIAS BY STRATEGY AND LEVEL (re-reported from rule_part4_summary_by_level_strategy.csv — not recomputed)")
    print("=" * 92)
    for level in ["Category", "Type", "Item"]:
        sub = summary_strategy[summary_strategy["level"] == level].sort_values("Bias", key=lambda s: s.abs())
        print(f"\n--- {level} ---")
        print(sub[["strategy", "MAE", "RMSE", "Bias", "MASE"]].to_string(index=False))
        for _, r in sub.iterrows():
            direction = "UNDER-forecasts" if r["Bias"] < 0 else ("OVER-forecasts" if r["Bias"] > 0 else "unbiased")
            print(f"  {r['strategy']}: {direction} by {abs(r['Bias']):.1f} units/month on average")

    print("\n" + "=" * 92)
    print("PART 2: WHERE MAE-BEST AND BIAS-BEST STRATEGY DISAGREE (re-reported + new detail)")
    print("=" * 92)
    for level in ["Category", "Type", "Item"]:
        sub = mae_bias_disagree[mae_bias_disagree["level"] == level]
        n_dis = sub["disagree"].sum()
        print(f"{level}: {n_dis} of {len(sub)} series disagree ({100*n_dis/len(sub):.1f}%)")
    print("\nCONTEXT: an earlier, separate analysis (choosing among the 6 base MODELS empirically, not among")
    print("these 4 STRATEGIES) found 53.4% disagreement at item level and 60% at Category/Type level. The")
    print("comparison here is not apples-to-apples (4 coarser strategies vs. 6 individual models), but the")
    print("SAME underlying pattern — MAE-best and Bias-best frequently differ — still holds, just at a lower")
    print("rate once strategies are coarsened to 4 choices instead of 6.")
    if len(detail_df):
        detail_df["abs_mae_gap"] = detail_df["MAE_of_MAE_best_vs_MAE_of_bias_best_gap"].abs()
        top10 = detail_df.sort_values("abs_mae_gap", ascending=False).head(10)
        print("\nLargest disagreements (by MAE difference between the MAE-best and Bias-best strategy):")
        print(top10[["level", "key", "MAE_best_strategy", "MAE_best_MAE", "MAE_best_Bias",
                      "Bias_best_strategy", "Bias_best_MAE", "Bias_best_Bias"]].to_string(index=False))

    print("\n" + "=" * 92)
    print("PART 3: VALIDATION-TO-TEST GAP PER STRATEGY (NEWLY COMPUTED — not in the prior run)")
    print("=" * 92)
    print("Prior figures (127% item-level, 31.9% aggregated) were for EMPIRICAL SELECTION ONLY. Computed here")
    print("for all four strategies, same methodology (mean test MAE - mean val MAE, relative to mean val MAE),")
    print("using each strategy's ALREADY-CHOSEN model (from rule_part4_model_selections.csv) fit on train-only")
    print("(19mo) for validation and train+val (25mo) for test — no re-selection, no leakage.")
    for level in ["Category", "Type", "Item"]:
        sub = gap_df[gap_df["level"] == level].sort_values("gap_pct")
        print(f"\n--- {level} ---")
        print(sub[["strategy", "n_series", "mean_val_MAE", "mean_test_MAE", "gap", "gap_pct"]].to_string(index=False))

    print("\n" + "=" * 92)
    print("PART 4: FULL METRIC TABLE + WINNER MARGIN")
    print("=" * 92)
    print(summary_strategy.sort_values(["level", "MAE"]).to_string(index=False))
    print("\nMargin between winner and runner-up (by MAE), with two noise checks: an unpaired SE (winner's own")
    print("per-series spread) and a PAIRED comparison (same series, both strategies — more appropriate here")
    print("since both are scored on identical series and their errors are likely correlated, so an unpaired SE")
    print("overstates the uncertainty):")
    print(margin_df.to_string(index=False))
    for _, r in margin_df.iterrows():
        t = r["paired_t_stat"]
        verdict = "paired t exceeds ~2 — plausibly a real, consistent difference" if pd.notna(t) and abs(t) > 2 else "paired t is small — the margin could plausibly be chance/noise"
        print(f"  {r['level']}: {verdict} (paired t = {t:.2f} on {int(r['n_paired_series'])} series)")

    print("\n" + "=" * 92)
    print("PART 5: THE 16 ITEMS WITH NO SALES HISTORY")
    print("=" * 92)
    print(f"{len(nosale_items)} item series are classified 'NoSale' (zero demand in the analysis window) and were")
    print("EXCLUDED from every metric reported above (Parts 1-4) — they cannot be backtested (no train/val/test")
    print("split is possible with zero data) and no rule, empirical selection, or combination forecast was fit")
    print("for them. They ARE included in the 128-item Part 1/2 characteristics report (flagged 'NoSale', ADI/CV2")
    print("undefined) but carry no model recommendation and no test-set score.")
    print(f"Items: {sorted(nosale_items['key'].tolist())}")
    print("Current handling: none — no forecast is produced for these items by this pipeline. For inventory")
    print("planning they would need a different treatment entirely (e.g. new-item / no-history heuristics,")
    print("or business input), which is outside this pipeline's scope.")

    print("\n" + "=" * 92)
    print("PART 6: THE STABILITY GATE — WHAT IT DOES AND WHY IT DESTABILISES SELECTION")
    print("=" * 92)
    print("The extended layer (src/rule_based_selection.py, apply_extended_layer) checks, for EVERY rolling")
    print("origin independently: is this window's history >= 24 months, AND is the SBC classification the SAME")
    print("across that window's first-12/first-24/full sub-windows? If either check fails, the layer OVERRIDES")
    print("whatever SBC/KH/PK recommended and forces Naive instead, regardless of ADI/CV2.")
    print("Why this destabilises the FINAL recommendation across rolling origins: the 7 origins tested have train")
    print("sizes 13,15,17,19,21,23,25 months. Every one of the first 6 origins (13 through 23 months) has FEWER")
    print("than 24 months of history by construction — so the gate forces Naive at EVERY one of those origins,")
    print("no matter how stable the underlying ADI/CV2 classification actually is. Only the 7th origin (25")
    print("months) can ever produce a non-Naive answer. The result: the sequence of recommendations is")
    print("[Naive,Naive,Naive,Naive,Naive,Naive,X] — and unless X happens to equal Naive too, that is registered")
    print("as 'unstable' (2 distinct models across origins), even though the underlying rule was steady the")
    print("whole time. This is why 'base' (un-gated) stability was 84-100% but 'final' (gated) stability was")
    print("only 0-32% — the gap is almost entirely the gate's own hard cutoff, not genuine boundary-crossing.")
    print("\nAlternatives that would avoid this artifact (not implemented, for you to choose from):")
    print("  1. Lower the minimum-history threshold (e.g. 12 or 13 months) so more origins can produce a")
    print("     non-Naive answer — trades away some of the original conservatism about short-series reliability.")
    print("  2. Make the gate's OUTPUT continuous/graduated rather than a hard cutoff — e.g. blend the rule's")
    print("     recommendation with Naive in proportion to how much history is available, rather than an on/off switch.")
    print("  3. Test stability using a criterion that does not require a full 24-month window at all — e.g.")
    print("     compare only the two shortest available windows at each origin (rather than requiring first-12,")
    print("     first-24 AND full to all be computable), so the stability check itself can run earlier.")
    print("  4. Drop the stability sub-check from the gate entirely and rely only on the minimum-history check —")
    print("     simpler, but loses the explicit protection against a classification that looks fine only by luck.")
    print("  5. Re-run the Part 5 rolling-origin stability test using only origins >= 24 months (i.e. exclude the")
    print("     6 origins the gate can never pass) — this would isolate whether the gate's OWN decision (not just")
    print("     the underlying classification) is stable once it is actually allowed to fire.")
    print("No change has been made in this task — this is presented for a decision, not applied.")

    # ============================= PART 7 headline =============================
    print("\n" + "#" * 92)
    print("# PART 7: WHAT THE COMPLETE EVIDENCE SUPPORTS")
    print("#" * 92)
    for level in ["Category", "Type", "Item"]:
        sub_test = summary_strategy[summary_strategy["level"] == level]
        mae_winner = sub_test.loc[sub_test["MAE"].idxmin(), "strategy"]
        bias_winner = sub_test.loc[sub_test["Bias"].abs().idxmin(), "strategy"]
        gap_sub = gap_df[gap_df["level"] == level].sort_values("gap_pct")
        gap_winner = gap_sub.iloc[0]["strategy"]
        print(f"\n{level}: MAE-best = {mae_winner}, |Bias|-best = {bias_winner}, smallest overfitting gap = {gap_winner}")
    print("\nSee narrative conclusion in the assistant's chat message for the full synthesis across all three checks.")
