"""Tests for src/build_report.py -- the report must build cleanly from the current
output/summary/ contents, every rendered number must match its cited source exactly, and the
build must FAIL LOUDLY (raise, never render a blank/placeholder page) when a required source
file is missing (CONVENTIONS.md: validation failures never silently skipped).

Phase E1 report rework: the report now embeds its chart data as a single JSON block
(src/build_report.py's embed_report_data()) so client-side Plotly charts never re-derive a
number -- test_embedded_json_matches_source_files_exactly checks that JSON block value-for-value
against fresh, independent reads of the same source files, not just a shape/presence check.
"""
import json
import os
import re
import shutil

import pandas as pd
import pytest

import build_report
from build_report import ReportSourceError, build_report as run_build_report, load_config

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
FORECAST_OUT = os.path.join(PROJECT_ROOT, "forecast", "sales_report.html")


def _embedded_data():
    with open(FORECAST_OUT, "r", encoding="utf-8") as f:
        html_text = f.read()
    m = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html_text, re.DOTALL)
    assert m, "Embedded #report-data JSON block not found in rendered report"
    return json.loads(m.group(1))


def test_report_builds_without_error_from_current_outputs(tmp_path):
    """FIXED (Part 1/Part 3 of the forward test / monthly refresh task): previously called
    run_build_report() with no override, which wrote directly to the real tracked
    forecast/sales_report.html on every test run (METRICS.md Sec.28's last bullet; commits
    5c17ea4/da5aedd were trivial page_built_at-only re-builds caused by exactly this). Now passes
    a tmp_path -- the real tracked file is never touched by running the test suite."""
    out_path = run_build_report(output_path=str(tmp_path / "sales_report.html"))
    assert os.path.exists(out_path)
    with open(out_path, "r", encoding="utf-8") as f:
        html_text = f.read()
    assert len(html_text) > 1000
    for section_id in ["exec-summary", "scope", "business-findings", "data", "model",
                        "results", "limitations", "next-steps"]:
        assert f'id="{section_id}"' in html_text, f"Section {section_id} missing from rendered report"


def test_every_source_citation_names_a_real_file_and_column():
    """Every '<!-- source: output/summary/X, column Y -->' comment must name a file that
    exists and, where Y is a real column name (not a compound like 'a / b'), a column that
    file actually has."""
    out_path = os.path.join(PROJECT_ROOT, "forecast", "sales_report.html")
    with open(out_path, "r", encoding="utf-8") as f:
        html_text = f.read()
    citations = re.findall(r"<!-- source: output/summary/([\w\.]+), column ([^-]+?) -->", html_text)
    assert len(citations) > 0, "No source citations found in the rendered report"
    checked_files = set()
    for rel_path, col_spec in citations:
        abs_path = os.path.join(SUMMARY_DIR, rel_path)
        assert os.path.exists(abs_path), f"Cited source file does not exist: {rel_path}"
        if rel_path not in checked_files:
            df = pd.read_csv(abs_path)
            for col in re.split(r"\s*/\s*", col_spec.strip()):
                assert col in df.columns, f"Cited column '{col}' not in {rel_path} (has: {list(df.columns)})"
            checked_files.add(rel_path)


def test_scope_table_numeric_values_match_their_source_csv():
    """The rendered scope-table grand totals must equal a fresh, independent recomputation
    from the same source CSV the report cites."""
    out_path = os.path.join(PROJECT_ROOT, "forecast", "sales_report.html")
    with open(out_path, "r", encoding="utf-8") as f:
        html_text = f.read()
    m = re.search(r"รวมทั้งหมด</td><td>(\d+)</td><td>(\d+)</td><td>(\d+)</td><td>(\d+)</td>", html_text)
    assert m, "Scope grand-total row not found in rendered report"
    rendered_forecast, rendered_placeholder, rendered_excluded, rendered_total = (int(x) for x in m.groups())

    df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv"))
    bucket_map = {
        "forecast": "forecast",
        "placeholder - pending method": "placeholder",
        "placeholder - method already assigned": "placeholder",
        "excluded - division excluded from forecasting (data volume)": "excluded",
        "excluded - listed but never sold, no plan-against basis": "excluded",
    }
    df["bucket"] = df["status_category"].map(bucket_map)
    counts = df["bucket"].value_counts()
    assert rendered_forecast == counts["forecast"]
    assert rendered_placeholder == counts["placeholder"]
    assert rendered_excluded == counts["excluded"]
    assert rendered_total == len(df)


def test_median_notice_matches_source_csv_exactly():
    out_path = os.path.join(PROJECT_ROOT, "forecast", "sales_report.html")
    with open(out_path, "r", encoding="utf-8") as f:
        html_text = f.read()
    m = re.search(r"Median customer notice: <b>([\d.,]+)</b>", html_text)
    assert m, "Median notice figure not found in rendered report"
    rendered_value = float(m.group(1).replace(",", ""))

    source_df = pd.read_csv(os.path.join(SUMMARY_DIR, "leadtime_overall_distribution.csv"))
    expected = round(source_df["median"].iloc[0], 0)
    assert rendered_value == expected


def test_build_fails_loudly_when_a_required_source_file_is_missing(tmp_path, monkeypatch):
    """Simulates the missing-file case in an isolated temp copy of output/summary -- never
    touches the real project files."""
    temp_summary = tmp_path / "summary"
    shutil.copytree(SUMMARY_DIR, temp_summary)
    os.remove(temp_summary / "delivery_by_year.csv")

    monkeypatch.setattr(build_report, "SUMMARY_DIR", str(temp_summary))
    with pytest.raises(ReportSourceError, match="delivery_by_year.csv"):
        build_report.render_page(load_config())


def test_run_pipeline_wires_build_report_as_the_final_stage():
    import run_pipeline
    assert run_pipeline.STAGES[-1]["script"] == "build_report.py"
    assert run_pipeline.STAGES[-1]["label"] == "build_sales_report"


def test_build_fails_loudly_when_a_required_column_is_missing(tmp_path, monkeypatch):
    temp_summary = tmp_path / "summary"
    shutil.copytree(SUMMARY_DIR, temp_summary)
    df = pd.read_csv(temp_summary / "phaseC_step2_per_division_summary_qty.csv")
    df.drop(columns=["MASE"]).to_csv(temp_summary / "phaseC_step2_per_division_summary_qty.csv", index=False)

    monkeypatch.setattr(build_report, "SUMMARY_DIR", str(temp_summary))
    with pytest.raises(ReportSourceError, match="MASE"):
        build_report.render_page(load_config())


def test_build_fails_loudly_when_forecast_vs_actual_source_is_missing(tmp_path, monkeypatch):
    """The new (Phase E1 rework) forecast-vs-actual chart's own source file must also gate the
    build -- removing it must raise ReportSourceError naming it, not render a blank chart."""
    temp_summary = tmp_path / "summary"
    shutil.copytree(SUMMARY_DIR, temp_summary)
    os.remove(temp_summary / "report_item_forecast_vs_actual_by_origin.csv")

    monkeypatch.setattr(build_report, "SUMMARY_DIR", str(temp_summary))
    with pytest.raises(ReportSourceError, match="report_item_forecast_vs_actual_by_origin.csv"):
        build_report.render_page(load_config())


def test_embedded_json_matches_source_files_exactly():
    """Value-for-value: every number embedded in #report-data must equal a fresh, independent
    read of its own source file/column -- not merely be present or the right shape. This is the
    drift-prevention guarantee the report rework specifically asked for."""
    data = _embedded_data()

    notice_src = pd.read_csv(os.path.join(SUMMARY_DIR, "leadtime_notice_buckets_overall.csv"))
    assert data["notice"]["values"] == pytest.approx(list(notice_src["pct_of_orders"]))

    ontime_src = pd.read_csv(os.path.join(SUMMARY_DIR, "delivery_by_year.csv"))
    ontime_src = ontime_src[ontime_src["year"].isin([2023, 2024, 2025, 2026])].sort_values("year")
    assert data["ontime"]["years"] == list(int(y) for y in ontime_src["year"])
    assert data["ontime"]["values"] == pytest.approx(list(ontime_src["pct_on_time"]))

    model_src = pd.read_csv(os.path.join(SUMMARY_DIR, "focus_items_test_all.csv"))
    for model in ["Naive", "MA3", "MA6", "MA12", "Croston", "SBA", "Combination", "Top-down"]:
        for item in ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]:
            expected = model_src[(model_src["model"] == model) & (model_src["itemcode"] == item)]["MAE"].iloc[0]
            assert data["model_bar"][model][item] == pytest.approx(expected)

    div_src = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_per_division_summary_qty.csv"))
    div_lookup = {r["division"]: r for _, r in div_src.iterrows()}
    for row in data["per_division"]:
        expected = div_lookup[row["division"]]
        assert row["MAE"] == pytest.approx(expected["MAE"])
        assert row["MASE"] == pytest.approx(expected["MASE"])
        assert row["Bias"] == pytest.approx(expected["Bias"])
        assert row["n_items"] == int(expected["n_items"])

    rolling_src = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_rolling_origin_qty.csv"))
    rolling_type = rolling_src[rolling_src["level"] == "Type"]
    sample = rolling_type.sample(min(25, len(rolling_type)), random_state=0)
    for _, r in sample.iterrows():
        match = [x for x in data["rolling_origin"] if x["division"] == r["division"] and x["type"] == r["name"]
                  and x["model"] == r["model"] and x["origin"] == int(r["origin"])]
        assert len(match) == 1, f"No embedded rolling_origin row for {r['division']}/{r['name']}/{r['model']}/origin {r['origin']}"
        assert match[0]["MAE"] == pytest.approx(r["MAE"])

    fva_src = pd.read_csv(os.path.join(SUMMARY_DIR, "report_item_forecast_vs_actual_by_origin.csv"))
    fva_sample = fva_src.sample(min(30, len(fva_src)), random_state=0)
    for _, r in fva_sample.iterrows():
        match = [x for x in data["forecast_vs_actual"] if x["itemcode"] == r["itemcode"] and x["origin"] == int(r["origin"])
                  and x["month_in_horizon"] == int(r["month_in_horizon"])]
        assert len(match) == 1
        assert match[0]["actual_qty"] == pytest.approx(r["actual_qty"])
        if pd.notna(r["forecast_qty"]):
            assert match[0]["forecast_qty"] == pytest.approx(r["forecast_qty"])
        else:
            assert match[0]["forecast_qty"] is None

    scope_src = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv"))
    bucket_map = {
        "forecast": "forecast", "placeholder - pending method": "placeholder",
        "placeholder - method already assigned": "placeholder",
        "excluded - division excluded from forecasting (data volume)": "excluded",
        "excluded - listed but never sold, no plan-against basis": "excluded",
    }
    scope_src["bucket"] = scope_src["status_category"].map(bucket_map)
    expected_scope = pd.crosstab(scope_src["division"], scope_src["bucket"])
    for div, row in data["scope_table"].items():
        assert row["forecast"] == int(expected_scope.loc[div].get("forecast", 0))
        assert row["placeholder"] == int(expected_scope.loc[div].get("placeholder", 0))
        assert row["excluded"] == int(expected_scope.loc[div].get("excluded", 0))


def test_model_chart_includes_topdown_for_legend_toggle():
    """Part 2's legend-toggle control needs Top-down present alongside Combination and the six
    base models -- not just Combination (the previous report's chart omitted Top-down)."""
    data = _embedded_data()
    assert "Top-down" in data["model_bar"]
    assert "Combination" in data["model_bar"]
    for model in ["Naive", "MA3", "MA6", "MA12", "Croston", "SBA"]:
        assert model in data["model_bar"]


def test_forecast_vs_actual_uses_seven_origins_not_nine():
    """Root-cause fix check: the corrected chart's data must use the project's standard 7-origin
    scheme (get_origins(31, 6)), not the old 9-origin (get_origins(31, 4)) scheme."""
    data = _embedded_data()
    origins = sorted(set(r["origin"] for r in data["forecast_vs_actual"]))
    assert origins == [1, 2, 3, 4, 5, 6, 7], f"Expected 7 standard origins, got {origins}"


def test_forecast_vs_actual_has_both_forecast_and_actual():
    """The old chart plotted actual only. The rebuilt chart must carry both a real (non-null)
    forecast value and an actual value for the default focus items."""
    data = _embedded_data()
    focus_rows = [r for r in data["forecast_vs_actual"] if r["itemcode"] == "EEE-F-FC-1040010002"]
    assert len(focus_rows) > 0
    assert any(r["forecast_qty"] is not None for r in focus_rows)
    assert all(isinstance(r["actual_qty"], (int, float)) for r in focus_rows)


def test_plotly_loaded_from_pinned_cdn_url():
    with open(FORECAST_OUT, "r", encoding="utf-8") as f:
        html_text = f.read()
    assert "cdnjs.cloudflare.com/ajax/libs/plotly.js/" in html_text
    assert "@latest" not in html_text
    m = re.search(r"plotly\.js/([\d.]+)/plotly", html_text)
    assert m, "No pinned Plotly version found in the CDN script tag"


# ====================================================================================================== sections added on 2026-10-08
# Read from the tracked page (rebuilt by the monthly runner); the values are recomputed here from their sources.

def _tracked_sales_html() -> str:
    with open(FORECAST_OUT, "r", encoding="utf-8") as f:
        return f.read()


def _visible(html_text: str) -> str:
    import html as _html
    t = re.sub(r'<script type="application/json".*?</script>|<style.*?</style>|<script.*?</script>|<!--.*?-->', "", html_text, flags=re.S)
    return _html.unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "\n", t)))


def test_the_three_approved_lines_are_on_the_page_with_their_values_filled():
    import reader_values as rv
    h = _tracked_sales_html()
    vf = rv.vintage_facts()
    m = re.search(r'id="freshness-line">ยอดทายรอบ (.*?) · ใช้ยอดขายถึง (.*?) · หน้าสร้างเมื่อ (\d{1,2} \S+ \d{2} \d{2}:\d{2})</span>', h)
    assert m, "the freshness line is missing or not in the approved shape"
    assert m.group(1) == rv.thai_month_short(vf["run_date"]) and m.group(2) == rv.thai_month_short(vf["fit_last"])
    assert f'id="fit-range-line">ยอดขายที่ใช้ทาย {rv.thai_month_short(vf["fit_first"])} ถึง {rv.thai_month_short(vf["fit_last"])}</td>' in h
    first, last = rv.thai_month_short(vf["forecast_months"][0]), rv.thai_month_short(vf["forecast_months"][-1])
    assert f"<h2>2. ยอดทาย {first} ถึง {last}</h2>" in h
    scope = build_report.gather_scope_table()
    n = int(scope["placeholder"].sum() + scope["excluded"].sum())
    assert f'<p class="hint" id="forward-missing">รหัสที่ยังไม่มียอดทาย {n} รหัส ดูเหตุผลใน<a href="#scope">ตารางขอบเขตข้อมูล</a></p>' in h
    assert "ข้อมูลดึงเมื่อ:" not in h and "ช่วงข้อมูลที่ใช้ได้" not in h
    assert "ทุกต้นเดือนระบบเทียบยอดทายกับยอดขายจริงของเดือนที่ผ่านมา และเพิ่มผลในตารางนี้" in h
    assert "ทุกเดือนระบบจะเทียบการทายกับยอดขายจริงเดือนล่าสุด" not in h
    heads = re.findall(r"<h2>(\d)\. ", h)
    assert heads == [str(i) for i in range(1, 10)]                                    # the sections are numbered 1 to 9 without a gap


def test_every_approved_note_line_is_on_the_page_verbatim_and_no_brace_is_left():
    h = _tracked_sales_html()
    text = _visible(h)
    for line in ["▸ เดือนข้างหน้าสินค้าแต่ละประเภทน่าจะขายกี่ชิ้น", "▸ แถว = ประเภทสินค้า · คอลัมน์ = เดือน · ตัวเลข = จำนวนชิ้น", "▸ คลิกประเภทเพื่อดูรายรหัส",
                 "▸ เป็นค่ากลางค่าเดียว ยังไม่มีช่วงสูงต่ำ ดูว่าพลาดได้แค่ไหนจากส่วนผลลัพธ์",
                 "▸ สองกลุ่มนำร่องทายแม่นแค่ไหน", "▸ MAE = พลาดเฉลี่ยกี่ชิ้นต่อเดือน · Bias ติดลบ = ทายต่ำกว่าจริง",
                 "▸ ถ้าใช้ยอดทายของสองกลุ่มนี้วางแผน ให้ระวังว่ามักทายต่ำ", "Surge Arrester ในตารางนี้นับเฉพาะ Medium Voltage",
                 "▸ ยอดที่ทายไว้ล่วงหน้า พอถึงเดือนจริงพลาดแค่ไหน", "▸ MAE เดือนจริงสูงกว่าผลทดสอบย้อนหลังมาก = ช่วงนี้ทายยากกว่าปกติ",
                 "กลุ่มนำร่อง: Fuse Cutout และ Surge Arrester", "ยอดทายเทียบยอดขายจริง"]:
        assert line in text, line
    assert "{" not in text and "}" not in text, "a placeholder or a brace is left in the visible text of the sales report"


def _forward_rows(h: str) -> dict:
    """{division: {"types": {type: [cells]}, "items": {code: [cells]}}} from the forward forecast tables of the page."""
    import html as _html
    out = {}
    for d, body in re.findall(r'<table class="report-table fwd-table" id="fwd-table-(\w+)">.*?<tbody>(.*?)</tbody>', h, re.S):
        types, items = {}, {}
        for row in re.findall(r'<tr class="fwd-(?:type|item)".*?</tr>', body, re.S):
            cells = re.findall(r"<td>(.*?)</td>", row)
            label = _html.unescape(re.sub(r"<[^>]+>", "", cells[0].split(" <span")[0]))
            (types if 'class="fwd-type"' in row else items)[label] = cells[1:]
        out[d] = {"types": types, "items": items}
    return out


def test_the_forward_forecast_table_equals_the_vintage_the_min_max_page_and_the_operation_plan_use():
    import numpy as np
    import build_inventory_page_data as bd
    import operation_plan as op
    import reader_values as rv
    vf = rv.vintage_facts()
    rows = vf["item_rows"]
    h = _tracked_sales_html()
    page = _forward_rows(h)
    assert set(page) == set(rows["division"].unique())
    for d, g in rows.groupby("division"):
        # every item and month of the vintage, formatted as the page formats a cell; a Type is the sum of its items; no division total row
        by_item = g.pivot_table(index="itemcode", columns="target_month", values="forecast_qty", aggfunc="sum").reindex(columns=vf["forecast_months"])
        assert set(page[d]["items"]) == set(by_item.index)
        for code, vals in by_item.iterrows():
            assert page[d]["items"][code] == [build_report.fmt_cell(v) for v in vals], (d, code)
        by_type = g.pivot_table(index="type", columns="target_month", values="forecast_qty", aggfunc="sum").reindex(columns=vf["forecast_months"])
        assert set(page[d]["types"]) == set(by_type.index)
        for t, vals in by_type.iterrows():
            assert page[d]["types"][t] == [build_report.fmt_cell(v) for v in vals], (d, t)
    assert "total-row" not in re.search(r'<section id="forward-forecast">.*?</section>', h, re.S).group(0)
    # the same vintage as the Min-Max page (G2): its item arrays are the vintage's months, extended flat
    g2, info = bd.latest_vintage_item_forecasts()
    assert info["vintage_id"] == vf["vintage_id"] and info["target_months"] == vf["forecast_months"]
    for code, arr in g2.items():
        assert np.allclose(arr[:len(vf["forecast_months"])], vf["forecast"].loc[code, vf["forecast_months"]].to_numpy(dtype=float)), code
    # and the operation plan (G3): its forecast column for the plan's months is the vintage's value for the item and month
    cfg = op.load_config()
    im, _dm, meta = op.read_outputs(PROJECT_ROOT, cfg)
    assert meta["vintage_id"] == vf["vintage_id"]
    plan = im[im["status_category"] == "forecast"]
    for r in plan.itertuples():
        assert abs(r.forecast - vf["forecast"].loc[r.item, r.month]) < 1e-6, (r.item, r.month)


def test_bias_is_forecast_minus_actual_so_a_negative_bias_is_a_forecast_below_the_actual():
    import inspect
    import numpy as np
    import backtest_rekeyed as bk
    m = bk.compute_metrics(np.array([10.0]), np.array([7.0]), np.array([1.0, 2.0, 3.0, 4.0]))      # (actual, forecast, fit series): 3 units too low
    assert m["Bias"] == -3.0 and m["MAE"] == 3.0
    src = inspect.getsource(bk.compute_metrics)
    assert re.search(r"errors?\s*=\s*\w+\s*-\s*\w+", src), "compute_metrics no longer computes an error as one array minus another; re-check the sign of Bias"


def test_the_pilot_group_table_and_sentences_follow_the_pilot_view_data():
    import focus_item_model_selection as fims
    h = _tracked_sales_html()
    recorded = fims.read_pilot_view(os.path.join(SUMMARY_DIR, "pilot_view_data_v1.json"))["units"]       # hash-checked record of week 4
    fresh = fims.build_pilot_view_payload()["units"]
    cfg = load_config()["report"]
    for key, unit in (("fuse_cutout", "Drop-out Fuse Cutout"), ("surge_arrester", "Surge Arrester")):
        label = cfg["pilot_labels"][key]
        own = fresh[unit]["series_own"]
        assert own["MAE"] == pytest.approx(recorded[unit]["series_own"]["MAE"]) and own["Bias"] == pytest.approx(recorded[unit]["series_own"]["Bias"])
        assert f"<tr><td>{label}</td><td>{own['MAE']:.1f}</td><td>{own['Bias']:.1f}</td></tr>" in h
        if own["Bias"] < 0:
            assert f"▸ {label} ทายต่ำกว่าจริงเฉลี่ยเดือนละ {abs(own['Bias']):.1f} ชิ้น" in h
        else:
            assert f"▸ {label} ทายต่ำกว่าจริง" not in h
    if all(fresh[u]["series_own"]["Bias"] >= 0 for u in ("Drop-out Fuse Cutout", "Surge Arrester")):
        assert "ให้ระวังว่ามักทายต่ำ" not in h
    assert "Surge Arrester ในตารางนี้นับเฉพาะ Medium Voltage" in h


def test_the_forecast_versus_actual_table_follows_the_recorded_forward_test_scores():
    import forward_test_scoring as fts
    import reader_values as rv
    h = _tracked_sales_html()
    scores = pd.read_csv(fts.SCORES_PATH)
    s = scores[(scores["scope"] == "division") & (scores["horizon"] == 1)]
    back = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_per_division.csv"))
    back = back[back["approach"] == "Top-down"].set_index("division")["MAE"]
    table = re.search(r'<table class="report-table" id="scored-table">.*?<tbody>(.*?)</tbody>', h, re.S).group(1)
    rendered = re.findall(r"<tr><td>(\w+)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", table)
    assert len(rendered) == len(s) and len(s) > 0
    expected = {(r.key, rv.thai_month_short(r.target_month)): (f"{r.MAE:.1f}", f"{r.Bias:.1f}", f"{back[r.key]:.1f}") for r in s.itertuples()}
    assert {(d, m): (a, b, c) for d, m, a, b, c in rendered} == expected
    assert f"▸ ตอนนี้มีผล {s['target_month'].nunique()} เดือน ยังสรุปไม่ได้ว่าวิธีทายดีขึ้นหรือแย่ลง" in h
    assert "MAE ในการทดสอบย้อนหลัง" in h


def test_the_forward_table_has_a_division_selector_and_types_that_expand_to_items():
    h = _tracked_sales_html()
    sec = re.search(r'<section id="forward-forecast">.*?</section>', h, re.S).group(0)
    assert '<select id="fwdDivision">' in sec and sec.count('class="fwd-type"') > 5 and 'class="fwd-item"' in sec
    assert 'aria-expanded="false"' in sec and "(มีผลกับตารางนี้เท่านั้น)" in sec
    options = re.findall(r'<option value="\w+">', sec.split('id="fwdDivision"')[1].split("</select>")[0])
    assert sec.count('class="table-scroll fwd-table-wrap"') == len(options)
