"""Phase D Explorer -- Check 3: where CI101-sheet items sold under PEM101 are held.

Question (STATUS.md Phase D, Check 3): 37.24% of the combined CI101+PEM101 Omni-Channel value
for CI101's 13 pricelist item codes is recorded under division='PEM101' in cube_Sale_APD
(phaseC_sheetmap_report.md, Section 5) -- confirmed as genuine, current-period demand for
CI101's own item codes, now automatically in this project's forecast scope (config.yaml
sheet_to_division: CI101 sheet -> division CI101, database division tag never used as a filter).
NOT yet known: whether the PHYSICAL STOCK for these items sits in the same warehouses PEM101's
own products use, or somewhere else (or nowhere) -- this determines whether Phase E should plan
stock for these items using PEM101's warehouse pool or treat them separately.

Scope is deliberately narrow, per the task brief: [salewarehouse].[dbo].[Cube_Inventory_Exact]
joined to [salewarehouse].[dbo].[cube_Sale_APD] only. No other table is queried.

Explorer role (AGENTS.md): reports what a join/query returns, does not interpret business
meaning beyond the plain practical conclusion the task brief asks for directly.

Investigation script only -- no pipeline code touched, no config changed. Writes CSVs to
output/summary/, prefixed phaseD_check3_, and a report to output/summary/phaseD_check3_report.md.
"""
import logging
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseD_check3")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SCOPE_335_FILE = os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv")

SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"

# Judgment call (stated explicitly, per task instructions): a warehouse code is treated as
# "table-wide shared / ambiguous" -- not distinctively PEM101's -- if it holds nonzero stock for
# items from 3 or more of the pricelist's distinct divisions (majority of the 6 total divisions:
# PEM101/PEM102/PEM103/PEM104/PEM107/CI101). This threshold is not derived from the data; it is
# a reasonable reading of "used broadly" vs. "essentially exclusive," consistent with the prior
# Phase 4 warehouse-structure finding (STATUS.md: "33 of 34 codes used across MULTIPLE divisions")
# which this check independently re-verifies for the specific codes in play here.
AMBIGUITY_THRESHOLD_DIVISIONS = 3


def out(name: str) -> str:
    return os.path.join(SUMMARY_DIR, f"phaseD_check3_{name}")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sql_list(values):
    return "','".join(v.replace("'", "''") for v in values)


def strip_warehouse(df: pd.DataFrame) -> pd.DataFrame:
    n_padded = (df["warehouse"] != df["warehouse"].str.strip()).sum()
    if n_padded:
        logger.info("%d of %d rows have a fixed-width-padded warehouse code -- stripped before grouping.",
                    n_padded, len(df))
    df = df.copy()
    df["warehouse"] = df["warehouse"].str.strip()
    return df


def build_full_registry_division_map(config: dict) -> pd.DataFrame:
    """One row per pricelist code (all visible sheets) -> division, via config's
    sheet_to_division mapping (authoritative source, CONVENTIONS.md), NOT the database's
    division column. Used only for the table-wide warehouse-ambiguity check (Check 4)."""
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    sheet_to_division = config["sheet_to_division"]
    unmapped = set(pl["sheet"].unique()) - set(sheet_to_division.keys())
    if unmapped:
        raise ValueError(f"Sheets with no sheet_to_division mapping: {unmapped} -- stopping.")
    pl = pl.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    pl["division"] = pl["sheet"].map(sheet_to_division)
    return pl[["code", "sheet", "division"]]


def main():
    config = load_config()
    statuses = config["status_basis"]
    revenue_type = config["revenue_type"]

    # =====================================================================================
    # STEP 0 -- confirm Cube_Inventory_Exact schema directly (do not assume column names)
    # =====================================================================================
    logger.info("=== STEP 0: confirm Cube_Inventory_Exact schema ===")
    schema = run_query("""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Cube_Inventory_Exact'
        ORDER BY ORDINAL_POSITION
    """)
    schema.to_csv(out("00_inventory_exact_schema.csv"), index=False)
    logger.info("Cube_Inventory_Exact columns: %s", schema["COLUMN_NAME"].tolist())
    if "itemcode" not in schema["COLUMN_NAME"].tolist():
        raise ValueError(
            f"Column 'itemcode' NOT found in Cube_Inventory_Exact schema -- actual columns: "
            f"{schema['COLUMN_NAME'].tolist()}. Stopping rather than guessing a substitute."
        )
    logger.info("Confirmed: itemcode column name is 'itemcode' (schema-verified, not assumed).")

    # =====================================================================================
    # STEP 0b -- the 13 CI101-sheet pricelist codes
    # =====================================================================================
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    ci = pl[pl["sheet"] == "CI101"].copy()
    codes = sorted(ci["code"].unique().tolist())
    logger.info("CI101 sheet pricelist rows: %d, distinct codes: %d -> %s", len(ci), len(codes), codes)
    if len(codes) != 13:
        raise ValueError(f"Expected 13 distinct CI101 codes, found {len(codes)} -- stopping.")

    # =====================================================================================
    # CHECK 1 -- per-item division breakdown of Omni Channel / Actual+MPS sales for the 13 codes
    # =====================================================================================
    logger.info("=== CHECK 1: per-item PEM101-tagged sales among CI101's 13 codes ===")
    q1 = f"""
        SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{sql_list(codes)}')
          AND revenue_type = '{revenue_type}'
          AND status IN ('{sql_list(statuses)}')
        GROUP BY itemcode, division
        ORDER BY itemcode, sum_sale DESC
    """
    div_breakdown = run_query(q1)
    if (div_breakdown["sum_sale"] < 0).any() or (div_breakdown["sum_qty"] < 0).any():
        neg = div_breakdown[(div_breakdown["sum_sale"] < 0) | (div_breakdown["sum_qty"] < 0)]
        raise ValueError(f"Negative sum_sale/sum_qty found in per-item/division breakdown -- must be "
                          f"reviewed, not dropped silently: {neg.to_dict('records')}")
    div_breakdown.to_csv(out("01_per_item_division_breakdown.csv"), index=False)
    logger.info("Pulled %d (itemcode, division) groups across the 13 CI101 codes.", len(div_breakdown))

    # Per-item summary: total (CI101+PEM101 basis, matching phaseC_sheetmap_report.md Section 5's
    # definition) vs. PEM101-tagged share.
    ci_pem = div_breakdown[div_breakdown["division"].isin(["CI101", "PEM101"])]
    pivot = ci_pem.pivot_table(index="itemcode", columns="division",
                                values=["n_rows", "sum_sale", "sum_qty"], aggfunc="sum", fill_value=0)
    pivot.columns = [f"{val}_{div}" for val, div in pivot.columns]
    pivot = pivot.reset_index()
    summary = pd.DataFrame({"itemcode": codes}).merge(pivot, on="itemcode", how="left").fillna(0)
    for col in ["n_rows_CI101", "n_rows_PEM101", "sum_sale_CI101", "sum_sale_PEM101",
                "sum_qty_CI101", "sum_qty_PEM101"]:
        if col not in summary.columns:
            summary[col] = 0.0
    summary["combined_ci101_pem101_sale"] = summary["sum_sale_CI101"] + summary["sum_sale_PEM101"]
    summary["pct_value_under_pem101"] = summary.apply(
        lambda r: round(100.0 * r["sum_sale_PEM101"] / r["combined_ci101_pem101_sale"], 2)
        if r["combined_ci101_pem101_sale"] > 0 else None, axis=1
    )
    summary["has_pem101_tagged_sales"] = summary["n_rows_PEM101"] > 0

    # Also record any other division these 13 codes appear under (reference only -- residual,
    # e.g. PCE101/PEM104, seen in phaseC_sheetmap_report.md; not part of the 37.24% denominator).
    other_div = div_breakdown[~div_breakdown["division"].isin(["CI101", "PEM101"])]
    other_div_by_item = other_div.groupby("itemcode").agg(
        other_divisions=("division", lambda s: sorted(s.dropna().unique().tolist())),
        other_division_sale=("sum_sale", "sum"),
    ).reset_index()
    summary = summary.merge(other_div_by_item, on="itemcode", how="left")
    summary["other_divisions"] = summary["other_divisions"].apply(lambda v: v if isinstance(v, list) else [])
    summary["other_division_sale"] = summary["other_division_sale"].fillna(0.0)

    summary = summary.sort_values("itemcode").reset_index(drop=True)
    summary.to_csv(out("01_per_item_pem101_summary.csv"), index=False)
    print("\nCHECK 1 -- per-item CI101/PEM101 division split (Omni Channel, Actual+MPS):")
    print(summary[["itemcode", "n_rows_CI101", "sum_sale_CI101", "n_rows_PEM101", "sum_sale_PEM101",
                    "pct_value_under_pem101", "has_pem101_tagged_sales", "other_divisions"]].to_string(index=False))

    items_with_pem101 = sorted(summary[summary["has_pem101_tagged_sales"]]["itemcode"].tolist())
    logger.info("Of 13 CI101 codes, %d have >=1 row under division='PEM101' (Omni Channel, Actual/MPS): %s",
                len(items_with_pem101), items_with_pem101)

    # Aggregate reproduction check vs. the known 37.24% figure (phaseC_sheetmap_report.md Section 5:
    # CI101-tagged 104,089,870 / PEM101-tagged 61,772,748 / combined 165,862,618 / share 37.24%).
    agg_ci = summary["sum_sale_CI101"].sum()
    agg_pem = summary["sum_sale_PEM101"].sum()
    agg_combined = agg_ci + agg_pem
    agg_pct = round(100.0 * agg_pem / agg_combined, 2) if agg_combined else None
    logger.info("Aggregate reproduction: CI101-tagged=%.2f, PEM101-tagged=%.2f, combined=%.2f, "
                "PEM101 share=%.2f%% (prior report: CI101=104,089,870, PEM101=61,772,748, "
                "combined=165,862,618, share=37.24%%).", agg_ci, agg_pem, agg_combined, agg_pct)
    pd.DataFrame([{
        "agg_ci101_sale": agg_ci, "agg_pem101_sale": agg_pem, "agg_combined_sale": agg_combined,
        "agg_pct_pem101": agg_pct, "prior_report_ci101_sale": 104089870, "prior_report_pem101_sale": 61772748,
        "prior_report_combined_sale": 165862618, "prior_report_pct_pem101": 37.24,
    }]).to_csv(out("01b_aggregate_reproduction_check.csv"), index=False)

    # =====================================================================================
    # CHECK 2 -- stock by warehouse, for every CI101 item with PEM101-tagged sales
    # =====================================================================================
    logger.info("=== CHECK 2: Cube_Inventory_Exact stock by warehouse, for the %d items with "
                "PEM101-tagged sales ===", len(items_with_pem101))
    if items_with_pem101:
        q2 = f"""
            SELECT company, warehouse, itemcode, unit, stock, timestamp
            FROM {INV_TABLE}
            WHERE itemcode IN ('{sql_list(items_with_pem101)}')
        """
        inv_ci = run_query(q2)
        inv_ci = strip_warehouse(inv_ci)
        inv_ci.to_csv(out("02_ci101_pem101tagged_inventory_raw.csv"), index=False)
        neg_stock = inv_ci[inv_ci["stock"] < 0]
        if len(neg_stock):
            logger.warning("%d rows have NEGATIVE stock in Cube_Inventory_Exact for these items -- kept, "
                            "reported, not dropped: %s", len(neg_stock), neg_stock.to_dict("records"))
        logger.info("Pulled %d Cube_Inventory_Exact rows for %d items.", len(inv_ci), len(items_with_pem101))

        by_item_wh = inv_ci.groupby(["itemcode", "warehouse"], as_index=False)["stock"].sum()
        by_item_wh.to_csv(out("02_ci101_pem101tagged_by_warehouse.csv"), index=False)

        items_any_inv_rows = set(inv_ci["itemcode"].unique())
        items_no_inv_rows = sorted(set(items_with_pem101) - items_any_inv_rows)
        per_item_total_stock = by_item_wh.groupby("itemcode")["stock"].sum()
        items_zero_total_stock = sorted(per_item_total_stock[per_item_total_stock <= 0].index.tolist())
        logger.info("Of %d items: %d have NO rows at all in Cube_Inventory_Exact; %d more have rows but "
                    "total stock <= 0 across all warehouses.", len(items_with_pem101),
                    len(items_no_inv_rows), len(items_zero_total_stock))
    else:
        inv_ci = pd.DataFrame(columns=["company", "warehouse", "itemcode", "unit", "stock", "timestamp"])
        by_item_wh = pd.DataFrame(columns=["itemcode", "warehouse", "stock"])
        by_item_wh.to_csv(out("02_ci101_pem101tagged_by_warehouse.csv"), index=False)
        items_no_inv_rows, items_zero_total_stock = [], []
        logger.info("No CI101 items have PEM101-tagged sales -- Check 2 has nothing to pull. Stopping "
                    "this check here per the stopping rule; report will state this plainly.")

    # =====================================================================================
    # CHECK 3 -- comparison set: PEM101's own products' warehouses
    # =====================================================================================
    logger.info("=== CHECK 3: comparison set -- PEM101's own products' stock-holding warehouses ===")
    scope335 = pd.read_csv(SCOPE_335_FILE)
    pem101_items = sorted(scope335[scope335["division"] == "PEM101"]["code"].unique().tolist())
    logger.info("PEM101's own products, comparison set choice (stated explicitly): the 335-item "
                "forecast scope's division='PEM101' codes (pricelist-sourced, per CONVENTIONS.md -- "
                "the pricelist, not cube_Sale_APD's own division tag, is authoritative for which "
                "items are 'PEM101's own'). This is the full set (%d codes), not a sample, since it "
                "is readily available and gives the most representative picture -- not just the 3 "
                "pilot focus items.", len(pem101_items))

    q3 = f"""
        SELECT company, warehouse, itemcode, unit, stock, timestamp
        FROM {INV_TABLE}
        WHERE itemcode IN ('{sql_list(pem101_items)}')
    """
    inv_pem101 = run_query(q3)
    inv_pem101 = strip_warehouse(inv_pem101)
    inv_pem101.to_csv(out("03_pem101_own_items_inventory_raw.csv"), index=False)
    neg_stock_pem = inv_pem101[inv_pem101["stock"] < 0]
    if len(neg_stock_pem):
        logger.warning("%d rows have NEGATIVE stock in Cube_Inventory_Exact for PEM101's own items -- "
                        "kept, reported, not dropped.", len(neg_stock_pem))
    logger.info("Pulled %d Cube_Inventory_Exact rows for %d PEM101-own items.", len(inv_pem101), len(pem101_items))

    pem101_by_wh = inv_pem101.groupby(["itemcode", "warehouse"], as_index=False)["stock"].sum()
    pem101_by_wh.to_csv(out("03_pem101_own_items_by_warehouse.csv"), index=False)

    wh_stock_totals_pem101 = inv_pem101.groupby("warehouse")["stock"].sum()
    pem101_warehouses_with_stock = sorted(wh_stock_totals_pem101[wh_stock_totals_pem101 > 0].index.tolist())
    logger.info("PEM101's own products hold nonzero stock in %d distinct warehouse codes: %s",
                len(pem101_warehouses_with_stock), pem101_warehouses_with_stock)
    pd.DataFrame({"warehouse": pem101_warehouses_with_stock}).to_csv(
        out("03_pem101_own_warehouse_set.csv"), index=False)

    # =====================================================================================
    # CHECK 4 -- table-wide warehouse ambiguity: how many pricelist divisions hold nonzero stock
    # in each relevant warehouse code (Cube_Inventory_Exact joined to the full pricelist
    # registry's division, still within the stated Cube_Inventory_Exact / cube_Sale_APD scope in
    # spirit -- the pricelist file itself is the authoritative division source per CONVENTIONS.md,
    # not a "wider database" search).
    # =====================================================================================
    logger.info("=== CHECK 4: table-wide warehouse ambiguity (is a warehouse code distinctively "
                "PEM101's, or shared broadly across divisions?) ===")
    full_registry = build_full_registry_division_map(config)
    logger.info("Full pricelist registry: %d codes across %d divisions: %s",
                len(full_registry), full_registry["division"].nunique(),
                sorted(full_registry["division"].unique().tolist()))

    q4 = f"""
        SELECT warehouse, itemcode, SUM(stock) AS stock
        FROM {INV_TABLE}
        WHERE itemcode IN ('{sql_list(sorted(full_registry["code"].unique().tolist()))}')
        GROUP BY warehouse, itemcode
    """
    inv_all = run_query(q4)
    inv_all = strip_warehouse(inv_all)
    inv_all = inv_all.merge(full_registry[["code", "division"]], left_on="itemcode", right_on="code", how="left")
    unmapped_inv = inv_all[inv_all["division"].isna()]
    if len(unmapped_inv):
        logger.warning("%d Cube_Inventory_Exact rows (table-wide pull, full registry item codes) have no "
                        "matching pricelist division after the join -- should not happen since the query "
                        "itself was scoped to full_registry codes; investigating: %s",
                        len(unmapped_inv), unmapped_inv["itemcode"].unique().tolist()[:20])

    inv_all_nonzero = inv_all[inv_all["stock"] > 0]
    wh_division_counts = inv_all_nonzero.groupby("warehouse")["division"].apply(
        lambda s: sorted(s.dropna().unique().tolist())).reset_index().rename(columns={"division": "divisions_with_stock_here"})
    wh_division_counts["n_divisions"] = wh_division_counts["divisions_with_stock_here"].apply(len)
    wh_division_counts["ambiguous"] = wh_division_counts["n_divisions"] >= AMBIGUITY_THRESHOLD_DIVISIONS
    wh_division_counts = wh_division_counts.sort_values("n_divisions", ascending=False)
    wh_division_counts.to_csv(out("04_warehouse_division_ambiguity_tablewide.csv"), index=False)
    print("\nCHECK 4 -- table-wide warehouse/division ambiguity (all pricelist divisions, nonzero stock):")
    print(wh_division_counts.to_string(index=False))

    ambiguity_lookup = wh_division_counts.set_index("warehouse")[["n_divisions", "divisions_with_stock_here", "ambiguous"]].to_dict("index")

    # =====================================================================================
    # VERDICT -- per CI101 item with PEM101-tagged sales: same / different / partial / no-stock /
    # undetermined, against PEM101's own warehouse set, with the table-wide ambiguity caveat.
    # =====================================================================================
    logger.info("=== VERDICT: per-item same/different/partial/no-stock/undetermined ===")
    verdict_rows = []
    pem101_set = set(pem101_warehouses_with_stock)
    for item in items_with_pem101:
        item_wh_rows = by_item_wh[(by_item_wh["itemcode"] == item) & (by_item_wh["stock"] > 0)]
        item_wh_set = set(item_wh_rows["warehouse"].tolist())

        if item in items_no_inv_rows:
            raw_verdict = "NO_STOCK_NO_INVENTORY_RECORD"
        elif not item_wh_set:
            raw_verdict = "NO_STOCK_ZERO_QTY"
        elif item_wh_set.issubset(pem101_set) and item_wh_set:
            raw_verdict = "SAME"
        elif item_wh_set & pem101_set:
            raw_verdict = "PARTIAL"
        else:
            raw_verdict = "DIFFERENT"

        if item_wh_set:
            wh_ambig_detail = {w: ambiguity_lookup.get(w, {"n_divisions": None, "ambiguous": None}) for w in sorted(item_wh_set)}
            n_ambiguous_wh = sum(1 for w in item_wh_set if ambiguity_lookup.get(w, {}).get("ambiguous"))
            all_ambiguous = n_ambiguous_wh == len(item_wh_set) and len(item_wh_set) > 0
            any_distinctive = any((not ambiguity_lookup.get(w, {}).get("ambiguous", True)) for w in item_wh_set)
        else:
            wh_ambig_detail, n_ambiguous_wh, all_ambiguous, any_distinctive = {}, 0, False, False

        if raw_verdict in ("NO_STOCK_NO_INVENTORY_RECORD", "NO_STOCK_ZERO_QTY"):
            final_verdict = raw_verdict
        elif raw_verdict == "SAME" and all_ambiguous:
            final_verdict = "SAME_BUT_UNDETERMINED (warehouse codes shared broadly across divisions table-wide -- cannot confirm distinctively PEM101's)"
        elif raw_verdict == "SAME" and any_distinctive:
            final_verdict = "SAME_DISTINCTIVE (at least one stock-holding warehouse is not broadly shared table-wide)"
        elif raw_verdict == "DIFFERENT":
            final_verdict = "DIFFERENT (no overlap with PEM101's own warehouse set)"
        elif raw_verdict == "PARTIAL" and all_ambiguous:
            final_verdict = "PARTIAL_BUT_UNDETERMINED (overlapping warehouses are shared broadly table-wide)"
        elif raw_verdict == "PARTIAL":
            final_verdict = "PARTIAL"
        else:
            final_verdict = raw_verdict

        verdict_rows.append({
            "itemcode": item,
            "item_warehouses_with_stock": sorted(item_wh_set),
            "item_total_stock": float(item_wh_rows["stock"].sum()) if len(item_wh_rows) else 0.0,
            "pem101_own_warehouse_set": pem101_warehouses_with_stock,
            "overlap_warehouses": sorted(item_wh_set & pem101_set),
            "raw_verdict": raw_verdict,
            "n_ambiguous_warehouses_of_item_set": n_ambiguous_wh,
            "n_item_warehouses": len(item_wh_set),
            "warehouse_ambiguity_detail": wh_ambig_detail,
            "final_verdict": final_verdict,
        })

    verdict_df = pd.DataFrame(verdict_rows)
    verdict_df.to_csv(out("05_per_item_verdict.csv"), index=False)
    print("\nFINAL VERDICT -- per CI101 item with PEM101-tagged sales:")
    if len(verdict_df):
        print(verdict_df[["itemcode", "item_warehouses_with_stock", "overlap_warehouses",
                           "raw_verdict", "final_verdict"]].to_string(index=False))
        print("\nRaw verdict counts:")
        print(verdict_df["raw_verdict"].value_counts().to_string())
    else:
        print("(no items with PEM101-tagged sales -- nothing to verdict)")

    print("\n" + "=" * 90)
    print(f"DONE -- {len(items_with_pem101)} of 13 CI101 items have PEM101-tagged sales. "
          f"See output/summary/phaseD_check3_report.md for the full write-up.")
    print("=" * 90)


if __name__ == "__main__":
    main()
