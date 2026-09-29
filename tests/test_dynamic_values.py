"""Dynamic values rule (CONVENTIONS.md "Dynamic values"): every number a reader sees is computed
at build time from data, config or a recorded output, never typed.

Each page is built twice, the second time with the source of one value perturbed (the recorded
output file, the config value or the data field the number is read from is altered as it is read;
no file on disk is touched). If a number in reader text renders the same in both builds although
its source differs, it is typed by hand and the test fails. Illustrative examples in the user
manual are outside this test (docs/user_manual.md).

The tests need no database and no browser, except the last one, which renders both inventory pages
in Edge to read the lines that the page's own script fills in (skipped with a message without Edge).
"""
import copy
import json
import os
import re
import sys

import pandas as pd
import pytest
import yaml

from page_helpers import Edge, fresh_inventory_data, require_browser

import reader_values as rv

# ------------------------------------------------------------------ perturbations

STOCK_VALUE_FILE = "phaseE1fix_2_minmax_stockvalue.csv"
NO_MINMAX_FILE = "phaseE1fix_2_current_minmax.csv"
DISAGREE_FILE = "phaseA_a1_task2_plandeldate_disagreement_rows.csv"
ITEM_LEVEL_FILE = "task2b_part2_item_level.csv"
ON_TIME_FILE = "delivery_by_year.csv"
POLICY_FILE = "phaseE1fix_1_item_policy.csv"


def _scale_stock_value(df):
    if "stock_value_contribution" not in df.columns:
        return df
    df = df.copy()
    df["stock_value_contribution"] = df["stock_value_contribution"] * 1.5
    return df


def _more_missing_minmax(df):
    if "has_current_setting" not in df.columns:
        return df
    df = df.copy()
    idx = df.index[df["has_current_setting"].astype(bool)][:5]
    df.loc[idx, "has_current_setting"] = False
    return df


def _double_rows(df):
    return pd.concat([df, df], ignore_index=True)


def _extra_signal_and_fewer_stock_policy(df):
    if "class" not in df.columns:
        return df
    df = df.copy()
    df["S4"] = True
    idx = df.index[(df["division"] == "PEM101") & (df["class"] == "stock_policy")][:5]
    df.loc[idx, "class"] = "conflict"
    return df


def _drop_first_year(df):
    """Removes the earliest year from a by-year table (the year range shown follows the data)."""
    if "year" not in df.columns:
        return df
    return df[df["year"] != df["year"].min()].copy()


def _all_items_smooth(df):
    """Every item sells the same quantity every month: no item is Intermittent or Lumpy any more."""
    if "qty" not in df.columns or "itemcode" not in df.columns:
        return df
    df = df.copy()
    df["qty"] = 5.0
    return df


def _later_target_months(df):
    if "target_month" not in df.columns:
        return df
    df = df.copy()
    df["target_month"] = [str(pd.Period(m, freq="M") + 3) for m in df["target_month"]]
    return df


def _extra_notice_bucket(df):
    if "min_notice_days" not in df.columns:
        return df
    extra = df.iloc[[-1]].copy()
    extra["min_notice_days"] = 240
    return pd.concat([df, extra], ignore_index=True)


def _fewer_calibrated_items(df):
    if "policy" not in df.columns:
        return df
    df = df.copy()
    idx = df.index[df["policy"] == "finished_goods_stock"][:4]
    df.loc[idx, "policy"] = "component_stock_ato"
    return df


CSV_TRANSFORMS = {STOCK_VALUE_FILE: _scale_stock_value, NO_MINMAX_FILE: _more_missing_minmax, DISAGREE_FILE: _double_rows,
                  ITEM_LEVEL_FILE: _extra_signal_and_fewer_stock_policy, ON_TIME_FILE: _drop_first_year,
                  "delivery_not_late_by_year.csv": _drop_first_year, POLICY_FILE: _fewer_calibrated_items,
                  "processed_all_divisions_monthly_qty.csv": _all_items_smooth,
                  "forward_test_log_all_divisions.csv": _later_target_months,
                  "leadtime_notice_buckets_overall.csv": _extra_notice_bucket}


def _perturb_grid(d):
    d = copy.deepcopy(d)
    d["n_distinct_members"] = d["n_distinct_members"] + 1000
    d["today_point"]["not_late_pct"] = 91.37
    d["today_point"]["stock_value_thb"] = d["today_point"]["stock_value_thb"] * 2
    d["presets"]["extra_preset"] = copy.deepcopy(d["presets"]["stretch_99pct"])
    return d


def _perturb_alert(d):
    d = copy.deepcopy(d)
    d["not_late_before_may_2026_pct"] = 12.3
    d["units_before_may_2026"] = 987654
    d["units_from_may_2026"] = 4321
    d["split_date"] = "2026-06-01"
    return d


def _perturb_ratio(d):
    d = copy.deepcopy(d)
    d["today_not_late_pct"] = 90.11
    return d


JSON_TRANSFORMS = {"phase23_dense_grid_PEM101.json": _perturb_grid, "task2b_part4_pem107_alert.json": _perturb_alert,
                   "task2b_part3_ratio_grid_PEM101.json": _perturb_ratio}


def _perturb_config(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["backtest"]["min_train_months"] = cfg["backtest"]["min_train_months"] + 4
    cfg["page_timestamps"]["staleness_threshold_days"] = 1
    cfg["report_statistics"]["paired_t_threshold"] = 3
    cfg["backtest"]["holdout_months"] = 5
    cfg["inventory_page"]["tier_a_ranges"]["cycle_service_level"] = [0.85, 0.97]
    return cfg


class Build:
    """One build of both pages, optionally with perturbed sources."""

    def __init__(self, tmp_path, perturbed: bool, monkeypatch):
        self.perturbed = perturbed
        self.tmp = tmp_path
        self.mp = monkeypatch
        self.config = None

    def run(self):
        import build_inventory_page as bp
        import build_report
        mp = self.mp
        seg_copy = None
        if self.perturbed:
            orig_read = pd.read_csv
            orig_load = json.load
            orig_yaml = yaml.safe_load

            def read_csv(path, *a, **k):
                df = orig_read(path, *a, **k)
                fn = CSV_TRANSFORMS.get(os.path.basename(str(path)))
                return fn(df) if fn else df

            def load(f, *a, **k):
                d = orig_load(f, *a, **k)
                fn = JSON_TRANSFORMS.get(os.path.basename(getattr(f, "name", "")))
                return fn(d) if fn else d

            def safe_load(stream, *a, **k):
                d = orig_yaml(stream, *a, **k)
                return _perturb_config(d) if isinstance(d, dict) and "backtest" in d and "report" in d else d

            mp.setattr(pd, "read_csv", read_csv)
            mp.setattr(json, "load", load)
            mp.setattr(yaml, "safe_load", safe_load)
            with open(rv.SEGMENTATION_SCRIPT, encoding="utf-8") as f:
                text = f.read()
            seg_copy = self.tmp / "segmentation_copy.py"
            seg_copy.write_text(re.sub(r"^S3_THRESHOLD_DAYS\s*=\s*\d+", "S3_THRESHOLD_DAYS = 21", text, flags=re.M), encoding="utf-8")
            mp.setattr(rv, "SEGMENTATION_SCRIPT", str(seg_copy))
            mp.setattr(build_report, "FOCUS_ITEMS", list(build_report.FOCUS_ITEMS[:2]))
            real_notlate = build_report.gather_notlate
            mp.setattr(build_report, "gather_notlate", lambda: real_notlate().iloc[0:0])
        suffix = "perturbed" if self.perturbed else "base"
        self.sales_path = build_report.build_report(output_path=str(self.tmp / f"sales_{suffix}.html"))
        data = fresh_inventory_data()
        mp.setattr(bp, "build_data", lambda **kw: data)
        page = bp.build_page()
        self.inventory_path = str(self.tmp / f"inventory_{suffix}.html")
        with open(self.inventory_path, "w", encoding="utf-8") as f:
            f.write(page)
        self.data = data
        with open(self.sales_path, encoding="utf-8") as f:
            self.sales_html = f.read()
        self.inventory_html = page
        return self


@pytest.fixture
def two_builds(tmp_path, monkeypatch):
    base = Build(tmp_path, False, monkeypatch).run()
    monkeypatch.undo()          # restore everything, then perturb
    pert = Build(tmp_path, True, monkeypatch).run()
    monkeypatch.undo()
    return base, pert


def _first(pattern, text):
    m = re.search(pattern, text)
    assert m, f"pattern not found: {pattern}"
    return m.group(1)


# ------------------------------------------------------------------ sales report

def test_sales_report_numbers_follow_their_sources(two_builds):
    base, pert = two_builds
    b, p = base.sales_html, pert.sales_html
    # 7 backtest rounds: config backtest block
    rb, rp = _first(r"ทดสอบย้อนหลัง (\d+) รอบ", b), _first(r"ทดสอบย้อนหลัง (\d+) รอบ", p)
    assert rb != rp, "backtest round count is typed, not read from config"
    assert _first(r"ทดสอบ (\d+) รอบแบบเดียวกับ", p) == rp
    # 46 of 128 items with no current Min/Max
    assert _first(r"ใช้คำนวณไม่ได้ (\d+) จาก \d+ รายการ", p) == str(int(_first(r"ใช้คำนวณไม่ได้ (\d+) จาก \d+ รายการ", b)) + 5)
    # 2.5% forecast_date finding: doubled disagreement rows double the share
    fb, fp = float(_first(r"กระทบประมาณ ([\d.]+)% ของรายการ", b)), float(_first(r"กระทบประมาณ ([\d.]+)% ของรายการ", p))
    assert fp == pytest.approx(2 * fb, abs=0.11), (fb, fp)
    # on-time 2023 value in the executive summary
    assert _first(r"ปรับตัวขึ้นจาก [\d.]+% \((\d{4})\)", b) == "2023" and _first(r"ปรับตัวขึ้นจาก [\d.]+% \((\d{4})\)", p) == "2024"
    # staleness threshold from config
    assert "เก่ากว่า 1 วัน" in p and "เก่ากว่า 1 วัน" not in b


# ------------------------------------------------------------------ inventory page (static text and data)

def test_inventory_page_numbers_follow_their_sources(two_builds):
    base, pert = two_builds
    b, p = base.inventory_html, pert.inventory_html
    gb, gp = float(_first(r"ประมาณ (\d+)% \(PEM101\)", b)), float(_first(r"ประมาณ (\d+)% \(PEM101\)", p))
    assert gb != gp, "the monthly-versus-daily gap is typed, not computed"
    assert _first(r"ส่งได้ภายใน (\d+) วัน", b) == "14" and _first(r"ส่งได้ภายใน (\d+) วัน", p) == "21"
    assert _first(r"พฤติกรรมจริง (\d+) อย่าง", b) == "3" and _first(r"พฤติกรรมจริง (\d+) อย่าง", p) == "4"
    nb, npt = base.data["divisions"]["PEM101"]["curve_target"]["item_set_note"], pert.data["divisions"]["PEM101"]["curve_target"]["item_set_note"]
    assert re.findall(r"\d+", nb) != re.findall(r"\d+", npt), "calibrated / stock-policy item counts are typed"
    assert pert.data["staleness_threshold_days"] == 1 and base.data["staleness_threshold_days"] != 1
    # PEM107 split month is read from the alert data, with wording only for the month approved
    assert base.data["pem107_alert"]["split_label"] != pert.data["pem107_alert"]["split_label"]


def test_thai_month_names_cover_every_month():
    assert rv.thai_month_year("2026-05-01") == "พ.ค. 2569"
    assert rv.thai_month_year("2026-10-01") == "ต.ค. 2569"
    assert len({rv.thai_month_year(f"2026-{m:02d}-01") for m in range(1, 13)}) == 12


def test_backtest_rounds_match_the_backtest_module():
    import backtest_rekeyed as bk
    with open(os.path.join(rv.PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert rv.backtest_rounds(cfg) == len(bk.get_origins(bk.TOTAL_MONTHS, bk.HOLDOUT))


# ------------------------------------------------------------------ W-rest numbers

def test_numbers_from_the_remaining_typed_list_follow_their_sources(two_builds):
    base, pert = two_builds
    b, p = base.sales_html, pert.sales_html
    # share of items with intermittent or lumpy demand (METRICS.md Sec.29 classification of the data)
    sb, sp_ = int(_first(r"และ (\d+)% ของรหัสสินค้ามีลักษณะการขายแบบ", b)), int(_first(r"และ (\d+)% ของรหัสสินค้ามีลักษณะการขายแบบ", p))
    assert sb == round(rv.intermittent_lumpy_share_pct()) and sp_ == 0, (sb, sp_)
    # first scoring month from the forward-test log
    with open(os.path.join(rv.PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        real_cfg = yaml.safe_load(f)
    assert f"ผลรอบแรกต้นเดือน {rv.first_scoring_month_label(real_cfg)}" in b
    lb, lp = _first(r"ผลรอบแรกต้นเดือน ([^<]+)<", b), _first(r"ผลรอบแรกต้นเดือน ([^<]+)<", p)
    assert lb != lp, "first scoring month is typed"
    # |t| threshold
    assert _first(r"\|t\| ต่ำกว่า (\d+) ในทุกคู่", b) == "2" and _first(r"\|t\| ต่ำกว่า (\d+) ในทุกคู่", p) == "3"
    # year range in the delivery section follows the years present
    assert "(2023-2026)" in b and "(2024-2026)" in p and "(2023-2026)" not in p
    # numbers inside the manual notes that describe the data or a control
    assert "≥30 วัน, ≥60 วัน … ≥180 วัน" in b and "≥30 วัน, ≥60 วัน … ≥240 วัน" in p
    assert "รหัสสินค้า 3 ตัว" in b and "รหัสสินค้า 2 ตัว" in p
    assert "รอบทดสอบที่ 1-7 " in b and "รอบทดสอบที่ 1-7 " not in p
    assert "เดือนที่ 1-6 หลังจุด" in b and "เดือนที่ 1-5 หลังจุด" in p
    assert "▸ 2 เส้น ส่งไม่ช้า" in b and "▸ 1 เส้น ส่งไม่ช้า" in p
    ib, ip = base.inventory_html, pert.inventory_html
    assert "cycle service level (0.80-0.99)" in ib and "cycle service level (0.85-0.97)" in ip
    assert "ใช้ปุ่มเป้าสำเร็จรูป 3 ปุ่ม" in ib and "ใช้ปุ่มเป้าสำเร็จรูป 4 ปุ่ม" in ip
    assert "ก่อนและหลัง พ.ค. 2569 พร้อม" in ib and "ก่อนและหลัง มิ.ย. 2569 พร้อม" in ip
    assert "ตั้งแต่ พ.ค. 2569</div>" in ib and "ตั้งแต่ มิ.ย. 2569</div>" in ip
    # the chart axis of the trade-off follows the configured range
    assert base.data["tier_a_ranges"]["cycle_service_level"] == [0.8, 0.99] and pert.data["tier_a_ranges"]["cycle_service_level"] == [0.85, 0.97]


# ------------------------------------------------------------------ lines the page's script fills in

def test_script_filled_lines_follow_their_sources(two_builds):
    exe = require_browser()
    base, pert = two_builds
    edge = Edge(exe)
    try:
        texts = {}
        for name, build in (("base", base), ("pert", pert)):
            edge.open(build.inventory_path)
            edge.ev("document.getElementById('preset-highest-at-today').click(); 1")
            edge.pump(0.3)
            summary = edge.ev("document.getElementById('curve-target-summary').textContent")
            rel = edge.ev("document.getElementById('relative-service-cost-note').textContent")
            edge.ev("document.getElementById('division-select').value='PEM107'; onDivisionChange(); 1")
            edge.pump(0.4)
            alert = edge.ev("document.getElementById('pem107-alert-limitations').textContent")
            texts[name] = (summary, rel, alert)
        sb, rb, ab = texts["base"]
        sp, rp, ap = texts["pert"]
        grid_b = base.data["divisions"]["PEM101"]["curve_target"]
        grid_p = pert.data["divisions"]["PEM101"]["curve_target"]
        assert f"{grid_p['n_distinct_members']} ชุด" in sp and f"{grid_b['n_distinct_members']} ชุด" in sb and sb != sp
        assert "ส่งไม่ช้า 91.37%" in sp and "ส่งไม่ช้า 91.37%" not in sb
        assert f"{round(grid_p['today_point']['stock_value_thb']):,} บาท" in sp
        assert "จาก 90.11% เป็น" in rp and "จาก 90.11% เป็น" not in rb
        assert "12.3%" in ap and "987,654 ชิ้น" in ap and "4,321 ชิ้น" in ap
        assert "12.3%" not in ab
    finally:
        edge.close()
