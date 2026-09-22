"""Phase E2 readiness: does PEM102/PEM103/PEM104/PEM107/CI101 stock genuinely not exist, sit in
warehouses not named after the division, or sit in a table other than Cube_Inventory_Exact?

Single Explorer (AGENTS.md), read-only. Division is sourced from the pricelist
(config['sheet_to_division']), never from any database `division`/`ManuDivision` column
(CONVENTIONS.md). Warehouse ownership is never inferred from a code's name -- only from where the
item-to-warehouse mapping itself shows nonzero stock.

SCOPE NOTE (reported, not silently reconciled): the task states "every pricelist item of PEM102,
PEM103, PEM107 and CI101 -- 317 codes". The current pricelist (reference/pricelist.xlsx, visible
sheets only, deduplicated -- CONVENTIONS.md's authoritative source) gives PEM102=26, PEM103=87,
PEM107=136, CI101=13 = 262 codes for those four divisions, not 317. 445 (full registry) - 128
(the PEM101 Fuse/Surge-Arrester PILOT subset) = 317 exactly, so "317" appears to describe
"everything outside the 128-item PEM101 pilot" (which would include the other 43 non-pilot PEM101
items), a different definition than "PEM102+PEM103+PEM107+CI101" literally. Per ground rules
(never fabricate a match to an unverified number), this script uses the VERIFIED,
pricelist-derived scope: 262 codes across PEM102/PEM103/PEM107/CI101, plus PEM104's 12 = 274
codes total, and states this discrepancy plainly rather than forcing a match to 317.

METRICS.md Sec.1 unit_cost is computed fresh here (median(cost/qty), trailing 12mo, Omni Channel,
Actual+MPS, <3 rows -> most-recent fallback, 0 rows -> no_unit_cost_item) via the already-locked
implementation in src/phaseE1fix_recompute.py (imported, not re-derived).

DATABASE ACCESS RULE: one connection attempt only. If the first query fails, this script stops
and raises -- nothing here retries a failed login. Subsequent queries in the same run reuse the
same already-proven credentials.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402
from division_utils import assert_no_code_on_multiple_sheets  # noqa: E402
from phaseE1fix_recompute import compute_unit_cost_metrics1  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE2_readiness")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"
TARGET_DIVISIONS = ["PEM102", "PEM103", "PEM107", "CI101"]
COMPLETENESS_DIVISION = "PEM104"
DOMINANCE_THRESHOLD_PCT = 60.0

# Other-table Part 3 candidates: (table, itemcode_col, qty_cols, division_col_or_None, character)
# Found via a systematic INFORMATION_SCHEMA search (item-code-like AND qty/stock/balance-like
# column), narrowed to plausible stock/balance/contract candidates -- excludes the many
# clearly-sales/quotation/snapshot-alias tables the same search also matched (cube_Sale_APD_*
# variants, Cube_Backlog_*, Cube_CES, Cube_Quotation_*, cube_revenue/Revunue, cube_final,
# cube_cus_complaint, cube_pl_erp_transaction*) -- named here, not queried, since their names and
# known columns (customer, quotation, complaint, GL posting) already identify them as sales/
# quotation/complaint/accounting documents, not stock. cube_Contract (product_id, plan_qty,
# actual_qty, backlog_qty) is added by hand: its item column is 'product_id', not 'itemcode', so
# the systematic search's '%itemcode%' pattern missed it -- a real, reported search-pattern gap.
OTHER_TABLE_CANDIDATES = [
    {"table": "Cube_Inventory_Aging", "item_col": "ItemCode",
     "qty_cols": ["Stock", "FreeStock"], "division_col": "Division", "warehouse_col": "Warehouse"},
    {"table": "Cube_Inventory_Aging_PSL", "item_col": "ItemCode",
     "qty_cols": ["Stock", "FreeStock", "AvailableStock", "QtyIN_ALL", "QtyOUT_ALL"],
     "division_col": None, "warehouse_col": "Warehouse"},
    {"table": "Cube_Inventory_Exact_PPD", "item_col": "itemcode",
     "qty_cols": ["stock", "freestock", "tobe_received", "available"],
     "division_col": None, "warehouse_col": "warehouse"},
    {"table": "Cube_Inventory_Batch", "item_col": "ItemCode",
     "qty_cols": ["QuantityReceived", "QuantityAvailable", "QuantityDelivered"],
     "division_col": None, "warehouse_col": None},
    {"table": "information_state", "item_col": "itemcode",
     "qty_cols": ["quantity", "amount"], "division_col": None, "warehouse_col": None},
    {"table": "Cube_tobe_received", "item_col": "itemcode",
     "qty_cols": ["quantity"], "division_col": None, "warehouse_col": "warehouse"},
    {"table": "Cube_Incoming_Receipt", "item_col": "itemcode",
     "qty_cols": ["qty"], "division_col": "division", "warehouse_col": None},
    {"table": "Cube_Incoming_Wait", "item_col": "itemcode",
     "qty_cols": ["quantity"], "division_col": "division", "warehouse_col": None},
    {"table": "Cube_pr_monitoring", "item_col": "itemcode",
     "qty_cols": ["quantity"], "division_col": "division", "warehouse_col": None},
]


def out(name: str) -> str:
    return os.path.join(SUMMARY_DIR, f"phaseE2_{name}")


def sql_list(values) -> str:
    return "','".join(str(v).replace("'", "''") for v in values)


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def strip_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df = df.copy()
    df[col] = df[col].astype(str).str.strip()
    return df


# ================================================================================================
# STEP 1: item scope + division, pricelist-sourced (CONVENTIONS.md authoritative)
# ================================================================================================
def step1_scope(config: dict) -> tuple:
    logger.info("=== STEP 1: pricelist item scope + division ===")
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    assert_no_code_on_multiple_sheets(pl)
    pl = pl.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    pl["division"] = pl["sheet"].map(config["sheet_to_division"])
    full_scope = pl[["code", "sheet", "division", "category", "type"]].rename(columns={"code": "itemcode"})

    counts = full_scope["division"].value_counts().to_dict()
    target_count = sum(counts.get(d, 0) for d in TARGET_DIVISIONS)
    pem104_count = counts.get(COMPLETENESS_DIVISION, 0)
    logger.info("Pricelist division counts: %s", counts)
    logger.info("VERIFIED count for %s: %d codes (task states 317). PEM104: %d codes (task states 12, matches).",
                TARGET_DIVISIONS, target_count, pem104_count)
    if target_count != 317:
        logger.warning("SCOPE DISCREPANCY, reported not reconciled: task says 317 codes for %s; "
                        "the current pricelist gives %d. 445 (full registry) - 128 (PEM101 pilot "
                        "subset) = 317 exactly -- '317' appears to mean 'every code outside the "
                        "128-item PEM101 pilot' (which also includes 43 non-pilot PEM101 items), "
                        "a different set than 'PEM102+PEM103+PEM107+CI101'. Proceeding with the "
                        "VERIFIED %d-code scope for those 4 divisions (+ %d PEM104 = %d total), "
                        "not a fabricated 317.", TARGET_DIVISIONS, target_count, pem104_count,
                        target_count + pem104_count)

    scope_divs = TARGET_DIVISIONS + [COMPLETENESS_DIVISION]
    scope = full_scope[full_scope["division"].isin(scope_divs)].copy()
    scope.to_csv(out("0_item_scope.csv"), index=False)
    logger.info("Investigation scope: %d codes (%s), + %d PEM104 for completeness = %d total.",
                target_count, TARGET_DIVISIONS, pem104_count, len(scope))
    return full_scope, scope


# ================================================================================================
# STEP 2: Cube_Inventory_Exact pull, FULL 445-item registry (needed for Part 2's true
# shared-warehouse picture, which must see divisions beyond the 5 in scope, e.g. PEM101)
# ================================================================================================
def step2_inventory_pull(full_scope: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 2: Cube_Inventory_Exact pull, FULL 445-item registry (single connection attempt) ===")
    codes = sorted(full_scope["itemcode"].unique())
    try:
        inv = run_query(f"""
            SELECT itemcode, warehouse, stock, freestock, tobe_received, available, timestamp
            FROM {INV_TABLE} WHERE itemcode IN ('{sql_list(codes)}')
        """)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: single connection attempt failed, not retrying. Error: %r", exc)
        raise
    inv = strip_col(inv, "warehouse")
    inv = inv.merge(full_scope, on="itemcode", how="left")
    logger.info("Pulled %d (item, warehouse) rows, %d distinct items present (of %d in full registry), "
                "%d distinct warehouse codes. Snapshot timestamp range: %s to %s.",
                len(inv), inv["itemcode"].nunique(), len(codes), inv["warehouse"].nunique(),
                inv["timestamp"].min(), inv["timestamp"].max())
    inv.to_csv(out("0_full_registry_inventory_raw.csv"), index=False)
    return inv


# ================================================================================================
# PART 1: reverse item -> warehouse, per-division aggregation, cross-tab, concentration
# ================================================================================================
def part1_reverse_and_crosstab(inv_full: pd.DataFrame, scope: pd.DataFrame, unit_cost: pd.DataFrame) -> dict:
    logger.info("=== PART 1: reverse item->warehouse, division aggregation, cross-tab ===")
    scope_codes = set(scope["itemcode"])
    inv = inv_full[inv_full["itemcode"].isin(scope_codes)].copy()
    inv = inv.merge(unit_cost[["itemcode", "unit_cost", "unit_cost_fallback", "no_unit_cost_item"]],
                     on="itemcode", how="left")
    nonzero = inv[inv["stock"] != 0].copy()
    nonzero["value"] = np.where(nonzero["no_unit_cost_item"], np.nan, nonzero["stock"] * nonzero["unit_cost"])

    # --- per-item reverse listing ---
    item_wh = nonzero.groupby(["itemcode", "division"]).apply(
        lambda g: [{"warehouse": w, "qty": float(q)} for w, q in zip(g["warehouse"], g["stock"])]
    ).reset_index(name="warehouses_with_stock")
    item_wh["n_warehouses"] = item_wh["warehouses_with_stock"].apply(len)
    item_wh["total_qty"] = item_wh["warehouses_with_stock"].apply(lambda lst: sum(d["qty"] for d in lst))
    # every scope item, including those with ZERO stock anywhere (explicit, not silently omitted)
    all_items = scope[["itemcode", "division"]].merge(item_wh, on=["itemcode", "division"], how="left")
    all_items["n_warehouses"] = all_items["n_warehouses"].fillna(0).astype(int)
    all_items["total_qty"] = all_items["total_qty"].fillna(0.0)
    all_items["has_stock_anywhere"] = all_items["n_warehouses"] > 0
    all_items.to_csv(out("1_item_to_warehouse_reverse.csv"), index=False)
    logger.info("Reverse lookup: %d/%d scope items have nonzero stock in >=1 warehouse code in "
                "Cube_Inventory_Exact.", int(all_items["has_stock_anywhere"].sum()), len(all_items))

    # --- per-division aggregation ---
    div_rows = []
    for div, g in all_items.groupby("division"):
        stocked = g[g["has_stock_anywhere"]]
        div_nonzero = nonzero[nonzero["division"] == div]
        total_value = div_nonzero["value"].sum(skipna=True)
        n_no_cost = int(div_nonzero.loc[div_nonzero["no_unit_cost_item"].fillna(True), "itemcode"].nunique())
        wh_share = (div_nonzero.groupby("warehouse")["stock"].sum().sort_values(ascending=False))
        wh_share_pct = (100 * wh_share / wh_share.sum()).round(2) if wh_share.sum() else wh_share
        div_rows.append({
            "division": div, "n_codes_in_scope": len(g), "n_items_with_stock": len(stocked),
            "pct_items_with_stock": round(100 * len(stocked) / len(g), 1) if len(g) else 0.0,
            "total_qty": float(div_nonzero["stock"].sum()),
            "total_value_thb": float(total_value) if total_value == total_value else 0.0,
            "n_items_no_cost_record_but_stocked": n_no_cost,
            "warehouse_codes_holding_stock": list(wh_share.index),
            "warehouse_qty_share_pct": {k: float(v) for k, v in wh_share_pct.items()},
        })
    div_summary = pd.DataFrame(div_rows).sort_values("division")
    div_summary.to_csv(out("1_division_summary.csv"), index=False)
    logger.info("Per-division summary:\n%s", div_summary[["division", "n_codes_in_scope",
                "n_items_with_stock", "total_qty", "total_value_thb"]].to_string(index=False))

    # --- division x warehouse cross-tab (same shape as the PEM101/whmap cross-tab) ---
    cross = nonzero.groupby(["division", "warehouse"], as_index=False).agg(
        n_items=("itemcode", "nunique"), qty=("stock", "sum"), value_priced=("value", "sum"))
    cross["value_priced"] = cross["value_priced"].fillna(0.0)
    cross = cross.sort_values(["division", "qty"], ascending=[True, False])
    cross.to_csv(out("1_division_by_warehouse_crosstab.csv"), index=False)

    # --- concentration characterization per division: concentrated / spread / absent ---
    conc_rows = []
    for div, g in cross.groupby("division"):
        total_qty = g["qty"].sum()
        g_sorted = g.sort_values("qty", ascending=False)
        n_codes = len(g_sorted)
        top1_share = 100 * g_sorted["qty"].iloc[0] / total_qty if total_qty and n_codes else None
        n_items_stocked = div_summary.loc[div_summary["division"] == div, "n_items_with_stock"].iloc[0]
        if n_items_stocked == 0:
            picture = "ABSENT (zero items with any stock in this scope)"
        elif n_codes == 1:
            picture = f"CONCENTRATED (100% of qty in a single warehouse code, {g_sorted.iloc[0]['warehouse']})"
        elif top1_share is not None and top1_share >= DOMINANCE_THRESHOLD_PCT:
            picture = f"CONCENTRATED ({top1_share:.1f}% of qty in {g_sorted.iloc[0]['warehouse']}, {n_codes} codes total)"
        else:
            picture = f"SPREAD ({n_codes} warehouse codes, no single code holds >={DOMINANCE_THRESHOLD_PCT:.0f}% -- top code {g_sorted.iloc[0]['warehouse']} at {top1_share:.1f}%)" if top1_share is not None else f"SPREAD ({n_codes} codes)"
        conc_rows.append({"division": div, "n_warehouse_codes": n_codes, "total_qty": total_qty,
                           "top1_warehouse": g_sorted.iloc[0]["warehouse"] if n_codes else None,
                           "top1_qty_share_pct": round(top1_share, 1) if top1_share is not None else None,
                           "stock_picture": picture})
    # divisions with zero stock at all won't appear in `cross` -- add them explicitly
    for div in TARGET_DIVISIONS + [COMPLETENESS_DIVISION]:
        if div not in cross["division"].unique():
            conc_rows.append({"division": div, "n_warehouse_codes": 0, "total_qty": 0.0,
                               "top1_warehouse": None, "top1_qty_share_pct": None,
                               "stock_picture": "ABSENT (zero items with any stock in this scope)"})
    conc = pd.DataFrame(conc_rows).sort_values("division")
    conc.to_csv(out("1_division_concentration.csv"), index=False)
    logger.info("Stock picture per division:\n%s", conc[["division", "n_warehouse_codes", "total_qty",
                "stock_picture"]].to_string(index=False))

    return {"item_wh": all_items, "div_summary": div_summary, "cross": cross, "concentration": conc, "nonzero": nonzero}


# ================================================================================================
# PART 2: shared warehouses -- pooled vs. separate-location, using the FULL 445-item registry
# ================================================================================================
def part2_shared_warehouses(inv_full: pd.DataFrame, unit_cost: pd.DataFrame, target_warehouses: list) -> pd.DataFrame:
    logger.info("=== PART 2: shared warehouses (cross-referenced against the FULL pricelist registry, "
                "all 6 divisions, not just the 5 in scope) ===")
    inv = inv_full.merge(unit_cost[["itemcode", "unit_cost", "no_unit_cost_item"]], on="itemcode", how="left")
    nonzero = inv[(inv["stock"] != 0) & (inv["warehouse"].isin(target_warehouses))].copy()
    nonzero["value"] = np.where(nonzero["no_unit_cost_item"], np.nan, nonzero["stock"] * nonzero["unit_cost"])

    rows = []
    pooled_check_rows = []
    for wh, g in nonzero.groupby("warehouse"):
        divs = g["division"].unique()
        if len(divs) <= 1:
            continue  # not shared
        by_div = g.groupby("division").agg(n_items=("itemcode", "nunique"), qty=("stock", "sum"),
                                            value_thb=("value", "sum")).reset_index()
        by_div["value_thb"] = by_div["value_thb"].fillna(0.0)
        total_qty = by_div["qty"].sum()
        by_div["qty_share_pct"] = (100 * by_div["qty"] / total_qty).round(2)
        for _, r in by_div.iterrows():
            rows.append({"warehouse": wh, "division": r["division"], "n_items": r["n_items"],
                         "qty": r["qty"], "qty_share_pct": r["qty_share_pct"], "value_thb": r["value_thb"]})

        # pooled vs. separate: does the SAME itemcode appear under >1 division in this warehouse?
        # (structurally should never happen -- a pricelist code belongs to exactly one division,
        # enforced by assert_no_code_on_multiple_sheets -- verified empirically here, not assumed)
        item_div_counts = g.groupby("itemcode")["division"].nunique()
        n_pooled_items = int((item_div_counts > 1).sum())
        pooled_check_rows.append({
            "warehouse": wh, "n_divisions_present": len(divs), "divisions": sorted(divs),
            "n_distinct_items": g["itemcode"].nunique(),
            "n_items_appearing_under_2plus_divisions": n_pooled_items,
            "verdict": "GENUINELY POOLED (same item code shared across divisions)" if n_pooled_items
                       else "SHARED LOCATION, SEPARATE STOCK (each division's item codes are distinct within it)",
        })
    shared_split = pd.DataFrame(rows).sort_values(["warehouse", "qty"], ascending=[True, False])
    shared_split.to_csv(out("2_shared_warehouse_division_split.csv"), index=False)
    pooled_check = pd.DataFrame(pooled_check_rows).sort_values("warehouse")
    pooled_check.to_csv(out("2_shared_warehouse_pooled_check.csv"), index=False)

    logger.info("%d warehouse codes hold stock for >1 division (out of the target divisions' "
                "warehouse set, checked against the FULL 445-item registry):\n%s",
                len(pooled_check), pooled_check.to_string(index=False))
    return {"split": shared_split, "pooled_check": pooled_check}


# ================================================================================================
# PART 3: other tables -- search beyond Cube_Inventory_Exact / cube_inventory_tran
# ================================================================================================
def part3_other_tables(scope: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== PART 3: search other tables for the scope's 274 items ===")
    codes = sorted(scope["itemcode"].unique())
    results = []

    for cand in OTHER_TABLE_CANDIDATES:
        table, item_col, qty_cols = cand["table"], cand["item_col"], cand["qty_cols"]
        select_cols = [item_col] + qty_cols
        if cand["division_col"]:
            select_cols.append(cand["division_col"])
        if cand["warehouse_col"]:
            select_cols.append(cand["warehouse_col"])
        select_sql = ", ".join(sorted(set(select_cols)))
        sql = f"""SELECT {select_sql} FROM [salewarehouse].[dbo].[{table}]
                  WHERE {item_col} IN ('{sql_list(codes)}')"""
        try:
            df = run_query(sql)
        except Exception as exc:
            logger.warning("Query against %s failed (%r) -- recorded as NOT QUERIED, not silently skipped.",
                            table, exc)
            results.append({"table": table, "columns_checked": select_cols, "status": "QUERY_FAILED",
                             "n_items_present": None, "n_rows": None, "total_qty_by_col": None})
            continue
        if cand["item_col"]:
            df = strip_col(df, item_col) if df[item_col].dtype == object else df
        n_items = df[item_col].nunique() if len(df) else 0
        qty_totals = {c: float(df[c].sum()) for c in qty_cols if c in df.columns}
        df.to_csv(out(f"3_raw_{table}.csv"), index=False)
        logger.info("%s: %d rows, %d/%d scope items present, qty totals by column: %s",
                    table, len(df), n_items, len(codes), qty_totals)
        results.append({"table": table, "columns_checked": select_cols, "status": "OK",
                         "n_items_present": n_items, "n_rows": len(df), "total_qty_by_col": qty_totals})

    # cube_Contract by hand: item column is 'product_id', not 'itemcode' -- the systematic
    # INFORMATION_SCHEMA search's '%itemcode%' pattern missed this table entirely (a real,
    # reported search-pattern gap, not silently patched over).
    try:
        contract = run_query(f"""
            SELECT contractid, product_id, product, jobname, status, plan_qty, actual_qty, backlog_qty
            FROM [salewarehouse].[dbo].[cube_Contract] WHERE product_id IN ('{sql_list(codes)}')
        """)
        contract.to_csv(out("3_raw_cube_Contract.csv"), index=False)
        n_items = contract["product_id"].nunique() if len(contract) else 0
        qty_totals = {c: float(contract[c].sum()) for c in ["plan_qty", "actual_qty", "backlog_qty"]}
        logger.info("cube_Contract (item col='product_id', found by hand, NOT by the systematic "
                    "'%%itemcode%%' search): %d rows, %d/%d scope items present, qty totals: %s",
                    len(contract), n_items, len(codes), qty_totals)
        results.append({"table": "cube_Contract", "columns_checked": ["product_id", "plan_qty", "actual_qty", "backlog_qty"],
                         "status": "OK", "n_items_present": n_items, "n_rows": len(contract),
                         "total_qty_by_col": qty_totals})
    except Exception as exc:
        logger.warning("Query against cube_Contract failed (%r).", exc)
        results.append({"table": "cube_Contract", "columns_checked": ["product_id"], "status": "QUERY_FAILED",
                         "n_items_present": None, "n_rows": None, "total_qty_by_col": None})

    result_df = pd.DataFrame(results)
    result_df.to_csv(out("3_other_tables_summary.csv"), index=False)
    return result_df


if __name__ == "__main__":
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    config = load_config()
    full_scope, scope = step1_scope(config)
    inv_full = step2_inventory_pull(full_scope)

    unit_cost = compute_unit_cost_metrics1(full_scope["itemcode"].tolist(),
                                            config["phase_e1_assumptions"]["unit_cost_median_window_months"])
    unit_cost.rename(columns={"itemcode": "itemcode"}, inplace=True)
    unit_cost.to_csv(out("0_unit_cost.csv"), index=False)
    logger.info("unit_cost (METRICS.md Sec.1): %d/%d full-registry items priced.",
                int((~unit_cost["no_unit_cost_item"]).sum()), len(unit_cost))

    p1 = part1_reverse_and_crosstab(inv_full, scope, unit_cost)
    target_warehouses = sorted(p1["cross"]["warehouse"].unique())
    p2 = part2_shared_warehouses(inv_full, unit_cost, target_warehouses)
    p3 = part3_other_tables(scope)

    logger.info("DONE. Outputs written to output/summary/phaseE2_*.csv")
