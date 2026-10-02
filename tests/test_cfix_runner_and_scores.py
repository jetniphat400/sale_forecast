"""C-fix: forward-test scores on the backtest's definition, the append-only score record, step 10's comparison base,
and step 11's explicit staging list. Synthetic data in temporary folders only: no database, no real output file."""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import forward_test_scoring as fts
import monthly_refresh as mr
from backtest_rekeyed import compute_metrics

pytestmark = pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1",
                                reason="already running inside a dry-run copy of the project")


# ------------------------------------------------------------------ scores follow the backtest's definition

def _raw(items):
    """items: {code: [monthly qty over 2024-01..]} -> raw rows (createDate = forecast_date = 1st of the month)."""
    rows = []
    for code, qs in items.items():
        for i, q in enumerate(qs):
            d = str(pd.Period("2024-01", "M") + i) + "-01"
            rows.append({"itemcode": code, "createDate": d, "forecast_date": d, "qty": q, "division": "PEM101"})
    return pd.DataFrame(rows)


def _log(rows):
    return pd.DataFrame([{"vintage_id": 1, "level": "Item", "itemcode": c, "division": d, "horizon": 1,
                          "target_month": "2024-07", "forecast_qty": f, "actual_qty": a} for c, d, f, a in rows])


META = {"1": {"fit_first_month": "2024-01", "fit_last_month": "2024-06"}}


def test_mase_is_the_mean_of_per_item_mase_with_the_fit_series_scale_and_undefined_items_left_out():
    raw = _raw({"A": [1, 3, 2, 4, 3, 5], "B": [2, 2, 2, 2, 2, 2], "C": [0, 0, 0, 0, 0, 0]})
    log = _log([("A", "PEM101", 5.0, 4.0), ("B", "PEM101", 3.0, 1.0), ("C", "PEM101", 1.0, 0.0)])
    out = fts.compute_score_rows(log, META, raw, "r1")
    row = out[(out["scope"] == "division") & (out["key"] == "PEM101")].iloc[0]
    scale_a = np.mean(np.abs(np.diff([1, 3, 2, 4, 3, 5])))
    assert row["n_items"] == 2, "an all-zero fit series is not scored (the backtest's own rule)"
    assert row["n_mase_defined"] == 1, "B's scale is 0: its MASE is undefined and left out of the mean"
    assert row["MASE"] == pytest.approx(1.0 / scale_a)
    assert row["MAE"] == pytest.approx((1.0 + 2.0) / 2)
    assert row["Bias"] == pytest.approx((1.0 + 2.0) / 2)
    assert row["RMSE_pooled"] == pytest.approx(np.sqrt((1.0 + 4.0) / 2))
    ref = compute_metrics(np.array([4.0]), np.array([5.0]), np.array([1, 3, 2, 4, 3, 5], dtype=float))
    assert row["MASE"] == pytest.approx(ref["MASE"]), "must be backtest_rekeyed.compute_metrics itself"


def test_a_vintage_month_with_a_missing_actual_is_not_scored_yet():
    raw = _raw({"A": [1, 3, 2, 4, 3, 5]})
    log = _log([("A", "PEM101", 5.0, np.nan)])
    assert fts.compute_score_rows(log, META, raw, "r1").empty


# ------------------------------------------------------------------ the append-only record

def _score_rows(run_id, month="2024-07", mae=1.0):
    return pd.DataFrame([{"score_run_id": run_id, "vintage_id": 1, "scope": "division", "key": "PEM101",
                          "target_month": month, "horizon": 1, "n_items": 2, "n_mase_defined": 2, "MAE": mae,
                          "RMSE": mae, "RMSE_pooled": mae, "Bias": 0.5, "MASE": 1.25, "definition": fts.DEFINITION,
                          "fit_first_month": "2024-01", "fit_last_month": "2024-06", "recorded_at": "2026-10-02T09:00:00"}])


def test_the_record_is_append_only_and_hashed_after_read_back(tmp_path):
    sp, ip = str(tmp_path / "s.csv"), str(tmp_path / "i.json")
    r = fts.append_scores(_score_rows("run1"), sp, ip)
    assert r["appended"] == 1 and fts.verify_score_record(sp, ip) == 1
    before = open(sp, "rb").read()
    again = fts.append_scores(_score_rows("run2", mae=99.0), sp, ip)   # same key: already recorded, never replaced
    assert again["appended"] == 0 and open(sp, "rb").read() == before
    fts.append_scores(_score_rows("run3", month="2024-08"), sp, ip)
    assert open(sp, "rb").read().startswith(before), "earlier rows are untouched byte for byte"
    assert fts.verify_score_record(sp, ip) == 2


def test_an_edited_row_fails_verification_and_blocks_further_appends(tmp_path):
    sp, ip = str(tmp_path / "s.csv"), str(tmp_path / "i.json")
    fts.append_scores(_score_rows("run1"), sp, ip)
    text = open(sp, encoding="utf-8").read().replace(",1.0,1.0,1.0,0.5,", ",2.0,1.0,1.0,0.5,")
    open(sp, "w", encoding="utf-8", newline="").write(text)
    with pytest.raises(fts.ScoreRecordError):
        fts.verify_score_record(sp, ip)
    with pytest.raises(fts.ScoreRecordError):
        fts.append_scores(_score_rows("run2", month="2024-08"), sp, ip)


# ------------------------------------------------------------------ Part 4: step 10 / step 4 comparison base

def _run_log(run_id, started, ok=True, dry=False, mae=10.0, pushed=True, fail_step=None):
    steps = {k: {"status": "ok"} for k in mr.STEP_ORDER}
    steps["4_backtest"]["result"] = {"per_division_comparison_topdown": [
        {"division": "PEM101", "new_MAE": mae, "new_RMSE": mae, "new_Bias": 0.0, "new_MASE": 1.0}]}
    steps["11_commit_and_push"]["result"] = {"pushed": pushed}
    log = {"run_id": run_id, "dry_run": dry, "started_at": started, "steps": steps}
    if fail_step:
        steps[fail_step] = {"status": "FAILED"}
        log["aborted_at_step"] = fail_step
    return log


def test_the_comparison_base_is_the_last_successful_run_not_a_failed_run_in_between(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    for log in (_run_log("s1", "2026-10-02T08:12:25", mae=10.0),
                _run_log("f1", "2026-10-02T09:00:00", mae=99.0, fail_step="6_fill_and_score"),   # failed AFTER step 4 wrote
                _run_log("d1", "2026-10-02T09:30:00", mae=77.0, dry=True),
                _run_log("h1", "2026-10-02T09:40:00", mae=55.0, pushed=False),                    # gates held the commit
                _run_log("s0", "2026-09-25T08:00:00", mae=5.0)):
        (runs / f"monthly_refresh_{log['run_id']}.json").write_text(json.dumps(log), encoding="utf-8")
    best = mr.find_last_successful_run(str(runs))
    assert best["run_id"] == "s1"
    assert mr.baseline_from_run_log(best)["PEM101"]["MAE"] == 10.0
    # a later successful run takes over; the failed run between two successes was never the base
    (runs / "monthly_refresh_s2.json").write_text(json.dumps(_run_log("s2", "2026-11-02T08:00:00", mae=12.0)), encoding="utf-8")
    assert mr.find_last_successful_run(str(runs))["run_id"] == "s2"


def test_step4_compares_with_the_successful_runs_figures(monkeypatch, tmp_path):
    """Step 4 with its scripts stubbed: the files on disk say 99 (a failed run overwrote them), the last successful run said 10."""
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "monthly_refresh_s1.json").write_text(json.dumps(_run_log("s1", "2026-10-02T08:12:25", mae=10.0)), encoding="utf-8")
    monkeypatch.setattr(mr, "RUNS_DIR", str(runs))
    monkeypatch.setattr(mr, "SUMMARY_DIR", str(tmp_path))
    pd_path, tr_path = str(tmp_path / "pd.csv"), str(tmp_path / "tr.csv")
    monkeypatch.setattr(mr, "PER_DIVISION_SUMMARY_PATH", pd_path)
    monkeypatch.setattr(mr, "TRANSFERABILITY_PATH", tr_path)
    pd.DataFrame([{"division": "PEM101", "MAE": 1.0}]).to_csv(pd_path, index=False)
    pd.DataFrame([{"division": "PEM101", "approach": "Top-down", "MAE": 99.0, "RMSE": 99.0, "Bias": 0.0, "MASE": 1.0}]).to_csv(tr_path, index=False)

    class P:
        returncode, stderr = 0, ""
    monkeypatch.setattr(mr, "run_script", lambda *a, **k: P())
    monkeypatch.setattr(mr, "_run_regeneration_step", lambda *a, **k: {"refreshed": True})
    pd.DataFrame([{"division": "PEM101", "approach": "Top-down", "MAE": 11.0, "RMSE": 11.0, "Bias": 0.0, "MASE": 1.0}]).to_csv(tr_path, index=False)
    out = mr.step4_backtest("t", offline=True)
    e = out["per_division_comparison_topdown"][0]
    assert out["comparison_base_run_id"] == "s1" and e["previous_MAE"] == 10.0 and e["MAE_change_pct"] == pytest.approx(10.0)


# ------------------------------------------------------------------ Part 7: explicit staging list

def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = str(tmp_path / "repo")
    os.makedirs(os.path.join(r, "forecast"))
    os.makedirs(os.path.join(r, "data"))
    for rel in mr.GENERATED_PATHS + ["notes.md"]:
        open(os.path.join(r, rel), "w").write("v1\n")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    monkeypatch.setattr(mr, "PROJECT_ROOT", r)
    monkeypatch.setattr(mr, "check_tcp_reachable", lambda *a, **k: (True, None))
    return r


GATES = ({"passed": True}, {"passed": True}, {"passed": True})


def test_only_the_generated_paths_are_staged_and_committed(repo, monkeypatch):
    for rel in mr.GENERATED_PATHS:
        open(os.path.join(repo, rel), "w").write("v2\n")
    open(os.path.join(repo, "untracked.txt"), "w").write("x\n")       # untracked: never staged by an explicit add
    monkeypatch.setattr(subprocess, "run", _no_push(subprocess.run))
    result = mr.step11_commit_and_push(False, *GATES)
    assert "committed" not in result or result["pushed"] in (True, False)
    files = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(files) == sorted(mr.GENERATED_PATHS)


def test_a_stray_modified_file_stops_the_run_before_anything_is_staged(repo, monkeypatch):
    for rel in mr.GENERATED_PATHS:
        open(os.path.join(repo, rel), "w").write("v2\n")
    open(os.path.join(repo, "notes.md"), "w").write("someone's edit\n")
    head = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(mr.MonthlyRefreshAbort, match="notes.md"):
        mr.step11_commit_and_push(False, *GATES)
    assert _git(repo, "rev-parse", "HEAD") == head and _git(repo, "diff", "--cached", "--name-only").strip() == ""


def test_a_stray_file_stages_nothing_and_the_run_log_says_so(repo, monkeypatch, tmp_path):
    open(os.path.join(repo, "notes.md"), "w").write("someone's edit\n")
    _git(repo, "add", "notes.md")                                       # staged by someone else
    with pytest.raises(mr.MonthlyRefreshAbort):
        mr.step11_commit_and_push(False, *GATES)
    assert _git(repo, "diff", "--cached", "--name-only").split() == ["notes.md"]


def _no_push(real_run):
    def run(cmd, *a, **k):
        if cmd[:2] == ["git", "push"]:
            return subprocess.CompletedProcess(cmd, 0, "pushed (stub)", "")
        return real_run(cmd, *a, **k)
    return run


# ------------------------------------------------------------------ Parts 1 and 2: the runner pulls and rebuilds what the pages read

class _Proc:
    def __init__(self, rc=0):
        self.returncode, self.stdout, self.stderr = rc, "", "boom" if rc else ""


def test_inventory_json_is_regenerated_from_the_saved_pull_and_must_carry_its_time(monkeypatch, tmp_path):
    pull = tmp_path / "pull"
    pull.mkdir()
    (pull / "pull_meta.json").write_text(json.dumps({"pulled_at_utc": "2026-10-02T01:12:31Z", "pulled_at_local": "2026-10-02 08:12:31"}))
    inv = tmp_path / "inventory.json"
    monkeypatch.setattr(mr, "INVENTORY_PULL_DIR", str(pull))
    monkeypatch.setattr(mr, "INVENTORY_JSON_PATH", str(inv))
    calls = []

    def fake_run(script, args=None):
        calls.append((script, args))
        inv.write_text(json.dumps({"snapshot": {"generated_at": "2026-10-02T01:12:31Z"}}))
        return _Proc()
    monkeypatch.setattr(mr, "run_script", fake_run)
    out = mr.regenerate_inventory_json({"inventory_pull": {"refreshed": True}})
    assert out["regenerated"] is True and out["data_pulled_at_utc"] == "2026-10-02T01:12:31Z"
    assert calls == [("build_inventory_dataset.py", ["--from-pulls", str(pull)])]
    # a build that carries another time than the pull is refused
    inv.write_text("")
    monkeypatch.setattr(mr, "run_script", lambda *a, **k: (inv.write_text(json.dumps({"snapshot": {"generated_at": "2099-01-01T00:00:00Z"}})), _Proc())[1])
    with pytest.raises(mr.MonthlyRefreshAbort, match="generated at"):
        mr.regenerate_inventory_json({"inventory_pull": {"refreshed": True}})


def test_inventory_json_is_left_alone_and_the_log_says_why_when_there_is_no_fresh_pull(monkeypatch, tmp_path):
    monkeypatch.setattr(mr, "INVENTORY_PULL_DIR", str(tmp_path / "none"))
    assert mr.regenerate_inventory_json({})["regenerated"] is False
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "pull_meta.json").write_text("{}")
    monkeypatch.setattr(mr, "INVENTORY_PULL_DIR", str(tmp_path / "p"))
    out = mr.regenerate_inventory_json({"inventory_pull": {"refreshed": False, "not_refreshed_reason": "script exited 1"}})
    assert out["regenerated"] is False and "script exited 1" in out["reason"]


def test_step1_pulls_the_pilot_file_and_the_inventory_tables_in_the_same_stage(monkeypatch, tmp_path):
    seen = []

    def fake_stage(label, script, output_path, args=None):
        seen.append((script, args))
        return {"label": label, "script": script, "refreshed": True}
    monkeypatch.setattr(mr, "_pull_stage", fake_stage)
    monkeypatch.setattr(mr, "check_tcp_reachable", lambda *a, **k: (True, None))
    monkeypatch.setattr(mr, "run_script", lambda *a, **k: _Proc())
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: pd.DataFrame({"snapshot_pull_date": ["2026-10-05 07:00:01"], "itemcode": ["A"], "division": ["PEM101"]}))
    out = mr.step1_pull_data(False, offline=False)
    assert [s for s, _ in seen] == ["load_data_full.py", "build_inventory_dataset.py"]
    assert seen[1][1][0] == "--save-pulls" and out["pilot_128item_refresh"]["refreshed"] and out["inventory_pull"]["refreshed"]


def test_step4_regenerates_the_pilot_derived_inputs(monkeypatch, tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(mr, "RUNS_DIR", str(runs))
    monkeypatch.setattr(mr, "SUMMARY_DIR", str(tmp_path))
    pd_path, tr_path = str(tmp_path / "pd.csv"), str(tmp_path / "tr.csv")
    monkeypatch.setattr(mr, "PER_DIVISION_SUMMARY_PATH", pd_path)
    monkeypatch.setattr(mr, "TRANSFERABILITY_PATH", tr_path)
    pd.DataFrame([{"division": "PEM101", "MAE": 1.0}]).to_csv(pd_path, index=False)
    pd.DataFrame([{"division": "PEM101", "approach": "Top-down", "MAE": 1.0, "RMSE": 1.0, "Bias": 0.0, "MASE": 1.0}]).to_csv(tr_path, index=False)
    monkeypatch.setattr(mr, "run_script", lambda *a, **k: _Proc())
    labels = []
    monkeypatch.setattr(mr, "_run_regeneration_step", lambda label, script, out, skip_reason=None: labels.append(script) or {"refreshed": True})
    mr.step4_backtest("t", offline=True)
    assert "build_report_data.py" in labels and "item_level_reconciliation.py" in labels
