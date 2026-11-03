"""The daily rebuild's months gate checks the plan's months against what they must be (the latest vintage's target months from the current month onward), not against the previous build (Prompt 66, item 3)."""
import os
import sys
from datetime import datetime

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import daily_rebuild as dr  # noqa: E402
import operation_plan as op  # noqa: E402

VINTAGE_MONTHS = ["2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]


def _om(months, items=445):
    return {"months": months, "counts": {"items": items}}


@pytest.fixture
def vintage(monkeypatch):
    monkeypatch.setattr(op, "latest_vintage_forecast", lambda root, cfg: (None, 2, list(VINTAGE_MONTHS), True))


def _check(om, snap_items, day):
    return dr.months_and_items_check("root", {}, om, snap_items, now=datetime(2026, *day))


def test_a_month_roll_passes_the_plan_now_starts_at_the_new_month(vintage):
    ok, _ = _check(_om(["2026-11", "2026-12", "2027-01", "2027-02"]), 445, (11, 2))          # the snapshot of the day before had October; the new plan is right
    assert ok


def test_the_same_months_in_the_same_month_pass(vintage):
    assert _check(_om(["2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]), 445, (10, 30))[0]


def test_wrong_months_fail_even_when_they_equal_the_previous_build(vintage):
    ok, detail = _check(_om(["2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]), 445, (11, 2))        # a stale plan: October kept although the month is November
    assert not ok and "expected ['2026-11'" in detail
    assert not _check(_om(["2026-11", "2026-12", "2027-01"]), 445, (11, 2))[0]                              # a month missing
    assert not _check(_om(["2026-12", "2027-01", "2027-02"]), 445, (11, 2))[0]                              # the plan starts too late


def test_the_item_count_is_still_compared_with_the_previous_build(vintage):
    months = ["2026-11", "2026-12", "2027-01", "2027-02"]
    assert not _check(_om(months, 444), 445, (11, 2))[0]
    assert _check(_om(months, 445), 445, (11, 2))[0]


def test_a_new_vintage_with_new_months_is_followed_without_a_hold(monkeypatch):
    monkeypatch.setattr(op, "latest_vintage_forecast", lambda root, cfg: (None, 3, ["2026-11", "2026-12", "2027-01", "2027-02", "2027-03"], True))
    assert _check(_om(["2026-11", "2026-12", "2027-01", "2027-02", "2027-03"]), 445, (11, 5))[0]


def test_the_gate_in_check_gates_uses_the_helper_and_no_longer_reads_the_snapshot_months():
    src = open(os.path.join(PROJECT_ROOT, "src", "daily_rebuild.py"), encoding="utf-8").read()
    body = src.split("def check_gates")[1].split("def monthly_built_log")[0]
    assert "months_and_items_check(" in body and 'snap["months"]' not in body
