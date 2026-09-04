"""Investigates whether the Dec-2022-to-Jan-2023 break in Cube_CES (PEM101,
Omni Channel, pilot items) reflects a system/recording change or a genuine
business change: customer history, contract start dates, item history
elsewhere, and the monthly shape of the transition.

Investigation only. Does not extend the analysis period or modify config.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_2023_break")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

    # ============ PART 2: the 63 Jan-2023 customers' prior history ============
    jan23_customers = run_query(f"""
        SELECT DISTINCT CustomerID FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2023-01-01' AND CtrDate < '2023-02-01'
    """)
    cust_ids = sorted(jan23_customers["CustomerID"].dropna().unique())
    logger.info("Distinct customers in Jan 2023 (pilot items, PEM101/Omni Channel): %d", len(cust_ids))
    cust_list = "','".join(cust_ids)

    # ref_customer entry_date (earliest recorded registration)
    entry = run_query(f"SELECT customerid, MIN(entry_date) AS earliest_entry_date FROM ref_customer WHERE customerid IN ('{cust_list}') GROUP BY customerid")
    entry.to_csv(os.path.join(SUMMARY_DIR, "part2_jan2023_customers_entry_date.csv"), index=False)
    n_pre2023_entry = (pd.to_datetime(entry["earliest_entry_date"]) < pd.Timestamp("2023-01-01")).sum()
    logger.info("Of %d Jan-2023 customers: %d have a ref_customer entry_date before 2023-01-01 (pre-existing registration)",
                len(entry), n_pre2023_entry)

    # Any earlier activity in cube_Sale_APD, ANY division/revenue_type, before 2023-01-01
    apd_prior = run_query(f"""
        SELECT customerid, MIN(createDate) AS earliest_createDate, COUNT(*) AS n_rows,
               COUNT(DISTINCT division) AS n_divisions, COUNT(DISTINCT revenue_type) AS n_revenue_types
        FROM cube_Sale_APD WHERE customerid IN ('{cust_list}') AND createDate < '2023-01-01'
        GROUP BY customerid
    """)
    apd_prior.to_csv(os.path.join(SUMMARY_DIR, "part2_jan2023_customers_apd_prior_activity.csv"), index=False)
    logger.info("Of %d Jan-2023 customers: %d have PRIOR cube_Sale_APD activity (any division/revenue_type) before 2023-01-01",
                len(cust_ids), len(apd_prior))

    # Any earlier activity in Cube_CES, ANY ManuDivision/RevenueType, before 2023-01-01
    ces_prior = run_query(f"""
        SELECT CustomerID AS customerid, MIN(CtrDate) AS earliest_ctrdate, COUNT(*) AS n_rows,
               COUNT(DISTINCT ManuDivision) AS n_divisions, COUNT(DISTINCT RevenueType) AS n_revenue_types
        FROM Cube_CES WHERE CustomerID IN ('{cust_list}') AND CtrDate < '2023-01-01'
        GROUP BY CustomerID
    """)
    ces_prior.to_csv(os.path.join(SUMMARY_DIR, "part2_jan2023_customers_ces_prior_activity.csv"), index=False)
    logger.info("Of %d Jan-2023 customers: %d have PRIOR Cube_CES activity (any division/revenue_type) before 2023-01-01",
                len(cust_ids), len(ces_prior))

    any_prior = set(apd_prior["customerid"]) | set(ces_prior["customerid"]) | set(entry.loc[pd.to_datetime(entry["earliest_entry_date"]) < pd.Timestamp("2023-01-01"), "customerid"])
    logger.info("Of %d Jan-2023 customers: %d have SOME prior trace (entry_date, cube_Sale_APD, or Cube_CES) before 2023-01-01; %d appear genuinely new",
                len(cust_ids), len(any_prior), len(cust_ids) - len(any_prior))

    # ============ PART 3: contract start dates for Jan-2023 contracts ============
    jan23_contracts = run_query(f"""
        SELECT DISTINCT ContractID, CtrDate FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2023-01-01' AND CtrDate < '2023-02-01'
    """)
    logger.info("Distinct contracts in Jan 2023 (pilot items): %d", jan23_contracts["ContractID"].nunique())
    # earliest CtrDate for these same ContractIDs anywhere in Cube_CES (any item/division/revenue_type)
    ctr_list = "','".join(jan23_contracts["ContractID"].unique())
    ctr_earliest = run_query(f"""
        SELECT ContractID, MIN(CtrDate) AS earliest_ctrdate_anywhere
        FROM Cube_CES WHERE ContractID IN ('{ctr_list}') GROUP BY ContractID
    """)
    ctr_earliest.to_csv(os.path.join(SUMMARY_DIR, "part3_jan2023_contracts_earliest_date.csv"), index=False)
    n_started_before = (pd.to_datetime(ctr_earliest["earliest_ctrdate_anywhere"]) < pd.Timestamp("2023-01-01")).sum()
    logger.info("Of %d Jan-2023 contracts: %d have an earliest CtrDate (any item) BEFORE 2023-01-01",
                len(ctr_earliest), n_started_before)

    # ============ PART 4: pilot items before 2023, any division/revenue_type/status ============
    apd_item_prior = run_query(f"""
        SELECT itemcode, division, revenue_type, status, COUNT(*) AS n_rows, MIN(createDate) AS earliest, MAX(createDate) AS latest,
               SUM(qty) AS total_qty, COUNT(DISTINCT customerid) AS n_customers
        FROM cube_Sale_APD WHERE itemcode IN ('{code_list}') AND createDate < '2023-01-01'
        GROUP BY itemcode, division, revenue_type, status ORDER BY itemcode
    """)
    apd_item_prior.to_csv(os.path.join(SUMMARY_DIR, "part4_pilot_items_apd_before_2023.csv"), index=False)
    logger.info("cube_Sale_APD: pilot items before 2023-01-01, any division/revenue_type/status: %d rows across %d items",
                apd_item_prior["n_rows"].sum() if len(apd_item_prior) else 0, apd_item_prior["itemcode"].nunique() if len(apd_item_prior) else 0)

    ces_item_prior = run_query(f"""
        SELECT ItemCode AS itemcode, ManuDivision, RevenueType, Status, COUNT(*) AS n_rows,
               MIN(CtrDate) AS earliest, MAX(CtrDate) AS latest,
               SUM(ActualQty)+SUM(BacklogQty) AS total_qty, COUNT(DISTINCT CustomerID) AS n_customers
        FROM Cube_CES WHERE ItemCode IN ('{code_list}') AND CtrDate < '2023-01-01'
        GROUP BY ItemCode, ManuDivision, RevenueType, Status ORDER BY ItemCode
    """)
    ces_item_prior.to_csv(os.path.join(SUMMARY_DIR, "part4_pilot_items_ces_before_2023.csv"), index=False)
    logger.info("Cube_CES: pilot items before 2023-01-01, any ManuDivision/RevenueType/Status: %d rows across %d items",
                ces_item_prior["n_rows"].sum() if len(ces_item_prior) else 0, ces_item_prior["itemcode"].nunique() if len(ces_item_prior) else 0)

    # ============ PART 5: monthly shape, Jan 2022 - Dec 2023 ============
    pilot_monthly = run_query(f"""
        SELECT YEAR(CtrDate) AS yr, MONTH(CtrDate) AS mo, COUNT(*) AS n_rows,
               COUNT(DISTINCT CustomerID) AS n_customers, COUNT(DISTINCT ItemCode) AS n_items,
               SUM(ActualQty)+SUM(BacklogQty) AS total_qty, SUM(ActualPrice)+SUM(BacklogPrice) AS total_value
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2022-01-01' AND CtrDate < '2024-01-01'
        GROUP BY YEAR(CtrDate), MONTH(CtrDate) ORDER BY yr, mo
    """)
    pilot_monthly.to_csv(os.path.join(SUMMARY_DIR, "part5_pilot_monthly_2022_2023.csv"), index=False)

    whole_pem101_monthly = run_query("""
        SELECT YEAR(CtrDate) AS yr, MONTH(CtrDate) AS mo, COUNT(*) AS n_rows,
               COUNT(DISTINCT CustomerID) AS n_customers, COUNT(DISTINCT ItemCode) AS n_items,
               SUM(ActualQty)+SUM(BacklogQty) AS total_qty, SUM(ActualPrice)+SUM(BacklogPrice) AS total_value
        FROM Cube_CES
        WHERE ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2022-01-01' AND CtrDate < '2024-01-01'
        GROUP BY YEAR(CtrDate), MONTH(CtrDate) ORDER BY yr, mo
    """)
    whole_pem101_monthly.to_csv(os.path.join(SUMMARY_DIR, "part5_whole_pem101_monthly_2022_2023.csv"), index=False)

    print("\n=== PART 5: Pilot items, Jan 2022 - Dec 2023 ===")
    print(pilot_monthly.to_string(index=False))
    print("\n=== PART 5: Whole PEM101/Omni Channel, Jan 2022 - Dec 2023 ===")
    print(whole_pem101_monthly.to_string(index=False))
