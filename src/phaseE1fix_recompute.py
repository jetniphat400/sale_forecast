"""Phase E1-fix: recompute segmentation and every Phase E1 metric strictly per METRICS.md.

METRICS.md is now the single source of truth for every formula used here -- this script cites
the exact METRICS.md section for each metric it computes and computes NOTHING METRICS.md does
not define. Where METRICS.md's literal text differs from this project's prior Phase E1
implementation (src/phaseE1_common.py, src/phaseE1_segment_items.py), METRICS.md wins and the
difference is logged explicitly, not silently reconciled.

Known literal-text deviation, flagged here and in the hand-back report (not silently resolved):
METRICS.md Sec.14 says confirmed demand = "MPS rows in cube_Sale_APD plus Backlog rows in
Cube_CES" -- this project's prior implementation (config['phase_e1_assumptions']
['backlog_vs_mps_double_count_note'], src/build_inventory_dataset.py) used the separate
Cube_Backlog TABLE for backlog, not Cube_CES rows with Status='Backlog'. This script follows
METRICS.md's literal text (Cube_CES Status='Backlog'), not the prior Cube_Backlog-table
convention -- flagged as a candidate METRICS.md ambiguity for follow-up, not guessed silently.

Scope: PEM101 128-item pilot, per config['adopted_scope_file'] (unchanged from Phase E1).
Series: the LOCKED frozen forecast_date-keyed snapshot (output/data/processed_full_category_
sales_monthly_forecastDate.csv) -- NEVER a live pull -- this is the exact bug that caused the
original Phase E1 Modeler/Validator mismatch; unit_cost is the one metric METRICS.md Sec.1
explicitly sources from cube_Sale_APD directly (a live pull is correct there, not a bug).
"""
import logging
import math
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import run_query
from models import combination_forecast
from backtest_rekeyed import MA_WINDOWS
from phaseE1_common import (
    PROJECT_ROOT, SUMMARY_DIR, TOTAL_MONTHS,
    load_config, load_scope, load_monthly_series, query_order_level,
    topdown_item_forecast, query_inventory_exact, sellable_stock_per_item,
    current_minmax_per_item, mase_with_flag,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1fix_recompute")

SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"
DAYS_PER_MONTH = 30.44  # calendar-average month length, used consistently for day->month prorating
RAW_SALES_FILE = os.path.join(PROJECT_ROOT, "output", "data", "raw_full_category_sales.csv")


# ================================================================================================
# PART 1 -- Segmentation per METRICS.md Sec.15
# ================================================================================================

def build_item_facts(scope: pd.DataFrame, series_bundle: dict, order_level: pd.DataFrame) -> pd.DataFrame:
    """METRICS.md Sec.15 (corrected 2026-09-22):
        annual_value[item]    = sum of `sale` over the TRAILING 12 MONTHS ENDING AT THE DATA
                                CUTOFF (the frozen monthly series' own last complete month) --
                                NOT the item's own active span, NOT the full 31-month window.
        order_frequency[item] = count of DISTINCT (contractid, createDate) pairs in the SAME
                                trailing-12-month window (by createDate).
    This corrects the prior implementation, which annualized the FULL 31-month window
    (mean x 12) for annual_value and divided total order-line count by a fixed 31/12-month
    denominator for frequency -- neither matches METRICS.md's now-literal 'trailing 12 months
    ending at the data cutoff' wording, and was one root cause of the 76-vs-77 Modeler/Validator
    segmentation mismatch (STATUS.md, Phase E1-fix; METRICS.md Sec.15's own resolution note)."""
    series = series_bundle["series"]
    monthly_full = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "data",
                                             "processed_full_category_sales_monthly_forecastDate.csv"))
    data_cutoff_month = pd.Period(monthly_full["year_month"].max(), freq="M")
    window_months = pd.period_range(data_cutoff_month - 11, data_cutoff_month, freq="M")
    window_months_str = set(str(m) for m in window_months)
    window_start_date = window_months[0].start_time
    window_end_date = data_cutoff_month.end_time
    logger.info("METRICS.md Sec.15 trailing-12-month window: %s to %s (data cutoff = last complete "
                "month in the frozen series).", window_months[0], window_months[-1])

    sale_12mo = monthly_full[monthly_full["year_month"].isin(window_months_str)].groupby(
        "itemcode")["sale"].sum()

    ol = order_level.copy()
    ol["createDate"] = pd.to_datetime(ol["createDate"])
    ol_window = ol[(ol["createDate"] >= window_start_date) & (ol["createDate"] <= window_end_date)]
    freq_12mo = ol_window.drop_duplicates(subset=["itemcode", "contractid", "createDate"]).groupby(
        "itemcode").size()

    rows = []
    for _, r in scope.iterrows():
        code = r["code"]
        annual_value = float(sale_12mo.get(code, 0.0))
        order_freq = float(freq_12mo.get(code, 0))  # window IS 12 months -> count == per-year rate
        rows.append({"code": code, "type": r["type"], "eligible_for_policy": r["eligible_for_policy"],
                     "is_excluded": r["is_excluded"], "is_placeholder": r["is_placeholder"],
                     "annual_value_thb": annual_value, "order_freq_per_year": order_freq,
                     "has_history": code in series})
    return pd.DataFrame(rows)


def assign_policy_metrics15(facts: pd.DataFrame, assembly_time_days: int, median_notice_days: float) -> tuple:
    """METRICS.md Sec.15, applied literally:
        finished_goods_stock : annual value >= P50 of division OR order frequency >= 6/year
        component_stock_ato  : otherwise, AND assembly_time_days <= 6 (median customer notice)
        make_to_order        : never (notice never exceeds procurement)
        placeholder/excluded : per config item status
    'P50 of division' -- for the PEM101 pilot this scope IS PEM101 (128-item scope, 112 eligible);
    for the E2 pilot divisions this scope is the passed-in division's own item set. Stated as a
    resolved reading, not left ambiguous, because no other population is available to a single
    division's pipeline run.

    AMENDED 2026-09-22 (METRICS.md Sec.15): if P50 across the division's forecast items is
    exactly 0 (found live for PEM103: 57% of its 87 items have zero trailing-12-month sales), the
    value criterion is undefined and is NOT applied -- classification falls back to
    order_frequency >= 6/year alone. A second, informational-only P50 is also computed over items
    with annual_value > 0, reported but never used to classify."""
    elig = facts[facts["eligible_for_policy"]].copy()
    p50_value = float(elig["annual_value_thb"].median())
    freq_cutoff = 6.0

    # METRICS.md Sec.15 (amended 2026-09-22): if P50 across the division's forecast items is
    # zero, the value criterion is undefined and must not be applied -- classify by
    # order_frequency alone. Found live for PEM103 (57% of its 87 items have zero trailing-12mo
    # sales, pushing P50 to exactly 0, which under the OLD literal ">=" rule classified every
    # item finished_goods_stock regardless of frequency -- defeating the split).
    zero_p50_rule_used = p50_value == 0.0
    p50_nonzero_informational = (
        float(elig.loc[elig["annual_value_thb"] > 0, "annual_value_thb"].median())
        if (elig["annual_value_thb"] > 0).any() else None
    )  # informational only, per the amendment -- never drives classification

    def policy(row):
        if row["is_excluded"]:
            return "excluded"
        if row["is_placeholder"]:
            return "placeholder"
        if zero_p50_rule_used:
            fg = row["order_freq_per_year"] >= freq_cutoff
        else:
            fg = (row["annual_value_thb"] >= p50_value) or (row["order_freq_per_year"] >= freq_cutoff)
        if fg:
            return "finished_goods_stock"
        # component_stock_ato requires assembly_time_days <= median_notice_days (6d default)
        if assembly_time_days <= median_notice_days:
            return "component_stock_ato"
        # METRICS.md Sec.15 addendum (2026-09-23, Phase J2 Part 0): if assembly_time_days exceeds
        # the notice threshold, component_stock_ato is INFEASIBLE under this criterion -- named
        # explicitly rather than left as an undefined/unclassified state. At the config default
        # (3d <= 6d) this branch never fires.
        return "component_stock_ato_infeasible"

    facts = facts.copy()
    facts["policy"] = facts.apply(policy, axis=1)
    facts["p50_annual_value_thb"] = p50_value
    facts["freq_cutoff_per_year"] = freq_cutoff
    facts["zero_p50_rule_used"] = zero_p50_rule_used
    n_undefined = int((facts["policy"] == "component_stock_ato_infeasible").sum())
    if n_undefined:
        logger.warning("%d items fall into METRICS.md Sec.15's component_stock_ato_infeasible "
                        "state (assembly_time_days > median notice, so finished_goods_stock is not "
                        "met and component_stock_ato is infeasible) -- reported explicitly, not "
                        "silently assigned.", n_undefined)
    if zero_p50_rule_used:
        logger.warning("METRICS.md Sec.15 zero-P50 rule USED: P50 annual_value_thb is exactly 0 "
                        "across %d eligible items -- the value criterion is undefined and was NOT "
                        "applied; classification is by order_frequency >= %.0f/yr alone. "
                        "Informational-only P50 over items with annual_value>0: %s.",
                        len(elig), freq_cutoff,
                        f"THB {p50_nonzero_informational:,.2f}" if p50_nonzero_informational is not None else "undefined (no item has any value)")
    return facts, {"p50_annual_value_thb": p50_value, "freq_cutoff_per_year": freq_cutoff,
                   "assembly_time_days_used": assembly_time_days, "median_notice_days_used": median_notice_days,
                   "n_undefined_by_spec": n_undefined, "zero_p50_rule_used": zero_p50_rule_used,
                   "p50_nonzero_informational_thb": p50_nonzero_informational}


def threshold_sensitivity(facts: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """Every item within +-5% of either threshold (annual value vs P50, or order frequency vs 6/yr)."""
    p50 = thresholds["p50_annual_value_thb"]
    freq_cutoff = thresholds["freq_cutoff_per_year"]
    elig = facts[facts["eligible_for_policy"]].copy()
    elig["value_pct_from_p50"] = 100 * (elig["annual_value_thb"] - p50) / p50 if p50 else np.nan
    elig["freq_pct_from_cutoff"] = 100 * (elig["order_freq_per_year"] - freq_cutoff) / freq_cutoff
    near_value = elig["value_pct_from_p50"].abs() <= 5.0
    near_freq = elig["freq_pct_from_cutoff"].abs() <= 5.0
    near = elig[near_value | near_freq].copy()
    near["near_value_threshold"] = near_value[near.index]
    near["near_freq_threshold"] = near_freq[near.index]
    return near[["code", "annual_value_thb", "value_pct_from_p50", "near_value_threshold",
                 "order_freq_per_year", "freq_pct_from_cutoff", "near_freq_threshold", "policy"]]


# ================================================================================================
# PART 2 -- Metric recomputation per METRICS.md
# ================================================================================================

def compute_unit_cost_metrics1(item_codes: list, window_months: int) -> pd.DataFrame:
    """METRICS.md Sec.1, literally:
      unit_cost[item] = median(cost/qty) over rows in the trailing 12 months, Omni Channel,
                         Actual+MPS status
      - qty=0 rows excluded from the median
      - fewer than 3 rows in-window -> unit_cost_fallback = most-recent row with qty>0
      - no row at all -> unit_cost undefined -> no_unit_cost_items
    Deviation from the prior Phase D Check 2 / phaseE1_common methodology, noted: that
    implementation fell back to most-recent-transaction whenever the 12-month window had ZERO
    rows, not when it had FEWER THAN THREE. This script implements METRICS.md's literal <3 rule.
    Also, METRICS.md does not explicitly restrict the unit_cost pull to revenue_type='Omni
    Channel'/status IN ('Actual','MPS') in its formula line, but does say so in its own words
    ("Omni Channel scope, Actual + MPS status") -- applied as an explicit filter here, not
    inferred from the raw table's full row population."""
    code_list = "','".join(sorted(item_codes))
    sql = f"""SELECT itemcode, qty, cost, createDate FROM {SALE_TABLE}
              WHERE itemcode IN ('{code_list}') AND revenue_type = 'Omni Channel'
                AND status IN ('Actual','MPS')"""
    raw = run_query(sql)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    df = raw[(raw["qty"].notna()) & (raw["qty"] != 0) & (raw["cost"].notna())].copy()
    df["unit_cost"] = df["cost"] / df["qty"]

    global_max = df["createDate"].max()
    window_start = global_max - pd.DateOffset(months=window_months)
    in_window = df[df["createDate"] >= window_start]
    n_in_window = in_window.groupby("itemcode").size().rename("n_rows_12mo")
    median12 = in_window.groupby("itemcode")["unit_cost"].median().rename("median_unit_cost_12mo")

    max_date_per_item = df.groupby("itemcode")["createDate"].transform("max")
    recent = df[df["createDate"] == max_date_per_item].groupby("itemcode").agg(
        most_recent_unit_cost=("unit_cost", "mean"))

    out = pd.DataFrame({"itemcode": sorted(set(item_codes))}).set_index("itemcode")
    out = out.join(n_in_window).join(median12).join(recent).reset_index()
    out["n_rows_12mo"] = out["n_rows_12mo"].fillna(0).astype(int)

    enough_rows = out["n_rows_12mo"] >= 3
    has_recent = out["most_recent_unit_cost"].notna()
    out["unit_cost"] = np.where(enough_rows, out["median_unit_cost_12mo"], out["most_recent_unit_cost"])
    out["unit_cost_fallback"] = (~enough_rows) & has_recent
    out["no_unit_cost_item"] = (~enough_rows) & (~has_recent)
    out["basis"] = np.select(
        [enough_rows, (~enough_rows) & has_recent],
        ["median_12mo_ge3rows", "most_recent_transaction (unit_cost_fallback, <3 rows in 12mo window)"],
        default="no_unit_cost_items")
    n_fb, n_none = int(out["unit_cost_fallback"].sum()), int(out["no_unit_cost_item"].sum())
    logger.info("unit_cost (METRICS.md Sec.1): %d/%d priced from >=3-row 12mo median, "
                "%d unit_cost_fallback (<3 rows, most-recent used), %d no_unit_cost_items.",
                int(enough_rows.sum()), len(out), n_fb, n_none)
    return out[["itemcode", "unit_cost", "unit_cost_fallback", "no_unit_cost_item", "basis", "n_rows_12mo"]]


def protection_period_months(e1: dict) -> tuple:
    """METRICS.md Sec.2: protection_period_days = lead + assembly + review, all from config.
    Returned as (full_months, frac_month) for prorating (METRICS.md Sec.3's 'prorated for
    partial months')."""
    days = (e1["default_scenario"]["procurement_lead_time_days"]
            + e1["default_scenario"]["assembly_time_days"]
            + e1["review_interval_days_default"])
    months_float = days / DAYS_PER_MONTH
    full = int(math.floor(months_float))
    frac = months_float - full
    return full, frac, days


def load_daily_series(scope: pd.DataFrame, month_min: str, month_max: str) -> dict:
    """Builds a TRUE daily (not monthly-prorated) forecast_date-keyed ACTUAL-demand series per
    scope item, from the SAME frozen raw snapshot (`raw_full_category_sales.csv`, never a live
    pull) that src/load_data_full.py used to build the monthly series -- this is the identical
    underlying history at finer grain, not a different pull or a different scope.

    METRICS.md Sec.4 (corrected 2026-09-22) requires the ltd_distribution rolling window to
    advance one DAY at a time on the daily series when one is available; this is that series.

    Filtered identically to load_data_full.py's aggregate_monthly(date_col='forecast_date'):
    non-null forecast_date, forecast_date >= createDate (drops the known negative-interval
    anomaly). Bounded to [month_min, month_max] -- the SAME 31-month window as the monthly file
    (output/data/processed_full_category_sales_monthly_forecastDate.csv) -- so the daily and
    monthly series describe the identical history at different granularities, never different
    scopes. Zero-filled per item across every calendar day in the window.

    Returns {itemcode: (qty_array[n_days], date_index[n_days])}. Returns {} (empty) if the frozen
    raw file is missing, so callers can fall back to prorated-monthly windows and report it.
    """
    if not os.path.exists(RAW_SALES_FILE):
        logger.warning("Frozen raw file %s not found -- daily series unavailable, ltd_distribution "
                        "will fall back to prorated-monthly windows for every item.", RAW_SALES_FILE)
        return {}
    raw = pd.read_csv(RAW_SALES_FILE)
    n_raw = len(raw)
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw["createDate"] = pd.to_datetime(raw["createDate"], errors="coerce")
    raw = raw.dropna(subset=["forecast_date"])
    raw = raw[raw["forecast_date"] >= raw["createDate"]]

    day_min = pd.Period(month_min, freq="M").start_time
    day_max = pd.Period(month_max, freq="M").end_time.normalize()
    raw = raw[(raw["forecast_date"] >= day_min) & (raw["forecast_date"] <= day_max)]
    logger.info("Daily series (forecast_date-keyed, frozen %s): %d of %d raw rows kept after "
                "null/negative-interval/window filters. Window %s to %s (%d days).",
                RAW_SALES_FILE, len(raw), n_raw, day_min.date(), day_max.date(),
                (day_max - day_min).days + 1)

    full_day_index = pd.date_range(day_min, day_max, freq="D")
    daily = raw.groupby(["itemcode", raw["forecast_date"].dt.normalize()])["qty"].sum()
    item_index = daily.index.get_level_values(0)

    out = {}
    for code in sorted(scope["code"].unique()):
        s = pd.Series(0.0, index=full_day_index)
        if code in item_index:
            sub = daily.loc[code]
            s.loc[sub.index] = sub.to_numpy(dtype=float)
        out[code] = (s.to_numpy(dtype=float), full_day_index)
    return out


def compute_safety_stock(cum: np.ndarray, ltd: float, sl: float) -> tuple:
    """METRICS.md Sec.4's literal formula: safety_stock = percentile(ltd_distribution, sl) - LTD,
    floored at 0. Subtracts LTD (the forecast-based point estimate, METRICS.md Sec.3) -- NOT the
    empirical distribution's own mean. These differ whenever the forecast and the historical
    average disagree; conflating them was a confirmed code defect (STATUS.md, Phase E1-fix Part
    2: the Modeler's prior code computed `percentile - cum.mean()`, which the Validator's
    independent implementation, matching METRICS.md literally, did not reproduce).
    Returns (percentile_value, safety_stock)."""
    pct_value = float(np.percentile(cum, sl * 100))
    safety_stock = max(0.0, pct_value - ltd)
    return pct_value, safety_stock


def compute_ltd_and_distribution(scope: pd.DataFrame, series_bundle: dict, facts: pd.DataFrame,
                                  full_months: int, frac_month: int, sl: float,
                                  daily_series: dict, protection_period_days: int) -> pd.DataFrame:
    """METRICS.md Sec.3/4 (corrected 2026-09-22):
      LTD[item] = Top-down combination forecast summed over protection_period months, prorated
                  for the partial month (unchanged -- the forecast model itself is monthly; its
                  total prorated horizon already equals protection_period_days exactly, via
                  DAYS_PER_MONTH, see protection_period_months()).
      ltd_distribution[item] = empirical distribution of cumulative ACTUAL demand over rolling
                  windows of EXACTLY protection_period_days, advancing ONE DAY at a time, on the
                  daily forecast_date-keyed series (load_daily_series) when the item has one.
                  Falls back to a monthly-bucket proration (partial month weighted by frac_month,
                  same convention as LTD) only for items absent from the daily series -- reported
                  per item via `distribution_method`.
      safety_stock[item, sl] = percentile(ltd_distribution, sl) - LTD ; floored at 0.
      Fewer than 6 non-zero windows -> percentiles above 90 reported 'unreliable'.
    Placeholder items have no LTD (outside the hierarchy, Sec.3) -- excluded from this function's
    input by the caller (only eligible_for_policy items with fg_stock/ato relevance are passed)."""
    series = series_bundle["series"]
    horizon = full_months + (1 if frac_month > 0 else 0)
    fc = topdown_item_forecast(scope, series, fit_end=TOTAL_MONTHS, horizon=horizon)

    window_len_months = full_months + (1 if frac_month > 0 else 0)  # monthly-fallback window length only

    rows = []
    n_daily, n_fallback = 0, 0
    for code in facts["code"]:
        if code not in fc or code not in series:
            continue
        forecast_arr = fc[code]
        ltd = float(forecast_arr[:full_months].sum())
        if frac_month > 0 and full_months < len(forecast_arr):
            ltd += frac_month * forecast_arr[full_months]

        if code in daily_series:
            method = "daily"
            qty_d, _dates = daily_series[code]
            n_d = len(qty_d)
            if protection_period_days <= 0 or protection_period_days > n_d:
                rows.append({"code": code, "LTD": ltd, "n_nonzero_windows": 0, "unreliable_upper_pct": True,
                             "safety_stock": np.nan, "min_qty": np.nan, "distribution_method": method})
                continue
            csum = np.concatenate([[0.0], np.cumsum(qty_d)])
            cum = csum[protection_period_days:] - csum[:-protection_period_days]
            n_daily += 1
        else:
            method = "monthly_prorated_fallback"
            n_fallback += 1
            qty, _months = series[code]
            n = len(qty)
            if window_len_months <= 0 or window_len_months > n:
                rows.append({"code": code, "LTD": ltd, "n_nonzero_windows": 0, "unreliable_upper_pct": True,
                             "safety_stock": np.nan, "min_qty": np.nan, "distribution_method": method})
                continue
            cum = np.array([qty[i:i + full_months].sum() +
                            (frac_month * qty[i + full_months] if frac_month > 0 and i + full_months < n else 0.0)
                            for i in range(n - window_len_months + 1)])

        n_nonzero = int((cum > 0).sum())
        unreliable = n_nonzero < 6
        pct_value, safety_stock = compute_safety_stock(cum, ltd, sl)
        min_qty = ltd + safety_stock
        rows.append({"code": code, "LTD": ltd, "ltd_distribution_mean": float(cum.mean()),
                     "percentile_value": pct_value, "n_nonzero_windows": n_nonzero,
                     "unreliable_upper_pct": unreliable, "safety_stock": safety_stock, "min_qty": min_qty,
                     "forecast_horizon_used": horizon, "distribution_method": method})
    logger.info("ltd_distribution (METRICS.md Sec.4): %d items used the TRUE daily rolling window "
                "(protection_period_days=%d, stepped 1 day at a time); %d items fell back to "
                "prorated-monthly windows (no daily history available for that item).",
                n_daily, protection_period_days, n_fallback)
    return pd.DataFrame(rows)


def compute_max_and_stock_value(ltd_df: pd.DataFrame, scope: pd.DataFrame, series_bundle: dict,
                                 facts: pd.DataFrame, unit_cost_df: pd.DataFrame,
                                 review_interval_days: int) -> pd.DataFrame:
    """METRICS.md Sec.5/6: Max = Min + demand over review_interval_days (forecast-based, same
    horizon-extension convention as LTD, immediately following the protection period). stock_value
    = Sum(Min x unit_cost) over finished_goods_stock items with a usable unit_cost."""
    series = series_bundle["series"]
    review_months_float = review_interval_days / DAYS_PER_MONTH
    review_full = int(math.floor(review_months_float))
    review_frac = review_months_float - review_full

    df = ltd_df.merge(facts[["code", "policy"]], on="code", how="left").merge(
        unit_cost_df.rename(columns={"itemcode": "code"}), on="code", how="left")

    replen_qty = []
    for _, r in df.iterrows():
        code = r["code"]
        horizon = int(r.get("forecast_horizon_used", 0) or 0)
        extra_needed = review_full + (1 if review_frac > 0 else 0)
        total_horizon = horizon + extra_needed
        if code in series:
            fc = topdown_item_forecast(scope, series, fit_end=TOTAL_MONTHS, horizon=total_horizon).get(code)
        else:
            fc = None
        if fc is None or np.isnan(r["min_qty"]):
            replen_qty.append(np.nan)
            continue
        seg = fc[horizon: horizon + review_full].sum()
        if review_frac > 0 and horizon + review_full < len(fc):
            seg += review_frac * fc[horizon + review_full]
        replen_qty.append(float(seg))
    df["replenishment_qty"] = replen_qty
    df["max_qty"] = df["min_qty"] + df["replenishment_qty"]
    df["stock_value_contribution"] = np.where(
        (df["policy"] == "finished_goods_stock") & df["unit_cost"].notna(),
        df["min_qty"] * df["unit_cost"], 0.0)
    return df


def compute_mase(scope: pd.DataFrame, series_bundle: dict, item_codes: list, horizon: int) -> pd.DataFrame:
    """METRICS.md Sec.13: MASE = MAE(model) / MAE(in-sample seasonal-naive, m=1). One evaluation
    point per item: train = qty[:TOTAL_MONTHS-horizon], test = qty[-horizon:], forecast = Top-down
    combination fit on train. Scale = mean absolute first difference of the TRAIN series
    (identical recipe to src/backtest_rekeyed.py's compute_metrics / phaseE1_common.mase_with_flag)
    -- undefined when train is constant/all-zero. This is a single-origin MASE (the default
    scenario's own horizon), not the full 7-origin rolling backtest already reported elsewhere in
    this project; stated as such, not conflated with that separate figure."""
    series = series_bundle["series"]
    fit_end = TOTAL_MONTHS - horizon
    fc = topdown_item_forecast(scope, series, fit_end=fit_end, horizon=horizon)
    rows = []
    for code in item_codes:
        if code not in series or code not in fc:
            continue
        qty, _ = series[code]
        actual = qty[fit_end:fit_end + horizon]
        forecast = fc[code]
        mae = float(np.mean(np.abs(actual - forecast)))
        train = qty[:fit_end]
        mase, undefined = mase_with_flag(mae, train)
        rows.append({"code": code, "MAE": mae, "MASE": mase, "MASE_undefined": undefined})
    return pd.DataFrame(rows)


def main():
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    order_level = query_order_level(scope["code"].tolist(), config)

    median_notice_days = float(order_level["notice_days"].median())
    logger.info("Project-wide median customer notice: %.2f days (STATUS.md cites 6 -- confirmed live).",
                median_notice_days)

    # ---- Part 1: segmentation per METRICS.md Sec.15 ----
    facts = build_item_facts(scope, series_bundle, order_level)
    facts, thresholds = assign_policy_metrics15(
        facts, assembly_time_days=e1["default_scenario"]["assembly_time_days"],
        median_notice_days=median_notice_days)
    sensitivity = threshold_sensitivity(facts, thresholds)

    counts = facts["policy"].value_counts().to_dict()
    logger.info("METRICS.md Sec.15 policy counts: %s (total %d)", counts, len(facts))

    facts.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_item_policy.csv"), index=False)
    sensitivity.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_threshold_sensitivity.csv"), index=False)

    fg_codes = set(facts[facts["policy"] == "finished_goods_stock"]["code"])

    # ---- Part 2: full metric recomputation, default scenario ----
    full_months, frac_month, protection_days = protection_period_months(e1)
    sl = e1["default_scenario"]["cycle_service_level"]
    logger.info("protection_period_days=%d -> %d full months + %.3f fractional month (sl=%.2f)",
                protection_days, full_months, frac_month, sl)

    sample_months = next(iter(series_bundle["series"].values()))[1]
    month_min, month_max = sample_months[0], sample_months[-1]
    daily_series = load_daily_series(scope, month_min, month_max)

    ltd_input = facts[facts["policy"].isin(["finished_goods_stock", "component_stock_ato"])]
    ltd_df = compute_ltd_and_distribution(scope, series_bundle, ltd_input, full_months, frac_month, sl,
                                           daily_series, protection_days)

    unit_cost_df = compute_unit_cost_metrics1(scope["code"].tolist(), e1["unit_cost_median_window_months"])

    full_df = compute_max_and_stock_value(ltd_df, scope, series_bundle, facts, unit_cost_df,
                                           e1["review_interval_days_default"])

    stock_value = float(full_df.loc[full_df["code"].isin(fg_codes), "stock_value_contribution"].sum())
    n_no_unit_cost_in_fg = int(unit_cost_df.merge(facts[["code"]].assign(itemcode=facts["code"]),
                                left_on="itemcode", right_on="itemcode")
                                .merge(facts[facts["policy"] == "finished_goods_stock"][["code"]],
                                       left_on="itemcode", right_on="code")["no_unit_cost_item"].sum())
    logger.info("stock_value (METRICS.md Sec.6, Sum Min x unit_cost over finished_goods_stock): THB %.2f "
                "(%d fg items excluded for no_unit_cost_item)", stock_value, n_no_unit_cost_in_fg)

    # sellable stock / current min-max
    inv = query_inventory_exact(scope["code"].tolist())
    # sellable_warehouse_codes is keyed per division since 2026-09-22 (Phase E2 Part 2); this
    # script is PEM101-specific by design (its scope is always the 128-item PEM101 pilot).
    sellable = sellable_stock_per_item(inv, scope["code"].tolist(), e1["sellable_warehouse_codes"]["PEM101"])
    current_mm = current_minmax_per_item(inv, scope["code"].tolist())
    current_mm.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_minmax.csv"), index=False)

    cs_df = sellable.rename(columns={"itemcode": "code"}).merge(
        unit_cost_df.rename(columns={"itemcode": "code"}), on="code", how="left").merge(
        facts[["code", "policy"]], on="code", how="left")
    current_stock_value = float((cs_df.loc[cs_df["code"].isin(fg_codes), "sellable_stock"] *
                                  cs_df.loc[cs_df["code"].isin(fg_codes), "unit_cost"].fillna(0)).sum())
    logger.info("current_stock_value (METRICS.md Sec.6 comparison figure, on-hand-based, SAME "
                "finished_goods_stock item set): THB %.2f", current_stock_value)

    # months_of_cover: on_hand_sellable / mean monthly forecast over the protection-period horizon
    mc_rows = []
    for code in scope["code"]:
        oh = float(sellable.loc[sellable["itemcode"] == code, "sellable_stock"].iloc[0]) if code in set(sellable["itemcode"]) else 0.0
        r = ltd_df[ltd_df["code"] == code]
        if len(r) and r["forecast_horizon_used"].iloc[0]:
            horizon = int(r["forecast_horizon_used"].iloc[0])
            fc = topdown_item_forecast(scope, series_bundle["series"], TOTAL_MONTHS, horizon).get(code)
            mean_fc = float(np.mean(fc)) if fc is not None and len(fc) else 0.0
        else:
            mean_fc = 0.0
        moc = (oh / mean_fc) if mean_fc > 0 else np.inf
        mc_rows.append({"code": code, "on_hand_sellable": oh, "mean_monthly_forecast": mean_fc,
                         "months_of_cover": moc})
    moc_df = pd.DataFrame(mc_rows)
    n_infinite = int(np.isinf(moc_df["months_of_cover"]).sum())
    logger.info("months_of_cover: %d of %d items have forecast=0 -> reported as Inf.", n_infinite, len(moc_df))

    # ---- forecast_consumption, METRICS.md Sec.14 (corrected 2026-09-22): confirmed_total and
    # open_demand_total are two DISTINCT metrics, both reported, never one under the other's
    # name. confirmed[item, month] = Sum qty of confirmed undelivered orders whose forecast_date
    # falls in that month (MPS rows by their own forecast_date month; Cube_CES Status='Backlog'
    # rows by their own ForecastDelDate month -- NOT force-placed in the current month unless
    # actually overdue). Cube_Backlog table is never used (Part 1 finding, cited in Sec.14 now).
    pull_date = series_bundle["pull_date"]
    last_month = series_bundle["series"][next(iter(series_bundle["series"]))][1][-1] if series_bundle["series"] else None
    after_month_end = pd.Period(last_month, freq="M").end_time.strftime("%Y-%m-%d") if last_month else None
    fg_list = sorted(fg_codes)
    today = pd.Timestamp.now().normalize()  # "today" per Sec.14's literal text -- the live wall-clock
    # date, not the frozen series' snapshot_pull_date (that constant is the historical-actuals
    # freeze date, unrelated to what "overdue" means for a live confirmed-order pull).

    code_list = "','".join(fg_list)
    # cube_Sale_APD's contract-id column is named 'contractid' (confirmed against the live schema,
    # TOP 0 * pull) -- an earlier version of this script guessed 'contract', which does not exist;
    # this is a query-text fix for a discovered typo, not a login retry (the connection itself was
    # never re-attempted after a failure).
    mps_sql = f"""SELECT itemcode, forecast_date, qty, status, createDate, contractid AS contract
                  FROM {SALE_TABLE} WHERE itemcode IN ('{code_list}') AND status='MPS'
                    AND forecast_date > '{after_month_end}'""" if fg_list else None
    mps = run_query(mps_sql) if mps_sql else pd.DataFrame()

    ces_backlog_sql = f"""SELECT ItemCode AS itemcode, ContractID AS contract, ForecastDelDate,
                                 ActualQty, BacklogQty
                          FROM {CES_TABLE} WHERE ItemCode IN ('{code_list}') AND Status='Backlog'""" if fg_list else None
    try:
        ces_backlog = run_query(ces_backlog_sql) if ces_backlog_sql else pd.DataFrame()
    except Exception as exc:
        logger.error("Cube_CES Status='Backlog' query failed: %s -- METRICS.md Sec.14's literal source "
                      "could not be read; forecast_consumption cannot be computed as specified.", exc)
        ces_backlog = pd.DataFrame()

    if len(mps):
        mps["forecast_date"] = pd.to_datetime(mps["forecast_date"])
        mps["year_month"] = mps["forecast_date"].dt.to_period("M").astype(str)
        mps["dedupe_key"] = mps["itemcode"].astype(str) + "::" + mps["contract"].astype(str)
        mps_dedup = mps.drop_duplicates(subset="dedupe_key")
    else:
        mps_dedup = mps

    if len(ces_backlog):
        ces_backlog["ForecastDelDate"] = pd.to_datetime(ces_backlog["ForecastDelDate"], errors="coerce")
        ces_backlog["qty"] = ces_backlog["ActualQty"].fillna(0) + ces_backlog["BacklogQty"].fillna(0)
        ces_backlog["dedupe_key"] = ces_backlog["itemcode"].astype(str) + "::" + ces_backlog["contract"].astype(str)
        ces_dedup = ces_backlog.drop_duplicates(subset="dedupe_key").copy()
        # Cross-source dedup: METRICS.md Sec.14 says "deduplicated on contract + item" across
        # BOTH sources combined, not each source deduped only against itself -- a contract that
        # is both an MPS row in cube_Sale_APD AND a Cube_CES Backlog row (the same order, seen
        # through two systems -- expected per STATUS.md's Phase A finding that MPS-linked
        # contracts carry Cube_CES Status='Backlog') must count once, not twice. Confirmed as a
        # real, not hypothetical, double-count here: dropping this line doubled confirmed_total
        # for every focus item exactly 2x before this fix.
        mps_keys = set(mps_dedup["dedupe_key"]) if len(mps_dedup) else set()
        n_before = len(ces_dedup)
        ces_dedup = ces_dedup[~ces_dedup["dedupe_key"].isin(mps_keys)]
        n_dropped_dupe = n_before - len(ces_dedup)
        if n_dropped_dupe:
            logger.info("forecast_consumption: dropped %d Cube_CES Backlog rows already counted "
                        "via MPS on the same (item, contract) key -- cross-source dedup per "
                        "METRICS.md Sec.14.", n_dropped_dupe)
        # overdue = forecast_date before today, OR null (a backlog row with no forecast_date at
        # all cannot be placed in its own month, so it is treated as overdue and placed now).
        ces_dedup["overdue"] = ces_dedup["ForecastDelDate"].isna() | (ces_dedup["ForecastDelDate"] < today)
        ces_dedup["year_month"] = ces_dedup["ForecastDelDate"].dt.to_period("M").astype(str)
    else:
        ces_dedup = ces_backlog

    forecast_horizon_months = full_months + (1 if frac_month > 0 else 0)
    period_starts = pd.Period(after_month_end, freq="M") + 1
    period_labels = [str(period_starts + i) for i in range(forecast_horizon_months)]

    confirmed = {code: {m: 0.0 for m in period_labels} for code in fg_list}
    if len(mps_dedup):
        for _, r in mps_dedup.iterrows():
            if r["itemcode"] in confirmed and r["year_month"] in confirmed[r["itemcode"]]:
                confirmed[r["itemcode"]][r["year_month"]] += float(r["qty"])
    if len(ces_dedup):
        for _, r in ces_dedup.iterrows():
            if r["itemcode"] not in confirmed:
                continue
            target_month = period_labels[0] if r["overdue"] else r["year_month"]
            if target_month in confirmed[r["itemcode"]]:
                confirmed[r["itemcode"]][target_month] += float(r["qty"])

    consumption_rows = []
    fc_by_item = topdown_item_forecast(scope, series_bundle["series"], TOTAL_MONTHS, forecast_horizon_months)
    for code in fg_list:
        fc = fc_by_item.get(code)
        if fc is None:
            continue
        for i, m in enumerate(period_labels):
            forecast_val = float(fc[i])
            # The horizon's LAST period is the same partial month LTD (Sec.3) prorates by
            # frac_month -- weight it identically here so "the horizon" means the same thing
            # (the protection period, not one extra whole month) in both places. Fixes an
            # internal inconsistency found while re-tracing a confirmed/open_demand mismatch:
            # LTD prorated the partial month, forecast_consumption previously did not.
            if i == len(period_labels) - 1 and frac_month > 0:
                forecast_val *= frac_month
            conf = confirmed[code][m]
            open_demand = max(forecast_val - conf, 0.0)
            consumption_rows.append({"code": code, "year_month": m, "raw_forecast": forecast_val,
                                      "confirmed": conf, "open_demand": open_demand})
    consumption_df = pd.DataFrame(consumption_rows)
    confirmed_total = float(consumption_df["confirmed"].sum()) if len(consumption_df) else 0.0
    open_demand_total = float(consumption_df["open_demand"].sum()) if len(consumption_df) else 0.0
    total_forecast = float(consumption_df["raw_forecast"].sum()) if len(consumption_df) else 0.0
    logger.info("forecast_consumption (METRICS.md Sec.14, corrected): confirmed_total=%.1f, "
                "open_demand_total=%.1f, total raw forecast=%.1f, across %d finished_goods_stock "
                "items, horizon %s..%s", confirmed_total, open_demand_total, total_forecast,
                len(fg_list), period_labels[0] if period_labels else None, period_labels[-1] if period_labels else None)

    mase_df = compute_mase(scope, series_bundle, sorted(fg_codes), forecast_horizon_months)
    mase_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_mase.csv"), index=False)
    n_mase_undefined = int(mase_df["MASE_undefined"].sum()) if len(mase_df) else 0
    mean_mase = float(mase_df.loc[~mase_df["MASE_undefined"], "MASE"].mean()) if len(mase_df) else float("nan")
    logger.info("MASE (METRICS.md Sec.13): %d of %d finished_goods_stock items MASE_undefined "
                "(excluded from the mean); mean MASE over the rest = %.3f", n_mase_undefined, len(mase_df), mean_mase)

    focus_items = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
    focus_min = full_df[full_df["code"].isin(focus_items)][["code", "LTD", "safety_stock", "min_qty", "max_qty"]]
    focus_rows = consumption_df[consumption_df["code"].isin(focus_items)] if len(consumption_df) else consumption_df
    focus_confirmed_total = float(focus_rows["confirmed"].sum()) if len(focus_rows) else 0.0
    focus_open_demand_total = float(focus_rows["open_demand"].sum()) if len(focus_rows) else 0.0

    # ---- write outputs ----
    full_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_minmax_stockvalue.csv"), index=False)
    unit_cost_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_unit_cost.csv"), index=False)
    moc_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_months_of_cover.csv"), index=False)
    consumption_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_forecast_consumption.csv"), index=False)
    cs_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_stock_value_inputs.csv"), index=False)

    n_fallback = int(unit_cost_df["unit_cost_fallback"].sum())
    n_no_cost = int(unit_cost_df["no_unit_cost_item"].sum())
    n_unreliable = int(ltd_df["unreliable_upper_pct"].sum()) if len(ltd_df) else 0
    n_daily_dist = int((ltd_df["distribution_method"] == "daily").sum()) if len(ltd_df) else 0
    n_monthly_fallback_dist = int((ltd_df["distribution_method"] == "monthly_prorated_fallback").sum()) if len(ltd_df) else 0

    print("\n" + "=" * 90)
    print("PHASE E1-FIX MODELER -- HEADLINE FIGURES (default scenario, METRICS.md formulas)")
    print("=" * 90)
    print(f"Segmentation (METRICS.md Sec.15): {counts}")
    print(f"  P50 annual value (division=PEM101 eligible pop.): THB {thresholds['p50_annual_value_thb']:,.2f}")
    print(f"  order-frequency cutoff: {thresholds['freq_cutoff_per_year']}/yr; "
          f"median_notice_days used: {thresholds['median_notice_days_used']:.2f}")
    print(f"  items within +-5%% of a threshold: {len(sensitivity)}")
    print(f"unit_cost: {n_fallback} unit_cost_fallback, {n_no_cost} no_unit_cost_items")
    print(f"ltd_distribution: {n_unreliable} items flagged unreliable_upper_pct (<6 non-zero windows); "
          f"{n_daily_dist} items used the true daily rolling window, {n_monthly_fallback_dist} fell "
          f"back to prorated-monthly windows")
    print(f"MASE: {n_mase_undefined} items MASE_undefined (excluded from mean); mean MASE (rest) = {mean_mase:.3f}")
    print(f"stock_value (Sec.6, Sum Min x unit_cost, finished_goods_stock only): THB {stock_value:,.2f}")
    print(f"current_stock_value (Sec.6 comparison, same item set): THB {current_stock_value:,.2f}")
    print(f"forecast_consumption (Sec.14): confirmed_total={confirmed_total:,.1f} units, "
          f"open_demand_total={open_demand_total:,.1f} units, of {total_forecast:,.1f} raw forecast")
    print(f"Focus-item confirmed_total: {focus_confirmed_total:,.1f} units; "
          f"focus-item open_demand_total: {focus_open_demand_total:,.1f} units")
    print("\nFocus-item Min/Max:")
    print(focus_min.to_string(index=False))
    print(f"\nsnapshot_pull_date used for the frozen series: {pull_date}")

    return {"facts": facts, "thresholds": thresholds, "sensitivity": sensitivity, "full_df": full_df,
            "stock_value": stock_value, "current_stock_value": current_stock_value,
            "unit_cost_df": unit_cost_df, "moc_df": moc_df, "consumption_df": consumption_df,
            "confirmed_total": confirmed_total, "open_demand_total": open_demand_total,
            "focus_confirmed_total": focus_confirmed_total, "focus_open_demand_total": focus_open_demand_total,
            "n_fallback": n_fallback, "n_no_cost": n_no_cost, "n_unreliable": n_unreliable,
            "n_daily_dist": n_daily_dist, "n_monthly_fallback_dist": n_monthly_fallback_dist,
            "protection_days": protection_days, "full_months": full_months, "frac_month": frac_month,
            "sl": sl, "fg_codes": fg_codes, "mase_df": mase_df, "n_mase_undefined": n_mase_undefined}


if __name__ == "__main__":
    main()
