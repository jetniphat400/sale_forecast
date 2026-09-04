"""Phase 4 prep investigation, Part 5: order quantity patterns (lot size / MOQ evidence).

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched.
Scope: the 128 item codes in Product Cate. Fuse and Surge Arrester.

Reuses output/data/raw_full_category_sales.csv (row-level orders, PEM101/Omni Channel,
Actual+MPS, 2024-01-01+, already pulled for the Phase 3.1 category-scope expansion task).
Looks for round-number clustering and recurring multiples in order quantity ('qty') per item -
this is observational evidence for a possible lot size or minimum order quantity, not proof of
one, since the data has no field that states a lot size or MOQ directly.
"""
import os
from math import gcd
from functools import reduce

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

MIN_ORDERS_FOR_ANALYSIS = 10
# Candidate lot sizes checked for "% of orders that are an exact multiple of L" evidence.
CANDIDATE_LOT_SIZES = [1, 2, 3, 5, 6, 10, 12, 15, 20, 25, 50, 100]
STRONG_MULTIPLE_COVERAGE_PCT = 80.0
STRONG_MODE_SHARE_PCT = 25.0


def get_scope() -> pd.DataFrame:
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))


def best_multiple_candidate(qtys: pd.Series):
    """Largest candidate lot size L>1 for which at least STRONG_MULTIPLE_COVERAGE_PCT% of
    orders (by count) are an exact multiple of L. Returns (L, coverage_pct) or (1, 100.0)."""
    best = (1, 100.0)
    for L in CANDIDATE_LOT_SIZES:
        if L == 1:
            continue
        coverage = 100 * (qtys % L == 0).mean()
        if coverage >= STRONG_MULTIPLE_COVERAGE_PCT and L > best[0]:
            best = (L, round(coverage, 1))
    return best


if __name__ == "__main__":
    scope = get_scope()
    item_type_map = scope.set_index("code")[["category", "type"]]

    print("\n" + "#" * 92)
    print("# PART 5: ORDER QUANTITY PATTERNS (LOT SIZE / MOQ EVIDENCE)")
    print("#" * 92)

    orders = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    print(f"\nReusing {len(orders)} order-line rows already pulled for this scope (PEM101/Omni Channel, "
          f"Actual+MPS, 2024-01-01 onward). {orders['itemcode'].nunique()} of 128 items have at least one order.")

    order_counts = orders.groupby("itemcode").size()
    eligible = order_counts[order_counts >= MIN_ORDERS_FOR_ANALYSIS].index
    print(f"\n{len(eligible)} of {order_counts.shape[0]} items have at least {MIN_ORDERS_FOR_ANALYSIS} orders - "
          f"the minimum needed for a quantity-clustering pattern to mean anything. Items below this are reported "
          f"as insufficient evidence, not as 'no pattern'.")

    rows = []
    for item, grp in orders.groupby("itemcode"):
        qtys = grp["qty"]
        n = len(qtys)
        vc = qtys.value_counts()
        top3 = vc.head(3)
        mode_qty = top3.index[0]
        mode_share = 100 * top3.iloc[0] / n
        if n >= MIN_ORDERS_FOR_ANALYSIS:
            lot_L, lot_cov = best_multiple_candidate(qtys)
        else:
            lot_L, lot_cov = None, None
        rows.append({
            "itemcode": item, "n_orders": n,
            "top1_qty": mode_qty, "top1_share_pct": round(mode_share, 1),
            "top2_qty": top3.index[1] if len(top3) > 1 else None,
            "top2_n": int(top3.iloc[1]) if len(top3) > 1 else None,
            "top3_qty": top3.index[2] if len(top3) > 2 else None,
            "top3_n": int(top3.iloc[2]) if len(top3) > 2 else None,
            "min_qty": qtys.min(), "max_qty": qtys.max(), "median_qty": qtys.median(),
            "candidate_lot_size": lot_L, "lot_size_coverage_pct": lot_cov,
        })
    per_item = pd.DataFrame(rows).merge(item_type_map, left_on="itemcode", right_index=True, how="left")
    per_item.to_csv(os.path.join(SUMMARY_DIR, "part5_order_quantity_patterns_per_item.csv"), index=False)

    eligible_df = per_item[per_item["n_orders"] >= MIN_ORDERS_FOR_ANALYSIS].copy()

    strong_mode = eligible_df[eligible_df["top1_share_pct"] >= STRONG_MODE_SHARE_PCT]
    strong_multiple = eligible_df[eligible_df["candidate_lot_size"] > 1]
    either_strong = eligible_df[
        (eligible_df["top1_share_pct"] >= STRONG_MODE_SHARE_PCT) | (eligible_df["candidate_lot_size"] > 1)
    ]
    no_pattern = eligible_df[~eligible_df["itemcode"].isin(either_strong["itemcode"])]

    print(f"\nOf the {len(eligible_df)} items with enough orders to test:")
    print(f"  {len(strong_mode)} items ({100*len(strong_mode)/len(eligible_df):.1f}%) have a SINGLE dominant "
          f"quantity value accounting for at least {STRONG_MODE_SHARE_PCT:.0f}% of that item's own orders - "
          f"the clearest single-number lot-size signal.")
    print(f"  {len(strong_multiple)} items ({100*len(strong_multiple)/len(eligible_df):.1f}%) have at least "
          f"{STRONG_MULTIPLE_COVERAGE_PCT:.0f}% of orders landing on an exact multiple of some number greater "
          f"than 1 (a looser signal - consistent with a base unit/lot size even when the exact order size "
          f"varies).")
    print(f"  {len(either_strong)} items ({100*len(either_strong)/len(eligible_df):.1f}%) show EITHER signal.")
    print(f"  {len(no_pattern)} items ({100*len(no_pattern)/len(eligible_df):.1f}%) show NEITHER - order "
          f"quantities look closer to arbitrary/customer-driven than to a fixed lot size, from this evidence "
          f"alone.")

    print("\n10 items with the STRONGEST single-quantity dominance:")
    top_dominant = eligible_df.sort_values("top1_share_pct", ascending=False).head(10)
    print(top_dominant[["category", "type", "n_orders", "top1_qty", "top1_share_pct", "candidate_lot_size", "lot_size_coverage_pct"]].to_string(index=False))

    print("\n10 items with the STRONGEST recurring-multiple evidence (largest candidate lot size, "
          f"among items clearing {STRONG_MULTIPLE_COVERAGE_PCT:.0f}% coverage):")
    top_multiple = strong_multiple.sort_values("candidate_lot_size", ascending=False).head(10)
    print(top_multiple[["category", "type", "n_orders", "candidate_lot_size", "lot_size_coverage_pct", "top1_qty", "top1_share_pct"]].to_string(index=False))

    by_type = eligible_df.groupby("type").agg(
        n_items=("itemcode", "nunique"),
        pct_with_strong_signal=("itemcode", lambda s: 100 * s.isin(either_strong["itemcode"]).mean()),
    ).sort_values("pct_with_strong_signal", ascending=False)
    by_type.to_csv(os.path.join(SUMMARY_DIR, "part5_summary_by_type.csv"))
    print("\nShare of items with a strong lot-size signal, by product type:")
    print(by_type.round(1).to_string())

    print("\n--- PART 5 CONCLUSION ---")
    print(f"{len(either_strong)} of {len(eligible_df)} testable items ({100*len(either_strong)/len(eligible_df):.1f}%) "
          f"show observational evidence CONSISTENT WITH a lot size or minimum order quantity - either a single "
          f"quantity that recurs often, or a recurring multiple. This is suggestive, not proof: the data has no "
          f"field that states a lot size or MOQ directly, round quantities could equally reflect customer "
          f"ordering habits (e.g. buying in tens) rather than a supplier/production constraint, and no field "
          f"distinguishes the two explanations. The evidence is NOT strong enough to set an actual lot size or "
          f"MOQ value from data alone for any item - this must be confirmed by the business (production/"
          f"purchasing) per item, especially for the make-to-order side where a real MOQ is most likely to bind.")

    print("\nOutputs: output/summary/part5_order_quantity_patterns_per_item.csv, part5_summary_by_type.csv")
