"""Phase 23, Part 6 parity tests: forecast/inventory.html's client-side curve-interpolation JS
(extracted and run for real in Node, not re-implemented by hand for the test) must produce
per-item Min/Max/stock_value identical (within a tight float tolerance) to
src/curve_interpolation.py's pure-Python mirror, operating on the SAME embedded dense grid --
at each of PEM101's 3 not_late presets and at 2 arbitrary slider positions strictly between two
embedded grid points (so real interpolation, not a grid-point passthrough, is exercised).

Tolerance: 1e-6 relative (rtol) via math.isclose -- both languages do IEEE-754 double arithmetic
on the same linear-interpolation operations in the same order, so exact-to-many-decimal-places
agreement is expected; this is not a loosened tolerance to force a pass, it is the ordinary
floating-point equality tolerance for two independent implementations of the same arithmetic
(same pattern as tests/test_inventory_parity.py's Tier-A JS/Python parity check).
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

from curve_interpolation import interpolate_grid_at_notlate as python_interpolate


def _load_html():
    with open(INVENTORY_HTML, "r", encoding="utf-8") as f:
        return f.read()


def _extract_embedded_data():
    html_text = _load_html()
    m = re.search(r'<script type="application/json" id="inventory-data">(.*?)</script>', html_text, re.DOTALL)
    assert m, "Embedded #inventory-data JSON block not found in forecast/inventory.html"
    return json.loads(m.group(1))


def _extract_interp_js():
    html_text = _load_html()
    m = re.search(r"// BEGIN_CURVE_INTERP_JS.*?// END_CURVE_INTERP_JS", html_text, re.DOTALL)
    assert m, "CURVE_INTERP_JS block not found in forecast/inventory.html (missing markers)"
    return m.group(0)


def _run_js_interpolate(grid: list, target_not_late: float, tmp_path) -> dict:
    js_block = _extract_interp_js()
    runner = (f"\nconsole.log(JSON.stringify(interpolateGridAtNotLate("
              f"{json.dumps(grid)}, {json.dumps(target_not_late)})));\n")
    js_path = tmp_path / f"curve_interp_extracted_{target_not_late}.js"
    js_path.write_text(js_block + runner, encoding="utf-8")
    result = subprocess.run(["node", str(js_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"Node execution failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def _compare(js_result: dict, py_result: dict, label: str):
    for field in ["not_late_median_pct", "stock_value_min", "stock_value_median", "stock_value_max"]:
        jv, pv = js_result[field], py_result[field]
        assert math.isclose(jv, pv, rel_tol=1e-6, abs_tol=1e-4), \
            f"[{label}] {field} mismatch: JS={jv} Python={pv}"
    js_by_code = {r["code"]: r for r in js_result["items"]}
    py_by_code = {r["code"]: r for r in py_result["items"]}
    assert set(js_by_code) == set(py_by_code), f"[{label}] item sets differ between JS and Python"
    mismatches = []
    for code, py_r in py_by_code.items():
        js_r = js_by_code[code]
        for field in ["Min", "Max_median", "Max_min", "Max_max"]:
            jv, pv = js_r[field], py_r[field]
            if not math.isclose(jv, pv, rel_tol=1e-6, abs_tol=1e-4):
                mismatches.append((code, field, jv, pv))
    assert not mismatches, f"[{label}] Min/Max mismatches (code, field, JS, Python): {mismatches[:10]}"


@pytest.fixture(scope="module")
def pem101_grid():
    data = _extract_embedded_data()
    return data["divisions"]["PEM101"]["curve_target"]["grid"]


@pytest.fixture(scope="module")
def pem101_presets():
    data = _extract_embedded_data()
    return data["divisions"]["PEM101"]["curve_target"]["presets"]


@pytest.mark.parametrize("preset_key", ["today_lowest_stock", "highest_at_today_stock", "stretch_99pct"])
def test_js_matches_python_at_preset(preset_key, tmp_path, pem101_grid, pem101_presets):
    target = pem101_presets[preset_key]["not_late_pct"]
    js_result = _run_js_interpolate(pem101_grid, target, tmp_path)
    py_result = python_interpolate(pem101_grid, target)
    _compare(js_result, py_result, f"preset={preset_key} (not_late={target})")


def _midpoint_between_grid_points(grid, i):
    a, b = grid[i], grid[i + 1]
    return (a["not_late_median_pct"] + b["not_late_median_pct"]) / 2.0


def test_js_matches_python_at_slider_position_1(tmp_path, pem101_grid):
    """A slider position strictly between grid points 3 and 4 (not on any embedded point)."""
    target = _midpoint_between_grid_points(pem101_grid, 3)
    assert pem101_grid[3]["not_late_median_pct"] < target < pem101_grid[4]["not_late_median_pct"]
    js_result = _run_js_interpolate(pem101_grid, target, tmp_path)
    py_result = python_interpolate(pem101_grid, target)
    _compare(js_result, py_result, f"slider position 1 (not_late={target})")


def test_js_matches_python_at_slider_position_2(tmp_path, pem101_grid):
    """A slider position strictly between grid points 12 and 13 (not on any embedded point)."""
    target = _midpoint_between_grid_points(pem101_grid, 12)
    assert pem101_grid[12]["not_late_median_pct"] < target < pem101_grid[13]["not_late_median_pct"]
    js_result = _run_js_interpolate(pem101_grid, target, tmp_path)
    py_result = python_interpolate(pem101_grid, target)
    _compare(js_result, py_result, f"slider position 2 (not_late={target})")
