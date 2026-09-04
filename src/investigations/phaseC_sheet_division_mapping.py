"""Phase C — sheet-to-division mapping investigation (Explorer role, AGENTS.md).

Tests, directly against cube_Sale_APD, whether "pricelist sheet name" is a safe stand-in for
the database `division` column when scoping Phase C's per-division forecasting work. Phase C
step 1's five parallel Validators each assumed sheet == division for their own division and
found real problems with that assumption at the edges (PEM102/PEM107 legacy "-OLD" tag
swap, CI101/PEM101 split) — this script runs ONE consistent, Omni-Channel-scoped method across
ALL SIX visible pricelist sheets, so the results are directly comparable, instead of reusing the
five Validators' methodologically-inconsistent CSVs (see STATUS.md Phase C step 1 and
output/summary/phaseC_synthesis_report.md, sections 2/6, for why those are not reused here).

Scope filter applied throughout: revenue_type = 'Omni Channel' AND status IN ('Actual','MPS').
This is this project's established Omni-Channel scope convention (STATUS.md Locked Decisions,
"All queries filter on division='PEM101' and revenue_type='Omni Channel'" and Phase C step 1's
CI101/PEM103 findings, which both use this same status/revenue_type combination) — applied here
so this investigation's numbers are comparable to every other Omni-Channel-scoped figure already
recorded in STATUS.md. `division` is deliberately NOT filtered (left free) so every division a
sheet's codes actually appear under can be seen — that is the entire point of this script.

Per AGENTS.md's Explorer role: reports what the query returns, not why any mismatch exists.

Writes CSVs to output/summary/, prefixed phaseC_sheetmap_ (distinct from the phaseC_<DIV>_*
files the five Phase C step-1 Validators already wrote, and from the phaseC_validator_*.py
scripts already in this folder, which this script does not modify).
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("phaseC_sheetmap")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PRICELIST_PATH = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")
os.makedirs(SUMMARY_DIR, exist_ok=True)

SOURCE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"

# Omni-Channel scope filter, per STATUS.md's established convention (see module docstring).
REVENUE_TYPE_FILTER = "Omni Channel"
STATUS_FILTER = ("Actual", "MPS")

# Cleanliness threshold for "is sheet a safe stand-in for division": the % of a sheet's total
# in-scope (Omni Channel, Actual/MPS) sale value that must fall under that sheet's own home
# division for the sheet to be usable as the grouping key without falling back to `division`.
# Set at 95% — a round, defensible cut chosen to sit clearly ABOVE the noise band (a handful of
# stray rows or a small documented cross-division exclusion, the kind PEM101 itself has: 0.42%
# excluded per STATUS.md Locked Decisions, i.e. 99.58% clean) and clearly BELOW the two known
# structural problems this investigation exists to catch (CI101's prior-reported 37.2% split and
# PEM102/PEM107's near-total legacy-tag swap) — so a sheet only fails this test for the kind of
# large, structural mismatch already documented, not for ordinary small-value noise.
SHEET_CLEAN_THRESHOLD_PCT = 95.0

# Expected ("home") division per visible pricelist sheet, per this task's brief and confirmed
# below (Step 0) against the pricelist's own "business" column rather than hardcoded blindly.
EXPECTED_HOME_DIVISION = {
    "PEM101-Version 2": "PEM101",
    "PEM102-Version 2": "PEM102",
    "PEM103-Version2": "PEM103",
    "PEM104": "PEM104",
    "PEM107 CT-Version 2": "PEM107",
    "CI101": "CI101",
}


def out(name: str) -> str:
    return os.path.join(SUMMARY_DIR, f"phaseC_sheetmap_{name}")


def sql_list(values) -> str:
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def load_pricelist_scope() -> pd.DataFrame:
    """Load visible-sheet pricelist rows, dedupe to one row per (sheet, code), and confirm the
    sheet -> home-division mapping against the pricelist's own 'business' column.

    Returns a DataFrame with columns: sheet, code, home_division (one row per distinct code).
    """
    pl = load_visible_product_rows(PRICELIST_PATH)
    n_raw = len(pl)

    dup_mask = pl.duplicated(subset=["sheet", "code"], keep="first")
    n_dupes = int(dup_mask.sum())
    if n_dupes:
        dupe_codes = pl.loc[pl.duplicated(subset=["sheet", "code"], keep=False), ["sheet", "code"]]
        logger.info(
            "Dropping %d within-sheet duplicate pricelist row(s) (same sheet+code appears "
            "more than once): %s",
            n_dupes, dupe_codes.drop_duplicates().to_dict("records"),
        )
    pl = pl.loc[~dup_mask].copy()

    n_multi_sheet = int((pl.groupby("code")["sheet"].nunique() > 1).sum())
    if n_multi_sheet:
        raise RuntimeError(
            f"{n_multi_sheet} code(s) appear on more than one visible sheet — the per-code "
            "sheet mapping this script relies on is not 1:1. Stopping (never-guess rule)."
        )
    logger.info("Confirmed: no item code appears on more than one visible sheet (checked directly).")

    derived_home = pl.groupby("sheet")["business"].unique().apply(
        lambda arr: arr[0] if len(arr) == 1 else None
    )
    mismatches = []
    for sheet, expected in EXPECTED_HOME_DIVISION.items():
        actual = derived_home.get(sheet)
        if actual != expected:
            mismatches.append((sheet, expected, actual))
    if mismatches:
        raise RuntimeError(
            f"Sheet -> home-division mapping mismatch between task brief and pricelist "
            f"'business' column, stopping (never-guess rule): {mismatches}"
        )
    logger.info(
        "Confirmed: pricelist 'business' column matches the task's stated sheet->home-division "
        "mapping exactly for all %d sheets: %s", len(EXPECTED_HOME_DIVISION), EXPECTED_HOME_DIVISION,
    )

    scope = pl[["sheet", "code"]].copy()
    scope["home_division"] = scope["sheet"].map(EXPECTED_HOME_DIVISION)
    logger.info(
        "Pricelist scope: %d raw product rows read, %d duplicate row(s) dropped, "
        "%d distinct (sheet, code) rows retained across %d sheets.",
        n_raw, n_dupes, len(scope), scope["sheet"].nunique(),
    )
    return scope


def query_item_division_breakdown(codes: list) -> pd.DataFrame:
    """Per itemcode x division: row count, sum(sale), sum(qty), under the Omni Channel /
    Actual+MPS scope, division left unfiltered so the full spread is visible."""
    status_list = sql_list(STATUS_FILTER)
    codes_list = sql_list(codes)
    q = f"""
    SELECT itemcode, division, COUNT(*) AS n_rows, SUM(sale) AS sum_sale, SUM(qty) AS sum_qty
    FROM {SOURCE_TABLE}
    WHERE itemcode IN ({codes_list})
      AND revenue_type = '{REVENUE_TYPE_FILTER}'
      AND status IN ({status_list})
    GROUP BY itemcode, division
    ORDER BY itemcode, sum_sale DESC
    """
    logger.info(
        "Running per-itemcode x division query: %d distinct item codes, revenue_type=%r, "
        "status IN %s, division unfiltered.", len(codes), REVENUE_TYPE_FILTER, STATUS_FILTER,
    )
    df = run_query(q)
    logger.info("Query returned %d (itemcode, division) rows.", len(df))
    return df


def main():
    scope = load_pricelist_scope()
    scope.to_csv(out("00_pricelist_scope.csv"), index=False)

    all_codes = sorted(scope["code"].unique().tolist())
    logger.info("Total distinct item codes across all 6 visible sheets: %d", len(all_codes))

    div_df = query_item_division_breakdown(all_codes)
    div_df.to_csv(out("01_raw_itemcode_division_query.csv"), index=False)

    # ---- Step 1: per-item x division, with sheet/home_division context ----
    per_item = scope.merge(div_df, left_on="code", right_on="itemcode", how="left")
    codes_with_no_rows_at_all = per_item.loc[per_item["division"].isna(), "code"].unique()
    per_item = per_item.dropna(subset=["division"]).copy()
    per_item["n_rows"] = per_item["n_rows"].astype(int)
    per_item["is_home_division"] = per_item["division"] == per_item["home_division"]
    per_item = per_item[["sheet", "code", "home_division", "division", "is_home_division",
                          "n_rows", "sum_sale", "sum_qty"]].sort_values(["sheet", "code", "division"])
    per_item.to_csv(out("per_item_division.csv"), index=False)
    logger.info(
        "Step 1 (per item x division) written: %d rows covering %d distinct codes with at "
        "least one Omni-Channel row somewhere; %d codes had zero rows in this scope under any "
        "division.", len(per_item), per_item["code"].nunique(), len(codes_with_no_rows_at_all),
    )

    # ---- Step 2: per-sheet x division breakdown + home-vs-other summary ----
    sheet_div = per_item.groupby(["sheet", "home_division", "division"], as_index=False).agg(
        n_rows=("n_rows", "sum"), sum_sale=("sum_sale", "sum"), sum_qty=("sum_qty", "sum"),
    )
    sheet_totals = sheet_div.groupby("sheet")["sum_sale"].sum().rename("sheet_total_sale")
    sheet_div = sheet_div.merge(sheet_totals, on="sheet")
    sheet_div["pct_of_sheet_value"] = (
        sheet_div["sum_sale"] / sheet_div["sheet_total_sale"] * 100
    ).where(sheet_div["sheet_total_sale"] != 0, 0.0)
    sheet_div = sheet_div.sort_values(["sheet", "sum_sale"], ascending=[True, False])
    sheet_div.to_csv(out("per_sheet_division_breakdown.csv"), index=False)

    n_codes_per_sheet = scope.groupby("sheet")["code"].nunique()
    n_codes_no_history_per_sheet = (
        scope[scope["code"].isin(codes_with_no_rows_at_all)].groupby("sheet")["code"].nunique()
    )

    summary_rows = []
    for sheet, home_division in EXPECTED_HOME_DIVISION.items():
        sub = sheet_div[sheet_div["sheet"] == sheet]
        total_sale = float(sub["sheet_total_sale"].iloc[0]) if len(sub) else 0.0
        home_sale = float(sub.loc[sub["division"] == home_division, "sum_sale"].sum())
        other_sale = total_sale - home_sale
        home_pct = (home_sale / total_sale * 100) if total_sale else None
        n_codes = int(n_codes_per_sheet.get(sheet, 0))
        n_no_hist = int(n_codes_no_history_per_sheet.get(sheet, 0))
        other_divisions = sorted(
            sub.loc[(sub["division"] != home_division) & (sub["sum_sale"] != 0), "division"].tolist()
        )
        if total_sale == 0:
            verdict = "UNDETERMINED (zero Omni-Channel value found for this sheet at all)"
        elif home_pct >= SHEET_CLEAN_THRESHOLD_PCT:
            verdict = f"CLEAN (home_pct {home_pct:.2f}% >= {SHEET_CLEAN_THRESHOLD_PCT}% threshold)"
        else:
            verdict = f"NOT CLEAN (home_pct {home_pct:.2f}% < {SHEET_CLEAN_THRESHOLD_PCT}% threshold)"
        summary_rows.append({
            "sheet": sheet, "home_division": home_division, "n_codes": n_codes,
            "n_codes_no_history": n_no_hist,
            "sheet_total_omni_sale": total_sale, "home_division_sale": home_sale,
            "other_division_sale": other_sale, "home_pct_of_sheet_value": home_pct,
            "other_divisions_present": ", ".join(other_divisions) if other_divisions else "",
            "verdict": verdict,
        })
    per_sheet_summary = pd.DataFrame(summary_rows)
    per_sheet_summary.to_csv(out("per_sheet_summary.csv"), index=False)
    logger.info("Step 2/4 (per-sheet summary + clean/not-clean verdict) written:\n%s",
                per_sheet_summary.to_string())

    # ---- Step 3: flags ----
    # (a) codes under more than one division
    n_div_per_code = per_item.groupby("code")["division"].nunique()
    multi_div_codes = n_div_per_code[n_div_per_code > 1].index.tolist()
    flagged_multi = per_item[per_item["code"].isin(multi_div_codes)].sort_values(["code", "division"])
    flagged_multi.to_csv(out("flagged_multi_division.csv"), index=False)
    logger.info("Flag (a): %d code(s) appear under more than one division.", len(multi_div_codes))

    # (b) codes with zero rows under home division but rows under some other division
    home_rows = per_item[per_item["is_home_division"]].set_index("code")["n_rows"]
    codes_with_any_rows = set(per_item["code"].unique())
    codes_with_home_rows = set(home_rows[home_rows > 0].index)
    wrong_div_only_codes = sorted(codes_with_any_rows - codes_with_home_rows)
    flagged_wrong = per_item[per_item["code"].isin(wrong_div_only_codes)].sort_values(["code", "division"])
    flagged_wrong.to_csv(out("flagged_wrong_division.csv"), index=False)
    logger.info(
        "Flag (b): %d code(s) have zero Omni-Channel rows under their own sheet's home "
        "division, but rows exist under a different division.", len(wrong_div_only_codes),
    )

    # (c) codes with no division at all (zero Omni-Channel rows anywhere)
    flagged_no_div = scope[scope["code"].isin(codes_with_no_rows_at_all)].sort_values(["sheet", "code"])
    flagged_no_div.to_csv(out("flagged_no_division.csv"), index=False)
    logger.info(
        "Flag (c): %d code(s) have zero Omni-Channel (Actual/MPS) rows under ANY division.",
        len(flagged_no_div),
    )

    # ---- Step 5: CI101 detail ----
    ci_codes = scope.loc[scope["sheet"] == "CI101", "code"].unique().tolist()
    ci_detail = per_item[per_item["code"].isin(ci_codes)].copy()
    ci_detail.to_csv(out("CI101_detail.csv"), index=False)

    ci_ci101_sale = float(ci_detail.loc[ci_detail["division"] == "CI101", "sum_sale"].sum())
    ci_pem101_sale = float(ci_detail.loc[ci_detail["division"] == "PEM101", "sum_sale"].sum())
    ci_combined = ci_ci101_sale + ci_pem101_sale
    ci_pem101_pct_of_combined = (ci_pem101_sale / ci_combined * 100) if ci_combined else None
    logger.info(
        "CI101 re-derivation: CI101-tagged sale=%.2f, PEM101-tagged sale (CI101 codes)=%.2f, "
        "combined=%.2f, PEM101 share of combined=%s%%",
        ci_ci101_sale, ci_pem101_sale, ci_combined,
        f"{ci_pem101_pct_of_combined:.2f}" if ci_pem101_pct_of_combined is not None else "N/A",
    )
    ci_summary = pd.DataFrame([{
        "n_ci101_codes": len(ci_codes),
        "ci101_tagged_sale": ci_ci101_sale,
        "pem101_tagged_sale": ci_pem101_sale,
        "combined_ci101_plus_pem101_sale": ci_combined,
        "pem101_pct_of_combined": ci_pem101_pct_of_combined,
        "prior_reported_pct_phaseC_synthesis": 37.2,
    }])
    ci_summary.to_csv(out("CI101_pem101_split_summary.csv"), index=False)

    logger.info("=== DONE. All phaseC_sheetmap_* CSVs written to %s ===", SUMMARY_DIR)
    return {
        "per_item": per_item,
        "per_sheet_summary": per_sheet_summary,
        "multi_div_codes": multi_div_codes,
        "wrong_div_only_codes": wrong_div_only_codes,
        "no_div_codes": sorted(codes_with_no_rows_at_all),
        "ci_summary": ci_summary,
    }


if __name__ == "__main__":
    main()
