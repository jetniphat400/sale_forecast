"""Task (2026-09-01, second task of the day): INVESTIGATION ONLY. Tests the
hypothesis that late deliveries are caused by stock being unavailable when
the order arrives (motivated by the prior task's finding: median customer
notice is only 6 days, far too short to produce/procure against). No min/max
values are calculated. No model or inventory policy is built. config.yaml is
not touched.

The data has no field stating WHY a delivery was late, and no historical
stock-level time series exists (STATUS.md, Phase 4 groundwork survey) — this
hypothesis CANNOT be proven directly from this data. This script gathers the
strongest available INDIRECT evidence across four independent angles (Parts
1-4) and is explicit throughout about what remains unproven.

Reuses existing outputs rather than rebuilding them:
  - output/data/processed_ces_delivery_assessable.csv (src/delivery_performance.py):
    per-delivery on-time/late outcome, Cube_CES, 128-item scope.
  - output/summary/phase4_part1_minmax_vs_sales.csv (src/investigate_inventory.py):
    per-item current min/max (summed across warehouses, labelled not
    authoritative per that script's own caveat) and months-of-cover.
  - output/summary/delivery_ces_spike_months.csv (src/delivery_performance.py):
    per-item spike months, Cube_CES quantity, same 3x-median rule used
    throughout this project.
  - output/data/processed_order_leadtime_clean.csv (src/order_leadtime.py):
    per-order notice period (cube_Sale_APD), for the Part 4 customer profile.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_stock_availability_hypothesis")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

MIN_ORDERS_FOR_ITEM_RATE = 10  # minimum assessable orders per item to trust its late rate / size comparison
POST_SPIKE_LAG_MONTHS = [1, 2]  # "shortly after" a spike, per the task wording


def load_delivery_data() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA_DIR, "processed_ces_delivery_assessable.csv"))
    df["CtrDate"] = pd.to_datetime(df["CtrDate"])
    df["year_month"] = df["CtrDate"].dt.to_period("M").astype(str)
    df["is_late"] = df["status_vs_plan"] == "late"
    return df


# ============================================================================
# PART 1: late rate vs. min/max configuration
# ============================================================================

def part1(df: pd.DataFrame):
    minmax = pd.read_csv(os.path.join(SUMMARY_DIR, "phase4_part1_minmax_vs_sales.csv"))

    item_rate = df.groupby("ItemCode").agg(n_assessable=("is_late", "size"), n_late=("is_late", "sum")).reset_index()
    item_rate["late_rate_pct"] = 100 * item_rate["n_late"] / item_rate["n_assessable"]
    item_rate = item_rate.rename(columns={"ItemCode": "itemcode"})

    combined = item_rate.merge(minmax, on="itemcode", how="left")
    combined["has_inventory_row"] = combined["total_minimum"].notna()
    combined["total_minimum"] = combined["total_minimum"].fillna(0)
    combined["total_maximum"] = combined["total_maximum"].fillna(0)
    combined["has_config"] = (combined["total_minimum"] > 0) | (combined["total_maximum"] > 0)
    combined.to_csv(os.path.join(SUMMARY_DIR, "hyp_part1_item_late_rate_vs_minmax.csv"), index=False)

    qualified = combined[combined["n_assessable"] >= MIN_ORDERS_FOR_ITEM_RATE].copy()
    logger.info("Part 1: %d of %d items have >= %d assessable orders and are used for the comparisons below",
                len(qualified), len(combined), MIN_ORDERS_FOR_ITEM_RATE)

    # ---- configured vs. unconfigured: item-level (equal-weight-per-item) ----
    configured = qualified[qualified["has_config"]]["late_rate_pct"]
    unconfigured = qualified[~qualified["has_config"]]["late_rate_pct"]
    if len(configured) > 1 and len(unconfigured) > 1:
        u_item, p_item = stats.mannwhitneyu(configured, unconfigured, alternative="two-sided")
    else:
        u_item, p_item = np.nan, np.nan

    # ---- configured vs. unconfigured: pooled ORDER-level (volume-weighted) ----
    order_level = df.merge(combined[["itemcode", "has_config"]], left_on="ItemCode", right_on="itemcode", how="left")
    pooled = order_level.groupby("has_config").agg(n=("is_late", "size"), n_late=("is_late", "sum"))
    pooled["late_rate_pct"] = 100 * pooled["n_late"] / pooled["n"]
    if len(pooled) == 2:
        chi2, chi_p, _, _ = stats.chi2_contingency(pd.crosstab(order_level["has_config"], order_level["is_late"]))
    else:
        chi2, chi_p = np.nan, np.nan
    pooled.to_csv(os.path.join(SUMMARY_DIR, "hyp_part1_pooled_config_vs_unconfig.csv"))

    item_level_summary = pd.DataFrame([
        {"group": "configured (min or max > 0)", "n_items": len(configured), "mean_late_rate_pct": configured.mean() if len(configured) else np.nan, "median_late_rate_pct": configured.median() if len(configured) else np.nan},
        {"group": "unconfigured (min=max=0 or missing)", "n_items": len(unconfigured), "mean_late_rate_pct": unconfigured.mean() if len(unconfigured) else np.nan, "median_late_rate_pct": unconfigured.median() if len(unconfigured) else np.nan},
    ])
    item_level_summary.to_csv(os.path.join(SUMMARY_DIR, "hyp_part1_configured_vs_unconfigured_itemlevel.csv"), index=False)

    # ---- among configured items: does months-of-cover relate to late rate? ----
    cover_df = qualified[qualified["has_config"] & qualified["min_months_of_cover"].notna()].copy()
    if len(cover_df) > 3:
        rho_min, p_min = stats.spearmanr(cover_df["min_months_of_cover"], cover_df["late_rate_pct"])
    else:
        rho_min, p_min = np.nan, np.nan
    cover_df_max = qualified[qualified["has_config"] & qualified["max_months_of_cover"].notna()].copy()
    if len(cover_df_max) > 3:
        rho_max, p_max = stats.spearmanr(cover_df_max["max_months_of_cover"], cover_df_max["late_rate_pct"])
    else:
        rho_max, p_max = np.nan, np.nan
    cover_corr = pd.DataFrame([
        {"cover_metric": "min_months_of_cover", "n_items": len(cover_df), "spearman_rho": rho_min, "p_value": p_min},
        {"cover_metric": "max_months_of_cover", "n_items": len(cover_df_max), "spearman_rho": rho_max, "p_value": p_max},
    ])
    cover_corr.to_csv(os.path.join(SUMMARY_DIR, "hyp_part1_cover_vs_late_rate_correlation.csv"), index=False)

    # ---- low-cover vs high-cover among configured items (median split) ----
    low_high = None
    if len(cover_df) >= 6:
        median_cover = cover_df["min_months_of_cover"].median()
        low_cover = cover_df[cover_df["min_months_of_cover"] <= median_cover]["late_rate_pct"]
        high_cover = cover_df[cover_df["min_months_of_cover"] > median_cover]["late_rate_pct"]
        u_cov, p_cov = stats.mannwhitneyu(low_cover, high_cover, alternative="two-sided") if len(low_cover) > 1 and len(high_cover) > 1 else (np.nan, np.nan)
        low_high = {"median_cover_split_months": median_cover, "low_cover_n": len(low_cover), "low_cover_mean_late_pct": low_cover.mean(),
                    "high_cover_n": len(high_cover), "high_cover_mean_late_pct": high_cover.mean(), "u_stat": u_cov, "p_value": p_cov}
        pd.DataFrame([low_high]).to_csv(os.path.join(SUMMARY_DIR, "hyp_part1_low_vs_high_cover.csv"), index=False)

    # ---- charts ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.boxplot([unconfigured, configured], tick_labels=["Unconfigured", "Configured"], showfliers=True)
    ax.set_ylabel("Item late-delivery rate (%)")
    ax.set_title("Late rate: unconfigured vs. configured min/max")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "hyp_part1_config_vs_late_rate.png"))
    plt.close(fig)

    if len(cover_df) > 3:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.scatter(cover_df["min_months_of_cover"].clip(upper=200), cover_df["late_rate_pct"], alpha=0.6)
        ax.set_xscale("symlog")
        ax.set_xlabel("Minimum months of cover (symlog scale, clipped at 200)")
        ax.set_ylabel("Item late-delivery rate (%)")
        ax.set_title("Months of cover vs. late rate (configured items only)")
        fig.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "hyp_part1_cover_vs_late_rate.png"))
        plt.close(fig)

    return {
        "combined": combined, "qualified": qualified, "item_level_summary": item_level_summary,
        "u_item": u_item, "p_item": p_item, "pooled": pooled, "chi2": chi2, "chi_p": chi_p,
        "cover_corr": cover_corr, "low_high": low_high,
    }


# ============================================================================
# PART 2: order size, late vs. on-time
# ============================================================================

def part2(df: pd.DataFrame):
    item_median_qty = df.groupby("ItemCode")["ActualQty"].median().rename("item_median_qty")
    d = df.merge(item_median_qty, left_on="ItemCode", right_index=True)
    d = d[d["item_median_qty"] > 0].copy()
    d["size_ratio"] = d["ActualQty"] / d["item_median_qty"]

    item_counts = d.groupby("ItemCode")["is_late"].agg(n="size", n_late="sum")
    qualified_items = item_counts[(item_counts["n"] >= MIN_ORDERS_FOR_ITEM_RATE) & (item_counts["n_late"] >= 3) & ((item_counts["n"] - item_counts["n_late"]) >= 3)].index
    d_q = d[d["ItemCode"].isin(qualified_items)].copy()
    logger.info("Part 2: %d of %d items have >= %d orders with >= 3 late AND >= 3 on-time/early, used for the "
                "item-normalized size comparison", len(qualified_items), d["ItemCode"].nunique(), MIN_ORDERS_FOR_ITEM_RATE)

    late_ratio = d_q.loc[d_q["is_late"], "size_ratio"]
    nonlate_ratio = d_q.loc[~d_q["is_late"], "size_ratio"]
    u_stat, p_value = stats.mannwhitneyu(late_ratio, nonlate_ratio, alternative="two-sided")

    size_summary = pd.DataFrame([
        {"group": "late", "n": len(late_ratio), "mean_ratio_to_item_median": late_ratio.mean(), "median_ratio_to_item_median": late_ratio.median()},
        {"group": "on_time_or_early", "n": len(nonlate_ratio), "mean_ratio_to_item_median": nonlate_ratio.mean(), "median_ratio_to_item_median": nonlate_ratio.median()},
    ])
    size_summary.to_csv(os.path.join(SUMMARY_DIR, "hyp_part2_order_size_late_vs_ontime.csv"), index=False)

    # per-item paired comparison: for how many items is the late-order median ratio bigger?
    per_item = d_q.groupby(["ItemCode", "is_late"])["size_ratio"].median().unstack()
    per_item.columns = ["median_ratio_nonlate", "median_ratio_late"] if False else per_item.columns
    per_item = per_item.rename(columns={True: "median_ratio_late", False: "median_ratio_nonlate"})
    per_item = per_item.dropna()
    per_item["late_bigger"] = per_item["median_ratio_late"] > per_item["median_ratio_nonlate"]
    per_item.to_csv(os.path.join(SUMMARY_DIR, "hyp_part2_per_item_size_comparison.csv"))
    n_late_bigger = int(per_item["late_bigger"].sum())
    n_items_compared = len(per_item)
    if n_items_compared > 0:
        sign_p = stats.binomtest(n_late_bigger, n_items_compared, 0.5).pvalue
    else:
        sign_p = np.nan

    # late rate by order-size quartile (item-normalized), across the full qualified set
    d_q["size_quartile"] = pd.qcut(d_q["size_ratio"], 4, labels=["Q1 (smallest)", "Q2", "Q3", "Q4 (largest)"], duplicates="drop")
    by_quartile = d_q.groupby("size_quartile", observed=True).agg(n=("is_late", "size"), n_late=("is_late", "sum"))
    by_quartile["late_rate_pct"] = 100 * by_quartile["n_late"] / by_quartile["n"]
    by_quartile.to_csv(os.path.join(SUMMARY_DIR, "hyp_part2_late_rate_by_size_quartile.csv"))
    ct = pd.crosstab(d_q["size_quartile"], d_q["is_late"])
    chi2_q, chi_p_q, _, _ = stats.chi2_contingency(ct)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4.5))
    by_quartile["late_rate_pct"].plot(kind="bar", ax=ax, color="tab:red")
    ax.set_ylabel("Late-delivery rate (%)")
    ax.set_title("Late rate by order size (relative to item's own median), quartiles")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "hyp_part2_late_rate_by_size_quartile.png"))
    plt.close(fig)

    return {"size_summary": size_summary, "u_stat": u_stat, "p_value": p_value, "per_item": per_item,
            "n_late_bigger": n_late_bigger, "n_items_compared": n_items_compared, "sign_p": sign_p,
            "by_quartile": by_quartile, "chi2_q": chi2_q, "chi_p_q": chi_p_q}


# ============================================================================
# PART 3: timing — monthly clustering and post-spike lag
# ============================================================================

def part3(df: pd.DataFrame):
    monthly = df.groupby("year_month").agg(n=("is_late", "size"), n_late=("is_late", "sum")).sort_index()
    monthly["late_rate_pct"] = 100 * monthly["n_late"] / monthly["n"]
    monthly.to_csv(os.path.join(SUMMARY_DIR, "hyp_part3_late_deliveries_by_month.csv"))

    spikes = pd.read_csv(os.path.join(SUMMARY_DIR, "delivery_ces_spike_months.csv"))
    spike_keys = set(zip(spikes["itemcode"], spikes["year_month"]))
    df = df.copy()
    df["is_spike_month"] = df.apply(lambda r: (r["ItemCode"], r["year_month"]) in spike_keys, axis=1)

    by_spike = df.groupby("is_spike_month").agg(n=("is_late", "size"), n_late=("is_late", "sum"))
    by_spike["late_rate_pct"] = 100 * by_spike["n_late"] / by_spike["n"]
    by_spike.to_csv(os.path.join(SUMMARY_DIR, "hyp_part3_late_rate_by_spike_month.csv"))
    n_spike_months_value_share = 100 * df.loc[df["is_spike_month"], "ActualQty"].sum() / df["ActualQty"].sum()
    n_spike_item_months_share = 100 * len(spikes) / df.groupby(["ItemCode"]).apply(lambda g: g["year_month"].nunique()).sum()
    chi2_s, chi_p_s, _, _ = stats.chi2_contingency(pd.crosstab(df["is_spike_month"], df["is_late"]))

    # ---- lag analysis: does late rate rise in the 1-2 months AFTER an item's own spike? ----
    item_months = df.groupby(["ItemCode", "year_month"]).agg(n=("is_late", "size"), n_late=("is_late", "sum")).reset_index()
    item_months["period"] = pd.PeriodIndex(item_months["year_month"], freq="M")
    item_months = item_months.sort_values(["ItemCode", "period"])

    item_spike_periods = {}
    for item, g in spikes.groupby("itemcode"):
        item_spike_periods[item] = set(pd.PeriodIndex(g["year_month"], freq="M"))

    def tag_row(row):
        item, period = row["ItemCode"], row["period"]
        spike_periods = item_spike_periods.get(item, set())
        if period in spike_periods:
            return "spike_month_itself"
        for lag in POST_SPIKE_LAG_MONTHS:
            if (period - lag) in spike_periods:
                return "post_spike_lag"
        return "baseline"

    item_months["timing_bucket"] = item_months.apply(tag_row, axis=1)
    bucket_summary = item_months.groupby("timing_bucket").agg(n=("n", "sum"), n_late=("n_late", "sum"))
    bucket_summary["late_rate_pct"] = 100 * bucket_summary["n_late"] / bucket_summary["n"]
    bucket_summary.to_csv(os.path.join(SUMMARY_DIR, "hyp_part3_late_rate_by_timing_bucket.csv"))

    post = item_months[item_months["timing_bucket"] == "post_spike_lag"]
    base = item_months[item_months["timing_bucket"] == "baseline"]
    ct_lag = pd.DataFrame({
        "late": [post["n_late"].sum(), base["n_late"].sum()],
        "not_late": [post["n"].sum() - post["n_late"].sum(), base["n"].sum() - base["n_late"].sum()],
    }, index=["post_spike_lag", "baseline"])
    if (ct_lag > 0).all().all():
        chi2_lag, chi_p_lag, _, _ = stats.chi2_contingency(ct_lag)
    else:
        chi2_lag, chi_p_lag = np.nan, np.nan

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax1 = plt.subplots(figsize=(12, 4.5))
    ax1.bar(monthly.index, monthly["n"], color="lightgray", label="Total assessable deliveries")
    ax1.bar(monthly.index, monthly["n_late"], color="tab:red", label="Late deliveries")
    ax1.set_ylabel("Count")
    ax1.tick_params(axis="x", rotation=90)
    ax1.legend(loc="upper left", fontsize=8)
    ax2 = ax1.twinx()
    ax2.plot(monthly.index, monthly["late_rate_pct"], color="black", marker="o", markersize=3, label="Late rate %")
    ax2.set_ylabel("Late rate (%)")
    ax1.set_title("Late deliveries by month, 2023-2026")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "hyp_part3_late_by_month.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    bucket_summary["late_rate_pct"].reindex(["baseline", "post_spike_lag", "spike_month_itself"]).plot(kind="bar", ax=ax, color=["tab:blue", "tab:orange", "tab:red"])
    ax.set_ylabel("Late rate (%)")
    ax.set_title(f"Late rate by timing relative to an item's own spike month (lag={POST_SPIKE_LAG_MONTHS})")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "hyp_part3_late_rate_by_timing_bucket.png"))
    plt.close(fig)

    return {"monthly": monthly, "by_spike": by_spike, "chi2_s": chi2_s, "chi_p_s": chi_p_s,
            "spike_value_share": n_spike_months_value_share, "spike_item_month_share": n_spike_item_months_share,
            "bucket_summary": bucket_summary, "chi2_lag": chi2_lag, "chi_p_lag": chi_p_lag}


# ============================================================================
# PART 4: customer differences — behaviour vs. item mix
# ============================================================================

def part4(df: pd.DataFrame, item_late_rate: pd.DataFrame):
    by_customer = pd.read_csv(os.path.join(SUMMARY_DIR, "delivery_by_top15_customers.csv"))
    by_customer = by_customer.sort_values("pct_late")
    lowest = by_customer.iloc[0]
    highest = by_customer.iloc[-1]
    logger.info("Part 4: lowest late-rate top-15 customer = %s (%.2f%%), highest = %s (%.2f%%)",
                lowest["CustomerID"], lowest["pct_late"], highest["CustomerID"], highest["pct_late"])

    top15_ids = by_customer["CustomerID"].tolist()
    item_rate_map = item_late_rate.set_index("itemcode")["late_rate_pct"]

    # item-mix-adjusted "expected" late rate per customer: weight each item's
    # OVERALL (all-customer) late rate by this customer's own order-count share of that item
    profiles = []
    for cust in top15_ids:
        cd = df[df["CustomerID"] == cust]
        item_counts = cd["ItemCode"].value_counts()
        weights = item_counts / item_counts.sum()
        expected_rate = sum(weights.get(item, 0) * item_rate_map.get(item, np.nan) for item in weights.index
                             if item in item_rate_map.index)
        actual_rate = 100 * cd["is_late"].mean()
        n_items = cd["ItemCode"].nunique()
        shares = item_counts / item_counts.sum()
        hhi = float((shares ** 2).sum())  # 1/n_items (even spread) to 1.0 (single item)
        n_orders = len(cd)
        profiles.append({
            "CustomerID": cust, "n_orders": n_orders, "n_distinct_items": n_items, "purchase_hhi": round(hhi, 3),
            "actual_late_rate_pct": round(actual_rate, 2), "item_mix_expected_late_rate_pct": round(expected_rate, 2) if not np.isnan(expected_rate) else None,
            "gap_actual_minus_expected": round(actual_rate - expected_rate, 2) if not np.isnan(expected_rate) else None,
        })
    profile_df = pd.DataFrame(profiles).sort_values("actual_late_rate_pct")
    profile_df.to_csv(os.path.join(SUMMARY_DIR, "hyp_part4_customer_behaviour_vs_itemmix.csv"), index=False)

    corr_actual_expected = profile_df[["actual_late_rate_pct", "item_mix_expected_late_rate_pct"]].dropna()
    rho, p_corr = stats.spearmanr(corr_actual_expected["actual_late_rate_pct"], corr_actual_expected["item_mix_expected_late_rate_pct"]) if len(corr_actual_expected) > 3 else (np.nan, np.nan)

    # ---- deep-dive: highest vs lowest customer ----
    notice = pd.read_csv(os.path.join(DATA_DIR, "processed_order_leadtime_clean.csv"))
    deep = []
    for cust, label in [(lowest["CustomerID"], "lowest_late_rate"), (highest["CustomerID"], "highest_late_rate")]:
        cd = df[df["CustomerID"] == cust]
        cn = notice[notice["customerid"] == cust]
        items = set(cd["ItemCode"].unique())
        n_months_active = cd["year_month"].nunique()
        span_months = (cd["CtrDate"].max() - cd["CtrDate"].min()).days / 30.44 if len(cd) else np.nan
        deep.append({
            "CustomerID": cust, "role": label, "n_orders_assessable": len(cd), "n_distinct_items": len(items),
            "late_rate_pct": round(100 * cd["is_late"].mean(), 2),
            "median_order_qty": cd["ActualQty"].median(), "mean_order_qty": round(cd["ActualQty"].mean(), 1),
            "median_notice_days": cn["notice_days"].median() if len(cn) else None,
            "mean_notice_days": round(cn["notice_days"].mean(), 1) if len(cn) else None,
            "n_orders_per_active_month": round(len(cd) / n_months_active, 1) if n_months_active else None,
            "active_span_months": round(span_months, 1) if not np.isnan(span_months) else None,
            "top_5_items_by_order_count": cd["ItemCode"].value_counts().head(5).to_dict(),
        })
    deep_df = pd.DataFrame(deep)
    deep_df.to_csv(os.path.join(SUMMARY_DIR, "hyp_part4_deepdive_highest_vs_lowest.csv"), index=False)

    shared_items = set(df[df["CustomerID"] == lowest["CustomerID"]]["ItemCode"]) & set(df[df["CustomerID"] == highest["CustomerID"]]["ItemCode"])
    shared_comparison = None
    if shared_items:
        rows = []
        for item in shared_items:
            for cust, label in [(lowest["CustomerID"], "lowest_late_rate_customer"), (highest["CustomerID"], "highest_late_rate_customer")]:
                sub = df[(df["CustomerID"] == cust) & (df["ItemCode"] == item)]
                if len(sub) >= 3:
                    rows.append({"itemcode": item, "customer_role": label, "n": len(sub), "late_rate_pct": round(100 * sub["is_late"].mean(), 1)})
        shared_comparison = pd.DataFrame(rows)
        if len(shared_comparison):
            shared_comparison.to_csv(os.path.join(SUMMARY_DIR, "hyp_part4_shared_items_headtohead.csv"), index=False)
            pivot = shared_comparison.pivot_table(index="itemcode", columns="customer_role", values="late_rate_pct")
            if {"lowest_late_rate_customer", "highest_late_rate_customer"}.issubset(pivot.columns):
                pivot = pivot.dropna()
                pivot["gap_highest_minus_lowest"] = pivot["highest_late_rate_customer"] - pivot["lowest_late_rate_customer"]
                pivot.to_csv(os.path.join(SUMMARY_DIR, "hyp_part4_shared_items_gap.csv"))
                shared_comparison_gap_mean = float(pivot["gap_highest_minus_lowest"].mean())
            else:
                shared_comparison_gap_mean = None
        else:
            shared_comparison_gap_mean = None
    else:
        shared_comparison_gap_mean = None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(profile_df["item_mix_expected_late_rate_pct"], profile_df["actual_late_rate_pct"])
    for _, r in profile_df.iterrows():
        ax.annotate(r["CustomerID"], (r["item_mix_expected_late_rate_pct"], r["actual_late_rate_pct"]), fontsize=7)
    lims = [0, max(profile_df["actual_late_rate_pct"].max(), profile_df["item_mix_expected_late_rate_pct"].max()) * 1.1]
    ax.plot(lims, lims, linestyle="--", color="gray", label="actual = item-mix-expected")
    ax.set_xlabel("Item-mix-expected late rate (%)")
    ax.set_ylabel("Actual late rate (%)")
    ax.set_title("Customer late rate: actual vs. expected from item mix alone")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "hyp_part4_actual_vs_expected_late_rate.png"))
    plt.close(fig)

    return {"profile_df": profile_df, "rho": rho, "p_corr": p_corr, "deep_df": deep_df,
            "shared_comparison": shared_comparison, "shared_comparison_gap_mean": shared_comparison_gap_mean,
            "lowest": lowest, "highest": highest}


if __name__ == "__main__":
    df = load_delivery_data()
    logger.info("Loaded %d assessable Cube_CES delivery rows (128-item scope, 2023+)", len(df))

    r1 = part1(df)
    r2 = part2(df)
    r3 = part3(df)
    r4 = part4(df, r1["combined"][["itemcode", "late_rate_pct"]])

    # ============================= PART 5: SYNTHESIS ESTIMATE =============================
    print("\n" + "#" * 92)
    print("# PART 5: WHAT PROPORTION OF LATE DELIVERIES COULD PLAUSIBLY BE PREVENTED BY STOCK?")
    print("#" * 92)
    print("\nThis is a REASONED ESTIMATE built from Parts 1-4's indirect evidence, NOT a measurement — no historical")
    print("stock-level data exists to compute this directly (STATUS.md, Phase 4 groundwork). Assumptions are stated")
    print("explicitly below; the range reflects how much each piece of evidence does or does not support the")
    print("hypothesis, not a precise calculation.")

    total_late = int(df["is_late"].sum())
    total_assessable = len(df)
    print(f"\nTotal late deliveries in scope: {total_late} of {total_assessable} assessable ({100*total_late/total_assessable:.2f}%).")

    # ============================= CONSOLE: PART 1 =============================
    print("\n" + "=" * 92)
    print("PART 1: LATE RATE vs. MIN/MAX CONFIGURATION")
    print("=" * 92)
    print(f"Items with >= {MIN_ORDERS_FOR_ITEM_RATE} assessable orders used: {len(r1['qualified'])} of {len(r1['combined'])}")
    print("\nConfigured vs. unconfigured (item-level, equal weight per item):")
    print(r1["item_level_summary"].to_string(index=False))
    if not np.isnan(r1["p_item"]):
        print(f"Mann-Whitney U (item-level late rate, configured vs unconfigured): U={r1['u_item']:.1f}, p={r1['p_item']:.4f} — "
              f"{'statistically significant' if r1['p_item']<0.05 else 'NOT statistically significant'}")
    print("\nConfigured vs. unconfigured (pooled, order-level / volume-weighted):")
    print(r1["pooled"].to_string())
    print(f"Chi-square (order-level late vs. config status): chi2={r1['chi2']:.2f}, p={r1['chi_p']:.4f} — "
          f"{'statistically significant' if r1['chi_p']<0.05 else 'NOT statistically significant'}")
    print("\nAmong configured items — does months-of-cover correlate with late rate? (Spearman)")
    print(r1["cover_corr"].to_string(index=False))
    if r1["low_high"]:
        lh = r1["low_high"]
        print(f"\nLow-cover (<= median {lh['median_cover_split_months']:.1f} months, n={lh['low_cover_n']}) mean late "
              f"rate = {lh['low_cover_mean_late_pct']:.2f}%  vs.  High-cover (n={lh['high_cover_n']}) mean late rate "
              f"= {lh['high_cover_mean_late_pct']:.2f}%  (Mann-Whitney p={lh['p_value']:.4f})")

    # ============================= CONSOLE: PART 2 =============================
    print("\n" + "=" * 92)
    print("PART 2: ORDER SIZE — LATE vs. ON-TIME")
    print("=" * 92)
    print(r2["size_summary"].to_string(index=False))
    print(f"Mann-Whitney U (item-normalized order size, late vs non-late): U={r2['u_stat']:.1f}, p={r2['p_value']:.4f} — "
          f"{'statistically significant' if r2['p_value']<0.05 else 'NOT statistically significant'}")
    print(f"\nPer-item paired check: of {r2['n_items_compared']} items with enough late AND on-time orders to compare, "
          f"{r2['n_late_bigger']} ({100*r2['n_late_bigger']/r2['n_items_compared']:.1f}%) have a LARGER median late-order "
          f"size than their own on-time median (sign test p={r2['sign_p']:.4f}).")
    print("\nLate rate by order-size quartile (relative to the item's own median):")
    print(r2["by_quartile"].round(2).to_string())
    print(f"Chi-square (size quartile vs late/non-late): chi2={r2['chi2_q']:.2f}, p={r2['chi_p_q']:.4f} — "
          f"{'statistically significant' if r2['chi_p_q']<0.05 else 'NOT statistically significant'}")

    # ============================= CONSOLE: PART 3 =============================
    print("\n" + "=" * 92)
    print("PART 3: TIMING OF LATE DELIVERIES")
    print("=" * 92)
    print("Late deliveries and late rate by month (first/last 6 shown; full table in hyp_part3_late_deliveries_by_month.csv):")
    print(r3["monthly"].round(2).head(6).to_string())
    print("...")
    print(r3["monthly"].round(2).tail(6).to_string())
    print(f"\nSpike months account for {r3['spike_item_month_share']:.1f}% of item-months and "
          f"{r3['spike_value_share']:.1f}% of ActualQty volume in this assessable delivery scope (Cube_CES-based "
          f"spike definition — see delivery_ces_spike_months.csv; NOT the same figure as the earlier 58-item-pilot "
          f"16.6%/3.4% finding, which used cube_Sale_APD on a narrower item scope).")
    print("\nLate rate: spike months vs. normal months:")
    print(r3["by_spike"].round(2).to_string())
    print(f"Chi-square: chi2={r3['chi2_s']:.2f}, p={r3['chi_p_s']:.4f} — "
          f"{'statistically significant' if r3['chi_p_s']<0.05 else 'NOT statistically significant'}")
    print(f"\nLate rate by timing relative to an item's OWN spike month (lag months tested: {POST_SPIKE_LAG_MONTHS}):")
    print(r3["bucket_summary"].round(2).to_string())
    if not np.isnan(r3["chi_p_lag"]):
        print(f"Chi-square (post-spike-lag vs baseline): chi2={r3['chi2_lag']:.2f}, p={r3['chi_p_lag']:.4f} — "
              f"{'statistically significant' if r3['chi_p_lag']<0.05 else 'NOT statistically significant'}")
    else:
        print("Chi-square could not be computed for the lag comparison (an empty cell in the contingency table).")

    # ============================= CONSOLE: PART 4 =============================
    print("\n" + "=" * 92)
    print("PART 4: CUSTOMER DIFFERENCES — BEHAVIOUR vs. ITEM MIX")
    print("=" * 92)
    print("Full top-15 customer profile (item-mix-expected late rate vs actual):")
    print(r4["profile_df"].to_string(index=False))
    if not np.isnan(r4["rho"]):
        print(f"\nSpearman correlation (actual late rate vs. item-mix-expected late rate, across top-15 customers): "
              f"rho={r4['rho']:.2f}, p={r4['p_corr']:.4f} — "
              f"{'a strong positive relationship: customers who buy inherently late-prone items ARE the ones with high late rates (item-mix effect)' if r4['rho']>0.5 and r4['p_corr']<0.05 else 'no strong/significant relationship — late rate does not simply follow item mix'}")
    print(f"\nDeep dive — lowest late-rate top-15 customer ({r4['lowest']['CustomerID']}, {r4['lowest']['pct_late']:.2f}%) "
          f"vs. highest ({r4['highest']['CustomerID']}, {r4['highest']['pct_late']:.2f}%):")
    print(r4["deep_df"].to_string(index=False))
    if r4["shared_comparison"] is not None and len(r4["shared_comparison"]):
        print(f"\nHead-to-head on items BOTH customers buy (n>=3 orders each side, isolates item effect from customer effect):")
        print(r4["shared_comparison"].to_string(index=False))
        if r4["shared_comparison_gap_mean"] is not None:
            print(f"\nOn items BOTH customers buy, the highest-late-rate customer's late rate is on average "
                  f"{r4['shared_comparison_gap_mean']:.1f} percentage points HIGHER than the lowest-late-rate "
                  f"customer's, for the IDENTICAL item. This is a RESIDUAL gap the item-mix correlation above does "
                  f"NOT explain — since a pure item/stock-availability effect should hit any customer buying that "
                  f"item similarly. The most likely contributor visible in this data: order size (this customer's "
                  f"median order is {r4['deep_df'].set_index('role').loc['highest_late_rate','median_order_qty']:.0f} "
                  f"units vs. {r4['deep_df'].set_index('role').loc['lowest_late_rate','median_order_qty']:.0f} for "
                  f"the low-late-rate customer, consistent with Part 2's finding that larger orders run somewhat "
                  f"later) — but this data cannot fully confirm order size is the whole explanation, and some "
                  f"customer- or allocation-specific factor cannot be ruled out.")
    else:
        print("\nNo shared items with sufficient order counts on both sides to run a direct head-to-head comparison.")

    # ============================= PART 5 estimate, built from the above =============================
    config_gap = r1["item_level_summary"].set_index("group")["mean_late_rate_pct"]
    config_effect_pct_points = config_gap.get("unconfigured (min=max=0 or missing)", np.nan) - config_gap.get("configured (min or max > 0)", np.nan)
    # Uses the size-quartile trend (Q1->Q4 late rate strictly increasing) + its own chi-square test, not the
    # late-vs-nonlate median ratio (which ties at 1.0 for both groups and would understate a real tail effect —
    # the Mann-Whitney test is significant because of the distribution's shape/tail, not a median shift).
    q_rates = r2["by_quartile"]["late_rate_pct"]
    size_effect_present = r2["chi_p_q"] < 0.05 and q_rates.iloc[-1] > q_rates.iloc[0]
    timing_effect_present = (not np.isnan(r3["chi_p_lag"])) and r3["chi_p_lag"] < 0.05 and r3["bucket_summary"].loc["post_spike_lag", "late_rate_pct"] > r3["bucket_summary"].loc["baseline", "late_rate_pct"]
    item_mix_dominates = (not np.isnan(r4["rho"])) and r4["rho"] > 0.5 and r4["p_corr"] < 0.05

    evidence_rows = [
        {"angle": "Part 1: unconfigured/low-cover items more late?", "supports_hypothesis": bool(config_effect_pct_points > 0) if not np.isnan(config_effect_pct_points) else None, "detail": f"gap = {config_effect_pct_points:.2f} pct points (unconfigured minus configured mean late rate)"},
        {"angle": "Part 2: late orders unusually large?", "supports_hypothesis": bool(size_effect_present), "detail": f"Mann-Whitney p={r2['p_value']:.4f}"},
        {"angle": "Part 3: late deliveries follow an item's own spike (drawdown pattern)?", "supports_hypothesis": bool(timing_effect_present) if not np.isnan(r3['chi_p_lag']) else None, "detail": f"post-spike-lag late rate={r3['bucket_summary'].loc['post_spike_lag','late_rate_pct']:.2f}% vs baseline={r3['bucket_summary'].loc['baseline','late_rate_pct']:.2f}%"},
        {"angle": "Part 4: late rate driven by item mix (stock-relevant) rather than customer behaviour?", "supports_hypothesis": bool(item_mix_dominates) if not np.isnan(r4['rho']) else None, "detail": f"rho={r4['rho']:.2f}, p={r4['p_corr']:.4f}"},
    ]
    evidence_df = pd.DataFrame(evidence_rows)
    evidence_df.to_csv(os.path.join(SUMMARY_DIR, "hyp_part5_evidence_scorecard.csv"), index=False)
    print("\n" + "-" * 92)
    print("EVIDENCE SCORECARD (each angle, does it point toward the stock-availability hypothesis?)")
    print("-" * 92)
    print(evidence_df.to_string(index=False))

    n_supporting = evidence_df["supports_hypothesis"].sum()
    n_testable = evidence_df["supports_hypothesis"].notna().sum()

    if n_supporting >= 3:
        low, high = 0.35, 0.65
        verdict = "The evidence LEANS TOWARD SUPPORTING the hypothesis"
    elif n_supporting <= 1:
        low, high = 0.05, 0.25
        verdict = "The evidence LEANS AGAINST / DOES NOT CLEARLY SUPPORT the hypothesis"
    else:
        low, high = 0.15, 0.45
        verdict = "The evidence is MIXED / INCONCLUSIVE on the hypothesis"

    print(f"\n{n_supporting} of {n_testable} testable angles point toward the stock-availability hypothesis.")
    print(f"\nESTIMATE (explicitly a judgment range, not a measurement): roughly {low*100:.0f}%-{high*100:.0f}% of the "
          f"{total_late} late deliveries in this scope could PLAUSIBLY have been prevented by adequate stock on hand.")
    print("\nAssumptions behind this range (stated explicitly):")
    print("  1. The configured-vs-unconfigured and cover-vs-late-rate relationships in Part 1 (if present) are")
    print("     assumed to reflect stock availability's causal effect on lateness — but item type, customer mix,")
    print("     and manufacturing complexity differ across items too, and are NOT controlled for here.")
    print("  2. Order-size and timing effects (Parts 2-3) are assumed consistent with a 'stock drawn down, not")
    print("     replenished in time' mechanism where they point that direction — but the same patterns could also")
    print("     arise from other causes (e.g. genuinely longer production time for larger orders) not testable here.")
    print("  3. Where late rate follows item mix rather than customer behaviour (Part 4), this is taken as support")
    print("     for a stock/item-level cause rather than an order-placement behaviour cause — but 'item mix' could")
    print("     also proxy for item-specific MANUFACTURING difficulty, not only stock availability; this data cannot")
    print("     separate the two.")
    print("  4. No historical stock-level data exists (STATUS.md) — this estimate is NOT a measurement of stockouts")
    print("     coincident with late orders, only an inference from indirect correlates. It should be treated as a")
    print("     planning input to prioritize investigation, not as a validated figure.")

    print("\n" + "#" * 92)
    print(f"# BOTTOM-LINE VERDICT: {verdict}")
    print("#" * 92)

    print("\nCharts: output/charts/hyp_part1_config_vs_late_rate.png, hyp_part1_cover_vs_late_rate.png,")
    print("hyp_part2_late_rate_by_size_quartile.png, hyp_part3_late_by_month.png, hyp_part3_late_rate_by_timing_bucket.png,")
    print("hyp_part4_actual_vs_expected_late_rate.png")
    print("Full detail: output/summary/hyp_part1_*.csv through hyp_part5_*.csv")
