"""Q23 follow-up, Explorer 1 ("order side") -- tests whether PEM103/PEM107's 2026 channel-mix
reversal (Q23, V2-confirmed) is a database RECORDING-METHOD change or a genuine BUSINESS change.

ONE DB connection attempt (this task's DATABASE ACCESS RULE) -- if the first query fails to
connect/authenticate, this script raises and stops; every subsequent query in the same run is
normal use of an established connection, not a retry.

Uses the FIXED shared Cube_CES helper (src/cube_ces_pull.py, DATA_MAP.md Trap 18) -- no date
filter at the SQL level. Reuses the cached, already-V2-confirmed cube_Sale_APD pull
(output/data/phaseQ23_raw_sales_allchannels_351full.csv) for the item/timing/value-based checks
(same value definition as the prior Q23 task, so results are directly comparable), and a fresh
Cube_CES pull for the customer-identity check (cube_Sale_APD carries no customer field).

PRIVACY: raw CustomerID/CustomerName values are read but never written to any committed file or
printed in this script's own log output (DATA_MAP.md's own header rule: no customer names or
codes in project documentation, repository is public). Aggregated counts/shares only.
"""
import logging
import os
import sys

import numpy as np
import openpyxl
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from cube_ces_pull import pull_cube_ces_for_items
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase136_explorer1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CACHED_SALES_PULL = os.path.join(DATA_DIR, "phaseQ23_raw_sales_allchannels_351full.csv")
PRICELIST_PATH = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")

DIVISIONS = ["PEM103", "PEM107"]


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_scope(config) -> pd.DataFrame:
    pdf = load_visible_product_rows(PRICELIST_PATH)
    sheet_to_division = config["sheet_to_division"]
    pdf = pdf[pdf["sheet"].isin([s for s, d in sheet_to_division.items() if d in DIVISIONS])].copy()
    pdf["division"] = pdf["sheet"].map(sheet_to_division)
    pdf = pdf.drop_duplicates(subset=["code"])
    logger.info("Full pricelist scope: %s", pdf.groupby("division")["code"].nunique().to_dict())
    return pdf


# ------------------------------------------------------------------------------------------------
# Part 1 -- customers (Cube_CES, one fresh DB pull, no date filter at pull -- src/cube_ces_pull.py)
# ------------------------------------------------------------------------------------------------

def customer_switch_analysis(scope: pd.DataFrame) -> pd.DataFrame:
    codes = sorted(scope["code"].unique())
    code_to_div = dict(zip(scope["code"], scope["division"]))

    ces = pull_cube_ces_for_items(
        codes,
        columns=["ItemCode", "ContractID", "Status", "CtrDate", "ForecastDelDate", "ActualDelDate",
                 "ActualQty", "RevenueType", "CustomerID", "CustomerName"],
    )
    ces.to_csv(os.path.join(DATA_DIR, "phase136_cube_ces_raw.csv"), index=False)

    ces["division"] = ces["ItemCode"].map(code_to_div)
    ces = ces[ces["division"].notna()].copy()
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["year"] = ces["CtrDate"].dt.year
    ces = ces[ces["RevenueType"].isin(["Omni Channel", "Tendering"])].copy()
    ces = ces[ces["year"].isin([2025, 2026])].copy()
    ces["ActualQty"] = ces["ActualQty"].fillna(0)

    results = []
    for div, g in ces.groupby("division"):
        cy_channel = g.groupby(["CustomerID", "year", "RevenueType"])["ActualQty"].sum().unstack(fill_value=0)
        dom = cy_channel.idxmax(axis=1).unstack()
        if 2025 not in dom.columns or 2026 not in dom.columns:
            continue
        dom_both = dom.dropna(subset=[2025, 2026])
        switched = dom_both[dom_both[2025] != dom_both[2026]]

        total_qty = g["ActualQty"].sum()
        switched_qty = g[g["CustomerID"].isin(switched.index)]["ActualQty"].sum()
        switch_share_pct = 100 * switched_qty / total_qty if total_qty else np.nan

        distinct_2025 = set(g.loc[g["year"] == 2025, "CustomerID"])
        distinct_2026 = set(g.loc[g["year"] == 2026, "CustomerID"])

        results.append({
            "division": div,
            "n_customers_active_both_years": len(dom_both),
            "n_customers_switched_dominant_channel": len(switched),
            "switch_qty_share_pct_of_2yr_total": switch_share_pct,
            "n_distinct_customers_2025": len(distinct_2025),
            "n_distinct_customers_2026": len(distinct_2026),
            "n_customers_only_2025": len(distinct_2025 - distinct_2026),
            "n_customers_only_2026": len(distinct_2026 - distinct_2025),
        })
        logger.info("[%s] %d customers active both years; %d switched dominant channel (%.2f%% of qty). "
                    "Distinct customers: %d (2025), %d (2026), turnover %d only-2025 / %d only-2026.",
                    div, len(dom_both), len(switched), switch_share_pct,
                    len(distinct_2025), len(distinct_2026), len(distinct_2025 - distinct_2026),
                    len(distinct_2026 - distinct_2025))

    result_df = pd.DataFrame(results)
    result_df.to_csv(os.path.join(SUMMARY_DIR, "phase136_customer_switch_summary.csv"), index=False)
    return result_df


# ------------------------------------------------------------------------------------------------
# Part 2 -- items (cached cube_Sale_APD pull, already V2-confirmed channel-mix source)
# ------------------------------------------------------------------------------------------------

def item_flip_analysis() -> dict:
    df = pd.read_csv(CACHED_SALES_PULL)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["year"] = df["createDate"].dt.year
    df = df[df["revenue_type"].isin(["Omni Channel", "Tendering"])].copy()
    df = df[df["year"].isin([2025, 2026])].copy()

    out = {}
    for div in DIVISIONS:
        g = df[df["division"] == div]
        item_year_channel = g.groupby(["itemcode", "year", "revenue_type"])["sale"].sum().unstack(fill_value=0.0)
        dom = item_year_channel.idxmax(axis=1).unstack()
        both_years = dom.dropna(subset=[2025, 2026]) if 2025 in dom.columns and 2026 in dom.columns else dom.iloc[0:0]
        flipped = both_years[both_years[2025] != both_years[2026]] if len(both_years) else both_years

        total_value = g[g["itemcode"].isin(both_years.index)]["sale"].sum()
        flipped_value = g[g["itemcode"].isin(flipped.index)]["sale"].sum()
        flip_share_pct = 100 * flipped_value / total_value if total_value else np.nan

        flipped.to_csv(os.path.join(SUMMARY_DIR, f"phase136_{div}_flipped_items.csv"))
        out[div] = {"n_items_both_years": len(both_years), "n_flipped": len(flipped),
                    "flip_value_share_pct": flip_share_pct, "flipped_items": flipped}
        logger.info("[%s] %d items present both years, %d flipped dominant channel (%.2f%% of value).",
                    div, len(both_years), len(flipped), flip_share_pct)
    return out


# ------------------------------------------------------------------------------------------------
# Part 3 -- timing (cached cube_Sale_APD pull, monthly value share)
# ------------------------------------------------------------------------------------------------

def monthly_timing() -> dict:
    df = pd.read_csv(CACHED_SALES_PULL)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["year_month"] = df["createDate"].dt.to_period("M")

    out = {}
    for div in DIVISIONS:
        sub = df[(df["division"] == div) & (df["createDate"] >= "2025-01-01") &
                 (df["revenue_type"].isin(["Omni Channel", "Tendering"]))]
        g = sub.groupby(["year_month", "revenue_type"])["sale"].sum().unstack(fill_value=0.0)
        g["total"] = g.sum(axis=1)
        g["tendering_share_pct"] = 100 * g.get("Tendering", 0) / g["total"]
        g.to_csv(os.path.join(SUMMARY_DIR, f"phase136_{div}_monthly_timing.csv"))
        out[div] = g
        logger.info("[%s] monthly tendering_share_pct range: %.1f - %.1f (see CSV for the full series).",
                    div, g["tendering_share_pct"].min(), g["tendering_share_pct"].max())

        # Contract-level detail for any month whose Tendering share is a local spike, to distinguish
        # "many small contracts relabeled" from "a handful of large, discrete tenders."
        spikes = g[g["tendering_share_pct"] > 50].index.astype(str).tolist()
        for ym in spikes:
            spike_rows = sub[(sub["createDate"].dt.to_period("M").astype(str) == ym) &
                              (sub["revenue_type"] == "Tendering")]
            logger.info("[%s %s spike] n_rows=%d, n_contracts=%d, n_items=%d, value=%.0f",
                        div, ym, len(spike_rows), spike_rows["contractid"].nunique(),
                        spike_rows["itemcode"].nunique(), spike_rows["sale"].sum())
    return out


# ------------------------------------------------------------------------------------------------
# Part 4 -- the 136-code sheet-overlap historical inconsistency (local file only, no DB)
# ------------------------------------------------------------------------------------------------

def sheet_overlap_check() -> dict:
    wb = openpyxl.load_workbook(PRICELIST_PATH, read_only=True, data_only=True)
    HEADER_ROW, DATA_START_ROW = 3, 5

    all_sheets_codes = {}
    for name in wb.sheetnames:
        ws = wb[name]
        rows = list(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 2000), values_only=True))
        if len(rows) < HEADER_ROW:
            continue
        header = rows[HEADER_ROW - 1]
        code_idx = next((i for i, h in enumerate(header) if h and "product code" in str(h).lower()), None)
        if code_idx is None:
            continue
        codes = {str(r[code_idx]).strip() for r in rows[DATA_START_ROW - 1:]
                 if code_idx < len(r) and r[code_idx] is not None and str(r[code_idx]).strip() != ""}
        all_sheets_codes[name] = {"state": ws.sheet_state, "codes": codes}

    pem103_sheets = [n for n in all_sheets_codes if "103" in n]
    pem107_sheets = [n for n in all_sheets_codes if "107" in n]
    pem103_all = set().union(*(all_sheets_codes[n]["codes"] for n in pem103_sheets)) if pem103_sheets else set()
    pem107_all = set().union(*(all_sheets_codes[n]["codes"] for n in pem107_sheets)) if pem107_sheets else set()
    overlap = pem103_all & pem107_all

    logger.info("PEM103-named sheets: %s", pem103_sheets)
    logger.info("PEM107-named sheets: %s", pem107_sheets)
    logger.info("Total PEM103-sheet codes (all versions): %d; PEM107-sheet codes (all versions): %d",
                len(pem103_all), len(pem107_all))
    logger.info("Overlap between ANY PEM103-named sheet and ANY PEM107-named sheet, any version "
                "(visible or hidden): %d codes", len(overlap))

    return {
        "pem103_sheets": pem103_sheets, "pem107_sheets": pem107_sheets,
        "pem103_code_count": len(pem103_all), "pem107_code_count": len(pem107_all),
        "overlap_count": len(overlap), "overlap_codes": sorted(overlap),
    }


def main():
    config = load_config()
    scope = get_scope(config)

    logger.info("=" * 100)
    logger.info("PART 1 -- customer channel-switch analysis (Cube_CES, one fresh DB connection)")
    logger.info("=" * 100)
    customers = customer_switch_analysis(scope)

    logger.info("=" * 100)
    logger.info("PART 2 -- item dominant-channel-flip analysis")
    logger.info("=" * 100)
    items = item_flip_analysis()

    logger.info("=" * 100)
    logger.info("PART 3 -- monthly timing (step change vs. gradual drift)")
    logger.info("=" * 100)
    timing = monthly_timing()

    logger.info("=" * 100)
    logger.info("PART 4 -- 136-code sheet-overlap historical inconsistency")
    logger.info("=" * 100)
    sheets = sheet_overlap_check()

    # Cross-reference: any flipped item among the (possibly empty) sheet-overlap codes?
    overlap_set = set(sheets["overlap_codes"])
    for div in DIVISIONS:
        flipped_codes = set(items[div]["flipped_items"].index)
        cross = flipped_codes & overlap_set
        logger.info("[%s] flipped items that are ALSO in the PEM103/PEM107 sheet-overlap set: %d",
                    div, len(cross))

    return customers, items, timing, sheets


if __name__ == "__main__":
    main()
