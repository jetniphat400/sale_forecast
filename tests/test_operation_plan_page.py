"""Screen checks for week 2, in a headless browser (own Edge on a temp profile, own PID, closed by PID only): the page is built to a temporary
site folder by the builder (no database); no tracked file is modified.

  * the D3 line shows with its values (median over items with observed purchase records, their count, the items shown);
  * the Min and Max the plan takes as "the page's default on load" equal what the page renders on load: the PEM101 calibrated section's item table
    and the PEM107 item table, so the Python port in src/operation_plan.py and the page's own script agree;
  * the controls still change the figures they claim to (the preset buttons and the slider move the calibrated section's table).
With no browser, or without the recorded outputs, a test is SKIPPED with a message, never passed silently."""
import os
import re
import time

import pandas as pd
import pytest

from page_helpers import Edge, PROJECT_ROOT, fresh_inventory_data, load_stock_payload, require_browser, write_stock_file

import operation_plan as op  # noqa: E402
import maxmin_v1 as mm  # noqa: E402

D3_LINE = "lead time วัตถุดิบจากใบสั่งซื้อจริง ค่ากลาง {median} วัน (มีข้อมูล {n_observed} จาก {n_items} รายการ) ใช้สำหรับวางแผนสั่งวัตถุดิบ ไม่ได้ใช้คำนวณ Min/Max ของสินค้า"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    cfg = mm.load_config()
    for rel in (cfg["item_lead_time_file"], cfg["dense_grid_file"], cfg["ensemble_members_file"]):
        if not os.path.exists(mm.path_of(rel)):
            pytest.skip("SKIPPED, not passed: recorded output missing on this machine: " + rel)
    import build_inventory_page as bp
    data = fresh_inventory_data()
    mp = pytest.MonkeyPatch()
    mp.setattr(bp, "build_data", lambda **kw: data)
    try:
        page = bp.build_page()
    finally:
        mp.undo()
    d = tmp_path_factory.mktemp("week2_screen")
    out = d / "forecast" / "inventory.html"
    out.parent.mkdir(parents=True)
    out.write_text(page, encoding="utf-8")
    write_stock_file(str(d), load_stock_payload())
    return str(out), data


@pytest.fixture(scope="module")
def edge(site):
    e = Edge(require_browser())
    e.open(site[0])
    assert _wait(e, "document.getElementById('stock-labels').style.display !== 'none'"), "the page did not finish loading"
    yield e
    e.close()


def _wait(edge, expr, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if edge.ev(expr):
            return True
        edge.pump(0.2)
    return False


def _select(edge, division):
    edge.ev(f"document.getElementById('division-select').value='{division}'; onDivisionChange(); 1")
    edge.pump(0.5)


def _num(text):
    return float(re.sub(r"[^\d.\-]", "", text))


def _js_round(x):
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def test_the_d3_line_shows_with_its_values_and_replaces_the_old_wording(edge, site):
    _select(edge, "PEM101")
    assert _wait(edge, "document.getElementById('curve-item-table-body').children.length > 0")
    lines = [l.strip() for l in edge.ev("document.getElementById('curve-lead-lines').innerText").split("\n") if l.strip()]
    lead = pd.read_csv(mm.path_of(mm.load_config()["item_lead_time_file"]))
    obs = lead[lead["bottleneck_source"] == "observed"]["bottleneck_days"]
    expected = D3_LINE.format(median=f"{float(obs.median()):g}", n_observed=len(obs), n_items=len(lead))
    assert lines[1] == expected, lines
    assert "ยาวกว่านี้" not in " ".join(lines)
    ll = site[1]["divisions"]["PEM101"]["curve_target"]["lead_time_lines"]
    assert (ll["material_lead_median_observed"], ll["n_observed"], ll["n_items"]) == (float(obs.median()), len(obs), len(lead))
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors


def test_the_pem101_default_min_and_max_equal_what_the_page_renders_on_load(edge, site):
    data = site[1]
    _select(edge, "PEM101")
    assert _wait(edge, "document.getElementById('curve-item-table-body').children.length > 0")
    rows = edge.ev("[...document.querySelectorAll('#curve-item-table-body tr')].map(r=>[...r.children].map(c=>c.textContent.trim()))")
    shown = {r[0]: (_num(r[1]), _num(r[2])) for r in rows}
    mm_ = op.page_default_min_max(data, "PEM101")
    stock = mm_[mm_["class"] == "stock_policy"]
    assert len(shown) == len(stock) == 92 and set(shown) == set(stock["item"])
    for _, r in stock.iterrows():
        assert abs(shown[r["item"]][0] - _js_round(r["min"])) <= 1 and abs(shown[r["item"]][1] - _js_round(r["max"])) <= 1, r["item"]


def test_the_pem107_default_min_and_max_equal_what_the_page_renders_on_load(edge, site):
    data = site[1]
    _select(edge, "PEM107")
    assert _wait(edge, "document.getElementById('item-table-body').children.length > 0")
    rows = edge.ev("[...document.querySelectorAll('#item-table-body tr')].map(r=>[...r.children].map(c=>c.textContent.trim()))")
    shown = {r[0]: (r[4], r[5]) for r in rows}
    mm_ = op.page_default_min_max(data, "PEM107")
    stock = mm_[mm_["class"] == "stock_policy"]
    assert len(stock) == 4 and set(stock["item"]) <= set(shown)
    for _, r in stock.iterrows():
        lo, hi = shown[r["item"]]
        assert abs(_num(lo) - _js_round(r["min"])) <= 1 and abs(_num(hi) - _js_round(r["max"])) <= 1, r["item"]
    _select(edge, "PEM101")


def test_the_calibrated_section_controls_still_move_the_figures_they_claim_to(edge):
    _select(edge, "PEM101")
    assert _wait(edge, "document.getElementById('curve-item-table-body').children.length > 0")
    first = lambda: edge.ev("[...document.querySelectorAll('#curve-item-table-body tr')].map(r=>r.children[1].textContent).join('|')")
    edge.ev("document.getElementById('preset-today-lowest').click(); 1")
    edge.pump(0.3)
    at_today = first()
    edge.ev("document.getElementById('preset-stretch').click(); 1")
    edge.pump(0.3)
    at_stretch = first()
    assert at_today != at_stretch, "the stretch preset did not change the item table"
    assert not [x for x in edge.errors if x.startswith("exception")], edge.errors
    edge.ev("document.getElementById('preset-today-lowest').click(); 1")
