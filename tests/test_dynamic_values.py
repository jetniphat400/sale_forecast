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


def _different_significance(df):
    """PEM101 against Direct gets a larger relative difference (7.7 percent), PEM103 against Direct becomes a real loss."""
    if "rel_diff_pct" not in df.columns:
        return df
    df = df.copy()
    df.loc[(df["division"] == "PEM101") & (df["other_method"] == "Direct"), "rel_diff_pct"] = -7.7
    df.loc[(df["division"] == "PEM103") & (df["other_method"] == "Direct"), ["rel_diff_pct", "verdict"]] = [3.0, "worse"]
    return df


def _slower_materials(df):
    """Every item's slowest-material lead time 10 days longer (the PEM101 calibrated section's median line and column follow it)."""
    if "bottleneck_days" not in df.columns:
        return df
    df = df.copy()
    df["bottleneck_days"] = df["bottleneck_days"] + 10
    return df



def _perturb_grid(d):
    d = copy.deepcopy(d)
    d["n_distinct_members"] = d["n_distinct_members"] + 1000
    d["n_items_calibrated"] = d["n_items_calibrated"] + 7
    d["lead_time_days"] = {"min": 2, "max": 45, "median": 9.0}
    d["today_point"]["not_late_pct"] = 91.37
    d["today_point"]["stock_value_thb"] = d["today_point"]["stock_value_thb"] * 2
    d["presets"]["extra_preset"] = copy.deepcopy(d["presets"]["stretch_99pct"])
    return d


def _perturb_targets(d):
    """The sales history behind the PEM101 Min and Max ends two months later (the section's note names the window)."""
    d = copy.deepcopy(d)
    if "validation_end" in d:
        d["validation_end"] = "2026-11-30"
    return d


def _more_placeholders(df):
    """Seven forecast-status codes become placeholders (the total stays 445): the count of codes with no forecast changes by seven."""
    if "status_category" not in df.columns:
        return df
    df = df.copy()
    idx = df.index[df["status_category"] == "forecast"][:7]
    df.loc[idx, "status_category"] = "placeholder - pending method"
    return df


def _shift_months(ym, k):
    return str(pd.Period(ym, freq="M") + k)


def _perturbed_vintage_facts(f):
    """The latest vintage as another vintage: run three months later, fit window and forecast months three months later, every forecast doubled
    (the forward-test log itself cannot be altered as it is read: its rows are checked against a recorded hash)."""
    g = dict(f)
    g.update(run_date="2027-01-04", fit_first=_shift_months(f["fit_first"], 3), fit_last=_shift_months(f["fit_last"], 3),
             forecast_months=[_shift_months(m, 3) for m in f["forecast_months"]])
    rows = f["item_rows"].copy()
    rows["target_month"] = rows["target_month"].map(lambda m: _shift_months(m, 3))
    rows["forecast_qty"] = rows["forecast_qty"] * 2
    g["item_rows"] = rows
    w = f["forecast"].copy()
    w.columns = [_shift_months(c, 3) for c in w.columns]
    g["forecast"] = w * 2
    return g


def _perturbed_scored(df):
    """Two scored months instead of one, every MAE and Bias doubled."""
    later = df.copy()
    later["target_month"] = later["target_month"].map(lambda m: _shift_months(m, 1))
    out = pd.concat([df, later], ignore_index=True)
    out["MAE"], out["Bias"] = out["MAE"] * 2, out["Bias"] * 2
    return out


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


JSON_TRANSFORMS = {"week1_recal_targets.json": _perturb_targets, "maxmin_v1_dense_grid_PEM101.json": _perturb_grid, "task2b_part4_pem107_alert.json": _perturb_alert,
                   "maxmin_v1_ratio_grid_PEM101.json": _perturb_ratio}

CSV_TRANSFORMS = {"phaseC_step1revised_item_status_445.csv": _more_placeholders, "item_lead_time_v1.csv": _slower_materials, "topdown_significance.csv": _different_significance, STOCK_VALUE_FILE: _scale_stock_value, NO_MINMAX_FILE: _more_missing_minmax, DISAGREE_FILE: _double_rows,
                  ITEM_LEVEL_FILE: _extra_signal_and_fewer_stock_policy, ON_TIME_FILE: _drop_first_year,
                  "delivery_not_late_by_year.csv": _drop_first_year, POLICY_FILE: _fewer_calibrated_items,
                  "processed_all_divisions_monthly_qty.csv": _all_items_smooth,
                  "leadtime_notice_buckets_overall.csv": _extra_notice_bucket}


def _perturb_config(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["backtest"]["min_train_months"] = cfg["backtest"]["min_train_months"] + 4
    cfg["page_timestamps"]["staleness_threshold_days"] = 1
    cfg["report_statistics"]["paired_t_threshold"] = 3
    cfg["backtest"]["holdout_months"] = 5
    cfg["inventory_page"]["tier_a_ranges"]["cycle_service_level"] = [0.85, 0.97]
    return cfg


PILOT_FILE = "processed_full_category_sales_monthly_forecastDate.csv"
PILOT_AGE_PERTURBED_DAYS = 5      # older than the perturbed 1-day threshold (the build counts whole days, so >= 2 is stale)
PILOT_AGE_BASE_DAYS = 0


def set_pilot_data_date(monkeypatch, age_days: float):
    """C11 (2026-10-02): the PEM101 pilot file's data date is set BY THE TEST, never taken from the real file, whose
    age changes with every run (the monthly runner now refreshes it). Every read of that file through pandas returns
    its snapshot_pull_date as `age_days` before now; the real file on disk is not touched."""
    from datetime import datetime, timedelta
    stamp = (datetime.now() - timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M:%S")
    orig = pd.read_csv

    def read_csv(path, *a, **k):
        df = orig(path, *a, **k)
        if os.path.basename(str(path)) == PILOT_FILE and "snapshot_pull_date" in df.columns:
            df = df.copy()
            df["snapshot_pull_date"] = stamp
        return df
    monkeypatch.setattr(pd, "read_csv", read_csv)
    return stamp


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
        real_facts = rv.vintage_facts()          # read (and hash-checked) before any source is perturbed
        set_pilot_data_date(mp, PILOT_AGE_PERTURBED_DAYS if self.perturbed else PILOT_AGE_BASE_DAYS)
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
            mp.setattr(rv, "vintage_facts", lambda root=None: _perturbed_vintage_facts(real_facts))
            # the unit prices of the baht view read the saved monthly series, which has no month beyond the real fit window: price on the real window
            real_prices = rv.unit_prices
            mp.setattr(rv, "unit_prices", lambda codes, basis, ff, fl, *a, **k: real_prices(codes, basis, real_facts["fit_first"], real_facts["fit_last"], *a, **k))
            mp.setattr(rv, "price_back_check", lambda *a, **k: {"ratios": {}, "outside": []})        # the perturbed series would trip the price back-check; tested in test_build_report.py
            real_scored = build_report.gather_scored_months
            mp.setattr(build_report, "gather_scored_months", lambda pr: _perturbed_scored(real_scored(pr)))
            # the perturbed scores no longer match the log the baht columns are computed from (checked against Bias in the build): the baht columns are tested in test_build_report.py
            mp.setattr(build_report, "attach_scored_baht", lambda sc, prices: sc.assign(baht_forecast=0, baht_actual=0, baht_diff=0, n_no_price=0))
            # the perturbed series no longer reproduces the main table's MAE, which the Relative MAE block checks (and stops on): that block is tested in test_build_report.py
            mp.setattr(build_report, "gather_accuracy_vs_naive", lambda cfg, pr: {
                "rows": [], "forward_items": None, "items_beyond_limit": {}, "thresholds": {"good": 0.7, "pass": 1.0, "limit": 4.0},
                "forward_by_division": pd.DataFrame(columns=["vintage_id", "target_month", "division", "MAE_naive", "relative_mae"])})
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
    # the "does Top-down beat the others" block: percentages and verdicts come from topdown_significance.csv
    import build_report
    sig = pd.read_csv(os.path.join(rv.SUMMARY_DIR, "topdown_significance.csv"))
    direct = sig[sig["other_method"] == "Direct"]
    expected_base = build_report.significance_line(direct, "Direct")
    assert expected_base in b, "the Direct line of the block does not follow topdown_significance.csv"
    assert expected_base not in p
    assert "PEM101 ทายพลาดน้อยกว่าประมาณ 7.7% ทดสอบแล้วความต่างนี้เกิดจริง" in p
    assert "PEM101 ทายพลาดน้อยกว่าประมาณ 7.7% ทดสอบแล้วความต่างนี้เกิดจริง แม้จะเล็ก" not in p      # 7.7 is not below 5
    assert "PEM103 ทายพลาดมากกว่าประมาณ 3.0% ทดสอบแล้วความต่างนี้เกิดจริง แม้จะเล็ก" in p


def _pilot_row(html_text):
    """(shown data date, status) of the 'ช่วงข้อมูลหลัก' row of the page's per-section freshness table."""
    m = re.search(r"<td><!-- source: [^>]*-->ช่วงข้อมูลหลัก</td><td>([^<]*)</td><td>([^<]*)</td>", html_text)
    assert m, "the freshness table has no row for the pilot section"
    return m.group(1), m.group(2)


@pytest.mark.parametrize("age_days,expect_notice", [(5, True), (0, False)])
def test_pilot_data_age_drives_the_staleness_notice_in_both_directions(tmp_path, monkeypatch, age_days, expect_notice):
    """With a 1-day threshold: a pilot data date 5 days old shows the notice with its date; one from now shows none.
    The pilot file's data date is set by the test (set_pilot_data_date), whatever the real file's age."""
    import build_report
    stamp = set_pilot_data_date(monkeypatch, age_days)
    monkeypatch.setattr(rv, "staleness_threshold_days", lambda config: 1)
    path = build_report.build_report(output_path=str(tmp_path / "sales.html"))
    with open(path, encoding="utf-8") as f:
        shown, status = _pilot_row(f.read())
    assert shown == stamp, "the page must show the data date the test set"
    assert status == ("เก่ากว่า 1 วัน" if expect_notice else "ใหม่")


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
    llb = base.data["divisions"]["PEM101"]["curve_target"]["lead_time_lines"]
    llp = pert.data["divisions"]["PEM101"]["curve_target"]["lead_time_lines"]
    assert llp["lead_min"] == 2 and llp["lead_max"] == 45 and llb["lead_max"] != 45, "the lead range is typed, not read from the members"
    assert llp["material_lead_median_observed"] == llb["material_lead_median_observed"] + 10, "the observed material lead median is typed, not read from the per-item output"
    assert llp["n_observed"] == llb["n_observed"] and llp["n_items"] == llb["n_items"] == 92 and 0 < llb["n_observed"] <= llb["n_items"]
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
    assert "ทุกต้นเดือนระบบเทียบยอดทายกับยอดขายจริงของเดือนที่ผ่านมา และเพิ่มผลในตารางนี้" in b and "ผลรอบแรกต้นเดือน" not in b
    # the |t| and Wilcoxon thresholds are applied when topdown_significance.csv is written (METRICS.md Sec.41), not typed in the page;
    # the report only states them in an HTML comment read from that file
    assert "|t| &gt;= 2" in b and "Wilcoxon p &lt; 0.05" in b
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
            lines = edge.ev("document.getElementById('curve-lead-lines').textContent")
            edge.ev("document.getElementById('division-select').value='PEM107'; onDivisionChange(); 1")
            edge.pump(0.4)
            alert = edge.ev("document.getElementById('pem107-alert-limitations').textContent")
            texts[name] = (summary, rel, alert)
            ll = (base if name == "base" else pert).data["divisions"]["PEM101"]["curve_target"]["lead_time_lines"]
            assert f"อยู่ระหว่าง {ll['lead_min']} ถึง {ll['lead_max']} วัน" in lines
            assert f"ค่ากลาง {ll['material_lead_median_observed']:g} วัน (มีข้อมูล {ll['n_observed']} จาก {ll['n_items']} รายการ)" in lines
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


# ------------------------------------------------------------------ forecast/operation_plan.html (week 2)

def test_operation_plan_page_numbers_dates_and_items_follow_their_sources():
    """The plan page is built twice from fixture plans that differ in one source each (stock pull time, forecast run date, first month, opening stock,
    backlog, item codes). Every figure, date and item code in its text must change with its source; a typed value would render the same twice."""
    import re as _re
    from test_operation_plan_page_builder import _plan
    import build_operation_plan_page as bp
    im, dm, meta = _plan()
    base = bp.render(bp.compute_values(im, dm, meta, {}, "2026-10-02", ["PEM101", "PEM107"]))
    im2, dm2, meta2 = _plan(extra107={"Z9": 400.0, "Y9": 100.0, "X9": 30.0}, refill101=True)
    im2 = im2.copy()
    im2["month"] = im2["month"].map({"2026-10": "2027-02", "2026-11": "2027-03", "2026-12": "2027-04"})
    dm2 = dm2.copy()
    dm2["month"] = dm2["month"].map({"2026-10": "2027-02", "2026-11": "2027-03", "2026-12": "2027-04"})
    meta2 = dict(meta2, months=["2027-02", "2027-03", "2027-04"], stock_pull={"pulled_at_local": "2027-01-15 17:45:10"})
    pert = bp.render(bp.compute_values(im2, dm2, meta2, {}, "2027-01-04", ["PEM101", "PEM107"]))
    lines = lambda page: _re.findall(r'<p class="note-line">(.*?)</p>', page)
    assert "6 ต.ค. 69 08:00" in base and "15 ม.ค. 70 17:45" in pert and "6 ต.ค. 69" not in pert
    assert "Forecast (ยอดทาย) รันเมื่อ ต.ค. 69" in base and "Forecast (ยอดทาย) รันเมื่อ ม.ค. 70" in pert
    lb, lp = lines(base), lines(pert)
    assert lb[0].startswith("ต.ค. 69 PEM101") and lp[0].startswith("ก.พ. 70 PEM101")
    assert "A7" in lb[1] and "Z9" in lp[1] and "Z9" not in lb[1] and "A7" not in lp[1]
    assert _re.findall(r"\d[\d,]*", lb[1]) != _re.findall(r"\d[\d,]*", lp[1])
    assert base != pert


# ------------------------------------------------------------------ week 3: the division lines of the plan page and the material plan page

def test_operation_plan_division_lines_follow_the_counts_of_the_plan():
    """The counts in the three per-division lines come from the plan's meta (counts per division): changing a count changes the line, and a division with
    stock items or with nothing to say shows no line."""
    import build_operation_plan_page as bp
    from test_operation_plan_page_builder import _plan_all, SIX
    im, dm, meta = _plan_all()
    base = bp.render(bp.compute_values(im, dm, meta, {}, "2026-10-02", SIX))
    meta2 = copy.deepcopy(meta)
    meta2["counts"]["no_forecast_items_by_division"]["PEM103"] = 41
    meta2["counts"]["no_production_items_by_division"]["PEM103"] = 17
    meta2["counts"]["stock_items_by_division"]["PEM102"] = 3          # a division that has stock items no longer says it has none
    pert = bp.render(bp.compute_values(im, dm, meta2, {}, "2026-10-02", SIX))
    assert "1 รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้มีออเดอร์ค้าง 1 รหัส" in base and "41 รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้มีออเดอร์ค้าง 1 รหัส" in pert and "41 รหัส" not in base
    assert "1 รหัสไม่พบการผลิตในระบบ ไม่นับเป็นภาระผลิต" in base and "17 รหัสไม่พบการผลิตในระบบ ไม่นับเป็นภาระผลิต" in pert
    assert "PEM102 ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock" in base and "PEM102 ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock" not in pert


def _material_frames(n_months, today, pulled, warehouses, divisions, open_used, qty, lead, first_date):
    months = [str(pd.Period("2026-10", freq="M") + k) for k in range(n_months)]
    mm = pd.DataFrame([{"material": "M1", "month": m, "gross": qty, "stock_available": 0.0, "open_orders_cum": 0.0, "net_cum": qty * (k + 1), "net_month": qty,
                        "order_date": first_date} for k, m in enumerate(months)])
    sm = pd.DataFrame([{"material": "M1", "name": "Material one", "used_in": "FG-ONE FG-TWO", "n_products": 2, "bom_unit": "PC", "stock_unit": "PC", "purchase_unit": "PC",
                        "unit_vs_stock": "same", "unit_vs_purchase": "same", "stock_now": 0.0, "open_orders_total": 0.0, "lead_days": lead, "lead_source": "observed",
                        "total_gross": qty * n_months, "total_net": qty * n_months, "first_short_month": months[0], "latest_order_date": first_date, "to_order_now": True,
                        "qty_to_order_now": qty, "also_has_bom": False}])
    meta = {"months": months, "today": today, "operation_plan_today": today, "rm_pulled_at_local": pulled, "rm_warehouses": warehouses, "open_orders_used": open_used, "divisions": divisions}
    return mm, sm, meta


def test_material_plan_page_text_values_follow_their_sources():
    import build_material_plan_page as bm
    a = bm.render(bm.compute_values(*_material_frames(5, "2026-10-06", "2026-10-06 07:30:00", ["WH21", "WH22"], ["PEM101", "PEM103"], True, 50.0, 20.0, "2026-09-11"), 30))
    b = bm.render(bm.compute_values(*_material_frames(3, "2027-01-04", "2027-01-15 17:45:10", ["WH90"], ["CI101"], False, 77.0, 33.0, "2027-01-20"), 45))
    assert "แผนวัตถุดิบ 5 เดือน" in a and "แผนวัตถุดิบ 3 เดือน" in b
    assert "จากแผนการผลิตรอบ ต.ค. 69 · stock วัตถุดิบดึงเมื่อ 6 ต.ค. 69 07:30" in a and "จากแผนการผลิตรอบ ม.ค. 70 · stock วัตถุดิบดึงเมื่อ 15 ม.ค. 70 17:45" in b
    assert "stock วัตถุดิบนับจากคลัง WH21, WH22" in a and "stock วัตถุดิบนับจากคลัง WH90" in b
    assert 'id="divisions-covered">ฝ่ายที่รวมในแผนนี้: PEM101, PEM103<' in a and 'id="divisions-covered">ฝ่ายที่รวมในแผนนี้: CI101<' in b
    assert "นับของที่สั่งแล้วรอรับตามวันที่คาดว่าจะได้" in a and "ยังไม่นับของที่สั่งแล้วรอรับ" in b
    cells = lambda page, table: re.findall(r"<td[^>]*>(.*?)</td>", page.split('id="%s"' % table)[1].split("</table>")[0])
    ca, cb = cells(a, "late-table"), cells(b, "within-table")           # a: order date before the plan's day; b: 16 days after it, inside the 45-day window
    assert ca[3:6] == ["250", "11 ก.ย. 69", "20"] and cb[3:6] == ["231", "20 ม.ค. 70", "33"] and ca[6] == "ใบสั่งซื้อจริง"      # the quantity sums the months whose order date is in the list's span
    assert "ต้องสั่งภายใน 30 วัน</h2>" in a and "ต้องสั่งภายใน 45 วัน</h2>" in b
    assert "วัตถุดิบที่ต้องสั่งภายใน 30 วันข้างหน้า ถึงจะได้ของทันตามแผน" in a and "วัตถุดิบที่ต้องสั่งภายใน 45 วันข้างหน้า ถึงจะได้ของทันตามแผน" in b


# ------------------------------------------------------------------ 2026-10-08: the new lines and tables follow their sources

def _forward_cells(html_text):
    """First division's first item row of the forward forecast table: (code, [cells])."""
    row = re.search(r'<tr class="fwd-item".*?</tr>', html_text, re.S).group(0)
    return re.search(r"<td>([^<\s]+)", row).group(1), re.findall(r"<td>(.*?)</td>", row)[1:]


def test_new_sales_report_lines_and_tables_follow_their_sources(two_builds):
    base, pert = two_builds
    b, p = base.sales_html, pert.sales_html
    # the round, the last month of the sales used and the build time come from the vintage and the clock
    fb, fp = _first(r'id="freshness-line">(.*?)</span>', b), _first(r'id="freshness-line">(.*?)</span>', p)
    assert fb != fp and fp.startswith("Forecast (ยอดทาย) รันเมื่อ ม.ค. 70 · ใช้ยอดขายถึง พ.ย. 69 · หน้าสร้างเมื่อ ")
    assert re.fullmatch(r"Forecast \(ยอดทาย\) รันเมื่อ \S+ \d\d · ใช้ยอดขายถึง \S+ \d\d · หน้าสร้างเมื่อ \d{1,2} \S+ \d\d \d\d:\d\d", fb)
    # the fit window, the forecast months
    rb, rp = _first(r'id="fit-range-line">(.*?)</td>', b), _first(r'id="fit-range-line">(.*?)</td>', p)
    assert rb != rp and rp == "ยอดขายที่ใช้ทาย พ.ค. 67 ถึง พ.ย. 69"
    hb, hp = _first(r"<h2>2\. (.*?)</h2>", b), _first(r"<h2>2\. (.*?)</h2>", p)
    assert hb != hp and hp == "ยอดทาย ธ.ค. 69 ถึง พ.ค. 70"
    # the count of codes with no forecast follows the scope table (seven codes moved from forecast to placeholder)
    nb, np_ = int(_first(r"รหัสที่ยังไม่มียอดทาย (\d+) รหัส", b)), int(_first(r"รหัสที่ยังไม่มียอดทาย (\d+) รหัส", p))
    assert np_ == nb + 7
    # the forward forecast follows the vintage: every forecast doubled in the second build
    cb, vb = _forward_cells(b)
    cp, vp = _forward_cells(p)
    assert cb == cp
    for x, y in zip(vb, vp):
        xv, yv = float(x.replace(",", "")), float(y.replace(",", ""))
        assert yv == pytest.approx(2 * xv, abs=0.51 if xv >= 10 else 0.11), (x, y)
    assert vb != vp
    # the pilot groups: MAE and Bias are recomputed from the series, so another series gives other values; the sentence repeats the Bias of its row
    for html_text in (b, p):
        for label in ("Fuse Cutout", "Surge Arrester"):
            mae, bias = re.search(rf"<tr><td>{label}</td><td>(-?[\d.]+)</td><td>(-?[\d.]+)</td></tr>", html_text).groups()
            if float(bias) < 0:
                assert f"▸ {label} ทายต่ำกว่าจริงเฉลี่ยเดือนละ {abs(float(bias)):.1f} ชิ้น" in html_text
            else:
                assert f"▸ {label} ทายต่ำกว่าจริง" not in html_text
    assert re.findall(r'<tr><td>(?:Fuse Cutout|Surge Arrester)</td><td>[-\d.]+</td><td>[-\d.]+</td></tr>', b) != \
        re.findall(r'<tr><td>(?:Fuse Cutout|Surge Arrester)</td><td>[-\d.]+</td><td>[-\d.]+</td></tr>', p)
    # the monthly scored table and its count of months
    assert "▸ ตอนนี้มีผล 1 เดือน" in b and "▸ ตอนนี้มีผล 2 เดือน" in p
    sb, sp_ = re.findall(r'<table class="report-table" id="scored-table">.*?<tbody>(.*?)</tbody>', b, re.S)[0], re.findall(r'<table class="report-table" id="scored-table">.*?<tbody>(.*?)</tbody>', p, re.S)[0]
    assert sb != sp_ and sp_.count("<tr>") == 2 * sb.count("<tr>")


def test_new_inventory_page_values_follow_their_sources(two_builds):
    base, pert = two_builds
    assert base.data["forecast_round_label"] != pert.data["forecast_round_label"] and pert.data["forecast_round_label"] == "ม.ค. 70"
    nb = base.data["divisions"]["PEM101"]["curve_target"]["demand_input_note"]
    np_ = pert.data["divisions"]["PEM101"]["curve_target"]["demand_input_note"]
    assert nb != np_ and "{" not in nb and "}" not in np_
    mb, mp_ = re.search(r"ย้อนหลัง (\S+ \d\d) ถึง (\S+ \d\d) ", nb), re.search(r"ย้อนหลัง (\S+ \d\d) ถึง (\S+ \d\d) ", np_)
    assert mb.group(1) == mp_.group(1) and mb.group(2) != mp_.group(2) and mp_.group(2) == "พ.ย. 69"        # the end of the sales history moved two months, the start did not
