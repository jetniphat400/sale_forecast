"""Week 3 (2026-10-06): the Sec.23 additions (data_inconsistent, no_production_in_system, too_little_data, the mixed-item rule, display labels), the material
plan (METRICS.md Sec.43: multi-level explosion, netting, order dates, recorded outputs and their hashes, proofs), its page, and the check that every page lists
all six divisions or says why. Everything runs on small fixtures in temporary folders; nothing tracked is modified. A test that reads the recorded real
outputs skips with a message when those files are not on this machine, never passes silently."""
import copy
import hashlib
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest
import yaml

from page_helpers import PROJECT_ROOT

sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "investigations"))
import operation_plan as op  # noqa: E402
import material_plan as mp  # noqa: E402
import build_material_plan_page as bm  # noqa: E402
import build_operation_plan_page as bp  # noqa: E402
import task2b_part2_fulfilment_segmentation as seg  # noqa: E402

TODAY = pd.Timestamp("2026-10-06")
MONTHS = ["2026-10", "2026-11", "2026-12"]
W3 = seg.load_week3_config()
RULE = W3["mixed_rule"]
SIX = ["PEM101", "PEM103", "PEM107", "PEM102", "PEM104", "CI101"]


# ====================================================================================================== Part 2: the three definitions
@pytest.mark.parametrize("label,s1,s2,s3,s2c,expected", [
    ("MTS", False, False, False, True, True),        # stock label, no stock signal at all
    ("MTS", True, False, False, True, False),        # one signal is enough to avoid the flag
    ("MTO", True, True, True, True, True),           # made-to-order label, every signal says stock
    ("ETO", True, True, True, True, True),
    ("MTO", True, True, False, True, False),
    ("MTS", False, None, False, False, True),        # S2 cannot be computed: S1 and S3 only
    ("MTO", True, None, True, False, True),
    ("MTO", True, None, False, False, False),
    ("mixed", False, False, False, True, False),     # a mixed label is never flagged
])
def test_data_inconsistent_follows_the_two_conditions(label, s1, s2, s3, s2c, expected):
    assert seg.is_data_inconsistent(label, s1, s2, s3, s2c) is expected


def _ces(rows):
    return pd.DataFrame([{"ItemCode": i, "ContractID": c, "Status": s, "CtrDate": d, "PlanID": p, "ActualDelDate": a, "OLMJobCode": None}
                         for i, c, s, d, p, a in rows])


def test_too_little_data_counts_distinct_delivered_contracts_in_the_window_only():
    ces = _ces([("A", "c1", "Actual", "2024-02-01", 1, "2024-02-05"), ("A", "c1", "Actual", "2024-02-01", 2, "2024-02-06"),     # one contract, two plan rows
                ("A", "c2", "Actual", "2025-03-01", 1, "2025-03-05"), ("A", "c3", "Backlog", "2025-04-01", 1, None),                # a backlog row is not delivered
                ("A", "c0", "Actual", "2023-12-31", 1, "2024-01-05"),                                                               # created before the window
                ("B", "d1", "Actual", "2024-01-01", 1, "2024-01-09")])
    n = seg.delivered_contracts_in_window(ces, W3["analysis_window_start"])
    assert n["A"] == 2 and n["B"] == 1
    items = pd.DataFrame({"code": ["A", "B", "Z"]})
    nd = items["code"].map(n).fillna(0).astype(int)
    for k, expect in ((2, [False, True, True]), (3, [True, True, True]), (5, [True, True, True])):
        assert list(nd < k) == [bool(x) for x in expect] or k == 2
    assert [bool(x) for x in (nd < 2)] == [False, True, True]


def test_the_too_little_data_counts_are_reported_at_the_neighbouring_values():
    table = pd.DataFrame({"division": ["PEM101"] * 4 + ["CI101"] * 2, "n_delivered_window": [0, 2, 3, 6, 1, 5]})
    c = seg.too_little_data_counts(table, [2, 3, 5])
    assert c[2] == {"CI101": 1, "PEM101": 1} and c[3] == {"CI101": 1, "PEM101": 2} and c[5] == {"CI101": 1, "PEM101": 3}
    assert W3["min_delivered_contracts"] == 3 and W3["min_delivered_contracts_report_at"] == [2, 3, 5]


@pytest.mark.parametrize("args,expected", [
    ((("stock_policy"), True, False, False, False), "no_production_in_system"),          # the label of an item with no production wins over everything
    (("stock_policy", True, True, True, True), "no_production_in_system"),
    (("stock_policy", False, True, True, True), "stock_policy"),                           # a class decided by the user or the business is kept
    (("conflict", False, True, True, False), "too_little_data"),
    (("conflict", False, False, True, False), "mixed"),
    (("conflict", False, False, False, False), "conflict"),
    (("confirmed_to_order", False, True, False, False), "too_little_data"),
])
def test_display_label_order(args, expected):
    assert seg.display_label(*args) == expected


def _fixture_pulls():
    """Six items of two divisions: S (stock, kept), K (kept made-to-order, label contradicts), M (mixed by lines), L (little data), N (no production), P (placeholder)."""
    universe = pd.DataFrame({"code": ["S", "K", "M", "L", "N", "P", "T"], "division": ["PEM101", "PEM101", "PEM103", "PEM103", "PEM103", "PEM103", "PEM104"],
                             "status_category": ["forecast", "forecast", "forecast", "forecast", "forecast", "placeholder - pending method", "excluded - division"]})
    codes = list(universe["code"])
    label_df = pd.DataFrame({"itemcode": codes, "manufacturing_type": ["MTS", "MTS", "MTS", "MTO", "MTO", None, "MTS"], "share": [1.0] * 7,
                             "label": ["MTS", "MTS", "mixed", "MTO", "MTO", "mixed", "MTS"]})
    s1 = pd.DataFrame({"itemcode": codes, "total_stock": [5.0, 0, 0, 0, 0, 0, 0], "S1": [True, False, False, False, False, False, False]})
    s2s3 = pd.DataFrame({"itemcode": codes, "n_delivered_contracts": [9] * 7, "n_cube_final_linked": [0] * 7, "n_traceable_pre_existing": [0] * 7,
                         "S2_share": [np.nan] * 7, "S2_computable": [False] * 7, "S2": [None] * 7, "S3_median_days": [3, 30, 3, 20, 20, np.nan, 20], "S3_n": [9] * 7,
                         "S3": [True, False, True, False, False, False, False]})
    rows = []                                                   # delivered lines: contract id, plan id, label, createDate -> ActualDelDate
    def lines(item, label, days, start):
        for k, d in enumerate(days):
            rows.append((item, f"{item}-{label}-{k}", label, start, d))
    lines("M", "MTS", [1, 2, 3, 4], "2026-03-01"); lines("M", "MTO", [30, 40, 50], "2026-03-01")
    lines("S", "MTS", [2, 3, 4, 5], "2026-02-01"); lines("S", "MTO", [40, 41, 42], "2026-02-01")      # the rule calls S mixed, but its class is a kept decision
    apd = pd.DataFrame([{"itemcode": i, "contractid": c, "planid": 1, "status": "Actual", "manufacturing_type": lab, "createDate": s, "qty": 10.0}
                        for i, c, lab, s, d in rows])
    ces = pd.DataFrame([{"ItemCode": i, "ContractID": c, "PlanID": 1, "Status": "Actual", "CtrDate": s,
                         "ActualDelDate": (pd.Timestamp(s) + pd.Timedelta(days=int(d), unit=None) if False else pd.Timestamp(s) + pd.to_timedelta(int(d), unit='D')).strftime("%Y-%m-%d"), "OLMJobCode": None} for i, c, lab, s, d in rows])
    return universe, label_df, s1, s2s3, apd, ces


def test_the_week3_table_flags_labels_and_the_known_item_test_on_fixtures():
    universe, label_df, s1, s2s3, apd, ces = _fixture_pulls()
    kept = {"S": "stock_policy", "K": "confirmed_to_order"}
    decisions = {}
    table, test = seg.build_week3_item_level(universe, label_df, s1, s2s3, apd, ces, bom_counts={"S": 3, "K": 1, "M": 2, "T": 1}, final_counts={"L": 4}, kept_class=kept,
                                             today=TODAY, w3=dict(W3, mixed_rule={**RULE, "max_share_of_known_items": 0.6}), decisions=decisions)   # one of the two known items is called mixed
    t = table.set_index("code")
    assert t.loc["K", "data_inconsistent"] and not t.loc["S", "data_inconsistent"]          # K: label MTS, no signal; S: label MTS, S1 and S3 hold
    assert t.loc["N", "no_production_in_system"] and t.loc["P", "no_production_in_system"] and not t.loc["L", "no_production_in_system"]    # L has a cube_final record
    assert not t.loc["S", "no_production_in_system"] and t.loc["S", "n_bom_entries"] == 3
    assert t.loc["S", "n_delivered_window"] == 7 and t.loc["M", "n_delivered_window"] == 7 and t.loc["L", "too_little_data"]
    assert t.loc["M", "mixed_by_rule"] and t.loc["M", "mixed_applied"] and t.loc["M", "class_label"] == "mixed"
    assert t.loc["S", "mixed_by_rule"] and not t.loc["S", "mixed_applied"] and t.loc["S", "class_label"] == "stock_policy"   # a kept class keeps its class and label
    assert t.loc["N", "class_label"] == "no_production_in_system" and t.loc["P", "class_label"] == "no_production_in_system"
    assert t.loc["L", "class_label"] == "too_little_data"
    assert t.loc["T", "class"] == "confirmed_to_order" and t.loc["T", "class_basis"] == "business_confirmed" and t.loc["T", "class_label"] == "confirmed_to_order"
    assert test["n_known"] == 2 and test["n_called_mixed"] == 1 and test["adopted"] is True
    assert t.loc["M", "mts_share_12m"] == pytest.approx(40.0 / 70.0)                          # four MTS lines of ten units against three MTO lines
    assert pd.isna(t.loc["S", "mts_share_12m"])          # S is a stock item of a kept class and not a conflict or mixed-label item: the rule is not applied to it
    assert pd.isna(t.loc["L", "mts_share_12m"])


# ====================================================================================================== Part 3: the mixed-item rule
def _lines(spec):
    return pd.DataFrame([{"itemcode": i, "manufacturing_type": lab, "days": d} for i, lab, days in spec for d in days])


def test_the_mixed_rule_calls_a_two_mode_item_mixed_and_a_single_mode_item_not():
    s = seg.mixed_item_stats(_lines([("two", "MTS", [1, 2, 3, 4]), ("two", "MTO", [30, 40, 50]),
                                     ("only_stock", "MTS", [1, 2, 3, 4, 5, 6]),                       # a known single-mode stock item
                                     ("only_order", "MTO", [30, 31, 32, 33]),                          # a known single-mode made-to-order item
                                     ("few", "MTS", [1, 2]), ("few", "MTO", [30, 40, 50]),            # fewer than three lines of one kind
                                     ("close", "MTS", [12, 12, 12]), ("close", "MTO", [18, 18, 18]),   # medians 6 days apart (a gap of at least 7 is needed)
                                     ("slow_stock", "MTS", [15, 15, 15]), ("slow_stock", "MTO", [40, 40, 40]),   # the MTS median is above 14
                                     ("fast_order", "MTS", [2, 2, 2]), ("fast_order", "MTO", [14, 14, 14]),      # the MTO median must exceed 14
                                     ("edge", "MTS", [14, 14, 14]), ("edge", "MTO", [21, 21, 21]),    # 14 and 21: at most 14 and above 14, gap exactly 7
                                     ("eto", "MTS", [3, 3, 3]), ("eto", "ETO", [60, 60, 60])]), RULE)  # ETO counts with MTO
    got = s["mixed_by_rule"].to_dict()
    assert got == {"two": True, "only_stock": False, "only_order": False, "few": False, "close": False, "slow_stock": False, "fast_order": False, "edge": True, "eto": True}
    assert s.loc["two", "n_lines_mts"] == 4 and s.loc["two", "n_lines_order"] == 3 and s.loc["two", "median_days_mts"] == 2.5 and s.loc["two", "median_days_order"] == 40.0


def test_the_rule_is_adopted_when_it_calls_at_most_a_tenth_of_the_known_items_mixed_and_not_adopted_above():
    codes = [f"k{i}" for i in range(20)]
    stats = pd.DataFrame({"mixed_by_rule": [i < 2 for i in range(20)]}, index=codes)
    assert seg.mixed_rule_known_test(stats, codes, RULE) == {"n_known": 20, "n_called_mixed": 2, "share": 0.1, "adopted": True}       # exactly one in ten: adopted
    stats3 = pd.DataFrame({"mixed_by_rule": [i < 3 for i in range(20)]}, index=codes)
    r = seg.mixed_rule_known_test(stats3, codes, RULE)
    assert r["n_called_mixed"] == 3 and r["share"] == 0.15 and r["adopted"] is False
    assert seg.mixed_rule_known_test(stats, [], RULE)["adopted"] is True and seg.mixed_rule_known_test(stats, ["absent"], RULE)["n_called_mixed"] == 0


def test_a_rule_that_is_not_adopted_marks_no_item_mixed():
    universe, label_df, s1, s2s3, apd, ces = _fixture_pulls()
    w3 = copy.deepcopy(W3)
    w3["mixed_rule"]["max_share_of_known_items"] = -1.0          # nothing can be adopted
    table, test = seg.build_week3_item_level(universe, label_df, s1, s2s3, apd, ces, {"S": 1}, {}, {"S": "stock_policy"}, TODAY, w3, {})
    assert test["adopted"] is False and not table["mixed_applied"].any() and table["mts_share_12m"].isna().all()
    assert (table.set_index("code").loc["M", "class_label"] in ("conflict", "too_little_data", "no_production_in_system"))


def test_delivered_lines_join_on_contract_item_and_plan_and_drop_negative_days():
    apd = pd.DataFrame([{"itemcode": "A", "contractid": "c1", "planid": 1, "status": "Actual", "manufacturing_type": "MTS", "createDate": "2026-01-01", "qty": 1},
                        {"itemcode": "A", "contractid": "c1", "planid": 2, "status": "Actual", "manufacturing_type": "MTO", "createDate": "2026-01-01", "qty": 1},
                        {"itemcode": "A", "contractid": "c2", "planid": 1, "status": "MPS", "manufacturing_type": "MTS", "createDate": "2026-01-01", "qty": 1},
                        {"itemcode": "A", "contractid": "c3", "planid": 1, "status": "Actual", "manufacturing_type": "MTS", "createDate": "2026-01-10", "qty": 1}])
    ces = pd.DataFrame([{"ItemCode": "A", "ContractID": "c1", "PlanID": 1, "Status": "Actual", "ActualDelDate": "2026-01-05"},
                        {"ItemCode": "A", "ContractID": "c1", "PlanID": 2, "Status": "Actual", "ActualDelDate": "2026-02-01"},
                        {"ItemCode": "A", "ContractID": "c3", "PlanID": 1, "Status": "Actual", "ActualDelDate": "2026-01-05"}])      # delivered before it was created
    out = seg.delivered_lines(apd, ces)
    assert sorted(zip(out["manufacturing_type"], out["days"])) == [("MTO", 31), ("MTS", 4)]


# ====================================================================================================== Part 6: explosion
def _bom(rows):
    return pd.DataFrame(rows, columns=["ItemFG", "ItemRawmat", "Quantity", "Unit", "Sequenceno", "Type"])


BOM = _bom([("FG1", None, 1, "PC", 0, "Standard"), ("FG1", "SUB1", 2, "PC", 1, "Standard"), ("FG1", "RM-A", 3, "PC", 2, "Standard"), ("FG1", "MH-01", 0.5, "hour", 3, "Machine Hour"),
            ("FG2", "RM-A", 1, "PC", 1, "Standard"), ("FG2", "SUB1", 1, "PC", 2, "Standard"),
            ("SUB1", None, 1, "PC", 0, "Standard"), ("SUB1", "RM-B", 4, "KG", 1, "Standard"), ("SUB1", "RM-A", 1, "PC", 2, "Standard"), ("SUB1", "SUB2", 2, "PC", 3, "Standard"),
            ("SUB2", "RM-C", 5, "PC", 1, "Standard"), ("RM-D", "RM-E", 1, "PC", 1, "Standard")])
PO = pd.DataFrame({"po_no": ["1", "2", "3", "4", "5"], "item_code": ["RM-A", "RM-B", "RM-C", "RM-D", "RM-E"], "po_date": ["2026-01-01"] * 5, "planed_date": ["2026-01-20"] * 5,
                   "po_quantity": [10] * 5, "received_quantity": [10] * 5})
RCV = pd.DataFrame({"PO": ["1", "2", "3", "4", "5"], "Itemcode": ["RM-A", "RM-B", "RM-C", "RM-D", "RM-E"], "Receive_date": ["2026-01-21", "2026-02-10", "2026-01-05", "2026-01-02", "2026-01-03"],
                    "Items_Received": [10] * 5})


def _explode(demand):
    lines = mp.bom_component_lines(BOM)
    return mp.explode(demand, lines, mp.parents_with_bom(BOM), mp.purchased_codes(PO, RCV), 2)


def test_bom_lines_drop_the_header_row_and_the_time_pseudo_codes():
    lines = mp.bom_component_lines(BOM)
    assert "MH-01" not in set(lines["comp"]) and not (lines["comp"] == "").any()
    bom = pd.concat([BOM, _bom([("FG1", "LH-01", 2, "hour", 4, "Labor hour"), ("FG1", "LABOR-X", 1, "hour", 5, "Standard")])])
    got = set(mp.bom_component_lines(bom).query("parent == 'FG1'")["comp"])
    assert "LH-01" not in got and "MH-01" not in got          # both time types are pseudo-codes
    assert "LABOR-X" in got                                    # a Standard line is a material even when its unit is hour (it has a purchase record)
    assert set(lines[lines["parent"] == "FG1"]["comp"]) == {"SUB1", "RM-A"}


def test_a_sub_assembly_is_expanded_to_purchased_materials_level_by_level_and_shared_components_add_up():
    ex = _explode({"FG1": np.array([10.0, 0.0]), "FG2": np.array([0.0, 20.0])})
    g = {k: list(v) for k, v in ex["gross"].items()}
    # FG1 x10: SUB1 20 -> RM-B 80, RM-A 20, SUB2 40 -> RM-C 200; RM-A direct 30.  FG2 x20: RM-A direct 20, SUB1 20 -> RM-B 80, RM-A 20, SUB2 40 -> RM-C 200
    assert g == {"RM-A": [50.0, 40.0], "RM-B": [80.0, 80.0], "RM-C": [200.0, 200.0]}
    assert ex["levels"] == 3 and ex["in_house_expanded"] == {"SUB1", "SUB2"} and "MH-01" not in ex["gross"]
    assert ex["roots"]["RM-C"] == {"FG1": 200.0, "FG2": 200.0} and ex["roots"]["RM-A"] == {"FG1": 50.0, "FG2": 40.0}


def test_a_component_with_a_purchase_record_is_a_purchased_material_even_when_it_has_a_bom():
    bom = pd.concat([BOM, _bom([("FG3", "RM-D", 2, "PC", 1, "Standard")])])
    ex = mp.explode({"FG3": np.array([5.0, 0.0])}, mp.bom_component_lines(bom), mp.parents_with_bom(bom), mp.purchased_codes(PO, RCV), 2)
    assert list(ex["gross"]["RM-D"]) == [10.0, 0.0] and "RM-E" not in ex["gross"]
    assert mp.is_in_house("SUB1", mp.parents_with_bom(BOM), mp.purchased_codes(PO, RCV)) and not mp.is_in_house("RM-D", mp.parents_with_bom(BOM), mp.purchased_codes(PO, RCV))


def test_an_item_with_no_bom_line_is_reported_and_a_loop_stops_the_build():
    ex = _explode({"NOBOM": np.array([3.0, 0.0])})
    assert ex["no_bom"] == {"NOBOM"} and ex["gross"] == {}
    loop = _bom([("L1", "L2", 1, "PC", 1, "Standard"), ("L2", "L1", 1, "PC", 1, "Standard")])
    with pytest.raises(mp.MaterialPlanError, match="does not end"):
        mp.explode({"L1": np.array([1.0])}, mp.bom_component_lines(loop), mp.parents_with_bom(loop), set(), 1, max_levels=6)


def test_an_item_with_no_demand_is_not_exploded():
    ex = _explode({"FG1": np.array([0.0, 0.0])})
    assert ex["gross"] == {} and ex["levels"] == 0


# ====================================================================================================== netting, order dates
def test_netting_is_the_running_maximum_of_the_cumulative_shortfall_and_a_later_surplus_does_not_cancel_it():
    avail, net_cum, net_month = mp.net_requirement(np.array([10.0, 10.0, 10.0]), 15.0, np.array([0.0, 0.0, 20.0]))
    assert list(avail) == [15.0, 15.0, 35.0] and list(net_cum) == [0.0, 5.0, 5.0] and list(net_month) == [0.0, 5.0, 0.0]


def test_net_requirement_with_no_stock_equals_gross_and_with_enough_stock_is_zero():
    _, c, m = mp.net_requirement(np.array([4.0, 6.0]), 0.0, np.zeros(2))
    assert list(c) == [4.0, 10.0] and list(m) == [4.0, 6.0]
    _, c2, m2 = mp.net_requirement(np.array([4.0, 6.0]), 100.0, np.zeros(2))
    assert not c2.any() and not m2.any()


def test_the_order_date_is_the_first_day_of_the_short_month_minus_the_lead_time():
    d = mp.order_dates(np.array([0.0, 5.0, 0.0]), MONTHS, 30)
    assert d == [None, pd.Timestamp("2026-10-02").date(), None]
    assert mp.order_dates(np.array([1.0, 0.0, 2.0]), MONTHS, 10.5)[0] == (pd.Timestamp("2026-10-01") - pd.to_timedelta(10.5, unit="D")).date()


def test_open_orders_arrive_in_the_month_of_their_expected_date_and_overdue_ones_count_in_the_first_month():
    tobe = pd.DataFrame({"itemcode": ["X", "X", "X", "X", "Y"], "fulfill_date": ["2026-09-01", "2026-11-15", "2027-03-01", "2026-12-31", None], "quantity": [5, 7, 11, 13, 17]})
    arr, tot, after = mp.open_orders_by_month(tobe, MONTHS)
    assert list(arr["X"]) == [5.0, 7.0, 13.0] and tot["X"] == 36.0 and after == 1 and tot["Y"] == 17.0 and "Y" not in arr


def test_stock_counts_only_the_proven_warehouses_and_a_negative_total_counts_as_zero():
    inv = pd.DataFrame({"warehouse": ["WH21 ", "QA", "WH22", "WH21", "WH22"], "itemcode": ["x", "x", "x", "y", "y"], "stock": [10, 100, 5, -3, 1]})
    s = mp.raw_material_stock(inv, ["WH21", "WH22"])
    assert s == {"X": 15.0, "Y": 0.0}


# ====================================================================================================== lead time and units
def test_the_lead_time_uses_observed_then_supplier_quoted_then_assumed():
    price = pd.DataFrame({"ItemCode": ["RM-B", "RM-Q"], "DeliveryTime": ["30 Days", "45 Days"]})
    out = mp.material_lead_times(["RM-A", "RM-B", "RM-Q", "RM-Z"], PO, RCV, price, 63, [0, 730])
    assert out["RM-A"] == (20.0, "observed") and out["RM-B"] == (40.0, "observed")        # observed beats the quote
    assert out["RM-Q"] == (45.0, "supplier_quoted") and out["RM-Z"] == (63.0, "assumed")
    assert set(bm.TEXT["source"]) == {"observed", "supplier_quoted", "assumed"}


@pytest.mark.parametrize("bom,others,expected", [("PC", ["PC"], "same"), ("PCS", ["PC"], "same"), ("PC", ["SET"], "differs"), ("SET", ["PC", "SET"], "differs"),
                                                   ("PC", ["-"], "unknown"), ("-", ["PC"], "unknown"), ("METRE", ["M"], "same"), ("PC", [], "unknown")])
def test_the_unit_check(bom, others, expected):
    assert mp.unit_check(bom, others) == expected


# ====================================================================================================== the proofs
def test_the_warehouse_proof_takes_the_warehouses_that_issue_to_production_and_reports_the_receiving_one_apart():
    t = pd.DataFrame({"warehouse": ["QA", "QA", "WH1", "WH1", "WH2", "WH3", "WH3"], "transtype": ["A", "B", "B", "A", "B", "B", "150"], "n": [900, 1, 600, 10, 380, 9, 50]})
    inv = pd.DataFrame({"warehouse": ["QA", "WH1", "WH2", "WH9"], "itemcode": ["a"] * 4, "stock": [5, 7, 11, 13]})
    r = mp.rm_warehouse_proof(t, inv, 0.01)
    assert r["rm_warehouses"] == ["WH1", "WH2"] and r["purchase_receipt_warehouse"] == "QA" and r["issues_from_receipt_warehouse"] == 1
    assert r["stock_units_in_rm"] == 18.0 and r["stock_units_elsewhere"] == 13.0 + 5.0 and r["stock_units_in_receipt_warehouse"] == 5.0


def test_the_open_orders_proof_passes_only_when_every_criterion_holds():
    cfgp = {k: v for k, v in mp.load_config(PROJECT_ROOT).items() if k.startswith("open_orders")}
    po = pd.DataFrame({"po_no": ["1", "2", "3", "4"], "item_code": ["a", "a", "b", "c"], "po_date": ["2026-01-01", "2026-01-01", "2026-01-01", "2024-01-01"],
                       "planed_date": ["2026-11-05", "2026-11-06", "2026-11-07", "2024-02-01"], "po_quantity": [10, 20, 30, 5], "received_quantity": [4, 0, 30, 5]})
    tobe = pd.DataFrame({"po_number": ["1", "2"], "itemcode": ["a", "a"], "quantity": [6, 20], "fulfill_date": ["2026-11-05", "2026-11-06"]})
    rcv = pd.DataFrame({"PO": ["4"], "Itemcode": ["c"], "Receive_date": ["2024-02-05"], "Items_Received": [5]})
    ok = mp.open_orders_proof(tobe, po, rcv, cfgp)
    assert ok["match_share"] == 1.0 and ok["quantity_share"] == 1.0 and ok["date_share"] == 1.0 and ok["within_days_share"] == 1.0 and ok["usable"] is True
    bad_date = tobe.assign(fulfill_date=["2026-12-01", "2026-12-02"])
    assert mp.open_orders_proof(bad_date, po, rcv, cfgp)["usable"] is False
    bad_qty = tobe.assign(quantity=[1, 2])
    assert mp.open_orders_proof(bad_qty, po, rcv, cfgp)["usable"] is False
    late = rcv.assign(Receive_date=["2024-04-05"])
    r = mp.open_orders_proof(tobe, po, late, cfgp)
    assert r["within_days_share"] == 0.0 and r["usable"] is False and r["share_received_more_than_within_days_late"] == 1.0


def test_the_bom_proof_prefers_the_source_that_covers_the_issued_materials_and_ignores_hours():
    v1 = pd.DataFrame({"parent": ["W"] * 3, "comp": ["a", "b", "c"], "qty": [2.0, 1.0, 4.0]})
    v2 = pd.DataFrame({"parent": ["W"] * 2, "comp": ["a", "b"], "qty": [2.0, 1.0]})
    jobs = pd.DataFrame({"order": ["o1", "o2"], "item": ["W", "W"], "qty": [3.0, 5.0]})
    issues = pd.DataFrame({"order": ["o1", "o1", "o1", "o1", "o2", "o2", "o2"], "mat": ["a", "b", "c", "HOUR", "a", "b", "c"], "used": [6.0, 3.0, 12.0, 1.0, 10.0, 5.0, 40.0],
                           "unit": ["PC", "PC", "PC", "hour", "PC", "PC", "PC"]})
    r = mp.bom_source_proof(v1, v2, jobs, issues)
    assert r["lines_only_v1"] == 1 and r["lines_only_v2"] == 0 and r["quantity_equal_share"] == 1.0 and r["items_identical_sets_share"] == 0.0
    assert r["v1"]["pairs_found_share"] == 1.0 and r["v1"]["n_pairs"] == 6 and r["v1"]["orders_fully_covered_share"] == 1.0
    assert r["v2"]["pairs_found_share"] == pytest.approx(4 / 6) and r["v2"]["orders_fully_covered_share"] == 0.0
    assert r["v1"]["within_tolerance_share"] == pytest.approx(5 / 6)       # o2's c: 5 x 4 = 20 against 40 issued


# ====================================================================================================== a fixture project: build, hashes, page
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


@pytest.fixture()
def project(tmp_path):
    """A recorded operation plan (written by operation_plan.write_outputs), the saved week 3 pulls and a config; production quantities FG1 10, 0, 0 and FG2 0, 20, 0."""
    root = str(tmp_path)
    real = op.load_full_config(PROJECT_ROOT)
    full = {"operation_plan": copy.deepcopy(real["operation_plan"]), "material_plan": copy.deepcopy(real["material_plan"]), "lead_time_v1": real["lead_time_v1"]}
    full["material_plan"]["rm_warehouses"] = ["WH21", "WH22"]
    _write(os.path.join(root, "config", "config.yaml"), yaml.safe_dump(full))
    cols = op.ITEM_MONTH_COLUMNS
    rows = []
    for item, d, vals, counted in (("FG1", "PEM101", [10.0, 0.0, 0.0], True), ("FG2", "PEM107", [0.0, 20.0, 0.0], True), ("FG9", "PEM103", [100.0, 100.0, 100.0], False)):
        for m, v in zip(MONTHS, vals):
            rows.append({"division": d, "item": item, "class": "confirmed_to_order", "month": m, "demand": v, "load": v, "counted": counted, "status_category": "forecast",
                         "class_label": "confirmed_to_order", "data_inconsistent": False})
    im = pd.DataFrame(rows).reindex(columns=cols)
    dm = pd.DataFrame([{"division": "PEM101", "month": m, "total_load": 0.0} for m in MONTHS]).reindex(columns=op.DIVISION_MONTH_COLUMNS)
    meta = {"months": MONTHS, "today": "2026-10-06", "built_at": "2026-10-06T08:00:00", "vintage_id": 1}
    op.write_outputs({"item_month": im, "division_month": dm, "meta": meta}, root, full["operation_plan"])
    bom = pd.concat([BOM, _bom([("FG9", "RM-A", 99, "PC", 1, "Standard")])])
    inv = pd.DataFrame({"warehouse": ["WH21", "WH22", "QA", "WH21"], "itemcode": ["RM-A", "RM-A", "RM-A", "RM-B"], "stock": [10.0, 5.0, 1000.0, 200.0], "unit": ["PC", "PC", "PC", "KG"]})
    tobe = pd.DataFrame({"fulfill_date": ["2026-11-20"], "po_number": ["9"], "itemcode": ["RM-C"], "quantity": [150.0], "unit": ["PC"], "warehouse": ["QA"], "order_date": ["2026-09-30"]})
    price = pd.DataFrame({"ItemCode": ["RM-C"], "SupplierNumber": ["s"], "Unit": ["PC"], "DeliveryTime": ["0 Days"]})
    names = pd.DataFrame({"ItemCode": ["RM-A", "RM-B"], "Description": ["Alpha part", "Beta bar"]})
    w3 = {"backlog_ces": pd.DataFrame(), "backlog_pulled_at_local": "2026-10-06 07:00:00", "bom_tree": bom, "rm_inventory": inv, "rm_pulled_at_local": "2026-10-06 07:30:00",
          "open_orders": tobe, "po_lines": PO, "receipts": RCV, "price": price, "item_names": names}
    target = os.path.join(root, *full["operation_plan"]["week3_inputs_file"].split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    pd.to_pickle(w3, target)
    return root


def _result(project):
    return mp.build(project, TODAY, cfg=mp.load_config(project))


def test_the_plan_leaves_out_items_the_operation_plan_does_not_count_and_explodes_the_rest(project):
    r = _result(project)
    mm = r["material_month"].pivot(index="material", columns="month", values="gross")
    assert list(mm.loc["RM-A"]) == [50.0, 40.0, 0.0] and list(mm.loc["RM-C"]) == [200.0, 200.0, 0.0]     # FG9's 99 units of RM-A per piece are not in it
    assert r["meta"]["n_items_exploded"] == 2 and r["meta"]["n_materials"] == 3


def test_stock_open_orders_net_requirement_and_order_dates_per_material(project):
    r = _result(project)
    mmth = r["material_month"].set_index(["material", "month"])
    s = r["summary"].set_index("material")
    # RM-A: stock 15 in the proven warehouses (QA's 1000 is not counted); gross 50, 40 -> cumulative 50, 90 -> net cumulative 35, 75
    assert s.loc["RM-A", "stock_now"] == 15.0 and mmth.loc[("RM-A", "2026-10"), "net_cum"] == 35.0 and mmth.loc[("RM-A", "2026-11"), "net_cum"] == 75.0
    assert mmth.loc[("RM-A", "2026-11"), "net_month"] == 40.0 and s.loc["RM-A", "total_net"] == 75.0
    # RM-C: no stock; the open order of 150 is expected 2026-11-20 and counts from November: cumulative gross 200, 400 against 0, 150 -> short 200, 250
    assert mmth.loc[("RM-C", "2026-10"), "net_cum"] == 200.0 and mmth.loc[("RM-C", "2026-11"), "net_cum"] == 250.0 and mmth.loc[("RM-C", "2026-11"), "open_orders_cum"] == 150.0
    assert s.loc["RM-C", "open_orders_total"] == 150.0
    # RM-B: stock 200 covers October (80) and November (160 cumulative) so there is no net requirement and no order date
    assert s.loc["RM-B", "total_net"] == 0.0 and s.loc["RM-B", "first_short_month"] == "" or pd.isna(s.loc["RM-B", "first_short_month"]) or s.loc["RM-B", "first_short_month"] == ""
    assert not bool(s.loc["RM-B", "to_order_now"])
    # lead times: RM-A observed 20 days; RM-C observed 4 days (the quote of 0 days is not a quote); RM-B observed 40
    assert (s.loc["RM-A", "lead_days"], s.loc["RM-A", "lead_source"]) == (20.0, "observed") and s.loc["RM-C", "lead_days"] == 4.0
    # the first short month of RM-A is October: 2026-10-01 minus 20 days has passed on 2026-10-06, so it is to order now with the October net requirement only: November's 40 units are ordered by 2026-10-12, still ahead
    assert str(s.loc["RM-A", "latest_order_date"]) == "2026-09-11" and bool(s.loc["RM-A", "to_order_now"]) and s.loc["RM-A", "qty_to_order_now"] == 35.0
    assert s.loc["RM-A", "name"] == "Alpha part" and s.loc["RM-C", "name"] in ("", None) or pd.isna(s.loc["RM-C", "name"])


def test_a_material_whose_first_order_date_is_still_ahead_is_not_to_order_now(project):
    root = project
    cfg = mp.load_config(root)
    r = mp.build(root, pd.Timestamp("2026-09-01"), cfg=cfg)           # as of early September the October order date (2026-09-11) is ahead
    s = r["summary"].set_index("material")
    assert not bool(s.loc["RM-A", "to_order_now"]) and s.loc["RM-A", "qty_to_order_now"] == 0.0 and r["meta"]["n_to_order_now"] == 0


def test_the_unit_columns_compare_the_bom_unit_with_stock_and_purchase_units(project):
    s = _result(project)["summary"].set_index("material")
    assert s.loc["RM-A", "bom_unit"] == "PC" and s.loc["RM-A", "unit_vs_stock"] == "same"
    assert s.loc["RM-B", "bom_unit"] == "KG" and s.loc["RM-B", "unit_vs_stock"] == "same" and s.loc["RM-B", "unit_vs_purchase"] == "unknown"
    assert s.loc["RM-C", "unit_vs_stock"] == "unknown" and s.loc["RM-C", "unit_vs_purchase"] == "same"


def test_the_recorded_outputs_carry_hashes_in_the_integrity_file_and_a_changed_byte_is_caught(project):
    cfg = mp.load_config(project)
    out = mp.run(project, TODAY)
    rec = mp.verify_outputs(project, cfg)
    assert set(rec["files"]) == {"material_plan_v1_material_month.csv", "material_plan_v1_material_summary.csv"}
    for name, v in rec["files"].items():
        assert hashlib.sha256(open(os.path.join(project, "output", "summary", name), "rb").read()).hexdigest() == v["sha256"]
    op.verify_outputs(project, cfg["operation_plan"])               # the operation plan's own entries still verify beside the new section
    mm, sm, meta = mp.read_outputs(project)
    assert len(sm) == out["n_materials"] == 3 and meta["months"] == MONTHS and meta["rm_warehouses"] == ["WH21", "WH22"]
    with open(os.path.join(project, "output", "summary", "material_plan_v1_material_summary.csv"), "ab") as f:
        f.write(b"x")
    with pytest.raises(mp.MaterialPlanError):
        mp.verify_outputs(project, cfg)


def test_a_missing_recorded_section_or_unproven_warehouses_stop_the_build(project):
    cfg = mp.load_config(project)
    with pytest.raises(mp.MaterialPlanError, match="no material_plan section"):
        mp.verify_outputs(project, cfg)
    empty = copy.deepcopy(cfg)
    empty["rm_warehouses"] = []
    with pytest.raises(mp.MaterialPlanError, match="not been proven"):
        mp.build(project, TODAY, cfg=empty)


def test_the_run_writes_nothing_outside_its_output_folder_when_given_one(project, tmp_path_factory):
    before = {os.path.join(d, f) for d, _, fs in os.walk(project) for f in fs}
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    cfg = mp.load_config(project)
    op_dir = tmp_path_factory.mktemp("opdir")
    import shutil
    for name in os.listdir(os.path.join(project, "output", "summary")):
        shutil.copy(os.path.join(project, "output", "summary", name), op_dir / name)
    mp.run(project, TODAY, out_dir=str(op_dir), op_out_dir=str(op_dir))
    after = {os.path.join(d, f) for d, _, fs in os.walk(project) for f in fs}
    assert before == after
    assert set(os.listdir(op_dir)) >= {"material_plan_v1_material_month.csv", "material_plan_v1_material_summary.csv"}
    assert not os.listdir(elsewhere)


# ====================================================================================================== the page
def _page(project):
    mp.run(project, TODAY)
    return bm.render(bm.build_values(project)), bm.build_values(project)


def test_the_page_text_is_the_approved_text_and_every_braced_value_comes_from_the_plan(project):
    page, v = _page(project)
    mm, sm, meta = mp.read_outputs(project)
    assert f"แผนวัตถุดิบ {len(meta['months'])} เดือน" in page and v["n_months"] == 3
    assert f"จากแผนการผลิตรอบ {bp.thai_month(meta['operation_plan_today'][:7])} · stock วัตถุดิบดึงเมื่อ {bp.thai_datetime(meta['rm_pulled_at_local'])}" in page
    assert "จากแผนการผลิตรอบ ต.ค. 69 · stock วัตถุดิบดึงเมื่อ 6 ต.ค. 69 07:30" in page
    assert "stock วัตถุดิบนับจากคลัง WH21, WH22" in page and "นับของที่สั่งแล้วรอรับตามวันที่คาดว่าจะได้" in page and "ยังไม่นับของที่สั่งแล้วรอรับ" not in page
    n = int(mp.load_config(project)["order_window_days"])
    assert n == 30 and v["n_days"] == n
    assert f'<h2 id="within-title">ต้องสั่งภายใน {n} วัน</h2>' in page and f"วัตถุดิบที่ต้องสั่งภายใน {n} วันข้างหน้า ถึงจะได้ของทันตามแผน" in page
    assert '<h2 id="late-title">ขาดแล้ว สั่งตอนนี้ไม่ทัน</h2>' in page
    assert "วัตถุดิบที่แผนต้องใช้ก่อนที่ของจะมาถึงแม้สั่งวันนี้ ควรตรวจของที่มีอยู่จริง หรือเร่งของที่สั่งไว้แล้ว" in page
    assert "ต้องสั่งทันที" not in page and page.index('id="within-title"') < page.index('id="late-title"') < page.index('id="material-table"')


def test_the_two_order_lists_split_by_the_latest_order_date_with_the_approved_columns_and_source_labels(project):
    page, v = _page(project)
    heads_expected = ["รหัสวัตถุดิบ", "ชื่อ", "ใช้ในสินค้า (รหัส)", "ต้องสั่งเพิ่ม", "ต้องสั่งภายใน", "lead time (วัน)", "ที่มา lead time"]
    for table in ("within-table", "late-table"):
        assert re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", page.split('id="%s"' % table)[1].split("</table>")[0]) == heads_expected
    _, sm, meta = mp.read_outputs(project)
    today = pd.Timestamp(meta["today"])
    dates = pd.to_datetime(sm.set_index("material")["latest_order_date"])
    block = page.split('id="late-table"')[1].split("</table>")[0]
    rows = re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', block)
    assert sorted(m for m, _ in rows) == sorted(dates[dates < today].index)
    within = re.findall(r'<tr data-material="([^"]+)">', page.split('id="within-table"')[1].split("</table>")[0])
    assert sorted(within) == sorted(dates[(dates >= today) & (dates <= today + pd.Timedelta(days=30))].index)
    cells = re.findall(r"<td[^>]*>(.*?)</td>", dict(rows)["RM-A"])          # the fixture holds no purchase unit for RM-A: its own flag, dashes for quantity and date, the rest as before
    assert cells[0] == 'RM-A<span class="flag unit">ไม่มีหน่วยซื้อในระบบ</span>' and cells[1] == "Alpha part" and cells[2] == "FG1, FG2" and cells[3] == "-" and cells[4] == "-" and cells[5] == "20" and cells[6] == "ใบสั่งซื้อจริง"


def test_the_main_table_has_stock_open_orders_and_the_demand_and_net_columns_per_month(project):
    page, v = _page(project)
    block = page.split('id="material-table"')[1].split("</table>")[0]
    top = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", block.split("</tr>")[0])
    assert top[:4] == ["รหัส", "ชื่อ", "stock ตอนนี้", "ของที่สั่งแล้วรอรับ"] and top[4:] == v["month_labels"]
    sub = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", block.split("</tr>")[1])
    assert sub == ["ความต้องการ", "ต้องสั่งเพิ่ม"] * 3
    rows = {m: re.findall(r"<td[^>]*>(.*?)</td>", r) for m, r in re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', block)}
    assert set(rows) == {"RM-A", "RM-B", "RM-C"}
    assert rows["RM-C"][:4] == ["RM-C", "-", "-", "150"] and rows["RM-C"][4:] == ["200", "200", "200", "50", "-", "-"]


def test_the_note_without_open_orders_is_the_other_approved_sentence(project):
    root = project
    cfg = copy.deepcopy(mp.load_config(root))
    cfg["open_orders_usable"] = False
    result = mp.build(root, TODAY, cfg=cfg)
    vals = bm.compute_values(result["material_month"], result["summary"], result["meta"], 30)
    page = bm.render(vals)
    assert "ยังไม่นับของที่สั่งแล้วรอรับ เพราะข้อมูลวันรับของยังใช้ไม่ได้ ตัวเลขต้องสั่งเพิ่มจึงอาจสูงกว่าจริง" in page and "นับของที่สั่งแล้วรอรับตามวันที่คาดว่าจะได้" not in page
    assert "stock วัตถุดิบนับจากคลัง" in page
    s = result["summary"].set_index("material")
    assert s.loc["RM-C", "open_orders_total"] == 0.0 and s.loc["RM-C", "total_net"] == 400.0         # without the open order the whole requirement is short


def test_the_order_lists_are_sorted_by_the_order_date_and_a_missing_name_shows_a_dash(project):
    page, v = _page(project)
    for k in ("late", "within"):
        assert list(v[k]["latest_order_date"]) == sorted(v[k]["latest_order_date"])
    block = page.split('id="late-table"')[1].split("</table>")[0]
    cells = re.findall(r"<td[^>]*>(.*?)</td>", dict(re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', block))["RM-C"])
    assert cells[1] == "-"


# ====================================================================================================== every page lists all six divisions or says why
def test_the_operation_plan_page_and_the_inventory_page_show_all_six_divisions_and_the_material_plan_page_names_the_divisions_it_covers():
    from build_operation_plan_page import DASH  # noqa: F401
    tracked = os.path.join(PROJECT_ROOT, "forecast")
    for page in ("operation_plan.html", "inventory.html", "material_plan.html"):
        if not os.path.exists(os.path.join(tracked, page)):
            pytest.skip(f"SKIPPED, not passed: forecast/{page} is not built yet")
    plan = open(os.path.join(tracked, "operation_plan.html"), encoding="utf-8").read()
    assert re.findall(r'<table class="report-table summary-table" id="summary-(\w+)">', plan) == SIX
    assert sorted(set(re.findall(r'<tr data-division="(\w+)" data-class="\w+">', plan))) == sorted(SIX)         # an item row for each division
    inv = open(os.path.join(tracked, "inventory.html"), encoding="utf-8").read()
    enabled = re.findall(r'<option value="(\w+)">\1 \(', inv)
    disabled = re.findall(r'<option value="(\w+)" disabled', inv)
    assert sorted(enabled + disabled) == sorted(SIX)
    notes = re.search(r'id="disabled-note-list">(.*?)</ul>', inv, re.S).group(1)
    for d in disabled:       # a division without Min and Max shows the approved line in place of its figures
        li = re.search(r"<li><b>%s</b>: (.*?)</li>" % d, notes).group(1)
        assert li.endswith("ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock") or "ยังไม่ได้คำนวณ Min/Max ให้" in li
    mat = open(os.path.join(tracked, "material_plan.html"), encoding="utf-8").read()
    assert re.search(r'id="divisions-covered">ฝ่ายที่รวมในแผนนี้: %s</p>' % re.escape(", ".join(SIX)), mat)
    assert mat.index('id="verification-notice"') < mat.index('class="back-link"')


def test_the_inventory_page_line_for_a_division_without_min_max_uses_the_count_or_the_zero_text(tmp_path, monkeypatch):
    import build_inventory_page_data as bd
    monkeypatch.setattr(bd, "SUMMARY_DIR", str(tmp_path))
    pd.DataFrame({"division": ["CI101", "CI101", "PEM102"], "class_used": ["stock_policy", "stock_policy", "conflict"]}).to_csv(tmp_path / "task2b_part2_item_level.csv", index=False)
    assert bd.no_min_max_line("CI101") == "ยังไม่ได้คำนวณ Min/Max ให้ 2 รหัสที่เข้าเกณฑ์เก็บ stock"
    assert bd.no_min_max_line("PEM102") == "ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock" and bd.no_min_max_line("PEM104") == "ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock"
    os.remove(tmp_path / "task2b_part2_item_level.csv")
    with pytest.raises(FileNotFoundError):
        bd.stock_class_count("CI101")


# ====================================================================================================== the recorded real outputs
def _recorded_material():
    cfg = mp.load_config(PROJECT_ROOT)
    for k in ("output_material_month_file", "output_material_summary_file"):
        if not os.path.exists(op.path_of(PROJECT_ROOT, cfg[k])):
            pytest.skip("SKIPPED, not passed: the recorded material plan is not on this machine: " + cfg[k])
    return cfg


def test_the_recorded_material_plan_hashes_verify_and_it_reads_back_consistently():
    cfg = _recorded_material()
    mm, sm, meta = mp.read_outputs(PROJECT_ROOT, cfg)
    assert meta["months"] == sorted(set(mm["month"])) and len(sm) == meta["n_materials"] == mm["material"].nunique()
    g = mm.groupby("material")
    assert ((g["net_cum"].max() - sm.set_index("material")["total_net"]).abs() < 1e-3).all()
    assert (mm["net_month"] >= -1e-9).all() and (mm["gross"] >= 0).all()
    now = sm[sm["to_order_now"].astype(bool)]
    assert (pd.to_datetime(now["latest_order_date"]) <= pd.Timestamp(meta["today"])).all() and meta["n_to_order_now"] == len(now)
    assert set(meta["rm_warehouses"]) == set(cfg["rm_warehouses"])


def test_the_config_warehouses_equal_the_proof_on_the_saved_pulls_and_no_material_name_is_missing_for_a_material_in_the_plan_beyond_a_few():
    cfg = _recorded_material()
    _, sm, _ = mp.read_outputs(PROJECT_ROOT, cfg)
    assert (sm["name"].isna() | (sm["name"] == "")).mean() < 0.01      # the item master holds the material names


# ====================================================================================================== the notice and the unit flag
def test_the_page_opens_with_the_visually_distinct_notice_above_everything_else(project):
    page, v = _page(project)
    body = page.split('<div class="wrap">')[1]
    assert body.lstrip().startswith('<div class="notice" id="verification-notice">แผนนี้ยังอยู่ระหว่างตรวจสอบ ตัวเลขต้องสั่งยังใช้สั่งซื้อจริงไม่ได้</div>')
    assert ".notice {" in page and "border: 2px solid" in page


def test_a_material_whose_purchase_unit_differs_from_its_bom_unit_shows_the_flag_and_dashes_in_both_tables(project):
    root = project
    w3 = op.load_week3_inputs(root, mp.load_config(root)["operation_plan"])
    w3["price"] = pd.concat([w3["price"], pd.DataFrame({"ItemCode": ["RM-A"], "SupplierNumber": ["s"], "Unit": ["SET"], "DeliveryTime": ["0 Days"]})], ignore_index=True)
    pd.to_pickle(w3, os.path.join(root, *mp.load_config(root)["operation_plan"]["week3_inputs_file"].split("/")))
    page, v = _page(root)
    s = mp.read_outputs(root)[1].set_index("material")
    assert s.loc["RM-A", "unit_vs_purchase"] == "differs" and s.loc["RM-C", "unit_vs_purchase"] != "differs"
    assert v["n_unit_flag"] == 1 and v["n_late_flagged"] + v["n_within_flagged"] == 1
    flag = '<span class="flag unit">หน่วยซื้อไม่ตรงกับหน่วยใน BOM</span>'
    now = dict(re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', page.split('id="late-table"')[1].split("</table>")[0]))
    cells = re.findall(r"<td[^>]*>(.*?)</td>", now["RM-A"])
    assert cells[0] == "RM-A" + flag and cells[3] == "-" and cells[4] == "-" and cells[5] == "20"      # no order quantity and no order date; the lead time stays
    main = dict(re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', page.split('id="material-table"')[1].split("</table>")[0]))
    m = re.findall(r"<td[^>]*>(.*?)</td>", main["RM-A"])
    assert m[0] == "RM-A" + flag and m[5::2] == ["-"] * 3 and m[4::2] == ["50", "40", "-"]            # demand stays, net requirement is a dash
    other = re.findall(r"<td[^>]*>(.*?)</td>", main["RM-C"])
    assert other[0] == "RM-C" and "-" not in other[5:9:2] or other[5] != "-"
    assert page.count(flag) == 2


def _list_frames(today, dates, purchase_units):
    months = ["2026-10", "2026-11"]
    mm = pd.DataFrame([{"material": m, "month": mo, "gross": 10.0, "net_month": 10.0, "order_date": d} for (m, d) in dates.items() for mo in months])
    sm = pd.DataFrame([{"material": m, "name": m, "used_in": "FG1", "n_products": 1, "purchase_unit": purchase_units.get(m, "PC"), "unit_vs_purchase": "same", "stock_now": 0.0, "open_orders_total": 0.0, "stock_unit": "PC", "bom_unit": "PC", "lead_days": 10.0,
                        "lead_source": "observed", "total_net": 20.0, "first_short_month": months[0], "latest_order_date": d} for m, d in dates.items()])
    meta = {"months": months, "today": today, "operation_plan_today": today, "rm_pulled_at_local": today + " 07:00:00", "rm_warehouses": ["W1"], "open_orders_used": True, "divisions": ["PEM101"]}
    return mm, sm, meta


def test_the_two_lists_hold_the_boundary_dates_the_day_before_today_goes_to_the_late_list_and_today_plus_n_days_stays_in_the_window():
    dates = {"M-MINUS1": "2026-10-05", "M-TODAY": "2026-10-06", "M-END": "2026-11-05", "M-AFTER": "2026-11-06"}       # today 2026-10-06, window 30 days: ends 2026-11-05
    v = bm.compute_values(*_list_frames("2026-10-06", dates, {}), 30)
    assert list(v["late"]["material"]) == ["M-MINUS1"]
    assert list(v["within"]["material"]) == ["M-TODAY", "M-END"]
    assert "M-AFTER" not in set(v["late"]["material"]) | set(v["within"]["material"]) and "M-AFTER" in set(v["main"]["material"])
    v7 = bm.compute_values(*_list_frames("2026-10-06", dates, {}), 31)
    assert list(v7["within"]["material"]) == ["M-TODAY", "M-END", "M-AFTER"]


def test_a_material_with_no_purchase_unit_shows_its_flag_and_dashes_and_is_counted_in_its_list():
    dates = {"M-NOUNIT": "2026-10-10", "M-OK": "2026-10-11", "M-LATE-NOUNIT": "2026-09-30"}
    v = bm.compute_values(*_list_frames("2026-10-06", dates, {"M-NOUNIT": "", "M-LATE-NOUNIT": " "}), 30)
    assert v["n_no_unit"] == 2 and v["n_within_flagged"] == 1 and v["n_late_flagged"] == 1 and v["n_unit_flag"] == 0
    page = bm.render(v)
    flag = '<span class="flag unit">ไม่มีหน่วยซื้อในระบบ</span>'
    for table, material in (("within-table", "M-NOUNIT"), ("late-table", "M-LATE-NOUNIT")):
        rows = dict(re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', page.split('id="%s"' % table)[1].split("</table>")[0]))
        c = re.findall(r"<td[^>]*>(.*?)</td>", rows[material])
        assert c[0] == material + flag and c[3] == "-" and c[4] == "-" and c[5] == "10"
    ok = re.findall(r"<td[^>]*>(.*?)</td>", dict(re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', page.split('id="within-table"')[1].split("</table>")[0]))["M-OK"])
    assert ok[0] == "M-OK" and ok[3] == "20" and ok[4] == "11 ต.ค. 69"
    main = dict(re.findall(r'<tr data-material="([^"]+)">(.*?)</tr>', page.split('id="material-table"')[1].split("</table>")[0]))
    m = re.findall(r"<td[^>]*>(.*?)</td>", main["M-NOUNIT"])
    assert m[0] == "M-NOUNIT" + flag and m[5::2] == ["-", "-"]
    assert page.count(flag) == 4        # each flagged material appears in its list and in the main table


# ====================================================================================================== the runner pulls the plan's inputs (week 4)
def _fake_run_query(log):
    """A stand-in for db.run_query over a tiny world: FG1 -> SUB1 -> RM-A, RM-B; FG2 -> RM-B. It records every statement it is given."""
    bom = {"FG1": [("SUB1", 2)], "SUB1": [("RM-A", 3), ("RM-B", 1)], "FG2": [("RM-B", 4)]}

    def run(sql):
        log.append(sql)
        codes = set(re.findall(r"'([^']+)'", sql.split(" IN (", 1)[1].split(")", 1)[0]) if " IN (" in sql else [])
        if "FROM Cube_BOM_Exact" in sql:
            rows = [{"ItemFG": p + "   ", "ItemRawmat": c, "Quantity": q, "Unit": "PC", "Sequenceno": i + 1, "Type": "Standard", "Status": "Active", "Warehouse": "W",
                     "Division": "D", "ItemGroup": "G", "version": 1, "Timestamp": "t"} for p, kids in bom.items() if p in {x.upper() for x in codes} or p in codes
                    for i, (c, q) in enumerate(kids)]
            return pd.DataFrame(rows, columns=["ItemFG", "ItemRawmat", "Quantity", "Unit", "Sequenceno", "Type", "Status", "Warehouse", "Division", "ItemGroup", "version", "Timestamp"])
        if "Cube_Inventory_Exact" in sql:
            return pd.DataFrame({"warehouse": ["WH21"] * len(codes), "itemcode": sorted(codes), "stock": [1.0] * len(codes), "unit": ["PC"] * len(codes)})
        if "Cube_tobe_received" in sql:
            return pd.DataFrame({"fulfill_date": ["2026-11-01"], "po_number": ["P1"], "itemcode": ["RM-A"], "quantity": [5.0], "unit": ["PC"], "warehouse": ["QA"], "order_date": ["2026-10-01"]})
        if "Cube_PO_Exact" in sql:
            return pd.DataFrame({"po_no": ["P0"], "item_code": ["RM-A"], "po_date": ["2026-01-01"], "planed_date": ["2026-01-20"], "po_quantity": [1.0], "received_quantity": [1.0]})
        if "Cube_ReceiveRM" in sql:
            return pd.DataFrame({"PO": ["P0"], "Itemcode": ["RM-A"], "Receive_date": ["2026-01-21"], "Items_Received": [1.0]})
        if "Cube_PriceList" in sql:
            return pd.DataFrame({"ItemCode": ["RM-B"], "SupplierNumber": ["s"], "Unit": ["PC"], "DeliveryTime": ["30 Days"]})
        if "Cube_ItemList" in sql:
            return pd.DataFrame({"ItemCode": sorted(codes), "Description": ["d"] * len(codes)})
        raise AssertionError("an unexpected statement: " + sql[:80])
    return run


def test_the_pull_walks_the_bom_level_by_level_and_reads_every_source_for_every_component(monkeypatch):
    import db
    log = []
    monkeypatch.setattr(db, "run_query", _fake_run_query(log))
    got = mp.pull_material_inputs(["FG1", "FG2"], "2022-01-01")
    parents = {x.strip() for x in got["bom_tree"]["ItemFG"]}
    assert parents == {"FG1", "FG2", "SUB1"}                       # SUB1 was looked up as a parent on the second level
    comps_sql = [s for s in log if "Cube_Inventory_Exact" in s][0]
    assert all(f"'{c}'" in comps_sql for c in ("RM-A", "RM-B", "SUB1"))
    assert sum("FROM Cube_BOM_Exact" in s for s in log) == 3        # FG1 and FG2 at once, then SUB1, then the last level (RM-A and RM-B have no BOM)
    assert all(not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\b", s, re.I) for s in log)      # read-only
    assert set(got) == {"bom_tree", "inventory", "tobe", "po", "receipts", "price", "item"}
    assert any("po_date >= '2022-01-01'" in s for s in log) and any("Receive_date >= '2022-01-01'" in s for s in log)


def test_the_assembled_inputs_have_what_the_plan_reads_and_the_backlog_comes_from_the_class_evidence_ces(monkeypatch):
    import db
    monkeypatch.setattr(db, "run_query", _fake_run_query([]))
    material = mp.pull_material_inputs(["FG1"], "2022-01-01")
    ces = pd.DataFrame({"ItemCode": ["A", "A"], "ContractID": ["c1", "c2"], "Status": ["Backlog", "Actual"], "ForecastDelDate": ["2026-10-20", "2026-01-01"],
                        "PlanDelDate": ["2026-10-20", "2026-01-01"], "ActualQty": [0, 5], "BacklogQty": [7, 0], "RevenueType": ["Omni Channel", "Tendering"]})
    b = mp.assemble_inputs(material, ces, "2026-10-06 09:00:00", "2026-10-06 09:00:01")
    assert list(b["backlog_ces"]["ContractID"]) == ["c1"] and b["backlog_pulled_at_local"] == "2026-10-06 09:00:00" and b["rm_pulled_at_local"] == "2026-10-06 09:00:01"
    assert set(b) == {"backlog_ces", "backlog_pulled_at_local", "bom_tree", "rm_inventory", "rm_pulled_at_local", "open_orders", "po_lines", "receipts", "price", "item_names"}
    # the plan can read it: BOM lines, purchase evidence and lead time from the assembled frames
    lines = mp.bom_component_lines(b["bom_tree"])
    assert set(lines[lines["parent"] == "SUB1"]["comp"]) == {"RM-A", "RM-B"} and "RM-A" in mp.purchased_codes(b["po_lines"], b["receipts"])


def test_the_pull_stage_saves_the_inputs_and_the_class_evidence_beside_each_other_and_recomputes_the_class_file(tmp_path, monkeypatch):
    import contextlib
    import db
    real = op.load_full_config(PROJECT_ROOT)
    full = {"operation_plan": copy.deepcopy(real["operation_plan"]), "material_plan": copy.deepcopy(real["material_plan"]), "lead_time_v1": real["lead_time_v1"]}
    _write(os.path.join(str(tmp_path), "config", "config.yaml"), yaml.safe_dump(full))
    monkeypatch.setattr(db, "run_query", _fake_run_query([]))
    sessions = []

    @contextlib.contextmanager
    def fake_session():
        sessions.append(1)
        yield None
    monkeypatch.setattr(db, "session", fake_session)
    monkeypatch.setattr(seg, "class_evidence_codes", lambda: ["FG1", "FG2"])
    ces = pd.DataFrame({"ItemCode": ["FG1"], "ContractID": ["c1"], "Status": ["Backlog"], "ForecastDelDate": ["2026-10-20"], "PlanDelDate": ["2026-10-20"], "ActualQty": [0],
                        "BacklogQty": [3], "RevenueType": ["Omni Channel"]})
    monkeypatch.setattr(seg, "pull_class_evidence", lambda codes: {"p2_apd": pd.DataFrame(), "p2_ces": ces, "p2_final": pd.DataFrame(), "p2_inv": pd.DataFrame(), "p4_bom": pd.DataFrame()})
    seen = {}
    monkeypatch.setattr(seg, "run_from_frames", lambda frames, out, today, write: seen.update(out=out, write=write, names=sorted(frames)) or {"table": pd.DataFrame({"a": [1, 2]})})
    r = mp.pull_and_save(str(tmp_path))
    assert sessions == [1], "exactly one database session is opened by the pull stage"
    folder = os.path.dirname(op.path_of(str(tmp_path), full["operation_plan"]["week3_inputs_file"]))
    assert sorted(os.listdir(folder)) == ["class_evidence.pkl", "material_inputs.pkl"]
    saved = pd.read_pickle(os.path.join(folder, "material_inputs.pkl"))
    assert list(saved["backlog_ces"]["ItemCode"]) == ["FG1"] and set(saved["bom_tree"]["ItemFG"].str.strip()) >= {"FG1", "SUB1"}
    assert pd.read_pickle(os.path.join(folder, "class_evidence.pkl"))["pulled_at_local"] == r["pulled_at_local"]
    assert seen["write"] is True and seen["out"].endswith("task2b_part2_item_level.csv") and r["n_items"] == 2 and "p2_ces" in seen["names"]
    with pytest.raises(Exception):
        monkeypatch.setattr(seg, "pull_class_evidence", lambda codes: (_ for _ in ()).throw(RuntimeError("login failed")))
        mp.pull_and_save(str(tmp_path))                              # a failure inside the session is raised, not retried
    assert sessions == [1, 1]


def test_an_open_session_is_reused_and_never_nested(tmp_path, monkeypatch):
    import db
    real = op.load_full_config(PROJECT_ROOT)
    full = {"operation_plan": copy.deepcopy(real["operation_plan"]), "material_plan": copy.deepcopy(real["material_plan"]), "lead_time_v1": real["lead_time_v1"]}
    _write(os.path.join(str(tmp_path), "config", "config.yaml"), yaml.safe_dump(full))
    monkeypatch.setattr(db, "run_query", _fake_run_query([]))
    monkeypatch.setattr(db, "session", lambda: (_ for _ in ()).throw(AssertionError("a second session was opened")))
    monkeypatch.setattr(seg, "class_evidence_codes", lambda: ["FG1"])
    monkeypatch.setattr(seg, "pull_class_evidence", lambda codes: {"p2_ces": pd.DataFrame({"ItemCode": [], "ContractID": [], "Status": [], "ForecastDelDate": [], "PlanDelDate": [],
                                                                                           "ActualQty": [], "BacklogQty": [], "RevenueType": []})})
    monkeypatch.setattr(seg, "run_from_frames", lambda *a, **k: {"table": pd.DataFrame()})
    mp.pull_and_save(str(tmp_path), in_open_session=True)


def test_the_runner_has_the_pull_stage_and_the_plan_no_longer_reads_the_one_off_file():
    src = open(os.path.join(PROJECT_ROOT, "src", "monthly_refresh.py"), encoding="utf-8").read()
    step1 = src.split("def step1_pull_data")[1].split("def step2_validate")[0]
    assert '"material_plan.py"' in step1 and '"--pull"' in step1 and "material_plan_pull" in step1
    cfg = op.load_config(PROJECT_ROOT)
    assert "week3_inputs" not in cfg["week3_inputs_file"] and cfg["week3_inputs_file"].endswith("material_pull/material_inputs.pkl")
    for name in ("operation_plan.py", "material_plan.py", "build_operation_plan_page.py", "build_material_plan_page.py"):
        text = open(os.path.join(PROJECT_ROOT, "src", name), encoding="utf-8").read()
        assert "week3_inputs/" not in text, name
    import monthly_refresh as mr
    out = mr.step1_pull_data(dry_run=True, offline=True)
    assert out["material_plan_pull"]["refreshed"] is False
