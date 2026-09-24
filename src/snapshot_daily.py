"""Prospective posting-delay measurement (Part 3 follow-up, STATUS.md 2026-09-22 posting-delay
entry): a daily snapshot of cube_Sale_APD's row counts and max dates, because the retrospective
question ("when did a row first become visible?") cannot be answered from the table as it stands
-- `timeStamp` is a full-table-reload artifact (STATUS.md, confirmed a 4th independent time), and
no insert/modified-date column exists. Going forward, comparing consecutive daily snapshots'
per-createDate row counts can reveal when a business-dated row actually appeared, instead.

Records, once per run: run timestamp, total in-scope row count, per-createDate row counts for the
last 60 calendar days (embedded as one JSON field, so the file stays one line per run), and
max(createDate)/max(forecast_date). Appended to output/snapshots/posting_delay.csv.

Also records cube_final's own total row count (table-wide, no filter), added this task (Part 0)
after DATA_MAP.md Sec.4 Trap 7: cube_final returned zero rows for in-scope items during Phase J2/J3
pulls, then the identical query returned 28,000 rows a day later -- the "table was being reloaded"
explanation was never established, only hypothesised. Recording this count daily means a future
empty window is a recorded FACT in this file, not something inferred after the fact from an
unrelated pull's failure.

Scope matches this project's standing "project scope" filter (identical to
src/phaseE1_common.py::query_order_level): revenue_type = config['revenue_type'],
status IN config['status_basis'], createDate >= config['date_range']['start'].

Idempotent for a given calendar day: if a row for today's date already exists, it is REPLACED by
this run's snapshot (not duplicated) -- so the file holds at most one row per calendar day, always
reflecting that day's latest run.

Never writes credentials: only calls src/db.py::run_query, which returns a DataFrame -- this
script never touches the connection string, .env contents, or credential env vars directly, and
nothing here logs them.

DATABASE ACCESS RULE: one connection attempt only. If it fails, stop and report -- nothing here
retries a failed login.
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import run_query  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("snapshot_daily")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "output", "snapshots")
SNAPSHOT_CSV = os.path.join(SNAPSHOT_DIR, "posting_delay.csv")

SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
CUBE_FINAL_TABLE = "[salewarehouse].[dbo].[cube_final]"
LOOKBACK_DAYS = 60


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def take_snapshot(config: dict) -> dict:
    """Single DB connection attempt: one query, project-scope-filtered. If it fails, the caller
    stops and reports (DATABASE ACCESS RULE) -- no retry."""
    statuses = "','".join(config["status_basis"])
    start_date = config["date_range"]["start"]
    sql = f"""
        SELECT createDate, forecast_date
        FROM {SALE_TABLE}
        WHERE revenue_type = '{config["revenue_type"]}'
          AND status IN ('{statuses}')
          AND createDate >= '{start_date}'
    """
    df = run_query(sql)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")

    cube_final_count_df = run_query(f"SELECT COUNT(*) AS n_rows FROM {CUBE_FINAL_TABLE}")
    cube_final_total_row_count = int(cube_final_count_df["n_rows"].iloc[0])

    run_ts = datetime.now()
    today = run_ts.date()
    window_start = today - timedelta(days=LOOKBACK_DAYS - 1)

    recent = df[(df["createDate"].dt.date >= window_start) & (df["createDate"].dt.date <= today)]
    counts_by_createdate = (
        recent.groupby(recent["createDate"].dt.date.astype(str)).size().to_dict()
    )

    snapshot = {
        "run_date": today.isoformat(),
        "run_timestamp": run_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "total_row_count": int(len(df)),
        "max_createDate": df["createDate"].max().date().isoformat() if df["createDate"].notna().any() else "",
        "max_forecast_date": df["forecast_date"].max().date().isoformat() if df["forecast_date"].notna().any() else "",
        "counts_by_createdate_json": json.dumps(counts_by_createdate, sort_keys=True),
        "cube_final_total_row_count": cube_final_total_row_count,
    }
    logger.info("Snapshot: %d rows in scope; max createDate=%s; max forecast_date=%s; "
                "%d distinct createDates in the last %d days; cube_final table-wide row count=%d.",
                snapshot["total_row_count"], snapshot["max_createDate"], snapshot["max_forecast_date"],
                len(counts_by_createdate), LOOKBACK_DAYS, cube_final_total_row_count)
    return snapshot


def append_snapshot(snapshot: dict) -> None:
    """Idempotent for a given calendar day: replaces any existing row with the same run_date
    rather than appending a duplicate."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    columns = ["run_date", "run_timestamp", "total_row_count", "max_createDate",
               "max_forecast_date", "counts_by_createdate_json", "cube_final_total_row_count"]

    if os.path.exists(SNAPSHOT_CSV):
        existing = pd.read_csv(SNAPSHOT_CSV, dtype=str)
        replaced = (existing["run_date"] == snapshot["run_date"]).any()
        existing = existing[existing["run_date"] != snapshot["run_date"]]
    else:
        existing = pd.DataFrame(columns=columns)
        replaced = False

    new_row = pd.DataFrame([{k: str(snapshot[k]) for k in columns}])
    out = pd.concat([existing, new_row], ignore_index=True)
    out.to_csv(SNAPSHOT_CSV, index=False, columns=columns)
    action = "Replaced today's existing row" if replaced else "Appended new row"
    logger.info("%s -- %s now has %d row(s) total.", action, SNAPSHOT_CSV, len(out))


def main():
    config = load_config()
    try:
        snapshot = take_snapshot(config)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: first connection attempt failed, stopping. Error: %s", exc)
        raise
    append_snapshot(snapshot)


if __name__ == "__main__":
    main()
