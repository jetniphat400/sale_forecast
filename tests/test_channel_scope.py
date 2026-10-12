"""The revenue_type filter (src/channel_scope.py). After Prompt 27 (2026-10-12) the pilot scope is Price List items
under the Omni Channel filter only: the 'omni_tendering' option and the config key channel_scope are removed.

Proves that the filter is byte-for-byte the one this project's queries always used, in the helper and in the SQL of the
pipeline's own pull_raw_sales functions, and that the option and the key are gone.

Uses small synthetic config dicts and monkeypatches `run_query` so no database connection is
needed (CONVENTIONS.md / test_data_invariants.py's own convention: deterministic, no live pull).
"""
import os

import pandas as pd
import load_data_all_divisions as lda
import load_data_full as ldf
from channel_scope import revenue_type_sql_clause, revenue_types_for_scope


def _config():
    cfg = {
        "source_table": "[salewarehouse].[dbo].[cube_Sale_APD]",
        "revenue_type": "Omni Channel",
        "status_basis": ["Actual", "MPS"],
        "date_range": {"start": "2024-01-01"},
    }
    return cfg


# ---------------------------------------------------------------------------------------------
# Unit-level: the two functions channel_scope.py exposes
# ---------------------------------------------------------------------------------------------

def test_default_omni_scope_is_single_value():
    assert revenue_types_for_scope(_config()) == ["Omni Channel"]


def test_default_omni_clause_matches_original_equality_filter():
    # This is the exact string every query in this project used before channel_scope existed.
    assert revenue_type_sql_clause(_config()) == "revenue_type = 'Omni Channel'"


def test_the_tendering_option_and_the_channel_scope_key_are_gone():
    import inspect
    import yaml
    import channel_scope
    cfg = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml"), encoding="utf-8"))
    assert "channel_scope" not in cfg
    assert "Tendering" not in inspect.getsource(channel_scope).split('"""', 2)[2]
    assert revenue_types_for_scope(cfg) == [cfg["revenue_type"]] == ["Omni Channel"]


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
