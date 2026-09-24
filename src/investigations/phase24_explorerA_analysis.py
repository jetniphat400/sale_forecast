"""Phase 24 Explorer A analysis: forward/reverse dual-channel share and Omni not_late, by month,
for PEM107, to test the business's "shared production/stock, separated mid-2026" claim
(DATA_MAP.md Sec.7). Reads the raw pulls saved by phase24_explorerA_pull.py -- no further DB
access.
"""
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("phase24_explorerA_analysis")

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "summary"
WINDOW_START = "2025-01-01"
# Most recent COMPLETE month with data; today is 2026-09-24 (partial Sep 2026 is reported
# separately and flagged, not treated as a complete month for trend reading).
WINDOW_END_COMPLETE = "2026-08-31"


def load():
    cf = pd.read_csv(OUT_DIR / "phase24_explorerA_cube_final_raw.csv")
    ces = pd.read_csv(OUT_DIR / "phase24_explorerA_cube_ces_raw.csv")
    cf["final_date"] = pd.to_datetime(cf["final_date"], errors="coerce")
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["ForecastDelDate"] = pd.to_datetime(ces["ForecastDelDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")
    return cf, ces


def batch_channel_map(cf, ces):
    """For each cube_final jobno, the set of distinct Cube_CES RevenueType values found among
    ALL (unbounded-time) Cube_CES rows whose OLMJobCode matches that jobno -- 'ever linked'
    channel membership, used by both the forward and reverse direction checks.
    """
    ces_link = ces.dropna(subset=["OLMJobCode", "RevenueType"])
    grp = ces_link.groupby("OLMJobCode")["RevenueType"].apply(lambda s: set(s.unique()))
    jobnos = cf["jobno"].dropna().unique()
    rows = []
    for jn in jobnos:
        channels = grp.get(jn, set())
        rows.append({
            "jobno": jn,
            "channels": channels,
            "has_omni": "Omni Channel" in channels,
            "has_tendering": "Tendering" in channels,
            "has_other_only": bool(channels) and not ({"Omni Channel", "Tendering"} & channels),
            "linked": bool(channels),
        })
    bmap = pd.DataFrame(rows).set_index("jobno")
    return bmap


def match_rates(cf, ces):
    jobno_set = set(cf["jobno"].dropna().unique())
    olm_set = set(ces["OLMJobCode"].dropna().unique())
    fwd = len(jobno_set & olm_set) / len(jobno_set)
    rev = len(jobno_set & olm_set) / len(olm_set) if olm_set else float("nan")
    logger.info("Forward match (jobno -> OLMJobCode, all-time): %d/%d = %.2f%%",
                len(jobno_set & olm_set), len(jobno_set), 100 * fwd)
    logger.info("Reverse match (OLMJobCode -> jobno, all-time): %d/%d = %.2f%%",
                len(jobno_set & olm_set), len(olm_set), 100 * rev)
    return fwd, rev, len(jobno_set), len(olm_set), len(jobno_set & olm_set)


def forward_direction(cf, bmap):
    """Part 2: per calendar month (by cf.final_date), how many distinct PEM107 batches (jobno)
    active that month link (ever, via bmap) to BOTH Tendering and Omni Channel, vs only one
    channel, vs no link at all.
    """
    df = cf.dropna(subset=["final_date"]).copy()
    df["month"] = df["final_date"].dt.to_period("M").astype(str)
    df = df[(df["final_date"] >= WINDOW_START)]
    df = df.merge(bmap, left_on="jobno", right_index=True, how="left")
    df["has_omni"] = df["has_omni"].fillna(False)
    df["has_tendering"] = df["has_tendering"].fillna(False)
    df["linked"] = df["linked"].fillna(False)

    def classify(r):
        if r["has_omni"] and r["has_tendering"]:
            return "dual_channel"
        if r["has_omni"]:
            return "omni_only"
        if r["has_tendering"]:
            return "tendering_only"
        if r["linked"]:
            return "other_channel_only"
        return "no_ces_link"

    df["category"] = df.apply(classify, axis=1)
    per_batch_month = df.drop_duplicates(subset=["month", "jobno"])[["month", "jobno", "category"]]
    table = per_batch_month.groupby(["month", "category"]).size().unstack(fill_value=0)
    for col in ["dual_channel", "omni_only", "tendering_only", "other_channel_only", "no_ces_link"]:
        if col not in table.columns:
            table[col] = 0
    table = table[["dual_channel", "omni_only", "tendering_only", "other_channel_only", "no_ces_link"]]
    table["total_batches"] = table.sum(axis=1)
    table["dual_channel_share_of_linked"] = table["dual_channel"] / (
        table["total_batches"] - table["no_ces_link"]).replace(0, pd.NA)
    table["dual_channel_share_of_all"] = table["dual_channel"] / table["total_batches"]
    return table.reset_index()


def reverse_direction(ces, bmap):
    """Part 3: per calendar month (by CtrDate, contract-creation date), of PEM107's Omni Channel
    Cube_CES qty (ActualQty, Status in Actual/Backlog -- the established Actual+MPS-equivalent
    demand scope), what share has an OLMJobCode that traces to a cube_final batch (jobno) which
    ALSO served >=1 Tendering-tagged contract at any point (per bmap, unbounded time).
    """
    scope = ces[(ces["RevenueType"] == "Omni Channel") & (ces["Status"].isin(["Actual", "Backlog"]))].copy()
    scope = scope.dropna(subset=["CtrDate"])
    scope = scope[(scope["CtrDate"] >= WINDOW_START)]
    scope["month"] = scope["CtrDate"].dt.to_period("M").astype(str)
    scope = scope.merge(bmap[["has_tendering"]], left_on="OLMJobCode", right_index=True, how="left")
    scope["traces_to_dual_batch"] = scope["has_tendering"].fillna(False)
    scope["qty"] = scope["ActualQty"].fillna(0)

    g = scope.groupby("month").apply(
        lambda d: pd.Series({
            "omni_qty_total": d["qty"].sum(),
            "omni_qty_traced_to_dual_batch": d.loc[d["traces_to_dual_batch"], "qty"].sum(),
            "n_rows": len(d),
            "n_rows_with_olmjobcode": d["OLMJobCode"].notna().sum(),
        })
    ).reset_index()
    g["traced_share"] = g["omni_qty_traced_to_dual_batch"] / g["omni_qty_total"].replace(0, pd.NA)
    return g


def not_late_by_month(ces):
    """Part 4: PEM107 Omni Channel not_late per month, METRICS.md Sec.19 definition
    (not_late = delivered on or before due date), Status='Actual' only (ActualDelDate populated
    only for these rows), due-date field = ForecastDelDate (established convention, Sec.18/19/20
    and cube_ces_pull.py docstring). Both row- and unit-weighted computed; unit-weighted is
    reported as the primary figure (METRICS.md Sec.20 cites 'not_late (unit-weighted, section 19)
    per division' as the convention used for the division-level monthly/period figures this
    project already reports).
    """
    scope = ces[(ces["RevenueType"] == "Omni Channel") & (ces["Status"] == "Actual")].copy()
    scope = scope.dropna(subset=["ForecastDelDate", "ActualDelDate"])
    scope = scope[(scope["ForecastDelDate"] >= WINDOW_START)]
    scope["month"] = scope["ForecastDelDate"].dt.to_period("M").astype(str)
    scope["not_late"] = scope["ActualDelDate"] <= scope["ForecastDelDate"]
    scope["qty"] = scope["ActualQty"].fillna(0)

    def agg(d):
        row_weighted = d["not_late"].mean()
        unit_weighted = (d["not_late"] * d["qty"]).sum() / d["qty"].sum() if d["qty"].sum() > 0 else float("nan")
        return pd.Series({
            "n_rows": len(d),
            "total_qty": d["qty"].sum(),
            "not_late_row_weighted": row_weighted,
            "not_late_unit_weighted": unit_weighted,
        })

    g = scope.groupby("month").apply(agg).reset_index()
    return g


def main():
    cf, ces = load()
    bmap = batch_channel_map(cf, ces)
    fwd_rate, rev_rate, n_jobno, n_olm, n_match = match_rates(cf, ces)

    fwd_table = forward_direction(cf, bmap)
    rev_table = reverse_direction(ces, bmap)
    nl_table = not_late_by_month(ces)

    fwd_table.to_csv(OUT_DIR / "phase24_explorerA_forward_direction.csv", index=False)
    rev_table.to_csv(OUT_DIR / "phase24_explorerA_reverse_direction.csv", index=False)
    nl_table.to_csv(OUT_DIR / "phase24_explorerA_not_late_by_month.csv", index=False)

    with open(OUT_DIR / "phase24_explorerA_match_rates.txt", "w") as f:
        f.write(f"jobno distinct: {n_jobno}\n")
        f.write(f"OLMJobCode distinct (PEM107 item scope, all-time): {n_olm}\n")
        f.write(f"intersection: {n_match}\n")
        f.write(f"forward rate (jobno -> OLMJobCode): {fwd_rate:.4f}\n")
        f.write(f"reverse rate (OLMJobCode -> jobno): {rev_rate:.4f}\n")

    logger.info("Forward direction table:\n%s", fwd_table.to_string())
    logger.info("Reverse direction table:\n%s", rev_table.to_string())
    logger.info("not_late by month:\n%s", nl_table.to_string())


if __name__ == "__main__":
    main()
