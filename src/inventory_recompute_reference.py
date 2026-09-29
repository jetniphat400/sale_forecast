"""Pure-Python mirror of forecast/inventory.html's client-side JS recompute engine
(src/build_inventory_page.py's RECOMPUTE_JS), operating on the SAME embedded JSON data (not a
fresh DB pull). Exists so tests/test_inventory_parity.py can assert the JS (run in Node) and this
Python reference produce identical Min/Max/stock_value from identical inputs -- both implement
METRICS.md's formulas independently in two languages; agreement here is the parity guarantee the
task requires, not a re-verification against the live database (src/phaseE1fix_recompute.py
already did that, against the DB, separately).
"""
import numpy as np


def compute_ltd(forecast_arr, protection_days, days_per_month):
    months_float = protection_days / days_per_month
    full = int(np.floor(months_float))
    frac = months_float - full
    ltd = float(sum(forecast_arr[:full]))
    if frac > 0 and full < len(forecast_arr):
        ltd += frac * forecast_arr[full]
    return ltd, full, frac


def rolling_window_sums(actual_arr, full, frac):
    window_len = full + (1 if frac > 0 else 0)
    if window_len <= 0 or window_len > len(actual_arr):
        return []
    sums = []
    n = len(actual_arr)
    for i in range(n - window_len + 1):
        s = sum(actual_arr[i:i + full])
        if frac > 0 and i + full < n:
            s += frac * actual_arr[i + full]
        sums.append(s)
    return sums


def compute_item_min_max(item, controls, days_per_month):
    protection_days = (controls["procurement_lead_time_days"] + controls["assembly_time_days"]
                        + controls["review_interval_days"])
    ltd, full, frac = compute_ltd(item["forecast"], protection_days, days_per_month)
    window_sums = rolling_window_sums(item["actual_history"], full, frac)
    if not window_sums:
        return {"min": None, "max": None, "ltd": ltd, "safety_stock": None, "unreliable": True}
    pct_val = float(np.percentile(window_sums, controls["cycle_service_level"] * 100))
    # METRICS.md Sec.4 (corrected 2026-09-22): percentile - LTD, NOT percentile - mean(window_sums)
    # -- the two differ whenever the forecast (LTD) and the window distribution's own historical
    # mean disagree; this was a confirmed code defect, fixed identically in build_inventory_page.py.
    safety_stock = max(0.0, pct_val - ltd)
    min_qty = ltd + safety_stock

    review_months_float = controls["review_interval_days"] / days_per_month
    review_full = int(np.floor(review_months_float))
    review_frac = review_months_float - review_full
    replen = float(sum(item["forecast"][full:full + review_full]))
    if review_frac > 0 and full + review_full < len(item["forecast"]):
        replen += review_frac * item["forecast"][full + review_full]
    max_qty = min_qty + replen

    n_nonzero = sum(1 for x in window_sums if x > 0)
    horizon = full + (1 if frac > 0 else 0)
    mean_monthly_forecast = float(np.mean(item["forecast"][:horizon])) if horizon > 0 else 0.0
    return {"min": min_qty, "max": max_qty, "ltd": ltd, "safety_stock": safety_stock,
            "unreliable": n_nonzero < 6, "mean_monthly_forecast": mean_monthly_forecast,
            "replenishment": replen}


def gets_min_max(item):
    """task 2b Part 2 (METRICS.md Sec.23): 'stock_policy' (PEM101/PEM107) or the original
    'finished_goods_stock' (PEM103, unaffected by segmentation) get a Min/Max; nothing else does,
    even if the item has enough history to technically produce a number."""
    return item["policy"] in ("finished_goods_stock", "stock_policy")


def on_hand_sellable_for(item, checked_warehouses):
    checked = set(checked_warehouses)
    return float(sum(w["qty"] for w in item.get("by_warehouse", []) if w["code"] in checked))


def compute_all(division_data, controls, days_per_month, checked_warehouses=None):
    """checked_warehouses defaults to the division's full sellable_warehouse_codes (the same total
    the page showed before task 2b's checklist did anything) -- METRICS.md Sec.40
    (excess_stock_flag): a zero-forecast item has infinite cover and is flagged excess only if
    on_hand_sellable > 0 (also marked no_forecast_demand so callers can list it separately)."""
    if checked_warehouses is None:
        checked_warehouses = division_data["sellable_warehouse_codes"]
    checked_set = set(checked_warehouses)
    stock_value = 0.0
    per_item = []
    for item in division_data["items"]:
        in_fg = gets_min_max(item)
        r = compute_item_min_max(item, controls, days_per_month) if in_fg else {"min": None, "max": None, "unreliable": True}
        contribution = (r["min"] * item["unit_cost"]) if (in_fg and not item["no_unit_cost_item"] and r["min"] is not None) else 0.0
        if in_fg:
            stock_value += contribution
        on_hand_sellable = on_hand_sellable_for(item, checked_set)
        has_forecast = bool(r.get("mean_monthly_forecast"))
        moc = (on_hand_sellable / r["mean_monthly_forecast"]) if has_forecast else float("inf")
        no_forecast_demand = not has_forecast
        excess = (on_hand_sellable > 0) if no_forecast_demand else (moc > controls["obsolescence_threshold_months"])
        per_item.append({"code": item["code"], "policy": item["policy"], "min": r["min"], "max": r["max"],
                          "stock_value_contribution": contribution, "months_of_cover": moc,
                          "on_hand_sellable": on_hand_sellable, "excess": excess,
                          "no_forecast_demand": no_forecast_demand})
    holding_cost = stock_value * controls["holding_cost_rate_annual"]
    excess_count = sum(1 for r in per_item if r["excess"])
    return {"stock_value": stock_value, "holding_cost": holding_cost, "per_item": per_item,
            "excess_count": excess_count}
