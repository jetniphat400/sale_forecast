"""Explorer 2 (attribute side) -- tests whether Tendering vs Omni orders differ on attributes
independent of the revenue_type tag itself, for PEM103/PEM107, 2025 vs 2026.

Target node: Q23, feeding Q10 (PEM107 branch) and G1 (PEM103/PEM107 forecasts).

ONE DB connection attempt (task's DATABASE ACCESS RULE) -- if the first query fails, stop, do not
retry. Once connected, further queries in the same session are normal use, not retries.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase136_explorer2")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

DIVISIONS = ["PEM103", "PEM107"]


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_scope(config):
    pdf = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    sheet_to_division = config["sheet_to_division"]
    pdf = pdf[pdf["sheet"].isin([s for s, d in sheet_to_division.items() if d in DIVISIONS])].copy()
    pdf["division"] = pdf["sheet"].map(sheet_to_division)
    pdf = pdf.drop_duplicates(subset=["code"])
    counts = pdf.groupby("division")["code"].nunique().to_dict()
    logger.info("Full pricelist scope per division: %s (expect PEM103=87, PEM107=136)", counts)
    return pdf


def main():
    config = load_config()
    scope = get_scope(config)
    all_codes = sorted(scope["code"].unique())
    division_by_code = dict(zip(scope["code"], scope["division"]))
    source_table = config["source_table"]

    # ---- ONE DB connection: schema check first ----
    schema = run_query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'cube_Sale_APD'
    """)
    cols = sorted(schema["COLUMN_NAME"])
    logger.info("cube_Sale_APD full column list (%d columns): %s", len(cols), cols)
    customer_type_candidates = [c for c in cols if any(
        kw in c.lower() for kw in ["customer", "cust", "segment", "classif", "type"]
    )]
    logger.info("Customer-type/classification candidate columns: %s", customer_type_candidates)

    with open(os.path.join(SUMMARY_DIR, "phase136_explorer2_schema.csv"), "w", encoding="utf-8") as f:
        f.write("column_name\n")
        for c in cols:
            f.write(f"{c}\n")

    # ---- Pull, fresh, independent of the cached Q23 file ----
    code_list = "','".join(all_codes)
    sql = f"""
        SELECT itemcode, createDate, forecast_date, qty, sale, cost, status, contractid, revenue_type
        FROM {source_table}
        WHERE itemcode IN ('{code_list}')
          AND createDate >= '2025-01-01'
    """
    raw = run_query(sql)
    logger.info("Pulled %d rows for %d PEM103/PEM107 codes, createDate >= 2025-01-01, all revenue_types/status.",
                len(raw), len(all_codes))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw["division"] = raw["itemcode"].map(division_by_code)
    raw["year"] = raw["createDate"].dt.year
    raw.to_csv(os.path.join(DATA_DIR, "phase136_explorer2_raw.csv"), index=False)

    # ---- Consistency check vs cached Q23 pull (2025-2026 subset only) ----
    cached_path = os.path.join(DATA_DIR, "phaseQ23_raw_sales_allchannels_351full.csv")
    consistency = {}
    if os.path.exists(cached_path):
        cached = pd.read_csv(cached_path)
        cached["createDate"] = pd.to_datetime(cached["createDate"])
        cached_sub = cached[(cached["itemcode"].isin(all_codes)) & (cached["createDate"] >= "2025-01-01") &
                             (cached["status"].isin(["Actual", "MPS"]))]
        raw_actual_mps = raw[raw["status"].isin(["Actual", "MPS"])]
        consistency = {
            "cached_2025plus_value": float(cached_sub["sale"].sum()),
            "this_pull_2025plus_actual_mps_value": float(raw_actual_mps["sale"].sum()),
            "abs_diff": float(abs(cached_sub["sale"].sum() - raw_actual_mps["sale"].sum())),
        }
        consistency["pct_diff"] = 100 * consistency["abs_diff"] / consistency["cached_2025plus_value"] if consistency["cached_2025plus_value"] else np.nan
        logger.info("Consistency check vs cached Q23 pull (2025+, Actual+MPS, same codes): %s", consistency)

    # ---- Restrict to Omni Channel / Tendering only for the attribute comparison ----
    d = raw[raw["revenue_type"].isin(["Omni Channel", "Tendering"])].copy()
    d["notice_days"] = (d["forecast_date"] - d["createDate"]).dt.days

    results = {}
    contract_numbering = {}
    for division in DIVISIONS:
        dd = d[d["division"] == division]
        for year in [2025, 2026]:
            for channel in ["Omni Channel", "Tendering"]:
                g = dd[(dd["year"] == year) & (dd["revenue_type"] == channel)]
                key = f"{division}_{year}_{channel}"
                if len(g) == 0:
                    results[key] = {"n_rows": 0}
                    continue
                per_contract = g.groupby("contractid").agg(qty=("qty", "sum"), sale=("sale", "sum"),
                                                             n_lines=("itemcode", "nunique"))
                results[key] = {
                    "n_rows": len(g),
                    "n_contracts": g["contractid"].nunique(),
                    "row_qty_median": float(g["qty"].median()),
                    "row_qty_p25": float(g["qty"].quantile(0.25)),
                    "row_qty_p75": float(g["qty"].quantile(0.75)),
                    "row_sale_median": float(g["sale"].median()),
                    "row_sale_p25": float(g["sale"].quantile(0.25)),
                    "row_sale_p75": float(g["sale"].quantile(0.75)),
                    "contract_qty_median": float(per_contract["qty"].median()),
                    "contract_sale_median": float(per_contract["sale"].median()),
                    "contract_sale_p25": float(per_contract["sale"].quantile(0.25)),
                    "contract_sale_p75": float(per_contract["sale"].quantile(0.75)),
                    "n_lines_per_contract_median": float(per_contract["n_lines"].median()),
                    "n_lines_per_contract_p75": float(per_contract["n_lines"].quantile(0.75)),
                    "notice_days_median": float(g["notice_days"].median()) if g["notice_days"].notna().any() else None,
                    "notice_days_p25": float(g["notice_days"].quantile(0.25)) if g["notice_days"].notna().any() else None,
                    "notice_days_p75": float(g["notice_days"].quantile(0.75)) if g["notice_days"].notna().any() else None,
                    "notice_days_n_valid": int(g["notice_days"].notna().sum()),
                }
                # Contract numbering pattern: prefix (leading non-digit run) + digit length
                cids = per_contract.index.astype(str)
                prefixes = cids.str.extract(r"^([^\d]*)")[0].value_counts().to_dict()
                digit_lens = cids.str.replace(r"[^\d]", "", regex=True).str.len().value_counts().to_dict()
                contract_numbering[key] = {"n_contracts": len(cids), "prefixes": prefixes, "digit_lengths": digit_lens,
                                            "sample_ids": sorted(cids.tolist())[:5]}

    results_df = pd.DataFrame(results).T
    results_df.index.name = "division_year_channel"
    results_df.to_csv(os.path.join(SUMMARY_DIR, "phase136_explorer2_attribute_comparison.csv"))

    numbering_rows = []
    for key, v in contract_numbering.items():
        numbering_rows.append({"division_year_channel": key, "n_contracts": v["n_contracts"],
                                "prefixes": v["prefixes"], "digit_lengths": v["digit_lengths"],
                                "sample_ids": v["sample_ids"]})
    numbering_df = pd.DataFrame(numbering_rows)
    numbering_df.to_csv(os.path.join(SUMMARY_DIR, "phase136_explorer2_contract_numbering.csv"), index=False)

    print("\n" + "=" * 100)
    print("EXPLORER 2 (ATTRIBUTE SIDE) -- RESULTS")
    print("=" * 100)
    print(f"\nCustomer-type/classification candidate columns found: {customer_type_candidates}")
    print(f"\nConsistency check vs cached Q23 pull: {consistency}")
    print("\n--- Attribute comparison ---")
    print(results_df.to_string())
    print("\n--- Contract numbering ---")
    print(numbering_df.to_string())

    return results, contract_numbering, consistency, customer_type_candidates


if __name__ == "__main__":
    main()
