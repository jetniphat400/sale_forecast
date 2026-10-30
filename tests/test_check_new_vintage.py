"""The manual check of the new vintage after the first real monthly run (src/check_new_vintage.py, Prompt 63): fixtures only, read only."""
import hashlib
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import check_new_vintage as cv  # noqa: E402


def _log(rows):
    """rows: (vintage, division, month, qty, level)."""
    return pd.DataFrame([{"vintage_id": v, "itemcode": f"{d}-{i}", "division": d, "level": lvl, "target_month": m, "forecast_qty": q} for i, (v, d, m, q, lvl) in enumerate(rows)])


BASE = [(2, "PEM101", "2026-11", 100, "Item"), (2, "PEM101", "2026-12", 100, "Item"), (2, "PEM107", "2026-11", 10, "Item"), (2, "PEM107", "2026-12", 10, "Item"),
        (2, "PEM101", "2026-10", 999, "Item")]                                                  # 2026-10 is not forecast by vintage 3: outside the overlap


def test_a_division_that_moves_by_more_than_the_threshold_is_flagged_and_the_others_are_not():
    new = [(3, "PEM101", "2026-11", 110, "Item"), (3, "PEM101", "2026-12", 105, "Item"), (3, "PEM107", "2026-11", 14, "Item"), (3, "PEM107", "2026-12", 14, "Item"), (3, "PEM101", "2027-01", 500, "Item")]
    r = cv.compare(_log(BASE + new))
    by = {x["division"]: x for x in r["rows"]}
    assert r["new"] == 3 and r["old"] == 2 and r["months"] == ["2026-11", "2026-12"]
    assert by["PEM101"]["old_total"] == 200 and by["PEM101"]["new_total"] == 215 and not by["PEM101"]["flag"]          # 2026-10 and 2027-01 are not in both vintages
    assert round(by["PEM107"]["change_pct"], 1) == 40.0 and by["PEM107"]["flag"]
    assert by["COMPANY"]["old_total"] == 220 and by["COMPANY"]["new_total"] == 243 and not by["COMPANY"]["flag"]
    assert r["flagged"] == ["PEM107"]


def test_exactly_at_the_threshold_is_not_flagged_and_just_over_is():
    new = [(3, "PEM101", "2026-11", 130, "Item"), (3, "PEM101", "2026-12", 130, "Item"), (3, "PEM107", "2026-11", 13.1, "Item"), (3, "PEM107", "2026-12", 13.1, "Item")]
    by = {x["division"]: x for x in cv.compare(_log(BASE + new))["rows"]}
    assert by["PEM101"]["change_pct"] == pytest.approx(30.0) and not by["PEM101"]["flag"] and by["PEM107"]["flag"]
    assert not {x["division"]: x for x in cv.compare(_log(BASE + new), threshold=32)["rows"]}["PEM107"]["flag"]


def test_category_and_type_rows_are_not_counted_twice_and_a_division_with_no_old_total_is_flagged():
    new = [(3, "PEM101", "2026-11", 100, "Item"), (3, "PEM101", "2026-12", 100, "Item"), (3, "PEM101", "2026-11", 100, "Category"), (3, "PEM101", "2026-11", 100, "Type"),
           (3, "NEW1", "2026-11", 5, "Item")]
    by = {x["division"]: x for x in cv.compare(_log(BASE + new))["rows"]}
    assert by["PEM101"]["new_total"] == 200 and by["NEW1"]["change_pct"] is None and by["NEW1"]["flag"]


def test_a_missing_vintage_or_no_shared_month_cannot_be_compared():
    with pytest.raises(cv.VintageCheckError, match="vintage 3 is not in the log"):
        cv.compare(_log(BASE), new=3, old=2)
    with pytest.raises(cv.VintageCheckError, match="share no target month"):
        cv.compare(_log(BASE + [(3, "PEM101", "2027-06", 1, "Item")]))
    with pytest.raises(cv.VintageCheckError, match="no Item rows"):
        cv.compare(_log([(2, "PEM101", "2026-11", 1, "Category")]))


def test_the_command_exit_codes_the_text_and_that_it_writes_nothing(tmp_path, capsys):
    new = [(3, "PEM101", "2026-11", 100, "Item"), (3, "PEM101", "2026-12", 100, "Item"), (3, "PEM107", "2026-11", 30, "Item"), (3, "PEM107", "2026-12", 30, "Item")]
    path = tmp_path / "log.csv"
    _log(BASE + new).to_csv(path, index=False)
    before, listing = hashlib.sha256(path.read_bytes()).hexdigest(), sorted(os.listdir(tmp_path))
    assert cv.main(["--log", str(path)]) == 1
    out = capsys.readouterr().out
    assert "Vintage 3 against vintage 2" in out and "PEM107" in out and "FLAG" in out and "RESULT: flagged: PEM107" in out and "COMPANY" in out
    assert cv.main(["--log", str(path), "--threshold", "250"]) == 0 and "nothing flagged" in capsys.readouterr().out
    assert cv.main(["--log", str(tmp_path / "absent.csv")]) == 2 and "CANNOT COMPARE" in capsys.readouterr().out
    assert cv.main(["--log", str(path), "--new", "9"]) == 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before and sorted(os.listdir(tmp_path)) == listing          # read only
