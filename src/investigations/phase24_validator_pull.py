"""Phase 24 Validator -- ONE database connection attempt, all raw pulls needed for the four
independent recomputations (PEM107 dual-channel batch share, MTS/MTO/ETO dominant counts,
cube_final duration test, PEM101 trade-off-curve band). Per this task's DATABASE ACCESS RULE:
one connection attempt for the whole task; multiple SELECTs in this one script session count as
one attempt (project precedent, e.g. src/investigations/phase23_part0_cubefinal_join.py).

Writes raw pulls to output/data/phase24_validator_*.csv so all downstream computation can run
with zero further DB access.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from cube_final_pull import pull_cube_final_for_items, CUBE_FINAL_COLUMNS
from cube_ces_pull import pull_cube_ces_for_items, CUBE_CES_COLUMNS
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase24_validator_pull")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def main():
    combined = pd.read_csv(os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv"))
    pem101_scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))

    items_351 = sorted(combined["code"].unique().tolist())
    items_pem107 = sorted(combined.loc[combined["division"] == "PEM107", "code"].unique().tolist())
    items_pem103 = sorted(combined.loc[combined["division"] == "PEM103", "code"].unique().tolist())
    items_pem101 = sorted(pem101_scope["code"].unique().tolist())

    logger.info("Scope sizes: 351=%d, PEM107=%d, PEM103=%d, PEM101=%d",
                len(items_351), len(items_pem107), len(items_pem103), len(items_pem101))

    # ---- Part 1: cube_final for the 351-item combined scope (used for both Part1 PEM107 subset
    # and Part 3 duration test) ----
    cube_final = pull_cube_final_for_items(items_351, columns=CUBE_FINAL_COLUMNS)
    cube_final.to_csv(os.path.join(DATA_DIR, "phase24_validator_cube_final_351items.csv"), index=False)
    logger.info("Saved cube_final pull: %d rows.", len(cube_final))

    # ---- Part 1: Cube_CES for PEM107 items, with OLMJobCode added (RevenueType already default) ----
    ces_cols = CUBE_CES_COLUMNS + ["OLMJobCode"]
    cube_ces_pem107 = pull_cube_ces_for_items(items_pem107, columns=ces_cols)
    cube_ces_pem107.to_csv(os.path.join(DATA_DIR, "phase24_validator_cube_ces_pem107.csv"), index=False)
    logger.info("Saved Cube_CES PEM107 pull: %d rows.", len(cube_ces_pem107))

    # ---- Part 2: order-level manufacturing_type for PEM101/103/107 (Omni Channel, Actual+MPS,
    # createDate >= 2024-01-01, per config.yaml date_range/status_basis/revenue_type -- same filter
    # pattern as phaseE1_common.query_order_level, extended with manufacturing_type) ----
    def pull_mtype(item_codes, label):
        code_list = "','".join(sorted(item_codes))
        sql = f"""
            SELECT itemcode, manufacturing_type, qty
            FROM [salewarehouse].[dbo].[cube_Sale_APD]
            WHERE itemcode IN ('{code_list}')
              AND revenue_type = 'Omni Channel'
              AND status IN ('Actual','MPS')
              AND createDate >= '2024-01-01'
        """
        df = run_query(sql)
        logger.info("[%s] manufacturing_type pull: %d rows for %d items.", label, len(df), len(item_codes))
        return df

    mtype_pem101 = pull_mtype(items_pem101, "PEM101")
    mtype_pem103 = pull_mtype(items_pem103, "PEM103")
    mtype_pem107 = pull_mtype(items_pem107, "PEM107")
    mtype_pem101.to_csv(os.path.join(DATA_DIR, "phase24_validator_mtype_pem101.csv"), index=False)
    mtype_pem103.to_csv(os.path.join(DATA_DIR, "phase24_validator_mtype_pem103.csv"), index=False)
    mtype_pem107.to_csv(os.path.join(DATA_DIR, "phase24_validator_mtype_pem107.csv"), index=False)

    logger.info("All pulls complete, one connection session.")


if __name__ == "__main__":
    main()
