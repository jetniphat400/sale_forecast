"""Tests for the two new invariants added by the 2026-09-04 "Division source-of-truth correction"
(STATUS.md Locked Decisions): (1) no item code may appear on more than one visible pricelist
sheet — it would be counted under two divisions; (2) no confirmed duplicate may exist between an
-OLD-tagged row and a normally-tagged row for the same order.

Uses small synthetic DataFrames, not a live database pull or the real pricelist file (CONVENTIONS.md:
never commit generated output or data files; a fresh clone has neither reference/pricelist.xlsx nor
a database connection), so these tests are deterministic and require no external dependency.
"""
import pandas as pd
import pytest

from division_utils import assert_no_code_on_multiple_sheets, classify_old_tag_duplicates


# ---------------------------------------------------------------------------
# Invariant 1: no item code on more than one visible sheet
# ---------------------------------------------------------------------------

def test_code_on_two_different_sheets_raises():
    pricelist_df = pd.DataFrame({
        "sheet": ["PEM101-Version 2", "PEM102-Version 2"],
        "code": ["X-001", "X-001"],
    })
    with pytest.raises(ValueError, match="more than one visible sheet"):
        assert_no_code_on_multiple_sheets(pricelist_df)


def test_unique_codes_across_sheets_does_not_raise():
    pricelist_df = pd.DataFrame({
        "sheet": ["PEM101-Version 2", "PEM102-Version 2", "CI101"],
        "code": ["X-001", "X-002", "X-003"],
    })
    assert_no_code_on_multiple_sheets(pricelist_df)  # should not raise


def test_duplicate_row_within_the_same_sheet_does_not_raise():
    # Mirrors the already-known DS-F-99-0308 case on the CI101 sheet: the same code appears
    # twice as separate ROWS, but on the SAME sheet -- not a cross-division double count.
    pricelist_df = pd.DataFrame({
        "sheet": ["CI101", "CI101", "PEM101-Version 2"],
        "code": ["DS-F-99-0308", "DS-F-99-0308", "X-001"],
    })
    assert_no_code_on_multiple_sheets(pricelist_df)  # should not raise


# ---------------------------------------------------------------------------
# Invariant 2: no confirmed duplicate between an -OLD-tagged row and a normal-tagged row
# ---------------------------------------------------------------------------

def _row(contractid, itemcode, division_db_raw, qty, sale, forecast_date):
    return {"contractid": contractid, "itemcode": itemcode, "division_db_raw": division_db_raw,
            "qty": qty, "sale": sale, "forecast_date": pd.Timestamp(forecast_date)}


def test_exact_match_across_old_and_normal_tag_is_confirmed_duplicate():
    df = pd.DataFrame([
        _row("CTR-001", "ITEM-A", "PEM107", 10.0, 1000.0, "2024-06-01"),
        _row("CTR-001", "ITEM-A", "PEM102-OLD", 10.0, 1000.0, "2024-06-01"),  # identical -> duplicate
    ])
    result = classify_old_tag_duplicates(df)
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "CONFIRMED_DUPLICATE"


def test_differing_forecast_date_is_not_a_duplicate():
    # Same qty and sale, but a different forecast_date -- a genuine separate delivery tranche,
    # not the same order recorded twice (this project's established split-lot signal).
    df = pd.DataFrame([
        _row("CTR-002", "ITEM-B", "PEM107", 5.0, 500.0, "2024-11-29"),
        _row("CTR-002", "ITEM-B", "PEM102-OLD", 5.0, 500.0, "2024-12-06"),
    ])
    result = classify_old_tag_duplicates(df)
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "distinct_order_or_instalment"


def test_differing_qty_is_not_a_duplicate():
    df = pd.DataFrame([
        _row("CTR-003", "ITEM-C", "PEM107", 40.0, 486000.0, "2025-01-30"),
        _row("CTR-003", "ITEM-C", "PEM102-OLD", 100.0, 1215000.0, "2024-08-15"),
    ])
    result = classify_old_tag_duplicates(df)
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "distinct_order_or_instalment"


def test_no_old_tagged_rows_returns_empty_without_raising():
    df = pd.DataFrame([
        _row("CTR-004", "ITEM-D", "PEM107", 1.0, 100.0, "2024-01-01"),
        _row("CTR-004", "ITEM-D", "PEM102", 2.0, 200.0, "2024-02-01"),
    ])
    result = classify_old_tag_duplicates(df)
    assert len(result) == 0


def test_missing_required_column_raises():
    df = pd.DataFrame([{"contractid": "CTR-005", "itemcode": "ITEM-E"}])
    with pytest.raises(ValueError, match="missing required column"):
        classify_old_tag_duplicates(df)


def test_no_confirmed_duplicates_invariant_end_to_end():
    """This project's actual finding (2026-09-04 full-scope re-validation): 11 candidate pairs
    were found in the live data, 0 were confirmed duplicates. This test locks in that the
    classifier itself would correctly flag a duplicate if one existed, using a realistic mixed
    batch (some genuine near-misses, one deliberately planted exact-match duplicate)."""
    df = pd.DataFrame([
        _row("CTR-010", "ITEM-X", "PEM107", 3.0, 39300.0, "2025-01-31"),
        _row("CTR-010", "ITEM-X", "PEM102-OLD", 3.0, 39300.0, "2024-11-15"),  # distinct (date differs)
        _row("CTR-011", "ITEM-Y", "PEM102", 1.0, 268000.0, "2025-01-31"),
        _row("CTR-011", "ITEM-Y", "PEM107-OLD", 1.0, 268000.0, "2025-01-31"),  # planted: exact match
    ])
    result = classify_old_tag_duplicates(df)
    assert len(result) == 2
    confirmed = result[result["classification"] == "CONFIRMED_DUPLICATE"]
    assert len(confirmed) == 1
    assert confirmed.iloc[0]["contractid"] == "CTR-011"
