"""Systematic inventory of every table in the salewarehouse database.

Read-only investigation. Does not modify any data, does not build a model.
For each table: row count, date range (if any date-type column exists), and
whether it carries any of the requested key-concept columns.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("inventory_database")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

KEYWORD_PATTERNS = {
    "contractid": ["contract"],
    "itemcode_or_productcode": ["itemcode", "item_code", "productcode", "product_code"],
    "delivery_date": ["deldate", "delivery", "del_date", "delivered"],
    "lot_number": ["lot"],
    "grn_number": ["grn", "goodsreceipt", "goods_receipt"],
    "invoice_number": ["invoice"],
    "job_code": ["job"],
    "po_number": ["pono", "po_no", "ponumber", "purchaseorder", "purchase_order", "contractpo"],
}

DATE_TYPES = {"date", "datetime", "datetime2", "smalldatetime"}


def classify_columns(cols_df: pd.DataFrame) -> dict:
    tables = {}
    for table, grp in cols_df.groupby("TABLE_NAME"):
        col_names_lower = [c.lower() for c in grp["COLUMN_NAME"]]
        matches = {}
        for concept, patterns in KEYWORD_PATTERNS.items():
            hit_cols = [
                orig for orig, low in zip(grp["COLUMN_NAME"], col_names_lower)
                if any(p in low for p in patterns)
            ]
            matches[concept] = hit_cols
        date_cols = grp.loc[grp["DATA_TYPE"].isin(DATE_TYPES), "COLUMN_NAME"].tolist()
        tables[table] = {"matches": matches, "date_cols": date_cols, "n_columns": len(grp)}
    return tables


def inventory(tables: dict) -> pd.DataFrame:
    records = []
    for i, (table, info) in enumerate(sorted(tables.items()), start=1):
        try:
            cnt = run_query(f"SELECT COUNT(*) AS n FROM [{table}]")["n"].iloc[0]
        except Exception as e:
            logger.warning("Table %s: row count failed: %s", table, e)
            cnt = None

        date_range = None
        date_col_used = None
        # Prefer a column literally named 'date' or containing 'date' but not 'update'/'timestamp'
        preferred = [c for c in info["date_cols"] if "date" in c.lower()]
        candidates = preferred if preferred else info["date_cols"]
        for c in candidates:
            try:
                r = run_query(f"SELECT MIN([{c}]) AS mn, MAX([{c}]) AS mx FROM [{table}] WHERE [{c}] IS NOT NULL")
                if r["mn"].iloc[0] is not None:
                    date_range = (str(r["mn"].iloc[0]), str(r["mx"].iloc[0]))
                    date_col_used = c
                    break
            except Exception as e:
                logger.warning("Table %s date range on %s failed: %s", table, c, e)
                continue

        records.append({
            "table": table,
            "row_count": cnt,
            "n_columns": info["n_columns"],
            "date_column_used": date_col_used,
            "date_min": date_range[0] if date_range else None,
            "date_max": date_range[1] if date_range else None,
            "has_contractid": bool(info["matches"]["contractid"]),
            "contractid_cols": info["matches"]["contractid"],
            "has_itemcode": bool(info["matches"]["itemcode_or_productcode"]),
            "itemcode_cols": info["matches"]["itemcode_or_productcode"],
            "has_delivery_date": bool(info["matches"]["delivery_date"]),
            "delivery_date_cols": info["matches"]["delivery_date"],
            "has_lot_number": bool(info["matches"]["lot_number"]),
            "lot_number_cols": info["matches"]["lot_number"],
            "has_grn": bool(info["matches"]["grn_number"]),
            "grn_cols": info["matches"]["grn_number"],
            "has_invoice": bool(info["matches"]["invoice_number"]),
            "invoice_cols": info["matches"]["invoice_number"],
            "has_jobcode": bool(info["matches"]["job_code"]),
            "jobcode_cols": info["matches"]["job_code"],
            "has_po_number": bool(info["matches"]["po_number"]),
            "po_number_cols": info["matches"]["po_number"],
        })
        if i % 20 == 0:
            logger.info("Processed %d/%d tables", i, len(tables))
    return pd.DataFrame(records)


if __name__ == "__main__":
    cols = pd.read_csv(os.path.join(DATA_DIR, "raw_all_columns_all_tables.csv"))
    logger.info("Loaded column metadata for %d tables", cols["TABLE_NAME"].nunique())
    tables = classify_columns(cols)
    inv = inventory(tables)
    inv.to_csv(os.path.join(SUMMARY_DIR, "task1_full_database_inventory.csv"), index=False)
    logger.info("Inventory complete: %d tables, %d rows found total",
                len(inv), inv["row_count"].fillna(0).sum())

    joinable = inv[inv["has_contractid"] | inv["has_itemcode"]]
    joinable.to_csv(os.path.join(SUMMARY_DIR, "task1_joinable_tables.csv"), index=False)
    print(f"\nTables with contractid-like column: {inv['has_contractid'].sum()}")
    print(f"Tables with itemcode/productcode-like column: {inv['has_itemcode'].sum()}")
    print(f"Tables with delivery-date-like column: {inv['has_delivery_date'].sum()}")
    print(f"Tables with lot-number-like column: {inv['has_lot_number'].sum()}")
    print(f"Tables with GRN-like column: {inv['has_grn'].sum()}")
    print(f"Tables with invoice-like column: {inv['has_invoice'].sum()}")
    print(f"Tables with jobcode-like column: {inv['has_jobcode'].sum()}")
    print(f"Tables with PO-number-like column: {inv['has_po_number'].sum()}")
