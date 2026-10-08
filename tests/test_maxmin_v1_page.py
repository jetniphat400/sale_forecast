"""Max-Min v1 on the two pages, run in a headless browser (own Edge on a temp profile, own PID; only that PID is closed).

forecast/inventory.html is built to a temporary site folder by the page builder (no database); index.html is copied beside a copy of
data/assumptions.json and served from a local port, so the tab's runtime fetch is exercised. No tracked file is modified. With no
browser, or without the recorded outputs, a test is SKIPPED with a message, never passed silently.
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

from page_helpers import Edge, PROJECT_ROOT, fresh_inventory_data, load_stock_payload, require_browser, write_stock_file

import maxmin_v1 as mm  # noqa: E402

CFG = mm.load_config()
LINE_1 = "Min/Max คำนวณจาก lead time ที่ทำให้การจำลองส่งของทันและถือ stock ใกล้เคียงของจริงที่สุด อยู่ระหว่าง {lead_min} ถึง {lead_max} วัน"
LINE_2 = "lead time วัตถุดิบจากใบสั่งซื้อจริง ค่ากลาง {median_observed} วัน (มีข้อมูล {n_observed} จาก {n_items} รายการ) ใช้สำหรับวางแผนสั่งวัตถุดิบ ไม่ได้ใช้คำนวณ Min/Max ของสินค้า"
HEADERS = ["lead time วัตถุดิบ (วัน)", "ที่มา"]
LABELS = {"ใบสั่งซื้อจริง", "ผู้ขายแจ้ง", "ค่าประมาณ"}
INTRO = "ตัวเลขบางส่วนในระบบใช้ค่าแทนเพราะข้อมูลยังบอกไม่ได้ ตารางนี้บอกว่าใช้อะไรแทน และกระทบตัวเลขไหน"
FAIL = "โหลดรายการสมมติฐานไม่ได้"
TRACKED_ASSUMPTIONS = os.path.join(PROJECT_ROOT, "data", "assumptions.json")


@pytest.fixture(scope="module")
def edge():
    for rel in (CFG["item_lead_time_file"], CFG["dense_grid_file"], CFG["ensemble_members_file"]):
        if not os.path.exists(mm.path_of(rel)):
            pytest.skip("SKIPPED, not passed: recorded output missing on this machine: " + rel)
    e = Edge(require_browser())
    yield e
    e.close()


def _wait(edge, expr, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if edge.ev(expr):
            return True
        edge.pump(0.2)
    return False


def _fmt(v):
    return f"{float(v):g}"


# ------------------------------------------------------------------ forecast/inventory.html, PEM101 calibrated section
def _build(tmp_path_factory, name, mutate=None):
    """Builds the inventory page with the builder to a temporary site (with the tracked stock file beside it); mutate(data) edits the data first."""
    import build_inventory_page as bp
    d = tmp_path_factory.mktemp(name)
    data = fresh_inventory_data()
    if mutate:
        mutate(data)
    mp = pytest.MonkeyPatch()
    mp.setattr(bp, "build_data", lambda **kw: data)
    try:
        page = bp.build_page()
    finally:
        mp.undo()
    out = d / "forecast" / "inventory.html"
    out.parent.mkdir(parents=True)
    out.write_text(page, encoding="utf-8")
    write_stock_file(str(d), load_stock_payload())
    return str(out), data


def _open_inventory(edge, path):
    edge.open(path)
    assert _wait(edge, "document.getElementById('stock-labels').style.display !== 'none'"), "the page did not finish loading"
    edge.ev("document.getElementById('division-select').value='PEM101'; onDivisionChange(); 1")
    edge.pump(0.5)
    assert _wait(edge, "document.getElementById('curve-item-table-body').children.length > 0"), "the calibrated section did not render"


def test_both_lines_and_the_corrected_item_count_show_in_the_pem101_section(edge, tmp_path_factory):
    path, data = _build(tmp_path_factory, "inv")
    _open_inventory(edge, path)
    members = pd.read_csv(mm.path_of(CFG["ensemble_members_file"]))
    lead = pd.read_csv(mm.path_of(CFG["item_lead_time_file"]))
    lines = edge.ev("document.getElementById('curve-lead-lines').innerText").split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    expected = [LINE_1.format(lead_min=int(members["lead_time_days"].min()), lead_max=int(members["lead_time_days"].max())),
                LINE_2.format(median_observed=_fmt(lead.loc[lead["bottleneck_source"] == "observed", "bottleneck_days"].median()),
                              n_observed=int((lead["bottleneck_source"] == "observed").sum()), n_items=len(lead))]
    assert lines == expected
    summary = edge.ev("document.getElementById('curve-target-summary').innerText")
    n = len(lead)
    assert f"ปรับให้ตรงกับผลจริงจากสินค้า {n} รายการ" in summary and "76" not in summary
    assert f"ใช้ชุดค่าที่เป็นไปได้ {len(members)} ชุด" in summary
    assert "ยังไม่ได้ปรับใหม่" not in summary
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors


def test_the_item_table_has_the_two_columns_with_each_items_value_and_source(edge, tmp_path_factory):
    path, data = _build(tmp_path_factory, "inv_cols")
    _open_inventory(edge, path)
    heads = edge.ev("[...document.querySelectorAll('#curve-item-table thead th')].map(t=>t.textContent.trim())")
    assert heads[-2:] == HEADERS and len(heads) == 6
    rows = edge.ev("[...document.querySelectorAll('#curve-item-table-body tr')].map(r=>[...r.children].map(c=>c.textContent.trim()))")
    lead = pd.read_csv(mm.path_of(CFG["item_lead_time_file"])).set_index("item")
    labels = CFG["material_source_labels"]
    assert len(rows) == len(lead) == 92 and all(len(r) == 6 for r in rows)
    shown = {}
    for r in rows:
        code, days, source = r[0], r[4], r[5]
        assert days == _fmt(lead.loc[code, "bottleneck_days"]), code
        assert source == labels[lead.loc[code, "bottleneck_source"]], code
        if bool(lead.loc[code, "no_bom"]):
            assert source == "ค่าประมาณ", f"{code} has no walkable BOM"
        shown[source] = shown.get(source, 0) + 1
    assert shown == {labels[k]: int(v) for k, v in lead["bottleneck_source"].value_counts().items()}
    assert set(shown) <= LABELS


def test_all_three_source_labels_render_when_each_occurs(edge, tmp_path_factory):
    """The recorded data holds no supplier-quoted bottleneck today, so two items' sources are set in the page's data to prove the label renders."""
    def mutate(data):
        m = data["divisions"]["PEM101"]["curve_target"]["item_material_lead"]
        a, b = sorted(m)[:2]
        m[a] = {"days": 12.5, "source": "ผู้ขายแจ้ง"}
        m[b] = {"days": 40.0, "source": "ใบสั่งซื้อจริง"}
        m[sorted(m)[2]] = {"days": 63.0, "source": "ค่าประมาณ"}
    path, data = _build(tmp_path_factory, "inv_three", mutate)
    _open_inventory(edge, path)
    rows = edge.ev("[...document.querySelectorAll('#curve-item-table-body tr')].map(r=>[r.children[0].textContent.trim(), r.children[4].textContent.trim(), r.children[5].textContent.trim()])")
    by = {r[0]: r for r in rows}
    codes = sorted(by)[:3]
    assert by[codes[0]][1:] == ["12.5", "ผู้ขายแจ้ง"] and by[codes[1]][1:] == ["40", "ใบสั่งซื้อจริง"] and by[codes[2]][1:] == ["63", "ค่าประมาณ"]
    assert {r[2] for r in rows} >= LABELS


def test_the_controls_still_work_and_the_other_lines_are_unchanged(edge, tmp_path_factory):
    path, data = _build(tmp_path_factory, "inv_controls")
    _open_inventory(edge, path)
    ct = data["divisions"]["PEM101"]["curve_target"]
    for button, key in (("preset-today-lowest", "today_lowest_stock"), ("preset-highest-at-today", "highest_at_today_stock"), ("preset-stretch", "stretch_99pct")):
        edge.ev(f"document.getElementById('{button}').click(); 1")
        edge.pump(0.3)
        shown = float(edge.ev("document.getElementById('notlate-slider-value').textContent.replace('%','')"))
        assert shown == pytest.approx(ct["presets"][key]["not_late_pct"], abs=0.01)
        assert edge.ev("document.getElementById('curve-item-table-body').children.length") == 92
        assert "ต้องเพิ่ม stock" in edge.ev("document.getElementById('relative-service-cost-note').textContent") or \
               "ลด stock" in edge.ev("document.getElementById('relative-service-cost-note').textContent")
    assert edge.ev("document.getElementById('curve-lead-lines').innerText.includes('อยู่ระหว่าง')")
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors


# ------------------------------------------------------------------ index.html, the assumptions tab
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _serve(site):
    handler = functools.partial(_Quiet, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/index.html"


def _site(tmp_path_factory, name, assumptions="tracked"):
    site = tmp_path_factory.mktemp(name)
    shutil.copy(os.path.join(PROJECT_ROOT, "index.html"), site / "index.html")
    (site / "data").mkdir()
    shutil.copy(os.path.join(PROJECT_ROOT, "data", "inventory.json"), site / "data" / "inventory.json")
    if assumptions == "tracked":
        shutil.copy(TRACKED_ASSUMPTIONS, site / "data" / "assumptions.json")
    elif assumptions is not None:
        (site / "data" / "assumptions.json").write_text(assumptions, encoding="utf-8")
    return site


def _open_tab(edge, url):
    edge.open(url)
    assert edge.ev("document.getElementById('tb4').textContent.trim()") == "สมมติฐานที่ใช้อยู่"
    edge.ev("document.getElementById('tb4').click(); 1")
    edge.pump(0.8)


def test_the_assumptions_tab_shows_the_ten_records_from_the_json(edge, tmp_path_factory):
    site = _site(tmp_path_factory, "idx_ok")
    server, url = _serve(site)
    try:
        _open_tab(edge, url)
        assert _wait(edge, "document.querySelectorAll('#assumptionsTable tbody tr').length > 0"), "the tab did not render its table"
        assert edge.ev("document.getElementById('assumptionsTab').style.display") == "block"
        assert edge.ev("document.getElementById('origTab').style.display") == "none"
        assert edge.ev("document.querySelector('#assumptionsTab .assump-intro').textContent.trim()") == INTRO
        heads = edge.ev("[...document.querySelectorAll('#assumptionsTable thead th')].map(t=>t.textContent.trim())")
        assert heads == ["เรื่อง", "ยังไม่รู้อะไร", "ตอนนี้ใช้", "กระทบ"]
        rows = edge.ev("[...document.querySelectorAll('#assumptionsTable tbody tr')].map(r=>[...r.children].map(c=>c.textContent.trim()))")
        payload = json.load(open(site / "data" / "assumptions.json", encoding="utf-8"))["assumptions"]
        assert rows == [[r["topic"], r["unknown"], r["used_now"], r["affects"]] for r in payload] and len(rows) == 10
        assert FAIL not in edge.ev("document.getElementById('assumptionsTabContent').textContent")
        # the other tabs still switch
        edge.ev("document.getElementById('tb3').click(); 1")
        assert edge.ev("document.getElementById('assumptionsTab').style.display") == "none"
        assert edge.ev("document.getElementById('manualTab').style.display") == "block"
        assert not [x for x in edge.errors if x.startswith("exception")], edge.errors
    finally:
        server.shutdown()


def test_the_tab_follows_the_json_it_loads(edge, tmp_path_factory):
    payload = json.load(open(TRACKED_ASSUMPTIONS, encoding="utf-8"))
    payload["assumptions"] = payload["assumptions"][:2]
    payload["assumptions"][0]["used_now"] = "9-99 วัน"
    site = _site(tmp_path_factory, "idx_changed", assumptions=json.dumps(payload, ensure_ascii=False))
    server, url = _serve(site)
    try:
        _open_tab(edge, url)
        assert _wait(edge, "document.querySelectorAll('#assumptionsTable tbody tr').length > 0")
        rows = edge.ev("[...document.querySelectorAll('#assumptionsTable tbody tr')].map(r=>r.children[2].textContent.trim())")
        assert rows == ["9-99 วัน", payload["assumptions"][1]["used_now"]]
    finally:
        server.shutdown()


@pytest.mark.parametrize("name,content", [("missing", None), ("not_json", "this is not json"), ("wrong_shape", json.dumps({"assumptions": [{"topic": 5}]}))])
def test_the_tab_shows_the_failure_message_when_the_json_cannot_load(edge, tmp_path_factory, name, content):
    site = _site(tmp_path_factory, "idx_" + name, assumptions=content)
    server, url = _serve(site)
    try:
        _open_tab(edge, url)
        assert _wait(edge, f"document.getElementById('assumptionsTabContent').textContent.includes('{FAIL}')"), "no failure message"
        assert edge.ev("document.getElementById('assumptionsTable')") is None
        assert edge.ev("document.getElementById('assumptionsTabContent').textContent.trim()") == FAIL
    finally:
        server.shutdown()


# ------------------------------------------------------------------ 2026-10-09: the table "เกณฑ์ที่รอกำหนด" under the assumptions table
def test_the_criteria_table_shows_its_heading_columns_and_eight_approved_rows_under_the_first_table(edge, tmp_path_factory):
    from test_maxmin_v1 import PENDING_HEADS, _pending_expected
    expected, _values = _pending_expected()
    site = _site(tmp_path_factory, "idx_pending")
    server, url = _serve(site)
    try:
        _open_tab(edge, url)
        assert _wait(edge, "document.querySelectorAll('#pendingCriteriaTable tbody tr').length > 0"), "the criteria table did not render"
        assert edge.ev("document.getElementById('pendingCriteriaHeading').textContent.trim()") == "เกณฑ์ที่รอกำหนด"
        assert edge.ev("[...document.querySelectorAll('#pendingCriteriaTable thead th')].map(t=>t.textContent.trim())") == PENDING_HEADS
        rows = edge.ev("[...document.querySelectorAll('#pendingCriteriaTable tbody tr')].map(r=>[...r.children].map(c=>c.textContent.trim()))")
        assert rows == expected and len(rows) == 8
        text = edge.ev("document.getElementById('pendingCriteriaTable').innerText")
        assert "{" not in text and "}" not in text and "ร่าง: ต่ำกว่า 1 ผ่าน, ต่ำกว่า 0.7 ดี" in text and "ร่าง: ±4" in text and "หลังรอบ 5 ธ.ค. 69" in text
        # it sits below the first table, after its own heading, and the first table is unchanged (ten rows)
        order = edge.ev("(function(){var a=document.getElementById('assumptionsTable'), h=document.getElementById('pendingCriteriaHeading'), b=document.getElementById('pendingCriteriaTable');"
                        "return [a.compareDocumentPosition(h) & 4, h.compareDocumentPosition(b) & 4, document.querySelectorAll('#assumptionsTable tbody tr').length]})()")
        assert order == [4, 4, 10]
        assert not [x for x in edge.errors if x.startswith("exception")], edge.errors
    finally:
        server.shutdown()


def test_a_file_without_the_criteria_rows_shows_the_failure_message_not_half_a_tab(edge, tmp_path_factory):
    payload = json.load(open(TRACKED_ASSUMPTIONS, encoding="utf-8"))
    del payload["pending_criteria"]
    site = _site(tmp_path_factory, "idx_nopending", assumptions=json.dumps(payload, ensure_ascii=False))
    server, url = _serve(site)
    try:
        _open_tab(edge, url)
        assert _wait(edge, f"document.getElementById('assumptionsTabContent').textContent.includes('{FAIL}')"), "no failure message"
        assert edge.ev("document.getElementById('pendingCriteriaTable')") is None
    finally:
        server.shutdown()
