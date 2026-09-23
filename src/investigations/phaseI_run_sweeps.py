"""Phase I Part 1/2 -- one-at-a-time sweep runner. Sweeps each of 8 assumptions across its range,
holding all others at config default, recomputing segment policy / Min / Max / stock_value /
fill_rate via src/investigations/phaseI_sensitivity_engine.py (which itself reuses the existing
pipeline's verified functions). Classifies each assumption per METRICS.md Sec.17
(decision_sensitivity), at the 10%/20%/2pp default thresholds plus 5% and 20% variants.

Outputs (output/summary/):
  phaseI_1_scenario_results.csv       -- every scenario run: division, assumption, value, headline figures
  phaseI_1_item_detail_<division>.csv -- per-item Min/policy under every scenario, that division
  phaseI_2_classification.csv         -- per division/assumption verdict at 10/5/20% + policy flips
  phaseI_2_service_level_curve.csv    -- stock_value/fill_rate at each service level, all divisions
  phaseI_2_concentration_threshold.csv-- placeholder rule-flip check (report-only, no Min impact)

No database access -- everything from the single cached pull (phaseI_single_pull.py).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseI_run_sweeps")

SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")

NUMERIC_ASSUMPTIONS = [
    "procurement_lead_time_days", "assembly_time_days", "review_interval_days",
    "cycle_service_level", "unit_cost_window_months", "freq_cutoff_per_year",
]
ASSUMPTION_LABEL = {
    "procurement_lead_time_days": "procurement lead time (days)",
    "assembly_time_days": "assembly time (days)",
    "review_interval_days": "review interval (days)",
    "cycle_service_level": "cycle service level",
    "unit_cost_window_months": "unit-cost window (months)",
    "freq_cutoff_per_year": "segment frequency threshold (orders/yr)",
}


def compare_scenarios(default_result: dict, swept_result: dict) -> dict:
    facts_d = default_result["facts"].set_index("code")["policy"]
    facts_s = swept_result["facts"].set_index("code")["policy"].reindex(facts_d.index)
    policy_flip_mask = facts_d != facts_s
    flipped_items = [
        {"code": c, "policy_default": facts_d[c], "policy_swept": facts_s[c]}
        for c in facts_d.index[policy_flip_mask]
    ]

    master_index = facts_d.index  # ALL scope items (incl. placeholder/excluded, which have no Min)
    min_d = default_result["full_df"].set_index("code")["min_qty"].reindex(master_index)
    min_s = swept_result["full_df"].set_index("code")["min_qty"].reindex(master_index)
    sv_contrib_d = default_result["full_df"].set_index("code")["stock_value_contribution"].reindex(master_index).fillna(0.0)

    default_total_sv = default_result["stock_value"]
    weight = sv_contrib_d / default_total_sv if default_total_sv else sv_contrib_d * 0.0

    has_min_both = min_d.notna() & (min_d > 0) & min_s.notna()
    lost_min_items = min_d.index[min_d.notna() & (min_d > 0) & min_s.isna()].tolist()
    zero_min_default = int(((min_d == 0) & min_d.notna()).sum())

    item_min_shift = pd.Series(np.nan, index=master_index)
    item_min_shift[has_min_both] = (min_s[has_min_both] - min_d[has_min_both]).abs() / min_d[has_min_both]

    default_sv, swept_sv = default_result["stock_value"], swept_result["stock_value"]
    value_shift = abs(swept_sv - default_sv) / default_sv if default_sv else float("nan")

    fr_d, fr_s = default_result["fill_rate"], swept_result["fill_rate"]
    fill_rate_shift_pp = (fr_s - fr_d) * 100 if pd.notna(fr_d) and pd.notna(fr_s) else float("nan")

    detail = pd.DataFrame({
        "code": master_index, "min_default": min_d.values, "min_swept": min_s.values,
        "min_shift": item_min_shift.values, "stock_value_weight_default": weight.values,
        "policy_default": facts_d.values, "policy_swept": facts_s.values,
    })

    return {
        "policy_flip": bool(policy_flip_mask.any()), "n_policy_flips": int(policy_flip_mask.sum()),
        "flipped_items": flipped_items, "value_shift": value_shift, "fill_rate_shift_pp": fill_rate_shift_pp,
        "default_stock_value": default_sv, "swept_stock_value": swept_sv,
        "default_fill_rate": fr_d, "swept_fill_rate": fr_s,
        "lost_min_items": lost_min_items, "zero_min_default_count": zero_min_default,
        "item_detail": detail,
    }


def min_shift_weighted_trigger(detail: pd.DataFrame, min_shift_threshold_pct: float, weight_threshold_pct: float) -> tuple:
    """Criterion 2 of METRICS.md Sec.17, resolved reading (stated explicitly, not silently
    picked): items whose min_shift exceeds the threshold are grouped, and the criterion fires if
    THAT GROUP'S COMBINED stock_value share (of the division's default stock_value) reaches the
    weight threshold -- not any single item individually reaching it (real inventories rarely
    concentrate 20% of stock_value in one item; the aggregate reading is the only one that can
    ever fire)."""
    flagged = detail[detail["min_shift"] > (min_shift_threshold_pct / 100.0)]
    combined_weight_pct = 100 * flagged["stock_value_weight_default"].sum()
    return bool(combined_weight_pct >= weight_threshold_pct), combined_weight_pct, len(flagged)


def classify(cmp: dict, detail: pd.DataFrame, thresh_pct: float, weight_pct: float = 20.0, fill_rate_pp: float = 2.0) -> bool:
    if cmp["policy_flip"]:
        return True
    trig2, _, _ = min_shift_weighted_trigger(detail, thresh_pct, weight_pct)
    if trig2:
        return True
    if pd.notna(cmp["value_shift"]) and cmp["value_shift"] * 100 > thresh_pct:
        return True
    if pd.notna(cmp["fill_rate_shift_pp"]) and abs(cmp["fill_rate_shift_pp"]) > fill_rate_pp:
        return True
    return False


def run_division(config: dict, division: str, raw: pd.DataFrame, inv: pd.DataFrame) -> dict:
    logger.info("=" * 100)
    logger.info("DIVISION %s -- Part 1 one-at-a-time sweep", division)
    logger.info("=" * 100)
    bundle = eng.build_division_bundle(config, division, raw, inv)
    default_result = eng.default_scenario(bundle)
    logger.info("[%s] default: stock_value=%.2f fill_rate=%.4f csl=%.4f policy=%s",
                division, default_result["stock_value"], default_result["fill_rate"],
                default_result["cycle_service_level"], default_result["facts"]["policy"].value_counts().to_dict())

    scenario_rows = []
    item_detail_rows = []

    def record(assumption, value, result, is_default=False):
        cmp = compare_scenarios(default_result, result) if not is_default else {
            "policy_flip": False, "n_policy_flips": 0, "flipped_items": [], "value_shift": 0.0,
            "fill_rate_shift_pp": 0.0, "default_stock_value": default_result["stock_value"],
            "swept_stock_value": default_result["stock_value"], "default_fill_rate": default_result["fill_rate"],
            "swept_fill_rate": default_result["fill_rate"], "lost_min_items": [], "zero_min_default_count": 0,
            "item_detail": pd.DataFrame(),
        }
        row = {
            "division": division, "assumption": assumption, "value": value, "is_default": is_default,
            "stock_value": result["stock_value"], "fill_rate": result["fill_rate"],
            "cycle_service_level": result["cycle_service_level"],
            "n_finished_goods_stock": int((result["facts"]["policy"] == "finished_goods_stock").sum()),
            "n_component_stock_ato": int((result["facts"]["policy"] == "component_stock_ato").sum()),
            "value_shift": cmp["value_shift"], "fill_rate_shift_pp": cmp["fill_rate_shift_pp"],
            "n_policy_flips": cmp["n_policy_flips"], "policy_flip": cmp["policy_flip"],
            "n_lost_min_items": len(cmp["lost_min_items"]),
        }
        if not is_default and len(cmp["item_detail"]):
            d = cmp["item_detail"].copy()
            d["division"], d["assumption"], d["value"] = division, assumption, value
            item_detail_rows.append(d)
        scenario_rows.append((row, cmp))
        return cmp

    record("(default)", "default", default_result, is_default=True)

    for assumption in NUMERIC_ASSUMPTIONS:
        for value in eng.RANGES[assumption]:
            params = dict(eng.DEFAULTS)
            params[assumption] = value
            result = eng.run_scenario(bundle, **params)
            record(assumption, value, result)

    # ---- sellable warehouses: 3 named variants ----
    for variant_name, wh_list in bundle["sellable_variants"].items():
        result = eng.run_scenario(bundle, **eng.DEFAULTS, sellable_warehouses=wh_list)
        cmp = record("sellable_warehouses", variant_name, result)
        logger.info("[%s] sellable_warehouses=%s -> Min/stock_value/fill_rate identical to default: "
                    "value_shift=%.6f fill_rate_shift_pp=%.6f policy_flip=%s (expected: all ~0, "
                    "per METRICS.md Min/Max/stock_value/simulation formulas -- none depend on "
                    "on-hand/sellable stock).", division, variant_name, cmp["value_shift"],
                    cmp["fill_rate_shift_pp"], cmp["policy_flip"])

    scenario_df = pd.DataFrame([r for r, _ in scenario_rows])
    item_detail_df = pd.concat(item_detail_rows, ignore_index=True) if item_detail_rows else pd.DataFrame()

    return {
        "division": division, "bundle": bundle, "default_result": default_result,
        "scenario_df": scenario_df, "item_detail_df": item_detail_df,
        "scenario_rows": scenario_rows,
    }


def build_classification_table(division_results: dict) -> pd.DataFrame:
    rows = []
    for division, dres in division_results.items():
        for assumption in NUMERIC_ASSUMPTIONS + ["sellable_warehouses"]:
            sub_rows = [(r, cmp) for r, cmp in dres["scenario_rows"] if r["assumption"] == assumption]
            if not sub_rows:
                continue
            max_value_shift = max((r["value_shift"] for r, _ in sub_rows if pd.notna(r["value_shift"])), default=0.0)
            max_fr_shift = max((abs(r["fill_rate_shift_pp"]) for r, _ in sub_rows if pd.notna(r["fill_rate_shift_pp"])), default=0.0)
            any_policy_flip = any(r["policy_flip"] for r, _ in sub_rows)
            n_flip_total = sum(r["n_policy_flips"] for r, _ in sub_rows)
            max_min_shift_weighted = 0.0
            first_flip_value = None
            for r, cmp in sub_rows:
                if len(cmp["item_detail"]):
                    _, w, _ = min_shift_weighted_trigger(cmp["item_detail"], 10.0, 20.0)
                    max_min_shift_weighted = max(max_min_shift_weighted, w)
                if first_flip_value is None:
                    verdict_here = classify(cmp, cmp["item_detail"], 10.0)
                    if verdict_here:
                        first_flip_value = r["value"]
            verdict_10 = any(classify(cmp, cmp["item_detail"], 10.0) for _, cmp in sub_rows)
            verdict_5 = any(classify(cmp, cmp["item_detail"], 5.0) for _, cmp in sub_rows)
            verdict_20 = any(classify(cmp, cmp["item_detail"], 20.0) for _, cmp in sub_rows)
            rows.append({
                "division": division, "assumption": assumption,
                "assumption_label": ASSUMPTION_LABEL.get(assumption, assumption),
                "range_swept": str(eng.RANGES.get(assumption, list(dres["bundle"]["sellable_variants"].keys()))),
                "max_value_shift_pct": round(max_value_shift * 100, 3),
                "max_fill_rate_shift_pp": round(max_fr_shift, 3),
                "max_min_shift_weighted_pct_of_stock_value": round(max_min_shift_weighted, 3),
                "n_policy_flips_total": n_flip_total, "any_policy_flip": any_policy_flip,
                "verdict_at_10pct": "RELEVANT" if verdict_10 else "INSENSITIVE",
                "verdict_at_5pct": "RELEVANT" if verdict_5 else "INSENSITIVE",
                "verdict_at_20pct": "RELEVANT" if verdict_20 else "INSENSITIVE",
                "first_value_where_relevant_at_10pct": first_flip_value,
            })
    return pd.DataFrame(rows)


def build_service_level_curve(division_results: dict) -> pd.DataFrame:
    rows = []
    for division, dres in division_results.items():
        sub = [(r, cmp) for r, cmp in dres["scenario_rows"] if r["assumption"] == "cycle_service_level"]
        sub_sorted = sorted(sub, key=lambda rc: rc[0]["value"])
        prev = None
        for r, cmp in sub_sorted:
            sl = r["value"]
            sv = r["stock_value"]
            fr = r["fill_rate"]
            marginal_sv_per_pp_fr = None
            if prev is not None:
                d_sv = sv - prev["stock_value"]
                d_fr_pp = (fr - prev["fill_rate"]) * 100
                marginal_sv_per_pp_fr = (d_sv / d_fr_pp) if d_fr_pp not in (0, None) and pd.notna(d_fr_pp) else None
            rows.append({"division": division, "cycle_service_level": sl, "stock_value": sv,
                         "fill_rate": fr, "marginal_stock_value_per_pp_fill_rate": marginal_sv_per_pp_fr})
            prev = {"stock_value": sv, "fill_rate": fr}
    df = pd.DataFrame(rows)
    # knee: first point where marginal_sv_per_pp more than doubles vs the previous step, per division
    knees = []
    for division, g in df.groupby("division"):
        g = g.sort_values("cycle_service_level").reset_index(drop=True)
        knee_sl = None
        for i in range(2, len(g)):
            prev_m = g.loc[i - 1, "marginal_stock_value_per_pp_fill_rate"]
            cur_m = g.loc[i, "marginal_stock_value_per_pp_fill_rate"]
            if prev_m and cur_m and prev_m > 0 and cur_m > 2 * prev_m:
                knee_sl = g.loc[i, "cycle_service_level"]
                break
        knees.append({"division": division, "knee_cycle_service_level": knee_sl})
    knee_df = pd.DataFrame(knees)
    df = df.merge(knee_df, on="division", how="left")
    return df


def build_concentration_table(config: dict) -> pd.DataFrame:
    ph = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_placeholder_assignment_82items.csv"))
    thresholds = [30.0, 40.0, 50.0]
    rows = []
    for division in eng.DIVISIONS:
        sub = ph[(ph["division"] == division) & ph["type_top_item_share_pct"].notna()]
        if not len(sub):
            rows.append({"division": division, "n_items_governed_by_rule": 0,
                         "rule_at_30": None, "rule_at_40": None, "rule_at_50": None,
                         "any_flip_30_vs_40": False, "any_flip_40_vs_50": False, "any_flip_30_vs_50": False,
                         "note": "No items in this division's current pipeline receive placeholder policy "
                                 "at all (phaseE2_pilot_recompute: PEM103/PEM107 have no placeholder_item_codes "
                                 "list -- every item is eligible_for_policy) -- this assumption is N/A for this "
                                 "division under the CURRENT pipeline, not merely insensitive."})
            continue
        rule_at = {}
        for t in thresholds:
            rule_at[t] = np.where(sub["type_top_item_share_pct"] >= t, "B", "A")
        flip_30_40 = int((rule_at[30.0] != rule_at[40.0]).sum())
        flip_40_50 = int((rule_at[40.0] != rule_at[50.0]).sum())
        flip_30_50 = int((rule_at[30.0] != rule_at[50.0]).sum())
        rows.append({
            "division": division, "n_items_governed_by_rule": len(sub),
            "n_items_flip_30_vs_40": flip_30_40, "n_items_flip_40_vs_50": flip_40_50,
            "n_items_flip_30_vs_50": flip_30_50,
            "any_flip_30_vs_40": flip_30_40 > 0, "any_flip_40_vs_50": flip_40_50 > 0,
            "any_flip_30_vs_50": flip_30_50 > 0,
            "note": "Placeholder items carry no Min (METRICS.md Sec.5) and are excluded from the "
                    "hierarchy/stock_value/simulation (config placeholder_hierarchy_treatment) -- a rule "
                    "flip here changes only which of two REFERENCE-ONLY formulas (Type mean vs Type "
                    "median) produces a placeholder qty that never feeds Min/Max/stock_value/fill_rate. "
                    "Report-only per task instruction; not scored against the decision_sensitivity "
                    "criteria.",
        })
    return pd.DataFrame(rows)


def main():
    config = eng.load_config()
    raw, inv = eng.load_raw()
    division_results = {}
    for division in eng.DIVISIONS:
        division_results[division] = run_division(config, division, raw, inv)

    all_scenarios = pd.concat([dr["scenario_df"] for dr in division_results.values()], ignore_index=True)
    all_scenarios.to_csv(os.path.join(SUMMARY_DIR, "phaseI_1_scenario_results.csv"), index=False)

    for division, dres in division_results.items():
        if len(dres["item_detail_df"]):
            dres["item_detail_df"].to_csv(
                os.path.join(SUMMARY_DIR, f"phaseI_1_item_detail_{division}.csv"), index=False)

    classification_df = build_classification_table(division_results)
    classification_df.to_csv(os.path.join(SUMMARY_DIR, "phaseI_2_classification.csv"), index=False)

    curve_df = build_service_level_curve(division_results)
    curve_df.to_csv(os.path.join(SUMMARY_DIR, "phaseI_2_service_level_curve.csv"), index=False)

    conc_df = build_concentration_table(config)
    conc_df.to_csv(os.path.join(SUMMARY_DIR, "phaseI_2_concentration_threshold.csv"), index=False)

    print("\n" + "=" * 100)
    print("PHASE I PART 1/2 -- CLASSIFICATION SUMMARY")
    print("=" * 100)
    print(classification_df.to_string(index=False))
    print("\nSERVICE LEVEL CURVE:")
    print(curve_df.to_string(index=False))
    print("\nCONCENTRATION THRESHOLD (report-only):")
    print(conc_df.to_string(index=False))

    return division_results, classification_df, curve_df, conc_df


if __name__ == "__main__":
    main()
