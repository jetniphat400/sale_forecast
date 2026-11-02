"""Step 10's six-month gate compares a vintage with the PREVIOUS vintage, and a re-run in the same month judges the month's stored vintage (Prompt 65, RC-002 and RC-004). Fixtures only."""
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import monthly_refresh as mr  # noqa: E402

CONFIG = {"monthly_refresh": {"six_month_forecast_change_pct": 25, "backtest_mae_change_pct": 20, "total_on_hand_stock_change_pct": 20}}
STEP4 = {"per_division_comparison_topdown": [], "comparison_base": "no earlier successful run"}


def _log(tmp_path, monkeypatch, totals_by_vintage):
    """A forward-test log whose Item rows give each vintage the total per division in `totals_by_vintage` {vintage_id: {division: total}}, split over two items."""
    rows = []
    for vid, divs in totals_by_vintage.items():
        for div, total in divs.items():
            for k in range(2):
                rows.append({"vintage_id": vid, "level": "Item", "division": div, "itemcode": f"{div}-{k}", "forecast_qty": total / 2})
            rows.append({"vintage_id": vid, "level": "Type", "division": div, "itemcode": f"{div}-T", "forecast_qty": 9999.0})      # other levels are not counted
    path = tmp_path / "log.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", str(path))
    monkeypatch.setattr(mr, "last_daily_stock_baseline", lambda: None)
    monkeypatch.setattr(mr, "monthly_pull_on_hand_total", lambda: None)


def _gate(step5):
    return mr.step10_change_magnitude(CONFIG, STEP4, step5)["gates"]["six_month_forecast"]


def test_a_new_vintage_is_compared_with_the_previous_vintage_not_with_vintage_1(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0}, 2: {"A": 140.0}})                               # vintage 2 is +40% against vintage 1 (it would not pass against vintage 1)
    g = _gate({"vintage_id": 3, "six_month_item_forecast_total_by_division": {"A": 150.0}})          # +7.1% against vintage 2, +50% against vintage 1
    assert g["status"] == "passed" and "vintage 2" in g["reason"] and "vintage 3" in g["reason"]


def test_a_breach_against_the_previous_vintage_still_holds_and_names_the_vintage(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0}, 2: {"A": 100.0}})                               # equal to vintage 1, so the old rule would have passed
    out = mr.step10_change_magnitude(CONFIG, STEP4, {"vintage_id": 3, "six_month_item_forecast_total_by_division": {"A": 140.0}})
    g = out["gates"]["six_month_forecast"]
    assert g["status"] == "failed" and "40.0%" in g["reason"] and "against vintage 2" in g["reason"] and out["passed"] is False
    rep = out["six_month_forecast_by_division"]["A"]
    assert rep["previous_vintage_id"] == 2 and rep["new_vintage_id"] == 3 and rep["change_pct"] == pytest.approx(40.0)


def test_the_threshold_is_unchanged_exactly_at_it_passes_and_just_over_fails(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0}})
    assert _gate({"vintage_id": 2, "six_month_item_forecast_total_by_division": {"A": 125.0}})["status"] == "passed"
    assert _gate({"vintage_id": 2, "six_month_item_forecast_total_by_division": {"A": 125.1}})["status"] == "failed"
    assert _gate({"vintage_id": 2, "six_month_item_forecast_total_by_division": {"A": 75.0}})["status"] == "passed"
    assert _gate({"vintage_id": 2, "six_month_item_forecast_total_by_division": {"A": 74.9}})["status"] == "failed"


def test_the_first_vintage_has_nothing_to_compare_with_and_is_not_tested_not_passed(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0}})
    g = _gate({"vintage_id": 1, "six_month_item_forecast_total_by_division": {"A": 100.0}})
    assert g["status"] == "not_tested" and "first vintage" in g["reason"]


def test_the_previous_vintage_is_the_latest_one_before_the_new_one_even_when_the_new_one_is_already_in_the_log(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0}, 3: {"A": 200.0}, 4: {"A": 230.0}})                # a real run has appended vintage 4 before step 10; ids need not be consecutive
    g = _gate({"vintage_id": 4, "six_month_item_forecast_total_by_division": {"A": 230.0}})
    assert g["status"] == "passed" and "vintage 3" in g["reason"]                                    # +15% against vintage 3 (a comparison with itself or with vintage 1 would differ)


def test_a_rerun_in_the_same_month_judges_the_stored_vintage_against_its_previous_one_and_a_breach_still_holds(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0, "B": 50.0}, 2: {"A": 100.0, "B": 80.0}})           # stored vintage 2: A unchanged, B +60%
    skipped = {"skipped": True, "reason": "one-vintage-per-calendar-month guard", "existing_vintage_id_this_month": 2}
    out = mr.step10_change_magnitude(CONFIG, STEP4, skipped)
    g = out["gates"]["six_month_forecast"]
    assert g["status"] == "failed" and "B: six-month total forecast changed 60.0%" in g["reason"] and out["passed"] is False         # the hold survives a second run
    assert out["six_month_forecast_by_division"]["B"]["new_vintage_id"] == 2


def test_a_rerun_with_the_stored_vintage_within_the_limit_passes_and_so_pushes(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0}, 2: {"A": 110.0}})
    out = mr.step10_change_magnitude(CONFIG, STEP4, {"skipped": True, "reason": "guard", "existing_vintage_id_this_month": 2})
    g = out["gates"]["six_month_forecast"]
    assert g["status"] == "passed" and "stored, re-run" in g["reason"] and out["passed"] is True
    # the step 11 decision of a real run follows the gates: passed gates push
    assert mr.step11_commit_and_push(True, {"passed": True}, {"passed": True}, out)["would_push_if_real_run"] is True


def test_a_rerun_whose_skip_names_no_stored_vintage_is_not_tested(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, {1: {"A": 100.0}})
    g = _gate({"skipped": True, "reason": "guard"})
    assert g["status"] == "not_tested" and "names no stored vintage" in g["reason"]
