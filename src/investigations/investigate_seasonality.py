"""Phase 4 groundwork survey, Part 5: seasonal pattern check for Fuse and
Surge Arrester categories and their 8 Types — monthly demand for every month
of 2024, 2025 and 2026 (2026 partial, through August, and August itself is
an incomplete calendar month).

Reports numbers only. Does NOT fit or apply any seasonal model, and does not
claim a pattern beyond what two years (plus one partial) can support.
"""
import logging
import os
import sys

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_seasonality")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def build_month_of_year_table(monthly: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    monthly = monthly.copy()
    monthly["year"] = monthly["year_month"].str.slice(0, 4).astype(int)
    monthly["month"] = monthly["year_month"].str.slice(5, 7).astype(int)
    agg = monthly.groupby(group_cols + ["year", "month"], as_index=False)["qty"].sum()
    return agg


if __name__ == "__main__":
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    max_date = pd.to_datetime(raw["createDate"]).max()
    logger.info("Data available through %s. 2026 is a PARTIAL year (through August, and August itself "
                "is an incomplete calendar month, ending %s not August 31).", max_date.date(), max_date.date())

    cat_month = build_month_of_year_table(monthly, ["category"])
    type_month = build_month_of_year_table(monthly, ["category", "type"])

    cat_pivot = cat_month.pivot_table(index="category", columns=["year", "month"], values="qty", fill_value=0)
    type_pivot = type_month.pivot_table(index=["category", "type"], columns=["year", "month"], values="qty", fill_value=0)

    cat_month.to_csv(os.path.join(SUMMARY_DIR, "phase4_part5_category_monthly.csv"), index=False)
    type_month.to_csv(os.path.join(SUMMARY_DIR, "phase4_part5_type_monthly.csv"), index=False)

    print("\n" + "=" * 90)
    print("PART 5: SEASONAL PATTERN CHECK — monthly qty by category")
    print("=" * 90)
    print(cat_pivot.to_string())

    print("\n--- By Type ---")
    print(type_pivot.to_string())

    # Month-of-year comparison across years (2024 full, 2025 full, 2026 partial through Aug)
    print("\n" + "=" * 90)
    print("MONTH-OF-YEAR COMPARISON (is any calendar month consistently high/low across years?)")
    print("=" * 90)

    findings = []
    for cat, g in cat_month.groupby("category"):
        wide = g.pivot_table(index="month", columns="year", values="qty", fill_value=0)
        wide = wide.reindex(range(1, 13))
        wide.index = [MONTH_NAMES[m - 1] for m in range(1, 13)]
        print(f"\n{cat} — qty by calendar month, each year as its own column:")
        print(wide.to_string())
        # rank months within each year (only years with data for that month)
        ranks = wide.rank(ascending=False)
        avg_rank = ranks.mean(axis=1)
        top_month = avg_rank.idxmin()
        bottom_month = avg_rank.idxmax()
        agreement = {}
        for m in wide.index:
            vals = wide.loc[m]
            agreement[m] = vals.to_dict()
        findings.append({"level": "Category", "key": cat, "avg_rank_lowest_(highest_demand)_month": top_month,
                          "avg_rank_highest_(lowest_demand)_month": bottom_month})

    for (cat, typ), g in type_month.groupby(["category", "type"]):
        wide = g.pivot_table(index="month", columns="year", values="qty", fill_value=0)
        wide = wide.reindex(range(1, 13))
        wide.index = [MONTH_NAMES[m - 1] for m in range(1, 13)]
        ranks = wide.rank(ascending=False)
        avg_rank = ranks.mean(axis=1)
        top_month = avg_rank.idxmin()
        bottom_month = avg_rank.idxmax()
        findings.append({"level": "Type", "key": typ, "category": cat,
                          "avg_rank_lowest_(highest_demand)_month": top_month,
                          "avg_rank_highest_(lowest_demand)_month": bottom_month})

    findings_df = pd.DataFrame(findings)
    findings_df.to_csv(os.path.join(SUMMARY_DIR, "phase4_part5_month_rank_summary.csv"), index=False)

    print("\n" + "=" * 90)
    print("LIMITATION — stated explicitly per instruction")
    print("=" * 90)
    print("Only 2 complete years (2024, 2025) plus one partial year (2026, through August) are available.")
    print("With 2 complete years, a calendar month appearing 'high' or 'low' in both could be a genuine")
    print("seasonal effect OR simple coincidence — 2 data points cannot statistically distinguish a real")
    print("cycle from chance variation. The table above reports the raw numbers and which month ranks")
    print("highest/lowest on average; it does NOT constitute evidence of a confirmed seasonal pattern.")
    print("A defensible seasonal claim would need at least 3-4 complete years, which this dataset does not have.")
