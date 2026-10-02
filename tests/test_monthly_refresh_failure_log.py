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
from forward_test_common import (ForwardTestConsistencyError, append_vintage_and_hash, compute_row_integrity_hash,
                                 save_metadata)

from test_forward_test_integrity import base_entry, make_rows

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
    return log, meta


def _fake_computed(vintage_id=2):
    return {"vintage_id": vintage_id, "rows_df": make_rows(vintage_id), "metadata_entry": base_entry(vintage_id),
            "n_rows": 9, "six_month_item_forecast_total_by_division": {"PEM101": 1.0}}


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
