"""The 12:00 retry of the daily stock task (decided by the user 2026-10-06): a run that starts when a successful daily run of today already exists
exits at once, logs that it skipped and makes no database connection; otherwise it runs normally. No tracked file is modified; the logs live in a
temporary folder."""
import json
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
# The daily job: one login attempt per run, a reachability preflight before it, and no second login the same day after a refused one (Prompt 20).
# Fake connector and fake network only.
# ---------------------------------------------------------------------------------------------------------------------------------------------
class _FakeEngine:
    def __init__(self, fail):
        self.fail, self.connects = fail, 0

    def connect(self):
        self.connects += 1
        if self.fail:
            raise RuntimeError("('28000', \"[28000] Login failed for user (fake)\")")
        raise AssertionError("the success path is not exercised here")

    def dispose(self):
        pass


def _daily_env(monkeypatch, tmp_path, reachable, fail=True):
    import db
    import snapshot_daily as sd
    db.reset_login_state()
    monkeypatch.setattr(sd, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["snapshot_daily.py"])
    engine = _FakeEngine(fail)
    created = []
    monkeypatch.setattr(db, "get_connection", lambda: created.append(1) or engine)
    monkeypatch.setenv("DB_SERVER", "dbhost.invalid\\INSTANCE")
    monkeypatch.setattr(db.socket, "create_connection", (lambda *a, **k: _Sock()) if reachable else (lambda *a, **k: (_ for _ in ()).throw(OSError("timed out"))))
    real_load_config = djob.load_config
    monkeypatch.setattr(djob, "load_config", lambda *a, **k: {key: val for key, val in real_load_config(*a, **k).items() if key != "publishing"})
    monkeypatch.setattr(djob, "load_base", lambda *a, **k: {})
    monkeypatch.setattr(djob, "successful_run_today", lambda root, cfg, today=None: None)
    return sd, engine, created


class _Sock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _failure_logs(tmp_path):
    d = os.path.join(str(tmp_path), *LOG_DIR.split("/"))
    return [json.load(open(os.path.join(d, n), encoding="utf-8")) for n in sorted(os.listdir(d))] if os.path.isdir(d) else []


def test_a_failed_login_makes_exactly_one_attempt_then_a_non_zero_exit_and_the_second_start_does_not_log_in_again(tmp_path, monkeypatch):
    import db
    sd, engine, created = _daily_env(monkeypatch, tmp_path, reachable=True)
    with pytest.raises(RuntimeError, match="Login failed"):                              # the script ends with an uncaught error: a non-zero exit
        sd.main()
    assert engine.connects == 1 and db.login_attempts() == 1                             # one attempt, nothing after it
    logs = _failure_logs(tmp_path)
    assert len(logs) == 1 and logs[0]["status"] == "failed" and logs[0]["error"]["kind"] == "login_refused"
    import time
    time.sleep(1.1)                                                                      # the log file name is the run time to the second
    # the 12:00 start of the same day: no connection object is even built, and it ends non-zero with its reason in a log
    with pytest.raises(SystemExit) as stop:
        sd.main()
    assert stop.value.code == 1 and engine.connects == 1 and len(created) == 1 and db.login_attempts() == 1
    logs = _failure_logs(tmp_path)
    assert len(logs) == 2 and logs[1]["failed_step"] == "login retry blocked" and "not logging in again" in logs[1]["error"]["message"]
    db.reset_login_state()


def test_an_unreachable_host_makes_zero_login_attempts_and_a_non_zero_exit_and_does_not_block_the_next_start(tmp_path, monkeypatch):
    import db
    sd, engine, created = _daily_env(monkeypatch, tmp_path, reachable=False)
    with pytest.raises(SystemExit) as stop:
        sd.main()
    assert stop.value.code == 1 and engine.connects == 0 and created == [] and db.login_attempts() == 0
    logs = _failure_logs(tmp_path)
    assert len(logs) == 1 and logs[0]["failed_step"] == "database host unreachable" and logs[0]["error"]["kind"] == "unreachable"
    assert "DB host unreachable (off org network?)" in logs[0]["error"]["message"]
    assert djob.login_refused_today(str(tmp_path), CONFIG) is None                         # no login was attempted, so the noon start may try again once the network is back
    # back on the network: the next start gets as far as the (single) login attempt
    monkeypatch.setattr(db.socket, "create_connection", lambda *a, **k: _Sock())
    with pytest.raises(RuntimeError, match="Login failed"):
        sd.main()
    assert engine.connects == 1
    db.reset_login_state()


def test_the_failure_kind_separates_a_refused_login_from_an_unreachable_host():
    import db
    assert djob.failure_kind(db.DatabaseUnreachableError("x")) == "unreachable"
    assert djob.failure_kind(RuntimeError("('28000', \"Login failed for user 'x'. (18456)\")")) == "login_refused"
    assert djob.failure_kind(db.DatabaseLoginAlreadyFailedError("x")) == "login_refused"
    assert djob.failure_kind(ValueError("a query returned nothing")) == "other"
