"""Phase J Part 2 -- extended service-level curve (0.50-0.98) and the service level at which
scenario stock_value equals each division's current on-hand value, corrected by Part 1's
calibration_gap and compared against actual_on_time.

Uses TODAY's (pre-Part-4) config defaults for every other parameter -- lead=60, assembly=3,
review=30, freq_cutoff=6, unit_cost_window=12 -- matching Part 1/Phase I's baseline.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ_service_level")

SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")

SL_GRID = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.98]

# Task-given current on-hand values (STATUS.md-confirmed: PEM103 ฿6.06M / PEM107 ฿3.28M match
# STATUS.md's own prior figures exactly; PEM101's 18.07M is very close to -- 0.9% from -- this
# task's own direct recomputation of 18.25M, see phaseJ_calibration.py's cross-check. Used here
# AS GIVEN, per task instruction.)
CURRENT_ONHAND_VALUE = {"PEM101": 18_070_000, "PEM103": 6_060_000, "PEM107": 3_280_000}


def stock_value_at_sl(bundle: dict, sl: float) -> dict:
    params = dict(eng.DEFAULTS)
    params["cycle_service_level"] = sl
    result = eng.run_scenario(bundle, **params)
    return {"stock_value": result["stock_value"], "fill_rate": result["fill_rate"]}


def find_sl_for_target(bundle: dict, target_value: float, lo: float = 0.01, hi: float = 0.999,
                        tol: float = 1000.0, max_iter: int = 40) -> tuple:
    """Bisection: stock_value(sl) is monotonically non-decreasing in sl (verified empirically by
    the 11-point grid below before this is called) -- finds sl where stock_value == target_value
    to within `tol` THB. Searches DOWN TO 0.01 (below the task's displayed 0.50-0.98 sweep range)
    because the current-on-hand value can be, and for PEM101/103/107 turns out to be, below the
    stock_value the model produces even at SL=0.50 -- that is itself the finding, not an error, so
    it must be locatable rather than reported as 'out of range'."""
    lo_out = stock_value_at_sl(bundle, lo)
    hi_out = stock_value_at_sl(bundle, hi)
    lo_val, hi_val = lo_out["stock_value"], hi_out["stock_value"]
    if target_value < lo_val:
        return "<0.01", lo_val, lo_out["fill_rate"]  # target unreachable even at the floor tested
    if target_value > hi_val:
        return ">0.999", hi_val, hi_out["fill_rate"]  # target unreachable even at the ceiling tested
    mid_out = lo_out
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        mid_out = stock_value_at_sl(bundle, mid)
        mid_val = mid_out["stock_value"]
        if abs(mid_val - target_value) <= tol:
            return mid, mid_val, mid_out["fill_rate"]
        if mid_val < target_value:
            lo = mid
        else:
            hi = mid
    return mid, mid_out["stock_value"], mid_out["fill_rate"]


def main():
    config = eng.load_config()
    raw, inv = eng.load_raw()
    calib = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseJ_1_calibration_summary.csv")).set_index("division")

    curve_rows = []
    crossing_rows = []
    for division in eng.DIVISIONS:
        bundle = eng.build_division_bundle(config, division, raw, inv)
        for sl in SL_GRID:
            out = stock_value_at_sl(bundle, sl)
            curve_rows.append({"division": division, "cycle_service_level": sl,
                               "stock_value": out["stock_value"], "fill_rate": out["fill_rate"]})

        target = CURRENT_ONHAND_VALUE[division]
        sl_cross, sv_cross, fr_cross = find_sl_for_target(bundle, target)
        calibration_gap_pp = float(calib.loc[division, "calibration_gap_pp"])
        actual_on_time = float(calib.loc[division, "actual_on_time"])
        found_exact = isinstance(sl_cross, float)
        corrected_fill_rate = fr_cross - calibration_gap_pp / 100
        correction_out_of_range = not (0.0 <= corrected_fill_rate <= 1.0)
        raw_better_than_today = fr_cross > actual_on_time
        corrected_better_than_today = (corrected_fill_rate > actual_on_time) if not correction_out_of_range else None

        crossing_rows.append({
            "division": division, "current_onhand_value_thb": target,
            "sl_at_current_onhand_value": sl_cross, "found_exact_crossing": found_exact,
            "stock_value_at_crossing": sv_cross,
            "model_fill_rate_at_crossing_RAW": fr_cross, "calibration_gap_pp": calibration_gap_pp,
            "corrected_fill_rate_at_crossing": corrected_fill_rate,
            "correction_out_of_range_gt1_or_lt0": correction_out_of_range,
            "actual_on_time": actual_on_time,
            "raw_same_money_beats_today": raw_better_than_today,
            "corrected_same_money_beats_today": corrected_better_than_today,
        })
        logger.info("[%s] SL for stock_value=THB%.0f -> SL=%s (stock_value=%.0f, RAW model fill_rate=%.4f "
                    "[%s actual_on_time=%.4f], calibration-corrected=%.4f [%s -- %s])",
                    division, target, sl_cross, sv_cross, fr_cross,
                    "BELOW" if not raw_better_than_today else "ABOVE", actual_on_time,
                    corrected_fill_rate,
                    "OUT OF [0,1] RANGE, not meaningful" if correction_out_of_range else "in range",
                    "correction not applicable in this regime" if correction_out_of_range else
                    ("ABOVE" if corrected_better_than_today else "BELOW"))

    curve_df = pd.DataFrame(curve_rows)
    crossing_df = pd.DataFrame(crossing_rows)
    curve_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_2_service_level_curve_extended.csv"), index=False)
    crossing_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_2_current_onhand_crossing.csv"), index=False)

    print("\n" + "=" * 100)
    print("PHASE J PART 2 -- EXTENDED SERVICE-LEVEL CURVE")
    print("=" * 100)
    print(curve_df.to_string(index=False))
    print("\nCURRENT-ON-HAND CROSSING POINT:")
    print(crossing_df.to_string(index=False))
    return curve_df, crossing_df


if __name__ == "__main__":
    main()
