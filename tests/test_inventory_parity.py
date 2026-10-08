"""Part 4 parity tests: forecast/inventory.html's client-side JS (run for real in Node, not
re-implemented by hand for the test) must produce Min/Max/stock_value identical (within a tight
float tolerance) to src/inventory_recompute_reference.py's pure-Python mirror, operating on the
SAME embedded JSON -- at the default scenario and at one non-default control setting, for EACH
enabled division (PEM101, PEM103, PEM107 -- Phase E2 Part 3, 2026-09-22).

Tolerance: 1e-6 relative (rtol) via math.isclose -- both languages do IEEE-754 double arithmetic
on the same operations in the same order, so exact-to-many-decimal-places agreement is expected;
this is not a loosened tolerance to force a pass, it is the ordinary floating-point equality
tolerance for two independent implementations of the same arithmetic.
"""
import json
import math
import os
import re
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
INVENTORY_HTML = os.path.join(PROJECT_ROOT, "forecast", "inventory.html")

import stock_daily
from inventory_recompute_reference import compute_all as python_compute_all
from page_helpers import load_stock_payload

DEFAULT_CONTROLS = {"procurement_lead_time_days": 60, "assembly_time_days": 3,
                    "review_interval_days": 30, "cycle_service_level": 0.95,
                    "holding_cost_rate_annual": 0.20, "obsolescence_threshold_months": 6}
NON_DEFAULT_CONTROLS = {"procurement_lead_time_days": 45, "assembly_time_days": 7,
                        "review_interval_days": 14, "cycle_service_level": 0.90,
                        "holding_cost_rate_annual": 0.15, "obsolescence_threshold_months": 3}
DIVISIONS = ["PEM101", "PEM103", "PEM107"]


def _load_html():
    with open(INVENTORY_HTML, "r", encoding="utf-8") as f:
        return f.read()


def _extract_embedded_data():
    html_text = _load_html()
    m = re.search(r'<script type="application/json" id="inventory-data">(.*?)</script>', html_text, re.DOTALL)
    assert m, "Embedded #inventory-data JSON block not found in forecast/inventory.html"
    return json.loads(m.group(1))


def _extract_recompute_js():
    html_text = _load_html()
    m = re.search(r"const DATA = JSON\.parse.*?// END_RECOMPUTE_JS", html_text, re.DOTALL)
    assert m, "RECOMPUTE_JS block not found in forecast/inventory.html (missing // END_RECOMPUTE_JS marker)"
    return m.group(0)


def _run_js_compute_all(division: str, controls: dict, tmp_path, checked_warehouses=None, mutate=None) -> dict:
    """Writes the page's REAL extracted JS (not a hand re-implementation) to a temp file, with the
    document.getElementById(...) DOM read replaced by a literal JSON injection (Node has no DOM),
    and calls computeAll(controls, DATA.divisions[division], checkedWarehouses) via a tiny runner
    appended at the end."""
    js_block = _extract_recompute_js()
    data = _extract_embedded_data()
    if mutate:
        mutate(data)
    js_block = js_block.replace(
        "const DATA = JSON.parse(document.getElementById('inventory-data').textContent);",
        f"const DATA = {json.dumps(data)};")
    wh_arg = json.dumps(checked_warehouses) if checked_warehouses is not None else "undefined"
    # the page loads its stock file when it opens; here the page's own applyStock puts the tracked file's stock into DATA
    runner = (f"\napplyStock(DATA, {json.dumps(load_stock_payload())});\n"
              f"console.log(JSON.stringify(computeAll({json.dumps(controls)}, "
              f"DATA.divisions[{json.dumps(division)}], {wh_arg})));\n")
    js_path = tmp_path / f"inventory_recompute_extracted_{division}.js"
    js_path.write_text(js_block + runner, encoding="utf-8")
    result = subprocess.run(["node", str(js_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"Node execution failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def _compare(js_result: dict, py_result: dict, label: str, check_excess: bool = False):
    assert math.isclose(js_result["stockValue"], py_result["stock_value"], rel_tol=1e-6, abs_tol=1e-4), \
        f"[{label}] stock_value mismatch: JS={js_result['stockValue']} Python={py_result['stock_value']}"
    js_by_code = {r["code"]: r for r in js_result["perItem"]}
    py_by_code = {r["code"]: r for r in py_result["per_item"]}
    assert set(js_by_code) == set(py_by_code), f"[{label}] item sets differ between JS and Python"
    assert {c for c, r in js_by_code.items() if r["noVintageForecast"]} == {c for c, r in py_by_code.items() if r["no_vintage_forecast"]},         f"[{label}] the items with no forecast in the page's vintage differ between JS and Python"
    mismatches = []
    for code, py_r in py_by_code.items():
        js_r = js_by_code[code]
        for field_js, field_py in [("min", "min"), ("max", "max")]:
            jv, pv = js_r[field_js], py_r[field_py]
            if jv is None and pv is None:
                continue
            if jv is None or pv is None or not math.isclose(jv, pv, rel_tol=1e-6, abs_tol=1e-4):
                mismatches.append((code, field_py, jv, pv))
    assert not mismatches, f"[{label}] Min/Max mismatches (code, field, JS, Python): {mismatches[:10]}"

    if check_excess:
        assert js_result["excessCount"] == py_result["excess_count"], (
            f"[{label}] excessCount mismatch: JS={js_result['excessCount']} Python={py_result['excess_count']}"
        )
        excess_mismatches = []
        for code, py_r in py_by_code.items():
            js_r = js_by_code[code]
            if not math.isclose(js_r["onHandSellable"], py_r["on_hand_sellable"], rel_tol=1e-6, abs_tol=1e-4):
                excess_mismatches.append((code, "onHandSellable", js_r["onHandSellable"], py_r["on_hand_sellable"]))
            # JSON.stringify(Infinity) === null -- JS's monthsOfCover comes back None exactly when
            # Python's is float('inf'); both mean the same thing (no forecast in the window).
            js_moc, py_moc = js_r["monthsOfCover"], py_r["months_of_cover"]
            py_is_inf = isinstance(py_moc, float) and math.isinf(py_moc)
            if py_is_inf != (js_moc is None):
                excess_mismatches.append((code, "monthsOfCover_infinite_mismatch", js_moc, py_moc))
            elif not py_is_inf and not math.isclose(js_moc, py_moc, rel_tol=1e-6, abs_tol=1e-4):
                excess_mismatches.append((code, "monthsOfCover", js_moc, py_moc))
            if bool(js_r["excess"]) != bool(py_r["excess"]):
                excess_mismatches.append((code, "excess", js_r["excess"], py_r["excess"]))
        assert not excess_mismatches, f"[{label}] on_hand/months_of_cover/excess mismatches: {excess_mismatches[:10]}"


@pytest.fixture(scope="module")
def embedded_data():
    # the page embeds no stock; the Python side takes it from the same tracked stock file the page loads
    return stock_daily.apply_to_data(_extract_embedded_data(), load_stock_payload())


@pytest.mark.parametrize("division", DIVISIONS)
def test_js_matches_python_at_default_scenario(division, tmp_path, embedded_data):
    js_result = _run_js_compute_all(division, DEFAULT_CONTROLS, tmp_path)
    py_result = python_compute_all(embedded_data["divisions"][division], DEFAULT_CONTROLS, embedded_data["days_per_month"])
    _compare(js_result, py_result, f"{division} default scenario")


@pytest.mark.parametrize("division", DIVISIONS)
def test_js_matches_python_at_non_default_scenario(division, tmp_path, embedded_data):
    js_result = _run_js_compute_all(division, NON_DEFAULT_CONTROLS, tmp_path)
    py_result = python_compute_all(embedded_data["divisions"][division], NON_DEFAULT_CONTROLS, embedded_data["days_per_month"])
    _compare(js_result, py_result, f"{division} non-default scenario (45d/7d/14d/90%/15%)")


# Task 2b Part 1: the warehouse checklist and obsolescence-threshold slider are now live. These
# parity tests cover 2 warehouse selections (full sellable set; a single-warehouse subset) x 2
# thresholds (the config default 6mo; a tight 1mo), for every enabled division -- confirming the
# page's recomputed on_hand_sellable, months_of_cover and excess flags equal Python's, not just
# Min/Max (already covered above).
WAREHOUSE_SELECTIONS = {
    "full_sellable_set": None,  # None -> defaults to divisionData.sellable_warehouse_codes, both sides
    "single_warehouse": "first_only",  # resolved per-division below (that division's first sellable code)
}
THRESHOLDS = [6, 1]


def _controls_with_threshold(threshold_months: int) -> dict:
    return {**DEFAULT_CONTROLS, "obsolescence_threshold_months": threshold_months}


@pytest.mark.parametrize("threshold", THRESHOLDS)
@pytest.mark.parametrize("selection_name", list(WAREHOUSE_SELECTIONS))
@pytest.mark.parametrize("division", DIVISIONS)
def test_js_matches_python_for_warehouse_selection_and_threshold(division, selection_name, threshold, tmp_path, embedded_data):
    division_data = embedded_data["divisions"][division]
    full_set = division_data["sellable_warehouse_codes"]
    selection = WAREHOUSE_SELECTIONS[selection_name]
    checked = full_set if selection is None else [full_set[0]]
    controls = _controls_with_threshold(threshold)

    js_result = _run_js_compute_all(division, controls, tmp_path, checked_warehouses=checked)
    py_result = python_compute_all(division_data, controls, embedded_data["days_per_month"], checked_warehouses=checked)
    _compare(js_result, py_result,
             f"{division} warehouses={selection_name}({checked}) threshold={threshold}mo",
             check_excess=True)


def _drop_forecast_of_three_items(data):
    """PEM101: the first stock_policy item, the first confirmed_to_order item and the first conflict item lose their forecast (a vintage with no row for them)."""
    items = data["divisions"]["PEM101"]["items"]
    for policy in ("stock_policy", "confirmed_to_order", "conflict"):
        next(i for i in items if i["policy"] == policy)["forecast"] = []


def test_the_no_forecast_rule_is_the_same_in_js_and_python_and_selects_items_with_stock_and_no_forecast_month(tmp_path):
    """The list "สินค้าที่มีของแต่ไม่มียอดทาย" is the items with no positive forecast month in the page's vintage and a positive sellable stock: an item with a forecast
    is never in it, whatever its class, and an item with no forecast but no stock is not either."""
    payload = load_stock_payload()
    base = stock_daily.apply_to_data(_extract_embedded_data(), payload)
    data = _extract_embedded_data()
    _drop_forecast_of_three_items(data)
    data = stock_daily.apply_to_data(data, payload)
    py = python_compute_all(data["divisions"]["PEM101"], DEFAULT_CONTROLS, data["days_per_month"])
    js = _run_js_compute_all("PEM101", DEFAULT_CONTROLS, tmp_path, mutate=_drop_forecast_of_three_items)
    _compare(js, py, "PEM101 with three items without a forecast", check_excess=True)
    no_forecast = {r["code"]: r for r in py["per_item"] if r["no_vintage_forecast"]}
    assert len(no_forecast) == 3
    listed = {c for c, r in no_forecast.items() if r["on_hand_sellable"] > 0}
    with_stock = {i["code"] for i in base["divisions"]["PEM101"]["items"]
                  if sum(w["qty"] for w in i.get("by_warehouse", []) if w["code"] in base["divisions"]["PEM101"]["sellable_warehouse_codes"]) > 0}
    assert listed == set(no_forecast) & with_stock
    assert all(r["no_vintage_forecast"] is False for c, r in {r["code"]: r for r in python_compute_all(base["divisions"]["PEM101"], DEFAULT_CONTROLS, base["days_per_month"])["per_item"]}.items())
