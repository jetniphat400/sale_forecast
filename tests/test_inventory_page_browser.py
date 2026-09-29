"""Operates forecast/inventory.html in a headless browser (Edge, own temp profile, own PID).

The page is built to a temporary folder by src/build_inventory_page.build_page() (no database; see
tests/page_helpers.py) and opened at desktop and phone widths. For each division these tests move
the controls and fail if the numbers they should change do not change, if Min or Max change when
only the warehouse checklist changes, if the left panel is not in view after scrolling, if the
service-level marker does not follow its slider, if totals and tables are empty on load, if the
page has no charts message when the charting library fails, or if the console reports an error.

No tracked file is modified. With no browser available every test here is SKIPPED with a message,
never passed silently.
"""
import time

import pytest

from page_helpers import Edge, build_inventory_html, require_browser

DIVISIONS = ["PEM101", "PEM103", "PEM107"]
CHART_FAIL_MSG = "กราฟโหลดไม่ได้ เครือข่ายอาจบล็อกไลบรารีกราฟ · ตัวเลขและตารางยังใช้ได้ตามปกติ"
MARKER_NAME = "service level ที่เลือก"

SNAP = """(function(){
  function t(id){var e=document.getElementById(id);return e?e.textContent.trim():null}
  function tr(id){return [...document.querySelectorAll('#'+id+' tr')].map(r=>[...r.children].map(c=>c.textContent.trim()))}
  var P=window.__plots||{};
  function ys(id){return (P[id]||[]).map(d=>JSON.stringify(d.y||[]))}
  var items=tr('item-table-body');
  var marker=(P['chart-tradeoff']||[]).filter(d=>d.name==='%s')[0];
  return {stock:t('tot-stock-value'),holding:t('tot-holding-cost'),nItems:t('tot-n-items'),excess:t('tot-excess-count'),
    minmax:items.map(r=>[r[0],r[4],r[5]]),onhand:items.map(r=>[r[0],r[7],r[8],r[9]]),noForecast:tr('no-forecast-table-body'),
    tradeoffLine:(P['chart-tradeoff']||[]).filter(d=>d.name!=='%s').map(d=>JSON.stringify(d.y||[])),
    markerX:marker?marker.x[0]:null, markerY:marker?marker.y[0]:null, minVsCurrent:ys('chart-min-vs-current'),
    curveChart:ys('chart-robust-curve'),curveTotals:t('curve-target-totals'),rsc:t('relative-service-cost-note'),
    curveRows:tr('curve-item-table-body'),targetSlider:t('notlate-slider-value')}
})()""" % (MARKER_NAME, MARKER_NAME)


def set_slider(edge, key, value):
    edge.ev(f"(function(){{var e=document.getElementById('ctrl-{key}'); e.value={value}; "
            f"e.dispatchEvent(new Event('input')); return e.value}})()")
    edge.pump(0.3)


RESET = {"procurement_lead_time_days": 60, "assembly_time_days": 3, "review_interval_days": 30,
         "cycle_service_level": 0.95, "holding_cost_rate_annual": 0.2, "obsolescence_threshold_months": 6}


def select_division(edge, division):
    edge.ev(f"document.getElementById('division-select').value='{division}'; onDivisionChange(); 1")
    edge.pump(0.5)
    for k, v in RESET.items():
        set_slider(edge, k, v)


def changed(a, b):
    return {k for k in a if a[k] != b[k]}


@pytest.fixture(scope="module")
def page_path(tmp_path_factory):
    return build_inventory_html(str(tmp_path_factory.mktemp("inventory_browser") / "inventory.html"))


@pytest.fixture(scope="module")
def edge():
    exe = require_browser()
    e = Edge(exe)
    yield e
    e.close()


@pytest.fixture
def desktop(edge, page_path):
    edge.open(page_path, width=1440, height=900)
    return edge


def test_left_panel_stays_in_view_after_scrolling_to_the_bottom(desktop):
    e = desktop
    assert e.ev("document.documentElement.scrollHeight") > 2 * e.ev("window.innerHeight"), "page too short to test scrolling"
    e.ev("window.scrollTo(0, document.documentElement.scrollHeight); 1")
    e.pump(0.4)
    assert e.ev("window.scrollY") > 500
    box = e.ev("(function(){var r=document.getElementById('control-panel').getBoundingClientRect();"
               "var s=document.getElementById('division-select').getBoundingClientRect();"
               "return {top:r.top,bottom:r.bottom,h:r.height,selTop:s.top,selBottom:s.bottom,vh:window.innerHeight,"
               "pos:getComputedStyle(document.getElementById('control-panel')).position}})()")
    assert box["pos"] == "sticky" and box["h"] > 200
    assert 0 <= box["top"] < box["vh"] - 100, f"panel not in view after scrolling: {box}"
    assert 0 <= box["selTop"] and box["selBottom"] <= box["vh"], f"division selector not in view: {box}"
    # everything in the panel is visible at once at 1440x900 (no inner scrolling, nothing covered), for both divisions
    for division in ("PEM101", "PEM107"):
        e.ev(f"document.getElementById('division-select').value='{division}'; onDivisionChange(); 1")
        e.pump(0.4)
        fit = e.ev("(function(){var c=document.getElementById('control-panel');"
                   "var w=document.querySelector('#warehouse-checklist').getBoundingClientRect();"
                   "var hit=document.elementFromPoint(w.left+10,w.top+w.height/2);"
                   "return {sh:c.scrollHeight,ch:c.clientHeight,coveredBySummary:!!(hit&&hit.closest('#summary-box')),"
                   "sel:document.getElementById('division-select').getBoundingClientRect().top}})()")
        assert fit["sh"] <= fit["ch"] + 1, f"{division}: panel needs inner scrolling at 1440x900: {fit}"
        assert not fit["coveredBySummary"], f"{division}: the summary box covers the warehouse checklist"
        assert fit["sel"] >= 0, f"{division}: division selector out of view"
    assert not e.errors, e.errors


def test_totals_tables_and_summary_are_filled_on_load(desktop):
    s = desktop.ev(SNAP)
    assert s["stock"] not in (None, "-") and s["holding"] not in (None, "-")
    assert s["nItems"] not in (None, "-") and s["excess"] not in (None, "-")
    assert len(s["minmax"]) > 0, "item table is empty on load"
    assert desktop.ev("document.querySelector('#summary-box .summary-title').textContent") == "ผลจากตัวควบคุม"
    assert desktop.ev("document.getElementById('control-scope').textContent") == (
        "ตัวควบคุมชุดนี้มีผลกับ Min/Max ผลรวม ตาราง และกราฟด้านขวา · ไม่มีผลกับกราฟเป้าการส่งทันของ PEM101")
    assert not desktop.errors, desktop.errors


@pytest.mark.parametrize("division", DIVISIONS)
@pytest.mark.parametrize("key,value,expect", [
    ("procurement_lead_time_days", 90, {"stock", "holding", "minmax", "tradeoffLine", "minVsCurrent", "markerY"}),
    ("assembly_time_days", 20, {"stock", "holding", "minmax", "tradeoffLine", "minVsCurrent", "markerY"}),
    ("review_interval_days", 60, {"stock", "holding", "minmax", "tradeoffLine", "minVsCurrent", "markerY"}),
    ("cycle_service_level", 0.99, {"stock", "holding", "minmax", "minVsCurrent", "markerX", "markerY"}),
    ("holding_cost_rate_annual", 0.4, {"holding"}),
])
def test_scenario_control_changes_its_numbers(desktop, division, key, value, expect):
    e = desktop
    select_division(e, division)
    before = e.ev(SNAP)
    set_slider(e, key, value)
    after = e.ev(SNAP)
    got = changed(before, after)
    missing = expect - got
    assert not missing, f"{division} {key}={value}: expected these to change but they did not: {sorted(missing)}"
    if key == "holding_cost_rate_annual":
        assert before["stock"] == after["stock"] and before["minmax"] == after["minmax"], "holding cost rate must not move Min/Max or stock value"
    # the calibrated PEM101 target chart has its own controls, so these sliders must not move it
    assert before["curveChart"] == after["curveChart"] and before["curveTotals"] == after["curveTotals"]
    assert not e.errors, e.errors


@pytest.mark.parametrize("division", DIVISIONS)
def test_obsolescence_threshold_changes_excess_flags(desktop, division):
    e = desktop
    select_division(e, division)
    before = e.ev(SNAP)
    set_slider(e, "obsolescence_threshold_months", 1)
    after = e.ev(SNAP)
    assert e.ev("document.getElementById('val-obsolescence_threshold_months').textContent") == "1mo"
    if division == "PEM103":
        # PEM103 has no item whose cover exceeds any threshold in the range, so its flags cannot move
        assert before["minmax"] == after["minmax"]
    else:
        assert before["excess"] != after["excess"], f"{division}: excess count did not respond to the threshold"
        assert before["onhand"] != after["onhand"], f"{division}: excess flags in the item table did not change"
    assert before["minmax"] == after["minmax"], "the threshold must not change Min or Max"
    assert not e.errors, e.errors


@pytest.mark.parametrize("division", DIVISIONS)
def test_warehouse_checklist_changes_stock_columns_but_never_min_or_max(desktop, division):
    e = desktop
    select_division(e, division)
    before = e.ev(SNAP)
    n = e.ev("document.querySelectorAll('#warehouse-checklist .wh-check').length")
    assert n >= 1
    e.ev("(function(){var c=document.querySelector('#warehouse-checklist .wh-check'); c.checked=false; "
         "c.dispatchEvent(new Event('change')); return 1})()")
    e.pump(0.3)
    after = e.ev(SNAP)
    assert before["minmax"] == after["minmax"], "Min/Max changed when only the warehouse checklist changed"
    assert before["stock"] == after["stock"], "stock value total must not depend on the warehouse checklist"
    assert changed(before, after) & {"onhand", "excess", "noForecast"}, f"{division}: unticking a warehouse changed nothing"
    assert not e.errors, e.errors


@pytest.mark.parametrize("division", DIVISIONS)
def test_service_level_marker_follows_its_slider(desktop, division):
    e = desktop
    select_division(e, division)
    set_slider(e, "cycle_service_level", 0.85)
    a = e.ev(SNAP)
    set_slider(e, "cycle_service_level", 0.97)
    b = e.ev(SNAP)
    assert a["markerX"] == pytest.approx(0.85) and b["markerX"] == pytest.approx(0.97), (a["markerX"], b["markerX"])
    assert a["markerY"] != b["markerY"]
    assert not e.errors, e.errors


def test_pem101_target_section_has_its_own_controls(desktop):
    e = desktop
    select_division(e, "PEM101")
    assert e.ev("document.getElementById('curve-own-controls').textContent") == "ส่วนนี้ปรับได้ด้วยปุ่มเป้าและ slider ในส่วนนี้เท่านั้น"
    before = e.ev(SNAP)
    e.ev("document.getElementById('preset-highest-at-today').click(); 1")
    e.pump(0.3)
    mid = e.ev(SNAP)
    assert changed(before, mid) >= {"curveTotals", "rsc", "curveRows", "curveChart", "targetSlider"}
    assert before["stock"] == mid["stock"], "the target presets must not move the scenario summary"
    e.ev("(function(){var s=document.getElementById('notlate-slider'); s.value=(+s.min + +s.max)/2; "
         "s.dispatchEvent(new Event('input')); return 1})()")
    e.pump(0.3)
    end = e.ev(SNAP)
    assert changed(mid, end) >= {"curveTotals", "rsc", "curveRows", "curveChart", "targetSlider"}
    assert not e.errors, e.errors


def test_changed_numbers_are_highlighted_for_about_a_second(desktop):
    e = desktop
    select_division(e, "PEM101")
    assert e.ev("document.querySelectorAll('.flash').length") == 0
    set_slider(e, "procurement_lead_time_days", 90)
    assert e.ev("document.querySelectorAll('.flash').length") > 0, "no number was highlighted after a control change"
    assert e.ev("document.querySelector('#tot-stock-value').classList.contains('flash')")
    time.sleep(1.6)
    assert e.ev("document.querySelectorAll('.flash').length") == 0, "highlight did not clear"
    assert not e.errors, e.errors


def test_page_without_the_charting_library_still_shows_numbers_and_the_message(edge, page_path):
    edge.open(page_path, width=1440, height=900, cdn="fail")
    assert edge.ev("typeof Plotly") == "undefined"
    s = edge.ev(SNAP)
    assert s["stock"] not in (None, "-") and len(s["minmax"]) > 0, "totals or tables empty when the library fails to load"
    for chart in ("chart-tradeoff", "chart-min-vs-current", "chart-robust-curve"):
        text = edge.ev(f"document.getElementById('{chart}').textContent")
        assert text.strip() == CHART_FAIL_MSG, (chart, text)
    set_slider(edge, "procurement_lead_time_days", 90)
    assert edge.ev(SNAP)["stock"] != s["stock"], "controls stopped working without the library"
    scripts = [x for x in edge.errors if x.startswith("exception")]
    assert not scripts, f"script errors when the library failed to load: {scripts}"


def test_phone_width_panel_is_collapsible_and_page_does_not_scroll_sideways(edge, page_path):
    edge.open(page_path, width=390, height=844, mobile=True)
    assert edge.ev("window.innerWidth") <= 400
    assert edge.ev("getComputedStyle(document.getElementById('panel-toggle')).display") != "none"
    assert edge.ev("getComputedStyle(document.getElementById('panel-body')).display") == "none", "panel should start collapsed on a phone"
    arrow = edge.ev("getComputedStyle(document.getElementById('panel-toggle'),'::after').content")
    assert "▸" in arrow, f"toggle arrow does not render as the intended glyph: {arrow!r}"
    assert edge.ev("document.documentElement.scrollWidth <= window.innerWidth + 1"), "page scrolls sideways (collapsed)"
    edge.ev("document.getElementById('panel-toggle').click(); 1")
    edge.pump(0.3)
    assert edge.ev("getComputedStyle(document.getElementById('panel-body')).display") != "none"
    assert edge.ev("document.getElementById('panel-toggle').getAttribute('aria-expanded')") == "true"
    assert edge.ev("document.documentElement.scrollWidth <= window.innerWidth + 1"), "page scrolls sideways (expanded)"
    edge.ev("document.getElementById('panel-toggle').click(); 1")
    edge.pump(0.2)
    assert edge.ev("getComputedStyle(document.getElementById('panel-body')).display") == "none"
    for division in ("PEM107", "PEM101"):
        edge.ev(f"document.getElementById('division-select').value='{division}'; onDivisionChange(); 1")
        edge.pump(0.4)
        assert edge.ev("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"{division}: page scrolls sideways at 390px"
    assert not edge.errors, edge.errors
