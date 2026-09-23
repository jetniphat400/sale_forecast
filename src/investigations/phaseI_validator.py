"""Phase I Part 4 -- independent Validator.

Written independently of src/investigations/phaseI_sensitivity_engine.py and
phaseI_run_sweeps.py/phaseI_two_way.py (the Analyst's own new scripts for this task) -- does NOT
import or read either. Every formula below (policy assignment, unit cost, protection period, LTD/
safety stock, Min/Max, stock_value) is re-derived here from METRICS.md directly, in this
Validator's own code, following the same precedent as src/investigations/phaseE1fix_validator.py
(see its own docstring): reuse only PRE-EXISTING, previously-verified helpers that predate this
task (src/phaseE1_common.py's load_scope/topdown_item_forecast, src/phaseE2_pilot_recompute.py's
load_division_scope/build_monthly_series/build_daily_series -- data-loading/forecasting
infrastructure, not the metric formulas under test here), never the Analyst's new Phase I code.

Data source: the SAME single cached pull (output/data/phaseI_raw_sales_351items.csv,
phaseI_inventory_exact_351items.csv) -- re-querying the database a second time for this Validator
would violate this task's DATABASE ACCESS RULE (one connection attempt only, for the whole task,
already spent). Reading the raw pull is not "reading the Analyst's files" -- it is the shared raw
extract neither agent may re-fetch; the Analyst's DERIVED outputs (output/summary/phaseI_1_*,
phaseI_2_*, phaseI_3_*) are what this Validator's computation code never reads. The final
comparison step at the bottom of main() necessarily reads both sides -- that is the comparison
report, not the independent computation itself.

Scope, per task Part 4: the default row, plus the EXTREME (largest max_value_shift) end of every
assumption the Analyst found RELEVANT at the 10% threshold, for the three focus codes
(EEE-F-FC-1040010002, HS-F-99-02110, HS-F-99-0213) and each division's TOTAL stock_value.
"""
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, load_scope, topdown_item_forecast
from phaseE2_pilot_recompute import load_division_scope, build_monthly_series, build_daily_series, TOTAL_MONTHS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseI_validator")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
RAW_SALES_FILE = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")
INV_FILE = os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv")
DAYS_PER_MONTH = 30.44
FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

DEFAULTS = {
    "procurement_lead_time_days": 60, "assembly_time_days": 3, "review_interval_days": 30,
    "cycle_service_level": 0.95, "unit_cost_window_months": 12, "freq_cutoff_per_year": 6.0,
}

# ---- Validator's assignment: default + the extreme end of every RELEVANT assumption, per
# division, as determined by the Orchestrator from the Analyst's Part 1/2 classification (the
# Orchestrator reads that classification to decide WHAT to assign; this SCRIPT never reads it). ----
ASSIGNMENT = {
    "PEM101": {
        "procurement_lead_time_days": 30, "assembly_time_days": 14, "review_interval_days": 7,
        "cycle_service_level": 0.80, "freq_cutoff_per_year": 4.0,
    },
    "PEM103": {
        "procurement_lead_time_days": 30, "assembly_time_days": 14, "review_interval_days": 7,
        "cycle_service_level": 0.80, "unit_cost_window_months": 6, "freq_cutoff_per_year": 4.0,
    },
    "PEM107": {
        "procurement_lead_time_days": 30, "review_interval_days": 7,
        "cycle_service_level": 0.80, "unit_cost_window_months": 6, "freq_cutoff_per_year": 4.0,
    },
}


def load_raw_and_inv() -> tuple:
    raw = pd.read_csv(RAW_SALES_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    inv = pd.read_csv(INV_FILE)
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    return raw, inv


def get_scope(config: dict, division: str) -> pd.DataFrame:
    return load_scope(config) if division == "PEM101" else load_division_scope(config, division)


# ---- METRICS.md Sec.15, independently coded (merge-based, not the Analyst's apply()-based code) ----
def validator_facts(scope: pd.DataFrame, raw_div: pd.DataFrame, monthly_long: pd.DataFrame,
                     month_max: str) -> pd.DataFrame:
    cutoff = pd.Period(month_max, freq="M")
    win_start_date = (cutoff - 11).start_time
    win_end_date = cutoff.end_time
    win_months = {str(cutoff - i) for i in range(12)}

    sale12 = (monthly_long[monthly_long["year_month"].isin(win_months)]
              .groupby("itemcode")["sale"].sum().rename("annual_value_thb"))

    ol = raw_div[(raw_div["forecast_date"].notna()) & (raw_div["forecast_date"] >= raw_div["createDate"])]
    ol = ol[(ol["createDate"] >= win_start_date) & (ol["createDate"] <= win_end_date)]
    freq12 = (ol.drop_duplicates(subset=["itemcode", "contractid", "createDate"])
              .groupby("itemcode").size().rename("order_freq_per_year"))

    cols = ["code", "type"]
    for extra in ("is_excluded", "is_placeholder", "eligible_for_policy"):
        if extra in scope.columns:
            cols.append(extra)
    facts = scope[cols].merge(sale12, left_on="code", right_index=True, how="left") \
                        .merge(freq12, left_on="code", right_index=True, how="left")
    facts["annual_value_thb"] = facts["annual_value_thb"].fillna(0.0)
    facts["order_freq_per_year"] = facts["order_freq_per_year"].fillna(0.0)
    if "is_excluded" not in facts.columns:
        facts["is_excluded"] = False
    if "is_placeholder" not in facts.columns:
        facts["is_placeholder"] = False
    return facts


def validator_policy(facts: pd.DataFrame, assembly_time_days: float, median_notice_days: float,
                      freq_cutoff: float) -> pd.DataFrame:
    """METRICS.md Sec.15 -- config item-status overrides (excluded/placeholder, config.yaml
    excluded_item_codes/placeholder_item_codes, PEM101 128-item pilot only) take priority over the
    value/frequency criteria, per phaseE1_common.load_scope's is_excluded/is_placeholder flags --
    matches the Analyst engine's assign_policy_param precedence (excluded > placeholder > value/
    frequency), independently re-derived here rather than assumed."""
    elig = facts[~(facts["is_excluded"] | facts["is_placeholder"])]
    p50 = float(elig["annual_value_thb"].median())
    out = facts.copy()

    if p50 == 0.0:
        value_freq_policy = np.where(out["order_freq_per_year"] >= freq_cutoff, "finished_goods_stock",
                                      np.where(assembly_time_days <= median_notice_days, "component_stock_ato",
                                               "UNDEFINED"))
    else:
        is_fg = (out["annual_value_thb"] >= p50) | (out["order_freq_per_year"] >= freq_cutoff)
        value_freq_policy = np.where(is_fg, "finished_goods_stock",
                                      np.where(assembly_time_days <= median_notice_days, "component_stock_ato",
                                               "UNDEFINED"))
    out["policy"] = np.select([out["is_excluded"], out["is_placeholder"]],
                               ["excluded", "placeholder"], default=value_freq_policy)
    out["p50_used"] = p50
    return out


# ---- METRICS.md Sec.1, independently coded ----
def validator_unit_cost(raw_div: pd.DataFrame, window_months: int) -> pd.Series:
    d = raw_div[raw_div["qty"].notna() & (raw_div["qty"] != 0) & raw_div["cost"].notna()].copy()
    d["uc"] = d["cost"] / d["qty"]
    anchor = d["createDate"].max()
    win = d[d["createDate"] >= anchor - pd.DateOffset(months=window_months)]
    n_rows = win.groupby("itemcode").size()
    med = win.groupby("itemcode")["uc"].median()
    last_date = d.groupby("itemcode")["createDate"].transform("max")
    recent = d[d["createDate"] == last_date].groupby("itemcode")["uc"].mean()
    codes = sorted(raw_div["itemcode"].unique())
    result = {}
    for c in codes:
        if n_rows.get(c, 0) >= 3:
            result[c] = med[c]
        elif c in recent.index:
            result[c] = recent[c]
        else:
            result[c] = np.nan
    return pd.Series(result, name="unit_cost")


# ---- METRICS.md Sec.2-6, independently coded ----
def validator_minmax(scope: pd.DataFrame, series: dict, daily_series: dict, facts_policy: pd.DataFrame,
                      lead: float, assembly: float, review: float, sl: float) -> pd.DataFrame:
    protection_days = lead + assembly + review
    months_float = protection_days / DAYS_PER_MONTH
    full_m = int(months_float)  # floor for positive floats
    frac_m = months_float - full_m
    horizon = full_m + (1 if frac_m > 0 else 0)

    review_months_float = review / DAYS_PER_MONTH
    review_full = int(review_months_float)
    review_frac = review_months_float - review_full
    extra_needed = review_full + (1 if review_frac > 0 else 0)
    total_horizon = horizon + extra_needed

    eligible = facts_policy[facts_policy["policy"].isin(["finished_goods_stock", "component_stock_ato"])]
    fc_total = topdown_item_forecast(scope, series, fit_end=TOTAL_MONTHS, horizon=total_horizon)

    rows = []
    for _, r in eligible.iterrows():
        code = r["code"]
        if code not in fc_total or code not in daily_series:
            continue
        fc = fc_total[code]
        ltd = float(fc[:full_m].sum())
        if frac_m > 0:
            ltd += frac_m * fc[full_m]

        qty_d, _ = daily_series[code]
        n_d = len(qty_d)
        if protection_days <= 0 or protection_days > n_d:
            continue
        csum = np.concatenate([[0.0], np.cumsum(qty_d)])
        cum = csum[int(protection_days):] - csum[:-int(protection_days)]
        pct = float(np.percentile(cum, sl * 100))
        safety = max(0.0, pct - ltd)
        min_qty = ltd + safety

        replen = fc[horizon: horizon + review_full].sum()
        if review_frac > 0 and horizon + review_full < len(fc):
            replen += review_frac * fc[horizon + review_full]
        max_qty = min_qty + float(replen)
        rows.append({"code": code, "policy": r["policy"], "LTD": ltd, "safety_stock": safety,
                     "min_qty": min_qty, "max_qty": max_qty})
    return pd.DataFrame(rows)


def run_one(config: dict, division: str, raw: pd.DataFrame, inv: pd.DataFrame, params: dict) -> dict:
    scope = get_scope(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)].copy()

    series_bundle = build_monthly_series(raw_div, codes)
    daily_series = build_daily_series(raw_div, codes)
    month_max = series_bundle["series"][codes[0]][1][-1]

    ol_all = raw_div[(raw_div["forecast_date"].notna()) & (raw_div["forecast_date"] >= raw_div["createDate"])]
    notice_days = (ol_all["forecast_date"] - ol_all["createDate"]).dt.days
    median_notice = float(notice_days.median())

    facts = validator_facts(scope, raw_div, series_bundle["monthly_long"], month_max)
    facts_policy = validator_policy(facts, params["assembly_time_days"], median_notice, params["freq_cutoff_per_year"])

    minmax_df = validator_minmax(scope, series_bundle["series"], daily_series, facts_policy,
                                  params["procurement_lead_time_days"], params["assembly_time_days"],
                                  params["review_interval_days"], params["cycle_service_level"])

    unit_cost = validator_unit_cost(raw_div, params["unit_cost_window_months"])
    minmax_df = minmax_df.merge(unit_cost.rename("unit_cost"), left_on="code", right_index=True, how="left")
    minmax_df["stock_value_contribution"] = np.where(
        (minmax_df["policy"] == "finished_goods_stock") & minmax_df["unit_cost"].notna(),
        minmax_df["min_qty"] * minmax_df["unit_cost"], 0.0)

    total_stock_value = float(minmax_df.loc[minmax_df["policy"] == "finished_goods_stock",
                                             "stock_value_contribution"].sum())
    focus = minmax_df[minmax_df["code"].isin(FOCUS_ITEMS)][["code", "policy", "min_qty", "max_qty",
                                                             "stock_value_contribution"]]
    return {"total_stock_value": total_stock_value, "focus": focus, "minmax_df": minmax_df,
            "policy_counts": facts_policy["policy"].value_counts().to_dict()}


def main():
    config = load_config()
    raw, inv = load_raw_and_inv()

    rows = []
    focus_rows = []
    for division in ["PEM101", "PEM103", "PEM107"]:
        logger.info("=" * 90)
        logger.info("VALIDATOR: %s", division)
        logger.info("=" * 90)

        default_out = run_one(config, division, raw, inv, DEFAULTS)
        rows.append({"division": division, "scenario": "default", "changed_param": None, "value": None,
                     "total_stock_value": default_out["total_stock_value"],
                     "policy_counts": default_out["policy_counts"]})
        for _, r in default_out["focus"].iterrows():
            focus_rows.append({"division": division, "scenario": "default", "changed_param": None,
                               "value": None, **r.to_dict()})

        for param, value in ASSIGNMENT.get(division, {}).items():
            params = dict(DEFAULTS)
            params[param] = value
            out = run_one(config, division, raw, inv, params)
            rows.append({"division": division, "scenario": param, "changed_param": param, "value": value,
                        "total_stock_value": out["total_stock_value"], "policy_counts": out["policy_counts"]})
            for _, r in out["focus"].iterrows():
                focus_rows.append({"division": division, "scenario": param, "changed_param": param,
                                   "value": value, **r.to_dict()})
            logger.info("[%s] %s=%s -> Validator total_stock_value=%.2f", division, param, value,
                        out["total_stock_value"])

    validator_totals = pd.DataFrame(rows)
    validator_focus = pd.DataFrame(focus_rows)
    validator_totals.to_csv(os.path.join(SUMMARY_DIR, "phaseI_4_validator_totals.csv"), index=False)
    validator_focus.to_csv(os.path.join(SUMMARY_DIR, "phaseI_4_validator_focus_items.csv"), index=False)

    # ---- Comparison against the Analyst's saved outputs (this IS the comparison step; it reads
    # both sides by necessity) ----
    analyst_scen = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseI_1_scenario_results.csv"))
    compare_rows = []
    for _, vr in validator_totals.iterrows():
        division = vr["division"]
        if vr["scenario"] == "default":
            a = analyst_scen[(analyst_scen["division"] == division) & (analyst_scen["is_default"])]
        else:
            a = analyst_scen[(analyst_scen["division"] == division) &
                              (analyst_scen["assumption"] == vr["changed_param"]) &
                              (pd.to_numeric(analyst_scen["value"], errors="coerce").round(6) ==
                               round(float(vr["value"]), 6))]
        if not len(a):
            compare_rows.append({"division": division, "scenario": vr["scenario"], "value": vr["value"],
                                 "validator_stock_value": vr["total_stock_value"], "analyst_stock_value": None,
                                 "match": None, "note": "no matching Analyst row found"})
            continue
        analyst_sv = float(a["stock_value"].iloc[0])
        pct_diff = abs(vr["total_stock_value"] - analyst_sv) / analyst_sv * 100 if analyst_sv else float("nan")
        compare_rows.append({"division": division, "scenario": vr["scenario"], "value": vr["value"],
                             "validator_stock_value": vr["total_stock_value"], "analyst_stock_value": analyst_sv,
                             "pct_diff": pct_diff, "match": pct_diff < 1.0 if pd.notna(pct_diff) else None})
    compare_df = pd.DataFrame(compare_rows)
    compare_df.to_csv(os.path.join(SUMMARY_DIR, "phaseI_4_validator_comparison.csv"), index=False)

    print("\n" + "=" * 100)
    print("PHASE I PART 4 -- VALIDATOR COMPARISON (match = within 1% of the Analyst's figure)")
    print("=" * 100)
    print(compare_df.to_string(index=False))
    n_match = int(compare_df["match"].sum()) if "match" in compare_df else 0
    n_total = len(compare_df)
    print(f"\n{n_match}/{n_total} scenarios matched within 1%.")

    return validator_totals, validator_focus, compare_df


if __name__ == "__main__":
    main()
