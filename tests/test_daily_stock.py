"""The daily stock job (src/daily_stock_job.py): gates, staging list, stop on a modified tracked file, failure log,
skip while the monthly runner runs, and one JSON format from both the daily and the monthly path.

No database and no browser. Git runs for real, but only inside a temporary repository with its own temporary remote;
nothing here touches the project's repository or any tracked file.
"""
import json
import os
import subprocess
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import daily_stock_job as djob  # noqa: E402
import stock_daily as sd  # noqa: E402

CONFIG_WITH_PUBLISHING = djob.load_config(PROJECT_ROOT)
CONFIG = {k: v for k, v in CONFIG_WITH_PUBLISHING.items() if k != "publishing"}      # a fixture repository is not the publishing clone: the clone check is tested below


# ------------------------------------------------------------------ helpers
def _g(cwd, *args):
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout


def _frames(rows=100, stock=10.0, null_code=False, null_ces=False):
    codes = [f"I{i}" for i in range(rows)]
    if null_code:
        codes[3] = None
    inv = pd.DataFrame({"itemcode": codes, "warehouse": "WH01", "stock": stock, "timestamp": "2026-10-05 01:00:00"})
    ces = pd.DataFrame({"ItemCode": ["I1", None if null_ces else "I2"], "Timestamp": ["2026-10-05 02:00:00"] * 2})
    return inv, ces


def _payload(pull_time, **kw):
    inv, ces = _frames(**{k: v for k, v in kw.items() if k in ("rows", "stock")})
    return sd.build_payload(inv, ces, pull_time)


def _built(tmp_path, pull_time="2026-10-06 08:00:05", **kw):
    inv, ces = _frames(**kw)
    out = tmp_path / f"built_{pull_time[-8:].replace(':', '')}"
    out.mkdir(exist_ok=True)
    payload = sd.build_payload(inv.dropna(subset=["itemcode"]), ces.dropna(subset=["ItemCode"]), pull_time)
    (out / "inventory.json").write_text(json.dumps({"snapshot": {"generated_at": pull_time}, "items": len(inv)}), encoding="utf-8")
    sd.write_payload(payload, str(out / "stock_daily.json"))
    return {"inventory": inv, "backlog_ces": ces, "payload": payload, "inventory_json": str(out / "inventory.json"),
            "stock_json": str(out / "stock_daily.json"), "meta": {}}


@pytest.fixture
def repo(tmp_path):
    """A working repository with a bare remote, one published stock file (pull time 2026-10-05 07:41:40) and a tracked
    file that is not the job's."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    _g(work, "init", "-q", "-b", "main")
    _g(work, "config", "user.name", "test")
    _g(work, "config", "user.email", "test@example.com")
    _g(work, "config", "core.autocrlf", "false")
    _g(work, "remote", "add", "origin", str(remote))
    (work / "config").mkdir()
    (work / "config" / "config.yaml").write_text(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8").read(), encoding="utf-8")
    (work / "data").mkdir()
    (work / "data" / "inventory.json").write_text('{"old": true}\n', encoding="utf-8")
    sd.write_payload(_payload("2026-10-05 07:41:40"), str(work / "data" / "stock_daily.json"))
    (work / "other.txt").write_text("not the job's\n", encoding="utf-8")
    _g(work, "add", "-A")
    _g(work, "commit", "-q", "-m", "start")
    _g(work, "push", "-q", "origin", "main")
    return work


def _stub_build(monkeypatch, tmp_path, **kw):
    monkeypatch.setattr(djob, "build_stage", lambda root, pull_dir, out_dir: _built(tmp_path, **kw))


BASE = {"inventory_rows": 100, "on_hand_total": 1000.0, "source": "test", "pull_time": None}


# ------------------------------------------------------------------ gates
def test_every_gate_passes_on_a_normal_day():
    inv, ces = _frames()
    res = djob.check_gates(_payload("2026-10-06 08:00:05"), inv, ces, BASE, _payload("2026-10-05 07:41:40"), CONFIG)
    assert [r["gate"] for r in res] == ["row_count_band", "on_hand_total_band", "no_null_item_codes", "pull_newer_than_published"]
    assert all(r["passed"] for r in res), res


@pytest.mark.parametrize("rows,passes", [(100, True), (119, True), (81, True), (70, False), (140, False)])
def test_row_count_gate_band(rows, passes):
    inv, ces = _frames(rows=rows, stock=1000.0 / rows)
    res = {r["gate"]: r for r in djob.check_gates(_payload("2026-10-06 08:00:05"), inv, ces, BASE, None, CONFIG)}
    assert res["row_count_band"]["passed"] is passes, res["row_count_band"]


@pytest.mark.parametrize("stock,passes", [(10.0, True), (12.9, True), (7.1, True), (6.0, False), (14.0, False)])
def test_on_hand_total_gate_band(stock, passes):
    inv, ces = _frames(stock=stock)
    res = {r["gate"]: r for r in djob.check_gates(_payload("2026-10-06 08:00:05"), inv, ces, BASE, None, CONFIG)}
    assert res["on_hand_total_band"]["passed"] is passes, res["on_hand_total_band"]


def test_the_bands_come_from_config():
    assert CONFIG["daily_stock"]["row_count_band_pct"] == 20 and CONFIG["daily_stock"]["on_hand_total_band_pct"] == 30
    tight = {"daily_stock": dict(CONFIG["daily_stock"], row_count_band_pct=1)}
    inv, ces = _frames(rows=105, stock=1000.0 / 105)
    res = {r["gate"]: r for r in djob.check_gates(_payload("2026-10-06 08:00:05"), inv, ces, BASE, None, tight)}
    assert not res["row_count_band"]["passed"]


@pytest.mark.parametrize("kw", [{"null_code": True}, {"null_ces": True}])
def test_null_item_code_gate_fails(kw):
    inv, ces = _frames(**kw)
    res = {r["gate"]: r for r in djob.check_gates({"pull_time": "2026-10-06 08:00:05"}, inv, ces, BASE, None, CONFIG)}
    assert not res["no_null_item_codes"]["passed"]


def test_pull_time_gate_needs_a_strictly_newer_pull():
    inv, ces = _frames()
    pub = _payload("2026-10-05 07:41:40")
    for t, ok in (("2026-10-05 07:41:41", True), ("2026-10-05 07:41:40", False), ("2026-10-05 07:00:00", False)):
        res = {r["gate"]: r for r in djob.check_gates({"pull_time": t}, inv, ces, BASE, pub, CONFIG)}
        assert res["pull_newer_than_published"]["passed"] is ok, t
    # a replay of a saved pull is the pull already published: not older is enough
    res = {r["gate"]: r for r in djob.check_gates({"pull_time": "2026-10-05 07:41:40"}, inv, ces, BASE, pub, CONFIG, replay=True)}
    assert res["pull_newer_than_published"]["passed"]


def test_with_nothing_to_compare_the_band_gates_are_skipped_not_failed():
    inv, ces = _frames(rows=5)
    res = {r["gate"]: r for r in djob.check_gates(_payload("2026-10-06 08:00:05"), inv, ces, None, None, CONFIG)}
    assert res["row_count_band"]["passed"] and "skipped" in res["row_count_band"]["detail"]


# ------------------------------------------------------------------ publishing
def test_publish_stages_only_the_two_data_files_and_pushes(repo, tmp_path):
    (repo / "scratch.csv").write_text("untracked output that must never be staged\n", encoding="utf-8")
    result = djob.publish_stage(str(repo), CONFIG, _built(tmp_path))
    assert result["committed"] and result["pushed"]
    changed = _g(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(changed) == ["data/inventory.json", "data/stock_daily.json"]
    assert "scratch.csv" not in _g(repo, "show", "--name-only", "--format=", "HEAD")
    assert _g(repo, "log", "-1", "--format=%s").strip() == "Daily stock refresh, pulled 2026-10-06 08:00:05"
    remote_head = _g(tmp_path / "remote.git", "rev-parse", "main").strip()
    assert remote_head == _g(repo, "rev-parse", "HEAD").strip(), "the commit was not pushed"
    size = result["commit_size"]
    assert set(size["files"]) == {"data/inventory.json", "data/stock_daily.json"} and size["compressed_bytes_estimate"] > 0


def test_a_modified_tracked_file_stops_the_run_before_anything_changes(repo, tmp_path):
    (repo / "other.txt").write_text("edited by a person\n", encoding="utf-8")
    head = _g(repo, "rev-parse", "HEAD").strip()
    before = (repo / "data" / "stock_daily.json").read_text(encoding="utf-8")
    with pytest.raises(djob.DailyStop) as exc:
        djob.publish_stage(str(repo), CONFIG, _built(tmp_path))
    assert "other.txt" in str(exc.value)
    assert _g(repo, "rev-parse", "HEAD").strip() == head
    assert (repo / "data" / "stock_daily.json").read_text(encoding="utf-8") == before, "a data file was overwritten before the stop"
    assert _g(repo, "diff", "--cached", "--name-only").strip() == ""


def test_a_staged_tracked_file_also_stops_the_run(repo, tmp_path):
    (repo / "other.txt").write_text("staged edit\n", encoding="utf-8")
    _g(repo, "add", "other.txt")
    with pytest.raises(djob.DailyStop):
        djob.publish_stage(str(repo), CONFIG, _built(tmp_path))


def test_an_untracked_file_does_not_stop_the_run(repo, tmp_path):
    (repo / "notes.txt").write_text("untracked\n", encoding="utf-8")
    assert djob.publish_stage(str(repo), CONFIG, _built(tmp_path))["pushed"]


# ------------------------------------------------------------------ the whole run: log, skip, failure
def _log_files(repo):
    d = repo / CONFIG["daily_stock"]["log_dir"]
    return sorted(d.glob("daily_stock_*.json")) if d.exists() else []


def test_a_failed_gate_writes_a_log_makes_no_commit_and_raises(repo, tmp_path, monkeypatch):
    _stub_build(monkeypatch, tmp_path, rows=50, stock=20.0)           # half the rows against a base of 100
    head = _g(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(djob.DailyFailure) as exc:
        djob.run(str(repo), pull_dir=str(tmp_path / "pull"), base=BASE, config=CONFIG, run_id="t1")
    assert exc.value.gate == "row_count_band"
    (log_path,) = _log_files(repo)
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert log["status"] == "failed" and log["failed_gate"] == "row_count_band" and log["committed"] is False and log["pushed"] is False
    assert "row_count_band" in log["error"]["message"]
    assert _g(repo, "rev-parse", "HEAD").strip() == head


def test_a_failed_step_writes_a_log_naming_the_step(repo, tmp_path, monkeypatch):
    def boom(root, pull_dir, out_dir):
        raise djob.DailyFailure("build_inventory_dataset.py exited 1", step="build inventory.json")
    monkeypatch.setattr(djob, "build_stage", boom)
    with pytest.raises(djob.DailyFailure):
        djob.run(str(repo), pull_dir=str(tmp_path / "pull"), base=BASE, config=CONFIG, run_id="t2")
    log = json.loads(_log_files(repo)[0].read_text(encoding="utf-8"))
    assert log["failed_step"] == "build inventory.json" and log["status"] == "failed" and not log["committed"]


def test_a_full_run_publishes_and_records_the_base_for_tomorrow(repo, tmp_path, monkeypatch):
    _stub_build(monkeypatch, tmp_path)
    log = djob.run(str(repo), pull_dir=str(tmp_path / "pull"), base=BASE, config=CONFIG, run_id="t3")
    assert log["status"] == "published" and log["pushed"] and all(g["passed"] for g in log["gates"])
    last = json.loads((repo / CONFIG["daily_stock"]["last_success_file"]).read_text(encoding="utf-8"))
    assert last["pull_time"] == "2026-10-06 08:00:05" and last["inventory_rows"] == 100
    # the same pull again is not newer than what is now published
    _stub_build(monkeypatch, tmp_path)
    with pytest.raises(djob.DailyFailure) as exc:
        djob.run(str(repo), pull_dir=str(tmp_path / "pull"), base=None, config=CONFIG, run_id="t4")
    assert exc.value.gate == "pull_newer_than_published"


def test_nothing_is_published_while_the_monthly_runner_runs(repo, tmp_path, monkeypatch):
    _stub_build(monkeypatch, tmp_path)
    lock = repo / CONFIG["daily_stock"]["monthly_lock_file"]
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")          # this process is alive
    head = _g(repo, "rev-parse", "HEAD").strip()
    log = djob.run(str(repo), pull_dir=str(tmp_path / "pull"), base=BASE, config=CONFIG, run_id="t5")
    assert log["status"] == "skipped_monthly_runner_running" and not log["committed"]
    assert _g(repo, "rev-parse", "HEAD").strip() == head
    assert json.loads(_log_files(repo)[0].read_text(encoding="utf-8"))["status"] == "skipped_monthly_runner_running"


def test_a_stale_lock_from_a_dead_process_does_not_block_publishing(repo, tmp_path, monkeypatch):
    _stub_build(monkeypatch, tmp_path)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = repo / CONFIG["daily_stock"]["monthly_lock_file"]
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": dead.pid}), encoding="utf-8")
    assert not djob.monthly_runner_running(str(repo), CONFIG)
    assert djob.run(str(repo), pull_dir=str(tmp_path / "pull"), base=BASE, config=CONFIG, run_id="t6")["status"] == "published"


def test_a_dry_run_writes_only_its_log_and_stages_nothing(repo, tmp_path, monkeypatch):
    _stub_build(monkeypatch, tmp_path, pull_time="2026-10-05 07:41:40")      # the saved pull is the one already published
    head = _g(repo, "rev-parse", "HEAD").strip()
    before = {p: (repo / p).read_bytes() for p in CONFIG["daily_stock"]["published_files"]}
    log = djob.run(str(repo), dry_run=True, pull_dir=str(tmp_path / "pull"), base=BASE, config=CONFIG, run_id="t7")
    assert log["status"] == "dry_run_passed" and all(g["passed"] for g in log["gates"])
    assert {p: (repo / p).read_bytes() for p in before} == before
    assert _g(repo, "rev-parse", "HEAD").strip() == head and _g(repo, "status", "--porcelain", "--untracked-files=no").strip() == ""
    assert [p.name for p in _log_files(repo)] == ["daily_stock_t7.json"]


def test_snapshot_main_keeps_the_measurement_and_exits_non_zero_when_the_job_fails(monkeypatch):
    import contextlib
    import db
    import snapshot_daily as sdy
    calls = []
    monkeypatch.setattr(db, "session", contextlib.nullcontext)
    monkeypatch.setattr(sdy, "take_snapshot", lambda c: {"run_date": "x"})
    monkeypatch.setattr(sdy, "take_inventory_snapshot", lambda: "inv")
    monkeypatch.setattr(sdy, "append_snapshot", lambda s: calls.append("append"))
    monkeypatch.setattr(sdy, "write_inventory_snapshot", lambda i: calls.append("write"))
    monkeypatch.setattr(djob, "load_base", lambda root, cfg: None)
    monkeypatch.setattr(djob, "successful_run_today", lambda root, cfg, today=None: None)          # a real success of today in the shared logs must not skip this run
    monkeypatch.setattr(djob, "check_publishing_setup", lambda root, cfg: {"checked": False})          # this test is about the order of the steps, not the folder

    def fail(*a, **k):
        raise djob.DailyFailure("gate failed", gate="row_count_band")
    monkeypatch.setattr(djob, "run", fail)
    with pytest.raises(SystemExit) as exc:
        sdy.main()
    assert exc.value.code == 1 and calls == ["append", "write"], "the posting-delay snapshot must be written before the job runs"


def test_snapshot_main_from_the_main_working_copy_stops_before_any_database_session(monkeypatch, tmp_path):
    import db
    import snapshot_daily as sdy
    opened = []
    monkeypatch.setattr(db, "session", lambda: opened.append(1))
    monkeypatch.setattr(sys, "argv", ["snapshot_daily.py"])
    monkeypatch.setattr(sdy, "PROJECT_ROOT", str(tmp_path))                              # not the clone named in config
    monkeypatch.setattr(djob, "load_config", lambda *a, **k: CONFIG_WITH_PUBLISHING)
    monkeypatch.setattr(djob, "record_failure", lambda root, cfg, step, exc: opened.append(("logged", step)))
    with pytest.raises(SystemExit) as exc:
        sdy.main()
    assert exc.value.code == 1 and opened == [("logged", "publishing clone")]


def test_the_posting_delay_measurement_is_unchanged():
    """snapshot_daily.take_snapshot, append_snapshot and the snapshot columns are what they were before the daily job."""
    import inspect
    import snapshot_daily as sdy
    src = inspect.getsource(sdy.take_snapshot)
    for needle in ("counts_by_createdate_json", "max_createDate", "cube_final_total_row_count", "LOOKBACK_DAYS"):
        assert needle in src
    assert '["itemcode", "warehouse", "stock", "minimum", "maximum", "reserve_bywa"]' in inspect.getsource(sdy)


# ------------------------------------------------------------------ one format from both paths
def _synthetic_pull(tmp_path):
    d = tmp_path / "pull"
    d.mkdir()
    inv = pd.DataFrame({"company": ["PEM", "CI", "PEM"], "warehouse": ["FG01", "FG01", "WH21"], "itemcode": ["AA-1", "AA-1", "BB-2"],
                        "unit": "pcs", "stock": [10.0, 2.5, 4.0], "reserve_bywa": 0.0,
                        "timestamp": pd.to_datetime(["2026-10-05 21:41:03", "2026-10-05 21:42:10", "2026-10-05 21:41:30"])})
    ces = pd.DataFrame({"ContractID": ["C1"], "ItemCode": ["AA-1"], "CustomerID": ["X"], "ForecastDelDate": pd.to_datetime(["2026-10-01"]),
                        "PlanDelDate": pd.to_datetime(["2026-10-01"]), "ActualQty": [0.0], "BacklogQty": [3.0],
                        "Timestamp": pd.to_datetime(["2026-10-05 07:35:30"])})
    for name, df in (("inventory", inv), ("backlog_ces", ces), ("backlog_cube", pd.DataFrame({"x": []})), ("transfer_pairs", pd.DataFrame({"x": []}))):
        df.to_pickle(d / f"{name}.pkl")
    meta = {"pulled_at_utc": "2026-10-06T01:00:00Z", "pulled_at_local": "2026-10-06 08:00:05"}
    (d / "pull_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return str(d), meta


def test_monthly_and_daily_paths_write_identical_json_from_the_same_pull(tmp_path, monkeypatch):
    import monthly_refresh as mr
    pull_dir, meta = _synthetic_pull(tmp_path)

    class _Done:                                   # the inventory.json build is a separate script; only the stock file is compared
        returncode, stderr = 0, ""
    def fake_run(cmd, **kw):
        out = cmd[cmd.index("--out") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"snapshot": {"generated_at": meta["pulled_at_utc"]}}, f)
        return _Done()
    monkeypatch.setattr(djob.subprocess, "run", fake_run)
    out_dir = tmp_path / "daily_out"
    out_dir.mkdir()
    built = djob.build_stage(PROJECT_ROOT, pull_dir, str(out_dir))
    monthly_path = mr.write_stock_json(pull_dir, meta, str(tmp_path / "monthly_stock.json"))
    daily_bytes = open(built["stock_json"], "rb").read()
    assert open(monthly_path, "rb").read() == daily_bytes, "monthly and daily stock JSON differ for the same pull"
    payload = json.loads(daily_bytes)
    assert payload["format_version"] == 1 and payload["pull_time"] == "2026-10-06 08:00:05"
    assert payload["stock_source_load_time"] == "2026-10-05 21:41:03" and payload["reserved_source_load_time"] == "2026-10-05 07:35:30"
    assert payload["items"] == {"AA-1": [["FG01", 12.5]], "BB-2": [["WH21", 4.0]]}, "warehouse rows are summed over companies"


def test_the_payload_serialisation_is_deterministic():
    inv, ces = _frames()
    a, b = sd.dumps(sd.build_payload(inv, ces, "2026-10-06 08:00:05")), sd.dumps(sd.build_payload(inv.sample(frac=1, random_state=1), ces, "2026-10-06 08:00:05"))
    assert a == b


@pytest.mark.parametrize("bad", [{"format_version": 2}, {"items": []}, {"pull_time": "not a time"}, {"stock_source_load_time": None}])
def test_a_malformed_stock_file_is_refused(bad):
    good = _payload("2026-10-06 08:00:05")
    with pytest.raises(sd.StockPayloadError):
        sd.validate_payload({**good, **bad})


def test_the_monthly_runner_may_stage_the_stock_file_and_writes_a_lock_only_for_a_real_run():
    import monthly_refresh as mr
    assert "data/stock_daily.json" in mr.GENERATED_PATHS
    lock = os.path.join(PROJECT_ROOT, CONFIG["daily_stock"]["monthly_lock_file"])
    with mr._runner_lock(real_run=False):
        assert not os.path.exists(lock)
    assert sorted(CONFIG["daily_stock"]["published_files"]) == ["data/inventory.json", "data/stock_daily.json"]


# ------------------------------------------------------------------ the publishing clone (decision D1, 2026-10-06)
def _junction(link, target):
    if os.name != "nt":
        os.symlink(str(target), str(link), target_is_directory=True)
        return
    p = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.fixture
def clone_setup(repo, tmp_path):
    """The main working copy (`repo`, with a tracked file modified: work in progress), a publishing clone of the same remote whose output/ is a junction to the
    main copy's output/, and a config that names both."""
    shared = repo / "output"
    shared.mkdir(exist_ok=True)
    clone = tmp_path / "publish_clone"
    _g(tmp_path, "clone", "-q", "-c", "core.autocrlf=false", str(tmp_path / "remote.git"), str(clone))
    _g(clone, "config", "user.name", "test")
    _g(clone, "config", "user.email", "test@example.com")
    _g(clone, "config", "core.autocrlf", "false")
    _junction(clone / "output", shared)
    config = dict(CONFIG, publishing={"clone_root": str(clone), "shared_output_root": str(shared)})
    (repo / "other.txt").write_text("work in progress in the main copy\n", encoding="utf-8")
    return repo, clone, shared, config


def test_the_clone_fast_forwards_from_origin_commits_only_the_two_data_files_pushes_and_the_dirty_main_copy_then_pulls_cleanly(clone_setup, tmp_path):
    main, clone, shared, config = clone_setup
    # someone else publishes a data file to origin first: the clone must take it by fast-forward before it commits
    other = tmp_path / "other_clone"
    _g(tmp_path, "clone", "-q", "-c", "core.autocrlf=false", str(tmp_path / "remote.git"), str(other))
    _g(other, "config", "user.name", "x")
    _g(other, "config", "user.email", "x@example.com")
    (other / "newer.txt").write_text("a later commit on origin\n", encoding="utf-8")
    _g(other, "add", "-A")
    _g(other, "commit", "-q", "-m", "later")
    _g(other, "push", "-q", "origin", "main")
    origin_before = _g(clone, "ls-remote", "origin", "refs/heads/main").split()[0]
    result = djob.publish_stage(str(clone), config, _built(tmp_path))
    assert result["committed"] and result["pushed"]
    assert (clone / "newer.txt").exists(), "the clone did not fast-forward from origin first"
    assert sorted(_g(clone, "show", "--name-only", "--format=", "HEAD").split()) == ["data/inventory.json", "data/stock_daily.json"]
    assert _g(clone, "rev-parse", "HEAD~1").strip() == origin_before                     # exactly one new commit on top of origin's
    assert _g(tmp_path / "remote.git", "rev-parse", "main").strip() == _g(clone, "rev-parse", "HEAD").strip()
    assert _g(clone, "status", "--porcelain", "--untracked-files=no").strip() == ""
    # the main copy still holds its work in progress, and a plain pull takes both commits by fast-forward
    assert _g(main, "status", "--porcelain", "--untracked-files=no").strip() == "M other.txt"
    _g(main, "pull", "--ff-only", "origin", "main")
    assert _g(main, "rev-parse", "HEAD").strip() == _g(clone, "rev-parse", "HEAD").strip()
    assert (main / "other.txt").read_text(encoding="utf-8") == "work in progress in the main copy\n"


def test_the_publishing_check_needs_the_clone_and_the_shared_output_folder(clone_setup, tmp_path):
    main, clone, shared, config = clone_setup
    ok = djob.check_publishing_setup(str(clone), config)
    assert ok["checked"] and os.path.realpath(str(clone / "output")) == os.path.realpath(str(shared))
    with pytest.raises(djob.DailyStop, match="only from the publishing clone"):
        djob.check_publishing_setup(str(main), config)                                   # the main working copy never publishes
    with pytest.raises(djob.DailyStop, match="not the shared one"):
        djob.check_publishing_setup(str(clone), dict(config, publishing={"clone_root": str(clone), "shared_output_root": str(tmp_path / "elsewhere")}))
    head = _g(main, "rev-parse", "HEAD").strip()
    with pytest.raises(djob.DailyStop):
        djob.publish_stage(str(main), config, _built(tmp_path))
    assert _g(main, "rev-parse", "HEAD").strip() == head
    assert djob.check_publishing_setup(str(main), CONFIG) == {"checked": False}          # no block: not checked (a fixture)


def test_a_clone_whose_output_is_a_real_folder_does_not_publish(repo, tmp_path):
    clone = tmp_path / "plain_clone"
    _g(tmp_path, "clone", "-q", "-c", "core.autocrlf=false", str(tmp_path / "remote.git"), str(clone))
    (clone / "output").mkdir()
    config = dict(CONFIG, publishing={"clone_root": str(clone), "shared_output_root": str(repo / "output")})
    with pytest.raises(djob.DailyStop, match="not the shared one"):
        djob.publish_stage(str(clone), config, _built(tmp_path))


def test_the_clone_writes_its_logs_and_reads_the_lock_in_the_shared_folder(clone_setup, tmp_path, monkeypatch):
    main, clone, shared, config = clone_setup
    _stub_build(monkeypatch, tmp_path)
    lock = shared / "runs" / "monthly_refresh.lock"                                      # the monthly runner (also run from the clone) writes it here
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    assert djob.monthly_runner_running(str(clone), config)
    log = djob.run(str(clone), pull_dir=str(tmp_path / "pull"), base=BASE, config=config, run_id="c1")
    assert log["status"] == "skipped_monthly_runner_running" and not log["committed"]
    assert (shared / "runs" / "daily" / "daily_stock_c1.json").exists()                    # the log is in the shared folder, seen from the main copy too
    lock.unlink()
    log = djob.run(str(clone), pull_dir=str(tmp_path / "pull"), base=BASE, config=config, run_id="c2")
    assert log["status"] == "published" and (shared / "runs" / "daily" / "last_success.json").exists()


def test_changes_under_the_shared_output_folder_are_left_out_of_the_clean_check_only_when_a_clone_is_configured(repo):
    (repo / "output" / "summary").mkdir(parents=True)
    (repo / "output" / "summary" / "report.md").write_text("tracked report\n", encoding="utf-8")
    _g(repo, "add", "-f", "output/summary/report.md")
    _g(repo, "commit", "-q", "-m", "a tracked report under output/")
    (repo / "output" / "summary" / "report.md").write_text("changed through the junction\n", encoding="utf-8")
    assert djob.shared_output_prefixes(CONFIG) == () and djob.shared_output_prefixes(CONFIG_WITH_PUBLISHING) == ("output/",)
    assert len(djob.tracked_changes(str(repo))) == 1
    assert djob.tracked_changes(str(repo), djob.shared_output_prefixes(CONFIG_WITH_PUBLISHING)) == []
    (repo / "other.txt").write_text("a real change\n", encoding="utf-8")
    assert [l[3:] for l in djob.tracked_changes(str(repo), ("output/",))] == ["other.txt"]
