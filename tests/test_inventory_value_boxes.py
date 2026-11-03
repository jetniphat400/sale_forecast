"""The PEM101 value boxes of forecast/inventory.html follow METRICS.md Sec.6 over the items they count, state how many that is, and list the items they cannot count (Prompt 66, R2B1-001 and R2B1-002)."""
import json
import math
import os
import re
import subprocess
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_inventory_page_data as bd  # noqa: E402
from inventory_recompute_reference import compute_all, compute_item_min_max  # noqa: E402
from page_helpers import load_stock_payload  # noqa: E402

HTML = os.path.join(PROJECT_ROOT, "forecast", "inventory.html")
SUMMARY = os.path.join(PROJECT_ROOT, "output", "summary")
CONTROLS = {"procurement_lead_time_days": 60, "assembly_time_days": 3, "review_interval_days": 30, "cycle_service_level": 0.95,
            "holding_cost_rate_annual": 0.20, "obsolescence_threshold_months": 6}


def _page():
    return open(HTML, encoding="utf-8").read()


def _data(html=None):
    return json.loads(re.search(r'<script type="application/json" id="inventory-data">(.*?)</script>', html or _page(), re.S).group(1))


def _node_compute_all(tmp_path, data, html=None, division="PEM101"):
    block = re.search(r"const DATA = JSON\.parse.*?// END_RECOMPUTE_JS", html or _page(), re.S).group(0)
    js = block.replace("const DATA = JSON.parse(document.getElementById('inventory-data').textContent);", f"const DATA = {json.dumps(data)};")
    js += f"\napplyStock(DATA, {json.dumps(load_stock_payload())});\nconsole.log(JSON.stringify(computeAll({json.dumps(CONTROLS)}, DATA.divisions[{json.dumps(division)}])));\n"
    p = tmp_path / "box.js"
    p.write_text(js, encoding="utf-8")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _need_outputs():
    for f in ("phaseE1fix_2_unit_cost.csv", "phaseE2_0_unit_cost.csv"):
        if not os.path.exists(os.path.join(SUMMARY, f)):
            pytest.skip(f"SKIPPED, not passed: output/summary/{f} is not on this machine")


# ------------------------------------------------------------------ the cost of an item
def _df(rows):
    return pd.DataFrame(rows, columns=["itemcode", "unit_cost", "unit_cost_fallback", "no_unit_cost_item"])


def test_an_item_the_pilot_file_prices_keeps_the_pilot_cost_and_an_item_outside_it_takes_the_full_scope_cost():
    pilot = _df([("A", 10.0, False, False)])
    full = _df([("A", 11.0, False, False), ("B", 20.0, True, False)])
    assert bd.unit_cost_for("A", pilot, full) == {"unit_cost": 10.0, "unit_cost_fallback": False, "no_unit_cost_item": False, "unit_cost_source": "pilot"}
    assert bd.unit_cost_for("B", pilot, full) == {"unit_cost": 20.0, "unit_cost_fallback": True, "no_unit_cost_item": False, "unit_cost_source": "full_scope"}


def test_an_item_with_no_cost_in_either_table_has_no_unit_cost_and_an_unpriced_pilot_row_falls_through_to_the_full_table():
    pilot = _df([("C", float("nan"), False, True), ("D", float("nan"), False, True)])
    full = _df([("D", 5.0, False, False), ("E", float("nan"), False, True)])
    assert bd.unit_cost_for("Z", pilot, full)["no_unit_cost_item"] is True and bd.unit_cost_for("Z", pilot, full)["unit_cost"] is None
    assert bd.unit_cost_for("E", pilot, full)["no_unit_cost_item"] is True and bd.unit_cost_for("E", pilot, full)["unit_cost"] is None
    assert bd.unit_cost_for("C", pilot, full)["no_unit_cost_item"] is True
    assert bd.unit_cost_for("D", pilot, full) == {"unit_cost": 5.0, "unit_cost_fallback": False, "no_unit_cost_item": False, "unit_cost_source": "full_scope"}


# ------------------------------------------------------------------ the box on the page
def test_every_stock_policy_item_of_the_page_has_the_cost_the_cost_tables_give_it():
    _need_outputs()
    pilot = pd.read_csv(os.path.join(SUMMARY, "phaseE1fix_2_unit_cost.csv")).set_index("itemcode")["unit_cost"]
    full = pd.read_csv(os.path.join(SUMMARY, "phaseE2_0_unit_cost.csv")).set_index("itemcode")["unit_cost"]
    items = [i for i in _data()["divisions"]["PEM101"]["items"] if i["policy"] == "stock_policy"]
    assert len(items) == 92
    for i in items:
        expected = pilot[i["code"]] if i["code"] in pilot.index and pd.notna(pilot[i["code"]]) else full.get(i["code"])
        assert pd.notna(expected) and not i["no_unit_cost_item"] and math.isclose(i["unit_cost"], float(expected), rel_tol=1e-12), i["code"]


def test_the_box_value_equals_sec6_min_times_cost_recomputed_from_the_cost_tables_over_the_counted_items(tmp_path):
    """The independent figure: each stock_policy item's Min from the Python mirror of the page's rule, its cost read straight from the two cost tables (not from the page's embedded costs)."""
    _need_outputs()
    pilot = pd.read_csv(os.path.join(SUMMARY, "phaseE1fix_2_unit_cost.csv")).set_index("itemcode")["unit_cost"].dropna()
    full = pd.read_csv(os.path.join(SUMMARY, "phaseE2_0_unit_cost.csv")).set_index("itemcode")["unit_cost"].dropna()
    data = _data()
    div = data["divisions"]["PEM101"]
    expected, counted = 0.0, 0
    for it in div["items"]:
        if it["policy"] != "stock_policy":
            continue
        r = compute_item_min_max(it, CONTROLS, data["days_per_month"])
        cost = pilot.get(it["code"], full.get(it["code"]))
        if r["min"] is not None and cost is not None:
            expected += r["min"] * float(cost)
            counted += 1
    out = _node_compute_all(tmp_path, data)
    assert math.isclose(out["stockValue"], expected, rel_tol=1e-9, abs_tol=1e-4)
    assert out["valueCounted"] == counted == 92 and out["valueNotCounted"] == []
    assert math.isclose(out["stockValue"], 82361717.10, abs_tol=0.01)                                    # the Sec.6 figure (about THB 82.36M); the page showed 65,587,403.56 before


def test_the_python_mirror_counts_the_same_items_as_the_page_script(tmp_path):
    data = _data()
    py = compute_all(data["divisions"]["PEM101"], CONTROLS, data["days_per_month"])
    js = _node_compute_all(tmp_path, data)
    assert py["value_counted"] == js["valueCounted"] and py["value_not_counted"] == js["valueNotCounted"]
    assert math.isclose(py["stock_value"], js["stockValue"], rel_tol=1e-9)


def test_an_item_with_a_min_and_no_cost_is_left_out_of_the_value_counted_apart_and_named(tmp_path):
    data = _data()
    whole = _node_compute_all(tmp_path, data)
    victim = next(r for r in whole["perItem"] if r["policy"] == "stock_policy" and r["min"] is not None)
    for it in data["divisions"]["PEM101"]["items"]:
        if it["code"] == victim["code"]:
            it["unit_cost"], it["no_unit_cost_item"] = None, True
    cut = _node_compute_all(tmp_path, data)
    assert cut["valueNotCounted"] == [victim["code"]] and cut["valueCounted"] == whole["valueCounted"] - 1
    assert math.isclose(cut["stockValue"], whole["stockValue"] - victim["min"] * victim["unitCost"], rel_tol=1e-9)


def test_the_page_writes_the_count_and_the_list_next_to_the_box():
    html = _page()
    assert 'id="tot-stock-value-note"' in html and "'มูลค่าตาม Min รวม ' + result.valueCounted + ' จาก ' + nValued + ' รายการที่มี Min'" in html
    assert "ไม่มีต้นทุนต่อชิ้น: ' + result.valueNotCounted.join(', ')" in html
    assert "รวมทุกรหัส" not in html                                                                      # the label no longer claims every code


# ------------------------------------------------------------------ the "today" value
def test_the_today_value_states_how_many_items_it_covers_and_lists_the_others():
    _need_outputs()
    ct = _data()["divisions"]["PEM101"]["curve_target"]
    tp = ct["today_point"]
    pilot_priced = set(pd.read_csv(os.path.join(SUMMARY, "phaseE1fix_2_unit_cost.csv")).dropna(subset=["unit_cost"])["itemcode"])
    assert tp["n_items_calibrated"] == len(ct["items_order"]) == 92
    assert tp["not_valued_items"] == sorted(c for c in ct["items_order"] if c not in pilot_priced) and len(tp["not_valued_items"]) == 15
    assert tp["n_items_valued"] == 92 - 15 == 77
    assert math.isclose(tp["stock_value_thb"], 15491483.08, abs_tol=0.01)                              # the recorded value is not recomputed
    html = _page()
    assert "(นับ ${ct.today_point.n_items_valued} จาก ${ct.today_point.n_items_calibrated} รายการ)" in html
    assert "มูลค่า stock นี้ไม่รวม ${ct.today_point.not_valued_items.length} รายการ" in html


def test_a_recorded_value_that_covers_a_different_number_of_items_than_the_cost_file_prices_stops_the_build(monkeypatch):
    import maxmin_v1
    real = maxmin_v1.ensemble_summary
    monkeypatch.setattr(maxmin_v1, "ensemble_summary", lambda cfg=None: {**real(cfg), "n_item_matched_unit_cost": 76})
    _need_outputs()
    with pytest.raises(ValueError, match="cannot say which items"):
        bd._build_curve_target_pem101()
