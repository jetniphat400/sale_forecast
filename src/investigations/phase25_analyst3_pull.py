"""Phase 25 Analyst 3 (Agent 3 of 4 parallel, independent agents) -- data pull.

Target node: PROJECT_GRAPH.md Q10 (PEM107 branch) / Q23 (2026 Omni Channel delivery decline) --
this task's job is the BEHAVIOUR comparison (timing/delivery/traceability/mix) for PEM107,
Omni Channel vs Tendering, Period 1 (2025-05 to 2026-04) vs Period 2 (2026-05 onward), that Q10/Q23
need to judge whether the business's "separated in May 2026" account (DATA_MAP.md Sec.7, level A)
shows up as a STEP in behaviour at that date.

ONE database connection attempt for this whole task (binding rule): all three pulls below run in
this single script/session.
  1. Cube_CES for the PEM107 136-item scope (src/cube_ces_pull.py), OLMJobCode included, for
     not_late (METRICS.md Sec.19), order-to-delivery interval proxy, and the channel/date fields.
  2. cube_final for the same scope (src/cube_final_pull.py), for the batch-traceability measure
     (jobno + final_date), joined via jobno <-> Cube_CES.OLMJobCode (DATA_MAP.md Sec.2, jobcode/
     jobno/OLMJobCode entry -- all three reference the same production-batch-reference concept).
  3. cube_Sale_APD, own query via src/db.py's run_query (source table
     [salewarehouse].[dbo].[cube_Sale_APD]), columns itemcode/contractid/createDate/qty/status/
     revenue_type/manufacturing_type, PEM107 scope only, no other filter at SQL level -- for the
     manufacturing_type mix measure.

No date filter at SQL level for any pull (project convention, DATA_MAP.md Trap 18/cube_final_pull.py
docstring) -- all date windows applied afterward in Python.
"""
import sys
from pathlib import Path

import pandas as pd

SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))

from cube_ces_pull import pull_cube_ces_for_items, CUBE_CES_COLUMNS
from cube_final_pull import pull_cube_final_for_items
from db import run_query
from zero_row_guard import guard_nonempty

PROJECT_ROOT = SRC_DIR.parent
OUT_DIR = PROJECT_ROOT / "output" / "summary"
SCOPE_FILE = PROJECT_ROOT / "output" / "data" / "phaseI_combined_scope_351items.csv"


def main():
    scope = pd.read_csv(SCOPE_FILE)
    pem107 = scope[(scope["division"] == "PEM107") & (~scope["is_excluded"])]
    item_codes = pem107["code"].dropna().unique().tolist()
    print(f"PEM107 scope: {len(item_codes)} items")
    assert len(item_codes) == 136, f"Expected 136 PEM107 codes per task brief, got {len(item_codes)}"

    # --- Pull 1: Cube_CES, established shared helper, no date filter at SQL level ---
    ces = pull_cube_ces_for_items(item_codes, columns=CUBE_CES_COLUMNS + ["OLMJobCode"])
    ces.to_csv(OUT_DIR / "phase25_analyst3_cube_ces_raw.csv", index=False)
    print(f"Cube_CES: {len(ces)} rows -> phase25_analyst3_cube_ces_raw.csv")

    # --- Pull 2: cube_final, established shared helper, no date filter at SQL level ---
    cf = pull_cube_final_for_items(item_codes, allow_empty=True)
    cf.to_csv(OUT_DIR / "phase25_analyst3_cube_final_raw.csv", index=False)
    print(f"cube_final: {len(cf)} rows -> phase25_analyst3_cube_final_raw.csv")

    # --- Pull 3: cube_Sale_APD, own query, task-specified columns, PEM107 scope only ---
    code_list = "','".join(item_codes)
    sale_apd_sql = f"""
        SELECT itemcode, contractid, createDate, qty, status, revenue_type, manufacturing_type
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE itemcode IN ('{code_list}')
    """
    sale_apd = run_query(sale_apd_sql)
    guard_nonempty(sale_apd, table="cube_Sale_APD",
                    filter_desc=f"itemcode IN ({len(item_codes)} PEM107 codes)")
    sale_apd.to_csv(OUT_DIR / "phase25_analyst3_sale_apd_raw.csv", index=False)
    print(f"cube_Sale_APD: {len(sale_apd)} rows -> phase25_analyst3_sale_apd_raw.csv")

    print("PULL DONE -- single connection, 3 queries.")


if __name__ == "__main__":
    main()
