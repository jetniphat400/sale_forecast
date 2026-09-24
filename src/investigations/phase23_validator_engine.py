"""Independent Validator recomputation for this task (Part 2/3 trade-off curve + focus-code Min).

Runs from scratch: distinct ensemble member count (METRICS.md Sec.22, amended 2026-09-24 dedup
rule -- 4 parameters only, usable-stock definition NOT part of Min/Max/range_ratio/trade-off-curve
identity), median Min for 3 focus codes, and the trade-off curve strictly from
config.yaml's locked `trade_off_curve` block.

No new database access -- reuses output/data/phaseI_raw_sales_351items.csv and the existing
phaseJ3_calibration_engine / phaseI_sensitivity_engine / phaseE1_common functions.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, load_scope
import phaseI_sensitivity_engine as eng
import phaseJ3_calibration_engine as calib

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
GRID_FILE = os.path.join(SUMMARY_DIR, "phaseJ3_2_grid_PEM101.csv")
FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
DEFS = ["current", "fg_prefixed_only", "all_stockholding_except_qa_fmto_fmts"]


def step1_distinct_members():
    grid = pd.read_csv(GRID_FILE)
    print(f"[step1] grid rows: {len(grid)}")

    passing_masks = {}
    for d in DEFS:
        mask = (
            (grid["calib_notlate_diff_pp"] <= 3)
            & (grid["valid_notlate_diff_pp"] <= 3)
            & (grid[f"calib_stockval_pctdiff_{d}"] <= 15)
            & (grid[f"valid_stockval_pctdiff_{d}"] <= 15)
        )
        passing_masks[d] = mask
        print(f"[step1] def={d}: {int(mask.sum())} rows pass both-window tolerance")

    union_mask = passing_masks[DEFS[0]] | passing_masks[DEFS[1]] | passing_masks[DEFS[2]]
    union_rows = grid.loc[union_mask, ["r_months", "s_months", "review_interval_days", "lead_time_days"]]
    distinct = union_rows.drop_duplicates().reset_index(drop=True)
    print(f"[step1] union rows: {int(union_mask.sum())}; DISTINCT (r,s,review,lead) tuples: {len(distinct)}")

    # per-definition passing counts among the union, for the report
    detail = grid.loc[union_mask].copy()
    for d in DEFS:
        detail[f"passes_{d}"] = passing_masks[d].loc[union_mask]
    detail.to_csv(os.path.join(SUMMARY_DIR, "phase23_validator_union_passing_rows.csv"), index=False)
    distinct.to_csv(os.path.join(SUMMARY_DIR, "phase23_validator_distinct_members.csv"), index=False)
    return distinct


def build_bundle(config):
    raw, inv = calib.load_raw()
    validation_end = calib.determine_validation_end(raw)
    print(f"[bundle] validation_end (re-derived) = {validation_end}")
    bundle = calib.build_division_bundle(config, "PEM101", raw, inv, validation_end)
    print(f"[bundle] n codes in scope: {len(bundle['codes'])}")
    return bundle, validation_end


def step2_median_min(distinct_members: pd.DataFrame, bundle: dict):
    """Min_e = r_months * 30.44 * mean_daily_demand(item), mean over the FULL warm-up+scoring
    window (config trade_off_curve.warm_up.start .. simulation_window.end), per item's own daily
    series from build_full_daily_series -- already what `bundle['daily_series']` holds, since
    build_division_bundle was called with day_min=CALIBRATION_START(2024-01-01)==warm_up.start and
    day_max=validation_end. We verify below that validation_end == simulation_window.end from
    config before using it, since the config block is authoritative here."""
    rows = []
    for code in FOCUS_ITEMS:
        qty = bundle["daily_series"][code]
        mean_d = float(qty.mean())
        for _, m in distinct_members.iterrows():
            min_e = m["r_months"] * calib.DAYS_PER_MONTH * mean_d
            rows.append({"code": code, "r_months": m["r_months"], "s_months": m["s_months"],
                         "review_interval_days": m["review_interval_days"],
                         "lead_time_days": m["lead_time_days"], "mean_daily_demand": mean_d,
                         "Min_e": min_e})
    df = pd.DataFrame(rows)
    medians = df.groupby("code")["Min_e"].median()
    df.to_csv(os.path.join(SUMMARY_DIR, "phase23_validator_focus_min_detail.csv"), index=False)
    return df, medians


def step3_trade_off_curve(distinct_members: pd.DataFrame, bundle: dict, config: dict):
    toc = config["trade_off_curve"]
    grid_r = toc["reorder_level_grid_r_months"]
    win_start, win_end = toc["simulation_window"]["start"], toc["simulation_window"]["end"]
    print(f"[step3] scoring window: {win_start} .. {win_end}; grid points: {len(grid_r)}")

    day_index = bundle["day_index"]
    score_mask = calib.window_mask(day_index, win_start, win_end)
    unit_cost = bundle["unit_cost_df"]["unit_cost"]

    curve_rows = []
    n_members = len(distinct_members)
    for mi, m in enumerate(distinct_members.itertuples(index=False)):
        gap = m.s_months - m.r_months
        review = int(m.review_interval_days)
        lead = int(m.lead_time_days)
        for r_new in grid_r:
            s_new = r_new + gap
            demand_total = shipped_total = 0.0
            stockval_days = None
            for code in bundle["codes"]:
                qty = bundle["daily_series"][code]
                mean_d = qty.mean()
                if mean_d <= 0:
                    continue
                uc = unit_cost.get(code, np.nan)
                sim = calib.simulate_months_of_demand(
                    qty, r_new, s_new, review, lead,
                    initial_stock=s_new * calib.DAYS_PER_MONTH * mean_d, mean_daily_demand=mean_d)
                demand_total += sim["daily_demand"][score_mask].sum()
                shipped_total += sim["daily_shipped"][score_mask].sum()
                if pd.notna(uc):
                    item_val = sim["daily_on_hand"][score_mask] * uc
                    stockval_days = item_val if stockval_days is None else stockval_days + item_val
            not_late = shipped_total / demand_total if demand_total > 0 else np.nan
            stock_value = float(stockval_days.mean()) if stockval_days is not None else np.nan
            curve_rows.append({
                "member_r_months": m.r_months, "member_s_months": m.s_months,
                "review_interval_days": review, "lead_time_days": lead,
                "gap_months": gap, "r_new": r_new, "s_new": s_new,
                "not_late": not_late, "stock_value": stock_value,
            })
        if (mi + 1) % 10 == 0 or (mi + 1) == n_members:
            print(f"[step3] member {mi + 1}/{n_members} done")

    curve = pd.DataFrame(curve_rows)
    curve.to_csv(os.path.join(SUMMARY_DIR, "phase23_validator_curve_points.csv"), index=False)

    valid = curve.dropna(subset=["not_late", "stock_value"]).copy()
    valid["not_late_pct"] = valid["not_late"] * 100.0
    valid["bin_pp"] = valid["not_late_pct"].round(0).astype(int)
    envelope = valid.groupby("bin_pp")["stock_value"].agg(["min", "median", "max", "count"]).reset_index()
    envelope = envelope.rename(columns={"min": "stock_value_min", "median": "stock_value_median",
                                         "max": "stock_value_max", "count": "n_points"})
    envelope = envelope.sort_values("bin_pp")
    envelope.to_csv(os.path.join(SUMMARY_DIR, "phase23_validator_envelope.csv"), index=False)
    return curve, envelope


def main():
    config = load_config()
    distinct = step1_distinct_members()
    bundle, validation_end = build_bundle(config)

    toc = config["trade_off_curve"]
    cfg_win_end = toc["simulation_window"]["end"]
    cfg_warmup_start = toc["warm_up"]["start"]
    print(f"[check] config simulation_window.end={cfg_win_end} vs re-derived validation_end={validation_end}")
    print(f"[check] config warm_up.start={cfg_warmup_start} vs bundle day_index[0]={bundle['day_index'][0]}")

    min_detail, medians = step2_median_min(distinct, bundle)
    print("[step2] median Min per focus code:")
    for code in FOCUS_ITEMS:
        print(f"  {code}: {medians.get(code)}")

    curve, envelope = step3_trade_off_curve(distinct, bundle, config)
    print("[step3] envelope (bin_pp -> median stock_value):")
    print(envelope.to_string(index=False))

    return {"distinct": distinct, "medians": medians, "envelope": envelope, "min_detail": min_detail,
            "curve": curve, "validation_end": validation_end}


if __name__ == "__main__":
    main()
