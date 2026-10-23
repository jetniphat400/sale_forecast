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
AVAILABLE_NOTE = "Available ยังนับคลัง QA ด้วย จึงอาจสูงกว่าของที่หยิบส่งได้จริง ให้ดู Sellable − Reserved"

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
    shutil.copy(os.path.join(PROJECT_ROOT, "data", "assumptions.json"), site / "data" / "assumptions.json")     # the manual's {braced} numbers are filled from its manual_values
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
    assert re.search(r"stock ดึงเมื่อ \d{1,2} \S+ \d{2} \d{2}:\d{2}", page["stock"])
    assert re.search(r"ของที่ออเดอร์ที่รับแล้วจองไว้ \(Reserved\) ดึงเมื่อ \d{1,2} \S+ \d{2} \d{2}:\d{2}", page["stock"])
    assert re.search(r"ไฟล์ stock ประจำวัน ดึงเมื่อ \d{1,2} \S+ \d{2} \d{2}:\d{2}", page["stock"])
    for gone in ("Cube_", "task 2a", "DATA_MAP", "METRICS", "config.yaml", "inventory.json"):
        assert gone not in re.sub(r"DB \(Cube_\w+\)", "DB", page["stock"]), gone          # a table name only inside the approved DB (<table>) form


# ------------------------------------------------------------------ Part 3: Trend tab
def test_trend_note_is_first_in_the_tab_and_follows_the_data(page):
    text = open(INDEX, encoding="utf-8").read()
    omni = json.loads(_embedded_lines(text)["OMNI"][len("const OMNI = "):].rstrip(";"))
    import yaml
    cfg = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))
    import reader_values as rv
    expected = cfg["page_timestamps"]["text"]["trend_note"]
    assert omni["meta"]["data_note"] == expected and "ยอดนับตามวันที่รับ PO จึงไม่เท่ากับยอดในหน้าพยากรณ์" in expected
    lead = page["trend"].lstrip()
    assert lead.startswith("ข้อมูลอัปเดตล่าสุด: ยอดขายจริงล่าสุด " + rv.thai_date_short(omni["meta"]["last_date"])) and expected in page["trend"]
    assert ("ใหม่ (Fresh)" in lead or "เก่า (Stale)" in lead) and "Forecast ล่าสุด" not in lead          # a DATA label: the status is added when the page is read; the Trend tab uses no forecast
    assert page["trend_first"] == "trendHeader"
    assert re.fullmatch(r"\d{1,2} \S+ \d{2}", omni["meta"]["pull"])                      # the shared Thai date format (d MMM yy)
    assert "{" not in expected and "}" not in expected
    for gone in ("data_pulled_at", "62b1e81", "git blame", "DATA_MAP", "cube_Sale_APD", "pricelist_reader", "ไม่อัปเดต"):
        assert gone not in page["trend"].replace("DB (cube_Sale_APD)", "DB"), gone          # the table name only inside the approved DB (<table>) form


def test_trend_values_change_when_their_sources_change(edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8", newline="").read()
    omni = json.loads(_embedded_lines(text)["OMNI"][len("const OMNI = "):].rstrip(";"))
    note, label = omni["meta"]["data_note"], omni["meta"]["pricelist"]
    changed = text.replace(json.dumps(note, ensure_ascii=False), '"ทดสอบ ดึงเมื่อ 1 ม.ค. 70"', 1).replace(f'"pricelist":"{label}"', "\"pricelist\":\"Q9-2099\"", 1)
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
    assert note == "ทดสอบ ดึงเมื่อ 1 ม.ค. 70" and pl == "Q9-2099", (note, pl)


def test_trend_note_stays_hidden_when_the_data_carry_no_pull_date(edge, tmp_path_factory):
    text = open(INDEX, encoding="utf-8", newline="").read()
    changed = re.sub(r'"data_note":"[^"]*"', '"data_note":""', text, count=1)
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
    q = re.fullmatch(r"Q([1-4])'(20\d\d)", omni["meta"]["pricelist"])
    assert q and page["trend_pl_label"] == f"Q{q.group(1)} {str(int(q.group(2)) + 543)[-2:]}"          # the quarter label is written with the Buddhist year as two digits
    assert set(page["trend_yrs"]) == {f"{str(omni['meta']['first_year'] + 543)[-2:]}-{str(omni['meta']['last_year'] + 543)[-2:]}"}
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
    for shown in ("มีของ", "ของเป็นศูนย์", "ไม่มีใน DB (Cube_Inventory_Exact)"):
        assert shown in stock, shown
    for gone in ("has_stock", "zero_stock", "no_db_record"):
        assert gone not in stock, gone


# ------------------------------------------------------------------ Part 5: manual
def test_manual_states_the_gap_without_a_typed_percentage(page):
    assert "ตัวเลขบนหน้านี้ต่างเล็กน้อย ดูตัวเลขบนหน้า Min-Max" in page["manual"]
    assert "ประมาณ 3%" not in page["manual"]
    # the manual's numbers and dates come from data/assumptions.json at runtime: none is left unresolved or blank, the schedule reads "first weekday from the 5th", no typed December date
    import re as _re
    manual_values = json.load(open(os.path.join(PROJECT_ROOT, "data", "assumptions.json"), encoding="utf-8"))["manual_values"]
    assert "[ค่าไม่พบ" not in page["manual"] and not _re.search(r"\{[a-z_0-9]+\}", page["manual"]) and "5 ธ.ค." not in page["manual"]
    assert f"ข้อมูลขายใน DB (cube_Sale_APD) ถึง {manual_values['trend_data_through']}" in page["manual"] and "วันธรรมดา (จันทร์ถึงศุกร์) วันแรกตั้งแต่วันที่ " + manual_values["run_day_base"] in page["manual"]
    assert f"ต้องรอ {manual_values['guard_days']} วันหลังสิ้นเดือน" in page["manual"]
    # the confirmed lead time (45-60 days, read from config), never the stress point 75; the one term for on-time delivery; the data date in the one year format
    assert "แต่การสั่งวัตถุดิบใช้ 45-60 วัน" in page["manual"] and "45-75" not in page["manual"]
    assert "ฝ่ายที่ขายเยอะ MAE มักสูงกว่า" in page["manual"] and "สูงกว่าเสมอ" not in page["manual"].split("ฝ่ายที่ขายเยอะ")[1][:30]
    assert re.search(r"ข้อมูลขายใน DB \(cube_Sale_APD\) ถึง \d{1,2} \S+ \d{2}\b", page["manual"]) and not re.search(r"\b(20[2-3]\d|25[6-7]\d)\b", page["manual"])


# ------------------------------------------------------------------ embedded data untouched
def _manual_text(edge, site):
    server, url = _serve(site)
    try:
        edge.open(url)
        edge.ev("omniShowTab(3); 1")
        assert _wait(edge, "document.getElementById('manualTabContent').innerText.indexOf('กำลังโหลด') < 0"), "the manual did not load"
        return edge.ev("document.getElementById('manualTab').innerText")
    finally:
        server.shutdown()


def test_the_manual_shows_an_unresolved_placeholder_visibly_never_blank(edge, tmp_path_factory):
    # one value missing from manual_values: that name is shown as [ค่าไม่พบ: name], the others are still filled
    site = _site(tmp_path_factory, "w3_manual_one_missing")
    path = site / "data" / "assumptions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["manual_values"]["trend_data_through"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    text = _manual_text(edge, site)
    assert "โหลดค่าบางตัวของคู่มือไม่ได้" in text and "[ค่าไม่พบ" not in text
    # the file cannot be read at all: every name stays visible as unresolved
    site2 = _site(tmp_path_factory, "w3_manual_no_values")
    os.remove(site2 / "data" / "assumptions.json")
    text2 = _manual_text(edge, site2)
    assert "โหลดค่าบางตัวของคู่มือไม่ได้" in text2 and "[ค่าไม่พบ" not in text2 and "—" in text2


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
LABELS = ["S&OP Plan (เดิม)", "สรุปผู้บริหาร", "Trend Price List Omni ปี 67–69", "Production Plan (แผนผลิต)", "แผนวัตถุดิบ", "สมมติฐานที่ใช้อยู่", "คู่มือการใช้งาน"]
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
    assert '<a class="back-link" id="plan-link" href="operation_plan.html">Production Plan</a>' in inv
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
    totals = {"pulled_at": "2024-03-15T10:00:00", "last_date": "2024-03-14", "n_rows": 8, "qty": 30.0, "sale": 1200.0}
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
    assert "ตรวจสอบแล้ว" not in " ".join(page["trend_c4"].split())
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
    import build_exec_summary as bx
    assert text.count(bx.EXEC_BEGIN) == 1 and text.count(bx.EXEC_END) == 1
    return text[text.index(bx.EXEC_BEGIN) + len(bx.EXEC_BEGIN):text.index(bx.EXEC_END)]


def _exec_visible(block: str) -> list:
    import html as _html
    block = re.sub(r"<script.*?</script>", "", block, flags=re.S)
    t = re.sub(r"</(?:div|tr|li|p|h3|ul|table|thead|tbody)>", "\n", block)
    t = re.sub(r"</t[dh]>", " | ", t)
    return [" ".join(x.split()) for x in _html.unescape(re.sub(r"<[^>]+>", "", t)).split("\n") if x.strip()]


def _fixed_labels(cfg: dict) -> dict:
    """The executive tab's "ข้อมูล ณ" lines for fixed data (config page_timestamps.text): the sales line is MODEL-ROUND, the others are DATA with a status."""
    import reader_values as rv
    t = cfg["page_timestamps"]["text"]
    items = [("sales_round", "2026-10-05", "round"), ("plan_stock", "2026-10-20 08:00:00", "data"), ("peak", "2026-10-02", "file"), ("material", "2026-10-20 09:42:00", "data"), ("pem107_alert", "2026-10-20 09:46:00", "data")]
    return {"header": rv.data_header(cfg, items, False), "js": rv.data_age_js(cfg)}


def _fixed_exec_data():
    """A small fixed data set: two forecast divisions and every watch-out condition off."""
    import build_trend_tab as _bt
    cfg = _bt.load_config()
    rows = [{"division": "AAA", "ytd": 100e6, "last_ytd": 80e6, "change": 0.25, "forecast_remaining": 50e6, "projection": 150e6, "relative_mae": 0.6},
            {"division": "BBB", "ytd": 30e6, "last_ytd": 40e6, "change": -0.25, "forecast_remaining": 10e6, "projection": 40e6, "relative_mae": 1.2}]
    tot = {"ytd": 130e6, "last_ytd": 120e6, "forecast_remaining": 60e6, "projection": 190e6, "change": 130 / 120 - 1}
    return {"data_month": "2026-08", "data_month_label": "ส.ค. 69", "year": 2026, "year_be": 69, "remaining_months": ["2026-09"], "rows": rows, "total": tot, "n_forecast_divisions": 2,
            "n_beat_naive": 1, "thresholds": {"good": 0.7, "pass": 1.0, "limit": 4.0}, "watch": [], "pending": [{"topic": "หัวข้อ", "to_decide": "ต้องตัดสินอะไร"}], "labels": _fixed_labels(cfg),
            "monthly": {"actual": {f"2026-{m:02d}": v * 1e6 for m, v in zip(range(1, 9), [10, 12, 14, 16, 18, 20, 20, 20])},
                        "last_year": {f"2025-{m:02d}": v * 1e6 for m, v in zip(range(1, 13), [15] * 8 + [10] * 4)}, "projection": {"2026-09": 60e6}}}


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


def _chart_values(block: str) -> dict:
    """The numbers the two charts of a rendered block show: the tooltips of chart 1 by series, the value labels of chart 2, the threshold line and the table's Relative MAE column."""
    def tips(cls):
        return re.findall(r'<circle class="' + cls + r'"[^>]*><title>(.*?)</title>', block)
    return {"actual": tips("ec-dot-actual"), "proj": tips("ec-dot-proj"), "last": tips("ec-dot-last"), "bars": re.findall(r'<text class="ec-val"[^>]*>(.*?)</text>', block),
            "table": [m for m in re.findall(r'<tr data-division="[^"]*"><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td><td>([^<]*)</td>', block) if m != "–"]}


def test_the_two_exec_charts_reconcile_with_the_cards_and_the_table_on_the_saved_data():
    """Not a run gate (nothing here is called by exec_gate or the monthly run): Chart 1's monthly actuals add up to the YTD of the rows, last year's months to the last-year YTD, YTD plus the
    dashed months to the full-year projection; Chart 2's bar values are the table's Relative MAE column."""
    import build_trend_tab as bt
    import build_exec_summary as bx
    cfg = bt.load_config()
    d = bx.exec_data(PROJECT_ROOT)
    mo, tot, mnum = d["monthly"], d["total"], int(d["data_month"][5:7])
    assert list(mo["actual"]) == [f"{d['year']}-{m:02d}" for m in range(1, mnum + 1)] and list(mo["projection"]) == d["remaining_months"] and len(mo["last_year"]) == 12
    assert abs(sum(mo["actual"].values()) - tot["ytd"]) < 1e-6
    assert abs(sum(v for k, v in mo["last_year"].items() if int(k[5:7]) <= mnum) - tot["last_ytd"]) < 1e-6
    assert abs(sum(mo["actual"].values()) + sum(mo["projection"].values()) - tot["projection"]) < 1e-6
    shown = _chart_values(bx.exec_render(d, cfg))
    assert len(shown["actual"]) == mnum and len(shown["proj"]) == len(d["remaining_months"]) and len(shown["last"]) == 12
    assert shown["bars"] == shown["table"] and len(shown["bars"]) == sum(1 for r in d["rows"] if r["relative_mae"] is not None)


def test_exec_render_handles_a_division_with_no_relative_mae_and_a_data_month_other_than_august():
    import build_trend_tab as bt
    import build_exec_summary as bx
    cfg = bt.load_config()
    d = _fixed_exec_data()
    d["rows"][1]["relative_mae"] = None
    d.update(data_month="2026-10", data_month_label="ต.ค. 69", remaining_months=["2026-11", "2026-12"])
    d["monthly"] = {"actual": {f"2026-{m:02d}": 10e6 for m in range(1, 11)}, "last_year": {f"2025-{m:02d}": 9e6 for m in range(1, 13)}, "projection": {"2026-11": 15e6, "2026-12": 15e6}}
    block = bx.exec_render(d, cfg)
    shown = _chart_values(block)
    assert len(shown["actual"]) == 10 and shown["actual"][-1] == "ต.ค. 69: 10.0 ล้านบาท" and shown["proj"] == ["พ.ย. 69: 15.0 ล้านบาท", "ธ.ค. 69: 15.0 ล้านบาท"]
    assert shown["bars"] == ["0.60"] and "PEM104 ไม่ได้ทำ Forecast (ผลิตตามสั่งทั้งหมด)" in block and "{" not in re.sub(r"<script.*?</script>", "", block, flags=re.S) and "}" not in re.sub(r"<script.*?</script>", "", block, flags=re.S)
    assert 'class="ec-bar-pass"' in block and 'class="ec-bar-above"' not in block                      # the one value (0.60) is below the pass threshold of 1.0
    d["monthly"]["projection"] = {}                                                                     # the data month is December: nothing remaining, no dashed line, no error
    d.update(data_month="2026-12", remaining_months=[])
    d["monthly"]["actual"] = {f"2026-{m:02d}": 10e6 for m in range(1, 13)}
    assert '<polyline class="ec-proj"' not in bx.exec_render(d, cfg)


def test_the_exec_tab_texts_cards_table_and_remarks_are_verbatim_from_fixed_data():
    import build_trend_tab as bt
    import build_exec_summary as bx
    cfg = bt.load_config()
    import reader_values as rv
    DECISION_DATE_TH = rv.thai_date_short(rv.criteria_decision_date(cfg["maxmin_v1"]["pending_criteria_values"]))
    d = _fixed_exec_data()
    d["watch"] = []
    lines = _exec_visible(bx.exec_render(d, cfg))
    assert lines[0].startswith("ยอดขาย ม.ค.–ส.ค. 69 | ") or "ยอดขาย ม.ค.–ส.ค. 69" in lines
    joined = "\n".join(lines)
    for text in ["ยอดขาย ม.ค.–ส.ค. 69", "130.0 ล้านบาท", "เทียบช่วงเดียวกันปีก่อน +8.3%", "คาดการณ์ทั้งปี 69 (สินค้าใน Price List)", "190.0 ล้านบาท",
                 "ความแม่นของ Forecast", "1 จาก 2 ฝ่าย", "Forecast = ยอดขายที่ระบบคาดการณ์ · Relative MAE ต่ำกว่าวิธีเทียบ Naive (ใช้ยอดเดือนล่าสุดเป็น Forecast ทุกเดือน) ตามเกณฑ์ร่าง · ฝ่ายที่พิสูจน์แล้วว่าดีกว่าจริงดูในหน้ายอดขาย · ยืนยันเกณฑ์หลังรอบ " + DECISION_DATE_TH, "เรื่องที่ต้องระวัง", "0 เรื่อง", "ดูรายการด้านล่าง", "เรื่องที่รอผู้บริหารตัดสิน", "หัวข้อ · ต้องตัดสินอะไร",
                 "ฝ่าย | ยอดขาย YTD | ปีก่อน YTD | เปลี่ยน | คาดการณ์ทั้งปี | Relative MAE | หมายเหตุ",
                 "AAA | 100.0 | 80.0 | +25.0% | 150.0 | 0.60 |",
                 "BBB | 30.0 | 40.0 | -25.0% | 40.0 | 1.20 |",
                 "รวม | 130.0 | 120.0 | +8.3% | 190.0 | – |",
                 "PEM104 | – | – | – | – | – | PEM104 ผลิตตามสั่งทั้งหมด จึงไม่ได้ทำ Forecast",
                 "ยอดขาย = ยอดตามเดือนที่ต้องส่งของ รวม PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) ไม่รวม VAT · ยอดจริงมีถึง ส.ค. 69 · คาดการณ์ทั้งปี = ยอดจริงที่มีทั้งหมดข้างต้น + ยอดเดือนที่เหลือ · ยอดเดือนที่เหลือ = ค่าที่มากกว่าระหว่าง Forecast กับออเดอร์ที่รับแล้ว × ราคาขายเฉลี่ยจริง · ยอดขายและคาดการณ์นับเฉพาะสินค้าใน Price List"]:
        assert text in joined, text
    assert "{" not in joined and "}" not in joined
    # no revenue target anywhere in the tab (Prompt 27: the pilot scope is Price List items only): no target column, no attainment text, no PEMC row, no card-2 subtitle
    for gone in ("ถึงเป้า", "เป้า (Revenue)", "เป้ารวมสินค้า Omni", "ไม่พบเป้า", "PEMC", "เป้ามาจากระบบเป้า"):
        assert gone not in joined, gone
    assert 'id="execCard2"' in bx.exec_render(d, cfg) and bx.exec_render(d, cfg).count('class="s"') == 3        # card 2 has no subtitle line any more


def test_each_watch_out_line_appears_only_when_its_condition_holds():
    import build_trend_tab as bt
    import build_exec_summary as bx
    cfg = bt.load_config()
    none = bx.exec_watch([{"group": "G", "value": 3.9}, {"group": "H", "value": -4.0}, {"group": "I", "value": None}], 4.0, [], 0, None)
    assert none == []                                                                                    # at the limit or inside it: no line; no plan line, no late material, no alert
    low = bx.exec_watch([{"group": "G", "value": -6.0, "points": [("2026-01", -3), ("2026-02", -3), ("2026-03", -3), ("2026-04", -3), ("2026-05", -3), ("2026-06", -3)]}], 4.0, [], 0, None)          # six points below the actual: -6.0, still -5.0 without any one point: no suffix
    high = bx.exec_watch([{"group": "H", "value": 6.7, "points": [("2026-01", 1), ("2026-02", -1), ("2026-03", 1), ("2026-04", -1), ("2026-05", 1), ("2026-06", -1), ("2026-07", 1), ("2026-08", 30)]}], 4.0, [], 0, None)   # 5 of 8 above, 6.7; without the 30 it is 1.0, within the limit: suffix for the 8th month
    plan = bx.exec_watch([], 4.0, [{"division": "D1", "month": "ต.ค. 69", "pct": "119.9%", "first": "3 ม.ค. 66", "last": "2 ต.ค. 69"}], 0, None)
    mat = bx.exec_watch([], 4.0, [], 584, None, "6 ต.ค. 69")
    alert = bx.exec_watch([], 4.0, [], 0, {"since": "พ.ค. 69", "pct": "57.7%"})
    assert [w["kind"] for w in low + high + plan + mat + alert] == ["low", "high", "plan", "material", "pem107"]
    d = _fixed_exec_data()
    d["watch"] = low + high + plan + mat + alert
    lines = _exec_visible(bx.exec_render(d, cfg))
    assert "G Forecast ต่ำกว่าจริง 6 จาก 6 จุดวัด (Tracking Signal -6.0) คาดการณ์ทั้งปีของกลุ่มนี้อาจต่ำกว่าที่จะเกิดจริง" in lines and (low[0]["k"], low[0]["n"], low[0]["month"]) == (6, 6, None)
    assert "H Forecast สูงกว่าจริง 5 จาก 8 จุดวัด (Tracking Signal 6.7) ส่วนใหญ่มาจากเดือน ส.ค. 69 เดือนเดียว คาดการณ์ทั้งปีของกลุ่มนี้อาจสูงกว่าที่จะเกิดจริง" in lines and (high[0]["k"], high[0]["n"], high[0]["month"]) == (5, 8, "2026-08")
    assert not any("ต่อเนื่อง" in x for x in lines)
    assert "แผนผลิต D1 เดือน ต.ค. 69 สูงกว่า Historical peak (ยอดผลิตเสร็จสูงสุดต่อเดือนในอดีต ไม่ใช่กำลังผลิตเต็มที่) (119.9%) คิดจากประวัติผลิต 3 ม.ค. 66 ถึง 2 ต.ค. 69" in lines
    assert "วัตถุดิบ 584 รายการเลยกำหนดสั่ง (Late to order) สั่งวันนี้ของมาไม่ทันแผน (ณ 6 ต.ค. 69)" in lines
    assert "PEM107 ส่งของช่องทาง Omni ส่งทัน (Not-late: ส่งไม่ช้ากว่าวันนัด) น้อยลงตั้งแต่ พ.ค. 69 (57.7%)" in lines
    assert "5 เรื่อง" in "\n".join(lines)                                                                 # card 4 counts the lines shown
    assert not any("Forecast ต่ำกว่าจริง" in x for x in _exec_visible(bx.exec_render(dict(d, watch=high), cfg)))
    # an undefined signal without the largest point gives no suffix; a tie for the largest takes the first point in time order
    assert bx.exec_ts_counts([("2026-01", -5.0), ("2026-02", 0.0)], 4.0) == {"k": 1, "n": 2, "month": None}
    assert bx.exec_ts_counts([("2026-01", -3.0), ("2026-02", -3.0), ("2026-03", 0.5)], 2.0)["month"] == "2026-01"


def test_the_watch_out_counts_on_the_saved_data_equal_an_independent_recomputation_and_no_line_says_continuously():
    import build_trend_tab as bt
    import build_exec_summary as bx
    import build_report as br
    cfg = bt.load_config()
    limit = float(cfg["maxmin_v1"]["pending_criteria_values"]["tracking_signal_limit"])
    acc = br.gather_accuracy_vs_naive(cfg, br.gather_primary_results())
    d = bx.exec_data(PROJECT_ROOT)
    seen = {w["group"]: w for w in d["watch"] if w["kind"] in ("low", "high")}
    expect = {}
    for r in acc["rows"]:
        e = [x for _m, x in r["points"]]
        ts = sum(e) / (sum(abs(x) for x in e) / len(e))
        assert abs(ts - r["tracking_signal"]) < 1e-9 and len(e) == r["n_points"]                       # the points are the page's own
        if abs(ts) > limit:
            k = sum(1 for x in e if (x < 0) == (ts < 0) and x != 0)
            big = max(range(len(e)), key=lambda i: abs(e[i]))
            rest = e[:big] + e[big + 1:]
            rest_ts = sum(rest) / (sum(abs(x) for x in rest) / len(rest)) if any(rest) else None
            expect[r["label"]] = (k, len(e), r["points"][big][0] if rest_ts is not None and abs(rest_ts) <= limit else None)
    assert expect and {g: (w["k"], w["n"], w["month"]) for g, w in seen.items()} == expect
    lines = _exec_visible(bx.exec_render(d, cfg))
    assert not any("ต่อเนื่อง" in x for x in lines if any(re.match(re.escape(g) + r"( \([^)]*\))? Forecast ", x) for g in expect))          # no watch-out line says "continuously" (the decision list's Bias topic is another text)
    for g, (k, n, month) in expect.items():
        line = next(x for x in lines if re.match(re.escape(g) + r"( \([^)]*\))? Forecast ", x))
        assert f" {k} จาก {n} จุดวัด (Tracking Signal " in line and (("ส่วนใหญ่มาจากเดือน" in line) == (month is not None))


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
    import build_exec_summary as bx
    # AAA: item A1 forecast 10 and 20 against 40 and 5 on the books -> 40 + 20; item A2 forecast 30 and 8 against 0 and 70 -> 30 + 70; BBB: B1 forecast 2 and 9 against 3 and 4 -> 3 + 9
    page = _fixed_page(tmp_path, [("A1", [10, 20]), ("A2", [30, 8])], [("B1", [2, 9])])
    assert bx.exec_gate(_gate_data([40 + 20 + 30 + 70, 3 + 9]), page)["passed"]
    with pytest.raises(bx.ExecSummaryError, match="projection"):
        bx.exec_gate(_gate_data([40 + 20 + 30 + 70 + 1, 3 + 9]), page)                                   # a projection that is not YTD plus the per-item maxima
    with pytest.raises(bx.ExecSummaryError, match="projection"):
        bx.exec_gate(_gate_data([10 + 20 + 30 + 8, 3 + 9]), page)                                         # the forecast page's baht alone is no longer the rule
    bad = _gate_data([40 + 20 + 30 + 70, 3 + 9])
    bad["total"]["ytd"] += 5.0                                                                           # a total row that is not the sum of the division rows
    with pytest.raises(bx.ExecSummaryError, match="total row"):
        bx.exec_gate(bad, page)
    wrong_months = _gate_data([40 + 20 + 30 + 70, 3 + 9])
    wrong_months["remaining_months"] = ["2026-10", "2026-11"]
    with pytest.raises(bx.ExecSummaryError, match="remaining months"):
        bx.exec_gate(wrong_months, page)


def test_the_remaining_months_take_the_larger_of_the_forecast_and_the_orders_on_the_books():
    import build_exec_summary as bx
    assert bx.exec_month_units(10, 4) == 10 and bx.exec_month_units(4, 10) == 10                          # forecast above the orders, orders above the forecast
    assert bx.exec_month_units(None, 7) == 7 and bx.exec_month_units(0, 0) == 0                           # an item with no forecast row counts 0 forecast units
    assert bx.exec_month_baht(10.4, 4, 100.0) == 1040 and bx.exec_month_baht(2.0, 3.5, 100.0) == 350     # units x unit price in whole baht
    assert bx.exec_month_baht(2.5, 0, 0.1) == 0 and bx.exec_month_baht(2.5, 0, 0.3) == 1 and bx.exec_month_baht(5, 9, None) == 0   # half up at item and month level; no price: 0
    raw = pd.DataFrame([
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 3, "status": "MPS", "revenue_type": "Omni Channel"},
        {"itemcode": "A", "createDate": "2026-08-05", "forecast_date": "2026-09-20", "qty": 4, "status": "Actual", "revenue_type": "Omni Channel"},
        {"itemcode": "A", "createDate": "2026-08-05", "forecast_date": "2026-10-20", "qty": 6, "status": "MPS", "revenue_type": "Omni Channel"},
        {"itemcode": "A", "createDate": "2026-09-30", "forecast_date": "2026-09-01", "qty": 50, "status": "MPS", "revenue_type": "Omni Channel"},      # forecast_date before createDate: not counted
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 60, "status": "Cancel", "revenue_type": "Omni Channel"},    # not Actual or MPS
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 70, "status": "MPS", "revenue_type": "Tendering"},          # not Omni Channel
        {"itemcode": "B", "createDate": "2026-08-01", "forecast_date": "2026-09-10", "qty": 80, "status": "MPS", "revenue_type": "Omni Channel"},       # outside the scope
        {"itemcode": "A", "createDate": "2026-08-01", "forecast_date": "2026-03-10", "qty": 90, "status": "Actual", "revenue_type": "Omni Channel"}])  # a month already in YTD
    assert bx.exec_booked_units(raw, {"A"}, ["2026-09", "2026-10"]) == {("A", "2026-09"): 7.0, ("A", "2026-10"): 6.0}


def test_the_tab_holds_no_customer_or_person_identifier_and_no_revenue_target():
    import build_trend_tab as bt
    cfg = bt.load_config()
    assert not any(k.startswith("target") for k in cfg["exec_summary"]) and set(cfg["exec_summary"]["text"]).isdisjoint({"card2_sub", "remark_PEMC", "remark_no_target"})
    assert "เป้า (Revenue)" not in cfg["exec_summary"]["text"]["columns"] and "ถึงเป้า" not in cfg["exec_summary"]["text"]["columns"]
    block = _exec_block(open(INDEX, encoding="utf-8").read())
    assert not re.search(r"CS\d{4,}|CTR-\d{4}|Co\.,|Ltd|บริษัท .* จำกัด|@", block)
    assert "{" not in re.sub(r"<script.*?</script>", "", block, flags=re.S) and "}" not in re.sub(r"<script.*?</script>", "", block, flags=re.S)
    for gone in ("ถึงเป้า", "เป้า (Revenue)", "เป้ารวมสินค้า Omni", "ไม่พบเป้า", "PEMC"):
        assert gone not in block, gone


def test_the_executive_tab_in_index_html_is_what_the_builder_makes_from_the_saved_pulls():
    import build_trend_tab as bt
    import build_exec_summary as bx
    cfg = bt.load_config()
    data = bx.exec_data(PROJECT_ROOT)
    assert "\n" + bx.exec_render(data, cfg) + "\n" == _exec_block(open(INDEX, encoding="utf-8").read())
    # the identities on the real figures: the total row is the sum of its rows, each projection is YTD plus the remaining months' baht of the forecast page
    assert bx.exec_gate(data, os.path.join(PROJECT_ROOT, "forecast", "sales_report.html"))["passed"]
    assert data["rows"][0]["division"] == "PEM101" and [r["division"] for r in data["rows"]] == ["PEM101", "PEM103", "PEM107", "PEM102", "CI101"]
    assert data["n_forecast_divisions"] == 5


def test_the_scripts_of_the_page_write_dates_like_the_python_formatter(edge, tmp_path_factory):
    import reader_values as rv
    site = _site(tmp_path_factory, "w3_formatter")
    server, url = _serve(site)
    try:
        edge.open(url)
        got = edge.ev("[thaiMonthShort('2026-10'), thaiMonthShort('2027-01'), thaiDateShort('2026-12-07'), thaiDateShort('2027-01-05'), thaiDateTime('2026-10-05 07:41:06'), "
                      "thaiDateTime('2026-10-05 07:41:06', true), thaiYearShort(2026), thaiQuarter(\"Q3'2026\"), thaiDateTime('')]")
    finally:
        server.shutdown()
    assert got == [rv.thai_month_short("2026-10"), rv.thai_month_short("2027-01"), rv.thai_date_short("2026-12-07"), rv.thai_date_short("2027-01-05"),
                   rv.thai_datetime_short("2026-10-05 07:41:06"), rv.thai_datetime_short("2026-10-05 07:41:06", seconds=True), rv.thai_year_short(2026), "Q3 69", "ไม่ทราบ"]
    assert got[:4] == ["ต.ค. 69", "ม.ค. 70", "7 ธ.ค. 69", "5 ม.ค. 70"]


def test_no_four_digit_year_and_no_iso_date_is_shown_outside_the_sop_tab(edge, tmp_path_factory):
    site = tmp_path_factory.mktemp("w3_all_pages")
    (site / "docs").mkdir()
    (site / "data").mkdir()
    (site / "forecast").mkdir()
    shutil.copy(INDEX, site / "index.html")
    shutil.copy(os.path.join(PROJECT_ROOT, "docs", "user_manual.md"), site / "docs" / "user_manual.md")
    for name in ("assumptions.json", "inventory.json", "stock_daily.json"):
        shutil.copy(os.path.join(PROJECT_ROOT, "data", name), site / "data" / name)
    for name in ("sales_report", "inventory", "operation_plan", "material_plan"):
        shutil.copy(os.path.join(PROJECT_ROOT, "forecast", name + ".html"), site / "forecast" / (name + ".html"))
    year4 = re.compile(r"(?<![A-Za-z0-9.,/<-])(20[2-3]\d|25[6-7]\d)(?![\d])")
    iso = re.compile(r"\b20[2-3]\d-\d\d(-\d\d)?\b")
    js = """(function(){var c=document.body.cloneNode(true);c.querySelectorAll('script,style,td.name,td.mono,td.code,#skuTbl').forEach(function(e){e.remove();});
      var s=c.querySelector('#origTab'); if(s)s.remove(); var w=document.createTreeWalker(c,NodeFilter.SHOW_TEXT),o=[],n; while(n=w.nextNode()){o.push(n.nodeValue);}
      var t=[]; document.querySelectorAll('[title]').forEach(function(e){ if(!(document.getElementById('origTab') && document.getElementById('origTab').contains(e))) t.push(e.getAttribute('title')); });
      return o.join(' ') + ' ' + t.join(' ');})()"""
    server, url = _serve(site)
    base = url.rsplit("/", 1)[0] + "/"
    seen = {}
    try:
        edge.open(base + "index.html")
        time.sleep(1.5)
        n = edge.ev("document.querySelectorAll('#tabBar > button').length")
        for i in range(1, n):                                                           # every tab but the original S&OP tab
            edge.ev(f"document.querySelectorAll('#tabBar > button')[{i}].click(); 1")
            time.sleep(1.2)
            seen[f"index tab {i}"] = edge.ev(js)
        assert _wait(edge, "document.getElementById('manualTabContent').innerText.indexOf('กำลังโหลด') < 0")
        for page_name in ("sales_report", "inventory", "operation_plan", "material_plan"):
            edge.open(base + f"forecast/{page_name}.html")
            time.sleep(2.5)
            seen[page_name] = edge.ev(js)
            if page_name == "inventory":
                for division in ("PEM103", "PEM107"):
                    edge.ev(f"var s=document.getElementById('division-select'); s.value='{division}'; s.dispatchEvent(new Event('change')); 1")
                    time.sleep(1.5)
                    seen[f"inventory {division}"] = edge.ev(js)
    finally:
        server.shutdown()
    for where, text in seen.items():
        assert text and len(text) > 200, f"{where} showed no text"
        assert not year4.search(text), f"{where} shows a four-digit year: {text[max(0, year4.search(text).start() - 40): year4.search(text).end() + 20]!r}"
        assert not iso.search(text), f"{where} shows an ISO date: {text[max(0, iso.search(text).start() - 40): iso.search(text).end() + 20]!r}"


# ------------------------------------------------------------------ Prompt 28: the all-channels label, no ERP source wording, no revenue-target text
def _outside_the_original_tab(text: str) -> str:
    """index.html without the original S&OP tab (div#origTab up to the stock panel), which belongs to the user."""
    return text[:text.index('<div id="origTab">')] + text[text.index('<div id="invPanel">'):]


def test_the_stock_panel_labels_reserved_and_available_as_all_channels_with_a_tooltip(edge, tmp_path_factory):
    site = _site(tmp_path_factory, "p28_allch")
    server, url = _serve(site)
    try:
        edge.open(url)
        edge.ev("omniShowTab(1); document.getElementById('invMenuRow').click(); 1")
        assert _wait(edge, "document.getElementById('invContent') && document.getElementById('invContent').style.display !== 'none'")
        badges = edge.ev("[...document.querySelectorAll('#invTable th[data-k=backlog], #invTable th[data-k=available]')].map(t=>{const b=t.querySelector('.inv-allch'); return b && [b.textContent, b.title]})")
        assert badges == [["รวมทุกช่องทาง", "stock และออเดอร์ที่รับแล้วใช้ร่วมกันทุกช่องทาง"]] * 2
        assert "รวมทุกช่องทาง" in edge.ev("document.getElementById('invBacklogLabel').textContent")
        assert edge.ev("(function(){const b=document.querySelector('#invTableBody .inv-bl-btn'); if(!b) return false; b.click(); return true})()")
        assert "รวมทุกช่องทาง" in edge.ev("document.getElementById('invBlSub').textContent")
    finally:
        server.shutdown()
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors


def test_no_page_or_manual_text_outside_the_original_tab_names_erp_as_a_source_or_a_revenue_target():
    import glob
    texts = {"index.html": _outside_the_original_tab(open(INDEX, encoding="utf-8").read()), "docs/user_manual.md": open(os.path.join(PROJECT_ROOT, "docs", "user_manual.md"), encoding="utf-8").read(),
             "config/manual_notes.yaml": open(os.path.join(PROJECT_ROOT, "config", "manual_notes.yaml"), encoding="utf-8").read()}
    for path in glob.glob(os.path.join(PROJECT_ROOT, "forecast", "*.html")):
        if "Chase S&OP" not in os.path.basename(path):                  # the standalone copy of the original tab belongs to the user
            texts["forecast/" + os.path.basename(path)] = open(path, encoding="utf-8").read()
    for name, t in texts.items():
        assert not re.search(r"\bERP\b", t, re.I), f"{name}: ERP named as a source (say DB and the table)"
        for gone in ("เป้ารายได้", "เป้าตรงๆ", "เป้า (Revenue)", "เป้ารวมสินค้า Omni", "ไม่พบเป้า", "Cube_Target_PMIS"):
            assert gone not in t, f"{name}: revenue-target text {gone!r}"


# ------------------------------------------------------------------ Prompt 29: the Edge helper leaves no process and no profile folder behind
def test_the_edge_helper_leaves_no_child_process_and_no_profile_folder_after_a_browser_test_or_a_failed_one(tmp_path):
    import page_helpers as ph
    exe = ph.require_browser()
    for fail in (False, True):
        e = ph.Edge(exe)
        profile = e.profile
        try:
            e.open("about:blank")
            assert ph.profile_pids(profile), "the helper's Edge should be running"
            if fail:
                raise RuntimeError("a failing test")
        except RuntimeError:
            pass
        finally:
            e.close()
        assert e.leftovers() == {"pids": [], "profile_exists": False}, e.leftovers()
        assert ph.profile_pids(profile) == [] and not os.path.exists(profile)


def test_no_page_or_manual_text_outside_the_original_tab_calls_a_database_table_the_system():
    """Prompt 29: where page text names a data source that is the database it says DB (<table>); these exact phrases (a source named as ระบบ) are gone. Other meanings of ระบบ stay."""
    import glob
    gone = ["ในระบบ ณ", "ที่ตั้งในระบบ", "ค่าที่ตั้งในระบบ", "ไม่มีบันทึกผลิตในระบบ", "ไม่มีหน่วยซื้อในระบบ", "ไม่มี BOM ในระบบ", "ไม่มีข้อมูลในระบบ", "ระบบขายของบริษัท", "ไม่มียอดขายในระบบ",
            "ไม่มีในระบบ stock", "ไม่มีใบสั่งซื้อในระบบ", "ป้ายในระบบ", "คีย์ช้าเข้าระบบ", "ที่บันทึกไว้ในระบบ", "ไว้ในระบบคลัง", "จากระบบ ดูอันนี้", "ระบบไม่มีบันทึกการแก้", "ระบบไม่ได้บันทึกว่า"]
    texts = {"index.html": _outside_the_original_tab(open(INDEX, encoding="utf-8").read()), "docs/user_manual.md": open(os.path.join(PROJECT_ROOT, "docs", "user_manual.md"), encoding="utf-8").read(),
             "config/manual_notes.yaml": open(os.path.join(PROJECT_ROOT, "config", "manual_notes.yaml"), encoding="utf-8").read()}
    for path in glob.glob(os.path.join(PROJECT_ROOT, "forecast", "*.html")):
        if "Chase S&OP" not in os.path.basename(path):
            texts["forecast/" + os.path.basename(path)] = open(path, encoding="utf-8").read()
    for name, t in texts.items():
        t = re.sub(r"<!--.*?-->", "", t, flags=re.S)                  # an off-screen comment may quote the old wording
        for phrase in gone:
            assert phrase not in t, f"{name}: {phrase!r}"
    assert "header_items" in texts["forecast/inventory.html"] and "dataHeaderHtml(T, items, DATA.forecast_header)" in texts["forecast/inventory.html"]
    assert "DB (cube_Sale_APD)" in texts["forecast/sales_report.html"] and "DB (cube_final)" in texts["forecast/operation_plan.html"]
    assert "DB (Cube_BOM_Exact)" in texts["forecast/material_plan.html"] or "ไม่มี BOM ใน DB" not in texts["forecast/material_plan.html"]


def test_the_stock_panel_script_judges_its_two_daily_sources_by_the_previous_weekday(edge, tmp_path_factory):
    import yaml
    cfg = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))
    assert "const INV_DAILY_WEEKDAYS_BACK = %d;" % cfg["page_timestamps"]["daily_weekdays_back"] in open(INDEX, encoding="utf-8").read()
    base = json.load(open(os.path.join(PROJECT_ROOT, "data", "inventory.json"), encoding="utf-8"))
    import reader_values as rv
    today = rv.date_today()          # the panel judges its sources against the day it is read
    for generated, loaded, old in ((f"{today}T01:00:00Z", f"{rv.previous_weekday(today, 1)} 21:00:00", False), (f"{today}T01:00:00Z", f"{rv.previous_weekday(today, 2)} 21:00:00", True)):
        inv = json.loads(json.dumps(base))
        inv["snapshot"].update(generated_at=generated, loaded_at=loaded)
        inv["backlog"]["loaded_at"] = loaded
        site = _site(tmp_path_factory, "p29_fresh", inventory=inv)
        server, url = _serve(site)
        try:
            edge.open(url)
            edge.ev("omniShowTab(1); document.getElementById('invMenuRow').click(); 1")
            assert _wait(edge, "document.getElementById('invContent') && document.getElementById('invContent').style.display !== 'none'")
            shown = edge.ev("[document.getElementById('invStalenessNote'), document.getElementById('invBacklogStalenessNote')].map(e => getComputedStyle(e).display !== 'none' ? e.innerText : '')")
        finally:
            server.shutdown()
        assert [bool(x) for x in shown] == [old, old], (generated, loaded, shown)
        labels = edge.ev("document.getElementById('invSnapshotLabel').textContent + ' | ' + document.getElementById('invBacklogLabel').textContent")
        assert labels.count("เก่า (Stale)") == (2 if old else 0) and labels.count("ใหม่ (Fresh)") == (1 if old else 3), labels      # stock, Reserved and the daily file each carry a status; the file was built today
        if old:
            assert all("ข้อมูล" in x and "เก่า" in x and "ดึงก่อนวันทำการก่อนหน้า" in x and "page_built_at" not in x for x in shown)


def test_prompt_30_source_wording_the_min_max_settings_the_stock_pull_line_and_the_trend_data_line_name_their_db_table():
    inv = open(os.path.join(PROJECT_ROOT, "forecast", "inventory.html"), encoding="utf-8").read()
    plan = open(os.path.join(PROJECT_ROOT, "forecast", "operation_plan.html"), encoding="utf-8").read()
    idx = open(INDEX, encoding="utf-8").read()
    manual = open(os.path.join(PROJECT_ROOT, "docs", "user_manual.md"), encoding="utf-8").read()
    visible = lambda t: re.sub(r"<!--.*?-->", "", t, flags=re.S)
    # the Min-Max page: the Min and Max settings are named as DB (Cube_Inventory_Exact), the old "ตั้งในระบบตอนนี้" is gone from what is shown
    assert "Min ค่าที่ตั้งใน DB (Cube_Inventory_Exact)" in visible(inv) and "ในระบบตอนนี้" not in visible(inv) and "ระบบตอนนี้" not in visible(plan)
    assert "header_items" in inv and "ข้อมูล stock จาก DB (Cube_Inventory_Exact) · Forecast" in plan and "stock และออเดอร์ที่รับแล้ว ดึงเมื่อ" in plan
    assert "ข้อมูล stock ดึงเมื่อ" not in visible(inv) and "ข้อมูล stock ดึงเมื่อ" not in visible(plan)
    assert "ข้อมูลขายใน DB (cube_Sale_APD)" in idx and "ข้อมูลถึง " not in visible(_outside_the_original_tab(idx))
    assert manual.count("ข้อมูลขายใน DB (cube_Sale_APD) ถึง {trend_data_through}") == 2 and "ข้อมูลถึง {" not in manual


# ---- Prompt 33: the Trend tab's totals gate absorbs rounding but still fails on a real difference

def test_the_trend_totals_gate_passes_at_the_rounding_boundary_and_fails_on_a_real_difference():
    import build_trend_tab as bt
    completeness = {"n_rows": 120000, "qty": 4250.5, "sale": 2162663420.55}
    ok = bt.trend_total_mismatches(120000, 4250.5, 2162663420.55, 4250.5, 2162663420.55, completeness)
    assert ok == {}
    boundary = bt.trend_total_mismatches(120000, 4250.5 + 0.00004, 2162663420.55 - 0.004, 4250.5 + 0.0009, 2162663420.55 + 0.06, completeness)
    assert boundary == {}, "a difference inside the rounding of each figure must not stop the run"
    for name, args in {"rows": (120001, 4250.5, 2162663420.55, 4250.5, 2162663420.55),
                       "qty": (120000, 4250.52, 2162663420.55, 4250.5, 2162663420.55),
                       "sale": (120000, 4250.5, 2162663420.58, 4250.5, 2162663420.55),
                       "items_qty": (120000, 4250.5, 2162663420.55, 4250.52, 2162663420.55),
                       "items_sale": (120000, 4250.5, 2162663420.55, 4250.5, 2162663420.75)}.items():
        assert name in bt.trend_total_mismatches(*args, completeness), f"a real difference in {name} did not fail the gate"


# ---- Prompt 34, item 10: scope lines

def test_the_executive_tab_and_the_min_max_page_state_their_scope():
    import yaml
    root = PROJECT_ROOT
    cfg = yaml.safe_load(open(os.path.join(root, "config", "config.yaml"), encoding="utf-8"))
    footer = cfg["exec_summary"]["text"]["footer"]
    assert "Price List" in footer and "Omni Channel" in footer
    index = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    assert footer.split("{data_month}")[-1].strip(" ·") in index, "the executive tab of index.html does not carry the footer of the config"
    scope = cfg["inventory_page"]["scope_line"]
    assert "Price List" in scope and "Omni Channel" in scope and "รวมทุกช่องทาง" in scope
    page = open(os.path.join(root, "forecast", "inventory.html"), encoding="utf-8").read()
    assert 'id="scope-line"' in page and "document.getElementById('scope-line').textContent = DATA.scope_line;" in page
    data = json.loads(re.search(r'<script type="application/json" id="inventory-data">(.*?)</script>', page, re.S).group(1))
    assert data["scope_line"] == scope
    template = open(os.path.join(root, "src", "build_inventory_page.py"), encoding="utf-8").read()
    assert 'id="scope-line"' in template and "DATA.scope_line" in template
