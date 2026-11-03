"""Step 10's backtest-MAE gate and total on-hand stock gate guard the sign and the threshold exactly (Prompt 66, R2C2-002). Fixtures only; no code behind them changed."""
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import monthly_refresh as mr  # noqa: E402

CONFIG = {"monthly_refresh": {"six_month_forecast_change_pct": 25, "backtest_mae_change_pct": 20, "total_on_hand_stock_change_pct": 20}}
NEW = {"vintage_id": 1, "six_month_item_forecast_total_by_division": {}}


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    path = tmp_path / "log.csv"
    pd.DataFrame([{"vintage_id": 1, "level": "Item", "division": "A", "itemcode": "A-0", "forecast_qty": 1.0}]).to_csv(path, index=False)
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", str(path))
    monkeypatch.setattr(mr, "last_daily_stock_baseline", lambda: None)
    monkeypatch.setattr(mr, "monthly_pull_on_hand_total", lambda: None)


def _mae(entries, base="earlier run"):
    return mr.step10_change_magnitude(CONFIG, {"per_division_comparison_topdown": [{"division": d, "MAE_change_pct": p} for d, p in entries], "comparison_base": base}, NEW)


def _stock(monkeypatch, baseline_total, new_total):
    monkeypatch.setattr(mr, "last_daily_stock_baseline", lambda: None if baseline_total is None else {"on_hand_total": baseline_total, "pull_time": "2026-11-04 10:30:00", "run_id": "r"})
    monkeypatch.setattr(mr, "monthly_pull_on_hand_total", lambda: new_total)
    return mr.step10_change_magnitude(CONFIG, {"per_division_comparison_topdown": [], "comparison_base": "no earlier successful run"}, NEW)


# ------------------------------------------------------------------ backtest MAE (limit 20 %)
@pytest.mark.parametrize("pct,status", [(20.0, "passed"), (20.1, "failed"), (-20.0, "passed"), (-20.1, "failed"), (0.0, "passed"), (-5.0, "passed"), (150.0, "failed"), (-90.0, "failed")])
def test_the_mae_gate_holds_a_change_of_either_sign_only_beyond_the_limit_and_passes_exactly_at_it(quiet, pct, status):
    gate = _mae([("A", pct)])["gates"]["backtest_mae"]
    assert gate["status"] == status


def test_a_mae_failure_names_the_division_and_the_signed_percentage_and_holds_the_run(quiet):
    out = _mae([("A", -33.3), ("B", 4.0)])
    gate = out["gates"]["backtest_mae"]
    assert gate["status"] == "failed" and "A: backtest MAE changed -33.3%" in gate["reason"] and "B:" not in gate["reason"] and out["passed"] is False
    assert out["backtest_mae_change_pct_by_division"] == {"A": -33.3, "B": 4.0}


def test_a_mae_with_no_percentage_for_any_division_is_not_tested_with_the_reason_of_the_comparison_and_one_comparable_division_is_enough_to_pass(quiet):
    out = _mae([("A", None), ("B", None)], base="no earlier successful run")
    assert out["gates"]["backtest_mae"]["status"] == "not_tested" and "no earlier successful run" in out["gates"]["backtest_mae"]["reason"]
    assert _mae([("A", None), ("B", 3.0)])["gates"]["backtest_mae"]["status"] == "passed"
    assert _mae([])["gates"]["backtest_mae"]["status"] == "not_tested"


# ------------------------------------------------------------------ total on-hand stock (limit 20 %)
@pytest.mark.parametrize("new_total,status", [(1200.0, "passed"), (1201.0, "failed"), (800.0, "passed"), (799.0, "failed"), (1000.0, "passed"), (900.0, "passed"), (5000.0, "failed"), (0.0, "failed")])
def test_the_stock_gate_holds_a_change_of_either_sign_only_beyond_the_limit_and_passes_exactly_at_it(quiet, monkeypatch, new_total, status):
    assert _stock(monkeypatch, 1000.0, new_total)["gates"]["on_hand_stock"]["status"] == status


def test_a_stock_failure_states_the_signed_change_and_the_baseline_and_a_pass_states_the_sign(quiet, monkeypatch):
    down = _stock(monkeypatch, 1000.0, 700.0)
    assert down["gates"]["on_hand_stock"]["status"] == "failed" and "total on-hand stock changed -30.0%" in down["gates"]["on_hand_stock"]["reason"] and down["passed"] is False
    assert down["total_on_hand_stock"]["change_pct"] == pytest.approx(-30.0) and down["total_on_hand_stock"]["baseline_on_hand_total"] == 1000.0
    up = _stock(monkeypatch, 1000.0, 1100.0)
    assert up["gates"]["on_hand_stock"]["status"] == "passed" and "+10.0%" in up["gates"]["on_hand_stock"]["reason"]


def test_the_stock_gate_is_not_tested_without_a_baseline_without_a_new_total_or_with_a_zero_baseline(quiet, monkeypatch):
    assert _stock(monkeypatch, None, 1000.0)["gates"]["on_hand_stock"]["status"] == "not_tested"
    assert _stock(monkeypatch, 1000.0, None)["gates"]["on_hand_stock"]["status"] == "not_tested"
    assert _stock(monkeypatch, 0.0, 1000.0)["gates"]["on_hand_stock"]["status"] == "not_tested"


def test_the_two_gates_use_their_own_thresholds(quiet, monkeypatch):
    """A 25 % change is inside a six-month limit of 25 but outside the 20 of the MAE and stock gates."""
    assert _mae([("A", 25.0)])["gates"]["backtest_mae"]["status"] == "failed"
    assert _stock(monkeypatch, 1000.0, 1250.0)["gates"]["on_hand_stock"]["status"] == "failed"
