"""Phase J3 Part 2 -- Modeler: run METRICS.md Sec.20 inverse_calibration grid search per division.

Targets (from the Part 1 Validator, output/summary/phaseJ3_validator_reconciliation.md,
independently recomputed on the cached Cube_CES pull, unit-weighted not_late per METRICS.md
Sec.19, ForecastDelDate-windowed per METRICS.md Sec.18/19/20 convention):

    Calibration (2024-01-01 to 2025-12-31): PEM101 97.70%, PEM103 90.89%, PEM107 86.61%
    Validation  (2026-01-01 onward, partial year): PEM101 98.28%, PEM103 96.56%, PEM107 76.54%
    Current on-hand stock value (single snapshot, Cube_Inventory_Exact, "current" sellable-
    warehouse definition): PEM101 THB 18.25M, PEM103 THB 6.06M, PEM107 THB 3.40M

Grid bounds (per this task's own instruction: "Build the grid around what Explorer D found rather
than the old assumptions"):
  - review_interval_days: Explorer D's per-item-typical cadence (median 36-58 days across
    divisions, p75 up to 133) is far longer than the originally-suggested "continuous through 30
    days" -- the grid is extended to span both: [1 (continuous), 7, 14, 30, 60, 90, 130].
  - lead_time_days: Explorer D's decisive test (cube_final) FAILED AGAIN on a clean, uninterrupted
    connection this session -- contradicting the earlier "process-kill artifact" theory (DATA_MAP.md
    Trap 7, now itself corrected) -- so no batch-to-availability time could be derived. Falling back
    to the only other data-derived lead-time evidence in this project (DATA_MAP.md §1, Cube_PO_Exact:
    16-189 days observed, mean 70) plus the business-confirmed 45-60 day procurement figure
    (STATUS.md Section 8.1) and Phase E1's own sensitivity point (75 days): [7, 15, 30, 45, 60, 75, 90].
    Explicitly flagged: this bound is NOT informed by Explorer D's batch data as the task intended --
    a real, disclosed limitation.
  - r_months (reorder level, months of mean demand): [0.25, 0.5, 1, 1.5, 2, 3]
  - s_months (order-up-to level, months of mean demand): [0.5, 1, 1.5, 2, 2.5, 3, 4, 5], filtered to
    s_months > r_months.

Tolerance (METRICS.md Sec.20): not_late within +-3 points AND stock value within +-15%.
Identified (METRICS.md Sec.20): every combination that passes tolerance on BOTH calibration and
validation agrees on that parameter within one grid step.

No new database access -- reuses the calibration engine's cached-data bundles.
"""
import itertools
import logging
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseJ3_calibration_engine as jc
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ3_run_calibration")

SUMMARY_DIR = os.path.join(jc.PROJECT_ROOT, "output", "summary")

REVIEW_INTERVAL_GRID = [1, 7, 14, 30, 60, 90, 130]
LEAD_TIME_GRID = [1, 3, 5, 7, 15, 30, 45, 60, 75, 90]
R_MONTHS_GRID = [0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6]
S_MONTHS_GRID = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8]
# NOTE (revised after first pass): the first, narrower grid (lead 7-90, r 0.25-3, s 0.5-5) put
# PEM103/PEM107's best achievable not_late at the grid's own edge (r=3, s=5, lead=7) in both
# cases -- meaning the grid was truncating the true optimum, not reflecting a real ceiling in the
# data. Extended lead_time_days down to 1 day and r/s_months up to 6/8 months so the search space
# no longer clips against its own boundary. Disclosed here, not silently widened without a trace.

NOT_LATE_TARGET_CALIB = {"PEM101": 0.9770, "PEM103": 0.9089, "PEM107": 0.8661}
NOT_LATE_TARGET_VALID = {"PEM101": 0.9828, "PEM103": 0.9656, "PEM107": 0.7654}
STOCK_VALUE_TARGET_CURRENT = {"PEM101": 18_250_000, "PEM103": 6_060_000, "PEM107": 3_400_000}

NOT_LATE_TOL_PP = 3.0
STOCK_VALUE_TOL_PCT = 15.0


def rs_pairs():
    return [(r, s) for r in R_MONTHS_GRID for s in S_MONTHS_GRID if s > r]


def stock_value_targets_all_definitions(config: dict, division: str, raw: pd.DataFrame, inv: pd.DataFrame) -> dict:
    """Current on-hand stock value under all 3 Phase I usable-stock definitions, for reporting
    identification against each -- the "current" figure matches the Validator's own number
    (cross-check), the other two are computed here the same way (no new DB access)."""
    scope = jc.load_scope_for(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)]
    inv_div = inv[inv["itemcode"].isin(codes)]
    unit_cost = eng.compute_unit_cost_from_raw(raw_div, codes, 12).set_index("itemcode")["unit_cost"]

    all_wh_codes = sorted(inv["warehouse"].unique().tolist())
    e1 = config["phase_e1_assumptions"]
    variants = {
        "current": e1["sellable_warehouse_codes"].get(division),
        "fg_prefixed_only": eng.fg_prefixed_warehouses(all_wh_codes),
        "all_stockholding_except_qa_fmto_fmts": eng.current_stockholding_warehouses(inv_div),
    }
    out = {}
    for name, wh_list in variants.items():
        sellable = eng.sellable_stock_per_item(inv_div, codes, wh_list).set_index("itemcode")["sellable_stock"]
        value = float((sellable * unit_cost.reindex(sellable.index).fillna(0)).sum())
        out[name] = value
    return out


def run_division(config, division, raw, inv, validation_end):
    logger.info("=" * 100)
    logger.info("DIVISION %s -- building bundle, validation_end=%s", division, validation_end)
    bundle = jc.build_division_bundle(config, division, raw, inv, validation_end)

    stock_targets = stock_value_targets_all_definitions(config, division, raw, inv)
    logger.info("[%s] stock value targets (all 3 definitions): %s", division, stock_targets)

    pairs = rs_pairs()
    rows = []
    t0 = time.time()
    n_total = len(REVIEW_INTERVAL_GRID) * len(LEAD_TIME_GRID) * len(pairs)
    i = 0
    for review, lead, (r, s) in itertools.product(REVIEW_INTERVAL_GRID, LEAD_TIME_GRID, pairs):
        i += 1
        point = jc.run_division_grid_point(bundle, r, s, review, lead)
        rows.append(point)
        if i % 200 == 0:
            logger.info("[%s] %d/%d grid points done (%.1fs elapsed)", division, i, n_total, time.time() - t0)
    logger.info("[%s] grid complete: %d points in %.1fs", division, len(rows), time.time() - t0)

    df = pd.DataFrame(rows)
    df["division"] = division
    for name, target in stock_targets.items():
        df[f"calib_stockval_pctdiff_{name}"] = 100 * (df["calib_stock_value"] - target).abs() / target
        df[f"valid_stockval_pctdiff_{name}"] = 100 * (df["valid_stock_value"] - target).abs() / target
    df["calib_notlate_diff_pp"] = 100 * (df["calib_not_late"] - NOT_LATE_TARGET_CALIB[division]).abs()
    df["valid_notlate_diff_pp"] = 100 * (df["valid_not_late"] - NOT_LATE_TARGET_VALID[division]).abs()

    return df


def identify_parameters(passing: pd.DataFrame) -> dict:
    result = {}
    for param, grid in [("r_months", R_MONTHS_GRID), ("s_months", S_MONTHS_GRID),
                        ("review_interval_days", REVIEW_INTERVAL_GRID), ("lead_time_days", LEAD_TIME_GRID)]:
        if len(passing) == 0:
            result[param] = {"identified": None, "reason": "no combination passes tolerance"}
            continue
        vals = sorted(passing[param].unique())
        grid_sorted = sorted(grid)
        span_steps = grid_sorted.index(max(vals)) - grid_sorted.index(min(vals))
        identified = span_steps <= 1
        result[param] = {"identified": identified, "values_seen": vals, "grid_step_span": span_steps,
                         "n_distinct": len(vals)}
    return result


def main():
    config = jc.load_config()
    raw, inv = jc.load_raw()
    validation_end = jc.determine_validation_end(raw)

    all_results = {}
    for division in jc.DIVISIONS:
        df = run_division(config, division, raw, inv, validation_end)
        df.to_csv(os.path.join(SUMMARY_DIR, f"phaseJ3_2_grid_{division}.csv"), index=False)
        all_results[division] = df

    summary_rows = []
    for division, df in all_results.items():
        for stockdef in ["current", "fg_prefixed_only", "all_stockholding_except_qa_fmto_fmts"]:
            passing = df[
                (df["calib_notlate_diff_pp"] <= NOT_LATE_TOL_PP) &
                (df[f"calib_stockval_pctdiff_{stockdef}"] <= STOCK_VALUE_TOL_PCT) &
                (df["valid_notlate_diff_pp"] <= NOT_LATE_TOL_PP) &
                (df[f"valid_stockval_pctdiff_{stockdef}"] <= STOCK_VALUE_TOL_PCT)
            ]
            ident = identify_parameters(passing)
            best = None
            if len(passing):
                passing = passing.copy()
                passing["combined_error"] = (passing["calib_notlate_diff_pp"] + passing["valid_notlate_diff_pp"] +
                                             passing[f"calib_stockval_pctdiff_{stockdef}"] / 5 +
                                             passing[f"valid_stockval_pctdiff_{stockdef}"] / 5)
                best = passing.sort_values("combined_error").iloc[0].to_dict()
            summary_rows.append({
                "division": division, "stock_definition": stockdef, "n_passing": len(passing),
                "n_total": len(df), "identification": ident,
                "best_fit": {k: best[k] for k in ["r_months", "s_months", "review_interval_days",
                                                   "lead_time_days", "calib_not_late", "valid_not_late",
                                                   "calib_stock_value", "valid_stock_value"]} if best else None,
            })
            logger.info("[%s / %s] %d/%d combos pass both-window tolerance. Identification: %s",
                        division, stockdef, len(passing), len(df), ident)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_json(os.path.join(SUMMARY_DIR, "phaseJ3_2_calibration_summary.json"), orient="records", indent=2)

    print("\n" + "=" * 100)
    print("PHASE J3 PART 2 -- CALIBRATION SUMMARY")
    print("=" * 100)
    for r in summary_rows:
        print(f"\n{r['division']} / {r['stock_definition']}: {r['n_passing']}/{r['n_total']} pass")
        print("  identification:", r["identification"])
        print("  best_fit:", r["best_fit"])

    return all_results, summary_rows


if __name__ == "__main__":
    main()
