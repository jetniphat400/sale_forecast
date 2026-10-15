"""Shared Cube_CES pull helper.

Trap (DATA_MAP.md Sec.4, #18, fixed 2026-09-25): a Q23 investigation script
(`src/investigations/phaseQ23_explorer.py`) added a `CtrDate >= '2023-01-01'` filter to its
Cube_CES pull that looked harmless but was NOT equivalent to this project's established `not_late`
method (METRICS.md Sec.18/19/20: `ForecastDelDate`-windowed, no `CtrDate` filter at pull time). It
silently dropped legitimate rows -- a contract created (`CtrDate`) before 2023 can still have a
delivery (`ForecastDelDate`/`ActualDelDate`) that falls inside a 2024+ analysis window -- and
produced a `not_late` figure unrecognizable against this project's own established headline.

This module is the one place any future script should pull Cube_CES for an item-code scope: no
date filter at pull time, ever (the established, working pattern already used successfully by
`output/data/phaseJ_cube_ces_351items.csv` and `src/investigations/phaseJ3_validator_reconciliation.py`
-- both pull the full, unbounded history for the scope and apply any date WINDOW later, in Python,
against `ForecastDelDate`/`CtrDate` as the analysis requires, never as a SQL floor that silently
discards rows before the analysis logic ever sees them).
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import run_query
from zero_row_guard import guard_nonempty

logger = logging.getLogger("cube_ces_pull")

CUBE_CES_COLUMNS = [
    "ItemCode", "ContractID", "Status", "CtrDate", "PlanDelDate", "ForecastDelDate",
    "ActualDelDate", "ActualQty", "RevenueType", "CustomerID", "CustomerName",
]


def pull_cube_ces_for_items(item_codes: list, columns: list = None, allow_empty: bool = False, revenue_type: str = None):
    """Pulls Cube_CES rows for `item_codes`, with NO date filter of any kind at the SQL level --
    the scope is itemcode only. Any date window (calibration/validation periods, a specific year,
    etc.) must be applied afterward in Python against whichever date field the analysis actually
    needs (`ForecastDelDate` for `not_late`, METRICS.md Sec.18/19/20), never re-added here as a
    pull-time floor -- that is exactly the mistake this module exists to prevent (see module
    docstring, DATA_MAP.md Trap 18).

    Raises `zero_row_guard.EmptyQueryResultError` if the pull returns zero rows, unless
    `allow_empty=True` is passed explicitly (this task's Part 0 zero-row guard -- see
    src/zero_row_guard.py; DATA_MAP.md Sec.4 Trap 7, the cube_final precedent this generalizes).

    `revenue_type` (default None: every channel, as the investigations always pulled) adds the locked scope filter
    `AND RevenueType = '<value>'` (Prompt 28; the class signals S2 and S3 pass 'Omni Channel'). It is a row filter on the
    channel, never a date filter.
    """
    cols = columns or CUBE_CES_COLUMNS
    code_list = "','".join(item_codes)
    col_list = ", ".join(cols)
    channel = f" AND RevenueType = '{revenue_type}'" if revenue_type else ""
    sql = f"""
        SELECT {col_list}
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}'){channel}
    """
    df = run_query(sql)
    guard_nonempty(df, table="Cube_CES", filter_desc=f"ItemCode IN ({len(item_codes)} codes)",
                   allow_empty=allow_empty)
    logger.info("Pulled %d Cube_CES rows for %d item codes (no date filter at pull -- "
                "any date window is applied afterward, never as a SQL floor).",
                len(df), len(item_codes))
    return df


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# PEM107 delivery-decline alert of the Min-Max page (Prompt 35: moved here from src/investigations/task2b_part4_pem107_alert.py, which now calls this code).
#
# Scope: Cube_CES rows for PEM107's Price List item codes, RevenueType = 'Omni Channel' (the filter is in the SQL), Status = 'Actual' (delivered).
# not_late (METRICS.md Sec.19, unit-weighted): share of ActualQty delivered on or before ForecastDelDate. The "before May 2026" / "from May 2026" split is by
# ForecastDelDate. The per-item table restricts "units ordered from May" and "units late" to the post-May window. Product type, description and code come from
# reference/pricelist.xlsx (PEM107 visible sheet), never from a database column. No customer column is pulled. The monthly runner calls it in step 1
# (`python src/cube_ces_pull.py --pem107-alert`, one read-only session, one login attempt); the output carries its pull time (`data_pulled_at`), so the Min-Max
# page judges its freshness by the monthly cadence (config page_timestamps).
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
import contextlib
import json
import os
from datetime import datetime

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PEM107_SPLIT_DATE = "2026-05-01"
# "Before May 2026" is bounded at this project's own standard Omni-forecast usable-era start (DATA_MAP.md: 2024-onward is the usable era): comparing about 14 years of raw
# Cube_CES history with 5 months after May would not be like for like (CONVENTIONS.md "compare only like with like").
PEM107_BEFORE_WINDOW_START = "2024-01-01"
PEM107_ALERT_JSON = os.path.join(SUMMARY_DIR, "task2b_part4_pem107_alert.json")
PEM107_ITEMS_CSV = os.path.join(SUMMARY_DIR, "task2b_part4_pem107_alert_items.csv")
PEM107_CES_RAW = os.path.join(SUMMARY_DIR, "task2b_part4_cube_ces_raw.csv")
PEM107_COLUMNS = ["ItemCode", "ContractID", "Status", "RevenueType", "ForecastDelDate", "ActualDelDate", "ActualQty"]
PEM107_REVENUE_TYPE = "Omni Channel"


def compute_pem107_alert(ces: pd.DataFrame, pl_pem107: pd.DataFrame, item_codes: list, pull_time: str) -> tuple:
    """(alert dict, per-item DataFrame) from the pulled Cube_CES rows `ces`, PEM107's Price List rows `pl_pem107` (columns code, type, description) and the item codes.
    No input or output: the pull and the writing are `pull_pem107_alert`."""
    d = ces[(ces["Status"] == "Actual") & (ces["RevenueType"] == "Omni Channel")].copy()
    d["ForecastDelDate"] = pd.to_datetime(d["ForecastDelDate"], errors="coerce")
    d["ActualDelDate"] = pd.to_datetime(d["ActualDelDate"], errors="coerce")
    d = d[d["ForecastDelDate"].notna() & d["ActualDelDate"].notna() & d["ActualQty"].notna()]
    d["late"] = d["ActualDelDate"] > d["ForecastDelDate"]
    d["period"] = None
    split = pd.Timestamp(PEM107_SPLIT_DATE)
    window_start = pd.Timestamp(PEM107_BEFORE_WINDOW_START)
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

    subtotal_by_type = item_df.groupby("product_type", as_index=False).agg(
        units_ordered_from_may=("units_ordered_from_may", "sum"),
        units_late=("units_late", "sum"))

    alert = {
        "not_late_before_may_2026_pct": nl_before, "units_before_may_2026": units_before,
        "not_late_from_may_2026_pct": nl_after, "units_from_may_2026": units_after,
        "split_date": PEM107_SPLIT_DATE,
        "before_window_start": PEM107_BEFORE_WINDOW_START,
        "data_pulled_at": pull_time,
        "source": {
            "pricelist": "reference/pricelist.xlsx, PEM107 visible sheet (PRICELIST RULE)",
            "delivery": "Cube_CES, Status='Actual', RevenueType='Omni Channel', ActualDelDate vs ForecastDelDate",
            "metric": "METRICS.md Sec.19 (not_late, unit-weighted)",
        },
        "limitations": [
            "\"Before May 2026\" is bounded at {} (this project's established Omni-forecast usable-era start), not Cube_CES's full ~14-year history -- comparing all history against 5 post-May months would not be like-for-like.".format(PEM107_BEFORE_WINDOW_START),
            "Post-May-2026 volume is small (n={} units) relative to the prior period (n={} units) -- a few large orders can move the percentage a lot.".format(units_after, units_before),
            "The cause of the decline is undetermined -- DATA_MAP.md Sec.7 (PEM107 branch): the business-stated May-2026 production/stock separation has no reliable, uniquely-attributable data trace (the one candidate field, cube_final.division, shows an identical step a year earlier with no known cause), and no behavioural measure shows a discrete shift exactly at May 2026 (the drop is volatile, concentrated in June).",
            "What was actually separated in May 2026 (stock/warehouses, production lines/staff, or both) is not confirmed by any data check to date -- an open point for the business to clarify, not inferred here.",
        ],
        "subtotal_by_product_type": subtotal_by_type.to_dict("records"),
    }
    return alert, item_df


def pem107_pricelist_rows(root: str = PROJECT_ROOT) -> tuple:
    """(PEM107 rows of the Price List with code, type, description; their sorted codes)."""
    from pricelist_reader import load_visible_product_rows
    pl = load_visible_product_rows(os.path.join(root, "reference", "pricelist.xlsx"))
    pl_pem107 = pl[pl["business"] == "PEM107"][["code", "type", "description"]].drop_duplicates("code")
    return pl_pem107, sorted(pl_pem107["code"].unique())


def pull_pem107_alert(root: str = PROJECT_ROOT, in_open_session: bool = False, now: datetime = None) -> dict:
    """Pulls Cube_CES for PEM107's codes (Omni Channel in the SQL; read only; ONE session, no retry: a login failure raises; `in_open_session` True when the caller holds the
    session), computes the alert and writes the alert JSON (dated: `data_pulled_at`), the per-item CSV and the raw pull. Returns the counts."""
    import db
    pl_pem107, item_codes = pem107_pricelist_rows(root)
    summary = os.path.join(root, "output", "summary")
    pull_time = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    with (contextlib.nullcontext() if in_open_session else db.session()):
        ces = pull_cube_ces_for_items(item_codes, columns=PEM107_COLUMNS, allow_empty=True, revenue_type=PEM107_REVENUE_TYPE)
    os.makedirs(summary, exist_ok=True)
    ces.to_csv(os.path.join(summary, os.path.basename(PEM107_CES_RAW)), index=False)
    alert, item_df = compute_pem107_alert(ces, pl_pem107, item_codes, pull_time)
    item_df.to_csv(os.path.join(summary, os.path.basename(PEM107_ITEMS_CSV)), index=False)
    with open(os.path.join(summary, os.path.basename(PEM107_ALERT_JSON)), "w", encoding="utf-8") as f:
        json.dump(alert, f, indent=2, default=str)
    logger.info("PEM107 alert: not_late before the split %s%% (n=%s units), from it %s%% (n=%s units); %d Cube_CES rows",
                alert["not_late_before_may_2026_pct"], alert["units_before_may_2026"], alert["not_late_from_may_2026_pct"], alert["units_from_may_2026"], len(ces))
    return {"pulled_at_local": pull_time, "rows": {"cube_ces_omni": int(len(ces)), "items_in_alert": int(len(item_df))}, "written_to": PEM107_ALERT_JSON.replace(PROJECT_ROOT, "").lstrip("\\/")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--pem107-alert" in sys.argv[1:]:
        import db
        db.require_reachable()
        print(json.dumps(pull_pem107_alert(), default=str))
    else:
        print("usage: python src/cube_ces_pull.py --pem107-alert")
