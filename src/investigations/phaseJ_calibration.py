"""Phase J Part 1 -- baseline_replay, actual_on_time, calibration_gap (METRICS.md Sec.18).

Reuses Phase I's cached raw pulls (output/data/phaseI_raw_sales_351items.csv,
phaseI_inventory_exact_351items.csv, phaseI_combined_scope_351items.csv) and this task's own
Cube_CES pull (output/data/phaseJ_cube_ces_351items.csv, src/investigations/phaseJ_single_pull.py)
-- no further database access.
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
logger = logging.getLogger("phaseJ_calibration")

DATA_DIR = os.path.join(eng.PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")
CES_FILE = os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv")
HORIZON_START, HORIZON_END = "2024-01-01", "2026-07-31"

# Baseline uses TODAY's (pre-Part-4) config defaults -- lead=60, assembly=3, review=30 -- since
# Part 1 validates the model as it stands BEFORE Part 4's default change.
BASELINE_LEAD = 60
BASELINE_ASSEMBLY = 3
BASELINE_REVIEW = 30
BASELINE_LEAD_TIME_DAYS = BASELINE_LEAD + BASELINE_ASSEMBLY


def current_minmax_sellable_only(inv_div: pd.DataFrame, codes: list, sellable_warehouses: list) -> pd.DataFrame:
    """METRICS.md Sec.18: 'Min and Max = current minimum and maximum from Cube_Inventory_Exact
    summed across the division's sellable warehouses' -- deliberately NOT the same as
    phaseE1_common.current_minmax_per_item (which sums across ALL warehouses, for a different,
    comparison-only purpose). Restricting to sellable warehouses here matches the on-hand-stock
    convention (sellable_stock_per_item) so Min/Max and initial stock describe the same physical
    stock pool."""
    sub = inv_div[inv_div["warehouse"].isin(sellable_warehouses)]
    per_item = sub.groupby("itemcode", as_index=False).agg(
        current_min=("minimum", "sum"), current_max=("maximum", "sum"))
    out = pd.DataFrame({"itemcode": codes}).merge(per_item, on="itemcode", how="left")
    out["current_min"] = out["current_min"].fillna(0.0)
    out["current_max"] = out["current_max"].fillna(0.0)
    out["has_current_setting"] = (out["current_min"] > 0) | (out["current_max"] > 0)
    return out


def simulate_baseline_with_setting(qty_daily: np.ndarray, min_qty: float, max_qty: float,
                                    initial_stock: float, review_interval_days: int,
                                    lead_time_days: int) -> dict:
    """Identical mechanics to phaseE1fix_simulation.simulate_item_daily, EXCEPT initial stock is
    the item's ACTUAL current on-hand (sellable), not Max -- METRICS.md Sec.18: 'initial stock =
    current on-hand in sellable warehouses'."""
    n = len(qty_daily)
    on_hand = float(initial_stock)
    on_order = 0.0
    pending = {}
    backorder = 0.0
    total_demand = 0.0
    total_shipped_same_day = 0.0
    cycle_count = 0
    cycle_stockouts = 0
    stockout_in_current_cycle = False

    for t in range(n):
        if t in pending:
            received = pending.pop(t)
            on_order -= received
            if backorder > 0:
                paid = min(backorder, received)
                backorder -= paid
                received -= paid
            on_hand += received
            cycle_count += 1
            if stockout_in_current_cycle:
                cycle_stockouts += 1
            stockout_in_current_cycle = False

        if t % review_interval_days == 0:
            inventory_position = on_hand + on_order
            if inventory_position <= min_qty:
                order_qty = max_qty - inventory_position
                if order_qty > 0:
                    arrival = t + lead_time_days
                    on_order += order_qty
                    if arrival < n:
                        pending[arrival] = pending.get(arrival, 0.0) + order_qty

        demand_t = float(qty_daily[t])
        total_demand += demand_t
        if on_hand >= demand_t:
            shipped = demand_t
            on_hand -= demand_t
        else:
            shipped = on_hand
            shortfall = demand_t - on_hand
            on_hand = 0.0
            backorder += shortfall
            stockout_in_current_cycle = True
        total_shipped_same_day += shipped

    cycle_count += 1
    if stockout_in_current_cycle:
        cycle_stockouts += 1

    fill_rate = total_shipped_same_day / total_demand if total_demand > 0 else None
    cycle_service_level = 1 - (cycle_stockouts / cycle_count) if cycle_count > 0 else None
    return {"fill_rate": fill_rate, "cycle_service_level": cycle_service_level,
            "total_demand": total_demand, "total_shipped_same_day": total_shipped_same_day,
            "cycle_count": cycle_count, "cycle_stockouts": cycle_stockouts}


def simulate_baseline_reactive(qty_daily: np.ndarray, initial_stock: float, lead_time_days: int) -> dict:
    """METRICS.md Sec.18: items with no current setting are REACTIVE -- 'no reorder until a
    backorder exists, then order exactly the backorder quantity'. Resolved reading (stated
    explicitly, ambiguity per CONVENTIONS.md): no periodic review at all for these items; each
    day a shortfall occurs, an order for EXACTLY that day's shortfall is placed immediately,
    arriving lead_time_days later -- a purely reactive, no-planning policy, as opposed to the
    has-setting items' periodic Min/Max review."""
    n = len(qty_daily)
    on_hand = float(initial_stock)
    on_order = 0.0
    pending = {}
    backorder = 0.0
    total_demand = 0.0
    total_shipped_same_day = 0.0
    cycle_count = 0
    cycle_stockouts = 0
    stockout_in_current_cycle = False

    for t in range(n):
        if t in pending:
            received = pending.pop(t)
            on_order -= received
            if backorder > 0:
                paid = min(backorder, received)
                backorder -= paid
                received -= paid
            on_hand += received
            cycle_count += 1
            if stockout_in_current_cycle:
                cycle_stockouts += 1
            stockout_in_current_cycle = False

        demand_t = float(qty_daily[t])
        total_demand += demand_t
        if on_hand >= demand_t:
            shipped = demand_t
            on_hand -= demand_t
        else:
            shipped = on_hand
            shortfall = demand_t - on_hand
            on_hand = 0.0
            backorder += shortfall
            stockout_in_current_cycle = True
            arrival = t + lead_time_days
            on_order += shortfall
            if arrival < n:
                pending[arrival] = pending.get(arrival, 0.0) + shortfall
        total_shipped_same_day += shipped

    cycle_count += 1
    if stockout_in_current_cycle:
        cycle_stockouts += 1

    fill_rate = total_shipped_same_day / total_demand if total_demand > 0 else None
    cycle_service_level = 1 - (cycle_stockouts / cycle_count) if cycle_count > 0 else None
    return {"fill_rate": fill_rate, "cycle_service_level": cycle_service_level,
            "total_demand": total_demand, "total_shipped_same_day": total_shipped_same_day,
            "cycle_count": cycle_count, "cycle_stockouts": cycle_stockouts}


def run_baseline_replay(division: str, bundle: dict, policy_by_code: dict) -> pd.DataFrame:
    codes = bundle["codes"]
    daily_series = bundle["daily_series"]
    inv_div = bundle["inv_div"]
    sellable_wh = bundle["sellable_variants"]["current"]

    mm = current_minmax_sellable_only(inv_div, codes, sellable_wh)
    onhand = eng.sellable_stock_per_item(inv_div, codes, sellable_wh).rename(columns={"itemcode": "code_"})
    onhand_by_code = dict(zip(onhand["code_"], onhand["sellable_stock"]))
    mm_by_code = mm.set_index("itemcode").to_dict("index")

    rows = []
    for code in codes:
        qty_d, _ = daily_series[code]
        initial_stock = onhand_by_code.get(code, 0.0)
        info = mm_by_code.get(code, {"current_min": 0.0, "current_max": 0.0, "has_current_setting": False})
        if info["has_current_setting"]:
            sim = simulate_baseline_with_setting(qty_d, info["current_min"], info["current_max"],
                                                  initial_stock, BASELINE_REVIEW, BASELINE_LEAD_TIME_DAYS)
        else:
            sim = simulate_baseline_reactive(qty_d, initial_stock, BASELINE_LEAD_TIME_DAYS)
        sim["code"] = code
        sim["has_current_setting"] = info["has_current_setting"]
        sim["current_min"] = info["current_min"]
        sim["current_max"] = info["current_max"]
        sim["initial_stock"] = initial_stock
        sim["policy"] = policy_by_code.get(code, "unknown")
        rows.append(sim)
    return pd.DataFrame(rows)


def compute_actual_on_time(division: str, codes: list) -> dict:
    ces = pd.read_csv(CES_FILE)
    ces = ces[ces["ItemCode"].isin(codes)].copy()
    ces["ForecastDelDate"] = pd.to_datetime(ces["ForecastDelDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")

    win = ces[(ces["ForecastDelDate"] >= HORIZON_START) & (ces["ForecastDelDate"] <= HORIZON_END)].copy()
    n_total = len(win)
    excluded_no_actual = win[win["ActualDelDate"].isna()]
    scored = win[win["ActualDelDate"].notna()].copy()
    scored["on_time"] = scored["ActualDelDate"] <= scored["ForecastDelDate"]
    total_units = float(scored["ActualQty"].sum())
    on_time_units = float(scored.loc[scored["on_time"], "ActualQty"].sum())
    actual_on_time = on_time_units / total_units if total_units > 0 else float("nan")

    # per-item breakdown, for the segment-policy join later
    per_item = scored.groupby("ItemCode")[["ActualQty", "on_time"]].apply(
        lambda g: pd.Series({"units": g["ActualQty"].sum(),
                             "on_time_units": g.loc[g["on_time"], "ActualQty"].sum()})
    ).reset_index().rename(columns={"ItemCode": "code"})
    per_item["actual_on_time_item"] = np.where(per_item["units"] > 0,
                                                per_item["on_time_units"] / per_item["units"], np.nan)

    return {"actual_on_time": actual_on_time, "n_rows_in_horizon": n_total,
            "n_excluded_no_actual": len(excluded_no_actual), "total_units": total_units,
            "on_time_units": on_time_units, "per_item": per_item}


def main():
    config = eng.load_config()
    raw, inv = eng.load_raw()

    summary_rows = []
    breakdown_rows = []
    baseline_detail = {}

    for division in eng.DIVISIONS:
        logger.info("=" * 100)
        logger.info("CALIBRATION: %s", division)
        logger.info("=" * 100)
        bundle = eng.build_division_bundle(config, division, raw, inv)
        default_result = eng.default_scenario(bundle)
        policy_by_code = default_result["policy_by_code"]

        base_df = run_baseline_replay(division, bundle, policy_by_code)
        baseline_detail[division] = base_df

        total_demand_all = base_df["total_demand"].sum()
        total_shipped_all = base_df["total_shipped_same_day"].sum()
        baseline_fill_rate = total_shipped_all / total_demand_all if total_demand_all else float("nan")

        ces_result = compute_actual_on_time(division, bundle["codes"])
        actual_on_time = ces_result["actual_on_time"]
        calibration_gap = baseline_fill_rate - actual_on_time

        n_reactive = int((~base_df["has_current_setting"]).sum())
        n_with_setting = int(base_df["has_current_setting"].sum())

        interpretation = ("credible (within +-5pp)" if abs(calibration_gap) * 100 <= 5 else
                          ("optimistic" if calibration_gap > 0 else "pessimistic"))

        logger.info("[%s] baseline_fill_rate=%.4f actual_on_time=%.4f calibration_gap=%.4f (%s); "
                    "n_with_setting=%d n_reactive=%d", division, baseline_fill_rate, actual_on_time,
                    calibration_gap, interpretation, n_with_setting, n_reactive)

        summary_rows.append({
            "division": division, "baseline_fill_rate": baseline_fill_rate,
            "actual_on_time": actual_on_time, "calibration_gap_pp": calibration_gap * 100,
            "interpretation": interpretation, "n_with_setting": n_with_setting, "n_reactive": n_reactive,
            "n_items": len(bundle["codes"]), "ces_rows_in_horizon": ces_result["n_rows_in_horizon"],
            "ces_excluded_no_actual": ces_result["n_excluded_no_actual"],
            "ces_total_units": ces_result["total_units"],
        })

        # breakdown by segment policy x has_current_setting
        for (policy, has_setting), g in base_df.groupby(["policy", "has_current_setting"]):
            td, ts = g["total_demand"].sum(), g["total_shipped_same_day"].sum()
            fr = ts / td if td > 0 else float("nan")
            breakdown_rows.append({"division": division, "policy": policy,
                                   "has_current_setting": has_setting, "n_items": len(g),
                                   "baseline_fill_rate": fr, "total_demand": td})

    summary_df = pd.DataFrame(summary_rows)
    breakdown_df = pd.DataFrame(breakdown_rows)
    summary_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_1_calibration_summary.csv"), index=False)
    breakdown_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_1_calibration_breakdown.csv"), index=False)
    for division, df in baseline_detail.items():
        df.to_csv(os.path.join(SUMMARY_DIR, f"phaseJ_1_baseline_detail_{division}.csv"), index=False)

    print("\n" + "=" * 100)
    print("PHASE J PART 1 -- CALIBRATION")
    print("=" * 100)
    print(summary_df.to_string(index=False))
    print("\nBREAKDOWN BY SEGMENT POLICY x HAS-CURRENT-SETTING:")
    print(breakdown_df.to_string(index=False))
    return summary_df, breakdown_df, baseline_detail


if __name__ == "__main__":
    main()
