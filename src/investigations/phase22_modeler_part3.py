"""Phase 22 Modeler Part 3: trade-off curve (envelope across ensemble members)."""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_scope
import phaseJ3_calibration_engine as jc
import phaseI_sensitivity_engine as eng

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

R_GRID = [0.10, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 2.50, 3.00, 4.00]  # spans below/above the
# ensemble's own observed r_months range (0.25-2.0) to reveal the fuller curve, 10 points.

config = jc.load_config()
raw = pd.read_csv(os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv"))
raw["createDate"] = pd.to_datetime(raw["createDate"])
raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
scope = load_scope(config)
elig = scope[scope["eligible_for_policy"]]
codes = sorted(elig["code"].unique())
raw_div = raw[raw["itemcode"].isin(codes)].copy()

validation_end = jc.determine_validation_end(raw)
daily_bundle = jc.build_full_daily_series(raw_div, codes, jc.CALIBRATION_START, validation_end)
daily_series = daily_bundle["series"]
day_index = daily_bundle["day_index"]
unit_cost_df = eng.compute_unit_cost_from_raw(raw_div, codes, 12).set_index("itemcode")
unit_cost = unit_cost_df["unit_cost"]

calib_mask = jc.window_mask(day_index, jc.CALIBRATION_SCORE_START, jc.CALIBRATION_END)
valid_mask = jc.window_mask(day_index, jc.VALIDATION_START, str(day_index[-1].date()))
full_mask = calib_mask | valid_mask

dedup = pd.read_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_ensemble_dedup.csv"))
print(f"Ensemble members: {len(dedup)}, grid points per member: {len(R_GRID)}, items: {len(codes)}")
print(f"Estimated simulate calls: {len(dedup) * len(R_GRID) * len(codes)}")

t0 = time.time()
rows = []
for mi, m in dedup.iterrows():
    gap = m["s_months"] - m["r_months"]
    review = int(m["review_interval_days"])
    lead = int(m["lead_time_days"])
    for r_new in R_GRID:
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
                initial_stock=s_new * jc.DAYS_PER_MONTH * mean_d, mean_daily_demand=mean_d)
            demand_sum += sim["daily_demand"][full_mask].sum()
            shipped_sum += sim["daily_shipped"][full_mask].sum()
            uc = unit_cost.get(c, np.nan)
            if pd.notna(uc):
                v = sim["daily_on_hand"][full_mask] * uc
                stockval_days = v if stockval_days is None else stockval_days + v
        not_late = shipped_sum / demand_sum if demand_sum > 0 else np.nan
        stock_value = float(stockval_days.mean()) if stockval_days is not None else np.nan
        rows.append({
            "member_idx": mi, "stockdef": m["stockdef"], "review_interval_days": review,
            "lead_time_days": lead, "orig_r_months": m["r_months"], "orig_s_months": m["s_months"],
            "swept_r_months": r_new, "swept_s_months": s_new,
            "not_late": not_late, "stock_value": stock_value,
        })
    if True:
        print(f"  member {mi}/{len(dedup)} done, {time.time()-t0:.1f}s elapsed")

curve = pd.DataFrame(rows)
curve.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_tradeoff_curve_points.csv"), index=False)
print(f"\nDone in {time.time()-t0:.1f}s. {len(curve)} grid points computed.")

# --- envelope: bin not_late to nearest 1pp, report min/median/max stock_value per bin ---
curve = curve.dropna(subset=["not_late", "stock_value"])
curve["not_late_bin_pct"] = (curve["not_late"] * 100).round(0)
envelope = curve.groupby("not_late_bin_pct")["stock_value"].agg(["min", "median", "max", "count"]).reset_index()
envelope.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_tradeoff_envelope.csv"), index=False)
print("\nEnvelope (not_late % bin -> stock_value min/median/max, THB):")
print(envelope.to_string(index=False))
