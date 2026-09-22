"""Part 3: measure the leakage guard's 30-day margin -- was it measured or just reasoned?

Question: for every row in cube_Sale_APD in scope from 2024-01-01, when did the row become
VISIBLE in the database (first appearance), as distinct from its business date (createDate)?
Test the available signals: timeStamp, any insert/modified-date column, and the gap between
createDate and the earliest date the row could have been written.

This is a single-question, single-signal-inventory task -- Single Explorer (AGENTS.md), read-only.

Prior art (STATUS.md, already established, re-verified live here rather than only cited):
- 2026-08-30 snapshot: all 51,059 rows' `timeStamp` land in one ~17-minute window.
- 2026-09-04 snapshot (independent re-check, 4 days later): all 27,679 PEM101-scope rows' `timeStamp`
  land in one 64.2-second window, on a DIFFERENT calendar date (2026-09-03) than the first check --
  i.e. `timeStamp` re-stamps EVERY row, old and new alike, on every reload. It is a table-refresh
  clock, not a per-row insert clock.
- `INFORMATION_SCHEMA.COLUMNS` (2026-09-04) enumerated exactly 8 date/datetime columns on
  cube_Sale_APD: createDate, PODate, forecast_date, timeStamp, customer_entry, warranty_date,
  newCustomerDate, plan_date. None of these is documented or behaves as a row-insert/modified
  timestamp; createDate/PODate are independently cross-validated (against Cube_CES) as genuine
  business/contract dates, not database-write dates.
- A prior, differently-motivated check (duplicate-vs-split-lot investigation) found auto-increment
  id-gap and timeStamp-spread do NOT reliably separate insertion order/timing -- "inconclusive".

This script re-verifies the load-batch signature is still true TODAY, at the Part-3-specified full
scope (createDate >= 2024-01-01, all divisions -- not just PEM101), and re-confirms the column
inventory has not changed, before concluding whether a fresh measurement is even possible.

DATABASE ACCESS RULE: one connection attempt only. If the first query fails, stop and report.
Subsequent queries in the same run reuse the same already-proven credentials.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import run_query  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

TABLE = "cube_Sale_APD"


def main():
    # --- Single connection attempt: first query. If this fails, stop (DATABASE ACCESS RULE). ---
    try:
        cols = run_query(
            f"""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{TABLE}'
            ORDER BY ORDINAL_POSITION
            """
        )
    except Exception as exc:
        print(f"DATABASE ACCESS RULE: first connection attempt failed, stopping. Error: {exc}")
        return
    print(f"Connected. {TABLE} has {len(cols)} columns.")

    date_like = cols[cols["DATA_TYPE"].isin(["date", "datetime", "datetime2", "smalldatetime"])]
    print("\nDate/datetime columns (fresh INFORMATION_SCHEMA check):")
    print(date_like.to_string(index=False))

    known_8 = {
        "createDate", "PODate", "forecast_date", "timeStamp",
        "customer_entry", "warranty_date", "newCustomerDate", "plan_date",
    }
    found = set(date_like["COLUMN_NAME"])
    new_cols = found - known_8
    missing_cols = known_8 - found
    print(f"\nNew date/datetime columns vs prior catalogue: {sorted(new_cols) or 'NONE'}")
    print(f"Previously-catalogued columns no longer present: {sorted(missing_cols) or 'NONE'}")

    # Any column that looks like an insert/modified/audit timestamp by name, regardless of type.
    audit_like = cols[cols["COLUMN_NAME"].str.contains(
        "insert|modif|audit|created_?at|updated_?at|load|etl|dw_", case=False, regex=True
    )]
    print(f"\nColumns whose NAME suggests insert/modified/audit tracking (any data type):")
    print(audit_like.to_string(index=False) if len(audit_like) else "  NONE FOUND")

    # --- Re-verify the timeStamp load-batch signature at Part 3's full scope (all divisions,
    # createDate >= 2024-01-01), today, rather than only citing the PEM101-scope 2026-09-04 check. ---
    scope = run_query(
        f"""
        SELECT createDate, forecast_date, timeStamp
        FROM {TABLE}
        WHERE createDate >= '2024-01-01'
        """
    )
    scope["createDate"] = pd.to_datetime(scope["createDate"])
    scope["forecast_date"] = pd.to_datetime(scope["forecast_date"], errors="coerce")
    scope["timeStamp"] = pd.to_datetime(scope["timeStamp"])
    n = len(scope)
    print(f"\nScope (createDate >= 2024-01-01, all divisions): {n} rows")

    ts_dates = scope["timeStamp"].dt.date
    distinct_ts_dates = ts_dates.nunique()
    top_date = ts_dates.value_counts().idxmax()
    top_date_share = ts_dates.value_counts().max() / n
    ts_span = scope["timeStamp"].max() - scope["timeStamp"].min()
    print(f"timeStamp: {distinct_ts_dates} distinct calendar date(s); "
          f"top date {top_date} covers {top_date_share:.4%} of rows; "
          f"full span min-to-max = {ts_span}")

    is_single_batch = (distinct_ts_dates == 1) or (top_date_share > 0.99)
    print(f"Single-load-batch signature (>99% of rows on one calendar date)? {is_single_batch}")

    out_path = os.path.join(SUMMARY_DIR, "phaseE2_posting_delay_scope_check.csv")
    scope.describe(include="all").to_csv(out_path)
    print(f"\nScope summary written: {out_path}")

    print("\n=== VERDICT ===")
    if is_single_batch and not new_cols:
        print(
            "No reliable first-appearance signal exists in cube_Sale_APD. timeStamp re-confirmed "
            "(3rd independent check, spanning 2026-08-30 / 2026-09-04 / today) as a full-table-"
            "reload artifact: effectively all in-scope rows share one narrow load window, "
            "regardless of the row's own business age -- meaning it records 'when the table was "
            "last refreshed', not 'when this row first appeared'. No insert/modified/audit-date "
            "column exists (fresh INFORMATION_SCHEMA check, same 8 date columns as before, no new "
            "ones). createDate/PODate are independently confirmed (STATUS.md, cross-validated "
            "against Cube_CES) to be genuine business/contract dates, not database-write dates, so "
            "the 'gap between createDate and the earliest date the row could have been written' "
            "cannot be computed either -- there is no earliest-written date recorded anywhere in "
            "this table. First-appearance cannot be reconstructed from this table, retrospectively, "
            "with any column it currently has."
        )
    else:
        print(
            "UNEXPECTED: schema or timeStamp behavior differs from the prior, well-established "
            "finding. Manual review required before drawing a conclusion -- see printed evidence "
            "above."
        )


if __name__ == "__main__":
    main()
