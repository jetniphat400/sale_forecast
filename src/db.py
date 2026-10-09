"""Database connection helper. Loads credentials from .env — never hardcode them here."""
import contextlib
import os
import socket
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


class DatabaseUnreachableError(RuntimeError):
    """The database host does not answer a plain TCP connect (for example the machine is off the organisation's network). No login was attempted."""


class DatabaseLoginAlreadyFailedError(RuntimeError):
    """A login already failed in this process: no further login attempt is made (an account can be locked by repeated attempts)."""


UNREACHABLE_MESSAGE = "DB host unreachable (off org network?)"
DEFAULT_PORT = 1433                  # SQL Server default; DB_SERVER names host\instance, so the port is an assumption for the reachability check only, never for the ODBC login itself

_LOGIN_ATTEMPTS = 0                  # engine.connect() calls made by this process (a successful login counts, a failed one counts)
_LOGIN_FAILURE = None                # the first login failure of this process, if any


def login_attempts() -> int:
    return _LOGIN_ATTEMPTS


def reset_login_state() -> None:
    """For tests only: forgets the attempt count and any recorded failure."""
    global _LOGIN_ATTEMPTS, _LOGIN_FAILURE
    _LOGIN_ATTEMPTS, _LOGIN_FAILURE = 0, None


def split_server(server: str) -> tuple:
    """(host, port) for the reachability check from DB_SERVER: `host`, `host\\instance` or `host,port`."""
    host = server.split("\\")[0].split(",")[0].strip()
    port = DEFAULT_PORT
    if "," in server:
        tail = server.split(",", 1)[1].split("\\")[0].strip()
        if tail.isdigit():
            port = int(tail)
    return host, port


def preflight(timeout: float = 5.0) -> dict:
    """A plain TCP connect to the DB host and port with a short timeout and NO authentication: no login is attempted. Returns {reachable, host, port, error}."""
    server = os.getenv("DB_SERVER", "")
    host, port = split_server(server)
    if not host:
        return {"reachable": False, "host": host, "port": port, "error": "DB_SERVER not set"}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"reachable": True, "host": host, "port": port, "error": None}
    except OSError as e:
        return {"reachable": False, "host": host, "port": port, "error": str(e)}


def require_reachable(timeout: float = 5.0) -> dict:
    """preflight(), raising DatabaseUnreachableError (message UNREACHABLE_MESSAGE) when the host does not answer; never logs in."""
    result = preflight(timeout)
    if not result["reachable"]:
        raise DatabaseUnreachableError(f"{UNREACHABLE_MESSAGE}: {result['host']}:{result['port']} ({result['error']})")
    return result


def _login(engine):
    """The ONE place a login happens: one attempt per call, never retried. After a failed login every later call in this process raises at once without connecting."""
    global _LOGIN_ATTEMPTS, _LOGIN_FAILURE
    if _LOGIN_FAILURE is not None:
        raise DatabaseLoginAlreadyFailedError(f"a database login already failed in this process ({_LOGIN_FAILURE}); no further login attempt is made")
    _LOGIN_ATTEMPTS += 1
    try:
        return engine.connect()
    except Exception as e:      # noqa: BLE001 -- remember it, then raise the original
        _LOGIN_FAILURE = type(e).__name__
        raise


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
    conn = _login(engine)
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
    with _login(engine) as conn:
        return pd.read_sql(sql, conn)
