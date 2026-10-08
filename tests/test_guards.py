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
# Scope: the project's markdown documents (STATUS, DATA_MAP, METRICS, PROJECT_GRAPH, AGENTS, CONVENTIONS), everything under config/, src/ and tests/ (.py .yaml .yml .md .json).
#
# Formats, as observed in the saved pulls (output/data and output/summary, which are untracked):
#   * customer ID   : two capital letters then five digits (the CustomerID / customerid columns of Cube_CES, cube_Sale_APD and Cube_Quotation);
#   * contract number: two to five capital letters, a hyphen, a four-digit year, a hyphen, five digits (the ContractID / contractid columns: contract, quotation and enquiry
#                     numbers share this shape);
#   * customer name : exact match against the values of the customer-name columns (cusname, customer_name, CustomerName) of the saved pulls, when those files are present;
#   * login name    : the user folder of a Windows path (Users, then a folder other than the placeholder <user>), and the login recorded in .env (DB_USER), when .env is present.
# The test reads files only; it holds no real identifier (the examples below are built from parts), and it modifies no tracked file. Where the saved pulls are absent the
# exact-match part is skipped with a message, never passed silently; the format part always runs.
# ====================================================================================================
import glob
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["STATUS.md", "DATA_MAP.md", "METRICS.md", "PROJECT_GRAPH.md", "AGENTS.md", "CONVENTIONS.md"]
SUFFIXES = (".py", ".yaml", ".yml", ".md", ".json")
CUSTOMER_ID = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{5}(?![A-Za-z0-9])")
CONTRACT_NO = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,5}-\d{4}-\d{5}(?![A-Za-z0-9])")
WINDOWS_USER = re.compile(r"Users[\\/]([^\\/\s`'\"]+)")
CUSTOMER_NAME_COLUMNS = ("cusname", "customer_name", "customername", "end_cusname")
MIN_NAME_LENGTH = 8


def scope_files() -> list:
    files = [os.path.join(PROJECT_ROOT, d) for d in DOCS]
    for top in ("config", "src", "tests"):
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


def test_no_customer_id_or_contract_number_in_documents_config_source_or_tests():
    files = scope_files()
    assert len(files) > 100, "the scope looks empty"
    found = hits(CUSTOMER_ID, files) + hits(CONTRACT_NO, files)
    assert not found, "customer IDs or contract numbers (CONVENTIONS.md): " + ", ".join(found[:20])


def test_no_personal_login_name_in_a_path_in_documents_config_source_or_tests():
    found = []
    for f in scope_files():
        for n, line in enumerate(read(f).splitlines(), 1):
            for m in WINDOWS_USER.finditer(line):
                if m.group(1) not in ("<user>", "Public", "Default", "All"):
                    found.append(f"{rel(f)}:{n}")
    assert not found, "a personal login name in a path (write <user>): " + ", ".join(found[:20])
    env = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env):
        login = [l.split("=", 1)[1].strip().strip('"').strip("'") for l in read(env).splitlines() if l.startswith("DB_USER=")]
        for name in login:
            if len(name) >= 4:
                assert not [f for f in scope_files() if name in read(f)], "the database login name appears in a file of the scope"


def _customer_names() -> set:
    import pandas as pd
    names = set()
    for f in glob.glob(os.path.join(PROJECT_ROOT, "output", "data", "*.csv")):
        try:
            cols = pd.read_csv(f, nrows=0).columns
        except Exception:
            continue
        for c in cols:
            if c.lower() in CUSTOMER_NAME_COLUMNS:
                names |= set(pd.read_csv(f, usecols=[c], dtype=str)[c].dropna().str.strip().unique())
    return {n for n in names if len(n) >= MIN_NAME_LENGTH and " " in n}


def _customer_ids() -> set:
    import pandas as pd
    ids = set()
    for f in glob.glob(os.path.join(PROJECT_ROOT, "output", "data", "*.csv")):
        try:
            cols = pd.read_csv(f, nrows=0).columns
        except Exception:
            continue
        for c in cols:
            if c.lower() in ("customerid", "customer_id", "end_customerid"):
                ids |= set(pd.read_csv(f, usecols=[c], dtype=str)[c].dropna().str.strip().unique())
    return {i for i in ids if len(i) >= 6}


def test_no_customer_name_or_id_from_the_saved_pulls_appears_by_exact_match():
    names, ids = _customer_names(), _customer_ids()
    if not names and not ids:
        pytest.skip("SKIPPED, not passed: the saved pulls are not on this machine, so the exact-match check could not run (the format checks above did)")
    texts = {f: read(f) for f in scope_files()}
    found = sorted({rel(f) for f, t in texts.items() for n in names if n in t} | {rel(f) for f, t in texts.items() for i in ids if i in t})
    assert not found, "a customer name or ID from the saved pulls appears in: " + ", ".join(found[:20])


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
