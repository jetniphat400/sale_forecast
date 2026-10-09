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


def test_the_real_vintages_1_and_2_have_no_saved_series_and_are_untouched():
    meta = mr.load_metadata(mr.FORWARD_TEST_METADATA_PATH)
    assert all("fit_series_sha256" not in meta[k] for k in ("1", "2"))
    assert not os.path.exists(os.path.join(vs.SERIES_DIR, vs.series_filename(1)))


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
