"""Task 2 (Explorer+Validator) -- ad hoc schema exploration for the 31 no-history/no-sale
items investigation. Not part of the permanent pipeline; scratch investigation script,
written under src/ only because db.py's sys.path setup expects to be run from there.
Outputs go to output/summary/ per the task instructions.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

if __name__ == "__main__":
    # 1. Confirm table names / columns for candidate tables
    tables_to_check = [
        "cube_inventory_tran", "Cube_Inventory_Exact", "Cube_CES",
    ]
    for t in tables_to_check:
        q = f"""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{t}'
            ORDER BY ORDINAL_POSITION
        """
        df = run_query(q)
        print(f"\n=== {t} ({len(df)} columns) ===")
        print(df.to_string(index=False))
        df.to_csv(os.path.join(SUMMARY_DIR, f"task2_schema_{t}.csv"), index=False)

    # 2. Search for quotation-like table names
    q = """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME LIKE '%uot%'
        ORDER BY TABLE_NAME
    """
    df = run_query(q)
    print("\n=== Tables matching '%uot%' (quotation) ===")
    print(df.to_string(index=False))
    df.to_csv(os.path.join(SUMMARY_DIR, "task2_schema_quotation_tables.csv"), index=False)
