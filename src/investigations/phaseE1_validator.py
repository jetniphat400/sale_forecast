"""Phase E1 — single Validator, independent recomputation of 4 headline figures.

Per the task instruction and AGENTS.md's Validator role: this script recomputes specific Phase
E1 headline figures INDEPENDENTLY, from raw data (a fresh live pull against the database) and
config alone. It does NOT read any Modeler intermediate file (no output/summary/phaseE1_*,
output/charts/phaseE1_*, or src/phaseE1_*.py file is imported or opened anywhere here).

It DOES reuse pre-existing, already-verified (pre-Phase-E1) project building blocks, exactly as
the task instructs:
  - src/db.py                     (DB connection / run_query)
  - src/models.py                 (combination_forecast — the LOCKED forecasting method)
  - src/pricelist_reader.py       (visible-sheet pricelist reader)
  - src/load_data_full.py         (Category-scope derivation, raw-pull pattern — logic re-used,
                                    not the file's own CSV outputs)
  - src/item_level_reconciliation.py / src/transferability_all_divisions.py (the Top-down share
                                    pattern: share computed from TRAIN data only) — pattern
                                    re-implemented here from scratch, this file is not imported
                                    or copied
  - src/build_inventory_dataset.py (the Cube_Backlog query pattern — reused, this file is not
                                    imported; the query is re-written here against the DB)
  - src/investigations/phaseD_check2_stock_value.py (the unit-cost methodology: cost/qty per
                                    row, median over the trailing 12 months anchored to the
                                    global max createDate, most-recent-transaction fallback) —
                                    reused for cross-phase consistency, per config's own
                                    unit_cost_basis_owner note. This is a pre-existing Phase D
                                    script, not a Phase E1 file, so reading/reusing it is
                                    explicitly in scope.

Every number this script produces is written to output/summary/phaseE1_validator_report.md
(this script's OWN report; the task's hard exclusion only bans READING existing phaseE1_* files,
not writing new ones).
"""
import logging
import math
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query
from models import combination_forecast
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_validator")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"
BACKLOG_TABLE = "[salewarehouse].[dbo].[Cube_Backlog]"
BACKLOG_SALE_COMPANIES = ["PEM", "CI"]

MA_WINDOWS = [3, 6, 12]  # config['moving_average_windows']
FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

DAYS_PER_MONTH = 30.44  # same conversion constant this project's own config assumptions use
    # (simulation_receipt_timing_assumption: "ceil(.../30.44)")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ==================================================================================================
# STEP 1 — independent re-derivation of the 128-item scope + overlap check
# ==================================================================================================

def derive_128_scope(config: dict) -> pd.DataFrame:
    """Re-derives the Fuse + Surge Arrester Category scope directly from the pricelist (NOT by
    reading config['adopted_scope_file']'s CSV — that file is itself produced by
    src/load_data_full.py, a pre-existing script, but re-deriving from the pricelist directly is
    more independent and doubles as a cross-check against the file the task names)."""
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    df = load_visible_product_rows(pricelist_path)
    scope = df[df["category"].isin(["Fuse", "Surge Arrester"])][["code", "category", "type"]].drop_duplicates()
    scope = scope.reset_index(drop=True)
    logger.info("Independently re-derived scope from pricelist: %d codes, %d Types, %d Categories.",
                len(scope), scope["type"].nunique(), scope["category"].nunique())

    # Cross-check against the file config['adopted_scope_file'] NAMES (reading the file's row
    # count only, as an integrity cross-check — not treated as authoritative; the pricelist read
    # above is the actual basis for every figure in this report).
    adopted_path = os.path.join(PROJECT_ROOT, config["adopted_scope_file"])
    if os.path.exists(adopted_path):
        adopted = pd.read_csv(adopted_path)
        adopted_codes = set(adopted["code"]) if "code" in adopted.columns else set()
        my_codes = set(scope["code"])
        logger.info("Cross-check vs config['adopted_scope_file'] (%s): file has %d rows, %d codes; "
                    "my independent pricelist derivation has %d codes; symmetric difference = %d.",
                    config["adopted_scope_file"], len(adopted), len(adopted_codes), len(my_codes),
                    len(adopted_codes ^ my_codes))
    return scope


def check_overlaps(config: dict, scope: pd.DataFrame) -> dict:
    scope_codes = set(scope["code"])
    excluded = set(config["excluded_item_codes"])
    placeholder = set(config["placeholder_item_codes"])
    excl_overlap = sorted(scope_codes & excluded)
    ph_overlap = sorted(scope_codes & placeholder)
    both = set(excl_overlap) & set(ph_overlap)
    logger.info("Overlap check: %d of %d excluded_item_codes fall inside the 128-item scope: %s",
                len(excl_overlap), len(excluded), excl_overlap)
    logger.info("Overlap check: %d of %d placeholder_item_codes fall inside the 128-item scope: %s",
                len(ph_overlap), len(placeholder), ph_overlap)
    if both:
        raise ValueError(f"{len(both)} codes appear in BOTH excluded_item_codes and "
                          f"placeholder_item_codes AND the scope — ambiguous, must be resolved by hand: {both}")
    n_112 = len(scope_codes) - len(excl_overlap) - len(ph_overlap)
    return {"excl_overlap": excl_overlap, "ph_overlap": ph_overlap,
            "n_scope": len(scope_codes), "n_112": n_112,
            "keep_codes": sorted(scope_codes - set(excl_overlap) - set(ph_overlap))}


# ==================================================================================================
# STEP 2 — fresh raw pull (independent of any Modeler intermediate) + monthly series (forecast_date-keyed)
# ==================================================================================================

def pull_raw_sales(config: dict, item_codes: list) -> tuple:
    """Fresh live pull, itemcode + revenue_type + status + createDate>=start only (no division
    filter — CONVENTIONS.md / config.yaml division_source correction). Returns (df, snapshot_pull_date)."""
    code_list = "','".join(sorted(item_codes))
    status_list = "','".join(config["status_basis"])
    sql = f"""
        SELECT itemcode, createDate, forecast_date, qty, sale, status
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{config["revenue_type"]}'
          AND status IN ('{status_list}')
          AND createDate >= '{config["date_range"]["start"]}'
    """
    df = run_query(sql)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    n0 = len(df)
    neg = df[(df["qty"] < 0)]
    if len(neg):
        raise ValueError(f"{len(neg)} rows with negative qty — must be reviewed, not silently dropped.")
    snapshot_pull_date = pd.Timestamp.now().normalize()
    logger.info("Fresh raw pull: %d rows, %d distinct items (of %d requested). snapshot_pull_date=%s "
                "(this validator's own live pull, frozen for this run).",
                n0, df["itemcode"].nunique(), len(item_codes), snapshot_pull_date.date())
    return df, snapshot_pull_date


def monthly_series_forecastdate(raw: pd.DataFrame) -> pd.DataFrame:
    """Monthly qty per item, keyed on forecast_date (adopted_series_key), Actual+MPS status,
    dropping null/negative-interval forecast_date rows (same rule as load_data_full.py's
    aggregate_monthly), zero-filled over each item's own observed month range."""
    d = raw.dropna(subset=["forecast_date"]).copy()
    d = d[d["forecast_date"] >= d["createDate"]]
    d["year_month"] = d["forecast_date"].dt.to_period("M")
    monthly = d.groupby(["itemcode", "year_month"], as_index=False)["qty"].sum()
    return monthly


def full_grid(monthly: pd.DataFrame, item_codes: list, min_month, max_month) -> pd.DataFrame:
    months = pd.period_range(min_month, max_month, freq="M")
    idx = pd.MultiIndex.from_product([item_codes, months], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(idx, fill_value=0.0).reset_index()
    return full


# ==================================================================================================
# FIGURE 1 — Min for the 3 focus items (empirical protection-period distribution)
# ==================================================================================================

def protection_period_months(config: dict) -> tuple:
    a = config["phase_e1_assumptions"]
    ds = a["default_scenario"]
    days = ds["procurement_lead_time_days"] + ds["assembly_time_days"] + a["review_interval_days_default"]
    months = math.ceil(days / DAYS_PER_MONTH)
    return days, months


def empirical_min(qty_series: np.ndarray, h_months: int, csl: float) -> dict:
    """Empirical protection-period cumulative-demand distribution: every overlapping h-month
    rolling sum of the item's own actual monthly history. Min = percentile(csl) of that
    distribution; safety stock = percentile - mean (config's safety_stock_convention)."""
    if len(qty_series) < h_months:
        return None
    rolling = np.array([qty_series[i:i + h_months].sum() for i in range(len(qty_series) - h_months + 1)])
    mean_ = float(rolling.mean())
    pct = float(np.percentile(rolling, csl * 100))
    ss = pct - mean_
    return {"n_windows": len(rolling), "mean_protection_demand": mean_,
            "percentile_value": pct, "safety_stock": ss, "min": mean_ + ss}


# ==================================================================================================
# FIGURE 2 — consumption for the 3 focus items over the protection-period horizon
# ==================================================================================================

def horizon_months(last_complete_month, n_months: int) -> list:
    """Horizon = the n_months immediately following the last COMPLETE historical month, i.e.
    Period 1 = the pull date's own (partial, in-progress) calendar month. This is deliberately
    the same month-indexing the Top-down forecast array itself uses (forecast index 0 = the
    month right after train_end_month=last_complete_month), so 'raw_forecast' and 'confirmed_qty'
    line up on the same calendar months without any separate re-indexing. Chosen over skipping to
    the month after the pull date's month because the task instruction reads the horizon as
    starting 'right after the snapshot pull date' (i.e. from now onward), not from the next full
    calendar month — and because nearly all already-confirmed MPS/backlog demand for these items
    sits within days of the pull date (median 6-day customer notice, STATUS.md), which would
    otherwise fall outside Period 1 entirely, an artifact of month-boundary bookkeeping rather
    than a real gap in confirmed demand. STATED, not the only defensible choice."""
    start = last_complete_month + 1
    return [start + i for i in range(n_months)]


def query_mps_future(config: dict, item_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT itemcode, forecast_date, qty, status
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{config["revenue_type"]}'
          AND status = 'MPS'
    """
    df = run_query(sql)
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    return df.dropna(subset=["forecast_date"])


def query_backlog_for_items(item_codes: list) -> pd.DataFrame:
    """Same query pattern as src/build_inventory_dataset.py's query_backlog: sale_company IN
    ('PEM','CI'), no status filter (every row already outstanding)."""
    code_list = "','".join(sorted(item_codes))
    sql = f"""
        SELECT docID, itemcode, quantity, status, sale_company, deliverydate, plan_deliverydate
        FROM {BACKLOG_TABLE}
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    df["sale_company"] = df["sale_company"].astype(str).str.strip()
    df = df[df["sale_company"].isin(BACKLOG_SALE_COMPANIES)].copy()
    df["deliverydate"] = pd.to_datetime(df["deliverydate"], errors="coerce")
    df["plan_deliverydate"] = pd.to_datetime(df["plan_deliverydate"], errors="coerce")
    df["effective_date"] = df["deliverydate"].fillna(df["plan_deliverydate"])
    return df


def build_topdown_item_forecast(item_code: str, item_type: str, monthly_full: pd.DataFrame,
                                 type_series_map: dict, train_end_month, horizon: int) -> np.ndarray:
    """Top-down: Type-level combination_forecast (fit on data through train_end_month, INCLUSIVE),
    allocated to the item by its own share of the Type total over that SAME training window
    (share computed from train data only — the leakage-free pattern in
    src/item_level_reconciliation.py / src/transferability_all_divisions.py)."""
    type_qty = type_series_map[item_type]
    type_qty = type_qty[type_qty["year_month"] <= train_end_month].sort_values("year_month")
    train = type_qty["qty"].to_numpy(dtype=float)
    type_fc = np.clip(combination_forecast(train, horizon, MA_WINDOWS), 0, None)

    item_hist = monthly_full[(monthly_full["itemcode"] == item_code) &
                              (monthly_full["year_month"] <= train_end_month)]
    item_total = item_hist["qty"].sum()
    type_total = train.sum()
    share = item_total / type_total if type_total > 0 else np.nan
    return type_fc * share, share


# ==================================================================================================
# FIGURE 3 — FG-stock-policy-supported item set, Min/Max, scenario stock value
# ==================================================================================================

def classify_adi_cv2(qty: np.ndarray) -> tuple:
    """Standard Syntetos-Boylan-Croston (2005) thresholds: ADI (average inter-demand interval)
    and CV^2 (squared coefficient of variation of non-zero demand sizes)."""
    nonzero_idx = np.flatnonzero(qty > 0)
    if len(nonzero_idx) < 2:
        return np.nan, np.nan, "insufficient_nonzero_periods"
    intervals = np.diff(nonzero_idx)
    adi = float(intervals.mean()) if len(intervals) else np.nan
    sizes = qty[nonzero_idx]
    cv2 = float((sizes.std(ddof=0) / sizes.mean()) ** 2) if sizes.mean() > 0 else np.nan
    if np.isnan(adi) or np.isnan(cv2):
        return adi, cv2, "insufficient_data"
    if adi < 1.32 and cv2 < 0.49:
        cls = "Smooth"
    elif adi >= 1.32 and cv2 < 0.49:
        cls = "Intermittent"
    elif adi < 1.32 and cv2 >= 0.49:
        cls = "Erratic"
    else:
        cls = "Lumpy"
    return adi, cv2, cls


def query_unit_cost(item_codes: list, window_months: int = 12) -> pd.DataFrame:
    """Reuses src/investigations/phaseD_check2_stock_value.py's exact methodology: unit_cost =
    cost/qty per row; primary = median over the trailing `window_months` anchored to the global
    max createDate across the pulled rows, with most-recent-transaction fallback."""
    code_list = "','".join(sorted(item_codes))
    sql = f"SELECT itemcode, qty, cost, createDate FROM {SALE_TABLE} WHERE itemcode IN ('{code_list}')"
    df = run_query(sql)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df = df[(df["qty"].notna()) & (df["qty"] != 0) & (df["cost"].notna())].copy()
    df["unit_cost"] = df["cost"] / df["qty"]

    global_max = df["createDate"].max()
    window_start = global_max - pd.DateOffset(months=window_months)

    max_date_per_item = df.groupby("itemcode")["createDate"].transform("max")
    recent = df[df["createDate"] == max_date_per_item].groupby("itemcode", as_index=False)["unit_cost"].mean() \
        .rename(columns={"unit_cost": "most_recent_unit_cost"})

    in_window = df[df["createDate"] >= window_start]
    median12 = in_window.groupby("itemcode", as_index=False)["unit_cost"].median() \
        .rename(columns={"unit_cost": "median_unit_cost_12mo"})

    out = pd.DataFrame({"itemcode": sorted(item_codes)}).merge(median12, on="itemcode", how="left") \
        .merge(recent, on="itemcode", how="left")
    has_median = out["median_unit_cost_12mo"].notna()
    has_recent = out["most_recent_unit_cost"].notna()
    out["primary_unit_cost"] = np.where(has_median, out["median_unit_cost_12mo"], out["most_recent_unit_cost"])
    out["primary_basis"] = np.select(
        [has_median, (~has_median) & has_recent],
        ["median_last_12mo", "most_recent_transaction (FALLBACK)"],
        default="NO_COST_RECORD")
    return out


def query_sellable_onhand(item_codes: list, sellable_codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(item_codes))
    wh_list = "','".join(sellable_codes)
    sql = f"""
        SELECT itemcode, warehouse, stock
        FROM {INV_TABLE}
        WHERE itemcode IN ('{code_list}') AND LTRIM(RTRIM(warehouse)) IN ('{wh_list}')
    """
    df = run_query(sql)
    per_item = df.groupby("itemcode", as_index=False)["stock"].sum().rename(columns={"stock": "sellable_onhand"})
    out = pd.DataFrame({"itemcode": sorted(item_codes)}).merge(per_item, on="itemcode", how="left")
    out["sellable_onhand"] = out["sellable_onhand"].fillna(0.0)
    return out


# ==================================================================================================
# FIGURE 4 — historical simulation, fill rate
# ==================================================================================================

def simulate_item(qty_hist: np.ndarray, max_qty: float, lead_months: int) -> dict:
    """Order-up-to-Max (base-stock) periodic-review simulation, per the config's own
    simulation_initial_stock / receipt_timing / fulfilment_sequence assumptions (see report for
    the exact statements). Returns per-item totals: demand, fulfilled, stockout_months."""
    n = len(qty_hist)
    on_hand = max_qty
    backorder = 0.0
    pipeline = {}  # arrival_month_idx -> qty
    total_demand = 0.0
    total_fulfilled = 0.0
    stockout_months = 0

    for m in range(n):
        on_hand += pipeline.pop(m, 0.0)  # receipt arrives FIRST

        pay_backorder = min(on_hand, backorder)
        on_hand -= pay_backorder
        backorder -= pay_backorder

        demand_m = float(qty_hist[m])
        served = min(on_hand, demand_m)
        on_hand -= served
        shortfall = demand_m - served
        backorder += shortfall
        if shortfall > 1e-9:
            stockout_months += 1

        total_demand += demand_m
        total_fulfilled += served

        outstanding_pipeline = sum(pipeline.values())
        order_qty = max(0.0, max_qty - (on_hand + outstanding_pipeline))
        if order_qty > 0:
            pipeline[m + lead_months] = pipeline.get(m + lead_months, 0.0) + order_qty

    return {"n_months": n, "total_demand": total_demand, "total_fulfilled": total_fulfilled,
            "stockout_months": stockout_months}


if __name__ == "__main__":
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    config = load_config()

    print("=" * 100)
    print("STEP 1 — independent 128-item scope + overlap check")
    print("=" * 100)
    scope = derive_128_scope(config)
    overlap = check_overlaps(config, scope)
    print(f"128-item scope (independently re-derived): {overlap['n_scope']} codes")
    print(f"excluded_item_codes overlap: {len(overlap['excl_overlap'])} -> {overlap['excl_overlap']}")
    print(f"placeholder_item_codes overlap: {len(overlap['ph_overlap'])} -> {overlap['ph_overlap']}")
    print(f"Remaining after removing overlaps: {overlap['n_112']} (task's own text expects 112)")

    print("\n" + "=" * 100)
    print("STEP 2 — fresh raw pull + monthly series")
    print("=" * 100)
    all_128 = sorted(scope["code"].unique())
    raw, snapshot_pull_date = pull_raw_sales(config, all_128)
    monthly = monthly_series_forecastdate(raw)
    min_month = monthly["year_month"].min()
    # last COMPLETE month before the pull date (exclude a partial trailing month)
    last_complete_month = pd.Period(snapshot_pull_date, freq="M") - 1
    monthly_full = full_grid(monthly, all_128, min_month, last_complete_month)
    monthly_full = monthly_full.merge(scope.rename(columns={"code": "itemcode"}), on="itemcode", how="left")
    print(f"Monthly grid: {all_128.__len__()} items x {monthly_full['year_month'].nunique()} months "
          f"({min_month} to {last_complete_month}). snapshot_pull_date={snapshot_pull_date.date()}")

    days, h_months = protection_period_months(config)
    print(f"\nProtection period: lead {config['phase_e1_assumptions']['default_scenario']['procurement_lead_time_days']}"
          f" + assembly {config['phase_e1_assumptions']['default_scenario']['assembly_time_days']}"
          f" + review {config['phase_e1_assumptions']['review_interval_days_default']} = {days} days "
          f"-> ceil({days}/{DAYS_PER_MONTH}) = {h_months} months")

    print("\n" + "=" * 100)
    print("FIGURE 1 — Min for the 3 focus items")
    print("=" * 100)
    csl = config["phase_e1_assumptions"]["default_scenario"]["cycle_service_level"]
    fig1_rows = []
    for item in FOCUS_ITEMS:
        g = monthly_full[monthly_full["itemcode"] == item].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        res = empirical_min(qty, h_months, csl)
        res["itemcode"] = item
        res["n_months_history"] = len(qty)
        fig1_rows.append(res)
        print(f"{item}: n_months={len(qty)}, n_windows={res['n_windows']}, "
              f"mean={res['mean_protection_demand']:.2f}, p{csl*100:.0f}={res['percentile_value']:.2f}, "
              f"safety_stock={res['safety_stock']:.2f}, Min={res['min']:.2f}")
    fig1_df = pd.DataFrame(fig1_rows)
    fig1_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig1_min.csv"), index=False)

    print("\n" + "=" * 100)
    print("FIGURE 2 — consumption for the 3 focus items over the horizon")
    print("=" * 100)
    horizon = horizon_months(last_complete_month, h_months)
    print(f"Horizon months (Period 1 = the pull date's own in-progress month, right after the "
          f"last COMPLETE historical month {last_complete_month}; pull date={snapshot_pull_date.date()}): {horizon}")

    mps_future = query_mps_future(config, FOCUS_ITEMS)
    mps_future["year_month"] = mps_future["forecast_date"].dt.to_period("M")
    backlog = query_backlog_for_items(FOCUS_ITEMS)
    overdue = backlog[backlog["effective_date"].notna() & (backlog["effective_date"] < snapshot_pull_date)]
    future_backlog = backlog[backlog["effective_date"].notna() & (backlog["effective_date"] >= snapshot_pull_date)]
    print(f"NOTE (stated scope decision, per config['forecast_consumption_logic'] / "
          f"['backlog_vs_mps_double_count_note']): Cube_Backlog rows whose effective date is "
          f"already PAST the pull date ({snapshot_pull_date.date()}) count as immediate Period-1 "
          f"demand. Cube_Backlog rows with a FUTURE effective date are NOT added on top of MPS for "
          f"future periods (no verified shared key between Cube_Backlog and cube_Sale_APD exists to "
          f"rule out double counting — {len(future_backlog)} such future-dated backlog rows exist "
          f"for the 3 focus items and are excluded from the future-period figures below on that "
          f"stated basis, an ASSUMPTION, not a proven de-duplication).")

    type_series_map = {}
    for typ, g in monthly_full.groupby("type"):
        keep_types_items = set(overlap["keep_codes"])
        gg = g[g["itemcode"].isin(keep_types_items)]
        type_series_map[typ] = gg.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")

    item_type_map = dict(zip(scope["code"], scope["type"]))
    fig2_rows = []
    for item in FOCUS_ITEMS:
        item_type = item_type_map[item]
        fc, share = build_topdown_item_forecast(item, item_type, monthly_full, type_series_map,
                                                 last_complete_month, h_months)
        for i, per in enumerate(horizon):
            confirmed_mps = mps_future[(mps_future["itemcode"] == item) &
                                        (mps_future["year_month"] == per)]["qty"].sum()
            confirmed = confirmed_mps
            if i == 0:
                overdue_qty = overdue[overdue["itemcode"] == item]["quantity"].sum()
                confirmed = confirmed + overdue_qty
            forecast_val = fc[i]
            pct = 100 * confirmed / forecast_val if forecast_val > 0 else np.nan
            fig2_rows.append({"itemcode": item, "period": i + 1, "year_month": str(per),
                               "confirmed_qty": confirmed, "raw_forecast": forecast_val,
                               "pct_of_forecast_consumed": pct, "topdown_share": share})
            print(f"{item} period {i+1} ({per}): confirmed={confirmed:.1f}, forecast={forecast_val:.2f}, "
                  f"%consumed={pct:.1f}%" if pd.notna(pct) else
                  f"{item} period {i+1} ({per}): confirmed={confirmed:.1f}, forecast={forecast_val:.2f}, %consumed=N/A")
    fig2_df = pd.DataFrame(fig2_rows)
    fig2_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig2_consumption.csv"), index=False)
    fig2_total = fig2_df.groupby("itemcode", as_index=False)[["confirmed_qty", "raw_forecast"]].sum()
    fig2_total["pct_of_forecast_consumed_total"] = 100 * fig2_total["confirmed_qty"] / fig2_total["raw_forecast"]
    print("\nTotals across the whole horizon, per item:")
    print(fig2_total.to_string(index=False))
    grand_confirmed = float(fig2_df["confirmed_qty"].sum())
    grand_forecast = float(fig2_df["raw_forecast"].sum())
    print(f"\nGRAND TOTAL (3 focus items, whole horizon): confirmed={grand_confirmed:.1f}, "
          f"forecast={grand_forecast:.1f}, pct={100*grand_confirmed/grand_forecast:.1f}%")

    print("\n" + "=" * 100)
    print("FIGURE 3 — FG-stock-policy-supported set, Min/Max, scenario stock value")
    print("=" * 100)
    keep_codes = overlap["keep_codes"]
    assert len(keep_codes) == overlap["n_112"]
    fig3_rows = []
    for code in keep_codes:
        g = monthly_full[monthly_full["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        adi, cv2, cls = classify_adi_cv2(qty)
        mean_monthly = float(qty.mean())
        n_months = len(qty)
        n_nonzero = int((qty > 0).sum())
        order_freq = n_nonzero / n_months if n_months else np.nan
        fig3_rows.append({"itemcode": code, "type": item_type_map[code], "adi": adi, "cv2": cv2,
                           "demand_class": cls, "mean_monthly_qty": mean_monthly,
                           "order_frequency": order_freq, "n_nonzero_months": n_nonzero,
                           "n_months": n_months})
    fig3_df = pd.DataFrame(fig3_rows)

    unit_cost_df = query_unit_cost(keep_codes, config["phase_e1_assumptions"]["unit_cost_median_window_months"])
    fig3_df = fig3_df.merge(unit_cost_df, on="itemcode", how="left")
    fig3_df["annual_value"] = fig3_df["mean_monthly_qty"] * 12 * fig3_df["primary_unit_cost"].fillna(0.0)

    median_value = fig3_df["annual_value"].median()
    median_freq = fig3_df["order_frequency"].median()
    fig3_df["low_value"] = fig3_df["annual_value"] < median_value
    fig3_df["low_frequency"] = fig3_df["order_frequency"] < median_freq
    fig3_df["fg_stock_supported"] = ~(fig3_df["low_value"] & fig3_df["low_frequency"])
    print(f"Median annual_value across the {len(fig3_df)}-item set: {median_value:,.2f} THB")
    print(f"Median order_frequency: {median_freq:.3f}")
    print(f"METHOD (stated, independent judgment call): an item is EXCLUDED from the FG-stock-"
          f"supported set only if it is BOTH low-value (annual_value < median) AND low-frequency "
          f"(order_frequency < median) — i.e. only the bottom-value/bottom-frequency quadrant is "
          f"excluded, since the 45-60 day procurement lead time so greatly exceeds the 6-day median "
          f"customer order notice (STATUS.md Business Findings) that FG stock is needed to meet "
          f"realistic delivery expectations for every item NOT in that quadrant.")
    n_fg = int(fig3_df["fg_stock_supported"].sum())
    print(f"Resulting FG-stock-supported set: {n_fg} of {len(fig3_df)} items.")
    fig3_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig3_fg_classification.csv"), index=False)

    fg_set = fig3_df[fig3_df["fg_stock_supported"]].copy()
    lead = config["phase_e1_assumptions"]["default_scenario"]["procurement_lead_time_days"]
    review = config["phase_e1_assumptions"]["review_interval_days_default"]
    replen_rows = []
    for _, row in fg_set.iterrows():
        code = row["itemcode"]
        g = monthly_full[monthly_full["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        res = empirical_min(qty, h_months, csl)
        if res is None:
            continue
        replen_qty = row["mean_monthly_qty"] * (review / DAYS_PER_MONTH)
        max_qty = res["min"] + replen_qty
        replen_rows.append({"itemcode": code, "min": res["min"], "replen_qty": replen_qty,
                             "max": max_qty, "unit_cost": row["primary_unit_cost"],
                             "cost_basis": row["primary_basis"]})
    minmax_df = pd.DataFrame(replen_rows)
    minmax_df["max_value"] = minmax_df["max"] * minmax_df["unit_cost"].fillna(0.0)
    minmax_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig3_minmax.csv"), index=False)

    n_priced = int(minmax_df["unit_cost"].notna().sum())
    total_stock_value = float(minmax_df.loc[minmax_df["unit_cost"].notna(), "max_value"].sum())
    print(f"\nItems with a Min/Max computed: {len(minmax_df)} of {n_fg} FG-stock-supported items "
          f"(some may lack {h_months}-month history for the empirical distribution).")
    print(f"Items with a usable unit cost: {n_priced} of {len(minmax_df)}")
    print(f"PRIMARY: total scenario stock value (sum of Max_qty x unit_cost, priced items only): "
          f"THB {total_stock_value:,.2f}")

    sellable = query_sellable_onhand(fg_set["itemcode"].tolist(),
                                      config["phase_e1_assumptions"]["sellable_warehouse_codes"])
    sellable = sellable.merge(minmax_df[["itemcode", "unit_cost"]], on="itemcode", how="left")
    sellable["onhand_value"] = sellable["sellable_onhand"] * sellable["unit_cost"].fillna(0.0)
    secondary_value = float(sellable.loc[sellable["unit_cost"].notna(), "onhand_value"].sum())
    print(f"SECONDARY (alternate interpretation, NOT primary): value of CURRENT sellable on-hand "
          f"stock (FG01/FG21/WH21) for the same {n_fg}-item set: THB {secondary_value:,.2f}")

    print("\n" + "=" * 100)
    print("FIGURE 4 — historical simulation, fill rate")
    print("=" * 100)
    lead_months = math.ceil((lead + config["phase_e1_assumptions"]["default_scenario"]["assembly_time_days"])
                             / DAYS_PER_MONTH)
    print(f"lead_months (lead+assembly only, per simulation_receipt_timing_assumption) = "
          f"ceil(({lead}+{config['phase_e1_assumptions']['default_scenario']['assembly_time_days']})/{DAYS_PER_MONTH}) = {lead_months}")

    sim_rows = []
    total_demand_all, total_fulfilled_all, total_stockout_months = 0.0, 0.0, 0
    for _, row in minmax_df.iterrows():
        code = row["itemcode"]
        g = monthly_full[monthly_full["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        max_qty = row["max"]
        res = simulate_item(qty, max_qty, lead_months)
        res["itemcode"] = code
        sim_rows.append(res)
        total_demand_all += res["total_demand"]
        total_fulfilled_all += res["total_fulfilled"]
        total_stockout_months += res["stockout_months"]
    sim_df = pd.DataFrame(sim_rows)
    sim_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_validator_fig4_simulation.csv"), index=False)

    fill_rate = 100 * total_fulfilled_all / total_demand_all if total_demand_all else np.nan
    print(f"Simulated {len(sim_df)} items, {sim_df['n_months'].iloc[0] if len(sim_df) else 0} months each "
          f"({min_month} to {last_complete_month}).")
    print(f"AGGREGATE unit fill rate (pooled across all items/months): {fill_rate:.2f}%")
    print(f"Total item-months with a stockout: {total_stockout_months} of "
          f"{int(sim_df['n_months'].sum())} item-months")

    print("\nDONE. CSVs written to output/summary/phaseE1_validator_fig{1,2,3,4}_*.csv")
