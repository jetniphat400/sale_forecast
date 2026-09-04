"""Task 2 -- build the final per-item classification table for the 16 no-history/no-sale
items in the 128-item Fuse/Surge Arrester scope. Merges all evidence gathered by
task2_no_history_investigation.py and task2_pricelist_version_check.py, and attaches a
classification, confidence level, and evidence notes per item.
"""
import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

CLASSIFICATION = {
    "EEE-F-FL-1040030100": (
        "(d) Listed but never sold", "High",
        "Zero rows in cube_Sale_APD (any filter), Cube_CES, cube_inventory_tran, "
        "Cube_Inventory_Exact, Cube_Quotation. Present in pricelist Version1 (hidden) AND "
        "Version2 (visible) -- not new to the current version, so a 'new item, not yet "
        "reached market' story cannot be dated from pricelist evidence alone.",
    ),
    "HS-F-99-1241H03": (
        "(d) Listed but never sold", "High",
        "Zero rows in every one of the 5 tables checked (same pattern as "
        "EEE-F-FL-1040030100). Present in Version1 (hidden) and Version2 (visible).",
    ),
    "HS-F-99-0181": (
        "(d) Listed but never sold", "Moderate",
        "Cube_CES: 2 rows, both pipeline-stage (P2), zero Actual/Backlog ever. "
        "Cube_Quotation: 1 row, status Process, a real named customer (name redacted -- "
        "customer identity is business-sensitive, not committed to this public repo; see "
        "the un-redacted CSV in output/summary/), qty 1, forecast_date 2026-08-13 -- a "
        "live, currently-open, unconverted quotation, not a dead SKU. Stock: 2 warehouse "
        "rows, both zero.",
    ),
    "HS-F-99-1181": (
        "(d) Listed but never sold", "Moderate",
        "Cube_CES: 4 pipeline rows (P2, 2024-2026), zero Actual/Backlog. Cube_Quotation: "
        "1 row, status Process, qty 9, forecast_date 2026-08-28 -- live unconverted quote. "
        "Stock: 1 warehouse row, zero.",
    ),
    "HS-F-99-1211H22": (
        "(d) Listed but never sold", "Moderate-High",
        "Cube_CES: only 1 pipeline row ever (P2, 2024-12-19, qty 1), zero Actual/Backlog. "
        "No Cube_Quotation row. No Cube_Inventory_Exact row at all (not even a zero-stock "
        "row) -- weakest activity signal of the 4 pipeline-only items.",
    ),
    "HS-F-99-3031": (
        "(d) Listed but never sold", "Moderate",
        "Cube_CES: 2 pipeline rows (P2, 2025-04), zero Actual/Backlog ever. No "
        "Cube_Quotation row. Stock: 1 warehouse row, zero.",
    ),
    "EEE-F-FL-5920-353-01100": (
        "Cannot classify cleanly -- closest (c) apparent dormancy/decline, NOT confirmed",
        "Moderate",
        "Cube_CES: 6 Actual rows 2018-2022 (54,000 lifetime units); the 2 largest "
        "(2022-06-30, 20,000 units) are explicitly tagged RevenueType=Omni Channel, "
        "ManuDivision/SaleDivision=PEM101 -- genuinely inside this project's channel and "
        "division scope, excluded ONLY by the 2024-01-01 date-window cutoff, not by "
        "division or revenue_type. Nothing since 2022 except 2 tiny pipeline quotes "
        "(2023, 2024). A scope-boundary/recency effect, not a cross-channel effect -- "
        "flagged as distinct from the (b)-leaning items below.",
    ),
    "EEE-F-FL-5920-353-01600": (
        "(b)-leaning, not fully confirmed", "Low-Moderate",
        "Cube_CES: 3 Actual rows 2019-2022 (12,503 units); RevenueType is blank/NULL for "
        "all 3 (a genuine data gap, not inferred) -- channel cannot be confirmed. Most "
        "recent (2022-05-11, qty 3) is credited to SaleDivision=PEM105 (cross-division "
        "sales credit), supporting 'sold, credited elsewhere' but not proof of which "
        "revenue channel.",
    ),
    "EEE-F-FL-5920-353-02600": (
        "(b) Sold, exclusively via Tendering channel", "High",
        "Directly confirmed in cube_Sale_APD itself: 4 rows under revenue_type=Tendering "
        "(divisions PEM101 and PSS), 24,000 qty and ~3.05-3.50M THB each, 2025-2026. "
        "Independently corroborated by Cube_CES (10 Actual rows, 88,500 lifetime units, "
        "the 4 most recent explicitly Tendering) and Cube_Quotation (4 rows, all "
        "quotation_status=Success, Tendering, two named customers (names redacted -- "
        "customer identity is business-sensitive, not committed to this public repo; see "
        "the un-redacted CSV in output/summary/)). Genuinely active and successful -- "
        "simply outside this project's Omni Channel scope entirely, not dormant.",
    ),
    "EEE-F-FL-5920-353-06600": (
        "(b) Sold via Tendering (2023), plus a live unconverted Omni-Channel quote",
        "Moderate-High",
        "Cube_CES: 4 Actual rows (2019, 2022 blank RevenueType; 2023-06-12 and "
        "2023-06-30 explicitly Tendering, divisions PTS and PEM101), 18,500 lifetime "
        "units. Cube_Quotation: 1 row, status Process, Omni Channel, qty 1, "
        "forecast_date 2026-09-18 (a future-dated, still-open forecast entry, not an "
        "anomaly).",
    ),
    "FC-A-38-00203": (
        "(b)-leaning, not fully confirmed", "Moderate",
        "Cube_CES: 1 Actual row (2022-12-19, qty 6, SaleDivision=PEM105, RevenueType "
        "blank). Independently, cube_inventory_tran shows 126 real movement "
        "transactions 2019-2026 (1,602 units out, 1,752 in) across transtypes "
        "B/N/150/151/A -- codes not decodable from the schema or any documentation "
        "found, so these movements cannot be conclusively confirmed as sales versus "
        "internal transfers/scrap/samples. Currently holds real stock: warehouse "
        "WH21, stock=150, available=101.",
    ),
    "HS-F-99-1151": (
        "(b)-leaning, not fully confirmed", "Low-Moderate",
        "Cube_CES: 2 Actual rows (2017, 2021; 12 lifetime units), both "
        "SaleDivision=PEM105, RevenueType blank (channel unconfirmed). Dormant since "
        "2021 aside from 4 tiny pipeline quotes (2024-2025).",
    ),
    "HS-F-99-2091N": (
        "Cannot classify cleanly -- mixed cross-division and live-pipeline evidence",
        "Low-Moderate",
        "Cube_CES: 2 Actual rows, both 2021, 6 lifetime units -- one under "
        "ManuDivision=PMW101 (a genuinely different manufacturing division from "
        "PEM101), one under PEM101/PEM101 but RevenueType blank. 5 pipeline rows "
        "(P2/P3, 2025-2026). Cube_Quotation: 2 live Process rows, Omni Channel, two named "
        "customers (names redacted -- customer identity is business-sensitive, not "
        "committed to this public repo; see the un-redacted CSV in output/summary/), "
        "most recent forecast_date 2026-08-22 -- real, current customer interest, "
        "unconverted.",
    ),
    "HS-F-99-3121": (
        "Cannot classify cleanly -- closest (c) apparent dormancy, NOT confirmed",
        "Moderate",
        "Cube_CES: 3 Actual rows; the earliest (2020-02-14, qty 13) is explicitly "
        "RevenueType=Omni Channel, ManuDivision/SaleDivision=PEM101 -- genuinely inside "
        "this project's scope, excluded only by the 2024-01-01 date window (same "
        "scope-boundary pattern as EEE-F-FL-5920-353-01100). The 2 later rows (2022, "
        "blank RevenueType) add 6 more units. Currently holds a small real stock "
        "(12 units) in a warehouse coded NCRM -- meaning not confirmed from the "
        "schema, not guessed.",
    ),
    "HS-F-99-3331": (
        "(b) Sold under a different division (PPD101)", "Moderate",
        "Cube_CES: 1 Actual row (2021-05-19, qty 6), ManuDivision AND SaleDivision "
        "both = PPD101 -- a genuinely different division from PEM101 (stronger "
        "evidence than a blank-RevenueType case, since the division field itself "
        "differs). 4 tiny pipeline rows since (2023-2025).",
    ),
    "HS-F-99-3361": (
        "Cannot classify cleanly -- mixed same-division/blank-channel and "
        "live-pipeline evidence", "Low-Moderate",
        "Cube_CES: 2 Actual rows (2022-04-20, 3 units each, ManuDivision/SaleDivision "
        "both PEM101, RevenueType blank -- channel unconfirmed, cannot rule Omni "
        "Channel in or out). 4 pipeline rows since. Cube_Quotation: 2 live Process "
        "rows, Omni Channel, two named customers (names redacted -- customer identity "
        "is business-sensitive, not committed to this public repo; see the un-redacted "
        "CSV in output/summary/), most recent forecast_date 2026-08-17.",
    ),
}

if __name__ == "__main__":
    m = pd.read_csv(os.path.join(SUMMARY_DIR, "task2_master_evidence_16items.csv"))
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv")).rename(
        columns={"code": "itemcode"})
    m = scope.merge(m, on="itemcode")

    m["classification"] = m["itemcode"].map(lambda c: CLASSIFICATION[c][0])
    m["confidence"] = m["itemcode"].map(lambda c: CLASSIFICATION[c][1])
    m["notes"] = m["itemcode"].map(lambda c: CLASSIFICATION[c][2])

    out_cols = [
        "itemcode", "category", "type", "n_ces_rows", "n_ces_actual", "n_ces_backlog",
        "n_ces_pipeline_P_T", "last_ces_actual_ctrdate", "total_ces_actual_qty",
        "ces_actual_revenuetypes", "last_ces_pipeline_forecastdeldate",
        "has_any_row_cube_Sale_APD_nofilter", "has_inventory_tran_rows",
        "has_inventory_exact_row", "current_stock_qty_sum", "has_positive_current_stock",
        "has_quotation_row", "quotation_max_create_date", "in_pricelist_version1_hidden",
        "in_pricelist_version2_visible", "classification", "confidence", "notes",
    ]
    m = m[out_cols]
    m.to_csv(os.path.join(SUMMARY_DIR, "task2_per_item_classification_final.csv"), index=False)
    print("Written output/summary/task2_per_item_classification_final.csv")
    print("\nClassification counts:")
    print(m["classification"].value_counts())
    print("\nConfidence counts:")
    print(m["confidence"].value_counts())
