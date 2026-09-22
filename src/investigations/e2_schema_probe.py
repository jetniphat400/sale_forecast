import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import run_query

CANDIDATES = ['Cube_Backlog', 'Cube_Backlog_PSP', 'Cube_Backlog_Snapshot', 'Cube_CES', 'Cube_Incoming_Receipt',
              'Cube_Incoming_Wait', 'Cube_Inventory_Aging', 'Cube_Inventory_Aging_PSL', 'Cube_Inventory_Batch',
              'Cube_Inventory_Exact', 'Cube_Inventory_Exact_PPD', 'Cube_Invoice_PSP', 'Cube_OQ',
              'Cube_PMIS_Invoice', 'Cube_PO_Exact', 'Cube_Production_Control', 'Cube_Quotation',
              'Cube_Quotation_PSP', 'Cube_Sale_APD_2', 'Cube_pr_monitoring', 'Cube_production',
              'Cube_tobe_received', 'cube_Revunue', 'cube_Sale', 'cube_Sale_APD', 'cube_Sale_APD_2016',
              'cube_Sale_APD_snapshot', 'cube_Sale_APD_test', 'cube_Sale_PSP', 'cube_Sale_PSP_API',
              'cube_Sale_Snapshot', 'cube_cus_complaint', 'cube_final', 'cube_inventory_tran',
              'cube_pl_erp_transaction', 'cube_pl_erp_transaction_temp', 'cube_po', 'cube_po_bom',
              'cube_pr_bom', 'cube_revenue', 'information_state']

in_list = "','".join(CANDIDATES)
sql = ("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
       f"WHERE TABLE_NAME IN ('{in_list}') ORDER BY TABLE_NAME, ORDINAL_POSITION")
cols = run_query(sql)
out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "output", "summary", "e2_candidate_table_columns.csv")
cols.to_csv(out_path, index=False)
print("rows:", len(cols))
print(cols.groupby("TABLE_NAME")["COLUMN_NAME"].apply(lambda s: ", ".join(s)).to_string())
