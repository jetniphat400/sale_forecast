"""Phase C step 1 REVISED Validator — division PEM102, re-derived on the corrected
division-source-of-truth basis (2026-09-04, STATUS.md Locked Decisions, "Division
source-of-truth correction"; CONVENTIONS.md, "The pricelist is the authoritative source for
product attributes").

Why this script exists: `phaseC_validator_PEM102.py` / `_part2.py` (original Phase C step 1) ran
every check under `WHERE division = 'PEM102'`. That filter has since been removed project-wide —
the pricelist alone determines an item's division; every Omni-Channel row for an item's code
counts regardless of the database's own `division` tag. A full-scope (445-code) re-validation
(`src/investigations/phaseC_full_scope_revalidation.py`,
`output/summary/phaseC_revalidation_report.md`) already measured PEM102's aggregate value shift
(+38.40%) but did NOT re-run PEM102's full per-division readiness checks. This script does that,
re-running the same checks as the original PEM102 Validator (usable date range, name/code
collisions, pricelist agreement, duplicates/split lots, Cube_CES reconciliation, demand profile)
on the new (no-`division`-filter) basis, using the same methodology as that original script and as
`phaseC_full_scope_revalidation.py`'s Cube_CES step (5-field key) so figures are directly
comparable.

Investigation only. No pipeline code touched (`src/load_data_full.py`, `aggregate_levels.py`,
etc.), no `config/config.yaml` change, no data modified, no git action taken. Writes only to
`output/summary/`, all new files prefixed `phaseC_step1revised_PEM102_`.
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
from division_utils import assert_no_code_on_multiple_sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_step1revised_validator_PEM102")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SOURCE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"
PREFIX = "phaseC_step1revised_PEM102_"
DIVISION = "PEM102"
SHEET_NAME = "PEM102-Version 2"

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def outpath(name: str) -> str:
    return os.path.join(SUMMARY_DIR, f"{PREFIX}{name}")


def sql_in_list(codes) -> str:
    return ",".join("'" + str(c).replace("'", "''") + "'" for c in codes)


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


def main():
    config = load_config()
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    sheet_to_division = config["sheet_to_division"]
    if sheet_to_division.get(SHEET_NAME) != DIVISION:
        raise ValueError(
            f"config.yaml sheet_to_division[{SHEET_NAME!r}] = "
            f"{sheet_to_division.get(SHEET_NAME)!r}, expected {DIVISION!r} — mapping changed, "
            f"stop rather than assume."
        )

    # ================================================================
    # Setup: pricelist scope (PEM102's codes), re-verified not assumed
    # ================================================================
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    full_pricelist = load_visible_product_rows(pricelist_path)
    full_pricelist = full_pricelist.drop_duplicates(subset=["sheet", "code"])

    # Whole-pricelist sheet-uniqueness invariant -- cheap to re-run, already established
    # project-wide in phaseC_sheetmap_report.md and phaseC_revalidation_report.md §0.
    assert_no_code_on_multiple_sheets(full_pricelist)
    logger.info("Re-confirmed: no item code on more than one visible sheet (whole pricelist, "
                "%d distinct codes) -- consistent with phaseC_sheetmap_report.md and "
                "phaseC_revalidation_report.md §0.", full_pricelist["code"].nunique())

    pem102 = full_pricelist[full_pricelist["sheet"] == SHEET_NAME].copy()
    codes = sorted(pem102["code"].unique().tolist())
    logger.info("PEM102 (sheet %r): %d rows, %d distinct item codes", SHEET_NAME, len(pem102), len(codes))
    pem102.to_csv(outpath("pricelist_rows.csv"), index=False)
    codes_in = sql_in_list(codes)

    # ================================================================
    # Main pull: itemcode + revenue_type + status only -- NO division filter.
    # division AS division_db_raw kept for reference/inspection only, never a filter.
    # ================================================================
    sql_main = f"""
    SELECT contractid, itemcode, createDate, forecast_date, qty, sale, status,
           division AS division_db_raw, revenue_type, productCateName, productTypeName, quotationid
    FROM {SOURCE_TABLE}
    WHERE itemcode IN ({codes_in})
      AND revenue_type = '{revenue_type}'
      AND status IN ('{"','".join(statuses)}')
    """
    df = run_query(sql_main)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    neg = df[(df["qty"] < 0) | (df["sale"] < 0)]
    if len(neg):
        raise ValueError(f"{len(neg)} negative qty/sale rows found -- must be reviewed, not silently dropped.")
    logger.info("Main pull (no division filter): %d rows, %d distinct items with any row, "
                "0 negative qty/sale rows (checked).", len(df), df["itemcode"].nunique())
    df.to_csv(outpath("00_main_pull_raw.csv"), index=False)

    # Also pull the fully unfiltered (itemcode-only) scope for column-completeness/date-range
    # checks, matching the original validator's Check 2 method exactly.
    sql_unfiltered = f"""
    SELECT itemcode, createDate, forecast_date, qty, sale, status, division AS division_db_raw,
           revenue_type, productCateName, productTypeName
    FROM {SOURCE_TABLE}
    WHERE itemcode IN ({codes_in})
    """
    raw_unfiltered = run_query(sql_unfiltered)
    raw_unfiltered["createDate"] = pd.to_datetime(raw_unfiltered["createDate"])
    raw_unfiltered.to_csv(outpath("00_raw_unfiltered_itemcode_scope.csv"), index=False)
    logger.info("Unfiltered itemcode-scope pull (any division/revenue_type/status): %d rows", len(raw_unfiltered))

    # ================================================================
    # CHECK 1: Usable date range
    # ================================================================
    logger.info("=== CHECK 1: usable date range ===")
    df["year_month"] = df["createDate"].dt.to_period("M").astype(str)
    monthly = df.groupby("year_month").agg(n_rows=("itemcode", "size"), total_sale=("sale", "sum"),
                                            total_qty=("qty", "sum")).reset_index().sort_values("year_month")
    monthly.to_csv(outpath("check1_date_range_monthly_new_basis.csv"), index=False)

    raw_unfiltered["yr"] = raw_unfiltered["createDate"].dt.year
    raw_unfiltered["mo"] = raw_unfiltered["createDate"].dt.month
    monthly_unfiltered = raw_unfiltered.groupby(["yr", "mo"]).agg(
        n_rows=("itemcode", "size"), total_sale=("sale", "sum"), total_qty=("qty", "sum")
    ).reset_index().sort_values(["yr", "mo"])
    monthly_unfiltered.to_csv(outpath("check1_date_range_monthly_unfiltered_itemcode_scope.csv"), index=False)

    completeness_rows = []
    for yr, grp in raw_unfiltered.groupby("yr"):
        completeness_rows.append({
            "year": yr, "n_rows": len(grp),
            "pct_revenue_type": round(100 * grp["revenue_type"].notna().mean(), 1),
            "pct_forecast_date": round(100 * grp["forecast_date"].notna().mean(), 1),
            "pct_division": round(100 * grp["division_db_raw"].notna().mean(), 1),
            "pct_status": round(100 * grp["status"].notna().mean(), 1),
            "pct_productCateName": round(100 * grp["productCateName"].notna().mean(), 1),
            "pct_productTypeName": round(100 * grp["productTypeName"].notna().mean(), 1),
        })
    completeness = pd.DataFrame(completeness_rows).sort_values("year")
    completeness.to_csv(outpath("check1_column_completeness_by_year.csv"), index=False)

    min_create, max_create = df["createDate"].min(), df["createDate"].max()
    min_fd, max_fd = df["forecast_date"].min(), df["forecast_date"].max()
    logger.info("CHECK 1: new-basis (no division filter) createDate range %s to %s, forecast_date "
                "range %s to %s. Monthly breakdown: %s", min_create.date(), max_create.date(),
                min_fd.date() if pd.notna(min_fd) else None, max_fd.date() if pd.notna(max_fd) else None,
                monthly.to_dict("records"))

    # ================================================================
    # CHECK 2: Name and code collisions
    # ================================================================
    logger.info("=== CHECK 2: name and code collisions ===")
    cate_names = sorted(df["productCateName"].dropna().unique().tolist())
    type_names = sorted(df["productTypeName"].dropna().unique().tolist())
    pd.DataFrame({"productCateName": cate_names}).to_csv(outpath("check2_our_category_names.csv"), index=False)
    pd.DataFrame({"productTypeName": type_names}).to_csv(outpath("check2_our_type_names.csv"), index=False)

    if cate_names:
        sql_cate = f"""
        SELECT productCateName, division, COUNT(*) AS n_rows, SUM(sale) AS total_sale
        FROM {SOURCE_TABLE}
        WHERE productCateName IN ({sql_in_list(cate_names)})
        GROUP BY productCateName, division
        ORDER BY productCateName, n_rows DESC
        """
        df_cate = run_query(sql_cate)
        df_cate.to_csv(outpath("check2_category_name_collisions.csv"), index=False)
        n_cate_other = df_cate[df_cate["division"] != DIVISION]["productCateName"].nunique()
        logger.info("CHECK 2: %d of %d category names carried by PEM102 items also appear under a "
                    "database division tag other than %r.", n_cate_other, len(cate_names), DIVISION)

    if type_names:
        sql_type = f"""
        SELECT productTypeName, division, COUNT(*) AS n_rows, SUM(sale) AS total_sale
        FROM {SOURCE_TABLE}
        WHERE productTypeName IN ({sql_in_list(type_names)})
        GROUP BY productTypeName, division
        ORDER BY productTypeName, n_rows DESC
        """
        df_type = run_query(sql_type)
        df_type.to_csv(outpath("check2_type_name_collisions.csv"), index=False)
        n_type_other = df_type[df_type["division"] != DIVISION]["productTypeName"].nunique()
        logger.info("CHECK 2: %d of %d type names carried by PEM102 items also appear under a "
                    "database division tag other than %r.", n_type_other, len(type_names), DIVISION)

    # itemcode x database-division split, reference only (division_db_raw), for context on where
    # PEM102's value composition comes from -- NOT used to decide scope (pricelist already decided
    # scope: all these rows count).
    sql_item_div = f"""
    SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS total_sale
    FROM {SOURCE_TABLE}
    WHERE itemcode IN ({codes_in})
    GROUP BY itemcode, division
    ORDER BY itemcode, n_rows DESC
    """
    df_item_div = run_query(sql_item_div)
    df_item_div.to_csv(outpath("check2_itemcode_by_db_division_raw.csv"), index=False)

    # Codes with no row at all in the pricelist-scoped, no-division-filter pull (used again in Check 6/no-history)
    codes_with_any_row = set(raw_unfiltered["itemcode"].unique().tolist())
    codes_no_history = sorted(set(codes) - codes_with_any_row)
    logger.info("CHECK 2 / no-history: %d of %d PEM102 codes have zero rows in cube_Sale_APD under "
                "ANY filter (itemcode only): %s", len(codes_no_history), len(codes), codes_no_history)

    # ================================================================
    # CHECK 3: Pricelist agreement (category/type naming only -- division_db_raw disagreement
    # is EXPECTED per the PEM102<->PEM107 -OLD tag mechanism and is NOT reported as a mismatch here)
    # ================================================================
    logger.info("=== CHECK 3: pricelist agreement (category/type naming) ===")
    db_names = df.groupby("itemcode").agg(
        db_categories=("productCateName", lambda x: sorted(set(x.dropna()))),
        db_types=("productTypeName", lambda x: sorted(set(x.dropna()))),
        db_divisions_seen=("division_db_raw", lambda x: sorted(set(x.dropna()))),
    ).reset_index()

    pl_names = pem102[["code", "category", "type"]].drop_duplicates()
    merged = pl_names.merge(db_names, left_on="code", right_on="itemcode", how="left")
    for col in ("db_categories", "db_types", "db_divisions_seen"):
        merged[col] = merged[col].apply(lambda x: x if isinstance(x, list) else [])

    def cat_status(row):
        if not row["db_categories"]:
            return "no_db_rows_in_scope"
        return "MATCH" if row["category"] in row["db_categories"] else "MISMATCH"

    def type_status(row):
        if not row["db_types"]:
            return "no_db_rows_in_scope"
        return "MATCH" if row["type"] in row["db_types"] else "MISMATCH"

    merged["category_status"] = merged.apply(cat_status, axis=1)
    merged["type_status"] = merged.apply(type_status, axis=1)
    merged["multi_category_in_db"] = merged["db_categories"].apply(lambda x: len(x) > 1)
    merged["multi_type_in_db"] = merged["db_types"].apply(lambda x: len(x) > 1)
    merged.to_csv(outpath("check3_pricelist_agreement.csv"), index=False)
    logger.info("CHECK 3: category_status counts: %s | type_status counts: %s",
                merged["category_status"].value_counts().to_dict(),
                merged["type_status"].value_counts().to_dict())

    # ================================================================
    # CHECK 4: Duplicates and split lots (new basis -- no division filter, so this naturally
    # covers PEM102-vs-PEM107-OLD (and any other cross-tag) duplication for PEM102's own codes)
    # ================================================================
    logger.info("=== CHECK 4: duplicates and split lots ===")
    grp_cols = ["contractid", "itemcode", "createDate", "qty", "sale", "status"]
    df["_key"] = df[grp_cols].astype(str).agg("|".join, axis=1)
    grp_sizes = df.groupby("_key").size()
    dup_keys = grp_sizes[grp_sizes > 1].index
    dup_rows = df[df["_key"].isin(dup_keys)].copy()

    bucket_rows = []
    for key, g in dup_rows.groupby("_key"):
        n_distinct_fd = g["forecast_date"].nunique(dropna=False)
        bucket = "split_lot_plausible" if n_distinct_fd > 1 else "unexplained_duplicate"
        bucket_rows.append({
            "key": key, "n_rows": len(g), "n_distinct_forecast_date": n_distinct_fd,
            "bucket": bucket, "sum_sale": g["sale"].sum(), "sum_qty": g["qty"].sum(),
            "contractid": g["contractid"].iloc[0], "itemcode": g["itemcode"].iloc[0],
            "divisions_db_raw_seen": sorted(set(g["division_db_raw"].dropna())),
        })
    dup_summary = pd.DataFrame(bucket_rows)
    dup_summary.to_csv(outpath("check4_duplicate_groups.csv"), index=False)
    if len(dup_summary):
        agg = dup_summary.groupby("bucket").agg(
            n_groups=("key", "count"), n_rows=("n_rows", "sum"), total_sale=("sum_sale", "sum")
        ).reset_index()
    else:
        agg = pd.DataFrame(columns=["bucket", "n_groups", "n_rows", "total_sale"])
    agg.to_csv(outpath("check4_duplicate_bucket_summary.csv"), index=False)
    logger.info("CHECK 4: %d duplicate-key groups (%d rows) found in the new (no-division-filter) "
                "pull of %d rows. Bucket summary: %s", len(dup_keys), len(dup_rows), len(df),
                agg.to_dict("records"))

    # ================================================================
    # CHECK 5: Cube_CES reconciliation -- identical 5-field-key method to
    # phaseC_full_scope_revalidation.py step4_cube_ces_reconciliation / original PEM107 Check 7.
    # ================================================================
    logger.info("=== CHECK 5: Cube_CES reconciliation (5-field key, no ManuDivision filter) ===")
    sql_ces = f"""
    SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty
    FROM {CES_TABLE}
    WHERE ItemCode IN ({codes_in})
    """
    ces = run_query(sql_ces)
    ces.to_csv(outpath("check5_cube_ces_raw.csv"), index=False)

    apd = df.copy()
    apd["createDate_d"] = apd["createDate"].dt.date
    apd["mapped_status"] = apd["status"].map({"Actual": "Actual", "MPS": "Backlog"})

    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"])
    ces["CtrDate_d"] = ces["CtrDate"].dt.date
    ces["match_qty"] = np.where(ces["Status"] == "Actual", ces["ActualQty"], ces["BacklogQty"])

    merged_ces = apd.merge(
        ces, left_on=["contractid", "itemcode", "createDate_d", "mapped_status", "qty"],
        right_on=["ContractID", "ItemCode", "CtrDate_d", "Status", "match_qty"],
        how="left", indicator=True,
    )
    merged_ces["matched"] = merged_ces["_merge"] == "both"
    merged_ces.to_csv(outpath("check5_cube_ces_merge_detail.csv"), index=False)

    n_apd = len(merged_ces)
    n_matched = int(merged_ces["matched"].sum())
    match_rate = round(100 * n_matched / n_apd, 2) if n_apd else None
    ces_summary = pd.DataFrame([{"division": DIVISION, "n_apd_rows": n_apd, "n_matched": n_matched,
                                  "match_rate_pct": match_rate}])
    ces_summary.to_csv(outpath("check5_cube_ces_reconciliation.csv"), index=False)
    logger.info("CHECK 5: Cube_CES 5-field-key match: %d of %d APD rows (%.2f%%)", n_matched, n_apd,
                match_rate if match_rate is not None else float("nan"))

    # Contract-item level qty reconciliation, for the same additional evidence the original
    # PEM102 report cited. Restricted to CES Status IN ('Actual','Backlog') here (unlike the
    # row-level 5-field match above, which intentionally leaves the CES pull unrestricted per
    # phaseC_full_scope_revalidation.py's method) -- Cube_CES also carries P2/P3/T3/Cancel/MPS
    # status rows for these item codes (see check5_cube_ces_raw.csv), which are not this
    # project's Actual/Backlog reconciliation basis and would otherwise inflate "only in
    # Cube_CES" pair counts with rows that were never comparable to begin with.
    ces_ab = ces[ces["Status"].isin(["Actual", "Backlog"])].copy()
    apd_ci = apd.groupby(["contractid", "itemcode"])["qty"].sum().reset_index().rename(columns={"qty": "apd_qty"})
    ces_ab["_qty2"] = np.where(ces_ab["Status"] == "Actual", ces_ab["ActualQty"], ces_ab["BacklogQty"])
    ces_ci = ces_ab.groupby(["ContractID", "ItemCode"])["_qty2"].sum().reset_index().rename(
        columns={"ContractID": "contractid", "ItemCode": "itemcode", "_qty2": "ces_qty"})
    recon = apd_ci.merge(ces_ci, on=["contractid", "itemcode"], how="outer", indicator=True)
    recon["qty_match"] = np.isclose(recon["apd_qty"].fillna(-1), recon["ces_qty"].fillna(-2))
    recon.to_csv(outpath("check5_contract_item_reconciliation.csv"), index=False)
    both = recon[recon["_merge"] == "both"]
    logger.info("CHECK 5: contract-item pairs: %d total, %d in both sources, %d (%.2f%%) exact qty "
                "match, %d only in cube_Sale_APD, %d only in Cube_CES", len(recon), len(both),
                int(both["qty_match"].sum()), 100 * both["qty_match"].mean() if len(both) else float("nan"),
                (recon["_merge"] == "left_only").sum(), (recon["_merge"] == "right_only").sum())

    # ================================================================
    # CHECK 6: Demand profile
    # ================================================================
    logger.info("=== CHECK 6: demand profile ===")
    max_date = df["createDate"].max()
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_month = pd.Period(max_date, freq="M")
    monthly_complete = df.copy()
    if max_date < month_end:
        logger.info("Latest month %s partial (data ends %s) -- excluded from demand profile.",
                    latest_month, max_date.date())
        monthly_complete = monthly_complete[monthly_complete["year_month"] != str(latest_month)]

    all_months = sorted(monthly_complete["year_month"].unique())
    logger.info("CHECK 6: demand profile window %s to %s (%d months)", all_months[0], all_months[-1], len(all_months))

    monthly_qty = monthly_complete.groupby(["itemcode", "year_month"])["qty"].sum().reset_index()
    full_index = pd.MultiIndex.from_product([codes, all_months], names=["itemcode", "year_month"])
    grid = monthly_qty.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0).reset_index()
    grid.to_csv(outpath("check6_monthly_qty_grid.csv"), index=False)

    item_rows = []
    for item, g in grid.groupby("itemcode"):
        g = g.sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        cls, adi, cv2 = classify_demand(qty)
        n_zero = int((qty == 0).sum())
        item_rows.append({
            "itemcode": item, "n_periods": len(qty), "n_zero_periods": n_zero,
            "pct_zero": round(100 * n_zero / len(qty), 1),
            "ADI": round(adi, 3) if adi is not None else None,
            "CV2": round(cv2, 3) if cv2 is not None else None,
            "classification": cls, "total_qty": float(qty.sum()),
        })
    item_stats = pd.DataFrame(item_rows)
    item_stats.to_csv(outpath("check6_item_demand_classification.csv"), index=False)

    total_value = df["sale"].sum()
    n_with_sales = (item_stats["classification"] != "NoSale").sum()
    has_sales = item_stats[item_stats["classification"] != "NoSale"]
    logger.info(
        "CHECK 6: total value %.2f THB, %d of %d items with any sale, mean pct_zero %.1f%%, "
        "classification counts %s, mean ADI (excl NoSale) %.3f, mean CV2 (excl NoSale) %.3f",
        total_value, n_with_sales, len(item_stats), item_stats["pct_zero"].mean(),
        item_stats["classification"].value_counts().to_dict(),
        has_sales["ADI"].mean() if len(has_sales) else float("nan"),
        has_sales["CV2"].mean() if len(has_sales) else float("nan"),
    )

    summary = {
        "n_codes": len(codes),
        "n_rows_new_basis": len(df),
        "total_value_new_basis": float(total_value),
        "n_items_with_sales": int(n_with_sales),
        "n_no_history_any_filter": len(codes_no_history),
        "codes_no_history": codes_no_history,
        "min_createDate": str(min_create.date()),
        "max_createDate": str(max_create.date()),
        "cube_ces_match_rate_pct": match_rate,
        "n_duplicate_groups": len(dup_keys),
        "n_unexplained_duplicates": int((dup_summary["bucket"] == "unexplained_duplicate").sum()) if len(dup_summary) else 0,
        "n_split_lot_plausible": int((dup_summary["bucket"] == "split_lot_plausible").sum()) if len(dup_summary) else 0,
    }
    pd.DataFrame([summary]).to_csv(outpath("99_run_summary.csv"), index=False)
    logger.info("RUN SUMMARY: %s", summary)
    logger.info("Script complete. See output/summary/phaseC_step1revised_PEM102_*.csv for all "
                "supporting data, and output/summary/phaseC_step1revised_PEM102_report.md for the "
                "written report (authored separately from this script's log output).")


if __name__ == "__main__":
    main()
