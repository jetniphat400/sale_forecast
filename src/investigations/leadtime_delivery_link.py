"""Task (2026-09-01), Part 4: connects Part 3's late-delivery findings to
order notice periods, to determine whether late deliveries were placed with
unusually short notice (a demand-timing problem, unfixable by holding more
stock) or had normal/long notice and were still late (a supply/planning
problem Max-Min could address).

Methodology decision (stated explicitly): notice period here is computed
SELF-CONTAINED within Cube_CES (PlanDelDate - CtrDate), on the exact same
assessable rows already classified on_time/early/late in
src/delivery_performance.py — NOT by joining across to the Part 2
cube_Sale_APD notice figures. Reason: Cube_CES splits contracts into finer
PlanID-level rows than cube_Sale_APD (STATUS.md, Cube_CES deep-dive), so a
cross-table join on (ContractID, ItemCode) would risk a many-to-many
mismatch between the two tables' different grains. Using one table's own
fields for both the notice period AND the on-time outcome keeps the
comparison on identical rows. Part 2's cube_Sale_APD-based notice
distribution is reported alongside as a cross-check/triangulation, not as
the basis for the classification below.

"Short notice" vs "adequate notice" split: uses the OVERALL median notice
period across ALL assessable Cube_CES rows in this scope as the cutoff — a
data-driven threshold, not an arbitrary external number. A late order is
classified SHORT_NOTICE if its own notice was below that overall median, and
ADEQUATE_NOTICE_STILL_LATE otherwise. This is a reasoned choice (documented
here), not from any external source.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("leadtime_delivery_link")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")


def dist_stats(s: pd.Series) -> dict:
    s = s.dropna()
    if len(s) == 0:
        return {"n": 0}
    return {"n": len(s), "mean": float(s.mean()), "median": float(s.median()), "std": float(s.std()),
            "q1": float(s.quantile(0.25)), "q3": float(s.quantile(0.75))}


if __name__ == "__main__":
    df = pd.read_csv(os.path.join(DATA_DIR, "processed_ces_delivery_assessable.csv"))
    for c in ["CtrDate", "PlanDelDate", "ForecastDelDate", "ActualDelDate"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["notice_days"] = (df["PlanDelDate"] - df["CtrDate"]).dt.days

    n_negative_notice = (df["notice_days"] < 0).sum()
    logger.info("%d of %d assessable CES rows (%.2f%%) have a negative notice period (PlanDelDate before CtrDate) "
                "— same class of anomaly flagged in Part 2, excluded from the notice-vs-lateness comparison",
                n_negative_notice, len(df), 100 * n_negative_notice / len(df))
    df_pos = df[df["notice_days"] >= 0].copy()

    late = df_pos[df_pos["status_vs_plan"] == "late"].copy()
    nonlate = df_pos[df_pos["status_vs_plan"] != "late"].copy()

    late_stats = dist_stats(late["notice_days"])
    nonlate_stats = dist_stats(nonlate["notice_days"])
    u_stat, p_value = stats.mannwhitneyu(late["notice_days"].dropna(), nonlate["notice_days"].dropna(), alternative="two-sided")
    comparison_df = pd.DataFrame([
        {"group": "late_deliveries", **late_stats},
        {"group": "on_time_or_early_deliveries", **nonlate_stats},
    ])
    comparison_df.to_csv(os.path.join(SUMMARY_DIR, "link_notice_late_vs_nonlate.csv"), index=False)

    # ================= DATA-DRIVEN SHORT/ADEQUATE-NOTICE SPLIT =================
    overall_median_notice = df_pos["notice_days"].median()
    late["notice_category"] = np.where(late["notice_days"] < overall_median_notice,
                                        "SHORT_NOTICE", "ADEQUATE_NOTICE_STILL_LATE")
    late.to_csv(os.path.join(DATA_DIR, "processed_late_deliveries_with_notice.csv"), index=False)

    category_counts = late["notice_category"].value_counts()
    category_pct = (100 * category_counts / len(late)).round(2)
    category_summary = pd.DataFrame({"n": category_counts, "pct_of_late_deliveries": category_pct})
    category_summary.to_csv(os.path.join(SUMMARY_DIR, "link_late_delivery_category_split.csv"))

    # Same split, weighted by lateness magnitude and by backlog-relevant quantity (ActualQty)
    late_qty_by_category = late.groupby("notice_category")["ActualQty"].sum()
    late_delaydays_by_category = late.groupby("notice_category")["delay_vs_plan"].agg(["mean", "median", "sum"])
    weighted_df = late_qty_by_category.to_frame("total_qty_late").join(late_delaydays_by_category)
    weighted_df.to_csv(os.path.join(SUMMARY_DIR, "link_late_delivery_category_weighted.csv"))

    # ================= BREAKDOWN OF THE SPLIT BY PRODUCT TYPE / CUSTOMER / YEAR =================
    by_type = late.groupby(["type", "notice_category"]).size().unstack(fill_value=0)
    by_type["pct_short_notice"] = (100 * by_type.get("SHORT_NOTICE", 0) / by_type.sum(axis=1)).round(1)
    by_type.to_csv(os.path.join(SUMMARY_DIR, "link_late_category_by_type.csv"))

    by_year = late.assign(year=late["CtrDate"].dt.year).groupby(["year", "notice_category"]).size().unstack(fill_value=0)
    by_year["pct_short_notice"] = (100 * by_year.get("SHORT_NOTICE", 0) / by_year.sum(axis=1)).round(1)
    by_year.to_csv(os.path.join(SUMMARY_DIR, "link_late_category_by_year.csv"))

    cust_counts = late["CustomerID"].value_counts()
    top_late_customers = cust_counts.head(10).index.tolist()
    by_customer = late[late["CustomerID"].isin(top_late_customers)].groupby(["CustomerID", "notice_category"]).size().unstack(fill_value=0)
    by_customer["n_late_total"] = by_customer.sum(axis=1)
    by_customer = by_customer.sort_values("n_late_total", ascending=False)
    by_customer.to_csv(os.path.join(SUMMARY_DIR, "link_late_category_by_top_customers.csv"))

    # ================= CROSS-CHECK: Part 2's cube_Sale_APD notice distribution, reported alongside =================
    apd_notice_path = os.path.join(SUMMARY_DIR, "leadtime_overall_distribution.csv")
    apd_notice = pd.read_csv(apd_notice_path).iloc[0].to_dict() if os.path.exists(apd_notice_path) else None

    # ============================= CHARTS =============================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.boxplot([late["notice_days"].clip(upper=90), nonlate["notice_days"].clip(upper=90)],
               tick_labels=["Late deliveries", "On-time/Early deliveries"], showfliers=False)
    ax.axhline(overall_median_notice, color="gray", linestyle="--", linewidth=1, label=f"overall median ({overall_median_notice:.0f}d)")
    ax.set_title("Order notice period: late vs. non-late deliveries")
    ax.set_ylabel("Notice days (PlanDelDate - CtrDate), capped at 90")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "link_notice_late_vs_nonlate.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    category_counts.reindex(["SHORT_NOTICE", "ADEQUATE_NOTICE_STILL_LATE"]).plot(
        kind="pie", ax=ax, autopct="%1.1f%%", colors=["tab:orange", "tab:red"], ylabel="")
    ax.set_title("Late deliveries: short notice vs. adequate notice but still late")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "link_late_delivery_category_split.png"))
    plt.close(fig)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 92)
    print("# PART 4: CONNECTING LATE DELIVERIES TO ORDER NOTICE PERIODS")
    print("#" * 92)
    print(f"\n{n_negative_notice} of {len(df)} assessable rows ({100*n_negative_notice/len(df):.2f}%) excluded for "
          f"negative notice (data anomaly, same class as Part 2's finding).")
    print(f"\n{len(late)} late deliveries and {len(nonlate)} on-time/early deliveries compared "
          f"(of {len(df_pos)} assessable rows with a valid non-negative notice period).")

    print("\n--- NOTICE PERIOD: late vs. non-late deliveries ---")
    print(comparison_df.to_string(index=False))
    direction = "LONGER" if late_stats["median"] > nonlate_stats["median"] else "SHORTER"
    print(f"\nLate deliveries had a {direction} median notice period ({late_stats['median']:.0f} days) than "
          f"on-time/early deliveries ({nonlate_stats['median']:.0f} days).")
    print(f"Mann-Whitney U test: U={u_stat:.1f}, p={p_value:.2e} — "
          f"{'a statistically significant difference' if p_value < 0.05 else 'NO statistically significant difference'} "
          f"in notice period between late and non-late deliveries.")
    if direction == "LONGER" or p_value >= 0.05:
        print("This does NOT support 'late orders were placed with unusually short notice' as the general "
              "explanation — if anything, late orders had normal-to-slightly-longer notice than average, which "
              "points toward a supply/planning problem rather than a demand-timing problem.")
    else:
        print("This IS consistent with 'late orders were placed with unusually short notice' as a contributing "
              "explanation for at least part of the late-delivery problem.")

    print(f"\n--- QUANTIFIED SPLIT (cutoff = overall median notice of this scope = {overall_median_notice:.0f} days) ---")
    print(category_summary.to_string())
    print("\nWeighted by quantity and lateness magnitude:")
    print(weighted_df.round(2).to_string())

    print("\n--- BY PRODUCT TYPE (of late deliveries, %% that fall in SHORT_NOTICE) ---")
    print(by_type.to_string())
    print("\n--- BY YEAR (of late deliveries, %% that fall in SHORT_NOTICE) ---")
    print(by_year.to_string())
    print("\n--- BY TOP 10 LATE CUSTOMERS ---")
    print(by_customer.to_string())

    if apd_notice:
        print("\n--- CROSS-CHECK: Part 2's cube_Sale_APD-based overall notice distribution (different table, for context only) ---")
        print(pd.Series(apd_notice).to_string())

    print("\n" + "=" * 92)
    print("BOTTOM LINE")
    print("=" * 92)
    n_short = int(category_counts.get("SHORT_NOTICE", 0))
    n_adequate = int(category_counts.get("ADEQUATE_NOTICE_STILL_LATE", 0))
    print(f"Of {len(late)} late deliveries in this scope: {n_short} ({100*n_short/len(late):.1f}%) had "
          f"below-median notice (SHORT_NOTICE — a demand-timing problem, not fixable by holding more stock); "
          f"{n_adequate} ({100*n_adequate/len(late):.1f}%) had at-or-above-median notice and were STILL late "
          f"(ADEQUATE_NOTICE_STILL_LATE — points to a supply/planning problem that Max-Min could plausibly address).")
    print(f"The MAJORITY of the late-delivery problem in this scope falls into the "
          f"{'ADEQUATE_NOTICE_STILL_LATE' if n_adequate > n_short else 'SHORT_NOTICE'} category.")

    print("\nCharts: output/charts/link_notice_late_vs_nonlate.png, link_late_delivery_category_split.png")
    print("Full detail: output/summary/link_*.csv")
