"""Tests for src/zero_row_guard.py -- both the raising case (zero rows, no opt-out) and the
explicit opt-out case (zero rows, allow_empty=True is a valid answer)."""
import pandas as pd
import pytest

from zero_row_guard import EmptyQueryResultError, guard_nonempty


def test_raises_on_empty_dataframe_by_default():
    empty = pd.DataFrame(columns=["itemcode", "qty"])
    with pytest.raises(EmptyQueryResultError) as exc_info:
        guard_nonempty(empty, table="cube_final", filter_desc="itemcode IN ('A','B')")
    msg = str(exc_info.value)
    assert "cube_final" in msg
    assert "itemcode IN ('A','B')" in msg


def test_does_not_raise_on_nonempty_dataframe():
    df = pd.DataFrame({"itemcode": ["A", "B"], "qty": [1, 2]})
    result = guard_nonempty(df, table="cube_final", filter_desc="itemcode IN ('A','B')")
    assert result is df


def test_allow_empty_true_does_not_raise_on_empty_dataframe():
    empty = pd.DataFrame(columns=["itemcode", "qty"])
    result = guard_nonempty(empty, table="cube_final", filter_desc="itemcode IN ('A','B')", allow_empty=True)
    assert len(result) == 0


def test_error_message_names_table_filter_and_time():
    empty = pd.DataFrame()
    with pytest.raises(EmptyQueryResultError) as exc_info:
        guard_nonempty(empty, table="Cube_CES", filter_desc="ItemCode IN scope, 2026 window")
    msg = str(exc_info.value)
    assert "Cube_CES" in msg
    assert "2026 window" in msg
    # a timestamp in ISO format (YYYY-MM-DD) should be present, naming "the time"
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", msg)
