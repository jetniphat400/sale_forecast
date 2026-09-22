"""Phase E2 scoped pilot -- independent Validator, PEM103 and PEM107.

Reads NONE of src/phaseE2_pilot_recompute.py's output files. Its own scope derivation, its own
live raw-data pull (this script's own single DATABASE ACCESS RULE attempt), its own monthly/daily
series builders (independently coded below -- different aggregation style, pandas pivot_table
rather than the Modeler's groupby+reindex). Reuses only already-independent, already-verified
generic functions from src/investigations/phaseE1fix_validator.py (classify_segment,
ltd_and_safety_stock, historical_window_sum, daily_rolling_windows, prorate_weights,
month_starts_after, fit_topdown_forecast, part_c1_stock_value, part_c2_simulation, simulate_item)
-- none of those read a fixed PEM101 file path or assume the 128-item pilot scope; they were
already parameter-generic before this task.
"""
import logging
import math
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))          # src/investigations
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src

from db import run_query
from pricelist_reader import load_visible_product_rows
import phaseE1_common as pc
from phaseE1fix_validator import (
    classify_segment, ltd_and_safety_stock, fit_topdown_forecast,
    part_c1_stock_value, part_c2_simulation, prorate_weights,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE2_pilot_validator")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
DIVISIONS = ["PEM103", "PEM107"]
MONTH_MIN, MONTH_MAX = "2024-01", "2026-07"  # same fixed common window as the Modeler


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def own_division_scope(config: dict, division: str) -> pd.DataFrame:
    """Own re-derivation from the pricelist, independent of the Modeler's scope loader."""
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    pl = pl.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    sheet_to_division = config["sheet_to_division"]
    pl["division"] = pl["sheet"].map(sheet_to_division)
    rows = pl[pl["division"] == division][["code", "type", "category"]].copy()
    rows["eligible_for_policy"] = True
    logger.info("OWN division scope for %s: %d codes.", division, len(rows))
    return rows


def own_raw_pull(config: dict, codes: list) -> pd.DataFrame:
    revenue_type = config["revenue_type"]
    statuses = "','".join(config["status_basis"])
    start_date = config["date_range"]["start"]
    code_list = "','".join(sorted(codes))
    sql = f"""
        SELECT itemcode, contractid, createDate, forecast_date, qty, sale
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}') AND revenue_type = '{revenue_type}'
          AND status IN ('{statuses}') AND createDate >= '{start_date}'
    """
    try:
        df = run_query(sql)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: single connection attempt failed, not retrying. Error: %r", exc)
        raise
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    logger.info("OWN raw pull: %d rows for %d items.", len(df), len(codes))
    return df


def own_monthly_series(raw: pd.DataFrame, codes: list) -> dict:
    """Independently built via pivot_table (Modeler used groupby+reindex) -- same filter rule
    (forecast_date not null, forecast_date >= createDate), same fixed 31-month window."""
    d = raw.dropna(subset=["forecast_date"])
    d = d[d["forecast_date"] >= d["createDate"]].copy()
    d["year_month"] = d["forecast_date"].dt.to_period("M").astype(str)
    months = [str(p) for p in pd.period_range(MONTH_MIN, MONTH_MAX, freq="M")]
    d = d[d["year_month"].isin(months)]

    pivot_qty = d.pivot_table(index="itemcode", columns="year_month", values="qty", aggfunc="sum", fill_value=0.0)
    pivot_sale = d.pivot_table(index="itemcode", columns="year_month", values="sale", aggfunc="sum", fill_value=0.0)
    pivot_qty = pivot_qty.reindex(index=codes, columns=months, fill_value=0.0)
    pivot_sale = pivot_sale.reindex(index=codes, columns=months, fill_value=0.0)

    series = {code: (pivot_qty.loc[code].to_numpy(dtype=float), months) for code in codes}
    monthly_long = pivot_sale.reset_index().melt(id_vars="itemcode", var_name="year_month", value_name="sale")
    logger.info("OWN monthly series (pivot_table): %d items x %d months.", len(codes), len(months))
    return series, monthly_long


def own_daily_series(raw: pd.DataFrame, codes: list) -> dict:
    """Independently built (pivot_table), same window as the monthly series."""
    d = raw.dropna(subset=["forecast_date"])
    d = d[d["forecast_date"] >= d["createDate"]].copy()
    day_min = pd.Period(MONTH_MIN, freq="M").start_time
    day_max = pd.Period(MONTH_MAX, freq="M").end_time.normalize()
    d = d[(d["forecast_date"] >= day_min) & (d["forecast_date"] <= day_max)]

    pivot = d.pivot_table(index=d["forecast_date"].dt.normalize(), columns="itemcode", values="qty",
                           aggfunc="sum", fill_value=0.0)
    full_idx = pd.date_range(day_min, day_max, freq="D")
    pivot = pivot.reindex(index=full_idx, columns=codes, fill_value=0.0)
    logger.info("OWN daily series (pivot_table): %d items x %d days.", len(codes), len(full_idx))
    return {code: pivot[code].to_numpy(dtype=float) for code in codes}


def own_annual_value_and_frequency(config: dict, codes: list, monthly_long: pd.DataFrame) -> tuple:
    """METRICS.md Sec.15: trailing 12 months ending at the data cutoff (fixed window's own last
    month, matching the Modeler's cutoff for cross-division comparability)."""
    cutoff = pd.Period(MONTH_MAX, freq="M")
    window = set(str(p) for p in pd.period_range(cutoff - 11, cutoff, freq="M"))
    av = monthly_long[monthly_long["year_month"].isin(window)].groupby("itemcode", as_index=False)["sale"].sum()
    av = av.rename(columns={"sale": "annual_value_thb"})
    av = pd.DataFrame({"itemcode": codes}).merge(av, on="itemcode", how="left")
    av["annual_value_thb"] = av["annual_value_thb"].fillna(0.0)

    ol = pc.query_order_level(codes, config)
    window_start = pd.Period(min(window), freq="M").start_time
    window_end = cutoff.end_time
    ol_win = ol[(ol["createDate"] >= window_start) & (ol["createDate"] <= window_end)]
    dedup = ol_win.drop_duplicates(subset=["itemcode", "contractid", "createDate"])
    freq = dedup.groupby("itemcode", as_index=False).size().rename(columns={"size": "order_freq_per_year"})
    freq = pd.DataFrame({"itemcode": codes}).merge(freq, on="itemcode", how="left")
    freq["order_freq_per_year"] = freq["order_freq_per_year"].fillna(0).astype(float)
    median_notice = ol["notice_days"].median()
    return av, freq, median_notice, cutoff


def main():
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    default = e1["default_scenario"]
    lead, assembly, sl = default["procurement_lead_time_days"], default["assembly_time_days"], default["cycle_service_level"]
    review = e1["review_interval_days_default"]
    protection_period_days = lead + assembly + review
    freq_cutoff_per_year = config["segment_policy"]["order_freq_cutoff_per_year"]

    results = {}
    for division in DIVISIONS:
        logger.info("=" * 90)
        logger.info("OWN DIVISION: %s", division)
        logger.info("=" * 90)
        scope = own_division_scope(config, division)
        codes = sorted(scope["code"].unique())
        raw = own_raw_pull(config, codes)
        series, monthly_long = own_monthly_series(raw, codes)
        daily_series = own_daily_series(raw, codes)
        last_month_end = pd.Period(MONTH_MAX, freq="M").end_time

        av, freq, median_notice, cutoff = own_annual_value_and_frequency(config, codes, monthly_long)
        merged = av.merge(freq, on="itemcode")
        own_p50 = float(merged["annual_value_thb"].median())
        logger.info("[%s] OWN P50 annual_value_thb: %.2f (median notice %.2f days)", division, own_p50, median_notice)

        merged["segment"] = merged.apply(
            lambda r: classify_segment(r["annual_value_thb"], own_p50, r["order_freq_per_year"],
                                        freq_cutoff_per_year, assembly, median_notice), axis=1)
        merged["pct_from_value_threshold"] = np.where(
            own_p50 != 0, (merged["annual_value_thb"] - own_p50) / own_p50 * 100, np.nan)
        merged["pct_from_freq_threshold"] = (merged["order_freq_per_year"] - freq_cutoff_per_year) / freq_cutoff_per_year * 100
        merged["near_value_threshold"] = merged["pct_from_value_threshold"].abs() <= 5
        merged["near_freq_threshold"] = merged["pct_from_freq_threshold"].abs() <= 5
        counts = merged["segment"].value_counts().to_dict()
        n_zero_value = int((merged["annual_value_thb"] == 0).sum())
        logger.info("[%s] OWN segment counts: %s (%d/%d items have ZERO trailing-12mo annual_value)",
                    division, counts, n_zero_value, len(merged))
        merged.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_validator_{division}_segmentation.csv"), index=False)

        fg_codes = merged.loc[merged["segment"] == "finished_goods_stock", "itemcode"].tolist()

        c1_summary, c1_detail = part_c1_stock_value(config, scope, series, fg_codes, last_month_end, daily_series)
        logger.info("[%s] OWN stock_value: %s", division, c1_summary)

        c2_summary, c2_detail = part_c2_simulation(config, scope, series, c1_detail.rename(
            columns={"itemcode": "itemcode"}), last_month_end, daily_series)
        logger.info("[%s] OWN simulation: %s", division, c2_summary)

        # top 3 by value (from c1_detail's own stock_value_item)
        top3 = c1_detail.sort_values("stock_value_item", ascending=False).head(3)
        top3_forecasts = fit_topdown_forecast(scope, series, top3["itemcode"].tolist(),
                                               math.ceil(protection_period_days / 30.44) + 1)
        top3_rows = []
        for _, r in top3.iterrows():
            code = r["itemcode"]
            qty, months = series[code]
            fc = top3_forecasts.get(code)
            if fc is None:
                continue
            res = ltd_and_safety_stock(qty, months, fc, last_month_end, protection_period_days, sl,
                                        daily_qty=daily_series.get(code))
            res["itemcode"] = code
            res["stock_value_item"] = r["stock_value_item"]
            top3_rows.append(res)
        top3_df = pd.DataFrame(top3_rows)
        top3_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_validator_{division}_top3_min.csv"), index=False)
        logger.info("[%s] OWN top 3 by value, Min:\n%s", division,
                    top3_df[["itemcode", "ltd", "safety_stock", "min", "stock_value_item"]].to_string(index=False)
                    if len(top3_df) else "(none)")

        results[division] = {
            "own_p50": own_p50, "counts": counts, "merged": merged, "c1_summary": c1_summary,
            "c2_summary": c2_summary, "top3_df": top3_df, "n_zero_value": n_zero_value,
        }

    print("\n" + "=" * 90)
    print("PHASE E2 PILOT VALIDATOR -- PEM103 / PEM107, independent recomputation")
    print("=" * 90)
    for division, r in results.items():
        print(f"\n--- {division} ---")
        print(f"OWN P50 annual_value_thb: {r['own_p50']:.2f} ({r['n_zero_value']} items with zero trailing-12mo value)")
        print(f"OWN segment counts: {r['counts']}")
        print(f"OWN stock_value: THB {r['c1_summary']['total_stock_value_thb']:,.2f}")
        print(f"OWN fill_rate: {r['c2_summary']['fill_rate_unit_weighted']:.4f}, "
              f"cycle_service_level: {r['c2_summary']['cycle_service_level_pooled']:.4f}")
        print("OWN top 3 by value, Min:")
        print(r["top3_df"][["itemcode", "min", "stock_value_item"]].to_string(index=False) if len(r["top3_df"]) else "(none)")

    return results


if __name__ == "__main__":
    main()
