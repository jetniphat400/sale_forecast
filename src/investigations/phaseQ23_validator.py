"""Q23 Validator -- Part 6, independent recomputation of all three Q23 checks.

Reads ONLY this Validator's own fresh pull (src/investigations/phaseQ23_validator_pull.py output:
output/data/phaseQ23_validator_scope_394items.csv, phaseQ23_validator_raw_394items.csv) -- never
any cached scope/raw file another agent built this session, and never any Modeler/Analyst/Explorer
report or script from this task. Reuses only pre-existing, project-standard methodology:
  - src/backtest_rekeyed.py (get_origins, compute_metrics, MA_WINDOWS, rolling-origin convention:
    MIN_TRAIN_MONTHS=13, ORIGIN_STEP=2, HOLDOUT=6)
  - src/leakage_guard.py (check_window_closed, load_min_margin_days)
  - src/models.py (combination_forecast)
  - src/investigations/phaseJ3_run_calibration.py / phaseJ3_calibration_engine.py (METRICS.md
    Sec.20 grid, tolerance, targets, calibration/validation windows -- constants imported directly,
    not retyped, so there is no risk of transcription drift from the pre-existing values)

Three checks, per this task's own Part numbering:
  Part 1 -- channel mix, PEM103/PEM107, 2025 and 2026 only (own fresh 394-code pull).
  Part 2 -- METRICS.md Sec.21 same-target accuracy comparison (Method A: Omni-only Top-down;
            Method B: Omni+Tendering Top-down, scaled down to Omni by point-in-time Omni share of
            combined), rolling-origin, PEM101 (171-code full scope)/PEM103/PEM107.
  Part 3 -- METRICS.md Sec.20 inverse-calibration grid search, PEM103 only, driven by this
            Validator's OWN combined-channel (Omni+Tendering) daily series instead of Phase J3's
            Omni-only cached file. Grid/tolerance/targets reused verbatim from phaseJ3_run_calibration.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backtest_rekeyed import HOLDOUT, MA_WINDOWS, get_origins, compute_metrics
from leakage_guard import check_window_closed, load_min_margin_days
from models import combination_forecast
import phaseJ3_run_calibration as jr
import phaseJ3_calibration_engine as jc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseQ23_validator")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

RAW_FILE = os.path.join(DATA_DIR, "phaseQ23_validator_raw_394items.csv")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseQ23_validator_scope_394items.csv")

DIVISIONS = ["PEM101", "PEM103", "PEM107"]
OMNI = ["Omni Channel"]
COMBINED = ["Omni Channel", "Tendering"]
DAYS_PER_MONTH = jc.DAYS_PER_MONTH


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_raw() -> tuple:
    raw = pd.read_csv(RAW_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    scope = pd.read_csv(SCOPE_FILE)
    return raw, scope


# ================================================================================================
# Part 1 -- channel mix, PEM103/PEM107, 2025 and 2026 only
# ================================================================================================

def channel_mix(raw: pd.DataFrame, scope: pd.DataFrame) -> pd.DataFrame:
    code2div = dict(zip(scope["code"], scope["division"]))
    df = raw.copy()
    df["division"] = df["itemcode"].map(code2div)
    df["year"] = df["createDate"].dt.year
    rows = []
    for div in ["PEM103", "PEM107"]:
        for yr in [2025, 2026]:
            sub = df[(df["division"] == div) & (df["year"] == yr)]
            total_value = float(sub["sale"].sum())
            total_qty = float(sub["qty"].sum())
            for rt, g in sub.groupby("revenue_type"):
                value = float(g["sale"].sum())
                qty = float(g["qty"].sum())
                rows.append({
                    "division": div, "year": yr, "revenue_type": rt,
                    "value_thb": value, "qty": qty,
                    "value_share_pct": 100 * value / total_value if total_value else np.nan,
                    "qty_share_pct": 100 * qty / total_qty if total_qty else np.nan,
                    "division_year_total_value_thb": total_value,
                    "division_year_total_qty": total_qty,
                })
    return pd.DataFrame(rows)


def confirm_2023_empty(raw: pd.DataFrame) -> dict:
    n_2023 = int((raw["createDate"].dt.year == 2023).sum())
    d = raw.dropna(subset=["forecast_date"]).copy()
    d = d[d["forecast_date"] >= d["createDate"]]
    n_2023_usable_fd = int((d["createDate"].dt.year == 2023).sum())
    return {"rows_createDate_2023": n_2023, "usable_forecastdate_rows_createDate_2023": n_2023_usable_fd,
            "pull_start": "2023-01-01"}


# ================================================================================================
# Safe common window (own leakage-guard determination, per task instruction -- not assumed)
# ================================================================================================

def determine_safe_window(raw: pd.DataFrame, min_margin_days: int) -> dict:
    pull_date = raw["createDate"].max()
    month = pd.Period("2026-08", freq="M")  # start from the latest plausible month and back off
    month = pull_date.to_period("M")
    while True:
        try:
            check_window_closed(month, pull_date, min_margin_days)
            break
        except Exception:
            month = month - 1
    month_max = str(month)
    return {"pull_date": pull_date, "month_min": "2024-01", "month_max": month_max}


# ================================================================================================
# Monthly / daily zero-filled series builders (forecast_date-keyed, same convention project-wide)
# ================================================================================================

def _filtered(raw: pd.DataFrame, codes: list, revenue_types: list) -> pd.DataFrame:
    d = raw[raw["itemcode"].isin(codes) & raw["revenue_type"].isin(revenue_types)].copy()
    d = d.dropna(subset=["forecast_date"])
    d = d[d["forecast_date"] >= d["createDate"]]
    return d


def build_monthly_grid(raw: pd.DataFrame, codes: list, revenue_types: list, month_min: str, month_max: str) -> dict:
    d = _filtered(raw, codes, revenue_types)
    d["year_month"] = d["forecast_date"].dt.to_period("M")
    months = pd.period_range(month_min, month_max, freq="M")
    d = d[d["year_month"].isin(set(months))]
    monthly = d.groupby(["itemcode", "year_month"], as_index=False)["qty"].sum()
    full_index = pd.MultiIndex.from_product([codes, months], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()
    out = {}
    for code in codes:
        g = full[full["itemcode"] == code].sort_values("year_month")
        out[code] = g["qty"].to_numpy(dtype=float)
    return {"series": out, "months": [str(m) for m in months]}


def build_daily_grid(raw: pd.DataFrame, codes: list, revenue_types: list, day_min: str, day_max: str) -> dict:
    d = _filtered(raw, codes, revenue_types)
    day_min_ts, day_max_ts = pd.Timestamp(day_min), pd.Timestamp(day_max)
    d = d[(d["forecast_date"] >= day_min_ts) & (d["forecast_date"] <= day_max_ts)]
    full_day_index = pd.date_range(day_min_ts, day_max_ts, freq="D")
    daily = d.groupby(["itemcode", d["forecast_date"].dt.normalize()])["qty"].sum()
    item_index = daily.index.get_level_values(0)
    out = {}
    for code in codes:
        s = pd.Series(0.0, index=full_day_index)
        if code in item_index:
            sub = daily.loc[code]
            s.loc[sub.index] = sub.to_numpy(dtype=float)
        out[code] = s.to_numpy(dtype=float)
    return {"series": out, "day_index": full_day_index}


# ================================================================================================
# Part 2 -- METRICS.md Sec.21 same-target accuracy comparison (Method A vs Method B)
# ================================================================================================

def run_part2_division(division: str, scope_div: pd.DataFrame, raw: pd.DataFrame, month_min: str, month_max: str,
                        pull_date, min_margin_days: int) -> pd.DataFrame:
    codes = sorted(scope_div["code"].unique())
    type_of = dict(zip(scope_div["code"], scope_div["type"]))
    items_by_type = {}
    for code in codes:
        items_by_type.setdefault(type_of[code], []).append(code)

    omni = build_monthly_grid(raw, codes, OMNI, month_min, month_max)
    comb = build_monthly_grid(raw, codes, COMBINED, month_min, month_max)
    months = omni["months"]
    total_months = len(months)

    type_omni = {typ: sum(omni["series"][c] for c in items) for typ, items in items_by_type.items()}
    type_comb = {typ: sum(comb["series"][c] for c in items) for typ, items in items_by_type.items()}

    origins = get_origins(total_months, HOLDOUT)
    rows = []
    for origin_idx, train_size in enumerate(origins, start=1):
        test_end = train_size + HOLDOUT
        if test_end > total_months:
            continue
        window_end_month = months[test_end - 1]
        check_window_closed(window_end_month, pull_date, min_margin_days)

        typefc_omni, typefc_comb = {}, {}
        for typ in items_by_type:
            typefc_omni[typ] = np.clip(combination_forecast(type_omni[typ][:train_size], HOLDOUT, MA_WINDOWS), 0, None)
            typefc_comb[typ] = np.clip(combination_forecast(type_comb[typ][:train_size], HOLDOUT, MA_WINDOWS), 0, None)

        for typ, items in items_by_type.items():
            type_omni_train_sum = type_omni[typ][:train_size].sum()
            type_comb_train_sum = type_comb[typ][:train_size].sum()
            for code in items:
                qty_omni = omni["series"][code]
                qty_comb = comb["series"][code]
                train_omni = qty_omni[:train_size]
                test_omni = qty_omni[train_size:test_end]
                train_comb = qty_comb[:train_size]

                # ---- Method A: Top-down on Omni-only series ----
                share_a = train_omni.sum() / type_omni_train_sum if type_omni_train_sum > 0 else 1.0 / len(items)
                fc_a = typefc_omni[typ] * share_a

                # ---- Method B: Top-down on Omni+Tendering, allocated by combined share ----
                share_b = train_comb.sum() / type_comb_train_sum if type_comb_train_sum > 0 else 1.0 / len(items)
                fc_b_combined = typefc_comb[typ] * share_b

                # Scale down to Omni-only via point-in-time Omni share of combined (item's own
                # TRAIN window only -- no data after the origin, METRICS.md Sec.21).
                if train_comb.sum() > 0:
                    omni_share_of_combined = train_omni.sum() / train_comb.sum()
                    fallback_used = False
                elif type_comb_train_sum > 0:
                    # Fallback (documented choice, METRICS.md Sec.21 leaves this to the
                    # implementer): item has zero combined demand in its training window -- use
                    # the TYPE-level Omni share of combined over the same training window instead.
                    omni_share_of_combined = type_omni_train_sum / type_comb_train_sum
                    fallback_used = True
                else:
                    omni_share_of_combined = 0.0
                    fallback_used = True
                fc_b = fc_b_combined * omni_share_of_combined

                m_a = compute_metrics(test_omni, fc_a, train_omni)
                m_b = compute_metrics(test_omni, fc_b, train_omni)
                rows.append({"division": division, "type": typ, "itemcode": code, "origin": origin_idx,
                             "train_size": train_size, "fallback_used": fallback_used,
                             "MAE_A": m_a["MAE"], "RMSE_A": m_a["RMSE"], "Bias_A": m_a["Bias"], "MASE_A": m_a["MASE"],
                             "MAE_B": m_b["MAE"], "RMSE_B": m_b["RMSE"], "Bias_B": m_b["Bias"], "MASE_B": m_b["MASE"]})
    return pd.DataFrame(rows)


def run_part2(raw: pd.DataFrame, scope: pd.DataFrame, month_min: str, month_max: str, pull_date, min_margin_days: int) -> tuple:
    all_rows = []
    for division in DIVISIONS:
        scope_div = scope[scope["division"] == division]
        df = run_part2_division(division, scope_div, raw, month_min, month_max, pull_date, min_margin_days)
        all_rows.append(df)
        logger.info("[Part 2] %s: %d item x origin rows scored (%d items, %d origins).",
                    division, len(df), scope_div["code"].nunique(), df["origin"].nunique() if len(df) else 0)
    detail = pd.concat(all_rows, ignore_index=True)

    # item-mean-first: average across origins per item, THEN average across items per division
    item_mean = detail.groupby(["division", "itemcode"], as_index=False)[
        ["MAE_A", "RMSE_A", "Bias_A", "MASE_A", "MAE_B", "RMSE_B", "Bias_B", "MASE_B"]].mean()
    division_summary = item_mean.groupby("division", as_index=False)[
        ["MAE_A", "RMSE_A", "Bias_A", "MASE_A", "MAE_B", "RMSE_B", "Bias_B", "MASE_B"]].mean()
    return detail, item_mean, division_summary


# ================================================================================================
# Part 3 -- METRICS.md Sec.20 calibration, PEM103 only, combined-channel (Omni+Tendering) demand
# ================================================================================================

def compute_unit_cost_omni(raw_div: pd.DataFrame, codes: list) -> pd.Series:
    """METRICS.md Sec.1: median(cost/qty) over the trailing 12 months, Omni Channel scope,
    Actual+MPS status (already the pull's status filter). Identical formula to
    phaseI_sensitivity_engine.compute_unit_cost_from_raw, reproduced here on this Validator's own
    Omni-only subset (never mixing Tendering rows into the cost basis -- METRICS.md Sec.1 does not
    say to, and this task's ONLY authorized change is the demand series feeding the simulation)."""
    omni = raw_div[raw_div["revenue_type"] == "Omni Channel"].copy()
    df = omni[(omni["qty"].notna()) & (omni["qty"] != 0) & (omni["cost"].notna())].copy()
    df["unit_cost"] = df["cost"] / df["qty"]
    global_max = df["createDate"].max()
    window_start = global_max - pd.DateOffset(months=12)
    in_window = df[df["createDate"] >= window_start]
    n_rows = in_window.groupby("itemcode").size()
    median_w = in_window.groupby("itemcode")["unit_cost"].median()
    max_date_per_item = df.groupby("itemcode")["createDate"].transform("max")
    recent = df[df["createDate"] == max_date_per_item].groupby("itemcode")["unit_cost"].mean()

    out = pd.Series(index=sorted(set(codes)), dtype=float)
    for code in out.index:
        nrows = n_rows.get(code, 0)
        if nrows >= 3:
            out[code] = median_w.get(code, np.nan)
        elif code in recent.index:
            out[code] = recent[code]
        else:
            out[code] = np.nan
    return out


def simulate_grid_point_vectorized(qty_matrix: np.ndarray, r_months: float, s_months: float,
                                    review_interval_days: int, lead_time_days: int,
                                    mean_daily_demand: np.ndarray) -> dict:
    """Vectorized-over-items reimplementation of phaseJ3_calibration_engine.simulate_months_of_demand
    -- identical mechanics (review -> reorder -> receipt -> demand/fulfilment, backorders filled
    first from the next receipt, initial stock = S at day 0), just looping over DAYS only (not
    days x items), for tractable runtime across the full 4,130-point grid. qty_matrix: shape
    (n_days, n_items)."""
    r_abs = r_months * DAYS_PER_MONTH * mean_daily_demand
    s_abs = s_months * DAYS_PER_MONTH * mean_daily_demand
    n_days, n_items = qty_matrix.shape

    on_hand = s_abs.copy()
    on_order = np.zeros(n_items)
    backorder = np.zeros(n_items)
    max_due = n_days  # receipts due beyond n_days-1 never arrive within the horizon -- dropped, same as original
    future_receipts = np.zeros((n_days, n_items))

    daily_on_hand = np.zeros((n_days, n_items))
    daily_shipped = np.zeros((n_days, n_items))

    review_step = max(int(review_interval_days), 1)
    continuous = review_interval_days <= 1

    for t in range(n_days):
        received = future_receipts[t]
        on_order = on_order - received
        paid = np.minimum(backorder, received)
        backorder = backorder - paid
        on_hand = on_hand + (received - paid)

        if continuous or (t % review_step == 0):
            position = on_hand + on_order
            need_order = position <= r_abs
            order_qty = np.where(need_order, s_abs - position, 0.0)
            order_qty = np.maximum(order_qty, 0.0)
            on_order = on_order + order_qty
            due = t + lead_time_days
            if due < max_due:
                future_receipts[due] += order_qty

        demand_t = qty_matrix[t]
        shipped = np.minimum(on_hand, demand_t)
        daily_shipped[t] = shipped
        shortfall = demand_t - shipped
        on_hand = on_hand - shipped
        backorder = backorder + np.maximum(shortfall, 0.0)
        daily_on_hand[t] = on_hand

    return {"daily_on_hand": daily_on_hand, "daily_demand": qty_matrix, "daily_shipped": daily_shipped}


def run_part3_pem103(raw: pd.DataFrame, scope: pd.DataFrame) -> dict:
    division = "PEM103"
    scope_div = scope[scope["division"] == division]
    codes = sorted(scope_div["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)]

    validation_end = jc.determine_validation_end(raw_div)  # uses createDate.max(), same leakage-guard convention
    logger.info("[Part 3] PEM103 validation_end (own leakage-guard determination): %s", validation_end)

    daily = build_daily_grid(raw_div, codes, COMBINED, jc.CALIBRATION_START, validation_end)
    day_index = daily["day_index"]
    qty_matrix = np.stack([daily["series"][c] for c in codes], axis=1)  # (n_days, n_items)
    mean_daily_demand = qty_matrix.mean(axis=0)
    active = mean_daily_demand > 0
    logger.info("[Part 3] PEM103: %d of %d items have nonzero mean combined-channel daily demand "
                "(inactive items excluded from simulation exactly as phaseJ3_calibration_engine does).",
                int(active.sum()), len(codes))
    qty_active = qty_matrix[:, active]
    mean_active = mean_daily_demand[active]
    codes_active = [c for c, a in zip(codes, active) if a]

    unit_cost = compute_unit_cost_omni(raw_div, codes)
    unit_cost_active = unit_cost.reindex(codes_active).to_numpy(dtype=float)
    has_cost = ~np.isnan(unit_cost_active)
    logger.info("[Part 3] PEM103: %d of %d active items have a usable unit_cost (Omni-scope, METRICS.md Sec.1).",
                int(has_cost.sum()), len(codes_active))

    calib_mask = (day_index >= pd.Timestamp(jc.CALIBRATION_SCORE_START)) & (day_index <= pd.Timestamp(jc.CALIBRATION_END))
    valid_mask = (day_index >= pd.Timestamp(jc.VALIDATION_START)) & (day_index <= pd.Timestamp(day_index[-1]))
    logger.info("[Part 3] Calibration-score window: %s to %s (%d days); Validation window: %s to %s (%d days).",
                jc.CALIBRATION_SCORE_START, jc.CALIBRATION_END, int(calib_mask.sum()),
                jc.VALIDATION_START, day_index[-1].date(), int(valid_mask.sum()))

    pairs = jr.rs_pairs()
    rows = []
    n_total = len(jr.REVIEW_INTERVAL_GRID) * len(jr.LEAD_TIME_GRID) * len(pairs)
    i = 0
    import time
    t0 = time.time()
    for review in jr.REVIEW_INTERVAL_GRID:
        for lead in jr.LEAD_TIME_GRID:
            for (r, s) in pairs:
                i += 1
                sim = simulate_grid_point_vectorized(qty_active, r, s, review, lead, mean_active)
                calib_demand = sim["daily_demand"][calib_mask].sum()
                calib_shipped = sim["daily_shipped"][calib_mask].sum()
                valid_demand = sim["daily_demand"][valid_mask].sum()
                valid_shipped = sim["daily_shipped"][valid_mask].sum()
                calib_not_late = calib_shipped / calib_demand if calib_demand > 0 else np.nan
                valid_not_late = valid_shipped / valid_demand if valid_demand > 0 else np.nan

                oh = sim["daily_on_hand"]
                cost_col = np.where(has_cost, unit_cost_active, 0.0)
                item_val = oh * cost_col[None, :]
                calib_stock_value = float(item_val[calib_mask].sum(axis=1).mean())
                valid_stock_value = float(item_val[valid_mask].sum(axis=1).mean())

                rows.append({"r_months": r, "s_months": s, "review_interval_days": review, "lead_time_days": lead,
                             "calib_not_late": calib_not_late, "valid_not_late": valid_not_late,
                             "calib_stock_value": calib_stock_value, "valid_stock_value": valid_stock_value})
                if i % 500 == 0:
                    logger.info("[Part 3] %d/%d grid points done (%.1fs elapsed)", i, n_total, time.time() - t0)
    logger.info("[Part 3] Grid complete: %d points in %.1fs", len(rows), time.time() - t0)

    df = pd.DataFrame(rows)
    target = jr.STOCK_VALUE_TARGET_CURRENT["PEM103"]
    df["calib_stockval_pctdiff"] = 100 * (df["calib_stock_value"] - target).abs() / target
    df["valid_stockval_pctdiff"] = 100 * (df["valid_stock_value"] - target).abs() / target
    df["calib_notlate_diff_pp"] = 100 * (df["calib_not_late"] - jr.NOT_LATE_TARGET_CALIB["PEM103"]).abs()
    df["valid_notlate_diff_pp"] = 100 * (df["valid_not_late"] - jr.NOT_LATE_TARGET_VALID["PEM103"]).abs()

    passing_both = df[
        (df["calib_notlate_diff_pp"] <= jr.NOT_LATE_TOL_PP) &
        (df["calib_stockval_pctdiff"] <= jr.STOCK_VALUE_TOL_PCT) &
        (df["valid_notlate_diff_pp"] <= jr.NOT_LATE_TOL_PP) &
        (df["valid_stockval_pctdiff"] <= jr.STOCK_VALUE_TOL_PCT)
    ]
    notlate_only = df[(df["calib_notlate_diff_pp"] <= jr.NOT_LATE_TOL_PP) & (df["valid_notlate_diff_pp"] <= jr.NOT_LATE_TOL_PP)]

    best_notlate_only = None
    if len(notlate_only):
        nl = notlate_only.copy()
        nl["combined_notlate_err"] = nl["calib_notlate_diff_pp"] + nl["valid_notlate_diff_pp"]
        best_row = nl.sort_values(["combined_notlate_err", "calib_stock_value"]).iloc[0]
        capital_multiple = float(best_row["calib_stock_value"] / target)
        capital_multiple_valid = float(best_row["valid_stock_value"] / target)
        best_notlate_only = {"row": best_row.to_dict(), "capital_multiple_calib": capital_multiple,
                              "capital_multiple_valid": capital_multiple_valid}

    return {"grid_df": df, "n_passing_both": len(passing_both), "n_total": len(df),
            "passing_both": passing_both, "best_notlate_only": best_notlate_only,
            "target_stock_value": target, "n_active_items": len(codes_active),
            "n_items_with_cost": int(has_cost.sum()), "validation_end": validation_end}


def main():
    config = load_config()
    min_margin_days = load_min_margin_days(config)
    raw, scope = load_raw()

    logger.info("=" * 100)
    logger.info("PART 1 -- CHANNEL MIX")
    logger.info("=" * 100)
    mix = channel_mix(raw, scope)
    mix.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_validator_channel_mix.csv"), index=False)
    empty2023 = confirm_2023_empty(raw)
    logger.info("2023 usable-row check: %s", empty2023)
    print(mix.to_string(index=False))
    print("2023 check:", empty2023)

    window = determine_safe_window(raw, min_margin_days)
    logger.info("Own leakage-guard safe window: %s", window)

    logger.info("=" * 100)
    logger.info("PART 2 -- SAME-TARGET ACCURACY COMPARISON")
    logger.info("=" * 100)
    detail, item_mean, division_summary = run_part2(raw, scope, window["month_min"], window["month_max"],
                                                      window["pull_date"], min_margin_days)
    detail.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_validator_part2_detail.csv"), index=False)
    item_mean.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_validator_part2_item_mean.csv"), index=False)
    division_summary.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_validator_part2_division_summary.csv"), index=False)
    print(division_summary.to_string(index=False))

    logger.info("=" * 100)
    logger.info("PART 3 -- PEM103 COMBINED-DEMAND CALIBRATION")
    logger.info("=" * 100)
    part3 = run_part3_pem103(raw, scope)
    part3["grid_df"].to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_validator_part3_pem103_grid.csv"), index=False)
    print(f"PEM103 combined-demand calibration: {part3['n_passing_both']} / {part3['n_total']} grid points "
          f"pass BOTH-window tolerance.")
    if part3["best_notlate_only"]:
        bn = part3["best_notlate_only"]
        print(f"Best not_late-alone fit: {bn['row']}")
        print(f"Capital multiple vs real target (calib window): {bn['capital_multiple_calib']:.2f}x")
        print(f"Capital multiple vs real target (valid window): {bn['capital_multiple_valid']:.2f}x")
    else:
        print("No grid point matched not_late alone within tolerance on both windows.")

    return {"mix": mix, "empty2023": empty2023, "window": window, "detail": detail,
            "item_mean": item_mean, "division_summary": division_summary, "part3": part3}


if __name__ == "__main__":
    main()
