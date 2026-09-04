"""Task (2026-09-01), Part 3: historical on-time delivery baseline, from
Cube_CES, for the 128-item scope.

Compares ActualDelDate against PlanDelDate and ForecastDelDate. Business
framing (STATUS.md, Cube_CES deep-dive task): Status='Backlog' is Cube_CES's
own equivalent of cube_Sale_APD's MPS (not-yet-delivered, confirmed demand);
Status='Actual' rows are completed deliveries. Only completed (Actual) rows
with a non-null ActualDelDate can be assessed for on-time performance —
Backlog rows are, by definition, not yet delivered (they form the current
backlog reported in Part 3 below, not a "late" or "on time" delivery).

Scope decision (stated explicitly): ManuDivision='PEM101',
RevenueType='Omni Channel', Status IN ('Actual','Backlog'), CtrDate >=
2023-01-01 — the evidenced boundary from STATUS.md's Cube_CES row-level
verification task (dense, comparable data for these items begins January
2023; RevenueType is largely NULL, not a different value, before that).
Using the full available Cube_CES history back to 2023 (rather than matching
the 2024-01-01 floor used for demand forecasting) gives a longer, more
representative on-time-delivery baseline, since this question is about
historical delivery performance, not fitting a demand model.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("delivery_performance")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

MANU_DIVISION = "PEM101"
REVENUE_TYPE = "Omni Channel"
STATUSES = ["Actual", "Backlog"]
START_DATE = "2023-01-01"
SPIKE_MULTIPLIER = 3.0  # identical rule to src/investigate_spikes.py, applied here to Cube_CES's own quantity
TODAY = pd.Timestamp.now().normalize()


def get_scope() -> pd.DataFrame:
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))


def pull_raw(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(item_codes)
    status_list = "','".join(STATUSES)
    sql = f"""
        SELECT ContractID, ItemCode, CustomerID, CtrDate, PlanDelDate, ForecastDelDate, ActualDelDate,
               Status, PlanQty, ActualQty, BacklogQty
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
          AND ManuDivision = '{MANU_DIVISION}' AND RevenueType = '{REVENUE_TYPE}'
          AND Status IN ('{status_list}') AND CtrDate >= '{START_DATE}'
    """
    df = run_query(sql)
    logger.info("Pulled %d raw rows (%d items, ManuDivision=%s, RevenueType=%s, Status in %s, CtrDate >= %s)",
                len(df), len(item_codes), MANU_DIVISION, REVENUE_TYPE, STATUSES, START_DATE)
    return df


def classify_delay(days) -> str:
    if pd.isna(days):
        return "unknown"
    if days == 0:
        return "on_time"
    return "early" if days < 0 else "late"


def dist_stats(s: pd.Series) -> dict:
    s = s.dropna()
    if len(s) == 0:
        return {"n": 0}
    return {
        "n": len(s), "mean": float(s.mean()), "median": float(s.median()), "std": float(s.std()),
        "q1": float(s.quantile(0.25)), "q3": float(s.quantile(0.75)),
        "min": float(s.min()), "max": float(s.max()), "skewness": float(stats.skew(s)) if len(s) > 2 else None,
    }


if __name__ == "__main__":
    scope = get_scope()
    item_codes = sorted(scope["code"].unique())
    item_type_map = scope.set_index("code")[["category", "type"]]

    raw = pull_raw(item_codes)
    raw.to_csv(os.path.join(DATA_DIR, "raw_cube_ces_delivery_128items.csv"), index=False)

    df = raw.copy()
    for c in ["CtrDate", "PlanDelDate", "ForecastDelDate", "ActualDelDate"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = df.merge(item_type_map, left_on="ItemCode", right_index=True, how="left")
    df["year"] = df["CtrDate"].dt.year

    n_total = len(df)
    assessable = df[(df["Status"] == "Actual") & df["ActualDelDate"].notna()].copy()
    n_assessable = len(assessable)
    n_backlog = (df["Status"] == "Backlog").sum()
    n_actual_missing_actualdel = ((df["Status"] == "Actual") & df["ActualDelDate"].isna()).sum()

    assessable["delay_vs_plan"] = (assessable["ActualDelDate"] - assessable["PlanDelDate"]).dt.days
    assessable["delay_vs_forecast"] = (assessable["ActualDelDate"] - assessable["ForecastDelDate"]).dt.days
    assessable["status_vs_plan"] = assessable["delay_vs_plan"].apply(classify_delay)
    assessable["status_vs_forecast"] = assessable["delay_vs_forecast"].apply(classify_delay)
    assessable.to_csv(os.path.join(DATA_DIR, "processed_ces_delivery_assessable.csv"), index=False)

    # ================= OVERALL ON-TIME / EARLY / LATE =================
    overall_vs_plan = assessable["status_vs_plan"].value_counts(normalize=True).mul(100).round(2)
    overall_vs_forecast = assessable["status_vs_forecast"].value_counts(normalize=True).mul(100).round(2)
    overall_vs_plan.to_csv(os.path.join(SUMMARY_DIR, "delivery_overall_ontime_share_vs_plan.csv"))
    overall_vs_forecast.to_csv(os.path.join(SUMMARY_DIR, "delivery_overall_ontime_share_vs_forecast.csv"))

    delay_dist_plan = dist_stats(assessable["delay_vs_plan"])
    delay_dist_forecast = dist_stats(assessable["delay_vs_forecast"])
    late_only_plan = dist_stats(assessable.loc[assessable["delay_vs_plan"] > 0, "delay_vs_plan"])
    late_only_forecast = dist_stats(assessable.loc[assessable["delay_vs_forecast"] > 0, "delay_vs_forecast"])
    pd.DataFrame([
        {"metric": "delay_vs_plan_all", **delay_dist_plan},
        {"metric": "delay_vs_forecast_all", **delay_dist_forecast},
        {"metric": "delay_vs_plan_late_only", **late_only_plan},
        {"metric": "delay_vs_forecast_late_only", **late_only_forecast},
    ]).to_csv(os.path.join(SUMMARY_DIR, "delivery_lateness_distribution.csv"), index=False)

    # ================= BREAKDOWN: PRODUCT TYPE =================
    by_type = assessable.groupby("type").agg(
        n=("status_vs_plan", "size"),
        pct_on_time=("status_vs_plan", lambda s: 100 * (s == "on_time").mean()),
        pct_early=("status_vs_plan", lambda s: 100 * (s == "early").mean()),
        pct_late=("status_vs_plan", lambda s: 100 * (s == "late").mean()),
        median_delay=("delay_vs_plan", "median"), mean_delay=("delay_vs_plan", "mean"),
    ).sort_values("pct_late", ascending=False)
    by_type.to_csv(os.path.join(SUMMARY_DIR, "delivery_by_product_type.csv"))

    # ================= BREAKDOWN: CUSTOMER (top 15 by assessable order count) =================
    cust_counts = assessable["CustomerID"].value_counts()
    top_customers = cust_counts.head(15).index.tolist()
    by_customer = assessable[assessable["CustomerID"].isin(top_customers)].groupby("CustomerID").agg(
        n=("status_vs_plan", "size"),
        pct_on_time=("status_vs_plan", lambda s: 100 * (s == "on_time").mean()),
        pct_late=("status_vs_plan", lambda s: 100 * (s == "late").mean()),
        median_delay=("delay_vs_plan", "median"), mean_delay=("delay_vs_plan", "mean"),
    ).sort_values("n", ascending=False)
    by_customer.to_csv(os.path.join(SUMMARY_DIR, "delivery_by_top15_customers.csv"))

    # ================= BREAKDOWN: YEAR =================
    by_year = assessable.groupby("year").agg(
        n=("status_vs_plan", "size"),
        pct_on_time=("status_vs_plan", lambda s: 100 * (s == "on_time").mean()),
        pct_early=("status_vs_plan", lambda s: 100 * (s == "early").mean()),
        pct_late=("status_vs_plan", lambda s: 100 * (s == "late").mean()),
        median_delay=("delay_vs_plan", "median"), mean_delay=("delay_vs_plan", "mean"),
    )
    by_year.to_csv(os.path.join(SUMMARY_DIR, "delivery_by_year.csv"))

    # ================= BREAKDOWN: SPIKE MONTHS (recomputed on Cube_CES's own qty, same 3x-median rule) =================
    ces_qty = df.copy()
    ces_qty["qty"] = ces_qty["ActualQty"].fillna(0) + ces_qty["BacklogQty"].fillna(0)
    ces_qty["year_month"] = ces_qty["CtrDate"].dt.to_period("M").astype(str)
    monthly_item = ces_qty.groupby(["ItemCode", "year_month"], as_index=False)["qty"].sum()
    spike_keys = set()
    spike_rows_out = []
    for item, g in monthly_item.groupby("ItemCode"):
        nonzero = g.loc[g["qty"] > 0, "qty"]
        if len(nonzero) == 0:
            continue
        median_nz = nonzero.median()
        threshold = SPIKE_MULTIPLIER * median_nz
        flagged = g[g["qty"] > threshold]
        for _, r in flagged.iterrows():
            spike_keys.add((item, r["year_month"]))
            spike_rows_out.append({"itemcode": item, "year_month": r["year_month"], "qty": r["qty"],
                                    "item_median_nonzero_qty": median_nz, "threshold": threshold})
    ces_spikes_df = pd.DataFrame(spike_rows_out)
    ces_spikes_df.to_csv(os.path.join(SUMMARY_DIR, "delivery_ces_spike_months.csv"), index=False)
    logger.info("Cube_CES-based spike months (same 3x-median rule as src/investigate_spikes.py, applied to CES's "
                "own ActualQty+BacklogQty by CtrDate month — NOT the identical month set as Part 2's cube_Sale_APD-"
                "based spikes, since the source table, date field and time window differ): %d spike months across "
                "%d items", len(ces_spikes_df), ces_spikes_df["itemcode"].nunique() if len(ces_spikes_df) else 0)

    assessable["order_year_month"] = assessable["CtrDate"].dt.to_period("M").astype(str)
    assessable["is_spike_month"] = assessable.apply(lambda r: (r["ItemCode"], r["order_year_month"]) in spike_keys, axis=1)
    by_spike = assessable.groupby("is_spike_month").agg(
        n=("status_vs_plan", "size"),
        pct_on_time=("status_vs_plan", lambda s: 100 * (s == "on_time").mean()),
        pct_early=("status_vs_plan", lambda s: 100 * (s == "early").mean()),
        pct_late=("status_vs_plan", lambda s: 100 * (s == "late").mean()),
        median_delay=("delay_vs_plan", "median"), mean_delay=("delay_vs_plan", "mean"),
    )
    by_spike.to_csv(os.path.join(SUMMARY_DIR, "delivery_by_spike_month.csv"))

    ct = pd.crosstab(assessable["is_spike_month"], assessable["status_vs_plan"])
    chi2, chi_p, _, _ = stats.chi2_contingency(ct)

    # ================= CURRENT BACKLOG =================
    backlog = df[df["Status"] == "Backlog"].copy()
    backlog["age_days_vs_plan"] = (TODAY - backlog["PlanDelDate"]).dt.days
    backlog["age_days_vs_forecast"] = (TODAY - backlog["ForecastDelDate"]).dt.days
    backlog.to_csv(os.path.join(DATA_DIR, "processed_ces_backlog.csv"), index=False)

    backlog_by_item = backlog.groupby("ItemCode").agg(
        n_orders=("ContractID", "nunique"), total_backlog_qty=("BacklogQty", "sum"),
        median_age_days_vs_plan=("age_days_vs_plan", "median"), max_age_days_vs_plan=("age_days_vs_plan", "max"),
    ).sort_values("total_backlog_qty", ascending=False)
    backlog_by_item.to_csv(os.path.join(SUMMARY_DIR, "delivery_backlog_by_item.csv"))

    backlog_by_customer = backlog.groupby("CustomerID").agg(
        n_orders=("ContractID", "nunique"), total_backlog_qty=("BacklogQty", "sum"),
        median_age_days_vs_plan=("age_days_vs_plan", "median"),
    ).sort_values("total_backlog_qty", ascending=False)
    backlog_by_customer.to_csv(os.path.join(SUMMARY_DIR, "delivery_backlog_by_customer.csv"))

    backlog_age_stats = dist_stats(backlog["age_days_vs_plan"])
    backlog_summary = {
        "n_backlog_rows": len(backlog), "n_backlog_contracts": backlog["ContractID"].nunique(),
        "n_backlog_items": backlog["ItemCode"].nunique(), "n_backlog_customers": backlog["CustomerID"].nunique(),
        "total_backlog_qty": float(backlog["BacklogQty"].sum()),
        "pct_backlog_already_overdue_vs_plan": round(100 * (backlog["age_days_vs_plan"] > 0).mean(), 2),
        **{f"age_days_vs_plan_{k}": v for k, v in backlog_age_stats.items()},
    }
    pd.DataFrame([backlog_summary]).to_csv(os.path.join(SUMMARY_DIR, "delivery_backlog_summary.csv"), index=False)

    # ============================= CHARTS =============================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4.5))
    overall_vs_plan.reindex(["early", "on_time", "late"]).plot(kind="bar", ax=ax, color=["tab:green", "tab:blue", "tab:red"])
    ax.set_title("Delivery outcome vs Plan (128-item scope, assessable orders)")
    ax.set_ylabel("% of assessable deliveries")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "delivery_ontime_share.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    capped = assessable["delay_vs_plan"].clip(-60, 120)
    ax.hist(capped, bins=90, color="tab:purple", edgecolor="white")
    ax.axvline(0, color="black", linewidth=1)
    ax.set_title("Delivery delay vs Plan (days), negative = early, capped [-60, 120]")
    ax.set_xlabel("Days late (negative = early)")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "delivery_delay_distribution.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    by_year["pct_late"].plot(kind="bar", ax=ax, color="tab:red")
    ax.set_title("% of deliveries late (vs Plan) by year")
    ax.set_ylabel("% late")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "delivery_pct_late_by_year.png"))
    plt.close(fig)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 92)
    print("# PART 3: ON-TIME DELIVERY BASELINE (Cube_CES)")
    print("#" * 92)
    print(f"\nScope: {len(item_codes)} items, ManuDivision={MANU_DIVISION}, RevenueType={REVENUE_TYPE}, "
          f"Status in {STATUSES}, CtrDate >= {START_DATE}. {n_total} raw rows pulled.")
    print(f"\nASSESSABILITY: {n_assessable} of {n_total} rows ({100*n_assessable/n_total:.2f}%) can be assessed "
          f"(Status='Actual' with a non-null ActualDelDate).")
    print(f"  - {n_backlog} rows ({100*n_backlog/n_total:.2f}%) are Status='Backlog' — not yet delivered, no "
          f"ActualDelDate by definition; these form the current backlog reported below, not an on-time/late outcome.")
    print(f"  - {n_actual_missing_actualdel} rows ({100*n_actual_missing_actualdel/n_total:.2f}%) are Status='Actual' "
          f"but STILL lack an ActualDelDate — a small, unexplained data gap, excluded from the assessable set.")

    print("\n--- OVERALL: on-time / early / late vs PlanDelDate ---")
    print(overall_vs_plan.to_string())
    print("\n--- OVERALL: on-time / early / late vs ForecastDelDate ---")
    print(overall_vs_forecast.to_string())
    pct_agree = 100 * (assessable["PlanDelDate"] == assessable["ForecastDelDate"]).mean()
    print(f"\nPlanDelDate and ForecastDelDate are IDENTICAL on {pct_agree:.1f}% of assessable rows — the two "
          f"comparisons above are consistent with each other, not independent checks.")

    print("\n--- LATENESS DISTRIBUTION (days; vs Plan, all assessable rows including early/on-time) ---")
    print(pd.Series(delay_dist_plan).to_string())
    print("\n--- LATENESS DISTRIBUTION (days; vs Plan, LATE rows only) ---")
    print(pd.Series(late_only_plan).to_string())

    print("\n--- BY PRODUCT TYPE (sorted by %% late, descending) ---")
    print(by_type.round(2).to_string())

    print("\n--- BY TOP 15 CUSTOMERS (by assessable order count) ---")
    print(by_customer.round(2).to_string())

    print("\n--- BY YEAR ---")
    print(by_year.round(2).to_string())

    print("\n--- BY SPIKE MONTH vs NORMAL MONTH ---")
    print(f"(Spike-month rule recomputed directly on Cube_CES's own qty, same 3x-median methodology as Part 2 — "
          f"see module docstring for why this is not the identical month list as Part 2's cube_Sale_APD-based spikes.)")
    print(by_spike.round(2).to_string())
    print(f"\nChi-square test of independence (spike-month vs status_vs_plan): chi2={chi2:.2f}, p={chi_p:.4f} — "
          f"{'a statistically significant association' if chi_p < 0.05 else 'NO statistically significant association'} "
          f"between spike-month status and on-time/early/late outcome.")

    print("\n--- CURRENT BACKLOG ---")
    print(pd.Series(backlog_summary).to_string())
    print("\nTop 10 items by backlog quantity:")
    print(backlog_by_item.head(10).round(1).to_string())
    print("\nTop 10 customers by backlog quantity:")
    print(backlog_by_customer.head(10).round(1).to_string())

    print("\nCharts: output/charts/delivery_ontime_share.png, delivery_delay_distribution.png, delivery_pct_late_by_year.png")
    print("Full detail: output/summary/delivery_*.csv")
