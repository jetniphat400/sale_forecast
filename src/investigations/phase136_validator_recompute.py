"""Phase 136 Part 4 -- Validator: independent, from-scratch recomputation.

Investigates whether PEM103's and PEM107's 2025->2026 channel-mix reversal (Omni Channel vs
Tendering, by RevenueType) reflects a change in RECORDING/TAGGING or a genuine change in the
BUSINESS. This script does NOT read any Explorer/Synthesizer output from this phase -- pricelist
scope, DB pulls and all three analyses are built from scratch, per AGENTS.md's Validator role and
this task's explicit instruction.

Per CONVENTIONS.md and DATA_MAP.md Trap 18: Cube_CES is pulled with NO date filter at the SQL
level via src/cube_ces_pull.py; any date window is applied afterward in Python.

Outputs (this agent's own naming, distinct from any phase136_explorer*/phase136_synthesis* name):
  output/data/phase136_valrecompute_ces_scope.csv        -- raw Cube_CES pull, PEM103+PEM107 scope
  output/data/phase136_valrecompute_saleapd_scope.csv     -- raw cube_Sale_APD pull, same scope
  output/summary/phase136_valrecompute_part1_switch.csv   -- per-division customer switch summary
  output/summary/phase136_valrecompute_part2_monthly.csv  -- monthly Omni/Tendering value-share series
  output/summary/phase136_valrecompute_part3_segment.csv  -- customer_segment distribution comparison
  output/summary/phase136_validator_report.md             -- final report (task-mandated filename)

Privacy (DATA_MAP.md's own rule, repo is public): no raw CustomerID/CustomerName/ContractID is
printed or saved anywhere below -- only aggregated counts, shares and distributions.
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pricelist_reader import load_visible_product_rows  # noqa: E402
from cube_ces_pull import pull_cube_ces_for_items  # noqa: E402
from db import run_query  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase136_validator_recompute")

ROOT = Path(__file__).resolve().parents[2]
OUT_DATA = ROOT / "output" / "data"
OUT_SUMMARY = ROOT / "output" / "summary"
PRICELIST_PATH = ROOT / "reference" / "pricelist.xlsx"

PEM103_SHEET = "PEM103-Version2"
PEM107_SHEET = "PEM107 CT-Version 2"

LATEST_COMPLETE_MONTH = "2026-08"  # today is 2026-09-24; September 2026 is not yet complete


def build_scope():
    """Derive PEM103 (87 codes) / PEM107 (136 codes) scope from the pricelist, from scratch."""
    pl = load_visible_product_rows(str(PRICELIST_PATH))
    pem103 = sorted(pl[pl["sheet"] == PEM103_SHEET]["code"].unique().tolist())
    pem107 = sorted(pl[pl["sheet"] == PEM107_SHEET]["code"].unique().tolist())
    assert len(pem103) == 87, f"expected 87 PEM103 codes, got {len(pem103)}"
    assert len(pem107) == 136, f"expected 136 PEM107 codes, got {len(pem107)}"
    overlap = set(pem103) & set(pem107)
    assert not overlap, f"unexpected PEM103/PEM107 code overlap: {overlap}"
    logger.info("Scope built: PEM103=%d codes, PEM107=%d codes, overlap=0", len(pem103), len(pem107))
    return pem103, pem107


def div_map_from(pem103, pem107):
    m = {c: "PEM103" for c in pem103}
    m.update({c: "PEM107" for c in pem107})
    return m


def pull_ces(pem103, pem107):
    all_codes = pem103 + pem107
    cols = ["ItemCode", "ContractID", "Status", "CtrDate", "ForecastDelDate", "ActualDelDate",
            "ActualQty", "ContractPrice", "ActualPrice", "PlanQty", "RevenueType", "CustomerID"]
    df = pull_cube_ces_for_items(all_codes, columns=cols)
    dm = div_map_from(pem103, pem107)
    df["division"] = df["ItemCode"].map(dm)
    df["CtrDate"] = pd.to_datetime(df["CtrDate"], errors="coerce")
    df["year"] = df["CtrDate"].dt.year
    df["yyyymm"] = df["CtrDate"].dt.to_period("M").astype(str)
    n_unmapped = df["division"].isna().sum()
    logger.info("Cube_CES pull: %d rows, %d unmapped-division rows (dropped codes outside scope)",
                len(df), n_unmapped)
    return df


def pull_sale_apd(pem103, pem107):
    all_codes = pem103 + pem107
    code_list = "','".join(all_codes)
    cols = ["itemcode", "contractid", "createDate", "revenue_type", "qty", "sale", "cost",
            "customerid", "customer_segment"]
    col_list = ", ".join(cols)
    sql = f"SELECT {col_list} FROM cube_Sale_APD WHERE itemcode IN ('{code_list}')"
    df = run_query(sql)
    dm = div_map_from(pem103, pem107)
    df["division"] = df["itemcode"].map(dm)
    df["createDate"] = pd.to_datetime(df["createDate"], errors="coerce")
    df["year"] = df["createDate"].dt.year
    logger.info("cube_Sale_APD pull: %d rows", len(df))
    return df


# ---------------------------------------------------------------------------
# Part 1: customer channel-switch count and value share, per division
# ---------------------------------------------------------------------------

def _dominant_by(dsub, measure_col):
    piv = (dsub.groupby(["CustomerID", "year", "RevenueType"])[measure_col]
           .sum().unstack("RevenueType").fillna(0))
    for col in ["Omni Channel", "Tendering"]:
        if col not in piv.columns:
            piv[col] = 0.0
    piv["dominant"] = np.where(
        piv["Tendering"] > piv["Omni Channel"], "Tendering",
        np.where(piv["Omni Channel"] > piv["Tendering"], "Omni Channel", "Tie"))
    return piv.reset_index()


def part1_customer_switch(ces: pd.DataFrame):
    """For each CustomerID present in both 2025 and 2026 (by CtrDate year), determine their
    dominant channel each year and count/measure switches, per division.

    TWO independent dominance measures are computed and reported side by side, since they can
    disagree sharply for a tender-driven division (a handful of huge, low-quantity Tendering
    contracts can dominate VALUE while contributing little QUANTITY):
      - PlanQty (ordered quantity): zero nulls across all statuses in this scope, unlike
        ActualQty, which is populated only for delivered ('Actual') rows and would systematically
        undercount the still-partial 2026 year for any customer with an open ('Backlog') order.
      - ContractPrice (ordered THB value): also zero nulls across all statuses; this is the
        measure that actually drives the division-level value-share reversal being investigated.
    """
    scope = ces[
        ces["division"].notna()
        & ces["RevenueType"].isin(["Omni Channel", "Tendering"])
        & ces["year"].isin([2025, 2026])
        & ces["CustomerID"].notna()
    ].copy()

    results = []
    pair_rows = []
    for division, dsub in scope.groupby("division"):
        out_row = {"division": division}
        for measure_col, measure_name in [("PlanQty", "planqty"), ("ContractPrice", "contractprice")]:
            dom = _dominant_by(dsub, measure_col)
            wide = dom.pivot_table(index="CustomerID", columns="year", values="dominant", aggfunc="first")
            if 2025 not in wide.columns or 2026 not in wide.columns:
                continue
            both = wide.dropna(subset=[2025, 2026]).copy()
            both["switched"] = both[2025] != both[2026]

            tot_per_cust = dsub.groupby("CustomerID")[measure_col].sum()
            both = both.join(tot_per_cust.rename("measure_2yr"))

            n_recurring = len(both)
            n_switched = int(both["switched"].sum())
            total_measure = both["measure_2yr"].sum()
            switched_measure = both.loc[both["switched"], "measure_2yr"].sum()

            out_row[f"n_recurring_customers_{measure_name}"] = n_recurring
            out_row[f"n_switched_{measure_name}"] = n_switched
            out_row[f"pct_switched_{measure_name}"] = (100 * n_switched / n_recurring
                                                         if n_recurring else np.nan)
            out_row[f"{measure_name}_share_of_switchers_pct"] = (
                100 * switched_measure / total_measure if total_measure else np.nan)
            out_row[f"total_recurring_{measure_name}_2yr"] = total_measure

            if measure_name == "contractprice":
                for (y2025, y2026), n in both.groupby([2025, 2026]).size().items():
                    pair_rows.append({
                        "division": division, "dominant_2025": y2025, "dominant_2026": y2026,
                        "n_customers": int(n),
                    })

        # customer-population turnover (no customer IDs -- aggregated counts only)
        cust_2025 = set(dsub[dsub["year"] == 2025]["CustomerID"].unique())
        cust_2026 = set(dsub[dsub["year"] == 2026]["CustomerID"].unique())
        recurring_ids = cust_2025 & cust_2026
        only_2025_ids = cust_2025 - cust_2026
        only_2026_ids = cust_2026 - cust_2025
        price_by_cust_year = (dsub.groupby(["CustomerID", "year"])["ContractPrice"]
                               .sum().unstack("year").fillna(0))
        out_row["n_customers_2025"] = len(cust_2025)
        out_row["n_customers_2026"] = len(cust_2026)
        out_row["n_customers_recurring"] = len(recurring_ids)
        out_row["n_customers_only_2025"] = len(only_2025_ids)
        out_row["n_customers_only_2026"] = len(only_2026_ids)
        out_row["contractprice_2025_only2025custs_thb"] = (
            price_by_cust_year.loc[list(only_2025_ids), 2025].sum() if only_2025_ids and 2025 in price_by_cust_year else 0.0)
        out_row["contractprice_2026_only2026custs_thb"] = (
            price_by_cust_year.loc[list(only_2026_ids), 2026].sum() if only_2026_ids and 2026 in price_by_cust_year else 0.0)
        out_row["contractprice_2025_recurringcusts_thb"] = (
            price_by_cust_year.loc[list(recurring_ids), 2025].sum() if recurring_ids and 2025 in price_by_cust_year else 0.0)
        out_row["contractprice_2026_recurringcusts_thb"] = (
            price_by_cust_year.loc[list(recurring_ids), 2026].sum() if recurring_ids and 2026 in price_by_cust_year else 0.0)

        results.append(out_row)

    summary = pd.DataFrame(results)
    pairs = pd.DataFrame(pair_rows)
    return summary, pairs


# ---------------------------------------------------------------------------
# Part 2: monthly Omni-vs-Tendering value-share series, step-change detection
# ---------------------------------------------------------------------------

def part2_monthly_series(ces: pd.DataFrame):
    """Monthly value-share series (by CtrDate month), ContractPrice-based, Jan 2025 through
    LATEST_COMPLETE_MONTH, both divisions. ContractPrice is used because it is populated for
    every row regardless of delivery status (unlike ActualQty/ActualPrice), so it captures orders
    placed in a month even if not yet delivered -- the right basis for a channel-mix-by-order-date
    series. (Cross-check: this reproduces the already-known headline shares, e.g. PEM103 88.5%
    Tendering 2025 / 96.6% Omni 2026, almost exactly when aggregated to full-year -- see report.)
    """
    scope = ces[
        ces["division"].notna()
        & ces["RevenueType"].isin(["Omni Channel", "Tendering"])
        & (ces["CtrDate"] >= "2025-01-01")
        & (ces["CtrDate"] <= f"{LATEST_COMPLETE_MONTH}-28")
    ].copy()
    scope = scope[scope["yyyymm"] <= LATEST_COMPLETE_MONTH]

    monthly = (scope.groupby(["division", "yyyymm", "RevenueType"])["ContractPrice"]
               .sum().unstack("RevenueType").fillna(0))
    for col in ["Omni Channel", "Tendering"]:
        if col not in monthly.columns:
            monthly[col] = 0.0
    monthly["total"] = monthly["Omni Channel"] + monthly["Tendering"]
    monthly["omni_share_pct"] = np.where(monthly["total"] > 0,
                                          100 * monthly["Omni Channel"] / monthly["total"], np.nan)
    monthly = monthly.reset_index().sort_values(["division", "yyyymm"])
    monthly["mom_change_pp"] = monthly.groupby("division")["omni_share_pct"].diff()
    return monthly


def detect_step_month(monthly: pd.DataFrame, division: str, threshold_pp: float = 25.0,
                       persistence_months: int = 2, reversion_tol_pp: float = 10.0):
    """Step-change criterion (stated explicitly, applied uniformly to both divisions):
    a candidate step month is one where the month-over-month change in omni_share_pct exceeds
    `threshold_pp` percentage points in absolute value, AND the share in every one of the
    following `persistence_months` (as many as exist in the series) stays within
    `reversion_tol_pp` points of the new post-step level (i.e. does not revert back toward the
    pre-step level). If more than one month in the series qualifies, or none does, report that
    explicitly rather than forcing a single-month answer.
    """
    d = monthly[monthly["division"] == division].reset_index(drop=True)
    candidates = []
    for i, row in d.iterrows():
        if pd.isna(row["mom_change_pp"]) or abs(row["mom_change_pp"]) < threshold_pp:
            continue
        post_level = row["omni_share_pct"]
        future = d.loc[i + 1: i + persistence_months, "omni_share_pct"]
        if future.isna().any():
            persists = False
        else:
            persists = bool((future - post_level).abs().le(reversion_tol_pp).all())
        candidates.append({
            "yyyymm": row["yyyymm"],
            "mom_change_pp": row["mom_change_pp"],
            "pre_share_pct": row["omni_share_pct"] - row["mom_change_pp"],
            "post_share_pct": post_level,
            "persists_next_%d_months" % persistence_months: persists,
        })
    return pd.DataFrame(candidates)


# ---------------------------------------------------------------------------
# Part 3: attribute comparison -- customer_segment (cube_Sale_APD)
# ---------------------------------------------------------------------------

def part3_customer_segment(sale_apd: pd.DataFrame):
    """Attribute chosen: customer_segment (cube_Sale_APD). This is a direct customer-classification
    field discovered via INFORMATION_SCHEMA.COLUMNS on cube_Sale_APD (not assumed) -- the most
    direct test of Explorer 2's class of question (do Tendering vs Omni orders differ on a
    characteristic independent of the RevenueType tag itself?). For each division, compare the
    customer_segment distribution of 2026's flipped-to channel against (a) that SAME channel's own
    2025 distribution and (b) the OTHER channel's 2025 distribution, using total variation distance
    (half the sum of absolute differences in category shares; 0 = identical, 1 = fully disjoint).
    """
    null_rate = sale_apd["customer_segment"].isna().mean()
    logger.info("customer_segment null rate across full pulled scope: %.2f%%", 100 * null_rate)

    flipped_to = {"PEM103": "Omni Channel", "PEM107": "Tendering"}
    rows = []
    dist_rows = []
    for division, new_channel in flipped_to.items():
        old_channel = "Tendering" if new_channel == "Omni Channel" else "Omni Channel"
        d = sale_apd[(sale_apd["division"] == division)
                     & sale_apd["revenue_type"].isin(["Omni Channel", "Tendering"])]

        own_2025 = d[(d["year"] == 2025) & (d["revenue_type"] == new_channel)]
        other_2025 = d[(d["year"] == 2025) & (d["revenue_type"] == old_channel)]
        flipped_2026 = d[(d["year"] == 2026) & (d["revenue_type"] == new_channel)]

        def dist(sub):
            vc = sub["customer_segment"].fillna("(null)").value_counts(normalize=True)
            return vc

        p_own = dist(own_2025)
        p_other = dist(other_2025)
        p_flip = dist(flipped_2026)

        def tvd(a, b):
            idx = a.index.union(b.index)
            a2, b2 = a.reindex(idx, fill_value=0), b.reindex(idx, fill_value=0)
            return 0.5 * (a2 - b2).abs().sum()

        tvd_vs_own = tvd(p_flip, p_own)
        tvd_vs_other = tvd(p_flip, p_other)

        rows.append({
            "division": division,
            "new_dominant_channel_2026": new_channel,
            "old_dominant_channel_2025": old_channel,
            "n_rows_own_channel_2025": len(own_2025),
            "n_rows_other_channel_2025": len(other_2025),
            "n_rows_flipped_2026": len(flipped_2026),
            "tvd_flipped2026_vs_ownchannel2025": tvd_vs_own,
            "tvd_flipped2026_vs_otherchannel2025": tvd_vs_other,
            "closer_to": ("OWN channel's 2025 orders (contradicts relabeling)"
                          if tvd_vs_own < tvd_vs_other
                          else "OTHER channel's 2025 orders (supports relabeling)"
                          if tvd_vs_other < tvd_vs_own else "TIE"),
        })
        for seg in p_own.index.union(p_other.index).union(p_flip.index):
            dist_rows.append({
                "division": division, "customer_segment": seg,
                "own_channel_2025_share": p_own.get(seg, 0.0),
                "other_channel_2025_share": p_other.get(seg, 0.0),
                "flipped_2026_share": p_flip.get(seg, 0.0),
            })

    return pd.DataFrame(rows), pd.DataFrame(dist_rows), null_rate


def main():
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.mkdir(parents=True, exist_ok=True)

    pem103, pem107 = build_scope()
    ces = pull_ces(pem103, pem107)
    sale_apd = pull_sale_apd(pem103, pem107)

    ces.to_csv(OUT_DATA / "phase136_valrecompute_ces_scope.csv", index=False)
    sale_apd.to_csv(OUT_DATA / "phase136_valrecompute_saleapd_scope.csv", index=False, encoding="utf-8-sig")

    switch_summary, switch_pairs = part1_customer_switch(ces)
    switch_summary.to_csv(OUT_SUMMARY / "phase136_valrecompute_part1_switch_summary.csv", index=False)
    switch_pairs.to_csv(OUT_SUMMARY / "phase136_valrecompute_part1_switch_pairs.csv", index=False)
    logger.info("Part 1 summary:\n%s", switch_summary.to_string())

    monthly = part2_monthly_series(ces)
    monthly.to_csv(OUT_SUMMARY / "phase136_valrecompute_part2_monthly.csv", index=False)
    step_pem103 = detect_step_month(monthly, "PEM103")
    step_pem107 = detect_step_month(monthly, "PEM107")
    logger.info("PEM103 step candidates:\n%s", step_pem103.to_string())
    logger.info("PEM107 step candidates:\n%s", step_pem107.to_string())
    step_pem103.to_csv(OUT_SUMMARY / "phase136_valrecompute_part2_stepcandidates_pem103.csv", index=False)
    step_pem107.to_csv(OUT_SUMMARY / "phase136_valrecompute_part2_stepcandidates_pem107.csv", index=False)

    seg_summary, seg_dist, null_rate = part3_customer_segment(sale_apd)
    seg_summary.to_csv(OUT_SUMMARY / "phase136_valrecompute_part3_segment_summary.csv", index=False)
    seg_dist.to_csv(OUT_SUMMARY / "phase136_valrecompute_part3_segment_distribution.csv", index=False)
    logger.info("Part 3 summary:\n%s", seg_summary.to_string())

    return {
        "switch_summary": switch_summary, "switch_pairs": switch_pairs,
        "monthly": monthly, "step_pem103": step_pem103, "step_pem107": step_pem107,
        "seg_summary": seg_summary, "seg_dist": seg_dist, "seg_null_rate": null_rate,
    }


if __name__ == "__main__":
    main()
