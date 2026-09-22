"""Phase E1 shared data access and low-level computation helpers.

Used by every phaseE1_*.py script so the 128-item scope, exclusion/placeholder flags, the
forecast_date-keyed monthly series, unit cost, sellable stock, current Min/Max and backlog are
each read/derived exactly once, the same way, everywhere they are used (CONVENTIONS.md: separate
data access from computation; every number verifiable against a direct recomputation).

Scope reminder (binding on every script that imports this module): PEM101 only, the 128-item
pilot scope (config['adopted_scope_file']). This is a BOUNDED SCENARIO PILOT -- it produces NO
actionable purchase recommendation, only a scenario analysis for the business to evaluate.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import run_query
from models import combination_forecast
from leakage_guard import check_window_closed, load_min_margin_days
from backtest_rekeyed import MA_WINDOWS, get_origins, compute_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_common")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "summary")  # overwritten below
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

SCOPE_FILE = os.path.join(PROJECT_ROOT, "output", "summary", "part1_category_scope_all_codes.csv")
MONTHLY_FILE = os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")
SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"
BACKLOG_TABLE = "[salewarehouse].[dbo].[Cube_Backlog]"
BACKLOG_SALE_COMPANIES = ["PEM", "CI"]

TOTAL_MONTHS = 31  # 2024-01 .. 2026-07, forecast_date-keyed common window (src/backtest_rekeyed.py)
MEDIAN_WINDOW_MONTHS = 12  # unit-cost basis window, same as Phase D Check 2

# ADI/CV2 demand-classification thresholds -- Syntetos, Boylan & Croston (2005), reused verbatim
# from src/investigations/series_features.py (ADI_THRESHOLD, CV2_THRESHOLD) rather than
# re-derived, so this phase's classification is directly comparable to Phase 1's.
ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------------------------------------
# Scope: the 128-item pilot, with excluded/placeholder flags
# ------------------------------------------------------------------------------------------

def load_scope(config: dict) -> pd.DataFrame:
    """Re-derives the 128-item pilot scope from config['adopted_scope_file'] (verified count,
    not assumed -- see phaseE1_modeler_report.md for the confirmation) and flags every item
    against config['excluded_item_codes'] (6) and config['placeholder_item_codes'] (10).

    Returns columns: code, category, type, division, has_any_history, is_excluded,
    is_placeholder, eligible_for_policy (True only when neither flag is set).
    """
    scope_path = os.path.join(PROJECT_ROOT, config["adopted_scope_file"])
    scope = pd.read_csv(scope_path)
    n = len(scope)
    logger.info("Loaded %d rows from %s (config['adopted_scope_file']) -- this IS the 128-item "
                "pilot scope count, confirmed by this read, not assumed from config['pilot_categories'].",
                n, scope_path)

    excluded = set(config["excluded_item_codes"])
    placeholder = set(config["placeholder_item_codes"])
    placeholder82 = set(config["placeholder_item_assignments_82"].keys())

    overlap_82 = set(scope["code"]) & placeholder82
    if overlap_82:
        logger.warning("%d scope codes also appear in placeholder_item_assignments_82 (unexpected "
                        "-- that list is for the separate 82-item Phase C population): %s",
                        len(overlap_82), sorted(overlap_82))

    scope = scope.copy()
    scope["is_excluded"] = scope["code"].isin(excluded)
    scope["is_placeholder"] = scope["code"].isin(placeholder)
    scope["eligible_for_policy"] = ~(scope["is_excluded"] | scope["is_placeholder"])

    n_excl = int(scope["is_excluded"].sum())
    n_ph = int(scope["is_placeholder"].sum())
    n_elig = int(scope["eligible_for_policy"].sum())
    logger.info("Scope breakdown: %d total, %d excluded_item_codes, %d placeholder_item_codes, "
                "%d eligible_for_policy (%d + %d + %d = %d).",
                n, n_excl, n_ph, n_elig, n_excl, n_ph, n_elig, n_excl + n_ph + n_elig)
    if n_excl + n_ph + n_elig != n:
        raise ValueError("Excluded + placeholder + eligible does not reconcile to the scope total -- "
                          "an item is flagged both excluded and placeholder, which should not happen.")
    return scope


# ------------------------------------------------------------------------------------------
# Monthly demand series (forecast_date-keyed, the adopted series key)
# ------------------------------------------------------------------------------------------

def load_monthly_series(scope: pd.DataFrame) -> dict:
    """Returns {itemcode: (qty_array[31], months_list[31])} for every scope item PRESENT in the
    forecast_date-keyed monthly file. Also returns the file's snapshot_pull_date and the set of
    scope items absent from the file entirely (i.e. zero history in this project's PEM101 Omni
    Channel Actual+MPS scope -- expected for excluded/most placeholder items).
    """
    df = pd.read_csv(MONTHLY_FILE)
    pull_date = df["snapshot_pull_date"].iloc[0]
    codes_in_file = set(df["itemcode"].unique())
    scope_codes = set(scope["code"])
    present = scope_codes & codes_in_file
    absent = scope_codes - codes_in_file

    series = {}
    for code in present:
        g = df[df["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        months = g["year_month"].astype(str).tolist()
        if len(qty) != TOTAL_MONTHS:
            raise ValueError(f"{code} has {len(qty)} months in the monthly file, expected {TOTAL_MONTHS} -- "
                              f"the monthly file is expected to be a full zero-filled grid per item.")
        series[code] = (qty, months)

    logger.info("Monthly series (forecast_date-keyed, %s): %d of %d scope items present with full "
                "%d-month history; %d scope items have ZERO rows in this file (no PEM101 Omni "
                "Channel Actual/MPS history at all). snapshot_pull_date=%s.",
                MONTHLY_FILE, len(present), len(scope), TOTAL_MONTHS, len(absent), pull_date)
    return {"series": series, "pull_date": pull_date, "absent_codes": sorted(absent)}


def build_type_series(scope: pd.DataFrame, series: dict) -> dict:
    """{type: qty_array[31]} summed ONLY over eligible_for_policy items with history in `series`.
    Placeholder items are excluded from every Type total, per the locked "Placeholder items sit
    outside the Top-down hierarchy entirely" decision (config['placeholder_hierarchy_treatment'])
    -- reused here exactly, not re-decided.
    """
    eligible_codes = set(scope.loc[scope["eligible_for_policy"], "code"])
    type_of = dict(zip(scope["code"], scope["type"]))
    out = {}
    for code, (qty, _months) in series.items():
        if code not in eligible_codes:
            continue
        typ = type_of[code]
        out.setdefault(typ, np.zeros(TOTAL_MONTHS))
        out[typ] = out[typ] + qty
    return out


# ------------------------------------------------------------------------------------------
# Top-down forecast + per-origin share (the verified leakage-free pattern, reused from
# src/item_level_reconciliation.py's "Top-down" branch -- recomputed at each origin/fit_end
# from TRAIN data only, never from full history)
# ------------------------------------------------------------------------------------------

def topdown_item_forecast(scope: pd.DataFrame, series: dict, fit_end: int, horizon: int) -> dict:
    """Returns {itemcode: forecast_array[horizon]} for every eligible item with history, using
    the Top-down method: Type-level Combination forecast fit on qty[:fit_end], allocated to each
    item by that item's OWN qty[:fit_end] share of its Type's qty[:fit_end] total (train-only
    share, recomputed fresh here -- never from full 31-month history). This is the exact pattern
    E0.1 verified leakage-free (src/item_level_reconciliation.py, src/transferability_all_divisions.py).
    """
    eligible_codes = set(scope.loc[scope["eligible_for_policy"], "code"]) & set(series.keys())
    type_of = dict(zip(scope["code"], scope["type"]))

    # Type-level train slice and Type-level Combination forecast, fit_end months only.
    items_by_type = {}
    for code in eligible_codes:
        items_by_type.setdefault(type_of[code], []).append(code)

    type_forecast = {}
    for typ, codes in items_by_type.items():
        type_train = np.zeros(fit_end)
        for code in codes:
            type_train = type_train + series[code][0][:fit_end]
        type_forecast[typ] = np.clip(combination_forecast(type_train, horizon, MA_WINDOWS), 0, None)

    out = {}
    for typ, codes in items_by_type.items():
        totals = {code: series[code][0][:fit_end].sum() for code in codes}
        grand_total = sum(totals.values())
        for code in codes:
            share = totals[code] / grand_total if grand_total > 0 else 1.0 / len(codes)
            out[code] = type_forecast[typ] * share
    return out


# ------------------------------------------------------------------------------------------
# Unit cost (Phase D Check 2 methodology, reused verbatim for consistency across phases)
# ------------------------------------------------------------------------------------------

def query_sale_cost(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"SELECT itemcode, qty, cost, createDate FROM {SALE_TABLE} WHERE itemcode IN ('{code_list}')"
    df = run_query(sql)
    df["createDate"] = pd.to_datetime(df["createDate"])
    logger.info("Pulled %d rows from %s for %d item codes (unit-cost basis).", len(df), SALE_TABLE, len(item_codes))
    return df


def compute_unit_cost(item_codes: list) -> pd.DataFrame:
    """Per item: primary_unit_cost (median of cost/qty over the trailing 12 months, anchored to
    the global max createDate in this pull; falls back to the most-recent transaction's cost/qty
    if no row falls in that 12-month window), and primary_basis stating which was used, or
    'NO_COST_RECORD'. IDENTICAL methodology to output/summary/phaseD_check2_report.md -- reused,
    not re-derived, for consistency across phases.
    """
    raw = query_sale_cost(item_codes)
    df = raw[(raw["qty"].notna()) & (raw["qty"] != 0) & (raw["cost"].notna())].copy()
    df["unit_cost"] = df["cost"] / df["qty"]

    global_max = df["createDate"].max()
    window_start = global_max - pd.DateOffset(months=MEDIAN_WINDOW_MONTHS)

    max_date_per_item = df.groupby("itemcode")["createDate"].transform("max")
    recent = df[df["createDate"] == max_date_per_item].groupby("itemcode", as_index=False).agg(
        most_recent_unit_cost=("unit_cost", "mean"), most_recent_transaction_date=("createDate", "max"))

    in_window = df[df["createDate"] >= window_start]
    median12 = in_window.groupby("itemcode", as_index=False).agg(
        median_unit_cost_12mo=("unit_cost", "median"), n_rows_12mo=("unit_cost", "size"))

    out = pd.DataFrame({"itemcode": sorted(set(item_codes))})
    out = out.merge(recent, on="itemcode", how="left").merge(median12, on="itemcode", how="left")
    has_median = out["median_unit_cost_12mo"].notna()
    has_recent = out["most_recent_unit_cost"].notna()
    out["primary_unit_cost"] = np.where(has_median, out["median_unit_cost_12mo"], out["most_recent_unit_cost"])
    out["primary_basis"] = np.select(
        [has_median, (~has_median) & has_recent],
        ["median_last_12mo", "most_recent_transaction (FALLBACK)"],
        default="NO_COST_RECORD")
    n_no_cost = int((out["primary_basis"] == "NO_COST_RECORD").sum())
    logger.info("Unit cost: %d/%d items priced via median-12mo, %d via most-recent fallback, %d NO_COST_RECORD.",
                int(has_median.sum()), len(out), int(((~has_median) & has_recent).sum()), n_no_cost)
    return out[["itemcode", "primary_unit_cost", "primary_basis", "most_recent_unit_cost", "median_unit_cost_12mo"]]


# ------------------------------------------------------------------------------------------
# Sellable stock (Cube_Inventory_Exact, FG01/FG21/WH21 only -- config assumption) and current
# Min/Max (comparison baseline only, per STATUS.md's locked "cannot be used as inputs" finding)
# ------------------------------------------------------------------------------------------

def query_inventory_exact(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""SELECT company, warehouse, itemcode, stock, minimum, maximum, reserve_bywa, timestamp
              FROM {INV_TABLE} WHERE itemcode IN ('{code_list}')"""
    df = run_query(sql)
    df["warehouse"] = df["warehouse"].str.strip()
    logger.info("Pulled %d rows from %s for %d item codes.", len(df), INV_TABLE, len(item_codes))
    return df


def sellable_stock_per_item(inv: pd.DataFrame, item_codes: list, sellable_warehouses: list) -> pd.DataFrame:
    """Sellable stock = on-hand qty in sellable_warehouses only (config assumption, owner:
    business -- see config.yaml phase_e1_assumptions.sellable_warehouse_codes). Items absent
    from those warehouses get 0, not null (a real absence of stock there, not a missing-data gap)."""
    sub = inv[inv["warehouse"].isin(sellable_warehouses)]
    per_item = sub.groupby("itemcode", as_index=False)["stock"].sum().rename(columns={"stock": "sellable_stock"})
    out = pd.DataFrame({"itemcode": item_codes}).merge(per_item, on="itemcode", how="left")
    out["sellable_stock"] = out["sellable_stock"].fillna(0.0)
    return out


def current_minmax_per_item(inv: pd.DataFrame, item_codes: list) -> pd.DataFrame:
    """Current Min/Max SUMMED across ALL warehouses per item -- same convention as the earlier
    Phase 4 groundwork investigation (src/investigations/investigate_inventory.py,
    'total_minimum'/'total_maximum'). Comparison baseline ONLY (STATUS.md Locked Decisions: the
    existing min/max values cannot be used as calculation INPUTS; using them here only as a
    reported comparison point is exactly what that finding says they ARE good for)."""
    per_item = inv.groupby("itemcode", as_index=False).agg(
        current_total_min=("minimum", "sum"), current_total_max=("maximum", "sum"),
        n_warehouses=("warehouse", "nunique"))
    out = pd.DataFrame({"itemcode": item_codes}).merge(per_item, on="itemcode", how="left")
    out["current_total_min"] = out["current_total_min"].fillna(0.0)
    out["current_total_max"] = out["current_total_max"].fillna(0.0)
    out["n_warehouses"] = out["n_warehouses"].fillna(0).astype(int)
    out["has_current_setting"] = (out["current_total_min"] > 0) | (out["current_total_max"] > 0)
    return out


# ------------------------------------------------------------------------------------------
# Backlog (Cube_Backlog, sale_company IN ('PEM','CI'), no status filter -- same pattern as
# src/build_inventory_dataset.py's query_backlog/aggregate_backlog)
# ------------------------------------------------------------------------------------------

def query_backlog(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""SELECT docID, itemcode, quantity, status, sale_company, deliverydate, plan_deliverydate
              FROM {BACKLOG_TABLE} WHERE itemcode IN ('{code_list}')"""
    df = run_query(sql)
    df["sale_company"] = df["sale_company"].astype(str).str.strip()
    kept = df[df["sale_company"].isin(BACKLOG_SALE_COMPANIES)].copy()
    logger.info("Backlog: pulled %d rows, %d kept after sale_company IN %s.",
                len(df), len(kept), BACKLOG_SALE_COMPANIES)
    kept["effective_date"] = pd.to_datetime(kept["deliverydate"]).fillna(pd.to_datetime(kept["plan_deliverydate"]))
    return kept


# ------------------------------------------------------------------------------------------
# Confirmed future orders (cube_Sale_APD, status='MPS', forecast_date beyond the historical
# monthly series' last month -- by construction these are NOT already counted as history)
# ------------------------------------------------------------------------------------------

def query_confirmed_future_orders(item_codes: list, after_month_end: str) -> pd.DataFrame:
    """Rows with status='MPS' and forecast_date strictly after `after_month_end` (the last
    calendar month already present in the historical monthly series, e.g. '2026-07-31') --
    these cannot already be counted in that series (verified below by the caller), so adding
    them as 'confirmed future demand' does not double-count history."""
    code_list = "','".join(sorted(item_codes))
    sql = f"""SELECT itemcode, forecast_date, qty, status, createDate
              FROM {SALE_TABLE}
              WHERE itemcode IN ('{code_list}') AND status = 'MPS' AND forecast_date > '{after_month_end}'"""
    df = run_query(sql)
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])
    logger.info("Confirmed future MPS orders: %d rows for %d item codes with forecast_date > %s.",
                len(df), len(item_codes), after_month_end)
    return df


# ------------------------------------------------------------------------------------------
# Order-level rows (for order notice = forecast_date - createDate, and order-frequency counts)
# ------------------------------------------------------------------------------------------

def query_order_level(item_codes: list, config: dict) -> pd.DataFrame:
    """One row per cube_Sale_APD order line for the scope items (Omni Channel, Actual+MPS,
    date_range-bounded -- identical filter to this project's whole demand series,
    src/load_data_full.py), with notice_days = forecast_date - createDate computed here.
    Negative/null-forecast_date rows are dropped (same known anomaly class Phase A/B already
    document and exclude from the forecast_date-keyed series)."""
    code_list = "','".join(sorted(item_codes))
    statuses = "','".join(config["status_basis"])
    start_date = config["date_range"]["start"]
    sql = f"""
        SELECT itemcode, contractid, createDate, forecast_date, qty, status
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{config["revenue_type"]}'
          AND status IN ('{statuses}')
          AND createDate >= '{start_date}'
    """
    df = run_query(sql)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    n_before = len(df)
    df = df[df["forecast_date"].notna() & (df["forecast_date"] >= df["createDate"])].copy()
    df["notice_days"] = (df["forecast_date"] - df["createDate"]).dt.days
    logger.info("Order-level pull: %d rows for %d items; %d dropped (null/negative-interval "
                "forecast_date, same anomaly class as the forecast_date-keyed series build); "
                "%d order lines used for notice/frequency analysis.",
                n_before, len(item_codes), n_before - len(df), len(df))
    return df


# ------------------------------------------------------------------------------------------
# MASE with an explicit, non-silent zero-scale handling policy
# ------------------------------------------------------------------------------------------

def mase_with_flag(mae: float, scale_series: np.ndarray) -> tuple:
    """Returns (mase_or_nan, is_undefined: bool). scale = mean absolute first difference of
    scale_series (identical recipe to src/backtest_rekeyed.py compute_metrics) -- undefined
    (NaN, flagged True) when scale_series is all-zero or constant (first-difference all zero)."""
    diffs = np.abs(np.diff(scale_series))
    scale = diffs.mean() if len(diffs) else 0.0
    if scale > 0:
        return mae / scale, False
    return float("nan"), True
