"""Phase J3 — Explorer BOM. Single-connection pull for Cube_BOM_Exact content,
coverage of the 351-item scope, component/quantity sample, and join-verification
against Cube_Inventory_Exact (both directions).

CONVENTIONS.md/AGENTS.md rule: ONE connection attempt for this whole task. Every
query below reuses the same engine. If the connection fails, this script raises
and the task stops — no retry.
"""
import sys
import os

sys.path.insert(0, "src")
from db import get_connection  # noqa: E402

import pandas as pd  # noqa: E402

SUMMARY_DIR = "output/summary"
os.makedirs(SUMMARY_DIR, exist_ok=True)

scope = pd.read_csv("output/data/phaseI_combined_scope_351items.csv")
scope_codes = scope["code"].astype(str).str.strip().tolist()
print(f"Scope: {len(scope_codes)} items loaded from phaseI_combined_scope_351items.csv")


def code_list_sql(codes):
    escaped = [c.replace("'", "''") for c in codes]
    return ",".join(f"'{c}'" for c in escaped)


engine = get_connection()
with engine.connect() as conn:
    # 1. Schema / structure
    print("\n=== STEP 1: SELECT TOP 5 * FROM Cube_BOM_Exact ===")
    top5 = pd.read_sql("SELECT TOP 5 * FROM Cube_BOM_Exact", conn)
    print(top5.to_string())
    top5.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_top5_raw.csv", index=False)

    print("\n=== STEP 1b: INFORMATION_SCHEMA.COLUMNS for Cube_BOM_Exact ===")
    cols = pd.read_sql(
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Cube_BOM_Exact' "
        "ORDER BY ORDINAL_POSITION",
        conn,
    )
    print(cols.to_string())
    cols.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_schema.csv", index=False)

    print("\n=== STEP 1c: total row count, distinct ItemFG count (table-wide) ===")
    counts = pd.read_sql(
        "SELECT COUNT(*) AS n_rows, COUNT(DISTINCT ItemFG) AS n_distinct_itemfg "
        "FROM Cube_BOM_Exact",
        conn,
    )
    print(counts.to_string())
    counts.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_tablewide_counts.csv", index=False)

    # 2. Coverage of the 351-item scope + full BOM pull for scope
    print("\n=== STEP 2: BOM rows for the 351-item scope ===")
    scope_sql = code_list_sql(scope_codes)
    bom_scope = pd.read_sql(
        f"SELECT * FROM Cube_BOM_Exact WHERE ItemFG IN ({scope_sql})", conn
    )
    print(f"Rows returned: {len(bom_scope)}; distinct ItemFG in result: {bom_scope['ItemFG'].nunique() if len(bom_scope) else 0}")
    bom_scope.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_scope_raw_pull.csv", index=False)

    matched_itemfg = set(bom_scope["ItemFG"].astype(str).str.strip()) if len(bom_scope) else set()
    scope["code_stripped"] = scope["code"].astype(str).str.strip()
    scope["has_bom"] = scope["code_stripped"].isin(matched_itemfg)
    coverage_by_division = (
        scope.groupby("division")["has_bom"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "n_with_bom", "count": "n_items"})
    )
    coverage_by_division["pct"] = (100 * coverage_by_division["n_with_bom"] / coverage_by_division["n_items"]).round(1)
    print("\n=== STEP 2b: BOM coverage of the 351-item scope, per division ===")
    print(coverage_by_division.to_string())
    coverage_by_division.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_coverage_by_division.csv")
    scope[["code", "division", "type", "category", "has_bom"]].to_csv(
        f"{SUMMARY_DIR}/phaseJ3_explorerBOM_coverage_per_item.csv", index=False
    )

    # 3. Sample for the 16 fast-zero-onhand items from Phase J2 Explorer C
    fast_zero = pd.read_csv("output/summary/phaseJ2_explorerC_fast_zero_onhand_items.csv")
    fast_zero_codes = fast_zero["ItemCode"].astype(str).str.strip().tolist()
    print(f"\n=== STEP 3: BOM rows for the 16 Phase J2 Explorer C fast+zero-onhand items ===")
    fz_sql = code_list_sql(fast_zero_codes)
    bom_fastzero = pd.read_sql(
        f"SELECT * FROM Cube_BOM_Exact WHERE ItemFG IN ({fz_sql})", conn
    )
    print(f"Rows returned: {len(bom_fastzero)}; distinct ItemFG matched: {bom_fastzero['ItemFG'].nunique() if len(bom_fastzero) else 0} of {len(fast_zero_codes)}")
    bom_fastzero.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_16items_pull.csv", index=False)

    # Determine the likely component-code column name from the schema pull
    col_names = cols["COLUMN_NAME"].tolist()
    print(f"\nColumns available: {col_names}")

    qty_candidates = [c for c in col_names if any(k in c.lower() for k in ("qty", "quantity", "amount", "usage"))]
    print(f"Candidate quantity columns: {qty_candidates}")
    qty_col = qty_candidates[0] if qty_candidates else None

    # Component-code candidates: any item/material/component/part/rm-like column that is not ItemFG
    candidate_component_cols = [
        c for c in col_names
        if c != "ItemFG" and c not in qty_candidates
        and any(k in c.lower() for k in ("item", "comp", "material", "part", "rm", "sku", "code"))
    ]
    print(f"Candidate component-code columns: {candidate_component_cols}")

    component_col = None
    for cand in ["ItemRawmat", "ItemComponent", "ItemRM", "ComponentCode", "ItemCode", "Component", "PartCode", "ItemRaw", "RMCode", "Material"]:
        if cand in col_names:
            component_col = cand
            break
    if component_col is None and candidate_component_cols:
        component_col = candidate_component_cols[0]
    print(f"Using component_col = {component_col!r}, qty_col = {qty_col!r} for downstream analysis")

    # STEP 3b (confirmed from data, not a header-row artifact): Sequenceno=0 rows have
    # ItemRawmat = NULL and Quantity = 1 in every case observed -- this is the FG item's
    # own top-level assembly header line, not a component. Real component lines are
    # Sequenceno >= 1. Also split Type: 'Standard' = genuine material/component code,
    # 'Machine Hour' (observed codes like 'B101-OH1', 'B101-DL1', '105-OVERHEAD') = labor/
    # overhead cost-allocation lines, not stock items -- confirmed these never appear as
    # real component stock by inspecting the distinct code list (pattern: OVERHEAD/DL/OH
    # suffixes, no itemcode-like structure).
    if len(bom_scope) and component_col:
        bom_scope["_seq"] = pd.to_numeric(bom_scope["Sequenceno"], errors="coerce")
        header_rows = bom_scope[bom_scope["_seq"] == 0]
        component_rows = bom_scope[bom_scope["_seq"] >= 1].copy()
        print(f"\n=== STEP 3b: header vs. component rows ===")
        print(f"{len(header_rows)} header rows (Sequenceno=0, {component_col} null in "
              f"{header_rows[component_col].isna().sum()}/{len(header_rows)} of them, "
              f"Quantity always 1: {(header_rows['Quantity'] == 1).all()})")
        print(f"{len(component_rows)} genuine component-line rows (Sequenceno>=1)")
        print(component_rows["Type"].value_counts().to_string())
        component_rows.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_scope_component_lines_only.csv", index=False)

    # Grain check: does (ItemFG, component_col) repeat? does ItemFG alone repeat (expected: yes, one row
    # per component)? Report both, using the scope pull.
    if len(bom_scope):
        n_rows = len(bom_scope)
        n_distinct_itemfg = bom_scope["ItemFG"].nunique()
        print(f"\n=== GRAIN CHECK (351-item scope pull) ===")
        print(f"{n_rows} total rows, {n_distinct_itemfg} distinct ItemFG values "
              f"({'ItemFG repeats -> grain is finer than one-row-per-finished-item' if n_rows > n_distinct_itemfg else 'ItemFG does NOT repeat'})")
        if component_col:
            key_cols = ["ItemFG", component_col]
            n_dupe_keys = bom_scope.duplicated(subset=key_cols).sum()
            print(f"Duplicate (ItemFG, {component_col}) pairs: {n_dupe_keys} of {n_rows} rows "
                  f"({'grain is at least (ItemFG,' + component_col + ')' if n_dupe_keys == 0 else 'grain is FINER than (ItemFG, component) -- investigate extra key columns'})")

    if component_col and len(bom_scope):
        distinct_components = (
            component_rows[component_col].astype(str).str.strip().dropna().unique().tolist()
        )
        distinct_components = [c for c in distinct_components if c and c.lower() != "none"]
        print(f"\n=== STEP 4: {len(distinct_components)} distinct component codes across the 351-item scope's BOM (component lines only, Sequenceno>=1) ===")

        # 4a. Forward direction: component -> Cube_Inventory_Exact.itemcode presence
        comp_sql = code_list_sql(distinct_components)
        inv_match = pd.read_sql(
            f"SELECT DISTINCT itemcode FROM Cube_Inventory_Exact WHERE itemcode IN ({comp_sql})",
            conn,
        )
        matched_components = set(inv_match["itemcode"].astype(str).str.strip())
        print(f"Forward direction: {len(matched_components)} / {len(distinct_components)} distinct BOM component codes appear as itemcode in Cube_Inventory_Exact")

        # 4b. Reverse direction: pull full Cube_Inventory_Exact rows (all warehouses) for
        # exactly these component codes -- confirms symmetric match + gives stock values
        comp_inventory = pd.read_sql(
            f"SELECT company, warehouse, itemcode, stock, minimum, maximum, reserve_bywa, timestamp "
            f"FROM Cube_Inventory_Exact WHERE itemcode IN ({comp_sql})",
            conn,
        )
        comp_inventory.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_component_inventory.csv", index=False)
        print(f"Reverse-direction pull: {len(comp_inventory)} inventory rows for matched/candidate component codes; "
              f"{comp_inventory['itemcode'].nunique() if len(comp_inventory) else 0} distinct itemcodes returned")

        # Save the distinct component list + match flag
        comp_df = pd.DataFrame({"component_code": distinct_components})
        comp_df["in_cube_inventory_exact"] = comp_df["component_code"].isin(matched_components)
        comp_df.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_distinct_components_match.csv", index=False)

        # 5. Shared components: does the same component appear across multiple ItemFG?
        shared = (
            component_rows.groupby(component_col)["ItemFG"].nunique().reset_index(name="n_finished_items")
        )
        shared = shared.sort_values("n_finished_items", ascending=False)
        shared.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_shared_components.csv", index=False)
        print(f"\n=== STEP 5: shared-component check (component lines only) ===")
        print(f"{(shared['n_finished_items'] > 1).sum()} of {len(shared)} distinct components used by MORE than one finished item in the 351-item scope")
        print(shared.head(15).to_string())

        if qty_col and qty_col in component_rows.columns:
            print(f"\n=== Quantity stats ({qty_col}) across component lines only (Sequenceno>=1) ===")
            print(component_rows[qty_col].describe().to_string())
            print("\n--- Quantity stats for the 16 fast-zero-onhand items' component lines ---")
            fz_component_rows = bom_fastzero[pd.to_numeric(bom_fastzero["Sequenceno"], errors="coerce") >= 1]
            fz_component_rows.to_csv(f"{SUMMARY_DIR}/phaseJ3_explorerBOM_16items_component_lines_only.csv", index=False)
            print(fz_component_rows[[  "ItemFG", component_col, qty_col, "Unit", "Type"]].to_string())
    else:
        print("WARNING: could not determine component column automatically or bom_scope empty; "
              "manual inspection of top5/schema output required.")

print("\nDone. All queries ran over the single connection.")
