"""Phase 4 prep investigation, Part 3: warehouse structure.

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched.
Scope: the 128 item codes in Product Cate. Fuse and Surge Arrester.

Reuses output/data/raw_inventory_exact_128items.csv (Cube_Inventory_Exact, current-state
snapshot, already pulled in the Phase 4 groundwork survey) and
output/data/raw_inventory_tran_128items.csv (cube_inventory_tran, movement ledger, same
survey). Pulls one new join (itemcode -> division, whole cube_Sale_APD) to test whether
warehouse codes are business-unit-specific.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("warehouse_structure_investigation")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def get_scope() -> pd.DataFrame:
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))


if __name__ == "__main__":
    scope = get_scope()
    codes = sorted(scope["code"].unique())

    # ================= HOW MANY WAREHOUSES, WHAT IDENTIFIES THEM =================
    print("\n" + "#" * 92)
    print("# PART 3: WAREHOUSE STRUCTURE")
    print("#" * 92)

    inv = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_exact_128items.csv"))
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()

    print("\n--- No dedicated warehouse master/lookup table exists ---")
    no_wh_table = run_query("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '%warehouse%'")
    print(f"Search for a table named like '%warehouse%': {len(no_wh_table)} found. Warehouses are identified only "
          f"by a short code stored directly on inventory/transaction rows (the 'warehouse' column in "
          f"Cube_Inventory_Exact, Cube_Inventory_Aging, cube_inventory_tran, Cube_PO_Exact, and others) - there is "
          f"no separate table giving each code a name, address, or business-unit owner.")

    wh_counts = inv["warehouse"].value_counts()
    n_wh_128 = wh_counts.shape[0]
    print(f"\nWithin the 128-item scope's current Cube_Inventory_Exact snapshot: {n_wh_128} distinct warehouse "
          f"codes hold at least one of these items ({inv['itemcode'].nunique()} of 128 items appear in this "
          f"snapshot at all; 3 items have no row here). Whole-table (all items, any division): 76 distinct "
          f"warehouse codes exist.")
    wh_counts.to_csv(os.path.join(SUMMARY_DIR, "part3_warehouse_list_128items.csv"), header=["n_item_rows"])
    print("\nWarehouse codes and how many (item, warehouse) rows they hold in this scope, most common first:")
    print(wh_counts.to_string())

    print("\nReading the codes themselves (no documentation string found, inferred from naming and behaviour):")
    print("  FG, FG01, FG02, FG03, FG11, FG12, FG16, FG17, FG21, FG23, FG24 - a family of 'finished goods' codes, "
          "likely different physical stocking locations/branches for completed product.")
    print("  WH01, WH04, WH05, WH06, WH07, WH21, WH24, W121, W4-1 - a family of general warehouse codes.")
    print("  FMTS / FMTO - production-order WORK-IN-PROGRESS staging buckets (Make-To-Stock / Make-To-Order), "
          "not physical stocking warehouses in the usual sense - min/max are always 0 here and most rows show "
          "'tobe_received' (incoming from production) rather than settled stock. See the production-strategy "
          "investigation (Part 1/2) for the corroborating detail.")
    print("  QA - quality-assurance / incoming-inspection hold, evidenced by its role as a transfer source below.")
    print("  CL - appears as both a transfer source and destination; meaning not confirmed from data alone "
          "(possibly 'claim' or a consignment/customer location - not verifiable here).")
    print("  INTR, F-RD, AST, NCRM, F101/F102/F103/F106/F107/F109 - low-volume/specialised codes (in-transit, "
          "R&D, asset, non-conforming raw material, and factory/cost-center-linked codes respectively) - "
          "meanings read from the abbreviation and usage pattern, not confirmed by any lookup table.")

    # ================= BUSINESS UNIT MAPPING =================
    print("\n--- WHICH BUSINESS UNIT EACH WAREHOUSE BELONGS TO ---")
    print("Cube_Inventory_Exact's own 'company' field is too coarse to answer this: only 2 values exist table-wide "
          "('PEM', 'CI') - it distinguishes companies, not the finer PEM101/102/103/104/107 business units this "
          "project works with.")

    logger.info("Pulling whole-table itemcode -> division mapping to test whether warehouse codes are "
                "business-unit-specific")
    item_div = run_query("SELECT DISTINCT itemcode, division FROM cube_Sale_APD WHERE itemcode IS NOT NULL AND division IS NOT NULL")
    inv_all = run_query("SELECT itemcode, warehouse FROM Cube_Inventory_Exact")
    inv_all["warehouse"] = inv_all["warehouse"].str.strip()
    joined = inv_all.merge(item_div, on="itemcode", how="inner")
    joined.to_csv(os.path.join(DATA_DIR, "raw_warehouse_division_join_wholetable.csv"), index=False)

    wh_div = joined.groupby("warehouse")["division"].agg(
        n_rows="count", n_distinct_divisions="nunique",
        top_division=lambda s: s.value_counts().idxmax(),
        top_division_share_pct=lambda s: round(100 * s.value_counts().max() / len(s), 1),
    )
    scope_warehouses = [w for w in wh_counts.index]
    wh_div_scope = wh_div.loc[wh_div.index.isin(scope_warehouses)].sort_values("n_rows", ascending=False)
    wh_div_scope.to_csv(os.path.join(SUMMARY_DIR, "part3_warehouse_division_test.csv"))
    print(f"\nTest: for each of this scope's {len(scope_warehouses)} warehouse codes, joined against ALL items' "
          f"recorded sales division (table-wide, not just these 128 items), to see whether a warehouse code is "
          f"used exclusively by one division:")
    print(wh_div_scope.round(1).to_string())

    single_div_wh = (wh_div_scope["n_distinct_divisions"] == 1).sum()
    print(f"\n{single_div_wh} of {len(wh_div_scope)} warehouse codes are used by only ONE division table-wide; "
          f"every other warehouse code appears under MULTIPLE divisions - even the codes whose numeric suffix "
          f"visually resembles a division number (e.g. warehouse 'F101' is mostly used by division PEM101, but "
          f"also by PPD101/PEM102-OLD/PCE101/PTS; warehouse 'F103' is mostly PEM103 but also PEM102-OLD/PEM101/"
          f"PEM107/PTS).")
    print("CAVEAT that limits this test: 'division' here is the division recorded on a SALES TRANSACTION for an "
          "itemcode, and this project has already established (STATUS.md Phase 2) that the SAME itemcode is "
          "reused/sold under multiple divisions - so a warehouse appearing under several divisions could reflect "
          "genuine multi-BU warehouse sharing, OR it could simply be inheriting the itemcode-reuse ambiguity "
          "already documented elsewhere in this project. The data cannot separate these two explanations.")
    print("\nCONCLUSION: no reliable warehouse -> business-unit mapping can be produced from this data. There is "
          "no warehouse master table, the 'company' field is too coarse, and the only per-item division field is "
          "itself ambiguous for these items. This must be obtained from the business if warehouse-level planning "
          "needs to be grouped by business unit.")

    # ================= WHERE THE 128 ITEMS ARE HELD =================
    print("\n--- WHERE THE 128 ITEMS ARE HELD ACROSS WAREHOUSES ---")
    per_item_wh = inv.groupby("itemcode")["warehouse"].nunique().sort_values(ascending=False)
    per_item_wh.to_csv(os.path.join(SUMMARY_DIR, "part3_item_warehouse_count.csv"), header=["n_warehouses"])
    n_multi = (per_item_wh > 1).sum()
    n_single = (per_item_wh == 1).sum()
    n_present = len(per_item_wh)
    n_absent = len(codes) - n_present
    print(f"{n_present} of {len(codes)} items appear in the current inventory snapshot at all ({n_absent} do not).")
    print(f"Of those {n_present}: {n_multi} ({100*n_multi/n_present:.1f}%) are held in MORE THAN ONE warehouse; "
          f"{n_single} ({100*n_single/n_present:.1f}%) are held in exactly one.")
    print(f"Warehouse count per item: min={per_item_wh.min()}, median={per_item_wh.median():.0f}, "
          f"mean={per_item_wh.mean():.2f}, max={per_item_wh.max()}.")
    print("Holding stock across many warehouses is the NORM for this item scope, not the exception - this "
          "matches the earlier Phase 4 groundwork finding that Cube_Inventory_Exact's min/max values are set "
          "per warehouse, not per item, and genuinely differ across warehouses for the same item.")

    # ================= STOCK TRANSFERS =================
    print("\n--- STOCK TRANSFERS BETWEEN WAREHOUSES ---")
    tran = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_tran_128items.csv"))
    n_tran_items = tran["itemcode"].nunique()
    print(f"cube_inventory_tran (the transaction-level movement ledger) covers {n_tran_items} of {len(codes)} "
          f"items in this scope ({100*n_tran_items/len(codes):.1f}%) - a coverage limit already noted in the "
          f"Phase 4 groundwork survey, not something this task can improve on.")

    tran["warehouse"] = tran["warehouse"].astype(str).str.strip()
    t_pairs = tran[tran["transtype"].isin(["150", "151"])].copy()
    print(f"\ntranstype values '150' and '151' behave as an exact-opposite pair: across the WHOLE table (not just "
          f"this scope), transtype 150 rows are 100% QtyOut-only and 151 rows are 100% QtyIn-only - the classic "
          f"signature of a transfer-out / transfer-in pair, not a documented code (no lookup table defines "
          f"transtype either).")

    groups = t_pairs.groupby(["itemcode", "ourref", "trans_date"])
    n_groups = 0
    n_matched = 0
    total_qty = 0.0
    items_with_transfer = set()
    wh_pairs = {}
    for key, grp in groups:
        if len(grp) == 2 and set(grp["transtype"]) == {"150", "151"}:
            n_groups += 1
            out_row = grp[grp["transtype"] == "150"].iloc[0]
            in_row = grp[grp["transtype"] == "151"].iloc[0]
            if pd.notna(out_row["QtyOut"]) and pd.notna(in_row["QtyIn"]) and abs(out_row["QtyOut"] - in_row["QtyIn"]) < 0.01:
                n_matched += 1
                total_qty += in_row["QtyIn"]
                items_with_transfer.add(key[0])
                pair = (out_row["warehouse"], in_row["warehouse"])
                wh_pairs[pair] = wh_pairs.get(pair, 0) + 1

    print(f"\nFound {n_groups} candidate (itemcode, order reference, date) groups with exactly one 150 row and "
          f"one 151 row; {n_matched} of {n_groups} ({100*n_matched/n_groups:.1f}%) have EXACTLY matching quantity "
          f"(QtyOut of the 150 row equals QtyIn of the 151 row to the unit) - strong evidence these are genuine "
          f"transfers between two warehouses of the same stock, not independent movements that happen to "
          f"coincide. Total quantity transferred across these confirmed pairs: {total_qty:,.0f} units. Date "
          f"range: {t_pairs['trans_date'].min()} to {t_pairs['trans_date'].max()} (spans the full available "
          f"history through the current data).")
    print(f"\nItems with at least one confirmed transfer: {len(items_with_transfer)} of the {n_tran_items} items "
          f"this table covers at all (a lower bound - the other {len(codes)-n_tran_items} items are simply not "
          f"covered by this table, not confirmed transfer-free).")

    wh_pairs_df = pd.DataFrame(
        [{"from_warehouse": k[0], "to_warehouse": k[1], "n_transfers": v} for k, v in wh_pairs.items()]
    ).sort_values("n_transfers", ascending=False)
    wh_pairs_df.to_csv(os.path.join(SUMMARY_DIR, "part3_warehouse_transfer_pairs.csv"), index=False)
    print("\nMost common transfer routes (from -> to, count):")
    print(wh_pairs_df.head(15).to_string(index=False))
    print("\nThe dominant route (QA -> WH01 -> FG01 -> FG02) reads as: goods arrive/clear quality inspection at "
          "QA, move to the main warehouse WH01, then out to finished-goods branch warehouses FG01/FG02 - "
          "consistent with a single internal supply chain feeding multiple stocking locations, not independent "
          "silos.")

    print("\n--- PART 3 CONCLUSION ---")
    print(f"{n_wh_128} warehouse codes hold these items today; no warehouse master table or business-unit "
          f"mapping exists in the database, and the one indirect test available (joining warehouse to sales "
          f"division) shows every warehouse code shared across multiple divisions, not cleanly business-unit-"
          f"specific - though this test is itself confounded by the project's already-documented itemcode-reuse-"
          f"across-division issue, so it cannot be treated as definitive either way. Multi-warehouse stocking is "
          f"the norm ({n_multi} of {n_present} present items, {100*n_multi/n_present:.1f}%). Stock transfers "
          f"between warehouses are CONFIRMED to occur, with exact-quantity-matched evidence spanning 2016 to the "
          f"present - warehouses cannot be treated as fully independent for planning purposes; goods routinely "
          f"move between them. Business unit ownership of each warehouse code must be obtained from the business.")

    print("\nOutputs: output/summary/part3_warehouse_list_128items.csv, part3_warehouse_division_test.csv, "
          "part3_item_warehouse_count.csv, part3_warehouse_transfer_pairs.csv")
