"""Tests for src/score_forward_test_all_divisions.py's consistency check -- the 335-item,
5-division extension of src/score_forward_test_v2.py's verify_consistency, with one added field
(`divisions`) that the single-division v2 log never needed. Same rule as every other guard in
this project: a mismatch must raise loudly (ForwardTestConsistencyError), never warn-and-continue
(CONVENTIONS.md).
"""
import pytest

from forward_test import config_version
from forward_test_common import ForwardTestConsistencyError, compute_scope_hash
from score_forward_test_all_divisions import load_config, verify_consistency

SCOPE_CODES = ["ITEM-A", "ITEM-B", "ITEM-C"]
SCOPE_DIVISIONS = ["PEM101", "PEM101", "PEM102"]


def _matching_metadata(current_config: dict) -> dict:
    return {
        "config_version": config_version(),
        "date_key": current_config["adopted_series_key"],
        "item_level_approach": current_config["adopted_item_level_approach"],
        "scope_hash": compute_scope_hash(SCOPE_CODES),
        "scope_n_items": len(SCOPE_CODES),
        "divisions": sorted(set(SCOPE_DIVISIONS)),
    }


def test_verify_consistency_passes_when_everything_matches_current_state():
    config = load_config()
    metadata = _matching_metadata(config)
    verify_consistency(metadata, config, SCOPE_CODES, SCOPE_DIVISIONS)  # must not raise


def test_verify_consistency_refuses_to_score_on_config_hash_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    metadata["config_version"] = "0" * 12
    with pytest.raises(ForwardTestConsistencyError, match="config_version"):
        verify_consistency(metadata, config, SCOPE_CODES, SCOPE_DIVISIONS)


def test_verify_consistency_refuses_to_score_on_scope_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    with pytest.raises(ForwardTestConsistencyError, match="scope_hash"):
        verify_consistency(metadata, config, SCOPE_CODES + ["ITEM-D"], SCOPE_DIVISIONS + ["PEM103"])


def test_verify_consistency_refuses_to_score_on_approach_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    assert config["adopted_item_level_approach"] != "Direct"
    metadata["item_level_approach"] = "Direct"
    with pytest.raises(ForwardTestConsistencyError, match="item_level_approach"):
        verify_consistency(metadata, config, SCOPE_CODES, SCOPE_DIVISIONS)


def test_verify_consistency_refuses_to_score_on_division_set_mismatch():
    """The new field v2 never had: a log recorded against one set of divisions must not be
    scored once the current scope's division set has changed (e.g. a division added/removed),
    even if every item code and the scope_hash otherwise still matched."""
    config = load_config()
    metadata = _matching_metadata(config)
    metadata["divisions"] = ["PEM101"]  # recorded as PEM101-only; current scope spans PEM101+PEM102
    with pytest.raises(ForwardTestConsistencyError, match="divisions"):
        verify_consistency(metadata, config, SCOPE_CODES, SCOPE_DIVISIONS)


def test_verify_consistency_refuses_to_score_the_archived_128item_log_metadata():
    """Direct regression test for this task's explicit requirement: the 128-item log's own
    recorded metadata (scope_hash/scope_n_items from the OLD 128-item scope, no `divisions` field
    at all) must never pass against the current 335-item, 5-division scope."""
    config = load_config()
    old_128item_metadata = {
        "config_version": config_version(),  # even if this happened to match...
        "date_key": config["adopted_series_key"],
        "item_level_approach": config["adopted_item_level_approach"],
        "scope_hash": "9439fc5dc3f2",  # the archived log's actual recorded 128-item scope_hash
        "scope_n_items": 128,
        "divisions": None,  # the v2 schema never recorded this field at all
    }
    with pytest.raises(ForwardTestConsistencyError):
        verify_consistency(old_128item_metadata, config, SCOPE_CODES, SCOPE_DIVISIONS)
