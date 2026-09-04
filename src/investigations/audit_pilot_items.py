"""Data quality audit for the 68 pilot items (High Voltage Distribution Fuse
Cutout + Medium Voltage Surge Arrester, from visible pricelist sheets).

Investigation and documentation only. Does not build a forecasting model,
does not run a backtest, and does not apply any cleaning rule.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("audit_pilot_items")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PRICELIST_PATH = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")

DIVISION = "PEM101"
REVENUE_TYPE = "Omni Channel"
CUTOFF_START = "2024-01-01"
PILOT_TYPES = ["High Voltage Distribution Fuse Cutout", "Medium Voltage Surge Arrester"]


def get_pilot_items():
    df = load_visible_product_rows(PRICELIST_PATH)
    pilot = df[df["type"].isin(PILOT_TYPES)].drop_duplicates("code")
    logger.info("Pilot items from visible pricelist sheets: %d", len(pilot))
    for t in PILOT_TYPES:
        n = (pilot["type"] == t).sum()
        logger.info("  Type %r: %d items", t, n)
    return pilot


def sql_in_list(values):
    return "','".join(sorted(str(v) for v in values))


def task2_checks(pilot_codes):
    logger.info("=== TASK 2: duplicate and anomaly checks ===")
    code_list = sql_in_list(pilot_codes)

    # Pull ALL rows for these 68 items, regardless of division/revenue_type,
    # so cross-division and anomaly checks are not pre-filtered away.
    raw = run_query(
        "SELECT itemcode, division, revenue_type, status, createDate, qty, sale, "
        "contractid, quotationid, jobcode, ContractPO_NO, planid "
        f"FROM cube_Sale_APD WHERE itemcode IN ('{code_list}')"
    )
    raw.to_csv(os.path.join(DATA_DIR, "raw_pilot_items_all_divisions.csv"), index=False)
    logger.info("Rows pulled for 68 pilot items (all divisions, all revenue types): %d", len(raw))

    # --- 2.1 cross-division exposure ---
    by_div = raw.groupby(["itemcode", "division"], as_index=False).agg(
        rows=("sale", "size"), sale_value=("sale", "sum")
    )
    multi_div_codes = by_div.groupby("itemcode")["division"].nunique()
    multi_div_codes = multi_div_codes[multi_div_codes > 1].index.tolist()
    cross_division = by_div[by_div["itemcode"].isin(multi_div_codes)].sort_values(["itemcode", "sale_value"], ascending=[True, False])
    cross_division.to_csv(os.path.join(SUMMARY_DIR, "task2_1_cross_division.csv"), index=False)
    total_value_all_div = raw["sale"].sum()
    total_value_pem101 = raw.loc[raw["division"] == DIVISION, "sale"].sum()
    excluded_value = total_value_all_div - total_value_pem101
    logger.info("2.1: %d of %d pilot codes appear under more than one division", len(multi_div_codes), len(pilot_codes))
    logger.info("2.1: total sale value all-divisions=%.2f, PEM101-only=%.2f, excluded by PEM101 filter=%.2f",
                total_value_all_div, total_value_pem101, excluded_value)

    # --- 2.2 exact duplicate rows ---
    dup_mask = raw.duplicated(subset=["itemcode", "createDate", "qty", "sale", "status"], keep=False)
    dup_rows = raw[dup_mask].sort_values(["itemcode", "createDate"])
    dup_rows.to_csv(os.path.join(SUMMARY_DIR, "task2_2_exact_duplicates.csv"), index=False)
    n_dup_rows = len(dup_rows)
    dup_value = dup_rows["sale"].sum()
    logger.info("2.2: %d rows participate in an exact duplicate group (itemcode+createDate+qty+sale+status), total value=%.2f",
                n_dup_rows, dup_value)

    # --- 2.3 negative values ---
    neg_qty = raw[raw["qty"] < 0]
    neg_sale = raw[raw["sale"] < 0]
    neg_qty.to_csv(os.path.join(SUMMARY_DIR, "task2_3_negative_qty.csv"), index=False)
    neg_sale.to_csv(os.path.join(SUMMARY_DIR, "task2_3_negative_sale.csv"), index=False)
    logger.info("2.3: negative qty rows=%d (total qty=%.2f), negative sale rows=%d (total sale=%.2f)",
                len(neg_qty), neg_qty["qty"].sum(), len(neg_sale), neg_sale["sale"].sum())

    # --- 2.4 Actual/MPS double-counting investigation ---
    # Tests overlap at the (document_id, itemcode) grain, which is the precise
    # question: does the SAME item under the SAME order appear as both Actual
    # and MPS? A same-document match across DIFFERENT items (e.g. one line
    # shipped, another line still pending on the same PO) is normal multi-line
    # PO behaviour, not a double-counting risk for any single item.
    #
    # NULL exclusion cannot rely on SQL's IS NOT NULL alone: the database
    # stores the literal 4-character string "None" as a placeholder for a
    # missing quotationid on many rows (confirmed via LEN()/ASCII() against
    # the raw column) instead of a true SQL NULL, so it must also be excluded
    # explicitly, or it is misread as one fake "document id" spanning nearly
    # every item and status.
    doc_cols = ["contractid", "quotationid", "jobcode", "ContractPO_NO", "planid"]
    doc_findings = {}
    for col in doc_cols:
        col_sql = run_query(
            f"SELECT itemcode, division, revenue_type, status, createDate, qty, sale, {col} "
            f"FROM cube_Sale_APD WHERE itemcode IN ('{code_list}') AND {col} IS NOT NULL"
        )
        clean = col_sql[
            (col_sql[col].astype(str).str.strip() != "") & (col_sql[col].astype(str) != "None")
        ]
        if clean.empty:
            doc_findings[col] = {"clean_non_null_rows": 0, "doc_item_pairs_with_both_status": 0}
            continue
        grp = clean.groupby([col, "itemcode"])["status"].nunique()
        both = grp[grp > 1]
        doc_findings[col] = {"clean_non_null_rows": len(clean), "doc_item_pairs_with_both_status": len(both)}
        if len(both) > 0:
            pairs = both.index.tolist()
            detail_frames = [clean[(clean[col] == doc_id) & (clean["itemcode"] == item)] for doc_id, item in pairs]
            detail = pd.concat(detail_frames).sort_values([col, "itemcode", "status"])
            detail.to_csv(os.path.join(SUMMARY_DIR, f"task2_4_doc_item_both_status_{col}.csv"), index=False)
    logger.info("2.4: document-identifier investigation (document+item grain): %s", doc_findings)

    # --- 2.5 missing values, out-of-range dates, qty/sale mismatch ---
    key_cols = ["itemcode", "createDate", "qty", "sale", "status", "division", "revenue_type"]
    missing = raw[raw[key_cols].isna().any(axis=1)]
    missing.to_csv(os.path.join(SUMMARY_DIR, "task2_5_missing_key_values.csv"), index=False)

    raw["createDate_dt"] = pd.to_datetime(raw["createDate"])
    today = pd.Timestamp.now().normalize()
    out_of_range = raw[(raw["createDate_dt"] < pd.Timestamp(CUTOFF_START)) | (raw["createDate_dt"] > today)]
    out_of_range.to_csv(os.path.join(SUMMARY_DIR, "task2_5_dates_out_of_range.csv"), index=False)

    qty_zero_sale_nonzero = raw[(raw["qty"] == 0) & (raw["sale"] != 0)]
    sale_zero_qty_nonzero = raw[(raw["sale"] == 0) & (raw["qty"] != 0)]
    qty_zero_sale_nonzero.to_csv(os.path.join(SUMMARY_DIR, "task2_5_qty_zero_sale_nonzero.csv"), index=False)
    sale_zero_qty_nonzero.to_csv(os.path.join(SUMMARY_DIR, "task2_5_sale_zero_qty_nonzero.csv"), index=False)

    logger.info("2.5: missing key values=%d rows, dates out of [%s, %s]=%d rows, qty=0&sale!=0=%d rows, sale=0&qty!=0=%d rows",
                len(missing), CUTOFF_START, today.date(), len(out_of_range), len(qty_zero_sale_nonzero), len(sale_zero_qty_nonzero))

    return {
        "raw": raw,
        "cross_division": cross_division,
        "multi_div_codes": multi_div_codes,
        "total_value_all_div": total_value_all_div,
        "total_value_pem101": total_value_pem101,
        "excluded_value": excluded_value,
        "n_dup_rows": n_dup_rows,
        "dup_value": dup_value,
        "neg_qty": neg_qty,
        "neg_sale": neg_sale,
        "doc_findings": doc_findings,
        "missing": missing,
        "out_of_range": out_of_range,
        "qty_zero_sale_nonzero": qty_zero_sale_nonzero,
        "sale_zero_qty_nonzero": sale_zero_qty_nonzero,
    }


def task3_cross_channel(pilot_codes):
    logger.info("=== TASK 3: cross-channel exposure ===")
    code_list = sql_in_list(pilot_codes)

    # 3.1 table-wide revenue_type distribution (no item filter, for context)
    all_rev = run_query(
        "SELECT revenue_type, COUNT(*) AS rows, SUM(sale) AS total_sale FROM cube_Sale_APD GROUP BY revenue_type ORDER BY total_sale DESC"
    )
    all_rev.to_csv(os.path.join(SUMMARY_DIR, "task3_1_all_revenue_types.csv"), index=False)
    logger.info("3.1: %d distinct revenue_type values table-wide", len(all_rev))

    # 3.2 pilot items under PEM101, per revenue_type
    pem101 = run_query(
        "SELECT itemcode, revenue_type, qty, sale FROM cube_Sale_APD "
        f"WHERE itemcode IN ('{code_list}') AND division = '{DIVISION}'"
    )
    pem101.to_csv(os.path.join(DATA_DIR, "raw_pilot_items_pem101.csv"), index=False)

    by_rev = pem101.groupby("revenue_type", as_index=False).agg(
        n_items=("itemcode", "nunique"), total_qty=("qty", "sum"), total_sale=("sale", "sum")
    ).sort_values("total_sale", ascending=False)
    by_rev.to_csv(os.path.join(SUMMARY_DIR, "task3_2_pilot_by_revenue_type.csv"), index=False)
    logger.info("3.2: pilot items span %d revenue_type values under division=%s", len(by_rev), DIVISION)

    # 3.3 per-item Omni Channel share of total (across all revenue types), under PEM101
    per_item_total = pem101.groupby("itemcode", as_index=False)["sale"].sum().rename(columns={"sale": "total_sale_all_channels"})
    per_item_omni = pem101[pem101["revenue_type"] == REVENUE_TYPE].groupby("itemcode", as_index=False)["sale"].sum().rename(columns={"sale": "omni_sale"})
    share = per_item_total.merge(per_item_omni, on="itemcode", how="left")
    share["omni_sale"] = share["omni_sale"].fillna(0.0)
    share["omni_share_pct"] = share.apply(
        lambda r: (r["omni_sale"] / r["total_sale_all_channels"] * 100) if r["total_sale_all_channels"] not in (0, None) else None,
        axis=1,
    )
    # include pilot codes with zero rows under PEM101 at all
    missing_codes = set(pilot_codes) - set(share["itemcode"])
    if missing_codes:
        extra = pd.DataFrame({"itemcode": sorted(missing_codes), "total_sale_all_channels": 0.0, "omni_sale": 0.0, "omni_share_pct": None})
        share = pd.concat([share, extra], ignore_index=True)
    share = share.sort_values("omni_share_pct", na_position="first")
    share.to_csv(os.path.join(SUMMARY_DIR, "task3_3_omni_share_per_item.csv"), index=False)

    # 3.4 flag items below 50%
    flagged = share[(share["omni_share_pct"].notna()) & (share["omni_share_pct"] < 50)]
    flagged.to_csv(os.path.join(SUMMARY_DIR, "task3_4_flagged_below_50pct.csv"), index=False)
    logger.info("3.4: %d items have Omni Channel share below 50%%", len(flagged))

    return {"all_rev": all_rev, "by_rev": by_rev, "share": share, "flagged": flagged}


def task4_pricelist_consistency(pilot_df):
    logger.info("=== TASK 4: consistency against the pricelist ===")
    codes = pilot_df["code"].tolist()
    code_list = sql_in_list(codes)

    db_rows = run_query(
        "SELECT DISTINCT itemcode, productTypeName, productCateName FROM cube_Sale_APD "
        f"WHERE itemcode IN ('{code_list}')"
    )
    codes_in_db = set(db_rows["itemcode"].unique())
    codes_not_in_db = sorted(set(codes) - codes_in_db)
    logger.info("4.1: %d of %d pilot items exist in the database at all; %d do not appear at all",
                len(codes_in_db), len(codes), len(codes_not_in_db))

    sales_present = run_query(
        f"SELECT DISTINCT itemcode FROM cube_Sale_APD WHERE itemcode IN ('{code_list}') AND sale IS NOT NULL"
    )
    codes_with_sales = set(sales_present["itemcode"].unique())
    codes_no_sales = sorted(set(codes) - codes_with_sales)
    logger.info("4.1: %d of %d pilot items have at least one sales row", len(codes_with_sales), len(codes))

    # 4.2 / 4.3: compare pricelist Type/Category vs DB productTypeName/productCateName
    db_by_code = db_rows.groupby("itemcode").agg(
        db_types=("productTypeName", lambda s: sorted(set(s.dropna()))),
        db_cates=("productCateName", lambda s: sorted(set(s.dropna()))),
    ).reset_index()

    merged = pilot_df[["code", "type", "category"]].merge(db_by_code, left_on="code", right_on="itemcode", how="left")

    def type_mismatch(row):
        if not isinstance(row["db_types"], list) or len(row["db_types"]) == 0:
            return True
        return row["type"] not in row["db_types"]

    def cate_mismatch(row):
        if not isinstance(row["db_cates"], list) or len(row["db_cates"]) == 0:
            return True
        return row["category"] not in row["db_cates"]

    merged["type_mismatch"] = merged.apply(type_mismatch, axis=1)
    merged["cate_mismatch"] = merged.apply(cate_mismatch, axis=1)
    merged.to_csv(os.path.join(SUMMARY_DIR, "task4_pricelist_vs_db_consistency.csv"), index=False)

    type_mismatches = merged[merged["type_mismatch"]]
    cate_mismatches = merged[merged["cate_mismatch"]]
    logger.info("4.2: %d items have Product Type mismatch (pricelist vs productTypeName, or absent from DB)", len(type_mismatches))
    logger.info("4.3: %d items have Product Cate. mismatch (pricelist vs productCateName, or absent from DB)", len(cate_mismatches))

    return {
        "codes_not_in_db": codes_not_in_db,
        "codes_no_sales": codes_no_sales,
        "merged": merged,
        "type_mismatches": type_mismatches,
        "cate_mismatches": cate_mismatches,
    }


if __name__ == "__main__":
    pilot_df = get_pilot_items()
    pilot_codes = pilot_df["code"].tolist()

    t2 = task2_checks(pilot_codes)
    t3 = task3_cross_channel(pilot_codes)
    t4 = task4_pricelist_consistency(pilot_df)

    print("\n" + "=" * 70)
    print("AUDIT SUMMARY")
    print("=" * 70)
    print(f"Pilot items: {len(pilot_codes)}")
    print(f"\n[2.1] Cross-division codes: {len(t2['multi_div_codes'])} -> {t2['multi_div_codes']}")
    print(f"      Total value all-divisions: {t2['total_value_all_div']:.2f}, PEM101-only: {t2['total_value_pem101']:.2f}, excluded: {t2['excluded_value']:.2f}")
    print(f"[2.2] Exact duplicate rows: {t2['n_dup_rows']}, total value: {t2['dup_value']:.2f}")
    print(f"[2.3] Negative qty rows: {len(t2['neg_qty'])} (sum={t2['neg_qty']['qty'].sum():.2f}), negative sale rows: {len(t2['neg_sale'])} (sum={t2['neg_sale']['sale'].sum():.2f})")
    print(f"[2.4] Document-id double-count investigation: {t2['doc_findings']}")
    print(f"[2.5] Missing key values: {len(t2['missing'])}, out-of-range dates: {len(t2['out_of_range'])}, qty=0&sale!=0: {len(t2['qty_zero_sale_nonzero'])}, sale=0&qty!=0: {len(t2['sale_zero_qty_nonzero'])}")
    print(f"\n[3.1] Distinct revenue_type values table-wide: {len(t3['all_rev'])}")
    print(t3['all_rev'].to_string(index=False))
    print(f"\n[3.2] Pilot items (PEM101) by revenue_type:")
    print(t3['by_rev'].to_string(index=False))
    print(f"\n[3.4] Items flagged below 50% Omni share: {len(t3['flagged'])}")
    print(t3['flagged'].to_string(index=False))
    print(f"\n[4.1] Pilot items not in DB at all: {len(t4['codes_not_in_db'])} -> {t4['codes_not_in_db']}")
    print(f"      Pilot items with no sales rows: {len(t4['codes_no_sales'])} -> {t4['codes_no_sales']}")
    print(f"[4.2] Product Type mismatches: {len(t4['type_mismatches'])}")
    print(f"[4.3] Product Cate. mismatches: {len(t4['cate_mismatches'])}")
