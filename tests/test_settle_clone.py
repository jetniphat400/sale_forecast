"""After a held or failed monthly run the publishing clone is left in a state the task launcher accepts (Prompt 65, RC-003). Every test works in a temporary bare origin and clone, with the real launcher.

End states (a real run after step 7): held by step 8, 9 or 10; failed or aborted in steps 7 to 11; staged but not committed; committed but not pushed; a person's change next to the run's;
nothing changed. The launcher exits 95 for a modified or staged tracked file and 93 when HEAD is not origin/main: the tests check both before and after.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monthly_refresh as mr  # noqa: E402

GIT = shutil.which("git")
REAL_STEP11 = mr.step11_commit_and_push
LAUNCHER = os.path.join(PROJECT_ROOT, "src", "task_launcher.py")
pytestmark = [pytest.mark.skipif(not GIT, reason="SKIPPED, not passed: the settle tests need git on this machine"),
              pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1", reason="already running inside a dry-run copy of the project")]


def git(cwd, *args, check=True):
    return subprocess.run([GIT, "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", check=check)


@pytest.fixture
def clone(tmp_path, monkeypatch):
    """A publishing clone at origin/main with every generated file tracked, a person's file (notes.txt) tracked, the launcher beside it (untracked) and the runner pointed at it."""
    origin, work, cl = tmp_path / "origin.git", tmp_path / "work", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    for c in (work,):
        git(c, "config", "user.email", "t@example.com")
        git(c, "config", "user.name", "t")
    for rel in mr.GENERATED_PATHS + ["notes.txt", "probe.py"]:
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("print('probe')\n" if rel == "probe.py" else f"head version of {rel}\n", encoding="utf-8", newline="")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "start")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(tmp_path, "clone", "-q", str(origin), str(cl))
    git(cl, "config", "user.email", "t@example.com")
    git(cl, "config", "user.name", "t")
    (cl / "src").mkdir()
    shutil.copy(LAUNCHER, cl / "src" / "task_launcher.py")
    monkeypatch.setattr(mr, "PROJECT_ROOT", str(cl))
    monkeypatch.setattr(mr, "RUNS_DIR", str(tmp_path / "runs"))
    return cl


def launcher_code(cl):
    cmd = [sys.executable, str(cl / "src" / "task_launcher.py"), "--task", "t1", "--script", "probe.py", "--git", GIT, "--python", sys.executable, "--clone-dir", str(cl),
           "--retry-wait-min-seconds", "0", "--retry-wait-max-seconds", "0"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120).returncode


def stub_steps(monkeypatch):
    """Every step a stand-in (tests/test_monthly_refresh_failure_log.py) plus step 7d, which that helper leaves real and which reads the project's config (here a temporary clone); step 11 is the real one."""
    from test_monthly_refresh_failure_log import _stub_steps
    _stub_steps(monkeypatch)
    monkeypatch.setattr(mr, "step7d_vintage_gate", lambda *a, **k: {"passed": True, "vintage_id": 3, "stages": {}})
    monkeypatch.setattr(mr, "step11_commit_and_push", REAL_STEP11)


def modify(cl, rels, text="the run's new version"):
    for rel in rels:
        (cl / rel).write_text(f"{text} of {rel}\n", encoding="utf-8", newline="")


def held_dir(report):
    return os.path.join(mr.PROJECT_ROOT, *report["held_dir"].split("/"))


def test_a_run_held_by_a_gate_leaves_modified_pages_the_launcher_refuses_and_settling_saves_restores_and_the_launcher_accepts(clone):
    modify(clone, mr.GENERATED_PATHS)
    assert launcher_code(clone) == 95                                                              # before: the launcher stops on a modified tracked file
    r = mr.settle_clone("run1", "held by step 10")
    assert r["clone_clean"] is True and sorted(r["files_saved"]) == sorted(mr.GENERATED_PATHS) and sorted(r["files_restored"]) == sorted(mr.GENERATED_PATHS) and r["errors"] == []
    for rel in mr.GENERATED_PATHS:
        assert (clone / rel).read_text(encoding="utf-8") == f"head version of {rel}\n"                                  # restored to HEAD
        assert open(os.path.join(held_dir(r), *rel.split("/")), encoding="utf-8").read() == f"the run's new version of {rel}\n"      # the held copy has the run's file
    assert git(clone, "status", "--porcelain", "--untracked-files=no").stdout == "" and launcher_code(clone) == 0


def test_a_run_that_failed_part_way_through_step_7_saves_and_restores_only_what_it_had_changed(clone):
    modify(clone, ["forecast/inventory.html", "data/assumptions.json"])
    r = mr.settle_clone("run2", "failed in 7c_material_plan")
    assert sorted(r["files_saved"]) == ["data/assumptions.json", "forecast/inventory.html"] and r["clone_clean"] is True
    assert not os.path.exists(os.path.join(held_dir(r), "index.html")) and launcher_code(clone) == 0


def test_changes_that_are_staged_but_not_committed_are_cleared_too(clone):
    modify(clone, ["index.html", "forecast/sales_report.html"])
    git(clone, "add", "index.html", "forecast/sales_report.html")                                  # step 11 staged them and the commit then failed
    assert launcher_code(clone) == 95
    r = mr.settle_clone("run3", "git commit failed")
    assert r["clone_clean"] is True and git(clone, "diff", "--cached", "--name-only").stdout == "" and launcher_code(clone) == 0
    assert open(os.path.join(held_dir(r), "index.html"), encoding="utf-8").read().startswith("the run's new version")


def test_a_commit_that_was_made_but_not_pushed_is_saved_as_a_bundle_with_its_files_and_the_clone_is_reset_to_origin(clone):
    modify(clone, ["index.html", "data/inventory.json"])
    git(clone, "add", "index.html", "data/inventory.json")                                         # not -A: the launcher beside the clone is untracked and must stay so
    git(clone, "commit", "-q", "-m", mr.MONTHLY_COMMIT_MESSAGE)                                    # the push after it failed
    assert launcher_code(clone) == 93                                                              # before: HEAD is ahead of origin/main
    commit = git(clone, "rev-parse", "HEAD").stdout.strip()
    r = mr.settle_clone("run4", "git push failed")
    u = r["unpushed_commit"]
    assert u["commits_ahead"] == 1 and u["reset_to_origin"] is True and r["clone_clean"] is True and r["head"] == r["origin_main"] and r["errors"] == []
    bundle = os.path.join(mr.PROJECT_ROOT, *u["bundle"].split("/"))
    assert os.path.exists(bundle) and git(clone, "bundle", "verify", bundle, check=False).returncode == 0       # the work is kept, and the bundle is a valid one
    assert git(clone, "bundle", "list-heads", bundle).stdout.split()[0] == commit                                # it holds exactly the unpushed commit
    assert open(os.path.join(held_dir(r), "index.html"), encoding="utf-8").read().startswith("the run's new version")    # the files can be read without git
    assert launcher_code(clone) == 0


def test_a_commit_that_is_not_the_runs_own_is_never_discarded_but_is_saved_and_reported(clone):
    modify(clone, ["notes.txt"])
    git(clone, "commit", "-q", "-am", "a person's own commit")
    modify(clone, ["index.html"])                                                                  # the run's modified page next to it
    r = mr.settle_clone("run5", "held by step 8")
    assert r["unpushed_commit"]["reset_to_origin"] is False and r["unpushed_commit"]["bundle"] and any("not reset" in x for x in r["left_for_a_person"])
    assert git(clone, "log", "-1", "--format=%s").stdout.strip() == "a person's own commit"             # still there
    assert (clone / "index.html").read_text(encoding="utf-8") == "head version of index.html\n"          # the page was still restored
    assert launcher_code(clone) == 93 and r["clone_clean"] is False                                # reported as not clean: a person must decide


def test_a_persons_edit_of_a_file_the_run_does_not_generate_is_never_touched_and_is_reported(clone):
    modify(clone, ["index.html"])
    (clone / "notes.txt").write_text("a person's unsaved edit\n", encoding="utf-8")
    r = mr.settle_clone("run6", "held by step 9")
    assert (clone / "notes.txt").read_text(encoding="utf-8") == "a person's unsaved edit\n" and any("notes.txt" in x for x in r["left_for_a_person"])
    assert (clone / "index.html").read_text(encoding="utf-8") == "head version of index.html\n" and r["clone_clean"] is False and launcher_code(clone) == 95


def test_a_clean_clone_is_left_alone_and_no_held_folder_is_made(clone):
    r = mr.settle_clone("run7", "step 11 did not publish: nothing to commit")
    assert r["clone_clean"] is True and r["held_dir"] is None and r["files_saved"] == [] and not os.path.exists(os.path.join(mr.RUNS_DIR, "held"))
    assert launcher_code(clone) == 0


# ------------------------------------------------------------------ through the runner itself
def _real_run(monkeypatch, tmp_path, clone, modified, step8):
    """main() as a REAL run (not a dry run), every step a stand-in; step 7 modifies the generated files, step 8 is `step8`."""
    stub_steps(monkeypatch)

    def step7(*a, **k):
        modify(clone, modified)
        return {"stub": "7"}
    monkeypatch.setattr(mr, "step7_rebuild_pages", step7)
    monkeypatch.setattr(mr, "step8_run_tests", step8)
    monkeypatch.setattr(mr, "check_stale_backup_folders", lambda *a, **k: {"checked": False})
    monkeypatch.setattr(mr, "run_backup", lambda *a, **k: {"status": "ok"})
    return dict(dry_run=False, run_id="live1", run_log_dir=str(tmp_path / "logs"))


@pytest.mark.parametrize("which", ["step 8 fails", "step 9 fails", "step 10 fails"])
def test_a_real_run_held_by_step_8_9_or_10_settles_the_clone_and_records_it_in_the_run_log(monkeypatch, tmp_path, clone, which):
    ok = {"passed": True, "summary_line": "ok"}
    bad = {"passed": False, "summary_line": "1 failed"}
    kw = _real_run(monkeypatch, tmp_path, clone, ["index.html", "forecast/operation_plan.html"], lambda *a, **k: bad if which == "step 8 fails" else ok)
    monkeypatch.setattr(mr, "step9_scan_sensitive_content", lambda *a, **k: {"passed": which != "step 9 fails", "findings": []})
    monkeypatch.setattr(mr, "step10_change_magnitude", lambda *a, **k: {"passed": which != "step 10 fails", "gates": {}})
    assert launcher_code(clone) == 0                                                                # nothing modified yet
    log = mr.main(**kw)
    s = log["clone_settled"]
    assert log["push_held"]["held"] is True and s["clone_clean"] is True and sorted(s["files_saved"]) == ["forecast/operation_plan.html", "index.html"] and s["files_restored"]
    saved = json.loads(open(tmp_path / "logs" / "monthly_refresh_live1.json", encoding="utf-8").read())["clone_settled"]
    assert saved["held_dir"].endswith("held/live1") and os.path.exists(os.path.join(str(clone), *saved["held_dir"].split("/"), "index.html"))
    assert launcher_code(clone) == 0


def test_a_real_run_that_aborts_after_step_7_settles_the_clone_before_the_error_leaves_the_runner(monkeypatch, tmp_path, clone):
    def boom(*a, **k):
        raise mr.MonthlyRefreshAbort("step 8 timed out")
    kw = _real_run(monkeypatch, tmp_path, clone, ["index.html"], boom)
    with pytest.raises(mr.MonthlyRefreshAbort):
        mr.main(**kw)
    saved = json.loads(open(tmp_path / "logs" / "monthly_refresh_live1.json", encoding="utf-8").read())
    assert saved["aborted_at_step"] == "8_run_tests" and saved["clone_settled"]["clone_clean"] is True and "8_run_tests" in saved["clone_settled"]["reason"]
    assert (clone / "index.html").read_text(encoding="utf-8") == "head version of index.html\n" and launcher_code(clone) == 0


def test_an_abort_before_step_7_has_nothing_to_settle_and_a_dry_run_never_settles(monkeypatch, tmp_path, clone):
    stub_steps(monkeypatch)
    calls = []
    monkeypatch.setattr(mr, "settle_clone", lambda *a, **k: calls.append(a) or {})
    monkeypatch.setattr(mr, "step2_validate", lambda *a, **k: (_ for _ in ()).throw(mr.MonthlyRefreshAbort("bad data")))
    monkeypatch.setattr(mr, "check_stale_backup_folders", lambda *a, **k: {"checked": False})
    with pytest.raises(mr.MonthlyRefreshAbort):
        mr.main(dry_run=False, run_id="live2", run_log_dir=str(tmp_path / "logs"))
    assert calls == []                                                                              # step 2: the tracked pages were not touched yet
    stub_steps(monkeypatch)
    monkeypatch.setattr(mr, "step8_run_tests", lambda *a, **k: {"passed": False, "summary_line": "x"})
    mr.main(dry_run=True, sandbox=True, offline=True, skip_tests=True, run_id="dry1", run_log_dir=str(tmp_path / "logs2"))
    assert calls == []                                                                              # a dry run works in a copy


def test_the_settle_command_does_what_the_run_does_and_refuses_while_the_runner_is_alive(monkeypatch, tmp_path, clone, capsys):
    modify(clone, ["index.html"])
    lock = tmp_path / "monthly_refresh.lock"
    monkeypatch.setattr(mr, "load_config", lambda: {"daily_stock": {"monthly_lock_file": "monthly_refresh.lock"}})
    monkeypatch.setattr(mr, "PROJECT_ROOT", str(tmp_path))
    lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")                              # this process is alive
    assert mr.cli(["--settle-clone"]) == mr.EXIT_ABORTED and (clone / "index.html").read_text(encoding="utf-8").startswith("the run's new version")
    lock.write_text(json.dumps({"pid": 999999}), encoding="utf-8")                                   # a dead process: a stale lock does not block
    monkeypatch.setattr(mr, "PROJECT_ROOT", str(clone))
    monkeypatch.setattr(mr, "load_config", lambda: {"daily_stock": {"monthly_lock_file": "output/runs/none.lock"}, "publishing": {}})
    assert mr.cli(["--settle-clone"]) == mr.EXIT_OK
    assert '"clone_clean": true' in capsys.readouterr().out and (clone / "index.html").read_text(encoding="utf-8") == "head version of index.html\n" and launcher_code(clone) == 0
