"""Item-specific model selection for this project's three focus codes
(EEE-F-FC-1040010002, HS-F-99-02110, HS-F-99-0213) — evaluated individually, not as part of an
aggregate Category/Type/division comparison. Every model available in the pipeline is scored on
each item separately: Naive, MA3/6/12, SES, Holt, Croston, SBA, TSB, the adopted six-model
Combination, and Top-down allocation from Type (the current default, compared against directly).

Data: reuses output/data/processed_all_divisions_monthly_qty.csv (335-item, 5-division scope,
2024-01 to 2026-07, forecast_date-keyed, snapshot_pull_date frozen by Phase C step 2's
src/load_data_all_divisions.py run) — NOT a fresh pull. This is deliberate: "Top-down
combination," the baseline every candidate here is compared against, was itself scored on this
exact data; a fresh pull would compare apples to a slightly different basket.

Evaluation: rolling-origin (src/backtest_rekeyed.py's get_origins/compute_metrics, imported
unchanged) is PRIMARY, train/val/test SECONDARY, per this project's adopted evaluation policy —
restated here because the task explicitly asks for it again given the known Feb-Jul 2026 window
anomaly (STATUS.md, closed without further pursuit, Section 8).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import (HOLDOUT, MA_WINDOWS, TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS,
                               VAL_MONTHS, compute_metrics, get_origins)
from leakage_guard import check_window_closed, load_min_margin_days
from models import (combination_forecast, croston_forecast, holt_forecast,
                     moving_average_forecast, naive_forecast, sba_forecast, ses_forecast,
                     tsb_forecast)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("focus_item_model_selection")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

# Pre-recovery supplementary split for EEE-F-FC-1040010002 (Part 3). Derived directly from the
# item's own monthly series (output/data/processed_all_divisions_monthly_qty.csv), not assumed:
# qty is genuinely 0 for 2025-01 through 2025-03 (the trough) and recovers steadily from 2025-04
# onward. 9 months train (2024-01 to 2024-09) / 6 months test (2024-10 to 2025-03) is the
# largest train/test split that stays entirely within the pre-recovery window (test ends exactly
# at the last confirmed zero month). This is NOT one of the standard rolling-origin points
# (MIN_TRAIN_MONTHS=13 in backtest_rekeyed.py makes every standard origin's test window already
# overlap the recovery — stated explicitly, not hidden) — a separate, single-split, smaller-n
# check, reported as supplementary evidence only.
EEE_PRE_RECOVERY_TRAIN_MONTHS = 9
EEE_PRE_RECOVERY_TEST_MONTHS = 6


def individual_model_candidates() -> dict:
    """All 9 individually-scored candidates (not the six-model Combination average, which is
    scored separately below, unchanged from its locked definition)."""
    models = {
        "Naive": naive_forecast,
        "MA3": lambda train, horizon: moving_average_forecast(train, horizon, 3),
        "MA6": lambda train, horizon: moving_average_forecast(train, horizon, 6),
        "MA12": lambda train, horizon: moving_average_forecast(train, horizon, 12),
        "SES": ses_forecast,
        "Holt": holt_forecast,
        "Croston": croston_forecast,
        "SBA": sba_forecast,
        "TSB": tsb_forecast,
    }
    return models


def build_item_and_type_series(monthly: pd.DataFrame, scope: pd.DataFrame, item_code: str) -> tuple:
    """Returns (item_qty, item_months, type_qty, type_months, division, type_name)."""
    row = scope[scope["code"] == item_code]
    if len(row) != 1:
        raise ValueError(f"{item_code}: expected exactly one scope row, found {len(row)}.")
    division, type_name = row["division"].iloc[0], row["type"].iloc[0]

    item_g = monthly[monthly["itemcode"] == item_code].sort_values("year_month")
    item_qty = item_g["qty"].to_numpy(dtype=float)
    item_months = item_g["year_month"].astype(str).tolist()

    type_items = scope[(scope["division"] == division) & (scope["type"] == type_name)]["code"].tolist()
    type_g = monthly[monthly["itemcode"].isin(type_items)].groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
    type_qty = type_g["qty"].to_numpy(dtype=float)
    type_months = type_g["year_month"].astype(str).tolist()

    return item_qty, item_months, type_qty, type_months, division, type_name


def score_all_candidates_at_origin(train: np.ndarray, test: np.ndarray, type_train: np.ndarray) -> dict:
    """Fits every candidate on `train`, scores against `test`. Returns {model_name: metrics_dict}.
    Raises nothing on an individual model failure -- records the failure reason instead, per
    instruction ("report why rather than silently omitting it")."""
    results = {}
    for name, fn in individual_model_candidates().items():
        try:
            fc = np.clip(fn(train, len(test)), 0, None)
            results[name] = {"metrics": compute_metrics(test, fc, train), "forecast": fc, "error": None}
        except Exception as e:
            results[name] = {"metrics": None, "forecast": None, "error": f"{type(e).__name__}: {e}"}

    try:
        fc = np.clip(combination_forecast(train, len(test), MA_WINDOWS), 0, None)
        results["Combination"] = {"metrics": compute_metrics(test, fc, train), "forecast": fc, "error": None}
    except Exception as e:
        results["Combination"] = {"metrics": None, "forecast": None, "error": f"{type(e).__name__}: {e}"}

    try:
        type_fc = np.clip(combination_forecast(type_train, len(test), MA_WINDOWS), 0, None)
        item_total, type_total = train.sum(), type_train.sum()
        share = item_total / type_total if type_total > 0 else np.nan
        if pd.notna(share):
            fc = type_fc * share
            results["Top-down"] = {"metrics": compute_metrics(test, fc, train), "forecast": fc, "error": None}
        else:
            results["Top-down"] = {"metrics": None, "forecast": None, "error": "Type total qty is 0 over this training window -- share undefined."}
    except Exception as e:
        results["Top-down"] = {"metrics": None, "forecast": None, "error": f"{type(e).__name__}: {e}"}

    return results


def run_rolling_origin_all_candidates(item_qty, item_months, type_qty, type_months,
                                       pull_date, min_margin_days) -> pd.DataFrame:
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)
    rows = []
    for origin_idx, train_size in enumerate(origins, start=1):
        train = item_qty[:train_size]
        test = item_qty[train_size:train_size + HOLDOUT]
        type_train = type_qty[:train_size]
        if len(test) < HOLDOUT:
            continue
        window_end_month = item_months[train_size + HOLDOUT - 1]
        check_window_closed(window_end_month, pull_date, min_margin_days)

        scored = score_all_candidates_at_origin(train, test, type_train)
        for model_name, r in scored.items():
            row = {"origin": origin_idx, "train_size": train_size, "model": model_name,
                   "window_end_month": window_end_month, "error": r["error"]}
            if r["metrics"] is not None:
                row.update(r["metrics"])
            rows.append(row)
    return pd.DataFrame(rows)


def run_train_val_test_all_candidates(item_qty, type_qty, pull_date, min_margin_days, item_months) -> tuple:
    if len(item_qty) != TOTAL_MONTHS:
        raise ValueError(f"Expected {TOTAL_MONTHS} months, got {len(item_qty)}.")
    train = item_qty[:TRAIN_MONTHS]
    val = item_qty[TRAIN_MONTHS:TRAIN_MONTHS + VAL_MONTHS]
    train_val = item_qty[:TRAIN_MONTHS + VAL_MONTHS]
    test = item_qty[TRAIN_MONTHS + VAL_MONTHS:]
    type_train = type_qty[:TRAIN_MONTHS]
    type_train_val = type_qty[:TRAIN_MONTHS + VAL_MONTHS]

    check_window_closed(item_months[TRAIN_MONTHS + VAL_MONTHS - 1], pull_date, min_margin_days)
    check_window_closed(item_months[TOTAL_MONTHS - 1], pull_date, min_margin_days)

    val_scored = score_all_candidates_at_origin(train, val, type_train)
    test_scored = score_all_candidates_at_origin(train_val, test, type_train_val)

    val_rows = [{"model": k, "error": v["error"], **(v["metrics"] or {})} for k, v in val_scored.items()]
    test_rows = [{"model": k, "error": v["error"], **(v["metrics"] or {})} for k, v in test_scored.items()]
    return pd.DataFrame(val_rows), pd.DataFrame(test_rows)


def bias_sign_summary(ro: pd.DataFrame) -> pd.DataFrame:
    """Per model: mean signed Bias, and how many origins were positive vs negative -- a model
    whose Bias flips sign across origins is a materially different result from one that is
    steadily biased in one direction, even if the MEAN happens to look similar."""
    rows = []
    for model, g in ro.dropna(subset=["Bias"]).groupby("model"):
        n = len(g)
        n_pos = (g["Bias"] > 0).sum()
        n_neg = (g["Bias"] < 0).sum()
        n_zero = n - n_pos - n_neg
        consistent = (n_pos == n) or (n_neg == n)
        rows.append({"model": model, "mean_bias": g["Bias"].mean(), "n_origins": n,
                     "n_positive": n_pos, "n_negative": n_neg, "n_zero": n_zero,
                     "sign_consistent": consistent})
    return pd.DataFrame(rows)


def winner_per_origin(ro: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for origin, g in ro.dropna(subset=["MAE"]).groupby("origin"):
        best = g.loc[g["MAE"].idxmin()]
        rows.append({"origin": origin, "winner": best["model"], "winner_MAE": best["MAE"]})
    win_counts = pd.DataFrame(rows)["winner"].value_counts()
    return pd.DataFrame(rows), win_counts


def paired_significance_vs_topdown(ro: pd.DataFrame, candidate_model: str) -> dict:
    """Paired t-test across origins, SAME methodology as
    src/transferability_all_divisions.py / src/item_level_reconciliation.py: pair by origin,
    diff = candidate_MAE - topdown_MAE, t = mean(diff)/se(diff)."""
    cand = ro[ro["model"] == candidate_model][["origin", "MAE"]].rename(columns={"MAE": "MAE_cand"})
    topdown = ro[ro["model"] == "Top-down"][["origin", "MAE"]].rename(columns={"MAE": "MAE_topdown"})
    paired = cand.merge(topdown, on="origin").dropna()
    n = len(paired)
    if n < 2:
        return {"candidate": candidate_model, "n_origins": n, "mean_diff": np.nan, "t_stat": np.nan}
    diff = paired["MAE_cand"] - paired["MAE_topdown"]
    se = diff.std(ddof=1) / np.sqrt(n)
    t_stat = diff.mean() / se if se else np.nan
    return {"candidate": candidate_model, "n_origins": n, "mean_diff": diff.mean(), "t_stat": t_stat}


# ------------------------------------------------------------------ data for the view of the two pilot categories and three items (week 4, computed only)
# Final method (STATUS.md Locked Decisions, "Final forecasting method: Top-down combination"): the Type-level six-model Combination allocated to items by each item's
# train-window share of its Type (src/transferability_all_divisions.py); the category-level backtest is the Type-level Combination series' own forecast. Read-only on the
# saved files under output/; no database. Recorded as one JSON file that carries the SHA-256 of its own content (`write_pilot_view`, `read_pilot_view`).
import hashlib as _hashlib
import json as _json
import math

FOCUS_PV = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
PILOT_CAT_DEFS = {
    "Drop-out Fuse Cutout": {"pricelist_type": "High Voltage Distribution Fuse Cutout", "level": "Type"},
    "Surge Arrester": {"pricelist_type": "Medium Voltage Surge Arrester", "level": "Type"},
}
# alternative reading of "Surge Arrester": the pricelist Product Cate. of that name (Low + Medium Voltage types)
PILOT_ALT_SURGE_CATEGORY = "Surge Arrester"


def _pv_float(x):
    if x is None:
        return None
    try:
        x = float(x)
    except Exception:
        return None
    return None if (math.isnan(x) or math.isinf(x)) else x


def _pv_clean(o):
    if isinstance(o, dict):
        return {str(k): _pv_clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_pv_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return _pv_float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def _pv_mean(vals):
    v = [x for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.mean(v)) if v else None


def build_pilot_view_payload(root: str = None) -> dict:
    root = root or PROJECT_ROOT
    src = os.path.join(root, "src")
    sys.path.insert(0, src)
    from backtest_rekeyed import HOLDOUT, MA_WINDOWS, TOTAL_MONTHS, compute_metrics, get_origins, run_rolling_origin
    from backtest_all_divisions import build_level_series_by_division
    from forward_test_scoring import fit_series_from_raw, score_items
    from leakage_guard import load_min_margin_days
    from models import combination_forecast, get_models
    from transferability_all_divisions import build_item_and_type_series, run_transferability_rolling_origin

    S = os.path.join(root, "output", "summary")
    D = os.path.join(root, "output", "data")
    with open(os.path.join(root, "config", "config.yaml"), "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(S, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(D, "processed_all_divisions_monthly_qty.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    pricelist_rows = pd.read_csv(os.path.join(D, "raw_pricelist_visible_rows.csv"))
    models = get_models(MA_WINDOWS)
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)
    payload = {"meta": {
        "today_checked": "2026-10-07",
        "root": root, "backtest": {"HOLDOUT": HOLDOUT, "TOTAL_MONTHS": TOTAL_MONTHS, "origins_train_sizes": origins,
                                   "min_margin_days": min_margin_days},
        "monthly_file": "output/data/processed_all_divisions_monthly_qty.csv",
        "monthly_snapshot_pull_date": pull_date,
        "monthly_first_month": monthly["year_month"].min(), "monthly_last_month": monthly["year_month"].max(),
        "scope_file": "output/summary/phaseC_step2_scope_335items.csv",
        "pricelist_file": "output/data/raw_pricelist_visible_rows.csv (copy of reference/pricelist.xlsx visible rows)",
        "method": ("Final method per STATUS.md Locked Decisions: Top-down combination. Category = Type-level six-model "
                   "Combination forecast (series' own); item = category/Type Combination x item's train-window qty share."),
        "model_note": "No model chosen by me; this is the project's locked method (Modeler role reports, does not decide)."}}

    # ------------------------------------------------------------------ scope
    scope_out = {}
    for cname, d in PILOT_CAT_DEFS.items():
        sub = scope[scope["type"] == d["pricelist_type"]]
        pl = pricelist_rows[pricelist_rows["type"] == d["pricelist_type"]]
        scope_out[cname] = {
            "defined_by": f"pricelist Product Type == '{d['pricelist_type']}' (config/config.yaml pilot_categories; DATA_MAP #42)",
            "division": sorted(sub["division"].unique().tolist()), "pricelist_category": sorted(sub["category"].unique().tolist()),
            "sheet": sorted(sub["sheet"].unique().tolist()),
            "n_items_in_scope_335_file": int(len(sub)), "n_items_in_pricelist_rows_file": int(len(pl)),
            "item_codes": sorted(sub["code"].tolist()),
            "same_codes_in_both_files": sorted(sub["code"].tolist()) == sorted(pl["code"].tolist()),
            "descriptions": {r.code: r.description for r in pl.itertuples()},
        }
    flag_file = os.path.join(S, "phaseD_check1_04_item_scope_445_with_division_and_forecast_flag.csv")
    flags = pd.read_csv(flag_file)
    for cname, d in PILOT_CAT_DEFS.items():
        pl_codes = pricelist_rows[pricelist_rows["type"] == d["pricelist_type"]]
        miss = pl_codes[~pl_codes["code"].isin(scope["code"])]
        scope_out[cname]["n_pricelist_items"] = int(len(pl_codes))
        scope_out[cname]["pricelist_items_not_in_forecast_scope"] = {
            "codes": sorted(miss["code"].tolist()),
            "is_forecast_item_flag_in": "output/summary/phaseD_check1_04_item_scope_445_with_division_and_forecast_flag.csv",
            "flag_values": flags[flags["itemcode"].isin(miss["code"])].set_index("itemcode")["is_forecast_item"].astype(bool).to_dict(),
            "in_config_placeholder_item_codes": sorted(set(miss["code"]) & set(config.get("placeholder_item_codes", []))),
            "note": "reason for is_forecast_item=False not re-derived here (INFERRED: forecast-status filter of load_data_all_divisions.py)"}
    alt = scope[scope["category"] == PILOT_ALT_SURGE_CATEGORY]
    scope_out["Surge Arrester (alt: whole pricelist Product Cate.)"] = {
        "defined_by": "pricelist Product Cate. == 'Surge Arrester' (Low Voltage + Medium Voltage types)",
        "types": alt.groupby("type").size().to_dict(), "n_items": int(len(alt)), "item_codes": sorted(alt["code"].tolist())}
    focus_rows = pricelist_rows[pricelist_rows["code"].isin(FOCUS_PV)]
    scope_out["focus_items"] = {r.code: {"category": r.category, "type": r.type, "description": r.description, "sheet": r.sheet}
                                for r in focus_rows.itertuples()}
    payload["scope"] = scope_out
    payload["scope"]["note_name"] = ("No pricelist Product Type is literally named 'Drop-out Fuse Cutout'; the project (STATUS.md brief item 2, "
                                     "DATA_MAP #42) maps it to Product Type 'High Voltage Distribution Fuse Cutout'.")

    # ------------------------------------------------------------------ series
    series = build_level_series_by_division(monthly, scope, "qty")
    pilot_types = {c: f"PEM101::{d['pricelist_type']}" for c, d in PILOT_CAT_DEFS.items()}
    alt_cat_key = f"PEM101::{PILOT_ALT_SURGE_CATEGORY}"
    months_all = series[("Type", pilot_types["Drop-out Fuse Cutout"], "PEM101::Fuse")][1]
    payload["meta"]["months"] = months_all

    # ---- reproduction 1: Type-level Combination rolling origin vs per-division summary and per-key rows
    type_keys = [k for k in series if k[0] == "Type"]
    sub_series = {k: series[k] for k in type_keys}
    sub_series[("Category", alt_cat_key, alt_cat_key)] = series[("Category", alt_cat_key, alt_cat_key)]
    ro = run_rolling_origin(sub_series, models, pull_date, min_margin_days)
    ro["division"] = ro["key"].str.split("::").str[0]
    combo = ro[(ro["model"] == "Combination") & (ro["level"] == "Type")]
    mine_div = combo.groupby("division", as_index=False).agg(MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), Bias=("Bias", "mean"),
                                                            MASE=("MASE", "mean"), n_origins=("origin", "nunique"))
    rec_div = pd.read_csv(os.path.join(S, "phaseC_step2_per_division_summary_qty.csv"))
    m = mine_div.merge(rec_div[["division", "MAE", "RMSE", "Bias", "MASE", "n_origins"]], on="division", suffixes=("_mine", "_recorded"))
    rep1 = []
    for r in m.itertuples():
        rep1.append({"division": r.division, "MAE_mine": r.MAE_mine, "MAE_recorded": r.MAE_recorded, "Bias_mine": r.Bias_mine,
                     "Bias_recorded": r.Bias_recorded, "MASE_mine": r.MASE_mine, "MASE_recorded": r.MASE_recorded,
                     "max_abs_diff": max(abs(r.MAE_mine - r.MAE_recorded), abs(r.Bias_mine - r.Bias_recorded),
                                         abs(r.MASE_mine - r.MASE_recorded)),
                     "n_origins_mine": int(r.n_origins_mine), "n_origins_recorded": int(r.n_origins_recorded)})
    rec_ro = pd.read_csv(os.path.join(S, "phaseC_step2_rolling_origin_qty.csv"))
    keys_chk = list(pilot_types.values()) + [alt_cat_key]
    cmp_rows = []
    for key in keys_chk:
        a = ro[ro["key"] == key][["level", "key", "origin", "model", "MAE", "Bias", "MASE"]]
        b = rec_ro[rec_ro["key"] == key][["level", "key", "origin", "model", "MAE", "Bias", "MASE"]]
        j = a.merge(b, on=["level", "key", "origin", "model"], suffixes=("_mine", "_rec"))
        cmp_rows.append({"key": key, "n_rows_mine": int(len(a)), "n_rows_recorded": int(len(b)), "n_matched": int(len(j)),
                         "max_abs_diff_MAE": float((j["MAE_mine"] - j["MAE_rec"]).abs().max()),
                         "max_abs_diff_Bias": float((j["Bias_mine"] - j["Bias_rec"]).abs().max()),
                         "max_abs_diff_MASE": float((j["MASE_mine"] - j["MASE_rec"]).abs().max())})
    payload["reproduction"] = {"per_division_type_level_combination": {
        "recorded_file": "output/summary/phaseC_step2_per_division_summary_qty.csv", "rows": rep1,
        "max_abs_diff_all": max(r["max_abs_diff"] for r in rep1)},
        "per_key_rolling_origin_rows": {"recorded_file": "output/summary/phaseC_step2_rolling_origin_qty.csv", "rows": cmp_rows}}

    # ---- reproduction 2: item Top-down (transferability) vs recorded item rolling origin + per-division summary
    item_series, type_series = build_item_and_type_series(monthly, scope)
    tr = run_transferability_rolling_origin(item_series, type_series, pull_date, min_margin_days)
    rec_tr = pd.read_csv(os.path.join(S, "phaseC_step2_transferability_item_rolling_origin.csv"))
    j = tr.merge(rec_tr, on=["itemcode", "origin", "approach"], suffixes=("_mine", "_rec"))
    tr_div = tr.groupby(["division", "approach"], as_index=False).agg(MAE=("MAE", "mean"), Bias=("Bias", "mean"), MASE=("MASE", "mean"),
                                                                     n_scored=("MAE", "size"))
    rec_tr_div = pd.read_csv(os.path.join(S, "phaseC_step2_transferability_per_division.csv"))
    jd = tr_div.merge(rec_tr_div[["division", "approach", "MAE", "Bias", "MASE", "n_scored"]], on=["division", "approach"], suffixes=("_mine", "_rec"))
    payload["reproduction"]["item_transferability"] = {
        "recorded_files": ["output/summary/phaseC_step2_transferability_item_rolling_origin.csv",
                           "output/summary/phaseC_step2_transferability_per_division.csv"],
        "n_item_origin_approach_rows_mine": int(len(tr)), "n_recorded": int(len(rec_tr)), "n_matched": int(len(j)),
        "max_abs_diff_MAE": float((j["MAE_mine"] - j["MAE_rec"]).abs().max()),
        "max_abs_diff_Bias": float((j["Bias_mine"] - j["Bias_rec"]).abs().max()),
        "max_abs_diff_MASE": float((j["MASE_mine"] - j["MASE_rec"]).abs().max()),
        "per_division_rows": [{"division": r.division, "approach": r.approach, "MAE_mine": r.MAE_mine, "MAE_recorded": r.MAE_rec,
                               "Bias_mine": r.Bias_mine, "Bias_recorded": r.Bias_rec, "MASE_mine": r.MASE_mine, "MASE_recorded": r.MASE_rec,
                               "n_mine": int(r.n_scored_mine), "n_recorded": int(r.n_scored_rec)} for r in jd.itertuples()],
        "max_abs_diff_per_division": float(max((jd["MAE_mine"] - jd["MAE_rec"]).abs().max(), (jd["Bias_mine"] - jd["Bias_rec"]).abs().max(),
                                              (jd["MASE_mine"] - jd["MASE_rec"]).abs().max()))}

    # ---- reproduction 3: focus items, all candidates, vs focus_items_rolling_origin_all.csv
    rec_focus = pd.read_csv(os.path.join(S, "focus_items_rolling_origin_all.csv"))
    focus_cmp, focus_direct = [], {}
    for code in FOCUS_PV:
        qty, months, type_key, div, cat = item_series[code]
        type_qty = type_series[type_key][0]
        rows = []
        for oi, ts in enumerate(origins, start=1):
            train, test = qty[:ts], qty[ts:ts + HOLDOUT]
            res = score_all_candidates_at_origin(train, test, type_qty[:ts])
            for mname, r in res.items():
                if r["metrics"] is not None:
                    rows.append({"origin": oi, "model": mname, **r["metrics"]})
        mine = pd.DataFrame(rows)
        rec = rec_focus[rec_focus["itemcode"] == code][["origin", "model", "MAE", "Bias", "MASE"]]
        jj = mine.merge(rec, on=["origin", "model"], suffixes=("_mine", "_rec"))
        focus_cmp.append({"itemcode": code, "n_rows_mine": int(len(mine)), "n_rows_recorded": int(len(rec)), "n_matched": int(len(jj)),
                          "max_abs_diff_MAE": float((jj["MAE_mine"] - jj["MAE_rec"]).abs().max()),
                          "max_abs_diff_Bias": float((jj["Bias_mine"] - jj["Bias_rec"]).abs().max()),
                          "max_abs_diff_MASE": float((jj["MASE_mine"] - jj["MASE_rec"]).abs().max()),
                          "mean_over_origins_mine": {mm: {k: float(g[k].mean()) for k in ["MAE", "Bias", "MASE"]}
                                                     for mm, g in mine[mine["model"].isin(["Top-down", "Combination", "Naive"])].groupby("model")},
                          "mean_over_origins_recorded": {mm: {k: float(g[k].mean()) for k in ["MAE", "Bias", "MASE"]}
                                                         for mm, g in rec_focus[(rec_focus["itemcode"] == code) &
                                                                                (rec_focus["model"].isin(["Top-down", "Combination", "Naive"]))].groupby("model")}})
        focus_direct[code] = {"Combination_Direct": focus_cmp[-1]["mean_over_origins_mine"].get("Combination")}
    payload["reproduction"]["focus_items_all_candidates"] = {
        "recorded_file": "output/summary/focus_items_rolling_origin_all.csv (also focus_<code>_rolling_origin.csv are its per-item split)",
        "rows": focus_cmp}

    # ------------------------------------------------------------------ units: per-origin forecasts and metrics
    def origin_block_series(qty, months, type_fc_fn):
        out = []
        for oi, ts in enumerate(origins, start=1):
            train, test = qty[:ts], qty[ts:ts + HOLDOUT]
            fc = type_fc_fn(ts)
            mt = compute_metrics(test, fc, train)
            out.append({"origin": oi, "train_size": ts, "fit_first_month": months[0], "fit_last_month": months[ts - 1],
                        "first_test_month": months[ts], "last_test_month": months[ts + HOLDOUT - 1],
                        "forecast_by_month": {months[ts + h]: float(fc[h]) for h in range(HOLDOUT)},
                        "actual_by_month": {months[ts + h]: float(test[h]) for h in range(HOLDOUT)},
                        "MAE": mt["MAE"], "RMSE": mt["RMSE"], "Bias": mt["Bias"], "MASE": mt["MASE"]})
        return out

    def summarise(blocks):
        return {"n_origins": len(blocks), "first_test_month": min(b["first_test_month"] for b in blocks),
                "last_test_month": max(b["last_test_month"] for b in blocks),
                "MAE": _pv_mean([b["MAE"] for b in blocks]), "RMSE": _pv_mean([b["RMSE"] for b in blocks]),
                "Bias": _pv_mean([b["Bias"] for b in blocks]), "MASE": _pv_mean([b["MASE"] for b in blocks])}

    units = {}
    # category series (own): Type-level Combination, clipped as run_rolling_origin does
    def cat_unit(label, key_tuple, member_codes):
        kk = [k for k in series if k[0] == key_tuple[0] and k[1] == key_tuple[1]]
        assert len(kk) == 1, kk
        qty, months = series[kk[0]]
        qty = np.asarray(qty, dtype=float)
        blocks = origin_block_series(qty, months, lambda ts: np.clip(combination_forecast(qty[:ts], HOLDOUT, MA_WINDOWS), 0, None))
        # item side (Top-down), same items
        item_blocks = {}
        for code in member_codes:
            iq, im, tk, dv, ct = item_series[code]
            if len(iq) != TOTAL_MONTHS or iq.sum() == 0:
                item_blocks[code] = None
                continue
            tq = type_series[tk][0]
            blks = []
            for oi, ts in enumerate(origins, start=1):
                train, test = iq[:ts], iq[ts:ts + HOLDOUT]
                tfc = np.clip(combination_forecast(tq[:ts], HOLDOUT, MA_WINDOWS), 0, None)
                share = train.sum() / tq[:ts].sum() if tq[:ts].sum() > 0 else float("nan")
                fc = tfc * share
                mt = compute_metrics(test, fc, train)
                blks.append({"origin": oi, "train_size": ts, "first_test_month": im[ts], "last_test_month": im[ts + HOLDOUT - 1],
                             "forecast_by_month": {im[ts + h]: float(fc[h]) for h in range(HOLDOUT)},
                             "actual_by_month": {im[ts + h]: float(test[h]) for h in range(HOLDOUT)},
                             "MAE": mt["MAE"], "RMSE": mt["RMSE"], "Bias": mt["Bias"], "MASE": mt["MASE"]})
            item_blocks[code] = blks
        scored = {c: summarise(b) for c, b in item_blocks.items() if b}
        unscored = [c for c, b in item_blocks.items() if not b]
        item_mase = [v["MASE"] for v in scored.values()]
        return {"label": label, "series_key": "/".join(key_tuple[:2]), "n_member_items": len(member_codes),
                "monthly_actual": {mm: float(v) for mm, v in zip(months, qty)},
                "origins": blocks, "series_own": summarise(blocks),
                "items_mean": {"n_items_scored": len(scored), "items_not_scored_all_zero": unscored,
                               "MAE": _pv_mean([v["MAE"] for v in scored.values()]),
                               "RMSE": _pv_mean([v["RMSE"] for v in scored.values()]),
                               "Bias": _pv_mean([v["Bias"] for v in scored.values()]),
                               "MASE": _pv_mean(item_mase), "n_items_mase_defined": int(sum(x is not None for x in item_mase))},
                "per_item_summary": scored}

    for cname, d in PILOT_CAT_DEFS.items():
        codes = payload["scope"][cname]["item_codes"]
        units[cname] = cat_unit(cname, ("Type", pilot_types[cname], pilot_types[cname]), codes)
    alt_codes = payload["scope"]["Surge Arrester (alt: whole pricelist Product Cate.)"]["item_codes"]
    units["Surge Arrester (alt: Product Cate., LV+MV)"] = cat_unit("Surge Arrester alt", ("Category", alt_cat_key, alt_cat_key), alt_codes)

    # focus items: Top-down (final) + Direct Combination, per-origin forecast
    for code in FOCUS_PV:
        iq, im, tk, dv, ct = item_series[code]
        tq = type_series[tk][0]
        blks_td, blks_dc = [], []
        for oi, ts in enumerate(origins, start=1):
            train, test = iq[:ts], iq[ts:ts + HOLDOUT]
            tfc = np.clip(combination_forecast(tq[:ts], HOLDOUT, MA_WINDOWS), 0, None)
            share = train.sum() / tq[:ts].sum()
            fc = tfc * share
            dfc = np.clip(combination_forecast(train, HOLDOUT, MA_WINDOWS), 0, None)
            for tgt, f in ((blks_td, fc), (blks_dc, dfc)):
                mt = compute_metrics(test, f, train)
                tgt.append({"origin": oi, "train_size": ts, "fit_first_month": im[0], "fit_last_month": im[ts - 1],
                            "first_test_month": im[ts], "last_test_month": im[ts + HOLDOUT - 1],
                            "forecast_by_month": {im[ts + h]: float(f[h]) for h in range(HOLDOUT)},
                            "actual_by_month": {im[ts + h]: float(test[h]) for h in range(HOLDOUT)},
                            "MAE": mt["MAE"], "RMSE": mt["RMSE"], "Bias": mt["Bias"], "MASE": mt["MASE"]})
        units[code] = {"label": code, "type_key": tk, "type": payload["scope"]["focus_items"][code]["type"],
                       "monthly_actual": {mm: float(v) for mm, v in zip(im, iq)},
                       "origins_topdown_final": blks_td, "topdown_final": summarise(blks_td),
                       "origins_direct_combination": blks_dc, "direct_combination_secondary": summarise(blks_dc),
                       "share_of_type_by_origin": [float(iq[:ts].sum() / tq[:ts].sum()) for ts in origins]}
    payload["units"] = units

    # ------------------------------------------------------------------ forward test
    log = pd.read_csv(os.path.join(S, "forward_test_log_all_divisions.csv"))
    scored_file = pd.read_csv(os.path.join(S, "forward_test_scored_all_divisions.csv"))
    fscores = pd.read_csv(os.path.join(S, "forward_test_scores.csv"))
    meta = _json.load(open(os.path.join(S, "forward_test_log_all_divisions_metadata.json"), encoding="utf-8"))
    raw = pd.read_csv(os.path.join(D, "raw_all_divisions_sales.csv"))
    fw = {"source_files": ["output/summary/forward_test_log_all_divisions.csv", "output/summary/forward_test_scored_all_divisions.csv",
                           "output/summary/forward_test_scores.csv", "output/summary/forward_test_log_all_divisions_metadata.json",
                           "output/data/raw_all_divisions_sales.csv (fit series rebuild, METRICS 13 scale)"],
          "n_rows_log_with_actual": int(log["actual_qty"].notna().sum()),
          "n_rows_scored_file_with_actual": int(scored_file["actual_qty"].notna().sum()),
          "vintages_in_log": sorted(int(v) for v in log["vintage_id"].unique()),
          "scored_target_months": sorted({(int(r.vintage_id), r.target_month, int(r.horizon)) for r in
                                          log[log["actual_qty"].notna() & (log["level"] == "Item")].itertuples()})}
    fw["scored_target_months"] = [list(x) for x in fw["scored_target_months"]]
    actual_rows = log[log["actual_qty"].notna()]
    fw["levels_with_actual"] = actual_rows.groupby("level").size().to_dict()
    # reproduction vs forward_test_scores.csv
    vmeta = meta["1"]
    fit_first, fit_last = vmeta["fit_first_month"], vmeta["fit_last_month"]
    item_scope_codes = sorted(scope["code"].tolist())
    fit = fit_series_from_raw(raw, item_scope_codes, fit_first, fit_last)
    v1h1 = log[(log["vintage_id"] == 1) & (log["horizon"] == 1) & (log["level"] == "Item")].copy()
    v1h1["actual_qty"] = pd.to_numeric(v1h1["actual_qty"])
    per_item_fw = score_items(v1h1.dropna(subset=["actual_qty"]), fit)
    rep_fw = []
    for code in FOCUS_PV:
        r = per_item_fw[per_item_fw["itemcode"] == code].iloc[0]
        rec = fscores[(fscores["scope"] == "focus_code") & (fscores["key"] == code)].iloc[0]
        rep_fw.append({"scope": "focus_code", "key": code, "MAE_mine": r["MAE"], "MAE_recorded": rec["MAE"], "Bias_mine": r["Bias"],
                       "Bias_recorded": rec["Bias"], "MASE_mine": r["MASE"], "MASE_recorded": rec["MASE"]})
    for div in ["PEM101"]:
        d = per_item_fw[per_item_fw["division"] == div]
        rec = fscores[(fscores["scope"] == "division") & (fscores["key"] == div)].iloc[0]
        rep_fw.append({"scope": "division", "key": div, "n_mine": int(len(d)), "n_recorded": int(rec["n_items"]), "MAE_mine": d["MAE"].mean(),
                       "MAE_recorded": rec["MAE"], "Bias_mine": d["Bias"].mean(), "Bias_recorded": rec["Bias"], "MASE_mine": d["MASE"].mean(),
                       "MASE_recorded": rec["MASE"]})
    fw["reproduction_vs_forward_test_scores_csv"] = rep_fw

    def fw_unit(label, member_codes, type_or_cat_row_name, row_level):
        rows = v1h1[v1h1["itemcode"].isin(member_codes)]
        pi = per_item_fw[per_item_fw["itemcode"].isin(member_codes)]
        # series' own (log's Type / Category row)
        own = log[(log["vintage_id"] == 1) & (log["horizon"] == 1) & (log["level"] == row_level) & (log["itemcode"] == type_or_cat_row_name)]
        own_out = None
        if len(own):
            o = own.iloc[0]
            agg_fit = np.sum([fit[c] for c in member_codes if c in fit], axis=0)
            act = float(o["actual_qty"]) if pd.notna(o["actual_qty"]) else None
            if act is not None:
                mt = compute_metrics(np.array([act]), np.array([float(o["forecast_qty"])]), agg_fit)
                own_out = {"forecast_qty": float(o["forecast_qty"]), "actual_qty": act, "MAE": mt["MAE"], "Bias": mt["Bias"], "MASE": mt["MASE"],
                           "fit_series_source": "sum of member items' fit series rebuilt from raw (my extension of the METRICS 13 scale; not a recorded figure)",
                           "log_row_key": f"{row_level}:{type_or_cat_row_name}"}
        return {"label": label, "vintage": 1, "horizon": 1, "target_month": "2026-08", "n_months_scored": 1,
                "n_items_scored": int(len(pi)),
                "items_mean": {"MAE": float(pi["MAE"].mean()), "Bias": float(pi["Bias"].mean()),
                               "MASE": _pv_mean(pi["MASE"].tolist()), "n_mase_defined": int(pi["MASE"].notna().sum())},
                "series_own": own_out,
                "sum_of_item_forecast": float(rows["forecast_qty"].sum()), "sum_of_item_actual": float(rows["actual_qty"].sum())}

    fw["units"] = {
        "Drop-out Fuse Cutout": fw_unit("Drop-out Fuse Cutout", scope_out["Drop-out Fuse Cutout"]["item_codes"],
                                        PILOT_CAT_DEFS["Drop-out Fuse Cutout"]["pricelist_type"], "Type"),
        "Surge Arrester": fw_unit("Surge Arrester", scope_out["Surge Arrester"]["item_codes"], PILOT_CAT_DEFS["Surge Arrester"]["pricelist_type"], "Type"),
        "Surge Arrester (alt: Product Cate., LV+MV)": fw_unit("Surge Arrester alt", alt_codes, PILOT_ALT_SURGE_CATEGORY, "Category")}
    fw["items"] = {}
    for code in FOCUS_PV:
        r = v1h1[v1h1["itemcode"] == code].iloc[0]
        pi = per_item_fw[per_item_fw["itemcode"] == code].iloc[0]
        fw["items"][code] = {"vintage": 1, "horizon": 1, "target_month": "2026-08", "forecast_qty": float(r["forecast_qty"]),
                             "actual_qty": float(r["actual_qty"]), "MAE": pi["MAE"], "Bias": pi["Bias"], "MASE": pi["MASE"], "n_months_scored": 1}
    # all forward-test rows (every horizon, both vintages) of the three items and category rows, for the view
    keep = log[((log["level"] == "Item") & log["itemcode"].isin(FOCUS_PV)) |
               ((log["level"] == "Type") & log["itemcode"].isin([d["pricelist_type"] for d in PILOT_CAT_DEFS.values()])) |
               ((log["level"] == "Category") & (log["itemcode"] == PILOT_ALT_SURGE_CATEGORY))]
    fw["forecast_rows"] = [{"vintage_id": int(r.vintage_id), "level": r.level, "key": r.itemcode, "horizon": int(r.horizon),
                            "target_month": r.target_month, "forecast_qty": float(r.forecast_qty),
                            "actual_qty": None if pd.isna(r.actual_qty) else float(r.actual_qty)} for r in keep.itertuples()]
    # check: log actual for Aug 2026 vs current monthly file's Aug 2026
    chk = []
    for code in FOCUS_PV:
        cur = float(monthly[(monthly["itemcode"] == code) & (monthly["year_month"] == "2026-08")]["qty"].sum())
        chk.append({"itemcode": code, "log_actual_2026_08": fw["items"][code]["actual_qty"], "monthly_file_2026_08": cur})
    fw["log_actual_vs_monthly_file"] = chk
    payload["forward_test"] = fw
    return _pv_clean(payload)


def _pv_hash(payload: dict) -> str:
    body_ = _json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return _hashlib.sha256(body_.encode("utf-8")).hexdigest()


def write_pilot_view(path: str, root: str = None) -> str:
    """Computes the payload and writes {"payload": ..., "sha256": hash of the payload's canonical JSON}."""
    payload = build_pilot_view_payload(root)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        _json.dump({"payload": payload, "sha256": _pv_hash(payload)}, fh, ensure_ascii=False, indent=1, allow_nan=False)
        fh.write("\n")
    return path


def read_pilot_view(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        rec = _json.load(fh)
    if rec.get("sha256") != _pv_hash(rec["payload"]):
        raise ValueError(f"{path} does not hash to the value it records")
    return rec["payload"]


if __name__ == "__main__":
    if "--pilot-view" in sys.argv:        # week 4: the data for the pilot view, recorded with its own hash; nothing else runs
        print(write_pilot_view(os.path.join(SUMMARY_DIR, "pilot_view_data_v1.json")))
        sys.exit(0)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    logger.info("Data: processed_all_divisions_monthly_qty.csv, snapshot_pull_date=%s, "
                "leakage guard min_margin_days=%d", pull_date, min_margin_days)

    all_ro, all_val, all_test, all_bias, all_winners, all_sig = [], [], [], [], [], []

    for item in FOCUS_ITEMS:
        logger.info("=== %s ===", item)
        item_qty, item_months, type_qty, type_months, division, type_name = build_item_and_type_series(
            monthly, scope, item)
        logger.info("%s: division=%s, type=%s, %d months, total qty=%.0f, %d zero months (%.1f%%)",
                    item, division, type_name, len(item_qty), item_qty.sum(),
                    int((item_qty == 0).sum()), 100 * (item_qty == 0).mean())

        ro = run_rolling_origin_all_candidates(item_qty, item_months, type_qty, type_months,
                                                pull_date, min_margin_days)
        ro["itemcode"] = item
        ro.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_rolling_origin.csv".replace("/", "_")), index=False)
        all_ro.append(ro)

        val_df, test_df = run_train_val_test_all_candidates(item_qty, type_qty, pull_date,
                                                              min_margin_days, item_months)
        val_df["itemcode"], test_df["itemcode"] = item, item
        val_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_val.csv".replace("/", "_")), index=False)
        test_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_test.csv".replace("/", "_")), index=False)
        all_val.append(val_df)
        all_test.append(test_df)

        bias_df = bias_sign_summary(ro)
        bias_df["itemcode"] = item
        bias_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_bias_sign.csv".replace("/", "_")), index=False)
        all_bias.append(bias_df)

        winners_df, win_counts = winner_per_origin(ro)
        winners_df["itemcode"] = item
        winners_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_winner_per_origin.csv".replace("/", "_")), index=False)
        all_winners.append(winners_df)

        sig_rows = []
        for model in ro["model"].unique():
            if model == "Top-down":
                continue
            sig_rows.append({**paired_significance_vs_topdown(ro, model), "itemcode": item})
        sig_df = pd.DataFrame(sig_rows)
        sig_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_significance_vs_topdown.csv".replace("/", "_")), index=False)
        all_sig.append(sig_df)

        logger.info("%s: rolling-origin done (%d origins x %d candidates), val/test done, "
                    "%d/%d origins won by each model: %s", item, ro["origin"].nunique(),
                    ro["model"].nunique(), ro["origin"].nunique(), ro["origin"].nunique(),
                    win_counts.to_dict())

    pd.concat(all_ro, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_rolling_origin_all.csv"), index=False)
    pd.concat(all_val, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_val_all.csv"), index=False)
    focus_items_test_all_df = pd.concat(all_test, ignore_index=True)
    # snapshot_pull_date recorded so a consuming page (src/build_report.py) can show WHEN the
    # data was pulled, never a file mtime proxy (task 2cfix2, Part 3) -- same pull that produced
    # processed_all_divisions_monthly_qty.csv, read above.
    focus_items_test_all_df["snapshot_pull_date"] = pull_date
    focus_items_test_all_df.to_csv(os.path.join(SUMMARY_DIR, "focus_items_test_all.csv"), index=False)
    pd.concat(all_bias, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_bias_sign_all.csv"), index=False)
    pd.concat(all_winners, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_winner_per_origin_all.csv"), index=False)
    pd.concat(all_sig, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_significance_vs_topdown_all.csv"), index=False)

    # ============================= EEE-F-FC-1040010002: pre-recovery supplementary split =============================
    logger.info("=== EEE-F-FC-1040010002: pre-recovery supplementary split ===")
    item_qty, item_months, type_qty, type_months, division, type_name = build_item_and_type_series(
        monthly, scope, "EEE-F-FC-1040010002")
    pre_train = item_qty[:EEE_PRE_RECOVERY_TRAIN_MONTHS]
    pre_test = item_qty[EEE_PRE_RECOVERY_TRAIN_MONTHS:EEE_PRE_RECOVERY_TRAIN_MONTHS + EEE_PRE_RECOVERY_TEST_MONTHS]
    pre_type_train = type_qty[:EEE_PRE_RECOVERY_TRAIN_MONTHS]
    window_end_month = item_months[EEE_PRE_RECOVERY_TRAIN_MONTHS + EEE_PRE_RECOVERY_TEST_MONTHS - 1]
    check_window_closed(window_end_month, pull_date, min_margin_days)
    logger.info("Pre-recovery split: train %s to %s (%d months), test %s to %s (%d months)",
                item_months[0], item_months[EEE_PRE_RECOVERY_TRAIN_MONTHS - 1], EEE_PRE_RECOVERY_TRAIN_MONTHS,
                item_months[EEE_PRE_RECOVERY_TRAIN_MONTHS], window_end_month, EEE_PRE_RECOVERY_TEST_MONTHS)
    pre_scored = score_all_candidates_at_origin(pre_train, pre_test, pre_type_train)
    pre_rows = [{"model": k, "error": v["error"], **(v["metrics"] or {})} for k, v in pre_scored.items()]
    pre_df = pd.DataFrame(pre_rows)
    pre_df.to_csv(os.path.join(SUMMARY_DIR, "focus_EEE-F-FC-1040010002_pre_recovery_split.csv"), index=False)
    print("\nEEE-F-FC-1040010002 pre-recovery split (train 2024-01/09, test 2024-10/2025-03):")
    print(pre_df[["model", "MAE", "RMSE", "Bias", "MASE", "error"]].round(2).to_string(index=False))

    print("\n" + "=" * 92)
    print("FOCUS ITEM MODEL SELECTION — SUMMARY")
    print("=" * 92)
    for item in FOCUS_ITEMS:
        ro = pd.concat(all_ro, ignore_index=True)
        item_ro = ro[ro["itemcode"] == item]
        summary = item_ro.dropna(subset=["MAE"]).groupby("model", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean().sort_values("MAE")
        print(f"\n--- {item} (rolling-origin mean, primary) ---")
        print(summary.round(2).to_string(index=False))

    print("\nOutputs: output/summary/focus_<item>_*.csv, focus_items_*_all.csv, "
          "focus_EEE-F-FC-1040010002_pre_recovery_split.csv")
