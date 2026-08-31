"""Deep investigation of Cube_CES: reconciliation against cube_Sale_APD for
2024+, and characterization of its pre-2024 rows for the 58 pilot items.

Investigation only. Does not extend the analysis period, change granularity,
or modify config.yaml.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_cube_ces")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    logger.info("58 pilot item codes confirmed: %d", len(item_codes))

    # ================= PART 2: reconcile vs cube_Sale_APD, 2024+ =================
    apd = run_query(f"""
        SELECT SUM(qty) AS total_qty, SUM(sale) AS total_sale, COUNT(*) AS n_rows,
               COUNT(DISTINCT contractid) AS n_contracts
        FROM cube_Sale_APD
        WHERE itemcode IN ('{code_list}') AND division='PEM101' AND revenue_type='Omni Channel'
          AND status IN ('Actual','MPS') AND createDate >= '2024-01-01'
    """)
    logger.info("cube_Sale_APD (2024+, PEM101/Omni Channel/Actual+MPS): qty=%.1f, sale=%.2f, rows=%d, contracts=%d",
                apd["total_qty"].iloc[0], apd["total_sale"].iloc[0], apd["n_rows"].iloc[0], apd["n_contracts"].iloc[0])

    ces = run_query(f"""
        SELECT SUM(ActualQty) AS total_actual_qty, SUM(BacklogQty) AS total_backlog_qty,
               SUM(ActualPrice) AS total_actual_price, SUM(BacklogPrice) AS total_backlog_price,
               COUNT(*) AS n_rows, COUNT(DISTINCT ContractID) AS n_contracts
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2024-01-01'
    """)
    ces_qty = (ces["total_actual_qty"].iloc[0] or 0) + (ces["total_backlog_qty"].iloc[0] or 0)
    ces_value = (ces["total_actual_price"].iloc[0] or 0) + (ces["total_backlog_price"].iloc[0] or 0)
    logger.info("Cube_CES (2024+, ManuDivision=PEM101/RevenueType=Omni Channel/Status=Actual+Backlog): "
                "qty=%.1f, value=%.2f, rows=%d, contracts=%d", ces_qty, ces_value, ces["n_rows"].iloc[0], ces["n_contracts"].iloc[0])

    comparison = pd.DataFrame([
        {"source": "cube_Sale_APD", "total_qty": apd["total_qty"].iloc[0], "total_value": apd["total_sale"].iloc[0],
         "n_rows": apd["n_rows"].iloc[0], "n_contracts": apd["n_contracts"].iloc[0]},
        {"source": "Cube_CES", "total_qty": ces_qty, "total_value": ces_value,
         "n_rows": ces["n_rows"].iloc[0], "n_contracts": ces["n_contracts"].iloc[0]},
    ])
    comparison.to_csv(os.path.join(SUMMARY_DIR, "part2_ces_vs_apd_aggregate.csv"), index=False)
    print("\n=== PART 2: AGGREGATE COMPARISON (2024+) ===")
    print(comparison.to_string(index=False))

    # contract-level comparison
    apd_by_contract = run_query(f"""
        SELECT contractid, itemcode, SUM(qty) AS apd_qty, SUM(sale) AS apd_value
        FROM cube_Sale_APD
        WHERE itemcode IN ('{code_list}') AND division='PEM101' AND revenue_type='Omni Channel'
          AND status IN ('Actual','MPS') AND createDate >= '2024-01-01'
        GROUP BY contractid, itemcode
    """)
    ces_by_contract = run_query(f"""
        SELECT ContractID AS contractid, ItemCode AS itemcode,
               SUM(ActualQty)+SUM(BacklogQty) AS ces_qty, SUM(ActualPrice)+SUM(BacklogPrice) AS ces_value
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND ManuDivision='PEM101' AND RevenueType='Omni Channel'
          AND Status IN ('Actual','Backlog') AND CtrDate >= '2024-01-01'
        GROUP BY ContractID, ItemCode
    """)
    merged = apd_by_contract.merge(ces_by_contract, on=["contractid", "itemcode"], how="outer", indicator=True)
    merged.to_csv(os.path.join(SUMMARY_DIR, "part2_ces_vs_apd_contract_level.csv"), index=False)
    logger.info("Contract-item level merge: %s", merged["_merge"].value_counts().to_dict())

    matched = merged[merged["_merge"] == "both"].copy()
    matched["qty_diff"] = matched["apd_qty"] - matched["ces_qty"]
    n_exact = (matched["qty_diff"].abs() < 0.01).sum()
    logger.info("Of %d contract-item pairs present in BOTH sources, %d (%.1f%%) have exactly matching qty",
                len(matched), n_exact, n_exact / len(matched) * 100 if len(matched) else 0)

    print(f"\nContract-item pairs: only in cube_Sale_APD={(merged['_merge']=='left_only').sum()}, "
          f"only in Cube_CES={(merged['_merge']=='right_only').sum()}, in both={(merged['_merge']=='both').sum()}")
    print(f"Of pairs in both, exact qty match: {n_exact} of {len(matched)} ({n_exact/len(matched)*100:.1f}%)" if len(matched) else "no overlapping pairs")

    # ================= PART 3: pre-2024 Cube_CES characterization =================
    ces_yearly_pilot = run_query(f"""
        SELECT YEAR(CtrDate) AS yr, COUNT(*) AS n_rows,
               COUNT(CustomerID) AS n_customerid_nonnull, COUNT(ActualDelDate) AS n_actualdel_nonnull,
               COUNT(DISTINCT ContractID) AS n_contracts,
               SUM(ActualQty) AS total_actual_qty, SUM(BacklogQty) AS total_backlog_qty,
               SUM(ActualPrice) AS total_actual_price
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
        GROUP BY YEAR(CtrDate) ORDER BY yr
    """)
    ces_yearly_pilot.to_csv(os.path.join(SUMMARY_DIR, "part3_ces_pilot_yearly.csv"), index=False)
    print("\n=== PART 3: Cube_CES pilot-item rows by year ===")
    print(ces_yearly_pilot.to_string(index=False))

    # completeness of key columns, pre-2024 vs post-2024
    cols_to_check = ["CustomerID", "CustomerName", "ActualDelDate", "PlanDelDate", "ForecastDelDate",
                      "OLMJobCode", "JobName", "PlanID", "Status", "ContractPrice"]
    completeness_records = []
    for period, cond in [("pre-2024", "CtrDate < '2024-01-01'"), ("2024-plus", "CtrDate >= '2024-01-01'")]:
        total = run_query(f"SELECT COUNT(*) AS n FROM Cube_CES WHERE ItemCode IN ('{code_list}') AND {cond}")["n"].iloc[0]
        for col in cols_to_check:
            non_null = run_query(f"SELECT COUNT({col}) AS n FROM Cube_CES WHERE ItemCode IN ('{code_list}') AND {cond}")["n"].iloc[0]
            completeness_records.append({"period": period, "column": col, "pct_non_null": round(non_null/total*100, 1) if total else None})
    completeness_df = pd.DataFrame(completeness_records).pivot(index="column", columns="period", values="pct_non_null")
    completeness_df.to_csv(os.path.join(SUMMARY_DIR, "part3_ces_completeness_pre_post_2024.csv"))
    print("\n=== Column completeness: pre-2024 vs 2024+ (Cube_CES, 58 pilot items) ===")
    print(completeness_df.to_string())

    # Status distribution pre-2024 vs post-2024 for pilot items specifically
    status_by_period = run_query(f"""
        SELECT CASE WHEN CtrDate < '2024-01-01' THEN 'pre-2024' ELSE '2024-plus' END AS period,
               Status, COUNT(*) AS n
        FROM Cube_CES WHERE ItemCode IN ('{code_list}')
        GROUP BY CASE WHEN CtrDate < '2024-01-01' THEN 'pre-2024' ELSE '2024-plus' END, Status
        ORDER BY period, n DESC
    """)
    status_by_period.to_csv(os.path.join(SUMMARY_DIR, "part3_ces_status_pre_post_2024.csv"), index=False)
    print("\n=== Status distribution: pre-2024 vs 2024+ (58 pilot items) ===")
    print(status_by_period.to_string(index=False))
