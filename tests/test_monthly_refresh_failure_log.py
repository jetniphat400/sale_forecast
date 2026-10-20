"""The monthly runner always ends with a run log (task C2b, METRICS.md Sec.28) and a dry run exercises the
write-and-read-back of the forward-test log.

* Any step failure, including an uncaught exception, ends the run with a run log that names the failed step, the
  error and the steps not run, records no commit and no push, and makes the command exit non-zero.
* In dry-run mode the new vintage is appended to a TEMPORARY copy of the log, read back and verified exactly
  as step 6 verifies the real log; the real log and metadata are never touched.

Steps are replaced by stand-ins and the log/metadata paths point into a temporary folder: no database, no real
output file, no tracked file is used or modified.
"""
import hashlib
import json
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import monthly_refresh as mr
import vintage_series

from forward_test_common import (ForwardTestConsistencyError, append_vintage_and_hash, compute_row_integrity_hash,
                                 save_metadata)

from test_forward_test_integrity import base_entry, make_rows

FIT_SERIES = b"year_month,itemcode,qty\n2026-08,A-1,3\n"

pytestmark = pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1",
                                reason="already running inside a dry-run copy of the project")


def _stub_steps(monkeypatch, fail_step=None, exc=RuntimeError("boom: not a MonthlyRefreshAbort")):
    """Replace every step with a stand-in that succeeds, except `fail_step` which raises `exc`."""
    def ok(name, result=None):
        def step(*a, **k):
            if name == fail_step:
                raise exc
            return result if result is not None else {"stub": name}
        return step

    monkeypatch.setattr(mr, "step1_pull_data", ok("1_pull_data", {"snapshot_pull_date": "2026-10-02 07:45:57"}))
    monkeypatch.setattr(mr, "step2_validate", ok("2_validate"))
    monkeypatch.setattr(mr, "step3_frozen_snapshot", ok("3_frozen_snapshot"))
    monkeypatch.setattr(mr, "step4_backtest", ok("4_backtest", {"per_division_comparison_topdown": []}))
    monkeypatch.setattr(mr, "step5_new_vintage", ok("5_new_forward_test_vintage", {"skipped": True}))
    monkeypatch.setattr(mr, "step6_fill_and_score", ok("6_fill_and_score"))
    monkeypatch.setattr(mr, "step7_rebuild_pages", ok("7_rebuild_pages"))
    monkeypatch.setattr(mr, "step7b_operation_plan", ok("7b_operation_plan"))
    monkeypatch.setattr(mr, "step7c_material_plan", ok("7c_material_plan"))
    monkeypatch.setattr(mr, "step7e_trend_tab", ok("7e_trend_tab"))
    monkeypatch.setattr(mr, "step7f_exec_summary", ok("7f_exec_summary"))
    monkeypatch.setattr(mr, "step8_run_tests", ok("8_run_tests", {"passed": True}))
    monkeypatch.setattr(mr, "step9_scan_sensitive_content", ok("9_scan_sensitive_content", {"passed": True}))
    monkeypatch.setattr(mr, "step10_change_magnitude", ok("10_change_magnitude", {"passed": True}))
    pushed = []
    monkeypatch.setattr(mr, "step11_commit_and_push", lambda *a, **k: pushed.append(a) or {"pushed": False})
    return pushed


def _run(monkeypatch, tmp_path, **kw):
    monkeypatch.setattr(mr, "RUNS_DIR", str(tmp_path / "runs"))
    return mr.main(dry_run=True, sandbox=True, run_id="t1", run_log_dir=str(tmp_path / "logs"), offline=True,
                   skip_tests=True, **kw)


@pytest.mark.parametrize("fail_step,exc", [
    ("2_validate", RuntimeError("boom: not a MonthlyRefreshAbort")),
    ("6_fill_and_score", ForwardTestConsistencyError("vintage 2: row_integrity_hash mismatch")),
    ("4_backtest", mr.MonthlyRefreshAbort("a deliberate abort")),
    ("10_change_magnitude", KeyError("missing threshold")),
])
def test_any_step_failure_writes_a_run_log_and_ends_the_run(monkeypatch, tmp_path, fail_step, exc):
    pushed = _stub_steps(monkeypatch, fail_step, exc)
    with pytest.raises(type(exc)):
        _run(monkeypatch, tmp_path)
    log_path = tmp_path / "logs" / "monthly_refresh_t1.json"
    assert log_path.exists(), "a failed run wrote no run log"
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert log["failed_step"] == fail_step and log["aborted_at_step"] == fail_step
    assert log["error"]["type"] == type(exc).__name__ and str(exc.args[0]) in log["error"]["message"]
    assert log["steps"][fail_step]["status"] in ("FAILED", "ABORTED")
    assert log["steps_not_run"] == mr.STEP_ORDER[mr.STEP_ORDER.index(fail_step) + 1:]
    assert log["committed"] is False and log["pushed"] is False
    assert not pushed, "step 11 (commit and push) ran after a failed step"
    ran = [k for k, v in log["steps"].items() if v["status"] == "ok"]
    assert ran == mr.STEP_ORDER[:mr.STEP_ORDER.index(fail_step)]


def test_a_completed_run_has_no_failure_fields(monkeypatch, tmp_path):
    _stub_steps(monkeypatch)
    log = _run(monkeypatch, tmp_path)
    assert "aborted_at_step" not in log and "failed_step" not in log
    assert [k for k in log["steps"]] == mr.STEP_ORDER


def test_the_command_exits_non_zero_when_the_run_failed_and_zero_when_it_completed(monkeypatch):
    monkeypatch.setattr(mr, "main", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert mr.cli(["--dry-run"]) == 1
    monkeypatch.setattr(mr, "main", lambda **k: {"steps": {}, "aborted_at_step": "6_fill_and_score"})
    assert mr.cli(["--dry-run"]) == 1
    monkeypatch.setattr(mr, "main", lambda **k: {"steps": {}})
    assert mr.cli(["--dry-run"]) == 0


# ------------------------------------------------------------------ dry run exercises write and read-back

def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _setup_log(tmp_path, monkeypatch):
    log = str(tmp_path / "forward_test_log_all_divisions.csv")
    meta = str(tmp_path / "forward_test_log_all_divisions_metadata.json")
    entry1 = append_vintage_and_hash(log, make_rows(1, "2026-09-07", "2026-07"), base_entry(1))
    save_metadata(meta, {"1": entry1})
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", log)
    monkeypatch.setattr(mr, "FORWARD_TEST_METADATA_PATH", meta)
    monkeypatch.setattr(mr, "COMPARATOR_LOG_PATH", str(tmp_path / "comparator_log.csv"))
    monkeypatch.setattr(mr, "COMPARATOR_METADATA_PATH", str(tmp_path / "comparator_metadata.json"))
    monkeypatch.setattr(mr, "SHADOW_LOG_PATH", str(tmp_path / "shadow_log.csv"))
    monkeypatch.setattr(mr, "SHADOW_METADATA_PATH", str(tmp_path / "shadow_metadata.json"))
    monkeypatch.setattr(vintage_series, "SERIES_DIR", str(tmp_path / "vintage_series"))   # never the real folder
    return log, meta


def _fake_computed(vintage_id=2):
    return {"vintage_id": vintage_id, "rows_df": make_rows(vintage_id), "metadata_entry": {**base_entry(vintage_id), **vintage_series.metadata_fields(FIT_SERIES, vintage_id)},
            "fit_series_bytes": FIT_SERIES, "n_rows": 9, "six_month_item_forecast_total_by_division": {"PEM101": 1.0},
            "comparator_rows_df": make_rows(vintage_id), "comparator_metadata_entry": {**base_entry(vintage_id), "ma_window_by_division": {"PEM101": 3}},
            "shadow_rows_df": make_rows(vintage_id), "shadow_metadata_entry": {**base_entry(vintage_id), "model_family": "shadow"}}


def test_a_dry_run_appends_the_new_vintage_to_a_temporary_copy_reads_it_back_and_verifies(monkeypatch, tmp_path):
    log, meta = _setup_log(tmp_path, monkeypatch)
    before = (_sha(log), _sha(meta))
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed())
    result = mr.step5_new_vintage(dry_run=True, force_new_vintage=True)
    assert result["rehearsal"]["verified"] is True and result["rehearsal"]["row_hash_scheme"] == "csv_readback_v1"
    assert (_sha(log), _sha(meta)) == before, "a dry run touched the real forward-test log or metadata"


def test_a_dry_run_rehearsal_fails_when_the_hash_would_not_survive_the_write(monkeypatch, tmp_path):
    """The pre-fix behaviour: the hash computed from in-memory rows (empty type as "") and checked under the
    read-back scheme. This is what 2026-10-02's real run did, and what a dry run could not see."""
    _setup_log(tmp_path, monkeypatch)

    def old_way(log_path, rows_df, metadata_entry):
        rows_df.to_csv(log_path, mode="a", header=False, index=False)
        entry = dict(metadata_entry)
        entry["row_integrity_hash"] = compute_row_integrity_hash(rows_df)       # in memory, default scheme
        return entry

    monkeypatch.setattr(mr, "append_vintage_and_hash", old_way)
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed())
    with pytest.raises(ForwardTestConsistencyError, match="vintage 2"):
        mr.step5_new_vintage(dry_run=True, force_new_vintage=True)


def test_a_real_run_writes_the_vintage_with_a_hash_taken_from_the_read_back_rows(monkeypatch, tmp_path):
    log, meta = _setup_log(tmp_path, monkeypatch)
    monkeypatch.setattr(mr, "compute_new_vintage", lambda: _fake_computed())
    result = mr.step5_new_vintage(dry_run=False, force_new_vintage=True)
    assert result["written"] is True and result["row_hash_scheme"] == "csv_readback_v1"
    from score_forward_test_all_divisions import verify_consistency
    from forward_test_common import load_metadata, read_forward_test_log
    verify_consistency(read_forward_test_log(log), load_metadata(meta))
    assert sorted(load_metadata(meta)) == ["1", "2"]


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Login safety round 2 (Prompt 23): LoginRefused (SQLSTATE 28000) stops every job with exit code 3 and writes a shared lock; any other failure of an auxiliary pull is a WARN and a partial run
# (exit code 2); one login attempt per failure; the preflight comes before any login; and the monthly run's weekday-only run day. Fakes only: the real database, the network, the real lock file
# and the real state file are never touched.
# ---------------------------------------------------------------------------------------------------------------------------------------------
import contextlib as _contextlib  # noqa: E402
import subprocess as _subprocess  # noqa: E402
from datetime import date as _date  # noqa: E402

import db as _db  # noqa: E402


class _Proc:
    def __init__(self, rc=0):
        self.returncode, self.stdout, self.stderr = rc, "", "stderr text"


def _step1_env(monkeypatch, run_rc):
    """Step 1 with a reachable host, a fake run_script that returns run_rc[i] for the i-th call (0 after the list), and a stand-in monthly file. Returns the list of scripts started."""
    _db.reset_login_state()
    started = []

    def fake_run_script(script, args=None):
        started.append(script)
        rc = run_rc[len(started) - 1] if len(started) <= len(run_rc) else 0
        return _Proc(rc)
    monkeypatch.setenv("DB_SERVER", "dbhost.invalid\\INSTANCE")
    monkeypatch.setattr(mr, "check_tcp_reachable", lambda *a, **k: (True, None))
    monkeypatch.setattr(mr, "run_script", fake_run_script)
    monkeypatch.setattr(mr, "_DB_STAGE_FAILURE", None)
    mr._PARTIAL_WARNINGS.clear()
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: pd.DataFrame({"snapshot_pull_date": ["2026-10-05 07:00:01"], "itemcode": ["A"], "division": ["PEM101"]}))
    return started


# ------------------------------------------------------------------ the run day
@pytest.mark.parametrize("year,month,expected", [(2026, 11, "2026-11-05"), (2026, 12, "2026-12-07"), (2027, 6, "2027-06-07"), (2027, 9, "2027-09-06"), (2027, 2, "2027-02-05")])
def test_the_run_day_is_the_first_weekday_on_or_after_the_5th(year, month, expected):
    d = mr.run_day(year, month)
    assert d.isoformat() == expected and d.weekday() < 5 and d.day >= 5


def test_the_run_day_follows_the_configured_base_day():
    assert mr.run_day(2026, 12, base_day=12).isoformat() == "2026-12-14"           # 12 Dec 2026 is a Saturday
    assert mr.run_day(2026, 12, base_day=1).isoformat() == "2026-12-01"


class _Today(_date):
    fixed = _date(2026, 12, 7)

    @classmethod
    def today(cls):
        return cls.fixed


def _cli_env(monkeypatch, tmp_path, today, main_log=None, main_exc=None):
    """The monthly command with a fixed day, a temporary state file, no lock file and no publishing check; returns the list of main() calls."""
    _Today.fixed = today
    monkeypatch.setattr(mr, "date", _Today)
    monkeypatch.setattr(mr, "MONTHLY_STATE_PATH", str(tmp_path / "state" / "monthly_run_state.json"))
    monkeypatch.setattr(mr, "_runner_lock", lambda real_run: _contextlib.nullcontext())
    import daily_stock_job
    monkeypatch.setattr(daily_stock_job, "check_publishing_setup", lambda *a, **k: {})
    calls = []

    def fake_main(**k):
        calls.append(k)
        if main_exc:
            raise main_exc
        return main_log if main_log is not None else {"run_id": "r1", "steps": {}}
    monkeypatch.setattr(mr, "main", fake_main)
    monkeypatch.setattr(_db, "preflight", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the preflight ran")))
    return calls


def test_a_weekend_is_not_a_run_day_nothing_runs_and_no_lock_check_preflight_or_login_happens(monkeypatch, tmp_path):
    for day in (_date(2026, 12, 5), _date(2026, 12, 6)):                                   # Saturday and Sunday
        calls = _cli_env(monkeypatch, tmp_path, day)
        monkeypatch.setattr(_db, "check_refused_lock", lambda: (_ for _ in ()).throw(AssertionError("the lock was checked")))
        assert mr.cli([]) == 0 and calls == []
    assert not os.path.exists(mr.MONTHLY_STATE_PATH)


def test_the_run_day_runs_once_and_a_second_start_in_the_same_month_does_nothing(monkeypatch, tmp_path):
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7))
    assert mr.cli([]) == 0 and len(calls) == 1
    assert mr.read_monthly_state()["last_success_month"] == "2026-12"
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 8))
    assert mr.cli([]) == 0                                                                   # already done this month: no second run
    assert mr.monthly_run_due(_date(2026, 12, 9), mr.read_monthly_state())[1].startswith("already done")


def test_before_the_run_day_nothing_runs_and_a_missed_run_day_is_made_up_on_the_next_weekday_once(monkeypatch, tmp_path):
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 4))                              # Friday before the run day (Monday 7 December)
    assert mr.cli([]) == 0 and calls == []
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 9))                              # the run day was missed (machine off): Wednesday makes it up
    assert mr.cli([]) == 0 and len(calls) == 1
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 10))                             # and only once
    assert mr.cli([]) == 0 and calls == []
    assert mr.monthly_run_due(_date(2026, 12, 9), {}) == (True, "run day made up (the run day was 2026-12-07)")


def test_a_failed_or_partial_run_is_not_marked_done_and_runs_again_on_the_next_weekday(monkeypatch, tmp_path):
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log={"run_id": "r1", "steps": {}, "aborted_at_step": "6_fill_and_score"})
    assert mr.cli([]) == 1 and not os.path.exists(mr.MONTHLY_STATE_PATH)                    # a failed run
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 8), main_log={"run_id": "r2", "steps": {}, "partial": True, "warnings": ["WARN: x"]})
    assert mr.cli([]) == 2 and len(calls) == 1 and not os.path.exists(mr.MONTHLY_STATE_PATH)   # a partial run: tried again, not marked
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 9))
    assert mr.cli([]) == 0 and len(calls) == 1 and mr.read_monthly_state()["last_success_month"] == "2026-12"


def test_a_manual_run_can_ignore_the_run_day(monkeypatch, tmp_path):
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 6))
    assert mr.cli(["--ignore-run-day"]) == 0 and len(calls) == 1


# ------------------------------------------------------------------ exit codes
def test_exit_codes_login_refused_is_3_partial_is_2_failure_is_1_success_is_0(monkeypatch, tmp_path):
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_exc=mr.MonthlyLoginRefused("a stage ended with code 3"))
    assert mr.cli([]) == 3 and os.path.exists(_db.REFUSED_LOCK_PATH)                         # the lock is written
    os.remove(_db.REFUSED_LOCK_PATH)
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_exc=_db.LoginRefused("refused in step 6"))
    assert mr.cli([]) == 3
    os.remove(_db.REFUSED_LOCK_PATH)
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_exc=RuntimeError("boom"))
    assert mr.cli([]) == 1
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log={"run_id": "r", "steps": {}, "partial": True})
    assert mr.cli([]) == 2
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7))
    assert mr.cli([]) == 0


def test_exit_code_3_from_a_stage_stops_every_later_database_stage_and_the_run(monkeypatch):
    started = _step1_env(monkeypatch, run_rc=[0, 0, 3])                                      # the main pull and the pilot file work, the inventory pull is refused
    with pytest.raises(mr.MonthlyLoginRefused, match="exit code 3"):
        mr.step1_pull_data(False, offline=False)
    assert started == ["load_data_all_divisions.py", "load_data_full.py", "build_inventory_dataset.py"]      # the later pulls were never started
    assert mr._DB_STAGE_FAILURE == "inventory.json pulls"
    started = _step1_env(monkeypatch, run_rc=[3])                                            # the main pull itself is refused
    with pytest.raises(mr.MonthlyLoginRefused):
        mr.step1_pull_data(False, offline=False)
    assert started == ["load_data_all_divisions.py"]


def test_any_other_failure_of_an_auxiliary_pull_keeps_the_previous_file_and_warns_and_the_step_goes_on(monkeypatch):
    started = _step1_env(monkeypatch, run_rc=[0, 0, 1])                                      # the inventory pull fails, but not by a refused login
    out = mr.step1_pull_data(False, offline=False)                                           # the step completes
    assert started == ["load_data_all_divisions.py", "load_data_full.py", "build_inventory_dataset.py", "material_plan.py", "build_trend_tab.py", "cube_ces_pull.py"]
    assert out["inventory_pull"]["refreshed"] is False and "exited 1" in out["inventory_pull"]["not_refreshed_reason"]
    failed = [w for w in mr._PARTIAL_WARNINGS if "exited 1" in w]
    assert len(failed) == 1 and failed[0].startswith("WARN:") and "inventory.json pulls" in failed[0]
    assert all("was not rewritten" in w for w in mr._PARTIAL_WARNINGS if w not in failed)          # the fake stages exit 0 and write nothing: each is its own WARN since Prompt 30


def test_a_warning_from_an_auxiliary_stage_is_in_the_run_log_and_the_run_is_partial(monkeypatch, tmp_path):
    _stub_steps(monkeypatch)
    monkeypatch.setattr(mr, "step1_pull_data", lambda *a, **k: mr._PARTIAL_WARNINGS.append("WARN: a stage failed") or {"snapshot_pull_date": "2026-10-02 07:45:57"})
    log = _run(monkeypatch, tmp_path)
    assert log["partial"] is True and log["warnings"] == ["WARN: a stage failed"] and "aborted_at_step" not in log


def test_in_step_4_exit_code_3_stops_the_other_database_script_and_exit_code_1_only_warns(monkeypatch, tmp_path):
    monkeypatch.setattr(mr, "_DB_STAGE_FAILURE", None)
    mr._PARTIAL_WARNINGS.clear()
    monkeypatch.setattr(mr, "SUMMARY_DIR", str(tmp_path))
    started = []
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: started.append(script) or _Proc(3))
    first = mr._run_regeneration_step("order notice", os.path.join("investigations", "order_leadtime.py"), "a.csv")
    second = mr._run_regeneration_step("delivery", os.path.join("investigations", "delivery_performance.py"), "b.csv")
    assert started == [os.path.join("investigations", "order_leadtime.py")] and first["returncode"] == 3
    assert second["refreshed"] is False and "no further login attempt" in second["not_refreshed_reason"]
    with pytest.raises(mr.MonthlyLoginRefused):
        mr._abort_if_a_database_stage_failed("Step 4")
    monkeypatch.setattr(mr, "_DB_STAGE_FAILURE", None)
    started.clear()
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: started.append(script) or _Proc(1))
    mr._run_regeneration_step("order notice", os.path.join("investigations", "order_leadtime.py"), "a.csv")
    mr._run_regeneration_step("delivery", os.path.join("investigations", "delivery_performance.py"), "b.csv")
    assert len(started) == 2 and len(mr._PARTIAL_WARNINGS) == 2                                 # both ran; two WARN lines; no abort
    mr._abort_if_a_database_stage_failed("Step 4")


# ------------------------------------------------------------------ the preflight, the lock and the login helper
def test_an_unreachable_host_makes_zero_login_attempts_and_the_run_ends_non_zero(monkeypatch, tmp_path):
    _db.reset_login_state()
    started = []
    monkeypatch.setenv("DB_SERVER", "dbhost.invalid")
    monkeypatch.setattr(mr.socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("timed out")))     # the real preflight code, a fake network
    monkeypatch.setattr(mr, "run_script", lambda *a, **k: started.append(a) or _Proc(0))
    with pytest.raises(mr.MonthlyRefreshAbort, match=r"DB host unreachable \(off org network\?\)") as exc:
        mr.step1_pull_data(False, offline=False)
    assert "dbhost" not in str(exc.value)                                                    # the host is never written into a message
    assert started == [] and _db.login_attempts() == 0
    pushed = _stub_steps(monkeypatch, "1_pull_data", exc.value)
    with pytest.raises(mr.MonthlyRefreshAbort):
        _run(monkeypatch, tmp_path)
    log = json.loads((tmp_path / "logs" / "monthly_refresh_t1.json").read_text(encoding="utf-8"))
    assert log["failed_step"] == "1_pull_data" and "DB host unreachable" in log["error"]["message"] and not pushed


def test_a_main_pull_that_fails_for_another_reason_aborts_the_run_with_exit_1_not_3(monkeypatch):
    started = _step1_env(monkeypatch, run_rc=[1])
    with pytest.raises(mr.MonthlyRefreshAbort, match="Never retrying the database") as exc:
        mr.step1_pull_data(False, offline=False)
    assert not isinstance(exc.value, mr.MonthlyLoginRefused) and started == ["load_data_all_divisions.py"]


class _FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class _FakeEngine:
    def __init__(self, error=None):
        self.error, self.connects = error, 0

    def connect(self):
        self.connects += 1
        if self.error is not None:
            raise self.error
        return _FakeConn()

    def dispose(self):
        pass


class _DriverError(Exception):
    """A stand-in for pyodbc.Error: args = (sqlstate, message)."""


def _refused():
    return _DriverError("28000", "[28000] [Driver][SQL Server]Login failed for user 'someone'. (18456) (SQLDriverConnect)")


def test_sqlstate_28000_is_detected_first_then_the_native_code_and_the_message_only_as_a_fallback():
    assert _db.is_login_refused(_refused())
    wrapped = RuntimeError("(pyodbc.Error) wrapped")
    wrapped.orig = _DriverError("28000", "no useful text")                                   # SQLAlchemy keeps the driver's error in .orig
    assert _db.is_login_refused(wrapped)
    assert _db.is_login_refused(_DriverError("42000", "[Driver] error 18456 while connecting"))     # the driver's own native code
    assert _db.is_login_refused(RuntimeError("Login failed for user"))                       # fallback: text only
    assert not _db.is_login_refused(_DriverError("08001", "[08001] [Driver] Named Pipes Provider: Could not open a connection"))
    assert not _db.is_login_refused(_DriverError("HYT00", "Login timeout expired"))
    assert not _db.is_login_refused(ValueError("a query returned nothing"))


def test_login_refused_is_not_an_exception_so_no_except_exception_can_swallow_it():
    assert issubclass(_db.LoginRefused, BaseException) and not issubclass(_db.LoginRefused, Exception)
    swallowed = False
    try:
        try:
            raise _db.LoginRefused("x")
        except Exception:      # noqa: BLE001
            swallowed = True
    except _db.LoginRefused:
        pass
    assert not swallowed


def test_a_refused_login_makes_one_attempt_writes_the_lock_and_every_later_call_is_refused_at_once(monkeypatch):
    _db.reset_login_state()
    engine = _FakeEngine(_refused())
    monkeypatch.setattr(_db, "get_connection", lambda: engine)
    with pytest.raises(_db.LoginRefused) as exc:
        _db.run_query("SELECT 1")
    assert "someone" not in str(exc.value) and "someone" not in repr(exc.value.__cause__ or "")      # the login name is never in the message
    assert engine.connects == 1 and _db.login_attempts() == 1
    lock = json.loads(open(_db.REFUSED_LOCK_PATH, encoding="utf-8").read())
    assert set(lock) == {"refused_at", "job"}                                                # the timestamp and the job name only
    with pytest.raises(_db.LoginRefused, match="fix the credentials, then delete"):
        _db.run_query("SELECT 2")
    with pytest.raises(_db.LoginRefused):
        with _db.session():
            pass
    assert engine.connects == 1 and _db.login_attempts() == 1                               # no further attempt
    _db.reset_login_state()


def test_another_login_failure_is_not_a_refusal_and_writes_no_lock(monkeypatch):
    _db.reset_login_state()
    engine = _FakeEngine(_DriverError("08001", "[08001] could not open a connection"))
    monkeypatch.setattr(_db, "get_connection", lambda: engine)
    with pytest.raises(_DriverError):
        _db.run_query("SELECT 1")
    assert not os.path.exists(_db.REFUSED_LOCK_PATH)
    _db.reset_login_state()


def test_the_lock_blocks_the_preflight_the_login_and_the_monthly_command_and_is_never_deleted_by_the_code(monkeypatch, tmp_path):
    _db.reset_login_state()
    _db.write_refused_lock("some_job.py")
    monkeypatch.setattr(_db.socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the network was touched")))
    monkeypatch.setenv("DB_SERVER", "dbhost.invalid")
    with pytest.raises(_db.LoginRefused, match="fix the credentials, then delete output/state/db_login_refused.lock"):
        _db.preflight()                                                                      # before the TCP connect
    engine = _FakeEngine()
    monkeypatch.setattr(_db, "get_connection", lambda: engine)
    with pytest.raises(_db.LoginRefused):
        _db.run_query("SELECT 1")                                                            # before the login
    assert engine.connects == 0
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7))
    assert mr.cli([]) == 3 and calls == []                                                   # the monthly command stops before step 1
    assert os.path.exists(_db.REFUSED_LOCK_PATH)                                             # still there: only the user deletes it


def test_an_uncaught_login_refused_ends_any_script_with_exit_code_3_and_writes_the_lock(tmp_path):
    lock = str(tmp_path / "x.lock")
    code = ("import sys; sys.path.insert(0, r'%s'); import db; db.REFUSED_LOCK_PATH = r'%s'; raise db.LoginRefused('refused')" % (os.path.join(PROJECT_ROOT, "src"), lock))
    r = _subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 3 and os.path.exists(lock) and "DB LOGIN REFUSED" in r.stderr
    assert set(json.loads(open(lock, encoding="utf-8").read())) == {"refused_at", "job"}


def test_the_db_helper_session_logs_in_once_for_many_queries(monkeypatch):
    _db.reset_login_state()
    engine = _FakeEngine()
    monkeypatch.setattr(_db, "get_connection", lambda: engine)
    monkeypatch.setattr(_db.pd, "read_sql", lambda sql, conn: pd.DataFrame({"n": [1]}))
    with _db.session():
        assert _db.run_query("SELECT 1")["n"].iloc[0] == 1 and len(_db.run_query("SELECT 2")) == 1
    assert engine.connects == 1 and _db.login_attempts() == 1
    _db.reset_login_state()


def test_the_preflight_is_a_plain_tcp_connect_that_never_logs_in(monkeypatch):
    _db.reset_login_state()
    seen = []
    monkeypatch.setenv("DB_SERVER", "somehost,14330\\INSTANCE")
    monkeypatch.setattr(_db.socket, "create_connection", lambda addr, timeout=None: seen.append((addr, timeout)) or _FakeConn())
    out = _db.preflight(timeout=2.0)
    assert out["reachable"] is True and seen == [(("somehost", 14330), 2.0)] and _db.login_attempts() == 0
    monkeypatch.setenv("DB_SERVER", "somehost\\INSTANCE")
    _db.preflight()
    assert seen[-1][0] == ("somehost", 1433)
    monkeypatch.setattr(_db.socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("no route")))
    with pytest.raises(_db.DatabaseUnreachableError, match=r"DB host unreachable \(off org network\?\)") as exc:
        _db.require_reachable()
    assert "somehost" not in str(exc.value) and _db.login_attempts() == 0


# ------------------------------------------------------------------ Prompt 30: a stage that exits 0 without rewriting its declared output file is partial (WARN, exit 2)
def _unwritten_env(monkeypatch, tmp_path):
    monkeypatch.setattr(mr, "_DB_STAGE_FAILURE", None)
    mr._PARTIAL_WARNINGS.clear()
    monkeypatch.setattr(mr, "SUMMARY_DIR", str(tmp_path))
    return tmp_path / "out.csv"


def test_a_pull_stage_that_exits_0_without_rewriting_its_file_is_a_warning_and_a_rewritten_file_is_not(monkeypatch, tmp_path):
    out = _unwritten_env(monkeypatch, tmp_path)
    out.write_text("a,b\n1,2\n")
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: _Proc(0))                  # exit 0, the file untouched: same mtime and same sha256
    r = mr._pull_stage("aux pull", "aux.py", str(out))
    assert r["refreshed"] is False and r["not_refreshed_reason"] == "output file not rewritten"
    assert len(mr._PARTIAL_WARNINGS) == 1 and mr._PARTIAL_WARNINGS[0].startswith("WARN: the stage 'aux pull' exited 0 but its output file was not rewritten")
    mr._PARTIAL_WARNINGS.clear()

    def rewrite(script, args=None):
        out.write_text("a,b\n3,4\n")
        return _Proc(0)
    monkeypatch.setattr(mr, "run_script", rewrite)
    assert mr._pull_stage("aux pull", "aux.py", str(out))["refreshed"] is True and mr._PARTIAL_WARNINGS == []
    os.remove(out)                                                                              # a file that was never created is not rewritten either
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: _Proc(0))
    mr._pull_stage("aux pull", "aux.py", str(out))
    assert len(mr._PARTIAL_WARNINGS) == 1
    mr._PARTIAL_WARNINGS.clear()
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: _Proc(1))                  # a non-zero exit keeps its own WARN (not a second one)
    mr._pull_stage("aux pull", "aux.py", str(out))
    assert len(mr._PARTIAL_WARNINGS) == 1 and "exited 1" in mr._PARTIAL_WARNINGS[0]


def test_a_regeneration_step_that_exits_0_without_rewriting_its_file_is_a_warning(monkeypatch, tmp_path):
    _unwritten_env(monkeypatch, tmp_path)
    (tmp_path / "x.csv").write_text("a\n1\n")
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: _Proc(0))
    r = mr._run_regeneration_step("regen", "regen.py", "x.csv")
    assert r["refreshed"] is False and len(mr._PARTIAL_WARNINGS) == 1 and "regen" in mr._PARTIAL_WARNINGS[0]


def test_the_run_with_such_a_stage_is_partial_and_the_command_ends_with_exit_code_2(monkeypatch, tmp_path):
    out = _unwritten_env(monkeypatch, tmp_path)
    out.write_text("a\n1\n")
    _stub_steps(monkeypatch)
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: _Proc(0))
    monkeypatch.setattr(mr, "step1_pull_data", lambda *a, **k: mr._pull_stage("aux pull", "aux.py", str(out)) and {"snapshot_pull_date": "2026-10-02 07:45:57"})
    log = _run(monkeypatch, tmp_path)
    assert log["partial"] is True and "aborted_at_step" not in log and len(log["warnings"]) == 1 and "was not rewritten" in log["warnings"][0]
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log=log)
    assert mr.cli([]) == 2 and not os.path.exists(mr.MONTHLY_STATE_PATH)              # not marked done: it runs again on the next weekday


# ---- Prompt 33: a failed gate must not look like a success

def _held_gate_log(monkeypatch, tmp_path, failing="tests"):
    """A run (fakes only) in which one gate fails: step 8 (tests) or a change-magnitude gate of step 10."""
    _stub_steps(monkeypatch)
    if failing == "tests":
        monkeypatch.setattr(mr, "step8_run_tests", lambda *a, **k: {"passed": False, "summary_line": "2 failed, 800 passed"})
    else:
        monkeypatch.setattr(mr, "step10_change_magnitude", lambda *a, **k: {"passed": False, "gates": {"six_month_forecast": {"status": "failed", "reason": "a division moved more than the limit"}}})
    return _run(monkeypatch, tmp_path)


def test_a_failed_gate_is_named_in_the_run_log_with_its_reason(monkeypatch, tmp_path):
    log = _held_gate_log(monkeypatch, tmp_path, "tests")
    assert log["gates_failed"] == {"tests": "2 failed, 800 passed"} and log["push_held"]["held"] is True and log["push_held"]["gates"] == ["tests"]
    log2 = _held_gate_log(monkeypatch, tmp_path, "step10")
    assert log2["gates_failed"] == {"step10_six_month_forecast": "a division moved more than the limit"}


def test_a_held_gate_ends_with_exit_code_4_writes_no_state_and_the_next_weekday_runs_again(monkeypatch, tmp_path):
    assert mr.EXIT_GATE_HELD == 4 and len({mr.EXIT_OK, mr.EXIT_ABORTED, mr.EXIT_PARTIAL, mr.EXIT_LOGIN_REFUSED, mr.EXIT_GATE_HELD}) == 5
    log = _held_gate_log(monkeypatch, tmp_path, "tests")
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log=log)
    assert mr.cli([]) == 4 and len(calls) == 1
    assert not os.path.exists(mr.MONTHLY_STATE_PATH), "a held gate wrote the success state"
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 8), main_log=log)               # the next weekday: the run is due again
    assert mr.monthly_run_due(_date(2026, 12, 8), mr.read_monthly_state())[0] is True
    assert mr.cli([]) == 4 and len(calls) == 1 and not os.path.exists(mr.MONTHLY_STATE_PATH)
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 9), main_log={"run_id": "r2", "steps": {}})       # a later run whose gates pass is a normal success
    assert mr.cli([]) == 0 and mr.read_monthly_state()["last_success_month"] == "2026-12"


def test_a_normal_run_still_writes_the_state_and_exits_0(monkeypatch, tmp_path):
    _stub_steps(monkeypatch)
    log = _run(monkeypatch, tmp_path)
    assert "gates_failed" not in log and "push_held" not in log
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log=log)
    assert mr.cli([]) == 0 and mr.read_monthly_state()["last_success_month"] == "2026-12"


def test_a_dry_run_reports_a_failed_gate_in_its_log_but_never_exits_4(monkeypatch, tmp_path):
    log = _held_gate_log(monkeypatch, tmp_path, "tests")
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log=log)
    assert mr.cli(["--dry-run"]) == 0 and not os.path.exists(mr.MONTHLY_STATE_PATH)


# ---- Prompt 34, item 3: every gate failure and every failed or held push ends a real run with exit code 4 and writes no success state

import ast as _ast
import subprocess as _subprocess

GATE_MARKERS = ["Step 2 (validate) ABORTED", "Step 7d STOPPED", "Step 5 ABORTED: leakage guard refused", "Step 11 STOPPED before staging",
                "Step 7e (Trend tab) gate FAILED", "Step 7f (executive summary) gate FAILED"]


def test_every_gate_raise_site_uses_the_gate_exception():
    tree = _ast.parse(open(mr.__file__, encoding="utf-8").read())
    seen = {m: [] for m in GATE_MARKERS}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Raise) and isinstance(node.exc, _ast.Call) and node.exc.args and isinstance(node.exc.func, _ast.Name):
            text = _ast.unparse(node.exc.args[0])
            for m in GATE_MARKERS:
                if m in text:
                    seen[m].append(node.exc.func.id)
    assert all(seen[m] for m in GATE_MARKERS), {m: v for m, v in seen.items() if not v}
    assert all(set(v) == {"MonthlyGateFailed"} for v in seen.values()), seen
    assert issubclass(mr.MonthlyGateFailed, mr.MonthlyRefreshAbort)


def _stub_all(monkeypatch):
    pushed = _stub_steps(monkeypatch)
    monkeypatch.setattr(mr, "step7d_vintage_gate", lambda *a, **k: {"vintage_id": 2})
    return pushed


@pytest.mark.parametrize("step,fn", [("2_validate", "step2_validate"), ("5_new_forward_test_vintage", "step5_new_vintage"), ("7d_vintage_gate", "step7d_vintage_gate"),
                                     ("7e_trend_tab", "step7e_trend_tab"), ("7f_exec_summary", "step7f_exec_summary")])
def test_a_failed_gate_step_names_itself_in_the_run_log_and_a_real_run_ends_with_exit_code_4_and_no_state(monkeypatch, tmp_path, step, fn):
    _stub_all(monkeypatch)
    exc = mr.MonthlyGateFailed(f"{step} gate failed for the test")
    monkeypatch.setattr(mr, fn, lambda *a, **k: (_ for _ in ()).throw(exc))
    with pytest.raises(mr.MonthlyGateFailed):
        _run(monkeypatch, tmp_path)
    log = json.loads((tmp_path / "logs" / "monthly_refresh_t1.json").read_text(encoding="utf-8"))
    assert log["failed_step"] == step and "gate failed for the test" in log["error"]["message"]
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_exc=exc)
    assert mr.cli([]) == 4 and len(calls) == 1 and not os.path.exists(mr.MONTHLY_STATE_PATH)
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_exc=exc)
    assert mr.cli(["--dry-run"]) == 1                                                       # a dry run keeps its behaviour: a plain failure
    assert mr.monthly_run_due(_date(2026, 12, 8), mr.read_monthly_state())[0] is True


def test_only_the_gate_errors_of_the_trend_and_executive_steps_are_gate_failures(monkeypatch, tmp_path):
    import build_exec_summary as bx
    import build_trend_tab as bt
    staged = str(tmp_path / "staged")
    os.makedirs(staged)
    monkeypatch.setattr(mr, "IN_SANDBOX", True)
    monkeypatch.setattr(bt, "run_build", lambda *a, **k: (_ for _ in ()).throw(bt.TrendTotalsMismatch("totals differ")))
    with pytest.raises(mr.MonthlyGateFailed):
        mr.step7e_trend_tab(False, staged)
    monkeypatch.setattr(bt, "run_build", lambda *a, **k: (_ for _ in ()).throw(bt.TrendTabError("the saved pull is missing")))
    with pytest.raises(mr.MonthlyRefreshAbort) as e1:
        mr.step7e_trend_tab(False, staged)
    assert not isinstance(e1.value, mr.MonthlyGateFailed)
    monkeypatch.setattr(bx, "run_exec_build", lambda *a, **k: (_ for _ in ()).throw(bx.ExecSummaryError("the total row differs")))
    with pytest.raises(mr.MonthlyGateFailed):
        mr.step7f_exec_summary(False, staged)
    monkeypatch.setattr(bx, "run_exec_build", lambda *a, **k: (_ for _ in ()).throw(bt.TrendTabError("markers missing")))
    with pytest.raises(mr.MonthlyRefreshAbort) as e2:
        mr.step7f_exec_summary(False, staged)
    assert not isinstance(e2.value, mr.MonthlyGateFailed)


class _Done:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _step11_env(monkeypatch, github=True, stray=(), changed=True, add_fails=False, commit_fails=False, push_rc=0):
    import daily_stock_job
    monkeypatch.setattr(daily_stock_job, "check_publishing_setup", lambda *a, **k: {})
    monkeypatch.setattr(mr, "check_tcp_reachable", lambda *a, **k: (github, "unreachable" if not github else None))
    monkeypatch.setattr(mr, "stray_changes_outside_generated_list", lambda: list(stray))
    monkeypatch.setattr(mr, "_git_path_changed", lambda p: changed and p == mr.GENERATED_PATHS[0])

    def fake_run(cmd, **k):
        if (cmd[:2] == ["git", "add"] and add_fails) or (cmd[:2] == ["git", "commit"] and commit_fails):
            raise _subprocess.CalledProcessError(1, cmd, stderr="refused")
        return _Done(push_rc if cmd[:2] == ["git", "push"] else 0, "", "rejected" if cmd[:2] == ["git", "push"] and push_rc else "")
    monkeypatch.setattr(mr.subprocess, "run", fake_run)


GATES_OK = ({"passed": True}, {"passed": True}, {"passed": True})


def test_every_held_or_failed_push_is_marked_held(monkeypatch):
    _step11_env(monkeypatch, github=False)
    assert mr.step11_commit_and_push(False, *GATES_OK)["held"] is True                       # GitHub unreachable
    _step11_env(monkeypatch, push_rc=1)
    r = mr.step11_commit_and_push(False, *GATES_OK)
    assert r["held"] is True and r["pushed"] is False and r["committed"] is True              # the push was refused
    _step11_env(monkeypatch, commit_fails=True)
    r = mr.step11_commit_and_push(False, *GATES_OK)
    assert r["held"] is True and r["committed"] is False                                      # the commit was refused
    _step11_env(monkeypatch, add_fails=True)
    assert mr.step11_commit_and_push(False, *GATES_OK)["held"] is True
    _step11_env(monkeypatch, stray=["forecast/other.html"])
    with pytest.raises(mr.MonthlyGateFailed):
        mr.step11_commit_and_push(False, *GATES_OK)                                           # tracked changes outside the generated list
    assert mr.step11_commit_and_push(False, {"passed": False}, {"passed": True}, {"passed": True})["held"] is True      # a failed gate
    _step11_env(monkeypatch)
    ok = mr.step11_commit_and_push(False, *GATES_OK)
    assert ok["pushed"] is True and "held" not in ok
    _step11_env(monkeypatch, changed=False)
    assert "held" not in mr.step11_commit_and_push(False, *GATES_OK)                          # nothing to commit is not a failure


@pytest.mark.parametrize("held_result", [{"pushed": False, "held": True, "reason": "GitHub unreachable"}, {"pushed": False, "held": True, "committed": True, "reason": "git push failed: rejected"}])
def test_a_held_or_failed_push_ends_a_real_run_with_exit_code_4_and_writes_no_state(monkeypatch, tmp_path, held_result):
    _stub_all(monkeypatch)
    monkeypatch.setattr(mr, "step11_commit_and_push", lambda *a, **k: held_result)
    monkeypatch.setattr(mr, "RUNS_DIR", str(tmp_path / "runs"))
    log = mr.main(dry_run=False, sandbox=False, run_id="t3", run_log_dir=str(tmp_path / "logs"), offline=True, skip_tests=True)
    assert log["push_held"]["held"] is True and held_result["reason"] in log["push_held"]["reason"]
    calls = _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log=log)
    assert mr.cli([]) == 4 and len(calls) == 1 and not os.path.exists(mr.MONTHLY_STATE_PATH)
    assert mr.cli(["--dry-run"]) == 0                                                         # a dry run reports it in its log and exits 0
    monkeypatch.undo()
    _stub_all(monkeypatch)
    monkeypatch.setattr(mr, "step11_commit_and_push", lambda *a, **k: {"pushed": True})
    monkeypatch.setattr(mr, "RUNS_DIR", str(tmp_path / "runs"))
    pushed_ok = mr.main(dry_run=False, sandbox=False, run_id="t4", run_log_dir=str(tmp_path / "logs"), offline=True, skip_tests=True)
    assert "push_held" not in pushed_ok
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 8), main_log=pushed_ok)
    assert mr.cli([]) == 0 and mr.read_monthly_state()["last_success_month"] == "2026-12"


def test_a_held_gate_or_push_outranks_a_failed_backup_and_anything_inside_step_11_is_a_held_push(monkeypatch, tmp_path):
    import daily_stock_job
    held = {"run_id": "r9", "steps": {}, "gates_failed": {"tests": "2 failed"}, "push_held": {"held": True, "gates": ["tests"], "reason": ""}, "backup": {"status": "FAILED"}}
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log=held)
    assert mr.cli([]) == 4 and not os.path.exists(mr.MONTHLY_STATE_PATH)                    # the held push is exit code 4 also when the backup failed too
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log={"run_id": "r9", "steps": {}, "backup": {"status": "FAILED"}})
    assert mr.cli([]) == 1                                                                   # a failed backup alone keeps its exit code
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log={"run_id": "r9", "steps": {}, "aborted_at_step": "6_fill_and_score", "gates_failed": {"x": "y"}})
    assert mr.cli([]) == 1                                                                   # an abort stays an abort
    _step11_env(monkeypatch)
    monkeypatch.setattr(daily_stock_job, "check_publishing_setup", lambda *a, **k: (_ for _ in ()).throw(daily_stock_job.DailyStop("setup", "this is not the publishing clone")))
    r = mr.step11_commit_and_push(False, *GATES_OK)
    assert r["held"] is True and r["pushed"] is False and "could not publish" in r["reason"]
    _step11_env(monkeypatch)
    monkeypatch.setattr(mr, "stray_changes_outside_generated_list", lambda: (_ for _ in ()).throw(_subprocess.CalledProcessError(128, ["git", "status"], stderr="not a git repository")))
    assert mr.step11_commit_and_push(False, *GATES_OK)["held"] is True
    _step11_env(monkeypatch)
    monkeypatch.setattr(mr, "check_tcp_reachable", lambda *a, **k: (_ for _ in ()).throw(OSError("socket error")))
    assert mr.step11_commit_and_push(False, *GATES_OK)["held"] is True


# ---- Prompt 35, Step 1: the PEM107 alert pull is a stage of step 1; its failure is a WARN and a partial run

def test_step_1_has_the_pem107_alert_stage_and_the_offline_dry_run_reports_it():
    tree = _ast.parse(open(mr.__file__, encoding="utf-8").read())
    stages = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name) and node.func.id == "_pull_stage" and len(node.args) >= 2:
            stages.append((_ast.unparse(node.args[1]), _ast.unparse(node)))
    assert any(script == "'cube_ces_pull.py'" and "--pem107-alert" in call for script, call in stages), stages
    result = mr.step1_pull_data(True, True)                                       # the offline pull step of a dry run: no database
    assert result["pem107_alert_pull"]["refreshed"] is False and "offline" in result["pem107_alert_pull"]["not_refreshed_reason"]


def test_a_failed_pem107_pull_is_a_warning_and_the_run_is_partial_with_exit_code_2(monkeypatch, tmp_path):
    out = _unwritten_env(monkeypatch, tmp_path)
    out.write_text("{}")
    _stub_steps(monkeypatch)
    monkeypatch.setattr(mr, "run_script", lambda script, args=None: _Proc(1))             # the pull script exits 1: not a refused login
    monkeypatch.setattr(mr, "step1_pull_data", lambda *a, **k: {"pem107_alert_pull": mr._pull_stage("PEM107 alert pull", "cube_ces_pull.py", str(out), args=["--pem107-alert"]),
                                                              "snapshot_pull_date": "2026-10-02 07:45:57"})
    log = _run(monkeypatch, tmp_path)
    assert log["steps"]["1_pull_data"]["status"] == "ok" and log["partial"] is True and "aborted_at_step" not in log
    assert len(log["warnings"]) == 1 and "PEM107 alert pull" in log["warnings"][0] and log["warnings"][0].startswith("WARN")
    _cli_env(monkeypatch, tmp_path, _date(2026, 12, 7), main_log=log)
    assert mr.cli([]) == 2 and not os.path.exists(mr.MONTHLY_STATE_PATH)                  # exit code 2, not marked done: it runs again on the next weekday


def test_the_pem107_alert_is_a_data_source_judged_by_the_previous_weekday():
    import yaml
    import reader_values as rv
    import build_inventory_page_data as bipd
    cfg = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))
    assert rv.source_class(cfg, bipd.PEM107_ALERT_SOURCE) == "data" and rv.source_class(cfg, bipd.PILOT_SALES_SOURCE) == "model_round"
    assert bipd.freshness_block(cfg)["daily_weekdays_back"] == 1
    assert rv.data_is_stale("2026-10-13", _date(2026, 10, 15), cfg) is True and rv.data_is_stale("2026-10-14", _date(2026, 10, 15), cfg) is False
    page = open(os.path.join(PROJECT_ROOT, "src", "build_inventory_page.py"), encoding="utf-8").read()
    assert "dataStatus(a.data_pulled_at)" in page
