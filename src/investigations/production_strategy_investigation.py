"""Phase 4 prep investigation, Parts 1-2: make-to-stock vs make-to-order.

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched.
Scope: the 128 item codes in Product Cate. Fuse and Surge Arrester
(output/summary/part1_category_scope_all_codes.csv).

Part 1: search cube_Sale_APD's own manufacturing_type field (and the item-master
Assortment fields, already surveyed in src/investigate_leadtime_classification.py) for a
production-strategy classification, and report its distinct values, coverage and reliability.

Part 2: since manufacturing_type is an ORDER-level attribute (not a fixed item property,
established in the earlier Phase 4 groundwork survey), infer production strategy from
delivery speed instead. Reasoning applied, stated explicitly per instruction: customers give
a median of 6 days' order notice (STATUS.md, order-notice task) while stated production lead
time is 45-60 days. An item consistently delivered within days of the PO must be filled from
stock already held; an item consistently taking close to the full production lead time is
likely produced to order. This is inference from delivery timing, not a recorded fact.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("production_strategy_investigation")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

# Classification bands for Part 2, stated explicitly (reasoned judgment, not a business rule):
# MTS band: median order-to-delivery <= 14 days. Roughly 2x the 6-day median customer notice,
# a generous buffer, since even 2 weeks is far below any plausible production lead time.
MTS_MAX_DAYS = 14
# MTO band: 30-75 days, bracketing the stated 45-60 day default with a +/-15 day buffer for
# realistic variation around a stated range rather than a single point estimate.
MTO_MIN_DAYS = 30
MTO_MAX_DAYS = 75
# Minimum sample size to trust a per-item median at all.
MIN_ORDERS = 5
# An item's spread is considered too wide to trust the median if IQR exceeds the median itself
# (i.e., the spread is at least as large as the central value) - downgrades to Cannot Determine
# even if the median alone would fall in a band.
MAX_IQR_TO_MEDIAN_RATIO = 1.0


def get_scope() -> pd.DataFrame:
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))


def get_item_values(codes: list) -> pd.Series:
    """Total sales value ('sale') per item, from the already-pulled 128-item, PEM101/Omni
    Channel, Actual+MPS, 2024-01-01+ row-level sales pull (raw_full_category_sales.csv)."""
    path = os.path.join(DATA_DIR, "raw_full_category_sales.csv")
    df = pd.read_csv(path)
    return df.groupby("itemcode")["sale"].sum()


def classify_item(median_days, n_orders, iqr) -> str:
    if n_orders < MIN_ORDERS:
        return "Cannot determine (too few observed deliveries)"
    if pd.isna(median_days):
        return "Cannot determine (no data)"
    if iqr is not None and not pd.isna(iqr) and median_days > 0 and (iqr / median_days) > MAX_IQR_TO_MEDIAN_RATIO:
        return "Cannot determine (spread too wide to trust the median)"
    if median_days <= MTS_MAX_DAYS:
        return "Likely make-to-stock"
    if MTO_MIN_DAYS <= median_days <= MTO_MAX_DAYS:
        return "Likely make-to-order"
    return "Cannot determine (median outside both bands)"


if __name__ == "__main__":
    scope = get_scope()
    codes = sorted(scope["code"].unique())
    code_list = "','".join(codes)
    item_type_map = scope.set_index("code")[["category", "type"]]

    # ================= PART 1: manufacturing_type =================
    print("\n" + "#" * 92)
    print("# PART 1: manufacturing_type IN cube_Sale_APD")
    print("#" * 92)

    mt_whole = run_query("SELECT manufacturing_type, COUNT(*) n FROM cube_Sale_APD GROUP BY manufacturing_type ORDER BY n DESC")
    mt_whole["pct"] = (100 * mt_whole["n"] / mt_whole["n"].sum()).round(2)
    mt_whole.to_csv(os.path.join(SUMMARY_DIR, "part1_manufacturing_type_whole_table.csv"), index=False)
    print("\nDistinct values, whole cube_Sale_APD table (51,059+ rows table-wide):")
    print(mt_whole.to_string(index=False))
    print("\nThese three named values (MTS, MTO, ETO) are the standard production-strategy")
    print("abbreviations (Make-to-Stock, Make-to-Order, Engineer-to-Order); a blank/NULL value")
    print("also occurs. No lookup/description table was found defining them explicitly - this")
    print("reading is based on the values matching standard industry terminology, not a")
    print("database comment or documentation string.")

    logger.info("Pulling manufacturing_type rows for the 128-item scope")
    mt128 = run_query(f"SELECT itemcode, manufacturing_type, COUNT(*) n FROM cube_Sale_APD "
                       f"WHERE itemcode IN ('{code_list}') GROUP BY itemcode, manufacturing_type")
    mt128.to_csv(os.path.join(SUMMARY_DIR, "part1_manufacturing_type_128items.csv"), index=False)

    n_covered = mt128["itemcode"].nunique()
    n_no_rows = len(codes) - n_covered
    print(f"\nCoverage: {n_covered} of {len(codes)} items ({100*n_covered/len(codes):.1f}%) appear in "
          f"cube_Sale_APD with a manufacturing_type value recorded at all; {n_no_rows} items have zero rows.")

    # Per-item: dominant value, purity, mixed flag
    mt128["manufacturing_type"] = mt128["manufacturing_type"].fillna("(blank)")
    pivot = mt128.pivot_table(index="itemcode", columns="manufacturing_type", values="n", aggfunc="sum", fill_value=0)
    pivot["total_orders"] = pivot.sum(axis=1)
    value_cols = [c for c in pivot.columns if c != "total_orders"]
    pivot["dominant_type"] = pivot[value_cols].idxmax(axis=1)
    pivot["dominant_share_pct"] = (100 * pivot[value_cols].max(axis=1) / pivot["total_orders"]).round(1)
    pivot["n_distinct_values"] = (pivot[value_cols] > 0).sum(axis=1)
    pivot["is_mixed"] = pivot["n_distinct_values"] > 1
    pivot = pivot.reset_index().merge(item_type_map, left_on="itemcode", right_index=True, how="left")
    pivot.to_csv(os.path.join(SUMMARY_DIR, "part1_manufacturing_type_per_item_distribution.csv"), index=False)

    n_mixed = pivot["is_mixed"].sum()
    print(f"\n{n_mixed} of {n_covered} covered items ({100*n_mixed/n_covered:.1f}%) show MORE THAN ONE "
          f"manufacturing_type value across their own sales rows (e.g. some orders MTS, others MTO for the "
          f"SAME item code). This means manufacturing_type is recorded per ORDER, not as a fixed property of "
          f"the item - it describes how that specific order was fulfilled, which can vary order to order.")

    dominant_counts = pivot["dominant_type"].value_counts()
    print("\nDistribution of the 128 items by their DOMINANT (most frequent) manufacturing_type value "
          "(not a claim that this is the item's fixed classification, just its most common order pattern):")
    print(dominant_counts.to_string())
    print(f"(+ {n_no_rows} items with no manufacturing_type rows at all -> cannot be classified this way)")

    # Corroborating evidence: FMTS/FMTO warehouse codes in the current inventory snapshot
    inv_path = os.path.join(DATA_DIR, "raw_inventory_exact_128items.csv")
    if os.path.exists(inv_path):
        inv = pd.read_csv(inv_path)
        inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
        fmts_fmto = inv[inv["warehouse"].isin(["FMTS", "FMTO"])]
        items_fmts = set(fmts_fmto.loc[fmts_fmto["warehouse"] == "FMTS", "itemcode"])
        items_fmto = set(fmts_fmto.loc[fmts_fmto["warehouse"] == "FMTO", "itemcode"])
        both = items_fmts & items_fmto
        print(f"\nCorroborating evidence from Cube_Inventory_Exact: this table carries two production-order "
              f"staging locations literally named 'FMTS' and 'FMTO' (Finished-goods Make-To-Stock / "
              f"Make-To-Order work-in-progress buckets, read from the code, not a documented definition). "
              f"{len(items_fmts)} items have an FMTS row and {len(items_fmto)} have an FMTO row in the "
              f"current snapshot; {len(both)} items have BOTH. This independently corroborates the "
              f"manufacturing_type finding: the SAME item is staged under both production strategies "
              f"depending on the order, not assigned to one permanently.")

    print("\n--- PART 1 CONCLUSION ---")
    print(f"manufacturing_type covers {n_covered}/{len(codes)} items ({100*n_covered/len(codes):.1f}%) but "
          f"CANNOT reliably classify these items into a fixed MTS/MTO/ETO category: it is an order-level "
          f"field, {n_mixed} of {n_covered} covered items ({100*n_mixed/n_covered:.1f}%) show more than one "
          f"value, and warehouse-level evidence (FMTS/FMTO staging) independently shows the same pattern. "
          f"No other table surveyed in this project (Cube_ItemList's Assortment fields, ItemGroup, "
          f"Condition - see src/investigate_leadtime_classification.py) carries an item-level production-"
          f"strategy, procurement-type or planning-policy field. If a single, fixed per-item classification "
          f"is needed for Phase 4, it must come from the business, not this field.")

    # ================= PART 2: infer from delivery speed =================
    print("\n" + "#" * 92)
    print("# PART 2: INFERRING PRODUCTION STRATEGY FROM ORDER-TO-DELIVERY TIMING (Cube_CES)")
    print("#" * 92)

    ces_path = os.path.join(DATA_DIR, "raw_cube_ces_delivery_128items.csv")
    ces = pd.read_csv(ces_path)
    print(f"\nReusing the existing Cube_CES pull ({ces_path}): {len(ces)} rows, ManuDivision=PEM101, "
          f"RevenueType=Omni Channel, Status IN ('Actual','Backlog'), CtrDate >= 2023-01-01.")
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")

    delivered = ces[(ces["Status"] == "Actual") & ces["ActualDelDate"].notna() & ces["CtrDate"].notna()].copy()
    delivered["interval_days"] = (delivered["ActualDelDate"] - delivered["CtrDate"]).dt.days
    n_before_excl = len(delivered)
    n_negative = (delivered["interval_days"] < 0).sum()
    delivered = delivered[delivered["interval_days"] >= 0].copy()
    print(f"\n{n_before_excl} rows have a completed delivery (Status='Actual', non-null CtrDate and "
          f"ActualDelDate). {n_negative} rows ({100*n_negative/n_before_excl:.2f}%) show ActualDelDate before "
          f"CtrDate - a data anomaly (same class found in the earlier order-notice task), EXCLUDED from the "
          f"stats below. {len(delivered)} rows remain.")
    delivered.rename(columns={"ItemCode": "itemcode"}).to_csv(
        os.path.join(DATA_DIR, "processed_order_to_delivery_interval.csv"), index=False)
    delivered = delivered.rename(columns={"ItemCode": "itemcode"})

    per_item = delivered.groupby("itemcode")["interval_days"].agg(
        n_orders="count", median_days="median", mean_days="mean", std_days="std",
        q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75), min_days="min", max_days="max",
    ).reset_index()
    per_item["iqr_days"] = per_item["q3"] - per_item["q1"]
    per_item["classification"] = per_item.apply(
        lambda r: classify_item(r["median_days"], r["n_orders"], r["iqr_days"]), axis=1)

    # Items with zero Cube_CES delivery evidence at all
    covered_items = set(per_item["itemcode"])
    no_evidence = [c for c in codes if c not in covered_items]
    no_evidence_df = pd.DataFrame({"itemcode": no_evidence, "n_orders": 0, "classification": "Cannot determine (no delivery data in Cube_CES)"})
    per_item_full = pd.concat([per_item, no_evidence_df], ignore_index=True)
    per_item_full = per_item_full.merge(item_type_map, left_on="itemcode", right_index=True, how="left")

    values = get_item_values(codes)
    per_item_full["sales_value"] = per_item_full["itemcode"].map(values).fillna(0)
    per_item_full.to_csv(os.path.join(SUMMARY_DIR, "part2_production_strategy_classification.csv"), index=False)

    print(f"\nItems with at least one assessable delivery in Cube_CES: {len(per_item)} of {len(codes)}. "
          f"{len(no_evidence)} items have zero Cube_CES delivery rows at all in this scope/window.")

    print(f"\nClassification bands used (stated explicitly, a reasoned judgment call, NOT a business rule):")
    print(f"  Likely make-to-stock : median order-to-delivery <= {MTS_MAX_DAYS} days")
    print(f"  Likely make-to-order : median order-to-delivery between {MTO_MIN_DAYS} and {MTO_MAX_DAYS} days "
          f"(brackets the stated 45-60 day default with a +/-15 day buffer)")
    print(f"  Cannot determine     : fewer than {MIN_ORDERS} observed deliveries, OR median in the "
          f"{MTS_MAX_DAYS+1}-{MTO_MIN_DAYS-1} day gap or above {MTO_MAX_DAYS} days, OR the interquartile "
          f"range exceeds the median itself (spread as large as the central value - median not trustworthy)")

    class_summary = per_item_full.groupby("classification").agg(
        n_items=("itemcode", "nunique"), total_sales_value=("sales_value", "sum")
    ).sort_values("total_sales_value", ascending=False)
    class_summary["pct_of_items"] = (100 * class_summary["n_items"] / len(codes)).round(1)
    total_value = per_item_full["sales_value"].sum()
    class_summary["pct_of_value"] = (100 * class_summary["total_sales_value"] / total_value).round(1)
    class_summary.to_csv(os.path.join(SUMMARY_DIR, "part2_classification_summary.csv"))

    print("\n--- CLASSIFICATION RESULT (128 items) ---")
    print(class_summary.round(1).to_string())
    print(f"\n(Total sales value across the 128 items, 2024-01-01+ PEM101/Omni Channel Actual+MPS basis: "
          f"THB {total_value:,.0f})")

    mts_items = per_item_full[per_item_full["classification"] == "Likely make-to-stock"]
    mto_items = per_item_full[per_item_full["classification"] == "Likely make-to-order"]
    if len(mts_items):
        print(f"\nLikely make-to-stock items - median interval range: "
              f"{mts_items['median_days'].min():.0f} to {mts_items['median_days'].max():.0f} days")
    if len(mto_items):
        print(f"Likely make-to-order items - median interval range: "
              f"{mto_items['median_days'].min():.0f} to {mto_items['median_days'].max():.0f} days")

    print("\n--- IMPORTANT CAVEATS (stated explicitly, per instruction) ---")
    print("This is INFERENCE from delivery timing, not a recorded fact. It assumes the order-to-delivery")
    print("interval reflects how the order was fulfilled (from stock vs produced/procured), which the data")
    print("cannot directly confirm - no field in Cube_CES or cube_Sale_APD states why a delivery took as long")
    print("as it did. An item could show a short interval because it happens to be a fast-moving MTS item, OR")
    print("because it was made to order using expedited/rush production - the data cannot distinguish these.")
    print("The business should confirm this classification, especially for the 'Cannot determine' bucket.")

    print("\nOutputs: output/summary/part1_manufacturing_type_whole_table.csv, "
          "part1_manufacturing_type_128items.csv, part1_manufacturing_type_per_item_distribution.csv, "
          "part2_production_strategy_classification.csv, part2_classification_summary.csv")
