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

The same module also holds the two small, stdlib-only helpers the scheduled jobs share (Prompt 45; they are here because this module imports no pandas, so a job can use it as its very
first act, and because a new module was not allowed): `write_start_marker` (one line per start of the daily and the monthly job, before any heavy import) and `run_process` (subprocess.run
with a bounded retry only when the operating system refused to CREATE the child process, WinError 5).
"""
import linecache
import logging
import os
import subprocess
import time
from datetime import datetime

logger = logging.getLogger("zero_row_guard")

START_MARKER_FILE = "start_markers.log"
PROCESS_ATTEMPTS = 3
PROCESS_RETRY_WAIT_SECONDS = 15.0


def write_start_marker(folder: str, script: str, now: datetime = None) -> None:
    """Appends "<ISO time> start pid=<pid> script=<name>" to <folder>/start_markers.log. Never raises and never changes anything else: a marker must not be able to stop or alter a job.
    A start with no marker means the git pull or the interpreter failed; a marker with no run log means python died early."""
    try:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, START_MARKER_FILE), "a", encoding="utf-8") as f:
            f.write(f"{(now or datetime.now()).isoformat(timespec='seconds')} start pid={os.getpid()} script={script}\n")
    except Exception:      # noqa: BLE001 -- swallowed on purpose (an unwritable folder, a full disk, anything)
        pass


def _failed_at_process_creation(exc: BaseException) -> bool:
    """True when `exc` was raised by the CreateProcess call inside subprocess._execute_child: the operating system refused to create the child, so nothing ran. A PermissionError raised anywhere
    else (reading the pipes, killing a child after a timeout) has no such frame and is never retried."""
    tb = exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        if code.co_name == "_execute_child" and code.co_filename == subprocess.__file__ and "CreateProcess" in linecache.getline(code.co_filename, tb.tb_lineno):
            return True
        tb = tb.tb_next
    return False


def run_process(cmd, *, attempts: int = PROCESS_ATTEMPTS, wait: float = PROCESS_RETRY_WAIT_SECONDS, sleep=time.sleep, **kwargs):
    """subprocess.run(cmd, **kwargs), tried at most `attempts` times in all, `wait` seconds apart, and ONLY when process creation itself raised PermissionError with winerror 5 (the child
    never started, so no work was done and no database login can be repeated). The last such error, and every other exception, is raised unchanged; a non-zero exit code is returned
    (or raised by check=True) as subprocess.run does, never retried."""
    for attempt in range(1, attempts + 1):
        try:
            return subprocess.run(cmd, **kwargs)
        except PermissionError as exc:
            if getattr(exc, "winerror", None) != 5 or not _failed_at_process_creation(exc) or attempt >= attempts:
                raise
            logger.warning("Could not create the child process (attempt %d of %d, WinError 5 at creation): retrying in %s s: %s", attempt, attempts, wait, os.path.basename(str(cmd[0])))
            sleep(wait)


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
