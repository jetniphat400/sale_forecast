"""Phase C step 2: rebuilds the forward-test log for the FULL 335-item, 5-division scope
(output/summary/phaseC_step2_scope_335items.csv), superseding forward_test_log_v2.csv (128 items,
PEM101 sheet Fuse+Surge Category only — archived, see output/summary/archive/).

SCHEMA: extends forward_test_log_v2.csv's schema with one added column, `division` (inserted
after itemcode) — necessary now, not optional, because Category/Type names collide across
divisions (documented repeatedly in STATUS.md, e.g. "Fuse" exists under many divisions for
unrelated products): without a division column, a Type-level or Category-level row's identity
would be ambiguous the moment two divisions share a name. Every other column keeps its v2 meaning
unchanged. The same consistency-check fields (config_version, date_key, scope_hash, scope_n_items)
are recomputed for the new 335-item scope and written into a new metadata file, so
src/score_forward_test_v2.py's verify_consistency()-style check still has something to check
against once a scoring script is built for this log (not done in this task).

METHOD — reused, not reinvented: Type/Category-level rows use plain Combination
(src/models.py combination_forecast) fitted on the Type's/Category's own division-qualified
monthly qty series; Item-level rows use Top-down allocation
(src/item_level_reconciliation.forecast_all_approaches's "Top-down" branch, unmodified, called
with division-qualified Type keys so allocation never mixes two divisions' same-named Types).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import TOTAL_MONTHS
from forward_test import config_version
from forward_test_common import compute_scope_hash, save_metadata
from item_level_reconciliation import forecast_all_approaches
from leakage_guard import check_window_closed, load_min_margin_days
from models import combination_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("forward_test_all_divisions")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions.csv")
METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions_metadata.json")

COLUMNS = ["itemcode", "division", "level", "category", "type", "forecast_run_date", "data_cutoff_date",
           "fit_last_month", "model", "config_version", "date_key", "scope_hash", "scope_n_items",
           "horizon", "target_month", "forecast_qty", "actual_qty"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_item_series_div(monthly: pd.DataFrame, scope: pd.DataFrame, n_months: int) -> dict:
    """{code: (qty_array, type_key, category)}, type_key = 'DIVISION::type'."""
    out = {}
    for _, row in scope.iterrows():
        code, div, cat, typ = row["code"], row["division"], row["category"], row["type"]
        g = monthly[monthly["itemcode"] == code].sort_values("year_month")
        qty = g["qty"].to_numpy(dtype=float)
        if len(qty) == n_months:
            out[code] = (qty, f"{div}::{typ}", cat)
    return out


def build_type_series_div(monthly: pd.DataFrame, n_months: int) -> dict:
    out = {}
    for (div, typ), g in monthly.groupby(["division", "type"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        if len(qty) == n_months:
            out[f"{div}::{typ}"] = qty
    return out


def build_category_series_div(monthly: pd.DataFrame, n_months: int) -> dict:
    out = {}
    for (div, cat), g in monthly.groupby(["division", "category"]):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        if len(qty) == n_months:
            out[f"{div}::{cat}"] = qty
    return out


if __name__ == "__main__":
    config = load_config()
    date_key_cfg = config["adopted_series_key"]
    date_key = "forecastDate"  # this pipeline is forecast_date-keyed only; must match config's adopted key
    if date_key_cfg != date_key:
        raise ValueError(f"config.yaml adopted_series_key={date_key_cfg!r} but this script only builds "
                          f"a {date_key!r}-keyed log — mismatch must be resolved before proceeding.")
    approach_label = config["adopted_item_level_approach"]
    horizon = config["backtest_holdout_months"]
    ma_windows = config["moving_average_windows"]
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly_path = os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv")
    monthly = pd.read_csv(monthly_path)

    pull_date = monthly["snapshot_pull_date"].iloc[0]
    months = sorted(monthly["year_month"].unique())
    n_fit_months = len(months)
    if n_fit_months != TOTAL_MONTHS:
        raise ValueError(f"{monthly_path} has {n_fit_months} months, expected {TOTAL_MONTHS}.")
    fit_first_month, fit_last_month = months[0], months[-1]

    check_window_closed(fit_last_month, pull_date, min_margin_days)
    actual_margin_days = (pd.Timestamp(pull_date).normalize() - pd.Period(fit_last_month, freq="M").end_time.normalize()).days
    logger.info("Leakage guard OK: fitted window ends %s, pull_date=%s, margin=%d days (>= required %d)",
                fit_last_month, pull_date, actual_margin_days, min_margin_days)

    run_date = pd.Timestamp.now().normalize().date().isoformat()
    data_cutoff_date = pd.Timestamp(pull_date).date().isoformat()
    cfg_ver = config_version()
    scope_codes = sorted(scope["code"].unique())
    scope_hash = compute_scope_hash(scope_codes)
    n_scope_items = len(scope_codes)
    target_months = [str(pd.Period(fit_last_month, freq="M") + i) for i in range(1, horizon + 1)]

    logger.info("date_key=%s, approach=%s, %d scope items across %d divisions, fitted %s to %s (%d months), "
                "forecasting %d months ahead: %s", date_key, approach_label, n_scope_items,
                scope["division"].nunique(), fit_first_month, fit_last_month, n_fit_months, horizon, target_months)

    item_series = build_item_series_div(monthly, scope, n_fit_months)
    type_series = build_type_series_div(monthly, n_fit_months)
    category_series = build_category_series_div(monthly, n_fit_months)
    logger.info("%d of %d scope items have full %d-month history; %d division-qualified Types, "
                "%d division-qualified Categories", len(item_series), n_scope_items, n_fit_months,
                len(type_series), len(category_series))

    no_history_codes = sorted(set(scope["code"]) - set(item_series.keys()))
    if len(no_history_codes):
        logger.warning("%d of %d scope codes have < %d months history (should be 0 for 'forecast'-status "
                        "codes, which are defined as having some history) — investigate before trusting "
                        "their forecast_qty=0 rows: %s", len(no_history_codes), n_scope_items, n_fit_months,
                        no_history_codes)

    approaches = forecast_all_approaches(item_series, type_series, n_fit_months, horizon)
    topdown_history = approaches["Top-down"]
    topdown_no_history = {code: np.zeros(horizon) for code in no_history_codes}
    topdown_all = {**topdown_history, **topdown_no_history}
    if len(topdown_all) != n_scope_items:
        raise ValueError(f"Top-down forecast covers {len(topdown_all)} items, expected {n_scope_items}.")
    if any((fc < 0).any() for fc in topdown_all.values()):
        raise ValueError("Negative forecast_qty produced by Top-down allocation.")

    type_forecast = {typ: np.clip(combination_forecast(qty[:n_fit_months], horizon, ma_windows), 0, None)
                      for typ, qty in type_series.items()}
    category_forecast = {cat: np.clip(combination_forecast(qty[:n_fit_months], horizon, ma_windows), 0, None)
                          for cat, qty in category_series.items()}

    item_to_info = scope.set_index("code")[["division", "category", "type"]].to_dict("index")

    def base_row(itemcode, division, level, category, type_):
        return {"itemcode": itemcode, "division": division, "level": level, "category": category, "type": type_,
                "forecast_run_date": run_date, "data_cutoff_date": data_cutoff_date,
                "fit_last_month": fit_last_month, "config_version": cfg_ver, "date_key": date_key,
                "scope_hash": scope_hash, "scope_n_items": n_scope_items}

    records = []
    for item, fc in topdown_all.items():
        info = item_to_info[item]
        row = base_row(item, info["division"], "Item", info["category"], info["type"])
        row["model"] = f"{approach_label}_Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm, "forecast_qty": round(float(val), 4), "actual_qty": ""})

    for type_key, fc in type_forecast.items():
        div, typ = type_key.split("::", 1)
        cat = scope[(scope["division"] == div) & (scope["type"] == typ)]["category"].iloc[0]
        row = base_row(typ, div, "Type", cat, typ)
        row["model"] = "Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm, "forecast_qty": round(float(val), 4), "actual_qty": ""})

    for cat_key, fc in category_forecast.items():
        div, cat = cat_key.split("::", 1)
        row = base_row(cat, div, "Category", cat, "")
        row["model"] = "Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm, "forecast_qty": round(float(val), 4), "actual_qty": ""})

    log_df = pd.DataFrame(records, columns=COLUMNS)
    if (log_df["forecast_qty"] < 0).any():
        raise ValueError("Negative forecast_qty in final log.")
    log_df.to_csv(LOG_PATH, index=False)

    n_item_rows = len(topdown_all) * horizon
    n_type_rows = len(type_forecast) * horizon
    n_cat_rows = len(category_forecast) * horizon
    logger.info("Wrote %s: %d rows (Item %d, Type %d, Category %d)", LOG_PATH, len(log_df),
                n_item_rows, n_type_rows, n_cat_rows)

    metadata = {
        "log_file": os.path.relpath(LOG_PATH, PROJECT_ROOT).replace("\\", "/"),
        "generated_by_script": "src/forward_test_all_divisions.py",
        "forecast_run_date": run_date, "config_version": cfg_ver, "date_key": date_key,
        "item_level_approach": approach_label, "scope_hash": scope_hash, "scope_n_items": n_scope_items,
        "scope_source_file": "output/summary/phaseC_step2_scope_335items.csv",
        "monthly_series_source_file": os.path.relpath(monthly_path, PROJECT_ROOT).replace("\\", "/"),
        "monthly_series_snapshot_pull_date": str(pull_date),
        "fit_first_month": fit_first_month, "fit_last_month": fit_last_month, "fit_n_months": n_fit_months,
        "horizon_months": horizon, "target_months": target_months,
        "leakage_guard_min_margin_days": min_margin_days, "leakage_guard_actual_margin_days": actual_margin_days,
        "n_item_rows": n_item_rows, "n_type_rows": n_type_rows, "n_category_rows": n_cat_rows,
        "n_total_rows": len(log_df), "n_items_with_history": len(topdown_history),
        "n_items_no_history_zero_forecast": len(topdown_no_history),
        "divisions": sorted(scope["division"].unique().tolist()),
        "supersedes": "output/summary/forward_test_log_v2.csv (128-item PEM101-sheet Fuse+Surge scope, "
                       "archived to output/summary/archive/ — see the README there)",
    }
    save_metadata(METADATA_PATH, metadata)

    print(f"\nForward-test log (all divisions) written: {LOG_PATH}")
    print(f"Rows: {len(log_df)} ({n_item_rows} Item + {n_type_rows} Type + {n_cat_rows} Category)")
    print(f"Scope: {n_scope_items} items across {scope['division'].nunique()} divisions")
    print(f"Fitted window: {fit_first_month} to {fit_last_month} ({n_fit_months} months, forecast_date-keyed, "
          f"pull_date={pull_date})")
    print(f"Target months (horizon 1-{horizon}): {target_months}")
    print("actual_qty is empty for all rows -- these are real future periods, not fabricated.")
    print(f"Metadata: {METADATA_PATH}")
