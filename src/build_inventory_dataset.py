"""Builds data/inventory.json for the new Inventory detail view.

Read-only against the database (SELECT only). Does not touch index.html.

Step 1: builds the FULL pricelist product-code registry (every code the company sells, from
every VISIBLE sheet in reference/pricelist.xlsx -- same visibility convention as
src/pricelist_reader.py), not the 335-item forecast scope. Business/Category/Type/Description
come from the pricelist's own columns (CONVENTIONS.md: the pricelist is authoritative for these
attributes; the database's division tag is never used).

Step 2: joins the full registry to Cube_Inventory_Exact (chosen over Cube_Inventory_Aging and
cube_inventory_tran in the prior read-only investigation -- see
output/summary/inventory_source_investigation_report.md Part 1d -- because it has a verified
unique (company, warehouse, itemcode) grain and a directly-readable `stock` column, unlike
Aging's GL-account-duplicated rows or the tran ledger's derived-balance requirement).

Step 2B: joins the same registry to outstanding customer backlog from Cube_Backlog, filtered to
`sale_company IN ('PEM','CI')` so the demand side covers the same company scope as the supply
side (Cube_Inventory_Exact holds exactly two company values, PEM and CI -- see
output/summary/company_scope_investigation_report.md). NO status filter is applied: every row in
Cube_Backlog is already outstanding (`viewType = 'CTR/PO to be delivered'` table-wide, and the
table carries no delivered/cancelled status value at all -- see
output/summary/reserved_available_investigation_report.md Part 2b). `available` is then
on-hand minus backlog, never clamped: a negative means outstanding orders exceed stock on hand.
Each item also carries `backlog_rows`: the individual Cube_Backlog rows behind its total, as-is and
never de-duplicated, so a reviewer can judge each row for themselves. Every item's rows are asserted
to sum exactly to that item's backlog total.

Step 3: classifies each warehouse's role (staging vs holding vs unknown) from
cube_inventory_tran transfer-pair evidence only -- never from the warehouse code's name.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_inventory_dataset")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SCOPE_335_FILE = os.path.join(PROJECT_ROOT, "output", "summary", "phaseC_step2_scope_335items.csv")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "inventory.json")
SOURCE_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"
TRAN_TABLE = "[salewarehouse].[dbo].[cube_inventory_tran]"
BACKLOG_TABLE = "[salewarehouse].[dbo].[Cube_Backlog]"
BACKLOG_SALE_COMPANIES = ["PEM", "CI"]
# Rows sharing every one of these values but sitting under different docID (contract) numbers are
# the cross-contract duplicate-recording pattern documented in
# output/summary/reserve_backlog_relationship_report.md. Used for DIAGNOSTICS ONLY here -- the
# backlog figure written to JSON is the as-is sum, not de-duplicated.
BACKLOG_DEDUP_KEY = ["itemcode", "quantity", "status", "deliverydate", "plan_deliverydate"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------------------------
# STEP 1 -- full pricelist code registry
# --------------------------------------------------------------------------------------------

def build_full_registry(config: dict) -> pd.DataFrame:
    """Returns one row per code: code, business, category, type, description, sheet, division.

    business/category/type/description are the pricelist's own column values (never the
    database's division tag). division is business, kept as a separate column name for
    clarity when joined with the 335-item scope file (which uses `division`).
    """
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    df = load_visible_product_rows(pricelist_path)
    per_sheet_counts = df.groupby("sheet")["code"].nunique().to_dict()
    logger.info("Loaded %d product rows from visible pricelist sheets. Unique codes per sheet: %s",
                len(df), per_sheet_counts)

    dupes = df[df.duplicated(subset=["sheet", "code"], keep=False)]
    if len(dupes):
        logger.info("%d duplicate (sheet, code) rows found -- keeping the first occurrence per code, "
                     "dropping the rest. Duplicates: %s",
                     len(dupes), dupes[["sheet", "code", "description"]].to_dict("records"))
    df = df.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)

    sheet_to_division = config["sheet_to_division"]
    unmapped_sheets = set(df["sheet"].unique()) - set(sheet_to_division.keys())
    if unmapped_sheets:
        raise ValueError(f"Sheets with product rows but no sheet_to_division mapping: {unmapped_sheets}")

    mismatch = df[df["business"].astype(str).str.strip() != df["sheet"].map(sheet_to_division).astype(str).str.strip()]
    if len(mismatch):
        raise ValueError(f"{len(mismatch)} rows where pricelist 'Business' column disagrees with "
                          f"config sheet_to_division: {mismatch[['sheet', 'code', 'business']].to_dict('records')}")

    n_null_type = df["type"].isna().sum()
    if n_null_type:
        logger.info("%d codes have a null Product Type in the pricelist (not invented, left null): %s",
                     n_null_type, df[df["type"].isna()]["code"].tolist())

    logger.info("Full registry: %d unique codes across %d sheets: %s",
                len(df), df["sheet"].nunique(), per_sheet_counts)
    return df


def reconcile_against_335(registry: pd.DataFrame) -> pd.DataFrame:
    """Adds in_forecast_scope + exclusion_reason columns. Raises if 335 is not a strict subset."""
    scope = pd.read_csv(SCOPE_335_FILE)
    scope_codes = set(scope["code"])
    full_codes = set(registry["code"])

    not_in_full = scope_codes - full_codes
    if not_in_full:
        raise ValueError(f"{len(not_in_full)} codes in the 335-item scope are NOT in the full "
                          f"pricelist registry -- 335 is not a strict subset, stopping: {not_in_full}")

    registry = registry.copy()
    registry["in_forecast_scope"] = registry["code"].isin(scope_codes)
    missing = registry[~registry["in_forecast_scope"]]
    logger.info("335-item scope check: %d/%d scope codes found in full registry (subset OK). "
                "%d full-registry codes are outside the 335 scope.", len(scope_codes) - len(not_in_full),
                len(scope_codes), len(missing))

    config = load_config()
    excluded = set(config["excluded_item_codes"])
    placeholder = set(config["placeholder_item_codes"])
    placeholder82 = set(config["placeholder_item_assignments_82"].keys())

    def reason(row):
        if row["in_forecast_scope"]:
            return None
        if row["business"] == "PEM104":
            return ("PEM104 division excluded from forecasting -- data-volume reason (only 12 "
                     "transactions across 17 months); see config.yaml divisions_excluded_from_forecasting")
        if row["code"] in excluded:
            return ("excluded_item_codes: listed in pricelist but never sold -- zero rows in "
                     "cube_Sale_APD, Cube_CES, cube_inventory_tran, Cube_Inventory_Exact, or Cube_Quotation")
        if row["code"] in placeholder:
            return "placeholder_item_codes: sold only outside this project's scope, or unclassifiable"
        if row["code"] in placeholder82:
            return "placeholder_item_assignments_82: no-history item, placeholder rule A/B/C assigned"
        return "NO RECORDED REASON FOUND IN REPO"

    registry["exclusion_reason"] = registry.apply(reason, axis=1)
    missing = registry[~registry["in_forecast_scope"]]
    unexplained = missing[missing["exclusion_reason"] == "NO RECORDED REASON FOUND IN REPO"]
    if len(unexplained):
        logger.warning("%d codes are outside the 335 scope with NO recorded reason found anywhere in the "
                        "repo -- reporting as unexplained rather than guessing: %s",
                        len(unexplained), unexplained["code"].tolist())
    else:
        logger.info("All %d codes outside the 335 scope have a recorded reason in the repo.", len(missing))

    by_division_reason = missing.groupby(["business", "exclusion_reason"]).size()
    logger.info("Missing codes grouped by division and reason:\n%s", by_division_reason.to_string())
    return registry


# --------------------------------------------------------------------------------------------
# STEP 2 -- join to on-hand stock
# --------------------------------------------------------------------------------------------

def query_inventory_exact(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT company, warehouse, itemcode, unit, stock, reserve_bywa, timestamp
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    n_padded = (df["warehouse"] != df["warehouse"].str.strip()).sum()
    if n_padded:
        logger.info("%d of %d rows have a fixed-width-padded warehouse code (e.g. 'QA  ') -- "
                     "stripped to 'QA' etc. before any grouping/output.", n_padded, len(df))
    df["warehouse"] = df["warehouse"].str.strip()
    logger.info("Pulled %d rows from %s for %d item codes.", len(df), SOURCE_TABLE, len(item_codes))
    dupe_grain = df.groupby(["company", "warehouse", "itemcode"]).size()
    dupe_grain = dupe_grain[dupe_grain > 1]
    if len(dupe_grain):
        logger.warning("%d (company, warehouse, itemcode) combinations have more than one row in %s "
                        "after stripping warehouse padding -- summed, not dropped, downstream.",
                        len(dupe_grain), SOURCE_TABLE)
    return df


def classify_stock_state(registry: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    per_code_total = inv.groupby("itemcode", as_index=False)["stock"].sum().rename(
        columns={"itemcode": "code", "stock": "qty"})
    merged = registry.merge(per_code_total, on="code", how="left")

    def state(row):
        if pd.isna(row["qty"]):
            return "no_db_record"
        if row["qty"] > 0:
            return "has_stock"
        return "zero_stock"

    merged["state"] = merged.apply(state, axis=1)
    # qty must be null (None), never 0, for no_db_record.
    merged.loc[merged["state"] == "no_db_record", "qty"] = None
    return merged


def report_snapshot_timestamp(inv: pd.DataFrame) -> dict:
    ts = pd.to_datetime(inv["timestamp"])
    distinct_dates = sorted(ts.dt.date.unique().tolist())
    distinct_timestamps = ts.nunique()
    single_date = len(distinct_dates) == 1
    logger.info(
        "Snapshot timestamp: %d distinct exact timestamps across %d distinct date(s) (%s). "
        "Range: %s to %s.",
        distinct_timestamps, len(distinct_dates), distinct_dates, ts.min(), ts.max(),
    )
    return {
        "min_timestamp": str(ts.min()),
        "max_timestamp": str(ts.max()),
        "distinct_dates": [str(d) for d in distinct_dates],
        "distinct_timestamps": int(distinct_timestamps),
        "single_date": bool(single_date),
    }


# --------------------------------------------------------------------------------------------
# STEP 2B -- outstanding backlog + available
# --------------------------------------------------------------------------------------------

def query_backlog(item_codes: list) -> pd.DataFrame:
    """Outstanding customer backlog rows for the registry codes, scoped to PEM + CI.

    No status filter: every Cube_Backlog row is already outstanding. `sale_company` is compared
    after stripping, because the column is fixed-width padded like `warehouse` is.
    """
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT id, docID, job, customer, itemcode, quantity, status, viewType, sale_company,
               sale_division, deliverydate, plan_deliverydate, receivedate, backlog_from, timestamp
        FROM {BACKLOG_TABLE}
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    df["sale_company"] = df["sale_company"].astype(str).str.strip()

    non_outstanding = df[df["viewType"].astype(str).str.strip() != "CTR/PO to be delivered"]
    if len(non_outstanding):
        logger.warning(
            "%d of %d backlog rows do NOT carry viewType='CTR/PO to be delivered' -- the "
            "no-status-filter assumption (every row is outstanding) rests on that value being "
            "universal. Counted anyway, per the instruction that all statuses count, but this "
            "needs re-checking: %s",
            len(non_outstanding), len(df), sorted(non_outstanding["viewType"].unique().tolist()))

    kept = df[df["sale_company"].isin(BACKLOG_SALE_COMPANIES)].copy()
    logger.info(
        "Pulled %d backlog rows from %s for the registry codes; %d rows kept after "
        "sale_company IN %s, %d rows dropped (%s). Status values kept (no filter applied): %s",
        len(df), BACKLOG_TABLE, len(kept), BACKLOG_SALE_COMPANIES, len(df) - len(kept),
        df[~df["sale_company"].isin(BACKLOG_SALE_COMPANIES)]["sale_company"].value_counts().to_dict(),
        kept["status"].value_counts().to_dict())
    return kept


def aggregate_backlog(backlog: pd.DataFrame) -> pd.DataFrame:
    """One row per code: summed outstanding quantity across all its backlog lines.

    Cube_Backlog's grain is one row per scheduled delivery line within a contract-item, so a code's
    total must sum every matching row -- never take a single row's value.
    """
    return backlog.groupby("itemcode", as_index=False)["quantity"].sum().rename(
        columns={"itemcode": "code", "quantity": "backlog"})


def _clean_str(v) -> str:
    """Source columns are fixed-width padded varchars; nulls must stay null, not become 'None'."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return None
    s = str(v).strip()
    return s if s else None


def _clean_date(v) -> str:
    """Dates as plain ISO strings (date-only for `deliverydate`, which is a DATE column;
    plan_deliverydate is a DATETIME whose time part is carried through as-is)."""
    if v is None or pd.isna(v):
        return None
    ts = pd.to_datetime(v)
    if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
        return ts.strftime("%Y-%m-%d")
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def build_backlog_rows(backlog: pd.DataFrame) -> dict:
    """code -> [the individual Cube_Backlog rows behind that code's total], NOT de-duplicated.

    Every row is carried through exactly as the source holds it, including rows that duplicate
    another row's (quantity, status, deliverydate) under a different docID -- surfacing those to a
    human reviewer is the entire point of this per-row view, so collapsing them here would destroy
    the thing it exists to show.
    """
    out = {}
    for itemcode, grp in backlog.groupby("itemcode"):
        rows = []
        for _, r in grp.iterrows():
            rows.append({
                "doc_id": _clean_str(r["docID"]),
                "job": _clean_str(r["job"]),
                "customer": _clean_str(r["customer"]),
                "quantity": float(r["quantity"]),
                "status": _clean_str(r["status"]),
                "delivery_date": _clean_date(r["deliverydate"]),
                "plan_delivery_date": _clean_date(r["plan_deliverydate"]),
                "backlog_from": _clean_str(r["backlog_from"]),
            })
        out[itemcode] = rows
    return out


def assert_backlog_rows_sum(classified: pd.DataFrame, backlog_rows: dict) -> list:
    """Every item's per-row detail must sum exactly to the `backlog` total written for that item.

    Checks in both directions: no item carries rows that overshoot or undershoot its total, and no
    item with a non-zero total is missing its rows.
    """
    mismatches = []
    for _, row in classified.iterrows():
        code, total = row["code"], float(row["backlog"])
        rows = backlog_rows.get(code, [])
        row_sum = sum(r["quantity"] for r in rows)
        if abs(row_sum - total) > 1e-6:
            mismatches.append({"code": code, "total": total, "row_sum": row_sum,
                               "n_rows": len(rows)})
        if total > 0 and not rows:
            mismatches.append({"code": code, "total": total, "row_sum": 0.0, "n_rows": 0})
    return mismatches


def add_backlog_and_available(classified: pd.DataFrame, backlog_per_code: pd.DataFrame) -> pd.DataFrame:
    """Adds `backlog` (0 when a code has no backlog rows) and `available` (on-hand minus backlog,
    never clamped; null when on-hand itself is unknown because the code has no stock record).
    """
    merged = classified.merge(backlog_per_code, on="code", how="left")
    merged["backlog"] = merged["backlog"].fillna(0.0)
    merged["available"] = merged["qty"] - merged["backlog"]
    merged.loc[merged["state"] == "no_db_record", "available"] = None
    return merged


def query_backlog_unfiltered(item_codes: list) -> pd.DataFrame:
    """The same registry-code backlog rows WITHOUT the sale_company filter, so the run can report
    exactly what the filter removed. Diagnostics only -- never used for the written figure."""
    code_list = "','".join(sorted(item_codes))
    df = run_query(f"""
        SELECT id, docID, itemcode, quantity, status, sale_company, sale_division,
               deliverydate, plan_deliverydate, receivedate
        FROM {BACKLOG_TABLE}
        WHERE itemcode IN ('{code_list}')
    """)
    df["sale_company"] = df["sale_company"].astype(str).str.strip()
    return df


def classify_negative_causes(negatives: pd.DataFrame, flagged_backlog: pd.DataFrame) -> pd.DataFrame:
    """Assigns each negative-available code a most-likely cause from row-level evidence.

    Order matters: the duplicate test runs first, because a code whose backlog is inflated by
    duplicate rows would otherwise be misread as genuine excess demand.
    """
    dup_by_code = flagged_backlog[flagged_backlog["is_cross_contract_duplicate"]].groupby("itemcode")
    dup_qty = dup_by_code["quantity"].sum().to_dict()
    dup_rows = dup_by_code.size().to_dict()
    dup_docids = dup_by_code["docID"].apply(lambda s: sorted(set(s))).to_dict()

    # DELIVERYORDER's meaning is unresolved -- it may mean "already physically shipped" (in which
    # case those units should not count as outstanding at all) or "delivery order raised, not yet
    # shipped". A negative that only exists because of such rows cannot be called either way.
    do = flagged_backlog[flagged_backlog["status"].astype(str).str.strip() == "DELIVERYORDER"]
    do_qty = do.groupby("itemcode")["quantity"].sum().to_dict()

    rows = []
    for _, r in negatives.iterrows():
        code, qty, backlog, available = r["code"], r["qty"], r["backlog"], r["available"]
        dedup_available = qty - (backlog - dup_qty.get(code, 0.0))
        if code in dup_qty and dedup_available >= 0:
            cause = "duplicate backlog rows"
            evidence = (f"{dup_rows[code]} rows sharing {BACKLOG_DEDUP_KEY} across docIDs "
                        f"{dup_docids[code]} contribute {dup_qty[code]:,.0f} units; removing them "
                        f"leaves {backlog - dup_qty[code]:,.0f} backlog against {qty:,.0f} on hand, "
                        f"i.e. available {dedup_available:,.0f} -- no longer negative")
        elif code in dup_qty:
            cause = "duplicate backlog rows (partial)"
            evidence = (f"{dup_rows[code]} duplicate rows across docIDs {dup_docids[code]} "
                        f"contribute {dup_qty[code]:,.0f} units, but removing them still leaves "
                        f"{backlog - dup_qty[code]:,.0f} backlog against {qty:,.0f} on hand "
                        f"(available {dedup_available:,.0f}) -- duplication is only part of it")
        elif code in do_qty and qty - (backlog - do_qty[code]) >= 0:
            cause = "cannot be determined (DELIVERYORDER)"
            evidence = (f"{do_qty[code]:,.0f} of the {backlog:,.0f} backlog units are "
                        f"DELIVERYORDER-status rows; if that status means already shipped this code "
                        f"is not short at all (available would be "
                        f"{qty - (backlog - do_qty[code]):,.0f}). That status's meaning is "
                        f"unresolved in the data, so the shortfall cannot be confirmed either way")
        elif qty == 0:
            cause = "backlog exists but on-hand is zero"
            evidence = (f"{backlog:,.0f} units of backlog against a stock record showing 0 on hand "
                        f"in every warehouse -- nothing can be allocated because nothing is there")
        else:
            cause = "genuine excess of orders over stock"
            evidence = (f"{backlog:,.0f} units ordered against {qty:,.0f} on hand, with no "
                        f"duplicate-key rows in the filtered backlog -- reads as real outstanding "
                        f"demand exceeding stock, not a data artifact")
        rows.append({"code": code, "qty": qty, "backlog": backlog, "available": available,
                     "cause": cause, "evidence": evidence})
    return pd.DataFrame(rows)


def flag_duplicate_backlog_rows(backlog: pd.DataFrame) -> pd.DataFrame:
    """Flags rows that share BACKLOG_DEDUP_KEY with another row under a DIFFERENT docID.

    Diagnostics only -- these rows are still counted in the written figure. Rows sharing a docID
    are legitimate multi-line delivery schedules, not duplicates, so they are not flagged.
    """
    df = backlog.copy()
    docids_per_key = df.groupby(BACKLOG_DEDUP_KEY, dropna=False)["docID"].transform("nunique")
    rows_per_key = df.groupby(BACKLOG_DEDUP_KEY, dropna=False)["docID"].transform("size")
    df["is_cross_contract_duplicate"] = (rows_per_key > 1) & (docids_per_key > 1)
    return df


# --------------------------------------------------------------------------------------------
# STEP 3 -- warehouse breakdown + role classification
# --------------------------------------------------------------------------------------------

def build_by_warehouse(inv: pd.DataFrame) -> dict:
    """code -> [{code: warehouse, qty}] for warehouses where that item's stock > 0."""
    per_item_wh = inv.groupby(["itemcode", "warehouse"], as_index=False)["stock"].sum()
    per_item_wh = per_item_wh[per_item_wh["stock"] > 0]
    out = {}
    for itemcode, grp in per_item_wh.groupby("itemcode"):
        out[itemcode] = [{"code": r["warehouse"], "qty": float(r["stock"])} for _, r in grp.iterrows()]
    return out


def query_transfer_pairs(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT itemcode, ourref, trans_date, warehouse, QtyIn, QtyOut
        FROM {TRAN_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND (QtyIn > 0 OR QtyOut > 0)
          AND ourref IS NOT NULL
    """
    df = run_query(sql)
    n_padded = (df["warehouse"] != df["warehouse"].str.strip()).sum()
    if n_padded:
        logger.info("%d of %d movement rows have a fixed-width-padded warehouse code -- stripped "
                     "before pairing.", n_padded, len(df))
    df["warehouse"] = df["warehouse"].str.strip()
    logger.info("Pulled %d movement rows from %s for %d item codes (QtyIn>0 or QtyOut>0, ourref not null).",
                len(df), TRAN_TABLE, len(item_codes))
    return df


def classify_warehouse_roles(tran: pd.DataFrame, all_warehouses: list) -> pd.DataFrame:
    """Pairs QtyOut/QtyIn legs sharing the same (itemcode, ourref, trans_date) into transfer
    edges (source_warehouse -> dest_warehouse), then flags each warehouse:
      - staging  : appears ONLY as a source across all evidenced transfers
      - holding  : appears ONLY as a destination across all evidenced transfers
      - unknown  : appears as both, or never appears in any transfer pair at all (no evidence)
    """
    out_count = {w: 0 for w in all_warehouses}
    in_count = {w: 0 for w in all_warehouses}
    n_edges = 0
    n_groups = 0
    n_paired_groups = 0
    n_rows_in_paired_groups = 0

    for (_itemcode, _ourref, _date), grp in tran.groupby(["itemcode", "ourref", "trans_date"]):
        n_groups += 1
        sources = grp[grp["QtyOut"] > 0]["warehouse"].tolist()
        dests = grp[grp["QtyIn"] > 0]["warehouse"].tolist()
        if sources and dests:
            n_paired_groups += 1
            n_rows_in_paired_groups += len(grp)
        for s in sources:
            for d in dests:
                if s == d:
                    continue
                out_count[s] = out_count.get(s, 0) + 1
                in_count[d] = in_count.get(d, 0) + 1
                n_edges += 1

    logger.info(
        "Found %d transfer edges from %d paired (itemcode, ourref, trans_date) groups (both an in-leg "
        "and an out-leg present) out of %d total groups. IMPORTANT CAVEAT: only %d of %d movement rows "
        "(%.1f%%) fall inside a paired group -- the remaining rows are singleton entries under their own "
        "ourref (e.g. issues/receipts against a job or production order) that provide NO directional "
        "transfer evidence under this method and are excluded from the role classification below. Role "
        "flags below are therefore based on a partial (~%.0f%%) sample of movement rows, not the full "
        "movement history.",
        n_edges, n_paired_groups, n_groups, n_rows_in_paired_groups, len(tran),
        100 * n_rows_in_paired_groups / len(tran) if len(tran) else 0,
        100 * n_rows_in_paired_groups / len(tran) if len(tran) else 0,
    )

    rows = []
    for w in all_warehouses:
        o, i = out_count.get(w, 0), in_count.get(w, 0)
        if o > 0 and i == 0:
            role = "staging"
        elif i > 0 and o == 0:
            role = "holding"
        else:
            role = "unknown"
        rows.append({"code": w, "out_count": o, "in_count": i, "role": role})
    result = pd.DataFrame(rows)
    logger.info("Warehouse role classification:\n%s", result.to_string(index=False))
    return result


# --------------------------------------------------------------------------------------------
# STEP 4 -- write data/inventory.json
# --------------------------------------------------------------------------------------------

def build_json(classified: pd.DataFrame, by_warehouse: dict, warehouse_roles: pd.DataFrame,
               snapshot_meta: dict, source_table: str, backlog_meta: dict,
               backlog_rows: dict) -> dict:
    warehouses = [{"code": r["code"], "role": r["role"]} for _, r in warehouse_roles.iterrows()]

    known = classified[classified["available"].notna()]
    totals = {
        "codes": int(len(classified)),
        "has_stock": int((classified["state"] == "has_stock").sum()),
        "zero_stock": int((classified["state"] == "zero_stock").sum()),
        "no_db_record": int((classified["state"] == "no_db_record").sum()),
        "codes_with_backlog": int((classified["backlog"] > 0).sum()),
        "backlog_total": float(classified["backlog"].sum()),
        "available_positive": int((known["available"] > 0).sum()),
        "available_zero": int((known["available"] == 0).sum()),
        "available_negative": int((known["available"] < 0).sum()),
        "available_unknown": int(classified["available"].isna().sum()),
        "available_total": float(known["available"].sum()),
    }

    items = []
    for _, row in classified.iterrows():
        qty = row["qty"]
        available = row["available"]
        items.append({
            "code": row["code"],
            "business": row["business"],
            "category": row["category"],
            "type": None if pd.isna(row["type"]) else row["type"],
            "description": row["description"],
            "state": row["state"],
            "qty": None if pd.isna(qty) else float(qty),
            "backlog": float(row["backlog"]),
            "available": None if pd.isna(available) else float(available),
            "in_forecast_scope": bool(row["in_forecast_scope"]),
            "by_warehouse": by_warehouse.get(row["code"], []),
            "backlog_rows": backlog_rows.get(row["code"], []),
        })

    return {
        "snapshot": {
            "source_table": source_table,
            "loaded_at": snapshot_meta["min_timestamp"],
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "refresh_cadence": "unknown",
        },
        "backlog": backlog_meta,
        "warehouses": warehouses,
        "totals": totals,
        "items": items,
    }


# --------------------------------------------------------------------------------------------
# STEP 5 -- verify
# --------------------------------------------------------------------------------------------

def verify(path: str, expected_registry_count: int, expected_totals: dict,
           expected_negative: int) -> list:
    results = []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    ok = len(items) == expected_registry_count
    results.append((f"item count ({len(items)}) equals full registry count ({expected_registry_count})", ok))

    recomputed = {"has_stock": 0, "zero_stock": 0, "no_db_record": 0}
    for it in items:
        recomputed[it["state"]] += 1
    ok = recomputed == {k: expected_totals[k] for k in recomputed}
    results.append((f"recomputed state counts {recomputed} match step 2c {[expected_totals[k] for k in recomputed]}", ok))

    bad_sum = []
    for it in items:
        if it["state"] == "has_stock":
            wh_sum = sum(w["qty"] for w in it["by_warehouse"])
            if abs(wh_sum - it["qty"]) > 1e-6:
                bad_sum.append((it["code"], wh_sum, it["qty"]))
    ok = len(bad_sum) == 0
    results.append((f"every has_stock item's by_warehouse sum equals qty ({len(bad_sum)} mismatches)", ok))

    bad_null = [it["code"] for it in items if it["state"] == "no_db_record" and it["qty"] is not None]
    ok = len(bad_null) == 0
    results.append((f"no no_db_record item has a non-null qty ({len(bad_null)} violations)", ok))

    warehouse_codes = {w["code"] for w in data["warehouses"]}
    bad_wh = []
    for it in items:
        for w in it["by_warehouse"]:
            if w["code"] not in warehouse_codes:
                bad_wh.append((it["code"], w["code"]))
    ok = len(bad_wh) == 0
    results.append((f"every by_warehouse code exists in the warehouses list ({len(bad_wh)} violations)", ok))

    bad_avail = [(it["code"], it["qty"], it["backlog"], it["available"])
                 for it in items
                 if it["qty"] is not None and it["available"] is not None
                 and abs((it["qty"] - it["backlog"]) - it["available"]) > 1e-6]
    ok = len(bad_avail) == 0
    results.append((f"available == qty - backlog for every item where both are known "
                    f"({len(bad_avail)} mismatches)", ok))

    bad_avail_null = [it["code"] for it in items
                      if it["state"] == "no_db_record" and it["available"] is not None]
    ok = len(bad_avail_null) == 0
    results.append((f"no no_db_record item has a non-null available ({len(bad_avail_null)} violations)", ok))

    bad_backlog_null = [it["code"] for it in items if it["backlog"] is None]
    ok = len(bad_backlog_null) == 0
    results.append((f"every item has a non-null backlog, 0 rather than null when it has no backlog "
                    f"row ({len(bad_backlog_null)} violations)", ok))

    bad_rows_sum = [(it["code"], sum(r["quantity"] for r in it["backlog_rows"]), it["backlog"])
                    for it in items
                    if abs(sum(r["quantity"] for r in it["backlog_rows"]) - it["backlog"]) > 1e-6]
    ok = len(bad_rows_sum) == 0
    results.append((f"every item's backlog_rows sum exactly to its backlog total "
                    f"({len(bad_rows_sum)} mismatches)", ok))

    bad_rows_missing = [it["code"] for it in items if it["backlog"] > 0 and not it["backlog_rows"]]
    ok = len(bad_rows_missing) == 0
    results.append((f"every item with backlog > 0 carries its per-row detail "
                    f"({len(bad_rows_missing)} items missing rows)", ok))

    row_fields = {"doc_id", "job", "customer", "quantity", "status", "delivery_date",
                  "plan_delivery_date", "backlog_from"}
    bad_fields = [it["code"] for it in items
                  for r in it["backlog_rows"] if set(r.keys()) != row_fields]
    ok = len(bad_fields) == 0
    results.append((f"every backlog row carries all {len(row_fields)} verification fields "
                    f"({len(bad_fields)} rows with a different field set)", ok))

    recomputed_neg = sum(1 for it in items if it["available"] is not None and it["available"] < 0)
    ok = recomputed_neg == expected_negative
    results.append((f"negative-available count in file ({recomputed_neg}) matches step 2b "
                    f"({expected_negative})", ok))

    for desc, ok in results:
        logger.info("[%s] %s", "PASS" if ok else "FAIL", desc)
    return results


def load_previous_run(path: str) -> dict:
    """Reads the JSON already on disk (the previous run) so this run can report how the headline
    figures moved. Returns None when there is no previous file to compare against."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]
    return {
        "totals": data["totals"],
        "on_hand_total": sum(it["qty"] for it in items if it["qty"] is not None),
        "snapshot_loaded_at": data["snapshot"]["loaded_at"],
        "snapshot_generated_at": data["snapshot"].get("generated_at"),
        "backlog_loaded_at": data.get("backlog", {}).get("loaded_at"),
        "file_size": os.path.getsize(path),
    }


def _delta(new: float, old: float) -> str:
    d = new - old
    if abs(d) < 1e-9:
        return "unchanged"
    return f"{d:+,.0f}"


def report_movement(previous: dict, new_totals: dict, new_on_hand: float,
                    new_snapshot: dict, new_backlog_meta: dict, new_generated_at: str) -> None:
    print(f"    this run's stock snapshot   : {new_snapshot['min_timestamp']} "
          f"(source-table timestamp, min across rows)")
    print(f"    this run's backlog snapshot : {new_backlog_meta['loaded_at']}")
    print(f"    this run generated at       : {new_generated_at}")
    if previous is None:
        print("    no previous data/inventory.json on disk -- nothing to compare against.")
        return
    print(f"    previous stock snapshot     : {previous['snapshot_loaded_at']}")
    print(f"    previous backlog snapshot   : {previous['backlog_loaded_at']}")
    print(f"    previous run generated at   : {previous['snapshot_generated_at']}")
    p = previous["totals"]
    print()
    print(f"    {'figure':<34}{'previous':>14}{'this run':>14}{'change':>14}")
    for label, key in [("has_stock", "has_stock"), ("zero_stock", "zero_stock"),
                       ("no_db_record", "no_db_record"),
                       ("codes with backlog", "codes_with_backlog"),
                       ("backlog total (units)", "backlog_total"),
                       ("codes with negative available", "available_negative")]:
        print(f"    {label:<34}{p[key]:>14,.0f}{new_totals[key]:>14,.0f}"
              f"{_delta(new_totals[key], p[key]):>14}")
    print(f"    {'on-hand total (units)':<34}{previous['on_hand_total']:>14,.0f}"
          f"{new_on_hand:>14,.0f}{_delta(new_on_hand, previous['on_hand_total']):>14}")


if __name__ == "__main__":
    config = load_config()
    previous_run = load_previous_run(OUTPUT_PATH)

    print("\n" + "=" * 78)
    print("STEP 1 — FULL PRICELIST CODE REGISTRY")
    print("=" * 78)
    registry = build_full_registry(config)
    registry = reconcile_against_335(registry)
    print(f"Source: {config['pricelist_path']}, visible sheets: {sorted(registry['sheet'].unique())}")
    print(f"Per-sheet unique code counts: {registry.groupby('sheet')['code'].nunique().to_dict()}")
    print(f"Deduplicated total: {len(registry)} unique codes "
          f"(1 within-sheet duplicate code resolved by keeping the first pricelist row)")
    n_in_scope = int(registry["in_forecast_scope"].sum())
    n_missing = len(registry) - n_in_scope
    print(f"335-scope reconciliation: {n_in_scope} of {len(registry)} full-registry codes are in the "
          f"335-item forecast scope; {n_missing} are outside it, all with a recorded reason (see log).")

    print("\n" + "=" * 78)
    print("STEP 2 — JOIN TO ON-HAND STOCK (Cube_Inventory_Exact)")
    print("=" * 78)
    item_codes = sorted(registry["code"].unique())
    inv = query_inventory_exact(item_codes)
    classified = classify_stock_state(registry, inv)
    snapshot_meta = report_snapshot_timestamp(inv)

    counts = classified["state"].value_counts().to_dict()
    has_stock = counts.get("has_stock", 0)
    zero_stock = counts.get("zero_stock", 0)
    no_db_record = counts.get("no_db_record", 0)
    checksum = has_stock + zero_stock + no_db_record
    print(f"has_stock={has_stock}  zero_stock={zero_stock}  no_db_record={no_db_record}  "
          f"sum={checksum}  registry_count={len(registry)}  match={checksum == len(registry)}")
    if checksum != len(registry):
        raise ValueError("State counts do not sum to the registry count — stopping before Step 3.")
    print(f"Snapshot timestamp range: {snapshot_meta['min_timestamp']} to {snapshot_meta['max_timestamp']} "
          f"({snapshot_meta['distinct_timestamps']} distinct timestamps, "
          f"{'single date' if snapshot_meta['single_date'] else 'MULTIPLE DATES'}: {snapshot_meta['distinct_dates']})")

    print("\n" + "=" * 78)
    print("BACKLOG STEP 1 — OUTSTANDING BACKLOG (Cube_Backlog, sale_company IN ('PEM','CI'), all statuses)")
    print("=" * 78)
    backlog_rows = query_backlog(item_codes)
    backlog_per_code = aggregate_backlog(backlog_rows)
    classified = add_backlog_and_available(classified, backlog_per_code)
    backlog_detail = build_backlog_rows(backlog_rows)

    n_backlog_codes = int((classified["backlog"] > 0).sum())
    backlog_total = float(classified["backlog"].sum())
    print(f"1a  codes with backlog > 0: {n_backlog_codes}/{len(classified)}   grand total: "
          f"{backlog_total:,.0f} units")
    print(f"    vs unfiltered (previous investigation): 155 codes / 99,132 units  ->  "
          f"{n_backlog_codes - 155:+d} codes, {backlog_total - 99132:+,.0f} units")

    n_detail_rows = sum(len(v) for v in backlog_detail.values())
    mismatches = assert_backlog_rows_sum(classified, backlog_detail)
    print(f"1a2 per-item backlog row detail: {n_detail_rows} rows carried across "
          f"{len(backlog_detail)} codes (not de-duplicated).")
    print(f"    sum check — every item's rows must total exactly its backlog figure: "
          f"{len(classified) - len(mismatches)}/{len(classified)} items PASS, "
          f"{len(mismatches)} FAIL")
    if mismatches:
        for m in mismatches[:20]:
            print(f"      MISMATCH {m['code']}: {m['n_rows']} rows summing {m['row_sum']:,.4f} "
                  f"vs total {m['total']:,.4f}")
        raise SystemExit("Per-item backlog rows do not sum to the per-item totals — stopping.")
    print(f"    rows carried ({n_detail_rows}) vs rows used for the totals ({len(backlog_rows)}): "
          f"{'MATCH' if n_detail_rows == len(backlog_rows) else 'MISMATCH'}")

    all_rows = query_backlog_unfiltered(item_codes)
    dropped_rows = len(all_rows) - len(backlog_rows)
    dropped_qty = float(all_rows["quantity"].sum() - backlog_rows["quantity"].sum())
    print(f"1b  sale_company filter removed {dropped_rows} rows / {dropped_qty:,.0f} units "
          f"(registry codes only). Removed by sale_company: "
          f"{all_rows[~all_rows['sale_company'].isin(BACKLOG_SALE_COMPANIES)]['sale_company'].value_counts().to_dict()}")

    flagged_all = flag_duplicate_backlog_rows(all_rows)
    flagged_kept = flag_duplicate_backlog_rows(backlog_rows)
    dup_all = flagged_all[flagged_all["is_cross_contract_duplicate"]]
    dup_all_inside = dup_all[dup_all["sale_company"].isin(BACKLOG_SALE_COMPANIES)]
    dup_all_outside = dup_all[~dup_all["sale_company"].isin(BACKLOG_SALE_COMPANIES)]
    dup_inside = flagged_kept[flagged_kept["is_cross_contract_duplicate"]]
    print(f"    cross-contract duplicate rows (key {BACKLOG_DEDUP_KEY}, differing docID):")
    print(f"      flagged BEFORE the filter: {len(dup_all)} rows / {dup_all['quantity'].sum():,.0f} "
          f"units, of which {len(dup_all_inside)} rows sit inside the PEM/CI set and "
          f"{len(dup_all_outside)} rows outside it")
    print(f"      still flagged AFTER the filter (key re-applied to the kept rows only): "
          f"{len(dup_inside)} rows / {dup_inside['quantity'].sum():,.0f} units")
    print(f"      the difference ({len(dup_all_inside) - len(dup_inside)} rows, "
          f"{dup_all_inside['quantity'].sum() - dup_inside['quantity'].sum():,.0f} units) is "
          f"duplicate PAIRS the filter itself broke up: one copy was tagged PEM/CI and its twin was "
          f"tagged to a dropped entity, so only one copy now survives and it is no longer a duplicate")
    if len(dup_inside):
        print(f"      -> the duplication problem STILL EXISTS after filtering, at "
              f"{dup_inside['quantity'].sum():,.0f} units across {dup_inside['itemcode'].nunique()} "
              f"code(s) -- far smaller than the {dup_all['quantity'].sum():,.0f} units before it, "
              f"but not eliminated: {sorted(dup_inside['itemcode'].unique().tolist())}")
    else:
        print("      -> no cross-contract duplicate rows survive the sale_company filter.")

    print("\n" + "=" * 78)
    print("BACKLOG STEP 2 — AVAILABLE = ON-HAND - BACKLOG (negatives not clamped)")
    print("=" * 78)
    known = classified[classified["available"].notna()]
    n_pos = int((known["available"] > 0).sum())
    n_zero = int((known["available"] == 0).sum())
    n_neg = int((known["available"] < 0).sum())
    n_unknown = int(classified["available"].isna().sum())
    print(f"2b  positive={n_pos}  zero={n_zero}  negative={n_neg}  unknown(no_db_record)={n_unknown}  "
          f"sum={n_pos + n_zero + n_neg + n_unknown}  registry={len(classified)}  "
          f"match={n_pos + n_zero + n_neg + n_unknown == len(classified)}")
    print(f"    total available across all codes where it is known: {known['available'].sum():,.0f} units")

    negatives = classified[classified["available"].notna() & (classified["available"] < 0)].copy()
    negatives = negatives.sort_values("available")
    print(f"\n2c  every negative code, most negative first ({len(negatives)} total):")
    shown = negatives.head(30)
    print(f"    {'code':<28}{'division':<10}{'on_hand':>12}{'backlog':>12}{'available':>12}")
    for _, r in shown.iterrows():
        print(f"    {r['code']:<28}{r['business']:<10}{r['qty']:>12,.0f}{r['backlog']:>12,.0f}"
              f"{r['available']:>12,.0f}")
    if len(negatives) > 30:
        print(f"    ... and {len(negatives) - 30} more negative codes (all written to the JSON).")

    print(f"\n2d  cause classification for the {len(negatives)} negative codes:")
    causes = classify_negative_causes(negatives, flagged_kept)
    for cause, grp in causes.groupby("cause"):
        print(f"    {cause:<42} {len(grp):>4} codes  {grp['available'].sum():>14,.0f} units of shortfall")
    print("\n    working for the top 5 most negative:")
    for _, r in causes.sort_values("available").head(5).iterrows():
        print(f"    {r['code']} (on-hand {r['qty']:,.0f}, backlog {r['backlog']:,.0f}, "
              f"available {r['available']:,.0f})\n      -> {r['cause']}: {r['evidence']}")

    print("\n" + "=" * 78)
    print("BACKLOG STEP 3 — SANITY CHECK: same distribution if reserve_bywa were used instead")
    print("=" * 78)
    reserve_per_code = inv.groupby("itemcode", as_index=False)["reserve_bywa"].sum().rename(
        columns={"itemcode": "code"})
    rc = classified.merge(reserve_per_code, on="code", how="left")
    rc["avail_reserve"] = rc["qty"] - rc["reserve_bywa"].fillna(0.0)
    rc.loc[rc["state"] == "no_db_record", "avail_reserve"] = None
    kr = rc[rc["avail_reserve"].notna()]
    print(f"reserve_bywa basis: positive={int((kr['avail_reserve'] > 0).sum())}  "
          f"zero={int((kr['avail_reserve'] == 0).sum())}  "
          f"negative={int((kr['avail_reserve'] < 0).sum())}  unknown={int(rc['avail_reserve'].isna().sum())}  "
          f"total={kr['avail_reserve'].sum():,.0f} units")
    print(f"backlog basis (step 2b, for comparison): positive={n_pos}  zero={n_zero}  "
          f"negative={n_neg}  unknown={n_unknown}  total={known['available'].sum():,.0f} units")

    print("\n" + "=" * 78)
    print("STEP 3 — WAREHOUSE BREAKDOWN")
    print("=" * 78)
    by_warehouse = build_by_warehouse(inv)
    all_warehouses = sorted(inv["warehouse"].dropna().unique().tolist())
    tran = query_transfer_pairs(item_codes)
    warehouse_roles = classify_warehouse_roles(tran, all_warehouses)

    stock_by_wh = inv.groupby("warehouse", as_index=False)["stock"].sum()
    nonzero_wh = stock_by_wh[stock_by_wh["stock"] > 0]["warehouse"].tolist()
    staging_with_stock = warehouse_roles[(warehouse_roles["role"] == "staging") &
                                          (warehouse_roles["code"].isin(nonzero_wh))]
    print(f"Warehouses holding non-zero stock for this item set: {sorted(nonzero_wh)}")
    print(f"Role counts: {warehouse_roles['role'].value_counts().to_dict()}")
    if len(staging_with_stock):
        print(f"WARNING: {len(staging_with_stock)} staging-flagged warehouse(s) hold non-zero stock: "
              f"{staging_with_stock['code'].tolist()} — the 'sum all warehouses' total DOES include "
              f"some non-sellable stock for these codes.")
    else:
        print("No staging-flagged warehouse holds non-zero stock for this item set — the 'sum all "
              "warehouses' total does not currently include any warehouse flagged non-sellable by "
              "movement evidence. (Warehouses with role 'unknown' were not evidenced either way; "
              "if any hold stock, that stock's sellability cannot be confirmed from data.)")
    unknown_with_stock = warehouse_roles[(warehouse_roles["role"] == "unknown") &
                                          (warehouse_roles["code"].isin(nonzero_wh))]
    if len(unknown_with_stock):
        print(f"NOTE: {len(unknown_with_stock)} 'unknown'-role warehouse(s) also hold non-zero stock: "
              f"{unknown_with_stock['code'].tolist()} — sellability not evidenced either way.")

    print("\n" + "=" * 78)
    print("STEP 4 — WRITE data/inventory.json")
    print("=" * 78)
    backlog_ts = pd.to_datetime(backlog_rows["timestamp"])
    backlog_meta = {
        "source_table": BACKLOG_TABLE,
        "loaded_at": str(backlog_ts.min()),
        "sale_company_filter": BACKLOG_SALE_COMPANIES,
        "status_filter": None,
        "scope_note": (
            "Scoped to sale_company IN ('PEM','CI') to match Cube_Inventory_Exact, which holds "
            "exactly those two company values. No status filter: every Cube_Backlog row is already "
            "outstanding (viewType='CTR/PO to be delivered' table-wide, no delivered or cancelled "
            "status exists). Quantities are summed as-is, NOT de-duplicated -- a known "
            "cross-contract duplicate-recording pattern inflates some codes; see "
            "output/summary/reserve_backlog_relationship_report.md."
        ),
        "rows_used": int(len(backlog_rows)),
        "cross_contract_duplicate_rows_included": int(len(dup_inside)),
    }
    backlog_meta["detail_rows_written"] = int(n_detail_rows)
    backlog_meta["detail_note"] = (
        "Every item's backlog_rows are the individual Cube_Backlog rows behind its backlog total, "
        "carried through as-is with NO de-duplication, so a reviewer can judge row by row whether "
        "each one belongs. Rows sharing a quantity, status and delivery date under different "
        "docIDs are the known cross-contract duplicate-recording pattern; they are included."
    )
    payload = build_json(classified, by_warehouse, warehouse_roles, snapshot_meta, SOURCE_TABLE,
                         backlog_meta, backlog_detail)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(OUTPUT_PATH)
    prev_size = previous_run["file_size"] if previous_run else None
    print(f"Wrote {OUTPUT_PATH} ({file_size:,} bytes"
          + (f", previously {prev_size:,} bytes, {file_size - prev_size:+,})" if prev_size else ")"))

    print("\n" + "=" * 78)
    print("STEP 4B — MOVEMENT AGAINST THE PREVIOUS RUN")
    print("=" * 78)
    on_hand_total = float(classified["qty"].sum())
    report_movement(previous_run, payload["totals"], on_hand_total, snapshot_meta, backlog_meta,
                    payload["snapshot"]["generated_at"])

    print("\n" + "=" * 78)
    print("STEP 5 — VERIFY")
    print("=" * 78)
    verify_results = verify(OUTPUT_PATH, len(registry),
                             {"has_stock": has_stock, "zero_stock": zero_stock, "no_db_record": no_db_record},
                             n_neg)
    all_ok = all(ok for _, ok in verify_results)
    for desc, ok in verify_results:
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
    if not all_ok:
        raise SystemExit("One or more verification assertions FAILED — not proceeding to commit.")
