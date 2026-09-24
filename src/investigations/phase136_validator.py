"""Phase 136 Validator (independent recomputation) -- PEM103/PEM107 channel-mix reversal.

Task: check whether the 2026 Tendering<->Omni channel-mix reversal found for PEM103 and PEM107
(prior Q23/phase136 Explorer work) reflects a recording-method change or a genuine business
change. This script is an INDEPENDENT recomputation -- it does not read any phase136_explorer*/
phase136_synthesis* file, script or CSV. It derives scope from src/pricelist_reader.py +
config.yaml, pulls its own fresh data via src/cube_ces_pull.py and a direct cube_Sale_APD query,
and computes all figures from scratch.

Three parts:
  1. Customer channel-switch count and value(qty) share, PEM103 vs PEM107, 2025 vs 2026
     (Cube_CES, ActualQty).
  2. Monthly Tendering-vs-Omni VALUE share (Cube_CES.ActualPrice, confirmed below to be a line
     total not a unit price -- same pattern as cube_Sale_APD.cost, CONVENTIONS.md), keyed on
     CtrDate month, Jan 2025 - latest complete month.
  3. One attribute comparison from Explorer 2's dimension list: notice days
     (forecast_date - createDate), Omni vs Tendering, 2025 vs 2026, cube_Sale_APD.

PRIVACY: no CustomerID/CustomerName is written to any output/summary file -- only aggregated
counts/shares. Raw Cube_CES pull (with CustomerID) is written only to output/data/ (gitignored,
never committed, per CONVENTIONS.md "never commit generated output").
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import run_query
from cube_ces_pull import pull_cube_ces_for_items
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("phase136_validator")

ROOT = Path(__file__).resolve().parents[2]
OUT_DATA = ROOT / "output" / "data"
OUT_SUMMARY = ROOT / "output" / "summary"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_SUMMARY.mkdir(parents=True, exist_ok=True)

with open(ROOT / "config" / "config.yaml", "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

STATUS_BASIS = CFG["status_basis"]  # ["Actual", "MPS"]

# ---------------------------------------------------------------------------
# Part 0: scope (pricelist is authoritative -- CONVENTIONS.md)
# ---------------------------------------------------------------------------

def derive_scope():
    pricelist_path = ROOT / CFG["pricelist_path"]
    sheet_to_division = CFG["sheet_to_division"]
    df = load_visible_product_rows(str(pricelist_path))
    df["division"] = df["sheet"].map(sheet_to_division)
    scope = df[df["division"].isin(["PEM103", "PEM107"])].drop_duplicates(subset=["code", "division"])
    code_to_division = dict(zip(scope["code"], scope["division"]))
    for div in ["PEM103", "PEM107"]:
        n = sum(1 for v in code_to_division.values() if v == div)
        logger.info("Scope check: %s has %d distinct item codes (pricelist, visible sheets only)", div, n)
    return code_to_division


# ---------------------------------------------------------------------------
# Part 1 + 2 data: Cube_CES pull (no date filter at pull time -- DATA_MAP.md Trap 18)
# ---------------------------------------------------------------------------

def pull_ces(code_to_division: dict) -> pd.DataFrame:
    codes = list(code_to_division.keys())
    cols = ["ItemCode", "ContractID", "Status", "CtrDate", "ForecastDelDate",
            "ActualQty", "ActualPrice", "RevenueType", "CustomerID"]
    df = pull_cube_ces_for_items(codes, columns=cols)
    df["division"] = df["ItemCode"].map(code_to_division)
    unmapped = df["division"].isna().sum()
    if unmapped:
        logger.warning("%d/%d pulled rows have an ItemCode not in the 223-code scope map (dropped)",
                        unmapped, len(df))
    df = df.dropna(subset=["division"]).copy()
    df["CtrDate"] = pd.to_datetime(df["CtrDate"])
    df["year"] = df["CtrDate"].dt.year
    df["month"] = df["CtrDate"].dt.to_period("M")
    raw_path = OUT_DATA / "phase136_validator_cube_ces_raw.csv"
    df.to_csv(raw_path, index=False)
    logger.info("Pulled %d Cube_CES rows for 223-code PEM103+PEM107 scope -> %s (gitignored, has CustomerID)",
                len(df), raw_path)
    return df


def verify_actualprice_is_line_total(df: pd.DataFrame):
    """Sanity check (already spot-checked live against the DB before writing this script):
    ActualPrice/ActualQty is a stable unit price across rows of varying qty for the same item --
    i.e. ActualPrice is a LINE TOTAL, same pattern CONVENTIONS.md documents for cube_Sale_APD.cost.
    Recorded here as a check, not re-derived at report time.
    """
    sample = df[(df["ActualQty"] > 1) & (df["ActualPrice"] > 0)].copy()
    sample["unit_price"] = sample["ActualPrice"] / sample["ActualQty"]
    by_item = sample.groupby("ItemCode")["unit_price"].agg(["count", "std", "mean"])
    by_item = by_item[by_item["count"] >= 5]
    by_item["cv"] = by_item["std"] / by_item["mean"]
    logger.info("ActualPrice-as-line-total check: median within-item CV of (ActualPrice/ActualQty) "
                "across %d items with >=5 qty>1 rows = %.4f (low CV supports line-total reading)",
                len(by_item), by_item["cv"].median())


# ---------------------------------------------------------------------------
# Part 1: customer channel-switch count and qty share, 2025 vs 2026
# ---------------------------------------------------------------------------

def part1_customer_switch(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    detail_rows = []
    for div in ["PEM103", "PEM107"]:
        sub = df[df["division"] == div]

        # distinct-customer counts per year (any nonzero ActualQty that year)
        by_cust_year = sub.groupby(["CustomerID", "year"])["ActualQty"].sum().reset_index()
        cust_2025 = set(by_cust_year.loc[(by_cust_year["year"] == 2025) & (by_cust_year["ActualQty"] > 0), "CustomerID"])
        cust_2026 = set(by_cust_year.loc[(by_cust_year["year"] == 2026) & (by_cust_year["ActualQty"] > 0), "CustomerID"])
        both = cust_2025 & cust_2026
        only_2025 = cust_2025 - cust_2026
        only_2026 = cust_2026 - cust_2025

        # dominant revenue type per customer per year, by summed ActualQty
        by_cust_year_rt = sub.groupby(["CustomerID", "year", "RevenueType"])["ActualQty"].sum().reset_index()

        def dominant(cust, yr):
            g = by_cust_year_rt[(by_cust_year_rt["CustomerID"] == cust) & (by_cust_year_rt["year"] == yr)]
            g = g[g["ActualQty"] > 0]
            if g.empty:
                return None, 0.0
            g = g.sort_values(["ActualQty", "RevenueType"], ascending=[False, True])  # tie-break: alphabetical
            top = g.iloc[0]
            return top["RevenueType"], top["ActualQty"]

        n_switched = 0
        qty_switchers_2yr = 0.0
        qty_bothyears_2yr = 0.0
        for cust in both:
            dom25, q25 = dominant(cust, 2025)
            dom26, q26 = dominant(cust, 2026)
            total_cust_qty = sub[(sub["CustomerID"] == cust) & (sub["year"].isin([2025, 2026]))]["ActualQty"].sum()
            qty_bothyears_2yr += total_cust_qty
            switched = (dom25 is not None) and (dom26 is not None) and (dom25 != dom26)
            if switched:
                n_switched += 1
                qty_switchers_2yr += total_cust_qty
            detail_rows.append({"division": div, "n_customers_both_years_flag": 1,
                                 "dominant_2025": dom25, "dominant_2026": dom26, "switched": switched})

        qty_all_2yr = sub[sub["year"].isin([2025, 2026])]["ActualQty"].sum()

        rows.append({
            "division": div,
            "n_customers_2025": len(cust_2025),
            "n_customers_2026": len(cust_2026),
            "n_customers_both_years": len(both),
            "n_customers_only_2025": len(only_2025),
            "n_customers_only_2026": len(only_2026),
            "n_switched_dominant_channel": n_switched,
            "pct_of_both_years_customers_switched": round(100 * n_switched / len(both), 2) if both else None,
            "qty_switchers_2yr_combined": round(qty_switchers_2yr, 2),
            "qty_bothyears_customers_2yr_combined": round(qty_bothyears_2yr, 2),
            "qty_all_division_2yr_combined": round(qty_all_2yr, 2),
            "switchers_pct_of_bothyears_qty": round(100 * qty_switchers_2yr / qty_bothyears_2yr, 2) if qty_bothyears_2yr else None,
            "switchers_pct_of_all_division_2yr_qty": round(100 * qty_switchers_2yr / qty_all_2yr, 2) if qty_all_2yr else None,
        })

    result = pd.DataFrame(rows)
    detail = pd.DataFrame(detail_rows)  # aggregate-only counts by dominant-pair, no CustomerID
    detail_agg = detail.groupby(["division", "dominant_2025", "dominant_2026", "switched"]).size().reset_index(name="n_customers")
    result.to_csv(OUT_SUMMARY / "phase136_validator_part1_customer_switch.csv", index=False)
    detail_agg.to_csv(OUT_SUMMARY / "phase136_validator_part1_switch_pairs.csv", index=False)
    logger.info("Part 1 written: %s, %s", "phase136_validator_part1_customer_switch.csv",
                "phase136_validator_part1_switch_pairs.csv")
    return result, detail_agg


# ---------------------------------------------------------------------------
# Part 2: monthly Tendering-vs-Omni VALUE share, Jan 2025 - latest complete month
# ---------------------------------------------------------------------------

def part2_monthly_value_share(df: pd.DataFrame) -> pd.DataFrame:
    max_ctrdate = df["CtrDate"].max()
    # latest complete month: if max_ctrdate falls inside a month, that month may be partial ->
    # last COMPLETE month is the one before it.
    latest_partial_month = max_ctrdate.to_period("M")
    latest_complete_month = latest_partial_month - 1
    logger.info("Max CtrDate observed in pull: %s -> latest complete month = %s (month of max date, %s, "
                "treated as potentially partial and excluded)", max_ctrdate.date(), latest_complete_month,
                latest_partial_month)

    start_month = pd.Period("2025-01", freq="M")
    monthly = df.groupby(["division", "month", "RevenueType"])["ActualPrice"].sum().reset_index()
    monthly = monthly[(monthly["month"] >= start_month) & (monthly["month"] <= latest_complete_month)]

    totals = monthly.groupby(["division", "month"])["ActualPrice"].transform("sum")
    monthly["value_share_pct"] = np.where(totals > 0, 100 * monthly["ActualPrice"] / totals, np.nan)

    wide = monthly.pivot_table(index=["division", "month"], columns="RevenueType",
                                values="value_share_pct", fill_value=0.0).reset_index()
    wide.columns.name = None
    totals_df = monthly.groupby(["division", "month"])["ActualPrice"].sum().reset_index().rename(
        columns={"ActualPrice": "total_value"})
    wide = wide.merge(totals_df, on=["division", "month"])
    wide["month"] = wide["month"].astype(str)
    wide = wide.sort_values(["division", "month"])
    wide.to_csv(OUT_SUMMARY / "phase136_validator_part2_monthly_value_share.csv", index=False)
    logger.info("Part 2 written: phase136_validator_part2_monthly_value_share.csv (%d division-month rows, "
                "%s to %s)", len(wide), start_month, latest_complete_month)
    return wide, latest_complete_month


# ---------------------------------------------------------------------------
# Part 3: notice days (forecast_date - createDate), Omni vs Tendering, 2025 vs 2026
# cube_Sale_APD, fresh pull (per task instructions), status_basis filter applied
# (project convention, config.yaml status_basis) and stated explicitly.
# ---------------------------------------------------------------------------

def pull_sale_apd(code_to_division: dict) -> pd.DataFrame:
    codes = list(code_to_division.keys())
    code_list = "','".join(codes)
    status_list = "','".join(STATUS_BASIS)
    sql = f"""
        SELECT itemcode, createDate, forecast_date, revenue_type, qty, status, contractid
        FROM {CFG['source_table']}
        WHERE itemcode IN ('{code_list}')
          AND status IN ('{status_list}')
    """
    df = run_query(sql)
    df["division"] = df["itemcode"].map(code_to_division)
    unmapped = df["division"].isna().sum()
    if unmapped:
        logger.warning("%d/%d cube_Sale_APD rows have an itemcode not in scope map (dropped)", unmapped, len(df))
    df = df.dropna(subset=["division"]).copy()
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])
    df["year"] = df["createDate"].dt.year
    df["notice_days"] = (df["forecast_date"] - df["createDate"]).dt.days
    raw_path = OUT_DATA / "phase136_validator_sale_apd_raw.csv"
    df.to_csv(raw_path, index=False)
    logger.info("Pulled %d cube_Sale_APD rows (status IN %s) for 223-code scope -> %s",
                len(df), STATUS_BASIS, raw_path)
    return df


def part3_notice_days(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[df["year"].isin([2025, 2026]) & df["revenue_type"].isin(["Omni Channel", "Tendering"])].copy()
    sub = sub.dropna(subset=["notice_days"])
    n_negative = (sub["notice_days"] < 0).sum()
    logger.info("Part 3: %d/%d rows (2025-2026, Omni/Tendering) have a negative notice_days value "
                "(kept, not dropped, reported)", n_negative, len(sub))

    g = sub.groupby(["division", "year", "revenue_type"])["notice_days"].agg(
        n="count", median="median", mean="mean", std="std").reset_index()
    g.to_csv(OUT_SUMMARY / "phase136_validator_part3_notice_days.csv", index=False)
    logger.info("Part 3 written: phase136_validator_part3_notice_days.csv")
    return g


# ---------------------------------------------------------------------------
def main():
    code_to_division = derive_scope()

    ces = pull_ces(code_to_division)
    verify_actualprice_is_line_total(ces)

    part1_result, part1_pairs = part1_customer_switch(ces)
    part2_result, latest_complete_month = part2_monthly_value_share(ces)

    sale_apd = pull_sale_apd(code_to_division)
    part3_result = part3_notice_days(sale_apd)

    print("\n=== PART 1: customer channel-switch ===")
    print(part1_result.to_string(index=False))
    print("\n=== PART 1: switch pairs (aggregate, no customer IDs) ===")
    print(part1_pairs.to_string(index=False))
    print(f"\n=== PART 2: monthly value share (latest complete month = {latest_complete_month}) ===")
    print(part2_result.to_string(index=False))
    print("\n=== PART 3: notice days ===")
    print(part3_result.to_string(index=False))


if __name__ == "__main__":
    main()
