"""Rule-based selection task, Part 5: applies each rule set at multiple
rolling origins and reports whether it selects the same model each time —
the key claimed advantage of rule-based selection over empirical selection
(which changed its winner at nearly every origin in prior work on this
project). Quantified directly, not assumed.

Same origin settings as this project's prior rolling-origin backtests
(src/rolling_origin.py, src/backtest_aggregate.py): MIN_TRAIN_MONTHS=13,
step=2, holdout=6 — for direct comparability.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from feature_analysis import build_all_series, determine_complete_months
from rule_based_selection import select_models_for_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("rule_stability_origins")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

MIN_TRAIN_MONTHS = 13
ORIGIN_STEP = 2
HOLDOUT = 6


def get_origins(total_months: int, holdout: int) -> list:
    last_train = total_months - holdout
    origins = list(range(MIN_TRAIN_MONTHS, last_train + 1, ORIGIN_STEP))
    if origins[-1] != last_train:
        origins.append(last_train)
    return origins


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    series = build_all_series(monthly, scope)

    total_months = monthly["year_month"].nunique()
    origins = get_origins(total_months, HOLDOUT)
    logger.info("Total months: %d. Origins: %d (train sizes %s)", total_months, len(origins), origins)

    rows = []
    for (level, key, cat), (qty, months) in series.items():
        if len(qty) != total_months or qty.sum() == 0:
            continue
        for origin_idx, train_size in enumerate(origins, start=1):
            choice = select_models_for_series(qty[:train_size], months[:train_size])
            rows.append({
                "level": level, "key": key, "category": cat, "origin": origin_idx, "train_size": train_size,
                "SBC_model": choice.get("SBC_final", "Naive"), "KH_model": choice.get("KH_final", "Naive"),
                "PK_model": choice.get("PK_final", "Naive"),
                "SBC_base": choice.get("SBC_base", "Naive"), "KH_base": choice.get("KH_base", "Naive"),
                "PK_base": choice.get("PK_base", "Naive"),
            })

    origins_df = pd.DataFrame(rows)
    origins_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part5_rule_choice_per_origin.csv"), index=False)

    stability_rows = []
    for rule_col, layer in [("SBC_model", "final"), ("KH_model", "final"), ("PK_model", "final"),
                             ("SBC_base", "base"), ("KH_base", "base"), ("PK_base", "base")]:
        for (level, key), g in origins_df.groupby(["level", "key"]):
            n_distinct = g[rule_col].nunique()
            n_origins_series = len(g)
            stability_rows.append({
                "rule_set": rule_col.replace("_model", "").replace("_base", ""), "layer": layer,
                "level": level, "key": key,
                "n_origins": n_origins_series, "n_distinct_models": n_distinct,
                "stable": n_distinct == 1, "models_seen": sorted(g[rule_col].unique().tolist()),
            })
    stability_df = pd.DataFrame(stability_rows)
    stability_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part5_stability_summary.csv"), index=False)

    print("\n" + "=" * 90)
    print(f"PART 5: RULE STABILITY ACROSS {len(origins)} ROLLING ORIGINS (train sizes {origins})")
    print("=" * 90)
    print("\nNOTE: the 'final' layer includes the extended layer's data-sufficiency gate (Naive whenever a")
    print("window has < 24 months of history) — since origins 1-6 all have < 24 months, that gate alone forces")
    print("Naive at every early origin regardless of the underlying ADI/CV2 classification. 'base' strips that")
    print("gate out and reports stability of the pure SBC/KH/PK classification-driven choice (Croston/SBA/SES)")
    print("on its own, which is what the 'rules should be more stable' rationale is actually claiming.")

    for rule in ["SBC", "KH", "PK"]:
        print(f"\n--- {rule} rule set ---")
        for layer in ["base", "final"]:
            print(f" [{layer}]")
            for level in ["Category", "Type", "Item"]:
                sub = stability_df[(stability_df["rule_set"] == rule) & (stability_df["layer"] == layer) & (stability_df["level"] == level)]
                n_stable = sub["stable"].sum()
                n_total = len(sub)
                print(f"  {level}: {n_stable} of {n_total} series ({100*n_stable/n_total:.1f}%) select the SAME model at every origin")

    print("\nComparison point (established in prior work on this project, not re-derived here):")
    print("Empirical (validation-selected) rolling-origin stability was 25.9% at item level (15/58 items, prior")
    print("58-item Type-level pilot) and 0% at Category/Type level (0/10 series, prior 128-item aggregate task).")

    print("\nFull detail: output/summary/rule_part5_rule_choice_per_origin.csv, rule_part5_stability_summary.csv")
