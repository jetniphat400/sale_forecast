"""Phase 23, Part 5: precompute a dense grid (the locked config.yaml trade_off_curve grid, 20
reorder-level points) of per-item Min/Max and total stock_value bands, for PEM101's selectable
not_late target on forecast/inventory.html. The page interpolates ONLY between these embedded grid
points -- no client-side simulation.

Reuses output/summary/phase23_modeler_tradeoff_curve_points.csv (member x grid_r -> not_late,
stock_value, already computed by Part 3) -- no new simulation run, no new database access. Rebuilds
the daily series once (cheap -- no simulate_months_of_demand calls) to get each item's own mean
daily demand, since Min(grid_r, item) = grid_r * 30.44 * mean_demand(item) is deterministic (does
not depend on which ensemble member you're sweeping from -- only Max depends on the member's own
s-minus-r gap).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, load_scope
import phaseJ3_calibration_engine as jc

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DAYS_PER_MONTH = 30.44

# Today's operating point -- J3 reconciled targets, cited (same figures as phase23_modeler.py):
# output/summary/phaseJ3_report.md (PEM101 valid not_late 98.28%) and
# output/summary/phaseJ3_validator_stock_value_summary.csv (current_stock_value_thb 18,247,625.22).
TODAY_NOT_LATE_PCT = 98.28
TODAY_STOCK_VALUE_THB = 18247625.22


def main():
    config = load_config()
    tc = config["trade_off_curve"]
    window = tc["simulation_window"]
    warmup = tc["warm_up"]

    scope = load_scope(config)
    elig = scope[scope["eligible_for_policy"]]
    codes = sorted(elig["code"].unique())

    raw = pd.read_csv(os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv"))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw_div = raw[raw["itemcode"].isin(codes)].copy()
    daily_bundle = jc.build_full_daily_series(raw_div, codes, warmup["start"], window["end"])
    daily_series = daily_bundle["series"]
    mean_demand = {c: float(daily_series[c].mean()) for c in codes}

    members = pd.read_csv(os.path.join(SUMMARY_DIR, "phase23_ensemble_distinct_members_PEM101.csv"))
    assert len(members) == 80
    members["gap"] = members["s_months"] - members["r_months"]
    gaps = members["gap"].values

    curve_points = pd.read_csv(os.path.join(SUMMARY_DIR, "phase23_modeler_tradeoff_curve_points.csv"))
    curve_valid = curve_points.dropna(subset=["not_late", "stock_value"])
    agg = curve_valid.groupby("swept_r_months").agg(
        not_late_median=("not_late", "median"),
        stock_value_min=("stock_value", "min"),
        stock_value_median=("stock_value", "median"),
        stock_value_max=("stock_value", "max"),
        n_members=("stock_value", "count"),
    ).reset_index().rename(columns={"swept_r_months": "r"}).sort_values("r")

    dense_grid = []
    for _, row in agg.iterrows():
        r = float(row["r"])
        item_rows = []
        for c in codes:
            md = mean_demand[c]
            min_val = r * DAYS_PER_MONTH * md
            max_vals = (r + gaps) * DAYS_PER_MONTH * md
            item_rows.append({
                "code": c,
                "Min": round(min_val, 2),
                "Max_median": round(float(pd.Series(max_vals).median()), 2),
                "Max_min": round(float(max_vals.min()), 2),
                "Max_max": round(float(max_vals.max()), 2),
            })
        dense_grid.append({
            "r": r,
            "not_late_median_pct": round(float(row["not_late_median"]) * 100, 3),
            "stock_value_min": round(float(row["stock_value_min"]), 2),
            "stock_value_median": round(float(row["stock_value_median"]), 2),
            "stock_value_max": round(float(row["stock_value_max"]), 2),
            "n_members": int(row["n_members"]),
            "items": item_rows,
        })

    # --- 3 presets, interpolated on the median curve (r, not_late_median_pct, stock_value_median) ---
    # Both not_late_median and stock_value_median are monotonically increasing in r across all 20
    # grid points (verified directly from the values above) -- linear interpolation between grid
    # points is well-defined and single-valued in both directions.
    r_arr = np.array([g["r"] for g in dense_grid])
    nl_arr = np.array([g["not_late_median_pct"] for g in dense_grid])
    sv_arr = np.array([g["stock_value_median"] for g in dense_grid])

    def interp_r_at_notlate(target_nl):
        return float(np.interp(target_nl, nl_arr, r_arr))

    def interp_r_at_stockvalue(target_sv):
        return float(np.interp(target_sv, sv_arr, r_arr))

    def sv_at_r(r_val):
        return float(np.interp(r_val, r_arr, sv_arr))

    def nl_at_r(r_val):
        return float(np.interp(r_val, r_arr, nl_arr))

    # Preset 1: today's not_late, at the lowest (median-curve) stock value that achieves it.
    r1 = interp_r_at_notlate(TODAY_NOT_LATE_PCT)
    preset1 = {"not_late_pct": round(TODAY_NOT_LATE_PCT, 3), "r": round(r1, 4),
               "stock_value_median": round(sv_at_r(r1), 2),
               "label": "Today's not_late (98.28%) at the lowest median stock value"}

    # Preset 2: the highest not_late the median curve reaches at today's actual stock value.
    r2 = interp_r_at_stockvalue(TODAY_STOCK_VALUE_THB)
    preset2 = {"not_late_pct": round(nl_at_r(r2), 3), "r": round(r2, 4),
               "stock_value_median": round(TODAY_STOCK_VALUE_THB, 2),
               "label": "Highest not_late the median curve reaches at today's stock value"}

    # Preset 3: 99% if reachable, else the curve's own highest point (labelled as capped).
    max_nl = float(nl_arr.max())
    if max_nl >= 99.0:
        r3 = interp_r_at_notlate(99.0)
        preset3 = {"not_late_pct": 99.0, "r": round(r3, 4), "stock_value_median": round(sv_at_r(r3), 2),
                   "capped": False, "label": "Stretch target: 99% not_late"}
    else:
        r3 = float(r_arr[-1])
        preset3 = {"not_late_pct": round(max_nl, 3), "r": round(r3, 4), "stock_value_median": round(sv_arr[-1], 2),
                   "capped": True, "label": f"Stretch target: curve's highest point ({max_nl:.2f}%, 99% not reached)"}

    print("\nPresets:")
    for name, p in [("today_lowest_stock", preset1), ("highest_at_today_stock", preset2), ("stretch_99pct", preset3)]:
        print(f"  {name}: {p}")

    out = {
        "grid": dense_grid,
        "n_distinct_members": int(len(members)),
        "items_order": codes,
        "today_point": {"not_late_pct": TODAY_NOT_LATE_PCT, "stock_value_thb": TODAY_STOCK_VALUE_THB,
                         "source": "output/summary/phaseJ3_report.md (valid not_late) + "
                                    "output/summary/phaseJ3_validator_stock_value_summary.csv "
                                    "(current_stock_value_thb) -- J3 reconciled targets"},
        "presets": {"today_lowest_stock": preset1, "highest_at_today_stock": preset2, "stretch_99pct": preset3},
        "not_late_range_pct": [round(float(nl_arr.min()), 3), round(float(nl_arr.max()), 3)],
        "source_report": "output/summary/phase23_modeler_report.md",
    }
    out_path = os.path.join(SUMMARY_DIR, "phase23_dense_grid_PEM101.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"\nSaved dense grid: {len(dense_grid)} r-points x {len(codes)} items -> {out_path}")

    not_lates = [g["not_late_median_pct"] for g in dense_grid]
    print(f"not_late_median range across grid: {min(not_lates):.2f}% - {max(not_lates):.2f}%")
    svs = [g["stock_value_median"] for g in dense_grid]
    print(f"stock_value_median range across grid: THB {min(svs):,.2f} - THB {max(svs):,.2f}")


if __name__ == "__main__":
    main()
