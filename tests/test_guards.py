"""Guards built during Phase B: the leakage guard (src/leakage_guard.py) and the
forward-test consistency check (src/score_forward_test_v2.verify_consistency).
Both must raise loudly on violation, never silently skip or warn-and-continue
(CONVENTIONS.md: "Validation failures must be raised loudly, never silently skipped").
"""
import pytest

from forward_test import config_version
from forward_test_common import ForwardTestConsistencyError, compute_scope_hash
from leakage_guard import LeakageGuardError, check_window_closed, load_min_margin_days
from score_forward_test_v2 import load_config, verify_consistency

SCOPE_CODES = ["ITEM-A", "ITEM-B", "ITEM-C"]


# ---------------------------------------------------------------------------
# Leakage guard
# ---------------------------------------------------------------------------

def test_leakage_guard_raises_when_pull_lands_the_same_day_the_window_closes():
    with pytest.raises(LeakageGuardError):
        check_window_closed("2026-07", "2026-07-31", min_margin_days=30)


def test_leakage_guard_raises_when_margin_is_one_day_short():
    with pytest.raises(LeakageGuardError):
        check_window_closed("2026-07", "2026-08-29", min_margin_days=30)  # gap = 29 days


def test_leakage_guard_error_message_states_window_end_pull_date_and_margins():
    with pytest.raises(LeakageGuardError) as excinfo:
        check_window_closed("2026-07", "2026-07-31", min_margin_days=30)
    message = str(excinfo.value)
    assert "2026-07-31" in message  # window end
    assert "30" in message           # required margin
    assert "0" in message            # actual margin


def test_leakage_guard_passes_when_margin_exactly_meets_the_requirement():
    # Boundary is `actual_gap_days < min_margin_days` -- an exact match must NOT raise.
    check_window_closed("2026-07", "2026-08-30", min_margin_days=30)  # gap = 30 days


def test_leakage_guard_passes_with_a_generous_margin():
    check_window_closed("2026-07", "2026-12-31", min_margin_days=30)


def test_load_min_margin_days_raises_loudly_when_config_section_missing():
    with pytest.raises(KeyError):
        load_min_margin_days({})


def test_load_min_margin_days_reads_the_configured_value():
    assert load_min_margin_days({"leakage_guard": {"min_margin_days": 30}}) == 30


# ---------------------------------------------------------------------------
# Forward-test consistency check
# ---------------------------------------------------------------------------

def _matching_metadata(current_config: dict) -> dict:
    return {
        "config_version": config_version(),
        "date_key": current_config["adopted_series_key"],
        "item_level_approach": current_config["adopted_item_level_approach"],
        "scope_hash": compute_scope_hash(SCOPE_CODES),
        "scope_n_items": len(SCOPE_CODES),
    }


def test_verify_consistency_passes_when_everything_matches_current_state():
    config = load_config()
    metadata = _matching_metadata(config)
    verify_consistency(metadata, config, SCOPE_CODES)  # must not raise


def test_verify_consistency_refuses_to_score_on_config_hash_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    metadata["config_version"] = "0" * 12  # a stale hash, does not match current config.yaml
    with pytest.raises(ForwardTestConsistencyError, match="config_version"):
        verify_consistency(metadata, config, SCOPE_CODES)


def test_verify_consistency_refuses_to_score_on_series_key_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    assert config["adopted_series_key"] != "createDate", (
        "test assumes the adopted series key is not createDate -- update this test if it changes"
    )
    metadata["date_key"] = "createDate"
    with pytest.raises(ForwardTestConsistencyError, match="date_key"):
        verify_consistency(metadata, config, SCOPE_CODES)


def test_verify_consistency_refuses_to_score_on_scope_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    with pytest.raises(ForwardTestConsistencyError, match="scope_hash"):
        verify_consistency(metadata, config, SCOPE_CODES + ["ITEM-D"])  # scope grew, hash now stale


def test_verify_consistency_refuses_to_score_on_approach_mismatch():
    config = load_config()
    metadata = _matching_metadata(config)
    assert config["adopted_item_level_approach"] != "Direct"
    metadata["item_level_approach"] = "Direct"
    with pytest.raises(ForwardTestConsistencyError, match="item_level_approach"):
        verify_consistency(metadata, config, SCOPE_CODES)


# ====================================================================================================
# Guard for CONVENTIONS.md "Customer and contract identifiers" (decided by the user, 2026-10-06): customer IDs, customer names, contract numbers and personal login
# names never appear in documentation, config, source or tests (pages under forecast/ and index.html may show them).
#
# Scope: the project's markdown documents (STATUS, DATA_MAP, METRICS, PROJECT_GRAPH, AGENTS, CONVENTIONS), everything under docs/, config/, src/ and tests/ (.py .yaml .yml .md .json .csv .txt),
# and the JSON files under data/ (Prompt 33, 2026-10-15). The pages (index.html, forecast/*.html) may show identifiers and are not scanned. data/inventory.json is the stock panel's runtime
# data: the three fields the panel's backlog pop-up DISPLAYS (doc_id, job, customer) are allowed there, every other part of every data file is scanned like a document.
#
# Formats, as observed in the saved pulls (output/data and output/summary, which are untracked):
#   * customer ID   : two capital letters then five digits (the CustomerID / customerid columns of Cube_CES, cube_Sale_APD and Cube_Quotation);
#   * contract number: two to five capital letters, a hyphen, a four-digit year, a hyphen, five digits (the ContractID / contractid columns: contract, quotation and enquiry
#                     numbers share this shape);
#   * customer name : exact match against the values of the customer-name columns (cusname, customer_name, CustomerName) of the saved pulls, when those files are present;
#   * login name    : the user folder of a Windows path (Users, then a folder other than the placeholder <user>), and the login recorded in .env (DB_USER), when .env is present.
# The test reads files only; it holds no real identifier or value (the examples below are built from parts), and it modifies no tracked file. The exact-match part reads the saved pulls
# when they are present; when they are absent the format checks alone run (the test is never skipped).
#   * target values : the revenue target (Cube_Target_PMIS, the workbook target_data.xlsx) is never written in a tracked document, config, source or test: an exact-match check against
#                     the saved aggregate output/data/exec_pull/targets.csv when it exists, and a format check that always runs (a line that talks about the revenue target carries no amount).
# ====================================================================================================
import glob
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["STATUS.md", "DATA_MAP.md", "METRICS.md", "PROJECT_GRAPH.md", "AGENTS.md", "CONVENTIONS.md"]
SUFFIXES = (".py", ".yaml", ".yml", ".md", ".json", ".csv", ".txt")
DISPLAYED_BACKLOG_FIELDS = ("doc_id", "job", "customer")     # the fields the stock panel's backlog pop-up shows (index.html invOpenBacklogDetail)
REVENUE_TARGET_LINE = re.compile(r"revenue target|target by division|target aggregate|target table|target workbook|target version|Cube_Target|TARGET_PMIS|target_data|TargetC1005|divisions' target|million target|saved target|against the [^.]{0,40}target|year-end projection|เป้า", re.I)
AMOUNT = re.compile(r"(?<![\w.\-/])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)(?![\w\-/])|(?<![\w.\-/])\d[\d,]*(?:\.\d+)?\s?[MB]\b")      # an amount: thousands separators, decimals, or a million / billion suffix
CUSTOMER_ID = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{5}(?![A-Za-z0-9])")
CONTRACT_NO = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,5}-\d{4}-\d{5}(?![A-Za-z0-9])")
WINDOWS_USER = re.compile(r"Users[\\/]+([^\\/\s`'\"]+)", re.I)       # any number of separators (a doubled backslash in a Python or JSON string), either slash, any case (Users or users)
CUSTOMER_NAME_COLUMNS = ("cusname", "customer_name", "customername", "end_cusname")
MIN_NAME_LENGTH = 8


def scope_files() -> list:
    files = [os.path.join(PROJECT_ROOT, d) for d in DOCS]
    for top in ("docs", "config", "src", "tests"):
        for folder, dirs, names in os.walk(os.path.join(PROJECT_ROOT, top)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            files += [os.path.join(folder, n) for n in names if n.endswith(SUFFIXES)]
    return [f for f in files if os.path.isfile(f)]


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def rel(path: str) -> str:
    return os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")


def hits(pattern, files) -> list:
    out = []
    for f in files:
        for n, line in enumerate(read(f).splitlines(), 1):
            if pattern.search(line):
                out.append(f"{rel(f)}:{n}")
    return out


def test_the_guard_recognises_each_format_using_made_up_values_built_from_parts():
    cid = "C" + "S" + "0" * 4 + "1"
    contract = "CT" + "R" + "-" + "2" * 4 + "-" + "0" * 4 + "7"
    assert CUSTOMER_ID.search(f"customer {cid} ordered") and CUSTOMER_ID.search(f"`{cid}`")
    assert CONTRACT_NO.search(f"contract {contract} is late") and CONTRACT_NO.search("QTN" + "-" + "2025" + "-" + "00350")
    assert not CUSTOMER_ID.search("PEM107 and HS-F-99-02110") and not CONTRACT_NO.search("EEE-F-FC-1040010002 on 2026-10-06")
    assert not CUSTOMER_ID.search("ABC12345678") and not CONTRACT_NO.search("EEE-F-FL-1040030002")
    assert WINDOWS_USER.search("C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "AppData").group(1) == "someone"
    assert WINDOWS_USER.search("C:" + chr(92) + "Users" + chr(92) + "<user>" + chr(92) + "AppData").group(1) == "<user>"
    # the forms the first version of the pattern missed (Prompt 34): doubled backslashes, forward slashes, lower case
    assert WINDOWS_USER.search("C:" + chr(92) * 2 + "Users" + chr(92) * 2 + "someone" + chr(92) * 2 + "x").group(1) == "someone"
    assert WINDOWS_USER.search("c:/" + "users" + "/someone/AppData").group(1) == "someone"
    assert WINDOWS_USER.search("C:/" + "Users" + "/" + "<user>" + "/x").group(1) == "<user>"


def test_no_customer_id_or_contract_number_in_documents_config_source_or_tests():
    files = scope_files()
    assert len(files) > 100, "the scope looks empty"
    assert any(rel(f).startswith("docs/") for f in files), "docs/ is not in the scope"
    found = hits(CUSTOMER_ID, files) + hits(CONTRACT_NO, files)
    assert not found, "customer IDs or contract numbers (CONVENTIONS.md): " + ", ".join(found[:20])


def test_no_personal_login_name_in_a_path_in_documents_config_source_or_tests():
    found = []
    for f in scope_files():
        for n, line in enumerate(read(f).splitlines(), 1):
            for m in WINDOWS_USER.finditer(line):
                if m.group(1).lower() not in ("<user>", "public", "default", "all"):
                    found.append(f"{rel(f)}:{n}")
    assert not found, "a personal login name in a path (write <user>): " + ", ".join(found[:20])
    env = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env):
        login = [l.split("=", 1)[1].strip().strip('"').strip("'") for l in read(env).splitlines() if l.startswith("DB_USER=")]
        for name in login:
            if len(name) >= 4:
                assert not [f for f in scope_files() if name in read(f)], "the database login name appears in a file of the scope"


def _saved_pull_columns(kinds: dict) -> dict:
    """{kind: set of values} read from the saved pulls under output/ (CSV files; empty sets when none is present). Columns are matched by lower-case name."""
    import pandas as pd
    out = {k: set() for k in kinds}
    for f in glob.glob(os.path.join(PROJECT_ROOT, "output", "data", "*.csv")) + glob.glob(os.path.join(PROJECT_ROOT, "output", "summary", "*.csv")):
        try:
            cols = pd.read_csv(f, nrows=0).columns
        except Exception:
            continue
        for c in cols:
            for kind, names in kinds.items():
                if c.lower() in names:
                    try:
                        out[kind] |= set(pd.read_csv(f, usecols=[c], dtype=str)[c].dropna().str.strip().unique())
                    except Exception:
                        pass
    return out


def _customer_names() -> set:
    names = _saved_pull_columns({"n": CUSTOMER_NAME_COLUMNS})["n"]
    return {n for n in names if len(n) >= MIN_NAME_LENGTH and " " in n}


def _customer_ids() -> set:
    ids = _saved_pull_columns({"i": ("customerid", "customer_id", "end_customerid")})["i"]
    return {i for i in ids if len(i) >= 6}


def _contract_numbers() -> set:
    vals = _saved_pull_columns({"c": ("contractid", "docid", "doc_id", "quotationid")})["c"]
    return {v for v in vals if len(v) >= 8}


def data_scan_texts() -> dict:
    """{relative path: text} of every JSON file under data/ with the displayed backlog fields (doc_id, job, customer) of data/inventory.json blanked: those, and only those, may show identifiers."""
    import json
    out = {}
    for f in sorted(glob.glob(os.path.join(PROJECT_ROOT, "data", "*.json"))):
        text = read(f)
        if os.path.basename(f) == "inventory.json":
            data = json.loads(text)
            for item in data.get("items", []):
                for row in item.get("backlog_rows", []):
                    for k in DISPLAYED_BACKLOG_FIELDS:
                        row[k] = ""
            text = json.dumps(data, ensure_ascii=False, indent=1)
        out[rel(f)] = text
    return out


def test_no_customer_id_or_contract_number_in_data_json_except_the_displayed_fields():
    texts = data_scan_texts()
    assert "data/inventory.json" in texts and len(texts) >= 3
    found = [f"{name}:{n}" for name, text in texts.items() for n, line in enumerate(text.splitlines(), 1)
             if CUSTOMER_ID.search(line) or CONTRACT_NO.search(line)]
    assert not found, "a customer ID or contract number outside the displayed fields of data/*.json: " + ", ".join(found[:20])


def test_the_customer_and_contract_fields_of_inventory_json_are_exactly_those_the_stock_panel_displays():
    """A field that holds a customer or contract identifier may be in data/inventory.json only while the page shows it (Prompt 33): if the panel stops displaying one, the
    generator must stop writing it."""
    import json
    with open(os.path.join(PROJECT_ROOT, "data", "inventory.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    page = read(os.path.join(PROJECT_ROOT, "index.html"))
    rows = [row for item in data["items"] for row in item["backlog_rows"]]
    fields = {k for row in rows for k in row}
    holding_identifiers = {k for k in fields if any(CUSTOMER_ID.search(str(row.get(k, ""))) or CONTRACT_NO.search(str(row.get(k, ""))) for row in rows)}
    assert holding_identifiers <= set(DISPLAYED_BACKLOG_FIELDS), sorted(holding_identifiers - set(DISPLAYED_BACKLOG_FIELDS))
    for k in DISPLAYED_BACKLOG_FIELDS:
        assert f"r.{k}" in page, f"the stock panel no longer shows the field {k}: remove it from data/inventory.json (its generator, src/build_inventory_dataset.py)"


def test_no_customer_name_or_id_or_contract_from_the_saved_pulls_appears_by_exact_match():
    """Runs always. With the saved pulls on this machine it also compares exact values; without them the format checks (above and below) still run."""
    names, ids, contracts = _customer_names(), _customer_ids(), _contract_numbers()
    texts = {rel(f): read(f) for f in scope_files()}
    texts.update(data_scan_texts())
    tokens = {name: set(re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_./]*", t)) for name, t in texts.items()}
    found = sorted({name for name, tk in tokens.items() if (tk & ids) or (tk & contracts)} | {name for name, t in texts.items() for n in names if n in t})
    assert not found, "a customer name, ID or contract number from the saved pulls appears in: " + ", ".join(found[:20])


def _target_forms() -> tuple:
    """(whole-number forms, million forms) of the revenue-target sums of output/data/exec_pull/targets.csv, built in memory; two empty sets when the file is not on this machine."""
    path = os.path.join(PROJECT_ROOT, "output", "data", "exec_pull", "targets.csv")
    if not os.path.exists(path):
        return set(), set()
    import itertools
    import pandas as pd
    t = pd.read_csv(path)
    cols = [c for c in ("division", "revenue_type", "category", "product_type", "yr") if c in t.columns]
    sums = {float(t["amount"].sum())}
    for r in range(1, len(cols) + 1):
        for sub in itertools.combinations(cols, r):
            for _, g in t.groupby(list(sub), dropna=True):
                sums.add(float(g["amount"].sum()))
    sums |= {float(a) for a in t["amount"].dropna()}
    big, mil = set(), set()
    for v in sums:
        if v >= 1e6:
            big |= {f"{v:.0f}", f"{v:,.0f}"}
            mil |= {f"{v / 1e6:.1f}", f"{v / 1e6:.2f}", f"{v / 1e6:,.1f}"}
    return {b for b in big if len(re.sub(r"\D", "", b)) >= 7}, mil


def test_no_revenue_target_value_in_documents_config_source_or_tests():
    """Format check (always runs): a line that talks about the revenue target carries no amount. Exact check (when targets.csv is present): none of its sums appears."""
    big, mil = _target_forms()
    token = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d{7,})(?![\d]|[.,]\d)")
    mil_token = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})*\.\d{1,2})(?![\d]|[.,]\d)")
    found = []
    for f in scope_files():
        for n, line in enumerate(read(f).splitlines(), 1):
            is_target_line = bool(REVENUE_TARGET_LINE.search(line))
            if is_target_line and AMOUNT.search(line):
                found.append(f"{rel(f)}:{n}")
            elif big and any(m in big for m in token.findall(line)):
                found.append(f"{rel(f)}:{n}")
            elif mil and is_target_line and any(m in mil for m in mil_token.findall(line)):
                found.append(f"{rel(f)}:{n}")
    assert not found, "a revenue-target amount in: " + ", ".join(found[:20])


def test_the_target_format_check_recognises_what_it_must():
    """Made-up values only, built from parts."""
    amount = "1" + "23" + "," + "456"
    assert REVENUE_TARGET_LINE.search("the 2026 revenue target by division is " + amount) and AMOUNT.search("is " + amount)
    assert AMOUNT.search("the 2026 revenue target is THB " + "12" + "M") and AMOUNT.search("THB " + "9" + "," + "999" + "M")
    assert not AMOUNT.search("the revenue target was removed (Prompt 27)")
    assert not REVENUE_TARGET_LINE.search("the service level for not late is 98.24 percent")


# ---------------------------------------------------------------------------
# Nothing under output/ is tracked (decision of 2026-10-07): the publishing clone's output/ is a junction into the main copy's output/, so a tracked
# file there could be changed or deleted in the main copy by a pull in the clone.
# ---------------------------------------------------------------------------
HELD_UNDER_OUTPUT = set()      # nothing is held: check_significance_topdown.md moved to docs/reports (decision D2 of 2026-10-07)


def test_no_file_under_output_is_tracked():
    import os
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isdir(os.path.join(root, ".git")):
        pytest.skip("SKIPPED, not passed: not a git working copy (a temporary copy of the project)")
    tracked = subprocess.run(["git", "ls-files", "output"], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True).stdout.split()
    assert set(tracked) <= HELD_UNDER_OUTPUT, sorted(set(tracked) - HELD_UNDER_OUTPUT)[:10]
    ignore = open(os.path.join(root, ".gitignore"), encoding="utf-8").read().split()
    assert "output/" in ignore


# ------------------------------------------------------------------ the test suite never connects to the database (decision of the user, 2026-10-08)
def test_the_database_block_refuses_every_way_to_connect(monkeypatch):
    import db
    import pyodbc
    from sqlalchemy.engine import Engine
    monkeypatch.setenv("SALE_FORECAST_DB_EXPECTED", "1")          # these attempts are the block's own test: the session count does not charge them to a test
    with pytest.raises(db.DatabaseBlockedError, match="refused"):
        db.run_query("SELECT 1")                                  # the project's own helper
    with pytest.raises(db.DatabaseBlockedError, match="refused"):
        with db.session():
            pass
    with pytest.raises(db.DatabaseBlockedError, match="pyodbc.connect"):
        pyodbc.connect("DRIVER={none};SERVER=none")
    with pytest.raises(db.DatabaseBlockedError, match="Engine.connect"):
        Engine.connect(None)


# ---------------------------------------------------------------------------
# No login name in any tracked file (rule of the project; Prompt 19). The Windows login comes from the environment, the DB login from the app's own credential source (.env, read without
# connecting). The messages name file:line only, never the value.
# ---------------------------------------------------------------------------
def _login_locations() -> dict:
    import subprocess
    from dotenv import dotenv_values
    values = {"Windows login": {os.environ.get("USERNAME", ""), os.path.basename(os.environ.get("USERPROFILE", ""))},
              "DB login": {str(dotenv_values(os.path.join(PROJECT_ROOT, ".env")).get("DB_USER") or "")},
              "DB host": {x.strip() for x in (str(dotenv_values(os.path.join(PROJECT_ROOT, ".env")).get("DB_SERVER") or ""),
                                                str(dotenv_values(os.path.join(PROJECT_ROOT, ".env")).get("DB_SERVER") or "").split(chr(92))[0].split(",")[0])}}
    values = {k: {v.lower() for v in vs if len(v) >= 4} for k, vs in values.items()}
    if os.path.isdir(os.path.join(PROJECT_ROOT, ".git")):
        files = [os.path.join(PROJECT_ROOT, f) for f in subprocess.run(["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout.split("\n") if f]
    else:
        files = scope_files()
    found = {k: [] for k in values}
    for f in files:
        if not os.path.isfile(f):
            continue
        with open(f, "rb") as fh:
            data = fh.read()
        if b"\0" in data[:4000]:
            continue
        for n, line in enumerate(data.decode("utf-8", errors="ignore").lower().split("\n"), 1):
            for kind, vs in values.items():
                if any(v in line for v in vs):
                    found[kind].append(f"{rel(f)}:{n}")
    found["_checked"] = {k: bool(v) for k, v in values.items()}
    return found


def test_no_windows_login_or_db_login_appears_in_a_tracked_file():
    import warnings
    found = _login_locations()
    checked = found.pop("_checked")
    assert checked["Windows login"], "the Windows login could not be read from the environment, so nothing was checked"
    missing = [k for k in ("DB login", "DB host") if not checked[k]]
    if missing:
        warnings.warn(f"{' and '.join(missing)} not readable from the credential source (.env): this run did not check for them", UserWarning)
        print(f"login scan: checked the Windows login only; not readable here: {', '.join(missing)}")
    for kind, locations in found.items():
        if kind in missing:
            continue
        assert not locations, f"a {kind} appears in: " + ", ".join(locations[:20])


# ====================================================================================================
# Prompt 38 (eight wordings) and Prompt 39 (the verb "to guess", the plain three-letter string, added as the ninth entry) and Prompt 40 (the old name of the Production Plan, the tenth entry; the original S&OP tab is skipped as for the others): wordings the readers must never see again: they are not in the visible text of index.html (outside the original S&OP tab), forecast/sales_report.html,
# inventory.html, operation_plan.html, material_plan.html, nor in the user-text sources (config/config.yaml and config/manual_notes.yaml string values,
# data/assumptions.json string values, docs/user_manual.md). Visible text = the text a reader sees in the static HTML (scripts, styles and comments dropped) plus the
# quoted strings of its scripts (script comments dropped) plus title/aria-label/placeholder/alt attributes. The words are built from parts so that this file does not hold them.
# DB product names: none of the words is in a product name of the saved pulls (collision count 0 when this was written); a collision would show here as a hit.
# ====================================================================================================
from html.parser import HTMLParser

BANNED_WORDS = ("ยอด" + "ทาย", "วิธี" + "เดาง่าย", "ของ" + "ค้าง", "สต็อ" + "ค", "สต็อ" + "ก", "Price" + "list", "ความคลาด" + "สะสม", "ค่า" + "ทาย", "ท" + "าย", "แผน" + "การผลิต", "เ" + "ดา", "ปรับให้ตรง" + "กับผลจริง", "ICT (" + "UTC+7)", "หน้า" + "สร้างเมื่อ")
BANNED_PAGES = ("index.html", "forecast/sales_report.html", "forecast/inventory.html", "forecast/operation_plan.html", "forecast/material_plan.html")
BANNED_SOURCES = ("config/config.yaml", "config/manual_notes.yaml", "data/assumptions.json", "docs/user_manual.md")
# Words and DB product-name text that contain the letters of the verb without being it (found in the saved pulls: a paint colour in product names; the others are ordinary Thai words).
# They are removed from a piece before the search, so they never count as a hit. Written out in full: this file is not one of the scanned user texts.
NOT_THE_VERB = ("เทาย่น", "ทายาท", "ทักทาย", "ท้าทาย")
ORIG_TAB_OPEN = '<div id="origTab">'
ORIG_TAB_CLOSE = "</div><!--/origTab-->"


class _PageText(HTMLParser):
    """Visible text and the text attributes of a static page; the content of <script> is kept apart, the content of <style> is dropped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts, self.scripts, self._in = [], [], None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("title", "aria-label", "placeholder", "alt") and value:
                self.texts.append(value)
        if tag in ("script", "style"):
            self._in, self._buf = tag, []

    def handle_endtag(self, tag):
        if tag == self._in:
            if tag == "script":
                self.scripts.append("".join(self._buf))
            self._in = None

    def handle_data(self, data):
        if self._in is None:
            if data.strip():
                self.texts.append(data)
        else:
            self._buf.append(data)


def _js_strings(code: str) -> list:
    """The quoted strings of a script, comments dropped."""
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c == "/" and code[i + 1:i + 2] == "/":
            j = code.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and code[i + 1:i + 2] == "*":
            j = code.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "'\"`":
            j, buf = i + 1, []
            while j < n and code[j] != c:
                if code[j] == "\\":
                    buf.append(code[j:j + 2])
                    j += 2
                    continue
                buf.append(code[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
        else:
            i += 1
    return out


def _page_texts(html_text: str, name: str) -> list:
    if name == "index.html":
        assert html_text.count(ORIG_TAB_OPEN) == 1 and html_text.count(ORIG_TAB_CLOSE) == 1, "the markers of the original S&OP tab are not where the guard expects them"
        html_text = html_text.split(ORIG_TAB_OPEN)[0] + html_text.split(ORIG_TAB_CLOSE)[1]
    p = _PageText()
    p.feed(html_text)
    p.close()
    return p.texts + [t for code in p.scripts for t in _js_strings(code)]


def _source_strings(text: str, path: str) -> list:
    import json as _json
    import yaml as _yaml

    def walk(o):
        if isinstance(o, str):
            yield o
        elif isinstance(o, dict):
            for k, v in o.items():
                yield from walk(k)
                yield from walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                yield from walk(v)

    if path.endswith(".yaml"):
        return list(walk(_yaml.safe_load(text)))
    if path.endswith(".json"):
        return list(walk(_json.loads(text)))
    return [text]


def banned_wording_hits(root: str) -> list:
    """(file, word, 40 characters around it) for every banned word in the pages' reader text and in the user-text sources under `root`."""
    found = []
    for rel_path, kind in [(p, "page") for p in BANNED_PAGES] + [(p, "source") for p in BANNED_SOURCES]:
        with open(os.path.join(root, rel_path), encoding="utf-8") as f:
            text = f.read()
        pieces = _page_texts(text, rel_path) if kind == "page" else _source_strings(text, rel_path)
        for piece in pieces:
            for allowed in NOT_THE_VERB:
                piece = piece.replace(allowed, "")
            for word in BANNED_WORDS:
                i = piece.find(word)
                if i >= 0:
                    found.append((rel_path, word, piece[max(0, i - 20):i + len(word) + 20].replace("\n", " ")))
    return found


def test_none_of_the_banned_wordings_is_in_the_reader_text_of_the_pages_or_in_the_user_text_sources():
    hits = banned_wording_hits(PROJECT_ROOT)
    assert not hits, f"banned wording found: {[(f, w) for f, w, _ in hits][:20]}"


def test_the_banned_wording_guard_fails_when_one_word_is_injected_into_a_temporary_copy_and_ignores_comments_and_the_original_tab(tmp_path):
    import shutil
    for rel_path in BANNED_PAGES + BANNED_SOURCES:
        os.makedirs(os.path.dirname(os.path.join(str(tmp_path), rel_path)) or str(tmp_path), exist_ok=True)
        shutil.copyfile(os.path.join(PROJECT_ROOT, rel_path), os.path.join(str(tmp_path), rel_path))
    assert banned_wording_hits(str(tmp_path)) == [], "the copy must start clean"
    word = BANNED_WORDS[0]

    def edit(rel_path, fn):
        p = os.path.join(str(tmp_path), rel_path)
        with open(p, encoding="utf-8", newline="") as f:
            s = f.read()
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(fn(s))

    # not seen by a reader: an HTML comment, a script comment, the original S&OP tab
    edit("forecast/operation_plan.html", lambda s: s.replace("</body>", "<!-- " + word + " --><script>// " + word + "\n</script></body>", 1))
    edit("index.html", lambda s: s.replace(ORIG_TAB_OPEN, ORIG_TAB_OPEN + "<p>" + word + "</p>", 1))
    assert banned_wording_hits(str(tmp_path)) == []
    # seen by a reader: page text, a script string, a title attribute, a yaml value, a json value, the manual, the executive tab of index.html
    edit("forecast/material_plan.html", lambda s: s.replace("</body>", "<p>" + word + "</p></body>", 1))
    edit("forecast/inventory.html", lambda s: s.replace("</body>", "<script>var t = '" + word + "';</script></body>", 1))
    edit("forecast/sales_report.html", lambda s: s.replace("</body>", '<span title="' + word + '">x</span></body>', 1))
    edit("config/manual_notes.yaml", lambda s: s.rstrip("\n") + '\nextra_key:\n  - "' + word + '"\n')
    edit("data/assumptions.json", lambda s: s.rstrip().rstrip("}").rstrip() + ', "extra": "' + word + '"}')
    edit("docs/user_manual.md", lambda s: s + "\n" + word + "\n")
    edit("index.html", lambda s: s.replace('<div id="execTab">', '<div id="execTab"><p>' + word + "</p>", 1))
    got = sorted({f for f, _, _ in banned_wording_hits(str(tmp_path))})
    assert got == sorted(["forecast/material_plan.html", "forecast/inventory.html", "forecast/sales_report.html", "config/manual_notes.yaml", "data/assumptions.json", "docs/user_manual.md", "index.html"])


def test_the_banned_wording_guard_ignores_product_names_and_words_that_only_contain_the_letters_of_the_verb(tmp_path):
    import shutil
    for rel_path in BANNED_PAGES + BANNED_SOURCES:
        os.makedirs(os.path.dirname(os.path.join(str(tmp_path), rel_path)) or str(tmp_path), exist_ok=True)
        shutil.copyfile(os.path.join(PROJECT_ROOT, rel_path), os.path.join(str(tmp_path), rel_path))
    p = os.path.join(str(tmp_path), "forecast", "material_plan.html")
    with open(p, encoding="utf-8", newline="") as f:
        s = f.read()
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s.replace("</body>", "<p>" + " ".join(NOT_THE_VERB) + "</p></body>", 1))
    assert banned_wording_hits(str(tmp_path)) == []
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s.replace("</body>", "<p>" + " ".join(NOT_THE_VERB) + " " + BANNED_WORDS[-1] + "ต่ำกว่าจริง</p></body>", 1))
    assert [w for _, w, _ in banned_wording_hits(str(tmp_path))] == [BANNED_WORDS[-1]]
