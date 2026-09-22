"""METRICS.md Sec.1: unit_cost's basis rows must be 'Omni Channel scope, Actual + MPS status'.

Guards against the confirmed defect (STATUS.md, PEM107 gap root-cause entry, 2026-09-22):
src/phaseE1_common.py::query_sale_cost omitted the revenue_type/status filter entirely, letting
non-Omni-Channel rows (e.g. 'Total Customer Solution', 'Tendering') leak into the trailing-12-month
median used by src/phaseE1_common.py::compute_unit_cost -- root cause of PEM107's 6.34%
Modeler/Validator stock_value gap. These tests fail against the old, unfiltered query and pass
against the corrected one.

The fake `run_query` below simulates what a real SQL server does with the WHERE clause: it applies
the revenue_type/status filter ONLY IF that exact clause text is present in the SQL string passed
to it. This makes the test fail the same way an unfiltered query would actually fail in production
-- a leaked Tendering row -- rather than only checking the SQL string's presence out of context.
"""
import pandas as pd
import pytest

import phaseE1_common as pc

NOW = pd.Timestamp("2026-09-01")


def _fixture() -> pd.DataFrame:
    rows = [
        # Omni Channel, Actual/MPS -- the only rows METRICS.md Sec.1 permits into the median.
        {"itemcode": "TEST-001", "qty": 10, "cost": 100, "createDate": NOW - pd.DateOffset(months=1),
         "revenue_type": "Omni Channel", "status": "Actual"},
        {"itemcode": "TEST-001", "qty": 10, "cost": 200, "createDate": NOW - pd.DateOffset(months=2),
         "revenue_type": "Omni Channel", "status": "Actual"},
        {"itemcode": "TEST-001", "qty": 10, "cost": 300, "createDate": NOW - pd.DateOffset(months=3),
         "revenue_type": "Omni Channel", "status": "MPS"},
        # Tendering row -- must be excluded. Its cost/qty is a deliberately extreme outlier
        # (unit_cost 10,000 vs. 10/20/30) so any leak is unmistakable in the resulting median.
        {"itemcode": "TEST-001", "qty": 10, "cost": 100000, "createDate": NOW - pd.DateOffset(months=1),
         "revenue_type": "Tendering", "status": "Actual"},
    ]
    return pd.DataFrame(rows)


def _fake_run_query(sql: str) -> pd.DataFrame:
    """Simulates server-side WHERE filtering, gated on whether the filter clause text is
    actually present in the SQL -- absent filter clauses mean absent filtering, exactly like a
    real database would behave."""
    df = _fixture()
    if "revenue_type = 'Omni Channel'" in sql:
        df = df[df["revenue_type"] == "Omni Channel"]
    if "status IN ('Actual','MPS')" in sql:
        df = df[df["status"].isin(["Actual", "MPS"])]
    return df[["itemcode", "qty", "cost", "createDate"]].reset_index(drop=True)


def test_query_sale_cost_excludes_non_omni_channel_tendering_row(monkeypatch):
    monkeypatch.setattr(pc, "run_query", _fake_run_query)

    result = pc.query_sale_cost(["TEST-001"])

    assert len(result) == 3, (
        f"query_sale_cost returned {len(result)} rows, expected 3 -- METRICS.md Sec.1 requires "
        f"'Omni Channel scope, Actual + MPS status'; a Tendering row leaked through, meaning the "
        f"revenue_type/status filter is missing from query_sale_cost's SQL.")
    assert 100000 not in result["cost"].values, "the Tendering row's cost leaked into the result"


def test_compute_unit_cost_median_excludes_tendering_row(monkeypatch):
    monkeypatch.setattr(pc, "run_query", _fake_run_query)

    out = pc.compute_unit_cost(["TEST-001"])
    row = out[out["itemcode"] == "TEST-001"].iloc[0]

    assert row["primary_unit_cost"] == pytest.approx(20.0), (
        f"unit_cost = {row['primary_unit_cost']}, expected 20.0 (median of [10, 20, 30] from the "
        f"3 Omni-Channel/Actual+MPS rows). A value near 25.0 means the Tendering row's cost/qty "
        f"(unit_cost 10,000) leaked into the median -- METRICS.md Sec.1's revenue_type/status "
        f"filter is missing from query_sale_cost's SQL.")
