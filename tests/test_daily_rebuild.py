"""The daily extra pulls and the rebuild stage (Prompt 57, src/daily_rebuild.py). No database, no network: the pull functions, the builders and the gates are replaced by fakes that write files, and git runs in
temporary repositories. The real builders on saved data are exercised by tests/test_operation_plan_page_builder.py, tests/test_material_plan.py and the monthly dry run."""
import contextlib
import json
import os
import subprocess
import sys
from datetime import date

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import daily_rebuild as dr  # noqa: E402
import daily_stock_job as djob  # noqa: E402
import source_guard as sg  # noqa: E402

with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as _f:
    REAL = yaml.safe_load(_f)


@pytest.fixture
def project(tmp_path):
    """A folder holding every file the stage may change, each with its own bytes; returns (root, config)."""
    for rel in dr.backup_paths(REAL):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"old {rel}".encode())
    for rel in REAL["daily_rebuild"]["model_files"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"model {rel}".encode())
    (tmp_path / "output" / "runs" / "daily").mkdir(parents=True, exist_ok=True)
    sg.write_base(str(tmp_path), REAL, {"trend": 100, "pem107": 100, "material_rm_inventory": 100, "material_open_orders": 10}, "fixture")      # the source guard fails closed without a base (Prompt 63)
    return str(tmp_path), REAL


def _hashes(root, rels):
    return {rel: dr._sha(os.path.join(root, *rel.split("/"))) for rel in rels}


def _write(root, rel, text):
    with open(os.path.join(root, *rel.split("/")), "w", encoding="utf-8") as f:
        f.write(text)


# ------------------------------------------------------------------ backup and restore
def test_a_restore_puts_every_file_back_hash_identical_and_removes_a_file_that_did_not_exist(project):
    root, config = project
    rels = dr.backup_paths(config)
    os.remove(os.path.join(root, *rels[0].split("/")))                           # a file that does not exist yet
    before = _hashes(root, rels)
    backup = dr.Backup(root, rels)
    for rel in rels:
        _write(root, rel, "changed " + rel)
    assert len(backup.verify()) == len(rels)
    backup.restore()
    assert backup.verify() == [] and _hashes(root, rels) == before and not os.path.exists(os.path.join(root, *rels[0].split("/")))
    backup.close()
    assert not os.path.exists(backup.dir)


def test_the_backup_covers_every_file_a_pull_or_the_rebuild_writes(project):
    _, config = project
    rels = set(dr.backup_paths(config))
    assert {f for files in dr.source_files(config).values() for f in files} <= rels
    for key in ("output_item_month_file", "output_division_month_file", "output_meta_file", "output_integrity_file"):
        assert config["operation_plan"][key] in rels
    assert {config["material_plan"]["output_material_month_file"], config["material_plan"]["output_material_summary_file"], *config["daily_rebuild"]["allowed_files"]} <= rels


# ------------------------------------------------------------------ the extra pulls
def _fake_pulls(root, config, failing=None, counts=None):
    files, counts = dr.source_files(config), counts or {"trend": {"rows": 100}, "pem107": {"rows": 100}, "material": {"rm_inventory": 100, "open_orders": 10}}

    def make(name):
        def pull(r):
            for rel in files[name]:
                _write(r, rel, "new " + rel)                                      # the pull writes its files ...
            if name == failing:
                raise RuntimeError(f"{name} pull broke")                           # ... and then fails
            return counts[name]
        return pull
    return {name: make(name) for name in files}


@pytest.mark.parametrize("failing", ["trend", "pem107", "material"])
def test_each_extra_pull_failing_alone_keeps_its_old_files_and_the_others_still_run(project, failing):
    root, config = project
    files = dr.source_files(config)
    before = _hashes(root, [f for fs in files.values() for f in fs])
    backup = dr.Backup(root, dr.backup_paths(config))
    results = dr.run_extras(root, config, backup, pulls=_fake_pulls(root, config, failing))
    by = {r["source"]: r for r in results}
    assert by[failing]["status"] == "failed" and "broke" in by[failing]["error"]
    assert {n for n, r in by.items() if r["status"] == "ok"} == set(files) - {failing}
    now = _hashes(root, [f for fs in files.values() for f in fs])
    for name, rels in files.items():
        for rel in rels:
            assert (now[rel] == before[rel]) == (name == failing)               # only the failed source is back to its old bytes; the others hold the new pull


def test_a_pull_whose_row_count_leaves_its_band_is_not_used(project):
    root, config = project
    _write(root, dr.source_files(config)["trend"][2], json.dumps({"n_rows": 1000}))
    sg.write_base(root, config, {"trend": 1000}, "fixture")                          # the stored base agrees with the file on disk, as it does in real runs
    backup = dr.Backup(root, dr.backup_paths(config))
    results = dr.run_extras(root, config, backup, pulls={"trend": _fake_pulls(root, config, counts={"trend": {"rows": 700}})["trend"]})
    assert results[0]["status"] == "failed" and "allowed +/-10" in results[0]["error"]
    assert dr.Backup.verify(backup) == []                                           # its files are as they were
    ok = dr.run_extras(root, config, backup, pulls={"trend": _fake_pulls(root, config, counts={"trend": {"rows": 1050}})["trend"]})
    assert ok[0]["status"] == "ok"


def test_the_noon_retry_pulls_only_what_failed_and_a_partial_day_is_not_a_success(project, tmp_path):
    root, config = project
    log = {"run_id": "r1", "dry_run": False, "status": config["daily_rebuild"]["partial_status"], "finished_at": f"{date.today()}T08:01:00",
           "extras": [{"source": "trend", "status": "ok"}, {"source": "pem107", "status": "failed", "error": "x"}, {"source": "material", "status": "ok"}]}
    log_dir = os.path.join(root, config["daily_stock"]["log_dir"])
    with open(os.path.join(log_dir, "daily_stock_r1.json"), "w", encoding="utf-8") as f:
        json.dump(log, f)
    assert djob.successful_run_today(root, config) is None                           # a partial day does not stop the noon start
    partial = dr.partial_run_today(root, config)
    assert partial["run_id"] == "r1" and dr.done_sources(partial) == {"trend", "material"}
    backup = dr.Backup(root, dr.backup_paths(config))
    results = dr.run_extras(root, config, backup, done=dr.done_sources(partial), pulls=_fake_pulls(root, config))
    assert {r["source"]: r["status"] for r in results} == {"trend": "done_earlier_today", "pem107": "ok", "material": "done_earlier_today"}


# ------------------------------------------------------------------ skip rules
def test_the_extras_and_the_rebuild_are_skipped_while_the_monthly_runner_runs_or_has_started_or_finished_today(project):
    root, config = project
    rd = config["daily_rebuild"]
    assert dr.skip_reason(root, config) is None
    lock = os.path.join(root, config["daily_stock"]["monthly_lock_file"])
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    with open(lock, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid()}, f)                                           # a live process
    assert "monthly runner is running" in dr.skip_reason(root, config)
    with open(lock, "w", encoding="utf-8") as f:
        json.dump({"pid": 2 ** 22 + 7}, f)                                           # a dead one: ignored
    assert dr.skip_reason(root, config) is None
    os.makedirs(os.path.join(root, "output", "state"), exist_ok=True)
    _write(root, rd["monthly_attempt_file"], json.dumps({"date": str(date.today()), "run_id": "m1"}))
    assert "monthly attempt is recorded for today (run m1)" in dr.skip_reason(root, config)
    _write(root, rd["monthly_attempt_file"], json.dumps({"date": "2026-01-01", "run_id": "m0"}))
    assert dr.skip_reason(root, config) is None                                      # an attempt of another day does not matter
    _write(root, rd["monthly_state_file"], json.dumps({"last_success_month": "2026-10", "recorded_at": f"{date.today()}T07:30:00"}))
    assert "monthly success is recorded for today" in dr.skip_reason(root, config)


def test_a_skipped_rebuild_touches_nothing_and_says_why(project):
    root, config = project
    os.makedirs(os.path.join(root, "output", "state"), exist_ok=True)
    _write(root, config["daily_rebuild"]["monthly_attempt_file"], json.dumps({"date": str(date.today()), "run_id": "m1"}))
    before = _hashes(root, dr.backup_paths(config))
    backup = dr.Backup(root, dr.backup_paths(config))
    result = dr.run_rebuild(root, config, backup, git=False, steps=[("boom", lambda r: (_ for _ in ()).throw(AssertionError("must not run")))], gates=lambda *a: [])
    assert result["status"] == "skipped" and "monthly attempt" in result["reason"] and _hashes(root, dr.backup_paths(config)) == before


# ------------------------------------------------------------------ the rebuild
def _steps(root, fail_at=None):
    pages = REAL["daily_rebuild"]["allowed_files"] + dr.backup_paths(REAL)[:6]

    def make(name):
        def step(r):
            for rel in pages:
                _write(r, rel, f"{name} {rel}")
            if name == fail_at:
                raise RuntimeError(f"{name} broke")
        return step
    return [(n, make(n)) for n in ("trend", "minmax", "operation plan", "material plan", "executive")]


def _snapshot_free(monkeypatch):
    monkeypatch.setattr(dr, "snapshot", lambda root, config: {})
    monkeypatch.setattr(dr, "archive_monthly_records", lambda *a, **k: None)


def test_a_failed_step_puts_every_file_back_hash_identical_and_the_result_says_which_step(project, monkeypatch):
    root, config = project
    _snapshot_free(monkeypatch)
    rels = dr.backup_paths(config)
    before = _hashes(root, rels)
    backup = dr.Backup(root, rels)
    result = dr.run_rebuild(root, config, backup, git=False, steps=_steps(root, fail_at="material plan"), gates=lambda *a: [])
    assert result["status"] == "failed" and result["failed_step"] == "material plan" and "broke" in result["error"] and result["restored"] is True
    assert _hashes(root, rels) == before


def test_a_failed_gate_puts_every_file_back_too(project, monkeypatch):
    root, config = project
    _snapshot_free(monkeypatch)
    rels = dr.backup_paths(config)
    before = _hashes(root, rels)
    backup = dr.Backup(root, rels)

    def gates(r, c, snap, git):
        raise dr.RebuildFailure("pair check: built at different times", step="pair check")
    result = dr.run_rebuild(root, config, backup, git=False, steps=_steps(root), gates=gates)
    assert result["status"] == "failed" and result["failed_step"] == "pair check" and result["restored"] is True and _hashes(root, rels) == before


def test_a_rebuild_that_passes_keeps_the_new_files_and_reports_steps_and_gates(project, monkeypatch):
    root, config = project
    _snapshot_free(monkeypatch)
    backup = dr.Backup(root, dr.backup_paths(config))
    result = dr.run_rebuild(root, config, backup, git=False, steps=_steps(root), gates=lambda *a: ["pair check"])
    assert result["status"] == "ok" and [s["step"] for s in result["steps"]] == ["trend", "minmax", "operation plan", "material plan", "executive"] and result["gates"] == ["pair check"]
    assert open(os.path.join(root, "index.html"), encoding="utf-8").read() == "executive index.html"


def test_the_monthly_runner_starting_before_the_commit_stops_the_rebuild_without_putting_files_over_its_work(project, monkeypatch):
    root, config = project
    _snapshot_free(monkeypatch)
    calls = iter([None, "the monthly runner is running"])
    monkeypatch.setattr(dr, "skip_reason", lambda *a, **k: next(calls))
    monkeypatch.setattr(djob, "monthly_runner_running", lambda *a, **k: True)
    backup = dr.Backup(root, dr.backup_paths(config))
    result = dr.run_rebuild(root, config, backup, git=False, steps=_steps(root), gates=lambda *a: [])
    assert result["status"] == "failed" and result["failed_step"] == "lock before commit" and result["restored"] is False


# ------------------------------------------------------------------ the allowed files, git
def test_the_allowed_files_are_the_monthly_runners_own_generated_paths():
    import monthly_refresh as mr
    allowed = REAL["daily_rebuild"]["allowed_files"]
    assert set(allowed) == {"forecast/operation_plan.html", "forecast/material_plan.html", "forecast/inventory.html", "index.html"} and set(allowed) <= set(mr.GENERATED_PATHS)
    assert set(REAL["daily_stock"]["published_files"]).isdisjoint(allowed)            # the stock publish keeps its own two files


def _g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repos(tmp_path):
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    for k, v in (("user.email", "t@example.org"), ("user.name", "t")):
        _g(work, "config", k, v)
    files = REAL["daily_rebuild"]["allowed_files"] + ["data/stock_daily.json", "src/other.py"]
    for rel in files:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text("v1 " + rel, encoding="utf-8")
    _g(work, "add", "-A")
    _g(work, "commit", "-q", "-m", "start")
    _g(work, "push", "-q", "origin", "HEAD:main")
    return work


def test_only_the_allowed_files_are_committed_and_pushed(repos):
    for rel in REAL["daily_rebuild"]["allowed_files"][:3] + ["src/other.py"]:
        (repos / rel).write_text("v2 " + rel, encoding="utf-8")
    result = dr.commit_and_push(str(repos), REAL, "2026-10-27 08:00:30")
    assert result["committed"] and result["pushed"] and sorted(result["files"]) == sorted(REAL["daily_rebuild"]["allowed_files"][:3])
    assert sorted(_g(repos, "show", "--name-only", "--format=", "HEAD").split()) == sorted(REAL["daily_rebuild"]["allowed_files"][:3])
    assert "src/other.py" in _g(repos, "status", "--porcelain")                       # the stray tracked change is left alone, never staged
    assert _g(repos, "log", "-1", "--format=%s").strip() == "Daily rebuild, stock pulled 2026-10-27 08:00:30"


def test_nothing_changed_means_no_commit(repos):
    assert dr.commit_and_push(str(repos), REAL, "t")["committed"] is False


def test_a_failed_rebuild_with_git_checks_the_tracked_pages_out_again(repos, project, monkeypatch):
    root, config = project
    _snapshot_free(monkeypatch)
    monkeypatch.setattr(djob, "monthly_runner_running", lambda *a, **k: False)
    rels = REAL["daily_rebuild"]["allowed_files"]
    backup = dr.Backup(str(repos), rels)

    def steps_in_repo(name):
        def step(r):
            for rel in rels:
                (repos / rel).write_text("rebuilt " + rel, encoding="utf-8")
            raise RuntimeError("broke")
        return step
    result = dr.run_rebuild(str(repos), REAL, backup, git=True, steps=[("trend", steps_in_repo("trend"))], gates=lambda *a: [])
    assert result["status"] == "failed" and result["restored"] is True
    assert _g(repos, "status", "--porcelain", "--untracked-files=no").strip() == ""    # a clean tree: the next day's run is not stopped by a modified tracked file


# ------------------------------------------------------------------ the day's status and exit code
@pytest.mark.parametrize("stock,extras,rebuild,expected", [
    ("published", [{"status": "ok"}, {"status": "ok"}], {"status": "ok", "committed": True, "pushed": True}, ("published", 0)),
    ("published", [{"status": "ok"}, {"status": "failed"}], {"status": "ok"}, ("published_partial", 2)),
    ("published", [{"status": "ok"}], {"status": "failed"}, ("published_partial", 2)),
    ("published", [{"status": "ok"}], {"status": "ok", "committed": True, "pushed": False}, ("published_partial", 2)),
    ("nothing_to_publish", [{"status": "failed"}], {"status": "skipped"}, ("published_partial", 2)),
    ("published", [], {"status": "skipped", "reason": "the monthly runner is running"}, ("published", 0)),
    ("skipped_monthly_runner_running", [], {"status": "skipped"}, ("skipped_monthly_runner_running", 0)),
])
def test_status_and_exit_code_of_the_day(stock, extras, rebuild, expected):
    assert dr.finalize(stock, extras, rebuild, REAL) == expected


# ------------------------------------------------------------------ the daily job: order, isolation, exit code
def _run_main(monkeypatch, tmp_path, extras, rebuild, stock_status="published", skip=None, order=None, partial=None, pulls=None):
    import db
    import snapshot_daily as sd
    order = order if order is not None else []
    log = {"run_id": "r9", "status": stock_status, "steps": [], "gates": []}
    written = []

    @contextlib.contextmanager
    def fake_session():
        order.append("session open")
        yield
        order.append("session closed")
    monkeypatch.setattr(db, "session", fake_session)
    monkeypatch.setattr(sd, "is_weekday", lambda now=None: True)
    monkeypatch.setattr(db, "check_refused_lock", lambda: None)
    monkeypatch.setattr(db, "require_reachable", lambda *a, **k: None)
    monkeypatch.setattr(djob, "check_publishing_setup", lambda *a, **k: {})
    monkeypatch.setattr(djob, "successful_run_today", lambda *a, **k: None)
    monkeypatch.setattr(djob, "load_base", lambda *a, **k: None)
    monkeypatch.setattr(djob, "_write_log", lambda root, config, lg: written.append(dict(lg)) or "p")
    monkeypatch.setattr(sd, "take_inventory_snapshot", lambda: "snap")
    monkeypatch.setattr(sd, "write_inventory_snapshot", lambda s: None)
    monkeypatch.setattr(djob, "run", lambda *a, **k: order.append("stock publish") or log)
    monkeypatch.setattr(dr, "partial_run_today", lambda *a, **k: partial)
    monkeypatch.setattr(dr, "skip_reason", lambda *a, **k: skip)

    class _Backup:
        def close(self):
            order.append("backup closed")
    monkeypatch.setattr(dr, "begin", lambda *a, **k: _Backup())
    if pulls is None:
        monkeypatch.setattr(dr, "run_extras", lambda *a, **k: order.append("extras") or extras)
    else:                                                  # the real run_extras with fake pulls: which sources the start pulls is the point of the test
        monkeypatch.setattr(dr, "PULLS", pulls)
        monkeypatch.setattr(dr, "previous_counts", lambda *a, **k: {})
        monkeypatch.setattr(sg, "read_base", lambda root, config: {n: {"rows": 1} for n in ("trend", "pem107")})       # the real project's stored base is never read or written by a test
        monkeypatch.setattr(sg, "write_base", lambda *a, **k: None)
        real_extras = dr.run_extras
        monkeypatch.setattr(dr, "run_extras", lambda *a, **k: order.append("extras") or real_extras(*a, **k))

    def fake_rebuild(*a, **k):
        order.append("rebuild")
        if isinstance(rebuild, BaseException):
            raise rebuild
        return rebuild
    monkeypatch.setattr(dr, "run_rebuild", fake_rebuild)
    code = 0
    try:
        sd.main()
    except SystemExit as e:
        code = e.code
    return code, written, order


def test_the_stock_publish_comes_first_the_extras_inside_the_session_and_the_rebuild_after_it(monkeypatch, tmp_path):
    code, written, order = _run_main(monkeypatch, tmp_path, [{"source": "trend", "status": "ok"}], {"status": "ok"})
    assert order == ["session open", "stock publish", "extras", "session closed", "rebuild", "backup closed"] and code == 0
    assert written[-1]["status"] == "published" and written[-1]["extras"][0]["source"] == "trend" and written[-1]["rebuild"]["status"] == "ok"


def test_an_extra_pull_or_rebuild_failure_leaves_the_stock_published_and_ends_with_exit_2(monkeypatch, tmp_path):
    code, written, order = _run_main(monkeypatch, tmp_path, [{"source": "trend", "status": "failed", "error": "x"}], {"status": "failed", "failed_step": "pair check", "restored": True})
    assert code == 2 and written[-1]["status"] == "published_partial" and order.index("stock publish") < order.index("extras")
    code, written, _ = _run_main(monkeypatch, tmp_path, [{"source": "trend", "status": "ok"}], {"status": "failed", "failed_step": "executive", "restored": True})
    assert code == 2 and written[-1]["rebuild"]["restored"] is True


def test_the_monthly_day_skips_the_extras_and_the_rebuild_and_logs_why(monkeypatch, tmp_path):
    code, written, order = _run_main(monkeypatch, tmp_path, [], None, skip="a monthly attempt is recorded for today (run m1)")
    assert code == 0 and "extras" not in order and "rebuild" not in order
    assert written[-1]["status"] == "published" and written[-1]["rebuild"] == {"status": "skipped", "reason": "a monthly attempt is recorded for today (run m1)"}


def test_a_stock_job_that_did_not_publish_starts_no_extra_pull(monkeypatch, tmp_path):
    code, written, order = _run_main(monkeypatch, tmp_path, [], None, stock_status="skipped_monthly_runner_running")
    assert code == 0 and "extras" not in order and written[-1]["rebuild"]["status"] == "skipped"


# ------------------------------------------------------------------ model protection and the sources
def test_the_model_input_files_are_never_a_target_of_a_pull_the_rebuild_or_a_backup(project):
    _, config = project
    model = set(config["daily_rebuild"]["model_files"])
    assert model.isdisjoint(set(dr.backup_paths(config))) and set(dr.PULLS) == {"trend", "pem107", "material"}
    for rel in ("output/data/raw_all_divisions_sales.csv", "output/data/processed_all_divisions_monthly_qty.csv", "output/data/processed_all_divisions_monthly_sale.csv"):
        assert rel in model
    src = open(os.path.join(PROJECT_ROOT, "src", "daily_rebuild.py"), encoding="utf-8").read()
    assert "raw_all_divisions_sales" not in src and "processed_all_divisions" not in src and "forward_test_log" not in src      # only config names them


def test_the_snapshot_notices_a_changed_model_file(project, monkeypatch):
    root, config = project
    monkeypatch.setattr(dr, "_index_parts", lambda text: ("rest", "model"))
    _write(root, "index.html", "x")
    before = dr.snapshot(root, config)["model_hashes"]
    _write(root, config["daily_rebuild"]["model_files"][0], "tampered")
    assert dr.snapshot(root, config)["model_hashes"] != before


def test_the_split_material_pull_asks_for_the_two_statements_only_and_keeps_the_rest_of_the_bundle(tmp_path, monkeypatch):
    import pandas as pd
    import db
    import material_plan as mp
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8").read(), encoding="utf-8")
    out = tmp_path / mp.load_config(str(tmp_path))["operation_plan"]["week3_inputs_file"]
    out.parent.mkdir(parents=True)
    bom = pd.DataFrame({"ItemFG": ["FG1"], "ItemRawmat": ["RM1"], "Quantity": [1.0], "Unit": ["EA"], "Sequenceno": [1], "Type": ["Material"]})
    old = {"bom_tree": bom, "rm_inventory": pd.DataFrame(), "rm_pulled_at_local": "2026-10-20 09:42:00", "open_orders": pd.DataFrame(), "po_lines": pd.DataFrame({"a": [1]}),
           "backlog_ces": pd.DataFrame({"b": [2]}), "backlog_pulled_at_local": "x", "receipts": pd.DataFrame(), "price": pd.DataFrame(), "item_names": pd.DataFrame()}
    pd.to_pickle(old, out)
    sql = []

    def fake_query(statement):
        sql.append(statement)
        if "Cube_Inventory_Exact" in statement:
            return pd.DataFrame({"warehouse": ["W1"], "itemcode": ["RM1"], "stock": [5.0], "unit": ["EA"]})
        return pd.DataFrame({"fulfill_date": ["2026-11-01"], "po_number": ["P1"], "itemcode": ["RM1"], "quantity": [3.0], "unit": ["EA"], "warehouse": ["W1"], "order_date": ["2026-10-01"]})
    monkeypatch.setattr(db, "run_query", fake_query)
    result = mp.pull_rm_stock_and_open_orders(str(tmp_path), in_open_session=True)
    assert len(sql) == 2 and sql[0] == mp.RM_STOCK_SQL.format(codes="RM1") and sql[1] == mp.OPEN_PO_SQL.format(codes="RM1")
    assert mp.RM_STOCK_SQL == "SELECT warehouse, itemcode, stock, unit FROM Cube_Inventory_Exact WHERE itemcode IN ('{codes}')"      # the text of the full pull, unchanged
    assert mp.OPEN_PO_SQL == "SELECT fulfill_date, po_number, itemcode, quantity, unit, warehouse, order_date FROM Cube_tobe_received WHERE itemcode IN ('{codes}')"
    new = pd.read_pickle(out)
    assert result["rows"] == {"rm_inventory": 1, "open_orders": 1} and new["rm_pulled_at_local"] != old["rm_pulled_at_local"] and len(new["rm_inventory"]) == 1 and len(new["open_orders"]) == 1
    for k in ("bom_tree", "po_lines", "backlog_ces", "backlog_pulled_at_local", "receipts", "price", "item_names"):
        assert (new[k].equals(old[k]) if hasattr(old[k], "equals") else new[k] == old[k]), k             # the BOM, purchase orders, receipts, prices and names stay from the last full pull
    monkeypatch.setattr(db, "run_query", lambda statement: (_ for _ in ()).throw(RuntimeError("down")))
    before = out.read_bytes()
    with pytest.raises(RuntimeError):
        mp.pull_rm_stock_and_open_orders(str(tmp_path), in_open_session=True)
    assert out.read_bytes() == before                                                                     # a failed pull leaves the bundle as it was


# ------------------------------------------------------------------ Prompt 58: the noon retry after a failed (and restored) rebuild, and a failure while putting back
def _partial_log(rebuild, extras=("ok", "ok", "ok")):
    return {"run_id": "r1", "status": "published_partial", "extras": [{"source": n, "status": st} for n, st in zip(("trend", "pem107", "material"), extras)], "rebuild": rebuild}


def test_a_failed_and_restored_rebuild_means_the_noon_retry_pulls_every_source_again(project):
    root, config = project
    log = _partial_log({"status": "failed", "failed_step": "pair check", "restored": True})
    assert dr.done_sources(log) == set()                                              # the restore put yesterday's source files back, so no "ok" of the morning counts
    backup = dr.Backup(root, dr.backup_paths(config))
    results = dr.run_extras(root, config, backup, done=dr.done_sources(log), pulls=_fake_pulls(root, config))
    assert {r["source"]: r["status"] for r in results} == {"trend": "ok", "pem107": "ok", "material": "ok"}


def test_a_failed_pull_with_an_ok_rebuild_keeps_the_sources_that_were_ok(project):
    log = _partial_log({"status": "ok"}, extras=("ok", "failed", "ok"))
    assert dr.done_sources(log) == {"trend", "material"}
    assert dr.done_sources(_partial_log({"status": "skipped", "reason": "x"}, extras=("ok", "failed", "ok"))) == {"trend", "material"}
    assert dr.done_sources(None) == set() and dr.done_sources({}) == set()


def test_a_failed_rebuild_that_was_not_restored_also_pulls_every_source_again(project):
    # restored False = the monthly runner was running (nothing put back) or the restore itself failed (files half restored): either way the files on disk are not known to be today's pull.
    assert dr.done_sources(_partial_log({"status": "failed", "restored": False, "note": "the monthly runner is running"})) == set()
    assert dr.done_sources(_partial_log({"status": "failed", "restored": False, "restore_errors": [{"file": "a", "error": "x"}]})) == set()


def test_the_noon_start_after_a_failed_restored_morning_rebuild_pulls_every_source_through_main(monkeypatch, tmp_path):
    pulled = []

    def pull(name):
        return lambda root: pulled.append(name) or {"rows": 1}
    morning = _partial_log({"status": "failed", "failed_step": "executive", "restored": True})
    code, written, order = _run_main(monkeypatch, tmp_path, None, {"status": "ok"}, partial=morning, pulls={n: pull(n) for n in ("trend", "pem107", "material")})
    assert sorted(pulled) == ["material", "pem107", "trend"] and code == 0
    assert [(e["source"], e["status"]) for e in written[-1]["extras"]] == [("trend", "ok"), ("pem107", "ok"), ("material", "ok")]
    pulled.clear()                                                                      # control: a morning whose rebuild was ok and whose pem107 pull failed pulls only that one
    morning = _partial_log({"status": "ok"}, extras=("ok", "failed", "ok"))
    _run_main(monkeypatch, tmp_path, None, {"status": "ok"}, partial=morning, pulls={n: pull(n) for n in ("trend", "pem107", "material")})
    assert pulled == ["pem107"]


def test_an_exception_escaping_run_rebuild_is_logged_as_a_failed_rebuild_and_the_day_ends_partial(monkeypatch, tmp_path):
    code, written, order = _run_main(monkeypatch, tmp_path, [{"source": "trend", "status": "ok"}], FileNotFoundError("backup copy gone"))
    assert code == 2 and written[-1]["status"] == "published_partial"
    rb = written[-1]["rebuild"]
    assert rb["status"] == "failed" and rb["failed_step"] == "rebuild (unexpected)" and "FileNotFoundError" in rb["error"] and rb["restored"] is False
    assert written[-1]["extras"][0]["source"] == "trend" and order[-1] == "backup closed"      # the log has the extras, and the backup folder is always removed


def test_restore_continues_past_a_failing_file_and_names_it(project):
    root, config = project
    rels = dr.backup_paths(config)[:4]
    backup = dr.Backup(root, rels)
    for rel in rels:
        _write(root, rel, "changed " + rel)
    os.remove(os.path.join(backup.dir, *rels[1].split("/")))                            # the saved copy of the second file is gone
    errors = backup.restore()
    assert [e["file"] for e in errors] == [rels[1]] and "FileNotFoundError" in errors[0]["error"]
    assert backup.verify() == [rels[1]]                                                  # the other three were put back
    assert backup.restore([rels[0]]) == []


def test_a_restore_that_fails_during_a_failed_rebuild_is_reported_not_raised(project, monkeypatch):
    root, config = project
    _snapshot_free(monkeypatch)
    rels = dr.backup_paths(config)
    backup = dr.Backup(root, rels)
    os.remove(os.path.join(backup.dir, *rels[2].split("/")))
    result = dr.run_rebuild(root, config, backup, git=False, steps=_steps(root, fail_at="material plan"), gates=lambda *a: [])
    assert result["status"] == "failed" and result["restored"] is False
    assert [e["file"] for e in result["restore_errors"]] == [rels[2]]
    assert dr.finalize("published", [{"source": "trend", "status": "ok"}], result, config) == (config["daily_rebuild"]["partial_status"], 2)


# ------------------------------------------------------------------ Prompt 59: the monthly plan-record archive needs a real, successful monthly run log of the month
def _put(root, rel, text):
    os.makedirs(os.path.dirname(os.path.join(root, *rel.split("/"))), exist_ok=True)
    _write(root, rel, text)


def _monthly_log(root, config, name, month="2026-11", dry=False, sandbox=False, offline=False, step7b="ok", pushed=True, finished=True, other="ok"):
    steps = {"1_pull_data": {"status": other}, "11_commit_and_push": {"status": "ok", "result": {"pushed": pushed}}}
    if step7b is not None:                                      # None: a run without the plan step, like the real monthly run of 2026-10-05, which came before step 7b existed
        steps["7b_operation_plan"] = {"status": step7b}
    log = {"run_id": name, "dry_run": dry, "dry_run_in_temporary_copy": sandbox, "offline": offline, "started_at": f"{month}-05T07:00:00", "steps": steps}
    if finished:
        log["finished_at"] = f"{month}-05T07:40:00"
    _put(root, f"{config['daily_rebuild']['monthly_run_logs_dir']}/monthly_refresh_{name}.json", json.dumps(log))


def _archive_ready(project):
    root, config = project
    rd = config["daily_rebuild"]
    _put(root, rd["monthly_state_file"], json.dumps({"last_success_month": "2026-11", "recorded_at": "2026-11-05T07:40:00"}))
    return root, config, date(2026, 11, 9)


def _archive_dir(root, config):
    return os.path.join(root, *config["daily_rebuild"]["archive_dir"].split("/"), "2026-11")


def test_no_monthly_log_means_no_archive_even_when_the_success_state_says_the_month_is_done(project):
    root, config, today = _archive_ready(project)
    assert dr.archive_monthly_records(root, config, today) is None and not os.path.exists(_archive_dir(root, config))


@pytest.mark.parametrize("kind", ["dry_run", "sandbox_copy", "offline"])
def test_a_dry_run_sandbox_or_offline_log_means_no_archive(project, kind):
    root, config, today = _archive_ready(project)
    _monthly_log(root, config, "d1", dry=kind == "dry_run", sandbox=kind == "sandbox_copy", offline=kind == "offline")
    assert dr.archive_monthly_records(root, config, today) is None and not os.path.exists(_archive_dir(root, config))


@pytest.mark.parametrize("flaw", [{"step7b": "FAILED"}, {"step7b": None}, {"pushed": False}, {"finished": False}, {"other": "FAILED"}, {"month": "2026-10"}])
def test_a_real_log_that_did_not_build_the_plan_or_did_not_end_successfully_or_is_of_another_month_means_no_archive(project, flaw):
    root, config, today = _archive_ready(project)
    _monthly_log(root, config, "r1", **flaw)
    assert dr.archive_monthly_records(root, config, today) is None and not os.path.exists(_archive_dir(root, config))


def test_a_real_successful_log_archives_once_and_a_second_call_the_same_month_changes_nothing(project):
    root, config, today = _archive_ready(project)
    _monthly_log(root, config, "r1")
    dst = dr.archive_monthly_records(root, config, today)
    assert dst == _archive_dir(root, config)
    copied = sorted(os.listdir(dst))
    assert len(copied) == 6 and "operation_plan_v1_meta.json" in copied
    first = {n: dr._sha(os.path.join(dst, n)) for n in copied}
    _put(root, config["operation_plan"]["output_meta_file"], "changed by a later daily rebuild")
    assert dr.archive_monthly_records(root, config, today) is None
    assert sorted(os.listdir(dst)) == copied and {n: dr._sha(os.path.join(dst, n)) for n in copied} == first       # the first copy is untouched


def test_an_existing_archive_folder_is_never_overwritten_even_with_a_good_log(project):
    root, config, today = _archive_ready(project)
    _monthly_log(root, config, "r1")
    os.makedirs(_archive_dir(root, config))
    _put(root, config["daily_rebuild"]["archive_dir"] + "/2026-11/README.md", "a development copy")
    assert dr.archive_monthly_records(root, config, today) is None
    assert os.listdir(_archive_dir(root, config)) == ["README.md"]
