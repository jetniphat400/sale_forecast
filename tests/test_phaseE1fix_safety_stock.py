"""METRICS.md Sec.4: safety_stock = percentile(ltd_distribution, sl) - LTD, floored at 0.

Guards against the confirmed Phase E1-fix code defect (STATUS.md, Phase E1-fix Part 2):
src/phaseE1fix_recompute.py used to subtract the empirical distribution's own mean
(`cum.mean()`) instead of LTD (the forecast-based point estimate, METRICS.md Sec.3). The two
differ whenever the forecast and the historical average disagree, which the fixtures below are
deliberately built to exercise -- these tests fail under the old `percentile - mean` formula and
pass under the corrected `percentile - LTD` formula.
"""
import numpy as np
import pytest

from phaseE1fix_recompute import compute_safety_stock

# Six non-zero windows -> not flagged unreliable. mean = 41.6667, distinct from every LTD tested
# below, so a percentile-minus-mean regression is caught rather than accidentally matching.
CUM = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 100.0])
SL = 0.95
PCT_95 = float(np.percentile(CUM, 95))  # 87.5
MEAN = float(CUM.mean())  # 41.666...


def test_safety_stock_subtracts_ltd_not_distribution_mean():
    ltd = 15.0  # deliberately far from MEAN (41.67) so the two formulas diverge clearly
    pct_value, safety_stock = compute_safety_stock(CUM, ltd, SL)

    assert pct_value == pytest.approx(PCT_95)
    assert safety_stock == pytest.approx(PCT_95 - ltd)
    # Regression guard: the old bug computed percentile - mean. Assert we are NOT that value.
    old_buggy_value = PCT_95 - MEAN
    assert safety_stock != pytest.approx(old_buggy_value), (
        f"safety_stock ({safety_stock}) matches the OLD buggy formula (percentile - mean = "
        f"{old_buggy_value}) instead of METRICS.md Sec.4's percentile - LTD ({PCT_95 - ltd})")


def test_safety_stock_formula_differs_from_mean_based_formula_when_ltd_and_mean_diverge():
    # LTD far above the distribution mean -> mean-based (buggy) formula would give a LARGER
    # safety_stock than the LTD-based (correct) one; assert the correct, smaller value.
    ltd = 90.0
    _, safety_stock = compute_safety_stock(CUM, ltd, SL)
    assert safety_stock == pytest.approx(max(0.0, PCT_95 - ltd))
    assert safety_stock < (PCT_95 - MEAN)


def test_safety_stock_floored_at_zero():
    ltd = 500.0  # far above the 95th percentile of CUM
    pct_value, safety_stock = compute_safety_stock(CUM, ltd, SL)
    assert pct_value == pytest.approx(PCT_95)
    assert safety_stock == 0.0
