"""Loads and validates sales data for the pilot forecasting scope.

Filters by itemcode rather than productTypeName, because the pricelist and
the database disagree on the Surge Arrester voltage tier (see STATUS.md,
2026-08-31) — item codes are unambiguous, product type names are not.

MPS rows represent confirmed demand ("PO Received") and must never be
dropped or filtered out anywhere in this pipeline (locked decision,
2026-08-31).
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
logger = logging.getLogger("load_data")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def load_config() -> dict:
    """Read config.yaml. No parameter used by this module is hardcoded."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_pilot_scope(config: dict) -> tuple[list, list]:
    """Return (forecastable_codes, excluded_codes) for the pilot scope.

    The pricelist's Product Type column (config: pilot_categories) identifies
    the 68 pilot items. Codes with zero rows anywhere in the source table are
    excluded from forecasting and returned separately for Phase 4 record-keeping.
    """
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pilot_df = load_visible_product_rows(pricelist_path)
    type_values = list(config["pilot_categories"].values())
    scope_df = pilot_df[pilot_df["type"].isin(type_values)]
    all_codes = sorted(scope_df["code"].unique())
    logger.info("Pilot scope from pricelist (Type-level filter, not DB productTypeName): %d item codes", len(all_codes))

    code_list = "','".join(all_codes)
    source_table = config["source_table"]
    present = run_query(f"SELECT DISTINCT itemcode FROM {source_table} WHERE itemcode IN ('{code_list}')")
    present_codes = set(present["itemcode"])
    forecastable = sorted(present_codes)
    excluded = sorted(set(all_codes) - present_codes)
    logger.info("%d of %d pilot codes have at least one row in %s; %d excluded (no sales history at all)",
                len(forecastable), len(all_codes), source_table, len(excluded))
    return forecastable, excluded


def pull_raw_sales(config: dict, item_codes: list) -> pd.DataFrame:
    """Pull raw daily sales rows for the given item codes, unaggregated and unfiltered
    beyond the config-specified division / revenue_type / status / date scope."""
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
    """Validate raw pulled data. Raises loudly on any violation — never silently drops a row."""
    n_rows = len(df)

    neg_qty = df[df["qty"] < 0]
    if len(neg_qty) > 0:
        raise ValueError(
            f"Found {len(neg_qty)} rows with negative qty — data must be reviewed, not silently "
            f"dropped. Sample: {neg_qty[['itemcode', 'createDate', 'qty']].head(5).to_dict('records')}"
        )

    neg_sale = df[df["sale"] < 0]
    if len(neg_sale) > 0:
        raise ValueError(
            f"Found {len(neg_sale)} rows with negative sale — data must be reviewed, not silently "
            f"dropped. Sample: {neg_sale[['itemcode', 'createDate', 'sale']].head(5).to_dict('records')}"
        )

    df = df.copy()
    df["createDate"] = pd.to_datetime(df["createDate"])
    today = pd.Timestamp.now().normalize()
    out_of_range = df[(df["createDate"] < pd.Timestamp(start_date)) | (df["createDate"] > today)]
    if len(out_of_range) > 0:
        raise ValueError(
            f"Found {len(out_of_range)} rows with createDate outside [{start_date}, {today.date()}] — "
            f"data must be reviewed, not silently dropped."
        )

    pulled_items = set(df["itemcode"].unique())
    expected_items = set(item_codes)
    missing_entirely = expected_items - pulled_items
    if missing_entirely:
        logger.warning(
            "%d of %d pilot items have ZERO rows under this division/revenue_type/status/date "
            "scope (though they have some history elsewhere in the table): %s",
            len(missing_entirely), len(expected_items), sorted(missing_entirely),
        )

    logger.info(
        "Validation passed: %d rows, %d distinct items (of %d expected), no negative values, "
        "no out-of-range dates, 0 rows dropped",
        n_rows, len(pulled_items), len(expected_items),
    )
    return df


def aggregate_monthly(df: pd.DataFrame, item_codes: list) -> pd.DataFrame:
    """Aggregate raw daily rows to one row per (item, month). Every item gets a
    complete, gap-free monthly series — months with no sales are filled with zero,
    not omitted, since a missing month and a zero-sales month mean different things
    to a forecasting model but must both be representable here as zero.
    """
    df = df.copy()
    df["year_month"] = df["createDate"].dt.to_period("M")

    monthly = df.groupby(["itemcode", "year_month"], as_index=False).agg(
        qty=("qty", "sum"), sale=("sale", "sum")
    )

    raw_qty_total = df["qty"].sum()
    raw_sale_total = df["sale"].sum()
    agg_qty_total = monthly["qty"].sum()
    agg_sale_total = monthly["sale"].sum()
    if abs(raw_qty_total - agg_qty_total) > 1e-6 or abs(raw_sale_total - agg_sale_total) > 1e-6:
        raise ValueError(
            f"Monthly aggregation does not reconcile to the daily source: "
            f"raw qty={raw_qty_total} vs aggregated qty={agg_qty_total}, "
            f"raw sale={raw_sale_total} vs aggregated sale={agg_sale_total}"
        )
    logger.info(
        "Reconciliation OK: monthly totals match the daily source exactly (qty=%.2f, sale=%.2f)",
        agg_qty_total, agg_sale_total,
    )

    n_items_before = df["itemcode"].nunique()
    n_items_with_any_sales = monthly["itemcode"].nunique()
    logger.info(
        "Item counts: %d items had at least one row before aggregation, %d after grouping "
        "(both must be <= %d, the full pilot scope)",
        n_items_before, n_items_with_any_sales, len(item_codes),
    )
    if n_items_before != n_items_with_any_sales:
        raise ValueError(
            f"Item count changed during aggregation: {n_items_before} before, "
            f"{n_items_with_any_sales} after — rows were lost or gained unexpectedly."
        )

    min_month = df["year_month"].min()
    max_month = df["year_month"].max()
    all_months = pd.period_range(min_month, max_month, freq="M")
    full_index = pd.MultiIndex.from_product([item_codes, all_months], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()

    n_items_final = full["itemcode"].nunique()
    if n_items_final != len(item_codes):
        raise ValueError(f"Final monthly grid has {n_items_final} items, expected {len(item_codes)}")

    logger.info(
        "Monthly grid built: %d items x %d months (%s to %s) = %d rows",
        len(item_codes), len(all_months), min_month, max_month, len(full),
    )
    return full


if __name__ == "__main__":
    config = load_config()

    forecastable_codes, excluded_codes = get_pilot_scope(config)
    pd.DataFrame({"itemcode": excluded_codes}).to_csv(
        os.path.join(SUMMARY_DIR, "excluded_items_no_history.csv"), index=False
    )
    logger.info(
        "Wrote %d excluded item codes (no sales history) for Phase 4 inventory planning "
        "to output/summary/excluded_items_no_history.csv",
        len(excluded_codes),
    )

    raw = pull_raw_sales(config, forecastable_codes)
    raw = validate_raw(raw, forecastable_codes, config["date_range"]["start"])

    raw.to_csv(os.path.join(DATA_DIR, "raw_pilot_sales_58items.csv"), index=False)
    logger.info("Saved raw pull, unmodified: output/data/raw_pilot_sales_58items.csv")

    monthly = aggregate_monthly(raw, forecastable_codes)
    monthly.to_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly.csv"), index=False)
    logger.info("Saved processed monthly aggregate: output/data/processed_pilot_sales_monthly.csv")
