"""Phase C -- characterise the 89 no-history pricelist codes not yet covered by config.yaml's
excluded_item_codes / placeholder_item_codes lists (STATUS.md, "No-history recount", 2026-09-04:
105 of 445 codes have zero Omni-Channel rows anywhere on the new (unfiltered) basis; 16 are
already covered by the existing config lists, 89 are not).

This is a CHARACTERISATION task only (per AGENTS.md Validator boundary and the task brief) -- it
does NOT choose exclude/placeholder/other for any of the 89 codes. It gathers, per code:
  1. sheet + Product Type (from the pricelist)
  2. count of sibling codes (same sheet, same Type) that DO have Omni-Channel history
  3. concentration of that Type (top-item share of Type value, among items with history)
  4. presence/absence in Cube_CES, Cube_Inventory_Exact, Cube_Quotation (column names confirmed
     directly per table, not assumed)
  5. whether the code also appears on a HIDDEN "Version1" pricelist sheet (read directly with
     openpyxl here -- pricelist_reader.py is deliberately visible-sheets-only and is not modified)

Investigation script only -- no pipeline code touched, no config changed. Writes CSVs to
output/summary/, prefixed phaseC_89items_.
"""
import logging
import os
import sys

import numpy as np
import openpyxl
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query  # noqa: E402
from pricelist_reader import _find_col, _HEADER_ROW, _DATA_START_ROW, _REQUIRED_HEADERS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_89items")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PRICELIST_PATH = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")
CONSOLIDATED_445_CSV = os.path.join(SUMMARY_DIR, "phaseC_revalidation_06_consolidated_item_status_445.csv")

SOURCE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"
INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"
QUOT_TABLE = "[salewarehouse].[dbo].[Cube_Quotation]"

DOMINATED_THRESHOLD_PCT = 60.0  # matches this project's own reference point (Fuse Cutout Type's
                                 # ~60%-share focus item, cited in the task brief) -- a stated
                                 # judgment call, not derived from this data.


def out(name):
    return os.path.join(SUMMARY_DIR, f"phaseC_89items_{name}")


def sql_in(codes):
    return "','".join(c.replace("'", "''") for c in codes)


# ============================================================================
# Step 1: load the 89-item population, confirm the count
# ============================================================================
def load_population():
    logger.info("=== STEP 1: load 89-item population from %s ===", CONSOLIDATED_445_CSV)
    full = pd.read_csv(CONSOLIDATED_445_CSV)
    pop = full[
        (~full["has_omni_history_new_basis"])
        & (~full["in_config_excluded_item_codes"])
        & (~full["in_config_placeholder_item_codes"])
    ].copy()
    logger.info("Population size: %d (expected 89)", len(pop))
    if len(pop) != 89:
        raise ValueError(
            f"Expected exactly 89 codes in the population, found {len(pop)}. Stopping per the "
            f"task's explicit instruction to report a discrepancy rather than silently adjust."
        )
    return pop, full


# ============================================================================
# Step 2/3: siblings-with-history count + Type concentration
# ============================================================================
def compute_type_value(full_scope: pd.DataFrame) -> pd.DataFrame:
    """Query per-item Omni-Channel value (corrected, no-division-filter basis) for every code in
    every (sheet, type) group touched by the 89-item population, so sibling-with-history counts
    and Type concentration can be computed from a fresh, independent query (not by reusing the
    445-code CSV's boolean has_omni_history flag alone)."""
    logger.info("=== STEP 2/3: per-item Omni-Channel value for every code sharing a (sheet, type) "
                "with a population item ===")
    pop_types = full_scope.loc[
        (~full_scope["has_omni_history_new_basis"])
        & (~full_scope["in_config_excluded_item_codes"])
        & (~full_scope["in_config_placeholder_item_codes"]),
        ["sheet", "type"],
    ].drop_duplicates()
    logger.info("Distinct (sheet, type) groups touched by the 89-item population: %d", len(pop_types))

    relevant = full_scope.merge(pop_types, on=["sheet", "type"], how="inner")
    all_codes_in_relevant_types = sorted(relevant["code"].unique().tolist())
    logger.info("Total codes across these %d (sheet, type) groups (89-item codes + their siblings): %d",
                len(pop_types), len(all_codes_in_relevant_types))

    q = f"""
        SELECT itemcode, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty, COUNT(*) AS n_rows
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{sql_in(all_codes_in_relevant_types)}')
          AND revenue_type = 'Omni Channel'
          AND status IN ('Actual','MPS')
        GROUP BY itemcode
    """
    vals = run_query(q)
    logger.info("Per-item Omni-Channel value pulled for %d of %d codes in these Type groups "
                "(codes absent from this result have zero rows).", len(vals), len(all_codes_in_relevant_types))

    value_by_code = dict(zip(vals["itemcode"], vals["sum_sale"]))
    relevant = relevant.copy()
    relevant["sum_sale"] = relevant["code"].map(value_by_code).fillna(0.0)
    relevant["has_history_confirmed"] = relevant["sum_sale"] > 0
    relevant.to_csv(out("00_type_group_value_detail.csv"), index=False)
    return relevant


def siblings_and_concentration(pop: pd.DataFrame, relevant: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in pop.iterrows():
        code, sheet, typ = r["code"], r["sheet"], r["type"]
        grp = relevant[(relevant["sheet"] == sheet) & (relevant["type"] == typ)]
        siblings = grp[grp["code"] != code]
        siblings_with_history = siblings[siblings["has_history_confirmed"]]
        n_siblings_total = len(siblings)
        n_siblings_with_history = len(siblings_with_history)

        with_hist_all = grp[grp["has_history_confirmed"]]  # includes the item itself if it had
                                                             # history (it never will, by construction)
        total_type_value = with_hist_all["sum_sale"].sum()
        if len(with_hist_all) == 0:
            top_share_pct = None
            top_item = None
        else:
            top_row = with_hist_all.loc[with_hist_all["sum_sale"].idxmax()]
            top_item = top_row["code"]
            top_share_pct = round(100.0 * top_row["sum_sale"] / total_type_value, 2) if total_type_value else None

        rows.append({
            "code": code, "sheet": sheet, "type": typ,
            "n_siblings_total": n_siblings_total,
            "n_siblings_with_history": n_siblings_with_history,
            "type_total_value_thb": total_type_value,
            "type_top_item": top_item,
            "type_top_item_share_pct": top_share_pct,
        })
    result = pd.DataFrame(rows)
    result.to_csv(out("01_siblings_and_concentration.csv"), index=False)
    return result


# ============================================================================
# Step 4: presence/absence in Cube_CES, Cube_Inventory_Exact, Cube_Quotation
# ============================================================================
def multi_table_trace(codes):
    logger.info("=== STEP 4: Cube_CES / Cube_Inventory_Exact / Cube_Quotation trace ===")
    cl = sql_in(codes)

    # Cube_CES -- column confirmed directly: ItemCode (schema pulled live above in this
    # investigation session; also matches every other script in this project that queries this table).
    # NOTE: deliberately NOT deriving a $ value from ActualPrice/BacklogPrice * qty here -- a spot
    # check on CA-F-99-010304 found ActualQty=1336, ActualPrice=6,546,400 -> a naive qty*price
    # would be ~8.7 BILLION THB for one row, clearly not a per-unit price this table stores that
    # way (CONVENTIONS.md: validate before use, negative/out-of-range values must be caught, not
    # silently trusted). This project's own precedent (task2_no_history_investigation.py Q3) only
    # ever sums ActualQty/BacklogQty from Cube_CES, never a derived $ value -- followed here too.
    q_ces = f"""
        SELECT ItemCode AS itemcode, COUNT(*) AS n_ces_rows,
               SUM(CASE WHEN Status = 'Actual' THEN 1 ELSE 0 END) AS n_ces_actual,
               SUM(CASE WHEN Status = 'Backlog' THEN 1 ELSE 0 END) AS n_ces_backlog,
               SUM(CASE WHEN Status NOT IN ('Actual','Backlog') THEN 1 ELSE 0 END) AS n_ces_pipeline_other,
               SUM(CASE WHEN Status = 'Actual' THEN ISNULL(ActualQty,0) ELSE 0 END) AS sum_ces_actual_qty,
               SUM(CASE WHEN Status = 'Backlog' THEN ISNULL(BacklogQty,0) ELSE 0 END) AS sum_ces_backlog_qty,
               MAX(CtrDate) AS last_ctrdate,
               COUNT(DISTINCT RevenueType) AS n_distinct_revenue_types,
               COUNT(DISTINCT ManuDivision) AS n_distinct_manu_division,
               COUNT(DISTINCT SaleDivision) AS n_distinct_sale_division
        FROM {CES_TABLE}
        WHERE ItemCode IN ('{cl}')
        GROUP BY ItemCode
    """
    ces = run_query(q_ces)
    ces.to_csv(out("02_ces_summary.csv"), index=False)
    logger.info("Cube_CES: %d of %d codes have >=1 row.", len(ces), len(codes))

    # detail: revenue_type / manu_division / sale_division actually carried, for classification evidence
    q_ces_detail = f"""
        SELECT ItemCode AS itemcode, Status, RevenueType, ManuDivision, SaleDivision,
               COUNT(*) AS n_rows, MAX(CtrDate) AS max_ctrdate
        FROM {CES_TABLE}
        WHERE ItemCode IN ('{cl}')
        GROUP BY ItemCode, Status, RevenueType, ManuDivision, SaleDivision
        ORDER BY ItemCode
    """
    ces_detail = run_query(q_ces_detail)
    ces_detail.to_csv(out("02b_ces_detail.csv"), index=False)

    # Cube_Inventory_Exact -- column confirmed directly by querying its schema in this session:
    # lowercase 'itemcode' (not 'ItemCode').
    q_inv = f"""
        SELECT itemcode, COUNT(*) AS n_inventory_rows, SUM(stock) AS sum_stock,
               SUM(available) AS sum_available, MAX(timestamp) AS max_timestamp
        FROM {INV_TABLE}
        WHERE itemcode IN ('{cl}')
        GROUP BY itemcode
    """
    inv = run_query(q_inv)
    inv.to_csv(out("03_inventory_exact_summary.csv"), index=False)
    logger.info("Cube_Inventory_Exact: %d of %d codes have >=1 row.", len(inv), len(codes))

    # Cube_Quotation -- column confirmed directly: lowercase 'itemcode'.
    q_quot = f"""
        SELECT itemcode, COUNT(*) AS n_quotation_rows, SUM(sale) AS sum_quotation_sale,
               MAX(create_date) AS max_create_date,
               COUNT(DISTINCT quotation_status) AS n_distinct_quotation_status,
               COUNT(DISTINCT revenue_type) AS n_distinct_revenue_type,
               COUNT(DISTINCT division) AS n_distinct_division
        FROM {QUOT_TABLE}
        WHERE itemcode IN ('{cl}')
        GROUP BY itemcode
    """
    quot = run_query(q_quot)
    quot.to_csv(out("04_quotation_summary.csv"), index=False)
    logger.info("Cube_Quotation: %d of %d codes have >=1 row.", len(quot), len(codes))

    q_quot_detail = f"""
        SELECT itemcode, quotation_status, revenue_type, division, COUNT(*) AS n_rows,
               SUM(sale) AS sum_sale, MAX(create_date) AS max_create_date
        FROM {QUOT_TABLE}
        WHERE itemcode IN ('{cl}')
        GROUP BY itemcode, quotation_status, revenue_type, division
        ORDER BY itemcode
    """
    quot_detail = run_query(q_quot_detail)
    quot_detail.to_csv(out("04b_quotation_detail.csv"), index=False)

    return ces, ces_detail, inv, quot, quot_detail


# ============================================================================
# Step 5: hidden Version1 sheet check (ad hoc openpyxl read of ALL sheets, visible+hidden --
# pricelist_reader.py deliberately not modified/reused for hidden sheets)
# ============================================================================
def read_all_sheets_with_state(path):
    logger.info("=== STEP 5: reading ALL pricelist sheets (visible + hidden) directly with openpyxl ===")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    records = []
    for name in wb.sheetnames:
        ws = wb[name]
        rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))
        if len(rows) < _HEADER_ROW:
            logger.info("Skipping sheet %r: fewer than %d rows", name, _HEADER_ROW)
            continue
        header = rows[_HEADER_ROW - 1]
        code_idx = _find_col(header, _REQUIRED_HEADERS["code"])
        if code_idx is None:
            logger.info("Skipping sheet %r (state=%r): no 'Product Code' column found", name, ws.sheet_state)
            continue
        data_rows = rows[_DATA_START_ROW - 1:]
        for r in data_rows:
            code = r[code_idx] if code_idx < len(r) else None
            if code is None or str(code).strip() == "":
                continue
            records.append({"sheet": name, "sheet_state": ws.sheet_state, "code": str(code).strip()})
    df = pd.DataFrame.from_records(records)
    logger.info("Total rows across ALL sheets (visible+hidden): %d", len(df))
    logger.info("Sheets found:\n%s", df.groupby(["sheet", "sheet_state"]).size().to_string())
    return df


def hidden_version_check(codes, all_sheets_df):
    sub = all_sheets_df[all_sheets_df["code"].isin(codes)]
    sub.to_csv(out("05_all_sheets_membership_89items.csv"), index=False)
    rows = []
    for code in codes:
        code_rows = sub[sub["code"] == code]
        hidden_sheets = sorted(code_rows[code_rows["sheet_state"] == "hidden"]["sheet"].unique().tolist())
        visible_sheets = sorted(code_rows[code_rows["sheet_state"] == "visible"]["sheet"].unique().tolist())
        rows.append({
            "code": code,
            "in_hidden_version1_sheet": len(hidden_sheets) > 0,
            "hidden_sheets": hidden_sheets,
            "visible_sheets": visible_sheets,
        })
    return pd.DataFrame(rows)


# ============================================================================
# Step 6: assemble final per-item table + pattern grouping
# ============================================================================
def classify_pattern(row):
    """Group each of the 89 items into the patterns the task brief describes. Grouping logic is
    stated explicitly here so it can be checked/adjusted -- not a hidden rule."""
    has_ces_real = row["n_ces_actual"] > 0 or row["n_ces_backlog"] > 0
    has_quotation = row["n_quotation_rows"] > 0
    has_inventory = row["n_inventory_rows"] > 0
    has_any_trace = has_ces_real or has_quotation or has_inventory or row["n_ces_pipeline_other"] > 0

    if not has_any_trace:
        return "Listed but no trace anywhere (matches excluded_item_codes reasoning pattern)"

    if has_ces_real or has_quotation:
        # real Actual/Backlog CES rows, or a quotation row, exist -- distinguish "outside this
        # project's Omni-Channel/CI101-division-family filter" if the trace carries a
        # non-Omni-Channel revenue_type or a manufacturing/sale division unrelated to the code's
        # own pricelist sheet.
        if has_ces_real:
            return "Sold only outside this project's filter (Cube_CES Actual/Backlog trace exists, matches placeholder_item_codes reasoning pattern)"
        return "Sold only outside this project's filter (Cube_Quotation trace exists, no confirmed Actual/Backlog sale)"

    # only pipeline-stage CES rows and/or inventory rows, no confirmed Actual/Backlog sale or quotation
    return "Listed, only pipeline-stage/inventory trace, no confirmed sale (weak evidence, not classified as (b) or (d))"


def sibling_pattern(row):
    if pd.isna(row["type"]):
        return "Type undefined in pricelist (blank Product Type) -- sibling/concentration analysis inapplicable"
    if row["n_siblings_with_history"] == 0:
        return "No siblings with history"
    if row["type_top_item_share_pct"] is None:
        return "Undefined (no item in Type has history)"  # should not occur when n_siblings_with_history>0
    if row["n_siblings_with_history"] == 1:
        return "Dominated Type (single sibling holds all Type value)"
    if row["type_top_item_share_pct"] >= DOMINATED_THRESHOLD_PCT:
        return f"Dominated Type (top item >={DOMINATED_THRESHOLD_PCT:.0f}% share)"
    return "Balanced Type (multiple siblings, no single dominant item)"


def main():
    pop, full = load_population()
    relevant = compute_type_value(full)
    sib = siblings_and_concentration(pop, relevant)

    codes = sorted(pop["code"].unique().tolist())
    ces, ces_detail, inv, quot, quot_detail = multi_table_trace(codes)

    all_sheets_df = read_all_sheets_with_state(PRICELIST_PATH)
    hidden = hidden_version_check(codes, all_sheets_df)

    # assemble
    final = pop[["code", "sheet", "category", "type"]].merge(sib.drop(columns=["sheet", "type"]), on="code", how="left")
    final = final.merge(ces, left_on="code", right_on="itemcode", how="left").drop(columns=["itemcode"])
    final = final.merge(inv, left_on="code", right_on="itemcode", how="left").drop(columns=["itemcode"])
    final = final.merge(quot, left_on="code", right_on="itemcode", how="left").drop(columns=["itemcode"])
    final = final.merge(hidden, on="code", how="left")

    for c in ["n_ces_rows", "n_ces_actual", "n_ces_backlog", "n_ces_pipeline_other",
              "sum_ces_actual_qty", "sum_ces_backlog_qty",
              "n_inventory_rows", "sum_stock", "sum_available",
              "n_quotation_rows", "sum_quotation_sale"]:
        final[c] = final[c].fillna(0)

    final["sibling_pattern"] = final.apply(sibling_pattern, axis=1)
    final["trace_pattern"] = final.apply(classify_pattern, axis=1)

    # Flag items whose Cube_CES Actual/Backlog rows include an Omni-Channel-tagged row -- these
    # do NOT cleanly fit "sold outside this project's filter" (that story requires a
    # non-Omni-Channel/non-project trace); a real Actual/Backlog Omni-Channel row in Cube_CES with
    # no counterpart in cube_Sale_APD (checked on the full-history, no-date-filter basis in Part A/
    # the revalidation script) is instead an unexplained cross-table gap. Reported, not resolved.
    real_ces = ces_detail[ces_detail["Status"].isin(["Actual", "Backlog"])]
    omni_ces_items = set(real_ces[real_ces["RevenueType"] == "Omni Channel"]["itemcode"].unique())
    final["ces_actual_backlog_has_omni_channel_row"] = final["code"].isin(omni_ces_items)

    final.to_csv(out("characterization.csv"), index=False)
    logger.info("Wrote %s (%d rows)", out("characterization.csv"), len(final))

    print("\n=== Sibling pattern counts ===")
    print(final["sibling_pattern"].value_counts().to_string())
    print("\n=== Trace pattern counts ===")
    print(final["trace_pattern"].value_counts().to_string())
    print("\n=== Cross-tab ===")
    print(pd.crosstab(final["sibling_pattern"], final["trace_pattern"]).to_string())
    print("\n=== Hidden-version1 presence ===")
    print(final["in_hidden_version1_sheet"].value_counts().to_string())

    return final


if __name__ == "__main__":
    main()
