"""Phase 25 Explorer 2: search for ANY column, anywhere, that changed for PEM107 around
May 2026 -- independent of the batch-linkage (jobno/OLMJobCode) test another agent is running.

Scope: PEM107, 136 items from output/data/phaseI_combined_scope_351items.csv (pricelist-authoritative
scope; the database's own `division` column is reference-only per CONVENTIONS.md and is never used
as a filter here).

One connection attempt: every query below runs in this one script/session (schema probes via
INFORMATION_SCHEMA.COLUMNS, then the three data pulls) -- per this project's established
precedent, multiple queries in one script count as one connection attempt.

No date filter at SQL level anywhere (cube_Sale_APD, Cube_CES, cube_final) -- itemcode/ItemCode
scope only; date windows (Jan 2025 onward, Apr 2026 vs Jun 2026) are applied afterward in Python,
per src/cube_final_pull.py and src/cube_ces_pull.py's established pattern.

Privacy: customer_name / CustomerName / any customer or contract identifier is dropped before any
CSV is written (repo is public).
"""
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import run_query
from cube_final_pull import pull_cube_final_for_items, CUBE_FINAL_COLUMNS
from cube_ces_pull import pull_cube_ces_for_items

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("phase25_explorer2_pull")

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCOPE_FILE = Path(__file__).resolve().parents[2] / "output" / "data" / "phaseI_combined_scope_351items.csv"


def get_full_schema(table_schema: str, table_name: str) -> pd.DataFrame:
    sql = f"""
        SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{table_schema}' AND TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
    """
    return run_query(sql)


def main():
    scope = pd.read_csv(SCOPE_FILE)
    pem107_items = scope.loc[scope["division"] == "PEM107", "code"].dropna().unique().tolist()
    logger.info("PEM107 item scope: %d items (from %s)", len(pem107_items), SCOPE_FILE)

    # --- Full schema probes (one query each, same session) ---
    schema_sale_apd = get_full_schema("dbo", "cube_Sale_APD")
    schema_sale_apd.to_csv(OUT_DIR / "phase25_explorer2_schema_cube_Sale_APD.csv", index=False)
    logger.info("cube_Sale_APD schema: %d columns", len(schema_sale_apd))

    schema_ces = get_full_schema("dbo", "Cube_CES")
    schema_ces.to_csv(OUT_DIR / "phase25_explorer2_schema_Cube_CES.csv", index=False)
    logger.info("Cube_CES schema: %d columns", len(schema_ces))

    schema_cube_final = get_full_schema("dbo", "cube_final")
    schema_cube_final.to_csv(OUT_DIR / "phase25_explorer2_schema_cube_final.csv", index=False)
    logger.info("cube_final schema: %d columns", len(schema_cube_final))

    # --- cube_Sale_APD pull: full categorical-relevant column list, itemcode scope, no date filter ---
    sale_apd_cols = [
        "itemcode", "contractid", "division", "revenue_type", "status", "jobcode",
        "customer_segment", "manufacturing_type", "productID", "typeOfSale",
        "forecast_date", "createDate", "PODate", "cost", "qty",
    ]
    # Only request columns that actually exist in the live schema (schema probe just confirmed).
    live_cols_sale_apd = set(schema_sale_apd["COLUMN_NAME"].tolist())
    sale_apd_cols_final = [c for c in sale_apd_cols if c in live_cols_sale_apd]
    missing_sale_apd = [c for c in sale_apd_cols if c not in live_cols_sale_apd]
    if missing_sale_apd:
        logger.warning("cube_Sale_APD columns requested but not in live schema (skipped): %s",
                        missing_sale_apd)

    code_list = "','".join(pem107_items)
    col_list = ", ".join(f"[{c}]" for c in sale_apd_cols_final)
    sql_sale_apd = f"""
        SELECT {col_list}
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE itemcode IN ('{code_list}')
    """
    sale_apd_df = run_query(sql_sale_apd)
    logger.info("cube_Sale_APD: %d rows pulled for %d items", len(sale_apd_df), len(pem107_items))
    sale_apd_save = sale_apd_df.drop(columns=[c for c in ["contractid"] if c in sale_apd_df.columns])
    sale_apd_save.to_csv(OUT_DIR / "phase25_explorer2_cube_Sale_APD_raw.csv", index=False)

    # --- Cube_CES pull: wide column list including SaleDivision + OLMJobCode prefix source ---
    ces_wide_cols = [
        "ItemCode", "ContractID", "Status", "RevenueType", "SaleDivision", "CtrDate",
        "PlanDelDate", "ForecastDelDate", "ActualDelDate", "ActualQty", "OLMJobCode",
        "CustomerID", "CustomerName",
    ]
    live_cols_ces = set(schema_ces["COLUMN_NAME"].tolist())
    ces_cols_final = [c for c in ces_wide_cols if c in live_cols_ces]
    missing_ces = [c for c in ces_wide_cols if c not in live_cols_ces]
    if missing_ces:
        logger.warning("Cube_CES columns requested but not in live schema (skipped): %s", missing_ces)
    # also surface any live column that looks status/type/plant/location-like and wasn't already requested
    interesting_extra = [c for c in schema_ces["COLUMN_NAME"].tolist()
                         if c not in ces_cols_final
                         and any(k in c.lower() for k in
                                 ["status", "type", "division", "plant", "line", "location",
                                  "warehouse", "company", "dept", "factory"])]
    if interesting_extra:
        logger.info("Cube_CES: extra status/type/location-like columns found in live schema, "
                    "adding to pull: %s", interesting_extra)
        ces_cols_final = ces_cols_final + interesting_extra

    ces_df = pull_cube_ces_for_items(pem107_items, columns=ces_cols_final, allow_empty=False)
    ces_save = ces_df.drop(columns=[c for c in ["CustomerName", "CustomerID", "ContractID"]
                                     if c in ces_df.columns])
    ces_save.to_csv(OUT_DIR / "phase25_explorer2_Cube_CES_raw.csv", index=False)
    logger.info("Cube_CES: %d rows saved (customer columns dropped for privacy)", len(ces_save))

    # --- cube_final pull: default full 34/35-column schema plus any extra live column found ---
    live_cols_cf = set(schema_cube_final["COLUMN_NAME"].tolist())
    extra_cf = [c for c in live_cols_cf if c not in CUBE_FINAL_COLUMNS]
    cf_cols_final = CUBE_FINAL_COLUMNS + extra_cf
    if extra_cf:
        logger.info("cube_final: live schema has columns beyond the shared loader's default list, "
                    "adding: %s", extra_cf)

    cube_final_df = pull_cube_final_for_items(pem107_items, columns=cf_cols_final, allow_empty=False)
    cf_save = cube_final_df.drop(
        columns=[c for c in ["customer_name", "descriptions", "project", "note",
                              "ctrno", "pono", "cus_serialno", "fg_check_by", "fg_check_name",
                              "fg_pack_name", "fg_final_by", "fg_final_name"]
                 if c in cube_final_df.columns])
    cf_save.to_csv(OUT_DIR / "phase25_explorer2_cube_final_raw.csv", index=False)
    logger.info("cube_final: %d rows saved (free-text/customer columns dropped for privacy)",
                len(cf_save))

    logger.info("All pulls complete. Raw files written to %s", OUT_DIR)


if __name__ == "__main__":
    main()
