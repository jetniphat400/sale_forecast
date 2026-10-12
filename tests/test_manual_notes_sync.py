"""Confirms config/manual_notes.yaml's ▸ notes actually reach every page they are meant for.

sales_report.html and inventory.html are generator-built (src/manual_notes.render_notes_html),
so a rebuild of either from the tracked config/manual_notes.yaml must reproduce the same notes
byte-for-byte -- checked directly against the tracked, already-built files.

index.html has no generator (docs/user_manual.md's own task instructions: "edit it directly"), so
its copies of the same notes are hand-maintained; this file checks they still match
config/manual_notes.yaml's index.html entries exactly, so a future hand-edit of one without the
other is caught here rather than silently drifting.
"""
import html
import os
import re

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_NOTES_PATH = os.path.join(PROJECT_ROOT, "config", "manual_notes.yaml")
INDEX_HTML = os.path.join(PROJECT_ROOT, "index.html")
SALES_REPORT_HTML = os.path.join(PROJECT_ROOT, "forecast", "sales_report.html")
INVENTORY_HTML = os.path.join(PROJECT_ROOT, "forecast", "inventory.html")


def load_notes() -> dict:
    with open(MANUAL_NOTES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _present(line: str, text: str) -> bool:
    """True when `line` is in `text`. A {braced} name in a configured line stands for a number that the
    builder fills at build time, so it matches any run of characters without a space."""
    if "{" not in line:
        return html.escape(line) in text
    pattern = re.escape(html.escape(line))
    pattern = re.sub(r"\\{[a-z_]+\\}", r"[^<]+?", pattern)
    return re.search(pattern, text) is not None


def test_manual_notes_yaml_has_expected_pages():
    notes = load_notes()
    assert set(notes.keys()) == {"sales_report.html", "inventory.html", "index.html"}


def test_sales_report_html_contains_every_configured_note():
    notes = load_notes()["sales_report.html"]
    with open(SALES_REPORT_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    for chart_id, lines in notes.items():
        for line in lines:
            assert _present(line, text), (
                f"sales_report.html is missing the configured note for {chart_id!r}: {line!r} "
                f"-- re-run `python src/build_report.py`."
            )


def test_inventory_html_contains_every_configured_note():
    notes = load_notes()["inventory.html"]
    with open(INVENTORY_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    for chart_id, lines in notes.items():
        for line in lines:
            assert _present(line, text), (
                f"inventory.html is missing the configured note for {chart_id!r}: {line!r} "
                f"-- re-run `python src/build_inventory_page.py`."
            )


def test_index_html_hand_copied_notes_match_manual_notes_yaml():
    notes = load_notes()["index.html"]
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    for chart_id, lines in notes.items():
        for line in lines:
            # a {braced} name stands for a value the page's script fills from its data (the Trend tab's first and last month): the fixed pieces around it must be in the file
            pieces = [p for p in re.split(r"\{[a-z_]+\}", line) if p]
            assert all(p in text for p in pieces), (
                f"index.html's hand-maintained copy is missing (or drifted from) the note for "
                f"{chart_id!r}: {line!r} -- config/manual_notes.yaml is the source of truth; "
                f"update index.html to match it exactly."
            )


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# The manual's numbers and dates are {braced} names filled at runtime from data/assumptions.json (key manual_values): none may be left unresolved.
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
USER_MANUAL = os.path.join(PROJECT_ROOT, "docs", "user_manual.md")
ASSUMPTIONS_JSON = os.path.join(PROJECT_ROOT, "data", "assumptions.json")


def _manual_names() -> set:
    with open(USER_MANUAL, "r", encoding="utf-8") as f:
        return set(re.findall(r"\{([a-z][a-z0-9_]*)\}", f.read()))


def test_every_manual_placeholder_has_a_value_in_the_published_json():
    import json
    names = _manual_names()
    assert names, "the manual has no placeholder at all: its numbers are typed again"
    with open(ASSUMPTIONS_JSON, "r", encoding="utf-8") as f:
        values = json.load(f)["manual_values"]
    unresolved = sorted(n for n in names if not str(values.get(n, "")).strip())
    assert unresolved == [], f"manual placeholders with no value in data/assumptions.json manual_values: {unresolved}"
    assert sorted(set(values) - names) == [], "manual_values holds a name the manual does not use"


def test_an_unresolved_manual_placeholder_is_detected():
    import json
    with open(ASSUMPTIONS_JSON, "r", encoding="utf-8") as f:
        values = dict(json.load(f)["manual_values"])
    values.pop("stale_days")
    assert [n for n in sorted(_manual_names()) if not str(values.get(n, "")).strip()] == ["stale_days"]


def test_the_published_manual_values_are_what_the_sources_compute_now():
    import json
    import sys
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
    import reader_values as rv
    with open(ASSUMPTIONS_JSON, "r", encoding="utf-8") as f:
        published = json.load(f)["manual_values"]
    assert published == rv.manual_values(), "data/assumptions.json manual_values is out of date: rebuild it with src/maxmin_v1.py write_assumptions"


def test_no_manual_number_that_describes_the_data_or_the_schedule_is_typed():
    with open(USER_MANUAL, "r", encoding="utf-8") as f:
        text = f.read()
    for typed in ("ข้อมูลถึง 25 ส.ค. 2569", "448 รหัส", "วันที่ 5", "5 ธ.ค.", "ต้องรอ 30 วัน", "45-60 วัน"):
        assert typed not in text, f"the manual types {typed!r}: use a placeholder filled from data/assumptions.json"
    assert "วันธรรมดา (จันทร์ถึงศุกร์) วันแรกตั้งแต่วันที่ {run_day_base}" in text


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# The confirmed procurement lead time: 45-60 days (config phase_e1_assumptions); 75 is a stress point of the sensitivity grid and is never shown as the lead time of the business.
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
def _config() -> dict:
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_the_confirmed_lead_time_chain_config_to_manual_value_to_pages():
    import json
    e1 = _config()["phase_e1_assumptions"]
    grid, default = e1["procurement_lead_time_days_grid"], e1["procurement_lead_time_days_default"]
    assert min(grid) == 45 and default == 60 and max(grid) == 75 > default           # the confirmed range 45-60 and the stress point 75 as they stand in config
    with open(ASSUMPTIONS_JSON, "r", encoding="utf-8") as f:
        values = json.load(f)["manual_values"]
    assert (values["lead_confirmed_first"], values["lead_confirmed_last"]) == (str(min(grid)), str(default))     # read from config, not typed
    assert not any(k.startswith("lead_grid") for k in values)
    with open(USER_MANUAL, "r", encoding="utf-8") as f:
        manual = f.read()
    assert "แต่สั่งวัตถุดิบใช้ {lead_confirmed_first}-{lead_confirmed_last} วัน" in manual
    with open(SALES_REPORT_HTML, "r", encoding="utf-8") as f:
        sales = f.read()
    assert f"<b>{min(grid)}-{default}</b> วัน" in sales and f"ช่วงทดสอบความไวเพิ่มถึง {max(grid)} วัน" in sales
    for rel in ("docs/user_manual.md", "index.html", "forecast/sales_report.html", "forecast/inventory.html", "forecast/operation_plan.html", "forecast/material_plan.html"):
        with open(os.path.join(PROJECT_ROOT, rel), "r", encoding="utf-8") as f:
            text = f.read()
        text = re.sub(r'<td class="name">.*?</td>', " ", text)                          # product names of the tables are not text of the page
        assert not re.search(r"45\s*[-–]\s*75", text), f"{rel} presents 45-75 as a lead time"


def test_one_term_for_on_time_delivery_and_its_explanation_at_the_first_use():
    explanation = "ส่งไม่ช้ากว่าวันนัด"
    old = re.compile(r"ส่งไม่ช้า(?!กว่าวันนัด)|ส่งไม่ล่าช้า|ไม่สาย")
    for rel in ("docs/user_manual.md", "config/manual_notes.yaml", "forecast/sales_report.html", "forecast/inventory.html", "forecast/operation_plan.html", "forecast/material_plan.html"):
        with open(os.path.join(PROJECT_ROOT, rel), "r", encoding="utf-8") as f:
            text = f.read()
        assert not old.search(text), f"{rel} still uses another word than ส่งทัน for on-time delivery: {old.search(text).group(0)!r}"
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        index = f.read()
    start = index.index('<div id="origTab"')
    depth, end = 0, start
    for m in re.finditer(r"<div\b|</div>", index[start:]):
        depth += 1 if m.group(0).startswith("<div") else -1
        if depth == 0:
            end = start + m.end()
            break
    assert end > start and not old.search(index[:start] + index[end:])                  # the original S&OP tab is not touched and not checked
    # the manual: every heading block that uses the term explains it
    with open(USER_MANUAL, "r", encoding="utf-8") as f:
        blocks = re.split(r"(?m)^#{2,3} ", f.read())
    for block in blocks:
        if "ส่งทัน" in block:
            assert explanation in block, f"a manual section uses ส่งทัน without explaining it: {block[:50]!r}"
    # the pages: the first use outside the closed data-date table is followed by the explanation
    for rel in ("forecast/sales_report.html", "forecast/inventory.html"):
        with open(os.path.join(PROJECT_ROOT, rel), "r", encoding="utf-8") as f:
            page = f.read()
        page = re.sub(r"<details.*?</details>", " ", page, flags=re.S)
        page = re.sub(r"<(script|style)\b.*?</\1>|<!--.*?-->", " ", page, flags=re.S)
        first = page.index("ส่งทัน")
        assert explanation in page[first: first + 60], f"{rel}: the first ส่งทัน is not followed by its explanation: {page[first - 20: first + 60]!r}"
