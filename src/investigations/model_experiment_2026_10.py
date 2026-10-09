"""Forecast model experiment of 2026-10 (report only; METRICS.md Sec.50; config experiment_2026_10, PRE-REGISTERED 2026-10-09 before this file computed anything).

Compares the production Top-down Combination ("current") with five candidates on the existing backtest of the main table: the saved monthly series, the same items, the same 7
rolling origins, the same 6 horizons, the same cells (an item x an origin with a Top-down forecast). Groups: the five forecast divisions and the two pilot groups. Nothing in
the production model, a page, a recorded output or the forward-test log is changed or written; the result is printed and saved as one JSON under output/summary (untracked).

LEAKAGE: every candidate's forecast at an origin is computed by `forecasts_at_origin`, which hands each model the first `train_size` months only and asserts the length; the
test in tests/test_model_invariants.py changes every later value and shows no forecast changes.

Run: python src/investigations/model_experiment_2026_10.py
"""
import json
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest_rekeyed import HOLDOUT, MA_WINDOWS, TOTAL_MONTHS, get_origins        # noqa: E402
from leakage_guard import check_window_closed, load_min_margin_days                # noqa: E402
from models import combination_forecast, holt_forecast, naive_forecast             # noqa: E402
import transferability_all_divisions as ta                                         # noqa: E402

logger = logging.getLogger("model_experiment_2026_10")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")


def load_config() -> dict:
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Candidate forecasts (each receives training data only)
# ---------------------------------------------------------------------------------------------------------------------------------------------

def holt_clipped(train: np.ndarray, horizon: int) -> np.ndarray:
    """Holt's linear trend (statsforecast), clipped at 0; a failure or a non-finite value raises (never skipped)."""
    fc = np.clip(np.asarray(holt_forecast(train, horizon), dtype=float), 0, None)
    if not np.all(np.isfinite(fc)):
        raise ValueError("Holt returned a non-finite forecast")
    return fc


def bias_factor(type_train: np.ndarray, window: int, f_min: float, f_max: float) -> float:
    """f = sum of actual / sum of one-step-ahead in-sample Combination forecasts over the `window` months before the origin; the forecast of month m uses months before m only;
    1 when the forecast sum is 0; clipped to [f_min, f_max]."""
    n = len(type_train)
    forecasts, actual = [], []
    for m in range(n - window, n):
        forecasts.append(float(combination_forecast(type_train[:m], 1, MA_WINDOWS)[0]))
        actual.append(float(type_train[m]))
    denom = sum(forecasts)
    f = 1.0 if denom <= 0 else sum(actual) / denom
    return float(min(max(f, f_min), f_max))


def seasonal_naive(train: np.ndarray, horizon: int, lag: int) -> tuple:
    """(forecast, number of target months without a value `lag` months earlier): the value of month t - lag for target month t = len(train) + h; a missing one is filled with the
    Naive forecast and counted."""
    out, missing = np.empty(horizon), 0
    for h in range(horizon):
        idx = len(train) + h - lag
        if 0 <= idx < len(train):
            out[h] = train[idx]
        else:
            out[h] = train[-1]
            missing += 1
    return np.clip(out, 0, None), missing


def type_level_forecasts(type_series: np.ndarray, train_size: int, horizon: int, cfg: dict) -> dict:
    """The Type-level forecasts of current, holt, combination_plus_holt and bias_adjusted at one origin, from the first `train_size` months only."""
    train = np.asarray(type_series[:train_size], dtype=float)
    assert len(train) == train_size, "leakage guard: the models receive exactly the first train_size months"
    comb = np.clip(combination_forecast(train, horizon, MA_WINDOWS), 0, None)
    holt = holt_clipped(train, horizon)
    b = cfg["bias_adjusted"]
    f = bias_factor(train, int(b["window_months"]), float(b["factor_min"]), float(b["factor_max"]))
    return {"current": comb, "holt": holt, "combination_plus_holt": (6 * comb + holt) / 7, "bias_adjusted": comb * f, "bias_factor": f}


def forecasts_at_origin(item_series: np.ndarray, type_series: np.ndarray, train_size: int, horizon: int, cfg: dict, type_level: dict = None) -> dict:
    """{candidate: forecast array} for one item (or one group: item_series = type_series, share 1) at one origin. Only the first `train_size` months of either series are used."""
    item_train = np.asarray(item_series[:train_size], dtype=float)
    type_train = np.asarray(type_series[:train_size], dtype=float)
    assert len(item_train) == train_size and len(type_train) == train_size, "leakage guard"
    share = item_train.sum() / type_train.sum() if type_train.sum() > 0 else np.nan
    tl = type_level or type_level_forecasts(type_series, train_size, horizon, cfg)
    sn, missing = seasonal_naive(item_train, horizon, int(cfg["seasonal_naive"]["lag_months"]))
    return {"current": tl["current"] * share, "naive": np.clip(naive_forecast(item_train, horizon), 0, None), "holt": tl["holt"] * share,
            "combination_plus_holt": tl["combination_plus_holt"] * share, "bias_adjusted": tl["bias_adjusted"] * share, "seasonal_naive": sn,
            "_seasonal_missing": missing, "_share": share}


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Metrics and the rule
# ---------------------------------------------------------------------------------------------------------------------------------------------

def cell_sets(cells: list, candidates: list) -> list:
    return [c for c in cells]


def relative_mae(cells: list, cand: str, origins: set, horizon: int = None):
    """Sum of the candidate's window MAE (or |error| at one horizon) over Naive's, on the cells of the given origins; None when Naive's sum is 0 or there is no cell."""
    sel = [c for c in cells if c["origin"] in origins]
    if not sel:
        return None
    if horizon is None:
        m = sum(float(np.abs(c["fc"][cand] - c["act"]).mean()) for c in sel)
        n = sum(float(np.abs(c["fc"]["naive"] - c["act"]).mean()) for c in sel)
    else:
        h = horizon - 1
        m = sum(abs(float(c["fc"][cand][h] - c["act"][h])) for c in sel)
        n = sum(abs(float(c["fc"]["naive"][h] - c["act"][h])) for c in sel)
    return (m / n) if n > 0 else None


def tracking_signal(cells: list, cand: str, origins: set):
    """Tracking Signal of the group's monthly total at horizon 1: one point per origin (forecast - actual, summed over the cells of that origin); None when every error is 0."""
    by = {}
    for c in cells:
        if c["origin"] in origins:
            by[c["origin"]] = by.get(c["origin"], 0.0) + float(c["fc"][cand][0] - c["act"][0])
    e = [by[k] for k in sorted(by)]
    mean_abs = sum(abs(x) for x in e) / len(e) if e else 0.0
    return (sum(e) / mean_abs) if mean_abs > 0 else None


def group_table(cells: list, candidates: list, rule_cfg: dict, limit: float) -> dict:
    sel, conf, allo = (set(rule_cfg["origins"][k]) for k in ("selection", "confirmation", "reference"))
    out = {}
    for cand in candidates:
        ts15 = tracking_signal(cells, cand, sel)
        out[cand] = {"rel_15": relative_mae(cells, cand, sel), "rel_67": relative_mae(cells, cand, conf), "rel_all": relative_mae(cells, cand, allo),
                     "rel_h3_all": relative_mae(cells, cand, allo, 3), "ts_15": ts15, "ts_all": tracking_signal(cells, cand, allo),
                     "passes_ts": ts15 is not None and abs(ts15) <= limit}
    return out


def apply_rule(table: dict, candidates: list, rule_cfg: dict) -> dict:
    """The pre-registered rule: among the candidates with |TS| on origins 1-5 within the limit, the lowest Relative MAE on origins 1-5 (ties: candidate order); recommend a switch only
    when it is not current, at least `min_relative_improvement` below current's on 1-5, and below current's on origins 6-7. No candidate passes: keep current."""
    rule = rule_cfg["selection_rule"]
    eligible = [c for c in candidates if table[c]["passes_ts"] and table[c]["rel_15"] is not None]
    if not eligible:
        return {"outcome": "keep current", "winner": None, "reason": "no candidate passes the Tracking Signal filter"}
    winner = min(eligible, key=lambda c: (table[c]["rel_15"], candidates.index(c)))
    if winner == "current":
        return {"outcome": "keep current", "winner": winner, "reason": "current has the lowest Relative MAE on origins 1-5 among the candidates that pass the Tracking Signal filter"}
    cur, win = table["current"], table[winner]
    better15 = cur["rel_15"] is not None and win["rel_15"] <= (1 - float(rule["min_relative_improvement"])) * cur["rel_15"]
    better67 = (not rule["confirmation_must_be_lower"]) or (cur["rel_67"] is not None and win["rel_67"] is not None and win["rel_67"] < cur["rel_67"])
    if better15 and better67:
        return {"outcome": "switch", "winner": winner, "reason": f"{winner} is at least 5 percent below current on origins 1-5 and lower on origins 6-7"}
    why = []
    if not better15:
        why.append("not at least 5 percent below current on origins 1-5")
    if not better67:
        why.append("not lower than current on origins 6-7")
    return {"outcome": "keep current", "winner": winner, "reason": f"{winner} wins origins 1-5 but is " + " and ".join(why)}


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------------------------------------------------------------------------

def build_cells(cfg: dict) -> tuple:
    """(division cells, group cells {label: [cells]}, bookkeeping). A cell: {division, itemcode, origin, fc {candidate: array}, act}. The item cells are exactly the main table's cells
    (transferability_all_divisions.topdown_naive_cells); the current forecast recomputed here must equal them."""
    full = load_config()
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    margin = load_min_margin_days(full)
    item_series, type_series = ta.build_item_and_type_series(monthly, scope)
    main_cells = ta.topdown_naive_cells(item_series, type_series, pull_date, margin)
    cache, cells, missing_total, max_diff = {}, [], 0, 0.0
    for c in main_cells:
        qty, _m, type_key, _d, _c = item_series[c["itemcode"]]
        tq, _ = type_series[type_key]
        ts = c["train_size"]
        key = (type_key, ts)
        if key not in cache:
            cache[key] = type_level_forecasts(tq, ts, HOLDOUT, cfg)
        fc = forecasts_at_origin(qty, tq, ts, HOLDOUT, cfg, cache[key])
        max_diff = max(max_diff, float(np.abs(fc["current"] - c["fc"]).max()))
        missing_total += int(fc["_seasonal_missing"])
        cells.append({"division": c["division"], "itemcode": c["itemcode"], "origin": c["origin"], "act": c["act"], "fc": {k: v for k, v in fc.items() if not k.startswith("_")}})
    groups = {}
    for key, label in full["report"]["pilot_labels"].items():
        type_name = full["pilot_categories"][key]
        div = scope.loc[scope["type"] == type_name, "division"].iloc[0]
        tq, months = type_series[f"{div}::{type_name}"]
        gc, missing_g = [], 0
        for k, ts in enumerate(get_origins(TOTAL_MONTHS, HOLDOUT), start=1):
            check_window_closed(months[ts + HOLDOUT - 1], pull_date, margin)
            fc = forecasts_at_origin(tq, tq, ts, HOLDOUT, cfg)
            missing_g += int(fc["_seasonal_missing"])
            gc.append({"division": div, "itemcode": label, "origin": k, "act": np.asarray(tq[ts:ts + HOLDOUT], dtype=float), "fc": {c: v for c, v in fc.items() if not c.startswith("_")}})
        groups[label] = gc
        missing_total += missing_g
    return cells, groups, {"n_cells": len(cells), "max_abs_diff_current_vs_main_table": max_diff, "seasonal_naive_missing_target_months": missing_total}


def run() -> dict:
    full = load_config()
    cfg = full["experiment_2026_10"]
    candidates = list(cfg["candidates"])
    limit = float(full["maxmin_v1"]["pending_criteria_values"]["tracking_signal_limit"])
    cells, groups, book = build_cells(cfg)
    result = {"bookkeeping": book, "limit": limit, "groups": {}}
    division_order = [d for d in ["PEM101", "PEM103", "PEM107", "PEM102", "CI101"] if any(c["division"] == d for c in cells)]
    sets = {d: [c for c in cells if c["division"] == d] for d in division_order}
    sets.update(groups)
    for label, cs in sets.items():
        table = group_table(cs, candidates, cfg, limit)
        result["groups"][label] = {"n_cells": len(cs), "table": table, "rule": apply_rule(table, candidates, cfg)}
    return result


def items_of_group(label: str, full: dict) -> list:
    """The forecast-scope items of a division, or of a pilot group (the items of its Type in PEM101)."""
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    for key, pl in full["report"]["pilot_labels"].items():
        if pl == label:
            return sorted(scope.loc[scope["type"] == full["pilot_categories"][key], "code"])
    return sorted(scope.loc[scope["division"] == label, "code"])


def projection_effect(label: str, candidate: str, cfg: dict) -> dict:
    """REPORT ONLY: the effect on the executive summary's year-end projection (METRICS.md Sec.49) of the group's items if `candidate` had produced vintage 2: a refit on the whole
    fit window (train size 31), the same unit prices and booked-order rule (the larger of the forecast and the units on the books, per item and remaining month). The current method
    recomputed here must equal the vintage's forecast units (checked). Nothing is written to a page or a recorded output."""
    import build_report as br
    import build_trend_tab as bt
    import forward_test_scoring as fts
    import reader_values as rv
    full = load_config()
    vf = rv.vintage_facts(PROJECT_ROOT)
    forward = br.gather_forward_forecast(vf, br.gather_scope_table())
    fwd_units = {it["item"]: it["values"] for ts in forward["divisions"].values() for t in ts for it in t["items"]}
    codes = sorted(fwd_units)
    price_info = rv.unit_prices(codes, full["report"]["price_basis"], vf["fit_first"], vf["fit_last"], os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"), PROJECT_ROOT)
    prices = price_info["prices"]
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    item_series, type_series = ta.build_item_and_type_series(monthly, scope)
    data_month = str(monthly["year_month"].max())
    assert data_month == vf["fit_last"] and len(next(iter(item_series.values()))[0]) == TOTAL_MONTHS
    year, mnum = int(data_month[:4]), int(data_month[5:7])
    remaining = [f"{year}-{m:02d}" for m in range(mnum + 1, 13)]
    idx = [forward["months"].index(m) for m in remaining]
    raw = pd.read_csv(fts.RAW_HISTORY_PATH, usecols=["itemcode", "createDate", "forecast_date", "qty", "status", "revenue_type"])
    items = items_of_group(label, full)
    booked = bt.exec_booked_units(raw, set(items), remaining)
    by_month = {m: {"current": 0, "candidate": 0} for m in remaining}
    cache, max_diff = {}, 0.0
    for code in items:
        qty, _m, type_key, _d, _c = item_series[code]
        tq, _ = type_series[type_key]
        if type_key not in cache:
            cache[type_key] = type_level_forecasts(tq, TOTAL_MONTHS, HOLDOUT, cfg)
        fc = forecasts_at_origin(qty, tq, TOTAL_MONTHS, HOLDOUT, cfg, cache[type_key])
        max_diff = max(max_diff, float(np.abs(fc["current"] - np.asarray(fwd_units[code])).max()))
        for m, i in zip(remaining, idx):
            b = booked.get((code, m), 0.0)
            by_month[m]["current"] += bt.exec_month_baht(fc["current"][i], b, prices[code]["price"])
            by_month[m]["candidate"] += bt.exec_month_baht(fc[candidate][i], b, prices[code]["price"])
    cur, cand = sum(v["current"] for v in by_month.values()), sum(v["candidate"] for v in by_month.values())
    return {"group": label, "candidate": candidate, "n_items": len(items), "remaining_months": remaining, "by_month": by_month, "remaining_current": cur, "remaining_candidate": cand,
            "difference": cand - cur, "max_abs_diff_current_vs_vintage_units": max_diff}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run()
    cfg = load_config()["experiment_2026_10"]
    result["projection_effect"] = [projection_effect(label, g["rule"]["winner"], cfg) for label, g in result["groups"].items() if g["rule"]["outcome"] == "switch"]
    out = os.path.join(SUMMARY_DIR, "model_experiment_2026_10.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=float)
    print(json.dumps({k: v for k, v in result.items() if k != "groups"}, indent=1, default=float))
    for label, g in result["groups"].items():
        print(f"\n== {label} ({g['n_cells']} cells): {g['rule']['outcome']} | {g['rule']['winner']} | {g['rule']['reason']}")
        for cand, m in g["table"].items():
            f = lambda x: "-" if x is None else f"{x:.3f}"
            print(f"  {cand:24s} 1-5 {f(m['rel_15'])}  6-7 {f(m['rel_67'])}  all {f(m['rel_all'])}  H3 {f(m['rel_h3_all'])}  TS15 {f(m['ts_15'])}  TSall {f(m['ts_all'])}  pass {m['passes_ts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
