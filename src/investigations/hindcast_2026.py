"""Hindcast 2026 (Prompt 64 step 3; Prompt 61 analysis only): how accurate the production model would have been from January 2026, with the origin and the leakage guarded.

ANALYSIS ONLY. It writes nothing to the forward-test log, the vintages, the model inputs or any published file. It reads the monthly series of a pull (a kept temporary copy of the project, made by a
dry run of the monthly runner), the scope file and the saved backtest choice of the moving-average windows, and writes its own tables.

The model is NOT re-implemented. The forecasts come from the functions step 5 of the monthly runner uses (`forward_test_all_divisions.build_item_series_div` / `build_type_series_div`,
`item_level_reconciliation.forecast_all_approaches` for Top-down, `models.naive_forecast`, `models.moving_average_forecast` with the windows of `ma_comparator`), called in the same order as
`monthly_refresh.compute_new_vintage`, but on a series cut at an origin and with the horizon passed as a parameter. `compute_new_vintage` itself cannot take a cut series (fixed series file, a
fixed 31-month check, today's date, the real forward-test log), so `check_driver_against_step5` proves the driver gives the same numbers as step 5 on the full series.

Runs (A): the monthly run of every month from 2025-10 to 2026-09 on its run day (`monthly_refresh.run_day`); the series is cut at the run's fit_last_month = the latest month the leakage guard
accepts at that run date; horizon 6. Run (B): the January 2026 run day, the same rule, horizon passed as a parameter up to 2026-09 (beyond the production horizon of 6).
"""
import hashlib
import io
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(SRC)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

RUN_MONTHS_A = [f"{y}-{m:02d}" for y, m in [(2025, 10), (2025, 11), (2025, 12)] + [(2026, k) for k in range(1, 10)]]
FIRST_SCORED_MONTH, LAST_SCORED_MONTH = "2026-01", "2026-09"
PRODUCTION_HORIZON = 6


class HindcastError(Exception):
    """A guard of the hindcast failed (the run's input does not end at its fit month, the config changed, ...)."""


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def assert_unchanged(path: str, hash_before: str) -> str:
    """Stops when the file no longer has the hash it had before the run (the hindcast must not tune anything: the config is hashed before and after)."""
    after = sha256_file(path)
    if after != hash_before:
        raise HindcastError(f"{os.path.basename(path)} changed during the hindcast")
    return after


def run_date_of(month: str, base_day: int = None) -> date:
    """The monthly run day of `month` ('YYYY-MM'): the first Monday to Friday on or after the base day (monthly_refresh.run_day)."""
    import monthly_refresh
    y, m = (int(x) for x in month.split("-"))
    return monthly_refresh.run_day(y, m, base_day)


def fit_last_month_for(run_date: date, months: list, margin_days: int) -> str:
    """The latest month of `months` that the project's own leakage guard accepts at `run_date` (the pull date of a run is its run day)."""
    from leakage_guard import LeakageGuardError, check_window_closed
    for month in sorted(months, reverse=True):
        try:
            check_window_closed(month, run_date.isoformat(), margin_days)
            return month
        except LeakageGuardError:
            continue
    raise HindcastError(f"no month of the series passes the leakage guard at {run_date}")


def cut_series(monthly: pd.DataFrame, fit_last: str) -> pd.DataFrame:
    """The series as a run of that origin sees it: every row at or before fit_last, and a hard check that nothing later is inside."""
    cut = monthly[monthly["year_month"] <= fit_last].copy()
    if cut.empty or cut["year_month"].max() != fit_last:
        raise HindcastError(f"the cut series does not end at its fit_last_month {fit_last} (ends {cut['year_month'].max() if len(cut) else 'empty'})")
    if (cut["year_month"] > fit_last).any():
        raise HindcastError("a month after fit_last_month is inside the run's input")
    return cut


def forecast_run(monthly: pd.DataFrame, scope: pd.DataFrame, fit_last: str, horizon: int, windows_by_division: dict) -> pd.DataFrame:
    """Item-level forecasts of ONE simulated run: columns item, division, target_month, horizon, f_topdown, f_naive, f_ma, history_months_nonzero.
    The order of the calls is that of monthly_refresh.compute_new_vintage; `horizon` is a parameter."""
    from forward_test_all_divisions import build_item_series_div, build_type_series_div
    from item_level_reconciliation import forecast_all_approaches
    from models import moving_average_forecast, naive_forecast
    cut = cut_series(monthly, fit_last)
    months = sorted(cut["year_month"].unique())
    n_fit = len(months)
    item_series = build_item_series_div(cut, scope, n_fit)
    type_series = build_type_series_div(cut, n_fit)
    no_history = sorted(set(scope["code"]) - set(item_series.keys()))
    topdown = {**forecast_all_approaches(item_series, type_series, n_fit, horizon)["Top-down"], **{c: np.zeros(horizon) for c in no_history}}
    info = scope.set_index("code")[["division"]].to_dict("index")
    target_months = [str(pd.Period(fit_last, freq="M") + i) for i in range(1, horizon + 1)]
    rows = []
    for code in sorted(set(item_series) | set(no_history)):
        division = info[code]["division"]
        if code in item_series:
            qty = np.asarray(item_series[code][0], dtype=float)
            naive = np.clip(naive_forecast(qty, horizon), 0, None)
            ma = np.clip(moving_average_forecast(qty, horizon, windows_by_division[division]), 0, None)
            nonzero = int((qty > 0).sum())
        else:
            naive, ma, nonzero = np.zeros(horizon), np.zeros(horizon), 0
        for h, tm in enumerate(target_months, start=1):
            rows.append({"item": code, "division": division, "target_month": tm, "horizon": h, "f_topdown": float(topdown[code][h - 1]),
                         "f_naive": float(naive[h - 1]), "f_ma": float(ma[h - 1]), "history_months_nonzero": nonzero})
    return pd.DataFrame(rows)


def simulate(monthly: pd.DataFrame, scope: pd.DataFrame, windows_by_division: dict, margin_days: int, base_day: int = None) -> pd.DataFrame:
    """Run family A (the 12 monthly runs, horizon 6) and run B (the January 2026 run, horizon up to LAST_SCORED_MONTH); one frame, with family, run_date and fit_last_month."""
    months = sorted(monthly["year_month"].unique())
    parts = []
    for month in RUN_MONTHS_A:
        rd = run_date_of(month, base_day)
        fit_last = fit_last_month_for(rd, months, margin_days)
        df = forecast_run(monthly, scope, fit_last, PRODUCTION_HORIZON, windows_by_division)
        parts.append(df.assign(family="A", run_month=month, run_date=rd.isoformat(), fit_last_month=fit_last))
    rd_b = run_date_of("2026-01", base_day)
    fit_b = fit_last_month_for(rd_b, months, margin_days)
    horizon_b = int(pd.Period(LAST_SCORED_MONTH, freq="M").ordinal - pd.Period(fit_b, freq="M").ordinal)
    parts.append(forecast_run(monthly, scope, fit_b, horizon_b, windows_by_division).assign(family="B", run_month="2026-01", run_date=rd_b.isoformat(), fit_last_month=fit_b))
    return pd.concat(parts, ignore_index=True)


def attach_actuals_and_prices(sim: pd.DataFrame, monthly: pd.DataFrame, prices: dict) -> pd.DataFrame:
    actual = monthly.rename(columns={"itemcode": "item", "year_month": "target_month", "qty": "actual"})[["item", "target_month", "actual"]]
    out = sim.merge(actual, on=["item", "target_month"], how="left")
    out["price"] = out["item"].map(prices)
    return out


def main_line(sim_a: pd.DataFrame) -> pd.DataFrame:
    """For every target month, the rows of the latest simulated run dated BEFORE the first day of that month (the third month ahead for a run on the 5th of the month before the target)."""
    first_day = pd.to_datetime(sim_a["target_month"] + "-01")
    ok = sim_a[pd.to_datetime(sim_a["run_date"]) < first_day]
    latest = ok.groupby("target_month")["run_date"].transform("max")
    return ok[ok["run_date"] == latest]


def check_driver_against_step5(monthly_full: pd.DataFrame, scope: pd.DataFrame, windows_by_division: dict, step5_item_rows: pd.DataFrame) -> dict:
    """The driver on the full series at horizon 6 against the Item rows `compute_new_vintage` produced on the same series (columns itemcode, horizon, forecast_qty): the largest difference."""
    fit_last = monthly_full["year_month"].max()
    mine = forecast_run(monthly_full, scope, fit_last, PRODUCTION_HORIZON, windows_by_division)
    theirs = step5_item_rows.rename(columns={"itemcode": "item"})[["item", "horizon", "forecast_qty"]]
    m = mine.merge(theirs, on=["item", "horizon"], how="outer", indicator=True)
    return {"rows_driver": int(len(mine)), "rows_step5": int(len(theirs)), "unmatched": int((m["_merge"] != "both").sum()),
            "max_abs_difference": float((m["f_topdown"] - m["forecast_qty"]).abs().max())}


# ---------------------------------------------------------------------------------------------------- measurement
def _safe_ratio(a: float, b: float):
    return float(a / b) if b else None


def item_level_table(df: pd.DataFrame, by: list) -> pd.DataFrame:
    """METRICS Sec.25 and 48 at item level, per group: n (item-month cells), MAE in quantity and in baht (fixed price per item), Relative MAE = sum|model e| / sum|Naive e| (quantity) for Top-down and MA,
    and relative bias = sum(forecast - actual) / sum(actual) (analysis only)."""
    d = df.dropna(subset=["actual"]).copy()
    for m in ("topdown", "naive", "ma"):
        d[f"e_{m}"] = d[f"f_{m}"] - d["actual"]
        d[f"ae_{m}"] = d[f"e_{m}"].abs()
        d[f"aeb_{m}"] = d[f"ae_{m}"] * d["price"]
    rows = []
    for key, g in d.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        row["n_cells"] = int(len(g))
        row["actual_qty"] = float(g["actual"].sum())
        for m in ("topdown", "naive", "ma"):
            row[f"mae_{m}"] = float(g[f"ae_{m}"].mean())
            row[f"mae_baht_{m}"] = float(g[f"aeb_{m}"].mean())
            row[f"bias_{m}"] = _safe_ratio(g[f"e_{m}"].sum(), g["actual"].sum())
        for m in ("topdown", "ma"):
            row[f"relmae_{m}"] = _safe_ratio(g[f"ae_{m}"].sum(), g["ae_naive"].sum())
            row[f"relmae_baht_{m}"] = _safe_ratio(g[f"aeb_{m}"].sum(), g["aeb_naive"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def totals_by_month(df: pd.DataFrame) -> pd.DataFrame:
    """Per division and target month, and for the company (the divisions added), the TOTAL in baht (fixed price per item): actual and each model's forecast."""
    d = df.dropna(subset=["actual"]).copy()
    for col in ("actual", "f_topdown", "f_naive", "f_ma"):
        d[col + "_baht"] = d[col] * d["price"]
    g = d.groupby(["division", "target_month"])[[c + "_baht" for c in ("actual", "f_topdown", "f_naive", "f_ma")] + ["actual"]].sum().reset_index()
    n_items = d.groupby(["division", "target_month"])["item"].nunique().rename("n_items").reset_index()
    g = g.merge(n_items, on=["division", "target_month"])
    comp = g.groupby("target_month")[[c for c in g.columns if c.endswith("_baht")] + ["n_items"]].sum().reset_index().assign(division="COMPANY")
    return pd.concat([g.drop(columns=["actual"]), comp], ignore_index=True)


def totals_summary(tot: pd.DataFrame) -> pd.DataFrame:
    """Over the months: n months, MAE of the monthly total in baht, relative to Naive, and bias = sum(forecast - actual) / sum(actual), per division and company."""
    rows = []
    for division, g in tot.groupby("division"):
        a = g["actual_baht"].to_numpy()
        row = {"division": division, "n_months": int(len(g)), "actual_baht": float(a.sum())}
        for m in ("topdown", "naive", "ma"):
            f = g[f"f_{m}_baht"].to_numpy()
            row[f"mae_baht_{m}"] = float(np.abs(f - a).mean())
            row[f"bias_{m}"] = _safe_ratio((f - a).sum(), a.sum())
        for m in ("topdown", "ma"):
            row[f"relmae_{m}"] = _safe_ratio(float(np.abs(g[f"f_{m}_baht"].to_numpy() - a).sum()), float(np.abs(g["f_naive_baht"].to_numpy() - a).sum()))
        rows.append(row)
    return pd.DataFrame(rows)
