"""How many of the six models of the combination forecast produced a forecast, per series (Prompt 65, T2-004): recorded, stored in the vintage metadata, warned in the run log, never a failure."""
import os
import sys

import numpy as np
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import models  # noqa: E402
import monthly_refresh as mr  # noqa: E402

WINDOWS = [3, 6, 12]
TRAIN = np.array([5.0, 0.0, 7.0, 3.0, 0.0, 9.0, 4.0, 6.0, 0.0, 2.0, 8.0, 5.0, 1.0, 0.0, 6.0])


def test_every_model_is_counted_and_a_normal_series_uses_all_six():
    usage = {}
    fc = models.combination_forecast(TRAIN, 6, WINDOWS, usage, "type::T1")
    assert usage == {"type::T1": {"used": 6, "expected": 6, "failed": []}}
    assert np.array_equal(fc, models.combination_forecast(TRAIN, 6, WINDOWS))                        # recording changes no number


def test_a_model_that_fails_is_still_left_out_of_the_average_but_is_now_counted_and_named(monkeypatch):
    def broken(train, horizon):
        raise ValueError("cannot be fitted")
    monkeypatch.setattr(models, "croston_forecast", broken)
    usage = {}
    fc = models.combination_forecast(TRAIN, 6, WINDOWS, usage, "item::A1")
    assert usage["item::A1"] == {"used": 5, "expected": 6, "failed": ["Croston"]}
    others = [np.clip(f(TRAIN, 6), 0, None) for n, f in models.get_models(WINDOWS).items() if n != "Croston"]
    assert np.allclose(fc, np.mean(others, axis=0))                                                  # the run is not failed: the other five are averaged, as before


def test_forecast_all_approaches_records_every_item_and_type_series():
    from item_level_reconciliation import forecast_all_approaches
    items = {"A1": (TRAIN, "D::T1", "C"), "A2": (TRAIN + 1, "D::T1", "C")}
    types = {"D::T1": TRAIN * 2 + 1}
    usage = {}
    forecast_all_approaches(items, types, len(TRAIN), 6, usage=usage)
    assert set(usage) == {"item::A1", "item::A2", "type::D::T1"} and all(u["used"] == 6 for u in usage.values())


def test_the_summary_counts_series_by_models_used_names_the_ones_with_fewer_and_the_warning_says_so():
    usage = {"item::A": {"used": 6, "expected": 6, "failed": []}, "item::B": {"used": 6, "expected": 6, "failed": []},
             "type::X": {"used": 4, "expected": 6, "failed": ["Croston", "SBA"]}}
    s = mr.model_count_summary(usage)
    assert s == {"models_expected": 6, "series_checked": 3, "series_by_models_used": {"4": 1, "6": 2}, "series_with_fewer_models": 1,
                 "fewer": {"type::X": {"used": 4, "expected": 6, "failed": ["Croston", "SBA"]}}}
    w = mr.model_count_warnings(s)
    assert len(w) == 1 and "1 of 3 series" in w[0] and "type::X used 4 of 6" in w[0] and "Croston, SBA" in w[0]
    assert mr.model_count_warnings(mr.model_count_summary({"a": {"used": 6, "expected": 6, "failed": []}})) == [] and mr.model_count_warnings(None) == []


def test_the_count_is_in_step_5_s_vintage_metadata_and_a_warning_reaches_the_run_log_without_failing_the_run(monkeypatch, tmp_path):
    """The run with a series that used fewer models ends like any other: no abort, no failed gate, no partial flag (which would make the run exit 2 and skip the success state)."""
    from test_monthly_refresh_failure_log import _run, _stub_steps
    _stub_steps(monkeypatch)
    fewer = mr.model_count_summary({"type::X": {"used": 5, "expected": 6, "failed": ["SBA"]}, "item::A": {"used": 6, "expected": 6, "failed": []}})
    monkeypatch.setattr(mr, "step5_new_vintage", lambda *a, **k: {"skipped": False, "vintage_id": 3, "model_count": fewer, "six_month_item_forecast_total_by_division": {}})
    log = _run(monkeypatch, tmp_path)
    assert len(log["model_count_warnings"]) == 1 and "type::X used 5 of 6" in log["model_count_warnings"][0]
    assert "aborted_at_step" not in log and "failed_step" not in log and "partial" not in log and "gates_failed" not in log
    assert [k for k in log["steps"]] == mr.STEP_ORDER


def test_a_run_with_every_model_present_has_no_warning_field(monkeypatch, tmp_path):
    from test_monthly_refresh_failure_log import _run, _stub_steps
    _stub_steps(monkeypatch)
    ok = mr.model_count_summary({"item::A": {"used": 6, "expected": 6, "failed": []}})
    monkeypatch.setattr(mr, "step5_new_vintage", lambda *a, **k: {"skipped": False, "vintage_id": 3, "model_count": ok, "six_month_item_forecast_total_by_division": {}})
    assert "model_count_warnings" not in _run(monkeypatch, tmp_path)


def test_the_metadata_entry_of_a_computed_vintage_carries_the_count():
    src = open(os.path.join(PROJECT_ROOT, "src", "monthly_refresh.py"), encoding="utf-8").read()
    body = src.split("def compute_new_vintage")[1].split("def rehearse_vintage_write_and_reread")[0]
    assert '"model_count": model_count,' in body and "model_usage" in body and 'return {"vintage_id": next_vintage_id' in body
