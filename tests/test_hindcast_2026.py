"""The 2026 hindcast (src/investigations/hindcast_2026.py, Prompt 64 step 3): the guards against leakage and the arithmetic of the measures. Fixtures only: no database, no real output file."""
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "investigations"))
import hindcast_2026 as hc  # noqa: E402

CONFIG = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))
MARGIN = int(CONFIG["leakage_guard"]["min_margin_days"])
WINDOWS = {"D1": 3, "D2": 6}


def _fixture(first="2024-03", last="2026-09", seed=7):
    """A small invented series: two divisions, three types, six items (one with no sale at all), one value per item and month."""
    months = [str(p) for p in pd.period_range(first, last, freq="M")]
    rng = np.random.default_rng(seed)
    items = [("A1", "D1", "T1"), ("A2", "D1", "T1"), ("A3", "D1", "T2"), ("B1", "D2", "T3"), ("B2", "D2", "T3"), ("Z0", "D2", "T3")]
    scope = pd.DataFrame([{"code": c, "sheet": "s", "division": d, "category": "C" + d, "type": t} for c, d, t in items])
    rows = []
    for c, d, t in items:
        for i, m in enumerate(months):
            q = 0.0 if c == "Z0" else float(rng.integers(0, 30) + (10 if c in ("A1", "B1") else 0))
            rows.append({"itemcode": c, "year_month": m, "qty": q, "snapshot_pull_date": "2026-10-30 13:00:00", "category": "C" + d, "type": t, "division": d})
    return pd.DataFrame(rows), scope


# ------------------------------------------------------------------ the fit month of a run: the project's own leakage guard at the run day
@pytest.mark.parametrize("month,run_day,fit_last", [("2025-10", date(2025, 10, 6), "2025-08"), ("2026-01", date(2026, 1, 5), "2025-11"), ("2026-03", date(2026, 3, 5), "2026-01"),
                                                    ("2026-09", date(2026, 9, 7), "2026-07")])
def test_the_run_day_and_the_fit_month_of_a_simulated_run_follow_the_runner_rules(month, run_day, fit_last):
    assert hc.run_date_of(month) == run_day and run_day.weekday() < 5
    months = [str(p) for p in pd.period_range("2024-03", "2026-09", freq="M")]
    assert hc.fit_last_month_for(run_day, months, MARGIN) == fit_last
    # first principles: the month ends at least MARGIN days before the run day, and the next month does not
    end = lambda ym: (pd.Period(ym, freq="M").end_time.normalize())      # noqa: E731
    assert (pd.Timestamp(run_day) - end(fit_last)).days >= MARGIN
    assert (pd.Timestamp(run_day) - end(str(pd.Period(fit_last, freq="M") + 1))).days < MARGIN


# ------------------------------------------------------------------ the input of a run ends at its fit month
def test_the_series_a_run_sees_ends_at_its_fit_month_and_a_cut_that_does_not_is_refused():
    monthly, _ = _fixture()
    cut = hc.cut_series(monthly, "2025-11")
    assert cut["year_month"].max() == "2025-11" and cut["year_month"].min() == "2024-03" and (cut["year_month"] <= "2025-11").all()
    with pytest.raises(hc.HindcastError, match="does not end at its fit_last_month"):
        hc.cut_series(monthly[monthly["year_month"] <= "2025-06"], "2025-11")


def test_every_simulated_run_is_given_input_that_ends_at_its_own_fit_month(monkeypatch):
    monthly, scope = _fixture()
    seen = []
    real = hc.cut_series
    monkeypatch.setattr(hc, "cut_series", lambda m, fit_last: seen.append((fit_last, real(m, fit_last)["year_month"].max())) or real(m, fit_last))
    sim = hc.simulate(monthly, scope, WINDOWS, MARGIN)
    assert len(seen) == 13 and all(fit_last == last for fit_last, last in seen)                       # 12 monthly runs (A) and the January run (B)
    runs = sim.drop_duplicates(["family", "run_month"])
    assert list(runs.loc[runs["family"] == "A", "fit_last_month"]) == [str(pd.Period("2025-08", freq="M") + i) for i in range(12)]
    assert runs.loc[runs["family"] == "B", "fit_last_month"].iloc[0] == "2025-11"
    for _, r in runs.iterrows():
        g = sim[(sim["family"] == r["family"]) & (sim["run_month"] == r["run_month"])]
        assert g["target_month"].min() == str(pd.Period(r["fit_last_month"], freq="M") + 1)                # the first target is the month after the fit month
    b = sim[sim["family"] == "B"]
    assert b["horizon"].max() == 10 and b["target_month"].max() == "2026-09"                                # beyond the production horizon of 6, passed as a parameter
    assert sim[sim["family"] == "A"]["horizon"].max() == 6


def test_canary_changing_every_value_after_the_fit_month_leaves_that_runs_forecast_unchanged():
    monthly, scope = _fixture()
    base = hc.forecast_run(monthly, scope, "2025-11", 6, WINDOWS)
    bad = monthly.copy()
    after = bad["year_month"] > "2025-11"
    bad.loc[after, "qty"] = bad.loc[after, "qty"] * 9 + 500
    again = hc.forecast_run(bad, scope, "2025-11", 6, WINDOWS)
    assert after.sum() > 0 and base[["f_topdown", "f_naive", "f_ma"]].equals(again[["f_topdown", "f_naive", "f_ma"]])
    changed = bad.copy()                                                                                    # control: a value INSIDE the fit window does move it
    changed.loc[(changed["itemcode"] == "A1") & (changed["year_month"] == "2025-11"), "qty"] += 100
    moved = hc.forecast_run(changed, scope, "2025-11", 6, WINDOWS)
    assert not base[["f_topdown", "f_naive", "f_ma"]].equals(moved[["f_topdown", "f_naive", "f_ma"]])


def test_an_item_with_no_history_before_the_origin_is_counted_and_forecast_zero():
    monthly, scope = _fixture()
    df = hc.forecast_run(monthly, scope, "2025-11", 6, WINDOWS)
    z = df[df["item"] == "Z0"]
    assert (z["history_months_nonzero"] == 0).all() and (z[["f_topdown", "f_naive", "f_ma"]] == 0).all().all()
    assert df.drop_duplicates("item").shape[0] == 6 and (df["f_topdown"] >= 0).all()


def test_the_driver_calls_the_production_functions_and_gives_their_numbers():
    """Not a second model: Top-down and the moving average of the driver are the production functions' output for the same cut series."""
    from forward_test_all_divisions import build_item_series_div, build_type_series_div
    from item_level_reconciliation import forecast_all_approaches
    from models import moving_average_forecast, naive_forecast
    monthly, scope = _fixture()
    cut = hc.cut_series(monthly, "2025-11")
    n = cut["year_month"].nunique()
    items, types = build_item_series_div(cut, scope, n), build_type_series_div(cut, n)
    td = forecast_all_approaches(items, types, n, 6)["Top-down"]
    df = hc.forecast_run(monthly, scope, "2025-11", 6, WINDOWS)
    a1 = df[df["item"] == "A1"].sort_values("horizon")
    assert np.allclose(a1["f_topdown"], td["A1"]) and np.allclose(a1["f_naive"], naive_forecast(items["A1"][0], 6)) and np.allclose(a1["f_ma"], moving_average_forecast(items["A1"][0], 6, 3))


# ------------------------------------------------------------------ the main line, the measures, the config guard
def test_the_main_line_of_a_target_month_is_the_latest_run_dated_before_the_month_and_is_the_third_month_ahead():
    monthly, scope = _fixture()
    sim = hc.simulate(monthly, scope, WINDOWS, MARGIN)
    a = sim[(sim["family"] == "A") & (sim["target_month"] >= "2026-01") & (sim["target_month"] <= "2026-09")]
    m = hc.main_line(a)
    assert sorted(m["horizon"].unique()) == [3]
    for tm, g in m.groupby("target_month"):
        prev_month = str(pd.Period(tm, freq="M") - 1)
        assert (g["run_month"] == prev_month).all() and (pd.to_datetime(g["run_date"]) < pd.Timestamp(tm + "-01")).all()


def test_the_item_level_measures_equal_a_hand_calculation():
    d = pd.DataFrame({"division": ["X"] * 3, "item": ["a", "b", "c"], "actual": [10.0, 20.0, 0.0], "f_topdown": [12.0, 15.0, 1.0], "f_naive": [14.0, 20.0, 4.0], "f_ma": [10.0, 30.0, 0.0],
                      "price": [2.0, 1.0, 5.0]})
    t = hc.item_level_table(d, ["division"]).iloc[0]
    assert t["n_cells"] == 3
    assert t["mae_topdown"] == pytest.approx((2 + 5 + 1) / 3) and t["mae_naive"] == pytest.approx((4 + 0 + 4) / 3) and t["mae_ma"] == pytest.approx((0 + 10 + 0) / 3)
    assert t["relmae_topdown"] == pytest.approx(8 / 8) and t["relmae_ma"] == pytest.approx(10 / 8)                         # sum|model e| / sum|Naive e|
    assert t["bias_topdown"] == pytest.approx((2 - 5 + 1) / 30) and t["bias_naive"] == pytest.approx((4 + 0 + 4) / 30)    # sum(forecast - actual) / sum(actual)
    assert t["mae_baht_topdown"] == pytest.approx((2 * 2 + 5 * 1 + 1 * 5) / 3) and t["relmae_baht_topdown"] == pytest.approx(14 / (8 + 0 + 20))


def test_the_totals_in_baht_use_one_price_for_actual_and_forecast_and_the_company_adds_the_divisions():
    d = pd.DataFrame({"division": ["X", "X", "Y"], "item": ["a", "b", "c"], "target_month": ["2026-03"] * 3, "actual": [10.0, 20.0, 5.0], "f_topdown": [12.0, 15.0, 5.0],
                      "f_naive": [10.0, 10.0, 0.0], "f_ma": [10.0, 20.0, 6.0], "price": [2.0, 1.0, 10.0]})
    t = hc.totals_by_month(d).set_index("division")
    assert t.loc["X", "actual_baht"] == 40.0 and t.loc["X", "f_topdown_baht"] == 39.0 and t.loc["Y", "actual_baht"] == 50.0
    assert t.loc["COMPANY", "actual_baht"] == 90.0 and t.loc["COMPANY", "f_topdown_baht"] == 89.0 and t.loc["COMPANY", "n_items"] == 3
    s = hc.totals_summary(hc.totals_by_month(d)).set_index("division")
    assert s.loc["COMPANY", "bias_topdown"] == pytest.approx(-1 / 90) and s.loc["COMPANY", "n_months"] == 1


def test_the_config_hash_guard_stops_the_run_when_the_file_changed(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("a: 1\n", encoding="utf-8")
    before = hc.sha256_file(str(f))
    assert hc.assert_unchanged(str(f), before) == before
    f.write_text("a: 2\n", encoding="utf-8")
    with pytest.raises(hc.HindcastError, match="changed during the hindcast"):
        hc.assert_unchanged(str(f), before)
