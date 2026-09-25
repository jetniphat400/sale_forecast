"""Phase 25 Explorer 2, analysis step (no DB access -- reads the raw CSVs already saved by
phase25_explorer2_pull.py). Builds, for every categorical column checked, a per-month x per-channel
distribution from Jan 2025 to the latest available data, and a focused April-2026-vs-June-2026
comparison (the months bracketing the claimed May 2026 PEM107 Tendering/Omni split).

Date keys used (methodology choice, stated explicitly per AGENTS.md rule 2):
- cube_Sale_APD, Cube_CES: forecast_date / ForecastDelDate (the scheduled-delivery-date concept,
  DATA_MAP.md Sec.2) -- chosen for consistency with the project's established "not_late"/June-2026
  delivery-performance drop, which is itself forecast_date-keyed (METRICS.md Sec.16, Sec.19).
- cube_final: final_date (the production-batch completion date used throughout this project's
  cube_final work, e.g. DATA_MAP.md Sec.4 Trap 21/22 and the prior Explorer A jobno/OLMJobCode
  linkage test) -- cube_final has no delivery-date or channel field of its own.

Channel field: revenue_type (cube_Sale_APD) / RevenueType (Cube_CES, native). cube_final has NO
channel field and no verified join to a channel-bearing table within this task's one-connection
budget (DATA_MAP.md: cube_final.ctrno <-> contractid/ContractID is still "H", never confirmed) --
cube_final's findings below are reported UNSPLIT by channel, and this limitation is stated
explicitly rather than silently worked around.
"""
import logging
import re
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("phase25_explorer2_analysis")

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "summary"

START = pd.Timestamp("2025-01-01")
APR = pd.Timestamp("2026-04-01")
JUN = pd.Timestamp("2026-06-01")


def month_key(s: pd.Series) -> pd.Series:
    """Returns a 'YYYY-MM' string per row, or pd.NA for unparseable dates -- never the literal
    string 'NaT', which would otherwise sort lexicographically ABOVE any real 'YYYY-MM' string
    (e.g. 'NaT' >= '2025-01' is True) and silently leak null-date rows into a >= filter."""
    d = pd.to_datetime(s, errors="coerce")
    out = d.dt.to_period("M").astype(str)
    out = out.where(d.notna(), other=pd.NA)
    return out


def jobcode_prefix(s: pd.Series) -> pd.Series:
    def _pfx(x):
        if pd.isna(x):
            return None
        first_token = str(x).split(",")[0].strip()
        m = re.match(r"^[A-Za-z]+", first_token)
        return m.group(0) if m else "OTHER_NONALPHA"
    return s.apply(_pfx)


def dist_table(df: pd.DataFrame, col: str, month_col: str, channel_col: str, label: str,
               start=START):
    """Per-month x per-channel value_counts (%), restricted to month >= start."""
    d = df.copy()
    d["_month"] = month_key(d[month_col])
    d = d[d["_month"].notna()]
    d = d[d["_month"] >= start.strftime("%Y-%m")]
    if channel_col is None:
        grp = d.groupby(["_month"])[col]
        out = grp.value_counts(normalize=True, dropna=False).rename("share").reset_index()
        out["channel"] = "ALL"
    else:
        grp = d.groupby(["_month", channel_col])[col]
        out = grp.value_counts(normalize=True, dropna=False).rename("share").reset_index()
        out = out.rename(columns={channel_col: "channel"})
    out = out.rename(columns={col: "value"})
    out["column"] = label
    counts = d.groupby(["_month"] + ([channel_col] if channel_col else [])).size()
    return out, d


def apr_jun_compare(df: pd.DataFrame, col: str, month_col: str, channel_col: str, label: str):
    d = df.copy()
    d["_month"] = pd.to_datetime(d[month_col], errors="coerce").dt.to_period("M")
    apr = d[d["_month"] == pd.Period("2026-04", freq="M")]
    jun = d[d["_month"] == pd.Period("2026-06", freq="M")]
    rows = []
    channels = ["ALL"]
    if channel_col:
        channels += sorted(pd.concat([apr[channel_col], jun[channel_col]]).dropna().unique().tolist())
    for ch in channels:
        a = apr if ch == "ALL" else apr[apr[channel_col] == ch]
        j = jun if ch == "ALL" else jun[jun[channel_col] == ch]
        n_a, n_j = len(a), len(j)
        va = a[col].value_counts(normalize=True, dropna=False)
        vj = j[col].value_counts(normalize=True, dropna=False)
        all_vals = set(va.index) | set(vj.index)
        for v in all_vals:
            rows.append({
                "column": label, "channel": ch, "value": v,
                "apr2026_share": round(va.get(v, 0.0) * 100, 2),
                "jun2026_share": round(vj.get(v, 0.0) * 100, 2),
                "apr2026_n": n_a, "jun2026_n": n_j,
                "abs_pp_change": round(abs(va.get(v, 0.0) - vj.get(v, 0.0)) * 100, 2),
            })
    out = pd.DataFrame(rows).sort_values(["column", "channel", "abs_pp_change"], ascending=[True, True, False])
    return out


def main():
    sa = pd.read_csv(OUT_DIR / "phase25_explorer2_cube_Sale_APD_raw.csv")
    ces = pd.read_csv(OUT_DIR / "phase25_explorer2_Cube_CES_raw.csv")
    cf = pd.read_csv(OUT_DIR / "phase25_explorer2_cube_final_raw.csv")

    sa["_jobcode_prefix"] = jobcode_prefix(sa["jobcode"])
    ces["_olmjobcode_prefix"] = jobcode_prefix(ces["OLMJobCode"])

    logger.info("cube_Sale_APD rows: %d, date range forecast_date %s to %s",
                len(sa), pd.to_datetime(sa["forecast_date"], errors="coerce").min(),
                pd.to_datetime(sa["forecast_date"], errors="coerce").max())
    logger.info("Cube_CES rows: %d, date range ForecastDelDate %s to %s",
                len(ces), pd.to_datetime(ces["ForecastDelDate"], errors="coerce").min(),
                pd.to_datetime(ces["ForecastDelDate"], errors="coerce").max())
    logger.info("cube_final rows: %d, date range final_date %s to %s",
                len(cf), pd.to_datetime(cf["final_date"], errors="coerce").min(),
                pd.to_datetime(cf["final_date"], errors="coerce").max())

    all_compare = []

    # --- cube_Sale_APD columns ---
    sa_cols = {
        "division": "cube_Sale_APD.division",
        "status": "cube_Sale_APD.status",
        "manufacturing_type": "cube_Sale_APD.manufacturing_type",
        "typeOfSale": "cube_Sale_APD.typeOfSale",
        "_jobcode_prefix": "cube_Sale_APD.jobcode_prefix",
    }
    for col, label in sa_cols.items():
        cmp = apr_jun_compare(sa, col, "forecast_date", "revenue_type", label)
        all_compare.append(cmp)

    # revenue_type itself (channel mix over time) -- context, ALL only
    cmp = apr_jun_compare(sa, "revenue_type", "forecast_date", None, "cube_Sale_APD.revenue_type")
    all_compare.append(cmp)

    # --- Cube_CES columns ---
    ces_cols = {
        "Status": "Cube_CES.Status",
        "SaleDivision": "Cube_CES.SaleDivision",
        "ManuDivision": "Cube_CES.ManuDivision",
        "Company": "Cube_CES.Company",
        "ProductType": "Cube_CES.ProductType",
        "PrdTypeID": "Cube_CES.PrdTypeID",
        "_olmjobcode_prefix": "Cube_CES.OLMJobCode_prefix",
    }
    for col, label in ces_cols.items():
        cmp = apr_jun_compare(ces, col, "ForecastDelDate", "RevenueType", label)
        all_compare.append(cmp)

    cmp = apr_jun_compare(ces, "RevenueType", "ForecastDelDate", None, "Cube_CES.RevenueType")
    all_compare.append(cmp)

    # --- cube_final columns (no channel field; report unsplit) ---
    cf_cols = {
        "division": "cube_final.division",
        "transfer_type": "cube_final.transfer_type",
        "fg_check_status": "cube_final.fg_check_status",
        "fg_final_status": "cube_final.fg_final_status",
        "company": "cube_final.company",
    }
    for col, label in cf_cols.items():
        cmp = apr_jun_compare(cf, col, "final_date", None, label)
        all_compare.append(cmp)

    # job_qty: numeric, bucket into ranges for a "distribution" comparison
    cf2 = cf.copy()
    cf2["_month"] = pd.to_datetime(cf2["final_date"], errors="coerce").dt.to_period("M")
    bins = [0, 5, 20, 50, 100, 500, 100000]
    labels = ["1-5", "6-20", "21-50", "51-100", "101-500", "501+"]
    cf2["_job_qty_bucket"] = pd.cut(cf2["job_qty"], bins=bins, labels=labels, include_lowest=True)
    cmp = apr_jun_compare(cf2, "_job_qty_bucket", "final_date", None, "cube_final.job_qty_bucket")
    all_compare.append(cmp)

    apr_n = (cf2["_month"] == pd.Period("2026-04", freq="M")).sum()
    jun_n = (cf2["_month"] == pd.Period("2026-06", freq="M")).sum()
    apr_stats = cf2.loc[cf2["_month"] == pd.Period("2026-04", freq="M"), "job_qty"].describe()
    jun_stats = cf2.loc[cf2["_month"] == pd.Period("2026-06", freq="M"), "job_qty"].describe()
    logger.info("cube_final job_qty April 2026 (n=%d):\n%s", apr_n, apr_stats)
    logger.info("cube_final job_qty June 2026 (n=%d):\n%s", jun_n, jun_stats)

    full = pd.concat(all_compare, ignore_index=True)
    full.to_csv(OUT_DIR / "phase25_explorer2_apr_vs_jun_2026_comparison.csv", index=False)
    logger.info("Wrote comparison table: %d rows -> %s", len(full),
                OUT_DIR / "phase25_explorer2_apr_vs_jun_2026_comparison.csv")

    # --- Also: full monthly time series (Jan 2025 - latest) per column, for context/plots ---
    monthly_all = []
    for col, label in sa_cols.items():
        out, _ = dist_table(sa, col, "forecast_date", "revenue_type", label)
        monthly_all.append(out)
    out, _ = dist_table(sa, "revenue_type", "forecast_date", None, "cube_Sale_APD.revenue_type")
    monthly_all.append(out)
    for col, label in ces_cols.items():
        out, _ = dist_table(ces, col, "ForecastDelDate", "RevenueType", label)
        monthly_all.append(out)
    out, _ = dist_table(ces, "RevenueType", "ForecastDelDate", None, "Cube_CES.RevenueType")
    monthly_all.append(out)
    for col, label in cf_cols.items():
        out, _ = dist_table(cf, col, "final_date", None, label)
        monthly_all.append(out)
    out, _ = dist_table(cf2, "_job_qty_bucket", "final_date", None, "cube_final.job_qty_bucket")
    monthly_all.append(out)

    monthly_full = pd.concat(monthly_all, ignore_index=True)
    monthly_full.to_csv(OUT_DIR / "phase25_explorer2_monthly_distributions_jan2025_onward.csv",
                         index=False)
    logger.info("Wrote monthly distribution table: %d rows -> %s", len(monthly_full),
                OUT_DIR / "phase25_explorer2_monthly_distributions_jan2025_onward.csv")

    # --- Row counts per month per channel (denominator context) ---
    sa["_month"] = month_key(sa["forecast_date"])
    sa_scoped = sa[sa["_month"].notna() & (sa["_month"] >= "2025-01")]
    sa_counts = sa_scoped.groupby(["_month", "revenue_type"]).size().rename("n").reset_index()
    sa_counts["table"] = "cube_Sale_APD"
    ces["_month"] = month_key(ces["ForecastDelDate"])
    ces_scoped = ces[ces["_month"].notna() & (ces["_month"] >= "2025-01")]
    ces_counts = ces_scoped.groupby(["_month", "RevenueType"], dropna=False).size().rename("n").reset_index()
    ces_counts = ces_counts.rename(columns={"RevenueType": "revenue_type"})
    ces_counts["table"] = "Cube_CES"
    cf["_month"] = month_key(cf["final_date"])
    cf_scoped = cf[cf["_month"].notna() & (cf["_month"] >= "2025-01")]
    cf_counts = cf_scoped.groupby(["_month"]).size().rename("n").reset_index()
    cf_counts["revenue_type"] = "N/A (no channel field)"
    cf_counts["table"] = "cube_final"
    row_counts = pd.concat([sa_counts, ces_counts, cf_counts], ignore_index=True)
    row_counts.to_csv(OUT_DIR / "phase25_explorer2_row_counts_by_month_channel.csv", index=False)
    logger.info("Wrote row-count table -> %s",
                OUT_DIR / "phase25_explorer2_row_counts_by_month_channel.csv")


if __name__ == "__main__":
    main()
