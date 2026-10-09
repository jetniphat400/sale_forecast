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
# PEM103 follows METRICS.md Sec.23 since 2026-10-06 and has no stock_policy item, so it shows no Min and Max rows: the tests that move a control and expect
# Min, Max or stock figures to move run for the divisions that have them; PEM103's page is checked in test_operation_plan_page_builder.py.
MIN_MAX_DIVISIONS = ["PEM101", "PEM107"]
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
    minmax:items.map(r=>[r[0],r[4],r[5]]),onhand:items.map(r=>[r[0],r[8],r[9],r[10]]),noForecast:tr('no-forecast-table-body'),
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
    return build_inventory_html(str(tmp_path_factory.mktemp("inventory_browser") / "forecast" / "inventory.html"))


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


@pytest.mark.parametrize("division", MIN_MAX_DIVISIONS)
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


@pytest.mark.parametrize("division", MIN_MAX_DIVISIONS)
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


# ------------------------------------------------------------------ summary count, relative-cost sentences, status labels

COUNT_JS = """(function(){
  var rows=[...document.querySelectorAll('#item-table-body tr')];
  var showing=rows.filter(function(r){var mn=r.children[4].textContent.trim(),mx=r.children[5].textContent.trim();
    return mn!=='-' && mx!=='-';}).length;
  return {shown:document.getElementById('tot-n-items').textContent.trim(), rowsWithMinMax:showing, rows:rows.length}})()"""


@pytest.mark.parametrize("division", MIN_MAX_DIVISIONS)
def test_summary_count_equals_item_table_rows_showing_a_min_and_max(desktop, division):
    e = desktop
    select_division(e, division)
    settings = [dict(RESET),
                dict(RESET, procurement_lead_time_days=90, cycle_service_level=0.99, assembly_time_days=10)]
    for setting in settings:
        for k, v in setting.items():
            set_slider(e, k, v)
        c = e.ev(COUNT_JS)
        assert c["rows"] > 0
        assert c["shown"] == str(c["rowsWithMinMax"]), f"{division} {setting}: summary shows {c['shown']}, table has {c['rowsWithMinMax']} rows with a Min and Max"
    # the count must not be the old always-zero value for the divisions that use the class rule
    assert e.ev(COUNT_JS)["rowsWithMinMax"] > 0
    assert not e.errors, e.errors


def _target_sentence(e):
    return e.ev("document.getElementById('relative-service-cost-note').textContent").strip()


def _set_target(e, value):
    e.ev(f"(function(){{var s=document.getElementById('notlate-slider'); s.value={value}; "
         f"s.dispatchEvent(new Event('input')); return 1}})()")
    e.pump(0.3)


def test_relative_cost_sentence_follows_the_sign_of_the_median(desktop):
    import re
    e = desktop
    select_division(e, "PEM101")
    lo = float(e.ev("document.getElementById('notlate-slider').min"))
    hi = float(e.ev("document.getElementById('notlate-slider').max"))
    minus = "−"
    range_re = r"\(ช่วง ([+" + minus + r"])(\d+\.\d)% ถึง ([+" + minus + r"])(\d+\.\d)%\)"
    # above today: the increase sentence, "+" before the median and signed range bounds
    e.ev("document.getElementById('preset-stretch').click(); 1")
    e.pump(0.3)
    today_pct = e.ev("document.getElementById('preset-today-lowest').textContent")
    up = _target_sentence(e)
    m = re.match(r"ต้องเพิ่ม stock \+(\d+\.\d)% " + range_re + r" เพื่อขยับการส่งไม่ช้าจาก (\d+\.\d+)% เป็น (\d+\.\d+)%", up)
    assert m, f"sentence above today is not the increase sentence: {up}"
    assert float(m.group(1)) > 0 and m.group(2) == "+" and m.group(4) == "+", up
    assert float(m.group(7)) > float(m.group(6))
    # below today: the reduction sentence, range bounds carry minus signs
    _set_target(e, (lo + hi) / 2)
    down = _target_sentence(e)
    m = re.match(r"ลด stock ได้ (\d+\.\d)% " + range_re + r" ถ้ายอมให้การส่งไม่ช้าลดจาก (\d+\.\d+)% เป็น (\d+\.\d+)%", down)
    assert m, f"sentence below today is not the reduction sentence: {down}"
    assert m.group(2) == minus and m.group(4) == minus, f"a reduction range must carry minus signs: {down}"
    assert float(m.group(7)) < float(m.group(6))
    assert "+-" not in down and "ต้องเพิ่ม" not in down
    # at today's own level the range straddles zero: both signs show
    e.ev("document.getElementById('preset-today-lowest').click(); 1")
    e.pump(0.3)
    mid = _target_sentence(e)
    m = re.search(range_re, mid)
    assert m and m.group(1) == minus and m.group(3) == "+", f"a range crossing zero must read minus to plus: {mid}"
    assert mid.startswith("ต้องเพิ่ม stock +")
    assert not e.errors, e.errors


@pytest.mark.parametrize("division", DIVISIONS)
def test_placeholder_status_values_show_their_approved_labels(desktop, division):
    e = desktop
    select_division(e, division)
    cells = e.ev("[...document.querySelectorAll('#no-policy-table-body tr')].map(r=>r.children[2].textContent.trim())")
    raw = [c for c in cells if c.startswith("placeholder - ") or c.startswith("excluded - ")]
    assert not raw, f"{division}: raw status values are still shown: {sorted(set(raw))}"
    allowed = {"ไม่มีประวัติขาย (รอวิธีประมาณ)", "ไม่มีประวัติขาย (กำหนดวิธีประมาณแล้ว)",
               "ตัดออก มีใน Price List แต่ไม่เคยขาย", "ตัดออก ทั้งฝ่ายไม่ใช้นโยบาย stock"}
    assert set(cells) <= allowed, sorted(set(cells) - allowed)


# ------------------------------------------------------------------ the system's Max: 0 is shown as not filled in
@pytest.mark.parametrize("division", MIN_MAX_DIVISIONS)
def test_a_system_max_of_zero_shows_as_not_filled_in_and_the_total_leaves_those_rows_out(desktop, division):
    from page_helpers import fresh_inventory_data
    e = desktop
    select_division(e, division)
    items = {i["code"]: i for i in fresh_inventory_data()["divisions"][division]["items"]}
    rows = e.ev("[...document.querySelectorAll('#item-table-body tr')].map(r=>[r.children[0].textContent.trim(), r.children[7].textContent.trim()])")
    assert rows
    not_filled = [c for c, t in rows if t == "ไม่ได้กรอก"]
    expected = [c for c, _ in rows if items[c].get("current_has_record") and items[c].get("current_max") == 0]
    assert sorted(not_filled) == sorted(expected), "every listed item whose system Max is 0 shows ไม่ได้กรอก, and no other item does"
    # an item with no record in the system shows a dash, never ไม่ได้กรอก and never 0
    no_record = [c for c, t in rows if not items[c].get("current_has_record")]
    assert all(dict(rows)[c] == "-" for c in no_record)
    # the total adds only filled-in Max values and says how many rows it leaves out
    filled = sum(items[c]["current_max"] for c, _ in rows if items[c].get("current_has_record") and (items[c].get("current_max") or 0) > 0)
    assert e.ev("document.getElementById('system-max-total').textContent.replace(/,/g,'')") == str(round(filled))
    assert e.ev("document.getElementById('system-max-note').textContent") == f"ไม่รวม {len(expected)} รายการที่ไม่ได้กรอก Max"
    assert not [x for x in e.errors if x.startswith("exception")], e.errors


def test_some_item_on_the_page_has_a_system_max_of_zero(desktop):
    """Guards the test above against passing on an empty set: today's data has such items in PEM101, PEM103 and PEM107."""
    from page_helpers import fresh_inventory_data
    data = fresh_inventory_data()["divisions"]
    assert any(i.get("current_has_record") and i.get("current_max") == 0 for d in data.values() for i in d["items"])


# ------------------------------------------------------------------ the 21 items whose class the user set from the data
PENDING_LABEL = "จัดตามข้อมูล รอยืนยัน"


def test_each_of_the_21_decided_items_carries_the_label_beside_its_class_and_no_other_item_does(desktop):
    from page_helpers import fresh_inventory_data
    e = desktop
    select_division(e, "PEM101")
    items = {i["code"]: i for i in fresh_inventory_data()["divisions"]["PEM101"]["items"]}
    decided = sorted(c for c, i in items.items() if i.get("class_basis"))
    assert len(decided) == 21
    # every table that shows an item's class: the item table, the no-forecast table, the class table
    shown = {}
    for table in ("item-table-body", "no-forecast-table-body", "class-table-body"):
        for code, cell in e.ev(f"[...document.querySelectorAll('#{table} tr')].map(r=>[r.children[0].textContent.trim(), "
                               f"(table => table === 'class-table-body' ? r.children[3] : r.children[1])('{table}').textContent])"):
            shown.setdefault(code, []).append(cell)
    for code in decided:
        assert code in shown, f"{code} is shown in no table"
        assert all(PENDING_LABEL in cell for cell in shown[code]), (code, shown[code])
    others = [c for c in shown if c not in decided]
    assert others and not [c for c in others if any(PENDING_LABEL in cell for cell in shown[c])]
    # the new stock_policy count is the one the calibrated-target note states
    n_stock = sum(1 for i in items.values() if i["policy"] == "stock_policy")
    assert n_stock == 92
    assert f"{n_stock} รายการ" in e.ev("document.body.textContent")
    assert not [x for x in e.errors if x.startswith("exception")], e.errors


# ====================================================================================================== 2026-10-08: the data line, the PEM101 demand note, the no-forecast list, the bar
@pytest.mark.parametrize("division", DIVISIONS)
def test_the_no_forecast_list_holds_only_items_with_stock_and_no_forecast_month_in_the_page_vintage(desktop, division):
    import stock_daily
    from inventory_recompute_reference import compute_all
    from page_helpers import fresh_inventory_data, load_stock_payload
    data = stock_daily.apply_to_data(fresh_inventory_data(), load_stock_payload())
    r = compute_all(data["divisions"][division], data["tier_a_defaults"], data["days_per_month"])
    expected = sorted(p["code"] for p in r["per_item"] if p["no_vintage_forecast"] and p["on_hand_sellable"] > 0)
    select_division(desktop, division)
    rows = desktop.ev(SNAP)["noForecast"]
    assert sorted(x[0] for x in rows) == expected
    # an item with a forecast is never listed, whatever its class
    with_forecast = {i["code"] for i in data["divisions"][division]["items"] if any(v > 0 for v in i["forecast"])}
    assert not {x[0] for x in rows} & with_forecast


def test_the_data_line_shows_the_round_and_the_stock_pull_time_and_the_script_formats_dates_like_the_shared_formatter(desktop):
    import reader_values as rv
    from page_helpers import load_stock_payload
    payload = load_stock_payload()
    expected = f"Forecast (ยอดทาย) รันเมื่อ {rv.thai_month_short(rv.vintage_facts()['run_date'])} · ข้อมูล stock ดึงเมื่อ {rv.thai_datetime_short(payload['pull_time'])}"
    assert desktop.ev("document.getElementById('data-line').innerText") == expected
    assert desktop.ev("document.getElementById('page-title').nextElementSibling.id") == "data-line"
    for stamp in ("2026-10-08 08:01:01", "2027-01-05 00:09:59", "2026-12-31 23:59:00", "2026-03-09 12:00:00"):
        assert desktop.ev(f"thaiDateTime('{stamp}')") == rv.thai_datetime_short(stamp), stamp


def test_the_pem101_section_says_its_min_and_max_come_from_sales_history(desktop):
    import yaml
    import maxmin_v1
    import reader_values as rv
    select_division(desktop, "PEM101")
    first, last = maxmin_v1.demand_history_window()
    with open(__import__("os").path.join(__import__("page_helpers").PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        template = yaml.safe_load(f)["inventory_page"]["pem101_demand_note"]
    expected = template.format(first_month=rv.thai_month_short(first), last_month=rv.thai_month_short(last))
    assert expected.startswith("Min/Max ส่วนนี้คิดจากยอดขายจริงย้อนหลัง ") and expected.endswith("ยังไม่ได้คิดจากยอดทาย ถ้ายอดขายข้างหน้าเพิ่มหรือลดมาก ค่านี้จะยังไม่ขยับตาม")
    assert desktop.ev("document.getElementById('curve-demand-note').textContent") == expected
    assert desktop.ev("document.getElementById('curve-demand-note').previousElementSibling.tagName") == "H2"
    assert "{" not in expected and "}" not in expected


def test_the_page_has_no_bar_and_keeps_its_back_link_and_its_link_to_the_operation_plan(desktop):
    assert desktop.ev("document.getElementById('page-nav')") is None
    assert desktop.ev("document.querySelector('a.back-link').nextElementSibling.id") == "plan-link"
    assert desktop.ev("(function(){const a=document.getElementById('plan-link'); return [a.innerText.trim(), a.getAttribute('href')]})()") == ["แผนการผลิต", "operation_plan.html"]
