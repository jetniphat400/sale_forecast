"""Forward-test vintage integrity (task C2b): a vintage's row_integrity_hash is recorded with the scheme it
was computed under, verification re-computes under that scheme, a new vintage's hash is computed only after
its rows are written and read back, and a failed or tampered vintage is reported clearly.

The fault this guards against: vintage 2's hash was computed from in-memory rows (an empty `type` hashed as
""), read back from the CSV the same cells are NaN (hashed as "nan"), and verification refused to score.
Everything here runs on small synthetic logs in a temporary folder; no real file is touched.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from forward_test_common import (HASH_SCHEME_CSV_READBACK, HASH_SCHEME_IN_MEMORY, ForwardTestConsistencyError,
                                 append_vintage_and_hash, compute_row_integrity_hash, read_forward_test_log)
from score_forward_test_all_divisions import verify_consistency

COLUMNS = ["vintage_id", "itemcode", "division", "level", "category", "type", "forecast_run_date", "data_cutoff_date",
           "fit_last_month", "config_version", "date_key", "scope_hash", "scope_n_items", "model", "horizon",
           "target_month", "forecast_qty", "actual_qty"]


def make_rows(vintage_id: int, run_date: str = "2026-10-02", fit_last: str = "2026-08") -> pd.DataFrame:
    """Item rows (with a type) and Category rows (type is the empty string, as the runner builds them)."""
    records = []
    for h in range(1, 4):
        for code, level, type_ in (("A-1", "Item", "Fuse"), ("A-2", "Item", "Arrester"), ("Fuse Cutout", "Category", "")):
            records.append({"vintage_id": vintage_id, "itemcode": code, "division": "PEM101", "level": level,
                            "category": "Fuse Cutout", "type": type_, "forecast_run_date": run_date,
                            "data_cutoff_date": run_date, "fit_last_month": fit_last, "config_version": "cfg1",
                            "date_key": "forecastDate", "scope_hash": "sh1", "scope_n_items": 2,
                            "model": "Top-down_Combination", "horizon": h, "target_month": f"2026-{8 + h:02d}",
                            "forecast_qty": round(10.123456 * h, 4), "actual_qty": ""})
    return pd.DataFrame(records, columns=COLUMNS)


def base_entry(vintage_id: int) -> dict:
    return {"vintage_id": vintage_id, "config_version": "cfg1", "date_key": "forecastDate", "scope_hash": "sh1",
            "scope_n_items": 2}


def test_a_vintage_written_and_read_back_verifies(tmp_path):
    log = str(tmp_path / "log.csv")
    entry = append_vintage_and_hash(log, make_rows(1), base_entry(1))
    assert entry["row_hash_scheme"] == HASH_SCHEME_CSV_READBACK
    verify_consistency(read_forward_test_log(log), {"1": entry})
    # a second vintage appended to the same log verifies too, each under its own recorded hash
    entry2 = append_vintage_and_hash(log, make_rows(2, "2026-11-05", "2026-09"), base_entry(2))
    verify_consistency(read_forward_test_log(log), {"1": entry, "2": entry2})


def test_the_in_memory_hash_of_rows_with_an_empty_type_differs_from_the_read_back_hash(tmp_path):
    """The fault itself: the same rows hash differently in memory and read back, under the read-back scheme."""
    rows = make_rows(2)
    log = str(tmp_path / "log.csv")
    rows.to_csv(log, index=False)
    back = read_forward_test_log(log)
    assert compute_row_integrity_hash(rows, HASH_SCHEME_CSV_READBACK) != compute_row_integrity_hash(back, HASH_SCHEME_CSV_READBACK)
    # under the in-memory scheme the two agree
    assert compute_row_integrity_hash(rows, HASH_SCHEME_IN_MEMORY) == compute_row_integrity_hash(back, HASH_SCHEME_IN_MEMORY)


def test_a_vintage_hashed_in_memory_verifies_under_its_recorded_scheme_and_not_under_the_default(tmp_path):
    rows = make_rows(2)
    log = str(tmp_path / "log.csv")
    rows.to_csv(log, index=False)
    memory_entry = dict(base_entry(2), row_integrity_hash=compute_row_integrity_hash(rows, HASH_SCHEME_IN_MEMORY),
                        row_hash_scheme=HASH_SCHEME_IN_MEMORY)
    verify_consistency(read_forward_test_log(log), {"2": memory_entry})
    # before the fix every hash was checked under the read-back scheme, which refused this vintage
    legacy_entry = dict(memory_entry)
    del legacy_entry["row_hash_scheme"]
    with pytest.raises(ForwardTestConsistencyError, match="row_hash_scheme mismatch|row_integrity_hash mismatch"):
        verify_consistency(read_forward_test_log(log), {"2": legacy_entry})


@pytest.mark.parametrize("scheme", [HASH_SCHEME_CSV_READBACK, HASH_SCHEME_IN_MEMORY])
@pytest.mark.parametrize("column,new_value", [("forecast_qty", "99.5"), ("itemcode", "ZZ-9"), ("target_month", "2030-01"),
                                              ("type", "Other"), ("horizon", "9")])
def test_tampering_with_any_hashed_value_fails_under_either_scheme(tmp_path, scheme, column, new_value):
    rows = make_rows(2)
    log = str(tmp_path / "log.csv")
    rows.to_csv(log, index=False)
    entry = dict(base_entry(2), row_hash_scheme=scheme,
                 row_integrity_hash=compute_row_integrity_hash(read_forward_test_log(log), scheme))
    verify_consistency(read_forward_test_log(log), {"2": entry})          # intact
    tampered = pd.read_csv(log, dtype=str)
    tampered.loc[tampered.index[3], column] = new_value
    tampered.to_csv(log, index=False)
    with pytest.raises(ForwardTestConsistencyError) as err:
        verify_consistency(read_forward_test_log(log), {"2": entry})
    assert "mismatch" in str(err.value) and "vintage 2" in str(err.value)


def test_a_changed_actual_qty_is_allowed(tmp_path):
    """actual_qty is the one column METRICS.md Sec.27 lets change after a vintage is written."""
    log = str(tmp_path / "log.csv")
    entry = append_vintage_and_hash(log, make_rows(1), base_entry(1))
    filled = pd.read_csv(log, dtype=str)
    filled.loc[filled.index[0], "actual_qty"] = "12.0"
    filled.to_csv(log, index=False)
    verify_consistency(read_forward_test_log(log), {"1": entry})


def test_a_scheme_mismatch_is_reported_clearly_and_distinguished_from_tampering(tmp_path):
    rows = make_rows(2)
    log = str(tmp_path / "log.csv")
    rows.to_csv(log, index=False)
    wrong = dict(base_entry(2), row_integrity_hash=compute_row_integrity_hash(rows, HASH_SCHEME_IN_MEMORY),
                 row_hash_scheme=HASH_SCHEME_CSV_READBACK)
    with pytest.raises(ForwardTestConsistencyError) as err:
        verify_consistency(read_forward_test_log(log), {"2": wrong})
    text = str(err.value)
    assert "row_hash_scheme mismatch" in text and HASH_SCHEME_IN_MEMORY in text and HASH_SCHEME_CSV_READBACK in text
    assert "rows are intact" in text


def test_an_unknown_scheme_is_reported(tmp_path):
    rows = make_rows(2)
    log = str(tmp_path / "log.csv")
    rows.to_csv(log, index=False)
    entry = dict(base_entry(2), row_integrity_hash="0" * 64, row_hash_scheme="made_up_v9")
    with pytest.raises(ForwardTestConsistencyError, match="unknown row_hash_scheme"):
        verify_consistency(read_forward_test_log(log), {"2": entry})
    with pytest.raises(ValueError, match="unknown row hash scheme"):
        compute_row_integrity_hash(rows, "made_up_v9")


def test_a_vintage_without_a_recorded_scheme_is_checked_under_the_read_back_scheme(tmp_path):
    """Vintage 1's metadata (written before schemes were recorded) has no row_hash_scheme."""
    log = str(tmp_path / "log.csv")
    make_rows(1).to_csv(log, index=False)
    entry = dict(base_entry(1), row_integrity_hash=compute_row_integrity_hash(read_forward_test_log(log), HASH_SCHEME_CSV_READBACK))
    verify_consistency(read_forward_test_log(log), {"1": entry})


def test_the_hash_does_not_depend_on_row_order(tmp_path):
    rows = make_rows(1)
    shuffled = rows.sample(frac=1.0, random_state=3)
    for scheme in (HASH_SCHEME_CSV_READBACK, HASH_SCHEME_IN_MEMORY):
        assert compute_row_integrity_hash(rows, scheme) == compute_row_integrity_hash(shuffled, scheme)
