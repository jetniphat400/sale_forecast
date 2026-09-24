"""Phase 22 -- Validator (AGENTS.md role): independent recomputation of METRICS.md Sec.22
(robust_minmax) for PEM101, checking the Modeler's phase22_modeler*.py work WITHOUT reading it.

Per the task brief, this script:
  1. Deduplicates PEM101's robust_ensemble from the pre-existing phaseJ3_2_grid_PEM101.csv
     (METRICS.md Sec.20 tolerance, both calibration AND validation windows), resolving each of the
     3 usable-stock definitions' actual warehouse-code sets independently (via
     phaseI_sensitivity_engine.fg_prefixed_warehouses / current_stockholding_warehouses, restricted
     to PEM101's own scope inventory -- NOT the full 351-item cached pull).
  2. Computes range_ratio and median_Min for the 3 config.yaml pilot_item_codes focus items, using
     Sec.20's own r_months x mean_daily_demand formula (verified against
     phaseJ3_calibration_engine.simulate_months_of_demand's r_abs computation).
  3. Sweeps each deduplicated ensemble member's reorder level (r_months) across a 12-point grid
     (own choice, stated below), holding review interval, lead time and the member's own s-r gap
     fixed, restricted to PEM101's 112 forecast-eligible items, and reports the median stock_value
     at two not_late levels (97% and 98%, +/-0.5pp bins -- own choice, stated below).

Only pre-existing, shared inputs and engine code are used (phaseJ3_calibration_engine.py,
phaseI_sensitivity_engine.py, phaseE1_common.py, the cached CSVs, phaseJ3_2_grid_PEM101.csv). No
new database access. This script and its outputs are independent of, and were written without
reading, src/investigations/phase22_modeler*.py or output/summary/phase22_modeler_*.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, load_scope
import phaseI_sensitivity_engine as eng
from phaseJ3_calibration_engine import (
    load_raw, determine_validation_end, build_full_daily_series, simulate_months_of_demand,
    DAYS_PER_MONTH, CALIBRATION_SCORE_START, CALIBRATION_END,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase22_validator")

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
GRID_FILE = os.path.join(SUMMARY_DIR, "phaseJ3_2_grid_PEM101.csv")
INV_FILE = os.path.join(PROJECT_ROOT, "output", "data", "phaseI_inventory_exact_351items.csv")

TOL_NOTLATE_PP = 3.0
TOL_STOCKVAL_PCT = 15.0
STOCK_DEFS = ["current", "fg_prefixed_only", "all_stockholding_except_qa_fmto_fmts"]

# Own choice, stated: reorder-level sweep for the trade-off curve, matching the original
# calibration grid's own r_months exploration range (0.25 .. 6.0 months), 12 points.
R_SWEEP = np.linspace(0.25, 6.0, 12)

# Own choice, stated: not_late levels and bin half-width for the curve's median stock_value.
# 97% / 98% picked because they sit inside the dense middle of the not_late range this ensemble's
# curve actually produces (checked below, before finalizing) and are round, decision-relevant
# service levels. +/-0.5pp keeps bins narrow while leaving enough points per bin to median over.
NOTLATE_LEVELS_PCT = [97.0, 98.0]
NOTLATE_BIN_HALFWIDTH_PP = 0.5


# ================================================================================================
# Part 1 -- deduplicated ensemble
# ================================================================================================

def resolve_warehouse_sets(config: dict, pem101_codes: list) -> dict:
    """Independently resolves the 3 usable-stock definitions' warehouse-code sets for PEM101,
    restricted to PEM101's own scope inventory rows (per task instruction) -- NOT assumed, NOT
    copied from any Modeler file."""
    inv = pd.read_csv(INV_FILE)
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    inv_div = inv[inv["itemcode"].isin(pem101_codes)].copy()

    all_wh_pem101 = sorted(inv_div["warehouse"].unique().tolist())
    current = config["phase_e1_assumptions"]["sellable_warehouse_codes"]["PEM101"]
    fg_only = eng.fg_prefixed_warehouses(all_wh_pem101)
    all_stock = eng.current_stockholding_warehouses(inv_div)

    # Reference only (not used in dedup): what fg_prefixed_only resolves to if the warehouse-code
    # universe is NOT restricted to PEM101 (i.e. exactly how phaseJ3_calibration_engine.py's own
    # build_division_bundle actually computed it, from the full 351-item cached pull). Reported
    # because it differs from the PEM101-restricted set this task asked for -- see report.
    all_wh_full = sorted(inv["warehouse"].unique().tolist())
    fg_only_unrestricted = eng.fg_prefixed_warehouses(all_wh_full)

    return {
        "current": sorted(current),
        "fg_prefixed_only": sorted(fg_only),
        "all_stockholding_except_qa_fmto_fmts": sorted(all_stock),
        "fg_prefixed_only_unrestricted_reference_only": sorted(fg_only_unrestricted),
    }


def build_deduplicated_ensemble(grid: pd.DataFrame, wh_sets: dict) -> pd.DataFrame:
    """METRICS.md Sec.22 robust_ensemble = grid points within Sec.20 tolerance on BOTH windows,
    per stock definition (validation-period set is non-empty here, so no calibration-only
    fallback is needed -- checked below). Deduplication rule (this task): two members are
    identical iff every grid parameter (r_months, s_months, review_interval_days,
    lead_time_days) matches AND their resolved warehouse sets are identical."""
    params = ["r_months", "s_months", "review_interval_days", "lead_time_days"]
    rows = []
    pass_counts = {}
    for d in STOCK_DEFS:
        mask = (
            (grid["calib_notlate_diff_pp"] <= TOL_NOTLATE_PP)
            & (grid["valid_notlate_diff_pp"] <= TOL_NOTLATE_PP)
            & (grid[f"calib_stockval_pctdiff_{d}"] <= TOL_STOCKVAL_PCT)
            & (grid[f"valid_stockval_pctdiff_{d}"] <= TOL_STOCKVAL_PCT)
        )
        pass_counts[d] = int(mask.sum())
        sub = grid.loc[mask, params].copy()
        sub["stock_def"] = d
        sub["warehouse_set"] = "|".join(wh_sets[d])
        rows.append(sub)
    all_passing = pd.concat(rows, ignore_index=True)

    # Dedup key = (r,s,review,lead,warehouse_set-as-string). Two stock_defs with an IDENTICAL
    # resolved warehouse set would collapse here; none do for PEM101 (checked in report).
    dedup_key = params + ["warehouse_set"]
    deduped = all_passing.drop_duplicates(subset=dedup_key).reset_index(drop=True)

    # Secondary diagnostic (not the reported ensemble size): how many distinct grid-PARAMETER
    # tuples (ignoring which stock_def/warehouse-set produced them) are in the union -- reveals
    # whether the same (r,s,review,lead) point independently qualifies under >1 definition even
    # though those definitions' warehouse sets differ (it does, for current vs.
    # all_stockholding_except_qa_fmto_fmts -- see report).
    n_unique_param_tuples = all_passing.drop_duplicates(subset=params).shape[0]

    return all_passing, deduped, pass_counts, n_unique_param_tuples


# ================================================================================================
# Part 2 -- range_ratio / median_Min for the 3 focus codes
# ================================================================================================

def compute_mean_daily_demand(raw: pd.DataFrame, codes: list, validation_end: str) -> dict:
    raw_codes = raw[raw["itemcode"].isin(codes)].copy()
    bundle = build_full_daily_series(raw_codes, codes, "2024-01-01", validation_end)
    return {c: float(bundle["series"][c].mean()) for c in codes}


def compute_range_ratio_median_min(deduped: pd.DataFrame, focus_codes: list,
                                    mean_daily_demand: dict) -> pd.DataFrame:
    out = []
    for code in focus_codes:
        mdd = mean_daily_demand[code]
        min_e_values = (deduped["r_months"].to_numpy() * DAYS_PER_MONTH * mdd)
        min_e_values = min_e_values[min_e_values > 0]  # Sec.22: "members with Min_e > 0"
        n_zero = int((deduped["r_months"].to_numpy() * DAYS_PER_MONTH * mdd <= 0).sum())
        if len(min_e_values) == 0:
            out.append({"item_code": code, "mean_daily_demand": mdd, "n_ensemble_members": len(deduped),
                        "n_min_e_zero": n_zero, "range_ratio": np.nan, "median_Min": np.nan,
                        "min_Min_e": np.nan, "max_Min_e": np.nan})
            continue
        out.append({
            "item_code": code, "mean_daily_demand": mdd, "n_ensemble_members": len(deduped),
            "n_min_e_zero": n_zero,
            "range_ratio": float(min_e_values.max() / min_e_values.min()),
            "median_Min": float(np.median(min_e_values)),
            "min_Min_e": float(min_e_values.min()),
            "max_Min_e": float(min_e_values.max()),
        })
    return pd.DataFrame(out)


# ================================================================================================
# Part 3 -- trade-off curve: median stock_value at two not_late levels
# ================================================================================================

def build_pem101_bundle_for_curve(config: dict, raw: pd.DataFrame, validation_end: str) -> dict:
    scope = load_scope(config)
    elig = scope[scope["eligible_for_policy"]]
    codes = sorted(elig["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)].copy()
    daily_bundle = build_full_daily_series(raw_div, codes, "2024-01-01", validation_end)
    unit_cost_df = eng.compute_unit_cost_from_raw(raw_div, codes, 12).set_index("itemcode")
    return {"codes": codes, "daily_series": daily_bundle["series"], "day_index": daily_bundle["day_index"],
            "unit_cost_df": unit_cost_df}


def window_mask(day_index: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    return (day_index >= pd.Timestamp(start)) & (day_index <= pd.Timestamp(end))


def simulate_curve_point(bundle: dict, r_months: float, s_months: float, review_interval_days: int,
                          lead_time_days: int, score_mask: np.ndarray) -> dict:
    unit_cost = bundle["unit_cost_df"]["unit_cost"]
    demand_tot = shipped_tot = 0.0
    stockval_days = None
    for code in bundle["codes"]:
        qty = bundle["daily_series"][code]
        mean_d = qty.mean()
        if mean_d <= 0:
            continue
        sim = simulate_months_of_demand(qty, r_months, s_months, review_interval_days, lead_time_days,
                                         initial_stock=s_months * DAYS_PER_MONTH * mean_d, mean_daily_demand=mean_d)
        demand_tot += sim["daily_demand"][score_mask].sum()
        shipped_tot += sim["daily_shipped"][score_mask].sum()
        uc = unit_cost.get(code, np.nan)
        if pd.notna(uc):
            item_val = sim["daily_on_hand"][score_mask] * uc
            stockval_days = item_val if stockval_days is None else stockval_days + item_val
    not_late = shipped_tot / demand_tot if demand_tot > 0 else np.nan
    stock_value = float(stockval_days.mean()) if stockval_days is not None else np.nan
    return {"not_late": not_late, "stock_value": stock_value}


def build_tradeoff_curve(bundle: dict, deduped: pd.DataFrame) -> pd.DataFrame:
    score_mask = window_mask(bundle["day_index"], CALIBRATION_SCORE_START, CALIBRATION_END)
    members = deduped.drop_duplicates(subset=["r_months", "s_months", "review_interval_days", "lead_time_days"])
    logger.info("Sweeping %d distinct (r,s,review,lead) ensemble-member parameter tuples x %d "
                "r_months points = %d curve grid points (stock_value/not_late do not depend on "
                "usable-stock definition, per phaseJ3_calibration_engine.py's own docstring, so "
                "members sharing identical (r,s,review,lead) across stock_defs are computed once).",
                len(members), len(R_SWEEP), len(members) * len(R_SWEEP))
    rows = []
    for _, m in members.iterrows():
        gap = m["s_months"] - m["r_months"]
        review = int(m["review_interval_days"])
        lead = int(m["lead_time_days"])
        for r_swept in R_SWEEP:
            s_swept = r_swept + gap
            if s_swept <= 0:
                continue
            res = simulate_curve_point(bundle, float(r_swept), float(s_swept), review, lead, score_mask)
            rows.append({
                "member_r_months": m["r_months"], "member_s_months": m["s_months"],
                "review_interval_days": review, "lead_time_days": lead, "gap_months": gap,
                "r_swept": float(r_swept), "s_swept": float(s_swept),
                "not_late": res["not_late"], "stock_value": res["stock_value"],
            })
    return pd.DataFrame(rows)


def summarize_curve_at_levels(curve: pd.DataFrame, levels_pct: list, halfwidth_pp: float) -> pd.DataFrame:
    curve = curve.dropna(subset=["not_late", "stock_value"]).copy()
    curve["not_late_pct"] = curve["not_late"] * 100.0
    out = []
    for level in levels_pct:
        lo, hi = level - halfwidth_pp, level + halfwidth_pp
        in_bin = curve[(curve["not_late_pct"] >= lo) & (curve["not_late_pct"] <= hi)]
        out.append({
            "not_late_level_pct": level, "bin_lo_pct": lo, "bin_hi_pct": hi,
            "n_points_in_bin": len(in_bin),
            "median_stock_value": float(in_bin["stock_value"].median()) if len(in_bin) else np.nan,
            "min_stock_value": float(in_bin["stock_value"].min()) if len(in_bin) else np.nan,
            "max_stock_value": float(in_bin["stock_value"].max()) if len(in_bin) else np.nan,
        })
    return pd.DataFrame(out)


# ================================================================================================
# Main
# ================================================================================================

def main():
    config = load_config()
    scope = load_scope(config)
    pem101_codes = sorted(scope["code"].unique())
    focus_codes = list(config["pilot_item_codes"])

    grid = pd.read_csv(GRID_FILE)
    logger.info("Loaded %d rows from %s (pre-existing shared input).", len(grid), GRID_FILE)

    wh_sets = resolve_warehouse_sets(config, pem101_codes)
    logger.info("Resolved warehouse sets (PEM101-restricted): current=%s fg_prefixed_only=%s "
                "all_stockholding_except_qa_fmto_fmts=%s [unrestricted-reference fg_prefixed_only=%s]",
                wh_sets["current"], wh_sets["fg_prefixed_only"],
                wh_sets["all_stockholding_except_qa_fmto_fmts"],
                wh_sets["fg_prefixed_only_unrestricted_reference_only"])

    all_passing, deduped, pass_counts, n_unique_param_tuples = build_deduplicated_ensemble(grid, wh_sets)
    logger.info("Passing counts per definition: %s. Union of distinct (r,s,review,lead) tuples "
                "(ignoring stock_def/warehouse identity) = %d. Deduplicated ensemble size "
                "(task's literal rule: params AND warehouse_set both match) = %d.",
                pass_counts, n_unique_param_tuples, len(deduped))

    all_passing.to_csv(os.path.join(SUMMARY_DIR, "phase22_validator_all_passing_PEM101.csv"), index=False)
    deduped.to_csv(os.path.join(SUMMARY_DIR, "phase22_validator_deduped_ensemble_PEM101.csv"), index=False)

    raw, inv = load_raw()
    validation_end = determine_validation_end(raw)
    logger.info("validation_end (phaseJ3_calibration_engine.determine_validation_end) = %s", validation_end)

    mean_daily_demand = compute_mean_daily_demand(raw, focus_codes, validation_end)
    logger.info("Mean daily demand, 2024-01-01..%s: %s", validation_end, mean_daily_demand)

    focus_df = compute_range_ratio_median_min(deduped, focus_codes, mean_daily_demand)
    focus_df.to_csv(os.path.join(SUMMARY_DIR, "phase22_validator_focus_codes_range_ratio.csv"), index=False)

    bundle = build_pem101_bundle_for_curve(config, raw, validation_end)
    curve = build_tradeoff_curve(bundle, deduped)
    curve.to_csv(os.path.join(SUMMARY_DIR, "phase22_validator_tradeoff_curve_PEM101.csv"), index=False)

    curve_pct = curve.dropna(subset=["not_late"]).copy()
    curve_pct["not_late_pct"] = curve_pct["not_late"] * 100.0
    logger.info("Curve not_late range: %.4f%% to %.4f%% over %d valid points (out of %d rows).",
                curve_pct["not_late_pct"].min(), curve_pct["not_late_pct"].max(), len(curve_pct), len(curve))

    level_summary = summarize_curve_at_levels(curve, NOTLATE_LEVELS_PCT, NOTLATE_BIN_HALFWIDTH_PP)
    level_summary.to_csv(os.path.join(SUMMARY_DIR, "phase22_validator_curve_level_summary_PEM101.csv"), index=False)
    logger.info("Level summary:\n%s", level_summary.to_string(index=False))

    return {
        "wh_sets": wh_sets, "pass_counts": pass_counts, "n_unique_param_tuples": n_unique_param_tuples,
        "deduped_size": len(deduped), "validation_end": validation_end,
        "mean_daily_demand": mean_daily_demand, "focus_df": focus_df, "level_summary": level_summary,
        "curve_pct_range": (curve_pct["not_late_pct"].min(), curve_pct["not_late_pct"].max()),
    }


if __name__ == "__main__":
    result = main()
    print(result)
