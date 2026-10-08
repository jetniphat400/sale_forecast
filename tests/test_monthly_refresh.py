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
import vintage_series

from forward_test_common import append_vintage_and_hash, save_metadata
from test_forward_test_integrity import base_entry, make_rows

FIT_SERIES = b"year_month,itemcode,qty\n2026-08,A-1,3\n"


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
        "rows_df": make_rows(vintage_id),
        "metadata_entry": {**base_entry(vintage_id), **vintage_series.metadata_fields(FIT_SERIES, vintage_id)},
        "fit_series_bytes": FIT_SERIES,
        "n_rows": 9,
        "six_month_item_forecast_total_by_division": {"PEM101": 100.0},
        "comparator_rows_df": make_rows(vintage_id),
        "comparator_metadata_entry": {**base_entry(vintage_id), "ma_window_by_division": {"PEM101": 3}},
    }


def _full_log(tmp_path, monkeypatch, vintage_1_date):
    """A synthetic log and metadata holding a complete vintage 1 (the dry run now writes and re-reads the log)."""
    log_path = os.path.join(str(tmp_path), "log.csv")
    metadata_path = os.path.join(str(tmp_path), "metadata.json")
    entry = append_vintage_and_hash(log_path, make_rows(1, vintage_1_date, "2026-07"), base_entry(1))
    save_metadata(metadata_path, {"1": entry})
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", log_path)
    monkeypatch.setattr(mr, "FORWARD_TEST_METADATA_PATH", metadata_path)
    # the moving-average comparator log lives beside the synthetic log, never at the real path
    monkeypatch.setattr(mr, "COMPARATOR_LOG_PATH", os.path.join(str(tmp_path), "comparator_log.csv"))
    monkeypatch.setattr(mr, "COMPARATOR_METADATA_PATH", os.path.join(str(tmp_path), "comparator_metadata.json"))
    monkeypatch.setattr(vintage_series, "SERIES_DIR", os.path.join(str(tmp_path), "vintage_series"))   # never the real folder
    return log_path, metadata_path


def test_step5_new_vintage_force_flag_overrides_guard_dry_run(tmp_path, monkeypatch):
    log_path, _meta = _full_log(tmp_path, monkeypatch, THIS_MONTH_DATE)
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed_vintage(2))

    result = mr.step5_new_vintage(dry_run=True, force_new_vintage=True)

    assert result["skipped"] is False
    assert result["force_override_used"] is True
    assert result["overridden_existing_vintage_id"] == 1
    assert result["vintage_id"] == 2
    assert result["written"] is False  # dry-run: computed, not appended
    on_disk = pd.read_csv(log_path)
    assert set(on_disk["vintage_id"]) == {1}  # dry-run never writes to the real log


def test_step5_new_vintage_force_flag_overrides_guard_real_run_appends(tmp_path, monkeypatch):
    log_path, metadata_path = _full_log(tmp_path, monkeypatch, THIS_MONTH_DATE)
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed_vintage(2))

    result = mr.step5_new_vintage(dry_run=False, force_new_vintage=True)

    assert result["written"] is True
    assert result["force_override_used"] is True
    on_disk = pd.read_csv(log_path)
    assert set(on_disk["vintage_id"]) == {1, 2}
    with open(metadata_path, "r", encoding="utf-8") as f:
        saved_meta = json.load(f)
    assert "2" in saved_meta


def test_step5_new_vintage_no_same_month_row_computes_normally_without_force(tmp_path, monkeypatch):
    """Sanity check on the non-guard path: when nothing in the log matches the current calendar
    month, a normal (non-forced) run computes and (if not dry-run) appends, exactly as before this
    guard existed."""
    log_path, _meta = _full_log(tmp_path, monkeypatch, "2020-01-01")
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed_vintage(2))

    result = mr.step5_new_vintage(dry_run=True, force_new_vintage=False)

    assert result["skipped"] is False
    assert "force_override_used" not in result
    assert result["vintage_id"] == 2


# ------------------------------------------------------------------ step 7d: one forecast vintage for G1, G2, G3 and the material plan (decision D2, 2026-10-08)
def _stage(vid):
    return {"vintage_id": vid, "source": "test"}


def test_the_vintage_gate_passes_when_all_four_stages_carry_the_same_vintage():
    r = mr.vintage_gate(_stage(2), _stage(2), _stage(2), _stage(2))
    assert r["vintage_id"] == 2 and len(r["stages"]) == 4


@pytest.mark.parametrize("ids", [(2, 1, 2, 2), (2, 2, 1, 2), (2, 2, 2, 1), (1, 2, 2, 2), (2, 2, None, 2), (None, None, None, None)])
def test_the_vintage_gate_fails_when_any_stage_differs_or_records_none_and_names_the_stages(ids):
    with pytest.raises(mr.MonthlyRefreshAbort, match="do not carry one forecast vintage") as e:
        mr.vintage_gate(*[_stage(i) for i in ids])
    for name in ("G1", "G2", "G3", "material plan"):
        assert name in str(e.value)


def test_the_runner_runs_the_gate_after_the_material_plan_and_before_the_tests_and_the_gate_is_counted():
    order = mr.STEP_ORDER
    assert order.index("7_rebuild_pages") < order.index("7b_operation_plan") < order.index("7c_material_plan") < order.index("7d_vintage_gate") < order.index("8_run_tests")
    gates = mr.gate_outcomes({"passed": True, "summary_line": "x"}, {"passed": True, "findings": []}, {"gates": {}}, {"vintage_id": 2})
    assert gates["gates"]["vintage_consistency"]["status"] == "passed" and gates["counts"]["passed"] == 3
    assert "vintage_consistency" not in mr.gate_outcomes({"passed": True}, {"passed": True, "findings": []}, {"gates": {}})["gates"]


def test_the_gate_reads_the_recorded_files_of_the_four_stages_and_stops_on_a_page_of_another_vintage(tmp_path, monkeypatch):
    import operation_plan as op
    import material_plan as mpl
    cfg = op.load_config(mr.PROJECT_ROOT)
    try:
        op.read_outputs(mr.PROJECT_ROOT, cfg)
        mpl.read_outputs(mr.PROJECT_ROOT)
    except Exception:                       # noqa: BLE001
        pytest.skip("SKIPPED, not passed: the recorded operation plan or material plan is not on this machine")
    page = os.path.join(mr.PROJECT_ROOT, "forecast", "inventory.html")
    if op.read_page_data(page).get("forecast_vintage") is None:
        pytest.skip("SKIPPED, not passed: the tracked inventory page carries no forecast_vintage yet")
    monkeypatch.setattr(mr, "FORECAST_DIR", os.path.join(mr.PROJECT_ROOT, "forecast"))
    assert mr.step7d_vintage_gate(False, str(tmp_path))["passed"]
    real = op.read_page_data
    monkeypatch.setattr(op, "read_page_data", lambda p: dict(real(p), forecast_vintage={"vintage_id": 99}))
    with pytest.raises(mr.MonthlyRefreshAbort, match="G2"):
        mr.step7d_vintage_gate(False, str(tmp_path))
