"""Operates forecast/sales_report.html in a headless browser (Edge, own temp profile, own PID).

The page is built to a temporary folder by src/build_report.build_report(output_path=...) from the data
already on disk. With the charting library blocked the text, the tables and the data-date table must
still render and every chart area must show the message; with it available (a stand-in that records
the traces) every chart is drawn and the console reports no error. No tracked file is modified. With no
browser available every test here is SKIPPED with a message, never passed silently.
"""
import pytest

from page_helpers import Edge, require_browser

CHART_FAIL_MSG = "กราฟโหลดไม่ได้ เครือข่ายอาจบล็อกไลบรารีกราฟ · ตัวเลขและตารางยังใช้ได้ตามปกติ"
CHARTS = ["chart-notice", "chart-ontime", "chart-model", "chart-rolling", "chart-fva"]


@pytest.fixture(scope="module")
def page_path(tmp_path_factory):
    import build_report
    return build_report.build_report(output_path=str(tmp_path_factory.mktemp("sales_browser") / "sales_report.html"))


@pytest.fixture(scope="module")
def edge():
    e = Edge(require_browser())
    yield e
    e.close()


def test_without_the_charting_library_text_and_tables_render_and_charts_show_the_message(edge, page_path):
    edge.open(page_path, cdn="fail")
    assert edge.ev("typeof Plotly") == "undefined"
    scripts = [x for x in edge.errors if x.startswith("exception")]
    assert not scripts, f"script errors when the library failed to load: {scripts}"
    for chart in CHARTS:
        assert edge.ev(f"document.getElementById('{chart}').textContent").strip() == CHART_FAIL_MSG, chart
    # text and sections
    assert edge.ev("document.querySelectorAll('section').length") >= 8
    assert edge.ev("document.querySelector('#results h2').textContent").startswith("7.")
    # the tables the page's script fills, and the data-date table
    assert edge.ev("document.querySelectorAll('#primary-results-table tbody tr').length") > 0
    assert edge.ev("document.querySelectorAll('#div-results-table tbody tr').length") > 0
    freshness = edge.ev("document.querySelector('details table').textContent")
    assert "ช่วงข้อมูลหลัก" in freshness and "กราฟส่งไม่ช้า" in freshness
    assert edge.ev("document.querySelectorAll('details table tbody tr').length") == 7
    # the selectors still work and the type list is filled
    edge.ev("document.getElementById('filterDivision').value='PEM101'; "
            "document.getElementById('filterDivision').dispatchEvent(new Event('change')); 1")
    edge.pump(0.3)
    assert edge.ev("document.querySelectorAll('#primary-results-table tbody tr').length") == 1
    assert edge.ev("document.querySelectorAll('#filterType option').length") > 1
    scripts = [x for x in edge.errors if x.startswith("exception")]
    assert not scripts, scripts


def test_with_the_charting_library_every_chart_is_drawn_and_the_console_is_clean(edge, page_path):
    edge.open(page_path, cdn="stub")
    drawn = edge.ev("Object.keys(window.__plots).sort()")
    assert drawn == sorted(CHARTS), drawn
    for chart in CHARTS:
        assert CHART_FAIL_MSG not in edge.ev(f"document.getElementById('{chart}').textContent")
    edge.ev("document.getElementById('filterDivision').value='PEM107'; "
            "document.getElementById('filterDivision').dispatchEvent(new Event('change')); 1")
    edge.pump(0.3)
    assert not edge.errors, edge.errors


# ---- unit switch of section 2 (pieces / baht), Prompt 10 -------------------------------------------------------------------------------

def _visible_block(edge, selector):
    return " ".join(edge.ev(f"(function(){{var e=document.querySelector('{selector}'); return e ? e.innerText : '';}})()").split())


def _shown(edge, selector):
    """True when the element exists and is rendered (not display:none, not hidden, inside no hidden parent)."""
    return bool(edge.ev(f"(function(){{var e=document.querySelector('{selector}'); return !!e && e.getClientRects().length > 0;}})()"))


def _click_unit(edge, unit):
    edge.ev(f"document.querySelector('#unitSwitch button[data-unit={unit}]').click(); 1")
    edge.pump(0.2)


def _select_division(edge, division):
    edge.ev(f"var s=document.getElementById('fwdDivision'); s.value='{division}'; s.dispatchEvent(new Event('change')); 1")
    edge.pump(0.2)


def test_the_unit_switch_shows_pieces_by_default_and_baht_on_request_and_keeps_the_division(edge, page_path):
    edge.open(page_path, cdn="stub")
    text = _visible_block(edge, "#forward-forecast")
    assert "หน่วย: ชิ้น · บาท (มีผลกับตารางในส่วนนี้เท่านั้น)" in text
    # default: pieces, the current view
    assert edge.ev("Array.from(document.querySelectorAll('#unitSwitch button')).map(b => b.getAttribute('aria-pressed')).join()") == "true,false"
    assert _shown(edge, ".fwd-table-wrap:not([hidden])") and not _shown(edge, "#baht-label") and not _shown(edge, "#baht-summary-table")
    assert "ยอดทายรวมรายเดือน (บาท)" not in text and "มูลค่าคิดจากราคาขายเฉลี่ยจริงของแต่ละรหัส" not in text
    divisions = edge.ev("Array.from(document.querySelectorAll('#fwdDivision option')).map(o => o.value)")
    assert len(divisions) >= 2
    second = divisions[1]
    _select_division(edge, second)
    _click_unit(edge, "baht")
    # baht mode: label, explanation, summary table, the baht table of the SAME division with its total row; the pieces table is hidden
    assert edge.ev("document.getElementById('fwdDivision').value") == second
    text = _visible_block(edge, "#forward-forecast")
    assert "มูลค่าคิดจากราคาขายเฉลี่ยจริงของแต่ละรหัส" in text and "ยอดทายรวมรายเดือน (บาท)" in text and "รวมทุกฝ่าย" in text
    assert "▸ ยอดทายคิดเป็นเงินเท่าไหร่ต่อเดือน ▸ ตัวเลข = ยอดทาย (ชิ้น) × ราคาขายเฉลี่ยของรหัสนั้น หน่วยบาท" in text
    assert "▸ แถว = ประเภทสินค้า · คอลัมน์ = เดือน · ตัวเลข = จำนวนชิ้น" not in text                      # the pieces explanation is not shown over baht
    assert not _shown(edge, ".fwd-table-wrap") and _shown(edge, f".fwd-baht-wrap[data-division={second}]")
    assert edge.ev("document.querySelectorAll('.fwd-baht-wrap:not([hidden])').length") == 1
    assert edge.ev(f"document.querySelector('.fwd-baht-wrap[data-division={second}] tr.total-row td').textContent") == f"รวม {second}"
    # the division selector keeps working in baht mode, and a Type row expands to its items
    _select_division(edge, divisions[0])
    assert _shown(edge, f".fwd-baht-wrap[data-division={divisions[0]}]") and not _shown(edge, f".fwd-baht-wrap[data-division={second}]")
    edge.ev(f"document.querySelector('.fwd-baht-wrap[data-division={divisions[0]}] tr.fwd-btype').click(); 1")
    assert edge.ev(f"document.querySelectorAll('.fwd-baht-wrap[data-division={divisions[0]}] tr.fwd-bitem:not([hidden])').length") > 0
    # back to pieces: the same division is selected and the pieces table of it is shown again
    _click_unit(edge, "pieces")
    assert edge.ev("document.getElementById('fwdDivision').value") == divisions[0]
    assert _shown(edge, f".fwd-table-wrap[data-division={divisions[0]}]") and not _shown(edge, "#baht-summary-table")
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors


def test_no_horizontal_page_scroll_at_phone_width_in_both_modes(edge, page_path):
    edge.open(page_path, width=390, height=844, mobile=True, cdn="stub")
    for unit in ("pieces", "baht"):
        _click_unit(edge, unit)
        for division in edge.ev("Array.from(document.querySelectorAll('#fwdDivision option')).map(o => o.value)")[:2]:
            _select_division(edge, division)
            assert edge.ev("document.documentElement.scrollWidth") <= edge.ev("document.documentElement.clientWidth"), (unit, division)
    edge.ev("document.getElementById('scored-table').scrollIntoView(); 1")
    assert edge.ev("document.documentElement.scrollWidth") <= 390                                         # the forecast-versus-actual table scrolls inside its own box
