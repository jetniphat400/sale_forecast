"""The stock figures and their three dates on the two pages, run in a headless browser (own Edge, own temp profile, own PID).

Pages are built to a temporary site folder (forecast/inventory.html next to data/stock_daily.json, and a copy of index.html
beside the tracked data/inventory.json). No database, no tracked file is modified. With no browser available every test
here is SKIPPED with a message, never passed silently.
"""
import copy
import functools
import http.server
import json
import os
import shutil
import threading
import time

import pandas as pd
import pytest

from page_helpers import (Edge, PROJECT_ROOT, build_inventory_html, fresh_inventory_data, load_stock_payload, require_browser,
                          write_stock_file)

import inventory_recompute_reference as ref  # noqa: E402
import stock_daily as sd  # noqa: E402

FAIL_MSG = "โหลดข้อมูล stock ไม่ได้ · ตัวเลขอื่นในหน้านี้ยังใช้ได้ตามปกติ"
THAI = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def thai(s):
    """d MMM yy HH:mm with the Buddhist year, written independently of the page's own function."""
    t = pd.Timestamp(s)
    return f"{t.day} {THAI[t.month - 1]} {str(t.year + 543)[-2:]} {t.hour:02d}:{t.minute:02d}"


@pytest.fixture(scope="module")
def edge():
    e = Edge(require_browser())
    yield e
    e.close()


def _site(tmp_path_factory, name, stock):
    d = tmp_path_factory.mktemp(name)
    return build_inventory_html(str(d / "forecast" / "inventory.html"), stock=stock)


def _wait(edge, expr, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        if edge.ev(expr):
            return True
        edge.pump(0.2)
    return False


def _open(edge, path):
    edge.open(path)
    assert _wait(edge, "document.getElementById('stock-labels').style.display !== 'none'"), "the page did not finish loading its stock file"


def _first_cover_row(edge, division="PEM101"):
    """(code, months of cover text) of the first item-table row whose cover is a finite number above zero."""
    edge.ev(f"document.getElementById('division-select').value='{division}'; onDivisionChange(); 1")
    edge.pump(0.4)
    rows = edge.ev("[...document.querySelectorAll('#item-table-body tr')].map(r=>[r.children[0].textContent.trim(), r.children[8].textContent.trim()])")
    for code, cover in rows:
        try:
            if float(cover) > 0:
                return code, float(cover)
        except ValueError:
            continue
    pytest.fail("no item with a finite cover above zero in the item table")


# ------------------------------------------------------------------ figures come from the stock file
def test_stock_figures_follow_the_stock_file_not_the_page(edge, tmp_path_factory):
    base = load_stock_payload()
    doubled = copy.deepcopy(base)
    for rows in doubled["items"].values():
        for r in rows:
            r[1] = r[1] * 2
    results = {}
    for name, payload in (("one", base), ("two", doubled)):
        _open(edge, _site(tmp_path_factory, f"stock_{name}", payload))
        results[name] = _first_cover_row(edge)
        assert not [x for x in edge.errors if x.startswith("exception")], edge.errors
    (c1, v1), (c2, v2) = results["one"], results["two"]
    assert c1 == c2
    assert v2 == pytest.approx(2 * v1, abs=0.15), f"months of cover did not follow the stock file: {v1} then {v2}"


def test_the_excess_count_equals_the_python_reference_for_the_same_stock_file(edge, tmp_path_factory):
    payload = load_stock_payload()
    path = _site(tmp_path_factory, "stock_excess", payload)
    _open(edge, path)
    data = sd.apply_to_data(fresh_inventory_data(), payload)
    controls = {"procurement_lead_time_days": 60, "assembly_time_days": 3, "review_interval_days": 30, "cycle_service_level": 0.95,
                "holding_cost_rate_annual": 0.2, "obsolescence_threshold_months": 6}
    for division in ("PEM101", "PEM103", "PEM107"):
        edge.ev(f"document.getElementById('division-select').value='{division}'; onDivisionChange(); 1")
        edge.pump(0.4)
        for k, v in controls.items():
            edge.ev(f"(function(){{var e=document.getElementById('ctrl-{k}'); e.value={v}; e.dispatchEvent(new Event('input')); return 1}})()")
        edge.pump(0.3)
        expected = ref.compute_all(data["divisions"][division], controls, data["days_per_month"])["excess_count"]
        assert edge.ev("document.getElementById('tot-excess-count').textContent.trim()") == str(expected), division


# ------------------------------------------------------------------ the three dates
def test_the_three_labels_show_the_values_in_the_stock_file(edge, tmp_path_factory):
    payload = load_stock_payload()
    payload = {**payload, "stock_source_load_time": "2026-10-04 21:41:03", "reserved_source_load_time": "2026-10-05 07:35:30",
               "pull_time": "2026-10-06 08:00:05"}
    _open(edge, _site(tmp_path_factory, "stock_labels", payload))
    assert edge.ev("document.getElementById('stock-label-stock').textContent") == "ข้อมูล stock ใน DB (Cube_Inventory_Exact) ณ " + thai(payload["stock_source_load_time"])
    assert edge.ev("document.getElementById('stock-label-reserved').textContent") == "ยอดจองใน DB (Cube_CES) ณ " + thai(payload["reserved_source_load_time"])
    assert edge.ev("document.getElementById('stock-label-pulled').textContent") == "ดึงข้อมูลเมื่อ " + thai(payload["pull_time"])
    assert thai("2026-10-04 21:41:03") == "4 ต.ค. 69 21:41"
    # the replaced labels are gone
    assert edge.ev("document.getElementById('stock-note')") is None
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors


@pytest.mark.parametrize("pull,reserved_at,old", [
    ("2026-10-06 08:00:05", "2026-10-05 21:00:00", False),       # Tuesday pull, source loaded the evening of the previous weekday (Monday): fresh
    ("2026-10-06 08:00:05", "2026-10-03 21:00:00", True),        # loaded on Saturday, before the previous weekday (Monday): old
    ("2026-10-12 08:00:05", "2026-10-09 21:00:00", False),       # Monday pull, source loaded on the Friday before: fresh (the previous weekday of a Monday is the Friday)
    ("2026-10-12 08:00:05", "2026-10-08 21:00:00", True),        # Monday pull, source loaded on the Thursday: old
])
def test_the_reserved_date_is_old_when_it_is_before_the_previous_weekday_of_the_pull(edge, tmp_path_factory, pull, reserved_at, old):
    base = load_stock_payload()
    stock_at = str(pd.Timestamp(pull) - pd.Timedelta(hours=11))[:19]
    p = {**base, "pull_time": pull[:19], "stock_source_load_time": stock_at, "reserved_source_load_time": reserved_at}
    _open(edge, _site(tmp_path_factory, "stock_age_" + pull[:10] + reserved_at[:10], p))
    reserved = edge.ev("document.getElementById('stock-label-reserved').parentElement.textContent")
    stock = edge.ev("document.getElementById('stock-label-stock').parentElement.textContent")
    assert ("ข้อมูลเก่า ดึงก่อนวันทำการก่อนหน้า" in reserved) == old
    # the reserved age is judged on its own: the stock line (loaded 11 hours before the pull) has no notice in any of the cases
    assert reserved.count("ข้อมูลเก่า") == (1 if old else 0)                       # the container of both labels holds the one notice, after the reserved label
    if old:
        assert reserved.index("ข้อมูลเก่า") > reserved.index("ยอดจองใน DB (Cube_CES)")
    assert "ข้อมูลเก่า" not in stock.split("ยอดจองใน DB")[0]                             # nothing after the stock label and before the reserved one


# ------------------------------------------------------------------ the file cannot be loaded
@pytest.mark.parametrize("how", ["missing", "malformed", "wrong_format"])
def test_when_the_stock_file_cannot_load_the_page_says_so_and_everything_else_works(edge, tmp_path_factory, how):
    stock = None if how == "missing" else load_stock_payload()
    path = _site(tmp_path_factory, f"stock_fail_{how}", stock)
    site = os.path.dirname(os.path.dirname(path))
    target = os.path.join(site, "data", "stock_daily.json")
    if how == "malformed":
        with open(target, "w", encoding="utf-8") as f:
            f.write("{not json")
    elif how == "wrong_format":
        with open(target, "w", encoding="utf-8") as f:
            json.dump({"format_version": 99, "items": {}}, f)
    _open(edge, path)
    assert edge.ev("document.getElementById('stock-labels').textContent.trim()") == FAIL_MSG
    assert edge.ev("document.getElementById('tot-excess-count').textContent.trim()") == "–"
    # figures that need no stock still render: Min and Max, the stock value in THB, the item table
    assert edge.ev("document.getElementById('tot-stock-value').textContent.trim()") not in ("", "-")
    rows = edge.ev("[...document.querySelectorAll('#item-table-body tr')].map(r=>[r.children[4].textContent.trim(), r.children[5].textContent.trim(), "
                   "r.children[8].textContent.trim(), r.children[10].textContent.trim()])")
    assert rows and any(r[0] not in ("-", "") and r[1] not in ("-", "") for r in rows), "Min and Max are blank when the stock file fails"
    assert all(r[2] == "–" and r[3] == "–" for r in rows), "stock-dependent cells must not show a number without stock"
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors


# ------------------------------------------------------------------ the index stock panel
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def index_site(tmp_path_factory):
    site = tmp_path_factory.mktemp("index_site")
    shutil.copy(os.path.join(PROJECT_ROOT, "index.html"), site / "index.html")
    (site / "data").mkdir()
    shutil.copy(os.path.join(PROJECT_ROOT, "data", "inventory.json"), site / "data" / "inventory.json")
    handler = functools.partial(_Quiet, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/index.html", site
    server.shutdown()


def test_the_index_panel_shows_the_three_dates_from_its_data_file(edge, index_site):
    url, site = index_site
    with open(site / "data" / "inventory.json", encoding="utf-8") as f:
        inv = json.load(f)
    edge.open(url)
    edge.ev("document.getElementById('invMenuRow').click(); 1")
    assert _wait(edge, "document.getElementById('invContent') && document.getElementById('invContent').style.display !== 'none'", 30), "stock panel did not load"
    pulled = (pd.Timestamp(inv["snapshot"]["generated_at"]).tz_convert("Asia/Bangkok")).tz_localize(None)
    assert edge.ev("document.getElementById('invSnapshotLabel').textContent") == "ข้อมูล stock ใน DB (Cube_Inventory_Exact) ณ " + thai(inv["snapshot"]["loaded_at"])
    assert edge.ev("document.getElementById('invBacklogLabel').textContent").startswith("ยอดจองใน DB (Cube_CES) ณ " + thai(inv["backlog"]["loaded_at"]))
    assert edge.ev("document.getElementById('invPageTimestampNote').textContent") == "ดึงข้อมูลเมื่อ " + thai(pulled)
    shown = edge.ev("document.getElementById('invSnapshotLabel').textContent + document.getElementById('invBacklogLabel').textContent")
    assert "รอบการอัปเดต" not in shown and "คนละรอบการโหลด" not in shown, "a load schedule is stated on the panel"
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors
