"""Phase 25 Explorer 1: pull raw data to test whether the jobcode/OLMJobCode <-> cube_final.jobno
linkage itself went blind at the late-2024 division reorganisation (Q10, PEM107 branch,
PROJECT_GRAPH.md). This is a test of LINKAGE RELIABILITY only, not of whether batches were
actually shared -- see the analysis script and report for that distinction.

Three pulls, one connection attempt (established precedent, e.g. phase24_explorerA_pull.py):
  1. cube_final for the PEM107 item scope (shared loader, has `jobno`).
  2. Cube_CES for the PEM107 item scope, with OLMJobCode added (shared loader).
  3. cube_Sale_APD for the PEM107 item scope -- itemcode, contractid, createDate, forecast_date,
     qty, status, division, revenue_type, jobcode -- no shared loader exists for this column set,
     so this is a direct run_query call per the task's instructions. No revenue_type/status/date
     filter at the SQL level; itemcode IN (...) only.

No date filter at pull time anywhere (DATA_MAP.md Trap 7/18 pattern) -- Jan-2024-onward and any
other window is applied afterward in the analysis script.
"""
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import run_query
from cube_final_pull import pull_cube_final_for_items
from cube_ces_pull import pull_cube_ces_for_items, CUBE_CES_COLUMNS
from zero_row_guard import guard_nonempty

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("phase25_explorer1_pull")

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCOPE_FILE = Path(__file__).resolve().parents[2] / "output" / "data" / "phaseI_combined_scope_351items.csv"

SALE_APD_COLUMNS = [
    "itemcode", "contractid", "createDate", "forecast_date", "qty", "status",
    "division", "revenue_type", "jobcode",
]


def pull_sale_apd_for_items(item_codes):
    code_list = "','".join(item_codes)
    col_list = ", ".join(SALE_APD_COLUMNS)
    sql = f"""
        SELECT {col_list}
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    guard_nonempty(df, table="cube_Sale_APD",
                    filter_desc=f"itemcode IN ({len(item_codes)} codes)", allow_empty=False)
    logger.info("Pulled %d cube_Sale_APD rows for %d item codes (no revenue_type/status/date "
                "filter at pull -- applied afterward in Python).", len(df), len(item_codes))
    return df


def main():
    scope = pd.read_csv(SCOPE_FILE)
    pem107_items = scope.loc[scope["division"] == "PEM107", "code"].dropna().unique().tolist()
    logger.info("PEM107 item scope: %d items (from %s)", len(pem107_items), SCOPE_FILE)

    cube_final_df = pull_cube_final_for_items(pem107_items, allow_empty=False)
    logger.info("cube_final: %d rows, %d distinct jobno", len(cube_final_df),
                cube_final_df["jobno"].nunique())

    ces_cols = CUBE_CES_COLUMNS + ["OLMJobCode"]
    cube_ces_df = pull_cube_ces_for_items(pem107_items, columns=ces_cols, allow_empty=False)
    logger.info("Cube_CES: %d rows, %d distinct OLMJobCode, RevenueType values: %s",
                len(cube_ces_df), cube_ces_df["OLMJobCode"].nunique(),
                cube_ces_df["RevenueType"].value_counts().to_dict())

    sale_apd_df = pull_sale_apd_for_items(pem107_items)
    logger.info("cube_Sale_APD: %d rows, revenue_type values: %s, status values: %s",
                len(sale_apd_df), sale_apd_df["revenue_type"].value_counts().to_dict(),
                sale_apd_df["status"].value_counts().to_dict())

    # Save raw pulls. This task's instructions forbid customer names, contract IDs and employee
    # names in anything written to output/summary (repo is public) -- broader than the usual
    # customer_name/CustomerName-only rule, so dropped here explicitly:
    #   - cube_final: `ctrno` (a contract ID, DATA_MAP.md Sec.1 cube_final entry), and
    #     `fg_check_name`/`fg_final_name`/`fg_pack_name` (found, on inspection of the pulled
    #     values, to hold actual employee names, not role codes -- `fg_check_by`/`fg_final_by`
    #     hold role codes like 'QA'/'QC' and are kept).
    #   - Cube_CES: `ContractID`, `CustomerName` (if requested).
    #   - cube_Sale_APD: `contractid`. `contractid`/`ContractID` are used in-memory for the
    #     (contractid, itemcode) join grain in the analysis script but never persisted to disk.
    cf_save = cube_final_df.drop(columns=[c for c in
        ["ctrno", "fg_check_name", "fg_final_name", "fg_pack_name", "customer_name"]
        if c in cube_final_df.columns])
    ces_save = cube_ces_df.drop(columns=[c for c in ["ContractID", "CustomerName"]
                                          if c in cube_ces_df.columns])
    sale_apd_save = sale_apd_df.drop(columns=[c for c in ["contractid"]
                                               if c in sale_apd_df.columns])
    cf_save.to_csv(OUT_DIR / "phase25_explorer1_cube_final_raw.csv", index=False)
    ces_save.to_csv(OUT_DIR / "phase25_explorer1_cube_ces_raw.csv", index=False)
    sale_apd_save.to_csv(OUT_DIR / "phase25_explorer1_sale_apd_raw.csv", index=False)
    logger.info("Saved raw pulls to %s (contract IDs and employee-name columns dropped per this "
                "task's privacy rule; the in-memory dataframes with contractid/ContractID are "
                "not persisted -- re-run this pull script if the analysis needs to redo the "
                "contract-grain join from scratch).", OUT_DIR)


if __name__ == "__main__":
    main()
