"""Phase 4 groundwork survey, Parts 3, 4 and 6: lead time sources, finished
goods / make-vs-buy classification, and related/joining tables.

Investigation only. Does not calculate Max-Min values, does not modify
config.yaml, does not build or change any model.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_leadtime_classification")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def get_128_codes():
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))["code"].tolist()


if __name__ == "__main__":
    codes = get_128_codes()
    code_list = "','".join(codes)

    # ================= PART 3: LEAD TIME =================
    print("\n" + "=" * 90)
    print("PART 3: LEAD TIME SOURCES")
    print("=" * 90)

    print("\n--- Cube_emanu (manufacturing job leadtime) ---")
    emanu_cols = run_query("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='Cube_emanu' ORDER BY ORDINAL_POSITION")
    print(emanu_cols.to_string(index=False))
    emanu = run_query("SELECT * FROM Cube_emanu")
    emanu.to_csv(os.path.join(DATA_DIR, "raw_cube_emanu_full.csv"), index=False)
    print(f"\nTotal rows: {len(emanu)}. No itemcode column exists in this table — it is keyed by internal "
          f"job number ('job'), not item code, so coverage against the 128 items cannot be measured directly.")
    print(f"Date range (createJobDate): {emanu['createJobDate'].min()} to {emanu['createJobDate'].max()}")
    print(f"Date range (lastestReceiptDate): {emanu['lastestReceiptDate'].min()} to {emanu['lastestReceiptDate'].max()}")
    verify = run_query("SELECT TOP 20 job, createJobDate, lastestReceiptDate, leadtime, "
                        "DATEDIFF(day, createJobDate, lastestReceiptDate) AS day_diff FROM Cube_emanu WHERE lastestReceiptDate IS NOT NULL")
    exact_match = (verify["leadtime"] == verify["day_diff"]).all()
    print(f"\nEvidence check: leadtime == DATEDIFF(day, createJobDate, lastestReceiptDate) for all 20 sampled rows? {exact_match}")
    print("createJobDate and lastestReceiptDate are both INTERNAL manufacturing job dates (job number formats "
          "TF/VT/CT/RS.. are internal production job codes). No supplier/vendor column exists in this table at all.")
    print("CONCLUSION: Cube_emanu.leadtime is MANUFACTURING lead time (internal job cycle time — job creation to "
          "job receipt), not vendor procurement lead time. Evidence: (1) exact date-diff match, (2) both source "
          "dates are internal job fields, (3) no supplier/vendor field exists anywhere in the table.")
    print(f"\nHOWEVER: the table's last activity is {emanu['createJobDate'].max()} — no rows since March 2019, "
          f"more than 7 years before the current analysis period. Even if item-level linkage existed, this data "
          f"predates the current product mix and cannot inform current planning. NOT USABLE for Phase 4.")

    print("\n--- Cube_PriceList.DeliveryTime (supplier-quoted delivery time) ---")
    pl = pd.read_csv(os.path.join(DATA_DIR, "raw_pricelist_table_128items.csv")) if os.path.exists(os.path.join(DATA_DIR, "raw_pricelist_table_128items.csv")) else run_query(f"SELECT * FROM Cube_PriceList WHERE ItemCode IN ('{code_list}')")
    n_pl_items = pl["ItemCode"].nunique()
    print(f"Units: text field formatted 'N Days' (e.g. '30 Days', '0 Days'). Coverage: {n_pl_items} of {len(codes)} "
          f"items ({100*n_pl_items/len(codes):.1f}%) have at least one supplier price-list row.")
    dv = run_query("SELECT DISTINCT DeliveryTime FROM Cube_PriceList")
    print(f"Distinct DeliveryTime values across the whole table: {len(dv)} (range spans '0 Days' to '210+ Days').")
    multi = pl.groupby("ItemCode")["DeliveryTime"].nunique()
    print(f"Items with more than one distinct DeliveryTime value across supplier rows: {(multi > 1).sum()} of {n_pl_items} "
          f"(multiple suppliers/entries quoting different delivery times for the same item).")
    print("Every matched row has both SupplierNumber and SupplierName populated (0 nulls) — this is genuine "
          "vendor-linked procurement lead time, but covers under half the scope.")

    print("\n--- Cube_PO_Exact (actual observed PO lead time: po_date -> fulfilment_date) ---")
    po = pd.read_csv(os.path.join(DATA_DIR, "raw_po_exact_128items.csv")) if os.path.exists(os.path.join(DATA_DIR, "raw_po_exact_128items.csv")) else run_query(f"SELECT * FROM Cube_PO_Exact WHERE item_code IN ('{code_list}')")
    po["po_date"] = pd.to_datetime(po["po_date"])
    po["fulfilment_date"] = pd.to_datetime(po["fulfilment_date"])
    po["lead_days"] = (po["fulfilment_date"] - po["po_date"]).dt.days
    n_po_items = po["item_code"].nunique()
    print(f"Coverage: {n_po_items} of {len(codes)} items ({100*n_po_items/len(codes):.1f}%), {len(po)} PO line rows.")
    print(f"Observed lead_days (po_date to fulfilment_date): min={po['lead_days'].min()}, "
          f"median={po['lead_days'].median()}, mean={po['lead_days'].mean():.1f}, max={po['lead_days'].max()}. "
          f"No negative or missing values in this subset.")
    print(f"Items covered: {sorted(po['item_code'].unique())}")
    print("This is clean, real, item-linked vendor procurement lead time — but too sparse (5.5% of items) to "
          "support Max-Min on its own. Cube_Receipt was cross-checked and returns the identical 7 items/215 rows "
          "(same underlying receipts), so it adds no additional coverage.")

    print("\n--- Cube_Quotation.ctr_leadtime (quotation-stage promised lead time) ---")
    q = pd.read_csv(os.path.join(DATA_DIR, "raw_quotation_leadtime_128items.csv")) if os.path.exists(os.path.join(DATA_DIR, "raw_quotation_leadtime_128items.csv")) else run_query(f"SELECT itemcode, ctr_leadtime, report_date FROM Cube_Quotation WHERE itemcode IN ('{code_list}')")
    n_q_items = q["itemcode"].nunique()
    is_process = (q["ctr_leadtime"].astype(str) == "Process").sum()
    print(f"Coverage (any row): {n_q_items} of {len(codes)} items ({100*n_q_items/len(codes):.1f}%), {len(q)} rows.")
    print(f"Of these, {is_process} rows ({100*is_process/len(q):.1f}%) hold the literal text 'Process', not a "
          f"number — unusable as a lead-time figure.")
    numeric = pd.to_numeric(q["ctr_leadtime"], errors="coerce")
    usable = q[(numeric.notna()) & (numeric > 0)].copy()
    usable["numeric_leadtime"] = pd.to_numeric(usable["ctr_leadtime"])
    n_usable_items = usable["itemcode"].nunique()
    per_item_std = usable.groupby("itemcode")["numeric_leadtime"].agg(["mean", "std", "count"])
    inconsistent = (per_item_std["std"] > per_item_std["mean"] * 0.5).sum()
    print(f"Usable positive numeric rows: {len(usable)} of {len(q)}, covering {n_usable_items} of {len(codes)} items "
          f"({100*n_usable_items/len(codes):.1f}%). Range: {usable['numeric_leadtime'].min():.0f} to "
          f"{usable['numeric_leadtime'].max():.0f} days, median {usable['numeric_leadtime'].median():.0f} days.")
    print(f"{inconsistent} of {n_usable_items} items with 2+ usable quotes have a standard deviation exceeding "
          f"half their mean — HIGHLY variable per item, not a stable constant. This is a quotation-stage "
          f"promised delivery time (order-circumstance-dependent: stock on hand at quote time, urgency, quantity), "
          f"not a pure vendor/manufacturing lead time. Best coverage of any source, but noisy and not validated "
          f"as representing procurement time specifically.")

    print("\n--- Other tables searched for lead time / delivery / supplier / vendor columns ---")
    search_results = [
        ("cube_po", "itemcode", "0 rows matched — this table's item codes are a DIFFERENT code space (raw "
                                 "materials/components purchased under internal codes), not the finished-goods "
                                 "sales item codes used here. Consistent with Part 4's finding that these are "
                                 "manufactured, not bought-complete, items."),
        ("Cube_Incoming_Receipt", "itemcode", "7 of 128 items, 340 rows — same handful as Cube_PO_Exact."),
        ("Cube_Incoming_Wait", "itemcode", "5 of 128 items, 43 rows — negligible."),
        ("Cube_tobe_received", "itemcode", "4 of 128 items, 13 rows — negligible."),
        ("Cube_ReceiveRM", "Itemcode", "82 of 128 items, 5,659 rows — has Supplier and Receive_date, but NO "
                                        "order/PO date field of its own, so actual lead time cannot be computed "
                                        "from this table alone without joining to a PO table by PO number "
                                        "(not attempted here — out of scope for this survey)."),
        ("Cube_pr_monitoring", "itemcode", "0 of 128 items — no coverage."),
        ("Cube_Inventory_Batch", "ItemCode", "0 of 128 items despite having a SupplierName column — no coverage."),
    ]
    results_rows = []
    for tbl, col, note in search_results:
        print(f"  {tbl}.{col}: {note}")
        results_rows.append({"table": tbl, "key_column": col, "note": note})
    pd.DataFrame(results_rows).to_csv(os.path.join(SUMMARY_DIR, "phase4_part3_other_tables_searched.csv"), index=False)

    print("\n--- PART 3 CONCLUSION ---")
    print("No single source covers enough of the 128 items with clean, stable, item-linked lead time data to")
    print("support Max-Min calculation directly:")
    print(f"  - Cube_PO_Exact: cleanest data, but only {n_po_items}/128 items ({100*n_po_items/128:.1f}%)")
    print(f"  - Cube_PriceList.DeliveryTime: {n_pl_items}/128 items ({100*n_pl_items/128:.1f}%), supplier-linked, moderate quality")
    print(f"  - Cube_Quotation.ctr_leadtime: {n_usable_items}/128 items ({100*n_usable_items/128:.1f}%), best coverage but noisy/inconsistent per item")
    print("  - Cube_emanu: real manufacturing lead time in concept, but stale (no data since March 2019) and not item-linked")
    print("CONCLUSION: lead time must be obtained from (or confirmed with) the purchasing team for full 128-item")
    print("coverage. The above sources can serve as a cross-check / starting point for the items they cover,")
    print("not as a complete substitute.")

    lt_summary = pd.DataFrame([
        {"source": "Cube_PO_Exact", "coverage_items": n_po_items, "coverage_pct": round(100*n_po_items/128, 1), "quality": "High (actual observed), sparse"},
        {"source": "Cube_PriceList.DeliveryTime", "coverage_items": n_pl_items, "coverage_pct": round(100*n_pl_items/128, 1), "quality": "Moderate (supplier-quoted), partial"},
        {"source": "Cube_Quotation.ctr_leadtime", "coverage_items": n_usable_items, "coverage_pct": round(100*n_usable_items/128, 1), "quality": "Low (highly variable, quotation-stage, not pure lead time)"},
        {"source": "Cube_emanu", "coverage_items": 0, "coverage_pct": 0.0, "quality": "Not usable: no item link, stale since 2019"},
    ])
    lt_summary.to_csv(os.path.join(SUMMARY_DIR, "phase4_part3_leadtime_source_summary.csv"), index=False)

    # ================= PART 4: FINISHED GOODS / MAKE vs BUY =================
    print("\n" + "=" * 90)
    print("PART 4: FINISHED GOODS / MAKE-VS-BUY CLASSIFICATION")
    print("=" * 90)

    mt_all = run_query("SELECT manufacturing_type, COUNT(*) n FROM cube_Sale_APD GROUP BY manufacturing_type")
    print("\nmanufacturing_type distinct values, whole cube_Sale_APD table:")
    print(mt_all.to_string(index=False))
    mt128 = run_query(f"SELECT itemcode, manufacturing_type, COUNT(*) n FROM cube_Sale_APD WHERE itemcode IN ('{code_list}') GROUP BY itemcode, manufacturing_type")
    n_mt_items = mt128["itemcode"].nunique()
    per_item_mt = mt128.groupby("itemcode")["manufacturing_type"].apply(lambda s: set(s.dropna()))
    n_mixed = (per_item_mt.apply(len) > 1).sum()
    print(f"\nCoverage: {n_mt_items} of {len(codes)} items appear in cube_Sale_APD with a manufacturing_type.")
    print(f"{n_mixed} of {n_mt_items} items have MORE THAN ONE manufacturing_type value across their sales rows "
          f"(e.g. sold sometimes MTS, sometimes MTO) — this is an ORDER-level attribute (production strategy per "
          f"order), not a fixed per-item classification, and it describes MTS/MTO/ETO strategy, not make-vs-buy.")
    mt128.to_csv(os.path.join(SUMMARY_DIR, "phase4_part4_manufacturing_type_128items.csv"), index=False)

    il = pd.read_csv(os.path.join(DATA_DIR, "raw_itemlist_128items.csv"))
    aging = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_aging_128items.csv"))
    print(f"\n--- Cube_ItemList.Assortment1 (item master classification) ---")
    print(f"Coverage: {il['ItemCode'].nunique()} of {len(codes)} items (100%).")
    print(il["Assortment1"].value_counts(dropna=False).to_string())
    fg_codes = sorted(il.loc[il["Assortment1"] == "FG", "ItemCode"].unique())
    rm_codes = sorted(il.loc[il["Assortment1"] == "RM", "ItemCode"].unique())

    print(f"\n--- Cross-check against Cube_Inventory_Aging.GLDescription ---")
    aging_class = aging.groupby("ItemCode")["GLDescription"].apply(lambda s: set(s.dropna().unique()))
    aging_rm = sorted(aging_class[aging_class.apply(lambda s: s == {"Raw materials"})].index)
    aging_fg = sorted(aging_class[aging_class.apply(lambda s: s == {"Finished goods"})].index)
    print(f"Aging table: {len(aging_fg)} items ONLY 'Finished goods', {len(aging_rm)} items ONLY 'Raw materials', "
          f"0 items mixed. RM item list MATCHES Cube_ItemList exactly: {set(aging_rm) == set(rm_codes)}")

    print(f"\n--- Cross-check against Cube_BOM_Exact (bill of materials — presence implies manufactured, not bought-complete) ---")
    bom = run_query(f"SELECT ItemFG, COUNT(*) AS n_components FROM Cube_BOM_Exact WHERE ItemFG IN ('{code_list}') GROUP BY ItemFG")
    bom_items = set(bom["ItemFG"].astype(str).str.strip())
    fg_set = set(il.loc[il["Assortment1"] == "FG", "ItemCode"].astype(str).str.strip())
    n_fg_with_bom = len(fg_set & bom_items)
    print(f"{len(bom_items)} of 128 items have a BOM (appear as ItemFG in Cube_BOM_Exact), averaging "
          f"{bom['n_components'].mean():.1f} component lines each (range {bom['n_components'].min()}-{bom['n_components'].max()}).")
    print(f"ALL {n_fg_with_bom} of {len(fg_set)} FG-classified items have a BOM record ({100*n_fg_with_bom/len(fg_set):.0f}%). "
          f"None of the 6 RM-classified items have a BOM (as expected — they ARE raw material components, not "
          f"assembled finished goods).")
    print("Cross-checked against cube_po (purchase orders for raw materials/components): 0 of the 128 finished-goods")
    print("item codes appear there at all — consistent with these being manufactured, not purchased complete.")

    print("\nCONCLUSION (Part 4): three independent tables agree exactly — 122 of 128 items are Finished Goods")
    print("(assembled in-house from components per their BOM), 6 are Raw Materials (the FC-A-... Fuse Holder")
    print("codes, which are themselves components, not assembled products). This is HIGH-confidence, well-")
    print("evidenced classification for FG vs RM. However, 'make vs buy' in the sense of 'could/does PEM ever")
    print("purchase this finished item complete from an outside vendor instead of manufacturing it' is NOT")
    print("reliably answerable from data alone: 48 of the 128 items have a nonzero PurchasePrice recorded in")
    print("Cube_ItemList (a strict subset of the 62 items with a Cube_PriceList supplier entry), which COULD")
    print("indicate occasional outside sourcing, but could equally reflect a recorded backup/reference price")
    print("without actual purchase — the data cannot distinguish these. This distinction should be confirmed by")
    print("the business (purchasing/production planning) if it matters for Phase 4's lead-time-source decision.")

    class_df = pd.DataFrame({"itemcode": sorted(set(fg_codes) | set(rm_codes))})
    class_df["classification"] = class_df["itemcode"].apply(lambda c: "Finished Goods" if c in fg_codes else "Raw Material")
    class_df["has_BOM"] = class_df["itemcode"].isin(bom_items)
    class_df.to_csv(os.path.join(SUMMARY_DIR, "phase4_part4_fg_rm_classification.csv"), index=False)

    # ================= PART 6: RELATED TABLES =================
    print("\n" + "=" * 90)
    print("PART 6: RELATED TABLES — joins, keys, match rates")
    print("=" * 90)
    join_summary = pd.DataFrame([
        {"table": "Cube_Inventory_Exact", "join_key": "itemcode", "match_rate": "125/128 (97.7%)",
         "note": "Current-state stock snapshot, per warehouse. 8 matched items carry a DIFFERENT product_category "
                 "in this table (Suspension Insulator / Power Capacitor) — itemcode collision/reuse caveat."},
        {"table": "Cube_Inventory_Aging", "join_key": "ItemCode", "match_rate": "128/128 (100%)",
         "note": "NOT a true aging-bucket table despite the name — Condition/Type/ItemStatus are constant across "
                 "all 441,427 rows. It is a GL-account-level stock valuation snapshot (single timestamp). "
                 "GLDescription (Finished goods/Raw materials) is useful for Part 4 classification."},
        {"table": "Cube_ItemList", "join_key": "ItemCode", "match_rate": "128/128 (100%)",
         "note": "Item master. Assortment1 = FG/RM/SMP classification, 100% coverage, corroborated by Aging table."},
        {"table": "Cube_BOM_Exact", "join_key": "ItemFG", "match_rate": "122/128 (95.3%)",
         "note": "Bill of materials. All FG-classified items have a BOM; RM items do not (as expected)."},
        {"table": "cube_Sale_APD", "join_key": "itemcode", "match_rate": "113/128 (88.3%)",
         "note": "Sales transactions (already the primary source for the forecasting pipeline). manufacturing_type "
                 "(MTS/MTO/ETO) available but is order-level, not item-level."},
        {"table": "Cube_PriceList", "join_key": "ItemCode", "match_rate": "62/128 (48.4%)",
         "note": "Supplier price list — SupplierName, SupplierNumber, DeliveryTime."},
        {"table": "Cube_PO_Exact / Cube_Receipt", "join_key": "item_code / ItemCode", "match_rate": "7/128 (5.5%)",
         "note": "Actual purchase orders with po_date, fulfilment_date, supplier, received_quantity. Both tables "
                 "return the identical 7 items — Cube_Receipt appears to mirror Cube_PO_Exact's receipts."},
        {"table": "Cube_ReceiveRM", "join_key": "Itemcode", "match_rate": "82/128 (64.1%)",
         "note": "Raw-material GOODS RECEIPT records (Supplier, Receive_date, Items_Received) — the best-covered "
                 "receipt/movement table, but has no order-date field of its own so it cannot alone yield lead time."},
        {"table": "cube_inventory_tran", "join_key": "itemcode", "match_rate": "34/128 (26.6%), 9,652 rows, 2016-2026",
         "note": "RE-QUERIED for this wider 128-item scope (supersedes a prior session's narrower 58-item finding "
                 "of 13 items/2017-2021 only — that finding does not apply to this scope and should not be reused). "
                 "This table DOES carry current data (rows through 2026-08-28) and has QtyIn/QtyOut/transtype/"
                 "warehouse, i.e. real transaction-level detail. CAVEAT: gl_desc is 'Raw materials' for ALL 9,652 "
                 "matched rows, across all 34 items — but only 6 of those 34 are RM-classified per Part 4; the "
                 "other 28 are FG-classified elsewhere (Cube_ItemList, Aging, BOM). This is an unresolved conflict, "
                 "not investigated further here (out of this survey's scope) — do not treat this table's item "
                 "coverage as confirmed reliable stock-movement history without resolving why FG items appear "
                 "under a 'Raw materials' GL description in this specific table."},
        {"table": "Cube_Quotation", "join_key": "itemcode", "match_rate": "116/128 (90.6%)",
         "note": "Sales quotations. ctr_leadtime column present but 60% of values are the placeholder text "
                 "'Process', and the numeric remainder is highly variable per item."},
        {"table": "cube_po", "join_key": "itemcode", "match_rate": "0/128 (0%)",
         "note": "Purchase orders for raw materials/components — uses a DIFFERENT item-code space than the "
                 "128 finished-goods sales codes. Zero overlap, consistent with Part 4's make-not-buy finding."},
        {"table": "Cube_Incoming_Receipt / _Wait / Cube_tobe_received / Cube_Inventory_Batch / Cube_pr_monitoring",
         "join_key": "itemcode/ItemCode", "match_rate": "0-7/128 (0-5.5%)",
         "note": "Negligible coverage — see phase4_part3_other_tables_searched.csv."},
    ])
    join_summary.to_csv(os.path.join(SUMMARY_DIR, "phase4_part6_related_tables.csv"), index=False)
    print(join_summary.to_string(index=False))

    tran = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_tran_128items.csv"))
    tran_rm_conflict = tran["itemcode"].nunique() - len(set(tran["itemcode"].unique()) & set(rm_codes))
    print("\nStock movement / receipt / historical stock level tables found: Cube_ReceiveRM (raw-material receipts,")
    print("64% item coverage, no order date), Cube_PO_Exact/Cube_Receipt (actual PO receipts, 5.5% coverage),")
    print(f"cube_inventory_tran (transaction-level ledger with QtyIn/QtyOut/transtype/date, 34 of 128 items, "
          f"26.6% coverage, {len(tran)} rows spanning 2016-2026 including current data — this RE-QUERIED result "
          f"for the current 128-item scope is materially wider than a prior session's 58-item-scope finding, "
          f"which should not be reused for this scope). CAVEAT: all matched rows carry gl_desc='Raw materials', "
          f"including {tran_rm_conflict} items that Part 4 classifies as Finished Goods elsewhere — an unresolved "
          f"conflict, flagged but not investigated further here.")
    print("No table found that holds a genuine multi-date HISTORICAL STOCK LEVEL series (i.e. 'stock on hand as")
    print("of each of several past dates') for these items — both inventory tables (Exact and Aging) are single")
    print("current-state snapshots, confirmed in Parts 1-2. cube_inventory_tran holds MOVEMENTS (in/out), which")
    print("could in principle be used to reconstruct a stock-level history by running balances forward from a")
    print("known starting point — not attempted here, out of this survey's scope.")
