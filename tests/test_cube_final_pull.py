"""Regression test for DATA_MAP.md Trap 7 (resolved 2026-09-24): cube_final pulls filtered on
itemcode had previously returned zero rows, and it was unclear whether the join key itself was
broken. This task (Phase 23, Part 0) confirmed the itemcode join works (75.21% forward match rate
for the 351-item scope) -- this test guards the shared helper (`src/cube_final_pull.py`) against a
future regression: it must always scope by `itemcode IN (...)` and must never add a date filter at
the SQL level (the same Trap-18 pattern already guarded for Cube_CES).
"""
import pandas as pd

import cube_final_pull


def test_pull_cube_final_for_items_has_no_date_filter(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return pd.DataFrame(columns=cube_final_pull.CUBE_FINAL_COLUMNS)

    monkeypatch.setattr(cube_final_pull, "run_query", fake_run_query)
    cube_final_pull.pull_cube_final_for_items(["A", "B"])

    sql = captured["sql"]
    assert "itemcode IN" in sql
    where_clause = sql.upper().split("WHERE", 1)[1]
    # The bug this test guards against: any date-column comparison in WHERE (final_date,
    # finalcheck_date, etc.) -- DATA_MAP.md Trap 7/Trap 18 pattern.
    for date_col in ["FINAL_DATE", "FINALCHECK_DATE", "FINALRECEIVE_DATE", "TIMSSTAMP"]:
        assert date_col not in where_clause, (
            f"pull_cube_final_for_items must not filter on {date_col} (or any date column) at "
            "the SQL level -- any date window belongs in Python, applied against whichever field "
            "the analysis needs."
        )
    assert ">=" not in where_clause and "<=" not in where_clause
    assert " < " not in where_clause and " > " not in where_clause


def test_pull_cube_final_for_items_scopes_by_itemcode_only(monkeypatch):
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return pd.DataFrame(columns=cube_final_pull.CUBE_FINAL_COLUMNS)

    monkeypatch.setattr(cube_final_pull, "run_query", fake_run_query)
    cube_final_pull.pull_cube_final_for_items(["X-1", "X-2", "X-3"])

    sql = captured["sql"]
    assert "'X-1'" in sql and "'X-2'" in sql and "'X-3'" in sql
    assert sql.strip().upper().count("WHERE") == 1


def test_pull_cube_final_for_items_uses_verified_working_key(monkeypatch):
    """Guards against reverting to a different, unverified join key: this task confirmed
    `itemcode` (exact string match, no format transform) is the working key -- the WHERE clause
    must reference the itemcode column literally, not a derived/transformed expression."""
    captured = {}

    def fake_run_query(sql):
        captured["sql"] = sql
        return pd.DataFrame(columns=cube_final_pull.CUBE_FINAL_COLUMNS)

    monkeypatch.setattr(cube_final_pull, "run_query", fake_run_query)
    cube_final_pull.pull_cube_final_for_items(["EEE-F-FC-1040010002"])

    sql = captured["sql"]
    where_clause = sql.split("WHERE", 1)[1]
    assert where_clause.strip().startswith("itemcode IN"), (
        "The WHERE clause must filter on the bare itemcode column (the verified working key), "
        "not a transformed expression such as UPPER(itemcode), LTRIM/RTRIM(itemcode), or a "
        "different column -- see output/summary/phase23_part0_cubefinal_join_report.md."
    )
