"""Phase 4 groundwork survey, Part 7: readiness assessment. Consolidates
Parts 1-6 into a single usable/insufficient/missing table with a confidence
level per conclusion. Prints the console summary. Writes to output/summary/.

Investigation only. No modeling, no config.yaml changes.
"""
import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

readiness = pd.DataFrame([
    {"area": "Current stock levels (Cube_Inventory_Exact)", "status": "USABLE (with caveats)", "confidence": "HIGH",
     "detail": "125/128 items covered, single current-state snapshot (not a time series). Minimum/maximum are "
               "set per warehouse, not per item — 81 of 119 multi-warehouse items have inconsistent values across "
               "warehouses, so which warehouse(s) count for Max-Min planning needs a business decision. 8 items "
               "carry a conflicting product_category in this table (itemcode collision caveat)."},
    {"area": "Existing min/max settings vs. current demand", "status": "USABLE for a staleness check", "confidence": "MEDIUM",
     "detail": "82/128 items have a nonzero min/max set. Expressed as months of recent sales cover, values range "
               "from <1 month to 1700+ months for thin-moving items — wide variation suggests some settings are "
               "stale rather than actively maintained. 7 items have a nonzero min/max but zero recent sales."},
    {"area": "Slow-moving / aging stock (Cube_Inventory_Aging)", "status": "MISSING — table does not measure this", "confidence": "HIGH",
     "detail": "Despite its name, this table has NO age-bucket structure — Condition/Type/ItemStatus are constant "
               "across all 441K rows. It is a GL-account valuation snapshot, single timestamp. It cannot answer "
               "'how long has this stock been held' as-is."},
    {"area": "Manufacturing lead time", "status": "MISSING (stale + no item link)", "confidence": "HIGH",
     "detail": "Cube_emanu.leadtime is genuine manufacturing cycle time (evidenced), but has no itemcode column "
               "and no data since March 2019 — unusable for current planning."},
    {"area": "Vendor procurement lead time", "status": "INSUFFICIENT — partial, fragmented", "confidence": "HIGH",
     "detail": "Best clean source (Cube_PO_Exact, actual observed) covers only 7/128 items (5.5%). "
               "Cube_PriceList.DeliveryTime covers 62/128 (48.4%) with genuine supplier linkage. "
               "Cube_Quotation.ctr_leadtime covers 100/128 (78.1%) numerically but is highly variable per item "
               "and represents a quoted delivery promise, not a validated procurement lead time."},
    {"area": "Finished goods vs. raw material classification", "status": "USABLE", "confidence": "HIGH",
     "detail": "122/128 Finished Goods, 6/128 Raw Material — confirmed by 3 independent tables in exact agreement "
               "(Cube_ItemList.Assortment1, Cube_Inventory_Aging.GLDescription, Cube_BOM_Exact presence)."},
    {"area": "Make vs. buy (manufactured in-house vs. purchased complete)", "status": "USABLE for FG-vs-RM only; make/buy itself unresolved", "confidence": "MEDIUM",
     "detail": "All 117 FG items have a BOM (strong evidence they are assembled, not bought complete) and none "
               "appear in the raw-material PO table (cube_po) under their own code. But whether any of them are "
               "ALSO occasionally purchased complete as a backup source is not distinguishable from data alone "
               "(48 items have a nonzero PurchasePrice, ambiguous meaning) — confirm with purchasing/production."},
    {"area": "Seasonal demand pattern", "status": "INSUFFICIENT — not enough years", "confidence": "HIGH (on the limitation itself)",
     "detail": "Only 2 complete years (2024, 2025) plus one partial (2026 through August). June looks high in "
               "both categories across all 3 years; a few other months disagree year to year. 2 data points "
               "cannot statistically distinguish a real seasonal cycle from coincidence — no seasonal pattern "
               "can be confirmed from this data."},
    {"area": "Historical stock-level time series", "status": "MISSING", "confidence": "HIGH",
     "detail": "No table holds 'stock on hand as of several past dates' directly. cube_inventory_tran holds "
               "movements (QtyIn/QtyOut) for 34/128 items (26.6%) back to 2016 including current data, from which "
               "a stock history COULD in principle be reconstructed — not attempted here, and this table has an "
               "unresolved GL-classification conflict (see Part 6) that should be resolved first."},
    {"area": "Stock movement / receipts (component level)", "status": "PARTIAL", "confidence": "MEDIUM",
     "detail": "Cube_ReceiveRM covers 82/128 items (64.1%) with Supplier and Receive_date, but no order-date "
               "field of its own, so it cannot yield lead time alone. Would need a join to a PO table by PO "
               "number to be useful for lead-time reconstruction — not attempted here."},
])
readiness.to_csv(os.path.join(SUMMARY_DIR, "phase4_part7_readiness_assessment.csv"), index=False)

unresolved = [
    "Which warehouse(s) should count toward each item's Max-Min policy — items are stocked across up to 20 "
    "warehouses with genuinely different min/max settings per warehouse; no data-only answer exists.",
    "The mechanism behind cube_inventory_tran's conflicting GL classification (28 of its 34 covered items are "
    "'Raw materials' there but 'Finished Goods' everywhere else) — not investigated, flagged only.",
    "Whether any of the 128 items are ever purchased complete from an outside vendor as an alternative to "
    "in-house manufacture (make vs. buy in the strict sense) — the data is suggestive (PurchasePrice populated "
    "for 48 items) but not conclusive.",
    "Whether the 8 items showing a conflicting product_category in Cube_Inventory_Exact (Suspension Insulator / "
    "Power Capacitor) represent genuine itemcode reuse/collision or a data entry issue — same open class of "
    "problem as the earlier pricelist-vs-database Surge Arrester voltage-tier disagreement (STATUS.md).",
    "Whether a real seasonal pattern exists at all — explicitly not answerable with 2 complete years of data.",
]

if __name__ == "__main__":
    print("\n" + "#" * 92)
    print("# PHASE 4 GROUNDWORK SURVEY — FINAL READINESS ASSESSMENT")
    print("#" * 92)
    print("\nScope: 128 item codes, Product Cate. = Fuse or Surge Arrester (established in the prior task).")
    print("This is a SURVEY only — no min/max values calculated, no model built, config.yaml not touched.\n")

    print(readiness.to_string(index=False))

    print("\n" + "=" * 92)
    print("READY NOW (usable as-is or with a stated caveat):")
    print("=" * 92)
    print("- Current stock snapshot (Cube_Inventory_Exact), with the per-warehouse caveat — HIGH confidence.")
    print("- Existing min/max settings and a staleness check against recent sales — MEDIUM confidence.")
    print("- Finished goods vs. raw material classification (122 FG / 6 RM) — HIGH confidence, triple-corroborated.")

    print("\n" + "=" * 92)
    print("EXISTS BUT INSUFFICIENT (partial coverage or quality issues, usable only as a cross-check):")
    print("=" * 92)
    print("- Vendor procurement lead time: best clean source only 5.5% coverage; best-coverage source (78.1%) is")
    print("  noisy quotation data, not validated procurement lead time.")
    print("- Make vs. buy distinction beyond FG/RM — suggestive signals only, not conclusive (MEDIUM confidence).")
    print("- Seasonal pattern: numbers reported, but 2 complete years cannot confirm a real cycle (by design, not")
    print("  a gap — this cannot be fixed except by waiting for more history).")
    print("- Component-level receipts (Cube_ReceiveRM, 64.1%) — no order date, cannot alone give lead time.")

    print("\n" + "=" * 92)
    print("MISSING ENTIRELY (must be requested from purchasing/warehouse teams):")
    print("=" * 92)
    print("- Manufacturing lead time for current production (Cube_emanu is stale, stopped March 2019).")
    print("- A genuine aging/slow-moving-stock measure — Cube_Inventory_Aging does not contain age buckets")
    print("  despite its name.")
    print("- A historical stock-LEVEL time series (only current snapshots exist; movements exist for a minority")
    print("  of items and would need reconstruction work, not attempted here).")
    print("- Full-coverage vendor lead time for all 128 items — recommend requesting this directly from")
    print("  purchasing rather than assembling it from fragments that together still miss roughly half the scope.")

    print("\n" + "=" * 92)
    print("UNRESOLVED (listed separately per instruction, not folded into the above):")
    print("=" * 92)
    for u in unresolved:
        print(f"- {u}")

    print("\nAll findings written to output/summary/ (files prefixed phase4_part1_ through phase4_part7_).")
    print("config/config.yaml was NOT modified. No model was built or changed.")
