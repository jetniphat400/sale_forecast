"""Week 1, item 1.4: METRICS.md Sec.20 inverse calibration of PEM101 on the 92 stock_policy items, each item's replenishment lead time fixed at
its lead_time_v1 value (src/lead_time_v1.py) instead of one fitted or assumed lead time, ForecastDelDate as the due date.

Method otherwise as phaseJ3_run_calibration.py / phaseJ3_calibration_engine.py (imported, not copied): the same simulation, the same
grid for review interval and for reorder and order-up-to levels (months of mean demand), the same windows (warm-up 2024-01 to 2024-06, calibration
scoring 2024-07 to 2025-12, validation 2026-01 to the last complete month), the same tolerance (not_late +-3 points, stock value +-15%, both
windows) and the three usable-stock definitions. Differences, all stated in docs/reports/summary/week1_leadtime_calibration.md:
the item set (92, not the 128-item pilot scope), the data (the 2026-10-05 monthly pull, validation to 2026-09-30), the lead time (per item, not a grid
dimension), unit cost (the frozen phase I cache, 77 of the 92 items have one).

A CONTROL run repeats the old method (lead time as a grid dimension 1..90 days) on the same 92 items and data, so the effect of the per-item
lead time can be read apart from the effect of the item set and the data.

Nothing here writes to a page, a builder or a job. Outputs (output/summary/week1_recal_*, integrity hashes in week1_recal_integrity.json) sit beside
the current calibration's files and are not read by anything else.
"""
import hashlib
import itertools
import json
import logging
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import phaseJ3_calibration_engine as jc
import phaseI_sensitivity_engine as eng
import phaseJ3_run_calibration as rc
from phaseE1_common import PROJECT_ROOT, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("week1_recalibration")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
INPUT_DIR = os.path.join(DATA_DIR, "lead_time_inputs")
RAW_PATH = os.path.join(DATA_DIR, "raw_all_divisions_sales.csv")
LEAD_PATH = os.path.join(SUMMARY_DIR, "item_lead_time_v1.csv")
CES_PATH = os.path.join(INPUT_DIR, "ces_92.csv")
INV_PATH = os.path.join(INPUT_DIR, "inventory_92.csv")
INTEGRITY_PATH = os.path.join(SUMMARY_DIR, "week1_recal_integrity.json")
STOCKDEFS = ["current", "fg_prefixed_only", "all_stockholding_except_qa_fmto_fmts"]
DEDUP_COLS = ["r_months", "s_months", "review_interval_days"]


# ------------------------------------------------------------------ observed targets
def observed_not_late(ces: pd.DataFrame, items, start: str, end: str = None) -> dict:
    """Unit-weighted not_late (METRICS.md Sec.19): sum of ActualQty delivered on or before ForecastDelDate / sum of ActualQty, over Status
    'Actual' rows whose ForecastDelDate is in [start, end] and that have an ActualDelDate. ForecastDelDate is the due date."""
    c = ces[ces["ItemCode"].astype(str).str.strip().isin(set(items)) & (ces["Status"].astype(str).str.strip() == "Actual")].copy()
    for col in ("ForecastDelDate", "ActualDelDate"):
        c[col] = pd.to_datetime(c[col], errors="coerce")
    c = c[c["ForecastDelDate"].notna() & (c["ForecastDelDate"] >= start)]
    if end:
        c = c[c["ForecastDelDate"] <= end]
    n_excl = int(c["ActualDelDate"].isna().sum())
    c = c[c["ActualDelDate"].notna()]
    w = c["ActualQty"].astype(float)
    ontime = c["ActualDelDate"] <= c["ForecastDelDate"]
    return {"not_late": float(w[ontime].sum() / w.sum()) if w.sum() > 0 else float("nan"), "units": float(w.sum()), "rows": int(len(c)), "excluded_no_actual_date": n_excl}


def stock_value_targets(inv: pd.DataFrame, codes: list, unit_cost: pd.Series, all_wh: list, current_wh: list) -> dict:
    out = {}
    variants = {"current": current_wh, "fg_prefixed_only": eng.fg_prefixed_warehouses(all_wh),
                "all_stockholding_except_qa_fmto_fmts": eng.current_stockholding_warehouses(inv)}
    for name, wh in variants.items():
        s = eng.sellable_stock_per_item(inv, codes, wh).set_index("itemcode")["sellable_stock"]
        out[name] = float((s * unit_cost.reindex(s.index).fillna(0)).sum())
    return out, {k: sorted(v) for k, v in variants.items()}


# ------------------------------------------------------------------ simulation with a per-item lead time
def point(bundle: dict, lead_by_item: dict, r: float, s: float, review: int, lead_fixed: int = None) -> dict:
    """One grid point; the per-item lead time (days, rounded) unless `lead_fixed` is given (the control run)."""
    day_index = bundle["day_index"]
    calib_mask = jc.window_mask(day_index, jc.CALIBRATION_SCORE_START, jc.CALIBRATION_END)
    valid_mask = jc.window_mask(day_index, jc.VALIDATION_START, day_index[-1].strftime("%Y-%m-%d"))
    uc = bundle["unit_cost_df"]["unit_cost"]
    cd = cs = vd = vs = 0.0
    csv_ = vsv = None
    n = 0
    for code in bundle["codes"]:
        qty = bundle["daily_series"][code]
        md = qty.mean()
        if md <= 0:
            continue
        lead = int(lead_fixed if lead_fixed is not None else round(lead_by_item[code]))
        sim = jc.simulate_months_of_demand(qty, r, s, review, lead, initial_stock=s * jc.DAYS_PER_MONTH * md, mean_daily_demand=md)
        n += 1
        cd += sim["daily_demand"][calib_mask].sum(); cs += sim["daily_shipped"][calib_mask].sum()
        vd += sim["daily_demand"][valid_mask].sum(); vs += sim["daily_shipped"][valid_mask].sum()
        u = uc.get(code, np.nan)
        if pd.notna(u):
            a, b = sim["daily_on_hand"][calib_mask] * u, sim["daily_on_hand"][valid_mask] * u
            csv_ = a if csv_ is None else csv_ + a
            vsv = b if vsv is None else vsv + b
    return {"r_months": r, "s_months": s, "review_interval_days": review, "lead_time_days": lead_fixed if lead_fixed is not None else "per_item",
            "calib_not_late": cs / cd if cd > 0 else np.nan, "valid_not_late": vs / vd if vd > 0 else np.nan,
            "calib_stock_value": float(csv_.mean()) if csv_ is not None else np.nan, "valid_stock_value": float(vsv.mean()) if vsv is not None else np.nan,
            "n_items_simulated": n}


def score(df: pd.DataFrame, nl_calib: float, nl_valid: float, sv_targets: dict) -> pd.DataFrame:
    df = df.copy()
    for name, t in sv_targets.items():
        df[f"calib_stockval_pctdiff_{name}"] = 100 * (df["calib_stock_value"] - t).abs() / t
        df[f"valid_stockval_pctdiff_{name}"] = 100 * (df["valid_stock_value"] - t).abs() / t
    df["calib_notlate_diff_pp"] = 100 * (df["calib_not_late"] - nl_calib).abs()
    df["valid_notlate_diff_pp"] = 100 * (df["valid_not_late"] - nl_valid).abs()
    return df


def passing(df: pd.DataFrame, stockdef: str) -> pd.DataFrame:
    return df[(df["calib_notlate_diff_pp"] <= rc.NOT_LATE_TOL_PP) & (df["valid_notlate_diff_pp"] <= rc.NOT_LATE_TOL_PP)
              & (df[f"calib_stockval_pctdiff_{stockdef}"] <= rc.STOCK_VALUE_TOL_PCT) & (df[f"valid_stockval_pctdiff_{stockdef}"] <= rc.STOCK_VALUE_TOL_PCT)]


def distinct_members(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Passing members over the three stock definitions, de-duplicated on the parameters that affect Min (METRICS.md Sec.22)."""
    parts = [passing(df, d) for d in STOCKDEFS]
    allp = pd.concat(parts, ignore_index=True) if parts else df.iloc[0:0]
    return allp.drop_duplicates(cols).reset_index(drop=True), [len(p) for p in parts]


# ------------------------------------------------------------------ trade-off curve (config trade_off_curve grid, members' own gap held)
def tradeoff(bundle: dict, members: pd.DataFrame, lead_by_item: dict, grid: list, window: tuple, per_item_lead: bool) -> pd.DataFrame:
    day_index = bundle["day_index"]
    mask = jc.window_mask(day_index, window[0], window[1])
    uc = bundle["unit_cost_df"]["unit_cost"]
    rows = []
    for mi, m in members.iterrows():
        gap = m["s_months"] - m["r_months"]
        for r_new in grid:
            s_new = r_new + gap
            dem = shp = 0.0
            sv = None
            for code in bundle["codes"]:
                qty = bundle["daily_series"][code]
                md = qty.mean()
                if md <= 0:
                    continue
                lead = int(round(lead_by_item[code])) if per_item_lead else int(m["lead_time_days"])
                sim = jc.simulate_months_of_demand(qty, r_new, s_new, int(m["review_interval_days"]), lead, initial_stock=s_new * jc.DAYS_PER_MONTH * md, mean_daily_demand=md)
                dem += sim["daily_demand"][mask].sum(); shp += sim["daily_shipped"][mask].sum()
                u = uc.get(code, np.nan)
                if pd.notna(u):
                    v = sim["daily_on_hand"][mask] * u
                    sv = v if sv is None else sv + v
            rows.append({"member_idx": mi, "review_interval_days": int(m["review_interval_days"]), "orig_r_months": m["r_months"], "orig_s_months": m["s_months"],
                         "swept_r_months": r_new, "swept_s_months": s_new, "not_late": shp / dem if dem > 0 else np.nan,
                         "stock_value": float(sv.mean()) if sv is not None else np.nan})
    return pd.DataFrame(rows)


def envelope(curve: pd.DataFrame) -> pd.DataFrame:
    c = curve.dropna(subset=["not_late", "stock_value"]).copy()
    c["not_late_bin_pct"] = (c["not_late"] * 100).round(0)
    return c.groupby("not_late_bin_pct")["stock_value"].agg(["min", "median", "max", "count"]).reset_index()


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def record(paths: list) -> dict:
    meta = {"recorded_at": datetime.now().isoformat(timespec="seconds"), "files": {os.path.basename(p): {"sha256": sha256_file(p)} for p in paths}}
    with open(INTEGRITY_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return meta


def verify_recorded() -> bool:
    with open(INTEGRITY_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    for name, info in meta["files"].items():
        if sha256_file(os.path.join(SUMMARY_DIR, name)) != info["sha256"]:
            raise ValueError(f"{name} does not hash to the recorded value")
    return True


def main(run_control: bool = True):
    config = load_config()
    items = json.load(open(os.path.join(INPUT_DIR, "stock92.json"), encoding="utf-8"))
    lead = pd.read_csv(LEAD_PATH).set_index("item")["lead_time_days"].to_dict()
    raw = pd.read_csv(RAW_PATH)
    raw["createDate"] = pd.to_datetime(raw["createDate"]); raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw = raw[raw["itemcode"].isin(items)]
    validation_end = jc.determine_validation_end(raw)
    logger.info("92 items, %d raw rows, validation_end %s", len(raw), validation_end)
    daily = jc.build_full_daily_series(raw, sorted(items), jc.CALIBRATION_START, validation_end)
    cost_raw = pd.read_csv(os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")); cost_raw["createDate"] = pd.to_datetime(cost_raw["createDate"])
    unit_cost = eng.compute_unit_cost_from_raw(cost_raw[cost_raw["itemcode"].isin(items)], sorted(items), 12).set_index("itemcode")
    bundle = {"codes": sorted(items), "daily_series": daily["series"], "day_index": daily["day_index"], "unit_cost_df": unit_cost}
    ces = pd.read_csv(CES_PATH)
    nl_c = observed_not_late(ces, items, jc.CALIBRATION_START, jc.CALIBRATION_END)
    nl_v = observed_not_late(ces, items, jc.VALIDATION_START, validation_end)
    inv = pd.read_csv(INV_PATH); inv["warehouse"] = inv["warehouse"].astype(str).str.strip(); inv["itemcode"] = inv["itemcode"].astype(str).str.strip()
    all_wh = sorted(pd.read_csv(os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv"))["warehouse"].astype(str).str.strip().unique().tolist())
    sv, wh_sets = stock_value_targets(inv, sorted(items), unit_cost["unit_cost"], all_wh, config["phase_e1_assumptions"]["sellable_warehouse_codes"]["PEM101"])
    targets = {"not_late_calibration": nl_c, "not_late_validation": nl_v, "stock_value_current_by_definition": sv, "warehouse_sets": wh_sets,
               "validation_end": validation_end, "n_items": len(items), "n_items_with_unit_cost": int(unit_cost["unit_cost"].notna().sum())}
    logger.info("targets %s", targets)

    pairs = rc.rs_pairs()
    t0 = time.time()
    rows = [point(bundle, lead, r, s, review) for review, (r, s) in itertools.product(rc.REVIEW_INTERVAL_GRID, pairs)]
    grid = score(pd.DataFrame(rows), nl_c["not_late"], nl_v["not_late"], sv)
    logger.info("per-item-lead grid: %d points in %.0fs", len(grid), time.time() - t0)
    grid_path = os.path.join(SUMMARY_DIR, "week1_recal_grid_PEM101_92.csv"); grid.to_csv(grid_path, index=False)
    members, counts = distinct_members(grid, DEDUP_COLS)
    members_path = os.path.join(SUMMARY_DIR, "week1_recal_members_PEM101_92.csv"); members.to_csv(members_path, index=False)
    paths = [grid_path, members_path]

    control_members = None
    if run_control:
        t0 = time.time()
        rows = [point(bundle, lead, r, s, review, lead_fixed=ld) for review, ld, (r, s) in itertools.product(rc.REVIEW_INTERVAL_GRID, rc.LEAD_TIME_GRID, pairs)]
        ctl = score(pd.DataFrame(rows), nl_c["not_late"], nl_v["not_late"], sv)
        logger.info("control grid: %d points in %.0fs", len(ctl), time.time() - t0)
        ctl_path = os.path.join(SUMMARY_DIR, "week1_recal_control_grid_PEM101_92.csv"); ctl.to_csv(ctl_path, index=False)
        control_members, ccounts = distinct_members(ctl, DEDUP_COLS + ["lead_time_days"])
        cm_path = os.path.join(SUMMARY_DIR, "week1_recal_control_members_PEM101_92.csv"); control_members.to_csv(cm_path, index=False)
        paths += [ctl_path, cm_path]
        targets["control_passing_by_definition"] = ccounts
        targets["control_distinct_members"] = int(len(control_members))
    targets["passing_by_definition"] = counts
    targets["distinct_members"] = int(len(members))

    tc = config["trade_off_curve"]
    window = (tc["simulation_window"]["start"], validation_end)
    envs = {}
    if len(members):
        curve = tradeoff(bundle, members, lead, tc["reorder_level_grid_r_months"], window, per_item_lead=True)
        cp = os.path.join(SUMMARY_DIR, "week1_recal_tradeoff_points_PEM101_92.csv"); curve.to_csv(cp, index=False)
        env = envelope(curve); ep = os.path.join(SUMMARY_DIR, "week1_recal_tradeoff_envelope_PEM101_92.csv"); env.to_csv(ep, index=False)
        paths += [cp, ep]
    if control_members is not None and len(control_members):
        curve = tradeoff(bundle, control_members, lead, tc["reorder_level_grid_r_months"], window, per_item_lead=False)
        cp = os.path.join(SUMMARY_DIR, "week1_recal_control_tradeoff_points_PEM101_92.csv"); curve.to_csv(cp, index=False)
        env = envelope(curve); ep = os.path.join(SUMMARY_DIR, "week1_recal_control_tradeoff_envelope_PEM101_92.csv"); env.to_csv(ep, index=False)
        paths += [cp, ep]
    tp = os.path.join(SUMMARY_DIR, "week1_recal_targets.json")
    with open(tp, "w", encoding="utf-8") as f:
        json.dump(targets, f, indent=1, default=str)
    paths.append(tp)
    record(paths)
    print(json.dumps(targets, indent=1, default=str))
    return targets


if __name__ == "__main__":
    main(run_control="--no-control" not in sys.argv)
