"""Phase J2, Explorer A -- Hypothesis A: real customer notice is longer than the 6-day
createDate-to-forecast_date gap because customers issue a quotation/enquiry well before the
formal PO.

Tests the join between Cube_Quotation and cube_Sale_APD, in BOTH directions (PO->quotation and
quotation->PO, per CONVENTIONS.md's two-direction rule for any absence/relationship claim).

Scope: PEM101 (128) + PEM103 (87) + PEM107 (136) = 351 items, from
output/data/phaseI_combined_scope_351items.csv (no DB access needed for scope -- pricelist-derived,
per CONVENTIONS.md's division source-of-truth rule). createDate >= 2024-01-01, revenue_type =
'Omni Channel', status IN ('Actual','MPS') -- same filters this project uses throughout
(config/config.yaml, src/phaseI_sensitivity_engine.py line ~115).

DATABASE ACCESS RULE: ONE connection attempt for this entire task. get_connection() is called
once; every SELECT below runs over that same open connection. On failure: stop, report, no retry.

Known going in (to be VERIFIED, not trusted): Cube_Quotation has itemcode, ctr_leadtime,
report_date (investigate_leadtime_classification.py); cube_Sale_APD has quotationid
(audit_pilot_items.py), which stores the literal 4-char string "None" as a missing-value
placeholder on many rows (STATUS.md line ~1347) -- must be excluded explicitly, IS NOT NULL alone
is not sufficient.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ2_explorerA")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")


def sql_in_list(values):
    return "','".join(sorted(str(v) for v in values))


def main():
    scope = pd.read_csv(SCOPE_FILE)
    assert set(scope["division"].unique()) == {"PEM101", "PEM103", "PEM107"}, scope["division"].unique()
    codes = sorted(scope["code"].unique())
    assert len(codes) == 351
    code_to_div = dict(zip(scope["code"], scope["division"]))
    code_list = sql_in_list(codes)

    logger.info("DATABASE ACCESS RULE: opening the SINGLE connection attempt for this entire "
                "task now (%d codes). No retry on failure.", len(codes))
    try:
        engine = get_connection()
        with engine.connect() as conn:
            # ---- 1. Schema verification: full column list of both tables ----
            quo_cols = pd.read_sql(
                "SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME='Cube_Quotation' ORDER BY ORDINAL_POSITION", conn)
            sale_cols = pd.read_sql(
                "SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME='cube_Sale_APD' ORDER BY ORDINAL_POSITION", conn)
            quo_sample = pd.read_sql("SELECT TOP 5 * FROM Cube_Quotation", conn)

            # ---- 2. Full Cube_Quotation pull, scoped to our 351 itemcodes, ALL columns ----
            quo = pd.read_sql(f"SELECT * FROM Cube_Quotation WHERE itemcode IN ('{code_list}')", conn)

            # ---- 3. cube_Sale_APD pull, scoped exactly as this project's demand series ----
            sales = pd.read_sql(
                "SELECT itemcode, quotationid, contractid, createDate, forecast_date, status, "
                "revenue_type, division AS division_db_raw, qty, sale "
                "FROM cube_Sale_APD "
                f"WHERE itemcode IN ('{code_list}') "
                "AND revenue_type = 'Omni Channel' "
                "AND status IN ('Actual','MPS') "
                "AND createDate >= '2024-01-01'",
                conn,
            )
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: the single connection attempt failed -- STOPPING, "
                      "not retrying. Error: %r", exc)
        raise

    logger.info("Pulled: Cube_Quotation schema=%d cols, cube_Sale_APD schema=%d cols, "
                "Cube_Quotation rows=%d, cube_Sale_APD scoped rows=%d",
                len(quo_cols), len(sale_cols), len(quo), len(sales))

    quo_cols.to_csv(os.path.join(DATA_DIR, "phaseJ2_explorerA_cube_quotation_schema.csv"), index=False)
    sale_cols.to_csv(os.path.join(DATA_DIR, "phaseJ2_explorerA_cube_sale_apd_schema.csv"), index=False)
    quo_sample.to_csv(os.path.join(DATA_DIR, "phaseJ2_explorerA_cube_quotation_sample.csv"), index=False)
    quo.to_csv(os.path.join(DATA_DIR, "phaseJ2_explorerA_cube_quotation_raw_351items.csv"), index=False)
    sales.to_csv(os.path.join(DATA_DIR, "phaseJ2_explorerA_cube_sale_apd_raw_351items.csv"), index=False)

    print("\n" + "=" * 90)
    print("STEP 1: Cube_Quotation FULL SCHEMA (verified via INFORMATION_SCHEMA.COLUMNS)")
    print("=" * 90)
    print(quo_cols.to_string(index=False))
    print("\nSample rows (TOP 5, unfiltered):")
    print(quo_sample.to_string(index=False))

    print("\n" + "=" * 90)
    print("STEP 1b: cube_Sale_APD FULL SCHEMA")
    print("=" * 90)
    print(sale_cols.to_string(index=False))

    # ---- Data-driven join-key discovery ----
    # Clean the known "None"-as-string placeholder in cube_Sale_APD.quotationid.
    sales["quotationid_clean"] = sales["quotationid"].astype(str).str.strip()
    sales["has_quotationid"] = (~sales["quotationid_clean"].isin(["None", "none", "NONE", "", "nan", "NaN"])) & sales["quotationid"].notna()
    n_total_rows = len(sales)
    n_with_qid = int(sales["has_quotationid"].sum())
    print("\n" + "=" * 90)
    print("STEP 4 (report item 4 first -- feeds everything else): SHARE OF POs WITH A quotationid AT ALL")
    print("=" * 90)
    print(f"cube_Sale_APD scoped rows (351 items, 2024+, Omni Channel, Actual/MPS): {n_total_rows}")
    print(f"Rows with a non-null, non-'None' quotationid: {n_with_qid} ({100*n_with_qid/n_total_rows:.2f}%)")
    print(f"Distinct non-null quotationid values: {sales.loc[sales['has_quotationid'], 'quotationid_clean'].nunique()}")

    qid_values = set(sales.loc[sales["has_quotationid"], "quotationid_clean"].unique())
    print("\n" + "=" * 90)
    print("STEP 2 continued: DATA-DRIVEN JOIN-KEY DISCOVERY")
    print("(testing every Cube_Quotation column for overlap against cube_Sale_APD.quotationid values, "
          "rather than assuming a name)")
    print("=" * 90)
    overlap_report = []
    for col in quo.columns:
        try:
            col_vals = set(quo[col].dropna().astype(str).str.strip().unique())
        except Exception:
            continue
        overlap = len(col_vals & qid_values)
        overlap_report.append({"column": col, "n_distinct_values": len(col_vals), "n_overlap_with_quotationid": overlap,
                                "overlap_pct_of_quotationid_values": round(100*overlap/max(len(qid_values), 1), 3)})
    overlap_df = pd.DataFrame(overlap_report).sort_values("n_overlap_with_quotationid", ascending=False)
    overlap_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_joinkey_discovery.csv"), index=False)
    print(overlap_df.to_string(index=False))

    best_col = overlap_df.iloc[0]["column"] if len(overlap_df) and overlap_df.iloc[0]["n_overlap_with_quotationid"] > 0 else None
    print(f"\n=> Best candidate join key in Cube_Quotation: {best_col!r} "
          f"({overlap_df.iloc[0]['n_overlap_with_quotationid'] if best_col else 0} of {len(qid_values)} "
          f"quotationid values found)" if best_col else "\n=> NO Cube_Quotation column overlaps with any "
          f"cube_Sale_APD.quotationid value at all (0 of {len(qid_values)}). CANNOT JOIN on quotationid.")

    # date columns present in Cube_Quotation (for both directions' date math)
    date_like_cols = [c for c in quo.columns if quo[c].dtype == object and quo[c].dropna().astype(str).str.match(r"^\d{4}-\d{2}-\d{2}").fillna(False).mean() > 0.5]
    for c in quo.columns:
        if c in date_like_cols:
            continue
        if np.issubdtype(quo[c].dtype, np.datetime64):
            date_like_cols.append(c)
    print(f"\nColumns in Cube_Quotation that look like dates (>50% ISO-date-like strings or datetime dtype): {date_like_cols}")

    results = {
        "n_total_scoped_rows": n_total_rows,
        "n_with_quotationid": n_with_qid,
        "pct_with_quotationid": round(100*n_with_qid/n_total_rows, 2),
        "n_distinct_quotationid_values": len(qid_values),
        "best_join_key_column": best_col,
        "cube_quotation_rows_351items": len(quo),
        "cube_quotation_distinct_itemcodes": quo["itemcode"].nunique() if "itemcode" in quo.columns else None,
    }

    if best_col is None:
        print("\nSTOPPING per instruction: no data-driven join key found between Cube_Quotation and "
              "cube_Sale_APD.quotationid. Cannot compute match rate, distributions, or reverse direction. "
              "Reporting this as CANNOT BE DETERMINED for the join itself.")
        pd.Series(results).to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_headline_results.csv"))
        return results, quo, sales, overlap_df, None, None

    quo["_joinkey"] = quo[best_col].astype(str).str.strip()

    # Are there duplicate itemcode+_joinkey rows in Cube_Quotation? (affects merge fan-out)
    dup_quo = quo.duplicated(subset=["itemcode", "_joinkey"]).sum()
    print(f"\nCube_Quotation duplicate (itemcode, {best_col}) rows: {dup_quo} of {len(quo)} "
          f"({100*dup_quo/len(quo):.2f}%) -- if >0, a merge will fan out; deduping to first row per "
          f"(itemcode,{best_col}) before date-distribution analysis (report_date, if it varies within a "
          f"group, is taken as the min).")

    # Reduce Cube_Quotation to one row per (itemcode, joinkey), taking the earliest report_date if
    # report_date is a genuine date column and multiple rows disagree.
    quo_dates = quo.copy()
    if "report_date" in quo_dates.columns:
        quo_dates["report_date"] = pd.to_datetime(quo_dates["report_date"], errors="coerce")
    agg_dict = {"report_date": "min"} if "report_date" in quo_dates.columns else {}
    for c in date_like_cols:
        if c == "report_date":
            continue
        quo_dates[c] = pd.to_datetime(quo_dates[c], errors="coerce")
        agg_dict[c] = "min"
    quo_dedup = quo_dates.groupby(["itemcode", "_joinkey"], as_index=False).agg(agg_dict) if agg_dict else \
        quo_dates.drop_duplicates(subset=["itemcode", "_joinkey"])[["itemcode", "_joinkey"]]

    # ---- STEP 2: JOIN MATCH RATE (PO -> quotation direction) ----
    print("\n" + "=" * 90)
    print("STEP 2: JOIN MATCH RATE (direction: cube_Sale_APD PO row -> Cube_Quotation)")
    print("=" * 90)
    sales["_joinkey"] = sales["quotationid_clean"]
    merged = sales.merge(quo_dedup, on=["itemcode", "_joinkey"], how="left", indicator=True,
                          suffixes=("", "_quo"))
    n_matched = int((merged["_merge"] == "both").sum())
    print(f"Of all {n_total_rows} scoped PO rows: {n_matched} ({100*n_matched/n_total_rows:.2f}%) join to a "
          f"Cube_Quotation row on (itemcode, {best_col}).")
    print(f"Of the {n_with_qid} rows that HAD a quotationid at all: {n_matched} ({100*n_matched/max(n_with_qid,1):.2f}%) "
          f"actually found a matching Cube_Quotation row (itemcode+id combination must both agree).")
    n_qid_no_match = n_with_qid - n_matched
    if n_qid_no_match > 0:
        print(f"NOTE: {n_qid_no_match} rows had a quotationid value but it did NOT match any Cube_Quotation "
              f"row for that item -- either the quotation predates/postdates this pull's item scope, the "
              f"quotation was for a different item on a multi-line quote, or the id spaces genuinely diverge.")

    results.update({
        "n_matched_rows": n_matched,
        "pct_matched_of_all_rows": round(100*n_matched/n_total_rows, 2),
        "pct_matched_of_rows_with_quotationid": round(100*n_matched/max(n_with_qid, 1), 2),
    })

    # ---- STEP 3: distributions for matched rows ----
    matched = merged[merged["_merge"] == "both"].copy()
    quote_date_col = "report_date" if "report_date" in matched.columns else (date_like_cols[0] if date_like_cols else None)
    print("\n" + "=" * 90)
    print(f"STEP 3: DISTRIBUTIONS for matched rows (quotation date column used: {quote_date_col!r})")
    print("=" * 90)
    dist_summary = {}
    if quote_date_col is not None:
        matched["createDate"] = pd.to_datetime(matched["createDate"])
        matched["forecast_date"] = pd.to_datetime(matched["forecast_date"], errors="coerce")
        matched[quote_date_col] = pd.to_datetime(matched[quote_date_col], errors="coerce")
        matched["quote_to_create_days"] = (matched["createDate"] - matched[quote_date_col]).dt.days
        matched["quote_to_forecast_days"] = (matched["forecast_date"] - matched[quote_date_col]).dt.days

        valid_a = matched["quote_to_create_days"].dropna()
        valid_b = matched["quote_to_forecast_days"].dropna()
        neg_a = (valid_a < 0).sum()
        neg_b = (valid_b < 0).sum()

        def dist(s):
            return {"n": int(s.count()), "min": s.min(), "p25": s.quantile(0.25), "median": s.median(),
                    "p75": s.quantile(0.75), "max": s.max(), "mean": round(s.mean(), 2),
                    "n_negative": int((s < 0).sum())}

        dist_a = dist(valid_a)
        dist_b = dist(valid_b)
        print(f"(a) quotation date -> createDate (days), n={dist_a['n']}: {dist_a}")
        print(f"    Rows where quote date is AFTER createDate (negative, quote issued after the PO -- "
              f"contradiction if hypothesis holds cleanly): {neg_a} ({100*neg_a/max(dist_a['n'],1):.2f}%)")
        print(f"(b) quotation date -> forecast_date (days), n={dist_b['n']}: {dist_b}")
        print(f"    Negative (quote after due date): {neg_b} ({100*neg_b/max(dist_b['n'],1):.2f}%)")

        bins = [-np.inf, 0, 6, 14, 30, 60, 90, 180, np.inf]
        labels = ["<0 (quote after PO)", "0-6d", "7-14d", "15-30d", "31-60d", "61-90d", "91-180d", ">180d"]
        hist_a = pd.cut(valid_a, bins=bins, labels=labels).value_counts().sort_index()
        hist_b = pd.cut(valid_b, bins=bins, labels=labels).value_counts().sort_index()
        print("\nHistogram, quote->createDate (a):")
        print(hist_a.to_string())
        print("\nHistogram, quote->forecast_date (b):")
        print(hist_b.to_string())

        dist_summary = {"quote_to_create": dist_a, "quote_to_forecast": dist_b}
        matched[["itemcode", "_joinkey", quote_date_col, "createDate", "forecast_date",
                 "quote_to_create_days", "quote_to_forecast_days"]].to_csv(
            os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_matched_rows_distributions.csv"), index=False)
        hist_a.to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_hist_quote_to_create.csv"))
        hist_b.to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_hist_quote_to_forecast.csv"))
    else:
        print("No usable date column found on the Cube_Quotation side -- CANNOT compute distributions.")

    # ---- STEP 5: REVERSE DIRECTION (quotation -> PO) ----
    print("\n" + "=" * 90)
    print("STEP 5: REVERSE DIRECTION -- from Cube_Quotation's side, conversion to a PO/contract")
    print("=" * 90)
    quo_dedup["_in_sales"] = quo_dedup.set_index(["itemcode", "_joinkey"]).index.isin(
        sales.set_index(["itemcode", "_joinkey"]).index)
    n_quo_total = len(quo_dedup)
    n_quo_converted = int(quo_dedup["_in_sales"].sum())
    print(f"Distinct Cube_Quotation (itemcode, {best_col}) combinations for these 351 items: {n_quo_total}")
    print(f"Of these, {n_quo_converted} ({100*n_quo_converted/max(n_quo_total,1):.2f}%) appear as a "
          f"quotationid on at least one cube_Sale_APD row in the 2024+/Omni/Actual+MPS scope.")
    print("NOTE: this is conversion INTO THE SAME SCOPE used above (2024+, Omni Channel, Actual/MPS) -- a "
          "quotation whose resulting order falls outside that scope (different revenue_type, status, or "
          "before 2024) will show as not-converted here even if it truly converted; this is a scope "
          "limitation of the check, not evidence the quotation never converted.")

    conv_days = None
    if quote_date_col is not None and n_quo_converted > 0:
        first_order_date = sales.groupby(["itemcode", "_joinkey"])["createDate"].min().rename("first_po_createDate")
        conv = quo_dedup.merge(first_order_date, on=["itemcode", "_joinkey"], how="inner")
        conv["report_date_dt"] = pd.to_datetime(conv[quote_date_col], errors="coerce")
        conv["first_po_createDate"] = pd.to_datetime(conv["first_po_createDate"])
        conv["conv_days"] = (conv["first_po_createDate"] - conv["report_date_dt"]).dt.days
        cd = conv["conv_days"].dropna()
        conv_days = {"n": int(cd.count()), "min": cd.min(), "p25": cd.quantile(0.25), "median": cd.median(),
                     "p75": cd.quantile(0.75), "max": cd.max(), "mean": round(cd.mean(), 2),
                     "n_negative": int((cd < 0).sum())}
        print(f"Time from quotation date to first matching PO createDate, n={conv_days['n']}: {conv_days}")
        conv[["itemcode", "_joinkey", quote_date_col, "first_po_createDate", "conv_days"]].to_csv(
            os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_reverse_conversion_days.csv"), index=False)

    quo_dedup.to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_quotation_conversion_summary.csv"), index=False)

    results.update({
        "n_distinct_quotations_351items": n_quo_total,
        "n_quotations_converted_within_scope": n_quo_converted,
        "pct_quotations_converted_within_scope": round(100*n_quo_converted/max(n_quo_total,1), 2),
    })
    if dist_summary:
        for k, v in dist_summary["quote_to_create"].items():
            results[f"quote_to_create_{k}"] = v
        for k, v in dist_summary["quote_to_forecast"].items():
            results[f"quote_to_forecast_{k}"] = v
    if conv_days:
        for k, v in conv_days.items():
            results[f"reverse_conv_days_{k}"] = v

    pd.Series(results).to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_headline_results.csv"))
    print("\n" + "=" * 90)
    print("HEADLINE RESULTS")
    print("=" * 90)
    print(pd.Series(results).to_string())

    return results, quo, sales, overlap_df, matched if quote_date_col else None, quo_dedup


if __name__ == "__main__":
    main()
