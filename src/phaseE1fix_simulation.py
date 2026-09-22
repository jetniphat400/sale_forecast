"""Phase E1-fix: historical simulation under METRICS.md's default-scenario Min/Max, reusing
src/phaseE1fix_recompute.py's already-computed outputs (no further DB access needed -- this is
pure computation on the frozen 31-month actual series + the default-scenario Min/Max already
written to output/summary/phaseE1fix_2_minmax_stockvalue.csv).

Reuses the simulation-mechanics assumptions already locked in config.yaml
(phase_e1_assumptions.simulation_initial_stock_assumption / _receipt_timing_assumption /
_fulfilment_sequence_assumption) from the original Phase E1 -- unchanged here, since METRICS.md
does not redefine them (METRICS.md Sec.10/11 define fill_rate and cycle_service_level themselves,
not how a historical replay's stock mechanics work).

METRICS.md Sec.10: fill_rate = units shipped immediately from stock / total units demanded.
METRICS.md Sec.11: cycle_service_level = replenishment cycles with no stockout / total cycles.
A "cycle" = one review_interval-length period (the default scenario's review_interval_days=30,
~1 calendar month) -- the natural cycle length for a periodic-review policy, consistent with this
project's monthly data granularity.
"""
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import PROJECT_ROOT, SUMMARY_DIR, load_config, load_scope, load_monthly_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1fix_simulation")


def simulate_item(qty_history: np.ndarray, min_qty: float, max_qty: float, receipt_lag_months: int) -> dict:
    """Order-up-to-Max, periodic review each month (review_interval_days=30 ~= 1 month at the
    default scenario). Initial stock = Max (config's stated assumption). A replenishment order is
    placed whenever on-hand < Min, receipt arrives `receipt_lag_months` later, sized to bring
    stock up to Max at order time. Demand exceeding on-hand is backordered (carried to next
    month), never a lost sale -- config's stated fulfilment-sequence assumption."""
    n = len(qty_history)
    on_hand = max_qty
    pending_receipts = {}  # month_index -> qty
    backorder = 0.0
    total_demand = 0.0
    total_shipped_immediately = 0.0
    cycles_with_stockout = 0
    total_cycles = n

    for t in range(n):
        if t in pending_receipts:
            on_hand += pending_receipts.pop(t)
        demand_t = qty_history[t] + backorder
        total_demand += qty_history[t]
        shipped = min(on_hand, demand_t)
        shortfall = demand_t - shipped
        immediate_shipped = min(on_hand, qty_history[t])
        total_shipped_immediately += immediate_shipped
        stockout_this_cycle = shortfall > 1e-9
        if stockout_this_cycle:
            cycles_with_stockout += 1
        on_hand = max(0.0, on_hand - shipped)
        backorder = shortfall

        if on_hand < min_qty:
            order_qty = max_qty - on_hand
            arrival = t + receipt_lag_months
            if arrival < n:
                pending_receipts[arrival] = pending_receipts.get(arrival, 0.0) + order_qty

    fill_rate = total_shipped_immediately / total_demand if total_demand > 0 else None
    cycle_service_level = 1 - (cycles_with_stockout / total_cycles) if total_cycles > 0 else None
    return {"fill_rate": fill_rate, "cycle_service_level": cycle_service_level,
            "total_demand": total_demand, "cycles_with_stockout": cycles_with_stockout,
            "total_cycles": total_cycles}


def main():
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    series = series_bundle["series"]

    minmax = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_minmax_stockvalue.csv"))
    fg = minmax[(minmax["policy"] == "finished_goods_stock") & minmax["min_qty"].notna() & minmax["max_qty"].notna()]

    lead = e1["default_scenario"]["procurement_lead_time_days"]
    assembly = e1["default_scenario"]["assembly_time_days"]
    receipt_lag_months = math.ceil((lead + assembly) / 30.44)
    logger.info("Simulation assumptions (config['phase_e1_assumptions'], unchanged from original "
                "Phase E1): initial stock = scenario Max; receipt_lag_months = ceil((%d+%d)/30.44) = %d; "
                "backorder carry-forward, receipts applied before demand each month.",
                lead, assembly, receipt_lag_months)

    rows = []
    for _, r in fg.iterrows():
        code = r["code"]
        if code not in series:
            continue
        qty, _months = series[code]
        result = simulate_item(qty, r["min_qty"], r["max_qty"], receipt_lag_months)
        result["code"] = code
        rows.append(result)

    sim_df = pd.DataFrame(rows)
    total_demand_all = sim_df["total_demand"].sum()
    weighted_fill_rate = (sim_df["fill_rate"] * sim_df["total_demand"]).sum() / total_demand_all if total_demand_all else None
    total_cycles_all = sim_df["total_cycles"].sum()
    total_stockout_cycles = sim_df["cycles_with_stockout"].sum()
    pooled_cycle_service_level = 1 - (total_stockout_cycles / total_cycles_all) if total_cycles_all else None

    sim_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_simulation.csv"), index=False)

    print("\n" + "=" * 90)
    print("PHASE E1-FIX HISTORICAL SIMULATION -- default scenario, METRICS.md Sec.10/11")
    print("=" * 90)
    print(f"{len(sim_df)} finished_goods_stock items simulated over their full actual history "
          f"(31 months, frozen series).")
    print(f"fill_rate (Sec.10, demand-weighted across items): {weighted_fill_rate:.4f} ({weighted_fill_rate*100:.2f}%)")
    print(f"cycle_service_level (Sec.11, pooled across all item-months as cycles): "
          f"{pooled_cycle_service_level:.4f} ({pooled_cycle_service_level*100:.2f}%)")
    print(f"Total stockout item-cycles: {total_stockout_cycles} of {total_cycles_all}")

    return {"sim_df": sim_df, "fill_rate": weighted_fill_rate, "cycle_service_level": pooled_cycle_service_level,
            "receipt_lag_months": receipt_lag_months}


if __name__ == "__main__":
    main()
