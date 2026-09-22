"""Read-only investigation: is outstanding backlog a defensible source for a "Reserved" column
next to on-hand qty (Cube_Inventory_Exact) for the 445-code pricelist registry, or is there a
better source? See output/summary/reserved_available_investigation_report.md for the write-up.

Does NOT modify index.html, data/inventory.json, or build_inventory_dataset.py. Does not commit.
Re-running will not reproduce identical figures -- cube_Sale_APD/Cube_Backlog/Cube_Inventory_Exact
are live tables that refresh daily; this script was run against a snapshot taken 2026-09-10.
"""
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(PROJECT_ROOT, "output", "summary")


def load_registry() -> pd.DataFrame:
    config = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))
    df = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    df = df.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    df["division"] = df["sheet"].map(config["sheet_to_division"])
    return df


def part1_candidate_tables():
    tables = run_query("""
        SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME
    """)
    keyword_cols = run_query("""
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE LOWER(COLUMN_NAME) LIKE '%reserv%' OR LOWER(COLUMN_NAME) LIKE '%alloc%'
           OR LOWER(COLUMN_NAME) LIKE '%backlog%' OR LOWER(COLUMN_NAME) LIKE '%commit%'
           OR LOWER(COLUMN_NAME) LIKE '%avail%'
        ORDER BY TABLE_NAME, COLUMN_NAME
    """)
    return tables, keyword_cols


def part1c_inventory_exact_reservation_field():
    cols = run_query("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'Cube_Inventory_Exact' ORDER BY ORDINAL_POSITION
    """)
    formula_check = run_query("""
        SELECT
          SUM(CASE WHEN ABS((stock - reserve_bywa + tobe_received) - available) < 0.01 THEN 1 ELSE 0 END) n_match,
          COUNT(*) n
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
    """)
    return cols, formula_check


def part2_backlog_table(codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(codes))
    return run_query(f"""
        SELECT id, docID, itemcode, quantity, status, deliverydate, plan_deliverydate,
               receivedate, division, sale_division, company, timestamp
        FROM [salewarehouse].[dbo].[Cube_Backlog]
        WHERE itemcode IN ('{code_list}')
    """)


def part3_inventory(codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(codes))
    df = run_query(f"""
        SELECT company, warehouse, itemcode, unit, stock, reserve_bywa, available, timestamp
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
        WHERE itemcode IN ('{code_list}')
    """)
    df["warehouse"] = df["warehouse"].str.strip()
    return df


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    registry = load_registry()
    codes = sorted(registry["code"].unique())

    tables, keyword_cols = part1_candidate_tables()
    print(f"{len(tables)} tables/views total. Reservation/backlog/available-keyword columns:")
    print(keyword_cols.to_string())

    cols, formula = part1c_inventory_exact_reservation_field()
    print("\nCube_Inventory_Exact columns:", cols["COLUMN_NAME"].tolist())
    print("available == stock - reserve_bywa + tobe_received match:", formula.to_string())

    bl = part2_backlog_table(codes)
    bl.to_csv(os.path.join(OUT, "reserved_available_backlog445_rows.csv"), index=False)
    print(f"\nCube_Backlog rows for 445-registry codes: {len(bl)}, distinct codes: {bl['itemcode'].nunique()}")

    inv = part3_inventory(codes)
    inv.to_csv(os.path.join(OUT, "reserved_available_inventory445_rows.csv"), index=False)

    bl_agg = bl.groupby("itemcode", as_index=False)["quantity"].sum().rename(
        columns={"itemcode": "code", "quantity": "backlog_qty"})
    inv_agg = inv.groupby("itemcode", as_index=False).agg(
        onhand=("stock", "sum"), reserve_bywa=("reserve_bywa", "sum")).rename(columns={"itemcode": "code"})

    joined = registry[["code", "division"]].merge(inv_agg, on="code", how="left").merge(bl_agg, on="code", how="left")
    joined[["onhand", "reserve_bywa", "backlog_qty"]] = joined[["onhand", "reserve_bywa", "backlog_qty"]].fillna(0)
    joined["net_onhand_minus_backlog"] = joined["onhand"] - joined["backlog_qty"]
    joined.to_csv(os.path.join(OUT, "reserved_available_join445.csv"), index=False)

    print(f"\nCodes with backlog > 0: {(joined['backlog_qty'] > 0).sum()} / {len(joined)}")
    print(f"Codes with net < 0: {(joined['net_onhand_minus_backlog'] < 0).sum()}")
    print(f"Total net across 445 codes: {joined['net_onhand_minus_backlog'].sum()}")
    print("\nDone. See output/summary/reserved_available_investigation_report.md for full write-up.")
