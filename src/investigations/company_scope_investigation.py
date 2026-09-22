"""Read-only investigation: company scope for a "Reserved" column next to on-hand qty.

Cube_Backlog carries both `company` (observed to look like customer names) and `sale_company`
(observed to look like selling-entity codes: PEM/PDE/PEMC/PPS/PSS/PTS/CI etc.) -- different from
each other and from `sale_division`. Cube_Inventory_Exact.company has only PEM/CI as of the last
check. This script establishes what company scope the two sources actually share, and whether the
Inventory panel's current unfiltered on-hand figure is equivalent to PEM+CI or includes something
else. See output/summary/company_scope_investigation_report.md for the write-up.

Does NOT modify index.html, data/inventory.json, or build_inventory_dataset.py. Does not commit.
Live tables -- re-running will not reproduce identical figures. Run against a snapshot taken
2026-09-10.
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
    return df[["code", "division"]]


def query_backlog_full() -> pd.DataFrame:
    return run_query("""
        SELECT id, docID, itemcode, quantity, status, viewType, deliverydate, plan_deliverydate,
               receivedate, division, sale_division, company, sale_company, customer, endcustomer,
               manufacturing_type, revenue_type, product_type, product_cateogory, timestamp
        FROM [salewarehouse].[dbo].[Cube_Backlog]
    """)


def query_inventory_full() -> pd.DataFrame:
    return run_query("""
        SELECT company, warehouse, itemcode, stock, timestamp
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
    """)


def query_company_reference_tables() -> pd.DataFrame:
    return run_query("""
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE LOWER(TABLE_NAME) LIKE '%compan%' OR LOWER(TABLE_NAME) LIKE '%organi%'
           OR LOWER(TABLE_NAME) LIKE '%entity%' OR LOWER(TABLE_NAME) LIKE '%legal%'
        ORDER BY TABLE_NAME, COLUMN_NAME
    """)


def query_sale_company_in_other_cubes() -> pd.DataFrame:
    """Which other tables have a sale_company-like or company-like column at all."""
    return run_query("""
        SELECT TABLE_NAME, COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE LOWER(COLUMN_NAME) IN ('company', 'sale_company', 'division', 'sale_division')
        ORDER BY TABLE_NAME, COLUMN_NAME
    """)


def query_sale_apd_company_check(entity_codes: list) -> pd.DataFrame:
    """Does cube_Sale_APD (or Cube_CES) carry any of these entity codes anywhere?"""
    code_list = "','".join(entity_codes)
    out = {}
    for tbl, cols_to_try in [
        ("cube_Sale_APD", ["division", "company"]),
        ("Cube_CES", ["division", "company"]),
        ("cube_Contract", ["division", "company", "sale_company"]),
    ]:
        cols = run_query(f"""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{tbl}'
        """)["COLUMN_NAME"].str.lower().tolist()
        present = [c for c in cols_to_try if c.lower() in cols]
        out[tbl] = present
    return out


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    registry = load_registry()
    codes = sorted(registry["code"].unique())
    print(f"Registry: {len(codes)} codes")

    # ================= PART 1 =================
    bl = query_backlog_full()
    bl.to_csv(os.path.join(OUT, "company_scope_backlog_full.csv"), index=False)
    print(f"\nCube_Backlog full table: {len(bl)} rows")

    # 1a: company vs sale_company agreement
    bl["company_norm"] = bl["company"].astype(str).str.strip()
    bl["sale_company_norm"] = bl["sale_company"].astype(str).str.strip()
    n_equal = int((bl["company_norm"] == bl["sale_company_norm"]).sum())
    print(f"1a: company == sale_company on {n_equal}/{len(bl)} rows ({n_equal/len(bl)*100:.1f}%)")

    company_vals = bl["company_norm"].value_counts()
    sale_company_vals = set(bl["sale_company_norm"].unique())
    company_not_in_sale_company = company_vals[~company_vals.index.isin(sale_company_vals)]
    print(f"1a: distinct `company` values NOT present anywhere in `sale_company`: "
          f"{len(company_not_in_sale_company)} of {bl['company_norm'].nunique()} distinct company values")
    print(company_not_in_sale_company.head(20).to_string())

    # relate company to customer/endcustomer
    sample_mismatch = bl[bl["company_norm"] != bl["sale_company_norm"]][
        ["company", "sale_company", "customer", "endcustomer", "sale_division"]].head(15)
    print("\n1a sample rows where company != sale_company (vs customer/endcustomer):")
    print(sample_mismatch.to_string())

    match_company_customer = int((bl["company_norm"] == bl["customer"].astype(str).str.strip()).sum())
    match_company_endcustomer = int((bl["company_norm"] == bl["endcustomer"].astype(str).str.strip()).sum())
    print(f"\n1a: `company` == `customer` on {match_company_customer}/{len(bl)} rows")
    print(f"1a: `company` == `endcustomer` on {match_company_endcustomer}/{len(bl)} rows")
    print(f"1a: distinct `company` values: {bl['company_norm'].nunique()}, "
          f"distinct `customer` values: {bl['customer'].astype(str).str.strip().nunique()}")

    # 1b: full sale_company breakdown
    sale_company_summary = bl.groupby("sale_company_norm").agg(
        n_rows=("id", "count"),
        outstanding_qty=("quantity", "sum"),
        n_distinct_itemcodes=("itemcode", "nunique"),
    ).reset_index().rename(columns={"sale_company_norm": "sale_company"})
    sale_company_summary = sale_company_summary.sort_values("n_rows", ascending=False)
    print("\n1b: sale_company breakdown:")
    print(sale_company_summary.to_string())
    sale_company_summary.to_csv(os.path.join(OUT, "company_scope_sale_company_summary.csv"), index=False)

    # 1c: per sale_company, registry membership of its itemcodes
    rows_1c = []
    for sc, grp in bl.groupby("sale_company_norm"):
        distinct_codes = set(grp["itemcode"].dropna().unique())
        in_reg = len(distinct_codes & set(codes))
        out_reg = len(distinct_codes) - in_reg
        rows_1c.append({"sale_company": sc, "n_distinct_itemcodes": len(distinct_codes),
                         "in_445_registry": in_reg, "not_in_445_registry": out_reg})
    df_1c = pd.DataFrame(rows_1c).sort_values("in_445_registry", ascending=False)
    print("\n1c: sale_company x registry membership:")
    print(df_1c.to_string())
    df_1c.to_csv(os.path.join(OUT, "company_scope_sale_company_registry_membership.csv"), index=False)

    # ================= PART 2 =================
    inv = query_inventory_full()
    inv["company_norm"] = inv["company"].astype(str).str.strip()
    inv.to_csv(os.path.join(OUT, "company_scope_inventory_full_summary.csv"), index=False)
    print(f"\nCube_Inventory_Exact full table: {len(inv)} rows, "
          f"distinct company values: {sorted(inv['company_norm'].unique())}")

    # 2a: per company breakdown
    rows_2a = []
    for comp, grp in inv.groupby("company_norm"):
        distinct_codes = set(grp["itemcode"].dropna().unique())
        in_reg = len(distinct_codes & set(codes))
        rows_2a.append({"company": comp, "n_rows": len(grp), "n_distinct_itemcodes": len(distinct_codes),
                         "n_in_445_registry": in_reg})
    df_2a = pd.DataFrame(rows_2a)
    print("\n2a: Cube_Inventory_Exact per company:")
    print(df_2a.to_string())

    # 2b: is registry stock fully contained in PEM+CI?
    reg_inv = inv[inv["itemcode"].isin(codes)]
    reg_companies = sorted(reg_inv["company_norm"].unique())
    print(f"\n2b: company values present for the 445-registry's stock rows: {reg_companies}")
    non_pem_ci = reg_inv[~reg_inv["company_norm"].isin(["PEM", "CI"])]
    print(f"2b: registry rows under a company OTHER than PEM/CI: {len(non_pem_ci)}")
    if len(non_pem_ci):
        print(non_pem_ci.to_string())

    all_companies_tablewide = sorted(inv["company_norm"].unique())
    unfiltered_equals_pem_ci = set(all_companies_tablewide) <= {"PEM", "CI"}
    print(f"2b: ALL company values table-wide: {all_companies_tablewide}")
    print(f"2b: unfiltered on-hand == PEM+CI only (no other company exists table-wide)? "
          f"{unfiltered_equals_pem_ci}")

    # 2c: per sale_company, split backlog qty by whether the code has ANY stock row in Cube_Inventory_Exact
    inv_codes_with_any_row = set(inv["itemcode"].dropna().unique())
    rows_2c = []
    for sc, grp in bl.groupby("sale_company_norm"):
        has_stock_row = grp[grp["itemcode"].isin(inv_codes_with_any_row)]
        no_stock_row = grp[~grp["itemcode"].isin(inv_codes_with_any_row)]
        rows_2c.append({
            "sale_company": sc,
            "qty_codes_with_stock_row": has_stock_row["quantity"].sum(),
            "qty_codes_no_stock_row": no_stock_row["quantity"].sum(),
            "n_codes_with_stock_row": has_stock_row["itemcode"].nunique(),
            "n_codes_no_stock_row": no_stock_row["itemcode"].nunique(),
        })
    df_2c = pd.DataFrame(rows_2c).sort_values("qty_codes_with_stock_row", ascending=False)
    print("\n2c: sale_company backlog qty split by stock-row existence in Cube_Inventory_Exact:")
    print(df_2c.to_string())
    df_2c.to_csv(os.path.join(OUT, "company_scope_2c_stock_row_split.csv"), index=False)

    # ================= PART 3 =================
    meaningful = sale_company_summary[sale_company_summary["n_rows"] >= 5]["sale_company"].tolist()
    print(f"\n3a: sale_company values with >=5 rows (meaningful volume): {meaningful}")
    mix_cols = ["division", "product_type", "product_cateogory", "manufacturing_type", "revenue_type"]
    for sc in meaningful:
        sub = bl[bl["sale_company_norm"] == sc]
        print(f"\n--- {sc} (n={len(sub)}) product mix ---")
        for col in mix_cols:
            print(f"  {col}: {sub[col].value_counts().head(6).to_dict()}")

    # 3b: reference tables for company/org codes
    ref_tables = query_company_reference_tables()
    print(f"\n3b: tables with 'compan'/'organi'/'entity'/'legal' in the name: "
          f"{ref_tables['TABLE_NAME'].unique().tolist() if len(ref_tables) else 'NONE FOUND'}")
    if len(ref_tables):
        print(ref_tables.to_string())

    company_cols_everywhere = query_sale_company_in_other_cubes()
    print("\n3b: every table with a company/sale_company/division/sale_division-named column:")
    print(company_cols_everywhere.to_string())

    entity_codes = [c for c in sale_company_summary["sale_company"].tolist() if c and c != "nan"]
    presence = query_sale_apd_company_check(entity_codes)
    print(f"\n3b: relevant company-ish columns present in cube_Sale_APD/Cube_CES/cube_Contract: {presence}")

    print("\nDone. See output/summary/company_scope_investigation_report.md for full write-up.")
