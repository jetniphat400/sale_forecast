"""Regression test for DATA_MAP.md Trap 18 (fixed 2026-09-25): a Cube_CES pull that added a
`CtrDate >= '2023-01-01'` filter, silently dropping legitimate rows and producing an
unrecognizable `not_late` figure. This test fails against that old filter and passes against the
fixed shared helper (`src/cube_ces_pull.py`), which must never add any date condition at pull time.
"""
import os

import pandas as pd
import pytest

import cube_ces_pull
from zero_row_guard import EmptyQueryResultError


def test_pull_cube_ces_for_items_has_no_date_filter(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return pd.DataFrame(columns=cube_ces_pull.CUBE_CES_COLUMNS)

    monkeypatch.setattr(cube_ces_pull, "run_query", fake_run_query)
    cube_ces_pull.pull_cube_ces_for_items(["A", "B"], allow_empty=True)

    sql = captured["sql"]
    assert "ItemCode IN" in sql
    where_clause = sql.upper().split("WHERE", 1)[1]
    # The bug this test guards against: any CtrDate (or other date-column) comparison in WHERE.
    assert "CTRDATE" not in where_clause, (
        "pull_cube_ces_for_items must not filter on CtrDate (or any date column) at the SQL "
        "level -- DATA_MAP.md Trap 18. Any date window belongs in Python, applied against "
        "whichever field the analysis needs (ForecastDelDate for not_late, METRICS.md Sec.18/19/20)."
    )
    assert ">=" not in where_clause and "<=" not in where_clause
    assert " < " not in where_clause and " > " not in where_clause


def test_pull_cube_ces_for_items_scopes_by_itemcode_only(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return pd.DataFrame(columns=cube_ces_pull.CUBE_CES_COLUMNS)

    monkeypatch.setattr(cube_ces_pull, "run_query", fake_run_query)
    cube_ces_pull.pull_cube_ces_for_items(["X-1", "X-2", "X-3"], allow_empty=True)

    sql = captured["sql"]
    assert "'X-1'" in sql and "'X-2'" in sql and "'X-3'" in sql
    assert sql.strip().upper().count("WHERE") == 1


def test_pull_cube_ces_raises_on_zero_rows_by_default(monkeypatch):
    """This task's Part 0 zero-row guard: a zero-row Cube_CES pull must fail loudly."""
    def fake_run_query(sql):
        return pd.DataFrame(columns=cube_ces_pull.CUBE_CES_COLUMNS)

    monkeypatch.setattr(cube_ces_pull, "run_query", fake_run_query)
    with pytest.raises(EmptyQueryResultError):
        cube_ces_pull.pull_cube_ces_for_items(["A", "B"])


def test_pull_cube_ces_allow_empty_true_does_not_raise(monkeypatch):
    """The explicit opt-out: a caller that knows zero rows is a valid answer must be able to say
    so, without the guard firing."""
    def fake_run_query(sql):
        return pd.DataFrame(columns=cube_ces_pull.CUBE_CES_COLUMNS)

    monkeypatch.setattr(cube_ces_pull, "run_query", fake_run_query)
    result = cube_ces_pull.pull_cube_ces_for_items(["A", "B"], allow_empty=True)
    assert len(result) == 0


# ---------------------------------------------------------------- Prompt 28: the Omni Channel filter of the three Cube_CES paths (rows 8, 9, 21)
def test_the_class_signal_pull_adds_the_omni_channel_filter_when_asked_and_never_a_date_filter(monkeypatch):
    captured = {}
    monkeypatch.setattr(cube_ces_pull, "run_query", lambda sql: captured.setdefault("sql", sql) and pd.DataFrame(columns=cube_ces_pull.CUBE_CES_COLUMNS))
    cube_ces_pull.pull_cube_ces_for_items(["A"], allow_empty=True, revenue_type="Omni Channel")
    assert "AND RevenueType = 'Omni Channel'" in captured["sql"] and "ForecastDelDate" not in captured["sql"].split("WHERE")[1] and "CtrDate" not in captured["sql"].split("WHERE")[1]
    captured.clear()
    cube_ces_pull.pull_cube_ces_for_items(["A"], allow_empty=True)
    assert "RevenueType =" not in captured["sql"]                                   # the investigations' default pull is unchanged


def test_the_class_evidence_pull_takes_omni_rows_of_every_status_and_the_backlog_rows_of_every_channel(monkeypatch):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "investigations"))
    import task2b_part2_fulfilment_segmentation as seg
    sqls = []
    import db
    monkeypatch.setattr(db, "run_query", lambda sql: sqls.append(sql) or pd.DataFrame())
    monkeypatch.setattr(seg, "load_week3_config", lambda: {"analysis_window_start": "2024-01-01"})
    seg.pull_class_evidence(["A"])
    ces = [s for s in sqls if "FROM Cube_CES" in s]
    assert len(ces) == 1 and "AND (RevenueType = 'Omni Channel' OR Status = 'Backlog')" in ces[0]
    assert all("revenue_type = 'Omni Channel'" in s for s in sqls if "cube_Sale_APD" in s)


def test_the_class_signals_read_only_the_omni_rows_and_a_frame_without_the_column_is_refused():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "investigations"))
    import task2b_part2_fulfilment_segmentation as seg
    ces = pd.DataFrame({"ItemCode": ["A", "A", "B", "B"], "Status": ["Actual", "Actual", "Backlog", "Actual"], "RevenueType": ["Omni Channel", "Tendering", "Tendering", None]})
    kept = seg.omni_rows(ces)
    assert kept["RevenueType"].tolist() == ["Omni Channel"]
    with pytest.raises(ValueError, match="no RevenueType"):
        seg.omni_rows(ces.drop(columns="RevenueType"))


def test_the_observed_not_late_counts_only_omni_channel_rows(tmp_path):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "investigations"))
    import week1_recalibration as wr
    ces = pd.DataFrame({"ItemCode": ["A"] * 3, "Status": ["Actual"] * 3, "ForecastDelDate": ["2026-01-10"] * 3, "ActualDelDate": ["2026-01-09", "2026-01-20", "2026-01-20"],
                        "ActualQty": [10.0, 10.0, 80.0], "RevenueType": ["Omni Channel", "Omni Channel", "Tendering"]})
    r = wr.observed_not_late(ces, ["A"], "2026-01-01", "2026-12-31")
    assert r["units"] == 20.0 and r["not_late"] == 0.5                              # the 80 late Tendering units are not counted
    with pytest.raises(ValueError, match="no RevenueType"):
        wr.observed_not_late(ces.drop(columns="RevenueType"), ["A"], "2026-01-01")


# ---------------------------------------------------------------- Prompt 30: the producer of the recalibration input (fakes only; it is not yet compared with a real pull)
def test_the_recalibration_input_producer_writes_the_saved_files_schema_through_one_session_with_the_omni_filter(monkeypatch, tmp_path):
    import contextlib
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "investigations"))
    import week1_recalibration as wr
    import db
    expected = ["ContractID", "ItemCode", "CtrDate", "PlanDelDate", "ForecastDelDate", "ActualDelDate", "Status", "PlanQty", "ActualQty", "RevenueType"]
    assert wr.CES_COLUMNS == expected
    if os.path.exists(wr.CES_PATH):                                              # the saved file's header is the schema
        assert list(pd.read_csv(wr.CES_PATH, nrows=0).columns) == expected
    items_path = tmp_path / "stock92.json"
    items_path.write_text('["B-2", "A-1"]')
    seen = {}

    @contextlib.contextmanager
    def fake_session(preflight=False):
        seen["session"], seen["preflight"] = True, preflight
        yield object()
    monkeypatch.setattr(db, "session", fake_session)
    row = {c: None for c in expected}
    row.update({"ContractID": "C1", "ItemCode": "A-1", "Status": "Actual", "ActualQty": 3.0, "RevenueType": "Omni Channel"})
    monkeypatch.setattr(cube_ces_pull, "run_query", lambda sql: seen.setdefault("sql", sql) and pd.DataFrame([{**row, "Extra": 1}]))
    cfg = {"maxmin_v1": {"ensemble_stock_items_file": str(items_path).replace("\\", "/")}}
    monkeypatch.setattr(wr, "PROJECT_ROOT", "")
    out = tmp_path / "ces_92.csv"
    res = wr.pull_ces_input(str(out), cfg)
    assert seen["session"] and seen["preflight"] is True                           # through db.py, with the preflight
    assert "AND RevenueType = 'Omni Channel'" in seen["sql"] and "('A-1','B-2')" in seen["sql"] and "ForecastDelDate" in seen["sql"].split("FROM")[0]
    assert "CtrDate >=" not in seen["sql"] and "WHERE ItemCode IN" in seen["sql"]
    written = pd.read_csv(out)
    assert list(written.columns) == expected and res == {"rows": 1, "items": 2, "path": str(out)}       # exactly the saved schema; the extra column is dropped


# ---- Prompt 35, Step 1: the PEM107 alert is production code of the monthly job

def _fake_pem107_inputs():
    pl = pd.DataFrame({"code": ["A1", "B1"], "type": ["Type A", "Type B"], "description": ["item a", "item b"]})
    rows = []
    # item A1: before the split (2026-05-01): 10 on time, 10 late; from it: 5 on time, 15 late. item B1: before: 20 on time; from it: 10 on time.
    def add(code, forecast, actual, qty, status="Actual", rtype="Omni Channel"):
        rows.append({"ItemCode": code, "ContractID": "X", "Status": status, "RevenueType": rtype, "ForecastDelDate": forecast, "ActualDelDate": actual, "ActualQty": qty})
    add("A1", "2026-01-10", "2026-01-10", 10)
    add("A1", "2026-02-10", "2026-02-20", 10)
    add("A1", "2026-06-10", "2026-06-10", 5)
    add("A1", "2026-07-10", "2026-07-30", 15)
    add("B1", "2026-03-10", "2026-03-01", 20)
    add("B1", "2026-08-10", "2026-08-10", 10)
    add("A1", "2026-06-12", "2026-06-30", 99, rtype="Tendering")          # another channel: not counted
    add("A1", "2026-06-12", None, 99, status="Backlog")                   # not delivered: not counted
    add("A1", "2023-06-12", "2023-06-30", 99)                             # before the window start: not counted
    return pl, pd.DataFrame(rows)


def test_the_pem107_alert_is_computed_from_delivered_omni_rows_only():
    pl, ces = _fake_pem107_inputs()
    alert, items = cube_ces_pull.compute_pem107_alert(ces, pl, ["A1", "B1"], "2026-11-05 07:00:00")
    assert alert["data_pulled_at"] == "2026-11-05 07:00:00"                                  # dated
    assert alert["units_before_may_2026"] == 40 and alert["units_from_may_2026"] == 30
    assert alert["not_late_before_may_2026_pct"] == pytest.approx(100 * 30 / 40) and alert["not_late_from_may_2026_pct"] == pytest.approx(100 * 15 / 30)
    top = items.iloc[0]
    assert top["product_code"] == "A1" and top["units_late"] == 15 and top["share_of_all_late_units_pct"] == pytest.approx(100.0)
    assert alert["split_date"] == "2026-05-01" and alert["before_window_start"] == "2024-01-01"
    assert "customer" not in " ".join(items.columns).lower() and set(items.columns) >= {"product_type", "product_description", "product_code"}


def test_the_pem107_pull_filters_omni_in_the_sql_goes_through_the_open_session_and_writes_dated_files(monkeypatch, tmp_path):
    from datetime import datetime
    import json
    pl, ces = _fake_pem107_inputs()
    seen = {}

    def fake_run_query(sql):
        seen["sql"] = sql
        return ces[ces["RevenueType"] == "Omni Channel"].reset_index(drop=True)
    monkeypatch.setattr(cube_ces_pull, "run_query", fake_run_query)
    monkeypatch.setattr(cube_ces_pull, "pem107_pricelist_rows", lambda root=None: (pl, ["A1", "B1"]))
    import db
    monkeypatch.setattr(db, "session", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a second session was opened")))
    result = cube_ces_pull.pull_pem107_alert(root=str(tmp_path), in_open_session=True, now=datetime(2026, 11, 5, 7, 0, 0))
    sql = seen["sql"]
    assert "FROM Cube_CES" in sql and "RevenueType = 'Omni Channel'" in sql and "ItemCode IN ('A1','B1')" in sql and "SELECT" in sql.upper()
    assert not any(w in sql.upper() for w in ("INSERT", "UPDATE", "DELETE", "CUSTOMER"))
    alert = json.load(open(tmp_path / "output" / "summary" / "task2b_part4_pem107_alert.json", encoding="utf-8"))
    assert alert["data_pulled_at"] == "2026-11-05 07:00:00" and result["pulled_at_local"] == "2026-11-05 07:00:00"
    assert (tmp_path / "output" / "summary" / "task2b_part4_pem107_alert_items.csv").exists() and result["rows"]["items_in_alert"] == 2
    assert result["rows"]["cube_ces_omni"] == len(ces[ces["RevenueType"] == "Omni Channel"])


def test_the_investigation_script_calls_the_production_code_and_holds_no_copy_of_it():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "investigations", "task2b_part4_pem107_alert.py"), encoding="utf-8").read()
    assert "pull_pem107_alert" in src and "not_late_unit_weighted" not in src and "groupby" not in src and "run_query" not in src
