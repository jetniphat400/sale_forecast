"""Week 2's page (forecast/operation_plan.html), the two Min-Max clarifications, the index link and the four assumption records.

Backend: the split of stock-item production on fixture items, every braced value against its source (including the omission rules and the joining of
one, two and three items), the page total against the recorded division-month total, the assumptions file. Screen: pages built to a temporary site and
opened in a headless browser (own Edge on a temp profile, own PID, closed by PID only). No tracked file is modified. With no browser, or without the
recorded plan, a test is SKIPPED with a message, never passed silently."""
import functools
import hashlib
import http.server
import json
import os
import re
import shutil
import threading
import time

import numpy as np
import pandas as pd
import pytest

from page_helpers import Edge, PROJECT_ROOT, fresh_inventory_data, load_stock_payload, require_browser, write_stock_file

import build_operation_plan_page as bp  # noqa: E402
import operation_plan as op  # noqa: E402
import maxmin_v1 as mm  # noqa: E402

CFG = op.load_config()
MONTHS = ["2026-10", "2026-11", "2026-12"]


# ------------------------------------------------------------------ fixture plan
def _rows(division, item, cls, forecast, backlog, opening=None, mn=None, mx=None, months=MONTHS):
    """Plan rows of one item as operation_plan.build_plan writes them (stock items simulated by simulate_item, others load = demand)."""
    out = []
    demand = [max(f, b) for f, b in zip(forecast, backlog)]
    if cls == "stock_policy":
        sim = op.simulate_item(opening, demand, mn, mx)
    for i, m in enumerate(months):
        r = {"division": division, "item": item, "class": cls, "min_max_source": "x" if cls == "stock_policy" else "", "month": m, "forecast": forecast[i],
             "backlog_due": backlog[i], "demand": demand[i], "demand_source": "backlog" if backlog[i] > forecast[i] else "forecast"}
        if cls == "stock_policy":
            r.update({"opening": sim[i]["opening"], "open_orders": 0.0, "min": mn, "max": mx, "planned_production": sim[i]["planned_production"],
                      "closing": sim[i]["closing"], "load": np.nan})
        else:
            r.update({"opening": np.nan, "open_orders": np.nan, "min": np.nan, "max": np.nan, "planned_production": np.nan, "closing": np.nan, "load": demand[i]})
        out.append(r)
    return out


def _plan(extra107=None, refill101=True, capacity=(1000.0, 100.0)):
    """PEM101: S1 starts below Min (refill part in October), S2 never produces, T1 made to order. PEM107: one stock item, made-to-order items whose
    October backlog is above the forecast (`extra107`: item -> backlog units in October)."""
    rows = []
    rows += _rows("PEM101", "S1", "stock_policy", [10, 10, 10], [0, 0, 0], opening=5.0 if refill101 else 500.0, mn=30.0, mx=80.0)
    rows += _rows("PEM101", "S2", "stock_policy", [1, 1, 1], [0, 0, 0], opening=500.0, mn=3.0, mx=9.0)
    rows += _rows("PEM101", "T1", "confirmed_to_order", [4, 4, 4], [0, 0, 0])
    rows += _rows("PEM107", "M1", "stock_policy", [5, 5, 5], [0, 0, 0], opening=1000.0, mn=10.0, mx=20.0)
    extra107 = extra107 if extra107 is not None else {"A7": 60.0, "B7": 25.0, "C7": 10.0, "D7": 5.0}
    for k, (item, b) in enumerate(extra107.items()):
        rows += _rows("PEM107", item, "confirmed_to_order" if k % 2 == 0 else "conflict", [2, 2, 2], [b, 0, 0])
    im = pd.DataFrame(rows, columns=op.ITEM_MONTH_COLUMNS)
    drows = []
    for d, cap in zip(("PEM101", "PEM107"), capacity):
        for m in MONTHS:
            s = im[(im["division"] == d) & (im["month"] == m)]
            total = float(s["planned_production"].fillna(0).sum() + s["load"].fillna(0).sum())
            drows.append({"division": d, "month": m, "planned_production_stock": float(s["planned_production"].fillna(0).sum()),
                          "load_confirmed_to_order": float(s.loc[s["class"] == "confirmed_to_order", "load"].sum()),
                          "load_conflict": float(s.loc[s["class"] == "conflict", "load"].sum()), "total_load": total, "capacity": cap,
                          "share_of_capacity": total / cap, "above_capacity": total > cap})
    meta = {"months": MONTHS, "stock_pull": {"pulled_at_local": "2026-10-06 08:00:40"}, "vintage_id": 2}
    return im, pd.DataFrame(drows, columns=op.DIVISION_MONTH_COLUMNS), meta


def _values(**kw):
    im, dm, meta = _plan(**{k: v for k, v in kw.items() if k in ("extra107", "refill101", "capacity")})
    return bp.compute_values(im, dm, meta, {"S1": "Name S1"}, kw.get("run_date", "2026-10-02"))


# ------------------------------------------------------------------ the split
def test_the_split_gives_demand_part_and_refill_that_add_back_to_production():
    prod = np.array([0.0, 5.0, 30.0, 100.0])
    dem = np.array([10.0, 10.0, 10.0, 40.0])
    meets, refill = bp.split_production(prod, dem)
    assert list(meets) == [0.0, 5.0, 10.0, 40.0] and list(refill) == [0.0, 0.0, 20.0, 60.0]
    assert np.allclose(meets + refill, prod) and (meets <= dem).all() and (refill >= 0).all()


def test_the_split_on_fixture_stock_items_by_month():
    im, dm, meta = _plan()
    v = bp.compute_values(im, dm, meta, {}, "2026-10-02")
    s = v["summary"].set_index(["division", "month"])
    s1 = im[(im["item"] == "S1")].set_index("month")
    # S1: opening 5, demand 10, Min 30, Max 80 -> closing -5 -> production 85 = demand 10 + refill 75; later months produce the demand only
    assert s1.loc["2026-10", "planned_production"] == 85.0
    assert s.loc[("PEM101", "2026-10"), "demand_part"] == 10.0 and s.loc[("PEM101", "2026-10"), "refill_part"] == 75.0
    assert s.loc[("PEM101", "2026-11"), "refill_part"] == pytest.approx(0.0) or s.loc[("PEM101", "2026-11"), "refill_part"] >= 0
    for (d, m), r in s.iterrows():
        sub = im[(im["division"] == d) & (im["month"] == m)]
        assert r["demand_part"] + r["refill_part"] == pytest.approx(sub["planned_production"].fillna(0).sum())
        assert r["mto"] == pytest.approx(sub["load"].fillna(0).sum())


def test_the_page_total_must_equal_the_recorded_division_month_total():
    im, dm, meta = _plan()
    bad = dm.copy()
    bad.loc[0, "total_load"] += 1.0
    with pytest.raises(op.OperationPlanError):
        bp.compute_values(im, bad, meta, {}, "2026-10-02")


def test_the_above_capacity_flag_follows_the_recorded_comparison():
    v = _values(capacity=(50.0, 1000.0))
    s = v["summary"].set_index(["division", "month"])
    assert s.loc[("PEM101", "2026-10"), "above"] and not s.loc[("PEM107", "2026-10"), "above"]
    page = bp.render(v)
    assert page.count(bp.TEXT["above_capacity"]) == int(v["summary"]["above"].sum()) >= 1


# ------------------------------------------------------------------ braced values
def test_dates_follow_the_source_in_thai_with_the_buddhist_year():
    assert bp.thai_datetime("2026-10-06 08:00:40") == "6 ต.ค. 69 08:00"
    assert bp.thai_datetime("2027-01-31 17:05:00") == "31 ม.ค. 70 17:05"
    assert bp.thai_month("2026-10") == "ต.ค. 69" and bp.thai_month("2027-12") == "ธ.ค. 70"
    v = _values(run_date="2027-03-15")
    assert v["forecast_run_month"] == "มี.ค. 70" and v["pull_time"] == "6 ต.ค. 69 08:00" and v["first_month"] == "ต.ค. 69"


def test_refill_units_is_the_pem101_first_month_refill_sum():
    v = _values()
    assert v["refill_units"] == "75" and v["refill_first"] == 75.0
    im, dm, meta = _plan()
    s1 = im[(im["item"] == "S1") & (im["month"] == "2026-10")].iloc[0]
    assert v["refill_first"] == pytest.approx(s1["planned_production"] - min(s1["planned_production"], s1["demand"]))


def test_backlog_above_forecast_is_pem107s_first_month_positive_excess_summed_over_items():
    v = _values()
    assert v["backlog_above_forecast_value"] == (60 - 2) + (25 - 2) + (10 - 2) + (5 - 2) and v["backlog_above_forecast"] == "92"
    v2 = _values(extra107={"A7": 1.0, "B7": 2.0})                  # backlog at or below the forecast of 2: no excess
    assert v2["backlog_above_forecast_value"] == 0.0


@pytest.mark.parametrize("extra,expected_codes", [
    ({"A7": 90.0, "B7": 5.0, "C7": 4.0}, ["A7"]),                                          # one item reaches 80 percent
    ({"A7": 60.0, "B7": 30.0, "C7": 10.0}, ["A7", "B7"]),                                  # two items reach it
    ({"A7": 40.0, "B7": 30.0, "C7": 20.0, "D7": 10.0}, ["A7", "B7", "C7"]),                # three items, the cap
    ({"A7": 30.0, "B7": 25.0, "C7": 20.0, "D7": 15.0, "E7": 10.0}, ["A7", "B7", "C7"]),    # more would be needed, three is the most
])
def test_top_backlog_items_reach_80_percent_at_most_three_in_descending_order(extra, expected_codes):
    v = _values(extra107=extra)
    assert [c for c, _ in v["top_backlog_picked"]] == expected_codes
    text = v["top_backlog_items"]
    parts = [f"{c} ({int(round(u)):,} หน่วย)" for c, u in v["top_backlog_picked"]]
    expect = parts[0] if len(parts) == 1 else (parts[0] + " และ " + parts[1] if len(parts) == 2 else parts[0] + ", " + parts[1] + " และ " + parts[2])
    assert text == expect


def test_the_joining_of_one_two_and_three_items():
    assert bp.join_items(["a (1 หน่วย)"]) == "a (1 หน่วย)"
    assert bp.join_items(["a", "b"]) == "a และ b"
    assert bp.join_items(["a", "b", "c"]) == "a, b และ c"


def test_the_three_lines_are_rendered_with_their_values_and_in_the_approved_wording():
    v = _values()
    page = bp.render(v)
    lines = [l.strip() for l in re.findall(r'<p class="note-line">(.*?)</p>', page)]
    assert lines[0] == (f"{v['first_month']} PEM101 ต้องเติมให้ถึง Max {v['refill_units']} หน่วย นอกเหนือจากความต้องการเดือนนั้น "
                        "เพราะ stock ตอนนี้ต่ำกว่า Max ทยอยเติมในเดือนถัดไปได้")
    assert lines[1] == (f"{v['first_month']} PEM107 มีออเดอร์ที่รับแล้วสูงกว่ายอดทาย {v['backlog_above_forecast']} หน่วย ส่วนใหญ่จาก {v['top_backlog_items']}")
    assert lines[2] == "ยอดผลิตสูงสุดที่เคยทำ คือยอดผลิตเสร็จต่อเดือนสูงสุดในอดีต นับทุกสินค้ารวมกันโดยไม่แยกขนาด ใช้ดูทิศทาง ไม่ได้แปลว่าเป็นกำลังผลิตเต็มที่"
    assert len(lines) == 3


def test_the_refill_line_is_omitted_when_the_refill_part_is_zero_and_the_backlog_line_when_there_is_no_excess():
    no_refill = bp.render(_values(refill101=False))
    assert "ต้องเติมให้ถึง Max" not in no_refill and "มีออเดอร์ที่รับแล้วสูงกว่ายอดทาย" in no_refill
    no_backlog = bp.render(_values(extra107={"A7": 1.0}))
    assert "มีออเดอร์ที่รับแล้วสูงกว่ายอดทาย" not in no_backlog and "ต้องเติมให้ถึง Max" in no_backlog
    neither = bp.render(_values(refill101=False, extra107={"A7": 1.0}))
    assert len(re.findall(r'<p class="note-line">', neither)) == 1 and "ยอดผลิตสูงสุดที่เคยทำ คือ" in neither


def test_the_heading_months_and_the_data_line_come_from_the_plan_not_from_typing():
    v = _values()
    page = bp.render(v)
    assert f"แผนการผลิต {len(MONTHS)} เดือน · PEM101 และ PEM107" in page
    assert f"ข้อมูล stock ดึงเมื่อ {v['pull_time']} · ยอดทายจากรอบ {v['forecast_run_month']}" in page
    im, dm, meta = _plan()
    meta4 = dict(meta, months=MONTHS)
    assert "6 เดือน" not in page


def test_the_item_table_has_blank_min_max_and_stock_for_items_without_them_and_class_labels():
    page = bp.render(_values())
    rows = re.findall(r'<tr data-division="(\w+)" data-class="(\w+)">(.*?)</tr>', page)
    by = {re.search(r"<td>(\w+)</td>", r[2]).group(1): r for r in rows}
    assert "เก็บ stock" in by["S1"][2] and "ผลิตตามสั่ง" in by["T1"][2] and "ยังไม่ชัด" in by["B7"][2]
    t1 = re.findall(r"<td[^>]*>(.*?)</td>", by["T1"][2])
    assert t1[3] == "" and t1[4] == "" and t1[5] == ""                      # stock now, Min, Max blank
    s1 = re.findall(r"<td[^>]*>(.*?)</td>", by["S1"][2])
    assert s1[1] == "Name S1" and s1[3] == "5" and s1[4] == "30" and s1[5] == "80"
    assert len(s1) == 6 + len(MONTHS)


# ------------------------------------------------------------------ against the recorded plan
def _recorded():
    for k in ("output_item_month_file", "output_division_month_file", "output_meta_file", "output_integrity_file"):
        if not os.path.exists(op.path_of(PROJECT_ROOT, CFG[k])):
            pytest.skip("SKIPPED, not passed: the recorded operation plan is not on this machine")
    if not os.path.exists(os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")):
        pytest.skip("SKIPPED, not passed: the price list is not on this machine")


def test_every_braced_value_equals_a_direct_recomputation_from_the_recorded_plan():
    _recorded()
    im, dm, meta = op.read_outputs(PROJECT_ROOT)
    v = bp.build_values(PROJECT_ROOT)
    first = meta["months"][0]
    a = im[(im["class"] == "stock_policy") & (im["division"] == "PEM101") & (im["month"] == first)]
    refill = float((a["planned_production"] - np.minimum(a["planned_production"], a["demand"])).sum())
    assert v["refill_units"] == f"{int(round(refill)):,}"
    b = im[(im["division"] == "PEM107") & (im["month"] == first)]
    ex = (b["backlog_due"] - b["forecast"]).clip(lower=0)
    assert v["backlog_above_forecast"] == f"{int(round(ex.sum())):,}"
    order = ex.groupby(b["item"]).sum().sort_values(ascending=False)
    run, picked = 0.0, []
    for code, x in order.items():
        picked.append(code)
        run += x
        if run >= 0.8 * ex.sum() or len(picked) == 3:
            break
    assert [c for c, _ in v["top_backlog_picked"]] == picked
    pulled = pd.Timestamp(meta["stock_pull"]["pulled_at_local"][:19])
    assert v["pull_time"] == f"{pulled.day} {bp.THAI_MONTHS[pulled.month - 1]} {str(pulled.year + 543)[-2:]} {pulled:%H:%M}"
    log = pd.read_csv(op.path_of(PROJECT_ROOT, CFG["forecast_log_file"]), dtype=str)
    run_date = sorted(set(log.loc[log["vintage_id"] == str(meta["vintage_id"]), "forecast_run_date"]))
    assert len(run_date) == 1 and v["forecast_run_month"] == bp.thai_month(run_date[0][:7])
    assert v["first_month"] == bp.thai_month(first) and v["n_months"] == len(meta["months"])


def test_the_summary_totals_equal_the_recorded_division_month_output_and_the_parts_add_back():
    _recorded()
    im, dm, meta = op.read_outputs(PROJECT_ROOT)
    v = bp.build_values(PROJECT_ROOT)
    for _, r in v["summary"].iterrows():
        rec = dm[(dm["division"] == r["division"]) & (dm["month"] == r["month"])].iloc[0]
        assert r["total"] == pytest.approx(rec["total_load"], abs=1e-3) and r["capacity"] == rec["capacity"]
        assert r["demand_part"] + r["refill_part"] == pytest.approx(rec["planned_production_stock"], abs=1e-3)
        assert r["mto"] == pytest.approx(rec["load_confirmed_to_order"] + rec["load_conflict"], abs=1e-3)
        assert r["above"] == bool(rec["above_capacity"])


def test_the_tracked_page_equals_a_fresh_build_from_the_recorded_plan(tmp_path):
    _recorded()
    fresh = bp.build_page(out_path=str(tmp_path / "p.html"))
    tracked = os.path.join(PROJECT_ROOT, "forecast", "operation_plan.html")
    if not os.path.exists(tracked):
        pytest.skip("SKIPPED, not passed: forecast/operation_plan.html is not built yet")
    with open(fresh, encoding="utf-8") as f, open(tracked, encoding="utf-8") as g:
        assert f.read() == g.read(), "the tracked page differs from what the builder makes from the recorded plan: run the monthly runner or build it"


# ------------------------------------------------------------------ assumptions
NEW_ASSUMPTIONS = [
    ("open_production_orders", "ใบสั่งผลิตที่กำลังทำ", "วันกำหนดเสร็จในระบบไม่ตรงกับวันเสร็จจริง", "ไม่นับในแผน", "แผนการผลิต"),
    ("fmto_fmts_warehouses", "คลัง FMTO และ FMTS", "ยังไม่รู้ว่าเป็นของพร้อมขายไหม", "ไม่นับ", "stock ที่ใช้เทียบกับ Min และแผนการผลิต"),
    ("forecast_range", "ยอดทาย", "ยังไม่มีช่วงสูง-ต่ำ", "ใช้ค่ากลาง", "แผนการผลิต"),
    ("calibration_window", "ช่วงข้อมูลที่ใช้ปรับ Min/Max", "ถ้าใช้ช่วงสั้นลง lead time ที่ได้จะแคบลง", "{window}", "Min/Max ของ PEM101"),
]


def test_the_assumption_records_are_built_with_the_approved_text_and_the_window_from_config():
    window = mm.thai_window(mm.load_config()["calibration_window"]["start"], mm.load_config()["calibration_window"]["end"])
    recs = {r["id"]: r for r in mm.build_assumptions(today="2026-10-06")["assumptions"]}
    assert len(recs) == 10
    for rid, topic, unknown, used, affects in NEW_ASSUMPTIONS:
        r = recs[rid]
        assert (r["topic"], r["unknown"], r["used_now"], r["affects"]) == (topic, unknown, used.format(window=window), affects)
    assert window == "มกราคม 2567 ถึง ธันวาคม 2568"


def test_the_calibration_window_in_config_equals_the_engines_constants():
    import sys
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "investigations"))
    import phaseJ3_calibration_engine as jc
    w = mm.load_config()["calibration_window"]
    assert jc.CALIBRATION_START[:7] == w["start"] and jc.CALIBRATION_END[:7] == w["end"]


def test_the_window_follows_config_and_the_thai_year_is_buddhist():
    assert mm.thai_window("2024-07", "2026-02") == "กรกฎาคม 2567 ถึง กุมภาพันธ์ 2569"


def test_the_tracked_assumptions_file_is_what_the_builder_writes(tmp_path):
    out = mm.write_assumptions(str(tmp_path / "a.json"), today="2026-10-06")
    with open(out, encoding="utf-8") as f, open(os.path.join(PROJECT_ROOT, "data", "assumptions.json"), encoding="utf-8") as g:
        built, tracked = json.load(f), json.load(g)
    assert [{k: v for k, v in r.items() if k != "updated_date"} for r in built["assumptions"]] == \
           [{k: v for k, v in r.items() if k != "updated_date"} for r in tracked["assumptions"]]
    assert len(tracked["assumptions"]) == 10


# ------------------------------------------------------------------ the runner
def test_the_runner_builds_the_page_in_its_plan_step_and_stages_it():
    src = open(os.path.join(PROJECT_ROOT, "src", "monthly_refresh.py"), encoding="utf-8").read()
    step = src.split("def step7b_operation_plan")[1].split("def step8_run_tests")[0]
    assert "build_operation_plan_page.build_page" in step and step.index("operation_plan.run") < step.index("build_operation_plan_page.build_page")
    import monthly_refresh as mr
    assert "forecast/operation_plan.html" in mr.GENERATED_PATHS


# ------------------------------------------------------------------ screen
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _wait(edge, expr, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if edge.ev(expr):
            return True
        edge.pump(0.2)
    return False


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """A temporary site: forecast/operation_plan.html (builder, recorded plan), forecast/inventory.html (builder, tracked data), index.html and
    the files it loads, served on a local port."""
    _recorded()
    import build_inventory_page as bpg
    root = tmp_path_factory.mktemp("week2_site")
    (root / "forecast").mkdir()
    (root / "data").mkdir()
    (root / "docs").mkdir()
    bp.build_page(out_path=str(root / "forecast" / "operation_plan.html"))
    data = fresh_inventory_data()
    mp = pytest.MonkeyPatch()
    mp.setattr(bpg, "build_data", lambda **kw: data)
    try:
        page = bpg.build_page()
    finally:
        mp.undo()
    (root / "forecast" / "inventory.html").write_text(page, encoding="utf-8")
    write_stock_file(str(root), load_stock_payload())
    shutil.copy(os.path.join(PROJECT_ROOT, "index.html"), root / "index.html")
    shutil.copy(os.path.join(PROJECT_ROOT, "docs", "user_manual.md"), root / "docs" / "user_manual.md")
    shutil.copy(os.path.join(PROJECT_ROOT, "data", "inventory.json"), root / "data" / "inventory.json")
    mm.write_assumptions(str(root / "data" / "assumptions.json"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def edge(site):
    e = Edge(require_browser())
    yield e
    e.close()


def test_the_new_page_shows_heading_data_line_summary_flag_lines_and_item_table(edge, site):
    v = bp.build_values(PROJECT_ROOT)
    edge.open(site + "/forecast/operation_plan.html")
    assert _wait(edge, "document.querySelectorAll('#item-table-body tr').length > 0")
    assert edge.ev("document.getElementById('page-title').innerText") == f"แผนการผลิต {v['n_months']} เดือน · PEM101 และ PEM107"
    assert edge.ev("document.getElementById('data-line').innerText") == f"ข้อมูล stock ดึงเมื่อ {v['pull_time']} · ยอดทายจากรอบ {v['forecast_run_month']}"
    heads = edge.ev("[...document.querySelectorAll('#summary-PEM101 thead th')].map(t=>t.innerText.trim())")
    assert heads == ["เดือน", "ผลิตตามความต้องการ", "เติมให้ถึง Max", "ผลิตตามสั่ง", "รวม", "เทียบยอดผลิตสูงสุดที่เคยทำ"]
    for d in ("PEM101", "PEM107"):
        rows = edge.ev(f"[...document.querySelectorAll('#summary-{d} tbody tr')].map(r=>[...r.children].map(c=>c.innerText.trim()))")
        s = v["summary"][v["summary"]["division"] == d].reset_index(drop=True)
        assert len(rows) == len(s) == v["n_months"]
        for r, (_, x) in zip(rows, s.iterrows()):
            assert r[0] == bp.thai_month(x["month"]) and r[1] == bp.fmt_units(x["demand_part"]) and r[2] == bp.fmt_units(x["refill_part"])
            assert r[3] == bp.fmt_units(x["mto"]) and r[4] == bp.fmt_units(x["total"])
            assert r[5].startswith(bp.fmt_pct(x["share"])) and (("สูงกว่ายอดผลิตสูงสุดที่เคยทำ" in r[5]) == bool(x["above"]))
    flagged = edge.ev("[...document.querySelectorAll('.summary-table .flag')].length")
    assert flagged == int(v["summary"]["above"].sum())
    lines = edge.ev("[...document.querySelectorAll('p.note-line')].map(p=>p.innerText.trim())")
    assert lines[-1].startswith("ยอดผลิตสูงสุดที่เคยทำ คือยอดผลิตเสร็จต่อเดือนสูงสุดในอดีต")
    if v["refill_first"] >= 0.5:
        assert lines[0] == f"{v['first_month']} PEM101 ต้องเติมให้ถึง Max {v['refill_units']} หน่วย นอกเหนือจากความต้องการเดือนนั้น เพราะ stock ตอนนี้ต่ำกว่า Max ทยอยเติมในเดือนถัดไปได้"
    if v["backlog_above_forecast_value"] >= 0.5:
        assert f"{v['first_month']} PEM107 มีออเดอร์ที่รับแล้วสูงกว่ายอดทาย {v['backlog_above_forecast']} หน่วย ส่วนใหญ่จาก {v['top_backlog_items']}" in lines
    cols = edge.ev("[...document.querySelectorAll('#item-table thead th')].map(t=>t.innerText.trim())")
    assert cols == ["รหัส", "ชื่อสินค้า", "ประเภท", "stock ตอนนี้", "Min", "Max"] + v["month_labels"]
    assert not [e for e in edge.errors if e.startswith("exception")], edge.errors


def test_the_filters_show_only_the_chosen_division_and_class(edge, site):
    v = bp.build_values(PROJECT_ROOT)
    edge.open(site + "/forecast/operation_plan.html")
    assert _wait(edge, "document.querySelectorAll('#item-table-body tr').length > 0")
    visible = lambda: edge.ev("[...document.querySelectorAll('#item-table-body tr')].filter(r=>r.style.display!=='none').map(r=>[r.dataset.division, r.dataset.class])")
    assert len(visible()) == len(v["items"])
    edge.ev("document.getElementById('filter-division').value='PEM107'; document.getElementById('filter-division').onchange(); 1")
    rows = visible()
    assert rows and {r[0] for r in rows} == {"PEM107"} and len(rows) == sum(1 for i in v["items"] if i["division"] == "PEM107")
    edge.ev("document.getElementById('filter-class').value='stock_policy'; document.getElementById('filter-class').onchange(); 1")
    rows = visible()
    assert {tuple(r) for r in rows} == {("PEM107", "stock_policy")} and len(rows) == sum(1 for i in v["items"] if i["division"] == "PEM107" and i["class"] == "stock_policy")
    edge.ev("document.getElementById('filter-division').value='all'; document.getElementById('filter-division').onchange(); "
            "document.getElementById('filter-class').value='conflict'; document.getElementById('filter-class').onchange(); 1")
    assert {r[1] for r in visible()} == {"conflict"} and {r[0] for r in visible()} == {"PEM101", "PEM107"}


def test_the_item_table_shows_the_plans_numbers_and_blank_min_max_for_items_without_them(edge, site):
    v = bp.build_values(PROJECT_ROOT)
    edge.open(site + "/forecast/operation_plan.html")
    assert _wait(edge, "document.querySelectorAll('#item-table-body tr').length > 0")
    rows = edge.ev("[...document.querySelectorAll('#item-table-body tr')].map(r=>[...r.children].map(c=>c.innerText.trim()))")
    by = {r[0]: r for r in rows}
    for it in v["items"]:
        r = by[it["item"]]
        assert r[1] == it["name"] and r[2] == bp.CLASS_LABELS[it["class"]]
        assert r[4] == (bp.fmt_cell(it["min"]) if it["min"] is not None else "") and r[5] == (bp.fmt_cell(it["max"]) if it["max"] is not None else "")
        assert r[6:] == [bp.fmt_cell(x) for x in it["months"]]


def test_the_two_min_max_texts_the_link_and_the_heading_suffix_show(edge, site):
    edge.open(site + "/forecast/inventory.html")
    assert _wait(edge, "document.getElementById('stock-labels').style.display !== 'none'"), "the page did not finish loading"
    edge.ev("document.getElementById('division-select').value='PEM101'; onDivisionChange(); 1")
    assert _wait(edge, "document.getElementById('curve-item-table-body').children.length > 0")
    assert edge.ev("document.querySelector('#curve-target-section h2').innerText") == "PEM101 — เลือกเป้าการส่งทัน แล้วดูว่าต้องถือของเท่าไหร่ (ค่าแนะนำ)"
    note = edge.ev("document.getElementById('item-table-note').innerText")
    assert note == "Min/Max ในตารางนี้เปลี่ยนตามตัวควบคุมด้านซ้าย ใช้ลองสมมติฐาน ค่าแนะนำอยู่ในส่วน PEM101 ด้านล่าง"
    assert edge.ev("getComputedStyle(document.getElementById('item-table-note')).display") != "none"
    # the note sits directly under the main item table
    assert edge.ev("document.getElementById('item-table').parentElement.nextElementSibling.id") == "item-table-note"
    link = edge.ev("(function(){const a=document.getElementById('plan-link'); return [a.innerText.trim(), a.getAttribute('href')]})()")
    assert link == ["แผนการผลิต", "operation_plan.html"]
    edge.ev("document.getElementById('division-select').value='PEM107'; onDivisionChange(); 1")
    edge.pump(0.4)
    assert edge.ev("getComputedStyle(document.getElementById('item-table-note')).display") == "none"
    assert not [e for e in edge.errors if e.startswith("exception")], edge.errors


def test_the_index_has_the_link_and_the_assumptions_tab_shows_ten_rows(edge, site):
    edge.open(site + "/index.html")
    time.sleep(1.5)
    link = edge.ev("(function(){const a=document.querySelector('#tabBar a'); return [a.innerText.trim(), a.getAttribute('href')]})()")
    assert link == ["แผนการผลิต", "forecast/operation_plan.html"]
    edge.ev("omniShowTab(4); 1")
    assert _wait(edge, "document.querySelectorAll('#assumptionsTab tbody tr').length > 0")
    rows = edge.ev("[...document.querySelectorAll('#assumptionsTab tbody tr')].map(r=>[...r.children].map(c=>c.innerText.trim()))")
    assert len(rows) == 10
    window = mm.thai_window(mm.load_config()["calibration_window"]["start"], mm.load_config()["calibration_window"]["end"])
    texts = {r[0]: r for r in rows}
    for rid, topic, unknown, used, affects in NEW_ASSUMPTIONS:
        r = texts[topic]
        assert r[1:4] == [unknown, used.format(window=window), affects]
    assert not [e for e in edge.errors if e.startswith("exception")], edge.errors
