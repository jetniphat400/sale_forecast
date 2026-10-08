"""Part 3 (manual-publish task): confirms a monthly-style rebuild of the two generated pages
still carries every manual note, axis title and scope label -- not just the copy on disk today.

Both builders are invoked exactly as their own real callers do:
  - sales_report.html: build_report.build_report(output_path=...), the same call
    src/monthly_refresh.py's step7_rebuild_pages() makes (METRICS.md Sec.28 step 7).
  - inventory.html: build_inventory_page.build_page(), the only entry point that exists for it.
    src/monthly_refresh.py's own module docstring (lines ~31-38) states this page is OUT OF ITS
    SCOPE -- it needs its own separate database connection the monthly runner's
    single-connection-per-run design does not make, and is deferred to task 2b. There is no
    "monthly runner" invocation of this builder to mirror; this test calls its one real entry
    point instead, which itself performs a live database pull (Cube_Inventory_Exact) for
    PEM103/PEM107 -- the same pull the tracked forecast/inventory.html on disk already reflects.

METRICS.md Sec.28's own rule ("Tests must not modify tracked output files; a test that
regenerates a page writes to a temporary location") applies here directly: both rebuilds below
write to tmp_path, never to the tracked forecast/*.html files.
"""
import html
import os
import sys

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import build_report  # noqa: E402
import build_inventory_page  # noqa: E402

MANUAL_NOTES_PATH = os.path.join(PROJECT_ROOT, "config", "manual_notes.yaml")


def load_notes(page: str) -> dict:
    with open(MANUAL_NOTES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)[page]


def _present(line, text):
    """True when the configured note line is in the page; a {braced} name is a number the builder filled."""
    import re
    if "{" not in line:
        return html.escape(line) in text
    pattern = re.sub(r"\\{[a-z_]+\\}", r"[^<]+?", re.escape(html.escape(line)))
    return re.search(pattern, text) is not None


def test_sales_report_rebuild_still_has_every_note_and_axis_title(tmp_path):
    out_path = build_report.build_report(output_path=os.path.join(str(tmp_path), "sales_report.html"))
    with open(out_path, "r", encoding="utf-8") as f:
        text = f.read()

    notes = load_notes("sales_report.html")
    for chart_id, lines in notes.items():
        for line in lines:
            assert _present(line, text), (
                f"Rebuilt sales_report.html lost the note for {chart_id!r}: {line!r}"
            )

    for axis_title in [
        "ระยะแจ้งล่วงหน้าขั้นต่ำ (วัน)",  # chart-notice X axis
        "% ของออเดอร์",                     # chart-notice Y axis
        "yaxis: {title: {text: '%'}}",     # chart-ontime Y axis
        "รหัสสินค้า",                        # chart-model X axis
        "MAE (ชิ้นต่อเดือน)",                # chart-model Y axis
    ]:
        assert axis_title in text, f"Rebuilt sales_report.html lost axis title text {axis_title!r}"

    # This pinned Plotly build (v4.1.1) silently drops the plain-string `title: '...'` shorthand --
    # confirmed by direct browser inspection this task (Plotly._fullLayout.xaxis.title.text stayed
    # the built-in "Click to enter X axis title" placeholder until every title was rewritten as
    # `title: {text: '...'}`). Guards against a future edit reintroducing the silently-broken form.
    assert "title: '" not in text, (
        "sales_report.html's client JS uses the plain-string Plotly title shorthand somewhere -- "
        "this pinned Plotly build silently ignores it (title never renders); use title: {text: ...}."
    )

    for scope_label in [
        "มีผลกับตารางหลัก ตารางรอง และกราฟ Rolling-origin",
        "มีผลกับกราฟ Rolling-origin เท่านั้น",
        "ตัวกรอง ฝ่าย/ประเภท ด้านบนไม่มีผลกับกราฟนี้",
    ]:
        assert scope_label in text, f"Rebuilt sales_report.html lost scope label {scope_label!r}"


def test_inventory_page_rebuild_still_has_every_note_axis_title_and_disabled_control(tmp_path):
    # No database: the page is rendered from the tracked page's own embedded data (week 4, prompt 6: this test used to call build_page() with no sources, which
    # pulls live from the database and wrote four pull files into output/snapshots on every full run).
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "tests"))
    from page_helpers import fresh_inventory_data
    data = fresh_inventory_data()
    mp = pytest.MonkeyPatch()
    mp.setattr(build_inventory_page, "build_data", lambda **kw: data)
    try:
        page_html = build_inventory_page.build_page()
    finally:
        mp.undo()
    out_path = os.path.join(str(tmp_path), "inventory.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    notes = load_notes("inventory.html")
    for chart_id, lines in notes.items():
        for line in lines:
            assert _present(line, page_html), (
                f"Rebuilt inventory.html lost the note for {chart_id!r}: {line!r}"
            )

    for axis_title in ["รหัสสินค้า", "จำนวน (ชิ้น)"]:
        assert axis_title in page_html, f"Rebuilt inventory.html lost Min-vs-current axis title {axis_title!r}"

    # Same silently-broken plain-string Plotly title shorthand as sales_report.html -- see that
    # test's own comment. Confirmed by direct browser inspection this task.
    assert "title: '" not in page_html, (
        "inventory.html's client JS uses the plain-string Plotly title shorthand somewhere -- "
        "this pinned Plotly build silently ignores it (title never renders); use title: {text: ...}."
    )

    # RE-ENABLED, task 2b Part 1 (METRICS.md Sec.40): both controls now compute something real
    # (excess flag / recomputed on_hand_sellable) -- superseding the earlier task's "not working"
    # labels, which this test used to require. See tests/test_inventory_parity.py for the
    # warehouse-selection/threshold parity coverage that replaces this disabled-state check.
    assert "ยังไม่ทำงาน — อยู่ระหว่างแก้ไข" not in page_html, (
        "Rebuilt inventory.html still shows the 'not working' label -- task 2b re-enabled both "
        "controls; this label should no longer appear anywhere on the page."
    )
    assert 'id="ctrl-obsolescence_threshold_months"' in page_html
    assert "disabled" not in page_html.split('id="ctrl-obsolescence_threshold_months"')[1][:120], (
        "The obsolescence slider must render WITHOUT the disabled attribute (task 2b re-enabled it)."
    )
    assert 'class="wh-check"' in page_html and 'onchange="onControlChange()"' in page_html, (
        "The warehouse checklist checkboxes must be wired to onControlChange() (task 2b re-enabled them)."
    )


def test_inventory_json_still_carries_a_builder_written_generated_at():
    """The stock panel's page_built_at now reads data/inventory.json's own snapshot.generated_at
    (this task's Part 1 fix, replacing a hand-typed constant in index.html) -- confirms the field
    this fix depends on still exists in the tracked data file."""
    import json
    data_path = os.path.join(PROJECT_ROOT, "data", "inventory.json")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "snapshot" in data and "generated_at" in data["snapshot"], (
        "data/inventory.json is missing snapshot.generated_at -- the stock panel's page_built_at "
        "fix (index.html's invUtcIsoToIctString) depends on this field."
    )
