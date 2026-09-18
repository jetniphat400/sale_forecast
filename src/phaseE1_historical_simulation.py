"""Phase E1.4 (Modeler): historical simulation of the Min/Max scenarios.

*** WHAT THIS SIMULATION CANNOT SHOW, stated here per the task instruction, not buried in a
footnote *** -- No historical stock-movement/transaction-level time series exists in this
database (confirmed absent, Phase D / inventory investigations). Initial stock (2024-01 starting
quantity), replenishment receipt timing, and fulfilment sequence are therefore ALL MODELLING
ASSUMPTIONS recorded explicitly in config['phase_e1_assumptions'], each with an owner and a
"scenario input, not a fact" label -- not measured values. THIS SIMULATION ANSWERS "what would
this policy have produced under these stated assumptions" -- it does NOT answer "how much would
have been saved" (no baseline-vs-policy cost comparison is computed here; that is Phase F's job).

Replays 2024-01 through 2026-07 (the full 31-month history this project's data actually covers --
NOT all of calendar 2026, which has not happened in the data yet) for the 66 FG-stock-supported
items (phaseE1_1_item_segments.csv), under the full 18-scenario grid (cheap to run in full: 66
items x 18 scenarios x 31 months is a trivial computation, so no scope reduction was needed).

Ordering rule (the classic (s, S) periodic-review interpretation of "Min-Max", used because no
MOQ/lot size exists to fix a literal order quantity, STATUS.md Section 8.3): at each monthly
review, if inventory position (on-hand + on order) <= Min, order UP TO Max (order qty = Max -
inventory position), arriving after the scenario's deterministic lead time.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import SUMMARY_DIR, CHARTS_DIR, TOTAL_MONTHS, load_config, load_scope, load_monthly_series, compute_unit_cost
from phaseE1_leadtime_demand import DAYS_PER_MONTH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_historical_simulation")


def simulate_item(qty: np.ndarray, min_qty: float, max_qty: float, lead_months: int) -> dict:
    """Runs the (s, S) simulation for one item under one scenario across all 31 months.
    Returns per-month stock levels + aggregate fill-rate/stockout/obsolescence statistics."""
    on_hand = max_qty  # simulation_initial_stock_assumption: start at this scenario's own Max
    pending = []  # list of [arrival_month_idx, qty]
    backlog_carried = 0.0
    stock_qty_by_month = []
    on_time_shipped_total = 0.0
    original_demand_total = 0.0
    stockout_flags = []
    zero_demand_streak = 0
    max_zero_demand_streak_with_stock = 0

    for t in range(TOTAL_MONTHS):
        arrivals = sum(q for (a, q) in pending if a == t)
        on_hand += arrivals
        pending = [(a, q) for (a, q) in pending if a != t]

        original_demand = float(qty[t])
        ship_to_backlog = min(on_hand, backlog_carried)
        on_hand -= ship_to_backlog
        backlog_carried -= ship_to_backlog
        ship_to_new = min(on_hand, original_demand)
        on_hand -= ship_to_new
        new_unmet = original_demand - ship_to_new
        backlog_carried += new_unmet

        on_time_shipped_total += ship_to_new
        original_demand_total += original_demand
        stockout_flags.append(new_unmet > 1e-9)

        if original_demand <= 0 and on_hand > 0:
            zero_demand_streak += 1
            max_zero_demand_streak_with_stock = max(max_zero_demand_streak_with_stock, zero_demand_streak)
        else:
            zero_demand_streak = 0

        stock_qty_by_month.append(on_hand)

        inv_position = on_hand + sum(q for _, q in pending)
        if inv_position <= min_qty:
            order_qty = max(0.0, max_qty - inv_position)
            if order_qty > 0:
                pending.append([t + lead_months, order_qty])

    stockout_flags = np.array(stockout_flags)
    # longest consecutive stockout streak
    max_streak, cur = 0, 0
    for f in stockout_flags:
        cur = cur + 1 if f else 0
        max_streak = max(max_streak, cur)

    return {
        "mean_stock_qty": float(np.mean(stock_qty_by_month)),
        "stock_qty_by_month": stock_qty_by_month,
        "on_time_shipped_total": on_time_shipped_total,
        "original_demand_total": original_demand_total,
        "unit_fill_rate": on_time_shipped_total / original_demand_total if original_demand_total > 0 else None,
        "n_stockout_months": int(stockout_flags.sum()),
        "longest_stockout_streak_months": int(max_streak),
        "max_zero_demand_streak_with_stock_months": int(max_zero_demand_streak_with_stock),
    }


def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(CHARTS_DIR, exist_ok=True)
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    obsolescence_threshold = e1["obsolescence_threshold_months"]

    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    series = series_bundle["series"]

    segments = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_item_segments.csv"))
    fg_items = segments.loc[segments["fg_stock_policy_supported"] == True, "code"].tolist()

    minmax = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_minmax_all_scenarios.csv"))
    grid = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_scenario_grid.csv"))
    logger.info("Simulating %d FG-stock items x %d scenarios x %d months = %d item-months of simulation "
                "(no scope reduction needed -- cheap to run in full).",
                len(fg_items), len(grid), TOTAL_MONTHS, len(fg_items) * len(grid) * TOTAL_MONTHS)

    unit_cost = compute_unit_cost(fg_items)
    cost_map = dict(zip(unit_cost["itemcode"], unit_cost["primary_unit_cost"]))
    n_no_cost = sum(1 for c in fg_items if pd.isna(cost_map.get(c)))
    logger.info("%d of %d FG items have NO usable cost record -- their stock VALUE is reported as "
                "undetermined (never assumed zero), quantity metrics are unaffected.", n_no_cost, len(fg_items))

    item_scenario_rows = []
    monthly_rows = []
    for _, sc in grid.iterrows():
        lead_months = int(np.ceil((sc["procurement_lead_time_days"] + sc["assembly_time_days"]) / DAYS_PER_MONTH))
        sc_mm = minmax[(minmax["procurement_lead_time_days"] == sc["procurement_lead_time_days"]) &
                       (minmax["assembly_time_days"] == sc["assembly_time_days"]) &
                       (minmax["cycle_service_level"] == sc["cycle_service_level"])]
        mm_map = {r["itemcode"]: (r["min_qty"], r["max_qty"]) for _, r in sc_mm.iterrows()}

        for code in fg_items:
            if code not in series or code not in mm_map:
                continue
            qty = series[code][0]
            min_q, max_q = mm_map[code]
            result = simulate_item(qty, min_q, max_q, lead_months)
            unit_price = cost_map.get(code, np.nan)

            item_scenario_rows.append({
                "itemcode": code, "procurement_lead_time_days": sc["procurement_lead_time_days"],
                "assembly_time_days": sc["assembly_time_days"], "cycle_service_level": sc["cycle_service_level"],
                "is_default_scenario": bool(sc["is_default_scenario"]),
                "min_qty": min_q, "max_qty": max_q,
                "unit_fill_rate": result["unit_fill_rate"], "n_stockout_months": result["n_stockout_months"],
                "longest_stockout_streak_months": result["longest_stockout_streak_months"],
                "mean_stock_qty": result["mean_stock_qty"],
                "mean_stock_value_thb": result["mean_stock_qty"] * unit_price if pd.notna(unit_price) else None,
                "max_zero_demand_streak_months": result["max_zero_demand_streak_with_stock_months"],
                "obsolescence_risk_flag": result["max_zero_demand_streak_with_stock_months"] > obsolescence_threshold,
            })
            if bool(sc["is_default_scenario"]):
                for t, q in enumerate(result["stock_qty_by_month"]):
                    monthly_rows.append({"itemcode": code, "month_index": t,
                                          "year_month": series[code][1][t], "stock_qty": q,
                                          "stock_value_thb": q * unit_price if pd.notna(unit_price) else None})

    item_scenario = pd.DataFrame(item_scenario_rows)
    monthly = pd.DataFrame(monthly_rows)
    item_scenario.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_4_simulation_item_scenario.csv"), index=False)
    monthly.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_4_simulation_default_scenario_monthly.csv"), index=False)

    scenario_summary = item_scenario.groupby(
        ["procurement_lead_time_days", "assembly_time_days", "cycle_service_level", "is_default_scenario"],
        as_index=False).agg(
        n_items=("itemcode", "nunique"),
        mean_unit_fill_rate=("unit_fill_rate", "mean"),
        total_stockout_months=("n_stockout_months", "sum"),
        mean_longest_stockout_streak=("longest_stockout_streak_months", "mean"),
        mean_stock_qty=("mean_stock_qty", "mean"),
        total_stock_value_thb=("mean_stock_value_thb", "sum"),
        n_obsolescence_risk_items=("obsolescence_risk_flag", "sum"))
    scenario_summary.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_4_scenario_summary.csv"), index=False)

    default_summary = scenario_summary[scenario_summary["is_default_scenario"]]
    logger.info("DEFAULT SCENARIO simulation summary: mean unit fill rate=%.4f, total stockout item-months=%d "
                "of %d, mean stock qty=%.1f, total mean stock value=THB %.2f, obsolescence-risk items=%d/%d.",
                default_summary["mean_unit_fill_rate"].iloc[0], int(default_summary["total_stockout_months"].iloc[0]),
                len(fg_items) * TOTAL_MONTHS, default_summary["mean_stock_qty"].iloc[0],
                default_summary["total_stock_value_thb"].iloc[0], int(default_summary["n_obsolescence_risk_items"].iloc[0]),
                len(fg_items))

    # ---- chart: default-scenario fill-rate/stock-value time series ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ts = monthly.groupby("year_month", as_index=False).agg(
        total_stock_qty=("stock_qty", "sum"), total_stock_value=("stock_value_thb", "sum"))
    ts = ts.sort_values("year_month")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    ax1.plot(ts["year_month"], ts["total_stock_qty"], marker=".", color="tab:blue")
    ax1.set_ylabel("Total simulated stock qty (66 FG items)")
    ax1.set_title("E1.4 default-scenario historical simulation: stock quantity and value over time")
    ax2.plot(ts["year_month"], ts["total_stock_value"], marker=".", color="tab:green")
    ax2.set_ylabel("Total simulated stock value (THB)")
    ax2.set_xlabel("Month")
    for ax in (ax1, ax2):
        ax.tick_params(axis="x", rotation=90, labelsize=6)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "phaseE1_historical_simulation_default_scenario.png"), dpi=120)
    plt.close(fig)
    logger.info("Chart: output/charts/phaseE1_historical_simulation_default_scenario.png")

    print("\n=== E1.4 SCENARIO SUMMARY (mean unit fill rate, stock value, obsolescence-risk items) ===")
    print(scenario_summary.round(3).to_string(index=False))

    return {"item_scenario": item_scenario, "scenario_summary": scenario_summary, "monthly": monthly,
            "default_summary": default_summary, "fg_items": fg_items}


if __name__ == "__main__":
    main()
