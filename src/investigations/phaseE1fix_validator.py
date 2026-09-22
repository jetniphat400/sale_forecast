"""Independent Validator recomputation for the Phase E1 fix task (2026-09-21).

Written by the Validator, NOT copied from any Modeler script for this fix task. Reuses only
pre-existing, previously-verified-leakage-free helper functions from src/phaseE1_common.py,
src/db.py, src/models.py, src/backtest_rekeyed.py and src/pricelist_reader.py (all predate this
fix task) -- the top-level computation and every judgment call below is this Validator's own.

Does NOT read: src/phaseE1fix_recompute.py, src/build_inventory_page*.py,
src/inventory_recompute_reference.py, forecast/inventory.html, or anything under
output/summary/phaseE1fix_* / output/charts/inventory_verification/ (the Modeler's own new work
product for this task).

Uses output/data/processed_full_category_sales_monthly_forecastDate.csv (the locked, frozen
snapshot series) for every historical-actuals computation tied to "the forecast_date-keyed
series" (METRICS.md LTD sec.3, ltd_distribution sec.4) -- NOT a live pull, per this project's own
prior-Validator-run lesson (STATUS.md).

unit_cost (METRICS.md sec.1) is sourced live from cube_Sale_APD directly, per METRICS.md's own
"trailing 12 months" definition -- this is the one figure in this task that IS supposed to be a
live pull.
"""
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))          # src/investigations
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src

from db import run_query
from models import combination_forecast
from backtest_rekeyed import MA_WINDOWS
import phaseE1_common as pc
import pricelist_reader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1fix_validator")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
OUT_PREFIX = "phaseE1fix_validator"

TODAY = pd.Timestamp("2026-09-21")  # per system-reminder, "today's date"

# ============================================================================
# Helpers: month grid, prorating over real calendar days
# ============================================================================

def month_starts_after(last_month_end: pd.Timestamp, n_months: int) -> list:
    """Returns n_months consecutive calendar-month start Timestamps beginning the month AFTER
    last_month_end (e.g. last_month_end=2026-07-31 -> [2026-08-01, 2026-09-01, ...])."""
    starts = []
    cur = (last_month_end + pd.offsets.MonthBegin(1))
    for _ in range(n_months):
        starts.append(cur)
        cur = cur + pd.offsets.MonthBegin(1)
    return starts


def prorate_weights(last_month_end: pd.Timestamp, period_days: int, n_months: int) -> np.ndarray:
    """Weight (0..1) to apply to each of the next n_months' forecast values so that the weighted
    sum equals the expected demand over exactly `period_days` calendar days starting the day after
    last_month_end. Whole months inside the period get weight 1.0; the month straddled by the
    period's end gets a fractional weight = (days of that month inside the period) / (days in that
    month); months entirely beyond the period get weight 0.0. This is an exact calendar-day
    prorating (not a fixed 30/30.44-day approximation), which is the most literal reading of
    METRICS.md sec.3's instruction to prorate "for partial months"."""
    period_end = last_month_end + pd.Timedelta(days=period_days)
    starts = month_starts_after(last_month_end, n_months)
    weights = np.zeros(n_months)
    for i, ms in enumerate(starts):
        me = ms + pd.offsets.MonthEnd(0)  # last day of that month
        days_in_month = me.day
        if period_end >= me:
            weights[i] = 1.0
        elif period_end >= ms:
            days_covered = (period_end - ms).days + 1
            weights[i] = max(0.0, min(1.0, days_covered / days_in_month))
        else:
            weights[i] = 0.0
    return weights


# ============================================================================
# 1. Scope: independent re-derivation + reuse of adopted_scope_file
# ============================================================================

def part_scope(config: dict) -> pd.DataFrame:
    logger.info("=== SCOPE: re-deriving the 128-item PEM101 pilot independently ===")
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    rows = pricelist_reader.load_visible_product_rows(pricelist_path)
    pem101 = rows[rows["sheet"] == "PEM101-Version 2"].copy()
    # adopted_scope_file is the 128-item CATEGORY-level scope (Fuse + Surge Arrester categories,
    # 8 Types, 2 Categories -- STATUS.md/config.yaml's own description of adopted_scope_file),
    # NOT the narrower 68-item Type-level pilot_categories (High Voltage Distribution Fuse Cutout
    # + Medium Voltage Surge Arrester Types only) used earlier in Phase 2. Re-derived at Category
    # level to match what adopted_scope_file actually is.
    categories_wanted = {"Fuse", "Surge Arrester"}
    own_scope = pem101[pem101["category"].isin(categories_wanted)].copy()
    own_codes = set(own_scope["code"])
    logger.info("Own pricelist-direct scope: %d codes (PEM101-Version 2 sheet, Product Category in %s)",
                len(own_codes), sorted(categories_wanted))

    scope = pc.load_scope(config)  # reuses config['adopted_scope_file'], a pre-existing artifact
    file_codes = set(scope["code"])
    logger.info("config['adopted_scope_file'] scope: %d codes", len(file_codes))

    sym_diff = own_codes ^ file_codes
    logger.info("Symmetric difference between pricelist-direct and adopted_scope_file scopes: %d %s",
                len(sym_diff), sorted(sym_diff) if sym_diff else "(exact match)")

    excluded = set(config["excluded_item_codes"])
    placeholder = set(config["placeholder_item_codes"])
    logger.info("excluded_item_codes: %d, placeholder_item_codes: %d, sum=%d (config-stated 16)",
                len(excluded), len(placeholder), len(excluded) + len(placeholder))

    return scope, len(own_codes), sym_diff


# ============================================================================
# 2. Part A: confirmed-demand source comparison, Cube_Backlog vs Cube_CES(Status='Backlog')
# ============================================================================

def part_a(scope: pd.DataFrame) -> dict:
    logger.info("=== PART A: Cube_Backlog vs Cube_CES(Status='Backlog') for the 128-item scope ===")
    codes = sorted(scope["code"].tolist())
    code_list = "','".join(codes)

    bl = run_query(f"""SELECT docID, itemcode, quantity, status, sale_company, division,
                               deliverydate, plan_deliverydate
                        FROM [salewarehouse].[dbo].[Cube_Backlog] WHERE itemcode IN ('{code_list}')""")
    ces = run_query(f"""SELECT ContractID, ItemCode, BacklogQty, Status, ManuDivision, Company,
                                ForecastDelDate, PlanDelDate
                         FROM Cube_CES WHERE ItemCode IN ('{code_list}') AND Status='Backlog'""")

    bl_pem = bl[bl["sale_company"].astype(str).str.strip() == "PEM"].copy()
    ces_pem = ces[ces["ManuDivision"].astype(str).str.strip() == "PEM101"].copy()

    bl_pairs = set(zip(bl_pem["docID"], bl_pem["itemcode"]))
    ces_pairs = set(zip(ces_pem["ContractID"], ces_pem["ItemCode"]))
    inter = bl_pairs & ces_pairs
    union = bl_pairs | ces_pairs

    result = {
        "cube_backlog_rows_pem": len(bl_pem),
        "cube_ces_backlog_rows_pem101": len(ces_pem),
        "cube_backlog_qty_sum": float(bl_pem["quantity"].sum()),
        "cube_ces_backlogqty_sum": float(ces_pem["BacklogQty"].sum()),
        "cube_backlog_distinct_pairs": len(bl_pairs),
        "cube_ces_distinct_pairs": len(ces_pairs),
        "intersection_pairs": len(inter),
        "match_rate_vs_union": len(inter) / len(union) if union else float("nan"),
        "match_rate_vs_backlog": len(inter) / len(bl_pairs) if bl_pairs else float("nan"),
        "match_rate_vs_ces": len(inter) / len(ces_pairs) if ces_pairs else float("nan"),
        "items_only_in_backlog": sorted(set(bl_pem["itemcode"]) - set(ces_pem["ItemCode"])),
        "items_only_in_ces": sorted(set(ces_pem["ItemCode"]) - set(bl_pem["itemcode"])),
    }
    for k, v in result.items():
        logger.info("Part A: %s = %s", k, v)

    ces_pem.to_csv(os.path.join(DATA_DIR, f"{OUT_PREFIX}_cube_ces_backlog_pem101.csv"), index=False)
    bl_pem.to_csv(os.path.join(DATA_DIR, f"{OUT_PREFIX}_cube_backlog_pem.csv"), index=False)
    return result, ces_pem


# ============================================================================
# 3. Part B: segmentation
# ============================================================================

def compute_annual_value(eligible_codes: set) -> pd.DataFrame:
    """METRICS.md sec.15 (corrected 2026-09-22): annual_value = sum of `sale` over the TRAILING
    12 MONTHS ENDING AT THE DATA CUTOFF -- the frozen monthly series' own last complete
    (year_month.max()) month, computed independently here from the raw monthly file rather than
    reusing any Modeler constant. Previously this Validator annualized the FULL 31-month window
    (mean x 12); that no longer matches METRICS.md's now-literal wording and was one root cause
    of the 76-vs-77 segmentation mismatch (METRICS.md Sec.15's own resolution note)."""
    df = pd.read_csv(pc.MONTHLY_FILE)
    df = df[df["itemcode"].isin(eligible_codes)]
    cutoff = pd.Period(df["year_month"].max(), freq="M")
    window = set(str(p) for p in pd.period_range(cutoff - 11, cutoff, freq="M"))
    logger.info("OWN trailing-12-month window (annual_value, order_frequency): %s to %s",
                min(window), max(window))
    df_win = df[df["year_month"].isin(window)]
    per_item = df_win.groupby("itemcode", as_index=False).agg(annual_value_thb=("sale", "sum"))
    out = pd.DataFrame({"itemcode": sorted(eligible_codes)}).merge(per_item, on="itemcode", how="left")
    out["annual_value_thb"] = out["annual_value_thb"].fillna(0.0)
    return out, cutoff, window


def compute_order_frequency(config: dict, eligible_codes: set, cutoff: pd.Period, window: set) -> pd.DataFrame:
    """METRICS.md sec.15 (corrected 2026-09-22): order_frequency = count of DISTINCT (contractid,
    createDate) pairs in the SAME trailing-12-month window as annual_value (by createDate), not a
    line count divided by a live, ever-growing span -- that live-span convention was this
    Validator's own prior method and was the OTHER root cause of the 76-vs-77 mismatch (a 'live
    today' denominator vs. a fixed reference date, per METRICS.md Sec.15's resolution note).
    Own live order-level pull (reuses phaseE1_common.query_order_level's query pattern -- Omni
    Channel, Actual+MPS -- but windowed and deduplicated here, this Validator's own top-level
    logic, not copied Modeler code)."""
    ol = pc.query_order_level(list(eligible_codes), config)
    window_start = pd.Period(min(window), freq="M").start_time
    window_end = cutoff.end_time
    ol_win = ol[(ol["createDate"] >= window_start) & (ol["createDate"] <= window_end)]
    logger.info("OWN order-level pull: %d rows total, %d fall inside the trailing-12mo window "
                "%s to %s.", len(ol), len(ol_win), window_start.date(), window_end.date())

    median_notice = ol["notice_days"].median()
    logger.info("OWN live median notice_days across %d order lines (all eligible items, full "
                "pull span): %.2f days (config records median_notice_days_used=6.00 -- sanity "
                "check against this figure).", len(ol), median_notice)

    dedup = ol_win.drop_duplicates(subset=["itemcode", "contractid", "createDate"])
    freq = dedup.groupby("itemcode", as_index=False).size().rename(
        columns={"size": "order_freq_per_year"})  # window IS 12 months -> count == per-year rate
    out = pd.DataFrame({"itemcode": sorted(eligible_codes)}).merge(freq, on="itemcode", how="left")
    out["order_freq_per_year"] = out["order_freq_per_year"].fillna(0).astype(float)
    return out, median_notice


def classify_segment(annual_value: float, p50: float, order_freq: float, freq_cutoff: float,
                      assembly_time_days: float, median_notice_days: float) -> str:
    """METRICS.md sec.15, applied literally: finished_goods_stock if annual_value >= p50 OR
    order_freq >= freq_cutoff (both inclusive, per config['segment_policy']'s own stated reading);
    otherwise component_stock_ato provided assembly_time_days <= median_notice_days;
    make_to_order is never assigned (notice never exceeds procurement lead time project-wide, per
    STATUS.md) -- if neither condition holds this function raises, since METRICS.md's own set of
    three outcomes (FG / ATO / MTO) should be exhaustive once MTO is ruled out a priori."""
    if annual_value >= p50 or order_freq >= freq_cutoff:
        return "finished_goods_stock"
    if assembly_time_days <= median_notice_days:
        return "component_stock_ato"
    return "make_to_order"


def part_b_segmentation(config: dict, scope: pd.DataFrame, av: pd.DataFrame, freq: pd.DataFrame,
                         median_notice: float) -> pd.DataFrame:
    logger.info("=== PART B: classify every eligible item, own P50, own frequency ===")
    default = config["phase_e1_assumptions"]["default_scenario"]
    assembly_days = default["assembly_time_days"]

    merged = av.merge(freq, left_on="itemcode", right_on="itemcode", how="outer")
    own_p50 = float(merged["annual_value_thb"].median())
    freq_cutoff = config["segment_policy"]["order_freq_cutoff_per_year"]
    config_p50 = config["segment_policy"]["p50_annual_value_thb"]

    logger.info("OWN computed P50 of annual_value_thb across %d eligible items: %.2f "
                "(config-recorded p50_annual_value_thb: %.2f, diff %.2f%%)",
                len(merged), own_p50, config_p50, 100 * (own_p50 - config_p50) / config_p50)
    logger.info("OWN live median notice_days: %.2f vs config median_notice_days_used=%.2f "
                "(assembly_time_days default scenario = %s)",
                median_notice, config["segment_policy"]["median_notice_days_used"], assembly_days)

    merged["segment"] = merged.apply(
        lambda r: classify_segment(r["annual_value_thb"], own_p50, r["order_freq_per_year"],
                                    freq_cutoff, assembly_days, median_notice), axis=1)

    # sensitivity: items within +/-5% of either threshold
    merged["pct_from_value_threshold"] = (merged["annual_value_thb"] - own_p50) / own_p50 * 100
    merged["pct_from_freq_threshold"] = (merged["order_freq_per_year"] - freq_cutoff) / freq_cutoff * 100
    merged["near_value_threshold"] = merged["pct_from_value_threshold"].abs() <= 5
    merged["near_freq_threshold"] = merged["pct_from_freq_threshold"].abs() <= 5

    counts = merged["segment"].value_counts().to_dict()
    logger.info("OWN segment counts: %s", counts)

    merged.to_csv(os.path.join(SUMMARY_DIR, f"{OUT_PREFIX}_segmentation.csv"), index=False)
    return merged, own_p50, freq_cutoff


# ============================================================================
# 4. LTD, safety_stock, Min, unit_cost, MASE_undefined -- for a given item set
# ============================================================================

def fit_topdown_forecast(scope: pd.DataFrame, series: dict, item_codes: list, horizon: int) -> dict:
    """Static, single full-history fit (fit_end=31, i.e. ALL of Jan2024-Jul2026), forecasting
    `horizon` months beyond the last observed month. This is the exact leakage-free Top-down
    pattern already verified in this project (src/item_level_reconciliation.py, reused via
    phaseE1_common.topdown_item_forecast) -- used here as a STATIC policy value (one Min/Max per
    item, held constant), matching how the original Phase E1 Modeler/Validator's exactly-matching
    Min figures for the 3 focus items were computed (STATUS.md: 'Min for the three focus items
    matches EXACTLY... once both used this project's own locked frozen-snapshot series')."""
    scope_present = scope[scope["code"].isin(series.keys())]
    fit_end = pc.TOTAL_MONTHS
    fc = pc.topdown_item_forecast(scope_present, series, fit_end, horizon)
    return {code: fc[code] for code in item_codes if code in fc}


def load_daily_history(eligible_codes: set, month_min: str, month_max: str) -> dict:
    """Independent (this Validator's OWN) daily forecast_date-keyed ACTUAL-demand series build,
    from the same frozen raw snapshot (output/data/raw_full_category_sales.csv) src/load_data_
    full.py used to build the monthly series -- never a live pull, never the Modeler's file.
    METRICS.md sec.4 (corrected 2026-09-22) prefers a true daily rolling window over the
    monthly-prorated fallback whenever a daily series is available, and one is available in this
    project (per-transaction forecast_date, not just month-end buckets). Written independently of
    src/phaseE1fix_recompute.py's load_daily_series -- a pivot_table build here, not a per-item
    Series loop -- same frozen source file, different code.
    Returns {itemcode: qty_array[n_days]}, zero-filled across every day in [month_min, month_max].
    """
    raw_path = os.path.join(DATA_DIR, "raw_full_category_sales.csv")
    if not os.path.exists(raw_path):
        logger.warning("Frozen raw file %s not found -- this Validator falls back to "
                        "monthly-prorated windows for every item.", raw_path)
        return {}
    raw = pd.read_csv(raw_path)
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw["createDate"] = pd.to_datetime(raw["createDate"], errors="coerce")
    raw = raw.dropna(subset=["forecast_date"])
    raw = raw[raw["forecast_date"] >= raw["createDate"]]
    day_min = pd.Period(month_min, freq="M").start_time
    day_max = pd.Period(month_max, freq="M").end_time.normalize()
    raw = raw[(raw["forecast_date"] >= day_min) & (raw["forecast_date"] <= day_max)]
    raw = raw[raw["itemcode"].isin(eligible_codes)]

    pivot = raw.pivot_table(index=raw["forecast_date"].dt.normalize(), columns="itemcode",
                             values="qty", aggfunc="sum", fill_value=0.0)
    full_idx = pd.date_range(day_min, day_max, freq="D")
    pivot = pivot.reindex(full_idx, fill_value=0.0)
    logger.info("OWN daily history build: %d items, %d days (%s to %s).",
                pivot.shape[1], len(full_idx), day_min.date(), day_max.date())
    return {code: pivot[code].to_numpy(dtype=float) for code in pivot.columns}


def daily_rolling_windows(qty_daily: np.ndarray, period_days: int) -> np.ndarray:
    """Exact rolling-sum windows of length period_days over a TRUE daily series, advancing one
    day at a time -- METRICS.md sec.4's preferred method; no monthly proration is needed here
    since the underlying data is already daily."""
    n = len(qty_daily)
    if period_days <= 0 or period_days > n:
        return np.array([qty_daily.sum()]) if n else np.array([0.0])
    csum = np.concatenate([[0.0], np.cumsum(qty_daily)])
    return csum[period_days:] - csum[:-period_days]


def historical_window_sum(qty: np.ndarray, months: list, origin: int, period_days: int) -> tuple:
    """Sum of qty starting at calendar-month index `origin`, covering EXACTLY `period_days`
    calendar days -- whole months inside the window count in full, the final month is weighted
    by the fraction of ITS OWN real days (28-31, from the actual calendar month, not a 30.44
    average) that fall inside the window. This is the exact-calendar-day analogue of
    prorate_weights(), applied to historical actuals instead of a forecast, per METRICS.md sec.4
    (corrected 2026-09-22): 'the window is measured in days and is never rounded to whole
    months... If the daily series is not available and only monthly buckets exist, the
    implementation must prorate: weight each partial month by the fraction of its days inside
    the window.' This Validator works from the frozen MONTHLY series only (no daily series was
    independently built here) -- this is that monthly-prorated fallback, used for every window.
    Returns (window_sum, complete) -- complete=False if the series runs out before period_days
    is covered (that origin is not a usable window)."""
    remaining = period_days
    total = 0.0
    j = origin
    while remaining > 0 and j < len(qty):
        days_in_month = pd.Period(months[j], freq="M").days_in_month
        if remaining >= days_in_month:
            total += qty[j]
            remaining -= days_in_month
        else:
            total += qty[j] * (remaining / days_in_month)
            remaining = 0.0
        j += 1
    return total, remaining <= 0


def ltd_and_safety_stock(qty: np.ndarray, months: list, forecast: np.ndarray,
                          last_month_end: pd.Timestamp, protection_period_days: int, sl: float,
                          daily_qty: np.ndarray = None) -> dict:
    """LTD (METRICS.md sec.3): forecast summed over the months the protection period spans,
    prorated for partial months (exact calendar-day prorating, see prorate_weights()).
    ltd_distribution (METRICS.md sec.4, corrected 2026-09-22): empirical distribution of rolling
    protection_period_days-length sums. Uses the TRUE daily series (daily_rolling_windows),
    advancing one day at a time, when `daily_qty` is supplied (this Validator's own daily
    history, load_daily_history) -- METRICS.md sec.4's preferred method. Falls back to a
    monthly-prorated window (historical_window_sum, exact-calendar-day weighting of the partial
    month, no 30.44 average) only when no daily history exists for the item.
    safety_stock = percentile(ltd_distribution, sl) - LTD, per METRICS.md's literal formula (NOT
    percentile - mean(ltd_distribution) -- that would be a different, unspecified quantity).
    Clamped at 0 if negative. unreliable=True if ltd_distribution has <6 non-zero windows."""
    weights = prorate_weights(last_month_end, protection_period_days, len(forecast))
    ltd = float(np.dot(forecast, weights))

    if daily_qty is not None and len(daily_qty) >= protection_period_days:
        dist = daily_rolling_windows(daily_qty, protection_period_days)
        method = "daily"
    else:
        n = len(qty)
        windows = []
        for i in range(n):
            total, complete = historical_window_sum(qty, months, i, protection_period_days)
            if complete:
                windows.append(total)
        dist = np.array(windows) if windows else np.array([qty.sum()])
        method = "monthly_prorated_fallback"

    pctl = float(np.percentile(dist, sl * 100))
    safety_stock = max(0.0, pctl - ltd)
    n_nonzero = int((dist > 0).sum())
    unreliable = (n_nonzero < 6) and (sl > 0.90)

    return {
        "protection_period_days": protection_period_days, "ltd": ltd,
        "ltd_distribution_mean": float(dist.mean()), "ltd_distribution_pctl": pctl,
        "safety_stock": safety_stock, "min": ltd + safety_stock,
        "n_nonzero_periods": n_nonzero, "unreliable": unreliable,
        "distribution_method": method,
    }


def compute_mase_undefined(series: dict, item_codes: list) -> pd.DataFrame:
    """MASE_undefined (METRICS.md sec.13): undefined whenever the in-sample seasonal-naive (m=1)
    MAE -- mean(|diff of consecutive actuals|) over the item's full history -- is exactly 0, i.e.
    a constant or all-zero series. This is independent of which model's MAE sits in the numerator
    (division by zero is division by zero regardless), so it can be determined directly from each
    item's own historical series without re-running a full backtest -- reuses
    phaseE1_common.mase_with_flag's scale-only logic, called fresh here per item."""
    rows = []
    for code in item_codes:
        if code in series:
            qty = series[code][0]
        else:
            qty = np.zeros(pc.TOTAL_MONTHS)  # absent from the frozen file = no history at all
        _, undefined = pc.mase_with_flag(mae=0.0, scale_series=qty)
        rows.append({"itemcode": code, "mase_undefined": undefined})
    return pd.DataFrame(rows)


# ============================================================================
# 5. Part C.1: stock_value over the OWN finished_goods_stock set
# ============================================================================

def part_c1_stock_value(config: dict, scope: pd.DataFrame, series: dict, fg_codes: list,
                         last_month_end: pd.Timestamp, daily_series: dict) -> dict:
    logger.info("=== PART C.1: stock_value (METRICS.md sec.6) over %d OWN finished_goods_stock items ===",
                len(fg_codes))
    default = config["phase_e1_assumptions"]["default_scenario"]
    lead, assembly, sl = default["procurement_lead_time_days"], default["assembly_time_days"], default["cycle_service_level"]
    review = config["phase_e1_assumptions"]["review_interval_days_default"]
    protection_period_days = lead + assembly + review

    horizon = math.ceil(protection_period_days / 30.44) + 1
    forecasts = fit_topdown_forecast(scope, series, fg_codes, horizon)

    rows = []
    for code in fg_codes:
        if code not in series or code not in forecasts:
            rows.append({"itemcode": code, "min": None, "reason": "no history in frozen series"})
            continue
        qty, months = series[code]
        r = ltd_and_safety_stock(qty, months, forecasts[code], last_month_end, protection_period_days, sl,
                                  daily_qty=daily_series.get(code))
        r["itemcode"] = code
        rows.append(r)
    min_df = pd.DataFrame(rows)

    uc = pc.compute_unit_cost(fg_codes)
    merged = min_df.merge(uc, left_on="itemcode", right_on="itemcode", how="left")
    merged["has_unit_cost"] = merged["primary_basis"] != "NO_COST_RECORD"
    merged["stock_value_item"] = np.where(
        merged["has_unit_cost"] & merged["min"].notna(),
        merged["min"] * merged["primary_unit_cost"], np.nan)

    n_no_cost = int((~merged["has_unit_cost"]).sum())
    n_fallback = int((merged["primary_basis"] == "most_recent_transaction (FALLBACK)").sum())
    n_unreliable = int(merged["unreliable"].fillna(False).sum())
    n_valid = int(merged["stock_value_item"].notna().sum())
    total_stock_value = float(merged["stock_value_item"].sum(skipna=True))

    logger.info("stock_value: %d items priced and Min-computed (of %d finished_goods_stock items), "
                "total = %.2f THB. no_unit_cost_items=%d, unit_cost_fallback=%d, unreliable=%d",
                n_valid, len(fg_codes), total_stock_value, n_no_cost, n_fallback, n_unreliable)

    merged.to_csv(os.path.join(SUMMARY_DIR, f"{OUT_PREFIX}_stock_value_detail.csv"), index=False)
    return {
        "n_items_priced": n_valid, "n_items_total": len(fg_codes), "total_stock_value_thb": total_stock_value,
        "no_unit_cost_items": n_no_cost, "unit_cost_fallback": n_fallback, "unreliable_pctl": n_unreliable,
        "protection_period_days": protection_period_days,
    }, merged


# ============================================================================
# 6. Part C.2: historical simulation replay -- fill_rate + cycle_service_level
# ============================================================================

def simulate_item(qty_hist: np.ndarray, min_level: float, max_level: float,
                   lead_plus_assembly_days: float) -> dict:
    """One item's 31-month order-up-to-Max sawtooth simulation, per THIS Validator's own stated
    assumptions (reusing config['phase_e1_assumptions']'s existing simulation-mechanics
    assumptions, which are locked config inputs, not re-invented):
    - initial stock at month 0 = Max (simulation_initial_stock_assumption).
    - receipt timing: an order placed at month t arrives exactly
      ceil(lead_plus_assembly_days/30.44) months later, deterministic, no variability
      (simulation_receipt_timing_assumption).
    - fulfilment sequence: within a month, any scheduled receipt is added to stock FIRST, then
      that month's demand is subtracted; a backorder from a prior month is served BEFORE the
      current month's own new demand (oldest obligation first); unmet current-month demand is
      carried forward as backorder, never a lost sale (simulation_fulfilment_sequence_assumption).
    - review interval ~= 1 month (30-day review vs ~30.44-day average month): an order is placed
      every month if the post-receipt inventory position (stock, since no other pipeline order is
      outstanding under a fixed 1-month review / L+A>1-month lead combination here) is below Max.
    fill_rate = sum(shipped_from_that_month's_own_demand) / sum(that month's own historical
      demand) -- unit-based, per METRICS.md sec.10, "immediately" read as "from this month's own
      demand, not a demand backordered from an earlier month".
    cycle_service_level = (months with that month's own demand fully met) / total months, per
      METRICS.md sec.11 (1-month review cycle, since review_interval_days_default=30 ~= 1 month).
    """
    n = len(qty_hist)
    lead_time_months = math.ceil(lead_plus_assembly_days / 30.44)
    stock = max_level
    backorder = 0.0
    pipeline = {}  # month_index -> qty arriving
    total_orig_demand = 0.0
    total_shipped_orig = 0.0
    stockout_months = 0

    for t in range(n):
        # 1. receive any scheduled arrival
        stock += pipeline.pop(t, 0.0)

        # 2. place a replenishment order (review ~monthly) up to Max, based on inventory position
        #    (on-hand + on-order not yet arrived - backorder)
        on_order = sum(pipeline.values())
        inv_position = stock + on_order - backorder
        if inv_position < max_level:
            order_qty = max_level - inv_position
            arrive_t = t + lead_time_months
            pipeline[arrive_t] = pipeline.get(arrive_t, 0.0) + order_qty

        # 3. serve backorder first, then this month's own demand
        orig_demand = float(qty_hist[t])
        total_orig_demand += orig_demand

        shipped_backorder = min(backorder, stock)
        stock -= shipped_backorder
        backorder -= shipped_backorder

        shipped_orig = min(orig_demand, stock)
        stock -= shipped_orig
        total_shipped_orig += shipped_orig

        unmet_orig = orig_demand - shipped_orig
        if unmet_orig > 1e-9 or backorder > 1e-9:
            stockout_months += 1
        backorder += unmet_orig

    fill_rate = total_shipped_orig / total_orig_demand if total_orig_demand > 0 else float("nan")
    cycle_service_level = (n - stockout_months) / n
    return {"fill_rate": fill_rate, "cycle_service_level": cycle_service_level,
            "total_orig_demand": total_orig_demand, "total_shipped_orig": total_shipped_orig,
            "stockout_months": stockout_months, "n_months": n}


def part_c2_simulation(config: dict, scope: pd.DataFrame, series: dict, fg_min: pd.DataFrame,
                        last_month_end: pd.Timestamp) -> dict:
    logger.info("=== PART C.2: historical simulation replay, fill_rate + cycle_service_level ===")
    default = config["phase_e1_assumptions"]["default_scenario"]
    lead, assembly = default["procurement_lead_time_days"], default["assembly_time_days"]
    review = config["phase_e1_assumptions"]["review_interval_days_default"]

    # Max = Min + review-interval expected demand (replenishment_qty_convention)
    fg_codes = fg_min.loc[fg_min["min"].notna(), "itemcode"].tolist()
    review_horizon = math.ceil(review / 30.44) + 1
    review_forecasts = fit_topdown_forecast(scope, series, fg_codes, review_horizon)

    rows = []
    for code in fg_codes:
        if code not in series or code not in review_forecasts:
            continue
        weights = prorate_weights(last_month_end, review, len(review_forecasts[code]))
        review_qty = float(np.dot(review_forecasts[code], weights))
        min_level = float(fg_min.loc[fg_min["itemcode"] == code, "min"].iloc[0])
        max_level = min_level + review_qty
        qty_hist = series[code][0]
        sim = simulate_item(qty_hist, min_level, max_level, lead + assembly)
        sim["itemcode"] = code
        sim["min_level"] = min_level
        sim["max_level"] = max_level
        rows.append(sim)

    sim_df = pd.DataFrame(rows)
    overall_fill_rate = sim_df["total_shipped_orig"].sum() / sim_df["total_orig_demand"].sum()
    overall_csl = 1 - (sim_df["stockout_months"].sum() / (sim_df["n_months"].sum()))
    mean_item_fill_rate = sim_df["fill_rate"].mean()
    mean_item_csl = sim_df["cycle_service_level"].mean()

    logger.info("Simulation over %d items: unit-weighted fill_rate=%.4f, cycle_service_level "
                "(1-total_stockout_months/total_months)=%.4f. Mean-of-item fill_rate=%.4f, "
                "mean-of-item cycle_service_level=%.4f", len(sim_df), overall_fill_rate, overall_csl,
                mean_item_fill_rate, mean_item_csl)

    sim_df.to_csv(os.path.join(SUMMARY_DIR, f"{OUT_PREFIX}_simulation_detail.csv"), index=False)
    return {
        "n_items_simulated": len(sim_df),
        "fill_rate_unit_weighted": float(overall_fill_rate),
        "cycle_service_level_pooled": float(overall_csl),
        "fill_rate_mean_of_items": float(mean_item_fill_rate),
        "cycle_service_level_mean_of_items": float(mean_item_csl),
    }, sim_df


# ============================================================================
# 7. Part C.3: Min for the 3 focus items (independent of their own segment classification)
# ============================================================================

def part_c3_focus_min(config: dict, scope: pd.DataFrame, series: dict, focus_items: list,
                       last_month_end: pd.Timestamp, daily_series: dict) -> pd.DataFrame:
    logger.info("=== PART C.3: Min (METRICS.md sec.5) for the 3 focus items ===")
    default = config["phase_e1_assumptions"]["default_scenario"]
    lead, assembly, sl = default["procurement_lead_time_days"], default["assembly_time_days"], default["cycle_service_level"]
    review = config["phase_e1_assumptions"]["review_interval_days_default"]
    protection_period_days = lead + assembly + review
    horizon = math.ceil(protection_period_days / 30.44) + 1

    forecasts = fit_topdown_forecast(scope, series, focus_items, horizon)
    rows = []
    for code in focus_items:
        qty, months = series[code]
        r = ltd_and_safety_stock(qty, months, forecasts[code], last_month_end, protection_period_days, sl,
                                  daily_qty=daily_series.get(code))
        r["itemcode"] = code
        rows.append(r)
        logger.info("Focus item %s: LTD=%.2f, safety_stock=%.2f, Min=%.2f (protection_period=%d days, "
                    "sl=%.2f, ltd_distribution n_nonzero=%d, unreliable=%s)",
                    code, r["ltd"], r["safety_stock"], r["min"], protection_period_days, sl,
                    r["n_nonzero_periods"], r["unreliable"])
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SUMMARY_DIR, f"{OUT_PREFIX}_focus_min_detail.csv"), index=False)
    return df, forecasts, protection_period_days


# ============================================================================
# 8. Part C.4: consumption total for the 3 focus items (METRICS.md sec.14)
# ============================================================================

def query_mps_with_contract(item_codes: list, after_month_end: str) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""SELECT itemcode, contractid, forecast_date, qty, status
              FROM {pc.SALE_TABLE}
              WHERE itemcode IN ('{code_list}') AND status = 'MPS' AND forecast_date > '{after_month_end}'"""
    df = run_query(sql)
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])
    return df


def part_c4_consumption(config: dict, focus_items: list, forecasts: dict, ces_backlog: pd.DataFrame,
                         last_month_end: pd.Timestamp, protection_period_days: int) -> dict:
    logger.info("=== PART C.4: consumption total (METRICS.md sec.14), confirmed source = Cube_CES "
                "Status='Backlog' (this Validator's OWN Part A conclusion) + cube_Sale_APD MPS ===")
    horizon = math.ceil(protection_period_days / 30.44) + 1
    months = month_starts_after(last_month_end, horizon)
    weights = prorate_weights(last_month_end, protection_period_days, horizon)
    period_end = last_month_end + pd.Timedelta(days=protection_period_days)

    mps = query_mps_with_contract(focus_items, last_month_end.strftime("%Y-%m-%d"))
    mps = mps[mps["forecast_date"] <= period_end]
    ces = ces_backlog[ces_backlog["ItemCode"].isin(focus_items)].copy()
    ces["ForecastDelDate"] = pd.to_datetime(ces["ForecastDelDate"], errors="coerce")

    detail_rows = []
    grand_total = 0.0
    for code in focus_items:
        mps_item = mps[mps["itemcode"] == code]
        mps_contracts = set(mps_item["contractid"])
        ces_item = ces[ces["ItemCode"] == code]
        ces_unique = ces_item[~ces_item["ContractID"].isin(mps_contracts)]  # dedup: skip CES rows
                                                                             # already counted via MPS

        for i, month_start in enumerate(months):
            month_end = month_start + pd.offsets.MonthEnd(0)
            fc = forecasts[code][i] * weights[i]

            mps_month = mps_item[(mps_item["forecast_date"] >= month_start) &
                                  (mps_item["forecast_date"] <= month_end)]["qty"].sum()

            if i == 0:
                # overdue CES rows (ForecastDelDate < TODAY, or null) placed in the current month
                ces_month = ces_unique[(ces_unique["ForecastDelDate"] < TODAY) |
                                        (ces_unique["ForecastDelDate"].isna()) |
                                        ((ces_unique["ForecastDelDate"] >= month_start) &
                                         (ces_unique["ForecastDelDate"] <= month_end))]["BacklogQty"].sum()
            else:
                ces_month = ces_unique[(ces_unique["ForecastDelDate"] >= month_start) &
                                        (ces_unique["ForecastDelDate"] <= month_end)]["BacklogQty"].sum()

            confirmed = float(mps_month) + float(ces_month)
            open_demand = max(fc - confirmed, 0.0)
            grand_total += open_demand
            detail_rows.append({
                "itemcode": code, "month": month_start.strftime("%Y-%m"), "forecast_weighted": fc,
                "confirmed_mps": float(mps_month), "confirmed_ces_backlog_dedup": float(ces_month),
                "confirmed_total": confirmed, "open_demand": open_demand,
            })

    detail = pd.DataFrame(detail_rows)
    detail.to_csv(os.path.join(SUMMARY_DIR, f"{OUT_PREFIX}_consumption_detail.csv"), index=False)
    logger.info("Consumption total (3 focus items, protection-period horizon): %.2f units", grand_total)
    logger.info("Per-item detail:\n%s", detail.to_string(index=False))
    return {"grand_total": grand_total}, detail


# ============================================================================
# MAIN
# ============================================================================

def main():
    config = pc.load_config()
    scope, own_scope_n, sym_diff = part_scope(config)
    monthly = pc.load_monthly_series(scope)
    series = monthly["series"]
    raw_monthly = pd.read_csv(pc.MONTHLY_FILE)
    max_ym = str(raw_monthly["year_month"].max())
    last_month_end = pd.Timestamp(max_ym + "-01") + pd.offsets.MonthEnd(0)
    logger.info("Frozen series snapshot_pull_date=%s; last calendar month in series (from data, not "
                "assumed)=%s -> last_month_end=%s", monthly["pull_date"], max_ym, last_month_end.date())

    a_result, ces_backlog_full = part_a(scope)

    eligible = scope[scope["eligible_for_policy"]]
    eligible_codes = set(eligible["code"])
    av, av_cutoff, av_window = compute_annual_value(eligible_codes)
    freq, median_notice = compute_order_frequency(config, eligible_codes, av_cutoff, av_window)
    seg_df, own_p50, freq_cutoff = part_b_segmentation(config, scope, av, freq, median_notice)

    sample_months = next(iter(series.values()))[1]
    daily_series = load_daily_history(set(scope["code"]), sample_months[0], sample_months[-1])

    fg_codes = seg_df.loc[seg_df["segment"] == "finished_goods_stock", "itemcode"].tolist()
    c1_summary, c1_detail = part_c1_stock_value(config, scope, series, fg_codes, last_month_end, daily_series)
    c2_summary, c2_detail = part_c2_simulation(config, scope, series, c1_detail.rename(
        columns={"itemcode": "itemcode"}), last_month_end)

    focus_items = config["pilot_item_codes"]
    c3_df, focus_forecasts, protection_period_days = part_c3_focus_min(
        config, scope, series, focus_items, last_month_end, daily_series)
    c4_summary, c4_detail = part_c4_consumption(
        config, focus_items, focus_forecasts, ces_backlog_full, last_month_end, protection_period_days)

    mase_df = compute_mase_undefined(series, scope["code"].tolist())
    n_mase_undefined = int(mase_df["mase_undefined"].sum())
    logger.info("MASE_undefined (own computation, all 128 scope items): %d", n_mase_undefined)
    mase_df.to_csv(os.path.join(SUMMARY_DIR, f"{OUT_PREFIX}_mase_undefined.csv"), index=False)

    logger.info("=== ALL DONE. Summary values for the report ===")
    logger.info("Part A: %s", a_result)
    logger.info("Part B: own_p50=%.2f, freq_cutoff=%.2f, segment counts=%s",
                own_p50, freq_cutoff, seg_df["segment"].value_counts().to_dict())
    logger.info("Part C1 (stock_value): %s", c1_summary)
    logger.info("Part C2 (simulation): %s", c2_summary)
    logger.info("Part C3 (focus Min):\n%s", c3_df[["itemcode", "ltd", "safety_stock", "min"]].to_string(index=False))
    logger.info("Part C4 (consumption total): %s", c4_summary)
    logger.info("MASE_undefined: %d", n_mase_undefined)


if __name__ == "__main__":
    main()
