"""R1 moving-average comparator and step 10's three gates (passed / failed / not tested). Synthetic data in temporary folders
only: no database, no real output file."""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import forward_test_scoring as fts
import ma_comparator as mac
import monthly_refresh as mr
from forward_test_common import append_vintage_and_hash, read_forward_test_log  # noqa: E402
from score_forward_test_all_divisions import verify_consistency  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1",
                                reason="already running inside a dry-run copy of the project")


# ------------------------------------------------------------------ window choice and its source
def _backtest(maes):
    """maes: {(division, model): [MAE per item]} -> item-level backtest rows (one origin)."""
    rows = []
    for (div, model), values in maes.items():
        for i, v in enumerate(values):
            rows.append({"level": "Item", "key": f"{div}-{i}", "category": f"{div}::Cat", "origin": 1, "model": model, "MAE": v,
                         "first_test_month": "2025-03", "last_test_month": "2025-08", "snapshot_pull_date": "2026-10-05 07:41:06"})
    return pd.DataFrame(rows)


def test_the_window_is_the_lowest_mean_item_mae_per_division_and_a_tie_goes_to_the_shorter_window():
    bt = _backtest({("A", "MA3"): [5, 5], ("A", "MA6"): [4, 4], ("A", "MA12"): [6, 6],
                    ("B", "MA3"): [3, 3], ("B", "MA6"): [3, 3], ("B", "MA12"): [3, 3]})
    choice = mac.choose_windows(bt, [3, 6, 12], "src.csv")
    assert mac.chosen_windows(choice) == {"A": 6, "B": 3}
    assert set(choice["source_file"]) == {"src.csv"}
    assert int(choice["chosen"].sum()) == 2


def test_the_window_uses_only_item_level_rows_of_the_candidate_windows():
    bt = _backtest({("A", "MA3"): [5], ("A", "MA6"): [4]})
    noise = pd.DataFrame([{"level": "Category", "key": "A::Cat", "category": "A::Cat", "origin": 1, "model": "MA3", "MAE": 0.0,
                           "first_test_month": "2025-03", "last_test_month": "2025-08", "snapshot_pull_date": "x"},
                          {"level": "Item", "key": "A-0", "category": "A::Cat", "origin": 1, "model": "Naive", "MAE": 0.0,
                           "first_test_month": "2025-03", "last_test_month": "2025-08", "snapshot_pull_date": "x"}])
    choice = mac.choose_windows(pd.concat([bt, noise]), [3, 6])
    assert mac.chosen_windows(choice) == {"A": 6}


def test_the_window_choice_takes_no_forward_test_input():
    import inspect
    assert list(inspect.signature(mac.choose_windows).parameters) == ["rolling_origin", "windows", "source_file"]
    assert "forward_test" not in inspect.getsource(mac.choose_windows)


def test_moving_average_rows_use_the_chosen_window_zero_for_no_history_and_never_negative():
    series = {"X": (np.array([1.0, 2, 3, 4, 5, 6]),), "Y": (np.array([0.0, 0, 0, 0, 0, 0]),)}
    info = {c: {"division": "A", "category": "Cat", "type": "T"} for c in ("X", "Y", "Z")}
    base = lambda code, div, level, cat, typ: {"itemcode": code, "division": div, "level": level, "category": cat, "type": typ}
    rows = mac.moving_average_rows(series, info, {"A": 3}, ["2026-09", "2026-10"], base, no_history_codes=["Z"])
    df = pd.DataFrame(rows)
    assert set(df["model"]) == {"MA3"} and set(df["window"]) == {3}
    assert df[df["itemcode"] == "X"]["forecast_qty"].tolist() == [5.0, 5.0]
    assert df[df["itemcode"] == "Z"]["forecast_qty"].tolist() == [0.0, 0.0]
    assert (df["forecast_qty"] >= 0).all() and len(df) == 6


# ------------------------------------------------------------------ comparator log hash written and re-read
def _comparator_rows(vid, run_date="2026-11-05"):
    recs = []
    for h in (1, 2):
        for code in ("A-1", "A-2"):
            recs.append({"vintage_id": vid, "itemcode": code, "division": "PEM101", "level": "Item", "category": "C", "type": "",
                         "forecast_run_date": run_date, "data_cutoff_date": run_date, "fit_last_month": "2026-10",
                         "config_version": "cfg1", "date_key": "forecastDate", "scope_hash": "sh1", "scope_n_items": 2,
                         "model": "MA12", "horizon": h, "target_month": f"2026-{10 + h:02d}", "forecast_qty": 3.14159 * h,
                         "actual_qty": ""})
    return pd.DataFrame(recs)


def test_the_comparator_log_hash_is_written_and_verifies_when_read_back(tmp_path):
    log = str(tmp_path / "cmp.csv")
    entry = append_vintage_and_hash(log, _comparator_rows(3),
                                    {"vintage_id": 3, "config_version": "cfg1", "date_key": "forecastDate", "scope_hash": "sh1", "scope_n_items": 2})
    verify_consistency(read_forward_test_log(log), {"3": entry})
    # a changed forecast value is caught
    back = pd.read_csv(log)
    back.loc[0, "forecast_qty"] = back.loc[0, "forecast_qty"] + 1
    back.to_csv(log, index=False)
    with pytest.raises(Exception):
        verify_consistency(read_forward_test_log(log), {"3": entry})


def test_with_no_comparator_log_the_check_says_so_and_reconstructs_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "COMPARATOR_LOG_PATH", str(tmp_path / "none.csv"))
    out = mr.verify_comparator_log()
    assert out["exists"] is False and "not reconstructed" in out["note"]
    assert not os.path.exists(tmp_path / "none.csv")


def test_comparator_actuals_are_copied_from_the_forward_test_log(tmp_path, monkeypatch):
    path = str(tmp_path / "cmp.csv")
    _comparator_rows(3).to_csv(path, index=False)
    monkeypatch.setattr(mr, "COMPARATOR_LOG_PATH", path)
    main = pd.DataFrame([{"level": "Item", "itemcode": "A-1", "target_month": "2026-11", "actual_qty": 7.0},
                         {"level": "Item", "itemcode": "A-2", "target_month": "2026-11", "actual_qty": ""}])
    assert mr.fill_comparator_actuals(main)["filled"] == 1
    back = pd.read_csv(path)
    assert back[(back["itemcode"] == "A-1") & (back["target_month"] == "2026-11")]["actual_qty"].iloc[0] == 7.0
    assert back[(back["itemcode"] == "A-2") & (back["target_month"] == "2026-11")]["actual_qty"].isna().all()


# ------------------------------------------------------------------ scoring of both methods
def test_both_methods_are_scored_with_the_same_metrics_under_separate_scopes():
    raw = pd.DataFrame([{"itemcode": "A", "createDate": f"2024-{m:02d}-01", "forecast_date": f"2024-{m:02d}-01", "qty": q, "division": "PEM101"}
                        for m, q in enumerate([1, 3, 2, 4, 3, 5], start=1)])
    meta = {"1": {"fit_first_month": "2024-01", "fit_last_month": "2024-06"}}
    top = pd.DataFrame([{"vintage_id": 1, "level": "Item", "itemcode": "A", "division": "PEM101", "horizon": 1, "target_month": "2024-07",
                         "model": "Top-down_Combination", "forecast_qty": 5.0, "actual_qty": 4.0}])
    cmp_ = top.assign(model="MA6", forecast_qty=3.0)
    a = fts.compute_score_rows(top, meta, raw, "r1")
    b = fts.compute_score_rows(cmp_, meta, raw, "r1", comparator=True)
    assert set(a["scope"]) == {"division"} and set(b["scope"]) == {"comparator_division"}
    assert b.iloc[0]["key"] == "PEM101|MA6" and a.iloc[0]["key"] == "PEM101"
    assert list(a.columns) == list(b.columns) == fts.SCORE_COLUMNS
    assert a.iloc[0]["MAE"] == pytest.approx(1.0) and b.iloc[0]["MAE"] == pytest.approx(1.0)
    assert a.iloc[0]["Bias"] == pytest.approx(1.0) and b.iloc[0]["Bias"] == pytest.approx(-1.0)


# ------------------------------------------------------------------ step 10 gates
CONFIG = {"monthly_refresh": {"six_month_forecast_change_pct": 20, "backtest_mae_change_pct": 20, "total_on_hand_stock_change_pct": 20}}


@pytest.fixture
def stock(monkeypatch, tmp_path):
    monkeypatch.setattr(mr, "FORWARD_TEST_LOG_PATH", str(tmp_path / "log.csv"))
    monkeypatch.setattr(mr, "INVENTORY_JSON_PATH", str(tmp_path / "none.json"))
    pd.DataFrame([{"vintage_id": 1, "level": "Item", "division": "PEM101", "forecast_qty": 100.0}]).to_csv(tmp_path / "log.csv", index=False)

    def set_(baseline, new):
        monkeypatch.setattr(mr, "last_daily_stock_baseline", lambda: baseline)
        monkeypatch.setattr(mr, "monthly_pull_on_hand_total", lambda: new)
    return set_


BASE = {"on_hand_total": 1000.0, "pull_time": "2026-10-05 11:12:26", "run_id": "d1"}
STEP4_OK = {"per_division_comparison_topdown": [{"division": "PEM101", "MAE_change_pct": 1.0}]}
STEP5_OK = {"six_month_item_forecast_total_by_division": {"PEM101": 105.0}}


def test_every_gate_passes_when_everything_is_within_threshold(stock):
    stock(BASE, 1050.0)
    out = mr.step10_change_magnitude(CONFIG, STEP4_OK, STEP5_OK)
    assert {g["status"] for g in out["gates"].values()} == {"passed"}
    assert out["gate_counts"] == {"passed": 3, "failed": 0, "not_tested": 0} and out["passed"] is True


def test_each_gate_fails_when_its_threshold_is_exceeded(stock):
    stock(BASE, 2000.0)
    out = mr.step10_change_magnitude(CONFIG, {"per_division_comparison_topdown": [{"division": "PEM101", "MAE_change_pct": 50.0}]},
                                     {"six_month_item_forecast_total_by_division": {"PEM101": 300.0}})
    assert {g["status"] for g in out["gates"].values()} == {"failed"}
    assert out["gate_counts"]["failed"] == 3 and out["passed"] is False and len(out["violations"]) == 3


def test_when_step_5_skips_the_six_month_gate_is_not_tested_and_is_not_counted_as_passed(stock):
    stock(BASE, 1050.0)
    out = mr.step10_change_magnitude(CONFIG, STEP4_OK, {"skipped": True, "reason": "vintage already exists for this month"})
    g = out["gates"]["six_month_forecast"]
    assert g["status"] == "not_tested" and "step 5 skipped" in g["reason"]
    assert out["gate_counts"] == {"passed": 2, "failed": 0, "not_tested": 1} and out["passed"] is True


def test_without_an_earlier_run_the_mae_gate_is_not_tested(stock):
    stock(BASE, 1050.0)
    out = mr.step10_change_magnitude(CONFIG, {"per_division_comparison_topdown": [], "comparison_base": "no earlier successful run"}, STEP5_OK)
    assert out["gates"]["backtest_mae"] == {"status": "not_tested", "reason": "no earlier successful run"}


@pytest.mark.parametrize("baseline,new,word", [(None, 1050.0, "no successful daily stock run"), (BASE, None, "saved no stock pull")])
def test_without_a_daily_baseline_or_a_pull_the_on_hand_gate_is_not_tested(stock, baseline, new, word):
    stock(baseline, new)
    g = mr.step10_change_magnitude(CONFIG, STEP4_OK, STEP5_OK)["gates"]["on_hand_stock"]
    assert g["status"] == "not_tested" and word in g["reason"]


def test_the_on_hand_baseline_is_the_daily_runs_published_stock(stock):
    stock(BASE, 1100.0)
    rep = mr.step10_change_magnitude(CONFIG, STEP4_OK, STEP5_OK)["total_on_hand_stock"]
    assert rep["baseline_on_hand_total"] == 1000.0 and rep["baseline_daily_run_id"] == "d1" and rep["change_pct"] == pytest.approx(10.0)


def test_the_run_outcome_counts_not_tested_separately_from_passed():
    gates = {"a": {"status": "passed", "reason": ""}, "b": {"status": "not_tested", "reason": "x"}, "c": {"status": "failed", "reason": "y"}}
    assert mr.count_gates(gates) == {"passed": 1, "failed": 1, "not_tested": 1}
    out = mr.gate_outcomes({"skipped": True, "summary_line": "skipped"}, {"passed": True, "findings": [], "n_changed_files_scanned": 3},
                           {"gates": {"six_month_forecast": {"status": "not_tested", "reason": "r"}, "on_hand_stock": {"status": "passed", "reason": ""}}})
    assert out["counts"] == {"passed": 2, "failed": 0, "not_tested": 2}
    assert out["not_tested"] == ["step10_six_month_forecast", "tests"]
