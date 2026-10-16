"""The daily job's entry point (the scheduled task starts it). Once per run, inside ONE database session
(src/db.py session()): the per-item, per-warehouse stock snapshot of the Price List codes
(output/snapshots/inventory_daily_YYYY-MM-DD.csv, one file per day, overwritten if run again the same day), then
the daily stock job (src/daily_stock_job.py: the published data files).

The prospective posting-delay measurement that used to run here (a daily row count of cube_Sale_APD and of
cube_final, appended to output/snapshots/posting_delay.csv) was removed on 2026-10-12 (Prompt 27): it was not limited
to the Price List items and no page reads it. The existing posting_delay.csv is kept as it was; it no longer grows.

Never writes credentials: every query goes through src/db.py (one session, one login attempt), which
returns DataFrames -- this script never touches the connection string, .env contents, or credential
env vars directly, and nothing here logs them.

DATABASE ACCESS RULE: one connection attempt only. If it fails, stop and report -- nothing here
retries a failed login.
"""
import logging
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import query_inventory_exact  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("snapshot_daily")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "output", "snapshots")

REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference")


def take_inventory_snapshot() -> pd.DataFrame:
    """Task 2b, Part 5: per-item, per-warehouse on-hand quantity from Cube_Inventory_Exact, once
    per day -- so PEM103/PEM107's live-pulled inventory.html figures (never otherwise persisted)
    can be independently re-verified after the fact. Item scope: every code on reference/
    pricelist.xlsx's VISIBLE sheets (PRICELIST RULE) -- the full 445/446-code registry, not just
    whichever division happens to be selected on any one page. Reuses
    src/phaseE1_common.py::query_inventory_exact (same helper build_inventory_page_data.py already
    uses) rather than a new query shape."""
    pl = load_visible_product_rows(os.path.join(REFERENCE_DIR, "pricelist.xlsx"))
    codes = sorted(pl["code"].unique())
    inv = query_inventory_exact(codes, allow_empty=True)
    load_timestamp = pd.to_datetime(inv["timestamp"]).min() if len(inv) and inv["timestamp"].notna().any() else pd.Timestamp.now()
    # minimum/maximum/reserve_bywa are kept too (task M2): the Min-Max page shows the settings now in the
    # system, and the monthly runner builds that page from this snapshot.
    inv = inv[["itemcode", "warehouse", "stock", "minimum", "maximum", "reserve_bywa"]].copy()
    inv["load_timestamp"] = load_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Inventory snapshot: %d (item, warehouse) rows for %d pricelist codes, "
                "load_timestamp=%s.", len(inv), len(codes), inv["load_timestamp"].iloc[0] if len(inv) else "n/a")
    return inv


def write_inventory_snapshot(inv: pd.DataFrame) -> str:
    """One dated file per day (output/snapshots/inventory_daily_YYYY-MM-DD.csv), overwritten if
    run again the same day."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    today = datetime.now().date().isoformat()
    path = os.path.join(SNAPSHOT_DIR, f"inventory_daily_{today}.csv")
    inv.to_csv(path, index=False)
    size_kb = os.path.getsize(path) / 1024
    logger.info("Inventory snapshot written: %s (%.1f KB, %d rows).", path, size_kb, len(inv))
    return path


def is_weekday(now=None) -> bool:
    """Monday to Friday: the daily job does nothing at the weekend."""
    return (now or datetime.now()).weekday() < 5


def main():
    """The stock snapshot, then the daily stock job (published data files), all inside ONE database session
    (src/db.py session()). A failure of the stock job never loses the snapshot: the snapshot is written first, and the
    stock job's failure is raised afterwards (non-zero exit, log under output/runs/daily/). The scheduled task starts it at 08:00 and again at 12:00; the second start does nothing when a successful
    run of today already exists (--force overrides)."""
    import daily_stock_job as djob
    import db
    from db import session
    logger.info("%s", djob.env_line())          # first, before the weekend exit, the lock check, the preflight and any database step: the visible-to-the-task proof of the backup variable
    if not is_weekday():      # Monday to Friday only: a missed Friday start that Task Scheduler launches at the weekend does nothing, before any lock check, preflight or login
        logger.info("Not a weekday: the daily job runs Monday to Friday only; nothing done.")
        return
    try:
        db.check_refused_lock()           # before the preflight and before any login
    except db.LoginRefused as exc:
        logger.error("%s", exc)
        raise SystemExit(db.EXIT_LOGIN_REFUSED)
    root_config = djob.load_config()
    try:
        djob.check_publishing_setup(PROJECT_ROOT, root_config)        # before any database session: a run from the wrong folder does nothing
    except djob.DailyStop as exc:
        logger.error("Daily stock job stopped (%s): %s", exc.step, exc)
        djob.record_failure(PROJECT_ROOT, root_config, exc.step, exc)
        raise SystemExit(1)
    # The task runs twice a day (08:00 and a 12:00 retry). A run that finds a successful daily run of today exits before it connects.
    existing = None if "--force" in sys.argv[1:] else djob.successful_run_today(PROJECT_ROOT, root_config)
    if existing:
        logger.info("Skipped: a successful daily run of today exists (run %s, %s). Log: %s", existing.get("run_id"), existing.get("status"),
                    djob.record_skip(PROJECT_ROOT, root_config, existing))
        return
    try:
        db.require_reachable()                # a plain TCP connect, no authentication: off the organisation's network no login is attempted
    except db.DatabaseUnreachableError as exc:
        logger.error("%s", exc)
        djob.record_failure(PROJECT_ROOT, root_config, "database host unreachable", exc)
        raise SystemExit(1)
    base = djob.load_base(PROJECT_ROOT, root_config)      # before today's snapshot file is written below
    try:
        with session():
            try:
                inv_snapshot = take_inventory_snapshot()
            except Exception as exc:
                logger.error("DATABASE ACCESS RULE: first connection attempt failed, stopping. Error: %s", exc)
                raise
            write_inventory_snapshot(inv_snapshot)
            djob.run(PROJECT_ROOT, base=base, config=root_config)
    except db.LoginRefused as exc:       # the server refused the login: the lock is written, the job ends with exit code 3
        logger.error("%s", exc)
        djob.record_failure(PROJECT_ROOT, root_config, "database login refused", RuntimeError("Login failed (SQLSTATE 28000, refused by the server)"))
        raise SystemExit(db.EXIT_LOGIN_REFUSED)
    except djob.DailyFailure as exc:
        logger.error("Daily stock job failed (%s): %s -- the stock snapshot above was kept.", exc.gate or exc.step, exc)
        raise SystemExit(1)
    except Exception as exc:     # login failure or a failure of the snapshot itself: no stock job log exists yet
        djob.record_failure(PROJECT_ROOT, root_config, "database session or stock snapshot", exc)
        raise


if __name__ == "__main__":
    main()
