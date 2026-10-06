"""Operation plan v1 (week 2, METRICS.md Sec.42): the simulation on fixture items, the demand rule, the capacity comparison, the recorded outputs'
hashes, the D3 values and the open-orders test. Everything runs on a small fixture project in a temporary folder; nothing tracked is modified.
Tests that read the recorded real outputs skip with a message when those files are not on this machine, never pass silently."""
import copy
import hashlib
import json
import os
import shutil

import numpy as np
import pandas as pd
import pytest
import yaml

from page_helpers import PROJECT_ROOT

import operation_plan as op  # noqa: E402
import build_inventory_dataset as bid  # noqa: E402
import forward_test_common as ftc  # noqa: E402

REAL_CFG = op.load_config()
TODAY = pd.Timestamp("2026-10-06")
MONTHS = ["2026-10", "2026-11", "2026-12"]


# ------------------------------------------------------------------ the simulation on single items
def test_an_item_that_falls_below_min_is_brought_up_to_max_in_that_month():
    rows = op.simulate_item(opening=100, demand=[30, 30, 30], min_qty=50, max_qty=120)
    assert [r["planned_production"] for r in rows] == [0.0, pytest.approx(120 - 40), 0.0]
    assert [r["closing"] for r in rows] == [70.0, 120.0, 90.0]
    assert [r["opening"] for r in rows] == [100.0, 70.0, 120.0]


def test_an_item_that_never_falls_below_min_is_never_produced():
    rows = op.simulate_item(opening=1000, demand=[10, 20, 30], min_qty=50, max_qty=120)
    assert sum(r["planned_production"] for r in rows) == 0.0 and rows[-1]["closing"] == 940.0


def test_closing_exactly_at_min_is_not_below_it():
    rows = op.simulate_item(opening=80, demand=[30], min_qty=50, max_qty=120)
    assert rows[0]["planned_production"] == 0.0 and rows[0]["closing"] == 50.0


def test_open_orders_arriving_in_a_month_are_added_before_the_comparison_with_min():
    without = op.simulate_item(10, [30], 20, 100)
    with_orders = op.simulate_item(10, [30], 20, 100, open_orders=[60])
    assert without[0]["planned_production"] == pytest.approx(100 + 20) and with_orders[0]["planned_production"] == 0.0
    assert with_orders[0]["closing"] == 40.0


def test_a_demand_that_empties_the_stock_is_not_hidden_by_a_negative_closing():
    rows = op.simulate_item(0, [25], 10, 40)
    assert rows[0]["planned_production"] == 65.0 and rows[0]["closing"] == 40.0


# ------------------------------------------------------------------ a fixture project
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _page(items_by_division, grid=None):
    """An inventory page holding only the embedded data the plan reads. PEM101 has a calibrated section (two grid points), PEM107 uses the default
    controls."""
    def row(code, policy, forecast=None, history=None):
        return {"code": code, "policy": policy, "forecast": forecast or [], "actual_history": history or []}
    data = {"days_per_month": 30.44, "tier_a_defaults": {"procurement_lead_time_days": 60, "assembly_time_days": 3, "review_interval_days": 30,
                                                          "cycle_service_level": 0.95, "holding_cost_rate_annual": 0.2, "obsolescence_threshold_months": 6},
            "page_built_at": "fixture", "divisions": {}}
    for d, items in items_by_division.items():
        data["divisions"][d] = {"items": [row(*i) for i in items]}
    stock101 = [i[0] for i in items_by_division["PEM101"] if i[1] == "stock_policy"]
    g = lambda nl, k: {"r": 1.0, "not_late_median_pct": nl, "stock_value_min": 0, "stock_value_median": 0, "stock_value_max": 0, "n_members": 1,
                       "items": [{"code": c, "Min": 10 * k * (i + 1), "Max_median": 20 * k * (i + 1), "Max_min": 0, "Max_max": 0} for i, c in enumerate(stock101)]}
    data["divisions"]["PEM101"]["curve_target"] = {"grid": grid or [g(90.0, 1), g(100.0, 3)], "presets": {"today_lowest_stock": {"not_late_pct": 95.0}}}
    return '<html><script type="application/json" id="inventory-data">' + json.dumps(data) + "</script></html>"


def _save_pull(root, rel, pulled, inventory, backlog):
    d = os.path.join(root, *rel.split("/"))
    os.makedirs(d, exist_ok=True)
    frames = {"inventory": inventory, "backlog_cube": pd.DataFrame(), "backlog_ces": backlog, "transfer_pairs": pd.DataFrame()}
    for k, v in frames.items():
        v.to_pickle(os.path.join(d, f"{k}.pkl"))
    with open(os.path.join(d, "pull_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"pulled_at_local": pulled, "pulled_at_utc": pulled}, f)


def _backlog(rows):
    return pd.DataFrame([{"ContractID": "C", "ItemCode": i, "CustomerID": "x", "ForecastDelDate": d, "PlanDelDate": d, "ActualQty": a, "BacklogQty": b,
                          "Timestamp": "2026-10-05 07:00:00"} for i, d, a, b in rows])


def _forecast_log(path, meta_path, rows, vintage=1):
    """rows: (item, division, month, qty). One vintage, horizon by month order."""
    months = sorted({r[2] for r in rows})
    df = pd.DataFrame([{"vintage_id": vintage, "itemcode": i, "division": d, "level": "Item", "category": "c", "type": "t", "forecast_run_date": "2026-10-02",
                        "data_cutoff_date": "2026-10-02", "fit_last_month": "2026-08", "model": "m", "config_version": "v", "date_key": "forecastDate",
                        "scope_hash": "h", "scope_n_items": 2, "horizon": months.index(m) + 1, "target_month": m, "forecast_qty": q, "actual_qty": ""}
                       for i, d, m, q in rows])
    df.to_csv(path, index=False)
    back = ftc.read_forward_test_log(path)
    ftc.save_metadata(meta_path, {str(vintage): {"row_integrity_hash": ftc.compute_row_integrity_hash(back[back["vintage_id"] == vintage]),
                                                  "row_hash_scheme": ftc.HASH_SCHEME_CSV_READBACK}})


@pytest.fixture()
def project(tmp_path):
    """Items: A101 (stock_policy, PEM101, starts above Min and falls below it), B101 (stock_policy, never falls below Min), C101 (confirmed_to_order,
    overdue backlog), D101 (conflict, backlog above forecast), E101 (stock_policy, backlog above forecast and overdue backlog), M107 (stock_policy, PEM107),
    N107 (confirmed_to_order)."""
    root = str(tmp_path)
    cfg = copy.deepcopy(REAL_CFG)
    cfg["capacity"]["data_map_reference"] = {"PEM101": 500, "PEM107": 60}
    cfg["open_orders_usable"] = False
    cfg["divisions"] = ["PEM101", "PEM107"]
    cfg["backlog_channel_scope"] = {}
    full = {"operation_plan": cfg, "phase_e1_assumptions": {"sellable_warehouse_codes": {"PEM101": ["FG01", "FG21"], "PEM107": ["FG27"]}}}
    _write(os.path.join(root, "config", "config.yaml"), yaml.safe_dump(full))
    history = [10.0] * 24
    _write(os.path.join(root, *cfg["inventory_page_file"].split("/")), _page({
        "PEM101": [("A101", "stock_policy"), ("B101", "stock_policy"), ("E101", "stock_policy"), ("C101", "confirmed_to_order"), ("D101", "conflict"),
                   ("X101", "confirmed_to_order")],
        "PEM107": [("M107", "stock_policy", [10.0] * 10, history), ("N107", "confirmed_to_order")]}))
    _write_status_file(root, cfg, 3)
    _write_class_file(root, cfg, [("A101", "PEM101", "forecast", "stock_policy", "stock_policy", False, False), ("B101", "PEM101", "forecast", "stock_policy", "stock_policy", False, False),
                                  ("E101", "PEM101", "forecast", "stock_policy", "stock_policy", False, False), ("C101", "PEM101", "forecast", "confirmed_to_order", "confirmed_to_order", False, False),
                                  ("D101", "PEM101", "forecast", "conflict", "mixed", True, False), ("X101", "PEM101", "forecast", "confirmed_to_order", "no_production_in_system", False, True),
                                  ("P101", "PEM101", "placeholder - pending method", "conflict", "conflict", False, False),
                                  ("M107", "PEM107", "forecast", "stock_policy", "stock_policy", False, False), ("N107", "PEM107", "forecast", "confirmed_to_order", "confirmed_to_order", False, False)])
    os.makedirs(os.path.join(root, "output", "summary"), exist_ok=True)
    rows = []
    fc = {"A101": 30, "B101": 1, "E101": 5, "C101": 20, "D101": 8, "X101": 12, "M107": 10, "N107": 40}
    for item, q in fc.items():
        for m in MONTHS:
            rows.append((item, "PEM107" if item.endswith("107") else "PEM101", m, float(q)))
    _forecast_log(os.path.join(root, *cfg["forecast_log_file"].split("/")), os.path.join(root, *cfg["forecast_log_metadata_file"].split("/")), rows)
    inv = pd.DataFrame([{"company": "PEM", "warehouse": w, "itemcode": i, "unit": "PCS", "stock": s, "reserve_bywa": 0, "timestamp": "2026-10-06 00:00:00"}
                        for w, i, s in [("FG01", "A101", 40), ("FG21", "A101", 30), ("WH99", "A101", 999), ("FG01", "B101", 5000), ("FG01", "E101", 0),
                                         ("FG27", "M107", 12), ("FG01", "M107", 888)]])
    backlog = _backlog([("C101", "2026-09-15", 0, 7),          # overdue: goes into the first month
                        ("C101", "2026-11-20", 2, 3),          # ActualQty + BacklogQty = 5
                        ("D101", "2026-10-30", 0, 50),         # above forecast (8)
                        ("E101", "2026-08-01", 0, 40),         # overdue and above the forecast (5)
                        ("E101", "2027-03-01", 0, 99),         # after the last plan month: not used
                        ("B101", "2026-11-02", 0, 0.5),       # below forecast: forecast stays the demand
                        ("P101", "2026-10-12", 0, 30),        # a placeholder item has no forecast: the confirmed order is its whole demand
                        ("P101", "2026-12-12", 2, 3)])
    _save_pull(root, cfg["stock_pull_dir"], "2026-10-06 08:00:40", inv, backlog)
    _save_pull(root, "output/data/inventory_pull", "2026-10-05 07:41:00", inv.iloc[:0], _backlog([("C101", "2026-10-10", 0, 1000)]))
    cf = pd.DataFrame({"itemcode": ["A101", "A101", "A101", "M107", "M107", "M107"], "final_date": ["2025-01-10", "2025-01-20", "2025-02-05", "2025-03-01", "2025-04-01", "2025-05-01"],
                       "transfer_qty": [300, 100, 500, 60, 50, 20]})
    os.makedirs(os.path.join(root, "output", "data", "lead_time_inputs"), exist_ok=True)
    cf.to_csv(os.path.join(root, *cfg["capacity"]["cube_final_file"].split("/")), index=False)
    pd.DataFrame({"code": ["A101", "M107"], "item_type": ["t", "t"], "item_division": ["PEM101", "PEM107"]}).to_csv(
        os.path.join(root, *cfg["capacity"]["item_division_file"].split("/")), index=False)
    return root, cfg


def _write_status_file(root, cfg, never_sold):
    """The phase C item status file: one row per fixture item plus `never_sold` PEM101 codes listed in the price list but never sold."""
    rows = [{"itemcode": c, "division": "PEM101", "status_category": "forecast"} for c in ("A101", "B101")]
    rows += [{"itemcode": f"NS{k}", "division": "PEM101", "status_category": cfg["never_sold_prefix"]} for k in range(never_sold)]
    p = os.path.join(root, *cfg["item_status_file"].split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    pd.DataFrame(rows).to_csv(p, index=False)


def _write_class_file(root, cfg, rows):
    """The Sec.23 item-level file as the plan reads it: code, division, status_category, class_used, class_label, data_inconsistent, no_production_in_system."""
    df = pd.DataFrame(rows, columns=["code", "division", "status_category", "class_used", "class_label", "data_inconsistent", "no_production_in_system"])
    p = os.path.join(root, *cfg["item_class_file"].split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    df.to_csv(p, index=False)


def _plan(project, **kw):
    root, cfg = project
    return op.build_plan(root, TODAY, cfg=cfg, full_cfg=op.load_full_config(root), **kw)


def _row(plan, item, month):
    im = plan["item_month"]
    return im[(im["item"] == item) & (im["month"] == month)].iloc[0]


def test_the_plan_covers_the_vintage_months_from_the_current_month_onward(project):
    plan = _plan(project)
    assert plan["meta"]["months"] == MONTHS and plan["meta"]["vintage_id"] == 1 and plan["meta"]["forecast_vintage_hash_verified"]
    assert plan["item_month"]["item"].nunique() == 9 and len(plan["item_month"]) == 9 * len(MONTHS)


def test_months_before_the_current_month_are_left_out(project):
    root, cfg = project
    plan = op.build_plan(root, pd.Timestamp("2026-11-03"), cfg=cfg, full_cfg=op.load_full_config(root))
    assert plan["meta"]["months"] == MONTHS[1:]


def test_opening_stock_counts_only_the_configured_sellable_warehouses(project):
    plan = _plan(project)
    assert _row(plan, "A101", "2026-10")["opening"] == 70.0       # FG01 + FG21, not WH99
    assert _row(plan, "M107", "2026-10")["opening"] == 12.0       # FG27 only, not FG01


def test_an_item_that_falls_below_min_gets_production_to_max_and_one_that_never_does_gets_none(project):
    plan = _plan(project)
    a = plan["item_month"][plan["item_month"]["item"] == "A101"]
    mn, mx = 10 * 1.0 + (10 * 3.0 - 10 * 1.0) * 0.5, 20 * 1.0 + (20 * 3.0 - 20 * 1.0) * 0.5      # the grid interpolated at the default not_late (95 of 90..100)
    assert (a["min"].iloc[0], a["max"].iloc[0]) == (pytest.approx(mn), pytest.approx(mx))
    assert a["planned_production"].sum() > 0
    for _, r in a.iterrows():
        assert r["closing"] >= r["min"] - 1e-9
        if r["planned_production"] > 0:
            assert r["closing"] == pytest.approx(r["max"])
    b = plan["item_month"][plan["item_month"]["item"] == "B101"]
    assert b["planned_production"].sum() == 0.0


def test_overdue_backlog_goes_into_the_first_month(project):
    plan = _plan(project)
    c = _row(plan, "C101", "2026-10")
    assert c["backlog_due"] == 7.0 and c["demand"] == 20.0 and c["demand_source"] == "forecast"      # 7 overdue < forecast 20
    e = _row(plan, "E101", "2026-10")
    assert e["backlog_due"] == 40.0 and e["demand"] == 40.0 and e["demand_source"] == "backlog"
    assert _row(plan, "E101", "2026-11")["backlog_due"] == 0.0


def test_an_item_with_backlog_above_the_forecast_plans_on_the_backlog(project):
    plan = _plan(project)
    d = _row(plan, "D101", "2026-10")
    assert d["forecast"] == 8.0 and d["backlog_due"] == 50.0 and d["demand"] == 50.0 and d["load"] == 50.0
    assert _row(plan, "D101", "2026-11")["demand"] == 8.0
    assert _row(plan, "B101", "2026-11")["demand"] == 1.0 and _row(plan, "B101", "2026-11")["demand_source"] == "forecast"
    assert plan["meta"]["counts"]["item_months_backlog_above_forecast"] == 2        # D101 in October, E101 in October
    assert plan["meta"]["counts"]["backlog_rows_after_last_month"] == 1


def test_actual_qty_and_backlog_qty_are_added_for_a_backlog_row(project):
    plan = _plan(project)
    assert _row(plan, "C101", "2026-11")["backlog_due"] == 5.0


def test_items_without_a_min_and_max_carry_a_load_equal_to_demand_and_their_class(project):
    plan = _plan(project)
    im = plan["item_month"]
    b = im[im["class"].isin(["confirmed_to_order", "conflict"])]
    assert (b["load"] == b["demand"]).all() and b["planned_production"].isna().all() and b["min"].isna().all()
    assert set(b["class"]) == {"confirmed_to_order", "conflict"}
    a = im[im["class"] == "stock_policy"]
    assert a["load"].isna().all() and a["planned_production"].notna().all()


def test_pem107_min_and_max_are_the_item_table_at_the_default_controls(project):
    import inventory_recompute_reference as ref
    root, cfg = project
    data = op.read_page_data(os.path.join(root, *cfg["inventory_page_file"].split("/")))
    item = next(i for i in data["divisions"]["PEM107"]["items"] if i["code"] == "M107")
    r = ref.compute_item_min_max(item, data["tier_a_defaults"], data["days_per_month"])
    m = _row(_plan(project), "M107", "2026-10")
    assert (m["min"], m["max"]) == (pytest.approx(r["min"]), pytest.approx(r["max"]))


def test_the_backlog_comes_from_the_latest_saved_pull_and_the_stock_from_the_daily_pull(project):
    plan = _plan(project)
    assert plan["meta"]["backlog_pull"]["pulled_at_local"] == "2026-10-06 08:00:40"          # not the 2026-10-05 pull holding 1000 units
    assert _row(plan, "C101", "2026-10")["backlog_due"] == 7.0


def test_a_division_month_above_capacity_is_flagged_and_one_below_is_not(project):
    plan = _plan(project)
    dm = plan["division_month"].set_index(["division", "month"])
    assert plan["meta"]["capacity"]["PEM101"]["capacity"] == 500.0 and plan["meta"]["capacity"]["PEM107"]["capacity"] == 60.0        # 2025-01 PEM101: 400, 2025-02: 500
    im = plan["item_month"]
    for (d, m), r in dm.iterrows():
        sub = im[(im["division"] == d) & (im["month"] == m) & im["counted"]]
        expect = sub["planned_production"].fillna(0).sum() + sub["load"].fillna(0).sum()
        assert r["total_load"] == pytest.approx(expect) and r["above_capacity"] == (expect > r["capacity"])
        assert r["share_of_capacity"] == pytest.approx(expect / r["capacity"])
    assert dm.loc[("PEM107", "2026-10"), "above_capacity"]            # 40 load + production of M107 above 60
    assert not dm.loc[("PEM101", "2026-12"), "above_capacity"]


def test_capacity_passes_over_an_isolated_spike(tmp_path):
    cf = pd.DataFrame({"itemcode": ["A"] * 4, "final_date": ["2025-01-05", "2025-02-05", "2025-03-05", "2025-04-05"], "transfer_qty": [1000, 100, 90, 80]})
    cf.to_csv(tmp_path / "cf.csv", index=False)
    pd.DataFrame({"code": ["A"], "item_type": ["t"], "item_division": ["PEM101"]}).to_csv(tmp_path / "m.csv", index=False)
    cap = op.capacity_reference(str(tmp_path / "cf.csv"), str(tmp_path / "m.csv"), REAL_CFG["capacity"], ["PEM101"])
    assert cap["PEM101"]["capacity"] == 100.0 and cap["PEM101"]["passed_over"] == ["2025-01"] and cap["PEM101"]["month"] == "2025-02"


def test_the_capacity_matches_data_map_flag_follows_the_recomputation(project):
    plan = _plan(project)
    root, cfg = project
    assert op.capacity_matches_data_map(plan["meta"]["capacity"], cfg)
    other = copy.deepcopy(cfg)
    other["capacity"]["data_map_reference"]["PEM101"] = 499
    assert not op.capacity_matches_data_map(plan["meta"]["capacity"], other)


def test_open_orders_are_ignored_unless_the_config_allows_them(project):
    oo = pd.DataFrame([{"item": "A101", "month": "2026-10", "qty": 1000.0}])
    off = _plan(project, open_orders=oo)
    assert off["meta"]["open_orders"] == {"usable": False, "counted": False, "n_rows": 0}
    root, cfg = project
    on_cfg = copy.deepcopy(cfg)
    on_cfg["open_orders_usable"] = True
    on = op.build_plan(root, TODAY, cfg=on_cfg, full_cfg=op.load_full_config(root), open_orders=oo)
    assert on["meta"]["open_orders"]["counted"] and _row(on, "A101", "2026-10")["open_orders"] == 1000.0
    assert _row(on, "A101", "2026-10")["planned_production"] == 0.0 and _row(off, "A101", "2026-10")["planned_production"] >= 0.0


def test_a_forecast_vintage_that_does_not_hash_to_its_metadata_stops_the_build(project):
    root, cfg = project
    p = os.path.join(root, *cfg["forecast_log_file"].split("/"))
    df = pd.read_csv(p, dtype=str)
    df.loc[0, "forecast_qty"] = "999"
    df.to_csv(p, index=False)
    with pytest.raises(op.OperationPlanError):
        _plan(project)


# ------------------------------------------------------------------ week 3: all divisions, items without a forecast, items not counted
def test_a_placeholder_item_has_no_forecast_and_its_demand_is_only_the_confirmed_orders(project):
    plan = _plan(project)
    p = plan["item_month"][plan["item_month"]["item"] == "P101"].set_index("month")
    assert (p["forecast"] == 0).all() and (p["demand_source"] == "backlog").all()
    assert p.loc["2026-10", "demand"] == 30.0 and p.loc["2026-11", "demand"] == 0.0 and p.loc["2026-12", "demand"] == 5.0     # 2 + 3 in December
    assert (p["load"] == p["demand"]).all() and p["planned_production"].isna().all() and p["status_category"].iloc[0].startswith("placeholder")


def test_an_item_with_no_production_in_the_system_is_listed_with_its_demand_and_counted_in_no_total(project):
    plan = _plan(project)
    x = plan["item_month"][plan["item_month"]["item"] == "X101"]
    assert (x["demand"] == 12.0).all() and (x["load"] == 12.0).all() and not x["counted"].any() and (x["class_label"] == "no_production_in_system").all()
    dm = plan["division_month"].set_index(["division", "month"])
    im = plan["item_month"]
    for m in MONTHS:
        counted = im[(im["division"] == "PEM101") & (im["month"] == m) & im["counted"]]
        assert dm.loc[("PEM101", m), "total_load"] == pytest.approx(counted["planned_production"].fillna(0).sum() + counted["load"].fillna(0).sum())
        assert dm.loc[("PEM101", m), "load_not_counted"] == pytest.approx(12.0)
    assert plan["meta"]["counts"]["no_production_items_by_division"]["PEM101"] == 1


def test_the_flag_and_the_label_of_an_item_come_from_the_class_file(project):
    plan = _plan(project)
    d = plan["item_month"][plan["item_month"]["item"] == "D101"]
    assert (d["class_label"] == "mixed").all() and d["data_inconsistent"].all() and (d["class"] == "conflict").all()
    assert not plan["item_month"][plan["item_month"]["item"] == "A101"]["data_inconsistent"].any()


def test_the_codes_listed_but_never_sold_are_counted_per_division_and_are_not_in_the_plan(project):
    plan = _plan(project)
    assert plan["meta"]["counts"]["never_sold_items_by_division"] == {"PEM101": 3, "PEM107": 0}
    assert not plan["item_month"]["item"].str.startswith("NS").any()


def test_the_counts_per_division_come_from_the_plan_not_from_typing(project):
    c = _plan(project)["meta"]["counts"]
    assert c["stock_items_by_division"] == {"PEM101": 3, "PEM107": 1}
    assert c["no_forecast_items_by_division"] == {"PEM101": 1, "PEM107": 0}
    assert c["by_division"] == {"PEM101": 7, "PEM107": 2}


def test_the_channel_scope_keeps_only_the_scoped_divisions_own_channel_and_leaves_the_others(project):
    b = pd.DataFrame({"ItemCode": ["I1", "I1", "I2", "I2"], "RevenueType": ["Omni Channel", "Tendering", "Tendering", None], "BacklogQty": [1, 2, 3, 4]})
    kept, dropped = op.filter_backlog_channel(b, {"I1": "PEM103", "I2": "PEM107"}, {"PEM103": "Omni Channel"})
    assert dropped == 1 and list(kept["BacklogQty"]) == [1, 3, 4]
    same, none = op.filter_backlog_channel(b, {"I1": "PEM103"}, {})
    assert none == 0 and len(same) == 4
    with pytest.raises(op.OperationPlanError):
        op.filter_backlog_channel(b.drop(columns="RevenueType"), {"I1": "PEM103"}, {"PEM103": "Omni Channel"})


def test_the_scoped_divisions_rows_come_from_the_saved_week3_pull_when_the_daily_pull_has_no_revenue_type(project):
    root, cfg = project
    cfg = copy.deepcopy(cfg)
    cfg["backlog_channel_scope"] = {"PEM101": "Omni Channel"}
    cfg["week3_inputs_file"] = "output/data/material_pull/material_inputs.pkl"
    w3 = {"backlog_ces": pd.DataFrame([{"ContractID": "W", "ItemCode": "D101", "ForecastDelDate": "2026-10-20", "PlanDelDate": "2026-10-20", "ActualQty": 0, "BacklogQty": 77,
                                         "RevenueType": "Omni Channel"},
                                        {"ContractID": "T", "ItemCode": "D101", "ForecastDelDate": "2026-10-21", "PlanDelDate": "2026-10-21", "ActualQty": 0, "BacklogQty": 500,
                                         "RevenueType": "Tendering"}]),
          "backlog_pulled_at_local": "2026-10-06 11:00:00"}
    os.makedirs(os.path.dirname(os.path.join(root, *cfg["week3_inputs_file"].split("/"))), exist_ok=True)
    pd.to_pickle(w3, os.path.join(root, *cfg["week3_inputs_file"].split("/")))
    plan = op.build_plan(root, TODAY, cfg=cfg, full_cfg=op.load_full_config(root))
    assert _row(plan, "D101", "2026-10")["backlog_due"] == 77.0                    # the saved Omni row only; the daily pull's 50 for D101 is replaced
    assert _row(plan, "C101", "2026-10")["backlog_due"] == 0.0                     # every scoped-division row comes from the saved pull, which holds none for C101
    assert plan["meta"]["backlog_pull"]["scoped_rows_from"]["divisions"] == ["PEM101"] and plan["meta"]["counts"]["backlog_rows_dropped_by_channel_scope"] == 1      # the Tendering row


def test_capacity_takes_extra_items_for_divisions_the_map_lacks_and_returns_none_for_a_division_with_no_output(tmp_path):
    cf = pd.DataFrame({"itemcode": ["A", "B", "B", "C"], "final_date": ["2025-01-05", "2025-01-06", "2025-02-06", "2025-01-07"], "transfer_qty": [100, 5, 7, 9]})
    cf.to_csv(tmp_path / "cf.csv", index=False)
    pd.DataFrame({"code": ["A"], "item_type": ["t"], "item_division": ["PEM101"]}).to_csv(tmp_path / "m.csv", index=False)
    cap = op.capacity_reference(str(tmp_path / "cf.csv"), str(tmp_path / "m.csv"), REAL_CFG["capacity"], ["PEM101", "CI101", "PEM104"], {"B": "CI101", "A": "CI101"})
    assert cap["PEM101"]["capacity"] == 100.0           # an item the file holds keeps the file's division
    assert cap["CI101"]["capacity"] == 7.0 and cap["PEM104"]["capacity"] is None and cap["PEM104"]["month"] is None


def test_a_missing_class_file_or_one_that_disagrees_with_the_page_stops_the_build(project):
    root, cfg = project
    path = os.path.join(root, *cfg["item_class_file"].split("/"))
    df = pd.read_csv(path)
    df.loc[df["code"] == "A101", "class_used"] = "conflict"
    df.to_csv(path, index=False)
    with pytest.raises(op.OperationPlanError, match="disagree on the class"):
        _plan(project)
    df[df["code"] != "A101"].to_csv(path, index=False)
    with pytest.raises(op.OperationPlanError, match="differ"):
        _plan(project)
    os.remove(path)
    with pytest.raises(op.OperationPlanError, match="missing"):
        _plan(project)


# ------------------------------------------------------------------ recorded outputs and their hashes
def test_outputs_are_recorded_with_hashes_and_a_changed_byte_is_caught(project, tmp_path):
    root, cfg = project
    out = tmp_path / "out"
    plan = _plan(project)
    written = op.write_outputs(plan, root, cfg, out_dir=str(out))
    rec = op.verify_outputs(root, cfg, out_dir=str(out))
    assert set(rec["files"]) == {"operation_plan_v1_item_month.csv", "operation_plan_v1_division_month.csv", "operation_plan_v1_meta.json"}
    for name, v in rec["files"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == v["sha256"]
    im, dm, meta = op.read_outputs(root, cfg, out_dir=str(out))
    assert len(im) == len(plan["item_month"]) and meta["months"] == MONTHS
    with open(out / "operation_plan_v1_item_month.csv", "ab") as f:
        f.write(b"x")
    with pytest.raises(op.OperationPlanError):
        op.verify_outputs(root, cfg, out_dir=str(out))
    assert written["paths"]["output_item_month_file"].startswith(str(out))


def test_the_plan_never_writes_under_the_project_root_when_given_an_output_folder(project, tmp_path_factory):
    root, cfg = project
    before = {os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs}
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    op.run(root, TODAY, out_dir=str(elsewhere))
    after = {os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs}
    assert before == after


def _recorded(cfg=REAL_CFG):
    for k in ("output_item_month_file", "output_division_month_file", "output_meta_file", "output_integrity_file"):
        if not os.path.exists(op.path_of(PROJECT_ROOT, cfg[k])):
            pytest.skip("SKIPPED, not passed: the recorded operation plan is not on this machine: " + cfg[k])


def test_the_recorded_plan_hashes_verify_and_it_reads_back_consistently():
    _recorded()
    im, dm, meta = op.read_outputs(PROJECT_ROOT)
    assert meta["months"] == sorted(set(im["month"])) == sorted(set(dm["month"]))
    assert set(im["class"]) <= {"stock_policy", "confirmed_to_order", "conflict"}
    a = im[im["class"] == "stock_policy"]
    assert ((a["closing"] - (a["opening"] - a["demand"] + a["open_orders"] + a["planned_production"])).abs() < 1e-3).all()
    assert (a["planned_production"] >= 0).all() and (im["demand"] >= im["forecast"] - 1e-6).all() and (im["demand"] >= im["backlog_due"] - 1e-6).all()
    for d in meta["capacity"]:
        assert (dm[dm["division"] == d]["capacity"] == meta["capacity"][d]["capacity"]).all()


def test_the_config_reference_figures_are_the_ones_data_map_records():
    text = open(os.path.join(PROJECT_ROOT, "DATA_MAP.md"), encoding="utf-8").read()
    for division, value in REAL_CFG["capacity"]["data_map_reference"].items():
        assert f"{value:,}" in text, f"DATA_MAP.md does not record {value:,} for {division}"
        assert division in text


def test_the_recomputed_capacity_equals_data_map_on_the_saved_pull():
    for k in ("cube_final_file", "item_division_file"):
        if not os.path.exists(op.path_of(PROJECT_ROOT, REAL_CFG["capacity"][k])):
            pytest.skip("SKIPPED, not passed: saved input missing on this machine: " + REAL_CFG["capacity"][k])
    cap = op.capacity_reference(op.path_of(PROJECT_ROOT, REAL_CFG["capacity"]["cube_final_file"]),
                                op.path_of(PROJECT_ROOT, REAL_CFG["capacity"]["item_division_file"]), REAL_CFG["capacity"], REAL_CFG["divisions"])
    assert op.capacity_matches_data_map(cap, REAL_CFG)


# ------------------------------------------------------------------ D3: the observed material lead-time median
def _lead_fixture(tmp_path, monkeypatch, rows):
    import maxmin_v1 as mm
    monkeypatch.setattr(mm, "PROJECT_ROOT", str(tmp_path))
    cfg = dict(mm.load_config())
    cfg["item_lead_time_file"], cfg["item_lead_time_integrity_file"] = "lead.csv", "lead.json"
    df = pd.DataFrame(rows, columns=["item", "bottleneck_days", "bottleneck_source", "no_bom", "production_days", "production_source"])
    df.to_csv(tmp_path / "lead.csv", index=False)
    (tmp_path / "lead.json").write_text(json.dumps({"sha256": hashlib.sha256((tmp_path / "lead.csv").read_bytes()).hexdigest()}))
    return mm, cfg


def test_the_observed_median_counts_only_items_whose_value_is_observed(tmp_path, monkeypatch):
    rows = [("A", 40, "observed", False, 26, "assumed"), ("B", 60, "observed", False, 26, "assumed"), ("C", 100, "observed", False, 26, "assumed"),
            ("D", 63, "assumed", True, 26, "assumed"), ("E", 63, "assumed", False, 26, "assumed"), ("F", 90, "supplier_quoted", False, 26, "assumed")]
    mm, cfg = _lead_fixture(tmp_path, monkeypatch, rows)
    page = mm.material_lead_for_page([r[0] for r in rows], cfg)
    assert page["median_observed_days"] == 60.0 and page["n_observed"] == 3 and page["n_items_shown"] == 6
    assert page["median_days"] == 63.0                      # the all-items median is not what the line states


def test_the_observed_count_and_median_follow_the_items_shown(tmp_path, monkeypatch):
    rows = [("A", 40, "observed", False, 26, "assumed"), ("B", 60, "observed", False, 26, "assumed"), ("C", 100, "observed", False, 26, "assumed"),
            ("D", 63, "assumed", True, 26, "assumed")]
    mm, cfg = _lead_fixture(tmp_path, monkeypatch, rows)
    page = mm.material_lead_for_page(["B", "C", "D"], cfg)
    assert page["median_observed_days"] == 80.0 and page["n_observed"] == 2 and page["n_items_shown"] == 3


def test_the_recorded_observed_median_equals_a_direct_recomputation():
    path = os.path.join(PROJECT_ROOT, "output", "summary", "item_lead_time_v1.csv")
    if not os.path.exists(path):
        pytest.skip("SKIPPED, not passed: output/summary/item_lead_time_v1.csv is not on this machine")
    import maxmin_v1 as mm
    d = pd.read_csv(path)
    page = mm.material_lead_for_page(list(d["item"]))
    obs = d[d["bottleneck_source"] == "observed"]["bottleneck_days"]
    assert page["median_observed_days"] == float(obs.median()) and page["n_observed"] == len(obs) and page["n_items_shown"] == len(d)


# ------------------------------------------------------------------ Part 1: the open-orders test's verdict
def _orders(n_finished_close, n_finished_far, n_unfinished=0):
    """Plan rows with a final record close to or far from the planned finish, and plan rows with no final record; every status Printed (so no
    status rule can pass)."""
    po, cf, k = [], [], 0
    for kind, n in (("close", n_finished_close), ("far", n_finished_far), ("none", n_unfinished)):
        for _ in range(n):
            k += 1
            po.append({"id": k, "company": "PEM", "warehouse": "W", "job": f"J{k}", "cost_centre": "x", "itemcode": "I", "description": "d", "planed": 10.0,
                       "to_be_realized": 10.0, "unit": "PCS", "start_date": "2026-01-01", "end_date": "2026-03-01", "actual_date": "2026-03-01", "status": "Printed",
                       "timestamp": "2026-10-06"})
            if kind != "none":
                cf.append({"jobno": f"J{k}", "itemcode": "I", "final_date": "2026-03-03" if kind == "close" else "2026-06-01"})
    return pd.DataFrame(po), pd.DataFrame(cf)


def test_open_orders_are_not_usable_when_the_planned_finish_does_not_hold():
    import sys
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "investigations"))
    import week2_open_orders_test as t
    po, cf = _orders(2, 8)
    res = t.run_test(po, cf, po, {"open_orders_test": REAL_CFG["open_orders_test"]}, TODAY, {"I"})
    assert res["C1_pass"] is False and res["usable"] is False and "planned finish" in res["verdict"]


def test_open_orders_are_usable_only_when_the_finish_holds_and_an_open_rule_passes():
    import sys
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "investigations"))
    import week2_open_orders_test as t
    po, cf = _orders(9, 1, n_unfinished=40)                # 90 percent of finished orders end within 14 days of the plan; 40 overdue orders have no record
    res = t.run_test(po, cf, po, {"open_orders_test": REAL_CFG["open_orders_test"]}, TODAY, {"I"})
    assert res["C1_pass"] is True
    # no way of telling an open order passes (all status Printed, no receipts, and only 10 of 50 overdue orders have a final record): not usable
    assert res["usable"] is False and "no way of telling" in res["verdict"]
    # now give the finished orders receipts that reach the plan: the receipts rule passes and the verdict becomes usable
    extra = po[po["job"].isin(set(cf["jobno"]))].copy()
    extra["to_be_realized"] = 0.0
    extra["id"] = extra["id"] + 1000
    res2 = t.run_test(pd.concat([po, extra], ignore_index=True), cf, po, {"open_orders_test": REAL_CFG["open_orders_test"]}, TODAY, {"I"})
    assert res2["C2b_pass"] is True and res2["usable"] is True and res2["verdict"].startswith("usable")


def test_the_recorded_open_orders_finding_matches_the_config_flag():
    path = op.path_of(PROJECT_ROOT, REAL_CFG["open_orders_test_file"])
    if not os.path.exists(path):
        pytest.skip("SKIPPED, not passed: the recorded open-orders test is not on this machine")
    with open(path, encoding="utf-8") as f:
        res = json.load(f)
    assert REAL_CFG["open_orders_usable"] is bool(res["usable"]), "the config flag must equal the recorded test's verdict"
    assert res["criteria"] == REAL_CFG["open_orders_test"]
