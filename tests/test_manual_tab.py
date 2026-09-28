"""Confirms index.html's third tab (manual tab) can never drift from docs/user_manual.md.

index.html has no generator, so this cannot be checked by rebuilding it. Instead the manual tab is
wired to fetch() docs/user_manual.md AT RUNTIME and render it client-side -- there is no second,
hand-copied text anywhere in index.html that could drift out of sync. This file checks that
architecture directly: the fetch call targets the real source file, and no long stretch of the
manual's own prose has been pasted into index.html as a static duplicate.

A full check that the RENDERED tab text is readable and complete (not just that the wiring is
correct) is done by the Part 4 Validator and the Part 5 CDP visual check, both of which load the
real page in a real browser -- this file only proves the architecture makes drift impossible; it
does not itself execute JavaScript.
"""
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(PROJECT_ROOT, "index.html")
USER_MANUAL = os.path.join(PROJECT_ROOT, "docs", "user_manual.md")


def read_index_html() -> str:
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        return f.read()


def test_user_manual_source_file_exists_and_matches_approved_heading():
    assert os.path.exists(USER_MANUAL), "docs/user_manual.md does not exist"
    with open(USER_MANUAL, "r", encoding="utf-8") as f:
        text = f.read()
    assert text.startswith("# คู่มือการใช้ Dashboard"), (
        "docs/user_manual.md's first line no longer matches the approved manual's title -- "
        "this file's content must be exactly the text between BEGIN MANUAL/END MANUAL."
    )
    # The rolling-origin ordering fact this task verified from src/backtest_rekeyed.py
    # (get_origins() + enumerate(origins, start=1): origin 1 = smallest train_size = earliest
    # window_end_month) means the manual's [ตรวจ] marker was REMOVED, not rewritten -- confirm
    # the corrected sentence is present and the marker is gone.
    assert "แกน X = รอบทดสอบที่ 1-7 เรียงตามเวลา · แกน Y" in text
    assert "[ตรวจ]" not in text


def test_manual_tab_button_and_container_exist():
    text = read_index_html()
    assert re.search(r'<button id="tb3" onclick="omniShowTab\(3\)">\s*คู่มือการใช้งาน\s*</button>', text), (
        "index.html has no tb3 button labelled คู่มือการใช้งาน"
    )
    assert '<div id="manualTab">' in text, "index.html has no #manualTab container"


def test_manual_tab_fetches_the_real_source_file_not_a_copy():
    text = read_index_html()
    assert "fetch('docs/user_manual.md')" in text, (
        "The manual tab must fetch() docs/user_manual.md at runtime, not embed a separate copy "
        "of its text -- this is what makes drift between the tab and the file impossible."
    )
    # Guard against a future regression to a hand-pasted copy: no long run of the manual's own
    # distinctive prose should appear anywhere else in index.html outside this fetch-based path.
    distinctive_lines = [
        "MASE — ดีกว่าวิธีเดาง่ายๆ ไหม",
        "PEM107 | ยังไม่ calibrate ระบบเปลี่ยนเมื่อ พ.ค. 2569",
    ]
    for line in distinctive_lines:
        assert line not in text, (
            f"Found manual prose pasted directly into index.html ({line!r}) -- this duplicates "
            f"docs/user_manual.md and can drift from it; the manual tab must fetch() the file "
            f"instead of embedding a copy."
        )


def test_omni_show_tab_hides_all_three_tabs():
    text = read_index_html()
    m = re.search(r"function omniShowTab\(n\)\{(.*?)\n\}", text, re.S)
    assert m, "omniShowTab(n) function not found"
    body = m.group(1)
    for tab_id in ["origTab", "omniTab", "manualTab"]:
        assert tab_id in body, f"omniShowTab does not reference #{tab_id} -- it will not be hidden on tab switch"
    for btn_id in ["tb1", "tb2", "tb3"]:
        assert btn_id in body, f"omniShowTab does not set #{btn_id}'s active class"


def test_stock_panel_close_listener_covers_all_three_tabs():
    text = read_index_html()
    assert re.search(r"\[\s*'tb1'\s*,\s*'tb2'\s*,\s*'tb3'\s*\]\.forEach", text), (
        "The listener that closes the stock panel on tab switch must include 'tb3' -- otherwise "
        "opening the manual tab while the panel is open leaves the panel visible behind it."
    )
