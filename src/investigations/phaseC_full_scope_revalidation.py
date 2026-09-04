"""Re-validates Phase C data quality on the corrected basis (2026-09-04): the pricelist is
authoritative for an item's division; the database's `division` column on cube_Sale_APD is
reference-only and is never used as a query filter (STATUS.md Locked Decisions, "Division
source-of-truth correction"). The data-quality work done so far (Phase C step 1, the sheet-mapping
task) was performed under a `division`-filtered pull. Removing that filter admits rows never
examined before — this script re-runs the checks that matter on the new, unfiltered basis, across
all 445 visible-pricelist item codes.

Checks, in order:
  0. Sheet uniqueness: confirm no item code appears on more than one visible pricelist sheet.
  1. Full pull: all 445 codes, revenue_type='Omni Channel', status IN ('Actual','MPS'), NO
     division filter. Division attached from the pricelist (config['sheet_to_division']); the
     database's own value kept as division_db_raw for reference.
  2. Totals per division, BEFORE (division_db_raw == pricelist home division only, i.e. what
     every prior loader's WHERE clause captured) vs AFTER (this pull, no division filter).
  3. Double-counting between -OLD-tagged and normally-tagged rows: for every (contractid,
     itemcode) pair with a row under an -OLD-suffixed division and a row under a non-OLD
     division, classify as a CONFIRMED DUPLICATE only if qty, sale and forecast_date all match
     exactly (this project's established split-lot-vs-duplicate key, e.g. task7 in STATUS.md's
     "Deep investigation of the 29 remaining confirmed duplicate sets" entry) — otherwise treated
     as distinct orders/instalments, not double-counted.
  4. Cube_CES reconciliation per division, using the same 5-field key this project has used since
     Phase C step 1 (contractid/ContractID, itemcode/ItemCode, createDate/CtrDate, mapped
     Actual<->Actual/MPS<->Backlog status, qty<->ActualQty-or-BacklogQty), computed on the
     unfiltered pull grouped by pricelist division.
  5. Usable date range per division, re-derived from the unfiltered pull.
  6. No-history recount and reconciliation against config.yaml's existing excluded_item_codes /
     placeholder_item_codes (which cover only the 128-item PEM101 Category scope) into one
     consolidated status per code across all 445.

CONVENTIONS.md: raw pulled data is kept separate from processed/summary output and never
overwritten; every number is written to a CSV so it can be independently recomputed; this script
reports how many rows were processed/dropped and why via the logging module.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query
from pricelist_reader import load_visible_product_rows
from division_utils import assert_no_code_on_multiple_sheets, classify_old_tag_duplicates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_full_scope_revalidation")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SOURCE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save(df: pd.DataFrame, name: str) -> None:
    path = os.path.join(SUMMARY_DIR, f"phaseC_revalidation_{name}")
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d rows)", path, len(df))


def sql_in(codes) -> str:
    return "','".join(codes)


# ============================================================================
# Step 0: pricelist scope + sheet-uniqueness check
# ============================================================================
def step0_pricelist_scope(config: dict) -> pd.DataFrame:
    logger.info("=== STEP 0: pricelist scope + sheet-uniqueness check ===")
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pdf = load_visible_product_rows(pricelist_path)
    logger.info("Loaded %d product rows from visible sheets", len(pdf))

    dup_within_sheet = pdf[pdf.duplicated(subset=["sheet", "code"], keep=False)]
    if len(dup_within_sheet):
        logger.warning("%d within-sheet duplicate (sheet, code) rows found (already known, e.g. "
                        "DS-F-99-0308 on CI101): %s", len(dup_within_sheet),
                        dup_within_sheet[["sheet", "code"]].to_dict("records"))
    pdf = pdf.drop_duplicates(subset=["sheet", "code"])

    try:
        assert_no_code_on_multiple_sheets(pdf)
    except ValueError:
        code_sheet_counts = pdf.groupby("code")["sheet"].nunique()
        detail = pdf[pdf["code"].isin(code_sheet_counts[code_sheet_counts > 1].index)][["code", "sheet"]].sort_values("code")
        save(detail, "00b_codes_on_multiple_sheets.csv")
        raise
    logger.info("CONFIRMED: no item code appears on more than one visible sheet (%d distinct codes checked).",
                pdf["code"].nunique())

    sheet_to_division = config["sheet_to_division"]
    unmapped = set(pdf["sheet"]) - set(sheet_to_division)
    if unmapped:
        raise ValueError(f"Sheet(s) {unmapped} missing from config['sheet_to_division'].")

    scope = pdf[["code", "sheet", "category", "type"]].drop_duplicates(subset=["code"]).copy()
    scope["division"] = scope["sheet"].map(sheet_to_division)
    logger.info("Scope: %d distinct item codes across %d sheets / divisions %s",
                len(scope), scope["sheet"].nunique(), sorted(scope["division"].unique()))
    save(scope, "00a_pricelist_scope.csv")
    return scope


# ============================================================================
# Step 1: full pull, no division filter
# ============================================================================
def step1_full_pull(config: dict, scope: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 1: full pull (445 codes, Omni Channel, Actual/MPS, NO division filter) ===")
    codes = sorted(scope["code"].unique())
    statuses = config["status_basis"]
    revenue_type = config["revenue_type"]
    sql = f"""
        SELECT contractid, itemcode, createDate, forecast_date, qty, sale, status,
               division AS division_db_raw, revenue_type
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{sql_in(codes)}')
          AND revenue_type = '{revenue_type}'
          AND status IN ('{"','".join(statuses)}')
    """
    df = run_query(sql)
    logger.info("Pulled %d raw rows for %d item codes, revenue_type=%s, status in %s, NO division "
                "filter, NO date filter (full history, not just >=2024-01-01, to see the full "
                "-OLD-tag spread as Phase C step 1's sheet-mapping task did).",
                len(df), len(codes), revenue_type, statuses)

    div_by_code = dict(zip(scope["code"], scope["division"]))
    df["division"] = df["itemcode"].map(div_by_code)
    unmapped = df[df["division"].isna()]
    if len(unmapped):
        raise ValueError(f"{len(unmapped)} rows have an itemcode with no pricelist division mapping.")

    neg_qty = df[df["qty"] < 0]
    neg_sale = df[df["sale"] < 0]
    if len(neg_qty) or len(neg_sale):
        raise ValueError(f"Found {len(neg_qty)} negative-qty and {len(neg_sale)} negative-sale rows — "
                          f"must be reviewed, not silently dropped.")
    logger.info("Validation: 0 negative qty/sale rows (checked, not assumed).")

    save(df, "01_full_pull_raw.csv")
    return df


# ============================================================================
# Step 2: totals per division, before vs after
# ============================================================================
def step2_totals_before_after(full: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 2: totals per division, BEFORE (division_db_raw == home division only) "
                "vs AFTER (this pull, no division filter) ===")
    rows = []
    for division, grp in full.groupby("division"):
        before = grp[grp["division_db_raw"] == division]
        after = grp
        before_qty, before_sale = float(before["qty"].sum()), float(before["sale"].sum())
        after_qty, after_sale = float(after["qty"].sum()), float(after["sale"].sum())
        rows.append({
            "division": division,
            "n_rows_before": len(before), "n_rows_after": len(after),
            "qty_before": before_qty, "qty_after": after_qty,
            "sale_before": before_sale, "sale_after": after_sale,
            "sale_delta": after_sale - before_sale,
            "sale_delta_pct": round(100 * (after_sale - before_sale) / before_sale, 2) if before_sale else None,
        })
    result = pd.DataFrame(rows).sort_values("division")
    save(result, "02_totals_before_after_per_division.csv")
    for _, r in result.iterrows():
        logger.info("[%s] BEFORE: %d rows, qty=%.1f, sale=%.2f  ->  AFTER: %d rows, qty=%.1f, sale=%.2f "
                    "(sale delta %+.2f%%)", r["division"], r["n_rows_before"], r["qty_before"],
                    r["sale_before"], r["n_rows_after"], r["qty_after"], r["sale_after"],
                    r["sale_delta_pct"] if r["sale_delta_pct"] is not None else float("nan"))
    return result


# ============================================================================
# Step 3: double-counting between -OLD-tagged and normally-tagged rows
# ============================================================================
def step3_old_tag_duplicates(full: pd.DataFrame) -> tuple:
    logger.info("=== STEP 3: double-counting check between -OLD-tagged and normally-tagged rows ===")
    n_old = full["division_db_raw"].str.endswith("-OLD", na=False).sum()
    logger.info("%d of %d rows under an -OLD-suffixed division_db_raw.", n_old, len(full))

    candidates_out = classify_old_tag_duplicates(full)
    save(candidates_out, "03_old_tag_candidates.csv")

    confirmed = candidates_out[candidates_out["classification"] == "CONFIRMED_DUPLICATE"]
    save(confirmed, "03_old_tag_confirmed_duplicates.csv")

    n_confirmed = len(confirmed)
    value_confirmed = float(confirmed["sale_normal"].sum()) if n_confirmed else 0.0
    logger.info("%d candidate (contractid, itemcode) row-pairs found with activity under both an "
                "-OLD tag and a normal tag. Of these, %d (%.1f%%) are CONFIRMED DUPLICATES (exact "
                "qty+sale+forecast_date match) — total value %.2f THB. The remaining %d are distinct "
                "orders/instalments (differ on qty, sale, or forecast_date), not double-counted.",
                len(candidates_out), n_confirmed,
                100 * n_confirmed / len(candidates_out) if len(candidates_out) else 0,
                value_confirmed, len(candidates_out) - n_confirmed)
    return candidates_out, confirmed


# ============================================================================
# Step 4: Cube_CES reconciliation per division
# ============================================================================
def step4_cube_ces_reconciliation(config: dict, scope: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 4: Cube_CES reconciliation per division (unfiltered basis) ===")
    codes = sorted(scope["code"].unique())
    statuses = config["status_basis"]
    revenue_type = config["revenue_type"]

    sql_apd = f"""
        SELECT contractid, itemcode, createDate, status, qty, sale
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{sql_in(codes)}') AND revenue_type = '{revenue_type}'
          AND status IN ('{"','".join(statuses)}')
    """
    df_apd = run_query(sql_apd)
    logger.info("Cube_CES check: %d APD rows pulled (no division filter).", len(df_apd))

    sql_ces = f"""
        SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty
        FROM {CES_TABLE}
        WHERE ItemCode IN ('{sql_in(codes)}')
    """
    df_ces = run_query(sql_ces)
    logger.info("Cube_CES check: %d Cube_CES rows pulled for these item codes.", len(df_ces))

    div_by_code = dict(zip(scope["code"], scope["division"]))
    df_apd["division"] = df_apd["itemcode"].map(div_by_code)
    df_apd["createDate"] = pd.to_datetime(df_apd["createDate"]).dt.date
    df_apd["mapped_status"] = df_apd["status"].map({"Actual": "Actual", "MPS": "Backlog"})

    df_ces["CtrDate"] = pd.to_datetime(df_ces["CtrDate"]).dt.date
    df_ces["match_qty"] = np.where(df_ces["Status"] == "Actual", df_ces["ActualQty"], df_ces["BacklogQty"])

    merged = df_apd.merge(
        df_ces, left_on=["contractid", "itemcode", "createDate", "mapped_status", "qty"],
        right_on=["ContractID", "ItemCode", "CtrDate", "Status", "match_qty"],
        how="left", indicator=True,
    )
    merged["matched"] = merged["_merge"] == "both"
    save(merged, "04_cube_ces_merge_detail.csv")

    result = merged.groupby("division").agg(
        n_apd_rows=("matched", "size"), n_matched=("matched", "sum")
    ).reset_index()
    result["match_rate_pct"] = round(100 * result["n_matched"] / result["n_apd_rows"], 2)
    save(result, "04_cube_ces_reconciliation_per_division.csv")
    for _, r in result.iterrows():
        logger.info("[%s] Cube_CES 5-field-key match: %d of %d rows (%.2f%%)",
                    r["division"], r["n_matched"], r["n_apd_rows"], r["match_rate_pct"])
    return result


# ============================================================================
# Step 5: usable date range per division
# ============================================================================
def step5_usable_date_range(full: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 5: usable date range per division (re-derived, -OLD rows included) ===")
    d = full.copy()
    d["createDate"] = pd.to_datetime(d["createDate"])
    d["forecast_date"] = pd.to_datetime(d["forecast_date"], errors="coerce")
    rows = []
    for division, grp in d.groupby("division"):
        rows.append({
            "division": division,
            "n_rows": len(grp),
            "min_createDate": grp["createDate"].min(),
            "max_createDate": grp["createDate"].max(),
            "min_forecast_date": grp["forecast_date"].min(),
            "max_forecast_date": grp["forecast_date"].max(),
        })
    result = pd.DataFrame(rows).sort_values("division")
    save(result, "05_usable_date_range_per_division.csv")
    for _, r in result.iterrows():
        logger.info("[%s] createDate range: %s to %s (%d rows)",
                    r["division"], r["min_createDate"], r["max_createDate"], r["n_rows"])
    return result


# ============================================================================
# Step 6: no-history recount + reconciliation
# ============================================================================
def step6_no_history_reconciliation(config: dict, scope: pd.DataFrame, full: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 6: no-history recount + reconciliation against existing excluded/placeholder lists ===")
    codes_with_rows = set(full["itemcode"].unique())
    result = scope.copy()
    result["has_omni_history_new_basis"] = result["code"].isin(codes_with_rows)

    excluded_list = set(config.get("excluded_item_codes", []))
    placeholder_list = set(config.get("placeholder_item_codes", []))
    result["in_config_excluded_item_codes"] = result["code"].isin(excluded_list)
    result["in_config_placeholder_item_codes"] = result["code"].isin(placeholder_list)

    def classify(row):
        if row["has_omni_history_new_basis"]:
            if row["in_config_excluded_item_codes"]:
                return "CONFLICT: has history on new basis but listed in excluded_item_codes — needs re-check"
            if row["in_config_placeholder_item_codes"]:
                return "has_history_new_basis; already a placeholder item in config"
            return "has_history_new_basis"
        else:
            if row["in_config_excluded_item_codes"]:
                return "no_history_new_basis; already in excluded_item_codes (consistent)"
            if row["in_config_placeholder_item_codes"]:
                return "CONFLICT: no history on new basis but listed as a placeholder item — needs re-check"
            return "no_history_new_basis; NOT YET in any config list — needs classification"

    result["status"] = result.apply(classify, axis=1)
    save(result, "06_consolidated_item_status_445.csv")

    n_no_history = (~result["has_omni_history_new_basis"]).sum()
    n_conflicts = result["status"].str.startswith("CONFLICT").sum()
    logger.info("Of 445 codes: %d have zero Omni-Channel rows anywhere on the new (unfiltered) basis "
                "(was 105 of 445 on the -OLD-excluded basis); %d conflicts with the existing 128-item-"
                "scope excluded/placeholder lists found.", n_no_history, n_conflicts)
    if n_conflicts:
        logger.warning("Conflicts:\n%s", result[result["status"].str.startswith("CONFLICT")]
                        [["code", "sheet", "division", "status"]].to_string(index=False))
    return result


if __name__ == "__main__":
    cfg = load_config()
    scope_df = step0_pricelist_scope(cfg)
    full_pull = step1_full_pull(cfg, scope_df)
    totals = step2_totals_before_after(full_pull)
    candidates, confirmed_dupes = step3_old_tag_duplicates(full_pull)
    ces_recon = step4_cube_ces_reconciliation(cfg, scope_df)
    date_ranges = step5_usable_date_range(full_pull)
    consolidated = step6_no_history_reconciliation(cfg, scope_df, full_pull)

    print("\n" + "=" * 90)
    print("PHASE C FULL-SCOPE RE-VALIDATION SUMMARY")
    print("=" * 90)
    print(f"Scope: {len(scope_df)} item codes across {scope_df['sheet'].nunique()} sheets")
    print(f"\n--- Totals before/after (division filter removed) ---")
    print(totals.to_string(index=False))
    print(f"\n--- Old-tag double-counting: {len(confirmed_dupes)} CONFIRMED duplicates of "
          f"{len(candidates)} candidate pairs ---")
    if len(confirmed_dupes):
        print(f"Total confirmed-duplicate value: {confirmed_dupes['sale_normal'].sum():,.2f} THB")
    print(f"\n--- Cube_CES reconciliation per division ---")
    print(ces_recon.to_string(index=False))
    print(f"\n--- Usable date range per division ---")
    print(date_ranges.to_string(index=False))
    print(f"\n--- No-history recount ---")
    n_no_hist = (~consolidated["has_omni_history_new_basis"]).sum()
    print(f"{n_no_hist} of {len(consolidated)} codes have zero Omni-Channel rows anywhere (new basis)")
    print(f"Conflicts with existing config lists: {consolidated['status'].str.startswith('CONFLICT').sum()}")
