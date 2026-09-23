"""Phase J3 -- Explorer D -- analysis over already-pulled data (no further DB access).

Runs entirely on cached files:
  - output/data/phaseI_combined_scope_351items.csv       (item -> division map)
  - output/summary/phaseJ2_explorerD_cube_ces_raw.csv     (Cube_CES, 351-item scope, all statuses,
                                                            OLMJobCode included -- Phase J2's own
                                                            successful pull, reused unchanged)
  - output/data/phaseI_raw_sales_351items.csv             (cube_Sale_APD, 351-item scope)
  - output/summary/task2_cube_final_jobno_match.csv       (stale, narrow, 2026-08-31 ad hoc pull --
                                                            39 rows / 4 items -- used ONLY as a
                                                            small, explicitly-caveated illustrative
                                                            check, never generalised)

This session's own fresh cube_final pull (phaseJ3_explorerD_pull.py) returned ZERO rows for the
same 351-item scope -- a clean, uninterrupted second failure to retrieve real batch-date data (not
explained by the Phase J2 process-kill). Steps 1/2/4-lead-time of the task brief that depend on
cube_final's own date fields (final_date, fg_pack_date, etc.) are therefore reported as CANNOT BE
DETERMINED, not guessed. Steps 3 and 4-cadence are computed here from the Cube_CES OLMJobCode
batch/token proxy (the same proxy Phase J2 used), independently recomputed (not merely re-read) so
this session's own figures are directly checkable against Phase J2's.
"""
import logging
import os

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ3_explorerD_analysis")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")
CES_OLM_FILE = os.path.join(SUMMARY_DIR, "phaseJ2_explorerD_cube_ces_raw.csv")
SALES_FILE = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")
TASK2_FILE = os.path.join(SUMMARY_DIR, "task2_cube_final_jobno_match.csv")

OUT_TOKEN_TABLE = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_token_batches.csv")
OUT_CADENCE_ITEM = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_cadence_per_item.csv")
OUT_CADENCE_DIVISION = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_cadence_per_division.csv")
OUT_REVERSE_OVERALL = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_reverse_traceability_overall.csv")
OUT_REVERSE_DIVISION = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_reverse_traceability_per_division.csv")
OUT_LAG_DIST = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_lag_distribution.csv")
OUT_LEGACY_ILLUSTRATIVE = os.path.join(SUMMARY_DIR, "phaseJ3_explorerD_legacy_cube_final_illustrative.csv")


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else np.nan


def dist_stats(series):
    s = pd.Series(series).dropna()
    if len(s) == 0:
        return dict(n=0, median=np.nan, p25=np.nan, p75=np.nan, min=np.nan, max=np.nan, mean=np.nan)
    return dict(
        n=len(s), median=float(s.median()), p25=pct(s, 25), p75=pct(s, 75),
        min=float(s.min()), max=float(s.max()), mean=float(s.mean()),
    )


def main():
    scope = pd.read_csv(SCOPE_FILE)
    item_division = scope.set_index("code")["division"].to_dict()

    ces = pd.read_csv(CES_OLM_FILE, parse_dates=["CtrDate", "ForecastDelDate", "ActualDelDate"])
    logger.info("Loaded Cube_CES OLMJobCode file: %d rows", len(ces))
    logger.info("Status counts:\n%s", ces["Status"].value_counts().to_string())

    # Project convention: Actual + Backlog is this project's established Cube_CES scope
    # (METRICS.md Sec.14/18; phaseJ_single_pull.py). Other statuses in this unfiltered pull
    # (P2/P3/Cancel/F/T2/T3/P1/MPS-in-CES -- a different concept from cube_Sale_APD's own MPS,
    # DATA_MAP.md Sec.2 Trap 4) are quotation/other pipeline stages, excluded here to match the
    # rest of the project's Cube_CES usage.
    ces_ab = ces[ces["Status"].isin(["Actual", "Backlog"])].copy()
    logger.info("Restricted to Actual+Backlog: %d rows", len(ces_ab))

    def is_blank_token(x):
        if pd.isna(x):
            return True
        s = str(x).strip()
        return s == "" or s.lower() == "none"

    ces_ab["has_token"] = ~ces_ab["OLMJobCode"].apply(is_blank_token)
    ces_ab["division"] = ces_ab["ItemCode"].map(item_division)
    n_no_division = ces_ab["division"].isna().sum()
    if n_no_division:
        logger.warning("%d rows have an ItemCode not found in the 351-item scope map -- dropped",
                        n_no_division)
    ces_ab = ces_ab.dropna(subset=["division"])

    usable = ces_ab[ces_ab["has_token"] & ces_ab["CtrDate"].notna()].copy()
    logger.info("Usable (non-blank OLMJobCode, non-null CtrDate): %d of %d Actual+Backlog rows",
                len(usable), len(ces_ab))

    # --- Token -> item consistency check (two-direction-ish sanity check on the batch-token
    # concept itself: does a token in THIS scope ever span more than one itemcode?) ---
    token_item_counts = usable.groupby("OLMJobCode")["ItemCode"].nunique()
    n_multi_item_tokens = int((token_item_counts > 1).sum())
    logger.info("Tokens spanning >1 itemcode within this scope: %d of %d distinct tokens (%.2f%%)",
                n_multi_item_tokens, len(token_item_counts),
                100 * n_multi_item_tokens / len(token_item_counts) if len(token_item_counts) else 0)

    # --- Per-token batch summary: first appearance date = proxy "batch became available" date ---
    token_summary = (
        usable.groupby("OLMJobCode")
        .agg(
            itemcode=("ItemCode", lambda x: x.mode().iat[0] if not x.mode().empty else x.iloc[0]),
            n_distinct_itemcodes=("ItemCode", "nunique"),
            n_distinct_contracts=("ContractID", "nunique"),
            first_ctrdate=("CtrDate", "min"),
            last_ctrdate=("CtrDate", "max"),
            n_rows=("ContractID", "size"),
        )
        .reset_index()
    )
    token_summary["division"] = token_summary["itemcode"].map(item_division)
    token_summary["span_days"] = (token_summary["last_ctrdate"] - token_summary["first_ctrdate"]).dt.days
    token_summary["serves_multi_contract"] = token_summary["n_distinct_contracts"] > 1
    token_summary.to_csv(OUT_TOKEN_TABLE, index=False)

    n_tokens = len(token_summary)
    n_multi = int(token_summary["serves_multi_contract"].sum())
    logger.info("Distinct usable tokens: %d; serve >1 contract: %d (%.1f%%) -- Phase J2 reported "
                "8,032 tokens / 1,108 (13.8%%) for comparison", n_tokens, n_multi,
                100 * n_multi / n_tokens if n_tokens else 0)
    if n_multi:
        span = token_summary.loc[token_summary["serves_multi_contract"], "span_days"]
        logger.info("Multi-contract token span_days: median=%.1f mean=%.1f max=%.1f -- Phase J2 "
                    "reported median 32, mean 72.9, max 1157 for comparison",
                    span.median(), span.mean(), span.max())

    # --- Cadence proxy: per item, sort distinct tokens by first_ctrdate, take gaps between
    # consecutive tokens' first appearance as the observed inter-batch interval. This is a PROXY
    # (token-first-use date, not a true production-start/availability date -- cube_final could not
    # supply that this session, see module docstring) for METRICS.md Sec.20's "effective review
    # interval" candidate. ---
    cadence_rows = []
    for item, g in token_summary.groupby("itemcode"):
        g = g.sort_values("first_ctrdate")
        if len(g) < 2:
            continue
        gaps = g["first_ctrdate"].diff().dt.days.dropna().values
        cadence_rows.append(dict(itemcode=item, division=item_division.get(item), **dist_stats(gaps),
                                  n_distinct_batches=len(g)))
    cadence_item_df = pd.DataFrame(cadence_rows)
    cadence_item_df.to_csv(OUT_CADENCE_ITEM, index=False)
    logger.info("Cadence proxy computed for %d items (>=2 distinct batch tokens)", len(cadence_item_df))

    # Per-division: pool ALL inter-batch gaps across the division's items (not the per-item medians)
    division_cadence_rows = []
    for division, g in token_summary.groupby("division"):
        all_gaps = []
        for item, gi in g.groupby("itemcode"):
            gi = gi.sort_values("first_ctrdate")
            if len(gi) < 2:
                continue
            all_gaps.extend(gi["first_ctrdate"].diff().dt.days.dropna().values)
        division_cadence_rows.append(dict(division=division, **dist_stats(all_gaps),
                                           n_items_with_ge2_batches=g.groupby("itemcode").size().gt(1).sum()
                                           if not g.empty else 0))
    cadence_division_df = pd.DataFrame(division_cadence_rows)
    cadence_division_df.to_csv(OUT_CADENCE_DIVISION, index=False)
    logger.info("Cadence proxy per division:\n%s", cadence_division_df.to_string())

    # --- Reverse-direction traceability + lag (task step 3) ---
    # Restrict to delivered contract-item rows (Status='Actual'). For each such row, ask: does its
    # OLMJobCode token's EARLIEST known appearance (across Actual+Backlog, this scope) predate this
    # row's own CtrDate? Explicit proxy limitation (same as Phase J2): earliest-contract-date is a
    # stand-in for "batch existed," not an independent production date.
    actual = ces_ab[ces_ab["Status"] == "Actual"].copy()
    n_actual = len(actual)
    token_first = token_summary.set_index("OLMJobCode")["first_ctrdate"]

    def classify(row):
        tok = row["OLMJobCode"]
        if is_blank_token(tok) or pd.isna(row["CtrDate"]):
            return "no_token"
        first = token_first.get(tok, pd.NaT)
        if pd.isna(first):
            return "no_token"
        if first < row["CtrDate"]:
            return "traceable_pre_existing"
        elif first == row["CtrDate"]:
            return "earliest_occurrence"
        else:
            # token's recorded earliest date is AFTER this row's own CtrDate -- can happen if this
            # row itself has a null/blank CtrDate elsewhere in a Backlog-only appearance; should be
            # rare/zero given first_ctrdate is a min over the same pool including this row.
            return "earliest_occurrence"

    actual["trace_class"] = actual.apply(classify, axis=1)
    actual["lag_days"] = np.where(
        actual["trace_class"] == "traceable_pre_existing",
        (actual["CtrDate"] - actual["OLMJobCode"].map(token_first)).dt.days,
        np.nan,
    )

    overall_counts = actual["trace_class"].value_counts()
    overall_share = (overall_counts / n_actual * 100).round(2)
    overall_df = pd.DataFrame({"n": overall_counts, "share_pct": overall_share})
    overall_df.to_csv(OUT_REVERSE_OVERALL)
    logger.info("Reverse-direction traceability (n=%d delivered/Actual rows):\n%s", n_actual,
                overall_df.to_string())

    division_group = actual.groupby("division")["trace_class"].value_counts(normalize=True).unstack().fillna(0) * 100
    division_group["n_rows"] = actual.groupby("division").size()
    division_group.to_csv(OUT_REVERSE_DIVISION)
    logger.info("Reverse-direction traceability per division (%%):\n%s", division_group.to_string())

    lag_overall = dist_stats(actual.loc[actual["trace_class"] == "traceable_pre_existing", "lag_days"])
    lag_by_division = {}
    for division, g in actual[actual["trace_class"] == "traceable_pre_existing"].groupby("division"):
        lag_by_division[division] = dist_stats(g["lag_days"])
    lag_df = pd.DataFrame(lag_by_division).T
    lag_df.loc["ALL"] = pd.Series(lag_overall)
    lag_df.to_csv(OUT_LAG_DIST)
    logger.info("Lag (days, batch-availability-proxy to PO date) for the traceable share:\n%s",
                lag_df.to_string())

    # --- Legacy cube_final illustrative check (39 stale rows, 4 items, 2026-08-31; NOT this
    # session's own pull -- clearly labelled, not generalised beyond these 4 items) ---
    if os.path.exists(TASK2_FILE):
        legacy = pd.read_csv(TASK2_FILE, parse_dates=["final_date"])
        sales = pd.read_csv(SALES_FILE, parse_dates=["createDate"])
        ces_main = pd.read_csv(os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv"),
                                parse_dates=["CtrDate"])
        # Join legacy cube_final rows to their contract's own PO date via ctrno<->contractid.
        po_from_sales = sales.groupby("contractid")["createDate"].min()
        po_from_ces = ces_main.groupby("ContractID")["CtrDate"].min()
        legacy["po_date_sales"] = legacy["ctrno"].map(po_from_sales)
        legacy["po_date_ces"] = legacy["ctrno"].map(po_from_ces)
        legacy["po_date_best"] = legacy["po_date_sales"].fillna(legacy["po_date_ces"])
        legacy["lag_final_to_po_days"] = (legacy["po_date_best"] - legacy["final_date"]).dt.days
        legacy.to_csv(OUT_LEGACY_ILLUSTRATIVE, index=False)
        matched = legacy["po_date_best"].notna().sum()
        logger.info("Legacy 39-row illustrative check: %d of %d rows matched a PO date via ctrno; "
                    "lag (final_date to PO date, days) stats where matched: %s",
                    matched, len(legacy),
                    dist_stats(legacy["lag_final_to_po_days"]))
    else:
        logger.warning("Legacy task2 file not found -- skipping illustrative check")

    print("ANALYSIS DONE")


if __name__ == "__main__":
    main()
