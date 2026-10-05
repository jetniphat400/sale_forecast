"""Week 1 items 1.3 and 1.4: the lead-time walk and source order on fixture BOMs, and the recorded outputs' hashes. Temporary folders only."""
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "investigations"))
import lead_time_v1 as lt
import week1_recalibration as wr

CFG = {"fallback_material_days": 63, "production_days_assumed": 26, "production_min_jobs": 3}


def bom(rows):
    return pd.DataFrame(rows, columns=["ItemFG", "ItemRawmat", "Sequenceno", "Type"])


BOM = bom([
    ("A-F-1", "", "0", "Standard"),                    # header row of A-F-1
    ("A-F-1", "M-R-1", "1", "Standard"),               # observed
    ("A-F-1", "M-R-2", "2", "Standard"),               # quoted only
    ("A-F-1", "M-R-3", "3", "Standard"),               # quoted 0 Days only: not usable, so assumed
    ("A-F-1", "B101-DL1", "4", "Machine Hour"),        # pseudo-code
    ("B-F-2", "A-W-9", "1", "Standard"),               # only an in-house sub-assembly
    ("C-F-3", "M-R-1", "1", "Standard"),
    ("C-F-3", "A-W-9", "2", "Standard"),
])
PO = pd.DataFrame({"po_no": ["P1", "P1", "P2", "P3"], "item_code": ["M-R-1", "M-R-1", "M-R-1", "M-R-9"],
                   "po_date": ["2026-01-01", "2026-01-01", "2026-02-01", "2026-01-01"]})
RCV = pd.DataFrame({"PO": ["P1", "P2", "P3"], "Itemcode": ["M-R-1", "M-R-1", "M-R-9"],
                    "Receive_date": ["2026-01-21", "2026-03-23", "2028-06-01"]})   # 20 days, 50 days, and an unusable one (> 730 days)
PL = pd.DataFrame({"ItemCode": ["M-R-1", "M-R-2", "M-R-2", "M-R-3"], "DeliveryTime": ["99 Days", "30 Days", "50 Days", "0 Days"]})
PROD = pd.DataFrame({"item": ["C-F-3", "B-F-2", "A-F-1"], "production_n_jobs": [4, 9, 2], "production_median_days": [10.0, 5.0, 8.0]})


def compute(items):
    obs = lt.observed_lead_times(PO, RCV)
    return lt.compute_item_lead_times(items, BOM, obs, PL, PROD, CFG).set_index("item")


def test_the_walk_excludes_the_header_row_and_the_machine_hour_pseudo_code():
    assert lt.walk_bom(BOM, "A-F-1") == ["M-R-1", "M-R-2", "M-R-3"]
    assert lt.walk_bom(BOM, "NO-BOM") == []


def test_observed_lead_time_is_one_per_po_item_and_drops_unusable_values():
    obs = lt.observed_lead_times(PO, RCV)
    assert sorted(obs[obs["item"] == "M-R-1"]["lead_days"]) == [20, 50]      # the repeated P1 line counts once
    assert "M-R-9" not in set(obs["item"])


def test_source_order_is_observed_then_supplier_quoted_then_assumed_and_zero_days_is_not_a_quote():
    quoted = lt.quoted_days_by_material(PL)
    assert "M-R-3" not in quoted and quoted["M-R-2"] == 40.0
    obs = {"M-R-1": 35.0}
    assert lt.material_lead_time("M-R-1", obs, quoted, 63) == (35.0, "observed")       # observed wins over the 99 Days quote
    assert lt.material_lead_time("M-R-2", obs, quoted, 63) == (40.0, "supplier_quoted")
    assert lt.material_lead_time("M-R-3", obs, quoted, 63) == (63.0, "assumed")


def test_item_lead_time_is_the_slowest_material_plus_production_time_with_its_sources():
    r = compute(["A-F-1"]).loc["A-F-1"]
    # materials: M-R-1 observed 35, M-R-2 quoted 40, M-R-3 assumed 63 -> bottleneck M-R-3; production: 2 jobs < 3 -> assumed 26
    assert (r["bottleneck_material"], r["bottleneck_days"], r["bottleneck_source"]) == ("M-R-3", 63.0, "assumed")
    assert (r["production_days"], r["production_source"]) == (26.0, "assumed")
    assert r["lead_time_days"] == 89.0 and (r["n_observed"], r["n_quoted"], r["n_assumed"]) == (1, 1, 1)


def test_an_item_with_enough_measured_jobs_uses_its_own_median_production_time():
    r = compute(["C-F-3"]).loc["C-F-3"]
    assert (r["production_days"], r["production_source"], r["production_n_jobs"]) == (10.0, "measured", 4)
    # the in-house sub-assembly is listed and left out of the maximum; M-R-1 (observed 35) is the bottleneck
    assert (r["bottleneck_material"], r["bottleneck_source"], r["inhouse_not_walked"]) == ("M-R-1", "observed", 1)
    assert r["lead_time_days"] == 45.0


def test_an_item_with_no_bom_or_only_in_house_parts_gets_the_assumed_values_labelled():
    t = compute(["NO-BOM", "B-F-2"])
    for item in ("NO-BOM", "B-F-2"):
        r = t.loc[item]
        assert bool(r["no_bom"]) and r["bottleneck_source"] == "assumed" and r["production_source"] == "assumed"
        assert r["lead_time_days"] == 63 + 26 and "assumed" in r["note"]
    # 9 matched jobs for B-F-2 are not used: its materials are not walked
    assert t.loc["B-F-2", "production_days"] == 26.0


def test_measured_production_days_counts_unique_jobs_from_start_to_the_latest_final_date():
    po = pd.DataFrame({"itemcode": ["X", "X", "X", "X"], "job": ["J1", "J1", "J2", "J3"], "start_date": ["2026-01-01"] * 4})
    cf = pd.DataFrame({"itemcode": ["X", "X", "X"], "jobno": ["J1", "J1", "J2"], "final_date": ["2026-01-11", "2026-01-21", "2026-01-06"]})
    m = lt.measured_production_days(po, cf).set_index("item")
    assert m.loc["X", "production_n_jobs"] == 2 and m.loc["X", "production_median_days"] == 12.5     # J1 20 days (latest final), J2 5; J3 has no final


def test_the_config_holds_the_three_assumption_values():
    cfg = lt.load_config()
    assert set(cfg) == {"fallback_material_days", "production_days_assumed", "production_min_jobs"}


def test_the_recorded_lead_time_output_hash_is_written_read_back_and_verified(tmp_path):
    out, meta = str(tmp_path / "lt.csv"), str(tmp_path / "lt.json")
    df = compute(["A-F-1", "C-F-3"]).reset_index()
    info = lt.write_recorded(df, out, meta)
    assert lt.verify_recorded(out, meta) is True and len(info["sha256"]) == 64
    with open(out, "a", encoding="utf-8") as f:
        f.write("tamper\n")
    with pytest.raises(ValueError, match="hashes to"):
        lt.verify_recorded(out, meta)


# ---------------------------------------------------------------- recalibration pieces
def test_observed_not_late_is_unit_weighted_on_the_forecast_date_window():
    ces = pd.DataFrame({"ItemCode": ["A", "A", "A", "B"], "Status": ["Actual"] * 4, "ActualQty": [10, 30, 60, 5],
                        "ForecastDelDate": ["2026-02-01", "2026-02-10", "2025-12-31", "2026-02-01"],
                        "ActualDelDate": ["2026-02-01", "2026-02-12", "2026-01-01", "2026-02-01"]})
    r = wr.observed_not_late(ces, ["A"], "2026-01-01", "2026-12-31")
    assert r["units"] == 40 and r["not_late"] == pytest.approx(10 / 40)         # the 2025 row is outside the window; the late 30 counts as late


def test_distinct_members_are_deduplicated_on_what_affects_min():
    base = {"calib_notlate_diff_pp": 0.0, "valid_notlate_diff_pp": 0.0}
    rows = []
    for d in wr.STOCKDEFS:
        rows.append({**base, "r_months": 1.0, "s_months": 2.0, "review_interval_days": 7, "lead_time_days": "per_item",
                     **{f"calib_stockval_pctdiff_{x}": 0.0 for x in wr.STOCKDEFS}, **{f"valid_stockval_pctdiff_{x}": 0.0 for x in wr.STOCKDEFS}})
    members, counts = wr.distinct_members(pd.DataFrame(rows), wr.DEDUP_COLS)
    assert counts == [3, 3, 3] and len(members) == 1


def test_recalibration_outputs_are_hashed_and_a_changed_file_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(wr, "SUMMARY_DIR", str(tmp_path)); monkeypatch.setattr(wr, "INTEGRITY_PATH", str(tmp_path / "week1_recal_integrity.json"))
    p = tmp_path / "week1_recal_members.csv"; p.write_text("r_months\n1\n", encoding="utf-8")
    wr.record([str(p)])
    assert wr.verify_recorded() is True
    p.write_text("r_months\n2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not hash"):
        wr.verify_recorded()
