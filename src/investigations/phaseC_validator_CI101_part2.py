"""Phase C Validator — division CI101, part 2: checks 4-8 (duplicates, pricelist agreement,
items without history, Cube_CES cross-check, demand profile). Reuses the raw pull from part 1
(output/summary/phaseC_CI101_raw_all_rows_any_filter.csv) plus targeted new queries.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("phaseC_CI101_p2")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def out(name):
    return os.path.join(SUMMARY_DIR, f"phaseC_CI101_{name}")


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
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    ci = pl[pl["business"] == "CI101"].copy()
    codes = sorted(ci["code"].unique().tolist())
    codes_sql_list = ", ".join(f"'{c}'" for c in codes)

    raw_all = pd.read_csv(out("raw_all_rows_any_filter.csv"), parse_dates=["createDate", "forecast_date"])

    # Concluded in-scope filter: division='CI101', revenue_type='Omni Channel'
    scope = raw_all[(raw_all["division"] == "CI101") & (raw_all["revenue_type"] == "Omni Channel")].copy()
    logger.info("In-scope rows (division=CI101, revenue_type=Omni Channel): %d", len(scope))

    # =====================================================================
    # CHECK 4 — duplicates and split lots
    # =====================================================================
    logger.info("CHECK 4: duplicates and split lots")
    grp_cols = ["contractid", "itemcode", "createDate", "qty", "sale", "status"]
    scope["createDate_d"] = scope["createDate"].dt.date
    g = scope.groupby(["contractid", "itemcode", "createDate_d", "qty", "sale", "status"])
    group_sizes = g.size()
    dup_groups = group_sizes[group_sizes > 1]
    logger.info("Groups with >1 row: %d", len(dup_groups))

    rows_out = []
    for key, n in dup_groups.items():
        contractid, itemcode, createDate_d, qty, sale, status = key
        sub = scope[
            (scope["contractid"] == contractid)
            & (scope["itemcode"] == itemcode)
            & (scope["createDate_d"] == createDate_d)
            & (scope["qty"] == qty)
            & (scope["sale"] == sale)
            & (scope["status"] == status)
        ]
        fd_nunique = sub["forecast_date"].nunique()
        bucket = "different_forecast_date_plausible_split_lot" if fd_nunique > 1 else "identical_forecast_date_unexplained_duplicate"
        rows_out.append({
            "contractid": contractid, "itemcode": itemcode, "createDate": createDate_d,
            "qty": qty, "sale": sale, "status": status, "n_rows": n,
            "forecast_date_nunique": fd_nunique, "bucket": bucket,
            "forecast_dates": sorted(sub["forecast_date"].astype(str).unique().tolist()),
        })
    dup_df = pd.DataFrame(rows_out)
    dup_df.to_csv(out("check4_duplicate_groups.csv"), index=False)

    if len(dup_df):
        summary = dup_df.groupby("bucket").agg(
            n_groups=("bucket", "size"),
            n_rows=("n_rows", "sum"),
            total_sale_value=("sale", lambda s: (s * dup_df.loc[s.index, "n_rows"]).sum()),
        )
        print("\nCHECK 4 — duplicate/split-lot bucket summary:")
        print(summary.to_string())
        summary.to_csv(out("check4_bucket_summary.csv"))
    else:
        print("\nCHECK 4 — no duplicate groups found (all (contractid,itemcode,createDate,qty,sale,status) combos are unique)")

    # =====================================================================
    # CHECK 5 — pricelist agreement
    # =====================================================================
    logger.info("CHECK 5: pricelist agreement")
    db_names = scope.groupby("itemcode").agg(
        db_cate_names=("productCateName", lambda s: sorted(s.dropna().unique().tolist())),
        db_type_names=("productTypeName", lambda s: sorted(s.dropna().unique().tolist())),
    ).reset_index()

    pl_agg = ci.groupby("code").agg(
        pl_categories=("category", lambda s: sorted(s.dropna().unique().tolist())),
        pl_types=("type", lambda s: sorted(s.dropna().unique().tolist())),
        pl_descriptions=("description", lambda s: sorted(s.dropna().unique().tolist())),
    ).reset_index().rename(columns={"code": "itemcode"})

    merged = pl_agg.merge(db_names, on="itemcode", how="left")

    def cate_match(row):
        db = set(row["db_cate_names"]) if isinstance(row["db_cate_names"], list) else set()
        pl_ = set(row["pl_categories"])
        if not db:
            return "no_db_rows"
        return "match" if db == pl_ else "mismatch"

    def type_match(row):
        db = set(row["db_type_names"]) if isinstance(row["db_type_names"], list) else set()
        pl_ = set(row["pl_types"])
        if not db:
            return "no_db_rows"
        return "match" if db == pl_ else "mismatch"

    merged["category_agreement"] = merged.apply(cate_match, axis=1)
    merged["type_agreement"] = merged.apply(type_match, axis=1)
    merged.to_csv(out("check5_pricelist_agreement.csv"), index=False)
    print("\nCHECK 5 — pricelist agreement:")
    print(merged[["itemcode", "pl_categories", "db_cate_names", "category_agreement",
                   "pl_types", "db_type_names", "type_agreement"]].to_string())

    # DS-F-99-0308 within-sheet duplicate detail
    dup0308 = ci[ci["code"] == "DS-F-99-0308"]
    dup0308.to_csv(out("check5_DS-F-99-0308_pricelist_rows.csv"), index=False)

    # =====================================================================
    # CHECK 6 — items without history
    # =====================================================================
    logger.info("CHECK 6: items without history")
    codes_with_any_row = set(raw_all["itemcode"].unique().tolist())
    no_history_codes = [c for c in codes if c not in codes_with_any_row]
    logger.info("Codes with zero rows in cube_Sale_APD under ANY filter: %d -> %s", len(no_history_codes), no_history_codes)

    no_hist_rows = []
    if no_history_codes:
        nh_list_sql = ", ".join(f"'{c}'" for c in no_history_codes)
        ces_q = f"SELECT * FROM [salewarehouse].[dbo].[Cube_CES] WHERE ItemCode IN ({nh_list_sql})"
        ces_df = run_query(ces_q)
        inv_q = f"SELECT * FROM [salewarehouse].[dbo].[Cube_Inventory_Exact] WHERE itemcode IN ({nh_list_sql})"
        try:
            inv_df = run_query(inv_q)
        except Exception as e:
            logger.warning("Cube_Inventory_Exact query failed: %s", e)
            inv_df = pd.DataFrame()
        quot_q = f"SELECT * FROM [salewarehouse].[dbo].[Cube_Quotation] WHERE itemcode IN ({nh_list_sql})"
        try:
            quot_df = run_query(quot_q)
        except Exception as e:
            logger.warning("Cube_Quotation query failed: %s", e)
            quot_df = pd.DataFrame()

        for c in no_history_codes:
            no_hist_rows.append({
                "itemcode": c,
                "cube_Sale_APD_rows": 0,
                "Cube_CES_rows": int((ces_df["ItemCode"] == c).sum()) if len(ces_df) else 0,
                "Cube_Inventory_Exact_rows": int((inv_df["itemcode"] == c).sum()) if len(inv_df) and "itemcode" in inv_df.columns else 0,
                "Cube_Quotation_rows": int((quot_df["itemcode"] == c).sum()) if len(quot_df) and "itemcode" in quot_df.columns else 0,
            })
        ces_df.to_csv(out("check6_ces_rows_no_history_items.csv"), index=False)
        inv_df.to_csv(out("check6_inventory_rows_no_history_items.csv"), index=False)
        quot_df.to_csv(out("check6_quotation_rows_no_history_items.csv"), index=False)
    no_hist_summary = pd.DataFrame(no_hist_rows) if no_hist_rows else pd.DataFrame(
        columns=["itemcode", "cube_Sale_APD_rows", "Cube_CES_rows", "Cube_Inventory_Exact_rows", "Cube_Quotation_rows"])
    no_hist_summary.to_csv(out("check6_no_history_items_crosscheck.csv"), index=False)
    print("\nCHECK 6 — items without history (any filter) cross-check:")
    print(no_hist_summary.to_string() if len(no_hist_summary) else "(none — all 13 codes have at least one row in cube_Sale_APD)")

    # =====================================================================
    # CHECK 7 — cross-check against Cube_CES
    # =====================================================================
    logger.info("CHECK 7: Cube_CES cross-check")
    ces_full_q = f"""
    SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty, PlanQty,
           ActualDelDate, PlanDelDate, ForecastDelDate, ManuDivision, SaleDivision, RevenueType
    FROM [salewarehouse].[dbo].[Cube_CES]
    WHERE ItemCode IN ({codes_sql_list})
      AND ManuDivision = 'CI101' AND RevenueType = 'Omni Channel'
      AND Status IN ('Actual', 'Backlog')
      AND CtrDate >= '2024-01-01'
    """
    ces_scope = run_query(ces_full_q)
    ces_scope.to_csv(out("check7_ces_scope_pull.csv"), index=False)
    logger.info("Cube_CES scope rows: %d", len(ces_scope))

    # apply the project's MPS<->Backlog status mapping, established for PEM101
    scope_2024 = scope[scope["createDate"] >= "2024-01-01"].copy()
    scope_2024["mapped_status"] = scope_2024["status"].map({"Actual": "Actual", "MPS": "Backlog"})

    apd_keys = set(zip(
        scope_2024["contractid"].astype(str),
        scope_2024["itemcode"].astype(str),
        scope_2024["createDate"].dt.date.astype(str),
        scope_2024["mapped_status"].astype(str),
        scope_2024["qty"].astype(float),
    ))
    ces_scope["CtrDate_d"] = pd.to_datetime(ces_scope["CtrDate"]).dt.date.astype(str)
    ces_keys = set(zip(
        ces_scope["ContractID"].astype(str),
        ces_scope["ItemCode"].astype(str),
        ces_scope["CtrDate_d"],
        ces_scope["Status"].astype(str),
        ces_scope["ActualQty"].fillna(0).astype(float),
    )) if len(ces_scope) else set()
    ces_keys_backlog = set(zip(
        ces_scope["ContractID"].astype(str),
        ces_scope["ItemCode"].astype(str),
        ces_scope["CtrDate_d"],
        ces_scope["Status"].astype(str),
        ces_scope["BacklogQty"].fillna(0).astype(float),
    )) if len(ces_scope) else set()
    all_ces_keys = ces_keys | ces_keys_backlog

    matched = sum(1 for k in apd_keys if k in all_ces_keys)
    n_apd = len(apd_keys)
    match_rate = 100.0 * matched / n_apd if n_apd else None
    print(f"\nCHECK 7 — row-level match rate (cube_Sale_APD distinct keys found in Cube_CES): "
          f"{matched}/{n_apd} = {match_rate}%" if n_apd else "\nCHECK 7 — no in-scope 2024+ rows to check")
    pd.DataFrame([{"n_apd_distinct_keys": n_apd, "n_matched_in_ces": matched, "match_rate_pct": match_rate,
                    "n_ces_scope_rows": len(ces_scope)}]).to_csv(out("check7_ces_reconciliation_summary.csv"), index=False)

    # =====================================================================
    # CHECK 8 — demand profile
    # =====================================================================
    logger.info("CHECK 8: demand profile")
    scope["year_month"] = scope["createDate"].dt.to_period("M").astype(str)
    monthly = scope.groupby(["itemcode", "year_month"], as_index=False)["qty"].sum()

    all_months = sorted(scope["year_month"].unique().tolist())
    items_any_sales = sorted(scope["itemcode"].unique().tolist())
    logger.info("Items with any sales under scope filter: %d of %d pricelist codes", len(items_any_sales), len(codes))

    full_index = pd.MultiIndex.from_product([items_any_sales, all_months], names=["itemcode", "year_month"])
    monthly_full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0).reset_index()

    class_rows = []
    for item, g in monthly_full.groupby("itemcode"):
        qty = g.sort_values("year_month")["qty"].to_numpy(dtype=float)
        cls, adi, cv2 = classify_demand(qty)
        pct_zero = 100.0 * (qty == 0).sum() / len(qty)
        class_rows.append({"itemcode": item, "n_periods": len(qty), "pct_zero": pct_zero,
                            "ADI": adi, "CV2": cv2, "classification": cls, "total_qty": qty.sum()})
    class_df = pd.DataFrame(class_rows)
    class_df.to_csv(out("check8_demand_classification.csv"), index=False)
    print("\nCHECK 8 — demand classification per item:")
    print(class_df.to_string())
    print("\nClassification counts:")
    print(class_df["classification"].value_counts().to_string())
    print(f"\nMean ADI: {class_df['ADI'].mean():.3f}  Mean CV2: {class_df['CV2'].mean():.3f}")
    print(f"Mean pct_zero: {class_df['pct_zero'].mean():.1f}%")
    print(f"Total value (THB) in scope: {scope['sale'].sum():,.2f}")

    summary8 = pd.DataFrame([{
        "n_items_any_sales": len(items_any_sales),
        "n_pricelist_codes": len(codes),
        "total_value_thb": scope["sale"].sum(),
        "mean_pct_zero_item_months": class_df["pct_zero"].mean(),
        "mean_ADI": class_df["ADI"].mean(),
        "mean_CV2": class_df["CV2"].mean(),
    }])
    summary8.to_csv(out("check8_summary.csv"), index=False)


if __name__ == "__main__":
    main()
