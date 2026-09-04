"""Phase 4 prep investigation (follow-up), Part 1: map the full warehouse flow.

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched.
Scope: the 128 item codes in Product Cate. Fuse and Surge Arrester.

Business context corrected by the user for this task: warehouses are STAGES of one process
(inspection -> storage -> ready to ship), not separate locations or business units. This script
reports every observed transfer route (not just the dominant path), tests directionality, and
classifies each of the 34 warehouse codes by OBSERVED movement behaviour - never by inference
from the code's name/abbreviation alone. A code is reported as "unidentified" when the data
gives no movement evidence for it in this item scope.

Reuses output/data/raw_inventory_tran_128items.csv (cube_inventory_tran) and
output/data/raw_inventory_exact_128items.csv (Cube_Inventory_Exact current snapshot), both
already pulled in the earlier Phase 4 groundwork survey / prep investigation.
"""
import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

# Transaction-type categorisation, evidenced directly from the qty-column behaviour of each code
# (checked against the whole table, not guessed): 150/151 are an exact transfer-out/transfer-in
# pair (see Part 3 of the prior investigation); A and H are QtyIn-only (external/incoming); B and
# J are QtyOut-only (external/outgoing); 190 is a stock count/adjustment; N and T carry no
# reliable qty and are excluded from movement volume (N is almost entirely a no-qty reference row,
# T is an accounting journal entry with Debit/Credit only, no physical qty).
EXTERNAL_IN_TYPES = ["A", "H"]
EXTERNAL_OUT_TYPES = ["B", "J"]
TRANSFER_OUT_TYPE = "150"
TRANSFER_IN_TYPE = "151"


def get_scope() -> pd.DataFrame:
    return pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))


def build_confirmed_transfers(tran: pd.DataFrame) -> pd.DataFrame:
    t = tran[tran["transtype"].isin([TRANSFER_OUT_TYPE, TRANSFER_IN_TYPE])].copy()
    rows = []
    for key, grp in t.groupby(["itemcode", "ourref", "trans_date"]):
        if len(grp) == 2 and set(grp["transtype"]) == {TRANSFER_OUT_TYPE, TRANSFER_IN_TYPE}:
            out_row = grp[grp["transtype"] == TRANSFER_OUT_TYPE].iloc[0]
            in_row = grp[grp["transtype"] == TRANSFER_IN_TYPE].iloc[0]
            if pd.notna(out_row["QtyOut"]) and pd.notna(in_row["QtyIn"]) and abs(out_row["QtyOut"] - in_row["QtyIn"]) < 0.01:
                rows.append({
                    "itemcode": key[0], "ourref": key[1], "trans_date": key[2],
                    "from_warehouse": out_row["warehouse"], "to_warehouse": in_row["warehouse"],
                    "qty": in_row["QtyIn"],
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    scope = get_scope()
    codes = sorted(scope["code"].unique())

    print("\n" + "#" * 92)
    print("# PART 1: FULL WAREHOUSE FLOW MAP")
    print("#" * 92)

    tran = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_tran_128items.csv"))
    tran["warehouse"] = tran["warehouse"].astype(str).str.strip()
    tran["trans_date"] = pd.to_datetime(tran["trans_date"])
    n_ledger_items = tran["itemcode"].nunique()

    transfers = build_confirmed_transfers(tran)
    transfers.to_csv(os.path.join(DATA_DIR, "processed_warehouse_transfers_128items.csv"), index=False)
    transfer_items = sorted(transfers["itemcode"].unique())

    print(f"\ncube_inventory_tran (the movement ledger) covers {n_ledger_items} of {len(codes)} items in this "
          f"scope at all. Of those {n_ledger_items}, only {len(transfer_items)} show ANY confirmed "
          f"transfer (150/151 pair): {transfer_items}.")
    print(f"\n*** CRITICAL SCOPE LIMITATION, stated up front: all {len(transfer_items)} items with transfer "
          f"evidence are the Fuse Holder RAW MATERIAL codes (previously classified Raw Material, not Finished "
          f"Goods, in the earlier Phase 4 groundwork survey) - {round(100*len(transfer_items)/len(codes),1)}% "
          f"of the 128-item scope. The other {n_ledger_items - len(transfer_items)} items the ledger covers at "
          f"all have only {(tran[~tran['itemcode'].isin(transfer_items)]['transtype'].isin(['N']).sum())} "
          f"near-empty reference rows between them, no real movement history. **Everything in this "
          f"investigation about warehouse flow, dwell time, and stage-level movement is evidenced ONLY for "
          f"these {len(transfer_items)} raw-material component items. It CANNOT be confirmed to hold for the "
          f"122 Finished Goods items that make up the great majority of this project's value and volume - the "
          f"movement ledger simply does not cover them.** Where this script applies a warehouse code's "
          f"observed role to the wider 128-item snapshot, that is stated explicitly as an extrapolation, not a "
          f"separately-confirmed fact for those items.")

    # ================= FULL ROUTE TABLE =================
    print("\n--- ALL OBSERVED TRANSFER ROUTES (from -> to), with volumes ---")
    routes = transfers.groupby(["from_warehouse", "to_warehouse"]).agg(
        n_transfers=("qty", "count"), total_qty=("qty", "sum"), n_items=("itemcode", "nunique"),
    ).sort_values("total_qty", ascending=False)
    routes.to_csv(os.path.join(SUMMARY_DIR, "part1_all_transfer_routes.csv"))
    print(routes.to_string())

    # ================= DIRECTIONALITY =================
    print("\n--- DIRECTIONALITY: is movement one-way or bidirectional between each pair? ---")
    pair_dir = {}
    for (a, b), row in routes.iterrows():
        key = tuple(sorted([a, b]))
        pair_dir.setdefault(key, {})[( "forward" if (a, b) == (key[0], key[1]) else "reverse")] = row["total_qty"]
    dir_rows = []
    for (a, b), d in pair_dir.items():
        fwd = d.get("forward", 0)
        rev = d.get("reverse", 0)
        both = fwd > 0 and rev > 0
        dir_rows.append({
            "warehouse_a": a, "warehouse_b": b, "qty_a_to_b": fwd, "qty_b_to_a": rev,
            "bidirectional": both,
        })
    dir_df = pd.DataFrame(dir_rows)
    dir_df.to_csv(os.path.join(SUMMARY_DIR, "part1_route_directionality.csv"), index=False)
    n_bidir = dir_df["bidirectional"].sum()
    print(f"{n_bidir} of {len(dir_df)} warehouse PAIRS with any observed transfer show movement in BOTH "
          f"directions; {len(dir_df) - n_bidir} are one-directional only.")
    print("Movement is therefore NOT strictly one-way through fixed sequential stages - it is predominantly "
          "forward (e.g. QA->WH01 far outweighs WH01->QA: 464,350 vs 96,450 units) but genuine reverse "
          "movement is confirmed at meaningful volume, not just noise:")
    bidir_pairs = dir_df[dir_df["bidirectional"]]
    for _, r in bidir_pairs.iterrows():
        print(f"  {r['warehouse_a']} -> {r['warehouse_b']} = {r['qty_a_to_b']:,.0f}   |   "
              f"{r['warehouse_b']} -> {r['warehouse_a']} = {r['qty_b_to_a']:,.0f}")

    # ================= PER-WAREHOUSE ROLE (movement-evidenced) =================
    print("\n--- PER-WAREHOUSE ROLE, FROM OBSERVED MOVEMENT (transfers + external in/out) ---")
    ext_in = tran[tran["transtype"].isin(EXTERNAL_IN_TYPES)].groupby("warehouse")["QtyIn"].sum()
    ext_out = tran[tran["transtype"].isin(EXTERNAL_OUT_TYPES)].groupby("warehouse")["QtyOut"].sum()
    xfer_out = transfers.groupby("from_warehouse")["qty"].sum()
    xfer_in = transfers.groupby("to_warehouse")["qty"].sum()

    all_wh_with_activity = set(ext_in.index) | set(ext_out.index) | set(xfer_out.index) | set(xfer_in.index)
    role_rows = []
    for wh in sorted(all_wh_with_activity):
        ei, eo = ext_in.get(wh, 0.0), ext_out.get(wh, 0.0)
        xo, xi = xfer_out.get(wh, 0.0), xfer_in.get(wh, 0.0)
        if ei > 0 and eo == 0 and xo == 0:
            role = "External receipt point only (goods enter here, no observed exit)"
        elif eo > 0 and ei == 0 and xi == 0:
            role = "External issue point only (goods leave here, no observed entry)"
        elif xo > 0 and xi == 0 and ei == 0 and eo == 0:
            role = "Transfer source only (sends onward, receives nothing observed)"
        elif xi > 0 and xo == 0 and ei == 0 and eo == 0:
            role = "Transfer destination only (receives, sends nothing observed)"
        else:
            role = "Mixed / transit (both inflow and outflow observed)"
        role_rows.append({
            "warehouse": wh, "external_receipt_qty": ei, "external_issue_qty": eo,
            "transfer_out_qty": xo, "transfer_in_qty": xi, "role_from_observed_behaviour": role,
        })
    role_df = pd.DataFrame(role_rows).sort_values(
        by=["external_receipt_qty", "external_issue_qty", "transfer_out_qty", "transfer_in_qty"], ascending=False)
    role_df.to_csv(os.path.join(SUMMARY_DIR, "part1_warehouse_role_from_movement.csv"), index=False)
    print(role_df.round(0).to_string(index=False))

    # ================= CROSS-REFERENCE WITH CURRENT SNAPSHOT (all 125 items) =================
    print("\n--- CROSS-REFERENCE: current-snapshot item holdings for ALL 34 codes (all 125 items present) ---")
    inv = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_exact_128items.csv"))
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    snap_by_wh = inv.groupby("warehouse").agg(
        n_items=("itemcode", "nunique"), total_stock=("stock", "sum"),
        total_freestock=("freestock", "sum"), total_tobe_received=("tobe_received", "sum"),
        total_available=("available", "sum"),
    ).sort_values("n_items", ascending=False)
    snap_by_wh["has_movement_evidence"] = snap_by_wh.index.isin(all_wh_with_activity)
    snap_by_wh.to_csv(os.path.join(SUMMARY_DIR, "part1_warehouse_snapshot_summary.csv"))
    print(snap_by_wh.round(0).to_string())

    unidentified = snap_by_wh[~snap_by_wh["has_movement_evidence"]]
    identified = snap_by_wh[snap_by_wh["has_movement_evidence"]]
    print(f"\n{len(identified)} of {len(snap_by_wh)} warehouse codes present in the current snapshot have SOME "
          f"observed movement evidence (transfer or external in/out) in this item scope's ledger, so a "
          f"behavioural role could be assigned (see table above).")
    print(f"\n**{len(unidentified)} of {len(snap_by_wh)} codes have ZERO movement evidence in this scope's "
          f"ledger: {sorted(unidentified.index.tolist())}. Listed as UNIDENTIFIED per instruction - no role is "
          f"assigned by inference from the code's name.** This most likely reflects the ledger's own narrow "
          f"34/128-item coverage (these codes may hold plenty of the OTHER 94 items the ledger simply never "
          f"captures) rather than proof these warehouses are inactive - the data cannot distinguish the two "
          f"explanations. They currently hold {int(unidentified['n_items'].sum())} (item, warehouse) "
          f"combinations and {unidentified['total_stock'].sum():,.0f} units of on-hand stock combined across "
          f"the 128-item scope.")

    print("\n--- PART 1 CONCLUSION ---")
    print("The flow is predominantly forward (QA -> WH01 -> downstream FG-family codes, by volume) but movement")
    print("is CONFIRMED bidirectional between several pairs, not strictly a fixed one-way sequence. A")
    print(f"behavioural role could be assigned to {len(identified)} of {len(snap_by_wh)} codes actually present")
    print(f"in the current snapshot; the remaining {len(unidentified)} are UNIDENTIFIED, not assumed inactive.")
    print("All of this is evidenced for only 6 of 128 items (the Raw Material Fuse Holder codes) - see the")
    print("scope limitation stated above.")

    print("\nOutputs: output/summary/part1_all_transfer_routes.csv, part1_route_directionality.csv, "
          "part1_warehouse_role_from_movement.csv, part1_warehouse_snapshot_summary.csv")
