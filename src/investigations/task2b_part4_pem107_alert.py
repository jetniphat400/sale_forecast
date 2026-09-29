"""Task 2b, Part 4 -- PEM107 delivery-decline alert, computed fresh at build time from Cube_CES.

DATABASE ACCESS RULE: one connection attempt (one query). On a failed login, stop, do not retry.

Scope: Cube_CES rows for PEM107's pricelist item codes, RevenueType='Omni Channel' (Cube_CES's OWN
native column, DATA_MAP.md Sec.2 -- no join to cube_Sale_APD needed), Status='Actual' (delivered).

Definitions:
  not_late (METRICS.md Sec.19, unit-weighted): share of ActualQty delivered ON OR BEFORE
    ForecastDelDate (ActualDelDate <= ForecastDelDate).
  "before May 2026" / "from May 2026" split: by ForecastDelDate (the delivery-DUE window each row
    belongs to) -- consistent with how the same split is already reported project-wide
    (DATA_MAP.md Sec.7, PEM107 branch: "not_late fell from ~89% before May 2026 to ~57% after").
  Per-item table: "units ordered from May 2026" / "units late" are BOTH restricted to the
    post-May-2026 window (ForecastDelDate >= 2026-05-01) -- this table's purpose is to show which
    items drive the post-May decline, so its two count columns describe that window specifically;
    the two not_late percentages compare each item's own before/after performance. This scoping
    choice is stated here explicitly, not left implicit.

PRICELIST RULE: Product Type/Description/Code come from reference/pricelist.xlsx's PEM107 visible
sheet, never a database column.

No customer_name/cusname column is pulled or printed.
"""
import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from cube_ces_pull import pull_cube_ces_for_items
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task2b_part4")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference")

SPLIT_DATE = "2026-05-01"
# "Before May 2026" is bounded at this project's own standard Omni-forecast usable-era start
# (DATA_MAP.md: "2024-onward is the project's usable era" for cube_Sale_APD; Cube_CES's own
# "dense/comparable data begins January 2023") -- comparing ~14 years of raw Cube_CES history
# against 5 months post-May would not be a like-for-like comparison (CONVENTIONS.md "compare only
# like with like"). Stated explicitly here and in the alert's own source/limitations text, not a
# silent filter.
BEFORE_WINDOW_START = "2024-01-01"
OUT_ALERT_JSON = os.path.join(SUMMARY_DIR, "task2b_part4_pem107_alert.json")
OUT_ITEM_CSV = os.path.join(SUMMARY_DIR, "task2b_part4_pem107_alert_items.csv")
OUT_CES_RAW = os.path.join(SUMMARY_DIR, "task2b_part4_cube_ces_raw.csv")


def main():
    pl = load_visible_product_rows(os.path.join(REFERENCE_DIR, "pricelist.xlsx"))
    pl_pem107 = pl[pl["business"] == "PEM107"][["code", "type", "description"]].drop_duplicates("code")
    item_codes = sorted(pl_pem107["code"].unique())
    logger.info("PEM107 pricelist item codes: %d", len(item_codes))

    if os.path.exists(OUT_CES_RAW):
        logger.info("Reusing already-pulled raw Cube_CES data from %s (this task's own earlier "
                     "pull, not a fresh connection) -- DATABASE ACCESS RULE: no second attempt made.",
                     OUT_CES_RAW)
        ces = pd.read_csv(OUT_CES_RAW)
        pull_time = None
        with open(OUT_ALERT_JSON, encoding="utf-8") as f:
            pull_time = json.load(f).get("data_pulled_at")
    else:
        logger.info("DATABASE ACCESS RULE: opening the single connection attempt now. No retry on "
                     "a failed login.")
        pull_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            ces = pull_cube_ces_for_items(
                item_codes,
                columns=["ItemCode", "ContractID", "Status", "RevenueType", "ForecastDelDate", "ActualDelDate", "ActualQty"],
                allow_empty=True)
        except Exception as exc:
            logger.error("DATABASE ACCESS RULE: the single connection attempt failed. Verbatim error: %r", exc)
            raise
        ces.to_csv(OUT_CES_RAW, index=False)

    d = ces[(ces["Status"] == "Actual") & (ces["RevenueType"] == "Omni Channel")].copy()
    d["ForecastDelDate"] = pd.to_datetime(d["ForecastDelDate"], errors="coerce")
    d["ActualDelDate"] = pd.to_datetime(d["ActualDelDate"], errors="coerce")
    d = d[d["ForecastDelDate"].notna() & d["ActualDelDate"].notna() & d["ActualQty"].notna()]
    d["late"] = d["ActualDelDate"] > d["ForecastDelDate"]
    d["period"] = None
    split = pd.Timestamp(SPLIT_DATE)
    window_start = pd.Timestamp(BEFORE_WINDOW_START)
    d = d[d["ForecastDelDate"] >= window_start]
    d.loc[d["ForecastDelDate"] < split, "period"] = "before_may_2026"
    d.loc[d["ForecastDelDate"] >= split, "period"] = "from_may_2026"

    def not_late_unit_weighted(sub):
        tot = sub["ActualQty"].sum()
        if tot == 0:
            return None, 0
        not_late_qty = sub.loc[~sub["late"], "ActualQty"].sum()
        return float(100 * not_late_qty / tot), int(tot)

    before = d[d["period"] == "before_may_2026"]
    after = d[d["period"] == "from_may_2026"]
    nl_before, units_before = not_late_unit_weighted(before)
    nl_after, units_after = not_late_unit_weighted(after)

    total_late_units_after = float(after.loc[after["late"], "ActualQty"].sum())

    # Per-item table: units ordered/late restricted to the post-May window (see module docstring).
    rows = []
    for code in item_codes:
        sub_after = after[after["ItemCode"] == code]
        sub_before = before[before["ItemCode"] == code]
        units_ordered = float(sub_after["ActualQty"].sum())
        units_late = float(sub_after.loc[sub_after["late"], "ActualQty"].sum())
        nl_after_item, _ = not_late_unit_weighted(sub_after)
        nl_before_item, _ = not_late_unit_weighted(sub_before)
        share_of_all_late = (units_late / total_late_units_after) if total_late_units_after else None
        pl_row = pl_pem107[pl_pem107["code"] == code]
        rows.append(dict(
            product_type=pl_row["type"].iloc[0] if len(pl_row) else None,
            product_description=pl_row["description"].iloc[0] if len(pl_row) else None,
            product_code=code,
            units_ordered_from_may=units_ordered,
            units_late=units_late,
            not_late_from_may_pct=nl_after_item,
            not_late_before_may_pct=nl_before_item,
            share_of_all_late_units_pct=(100 * share_of_all_late) if share_of_all_late is not None else None,
        ))
    item_df = pd.DataFrame(rows)
    item_df = item_df[item_df["units_ordered_from_may"] > 0].sort_values("units_late", ascending=False)
    item_df.to_csv(OUT_ITEM_CSV, index=False)

    subtotal_by_type = item_df.groupby("product_type", as_index=False).agg(
        units_ordered_from_may=("units_ordered_from_may", "sum"),
        units_late=("units_late", "sum"))

    alert = {
        "not_late_before_may_2026_pct": nl_before, "units_before_may_2026": units_before,
        "not_late_from_may_2026_pct": nl_after, "units_from_may_2026": units_after,
        "split_date": SPLIT_DATE,
        "before_window_start": BEFORE_WINDOW_START,
        "data_pulled_at": pull_time,
        "source": {
            "pricelist": "reference/pricelist.xlsx, PEM107 visible sheet (PRICELIST RULE)",
            "delivery": "Cube_CES, Status='Actual', RevenueType='Omni Channel', ActualDelDate vs ForecastDelDate",
            "metric": "METRICS.md Sec.19 (not_late, unit-weighted)",
        },
        "limitations": [
            "\"Before May 2026\" is bounded at {} (this project's established Omni-forecast usable-era start), not Cube_CES's full ~14-year history -- comparing all history against 5 post-May months would not be like-for-like.".format(BEFORE_WINDOW_START),
            "Post-May-2026 volume is small (n={} units) relative to the prior period (n={} units) -- a few large orders can move the percentage a lot.".format(units_after, units_before),
            "The cause of the decline is undetermined -- DATA_MAP.md Sec.7 (PEM107 branch): the business-stated May-2026 production/stock separation has no reliable, uniquely-attributable data trace (the one candidate field, cube_final.division, shows an identical step a year earlier with no known cause), and no behavioural measure shows a discrete shift exactly at May 2026 (the drop is volatile, concentrated in June).",
            "What was actually separated in May 2026 (stock/warehouses, production lines/staff, or both) is not confirmed by any data check to date -- an open point for the business to clarify, not inferred here.",
        ],
        "subtotal_by_product_type": subtotal_by_type.to_dict("records"),
    }
    with open(OUT_ALERT_JSON, "w", encoding="utf-8") as f:
        json.dump(alert, f, indent=2, default=str)

    logger.info("not_late before May 2026: %.2f%% (n=%d units) -- from May 2026: %.2f%% (n=%d units)",
                nl_before or 0, units_before, nl_after or 0, units_after)
    logger.info("Top 5 items by units_late:\n%s", item_df.head(5).to_string(index=False))
    print("DONE")


if __name__ == "__main__":
    main()
