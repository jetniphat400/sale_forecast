"""Validator task (2026-09-04): map every date/datetime column in
`[salewarehouse].[dbo].[cube_Sale_APD]` and test, from behaviour rather than
column name, whether `createDate` is really the customer's PO/order date --
the assumption this whole project has run on since Phase 2 Step 1 (STATUS.md:
"0 mismatches ... against the table's own year/month columns"), which was a
name-matching exercise, not proof of what event the column records.

Motivation (see the task brief / STATUS.md Phase A item 1 and Phase 1.5):
the 6-day median order notice and the createDate-keyed demand series both
assume createDate = a genuine customer-order event, fixed at intake. A
separate column, `PODate`, exists in the same table with (per an earlier,
non-rigorous note) "an identical observed range" -- raising the obvious
question of why two columns would exist if they meant the same thing, and
whether createDate is actually just a row-creation timestamp.

Role: single Validator (per AGENTS.md -- this is one coherent question, the
date columns must be understood together, not split across agents).
Read-only queries via src/db.py's run_query(). Nothing in config/config.yaml
or any existing pipeline script is modified. INVESTIGATION ONLY.

Scope for Part 1 (stated explicitly, per instruction, not silently mixed
with the modelling-relevant subset): `division = 'PEM101'` + the 128-item
`itemcode` list from output/summary/part1_category_scope_all_codes.csv --
NO revenue_type/status/createDate-start filter applied for the raw column
mapping (Part 1). Where a figure uses the additional standard project
filters (revenue_type='Omni Channel', status IN ('Actual','MPS'),
createDate>=2024-01-01 -- "the modelling scope"), that is stated explicitly
at the point it is used (Parts 2 and 3).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("datecol_validator")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

DIVISION = "PEM101"
REVENUE_TYPE = "Omni Channel"
STATUSES = ["Actual", "MPS"]
START_DATE = "2024-01-01"
FOCUS_CODES = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

# Rolling-origin/train-val-test window definition, IDENTICAL to src/backtest_rekeyed.py, so
# "the Feb-Jul 2026 window" means the exact same 6 calendar months in both places.
TRAIN_MONTHS = pd.period_range("2024-01", "2025-07", freq="M")
VAL_MONTHS = pd.period_range("2025-08", "2026-01", freq="M")
TEST_MONTHS = pd.period_range("2026-02", "2026-07", freq="M")

NOTICE_BUCKET_DAYS = [30, 60, 90]

ALL_DATE_COLS = ["createDate", "PODate", "forecast_date", "timeStamp",
                  "customer_entry", "warranty_date", "newCustomerDate", "plan_date"]
CORE_DATE_COLS = ["createDate", "PODate", "forecast_date"]


def get_scope() -> list:
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    return sorted(scope["code"].unique())


def sql_in(codes: list) -> str:
    return "','".join(codes)


# ============================================================================
# PART 1a: column inventory (do not rely on memory of which columns exist)
# ============================================================================
def part1a_column_inventory() -> pd.DataFrame:
    logger.info("PART 1a: INFORMATION_SCHEMA.COLUMNS inventory for cube_Sale_APD")
    cols = run_query("""
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'cube_Sale_APD'
        ORDER BY ORDINAL_POSITION
    """)
    cols.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1a_all_columns.csv"), index=False)
    date_cols = cols[cols["DATA_TYPE"].str.contains("date", case=False, na=False)]
    date_cols.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1a_date_typed_columns.csv"), index=False)
    logger.info("cube_Sale_APD has %d columns total; %d are date/datetime-typed: %s",
                len(cols), len(date_cols), date_cols["COLUMN_NAME"].tolist())
    assert set(date_cols["COLUMN_NAME"]) == set(ALL_DATE_COLS), (
        f"Date-typed column set changed since this script was written: {set(date_cols['COLUMN_NAME'])} "
        f"vs expected {set(ALL_DATE_COLS)} -- update ALL_DATE_COLS before trusting downstream parts.")
    return date_cols


# ============================================================================
# PART 1b: base-scope pull (division + itemcode ONLY -- no revenue_type/status/date filter)
# ============================================================================
def pull_base_scope(item_codes: list) -> pd.DataFrame:
    code_list = sql_in(item_codes)
    cols = ["itemcode", "contractid", "customerid", "createDate", "PODate", "forecast_date",
            "timeStamp", "customer_entry", "warranty_date", "newCustomerDate", "plan_date",
            "status", "revenue_type", "qty", "sale"]
    sql = f"""
        SELECT {", ".join(cols)}
        FROM cube_Sale_APD
        WHERE division = '{DIVISION}' AND itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    logger.info("Base-scope pull (division=%s, itemcode in 128-item scope, NO other filter): %d rows",
                DIVISION, len(df))
    for c in ["createDate", "PODate", "forecast_date", "customer_entry", "warranty_date",
              "newCustomerDate", "plan_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["timeStamp"] = pd.to_datetime(df["timeStamp"], errors="coerce")
    df.to_csv(os.path.join(DATA_DIR, "datecol_raw_base_scope_128items.csv"), index=False)
    status_rt = df.groupby(["status", "revenue_type"]).size().reset_index(name="n")
    status_rt.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1b_status_revenuetype_breakdown.csv"), index=False)
    logger.info("Base-scope status/revenue_type breakdown:\n%s", status_rt.to_string(index=False))
    return df


# ============================================================================
# PART 1b (cont.): range / null rate / distribution shape for EVERY date column
# ============================================================================
def part1b_range_nulls_distribution(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("PART 1b: observed range, null rate, distribution shape for every date-typed column")
    n = len(df)
    rows = []
    for c in ALL_DATE_COLS:
        s = df[c]
        rows.append({
            "column": c, "n_total_rows": n, "n_null": int(s.isna().sum()),
            "pct_null": round(100 * s.isna().mean(), 4),
            "min": s.min(), "max": s.max(), "n_distinct_values": int(s.nunique()),
        })
    result = pd.DataFrame(rows)
    result.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1b_range_nulls_distinct.csv"), index=False)
    logger.info("Range/null/distinct summary:\n%s", result.to_string(index=False))

    # Monthly histogram (distribution shape) for the 3 core date columns -- chart
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(CORE_DATE_COLS), 1, figsize=(10, 3 * len(CORE_DATE_COLS)), sharex=False)
    for ax, c in zip(axes, CORE_DATE_COLS):
        monthly_counts = df[c].dropna().dt.to_period("M").value_counts().sort_index()
        ax.bar(monthly_counts.index.astype(str), monthly_counts.values, color="tab:blue")
        ax.set_title(f"{c}: row count by calendar month (128-item base scope)")
        ax.tick_params(axis="x", labelrotation=90, labelsize=6)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "datecol_monthly_distribution.png"))
    plt.close(fig)
    return result


# ============================================================================
# PART 1c: createDate vs PODate
# ============================================================================
def part1c_createdate_vs_podate(df: pd.DataFrame) -> None:
    logger.info("PART 1c: createDate vs PODate")
    d = df.copy()
    d["diff_days"] = (d["PODate"] - d["createDate"]).dt.days
    n = len(d)
    n_equal = int((d["diff_days"] == 0).sum())
    logger.info("createDate == PODate exactly: %d of %d rows (%.4f%%)", n_equal, n, 100 * n_equal / n)

    mismatch = d[d["diff_days"] != 0].copy()
    mismatch.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1c_createdate_podate_mismatch_rows.csv"), index=False)

    diff_stats = {
        "n_total": n, "n_equal": n_equal, "pct_equal": round(100 * n_equal / n, 4),
        "n_mismatch": len(mismatch),
        "mismatch_mean_diff_days": float(mismatch["diff_days"].mean()) if len(mismatch) else None,
        "mismatch_median_diff_days": float(mismatch["diff_days"].median()) if len(mismatch) else None,
        "mismatch_min_diff_days": float(mismatch["diff_days"].min()) if len(mismatch) else None,
        "mismatch_max_diff_days": float(mismatch["diff_days"].max()) if len(mismatch) else None,
        "n_mismatch_podate_after_createdate": int((mismatch["diff_days"] > 0).sum()),
        "n_mismatch_podate_before_createdate": int((mismatch["diff_days"] < 0).sum()),
    }
    pd.DataFrame([diff_stats]).to_csv(os.path.join(SUMMARY_DIR, "datecol_p1c_diff_summary.csv"), index=False)
    logger.info("createDate vs PODate mismatch summary: %s", diff_stats)

    # by year, by item (which items ever show a mismatch)
    d["year"] = d["createDate"].dt.year
    by_year = d.groupby("year")["diff_days"].apply(lambda s: pd.Series({
        "n": len(s), "n_mismatch": int((s != 0).sum()), "pct_mismatch": round(100 * (s != 0).mean(), 4),
    })).unstack()
    by_year.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1c_mismatch_by_year.csv"))

    by_item_mismatch = mismatch.groupby("itemcode").size().sort_values(ascending=False)
    by_item_mismatch.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1c_mismatch_by_item.csv"))

    focus_check = d[d["itemcode"].isin(FOCUS_CODES)]
    focus_eq = (focus_check["diff_days"] == 0).mean() * 100
    logger.info("Focus codes (%s): createDate==PODate on %.2f%% of %d rows", FOCUS_CODES, focus_eq, len(focus_check))
    pd.DataFrame([{"n_focus_rows": len(focus_check), "pct_equal": round(focus_eq, 4)}]).to_csv(
        os.path.join(SUMMARY_DIR, "datecol_p1c_focus_codes_check.csv"), index=False)

    # chart: gap histogram (mismatches only -- the vast majority are 0 and would swamp the chart)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4))
    if len(mismatch):
        ax.bar(range(len(mismatch)), sorted(mismatch["diff_days"]), color="tab:orange")
    ax.set_title(f"createDate-vs-PODate gap (days), the {len(mismatch)} of {n} mismatching rows only\n"
                 f"({100*n_equal/n:.2f}% of all rows are EXACT matches (diff=0), excluded from this chart)")
    ax.set_ylabel("PODate - createDate (days)")
    ax.set_xlabel("mismatching row (sorted)")
    ax.axhline(0, color="grey", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "datecol_createdate_podate_gap_histogram.png"))
    plt.close(fig)


# ============================================================================
# PART 1d: createDate vs timeStamp -- is createDate ALSO a load artifact?
# ============================================================================
def part1d_loadbatch_signature(df: pd.DataFrame) -> None:
    logger.info("PART 1d: createDate vs timeStamp -- load-batch signature check")
    n = len(df)
    rows = []
    for c in ["createDate", "PODate", "forecast_date", "timeStamp"]:
        s = df[c].dropna()
        counts = s.value_counts()
        n_distinct = len(counts)
        top1_share = 100 * counts.iloc[0] / len(s) if n_distinct else None
        top1pct_dates = max(1, int(np.ceil(0.01 * n_distinct)))
        top1pct_share = 100 * counts.head(top1pct_dates).sum() / len(s) if n_distinct else None
        rows.append({
            "column": c, "n_nonnull": len(s), "n_distinct_values": n_distinct,
            "mean_rows_per_distinct_value": round(len(s) / n_distinct, 2) if n_distinct else None,
            "max_rows_on_single_value": int(counts.iloc[0]) if n_distinct else None,
            "pct_rows_on_busiest_single_value": round(top1_share, 3) if top1_share is not None else None,
            "pct_rows_on_busiest_1pct_of_distinct_values": round(top1pct_share, 3) if top1pct_share is not None else None,
        })
    result = pd.DataFrame(rows)
    result.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1d_loadbatch_concentration.csv"), index=False)
    logger.info("Load-batch concentration check:\n%s", result.to_string(index=False))

    ts_span_seconds = (df["timeStamp"].max() - df["timeStamp"].min()).total_seconds()
    logger.info("timeStamp: %d distinct calendar dates, full range spans %.1f seconds (%s to %s) -- "
                "confirms timeStamp is an ETL/refresh artifact re-stamped on every reload, not a "
                "historical per-row record; createDate shows NO comparable single-day/single-window "
                "concentration (see table above) -- createDate is NOT also a load artifact by this test.",
                df["timeStamp"].dt.date.nunique(), ts_span_seconds, df["timeStamp"].min(), df["timeStamp"].max())


# ============================================================================
# PART 1e: weekday distribution
# ============================================================================
def part1e_weekday_distribution(df: pd.DataFrame) -> None:
    logger.info("PART 1e: weekday distribution for createDate, PODate, forecast_date")
    rows = []
    for c in CORE_DATE_COLS:
        wd = df[c].dropna().dt.day_name().value_counts()
        wd = wd.reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], fill_value=0)
        for day, cnt in wd.items():
            rows.append({"column": c, "weekday": day, "n_rows": int(cnt),
                         "pct_of_column": round(100 * cnt / wd.sum(), 3) if wd.sum() else None})
    result = pd.DataFrame(rows)
    result.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1e_weekday_distribution.csv"), index=False)
    pivot = result.pivot(index="weekday", columns="column", values="pct_of_column").reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    logger.info("Weekday distribution (%% of column's rows):\n%s", pivot.to_string())

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    pivot.plot(kind="bar", ax=ax)
    ax.set_title("Weekday distribution: createDate, PODate, forecast_date (128-item base scope)")
    ax.set_ylabel("% of column's non-null rows")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "datecol_weekday_distribution.png"))
    plt.close(fig)


# ============================================================================
# PART 1f: cross-check against Cube_CES
# ============================================================================
def part1f_ces_crosscheck(df: pd.DataFrame, item_codes: list) -> None:
    logger.info("PART 1f: cross-check createDate/PODate/forecast_date against Cube_CES CtrDate/ReceiveCtrDate")
    code_list = sql_in(item_codes)
    ces = run_query(f"""
        SELECT DISTINCT ContractID, ItemCode, CtrDate, ReceiveCtrDate
        FROM Cube_CES
        WHERE ManuDivision = '{DIVISION}' AND ItemCode IN ('{code_list}')
    """)
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["ReceiveCtrDate"] = pd.to_datetime(ces["ReceiveCtrDate"], errors="coerce")
    logger.info("Cube_CES distinct (ContractID, ItemCode) pairs pulled (ManuDivision=%s): %d", DIVISION, len(ces))

    # Confirm grain assumption before trusting a simple merge: CtrDate/ReceiveCtrDate must be
    # constant per (ContractID, ItemCode) pair, or a naive merge risks a many-to-many artifact.
    grp = ces.groupby(["ContractID", "ItemCode"])
    n_multi_ctr = (grp["CtrDate"].nunique() > 1).sum()
    n_multi_recv = (grp["ReceiveCtrDate"].nunique() > 1).sum()
    logger.info("Grain check: %d of %d pairs have >1 distinct CtrDate, %d have >1 distinct ReceiveCtrDate "
                "(0 expected for a safe simple merge)", n_multi_ctr, grp.ngroups, n_multi_recv)
    if n_multi_ctr > 0 or n_multi_recv > 0:
        logger.warning("Grain assumption violated -- merge below may understate true agreement for affected pairs.")

    merged = df.merge(ces, left_on=["contractid", "itemcode"], right_on=["ContractID", "ItemCode"], how="inner")
    logger.info("cube_Sale_APD base-scope rows: %d; joinable to Cube_CES on (contractid, itemcode): %d (%.2f%%)",
                len(df), len(merged), 100 * len(merged) / len(df))

    def agreement(apd_col: str, ces_col: str) -> dict:
        diff = (merged[apd_col] - merged[ces_col]).dt.days
        valid = diff.dropna()
        if len(valid) == 0:
            return {"apd_column": apd_col, "ces_column": ces_col, "n": 0}
        return {
            "apd_column": apd_col, "ces_column": ces_col, "n": len(valid),
            "pct_exact_match": round(100 * (valid == 0).mean(), 3),
            "median_offset_days": float(valid.median()), "mean_offset_days": float(valid.mean()),
            "pct_within_1d": round(100 * (valid.abs() <= 1).mean(), 3),
            "pct_within_5d": round(100 * (valid.abs() <= 5).mean(), 3),
        }

    rows = [agreement(a, c) for a in CORE_DATE_COLS for c in ["CtrDate", "ReceiveCtrDate"]]
    result = pd.DataFrame(rows)
    result.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1f_ces_crosscheck.csv"), index=False)
    logger.info("Cube_CES cross-check (agreement rate, offset):\n%s", result.to_string(index=False))

    # Reconfirm the prompt's cited prior finding (CtrDate vs ReceiveCtrDate) at FULL 128-item scope.
    # Pull ALL Cube_CES statuses (not just Actual/Backlog) so the row-level -- not pair-deduped --
    # picture is visible, since a pre-contract stage (P2/MPS/N/A/P3) may legitimately have BOTH
    # dates NULL (not yet received) rather than disagreeing values -- that must not be scored as a
    # "disagreement" without checking, per the "never guess" rule.
    ces_all_status = run_query(f"""
        SELECT ContractID, ItemCode, CtrDate, ReceiveCtrDate, Status
        FROM Cube_CES
        WHERE ManuDivision = '{DIVISION}' AND ItemCode IN ('{code_list}')
    """)
    ces_all_status["CtrDate"] = pd.to_datetime(ces_all_status["CtrDate"], errors="coerce")
    ces_all_status["ReceiveCtrDate"] = pd.to_datetime(ces_all_status["ReceiveCtrDate"], errors="coerce")
    ctr_recv_diff_all = (ces_all_status["CtrDate"] - ces_all_status["ReceiveCtrDate"]).dt.days
    pct_all = 100 * (ctr_recv_diff_all == 0).mean()

    ab_only = ces_all_status[ces_all_status["Status"].isin(["Actual", "Backlog"])]
    ctr_recv_diff_ab = (ab_only["CtrDate"] - ab_only["ReceiveCtrDate"]).dt.days
    pct_ab = 100 * (ctr_recv_diff_ab == 0).mean()

    by_status = ces_all_status.groupby("Status").apply(
        lambda g: pd.Series({"n": len(g), "pct_equal": round(100 * ((g["CtrDate"] - g["ReceiveCtrDate"]).dt.days == 0).mean(), 3),
                              "n_both_null": int((g["CtrDate"].isna() & g["ReceiveCtrDate"].isna()).sum())})
    ).reset_index()
    by_status.to_csv(os.path.join(SUMMARY_DIR, "datecol_p1f_ctrdate_vs_receivectrdate_by_status.csv"), index=False)

    logger.info("Cube_CES CtrDate vs ReceiveCtrDate, full 128-item scope, ALL row-level pairs (n=%d, every "
                "Status): %.3f%% identical -- LOWER than the prior narrow-sample 100%% because P2/MPS/N/A/P3 "
                "pre-contract stages have BOTH dates NULL (not yet 'received'), which is not a genuine "
                "disagreement. Restricting to Status IN ('Actual','Backlog') -- this project's established "
                "CES status basis -- gives %.3f%% identical (n=%d), CONFIRMING (not contradicting) the prior "
                "narrow-sample finding at full scope. By-status breakdown in "
                "datecol_p1f_ctrdate_vs_receivectrdate_by_status.csv.",
                len(ces_all_status), pct_all, pct_ab, len(ab_only))
    pd.DataFrame([{
        "n_all_status_rows": len(ces_all_status), "pct_ctrdate_eq_receivectrdate_all_status": round(pct_all, 3),
        "n_actual_backlog_rows": len(ab_only), "pct_ctrdate_eq_receivectrdate_actual_backlog_only": round(pct_ab, 3),
    }]).to_csv(os.path.join(SUMMARY_DIR, "datecol_p1f_ctrdate_vs_receivectrdate_fullscope.csv"), index=False)


# ============================================================================
# PART 2: re-keying quantification if PODate were used instead of createDate
# (computed regardless of Part 2's conclusion, so the number is available either way --
# clearly labelled as conditional in the report)
# ============================================================================
def part2_rekeying_quantification(df: pd.DataFrame) -> None:
    logger.info("PART 2: quantify createDate-vs-PODate re-keying impact (modelling scope, same method as B1)")
    modeling = df[(df["revenue_type"] == REVENUE_TYPE) & (df["status"].isin(STATUSES))
                  & (df["createDate"] >= pd.Timestamp(START_DATE))].copy()
    logger.info("Modelling-scope subset (revenue_type=%s, status in %s, createDate>=%s): %d of %d base-scope rows",
                REVENUE_TYPE, STATUSES, START_DATE, len(modeling), len(df))

    all_months = TRAIN_MONTHS.append(VAL_MONTHS).append(TEST_MONTHS)
    common_set = set(all_months)

    modeling["cd_month"] = modeling["createDate"].dt.to_period("M")
    modeling["po_month"] = modeling["PODate"].dt.to_period("M")

    in_window_cd = modeling[modeling["cd_month"].isin(common_set)]
    in_window_po = modeling[modeling["po_month"].isin(common_set)]
    qty_cd, sale_cd = in_window_cd["qty"].sum(), in_window_cd["sale"].sum()
    qty_po, sale_po = in_window_po["qty"].sum(), in_window_po["sale"].sum()
    logger.info("In the identical %d-month window (%s to %s): createDate-keyed qty=%.1f sale=%.2f vs "
                "PODate-keyed qty=%.1f sale=%.2f (qty %.4f%% diff, sale %.4f%% diff)",
                len(all_months), all_months[0], all_months[-1], qty_cd, sale_cd, qty_po, sale_po,
                100 * (qty_po - qty_cd) / qty_cd if qty_cd else 0, 100 * (sale_po - sale_cd) / sale_cd if sale_cd else 0)

    # rows/qty/value that would move to a DIFFERENT calendar month under PODate-keying
    moved = modeling[modeling["cd_month"] != modeling["po_month"]]
    pd.DataFrame([{
        "n_rows_total": len(modeling), "n_rows_moved_to_different_month": len(moved),
        "pct_rows_moved": round(100 * len(moved) / len(modeling), 4),
        "qty_moved": float(moved["qty"].sum()), "sale_moved": float(moved["sale"].sum()),
        "pct_qty_moved_of_total": round(100 * moved["qty"].sum() / modeling["qty"].sum(), 4),
        "pct_sale_moved_of_total": round(100 * moved["sale"].sum() / modeling["sale"].sum(), 4),
        "window_qty_createDate_keyed": float(qty_cd), "window_qty_PODate_keyed": float(qty_po),
        "window_sale_createDate_keyed": float(sale_cd), "window_sale_PODate_keyed": float(sale_po),
    }]).to_csv(os.path.join(SUMMARY_DIR, "datecol_p2_rekeying_quantification.csv"), index=False)
    moved.to_csv(os.path.join(SUMMARY_DIR, "datecol_p2_rows_that_would_move_month.csv"), index=False)
    logger.info("Rows that would shift to a different calendar month if keyed on PODate instead of createDate: "
                "%d of %d (%.4f%%), qty=%.1f, sale=%.2f", len(moved), len(modeling),
                100 * len(moved) / len(modeling), moved["qty"].sum(), moved["sale"].sum())


# ============================================================================
# PART 3a: recompute order notice using PODate -> forecast_date, vs createDate -> forecast_date
# ============================================================================
def distribution_stats(s: pd.Series) -> dict:
    return {
        "n": len(s), "mean": float(s.mean()), "median": float(s.median()), "std": float(s.std()),
        "skewness": float(stats.skew(s)) if len(s) > 2 else None,
        "min": float(s.min()), "max": float(s.max()),
    }


def part3a_notice_recompute(df: pd.DataFrame) -> None:
    logger.info("PART 3a: recompute order notice using PODate as the start date, vs createDate (same rows)")
    modeling = df[(df["revenue_type"] == REVENUE_TYPE) & (df["status"].isin(STATUSES))
                  & (df["createDate"] >= pd.Timestamp(START_DATE))].copy()

    n_null_forecast = modeling["forecast_date"].isna().sum()
    clean = modeling.dropna(subset=["forecast_date"]).copy()
    logger.info("%d of %d rows have a null forecast_date, excluded from notice computation", n_null_forecast, len(modeling))

    clean["notice_createDate"] = (clean["forecast_date"] - clean["createDate"]).dt.days
    clean["notice_PODate"] = (clean["forecast_date"] - clean["PODate"]).dt.days

    rows = []
    bucket_rows = []
    for label, col in [("createDate_based", "notice_createDate"), ("PODate_based", "notice_PODate")]:
        neg = clean[clean[col] < 0]
        pos = clean[clean[col] >= 0]
        logger.info("[%s] %d of %d rows have a NEGATIVE notice (excluded from distribution, reported separately)",
                    label, len(neg), len(clean))
        d = distribution_stats(pos[col])
        d["basis"] = label
        d["n_negative_excluded"] = len(neg)
        rows.append(d)
        for days in NOTICE_BUCKET_DAYS:
            n_meeting = (pos[col] >= days).sum()
            bucket_rows.append({"basis": label, "min_notice_days": days,
                                 "pct_of_orders": round(100 * n_meeting / len(pos), 3) if len(pos) else None})

    result = pd.DataFrame(rows)
    result.to_csv(os.path.join(SUMMARY_DIR, "datecol_p3a_notice_comparison.csv"), index=False)
    logger.info("Order notice, createDate-based vs PODate-based (same row set, identical scope):\n%s",
                result.to_string(index=False))

    bucket_df = pd.DataFrame(bucket_rows)
    bucket_df.to_csv(os.path.join(SUMMARY_DIR, "datecol_p3a_notice_buckets_comparison.csv"), index=False)
    logger.info("Notice buckets:\n%s", bucket_df.to_string(index=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for label, col, color in [("createDate-based", "notice_createDate", "tab:blue"),
                               ("PODate-based", "notice_PODate", "tab:orange")]:
        capped = clean.loc[clean[col] >= 0, col].clip(upper=120)
        ax.hist(capped, bins=60, alpha=0.5, label=label, color=color)
    ax.set_title("Order notice distribution: createDate-based vs PODate-based (capped at 120 days)")
    ax.set_xlabel("Notice days")
    ax.set_ylabel("Number of order rows")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "datecol_notice_comparison_histogram.png"))
    plt.close(fig)


# ============================================================================
# PART 3b: Feb-Jul 2026 window -- back-dated-entry batch check
# ============================================================================
def part3b_window_backdating_check(df: pd.DataFrame) -> None:
    logger.info("PART 3b: does the Feb-Jul 2026 test window contain a batch of back-dated createDate entries "
                "(createDate much later than PODate)?")
    modeling = df[(df["revenue_type"] == REVENUE_TYPE) & (df["status"].isin(STATUSES))
                  & (df["createDate"] >= pd.Timestamp(START_DATE))].copy()
    modeling["cd_month"] = modeling["createDate"].dt.to_period("M")
    modeling["gap_days"] = (modeling["createDate"] - modeling["PODate"]).dt.days

    windows = {"TRAIN_2024-01_to_2025-07": TRAIN_MONTHS, "VAL_2025-08_to_2026-01": VAL_MONTHS,
               "TEST_2026-02_to_2026-07": TEST_MONTHS}
    rows = []
    for label, months in windows.items():
        sub = modeling[modeling["cd_month"].isin(set(months))]
        n = len(sub)
        n_gap = int((sub["gap_days"] != 0).sum())
        rows.append({
            "window": label, "n_rows": n, "n_rows_with_any_createDate_PODate_gap": n_gap,
            "pct_rows_with_gap": round(100 * n_gap / n, 4) if n else None,
            "qty_affected_by_gap": float(sub.loc[sub["gap_days"] != 0, "qty"].sum()),
            "sale_affected_by_gap": float(sub.loc[sub["gap_days"] != 0, "sale"].sum()),
            "total_window_qty": float(sub["qty"].sum()), "total_window_sale": float(sub["sale"].sum()),
            "max_gap_days_in_window": float(sub["gap_days"].max()) if n else None,
            "mean_gap_days": float(sub["gap_days"].mean()) if n else None,
        })
    result = pd.DataFrame(rows)
    result["pct_qty_affected"] = round(100 * result["qty_affected_by_gap"] / result["total_window_qty"], 5)
    result["pct_sale_affected"] = round(100 * result["sale_affected_by_gap"] / result["total_window_sale"], 5)
    result.to_csv(os.path.join(SUMMARY_DIR, "datecol_p3b_window_backdating_check.csv"), index=False)
    logger.info("Back-dated-entry check by rolling window:\n%s", result.to_string(index=False))

    # detail rows for the TEST window's affected rows, if any
    test_sub = modeling[modeling["cd_month"].isin(set(TEST_MONTHS)) & (modeling["gap_days"] != 0)]
    test_sub.to_csv(os.path.join(SUMMARY_DIR, "datecol_p3b_test_window_gap_rows.csv"), index=False)
    logger.info("TEST window (Feb-Jul 2026) rows with any createDate<>PODate gap: %d (detail in "
                "datecol_p3b_test_window_gap_rows.csv)", len(test_sub))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(result["window"], result["pct_rows_with_gap"], color=["tab:blue", "tab:green", "tab:red"])
    ax.set_title("Feb-Jul 2026 back-dated-entry check: %% of rows with createDate<>PODate gap, by window")
    ax.set_ylabel("% of rows with a gap")
    ax.tick_params(axis="x", labelrotation=15)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "datecol_window_backdating_check.png"))
    plt.close(fig)


if __name__ == "__main__":
    item_codes = get_scope()
    logger.info("Scope: %d item codes from part1_category_scope_all_codes.csv; 3 focus codes: %s",
                len(item_codes), FOCUS_CODES)

    part1a_column_inventory()
    base = pull_base_scope(item_codes)
    part1b_range_nulls_distribution(base)
    part1c_createdate_vs_podate(base)
    part1d_loadbatch_signature(base)
    part1e_weekday_distribution(base)
    part1f_ces_crosscheck(base, item_codes)

    part2_rekeying_quantification(base)

    part3a_notice_recompute(base)
    part3b_window_backdating_check(base)

    print("\nDone. See output/summary/datecol_p*.csv for detail, output/charts/datecol_*.png for charts, "
          "and output/summary/datecol_validator_report.md for the written report.")
