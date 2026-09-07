"""Phase C step 2: loads and validates sales data for the full 335 forecast-status item codes
across all divisions whose codes carry that status (PEM104 contributes none -- all 12 of its
codes are excluded from forecasting for a data-volume reason, see
output/summary/phaseC_step1revised_item_status_445.csv).

DIVISION (2026-09-04 correction, reaffirmed by the 2026-09-07/09 precondition check this script's
own run log records): the pricelist is authoritative for an item's division; the database's own
`division` column is reference-only and is NEVER used to filter which rows count as an item's
sales. Query selects by itemcode + revenue_type + status + date only. Each row's division is
attached from config['sheet_to_division']; the database's own value is kept as a separate
`division_db_raw` reference column.

Extends src/load_data_full.py's 128-item (PEM101 sheet, Fuse+Surge Category) scope to the full
335-item, 5-division scope Phase C step 2 forecasts. Does NOT replace load_data_full.py or its
128-item outputs (STATUS.md: that scope's method is "Proven, method locked") -- this is a
separate, additive script with its own output filenames.

Series is keyed on forecast_date (contractual delivery date), captured as a FROZEN SNAPSHOT at
run time (a `snapshot_pull_date` column, constant per run, is written into every output file) --
never re-queried live, consistent with this project's adopted_series_key (config.yaml) and the
reason recorded in STATUS.md (Phase A could not rule out forecast_date revision after intake, so
treating it as ever-changing would make results non-reproducible across runs).
"""
import logging
import os
import sys
from datetime import datetime

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from leakage_guard import load_min_margin_days
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("load_data_all_divisions")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
ITEM_STATUS_FILE = os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv")

FORECAST_DATE_ANOMALY_LOW = pd.Timestamp("1971-01-01")
FORECAST_DATE_ANOMALY_HIGH = pd.Timestamp("2030-01-01")
REQUIRED_MONTHS = 31  # matches every existing project backtest's TRAIN(19)+VAL(6)+TEST(6) window


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_forecast_scope(config: dict) -> pd.DataFrame:
    """Returns (code, sheet, division, category, type) for every item code whose
    phaseC_step1revised_item_status_445.csv status_category is 'forecast'."""
    status_df = pd.read_csv(ITEM_STATUS_FILE)
    forecast_codes = status_df[status_df["status_category"] == "forecast"][["itemcode", "sheet", "division"]]
    logger.info("%d codes with status_category == 'forecast' in %s, across divisions: %s",
                len(forecast_codes), ITEM_STATUS_FILE,
                forecast_codes["division"].value_counts().to_dict())

    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pdf = load_visible_product_rows(pricelist_path)
    merged = forecast_codes.merge(
        pdf[["code", "category", "type"]].drop_duplicates(subset=["code"]),
        left_on="itemcode", right_on="code", how="left",
    )
    missing_cat = merged[merged["category"].isna()]
    if len(missing_cat):
        raise ValueError(f"{len(missing_cat)} forecast-status codes have no pricelist category/type match: "
                          f"{missing_cat['itemcode'].tolist()}")
    merged = merged.drop(columns=["code"]).rename(columns={"itemcode": "code"})
    return merged[["code", "sheet", "division", "category", "type"]]


def pull_raw_sales(config: dict, scope: pd.DataFrame) -> pd.DataFrame:
    """No division filter -- see module docstring. division_db_raw kept for reference only."""
    source_table = config["source_table"]
    revenue_type = config["revenue_type"]
    statuses = config["status_basis"]
    start_date = config["date_range"]["start"]
    item_codes = sorted(scope["code"].unique())

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
        "Pulled %d raw rows: %d items across %d divisions, revenue_type=%s, status in %s, createDate >= %s "
        "(no division filter — division attached from pricelist below).",
        len(df), len(item_codes), scope["division"].nunique(), revenue_type, statuses, start_date,
    )
    division_by_code = dict(zip(scope["code"], scope["division"]))
    df["division"] = df["itemcode"].map(division_by_code)
    unmapped = df[df["division"].isna()]
    if len(unmapped) > 0:
        raise ValueError(f"{len(unmapped)} rows have an itemcode with no pricelist division mapping.")
    n_reference_mismatch = (df["division"] != df["division_db_raw"]).sum()
    logger.info(
        "%d of %d rows (%.2f%%) have a database division_db_raw that differs from the item's pricelist "
        "division — still counted (no division filter), division_db_raw kept for inspection.",
        n_reference_mismatch, len(df), 100 * n_reference_mismatch / len(df) if len(df) else 0,
    )
    n_mps = (df["status"] == "MPS").sum()
    logger.info("Of these, %d rows are MPS (confirmed demand — kept, never dropped)", n_mps)
    return df


def validate_raw(df: pd.DataFrame, item_codes: list, start_date: str) -> pd.DataFrame:
    n_rows = len(df)
    neg_qty = df[df["qty"] < 0]
    if len(neg_qty) > 0:
        raise ValueError(f"Found {len(neg_qty)} rows with negative qty.")
    neg_sale = df[df["sale"] < 0]
    if len(neg_sale) > 0:
        raise ValueError(f"Found {len(neg_sale)} rows with negative sale.")

    df = df.copy()
    df["createDate"] = pd.to_datetime(df["createDate"])
    today = pd.Timestamp.now().normalize()
    out_of_range = df[(df["createDate"] < pd.Timestamp(start_date)) | (df["createDate"] > today)]
    if len(out_of_range) > 0:
        raise ValueError(f"Found {len(out_of_range)} rows with createDate outside [{start_date}, {today.date()}].")

    pulled_items = set(df["itemcode"].unique())
    expected_items = set(item_codes)
    missing_entirely = expected_items - pulled_items
    if missing_entirely:
        logger.warning("%d of %d forecast-scope items have ZERO rows under this scope: %s",
                        len(missing_entirely), len(expected_items), sorted(missing_entirely))

    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    n_null_forecast = df["forecast_date"].isna().sum()
    logger.info("%d of %d rows (%.4f%%) have a NULL/unparseable forecast_date — excluded from the "
                "forecast_date-keyed series only.", n_null_forecast, n_rows,
                100 * n_null_forecast / n_rows if n_rows else 0)
    negative_interval = df[df["forecast_date"].notna() & (df["forecast_date"] < df["createDate"])]
    logger.info("%d of %d rows (%.4f%%) have forecast_date BEFORE createDate (known anomaly) — "
                "excluded from the forecast_date-keyed series only.", len(negative_interval), n_rows,
                100 * len(negative_interval) / n_rows if n_rows else 0)
    anomaly = df[df["forecast_date"].notna() & (
        (df["forecast_date"] <= FORECAST_DATE_ANOMALY_LOW) | (df["forecast_date"] >= FORECAST_DATE_ANOMALY_HIGH))]
    if len(anomaly) > 0:
        raise ValueError(f"Found {len(anomaly)} rows with an anomalous forecast_date (epoch/future).")
    logger.info("0 forecast_date epoch/future-date anomalies found in this fresh pull.")
    logger.info("Validation passed: %d rows, %d distinct items (of %d expected), no negative values, "
                "no out-of-range dates.", n_rows, len(pulled_items), len(expected_items))
    return df


def aggregate_monthly(df: pd.DataFrame, item_codes: list, value_col: str, common_months,
                       snapshot_pull_date: str) -> pd.DataFrame:
    """Builds the monthly (itemcode, year_month) grid keyed on forecast_date, restricted to
    `common_months`, summing `value_col` ('qty' or 'sale' — Part 2 of this task needs both)."""
    d = df.copy()
    n_before = len(d)
    d = d.dropna(subset=["forecast_date"])
    d = d[d["forecast_date"] >= d["createDate"]]
    logger.info("[%s] forecast_date-keyed aggregation: %d of %d raw rows excluded (null or negative-interval "
                "forecast_date), %d rows used.", value_col, n_before - len(d), n_before, len(d))

    d["year_month"] = d["forecast_date"].dt.to_period("M")
    common_set = set(common_months)
    outside = d[~d["year_month"].isin(common_set)]
    if len(outside):
        logger.info("[%s] %d rows (value=%.1f) fall outside the common %d-month window, excluded.",
                    value_col, len(outside), outside[value_col].sum(), len(common_months))
    d = d[d["year_month"].isin(common_set)]

    monthly = d.groupby(["itemcode", "year_month"], as_index=False).agg(value=(value_col, "sum"))
    full_index = pd.MultiIndex.from_product([item_codes, sorted(common_months)], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()
    full = full.rename(columns={"value": value_col})
    full["snapshot_pull_date"] = snapshot_pull_date

    n_items_final = full["itemcode"].nunique()
    if n_items_final != len(item_codes):
        raise ValueError(f"[{value_col}] Final monthly grid has {n_items_final} items, expected {len(item_codes)}")
    logger.info("[%s] Monthly grid built: %d items x %d months = %d rows. Total %s: %.1f",
                value_col, len(item_codes), len(common_months), len(full), value_col, full[value_col].sum())
    return full


if __name__ == "__main__":
    config = load_config()
    scope = get_forecast_scope(config)
    scope.to_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"), index=False)
    item_codes = sorted(scope["code"].unique())

    raw = pull_raw_sales(config, scope)
    raw = validate_raw(raw, item_codes, config["date_range"]["start"])
    raw.to_csv(os.path.join(DATA_DIR, "raw_all_divisions_sales.csv"), index=False)

    snapshot_pull_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Snapshot pull date recorded for this run: %s", snapshot_pull_date)

    d = raw.copy()
    d["forecast_date_valid"] = pd.to_datetime(d["forecast_date"], errors="coerce")
    d = d[d["forecast_date_valid"].notna() & (d["forecast_date_valid"] >= d["createDate"])]
    d["year_month"] = d["forecast_date_valid"].dt.to_period("M")
    all_months = sorted(d["year_month"].unique())
    max_createdate = raw["createDate"].max()
    latest_createdate_month = pd.Period(max_createdate, freq="M")
    complete_months = [m for m in all_months if m < latest_createdate_month]

    # Leakage guard (src/leakage_guard.py): a window's LAST month must clear min_margin_days of
    # calendar distance from the pull date before any backtest may score it. Applied here too,
    # not just inside the backtest scripts, so the common window this loader emits is never
    # unusable by construction — excluding it later per-origin would otherwise silently shrink
    # every division/Type's usable history without that being visible at load time.
    min_margin_days = load_min_margin_days(config)
    pull_ts = pd.Timestamp(snapshot_pull_date).normalize()
    safe_months = [m for m in complete_months
                   if (pull_ts - pd.Period(m, freq="M").end_time.normalize()).days >= min_margin_days]
    n_excluded_by_guard = len(complete_months) - len(safe_months)
    if n_excluded_by_guard:
        logger.info("Leakage guard (min_margin_days=%d): %d of %d createDate-complete months excluded "
                    "because their month-end is too close to the pull date (%s) — %s.",
                    min_margin_days, n_excluded_by_guard, len(complete_months), snapshot_pull_date,
                    [str(m) for m in complete_months if m not in safe_months])
    complete_months = safe_months
    if len(complete_months) > REQUIRED_MONTHS:
        common_months = complete_months[-REQUIRED_MONTHS:]
        logger.info("%d complete forecast_date months available; truncated to the most recent %d (%s to %s).",
                    len(complete_months), REQUIRED_MONTHS, common_months[0], common_months[-1])
    elif len(complete_months) < REQUIRED_MONTHS:
        common_months = complete_months
        logger.warning("Only %d complete months available (< the usual %d) — proceeding with what exists, "
                        "reported explicitly, not padded.", len(complete_months), REQUIRED_MONTHS)
    else:
        common_months = complete_months
    logger.info("Common window: %d months, %s to %s", len(common_months), common_months[0], common_months[-1])

    monthly_qty = aggregate_monthly(raw, item_codes, "qty", common_months, snapshot_pull_date)
    monthly_sale = aggregate_monthly(raw, item_codes, "sale", common_months, snapshot_pull_date)

    type_map = scope[["code", "category", "type", "division"]].rename(columns={"code": "itemcode"})
    monthly_qty = monthly_qty.merge(type_map, on="itemcode", how="left")
    monthly_sale = monthly_sale.merge(type_map, on="itemcode", how="left")

    monthly_qty.to_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"), index=False)
    monthly_sale.to_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_sale.csv"), index=False)

    print("\n" + "=" * 78)
    print("PHASE C STEP 2: ALL-DIVISION SCOPE LOAD")
    print("=" * 78)
    print(f"Scope: {len(scope)} items across {scope['division'].nunique()} divisions: "
          f"{scope['division'].value_counts().to_dict()}")
    print(f"Common window: {len(common_months)} months, {common_months[0]} to {common_months[-1]}")
    print(f"Total qty: {monthly_qty['qty'].sum():,.0f}   Total sale: {monthly_sale['sale'].sum():,.2f}")
    print(f"Snapshot pull date: {snapshot_pull_date}")
    print("Outputs: output/data/raw_all_divisions_sales.csv, "
          "processed_all_divisions_monthly_{qty,sale}.csv, "
          "output/summary/phaseC_step2_scope_335items.csv")
