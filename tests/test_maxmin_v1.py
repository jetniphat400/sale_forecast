"""Max-Min v1 for PEM101 (week 1; src/maxmin_v1.py): the ensemble output's hash, the builder pointing at it, every braced value against its
source, and the assumptions file's schema and values. No database. Tests write only to pytest's temporary folders, never to a tracked file.

The recorded outputs under output/ are git-ignored, so a machine without them SKIPS these tests with a message (never passes silently).
"""
import copy
import hashlib
import json
import os
import shutil

import pandas as pd
import pytest
import yaml

import maxmin_v1 as mm

PROJECT_ROOT = mm.PROJECT_ROOT
CFG = mm.load_config()
FULL = mm.load_full_config()


def _need(*rels):
    missing = [r for r in rels if not os.path.exists(mm.path_of(r))]
    if missing:
        pytest.skip("SKIPPED, not passed: recorded output missing on this machine: " + ", ".join(missing))


@pytest.fixture(scope="module")
def recorded():
    _need(CFG["ensemble_members_file"], CFG["ensemble_integrity_file"], CFG["dense_grid_file"], CFG["recorded_outputs_integrity_file"],
          CFG["item_lead_time_file"], CFG["item_lead_time_integrity_file"])
    return True


def _sha(rel):
    return hashlib.sha256(open(mm.path_of(rel), "rb").read()).hexdigest()


# ------------------------------------------------------------------ the ensemble output's hash
def test_the_control_runs_files_hash_to_their_recorded_values(recorded):
    meta = json.load(open(mm.path_of(CFG["ensemble_integrity_file"]), encoding="utf-8"))
    for key in ("ensemble_members_file", "ensemble_tradeoff_points_file", "ensemble_tradeoff_envelope_file", "ensemble_targets_file"):
        name = os.path.basename(CFG[key])
        assert meta["files"][name]["sha256"] == _sha(CFG[key]), name
    mm.verify_ensemble_files(CFG)


def test_the_page_inputs_hash_to_their_recorded_values(recorded):
    meta = json.load(open(mm.path_of(CFG["recorded_outputs_integrity_file"]), encoding="utf-8"))
    for key in ("dense_grid_file", "ratio_grid_file"):
        assert meta["files"][os.path.basename(CFG[key])]["sha256"] == _sha(CFG[key])
    dense, ratio = mm.load_page_inputs(CFG)
    assert dense["n_distinct_members"] == 36 or dense["n_distinct_members"] == len(pd.read_csv(mm.path_of(CFG["ensemble_members_file"])))
    assert ratio["today_not_late_pct"] == dense["today_point"]["not_late_pct"]


def test_a_changed_file_is_refused(recorded, tmp_path):
    """Copies the integrity file and one listed file to a temporary folder, changes one byte, and the check raises."""
    folder = tmp_path / "summary"
    folder.mkdir()
    name = os.path.basename(CFG["ensemble_members_file"])
    shutil.copy(mm.path_of(CFG["ensemble_members_file"]), folder / name)
    shutil.copy(mm.path_of(CFG["ensemble_integrity_file"]), folder / "integrity.json")
    mm.verify_files(str(folder / "integrity.json"), only=[name])
    with open(folder / name, "ab") as f:
        f.write(b"\n")
    with pytest.raises(mm.MaxMinV1Error, match="does not hash"):
        mm.verify_files(str(folder / "integrity.json"), only=[name])
    with pytest.raises(mm.MaxMinV1Error, match="not listed"):
        mm.verify_files(str(folder / "integrity.json"), only=["no_such_file.csv"])


# ------------------------------------------------------------------ the builder points at it
def test_the_inventory_builder_reads_the_ensemble_output_not_the_76_item_set(recorded):
    import build_inventory_page_data as bd
    ct = bd._build_curve_target_pem101()
    dense, ratio = mm.load_page_inputs(CFG)
    members = pd.read_csv(mm.path_of(CFG["ensemble_members_file"]))
    assert ct["n_distinct_members"] == len(members) == dense["n_distinct_members"]
    assert ct["items_order"] == dense["items_order"] and len(ct["items_order"]) == dense["n_items_calibrated"] == 92
    assert ct["grid"] == dense["grid"] and ct["relative_service_cost"] == ratio
    assert ct["today_point"]["not_late_pct"] == dense["today_point"]["not_late_pct"]
    assert "ปรับให้ตรงกับผลจริงจากสินค้า 92 รายการ" in ct["item_set_note"] and "76" not in ct["item_set_note"]
    assert bd.model_calibrated_at()["run_date"] == dense["calibrated_on"]
    cfg_text = open(os.path.join(PROJECT_ROOT, "src", "build_inventory_page_data.py"), encoding="utf-8").read()
    assert "phase23_dense_grid_PEM101" not in cfg_text.split("def _build_curve_target_pem101")[1].split("def _build_pem101_division")[0]


def test_the_note_keeps_the_earlier_clause_only_when_the_sets_differ(recorded, monkeypatch):
    import build_inventory_page_data as bd
    real = bd._load_fulfilment_segmentation

    def with_extra_stock_item(division):
        df = real(division).copy()
        if division == "PEM101":
            df.loc[df.index[df["class"] == "conflict"][0], "class"] = "stock_policy"
        return df
    monkeypatch.setattr(bd, "_load_fulfilment_segmentation", with_extra_stock_item)
    note = bd._build_curve_target_pem101()["item_set_note"]
    assert "93 รายการ" in note and "ยังไม่ได้ปรับใหม่ตามชุดนี้" in note and "ปรับให้ตรงกับผลจริงจากสินค้า 92 รายการ" in note


# ------------------------------------------------------------------ every braced value against its source
def test_the_lead_range_and_distinct_members_equal_the_members_file(recorded):
    members = pd.read_csv(mm.path_of(CFG["ensemble_members_file"]))
    s = mm.ensemble_summary(CFG)
    assert s["n_members"] == len(members) and len(members.drop_duplicates(["r_months", "s_months", "review_interval_days", "lead_time_days"])) == len(members)
    assert (s["lead_min"], s["lead_max"]) == (int(members["lead_time_days"].min()), int(members["lead_time_days"].max()))
    ct = mm.load_page_inputs(CFG)[0]
    assert ct["lead_time_days"] == {"min": s["lead_min"], "max": s["lead_max"], "median": s["lead_median"]}


def test_the_ensemble_reproduces_the_last_tasks_figures(recorded):
    """The week 1 calibration report's figures (output/summary/week1_leadtime_calibration.md): recomputed here from the recorded files."""
    s = mm.ensemble_summary(CFG)
    assert s["n_members"] == 36 and (s["lead_min"], s["lead_max"]) == (1, 30)
    assert round(s["simulated_today"]["not_late_pct"], 2) == 96.95 and round(s["simulated_today"]["stock_value_thb"] / 1e6, 2) == 14.77
    assert s["observed"]["not_late_pct"] == 98.34 and round(s["observed"]["stock_value_thb"] / 1e6, 2) == 15.49
    t = s["tradeoff_to_99"]
    assert round(t["median_pct"], 1) == 35.7 and round(t["min_pct"], 1) == 26.2 and round(t["max_pct"], 1) == 81.8
    assert round(t["stock_at_98_median"] / 1e6, 2) == 15.64 and round(t["stock_at_99_median"] / 1e6, 2) == 21.23


def test_the_dense_grid_follows_the_members_trade_off_points(recorded):
    dense, _ = mm.load_page_inputs(CFG)
    pts = pd.read_csv(mm.path_of(CFG["ensemble_tradeoff_points_file"])).dropna(subset=["not_late", "stock_value"])
    for g in dense["grid"]:
        sub = pts[pts["swept_r_months"] == g["r"]]
        assert g["n_members"] == len(sub)
        assert g["stock_value_median"] == pytest.approx(sub["stock_value"].median(), abs=0.01)
        assert g["stock_value_min"] == pytest.approx(sub["stock_value"].min(), abs=0.01)
        assert g["stock_value_max"] == pytest.approx(sub["stock_value"].max(), abs=0.01)
        assert g["not_late_median_pct"] == pytest.approx(100 * sub["not_late"].median(), abs=0.001)
        mins = [it["Min"] for it in g["items"]]
        assert len(mins) == 92 and all(m >= 0 for m in mins)
    # Min is linear in r for every item (Min = r x 30.44 x mean daily demand)
    by_r = {g["r"]: g for g in dense["grid"]}
    a, b = by_r[1.0], by_r[2.0]
    for ia, ib in zip(a["items"], b["items"]):
        assert ib["Min"] == pytest.approx(2 * ia["Min"], abs=0.02)


def _lead_csv():
    return pd.read_csv(mm.path_of(CFG["item_lead_time_file"]))


def test_the_material_lead_median_and_source_labels_equal_the_per_item_file(recorded):
    d = _lead_csv()
    page = mm.material_lead_for_page(list(d["item"]), CFG)
    assert page["median_days"] == float(d["bottleneck_days"].median())
    obs = d[d["bottleneck_source"] == "observed"]
    assert page["median_observed_days"] == float(obs["bottleneck_days"].median()) and page["n_observed"] == len(obs) and page["n_items_shown"] == len(d)
    labels = CFG["material_source_labels"]
    for _, r in d.iterrows():
        assert page["per_item"][r["item"]] == {"days": float(r["bottleneck_days"]), "source": labels[r["bottleneck_source"]]}
        if bool(r["no_bom"]):
            assert page["per_item"][r["item"]]["source"] == labels["assumed"]
    assert sum(page["label_counts"].values()) == len(d) == 92
    assert page["label_counts"].get(labels["observed"], 0) == int((d["bottleneck_source"] == "observed").sum())


def test_the_per_item_lead_time_file_is_hash_checked(recorded, tmp_path):
    bad = tmp_path / "lead.csv"
    shutil.copy(mm.path_of(CFG["item_lead_time_file"]), bad)
    with open(bad, "ab") as f:
        f.write(b"x")
    cfg = copy.deepcopy(CFG)
    cfg["item_lead_time_file"] = str(bad)      # an absolute path is used as it is by os.path.join
    with pytest.raises(mm.MaxMinV1Error, match="does not hash"):
        mm.material_lead_table(cfg)


def test_each_assumption_value_equals_its_source(recorded):
    v = mm.assumption_values(CFG)
    members = pd.read_csv(mm.path_of(CFG["ensemble_members_file"]))
    d = _lead_csv()
    assumed = d[d["production_source"] == "assumed"]
    assert (v["lead_min"], v["lead_max"]) == (int(members["lead_time_days"].min()), int(members["lead_time_days"].max()))
    assert v["n_assumed_production"] == len(assumed) and v["assumed_production_days"] == str(int(assumed["production_days"].iloc[0]))
    assert set(assumed["production_days"]) == {FULL["lead_time_v1"]["production_days_assumed"]}
    assert v["sellable_warehouses"] == ", ".join(FULL["phase_e1_assumptions"]["sellable_warehouse_codes"]["PEM101"])
    items = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "summary", "task2b_part2_item_level.csv"))
    import build_inventory_page_data as bd
    after = bd.apply_class_decisions(items, FULL.get("fulfilment_class_decisions", {}))
    assert v["n_undetermined"] == int(((after["division"] == "PEM101") & (after["class"] == "conflict")).sum())


def test_the_warehouse_list_follows_the_config_the_page_uses(recorded, monkeypatch):
    full = copy.deepcopy(FULL)
    full["phase_e1_assumptions"]["sellable_warehouse_codes"]["PEM101"] = ["AA01", "BB02"]
    monkeypatch.setattr(mm, "load_full_config", lambda: full)
    rec = {r["id"]: r for r in mm.build_assumptions(CFG, today="2030-01-02")["assumptions"]}
    assert rec["sellable_warehouses"]["used_now"] == "AA01, BB02"


# ------------------------------------------------------------------ the assumptions file
TRACKED_ASSUMPTIONS = os.path.join(PROJECT_ROOT, "data", "assumptions.json")


def test_the_assumptions_file_has_the_contract_schema():
    payload = json.load(open(TRACKED_ASSUMPTIONS, encoding="utf-8"))
    assert set(payload) == {"schema_version", "assumptions"} and payload["schema_version"] == mm.ASSUMPTIONS_SCHEMA_VERSION
    rows = payload["assumptions"]
    assert len(rows) == 10 and len({r["id"] for r in rows}) == 10
    for r in rows:
        assert list(r) == mm.ASSUMPTIONS_FIELDS
        assert all(isinstance(r[k], str) and r[k].strip() for k in r)
        assert "{" not in "".join(r.values()) and "}" not in "".join(r.values()), "a braced value was left unfilled"
        pd.Timestamp(r["updated_date"])


def test_the_assumptions_file_holds_the_approved_texts_and_the_computed_values(recorded):
    rows = {r["id"]: r for r in json.load(open(TRACKED_ASSUMPTIONS, encoding="utf-8"))["assumptions"]}
    v = mm.assumption_values(CFG)
    expected = {
        "minmax_lead_time": ("lead time ที่ใช้คำนวณ Min/Max", "ได้จากการจำลองให้ตรงผลจริง ไม่ได้วัดตรง", f"{v['lead_min']}-{v['lead_max']} วัน", "Min/Max ของ PEM101"),
        "production_time": ("เวลาผลิตสินค้า", "ระบบไม่บันทึกวันเริ่มผลิตจริง", f"{v['assumed_production_days']} วัน ({v['n_assumed_production']} รายการ)", "แผนสั่งวัตถุดิบ"),
        "material_without_purchase_history": ("วัตถุดิบที่ไม่มีประวัติสั่งซื้อ", "ไม่มีใบสั่งซื้อในระบบ", "เวลาที่ผู้ขายแจ้ง หรือค่าสูงของวัตถุดิบอื่น", "แผนสั่งวัตถุดิบ"),
        "sellable_warehouses": ("คลังที่นับว่าขายได้", "ประวัติการเคลื่อนไหวของคลังไม่พอ", v["sellable_warehouses"], "stock ที่ใช้เทียบกับ Min"),
        "pem101_undetermined_items": (f"สินค้า PEM101 {v['n_undetermined']} รหัส", "ยังไม่ชัดว่าเก็บ stock หรือผลิตตามสั่ง", "ไม่มี Min/Max", "Min/Max"),
        "production_capacity": ("กำลังผลิต", "ข้อมูลบอกได้แค่ยอดผลิตสูงสุดที่เคยทำ", "ใช้ยอดนั้นเป็นค่าต่ำสุด", "แผนการผลิต"),
        "open_production_orders": ("ใบสั่งผลิตที่กำลังทำ", "วันกำหนดเสร็จในระบบไม่ตรงกับวันเสร็จจริง", "ไม่นับในแผน", "แผนการผลิต"),
        "fmto_fmts_warehouses": ("คลัง FMTO และ FMTS", "ยังไม่รู้ว่าเป็นของพร้อมขายไหม", "ไม่นับ", "stock ที่ใช้เทียบกับ Min และแผนการผลิต"),
        "forecast_range": ("ยอดทาย", "ยังไม่มีช่วงสูง-ต่ำ", "ใช้ค่ากลาง", "แผนการผลิต"),
        "calibration_window": ("ช่วงข้อมูลที่ใช้ปรับ Min/Max", "ถ้าใช้ช่วงสั้นลง lead time ที่ได้จะแคบลง", v["calibration_window"], "Min/Max ของ PEM101"),
    }
    assert set(rows) == set(expected)
    for rid, (topic, unknown, used, affects) in expected.items():
        r = rows[rid]
        assert (r["topic"], r["unknown"], r["used_now"], r["affects"]) == (topic, unknown, used, affects), rid
    assert list(rows) == list(expected), "the records are in the approved order"


def test_the_assumptions_file_is_what_the_builder_writes_today(recorded, tmp_path):
    tracked = json.load(open(TRACKED_ASSUMPTIONS, encoding="utf-8"))
    out = mm.write_assumptions(str(tmp_path / "data" / "assumptions.json"), CFG, today=tracked["assumptions"][0]["updated_date"])
    assert json.load(open(out, encoding="utf-8")) == tracked


def test_a_perturbed_source_changes_the_written_values(recorded, monkeypatch, tmp_path):
    full = copy.deepcopy(FULL)
    full["phase_e1_assumptions"]["sellable_warehouse_codes"]["PEM101"] = ["ZZ99"]
    monkeypatch.setattr(mm, "load_full_config", lambda: full)
    monkeypatch.setattr(mm, "ensemble_summary", lambda cfg=None: {"lead_min": 7, "lead_max": 77})
    rows = {r["id"]: r for r in mm.build_assumptions(CFG, today="2031-03-04")["assumptions"]}
    assert rows["minmax_lead_time"]["used_now"] == "7-77 วัน" and rows["sellable_warehouses"]["used_now"] == "ZZ99"
    assert all(r["updated_date"] == "2031-03-04" for r in rows.values())


def test_the_monthly_runner_writes_the_file_and_lists_it_as_generated():
    import monthly_refresh as mr
    assert "data/assumptions.json" in mr.GENERATED_PATHS
    src = open(os.path.join(PROJECT_ROOT, "src", "monthly_refresh.py"), encoding="utf-8").read()
    assert "maxmin_v1.write_assumptions" in src.split("def step7_rebuild_pages")[1].split("def step8_run_tests")[0]
