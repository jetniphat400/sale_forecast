"""Database connection helper. Loads credentials from .env — never hardcode them here."""
import contextlib
import os
import urllib.parse

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# PROJECT_ROOT from __file__, never os.getcwd() (CONVENTIONS.md: no hardcoded absolute paths;
# paths relative to the project root) -- this module is imported by scripts that may be launched
# from any working directory (e.g. a Windows Scheduled Task running from C:\Windows\system32),
# so a bare load_dotenv() (which searches from the CURRENT WORKING DIRECTORY, not this file's
# location) could silently fail to find .env, leaving DB_SERVER/DB_PASSWORD/etc. unset. Task
# 2cfix2, this task.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"))

_REQUIRED_ENV_VARS = ["DB_SERVER", "DB_DATABASE", "DB_USER", "DB_PASSWORD", "DB_DRIVER"]

# The test suite must never connect (decision of the user, 2026-10-08). tests/conftest.py sets SALE_FORECAST_BLOCK_DB=1 for the whole test session; every Python process
# a test starts inherits it, so a connection attempt anywhere fails at once with DatabaseBlockedError instead of reaching the server. Each refusal is appended to the
# file named by SALE_FORECAST_DB_BLOCK_LOG (the test that was running, from PYTEST_CURRENT_TEST, and whether the attempt was deliberate) so a swallowed error is still counted.
BLOCK_ENV = "SALE_FORECAST_BLOCK_DB"


class DatabaseBlockedError(RuntimeError):
    """A database connection was attempted while tests have connections blocked."""


def refuse_if_blocked(where: str) -> None:
    if os.environ.get(BLOCK_ENV) != "1":
        return
    log = os.environ.get("SALE_FORECAST_DB_BLOCK_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write("|".join([os.environ.get("SALE_FORECAST_DB_EXPECTED", "0"), os.environ.get("PYTEST_CURRENT_TEST", "-").replace("|", "/"), where]) + chr(10))
    raise DatabaseBlockedError(f"database connection refused ({where}): the test suite must not connect to the database; run it from tracked data or a fixture")


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Copy .env.example to .env and fill in all values: {', '.join(_REQUIRED_ENV_VARS)}"
        )
    return value


def get_connection() -> Engine:
    """Build a SQLAlchemy engine (using pyodbc) from credentials in .env."""
    refuse_if_blocked("db.get_connection")
    server = _get_required_env("DB_SERVER")
    database = _get_required_env("DB_DATABASE")
    user = _get_required_env("DB_USER")
    password = _get_required_env("DB_PASSWORD")
    driver = _get_required_env("DB_DRIVER")

    odbc_connection_string = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};TrustServerCertificate=yes"
    )
    connection_url = "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(
        odbc_connection_string
    )
    return create_engine(connection_url)


# One shared connection for a job that must stay inside a single database session (the daily stock job).
# While a session() block is open, run_query reuses its connection instead of opening a new one per query;
# outside a block every call behaves as before.
_SHARED_CONNECTION = None


@contextlib.contextmanager
def session():
    """Opens ONE connection (one attempt, no retry: a login failure raises to the caller) and makes run_query use
    it until the block ends."""
    global _SHARED_CONNECTION
    if _SHARED_CONNECTION is not None:
        raise RuntimeError("a database session is already open")
    engine = get_connection()
    conn = engine.connect()
    _SHARED_CONNECTION = conn
    try:
        yield conn
    finally:
        _SHARED_CONNECTION = None
        conn.close()
        engine.dispose()


def run_query(sql: str) -> pd.DataFrame:
    """Run a read-only SQL query and return the result as a DataFrame."""
    if _SHARED_CONNECTION is not None:
        return pd.read_sql(sql, _SHARED_CONNECTION)
    engine = get_connection()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)
