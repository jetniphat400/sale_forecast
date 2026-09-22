"""Phase E1-fix Part 0: compare Cube_Backlog (table) against Cube_CES Status='Backlog' (rows)
for the 128-item PEM101 pilot scope, to resolve METRICS.md Sec.14's literal-text ambiguity
("Backlog rows in Cube_CES") against this project's prior convention (the separate Cube_Backlog
table). Does NOT edit METRICS.md -- reports the finding only.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import run_query
from phaseE1_common import PROJECT_ROOT, load_config, load_scope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1fix_part0")

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def main():
    config = load_config()
    scope = load_scope(config)
    codes = scope["code"].tolist()
    code_list = "','".join(sorted(codes))

    backlog = run_query(f"""SELECT docID, itemcode, quantity, status, sale_company, deliverydate, plan_deliverydate
                            FROM [salewarehouse].[dbo].[Cube_Backlog] WHERE itemcode IN ('{code_list}')""")
    backlog["sale_company"] = backlog["sale_company"].astype(str).str.strip()
    backlog_kept = backlog[backlog["sale_company"].isin(["PEM", "CI"])].copy()

    ces = run_query(f"""SELECT ContractID, ItemCode, CtrDate, ActualQty, BacklogQty, Status
                        FROM [salewarehouse].[dbo].[Cube_CES]
                        WHERE ItemCode IN ('{code_list}') AND Status='Backlog'""")
    ces["qty"] = ces["ActualQty"].fillna(0) + ces["BacklogQty"].fillna(0)

    n_backlog_rows = len(backlog_kept)
    n_ces_rows = len(ces)
    qty_backlog = float(backlog_kept["quantity"].sum())
    qty_ces = float(ces["qty"].sum())

    backlog_pairs = set(zip(backlog_kept["docID"].astype(str), backlog_kept["itemcode"]))
    ces_pairs = set(zip(ces["ContractID"].astype(str), ces["ItemCode"]))
    # docID (Cube_Backlog) and ContractID (Cube_CES) are different key spaces in general -- try a
    # direct string-equality match as the only testable hypothesis (no verified shared key exists
    # per STATUS.md); report the raw overlap, not a forced interpretation.
    direct_key_overlap = len(backlog_pairs & ces_pairs)

    backlog_items = set(backlog_kept["itemcode"])
    ces_items = set(ces["ItemCode"])
    item_overlap = backlog_items & ces_items
    item_only_backlog = backlog_items - ces_items
    item_only_ces = ces_items - backlog_items

    print("\n" + "=" * 90)
    print("PART 0 -- Cube_Backlog vs Cube_CES(Status='Backlog'), PEM101 128-item scope")
    print("=" * 90)
    print(f"Cube_Backlog (sale_company IN PEM,CI): {n_backlog_rows} rows, qty={qty_backlog:,.1f}, "
          f"{len(backlog_items)} distinct items, {len(backlog_pairs)} distinct (docID,item) pairs")
    print(f"Cube_CES Status='Backlog':             {n_ces_rows} rows, qty={qty_ces:,.1f}, "
          f"{len(ces_items)} distinct items, {len(ces_pairs)} distinct (ContractID,item) pairs")
    print(f"Direct (contract/docID, item) key-string overlap: {direct_key_overlap} "
          f"(docID and ContractID are different key spaces -- this is a weak/unreliable test, reported as-is)")
    print(f"Item-level overlap: {len(item_overlap)} items in both; {len(item_only_backlog)} only in "
          f"Cube_Backlog; {len(item_only_ces)} only in Cube_CES")

    if qty_backlog == 0 and qty_ces == 0:
        verdict = "Both sources are EMPTY for this scope -- no live outstanding backlog for these 128 items right now; the ambiguity has no practical effect at this snapshot."
    elif qty_backlog >= qty_ces and item_only_ces == set():
        verdict = "Cube_Backlog appears to be the SUPERSET (covers every item Cube_CES(Backlog) covers, and more) -- using Cube_Backlog is the safer choice to avoid under-counting confirmed undelivered demand."
    elif qty_ces >= qty_backlog and item_only_backlog == set():
        verdict = "Cube_CES(Status=Backlog) appears to be the SUPERSET -- using Cube_CES is the safer choice."
    else:
        verdict = "The two sources are MATERIALLY DIFFERENT populations (neither is a clean subset of the other) -- reported as such, not resolved by picking one; see the item-level overlap breakdown above."
    print(f"\nVERDICT: {verdict}")

    backlog_kept.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_0_cube_backlog_table.csv"), index=False)
    ces.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_0_cube_ces_backlog_rows.csv"), index=False)

    return {"n_backlog_rows": n_backlog_rows, "n_ces_rows": n_ces_rows, "qty_backlog": qty_backlog,
            "qty_ces": qty_ces, "item_overlap": item_overlap, "item_only_backlog": item_only_backlog,
            "item_only_ces": item_only_ces, "verdict": verdict}


if __name__ == "__main__":
    main()
