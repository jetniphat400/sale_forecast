"""Phase E1 — Validator, targeted re-check (Orchestrator follow-up, 2026-09-18).

Re-does ONLY Figure 1 (Min, 3 focus items) and Figure 2 (consumption total, 3 focus items) using
the project's LOCKED, adopted, FROZEN series (config['adopted_series_key'] = "forecastDate",
output/data/processed_full_category_sales_monthly_forecastDate.csv, snapshot_pull_date
2026-09-04 16:44:45, months 2024-01 to 2026-07 — 31 months) instead of the original report's live
DB pull (2026-09-18, 32 months through 2026-08).

This file is NOT a phaseE1_* Modeler file — it is this Validator's own re-check script, reusing
this Validator's own already-written functions from phaseE1_validator.py (import only; no
phaseE1_* Modeler output was read). Figures 3 and 4 are untouched, per the Orchestrator's
explicit instruction.

output/data/processed_full_category_sales_monthly_forecastDate.csv is produced by
src/load_data_full.py, a pre-existing (pre-Phase-E1) script explicitly in this Validator's
allowed-to-reuse list — reading its FROZEN OUTPUT FILE (not a live re-query) is exactly what the
task's "adopted_series_key ... captured as a frozen snapshot" convention requires; it is not a
Modeler intermediate for Phase E1, it predates Phase E1 entirely (Phase B1, 2026-09-02/04).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_validator import (  # noqa: E402  (import after sys.path insert, same pattern as the module itself)
    load_config, derive_128_scope, check_overlaps, empirical_min,
    build_topdown_item_forecast, horizon_months, query_mps_future, query_backlog_for_items,
    FOCUS_ITEMS, protection_period_months,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_validator_frozen_recheck")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FROZEN_FILE = os.path.join(PROJECT_ROOT, "output", "data",
                            "processed_full_category_sales_monthly_forecastDate.csv")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def load_frozen_series() -> tuple:
    df = pd.read_csv(FROZEN_FILE)
    required = {"itemcode", "year_month", "qty", "snapshot_pull_date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{FROZEN_FILE} missing required column(s): {missing} — actual columns: {df.columns.tolist()}")
    df["year_month"] = pd.PeriodIndex(df["year_month"], freq="M")
    snapshot_pull_date = pd.Timestamp(df["snapshot_pull_date"].iloc[0])
    n_dates = df["snapshot_pull_date"].nunique()
    if n_dates != 1:
        raise ValueError(f"Expected exactly one snapshot_pull_date in the frozen file, found {n_dates}")
    logger.info("Loaded frozen file %s: %d items, %d rows, snapshot_pull_date=%s, months %s to %s",
                FROZEN_FILE, df["itemcode"].nunique(), len(df), snapshot_pull_date,
                df["year_month"].min(), df["year_month"].max())
    return df, snapshot_pull_date


if __name__ == "__main__":
    config = load_config()
    scope = derive_128_scope(config)
    overlap = check_overlaps(config, scope)
    item_type_map = dict(zip(scope["code"], scope["type"]))
    keep_codes = set(overlap["keep_codes"])

    monthly_full, snapshot_pull_date = load_frozen_series()
    last_complete_month = monthly_full["year_month"].max()  # 2026-07, the frozen file's own last month
    days, h_months = protection_period_months(config)
    csl = config["phase_e1_assumptions"]["default_scenario"]["cycle_service_level"]

    print("=" * 100)
    print("TARGETED RE-CHECK — Figure 1 (Min) using the FROZEN forecastDate series")
    print("=" * 100)
    print(f"Frozen file: {FROZEN_FILE}")
    print(f"snapshot_pull_date (frozen) = {snapshot_pull_date}  |  months: "
          f"{monthly_full['year_month'].min()} to {last_complete_month} "
          f"({monthly_full['year_month'].nunique()} months)")
    print(f"(Original report used a LIVE pull: snapshot_pull_date=2026-09-18, 32 months through 2026-08.)")

    fig1_rows = []
    for item in FOCUS_ITEMS:
        g = monthly_full[monthly_full["itemcode"] == item].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        res = empirical_min(qty, h_months, csl)
        res["itemcode"] = item
        res["n_months_history"] = len(qty)
        fig1_rows.append(res)
        print(f"{item}: n_months={len(qty)}, n_windows={res['n_windows']}, "
              f"mean={res['mean_protection_demand']:.2f}, p{csl*100:.0f}={res['percentile_value']:.2f}, "
              f"safety_stock={res['safety_stock']:.2f}, Min={res['min']:.2f}")
    fig1_df = pd.DataFrame(fig1_rows)
    fig1_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig1_min_FROZEN.csv"), index=False)

    print("\n" + "=" * 100)
    print("TARGETED RE-CHECK — Figure 2 (consumption) using the FROZEN forecastDate series")
    print("=" * 100)
    horizon = horizon_months(last_complete_month, h_months)
    print(f"Horizon (month after the frozen series' own last month {last_complete_month}): {horizon}")

    # Confirmed demand (MPS + overdue backlog) is queried LIVE — no frozen equivalent exists for
    # these tables, and the task never asked for one; only the ACTUAL-HISTORY input series (used
    # for the Top-down fit and, in Figure 1, the empirical distribution) is frozen. The "now" used
    # to split Cube_Backlog into "overdue" (Period 1) vs "future" is the frozen file's own
    # snapshot_pull_date (2026-09-04 16:44:45), NOT today (2026-09-18) — this keeps the whole
    # re-check internally consistent with "what this figure would have been at the Modeler's own
    # frozen snapshot," rather than mixing a 2026-09-04 historical window with a 2026-09-18
    # confirmed-order cutoff.
    mps_future = query_mps_future(config, FOCUS_ITEMS)
    mps_future["year_month"] = mps_future["forecast_date"].dt.to_period("M")
    backlog = query_backlog_for_items(FOCUS_ITEMS)
    overdue = backlog[backlog["effective_date"].notna() & (backlog["effective_date"] < snapshot_pull_date)]
    future_backlog = backlog[backlog["effective_date"].notna() & (backlog["effective_date"] >= snapshot_pull_date)]
    print(f"NOTE: overdue/future backlog split uses the FROZEN snapshot_pull_date ({snapshot_pull_date}) "
          f"as 'now', not today. {len(future_backlog)} future-dated backlog rows excluded from "
          f"future periods (same stated scope decision as the original report).")

    type_series_map = {}
    for typ, g in monthly_full.groupby("type") if "type" in monthly_full.columns else []:
        pass  # placeholder, real build below (frozen file's own 'type' column is used directly)
    monthly_full_typed = monthly_full.copy()
    if "type" not in monthly_full_typed.columns:
        monthly_full_typed["type"] = monthly_full_typed["itemcode"].map(item_type_map)
    for typ, g in monthly_full_typed.groupby("type"):
        gg = g[g["itemcode"].isin(keep_codes)]
        type_series_map[typ] = gg.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")

    fig2_rows = []
    for item in FOCUS_ITEMS:
        item_type = item_type_map[item]
        fc, share = build_topdown_item_forecast(item, item_type, monthly_full_typed, type_series_map,
                                                 last_complete_month, h_months)
        for i, per in enumerate(horizon):
            confirmed_mps = mps_future[(mps_future["itemcode"] == item) &
                                        (mps_future["year_month"] == per)]["qty"].sum()
            confirmed = confirmed_mps
            if i == 0:
                overdue_qty = overdue[overdue["itemcode"] == item]["quantity"].sum()
                confirmed = confirmed + overdue_qty
            forecast_val = fc[i]
            pct = 100 * confirmed / forecast_val if forecast_val > 0 else np.nan
            fig2_rows.append({"itemcode": item, "period": i + 1, "year_month": str(per),
                               "confirmed_qty": confirmed, "raw_forecast": forecast_val,
                               "pct_of_forecast_consumed": pct, "topdown_share": share})
            print(f"{item} period {i+1} ({per}): confirmed={confirmed:.1f}, forecast={forecast_val:.2f}, "
                  + (f"%consumed={pct:.1f}%" if pd.notna(pct) else "%consumed=N/A"))
    fig2_df = pd.DataFrame(fig2_rows)
    fig2_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig2_consumption_FROZEN.csv"), index=False)
    fig2_total = fig2_df.groupby("itemcode", as_index=False)[["confirmed_qty", "raw_forecast"]].sum()
    fig2_total["pct_of_forecast_consumed_total"] = 100 * fig2_total["confirmed_qty"] / fig2_total["raw_forecast"]
    print("\nTotals across the whole horizon, per item:")
    print(fig2_total.to_string(index=False))
    grand_confirmed = float(fig2_df["confirmed_qty"].sum())
    grand_forecast = float(fig2_df["raw_forecast"].sum())
    print(f"\nGRAND TOTAL (3 focus items, whole horizon): confirmed={grand_confirmed:.1f}, "
          f"forecast={grand_forecast:.1f}, pct={100*grand_confirmed/grand_forecast:.1f}%")

    print("\nDONE. CSVs: output/summary/phaseE1_validator_fig{1,2}_*_FROZEN.csv")
