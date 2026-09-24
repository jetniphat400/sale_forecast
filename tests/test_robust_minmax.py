"""METRICS.md Sec.22 (robust_minmax): the deduplication rule and the range_ratio computation.

Uses small synthetic inputs, not the real PEM101 ensemble (that's exercised and cross-checked
separately, in output/summary/phase22_modeler_report.md and phase22_validator_report.md) -- these
tests are deterministic and require no database connection or cached data file.
"""
import pytest

from robust_minmax import compute_range_ratio, dedup_ensemble_members


def _member(r=0.5, s=2.0, review=1, lead=3, wh=("FG01", "FG21")):
    return {"r_months": r, "s_months": s, "review_interval_days": review,
            "lead_time_days": lead, "wh_set": frozenset(wh)}


# --- dedup_ensemble_members --------------------------------------------------------------------

def test_dedup_collapses_identical_params_and_identical_warehouse_set():
    a = _member(wh=("FG01", "FG21"))
    b = _member(wh=("FG21", "FG01"))  # same set, different insertion order
    assert dedup_ensemble_members([a, b]) == [a]


def test_dedup_keeps_members_with_different_warehouse_sets_even_if_params_match():
    a = _member(wh=("FG01", "FG21"))
    b = _member(wh=("FG01", "FG21", "WH21"))  # one extra warehouse -- a genuinely different set
    out = dedup_ensemble_members([a, b])
    assert len(out) == 2


def test_dedup_keeps_members_with_different_parameters_even_if_warehouse_set_matches():
    a = _member(r=0.5)
    b = _member(r=1.0)  # different reorder level, same warehouse set
    out = dedup_ensemble_members([a, b])
    assert len(out) == 2


def test_dedup_empty_input():
    assert dedup_ensemble_members([]) == []


def test_dedup_reproduces_pem101_finding_no_collapse_across_three_definitions():
    # Mirrors this task's own PEM101 finding: current/fg_prefixed_only/all_stockholding resolve
    # to three DIFFERENT warehouse sets, so their passing combinations never collapse even when
    # parameters coincide (see output/summary/phase22_modeler_report.md Part 1).
    current = _member(wh=("FG01", "FG21", "WH21"))
    fg_only = _member(wh=("FG01", "FG21"))
    all_stock = _member(wh=("FG01", "FG21", "WH21", "W4-1"))
    out = dedup_ensemble_members([current, fg_only, all_stock])
    assert len(out) == 3


# --- compute_range_ratio ------------------------------------------------------------------------

def test_range_ratio_basic():
    assert compute_range_ratio([1.0, 2.0, 4.0]) == pytest.approx(4.0)


def test_range_ratio_ignores_zero_values():
    # Min_e = 0 members are excluded from the ratio per METRICS.md Sec.22 ("over members with
    # Min_e > 0") -- a zero must never be treated as the minimum.
    assert compute_range_ratio([0.0, 2.0, 8.0]) == pytest.approx(4.0)


def test_range_ratio_all_zero_returns_none_not_a_fabricated_number():
    assert compute_range_ratio([0.0, 0.0, 0.0]) is None


def test_range_ratio_empty_returns_none():
    assert compute_range_ratio([]) is None


def test_range_ratio_single_positive_value_is_one():
    assert compute_range_ratio([5.0]) == pytest.approx(1.0)


def test_range_ratio_item_independent_scaling_matches_pem101_finding():
    # Min_e = r_months_e * const; the ratio is invariant to the per-item constant -- this is why
    # every PEM101 item got the identical range_ratio (~8.0) in this task's own finding.
    r_months = [0.25, 0.5, 1.0, 1.5, 2.0]
    const_item_a = 30.44 * 12.3
    const_item_b = 30.44 * 0.7
    ratio_a = compute_range_ratio([r * const_item_a for r in r_months])
    ratio_b = compute_range_ratio([r * const_item_b for r in r_months])
    assert ratio_a == pytest.approx(ratio_b)
    assert ratio_a == pytest.approx(max(r_months) / min(r_months))
