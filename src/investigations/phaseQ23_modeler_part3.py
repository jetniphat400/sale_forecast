"""Q23 Part 3 -- Modeler: re-run METRICS.md Sec.20 inverse calibration using omni_tendering
(combined Omni+Tendering) demand, for PEM103 and PEM107 ONLY (not PEM101, per this task's scope).

Reuses Phase J3's calibration engine (src/investigations/phaseJ3_calibration_engine.py) and its
grid/tolerance/targets/periods (src/investigations/phaseJ3_run_calibration.py) UNCHANGED. The ONE
thing that changes: the daily demand series driving the simulation is built from the Explorer's
combined-channel pull (output/data/phaseQ23_raw_sales_allchannels_351full.csv, revenue_type IN
('Omni Channel','Tendering')) instead of J3's Omni-only output/data/phaseI_raw_sales_351items.csv.

not_late / stock-value TARGETS are NOT changed -- they were computed from Cube_CES/inventory data
that was never itself restricted to Omni-only (src/investigations/phaseJ3_validator_reconciliation.py
Part B/C), so they remain valid targets for a combined-demand re-run.

unit_cost (feeds stock_value): computed from the SAME combined-channel raw pull by default (a
disclosed modeling choice, for internal consistency with the combined demand driving the
simulation) -- ALSO recomputed with the original Omni-only cost basis as a robustness check, both
reported, any conclusion-changing difference flagged explicitly.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseJ3_calibration_engine as jc  # noqa: E402
import phaseJ3_run_calibration as rc  # noqa: E402
import phaseI_sensitivity_engine as eng  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseQ23_modeler_part3")

SUMMARY_DIR = os.path.join(jc.PROJECT_ROOT, "output", "summary")
DATA_DIR = os.path.join(jc.PROJECT_ROOT, "output", "data")
COMBINED_RAW_FILE = os.path.join(DATA_DIR, "phaseQ23_raw_sales_allchannels_351full.csv")

DIVISIONS = ["PEM103", "PEM107"]


def load_combined_raw():
    raw = pd.read_csv(COMBINED_RAW_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    combined = raw[raw["revenue_type"].isin(["Omni Channel", "Tendering"])].copy()
    logger.info("Combined-channel raw: %d rows (of %d total, all revenue_types) after "
                "restricting to Omni Channel + Tendering.", len(combined), len(raw))
    return combined


def build_combined_bundle(config, division, combined_raw, inv, validation_end, omni_raw):
    """Same as jc.build_division_bundle but demand series comes from combined_raw. unit_cost is
    computed BOTH ways (combined-channel basis, the default/recommended one; Omni-only basis, a
    robustness check) and attached as two separate columns so downstream scoring can use either."""
    scope = jc.load_scope_for(config, division)
    codes = sorted(scope["code"].unique())
    raw_div_combined = combined_raw[combined_raw["itemcode"].isin(codes)].copy()
    raw_div_omni = omni_raw[omni_raw["itemcode"].isin(codes)].copy()
    inv_div = inv[inv["itemcode"].isin(codes)].copy()

    daily_bundle = jc.build_full_daily_series(raw_div_combined, codes, jc.CALIBRATION_START, validation_end)
    unit_cost_combined = eng.compute_unit_cost_from_raw(raw_div_combined, codes, 12).set_index("itemcode")
    unit_cost_omni = eng.compute_unit_cost_from_raw(raw_div_omni, codes, 12).set_index("itemcode")

    all_wh_codes = sorted(inv["warehouse"].unique().tolist())
    e1 = config["phase_e1_assumptions"]
    variants = {
        "current": e1["sellable_warehouse_codes"].get(division),
        "fg_prefixed_only": eng.fg_prefixed_warehouses(all_wh_codes),
        "all_stockholding_except_qa_fmto_fmts": eng.current_stockholding_warehouses(inv_div),
    }
    return {
        "division": division, "codes": codes, "daily_series": daily_bundle["series"],
        "day_index": daily_bundle["day_index"], "unit_cost_df": unit_cost_combined,
        "unit_cost_df_omni_basis": unit_cost_omni, "inv_div": inv_div, "sellable_variants": variants,
    }


def run_grid_for_bundle(bundle, unit_cost_col_df, label):
    """Identical grid loop to phaseJ3_run_calibration.run_division, but taking a pre-built bundle
    and letting the caller choose which unit_cost basis (combined or omni) scores stock_value."""
    day_index = bundle["day_index"]
    calib_mask = jc.window_mask(day_index, jc.CALIBRATION_SCORE_START, jc.CALIBRATION_END)
    valid_mask = jc.window_mask(day_index, jc.VALIDATION_START, day_index[-1].strftime("%Y-%m-%d"))
    unit_cost = unit_cost_col_df["unit_cost"]

    pairs = rc.rs_pairs()
    rows = []
    n_total = len(rc.REVIEW_INTERVAL_GRID) * len(rc.LEAD_TIME_GRID) * len(pairs)
    i = 0
    import time
    t0 = time.time()
    for review, lead, (r, s) in __import__("itertools").product(rc.REVIEW_INTERVAL_GRID, rc.LEAD_TIME_GRID, pairs):
        i += 1
        calib_demand = calib_shipped = valid_demand = valid_shipped = 0.0
        calib_stockval_days = valid_stockval_days = None
        n_items_simulated = 0
        for code in bundle["codes"]:
            qty = bundle["daily_series"][code]
            mean_d = qty.mean()
            if mean_d <= 0:
                continue
            uc = unit_cost.get(code, np.nan)
            sim = jc.simulate_months_of_demand(qty, r, s, review, lead,
                                                initial_stock=s * jc.DAYS_PER_MONTH * mean_d, mean_daily_demand=mean_d)
            n_items_simulated += 1
            calib_demand += sim["daily_demand"][calib_mask].sum()
            calib_shipped += sim["daily_shipped"][calib_mask].sum()
            valid_demand += sim["daily_demand"][valid_mask].sum()
            valid_shipped += sim["daily_shipped"][valid_mask].sum()
            if pd.notna(uc):
                item_calib_val = sim["daily_on_hand"][calib_mask] * uc
                item_valid_val = sim["daily_on_hand"][valid_mask] * uc
                calib_stockval_days = item_calib_val if calib_stockval_days is None else calib_stockval_days + item_calib_val
                valid_stockval_days = item_valid_val if valid_stockval_days is None else valid_stockval_days + item_valid_val
        rows.append({
            "r_months": r, "s_months": s, "review_interval_days": review, "lead_time_days": lead,
            "calib_not_late": calib_shipped / calib_demand if calib_demand > 0 else np.nan,
            "valid_not_late": valid_shipped / valid_demand if valid_demand > 0 else np.nan,
            "calib_stock_value": float(calib_stockval_days.mean()) if calib_stockval_days is not None else np.nan,
            "valid_stock_value": float(valid_stockval_days.mean()) if valid_stockval_days is not None else np.nan,
            "n_items_simulated": n_items_simulated,
        })
        if i % 1000 == 0:
            logger.info("[%s / %s] %d/%d grid points done (%.1fs elapsed)", bundle["division"], label, i, n_total, time.time() - t0)
    df = pd.DataFrame(rows)
    df["division"] = bundle["division"]
    df["unit_cost_basis"] = label
    return df


def score_and_identify(df, division, stock_target):
    df = df.copy()
    df["calib_stockval_pctdiff"] = 100 * (df["calib_stock_value"] - stock_target).abs() / stock_target
    df["valid_stockval_pctdiff"] = 100 * (df["valid_stock_value"] - stock_target).abs() / stock_target
    df["calib_notlate_diff_pp"] = 100 * (df["calib_not_late"] - rc.NOT_LATE_TARGET_CALIB[division]).abs()
    df["valid_notlate_diff_pp"] = 100 * (df["valid_not_late"] - rc.NOT_LATE_TARGET_VALID[division]).abs()
    passing = df[
        (df["calib_notlate_diff_pp"] <= rc.NOT_LATE_TOL_PP) &
        (df["calib_stockval_pctdiff"] <= rc.STOCK_VALUE_TOL_PCT) &
        (df["valid_notlate_diff_pp"] <= rc.NOT_LATE_TOL_PP) &
        (df["valid_stockval_pctdiff"] <= rc.STOCK_VALUE_TOL_PCT)
    ]
    ident = rc.identify_parameters(passing)
    best = None
    if len(passing):
        passing = passing.copy()
        passing["combined_error"] = (passing["calib_notlate_diff_pp"] + passing["valid_notlate_diff_pp"] +
                                     passing["calib_stockval_pctdiff"] / 5 + passing["valid_stockval_pctdiff"] / 5)
        best = passing.sort_values("combined_error").iloc[0].to_dict()
    return df, passing, ident, best


def main():
    config = jc.load_config()
    combined_raw = load_combined_raw()
    omni_raw, inv = jc.load_raw()  # jc.load_raw() reads the ORIGINAL Omni-only phaseI file + inv
    validation_end = jc.determine_validation_end(combined_raw)
    logger.info("Validation end (from combined-channel pull): %s", validation_end)

    all_summaries = []
    for division in DIVISIONS:
        bundle = build_combined_bundle(config, division, combined_raw, inv, validation_end, omni_raw)
        stock_targets = rc.STOCK_VALUE_TARGET_CURRENT
        logger.info("[%s] running grid, unit_cost basis=combined-channel (primary)...", division)
        df_combined_cost = run_grid_for_bundle(bundle, bundle["unit_cost_df"], "combined_channel")
        df_combined_cost.to_csv(os.path.join(SUMMARY_DIR, f"phaseQ23_part3_grid_{division}_combinedcost.csv"), index=False)

        logger.info("[%s] running grid, unit_cost basis=omni-only (robustness check)...", division)
        df_omni_cost = run_grid_for_bundle(bundle, bundle["unit_cost_df_omni_basis"], "omni_only")
        df_omni_cost.to_csv(os.path.join(SUMMARY_DIR, f"phaseQ23_part3_grid_{division}_omnicost.csv"), index=False)

        for label, df in [("combined_channel_unit_cost", df_combined_cost), ("omni_only_unit_cost", df_omni_cost)]:
            scored, passing, ident, best = score_and_identify(df, division, stock_targets[division])
            all_summaries.append({
                "division": division, "unit_cost_basis": label, "n_passing": len(passing), "n_total": len(scored),
                "identification": ident,
                "best_fit": {k: best[k] for k in ["r_months", "s_months", "review_interval_days", "lead_time_days",
                                                   "calib_not_late", "valid_not_late", "calib_stock_value",
                                                   "valid_stock_value"]} if best else None,
            })
            logger.info("[%s / %s] %d/%d combos pass both-window tolerance. Identification: %s",
                        division, label, len(passing), len(scored), ident)

    summary_df = pd.DataFrame(all_summaries)
    summary_df.to_json(os.path.join(SUMMARY_DIR, "phaseQ23_part3_calibration_summary.json"), orient="records", indent=2)

    print("\n" + "=" * 100)
    print("Q23 PART 3 -- COMBINED-DEMAND CALIBRATION SUMMARY (PEM103, PEM107)")
    print("=" * 100)
    for r in all_summaries:
        print(f"\n{r['division']} / {r['unit_cost_basis']}: {r['n_passing']}/{r['n_total']} pass")
        print("  identification:", r["identification"])
        print("  best_fit:", r["best_fit"])


if __name__ == "__main__":
    main()
