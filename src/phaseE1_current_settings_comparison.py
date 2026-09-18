"""Phase E1.5 (Modeler): compare the default scenario against CURRENT Min/Max settings.

Current Min/Max values are used here ONLY as a comparison baseline, per STATUS.md's locked
finding ("The existing min/max values in the inventory system cannot be used as inputs to any
calculation ... may be used only as a comparison baseline to show what would change under a new
policy") -- this script does exactly that, nothing more.

Also computes the 128-item-pilot-scope CURRENT total priced stock value directly from
Cube_Inventory_Exact, honestly alongside Phase D's existing THB 37,399,005.48 figure (which is
for the FULL 445-item universe, NOT this 128-item scope) -- flagging the scope mismatch rather
than silently conflating the two, per the task's explicit instruction.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import (
    SUMMARY_DIR, load_config, load_scope, load_monthly_series,
    query_inventory_exact, current_minmax_per_item, compute_unit_cost,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_current_settings_comparison")

PHASE_D_FULL_445_STOCK_VALUE_THB = 37399005.48  # output/summary/phaseD_check2_report.md, cited, not recomputed here


def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    obsolescence_threshold = e1["obsolescence_threshold_months"]

    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    series = series_bundle["series"]
    all_128 = scope["code"].tolist()

    logger.info("=== Current Min/Max (Cube_Inventory_Exact, comparison baseline only) ===")
    inv = query_inventory_exact(all_128)
    current = current_minmax_per_item(inv, all_128)
    n_with_setting = int(current["has_current_setting"].sum())
    logger.info("%d of %d 128-item-scope codes have a current Min or Max setting in Cube_Inventory_Exact "
                "(STATUS.md: 46/128 previously found with NO setting at pilot scope -- re-derived here "
                "fresh, not assumed unchanged).", n_with_setting, len(current))

    logger.info("=== Current stock value, 128-item pilot scope (apples-to-apples with the 445-item figure) ===")
    unit_cost = compute_unit_cost(all_128)
    cost_map = dict(zip(unit_cost["itemcode"], unit_cost["primary_unit_cost"]))
    stock_qty_all_wh = inv.groupby("itemcode", as_index=False)["stock"].sum().rename(columns={"stock": "qty_all_wh"})
    value_df = pd.DataFrame({"itemcode": all_128}).merge(stock_qty_all_wh, on="itemcode", how="left")
    value_df["qty_all_wh"] = value_df["qty_all_wh"].fillna(0.0)
    value_df["unit_cost"] = value_df["itemcode"].map(cost_map)
    value_df["stock_value_thb"] = np.where(value_df["unit_cost"].notna(), value_df["qty_all_wh"] * value_df["unit_cost"], np.nan)
    n_no_cost = int(value_df["unit_cost"].isna().sum())
    total_128_value = float(value_df["stock_value_thb"].sum(skipna=True))
    unpriced_qty = float(value_df.loc[value_df["unit_cost"].isna(), "qty_all_wh"].sum())
    logger.info("128-item pilot-scope CURRENT stock value (all warehouses, no sellability filter, same "
                "unit-cost methodology as Phase D Check 2): THB %.2f priced (%d/%d items priced, %d items/"
                "%.1f units have NO cost record, value undetermined for those). Phase D's cited FULL "
                "445-item figure is THB %.2f -- DIFFERENT SCOPE, not directly comparable without this "
                "128-item recomputation.",
                total_128_value, len(value_df) - n_no_cost, len(value_df), n_no_cost, unpriced_qty,
                PHASE_D_FULL_445_STOCK_VALUE_THB)

    logger.info("=== Compare current vs default-scenario Min/Max, for the 66 FG-stock items ===")
    segments = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_item_segments.csv"))
    default_mm = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1_3_minmax_default_scenario.csv"))

    mean_monthly = pd.DataFrame([{"itemcode": c, "mean_monthly_qty": float(series[c][0].mean())}
                                  for c in all_128 if c in series])

    comp = current.merge(segments[["code", "fg_stock_policy_supported", "eligible_for_policy", "segment"]],
                          left_on="itemcode", right_on="code", how="left").drop(columns=["code"])
    comp = comp.merge(default_mm[["itemcode", "min_qty", "max_qty", "protection_period_months"]],
                       on="itemcode", how="left").rename(
        columns={"min_qty": "scenario_default_min", "max_qty": "scenario_default_max"})
    comp = comp.merge(mean_monthly, on="itemcode", how="left")
    comp = comp.merge(value_df[["itemcode", "unit_cost"]], on="itemcode", how="left")

    comp["has_scenario_policy"] = comp["scenario_default_min"].notna()
    comp["no_scenario_policy_reason"] = np.select(
        [~comp["eligible_for_policy"].fillna(False),
         comp["eligible_for_policy"].fillna(False) & ~comp["fg_stock_policy_supported"].fillna(False)],
        ["no supported policy: placeholder/excluded item, no real forecast exists (see E1.1)",
         "E1.1 found Component-stock/assemble-to-order, not finished-goods stock, as this segment's "
         "supported policy -- no FG Min/Max computed for it in E1.3"],
        default="")

    comp["direction_min"] = np.select(
        [~comp["has_scenario_policy"], comp["scenario_default_min"] > comp["current_total_min"],
         comp["scenario_default_min"] < comp["current_total_min"]],
        ["N/A", "up", "down"], default="same")
    comp["direction_max"] = np.select(
        [~comp["has_scenario_policy"], comp["scenario_default_max"] > comp["current_total_max"],
         comp["scenario_default_max"] < comp["current_total_max"]],
        ["N/A", "up", "down"], default="same")
    comp["value_change_min_thb"] = np.where(
        comp["has_scenario_policy"] & comp["unit_cost"].notna(),
        (comp["scenario_default_min"] - comp["current_total_min"]) * comp["unit_cost"], np.nan)
    comp["value_change_max_thb"] = np.where(
        comp["has_scenario_policy"] & comp["unit_cost"].notna(),
        (comp["scenario_default_max"] - comp["current_total_max"]) * comp["unit_cost"], np.nan)

    # (a) current cover ABOVE the obsolescence threshold
    comp["current_max_months_of_cover"] = np.where(
        comp["mean_monthly_qty"] > 0, comp["current_total_max"] / comp["mean_monthly_qty"], np.nan)
    comp["cover_note"] = np.select(
        [comp["mean_monthly_qty"].isna(), comp["mean_monthly_qty"] == 0],
        ["N/A -- item not in the forecast_date-keyed monthly series (no history)",
         "undefined -- zero mean monthly demand, cover is indefinitely long if any stock/setting is held"],
        default="")
    comp["above_obsolescence_threshold"] = comp["current_max_months_of_cover"] > obsolescence_threshold

    # (b) current cover BELOW one full default-scenario protection period
    comp["below_full_protection_period"] = (
        comp["has_scenario_policy"] &
        (comp["current_max_months_of_cover"].fillna(-1) < comp["protection_period_months"]))

    out_cols = ["itemcode", "segment", "current_total_min", "current_total_max", "n_warehouses",
                "has_current_setting", "scenario_default_min", "scenario_default_max",
                "protection_period_months", "has_scenario_policy", "no_scenario_policy_reason",
                "direction_min", "direction_max", "value_change_min_thb", "value_change_max_thb",
                "mean_monthly_qty", "current_max_months_of_cover", "cover_note",
                "above_obsolescence_threshold", "below_full_protection_period"]
    comp_out = comp[out_cols].sort_values("itemcode")
    comp_out.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_5_current_vs_scenario.csv"), index=False)
    value_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_5_current_stock_value_128items.csv"), index=False)

    n_above = int(comp["above_obsolescence_threshold"].fillna(False).sum())
    n_below = int(comp["below_full_protection_period"].fillna(False).sum())
    n_up_min = int((comp["direction_min"] == "up").sum())
    n_down_min = int((comp["direction_min"] == "down").sum())
    logger.info("Comparison: %d/%d items have a current setting; of the %d FG-stock items with a scenario "
                "policy, %d would see Min go UP, %d DOWN under the default scenario. %d items' current "
                "Max implies cover ABOVE the %d-month obsolescence threshold; %d items' current Max "
                "implies cover BELOW one full default-scenario protection period (%s months).",
                n_with_setting, len(comp), int(comp["has_scenario_policy"].sum()), n_up_min, n_down_min,
                n_above, obsolescence_threshold, n_below,
                default_mm["protection_period_months"].iloc[0] if len(default_mm) else "?")

    print("\n=== E1.5 SAMPLE: current vs default-scenario Min/Max (FG-stock items only) ===")
    print(comp_out[comp_out["has_scenario_policy"]].head(10).round(2).to_string(index=False))

    return {"comp": comp_out, "value_128": total_128_value, "value_445_cited": PHASE_D_FULL_445_STOCK_VALUE_THB,
            "n_with_setting": n_with_setting, "n_above": n_above, "n_below": n_below}


if __name__ == "__main__":
    main()
