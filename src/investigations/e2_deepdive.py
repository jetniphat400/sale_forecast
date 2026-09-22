import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import run_query
from pricelist_reader import load_visible_product_rows
from division_utils import assert_no_code_on_multiple_sheets

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
config = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))

pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
assert_no_code_on_multiple_sheets(pl)
pl = pl.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
pl["division"] = pl["sheet"].map(config["sheet_to_division"])
scope = pl[pl["division"].isin(["PEM102", "PEM103", "PEM107", "CI101", "PEM104"])][["code", "division"]].rename(columns={"code": "itemcode"})
codes = sorted(scope["itemcode"].unique())
code_list = "','".join(codes)

print("=" * 90)
print("DEEP DIVE 1: Cube_Inventory_Aging -- full detail, per-division/warehouse breakdown")
print("=" * 90)
aging = run_query(f"""
    SELECT ID, Company, Warehouse, ItemCode, Assortment, Condition, Type, ItemStatus,
           Stock, FreeStock, GLAccount, GLDescription, CostPriceStandard, Amount, Division,
           Timestamp
    FROM [salewarehouse].[dbo].[Cube_Inventory_Aging]
    WHERE ItemCode IN ('{code_list}')
""")
aging["Warehouse"] = aging["Warehouse"].astype(str).str.strip()
aging["Company"] = aging["Company"].astype(str).str.strip()
aging["Division"] = aging["Division"].astype(str).str.strip()
aging.to_csv(os.path.join(SUMMARY_DIR, "phaseE2_3_cube_inventory_aging_full.csv"), index=False)
print(f"Total rows: {len(aging)}, distinct items: {aging['ItemCode'].nunique()}")
print(f"Timestamp range: {aging['Timestamp'].min()} to {aging['Timestamp'].max()} "
      f"(distinct timestamps: {aging['Timestamp'].nunique()})")
print(f"\nDistinct Company values: {sorted(aging['Company'].unique())}")
print(f"Distinct Division values (DB column, reference only per CONVENTIONS.md): {sorted(aging['Division'].unique())}")
print(f"Distinct Condition values: {sorted(aging['Condition'].dropna().unique())}")
print(f"Distinct ItemStatus values: {sorted(aging['ItemStatus'].dropna().unique())}")
print(f"Distinct GLDescription values: {sorted(aging['GLDescription'].dropna().unique())}")
print(f"\nWarehouse code universe in this table for these items: {sorted(aging['Warehouse'].unique())}")

nonzero = aging[aging["Stock"] != 0].merge(scope, left_on="ItemCode", right_on="itemcode", how="left")
print(f"\nNonzero-Stock rows: {len(nonzero)}, distinct items: {nonzero['ItemCode'].nunique()}")
cross = nonzero.groupby(["division", "Warehouse"], as_index=False).agg(
    n_items=("ItemCode", "nunique"), qty=("Stock", "sum"))
cross = cross.sort_values(["division", "qty"], ascending=[True, False])
cross.to_csv(os.path.join(SUMMARY_DIR, "phaseE2_3_aging_division_warehouse_crosstab.csv"), index=False)
print("\nDivision x Warehouse cross-tab (Cube_Inventory_Aging, pricelist division, nonzero Stock):")
print(cross.to_string(index=False))

# Cross-check: for items with stock in Aging but ZERO in Cube_Inventory_Exact, confirm directly
exact = run_query(f"""
    SELECT itemcode, warehouse, stock FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
    WHERE itemcode IN ('{code_list}')
""")
exact["warehouse"] = exact["warehouse"].astype(str).str.strip()
exact_nonzero_items = set(exact.loc[exact["stock"] != 0, "itemcode"])
aging_nonzero_items = set(nonzero["ItemCode"])
only_in_aging = aging_nonzero_items - exact_nonzero_items
print(f"\nItems with nonzero stock in Cube_Inventory_Aging but ZERO (or absent) in Cube_Inventory_Exact: "
      f"{len(only_in_aging)} of {len(aging_nonzero_items)} aging-stocked items")
sample = nonzero[nonzero["ItemCode"].isin(only_in_aging)][
    ["ItemCode", "division", "Warehouse", "Stock", "FreeStock", "Company", "Timestamp"]].sort_values("Stock", ascending=False)
sample.to_csv(os.path.join(SUMMARY_DIR, "phaseE2_3_aging_only_items_detail.csv"), index=False)
print(sample.head(20).to_string(index=False))

print("\n" + "=" * 90)
print("DEEP DIVE 2: information_state -- classify what this table actually is")
print("=" * 90)
info_sample = run_query(f"""
    SELECT TOP 30 * FROM [salewarehouse].[dbo].[information_state]
    WHERE itemcode IN ('{code_list}')
    ORDER BY forecast_date DESC
""")
print("Sample rows (top 30 by forecast_date desc):")
print(info_sample.to_string(index=False))

info_agg = run_query(f"""
    SELECT state, product_status, COUNT(*) n_rows, COUNT(DISTINCT itemcode) n_items,
           MIN(forecast_date) min_fd, MAX(forecast_date) max_fd, SUM(quantity) sum_qty
    FROM [salewarehouse].[dbo].[information_state]
    WHERE itemcode IN ('{code_list}')
    GROUP BY state, product_status
    ORDER BY n_rows DESC
""")
info_agg.to_csv(os.path.join(SUMMARY_DIR, "phaseE2_3_information_state_agg.csv"), index=False)
print("\nAggregated by (state, product_status):")
print(info_agg.to_string(index=False))
