"""Phase 24 Explorer D: pull PEM103 order/contract text (cube_Sale_APD.ctr_name and
cube_final.descriptions/project) for the 87-item PEM103 scope, in ONE database connection
(binding rule for this task).

Writes raw pulls to output/summary/phase24_explorerD_*.csv for later offline analysis (keyword
derivation, precision/recall, interval stats) so the single connection is not re-opened.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import get_connection
from zero_row_guard import guard_nonempty

SCOPE_PATH = Path(__file__).resolve().parents[2] / "output" / "data" / "phaseI_combined_scope_351items.csv"
OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "summary"

scope = pd.read_csv(SCOPE_PATH)
pem103 = scope[(scope["division"] == "PEM103") & (~scope["is_excluded"])]
item_codes = pem103["code"].dropna().unique().tolist()
print(f"PEM103 scope: {len(item_codes)} items")

code_list = "','".join(item_codes)

sale_apd_sql = f"""
    SELECT itemcode, ctr_name, revenue_type, contractid, createDate, forecast_date,
           customer_segment, productTypeName, productCateName, division
    FROM cube_Sale_APD
    WHERE itemcode IN ('{code_list}')
"""

cube_final_sql = f"""
    SELECT itemcode, descriptions, project, customer_name, final_date, ctrno, jobno, job_qty
    FROM [salewarehouse].[dbo].[cube_final]
    WHERE itemcode IN ('{code_list}')
"""

engine = get_connection()
with engine.connect() as conn:
    sale_apd_df = pd.read_sql(sale_apd_sql, conn)
    guard_nonempty(sale_apd_df, table="cube_Sale_APD", filter_desc=f"itemcode IN ({len(item_codes)} PEM103 codes)")
    print(f"cube_Sale_APD: {len(sale_apd_df)} rows")

    cube_final_df = pd.read_sql(cube_final_sql, conn)
    # cube_final coverage for PEM103 is known-low (36.78% forward match, DATA_MAP.md Sec.1);
    # allow empty here so a low-but-nonzero or even zero match doesn't abort the whole pull.
    guard_nonempty(cube_final_df, table="cube_final", filter_desc=f"itemcode IN ({len(item_codes)} PEM103 codes)",
                   allow_empty=True)
    print(f"cube_final: {len(cube_final_df)} rows")

sale_apd_df.to_csv(OUT_DIR / "phase24_explorerD_sale_apd_raw.csv", index=False)
cube_final_df.to_csv(OUT_DIR / "phase24_explorerD_cube_final_raw.csv", index=False)
print("Wrote raw pulls to output/summary/phase24_explorerD_sale_apd_raw.csv and "
      "phase24_explorerD_cube_final_raw.csv")

print("\nrevenue_type value counts (cube_Sale_APD, PEM103 scope):")
print(sale_apd_df["revenue_type"].value_counts(dropna=False))
