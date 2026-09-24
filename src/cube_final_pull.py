"""Shared cube_final pull helper.

Trap (DATA_MAP.md Sec.4, #7, resolved 2026-09-24): repeated pulls filtered `WHERE itemcode IN
(<351-item scope>)` returned ZERO rows across two separate task attempts (Phase J2, Phase J3),
even though the connections themselves succeeded and the table was confirmed non-empty by a later,
unfiltered diagnostic. This task (Phase 23, Part 0) re-ran the EXACT same itemcode join with a
fresh connection and it now returns real data at a reasonable match rate (28,000 rows, 264 of 351
in-scope items matched, 75.21% forward -- PEM101 87.50%, PEM103 36.78%, PEM107 88.24%; see
`output/summary/phase23_part0_cubefinal_join_report.md`). The join key itself (`itemcode` =
`itemcode`, exact string match, no format difference found between cube_final and cube_Sale_APD
samples) was never broken -- the prior zero-row pulls are best explained by a data-timing gap
(cube_final rows for these items had not yet been written at the time of those pulls), not a key
or format bug. This module exists so any future script pulls cube_final the same, now-verified way,
instead of re-deriving or re-doubting the join.

Pattern mirrors `src/cube_ces_pull.py` (DATA_MAP.md Trap 18): NO date filter at the SQL level, ever
-- any date window is applied afterward in Python against whichever date field the analysis needs
(e.g. `final_date` for batch timing), never as a pull-time floor that could silently exclude rows a
future pull would otherwise have found.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import run_query
from zero_row_guard import guard_nonempty

logger = logging.getLogger("cube_final_pull")

CUBE_FINAL_COLUMNS = [
    "id", "no", "finalid", "company", "division", "final_date", "finalcheck_date",
    "finalreceive_date", "jobno", "ctrno", "project", "customer_name", "pono", "itemcode",
    "descriptions", "cus_serialno", "job_qty", "transfer_history", "transfer_qty", "transfer_type",
    "ncrno", "qacheck_date", "fg_check_by", "fg_check_name", "fg_check_date", "fg_check_status",
    "fg_pack_name", "fg_pack_date", "fg_final_by", "fg_final_name", "fg_final_date",
    "fg_final_status", "note", "timsstamp", "serial_no",
]


def pull_cube_final_for_items(item_codes: list, columns: list = None, allow_empty: bool = False):
    """Pulls cube_final rows for `item_codes`, joined on the verified working key (`itemcode`,
    exact string match), with NO date filter of any kind at the SQL level -- the scope is itemcode
    only. Any date window (e.g. a specific batch period) must be applied afterward in Python
    against `final_date` or a neighbouring production-stage date column, never re-added here as a
    pull-time floor (DATA_MAP.md Trap 7/Trap 18 pattern).

    Raises `zero_row_guard.EmptyQueryResultError` if the pull returns zero rows, unless
    `allow_empty=True` is passed explicitly -- this is the exact failure mode DATA_MAP.md Trap 7
    documents (Phase J2/J3's zero-row pulls went unnoticed as a possible data problem rather than
    a real absence); this task's Part 0 zero-row guard makes that failure loud by default.
    """
    cols = columns or CUBE_FINAL_COLUMNS
    code_list = "','".join(item_codes)
    col_list = ", ".join(cols)
    sql = f"""
        SELECT {col_list}
        FROM [salewarehouse].[dbo].[cube_final]
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    guard_nonempty(df, table="cube_final", filter_desc=f"itemcode IN ({len(item_codes)} codes)",
                   allow_empty=allow_empty)
    logger.info("Pulled %d cube_final rows for %d item codes (itemcode join, no date filter at "
                "pull -- any date window is applied afterward).", len(df), len(item_codes))
    return df
