"""The 12:00 retry of the daily stock task (decided by the user 2026-10-06): a run that starts when a successful daily run of today already exists
exits at once, logs that it skipped and makes no database connection; otherwise it runs normally. No tracked file is modified; the logs live in a
temporary folder."""
import json
import logging
import os
import sys

import pytest

from page_helpers import PROJECT_ROOT

import daily_stock_job as djob  # noqa: E402

CONFIG = djob.load_config()
LOG_DIR = CONFIG["daily_stock"]["log_dir"]
TODAY = "2026-10-06"
REAL_SUCCESSFUL_RUN_TODAY = djob.successful_run_today      # kept before any test patches the module


def _log(root, name, status, finished, dry_run=False):
    d = os.path.join(str(root), *LOG_DIR.split("/"))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"daily_stock_{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"run_id": name, "status": status, "dry_run": dry_run, "finished_at": finished}, f)


@pytest.mark.parametrize("status", ["published", "nothing_to_publish"])
def test_a_published_or_unchanged_run_of_today_is_a_success(tmp_path, status):
    _log(tmp_path, "a", status, f"{TODAY}T08:01:00")
    found = djob.successful_run_today(str(tmp_path), CONFIG, today=TODAY)
    assert found and found["run_id"] == "a"


@pytest.mark.parametrize("status,finished,dry", [
    ("failed", f"{TODAY}T08:01:00", False),                          # the 08:00 run that stopped on a modified file
    ("skipped_monthly_runner_running", f"{TODAY}T08:01:00", False),  # held, nothing published
    ("dry_run_passed", f"{TODAY}T08:01:00", True),
    ("published", "2026-10-05T08:01:00", False),                     # yesterday's success does not count
    ("published", f"{TODAY}T08:01:00", True),                        # a dry run never counts, whatever its status
])
def test_anything_else_is_not_a_success_so_the_noon_run_goes_ahead(tmp_path, status, finished, dry):
    _log(tmp_path, "a", status, finished, dry_run=dry)
    assert djob.successful_run_today(str(tmp_path), CONFIG, today=TODAY) is None


def test_no_log_folder_means_no_success(tmp_path):
    assert djob.successful_run_today(str(tmp_path), CONFIG, today=TODAY) is None


def test_a_skip_is_logged_and_never_counts_as_a_success(tmp_path):
    _log(tmp_path, "a", "published", f"{TODAY}T08:01:00")
    existing = djob.successful_run_today(str(tmp_path), CONFIG, today=TODAY)
    path = djob.record_skip(str(tmp_path), CONFIG, existing)
    with open(path, encoding="utf-8") as f:
        log = json.load(f)
    assert log["status"] == CONFIG["daily_stock"]["skip_status"] and "skipped" in log["status"] and "did nothing" in log["note"] and "a" in log["note"]
    assert log["committed"] is False and log["pushed"] is False
    # remove the real success: only the skip log remains, and it is not a success
    os.remove(os.path.join(str(tmp_path), *LOG_DIR.split("/"), "daily_stock_a.json"))
    assert djob.successful_run_today(str(tmp_path), CONFIG, today=TODAY) is None


def _patch_main(monkeypatch, tmp_path, argv=None):
    import db
    import snapshot_daily as sd
    monkeypatch.setattr(sd, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["snapshot_daily.py"] + (argv or []))
    calls = {"session": 0, "load_base": 0}

    def no_session(*a, **k):
        calls["session"] += 1
        raise AssertionError("a database session was opened")

    class Proceeded(Exception):
        pass

    def load_base(*a, **k):
        calls["load_base"] += 1
        raise Proceeded()
    monkeypatch.setattr(db, "session", no_session)
    monkeypatch.setattr(db, "require_reachable", lambda *x, **k: {"reachable": True})      # the preflight is a network call: never in a test
    monkeypatch.setattr(sd, "is_weekday", lambda *x: True)                                  # these tests do not depend on the day they run
    real_load_config = djob.load_config
    monkeypatch.setattr(djob, "load_config", lambda *a, **k: {key: val for key, val in real_load_config(*a, **k).items() if key != "publishing"})      # a temporary folder is not the publishing clone
    monkeypatch.setattr(djob, "load_base", load_base)
    monkeypatch.setattr(djob, "successful_run_today", lambda root, cfg, today=None: REAL_SUCCESSFUL_RUN_TODAY(root, cfg, today=TODAY))
    return sd, calls, Proceeded


def test_the_snapshot_script_exits_before_connecting_when_a_success_exists_today(tmp_path, monkeypatch):
    _log(tmp_path, "a", "published", f"{TODAY}T08:01:00")
    sd, calls, _ = _patch_main(monkeypatch, tmp_path)
    sd.main()                                                # returns without raising and without a session
    assert calls == {"session": 0, "load_base": 0}
    logs = sorted(os.listdir(os.path.join(str(tmp_path), *LOG_DIR.split("/"))))
    assert len(logs) == 2 and any(json.load(open(os.path.join(str(tmp_path), *LOG_DIR.split("/"), n), encoding="utf-8"))["status"]
                                  == CONFIG["daily_stock"]["skip_status"] for n in logs)


def test_the_snapshot_script_runs_normally_when_no_success_exists_today(tmp_path, monkeypatch):
    _log(tmp_path, "a", "failed", f"{TODAY}T08:01:00")
    sd, calls, Proceeded = _patch_main(monkeypatch, tmp_path)
    with pytest.raises(Proceeded):
        sd.main()
    assert calls["load_base"] == 1


def test_force_runs_even_when_a_success_exists_today(tmp_path, monkeypatch):
    _log(tmp_path, "a", "published", f"{TODAY}T08:01:00")
    sd, calls, Proceeded = _patch_main(monkeypatch, tmp_path, argv=["--force"])
    with pytest.raises(Proceeded):
        sd.main()


# ---------------------------------------------------------------------------------------------------------------------------------------------
# The daily job (Prompt 23): Monday to Friday only; a refused login (SQLSTATE 28000) writes the shared lock and ends with exit code 3; the lock blocks every later start before the preflight and
# before any login; an unreachable host makes zero login attempts and does not block the next start. Fake connector and fake network only.
# ---------------------------------------------------------------------------------------------------------------------------------------------
class _DriverError(Exception):
    """A stand-in for pyodbc.Error: args = (sqlstate, message)."""


class _FakeEngine:
    def __init__(self, error=None):
        self.error, self.connects = error, 0

    def connect(self):
        self.connects += 1
        if self.error is not None:
            raise self.error
        raise AssertionError("the success path is not exercised here")

    def dispose(self):
        pass


class _Sock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _daily_env(monkeypatch, tmp_path, reachable, error=None, weekday=True):
    import db
    import snapshot_daily as sd
    db.reset_login_state()
    monkeypatch.setattr(sd, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["snapshot_daily.py"])
    monkeypatch.setattr(sd, "is_weekday", lambda *a: weekday)
    engine = _FakeEngine(error)
    created = []
    monkeypatch.setattr(db, "get_connection", lambda: created.append(1) or engine)
    monkeypatch.setenv("DB_SERVER", "dbhost.invalid\\INSTANCE")
    monkeypatch.setattr(db.socket, "create_connection", (lambda *a, **k: _Sock()) if reachable else (lambda *a, **k: (_ for _ in ()).throw(OSError("timed out"))))
    real_load_config = djob.load_config
    monkeypatch.setattr(djob, "load_config", lambda *a, **k: {key: val for key, val in real_load_config(*a, **k).items() if key != "publishing"})
    monkeypatch.setattr(djob, "load_base", lambda *a, **k: {})
    monkeypatch.setattr(djob, "successful_run_today", lambda root, cfg, today=None: None)
    return sd, engine, created


def _failure_logs(tmp_path):
    d = os.path.join(str(tmp_path), *LOG_DIR.split("/"))
    return [json.load(open(os.path.join(d, n), encoding="utf-8")) for n in sorted(os.listdir(d))] if os.path.isdir(d) else []


def test_monday_to_friday_are_weekdays_and_the_weekend_is_not():
    import datetime as dt
    import snapshot_daily as sd
    assert [sd.is_weekday(dt.datetime(2026, 12, d)) for d in range(7, 14)] == [True, True, True, True, True, False, False]       # Monday 7 December to Sunday 13 December


def test_the_weekend_start_does_nothing_before_any_lock_check_preflight_or_login(tmp_path, monkeypatch):
    import db
    sd, engine, created = _daily_env(monkeypatch, tmp_path, reachable=True, weekday=False)
    monkeypatch.setattr(db, "check_refused_lock", lambda: (_ for _ in ()).throw(AssertionError("the lock was checked")))
    monkeypatch.setattr(db, "require_reachable", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the preflight ran")))
    monkeypatch.setattr(djob, "check_publishing_setup", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the setup check ran")))
    sd.main()                                                                                # returns (exit code 0), nothing else
    assert engine.connects == 0 and created == [] and _failure_logs(tmp_path) == []


SECRET_PATH = "C:/Users/<user>/OneDrive - Secret Company"


def test_the_env_line_says_only_set_or_not_set_and_never_the_value(monkeypatch):
    monkeypatch.setenv("OneDriveCommercial", SECRET_PATH)
    line = djob.env_line()
    assert line == "env OneDriveCommercial: SET" and "<user>" not in line and "Secret" not in line and "OneDrive -" not in line
    monkeypatch.setenv("OneDriveCommercial", "")
    assert djob.env_line() == "env OneDriveCommercial: NOT SET"                              # an empty value is not set
    monkeypatch.delenv("OneDriveCommercial")
    assert djob.env_line() == "env OneDriveCommercial: NOT SET"


@pytest.mark.parametrize("value,expected", [(SECRET_PATH, "env OneDriveCommercial: SET"), (None, "env OneDriveCommercial: NOT SET")])
def test_the_line_is_logged_first_on_a_weekend_start_before_the_lock_check_and_changes_nothing_else(tmp_path, monkeypatch, caplog, value, expected):
    import db
    if value is None:
        monkeypatch.delenv("OneDriveCommercial", raising=False)
    else:
        monkeypatch.setenv("OneDriveCommercial", value)
    sd, engine, created = _daily_env(monkeypatch, tmp_path, reachable=True, weekday=False)
    monkeypatch.setattr(db, "check_refused_lock", lambda: (_ for _ in ()).throw(AssertionError("the lock was checked")))
    with caplog.at_level(logging.INFO, logger="snapshot_daily"):
        sd.main()
    messages = [r.getMessage() for r in caplog.records if r.name == "snapshot_daily"]
    assert messages[0] == expected and messages.count(expected) == 1 and "<user>" not in caplog.text and "Secret" not in caplog.text
    assert engine.connects == 0 and created == [] and _failure_logs(tmp_path) == []             # still no log file, no connection: the weekend exit is unchanged


def test_the_line_is_logged_before_a_blocked_start_and_the_exit_code_stays_3(tmp_path, monkeypatch, caplog):
    import db
    monkeypatch.setenv("OneDriveCommercial", SECRET_PATH)
    sd, engine, created = _daily_env(monkeypatch, tmp_path, reachable=True)
    monkeypatch.setattr(db, "check_refused_lock", lambda: (_ for _ in ()).throw(db.LoginRefused("locked")))
    with caplog.at_level(logging.INFO, logger="snapshot_daily"), pytest.raises(SystemExit) as stop:
        sd.main()
    assert stop.value.code == 3 and engine.connects == 0
    assert [r.getMessage() for r in caplog.records if r.name == "snapshot_daily"][0] == "env OneDriveCommercial: SET"


@pytest.mark.parametrize("value,expected", [(SECRET_PATH, "env OneDriveCommercial: SET"), (None, "env OneDriveCommercial: NOT SET")])
def test_every_daily_log_carries_the_line_a_skip_log_and_a_failure_log(tmp_path, monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("OneDriveCommercial", raising=False)
    else:
        monkeypatch.setenv("OneDriveCommercial", value)
    _log(tmp_path, "a", "published", f"{TODAY}T08:01:00")
    existing = djob.successful_run_today(str(tmp_path), CONFIG, today=TODAY)
    skip = json.load(open(djob.record_skip(str(tmp_path), CONFIG, existing), encoding="utf-8"))
    fail = json.load(open(djob.record_failure(str(tmp_path), CONFIG, "step", RuntimeError("x")), encoding="utf-8"))
    assert skip["env_note"] == expected and fail["env_note"] == expected
    assert "<user>" not in json.dumps(skip) and "Secret" not in json.dumps(fail)
    assert skip["status"] == CONFIG["daily_stock"]["skip_status"] and fail["status"] == "failed"      # nothing else in the logs changed


def test_a_refused_login_makes_one_attempt_writes_the_lock_exits_3_and_the_next_start_is_blocked_before_the_preflight(tmp_path, monkeypatch):
    import db
    sd, engine, created = _daily_env(monkeypatch, tmp_path, reachable=True, error=_DriverError("28000", "[28000] [Driver][SQL Server]Login failed for user 'someone'. (18456)"))
    with pytest.raises(SystemExit) as stop:
        sd.main()
    assert stop.value.code == 3 and engine.connects == 1 and db.login_attempts() == 1
    assert os.path.exists(db.REFUSED_LOCK_PATH) and set(json.load(open(db.REFUSED_LOCK_PATH, encoding="utf-8"))) == {"refused_at", "job"}
    logs = _failure_logs(tmp_path)
    assert len(logs) == 1 and logs[0]["status"] == "failed" and logs[0]["error"]["kind"] == "login_refused" and "someone" not in json.dumps(logs[0])
    # the next start (the noon one, or any later day): the lock stops it before the preflight and before any login
    monkeypatch.setattr(db, "require_reachable", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the preflight ran")))
    with pytest.raises(SystemExit) as again:
        sd.main()
    assert again.value.code == 3 and engine.connects == 1 and len(created) == 1 and db.login_attempts() == 1
    assert os.path.exists(db.REFUSED_LOCK_PATH)                                              # the code never deletes it
    db.reset_login_state()


def test_an_unreachable_host_makes_zero_login_attempts_exits_1_and_does_not_block_the_next_start(tmp_path, monkeypatch):
    import db
    sd, engine, created = _daily_env(monkeypatch, tmp_path, reachable=False)
    with pytest.raises(SystemExit) as stop:
        sd.main()
    assert stop.value.code == 1 and engine.connects == 0 and created == [] and db.login_attempts() == 0
    logs = _failure_logs(tmp_path)
    assert len(logs) == 1 and logs[0]["failed_step"] == "database host unreachable" and logs[0]["error"]["kind"] == "unreachable"
    assert "DB host unreachable (off org network?)" in logs[0]["error"]["message"] and "dbhost" not in json.dumps(logs[0])
    assert not os.path.exists(db.REFUSED_LOCK_PATH)                                          # no login was attempted: no lock
    monkeypatch.setattr(db.socket, "create_connection", lambda *a, **k: _Sock())             # back on the network: the next start makes its one attempt
    engine.error = _DriverError("28000", "[28000] Login failed")
    with pytest.raises(SystemExit) as stop2:
        sd.main()
    assert stop2.value.code == 3 and engine.connects == 1
    db.reset_login_state()


def test_the_failure_kind_separates_a_refused_login_from_an_unreachable_host():
    import db
    assert djob.failure_kind(db.DatabaseUnreachableError("x")) == "unreachable"
    assert djob.failure_kind(RuntimeError("('28000', \"Login failed for user 'x'. (18456)\")")) == "login_refused"
    assert djob.failure_kind(db.DatabaseLoginAlreadyFailedError("x")) == "login_refused"
    assert djob.failure_kind(ValueError("a query returned nothing")) == "other"
