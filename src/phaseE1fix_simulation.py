"""Phase E1-fix-2: historical simulation under METRICS.md's default-scenario Min/Max, per
METRICS.md Sec.16 (added 2026-09-22) -- a fully-specified daily replay, replacing the previous
monthly-granularity replay whose unstated reorder/receipt-timing mechanics were the confirmed root
cause of a 99.94%-vs-97.90% fill_rate mismatch between two independent implementations (STATUS.md,
Phase E1-fix-2 Part 3).

Runs on the frozen daily actual-demand series (built here from the SAME frozen raw snapshot,
output/data/raw_full_category_sales.csv, that src/phaseE1fix_recompute.py's load_daily_series
uses -- never a live pull) plus the already-computed default-scenario Min/Max
(output/summary/phaseE1fix_2_minmax_stockvalue.csv).

METRICS.md Sec.16, applied literally:
  review          : every review_interval_days, starting at day 0
  reorder trigger : on a review day, if on_hand + on_order <= Min, order (Max - on_hand - on_order)
  receipt         : an order placed on day d arrives at the start of day d + lead_time_days
                     (procurement_lead_time_days + assembly_time_days)
  demand          : daily, from the forecast_date-keyed actual series
  fulfilment      : ship on_hand in full if it covers demand; otherwise ship on_hand and record
                     the shortfall as a backorder, filled FIRST from the next receipt (never lost)
  initial stock   : Max at day 0, no order in flight
  fill_rate       : units shipped ON THE DEMAND DAY / units demanded (Sec.10) -- a backordered
                     unit counts as NOT shipped that day even once a later receipt fills it
  cycle_service   : cycles with no stockout / total cycles (Sec.11); a cycle is the interval
                     between two consecutive receipts
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import SUMMARY_DIR, load_config, load_scope, load_monthly_series
from phaseE1fix_recompute import load_daily_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1fix_simulation")


def simulate_item_daily(qty_daily: np.ndarray, min_qty: float, max_qty: float,
                         review_interval_days: int, lead_time_days: int) -> dict:
    """METRICS.md Sec.16's daily replay for one item. Returns fill_rate, cycle_service_level and
    the raw counts behind them (for pooling across items)."""
    n = len(qty_daily)
    on_hand = float(max_qty)   # initial stock = Max at day 0 (Sec.16)
    on_order = 0.0
    pending = {}                # day_index -> qty arriving
    backorder = 0.0
    total_demand = 0.0
    total_shipped_same_day = 0.0
    cycle_count = 0
    cycle_stockouts = 0
    stockout_in_current_cycle = False

    for t in range(n):
        # 1. Receipt: arrives at the START of the day. Pays down any outstanding backorder first
        #    (backorders are "filled first from the next receipt"), remainder becomes on_hand.
        #    A receipt also closes the current cycle and opens the next one (Sec.16: "a cycle is
        #    the interval between two consecutive receipts").
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

        # 2. Review + reorder trigger, every review_interval_days starting at day 0.
        if t % review_interval_days == 0:
            inventory_position = on_hand + on_order
            if inventory_position <= min_qty:
                order_qty = max_qty - inventory_position
                if order_qty > 0:
                    arrival = t + lead_time_days
                    on_order += order_qty
                    if arrival < n:
                        pending[arrival] = pending.get(arrival, 0.0) + order_qty

        # 3. Daily demand + fulfilment.
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

    # Close the final, still-open cycle at the end of the simulation horizon.
    cycle_count += 1
    if stockout_in_current_cycle:
        cycle_stockouts += 1

    fill_rate = total_shipped_same_day / total_demand if total_demand > 0 else None
    cycle_service_level = 1 - (cycle_stockouts / cycle_count) if cycle_count > 0 else None
    return {"fill_rate": fill_rate, "cycle_service_level": cycle_service_level,
            "total_demand": total_demand, "total_shipped_same_day": total_shipped_same_day,
            "cycle_count": cycle_count, "cycle_stockouts": cycle_stockouts}


def main():
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    sample_months = next(iter(series_bundle["series"].values()))[1]
    daily_series = load_daily_series(scope, sample_months[0], sample_months[-1])

    minmax = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_minmax_stockvalue.csv"))
    fg = minmax[(minmax["policy"] == "finished_goods_stock") & minmax["min_qty"].notna() & minmax["max_qty"].notna()]

    lead = e1["default_scenario"]["procurement_lead_time_days"]
    assembly = e1["default_scenario"]["assembly_time_days"]
    lead_time_days = lead + assembly
    review_interval_days = e1["review_interval_days_default"]
    logger.info("METRICS.md Sec.16 daily simulation: review_interval_days=%d, lead_time_days=%d "
                "(procurement %d + assembly %d), initial stock=Max, backorders filled first from "
                "the next receipt.", review_interval_days, lead_time_days, lead, assembly)

    rows = []
    n_no_daily = 0
    for _, r in fg.iterrows():
        code = r["code"]
        if code not in daily_series:
            n_no_daily += 1
            continue
        qty_daily, _dates = daily_series[code]
        result = simulate_item_daily(qty_daily, r["min_qty"], r["max_qty"], review_interval_days, lead_time_days)
        result["code"] = code
        rows.append(result)
    if n_no_daily:
        logger.warning("%d finished_goods_stock items had no daily history and were excluded from "
                        "the simulation (not silently zero-filled).", n_no_daily)

    sim_df = pd.DataFrame(rows)
    total_demand_all = sim_df["total_demand"].sum()
    total_shipped_all = sim_df["total_shipped_same_day"].sum()
    pooled_fill_rate = total_shipped_all / total_demand_all if total_demand_all else None
    total_cycles_all = sim_df["cycle_count"].sum()
    total_stockout_cycles = sim_df["cycle_stockouts"].sum()
    pooled_cycle_service_level = 1 - (total_stockout_cycles / total_cycles_all) if total_cycles_all else None

    sim_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_simulation.csv"), index=False)

    print("\n" + "=" * 90)
    print("PHASE E1-FIX-2 DAILY SIMULATION -- default scenario, METRICS.md Sec.10/11/16")
    print("=" * 90)
    print(f"{len(sim_df)} finished_goods_stock items simulated over their full daily actual "
          f"history ({len(next(iter(daily_series.values()))[0])} days, frozen raw snapshot).")
    print(f"fill_rate (Sec.10, unit-weighted, same-day shipment only): {pooled_fill_rate:.4f} "
          f"({pooled_fill_rate*100:.2f}%)")
    print(f"cycle_service_level (Sec.11/16, cycle = interval between receipts): "
          f"{pooled_cycle_service_level:.4f} ({pooled_cycle_service_level*100:.2f}%)")
    print(f"Total stockout cycles: {total_stockout_cycles} of {total_cycles_all}")

    return {"sim_df": sim_df, "fill_rate": pooled_fill_rate, "cycle_service_level": pooled_cycle_service_level,
            "lead_time_days": lead_time_days, "review_interval_days": review_interval_days}


if __name__ == "__main__":
    main()
