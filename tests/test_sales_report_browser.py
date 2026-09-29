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
    assert edge.ev("document.querySelector('#results h2').textContent").startswith("6.")
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
