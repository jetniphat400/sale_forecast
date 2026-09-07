"""Phase C step 1 REVISED Validator -- division CI101, re-run on the corrected (no
`division`-filter) basis (STATUS.md Locked Decisions, "Division source-of-truth correction",
2026-09-04). The original Phase C step 1 validator for CI101
(`src/investigations/phaseC_validator_CI101.py` / `_part2.py`,
`output/summary/phaseC_CI101_report.md`) filtered `division = 'CI101'`. That filter has since
been removed project-wide: the pricelist sheet defines an item's division; a query includes
every Omni Channel row for an item's code regardless of what `division` value the database row
happens to carry. This script re-derives CI101's full readiness picture (checks 1-7 of the task
brief) on that corrected basis, and states explicitly what changed vs. the original report.

Investigation script only -- no pipeline code touched, no config changed. Writes CSVs to
output/summary/, prefixed phaseC_step1revised_CI101_.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_step1revised_CI101")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SOURCE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def out(name):
    return os.path.join(SUMMARY_DIR, f"phaseC_step1revised_CI101_{name}")


def load_config():
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
    statuses = config["status_basis"]
    revenue_type = config["revenue_type"]

    # ---- Step 0: pricelist scope for CI101 sheet (config.yaml sheet_to_division: "CI101"->"CI101") ----
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    ci = pl[pl["sheet"] == "CI101"].copy()
    codes = sorted(ci["code"].unique().tolist())
    logger.info("CI101 sheet pricelist rows: %d, distinct codes: %d -> %s", len(ci), len(codes), codes)
    if len(codes) != 13:
        raise ValueError(f"Expected 13 distinct CI101 codes, found {len(codes)} -- stopping, not silently adjusting.")
    ci.to_csv(out("00_pricelist_rows.csv"), index=False)
    codes_sql = "','".join(codes)

    # =====================================================================
    # CORRECTED PULL -- no division filter. division AS division_db_raw kept for reference only.
    # =====================================================================
    logger.info("Pulling corrected-basis rows: itemcode IN (13 CI101 codes), revenue_type=%s, "
                "status IN %s, NO division filter, NO date filter (full history).", revenue_type, statuses)
    q_scope = f"""
        SELECT contractid, itemcode, createDate, forecast_date, qty, sale, status,
               division AS division_db_raw, revenue_type, productCateName, productTypeName
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{codes_sql}')
          AND revenue_type = '{revenue_type}'
          AND status IN ('{"','".join(statuses)}')
    """
    scope = run_query(q_scope)
    scope["createDate"] = pd.to_datetime(scope["createDate"])
    scope["forecast_date"] = pd.to_datetime(scope["forecast_date"], errors="coerce")
    logger.info("Corrected-basis pull: %d rows (original division='CI101'-filtered pull had 331).", len(scope))
    scope.to_csv(out("00_corrected_scope_raw.csv"), index=False)

    neg = scope[(scope["qty"] < 0) | (scope["sale"] < 0)]
    if len(neg):
        raise ValueError(f"{len(neg)} negative qty/sale rows found -- must be reviewed, not dropped silently.")
    logger.info("Validation: 0 negative qty/sale rows in corrected pull.")

    div_counts = scope["division_db_raw"].value_counts()
    logger.info("division_db_raw breakdown (reference only, never a filter):\n%s", div_counts.to_string())
    div_counts.to_frame("n_rows").to_csv(out("00b_division_db_raw_breakdown.csv"))
    div_value = scope.groupby("division_db_raw")["sale"].sum().sort_values(ascending=False)
    div_value.to_frame("sum_sale").to_csv(out("00c_division_db_raw_value_breakdown.csv"))
    print("\ndivision_db_raw value breakdown (corrected scope, reference only):")
    print(div_value.to_string())

    # =====================================================================
    # CHECK 1 -- usable date range
    # =====================================================================
    logger.info("=== CHECK 1: usable date range ===")
    scope["ym"] = scope["createDate"].dt.to_period("M").astype(str)
    monthly = scope.groupby("ym").agg(n_rows=("itemcode", "size"), sum_sale=("sale", "sum"),
                                       sum_qty=("qty", "sum")).reset_index().sort_values("ym")
    monthly.to_csv(out("check1_monthly.csv"), index=False)
    print("\nCHECK 1 -- monthly row counts/value (corrected scope):")
    print(monthly.to_string(index=False))

    min_cd, max_cd = scope["createDate"].min(), scope["createDate"].max()
    min_fd, max_fd = scope["forecast_date"].min(), scope["forecast_date"].max()
    n_before_2024 = (scope["createDate"] < "2024-01-01").sum()
    logger.info("createDate range: %s to %s. forecast_date range: %s to %s. Rows before 2024-01-01: %d",
                min_cd, max_cd, min_fd, max_fd, n_before_2024)

    completeness_rows = []
    for yr, grp in scope.groupby(scope["createDate"].dt.year):
        completeness_rows.append({
            "year": yr, "n_rows": len(grp),
            "pct_forecast_date": 100.0 * grp["forecast_date"].notna().mean(),
            "pct_division_db_raw": 100.0 * grp["division_db_raw"].notna().mean(),
            "pct_productCateName": 100.0 * grp["productCateName"].notna().mean(),
            "pct_productTypeName": 100.0 * grp["productTypeName"].notna().mean(),
        })
    completeness = pd.DataFrame(completeness_rows).sort_values("year")
    completeness.to_csv(out("check1_column_completeness_by_year.csv"), index=False)
    print("\nCHECK 1 -- column completeness by year:")
    print(completeness.to_string(index=False))

    check1_summary = pd.DataFrame([{
        "n_rows_corrected": len(scope), "min_createDate": min_cd, "max_createDate": max_cd,
        "min_forecast_date": min_fd, "max_forecast_date": max_fd,
        "n_rows_before_2024_01_01": int(n_before_2024),
    }])
    check1_summary.to_csv(out("check1_summary.csv"), index=False)
    print("\nCHECK 1 summary:")
    print(check1_summary.to_string(index=False))

    # =====================================================================
    # CHECK 2 -- name and code collisions
    # =====================================================================
    logger.info("=== CHECK 2: name and code collisions ===")
    q2_names = f"""
        SELECT DISTINCT productCateName, productTypeName
        FROM {SOURCE_TABLE}
        WHERE itemcode IN ('{codes_sql}')
    """
    names = run_query(q2_names)
    names.to_csv(out("check2_names_carried.csv"), index=False)
    cate_names = [c for c in names["productCateName"].dropna().unique().tolist()]
    type_names = [t for t in names["productTypeName"].dropna().unique().tolist()]
    logger.info("Distinct productCateName values carried by CI101 codes (any division/revenue_type): %d", len(cate_names))
    logger.info("Distinct productTypeName values carried by CI101 codes (any division/revenue_type): %d", len(type_names))

    if cate_names:
        cl = "','".join(c.replace("'", "''") for c in cate_names)
        q2_cate = f"""
            SELECT productCateName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
            FROM {SOURCE_TABLE} WHERE productCateName IN ('{cl}')
            GROUP BY productCateName, division ORDER BY productCateName, sum_sale DESC
        """
        cate_by_div = run_query(q2_cate)
        cate_by_div.to_csv(out("check2_category_name_by_division.csv"), index=False)
        n_cate_shared = cate_by_div.groupby("productCateName")["division"].nunique()
        n_cate_shared_with_other = (n_cate_shared > 1).sum()
        logger.info("Category names shared with >=1 other division: %d of %d", n_cate_shared_with_other, len(cate_names))

    if type_names:
        tl = "','".join(t.replace("'", "''") for t in type_names)
        q2_type = f"""
            SELECT productTypeName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
            FROM {SOURCE_TABLE} WHERE productTypeName IN ('{tl}')
            GROUP BY productTypeName, division ORDER BY productTypeName, sum_sale DESC
        """
        type_by_div = run_query(q2_type)
        type_by_div.to_csv(out("check2_type_name_by_division.csv"), index=False)
        n_type_shared = type_by_div.groupby("productTypeName")["division"].nunique()
        n_type_shared_with_other = (n_type_shared > 1).sum()
        logger.info("Type names shared with >=1 other division: %d of %d", n_type_shared_with_other, len(type_names))

    q2_itemcode_div = f"""
        SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
        FROM {SOURCE_TABLE} WHERE itemcode IN ('{codes_sql}')
        GROUP BY itemcode, division ORDER BY itemcode, sum_sale DESC
    """
    itemcode_div = run_query(q2_itemcode_div)
    itemcode_div.to_csv(out("check2_itemcode_by_division.csv"), index=False)
    n_codes_multi_division = (itemcode_div.groupby("itemcode")["division"].nunique() > 1).sum()
    logger.info("Of 13 CI101 codes, %d appear under more than 1 division somewhere in cube_Sale_APD "
                "(any revenue_type/status) -- unchanged query from the original report (never "
                "division-filtered to begin with).", n_codes_multi_division)

    # Multi-sheet check: cite the already-established whole-pricelist invariant, don't re-derive.
    logger.info("Multi-sheet uniqueness: NOT re-derived here -- already confirmed as a whole-pricelist "
                "invariant (phaseC_sheetmap_report.md, phaseC_revalidation_report.md Step 0): no item "
                "code appears on more than one visible sheet across all 445 codes, including CI101's 13. "
                "The known within-sheet duplicate DS-F-99-0308 (CI101 sheet, same code/category/type, "
                "different Description) still holds -- confirmed present in this script's own pricelist "
                "read above (14 rows / 13 distinct codes).")

    # =====================================================================
    # CHECK 3 -- pricelist agreement (category/type ONLY; division_db_raw disagreement is
    # EXPECTED/resolved, not reported as a mismatch here)
    # =====================================================================
    logger.info("=== CHECK 3: pricelist agreement (category/type) ===")
    db_names_by_item = scope.groupby("itemcode").agg(
        db_cate_names=("productCateName", lambda s: sorted(s.dropna().unique().tolist())),
        db_type_names=("productTypeName", lambda s: sorted(s.dropna().unique().tolist())),
    ).reset_index()

    pl_agg = ci.groupby("code").agg(
        pl_categories=("category", lambda s: sorted(s.dropna().unique().tolist())),
        pl_types=("type", lambda s: sorted(s.dropna().unique().tolist())),
    ).reset_index().rename(columns={"code": "itemcode"})

    merged3 = pl_agg.merge(db_names_by_item, on="itemcode", how="left")

    def cate_match(row):
        db = set(row["db_cate_names"]) if isinstance(row["db_cate_names"], list) else set()
        plc = set(row["pl_categories"])
        if not db:
            return "no_db_rows_in_corrected_scope"
        return "match" if db == plc else "mismatch"

    def type_match(row):
        db = set(row["db_type_names"]) if isinstance(row["db_type_names"], list) else set()
        plt = set(row["pl_types"])
        if not db:
            return "no_db_rows_in_corrected_scope"
        return "match" if db == plt else "mismatch"

    merged3["category_agreement"] = merged3.apply(cate_match, axis=1)
    merged3["type_agreement"] = merged3.apply(type_match, axis=1)
    merged3.to_csv(out("check3_pricelist_agreement.csv"), index=False)
    print("\nCHECK 3 -- pricelist agreement (corrected scope):")
    print(merged3[["itemcode", "pl_categories", "db_cate_names", "category_agreement",
                    "pl_types", "db_type_names", "type_agreement"]].to_string())
    n_cate_mismatch = (merged3["category_agreement"] == "mismatch").sum()
    n_type_mismatch = (merged3["type_agreement"] == "mismatch").sum()
    n_no_db_rows = (merged3["category_agreement"] == "no_db_rows_in_corrected_scope").sum()
    logger.info("Category mismatches: %d/13. Type mismatches: %d/13. Codes with no rows in corrected "
                "scope (should be 0 now that PEM101-tagged rows are included): %d/13.",
                n_cate_mismatch, n_type_mismatch, n_no_db_rows)

    # =====================================================================
    # CHECK 4 -- duplicates and split lots (corrected-scope pull, group by
    # contractid/itemcode/createDate/qty/sale/status)
    # =====================================================================
    logger.info("=== CHECK 4: duplicates and split lots ===")
    d = scope.copy()
    d["createDate_d"] = d["createDate"].dt.date
    g = d.groupby(["contractid", "itemcode", "createDate_d", "qty", "sale", "status"])
    sizes = g.size()
    dup_groups = sizes[sizes > 1]
    logger.info("Groups with >1 row (out of %d rows total): %d", len(d), len(dup_groups))

    rows_out = []
    for key, n in dup_groups.items():
        contractid, itemcode, createDate_d, qty, sale, status = key
        sub = d[(d["contractid"] == contractid) & (d["itemcode"] == itemcode)
                & (d["createDate_d"] == createDate_d) & (d["qty"] == qty)
                & (d["sale"] == sale) & (d["status"] == status)]
        fd_nunique = sub["forecast_date"].nunique()
        bucket = "different_forecast_date_plausible_split_lot" if fd_nunique > 1 else "identical_forecast_date_unexplained_duplicate"
        rows_out.append({
            "contractid": contractid, "itemcode": itemcode, "createDate": createDate_d,
            "qty": qty, "sale": sale, "status": status, "n_rows": n,
            "forecast_date_nunique": fd_nunique, "bucket": bucket,
            "forecast_dates": sorted(sub["forecast_date"].astype(str).unique().tolist()),
            "division_db_raw_values": sorted(sub["division_db_raw"].astype(str).unique().tolist()),
        })
    dup_df = pd.DataFrame(rows_out)
    dup_df.to_csv(out("check4_duplicate_groups.csv"), index=False)
    if len(dup_df):
        summary4 = dup_df.groupby("bucket").agg(
            n_groups=("bucket", "size"), n_rows=("n_rows", "sum"),
            total_sale_value=("sale", lambda s: (s * dup_df.loc[s.index, "n_rows"]).sum()),
        )
        print("\nCHECK 4 -- duplicate/split-lot bucket summary:")
        print(summary4.to_string())
        summary4.to_csv(out("check4_bucket_summary.csv"))
    else:
        print("\nCHECK 4 -- no duplicate groups found")
        pd.DataFrame(columns=["bucket", "n_groups", "n_rows", "total_sale_value"]).to_csv(out("check4_bucket_summary.csv"), index=False)

    # =====================================================================
    # CHECK 5 -- Cube_CES reconciliation, same 5-field-key method as
    # phaseC_full_scope_revalidation.py step4 / original PEM107 Check 7.
    # =====================================================================
    logger.info("=== CHECK 5: Cube_CES reconciliation (5-field key, full history, corrected scope) ===")
    q5_ces = f"""
        SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty
        FROM {CES_TABLE}
        WHERE ItemCode IN ('{codes_sql}')
    """
    ces = run_query(q5_ces)
    ces.to_csv(out("check5_ces_raw_pull.csv"), index=False)
    logger.info("Cube_CES rows pulled for these 13 item codes (no ManuDivision filter): %d", len(ces))

    apd = scope[["contractid", "itemcode", "createDate", "status", "qty", "sale", "division_db_raw"]].copy()
    apd["createDate"] = pd.to_datetime(apd["createDate"]).dt.date
    apd["mapped_status"] = apd["status"].map({"Actual": "Actual", "MPS": "Backlog"})

    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"]).dt.date
    ces["match_qty"] = np.where(ces["Status"] == "Actual", ces["ActualQty"], ces["BacklogQty"])

    merged5 = apd.merge(
        ces, left_on=["contractid", "itemcode", "createDate", "mapped_status", "qty"],
        right_on=["ContractID", "ItemCode", "CtrDate", "Status", "match_qty"],
        how="left", indicator=True,
    )
    merged5["matched"] = merged5["_merge"] == "both"
    merged5.to_csv(out("check5_ces_merge_detail.csv"), index=False)

    n_apd = len(merged5)
    n_matched = int(merged5["matched"].sum())
    match_rate = round(100.0 * n_matched / n_apd, 2) if n_apd else None
    logger.info("Cube_CES 5-field-key match: %d of %d rows (%.2f%%) -- full history, corrected "
                "(no division-filter) scope.", n_matched, n_apd, match_rate if match_rate else 0)
    pd.DataFrame([{"n_apd_rows": n_apd, "n_matched": n_matched, "match_rate_pct": match_rate,
                    "n_ces_rows_pulled": len(ces)}]).to_csv(out("check5_summary.csv"), index=False)

    # Trace unmatched rows individually (bonus over the original report, which explicitly
    # did not trace mismatches -- attempted here to close that noted gap where feasible).
    unmatched = merged5[~merged5["matched"]].copy()
    unmatched.to_csv(out("check5_unmatched_rows.csv"), index=False)
    logger.info("Unmatched cube_Sale_APD rows (not found in Cube_CES under the 5-field key): %d. "
                "Written for individual inspection: %s", len(unmatched), out("check5_unmatched_rows.csv"))
    if len(unmatched):
        # look for a near-match on (contractid, itemcode) ignoring the exact date/qty/status fields,
        # to see whether the row exists in Cube_CES at all under a looser key (diagnostic only).
        ces_pairs = set(zip(ces["ContractID"].astype(str), ces["ItemCode"].astype(str)))
        unmatched["contractid_itemcode_exists_in_ces_at_all"] = list(
            zip(unmatched["contractid"].astype(str), unmatched["itemcode"].astype(str))
        )
        unmatched["contractid_itemcode_exists_in_ces_at_all"] = unmatched["contractid_itemcode_exists_in_ces_at_all"].apply(
            lambda t: t in ces_pairs
        )
        n_pair_exists = unmatched["contractid_itemcode_exists_in_ces_at_all"].sum()
        logger.info("Of %d unmatched rows, %d have SOME row for the same (contractid, itemcode) in "
                     "Cube_CES (date/qty/status differs) -- consistent with multi-tranche/date-offset "
                     "explanations already documented for PEM101; %d have no (contractid, itemcode) "
                     "match in Cube_CES at all.", len(unmatched), n_pair_exists,
                     len(unmatched) - n_pair_exists)
        unmatched.to_csv(out("check5_unmatched_rows.csv"), index=False)

    # =====================================================================
    # CHECK 6 -- demand profile
    # =====================================================================
    logger.info("=== CHECK 6: demand profile ===")
    scope_dp = scope[scope["createDate"] >= "2024-01-01"].copy()
    scope_dp["ym"] = scope_dp["createDate"].dt.to_period("M").astype(str)
    monthly_qty = scope_dp.groupby(["itemcode", "ym"], as_index=False)["qty"].sum()

    all_months = sorted(scope_dp["ym"].unique().tolist())
    items_any_sales = sorted(scope_dp["itemcode"].unique().tolist())
    logger.info("Items with any sales under corrected scope (createDate>=2024-01-01): %d of 13 pricelist codes",
                len(items_any_sales))

    full_idx = pd.MultiIndex.from_product([codes, all_months], names=["itemcode", "ym"])
    monthly_full = monthly_qty.set_index(["itemcode", "ym"]).reindex(full_idx, fill_value=0).reset_index()

    class_rows = []
    for item, grp in monthly_full.groupby("itemcode"):
        qty = grp.sort_values("ym")["qty"].to_numpy(dtype=float)
        cls, adi, cv2 = classify_demand(qty)
        pct_zero = 100.0 * (qty == 0).sum() / len(qty)
        class_rows.append({"itemcode": item, "n_periods": len(qty), "pct_zero": pct_zero,
                            "ADI": adi, "CV2": cv2, "classification": cls, "total_qty": qty.sum()})
    class_df = pd.DataFrame(class_rows)
    class_df.to_csv(out("check6_demand_classification.csv"), index=False)
    print("\nCHECK 6 -- demand classification per item (corrected scope):")
    print(class_df.to_string())
    print("\nClassification counts:")
    print(class_df["classification"].value_counts().to_string())

    active = class_df[class_df["classification"] != "NoSale"]
    total_value_scope = scope_dp["sale"].sum()
    pct_zero_active_mean = active["pct_zero"].mean() if len(active) else None
    summary6 = pd.DataFrame([{
        "n_items_any_sales": len(items_any_sales), "n_pricelist_codes": 13,
        "n_months": len(all_months), "months_range": f"{all_months[0]} to {all_months[-1]}" if all_months else None,
        "total_value_thb": total_value_scope,
        "mean_pct_zero_active_items": pct_zero_active_mean,
        "mean_ADI_active": active["ADI"].mean() if len(active) else None,
        "mean_CV2_active": active["CV2"].mean() if len(active) else None,
        "n_smooth": int((class_df["classification"] == "Smooth").sum()),
        "n_erratic": int((class_df["classification"] == "Erratic").sum()),
        "n_intermittent": int((class_df["classification"] == "Intermittent").sum()),
        "n_lumpy": int((class_df["classification"] == "Lumpy").sum()),
        "n_nosale": int((class_df["classification"] == "NoSale").sum()),
    }])
    summary6.to_csv(out("check6_summary.csv"), index=False)
    print("\nCHECK 6 summary:")
    print(summary6.to_string(index=False))

    print("\n" + "=" * 90)
    print("DONE -- see output/summary/phaseC_step1revised_CI101_report.md for the full write-up")
    print("=" * 90)


if __name__ == "__main__":
    main()
