"""Data-access/computation layer for the report's forecast-vs-actual-per-origin chart
(CONVENTIONS.md: "separate data access, computation and presentation into different modules" --
src/build_report.py stays presentation-only, this module supplies the numbers it renders).

WHY THIS SCRIPT EXISTS (Phase E1 report rework, "fix chart content"): the previous report's
"cumulative actual -- 3 focus codes per rolling origin" chart read
output/summary/phaseE1_2_rolling_origin_cumulative.csv, whose x-axis ran 1-9. That file is real
and correctly computed, but it is Phase E1.2's OWN rolling-origin scheme, built to test the
4-MONTH PROTECTION-PERIOD horizon (src/phaseE1_leadtime_demand.py calls
`get_origins(TOTAL_MONTHS=31, horizon=4)`), not this project's standard 6-month-holdout backtest
used everywhere else (src/backtest_rekeyed.py, src/transferability_all_divisions.py:
`get_origins(31, 6)`). A shorter holdout fits more windows into the same 31-month series --
`get_origins(31, 4)` returns 9 origins where `get_origins(31, 6)` returns 7 -- so "1 to 9" was a
real origin index under a DIFFERENT (4-month) evaluation than the "7 origins" the rolling-origin
backtest everywhere else in this project refers to. It also plotted `cum_actual` only; the
Modeler's own file has a `cum_forecast` column that was simply never rendered.

THE FIX: recompute forecast vs. actual per origin using the project's STANDARD scheme (7 origins,
6-month holdout) with the SAME already-verified-leakage-free Top-down pattern (per-origin item
share from `train` data only -- confirmed leakage-free, Phase E0.1,
src/transferability_all_divisions.py), for every item in the 113-item PEM101 pilot scope (the
same monthly file src/phaseE1_common.py and the rest of this project's Phase B/C work uses),
across its 8 Types. This gives ONE consistent origin axis (1-7) with BOTH forecast and actual, for
any item in this scope -- the report's item selector defaults to the 3 focus codes but any item
in this 113-item scope is selectable.

SCOPE NOTE, stated plainly: this dataset covers PEM101's 113-item pilot scope only (the same scope
Phase E1 used), not the full 335-item forecast universe -- computing this per-origin
forecast/actual series fresh for all 335 items across every origin was out of this task's scope;
the report's Division/Type filters for the OTHER charts (scope table, per-division results table)
use the full 445/335-item files directly and are not limited by this scope note.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import HOLDOUT, MA_WINDOWS, TOTAL_MONTHS, get_origins
from leakage_guard import check_window_closed, load_min_margin_days
from models import combination_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_report_data")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
MONTHLY_FILE = os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")
OUT_FILE = os.path.join(SUMMARY_DIR, "report_item_forecast_vs_actual_by_origin.csv")

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_monthly() -> pd.DataFrame:
    if not os.path.exists(MONTHLY_FILE):
        raise FileNotFoundError(f"Required source missing: {MONTHLY_FILE}")
    df = pd.read_csv(MONTHLY_FILE)
    for col in ["itemcode", "year_month", "qty", "category", "type", "snapshot_pull_date"]:
        if col not in df.columns:
            raise ValueError(f"{MONTHLY_FILE} is missing required column '{col}'.")
    return df


def build_item_and_type_series(monthly: pd.DataFrame) -> tuple:
    item_series, item_meta = {}, {}
    for code, g in monthly.groupby("itemcode"):
        g = g.sort_values("year_month")
        if len(g) != TOTAL_MONTHS:
            continue  # not a full-length series -- excluded, same convention as the rest of Phase B/C/E1
        item_series[code] = (g["qty"].to_numpy(dtype=float), g["year_month"].astype(str).tolist())
        item_meta[code] = (g["category"].iloc[0], g["type"].iloc[0])

    type_series = {}
    for typ, g in monthly.groupby("type"):
        agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
        if len(agg) != TOTAL_MONTHS:
            continue
        type_series[typ] = agg["qty"].to_numpy(dtype=float)
    return item_series, item_meta, type_series


def compute_forecast_vs_actual_by_origin(item_series: dict, item_meta: dict, type_series: dict,
                                           pull_date, min_margin_days: int) -> pd.DataFrame:
    """Standard scheme, 7 origins (get_origins(31, 6)): for every item with a full-length series,
    Top-down forecast at each origin = Type-level Combination forecast * item's own train-only
    qty share of its Type -- the verified-leakage-free pattern (Phase E0.1)."""
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)
    rows = []
    n_refused = 0
    for code, (qty, months) in item_series.items():
        cat, typ = item_meta[code]
        if typ not in type_series:
            continue
        type_qty = type_series[typ]
        for origin_idx, train_size in enumerate(origins, start=1):
            window_end_month = months[train_size + HOLDOUT - 1]
            try:
                check_window_closed(window_end_month, pull_date, min_margin_days)
            except Exception:
                n_refused += 1
                continue
            type_train = type_qty[:train_size]
            type_fc = np.clip(combination_forecast(type_train, HOLDOUT, MA_WINDOWS), 0, None)
            item_total = qty[:train_size].sum()
            type_total = type_train.sum()
            share = item_total / type_total if type_total > 0 else np.nan
            item_fc = type_fc * share if np.isfinite(share) else np.full(HOLDOUT, np.nan)
            actual = qty[train_size:train_size + HOLDOUT]
            for h in range(HOLDOUT):
                rows.append({
                    "itemcode": code, "category": cat, "type": typ,
                    "origin": origin_idx, "train_size": train_size,
                    "month_in_horizon": h + 1, "year_month": months[train_size + h],
                    "actual_qty": float(actual[h]),
                    "forecast_qty": float(item_fc[h]) if np.isfinite(item_fc[h]) else None,
                })
    logger.info("%d item x origin x month rows computed across %d origins (standard get_origins(%d,%d) "
                "scheme). %d windows refused by the leakage guard.",
                len(rows), len(origins), TOTAL_MONTHS, HOLDOUT, n_refused)
    return pd.DataFrame(rows)


def build_report_data() -> pd.DataFrame:
    config = load_config()
    min_margin_days = load_min_margin_days(config)
    monthly = load_monthly()
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    item_series, item_meta, type_series = build_item_and_type_series(monthly)
    logger.info("%d full-length items across %d Types (PEM101 pilot scope, %s).",
                len(item_series), len(type_series), MONTHLY_FILE)
    missing_focus = set(FOCUS_ITEMS) - set(item_series)
    if missing_focus:
        raise ValueError(f"Focus item(s) missing from the full-length series: {missing_focus}")
    df = compute_forecast_vs_actual_by_origin(item_series, item_meta, type_series, pull_date, min_margin_days)
    df.to_csv(OUT_FILE, index=False)
    logger.info("Written: %s (%d rows)", OUT_FILE, len(df))
    return df


if __name__ == "__main__":
    build_report_data()
