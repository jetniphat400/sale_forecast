"""Regression test for DATA_MAP.md Trap 18 (fixed 2026-09-25): a Cube_CES pull that added a
`CtrDate >= '2023-01-01'` filter, silently dropping legitimate rows and producing an
unrecognizable `not_late` figure. This test fails against that old filter and passes against the
fixed shared helper (`src/cube_ces_pull.py`), which must never add any date condition at pull time.
"""
import pandas as pd

import cube_ces_pull


def test_pull_cube_ces_for_items_has_no_date_filter(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return pd.DataFrame(columns=cube_ces_pull.CUBE_CES_COLUMNS)

    monkeypatch.setattr(cube_ces_pull, "run_query", fake_run_query)
    cube_ces_pull.pull_cube_ces_for_items(["A", "B"])

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
    cube_ces_pull.pull_cube_ces_for_items(["X-1", "X-2", "X-3"])

    sql = captured["sql"]
    assert "'X-1'" in sql and "'X-2'" in sql and "'X-3'" in sql
    assert sql.strip().upper().count("WHERE") == 1
