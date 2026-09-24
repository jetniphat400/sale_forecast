"""Phase 23, Part 3: Modeler -- PEM101 Min/Max on the 80 distinct ensemble members (Part 1), and
the METRICS.md Sec.22 trade-off curve built strictly from config.yaml's locked `trade_off_curve`
block (Part 2). No new database access -- reuses output/data/phaseI_raw_sales_351items.csv and the
existing calibration engine.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, load_scope
import phaseJ3_calibration_engine as jc
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase23_modeler")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DAYS_PER_MONTH = 30.44
FOCUS_CODES = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

# Today's operating point -- J3 reconciled targets, cited (Verify, never recall):
# output/summary/phaseJ3_report.md line 21 (PEM101 valid not_late 98.28%), and
# output/summary/phaseJ3_validator_stock_value_summary.csv (PEM101 current_stock_value_thb
# 18,247,625.22, precise figure -- the report's "THB 18.25M" is this same figure rounded).
TODAY_NOT_LATE_PCT = 98.28
TODAY_STOCK_VALUE_THB = 18247625.22


def main():
    config = load_config()
    members = pd.read_csv(os.path.join(SUMMARY_DIR, "phase23_ensemble_distinct_members_PEM101.csv"))
    assert len(members) == 80, f"expected 80 distinct members (Part 1), got {len(members)}"
    logger.info("Loaded %d distinct ensemble members.", len(members))

    tc = config["trade_off_curve"]
    grid = tc["reorder_level_grid_r_months"]
    window = tc["simulation_window"]
    warmup = tc["warm_up"]
    weighting = tc["not_late_weighting"]
    assert weighting == "unit_weighted", f"unexpected not_late_weighting: {weighting}"
    logger.info("Locked config: grid=%d points, window=%s..%s, warm_up=%s..%s, weighting=%s",
                len(grid), window["start"], window["end"], warmup["start"], warmup["end"], weighting)

    scope = load_scope(config)
    elig = scope[scope["eligible_for_policy"]]
    codes = sorted(elig["code"].unique())
    logger.info("PEM101 eligible-for-policy scope: %d items.", len(codes))

    raw = pd.read_csv(os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv"))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw_div = raw[raw["itemcode"].isin(codes)].copy()

    daily_bundle = jc.build_full_daily_series(raw_div, codes, warmup["start"], window["end"])
    daily_series = daily_bundle["series"]
    day_index = daily_bundle["day_index"]
    mean_demand = {c: float(daily_series[c].mean()) for c in codes}
    n_zero = sum(1 for c in codes if mean_demand[c] <= 0)
    logger.info("Items with mean_daily_demand<=0 over the warm-up+scoring window: %d of %d",
                n_zero, len(codes))

    unit_cost_df = eng.compute_unit_cost_from_raw(raw_div, codes, 12).set_index("itemcode")
    unit_cost = unit_cost_df["unit_cost"]

    scoring_mask = jc.window_mask(day_index, window["start"], window["end"])
    logger.info("Scoring window covers %d of %d simulated days.", scoring_mask.sum(), len(day_index))

    # ================= Part A: per-item Min/Max across the 80 distinct members =================
    min_rows = []
    for mi, m in members.iterrows():
        for c in codes:
            md = mean_demand[c]
            min_e = m["r_months"] * DAYS_PER_MONTH * md
            max_e = m["s_months"] * DAYS_PER_MONTH * md
            min_rows.append({
                "itemcode": c, "member_idx": mi,
                "r_months": m["r_months"], "s_months": m["s_months"],
                "review_interval_days": m["review_interval_days"], "lead_time_days": m["lead_time_days"],
                "Min_e": min_e, "Max_e": max_e,
            })
    minmax_df = pd.DataFrame(min_rows)
    minmax_df.to_csv(os.path.join(SUMMARY_DIR, "phase23_modeler_per_item_minmax.csv"), index=False)
    logger.info("Per-item Min/Max rows: %d (%d items x %d members)", len(minmax_df), len(codes), len(members))

    summary_rows = []
    for c in codes:
        sub = minmax_df[minmax_df["itemcode"] == c]
        summary_rows.append({
            "itemcode": c,
            "median_Min": sub["Min_e"].median(), "min_Min": sub["Min_e"].min(), "max_Min": sub["Min_e"].max(),
            "median_Max": sub["Max_e"].median(), "min_Max": sub["Max_e"].min(), "max_Max": sub["Max_e"].max(),
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(os.path.join(SUMMARY_DIR, "phase23_modeler_minmax_summary.csv"), index=False)

    print("\n=== FOCUS CODES (Part A: Min/Max across 80 distinct members) ===")
    for fc in FOCUS_CODES:
        r = summary_df[summary_df["itemcode"] == fc]
        print(r.to_string(index=False) if len(r) else f"{fc}: NOT FOUND in eligible scope")

    # ================= Part B: trade-off curve, strictly from the locked config block =================
    import time
    t0 = time.time()
    rows = []
    for mi, m in members.iterrows():
        gap = m["s_months"] - m["r_months"]
        review = int(m["review_interval_days"])
        lead = int(m["lead_time_days"])
        for r_new in grid:
            s_new = r_new + gap
            if s_new <= r_new:
                continue
            demand_sum = shipped_sum = 0.0
            stockval_days = None
            for c in codes:
                qty = daily_series[c]
                mean_d = qty.mean()
                if mean_d <= 0:
                    continue
                sim = jc.simulate_months_of_demand(
                    qty, r_new, s_new, review, lead,
                    initial_stock=s_new * DAYS_PER_MONTH * mean_d, mean_daily_demand=mean_d)
                demand_sum += sim["daily_demand"][scoring_mask].sum()
                shipped_sum += sim["daily_shipped"][scoring_mask].sum()
                uc = unit_cost.get(c, np.nan)
                if pd.notna(uc):
                    v = sim["daily_on_hand"][scoring_mask] * uc
                    stockval_days = v if stockval_days is None else stockval_days + v
            not_late = shipped_sum / demand_sum if demand_sum > 0 else np.nan
            stock_value = float(stockval_days.mean()) if stockval_days is not None else np.nan
            rows.append({
                "member_idx": mi, "review_interval_days": review, "lead_time_days": lead,
                "orig_r_months": m["r_months"], "orig_s_months": m["s_months"],
                "swept_r_months": r_new, "swept_s_months": s_new,
                "not_late": not_late, "stock_value": stock_value,
            })
        logger.info("  member %d/%d done, %.1fs elapsed", mi + 1, len(members), time.time() - t0)

    curve = pd.DataFrame(rows)
    curve.to_csv(os.path.join(SUMMARY_DIR, "phase23_modeler_tradeoff_curve_points.csv"), index=False)
    logger.info("Curve points computed: %d (in %.1fs)", len(curve), time.time() - t0)

    curve_valid = curve.dropna(subset=["not_late", "stock_value"]).copy()
    curve_valid["not_late_bin_pct"] = (curve_valid["not_late"] * 100).round(0)
    envelope = curve_valid.groupby("not_late_bin_pct")["stock_value"].agg(
        ["min", "median", "max", "count"]).reset_index()
    envelope.to_csv(os.path.join(SUMMARY_DIR, "phase23_modeler_tradeoff_envelope.csv"), index=False)
    print("\nEnvelope (not_late % bin -> stock_value min/median/max, THB):")
    print(envelope.to_string(index=False))

    # ================= Part C: today's point vs. the median curve =================
    print(f"\n=== TODAY'S POINT (J3 reconciled targets) ===")
    print(f"not_late = {TODAY_NOT_LATE_PCT}% (output/summary/phaseJ3_report.md, PEM101 valid not_late)")
    print(f"stock_value = THB {TODAY_STOCK_VALUE_THB:,.2f} "
          f"(output/summary/phaseJ3_validator_stock_value_summary.csv, PEM101 current_stock_value_thb)")

    today_bin = round(TODAY_NOT_LATE_PCT)
    row_at_today_bin = envelope[envelope["not_late_bin_pct"] == today_bin]
    if len(row_at_today_bin):
        med_sv = row_at_today_bin["median"].iloc[0]
        print(f"\nMedian curve's stock_value at not_late={today_bin}% bin: THB {med_sv:,.2f} "
              f"(today's actual: THB {TODAY_STOCK_VALUE_THB:,.2f}, "
              f"diff {TODAY_STOCK_VALUE_THB - med_sv:+,.2f}, "
              f"{100*(TODAY_STOCK_VALUE_THB - med_sv)/med_sv:+.2f}%)")
    else:
        print(f"\nNo envelope bin at not_late={today_bin}% -- nearest bins: "
              f"{sorted(envelope['not_late_bin_pct'].tolist())}")

    # interpolate the median curve (median stock_value vs not_late_bin_pct) to find the not_late
    # level where the median curve's stock_value equals today's actual stock_value
    env_sorted = envelope.sort_values("not_late_bin_pct")
    x = env_sorted["not_late_bin_pct"].values
    y = env_sorted["median"].values
    if TODAY_STOCK_VALUE_THB < y.min() or TODAY_STOCK_VALUE_THB > y.max():
        print(f"\nToday's stock_value (THB {TODAY_STOCK_VALUE_THB:,.2f}) is OUTSIDE the median "
              f"curve's own range (THB {y.min():,.2f} to THB {y.max():,.2f}) -- cannot interpolate "
              f"a not_late level from the median curve at this stock value.")
    else:
        # median stock_value should be monotonic non-decreasing in not_late for a sensible
        # interpolation -- use np.interp on the sorted-by-y series
        order = np.argsort(y)
        not_late_at_today_sv = float(np.interp(TODAY_STOCK_VALUE_THB, y[order], x[order]))
        print(f"\nMedian curve's not_late at today's stock_value (THB {TODAY_STOCK_VALUE_THB:,.2f}): "
              f"~{not_late_at_today_sv:.1f}% (today's actual: {TODAY_NOT_LATE_PCT}%, "
              f"diff {TODAY_NOT_LATE_PCT - not_late_at_today_sv:+.1f}pp)")

    print(f"\nElapsed: {time.time()-t0:.1f}s total")


if __name__ == "__main__":
    main()
