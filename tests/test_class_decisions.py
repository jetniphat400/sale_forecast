"""E1 and E3 (decided by the user, 2026-10-05): PEM107's 41 G3 made-to-order codes and PEM101's 21 per-item class overrides.
Config `fulfilment_class_decisions` is applied on top of METRICS.md Sec.23 in src/build_inventory_page_data.apply_class_decisions;
the section 23 rule is not changed. Reads saved files only: no database, no tracked file written."""
import os
import re
import sys

import pandas as pd
import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
import build_inventory_page_data as bd

LEAN_REPORT = os.path.join(PROJECT_ROOT, "output", "summary", "phaseA_pem101_conflict_lean.md")
G3_REPORT = os.path.join(PROJECT_ROOT, "output", "summary", "phaseA_pem107_g3_verification.md")
ITEM_LEVEL = os.path.join(PROJECT_ROOT, "output", "summary", "task2b_part2_item_level.csv")


def decisions():
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["fulfilment_class_decisions"]


def lean_from_report() -> dict:
    """{code: lean} read from the per-item table of phaseA_pem101_conflict_lean.md (column 'Class')."""
    text = open(LEAN_REPORT, encoding="utf-8").read()
    table = text.split("## Full per-item table")[1].split("## Undetermined")[0]
    out = {}
    for line in table.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 14 and re.match(r"^[A-Z]", cells[1]) and cells[1] != "Code":
            out[cells[1]] = cells[11]
    return out


def g3_from_report() -> list:
    text = open(G3_REPORT, encoding="utf-8").read()
    block = text.split("Recommended subset")[1].split("The other 37")[0]
    return re.findall(r"[A-Z]{2}-F-99-\d+", block)


@pytest.fixture(scope="module")
def raw_items():
    for p in (LEAN_REPORT, G3_REPORT, ITEM_LEVEL):
        if not os.path.exists(p):
            pytest.skip(f"SKIPPED, not passed: {os.path.relpath(p, PROJECT_ROOT)} is not in this checkout")
    df = pd.read_csv(ITEM_LEVEL)
    return df[df["status_category"] == "forecast"] if "status_category" in df.columns else df   # the file also holds placeholders and other divisions (week 3)


# ------------------------------------------------------------------ E1
def test_the_g3_list_in_config_is_the_41_codes_of_the_verification_and_each_is_already_confirmed_to_order(raw_items):
    listed = decisions()["g3_made_to_order"]["PEM107"]
    assert sorted(listed) == sorted(g3_from_report()) and len(listed) == 41 == len(set(listed))
    have = raw_items[(raw_items["division"] == "PEM107") & raw_items["code"].isin(listed)]
    assert len(have) == 41 and set(have["class"]) == {"confirmed_to_order"}


def test_applying_the_decisions_changes_no_pem107_class(raw_items):
    out = bd.apply_class_decisions(raw_items, decisions())
    a = raw_items[raw_items["division"] == "PEM107"].set_index("code")["class"]
    b = out[out["division"] == "PEM107"].set_index("code")["class"]
    assert a.equals(b)


def test_a_g3_code_that_is_not_confirmed_to_order_stops_the_build(raw_items):
    stock_code = raw_items[(raw_items["division"] == "PEM107") & (raw_items["class"] == "stock_policy")]["code"].iloc[0]
    with pytest.raises(ValueError, match="not classed confirmed_to_order"):
        bd.apply_class_decisions(raw_items, {"g3_made_to_order": {"PEM107": [stock_code]}})


# ------------------------------------------------------------------ E3
def test_the_21_overrides_match_the_lean_report_and_the_20_undetermined_stay_as_they_are(raw_items):
    lean = lean_from_report()
    assert len(lean) == 41
    out = bd.apply_class_decisions(raw_items, decisions()).set_index("code")
    before = raw_items.set_index("code")
    for code, verdict in lean.items():
        if verdict == "leaning stock":
            assert out.loc[code, "class"] == "stock_policy" and out.loc[code, "class_basis"] == bd.CLASS_BASIS_DECIDED, code
        elif verdict == "leaning made-to-order":
            assert out.loc[code, "class"] == "confirmed_to_order" and out.loc[code, "class_basis"] == bd.CLASS_BASIS_DECIDED, code
        else:
            assert verdict == "undetermined"
            assert out.loc[code, "class"] == before.loc[code, "class"] == "conflict" and out.loc[code, "class_basis"] == "", code
    assert sum(v == "leaning stock" for v in lean.values()) == 10 and sum(v == "leaning made-to-order" for v in lean.values()) == 11


def test_no_other_item_changes_class_and_the_counts_move_as_stated(raw_items):
    lean = lean_from_report()
    out = bd.apply_class_decisions(raw_items, decisions())
    changed = out.loc[out["class"].values != raw_items["class"].values, "code"]
    assert sorted(changed) == sorted(c for c, v in lean.items() if v != "undetermined")
    p = out[out["division"] == "PEM101"]["class"].value_counts().to_dict()
    q = raw_items[raw_items["division"] == "PEM101"]["class"].value_counts().to_dict()
    assert (q["stock_policy"], q["confirmed_to_order"], q["conflict"]) == (82, 21, 41)
    assert (p["stock_policy"], p["confirmed_to_order"], p["conflict"]) == (92, 32, 20)


def test_an_override_for_an_item_that_is_not_in_the_conflict_class_is_refused(raw_items):
    stock_code = raw_items[(raw_items["division"] == "PEM101") & (raw_items["class"] == "stock_policy")]["code"].iloc[0]
    with pytest.raises(ValueError, match="not in the conflict class"):
        bd.apply_class_decisions(raw_items, {"class_overrides": {"PEM101": {"stock_policy": [stock_code]}}})
    with pytest.raises(ValueError, match="expected exactly one item"):
        bd.apply_class_decisions(raw_items, {"class_overrides": {"PEM101": {"stock_policy": ["NO-SUCH-CODE"]}}})


def test_the_calibrated_target_note_states_the_fitted_count_from_the_ensemble_output():
    """Week 1: the section is fitted on the 92 stock_policy items (the Max-Min v1 ensemble), so the note states that count, from the
    ensemble output, and no longer says it was not refitted; it would say so again if the stock_policy set grew past the fitted set."""
    from page_helpers import fresh_inventory_data
    pem101 = fresh_inventory_data()["divisions"]["PEM101"]
    n_stock = sum(1 for i in pem101["items"] if i["policy"] == "stock_policy")
    ct = pem101["curve_target"]
    assert ct["n_items_calibrated"] == 92 == n_stock
    assert ct["item_set_note"] == f"ปรับให้ตรงกับผลจริงจากสินค้า {ct['n_items_calibrated']} รายการ"
    assert "ยังไม่ได้ปรับใหม่" not in ct["item_set_note"] and "76" not in ct["item_set_note"]


# ------------------------------------------------------------------ manual text (part 4)
LINE_1 = "ค่าที่ตั้งในระบบ คือ Min/Max ที่บันทึกไว้ในระบบคลัง คนสั่งของใช้ดูประกอบการสั่ง แต่ยังไม่ได้ตรวจว่าตั้งไว้เหมาะสมหรือไม่ จึงใช้เป็นตัวเทียบเท่านั้น"
LINE_2 = 'Max ที่แสดงว่า "ไม่ได้กรอก" คือรายการที่ไม่ได้ใส่ค่า Max ไว้ในระบบ'


def test_both_manual_files_carry_the_two_approved_lines_and_not_the_old_note():
    for rel in ("docs/user_manual.md", "config/manual_notes.yaml"):
        text = open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8").read()
        assert LINE_1 in text and LINE_2 in text, rel
        assert "ไม่มีใครใช้จริง" not in text, rel


# ------------------------------------------------------------------ S2 as defined in METRICS.md Sec.23 (week 4): two separately written computations
SEGMENTATION_SRC = os.path.join(PROJECT_ROOT, "src", "investigations")
CLASS_EVIDENCE = os.path.join(PROJECT_ROOT, "output", "data", "material_pull", "class_evidence.pkl")


def s2_by_loops(ces, cf, items, threshold=0.5):
    """The definition of METRICS.md Sec.23 ("S2 defined"), written row by row with plain dicts and loops, not with the module's pandas operations: the batch date of a
    job code is the earliest final_date over the cube_final rows with exactly that jobno; a delivered row (Status 'Actual') is linked when its OLMJobCode is not blank
    and exactly equals a jobno, and served when its batch date is strictly before its CtrDate; share = served / all delivered rows; computable only with a linked row.
    Returns {item: (n_delivered, n_linked, n_served, computable, S2)}."""
    import pandas as pd
    first = {}
    for jobno, fd in zip(cf["jobno"], cf["final_date"]):
        ts = pd.to_datetime(fd, errors="coerce")
        if pd.isna(ts) or jobno is None or (isinstance(jobno, float) and pd.isna(jobno)):
            continue
        if jobno not in first or ts < first[jobno]:
            first[jobno] = ts
    count = {i: [0, 0, 0] for i in items}
    for item, status, code, ctr in zip(ces["ItemCode"], ces["Status"], ces["OLMJobCode"], ces["CtrDate"]):
        if status != "Actual" or item not in count:
            continue
        count[item][0] += 1
        blank = code is None or (isinstance(code, float) and pd.isna(code)) or str(code).strip() == "" or str(code).strip().lower() == "none"
        ctr_ts = pd.to_datetime(ctr, errors="coerce")
        if blank or pd.isna(ctr_ts) or code not in first:
            continue
        count[item][1] += 1
        if first[code] < ctr_ts:
            count[item][2] += 1
    out = {}
    for item, (n, linked, served) in count.items():
        comp = n > 0 and linked > 0
        out[item] = (n, linked, served, comp, (served / n >= threshold) if comp else None)
    return out


def _s2_module(ces, cf, items):
    import sys
    sys.path.insert(0, SEGMENTATION_SRC)
    import task2b_part2_fulfilment_segmentation as seg
    r = seg.compute_s2_s3(ces, cf, items, 0.5, 14).set_index("itemcode")
    return {i: (int(r.loc[i, "n_delivered_contracts"]), int(r.loc[i, "n_cube_final_linked"]), int(r.loc[i, "n_traceable_pre_existing"]),
                bool(r.loc[i, "S2_computable"]), (bool(r.loc[i, "S2"]) if r.loc[i, "S2"] is not None and r.loc[i, "S2"] == r.loc[i, "S2"] else None)) for i in items}


def _s2_fixture():
    import pandas as pd
    rows = [  # item, contract, status, ctr date, plan, job code
        ("A", "c1", "Actual", "2026-03-10", 1, "J1"),            # batch J1 finished 2026-03-01: served
        ("A", "c1", "Actual", "2026-03-10", 2, "J1"),            # a second plan line of the same contract counts as a second row
        ("A", "c2", "Actual", "2026-02-01", 1, "J1"),            # linked but the batch is later than the order: not served
        ("A", "c3", "Actual", "2026-03-01", 1, "J2"),            # J2 finished on the order day at 10:00: not strictly earlier than 00:00
        ("A", "c4", "Actual", "2026-03-10", 1, None),            # no job code: in the denominator only
        ("A", "c5", "Actual", "2026-03-10", 1, "none"),          # the text none is blank
        ("A", "c6", "Actual", "2026-03-10", 1, "J1,J3"),         # a comma list never links
        ("A", "c7", "Actual", "2026-03-10", 1, " J1"),           # no trimming: does not link
        ("A", "c8", "Backlog", "2026-03-10", 1, "J1"),           # not delivered
        ("A", "c9", "Actual", None, 1, "J1"),                    # no CtrDate: never linked
        ("B", "d1", "Actual", "2026-03-10", 1, "J9"),            # no cube_final row: no link at all, S2 not computable
        ("B", "d2", "Actual", "2026-03-10", 1, None),
        ("C", "e1", "Actual", "2026-03-10", 1, "J1"), ("C", "e2", "Actual", "2026-03-10", 1, "J1"), ("C", "e3", "Actual", "2026-03-10", 1, None), ("C", "e4", "Actual", "2026-03-10", 1, None),   # exactly half
        ("D", "f1", "Backlog", "2026-03-10", 1, "J1")]           # nothing delivered
    ces = pd.DataFrame(rows, columns=["ItemCode", "ContractID", "Status", "CtrDate", "PlanID", "OLMJobCode"])
    ces["ActualDelDate"] = "2026-06-01"      # read by the module's S3 part, not by S2
    cf = pd.DataFrame({"jobno": ["J1", "J1", "J2", "J3"], "itemcode": ["X", "Y", "X", "X"],
                       "final_date": ["2026-03-01 08:00:00", "2026-04-01 08:00:00", "2026-03-01 10:00:00", "2027-01-01 00:00:00"]})
    return ces, cf


def test_s2_two_computations_agree_on_a_fixture_that_holds_every_case_of_the_definition():
    ces, cf = _s2_fixture()
    items = ["A", "B", "C", "D"]
    by_module, by_loops = _s2_module(ces, cf, items), s2_by_loops(ces, cf, items)
    assert by_module == by_loops
    # item A: nine delivered rows (c8 is a backlog row); linked: c1 twice, c2 and c3 (c6 is a comma list, c7 has a space, c9 has no CtrDate); served: c1 twice
    # (c2's batch is later than its order, c3's batch was finished on the order day after midnight); 2 of 9 delivered rows is below one half
    assert by_loops["A"] == (9, 4, 2, True, False)
    assert by_loops["B"] == (2, 0, 0, False, None) and by_loops["D"] == (0, 0, 0, False, None)
    assert by_loops["C"] == (4, 2, 2, True, True)                             # exactly half of all delivered rows is enough


def test_s2_two_computations_agree_on_every_item_of_the_saved_class_evidence():
    import pandas as pd
    if not os.path.exists(CLASS_EVIDENCE):
        pytest.skip("SKIPPED, not passed: the saved class evidence is not on this machine (output/data/material_pull/class_evidence.pkl), so only the fixture test ran")
    ev = pd.read_pickle(CLASS_EVIDENCE)
    items = sorted(pd.read_csv(os.path.join(PROJECT_ROOT, "output", "summary", "task2b_part2_item_level.csv"))["code"])
    by_module, by_loops = _s2_module(ev["p2_ces"], ev["p2_final"], items), s2_by_loops(ev["p2_ces"], ev["p2_final"], items)
    differ = [i for i in items if by_module[i] != by_loops[i]]
    assert not differ, f"the two computations of S2 differ on {len(differ)} items, for example {differ[:5]}"
    assert len(items) > 400 and sum(1 for v in by_loops.values() if v[3]) > 100
