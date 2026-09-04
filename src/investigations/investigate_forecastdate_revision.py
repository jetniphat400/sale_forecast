"""Phase A / Task A1 (2026-09-02): is `forecast_date` (cube_Sale_APD) a fixed
PO-intake promise, or does it (or its Cube_CES equivalents) get revised after
first being recorded?

This is the task STATUS.md flags twice as an open caveat ("whether
forecast_date ... represents a fixed PO-intake promise or a continuously-
updated latest plan") and lists as Phase A item 1. Two headline business
facts (6-day median order notice; 57.8%/61.0%/68.6%/73.2% on-time delivery by
year) both assume forecast_date/PlanDelDate are fixed at intake. This script
tests that assumption directly rather than re-deriving it from a column name.

Role: combined Explorer (join/query results, match rates) + Validator (data
quality, contradiction-checking). No business interpretation of *why* beyond
what the joins/patterns directly show; no min/max, no model, no config.yaml
change; nothing committed.

INVESTIGATION ONLY — read-only queries against the database via src/db.py's
run_query(). Credentials are never printed or logged.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_forecastdate_revision")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

DIVISION = "PEM101"
REVENUE_TYPE = "Omni Channel"
APD_STATUSES = ["Actual", "MPS"]
APD_START_DATE = "2024-01-01"

CES_STATUSES = ["Actual", "Backlog"]
CES_START_DATE = "2023-01-01"

FOCUS_CODES = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

TODAY = pd.Timestamp.now().normalize()


def get_scope() -> list:
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    return sorted(scope["code"].unique())


def sql_in_list(codes: list) -> str:
    return "','".join(codes)


# ============================================================================
# TASK 1: epoch/future-date anomaly check, independent of the user's own quick check
# ============================================================================
def task1_anomaly_check(item_codes: list) -> pd.DataFrame:
    logger.info("TASK 1: epoch/future-date anomaly check (own fresh query, no division/revenue_type/status filter)")
    rows = []
    for label, codes in [("full_128_scope", item_codes), ("3_focus_codes", FOCUS_CODES)]:
        code_list = sql_in_list(codes)
        sql = f"""
            SELECT
                COUNT(*) AS n_rows,
                MIN(createDate) AS min_createDate, MAX(createDate) AS max_createDate,
                MIN(forecast_date) AS min_forecast_date, MAX(forecast_date) AS max_forecast_date,
                SUM(CASE WHEN forecast_date <= '1971-01-01' THEN 1 ELSE 0 END) AS n_forecast_epoch,
                SUM(CASE WHEN forecast_date >= '2030-01-01' THEN 1 ELSE 0 END) AS n_forecast_far_future,
                SUM(CASE WHEN createDate > GETDATE() THEN 1 ELSE 0 END) AS n_createDate_future,
                SUM(CASE WHEN forecast_date IS NULL THEN 1 ELSE 0 END) AS n_forecast_null
            FROM cube_Sale_APD
            WHERE itemcode IN ('{code_list}')
        """
        df = run_query(sql)
        df.insert(0, "scope", label)
        df.insert(1, "n_items", len(codes))
        rows.append(df)
        logger.info("scope=%s: n_rows=%d createDate=[%s, %s] forecast_date=[%s, %s] epoch=%d far_future=%d "
                    "createDate_future=%d forecast_null=%d",
                    label, df["n_rows"].iloc[0], df["min_createDate"].iloc[0], df["max_createDate"].iloc[0],
                    df["min_forecast_date"].iloc[0], df["max_forecast_date"].iloc[0],
                    df["n_forecast_epoch"].iloc[0], df["n_forecast_far_future"].iloc[0],
                    df["n_createDate_future"].iloc[0], df["n_forecast_null"].iloc[0])
    result = pd.concat(rows, ignore_index=True)
    result.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task1_anomaly_check.csv"), index=False)

    # Pull the actual anomalous rows, if any exist anywhere in the 128-item scope, for direct inspection.
    code_list = sql_in_list(item_codes)
    anomaly_sql = f"""
        SELECT itemcode, contractid, createDate, forecast_date, status, division, revenue_type
        FROM cube_Sale_APD
        WHERE itemcode IN ('{code_list}')
          AND (forecast_date <= '1971-01-01' OR forecast_date >= '2030-01-01' OR createDate > GETDATE())
    """
    anomaly_rows = run_query(anomaly_sql)
    anomaly_rows.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task1_anomaly_rows_if_any.csv"), index=False)
    logger.info("Anomalous rows found anywhere in the 128-item scope (any division/revenue_type/status): %d",
                len(anomaly_rows))
    return result


# ============================================================================
# TASK 2: forecast_date (cube_Sale_APD) vs ForecastDelDate/PlanDelDate/ActualDelDate (Cube_CES)
# ============================================================================
def pull_apd(item_codes: list) -> pd.DataFrame:
    code_list = sql_in_list(item_codes)
    status_list = sql_in_list(APD_STATUSES)
    sql = f"""
        SELECT itemcode, contractid, customerid, createDate, forecast_date, qty, sale, status
        FROM cube_Sale_APD
        WHERE itemcode IN ('{code_list}')
          AND division = '{DIVISION}' AND revenue_type = '{REVENUE_TYPE}'
          AND status IN ('{status_list}') AND createDate >= '{APD_START_DATE}'
    """
    df = run_query(sql)
    logger.info("Fresh pull of cube_Sale_APD: %d rows (division=%s, revenue_type=%s, status in %s, createDate >= %s)",
                len(df), DIVISION, REVENUE_TYPE, APD_STATUSES, APD_START_DATE)
    return df


def pull_ces_with_planid(item_codes: list, statuses: list, start_date: str) -> pd.DataFrame:
    code_list = sql_in_list(item_codes)
    status_list = sql_in_list(statuses)
    sql = f"""
        SELECT ContractID, ItemCode, PlanID, CustomerID, CtrDate, PlanDelDate, ForecastDelDate, ActualDelDate,
               Status, PlanQty, ActualQty, BacklogQty
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
          AND ManuDivision = '{DIVISION}' AND RevenueType = '{REVENUE_TYPE}'
          AND Status IN ('{status_list}') AND CtrDate >= '{start_date}'
    """
    df = run_query(sql)
    logger.info("Fresh pull of Cube_CES (with PlanID): %d rows (ManuDivision=%s, RevenueType=%s, Status in %s, "
                "CtrDate >= %s)", len(df), DIVISION, REVENUE_TYPE, statuses, start_date)
    return df


def task2_compare_dates(apd: pd.DataFrame, ces: pd.DataFrame) -> None:
    logger.info("TASK 2: comparing cube_Sale_APD.forecast_date vs Cube_CES ForecastDelDate/PlanDelDate/ActualDelDate")
    apd = apd.copy()
    ces = ces.copy()
    apd["createDate"] = pd.to_datetime(apd["createDate"])
    apd["forecast_date"] = pd.to_datetime(apd["forecast_date"], errors="coerce")
    for c in ["CtrDate", "PlanDelDate", "ForecastDelDate", "ActualDelDate"]:
        ces[c] = pd.to_datetime(ces[c], errors="coerce")

    apd_valid = apd.dropna(subset=["forecast_date"]).copy()
    apd_valid["apd_row_id"] = range(len(apd_valid))
    logger.info("APD rows with a non-null forecast_date usable for comparison: %d of %d", len(apd_valid), len(apd))

    # Many-to-many join on (contractid, itemcode): APD is one row per (contract,item,createDate,status);
    # Cube_CES is one row per PlanID (finer grain, e.g. one contract+item can have several tranches with
    # different dates). A naive cross-join compares every APD row against every one of that pair's
    # CES rows, which manufactures spurious large "differences" whenever an APD row is compared against
    # the WRONG tranche's CES row. To avoid that artifact, for every APD row we pick the single BEST-
    # matching CES row (the one with the smallest |forecast_date - ForecastDelDate|, ties broken
    # arbitrarily) and compare PlanDelDate/ActualDelDate from THAT SAME row only. This was verified by
    # hand on several contracts with multiple tranches (e.g. CTR-2024-05379, 3 tranches/item) before
    # being adopted, and confirmed to correctly pair each APD row with its own tranche.
    merged_all = apd_valid.merge(
        ces, left_on=["contractid", "itemcode"], right_on=["ContractID", "ItemCode"], how="inner",
        suffixes=("_apd", "_ces"),
    )
    logger.info("Cross-join rows (APD row x matched Cube_CES PlanID row) for scope, before best-match selection: %d",
                len(merged_all))
    merged_all["_diff_forecast_abs"] = (merged_all["forecast_date"] - merged_all["ForecastDelDate"]).dt.days.abs()
    merged = (merged_all.sort_values(["apd_row_id", "_diff_forecast_abs"])
                         .groupby("apd_row_id", as_index=False).first())
    logger.info("APD rows after selecting each one's single best-matching Cube_CES row: %d", len(merged))

    merged["diff_vs_ForecastDelDate"] = (merged["forecast_date"] - merged["ForecastDelDate"]).dt.days
    merged["diff_vs_PlanDelDate"] = (merged["forecast_date"] - merged["PlanDelDate"]).dt.days
    merged["diff_vs_ActualDelDate"] = (merged["forecast_date"] - merged["ActualDelDate"]).dt.days

    def pair_level_summary(apd_df: pd.DataFrame, merged_df: pd.DataFrame, label: str) -> dict:
        apd_pairs = apd_df.drop_duplicates(subset=["contractid", "itemcode"])[["contractid", "itemcode"]]
        n_apd_rows = len(apd_df)
        n_apd_pairs = len(apd_pairs)
        joinable_pairs = merged_df.drop_duplicates(subset=["contractid", "itemcode"])[["contractid", "itemcode"]]
        n_joinable_pairs = len(joinable_pairs)

        # exact match: does ANY matched Cube_CES row for this APD row have identical date?
        exact_forecast = merged_df.groupby(["contractid", "itemcode", "createDate", "forecast_date"])[
            "diff_vs_ForecastDelDate"].apply(lambda s: (s == 0).any())
        exact_plan = merged_df.groupby(["contractid", "itemcode", "createDate", "forecast_date"])[
            "diff_vs_PlanDelDate"].apply(lambda s: (s == 0).any())
        n_apd_obligations = len(exact_forecast)  # distinct (contract,item,createDate,forecast_date) APD "obligations" that had >=1 CES match

        return {
            "scope": label,
            "n_apd_rows_forecast_date_notnull": n_apd_rows,
            "n_distinct_apd_pairs": n_apd_pairs,
            "n_joinable_pairs_in_ces": n_joinable_pairs,
            "pct_pairs_joinable": round(100 * n_joinable_pairs / n_apd_pairs, 2) if n_apd_pairs else None,
            "n_apd_obligations_with_ces_match": n_apd_obligations,
            "pct_exact_match_vs_ForecastDelDate": round(100 * exact_forecast.mean(), 2) if n_apd_obligations else None,
            "pct_exact_match_vs_PlanDelDate": round(100 * exact_plan.mean(), 2) if n_apd_obligations else None,
        }

    summaries = [pair_level_summary(apd_valid, merged, "full_128_scope")]
    for code in FOCUS_CODES:
        apd_f = apd_valid[apd_valid["itemcode"] == code]
        merged_f = merged[merged["itemcode"] == code]
        summaries.append(pair_level_summary(apd_f, merged_f, f"focus_{code}"))
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task2_join_match_summary.csv"), index=False)
    logger.info("Task 2 pair-level summary:\n%s", summary_df.to_string(index=False))

    # Disagreement distribution (all rows, not just exact match) -- direction and magnitude
    def diff_stats(s: pd.Series) -> dict:
        s = s.dropna()
        if len(s) == 0:
            return {"n": 0}
        return {
            "n": len(s), "mean": float(s.mean()), "median": float(s.median()), "std": float(s.std()),
            "pct_exact_zero": round(100 * (s == 0).mean(), 2),
            "pct_apd_later": round(100 * (s > 0).mean(), 2),  # forecast_date AFTER the CES date
            "pct_apd_earlier": round(100 * (s < 0).mean(), 2),
            "q1": float(s.quantile(0.25)), "q3": float(s.quantile(0.75)),
            "min": float(s.min()), "max": float(s.max()),
        }

    diff_rows = []
    for label, sub in [("full_128_scope", merged)] + [(f"focus_{c}", merged[merged["itemcode"] == c]) for c in FOCUS_CODES]:
        for col in ["diff_vs_ForecastDelDate", "diff_vs_PlanDelDate", "diff_vs_ActualDelDate"]:
            d = diff_stats(sub[col])
            d["scope"] = label
            d["comparison"] = col
            diff_rows.append(d)
    diff_df = pd.DataFrame(diff_rows)
    diff_df.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task2_date_diff_distribution.csv"), index=False)
    logger.info("Task 2 diff distributions written to phaseA_a1_task2_date_diff_distribution.csv")

    merged.to_csv(os.path.join(DATA_DIR, "phaseA_a1_processed_apd_ces_joined_dates.csv"), index=False)


# ============================================================================
# TASK 3a: cube_Sale_APD -- same (contractid, itemcode, createDate) with DIFFERENT forecast_date
# ============================================================================
def task3a_same_createdate_diff_forecast(apd: pd.DataFrame) -> None:
    logger.info("TASK 3a: same (contractid, itemcode, createDate) with a DIFFERENT forecast_date in cube_Sale_APD")
    apd = apd.copy()
    apd["createDate"] = pd.to_datetime(apd["createDate"])
    apd["forecast_date"] = pd.to_datetime(apd["forecast_date"], errors="coerce")
    valid = apd.dropna(subset=["forecast_date"])

    grp = valid.groupby(["contractid", "itemcode", "createDate"])["forecast_date"].nunique()
    n_total_groups = len(grp)
    n_multi = (grp > 1).sum()
    logger.info("Groups (contractid, itemcode, createDate): %d total, %d (%.2f%%) have >1 distinct forecast_date",
                n_total_groups, n_multi, 100 * n_multi / n_total_groups if n_total_groups else 0)

    flagged_keys = grp[grp > 1].index
    if len(flagged_keys) > 0:
        flagged = valid.set_index(["contractid", "itemcode", "createDate"]).loc[flagged_keys].reset_index()
        flagged = flagged.sort_values(["contractid", "itemcode", "createDate"])
    else:
        flagged = valid.iloc[0:0].copy()
    flagged.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3a_same_createdate_diff_forecast.csv"), index=False)

    summary = pd.DataFrame([{
        "n_groups_total": n_total_groups, "n_groups_with_multiple_forecast_dates": int(n_multi),
        "pct_groups_with_multiple_forecast_dates": round(100 * n_multi / n_total_groups, 4) if n_total_groups else None,
        "n_rows_in_flagged_groups": len(flagged),
    }])
    summary.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3a_summary.csv"), index=False)
    logger.info("Task 3a summary: %s", summary.to_dict(orient="records")[0])


# ============================================================================
# TASK 3b: Cube_CES PlanID-level disagreement -- revision vs legitimate multi-tranche
# ============================================================================
def task3b_planid_disagreement(ces_all_status: pd.DataFrame) -> None:
    logger.info("TASK 3b: Cube_CES PlanID-level disagreement within (ContractID, ItemCode)")
    ces = ces_all_status.copy()
    for c in ["CtrDate", "PlanDelDate", "ForecastDelDate", "ActualDelDate"]:
        ces[c] = pd.to_datetime(ces[c], errors="coerce")

    grp = ces.groupby(["ContractID", "ItemCode"])
    n_pairs_total = grp.ngroups
    multi_planid_pairs = grp.filter(lambda g: g["PlanID"].nunique() > 1)
    n_pairs_multi = multi_planid_pairs.groupby(["ContractID", "ItemCode"]).ngroups
    logger.info("(ContractID,ItemCode) pairs: %d total, %d (%.2f%%) have >1 distinct PlanID",
                n_pairs_total, n_pairs_multi, 100 * n_pairs_multi / n_pairs_total if n_pairs_total else 0)

    # Classification logic (revised from a first-pass version that used "same PlanQty across PlanIDs"
    # as the revision signal -- rejected on inspection: several genuine equal-sized multi-tranche
    # orders (e.g. 500 units delivered in July + 500 more booked for October) have identical PlanQty
    # across PlanIDs by coincidence, which is normal, not evidence of revision. The decisive signal
    # instead is whether ActualDelDate (a REAL, already-happened delivery event) differs across the
    # PlanIDs: if it does, these are provably separate physical deliveries (genuine tranches),
    # regardless of whether their planned quantities happen to match.
    classification_rows = []
    for (contract, item), g in multi_planid_pairs.groupby(["ContractID", "ItemCode"]):
        g = g.drop_duplicates(subset=["PlanID"]).sort_values("PlanID")
        n_planid = g["PlanID"].nunique()
        qty_col = g["PlanQty"].round(6)
        n_distinct_qty = qty_col.nunique()
        n_distinct_forecastdel = g["ForecastDelDate"].nunique(dropna=True)
        n_distinct_plandel = g["PlanDelDate"].nunique(dropna=True)
        n_distinct_actualdel = g["ActualDelDate"].nunique(dropna=True)
        n_actual_notnull = g["ActualDelDate"].notna().sum()

        if n_distinct_actualdel > 1:
            # Two or more PlanIDs already have DIFFERENT real delivery dates -- provably separate
            # physical delivery events, cannot be a single obligation's date being revised.
            classification = "MULTIPLE_DISTINCT_ACTUAL_DATES_genuine_separate_tranches"
        elif n_distinct_qty > 1:
            classification = "different_qty_consistent_with_separate_tranches"
        elif n_distinct_forecastdel <= 1 and n_distinct_plandel <= 1:
            classification = "true_duplicate_rows_same_qty_same_dates"
        else:
            # Same PlanQty, and either a single shared ActualDelDate or none at all (still pending),
            # but ForecastDelDate/PlanDelDate disagree across PlanIDs. This is the only bucket
            # genuinely AMBIGUOUS between "revision of one obligation's plan" and "two coincidentally
            # equal-sized separate open orders" -- cannot be told apart from this data (see report).
            classification = "REVISION_CANDIDATE_same_qty_same_or_no_actual_but_dates_disagree"

        classification_rows.append({
            "ContractID": contract, "ItemCode": item, "n_planid": n_planid,
            "n_distinct_planqty": n_distinct_qty, "n_distinct_ForecastDelDate": n_distinct_forecastdel,
            "n_distinct_PlanDelDate": n_distinct_plandel, "n_distinct_ActualDelDate": n_distinct_actualdel,
            "n_actual_notnull": n_actual_notnull, "classification": classification,
        })

    class_df = pd.DataFrame(classification_rows)
    class_df.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3b_planid_classification.csv"), index=False)

    if len(class_df):
        class_counts = class_df["classification"].value_counts()
        logger.info("Task 3b classification counts:\n%s", class_counts.to_string())
    else:
        class_counts = pd.Series(dtype=int)
        logger.info("Task 3b: no (ContractID,ItemCode) pairs with >1 PlanID found in this scope.")

    summary = pd.DataFrame([{
        "n_pairs_total": n_pairs_total, "n_pairs_with_multiple_planid": n_pairs_multi,
        **{f"n_{k}": v for k, v in class_counts.items()},
    }])
    summary.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3b_summary.csv"), index=False)

    # Focus codes detail
    focus_class = class_df[class_df["ItemCode"].isin(FOCUS_CODES)]
    focus_class.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3b_focus_codes_detail.csv"), index=False)
    logger.info("Focus-code PlanID-disagreement rows: %d", len(focus_class))


# ============================================================================
# TASK 3c: audit/history/version table + Timestamp re-check (targeted, not full 108-table repeat)
# ============================================================================
def task3c_audit_trail_and_timestamp_check(item_codes: list) -> None:
    logger.info("TASK 3c: targeted re-check -- column names in cube_Sale_APD/Cube_CES suggesting a modification "
                "timestamp; independent re-verification of Cube_CES.Timestamp for the 3 focus items")

    col_sql = """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME IN ('cube_Sale_APD', 'Cube_CES')
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """
    cols = run_query(col_sql)
    cols.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3c_all_columns.csv"), index=False)
    keywords = ["modif", "updat", "chang", "revis", "edit", "version", "audit", "log", "history"]
    hits = cols[cols["COLUMN_NAME"].str.lower().str.contains("|".join(keywords), na=False)]
    hits.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3c_column_keyword_hits.csv"), index=False)
    logger.info("Columns in cube_Sale_APD/Cube_CES matching modification/history keywords (%s): %d found",
                keywords, len(hits))
    if len(hits):
        logger.info("Hits:\n%s", hits.to_string(index=False))

    code_list = sql_in_list(FOCUS_CODES)
    ts_sql = f"""
        SELECT ItemCode, PlanID, ContractID, CtrDate, ForecastDelDate, PlanDelDate, ActualDelDate, Timestamp, Status
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
    """
    ts_df = run_query(ts_sql)
    ts_df["Timestamp"] = pd.to_datetime(ts_df["Timestamp"], errors="coerce")
    ts_df.to_csv(os.path.join(DATA_DIR, "phaseA_a1_processed_focus_items_ces_timestamps.csv"), index=False)

    n_rows = len(ts_df)
    ts_min, ts_max = ts_df["Timestamp"].min(), ts_df["Timestamp"].max()
    span_seconds = (ts_max - ts_min).total_seconds() if pd.notna(ts_min) and pd.notna(ts_max) else None
    n_distinct_ts = ts_df["Timestamp"].nunique()
    logger.info("3 focus items, all Cube_CES rows (n=%d): Timestamp range [%s, %s], span=%.1fs, %d distinct values",
                n_rows, ts_min, ts_max, span_seconds if span_seconds is not None else -1, n_distinct_ts)

    summary = pd.DataFrame([{
        "n_rows": n_rows, "timestamp_min": ts_min, "timestamp_max": ts_max,
        "span_seconds": span_seconds, "n_distinct_timestamp_values": n_distinct_ts,
        "today": str(TODAY.date()),
    }])
    summary.to_csv(os.path.join(SUMMARY_DIR, "phaseA_a1_task3c_focus_timestamp_summary.csv"), index=False)


if __name__ == "__main__":
    item_codes = get_scope()
    logger.info("Scope: %d item codes from part1_category_scope_all_codes.csv; 3 focus codes: %s",
                len(item_codes), FOCUS_CODES)

    task1_result = task1_anomaly_check(item_codes)

    apd = pull_apd(item_codes)
    apd.to_csv(os.path.join(DATA_DIR, "phaseA_a1_raw_apd_fresh_pull.csv"), index=False)

    ces_scoped = pull_ces_with_planid(item_codes, CES_STATUSES, CES_START_DATE)
    ces_scoped.to_csv(os.path.join(DATA_DIR, "phaseA_a1_raw_ces_fresh_pull_scoped.csv"), index=False)

    task2_compare_dates(apd, ces_scoped)
    task3a_same_createdate_diff_forecast(apd)

    # Task 3b uses ALL Cube_CES statuses (not just Actual/Backlog) to see the full PlanID picture,
    # explicitly wider than the project's standard delivery-performance scope -- stated here, not silent.
    ces_all_status = pull_ces_with_planid(
        item_codes,
        ["Actual", "Backlog", "P2", "Cancel", "MPS", "P3", "N/A", "None", "T1", "T2", "T3", "F", "Y"],
        CES_START_DATE,
    )
    ces_all_status.to_csv(os.path.join(DATA_DIR, "phaseA_a1_raw_ces_fresh_pull_all_status.csv"), index=False)
    task3b_planid_disagreement(ces_all_status)

    task3c_audit_trail_and_timestamp_check(item_codes)

    print("\nDone. See output/summary/phaseA_a1_task*.csv for detail and "
          "output/summary/phaseA_a1_forecastdate_revision_findings.md for the written report.")
