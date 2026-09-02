"""Phase 4 prep investigation (follow-up), Part 3: which stock is actually sellable.

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched.
Scope: the 128 item codes in Product Cate. Fuse and Surge Arrester.

Business context given by the user: QA means inspection, then storage, then ready to ship -
implying 3 conceptual stages. This script classifies warehouse codes by OBSERVED BEHAVIOUR from
Part 1/2 (whether stock is ever drawn down for external use), not by what the code's name
suggests, and states plainly where the data cannot settle the question.

*** Hard structural gap, stated up front: neither cube_Sale_APD nor Cube_CES (the sales tables)
has ANY warehouse field (checked directly against both schemas) - there is NO way to link a
customer sale to the warehouse it shipped from, for any of the 128 items, Finished Goods or Raw
Material. The only behavioural evidence available (Part 1/2's external-issue analysis) comes from
cube_inventory_tran, which itself only covers 6 of 128 items (the Raw Material Fuse Holder codes)
and their exits there are issues TO PRODUCTION, not to a customer. This means "which stock is
sellable" cannot be directly answered for the 122 Finished Goods items that matter most to this
project - only a narrower, indirect question can be: which warehouse codes show behavioural
evidence of NEVER being drawn down for any external use at all (a safe lower bound on
"definitely not yet available"), versus everything else, which cannot be confirmed either way. ***
"""
import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


if __name__ == "__main__":
    print("\n" + "#" * 92)
    print("# PART 3: WHICH STOCK IS ACTUALLY SELLABLE")
    print("#" * 92)

    print("\n--- STRUCTURAL GAP, checked directly ---")
    print("Neither cube_Sale_APD nor Cube_CES has a warehouse column (re-confirmed against both schemas). "
          "There is no way to determine, from any sales record, which warehouse a delivered order shipped "
          "from. 'Sellable' cannot be measured directly for any item in this scope - only inferred indirectly, "
          "and only where other evidence exists.")

    role_df = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_warehouse_role_from_movement.csv")).set_index("warehouse")
    inv = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_exact_128items.csv"))
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()

    # ================= CLASSIFY BY OBSERVED BEHAVIOUR =================
    print("\n--- CLASSIFICATION, from observed behaviour only ---")
    print("IMPORTANT METHODOLOGICAL POINT, caught and corrected while writing this up: a first pass classified")
    print("every code with zero external-issue events in the 6-item RM ledger (including FG01/FG11/FG21/INTR)")
    print("as 'confirmed not available'. That is WRONG - those 6 items hold almost none of FG01/FG11/FG21's")
    print("stock (144,094 / 0 / 23,118 units respectively, across ALL 128 items). The ledger's silence for 6")
    print("unrelated Raw Material items says nothing about whether the much larger population of Finished")
    print("Goods items sitting in those same warehouse CODES ever ships from there. Absence of evidence for 6")
    print("items is not evidence of absence for the other 122. Only two exclusions are actually justified:")

    print("\n1. QA: of 567,306 units it ever received or held (6-item ledger), only 22 (0.004%) were ever issued "
          "externally - it is a pass-through gate. This generalises across items only as far as 'QA is an "
          "inspection gate' is itself an item-independent PROCESS description (confirmed directly by the "
          "business, not just inferred) - but note it is still an extrapolation beyond the 6 items actually "
          "observed, not separately proven for every one of the 128 items.")
    fmts_fmto = inv[inv["warehouse"].isin(["FMTS", "FMTO"])]
    n_fmts_items = inv.loc[inv["warehouse"] == "FMTS", "itemcode"].nunique()
    n_fmto_items = inv.loc[inv["warehouse"] == "FMTO", "itemcode"].nunique()
    print(f"\n2. FMTS/FMTO: this is evidenced BROADLY, independent of the 6-item ledger - {n_fmts_items} and "
          f"{n_fmto_items} of the 128 items (respectively) appear in the current snapshot under FMTS/FMTO, "
          f"and across ALL of them, settled 'stock' is negligible ({fmts_fmto['stock'].sum():,.0f} units "
          f"combined) while 'tobe_received' (incoming from an open, not-yet-complete production order) is "
          f"large ({fmts_fmto['tobe_received'].sum():,.0f} units) - a pattern confirmed across the wide item "
          f"set, not just the 6-item ledger subset.")

    confirmed_not_available = ["QA", "FMTS", "FMTO"]
    print(f"\n**Confirmed NOT available for any external use (in-process): {confirmed_not_available}.**")

    all_wh_in_snapshot = inv["warehouse"].unique().tolist()
    everything_else = sorted(set(all_wh_in_snapshot) - set(confirmed_not_available))
    print(f"\n**Every other warehouse code ({len(everything_else)} codes: {everything_else}) - CANNOT be "
          f"confirmed sellable or not-sellable from this data, including FG01/FG11/FG21/INTR (which merely "
          f"show no issue events among the 6 unrelated RM items) and WH01/WH21/FG02 (which DO show real "
          f"external-issue activity, but issue-to-PRODUCTION for raw-material components, not a customer "
          f"sale - this does not prove the analogous code holds sellable FINISHED GOODS stock too).**")

    # ================= CURRENT QUANTITIES BY STAGE =================
    print("\n--- CURRENT QUANTITIES BY STAGE (all 128 items, current Cube_Inventory_Exact snapshot) ---")
    by_wh = inv.groupby("warehouse").agg(
        n_items=("itemcode", "nunique"), total_stock=("stock", "sum"), total_available=("available", "sum"),
    ).sort_values("total_stock", ascending=False)
    by_wh["classification"] = by_wh.index.map(
        lambda wh: "Confirmed NOT available (in-process)" if wh in confirmed_not_available else "Cannot determine")
    by_wh.to_csv(os.path.join(SUMMARY_DIR, "part3_stock_by_stage_classification.csv"))
    print(by_wh.round(0).to_string())

    total_stock_all = by_wh["total_stock"].sum()
    not_avail_stock = by_wh.loc[by_wh["classification"] == "Confirmed NOT available (in-process)", "total_stock"].sum()
    cannot_determine_stock = total_stock_all - not_avail_stock
    print(f"\nOf {total_stock_all:,.0f} total on-hand 'stock' units across the 128-item scope: "
          f"{not_avail_stock:,.0f} ({100*not_avail_stock/total_stock_all:.2f}%) sit in warehouses CONFIRMED "
          f"not-yet-available for use; {cannot_determine_stock:,.0f} "
          f"({100*cannot_determine_stock/total_stock_all:.2f}%) sit in warehouses where availability CANNOT be "
          f"confirmed either way from this data.")
    print("This is NOT the same as saying that remaining stock IS sellable - it means the data cannot rule "
          "either way for it. Reporting it as 'sellable' would overstate what the evidence supports.")

    print("\n--- PART 3 CONCLUSION ---")
    print("The 3-stage business description (inspection -> storage -> ready to ship) maps cleanly onto QA for")
    print("the inspection stage (near-zero external issue, matching the business's own description) and onto")
    print("FMTS/FMTO for production-order WIP (near-zero settled stock, broadly evidenced across 69-103 of 128")
    print("items). Beyond those two, the data CANNOT confirm which stage holds sellable stock: production draws")
    print("components directly from WH01/WH21/FG02 for the 6 Raw Material items with any movement evidence, but")
    print("that is consumption-into-assembly, not a customer sale, and tells us nothing about the 122 Finished")
    print("Goods items that actually matter for customer-facing planning. Whether FG01/FG02/FG11/FG21")
    print("specifically represent a genuine 'ready to ship' stage for those FG items is PLAUSIBLE from their")
    print("downstream position in the flow (Part 1) but NOT CONFIRMED BY BEHAVIOUR - no sales table has a")
    print("warehouse field, and the movement ledger does not cover any FG item at all. This must be confirmed")
    print("by the business (e.g. warehouse/operations staff who know which locations orders are physically")
    print("picked and shipped from).")

    print("\nOutputs: output/summary/part3_stock_by_stage_classification.csv")
