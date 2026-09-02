"""Loads and validates sales data for the FULL Fuse + Surge Arrester category
scope (Part 1 of the Category/Type-level expansion task, 2026-08-31).

Extends src/load_data.py's 58/68-item Type-level pilot to every item code
where the pricelist's Product Cate. column is "Fuse" or "Surge Arrester" —
128 codes across 8 Types. This does NOT replace the Type-level pilot scope
(STATUS.md locked decision, 2026-08-31, kept for its original reason: mixing
dissimilar products into one item-level model fits none of them well). This
script instead feeds top-down aggregation (Category/Type/Item levels), which
is a different use of the wider scope — see STATUS.md.

Does not modify config/config.yaml. Reuses division, revenue_type,
status_basis, date_range and source_table from it (those are not pilot-scope
specific), but the Category-level item list itself is computed here, not
read from a config key, consistent with this project's practice of not
writing scope choices into config.yaml unless explicitly instructed.
"""
import logging
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("load_data_full")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

CATEGORIES = ["Fuse", "Surge Arrester"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_category_scope(config: dict) -> pd.DataFrame:
    """Returns a DataFrame (code, category, type) for every visible pricelist
    row whose category is Fuse or Surge Arrester, plus a has_sales flag."""
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pilot_df = load_visible_product_rows(pricelist_path)
    scope_df = pilot_df[pilot_df["category"].isin(CATEGORIES)][["code", "category", "type"]].drop_duplicates()
    all_codes = sorted(scope_df["code"].unique())
    logger.info("Category-level scope from pricelist (Product Cate. in %s): %d item codes across %d types",
                CATEGORIES, len(all_codes), scope_df["type"].nunique())

    code_list = "','".join(all_codes)
    source_table = config["source_table"]
    present = run_query(f"SELECT DISTINCT itemcode FROM {source_table} WHERE itemcode IN ('{code_list}')")
    present_codes = set(present["itemcode"])
    scope_df = scope_df.copy()
    scope_df["has_any_history"] = scope_df["code"].isin(present_codes)
    return scope_df


def pull_raw_sales(config: dict, item_codes: list) -> pd.DataFrame:
    source_table = config["source_table"]
    division = config["division"]
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    start_date = config["date_range"]["start"]

    code_list = "','".join(item_codes)
    status_list = "','".join(statuses)
    sql = f"""
        SELECT itemcode, createDate, qty, sale, status, division, revenue_type
        FROM {source_table}
        WHERE itemcode IN ('{code_list}')
          AND division = '{division}'
          AND revenue_type = '{revenue_type}'
          AND status IN ('{status_list}')
          AND createDate >= '{start_date}'
    """
    df = run_query(sql)
    logger.info(
        "Pulled %d raw rows: %d items, division=%s, revenue_type=%s, status in %s, createDate >= %s",
        len(df), len(item_codes), division, revenue_type, statuses, start_date,
    )
    n_mps = (df["status"] == "MPS").sum()
    logger.info("Of these, %d rows are MPS (confirmed demand — kept, never dropped)", n_mps)
    return df


def validate_raw(df: pd.DataFrame, item_codes: list, start_date: str) -> pd.DataFrame:
    n_rows = len(df)

    neg_qty = df[df["qty"] < 0]
    if len(neg_qty) > 0:
        raise ValueError(f"Found {len(neg_qty)} rows with negative qty — data must be reviewed, not silently dropped. "
                          f"Sample: {neg_qty[['itemcode', 'createDate', 'qty']].head(5).to_dict('records')}")

    neg_sale = df[df["sale"] < 0]
    if len(neg_sale) > 0:
        raise ValueError(f"Found {len(neg_sale)} rows with negative sale — data must be reviewed, not silently dropped. "
                          f"Sample: {neg_sale[['itemcode', 'createDate', 'sale']].head(5).to_dict('records')}")

    df = df.copy()
    df["createDate"] = pd.to_datetime(df["createDate"])
    today = pd.Timestamp.now().normalize()
    out_of_range = df[(df["createDate"] < pd.Timestamp(start_date)) | (df["createDate"] > today)]
    if len(out_of_range) > 0:
        raise ValueError(f"Found {len(out_of_range)} rows with createDate outside [{start_date}, {today.date()}] — "
                          f"data must be reviewed, not silently dropped.")

    pulled_items = set(df["itemcode"].unique())
    expected_items = set(item_codes)
    missing_entirely = expected_items - pulled_items
    if missing_entirely:
        logger.warning("%d of %d category-scope items have ZERO rows under this division/revenue_type/status/date scope: %s",
                        len(missing_entirely), len(expected_items), sorted(missing_entirely))

    logger.info("Validation passed: %d rows, %d distinct items (of %d expected), no negative values, no out-of-range dates, 0 rows dropped",
                n_rows, len(pulled_items), len(expected_items))
    return df


def aggregate_monthly(df: pd.DataFrame, item_codes: list) -> pd.DataFrame:
    df = df.copy()
    df["year_month"] = df["createDate"].dt.to_period("M")

    monthly = df.groupby(["itemcode", "year_month"], as_index=False).agg(qty=("qty", "sum"), sale=("sale", "sum"))

    raw_qty_total = df["qty"].sum()
    raw_sale_total = df["sale"].sum()
    agg_qty_total = monthly["qty"].sum()
    agg_sale_total = monthly["sale"].sum()
    if abs(raw_qty_total - agg_qty_total) > 1e-6 or abs(raw_sale_total - agg_sale_total) > 1e-6:
        raise ValueError(f"Monthly aggregation does not reconcile to the daily source: "
                          f"raw qty={raw_qty_total} vs aggregated qty={agg_qty_total}, "
                          f"raw sale={raw_sale_total} vs aggregated sale={agg_sale_total}")
    logger.info("Reconciliation OK: monthly totals match the daily source exactly (qty=%.2f, sale=%.2f)", agg_qty_total, agg_sale_total)

    n_items_before = df["itemcode"].nunique()
    n_items_with_any_sales = monthly["itemcode"].nunique()
    if n_items_before != n_items_with_any_sales:
        raise ValueError(f"Item count changed during aggregation: {n_items_before} before, {n_items_with_any_sales} after")

    min_month = df["year_month"].min()
    max_month = df["year_month"].max()
    all_months = pd.period_range(min_month, max_month, freq="M")
    full_index = pd.MultiIndex.from_product([item_codes, all_months], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()

    n_items_final = full["itemcode"].nunique()
    if n_items_final != len(item_codes):
        raise ValueError(f"Final monthly grid has {n_items_final} items, expected {len(item_codes)}")

    logger.info("Monthly grid built: %d items x %d months (%s to %s) = %d rows",
                len(item_codes), len(all_months), min_month, max_month, len(full))
    return full


if __name__ == "__main__":
    config = load_config()

    scope_df = get_category_scope(config)
    scope_df.to_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"), index=False)

    forecastable_codes = sorted(scope_df.loc[scope_df["has_any_history"], "code"].unique())
    excluded_codes = sorted(scope_df.loc[~scope_df["has_any_history"], "code"].unique())
    logger.info("%d of %d category-scope codes have at least one row in source table; %d excluded (no sales history at all)",
                len(forecastable_codes), len(scope_df), len(excluded_codes))

    raw = pull_raw_sales(config, forecastable_codes)
    raw = validate_raw(raw, forecastable_codes, config["date_range"]["start"])
    raw.to_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"), index=False)

    monthly = aggregate_monthly(raw, forecastable_codes)
    monthly = monthly.merge(scope_df[["code", "category", "type"]].rename(columns={"code": "itemcode"}), on="itemcode", how="left")
    monthly.to_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"), index=False)

    # Per-Type report: codes total, with/without sales-under-filter (i.e. rows present in `raw`), qty/value totals
    codes_with_sales_in_scope = set(raw["itemcode"].unique())
    per_type = []
    for (cat, typ), grp in scope_df.groupby(["category", "type"]):
        codes = set(grp["code"])
        n_total = len(codes)
        n_with_sales = len(codes & codes_with_sales_in_scope)
        n_no_sales = n_total - n_with_sales
        sub_raw = raw[raw["itemcode"].isin(codes)]
        per_type.append({
            "category": cat, "type": typ, "n_codes": n_total,
            "n_with_sales_2024plus": n_with_sales, "n_no_sales_2024plus": n_no_sales,
            "total_qty": sub_raw["qty"].sum(), "total_value": sub_raw["sale"].sum(),
        })
    per_type_df = pd.DataFrame(per_type).sort_values(["category", "type"])
    per_type_df.to_csv(os.path.join(SUMMARY_DIR, "part1_scope_report_by_type.csv"), index=False)

    print("\n" + "=" * 78)
    print("PART 1: CATEGORY-LEVEL SCOPE REPORT (Fuse + Surge Arrester, 2024-01-01 onward)")
    print("=" * 78)
    print(f"Total codes in scope: {len(scope_df)} across {scope_df['type'].nunique()} Types, "
          f"{scope_df['category'].nunique()} Categories")
    print(f"Codes with at least one row anywhere in source table: {len(forecastable_codes)}")
    print(f"Codes excluded (zero rows anywhere): {len(excluded_codes)} -> {excluded_codes}")
    print(f"\nRaw pull under filters (division=PEM101, revenue_type=Omni Channel, status Actual/MPS, >=2024-01-01): {len(raw)} rows")
    print(f"Codes among the {len(forecastable_codes)} forecastable that have ZERO rows under these specific filters: "
          f"{len(forecastable_codes) - len(codes_with_sales_in_scope)}")
    print("\nPer-Type breakdown:")
    print(per_type_df.to_string(index=False))
    print(f"\nTOTAL qty: {per_type_df['total_qty'].sum():,.0f}   TOTAL value: {per_type_df['total_value'].sum():,.2f}")
