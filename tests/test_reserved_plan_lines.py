"""Reserved is the sum of every Cube_CES Backlog plan line, and the stock page and the operation plan use one rule (Prompt 66, T1-001). Fixtures only."""
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import build_inventory_dataset as bid  # noqa: E402
import daily_stock_job as djob  # noqa: E402
import operation_plan as op  # noqa: E402
import source_guard as sg  # noqa: E402


def _ces(rows):
    cols = ["ContractID", "ItemCode", "PlanID", "CustomerID", "ForecastDelDate", "PlanDelDate", "ActualQty", "BacklogQty", "Timestamp", "RevenueType"]
    return pd.DataFrame([{**{"CustomerID": "X", "ForecastDelDate": "2026-11-10", "PlanDelDate": "2026-11-10", "ActualQty": 0.0, "Timestamp": "2026-11-02 07:35:00", "RevenueType": "Omni Channel"}, **r} for r in rows])[cols]


# the shape the verification found: one contract and item with three plan lines (own PlanID, quantity and date), plus an unrelated line
LINES = [dict(ContractID="C1", ItemCode="A", PlanID="P1", BacklogQty=10.0), dict(ContractID="C1", ItemCode="A", PlanID="P2", BacklogQty=20.0, ForecastDelDate="2026-12-02"),
         dict(ContractID="C1", ItemCode="A", PlanID="P3", BacklogQty=5.0), dict(ContractID="C2", ItemCode="B", PlanID="P4", BacklogQty=7.0)]


def test_separate_plan_lines_of_one_contract_and_item_all_count():
    per_code, rows = bid.dedup_and_aggregate_ces_backlog(_ces(LINES))
    assert dict(zip(per_code["code"], per_code["backlog"])) == {"A": 35.0, "B": 7.0}
    assert len(rows["A"]) == 3 and sorted(r["quantity"] for r in rows["A"]) == [5.0, 10.0, 20.0]


def test_a_true_duplicate_is_dropped_and_the_row_kept_does_not_depend_on_the_order_the_source_returned():
    a = _ces(LINES + [dict(ContractID="C1", ItemCode="A", PlanID="P1", BacklogQty=10.0)])                 # the same (contract, item, plan) again
    reversed_ = a.iloc[::-1].reset_index(drop=True)
    shuffled = a.sample(frac=1.0, random_state=3).reset_index(drop=True)
    kept = [bid.backlog_lines(x) for x in (a, reversed_, shuffled)]
    assert all(len(k) == 4 for k in kept)
    assert all(k.equals(kept[0]) for k in kept)                                                             # same rows in the same order whatever the arrival order
    differing = _ces(LINES + [dict(ContractID="C1", ItemCode="A", PlanID="P1", BacklogQty=99.0)])        # a repeated key with another quantity: still one line, always the same one
    assert bid.backlog_lines(differing)["BacklogQty"].tolist() == bid.backlog_lines(differing.iloc[::-1].reset_index(drop=True))["BacklogQty"].tolist()


def test_a_row_without_a_plan_id_is_never_dropped_and_a_pull_without_the_column_is_refused_by_the_page_but_read_by_the_plan():
    nan_ids = _ces([dict(ContractID="C1", ItemCode="A", PlanID=None, BacklogQty=1.0), dict(ContractID="C1", ItemCode="A", PlanID=None, BacklogQty=2.0)])
    assert len(bid.backlog_lines(nan_ids)) == 2
    old = _ces(LINES).drop(columns="PlanID")
    with pytest.raises(ValueError, match="no PlanID column"):
        bid.dedup_and_aggregate_ces_backlog(old)
    assert len(bid.backlog_lines(old, require_plan_id=False)) == 4                                           # the plan reads an older saved pull, every row counting as before


def test_the_stock_page_and_the_operation_plan_count_the_same_units():
    ces = _ces(LINES + [dict(ContractID="C1", ItemCode="A", PlanID="P1", BacklogQty=10.0)])
    per_code, _ = bid.dedup_and_aggregate_ces_backlog(ces)
    wide, n_after = op.backlog_by_month(ces, ["2026-11", "2026-12"])
    assert n_after == 0
    assert dict(zip(per_code["code"], per_code["backlog"])) == wide.sum(axis=1).to_dict() == {"A": 35.0, "B": 7.0}


def test_the_old_rule_would_have_changed_the_figure_the_unit_of_the_difference():
    """The effect on available: an item with on hand 12 and three plan lines (10 + 20 + 5) reads 12 - 35 = -23, not 12 - 10 = +2 (the old first-row rule)."""
    per_code, _ = bid.dedup_and_aggregate_ces_backlog(_ces(LINES))
    assert 12.0 - float(per_code.set_index("code").loc["A", "backlog"]) == -23.0


# ------------------------------------------------------------------ the guards
def test_the_daily_reserved_gates_include_a_plan_id_key_check_that_fails_on_a_null_or_a_missing_column():
    config = djob.load_config(PROJECT_ROOT)
    payload = {"reserved_source_load_time": "2026-11-02 07:35:00", "pull_time": "2026-11-03 10:30:00"}
    base = {"backlog_rows": 4, "source": "test"}

    def gates(ces):
        return {g["gate"]: g for g in djob.reserved_gates(payload, ces, base, config)}
    ok = gates(_ces(LINES))
    assert ok["reserved_key_columns"]["passed"] and ok["reserved_rows_band"]["passed"]
    null_plan = gates(_ces(LINES[:3] + [dict(ContractID="C2", ItemCode="B", PlanID=None, BacklogQty=7.0)]))
    assert not null_plan["reserved_key_columns"]["passed"] and "PlanID 1" in null_plan["reserved_key_columns"]["detail"]
    no_column = gates(_ces(LINES).drop(columns="PlanID"))
    assert not no_column["reserved_key_columns"]["passed"] and "PlanID" in no_column["reserved_key_columns"]["detail"]


def test_a_key_column_the_pull_does_not_have_counts_as_missing_in_the_frame_stats():
    s = sg.frame_stats(pd.DataFrame({"ItemCode": ["A", "B"]}), ("ItemCode", "PlanID"))
    assert s["key_nulls"] == {"ItemCode": 0, "PlanID": 2}


def test_the_monthly_step_1_checks_plan_id_as_a_key_of_the_reserved_pull():
    import monthly_refresh as mr
    reserved = next(src for src in mr._guard_plan()["stock_reserved" if "stock_reserved" in mr._guard_plan() else next(k for k, v in mr._guard_plan().items() if any(s[0] == "reserved" for s in v["sources"]))]["sources"] if src[0] == "reserved")
    assert reserved[4] == ("ItemCode", "PlanID")


def test_the_pull_selects_plan_id_and_orders_by_the_line_key(monkeypatch):
    captured = {}
    monkeypatch.setattr(bid, "run_query", lambda sql: captured.setdefault("sql", sql) and pd.DataFrame())
    bid.query_backlog_ces(["A"])
    sql = " ".join(captured["sql"].split())
    assert "SELECT ContractID, ItemCode, PlanID," in sql and sql.endswith("ORDER BY ContractID, ItemCode, PlanID")
