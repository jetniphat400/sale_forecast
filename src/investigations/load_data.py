"""Loads and validates sales data for the pilot forecasting scope.

Filters by itemcode rather than productTypeName, because the pricelist and
the database disagree on the Surge Arrester voltage tier (see STATUS.md,
2026-08-31) — item codes are unambiguous, product type names are not.

MPS rows represent confirmed demand ("PO Received") and must never be
dropped or filtered out anywhere in this pipeline (locked decision,
2026-08-31).

DIVISION (2026-09-04 correction, STATUS.md Locked Decisions, "Division
source-of-truth correction"): this project originally called this file
`src/load_data.py`; it was relocated to `src/investigations/` in the
2026-09-04 reorg (git history: "Reorganize src/") and is no longer called by
`src/run_pipeline.py` (superseded by `load_data_full.py`'s 128-item Category
scope), but is fixed here too since STATUS.md and this project's prose still
refer to it by its original name. The pricelist is authoritative for an
item's division; the database's own `division` column is reference-only and
is NEVER used to filter which rows count as an item's sales — the query below
selects by itemcode + revenue_type only. Each row's division is attached from
config['sheet_to_division']; the database's own value is kept as a separate
`division_db_raw` column so discrepancies can still be inspected.

RE-KEYING (Phase B, task B1, 2026-09-02): Phase A found this pipeline was
keyed on createDate (PO receipt date), when inventory planning needs
forecast_date (contractual delivery date). This script now pulls both date
fields and writes monthly series keyed BOTH ways
(`processed_pilot_sales_monthly_createDate.csv` /
`..._forecastDate.csv`), plus the original unsuffixed filename as an exact
alias of the createDate-keyed series (kept working, not deleted, for any
script that still reads it). forecast_date is a FROZEN SNAPSHOT taken at
run time (a `snapshot_pull_date` column is written into the output), never
re-queried live — Phase A could not rule out revision after intake.
"""
import logging
import os
import sys
from datetime import datetime

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("load_data")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
FORECAST_DATE_ANOMALY_LOW = pd.Timestamp("1971-01-01")
FORECAST_DATE_ANOMALY_HIGH = pd.Timestamp("2030-01-01")


def load_config() -> dict:
    """Read config.yaml. No parameter used by this module is hardcoded."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_pilot_scope(config: dict) -> tuple[list, list, dict]:
    """Return (forecastable_codes, excluded_codes, division_by_code) for the pilot scope.

    The pricelist's Product Type column (config: pilot_categories) identifies
    the 68 pilot items. Codes with zero rows anywhere in the source table are
    excluded from forecasting and returned separately for Phase 4 record-keeping.
    `division_by_code` maps each code to its division via config['sheet_to_division']
    (pricelist sheet -> division), per the 2026-09-04 source-of-truth correction — every
    code in this Type-level pilot scope is on the PEM101 sheet, so this maps every code to
    'PEM101', but is derived explicitly rather than hardcoded.
    """
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pilot_df = load_visible_product_rows(pricelist_path)
    type_values = list(config["pilot_categories"].values())
    scope_df = pilot_df[pilot_df["type"].isin(type_values)]
    all_codes = sorted(scope_df["code"].unique())
    logger.info("Pilot scope from pricelist (Type-level filter, not DB productTypeName): %d item codes", len(all_codes))

    sheet_to_division = config["sheet_to_division"]
    unmapped_sheets = set(scope_df["sheet"]) - set(sheet_to_division)
    if unmapped_sheets:
        raise ValueError(f"Sheet(s) {unmapped_sheets} have no entry in config['sheet_to_division'].")
    division_by_code = dict(zip(scope_df["code"], scope_df["sheet"].map(sheet_to_division)))

    code_list = "','".join(all_codes)
    source_table = config["source_table"]
    present = run_query(f"SELECT DISTINCT itemcode FROM {source_table} WHERE itemcode IN ('{code_list}')")
    present_codes = set(present["itemcode"])
    forecastable = sorted(present_codes)
    excluded = sorted(set(all_codes) - present_codes)
    logger.info("%d of %d pilot codes have at least one row in %s; %d excluded (no sales history at all)",
                len(forecastable), len(all_codes), source_table, len(excluded))
    return forecastable, excluded, division_by_code


def pull_raw_sales(config: dict, item_codes: list, division_by_code: dict) -> pd.DataFrame:
    """Pull raw daily sales rows for the given item codes, filtered on itemcode + revenue_type +
    status + date only — NOT division (2026-09-04 correction: the database's `division` column
    is reference-only, never a filter — STATUS.md Locked Decisions, "Division source-of-truth
    correction"). Each row's division is attached from the pricelist (`division_by_code`); the
    database's own value is kept as a separate `division_db_raw` reference column."""
    source_table = config["source_table"]
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    start_date = config["date_range"]["start"]

    code_list = "','".join(item_codes)
    status_list = "','".join(statuses)
    sql = f"""
        SELECT itemcode, createDate, forecast_date, qty, sale, status, division AS division_db_raw, revenue_type
        FROM {source_table}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{revenue_type}'
          AND status IN ('{status_list}')
          AND createDate >= '{start_date}'
    """
    df = run_query(sql)
    logger.info(
        "Pulled %d raw rows: %d items, revenue_type=%s, status in %s, createDate >= %s "
        "(no division filter — division attached from the pricelist below)",
        len(df), len(item_codes), revenue_type, statuses, start_date,
    )
    df["division"] = df["itemcode"].map(division_by_code)
    unmapped = df[df["division"].isna()]
    if len(unmapped) > 0:
        raise ValueError(f"{len(unmapped)} rows have an itemcode with no pricelist division mapping. "
                          f"Sample itemcodes: {sorted(unmapped['itemcode'].unique())[:5]}")
    n_reference_mismatch = (df["division"] != df["division_db_raw"]).sum()
    logger.info(
        "%d of %d rows (%.2f%%) have a database division_db_raw that differs from the item's pricelist "
        "division — these rows are still counted (division filter removed), division_db_raw kept for "
        "inspection.", n_reference_mismatch, len(df), 100 * n_reference_mismatch / len(df) if len(df) else 0,
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

    # --- forecast_date validation (Phase B, B1) ---
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    n_null_forecast = df["forecast_date"].isna().sum()
    logger.info("%d of %d rows (%.4f%%) have a NULL/unparseable forecast_date — excluded from the "
                "forecast_date-keyed series only (kept in the createDate-keyed series).",
                n_null_forecast, n_rows, 100 * n_null_forecast / n_rows if n_rows else 0)
    negative_interval = df[df["forecast_date"].notna() & (df["forecast_date"] < df["createDate"])]
    logger.info("%d of %d rows (%.4f%%) have forecast_date BEFORE createDate (known anomaly, Phase A) — "
                "excluded from the forecast_date-keyed series only.", len(negative_interval), n_rows,
                100 * len(negative_interval) / n_rows if n_rows else 0)
    anomaly = df[df["forecast_date"].notna() & (
        (df["forecast_date"] <= FORECAST_DATE_ANOMALY_LOW) | (df["forecast_date"] >= FORECAST_DATE_ANOMALY_HIGH))]
    if len(anomaly) > 0:
        raise ValueError(f"Found {len(anomaly)} rows with an anomalous forecast_date (epoch/future) — "
                          f"must be reviewed, not silently dropped.")
    logger.info("0 forecast_date epoch/future-date anomalies found in this fresh pull.")

    logger.info(
        "Validation passed: %d rows, %d distinct items (of %d expected), no negative values, "
        "no out-of-range dates, 0 rows dropped",
        n_rows, len(pulled_items), len(expected_items),
    )
    return df


def aggregate_monthly(df: pd.DataFrame, item_codes: list, date_col: str, common_months=None,
                       snapshot_pull_date: str = None) -> tuple:
    """Aggregate raw daily rows to one row per (item, month), keyed on `date_col`
    ('createDate' or 'forecast_date'). Every item gets a complete, gap-free monthly
    series — months with no sales are filled with zero, not omitted, since a missing
    month and a zero-sales month mean different things to a forecasting model but
    must both be representable here as zero. If `common_months` is given, the grid
    is restricted to it and out-of-window demand is excluded and reported (not
    silently dropped); otherwise the key's own natural full range is used.
    Returns (monthly_grid_df, stats_dict).
    """
    d = df.copy()
    if date_col == "forecast_date":
        n_before = len(d)
        d = d.dropna(subset=["forecast_date"])
        d = d[d["forecast_date"] >= d["createDate"]]
        logger.info("forecast_date-keyed: %d of %d raw rows excluded (null/negative-interval "
                    "forecast_date), %d rows used.", n_before - len(d), n_before, len(d))

    d["year_month"] = d[date_col].dt.to_period("M")

    if common_months is not None:
        common_set = set(common_months)
        outside = d[~d["year_month"].isin(common_set)]
        outside_qty, outside_sale = float(outside["qty"].sum()), float(outside["sale"].sum())
        if len(outside):
            logger.info("%s-keyed: %d rows (qty=%.1f, sale=%.2f) fall outside the common comparison "
                        "window — excluded from this grid, reported not silently dropped.",
                        date_col, len(outside), outside_qty, outside_sale)
        d = d[d["year_month"].isin(common_set)]
        months_used = sorted(common_set)
    else:
        outside_qty, outside_sale = 0.0, 0.0
        months_used = None

    monthly = d.groupby(["itemcode", "year_month"], as_index=False).agg(
        qty=("qty", "sum"), sale=("sale", "sum")
    )

    in_window_qty_total = d["qty"].sum()
    in_window_sale_total = d["sale"].sum()
    agg_qty_total = monthly["qty"].sum()
    agg_sale_total = monthly["sale"].sum()
    if abs(in_window_qty_total - agg_qty_total) > 1e-6 or abs(in_window_sale_total - agg_sale_total) > 1e-6:
        raise ValueError(
            f"[{date_col}] Monthly aggregation does not reconcile to its filtered source: "
            f"qty={in_window_qty_total} vs aggregated={agg_qty_total}, "
            f"sale={in_window_sale_total} vs aggregated={agg_sale_total}"
        )
    logger.info(
        "[%s] Reconciliation OK: monthly totals match the in-window source exactly (qty=%.2f, sale=%.2f)",
        date_col, agg_qty_total, agg_sale_total,
    )

    n_items_with_any_sales = monthly["itemcode"].nunique()
    if months_used is None:
        min_month, max_month = d["year_month"].min(), d["year_month"].max()
        months_used = pd.period_range(min_month, max_month, freq="M")

    full_index = pd.MultiIndex.from_product([item_codes, months_used], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()
    full["date_key"] = date_col
    full["snapshot_pull_date"] = snapshot_pull_date

    n_items_final = full["itemcode"].nunique()
    if n_items_final != len(item_codes):
        raise ValueError(f"[{date_col}] Final monthly grid has {n_items_final} items, expected {len(item_codes)}")

    logger.info(
        "[%s] Monthly grid built: %d items x %d months (%s to %s) = %d rows. In-window qty=%.1f, "
        "excluded-outside-window qty=%.1f",
        date_col, len(item_codes), len(months_used), min(months_used), max(months_used), len(full),
        agg_qty_total, outside_qty,
    )
    stats = {"date_key": date_col, "n_items": len(item_codes), "n_months": len(months_used),
              "min_month": str(min(months_used)), "max_month": str(max(months_used)),
              "in_window_qty": agg_qty_total, "in_window_sale": agg_sale_total,
              "excluded_outside_window_qty": outside_qty, "excluded_outside_window_sale": outside_sale}
    return full, stats


if __name__ == "__main__":
    config = load_config()

    forecastable_codes, excluded_codes, division_by_code = get_pilot_scope(config)
    pd.DataFrame({"itemcode": excluded_codes}).to_csv(
        os.path.join(SUMMARY_DIR, "excluded_items_no_history.csv"), index=False
    )
    logger.info(
        "Wrote %d excluded item codes (no sales history) for Phase 4 inventory planning "
        "to output/summary/excluded_items_no_history.csv",
        len(excluded_codes),
    )

    raw = pull_raw_sales(config, forecastable_codes, division_by_code)
    raw = validate_raw(raw, forecastable_codes, config["date_range"]["start"])

    raw.to_csv(os.path.join(DATA_DIR, "raw_pilot_sales_58items.csv"), index=False)
    logger.info("Saved raw pull, unmodified: output/data/raw_pilot_sales_58items.csv")

    snapshot_pull_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    max_createdate = raw["createDate"].max()
    createdate_month_end = max_createdate + pd.offsets.MonthEnd(0)
    latest_createdate_month = pd.Period(max_createdate, freq="M")
    all_createdate_months = pd.period_range(raw["createDate"].min(), latest_createdate_month, freq="M")
    complete_months = ([m for m in all_createdate_months if m != latest_createdate_month]
                        if max_createdate < createdate_month_end else list(all_createdate_months))
    common_months = complete_months  # this pilot scope has no fixed-31-month prior backtest to match

    monthly_createDate, stats_createDate = aggregate_monthly(
        raw, forecastable_codes, "createDate", common_months=common_months, snapshot_pull_date=snapshot_pull_date)
    monthly_forecastDate, stats_forecastDate = aggregate_monthly(
        raw, forecastable_codes, "forecast_date", common_months=common_months, snapshot_pull_date=snapshot_pull_date)

    monthly_createDate.to_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly_createDate.csv"), index=False)
    monthly_forecastDate.to_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly_forecastDate.csv"), index=False)
    monthly_createDate.to_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly.csv"), index=False)
    logger.info("Saved: processed_pilot_sales_monthly_createDate.csv, ..._forecastDate.csv, and the unsuffixed "
                "...monthly.csv (createDate alias, unchanged for existing scripts). Snapshot pull date: %s",
                snapshot_pull_date)
    pd.DataFrame([stats_createDate, stats_forecastDate]).to_csv(
        os.path.join(SUMMARY_DIR, "b1_rekeying_window_stats_58item_pilot.csv"), index=False)
