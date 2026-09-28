"""Single source of truth for the short "note-box" text that appears under each chart on the
generated pages, read from config/manual_notes.yaml (docs/user_manual.md task, Part 0).

Both src/build_report.py and src/build_inventory_page.py import render_notes_html() so the
wording under a chart lives in exactly one file, never retyped inside either builder. index.html
has no generator, so its entries in config/manual_notes.yaml are a documented reference an editor
copies into the static HTML by hand -- tests/test_manual_notes_sync.py checks that copy stays in
sync.
"""
import html
import os

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_NOTES_PATH = os.path.join(PROJECT_ROOT, "config", "manual_notes.yaml")


class ManualNotesError(Exception):
    """Raised when a page/chart id has no entry in config/manual_notes.yaml -- CONVENTIONS.md's
    'validation failures must be raised loudly' applies here too: a chart silently missing its
    approved note is a regression, not something to render blank."""


def load_manual_notes() -> dict:
    with open(MANUAL_NOTES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def render_notes_html(page: str, chart_id: str, css_class: str = "hint") -> str:
    """Renders config/manual_notes.yaml's ▸ lines for this page/chart as one <p> using an EXISTING
    page class (default 'hint', matching this project's 'p.hint'/'p.note-box' CSS convention for
    small text under a chart -- both sales_report.html and inventory.html style these as `p.hint`/
    `p.note-box`, tag-qualified, so this must render a <p>, not a <div>, to actually be styled).
    Never a new class invented for this purpose."""
    notes = load_manual_notes()
    lines = notes.get(page, {}).get(chart_id)
    if not lines:
        raise ManualNotesError(
            f"config/manual_notes.yaml has no notes for page={page!r} chart_id={chart_id!r}. "
            f"Add the entry (see docs/user_manual.md for the approved wording) before building."
        )
    body = "<br>".join(html.escape(line) for line in lines)
    return f'<p class="{css_class}">{body}</p>'
