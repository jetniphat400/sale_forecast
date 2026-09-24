"""Part 0 -- cube_final diagnostic (independent, run first, one DB connection attempt).

Per this task's DATABASE ACCESS RULE: attempt the connection once. On a failed login, stop and
report; never retry. Three queries, run in the SAME session once connected (not separate
"attempts" -- the rule is about the login, not the query count):
  1. INFORMATION_SCHEMA.COLUMNS for cube_final (column list).
  2. SELECT COUNT(*) FROM cube_final (row count).
  3. TOP 10 rows filtered to cube_final's own most recent month (determined from MAX(final_date)
     in the same table, not assumed).

Does not block the rest of this task (per instruction) -- reported to DATA_MAP.md/STATUS.md
regardless of outcome.
"""
import logging
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase22_cubefinal_diagnostic")


def main():
    # --- Query 1: column list ---
    try:
        cols = run_query("""
            SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'cube_final'
            ORDER BY ORDINAL_POSITION
        """)
    except Exception as e:
        print("QUERY 1 (INFORMATION_SCHEMA.COLUMNS) FAILED -- STOPPING, NOT RETRYING.")
        print("Verbatim error:")
        print(repr(e))
        traceback.print_exc()
        return

    print(f"Query 1 OK: {len(cols)} columns found for cube_final.")
    cols.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                              "output", "summary", "phase22_cubefinal_columns.csv"), index=False)
    print(cols.to_string(index=False))

    # --- Query 2: row count ---
    try:
        cnt = run_query("SELECT COUNT(*) AS n_rows FROM cube_final")
    except Exception as e:
        print("QUERY 2 (SELECT COUNT(*)) FAILED -- STOPPING, NOT RETRYING.")
        print("Verbatim error:")
        print(repr(e))
        traceback.print_exc()
        return

    n_rows = int(cnt["n_rows"].iloc[0])
    print(f"Query 2 OK: cube_final has {n_rows} rows table-wide (no filter).")

    if n_rows == 0:
        print("Table is empty table-wide -- skipping the date-filtered TOP 10 query (nothing to filter).")
        return

    # Determine the date column to use for "most recent month" -- final_date per DATA_MAP.md's
    # established schema note; confirm it's actually in the column list just pulled.
    date_col_candidates = [c for c in cols["COLUMN_NAME"] if c.lower() == "final_date"]
    if not date_col_candidates:
        print(f"WARNING: no 'final_date' column found in the live schema. Columns seen: "
              f"{sorted(cols['COLUMN_NAME'].tolist())}")
        return
    date_col = date_col_candidates[0]

    # --- Query 3: TOP 10, most recent month by final_date ---
    try:
        maxdate = run_query(f"SELECT MAX({date_col}) AS max_date FROM cube_final")
        max_date_val = maxdate["max_date"].iloc[0]
        print(f"MAX({date_col}) = {max_date_val}")
        top10 = run_query(f"""
            SELECT TOP 10 *
            FROM cube_final
            WHERE {date_col} >= DATEADD(month, DATEDIFF(month, 0, (SELECT MAX({date_col}) FROM cube_final)), 0)
            ORDER BY {date_col} DESC
        """)
    except Exception as e:
        print("QUERY 3 (TOP 10, most recent month) FAILED -- STOPPING, NOT RETRYING.")
        print("Verbatim error:")
        print(repr(e))
        traceback.print_exc()
        return

    print(f"Query 3 OK: {len(top10)} rows returned for the most recent month ({date_col} >= start of "
          f"the month containing {max_date_val}).")
    top10.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                               "output", "summary", "phase22_cubefinal_top10.csv"), index=False)
    print(top10.to_string(index=False))


if __name__ == "__main__":
    main()
