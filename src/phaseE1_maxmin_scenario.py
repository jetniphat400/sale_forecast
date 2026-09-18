"""Phase E1.3 (Modeler): Max-Min scenario grid with forecast consumption.

ONLY for the 66 items where E1.1 found finished-goods stock is the segment's supported policy
(phaseE1_1_item_segments.csv, fg_stock_policy_supported == True) -- the 46 low-value/low-freq
items (Component-ATO recommended) and the 16 excluded/placeholder items get NO Min/Max here,
per the task's own scope restriction and the hard acceptance criterion that a placeholder/
excluded item must never receive a Min, Max or purchase quantity.

Scenario grid: procurement lead time in {45,60,75} days x assembly time in {config default,
config alternative} days x cycle service level in {90%,95%,98%} = 18 scenarios, all computed.
ONE is designated the "default scenario" (config['phase_e1_assumptions']['default_scenario']).

IMPORTANT DISTINCTION, stated once here and repeated in the report: cycle service level (the
probability of NOT stocking out during one replenishment cycle) is NOT the same statistic as unit
fill rate (the % of demand units delivered on time) -- this script sets Min/Max to TARGET a given
cycle service level; whether that target is actually achieved, and what unit fill rate results,
is only checkable by the E1.4 historical simulation, not by this script.

Min = mean of the empirical protection-period demand distribution (E1.2, output/summary/
      phaseE1_2_empirical_distribution.csv, already built at the exact rounded horizon each
      scenario needs) + safety stock, where safety stock = (chosen percentile) - (mean) --
      i.e. Min IS the percentile value directly; both are reported for clarity.
Max = Min + a replenishment quantity = the review interval's own expected demand (this item's
      mean monthly qty x review_interval_days/30.44) -- a stated CONVENTION (config
      replenishment_qty_convention), since no MOQ/lot size exists in this data (confirmed
      absent, business-confirmed, STATUS.md Section 8.3).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import (
    SUMMARY_DIR, CHARTS_DIR, TOTAL_MONTHS,
    load_config, load_scope, load_monthly_series, topdown_item_forecast,
    query_inventory_exact, sellable_stock_per_item, query_backlog, query_confirmed_future_orders,
)
from phaseE1_leadtime_demand import protection_period_months

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_maxmin_scenario")

LAST_HISTORY_MONTH = "2026-07"  # last month in the forecast_date-keyed monthly series (TOTAL_MONTHS=31)
LAST_HISTORY_MONTH_END = "2026-07-31"


def build_scenario_grid(e1: dict) -> pd.DataFrame:
    rows = []
    for lt in e1["procurement_lead_time_days_grid"]:
        for at in [e1["assembly_time_days_default"], e1["assembly_time_days_alternative"]]:
            for sl in e1["cycle_service_level_grid"]:
                h = protection_period_months(lt, at, e1["review_interval_days_default"])
                is_default = (lt == e1["default_scenario"]["procurement_lead_time_days"] and
                              at == e1["default_scenario"]["assembly_time_days"] and
                              sl == e1["default_scenario"]["cycle_service_level"])
                rows.append({"procurement_lead_time_days": lt, "assembly_time_days": at,
                             "cycle_service_level": sl, "protection_period_months": h,
                             "is_default_scenario": is_default})
    grid = pd.DataFrame(rows)
    n_default = int(grid["is_default_scenario"].sum())
    if n_default != 1:
        raise ValueError(f"Expected exactly 1 default scenario in the 18-row grid, found {n_default}.")
    logger.info("Scenario grid: %d rows (3 lead-time x 2 assembly-time x 3 service-level).", len(grid))
    return grid


def compute_minmax(fg_items: list, series_bundle: dict, dist_df: pd.DataFrame, grid: pd.DataFrame,
                    review_interval_days: float) -> pd.DataFrame:
    """One row per (itemcode, scenario). dist_df is E1.2's empirical distribution
    (phaseE1_2_empirical_distribution.csv), already keyed by (itemcode, horizon_months)."""
    series = series_bundle["series"]
    mean_monthly = {code: float(series[code][0].mean()) for code in fg_items if code in series}

    sl_to_pct = {0.90: "p90", 0.95: "p95", 0.98: "p98"}
    rows = []
    for _, sc in grid.iterrows():
        h = int(sc["protection_period_months"])
        sl = sc["cycle_service_level"]
        pct_col = sl_to_pct[sl]
        for code in fg_items:
            if code not in mean_monthly:
                continue
            d = dist_df[(dist_df["itemcode"] == code) & (dist_df["horizon_months"] == h)]
            if d.empty:
                continue
            d = d.iloc[0]
            mean_h = d["mean"]
            pctl = d[pct_col]
            safety_stock = pctl - mean_h
            min_qty = mean_h + safety_stock  # == pctl, stated both ways per the safety-stock convention
            replenishment_qty = mean_monthly[code] * (review_interval_days / 30.44)
            max_qty = min_qty + replenishment_qty
            rows.append({
                "itemcode": code, "procurement_lead_time_days": sc["procurement_lead_time_days"],
                "assembly_time_days": sc["assembly_time_days"], "cycle_service_level": sl,
                "protection_period_months": h, "is_default_scenario": sc["is_default_scenario"],
                "mean_protection_period_demand": mean_h, "percentile_used": pctl,
                "safety_stock": safety_stock, "min_qty": min_qty,
                "replenishment_qty": replenishment_qty, "max_qty": max_qty,
                "n_nonzero_windows": d["n_nonzero_windows"],
                "too_few_for_upper_percentiles": bool(d["too_few_for_upper_percentiles"]),
            })
    return pd.DataFrame(rows)


def forward_forecast_consumption(scope: pd.DataFrame, series_bundle: dict, fg_items: list,
                                  horizon: int, config: dict) -> pd.DataFrame:
    """Genuine FORWARD-looking (not backtest) Top-down forecast for the default scenario's
    protection-period window, starting the month AFTER the last historical month (2026-08
    onward), with confirmed future cube_Sale_APD MPS orders and OVERDUE Cube_Backlog rows
    consuming that forecast per config['phase_e1_assumptions']['forecast_consumption_logic'].
    """
    series = series_bundle["series"]
    pull_date = pd.Timestamp(series_bundle["pull_date"])
    fc = topdown_item_forecast(scope, series, fit_end=TOTAL_MONTHS, horizon=horizon)

    future_months = pd.period_range(start=pd.Period(LAST_HISTORY_MONTH, freq="M") + 1, periods=horizon, freq="M")
    logger.info("Forward forecast window (default scenario, horizon=%d): %s to %s.",
                horizon, future_months[0], future_months[-1])

    confirmed = query_confirmed_future_orders(fg_items, LAST_HISTORY_MONTH_END)
    n_before_horizon_check = len(confirmed)
    confirmed["ym"] = confirmed["forecast_date"].dt.to_period("M")
    confirmed_in_window = confirmed[confirmed["ym"].isin(future_months)]
    logger.info("Confirmed future MPS orders: %d rows total (forecast_date > %s), %d fall inside "
                "the %d-month forward window used here (the rest are due further out, not "
                "relevant to this protection period).",
                n_before_horizon_check, LAST_HISTORY_MONTH_END, len(confirmed_in_window), horizon)
    mps_by_item_month = confirmed_in_window.groupby(["itemcode", "ym"])["qty"].sum()

    backlog = query_backlog(fg_items)
    overdue = backlog[backlog["effective_date"] < pull_date]
    overdue_by_item = overdue.groupby("itemcode")["quantity"].sum()
    future_backlog = backlog[backlog["effective_date"] >= pull_date].copy()
    future_backlog["ym"] = future_backlog["effective_date"].dt.to_period("M")
    n_future_backlog_in_window = int(future_backlog["ym"].isin(future_months).sum())
    logger.info("Backlog: %d overdue rows (delivery/plan date before the snapshot pull date %s) "
                "treated as immediate Period-1 demand; %d non-overdue backlog rows fall inside "
                "this forward window but are NOT separately added (per config "
                "'backlog_vs_mps_double_count_note' -- future-period confirmed demand is read "
                "from cube_Sale_APD MPS only, to avoid a plausible double count with Cube_Backlog).",
                len(overdue), pull_date.date(), n_future_backlog_in_window)

    rows = []
    for code in fg_items:
        if code not in fc:
            continue
        for i, ym in enumerate(future_months):
            raw_forecast = float(fc[code][i])
            confirmed_qty = float(mps_by_item_month.get((code, ym), 0.0))
            if i == 0:
                confirmed_qty += float(overdue_by_item.get(code, 0.0))
            remainder = max(0.0, raw_forecast - confirmed_qty)
            net_demand = confirmed_qty + remainder
            pct_consumed = 100 * min(confirmed_qty, raw_forecast) / raw_forecast if raw_forecast > 0 else (
                100.0 if confirmed_qty > 0 else 0.0)
            rows.append({"itemcode": code, "year_month": str(ym), "relative_month": i + 1,
                         "raw_statistical_forecast": raw_forecast, "confirmed_known_demand": confirmed_qty,
                         "forecast_remainder": remainder, "net_period_demand": net_demand,
                         "pct_of_forecast_consumed": pct_consumed})
    return pd.DataFrame(rows)


def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(CHARTS_DIR, exist_ok=True)
    config = load_config()
    e1 = config["phase_e1_assumptions"]

    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)

    segments = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_item_segments.csv"))
    fg_items = segments.loc[segments["fg_stock_policy_supported"] == True, "code"].tolist()
    logger.info("%d items carry E1.1's FG-stock-supported flag -- ONLY these get a Min/Max here.", len(fg_items))

    dist_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1_2_empirical_distribution.csv"))
    grid = build_scenario_grid(e1)
    grid.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_scenario_grid.csv"), index=False)

    minmax = compute_minmax(fg_items, series_bundle, dist_df, grid, e1["review_interval_days_default"])
    minmax.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_minmax_all_scenarios.csv"), index=False)
    logger.info("Computed Min/Max for %d (item x scenario) cells across %d items x %d scenarios.",
                len(minmax), minmax["itemcode"].nunique(), len(grid))

    default_scenario_df = minmax[minmax["is_default_scenario"]]
    default_scenario_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_minmax_default_scenario.csv"), index=False)
    logger.info("Default scenario (lead=%dd, assembly=%dd, service=%.0f%%, horizon=%d months): "
                "%d items priced. Mean Min=%.1f, mean Max=%.1f (units).",
                e1["default_scenario"]["procurement_lead_time_days"], e1["default_scenario"]["assembly_time_days"],
                100 * e1["default_scenario"]["cycle_service_level"],
                int(default_scenario_df["protection_period_months"].iloc[0]), len(default_scenario_df),
                default_scenario_df["min_qty"].mean(), default_scenario_df["max_qty"].mean())

    default_h = int(default_scenario_df["protection_period_months"].iloc[0])
    consumption = forward_forecast_consumption(scope, series_bundle, fg_items, default_h, config)
    consumption.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_forecast_consumption.csv"), index=False)
    monthly_consumption_summary = consumption.groupby("year_month", as_index=False).agg(
        n_items=("itemcode", "nunique"), total_raw_forecast=("raw_statistical_forecast", "sum"),
        total_confirmed=("confirmed_known_demand", "sum"), total_net_demand=("net_period_demand", "sum"))
    monthly_consumption_summary["pct_of_forecast_consumed"] = np.where(
        monthly_consumption_summary["total_raw_forecast"] > 0,
        100 * np.minimum(monthly_consumption_summary["total_confirmed"], monthly_consumption_summary["total_raw_forecast"])
        / monthly_consumption_summary["total_raw_forecast"], 0.0)
    monthly_consumption_summary.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_forecast_consumption_monthly_summary.csv"), index=False)

    # ---- sellable stock context for the FG items (used more heavily in E1.4/E1.5) ----
    inv = query_inventory_exact(fg_items)
    sellable = sellable_stock_per_item(inv, fg_items, e1["sellable_warehouse_codes"])
    sellable.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_sellable_stock.csv"), index=False)

    # ---- chart: scenario sensitivity (Min/Max vs lead time, faceted by service level) ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    agg = minmax.groupby(["procurement_lead_time_days", "assembly_time_days", "cycle_service_level"],
                          as_index=False)[["min_qty", "max_qty"]].mean()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for at, ax in zip(sorted(agg["assembly_time_days"].unique()), axes):
        sub = agg[agg["assembly_time_days"] == at]
        for sl, g in sub.groupby("cycle_service_level"):
            g = g.sort_values("procurement_lead_time_days")
            ax.plot(g["procurement_lead_time_days"], g["min_qty"], marker="o", label=f"Min, SL={sl:.0%}")
            ax.plot(g["procurement_lead_time_days"], g["max_qty"], marker="s", linestyle="--", label=f"Max, SL={sl:.0%}")
        ax.set_title(f"Assembly time = {at} days")
        ax.set_xlabel("Procurement lead time (days)")
        ax.legend(fontsize=7)
    axes[0].set_ylabel("Mean Min/Max across 66 FG-stock items (units)")
    fig.suptitle("E1.3 Min/Max scenario sensitivity (18-scenario grid, mean across 66 FG-stock items)")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "phaseE1_minmax_scenario_sensitivity.png"), dpi=120)
    plt.close(fig)
    logger.info("Chart: output/charts/phaseE1_minmax_scenario_sensitivity.png")

    print("\n=== E1.3 DEFAULT SCENARIO -- SAMPLE ===")
    print(default_scenario_df.head(10).round(2).to_string(index=False))
    print("\n=== E1.3 FORECAST CONSUMPTION, MONTHLY SUMMARY (default scenario, 66 FG items) ===")
    print(monthly_consumption_summary.round(1).to_string(index=False))

    return {"minmax": minmax, "grid": grid, "consumption": consumption,
            "monthly_consumption_summary": monthly_consumption_summary, "fg_items": fg_items,
            "default_h": default_h}


if __name__ == "__main__":
    main()
