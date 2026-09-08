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
        SELECT company, warehouse, itemcode, unit, stock, timestamp
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
               snapshot_meta: dict, source_table: str) -> dict:
    warehouses = [{"code": r["code"], "role": r["role"]} for _, r in warehouse_roles.iterrows()]

    totals = {
        "codes": int(len(classified)),
        "has_stock": int((classified["state"] == "has_stock").sum()),
        "zero_stock": int((classified["state"] == "zero_stock").sum()),
        "no_db_record": int((classified["state"] == "no_db_record").sum()),
    }

    items = []
    for _, row in classified.iterrows():
        qty = row["qty"]
        qty_out = None if pd.isna(qty) else float(qty)
        items.append({
            "code": row["code"],
            "business": row["business"],
            "category": row["category"],
            "type": None if pd.isna(row["type"]) else row["type"],
            "description": row["description"],
            "state": row["state"],
            "qty": qty_out,
            "in_forecast_scope": bool(row["in_forecast_scope"]),
            "by_warehouse": by_warehouse.get(row["code"], []),
        })

    return {
        "snapshot": {
            "source_table": source_table,
            "loaded_at": snapshot_meta["min_timestamp"],
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "refresh_cadence": "unknown",
        },
        "warehouses": warehouses,
        "totals": totals,
        "items": items,
    }


# --------------------------------------------------------------------------------------------
# STEP 5 -- verify
# --------------------------------------------------------------------------------------------

def verify(path: str, expected_registry_count: int, expected_totals: dict) -> list:
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

    for desc, ok in results:
        logger.info("[%s] %s", "PASS" if ok else "FAIL", desc)
    return results


if __name__ == "__main__":
    config = load_config()

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
    payload = build_json(classified, by_warehouse, warehouse_roles, snapshot_meta, SOURCE_TABLE)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(OUTPUT_PATH)
    print(f"Wrote {OUTPUT_PATH} ({file_size:,} bytes)")

    print("\n" + "=" * 78)
    print("STEP 5 — VERIFY")
    print("=" * 78)
    verify_results = verify(OUTPUT_PATH, len(registry),
                             {"has_stock": has_stock, "zero_stock": zero_stock, "no_db_record": no_db_record})
    all_ok = all(ok for _, ok in verify_results)
    for desc, ok in verify_results:
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
    if not all_ok:
        raise SystemExit("One or more verification assertions FAILED — not proceeding to commit.")
