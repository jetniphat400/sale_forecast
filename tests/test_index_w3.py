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

# The two embedded data lines of the Trend tab (const MATCH = ..., const OMNI = ...) are written by src/build_trend_tab.py between two markers (decision of the user,
# 2026-10-08); the test below rebuilds them from the saved pull and compares.


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
        out["default_tab"] = edge.ev("[...document.querySelectorAll('#tabBar .actv')].map(b => b.textContent.trim())")
        out["default_visible"] = edge.ev("['origTab','omniTab','manualTab','assumptionsTab','invPanel'].filter(i => getComputedStyle(document.getElementById(i)).display !== 'none')")
        out["bar"] = edge.ev("[...document.querySelectorAll('#tabBar > *')].map(e => e.textContent.trim())")
        out["sop"] = edge.ev("document.getElementById('origTab').innerText")
        out["sop_badges"] = edge.ev("(function(){var r={};document.querySelectorAll('#itemTable .badge').forEach(function(b){r[b.textContent]=(r[b.textContent]||0)+1});return r})()")
        out["sop_labels"] = edge.ev("[...document.querySelectorAll('#origTab td.rowlabel')].map(c=>c.textContent.trim())")
        out["sop_legend"] = edge.ev("[...document.querySelectorAll('#origTab .legend-row > span')].map(e => e.textContent.trim()).join(' | ')")
        out["sop_first"] = edge.ev("[...document.getElementById('origTab').querySelector('.wrap').children].find(e => e.tagName !== 'STYLE').className")
        edge.ev("omniShowTab(2); 1")
        assert _wait(edge, "document.getElementById('trendDataNote').style.display === 'block'"), "the Trend note did not appear"
        out["trend"] = edge.ev("document.getElementById('omniTab').innerText")
        out["trend_first"] = edge.ev("[...document.getElementById('omniTab').children].find(e => e.tagName !== 'STYLE').id")
        out["trend_pl_label"] = edge.ev("document.getElementById('trendPlLabel').textContent")
        out["trend_yellow"] = edge.ev("document.querySelectorAll('#omniTab > div.note')[1].innerText")
        out["trend_c4"] = edge.ev("document.getElementById('c4').innerText")
        out["trend_yrs"] = edge.ev("[...document.querySelectorAll('.omni-yrs')].map(e => e.textContent)")
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
    expected = f"ยอดนับตามวันที่รับ PO จึงไม่เท่ากับยอดในหน้าพยากรณ์ ซึ่งนับตามเดือนที่ต้องส่งของ · ข้อมูลถึง {omni['meta']['pull']}"
    assert page["trend"].lstrip().startswith(expected), page["trend"][:200]
    assert page["trend_first"] == "trendDataNote"
    assert re.fullmatch(r"\d{1,2} \S+ \d{2}", omni["meta"]["pull"])                      # the shared Thai date format (d MMM yy)
    assert "{" not in expected and "}" not in expected
    for gone in ("data_pulled_at", "62b1e81", "git blame", "DATA_MAP", "cube_Sale_APD", "pricelist_reader", "ไม่อัปเดต"):
        assert gone not in page["trend"], gone


def test_trend_values_change_when_their_sources_change(edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8", newline="").read()
    omni = json.loads(_embedded_lines(text)["OMNI"][len("const OMNI = "):].rstrip(";"))
    pull, label = omni["meta"]["pull"], omni["meta"]["pricelist"]
    changed = text.replace(f'"pull":"{pull}"', '"pull":"1 ม.ค. 70"', 1).replace(f'"pricelist":"{label}"', "\"pricelist\":\"Q9-2099\"", 1)
    assert changed != text
    site = _site(tmp_path_factory, "w3_perturbed", index_text=changed)
    server, url = _serve(site)
    try:
        edge.open(url)
        edge.ev("omniShowTab(2); 1")
        assert _wait(edge, "document.getElementById('trendDataNote').style.display === 'block'")
        note = edge.ev("document.getElementById('trendDataNote').textContent")
        pl = edge.ev("document.getElementById('trendPlLabel').textContent")
    finally:
        server.shutdown()
    assert note.endswith("ข้อมูลถึง 1 ม.ค. 70") and pl == "Q9-2099", (note, pl)


def test_trend_note_stays_hidden_when_the_data_carry_no_pull_date(edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8", newline="").read()
    changed = re.sub(r'"pull":"[^"]*"', '"pull":""', text, count=1)
    assert changed != text
    site = _site(tmp_path_factory, "w3_no_pull", index_text=changed)
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
    assert page["trend_pl_label"] == omni["meta"]["pricelist"] and re.fullmatch(r"Q[1-4]'20\d\d", page["trend_pl_label"])
    assert set(page["trend_yrs"]) == {f"{omni['meta']['first_year']}-{omni['meta']['last_year']}"}
    assert omni["months"][0] == f"{omni['meta']['first_year']}-01" and omni["n31"] == len(omni["months"]) - 1
    assert page["trend_head_count"] == str(len(omni["items"]))
    assert "(" + str(len(omni["items"])) + " รหัส)" in page["trend_head"] and "01.06.69" not in page["trend_head"]
    assert page["n31_spans"] and set(page["n31_spans"]) == {str(omni["n31"])}
    assert "{n31}" not in page["adi_title"] and f"({omni['n31']} ÷" in page["adi_title"]
    for typed in ("448 รหัส)", "ฐาน 31 เดือน", "ปี 2024-2026", "ส.ค.2026 ยังไม่จบเดือน", "ม.ค. 2567 - ส.ค. 2569"):
        assert typed not in text, f"{typed!r} is typed in index.html again"


def test_w3b_trend_numbers_follow_a_changed_source(edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8", newline="").read()
    n31 = re.search(r'"n31":(\d+)', text).group(1)
    changed = text.replace(f'"n31":{n31}', '"n31":29', 1)
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
def test_trend_embedded_data_is_what_the_builder_makes_from_the_saved_pull():
    import build_trend_tab as bt
    cfg = bt.load_config()
    pull_dir = os.path.join(PROJECT_ROOT, *cfg["trend_tab"]["pull_dir"].split("/"))
    if not os.path.exists(os.path.join(pull_dir, "completeness.json")):
        pytest.skip("SKIPPED, not passed: the saved Trend pull (untracked output) is not on this machine")
    daily, names, comp = bt.read_pull(PROJECT_ROOT, cfg)
    omni, match, _ = bt.build_data(daily, names, comp, bt.pricelist_rows(PROJECT_ROOT, cfg), cfg, bt.pricelist_label(PROJECT_ROOT))
    lines = _embedded_lines(open(INDEX, encoding="utf-8").read())
    assert json.loads(lines["OMNI"][len("const OMNI = "):].rstrip(";")) == json.loads(bt._json(omni))
    assert json.loads(lines["MATCH"][len("const MATCH = "):].rstrip(";")) == json.loads(bt._json(match))


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


# ====================================================================================================== 2026-10-09: the original tabs and links restored, only แผนวัตถุดิบ added
LABELS = ["S&OP Plan (เดิม)", "สรุปผู้บริหาร", "Trend Pricelist Omni 2024–2026", "แผนการผลิต (จากยอดทาย)", "แผนวัตถุดิบ", "สมมติฐานที่ใช้อยู่", "คู่มือการใช้งาน"]
PAGE_FILES = {"sales": "sales_report.html", "inventory": "inventory.html", "operation": "operation_plan.html", "material": "material_plan.html"}


def test_the_bar_has_exactly_the_seven_labels_in_order_with_the_two_page_links():
    import html as _html
    text = open(INDEX, encoding="utf-8").read()
    bar = re.search(r'<div id="tabBar">(.*?)</div>', text, re.S).group(1)
    items = re.findall(r'<(?:button|a)\b[^>]*>(.*?)</(?:button|a)>', bar, re.S)
    assert [_html.unescape(x).strip() for x in items] == LABELS
    assert re.findall(r'<(button|a) id="(\w+)"', bar) == [("button", "tb1"), ("button", "tb5"), ("button", "tb2"), ("a", "tbPlan"), ("a", "tbMat"), ("button", "tb4"), ("button", "tb3")]
    assert re.findall(r'<a id="(\w+)" href="([^"]+)"', bar) == [("tbPlan", "forecast/operation_plan.html"), ("tbMat", "forecast/material_plan.html")]
    assert 'id="tb1" class="actv"' in bar and "สต็อกวันนี้" not in text.split('<div id="origTab"')[0]
    for removed in ("tbStock", "tbSales", "tbInv", "OMNI_TAB_FRAGMENTS", "hashchange", "navsep"):
        assert removed not in text, removed
    # the two page links are styled alike (the same rule covers every link of the bar)
    assert "#tabBar a{" in text and "#tabBar a:hover" in text


def test_the_s_and_op_tab_opens_by_default(page):
    assert page["default_tab"] == ["S&OP Plan (เดิม)"]
    assert page["default_visible"] == ["origTab"]
    assert page["bar"] == LABELS


def test_the_s_and_op_in_tab_links_are_back_and_the_stock_panel_has_its_back_control():
    text = open(INDEX, encoding="utf-8").read()
    sop = text.split('<div id="origTab"')[1].split("<!--/origTab-->")[0]
    assert '<a class="oplink" href="forecast/sales_report.html">Sales — ยอดขาย</a>' in sop
    assert '<a class="oplink" href="forecast/inventory.html" onclick="event.stopPropagation()">→ Min/Max Scenario</a>' in sop
    assert 'id="invMenuRow"' in sop and "▸ ดูข้อมูลสต็อคจริง (คลิกหรือกด Enter)" in sop
    assert '<button type="button" id="invBackBtn">← กลับไปหน้า S&amp;OP Plan (Tab 1)</button>' in text
    assert "tabBar a" in text and 'id="invPanel"' in text


def test_the_stock_panel_opens_from_the_inventory_row_shows_the_daily_data_and_the_back_control_returns(edge, tmp_path_factory):
    site = _site(tmp_path_factory, "w9_stock")
    server, url = _serve(site)
    try:
        edge.open(url)
        time.sleep(1.5)
        assert edge.ev("getComputedStyle(document.getElementById('origTab')).display") != "none"
        edge.ev("document.getElementById('invMenuRow').click(); 1")
        assert _wait(edge, "document.getElementById('invContent').style.display === 'block'"), "the stock panel did not load"
        assert edge.ev("getComputedStyle(document.getElementById('origTab')).display") == "none"
        assert edge.ev("getComputedStyle(document.getElementById('invPanel')).display") == "block"
        inv = json.load(open(os.path.join(PROJECT_ROOT, "data", "inventory.json"), encoding="utf-8"))
        assert edge.ev("document.getElementById('invSnapshotLabel').innerText").strip() != ""
        assert edge.ev("document.querySelectorAll('#invTableBody tr').length") > 0 and len(inv["items"]) > 0
        edge.ev("document.getElementById('invBackBtn').click(); 1")
        assert edge.ev("getComputedStyle(document.getElementById('invPanel')).display") == "none"
        assert edge.ev("getComputedStyle(document.getElementById('origTab')).display") != "none"
        assert [e for e in edge.errors if e.startswith("exception")] == []
    finally:
        server.shutdown()


def test_the_four_working_pages_have_no_bar_and_keep_their_back_link_and_in_page_links():
    for name in PAGE_FILES.values():
        text = open(os.path.join(PROJECT_ROOT, "forecast", name), encoding="utf-8").read()
        assert "page-nav" not in text and "data-nav" not in text, name
        assert re.search(r'<a class="back-link" href="\.\./index\.html">(&larr;|←) กลับ', text), name
    inv = open(os.path.join(PROJECT_ROOT, "forecast", PAGE_FILES["inventory"]), encoding="utf-8").read()
    assert '<a class="back-link" id="plan-link" href="operation_plan.html">แผนการผลิต</a>' in inv
    op_page = open(os.path.join(PROJECT_ROOT, "forecast", PAGE_FILES["operation"]), encoding="utf-8").read()
    assert '<a class="page-link" id="material-plan-link" href="material_plan.html">แผนวัตถุดิบ</a>' in op_page


@pytest.mark.parametrize("width,height,mobile", [(1440, 900, False), (390, 844, True)])
def test_the_bar_fits_or_wraps_without_a_sideways_scroll_and_the_s_and_op_tab_opens_first(edge, tmp_path_factory, width, height, mobile):
    site = _site(tmp_path_factory, f"w9_layout_{width}")
    server, url = _serve(site)
    try:
        edge.open(url, width=width, height=height, mobile=mobile)
        time.sleep(1.5)
        facts = edge.ev("""(function(){var rights=[...document.querySelectorAll('#tabBar > *')].map(e=>e.getBoundingClientRect().right);
          return {innerW: window.innerWidth, maxRight: Math.max.apply(null, rights), barW: document.getElementById('tabBar').scrollWidth,
                  barClientW: document.getElementById('tabBar').clientWidth,
                  active: [...document.querySelectorAll('#tabBar .actv')].map(b => b.textContent.trim()),
                  origShown: getComputedStyle(document.getElementById('origTab')).display !== 'none'}})()""")
        assert facts["maxRight"] <= facts["innerW"] + 1 and facts["barW"] <= facts["barClientW"] + 1, facts       # the bar fits (it wraps on a narrow screen)
        assert facts["active"] == ["S&OP Plan (เดิม)"] and facts["origShown"], facts
    finally:
        server.shutdown()


# ------------------------------------------------------------------ Prompt 11: the Trend tab data builder (src/build_trend_tab.py)
def _fixture_pull():
    import pandas as pd
    pl = pd.DataFrame([
        {"code": "A-1", "sheet": "S1", "division": "PEM101", "category": "Cat", "type": "Typ", "description": "Cap 22kV 630A"},
        {"code": "B-2", "sheet": "S1", "division": "PEM101", "category": "Cat", "type": "Typ", "description": "Fuse 12,500A"},
        {"code": "C-3", "sheet": "S2", "division": "PEM102", "category": "Cat", "type": "", "description": "Router"},
        {"code": "D-4", "sheet": "S2", "division": "PEM102", "category": "Cat", "type": "Typ", "description": "Switch 22kV 630A"},
        {"code": "E-5", "sheet": "S2", "division": "PEM102", "category": "Cat", "type": "Typ", "description": "Never sold item"},
        {"code": "F-6", "sheet": "S2", "division": "PEM102", "category": "Cat", "type": "Typ", "description": "Only this month 5A"},
    ])
    daily = pd.DataFrame([
        {"itemcode": "A-1", "d": "2024-01-10", "status": "Actual", "q": 4.0, "s": 400.0, "n": 1},
        {"itemcode": "A-1", "d": "2024-01-10", "status": "MPS", "q": 1.0, "s": 100.0, "n": 1},
        {"itemcode": "A-1", "d": "2024-02-20", "status": "Actual", "q": 5.0, "s": 500.0, "n": 2},
        {"itemcode": "B-2", "d": "2024-01-05", "status": "Actual", "q": 8.0, "s": 80.0, "n": 1},
        {"itemcode": "C-3", "d": "2024-02-01", "status": "Actual", "q": 2.0, "s": 20.0, "n": 1},
        {"itemcode": "D-4", "d": "2024-02-02", "status": "Actual", "q": 3.0, "s": 30.0, "n": 1},
        {"itemcode": "F-6", "d": "2024-03-02", "status": "MPS", "q": 7.0, "s": 70.0, "n": 1},
    ])
    names = pd.DataFrame([
        {"itemcode": "A-1", "productName": "Capacitor 22,000 V 630 A", "n": 3},
        {"itemcode": "B-2", "productName": "Fuse 12500 A", "n": 1},
        {"itemcode": "C-3", "productName": "ROUTER WL-R210", "n": 1},
        {"itemcode": "D-4", "productName": "Switch 22 kV 600 A", "n": 1},
        {"itemcode": "F-6", "productName": "Other 5 A", "n": 1}, {"itemcode": "F-6", "productName": "Another 5 A", "n": 1},
    ])
    totals = {"pulled_at": "2024-03-15T10:00:00", "n_rows": 8, "qty": 30.0, "sale": 1200.0}
    return daily, names, totals, pl


def test_trend_builder_spec_remark_has_one_fixed_example_per_outcome():
    import build_trend_tab as bt
    assert bt.specs("Cap 22kV 630A") == {"22000v", "630a"}
    assert bt.specs("ดิสคอนเนคติ้งสวิตช์ 22 เควี 600 แอมป์") == {"22000v", "600a"}
    assert bt.specs("Fuse 12,500A") == {"12500a"}
    assert bt.spec_status(["Cap 22kV 630A"], "Capacitor 22,000 V 630 A", True)[0] == "ok"            # kV against V: same spec
    assert bt.spec_status(["Fuse 12,500A"], "Fuse 12500 A", True)[0] == "ok"                          # a comma number
    assert bt.spec_status(["Cap 22kV 630A"], "Cap 22kV", True)[0] == "ok"                              # one side contained in the other
    assert bt.spec_status(["Switch 22kV 630A"], "Switch 22 kV 600 A", True)[0] == "conflict"
    assert bt.spec_status(["Router"], "ROUTER WL-R210", True)[0] == "nospec"
    assert bt.spec_status(["Router 5A"], "ROUTER", True)[0] == "nospec"
    assert bt.spec_status(["Switch 22kV 630A"], "Switch 22kV 630A", False)[0] == "nodata"             # no sales in the scope
    assert bt.format_specs({"22000v", "630a"}) == "22kV, 630A" and bt.format_specs({"50hz", "12500a"}) == "12.5kA, 50HZ"


def test_trend_builder_classes_months_and_totals_from_a_fixture():
    import build_trend_tab as bt
    daily, names, totals, pl = _fixture_pull()
    cfg = bt.load_config()
    omni, match, report = bt.build_data(daily, names, totals, pl, cfg, "Q1'2024")
    assert omni["months"] == ["2024-01", "2024-02", "2024-03"] and omni["n31"] == 2                  # the month of the pull date is the incomplete one
    it = {i["c"]: i for i in omni["items"]}
    assert it["A-1"]["qa"][:2] == [4.0, 5.0] and it["A-1"]["qm"][:2] == [1.0, 0.0] and it["A-1"]["sa"][:2] == [400.0, 500.0]
    assert it["A-1"]["adi"] == 1.0 and it["A-1"]["cls"] == "Smooth"                                    # qty 5 and 5 in two months: ADI 1, CV2 0
    assert it["B-2"]["adi"] == 2.0 and it["B-2"]["cv2"] == 0.0 and it["B-2"]["cls"] == "Intermittent"
    assert it["E-5"]["cls"] == "NoSale" and it["E-5"]["adi"] is None and match["E-5"] == {"s": "nodata"}
    assert it["F-6"]["cls"] == "NoSale31M" and it["F-6"]["qm"][2] == 7.0                                 # sales only in the incomplete month: no ADI, no class
    assert it["C-3"]["pt"] == "-" and it["F-6"]["dbn"] == "Another 5 A"                                  # blank type shown as -; a name tie goes to the first in alphabetical order
    assert report["n_name_ties"] == 1 and report["spec"] == {"ok": 3, "conflict": 1, "nospec": 1, "nodata": 1}
    # the daily rows sum to the months, and the totals are the completeness query's
    for i in omni["items"]:
        assert sum(r[1] + r[3] for r in i["dd"]) == pytest.approx(sum(i["qa"]) + sum(i["qm"]))
        assert sum(r[2] + r[4] for r in i["dd"]) == pytest.approx(sum(i["sa"]) + sum(i["sm"]))
    assert report["totals"] == {"rows": 8, "qty": 30.0, "sale": 1200.0}
    assert [r for i in omni["items"] if i["c"] == "A-1" for r in i["dd"]] == [[240110, 4.0, 400.0, 1.0, 100.0], [240220, 5.0, 500.0, 0.0, 0.0]]


def test_trend_builder_stops_when_the_totals_differ_from_the_completeness_query():
    import build_trend_tab as bt
    daily, names, totals, pl = _fixture_pull()
    cfg = bt.load_config()
    for key, bad in (("n_rows", 9), ("qty", 31.0), ("sale", 1200.5)):
        with pytest.raises(bt.TrendTabError, match="completeness query"):
            bt.build_data(daily, names, dict(totals, **{key: bad}), pl, cfg, "Q1'2024")
    with pytest.raises(bt.TrendTabError, match="outside the months"):
        bt.build_data(daily.assign(d=daily["d"].where(daily.index != 0, "2024-06-01")), names, totals, pl, cfg, "Q1'2024")


def test_trend_builder_writes_only_between_the_markers_and_is_repeatable(tmp_path):
    import build_trend_tab as bt
    daily, names, totals, pl = _fixture_pull()
    omni, match, _ = bt.build_data(daily, names, totals, pl, bt.load_config(), "Q1'2024")
    path = tmp_path / "index.html"
    path.write_text("<html>before\nconst MATCH = {\"x\":{}};\nconst OMNI = {\"months\":[]};\nafter</html>", encoding="utf-8")
    bt.write_index(str(path), omni, match)
    once = path.read_text(encoding="utf-8")
    assert once.startswith("<html>before\n/* TREND-DATA-BEGIN */") and once.endswith("/* TREND-DATA-END */\nafter</html>")
    bt.write_index(str(path), omni, match)
    assert path.read_text(encoding="utf-8") == once                                                     # a second run changes nothing
    with pytest.raises(bt.TrendTabError):
        (tmp_path / "other.html").write_text("no data here", encoding="utf-8")
        bt.write_index(str(tmp_path / "other.html"), omni, match)


def test_trend_tab_in_index_html_is_the_saved_pull_and_its_totals_equal_the_completeness_query():
    import json as _json
    import build_trend_tab as bt
    cfg = bt.load_config()
    text = open(INDEX, encoding="utf-8").read()
    assert text.count(bt.BEGIN_MARK) == 1 and text.count(bt.END_MARK) == 1
    omni = _json.loads(_embedded_lines(text)["OMNI"][len("const OMNI = "):].rstrip(";"))
    pull_dir = os.path.join(PROJECT_ROOT, *cfg["trend_tab"]["pull_dir"].split("/"))
    if not os.path.exists(os.path.join(pull_dir, "completeness.json")):
        pytest.skip("SKIPPED, not passed: the saved Trend pull (untracked output) is not on this machine")
    comp = _json.load(open(os.path.join(pull_dir, "completeness.json"), encoding="utf-8"))
    assert round(sum(sum(i["qa"]) + sum(i["qm"]) for i in omni["items"]), 3) == round(comp["qty"], 3)
    assert round(sum(sum(i["sa"]) + sum(i["sm"]) for i in omni["items"]), 1) == round(comp["sale"], 1)
    assert sum(len(i["dd"]) for i in omni["items"]) > 0 and omni["meta"]["pull_iso"] == comp["pulled_at"][:10]
    assert omni["n31"] == len(omni["months"]) - 1 and omni["months"][-1] == comp["pulled_at"][:7]


def test_trend_yellow_note_and_chart_caption_show_the_months_and_date_of_the_data(page, edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8").read()
    omni = json.loads(_embedded_lines(text)["OMNI"][len("const OMNI = "):].rstrip(";"))
    m = omni["meta"]
    yellow = " ".join(page["trend_yellow"].split())
    assert f"เดือน {m['month_incomplete']} ยังไม่จบเดือน แสดงเป็นแท่งสีจาง และไม่รวมในการคำนวณ ADI/CV² (ฐาน {omni['n31']} เดือน: {m['base_first']} – {m['base_last']})" in yellow, yellow
    assert "คนละชุด" in yellow and "แท็บ S&OP Plan เดิม" in yellow                                           # the sentence about the S&OP tab is as it was
    assert f"ตรวจสอบแล้ว ({m['pull']}): ไม่มีรหัสสินค้าใดถูกนับซ้ำข้ามหน่วยธุรกิจ" in " ".join(page["trend_c4"].split())
    assert re.fullmatch(r"\S+ \d{2}", m["month_incomplete"])    # the shared month format (MMM yy, Buddhist year)
    changed = text.replace(f'"month_incomplete":"{m["month_incomplete"]}"', '"month_incomplete":"ม.ค. 99"', 1).replace(f'"base_last":"{m["base_last"]}"', '"base_last":"ธ.ค. 98"', 1)
    assert changed != text
    site = _site(tmp_path_factory, "p12_perturbed", index_text=changed)
    server, url = _serve(site)
    try:
        edge.open(url)
        edge.ev("omniShowTab(2); 1")
        assert _wait(edge, "document.getElementById('trendHeadCount').textContent !== ''")
        note = " ".join(edge.ev("document.querySelectorAll('#omniTab > div.note')[1].innerText").split())
    finally:
        server.shutdown()
    assert "เดือน ม.ค. 99 ยังไม่จบเดือน" in note and f"{m['base_first']} – ธ.ค. 98)" in note


# ------------------------------------------------------------------ Prompt 13: the executive summary tab (src/build_trend_tab.py, METRICS.md Sec.49)
def _exec_block(text: str) -> str:
    import build_trend_tab as bt
    assert text.count(bt.EXEC_BEGIN) == 1 and text.count(bt.EXEC_END) == 1
    return text[text.index(bt.EXEC_BEGIN) + len(bt.EXEC_BEGIN):text.index(bt.EXEC_END)]


def _exec_visible(block: str) -> list:
    import html as _html
    t = re.sub(r"</(?:div|tr|li|p|h3|ul|table|thead|tbody)>", "\n", block)
    t = re.sub(r"</t[dh]>", " | ", t)
    return [" ".join(x.split()) for x in _html.unescape(re.sub(r"<[^>]+>", "", t)).split("\n") if x.strip()]


def _fixed_exec_data():
    """A small fixed data set: two forecast divisions, one without a target, and every watch-out condition off."""
    rows = [{"division": "AAA", "ytd": 100e6, "last_ytd": 80e6, "change": 0.25, "forecast_remaining": 50e6, "projection": 150e6, "target": 200e6, "to_target": 0.75, "relative_mae": 0.6},
            {"division": "BBB", "ytd": 30e6, "last_ytd": 40e6, "change": -0.25, "forecast_remaining": 10e6, "projection": 40e6, "target": None, "to_target": None, "relative_mae": 1.2}]
    tot = {"ytd": 130e6, "last_ytd": 120e6, "forecast_remaining": 60e6, "projection": 190e6, "target": None, "change": 130 / 120 - 1, "to_target": None}
    return {"data_month": "2026-08", "data_month_label": "ส.ค. 69", "year": 2026, "year_be": 2569, "remaining_months": ["2026-09"], "rows": rows, "total": tot, "n_forecast_divisions": 2,
            "n_beat_naive": 1, "thresholds": {"good": 0.7, "pass": 1.0, "limit": 4.0}, "watch": [], "pending": [{"topic": "หัวข้อ", "to_decide": "ต้องตัดสินอะไร"}]}


def test_the_executive_tab_is_wired_into_the_tab_switch_and_is_a_tab_of_this_page():
    text = open(INDEX, encoding="utf-8").read()
    assert 'id="tb5" onclick="omniShowTab(5)"' in text and '<div id="execTab">' in text
    assert "document.getElementById('execTab').style.display = n==5?'block':'none';" in text
    assert "document.getElementById('tb5').className = n==5?'actv':'';" in text


def test_the_s_and_op_pointer_line_is_under_the_kpi_cards_and_links_to_the_new_tab():
    text = open(INDEX, encoding="utf-8").read()
    sop = text[text.index('<div id="origTab">'):text.index('<div id="execTab">') if '<div id="execTab">' in text else len(text)]
    m = re.search(r'</div>\s*(<p class="desc" id="sopExecPointer">.*?</p>)\s*<section>', sop, re.S)
    assert m and sop.index('<div class="kpi-row">') < sop.index(m.group(1))
    assert m.group(1) == '<p class="desc" id="sopExecPointer">ตัวเลขจริงดูที่แท็บ<a href="#" onclick="omniShowTab(5);return false">สรุปผู้บริหาร</a></p>'


def test_the_exec_tab_texts_cards_table_and_remarks_are_verbatim_from_fixed_data():
    import build_trend_tab as bt
    cfg = bt.load_config()
    d = _fixed_exec_data()
    d["watch"] = []
    lines = _exec_visible(bt.exec_render(d, cfg))
    assert lines[0].startswith("ยอดขาย ม.ค.–ส.ค. 69 | ") or "ยอดขาย ม.ค.–ส.ค. 69" in lines
    joined = "\n".join(lines)
    for text in ["ยอดขาย ม.ค.–ส.ค. 69", "130.0 ล้านบาท", "เทียบช่วงเดียวกันปีก่อน +8.3%", "คาดการณ์ทั้งปี 2569 (สินค้าใน Price List)", "190.0 ล้านบาท", "ถึงเป้า – · เป้ารวมสินค้า Omni ทุกตัว % นี้จึงน่าจะต่ำกว่าจริง",
                 "ความแม่นของยอดทาย", "1 จาก 2 ฝ่าย", "ดีกว่า Naive", "เรื่องที่ต้องระวัง", "0 เรื่อง", "ดูรายการด้านล่าง", "เรื่องที่รอผู้บริหารตัดสิน", "หัวข้อ · ต้องตัดสินอะไร",
                 "ฝ่าย | ยอดขาย YTD | ปีก่อน YTD | เปลี่ยน | คาดการณ์ทั้งปี | เป้า (Revenue) | ถึงเป้า | Relative MAE | หมายเหตุ",
                 "AAA | 100.0 | 80.0 | +25.0% | 150.0 | 200.0 | 75.0% | 0.60 |",
                 "BBB | 30.0 | 40.0 | -25.0% | 40.0 | – | – | 1.20 | ไม่พบเป้าของฝ่ายนี้ในระบบเป้า",
                 "รวม | 130.0 | 120.0 | +8.3% | 190.0 | – | – | – |",
                 "PEM104 | – | – | – | – | – | – | – | PEM104 ผลิตตามสั่งทั้งหมด จึงไม่ได้ทายยอดขาย",
                 "PEMC | – | – | – | – | – | – | – | PEMC อยู่นอกขอบเขตสินค้าของ Omni Channel ในโปรเจกต์นี้",
                 "ยอดขายนับตามเดือนที่ต้องส่งของ รวม PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) · ไม่รวม VAT · คาดการณ์ = ยอดจริงถึง ส.ค. 69 + เดือนที่เหลือใช้ค่าที่มากกว่าระหว่างยอดทายกับออเดอร์ที่รับแล้ว × ราคาขายเฉลี่ยจริง · "
                 "เป้ามาจากระบบเป้าของบริษัท (Revenue) · ยังไม่ได้ยืนยันว่าเป้านับจากวันส่งของหรือวันออก invoice · ยอดขายและคาดการณ์นับเฉพาะสินค้าใน Price List แต่เป้ารวมสินค้า Omni ทุกตัว"]:
        assert text in joined, text
    assert "{" not in joined and "}" not in joined
    # a division with a target and the total with every target: a percent to target in the total row and in card 2
    d["rows"][1].update(target=50e6, to_target=0.8)
    d["total"].update(target=250e6, to_target=190 / 250)
    again = "\n".join(_exec_visible(bt.exec_render(d, cfg)))
    assert "ถึงเป้า 76.0% · เป้ารวมสินค้า Omni ทุกตัว % นี้จึงน่าจะต่ำกว่าจริง" in again and "ไม่พบเป้าของฝ่ายนี้ในระบบเป้า" not in again.split("PEM104")[0]


def test_each_watch_out_line_appears_only_when_its_condition_holds():
    import build_trend_tab as bt
    cfg = bt.load_config()
    none = bt.exec_watch([{"group": "G", "value": 3.9}, {"group": "H", "value": -4.0}, {"group": "I", "value": None}], 4.0, [], 0, None)
    assert none == []                                                                                    # at the limit or inside it: no line; no plan line, no late material, no alert
    low = bt.exec_watch([{"group": "G", "value": -4.1}], 4.0, [], 0, None)
    high = bt.exec_watch([{"group": "H", "value": 6.7}], 4.0, [], 0, None)
    plan = bt.exec_watch([], 4.0, [{"division": "D1", "month": "ต.ค. 69", "pct": "119.9%"}], 0, None)
    mat = bt.exec_watch([], 4.0, [], 584, None)
    alert = bt.exec_watch([], 4.0, [], 0, {"since": "พ.ค. 2569", "pct": "57.7%"})
    assert [w["kind"] for w in low + high + plan + mat + alert] == ["low", "high", "plan", "material", "pem107"]
    d = _fixed_exec_data()
    d["watch"] = low + high + plan + mat + alert
    lines = _exec_visible(bt.exec_render(d, cfg))
    assert "G ทายต่ำกว่าจริงต่อเนื่อง (Tracking Signal -4.1) คาดการณ์ทั้งปีของกลุ่มนี้อาจต่ำกว่าที่จะเกิดจริง" in lines
    assert "H ทายสูงกว่าจริงต่อเนื่อง (Tracking Signal 6.7) คาดการณ์ทั้งปีของกลุ่มนี้อาจสูงกว่าที่จะเกิดจริง" in lines
    assert "แผนผลิต D1 เดือน ต.ค. 69 สูงกว่ายอดผลิตสูงสุดที่เคยทำ (119.9%)" in lines
    assert "วัตถุดิบ 584 รายการขาดแล้ว สั่งตอนนี้ไม่ทันแผน" in lines
    assert "PEM107 ส่งของช่องทาง Omni ทันน้อยลงตั้งแต่ พ.ค. 2569 (57.7% ไม่สาย)" in lines
    assert "5 เรื่อง" in "\n".join(lines)                                                                 # card 4 counts the lines shown
    assert not any("ทายต่ำกว่าจริง" in x for x in _exec_visible(bt.exec_render(dict(d, watch=high), cfg)))


def _fixed_page(tmp_path, a_vals, b_vals):
    """A forecast page with a per-item baht table for AAA (two items) and BBB (one item); each value list is the baht of the remaining months Sep and Oct."""
    def table(div, items):
        rows = "".join(f'<tr class="fwd-btype" id="x{i}"><td>T</td><td>0</td><td>0</td></tr><tr class="fwd-bitem" data-parent="x{i}" hidden><td>{code} <span class="fwd-name">n</span></td>'
                       + "".join(f"<td>{'-' if v is None else format(v, ',')}</td>" for v in vals) + "</tr>" for i, (code, vals) in enumerate(items))
        return (f'<table class="report-table fwd-table" id="fwd-baht-table-{div}"><thead><tr><th>ประเภทสินค้า</th><th>ก.ย. 69</th><th>ต.ค. 69</th></tr></thead><tbody>{rows}'
                f'<tr class="total-row"><td>รวม {div}</td><td>0</td><td>0</td></tr></tbody></table>')
    page = tmp_path / "sales_report.html"
    page.write_text(table("AAA", a_vals) + table("BBB", b_vals), encoding="utf-8")
    return str(page)


def _gate_data(rows_projection):
    d = _fixed_exec_data()
    d["remaining_months"] = ["2026-09", "2026-10"]
    d["booked_baht"] = {"A1": {"2026-09": 40, "2026-10": 5}, "A2": {"2026-09": 0, "2026-10": 70}, "B1": {"2026-09": 3, "2026-10": 4}}
    d["rows"][0]["projection"] = d["rows"][0]["ytd"] + rows_projection[0]
    d["rows"][1]["projection"] = d["rows"][1]["ytd"] + rows_projection[1]
    d["total"]["projection"] = d["rows"][0]["projection"] + d["rows"][1]["projection"]
    d["total"]["forecast_remaining"] = rows_projection[0] + rows_projection[1]
    for r, v in zip(d["rows"], rows_projection):
        r["forecast_remaining"] = v
    d["total"]["ytd"] = d["rows"][0]["ytd"] + d["rows"][1]["ytd"]
    d["total"]["last_ytd"] = d["rows"][0]["last_ytd"] + d["rows"][1]["last_ytd"]
    d["total"]["target"] = None
    return d


def test_the_total_row_and_the_year_end_projection_identities_are_gated(tmp_path):
    import build_trend_tab as bt
    # AAA: item A1 forecast 10 and 20 against 40 and 5 on the books -> 40 + 20; item A2 forecast 30 and 8 against 0 and 70 -> 30 + 70; BBB: B1 forecast 2 and 9 against 3 and 4 -> 3 + 9
    page = _fixed_page(tmp_path, [("A1", [10, 20]), ("A2", [30, 8])], [("B1", [2, 9])])
    assert bt.exec_gate(_gate_data([40 + 20 + 30 + 70, 3 + 9]), page)["passed"]
    with pytest.raises(bt.ExecSummaryError, match="projection"):
        bt.exec_gate(_gate_data([40 + 20 + 30 + 70 + 1, 3 + 9]), page)                                   # a projection that is not YTD plus the per-item maxima
    with pytest.raises(bt.ExecSummaryError, match="projection"):
        bt.exec_gate(_gate_data([10 + 20 + 30 + 8, 3 + 9]), page)                                         # the forecast page's baht alone is no longer the rule
    bad = _gate_data([40 + 20 + 30 + 70, 3 + 9])
    bad["total"]["ytd"] += 5.0                                                                           # a total row that is not the sum of the division rows
    with pytest.raises(bt.ExecSummaryError, match="total row"):
        bt.exec_gate(bad, page)
    wrong_months = _gate_data([40 + 20 + 30 + 70, 3 + 9])
    wrong_months["remaining_months"] = ["2026-10", "2026-11"]
    with pytest.raises(bt.ExecSummaryError, match="remaining months"):
        bt.exec_gate(wrong_months, page)


def test_the_remaining_months_take_the_larger_of_the_forecast_and_the_orders_on_the_books():
    import build_trend_tab as bt
    assert bt.exec_month_units(10, 4) == 10 and bt.exec_month_units(4, 10) == 10                          # forecast above the orders, orders above the forecast
    assert bt.exec_month_units(None, 7) == 7 and bt.exec_month_units(0, 0) == 0                           # an item with no forecast row counts 0 forecast units
    assert bt.exec_month_baht(10.4, 4, 100.0) == 1040 and bt.exec_month_baht(2.0, 3.5, 100.0) == 350     # units x unit price in whole baht
    assert bt.exec_month_baht(2.5, 0, 0.1) == 0 and bt.exec_month_baht(2.5, 0, 0.3) == 1 and bt.exec_month_baht(5, 9, None) == 0   # half up at item and month level; no price: 0
    raw = pd.DataFrame([
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 3, "status": "MPS", "revenue_type": "Omni Channel"},
        {"itemcode": "A", "createDate": "2026-08-05", "forecast_date": "2026-09-20", "qty": 4, "status": "Actual", "revenue_type": "Omni Channel"},
        {"itemcode": "A", "createDate": "2026-08-05", "forecast_date": "2026-10-20", "qty": 6, "status": "MPS", "revenue_type": "Omni Channel"},
        {"itemcode": "A", "createDate": "2026-09-30", "forecast_date": "2026-09-01", "qty": 50, "status": "MPS", "revenue_type": "Omni Channel"},      # forecast_date before createDate: not counted
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 60, "status": "Cancel", "revenue_type": "Omni Channel"},    # not Actual or MPS
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 70, "status": "MPS", "revenue_type": "Tendering"},          # not Omni Channel
        {"itemcode": "B", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 80, "status": "MPS", "revenue_type": "Omni Channel"},       # outside the scope
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-03-10", "qty": 90, "status": "Actual", "revenue_type": "Omni Channel"}])  # a month already in YTD
    assert bt.exec_booked_units(raw, {"A"}, ["2026-09", "2026-10"]) == {("A", "2026-09"): 7.0, ("A", "2026-10"): 6.0}


def test_the_targets_are_split_by_category_and_a_division_without_a_row_has_no_target(tmp_path):
    import json as _json
    import build_trend_tab as bt
    cfg = bt.load_config()
    pl = pd.DataFrame([{"code": "A", "division": "PEM103", "category": "Cat Transformer"}, {"code": "B", "division": "PEM107", "category": "Cat Instrument"}])
    d = tmp_path / "output" / "data" / "exec_pull"
    d.mkdir(parents=True)
    pd.DataFrame([
        {"yr": 2026, "division": "PEM101", "revenue_type": "Omni Channel", "category": "x", "product_type": "t", "amount": 100.0, "n_rows": 1, "n_null": 0},
        {"yr": 2026, "division": "PEM103", "revenue_type": "Omni Channel", "category": "Cat Transformer", "product_type": "t", "amount": 30.0, "n_rows": 1, "n_null": 0},
        {"yr": 2026, "division": "PEM103", "revenue_type": "Omni Channel", "category": "Cat Instrument", "product_type": "t", "amount": 20.0, "n_rows": 1, "n_null": 0},
        {"yr": 2026, "division": "PEM103", "revenue_type": "Omni Channel", "category": "Cat Unknown", "product_type": "t", "amount": 5.0, "n_rows": 1, "n_null": 0},
        {"yr": 2026, "division": "PEM103", "revenue_type": "Tendering", "category": "Cat Instrument", "product_type": "t", "amount": 999.0, "n_rows": 1, "n_null": 0},
        {"yr": 2026, "division": "PXX", "revenue_type": "Omni Channel", "category": "x", "product_type": "t", "amount": 7.0, "n_rows": 1, "n_null": 0}]).to_csv(d / "targets.csv", index=False)
    (d / "targets_meta.json").write_text(_json.dumps({"pulled_at": "2026-10-09T09:00:00", "year": 2026}), encoding="utf-8")
    by, rep = bt.exec_targets(str(tmp_path), cfg, pl, 2026)
    assert by["PEM101"] == 100.0 and by["PEM103"] == 30.0 and by["PEM107"] == 20.0                          # Omni only; PEM103's rows split by category
    assert by["PEM102"] is None and by["CI101"] is None and by["PEM104"] is None                           # no row at all: no target, not a target of 0
    assert rep["unallocated"] == 5.0 and rep["other_divisions"] == {"PXX": 7.0} and rep["omni_total"] == 162.0
    with pytest.raises(bt.ExecSummaryError, match="another year|is for"):
        bt.exec_targets(str(tmp_path), cfg, pl, 2027)


def test_pemc_has_no_price_list_item_and_the_tab_holds_no_customer_or_person_identifier():
    import build_trend_tab as bt
    cfg = bt.load_config()
    pl = bt.pricelist_rows(PROJECT_ROOT, cfg)
    assert "PEMC" not in set(pl["division"]) and "PEMC" not in set(pl["sheet"]) and "PEMC" not in set(cfg["sheet_to_division"].values())     # the VERIFY of the PEMC remark
    block = _exec_block(open(INDEX, encoding="utf-8").read())
    assert not re.search(r"CS\d{4,}|CTR-\d{4}|Co\.,|Ltd|บริษัท .* จำกัด|@", block)
    assert "{" not in block and "}" not in block


def test_the_executive_tab_in_index_html_is_what_the_builder_makes_from_the_saved_pulls():
    import build_trend_tab as bt
    cfg = bt.load_config()
    if not os.path.exists(os.path.join(PROJECT_ROOT, *cfg["exec_summary"]["target_pull_dir"].split("/"), "targets.csv")):
        pytest.skip("SKIPPED, not passed: the saved revenue-target pull (untracked output) is not on this machine")
    data = bt.exec_data(PROJECT_ROOT)
    assert "\n" + bt.exec_render(data, cfg) + "\n" == _exec_block(open(INDEX, encoding="utf-8").read())
    # the identities on the real figures: the total row is the sum of its rows, each projection is YTD plus the remaining months' baht of the forecast page
    assert bt.exec_gate(data, os.path.join(PROJECT_ROOT, "forecast", "sales_report.html"))["passed"]
    assert data["rows"][0]["division"] == "PEM101" and [r["division"] for r in data["rows"]] == ["PEM101", "PEM103", "PEM107", "PEM102", "CI101"]
    assert data["n_forecast_divisions"] == 5
