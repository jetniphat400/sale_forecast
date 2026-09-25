"""Tests for src/monthly_refresh.py's ONE-VINTAGE-PER-CALENDAR-MONTH guard (task 2cfix2, Part 2).

METRICS.md Sec.27/28: a monthly run appends one new vintage; nothing in the original design
stopped a SECOND real run in the same calendar month from appending vintage 3, vintage 4, etc.
This guard (find_existing_vintage_this_month(), wired into step5_new_vintage()) blocks that,
unless --force-new-vintage is explicitly passed.

Per this task's own instruction and CONVENTIONS.md's DATABASE ACCESS rule, these tests use a
synthetic/temporary log file (pytest's tmp_path fixture) and monkeypatch monthly_refresh's own
module-level path constants and compute_new_vintage() (which would otherwise need a real database
pull and the full forecasting pipeline) -- never the real tracked forward-test log, and no
database connection at all.
"""
import json
import os

import pandas as pd
import pytest

import monthly_refresh as mr


def _write_log(path: str, forecast_run_date_by_vintage: dict) -> None:
    rows = [{"vintage_id": v, "forecast_run_date": d} for v, d in forecast_run_date_by_vintage.items()]
    pd.DataFrame(rows).to_csv(path, index=False)


THIS_MONTH_DATE = pd.Timestamp.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------------------------
# find_existing_vintage_this_month() -- the guard's own pure logic
# ---------------------------------------------------------------------------------------------

def test_find_existing_vintage_this_month_returns_none_when_log_missing(tmp_path):
    missing_path = os.path.join(str(tmp_path), "does_not_exist.csv")
    assert mr.find_existing_vintage_this_month(missing_path, pd.Timestamp.now()) is None


def test_find_existing_vintage_this_month_returns_none_when_no_row_in_current_month(tmp_path):
    log_path = os.path.join(str(tmp_path), "log.csv")
    _write_log(log_path, {1: "2020-01-15"})  # a long-past month
    assert mr.find_existing_vintage_this_month(log_path, pd.Timestamp.now()) is None


def test_find_existing_vintage_this_month_finds_a_same_month_row(tmp_path):
    log_path = os.path.join(str(tmp_path), "log.csv")
    _write_log(log_path, {1: THIS_MONTH_DATE})
    found = mr.find_existing_vintage_this_month(log_path, pd.Timestamp.now())
    assert found == {"vintage_id": 1, "forecast_run_date": THIS_MONTH_DATE}


def test_find_existing_vintage_this_month_picks_highest_vintage_id_when_several_match(tmp_path):
    log_path = os.path.join(str(tmp_path), "log.csv")
    _write_log(log_path, {1: "2020-01-01", 2: THIS_MONTH_DATE, 3: THIS_MONTH_DATE})
    found = mr.find_existing_vintage_this_month(log_path, pd.Timestamp.now())
    assert found["vintage_id"] == 3


# ---------------------------------------------------------------------------------------------
# step5_new_vintage(): PATH 1 -- guard BLOCKS a same-month second append (dry-run and real)
# ---------------------------------------------------------------------------------------------

def test_step5_new_vintage_guard_blocks_same_month_append_dry_run(tmp_path, monkeypatch):
    log_path = os.path.join(str(tmp_path), "log.csv")
    _write_log(log_path, {1: THIS_MONTH_DATE})
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", log_path)
    monkeypatch.setattr(mr, "compute_new_vintage",
                         lambda: pytest.fail("compute_new_vintage() must not run when the guard blocks"))

    result = mr.step5_new_vintage(dry_run=True, force_new_vintage=False)

    assert result["skipped"] is True
    assert result["written"] is False
    assert result["existing_vintage_id_this_month"] == 1
    assert result["existing_forecast_run_date_this_month"] == THIS_MONTH_DATE
    assert mr._LAST_COMPUTED_VINTAGE is None


def test_step5_new_vintage_guard_blocks_same_month_append_real_run_writes_nothing(tmp_path, monkeypatch):
    log_path = os.path.join(str(tmp_path), "log.csv")
    _write_log(log_path, {1: THIS_MONTH_DATE})
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", log_path)
    monkeypatch.setattr(mr, "compute_new_vintage",
                         lambda: pytest.fail("compute_new_vintage() must not run when the guard blocks"))

    result = mr.step5_new_vintage(dry_run=False, force_new_vintage=False)

    assert result["skipped"] is True
    assert result["written"] is False
    on_disk = pd.read_csv(log_path)
    assert on_disk["vintage_id"].tolist() == [1]  # unchanged -- nothing appended


# ---------------------------------------------------------------------------------------------
# step5_new_vintage(): PATH 2 -- --force-new-vintage OVERRIDES the guard (dry-run and real)
# ---------------------------------------------------------------------------------------------

def _fake_computed_vintage(vintage_id: int) -> dict:
    return {
        "vintage_id": vintage_id,
        "rows_df": pd.DataFrame([{"vintage_id": vintage_id, "forecast_qty": 1.0}]),
        "metadata_entry": {"vintage_id": vintage_id, "note": "synthetic test vintage"},
        "n_rows": 1,
        "six_month_item_forecast_total_by_division": {"PEM101": 100.0},
    }


def test_step5_new_vintage_force_flag_overrides_guard_dry_run(tmp_path, monkeypatch):
    log_path = os.path.join(str(tmp_path), "log.csv")
    _write_log(log_path, {1: THIS_MONTH_DATE})
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", log_path)
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed_vintage(2))

    result = mr.step5_new_vintage(dry_run=True, force_new_vintage=True)

    assert result["skipped"] is False
    assert result["force_override_used"] is True
    assert result["overridden_existing_vintage_id"] == 1
    assert result["vintage_id"] == 2
    assert result["written"] is False  # dry-run: computed, not appended
    on_disk = pd.read_csv(log_path)
    assert on_disk["vintage_id"].tolist() == [1]  # dry-run never writes


def test_step5_new_vintage_force_flag_overrides_guard_real_run_appends(tmp_path, monkeypatch):
    log_path = os.path.join(str(tmp_path), "log.csv")
    metadata_path = os.path.join(str(tmp_path), "metadata.json")
    _write_log(log_path, {1: THIS_MONTH_DATE})
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump({}, f)
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", log_path)
    monkeypatch.setattr(mr, "FORWARD_TEST_METADATA_PATH", metadata_path)
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed_vintage(2))

    result = mr.step5_new_vintage(dry_run=False, force_new_vintage=True)

    assert result["written"] is True
    assert result["force_override_used"] is True
    on_disk = pd.read_csv(log_path)
    assert sorted(on_disk["vintage_id"].tolist()) == [1, 2]
    with open(metadata_path, "r", encoding="utf-8") as f:
        saved_meta = json.load(f)
    assert "2" in saved_meta


def test_step5_new_vintage_no_same_month_row_computes_normally_without_force(tmp_path, monkeypatch):
    """Sanity check on the non-guard path: when nothing in the log matches the current calendar
    month, a normal (non-forced) run computes and (if not dry-run) appends, exactly as before this
    guard existed."""
    log_path = os.path.join(str(tmp_path), "log.csv")
    _write_log(log_path, {1: "2020-01-01"})
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", log_path)
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed_vintage(2))

    result = mr.step5_new_vintage(dry_run=True, force_new_vintage=False)

    assert result["skipped"] is False
    assert "force_override_used" not in result
    assert result["vintage_id"] == 2
