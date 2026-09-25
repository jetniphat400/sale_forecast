"""Phase 24 Validator Part 4 -- independent recomputation of PEM101's trade-off-curve band at the
"today's not_late (98.28%), lowest stock" preset. Method: METRICS.md Sec.22's trade-off-curve
construction (per-member reorder-level sweep, holding each member's own order-up-to-minus-reorder
gap constant), scored over config.yaml trade_off_curve.simulation_window, using the LOCKED
reorder_level_grid_r_months grid applied identically to all 80 distinct ensemble members
(output/summary/phase23_ensemble_distinct_members_PEM101.csv). At each grid point, this script
computes each member's simulated not_late and stock_value; the grid point whose across-member
MEDIAN not_late is closest to 98.28% is picked as the target, and the min/median/max stock_value
across the 80 members AT THAT GRID POINT is reported as the band.

No DB access -- reuses output/data/phaseI_raw_sales_351items.csv and phaseI_inventory_exact_351items.csv
(already-cached Phase I pulls) exactly as phaseJ3_calibration_engine.py does.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from phaseJ3_calibration_engine import load_raw, build_division_bundle, CALIBRATION_START
from phaseE1_common import PROJECT_ROOT, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase24_validator_curve")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DAYS_PER_MONTH = 30.44
TARGET_NOT_LATE = 0.9828  # PEM101 valid not_late, phaseJ3_report.md "Reconciled targets" table


def simulate_vectorized(qty_matrix: np.ndarray, r_months: float, s_months: float,
                         review_interval_days: int, lead_time_days: int,
                         mean_daily_demand: np.ndarray) -> dict:
    """Vectorized across items (columns), identical mechanics to
    phaseJ3_calibration_engine.simulate_months_of_demand run per item -- verified equivalent for a
    single-item case in this script's __main__ self-check. qty_matrix: (n_days, n_items)."""
    n_days, n_items = qty_matrix.shape
    r_abs = r_months * DAYS_PER_MONTH * mean_daily_demand
    s_abs = s_months * DAYS_PER_MONTH * mean_daily_demand
    lead = int(round(lead_time_days))
    review = max(1, int(round(review_interval_days)))

    on_hand = s_abs.copy()
    on_order = np.zeros(n_items)
    backorder = np.zeros(n_items)
    pending = np.zeros((n_days, n_items))

    daily_on_hand = np.zeros((n_days, n_items))
    daily_demand = np.zeros((n_days, n_items))
    daily_shipped = np.zeros((n_days, n_items))

    for t in range(n_days):
        received = pending[t]
        on_order -= received
        paid = np.minimum(backorder, received)
        backorder -= paid
        on_hand += (received - paid)

        if t % review == 0:
            position = on_hand + on_order
            need = position <= r_abs
            order_qty = np.where(need, np.maximum(s_abs - position, 0.0), 0.0)
            on_order += order_qty
            due = t + lead
            if due < n_days:
                pending[due] += order_qty

        demand_t = qty_matrix[t]
        daily_demand[t] = demand_t
        shipped = np.minimum(on_hand, demand_t)
        daily_shipped[t] = shipped
        shortfall = demand_t - shipped
        on_hand -= shipped
        backorder += shortfall
        daily_on_hand[t] = on_hand

    return {"daily_on_hand": daily_on_hand, "daily_demand": daily_demand, "daily_shipped": daily_shipped}


def self_check(bundle, mean_d_vec):
    """Cross-check the vectorized simulation against the scalar phaseJ3_calibration_engine
    function for one item, one grid point -- must match to float precision."""
    from phaseJ3_calibration_engine import simulate_months_of_demand
    code0 = bundle["codes_used"][0]
    qty0 = bundle["qty_matrix"][:, 0]
    mean0 = mean_d_vec[0]
    scalar = simulate_months_of_demand(qty0, r_months=1.0, s_months=2.0, review_interval_days=7,
                                        lead_time_days=5, initial_stock=2.0 * DAYS_PER_MONTH * mean0,
                                        mean_daily_demand=mean0)
    vec = simulate_vectorized(bundle["qty_matrix"][:, :1], r_months=1.0, s_months=2.0,
                               review_interval_days=7, lead_time_days=5,
                               mean_daily_demand=np.array([mean0]))
    ok_on_hand = np.allclose(scalar["daily_on_hand"], vec["daily_on_hand"][:, 0])
    ok_shipped = np.allclose(scalar["daily_shipped"], vec["daily_shipped"][:, 0])
    logger.info("Self-check (item=%s): on_hand match=%s, shipped match=%s", code0, ok_on_hand, ok_shipped)
    if not (ok_on_hand and ok_shipped):
        raise AssertionError("Vectorized simulation does not match scalar reference -- fix before trusting results.")


def main():
    config = load_config()
    toc = config["trade_off_curve"]
    r_grid = toc["reorder_level_grid_r_months"]
    sim_start, sim_end = toc["simulation_window"]["start"], toc["simulation_window"]["end"]
    warm_start = toc["warm_up"]["start"]
    logger.info("Config trade_off_curve: r_grid=%s, sim_window=%s..%s, warm_up_start=%s",
                r_grid, sim_start, sim_end, warm_start)
    assert warm_start == CALIBRATION_START, "warm_up.start must match calibration engine's CALIBRATION_START"

    raw, inv = load_raw()
    bundle = build_division_bundle(config, "PEM101", raw, inv, validation_end=sim_end)
    day_index = bundle["day_index"]
    logger.info("Day index: %s .. %s (%d days)", day_index[0].date(), day_index[-1].date(), len(day_index))

    codes = bundle["codes"]
    daily_series = bundle["daily_series"]
    unit_cost = bundle["unit_cost_df"]["unit_cost"]

    used_codes = [c for c in codes if daily_series[c].mean() > 0]
    logger.info("%d of %d PEM101 scope items have mean daily demand > 0 (used in simulation).",
                len(used_codes), len(codes))
    qty_matrix = np.column_stack([daily_series[c] for c in used_codes])
    mean_d_vec = qty_matrix.mean(axis=0)
    uc_vec = np.array([unit_cost.get(c, np.nan) for c in used_codes])
    has_uc = ~np.isnan(uc_vec)
    logger.info("%d of %d used items have a valid unit_cost (rest excluded from stock_value sum, "
                "per phaseJ3_calibration_engine's own convention).", int(has_uc.sum()), len(used_codes))

    window_mask = (day_index >= pd.Timestamp(sim_start)) & (day_index <= pd.Timestamp(sim_end))
    logger.info("Simulation window mask: %d of %d days scored (%s..%s).",
                window_mask.sum(), len(day_index), sim_start, sim_end)

    self_check({"codes_used": used_codes, "qty_matrix": qty_matrix}, mean_d_vec)

    members = pd.read_csv(os.path.join(SUMMARY_DIR, "phase23_ensemble_distinct_members_PEM101.csv"))
    logger.info("Loaded %d distinct ensemble members.", len(members))
    members["gap_months"] = members["s_months"] - members["r_months"]

    records = []
    for gi, r in enumerate(r_grid):
        for mi, mrow in members.iterrows():
            s = r + mrow["gap_months"]
            sim = simulate_vectorized(qty_matrix, r_months=r, s_months=s,
                                       review_interval_days=mrow["review_interval_days"],
                                       lead_time_days=mrow["lead_time_days"],
                                       mean_daily_demand=mean_d_vec)
            demand_w = sim["daily_demand"][window_mask].sum()
            shipped_w = sim["daily_shipped"][window_mask].sum()
            not_late = shipped_w / demand_w if demand_w > 0 else np.nan

            onhand_w = sim["daily_on_hand"][window_mask]  # (n_window_days, n_items)
            stockval_daily = (onhand_w[:, has_uc] * uc_vec[has_uc]).sum(axis=1)
            stock_value = float(stockval_daily.mean())

            records.append({"r_months": r, "member_idx": mi, "s_months": s,
                             "review_interval_days": mrow["review_interval_days"],
                             "lead_time_days": mrow["lead_time_days"],
                             "not_late": not_late, "stock_value": stock_value})
        logger.info("Grid point %d/%d (r_months=%.2f) done.", gi + 1, len(r_grid), r)

    grid_df = pd.DataFrame(records)
    grid_df.to_csv(os.path.join(SUMMARY_DIR, "phase24_validator_pem101_curve_grid.csv"), index=False)

    per_r = grid_df.groupby("r_months").agg(
        median_not_late=("not_late", "median"), mean_not_late=("not_late", "mean"),
        median_stock_value=("stock_value", "median"), min_stock_value=("stock_value", "min"),
        max_stock_value=("stock_value", "max")).reset_index()
    per_r["abs_gap_to_target"] = (per_r["median_not_late"] - TARGET_NOT_LATE).abs()
    per_r = per_r.sort_values("r_months")
    per_r.to_csv(os.path.join(SUMMARY_DIR, "phase24_validator_pem101_curve_per_r.csv"), index=False)
    print(per_r.to_string(index=False))

    target_row = per_r.loc[per_r["abs_gap_to_target"].idxmin()]
    print(f"\nTarget r_months={target_row['r_months']} (median not_late={target_row['median_not_late']*100:.2f}%, "
          f"target={TARGET_NOT_LATE*100:.2f}%)")
    target_members = grid_df[grid_df["r_months"] == target_row["r_months"]]
    print(f"stock_value at target r: min={target_members['stock_value'].min():,.0f}, "
          f"median={target_members['stock_value'].median():,.0f}, max={target_members['stock_value'].max():,.0f}")
    print(f"not_late at target r across members: min={target_members['not_late'].min()*100:.2f}%, "
          f"median={target_members['not_late'].median()*100:.2f}%, max={target_members['not_late'].max()*100:.2f}%")


if __name__ == "__main__":
    main()
