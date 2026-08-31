"""Forecasting models for the pilot items.

Each model function takes a 1-D training array of monthly quantity and a
forecast horizon, and returns an array of length `horizon`. All models
produce a constant-level forecast repeated across the horizon, which is the
standard approach for these methods on low-volume, intermittent demand.
"""
import numpy as np
from statsforecast.models import CrostonClassic, CrostonSBA


def naive_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    """Repeats the last observed training value for every future period."""
    return np.full(horizon, train[-1], dtype=float)


def moving_average_forecast(train: np.ndarray, horizon: int, window: int) -> np.ndarray:
    """Repeats the average of the last `window` training months for every future period."""
    window = min(window, len(train))
    return np.full(horizon, train[-window:].mean(), dtype=float)


def croston_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    """Croston's classic method (statsforecast), for intermittent demand."""
    result = CrostonClassic().forecast(y=train.astype(float), h=horizon)
    return result["mean"]


def sba_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    """Syntetos-Boylan Approximation — bias-corrected Croston (statsforecast)."""
    result = CrostonSBA().forecast(y=train.astype(float), h=horizon)
    return result["mean"]


def get_models(moving_average_windows: list) -> dict:
    """Returns {model_name: callable(train, horizon) -> forecast_array} for every
    model to test, including one Moving Average variant per configured window."""
    models = {
        "Naive": naive_forecast,
        "Croston": croston_forecast,
        "SBA": sba_forecast,
    }
    for w in moving_average_windows:
        models[f"MA{w}"] = (lambda train, horizon, window=w: moving_average_forecast(train, horizon, window))
    return models
