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

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_NOTES_PATH = os.path.join(PROJECT_ROOT, "config", "manual_notes.yaml")
INDEX_HTML = os.path.join(PROJECT_ROOT, "index.html")
SALES_REPORT_HTML = os.path.join(PROJECT_ROOT, "forecast", "sales_report.html")
INVENTORY_HTML = os.path.join(PROJECT_ROOT, "forecast", "inventory.html")


def load_notes() -> dict:
    with open(MANUAL_NOTES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_manual_notes_yaml_has_expected_pages():
    notes = load_notes()
    assert set(notes.keys()) == {"sales_report.html", "inventory.html", "index.html"}


def test_sales_report_html_contains_every_configured_note():
    notes = load_notes()["sales_report.html"]
    with open(SALES_REPORT_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    for chart_id, lines in notes.items():
        for line in lines:
            assert html.escape(line) in text, (
                f"sales_report.html is missing the configured note for {chart_id!r}: {line!r} "
                f"-- re-run `python src/build_report.py`."
            )


def test_inventory_html_contains_every_configured_note():
    notes = load_notes()["inventory.html"]
    with open(INVENTORY_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    for chart_id, lines in notes.items():
        for line in lines:
            assert html.escape(line) in text, (
                f"inventory.html is missing the configured note for {chart_id!r}: {line!r} "
                f"-- re-run `python src/build_inventory_page.py`."
            )


def test_index_html_hand_copied_notes_match_manual_notes_yaml():
    notes = load_notes()["index.html"]
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        text = f.read()
    for chart_id, lines in notes.items():
        for line in lines:
            assert line in text, (
                f"index.html's hand-maintained copy is missing (or drifted from) the note for "
                f"{chart_id!r}: {line!r} -- config/manual_notes.yaml is the source of truth; "
                f"update index.html to match it exactly."
            )
