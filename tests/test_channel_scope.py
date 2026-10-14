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


# ---------------------------------------------------------------- Prompt 29 (row 20): has_any_history counts Omni Channel rows only, by channel, keeping every year
def test_the_has_any_history_pull_is_limited_to_the_omni_channel_and_adds_no_date_filter(monkeypatch):
    captured = []
    monkeypatch.setattr(ldf, "run_query", lambda sql: captured.append(sql) or pd.DataFrame({"itemcode": ["A"]}))
    monkeypatch.setattr(ldf, "load_visible_product_rows", lambda path: pd.DataFrame({"code": ["A", "B"], "category": [ldf.CATEGORIES[0]] * 2, "type": ["t", "t"], "sheet": ["PEM101-Version 2"] * 2}))
    cfg = _config()
    cfg.update({"pricelist_path": "reference/pricelist.xlsx", "sheet_to_division": {"PEM101-Version 2": "PEM101"}})
    scope = ldf.get_category_scope(cfg)
    sql = captured[0]
    assert "revenue_type = 'Omni Channel'" in sql and "SELECT DISTINCT itemcode" in sql
    assert "createDate" not in sql and "status" not in sql.lower().replace("select distinct", "")       # years and statuses are kept: no date and no status condition
    assert scope.set_index("code")["has_any_history"].to_dict() == {"A": True, "B": False}


def test_the_monthly_run_reports_the_codes_that_lost_or_gained_their_history(caplog):
    import logging
    import monthly_refresh as mr
    with caplog.at_level(logging.INFO, logger="monthly_refresh"):
        out = mr._report_history_flips({"A": True, "B": True, "C": False, "D": True}, {"A": True, "B": False, "C": True, "D": True})
    assert out == {"lost_history": ["B"], "gained_history": ["C"], "n_codes": 4}
    assert "1 code(s) lost their history: B; 1 gained it: C" in caplog.text
    assert mr._report_history_flips({}, {"A": True})["lost_history"] == []                              # no earlier file: nothing flips
