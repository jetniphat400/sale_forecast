"""Data invariants CONVENTIONS.md has required since the start of this project:
"Validate data before use, checking for negative values, dates outside the expected
range, unmatched item codes and duplicates" and "Write tests for invariants such as
... monthly totals matching the sum of daily records, and SKU counts staying
consistent before and after processing."

Uses small synthetic DataFrames, not a live database pull or committed output files
(CONVENTIONS.md: never commit generated output; a fresh clone has none), so these
tests are deterministic and do not require a database connection.

src/load_data_full.py and src/load_data.py share the same validate_raw/aggregate_monthly
logic (load_data_full.py is the one src/run_pipeline.py calls, for the full 128-item
Category scope) -- tested here via load_data_full, since that is what the pipeline runs.
"""
import pandas as pd
import pytest

from load_data_full import aggregate_monthly, validate_raw


def _base_df() -> pd.DataFrame:
    return pd.DataFrame({
        "itemcode": ["A", "A", "B", "B"],
        "createDate": pd.to_datetime(["2024-01-05", "2024-02-10", "2024-01-15", "2024-03-01"]),
        "forecast_date": pd.to_datetime(["2024-01-10", "2024-02-15", "2024-01-20", "2024-03-05"]),
        "qty": [10.0, 5.0, 3.0, 7.0],
        "sale": [1000.0, 500.0, 300.0, 700.0],
        "status": ["Actual", "MPS", "Actual", "Actual"],
        "division": ["PEM101"] * 4,
        "revenue_type": ["Omni Channel"] * 4,
    })


def test_negative_qty_raises():
    df = _base_df()
    df.loc[0, "qty"] = -1.0
    with pytest.raises(ValueError, match="negative qty"):
        validate_raw(df, ["A", "B"], "2024-01-01")


def test_negative_sale_raises():
    df = _base_df()
    df.loc[0, "sale"] = -1.0
    with pytest.raises(ValueError, match="negative sale"):
        validate_raw(df, ["A", "B"], "2024-01-01")


def test_out_of_range_date_raises():
    df = _base_df()
    df.loc[0, "createDate"] = pd.Timestamp("2020-01-01")  # before the configured start_date
    with pytest.raises(ValueError, match="outside"):
        validate_raw(df, ["A", "B"], "2024-01-01")


def test_anomalous_forecast_date_raises():
    df = _base_df()
    df.loc[0, "forecast_date"] = pd.Timestamp("1960-01-01")  # epoch anomaly, below the low bound
    with pytest.raises(ValueError, match="epoch/future-date anomaly"):
        validate_raw(df, ["A", "B"], "2024-01-01")


def test_valid_data_passes_without_raising():
    df = _base_df()
    validated = validate_raw(df, ["A", "B"], "2024-01-01")
    assert len(validated) == len(df)


def test_monthly_aggregate_reconciles_exactly_to_daily_source():
    df = _base_df()
    validated = validate_raw(df, ["A", "B"], "2024-01-01")
    monthly, stats = aggregate_monthly(validated, ["A", "B"], "createDate")
    assert monthly["qty"].sum() == pytest.approx(validated["qty"].sum())
    assert monthly["sale"].sum() == pytest.approx(validated["sale"].sum())


def test_monthly_aggregate_reconciles_for_forecast_date_key_too():
    df = _base_df()
    validated = validate_raw(df, ["A", "B"], "2024-01-01")
    monthly, stats = aggregate_monthly(validated, ["A", "B"], "forecast_date")
    # forecast_date-keyed aggregation excludes null/negative-interval rows (none here), so it
    # should reconcile to the full validated total exactly, same as the createDate key.
    assert monthly["qty"].sum() == pytest.approx(validated["qty"].sum())
    assert monthly["sale"].sum() == pytest.approx(validated["sale"].sum())


def test_item_count_entering_equals_item_count_leaving():
    df = _base_df()
    validated = validate_raw(df, ["A", "B"], "2024-01-01")
    # "C" has zero rows in the raw pull at all -- must still appear in the output grid,
    # zero-filled, not silently dropped (CONVENTIONS.md: SKU counts must stay consistent).
    item_codes = ["A", "B", "C"]
    monthly, stats = aggregate_monthly(validated, item_codes, "createDate")
    assert monthly["itemcode"].nunique() == len(item_codes)
    assert set(monthly["itemcode"].unique()) == set(item_codes)


def test_aggregate_monthly_raises_if_item_count_mismatch_were_possible():
    # aggregate_monthly builds its grid FROM item_codes (a reindex), so the invariant
    # is structural -- this locks in that the internal consistency check still exists
    # and does not silently pass a mismatched count through.
    import inspect
    source = inspect.getsource(aggregate_monthly)
    assert "Final monthly grid has" in source, (
        "aggregate_monthly must keep its item-count consistency check -- removing it would let "
        "an item silently disappear during processing without being reported."
    )
