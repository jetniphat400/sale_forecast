"""Tests for task 2a's Part 2 (page timestamps), Part 4 (no hand-maintained display dates,
MASE_undefined rendering) and Part 5 (stock panel Reserved source) requirements.

Per this project's DATABASE ACCESS rule, tests never open a new database connection or
re-run the pipeline themselves -- they check committed files and static source code, which is
enough to catch a regression (a future edit reverting to a hand-typed date, or to Cube_Backlog)
without costing another connection attempt every time the suite runs.
"""
import hashlib
import sys
import json
import os
import re

import pandas as pd
import pytest

import build_report
import build_inventory_dataset
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
FORWARD_TEST_LOG = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions.csv")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")

INDEX_HTML = os.path.join(PROJECT_ROOT, "index.html")
SALES_REPORT_HTML = os.path.join(PROJECT_ROOT, "forecast", "sales_report.html")
INVENTORY_HTML = os.path.join(PROJECT_ROOT, "forecast", "inventory.html")

# Recorded 2026-09-25 (task 2a, Part 1), immediately after running src/run_pipeline.py end to
# end and confirming the hash was unchanged before/after. CONVENTIONS.md/METRICS.md Sec.26: "The
# forward-test log is never refreshed or rewritten; it keeps the cutoff it was generated at" --
# this hash is therefore a project invariant, not a snapshot that is expected to need updating.
#
# UPDATED 2026-09-25 (forward test / monthly refresh task, Part 1.2): this is now the hash AFTER
# the one-time vintage_id schema migration (src/migrate_forward_test_vintage.py) -- METRICS.md
# Sec.27's `vintage_id` column was added (existing rows become vintage 1); every pre-existing
# column's value was verified unchanged, value-for-value, against an archived pre-migration copy
# (output/summary/archive/forward_test_log_all_divisions_pre_vintage_migration_2026-09-25.csv,
# whose own SHA-256, 3adb765139b576c508a93bf0e21b3562d48711d4d04b002800eb5c55e7576a04, IS the
# previous value of this constant -- confirming the migration's input was exactly the frozen file
# this test previously checked). A schema migration is a deliberate, one-time, reported change to
# this "frozen" file, not the ordinary "refreshed or rewritten" this rule forbids -- the row
# CONTENT (forecast_qty et al.) is unchanged; only the new vintage_id column was added. Any FUTURE
# change to this hash (other than another explicit, reported migration) must still be treated as
# a regression.
FROZEN_FORWARD_TEST_LOG_SHA256 = (
    "7ba4a3a45a975e04a52935d62036995e1c02db93d52fc9c24e8028d3182dfa2c"
)


# ---------------------------------------------------------------------------------------------
# (1) forward-test log is unchanged by a pipeline refresh
# ---------------------------------------------------------------------------------------------

# UPDATED 2026-10-02 (task C2b): the log is no longer one frozen file. METRICS.md Sec.27/28 have the monthly run APPEND a
# vintage each month (vintage 2 was appended on 2026-10-02), so the whole-file hash above (kept for the record) can no longer
# be the invariant. What stays frozen is every vintage's own forecast rows: vintage 1's rows (all columns except
# actual_qty, the one column allowed to be filled in later) must still hash to the value recorded at the 2026-09-25
# migration. Read back from the file, under the read-back scheme vintage 1's metadata uses.
FROZEN_VINTAGE_1_ROW_HASH = "160eefcd8bf45a61f7a1a0b3e9c08faadb5564ad601eec53e9205ebf5ef0d8f3"


def test_vintage_1_rows_in_the_forward_test_log_are_unchanged():
    """Vintage 1 is never rewritten (METRICS.md Sec.26/27). Later vintages are appended; actual_qty may be filled."""
    assert os.path.exists(FORWARD_TEST_LOG), (
        f"{FORWARD_TEST_LOG} does not exist -- cannot verify the forward-test log is frozen."
    )
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
    from forward_test_common import HASH_SCHEME_CSV_READBACK, compute_row_integrity_hash, read_forward_test_log
    log = read_forward_test_log(FORWARD_TEST_LOG)
    vintage_1 = log[log["vintage_id"] == 1]
    assert len(vintage_1) == 2340
    assert compute_row_integrity_hash(vintage_1, HASH_SCHEME_CSV_READBACK) == FROZEN_VINTAGE_1_ROW_HASH, (
        "vintage 1's rows in forward_test_log_all_divisions.csv have changed since the 2026-09-25 migration "
        "-- METRICS.md Sec.26 says a vintage must never be refreshed or rewritten."
    )


# ---------------------------------------------------------------------------------------------
# (2) each page renders data_pulled_at and page_built_at
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path,label", [
    (INDEX_HTML, "index.html"),
    (SALES_REPORT_HTML, "forecast/sales_report.html"),
    (INVENTORY_HTML, "forecast/inventory.html"),
])
def test_page_shows_data_pulled_at_and_page_built_at(path, label):
    assert os.path.exists(path), f"{path} does not exist"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    assert "data_pulled_at" in text, f"{label} has no data_pulled_at marker"
    assert "page_built_at" in text, f"{label} has no page_built_at marker"


def test_inventory_html_also_shows_model_calibrated_at():
    with open(INVENTORY_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    assert "model_calibrated_at" in text


# ---------------------------------------------------------------------------------------------
# (3) no displayed date is read from a hand-maintained config value
# ---------------------------------------------------------------------------------------------

def test_date_range_end_key_no_longer_exists_in_config():
    """config.yaml's date_range.end was the specific hand-maintained value STATUS.md Sec.10 item
    3 / manual_factsheet.md Part 5 item 3 found stale. Its removal is the checkable condition:
    if a future edit reintroduces it, this test fails, prompting a check of whether it is being
    read for display again."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert "end" not in config["date_range"], (
        "config.yaml's date_range.end has reappeared -- confirm nothing reads it for DISPLAY "
        "purposes (src/build_report.py's 'Usable range' row must derive its end date from "
        "output/data/processed_full_category_sales_monthly_forecastDate.csv's own year_month "
        "max, never from this config value)."
    )


def test_build_report_source_never_reads_date_range_end():
    """Static check on the generator's own source: build_report.py must not contain the literal
    dotted-path read `date_range']['end` (in any quoting style) anywhere -- this is the concrete,
    checkable condition for 'the display path no longer reads a hand-maintained config value',
    independent of whether the key still happens to exist in config.yaml."""
    src_path = os.path.join(PROJECT_ROOT, "src", "build_report.py")
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert "date_range']['end" not in src.replace('"', "'")


def test_the_data_range_line_follows_the_fit_window_of_the_latest_vintage_not_a_literal():
    """The line "ยอดขายที่ใช้คำนวณ Forecast {เดือนแรก} ถึง {เดือนสุดท้าย}" (it replaced the old 'Usable range' row, whose end came from the 128-item pilot file) is the
    fit window of the latest vintage of the forward-test log, in the shared month format; no 'Usable range' row and no typed end date is left on the page."""
    import reader_values as rv
    with open(SALES_REPORT_HTML, "r", encoding="utf-8") as f:
        html_text = f.read()
    assert "Usable range" not in html_text and "2024-01-01" not in re.sub(r"<script.*?</script>", "", html_text, flags=re.S)
    m = re.search(r'id="fit-range-line">(.*?)</td>', html_text)
    assert m, "the fit range line is not on forecast/sales_report.html"
    vf = rv.vintage_facts()
    assert m.group(1) == f"ยอดขายที่ใช้คำนวณ Forecast {rv.thai_month_short(vf['fit_first'])} ถึง {rv.thai_month_short(vf['fit_last'])}"


# ---------------------------------------------------------------------------------------------
# (4) stock panel's Reserved reads Cube_CES, not Cube_Backlog
# ---------------------------------------------------------------------------------------------

def test_reserved_source_is_cube_ces_not_cube_backlog():
    """Static source check: the WRITTEN Reserved figure must come from
    query_backlog_ces()/dedup_and_aggregate_ces_backlog() (Cube_CES). The old Cube_Backlog
    functions (query_backlog, aggregate_backlog) were removed on 2026-10-14 (Prompt 27)."""
    src_path = os.path.join(PROJECT_ROOT, "src", "build_inventory_dataset.py")
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert "def query_backlog_ces" in src
    assert "def dedup_and_aggregate_ces_backlog" in src
    # The call that feeds add_backlog_and_available (the one that ends up in the JSON) must use
    # the new function's result, not the old one.
    m = re.search(r"backlog_per_code, backlog_detail = dedup_and_aggregate_ces_backlog\(([^)]*)\)", src)
    assert m, "add_backlog_and_available's input is no longer built from dedup_and_aggregate_ces_backlog()"


def test_inventory_json_backlog_source_table_is_cube_ces():
    """Data-level check on the committed data/inventory.json: its backlog.source_table must
    name Cube_CES, and status_filter must be 'Backlog' -- the actual written artifact, not just
    the generator's source code."""
    path = os.path.join(PROJECT_ROOT, "data", "inventory.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "Cube_CES" in data["backlog"]["source_table"]
    assert "Cube_Backlog" not in data["backlog"]["source_table"]
    assert data["backlog"]["status_filter"] == "Backlog"


# ---------------------------------------------------------------------------------------------
# (5) MASE_undefined renders instead of NaN
# ---------------------------------------------------------------------------------------------

def test_the_mase_column_is_not_shown_on_the_sales_report_and_the_page_says_why():
    """Prompt 51 (decision 7): MASE is removed from both tables of the page; the recorded files keep it."""
    with open(SALES_REPORT_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    assert "function fmtMase" not in text and "<th>MASE" not in text and "MASE_undefined" not in text
    assert "ถอด MASE ออกจากหน้านี้ เพราะวัดเทียบกับความคลาดของ Naive ในข้อมูลที่ใช้คำนวณ Forecast ซึ่งอ่านขัดกับ Relative MAE · ใช้ Relative MAE แทน" in text


def test_embedded_json_never_contains_literal_nan_for_mase(tmp_path):
    """Builds the report fresh and inspects the embedded #report-data JSON text directly (not
    just the parsed dict, since Python's json.dumps would happily emit the bare token `NaN`,
    which is invalid JSON and would crash the browser's JSON.parse) -- confirms
    embed_report_data()'s None-for-NaN conversion actually reaches the serialized page.

    FIXED (forward test / monthly refresh task): previously called build_report.build_report()
    with no override, writing to the real tracked forecast/sales_report.html on every test run
    (the SECOND such test found this task, alongside test_build_report.py's -- a repo-wide search
    for every build_report()/build_inventory_page()-style call with no override found only these
    two). Now passes tmp_path -- the real tracked file is never touched by running the suite."""
    out_path = build_report.build_report(output_path=os.path.join(str(tmp_path), "sales_report.html"))
    with open(out_path, "r", encoding="utf-8") as f:
        html_text = f.read()
    m = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html_text, re.DOTALL)
    assert m
    report_json_text = m.group(1)
    assert re.search(r":\s*NaN\b", report_json_text) is None, (
        "Embedded report-data JSON contains a literal NaN token -- MASE (or another metric) is "
        "not being converted to None before json.dumps."
    )
    # And it must still be valid JSON (a literal NaN token would parse under Python's lenient
    # json.loads too, so re-parsing alone would not have caught the bug above).
    json.loads(report_json_text)


# ---------------------------------------------------------------------------------------------
# (6) per-section data_pulled_at is read from a recorded pull time, never a file mtime (2cfix2)
# ---------------------------------------------------------------------------------------------

def test_build_report_gather_freshness_never_uses_file_mtime():
    """Static source check (task 2cfix2, Part 3): gather_freshness() must never read a source
    file's modification time (os.path.getmtime) for any per-section data_pulled_at value -- every
    section must be read from a recorded snapshot_pull_date column instead. A prior version of
    this function used os.path.getmtime for 6 sections (STATUS.md Sec.10/12, task 2cfix's own
    Validator finding a real staged-vs-tracked timing gap this caused)."""
    src_path = os.path.join(PROJECT_ROOT, "src", "build_report.py")
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"def gather_freshness\(\).*?(?=\ndef )", src, re.DOTALL)
    assert m, "gather_freshness() not found in src/build_report.py"
    body = m.group(0)
    assert "os.path.getmtime(" not in body, (
        "gather_freshness() calls os.path.getmtime -- a displayed data_pulled_at section would "
        "be read from a file modification time instead of a recorded pull time (METRICS.md "
        "Sec.26 requires the latter)."
    )
    # Belt-and-braces: the whole file must contain no getmtime CALL at all (the function this
    # project used to route through for exactly this purpose, _file_mtime_str, is gone entirely;
    # this checks the actual call pattern, not the bare word, since this file's own comments now
    # document that history and legitimately mention the word).
    assert "os.path.getmtime(" not in src, "src/build_report.py still calls os.path.getmtime somewhere."
    assert "_file_mtime_str" not in src


def test_all_six_previously_mtime_based_sources_have_snapshot_pull_date_column():
    """Data-level check on the 6 committed source files STATUS.md/this task's brief named as
    file-mtime-based ('... -- file mtime' labels): each must now carry a real snapshot_pull_date
    column build_report.py can read (src/build_report.py's _source_pull_date()), not merely be
    fixed in the generator's source without the column actually landing in the committed file."""
    six_files = [
        "phaseC_step2_per_division_summary_qty.csv",
        "phaseC_step2_rolling_origin_qty.csv",
        "leadtime_notice_buckets_overall.csv",
        "focus_items_test_all.csv",
        "delivery_by_year.csv",
        "delivery_not_late_by_year.csv",
    ]
    for rel_path in six_files:
        path = os.path.join(SUMMARY_DIR, rel_path)
        assert os.path.exists(path), f"{path} does not exist"
        df = pd.read_csv(path, nrows=1)
        assert "snapshot_pull_date" in df.columns, (
            f"{rel_path} has no snapshot_pull_date column -- re-run its generating script "
            f"(task 2cfix2, Part 3)."
        )


def test_rendered_freshness_table_never_shows_file_mtime_label(tmp_path):
    """Behavioural check: a freshly built report's rendered freshness table must not contain the
    literal '-- file mtime' label any of the 6 sections used to show (task 2cfix2, Part 3).
    Writes to tmp_path, never the tracked page (METRICS.md Sec.28: tests must not modify tracked
    output files)."""
    out_path = build_report.build_report(output_path=os.path.join(str(tmp_path), "sales_report.html"))
    with open(out_path, "r", encoding="utf-8") as f:
        html_text = f.read()
    assert "file mtime" not in html_text, (
        "Rendered report still shows a '-- file mtime' freshness label -- a section is still "
        "reading a file modification time instead of a recorded pull time."
    )


def test_mase_or_undefined_converts_nan_to_none():
    df = pd.DataFrame({"division": ["X"], "MAE": [1.0], "RMSE": [1.0], "Bias": [0.0],
                        "MASE": [float("nan")], "n_scored": [5]})
    records = [
        {"division": r["division"], "MAE": float(r["MAE"]), "RMSE": float(r["RMSE"]),
         "Bias": float(r["Bias"]),
         "MASE": (None if pd.isna(r["MASE"]) else float(r["MASE"])),
         "n_scored": int(r["n_scored"])}
        for _, r in df.iterrows()
    ]
    assert records[0]["MASE"] is None


# ------------------------------------------------------------------ Prompt 29: freshness by pull cadence (config page_timestamps, METRICS.md Sec.26)
def _cfg():
    import yaml
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("today,pulled,old", [
    ("2026-10-12", "2026-10-09", False),    # Monday: the previous weekday is the Friday, a Friday pull is fresh
    ("2026-10-12", "2026-10-08", True),     # ... a Thursday pull is old
    ("2026-10-13", "2026-10-12", False),    # Tuesday: the previous weekday is Monday
    ("2026-10-13", "2026-10-09", True),     # a Friday pull seen on Tuesday is old
    ("2026-10-10", "2026-10-09", False),    # Saturday: the previous weekday is Friday
    ("2026-10-11", "2026-10-08", True),     # Sunday
])
def test_a_data_source_is_old_when_dated_before_the_previous_weekday(today, pulled, old):
    import reader_values as rv
    assert rv.data_is_stale(pulled, today, _cfg()) is old
    assert rv.data_status_text(pulled, today, _cfg()) == _cfg()["page_timestamps"]["text"]["data_stale" if old else "data_fresh"]


def test_every_labelled_source_is_classified_once_as_data_or_model_round_and_an_unclassified_one_stops_the_build():
    import reader_values as rv
    cfg = _cfg()
    pt = cfg["page_timestamps"]
    assert not set(pt["data_sources"]) & set(pt["model_round_sources"])
    assert {rv.source_class(cfg, s) for s in pt["data_sources"]} == {"data"} and {rv.source_class(cfg, s) for s in pt["model_round_sources"]} == {"model_round"}
    with pytest.raises(rv.ReaderValueError, match="neither list"):
        rv.source_class(cfg, "a new section")
    # the rule of Prompt 49: stock, backlog, raw-material stock, open purchase orders, Trend sales, PEM107 deliveries and the production history are DATA; what the forecast round was fitted on is MODEL-ROUND
    assert {"stock (หน้า Min-Max และแผง stock)", "ยอดจอง (หน้า Min-Max และแผง stock)", "แจ้งเตือน PEM107 (หน้า Min-Max)", "stock และออเดอร์ที่รับแล้ว (Production Plan)",
            "stock วัตถุดิบและใบสั่งซื้อที่ค้างรับ (แผนวัตถุดิบ)", "ยอดขายจริงล่าสุด (แท็บ Trend)", "ประวัติการผลิตของ Historical peak"} <= set(pt["data_sources"])
    # every section of the sales report is MODEL-ROUND
    assert {"ช่วงข้อมูลหลัก", "ผลทดสอบต่อฝ่าย", "กราฟ Rolling-origin", "กราฟระยะเวลาแจ้งล่วงหน้า", "กราฟ MAE โมเดลพื้นฐาน", "กราฟส่งตรงวันพอดี", "กราฟส่งทัน"} <= set(pt["model_round_sources"])


def test_a_model_round_label_has_no_status_wording_and_a_data_label_has_one(monkeypatch):
    import reader_values as rv
    cfg = _cfg()
    t = cfg["page_timestamps"]["text"]
    assert "Fresh" not in t["model_round"] and "Stale" not in t["model_round"] and "Fresh" not in t["sales_main"] and "Stale" not in t["sales_main"]
    facts = rv.model_round_facts("2026-10-05")
    assert facts["round"] == "ต.ค. 69" and facts["pulled"] == rv.thai_date_short(facts["pulled_iso"])
    span = rv.data_age("2026-10-02", "x", cfg, today="2026-10-05")           # Monday: the previous weekday is Friday 2026-10-02, which is not before it
    assert 'data-pulled="2026-10-02"' in span and t["data_fresh"] in span
    assert t["data_stale"] in rv.data_age("2026-10-01", "x", cfg, today="2026-10-05")
    js = rv.data_age_js(cfg)
    assert str(cfg["page_timestamps"]["daily_weekdays_back"]) in js and t["data_stale"] in js and "monthly" not in js


def test_the_two_thresholds_are_manual_values_and_the_manual_uses_them_and_the_old_one_is_gone():
    import reader_values as rv
    cfg = _cfg()
    values = rv.manual_values(cfg)
    assert "stale_days" not in values and "stale_monthly" not in values and values["stale_daily"] == str(cfg["page_timestamps"]["daily_weekdays_back"])
    manual = open(os.path.join(PROJECT_ROOT, "docs", "user_manual.md"), encoding="utf-8").read()
    assert "{stale_monthly}" not in manual and "{stale_daily}" in manual and "{stale_days}" not in manual
    assert "staleness_threshold_days" not in cfg["page_timestamps"]


def test_the_sales_report_numbers_do_not_depend_on_the_label_texts(tmp_path, monkeypatch):
    """Prompt 49: the labels are the only thing the new rule changes on the sales report. Building it with other label texts changes the label block (page-data-line) and nothing else, so no figure moves."""
    import copy
    import re
    import build_report
    base = build_report.load_config()
    changed = copy.deepcopy(base)
    t = changed["page_timestamps"]["text"]
    t["sales_main"], t["model_round"], t["trend_link"] = "AAA {round} {pulled}", "BBB {round} {pulled}", "CCC"
    mask = lambda page: re.sub(r'<details class="note-box" style="margin:10px 0" id="page-data-line">.*?</details>', "@@", page, flags=re.S)
    a = open(build_report.build_report(output_path=str(tmp_path / "a.html")), encoding="utf-8").read()
    monkeypatch.setattr(build_report, "load_config", lambda: changed)
    b = open(build_report.build_report(output_path=str(tmp_path / "b.html")), encoding="utf-8").read()
    assert a != b and "AAA " in b and "CCC" in b and "AAA " not in a
    assert mask(a).replace("@@", "") and mask(a) == mask(b)


def test_the_historical_peak_range_is_the_first_and_last_date_of_the_production_history_file(tmp_path):
    import operation_plan as op
    path = tmp_path / "cube_final.csv"
    path.write_text("itemcode,final_date,transfer_qty\nA,2023-01-03 09:07:28,5\nB,2026-10-02 17:04:08,7\nC,2024-05-01 00:00:00,1\n", encoding="utf-8")
    assert op.capacity_data_range(str(path), "final_date") == {"first_date": "2023-01-03", "last_date": "2026-10-02"}
    meta = op.read_outputs(PROJECT_ROOT, op.load_config(PROJECT_ROOT))[2]
    assert set(meta["capacity_range"]) == {"first_date", "last_date"} and meta["capacity_range"]["first_date"] <= meta["capacity_range"]["last_date"]
