"""Phase 22 Modeler Part 2: range_ratio, robust/sensitive split, focus codes, definition-alone effect."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
FOCUS_CODES = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
THRESHOLDS = [1.10, 1.25, 1.50]

minmax = pd.read_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_per_item_minmax.csv"))
dedup = pd.read_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_ensemble_dedup.csv"))
n_members = len(dedup)
print(f"Ensemble size: {n_members}")

items = sorted(minmax["itemcode"].unique())
rows = []
zero_items = []
for it in items:
    sub = minmax[minmax["itemcode"] == it]
    nonzero = sub[sub["Min_e"] > 0]
    if len(nonzero) == 0:
        zero_items.append(it)
        continue
    rr = nonzero["Min_e"].max() / nonzero["Min_e"].min()
    row = {
        "itemcode": it, "n_members_nonzero": len(nonzero), "n_members_total": len(sub),
        "range_ratio": rr,
        "min_Min": nonzero["Min_e"].min(), "max_Min": nonzero["Min_e"].max(),
        "median_Min": nonzero["Min_e"].median(), "median_Max": sub["Max_e"].median(),
        "min_Max": sub["Max_e"].min(), "max_Max": sub["Max_e"].max(),
    }
    for t in THRESHOLDS:
        row[f"robust_at_{t}"] = rr <= t
    rows.append(row)

result = pd.DataFrame(rows)
result.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_range_ratio.csv"), index=False)

print(f"\nItems with every Min_e == 0 (reported separately, no range_ratio): {len(zero_items)}")
print(zero_items)

print(f"\nItems with a computed range_ratio: {len(result)}")
for t in THRESHOLDS:
    n_robust = int(result[f"robust_at_{t}"].sum())
    n_sensitive = len(result) - n_robust
    print(f"  threshold {t}: robust={n_robust}, sensitive={n_sensitive}")

# --- driver analysis for sensitive items (threshold 1.25) ---
sensitive_125 = result[~result["robust_at_1.25"]]["itemcode"].tolist()
print(f"\nSensitive items at 1.25: {len(sensitive_125)}")

param_cols = ["r_months", "s_months", "review_interval_days", "lead_time_days", "stockdef"]


def driver_for_item(it):
    sub = minmax[minmax["itemcode"] == it]
    sub = sub[sub["Min_e"] > 0]
    base_range = sub["Min_e"].max() / sub["Min_e"].min()
    narrow = {}
    for p in param_cols:
        mode_val = sub[p].mode().iloc[0]
        fixed = sub[sub[p] == mode_val]
        if len(fixed) < 2:
            narrow[p] = None
            continue
        rr_fixed = fixed["Min_e"].max() / fixed["Min_e"].min()
        narrow[p] = base_range - rr_fixed  # how much range_ratio drops when this param is fixed
    valid = {k: v for k, v in narrow.items() if v is not None}
    if not valid:
        return None, narrow
    driver = max(valid, key=valid.get)
    return driver, narrow


driver_rows = []
for it in sensitive_125:
    driver, narrow = driver_for_item(it)
    driver_rows.append({"itemcode": it, "driver_param": driver, **{f"narrow_{k}": v for k, v in narrow.items()}})
driver_df = pd.DataFrame(driver_rows)
driver_df.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_sensitive_drivers.csv"), index=False)
print(driver_df["driver_param"].value_counts())

# --- usable-stock-definition-alone effect: current-only ensemble vs full deduped ensemble ---
current_only_members = minmax[minmax["stockdef"] == "current"]
rows2 = []
for it in items:
    sub_all = minmax[minmax["itemcode"] == it]
    sub_cur = current_only_members[current_only_members["itemcode"] == it]
    nz_all = sub_all[sub_all["Min_e"] > 0]
    nz_cur = sub_cur[sub_cur["Min_e"] > 0]
    if len(nz_all) == 0 or len(nz_cur) == 0:
        continue
    rr_all = nz_all["Min_e"].max() / nz_all["Min_e"].min()
    rr_cur = nz_cur["Min_e"].max() / nz_cur["Min_e"].min()
    rows2.append({"itemcode": it, "range_ratio_full_ensemble": rr_all,
                   "range_ratio_current_only": rr_cur, "diff": rr_all - rr_cur})
defcompare = pd.DataFrame(rows2)
defcompare.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_stockdef_effect.csv"), index=False)
print("\nUsable-stock-definition-alone effect (range_ratio full ensemble vs current-only):")
print(defcompare["diff"].describe())
n_affected = (defcompare["diff"].abs() > 0.01).sum()
print(f"Items where full-ensemble range_ratio differs from current-only by >0.01: {n_affected} of {len(defcompare)}")
print(defcompare[defcompare["diff"].abs() > 0.01].to_string(index=False))

# --- focus codes ---
print("\n=== FOCUS CODES ===")
for fc in FOCUS_CODES:
    r = result[result["itemcode"] == fc]
    if len(r) == 0:
        print(f"{fc}: in zero_items (every Min_e==0)" if fc in zero_items else f"{fc}: NOT FOUND in scope")
        continue
    print(r.to_string(index=False))
    dc = defcompare[defcompare["itemcode"] == fc]
    print(dc.to_string(index=False))
