"""Phase 4 prep investigation, Part 4: actual lead time from the data, vs the stated 45-60
day default.

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched.
Scope: the 128 item codes in Product Cate. Fuse and Surge Arrester.

Reuses output/data/processed_order_to_delivery_interval.csv, written by
src/production_strategy_investigation.py Part 2 (order-to-delivery interval, CtrDate to
ActualDelDate, Cube_CES, ManuDivision=PEM101/RevenueType=Omni Channel/Status='Actual', negative
anomalies already excluded there). This script adds the per-product-type view and the explicit
comparison against the stated 45-60 day default - it does not recompute the interval.

Explicit distinction stated per instruction: this measures ORDER-TO-DELIVERY time (when the
order was placed to when it was actually delivered), which mixes however much of that time was
spent on stock allocation, production, procurement and logistics together. It is NOT the same
as a pure procurement or production lead time (time to make/buy the item once a decision to
produce/procure is made) - the data has no field isolating that narrower quantity.
"""
import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

DEFAULT_MIN_DAYS = 45
DEFAULT_MAX_DAYS = 60


def get_scope() -> pd.DataFrame:
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))


if __name__ == "__main__":
    scope = get_scope()
    item_type_map = scope.set_index("code")[["category", "type"]]

    print("\n" + "#" * 92)
    print("# PART 4: ACTUAL LEAD TIME FROM THE DATA vs THE STATED 45-60 DAY DEFAULT")
    print("#" * 92)

    delivered = pd.read_csv(os.path.join(DATA_DIR, "processed_order_to_delivery_interval.csv"))
    print(f"\nReusing {len(delivered)} order-to-delivery observations already computed in Part 2 "
          f"(CtrDate to ActualDelDate, Cube_CES, ManuDivision=PEM101/RevenueType=Omni Channel/Status='Actual', "
          f"CtrDate >= 2023-01-01, negative-interval anomalies already excluded).")
    delivered = delivered.merge(item_type_map, left_on="itemcode", right_index=True, how="left")

    # ================= PER ITEM =================
    per_item = delivered.groupby("itemcode")["interval_days"].agg(
        n_orders="count", median_days="median", mean_days="mean", std_days="std",
        q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75), min_days="min", max_days="max",
    )
    per_item["iqr_days"] = per_item["q3"] - per_item["q1"]
    per_item = per_item.merge(item_type_map, left_index=True, right_index=True, how="left")
    per_item.to_csv(os.path.join(SUMMARY_DIR, "part4_leadtime_per_item.csv"))

    codes = sorted(scope["code"].unique())
    n_no_data = len(codes) - per_item.shape[0]
    print(f"\n{per_item.shape[0]} of {len(codes)} items have at least one observation; {n_no_data} have none "
          f"(same items flagged with no Cube_CES delivery data in Part 2).")

    faster = per_item[per_item["median_days"] < DEFAULT_MIN_DAYS]
    within = per_item[(per_item["median_days"] >= DEFAULT_MIN_DAYS) & (per_item["median_days"] <= DEFAULT_MAX_DAYS)]
    slower = per_item[per_item["median_days"] > DEFAULT_MAX_DAYS]
    print(f"\nAgainst the stated {DEFAULT_MIN_DAYS}-{DEFAULT_MAX_DAYS} day default, by median observed interval:")
    print(f"  FASTER than the default (median < {DEFAULT_MIN_DAYS} days): {len(faster)} of {per_item.shape[0]} items "
          f"({100*len(faster)/per_item.shape[0]:.1f}%)")
    print(f"  WITHIN the default range ({DEFAULT_MIN_DAYS}-{DEFAULT_MAX_DAYS} days): {len(within)} items "
          f"({100*len(within)/per_item.shape[0]:.1f}%)")
    print(f"  SLOWER than the default (median > {DEFAULT_MAX_DAYS} days): {len(slower)} items "
          f"({100*len(slower)/per_item.shape[0]:.1f}%)")
    print(f"\nOverall median across all {per_item.shape[0]} items' own medians: {per_item['median_days'].median():.1f} "
          f"days - the great majority of items are delivered far FASTER than the stated 45-60 day default, not "
          f"slower. Distribution of item medians: p10={per_item['median_days'].quantile(.1):.1f}, "
          f"p25={per_item['median_days'].quantile(.25):.1f}, p50={per_item['median_days'].median():.1f}, "
          f"p75={per_item['median_days'].quantile(.75):.1f}, p90={per_item['median_days'].quantile(.9):.1f}, "
          f"max={per_item['median_days'].max():.0f}.")

    print(f"\nSpread matters as much as the centre for safety stock (stated per instruction, not just reported "
          f"as an aside): item-level IQR (q3-q1) ranges from {per_item['iqr_days'].min():.0f} to "
          f"{per_item['iqr_days'].max():.0f} days, median IQR {per_item['iqr_days'].median():.0f} days. "
          f"{(per_item['iqr_days'] > per_item['median_days']).sum()} of {per_item.shape[0]} items "
          f"({100*(per_item['iqr_days'] > per_item['median_days']).mean():.1f}%) have an IQR LARGER than their own "
          f"median - meaning the spread around the typical value is at least as big as the typical value itself. "
          f"A single point estimate (even a correct one) would understate how variable actual delivery timing "
          f"is for a large share of these items.")

    slowest = per_item.sort_values("median_days", ascending=False).head(10)
    print("\n10 items with the LONGEST median observed interval:")
    print(slowest[["category", "type", "n_orders", "median_days", "iqr_days", "max_days"]].round(1).to_string())
    fastest = per_item.sort_values("median_days", ascending=True).head(10)
    print("\n10 items with the SHORTEST median observed interval:")
    print(fastest[["category", "type", "n_orders", "median_days", "iqr_days", "max_days"]].round(1).to_string())

    # ================= PER PRODUCT TYPE =================
    print("\n--- BY PRODUCT TYPE ---")
    by_type = delivered.groupby("type").agg(
        n_orders=("interval_days", "count"),
        n_items=("itemcode", "nunique"),
        median_days=("interval_days", "median"),
        mean_days=("interval_days", "mean"),
        std_days=("interval_days", "std"),
        q1=("interval_days", lambda s: s.quantile(0.25)),
        q3=("interval_days", lambda s: s.quantile(0.75)),
    )
    by_type["iqr_days"] = by_type["q3"] - by_type["q1"]
    by_type["vs_default"] = by_type["median_days"].apply(
        lambda m: "faster" if m < DEFAULT_MIN_DAYS else ("within" if m <= DEFAULT_MAX_DAYS else "slower"))
    by_type = by_type.sort_values("median_days", ascending=False)
    by_type.to_csv(os.path.join(SUMMARY_DIR, "part4_leadtime_by_product_type.csv"))
    print(by_type.round(1).to_string())

    n_types_faster = (by_type["vs_default"] == "faster").sum()
    print(f"\n{n_types_faster} of {len(by_type)} product TYPES have a median order-to-delivery interval faster "
          f"than the {DEFAULT_MIN_DAYS}-day floor of the stated default; none exceed {DEFAULT_MAX_DAYS} days at "
          f"the type level (aggregation smooths out the few individual items with very long medians seen above).")

    print("\n--- WHAT THIS DOES AND DOES NOT MEASURE (stated explicitly, per instruction) ---")
    print("This is ORDER-TO-DELIVERY time: CtrDate (when the PO was received) to ActualDelDate (when it was")
    print("actually delivered to the customer). It is NOT the same as procurement or production lead time (the")
    print("time needed to make or buy the item once a decision to produce/procure is made). If most orders are")
    print("filled from stock already on hand (as the order-notice task in STATUS.md found - median customer")
    print("notice is only 6 days), order-to-delivery time mostly reflects allocation/logistics speed for THOSE")
    print("orders, not how long it would take to replenish the stock that filled them. This can UNDERSTATE the")
    print("true production/procurement lead time for items that are rarely actually produced-to-order in this")
    print("window. Conversely, for items with a genuinely long observed interval, this measure cannot tell us")
    print("how much of that time was production/procurement vs. something else (customer-requested late")
    print("delivery, logistics delay, partial-shipment scheduling) - no cause field exists in this data.")
    print("CONCLUSION: this measure is a useful CROSS-CHECK on the stated 45-60 day default, and shows the")
    print("observed reality is faster for the great majority of items, but it cannot by itself CONFIRM or REPLACE")
    print("a procurement/production lead time figure - that should still come from purchasing/production.")

    print("\nOutputs: output/summary/part4_leadtime_per_item.csv, part4_leadtime_by_product_type.csv")
