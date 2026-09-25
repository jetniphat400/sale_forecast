"""Phase 24, Part 2: PEM101 envelope width at the 3 not_late presets (Modeler).

Simulates all 80 distinct ensemble members AT THE EXACT preset r-values (not the locked curve's 20
grid points) to get the true min/median/max stock_value distribution across members at each
preset -- more precise than linearly interpolating the grid's own min/max columns between two
bracketing points. Reuses the SAME locked config.yaml trade_off_curve block (simulation_window,
warm_up, not_late_weighting) and the same 80 distinct members as Part 1/3 of the prior task.

No new database access -- reuses output/data/phaseI_raw_sales_351items.csv (cached) and
output/summary/phase23_dense_grid_PEM101.json (the prior task's presets, for the exact r-values).
"""
import json
import logging
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, load_scope
import phaseJ3_calibration_engine as jc
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase24_modeler_part2")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DAYS_PER_MONTH = 30.44
STOCK_VALUE_TOL_PCT = 15.0  # METRICS.md Sec.20, both-window calibration tolerance

TODAY_NOT_LATE_PCT = 98.28
TODAY_STOCK_VALUE_THB = 18247625.22


def main():
    config = load_config()
    members = pd.read_csv(os.path.join(SUMMARY_DIR, "phase23_ensemble_distinct_members_PEM101.csv"))
    assert len(members) == 80

    tc = config["trade_off_curve"]
    window = tc["simulation_window"]
    warmup = tc["warm_up"]

    with open(os.path.join(SUMMARY_DIR, "phase23_dense_grid_PEM101.json"), encoding="utf-8") as f:
        dense_grid = json.load(f)
    presets = dense_grid["presets"]
    logger.info("Loaded presets: %s", {k: v["r"] for k, v in presets.items()})

    scope = load_scope(config)
    elig = scope[scope["eligible_for_policy"]]
    codes = sorted(elig["code"].unique())
    logger.info("PEM101 eligible-for-policy scope: %d items.", len(codes))

    raw = pd.read_csv(os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv"))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw_div = raw[raw["itemcode"].isin(codes)].copy()

    daily_bundle = jc.build_full_daily_series(raw_div, codes, warmup["start"], window["end"])
    daily_series = daily_bundle["series"]
    day_index = daily_bundle["day_index"]

    unit_cost_df = eng.compute_unit_cost_from_raw(raw_div, codes, 12).set_index("itemcode")
    unit_cost = unit_cost_df["unit_cost"]

    scoring_mask = jc.window_mask(day_index, window["start"], window["end"])

    results = {}
    t0 = time.time()
    for preset_name, preset in presets.items():
        r_new = preset["r"]
        member_svs = []
        member_nls = []
        for mi, m in members.iterrows():
            gap = m["s_months"] - m["r_months"]
            s_new = r_new + gap
            review = int(m["review_interval_days"])
            lead = int(m["lead_time_days"])
            demand_sum = shipped_sum = 0.0
            stockval_days = None
            for c in codes:
                qty = daily_series[c]
                mean_d = qty.mean()
                if mean_d <= 0:
                    continue
                sim = jc.simulate_months_of_demand(
                    qty, r_new, s_new, review, lead,
                    initial_stock=s_new * DAYS_PER_MONTH * mean_d, mean_daily_demand=mean_d)
                demand_sum += sim["daily_demand"][scoring_mask].sum()
                shipped_sum += sim["daily_shipped"][scoring_mask].sum()
                uc = unit_cost.get(c, np.nan)
                if pd.notna(uc):
                    v = sim["daily_on_hand"][scoring_mask] * uc
                    stockval_days = v if stockval_days is None else stockval_days + v
            not_late = shipped_sum / demand_sum if demand_sum > 0 else np.nan
            stock_value = float(stockval_days.mean()) if stockval_days is not None else np.nan
            member_svs.append(stock_value)
            member_nls.append(not_late)
        sv = pd.Series(member_svs).dropna()
        nl = pd.Series(member_nls).dropna()
        min_sv, med_sv, max_sv = float(sv.min()), float(sv.median()), float(sv.max())
        width = max_sv - min_sv
        width_pct_of_median = 100 * width / med_sv
        results[preset_name] = {
            "r": r_new, "target_not_late_pct": preset["not_late_pct"],
            "n_members": int(len(sv)),
            "not_late_median_across_members_pct": float(nl.median() * 100),
            "stock_value_min": min_sv, "stock_value_median": med_sv, "stock_value_max": max_sv,
            "band_width_thb": width, "band_width_pct_of_median": width_pct_of_median,
        }
        logger.info("[%s] r=%.4f: min=%.2f median=%.2f max=%.2f width=%.2f (%.1f%% of median), %.1fs elapsed",
                    preset_name, r_new, min_sv, med_sv, max_sv, width, width_pct_of_median, time.time() - t0)

    out_df = pd.DataFrame(results).T
    out_df.to_csv(os.path.join(SUMMARY_DIR, "phase24_modeler_preset_bands.csv"))
    print("\n=== PRESET BANDS (min/median/max stock_value across 80 members, exact preset r) ===")
    print(out_df.to_string())

    # --- distinguishability check at preset 1 (today_lowest_stock) ---
    p1 = results["today_lowest_stock"]
    tol_lo = p1["stock_value_median"] * (1 - STOCK_VALUE_TOL_PCT / 100)
    tol_hi = p1["stock_value_median"] * (1 + STOCK_VALUE_TOL_PCT / 100)
    today_in_tol_band = tol_lo <= TODAY_STOCK_VALUE_THB <= tol_hi
    today_in_member_band = p1["stock_value_min"] <= TODAY_STOCK_VALUE_THB <= p1["stock_value_max"]
    saving = TODAY_STOCK_VALUE_THB - p1["stock_value_median"]
    saving_pct = 100 * saving / TODAY_STOCK_VALUE_THB

    print(f"\n=== DISTINGUISHABILITY CHECK (preset 1: today's not_late at lowest median stock) ===")
    print(f"Today's stock_value: THB {TODAY_STOCK_VALUE_THB:,.2f} (cited: output/summary/phaseJ3_validator_stock_value_summary.csv)")
    print(f"Preset 1 median stock_value: THB {p1['stock_value_median']:,.2f}")
    print(f"Apparent saving: THB {saving:,.2f} ({saving_pct:.2f}%)")
    print(f"METRICS.md Sec.20 tolerance band (+/-{STOCK_VALUE_TOL_PCT}% of preset 1 median): "
          f"THB {tol_lo:,.2f} to THB {tol_hi:,.2f}")
    print(f"Today's actual stock_value falls INSIDE this tolerance band: {today_in_tol_band}")
    print(f"Preset 1's own across-member band (min-max at this exact r): "
          f"THB {p1['stock_value_min']:,.2f} to THB {p1['stock_value_max']:,.2f} "
          f"({p1['band_width_pct_of_median']:.1f}% of median)")
    print(f"Today's actual stock_value falls INSIDE the across-member band: {today_in_member_band}")

    # --- cost of moving from today's not_late to 99% (preset 3) ---
    p3 = results["stretch_99pct"]
    cost_to_99 = p3["stock_value_median"] - p1["stock_value_median"]
    cost_to_99_pct = 100 * cost_to_99 / p1["stock_value_median"]
    print(f"\n=== COST OF MOVING FROM TODAY'S not_late TO 99% ===")
    print(f"Preset 1 (today's not_late) median: THB {p1['stock_value_median']:,.2f} "
          f"(band THB {p1['stock_value_min']:,.2f}-{p1['stock_value_max']:,.2f})")
    print(f"Preset 3 (99%) median: THB {p3['stock_value_median']:,.2f} "
          f"(band THB {p3['stock_value_min']:,.2f}-{p3['stock_value_max']:,.2f})")
    print(f"Cost: THB {cost_to_99:,.2f} ({cost_to_99_pct:.1f}% increase over preset 1's median)")

    verdict = {
        "today_stock_value_thb": TODAY_STOCK_VALUE_THB,
        "preset1_median_thb": p1["stock_value_median"],
        "saving_thb": saving, "saving_pct": saving_pct,
        "tolerance_band_thb": [tol_lo, tol_hi],
        "today_in_tolerance_band": today_in_tol_band,
        "member_band_thb": [p1["stock_value_min"], p1["stock_value_max"]],
        "today_in_member_band": today_in_member_band,
        "distinguishable_from_zero": not (today_in_tol_band or today_in_member_band),
        "cost_to_99pct_thb": cost_to_99, "cost_to_99pct_pct": cost_to_99_pct,
    }
    with open(os.path.join(SUMMARY_DIR, "phase24_modeler_distinguishability.json"), "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2)
    print(f"\nDISTINGUISHABLE FROM ZERO: {verdict['distinguishable_from_zero']}")


if __name__ == "__main__":
    main()
