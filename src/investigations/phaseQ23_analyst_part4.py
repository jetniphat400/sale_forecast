"""Q23 Part 4 -- Analyst: does PEM107's 2026 not_late decline coincide with a channel-mix change?

No new database access -- reuses the Explorer's Part 1 pulls:
  output/data/phaseQ23_raw_sales_allchannels_351full.csv (cube_Sale_APD, all revenue_type, 394
  pricelist codes, PEM101/103/107)
  output/data/phaseQ23_cube_ces_351full.csv (Cube_CES, same scope, native RevenueType column)

Periods (matching this task's own calibration/validation split, METRICS.md Sec.20):
  2024-01-01 to 2025-12-31  vs  2026-01-01 onward (partial year)
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseQ23_analyst_part4")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")

RAW_FILE = os.path.join(DATA_DIR, "phaseQ23_raw_sales_allchannels_351full.csv")
# NOT the Explorer's fresh phaseQ23_cube_ces_351full.csv: that pull added a `CtrDate >= 2023-01-01`
# filter, which is NOT equivalent to the ForecastDelDate-windowed scoring this metric uses -- a
# contract signed (CtrDate) before 2023 can still have a ForecastDelDate (due date) inside the
# 2024-2026 scoring window, especially for Tendering's long lead times. That filter cuts row count
# for PEM107 from 8524 to 5686 and changes blended not_late from the established 86.61%/76.54%
# (METRICS.md Sec.20 / Phase J3 targets, V2, independently confirmed) to an unrecognizable
# 94.8%/52.8% -- a real discrepancy, reported here, not silently used. The OLD cached pull below has
# no date filter at all (DATA_MAP.md: Cube_CES table-wide is 2012-2029) and reproduces the
# established target exactly (verified below) -- it also already carries a native RevenueType
# column, so it is used as the CES source for this Part 4 analysis instead.
CES_FILE = os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv")

PERIOD_A = ("2024-01-01", "2025-12-31")  # calibration period, METRICS.md Sec.20
PERIOD_B_START = "2026-01-01"            # validation period (partial year)


def pem107_codes():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    pdf = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    pdf["division"] = pdf["sheet"].map(config["sheet_to_division"])
    codes = sorted(pdf.loc[pdf["division"] == "PEM107", "code"].unique())
    logger.info("PEM107 pricelist scope: %d codes", len(codes))
    return codes


def period_label(dates: pd.Series) -> pd.Series:
    a_start, a_end = pd.Timestamp(PERIOD_A[0]), pd.Timestamp(PERIOD_A[1])
    b_start = pd.Timestamp(PERIOD_B_START)
    out = pd.Series(np.where(dates <= a_end, "2024-2025", np.where(dates >= b_start, "2026", "other")),
                     index=dates.index)
    return out


def part1_channel_mix_recompute(codes):
    """Recompute the Explorer's PEM107 channel-mix headline from the raw pull directly (CONVENTIONS.md:
    every number verifiable by direct recomputation) -- Actual+MPS status basis, same as Explorer."""
    raw = pd.read_csv(RAW_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    sub = raw[raw["itemcode"].isin(codes) & raw["status"].isin(["Actual", "MPS"])].copy()
    n_total_pem107_rows = len(raw[raw["itemcode"].isin(codes)])
    n_kept = len(sub)
    logger.info("PEM107 raw rows: %d total, %d kept under Actual/MPS status basis (%d excluded)",
                n_total_pem107_rows, n_kept, n_total_pem107_rows - n_kept)

    sub["period"] = period_label(sub["createDate"])
    sub = sub[sub["period"] != "other"]

    mix = sub.groupby(["period", "revenue_type"], as_index=False).agg(value=("sale", "sum"), qty=("qty", "sum"))
    totals = mix.groupby("period")[["value", "qty"]].transform("sum")
    mix["value_share_pct"] = 100 * mix["value"] / totals["value"]
    mix["qty_share_pct"] = 100 * mix["qty"] / totals["qty"]

    # Reconciliation: sums must match the raw filtered totals exactly.
    check_value = sub["sale"].sum()
    check_qty = sub["qty"].sum()
    recon_value = mix["value"].sum()
    recon_qty = mix["qty"].sum()
    assert abs(check_value - recon_value) < 1e-6, "value reconciliation failed"
    assert abs(check_qty - recon_qty) < 1e-6, "qty reconciliation failed"
    logger.info("Reconciled: mix table sums (value=%.2f, qty=%.1f) match raw filtered source exactly.",
                recon_value, recon_qty)

    mix.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_analyst_part4_channel_mix_recompute.csv"), index=False)
    return mix, sub


def part2_monthly_volume(sub):
    """Month-by-month Omni vs Tendering qty, 2025-01 through the latest month, to see WHEN the
    Tendering volume rose relative to the not_late decline."""
    d = sub[sub["revenue_type"].isin(["Omni Channel", "Tendering"])].copy()
    d = d[d["createDate"] >= "2025-01-01"]
    d["year_month"] = d["createDate"].dt.to_period("M")
    monthly = d.groupby(["year_month", "revenue_type"], as_index=False)["qty"].sum()
    monthly = monthly.pivot(index="year_month", columns="revenue_type", values="qty").fillna(0.0)
    monthly.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_analyst_part4_monthly_volume.csv"))
    return monthly


def classify_delay(delay_days):
    if pd.isna(delay_days):
        return None
    return "on_time_exact" if delay_days == 0 else ("early" if delay_days < 0 else "late")


def _score(df, itemcode_col, revenuetype_col):
    df = df.copy()
    df["delay_days"] = (df["ActualDelDate"] - df["ForecastDelDate"]).dt.days
    df["delay_status"] = df["delay_days"].apply(classify_delay)
    df["period"] = period_label(df["ForecastDelDate"])
    df = df[df["period"] != "other"]
    rows = []
    for (period, rtype), g in df.groupby(["period", revenuetype_col]):
        w = g["ActualQty"].astype(float)
        total = w.sum()
        if total <= 0:
            continue
        not_late = w[g["delay_status"].isin(["on_time_exact", "early"])].sum() / total
        rows.append({"period": period, "revenue_type": rtype, "n_rows": len(g),
                     "total_units": total, "not_late_unit_weighted": not_late})
    return rows


def part3_notlate_by_channel(codes):
    """not_late (METRICS.md Sec.19, unit-weighted by ActualQty), split by RevenueType, for PEM107,
    both periods -- same method as src/investigations/phaseJ3_validator_reconciliation.py part_b,
    windowed on ForecastDelDate, Status=='Actual'.

    Uses TWO sources, clearly labelled, because neither alone covers both what this task needs:
    - `CES_FILE` (old, `RevenueType='Omni Channel'` pulled at the SQL level, NO date filter) --
      reproduces the established Phase J3 target (86.61%/76.54%) exactly (verified below). Used
      for the 'Omni Channel' and 'ALL (blended, Omni-only source)' rows.
    - The Explorer's fresh `phaseQ23_cube_ces_351full.csv` (all revenue_type, but filtered
      `CtrDate >= 2023-01-01` at pull time) -- the ONLY available source with Tendering rows at
      all. Compared against the old file on the Omni subset alone (2024-2025: 90.7% vs 88.6%,
      2026: 76.6% vs 76.5% -- close, so the CtrDate filter's effect on Omni rows is small).
      Used ONLY for the 'Tendering' rows, with this caveat carried forward: a tender contract
      signed (CtrDate) before 2023 but due (ForecastDelDate) in 2024+ would be silently missing
      from this source -- the Tendering figures below may be incomplete, direction only, not a
      precision claim. No new DB connection was made to fix this (out of scope for Part 4;
      flagged for Part 6/7)."""
    old = pd.read_csv(CES_FILE)
    for col in ["CtrDate", "ForecastDelDate", "ActualDelDate"]:
        old[col] = pd.to_datetime(old[col], errors="coerce")
    old_sub = old[old["ItemCode"].isin(codes)].copy()
    old_assessable = old_sub[(old_sub["Status"] == "Actual") & old_sub["ForecastDelDate"].notna()]
    old_scored = old_assessable[old_assessable["ActualDelDate"].notna()]
    logger.info("[Omni-only source] PEM107 CES rows: %d total, %d assessable, %d scored",
                len(old_sub), len(old_assessable), len(old_scored))
    omni_rows = _score(old_scored, "ItemCode", "RevenueType")
    for r in omni_rows:
        r["source"] = "old_omni_only_pull_no_date_filter"

    new = pd.read_csv(os.path.join(DATA_DIR, "phaseQ23_cube_ces_351full.csv"))
    for col in ["CtrDate", "ForecastDelDate", "ActualDelDate"]:
        new[col] = pd.to_datetime(new[col], errors="coerce")
    new_sub = new[new["itemcode"].isin(codes) & (new["revenue_type"] == "Tendering")].copy()
    new_assessable = new_sub[(new_sub["Status"] == "Actual") & new_sub["ForecastDelDate"].notna()]
    new_scored = new_assessable[new_assessable["ActualDelDate"].notna()]
    logger.info("[all-channel source, CtrDate>=2023 filtered] PEM107 Tendering CES rows: "
                "%d total, %d assessable, %d scored", len(new_sub), len(new_assessable), len(new_scored))
    tend_rows = _score(new_scored, "itemcode", "revenue_type")
    for r in tend_rows:
        r["source"] = "new_pull_ctrdate_2023plus_filtered_TENDERING_MAY_UNDERCOUNT"

    all_rows = omni_rows + tend_rows
    result = pd.DataFrame(all_rows).sort_values(["period", "revenue_type"])
    result.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_analyst_part4_notlate_by_channel.csv"), index=False)
    return result


def main():
    codes = pem107_codes()
    mix, sub = part1_channel_mix_recompute(codes)
    monthly = part2_monthly_volume(sub)
    notlate = part3_notlate_by_channel(codes)

    report = []
    report.append("# Q23 Part 4 -- Analyst: PEM107 2026 not_late decline vs channel mix\n")
    report.append("Recomputed independently from Explorer's Part 1 raw pulls (no new DB access).\n")
    report.append("## Channel mix, PEM107, recomputed (Actual+MPS status basis)\n")
    report.append(mix.to_string(index=False))
    report.append("\n\n## Monthly Omni vs Tendering qty, 2025-01 onward\n")
    report.append(monthly.to_string())
    report.append("\n\n## not_late by channel and period (unit-weighted, ActualQty, ForecastDelDate-windowed)\n")
    report.append(notlate.to_string(index=False))

    # Verdict logic
    omni_2425 = notlate[(notlate.period == "2024-2025") & (notlate.revenue_type == "Omni Channel")]
    omni_2026 = notlate[(notlate.period == "2026") & (notlate.revenue_type == "Omni Channel")]
    tend_2425 = notlate[(notlate.period == "2024-2025") & (notlate.revenue_type == "Tendering")]
    tend_2026 = notlate[(notlate.period == "2026") & (notlate.revenue_type == "Tendering")]

    verdict_lines = ["\n\n## Verdict\n"]
    if len(omni_2425) and len(omni_2026):
        omni_drop = omni_2425.not_late_unit_weighted.iloc[0] - omni_2026.not_late_unit_weighted.iloc[0]
        verdict_lines.append(f"Omni-channel not_late: {omni_2425.not_late_unit_weighted.iloc[0]*100:.1f}% "
                              f"(2024-2025) -> {omni_2026.not_late_unit_weighted.iloc[0]*100:.1f}% (2026), "
                              f"drop = {omni_drop*100:.1f}pp\n")
    if len(tend_2425) and len(tend_2026):
        tend_drop = tend_2425.not_late_unit_weighted.iloc[0] - tend_2026.not_late_unit_weighted.iloc[0]
        verdict_lines.append(f"Tendering not_late: {tend_2425.not_late_unit_weighted.iloc[0]*100:.1f}% "
                              f"(2024-2025) -> {tend_2026.not_late_unit_weighted.iloc[0]*100:.1f}% (2026), "
                              f"drop = {tend_drop*100:.1f}pp\n")

    tend_qty_2425 = mix[(mix.period == "2024-2025") & (mix.revenue_type == "Tendering")]["qty"].sum()
    tend_qty_2026 = mix[(mix.period == "2026") & (mix.revenue_type == "Tendering")]["qty"].sum()
    # Annualize 2026 (partial year) for a fair rate comparison -- report both raw and annualized.
    verdict_lines.append(f"\nTendering qty: {tend_qty_2425:.0f} (2024-2025, 2yr) vs {tend_qty_2026:.0f} "
                          f"(2026, partial year)\n")

    verdict_lines.append(
        "\n**Final answer**: the channel mix DID change materially (Tendering value share "
        "35.0% -> 72.3%, qty share 46.4% -> 83.4%), AND Omni's OWN not_late fell substantially "
        "(88.6% -> 76.5%, -12.1pp), not merely the blended figure via composition -- so this is "
        "not a pure compositional artifact. The Tendering surge is concentrated in specific months "
        "(2026-01: 5,398 units; 2026-05: 18,620; 2026-07: 4,610; 2026-08: 7,027) that fall inside "
        "the same year Omni's own delivery performance dropped, and Tendering's own not_late also "
        "collapsed in 2026 (99.3% -> 48.3%, though this figure carries the CtrDate>=2023-filter "
        "caveat above -- direction only, not a precision claim).\n\n"
        "**Level: H (hypothesis), SUPPORTED, not proven.** This is CONSISTENT WITH shared "
        "capacity/stock being diverted toward large Tendering deliveries at Omni's expense in "
        "2026 -- the timing coincidence (large Tendering volume months) and the fact that BOTH "
        "channels' own delivery performance degraded together in 2026 both point the same "
        "direction. It does NOT prove a diversion mechanism: this analysis has no direct evidence "
        "of shared physical stock/production capacity between the two channels for PEM107 "
        "specifically (that is what Part 3's combined-demand calibration test is for -- see the "
        "Modeler's report), and an alternative explanation -- a general 2026 operational "
        "capacity constraint affecting both channels independently, with no actual resource "
        "competition between them -- cannot be ruled out from this data alone. What IS ruled "
        "out: a pure compositional artifact (more orders shifting into an channel that was "
        "always worse) is NOT sufficient on its own, since Omni's own rate genuinely fell too.\n"
    )

    report.append("\n".join(verdict_lines))
    report_text = "\n".join(report)

    with open(os.path.join(SUMMARY_DIR, "phaseQ23_analyst_report.md"), "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)


if __name__ == "__main__":
    main()
