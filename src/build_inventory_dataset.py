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
BACKLOG_TABLE = "[salewarehouse].[dbo].[Cube_Backlog]"  # RETIRED as the Reserved source, 2026-09-25
# (task 2a, Part 5; DATA_MAP.md Trap 23) -- kept here ONLY for the one-time before/after
# comparison query in __main__ (`query_backlog`, below), never again as the written figure.
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"  # NEW Reserved source, per METRICS.md Sec.14
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


# --------------------------------------------------------------------------------------------
# STEP 2B (NEW, 2026-09-25, task 2a Part 5) -- Reserved from Cube_CES Status='Backlog'
# --------------------------------------------------------------------------------------------
# DATA_MAP.md Trap 23 ("PENDING VERIFICATION, NOT CONFIRMED -- stock panel Reserved from
# Cube_Backlog") is resolved by this change: the panel's Reserved figure now reads Cube_CES's own
# dedicated Status column (ground truth per STATUS.md:2084-2091 -- Status='Backlog' rows always
# carry ActualQty=0 and BacklogQty=the pending amount, confirmed against cube_Sale_APD's MPS rows
# both directions) instead of the separate Cube_Backlog table, which Trap 5/METRICS.md Sec.14
# already found lags Cube_CES by ~14 hours and can hold already-delivered pairs.

def query_backlog_ces(item_codes: list) -> pd.DataFrame:
    """Pulls every Cube_CES row with Status='Backlog' for the registry codes -- METRICS.md
    Sec.14's literal confirmed-demand source (the Cube_Backlog TABLE is never used)."""
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT ContractID, ItemCode, CustomerID, ForecastDelDate, PlanDelDate, ActualQty, BacklogQty, Timestamp
        FROM {CES_TABLE}
        WHERE ItemCode IN ('{code_list}') AND Status = 'Backlog'
    """
    df = run_query(sql)
    logger.info("Pulled %d Cube_CES Status='Backlog' rows for %d item codes.", len(df), len(item_codes))
    return df


def dedup_and_aggregate_ces_backlog(ces: pd.DataFrame) -> tuple:
    """METRICS.md Sec.14: confirmed demand is 'deduplicated on contract + item'. Returns
    (per_code totals df with columns [code, backlog], {code: [row dicts]} in the SAME field
    shape the old Cube_Backlog-based backlog_rows carried, so index.html's modal needs no
    structural change) -- `backlog_from` is repurposed to name the actual source table, since
    Cube_CES has no equivalent of Cube_Backlog's own `backlog_from` column."""
    empty_totals = pd.DataFrame(columns=["code", "backlog"])
    if ces.empty:
        return empty_totals, {}
    df = ces.copy()
    # qty = ActualQty + BacklogQty (same formula as the already-tested src/phaseE1fix_recompute.py
    # Cube_CES Backlog pull) -- for Status='Backlog' rows ActualQty is always 0
    # (STATUS.md:2084-2091), so this is BacklogQty in practice; the +ActualQty term is kept for
    # consistency with that already-tested pattern, not because it changes any value here.
    df["qty"] = df["ActualQty"].fillna(0) + df["BacklogQty"].fillna(0)
    df["dedupe_key"] = df["ItemCode"].astype(str) + "::" + df["ContractID"].astype(str)
    n_before = len(df)
    df = df.drop_duplicates(subset="dedupe_key").copy()
    n_dropped = n_before - len(df)
    if n_dropped:
        logger.info("Dedup on (contract, item) per METRICS.md Sec.14: dropped %d duplicate "
                    "Cube_CES Backlog rows of %d.", n_dropped, n_before)

    per_code = df.groupby("ItemCode", as_index=False)["qty"].sum().rename(
        columns={"ItemCode": "code", "qty": "backlog"})

    rows_by_code = {}
    for itemcode, grp in df.groupby("ItemCode"):
        rows = []
        for _, r in grp.iterrows():
            rows.append({
                "doc_id": _clean_str(r["ContractID"]),
                "job": None,
                "customer": _clean_str(r["CustomerID"]),
                "quantity": float(r["qty"]),
                "status": "Backlog",
                "delivery_date": _clean_date(r["ForecastDelDate"]) if pd.notna(r["ForecastDelDate"]) else None,
                "plan_delivery_date": _clean_date(r["PlanDelDate"]) if pd.notna(r["PlanDelDate"]) else None,
                "backlog_from": "Cube_CES",
            })
        rows_by_code[itemcode] = rows
    return per_code, rows_by_code


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
# STEP 2C (NEW, 2026-09-25, task 2a Part 5) -- sellable / staging / elsewhere on-hand split
# --------------------------------------------------------------------------------------------
# config.yaml's own sellable_warehouse_codes comment (line ~980): "a BUSINESS ASSUMPTION standing
# in for a fact the data cannot supply, to be confirmed by the warehouse team, never treated as
# verified" -- reused verbatim in the panel's own label (see index.html). CI101/PEM102/PEM104 have
# no configured list (too few stocked items for a confident sellable-set, per that same comment)
# and get "not_assessed": true, never a guessed 0 or an inherited list from another division.
STAGING_WAREHOUSE_CODES = {"QA", "FMTS", "FMTO"}


def compute_sellable_split(inv: pd.DataFrame, registry: pd.DataFrame, config: dict) -> dict:
    """Per item: on-hand split into sellable (division's configured sellable_warehouse_codes) /
    staging (QA/FMTS/FMTO specifically) / elsewhere, with totals for each bucket added
    separately in build_json(). Items with no Cube_Inventory_Exact rows at all (no_db_record)
    are left out here and get null buckets downstream, consistent with their qty/available
    already being null, never a guessed 0."""
    sellable_by_division = config["phase_e1_assumptions"]["sellable_warehouse_codes"]
    div_by_code = dict(zip(registry["code"], registry["business"]))
    result = {}
    for itemcode, grp in inv.groupby("itemcode"):
        division = div_by_code.get(itemcode)
        sellable_codes = sellable_by_division.get(division)
        if sellable_codes is None:
            result[itemcode] = {"not_assessed": True, "division": division,
                                 "sellable_qty": None, "staging_qty": None, "elsewhere_qty": None}
            continue
        sellable_set = set(sellable_codes)
        sellable_qty = float(grp[grp["warehouse"].isin(sellable_set)]["stock"].sum())
        staging_qty = float(grp[grp["warehouse"].isin(STAGING_WAREHOUSE_CODES)]["stock"].sum())
        elsewhere_qty = float(grp[~grp["warehouse"].isin(sellable_set | STAGING_WAREHOUSE_CODES)]["stock"].sum())
        result[itemcode] = {"not_assessed": False, "division": division,
                             "sellable_qty": sellable_qty, "staging_qty": staging_qty,
                             "elsewhere_qty": elsewhere_qty}
    return result


def sellable_split_totals(split: dict) -> dict:
    """Per-division totals for the sellable/staging/elsewhere split, plus the list of divisions
    with no configured sellable list ('not assessed')."""
    by_division = {}
    not_assessed_divisions = set()
    for itemcode, s in split.items():
        div = s["division"]
        if s["not_assessed"]:
            not_assessed_divisions.add(div)
            continue
        d = by_division.setdefault(div, {"sellable_total": 0.0, "staging_total": 0.0, "elsewhere_total": 0.0})
        d["sellable_total"] += s["sellable_qty"]
        d["staging_total"] += s["staging_qty"]
        d["elsewhere_total"] += s["elsewhere_qty"]
    return {"by_division": by_division, "not_assessed_divisions": sorted(not_assessed_divisions)}


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
               backlog_rows: dict, sellable_split: dict, sellable_totals: dict,
               sellable_warehouse_codes_by_division: dict) -> dict:
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
        split = sellable_split.get(row["code"])
        if split is None:
            # no_db_record: on-hand itself is unknown, so the split is unknown too (null), never
            # a guessed 0 -- consistent with qty/available already being null for this state.
            sellable_qty = staging_qty = elsewhere_qty = None
            not_assessed = row["business"] not in sellable_warehouse_codes_by_division
        else:
            not_assessed = split["not_assessed"]
            sellable_qty = split["sellable_qty"]
            staging_qty = split["staging_qty"]
            elsewhere_qty = split["elsewhere_qty"]
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
            "sellable_split": {
                "not_assessed": not_assessed,
                "sellable_qty": sellable_qty,
                "staging_qty": staging_qty,
                "elsewhere_qty": elsewhere_qty,
            },
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
        "sellable_split_totals": sellable_totals,
        "sellable_warehouse_codes_by_division": sellable_warehouse_codes_by_division,
        "staging_warehouse_codes": sorted(STAGING_WAREHOUSE_CODES),
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

    bad_split_sum = []
    for it in items:
        s = it["sellable_split"]
        if s["not_assessed"] or it["qty"] is None:
            continue
        total = (s["sellable_qty"] or 0) + (s["staging_qty"] or 0) + (s["elsewhere_qty"] or 0)
        if abs(total - it["qty"]) > 1e-6:
            bad_split_sum.append((it["code"], total, it["qty"]))
    ok = len(bad_split_sum) == 0
    results.append((f"sellable_split sellable+staging+elsewhere == qty for every assessed item "
                    f"with known qty ({len(bad_split_sum)} mismatches)", ok))

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
    print("BACKLOG STEP 1 — RESERVED, SWITCHED FROM Cube_Backlog TO Cube_CES Status='Backlog'")
    print("(task 2a, Part 5; DATA_MAP.md Trap 23; METRICS.md Sec.14)")
    print("=" * 78)

    # ---- BEFORE: the old Cube_Backlog-based figure, for a direct, cited before/after comparison
    # (never written to the JSON -- comparison only). ----
    old_backlog_rows = query_backlog(item_codes)
    old_backlog_per_code = aggregate_backlog(old_backlog_rows)
    old_total = float(old_backlog_per_code["backlog"].sum()) if len(old_backlog_per_code) else 0.0
    old_by_code = dict(zip(old_backlog_per_code["code"], old_backlog_per_code["backlog"]))
    print(f"1-before (Cube_Backlog, as-is, no dedup, sale_company filtered): "
          f"{len(old_backlog_per_code)} codes, {old_total:,.0f} units total")

    # ---- AFTER: Cube_CES Status='Backlog', deduplicated on (contract, item) per METRICS.md
    # Sec.14's literal text -- the new, adopted Reserved source. ----
    ces_backlog_raw = query_backlog_ces(item_codes)
    backlog_per_code, backlog_detail = dedup_and_aggregate_ces_backlog(ces_backlog_raw)
    classified = add_backlog_and_available(classified, backlog_per_code)

    new_total = float(backlog_per_code["backlog"].sum()) if len(backlog_per_code) else 0.0
    new_by_code = dict(zip(backlog_per_code["code"], backlog_per_code["backlog"]))
    n_backlog_codes = int((classified["backlog"] > 0).sum())
    print(f"1-after  (Cube_CES Status='Backlog', deduped on contract+item): "
          f"{len(backlog_per_code)} codes, {new_total:,.0f} units total")
    print(f"1-delta  TOTAL RESERVED: {old_total:,.0f} -> {new_total:,.0f} units "
          f"({new_total - old_total:+,.0f}, {((new_total - old_total) / old_total * 100) if old_total else float('nan'):+.1f}%)")
    print(f"         codes with Reserved > 0: {(old_backlog_per_code['backlog'] > 0).sum() if len(old_backlog_per_code) else 0} "
          f"-> {n_backlog_codes}")

    all_codes_touched = sorted(set(old_by_code) | set(new_by_code))
    changed = [{"code": c, "old": old_by_code.get(c, 0.0), "new": new_by_code.get(c, 0.0)}
               for c in all_codes_touched if abs(old_by_code.get(c, 0.0) - new_by_code.get(c, 0.0)) > 1e-6]
    print(f"1-items  {len(changed)}/{len(all_codes_touched)} touched codes changed value "
          f"(old Cube_Backlog vs new Cube_CES):")
    for r in sorted(changed, key=lambda r: -abs(r["new"] - r["old"]))[:30]:
        print(f"    {r['code']:<28}{r['old']:>12,.0f} -> {r['new']:>12,.0f}   ({r['new'] - r['old']:+,.0f})")
    if len(changed) > 30:
        print(f"    ... and {len(changed) - 30} more changed codes.")
    reserved_change_report = {
        "old_total_cube_backlog": old_total, "new_total_cube_ces_backlog": new_total,
        "old_codes_with_reserved": int((old_backlog_per_code["backlog"] > 0).sum()) if len(old_backlog_per_code) else 0,
        "new_codes_with_reserved": n_backlog_codes,
        "n_codes_changed": len(changed),
        "changed_codes_sample": changed[:50],
    }

    n_detail_rows = sum(len(v) for v in backlog_detail.values())
    mismatches = assert_backlog_rows_sum(classified, backlog_detail)
    print(f"1a2 per-item backlog row detail: {n_detail_rows} rows carried across "
          f"{len(backlog_detail)} codes (already deduped on contract+item above).")
    print(f"    sum check — every item's rows must total exactly its backlog figure: "
          f"{len(classified) - len(mismatches)}/{len(classified)} items PASS, "
          f"{len(mismatches)} FAIL")
    if mismatches:
        for m in mismatches[:20]:
            print(f"      MISMATCH {m['code']}: {m['n_rows']} rows summing {m['row_sum']:,.4f} "
                  f"vs total {m['total']:,.4f}")
        raise SystemExit("Per-item backlog rows do not sum to the per-item totals — stopping.")

    print("\n" + "=" * 78)
    print("BACKLOG STEP 2 — AVAILABLE = ON-HAND - RESERVED (negatives not clamped)")
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
    backlog_ts = pd.to_datetime(ces_backlog_raw["Timestamp"]) if len(ces_backlog_raw) else pd.Series([], dtype="datetime64[ns]")
    backlog_meta = {
        "source_table": CES_TABLE,
        "status_filter": "Backlog",
        "loaded_at": str(backlog_ts.min()) if len(backlog_ts) else None,
        "scope_note": (
            "SWITCHED 2026-09-25 (task 2a, Part 5; DATA_MAP.md Trap 23) from the Cube_Backlog "
            "TABLE to Cube_CES rows with Status='Backlog' -- METRICS.md Sec.14's literal "
            "confirmed-demand source. Cube_Backlog is known to lag Cube_CES by ~14 hours and can "
            "hold already-delivered pairs (DATA_MAP.md Trap 5). Deduplicated on (contract, item) "
            "per METRICS.md Sec.14's exact text -- see reserved_change_report below for the "
            "before/after total and the list of codes whose value changed."
        ),
        "rows_used": int(len(backlog_per_code)),
        "raw_rows_before_dedup": int(len(ces_backlog_raw)),
        "reserved_change_report": reserved_change_report,
    }
    backlog_meta["detail_rows_written"] = int(n_detail_rows)
    backlog_meta["detail_note"] = (
        "Every item's backlog_rows are its Cube_CES Status='Backlog' rows, deduplicated on "
        "(contract, item) per METRICS.md Sec.14 -- 'backlog_from' names the source table "
        "(Cube_CES), replacing the old Cube_Backlog-specific column of the same name."
    )
    sellable_by_division = config["phase_e1_assumptions"]["sellable_warehouse_codes"]
    sellable_split = compute_sellable_split(inv, registry, config)
    sellable_totals = sellable_split_totals(sellable_split)
    print("\n" + "=" * 78)
    print("STEP 2C — SELLABLE / STAGING (QA,FMTS,FMTO) / ELSEWHERE SPLIT")
    print("=" * 78)
    print(f"Divisions with a configured sellable list: {sorted(sellable_by_division.keys())}")
    print(f"Divisions NOT assessed (no configured list): {sellable_totals['not_assessed_divisions']}")
    for div, t in sellable_totals["by_division"].items():
        print(f"  {div:<8}sellable={t['sellable_total']:>10,.0f}  staging={t['staging_total']:>10,.0f}  "
              f"elsewhere={t['elsewhere_total']:>10,.0f}")

    payload = build_json(classified, by_warehouse, warehouse_roles, snapshot_meta, SOURCE_TABLE,
                         backlog_meta, backlog_detail, sellable_split, sellable_totals, sellable_by_division)
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
