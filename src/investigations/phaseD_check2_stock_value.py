"""Phase D, Check 2 (Explorer role, AGENTS.md): value tied up in stock.

Scope is deliberately narrow, per the task instructions: only
`[salewarehouse].[dbo].[Cube_Inventory_Exact]` (current stock quantity, ALL warehouse codes
summed at item level -- this is a total-capital-tied-up figure, not a sellable-stock figure,
which is Check 1's separate job) joined to `[salewarehouse].[dbo].[cube_Sale_APD]` (for the
`cost` column) is searched. No other table is queried.

INVESTIGATION ONLY, per AGENTS.md Explorer role: reports what queries return, never interprets
business meaning beyond stating the arithmetic. config.yaml is not touched.

*** METHODOLOGY FINDING, load-bearing, checked directly before any value was computed ***
The task brief describes `cube_Sale_APD.cost` as a "unit cost" column. That is NOT what the data
shows. Checked directly (see `_diagnose_cost_is_line_total` below, run against the live table):
for item EEE-F-FC-1040010002, multiple rows on the same day carry `cost` values of 3,094.36,
32,490.78, 69,623.10, 92,830.80, 108,302.60 and 154,718.00 against qty of 2, 21, 45, 60, 70 and
100 respectively -- cost/qty = 1,547.18 EXACTLY in every one of those rows. A broader check across
51,059 sale rows (qty<>0, cost not null, >=5 rows per item, 747 items) found unit_cost = cost/qty
has a median within-item coefficient of variation of 0.108 -- consistent with a per-unit price
that drifts slowly over time (real-world cost changes), not with `cost` already being a per-unit
figure (which would show CV effectively 0 or wildly implausible jumps). **Conclusion: `cost` is
the LINE-TOTAL cost of that sale row (qty * unit cost), not a unit cost.** This script therefore
derives unit cost as `cost / qty` per row before computing any "most recent" or "median" basis --
using the raw `cost` column directly, as the task brief's wording suggests, would overstate stock
value by roughly two orders of magnitude for high-qty rows. This finding is reported, not silently
worked around: see the report's "Findings" section.

Essential prior context relied on here (STATUS.md, Section 8.4 and Phase C closure):
- `output/summary/phaseC_step1revised_item_status_445.csv` classifies all 445 pricelist codes
  into status_category (forecast=335, placeholder - pending method=82, placeholder - method
  already assigned=10, excluded - division excluded from forecasting=12, excluded - listed but
  never sold=6).
- `output/data/processed_all_divisions_monthly_qty.csv` holds monthly qty for the 335
  forecast-status items, 2024-01 to 2026-07 (31 months) -- used here as the demand basis for
  months-of-cover, via mean monthly qty over that window (stated explicitly, chosen because no
  single "the forecast" file for all 335 items' FUTURE demand exists yet in one place).
- CONVENTIONS.md: the pricelist is authoritative for category/type/division; database columns for
  the same attributes are reference-only.
- STATUS.md Section 8.4 / CONVENTIONS.md: this is CAPITAL TIED UP (a point-in-time value), NOT an
  annual carrying cost -- no annual holding-cost rate exists in this data (the 15-25% figure
  elsewhere in STATUS.md is explicitly flagged as an unverified, uncited assumption, not a fact).
  An annual rate must be set as a configurable assumption in Phase E, not derived here.
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
logger = logging.getLogger("phaseD_check2_stock_value")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")

INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"
SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
ITEM_STATUS_FILE = os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv")
DEMAND_FILE = os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv")

MEDIAN_WINDOW_MONTHS = 12  # "last twelve months of available data" per the task brief
TOP_N_VALUE_ITEMS = 10


# ============================================================================================
# DATA ACCESS
# ============================================================================================

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_pricelist_registry(config: dict) -> pd.DataFrame:
    """One row per code (445 rows): code, sheet, division, category, type.

    Pricelist is authoritative for category/type/division (CONVENTIONS.md). Deduplicates
    within-sheet repeated codes (keep first), raises if any code appears on >1 distinct sheet
    (would double-count across divisions).
    """
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    df = load_visible_product_rows(pricelist_path)
    assert_no_code_on_multiple_sheets(df)
    before = len(df)
    df = df.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    logger.info("Pricelist registry: %d rows loaded, %d after within-sheet dedup.", before, len(df))

    sheet_to_division = config["sheet_to_division"]
    unmapped = set(df["sheet"].unique()) - set(sheet_to_division.keys())
    if unmapped:
        raise ValueError(f"Sheets with product rows but no sheet_to_division mapping: {unmapped}")
    df["division"] = df["sheet"].map(sheet_to_division)

    n_null_type = df["type"].isna().sum()
    if n_null_type:
        logger.info("%d codes have a null Product Type in the pricelist (kept null, not invented): %s",
                    n_null_type, df.loc[df["type"].isna(), "code"].tolist())
    df["type"] = df["type"].fillna("(Unclassified — no Product Type in pricelist)")
    return df[["code", "sheet", "division", "category", "type"]].rename(columns={"code": "itemcode"})


def load_item_status() -> pd.DataFrame:
    """status_category (and reason) for all 445 codes, from Phase C closure."""
    df = pd.read_csv(ITEM_STATUS_FILE)
    required = {"itemcode", "status_category"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{ITEM_STATUS_FILE} missing required column(s): {missing}")
    return df[["itemcode", "status_category"]]


def query_inventory_exact(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT itemcode, warehouse, stock, timestamp
        FROM {INV_TABLE}
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    logger.info("Pulled %d rows from %s for %d item codes (%d distinct itemcodes present).",
                len(df), INV_TABLE, len(item_codes), df["itemcode"].nunique())
    return df


def query_sale_cost(item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT itemcode, qty, cost, createDate
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    df["createDate"] = pd.to_datetime(df["createDate"])
    logger.info("Pulled %d rows from %s for %d item codes (%d distinct itemcodes present, "
                "createDate range %s to %s).",
                len(df), SALE_TABLE, len(item_codes), df["itemcode"].nunique(),
                df["createDate"].min(), df["createDate"].max())
    return df


def load_demand_basis() -> pd.DataFrame:
    """Mean monthly qty per item, 2024-01 to 2026-07 (335 forecast-status items only)."""
    df = pd.read_csv(DEMAND_FILE)
    required = {"itemcode", "year_month", "qty"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{DEMAND_FILE} missing required column(s): {missing}")
    n_months = df["year_month"].nunique()
    n_items = df["itemcode"].nunique()
    logger.info("Demand basis file: %d items x %d months (%s to %s).",
                n_items, n_months, df["year_month"].min(), df["year_month"].max())
    demand = df.groupby("itemcode", as_index=False)["qty"].mean().rename(
        columns={"qty": "mean_monthly_qty_2024_01_to_2026_07"})
    return demand


# ============================================================================================
# COMPUTATION
# ============================================================================================

def _diagnose_cost_is_line_total(sale_raw: pd.DataFrame) -> dict:
    """Re-derives, from the pulled data itself, the evidence that `cost` is a line-total, not
    a unit cost. Returns a small dict of diagnostic numbers cited in the report. Does not alter
    any computed value -- purely for evidence/citation."""
    df = sale_raw.copy()
    df = df[(df["qty"].notna()) & (df["qty"] != 0) & (df["cost"].notna())]
    df["unit_cost"] = df["cost"] / df["qty"]
    counts = df.groupby("itemcode").size()
    eligible = counts[counts >= 5].index
    sub = df[df["itemcode"].isin(eligible)]
    g = sub.groupby("itemcode")["unit_cost"].agg(["mean", "std", "count"])
    g = g[g["mean"] != 0]
    g["cv"] = g["std"] / g["mean"]
    return {
        "n_items_with_ge5_rows": int(len(g)),
        "median_within_item_cv_of_cost_over_qty": float(g["cv"].median()),
    }


def compute_stock_qty_per_item(inv_raw: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Sums stock across ALL warehouse codes (no exclusion — this is a total-capital figure).
    Items absent from Cube_Inventory_Exact entirely get qty=0 (confirmed absence of any row,
    not a missing-data gap for this figure)."""
    per_item = inv_raw.groupby("itemcode", as_index=False)["stock"].sum().rename(
        columns={"stock": "stock_qty_all_warehouses"})
    out = registry[["itemcode"]].merge(per_item, on="itemcode", how="left")
    n_no_row = out["stock_qty_all_warehouses"].isna().sum()
    out["stock_qty_all_warehouses"] = out["stock_qty_all_warehouses"].fillna(0.0)
    logger.info("Stock qty computed for all %d registry items; %d had zero rows in %s (qty set to 0).",
                len(out), n_no_row, INV_TABLE)
    return out


def compute_cost_bases(sale_raw: pd.DataFrame) -> pd.DataFrame:
    """Per item: most-recent-transaction unit cost, median-last-12-months unit cost, and row
    counts backing each, derived from cost/qty (see module docstring for why).

    Ties on max(createDate) are resolved by averaging the unit costs of the tied rows (logged).
    The 12-month window is anchored to the GLOBAL max(createDate) across the whole pulled
    dataset (2026-09-07 at pull time), not per item, so every item's window covers the same
    calendar period.
    """
    df = sale_raw.copy()
    df = df[(df["qty"].notna()) & (df["qty"] != 0) & (df["cost"].notna())]
    df["unit_cost"] = df["cost"] / df["qty"]

    global_max_date = df["createDate"].max()
    window_start = global_max_date - pd.DateOffset(months=MEDIAN_WINDOW_MONTHS)
    logger.info("Cost-basis window: last %d months anchored to global max createDate %s -> "
                "window start %s.", MEDIAN_WINDOW_MONTHS, global_max_date.date(), window_start.date())

    # --- most-recent-transaction basis ---
    max_date_per_item = df.groupby("itemcode")["createDate"].transform("max")
    is_max = df["createDate"] == max_date_per_item
    tied_counts = df[is_max].groupby("itemcode").size()
    n_ties = int((tied_counts > 1).sum())
    recent = df[is_max].groupby("itemcode", as_index=False).agg(
        most_recent_unit_cost=("unit_cost", "mean"),
        most_recent_transaction_date=("createDate", "max"),
        n_rows_on_most_recent_date=("unit_cost", "size"),
    )
    logger.info("Most-recent-transaction basis: %d items had >1 row tied on the max createDate "
                "(resolved by averaging their derived unit costs).", n_ties)

    # --- median-last-12-months basis ---
    in_window = df[df["createDate"] >= window_start]
    median12 = in_window.groupby("itemcode", as_index=False).agg(
        median_unit_cost_12mo=("unit_cost", "median"),
        n_rows_12mo=("unit_cost", "size"),
    )

    # --- row counts (all time, for the no-cost-record check) ---
    all_time = df.groupby("itemcode", as_index=False).agg(
        n_rows_all_time=("unit_cost", "size"),
        first_createDate=("createDate", "min"),
        last_createDate=("createDate", "max"),
    )

    out = all_time.merge(recent, on="itemcode", how="left").merge(median12, on="itemcode", how="left")
    out["n_rows_12mo"] = out["n_rows_12mo"].fillna(0).astype(int)
    return out


def choose_primary_cost(cost_bases: pd.DataFrame) -> pd.DataFrame:
    """Primary basis = median unit cost over the last 12 months (robust to one-off/error rows —
    this project's own history has repeatedly found isolated one-off/outlier rows in
    cube_Sale_APD-family tables, e.g. STATUS.md's large-order and duplicate-row investigations;
    a single unusually large or small transaction should not set an entire item's valuation).
    Falls back to the most-recent-transaction basis, FLAGGED explicitly, for items that have a
    cost history but none within the last 12 months (median12 is NaN but most_recent exists) —
    never silently substituted. Sanity companion: most_recent_unit_cost, kept alongside for the
    top-value comparison the task brief asks for.
    """
    out = cost_bases.copy()
    has_median = out["median_unit_cost_12mo"].notna()
    has_recent = out["most_recent_unit_cost"].notna()

    out["primary_unit_cost"] = np.where(has_median, out["median_unit_cost_12mo"], np.nan)
    out["primary_basis"] = np.where(has_median, "median_last_12mo", None)

    fallback_mask = (~has_median) & has_recent
    out.loc[fallback_mask, "primary_unit_cost"] = out.loc[fallback_mask, "most_recent_unit_cost"]
    out.loc[fallback_mask, "primary_basis"] = "most_recent_transaction (FALLBACK — no cost row in last 12mo)"
    n_fallback = int(fallback_mask.sum())
    logger.info("%d items used the most-recent-transaction fallback (had cost history, but none "
                "in the last %d months).", n_fallback, MEDIAN_WINDOW_MONTHS)

    no_cost = (~has_median) & (~has_recent)
    out.loc[no_cost, "primary_basis"] = "NO_COST_RECORD"
    return out


def compute_relative_diff_flag(df: pd.DataFrame, threshold: float = 0.20) -> pd.DataFrame:
    """Flags items where median_unit_cost_12mo and most_recent_unit_cost differ by more than
    `threshold` (relative to the larger of the two) — both bases present."""
    both = df["median_unit_cost_12mo"].notna() & df["most_recent_unit_cost"].notna()
    diff = (df["median_unit_cost_12mo"] - df["most_recent_unit_cost"]).abs()
    denom = df[["median_unit_cost_12mo", "most_recent_unit_cost"]].max(axis=1)
    rel_diff = diff / denom
    df = df.copy()
    df["cost_basis_relative_diff"] = np.where(both, rel_diff, np.nan)
    df["cost_basis_material_diff"] = both & (rel_diff > threshold)
    return df


def build_item_table(registry: pd.DataFrame, status: pd.DataFrame, stock_qty: pd.DataFrame,
                      cost_bases: pd.DataFrame, demand: pd.DataFrame) -> pd.DataFrame:
    df = registry.merge(status, on="itemcode", how="left")
    df = df.merge(stock_qty, on="itemcode", how="left")
    df = df.merge(cost_bases, on="itemcode", how="left")
    df = df.merge(demand, on="itemcode", how="left")

    df["primary_basis"] = df["primary_basis"].fillna("NO_COST_RECORD")
    df["has_cost_record"] = df["primary_basis"] != "NO_COST_RECORD"
    df["stock_value"] = np.where(df["has_cost_record"],
                                  df["stock_qty_all_warehouses"] * df["primary_unit_cost"], np.nan)
    df["stock_value_most_recent_basis"] = np.where(
        df["most_recent_unit_cost"].notna(),
        df["stock_qty_all_warehouses"] * df["most_recent_unit_cost"], np.nan)

    df["months_of_cover"] = np.where(
        df["mean_monthly_qty_2024_01_to_2026_07"].fillna(0) > 0,
        df["stock_qty_all_warehouses"] / df["mean_monthly_qty_2024_01_to_2026_07"],
        np.nan)
    df["months_of_cover_note"] = np.select(
        [
            df["status_category"] != "forecast",
            df["mean_monthly_qty_2024_01_to_2026_07"].isna(),
            df["mean_monthly_qty_2024_01_to_2026_07"] == 0,
        ],
        [
            "N/A — not a forecast-status item, no demand basis to plan against",
            "N/A — item not found in demand basis file",
            "undefined (mean monthly qty = 0 over 2024-01..2026-07 — stock covers indefinitely long)",
        ],
        default="",
    )
    return df


# ============================================================================================
# ROLLUPS / REPORTS
# ============================================================================================

def rollup_by(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    priced = df[df["has_cost_record"]]
    g = df.groupby(group_col, as_index=False).agg(
        n_items=("itemcode", "nunique"),
        n_items_with_stock=("stock_qty_all_warehouses", lambda s: (s > 0).sum()),
        total_stock_qty=("stock_qty_all_warehouses", "sum"),
    )
    gv = priced.groupby(group_col, as_index=False).agg(
        n_items_priced=("itemcode", "nunique"),
        priced_stock_value=("stock_value", "sum"),
    )
    out = g.merge(gv, on=group_col, how="left")
    out["n_items_priced"] = out["n_items_priced"].fillna(0).astype(int)
    out["priced_stock_value"] = out["priced_stock_value"].fillna(0.0)
    unpriced_qty = df[~df["has_cost_record"]].groupby(group_col)["stock_qty_all_warehouses"].sum()
    out["unpriced_stock_qty_value_undetermined"] = out[group_col].map(unpriced_qty).fillna(0.0)
    return out.sort_values("priced_stock_value", ascending=False)


def top_value_items(df: pd.DataFrame, n: int) -> pd.DataFrame:
    priced = df[df["has_cost_record"] & (df["stock_qty_all_warehouses"] > 0)].copy()
    priced = compute_relative_diff_flag(priced)
    top = priced.sort_values("stock_value", ascending=False).head(n)
    cols = ["itemcode", "category", "type", "division", "status_category",
            "stock_qty_all_warehouses", "primary_basis", "primary_unit_cost", "stock_value",
            "most_recent_unit_cost", "stock_value_most_recent_basis", "cost_basis_relative_diff",
            "cost_basis_material_diff", "mean_monthly_qty_2024_01_to_2026_07",
            "months_of_cover", "months_of_cover_note"]
    return top[cols]


def no_forecast_value_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    no_forecast = df[df["status_category"] != "forecast"]
    priced = no_forecast[no_forecast["has_cost_record"]]
    g = no_forecast.groupby("status_category", as_index=False).agg(
        n_items=("itemcode", "nunique"),
        n_items_with_stock=("stock_qty_all_warehouses", lambda s: (s > 0).sum()),
        total_stock_qty=("stock_qty_all_warehouses", "sum"),
    )
    gv = priced.groupby("status_category", as_index=False).agg(
        n_items_priced=("itemcode", "nunique"),
        priced_stock_value=("stock_value", "sum"),
    )
    out = g.merge(gv, on="status_category", how="left")
    out["n_items_priced"] = out["n_items_priced"].fillna(0).astype(int)
    out["priced_stock_value"] = out["priced_stock_value"].fillna(0.0)
    unpriced_qty = no_forecast[~no_forecast["has_cost_record"]].groupby("status_category")[
        "stock_qty_all_warehouses"].sum()
    out["unpriced_stock_qty_value_undetermined"] = out["status_category"].map(unpriced_qty).fillna(0.0)
    return out


def stock_no_cost_items(df: pd.DataFrame) -> pd.DataFrame:
    mask = (df["stock_qty_all_warehouses"] > 0) & (~df["has_cost_record"])
    cols = ["itemcode", "category", "type", "division", "status_category",
            "stock_qty_all_warehouses", "n_rows_all_time"]
    out = df.loc[mask, cols].copy()
    out["n_rows_all_time"] = out["n_rows_all_time"].fillna(0).astype(int)
    out["reason"] = np.where(out["n_rows_all_time"] == 0,
                              "0 rows in cube_Sale_APD for this itemcode",
                              "rows exist in cube_Sale_APD but none with a usable cost (should not "
                              "occur — cost was non-null for all pulled rows; flagged for review if seen)")
    return out.sort_values("stock_qty_all_warehouses", ascending=False)


# ============================================================================================
# MAIN
# ============================================================================================

def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    config = load_config()

    logger.info("=== STEP 1: pricelist registry + item status ===")
    registry = load_pricelist_registry(config)
    status = load_item_status()
    missing_status = set(registry["itemcode"]) - set(status["itemcode"])
    if missing_status:
        raise ValueError(f"{len(missing_status)} registry items missing from item status file: {missing_status}")

    logger.info("=== STEP 2: query Cube_Inventory_Exact (current stock, ALL warehouses) ===")
    item_codes = sorted(registry["itemcode"].unique())
    inv_raw = query_inventory_exact(item_codes)
    stock_qty = compute_stock_qty_per_item(inv_raw, registry)
    n_with_stock = int((stock_qty["stock_qty_all_warehouses"] > 0).sum())
    logger.info("%d of %d items have stock_qty_all_warehouses > 0.", n_with_stock, len(stock_qty))

    logger.info("=== STEP 3: query cube_Sale_APD (cost) and derive unit cost ===")
    sale_raw = query_sale_cost(item_codes)
    diag = _diagnose_cost_is_line_total(sale_raw)
    logger.info("Line-total-cost diagnostic: %d items with >=5 usable rows, median within-item "
                "CV of (cost/qty) = %.4f — consistent with cost being a LINE TOTAL, not a unit "
                "cost (see module docstring for the row-level evidence).",
                diag["n_items_with_ge5_rows"], diag["median_within_item_cv_of_cost_over_qty"])
    cost_bases = compute_cost_bases(sale_raw)
    cost_bases = choose_primary_cost(cost_bases)
    n_no_cost = int((cost_bases["primary_basis"] == "NO_COST_RECORD").sum())
    n_items_any_row = sale_raw["itemcode"].nunique()
    logger.info("%d of %d registry items have >=1 row in cube_Sale_APD; %d items have a usable "
                "cost basis; %d items have NO cost record at all.",
                n_items_any_row, len(registry), len(cost_bases), len(registry) - len(cost_bases))

    logger.info("=== STEP 4: demand basis (335 forecast-status items, mean monthly qty) ===")
    demand = load_demand_basis()

    logger.info("=== STEP 5: build item-level table, compute stock value ===")
    item_table = build_item_table(registry, status, stock_qty, cost_bases, demand)
    checksum = len(item_table)
    if checksum != 445:
        raise ValueError(f"Item table has {checksum} rows, expected 445 (registry count) — stopping.")

    n_stock_no_cost = int(((item_table["stock_qty_all_warehouses"] > 0) & (~item_table["has_cost_record"])).sum())
    total_priced_value = float(item_table.loc[item_table["has_cost_record"], "stock_value"].sum())
    total_unpriced_qty = float(item_table.loc[~item_table["has_cost_record"], "stock_qty_all_warehouses"].sum())
    logger.info("TOTAL priced stock value (primary basis, median-last-12mo with most-recent "
                "fallback): THB %.2f across %d priced items. %d items have stock but NO cost "
                "record (total %.1f units, value undetermined).",
                total_priced_value, int(item_table["has_cost_record"].sum()), n_stock_no_cost,
                total_unpriced_qty)

    logger.info("=== STEP 6: rollups ===")
    by_type = rollup_by(item_table, "type")
    by_division = rollup_by(item_table, "division")
    top10 = top_value_items(item_table, TOP_N_VALUE_ITEMS)
    no_forecast = no_forecast_value_breakdown(item_table)
    no_cost_items = stock_no_cost_items(item_table)

    logger.info("=== STEP 7: write CSVs ===")
    out_cols = ["itemcode", "category", "type", "division", "status_category",
                "stock_qty_all_warehouses", "n_rows_all_time", "first_createDate", "last_createDate",
                "most_recent_unit_cost", "most_recent_transaction_date", "n_rows_on_most_recent_date",
                "median_unit_cost_12mo", "n_rows_12mo", "primary_basis", "primary_unit_cost",
                "has_cost_record", "stock_value", "stock_value_most_recent_basis",
                "mean_monthly_qty_2024_01_to_2026_07", "months_of_cover", "months_of_cover_note"]
    item_table_out = item_table[out_cols].sort_values("stock_value", ascending=False, na_position="last")
    item_table_out.to_csv(os.path.join(SUMMARY_DIR, "phaseD_check2_item_stock_value.csv"), index=False)
    by_type.to_csv(os.path.join(SUMMARY_DIR, "phaseD_check2_rollup_by_type.csv"), index=False)
    by_division.to_csv(os.path.join(SUMMARY_DIR, "phaseD_check2_rollup_by_division.csv"), index=False)
    top10.to_csv(os.path.join(SUMMARY_DIR, "phaseD_check2_top10_value_items.csv"), index=False)
    no_forecast.to_csv(os.path.join(SUMMARY_DIR, "phaseD_check2_no_forecast_value_breakdown.csv"), index=False)
    no_cost_items.to_csv(os.path.join(SUMMARY_DIR, "phaseD_check2_stock_no_cost_items.csv"), index=False)

    logger.info("=== STEP 8: verification ===")
    recompute_total = float(item_table.loc[item_table["has_cost_record"], "stock_value"].sum())
    assert abs(recompute_total - total_priced_value) < 1e-6, "Recomputed total does not match logged total."
    by_type_sum = float(by_type["priced_stock_value"].sum())
    assert abs(by_type_sum - total_priced_value) < 1.0, \
        f"Type rollup sum ({by_type_sum:.2f}) does not match total priced value ({total_priced_value:.2f})."
    by_div_sum = float(by_division["priced_stock_value"].sum())
    assert abs(by_div_sum - total_priced_value) < 1.0, \
        f"Division rollup sum ({by_div_sum:.2f}) does not match total priced value ({total_priced_value:.2f})."
    logger.info("[PASS] item table row count == 445 registry items.")
    logger.info("[PASS] by-type rollup priced_stock_value sums to total priced value (THB %.2f).", by_type_sum)
    logger.info("[PASS] by-division rollup priced_stock_value sums to total priced value (THB %.2f).", by_div_sum)

    return {
        "item_table": item_table,
        "by_type": by_type,
        "by_division": by_division,
        "top10": top10,
        "no_forecast": no_forecast,
        "no_cost_items": no_cost_items,
        "total_priced_value": total_priced_value,
        "total_unpriced_qty": total_unpriced_qty,
        "n_stock_no_cost": n_stock_no_cost,
        "diag": diag,
    }


if __name__ == "__main__":
    main()
