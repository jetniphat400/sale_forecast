"""Each vintage's fit series is saved compressed, its hash recorded in the vintage's metadata and verified when the runner scores
(METRICS.md Sec.27). Temporary folders only; the real output/forward_test folder is never written."""
import gzip
import hashlib
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import monthly_refresh as mr
import vintage_series as vs

pytestmark = pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1",
                                reason="already running inside a dry-run copy of the project")

SERIES = b"year_month,itemcode,qty\n2026-07,A-1,3\n2026-08,A-1,5\n"


def test_the_series_is_saved_compressed_and_its_hash_is_of_the_uncompressed_bytes(tmp_path):
    path = vs.save_series(SERIES, 3, str(tmp_path))
    assert os.path.basename(path) == "vintage_003_fit_series.csv.gz" and os.path.getsize(path) > 0
    assert gzip.open(path, "rb").read() == SERIES
    meta = vs.metadata_fields(SERIES, 3)
    assert meta["fit_series_sha256"] == hashlib.sha256(SERIES).hexdigest() and meta["fit_series_n_bytes"] == len(SERIES)
    assert meta["fit_series_file"] == "output/forward_test/vintage_series/vintage_003_fit_series.csv.gz"


def test_the_same_bytes_give_the_same_file(tmp_path):
    a = vs.save_series(SERIES, 3, str(tmp_path / "a"))
    b = vs.save_series(SERIES, 3, str(tmp_path / "b"))
    assert open(a, "rb").read() == open(b, "rb").read()


def test_a_saved_series_is_never_overwritten(tmp_path):
    vs.save_series(SERIES, 3, str(tmp_path))
    with pytest.raises(vs.VintageSeriesError, match="never overwritten"):
        vs.save_series(SERIES + b"x", 3, str(tmp_path))


def test_the_hash_is_written_and_verified_when_read_back(tmp_path):
    vs.save_series(SERIES, 3, str(tmp_path))
    out = vs.verify_series({"3": vs.metadata_fields(SERIES, 3)}, str(tmp_path))
    assert out == {"verified": [3], "no_series_saved": []}


def test_a_changed_or_missing_file_fails_verification(tmp_path):
    meta = {"3": vs.metadata_fields(SERIES, 3)}
    with pytest.raises(vs.VintageSeriesError, match="missing"):
        vs.verify_series(meta, str(tmp_path))
    path = vs.save_series(SERIES, 3, str(tmp_path))
    with gzip.open(path, "wb") as f:
        f.write(SERIES.replace(b"5", b"6"))
    with pytest.raises(vs.VintageSeriesError, match="hashes to"):
        vs.verify_series(meta, str(tmp_path))


def test_vintages_without_a_recorded_hash_are_reported_not_verified(tmp_path):
    vs.save_series(SERIES, 3, str(tmp_path))
    out = vs.verify_series({"1": {"vintage_id": 1}, "2": {"vintage_id": 2}, "3": vs.metadata_fields(SERIES, 3)}, str(tmp_path))
    assert out == {"verified": [3], "no_series_saved": [1, 2]}


def test_the_real_vintage_1_is_recorded_as_not_reproducible_and_vintage_2_has_a_verified_snapshot():
    meta = mr.load_metadata(mr.FORWARD_TEST_METADATA_PATH)
    assert "fit_series_sha256" not in meta["1"] and meta["1"].get("fit_series_snapshot") == "not_reproducible" and meta["1"].get("fit_series_snapshot_reason")
    assert not os.path.exists(os.path.join(vs.SERIES_DIR, vs.series_filename(1)))
    if os.path.exists(os.path.join(vs.SERIES_DIR, vs.series_filename(2))):
        assert vs.verify_series({"2": meta["2"]}) == {"verified": [2], "no_series_saved": []} and "fit_series_provenance" in meta["2"]


def test_step_5_computes_the_hash_of_exactly_the_bytes_it_fits_on():
    computed = mr.compute_new_vintage()          # read-only: computes, writes nothing
    with open(os.path.join(mr.DATA_DIR, "processed_all_divisions_monthly_qty.csv"), "rb") as f:
        on_disk = f.read()
    assert computed["fit_series_bytes"] == on_disk
    assert computed["metadata_entry"]["fit_series_sha256"] == hashlib.sha256(on_disk).hexdigest()


def _score_step_with(monkeypatch, tmp_path, meta):
    monkeypatch.setattr(vs, "SERIES_DIR", str(tmp_path))
    monkeypatch.setattr(mr, "_fill_actuals", lambda *a, **k: {})
    monkeypatch.setattr(mr, "read_forward_test_log", lambda p: pd.DataFrame())
    monkeypatch.setattr(mr, "load_metadata", lambda p: meta)
    monkeypatch.setattr(mr, "verify_comparator_log", lambda: {"exists": False})
    monkeypatch.setattr(mr, "verify_shadow_log", lambda: {"exists": False})
    monkeypatch.setattr(mr.fts, "record_scores", lambda *a, **k: {"recorded": 0})
    return mr.step6_fill_and_score(dry_run=True)


def test_the_runner_verifies_the_series_hash_when_it_scores(monkeypatch, tmp_path):
    vs.save_series(SERIES, 3, str(tmp_path))
    result = _score_step_with(monkeypatch, tmp_path, {"2": {"vintage_id": 2}, "3": vs.metadata_fields(SERIES, 3)})
    assert result["fit_series"] == {"verified": [3], "no_series_saved": [2]}


def test_the_runner_stops_before_scoring_when_the_series_hash_does_not_match(monkeypatch, tmp_path):
    vs.save_series(SERIES, 3, str(tmp_path))
    meta = {"3": {**vs.metadata_fields(SERIES, 3), "fit_series_sha256": "0" * 64}}
    with pytest.raises(mr.MonthlyRefreshAbort, match="fit series failed its hash check"):
        _score_step_with(monkeypatch, tmp_path, meta)


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Snapshots of an existing vintage's fit series and the backup of the forward-test evidence (Prompt 18). Temporary folders only: no real
# OneDrive, no database, no write to the real output folder.
# ---------------------------------------------------------------------------------------------------------------------------------------------
import io  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402

import yaml  # noqa: E402


def _have_real_vintage_2():
    return all(os.path.exists(p) for p in (mr.FORWARD_TEST_LOG_PATH, mr.FORWARD_TEST_METADATA_PATH, mr.SHADOW_LOG_PATH, mr.SHADOW_METADATA_PATH,
                                           os.path.join(vs.SERIES_DIR, vs.series_filename(2)), os.path.join(PROJECT_ROOT, "output", "data", "processed_all_divisions_monthly_qty.csv")))


def test_vintage_2_rebuilt_from_its_saved_snapshot_equals_the_production_forecast_and_the_shadow_log():
    if not _have_real_vintage_2():
        pytest.skip("no vintage 2 snapshot in this checkout (generated output)")
    meta = json.load(open(mr.FORWARD_TEST_METADATA_PATH, encoding="utf-8"))["2"]
    data = vs.read_series(2)
    assert hashlib.sha256(data).hexdigest() == meta["fit_series_sha256"] and len(data) == meta["fit_series_n_bytes"]
    sh_meta = json.load(open(mr.SHADOW_METADATA_PATH, encoding="utf-8"))["2"]
    assert sh_meta["fit_series_sha256"] == meta["fit_series_sha256"]
    check = mr.reproduce_vintage(2, pd.read_csv(io.BytesIO(data)))
    assert check["production_series_compared"] == 390 and check["production_max_abs_diff"] <= mr.SNAPSHOT_TOLERANCE
    assert check["shadow_rows_compared"] == 288 and check["shadow_max_abs_diff"] <= mr.SNAPSHOT_TOLERANCE


def test_a_series_that_does_not_reproduce_the_vintage_is_never_saved(tmp_path):
    if not _have_real_vintage_2():
        pytest.skip("no vintage 2 in this checkout (generated output)")
    monthly = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "data", "processed_all_divisions_monthly_qty.csv"))
    meta = json.load(open(mr.FORWARD_TEST_METADATA_PATH, encoding="utf-8"))
    ms = dict(meta)
    ms["2"] = {k: v for k, v in meta["2"].items() if not k.startswith("fit_series_")}          # as before the snapshot, so the function runs its check
    p = tmp_path / "meta.json"
    p.write_text(json.dumps(ms), encoding="utf-8")
    monthly.loc[monthly.index[:50], "qty"] += 7.0                                              # a revised history
    import pytest as _pt
    with _pt.MonkeyPatch.context() as mp:
        mp.setattr(mr, "FORWARD_TEST_METADATA_PATH", str(p))
        out = mr.snapshot_vintage_series(2, monthly, "test", str(tmp_path / "series"))
    assert out["saved"] is False and "does not reproduce" in out["reason"] and out["production_max_abs_diff"] > mr.SNAPSHOT_TOLERANCE
    assert not os.path.exists(tmp_path / "series")
    assert json.loads(p.read_text(encoding="utf-8"))["2"].get("fit_series_sha256") is None


def _evidence_in(tmp_path, monkeypatch):
    src = tmp_path / "output"
    (src / "series").mkdir(parents=True)
    names = {"FORWARD_TEST_LOG_PATH": "log.csv", "FORWARD_TEST_METADATA_PATH": "meta.json", "SHADOW_LOG_PATH": "shadow.csv", "SHADOW_METADATA_PATH": "shadow_meta.json",
             "SCORE_RECORD_PATH": "scores.csv", "SCORE_INTEGRITY_PATH": "scores_integrity.json"}
    for attr, n in names.items():
        (src / n).write_bytes((f"content of {n}\n" * 50).encode("utf-8"))
        monkeypatch.setattr(mr, attr, str(src / n))
    vs.save_series(SERIES, 3, str(src / "series"))
    vs.save_series(SERIES + b"2026-09,A-1,9\n", 4, str(src / "series"))
    monkeypatch.setattr(vs, "SERIES_DIR", str(src / "series"))
    return src, names


def _config():
    return yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))


def test_backup_then_restore_gives_identical_sha256_for_every_file_and_nothing_is_overwritten(tmp_path, monkeypatch):
    src, names = _evidence_in(tmp_path, monkeypatch)
    drive = tmp_path / "drive"
    drive.mkdir()
    cfg = _config()
    monkeypatch.setenv(cfg["backup"]["env_var"], str(drive))
    from datetime import datetime
    r = mr.run_backup(cfg, datetime(2026, 11, 5, 7, 30, 0))
    assert r["files"] == 8 and r["all_sha256_match"] is True and r["folder"] == "%OneDriveCommercial%\\sale_forecast_backup\\2026-11-05"
    assert str(drive) not in json.dumps(r)                                              # the resolved path is never in the result
    dest = drive / cfg["backup"]["subfolder"] / "2026-11-05"
    restored = tmp_path / "restored"
    shutil.copytree(dest, restored)
    sums = dict(line.split("  ", 1)[::-1] for line in (restored / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines())
    originals = {n: tmp_path / "output" / n for n in names.values()}
    originals.update({"vintage_series/" + f: tmp_path / "output" / "series" / f for f in ("vintage_003_fit_series.csv.gz", "vintage_004_fit_series.csv.gz")})
    for name, path in originals.items():
        assert hashlib.sha256((restored / name).read_bytes()).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest() == sums[name]
    # a second backup the same day goes to its own folder; the first stays as it is
    first_sums = (dest / "SHA256SUMS.txt").read_bytes()
    r2 = mr.run_backup(cfg, datetime(2026, 11, 5, 9, 0, 1))
    assert r2["folder"].endswith("2026-11-05_090001") and (dest / "SHA256SUMS.txt").read_bytes() == first_sums
    assert len(os.listdir(drive / cfg["backup"]["subfolder"])) == 2


def test_a_copy_that_does_not_match_its_source_fails_the_backup(tmp_path, monkeypatch):
    _evidence_in(tmp_path, monkeypatch)
    drive = tmp_path / "drive"
    drive.mkdir()
    cfg = _config()
    monkeypatch.setenv(cfg["backup"]["env_var"], str(drive))
    real = shutil.copy2

    def corrupting(a, b, *x, **k):
        out = real(a, b, *x, **k)
        if str(b).endswith("scores.csv"):
            with open(b, "ab") as f:
                f.write(b"x")
        return out
    monkeypatch.setattr(mr.shutil, "copy2", corrupting)
    with pytest.raises(mr.BackupError, match="scores.csv"):
        mr.run_backup(cfg)


def test_a_missing_environment_variable_is_a_clear_error_with_no_fallback_location(tmp_path, monkeypatch):
    _evidence_in(tmp_path, monkeypatch)
    cfg = _config()
    monkeypatch.delenv(cfg["backup"]["env_var"], raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(mr.BackupError, match="OneDriveCommercial is not set"):
        mr.run_backup(cfg)
    assert sorted(os.listdir(tmp_path)) == ["output"]                                      # nothing was created anywhere, not even a fallback folder
    monkeypatch.setenv(cfg["backup"]["env_var"], str(tmp_path / "no_such_folder"))
    with pytest.raises(mr.BackupError, match="does not exist"):
        mr.run_backup(cfg)


def _stub_all_steps(monkeypatch):
    from test_monthly_refresh_failure_log import _stub_steps
    pushed = _stub_steps(monkeypatch)
    monkeypatch.setattr(mr, "step7d_vintage_gate", lambda *a, **k: {"vintage_id": 2})
    monkeypatch.setattr(mr, "step11_commit_and_push", lambda *a, **k: pushed.append(a) or {"pushed": True})
    return pushed


def test_a_failed_backup_ends_the_job_non_zero_but_the_pages_were_built_first(tmp_path, monkeypatch):
    pushed = _stub_all_steps(monkeypatch)
    monkeypatch.setattr(mr, "RUNS_DIR", str(tmp_path / "runs"))

    def failing_backup(*a, **k):
        raise mr.BackupError("the environment variable OneDriveCommercial is not set for this process: no backup was made and no other location is used")
    monkeypatch.setattr(mr, "run_backup", failing_backup)
    log = mr.main(dry_run=False, sandbox=False, run_id="t2", run_log_dir=str(tmp_path / "logs"), offline=False, skip_tests=True)
    assert log["steps"]["7_rebuild_pages"]["status"] == "ok" and log["steps"]["7b_operation_plan"]["status"] == "ok" and log["steps"]["7c_material_plan"]["status"] == "ok"
    assert [k for k in log["steps"]] == mr.STEP_ORDER and pushed                          # every step ran, including the commit and push
    assert log["backup"]["status"] == "FAILED" and "OneDriveCommercial" in log["backup"]["error"]
    saved = json.loads((tmp_path / "logs" / "monthly_refresh_t2.json").read_text(encoding="utf-8"))
    assert saved["backup"]["status"] == "FAILED"                                          # the reason is in the run log, not lost
    monkeypatch.setattr(mr, "main", lambda **k: log)
    assert mr.cli(["--dry-run"]) == 1
    monkeypatch.setattr(mr, "main", lambda **k: {"steps": {}, "backup": {"status": "ok"}})
    assert mr.cli(["--dry-run"]) == 0


def test_a_missing_environment_variable_in_a_real_run_is_a_recorded_failure_not_a_skip(tmp_path, monkeypatch):
    _stub_all_steps(monkeypatch)
    monkeypatch.setattr(mr, "RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.delenv(_config()["backup"]["env_var"], raising=False)
    log = mr.main(dry_run=False, sandbox=False, run_id="t3", run_log_dir=str(tmp_path / "logs"), offline=False, skip_tests=True)
    assert log["backup"]["status"] == "FAILED" and "is not set" in log["backup"]["error"]
    dry = mr.main(dry_run=True, sandbox=True, run_id="t4", run_log_dir=str(tmp_path / "logs"), offline=True, skip_tests=True)
    assert dry["backup"]["status"] == "skipped"
