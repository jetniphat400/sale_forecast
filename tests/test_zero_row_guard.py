"""Tests for src/zero_row_guard.py -- both the raising case (zero rows, no opt-out) and the
explicit opt-out case (zero rows, allow_empty=True is a valid answer)."""
import pandas as pd
import pytest

from zero_row_guard import EmptyQueryResultError, guard_nonempty


def test_raises_on_empty_dataframe_by_default():
    empty = pd.DataFrame(columns=["itemcode", "qty"])
    with pytest.raises(EmptyQueryResultError) as exc_info:
        guard_nonempty(empty, table="cube_final", filter_desc="itemcode IN ('A','B')")
    msg = str(exc_info.value)
    assert "cube_final" in msg
    assert "itemcode IN ('A','B')" in msg


def test_does_not_raise_on_nonempty_dataframe():
    df = pd.DataFrame({"itemcode": ["A", "B"], "qty": [1, 2]})
    result = guard_nonempty(df, table="cube_final", filter_desc="itemcode IN ('A','B')")
    assert result is df


def test_allow_empty_true_does_not_raise_on_empty_dataframe():
    empty = pd.DataFrame(columns=["itemcode", "qty"])
    result = guard_nonempty(empty, table="cube_final", filter_desc="itemcode IN ('A','B')", allow_empty=True)
    assert len(result) == 0


def test_error_message_names_table_filter_and_time():
    empty = pd.DataFrame()
    with pytest.raises(EmptyQueryResultError) as exc_info:
        guard_nonempty(empty, table="Cube_CES", filter_desc="ItemCode IN scope, 2026 window")
    msg = str(exc_info.value)
    assert "Cube_CES" in msg
    assert "2026 window" in msg
    # a timestamp in ISO format (YYYY-MM-DD) should be present, naming "the time"
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", msg)


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Prompt 45: the start marker and the bounded retry on child-process creation (WinError 5), both in this module
# ---------------------------------------------------------------------------------------------------------------------------------------------
import os
import re
import subprocess
import sys

import pytest

import zero_row_guard as zg

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
_OK = [sys.executable, "-c", "print('ok')"]


def _denied(winerror=5):
    return PermissionError(13, "Access is denied", None, winerror)


def _fail_creation(monkeypatch, times, winerror=5, exc=None):
    """Makes the first `times` CreateProcess calls of subprocess raise (as the operating system did on 2026-10-15); returns the list of calls."""
    real, calls = subprocess._winapi.CreateProcess, []

    def fake(*a, **k):
        calls.append(1)
        if len(calls) <= times:
            raise (exc or _denied(winerror))
        return real(*a, **k)
    monkeypatch.setattr(subprocess._winapi, "CreateProcess", fake)
    return calls


def test_a_refused_process_creation_is_retried_and_then_succeeds(monkeypatch):
    calls, slept = _fail_creation(monkeypatch, 2), []
    out = zg.run_process(_OK, sleep=slept.append, capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == "ok" and len(calls) == 3 and slept == [15.0, 15.0]


def test_three_refused_creations_give_up_with_the_original_error(monkeypatch):
    calls, slept = _fail_creation(monkeypatch, 99), []
    with pytest.raises(PermissionError) as stop:
        zg.run_process(_OK, sleep=slept.append, capture_output=True, text=True)
    assert stop.value.winerror == 5 and len(calls) == 3 and len(slept) == 2          # three attempts in all, two waits


def test_other_errors_are_never_retried(monkeypatch):
    calls = _fail_creation(monkeypatch, 99, winerror=32)                               # a creation error that is not WinError 5
    with pytest.raises(PermissionError):
        zg.run_process(_OK, sleep=lambda s: pytest.fail("slept"), capture_output=True)
    assert len(calls) == 1
    monkeypatch.undo()
    with pytest.raises(FileNotFoundError):                                             # the program does not exist: raised at creation, not WinError 5
        zg.run_process(["no_such_program_xyz"], sleep=lambda s: pytest.fail("slept"))
    # a PermissionError(5) that does NOT come from CreateProcess (the child may already have run) is not retried either
    seen = []

    def boom(cmd, **kw):
        seen.append(1)
        raise _denied()
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(PermissionError):
        zg.run_process(_OK, sleep=lambda s: pytest.fail("slept"))
    assert seen == [1]


def test_a_non_zero_exit_code_is_returned_or_raised_and_never_retried(monkeypatch):
    calls = []
    real = subprocess._winapi.CreateProcess
    monkeypatch.setattr(subprocess._winapi, "CreateProcess", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    bad = [sys.executable, "-c", "import sys; sys.exit(3)"]
    assert zg.run_process(bad, sleep=lambda s: pytest.fail("slept"), capture_output=True).returncode == 3 and len(calls) == 1
    with pytest.raises(subprocess.CalledProcessError):
        zg.run_process(bad, sleep=lambda s: pytest.fail("slept"), capture_output=True, check=True)
    assert len(calls) == 2


def test_the_start_marker_line_appends_and_never_raises(tmp_path, monkeypatch):
    zg.write_start_marker(str(tmp_path / "runs"), "snapshot_daily.py")
    zg.write_start_marker(str(tmp_path / "runs"), "snapshot_daily.py")
    lines = (tmp_path / "runs" / zg.START_MARKER_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d start pid=\d+ script=snapshot_daily\.py", x) for x in lines)
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    zg.write_start_marker(str(blocker / "sub"), "x.py")                                  # the folder cannot be made: swallowed
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    zg.write_start_marker(str(tmp_path / "runs"), "x.py")                                 # the file cannot be opened: swallowed


def test_both_entries_write_the_marker_before_any_heavy_import_and_only_when_run_as_a_script():
    daily = open(os.path.join(_SRC, "snapshot_daily.py"), encoding="utf-8").read()
    monthly = open(os.path.join(_SRC, "monthly_refresh.py"), encoding="utf-8").read()
    assert 0 < daily.index("write_start_marker(") < daily.index("import pandas as pd") and 0 < monthly.index("write_start_marker(") < monthly.index("import numpy as np")
    assert 'if __name__ == "__main__":' in daily[:daily.index("write_start_marker(")] and 'if __name__ == "__main__"' in monthly[:monthly.index("write_start_marker(")]
    # the folders are the jobs' existing run-log folders
    import yaml
    with open(os.path.join(os.path.dirname(_SRC), "config", "config.yaml"), encoding="utf-8") as f:
        log_dir = yaml.safe_load(f)["daily_stock"]["log_dir"]
    assert re.search(r'"output", "runs", "daily"\), "snapshot_daily.py"', daily) and log_dir == "output/runs/daily"
    assert re.search(r'"output", "runs"\), "monthly_refresh.py"', monthly)
    assert '{"--dry-run", "--offline", "--in-sandbox"} & set(sys.argv)' in monthly[:monthly.index("write_start_marker(")]          # a dry or offline run writes no marker (it changes nothing but its own run log)
    import importlib
    import snapshot_daily
    marker = os.path.join(os.path.dirname(_SRC), "output", "runs", "daily", zg.START_MARKER_FILE)
    before = os.path.getsize(marker) if os.path.exists(marker) else None
    importlib.reload(snapshot_daily)                                                       # imported, not run as a script: no marker
    assert (os.path.getsize(marker) if os.path.exists(marker) else None) == before


def test_every_subprocess_call_of_the_two_jobs_goes_through_the_one_helper():
    for name in ("monthly_refresh.py", "daily_stock_job.py"):
        text = open(os.path.join(_SRC, name), encoding="utf-8").read()
        assert "subprocess.run(" not in text and "subprocess.Popen(" not in text and "run_process(" in text, name


def test_the_retry_log_line_names_the_program_only_never_its_folder(monkeypatch, caplog):
    import logging
    _fail_creation(monkeypatch, 1)
    with caplog.at_level(logging.WARNING, logger="zero_row_guard"):
        zg.run_process(_OK, sleep=lambda s: None, capture_output=True, text=True)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "retrying in 15.0 s" in text and os.path.basename(sys.executable) in text and os.path.dirname(sys.executable) not in text
