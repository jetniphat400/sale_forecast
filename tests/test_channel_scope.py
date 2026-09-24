"""channel_scope (METRICS.md Sec.21, config.yaml channel_scope, added for Q23).

Proves two things CONVENTIONS.md and this task both require:
  1. The default config (channel_scope='omni', or the key absent) produces byte-for-byte the
     same revenue_type filter this project's queries used before channel_scope existed --
     the default pipeline run's SQL, and therefore its results, are unchanged.
  2. channel_scope='omni_tendering' selects both revenue_type values ('Omni Channel' and
     'Tendering'), never just one.

Uses small synthetic config dicts and monkeypatches `run_query` so no database connection is
needed (CONVENTIONS.md / test_data_invariants.py's own convention: deterministic, no live pull).
"""
import pandas as pd
import pytest

import load_data_all_divisions as lda
import load_data_full as ldf
from channel_scope import revenue_type_sql_clause, revenue_types_for_scope


def _config(channel_scope=None):
    cfg = {
        "source_table": "[salewarehouse].[dbo].[cube_Sale_APD]",
        "revenue_type": "Omni Channel",
        "status_basis": ["Actual", "MPS"],
        "date_range": {"start": "2024-01-01"},
    }
    if channel_scope is not None:
        cfg["channel_scope"] = channel_scope
    return cfg


# ---------------------------------------------------------------------------------------------
# Unit-level: the two functions channel_scope.py exposes
# ---------------------------------------------------------------------------------------------

def test_default_omni_scope_is_single_value():
    assert revenue_types_for_scope(_config()) == ["Omni Channel"]
    assert revenue_types_for_scope(_config("omni")) == ["Omni Channel"]


def test_default_omni_clause_matches_original_equality_filter():
    # This is the exact string every query in this project used before channel_scope existed.
    assert revenue_type_sql_clause(_config()) == "revenue_type = 'Omni Channel'"


def test_omni_tendering_selects_both_revenue_types():
    assert revenue_types_for_scope(_config("omni_tendering")) == ["Omni Channel", "Tendering"]
    assert revenue_type_sql_clause(_config("omni_tendering")) == \
        "revenue_type IN ('Omni Channel','Tendering')"


def test_unknown_channel_scope_raises():
    with pytest.raises(ValueError, match="Unknown channel_scope"):
        revenue_types_for_scope(_config("bogus_scope"))


# ---------------------------------------------------------------------------------------------
# Integration-level: the actual SQL built by the pipeline's own pull_raw_sales functions
# ---------------------------------------------------------------------------------------------

_EMPTY_COLUMNS = ["itemcode", "createDate", "forecast_date", "qty", "sale", "status",
                  "division_db_raw", "revenue_type"]


def _empty_df():
    return pd.DataFrame(columns=_EMPTY_COLUMNS)


def test_load_data_full_default_query_is_unchanged(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return _empty_df()

    monkeypatch.setattr(ldf, "run_query", fake_run_query)
    ldf.pull_raw_sales(_config(), ["A"], {"A": "PEM101"})
    assert "revenue_type = 'Omni Channel'" in captured["sql"]
    assert "Tendering" not in captured["sql"]


def test_load_data_full_omni_tendering_query_selects_both(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return _empty_df()

    monkeypatch.setattr(ldf, "run_query", fake_run_query)
    ldf.pull_raw_sales(_config("omni_tendering"), ["A"], {"A": "PEM101"})
    assert "revenue_type IN ('Omni Channel','Tendering')" in captured["sql"]


def test_load_data_all_divisions_default_query_is_unchanged(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return _empty_df()

    monkeypatch.setattr(lda, "run_query", fake_run_query)
    scope = pd.DataFrame({"code": ["A"], "division": ["PEM101"]})
    lda.pull_raw_sales(_config(), scope)
    assert "revenue_type = 'Omni Channel'" in captured["sql"]
    assert "Tendering" not in captured["sql"]


def test_load_data_all_divisions_omni_tendering_query_selects_both(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return _empty_df()

    monkeypatch.setattr(lda, "run_query", fake_run_query)
    scope = pd.DataFrame({"code": ["A"], "division": ["PEM101"]})
    lda.pull_raw_sales(_config("omni_tendering"), scope)
    assert "revenue_type IN ('Omni Channel','Tendering')" in captured["sql"]
