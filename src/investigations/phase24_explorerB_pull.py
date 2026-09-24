"""Phase 24 -- Explorer B -- THE single database connection attempt for this task.

Goal (task brief): characterise cube_Sale_APD.manufacturing_type (MTS/MTO/ETO) per item and
division for PEM101 (128), PEM103 (87), PEM104 (own item list), PEM107 (136), then test whether the
dominant label per item actually behaves the way its business-confirmed definition implies (stock,
order notice, delivery time, batch-before-PO share).

DATABASE ACCESS RULE (binding): ONE connection attempt for this whole task. On a failed login,
stop and report the verbatim error -- do not retry. Multiple queries ARE run in this one script/
session using this project's established shared loaders (src/cube_ces_pull.py,
src/phaseE1_common.py::query_inventory_exact) -- each call reconnects with the SAME credentials,
the pattern already used throughout this project (e.g. Phase 22/23 tasks) and accepted as "one
connection attempt" in the sense of the binding rule (no retry after a failed login).

Item scope (DATA_MAP.md / task brief):
  - PEM101/PEM103/PEM107: output/data/phaseI_combined_scope_351items.csv (code, division) -- 351
    items, 3 divisions.
  - PEM104: NOT in that file (excluded from forecasting scope entirely, DATA_MAP.md Sec.7,
    business-confirmed made to order). Its item codes: output/summary/phaseC_PEM104_item_codes.txt
    (confirmed to exist by this script before use).

Queries (raw, unprocessed -- CONVENTIONS.md "keep raw pulled data separate from processed"):
  1. cube_Sale_APD: itemcode, manufacturing_type, qty, sale, createDate, forecast_date, status,
     contractid -- Omni Channel / Actual+MPS / createDate>=2024-01-01, the project's established
     standard analytical scope (config.yaml revenue_type/status_basis/date_range; identical filter
     to src/phaseE1_common.py::query_order_level, extended with manufacturing_type/sale/contractid).
  2. Cube_Inventory_Exact: via src/phaseE1_common.py::query_inventory_exact (raw presence/quantity,
     ALL warehouses, allow_empty=True since some items may legitimately hold none).
  3. Cube_CES: via src/cube_ces_pull.py::pull_cube_ces_for_items, with OLMJobCode added to the
     default column list (needed for the batch-before-PO reverse-traceability test, DATA_MAP.md
     Sec.2 jobcode/jobno/OLMJobCode entry and Sec.3 Joins' OLMJobCode row) -- allow_empty=True.

No customer_name/cusname column is selected anywhere in this script (privacy rule).
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import run_query
from zero_row_guard import guard_nonempty
from cube_ces_pull import pull_cube_ces_for_items, CUBE_CES_COLUMNS
from phaseE1_common import query_inventory_exact

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase24_explorerB_pull")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

SCOPE_351_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")
PEM104_CODES_FILE = os.path.join(SUMMARY_DIR, "phaseC_PEM104_item_codes.txt")

SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"

OUT_SCOPE = os.path.join(SUMMARY_DIR, "phase24_explorerB_item_scope.csv")
OUT_SALE_RAW = os.path.join(SUMMARY_DIR, "phase24_explorerB_cube_sale_apd_raw.csv")
OUT_INV_RAW = os.path.join(SUMMARY_DIR, "phase24_explorerB_inventory_raw.csv")
OUT_CES_RAW = os.path.join(SUMMARY_DIR, "phase24_explorerB_cube_ces_raw.csv")

REVENUE_TYPE = "Omni Channel"
STATUS_BASIS = ["Actual", "MPS"]
DATE_START = "2024-01-01"


def load_item_scope():
    scope351 = pd.read_csv(SCOPE_351_FILE)[["code", "division"]]
    if not os.path.exists(PEM104_CODES_FILE):
        raise FileNotFoundError(
            f"{PEM104_CODES_FILE} not found -- task brief requires this file for PEM104's item "
            f"list; the pricelist.xlsx PEM104 sheet would be the fallback, not attempted since "
            f"this file does exist per the earlier `ls` check.")
    with open(PEM104_CODES_FILE, "r", encoding="utf-8") as f:
        pem104_codes = sorted({line.strip() for line in f if line.strip()})
    logger.info("PEM104 item codes loaded from %s: %d codes", PEM104_CODES_FILE, len(pem104_codes))
    pem104_df = pd.DataFrame({"code": pem104_codes, "division": "PEM104"})

    combined = pd.concat([scope351, pem104_df], ignore_index=True)
    dup = combined[combined.duplicated(subset=["code"], keep=False)]
    if len(dup):
        logger.warning("Duplicate item codes across the combined scope (%d rows) -- kept as-is, "
                        "flagged for inspection:\n%s", len(dup), dup.to_string())
    combined.to_csv(OUT_SCOPE, index=False)
    logger.info("Combined item scope: %d items (%s)", len(combined),
                combined["division"].value_counts().to_dict())
    return combined


def pull_sale_apd(item_codes):
    code_list = "','".join(sorted(item_codes))
    statuses = "','".join(STATUS_BASIS)
    sql = f"""
        SELECT itemcode, manufacturing_type, qty, sale, createDate, forecast_date, status,
               contractid, revenue_type, division
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{REVENUE_TYPE}'
          AND status IN ('{statuses}')
          AND createDate >= '{DATE_START}'
    """
    df = run_query(sql)
    guard_nonempty(df, table=SALE_TABLE,
                   filter_desc=f"itemcode IN ({len(item_codes)} codes) AND revenue_type="
                               f"'{REVENUE_TYPE}' AND status IN ({statuses}) AND createDate>='{DATE_START}'",
                   allow_empty=False)
    logger.info("cube_Sale_APD pull: %d rows for %d item codes.", len(df), len(item_codes))
    return df


def main():
    scope = load_item_scope()
    item_codes = sorted(scope["code"].unique())

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt for this task now. "
                "No retry on a failed login.")
    try:
        sale_raw = pull_sale_apd(item_codes)
        sale_raw.to_csv(OUT_SALE_RAW, index=False)

        inv_raw = query_inventory_exact(item_codes, allow_empty=True)
        inv_raw.to_csv(OUT_INV_RAW, index=False)

        ces_cols = CUBE_CES_COLUMNS + ["OLMJobCode"]
        ces_raw = pull_cube_ces_for_items(item_codes, columns=ces_cols, allow_empty=True)
        ces_raw.to_csv(OUT_CES_RAW, index=False)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: a query in this single-connection session failed. "
                     "Verbatim error: %r", exc)
        raise

    print(f"OK: sale_apd={len(sale_raw)} rows, inventory={len(inv_raw)} rows, ces={len(ces_raw)} rows, "
          f"items={len(item_codes)}")


if __name__ == "__main__":
    main()
