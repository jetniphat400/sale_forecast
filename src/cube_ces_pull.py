"""Shared Cube_CES pull helper.

Trap (DATA_MAP.md Sec.4, #18, fixed 2026-09-25): a Q23 investigation script
(`src/investigations/phaseQ23_explorer.py`) added a `CtrDate >= '2023-01-01'` filter to its
Cube_CES pull that looked harmless but was NOT equivalent to this project's established `not_late`
method (METRICS.md Sec.18/19/20: `ForecastDelDate`-windowed, no `CtrDate` filter at pull time). It
silently dropped legitimate rows -- a contract created (`CtrDate`) before 2023 can still have a
delivery (`ForecastDelDate`/`ActualDelDate`) that falls inside a 2024+ analysis window -- and
produced a `not_late` figure unrecognizable against this project's own established headline.

This module is the one place any future script should pull Cube_CES for an item-code scope: no
date filter at pull time, ever (the established, working pattern already used successfully by
`output/data/phaseJ_cube_ces_351items.csv` and `src/investigations/phaseJ3_validator_reconciliation.py`
-- both pull the full, unbounded history for the scope and apply any date WINDOW later, in Python,
against `ForecastDelDate`/`CtrDate` as the analysis requires, never as a SQL floor that silently
discards rows before the analysis logic ever sees them).
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import run_query

logger = logging.getLogger("cube_ces_pull")

CUBE_CES_COLUMNS = [
    "ItemCode", "ContractID", "Status", "CtrDate", "PlanDelDate", "ForecastDelDate",
    "ActualDelDate", "ActualQty", "RevenueType", "CustomerID", "CustomerName",
]


def pull_cube_ces_for_items(item_codes: list, columns: list = None):
    """Pulls Cube_CES rows for `item_codes`, with NO date filter of any kind at the SQL level --
    the scope is itemcode only. Any date window (calibration/validation periods, a specific year,
    etc.) must be applied afterward in Python against whichever date field the analysis actually
    needs (`ForecastDelDate` for `not_late`, METRICS.md Sec.18/19/20), never re-added here as a
    pull-time floor -- that is exactly the mistake this module exists to prevent (see module
    docstring, DATA_MAP.md Trap 18).
    """
    cols = columns or CUBE_CES_COLUMNS
    code_list = "','".join(item_codes)
    col_list = ", ".join(cols)
    sql = f"""
        SELECT {col_list}
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
    """
    df = run_query(sql)
    logger.info("Pulled %d Cube_CES rows for %d item codes (no date filter at pull -- "
                "any date window is applied afterward, never as a SQL floor).",
                len(df), len(item_codes))
    return df
