"""Phase I -- decision-sensitivity sweep engine.

Reuses the existing pipeline's division-generic, already-verified functions (imported, not
reimplemented) from src/phaseE1fix_recompute.py and src/phaseE1fix_simulation.py:
  compute_ltd_and_distribution, compute_max_and_stock_value, compute_safety_stock,
  threshold_sensitivity, simulate_item_daily
and from src/phaseE2_pilot_recompute.py / src/phaseE1_common.py:
  load_division_scope, build_monthly_series, build_daily_series, topdown_item_forecast,
  sellable_stock_per_item, current_minmax_per_item, load_scope (PEM101 128-item pilot)

Two functions are reimplemented here, NOT because the originals are wrong, but because the
originals hit the database on every call -- this task's DATABASE ACCESS RULE (one connection
attempt only, already spent by src/investigations/phaseI_single_pull.py) forbids that for a sweep
that calls them dozens of times per division:
  - order_level facts   -- rebuilt from the cached raw pull (identical filter to
                            phaseE1_common.query_order_level: same revenue_type/status/date_range,
                            already applied at pull time).
  - unit_cost            -- rebuilt from the cached raw pull (identical METRICS.md Sec.1 formula
                            to phaseE1fix_recompute.compute_unit_cost_metrics1: median cost/qty
                            over the trailing WINDOW months anchored to the pull's own global max
                            createDate; <3 rows -> most-recent-transaction fallback; 0 rows ->
                            NO_COST_RECORD), parameterized by window_months so it can be swept.
assign_policy_metrics15 is also reimplemented in a parameterized form (freq_cutoff_per_year as an
argument instead of hardcoded 6.0) -- otherwise byte-for-byte the same logic as
phaseE1fix_recompute.assign_policy_metrics15, including the zero-P50 rule.

DATA SOURCE: a single fresh pull, output/data/phaseI_raw_sales_351items.csv +
phaseI_inventory_exact_351items.csv (src/investigations/phaseI_single_pull.py, 2026-09-23),
covering PEM101's 128-item pilot scope, PEM103's 87 items and PEM107's 136 items in ONE connection
attempt. This supersedes the PEM101 frozen file's earlier pull date for THIS analysis only (a
deliberate, stated choice for cross-division consistency within the sensitivity sweep -- it does
not change or overwrite any previously locked Phase E1/E1-fix/E2 figure, which stays on its own
frozen/live-pull basis).
"""
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, load_scope, topdown_item_forecast, sellable_stock_per_item
from phaseE2_pilot_recompute import load_division_scope, build_monthly_series, build_daily_series, TOTAL_MONTHS
from phaseE1fix_recompute import (
    compute_ltd_and_distribution, compute_max_and_stock_value, threshold_sensitivity,
)
from phaseE1fix_simulation import simulate_item_daily

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseI_sensitivity_engine")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
DAYS_PER_MONTH = 30.44
RAW_SALES_FILE = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")
INV_FILE = os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv")

DIVISIONS = ["PEM101", "PEM103", "PEM107"]
FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

DEFAULTS = {
    "procurement_lead_time_days": 60,
    "assembly_time_days": 3,
    "review_interval_days": 30,
    "cycle_service_level": 0.95,
    "unit_cost_window_months": 12,
    "freq_cutoff_per_year": 6.0,
}

RANGES = {
    "procurement_lead_time_days": [30, 45, 60, 75, 90],
    "assembly_time_days": [0, 3, 7, 14],
    "review_interval_days": [7, 14, 30],
    "cycle_service_level": [0.80, 0.85, 0.90, 0.95, 0.98],
    "unit_cost_window_months": [6, 12, 24],
    "freq_cutoff_per_year": [4.0, 6.0, 8.0],
}


# ================================================================================================
# Data loading (from the single cached pull only -- no DB access anywhere below this point)
# ================================================================================================

def load_raw() -> tuple:
    raw = pd.read_csv(RAW_SALES_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    inv = pd.read_csv(INV_FILE)
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    return raw, inv


def get_division_scope(config: dict, division: str) -> pd.DataFrame:
    if division == "PEM101":
        return load_scope(config)
    return load_division_scope(config, division)


def build_order_level(raw_div: pd.DataFrame) -> pd.DataFrame:
    """Same filter/derivation as phaseE1_common.query_order_level, applied to the already-filtered
    cached pull (revenue_type/status/date_range already applied when the pull was made)."""
    df = raw_div.copy()
    n_before = len(df)
    df = df[df["forecast_date"].notna() & (df["forecast_date"] >= df["createDate"])].copy()
    df["notice_days"] = (df["forecast_date"] - df["createDate"]).dt.days
    logger.info("Order-level: %d of %d rows kept (null/negative-interval forecast_date dropped).",
                len(df), n_before)
    return df


def compute_unit_cost_from_raw(raw_div: pd.DataFrame, item_codes: list, window_months: int) -> pd.DataFrame:
    """METRICS.md Sec.1, identical formula to phaseE1fix_recompute.compute_unit_cost_metrics1,
    computed from the cached pull (already Omni Channel / Actual+MPS filtered at pull time)
    instead of a fresh live query -- parameterized by window_months so it can be swept."""
    df = raw_div[(raw_div["qty"].notna()) & (raw_div["qty"] != 0) & (raw_div["cost"].notna())].copy()
    df["unit_cost"] = df["cost"] / df["qty"]

    global_max = df["createDate"].max()
    window_start = global_max - pd.DateOffset(months=window_months)
    in_window = df[df["createDate"] >= window_start]
    n_in_window = in_window.groupby("itemcode").size().rename("n_rows_window")
    median_w = in_window.groupby("itemcode")["unit_cost"].median().rename("median_unit_cost_window")

    max_date_per_item = df.groupby("itemcode")["createDate"].transform("max")
    recent = df[df["createDate"] == max_date_per_item].groupby("itemcode").agg(
        most_recent_unit_cost=("unit_cost", "mean"))

    out = pd.DataFrame({"itemcode": sorted(set(item_codes))}).set_index("itemcode")
    out = out.join(n_in_window).join(median_w).join(recent).reset_index()
    out["n_rows_window"] = out["n_rows_window"].fillna(0).astype(int)

    enough_rows = out["n_rows_window"] >= 3
    has_recent = out["most_recent_unit_cost"].notna()
    out["unit_cost"] = np.where(enough_rows, out["median_unit_cost_window"], out["most_recent_unit_cost"])
    out["unit_cost_fallback"] = (~enough_rows) & has_recent
    out["no_unit_cost_item"] = (~enough_rows) & (~has_recent)
    out["basis"] = np.select(
        [enough_rows, (~enough_rows) & has_recent],
        ["median_12mo_ge3rows", "most_recent_transaction (unit_cost_fallback, <3 rows in window)"],
        default="no_unit_cost_items")
    out = out.rename(columns={"n_rows_window": "n_rows_12mo"})
    return out[["itemcode", "unit_cost", "unit_cost_fallback", "no_unit_cost_item", "basis", "n_rows_12mo"]]


def build_item_facts(scope: pd.DataFrame, monthly_long: pd.DataFrame, order_level: pd.DataFrame,
                      month_max: str) -> pd.DataFrame:
    """METRICS.md Sec.15: annual_value/order_frequency over the trailing 12 months ending at the
    data cutoff (month_max, the fixed window's own last month) -- identical to
    phaseE2_pilot_recompute.build_item_facts, just taking month_max explicitly."""
    data_cutoff_month = pd.Period(month_max, freq="M")
    window_months = pd.period_range(data_cutoff_month - 11, data_cutoff_month, freq="M")
    window_months_str = set(str(m) for m in window_months)
    window_start_date = window_months[0].start_time
    window_end_date = data_cutoff_month.end_time

    sale_12mo = monthly_long[monthly_long["year_month"].isin(window_months_str)].groupby("itemcode")["sale"].sum()

    ol = order_level.copy()
    ol_window = ol[(ol["createDate"] >= window_start_date) & (ol["createDate"] <= window_end_date)]
    freq_12mo = ol_window.drop_duplicates(subset=["itemcode", "contractid", "createDate"]).groupby("itemcode").size()

    rows = []
    for _, r in scope.iterrows():
        code = r["code"]
        annual_value = float(sale_12mo.get(code, 0.0))
        order_freq = float(freq_12mo.get(code, 0))
        rows.append({"code": code, "type": r["type"], "eligible_for_policy": r["eligible_for_policy"],
                     "is_excluded": r["is_excluded"], "is_placeholder": r["is_placeholder"], "has_history": True,
                     "annual_value_thb": annual_value, "order_freq_per_year": order_freq})
    return pd.DataFrame(rows)


def assign_policy_param(facts: pd.DataFrame, assembly_time_days: float, median_notice_days: float,
                         freq_cutoff_per_year: float) -> tuple:
    """Byte-for-byte phaseE1fix_recompute.assign_policy_metrics15, with freq_cutoff_per_year as a
    parameter instead of the hardcoded 6.0 -- needed to sweep the segment frequency threshold."""
    elig = facts[facts["eligible_for_policy"]].copy()
    p50_value = float(elig["annual_value_thb"].median())
    zero_p50_rule_used = p50_value == 0.0
    p50_nonzero_informational = (
        float(elig.loc[elig["annual_value_thb"] > 0, "annual_value_thb"].median())
        if (elig["annual_value_thb"] > 0).any() else None
    )

    def policy(row):
        if row["is_excluded"]:
            return "excluded"
        if row["is_placeholder"]:
            return "placeholder"
        if zero_p50_rule_used:
            fg = row["order_freq_per_year"] >= freq_cutoff_per_year
        else:
            fg = (row["annual_value_thb"] >= p50_value) or (row["order_freq_per_year"] >= freq_cutoff_per_year)
        if fg:
            return "finished_goods_stock"
        if assembly_time_days <= median_notice_days:
            return "component_stock_ato"
        return "UNDEFINED_BY_METRICS_MD_SEC15"

    facts = facts.copy()
    facts["policy"] = facts.apply(policy, axis=1)
    facts["p50_annual_value_thb"] = p50_value
    facts["freq_cutoff_per_year"] = freq_cutoff_per_year
    facts["zero_p50_rule_used"] = zero_p50_rule_used
    return facts, {"p50_annual_value_thb": p50_value, "freq_cutoff_per_year": freq_cutoff_per_year,
                   "assembly_time_days_used": assembly_time_days, "median_notice_days_used": median_notice_days,
                   "zero_p50_rule_used": zero_p50_rule_used,
                   "p50_nonzero_informational_thb": p50_nonzero_informational}


def current_stockholding_warehouses(inv_div: pd.DataFrame, exclude=("QA", "FMTO", "FMTS")) -> list:
    holding = inv_div.loc[inv_div["stock"] > 0, "warehouse"].unique().tolist()
    return sorted(set(holding) - set(exclude))


def fg_prefixed_warehouses(all_warehouse_codes: list) -> list:
    return sorted(w for w in set(all_warehouse_codes) if w.upper().startswith("FG"))


# ================================================================================================
# Per-division data bundle (built once; every scenario below is recomputed from this in memory)
# ================================================================================================

def build_division_bundle(config: dict, division: str, raw: pd.DataFrame, inv: pd.DataFrame) -> dict:
    scope = get_division_scope(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)].copy()
    inv_div = inv[inv["itemcode"].isin(codes)].copy()

    series_bundle = build_monthly_series(raw_div, codes)
    daily_series = build_daily_series(raw_div, codes)
    order_level = build_order_level(raw_div)
    median_notice_days = float(order_level["notice_days"].median())

    month_max = series_bundle["series"][codes[0]][1][-1]
    base_facts = build_item_facts(scope, series_bundle["monthly_long"], order_level, month_max)

    all_wh_codes = sorted(inv["warehouse"].unique().tolist())
    e1 = config["phase_e1_assumptions"]
    current_sellable = e1["sellable_warehouse_codes"].get(division)
    variant_fg = fg_prefixed_warehouses(all_wh_codes)
    variant_allstock = current_stockholding_warehouses(inv_div)

    logger.info("[%s] %d codes, %d with any daily history rows, median_notice_days=%.2f, "
                "sellable variants: current=%s, FG-only=%s, all-stock-except-QA/FMTO/FMTS=%s",
                division, len(codes), sum(1 for c in codes if daily_series[c][0].sum() > 0),
                median_notice_days, current_sellable, variant_fg, variant_allstock)

    return {
        "division": division, "scope": scope, "codes": codes, "raw_div": raw_div, "inv_div": inv_div,
        "series_bundle": series_bundle, "daily_series": daily_series, "order_level": order_level,
        "median_notice_days": median_notice_days, "base_facts": base_facts, "month_max": month_max,
        "sellable_variants": {
            "current": current_sellable,
            "fg_prefixed_only": variant_fg,
            "all_stockholding_except_qa_fmto_fmts": variant_allstock,
        },
    }


# ================================================================================================
# One scenario run
# ================================================================================================

def run_scenario(bundle: dict, procurement_lead_time_days: float, assembly_time_days: float,
                  review_interval_days: float, cycle_service_level: float,
                  unit_cost_window_months: int, freq_cutoff_per_year: float,
                  sellable_warehouses: list = None) -> dict:
    scope, series_bundle, daily_series = bundle["scope"], bundle["series_bundle"], bundle["daily_series"]
    codes, raw_div, inv_div = bundle["codes"], bundle["raw_div"], bundle["inv_div"]
    median_notice_days = bundle["median_notice_days"]

    facts, thresholds = assign_policy_param(bundle["base_facts"], assembly_time_days, median_notice_days,
                                             freq_cutoff_per_year)

    protection_days = procurement_lead_time_days + assembly_time_days + review_interval_days
    months_float = protection_days / DAYS_PER_MONTH
    full_months = int(math.floor(months_float))
    frac_month = months_float - full_months

    ltd_input = facts[facts["policy"].isin(["finished_goods_stock", "component_stock_ato"])]
    ltd_df = compute_ltd_and_distribution(scope, series_bundle, ltd_input, full_months, frac_month,
                                           cycle_service_level, daily_series, protection_days)
    unit_cost_df = compute_unit_cost_from_raw(raw_div, codes, unit_cost_window_months).rename(
        columns={"itemcode": "code"})
    unit_cost_df = unit_cost_df.rename(columns={"code": "itemcode"})
    full_df = compute_max_and_stock_value(ltd_df, scope, series_bundle, facts, unit_cost_df,
                                           review_interval_days)

    fg_codes = set(facts[facts["policy"] == "finished_goods_stock"]["code"])
    stock_value = float(full_df.loc[full_df["code"].isin(fg_codes), "stock_value_contribution"].sum())

    if sellable_warehouses is None:
        sellable_warehouses = bundle["sellable_variants"]["current"]
    sellable = sellable_stock_per_item(inv_div, codes, sellable_warehouses)

    # ---- Section 16 simulation, fill_rate / cycle_service_level ----
    lead_time_days = procurement_lead_time_days + assembly_time_days
    sim_rows = []
    for _, r in full_df[full_df["code"].isin(fg_codes)].iterrows():
        code = r["code"]
        if pd.isna(r["min_qty"]) or pd.isna(r["max_qty"]) or code not in daily_series:
            continue
        qty_daily, _ = daily_series[code]
        sim = simulate_item_daily(qty_daily, r["min_qty"], r["max_qty"],
                                   int(round(review_interval_days)), int(round(lead_time_days)))
        sim["code"] = code
        sim_rows.append(sim)
    sim_df = pd.DataFrame(sim_rows)
    if len(sim_df) and sim_df["total_demand"].sum() > 0:
        fill_rate = float(sim_df["total_shipped_same_day"].sum() / sim_df["total_demand"].sum())
        csl = float(1 - sim_df["cycle_stockouts"].sum() / sim_df["cycle_count"].sum())
    else:
        fill_rate, csl = float("nan"), float("nan")

    min_by_code = full_df.set_index("code")["min_qty"].to_dict()
    policy_by_code = facts.set_index("code")["policy"].to_dict()

    return {
        "facts": facts, "thresholds": thresholds, "full_df": full_df, "unit_cost_df": unit_cost_df,
        "stock_value": stock_value, "fill_rate": fill_rate, "cycle_service_level": csl,
        "fg_codes": fg_codes, "min_by_code": min_by_code, "policy_by_code": policy_by_code,
        "sellable": sellable, "n_items_simulated": len(sim_df), "sim_df": sim_df,
        "params": {"procurement_lead_time_days": procurement_lead_time_days,
                   "assembly_time_days": assembly_time_days, "review_interval_days": review_interval_days,
                   "cycle_service_level": cycle_service_level, "unit_cost_window_months": unit_cost_window_months,
                   "freq_cutoff_per_year": freq_cutoff_per_year,
                   "sellable_warehouses": sellable_warehouses},
    }


def default_scenario(bundle: dict) -> dict:
    return run_scenario(bundle, **DEFAULTS)
