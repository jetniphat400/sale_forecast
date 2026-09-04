"""Task 2 (Modeler): config-driven leakage-guard for backtest scoring.

CONVENTIONS.md: "Separate data access, computation and presentation into different modules" and
"Validation failures must be raised loudly, never silently skipped." This module holds ONLY the
guard's computation (no data pulling, no printing/plotting) so src/backtest_rekeyed.py's
run_train_val_test and run_rolling_origin can both call the identical check.

Motivation (src/leakage_check_forecastdate.py, output/summary/b4_leakage_and_windowposition_report.md):
the existing "zero future-dated rows inside the backtest window" finding was TRUE only because the
2026-09-02 pull happened to occur more than a month after the 31-month window's last month
(2026-07) had fully elapsed. That gap was incidental, not enforced by any code -- a future re-run
with a tighter pull-to-window-end gap could silently score a window before it is safe to trust,
without anyone noticing. This module makes that gap an explicit, checked precondition instead.
"""
import pandas as pd


class LeakageGuardError(Exception):
    """Raised when a backtest window is scored too close to the data's snapshot pull date.
    Never caught and silently ignored anywhere in this project's code -- CONVENTIONS.md requires
    validation failures to be raised loudly."""


def check_window_closed(window_end_month, pull_date, min_margin_days: int) -> None:
    """Refuse (raise LeakageGuardError) to score a window whose last month does not have at
    least `min_margin_days` of clearance before the data's snapshot pull date.

    window_end_month: the LAST calendar month included in the window being scored -- a
        pandas Period (freq='M') or any string pandas.Period() accepts (e.g. '2026-07').
    pull_date: the frozen snapshot_pull_date for the data being scored (str or Timestamp) --
        read from the monthly file's own `snapshot_pull_date` column (src/load_data_full.py),
        never re-queried live, so results stay reproducible across runs (CONVENTIONS.md).
    min_margin_days: config/config.yaml's leakage_guard.min_margin_days.

    Raises LeakageGuardError, stating the window's end date, the pull date, and both the
    required and actual gap, if pull_date - window_end < min_margin_days. Returns None (no
    warning object, no return value) if the window is safe to score.
    """
    window_end_period = pd.Period(window_end_month, freq="M")
    window_end_date = window_end_period.end_time.normalize()
    pull_ts = pd.Timestamp(pull_date).normalize()
    actual_gap_days = (pull_ts - window_end_date).days

    if actual_gap_days < min_margin_days:
        raise LeakageGuardError(
            f"LEAKAGE GUARD REFUSED TO SCORE THIS WINDOW. "
            f"Window end (last month of the test window): {window_end_date.date()} "
            f"(month {window_end_period}). "
            f"Data snapshot pull date: {pull_ts.date()}. "
            f"Required margin (config/config.yaml: leakage_guard.min_margin_days): {min_margin_days} day(s). "
            f"Actual margin: {actual_gap_days} day(s). "
            f"The pull happened too soon after this window's last month closed to trust the window "
            f"is complete -- refusing to score it, not silently skipping or warning-and-continuing."
        )


def load_min_margin_days(config: dict) -> int:
    """Reads leakage_guard.min_margin_days from an already-loaded config dict. Raises loudly
    (KeyError, not a silent default) if the section is missing -- CONVENTIONS.md: no magic
    numbers in code, every tunable value belongs in config.yaml, so a missing config section is
    a configuration error to surface, not something to paper over with a hardcoded fallback."""
    try:
        return int(config["leakage_guard"]["min_margin_days"])
    except KeyError as e:
        raise KeyError(
            "config/config.yaml is missing the leakage_guard.min_margin_days section required by "
            "src/leakage_guard.py -- this must be configured explicitly, not defaulted silently."
        ) from e
