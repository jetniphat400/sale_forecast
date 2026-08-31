"""Verifies, row by row, which Cube_CES status corresponds to cube_Sale_APD's
MPS and Actual statuses, for the 58 pilot items in the 2024+ overlap period.

Verification only. Does not extend the analysis period or modify config.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("verify_ces_status_mapping")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def get_58_item_codes():
    pilot = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    codes68 = sorted(pilot[pilot["type"].isin(["High Voltage Distribution Fuse Cutout", "Medium Voltage Surge Arrester"])]["code"].unique())
    code_list = "','".join(codes68)
    present = run_query(f"SELECT DISTINCT itemcode FROM cube_Sale_APD WHERE itemcode IN ('{code_list}')")
    return sorted(present["itemcode"])


if __name__ == "__main__":
    item_codes = get_58_item_codes()
    code_list = "','".join(item_codes)
    logger.info("58 pilot items confirmed: %d", len(item_codes))

    # Pull cube_Sale_APD rows (2024+, PEM101/Omni Channel, all statuses) with their key fields
    apd = run_query(f"""
        SELECT contractid, itemcode, createDate, qty, sale, status, customerid
        FROM cube_Sale_APD
        WHERE itemcode IN ('{code_list}') AND division='PEM101' AND revenue_type='Omni Channel'
          AND createDate >= '2024-01-01'
    """)
    apd.to_csv(os.path.join(DATA_DIR, "raw_apd_all_status_2024plus.csv"), index=False)
    logger.info("cube_Sale_APD 2024+ pilot rows (all statuses): %d (Actual=%d, MPS=%d, other=%d)",
                len(apd), (apd["status"] == "Actual").sum(), (apd["status"] == "MPS").sum(),
                (~apd["status"].isin(["Actual", "MPS"])).sum())

    # Pull Cube_CES rows (2024+, ManuDivision=PEM101/RevenueType=Omni Channel, all statuses)
    ces = run_query(f"""
        SELECT ContractID AS contractid, ItemCode AS itemcode, CtrDate AS createDate,
               ActualQty, BacklogQty, PlanQty, Status, CustomerID AS customerid
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND CtrDate >= '2024-01-01'
    """)
    ces.to_csv(os.path.join(DATA_DIR, "raw_ces_all_status_2024plus.csv"), index=False)
    logger.info("Cube_CES 2024+ pilot rows (all statuses): %d", len(ces))
    logger.info("Cube_CES status distribution:\n%s", ces["Status"].value_counts().to_string())

    # For each cube_Sale_APD status, find matching Cube_CES rows by (contractid, itemcode)
    # and report the distribution of Cube_CES statuses among the matches.
    mapping_records = []
    for apd_status in apd["status"].unique():
        apd_sub = apd[apd["status"] == apd_status]
        keys = set(zip(apd_sub["contractid"], apd_sub["itemcode"]))
        ces_matches = ces[ces.apply(lambda r: (r["contractid"], r["itemcode"]) in keys, axis=1)]
        n_apd_rows = len(apd_sub)
        n_apd_pairs = len(keys)
        n_ces_matched_pairs = ces_matches[["contractid", "itemcode"]].drop_duplicates().shape[0]
        status_dist = ces_matches["Status"].value_counts()
        for ces_status, n in status_dist.items():
            mapping_records.append({
                "apd_status": apd_status, "n_apd_rows": n_apd_rows, "n_apd_contract_item_pairs": n_apd_pairs,
                "ces_status": ces_status, "n_ces_rows_with_this_status": n,
            })
        unmatched_pairs = n_apd_pairs - n_ces_matched_pairs
        mapping_records.append({
            "apd_status": apd_status, "n_apd_rows": n_apd_rows, "n_apd_contract_item_pairs": n_apd_pairs,
            "ces_status": "NO_CES_MATCH_AT_ALL", "n_ces_rows_with_this_status": unmatched_pairs,
        })

    mapping_df = pd.DataFrame(mapping_records)
    mapping_df.to_csv(os.path.join(SUMMARY_DIR, "part1_status_mapping_apd_to_ces.csv"), index=False)
    print("\n=== PART 1: cube_Sale_APD status -> Cube_CES status (by contract+item match) ===")
    print(mapping_df.to_string(index=False))

    # Reverse direction: for each Cube_CES status, what cube_Sale_APD statuses do its
    # matching (contractid, itemcode) pairs carry?
    reverse_records = []
    for ces_status in ces["Status"].unique():
        ces_sub = ces[ces["Status"] == ces_status]
        keys = set(zip(ces_sub["contractid"], ces_sub["itemcode"]))
        apd_matches = apd[apd.apply(lambda r: (r["contractid"], r["itemcode"]) in keys, axis=1)]
        status_dist = apd_matches["status"].value_counts()
        n_ces_pairs = len(keys)
        n_apd_matched_pairs = apd_matches[["contractid", "itemcode"]].drop_duplicates().shape[0]
        for apd_status, n in status_dist.items():
            reverse_records.append({
                "ces_status": ces_status, "n_ces_contract_item_pairs": n_ces_pairs,
                "apd_status": apd_status, "n_apd_rows_with_this_status": n,
            })
        unmatched = n_ces_pairs - n_apd_matched_pairs
        reverse_records.append({
            "ces_status": ces_status, "n_ces_contract_item_pairs": n_ces_pairs,
            "apd_status": "NO_APD_MATCH_AT_ALL", "n_apd_rows_with_this_status": unmatched,
        })
    reverse_df = pd.DataFrame(reverse_records)
    reverse_df.to_csv(os.path.join(SUMMARY_DIR, "part1_status_mapping_ces_to_apd.csv"), index=False)
    print("\n=== PART 1 (reverse): Cube_CES status -> cube_Sale_APD status (by contract+item match) ===")
    print(reverse_df.to_string(index=False))
