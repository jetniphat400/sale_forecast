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
