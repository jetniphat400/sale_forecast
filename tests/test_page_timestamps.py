"""Tests for task 2a's Part 2 (page timestamps), Part 4 (no hand-maintained display dates,
MASE_undefined rendering) and Part 5 (stock panel Reserved source) requirements.

Per this project's DATABASE ACCESS rule, tests never open a new database connection or
re-run the pipeline themselves -- they check committed files and static source code, which is
enough to catch a regression (a future edit reverting to a hand-typed date, or to Cube_Backlog)
without costing another connection attempt every time the suite runs.
"""
import hashlib
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
FROZEN_FORWARD_TEST_LOG_SHA256 = (
    "3adb765139b576c508a93bf0e21b3562d48711d4d04b002800eb5c55e7576a04"
)


# ---------------------------------------------------------------------------------------------
# (1) forward-test log is unchanged by a pipeline refresh
# ---------------------------------------------------------------------------------------------

def test_forward_test_log_hash_matches_frozen_value():
    """The T1 forward-test log (output/summary/forward_test_log_all_divisions.csv,
    src/forward_test_all_divisions.py) must never change once generated -- METRICS.md Sec.26's
    own rule, added the same task this test was added in. A future pipeline run that
    (incorrectly) touches this file will change its hash and fail this test."""
    assert os.path.exists(FORWARD_TEST_LOG), (
        f"{FORWARD_TEST_LOG} does not exist -- cannot verify the forward-test log is frozen."
    )
    with open(FORWARD_TEST_LOG, "rb") as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest()
    assert actual_hash == FROZEN_FORWARD_TEST_LOG_SHA256, (
        "forward_test_log_all_divisions.csv has changed since it was last recorded as frozen "
        "(task 2a, Part 1) -- METRICS.md Sec.26 says it must never be refreshed or rewritten."
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


def test_usable_range_end_equals_data_derived_value_not_a_literal():
    """The rendered 'Usable range' end date must equal gather_usable_range_end()'s own
    data-derived output (the max year_month in the pipeline's monthly series) -- checkable and
    concrete: it must never equal the OLD removed config literal '2026-08-28', regardless of
    whatever the data currently contains."""
    with open(SALES_REPORT_HTML, "r", encoding="utf-8") as f:
        html_text = f.read()
    m = re.search(r"Usable range.*?(\d{4}-\d{2}-\d{2}) — (\S+)", html_text, re.DOTALL)
    assert m, "Usable range row not found in forecast/sales_report.html"
    rendered_end = m.group(2)
    assert rendered_end != "2026-08-28", (
        "Usable range end date still equals the old hand-maintained config.yaml literal -- "
        "the display path may have regressed to reading a typed value."
    )
    config = build_report.load_config()
    expected_end = build_report.gather_usable_range_end(config)
    assert rendered_end == expected_end


# ---------------------------------------------------------------------------------------------
# (4) stock panel's Reserved reads Cube_CES, not Cube_Backlog
# ---------------------------------------------------------------------------------------------

def test_reserved_source_is_cube_ces_not_cube_backlog():
    """Static source check: the WRITTEN Reserved figure must come from
    query_backlog_ces()/dedup_and_aggregate_ces_backlog() (Cube_CES), not query_backlog()/
    aggregate_backlog() (Cube_Backlog) -- the old functions are kept only for the one-time
    before/after comparison in __main__, never called for the written value."""
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

def test_client_js_renders_mase_undefined_not_nan():
    with open(SALES_REPORT_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    assert "MASE_undefined" in text
    assert "function fmtMase" in text


def test_embedded_json_never_contains_literal_nan_for_mase():
    """Builds the report fresh and inspects the embedded #report-data JSON text directly (not
    just the parsed dict, since Python's json.dumps would happily emit the bare token `NaN`,
    which is invalid JSON and would crash the browser's JSON.parse) -- confirms
    embed_report_data()'s None-for-NaN conversion actually reaches the serialized page."""
    out_path = build_report.build_report()
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
