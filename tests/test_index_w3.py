"""Phase W3: index.html's approved texts, the Trend tab's three computed values, the embedded data left untouched, and the
sales report's significance sentence.

Browser tests run in an own headless Edge (own temp profile, own PID) against a temporary copy of what index.html loads
at runtime (the page, the manual, data/inventory.json) served from a local port; no tracked file is modified. With no
browser available they are SKIPPED with a message, never passed silently.
"""
import functools
import hashlib
import http.server
import json
import os
import re
import shutil
import threading
import time

import pandas as pd
import pytest

from page_helpers import Edge, PROJECT_ROOT, require_browser

INDEX = os.path.join(PROJECT_ROOT, "index.html")
THAI = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

# The S&OP tab's original-file figures are a documented exception to CONVENTIONS.md "Dynamic values" until phase S
# rebuilds that tab from the database. The exception holds only while the tab carries the notice below.
SOP_NOTICE = ("ตัวเลขในแท็บนี้มาจากไฟล์ที่ทำไว้ครั้งเดียวเพื่อแสดงโครงแผน S&OP ไม่อัปเดต และตรวจกับระบบแล้วยืนยันไม่ได้ "
              "ห้ามใช้ตัดสินใจ · ม.ค.-ก.ค. = ช่วงที่ผ่านมา · ส.ค.-ธ.ค. = แผน")
AVAILABLE_NOTE = "ของที่หยิบส่งได้จริง ≈ Sellable − Reserved (Available ยังนับคลัง QA ด้วย)"

# SHA-256 of the two embedded data lines of the Trend tab (const MATCH = ..., const OMNI = ...) as they were before
# phase W3, which changed text and labels only. A change to either line changes the hash.
EMBEDDED_DATA_SHA256 = {"MATCH": "2d163e487a42c4909cd79fd14d3e00f41bb1a4c9709427f366e6b366c01018ad",
                        "OMNI": "e4504ed7eebec5e872b804f1f9b2dd99ba9fde47453bb24c8b6384fd5f5a581a"}


def _embedded_lines(text):
    return {name: next(l for l in text.splitlines() if l.startswith(f"const {name} = ")) for name in ("MATCH", "OMNI")}


def _thai_date(yymmdd):
    y, m, d = 2000 + yymmdd // 10000, yymmdd // 100 % 100, yymmdd % 100
    return f"{d} {THAI[m - 1]} {str(y + 543)[-2:]}"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _serve(site):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/index.html"


def _site(tmp_path_factory, name, index_text=None, inventory=None):
    site = tmp_path_factory.mktemp(name)
    (site / "docs").mkdir()
    (site / "data").mkdir()
    if index_text is None:
        shutil.copy(INDEX, site / "index.html")
    else:
        (site / "index.html").write_text(index_text, encoding="utf-8", newline="")
    shutil.copy(os.path.join(PROJECT_ROOT, "docs", "user_manual.md"), site / "docs" / "user_manual.md")
    if inventory is None:
        shutil.copy(os.path.join(PROJECT_ROOT, "data", "inventory.json"), site / "data" / "inventory.json")
    else:
        (site / "data" / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    return site


def _wait(edge, expr, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if edge.ev(expr):
            return True
        time.sleep(0.4)
    return False


@pytest.fixture(scope="module")
def edge():
    e = Edge(require_browser())
    yield e
    e.close()


@pytest.fixture(scope="module")
def page(edge, tmp_path_factory):
    """Rendered text of every part of index.html, plus a few DOM facts."""
    site = _site(tmp_path_factory, "w3_page")
    server, url = _serve(site)
    out = {}
    try:
        edge.open(url)
        time.sleep(1.5)
        out["sop"] = edge.ev("document.getElementById('origTab').innerText")
        out["sop_badges"] = edge.ev("(function(){var r={};document.querySelectorAll('#itemTable .badge').forEach(function(b){r[b.textContent]=(r[b.textContent]||0)+1});return r})()")
        out["sop_labels"] = edge.ev("[...document.querySelectorAll('#origTab td.rowlabel')].map(c=>c.textContent.trim())")
        out["sop_legend"] = edge.ev("[...document.querySelectorAll('#origTab .legend-row > span')].map(e => e.textContent.trim()).join(' | ')")
        out["sop_first"] = edge.ev("[...document.getElementById('origTab').querySelector('.wrap').children].find(e => e.tagName !== 'STYLE').className")
        edge.ev("omniShowTab(2); 1")
        assert _wait(edge, "document.getElementById('trendDataNote').style.display === 'block'"), "the Trend note did not appear"
        out["trend"] = edge.ev("document.getElementById('omniTab').innerText")
        out["trend_first"] = edge.ev("[...document.getElementById('omniTab').children].find(e => e.tagName !== 'STYLE').id")
        out["trend_spans"] = edge.ev("['trendLastDate','trendCodeCount','currentCodeCount'].map(i=>document.getElementById(i).textContent)")
        out["trend_head"] = edge.ev("document.querySelector('#omniTab h2').innerText")
        out["trend_head_count"] = edge.ev("document.getElementById('trendHeadCount').textContent")
        out["n31_spans"] = edge.ev("[...document.querySelectorAll('.omni-n31')].map(e => e.textContent)")
        out["adi_title"] = edge.ev("document.querySelector('#skuTbl th[data-k=adi]').title")
        out["nosale_label"] = edge.ev("[...document.querySelectorAll('#fCls option')].map(o => o.textContent)")
        edge.ev("omniShowTab(3); 1")
        assert _wait(edge, "document.getElementById('manualTabContent').innerText.indexOf('กำลังโหลด') < 0"), "the manual did not load"
        out["manual"] = edge.ev("document.getElementById('manualTab').innerText")
        edge.ev("omniShowTab(1); document.getElementById('invMenuRow').click(); 1")
        assert _wait(edge, "document.getElementById('invContent').style.display === 'block'"), "the stock panel did not load"
        out["stock"] = edge.ev("document.getElementById('invPanel').innerText")
        out["avail_th"] = edge.ev("(function(){var th=document.querySelector('#invTable th[data-k=available]');return {text:th.innerText,note:th.querySelector('.inv-th-note').innerText}})()")
        out["errors"] = [e for e in edge.errors if e.startswith("exception")]
    finally:
        server.shutdown()
    return out


# ------------------------------------------------------------------ Part 1: S&OP tab
def test_sop_notice_is_first_in_the_tab_and_verbatim(page):
    assert page["sop"].lstrip().startswith(SOP_NOTICE)
    assert "sop-warning" in page["sop_first"]


def test_sop_residue_is_gone(page):
    for gone in ("ตามที่ขอให้เติมให้ครบ", "รอ logic", "ข้อมูลจริงจาก Cube Sale APD2026", "data_pulled_at", "page_built_at"):
        assert gone not in page["sop"], gone


def test_sop_badges_use_the_approved_labels(page):
    assert set(page["sop_badges"]) == {"มียอดขาย", "ไม่มียอดขาย", "จากไฟล์บริษัท", "ค่าประมาณจากสูตร"}, page["sop_badges"]
    # every product row carries one Data badge and one Inventory Source badge
    assert page["sop_badges"]["มียอดขาย"] + page["sop_badges"]["ไม่มียอดขาย"] == page["sop_badges"]["จากไฟล์บริษัท"] + page["sop_badges"]["ค่าประมาณจากสูตร"]


def test_sop_row_labels_and_section5_heading(page):
    labels = page["sop_labels"]
    assert "Employees (สมมติ)" in labels and "Inventory Actual (ล้านบาท, สมมติ)" in labels and "Customer Service % (สมมติ)" in labels
    assert "ที่มาตามไฟล์ต้นฉบับ (ตรวจสอบย้อนหลังไม่ได้)" in page["sop"]
    assert "แหล่งข้อมูลจริง" not in page["sop"]


# ------------------------------------------------------------------ Part 2: stock panel
def test_stock_panel_available_note_and_three_labels(page):
    assert page["avail_th"]["note"] == AVAILABLE_NOTE
    assert page["avail_th"]["text"].startswith("Available")
    assert re.search(r"ข้อมูล stock ในระบบ ณ \d{1,2} \S+ \d{2} \d{2}:\d{2}", page["stock"])
    assert re.search(r"ยอดจองในระบบ ณ \d{1,2} \S+ \d{2} \d{2}:\d{2}", page["stock"])
    assert re.search(r"ดึงข้อมูลเมื่อ \d{1,2} \S+ \d{2} \d{2}:\d{2}", page["stock"])
    for gone in ("Cube_", "task 2a", "DATA_MAP", "METRICS", "config.yaml", "inventory.json"):
        assert gone not in page["stock"], gone


# ------------------------------------------------------------------ Part 3: Trend tab
def test_trend_note_is_first_in_the_tab_and_follows_the_data(page):
    text = open(INDEX, encoding="utf-8").read()
    omni = json.loads(_embedded_lines(text)["OMNI"][len("const OMNI = "):].rstrip(";"))
    last = max(r[0] for it in omni["items"] for r in it["dd"])
    with open(os.path.join(PROJECT_ROOT, "data", "inventory.json"), encoding="utf-8") as f:
        current = json.load(f)["totals"]["codes"]
    expected = (f"ข้อมูลถึง {_thai_date(last)} ไม่อัปเดต · ใช้ Price List ฐาน {len(omni['items'])} รหัส "
                f"ต่างจากหน้าอื่นที่ใช้ {current} รหัส เทียบตัวเลขข้ามหน้าตรงๆ ไม่ได้")
    assert page["trend"].lstrip().startswith(expected), page["trend"][:200]
    assert page["trend_first"] == "trendDataNote"
    assert page["trend_spans"] == [_thai_date(last), str(len(omni["items"])), str(current)]
    for gone in ("data_pulled_at", "62b1e81", "git blame", "DATA_MAP", "cube_Sale_APD", "pricelist_reader"):
        assert gone not in page["trend"], gone


def test_trend_values_change_when_their_sources_change(edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8", newline="").read()
    changed = re.sub(r'"dd":\[\[\d{6},', '"dd":[[301231,', text, count=1)
    assert changed != text
    inv = json.load(open(os.path.join(PROJECT_ROOT, "data", "inventory.json"), encoding="utf-8"))
    inv["totals"]["codes"] = 777
    site = _site(tmp_path_factory, "w3_perturbed", index_text=changed, inventory=inv)
    server, url = _serve(site)
    try:
        edge.open(url)
        edge.ev("omniShowTab(2); 1")
        assert _wait(edge, "document.getElementById('trendDataNote').style.display === 'block'")
        spans = edge.ev("['trendLastDate','trendCodeCount','currentCodeCount'].map(i=>document.getElementById(i).textContent)")
    finally:
        server.shutdown()
    assert spans[0] == _thai_date(301231) and spans[2] == "777", spans


def test_trend_note_stays_hidden_when_the_current_count_cannot_be_read(edge, tmp_path_factory):
    site = _site(tmp_path_factory, "w3_no_inventory")
    os.remove(site / "data" / "inventory.json")
    server, url = _serve(site)
    try:
        edge.open(url)
        edge.ev("omniShowTab(2); 1")
        time.sleep(1.5)
        assert edge.ev("document.getElementById('trendDataNote').style.display") == "none"
    finally:
        server.shutdown()


# ------------------------------------------------------------------ W3b: S&OP texts, computed numbers, stock status names
def test_w3b_sop_texts_are_in_place(page):
    sop = page["sop"]
    assert "แถบสีฟ้า = ช่วงที่ผ่านมา (ม.ค.-ก.ค.) · แถบสีส้ม = แผน (ส.ค.-ธ.ค.) · จัดแผนแบบ Chase Strategy คือผลิตให้ตรงกับความต้องการแต่ละเดือน" in sop
    assert "ตามไฟล์ต้นฉบับ (ตรวจสอบย้อนหลังไม่ได้)" in sop and "จับคู่รหัสสินค้าตามไฟล์ต้นฉบับ" in sop
    assert "ช่วงที่ผ่านมา" in page["sop_legend"]
    for gone in ("Figure 3.5", "History (ข้อมูลจริง)", "Cube Sale APD2026 (status", "จับคู่กับ itemcode", "ข้อมูลจริง ม.ค.–ก.ค."):
        assert gone not in sop, gone


def test_w3b_trend_numbers_are_computed_from_the_tab_data(page):
    text = open(INDEX, encoding="utf-8").read()
    omni = json.loads(_embedded_lines(text)["OMNI"][len("const OMNI = "):].rstrip(";"))
    assert page["trend_head_count"] == str(len(omni["items"]))
    assert "(" + str(len(omni["items"])) + " รหัส)" in page["trend_head"] and "01.06.69" not in page["trend_head"]
    assert page["n31_spans"] and set(page["n31_spans"]) == {str(omni["n31"])}
    assert "{n31}" not in page["adi_title"] and f"({omni['n31']} ÷" in page["adi_title"]
    for typed in ("448 รหัส)", "ฐาน 31 เดือน"):
        assert typed not in text, f"{typed!r} is typed in index.html again"


def test_w3b_trend_numbers_follow_a_changed_source(edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8", newline="").read()
    changed = text.replace('"n31":31', '"n31":29', 1)
    assert changed != text
    site = _site(tmp_path_factory, "w3b_perturbed", index_text=changed)
    server, url = _serve(site)
    try:
        edge.open(url)
        edge.ev("omniShowTab(2); 1")
        assert _wait(edge, "document.getElementById('trendHeadCount').textContent !== ''")
        spans = edge.ev("[...document.querySelectorAll('.omni-n31')].map(e => e.textContent)")
        title = edge.ev("document.querySelector('#skuTbl th[data-k=adi]').title")
    finally:
        server.shutdown()
    assert set(spans) == {"29"} and "(29 ÷" in title


def test_w3b_stock_status_names_are_reader_words(page):
    stock = page["stock"]
    for shown in ("มีของ", "ของเป็นศูนย์", "ไม่มีในระบบ stock"):
        assert shown in stock, shown
    for gone in ("has_stock", "zero_stock", "no_db_record"):
        assert gone not in stock, gone


# ------------------------------------------------------------------ Part 5: manual
def test_manual_states_the_gap_without_a_typed_percentage(page):
    assert "ตัวเลขบนหน้านี้ต่างเล็กน้อย ดูตัวเลขบนหน้า Min-Max" in page["manual"]
    assert "ประมาณ 3%" not in page["manual"]


# ------------------------------------------------------------------ embedded data untouched
def test_trend_embedded_data_is_untouched():
    lines = _embedded_lines(open(INDEX, encoding="utf-8").read())
    got = {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in lines.items()}
    if None in EMBEDDED_DATA_SHA256.values():
        pytest.skip("SKIPPED, not passed: the recorded hashes are not set")
    assert got == EMBEDDED_DATA_SHA256


# ------------------------------------------------------------------ sales report: no stale significance claim
def test_limitations_hold_no_significance_claim_the_block_replaced():
    """The significance sentence (and its Naive claim) is replaced by the computed block in section 6; the limitations list must
    not carry a typed significance statement again (tests/test_significance_topdown.py tests the block)."""
    import yaml
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert not [x for x in cfg["report"]["limitations"] if "นัยสำคัญ" in x or "Naive" in x]
    with open(os.path.join(PROJECT_ROOT, "forecast", "sales_report.html"), encoding="utf-8") as f:
        html_text = f.read()
    limitations = re.search(r'<section id="limitations">.*?</section>', html_text, re.S).group(0)
    assert "นัยสำคัญ" not in limitations and "Naive" not in limitations
