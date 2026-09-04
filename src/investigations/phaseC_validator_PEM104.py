"""Phase C Validator — PEM104 data-quality checks (8 checks per AGENTS.md/STATUS.md
Phase C task spec). Independent of the other four parallel Validators (PEM102, PEM103,
PEM107, CI101). Writes CSVs to output/summary/ with a phaseC_PEM104_ prefix.

Read-only: never writes to config.yaml or any pipeline code, never modifies DB data.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseC_PEM104")

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PREFIX = "phaseC_PEM104_"


def out(name):
    return os.path.join(SUMMARY_DIR, f"{PREFIX}{name}")


def save(df, name):
    path = out(name)
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d rows)", path, len(df))
    return path


def q(sql):
    logger.info("Query: %s", sql[:200].replace("\n", " "))
    return run_query(sql)


def code_list_sql(codes):
    return ",".join("'" + c.replace("'", "''") + "'" for c in codes)


if __name__ == "__main__":
    # ---- Step 0: get PEM104 item codes from pricelist ----
    pricelist = load_visible_product_rows(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"))
    pem104 = pricelist[pricelist["business"] == "PEM104"].copy()
    logger.info("Pricelist rows with business == 'PEM104': %d", len(pem104))
    logger.info("Distinct sheets carrying these rows: %s", pem104["sheet"].unique().tolist())
    save(pem104, "pricelist_rows.csv")

    codes = sorted(pem104["code"].unique().tolist())
    n_dupe_rows = len(pem104) - len(codes)
    logger.info("Distinct PEM104 item codes: %d (row count %d, within-sheet dup rows: %d)",
                len(codes), len(pem104), n_dupe_rows)

    with open(out("item_codes.txt"), "w") as f:
        f.write("\n".join(codes))

    code_sql = code_list_sql(codes)

    # ============================================================
    # CHECK 1 — filter definition: every (division, revenue_type) pair
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 1: filter definition")
    sql1 = f"""
    SELECT division, revenue_type, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty,
           COUNT(DISTINCT itemcode) AS n_distinct_items,
           MIN(createDate) AS min_createDate, MAX(createDate) AS max_createDate
    FROM {{table}}
    WHERE itemcode IN ({code_sql})
    GROUP BY division, revenue_type
    ORDER BY sum_sale DESC
    """.format(table="[salewarehouse].[dbo].[cube_Sale_APD]")
    check1 = q(sql1)
    save(check1, "check1_division_revenuetype_pairs.csv")
    print(check1.to_string())

    # Pull ALL raw rows (unfiltered by division/revenue_type/status) for full detail
    sql1b = f"""
    SELECT itemcode, createDate, forecast_date, qty, sale, status, division, revenue_type,
           productCateName, productTypeName, contractid, quotationid, jobcode, timeStamp
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql})
    """
    raw_all = q(sql1b)
    save(raw_all, "check1_raw_all_rows_unfiltered.csv")
    logger.info("Total unfiltered rows for PEM104 item codes: %d", len(raw_all))
    print(raw_all.to_string())

    # ============================================================
    # CHECK 2 — usable date range: monthly row count/value + column completeness by year
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 2: usable date range")
    raw_all["createDate"] = pd.to_datetime(raw_all["createDate"])
    raw_all["year_month"] = raw_all["createDate"].dt.to_period("M").astype(str)
    raw_all["year"] = raw_all["createDate"].dt.year

    monthly = raw_all.groupby("year_month", as_index=False).agg(
        n_rows=("itemcode", "count"), sum_qty=("qty", "sum"), sum_sale=("sale", "sum")
    ).sort_values("year_month")
    save(monthly, "check2_monthly_rowcount_value.csv")
    print(monthly.to_string())

    completeness_cols = ["revenue_type", "forecast_date", "division", "status", "productCateName", "productTypeName"]
    comp_rows = []
    for yr, g in raw_all.groupby("year"):
        row = {"year": yr, "n_rows": len(g)}
        for c in completeness_cols:
            row[f"pct_nonnull_{c}"] = round(100 * g[c].notna().mean(), 1)
        comp_rows.append(row)
    completeness = pd.DataFrame(comp_rows).sort_values("year")
    save(completeness, "check2_column_completeness_by_year.csv")
    print(completeness.to_string())

    logger.info("Overall min createDate: %s, max createDate: %s", raw_all["createDate"].min(), raw_all["createDate"].max())

    # ============================================================
    # CHECK 3 — name and code collisions
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 3: name/code collisions")

    cate_names = sorted(raw_all["productCateName"].dropna().unique().tolist())
    type_names = sorted(raw_all["productTypeName"].dropna().unique().tolist())
    logger.info("Distinct productCateName values carried by PEM104 items: %s", cate_names)
    logger.info("Distinct productTypeName values carried by PEM104 items: %s", type_names)

    cate_sql = ",".join("'" + c.replace("'", "''") + "'" for c in cate_names)
    sql3a = f"""
    SELECT productCateName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE productCateName IN ({cate_sql})
    GROUP BY productCateName, division
    ORDER BY productCateName, sum_sale DESC
    """
    cate_collision = q(sql3a)
    save(cate_collision, "check3_category_name_by_division.csv")
    print(cate_collision.to_string())

    type_sql = ",".join("'" + t.replace("'", "''") + "'" for t in type_names)
    sql3b = f"""
    SELECT productTypeName, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE productTypeName IN ({type_sql})
    GROUP BY productTypeName, division
    ORDER BY productTypeName, sum_sale DESC
    """
    type_collision = q(sql3b)
    save(type_collision, "check3_type_name_by_division.csv")
    print(type_collision.to_string())

    # Itemcode collisions: does each PEM104 itemcode appear under a different division anywhere?
    sql3c = f"""
    SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM [salewarehouse].[dbo].[cube_Sale_APD]
    WHERE itemcode IN ({code_sql})
    GROUP BY itemcode, division
    ORDER BY itemcode, sum_sale DESC
    """
    item_division = q(sql3c)
    save(item_division, "check3_itemcode_by_division.csv")
    print(item_division.to_string())

    # ============================================================
    # CHECK 4 — duplicates and split lots
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 4: duplicates and split lots")
    # Filter per Check 1 conclusion: division='PEM104', revenue_type='Omni Channel'
    scope = raw_all[(raw_all["division"] == "PEM104") & (raw_all["revenue_type"] == "Omni Channel")].copy()
    dup_key = ["contractid", "itemcode", "createDate", "qty", "sale", "status"]
    grp_sizes = scope.groupby(dup_key).size().reset_index(name="n_rows_in_group")
    dup_groups = grp_sizes[grp_sizes["n_rows_in_group"] > 1]
    logger.info("Groups with >1 row on (contractid,itemcode,createDate,qty,sale,status): %d", len(dup_groups))
    save(dup_groups, "check4_duplicate_groups.csv")
    if len(dup_groups) > 0:
        merged = scope.merge(dup_groups[dup_key], on=dup_key, how="inner")
        save(merged, "check4_duplicate_group_detail.csv")
        for _, g in merged.groupby(dup_key):
            fd_nunique = g["forecast_date"].nunique()
            logger.info("Group %s: %d rows, %d distinct forecast_date values", dict(zip(dup_key, g.iloc[0][dup_key])), len(g), fd_nunique)
    else:
        logger.info("No duplicate groups found — every row is unique on the 6-column key. With only %d rows in scope, this is expected.", len(scope))
    print(f"n_rows_in_scope={len(scope)}, n_duplicate_groups={len(dup_groups)}")

    # ============================================================
    # CHECK 5 — pricelist agreement
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 5: pricelist agreement")
    pl_lookup = pem104.set_index("code")[["category", "type"]].to_dict("index")
    db_by_item = raw_all.groupby("itemcode").agg(
        db_categories=("productCateName", lambda s: sorted(s.dropna().unique().tolist())),
        db_types=("productTypeName", lambda s: sorted(s.dropna().unique().tolist())),
        n_rows=("itemcode", "count"),
    ).reset_index()

    agreement_rows = []
    for code in codes:
        pl_cat = pl_lookup.get(code, {}).get("category")
        pl_type = pl_lookup.get(code, {}).get("type")
        db_row = db_by_item[db_by_item["itemcode"] == code]
        if len(db_row) == 0:
            db_cats, db_types, n_rows = [], [], 0
        else:
            db_cats = db_row.iloc[0]["db_categories"]
            db_types = db_row.iloc[0]["db_types"]
            n_rows = db_row.iloc[0]["n_rows"]
        cat_match = (len(db_cats) == 0) or (pl_cat in db_cats)
        type_match = (len(db_types) == 0) or (pl_type in db_types) or (pl_type in (None, "") and len(db_types) > 0)
        agreement_rows.append({
            "itemcode": code, "pricelist_category": pl_cat, "pricelist_type": pl_type,
            "db_categories": "; ".join(db_cats) if db_cats else None,
            "db_types": "; ".join(db_types) if db_types else None,
            "n_db_rows": n_rows, "category_match": cat_match, "type_match": type_match,
        })
    agreement = pd.DataFrame(agreement_rows)
    save(agreement, "check5_pricelist_vs_db_agreement.csv")
    print(agreement.to_string())

    # ============================================================
    # CHECK 6 — items without history: exhaustive per-item trace
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 6: items without history")
    has_sale_apd = set(raw_all["itemcode"].unique())
    no_history_codes = [c for c in codes if c not in has_sale_apd]
    logger.info("%d of %d PEM104 codes have ZERO rows in cube_Sale_APD under any filter: %s",
                len(no_history_codes), len(codes), no_history_codes)

    per_item_rows = []
    for code in codes:
        row = {"itemcode": code, "in_cube_Sale_APD": code in has_sale_apd}
        # Cube_CES
        ces = q(f"SELECT COUNT(*) AS n, MIN(CtrDate) AS min_date, MAX(CtrDate) AS max_date "
                f"FROM [salewarehouse].[dbo].[Cube_CES] WHERE ItemCode = '{code}'")
        row["ces_n_rows"] = int(ces.iloc[0]["n"])
        row["ces_min_date"] = ces.iloc[0]["min_date"]
        row["ces_max_date"] = ces.iloc[0]["max_date"]
        if row["ces_n_rows"] > 0:
            ces_st = q(f"SELECT DISTINCT Status FROM [salewarehouse].[dbo].[Cube_CES] WHERE ItemCode = '{code}'")
            row["ces_statuses"] = "|".join(ces_st["Status"].dropna().astype(str).tolist())
        else:
            row["ces_statuses"] = None
        # Cube_Inventory_Exact
        inv = q(f"SELECT COUNT(*) AS n, SUM(stock) AS sum_stock "
                f"FROM [salewarehouse].[dbo].[Cube_Inventory_Exact] WHERE itemcode = '{code}'")
        row["inv_n_rows"] = int(inv.iloc[0]["n"])
        row["inv_sum_stock"] = inv.iloc[0]["sum_stock"]
        if row["inv_n_rows"] > 0:
            inv_wh = q(f"SELECT DISTINCT warehouse FROM [salewarehouse].[dbo].[Cube_Inventory_Exact] WHERE itemcode = '{code}'")
            row["inv_warehouses"] = "|".join(inv_wh["warehouse"].dropna().astype(str).tolist())
        else:
            row["inv_warehouses"] = None
        # Cube_Quotation
        quo = q(f"SELECT COUNT(*) AS n, MIN(create_date) AS min_date, MAX(create_date) AS max_date "
                f"FROM [salewarehouse].[dbo].[Cube_Quotation] WHERE itemcode = '{code}'")
        row["quo_n_rows"] = int(quo.iloc[0]["n"])
        row["quo_min_date"] = quo.iloc[0]["min_date"]
        row["quo_max_date"] = quo.iloc[0]["max_date"]
        if row["quo_n_rows"] > 0:
            quo_st = q(f"SELECT DISTINCT quotation_status FROM [salewarehouse].[dbo].[Cube_Quotation] WHERE itemcode = '{code}'")
            row["quo_statuses"] = "|".join(quo_st["quotation_status"].dropna().astype(str).tolist())
        else:
            row["quo_statuses"] = None
        row["any_trace_anywhere"] = row["in_cube_Sale_APD"] or row["ces_n_rows"] > 0 or row["inv_n_rows"] > 0 or row["quo_n_rows"] > 0
        per_item_rows.append(row)

    per_item = pd.DataFrame(per_item_rows)
    save(per_item, "check6_per_item_history_trace.csv")
    print(per_item.to_string())

    # ============================================================
    # CHECK 7 — cross-check against Cube_CES (row-level, same definition as
    # STATUS.md's Phase 1.5 99.79% figure: match on (contractid, itemcode,
    # createDate/CtrDate, mapped status, qty). MPS<->Backlog mapping, Actual<->Actual.
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 7: cross-check against Cube_CES")
    ces_scope = q(f"""
    SELECT ContractID, ItemCode, CtrDate, Status, ActualQty, BacklogQty, PlanQty, ManuDivision, RevenueType
    FROM [salewarehouse].[dbo].[Cube_CES]
    WHERE ItemCode IN ({code_sql}) AND ManuDivision = 'PEM104' AND RevenueType = 'Omni Channel'
    """)
    save(ces_scope, "check7_ces_scope_raw.csv")
    logger.info("Cube_CES rows for PEM104/Omni Channel scope, these 12 itemcodes: %d", len(ces_scope))
    print(ces_scope.to_string())

    # Map cube_Sale_APD status -> Cube_CES status: Actual->Actual, MPS->Backlog
    sale_scope = scope.copy()
    sale_scope["mapped_ces_status"] = sale_scope["status"].map({"Actual": "Actual", "MPS": "Backlog"})
    sale_scope["createDate"] = pd.to_datetime(sale_scope["createDate"]).dt.date

    ces_scope2 = ces_scope.copy()
    ces_scope2["CtrDate"] = pd.to_datetime(ces_scope2["CtrDate"]).dt.date

    match_key_sale = ["contractid", "itemcode", "createDate", "mapped_ces_status"]
    match_key_ces = ["ContractID", "ItemCode", "CtrDate", "Status"]

    sale_keyed = sale_scope.set_index(match_key_sale)
    ces_keyed = ces_scope2.rename(columns=dict(zip(match_key_ces, match_key_sale)))

    matches = []
    for _, r in sale_scope.iterrows():
        cand = ces_scope2[
            (ces_scope2["ContractID"] == r["contractid"]) &
            (ces_scope2["ItemCode"] == r["itemcode"]) &
            (ces_scope2["CtrDate"] == r["createDate"]) &
            (ces_scope2["Status"] == r["mapped_ces_status"])
        ]
        row_match = len(cand) > 0
        qty_match = False
        if row_match:
            ces_qty = cand.iloc[0]["ActualQty"] if r["mapped_ces_status"] == "Actual" else cand.iloc[0]["BacklogQty"]
            qty_match = (float(ces_qty) == float(r["qty"]))
        matches.append({
            "contractid": r["contractid"], "itemcode": r["itemcode"], "createDate": r["createDate"],
            "status": r["status"], "qty": r["qty"], "sale": r["sale"],
            "ces_row_found": row_match, "ces_qty_match": qty_match,
            "ces_candidates_n": len(cand),
        })
    recon = pd.DataFrame(matches)
    save(recon, "check7_row_level_reconciliation.csv")
    print(recon.to_string())
    n = len(recon)
    n_found = recon["ces_row_found"].sum()
    n_qty_match = recon["ces_qty_match"].sum()
    logger.info("Row-level match rate (row exists in Cube_CES with same contractid/itemcode/date/mapped-status): %d/%d = %.2f%%", n_found, n, 100*n_found/n if n else 0)
    logger.info("Of those, exact qty match: %d/%d = %.2f%%", n_qty_match, n_found, 100*n_qty_match/n_found if n_found else 0)

    # Status distribution in Cube_CES scope, for context
    ces_status_counts = ces_scope["Status"].value_counts().reset_index()
    ces_status_counts.columns = ["Status", "n_rows"]
    save(ces_status_counts, "check7_ces_status_distribution.csv")
    print(ces_status_counts.to_string())

    # ============================================================
    # CHECK 8 — demand profile: monthly qty series per item, ADI/CV2 classification
    # ============================================================
    logger.info("=" * 70)
    logger.info("CHECK 8: demand profile")
    ADI_THRESHOLD = 1.32
    CV2_THRESHOLD = 0.49

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

    # Determine usable-from date and last complete month using this pull's own max date
    # (same convention as src/aggregate_levels.py determine_complete_months)
    max_date = scope["createDate"].max()  # already datetime
    month_end = max_date + pd.offsets.MonthEnd(0)
    latest_month = max_date.to_period("M")
    usable_from = scope["createDate"].min().to_period("M")
    logger.info("Usable-from month (first month with any PEM104/Omni Channel row): %s", usable_from)
    logger.info("Latest month in pull: %s (data ends %s, month ends %s) -> %s",
                latest_month, max_date.date(), month_end.date(),
                "PARTIAL, excluded" if max_date < month_end else "complete, kept")

    all_months = pd.period_range(usable_from, latest_month, freq="M")
    if max_date < month_end:
        all_months = all_months[all_months != latest_month]
    logger.info("Full monthly grid used for demand profile: %s to %s (%d periods)",
                all_months.min(), all_months.max(), len(all_months))

    scope["ym"] = scope["createDate"].dt.to_period("M")
    demand_rows = []
    class_rows = []
    for item in codes:
        item_rows = scope[scope["itemcode"] == item]
        monthly_qty = item_rows.groupby("ym")["qty"].sum()
        series = pd.Series(0.0, index=all_months)
        series.update(monthly_qty)
        for ym, val in series.items():
            demand_rows.append({"itemcode": item, "year_month": str(ym), "qty": val})
        cls, adi, cv2 = classify_demand(series.to_numpy())
        n_nonzero = int((series > 0).sum())
        class_rows.append({
            "itemcode": item, "n_periods": len(series), "n_nonzero_periods": n_nonzero,
            "pct_zero_periods": round(100 * (len(series) - n_nonzero) / len(series), 1),
            "ADI": round(adi, 3) if adi is not None else None,
            "CV2": round(cv2, 3) if cv2 is not None else None,
            "classification": cls, "total_qty": float(series.sum()),
        })

    demand_long = pd.DataFrame(demand_rows)
    save(demand_long, "check8_monthly_qty_per_item.csv")
    class_df = pd.DataFrame(class_rows)
    save(class_df, "check8_demand_classification.csv")
    print(class_df.to_string())

    n_any_sales = (class_df["classification"] != "NoSale").sum()
    total_value_thb = float(scope["sale"].sum())
    pct_zero_item_months = class_df["pct_zero_periods"].mean()
    print(f"\nItems with any sales: {n_any_sales} of {len(codes)}")
    print(f"Total value (THB), Check-1-filter scope: {total_value_thb}")
    class_counts = class_df["classification"].value_counts()
    print("Classification distribution:\n", class_counts.to_string())
    with_sales = class_df[class_df["classification"] != "NoSale"]
    if len(with_sales) > 0:
        print(f"Mean ADI (excl. NoSale): {with_sales['ADI'].mean():.3f}")
        print(f"Mean CV2 (excl. NoSale): {with_sales['CV2'].mean():.3f}")

    logger.info("ALL CHECKS COMPLETE")

