"""Zero-row guard for shared database loaders (cube_Sale_APD, Cube_CES, Cube_Inventory_Exact,
cube_final). Raises when a query expected to return data returns none, naming the table, the
filter and the time -- instead of letting a silently-empty pull propagate downstream unnoticed.

Motivation (this task, Part 0): cube_final returned zero rows for in-scope items during Phase J2
and Phase J3 pulls, yet the identical query now returns 28,000 rows (DATA_MAP.md Sec.4 Trap 7,
resolved). The "table was being reloaded" explanation was never established -- it was a
hypothesis. If a cube can go empty during a reload (or for any other silent reason) without a
loud failure, a pipeline consuming it can receive nothing without anyone noticing. This guard
makes that failure loud by default; a caller that knows zero rows is a valid answer for its own
query must say so explicitly with `allow_empty=True`.
"""
import logging
from datetime import datetime

logger = logging.getLogger("zero_row_guard")


class EmptyQueryResultError(RuntimeError):
    """Raised when a shared loader's query returned zero rows and allow_empty was not set."""


def guard_nonempty(df, table: str, filter_desc: str, allow_empty: bool = False):
    """Raises EmptyQueryResultError if `df` has zero rows and `allow_empty` is False. Returns
    `df` unchanged otherwise, so this composes inline:
        df = guard_nonempty(run_query(sql), table="cube_final", filter_desc=f"itemcode IN (...)")
    """
    if len(df) == 0 and not allow_empty:
        raise EmptyQueryResultError(
            f"Zero rows returned from {table} (filter: {filter_desc}) at "
            f"{datetime.now().isoformat(timespec='seconds')}. A query expected to return data "
            f"returned none -- this may be a real absence, a data-timing/reload gap "
            f"(DATA_MAP.md Sec.4 Trap 7), or an upstream problem. Pass allow_empty=True "
            f"explicitly if zero rows is a valid answer for this specific call."
        )
    if len(df) == 0:
        logger.warning("Zero rows returned from %s (filter: %s) -- allowed explicitly "
                        "(allow_empty=True).", table, filter_desc)
    return df
