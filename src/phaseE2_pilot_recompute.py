"""Phase E2 scoped pilot -- Modeler, PEM103 (87 items) and PEM107 (136 items).

Extends the PEM101 Phase E1-fix pipeline (src/phaseE1fix_recompute.py) to two more divisions, per
METRICS.md exactly as corrected there -- reuses that script's already-verified, division-generic
functions directly (assign_policy_metrics15, threshold_sensitivity, compute_unit_cost_metrics1,
protection_period_months, compute_safety_stock, compute_ltd_and_distribution,
compute_max_and_stock_value, compute_mase -- none of these read a fixed PEM101 file path or
depend on the 128-item pilot scope). Two things phaseE1fix_recompute.py's PEM101 pipeline could
NOT be reused for, because PEM103/PEM107 have no existing frozen series (that frozen file is
scoped to the Fuse+Surge-Arrester product category, i.e. PEM101 only):
  1. item scope -- built here from the pricelist by DIVISION (not product category);
  2. the monthly/daily demand series -- pulled fresh here (this script's own single DB connection
     attempt) and built in-memory, over the SAME 31-month common window PEM101's frozen series
     uses (2024-01 to 2026-07, TOTAL_MONTHS=31) so the TOTAL_MONTHS-dependent reused functions
     work unmodified and results stay directly comparable across divisions.

No excluded_item_codes/placeholder_item_codes list exists for PEM103/PEM107 (those lists are
PEM101-128-item-pilot-specific, from Phase C/D). Every item here is eligible_for_policy=True;
items with no sales history simply get annual_value=0, order_freq=0 and are classified by
METRICS.md Sec.15 like any other item (most likely component_stock_ato or make_to_order) --
stated as an assumption, not a silently-invented exclusion list.

DATABASE ACCESS RULE: one connection attempt only, covering BOTH divisions in one combined pull.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import run_query
from pricelist_reader import load_visible_product_rows
from division_utils import assert_no_code_on_multiple_sheets
from models import combination_forecast
from phaseE1_common import (
    PROJECT_ROOT, SUMMARY_DIR, topdown_item_forecast, query_inventory_exact,
    sellable_stock_per_item, current_minmax_per_item, query_order_level,
)
from phaseE1fix_recompute import (
    assign_policy_metrics15, threshold_sensitivity, compute_unit_cost_metrics1,
    protection_period_months, compute_safety_stock, compute_ltd_and_distribution,
    compute_max_and_stock_value, compute_mase,
)
from phaseE1fix_simulation import simulate_item_daily

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE2_pilot_recompute")

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
DIVISIONS = ["PEM103", "PEM107"]
TOTAL_MONTHS = 31  # SAME common window as PEM101's frozen series (2024-01 .. 2026-07)
MONTH_MIN, MONTH_MAX = "2024-01", "2026-07"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_division_scope(config: dict, division: str) -> pd.DataFrame:
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    assert_no_code_on_multiple_sheets(pl)
    pl = pl.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    pl["division"] = pl["sheet"].map(config["sheet_to_division"])
    scope = pl[pl["division"] == division][["code", "type", "category"]].copy()
    scope["eligible_for_policy"] = True
    scope["is_excluded"] = False
    scope["is_placeholder"] = False
    logger.info("Division scope for %s: %d codes across %d Types (no excluded/placeholder list "
                "exists for this division -- every item is eligible_for_policy).",
                division, len(scope), scope["type"].nunique())
    return scope


def pull_raw_sales(config: dict, codes: list) -> pd.DataFrame:
    """Single combined live pull, both divisions' items -- the one DATABASE ACCESS RULE attempt
    for this script. Same filter convention as src/load_data_full.py's pull_raw_sales: itemcode +
    revenue_type + status + date only, never a division filter (CONVENTIONS.md)."""
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    start_date = config["date_range"]["start"]
    code_list = "','".join(sorted(codes))
    status_list = "','".join(statuses)
    sql = f"""
        SELECT itemcode, createDate, forecast_date, qty, sale, status, contractid
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{revenue_type}'
          AND status IN ('{status_list}')
          AND createDate >= '{start_date}'
    """
    try:
        df = run_query(sql)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: single connection attempt failed, not retrying. Error: %r", exc)
        raise
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    n_before = len(df)
    neg_qty = df[df["qty"] < 0]
    if len(neg_qty):
        raise ValueError(f"{len(neg_qty)} rows with negative qty -- must be reviewed, not dropped.")
    logger.info("Pulled %d raw rows for %d items (%s, status in %s, createDate>=%s).",
                n_before, len(codes), revenue_type, statuses, start_date)
    return df


def build_monthly_series(raw: pd.DataFrame, codes: list) -> dict:
    """forecast_date-keyed monthly grid, zero-filled, over the fixed [MONTH_MIN, MONTH_MAX]
    31-month window -- same filter as src/load_data_full.py's aggregate_monthly(date_col=
    'forecast_date'): drop null forecast_date, drop forecast_date<createDate (known anomaly)."""
    d = raw.dropna(subset=["forecast_date"]).copy()
    d = d[d["forecast_date"] >= d["createDate"]]
    d["year_month"] = d["forecast_date"].dt.to_period("M")
    months = pd.period_range(MONTH_MIN, MONTH_MAX, freq="M")
    d = d[d["year_month"].isin(set(months))]

    monthly = d.groupby(["itemcode", "year_month"], as_index=False).agg(qty=("qty", "sum"), sale=("sale", "sum"))
    full_index = pd.MultiIndex.from_product([codes, months], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()
    full["year_month"] = full["year_month"].astype(str)

    series = {}
    for code in codes:
        g = full[full["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        month_labels = g["year_month"].tolist()
        if len(qty) != TOTAL_MONTHS:
            raise ValueError(f"{code}: {len(qty)} months in grid, expected {TOTAL_MONTHS}")
        series[code] = (qty, month_labels)
    logger.info("Monthly series built: %d items x %d months (%s to %s).", len(codes), TOTAL_MONTHS, MONTH_MIN, MONTH_MAX)
    return {"series": series, "monthly_long": full}


def build_daily_series(raw: pd.DataFrame, codes: list) -> dict:
    """True daily forecast_date-keyed series, zero-filled, over the SAME window as the monthly
    grid -- METRICS.md Sec.4's preferred (non-fallback) method, built the same way
    src/phaseE1fix_recompute.py's load_daily_series does, from this script's OWN raw pull."""
    d = raw.dropna(subset=["forecast_date"]).copy()
    d = d[d["forecast_date"] >= d["createDate"]]
    day_min = pd.Period(MONTH_MIN, freq="M").start_time
    day_max = pd.Period(MONTH_MAX, freq="M").end_time.normalize()
    d = d[(d["forecast_date"] >= day_min) & (d["forecast_date"] <= day_max)]

    full_day_index = pd.date_range(day_min, day_max, freq="D")
    daily = d.groupby(["itemcode", d["forecast_date"].dt.normalize()])["qty"].sum()
    item_index = daily.index.get_level_values(0)

    out = {}
    for code in codes:
        s = pd.Series(0.0, index=full_day_index)
        if code in item_index:
            sub = daily.loc[code]
            s.loc[sub.index] = sub.to_numpy(dtype=float)
        out[code] = (s.to_numpy(dtype=float), full_day_index)
    logger.info("Daily series built: %d items x %d days (%s to %s).", len(codes), len(full_day_index),
                day_min.date(), day_max.date())
    return out


def build_item_facts(scope: pd.DataFrame, monthly_long: pd.DataFrame, order_level: pd.DataFrame) -> pd.DataFrame:
    """METRICS.md Sec.15 (corrected): annual_value/order_frequency over the trailing 12 months
    ending at the data cutoff (here, the fixed window's own last month, 2026-07 -- same cutoff
    PEM101 uses, for direct cross-division comparability). Adapted from
    src/phaseE1fix_recompute.py's build_item_facts, which reads a fixed PEM101 file path; this
    version takes the monthly DataFrame this script itself built."""
    data_cutoff_month = pd.Period(MONTH_MAX, freq="M")
    window_months = pd.period_range(data_cutoff_month - 11, data_cutoff_month, freq="M")
    window_months_str = set(str(m) for m in window_months)
    window_start_date = window_months[0].start_time
    window_end_date = data_cutoff_month.end_time
    logger.info("METRICS.md Sec.15 trailing-12-month window: %s to %s", window_months[0], window_months[-1])

    sale_12mo = monthly_long[monthly_long["year_month"].isin(window_months_str)].groupby("itemcode")["sale"].sum()

    ol = order_level.copy()
    ol["createDate"] = pd.to_datetime(ol["createDate"])
    ol_window = ol[(ol["createDate"] >= window_start_date) & (ol["createDate"] <= window_end_date)]
    freq_12mo = ol_window.drop_duplicates(subset=["itemcode", "contractid", "createDate"]).groupby("itemcode").size()

    rows = []
    for _, r in scope.iterrows():
        code = r["code"]
        annual_value = float(sale_12mo.get(code, 0.0))
        order_freq = float(freq_12mo.get(code, 0))
        rows.append({"code": code, "type": r["type"], "eligible_for_policy": r["eligible_for_policy"],
                     "is_excluded": r["is_excluded"], "is_placeholder": r["is_placeholder"],
                     "annual_value_thb": annual_value, "order_freq_per_year": order_freq,
                     "has_history": True})
    return pd.DataFrame(rows)


def main():
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    sl = e1["default_scenario"]["cycle_service_level"]
    full_months, frac_month, protection_days = protection_period_months(e1)
    lead = e1["default_scenario"]["procurement_lead_time_days"]
    assembly = e1["default_scenario"]["assembly_time_days"]
    review = e1["review_interval_days_default"]
    lead_time_days = lead + assembly

    scopes = {div: load_division_scope(config, div) for div in DIVISIONS}
    all_codes = sorted(set().union(*[set(s["code"]) for s in scopes.values()]))
    raw = pull_raw_sales(config, all_codes)
    order_level = query_order_level(all_codes, config)
    median_notice_days = float(order_level["notice_days"].median())

    results = {}
    for division in DIVISIONS:
        logger.info("=" * 90)
        logger.info("DIVISION: %s", division)
        logger.info("=" * 90)
        scope = scopes[division]
        codes = sorted(scope["code"].unique())
        raw_div = raw[raw["itemcode"].isin(codes)]

        series_bundle = build_monthly_series(raw_div, codes)
        daily_series = build_daily_series(raw_div, codes)

        facts = build_item_facts(scope, series_bundle["monthly_long"], order_level[order_level["itemcode"].isin(codes)])
        facts, thresholds = assign_policy_metrics15(
            facts, assembly_time_days=assembly, median_notice_days=median_notice_days)
        sensitivity = threshold_sensitivity(facts, thresholds)
        counts = facts["policy"].value_counts().to_dict()
        logger.info("[%s] METRICS.md Sec.15 policy counts: %s (total %d)", division, counts, len(facts))
        facts.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_1_item_policy.csv"), index=False)
        sensitivity.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_1_threshold_sensitivity.csv"), index=False)

        fg_codes = set(facts[facts["policy"] == "finished_goods_stock"]["code"])
        ltd_input = facts[facts["policy"].isin(["finished_goods_stock", "component_stock_ato"])]
        ltd_df = compute_ltd_and_distribution(scope, series_bundle, ltd_input, full_months, frac_month, sl,
                                               daily_series, protection_days)
        unit_cost_df = compute_unit_cost_metrics1(codes, e1["unit_cost_median_window_months"])
        full_df = compute_max_and_stock_value(ltd_df, scope, series_bundle, facts, unit_cost_df, review)

        stock_value = float(full_df.loc[full_df["code"].isin(fg_codes), "stock_value_contribution"].sum())
        logger.info("[%s] stock_value (Sec.6): THB %.2f", division, stock_value)

        # ---- on-hand / sellable stock, per-division sellable_warehouse_codes (Part 2) ----
        inv = query_inventory_exact(codes)
        sellable = sellable_stock_per_item(inv, codes, e1["sellable_warehouse_codes"][division])
        current_mm = current_minmax_per_item(inv, codes)

        cs_df = sellable.rename(columns={"itemcode": "code"}).merge(
            unit_cost_df.rename(columns={"itemcode": "code"}), on="code", how="left").merge(
            facts[["code", "policy"]], on="code", how="left")
        current_stock_value = float((cs_df.loc[cs_df["code"].isin(fg_codes), "sellable_stock"] *
                                      cs_df.loc[cs_df["code"].isin(fg_codes), "unit_cost"].fillna(0)).sum())
        logger.info("[%s] current_stock_value (Sec.6 comparison, on-hand-based): THB %.2f", division, current_stock_value)

        # ---- two-group reporting: items WITH on-hand stock vs. items with NONE ----
        report_df = full_df.merge(cs_df[["code", "sellable_stock"]], on="code", how="left")
        report_df["sellable_stock"] = report_df["sellable_stock"].fillna(0.0)
        report_df["has_onhand_stock"] = report_df["sellable_stock"] > 0
        report_df["gap_to_min"] = report_df["min_qty"] - report_df["sellable_stock"]
        report_df.loc[~report_df["has_onhand_stock"] & report_df["min_qty"].notna(), "gap_to_min"] = report_df["min_qty"]
        report_df["gap_to_min_is_full_min"] = report_df["min_qty"].notna() & (~report_df["has_onhand_stock"])
        with_stock = report_df[report_df["has_onhand_stock"] & report_df["policy"].isin(
            ["finished_goods_stock", "component_stock_ato"])]
        without_stock = report_df[(~report_df["has_onhand_stock"]) & report_df["policy"].isin(
            ["finished_goods_stock", "component_stock_ato"])]
        logger.info("[%s] Two-group split (FG+ATO items): %d WITH on-hand stock, %d WITH NONE "
                    "(Min/Max still computed from demand, gap_to_min = full Min for these).",
                    division, len(with_stock), len(without_stock))
        report_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_2_minmax_stockvalue_twogroup.csv"), index=False)

        # ---- fill_rate / cycle_service_level, METRICS.md Sec.16 daily simulation ----
        sim_rows = []
        n_no_daily = 0
        for _, r in full_df[full_df["code"].isin(fg_codes)].iterrows():
            code = r["code"]
            if pd.isna(r["min_qty"]) or code not in daily_series:
                n_no_daily += 1
                continue
            qty_daily, _dates = daily_series[code]
            sim = simulate_item_daily(qty_daily, r["min_qty"], r["max_qty"], review, lead_time_days)
            sim["code"] = code
            sim_rows.append(sim)
        sim_df = pd.DataFrame(sim_rows)
        if len(sim_df):
            pooled_fill_rate = sim_df["total_shipped_same_day"].sum() / sim_df["total_demand"].sum()
            pooled_csl = 1 - (sim_df["cycle_stockouts"].sum() / sim_df["cycle_count"].sum())
        else:
            pooled_fill_rate, pooled_csl = float("nan"), float("nan")
        sim_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_2_simulation.csv"), index=False)
        logger.info("[%s] fill_rate=%.4f, cycle_service_level=%.4f (%d items simulated, %d skipped no-daily-history)",
                    division, pooled_fill_rate, pooled_csl, len(sim_df), n_no_daily)

        mase_df = compute_mase(scope, series_bundle, sorted(fg_codes), full_months + (1 if frac_month > 0 else 0))
        mase_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_2_mase.csv"), index=False)

        # ---- top 3 FG items by stock_value_contribution ----
        top3 = full_df[full_df["code"].isin(fg_codes)].sort_values(
            "stock_value_contribution", ascending=False).head(3)
        logger.info("[%s] Top 3 FG items by value:\n%s", division,
                    top3[["code", "LTD", "safety_stock", "min_qty", "max_qty", "stock_value_contribution"]].to_string(index=False))

        results[division] = {
            "facts": facts, "thresholds": thresholds, "sensitivity": sensitivity, "full_df": full_df,
            "report_df": report_df, "stock_value": stock_value, "current_stock_value": current_stock_value,
            "fill_rate": pooled_fill_rate, "cycle_service_level": pooled_csl, "top3": top3,
            "n_with_stock": len(with_stock), "n_without_stock": len(without_stock),
            "n_items": len(scope), "counts": counts, "unit_cost_df": unit_cost_df,
        }

    print("\n" + "=" * 90)
    print("PHASE E2 PILOT MODELER -- PEM103 / PEM107, default scenario, METRICS.md formulas")
    print("=" * 90)
    for division, r in results.items():
        print(f"\n--- {division} ({r['n_items']} items) ---")
        print(f"Segmentation (Sec.15): {r['counts']}")
        print(f"  P50 annual value: THB {r['thresholds']['p50_annual_value_thb']:,.2f}; "
              f"items within +-5%%: {len(r['sensitivity'])}")
        print(f"stock_value (Sec.6): THB {r['stock_value']:,.2f}")
        print(f"current_stock_value (on-hand): THB {r['current_stock_value']:,.2f}")
        print(f"fill_rate: {r['fill_rate']:.4f}, cycle_service_level: {r['cycle_service_level']:.4f}")
        print(f"Two-group: {r['n_with_stock']} items WITH on-hand stock, {r['n_without_stock']} WITH NONE")
        print("Top 3 by value:")
        print(r["top3"][["code", "min_qty", "max_qty", "stock_value_contribution"]].to_string(index=False))

    return results


if __name__ == "__main__":
    main()
