"""Pytest configuration shared by every test module.

Adds src/ to sys.path so tests can import project modules the same way the
scripts in src/ import each other (sys.path.insert(0, os.path.dirname(__file__))),
without needing the project installed as a package.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


# ------------------------------------------------------------------ the test suite never touches the database (decision of the user, 2026-10-08)
import tempfile  # noqa: E402

import pytest  # noqa: E402

os.environ["SALE_FORECAST_BLOCK_DB"] = "1"                      # inherited by every Python process a test starts (src/db.py refuses when it is set)
_BLOCK_LOG = os.path.join(tempfile.mkdtemp(prefix="db_block_"), "attempts.log")
os.environ["SALE_FORECAST_DB_BLOCK_LOG"] = _BLOCK_LOG
os.environ["SALE_FORECAST_DB_EXPECTED"] = "0"


def _refuse(where):
    import db
    db.refuse_if_blocked(where)


@pytest.fixture(scope="session", autouse=True)
def _no_database_connection():
    """Makes every way to open a connection raise at once: the project's helper (src/db.py), pyodbc and SQLAlchemy's engine. A test that would have connected fails loudly;
    a refusal that code swallows is still counted and fails the session (pytest_sessionfinish)."""
    import pyodbc
    from sqlalchemy.engine import Engine
    real_connect, real_engine_connect = pyodbc.connect, Engine.connect

    def blocked_pyodbc(*a, **k):
        _refuse("pyodbc.connect")

    def blocked_engine(self, *a, **k):
        _refuse("sqlalchemy Engine.connect")
    pyodbc.connect, Engine.connect = blocked_pyodbc, blocked_engine
    try:
        yield
    finally:
        pyodbc.connect, Engine.connect = real_connect, real_engine_connect


def _block_counts():
    if not os.path.exists(_BLOCK_LOG):
        return 0, 0
    rows = [l.split("|") for l in open(_BLOCK_LOG, encoding="utf-8").read().splitlines() if l.strip()]
    return len(rows), sum(1 for r in rows if r[0] == "1")


def pytest_terminal_summary(terminalreporter):
    total, deliberate = _block_counts()
    terminalreporter.write_line(f"database connection attempts: {total - deliberate} (blocked attempts {total}, of which {deliberate} deliberate, made by the block's own test)")


def pytest_sessionfinish(session, exitstatus):
    total, deliberate = _block_counts()
    if total - deliberate > 0 and session.exitstatus == 0:
        session.exitstatus = 1                                  # a refusal that code swallowed is still an attempt
