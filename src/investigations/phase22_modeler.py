"""METRICS.md Sec.22 (robust_minmax) -- Modeler, PEM101. Parts 1-3.

No new database access -- reuses output/data/phaseI_raw_sales_351items.csv,
phaseI_inventory_exact_351items.csv, and the existing per-combination grid
output/summary/phaseJ3_2_grid_PEM101.csv (already has all 3 stock-definition diagnostics per
grid point -- filtering it is not "regenerating a simulation", it IS the saved per-combination
passing list, just not pre-filtered to a single list).
"""
import itertools
import json
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
logger = logging.getLogger("phase22_modeler")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
GRID_FILE = os.path.join(SUMMARY_DIR, "phaseJ3_2_grid_PEM101.csv")

NOT_LATE_TOL_PP = 3.0
STOCK_VALUE_TOL_PCT = 15.0
DAYS_PER_MONTH = 30.44
FOCUS_CODES = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
RATIO_THRESHOLDS = [1.10, 1.25, 1.50]

STOCKDEFS = ["current", "fg_prefixed_only", "all_stockholding_except_qa_fmto_fmts"]


def part1_resolve_warehouse_sets(config, raw, inv):
    """Resolve each definition's warehouse-code set, both the NOMINAL list passed to
    sellable_stock_per_item and the EFFECTIVE subset that actually holds nonzero PEM101 stock
    (the latter is what matters for "resolve to the same set for PEM101's items")."""
    scope = load_scope(config)
    elig = scope[scope["eligible_for_policy"]]
    codes = sorted(elig["code"].unique())
    inv_div = inv[inv["itemcode"].isin(codes)].copy()
    all_wh_codes = sorted(inv["warehouse"].unique().tolist())  # global, matches calibration engine

    e1 = config["phase_e1_assumptions"]
    nominal = {
        "current": list(e1["sellable_warehouse_codes"]["PEM101"]),
        "fg_prefixed_only": eng.fg_prefixed_warehouses(all_wh_codes),
        "all_stockholding_except_qa_fmto_fmts": eng.current_stockholding_warehouses(inv_div),
    }
    effective = {}
    for name, wh_list in nominal.items():
        sub = inv_div[inv_div["warehouse"].isin(wh_list) & (inv_div["stock"] > 0)]
        effective[name] = sorted(sub["warehouse"].unique().tolist())

    logger.info("Nominal warehouse lists: %s", nominal)
    logger.info("Effective (nonzero-PEM101-stock) warehouse sets: %s", effective)
    return codes, nominal, effective


def part1_passing_sets(grid):
    passing = {}
    for d in STOCKDEFS:
        mask = (
            (grid["calib_notlate_diff_pp"] <= NOT_LATE_TOL_PP)
            & (grid["valid_notlate_diff_pp"] <= NOT_LATE_TOL_PP)
            & (grid[f"calib_stockval_pctdiff_{d}"] <= STOCK_VALUE_TOL_PCT)
            & (grid[f"valid_stockval_pctdiff_{d}"] <= STOCK_VALUE_TOL_PCT)
        )
        sub = grid[mask][["r_months", "s_months", "review_interval_days", "lead_time_days"]].copy()
        passing[d] = sub
        logger.info("[%s] %d/%d combinations pass both-window tolerance.", d, len(sub), len(grid))
    return passing


def dedup_ensemble(passing, effective_sets):
    """A member's identity key = (r,s,review,lead, frozenset(effective warehouse codes)).
    If two stock-definitions resolve to the same effective set, their passing combos collapse."""
    rows = []
    for d, df in passing.items():
        key_set = frozenset(effective_sets[d])
        for _, r in df.iterrows():
            rows.append({
                "stockdef": d, "r_months": r["r_months"], "s_months": r["s_months"],
                "review_interval_days": int(r["review_interval_days"]),
                "lead_time_days": int(r["lead_time_days"]),
                "wh_set": key_set,
            })
    all_members = pd.DataFrame(rows)
    all_members["member_key"] = all_members.apply(
        lambda r: (r["r_months"], r["s_months"], r["review_interval_days"], r["lead_time_days"], r["wh_set"]),
        axis=1)
    dedup = all_members.drop_duplicates(subset=["member_key"]).reset_index(drop=True)
    return all_members, dedup


def main():
    config = load_config()
    raw = pd.read_csv(os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv"))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    inv = pd.read_csv(os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv"))
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()

    codes, nominal, effective = part1_resolve_warehouse_sets(config, raw, inv)
    logger.info("PEM101 eligible-for-policy scope: %d codes.", len(codes))

    same_as_current = {d: (set(effective[d]) == set(effective["current"])) for d in STOCKDEFS}
    logger.info("Effective set == 'current'?: %s", same_as_current)

    grid = pd.read_csv(GRID_FILE)
    assert len(grid) == 4130, f"expected 4130 grid rows, got {len(grid)}"
    passing = part1_passing_sets(grid)
    for d in STOCKDEFS:
        print(f"PASSING [{d}]: n={len(passing[d])}")

    # cross-check against the existing summary JSON
    with open(os.path.join(SUMMARY_DIR, "phaseJ3_2_calibration_summary.json")) as f:
        summary_json = json.load(f)
    json_n = {r["stock_definition"]: r["n_passing"] for r in summary_json if r["division"] == "PEM101"}
    for d in STOCKDEFS:
        match = len(passing[d]) == json_n[d]
        print(f"  cross-check vs phaseJ3_2_calibration_summary.json: json n_passing={json_n[d]} -> "
              f"{'MATCH' if match else 'MISMATCH'}")

    all_members, dedup = dedup_ensemble(passing, effective)
    print(f"\nRaw members across 3 definitions (with duplication): {len(all_members)}")
    print(f"Deduplicated ensemble size: {len(dedup)}")
    overlap_report = all_members.groupby("stockdef").size().to_dict()
    print("Per-definition raw counts:", overlap_report)
    # which definitions collapsed together
    for d1, d2 in itertools.combinations(STOCKDEFS, 2):
        same = effective[d1] == effective[d2]
        print(f"  effective set equal? {d1} vs {d2}: {same} "
              f"({effective[d1]!r} vs {effective[d2]!r})")

    dedup.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_ensemble_dedup.csv"), index=False)
    all_members.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_ensemble_raw_members.csv"), index=False)

    validation_end = jc.determine_validation_end(raw)
    print(f"\nvalidation_end = {validation_end}")

    raw_div = raw[raw["itemcode"].isin(codes)].copy()
    daily_bundle = jc.build_full_daily_series(raw_div, codes, jc.CALIBRATION_START, validation_end)
    daily_series = daily_bundle["series"]
    day_index = daily_bundle["day_index"]

    mean_demand = {c: float(daily_series[c].mean()) for c in codes}
    n_zero_demand = sum(1 for c in codes if mean_demand[c] <= 0)
    print(f"Items with mean_daily_demand<=0 over the simulation window: {n_zero_demand} of {len(codes)}")

    # --- Part 2: per-item Min/Max across the deduplicated ensemble ---
    min_rows = []
    for _, m in dedup.iterrows():
        for c in codes:
            md = mean_demand[c]
            min_e = m["r_months"] * DAYS_PER_MONTH * md
            max_e = m["s_months"] * DAYS_PER_MONTH * md
            min_rows.append({
                "itemcode": c, "member_idx": _, "stockdef": m["stockdef"],
                "r_months": m["r_months"], "s_months": m["s_months"],
                "review_interval_days": m["review_interval_days"], "lead_time_days": m["lead_time_days"],
                "Min_e": min_e, "Max_e": max_e,
            })
    minmax_df = pd.DataFrame(min_rows)
    minmax_df.to_csv(os.path.join(SUMMARY_DIR, "phase22_modeler_per_item_minmax.csv"), index=False)
    print(f"\nPer-item Min/Max rows: {len(minmax_df)} ({len(codes)} items x {len(dedup)} members)")

    print("\n=== Script part 1/2 core computation done -- see phase22_modeler_part2.py for the "
          "range_ratio/robust-sensitive/focus-code analysis, and phase22_modeler_part3.py for "
          "the trade-off curve. ===")


if __name__ == "__main__":
    main()
