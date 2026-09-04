"""Task (2026-09-01), Part 2: how far ahead do customer orders provide notice?

Definition given directly by the business (not re-derived here): `createDate`
is when the PO was received, `forecast_date` is the contractual delivery
date. Notice period = forecast_date - createDate, in days, for every sales
row of the 128-item Category/Type/Item scope (output/summary/
part1_category_scope_all_codes.csv).

Scope decision (stated explicitly): uses the SAME filters as the rest of
this project's forecasting pipeline — division='PEM101', revenue_type='Omni
Channel', status IN ('Actual','MPS'), createDate >= 2024-01-01 (the evidenced
usable-data boundary — see STATUS.md Part 2 of the history-depth
investigation). This is a scope choice, not a data limitation: forecast_date
itself is not restricted to any status or division, but computing notice
periods for rows outside this project's established scope (other divisions,
other revenue types, or the pre-2024 window proven structurally absent for
this division/revenue_type combination) would mix in business the rest of
this project treats as out of scope.

Known data-quality caveat, reported rather than hidden: an earlier
investigation (STATUS.md, duplicate-vs-split-lot task) found forecast_date
sometimes steps forward across repeated rows of the same contract (e.g. one
set's rows step exactly 30 days apart), consistent with forecast_date being
UPDATED as a multi-tranche order's plan evolves, not necessarily fixed at the
moment the PO was first received. This script cannot distinguish "notice
given at PO intake" from "notice implied by the latest known delivery plan"
— reported as an open question, not resolved here.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query
from investigate_spikes import SPIKE_MULTIPLIER, find_spikes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("order_leadtime")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

DIVISION = "PEM101"
REVENUE_TYPE = "Omni Channel"
STATUSES = ["Actual", "MPS"]
START_DATE = "2024-01-01"

NOTICE_BUCKETS_DAYS = [30, 60, 90, 120, 150, 180]  # "at least N months" cutoffs, N=1..6 (30-day months)


def get_scope() -> pd.DataFrame:
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))


def pull_raw(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(item_codes)
    status_list = "','".join(STATUSES)
    sql = f"""
        SELECT itemcode, contractid, customerid, createDate, forecast_date, qty, sale, status
        FROM cube_Sale_APD
        WHERE itemcode IN ('{code_list}')
          AND division = '{DIVISION}' AND revenue_type = '{REVENUE_TYPE}'
          AND status IN ('{status_list}') AND createDate >= '{START_DATE}'
    """
    df = run_query(sql)
    logger.info("Pulled %d raw rows (%d items, division=%s, revenue_type=%s, status in %s, createDate >= %s)",
                len(df), len(item_codes), DIVISION, REVENUE_TYPE, STATUSES, START_DATE)
    return df


def validate_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    n_rows = len(df)
    df = df.copy()
    df["createDate"] = pd.to_datetime(df["createDate"])

    n_null_forecast = df["forecast_date"].isna().sum()
    logger.info("%d of %d rows (%.2f%%) have a NULL forecast_date — dropped from the notice-period analysis "
                "(cannot compute an interval without it), kept in the raw pull for the record",
                n_null_forecast, n_rows, 100 * n_null_forecast / n_rows if n_rows else 0)

    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    n_unparseable = df["forecast_date"].isna().sum() - n_null_forecast
    if n_unparseable > 0:
        logger.warning("%d additional rows had an unparseable (non-null but invalid) forecast_date — also dropped", n_unparseable)

    clean = df.dropna(subset=["forecast_date"]).copy()
    clean["notice_days"] = (clean["forecast_date"] - clean["createDate"]).dt.days

    n_negative = (clean["notice_days"] < 0).sum()
    logger.info("%d of %d assessable rows (%.2f%%) have a NEGATIVE notice period (forecast_date before createDate) "
                "— reported separately below as a data-quality anomaly, EXCLUDED from the main notice-period "
                "distribution since a negative 'notice' is not a meaningful lead time",
                n_negative, len(clean), 100 * n_negative / len(clean) if len(clean) else 0)

    return clean, df


def bucket_shares(notice_days: pd.Series) -> pd.DataFrame:
    rows = []
    n = len(notice_days)
    for days in NOTICE_BUCKETS_DAYS:
        n_meeting = (notice_days >= days).sum()
        rows.append({"min_notice_days": days, "min_notice_months_approx": round(days / 30, 1),
                     "n_orders_meeting": int(n_meeting), "pct_of_orders": round(100 * n_meeting / n, 2) if n else None})
    return pd.DataFrame(rows)


def distribution_stats(notice_days: pd.Series) -> dict:
    return {
        "n": len(notice_days), "mean": float(notice_days.mean()), "median": float(notice_days.median()),
        "std": float(notice_days.std()), "q1": float(notice_days.quantile(0.25)), "q3": float(notice_days.quantile(0.75)),
        "iqr": float(notice_days.quantile(0.75) - notice_days.quantile(0.25)),
        "min": float(notice_days.min()), "max": float(notice_days.max()),
        "skewness": float(stats.skew(notice_days)), "kurtosis_excess": float(stats.kurtosis(notice_days)),
    }


if __name__ == "__main__":
    scope = get_scope()
    item_codes = sorted(scope["code"].unique())
    item_type_map = scope.set_index("code")[["category", "type"]]

    raw = pull_raw(item_codes)
    raw.to_csv(os.path.join(DATA_DIR, "raw_order_leadtime_128items.csv"), index=False)

    clean, all_with_null = validate_and_clean(raw)
    clean = clean.merge(item_type_map, left_on="itemcode", right_index=True, how="left")
    clean["year"] = clean["createDate"].dt.year

    negative = clean[clean["notice_days"] < 0]
    positive = clean[clean["notice_days"] >= 0].copy()
    negative.to_csv(os.path.join(SUMMARY_DIR, "leadtime_negative_notice_anomalies.csv"), index=False)
    positive.to_csv(os.path.join(DATA_DIR, "processed_order_leadtime_clean.csv"), index=False)

    # ================= OVERALL DISTRIBUTION =================
    overall_stats = distribution_stats(positive["notice_days"])
    pd.DataFrame([overall_stats]).to_csv(os.path.join(SUMMARY_DIR, "leadtime_overall_distribution.csv"), index=False)

    overall_buckets = bucket_shares(positive["notice_days"])
    overall_buckets.to_csv(os.path.join(SUMMARY_DIR, "leadtime_notice_buckets_overall.csv"), index=False)

    # ================= BY PRODUCT TYPE =================
    by_type = positive.groupby("type")["notice_days"].apply(lambda s: pd.Series(distribution_stats(s))).unstack()
    by_type = by_type.sort_values("median")
    by_type.to_csv(os.path.join(SUMMARY_DIR, "leadtime_by_product_type.csv"))

    # ================= BY CUSTOMER (top 15 by order count) =================
    cust_counts = positive["customerid"].value_counts()
    top_customers = cust_counts.head(15).index.tolist()
    by_customer = positive[positive["customerid"].isin(top_customers)].groupby("customerid")["notice_days"].apply(
        lambda s: pd.Series(distribution_stats(s))).unstack()
    by_customer = by_customer.join(cust_counts.rename("n_orders_total_in_scope"))
    by_customer = by_customer.sort_values("n_orders_total_in_scope", ascending=False)
    by_customer.to_csv(os.path.join(SUMMARY_DIR, "leadtime_by_top15_customers.csv"))

    # Dispersion ACROSS customers (do different customers behave very differently?)
    per_customer_median = positive.groupby("customerid")["notice_days"].median()
    cross_customer_dispersion = {
        "n_customers": len(per_customer_median), "median_of_customer_medians": float(per_customer_median.median()),
        "std_of_customer_medians": float(per_customer_median.std()),
        "min_customer_median": float(per_customer_median.min()), "max_customer_median": float(per_customer_median.max()),
    }

    # ================= BY YEAR (stability check) =================
    by_year = positive.groupby("year")["notice_days"].apply(lambda s: pd.Series(distribution_stats(s))).unstack()
    by_year.to_csv(os.path.join(SUMMARY_DIR, "leadtime_by_year.csv"))
    complete_years = [y for y in by_year.index if y in (2024, 2025)]  # 2026 is partial (data ends 2026-08-28)

    # ================= SPIKE vs NORMAL MONTHS =================
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = monthly[monthly["year_month"] != str(pd.Period(pd.to_datetime(raw["createDate"]).max(), freq="M"))]
    spikes = find_spikes(monthly)
    spike_key = set(zip(spikes["itemcode"], spikes["year_month"]))
    positive = positive.copy()
    positive["year_month"] = positive["createDate"].dt.to_period("M").astype(str)
    positive["is_spike_month"] = positive.apply(lambda r: (r["itemcode"], r["year_month"]) in spike_key, axis=1)

    spike_notice = positive.loc[positive["is_spike_month"], "notice_days"]
    normal_notice = positive.loc[~positive["is_spike_month"], "notice_days"]
    spike_stats = distribution_stats(spike_notice) if len(spike_notice) else None
    normal_stats = distribution_stats(normal_notice) if len(normal_notice) else None
    if len(spike_notice) > 1 and len(normal_notice) > 1:
        u_stat, p_value = stats.mannwhitneyu(spike_notice, normal_notice, alternative="two-sided")
    else:
        u_stat, p_value = np.nan, np.nan
    spike_vs_normal = pd.DataFrame([
        {"group": "spike_month_orders", **(spike_stats or {})},
        {"group": "normal_month_orders", **(normal_stats or {})},
    ])
    spike_vs_normal.to_csv(os.path.join(SUMMARY_DIR, "leadtime_spike_vs_normal_months.csv"), index=False)

    # value-weighted view: does spike-month VALUE carry more or less notice?
    positive["notice_bucket_ge_30d"] = positive["notice_days"] >= 30
    value_by_spike_and_bucket = positive.groupby(["is_spike_month", "notice_bucket_ge_30d"])["sale"].sum().reset_index()
    value_by_spike_and_bucket.to_csv(os.path.join(SUMMARY_DIR, "leadtime_spike_value_by_notice_bucket.csv"), index=False)

    # ============================= CHARTS =============================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4.5))
    capped = positive["notice_days"].clip(upper=180)
    ax.hist(capped, bins=60, color="tab:blue", edgecolor="white")
    ax.set_title("Order notice period (createDate to forecast_date), capped at 180 days")
    ax.set_xlabel("Notice days")
    ax.set_ylabel("Number of order rows")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "leadtime_notice_distribution.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(overall_buckets["min_notice_months_approx"].astype(str) + "mo", overall_buckets["pct_of_orders"], color="tab:green")
    ax.set_title("Share of orders with at least N months' notice")
    ax.set_ylabel("% of orders")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "leadtime_notice_buckets.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.boxplot([spike_notice.clip(upper=180), normal_notice.clip(upper=180)], tick_labels=["Spike months", "Normal months"], showfliers=False)
    ax.set_title("Notice period: spike vs normal months (outliers hidden, capped at 180d)")
    ax.set_ylabel("Notice days")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "leadtime_spike_vs_normal.png"))
    plt.close(fig)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 92)
    print("# PART 2: ORDER NOTICE PERIOD (createDate -> forecast_date)")
    print("#" * 92)
    print(f"\nScope: {len(item_codes)} items, division={DIVISION}, revenue_type={REVENUE_TYPE}, status in {STATUSES}, "
          f"createDate >= {START_DATE}. {len(raw)} raw rows pulled.")
    n_null = all_with_null["forecast_date"].isna().sum()
    print(f"{n_null} of {len(raw)} rows ({100*n_null/len(raw):.2f}%) have no forecast_date and are excluded from this analysis.")
    print(f"{len(negative)} of {len(clean)} assessable rows ({100*len(negative)/len(clean):.2f}%) have a NEGATIVE notice "
          f"period (forecast_date before createDate) — treated as a data anomaly, excluded from the main distribution; "
          f"see leadtime_negative_notice_anomalies.csv.")
    print(f"\n{len(positive)} rows form the main notice-period distribution.")

    print("\n--- OVERALL DISTRIBUTION (days) ---")
    print(pd.Series(overall_stats).to_string())
    skew_note = "right-tailed - a minority of orders carry very long notice" if overall_stats["skewness"] > 0 else "left-tailed"
    print(f"\nShape: skewness={overall_stats['skewness']:.2f} ({skew_note}), excess kurtosis={overall_stats['kurtosis_excess']:.2f}.")

    print("\n--- CUMULATIVE NOTICE BUCKETS (share of orders with >= N months' notice) ---")
    print(overall_buckets.to_string(index=False))

    print("\n--- BY PRODUCT TYPE (median notice days, ascending) ---")
    print(by_type[["n", "median", "mean", "q1", "q3"]].to_string())

    print("\n--- BY TOP 15 CUSTOMERS (by order count) ---")
    print(by_customer[["n_orders_total_in_scope", "median", "mean", "q1", "q3"]].to_string())
    print("\nDispersion ACROSS all customers (median notice per customer):")
    print(pd.Series(cross_customer_dispersion).to_string())

    print("\n--- BY YEAR ---")
    print(by_year[["n", "median", "mean", "q1", "q3"]].to_string())
    if len(complete_years) == 2:
        y0, y1 = complete_years
        m0, m1 = by_year.loc[y0, "median"], by_year.loc[y1, "median"]
        print(f"\n2026 is partial (data through {raw['createDate'].max() if 'createDate' in raw else all_with_null['createDate'].max()}) "
              "— excluded from the year-over-year stability comparison below.")
        print(f"Median notice {y0}: {m0:.1f} days -> {y1}: {m1:.1f} days "
              f"({'stable' if abs(m1-m0) < 0.2*m0 else 'CHANGING'}, {100*(m1-m0)/m0:+.1f}%).")

    print("\n--- SPIKE MONTHS vs NORMAL MONTHS ---")
    print(f"Spike-month definition (reused from src/investigate_spikes.py, unchanged): a month qualifies as a spike "
          f"if qty > {SPIKE_MULTIPLIER}x the item's own median non-zero monthly qty. {len(spikes)} spike months found "
          f"across {spikes['itemcode'].nunique() if len(spikes) else 0} of the scope's items with sales history.")
    print(spike_vs_normal.to_string(index=False))
    if not np.isnan(p_value):
        print(f"\nMann-Whitney U test (spike-month vs normal-month order notice): U={u_stat:.1f}, p={p_value:.4f} — "
              f"{'a statistically significant difference in notice period' if p_value < 0.05 else 'NO statistically significant difference in notice period'} "
              f"between spike-month and normal-month orders.")
    print("\nValue (THB) by spike-month status and whether the order carried >=30 days' notice:")
    print(value_by_spike_and_bucket.to_string(index=False))

    print("\nCharts: output/charts/leadtime_notice_distribution.png, leadtime_notice_buckets.png, leadtime_spike_vs_normal.png")
    print("Full detail: output/summary/leadtime_*.csv")
