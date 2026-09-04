"""Computes the statistical characteristics used to drive rule-based model
selection (Part 1) and to test their stability across windows (Part 2).

Methodology notes (stated explicitly, not hidden in code):
  - ADI, CV-squared: standard definitions (Syntetos, Boylan & Croston 2005).
  - Trend: OLS slope of qty against a 0..n-1 time index (scipy.stats.linregress).
    Direction = sign of the slope; "significant" = the slope's p-value < 0.05
    AND the total fitted change over the series (slope * (n-1)) exceeds 20% of
    the series mean — a magnitude filter added because a statistically
    significant but tiny slope is not practically a "trend" for inventory
    purposes. This magnitude threshold is our own choice, not from a
    published source, and is reported as such.
  - Level shift: a simple, explicitly-labelled heuristic, not a formal
    structural-break test. For every candidate split point with at least 6
    periods on each side, compute Welch's t-statistic between the pre- and
    post-split segments; the split with the largest |t| is the candidate
    shift point. Flagged as a shift only if |t| > 3 (roughly p<0.01) AND the
    ratio of post/pre segment means differs by more than 50%. This is a
    heuristic screening tool, not a validated changepoint test.
  - Month-of-year strength: ratio of between-month-of-year variance to
    total variance (an eta-squared-like statistic) computed on de-trended
    residuals. Reported as an OBSERVATION ONLY per instruction — with at
    most 2 complete years of data this cannot confirm seasonality.
"""
import logging

import numpy as np
from scipy import stats

logger = logging.getLogger("series_features")

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49

TREND_PVALUE_THRESHOLD = 0.05
TREND_MAGNITUDE_THRESHOLD = 0.20  # fitted total change must exceed 20% of series mean

LEVEL_SHIFT_MIN_SEGMENT = 6
LEVEL_SHIFT_T_THRESHOLD = 3.0
LEVEL_SHIFT_RATIO_THRESHOLD = 0.50


def classify_demand(qty: np.ndarray) -> tuple:
    """Returns (classification, ADI, CV2) using SBC (2005) thresholds."""
    n = len(qty)
    nonzero = qty[qty > 0]
    if len(nonzero) == 0:
        return "NoSale", None, None
    adi = n / len(nonzero)
    mean_d = nonzero.mean()
    std_d = nonzero.std(ddof=1) if len(nonzero) > 1 else 0.0
    cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        cls = "Smooth"
    elif adi < ADI_THRESHOLD:
        cls = "Erratic"
    elif cv2 < CV2_THRESHOLD:
        cls = "Intermittent"
    else:
        cls = "Lumpy"
    return cls, adi, cv2


def compute_trend(qty: np.ndarray) -> dict:
    """OLS trend on the raw series. Returns direction, slope, R^2, p-value,
    and a boolean 'significant' flag per the magnitude+significance rule
    documented in the module docstring."""
    n = len(qty)
    if n < 4:
        return {"trend_direction": "Too short", "trend_slope": None, "trend_r2": None,
                "trend_pvalue": None, "trend_significant": False}
    x = np.arange(n)
    reg = stats.linregress(x, qty)
    mean_level = qty.mean()
    total_fitted_change = reg.slope * (n - 1)
    magnitude_ok = abs(total_fitted_change) > TREND_MAGNITUDE_THRESHOLD * mean_level if mean_level > 0 else False
    significant = (reg.pvalue < TREND_PVALUE_THRESHOLD) and magnitude_ok
    if not significant:
        direction = "Flat / no significant trend"
    elif reg.slope > 0:
        direction = "Increasing"
    else:
        direction = "Decreasing"
    return {
        "trend_direction": direction, "trend_slope": round(float(reg.slope), 4),
        "trend_r2": round(float(reg.rvalue ** 2), 4), "trend_pvalue": round(float(reg.pvalue), 4),
        "trend_significant": bool(significant),
    }


def detect_level_shift(qty: np.ndarray) -> dict:
    """Heuristic single-changepoint screen (see module docstring). NOT a
    formal structural-break test."""
    n = len(qty)
    if n < 2 * LEVEL_SHIFT_MIN_SEGMENT:
        return {"level_shift_detected": False, "level_shift_period": None,
                "level_shift_t": None, "level_shift_ratio": None,
                "level_shift_note": f"series too short ({n} periods) to test (needs >= {2*LEVEL_SHIFT_MIN_SEGMENT})"}
    best_t, best_split, best_ratio = 0.0, None, None
    for split in range(LEVEL_SHIFT_MIN_SEGMENT, n - LEVEL_SHIFT_MIN_SEGMENT + 1):
        pre, post = qty[:split], qty[split:]
        if pre.std(ddof=1) == 0 and post.std(ddof=1) == 0:
            continue
        t_stat, _ = stats.ttest_ind(post, pre, equal_var=False)
        if np.isnan(t_stat):
            continue
        if abs(t_stat) > abs(best_t):
            best_t = t_stat
            best_split = split
            pre_mean = pre.mean()
            best_ratio = (post.mean() - pre_mean) / pre_mean if pre_mean else None
    detected = best_split is not None and abs(best_t) > LEVEL_SHIFT_T_THRESHOLD and best_ratio is not None and abs(best_ratio) > LEVEL_SHIFT_RATIO_THRESHOLD
    return {
        "level_shift_detected": bool(detected), "level_shift_period": int(best_split) if detected else None,
        "level_shift_t": round(float(best_t), 2) if best_split is not None else None,
        "level_shift_ratio": round(float(best_ratio), 3) if best_ratio is not None else None,
        "level_shift_note": "heuristic screen (Welch's t, |t|>3 and >50% mean change), not a formal changepoint test",
    }


def compute_month_of_year_strength(qty: np.ndarray, months: list) -> dict:
    """Eta-squared-like ratio of between-month-of-year variance to total
    variance on de-trended residuals. OBSERVATION ONLY (see module docstring)
    — cannot confirm seasonality with <=2 complete years."""
    n = len(qty)
    if n < 12:
        return {"month_of_year_strength": None, "month_of_year_note": "series too short (<12 periods) to assess"}
    x = np.arange(n)
    reg = stats.linregress(x, qty)
    residuals = qty - (reg.intercept + reg.slope * x)
    month_nums = np.array([int(m.split("-")[1]) for m in months])
    total_var = residuals.var(ddof=0)
    if total_var == 0:
        return {"month_of_year_strength": 0.0, "month_of_year_note": "flat series, no variance to attribute"}
    group_means = {m: residuals[month_nums == m].mean() for m in range(1, 13) if (month_nums == m).any()}
    overall_mean = residuals.mean()
    # Eta-squared: SS_between / SS_total
    ss_total = np.sum((residuals - overall_mean) ** 2)
    ss_between = sum(
        residuals[month_nums == m].size * (group_means[m] - overall_mean) ** 2 for m in group_means
    )
    eta2 = ss_between / ss_total if ss_total > 0 else 0.0
    n_years = len(set(m.split("-")[0] for m in months))
    return {
        "month_of_year_strength": round(float(eta2), 3),
        "month_of_year_note": f"observation only ({n_years} distinct years in window, <=2 complete — cannot confirm a real seasonal pattern)",
    }


def compute_all_features(qty: np.ndarray, months: list) -> dict:
    """Full feature set for one series (Part 1). `months` are 'YYYY-MM' strings
    parallel to `qty`, chronologically sorted."""
    n = len(qty)
    n_zero = int((qty == 0).sum())
    cls, adi, cv2 = classify_demand(qty)
    trend = compute_trend(qty)
    shift = detect_level_shift(qty)
    seasonal = compute_month_of_year_strength(qty, months)
    features = {
        "n_periods": n, "n_zero_periods": n_zero, "n_nonzero_periods": n - n_zero,
        "pct_zero": round(100 * n_zero / n, 1) if n else None,
        "ADI": round(adi, 3) if adi is not None else None,
        "CV2": round(cv2, 3) if cv2 is not None else None,
        "classification": cls,
    }
    features.update(trend)
    features.update(shift)
    features.update(seasonal)
    return features
