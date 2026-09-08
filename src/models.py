"""Forecasting models for the pilot items.

Each model function takes a 1-D training array of monthly quantity and a
forecast horizon, and returns an array of length `horizon`. All models
produce a constant-level forecast repeated across the horizon, which is the
standard approach for these methods on low-volume, intermittent demand.
"""
import numpy as np
from statsforecast.models import TSB, CrostonClassic, CrostonSBA, Holt, SimpleExponentialSmoothingOptimized


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


def ses_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    """Simple Exponential Smoothing, alpha optimised (statsforecast). Used for
    non-intermittent (regular) demand per Petropoulos & Kourentzes (2015)."""
    result = SimpleExponentialSmoothingOptimized().forecast(y=train.astype(float), h=horizon)
    return result["mean"]


def holt_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    """Holt's linear trend exponential smoothing (statsforecast). Used for
    non-intermittent demand with a significant trend — none of SBC/KH/PK
    model trend, so this is an explicit addition for that case."""
    result = Holt(season_length=1).forecast(y=train.astype(float), h=horizon)
    return result["mean"]


_TSB_ALPHA_GRID = [0.05, 0.1, 0.2, 0.3, 0.4]  # STATED assumption: statsforecast has no
# "TSBOptimized" class (unlike Croston/SES), so alpha_d/alpha_p must be chosen here. Grid
# search, not a single fixed value, mirroring this project's existing "Optimized" variants
# (CrostonOptimized-style, SimpleExponentialSmoothingOptimized): fit every (alpha_d, alpha_p)
# pair in the grid on the training window only (no test-set leakage), score each by one-step
# in-sample squared error via statsforecast's own fitted values, and keep the best pair. The
# grid itself (5x5=25 combinations) is a stated choice, not derived from this project's data —
# it spans the range TSB's own literature (Teunter, Syntetos & Babai 2011) commonly explores.


def tsb_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    """Teunter-Syntetos-Babai method (statsforecast TSB) — separately smooths demand
    probability and demand size, addressing Croston/SBA's known inability to let a forecast
    decay toward zero once demand has genuinely stopped (relevant for items that go fully quiet
    for a stretch and later resume, e.g. a collapse-then-recovery pattern). alpha_d/alpha_p
    chosen by grid search (see _TSB_ALPHA_GRID) minimizing in-sample fitted error on the
    training window itself, not the test window."""
    train = train.astype(float)
    best_alpha, best_err = None, np.inf
    for alpha_d in _TSB_ALPHA_GRID:
        for alpha_p in _TSB_ALPHA_GRID:
            try:
                fitted = TSB(alpha_d=alpha_d, alpha_p=alpha_p).fit(y=train)
                in_sample = fitted.predict_in_sample()["fitted"]
                err = np.nanmean((train - in_sample) ** 2)
            except Exception:
                continue
            if np.isfinite(err) and err < best_err:
                best_err, best_alpha = err, (alpha_d, alpha_p)
    if best_alpha is None:
        raise ValueError("TSB grid search failed to fit any (alpha_d, alpha_p) pair on this training series.")
    result = TSB(alpha_d=best_alpha[0], alpha_p=best_alpha[1]).forecast(y=train, h=horizon)
    return result["mean"]


def combination_forecast(train: np.ndarray, horizon: int, moving_average_windows: list) -> np.ndarray:
    """Simple (equal-weight) average of every candidate model's forecast —
    Naive, MA variants, Croston, SBA. Per Petropoulos & Kourentzes (2015) and
    the wider combination-forecasting literature, averaging is preferable
    when no single model is clearly and consistently best and candidates are
    reasonably robust/diverse — exactly the situation found in this project's
    prior rolling-origin results (no stable winner at any level)."""
    candidates = get_models(moving_average_windows)
    forecasts = []
    for name, fn in candidates.items():
        try:
            fc = np.clip(fn(train, horizon), 0, None)
            forecasts.append(fc)
        except Exception:
            continue
    return np.mean(forecasts, axis=0)


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


def get_extended_models(moving_average_windows: list) -> dict:
    """Adds SES and Holt to the base candidate set — needed for the
    rule-based selection's non-intermittent layer (Part 3) and for the
    combination forecast, which averages every candidate including these."""
    models = get_models(moving_average_windows)
    models["SES"] = ses_forecast
    models["Holt"] = holt_forecast
    return models
