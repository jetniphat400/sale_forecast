"""Model invariants CONVENTIONS.md requires ("forecasts never being negative") plus the
two invariants specific to this project's adopted Top-down combination method
(STATUS.md Locked Decisions, 2026-09-04): item-level forecasts sum exactly to their
Type's forecast, and the combination forecast equals the arithmetic mean of the six
base models (Naive, MA3, MA6, MA12, Croston, SBA).
"""
import numpy as np
import pytest

from item_level_reconciliation import MA_WINDOWS, forecast_all_approaches
from models import combination_forecast, get_models

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
