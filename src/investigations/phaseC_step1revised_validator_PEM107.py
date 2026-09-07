"""Phase C step 1 REVISED — PEM107 readiness re-validation on the corrected division
source-of-truth basis (STATUS.md Locked Decisions, "Division source-of-truth correction",
2026-09-04).

Why this script exists: the original `phaseC_validator_PEM107.py` (Phase C step 1) assessed
PEM107 while `division = 'PEM107'` was still used as a query filter. That filter has since been
removed project-wide -- the pricelist sheet an item appears on determines its division; a query
must include every Omni Channel row for an item's code regardless of what `division` value the
database row happens to carry. For PEM107 this raised total Omni-Channel value by 90.01%
(`output/summary/phaseC_revalidation_report.md` Section 1) -- the largest magnitude change of the
three divisions re-validated in this round. That aggregate re-validation did not re-run PEM107's
full per-division readiness checks (category/type collisions, pricelist agreement, duplicates,
demand profile, readiness verdict) -- this script does that.

Corrected query pattern (CONVENTIONS.md, STATUS.md): pull item codes for PEM107 from the
pricelist (sheet == "PEM107 CT-Version 2", per config.yaml's sheet_to_division mapping). Query
cube_Sale_APD filtered on itemcode IN (...), revenue_type = 'Omni Channel', status IN
('Actual','MPS') -- NO division filter. `division` is selected as `division_db_raw` for
inspection/reporting only, never as a filter.

Read-only throughout: never writes to config.yaml or any pipeline code (src/*.py outside
src/investigations/), never modifies DB data. Per AGENTS.md's Validator role: checks data
quality, verifies figures by direct recomputation, does not interpret business meaning beyond a
readiness verdict.

Checks (per this task's brief):
  1. Usable date range (monthly row counts/value, column completeness, createDate/forecast_date
     min/max).
  2. Name and code collisions (productCateName/productTypeName shared with other divisions;
     multi-sheet/no-sheet code check cited from prior work, not re-derived).
  3. Pricelist agreement (category/type only -- division-tag disagreement e.g. PEM102-OLD is
     EXPECTED, not a mismatch, per this task's explicit instruction).
  4. Duplicates and split lots (forecast_date-differs test, on the new unfiltered pull).
  5. Cube_CES reconciliation (5-field key, same method as the PEM101/full-scope re-validation).
  6. Demand profile (ADI/CV2 classification, compared explicitly against the original Phase C
     step 1 PEM107 report).
  7. Readiness verdict (reported in the .md report, not a CSV).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402
from division_utils import assert_no_code_on_multiple_sheets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_step1revised_PEM107")

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
PREFIX = "phaseC_step1revised_PEM107_"
SHEET_NAME = "PEM107 CT-Version 2"
SOURCE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def out(name):
    return os.path.join(SUMMARY_DIR, f"{PREFIX}{name}")


def save(df: pd.DataFrame, name: str) -> str:
    path = out(name)
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d rows)", path, len(df))
    return path


def q(sql: str) -> pd.DataFrame:
    logger.info("Query: %s", sql[:300].replace("\n", " "))
    return run_query(sql)


def sql_in(codes) -> str:
    return "','".join(c.replace("'", "''") for c in codes)


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_demand(qty_series: np.ndarray):
    n_periods = len(qty_series)
    nonzero = qty_series[qty_series > 0]
    if len(nonzero) == 0:
        return "NoSale", None, None
    adi = n_periods / len(nonzero)
    mean_d = nonzero.mean()
    std_d = nonzero.std(ddof=1) if len(nonzero) > 1 else 0.0
    cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        cls = "Smooth"
    elif adi < ADI_THRESHOLD:
        cls = "Erratic"
    elif cv2 < CV2_THRESHOLD:
        cls = "Intermittent"
    else:
        cls = "Lumpy"
    return cls, adi, cv2


# ============================================================================
# Step 0: pricelist scope
# ============================================================================
def step0_scope(config: dict) -> pd.DataFrame:
    logger.info("=== STEP 0: PEM107 pricelist scope ===")
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pdf = load_visible_product_rows(pricelist_path)
    pdf_dedup = pdf.drop_duplicates(subset=["sheet", "code"])

    sheet_to_division = config["sheet_to_division"]
    mapped_division = sheet_to_division.get(SHEET_NAME)
    if mapped_division != "PEM107":
        raise ValueError(
            f"config.yaml sheet_to_division[{SHEET_NAME!r}] = {mapped_division!r}, expected "
            f"'PEM107' -- refusing to proceed with a stale assumption about the sheet name."
        )
    logger.info("Confirmed from config.yaml: sheet_to_division[%r] = %r", SHEET_NAME, mapped_division)

    # Re-confirm the whole-pricelist sheet-uniqueness invariant on the full pricelist (cheap,
    # cited by the full-scope re-validation already, re-checked here rather than blindly trusted).
    assert_no_code_on_multiple_sheets(pdf_dedup)

    pem107 = pdf_dedup[pdf_dedup["sheet"] == SHEET_NAME].copy()
    codes = sorted(pem107["code"].unique().tolist())
    logger.info("PEM107 sheet (%r): %d distinct item codes", SHEET_NAME, len(codes))
    save(pem107, "pricelist_rows.csv")
    with open(out("item_codes.txt"), "w") as f:
        f.write("\n".join(codes))
    return pem107


# ============================================================================
# Step 1: main scope pull -- NO division filter (the corrected query pattern)
# ============================================================================
def step1_main_pull(config: dict, codes) -> pd.DataFrame:
    logger.info("=== STEP 1: main scope pull, NO division filter (corrected query pattern) ===")
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    sql = f"""
        SELECT contractid, itemcode, createDate, forecast_date, qty, sale, status,
               division AS division_db_raw, revenue_type, productCateName, productTypeName
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{sql_in(codes)}')
          AND revenue_type = '{revenue_type}'
          AND status IN ('{"','".join(statuses)}')
    """
    df = q(sql)
    logger.info("Pulled %d rows for %d PEM107 item codes, revenue_type=%s, status in %s, NO "
                "division filter.", len(df), len(codes), revenue_type, statuses)

    neg = df[(df["qty"] < 0) | (df["sale"] < 0)]
    if len(neg):
        raise ValueError(f"Found {len(neg)} negative-qty/sale rows -- must be reviewed, not dropped silently.")
    logger.info("Validation: 0 negative qty/sale rows (checked, not assumed).")

    n_old = df["division_db_raw"].astype(str).str.endswith("-OLD").sum()
    logger.info("Of %d rows, %d (%.1f%%) carry an -OLD-suffixed division_db_raw tag (included, "
                "not excluded, per the corrected query pattern).", len(df), n_old,
                100 * n_old / len(df) if len(df) else 0)
    save(df, "00_main_pull_raw.csv")
    return df


# ============================================================================
# CHECK 1: usable date range
# ============================================================================
def check1_date_range(df: pd.DataFrame) -> None:
    logger.info("=== CHECK 1: usable date range ===")
    d = df.copy()
    d["createDate"] = pd.to_datetime(d["createDate"])
    d["forecast_date"] = pd.to_datetime(d["forecast_date"], errors="coerce")

    monthly = (
        d.assign(yr=d["createDate"].dt.year, mo=d["createDate"].dt.month)
        .groupby(["yr", "mo"])
        .agg(n_rows=("itemcode", "size"), sum_sale=("sale", "sum"), sum_qty=("qty", "sum"))
        .reset_index()
        .sort_values(["yr", "mo"])
    )
    save(monthly, "check1_monthly_rowcounts.csv")

    completeness = (
        d.assign(yr=d["createDate"].dt.year)
        .groupby("yr")
        .agg(
            n_rows=("itemcode", "size"),
            pct_forecast_date=("forecast_date", lambda s: round(100 * s.notna().mean(), 2)),
            pct_productCateName=("productCateName", lambda s: round(100 * s.notna().mean(), 2)),
            pct_productTypeName=("productTypeName", lambda s: round(100 * s.notna().mean(), 2)),
            pct_division_db_raw=("division_db_raw", lambda s: round(100 * s.notna().mean(), 2)),
        )
        .reset_index()
    )
    save(completeness, "check1_column_completeness_by_year.csv")

    summary = pd.DataFrame([{
        "n_rows": len(d),
        "min_createDate": d["createDate"].min(),
        "max_createDate": d["createDate"].max(),
        "min_forecast_date": d["forecast_date"].min(),
        "max_forecast_date": d["forecast_date"].max(),
    }])
    save(summary, "check1_date_range_summary.csv")

    max_date = d["createDate"].max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_partial = max_date < month_end
    logger.info("Check 1: createDate %s to %s (%d rows). Latest month %s is %s.",
                d["createDate"].min().date(), max_date.date(), len(d),
                max_date.to_period("M"), "PARTIAL (excluded from Check 6)" if latest_partial else "complete")


# ============================================================================
# CHECK 2: name and code collisions
# ============================================================================
def check2_collisions(config: dict, df: pd.DataFrame, codes) -> None:
    logger.info("=== CHECK 2: name and code collisions ===")
    cate_names = sorted(df["productCateName"].dropna().unique().tolist())
    type_names = sorted(df["productTypeName"].dropna().unique().tolist())
    logger.info("PEM107's %d codes carry %d distinct productCateName and %d distinct "
                "productTypeName values in the new unfiltered pull.", len(codes), len(cate_names), len(type_names))

    if cate_names:
        sql_cate = f"""
            SELECT productCateName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
            FROM {SOURCE_TABLE}
            WHERE productCateName IN ('{sql_in(cate_names)}')
            GROUP BY productCateName, division
            ORDER BY productCateName, sum_sale DESC
        """
        df_cate = q(sql_cate)
    else:
        df_cate = pd.DataFrame(columns=["productCateName", "division", "n_rows", "sum_sale"])
    save(df_cate, "check2_category_name_by_division.csv")

    if type_names:
        sql_type = f"""
            SELECT productTypeName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
            FROM {SOURCE_TABLE}
            WHERE productTypeName IN ('{sql_in(type_names)}')
            GROUP BY productTypeName, division
            ORDER BY productTypeName, sum_sale DESC
        """
        df_type = q(sql_type)
    else:
        df_type = pd.DataFrame(columns=["productTypeName", "division", "n_rows", "sum_sale"])
    save(df_type, "check2_type_name_by_division.csv")

    if len(df_cate):
        n_div_per_cate = df_cate.groupby("productCateName")["division"].nunique().reset_index(name="n_divisions")
        save(n_div_per_cate, "check2_category_n_divisions_summary.csv")
        logger.info("Category-name collision summary:\n%s", n_div_per_cate.to_string(index=False))
    if len(df_type):
        n_div_per_type = df_type.groupby("productTypeName")["division"].nunique().reset_index(name="n_divisions")
        save(n_div_per_type, "check2_type_n_divisions_summary.csv")
        logger.info("Type-name collision summary:\n%s", n_div_per_type.to_string(index=False))

    # Item-code cross-division exposure (raw, channel/status already fixed by the scope query;
    # this shows which OTHER division_db_raw tags these codes' Omni-Channel/Actual+MPS rows carry).
    exposure = (
        df.groupby("division_db_raw")
        .agg(n_rows=("itemcode", "size"), sum_sale=("sale", "sum"))
        .reset_index()
        .sort_values("sum_sale", ascending=False)
    )
    save(exposure, "check2_itemcode_exposure_by_division_db_raw.csv")
    logger.info("Row/value split across division_db_raw tags (within this scope query, no filter "
                "applied on this column):\n%s", exposure.to_string(index=False))


# ============================================================================
# CHECK 3: pricelist agreement (category/type naming only)
# ============================================================================
def check3_pricelist_agreement(pem107_pricelist: pd.DataFrame, df: pd.DataFrame) -> None:
    logger.info("=== CHECK 3: pricelist agreement (category/type naming only) ===")
    pl = pem107_pricelist[["code", "category", "type"]].rename(
        columns={"code": "itemcode", "category": "pl_category", "type": "pl_type"}
    )
    db_agg = df.groupby("itemcode").agg(
        db_categories=("productCateName", lambda x: sorted(set(x.dropna()))),
        db_types=("productTypeName", lambda x: sorted(set(x.dropna()))),
    ).reset_index()
    merged = pl.merge(db_agg, on="itemcode", how="left")

    def cat_match(row):
        if not isinstance(row["db_categories"], list) or len(row["db_categories"]) == 0:
            return "no_db_data"
        if row["pl_category"] in row["db_categories"]:
            return "match" if len(row["db_categories"]) == 1 else "match_plus_extra"
        return "mismatch"

    def type_match(row):
        if not isinstance(row["db_types"], list) or len(row["db_types"]) == 0:
            return "no_db_data"
        if row["pl_type"] in row["db_types"]:
            return "match" if len(row["db_types"]) == 1 else "match_plus_extra"
        return "mismatch"

    merged["category_agreement"] = merged.apply(cat_match, axis=1)
    merged["type_agreement"] = merged.apply(type_match, axis=1)
    save(merged, "check3_pricelist_agreement.csv")

    mismatches = merged[(merged["category_agreement"] == "mismatch") | (merged["type_agreement"] == "mismatch")]
    save(mismatches, "check3_pricelist_agreement_mismatches_only.csv")

    cat_counts = merged["category_agreement"].value_counts().to_dict()
    type_counts = merged["type_agreement"].value_counts().to_dict()
    logger.info("Check 3: category agreement counts %s; type agreement counts %s", cat_counts, type_counts)


# ============================================================================
# CHECK 4: duplicates and split lots
# ============================================================================
def check4_duplicates(df: pd.DataFrame) -> None:
    logger.info("=== CHECK 4: duplicates and split lots (new unfiltered pull) ===")
    d = df.copy()
    d["createDate"] = pd.to_datetime(d["createDate"])
    grp_cols = ["contractid", "itemcode", "createDate", "qty", "sale", "status"]
    counts = d.groupby(grp_cols, dropna=False).size().reset_index(name="n_rows")
    dup_groups = counts[counts["n_rows"] > 1]
    save(dup_groups, "check4_duplicate_groups.csv")

    results = []
    for _, row in dup_groups.iterrows():
        mask = pd.Series(True, index=d.index)
        for c in grp_cols:
            if pd.isna(row[c]):
                mask &= d[c].isna()
            else:
                mask &= (d[c] == row[c])
        sub = d[mask]
        fd_nunique = sub["forecast_date"].nunique(dropna=False)
        bucket = "split_lot_candidate" if fd_nunique > 1 else "unexplained_duplicate"
        results.append({
            **{c: row[c] for c in grp_cols},
            "n_rows": row["n_rows"],
            "n_distinct_forecast_date": fd_nunique,
            "bucket": bucket,
            "group_sale_value": sub["sale"].sum(),
            "division_db_raw_values": sorted(set(sub["division_db_raw"].dropna())),
        })
    df_res = pd.DataFrame(results)
    save(df_res, "check4_group_classification.csv")

    if len(df_res):
        summary = df_res.groupby("bucket").agg(
            n_groups=("bucket", "size"), total_rows=("n_rows", "sum"), total_value=("group_sale_value", "sum"),
        ).reset_index()
    else:
        summary = pd.DataFrame(columns=["bucket", "n_groups", "total_rows", "total_value"])
    save(summary, "check4_bucket_summary.csv")

    total_scope_value = float(d["sale"].sum())
    logger.info("Check 4: total in-scope value %.2f THB. Bucket summary:\n%s", total_scope_value,
                summary.to_string(index=False))

    # Cross-tag duplicate check: any group spanning more than one division_db_raw value?
    if len(df_res):
        df_res["n_distinct_division_db_raw"] = df_res["division_db_raw_values"].apply(len)
        cross_tag = df_res[df_res["n_distinct_division_db_raw"] > 1]
        save(cross_tag, "check4_cross_tag_groups.csv")
        logger.info("Check 4: %d of %d duplicate groups span more than one division_db_raw tag "
                    "(cross-tag duplication candidates).", len(cross_tag), len(df_res))


# ============================================================================
# CHECK 5: Cube_CES reconciliation
# ============================================================================
def check5_cube_ces(codes, df: pd.DataFrame) -> None:
    logger.info("=== CHECK 5: Cube_CES reconciliation (5-field key, new unfiltered pull) ===")
    d = df[["contractid", "itemcode", "createDate", "status", "qty", "sale"]].copy()
    d["createDate"] = pd.to_datetime(d["createDate"]).dt.date
    d["mapped_status"] = d["status"].map({"Actual": "Actual", "MPS": "Backlog"})
    d = d.reset_index(drop=True)
    d["_apd_row_id"] = d.index  # stable per-raw-row id so genuine duplicate rows are never
                                 # silently collapsed by a value-based dedup below

    sql_ces = f"""
        SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty
        FROM {CES_TABLE}
        WHERE ItemCode IN ('{sql_in(codes)}')
    """
    df_ces = q(sql_ces)
    save(df_ces, "check5_ces_rows.csv")
    df_ces["CtrDate"] = pd.to_datetime(df_ces["CtrDate"]).dt.date
    df_ces["match_qty"] = np.where(df_ces["Status"] == "Actual", df_ces["ActualQty"], df_ces["BacklogQty"])

    merged = d.merge(
        df_ces, left_on=["contractid", "itemcode", "createDate", "mapped_status", "qty"],
        right_on=["ContractID", "ItemCode", "CtrDate", "Status", "match_qty"],
        how="left", indicator=True,
    )
    merged["matched"] = merged["_merge"] == "both"
    save(merged, "check5_merge_detail.csv")

    # Collapse Cube_CES fan-out (one APD row matching multiple CES rows on the key) back to one
    # row per ORIGINAL APD row (_apd_row_id), so the match rate is not inflated by that fan-out.
    per_row_matched = merged.groupby("_apd_row_id")["matched"].any()
    n_apd = len(d)
    n_matched = int(per_row_matched.sum())
    match_rate = 100.0 * n_matched / n_apd if n_apd else None
    summary = pd.DataFrame([{"n_apd_rows": n_apd, "n_matched": n_matched, "match_rate_pct": round(match_rate, 2) if match_rate is not None else None}])
    save(summary, "check5_match_rate_summary.csv")
    logger.info("Check 5: matched %d of %d APD rows to Cube_CES on 5-field key (%.2f%%)",
                n_matched, n_apd, match_rate or 0)

    unmatched_ids = per_row_matched[~per_row_matched].index
    unmatched = d[d["_apd_row_id"].isin(unmatched_ids)].drop(columns=["_apd_row_id"])
    save(unmatched, "check5_unmatched_apd_rows.csv")


# ============================================================================
# CHECK 6: demand profile
# ============================================================================
def check6_demand_profile(df: pd.DataFrame, all_codes) -> None:
    logger.info("=== CHECK 6: demand profile ===")
    d = df.copy()
    d["createDate"] = pd.to_datetime(d["createDate"])
    max_date = d["createDate"].max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_period = max_date.to_period("M")
    if max_date < month_end:
        logger.info("Latest month %s is partial (data ends %s) -- excluded from demand profile.",
                    latest_period, max_date.date())
        complete_max_period = latest_period - 1
    else:
        complete_max_period = latest_period

    min_period = d["createDate"].min().to_period("M")
    all_months = pd.period_range(min_period, complete_max_period, freq="M")
    logger.info("Demand profile window: %s to %s (%d complete months).", min_period, complete_max_period, len(all_months))

    d["year_month"] = d["createDate"].dt.to_period("M")
    d = d[d["year_month"] <= complete_max_period]

    monthly_qty = d.groupby(["itemcode", "year_month"])["qty"].sum().reset_index()
    save(monthly_qty, "check6_raw_item_month_qty.csv")

    idx = pd.MultiIndex.from_product([all_codes, all_months], names=["itemcode", "year_month"])
    full = monthly_qty.set_index(["itemcode", "year_month"]).reindex(idx, fill_value=0).reset_index()

    results = []
    for code, grp in full.groupby("itemcode"):
        qty_arr = grp.sort_values("year_month")["qty"].values.astype(float)
        cls, adi, cv2 = classify_demand(qty_arr)
        results.append({
            "itemcode": code, "n_periods": len(qty_arr), "n_zero_periods": int((qty_arr == 0).sum()),
            "pct_zero": round(100 * (qty_arr == 0).sum() / len(qty_arr), 1),
            "total_qty": float(qty_arr.sum()), "ADI": round(adi, 3) if adi is not None else None,
            "CV2": round(cv2, 3) if cv2 is not None else None, "classification": cls,
        })
    df_cls = pd.DataFrame(results)
    save(df_cls, "check6_item_classification.csv")

    n_active = (df_cls["classification"] != "NoSale").sum()
    total_value = float(d["sale"].sum())
    # NOTE: df_cls["pct_zero"] is already on a 0-100 scale (computed above) -- do not multiply by
    # 100 again here.
    pct_zero_all = round(df_cls["pct_zero"].mean(), 1) if len(df_cls) else None
    active = df_cls[df_cls["classification"] != "NoSale"]
    pct_zero_active = round(100 * active["n_zero_periods"].sum() / active["n_periods"].sum(), 1) if len(active) else None

    class_counts = df_cls["classification"].value_counts().to_dict()
    summary = pd.DataFrame([{
        "n_items_total": len(all_codes), "n_items_active": int(n_active),
        "total_value_thb": total_value, "n_complete_months": len(all_months),
        "window_start": str(min_period), "window_end": str(complete_max_period),
        "pct_zero_all_items": pct_zero_all, "pct_zero_active_items": pct_zero_active,
        "mean_ADI_active": round(active["ADI"].mean(), 2) if len(active) else None,
        "mean_CV2_active": round(active["CV2"].mean(), 2) if len(active) else None,
        **{f"n_{k}": v for k, v in class_counts.items()},
    }])
    save(summary, "check6_demand_profile_summary.csv")
    logger.info("Check 6 summary:\n%s", summary.to_string(index=False))
    logger.info("Classification counts: %s", class_counts)


if __name__ == "__main__":
    cfg = load_config()
    pem107_pl = step0_scope(cfg)
    codes_list = sorted(pem107_pl["code"].unique().tolist())
    main_df = step1_main_pull(cfg, codes_list)

    check1_date_range(main_df)
    check2_collisions(cfg, main_df, codes_list)
    check3_pricelist_agreement(pem107_pl, main_df)
    check4_duplicates(main_df)
    check5_cube_ces(codes_list, main_df)
    check6_demand_profile(main_df, codes_list)

    print("\n" + "=" * 90)
    print("PHASE C STEP 1 REVISED — PEM107 VALIDATOR COMPLETE")
    print("=" * 90)
    print(f"Item codes in scope: {len(codes_list)}")
    print(f"Total rows pulled (no division filter): {len(main_df)}")
    print(f"Total value in scope: {main_df['sale'].sum():,.2f} THB")
