"""Identifies and profiles the largest buyers among the 58 pilot items, using
ref_customer as the customer master data source (join key: customerid).

Investigation only. Does not modify any data.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_customers")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def pull_all_pilot_sales() -> pd.DataFrame:
    sql = """
        SELECT itemcode, customerid, contractid, qty, sale, createDate
        FROM cube_Sale_APD
        WHERE division='PEM101' AND revenue_type='Omni Channel' AND status IN ('Actual','MPS')
          AND createDate >= '2024-01-01'
    """
    return run_query(sql)


def top_customers_by_value(sales: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    agg = sales.groupby("customerid").agg(
        total_sale=("sale", "sum"), total_qty=("qty", "sum"),
        n_orders=("contractid", "nunique"), n_items=("itemcode", "nunique"),
        n_months=("createDate", lambda s: pd.to_datetime(s).dt.to_period("M").nunique()),
    ).reset_index()
    total_value = sales["sale"].sum()
    agg["share_of_total_pct"] = (agg["total_sale"] / total_value * 100).round(2)
    return agg.sort_values("total_sale", ascending=False).head(n)


def customer_identity(customer_ids: list) -> pd.DataFrame:
    id_list = "','".join(customer_ids)
    r = run_query(f"""
        SELECT DISTINCT customerid, name, name_thai, province, country, class
        FROM ref_customer WHERE customerid IN ('{id_list}')
    """)
    seg = run_query(f"""
        SELECT customerid, customer_segment, COUNT(*) AS n
        FROM ref_customer WHERE customerid IN ('{id_list}') AND customer_segment IS NOT NULL
        GROUP BY customerid, customer_segment
    """)
    top_segment = seg.sort_values("n", ascending=False).drop_duplicates("customerid")[["customerid", "customer_segment"]]
    return r.merge(top_segment, on="customerid", how="left")


def order_interval_profile(sales: pd.DataFrame, customer_id: str) -> pd.DataFrame:
    sub = sales[sales["customerid"] == customer_id].copy()
    sub["createDate"] = pd.to_datetime(sub["createDate"])
    sub["year_month"] = sub["createDate"].dt.to_period("M")
    monthly = sub.groupby("year_month").agg(n_orders=("contractid", "nunique"), qty=("qty", "sum"), sale=("sale", "sum")).reset_index()
    return monthly.sort_values("year_month")


if __name__ == "__main__":
    sales = pull_all_pilot_sales()
    sales.to_csv(os.path.join(DATA_DIR, "raw_pilot_sales_all_customers.csv"), index=False)
    logger.info("Pulled %d rows across %d distinct customers for the pilot scope", len(sales), sales["customerid"].nunique())

    top10 = top_customers_by_value(sales, 10)
    top10.to_csv(os.path.join(SUMMARY_DIR, "partA_top10_customers.csv"), index=False)

    identity = customer_identity(top10["customerid"].tolist())
    identity.to_csv(os.path.join(SUMMARY_DIR, "partA_top10_customer_identity.csv"), index=False, encoding="utf-8-sig")

    cs02411_months = order_interval_profile(sales, "CS02411")
    cs02411_months.to_csv(os.path.join(SUMMARY_DIR, "partA_CS02411_monthly.csv"), index=False)

    cs02411_items = sales[sales["customerid"] == "CS02411"].groupby("itemcode").agg(
        qty=("qty", "sum"), sale=("sale", "sum"), n_orders=("contractid", "nunique")
    ).reset_index().sort_values("sale", ascending=False)
    cs02411_items.to_csv(os.path.join(SUMMARY_DIR, "partA_CS02411_items.csv"), index=False)

    print("\n=== TOP 10 CUSTOMERS BY VALUE (58-item pilot scope) ===")
    print(top10.to_string(index=False))
    print("\n=== IDENTITY ===")
    print(identity.to_string(index=False))
    print("\n=== CS02411 monthly order pattern ===")
    print(cs02411_months.to_string(index=False))
    print("\n=== CS02411 items bought ===")
    print(cs02411_items.to_string(index=False))
