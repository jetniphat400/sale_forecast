"""Phase J Part 5 -- independent Validator.

Written independently of src/investigations/phaseJ_calibration.py, phaseJ_service_level.py and
phaseJ_apply_robust_defaults.py (the Modeler's own new scripts for THIS task) -- does not import
or read any of them, or any output/summary/phaseJ_*.csv they wrote. Reuses only PRE-EXISTING,
previously-verified infrastructure that predates this task:
  - src/phaseE1_common.py, src/phaseE2_pilot_recompute.py (scope/series building -- data
    engineering, not a metric formula under test here).
  - src/investigations/phaseI_validator.py's validator_facts/validator_policy/validator_unit_cost/
    validator_minmax -- Phase I's OWN independent policy/LTD/Min/Max/stock_value implementation,
    itself already cross-checked against the Modeler's engine to floating-point precision
    (output/summary/phaseI_4_validator_comparison.csv, 19/19 match) -- reusing it here checks Part
    4's NEW default (assembly=7) through a genuinely independent code path from
    phaseI_sensitivity_engine.py (which src/investigations/phaseJ_apply_robust_defaults.py used).
METRICS.md Sec.18 (baseline_replay, actual_on_time, the SL-crossing search) is new this task and
has no prior independent implementation -- all of it is fresh code below, not adapted from
phaseJ_calibration.py/phaseJ_service_level.py.

Data source: the SAME cached pulls (output/data/phaseI_raw_sales_351items.csv,
phaseI_inventory_exact_351items.csv, phaseJ_cube_ces_351items.csv) -- a second database
connection for this Validator would violate the DATABASE ACCESS RULE (one attempt for the whole
task, already spent on Part 0's Cube_CES pull).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_scope, topdown_item_forecast, sellable_stock_per_item
from phaseE2_pilot_recompute import load_division_scope, build_monthly_series, build_daily_series
from phaseI_validator import validator_facts, validator_policy, validator_unit_cost, validator_minmax, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ_validator")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
RAW_SALES_FILE = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")
INV_FILE = os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv")
CES_FILE = os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv")
DIVISIONS = ["PEM101", "PEM103", "PEM107"]

BASELINE_LEAD, BASELINE_ASSEMBLY, BASELINE_REVIEW = 60, 3, 30       # today's (pre-Part-4) values
NEW_DEFAULT_LEAD, NEW_DEFAULT_ASSEMBLY, NEW_DEFAULT_REVIEW, NEW_DEFAULT_SL = 60, 7, 30, 0.95
FREQ_CUTOFF_DEFAULT, UNIT_COST_WINDOW_DEFAULT = 6.0, 12
HORIZON_START, HORIZON_END = "2024-01-01", "2026-07-31"
CURRENT_ONHAND_VALUE = {"PEM101": 18_070_000, "PEM103": 6_060_000, "PEM107": 3_280_000}


def load_data():
    raw = pd.read_csv(RAW_SALES_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    inv = pd.read_csv(INV_FILE)
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    ces = pd.read_csv(CES_FILE)
    ces["ForecastDelDate"] = pd.to_datetime(ces["ForecastDelDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")
    return raw, inv, ces


def get_scope(config, division):
    return load_scope(config) if division == "PEM101" else load_division_scope(config, division)


# ---- Fresh, independent baseline-replay implementation (own control flow: a single function with
# a `reactive` flag, rather than two near-duplicate functions like the Modeler's) ----
def replay_current_policy(qty_daily: np.ndarray, current_min: float, current_max: float,
                           initial_stock: float, review_days: int, lead_time_days: int,
                           reactive: bool) -> dict:
    on_hand, on_order, backorder = float(initial_stock), 0.0, 0.0
    arrivals = {}
    demand_sum, shipped_sum = 0.0, 0.0
    cycles, cycle_stockouts, stockout_flag = 0, 0, False

    for day in range(len(qty_daily)):
        if day in arrivals:
            qty_in = arrivals.pop(day)
            on_order -= qty_in
            payoff = min(backorder, qty_in)
            backorder -= payoff
            on_hand += (qty_in - payoff)
            cycles += 1
            cycle_stockouts += int(stockout_flag)
            stockout_flag = False

        if not reactive and day % review_days == 0:
            position = on_hand + on_order
            if position <= current_min:
                qty_order = current_max - position
                if qty_order > 0:
                    on_order += qty_order
                    due = day + lead_time_days
                    if due < len(qty_daily):
                        arrivals[due] = arrivals.get(due, 0.0) + qty_order

        need = float(qty_daily[day])
        demand_sum += need
        shortfall = max(0.0, need - on_hand)
        shipped_sum += min(on_hand, need)
        on_hand = max(0.0, on_hand - need)
        if shortfall > 0:
            backorder += shortfall
            stockout_flag = True
            if reactive:
                on_order += shortfall
                due = day + lead_time_days
                if due < len(qty_daily):
                    arrivals[due] = arrivals.get(due, 0.0) + shortfall

    cycles += 1
    cycle_stockouts += int(stockout_flag)
    return {"total_demand": demand_sum, "total_shipped": shipped_sum,
            "fill_rate": (shipped_sum / demand_sum) if demand_sum > 0 else None,
            "cycles": cycles, "cycle_stockouts": cycle_stockouts}


def current_min_max_sellable(inv_div: pd.DataFrame, codes: list, sellable_wh: list) -> dict:
    sub = inv_div[inv_div["warehouse"].isin(sellable_wh)]
    g = sub.groupby("itemcode")[["minimum", "maximum"]].sum()
    out = {}
    for c in codes:
        if c in g.index:
            out[c] = {"min": float(g.loc[c, "minimum"]), "max": float(g.loc[c, "maximum"])}
        else:
            out[c] = {"min": 0.0, "max": 0.0}
    return out


def baseline_and_actual_on_time(config, division, raw, inv, ces, sellable_wh):
    scope = get_scope(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)]
    inv_div = inv[inv["itemcode"].isin(codes)]
    daily = build_daily_series(raw_div, codes)

    onhand = sellable_stock_per_item(inv_div, codes, sellable_wh).set_index("itemcode")["sellable_stock"].to_dict()
    mm = current_min_max_sellable(inv_div, codes, sellable_wh)
    lead_time_days = BASELINE_LEAD + BASELINE_ASSEMBLY

    total_demand, total_shipped = 0.0, 0.0
    for code in codes:
        qty_d, _ = daily[code]
        m = mm[code]
        has_setting = (m["min"] > 0) or (m["max"] > 0)
        init = onhand.get(code, 0.0)
        r = replay_current_policy(qty_d, m["min"], m["max"], init, BASELINE_REVIEW, lead_time_days,
                                   reactive=not has_setting)
        total_demand += r["total_demand"]
        total_shipped += r["total_shipped"]
    baseline_fill_rate = total_shipped / total_demand if total_demand > 0 else float("nan")

    ces_div = ces[ces["ItemCode"].isin(codes)]
    win = ces_div[(ces_div["ForecastDelDate"] >= HORIZON_START) & (ces_div["ForecastDelDate"] <= HORIZON_END)]
    scored = win[win["ActualDelDate"].notna()]
    on_time_mask = scored["ActualDelDate"] <= scored["ForecastDelDate"]
    total_units = float(scored["ActualQty"].sum())
    on_time_units = float(scored.loc[on_time_mask, "ActualQty"].sum())
    actual_on_time = on_time_units / total_units if total_units > 0 else float("nan")

    return baseline_fill_rate, actual_on_time


def stock_value_at(config, division, raw, inv, lead, assembly, review, sl, freq_cutoff, unit_cost_window):
    scope = get_scope(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)]
    series_bundle = build_monthly_series(raw_div, codes)
    daily_series = build_daily_series(raw_div, codes)
    month_max = series_bundle["series"][codes[0]][1][-1]

    ol_all = raw_div[(raw_div["forecast_date"].notna()) & (raw_div["forecast_date"] >= raw_div["createDate"])]
    median_notice = float((ol_all["forecast_date"] - ol_all["createDate"]).dt.days.median())

    facts = validator_facts(scope, raw_div, series_bundle["monthly_long"], month_max)
    facts_policy = validator_policy(facts, assembly, median_notice, freq_cutoff)
    minmax_df = validator_minmax(scope, series_bundle["series"], daily_series, facts_policy,
                                  lead, assembly, review, sl)
    unit_cost = validator_unit_cost(raw_div, unit_cost_window)
    minmax_df = minmax_df.merge(unit_cost.rename("unit_cost"), left_on="code", right_index=True, how="left")
    stock_value = float((minmax_df.loc[minmax_df["policy"] == "finished_goods_stock", "min_qty"] *
                        minmax_df.loc[minmax_df["policy"] == "finished_goods_stock", "unit_cost"]).sum())
    return stock_value


def find_sl_crossing(config, division, raw, inv, target, lead, assembly, review, freq_cutoff, unit_cost_window):
    lo, hi = 0.01, 0.999
    lo_val = stock_value_at(config, division, raw, inv, lead, assembly, review, lo, freq_cutoff, unit_cost_window)
    if target < lo_val:
        return "<0.01", lo_val
    for _ in range(30):
        mid = (lo + hi) / 2
        mid_val = stock_value_at(config, division, raw, inv, lead, assembly, review, mid, freq_cutoff, unit_cost_window)
        if abs(mid_val - target) <= 1000:
            return mid, mid_val
        if mid_val < target:
            lo = mid
        else:
            hi = mid
    return mid, mid_val


def main():
    config = load_config()
    raw, inv, ces = load_data()
    e1 = config["phase_e1_assumptions"]

    rows = []
    for division in DIVISIONS:
        logger.info("=" * 90)
        logger.info("VALIDATOR (Phase J): %s", division)
        logger.info("=" * 90)
        sellable_wh = e1["sellable_warehouse_codes"][division]

        baseline_fr, actual_ot = baseline_and_actual_on_time(config, division, raw, inv, ces, sellable_wh)
        calib_gap_pp = (baseline_fr - actual_ot) * 100

        target = CURRENT_ONHAND_VALUE[division]
        sl_cross, sv_cross = find_sl_crossing(config, division, raw, inv, target, BASELINE_LEAD,
                                               BASELINE_ASSEMBLY, BASELINE_REVIEW, FREQ_CUTOFF_DEFAULT,
                                               UNIT_COST_WINDOW_DEFAULT)

        new_default_sv = stock_value_at(config, division, raw, inv, NEW_DEFAULT_LEAD, NEW_DEFAULT_ASSEMBLY,
                                         NEW_DEFAULT_REVIEW, NEW_DEFAULT_SL, FREQ_CUTOFF_DEFAULT,
                                         UNIT_COST_WINDOW_DEFAULT)

        rows.append({"division": division, "validator_baseline_fill_rate": baseline_fr,
                    "validator_actual_on_time": actual_ot, "validator_calibration_gap_pp": calib_gap_pp,
                    "validator_sl_at_current_onhand": sl_cross, "validator_stock_value_at_sl_crossing": sv_cross,
                    "validator_new_default_stock_value": new_default_sv})
        logger.info("[%s] baseline_fill_rate=%.4f actual_on_time=%.4f gap=%.2fpp; SL@onhand=%s "
                    "(sv=%.0f); new_default_stock_value=%.2f", division, baseline_fr, actual_ot,
                    calib_gap_pp, sl_cross, sv_cross, new_default_sv)

    validator_df = pd.DataFrame(rows)
    validator_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_5_validator_results.csv"), index=False)

    # ---- comparison against the Modeler's saved outputs (necessarily reads both sides) ----
    modeler_calib = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseJ_1_calibration_summary.csv")).set_index("division")
    modeler_cross = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseJ_2_current_onhand_crossing.csv")).set_index("division")
    modeler_new_default = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseJ_4_new_default_headline.csv")).set_index("division")

    compare_rows = []
    for _, r in validator_df.iterrows():
        d = r["division"]
        m_baseline = float(modeler_calib.loc[d, "baseline_fill_rate"])
        m_actual = float(modeler_calib.loc[d, "actual_on_time"])
        m_new_sv = float(modeler_new_default.loc[d, "stock_value"])
        compare_rows.append({
            "division": d,
            "baseline_fill_rate_match": abs(r["validator_baseline_fill_rate"] - m_baseline) < 0.01,
            "validator_baseline": r["validator_baseline_fill_rate"], "modeler_baseline": m_baseline,
            "actual_on_time_match": abs(r["validator_actual_on_time"] - m_actual) < 0.01,
            "validator_actual_on_time": r["validator_actual_on_time"], "modeler_actual_on_time": m_actual,
            "new_default_stock_value_match": abs(r["validator_new_default_stock_value"] - m_new_sv) / m_new_sv < 0.01,
            "validator_new_default_sv": r["validator_new_default_stock_value"], "modeler_new_default_sv": m_new_sv,
        })
    compare_df = pd.DataFrame(compare_rows)
    compare_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_5_validator_comparison.csv"), index=False)

    print("\n" + "=" * 100)
    print("PHASE J PART 5 -- VALIDATOR RESULTS")
    print("=" * 100)
    print(validator_df.to_string(index=False))
    print("\nCOMPARISON AGAINST MODELER:")
    print(compare_df.to_string(index=False))
    return validator_df, compare_df


if __name__ == "__main__":
    main()
