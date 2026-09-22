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

from inventory_recompute_reference import compute_all as python_compute_all

DEFAULT_CONTROLS = {"procurement_lead_time_days": 60, "assembly_time_days": 3,
                    "review_interval_days": 30, "cycle_service_level": 0.95,
                    "holding_cost_rate_annual": 0.20}
NON_DEFAULT_CONTROLS = {"procurement_lead_time_days": 45, "assembly_time_days": 7,
                        "review_interval_days": 14, "cycle_service_level": 0.90,
                        "holding_cost_rate_annual": 0.15}
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


def _run_js_compute_all(division: str, controls: dict, tmp_path) -> dict:
    """Writes the page's REAL extracted JS (not a hand re-implementation) to a temp file, with the
    document.getElementById(...) DOM read replaced by a literal JSON injection (Node has no DOM),
    and calls computeAll(controls, DATA.divisions[division]) via a tiny runner appended at the end."""
    js_block = _extract_recompute_js()
    data = _extract_embedded_data()
    js_block = js_block.replace(
        "const DATA = JSON.parse(document.getElementById('inventory-data').textContent);",
        f"const DATA = {json.dumps(data)};")
    runner = (f"\nconsole.log(JSON.stringify(computeAll({json.dumps(controls)}, "
              f"DATA.divisions[{json.dumps(division)}])));\n")
    js_path = tmp_path / f"inventory_recompute_extracted_{division}.js"
    js_path.write_text(js_block + runner, encoding="utf-8")
    result = subprocess.run(["node", str(js_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"Node execution failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def _compare(js_result: dict, py_result: dict, label: str):
    assert math.isclose(js_result["stockValue"], py_result["stock_value"], rel_tol=1e-6, abs_tol=1e-4), \
        f"[{label}] stock_value mismatch: JS={js_result['stockValue']} Python={py_result['stock_value']}"
    js_by_code = {r["code"]: r for r in js_result["perItem"]}
    py_by_code = {r["code"]: r for r in py_result["per_item"]}
    assert set(js_by_code) == set(py_by_code), f"[{label}] item sets differ between JS and Python"
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


@pytest.fixture(scope="module")
def embedded_data():
    return _extract_embedded_data()


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
