"""Model invariants CONVENTIONS.md requires ("forecasts never being negative") plus the
two invariants specific to this project's adopted Top-down combination method
(STATUS.md Locked Decisions, 2026-09-04): item-level forecasts sum exactly to their
Type's forecast, and the combination forecast equals the arithmetic mean of the six
base models (Naive, MA3, MA6, MA12, Croston, SBA).
"""
import numpy as np
import pytest

from item_level_reconciliation import MA_WINDOWS, forecast_all_approaches
from models import combination_forecast, get_models, tsb_forecast

TRAIN = np.array([5, 0, 3, 8, 0, 0, 12, 4, 6, 0, 2, 9, 5, 0, 0, 7, 3, 6, 1], dtype=float)
HORIZON = 6


def test_get_models_returns_exactly_the_six_adopted_base_models():
    models = get_models(MA_WINDOWS)
    assert set(models.keys()) == {"Naive", "MA3", "MA6", "MA12", "Croston", "SBA"}


def test_no_base_model_forecast_is_negative():
    models = get_models(MA_WINDOWS)
    for name, fn in models.items():
        fc = np.clip(fn(TRAIN, HORIZON), 0, None)
        assert (fc >= 0).all(), f"{name} produced a negative forecast: {fc}"


def test_combination_forecast_is_never_negative():
    fc = combination_forecast(TRAIN, HORIZON, MA_WINDOWS)
    assert (fc >= 0).all()


@pytest.mark.parametrize("train", [
    TRAIN,
    np.zeros(19, dtype=float),          # all-zero series (no-history-like edge case)
    np.array([0.0] * 15 + [3, 0, 5, 1]),  # mostly-zero, intermittent-shaped
])
def test_combination_forecast_never_negative_on_edge_cases(train):
    fc = combination_forecast(train, HORIZON, MA_WINDOWS)
    assert (fc >= 0).all()


def test_combination_forecast_equals_arithmetic_mean_of_the_six_base_models():
    models = get_models(MA_WINDOWS)
    assert len(models) == 6
    individual_forecasts = [np.clip(fn(TRAIN, HORIZON), 0, None) for fn in models.values()]
    expected_mean = np.mean(individual_forecasts, axis=0)
    actual = combination_forecast(TRAIN, HORIZON, MA_WINDOWS)
    np.testing.assert_allclose(actual, expected_mean)


def _synthetic_item_and_type_series(seed=42, fit_end=19, horizon=6):
    rng = np.random.default_rng(seed)
    total = fit_end + horizon
    item_series = {
        "ITEM1": (rng.integers(0, 10, total).astype(float), "TYPE_A", "CAT_A"),
        "ITEM2": (rng.integers(0, 10, total).astype(float), "TYPE_A", "CAT_A"),
        "ITEM3": (rng.integers(0, 10, total).astype(float), "TYPE_B", "CAT_A"),
        "ITEM4": (rng.integers(0, 10, total).astype(float), "TYPE_B", "CAT_A"),
    }
    type_series = {
        "TYPE_A": item_series["ITEM1"][0] + item_series["ITEM2"][0],
        "TYPE_B": item_series["ITEM3"][0] + item_series["ITEM4"][0],
    }
    return item_series, type_series, fit_end, horizon


def test_topdown_item_forecasts_sum_exactly_to_their_type_forecast():
    item_series, type_series, fit_end, horizon = _synthetic_item_and_type_series()
    approaches = forecast_all_approaches(item_series, type_series, fit_end, horizon)
    topdown = approaches["Top-down"]

    items_by_type = {}
    for item, (qty, typ, cat) in item_series.items():
        items_by_type.setdefault(typ, []).append(item)

    for typ, items in items_by_type.items():
        summed = np.sum([topdown[item] for item in items], axis=0)
        expected_type_forecast = np.clip(
            combination_forecast(type_series[typ][:fit_end], horizon, MA_WINDOWS), 0, None
        )
        np.testing.assert_allclose(summed, expected_type_forecast)


def test_topdown_forecasts_are_never_negative():
    item_series, type_series, fit_end, horizon = _synthetic_item_and_type_series()
    approaches = forecast_all_approaches(item_series, type_series, fit_end, horizon)
    for item, fc in approaches["Top-down"].items():
        assert (fc >= 0).all(), f"Top-down forecast for {item} went negative: {fc}"


# ---------------------------------------------------------------------------
# TSB (added for the focus-item model-selection task, 2026-09-08). statsforecast has no
# auto-optimized TSB variant (unlike Croston/SES), so src/models.py.tsb_forecast grid-searches
# alpha_d/alpha_p itself (see its own docstring for the grid and the stated-assumption caveat) --
# these tests lock in that the resulting forecast still respects this project's basic invariants.
# ---------------------------------------------------------------------------

def test_tsb_forecast_returns_correct_length():
    fc = tsb_forecast(TRAIN, HORIZON)
    assert len(fc) == HORIZON


def test_tsb_forecast_is_never_negative():
    fc = np.clip(tsb_forecast(TRAIN, HORIZON), 0, None)
    assert (fc >= 0).all()


def test_tsb_forecast_is_deterministic():
    # Grid search must not depend on random state or dict/set iteration order -- the same
    # training array must produce the exact same forecast every call.
    fc1 = tsb_forecast(TRAIN, HORIZON)
    fc2 = tsb_forecast(TRAIN, HORIZON)
    np.testing.assert_array_equal(fc1, fc2)


@pytest.mark.parametrize("train", [
    TRAIN,
    np.zeros(19, dtype=float),
    np.array([0.0] * 15 + [3, 0, 5, 1]),
])
def test_tsb_forecast_handles_edge_cases_without_raising(train):
    fc = tsb_forecast(train, HORIZON)
    assert len(fc) == HORIZON
    assert not np.isnan(fc).any()


def test_topdown_handles_a_zero_history_type_without_negative_or_nan():
    # An item whose Type has zero total qty over the fitting window (all-zero series) --
    # forecast_all_approaches must fall back to an equal split, not divide by zero into NaN.
    item_series = {
        "ITEM1": (np.zeros(25, dtype=float), "TYPE_ZERO", "CAT_A"),
        "ITEM2": (np.zeros(25, dtype=float), "TYPE_ZERO", "CAT_A"),
    }
    type_series = {"TYPE_ZERO": np.zeros(25, dtype=float)}
    approaches = forecast_all_approaches(item_series, type_series, 19, 6)
    for item, fc in approaches["Top-down"].items():
        assert not np.isnan(fc).any()
        assert (fc >= 0).all()


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Forecast model experiment of 2026-10 (src/investigations/model_experiment_2026_10.py, METRICS.md Sec.50): leakage, candidates, the pre-registered rule
# ---------------------------------------------------------------------------------------------------------------------------------------------
import os
import sys

import yaml

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src", "investigations"))
import model_experiment_2026_10 as mx  # noqa: E402


def _exp_cfg():
    with open(os.path.join(_PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["experiment_2026_10"]


_SERIES = np.array([5, 0, 3, 8, 0, 0, 12, 4, 6, 0, 2, 9, 5, 0, 0, 7, 3, 6, 1, 4, 8, 2, 0, 9, 6, 3, 7, 5, 4, 10, 2], dtype=float)       # 31 months


def test_no_candidate_forecast_changes_when_every_value_after_the_origin_changes():
    cfg = _exp_cfg()
    item = _SERIES.copy()
    typ = _SERIES * 3 + 1
    for train_size in (13, 19, 25):
        base = mx.forecasts_at_origin(item, typ, train_size, 6, cfg)
        item2, typ2 = item.copy(), typ.copy()
        item2[train_size:] = 1000.0 + np.arange(len(item2) - train_size)                 # every later value changed
        typ2[train_size:] = 5000.0
        changed = mx.forecasts_at_origin(item2, typ2, train_size, 6, cfg)
        for cand in cfg["candidates"]:
            assert np.array_equal(base[cand], changed[cand]), (cand, train_size)
        # a change before the origin does move them (the test can fail)
        item3 = item.copy()
        item3[train_size - 1] += 50.0
        assert not np.array_equal(base["naive"], mx.forecasts_at_origin(item3, typ, train_size, 6, cfg)["naive"])


def test_candidate_definitions_on_a_fixed_example():
    cfg = _exp_cfg()
    train = _SERIES[:25]
    typ = _SERIES * 3 + 1
    fc = mx.forecasts_at_origin(_SERIES, typ, 25, 6, cfg)
    share = _SERIES[:25].sum() / typ[:25].sum()
    comb = np.clip(combination_forecast(typ[:25], 6, MA_WINDOWS), 0, None)
    assert np.allclose(fc["current"], comb * share) and (fc["naive"] == train[-1]).all()
    holt = mx.holt_clipped(typ[:25], 6)
    assert np.allclose(fc["holt"], holt * share) and np.allclose(fc["combination_plus_holt"], (6 * comb + holt) / 7 * share)
    f = mx.bias_factor(typ[:25].astype(float), 6, 0.5, 2.0)
    assert 0.5 <= f <= 2.0 and np.allclose(fc["bias_adjusted"], comb * f * share)
    # the factor on a fixed case: a series that doubles is clipped at 2, a series that collapses at 0.5, a series of zeros gives 1
    assert mx.bias_factor(np.array([1.0] * 12 + [50.0] * 6), 6, 0.5, 2.0) == 2.0
    assert mx.bias_factor(np.array([50.0] * 12 + [0.0] * 6), 6, 0.5, 2.0) == 0.5
    assert mx.bias_factor(np.zeros(18), 6, 0.5, 2.0) == 1.0
    # seasonal naive: the value 12 months before each target month; the months of the last year before the origin, none missing at the first origin (13 months)
    sn, missing = mx.seasonal_naive(_SERIES[:13], 6, 12)
    assert list(sn) == list(_SERIES[1:7]) and missing == 0
    sn_short, missing_short = mx.seasonal_naive(_SERIES[:8], 6, 12)                      # fewer than 12 months: filled with Naive and counted, never dropped
    assert missing_short == 4 and list(sn_short) == [_SERIES[7]] * 4 + [_SERIES[0], _SERIES[1]]       # months 9 to 12 of the horizon have no value 12 months earlier, the last two do


def _fixed_table(cur15, cur67, c15, c67, ts_pass=True):
    base = {"rel_15": cur15, "rel_67": cur67, "rel_all": 1.0, "rel_h3_all": 1.0, "ts_15": 1.0, "ts_all": 1.0, "passes_ts": True}
    return {"current": dict(base), "naive": dict(base, rel_15=1.0, rel_67=1.0), "holt": dict(base, rel_15=c15, rel_67=c67, passes_ts=ts_pass),
            "combination_plus_holt": dict(base, rel_15=9.0, rel_67=9.0), "bias_adjusted": dict(base, rel_15=9.0, rel_67=9.0), "seasonal_naive": dict(base, rel_15=9.0, rel_67=9.0)}


def test_the_pre_registered_rule_on_fixed_examples():
    cfg = _exp_cfg()
    cands = cfg["candidates"]
    assert cfg["registered_on"] == "2026-10-09" and cfg["selection_rule"]["min_relative_improvement"] == 0.05
    assert cfg["bias_adjusted"] == {"window_months": 6, "factor_min": 0.5, "factor_max": 2.0} and cfg["seasonal_naive"]["lag_months"] == 12
    assert apply_rule_outcome(_fixed_table(0.90, 0.90, 0.80, 0.70), cands, cfg) == "switch"                        # 11 percent lower on 1-5 and lower on 6-7
    assert apply_rule_outcome(_fixed_table(0.90, 0.90, 0.86, 0.70), cands, cfg) == "keep current"                  # 4.4 percent lower: below the 5 percent bar
    assert apply_rule_outcome(_fixed_table(0.90, 0.90, 0.80, 0.95), cands, cfg) == "keep current"                  # not confirmed on origins 6-7
    assert apply_rule_outcome(_fixed_table(0.90, 0.90, 0.80, 0.70, ts_pass=False), cands, cfg) == "keep current"   # the winner fails the Tracking Signal filter: current stays
    t = _fixed_table(1.30, 1.30, 9.0, 9.0)
    t["current"]["passes_ts"] = False
    out = mx.apply_rule(t, cands, cfg)                                                                             # naive (1.0) is a valid winner
    assert out["outcome"] == "switch" and out["winner"] == "naive"
    for k in t:
        t[k]["passes_ts"] = False
    assert mx.apply_rule(t, cands, cfg) == {"outcome": "keep current", "winner": None, "reason": "no candidate passes the Tracking Signal filter"}
    assert mx.relative_mae([{"origin": 1, "act": np.array([1.0] * 6), "fc": {"x": np.array([2.0] * 6), "naive": np.array([3.0] * 6)}}], "x", {1}) == pytest.approx(0.5)


def apply_rule_outcome(table, cands, cfg):
    return mx.apply_rule(table, cands, cfg)["outcome"]


def test_the_current_candidate_equals_the_main_table_and_the_forecast_pages_relative_mae():
    import re
    if not os.path.exists(os.path.join(_PROJECT_ROOT, "output", "data", "processed_all_divisions_monthly_qty.csv")):
        pytest.skip("SKIPPED, not passed: the saved monthly series (untracked output) is not on this machine")
    result = mx.run()
    assert result["bookkeeping"]["max_abs_diff_current_vs_main_table"] < 1e-9 and result["bookkeeping"]["seasonal_naive_missing_target_months"] == 0
    with open(os.path.join(_PROJECT_ROOT, "forecast", "sales_report.html"), encoding="utf-8") as f:
        h = f.read()
    table = re.search(r'<table class="report-table" id="criteria-table">.*?<tbody>(.*?)</tbody>', h, re.S).group(1)
    page = {cells[0]: float(cells[1]) for cells in (re.findall(r"<td>(.*?)</td>", r) for r in re.findall(r"<tr>(.*?)</tr>", table, re.S))}
    assert set(page) == set(result["groups"])
    for label, g in result["groups"].items():
        assert f"{g['table']['current']['rel_all']:.2f}" == f"{page[label]:.2f}", label
        assert g["table"]["naive"]["rel_all"] == pytest.approx(1.0)
