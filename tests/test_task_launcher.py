"""The shared task launcher src/task_launcher.py (Prompt 59, Python since Prompt 60b): lock, retry, HEAD check, exit codes. Every test works in a temporary bare origin and clone; no database, no network, no scheduled task.

The race of Prompt 58 (two launches in the same second, both pulls failing 128) is repeated here with 3 pairs; the 25-pair proof is in STATUS.md, "Week 4, prompt 59".
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(PROJECT_ROOT, "src", "task_launcher.py")
GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(not GIT, reason="SKIPPED, not passed: the launcher tests need git on this machine")

PROBE = '''import os
import sys
here = os.path.dirname(os.path.abspath(__file__))
lock = os.path.join(here, "output", "runs", "git_pull.lock")
with open(os.path.join(here, "probe_out.txt"), "a") as f:
    f.write("ran lock_present=%s args=%s\\n" % (os.path.exists(lock), sys.argv[1:]))
sys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
'''


def git(cwd, *args, check=True):
    return subprocess.run([GIT, "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", check=check)


@pytest.fixture
def env(tmp_path):
    """(origin, clone, work): the clone is one commit behind origin; the launcher is copied into the clone's src (untracked)."""
    origin, work, clone = tmp_path / "origin.git", tmp_path / "work", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "t")
    (work / "probe.py").write_text(PROBE, encoding="utf-8")
    (work / "a.txt").write_text("one", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "c1")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    git(clone, "config", "user.email", "t@example.com")
    git(clone, "config", "user.name", "t")
    (work / "a.txt").write_text("two", encoding="utf-8")
    git(work, "commit", "-q", "-am", "c2")
    git(work, "push", "-q", "origin", "HEAD:main")
    (clone / "src").mkdir()
    shutil.copy(LAUNCHER, clone / "src" / "task_launcher.py")
    return origin, clone, work


def run_launcher(clone, *args, task="t1", git_exe=None, timeout=120, extra_env=None, script="probe.py", script_args=()):
    cmd = [sys.executable, str(clone / "src" / "task_launcher.py"), "--task", task, "--script", script,
           "--git", git_exe or GIT, "--python", sys.executable, "--clone-dir", str(clone), "--retry-wait-min-seconds", "0", "--retry-wait-max-seconds", "0", *args, *script_args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(extra_env or {})})


def log(clone):
    p = clone / "output" / "runs" / "task_launcher.log"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def ran(clone):
    p = clone / "probe_out.txt"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def head(clone):
    return git(clone, "rev-parse", "HEAD").stdout.strip()


def write_lock(clone, pid, started_at=None, task="other"):
    p = clone / "output" / "runs" / "git_pull.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": pid, "task": task, "started_at": (started_at or datetime.now()).isoformat()}), encoding="utf-8")
    return p


def test_the_launcher_pulls_checks_head_releases_the_lock_before_python_and_returns_python_exit_code(env):
    origin, clone, _ = env
    before = head(clone)
    r = run_launcher(clone, script_args=["7"])                              # "7" is the probe's argument and its exit code
    assert r.returncode == 7, r.stdout + r.stderr
    assert head(clone) == git(origin, "rev-parse", "main").stdout.strip() != before
    assert ran(clone) == ["ran lock_present=False args=['7']"]                       # the lock was released before Python started, so Python never holds it
    text = log(clone)
    assert "lock_acquired" in text and "git_pull attempt 1/4 exit=0" in text and "python_exit code=7" in text and "lock_released" in text
    assert not (clone / "output" / "runs" / "git_pull.lock").exists()


def test_a_held_lock_is_waited_for_and_the_launcher_gives_up_without_starting_python(env):
    _, clone, _ = env
    lock = write_lock(clone, os.getpid())
    r = run_launcher(clone, "--lock-wait-seconds", "3")
    assert r.returncode == 91 and ran(clone) == []
    text = log(clone)
    assert "lock_wait" in text and "lock_timeout" in text and "git_pull" not in text
    assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()           # the holder's lock is untouched


def test_a_lock_released_while_waiting_is_taken_and_the_run_goes_on(env):
    _, clone, _ = env
    lock = write_lock(clone, os.getpid())
    threading.Timer(4.0, lambda: lock.unlink()).start()
    r = run_launcher(clone, "--lock-wait-seconds", "40")
    assert r.returncode == 0, r.stdout + r.stderr
    text = log(clone)
    assert "lock_wait" in text and "lock_acquired" in text and "lock_takeover" not in text and len(ran(clone)) == 1


def test_a_lock_of_a_dead_process_is_taken_over_and_logged(env):
    _, clone, _ = env
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    write_lock(clone, dead.pid)
    r = run_launcher(clone)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "lock_takeover" in log(clone) and "is not running" in log(clone) and len(ran(clone)) == 1


def test_a_lock_older_than_the_stale_age_is_taken_over_even_when_its_pid_is_alive(env):
    _, clone, _ = env
    write_lock(clone, os.getpid(), started_at=datetime.now() - timedelta(hours=1))
    r = run_launcher(clone, "--lock-stale-seconds", "60")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "lock_takeover" in log(clone) and "over 60 s" in log(clone) and len(ran(clone)) == 1


def _failing_git(tmp_path, fail_first):
    """A git.cmd that records every call in calls.txt; `pull` fails (exit 1) for the first `fail_first` calls (all calls when negative), everything else goes to the real git."""
    stub = tmp_path / "git_stub.cmd"
    calls = tmp_path / "calls.txt"
    stub.write_text(
        "@echo off\r\n"
        "echo %* | findstr /C:\"pull --ff-only\" >nul\r\n"
        "if errorlevel 1 goto real\r\n"
        f"echo pull>>\"{calls}\"\r\n"
        f"for /f %%n in ('%SystemRoot%\\System32\\find.exe /c /v \"\" ^< \"{calls}\"') do set N=%%n\r\n"
        f"if {fail_first} LSS 0 (echo fatal: simulated 1>&2 & exit /b 1)\r\n"
        f"if %N% LEQ {fail_first} (echo fatal: simulated 1>&2 & exit /b 1)\r\n"
        ":real\r\n"
        f"\"{GIT}\" %*\r\n", encoding="utf-8")
    return str(stub), calls


def test_a_failing_pull_is_retried_the_configured_number_of_times_then_python_is_not_started(env, tmp_path):
    _, clone, _ = env
    stub, calls = _failing_git(tmp_path, -1)
    r = run_launcher(clone, "--git-retries", "2", git_exe=stub)
    assert r.returncode == 92 and ran(clone) == []
    assert len(calls.read_text().split()) == 3                                              # the first try and two retries
    text = log(clone)
    assert text.count("git_pull attempt") == 3 and "fatal: simulated" in text and "git pull failed after every retry" in text and "lock_released" in text


def test_a_pull_that_fails_once_and_then_works_starts_python(env, tmp_path):
    origin, clone, _ = env
    stub, calls = _failing_git(tmp_path, 1)
    r = run_launcher(clone, "--git-retries", "3", git_exe=stub)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(calls.read_text().split()) == 2 and len(ran(clone)) == 1
    assert head(clone) == git(origin, "rev-parse", "main").stdout.strip()


def test_an_unreachable_remote_exhausts_the_retries_and_starts_no_python(env, tmp_path):
    _, clone, _ = env
    git(clone, "remote", "set-url", "origin", str(tmp_path / "does_not_exist.git"))
    r = run_launcher(clone, "--git-retries", "1")
    assert r.returncode == 92 and ran(clone) == []
    text = log(clone)
    assert text.count("git_pull attempt") == 2 and "exit=1 " in text and "does not appear to be a git repository" in text and "Python not started" in text


def test_a_head_that_is_not_origin_main_stops_before_python(env):
    _, clone, _ = env
    git(clone, "pull", "-q", "--ff-only", "origin", "main")
    (clone / "a.txt").write_text("local", encoding="utf-8")
    git(clone, "commit", "-q", "-am", "local only")                                        # ahead of origin: the pull says "up to date" but HEAD is not origin/main
    r = run_launcher(clone)
    assert r.returncode == 93 and ran(clone) == []
    assert "is not origin/main" in log(clone) and "Python not started" in log(clone)


def test_a_modified_tracked_file_stops_before_python_with_95_but_an_untracked_file_does_not(env):
    _, clone, _ = env
    (clone / "scratch.txt").write_text("untracked", encoding="utf-8")
    r = run_launcher(clone)
    assert r.returncode == 0 and len(ran(clone)) == 1
    git(clone, "pull", "-q", "--ff-only", "origin", "main")
    (clone / "a.txt").write_text("edited by hand", encoding="utf-8")
    r = run_launcher(clone)
    assert r.returncode == 95 and len(ran(clone)) == 1                                    # since Prompt 60c a modified tracked file is found BEFORE the pull (95), not after it (93)
    assert "tracked files are modified" in log(clone) and "clone_in_use" in log(clone)


def test_a_missing_script_stops_with_94_after_the_pull(env):
    _, clone, _ = env
    r = run_launcher(clone, script="no_such_script.py")
    assert r.returncode == 94 and "script not found" in log(clone)


@pytest.mark.parametrize("trial", range(3))
def test_two_launches_in_the_same_second_both_pull_in_turn_and_both_start_python(env, trial):
    origin, clone, _ = env
    procs = []
    cmd_base = [sys.executable, str(clone / "src" / "task_launcher.py"), "--script", "probe.py", "--git", GIT, "--python", sys.executable,
                "--clone-dir", str(clone), "--retry-wait-min-seconds", "0", "--retry-wait-max-seconds", "0"]
    for name in ("daily", "monthly"):
        procs.append(subprocess.Popen(cmd_base + ["--task", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    codes = [p.wait(timeout=180) for p in procs]
    assert codes == [0, 0], [p.stdout.read() + p.stderr.read() for p in procs]
    assert len(ran(clone)) == 2 and head(clone) == git(origin, "rev-parse", "main").stdout.strip()
    text = log(clone)
    assert text.count("lock_acquired") == 2 and text.count("lock_released") == 2 and "exit=128" not in text
    assert not (clone / "output" / "runs" / "git_pull.lock").exists()


def run_as_scheduled(clone, boot, *script_args):
    """The launcher started as the task action starts it (cmd /c python task_launcher.py ...): no --clone-dir (the launcher finds its clone from its own path), no test-only waits."""
    cmd = ["cmd.exe", "/c", sys.executable, str(clone / "src" / "task_launcher.py"), "--task", "t1", "--script", "probe.py", "--git", GIT, "--python", sys.executable, *script_args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(clone), env={**os.environ, "TASK_LAUNCHER_BOOTSTRAP_LOG": str(boot)})


def test_the_launcher_started_without_clone_dir_finds_its_clone_and_runs(env, tmp_path):
    """Prompt 60b: the PowerShell launcher found its clone with $PSScriptRoot in a param default, which is empty in Windows PowerShell 5.1, so every scheduled start died with exit 1 before any log."""
    _, clone, _ = env
    boot = tmp_path / "boot.log"
    r = run_as_scheduled(clone, boot, "5")
    assert r.returncode == 5, r.stdout + r.stderr
    assert f"clone={clone}" in log(clone) and "python_exit code=5" in log(clone)
    assert ran(clone) == ["ran lock_present=False args=['5']"]


def test_the_bootstrap_log_is_written_first_with_the_environment_and_closed_with_the_exit_code(env, tmp_path):
    _, clone, _ = env
    boot = tmp_path / "boot.log"
    run_as_scheduled(clone, boot, "3")
    lines = boot.read_text(encoding="utf-8").splitlines()
    assert lines[0].split(" ", 2)[2].startswith("boot user=") and "exe=" in lines[0] and "temp=" in lines[0] and "--task t1" in lines[0]
    assert lines[-1].endswith("end exitcode=3"), lines


def test_a_missing_option_is_written_to_the_bootstrap_log_and_exits_94(env, tmp_path):
    _, clone, _ = env
    boot = tmp_path / "boot.log"
    r = subprocess.run([sys.executable, str(clone / "src" / "task_launcher.py"), "--task", "t1"], capture_output=True, text=True, timeout=60, cwd=str(clone),
                       env={**os.environ, "TASK_LAUNCHER_BOOTSTRAP_LOG": str(boot)})
    assert r.returncode == 94
    text = boot.read_text(encoding="utf-8")
    assert "launcher_args_error" in text and text.strip().endswith("end exitcode=94") and ran(clone) == []


def test_an_error_outside_the_run_is_written_to_the_bootstrap_log_with_its_line(env, tmp_path):
    _, clone, _ = env
    boot = tmp_path / "boot.log"
    (clone / "config").mkdir()
    (clone / "config" / "config.yaml").write_text("task_launcher:\n  git_retries: not_a_number\n", encoding="utf-8")       # int("not_a_number") raises in the config reader
    r = run_as_scheduled(clone, boot)
    assert r.returncode == 94
    text = boot.read_text(encoding="utf-8")
    assert "launcher_fatal" in text and "ValueError" in text and "line " in text and ran(clone) == []


# ------------------------------------------------------------------ Prompt 60c: no pull while the clone is in use (exit 95)
def _recording_git(tmp_path):
    """A git.cmd that appends every call's arguments to calls.txt and then runs the real git."""
    stub, calls = tmp_path / "git_rec.cmd", tmp_path / "git_calls.txt"
    stub.write_text("@echo off" + "\r\n" + f"echo %*>>\"{calls}\"" + "\r\n" + f"\"{GIT}\" %*" + "\r\n", encoding="utf-8")
    return str(stub), calls


def _git_calls(calls):
    return calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def write_monthly_lock(clone, pid, started_at=None):
    p = clone / "output" / "runs" / "monthly_refresh.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": pid, "started_at": (started_at or datetime.now()).isoformat(timespec="seconds")}), encoding="utf-8")
    return p


@pytest.mark.parametrize("task", ["SaleForecast_PostingDelaySnapshot", "SaleForecastMonthlyRefresh"])
def test_a_live_monthly_runner_lock_gives_95_with_no_pull_no_python_and_the_git_lock_released(env, tmp_path, task):
    _, clone, _ = env
    stub, calls = _recording_git(tmp_path)
    boot = tmp_path / "boot.log"
    before = head(clone)
    write_monthly_lock(clone, os.getpid())                                                # this process is alive
    r = run_launcher(clone, task=task, git_exe=stub, extra_env={"TASK_LAUNCHER_BOOTSTRAP_LOG": str(boot)})
    assert r.returncode == 95 and ran(clone) == [] and head(clone) == before
    assert not any("pull" in c for c in _git_calls(calls)), _git_calls(calls)
    text = log(clone)
    assert "clone_in_use" in text and "the monthly runner is running" in text and "lock_released" in text and "git_pull attempt" not in text
    assert not (clone / "output" / "runs" / "git_pull.lock").exists()
    assert "clone_in_use" in boot.read_text(encoding="utf-8") and "end exitcode=95" in boot.read_text(encoding="utf-8")


def test_a_monthly_lock_of_a_dead_process_does_not_block(env):
    _, clone, _ = env
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    write_monthly_lock(clone, dead.pid)
    r = run_launcher(clone)
    assert r.returncode == 0 and len(ran(clone)) == 1 and "clone_in_use" not in log(clone)


def test_a_live_pid_in_a_monthly_lock_older_than_the_limit_is_a_reused_pid_and_does_not_block(env):
    _, clone, _ = env
    lock = write_monthly_lock(clone, os.getpid())
    old = time.time() - 100000
    os.utime(lock, (old, old))
    r = run_launcher(clone)
    assert r.returncode == 0 and len(ran(clone)) == 1 and "monthly_lock_ignored" in log(clone)


def test_an_unreadable_monthly_lock_does_not_block(env):
    _, clone, _ = env
    (clone / "output" / "runs").mkdir(parents=True, exist_ok=True)
    (clone / "output" / "runs" / "monthly_refresh.lock").write_text("not json", encoding="utf-8")
    r = run_launcher(clone)
    assert r.returncode == 0 and "monthly_lock_unreadable" in log(clone)


def test_a_dirty_tracked_tree_gives_95_before_any_pull_and_a_staged_change_counts_too(env, tmp_path):
    _, clone, _ = env
    stub, calls = _recording_git(tmp_path)
    before = head(clone)
    (clone / "a.txt").write_text("edited by hand", encoding="utf-8")
    r = run_launcher(clone, git_exe=stub)
    assert r.returncode == 95 and ran(clone) == [] and head(clone) == before
    seen = _git_calls(calls)
    assert seen and all("status" in c for c in seen) and not any("pull" in c for c in seen), seen         # only the read-only status ran
    assert "tracked files are modified or staged" in log(clone) and "lock_released" in log(clone)
    git(clone, "checkout", "--", "a.txt")
    (clone / "a.txt").write_text("staged", encoding="utf-8")
    git(clone, "add", "a.txt")
    assert run_launcher(clone, git_exe=stub).returncode == 95


def test_an_index_lock_in_the_clone_gives_95_without_any_git_call(env, tmp_path):
    _, clone, _ = env
    stub, calls = _recording_git(tmp_path)
    (clone / ".git" / "index.lock").write_text("", encoding="utf-8")
    r = run_launcher(clone, git_exe=stub)
    assert r.returncode == 95 and _git_calls(calls) == [] and "index.lock" in log(clone)


def test_a_clean_tree_and_no_monthly_lock_pull_and_run_as_before(env, tmp_path):
    origin, clone, _ = env
    stub, calls = _recording_git(tmp_path)
    r = run_launcher(clone, git_exe=stub)
    assert r.returncode == 0 and len(ran(clone)) == 1 and head(clone) == git(origin, "rev-parse", "main").stdout.strip()
    seen = _git_calls(calls)
    assert any("status" in c for c in seen) and any("pull" in c for c in seen) and "clone_in_use" not in log(clone)
