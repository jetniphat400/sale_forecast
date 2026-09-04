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

RE-KEYING (Phase B, task B1, 2026-09-02): Phase A found the demand series was
keyed on createDate (PO receipt date) throughout this pipeline, when
inventory planning needs forecast_date (the contractual delivery date — the
date stock must actually be available by). This script now pulls both date
fields and builds monthly series keyed BOTH ways, saved to separate files
named by key (`..._createDate.csv` / `..._forecastDate.csv`). The original
unsuffixed filenames are also written, unchanged, as an alias of the
createDate-keyed series, so every existing downstream script that reads the
unsuffixed name keeps working exactly as before without modification — the
createDate-keyed series is kept alongside, not deleted, per instruction.

forecast_date is captured as a FROZEN SNAPSHOT at the moment this script is
run (a `snapshot_pull_date` column, constant per run, is written into every
output file), not re-queried live on every future read — Phase A could not
rule out forecast_date being revised after PO intake, so treating it as a
live, ever-changing field would make results non-reproducible across runs
(CONVENTIONS.md's reproducibility rule: record the cutoff used).
"""
import logging
import os
import sys
from datetime import datetime

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
# Epoch/future-date anomaly bounds a fresh pull is checked against every run (Phase A found none
# in this scope, but that must be reconfirmed on new data, never assumed to still hold).
FORECAST_DATE_ANOMALY_LOW = pd.Timestamp("1971-01-01")
FORECAST_DATE_ANOMALY_HIGH = pd.Timestamp("2030-01-01")


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
        SELECT itemcode, createDate, forecast_date, qty, sale, status, division, revenue_type
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

    # --- forecast_date validation (Phase B, B1) — re-checked every run, never assumed from Phase A ---
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    n_null_forecast = df["forecast_date"].isna().sum()
    logger.info("%d of %d rows (%.4f%%) have a NULL/unparseable forecast_date — these rows cannot be placed in the "
                "forecast_date-keyed series and are excluded from it only (kept in the createDate-keyed series).",
                n_null_forecast, n_rows, 100 * n_null_forecast / n_rows if n_rows else 0)

    negative_interval = df[df["forecast_date"].notna() & (df["forecast_date"] < df["createDate"])]
    logger.info("%d of %d rows (%.4f%%) have forecast_date BEFORE createDate — a known data anomaly (Phase A), "
                "excluded from the forecast_date-keyed series only.", len(negative_interval), n_rows,
                100 * len(negative_interval) / n_rows if n_rows else 0)

    anomaly = df[df["forecast_date"].notna() & (
        (df["forecast_date"] <= FORECAST_DATE_ANOMALY_LOW) | (df["forecast_date"] >= FORECAST_DATE_ANOMALY_HIGH))]
    if len(anomaly) > 0:
        raise ValueError(
            f"Found {len(anomaly)} rows with forecast_date <= {FORECAST_DATE_ANOMALY_LOW.date()} or "
            f">= {FORECAST_DATE_ANOMALY_HIGH.date()} — the table-wide epoch/future-date anomaly Phase A flagged "
            f"DOES reach this scope on this pull; data must be reviewed, not silently dropped. "
            f"Sample: {anomaly[['itemcode', 'createDate', 'forecast_date']].head(5).to_dict('records')}"
        )
    logger.info("0 forecast_date epoch/future-date anomalies found in this fresh pull (Phase A's negative finding "
                "for this scope re-confirmed, not assumed).")

    logger.info("Validation passed: %d rows, %d distinct items (of %d expected), no negative qty/sale, no "
                "out-of-range createDate, 0 rows dropped from the raw pull itself",
                n_rows, len(pulled_items), len(expected_items))
    return df


def aggregate_monthly(df: pd.DataFrame, item_codes: list, date_col: str, common_months=None,
                       snapshot_pull_date: str = None) -> tuple:
    """Builds the monthly (itemcode, year_month) grid keyed on `date_col` ('createDate' or
    'forecast_date'). If `common_months` (a list of Period objects) is given, the grid is
    restricted to exactly that calendar window — used to keep the two keyings directly
    comparable (Phase B, B1) — and any demand whose date_col value falls outside that window is
    excluded and reported separately (not silently dropped: its qty/sale total is returned).
    If `common_months` is None, the key's own natural full range is used instead.
    Returns (monthly_grid_df, stats_dict).
    """
    d = df.copy()
    if date_col == "forecast_date":
        n_before = len(d)
        d = d.dropna(subset=["forecast_date"])
        d = d[d["forecast_date"] >= d["createDate"]]  # drop the negative-interval anomaly rows too
        logger.info("forecast_date-keyed aggregation: %d of %d raw rows excluded (null or negative-interval "
                    "forecast_date), %d rows used.", n_before - len(d), n_before, len(d))

    d["year_month"] = d[date_col].dt.to_period("M")

    if common_months is not None:
        common_set = set(common_months)
        outside = d[~d["year_month"].isin(common_set)]
        outside_qty, outside_sale = float(outside["qty"].sum()), float(outside["sale"].sum())
        if len(outside):
            logger.info("%s-keyed: %d rows (qty=%.1f, sale=%.2f) fall OUTSIDE the common %d-month comparison "
                        "window and are excluded from this grid (reported separately, not silently dropped).",
                        date_col, len(outside), outside_qty, outside_sale, len(common_months))
        d = d[d["year_month"].isin(common_set)]
        months_used = sorted(common_set)
    else:
        outside_qty, outside_sale = 0.0, 0.0
        months_used = None

    monthly = d.groupby(["itemcode", "year_month"], as_index=False).agg(qty=("qty", "sum"), sale=("sale", "sum"))

    in_window_qty_total = float(d["qty"].sum())
    in_window_sale_total = float(d["sale"].sum())
    agg_qty_total = monthly["qty"].sum()
    agg_sale_total = monthly["sale"].sum()
    if abs(in_window_qty_total - agg_qty_total) > 1e-6 or abs(in_window_sale_total - agg_sale_total) > 1e-6:
        raise ValueError(f"[{date_col}] Monthly aggregation does not reconcile to its own filtered source: "
                          f"in-window qty={in_window_qty_total} vs aggregated qty={agg_qty_total}, "
                          f"in-window sale={in_window_sale_total} vs aggregated sale={agg_sale_total}")
    logger.info("[%s] Reconciliation OK: monthly totals match the in-window source exactly (qty=%.2f, sale=%.2f)",
                date_col, agg_qty_total, agg_sale_total)

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

    logger.info("[%s] Monthly grid built: %d items x %d months (%s to %s) = %d rows. "
                "In-window total qty=%.1f. Excluded-outside-window qty=%.1f (%.2f%% of in-window+excluded).",
                date_col, len(item_codes), len(months_used), min(months_used), max(months_used), len(full),
                agg_qty_total, outside_qty, 100 * outside_qty / (agg_qty_total + outside_qty) if (agg_qty_total + outside_qty) else 0)
    stats = {"date_key": date_col, "n_items": len(item_codes), "n_months": len(months_used),
              "min_month": str(min(months_used)), "max_month": str(max(months_used)),
              "in_window_qty": agg_qty_total, "in_window_sale": agg_sale_total,
              "excluded_outside_window_qty": outside_qty, "excluded_outside_window_sale": outside_sale}
    return full, stats


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

    snapshot_pull_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Snapshot pull date recorded for this run: %s (forecast_date is frozen at this value going "
                "forward for this pull — re-run this script to refresh it, it is never re-queried silently).",
                snapshot_pull_date)

    # Common comparison window: createDate's own complete-month range (excludes a trailing
    # partial month, same rule this project has always used), so both keyings can be compared
    # on identical calendar months (Phase B, B1) rather than each key's own, differently-shifted
    # natural range.
    max_createdate = raw["createDate"].max()
    createdate_month_end = max_createdate + pd.offsets.MonthEnd(0)
    latest_createdate_month = pd.Period(max_createdate, freq="M")
    all_createdate_months = pd.period_range(raw["createDate"].min(), latest_createdate_month, freq="M")
    if max_createdate < createdate_month_end:
        complete_months = [m for m in all_createdate_months if m != latest_createdate_month]
        logger.info("createDate's latest month %s is partial (data ends %s) — excluded from complete months.",
                    latest_createdate_month, max_createdate.date())
    else:
        complete_months = list(all_createdate_months)

    # Fixed at exactly TRAIN(19)+VAL(6)+TEST(6)=31 months, matching every existing backtest output
    # already in output/summary/ (evaluate_strategies.py, backtest_aggregate.py, etc.), so this
    # re-run is a true apples-to-apples comparison against them, not a shifted new window. More
    # months keep becoming complete as real time passes in this environment (32 were available on
    # this run) — those extra month(s) are deliberately NOT included here, stated explicitly
    # rather than silently changing the comparison window.
    REQUIRED_MONTHS = 31
    if len(complete_months) > REQUIRED_MONTHS:
        common_months = complete_months[:REQUIRED_MONTHS]
        logger.info("%d complete months available; truncated to the first %d (%s to %s) to match the fixed "
                    "31-month (19+6+6) window every existing backtest result was computed on. %d newer complete "
                    "month(s) (%s) exist but are excluded from this comparison, not silently absorbed.",
                    len(complete_months), REQUIRED_MONTHS, common_months[0], common_months[-1],
                    len(complete_months) - REQUIRED_MONTHS, complete_months[REQUIRED_MONTHS:])
    elif len(complete_months) < REQUIRED_MONTHS:
        raise ValueError(f"Only {len(complete_months)} complete months available, need {REQUIRED_MONTHS} to match "
                          f"the existing train/val/test backtests — cannot build a comparable window.")
    else:
        common_months = complete_months

    monthly_createDate, stats_createDate = aggregate_monthly(
        raw, forecastable_codes, "createDate", common_months=common_months, snapshot_pull_date=snapshot_pull_date)
    monthly_forecastDate, stats_forecastDate = aggregate_monthly(
        raw, forecastable_codes, "forecast_date", common_months=common_months, snapshot_pull_date=snapshot_pull_date)

    type_map = scope_df[["code", "category", "type"]].rename(columns={"code": "itemcode"})
    monthly_createDate = monthly_createDate.merge(type_map, on="itemcode", how="left")
    monthly_forecastDate = monthly_forecastDate.merge(type_map, on="itemcode", how="left")

    monthly_createDate.to_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly_createDate.csv"), index=False)
    monthly_forecastDate.to_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv"), index=False)
    # Unsuffixed filename kept as an EXACT alias of the createDate-keyed series (not deleted, not
    # changed in meaning) so every existing script that reads this name keeps working unmodified.
    monthly_createDate.to_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"), index=False)
    monthly = monthly_createDate  # for the per-Type report below, unchanged from before this edit

    pd.DataFrame([stats_createDate, stats_forecastDate]).to_csv(
        os.path.join(SUMMARY_DIR, "b1_rekeying_window_stats.csv"), index=False)

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

    print("\n" + "=" * 78)
    print("RE-KEYING (Phase B, B1): createDate-keyed vs forecast_date-keyed, same common window")
    print("=" * 78)
    print(f"Snapshot pull date (frozen forecast_date value used below): {snapshot_pull_date}")
    print(f"Common comparison window: {len(common_months)} months, {common_months[0]} to {common_months[-1]}")
    for s in (stats_createDate, stats_forecastDate):
        print(f"  [{s['date_key']}] in-window qty={s['in_window_qty']:,.1f}, sale={s['in_window_sale']:,.2f}; "
              f"excluded-outside-window qty={s['excluded_outside_window_qty']:,.1f}, "
              f"sale={s['excluded_outside_window_sale']:,.2f}")
    print("Outputs: output/data/processed_full_category_sales_monthly_createDate.csv, "
          "..._forecastDate.csv, and the unsuffixed ...monthly.csv (createDate alias, unchanged "
          "filename for existing scripts). Window stats: output/summary/b1_rekeying_window_stats.csv")
