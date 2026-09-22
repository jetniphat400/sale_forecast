"""Phase E1-fix-2, Part 1: full pair-level diff of Cube_Backlog vs Cube_CES(Status='Backlog')
for the PEM101 128-item pilot scope.

Goal (per task instruction, not METRICS.md itself -- this is a diagnostic, METRICS.md Sec.14 is
NOT edited here): for every (contract, item) pair present in one source but not the other, report
quantity/dates/status from whichever source holds it, GROUP the differences by cause, and decide
which source is the superset of genuinely open, undelivered, uncancelled orders.

Read-only. Single DB connection attempt (per task's DATABASE ACCESS RULE) -- if the very first
query fails, the script stops and raises; nothing here retries a failed connection. All
subsequent queries reuse the same already-proven credentials, so they are not independent
"attempts" under that rule.

Live tables (Cube_Backlog, Cube_CES) refresh daily -- re-running this script will not reproduce
identical figures. Snapshot date recorded in the printed output.
"""
import datetime
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import run_query  # noqa: E402
from phaseE1_common import PROJECT_ROOT, load_config, load_scope  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1fix2_part1")

SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
BACKLOG_TABLE = "[salewarehouse].[dbo].[Cube_Backlog]"
CES_TABLE = "[salewarehouse].[dbo].[Cube_CES]"


def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    config = load_config()
    scope = load_scope(config)
    codes = sorted(scope["code"].tolist())
    code_list = "','".join(codes)
    logger.info("Scope: %d PEM101 pilot items", len(codes))

    # ---- Single connection attempt: first query. If this raises, do not retry -- stop. ----
    try:
        backlog_all = run_query(f"""
            SELECT docID, itemcode, quantity, status, sale_company, sale_division, division,
                   company, deliverydate, plan_deliverydate, receivedate, timestamp
            FROM {BACKLOG_TABLE} WHERE itemcode IN ('{code_list}')""")
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: single connection attempt failed, not retrying. "
                      "Error: %r", exc)
        raise

    ces_all = run_query(f"""
        SELECT ContractID, ItemCode, Status, ActualQty, BacklogQty, PlanQty, ManuDivision, Company,
               CtrDate, ForecastDelDate, PlanDelDate, ActualDelDate, Timestamp
        FROM {CES_TABLE} WHERE ItemCode IN ('{code_list}')""")

    snapshot_ts = datetime.datetime.now().isoformat(timespec="seconds")
    print("=" * 100)
    print(f"Snapshot taken: {snapshot_ts} (live tables -- will differ on re-run)")
    print("=" * 100)

    # ---- Diagnostics: distinct status/company/division values, refresh recency ----
    print("\n--- Cube_Backlog: distinct status values (scope items) ---")
    print(backlog_all["status"].value_counts(dropna=False).to_string())
    print("\n--- Cube_Backlog: distinct sale_company values ---")
    print(backlog_all["sale_company"].astype(str).str.strip().value_counts(dropna=False).to_string())
    print(f"\nCube_Backlog timestamp range (scope items): {backlog_all['timestamp'].min()} to {backlog_all['timestamp'].max()}")

    print("\n--- Cube_CES: distinct Status values (scope items) ---")
    print(ces_all["Status"].value_counts(dropna=False).to_string())
    print("\n--- Cube_CES: distinct ManuDivision values ---")
    print(ces_all["ManuDivision"].astype(str).str.strip().value_counts(dropna=False).to_string())
    print(f"\nCube_CES Timestamp range (scope items): {ces_all['Timestamp'].min()} to {ces_all['Timestamp'].max()}")

    # ---- Apply project convention filters (same as phaseE1_common.py / phaseE1fix_validator.py) ----
    backlog_all["sale_company"] = backlog_all["sale_company"].astype(str).str.strip()
    backlog = backlog_all[backlog_all["sale_company"].isin(["PEM", "CI"])].copy()
    ces_all["ManuDivision"] = ces_all["ManuDivision"].astype(str).str.strip()
    ces = ces_all[ces_all["ManuDivision"] == "PEM101"].copy()
    ces_backlog = ces[ces["Status"] == "Backlog"].copy()

    print(f"\nCube_Backlog: {len(backlog_all)} raw rows -> {len(backlog)} after sale_company IN (PEM,CI)")
    print(f"Cube_CES: {len(ces_all)} raw rows -> {len(ces)} after ManuDivision==PEM101 -> "
          f"{len(ces_backlog)} after Status=='Backlog'")

    # ---- Build (contract, item) pair-level aggregates ----
    def agg_backlog(df):
        return df.groupby(["docID", "itemcode"], as_index=False).agg(
            quantity=("quantity", "sum"),
            statuses=("status", lambda s: sorted(set(s.dropna()))),
            deliverydate_min=("deliverydate", "min"),
            deliverydate_max=("deliverydate", "max"),
            plan_deliverydate_min=("plan_deliverydate", "min"),
            plan_deliverydate_max=("plan_deliverydate", "max"),
            timestamp_max=("timestamp", "max"),
            n_rows=("docID", "size"),
        )

    def agg_ces(df):
        return df.groupby(["ContractID", "ItemCode"], as_index=False).agg(
            backlog_qty=("BacklogQty", "sum"),
            actual_qty=("ActualQty", "sum"),
            statuses=("Status", lambda s: sorted(set(s.dropna()))),
            ctrdate_min=("CtrDate", "min"),
            ctrdate_max=("CtrDate", "max"),
            forecastdeldate_min=("ForecastDelDate", "min"),
            forecastdeldate_max=("ForecastDelDate", "max"),
            timestamp_max=("Timestamp", "max"),
            n_rows=("ContractID", "size"),
        )

    bl_pair = agg_backlog(backlog)
    ces_backlog_pair = agg_ces(ces_backlog)
    ces_all_pair = agg_ces(ces)  # any status, for status-mismatch lookup

    bl_keys = set(zip(bl_pair["docID"], bl_pair["itemcode"]))
    ces_bl_keys = set(zip(ces_backlog_pair["ContractID"], ces_backlog_pair["ItemCode"]))
    ces_any_keys = set(zip(ces_all_pair["ContractID"], ces_all_pair["ItemCode"]))
    bl_any_status_keys = set(zip(
        agg_backlog(backlog_all[backlog_all["sale_company"].isin(["PEM", "CI"])])["docID"],
        agg_backlog(backlog_all[backlog_all["sale_company"].isin(["PEM", "CI"])])["itemcode"]))

    only_in_backlog = bl_keys - ces_bl_keys
    only_in_ces_backlog = ces_bl_keys - bl_keys
    both = bl_keys & ces_bl_keys

    print(f"\nPair-level counts: Cube_Backlog={len(bl_keys)} distinct (docID,item) pairs, "
          f"Cube_CES(Status=Backlog)={len(ces_bl_keys)} distinct (ContractID,item) pairs")
    print(f"In both: {len(both)}; only in Cube_Backlog: {len(only_in_backlog)}; "
          f"only in Cube_CES(Backlog): {len(only_in_ces_backlog)}")
    union_n = len(bl_keys | ces_bl_keys)
    print(f"Match rate vs union: {len(both)/union_n*100:.2f}%" if union_n else "n/a")

    # ---- Cause grouping for "only in Cube_Backlog" pairs ----
    ces_status_by_key = {(r.ContractID, r.ItemCode): r.statuses for r in ces_all_pair.itertuples()}
    rows_backlog_only = []
    cause_counts_bl_only = {"different_status_in_ces": 0, "absent_from_ces_entirely": 0, "other": 0}
    for _, r in bl_pair[bl_pair.apply(lambda x: (x["docID"], x["itemcode"]) in only_in_backlog, axis=1)].iterrows():
        key = (r["docID"], r["itemcode"])
        ces_statuses = ces_status_by_key.get(key)
        if ces_statuses:
            cause = f"different_status_in_ces:{','.join(ces_statuses)}"
            cause_counts_bl_only["different_status_in_ces"] += 1
        elif key not in ces_any_keys:
            cause = "absent_from_ces_entirely"
            cause_counts_bl_only["absent_from_ces_entirely"] += 1
        else:
            cause = "other"
            cause_counts_bl_only["other"] += 1
        rows_backlog_only.append({
            "docID": r["docID"], "itemcode": r["itemcode"], "quantity": r["quantity"],
            "backlog_statuses": r["statuses"], "deliverydate_min": r["deliverydate_min"],
            "deliverydate_max": r["deliverydate_max"], "plan_deliverydate_min": r["plan_deliverydate_min"],
            "plan_deliverydate_max": r["plan_deliverydate_max"], "backlog_timestamp_max": r["timestamp_max"],
            "n_rows": r["n_rows"], "cause": cause, "ces_statuses_for_pair": ces_statuses,
        })
    df_backlog_only = pd.DataFrame(rows_backlog_only)

    # ---- Cause grouping for "only in Cube_CES(Backlog)" pairs ----
    bl_status_by_key = {}
    bl_all_pair_kept = agg_backlog(backlog_all[backlog_all["sale_company"].isin(["PEM", "CI"])])
    for r in bl_all_pair_kept.itertuples():
        bl_status_by_key[(r.docID, r.itemcode)] = r.statuses

    rows_ces_only = []
    cause_counts_ces_only = {"different_status_in_backlog": 0, "absent_from_backlog_entirely": 0, "other": 0}
    for _, r in ces_backlog_pair[ces_backlog_pair.apply(
            lambda x: (x["ContractID"], x["ItemCode"]) in only_in_ces_backlog, axis=1)].iterrows():
        key = (r["ContractID"], r["ItemCode"])
        bl_statuses = bl_status_by_key.get(key)
        if bl_statuses:
            cause = f"different_status_in_backlog:{','.join(bl_statuses)}"
            cause_counts_ces_only["different_status_in_backlog"] += 1
        elif key not in bl_any_status_keys:
            cause = "absent_from_backlog_entirely"
            cause_counts_ces_only["absent_from_backlog_entirely"] += 1
        else:
            cause = "other"
            cause_counts_ces_only["other"] += 1
        rows_ces_only.append({
            "ContractID": r["ContractID"], "ItemCode": r["ItemCode"], "backlog_qty": r["backlog_qty"],
            "actual_qty": r["actual_qty"], "ces_statuses": r["statuses"],
            "ctrdate_min": r["ctrdate_min"], "ctrdate_max": r["ctrdate_max"],
            "forecastdeldate_min": r["forecastdeldate_min"], "forecastdeldate_max": r["forecastdeldate_max"],
            "ces_timestamp_max": r["timestamp_max"], "n_rows": r["n_rows"], "cause": cause,
            "backlog_statuses_for_pair": bl_statuses,
        })
    df_ces_only = pd.DataFrame(rows_ces_only)

    # ---- Timing-difference sub-check: for "absent entirely" pairs, is the delivery/forecast
    # date near either table's refresh boundary (suggests the pair moved out during the gap
    # between the two tables' last refresh, not a real discrepancy)? ----
    bl_refresh = backlog_all["timestamp"].max()
    ces_refresh = ces_all["Timestamp"].max()
    print(f"\nCube_Backlog max timestamp (refresh) for scope items: {bl_refresh}")
    print(f"Cube_CES max Timestamp (refresh) for scope items: {ces_refresh}")
    refresh_gap_days = abs((pd.to_datetime(bl_refresh) - pd.to_datetime(ces_refresh)).days)
    print(f"Refresh gap between the two tables: {refresh_gap_days} day(s)")

    def near_refresh_boundary(date_val, ref_ts, window_days=3):
        if pd.isna(date_val) or pd.isna(ref_ts):
            return False
        return abs((pd.to_datetime(date_val) - pd.to_datetime(ref_ts)).days) <= window_days

    n_timing_bl_only = 0
    if len(df_backlog_only):
        n_timing_bl_only = df_backlog_only.apply(
            lambda r: r["cause"] == "absent_from_ces_entirely" and
            (near_refresh_boundary(r["deliverydate_max"], ces_refresh) or
             near_refresh_boundary(r["plan_deliverydate_max"], ces_refresh)), axis=1).sum()
    n_timing_ces_only = 0
    if len(df_ces_only):
        n_timing_ces_only = df_ces_only.apply(
            lambda r: r["cause"] == "absent_from_backlog_entirely" and
            (near_refresh_boundary(r["forecastdeldate_max"], bl_refresh) or
             near_refresh_boundary(r["ctrdate_max"], bl_refresh)), axis=1).sum()
    print(f"Of 'absent entirely' pairs: {n_timing_bl_only} Backlog-only pairs have a delivery/plan "
          f"date within 3 days of Cube_CES's refresh timestamp (candidate timing artefact)")
    print(f"                            {n_timing_ces_only} Cube_CES-only pairs have a forecast/ctr "
          f"date within 3 days of Cube_Backlog's refresh timestamp (candidate timing artefact)")

    # ---- Report ----
    print("\n" + "=" * 100)
    print("CAUSE BREAKDOWN -- pairs only in Cube_Backlog (not in Cube_CES Status='Backlog')")
    print("=" * 100)
    for cause, n in cause_counts_bl_only.items():
        print(f"  {cause}: {n}")
    if len(df_backlog_only):
        print(df_backlog_only.to_string())

    print("\n" + "=" * 100)
    print("CAUSE BREAKDOWN -- pairs only in Cube_CES(Status='Backlog') (not in Cube_Backlog)")
    print("=" * 100)
    for cause, n in cause_counts_ces_only.items():
        print(f"  {cause}: {n}")
    if len(df_ces_only):
        print(df_ces_only.to_string())

    # ---- Quantity totals for "genuinely open, undelivered, uncancelled" comparison ----
    qty_backlog_table = float(backlog["quantity"].sum())
    qty_ces_backlog = float(ces_backlog["BacklogQty"].sum())
    print(f"\nTotal quantity, Cube_Backlog (sale_company IN PEM,CI): {qty_backlog_table:,.1f}")
    print(f"Total quantity, Cube_CES(Status='Backlog', ManuDivision=PEM101).BacklogQty: {qty_ces_backlog:,.1f}")

    # cancelled-status leakage check: does either source retain rows for cancelled contracts?
    cancel_like = [s for s in ces_all["Status"].dropna().unique() if "cancel" in s.lower()]
    print(f"\nCube_CES Status values containing 'cancel': {cancel_like}")
    if cancel_like:
        cancel_keys = set(zip(
            ces_all[ces_all["Status"].isin(cancel_like)]["ContractID"],
            ces_all[ces_all["Status"].isin(cancel_like)]["ItemCode"]))
        leaked_in_backlog = bl_keys & cancel_keys
        print(f"Cube_Backlog pairs that are ALSO tagged cancelled in Cube_CES: {len(leaked_in_backlog)} "
              f"(if >0, Cube_Backlog is retaining cancelled orders -- would OVER-count open demand)")

    # ---- Save CSVs ----
    df_backlog_only.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix2_part1_backlog_only_pairs.csv"), index=False)
    df_ces_only.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix2_part1_ces_only_pairs.csv"), index=False)
    backlog.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix2_part1_backlog_raw.csv"), index=False)
    ces.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix2_part1_ces_raw.csv"), index=False)

    return {
        "n_backlog_pairs": len(bl_keys), "n_ces_backlog_pairs": len(ces_bl_keys),
        "n_both": len(both), "n_backlog_only": len(only_in_backlog), "n_ces_only": len(only_in_ces_backlog),
        "cause_counts_bl_only": cause_counts_bl_only, "cause_counts_ces_only": cause_counts_ces_only,
        "qty_backlog_table": qty_backlog_table, "qty_ces_backlog": qty_ces_backlog,
        "leaked_cancelled_in_backlog": len(leaked_in_backlog) if cancel_like else None,
    }


if __name__ == "__main__":
    main()
