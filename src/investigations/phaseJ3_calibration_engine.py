"""Phase J3 Part 2 -- METRICS.md Sec.20 inverse_calibration engine.

Fits Section 16's simulation parameters (review interval, replenishment lead time, reorder level
and order-up-to level expressed as months of mean demand, usable-stock definition) against
OBSERVED reality (METRICS.md Sec.19 not_late, unit-weighted, and average on-hand stock value),
instead of assuming today's Min/Max settings (Phase J's calibration_gap) or a forecast-driven LTD/
safety-stock policy (Section 16 as used in Phase E1/E2/I).

Key departure from Section 16 as previously implemented: reorder level (r) and order-up-to level
(S) are expressed in MONTHS OF MEAN DEMAND (METRICS.md Sec.20's own parameterization), converted
to absolute units per item from that item's own historical mean daily demand -- no forecast model
is used at all. This is deliberate: Sec.20 is calibrating the POLICY SHAPE against reality, not
re-deriving the LTD-based Min/Max formula.

simulated not_late == Section 16's fill_rate (units shipped same day / units demanded) -- these are
the SAME quantity under two names: a unit is "not late" exactly when it is shipped on its own
demand day (the day interpreted as its due date throughout this project's daily replay
convention), and "late" exactly when it is backordered past that day. Stated explicitly here so a
reader does not go looking for a second, different formula.

No new database access -- reuses output/data/phaseI_raw_sales_351items.csv,
phaseI_inventory_exact_351items.csv, phaseI_combined_scope_351items.csv (all already cached).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config
from phaseE2_pilot_recompute import load_division_scope
from phaseE1_common import load_scope as load_pem101_scope
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ3_calibration_engine")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
RAW_SALES_FILE = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")
INV_FILE = os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")

DIVISIONS = ["PEM101", "PEM103", "PEM107"]
DAYS_PER_MONTH = 30.44

CALIBRATION_START = "2024-01-01"
WARMUP_END = "2024-06-30"          # first 6 months, excluded from scoring
CALIBRATION_SCORE_START = "2024-07-01"
CALIBRATION_END = "2025-12-31"
VALIDATION_START = "2026-01-01"
# VALIDATION_END is set from the actual data available -- see build_full_daily_series.


def load_scope_for(config: dict, division: str) -> pd.DataFrame:
    return load_pem101_scope(config) if division == "PEM101" else load_division_scope(config, division)


def build_full_daily_series(raw: pd.DataFrame, codes: list, day_min: str, day_max: str) -> dict:
    """Same construction as phaseE2_pilot_recompute.build_daily_series, but with CALLER-SUPPLIED
    date bounds instead of the fixed 2024-01/2026-07 window -- needed here because the calibration
    window (2024-01 to 2025-12) and validation window (2026-01 onward) together span further than
    that fixed window."""
    d = raw.dropna(subset=["forecast_date"]).copy()
    d = d[d["forecast_date"] >= d["createDate"]]
    day_min_ts = pd.Timestamp(day_min)
    day_max_ts = pd.Timestamp(day_max)
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


def load_raw():
    raw = pd.read_csv(RAW_SALES_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    inv = pd.read_csv(INV_FILE)
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    return raw, inv


def determine_validation_end(raw: pd.DataFrame) -> str:
    """The latest month safely treated as 'complete' -- this project's own leakage-guard
    convention (config.yaml leakage_guard.min_margin_days=30) requires at least 30 days between a
    window's last month-end and the data pull/creation date. createDate max in the cached pull is
    the effective 'today' for this data; back off one full calendar month from it to stay inside
    that margin, consistent with STATUS.md's own 'first scoreable target month' reasoning."""
    pull_date = raw["createDate"].max()
    last_complete_month_end = (pull_date.to_period("M") - 1).end_time.normalize()
    return str(last_complete_month_end.date())


def usable_stock_variants(bundle: dict) -> dict:
    return bundle["sellable_variants"]


def build_division_bundle(config: dict, division: str, raw: pd.DataFrame, inv: pd.DataFrame,
                           validation_end: str) -> dict:
    scope = load_scope_for(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)].copy()
    inv_div = inv[inv["itemcode"].isin(codes)].copy()

    daily_bundle = build_full_daily_series(raw_div, codes, CALIBRATION_START, validation_end)
    unit_cost_df = eng.compute_unit_cost_from_raw(raw_div, codes, 12).set_index("itemcode")

    all_wh_codes = sorted(inv["warehouse"].unique().tolist())
    e1 = config["phase_e1_assumptions"]
    variants = {
        "current": e1["sellable_warehouse_codes"].get(division),
        "fg_prefixed_only": eng.fg_prefixed_warehouses(all_wh_codes),
        "all_stockholding_except_qa_fmto_fmts": eng.current_stockholding_warehouses(inv_div),
    }

    return {
        "division": division, "codes": codes, "daily_series": daily_bundle["series"],
        "day_index": daily_bundle["day_index"], "unit_cost_df": unit_cost_df,
        "inv_div": inv_div, "sellable_variants": variants,
    }


def simulate_months_of_demand(qty_daily: np.ndarray, r_months: float, s_months: float,
                               review_interval_days: int, lead_time_days: int,
                               initial_stock: float, mean_daily_demand: float) -> dict:
    """METRICS.md Sec.20 parameterization: reorder level r and order-up-to level S expressed in
    months of MEAN demand (converted to absolute units via this item's own historical mean daily
    demand over the whole window) -- no forecast model. Otherwise identical mechanics to
    phaseE1fix_simulation.simulate_item_daily (review->reorder->receipt->demand/fulfilment,
    backorders filled first from the next receipt)."""
    r_abs = r_months * DAYS_PER_MONTH * mean_daily_demand
    s_abs = s_months * DAYS_PER_MONTH * mean_daily_demand

    n = len(qty_daily)
    on_hand = float(initial_stock)
    on_order = 0.0
    pending = {}
    backorder = 0.0

    daily_on_hand = np.zeros(n)
    daily_demand = np.zeros(n)
    daily_shipped = np.zeros(n)

    for t in range(n):
        if t in pending:
            received = pending.pop(t)
            on_order -= received
            paid = min(backorder, received)
            backorder -= paid
            on_hand += (received - paid)

        if review_interval_days <= 1 or t % review_interval_days == 0:
            position = on_hand + on_order
            if position <= r_abs:
                order_qty = s_abs - position
                if order_qty > 0:
                    on_order += order_qty
                    due = t + lead_time_days
                    if due < n:
                        pending[due] = pending.get(due, 0.0) + order_qty

        demand_t = float(qty_daily[t])
        daily_demand[t] = demand_t
        shipped = min(on_hand, demand_t)
        daily_shipped[t] = shipped
        shortfall = demand_t - shipped
        on_hand -= shipped
        if shortfall > 0:
            backorder += shortfall
        daily_on_hand[t] = on_hand

    return {"daily_on_hand": daily_on_hand, "daily_demand": daily_demand, "daily_shipped": daily_shipped}


def window_mask(day_index: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    return (day_index >= pd.Timestamp(start)) & (day_index <= pd.Timestamp(end))


def run_division_grid_point(bundle: dict, r_months: float, s_months: float, review_interval_days: int,
                             lead_time_days: int) -> dict:
    """One grid point for one division: simulate every item, then score not_late (unit-weighted,
    == Section 16 fill_rate) and average stock value over the calibration-scoring window and the
    validation window separately. Initial stock = S (order-up-to level), matching Section 16's own
    'Max at day 0' convention -- METRICS.md Sec.20 states the historical initial stock is unknown
    and the warm-up absorbs it, so this choice does not need to match any real definition-specific
    snapshot.

    `stock_definition` is carried through as a LABEL, not used inside the simulation itself: the
    simulated trajectory (on_hand, demand, shipped) does not depend on which real warehouses count
    as "usable" -- that choice only matters when this grid point's calib/valid_stock_value is
    compared against the EMPIRICAL target, which differs per stock definition (see the Validator's
    Part C figures, one target value per definition). The grid search below therefore runs the
    identical simulation once per (r, s, review, lead) combination and scores it against all three
    definitions' targets, rather than re-simulating per definition."""
    day_index = bundle["day_index"]
    calib_mask = window_mask(day_index, CALIBRATION_SCORE_START, CALIBRATION_END)
    valid_mask = window_mask(day_index, VALIDATION_START, day_index[-1].strftime("%Y-%m-%d"))
    unit_cost = bundle["unit_cost_df"]["unit_cost"]

    calib_demand = calib_shipped = 0.0
    valid_demand = valid_shipped = 0.0
    calib_stockval_days = None
    valid_stockval_days = None
    n_items_simulated = 0

    for code in bundle["codes"]:
        qty = bundle["daily_series"][code]
        mean_d = qty.mean()
        if mean_d <= 0:
            continue
        uc = unit_cost.get(code, np.nan)
        sim = simulate_months_of_demand(qty, r_months, s_months, review_interval_days, lead_time_days,
                                         initial_stock=s_months * DAYS_PER_MONTH * mean_d, mean_daily_demand=mean_d)
        n_items_simulated += 1
        calib_demand += sim["daily_demand"][calib_mask].sum()
        calib_shipped += sim["daily_shipped"][calib_mask].sum()
        valid_demand += sim["daily_demand"][valid_mask].sum()
        valid_shipped += sim["daily_shipped"][valid_mask].sum()

        if pd.notna(uc):
            item_calib_val = sim["daily_on_hand"][calib_mask] * uc
            item_valid_val = sim["daily_on_hand"][valid_mask] * uc
            calib_stockval_days = item_calib_val if calib_stockval_days is None else calib_stockval_days + item_calib_val
            valid_stockval_days = item_valid_val if valid_stockval_days is None else valid_stockval_days + item_valid_val

    calib_not_late = calib_shipped / calib_demand if calib_demand > 0 else np.nan
    valid_not_late = valid_shipped / valid_demand if valid_demand > 0 else np.nan
    calib_stock_value = float(calib_stockval_days.mean()) if calib_stockval_days is not None else np.nan
    valid_stock_value = float(valid_stockval_days.mean()) if valid_stockval_days is not None else np.nan

    return {
        "r_months": r_months, "s_months": s_months, "review_interval_days": review_interval_days,
        "lead_time_days": lead_time_days,
        "calib_not_late": calib_not_late, "valid_not_late": valid_not_late,
        "calib_stock_value": calib_stock_value, "valid_stock_value": valid_stock_value,
        "n_items_simulated": n_items_simulated,
    }
