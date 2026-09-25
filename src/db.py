"""Database connection helper. Loads credentials from .env — never hardcode them here."""
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


def run_query(sql: str) -> pd.DataFrame:
    """Run a read-only SQL query and return the result as a DataFrame."""
    engine = get_connection()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)
