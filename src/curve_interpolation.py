"""Pure-Python mirror of forecast/inventory.html's client-side curve interpolation JS
(the `// BEGIN_CURVE_INTERP_JS` .. `// END_CURVE_INTERP_JS` block) -- used by
tests/test_inventory_curve_parity.py to check the page's real, extracted JS (run for real in
Node, not re-implemented there) against this independent Python implementation.

The page never simulates client-side; it only interpolates between the dense grid's 20 embedded
points (src/investigations/phase23_page_precompute.py), linearly, on `not_late_median_pct`.
"""


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _grid_point_as_result(g: dict) -> dict:
    return {
        "r": g["r"], "not_late_median_pct": g["not_late_median_pct"],
        "stock_value_min": g["stock_value_min"], "stock_value_median": g["stock_value_median"],
        "stock_value_max": g["stock_value_max"],
        "items": [{"code": it["code"], "Min": it["Min"], "Max_median": it["Max_median"],
                   "Max_min": it["Max_min"], "Max_max": it["Max_max"]} for it in g["items"]],
    }


def _lerp_grid_points(a: dict, b: dict, t: float) -> dict:
    items = []
    for ai, bi in zip(a["items"], b["items"]):
        items.append({
            "code": ai["code"], "Min": _lerp(ai["Min"], bi["Min"], t),
            "Max_median": _lerp(ai["Max_median"], bi["Max_median"], t),
            "Max_min": _lerp(ai["Max_min"], bi["Max_min"], t),
            "Max_max": _lerp(ai["Max_max"], bi["Max_max"], t),
        })
    return {
        "r": _lerp(a["r"], b["r"], t),
        "not_late_median_pct": _lerp(a["not_late_median_pct"], b["not_late_median_pct"], t),
        "stock_value_min": _lerp(a["stock_value_min"], b["stock_value_min"], t),
        "stock_value_median": _lerp(a["stock_value_median"], b["stock_value_median"], t),
        "stock_value_max": _lerp(a["stock_value_max"], b["stock_value_max"], t),
        "items": items,
    }


def interpolate_grid_at_notlate(grid: list, target_not_late: float) -> dict:
    """Identical logic to the page's interpolateGridAtNotLate(grid, targetNotLate)."""
    g = grid
    if target_not_late <= g[0]["not_late_median_pct"]:
        return _grid_point_as_result(g[0])
    if target_not_late >= g[-1]["not_late_median_pct"]:
        return _grid_point_as_result(g[-1])
    for i in range(len(g) - 1):
        a, b = g[i], g[i + 1]
        if a["not_late_median_pct"] <= target_not_late <= b["not_late_median_pct"]:
            t = (target_not_late - a["not_late_median_pct"]) / (b["not_late_median_pct"] - a["not_late_median_pct"])
            return _lerp_grid_points(a, b, t)
    raise AssertionError(f"target_not_late {target_not_late} not bracketed by grid")
