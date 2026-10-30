"""The shared source guard (Prompt 63, src/source_guard.py, config `source_guard`): an empty or abnormal source table can never reach a published page or a new vintage.

Fixtures only: no database, no real output file, no tracked file. The stored base of the real project is never read or written (tests/conftest.py points it at a temporary folder).
* every source: zero rows, out of band, no base at all, a null or old load time, null key columns, and a normal pull;
* the daily job: the stock and reserved gates (c791e27, Prompt 60c) behave as before, the extras put their files back, the stored base is kept;
* the monthly step 1: an abnormal pull aborts the run at step 1 (exit 4), puts the stage's files back, runs no later step, writes no success state, and is made up on the next working day.
"""
import contextlib
import json
import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import daily_rebuild as dr  # noqa: E402
import daily_stock_job as djob  # noqa: E402
import monthly_refresh as mr  # noqa: E402
import source_guard as sg  # noqa: E402
import stock_daily as sd  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1", reason="already running inside a dry-run copy of the project")

CONFIG = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))
SOURCES = list(CONFIG["source_guard"]["sources"])
LOAD_TIME_SOURCES = [n for n in SOURCES if sg.settings(CONFIG, n).get("load_time")]


def with_source(name, **changes):
    guard = CONFIG["source_guard"]
    return {**CONFIG, "source_guard": {**guard, "sources": {**guard["sources"], name: {**guard["sources"][name], **changes}}}}


# ------------------------------------------------------------------ the block lists every source the code checks, and only those
def test_every_source_the_code_checks_is_in_the_config_block_and_every_listed_source_is_checked():
    in_code = {"stock", "reserved"} | set(dr.GUARD_SOURCES.values()) | {src[0] for stage in mr._guard_plan().values() for src in stage["sources"]}
    assert in_code == set(SOURCES), (in_code ^ set(SOURCES))
    for name in SOURCES:
        s = sg.settings(CONFIG, name)
        assert s["rows_band_pct"] > 0 and s["zero_allowed"] is False and s["label"]


def test_the_bands_of_the_sources_that_were_already_banded_are_not_weaker_than_before():
    assert CONFIG["source_guard"]["sources"]["stock"]["rows_band_pct"] <= CONFIG["daily_stock"]["row_count_band_pct"]
    for src, key in (("trend", "trend_rows"), ("pem107", "pem107_rows"), ("material_rm_inventory", "material_rm_inventory"), ("material_open_orders", "material_open_orders")):
        assert sg.settings(CONFIG, src)["rows_band_pct"] <= CONFIG["daily_rebuild"]["bands_pct"][key], src
    assert sg.settings(CONFIG, "reserved")["rows_band_pct"] == 30 and sg.settings(CONFIG, "reserved")["zero_allowed"] is False      # as c791e27 set them


# ------------------------------------------------------------------ rows: zero, band, no base
@pytest.mark.parametrize("name", SOURCES)
def test_zero_rows_fail_for_every_source_unless_its_zero_allowed_says_otherwise(name):
    f = sg.check_rows(name, CONFIG, 0, [(1000, "stored")])
    assert not f["passed"] and f["source"] == name and "0 " in f["detail"] and "1,000" in f["detail"]
    assert sg.check_rows(name, with_source(name, zero_allowed=True), 0, [(1000, "stored")])["passed"]
    assert not sg.check_rows(name, CONFIG, 0, [])["passed"]                                         # zero fails with no base too


@pytest.mark.parametrize("name", SOURCES)
def test_a_count_outside_the_band_fails_on_both_sides_and_one_inside_passes(name):
    pct = sg.settings(CONFIG, name)["rows_band_pct"]
    base = 10000
    inside_hi, inside_lo = int(base * (1 + pct / 100.0)) - 1, int(base * (1 - pct / 100.0)) + 1
    outside_hi, outside_lo = int(base * (1 + pct / 100.0)) + 2, int(base * (1 - pct / 100.0)) - 2
    for rows, ok in ((base, True), (inside_hi, True), (inside_lo, True), (outside_hi, False), (outside_lo, False)):
        f = sg.check_rows(name, CONFIG, rows, [(base, "stored")])
        assert f["passed"] is ok, (name, rows, f)
    assert "allowed +/-" in sg.check_rows(name, CONFIG, outside_hi, [(base, "stored")])["detail"]


@pytest.mark.parametrize("name", SOURCES)
def test_with_no_base_at_all_every_source_fails_closed(name):
    for bases in (None, [], [(None, "stored"), (0, "disk")]):
        f = sg.check_rows(name, CONFIG, 500, bases)
        assert not f["passed"] and "nothing to compare with" in f["detail"], f


def test_the_stored_base_comes_first_then_what_is_on_disk():
    assert sg.check_rows("trend", CONFIG, 1000, [(1000, "stored"), (5, "disk")])["passed"]
    assert not sg.check_rows("trend", CONFIG, 5, [(1000, "stored"), (5, "disk")])["passed"]         # the stored base wins, the disk count is not consulted
    f = sg.check_rows("trend", CONFIG, 1000, [(None, "stored"), (1000, "disk")])
    assert f["passed"] and f["base_source"] == "disk"


# ------------------------------------------------------------------ load time
@pytest.mark.parametrize("name", LOAD_TIME_SOURCES)
def test_a_missing_or_old_load_time_fails_and_a_recent_one_passes(name):
    ref = "2026-11-05 07:30:00"
    limit = sg.settings(CONFIG, name)["max_load_age_hours"]
    assert not sg.check_load_time(name, CONFIG, None, ref)["passed"]
    assert not sg.check_load_time(name, CONFIG, "", ref)["passed"]
    assert not sg.check_load_time(name, CONFIG, "not a time", ref)["passed"]
    old = (pd.Timestamp(ref) - timedelta(hours=limit + 1)).isoformat()
    assert not sg.check_load_time(name, CONFIG, old, ref)["passed"] and "stopped loading" in sg.check_load_time(name, CONFIG, old, ref)["detail"]
    for recent in ((pd.Timestamp(ref) - timedelta(hours=limit - 1)).isoformat(), "2026-11-05 06:00:00"):
        assert sg.check_load_time(name, CONFIG, recent, ref)["passed"]


def test_only_the_sources_that_have_a_load_time_column_are_checked_for_one():
    assert set(LOAD_TIME_SOURCES) == {"stock", "reserved"}
    names = {f["check"] for f in sg.evaluate("trend", CONFIG, rows=10, bases=[(10, "x")])}
    assert names == {"rows_band"}


# ------------------------------------------------------------------ key columns
def test_null_or_blank_key_columns_fail_and_clean_ones_pass():
    df = pd.DataFrame({"itemcode": ["A", None, " ", "B"], "n": [1, 2, 3, 4], "ts": ["2026-11-05 01:00", "2026-11-05 02:00", None, "2026-11-04 23:00"]})
    st = sg.frame_stats(df, ("itemcode",), "ts")
    assert st["rows"] == 4 and st["key_nulls"] == {"itemcode": 2} and st["load_time"] == "2026-11-04 23:00:00"
    assert not sg.check_keys("monthly_sales", st["key_nulls"])["passed"] and "itemcode 2" in sg.check_keys("monthly_sales", st["key_nulls"])["detail"]
    clean = sg.frame_stats(pd.DataFrame({"itemcode": ["A", "B"]}), ("itemcode",))
    assert sg.check_keys("monthly_sales", clean["key_nulls"])["passed"] and clean["load_time"] is None
    assert sg.frame_stats(pd.DataFrame({"itemcode": []}), ("itemcode",), "ts")["load_time"] is None


@pytest.mark.parametrize("name", SOURCES)
def test_a_normal_pull_passes_every_check_of_every_source(name):
    kw = {"load_time": "2026-11-05 06:00:00", "reference_time": "2026-11-05 07:30:00"} if name in LOAD_TIME_SOURCES else {}
    findings = sg.evaluate(name, CONFIG, rows=1000, bases=[(1010, "stored base")], key_nulls={"itemcode": 0}, **kw)
    assert sg.failed(findings) == [] and {f["check"] for f in findings} >= {"rows_band", "key_columns"}
    assert all(f["source"] == name for f in findings)


def test_the_failure_text_names_the_source_the_check_and_the_values():
    findings = sg.evaluate("pem107", CONFIG, rows=0, bases=[(12096, "stored base")])
    text = sg.describe(findings)
    assert "pem107" in text and "rows_band" in text and "12,096" in text and "0 PEM107 delivery rows" in text
    assert sg.describe(sg.evaluate("pem107", CONFIG, rows=12100, bases=[(12096, "stored base")])) == ""


# ------------------------------------------------------------------ the stored base
def test_the_stored_base_is_written_atomically_keeps_other_sources_and_an_unreadable_file_reads_as_empty(tmp_path):
    root = str(tmp_path)
    assert sg.read_base(root, CONFIG) == {} and sg.stored_rows({}, "trend") is None
    sg.write_base(root, CONFIG, {"trend": 39000, "pem107": 12000}, "test one")
    sg.write_base(root, CONFIG, {"trend": 39100}, "test two")
    base = sg.read_base(root, CONFIG)
    assert sg.stored_rows(base, "trend") == 39100 and sg.stored_rows(base, "pem107") == 12000 and base["trend"]["by"] == "test two" and base["pem107"]["by"] == "test one"
    assert not [n for n in os.listdir(tmp_path / "output" / "state") if n.endswith(".tmp")]
    (tmp_path / "output" / "state" / "source_guard_base.json").write_text("not json", encoding="utf-8")
    assert sg.read_base(root, CONFIG) == {}


# ------------------------------------------------------------------ the daily job: stock and reserved gates, extras
def _frames(rows=100, stock_ts="2026-10-05 01:00:00", res_rows=2):
    inv = pd.DataFrame({"itemcode": [f"I{i}" for i in range(rows)], "warehouse": "WH01", "stock": 10.0, "timestamp": stock_ts})
    ces = pd.DataFrame({"ItemCode": [f"I{i}" for i in range(res_rows)], "Timestamp": ["2026-10-06 02:00:00"] * res_rows})
    return inv, ces


BASE = {"inventory_rows": 100, "on_hand_total": 1000.0, "backlog_rows": 2, "source": "test", "pull_time": None}


def _gates(stock_ts="2026-10-05 01:00:00", config=CONFIG, **kw):
    inv, ces = _frames(stock_ts=stock_ts, **kw)
    payload = sd.build_payload(inv, ces, "2026-10-06 08:00:05")
    return {r["gate"]: r for r in djob.check_gates(payload, inv, ces, BASE, None, config)}


def test_the_stock_source_load_time_must_exist_and_be_recent():
    assert _gates()["stock_load_time_present"]["passed"]
    assert not _gates(stock_ts="2026-10-02 01:00:00")["stock_load_time_present"]["passed"]           # 79 h before the pull
    inv, ces = _frames()
    assert not djob.check_gates({"pull_time": "2026-10-06 08:00:05", "stock_source_load_time": None}, inv, ces, BASE, None, CONFIG)[4]["passed"]


def test_the_reserved_gates_behave_as_before_the_shared_guard():
    g = _gates(res_rows=0)
    assert not g["reserved_rows_band"]["passed"] and "0 reserved rows" in g["reserved_rows_band"]["detail"]
    assert _gates()["reserved_rows_band"]["passed"] and _gates()["reserved_load_time_present"]["passed"]


@pytest.fixture
def daily_root(tmp_path):
    for rel in dr.backup_paths(CONFIG):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"old {rel}".encode())
    return str(tmp_path)


def _write(root, rel, text):
    with open(os.path.join(root, *rel.split("/")), "w", encoding="utf-8") as f:
        f.write(text)


def _pulls(root, counts):
    files = dr.source_files(CONFIG)

    def make(name):
        def pull(r):
            for rel in files[name]:
                _write(r, rel, "new " + rel)
            return counts[name]
        return pull
    return {name: make(name) for name in files}


GOOD = {"trend": {"rows": 39000}, "pem107": {"rows": 12000}, "material": {"rm_inventory": 18690, "open_orders": 700}}
BASES = {"trend": 39000, "pem107": 12000, "material_rm_inventory": 18690, "material_open_orders": 700}


def _hashes(root, rels):
    return {rel: dr._sha(os.path.join(root, *rel.split("/"))) for rel in rels}


@pytest.mark.parametrize("source,metric", [("trend", "rows"), ("pem107", "rows"), ("material", "rm_inventory"), ("material", "open_orders")])
def test_an_extra_pull_of_zero_rows_is_not_used_its_files_are_put_back_and_the_others_still_run(daily_root, source, metric):
    sg.write_base(daily_root, CONFIG, BASES, "fixture")
    files = dr.source_files(CONFIG)
    before = _hashes(daily_root, [f for fs in files.values() for f in fs])
    counts = {k: dict(v) for k, v in GOOD.items()}
    counts[source][metric] = 0
    backup = dr.Backup(daily_root, dr.backup_paths(CONFIG))
    results = {r["source"]: r for r in dr.run_extras(daily_root, CONFIG, backup, pulls=_pulls(daily_root, counts))}
    assert results[source]["status"] == "failed" and "0 " in results[source]["error"]
    assert all(r["status"] == "ok" for n, r in results.items() if n != source)
    now = _hashes(daily_root, [f for fs in files.values() for f in fs])
    for name, rels in files.items():
        for rel in rels:
            assert (now[rel] == before[rel]) == (name == source), (name, rel)
    stored = sg.read_base(daily_root, CONFIG)
    assert sg.stored_rows(stored, {"rows": source}.get(metric, f"{source}_{metric}")) == BASES[{"rows": source}.get(metric, f"{source}_{metric}")]      # a failed pull leaves the stored base as it was


def test_an_extra_pull_with_no_base_anywhere_fails_closed_and_a_normal_one_passes_and_is_stored(daily_root, monkeypatch):
    monkeypatch.setattr(dr, "previous_counts", lambda *a, **k: {})
    backup = dr.Backup(daily_root, dr.backup_paths(CONFIG))
    results = dr.run_extras(daily_root, CONFIG, backup, pulls=_pulls(daily_root, GOOD))
    assert [r["status"] for r in results] == ["failed", "failed", "failed"] and all("nothing to compare with" in r["error"] for r in results)
    sg.write_base(daily_root, CONFIG, BASES, "fixture")
    results = dr.run_extras(daily_root, CONFIG, backup, pulls=_pulls(daily_root, {**GOOD, "trend": {"rows": 39100}}))
    assert [r["status"] for r in results] == ["ok", "ok", "ok"]
    assert sg.stored_rows(sg.read_base(daily_root, CONFIG), "trend") == 39100                       # the next run compares with this pull


# ------------------------------------------------------------------ the monthly step 1
class _Proc:
    def __init__(self, code=0):
        self.returncode, self.stdout, self.stderr = code, "", ""


@pytest.fixture
def monthly(monkeypatch, tmp_path):
    """A temporary project for step 1: every pull script is replaced by a function that writes the files the real script writes, with the row counts in `counts`."""
    root = tmp_path / "proj"
    data, summary = root / "output" / "data", root / "output" / "summary"
    for d in (data, summary, data / "inventory_pull", root / "output" / "state", root / "output" / "runs"):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mr, "PROJECT_ROOT", str(root))
    monkeypatch.setattr(mr, "DATA_DIR", str(data))
    monkeypatch.setattr(mr, "SUMMARY_DIR", str(summary))
    monkeypatch.setattr(mr, "INVENTORY_PULL_DIR", str(data / "inventory_pull"))
    monkeypatch.setattr(mr, "PILOT_MONTHLY_PATH", str(data / "processed_full_category_sales_monthly_forecastDate.csv"))
    monkeypatch.setattr(mr, "check_tcp_reachable", lambda *a, **k: (True, None))
    monkeypatch.setattr(mr, "_DB_STAGE_FAILURE", None)
    mr._PARTIAL_WARNINGS.clear()
    state = {"counts": {n: 1000 for n in SOURCES}, "ran": [], "load": datetime.now().isoformat(timespec="seconds"), "key_null": False}
    cfg = mr.load_config()
    bundle = root / cfg["operation_plan"]["week3_inputs_file"]
    bundle.parent.mkdir(parents=True, exist_ok=True)
    trend_dir = root / cfg["trend_tab"]["pull_dir"]
    trend_dir.mkdir(parents=True, exist_ok=True)

    def codes(n):
        return [None if (state["key_null"] and i == 0) else f"I{i}" for i in range(n)]

    def write_all(script, args):
        c = state["counts"]
        if script == "load_data_all_divisions.py":
            pd.DataFrame({"itemcode": codes(c["monthly_sales"]), "qty": 1}).to_csv(data / "raw_all_divisions_sales.csv", index=False)
            pd.DataFrame({"snapshot_pull_date": ["2026-11-05 07:00:01"], "itemcode": ["I1"], "division": ["PEM101"], "year_month": ["2026-10"], "qty": [1]}).to_csv(data / "processed_all_divisions_monthly_qty.csv", index=False)
            pd.DataFrame({"x": [1]}).to_csv(data / "processed_all_divisions_monthly_sale.csv", index=False)
        elif script == "load_data_full.py":
            pd.DataFrame({"itemcode": codes(c["pilot_sales"]), "qty": 1}).to_csv(data / "raw_full_category_sales.csv", index=False)
            pd.DataFrame({"x": [c["pilot_sales"]]}).to_csv(data / "processed_full_category_sales_monthly_forecastDate.csv", index=False)
        elif script == "build_inventory_dataset.py":
            d = data / "inventory_pull"
            pd.DataFrame({"itemcode": codes(c["stock"]), "timestamp": state["load"]}).to_pickle(d / "inventory.pkl")
            pd.DataFrame({"ItemCode": codes(c["reserved"]), "Timestamp": state["load"]}).to_pickle(d / "backlog_ces.pkl")
            (d / "pull_meta.json").write_text(json.dumps({"n": c["stock"], "t": state["load"]}), encoding="utf-8")
        elif script == "material_plan.py":
            frames = {k: pd.DataFrame({"x": range(c[f"material_{k}"])}) for k in ("rm_inventory", "open_orders", "bom_tree", "po_lines", "receipts", "price", "item_names")}
            pd.to_pickle(frames, bundle)
        elif script == "build_trend_tab.py":
            (trend_dir / "completeness.json").write_text(json.dumps({"n_rows": c["trend"], "t": state["load"]}), encoding="utf-8")
            (trend_dir / "daily.csv").write_text("a\n1\n", encoding="utf-8")
            (trend_dir / "names.csv").write_text("a\n1\n", encoding="utf-8")
        elif script == "cube_ces_pull.py":
            pd.DataFrame({"ItemCode": codes(c["pem107"]), "Status": "Actual"}).to_csv(summary / "task2b_part4_cube_ces_raw.csv", index=False)
            (summary / "task2b_part4_pem107_alert.json").write_text(json.dumps({"t": state["load"], "n": c["pem107"]}), encoding="utf-8")
            (summary / "task2b_part4_pem107_alert_items.csv").write_text("a\n1\n", encoding="utf-8")

    def run_script(script, args=None):
        state["ran"].append(script)
        write_all(script, args)
        return _Proc(0)
    monkeypatch.setattr(mr, "run_script", run_script)
    write_all("load_data_all_divisions.py", None)                     # the files of the previous pull, with the same counts: the bands compare with these
    for s in ("load_data_full.py", "build_inventory_dataset.py", "material_plan.py", "build_trend_tab.py", "cube_ces_pull.py"):
        write_all(s, None)
    state["root"], state["bundle"] = root, bundle
    return state


def _file_hashes(root):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            if f != "source_guard_base.json":
                p = os.path.join(d, f)
                out[os.path.relpath(p, root)] = dr._sha(p)
    return out


def test_a_normal_step_1_passes_every_guard_and_stores_the_counts_for_the_next_run(monthly):
    out = mr.step1_pull_data(False, offline=False)
    assert out["source_guard"]["sources_checked"] == len(SOURCES) and all(f["passed"] for f in out["source_guard"]["findings"])
    assert monthly["ran"] == ["load_data_all_divisions.py", "load_data_full.py", "build_inventory_dataset.py", "material_plan.py", "build_trend_tab.py", "cube_ces_pull.py"]
    stored = sg.read_base(str(monthly["root"]), mr.load_config())
    assert set(stored) == set(SOURCES) and sg.stored_rows(stored, "trend") == 1000 and not any("_guard_rows" in v for v in out.values() if isinstance(v, dict))


@pytest.mark.parametrize("source,stage_script", [("monthly_sales", "load_data_all_divisions.py"), ("pilot_sales", "load_data_full.py"), ("stock", "build_inventory_dataset.py"),
                                                 ("reserved", "build_inventory_dataset.py"), ("material_rm_inventory", "material_plan.py"),
                                                 ("material_open_orders", "material_plan.py"), ("material_bom_tree", "material_plan.py"), ("material_po_lines", "material_plan.py"),
                                                 ("material_receipts", "material_plan.py"), ("material_price", "material_plan.py"), ("material_item_names", "material_plan.py"),
                                                 ("trend", "build_trend_tab.py"), ("pem107", "cube_ces_pull.py")])
def test_an_empty_source_aborts_step_1_at_its_stage_puts_its_files_back_and_runs_no_later_stage(monthly, source, stage_script):
    before = _file_hashes(monthly["root"])
    monthly["counts"][source] = 0
    with pytest.raises(mr.MonthlyGateFailed) as exc:
        mr.step1_pull_data(False, offline=False)
    text = str(exc.value)
    assert "source guard" in text and source in text and "rows_band" in text and "0 " in text
    stages = ["load_data_all_divisions.py", "load_data_full.py", "build_inventory_dataset.py", "material_plan.py", "build_trend_tab.py", "cube_ces_pull.py"]
    assert monthly["ran"] == stages[:stages.index(stage_script) + 1]                         # nothing after the failed stage was pulled
    assert _file_hashes(monthly["root"]) == before                                           # every file of the stage is as it was before the pull
    assert not os.path.exists(os.path.join(monthly["root"], "output", "state", "source_guard_base.json"))


def test_an_out_of_band_count_a_null_key_and_an_old_load_time_abort_step_1_too(monthly):
    monthly["counts"]["trend"] = 2000                                                        # +100% against the 1,000 on disk (band 10)
    with pytest.raises(mr.MonthlyGateFailed, match="trend rows_band.*allowed \\+/-10"):
        mr.step1_pull_data(False, offline=False)
    monthly["counts"]["trend"] = 1000
    monthly["key_null"] = True
    with pytest.raises(mr.MonthlyGateFailed, match="key_columns.*itemcode"):
        mr.step1_pull_data(False, offline=False)
    monthly["key_null"] = False
    monthly["load"] = (datetime.now() - timedelta(days=5)).isoformat(timespec="seconds")
    with pytest.raises(mr.MonthlyGateFailed, match="stopped loading"):
        mr.step1_pull_data(False, offline=False)


def test_with_no_stored_base_and_no_earlier_file_the_first_monthly_pull_fails_closed(monthly):
    for rel in ("output/data/raw_all_divisions_sales.csv",):
        os.remove(os.path.join(monthly["root"], *rel.split("/")))
    with pytest.raises(mr.MonthlyGateFailed, match="nothing to compare with"):
        mr.step1_pull_data(False, offline=False)


def test_the_stored_base_not_the_file_on_disk_is_what_a_later_pull_is_compared_with(monthly):
    sg.write_base(str(monthly["root"]), mr.load_config(), {"trend": 5000}, "earlier run")
    with pytest.raises(mr.MonthlyGateFailed, match="trend rows_band.*5,000"):
        mr.step1_pull_data(False, offline=False)


# ------------------------------------------------------------------ the run: abort at step 1, nothing else happens, the next working day makes it up
def _run_cli(monkeypatch, tmp_path, monthly, today, steps_called):
    """The real monthly command (real main, real step 1 over the temporary project) with every later step replaced by a stand-in that records that it ran."""
    class _Today(date):
        @classmethod
        def today(cls):
            return today
    monkeypatch.setattr(mr, "date", _Today)
    monkeypatch.setattr(mr, "MONTHLY_STATE_PATH", str(tmp_path / "state" / "monthly_run_state.json"))
    monkeypatch.setattr(mr, "MONTHLY_ATTEMPT_PATH", str(tmp_path / "state" / "monthly_attempt.json"))
    monkeypatch.setattr(mr, "RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(mr, "_runner_lock", lambda real_run: contextlib.nullcontext())
    monkeypatch.setattr(mr, "check_stale_backup_folders", lambda *a, **k: {"checked": False})
    import daily_stock_job
    import db
    monkeypatch.setattr(daily_stock_job, "check_publishing_setup", lambda *a, **k: {})
    monkeypatch.setattr(db, "check_refused_lock", lambda: None)

    def stand_in(name):
        def step(*a, **k):
            steps_called.append(name)
            return {"snapshot_pull_date": "2026-11-05 07:00:01", "passed": True, "per_division_comparison_topdown": [], "skipped": True, "vintage_id": 3, "stages": {}}
        return step
    for fn, name in (("step2_validate", "2"), ("step3_frozen_snapshot", "3"), ("step4_backtest", "4"), ("step5_new_vintage", "5"), ("step6_fill_and_score", "6"), ("step7_rebuild_pages", "7"),
                     ("step7b_operation_plan", "7b"), ("step7c_material_plan", "7c"), ("step7d_vintage_gate", "7d"), ("step7e_trend_tab", "7e"), ("step7f_exec_summary", "7f"),
                     ("step8_run_tests", "8"), ("step9_scan_sensitive_content", "9"), ("step10_change_magnitude", "10"), ("step11_commit_and_push", "11")):
        monkeypatch.setattr(mr, fn, stand_in(name))
    monkeypatch.setattr(mr, "run_backup", lambda *a, **k: steps_called.append("backup") or {"status": "ok"})
    return mr.cli([])


def test_an_empty_source_ends_the_monthly_run_at_step_1_with_exit_4_nothing_after_it_runs_and_the_next_working_day_makes_it_up(monkeypatch, tmp_path, monthly):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "monthly_run_state.json").write_text(json.dumps({"last_success_month": "2026-10"}), encoding="utf-8")        # as seeded on the real machine
    called = []
    monthly["counts"]["pem107"] = 0                                                           # Cube_CES empty, as on 2026-10-29
    assert _run_cli(monkeypatch, tmp_path, monthly, date(2026, 11, 5), called) == mr.EXIT_GATE_HELD == 4
    assert called == []                                                                       # no fit, no vintage, no page, no test run, no push, no backup
    state = json.loads((tmp_path / "state" / "monthly_run_state.json").read_text(encoding="utf-8"))
    assert state["last_success_month"] == "2026-10"                                           # the success state of November is NOT written
    assert json.loads((tmp_path / "state" / "monthly_attempt.json").read_text(encoding="utf-8"))["date"] == "2026-11-05"
    log = json.loads(next((tmp_path / "runs").glob("monthly_refresh_*.json")).read_text(encoding="utf-8"))
    assert log["aborted_at_step"] == "1_pull_data" and log["steps"]["1_pull_data"]["status"] == "ABORTED" and "pem107" in log["error"]["message"] and log["pushed"] is False
    assert log["steps_not_run"] == mr.STEP_ORDER[1:]
    # the same day (Task Scheduler's RestartOnFailure): the attempt guard exits 0 at once, nothing is pulled again
    pulled_before = list(monthly["ran"])
    assert _run_cli(monkeypatch, tmp_path, monthly, date(2026, 11, 5), called) == 0 and monthly["ran"] == pulled_before and called == []
    # the next working day: due again ("run day made up"), the source has recovered, the run goes through every step and records the success
    monthly["counts"]["pem107"] = 1000
    assert mr.monthly_run_due(date(2026, 11, 6), state) == (True, "run day made up (the run day was 2026-11-05)")
    assert _run_cli(monkeypatch, tmp_path, monthly, date(2026, 11, 6), called) == 0
    assert called[0] == "2" and called[-1] in ("11", "backup")
    assert json.loads((tmp_path / "state" / "monthly_run_state.json").read_text(encoding="utf-8"))["last_success_month"] == "2026-11"
