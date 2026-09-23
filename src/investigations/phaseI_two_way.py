"""Phase I Part 3 -- two-way grid on each division's top-2 assumptions by max value_shift
(read from output/summary/phaseI_2_classification.csv, produced by phaseI_run_sweeps.py).

Additive-vs-amplifying test: for each grid cell (a, b), compare the JOINT stock_value shift
against the SUM of the two assumptions' own MARGINAL shifts (each swept alone, same value, other
held at default) -- both measured relative to the default stock_value. amplification_ratio =
joint_value_shift_signed / (marginal_a_signed + marginal_b_signed) when the denominator is
non-negligible; > ~1.2 => amplifying, < ~0.8 => sub-additive/dampening, else roughly additive.
Signed shifts (not absolute) are used here specifically so direction is preserved -- two
assumptions pulling stock_value in OPPOSITE directions must show as partial cancellation, not as
amplification.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseI_two_way")

SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")


def top2_assumptions(classification_df: pd.DataFrame, division: str) -> list:
    sub = classification_df[(classification_df["division"] == division) &
                             (classification_df["assumption"] != "sellable_warehouses")]
    sub = sub.sort_values("max_value_shift_pct", ascending=False)
    return sub["assumption"].head(2).tolist()


def run_grid(bundle: dict, default_result: dict, assumption_a: str, assumption_b: str) -> pd.DataFrame:
    rows = []
    default_sv = default_result["stock_value"]
    for va in eng.RANGES[assumption_a]:
        for vb in eng.RANGES[assumption_b]:
            params = dict(eng.DEFAULTS)
            params[assumption_a] = va
            params[assumption_b] = vb
            result = eng.run_scenario(bundle, **params)
            joint_shift_signed = (result["stock_value"] - default_sv) / default_sv if default_sv else float("nan")
            rows.append({assumption_a: va, assumption_b: vb, "stock_value": result["stock_value"],
                         "fill_rate": result["fill_rate"], "joint_value_shift_signed": joint_shift_signed})
    return pd.DataFrame(rows)


def marginal_shifts(bundle: dict, default_result: dict, assumption: str) -> dict:
    default_sv = default_result["stock_value"]
    out = {}
    for v in eng.RANGES[assumption]:
        params = dict(eng.DEFAULTS)
        params[assumption] = v
        result = eng.run_scenario(bundle, **params)
        out[v] = (result["stock_value"] - default_sv) / default_sv if default_sv else float("nan")
    return out


def annotate_interaction(grid_df: pd.DataFrame, assumption_a: str, assumption_b: str,
                          marg_a: dict, marg_b: dict) -> pd.DataFrame:
    def classify_row(r):
        ma, mb = marg_a[r[assumption_a]], marg_b[r[assumption_b]]
        joint = r["joint_value_shift_signed"]
        denom = ma + mb
        if abs(denom) < 1e-6:
            return ("n/a (marginals ~cancel)", float("nan"))
        ratio = joint / denom
        if ratio > 1.2:
            return ("amplifying", ratio)
        if ratio < 0.8:
            return ("sub-additive/dampening", ratio)
        return ("roughly additive", ratio)

    results = grid_df.apply(classify_row, axis=1)
    grid_df = grid_df.copy()
    grid_df["interaction_label"] = [x[0] for x in results]
    grid_df["interaction_ratio_joint_over_sum_marginals"] = [x[1] for x in results]
    return grid_df


def main():
    config = eng.load_config()
    raw, inv = eng.load_raw()
    classification_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseI_2_classification.csv"))

    all_grids = []
    summary_rows = []
    for division in eng.DIVISIONS:
        bundle = eng.build_division_bundle(config, division, raw, inv)
        default_result = eng.default_scenario(bundle)
        a, b = top2_assumptions(classification_df, division)
        logger.info("[%s] top-2 by max_value_shift: %s, %s", division, a, b)

        marg_a = marginal_shifts(bundle, default_result, a)
        marg_b = marginal_shifts(bundle, default_result, b)
        grid_df = run_grid(bundle, default_result, a, b)
        grid_df = annotate_interaction(grid_df, a, b, marg_a, marg_b)
        grid_df["division"] = division
        grid_df["assumption_a"], grid_df["assumption_b"] = a, b
        all_grids.append(grid_df)

        label_counts = grid_df["interaction_label"].value_counts().to_dict()
        dominant = max(label_counts, key=label_counts.get)
        summary_rows.append({"division": division, "assumption_a": a, "assumption_b": b,
                             "n_cells": len(grid_df), "label_counts": label_counts,
                             "dominant_interaction": dominant})
        print(f"\n--- {division}: {a} x {b} ---")
        print(grid_df[[a, b, "stock_value", "joint_value_shift_signed", "interaction_label",
                        "interaction_ratio_joint_over_sum_marginals"]].to_string(index=False))

    combined = pd.concat(all_grids, ignore_index=True)
    combined.to_csv(os.path.join(SUMMARY_DIR, "phaseI_3_two_way_grid.csv"), index=False)

    print("\n" + "=" * 100)
    print("PART 3 SUMMARY")
    print("=" * 100)
    for r in summary_rows:
        print(r)

    return combined, summary_rows


if __name__ == "__main__":
    main()
