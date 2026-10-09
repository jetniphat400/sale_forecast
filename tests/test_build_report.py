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
    m = re.search(r'id="freshness-line">Forecast \(ยอดทาย\) รันเมื่อ (.*?) · ใช้ยอดขายถึง (.*?) · หน้าสร้างเมื่อ (\d{1,2} \S+ \d{2} \d{2}:\d{2})</span>', h)
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
    # the pieces tables carry no division total row (the baht tables do: tested below)
    assert all("total-row" not in t for t in re.findall(r'<table class="report-table fwd-table" id="fwd-table-\w+">.*?</table>', h, re.S))
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
    rendered = re.findall(r"<tr><td>(\w+)</td><td>(.*?)</td><td>(.*?)</td><td>[^<]*</td><td>[^<]*</td><td>(.*?)</td><td>(.*?)</td><td>.*?</td><td>.*?</td><td>.*?</td></tr>", table)
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


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Baht view (Prompt 10, decisions of the user 2026-10-08): switch, baht tables, unit price, forecast-versus-actual baht columns.
# ---------------------------------------------------------------------------------------------------------------------------------------------

def _int(cell: str) -> int:
    return int(cell.replace(",", ""))


def _baht_tables(h: str) -> dict:
    """{division: {"types": {type: [int]}, "items": {code: [int or None]}, "total": (label, [int])}} from the baht tables of the page."""
    import html as _html
    out = {}
    for d, body in re.findall(r'<table class="report-table fwd-table" id="fwd-baht-table-(\w+)">.*?<tbody>(.*?)</tbody>', h, re.S):
        types, items, total = {}, {}, None
        for row in re.findall(r'<tr class="(?:fwd-btype|fwd-bitem|total-row)".*?</tr>', body, re.S):
            cells = re.findall(r"<td>(.*?)</td>", row)
            vals = [None if c == "-" else _int(c) for c in cells[1:]]
            label = _html.unescape(re.sub(r"<[^>]+>", "", cells[0].split(" <span")[0]))
            if 'class="total-row"' in row:
                total = (label, vals)
            elif 'class="fwd-btype"' in row:
                types[label] = vals
            else:
                items[label] = vals
        out[d] = {"types": types, "items": items, "total": total}
    return out


def _page_prices():
    import reader_values as rv
    cfg = load_config()["report"]
    vf = rv.vintage_facts()
    codes = sorted(vf["item_rows"]["itemcode"].unique())
    info = rv.unit_prices(codes, cfg["price_basis"], vf["fit_first"], vf["fit_last"], os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"), PROJECT_ROOT)
    return vf, info


def test_the_unit_switch_and_the_baht_texts_are_on_the_page_verbatim_and_default_to_pieces():
    import reader_values as rv
    h = _tracked_sales_html()
    sec = re.search(r'<section id="forward-forecast">.*?</section>', h, re.S).group(0)         # default: pieces (no data-unit set, the pieces button pressed)
    text = " ".join(_visible(sec).split())
    assert "หน่วย: ชิ้น · บาท (มีผลกับตารางในส่วนนี้เท่านั้น)" in text
    assert '<button type="button" data-unit="pieces" aria-pressed="true">ชิ้น</button>' in sec and 'data-unit="baht" aria-pressed="false">บาท</button>' in sec
    vf, info = _page_prices()
    first, last = rv.thai_month_short(info["recent"][0]), rv.thai_month_short(info["recent"][-1])
    n_market = sum(1 for p in info["prices"].values() if p["source"] == "market_price")
    label = f"มูลค่าคิดจากราคาขายเฉลี่ยจริงของแต่ละรหัส {first} ถึง {last}" + (f" · {n_market} รหัสที่ไม่เคยขายใช้ราคาตั้งใน Price List" if n_market else "")
    assert f'id="baht-label">{label}</p>' in sec
    assert ("▸ ยอดทายคิดเป็นเงินเท่าไหร่ต่อเดือน ▸ ตัวเลข = ยอดทาย (ชิ้น) × ราคาขายเฉลี่ยของรหัสนั้น หน่วยบาท ▸ ถ้าราคาขายข้างหน้าต่างจากช่วงที่ใช้เฉลี่ย ยอดเงินจะคลาดตาม "
            "▸ ยังไม่ได้ตรวจว่านับแบบเดียวกับเป้ารายได้ อย่าเพิ่งเทียบกับเป้าตรงๆ") in text
    assert "ยอดทายรวมรายเดือน (บาท)" in text and "รวมทุกฝ่าย" in text
    for d in _baht_tables(h):
        assert f"รวม {d}" in text
    # the window of the label is config's number of months, ending at the last month of the fit window
    assert len(info["recent"]) == load_config()["report"]["price_basis"]["window_months"] and info["recent"][-1] == vf["fit_last"]
    assert "{" not in text and "}" not in text


def test_the_price_rule_and_window_are_in_config_and_the_market_price_column_is_found_per_sheet_by_its_header():
    import openpyxl
    import reader_values as rv
    basis = load_config()["report"]["price_basis"]
    assert basis["window_months"] == 12 and basis["order"] == ["sales_recent_window", "sales_fit_window", "market_price", "none"]
    path = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")
    market, columns = rv.market_prices(path, basis)
    assert len(columns) == 6 and market                                                    # the six visible product sheets
    wb = openpyxl.load_workbook(path, data_only=True)
    for sheet, col in columns.items():                                                      # the header text and the label sit in the found column
        assert str(wb[sheet][f"{col}3"].value).startswith(basis["market_price_header"])
        assert str(wb[sheet][f"{col}{basis['market_price_label_row']}"].value).strip() == basis["market_price_label"]
    for code, m in list(market.items())[::7]:                                               # a sample of codes read straight from the cell
        v = wb[m["sheet"]][m["cell"]].value
        assert (m["price"] is None and not isinstance(v, (int, float))) or v == m["price"]


def test_every_unit_price_is_the_sale_over_qty_of_the_item_in_the_window_or_the_market_price():
    vf, info = _page_prices()
    raw = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "data", "raw_all_divisions_sales.csv"), usecols=["itemcode", "createDate", "forecast_date", "qty", "sale", "status", "revenue_type"])
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw = raw[raw["revenue_type"].eq("Omni Channel") & raw["status"].isin(["Actual", "MPS"]) & raw["forecast_date"].notna() & (raw["forecast_date"] >= raw["createDate"])]
    raw["ym"] = raw["forecast_date"].dt.to_period("M").astype(str)
    for code, pr in info["prices"].items():
        if pr["source"] in ("sales_recent_window", "sales_fit_window"):
            months = info["recent"] if pr["source"] == "sales_recent_window" else info["fit"]
            g = raw[(raw["itemcode"] == code) & raw["ym"].isin(months)]
            assert g["qty"].sum() > 0 and pr["price"] == pytest.approx(g["sale"].sum() / g["qty"].sum(), rel=1e-9), code
        elif pr["source"] == "market_price":
            assert pr["price"] == info["market"][code]["price"] and pr["price"] > 0
            assert raw[(raw["itemcode"] == code) & raw["ym"].isin(info["fit"])]["qty"].sum() <= 0      # never sold in the fit window
        else:
            assert pr["price"] is None


def test_every_baht_cell_is_units_times_price_and_the_totals_add_up_exactly():
    import build_report as br
    h = _tracked_sales_html()
    vf, info = _page_prices()
    page = _baht_tables(h)
    months = vf["forecast_months"]
    rows = vf["item_rows"]
    summary = {}
    for label, cells in re.findall(r'<tr(?: class="total-row")?><td>([^<]+)</td>((?:<td>[^<]*</td>)+)</tr>', re.search(r'id="baht-summary-table">.*?</table>', h, re.S).group(0)):
        summary[label] = [_int(c) for c in re.findall(r"<td>(.*?)</td>", cells)]
    assert set(page) == set(rows["division"].unique())
    grand = [0] * len(months)
    for d, g in rows.groupby("division"):
        units = g.pivot_table(index="itemcode", columns="target_month", values="forecast_qty", aggfunc="sum").reindex(columns=months)
        assert set(page[d]["items"]) == set(units.index)
        for code, vals in units.iterrows():
            price = info["prices"][code]["price"]
            assert page[d]["items"][code] == [br._baht(v, price) for v in vals], (d, code)       # whole baht of units x price
        for mi in range(len(months)):
            types_sum = sum(v[mi] for v in page[d]["types"].values())
            items_sum = sum(v[mi] for v in page[d]["items"].values() if v[mi] is not None)
            assert items_sum == types_sum == page[d]["total"][1][mi] == summary[d][mi], (d, months[mi])
        for t, codes in g.groupby("type")["itemcode"].unique().items():
            for mi in range(len(months)):
                assert page[d]["types"][t][mi] == sum(page[d]["items"][c][mi] for c in codes if page[d]["items"][c][mi] is not None), (d, t)
        assert page[d]["total"][0] == f"รวม {d}"
        grand = [a + b for a, b in zip(grand, page[d]["total"][1])]
    assert summary["รวมทุกฝ่าย"] == grand


def test_a_perturbed_price_changes_the_baht_values_and_a_missing_price_shows_the_line_and_the_list(tmp_path, monkeypatch):
    import reader_values as rv
    h0 = _tracked_sales_html()
    assert "baht-no-price" not in h0 and "ไม่มีทั้งประวัติขายและราคาใน Price List" not in h0              # n = 0 now: no line
    vf, info = _page_prices()
    page0 = _baht_tables(h0)
    d0 = next(iter(page0))
    positive = [c for c, v in page0[d0]["items"].items() if v[0] and v[0] > 1000]
    code_up, code_none = positive[0], positive[1]
    real = rv.unit_prices

    def perturbed(*a, **k):
        out = real(*a, **k)
        out["prices"][code_up] = {"price": out["prices"][code_up]["price"] * 2, "source": "sales_recent_window"}
        out["prices"][code_none] = {"price": None, "source": "none"}
        return out
    monkeypatch.setattr(rv, "unit_prices", perturbed)
    out = run_build_report(output_path=str(tmp_path / "sales_report.html"))
    h1 = open(out, encoding="utf-8").read()
    page1 = _baht_tables(h1)
    assert all(abs(b - 2 * a) <= 1 for a, b in zip(page0[d0]["items"][code_up], page1[d0]["items"][code_up]))
    assert page1[d0]["items"][code_none] == [None] * len(vf["forecast_months"])                            # shown as "-", left out of the sums
    assert page1[d0]["total"][1][0] == page0[d0]["total"][1][0] + (page1[d0]["items"][code_up][0] - page0[d0]["items"][code_up][0]) - page0[d0]["items"][code_none][0]
    sec = re.search(r'<details id="baht-no-price">.*?</details>', h1, re.S).group(0)
    assert '<summary class="hint">1 รหัสไม่มีทั้งประวัติขายและราคาใน Price List ไม่ได้รวมในยอดบาท</summary>' in sec
    assert "open" not in re.match(r"<details[^>]*>", sec).group(0)                                         # closed by default
    assert "<th>รหัส</th><th>ชื่อ</th><th>ฝ่าย</th>" in sec and f"<td>{code_none}</td>" in sec and f"<td>{d0}</td>" in sec
    assert "{" not in _visible(h1) and "}" not in _visible(h1)


def test_the_forecast_versus_actual_table_has_the_baht_columns_and_the_note_and_the_difference_has_the_sign_of_bias():
    import forward_test_common as ftc
    import forward_test_scoring as fts
    import operation_plan as op
    import build_report as br
    import reader_values as rv
    h = _tracked_sales_html()
    vf, info = _page_prices()
    head = re.search(r'<table class="report-table" id="scored-table"><thead><tr>(.*?)</tr>', h, re.S).group(1)
    assert head.endswith("<th>ยอดทาย (บาท)</th><th>ยอดจริง (บาท)</th><th>ต่าง (บาท)</th>")
    assert "ตัวเลขบาทคิดทั้งยอดทายและยอดจริงด้วยราคาขายเฉลี่ยเดียวกัน (ยอดจริงคือจำนวนที่ขายจริง × ราคาขายเฉลี่ย ไม่ใช่รายได้ตามบัญชี) เพื่อดูว่าทายจำนวนพลาดคิดเป็นเงินเท่าไหร่ ต่างติดลบ = ทายต่ำกว่าจริง" in " ".join(_visible(h).split())
    body = re.search(r'id="scored-table">.*?<tbody>(.*?)</tbody>', h, re.S).group(1)
    rows = re.findall(r"<tr><td>(\w+)</td><td>(.*?)</td><td>(.*?)</td><td>[^<]*</td><td>[^<]*</td><td>(.*?)</td><td>.*?</td><td>(-?[\d,]+)</td><td>(-?[\d,]+)</td><td>(-?[\d,]+)</td></tr>", body)
    assert rows
    cfg = op.load_config(PROJECT_ROOT)
    log = ftc.read_forward_test_log(op.path_of(PROJECT_ROOT, cfg["forecast_log_file"]))
    meta = ftc.load_metadata(op.path_of(PROJECT_ROOT, cfg["forecast_log_metadata_file"]))
    raw = pd.read_csv(fts.RAW_HISTORY_PATH, usecols=["itemcode", "createDate", "forecast_date", "qty"])
    scores = pd.read_csv(fts.SCORES_PATH)
    scores = scores[(scores["scope"] == "division") & (scores["horizon"] == 1)]
    for division, month, mae, bias, f_b, a_b, diff in rows:
        sc = scores[(scores["key"] == division) & (scores["target_month"].map(rv.thai_month_short) == month)].iloc[0]
        g = log[(log["level"] == "Item") & (log["vintage_id"] == sc["vintage_id"]) & (log["target_month"] == sc["target_month"]) & (log["horizon"] == 1) & (log["division"] == division)].copy()
        g["actual_qty"] = pd.to_numeric(g["actual_qty"])
        vm = meta[str(int(sc["vintage_id"]))]
        used = set(fts.score_items(g, fts.fit_series_from_raw(raw, g["itemcode"].unique(), vm["fit_first_month"], vm["fit_last_month"]))["itemcode"])
        g = g[g["itemcode"].isin(used)]
        assert len(g) == sc["n_items"]                                                       # the very items of the row's MAE
        f_exp = sum(br._baht(f, info["prices"][c]["price"]) for c, f in zip(g["itemcode"], g["forecast_qty"]))
        a_exp = sum(br._baht(a, info["prices"][c]["price"]) for c, a in zip(g["itemcode"], g["actual_qty"]))
        assert (_int(f_b), _int(a_b), _int(diff)) == (f_exp, a_exp, f_exp - a_exp), (division, month)   # difference = forecast minus actual
        assert (g["forecast_qty"] - g["actual_qty"]).mean() == pytest.approx(sc["Bias"])      # the Bias of the row is the same forecast-minus-actual


def test_the_back_check_of_the_unit_prices_is_inside_its_limits_and_a_value_outside_them_stops_the_build(tmp_path, monkeypatch):
    import reader_values as rv
    basis = load_config()["report"]["price_basis"]
    vf, info = _page_prices()
    back = rv.price_back_check(info, basis, PROJECT_ROOT)
    assert back["outside"] == [] and set(back["ratios"]) == set(vf["item_rows"]["division"].unique())
    # direct recomputation for one division and year from the two saved series
    sale = pd.read_csv(os.path.join(PROJECT_ROOT, basis["sale_file"]))
    qty = pd.read_csv(os.path.join(PROJECT_ROOT, basis["qty_file"]))
    d = sale.merge(qty[["itemcode", "year_month", "qty"]], on=["itemcode", "year_month"])
    d = d[(d["division"] == "PEM101") & d["year_month"].str.startswith("2025")]
    value = sum(q * info["prices"][c]["price"] for c, q in zip(d["itemcode"], d["qty"]) if info["prices"][c]["price"] is not None)
    assert back["ratios"]["PEM101"]["2025"] == pytest.approx(value / d["sale"].sum())
    # inside the price window the ratio is 1 for the items priced from that window
    w = d.iloc[0:0]
    full = sale.merge(qty[["itemcode", "year_month", "qty"]], on=["itemcode", "year_month"])
    full = full[full["year_month"].isin(info["recent"]) & full["itemcode"].map(lambda c: info["prices"][c]["source"] == "sales_recent_window")]
    assert sum(q * info["prices"][c]["price"] for c, q in zip(full["itemcode"], full["qty"])) == pytest.approx(full["sale"].sum())
    monkeypatch.setattr(rv, "price_back_check", lambda *a, **k: {"ratios": {}, "outside": [("PEM101", "2025", 1.7)]})
    with pytest.raises(ReportSourceError, match="not published"):
        run_build_report(output_path=str(tmp_path / "sales_report.html"))


def test_the_flat_forecast_line_is_on_the_page_only_when_every_item_has_one_value_for_all_months(tmp_path, monkeypatch):
    import reader_values as rv
    line = "ยอดทายทุกเดือนเท่ากัน เพราะวิธีทายตอนนี้ให้ค่าระดับเดียวกับทุกเดือนข้างหน้า ยังไม่คิดช่วงขายดีขายน้อยตามฤดูกาล"
    vf = rv.vintage_facts()
    rows = vf["item_rows"]
    assert (rows.groupby("itemcode")["forecast_qty"].nunique() == 1).all()                               # the VERIFY, from the log itself
    h = _tracked_sales_html()
    sec = re.search(r'<section id="forward-forecast">.*?</section>', h, re.S).group(0)
    assert f'id="flat-forecast-line">' in sec and line in " ".join(_visible(sec).split())
    assert sec.index("flat-forecast-line") > sec.rindex("fwd-baht-wrap")                                 # under the tables, outside both unit views
    # a vintage with an item that differs between months: the line is not added
    real = build_report.gather_forward_forecast

    def not_flat(*a, **k):
        out = real(*a, **k)
        d = next(iter(out["divisions"]))
        out["divisions"][d][0]["items"][0]["values"][1] += 1.0
        return out
    monkeypatch.setattr(build_report, "gather_forward_forecast", not_flat)
    out = run_build_report(output_path=str(tmp_path / "sales_report.html"))
    assert "flat-forecast-line" not in open(out, encoding="utf-8").read()


# ---------------------------------------------------------------------------------------------------------------------------------------------
# Prompt 12: Relative MAE against Naive, Horizon 3, Tracking Signal, the draft verdicts (METRICS.md Sec.48)
# ---------------------------------------------------------------------------------------------------------------------------------------------

def test_naive_is_the_last_month_before_the_origin_for_every_horizon_on_a_fixed_example():
    import numpy as np
    import transferability_all_divisions as ta
    qty = np.array([(i % 5) + 1 for i in range(ta.TOTAL_MONTHS)], dtype=float)                     # 1,2,3,4,5,1,2,...
    months = [str(p) for p in pd.period_range("2024-01", periods=ta.TOTAL_MONTHS, freq="M")]
    item_series = {"X-1": (qty, months, "D::T", "D", "C")}
    cells = ta.topdown_naive_cells(item_series, {"D::T": (qty, months)}, "2027-01-01", 0)
    assert [c["train_size"] for c in cells] == ta.get_origins(ta.TOTAL_MONTHS, ta.HOLDOUT) and len(cells) == 7
    for c in cells:
        assert list(c["nv"]) == [qty[c["train_size"] - 1]] * ta.HOLDOUT                              # last observed month before the origin, all six horizons
        assert list(c["act"]) == list(qty[c["train_size"]:c["train_size"] + ta.HOLDOUT])
    # a one-cell example with known errors: model errors 1,1,2,.. against Naive errors 2,2,2,..
    cell = {"fc": np.array([4.0, 4.0, 4.0, 4.0, 4.0, 4.0]), "nv": np.array([6.0] * 6), "act": np.array([5.0, 5.0, 6.0, 5.0, 5.0, 5.0])}
    r = ta.relative_mae([cell])
    assert r["mae"] == pytest.approx((1 + 1 + 2 + 1 + 1 + 1) / 6) and r["mae_naive"] == pytest.approx((1 + 1 + 0 + 1 + 1 + 1) / 6)
    assert ta.relative_mae([cell], 3)["relative_mae"] is None                                              # Naive exact at horizon 3: undefined, not infinite
    assert ta.relative_mae([cell], 1)["relative_mae"] == pytest.approx(1.0)
    two = ta.relative_mae([cell, {"fc": np.array([1.0] * 6), "nv": np.array([3.0] * 6), "act": np.array([2.0] * 6)}])
    assert two["n_cells"] == 2 and two["relative_mae"] == pytest.approx((7 / 6 + 1) / (5 / 6 + 1))   # the ratio of the sums over the cells


def test_tracking_signal_on_a_fixed_example():
    import transferability_all_divisions as ta
    assert ta.tracking_signal([2, -1, 3]) == {"n_points": 3, "tracking_signal": pytest.approx(4 / 2)}   # sum 4, mean |e| 2
    assert ta.tracking_signal([-3, -3, -3, -3])["tracking_signal"] == pytest.approx(-4.0)              # always below the actual: -n
    assert ta.tracking_signal([1, -1, 1, -1])["tracking_signal"] == 0
    assert ta.tracking_signal([0, 0])["tracking_signal"] is None and ta.tracking_signal([])["n_points"] == 0


def test_verdicts_follow_the_thresholds_and_a_perturbed_threshold_changes_a_verdict():
    assert [build_report.verdict_relative(v, 0.7, 1.0) for v in (0.5, 0.7, 0.99, 1.0, 1.3, None)] == ["ดี", "ผ่าน", "ผ่าน", "ไม่ผ่าน", "ไม่ผ่าน", "-"]
    assert [build_report.verdict_tracking(v, 4.0) for v in (3.9, 4.0, -4.1, 6.7, None)] == ["ปกติ", "ปกติ", "เตือน", "เตือน", "-"]
    assert build_report.verdict_relative(0.8, 0.7, 1.0) == "ผ่าน" and build_report.verdict_relative(0.8, 0.7, 0.75) == "ไม่ผ่าน"      # a changed pass threshold changes the verdict
    assert build_report.verdict_tracking(5.0, 4.0) == "เตือน" and build_report.verdict_tracking(5.0, 6.0) == "ปกติ"


def _criteria_rows(h: str) -> list:
    import html as _html
    table = re.search(r'<table class="report-table" id="criteria-table">.*?<tbody>(.*?)</tbody>', h, re.S).group(1)
    return [[_html.unescape(c) for c in re.findall(r"<td>(.*?)</td>", r)] for r in re.findall(r"<tr>(.*?)</tr>", table, re.S)]


def test_the_criteria_block_is_verbatim_has_every_division_and_group_and_reads_its_thresholds_from_config(tmp_path, monkeypatch):
    import reader_values as rv
    h = _tracked_sales_html()
    import reader_values as rv
    cfg = load_config()
    crit = cfg["maxmin_v1"]["pending_criteria_values"]
    text = " ".join(_visible(re.search(r'<section id="results">.*?</section>', h, re.S).group(0)).split())
    assert "เทียบกับร่างเกณฑ์" in text
    head = re.search(r'<table class="report-table" id="criteria-table"><thead><tr>(.*?)</tr>', h, re.S).group(1)
    assert re.findall(r"<th>(.*?)</th>", head) == ["ฝ่าย / กลุ่ม", "Relative MAE", "ผล", "Relative MAE (Horizon 3)", "ผล", "Tracking Signal", "ผล"]
    lines = ["▸ วิธีทายของเราดีกว่าวิธี Naive (ใช้ยอดเดือนที่แล้วเป็นค่าทาย) ไหม",
             f"▸ Relative MAE = MAE ของเรา ÷ MAE ของ Naive ในเดือนทดสอบเดียวกัน ต่ำกว่า {crit['relative_mae_pass']:g} = ต่ำกว่า Naive ในการทดสอบนี้ (ถึงเกณฑ์ผ่านของร่าง) · ต่ำกว่า {crit['relative_mae_good']:g} = ถึงเกณฑ์ดีของร่าง",
             "▸ Horizon 3 = ทายล่วงหน้า 3 เดือน ใช้ดูความแม่นในช่วงที่ต้องสั่งวัตถุดิบล่วงหน้า",
             f"▸ Tracking Signal = ความคลาดสะสม ÷ ความคลาดเฉลี่ย บอกว่าทายเอียงไปทางเดียวต่อเนื่องไหม เกิน ±{crit['tracking_signal_limit']:g} = เตือน",
             f"▸ ถึงเกณฑ์ร่าง ยังไม่ได้แปลว่าพิสูจน์แล้วว่าดีกว่า Naive: ผลมาจากการทดสอบย้อนหลังเพียง {rv.backtest_rounds(cfg)} รอบ ดูว่าฝ่ายไหนต่างจาก Naive จริงในหัวข้อ \"ใช้วิธี Top-down ดีกว่าวิธีอื่นไหม\"",
             f"▸ เกณฑ์เป็นร่าง ผู้บริหารยืนยันหลังรอบ {rv.thai_date_short(crit['decision_date'])}"]
    block = re.search(r'<h3 id="criteria-vs-draft">.*?</table>', h, re.S).group(0)
    assert "<br>".join(lines) in re.sub(r"<!--.*?-->", "", block, flags=re.S).replace("&lt;", "<").replace("&quot;", '"')
    rows = _criteria_rows(h)
    assert [r[0] for r in rows] == [d for d in ["PEM101", "PEM103", "PEM107", "PEM102", "CI101"]] + ["Fuse Cutout", "Surge Arrester"]
    for r in rows:
        words = cfg["report"]["verdict_words"]
        inverse = {v: k for k, v in words.items()}
        assert r[2] in inverse and r[4] in inverse and r[6] in ("ปกติ", "เตือน")
        for value, verdict in ((r[1], r[2]), (r[3], r[4])):
            if min(abs(float(value) - 1.0), abs(float(value) - 0.7)) > 0.006:                                 # away from a threshold at the page's rounding
                assert inverse[verdict] == build_report.verdict_relative(float(value), 0.7, 1.0), r
    # the model MAE behind Relative MAE is the main table's MAE, for every division (the build stops otherwise)
    primary = build_report.gather_primary_results()
    acc = build_report.gather_accuracy_vs_naive(cfg, primary)
    main = primary.set_index("division")
    for r in acc["rows"]:
        if r["kind"] == "division":
            assert r["mae"] == pytest.approx(float(main.loc[r["label"], "MAE"]), abs=1e-9) and r["n_cells"] == int(main.loc[r["label"], "n_scored"])
    # a changed threshold in config changes the page: pass 0.5 turns PEM101 (Relative MAE 0.8) into ไม่ผ่าน and the notes show 0.5
    changed = load_config()
    changed["maxmin_v1"]["pending_criteria_values"].update({"relative_mae_pass": 0.5, "relative_mae_good": 0.3, "tracking_signal_limit": 9})
    monkeypatch.setattr(build_report, "load_config", lambda: changed)
    out = run_build_report(output_path=str(tmp_path / "sales_report.html"))
    h2 = open(out, encoding="utf-8").read()
    r2 = {r[0]: r for r in _criteria_rows(h2)}
    assert r2["PEM101"][2] == cfg["report"]["verdict_words"]["ไม่ผ่าน"] and r2["CI101"][6] == "ปกติ"                                         # |TS| 6.7 is inside the widened limit
    assert "ต่ำกว่า 0.5 = ต่ำกว่า Naive ในการทดสอบนี้ (ถึงเกณฑ์ผ่านของร่าง) · ต่ำกว่า 0.3 = ถึงเกณฑ์ดีของร่าง" in _visible(h2) and "เกิน ±9 = เตือน" in _visible(h2)
    assert "{" not in _visible(h2) and "}" not in _visible(h2)


def test_the_forecast_versus_actual_table_has_the_naive_columns_after_mae_and_they_follow_the_forward_test_log():
    import forward_test_common as ftc
    import forward_test_scoring as fts
    import operation_plan as op
    import reader_values as rv
    h = _tracked_sales_html()
    head = re.findall(r"<th>(.*?)</th>", re.search(r'<table class="report-table" id="scored-table"><thead><tr>(.*?)</tr>', h, re.S).group(1))
    assert head[:5] == ["ฝ่าย", "เดือน", "MAE", "MAE (Naive)", "Relative MAE"]
    cfg = op.load_config(PROJECT_ROOT)
    log = ftc.read_forward_test_log(op.path_of(PROJECT_ROOT, cfg["forecast_log_file"]))
    meta = ftc.load_metadata(op.path_of(PROJECT_ROOT, cfg["forecast_log_metadata_file"]))
    raw = pd.read_csv(fts.RAW_HISTORY_PATH, usecols=["itemcode", "createDate", "forecast_date", "qty"])
    items = fts.forward_naive_items(log, meta, raw)
    body = re.search(r'id="scored-table">.*?<tbody>(.*?)</tbody>', h, re.S).group(1)
    rows = re.findall(r"<tr><td>(\w+)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>", body)
    assert rows
    for division, month, mae, naive, rel in rows:
        g = items[(items["division"] == division) & (items["target_month"].map(rv.thai_month_short) == month)]
        assert len(g) > 0
        assert f"{g['e_model'].abs().mean():.1f}" == mae and f"{g['e_naive'].abs().mean():.1f}" == naive               # same items: MAE and MAE (Naive) are means of |e|
        assert f"{g['e_model'].abs().sum() / g['e_naive'].abs().sum():.2f}" == rel
        # Naive of an item = the quantity of the last month of the vintage's fit window; e = naive - actual
        vm = meta[str(int(g["vintage_id"].iloc[0]))]
        one = g.iloc[0]
        series = fts.fit_series_from_raw(raw, [one["itemcode"]], vm["fit_first_month"], vm["fit_last_month"])
        assert one["naive"] == series[one["itemcode"]][-1] and one["e_naive"] == one["naive"] - one["actual"]


def test_the_trend_note_and_the_chart_caption_carry_no_typed_month():
    text = open(os.path.join(PROJECT_ROOT, "index.html"), encoding="utf-8").read()
    for typed in ("เดือน ส.ค. 2026 ยังไม่จบเดือน", "ม.ค. 2024 – ก.ค. 2026", "ตรวจสอบแล้ว (2026-09-24)"):
        assert typed not in text, typed
    assert 'class="omni-month-incomplete"' in text and 'class="omni-base-first"' in text and "ตรวจสอบแล้ว (' + OMNI.meta.pull + '): ไม่มีรหัสสินค้า" in text
