"""Guards built during Phase B: the leakage guard (src/leakage_guard.py) and the
forward-test consistency check (src/score_forward_test_v2.verify_consistency).
Both must raise loudly on violation, never silently skip or warn-and-continue
(CONVENTIONS.md: "Validation failures must be raised loudly, never silently skipped").
"""
import pytest

from forward_test import config_version
from forward_test_common import ForwardTestConsistencyError, compute_scope_hash
from leakage_guard import LeakageGuardError, check_window_closed, load_min_margin_days
from score_forward_test_v2 import load_config, verify_consistency

SCOPE_CODES = ["ITEM-A", "ITEM-B", "ITEM-C"]


# ---------------------------------------------------------------------------
# Leakage guard
# ---------------------------------------------------------------------------

def test_leakage_guard_raises_when_pull_lands_the_same_day_the_window_closes():
    with pytest.raises(LeakageGuardError):
        check_window_closed("2026-07", "2026-07-31", min_margin_days=30)


def test_leakage_guard_raises_when_margin_is_one_day_short():
    with pytest.raises(LeakageGuardError):
        check_window_closed("2026-07", "2026-08-29", min_margin_days=30)  # gap = 29 days


def test_leakage_guard_error_message_states_window_end_pull_date_and_margins():
    with pytest.raises(LeakageGuardError) as excinfo:
        check_window_closed("2026-07", "2026-07-31", min_margin_days=30)
    message = str(excinfo.value)
    assert "2026-07-31" in message  # window end
    assert "30" in message           # required margin
    assert "0" in message            # actual margin


def test_leakage_guard_passes_when_margin_exactly_meets_the_requirement():
    # Boundary is `actual_gap_days < min_margin_days` -- an exact match must NOT raise.
    check_window_closed("2026-07", "2026-08-30", min_margin_days=30)  # gap = 30 days


def test_leakage_guard_passes_with_a_generous_margin():
    check_window_closed("2026-07", "2026-12-31", min_margin_days=30)


def test_load_min_margin_days_raises_loudly_when_config_section_missing():
    with pytest.raises(KeyError):
        load_min_margin_days({})


def test_load_min_margin_days_reads_the_configured_value():
    assert load_min_margin_days({"leakage_guard": {"min_margin_days": 30}}) == 30


# ---------------------------------------------------------------------------
# Forward-test consistency check
# ---------------------------------------------------------------------------

def _matching_metadata(current_config: dict) -> dict:
    return {
        "config_version": config_version(),
        "date_key": current_config["adopted_series_key"],
        "item_level_approach": current_config["adopted_item_level_approach"],
        "scope_hash": compute_scope_hash(SCOPE_CODES),
        "scope_n_items": len(SCOPE_CODES),
    }


def test_verify_consistency_passes_when_everything_matches_current_state():
    config = load_config()
    metadata = _matching_metadata(config)
    verify_consistency(metadata, config, SCOPE_CODES)  # must not raise


def test_verify_consistency_refuses_to_score_on_config_hash_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    metadata["config_version"] = "0" * 12  # a stale hash, does not match current config.yaml
    with pytest.raises(ForwardTestConsistencyError, match="config_version"):
        verify_consistency(metadata, config, SCOPE_CODES)


def test_verify_consistency_refuses_to_score_on_series_key_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    assert config["adopted_series_key"] != "createDate", (
        "test assumes the adopted series key is not createDate -- update this test if it changes"
    )
    metadata["date_key"] = "createDate"
    with pytest.raises(ForwardTestConsistencyError, match="date_key"):
        verify_consistency(metadata, config, SCOPE_CODES)


def test_verify_consistency_refuses_to_score_on_scope_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    with pytest.raises(ForwardTestConsistencyError, match="scope_hash"):
        verify_consistency(metadata, config, SCOPE_CODES + ["ITEM-D"])  # scope grew, hash now stale


def test_verify_consistency_refuses_to_score_on_approach_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    assert config["adopted_item_level_approach"] != "Direct"
    metadata["item_level_approach"] = "Direct"
    with pytest.raises(ForwardTestConsistencyError, match="item_level_approach"):
        verify_consistency(metadata, config, SCOPE_CODES)
