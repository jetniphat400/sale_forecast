"""Phase E1 — Validator, targeted re-check #2 (Orchestrator follow-up, 2026-09-18).

Re-does Figure 3 (FG-stock-policy-supported set, Min/Max, total scenario stock value) and
Figure 4 (fill rate simulation) using the project's LOCKED, adopted, FROZEN series
(output/data/processed_full_category_sales_monthly_forecastDate.csv, snapshot_pull_date
2026-09-04 16:44:45, 31 months 2024-01 to 2026-07) as the historical-actuals input EVERYWHERE
this Validator's original report used a live DB pull (32 months through 2026-08) — for all 112
non-excluded/non-placeholder items, not just the 3 focus items already re-checked.

Per the Orchestrator's explicit instruction:
  - Demand classification (ADI/CV²), annual value, order frequency, the empirical
    protection-period distributions feeding Min/Max, and the simulation replay window ALL now use
    the frozen series.
  - `confirmed_known_demand` is NOT part of Figures 3/4 at all (that was Figure 2 only) --
    nothing to change there.
  - Unit cost stays a LIVE query (cube_Sale_APD cost/qty), unchanged from the original report --
    the Orchestrator's instruction lists demand-side inputs only, not the cost basis.
  - The Validator's own independent segmentation methodology (ADI/CV² classes, the "both
    low-value AND low-frequency" median-split exclusion rule) is kept EXACTLY as originally
    designed -- only the input data window changes, not the judgment calls.
  - The simulation replay window is capped at the frozen series' own last month (2026-07), not
    extended -- stated explicitly, consistent with "31 months, 2024-01 to 2026-07" throughout.

This file re-uses this Validator's own already-written functions from phaseE1_validator.py
(import only). No phaseE1_* Modeler file was read.
"""
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_validator import (  # noqa: E402
    load_config, derive_128_scope, check_overlaps, classify_adi_cv2, query_unit_cost,
    empirical_min, simulate_item, query_sellable_onhand, protection_period_months, DAYS_PER_MONTH,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_validator_frozen_recheck_fig34")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FROZEN_FILE = os.path.join(PROJECT_ROOT, "output", "data",
                            "processed_full_category_sales_monthly_forecastDate.csv")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def load_frozen_series() -> tuple:
    df = pd.read_csv(FROZEN_FILE)
    required = {"itemcode", "year_month", "qty", "snapshot_pull_date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{FROZEN_FILE} missing required column(s): {missing}")
    df["year_month"] = pd.PeriodIndex(df["year_month"], freq="M")
    snapshot_pull_date = pd.Timestamp(df["snapshot_pull_date"].iloc[0])
    n_dates = df["snapshot_pull_date"].nunique()
    if n_dates != 1:
        raise ValueError(f"Expected exactly one snapshot_pull_date, found {n_dates}")
    return df, snapshot_pull_date


if __name__ == "__main__":
    config = load_config()
    scope = derive_128_scope(config)
    overlap = check_overlaps(config, scope)
    keep_codes = overlap["keep_codes"]
    item_type_map = dict(zip(scope["code"], scope["type"]))

    monthly_full, snapshot_pull_date = load_frozen_series()
    n_months_series = monthly_full["year_month"].nunique()
    min_m, max_m = monthly_full["year_month"].min(), monthly_full["year_month"].max()
    logger.info("Frozen file loaded: %d items, %d months (%s to %s), snapshot_pull_date=%s",
                monthly_full["itemcode"].nunique(), n_months_series, min_m, max_m, snapshot_pull_date)

    missing_from_frozen = set(keep_codes) - set(monthly_full["itemcode"].unique())
    if missing_from_frozen:
        logger.warning("%d of the 112 keep_codes are ABSENT from the frozen file (zero-history "
                        "items, treated as an all-zero 31-month series): %s",
                        len(missing_from_frozen), sorted(missing_from_frozen))
        pad_rows = []
        for code in missing_from_frozen:
            for m in pd.period_range(min_m, max_m, freq="M"):
                pad_rows.append({"itemcode": code, "year_month": m, "qty": 0.0})
        monthly_full = pd.concat([monthly_full, pd.DataFrame(pad_rows)], ignore_index=True)

    days, h_months = protection_period_months(config)
    csl = config["phase_e1_assumptions"]["default_scenario"]["cycle_service_level"]
    review = config["phase_e1_assumptions"]["review_interval_days_default"]
    lead = config["phase_e1_assumptions"]["default_scenario"]["procurement_lead_time_days"]
    assembly = config["phase_e1_assumptions"]["default_scenario"]["assembly_time_days"]

    print("=" * 100)
    print("TARGETED RE-CHECK #2 — Figure 3 (FG-set, Min/Max, stock value) on the FROZEN series")
    print("=" * 100)
    print(f"Frozen file: {FROZEN_FILE}")
    print(f"snapshot_pull_date (frozen) = {snapshot_pull_date}  |  months: {min_m} to {max_m} "
          f"({n_months_series} months)")
    print("(Original report used a LIVE pull: 32 months through 2026-08, for all 112 items.)")

    fig3_rows = []
    for code in keep_codes:
        g = monthly_full[monthly_full["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        adi, cv2, cls = classify_adi_cv2(qty)
        mean_monthly = float(qty.mean())
        n_m = len(qty)
        n_nonzero = int((qty > 0).sum())
        order_freq = n_nonzero / n_m if n_m else np.nan
        fig3_rows.append({"itemcode": code, "type": item_type_map[code], "adi": adi, "cv2": cv2,
                           "demand_class": cls, "mean_monthly_qty": mean_monthly,
                           "order_frequency": order_freq, "n_nonzero_months": n_nonzero,
                           "n_months": n_m})
    fig3_df = pd.DataFrame(fig3_rows)

    unit_cost_df = query_unit_cost(keep_codes, config["phase_e1_assumptions"]["unit_cost_median_window_months"])
    fig3_df = fig3_df.merge(unit_cost_df, on="itemcode", how="left")
    fig3_df["annual_value"] = fig3_df["mean_monthly_qty"] * 12 * fig3_df["primary_unit_cost"].fillna(0.0)

    median_value = fig3_df["annual_value"].median()
    median_freq = fig3_df["order_frequency"].median()
    fig3_df["low_value"] = fig3_df["annual_value"] < median_value
    fig3_df["low_frequency"] = fig3_df["order_frequency"] < median_freq
    fig3_df["fg_stock_supported"] = ~(fig3_df["low_value"] & fig3_df["low_frequency"])
    n_fg = int(fig3_df["fg_stock_supported"].sum())
    print(f"Median annual_value (frozen series): {median_value:,.2f} THB   "
          f"(original live-pull: 236,310.53 THB)")
    print(f"Median order_frequency (frozen series): {median_freq:.3f}   (original live-pull: 0.781)")
    print(f"Same segmentation rule as the original report (unchanged): exclude only the BOTH "
          f"low-value AND low-frequency quadrant.")
    print(f"Resulting FG-stock-supported set: {n_fg} of {len(fig3_df)} items "
          f"(original live-pull result: 68 of 112).")
    fig3_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig3_fg_classification_FROZEN.csv"), index=False)

    fg_set = fig3_df[fig3_df["fg_stock_supported"]].copy()
    replen_rows = []
    for _, row in fg_set.iterrows():
        code = row["itemcode"]
        g = monthly_full[monthly_full["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        res = empirical_min(qty, h_months, csl)
        if res is None:
            continue
        replen_qty = row["mean_monthly_qty"] * (review / DAYS_PER_MONTH)
        max_qty = res["min"] + replen_qty
        replen_rows.append({"itemcode": code, "min": res["min"], "replen_qty": replen_qty,
                             "max": max_qty, "unit_cost": row["primary_unit_cost"],
                             "cost_basis": row["primary_basis"]})
    minmax_df = pd.DataFrame(replen_rows)
    minmax_df["max_value"] = minmax_df["max"] * minmax_df["unit_cost"].fillna(0.0)
    minmax_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig3_minmax_FROZEN.csv"), index=False)

    n_priced = int(minmax_df["unit_cost"].notna().sum())
    total_stock_value = float(minmax_df.loc[minmax_df["unit_cost"].notna(), "max_value"].sum())
    print(f"\nItems with a Min/Max computed: {len(minmax_df)} of {n_fg} FG-stock-supported items")
    print(f"Items with a usable unit cost (LIVE query, unchanged from original): {n_priced} of {len(minmax_df)}")
    print(f"PRIMARY (FROZEN): total scenario stock value = THB {total_stock_value:,.2f}   "
          f"(original live-pull: THB 95,834,332.32)")

    sellable = query_sellable_onhand(fg_set["itemcode"].tolist(),
                                      config["phase_e1_assumptions"]["sellable_warehouse_codes"])
    sellable = sellable.merge(minmax_df[["itemcode", "unit_cost"]], on="itemcode", how="left")
    sellable["onhand_value"] = sellable["sellable_onhand"] * sellable["unit_cost"].fillna(0.0)
    secondary_value = float(sellable.loc[sellable["unit_cost"].notna(), "onhand_value"].sum())
    print(f"SECONDARY (alternate interpretation, current sellable on-hand, LIVE query unchanged): "
          f"THB {secondary_value:,.2f}   (original: THB 11,541,666.37)")

    print("\n" + "=" * 100)
    print("TARGETED RE-CHECK #2 — Figure 4 (fill rate simulation) on the FROZEN series")
    print("=" * 100)
    lead_months = math.ceil((lead + assembly) / DAYS_PER_MONTH)
    print(f"Replay window: {min_m} to {max_m} ({n_months_series} months) — CAPPED at the frozen "
          f"series' own last month (2026-07), NOT extended, per the Orchestrator's instruction to "
          f"stay consistent with the frozen series rather than mixing in a live partial tail.")
    print(f"lead_months (lead+assembly only) = ceil(({lead}+{assembly})/{DAYS_PER_MONTH}) = {lead_months}")

    sim_rows = []
    total_demand_all, total_fulfilled_all, total_stockout_months = 0.0, 0.0, 0
    for _, row in minmax_df.iterrows():
        code = row["itemcode"]
        g = monthly_full[monthly_full["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        max_qty = row["max"]
        res = simulate_item(qty, max_qty, lead_months)
        res["itemcode"] = code
        sim_rows.append(res)
        total_demand_all += res["total_demand"]
        total_fulfilled_all += res["total_fulfilled"]
        total_stockout_months += res["stockout_months"]
    sim_df = pd.DataFrame(sim_rows)
    sim_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig4_simulation_FROZEN.csv"), index=False)

    fill_rate = 100 * total_fulfilled_all / total_demand_all if total_demand_all else np.nan
    print(f"Simulated {len(sim_df)} items, {n_months_series} months each ({min_m} to {max_m}).")
    print(f"AGGREGATE unit fill rate (FROZEN): {fill_rate:.2f}%   (original live-pull: 99.81%)")
    print(f"Total item-months with a stockout (FROZEN): {total_stockout_months} of "
          f"{int(sim_df['n_months'].sum())} item-months   (original: 12 of 2,176)")

    print("\nDONE. CSVs: output/summary/phaseE1_validator_fig{3,4}_*_FROZEN.csv")
