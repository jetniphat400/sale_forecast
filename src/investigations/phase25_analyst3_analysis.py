"""Phase 25 Analyst 3 (Agent 3 of 4 parallel, independent agents) -- analysis.

Target node: PROJECT_GRAPH.md Q10 (PEM107 branch, "how does the business actually fulfil
orders") / Q23 (PEM107's 2026 Omni Channel delivery decline). This task tests the BEHAVIOUR side
(timing/delivery/traceability/mix) of the business's claim (DATA_MAP.md Sec.7, level A) that
PEM107's Tendering and Omni Channel production/stock were shared and then separated in May 2026 --
does a STEP show up at May 2026 on any of four measures, or is any change gradual/misaligned with
that date? Two other agents test the batch-linkage-blindness and categorical-shift questions
separately; this agent's scope is strictly the four behavioural measures below.

Runs entirely on the raw pulls from phase25_analyst3_pull.py (no further DB access):
  - output/summary/phase25_analyst3_cube_ces_raw.csv     (Cube_CES, PEM107 136-item scope)
  - output/summary/phase25_analyst3_cube_final_raw.csv   (cube_final, same scope)
  - output/summary/phase25_analyst3_sale_apd_raw.csv     (cube_Sale_APD, same scope)

Periods (task brief):
  Period 1: 2025-05-01 to 2026-04-30 inclusive
  Period 2: 2026-05-01 to the latest available data (exact n reported per figure -- Period 2 is
            only a few months, so every Period-2 figure is reported with its own n and described
            as directional, not definitive, per the task brief).

Channels: Omni Channel vs Tendering (RevenueType / revenue_type). Other values (e.g. "Total
Customer Solution") are excluded from the channel comparison; their share of the in-window volume
is reported and flagged if it exceeds 2% (CONVENTIONS.md error-review item, "report shares
alongside absolute volumes"; METRICS.md Sec.21 convention for excluded-revenue-type shares).
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase25_analyst3_analysis")

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
OUT_DIR = PROJECT_ROOT / "output" / "summary"

P1_START = pd.Timestamp("2025-05-01")
P1_END_EXCL = pd.Timestamp("2026-05-01")   # period 1 is [P1_START, P1_END_EXCL)
P2_START = pd.Timestamp("2026-05-01")

CHANNELS = ["Omni Channel", "Tendering"]


def period_of(ts):
    if pd.isna(ts):
        return None
    if ts < P1_START:
        return "pre_P1"
    if ts < P1_END_EXCL:
        return "P1"
    return "P2"


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else np.nan


def dist_stats(series):
    s = pd.Series(series).dropna()
    if len(s) == 0:
        return dict(n=0, median=np.nan, p25=np.nan, p75=np.nan, mean=np.nan, min=np.nan, max=np.nan)
    return dict(n=int(len(s)), median=float(s.median()), p25=pct(s, 25), p75=pct(s, 75),
                mean=float(s.mean()), min=float(s.min()), max=float(s.max()))


def load():
    ces = pd.read_csv(
        OUT_DIR / "phase25_analyst3_cube_ces_raw.csv",
        parse_dates=["CtrDate", "PlanDelDate", "ForecastDelDate", "ActualDelDate"],
    )
    cf = pd.read_csv(OUT_DIR / "phase25_analyst3_cube_final_raw.csv", parse_dates=["final_date"],
                      low_memory=False)
    apd = pd.read_csv(OUT_DIR / "phase25_analyst3_sale_apd_raw.csv", parse_dates=["createDate"])
    logger.info("Loaded: Cube_CES %d rows, cube_final %d rows, cube_Sale_APD %d rows",
                len(ces), len(cf), len(apd))
    return ces, cf, apd


# --------------------------------------------------------------------------------------------
# Scope / channel-mix bookkeeping
# --------------------------------------------------------------------------------------------

def report_other_revenue_type_share(ces):
    """cube_Sale_APD.revenue_type / Cube_CES.RevenueType channel share outside Omni/Tendering, for
    the delivered (Status='Actual') rows inside the analysis window (P1+P2), row- and qty-based.
    Flag if the non-Omni/Tendering share exceeds 2% (METRICS.md Sec.21 convention).
    """
    actual = ces[ces["Status"] == "Actual"].copy()
    actual["period"] = actual["CtrDate"].apply(period_of)
    win = actual[actual["period"].isin(["P1", "P2"])]
    win = win.copy()
    win["qty"] = win["ActualQty"].fillna(0)
    counts = win["RevenueType"].value_counts(dropna=False)
    qtys = win.groupby(win["RevenueType"].fillna("NULL"))["qty"].sum()
    other_row_share = 1 - (win["RevenueType"].isin(CHANNELS).sum() / len(win) if len(win) else np.nan)
    other_qty_share = 1 - (win.loc[win["RevenueType"].isin(CHANNELS), "qty"].sum() / win["qty"].sum()
                            if win["qty"].sum() else np.nan)
    logger.info("RevenueType counts (Status=Actual, CtrDate in P1+P2 window):\n%s", counts.to_string())
    logger.info("RevenueType qty (Status=Actual, CtrDate in P1+P2 window):\n%s", qtys.to_string())
    logger.info("Non-Omni/Tendering share: row=%.2f%% qty=%.2f%% (flag threshold 2%%)",
                100 * other_row_share, 100 * other_qty_share)
    return dict(counts=counts.to_dict(), qtys=qtys.to_dict(),
                other_row_share_pct=100 * other_row_share, other_qty_share_pct=100 * other_qty_share)


# --------------------------------------------------------------------------------------------
# Measure 1: not_late, unit-weighted (METRICS.md Sec.19), windowed by ForecastDelDate (due date;
# established convention -- METRICS.md Sec.18 notes fill_rate/not_late are measured on the due
# date, and phase24_explorerA_analysis.py's not_late_by_month windows the same way).
# --------------------------------------------------------------------------------------------

def measure1_not_late(ces):
    scope = ces[(ces["RevenueType"].isin(CHANNELS)) & (ces["Status"] == "Actual")].copy()
    n_before = len(scope)
    scope = scope.dropna(subset=["ForecastDelDate", "ActualDelDate"])
    n_dropped = n_before - len(scope)
    logger.info("Measure 1 (not_late): %d Actual rows in channel scope, %d dropped for missing "
                "ForecastDelDate/ActualDelDate, %d usable", n_before, n_dropped, len(scope))
    scope["not_late"] = scope["ActualDelDate"] <= scope["ForecastDelDate"]
    scope["qty"] = scope["ActualQty"].fillna(0)
    scope["period"] = scope["ForecastDelDate"].apply(period_of)
    scope["month"] = scope["ForecastDelDate"].dt.to_period("M").astype(str)

    def agg(d):
        row_w = d["not_late"].mean() if len(d) else np.nan
        unit_w = ((d["not_late"] * d["qty"]).sum() / d["qty"].sum()) if d["qty"].sum() > 0 else np.nan
        return pd.Series({"n_rows": len(d), "total_qty": d["qty"].sum(),
                           "not_late_row_weighted": row_w, "not_late_unit_weighted": unit_w})

    period_table = (scope[scope["period"].isin(["P1", "P2"])]
                     .groupby(["RevenueType", "period"]).apply(agg).reset_index())
    monthly_table = scope.groupby(["RevenueType", "month"]).apply(agg).reset_index()
    return period_table, monthly_table, n_dropped


# --------------------------------------------------------------------------------------------
# Measure 2: order-to-delivery interval, createDate -> ActualDelDate.
# createDate proxy = Cube_CES.CtrDate: DATA_MAP.md "Cube_CES date fields" entry records CtrDate
# matches cube_Sale_APD.createDate at 99.946% (STATUS.md:3333-3334, V2) -- used here directly
# (no cross-table join) to avoid the lossy ContractID+ItemCode join to cube_Sale_APD (72.28% match
# rate, Q23 Part 1 finding, DATA_MAP.md Cube_CES.RevenueType entry), which would otherwise drop
# ~28% of rows for no benefit (both fields have already been shown equivalent at 99.946%).
# Windowed by CtrDate (order-creation date) -- the natural anchor for an "order-to-delivery"
# interval, and the same anchor measure 3 uses.
# CAVEAT (stated per task brief): orders created late in Period 2 that have not yet been
# delivered are, by construction, absent from this measure (Status='Actual' required) -- this
# right-censors the most recent months toward SHORTER observed intervals (only fast deliveries
# have had time to complete). Flagged explicitly in the report, not corrected for.
# --------------------------------------------------------------------------------------------

def measure2_order_to_delivery(ces):
    scope = ces[(ces["RevenueType"].isin(CHANNELS)) & (ces["Status"] == "Actual")].copy()
    n_before = len(scope)
    scope = scope.dropna(subset=["CtrDate", "ActualDelDate"])
    n_dropped = n_before - len(scope)
    logger.info("Measure 2 (order-to-delivery): %d Actual rows in channel scope, %d dropped for "
                "missing CtrDate/ActualDelDate, %d usable", n_before, n_dropped, len(scope))
    scope["interval_days"] = (scope["ActualDelDate"] - scope["CtrDate"]).dt.days
    scope["period"] = scope["CtrDate"].apply(period_of)
    scope["month"] = scope["CtrDate"].dt.to_period("M").astype(str)

    period_rows = []
    for (rt, per), d in scope[scope["period"].isin(["P1", "P2"])].groupby(["RevenueType", "period"]):
        period_rows.append(dict(RevenueType=rt, period=per, **dist_stats(d["interval_days"])))
    period_table = pd.DataFrame(period_rows)

    month_rows = []
    for (rt, m), d in scope.groupby(["RevenueType", "month"]):
        month_rows.append(dict(RevenueType=rt, month=m, **dist_stats(d["interval_days"])))
    monthly_table = pd.DataFrame(month_rows)
    return period_table, monthly_table, n_dropped


# --------------------------------------------------------------------------------------------
# Measure 3: share of delivered contracts traceable to a cube_final batch (jobno, linked via
# Cube_CES.OLMJobCode -- DATA_MAP.md Sec.2 jobcode/jobno/OLMJobCode entry, "all three reference
# the same underlying concept: a production-batch reference") that EXISTED (per cube_final's own
# final_date, the earliest final_date recorded for that jobno) BEFORE the contract's own CtrDate
# (createDate proxy, see measure 2 note).
#
# This is the same reverse-traceability CONCEPT as DATA_MAP.md's established PEM107 58.9% pooled
# figure (phaseJ3_explorerD_analysis.py), but NOT a re-read of the same number: that figure used
# Cube_CES's own OLMJobCode first-CtrDate as a stand-in "batch existed" date, because cube_final
# returned zero rows in that session (DATA_MAP.md Sec.4 Trap 7). This task's cube_final pull
# succeeded (8,723 rows, 89.1% of this scope's distinct jobno values also appear as an OLMJobCode
# -- phase25_analyst3_pull.py console log), so this figure uses cube_final's own final_date
# directly -- a more direct measurement of the same concept, not a recomputation of the same
# number. Any difference from 58.9% is reported as a methodological difference, not a
# contradiction (AGENTS.md rule 4).
# --------------------------------------------------------------------------------------------

def measure3_batch_traceability(ces, cf):
    batch_avail = cf.groupby("jobno")["final_date"].min()

    scope = ces[(ces["RevenueType"].isin(CHANNELS)) & (ces["Status"] == "Actual")].copy()
    scope = scope.dropna(subset=["CtrDate"])
    scope["qty"] = scope["ActualQty"].fillna(0)
    scope["period"] = scope["CtrDate"].apply(period_of)
    scope["month"] = scope["CtrDate"].dt.to_period("M").astype(str)

    def is_blank(x):
        if pd.isna(x):
            return True
        s = str(x).strip()
        return s == "" or s.lower() == "none"

    scope["has_token"] = ~scope["OLMJobCode"].apply(is_blank)
    scope["batch_avail_date"] = scope["OLMJobCode"].map(batch_avail)

    def classify(r):
        if not r["has_token"]:
            return "no_token"
        if pd.isna(r["batch_avail_date"]):
            return "no_cube_final_link"
        if r["batch_avail_date"] < r["CtrDate"]:
            return "traceable_pre_existing"
        return "not_pre_existing"

    scope["trace_class"] = scope.apply(classify, axis=1)

    def agg(d):
        n = len(d)
        pre = (d["trace_class"] == "traceable_pre_existing")
        row_share = pre.sum() / n if n else np.nan
        qty_total = d["qty"].sum()
        qty_share = d.loc[pre, "qty"].sum() / qty_total if qty_total > 0 else np.nan
        return pd.Series({
            "n_contracts": n, "total_qty": qty_total,
            "n_traceable_pre_existing": int(pre.sum()),
            "traceable_share_row": row_share, "traceable_share_qty": qty_share,
            "n_no_token": int((d["trace_class"] == "no_token").sum()),
            "n_no_cube_final_link": int((d["trace_class"] == "no_cube_final_link").sum()),
        })

    period_table = (scope[scope["period"].isin(["P1", "P2"])]
                     .groupby(["RevenueType", "period"]).apply(agg).reset_index())
    monthly_table = scope.groupby(["RevenueType", "month"]).apply(agg).reset_index()
    return period_table, monthly_table


# --------------------------------------------------------------------------------------------
# Measure 4: manufacturing_type mix (MTS/MTO/ETO), count-based and qty-based, computed directly
# on cube_Sale_APD order rows in scope (order-level attribute, DATA_MAP.md Sec.2 manufacturing_type
# entry -- not a fixed per-item classification, so no per-item derivation is attempted here).
# Status: Actual + MPS (METRICS.md Sec.15 established convention for "confirmed order" scope) --
# deliberately WIDER than measures 1-3 (Status='Actual' only), because mix is an attribute set at
# ORDER time, not at delivery time; restricting to delivered-only would right-censor Period 2's
# most recent months out of the mix measure for no reason tied to what mix actually is. Both are
# reported (Actual-only alongside Actual+MPS) so the reader can see whether this choice matters.
# Windowed by createDate (order-creation date).
# --------------------------------------------------------------------------------------------

def measure4_manufacturing_mix(apd):
    scope = apd[apd["revenue_type"].isin(CHANNELS)].copy()
    scope = scope.dropna(subset=["createDate"])
    scope["RevenueType"] = scope["revenue_type"]
    scope["period"] = scope["createDate"].apply(period_of)
    scope["month"] = scope["createDate"].dt.to_period("M").astype(str)
    scope["qty"] = scope["qty"].fillna(0)
    scope["manufacturing_type"] = scope["manufacturing_type"].fillna("MISSING")

    def build(status_filter, label):
        d = scope[scope["status"].isin(status_filter)]
        rows = []
        for (rt, per), g in d[d["period"].isin(["P1", "P2"])].groupby(["RevenueType", "period"]):
            n = len(g)
            qty_tot = g["qty"].sum()
            for mt, gg in g.groupby("manufacturing_type"):
                rows.append(dict(status_scope=label, RevenueType=rt, period=per,
                                  manufacturing_type=mt, n=len(gg), n_share=len(gg) / n if n else np.nan,
                                  qty=gg["qty"].sum(), qty_share=gg["qty"].sum() / qty_tot if qty_tot else np.nan,
                                  n_total=n, qty_total=qty_tot))
        period_table = pd.DataFrame(rows)

        rows_m = []
        for (rt, m), g in d.groupby(["RevenueType", "month"]):
            n = len(g)
            qty_tot = g["qty"].sum()
            for mt, gg in g.groupby("manufacturing_type"):
                rows_m.append(dict(status_scope=label, RevenueType=rt, month=m,
                                    manufacturing_type=mt, n=len(gg), n_share=len(gg) / n if n else np.nan,
                                    qty=gg["qty"].sum(), qty_share=gg["qty"].sum() / qty_tot if qty_tot else np.nan,
                                    n_total=n, qty_total=qty_tot))
        monthly_table = pd.DataFrame(rows_m)
        return period_table, monthly_table

    period_actual, monthly_actual = build(["Actual"], "Actual_only")
    period_actual_mps, monthly_actual_mps = build(["Actual", "MPS"], "Actual_plus_MPS")
    return (pd.concat([period_actual, period_actual_mps], ignore_index=True),
            pd.concat([monthly_actual, monthly_actual_mps], ignore_index=True))


def main():
    ces, cf, apd = load()

    other_rt = report_other_revenue_type_share(ces)

    m1_period, m1_monthly, m1_dropped = measure1_not_late(ces)
    m2_period, m2_monthly, m2_dropped = measure2_order_to_delivery(ces)
    m3_period, m3_monthly = measure3_batch_traceability(ces, cf)
    m4_period, m4_monthly = measure4_manufacturing_mix(apd)

    m1_period.to_csv(OUT_DIR / "phase25_analyst3_m1_not_late_period.csv", index=False)
    m1_monthly.to_csv(OUT_DIR / "phase25_analyst3_m1_not_late_monthly.csv", index=False)
    m2_period.to_csv(OUT_DIR / "phase25_analyst3_m2_order_to_delivery_period.csv", index=False)
    m2_monthly.to_csv(OUT_DIR / "phase25_analyst3_m2_order_to_delivery_monthly.csv", index=False)
    m3_period.to_csv(OUT_DIR / "phase25_analyst3_m3_batch_traceability_period.csv", index=False)
    m3_monthly.to_csv(OUT_DIR / "phase25_analyst3_m3_batch_traceability_monthly.csv", index=False)
    m4_period.to_csv(OUT_DIR / "phase25_analyst3_m4_manufacturing_mix_period.csv", index=False)
    m4_monthly.to_csv(OUT_DIR / "phase25_analyst3_m4_manufacturing_mix_monthly.csv", index=False)

    logger.info("M1 not_late period table:\n%s", m1_period.to_string())
    logger.info("M2 order-to-delivery period table:\n%s", m2_period.to_string())
    logger.info("M3 batch traceability period table:\n%s", m3_period.to_string())
    logger.info("M4 manufacturing mix period table:\n%s", m4_period.to_string())

    print("ANALYSIS DONE")


if __name__ == "__main__":
    main()
