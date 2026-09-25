"""Phase 25 -- independent Validator (AGENTS.md Validator role), PEM107, Q10 branch.

Recomputes THREE figures from scratch, own queries and own logic, WITHOUT reading any
phase25_explorer1_/phase25_explorer2_/phase25_analyst3_/phase25_explorer4_ output file or script
(independent second-direction check per CONVENTIONS.md):

  1. Contract link rate (cube_Sale_APD jobcode / Cube_CES OLMJobCode -> cube_final jobno token
     match), by month, Sep-Dec 2024, Omni Channel vs Tendering, PEM107 scope.
  2. PEM107 Omni Channel not_late (METRICS.md Sec.19, unit-weighted), May-2025..Apr-2026 vs
     May-2026..latest.
  3. cube_final.division monthly distribution for the PEM107 itemcode scope, Jan-2025 onward,
     checking for a step around May 2026 and whether the same pattern recurs around May 2025.

Item scope: output/data/phaseI_combined_scope_351items.csv, rows where division == 'PEM107'
(136 codes) -- the pricelist-derived scope column. Per CONVENTIONS.md the database's OWN
`division` column (on cube_Sale_APD or cube_final) is reference-only, never a filter.

ONE database connection session for this entire script (three logical pulls: cube_Sale_APD,
cube_final, Cube_CES) -- if the connection fails, this script stops immediately, no retries.

No customer names / contract IDs / employee names are written to any output file. Contract IDs
are used only in memory (for the itemcode+contractid join between cube_Sale_APD and Cube_CES) and
never persisted; all saved CSVs are already aggregated above that grain.
"""
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import run_query
from cube_final_pull import pull_cube_final_for_items, CUBE_FINAL_COLUMNS
from cube_ces_pull import pull_cube_ces_for_items, CUBE_CES_COLUMNS
from zero_row_guard import guard_nonempty

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("phase25_validator")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCOPE_CSV = PROJECT_ROOT / "output" / "data" / "phaseI_combined_scope_351items.csv"
OUT_DIR = PROJECT_ROOT / "output" / "summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 0. Scope + pulls (one connection session)
# ---------------------------------------------------------------------------

def load_pem107_scope():
    scope = pd.read_csv(SCOPE_CSV)
    pem107 = scope[scope["division"] == "PEM107"]
    codes = sorted(pem107["code"].unique().tolist())
    logger.info("Loaded %d PEM107 codes from %s (pricelist-derived scope, 'division' column).",
                len(codes), SCOPE_CSV)
    return codes


def pull_sale_apd(item_codes):
    """Own query, no SQL-level date filter, per task instructions."""
    cols = ["itemcode", "contractid", "createDate", "forecast_date", "qty", "status",
            "division", "revenue_type", "jobcode"]
    code_list = "','".join(item_codes)
    col_list = ", ".join(cols)
    sql = f"""
        SELECT {col_list}
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE itemcode IN ('{code_list}')
    """
    df = run_query(sql)
    guard_nonempty(df, table="cube_Sale_APD", filter_desc=f"itemcode IN ({len(item_codes)} codes)")
    logger.info("Pulled %d cube_Sale_APD rows for %d PEM107 item codes.", len(df), len(item_codes))
    return df


def split_tokens(value):
    """Splits a comma-separated job-code/job-no string into a set of stripped, non-empty,
    upper-cased tokens. Safe on None/NaN (returns empty set)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    s = str(value)
    return {t.strip().upper() for t in s.split(",") if t.strip()}


def main():
    codes = load_pem107_scope()
    assert len(codes) == 136, f"Expected 136 PEM107 codes, got {len(codes)}"

    # --- ONE connection session, three pulls, no retries on failure ---
    sale_apd = pull_sale_apd(codes)
    cube_final = pull_cube_final_for_items(codes, columns=CUBE_FINAL_COLUMNS)
    cube_ces = pull_cube_ces_for_items(codes, columns=CUBE_CES_COLUMNS + ["OLMJobCode"])

    logger.info("Raw pulls: sale_apd=%d rows, cube_final=%d rows, cube_ces=%d rows.",
                len(sale_apd), len(cube_final), len(cube_ces))

    # Sanitized raw exports (no employee names, no contract/customer IDs) for independent review.
    drop_final = ["fg_check_name", "fg_final_name", "fg_pack_name", "ctrno", "customer_name"]
    cube_final.drop(columns=[c for c in drop_final if c in cube_final.columns]) \
        .to_csv(OUT_DIR / "phase25_validator_raw_cube_final.csv", index=False)
    drop_ces = ["ContractID", "CustomerID", "CustomerName"]
    cube_ces.drop(columns=[c for c in drop_ces if c in cube_ces.columns]) \
        .to_csv(OUT_DIR / "phase25_validator_raw_cube_ces.csv", index=False)
    # sale_apd raw is NOT exported (would require dropping contractid, which is still needed
    # in-memory below for the join) -- aggregated, contract-ID-free tables are exported per figure.

    figure1(sale_apd, cube_final, cube_ces)
    figure2(cube_ces)
    figure3(cube_final)


# ---------------------------------------------------------------------------
# Figure 1: link rate around the Sep-Dec 2024 boundary
# ---------------------------------------------------------------------------

def figure1(sale_apd, cube_final, cube_ces):
    logger.info("=== Figure 1: link rate, Sep-Dec 2024 ===")

    # cube_final jobno token population for this itemcode scope (defensive comma-split check).
    jobno_raw = cube_final["jobno"].dropna().astype(str)
    n_jobno_with_comma = jobno_raw.str.contains(",").sum()
    logger.info("cube_final.jobno: %d non-null values, %d contain a comma (checked, not assumed).",
                len(jobno_raw), n_jobno_with_comma)
    jobno_tokens = set()
    for v in jobno_raw:
        jobno_tokens |= split_tokens(v)
    logger.info("cube_final jobno token population size: %d distinct tokens.", len(jobno_tokens))

    # Verify whether Cube_CES.OLMJobCode is ever comma-separated (task explicitly requires this
    # check before assuming it's a single token).
    olm_raw = cube_ces["OLMJobCode"].dropna().astype(str)
    n_olm_with_comma = olm_raw.str.contains(",").sum()
    logger.info("Cube_CES.OLMJobCode: %d non-null values, %d contain a comma (checked).",
                len(olm_raw), n_olm_with_comma)

    # --- Aggregate cube_Sale_APD to the (contractid, itemcode) grain the task specifies ---
    sale_apd = sale_apd.copy()
    sale_apd["createDate"] = pd.to_datetime(sale_apd["createDate"], errors="coerce")
    n_rows_before = len(sale_apd)
    n_rows_no_contract = sale_apd["contractid"].isna().sum()
    if n_rows_no_contract:
        logger.warning("Dropping %d/%d cube_Sale_APD rows with null contractid before grain "
                        "aggregation.", n_rows_no_contract, n_rows_before)
    sale_apd = sale_apd.dropna(subset=["contractid"])

    # Check revenue_type consistency within a (contractid, itemcode) pair before grouping.
    rt_nunique = sale_apd.groupby(["contractid", "itemcode"])["revenue_type"].nunique()
    n_inconsistent_rt = int((rt_nunique > 1).sum())
    logger.info("(contractid, itemcode) pairs with >1 distinct revenue_type: %d of %d pairs "
                "(logged, not silently resolved).", n_inconsistent_rt, len(rt_nunique))

    pair_rows = []
    for (contractid, itemcode), g in sale_apd.groupby(["contractid", "itemcode"]):
        tokens = set()
        for v in g["jobcode"].dropna():
            tokens |= split_tokens(v)
        month = g["createDate"].min().to_period("M") if g["createDate"].notna().any() else pd.NaT
        rt_mode = g["revenue_type"].mode()
        pair_rows.append({
            "contractid": contractid, "itemcode": itemcode,
            "month": month,
            "revenue_type": rt_mode.iat[0] if not rt_mode.empty else None,
            "qty_total": g["qty"].sum(),
            "jobcode_tokens": tokens,
        })
    pairs = pd.DataFrame(pair_rows)
    logger.info("Aggregated to %d distinct (contractid, itemcode) pairs (grain per task spec).",
                len(pairs))

    # --- Cube_CES OLMJobCode tokens per (contractid, itemcode), for the OR-condition ---
    ces = cube_ces.dropna(subset=["ContractID"]).copy()
    ces_rows = []
    for (contractid, itemcode), g in ces.groupby(["ContractID", "ItemCode"]):
        tokens = set()
        for v in g["OLMJobCode"].dropna():
            tokens |= split_tokens(v)
        ces_rows.append({"contractid": contractid, "itemcode": itemcode, "olm_tokens": tokens})
    ces_tokens = pd.DataFrame(ces_rows)

    pairs = pairs.merge(ces_tokens, on=["contractid", "itemcode"], how="left")
    pairs["olm_tokens"] = pairs["olm_tokens"].apply(lambda x: x if isinstance(x, set) else set())

    pairs["linked_via_sale_apd"] = pairs["jobcode_tokens"].apply(lambda t: len(t & jobno_tokens) > 0)
    pairs["linked_via_ces"] = pairs["olm_tokens"].apply(lambda t: len(t & jobno_tokens) > 0)
    pairs["linked"] = pairs["linked_via_sale_apd"] | pairs["linked_via_ces"]

    window_months = [pd.Period("2024-09", "M"), pd.Period("2024-10", "M"),
                      pd.Period("2024-11", "M"), pd.Period("2024-12", "M")]
    window = pairs[pairs["month"].isin(window_months)].copy()
    logger.info("Contract+item pairs falling in Sep-Dec 2024 (by min createDate): %d of %d total pairs.",
                len(window), len(pairs))

    rt_norm = window["revenue_type"].fillna("UNKNOWN")
    window["revenue_type_norm"] = rt_norm

    rows = []
    for month in window_months:
        for rt in ["Omni Channel", "Tendering"]:
            g = window[(window["month"] == month) & (window["revenue_type_norm"] == rt)]
            n = len(g)
            n_linked = int(g["linked"].sum())
            qty_total = g["qty_total"].sum()
            qty_linked = g.loc[g["linked"], "qty_total"].sum()
            rows.append({
                "month": str(month), "revenue_type": rt,
                "n_contracts": n, "n_linked": n_linked,
                "link_rate_by_count_pct": round(100 * n_linked / n, 2) if n else None,
                "qty_total": qty_total, "qty_linked": qty_linked,
                "link_rate_by_qty_pct": round(100 * qty_linked / qty_total, 2) if qty_total else None,
            })
    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "phase25_validator_figure1_link_rate_by_month.csv", index=False)
    logger.info("Figure 1 result:\n%s", result.to_string(index=False))

    # Format-check note file
    with open(OUT_DIR / "phase25_validator_figure1_format_check.txt", "w") as f:
        f.write(f"cube_final.jobno non-null values: {len(jobno_raw)}\n")
        f.write(f"cube_final.jobno values containing a comma: {n_jobno_with_comma}\n")
        f.write(f"Cube_CES.OLMJobCode non-null values: {len(olm_raw)}\n")
        f.write(f"Cube_CES.OLMJobCode values containing a comma: {n_olm_with_comma}\n")
        f.write(f"(contractid, itemcode) pairs with >1 distinct revenue_type: {n_inconsistent_rt} "
                f"of {len(rt_nunique)}\n")
        f.write(f"cube_Sale_APD rows dropped for null contractid: {n_rows_no_contract} of {n_rows_before}\n")

    return result


# ---------------------------------------------------------------------------
# Figure 2: Omni Channel not_late, before/after May 2026
# ---------------------------------------------------------------------------

def figure2(cube_ces):
    logger.info("=== Figure 2: Omni Channel not_late, May2025-Apr2026 vs May2026-latest ===")

    df = cube_ces.copy()
    df["ForecastDelDate"] = pd.to_datetime(df["ForecastDelDate"], errors="coerce")
    df["ActualDelDate"] = pd.to_datetime(df["ActualDelDate"], errors="coerce")

    # METRICS.md Sec.19: not_late, unit-weighted (ActualQty), Status='Actual' only.
    n_before_status_filter = len(df)
    df = df[df["Status"] == "Actual"]
    df = df[df["RevenueType"] == "Omni Channel"]
    logger.info("After Status='Actual' + RevenueType='Omni Channel' filter: %d of %d rows.",
                len(df), n_before_status_filter)

    n_missing_forecast = df["ForecastDelDate"].isna().sum()
    n_missing_actual = df["ActualDelDate"].isna().sum()
    logger.info("Rows missing ForecastDelDate: %d; missing ActualDelDate: %d (both excluded).",
                n_missing_forecast, n_missing_actual)
    df = df.dropna(subset=["ForecastDelDate", "ActualDelDate"])

    df["month"] = df["ForecastDelDate"].dt.to_period("M")
    df["not_late"] = df["ActualDelDate"] <= df["ForecastDelDate"]
    df["ActualQty"] = pd.to_numeric(df["ActualQty"], errors="coerce").fillna(0)

    monthly = df.groupby("month").apply(
        lambda g: pd.Series({
            "n_rows": len(g),
            "qty_total": g["ActualQty"].sum(),
            "qty_not_late": g.loc[g["not_late"], "ActualQty"].sum(),
            "not_late_unit_weighted_pct": round(
                100 * g.loc[g["not_late"], "ActualQty"].sum() / g["ActualQty"].sum(), 2
            ) if g["ActualQty"].sum() else None,
        }), include_groups=False
    ).reset_index()
    monthly["month"] = monthly["month"].astype(str)
    monthly = monthly.sort_values("month")
    monthly.to_csv(OUT_DIR / "phase25_validator_figure2_not_late_monthly.csv", index=False)
    logger.info("Figure 2 monthly:\n%s", monthly.to_string(index=False))

    latest_month = df["month"].max()
    logger.info("Latest available ForecastDelDate month in PEM107 Omni Channel Actual data: %s",
                latest_month)

    p1 = df[(df["month"] >= pd.Period("2025-05", "M")) & (df["month"] <= pd.Period("2026-04", "M"))]
    p2 = df[(df["month"] >= pd.Period("2026-05", "M")) & (df["month"] <= latest_month)]

    def period_stats(g, label):
        qty_total = g["ActualQty"].sum()
        qty_not_late = g.loc[g["not_late"], "ActualQty"].sum()
        pct = round(100 * qty_not_late / qty_total, 2) if qty_total else None
        n = len(g)
        n_not_late = int(g["not_late"].sum())
        row_pct = round(100 * n_not_late / n, 2) if n else None
        logger.info("%s: n_rows=%d, qty_total=%s, qty_not_late=%s, not_late_unit_weighted_pct=%s, "
                    "not_late_row_weighted_pct=%s", label, n, qty_total, qty_not_late, pct, row_pct)
        return {"period": label, "n_rows": n, "qty_total": qty_total, "qty_not_late": qty_not_late,
                "not_late_unit_weighted_pct": pct, "not_late_row_weighted_pct": row_pct}

    period_result = pd.DataFrame([
        period_stats(p1, "2025-05_to_2026-04"),
        period_stats(p2, f"2026-05_to_{latest_month}"),
    ])
    period_result.to_csv(OUT_DIR / "phase25_validator_figure2_not_late_period.csv", index=False)
    logger.info("Figure 2 period result:\n%s", period_result.to_string(index=False))
    return monthly, period_result


# ---------------------------------------------------------------------------
# Figure 3: cube_final.division step change
# ---------------------------------------------------------------------------

def figure3(cube_final):
    logger.info("=== Figure 3: cube_final.division monthly distribution, Jan2025 onward ===")

    df = cube_final.copy()
    df["final_date"] = pd.to_datetime(df["final_date"], errors="coerce")
    n_missing = df["final_date"].isna().sum()
    logger.info("cube_final rows missing final_date: %d of %d (excluded from monthly bucketing).",
                n_missing, len(df))
    df = df.dropna(subset=["final_date"])
    df["month"] = df["final_date"].dt.to_period("M")
    df = df[df["month"] >= pd.Period("2025-01", "M")]

    dist = (
        df.groupby(["month", "division"]).size().rename("n").reset_index()
    )
    totals = df.groupby("month").size().rename("n_total").reset_index()
    dist = dist.merge(totals, on="month")
    dist["share_pct"] = round(100 * dist["n"] / dist["n_total"], 2)
    dist["month"] = dist["month"].astype(str)
    dist = dist.sort_values(["month", "n"], ascending=[True, False])
    dist.to_csv(OUT_DIR / "phase25_validator_figure3_division_monthly_distribution.csv", index=False)

    dominant = dist.sort_values(["month", "n"], ascending=[True, False]).groupby("month").first().reset_index()
    dominant = dominant[["month", "division", "n", "n_total", "share_pct"]].rename(
        columns={"division": "dominant_division"})
    dominant.to_csv(OUT_DIR / "phase25_validator_figure3_dominant_division_by_month.csv", index=False)
    logger.info("Figure 3 dominant division by month:\n%s", dominant.to_string(index=False))

    # Explicit check: does the dominant value change around May 2026? Around May 2025?
    dominant_sorted = dominant.sort_values("month").reset_index(drop=True)
    dominant_sorted["prev_dominant"] = dominant_sorted["dominant_division"].shift(1)
    dominant_sorted["changed_from_prev"] = (
        dominant_sorted["dominant_division"] != dominant_sorted["prev_dominant"]
    )
    changes = dominant_sorted[dominant_sorted["changed_from_prev"]]
    changes.to_csv(OUT_DIR / "phase25_validator_figure3_dominant_division_changes.csv", index=False)
    logger.info("Months where the dominant cube_final.division changed from the prior month:\n%s",
                changes.to_string(index=False))

    return dist, dominant, changes


if __name__ == "__main__":
    main()
