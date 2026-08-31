"""Full-column investigation of the 44 candidate-duplicate groups and the 3
Actual/MPS overlap cases found in the prior audit.

Investigation only. Does not clean, drop, or modify any data, and does not
build a model.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("investigate_duplicates")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

LOT_LIKE_KEYWORDS = [
    "lot", "seq", "line", "po", "do", "deliver", "warehouse", "destination",
    "ship", "district", "province", "customer",
]


def get_duplicate_sets():
    """Re-derive the exact (contractid, itemcode, createDate, qty, sale, status)
    sets flagged as true row-level duplicates in the prior audit."""
    df = pd.read_csv(os.path.join(SUMMARY_DIR, "task2_2_exact_duplicates.csv"))
    groups = df.groupby(["itemcode", "createDate", "qty", "sale", "status"])
    sets_ = []
    for key, grp in groups:
        contract_counts = grp["contractid"].value_counts()
        repeated = contract_counts[contract_counts > 1]
        for cid, cnt in repeated.items():
            sets_.append({
                "group_itemcode": key[0], "group_createDate": key[1], "group_qty": key[2],
                "group_sale": key[3], "group_status": key[4], "contractid": cid, "row_count": int(cnt),
            })
    logger.info("Re-derived %d parent 5-column groups, %d (contractid+5-col) duplicate sets",
                len(groups), len(sets_))
    return pd.DataFrame(sets_)


def pull_full_rows(dup_sets: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, r in dup_sets.iterrows():
        sql = (
            "SELECT * FROM cube_Sale_APD WHERE "
            f"contractid = '{r['contractid']}' AND itemcode = '{r['group_itemcode']}' "
            f"AND createDate = '{r['group_createDate']}' AND qty = {r['group_qty']} "
            f"AND sale = {r['group_sale']} AND status = '{r['group_status']}'"
        )
        rows = run_query(sql)
        rows["dup_set_id"] = f"{r['contractid']}|{r['group_itemcode']}|{r['group_createDate']}|{r['group_status']}"
        frames.append(rows)
    full = pd.concat(frames, ignore_index=True)
    logger.info("Pulled %d full-column rows across %d duplicate sets", len(full), len(dup_sets))
    return full


def compare_columns(full: pd.DataFrame):
    diff_records = []
    identical_sets = []
    col_diff_counter = {}
    all_cols = [c for c in full.columns if c != "dup_set_id"]

    for set_id, grp in full.groupby("dup_set_id"):
        grp = grp.reset_index(drop=True)
        differing_cols = []
        for col in all_cols:
            n_unique = grp[col].nunique(dropna=False)
            if n_unique > 1:
                differing_cols.append(col)
                col_diff_counter[col] = col_diff_counter.get(col, 0) + 1
                diff_records.append({
                    "dup_set_id": set_id, "column": col,
                    "values": grp[col].astype(str).tolist(),
                })
        if not differing_cols:
            identical_sets.append(set_id)

    diff_df = pd.DataFrame(diff_records)
    freq_df = pd.DataFrame(
        sorted(col_diff_counter.items(), key=lambda x: -x[1]),
        columns=["column", "n_sets_where_it_differs"],
    )
    logger.info("Sets with at least one differing column: %d", full["dup_set_id"].nunique() - len(identical_sets))
    logger.info("Sets identical across every column: %d -> %s", len(identical_sets), identical_sets)
    return diff_df, freq_df, identical_sets


if __name__ == "__main__":
    dup_sets = get_duplicate_sets()
    dup_sets.to_csv(os.path.join(SUMMARY_DIR, "task1_44groups_duplicate_sets.csv"), index=False)

    full = pull_full_rows(dup_sets)
    full.to_csv(os.path.join(DATA_DIR, "raw_44groups_full_columns.csv"), index=False)

    diff_df, freq_df, identical_sets = compare_columns(full)
    diff_df.to_csv(os.path.join(SUMMARY_DIR, "task1_column_differences.csv"), index=False)
    freq_df.to_csv(os.path.join(SUMMARY_DIR, "task1_column_diff_frequency.csv"), index=False)

    lot_like = freq_df[freq_df["column"].str.lower().apply(lambda c: any(k in c for k in LOT_LIKE_KEYWORDS))]

    print("\n" + "=" * 70)
    print("TASK 1 SUMMARY")
    print("=" * 70)
    print(f"Duplicate sets analyzed: {dup_sets.shape[0]}")
    print(f"Sets identical across EVERY column: {len(identical_sets)}")
    print(f"Sets with at least one differing column: {full['dup_set_id'].nunique() - len(identical_sets)}")
    print("\nColumn-difference frequency (top 20):")
    print(freq_df.head(20).to_string(index=False))
    print("\nColumns matching lot/sequence/PO/delivery/warehouse/destination/customer keywords:")
    print(lot_like.to_string(index=False))
