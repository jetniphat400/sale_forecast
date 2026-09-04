"""Forward-test log v2: rebuilds output/summary/forward_test_log_v2.csv for the project's
CURRENT configuration -- the 128-item Category scope (Fuse + Surge Arrester,
output/summary/part1_category_scope_all_codes.csv), the adopted Top-down combination
forecasting approach (STATUS.md Phase B3; config.yaml: adopted_item_level_approach), on the
forecast_date-keyed monthly series (STATUS.md Phase B1; config.yaml: adopted_series_key) --
superseding output/summary/forward_test_log.csv (58 items, 6 individual models, createDate-keyed;
archived under output/summary/archive/, see the README there for why it no longer applies).

WHY FORWARD TESTING MATTERS -- unchanged from src/forward_test.py's original reasoning (read
that file's own header docstring for the full argument): every other evaluation method in this
project scores a model against months that already existed in the data before the model was
chosen. Forward testing records a forecast for a period that has not happened yet and waits for
real, un-seen future actuals -- the only evaluation immune to hindsight.

METHOD -- reused, not reinvented, from src/item_level_reconciliation.py (Phase B3):
  - Type-level and Category-level rows: the plain Combination forecast (equal-weight mean of
    Naive/MA3/MA6/MA12/Croston/SBA, src/models.py combination_forecast), fitted directly on the
    Type's / Category's own monthly qty series.
  - Item-level rows: Top-down allocation -- item_level_reconciliation.forecast_all_approaches's
    "Top-down" branch, unmodified, called on the 113 of 128 items that have at least one row of
    sales history. This allocates each Type's Combination forecast to its member items by each
    item's historical qty SHARE of the Type over the fitting window.
  - The 15 of 128 scope items with ZERO sales history anywhere (has_any_history=False in
    part1_category_scope_all_codes.csv) cannot have a historical share computed by the reused
    function (there is nothing to divide). Mathematically, a zero-history item's share of its
    Type's history is exactly 0 (0 sales / a positive Type total), so its Top-down allocation is
    exactly 0 for every horizon -- not a placeholder or a guess, the literal result of applying
    the SAME formula with a genuinely-zero numerator. Computed directly here (np.zeros(horizon))
    rather than routed through the reused function, only to avoid feeding an all-zero training
    array into Croston/SBA (whose behaviour on an all-zero series is undefined/untested
    elsewhere in this project) for a result that is 0 either way.

FITTING WINDOW -- uses the EXISTING frozen
output/data/processed_full_category_sales_monthly_forecastDate.csv (snapshot_pull_date
2026-09-02 15:52:39, months 2024-01 through 2026-07), NOT a fresh live pull, even though the
database is reachable and a fresh pull today (2026-09-04) would have a true max createDate a few
days later. Reasoning (stated explicitly, not a default): this project's leakage guard
(src/leakage_guard.py, config.yaml leakage_guard.min_margin_days=30) requires at least 30 days
between a fitted window's last month-end and the data's pull date, because forecast_date-keyed
rows for an already-elapsed calendar month can still be entered/revised for up to that margin
after the month closes (Phase A). The existing 2026-09-02 pull already sits 33 days past its
last fitted month's end (2026-07-31) -- safely past the 30-day margin, reconfirmed below by
calling leakage_guard.check_window_closed directly rather than assuming it still holds. A fresh
pull today would only widen that margin to 35 days; it would NOT unlock August 2026 as a
fittable month, since August's month-end (2026-08-31) is only 4 days behind today (2026-09-04),
far short of the 30-day margin. Re-pulling therefore buys no additional fittable history while
introducing a second, undocumented pull-timing baseline alongside the one every other Phase-B/
Task-2/Task-3 output in this project was already cross-checked against -- so the existing frozen
pull is reused, and this reasoning is written here explicitly per this task's instruction to
state which data cutoff was used and why.

HORIZON -- 6 months (config.yaml backtest_holdout_months), starting the month AFTER the fitted
window's last month (2026-07), i.e. target months 2026-08 through 2027-01.

SCHEMA (output/summary/forward_test_log_v2.csv) -- extends src/forward_test.py's original
columns (itemcode, forecast_run_date, data_cutoff_date, model, config_version, horizon,
target_month, forecast_qty, actual_qty) with:
  level             - "Item", "Type", or "Category". Distinguishes what `itemcode` holds below.
  itemcode          - for level="Item", a genuine item code; for level="Type", the Type name;
                      for level="Category", the Category name. Kept as one column (not split
                      into separate identifier columns per level) to preserve the original
                      schema's shape, per this task's instruction -- `level` disambiguates it.
  category          - the row's Category (always populated: the item's own Category for Item
                      rows, the parent Category for Type rows, itself for Category rows).
  type              - the row's Type (populated for Item/Type rows; empty for Category rows,
                      which have no single Type).
  fit_last_month    - the last calendar month actually used to fit (2026-07) -- distinct from
                      data_cutoff_date (see below), added because the fitted window's last
                      month is what determines target_month/horizon, not the raw pull's max date.
  data_cutoff_date  - kept with its original meaning (src/forward_test.py's docstring): the true
                      cutoff of the underlying data pull used (here, the frozen pull's
                      snapshot_pull_date's date part, 2026-09-02 -- see FITTING WINDOW above for
                      why this pull was reused rather than a fresh one).
  date_key          - the series key this log is built on ("forecastDate") -- lets the
                      consistency check (src/score_forward_test_v2.py) verify a log matches
                      config.yaml's adopted_series_key before scoring it.
  scope_hash        - md5 (12 hex chars, src/forward_test_common.compute_scope_hash) of the
                      sorted set of item codes in part1_category_scope_all_codes.csv at
                      generation time -- lets the consistency check verify the log's item scope
                      still matches the CURRENT 128-item scope file before scoring it.
  scope_n_items     - 128 (a human-readable companion to scope_hash).
A companion output/summary/forward_test_log_v2_metadata.json records the same
config_version/date_key/scope_hash/scope_n_items ONCE at file level (plus fitting-window and
leakage-guard detail) so the consistency check can verify without re-deriving them from every
row of a potentially large CSV.

actual_qty is left EMPTY for every row -- never fabricated. Filled in later by
src/score_forward_test_v2.py once a target month's actuals genuinely exist and pass the
leakage-margin-aware completeness check.
"""
import hashlib
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
from item_level_reconciliation import build_item_series, build_type_series, forecast_all_approaches
from leakage_guard import check_window_closed, load_min_margin_days
from models import combination_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("forward_test_v2")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_v2.csv")
METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_v2_metadata.json")

COLUMNS = ["itemcode", "level", "category", "type", "forecast_run_date", "data_cutoff_date",
           "fit_last_month", "model", "config_version", "date_key", "scope_hash", "scope_n_items",
           "horizon", "target_month", "forecast_qty", "actual_qty"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def require_config_key(config: dict, key: str):
    """Raises loudly (KeyError) rather than defaulting silently -- CONVENTIONS.md: no magic
    numbers/values in code, and a missing adopted-method config key means this script cannot
    know what it is supposed to build."""
    if key not in config:
        raise KeyError(f"config/config.yaml is missing required key '{key}' -- "
                        f"src/forward_test_v2.py cannot determine the adopted method without it.")
    return config[key]


def build_category_series(monthly: pd.DataFrame, n_months: int) -> dict:
    """{category: qty_array} for each Category with the full fitted-window month count. Mirrors
    item_level_reconciliation.build_type_series exactly, one level up (Category instead of Type)
    -- that function has no Category-level equivalent, so this adds the missing one rather than
    modifying the existing, already-tested Type-level function."""
    out = {}
    for cat, g in monthly.groupby("category"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        qty = agg["qty"].to_numpy(dtype=float)
        if len(qty) == n_months:
            out[cat] = qty
    return out


if __name__ == "__main__":
    config = load_config()
    date_key = require_config_key(config, "adopted_series_key")
    approach_label = require_config_key(config, "adopted_item_level_approach")
    horizon = config["backtest_holdout_months"]
    ma_windows = config["moving_average_windows"]
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    monthly_path = os.path.join(DATA_DIR, f"processed_full_category_sales_monthly_{date_key}.csv")
    monthly = pd.read_csv(monthly_path)

    pull_date = monthly["snapshot_pull_date"].iloc[0]
    months = sorted(monthly["year_month"].unique())
    n_fit_months = len(months)
    if n_fit_months != TOTAL_MONTHS:
        raise ValueError(f"{monthly_path} has {n_fit_months} months, expected {TOTAL_MONTHS} "
                          f"(src/backtest_rekeyed.TOTAL_MONTHS) -- the fitting-window assumptions "
                          f"in this script's docstring no longer hold; re-check before proceeding.")
    fit_first_month, fit_last_month = months[0], months[-1]

    # Re-confirm (not assume) the fitted window still clears the leakage-guard margin against
    # this file's own recorded pull date -- see this module's docstring, "FITTING WINDOW".
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

    logger.info("date_key=%s, approach=%s, %d scope items, fitted %s to %s (%d months), "
                "forecasting %d months ahead: %s",
                date_key, approach_label, n_scope_items, fit_first_month, fit_last_month,
                n_fit_months, horizon, target_months)

    # ---- Build series: item (113 with history), Type (8), Category (2) ----
    item_series = build_item_series(monthly, scope)   # only items with full history
    type_series = build_type_series(monthly)
    category_series = build_category_series(monthly, n_fit_months)
    logger.info("%d of %d scope items have full %d-month history; %d Types, %d Categories",
                len(item_series), n_scope_items, n_fit_months, len(type_series), len(category_series))

    no_history_codes = sorted(scope.loc[~scope["has_any_history"], "code"])
    if len(no_history_codes) + len(item_series) != n_scope_items:
        raise ValueError(f"Scope accounting mismatch: {len(item_series)} with history + "
                          f"{len(no_history_codes)} without = {len(item_series) + len(no_history_codes)}, "
                          f"expected {n_scope_items}.")

    # ---- Top-down item-level forecasts (reused verbatim, not reinvented) ----
    approaches = forecast_all_approaches(item_series, type_series, n_fit_months, horizon)
    topdown_history = approaches["Top-down"]
    topdown_no_history = {code: np.zeros(horizon) for code in no_history_codes}
    topdown_all = {**topdown_history, **topdown_no_history}
    if len(topdown_all) != n_scope_items:
        raise ValueError(f"Top-down forecast covers {len(topdown_all)} items, expected {n_scope_items}.")
    if any((fc < 0).any() for fc in topdown_all.values()):
        raise ValueError("Negative forecast_qty produced by Top-down allocation -- forecasts must "
                          "never be negative (CONVENTIONS.md invariant).")

    # ---- Type-level and Category-level Combination forecasts ----
    type_forecast = {}
    for typ, qty in type_series.items():
        fc = np.clip(combination_forecast(qty[:n_fit_months], horizon, ma_windows), 0, None)
        type_forecast[typ] = fc
    category_forecast = {}
    for cat, qty in category_series.items():
        fc = np.clip(combination_forecast(qty[:n_fit_months], horizon, ma_windows), 0, None)
        category_forecast[cat] = fc

    # ---- Type -> Category map (confirmed 1:1 in this scope; raise loudly if that ever changes) ----
    type_to_cat = scope.groupby("type")["category"].nunique()
    ambiguous_types = type_to_cat[type_to_cat > 1]
    if len(ambiguous_types):
        raise ValueError(f"Type(s) spanning more than one Category found (was 1:1 when this script "
                          f"was written): {ambiguous_types.to_dict()} -- Type-level rows' 'category' "
                          f"column would be ambiguous; needs a design decision before proceeding.")
    type_to_category = scope.groupby("type")["category"].first().to_dict()
    item_to_cat_type = scope.set_index("code")[["category", "type"]].to_dict("index")

    # ---- Assemble log rows ----
    def base_row(itemcode, level, category, type_):
        return {"itemcode": itemcode, "level": level, "category": category, "type": type_,
                "forecast_run_date": run_date, "data_cutoff_date": data_cutoff_date,
                "fit_last_month": fit_last_month, "config_version": cfg_ver, "date_key": date_key,
                "scope_hash": scope_hash, "scope_n_items": n_scope_items}

    records = []
    for item, fc in topdown_all.items():
        info = item_to_cat_type[item]
        row = base_row(item, "Item", info["category"], info["type"])
        row["model"] = f"{approach_label}_Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm,
                             "forecast_qty": round(float(val), 4), "actual_qty": ""})

    for typ, fc in type_forecast.items():
        row = base_row(typ, "Type", type_to_category[typ], typ)
        row["model"] = "Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm,
                             "forecast_qty": round(float(val), 4), "actual_qty": ""})

    for cat, fc in category_forecast.items():
        row = base_row(cat, "Category", cat, "")
        row["model"] = "Combination"
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm,
                             "forecast_qty": round(float(val), 4), "actual_qty": ""})

    log_df = pd.DataFrame(records, columns=COLUMNS)
    if (log_df["forecast_qty"] < 0).any():
        raise ValueError("Negative forecast_qty in final log -- forecasts must never be negative.")
    log_df.to_csv(LOG_PATH, index=False)

    n_item_rows = len(topdown_all) * horizon
    n_type_rows = len(type_forecast) * horizon
    n_cat_rows = len(category_forecast) * horizon
    logger.info("Wrote %s: %d rows (Item %d = %d items x %d horizon; Type %d = %d types x %d horizon; "
                "Category %d = %d categories x %d horizon)", LOG_PATH, len(log_df),
                n_item_rows, len(topdown_all), horizon, n_type_rows, len(type_forecast), horizon,
                n_cat_rows, len(category_forecast), horizon)

    metadata = {
        "log_file": os.path.relpath(LOG_PATH, PROJECT_ROOT).replace("\\", "/"),
        "generated_by_script": "src/forward_test_v2.py",
        "forecast_run_date": run_date,
        "config_version": cfg_ver,
        "date_key": date_key,
        "item_level_approach": approach_label,
        "scope_hash": scope_hash,
        "scope_n_items": n_scope_items,
        "scope_source_file": "output/summary/part1_category_scope_all_codes.csv",
        "monthly_series_source_file": os.path.relpath(monthly_path, PROJECT_ROOT).replace("\\", "/"),
        "monthly_series_snapshot_pull_date": str(pull_date),
        "fit_first_month": fit_first_month,
        "fit_last_month": fit_last_month,
        "fit_n_months": n_fit_months,
        "horizon_months": horizon,
        "target_months": target_months,
        "leakage_guard_min_margin_days": min_margin_days,
        "leakage_guard_actual_margin_days": actual_margin_days,
        "n_item_rows": n_item_rows,
        "n_type_rows": n_type_rows,
        "n_category_rows": n_cat_rows,
        "n_total_rows": len(log_df),
        "n_items_with_history": len(topdown_history),
        "n_items_no_history_zero_forecast": len(topdown_no_history),
    }
    save_metadata(METADATA_PATH, metadata)
    logger.info("Wrote metadata: %s", METADATA_PATH)

    print(f"\nForward-test log v2 written: {LOG_PATH}")
    print(f"Rows: {len(log_df)} ({n_item_rows} Item + {n_type_rows} Type + {n_cat_rows} Category)")
    print(f"Fitted window: {fit_first_month} to {fit_last_month} ({n_fit_months} months, "
          f"forecast_date-keyed, pull_date={pull_date})")
    print(f"Target months (horizon 1-{horizon}): {target_months}")
    print("actual_qty is empty for all rows -- these are real future periods, not fabricated.")
    print(f"Metadata: {METADATA_PATH}")
