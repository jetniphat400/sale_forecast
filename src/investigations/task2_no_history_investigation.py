"""Task 2 (Explorer+Validator, parallel agent) -- investigate the 31 no-history/no-sale
items claim for the 128-item Fuse/Surge Arrester category scope.

Ad hoc investigation script (not part of the permanent pipeline). Writes every raw
query result to output/summary/task2_*.csv so every claim in the final report can be
traced back to an exact query result. Never modifies STATUS.md or git.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

SOURCE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
DIVISION = "PEM101"
REVENUE_TYPE = "Omni Channel"
STATUSES = ["Actual", "MPS"]
START_DATE = "2024-01-01"


def get_scope_codes():
    df = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    return sorted(df["code"].unique()), df


def code_list_sql(codes):
    return "','".join(codes)


if __name__ == "__main__":
    codes, scope_df = get_scope_codes()
    print(f"Scope: {len(codes)} item codes (output/summary/part1_category_scope_all_codes.csv)")
    cl = code_list_sql(codes)

    # ================================================================
    # Q1: Under the STANDARD project filter (division=PEM101, revenue_type=Omni
    # Channel, status IN Actual/MPS, createDate >= 2024-01-01) -- per item,
    # row count and sum(qty)/sum(sale).
    # ================================================================
    q1 = f"""
        SELECT itemcode, COUNT(*) AS n_rows_std_filter,
               SUM(qty) AS sum_qty_std_filter, SUM(sale) AS sum_sale_std_filter,
               MIN(createDate) AS min_createdate, MAX(createDate) AS max_createdate
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{cl}')
          AND division = '{DIVISION}'
          AND revenue_type = '{REVENUE_TYPE}'
          AND status IN ('{"','".join(STATUSES)}')
          AND createDate >= '{START_DATE}'
        GROUP BY itemcode
    """
    df1 = run_query(q1)
    df1.to_csv(os.path.join(SUMMARY_DIR, "task2_q1_std_filter_per_item.csv"), index=False)
    print(f"Q1: {len(df1)} of {len(codes)} items have >=1 row under the standard filter")

    # ================================================================
    # Q2: ANY activity anywhere in cube_Sale_APD -- no filter at all (any
    # division, any revenue_type, any status, any date) -- per item.
    # ================================================================
    q2 = f"""
        SELECT itemcode, COUNT(*) AS n_rows_any,
               SUM(qty) AS sum_qty_any, SUM(sale) AS sum_sale_any,
               MIN(createDate) AS min_createdate_any, MAX(createDate) AS max_createdate_any,
               COUNT(DISTINCT division) AS n_distinct_divisions,
               COUNT(DISTINCT revenue_type) AS n_distinct_revenue_types,
               COUNT(DISTINCT status) AS n_distinct_statuses
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{cl}')
        GROUP BY itemcode
    """
    df2 = run_query(q2)
    df2.to_csv(os.path.join(SUMMARY_DIR, "task2_q2_any_activity_per_item.csv"), index=False)
    print(f"Q2: {len(df2)} of {len(codes)} items have >=1 row ANYWHERE in {SOURCE_TABLE} (no filter)")

    # ================================================================
    # Q2b: for items with ANY activity but NOT under the std filter, what
    # divisions/revenue_types/statuses do their rows actually carry?
    # ================================================================
    q2b = f"""
        SELECT itemcode, division, revenue_type, status, COUNT(*) AS n_rows,
               SUM(qty) AS sum_qty, SUM(sale) AS sum_sale,
               MIN(createDate) AS min_createdate, MAX(createDate) AS max_createdate
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{cl}')
        GROUP BY itemcode, division, revenue_type, status
        ORDER BY itemcode, division, revenue_type, status
    """
    df2b = run_query(q2b)
    df2b.to_csv(os.path.join(SUMMARY_DIR, "task2_q2b_any_activity_breakdown.csv"), index=False)
    print(f"Q2b: {len(df2b)} (itemcode,division,revenue_type,status) breakdown rows written")

    # ================================================================
    # Q3: Cube_CES -- any row at all (Actual or Backlog), per item.
    # ================================================================
    q3 = f"""
        SELECT ItemCode AS itemcode, COUNT(*) AS n_rows_ces,
               SUM(CASE WHEN Status = 'Backlog' THEN 1 ELSE 0 END) AS n_backlog_rows,
               SUM(CASE WHEN Status = 'Actual' THEN 1 ELSE 0 END) AS n_actual_rows,
               SUM(BacklogQty) AS sum_backlog_qty,
               SUM(ActualQty) AS sum_actual_qty,
               MIN(CtrDate) AS min_ctrdate, MAX(CtrDate) AS max_ctrdate,
               COUNT(DISTINCT ManuDivision) AS n_distinct_manu_division,
               COUNT(DISTINCT SaleDivision) AS n_distinct_sale_division
        FROM [salewarehouse].[dbo].[Cube_CES]
        WHERE ItemCode IN ('{cl}')
        GROUP BY ItemCode
    """
    df3 = run_query(q3)
    df3.to_csv(os.path.join(SUMMARY_DIR, "task2_q3_cube_ces_per_item.csv"), index=False)
    print(f"Q3: {len(df3)} of {len(codes)} items have >=1 row in Cube_CES")

    # ================================================================
    # Q3b: distinct Status values present in Cube_CES table-wide (sanity check
    # that 'Backlog' really is the open/pending status value, per STATUS.md).
    # ================================================================
    q3b = "SELECT DISTINCT Status FROM [salewarehouse].[dbo].[Cube_CES]"
    df3b = run_query(q3b)
    df3b.to_csv(os.path.join(SUMMARY_DIR, "task2_q3b_cube_ces_distinct_status.csv"), index=False)
    print(f"Q3b: Cube_CES distinct Status values: {df3b['Status'].tolist()}")

    # ================================================================
    # Q4: cube_inventory_tran -- any row at all, per item.
    # ================================================================
    q4 = f"""
        SELECT itemcode, COUNT(*) AS n_rows_inv_tran,
               SUM(QtyIn) AS sum_qty_in, SUM(QtyOut) AS sum_qty_out,
               MIN(trans_date) AS min_trans_date, MAX(trans_date) AS max_trans_date,
               COUNT(DISTINCT transtype) AS n_distinct_transtypes
        FROM [salewarehouse].[dbo].[cube_inventory_tran]
        WHERE itemcode IN ('{cl}')
        GROUP BY itemcode
    """
    df4 = run_query(q4)
    df4.to_csv(os.path.join(SUMMARY_DIR, "task2_q4_inventory_tran_per_item.csv"), index=False)
    print(f"Q4: {len(df4)} of {len(codes)} items have >=1 row in cube_inventory_tran")

    # ================================================================
    # Q5: Cube_Inventory_Exact -- current stock snapshot, per item (per
    # STATUS.md, single timestamp table -- take all rows, could be >1 per
    # item if multiple warehouses).
    # ================================================================
    q5 = f"""
        SELECT itemcode, warehouse, stock, freestock, tobe_received, reserve_bywa,
               available, timestamp, minimum, maximum
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
        WHERE itemcode IN ('{cl}')
        ORDER BY itemcode, warehouse
    """
    df5 = run_query(q5)
    df5.to_csv(os.path.join(SUMMARY_DIR, "task2_q5_inventory_exact_per_item.csv"), index=False)
    print(f"Q5: {len(df5)} rows (item x warehouse) in Cube_Inventory_Exact; "
          f"{df5['itemcode'].nunique() if len(df5) else 0} of {len(codes)} distinct items have a stock row")

    # ================================================================
    # Q6: Cube_Quotation -- any row at all, per item.
    # ================================================================
    q6 = f"""
        SELECT itemcode, COUNT(*) AS n_rows_quotation,
               SUM(quantity) AS sum_quantity,
               MIN(create_date) AS min_create_date, MAX(create_date) AS max_create_date,
               COUNT(DISTINCT quotation_status) AS n_distinct_quotation_status,
               COUNT(DISTINCT division) AS n_distinct_divisions
        FROM [salewarehouse].[dbo].[Cube_Quotation]
        WHERE itemcode IN ('{cl}')
        GROUP BY itemcode
    """
    df6 = run_query(q6)
    df6.to_csv(os.path.join(SUMMARY_DIR, "task2_q6_quotation_per_item.csv"), index=False)
    print(f"Q6: {len(df6)} of {len(codes)} items have >=1 row in Cube_Quotation")

    # ================================================================
    # Q6b: distinct quotation_status values (sanity check for "open quotation").
    # ================================================================
    q6b = "SELECT DISTINCT quotation_status FROM [salewarehouse].[dbo].[Cube_Quotation]"
    df6b = run_query(q6b)
    df6b.to_csv(os.path.join(SUMMARY_DIR, "task2_q6b_quotation_distinct_status.csv"), index=False)
    print(f"Q6b: Cube_Quotation distinct quotation_status values: {df6b['quotation_status'].tolist()}")

    print("\nAll raw query results written to output/summary/task2_q*.csv")
