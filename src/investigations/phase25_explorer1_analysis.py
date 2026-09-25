"""Phase 25 Explorer 1 analysis: does the jobcode/OLMJobCode <-> cube_final.jobno linkage itself
go blind at the late-2024 PEM107 reorganisation? Reads the raw pulls saved by
phase25_explorer1_pull.py -- no further DB access (one connection attempt total, in the pull
script).

Contract grain: a contract is a distinct (contractid, itemcode) pair from cube_Sale_APD (96.7% of
pairs -- 5245/5428 -- have exactly one row; the remainder are grouped, see `build_contracts`).
This is the grain the task asks for, and it is the natural "who bought what" unit: jobcode/qty are
recorded per (contractid, itemcode) line, and Cube_CES's (ContractID, ItemCode) pair is the join
key back to that same line.

Link test: a contract links to cube_final if EITHER (a) any token in its cube_Sale_APD `jobcode`
(comma-split) is in cube_final's jobno set, OR (b) any token in the OLMJobCode value(s) of its
matching Cube_CES row(s) (also comma-split -- see Part 2, this is a deviation from the task's
"single token" assumption, found in the data: 5.4% of populated OLMJobCode values are
comma-lists) is in that same jobno set.

Privacy note: this task's instructions forbid contract IDs (and customer/employee names) in
anything written to output/summary. `contractid`/`ContractID` are used here ONLY as an in-memory
join key during this script's run -- the raw CSVs this script reads (saved by
phase25_explorer1_pull.py) have `contractid`/`ContractID` already dropped before being written to
disk. Re-running this exact script against those same saved CSVs will therefore KeyError; it is
kept in the repo as a record of the method used in this run, not as a script meant to be re-run
unchanged against the (privacy-stripped) files already on disk. A future re-run of this method
needs a fresh single-connection pull that keeps contractid/ContractID in memory for the join,
mirroring `phase25_explorer1_pull.py` before its privacy-stripping step.
"""
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("phase25_explorer1_analysis")

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "summary"
WINDOW_START = "2024-01-01"
# Latest available data date is 2026-09-23 (both pulls); today is 2026-09-25, so September 2026
# is a partial month -- reported separately, not treated as a complete month for trend reading.
LATEST_COMPLETE_MONTH_END = "2026-08-31"
CHANGE_POINT = "2024-10-01"  # established change point per DATA_MAP.md Sec.7 (last dual-channel
                              # batch final_date 2024-10-03; zero from Nov 2024 onward)


def split_tokens(value):
    if pd.isna(value):
        return set()
    return {t.strip() for t in str(value).split(",") if t.strip()}


def load():
    cf = pd.read_csv(OUT_DIR / "phase25_explorer1_cube_final_raw.csv")
    ces = pd.read_csv(OUT_DIR / "phase25_explorer1_cube_ces_raw.csv")
    sa = pd.read_csv(OUT_DIR / "phase25_explorer1_sale_apd_raw.csv")
    sa["createDate"] = pd.to_datetime(sa["createDate"], errors="coerce")
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    return cf, ces, sa


def build_contracts(sa):
    """Groups cube_Sale_APD rows to the (contractid, itemcode) grain. jobcode tokens are unioned
    across a group's rows (a contract-item can have more than one row/tranche, each with its own
    jobcode value); createDate is the group's earliest row (when the contract-item line was first
    created); qty is summed; revenue_type/status are reported as the set of values seen (flagged
    if more than one -- same contract-item should not mix channels, and if it does that is a data
    finding, not silently resolved here).
    """
    def agg(g):
        jobcode_tokens = set()
        for v in g["jobcode"]:
            jobcode_tokens |= split_tokens(v)
        rev_types = set(g["revenue_type"].dropna().unique())
        statuses = set(g["status"].dropna().unique())
        return pd.Series({
            "createDate": g["createDate"].min(),
            "qty": g["qty"].sum(),
            "jobcode_tokens": jobcode_tokens,
            "n_rows": len(g),
            "revenue_types": rev_types,
            "revenue_type": sorted(rev_types)[0] if len(rev_types) == 1 else "MIXED:" + "|".join(sorted(rev_types)),
            "statuses": statuses,
        })

    contracts = sa.groupby(["contractid", "itemcode"], dropna=False).apply(agg).reset_index()
    n_mixed = (contracts["revenue_type"].str.startswith("MIXED:")).sum()
    logger.info("Built %d contract-item pairs from %d cube_Sale_APD rows (%d pairs with >1 row; "
                "%d pairs mix revenue_type across their own rows -- reported as MIXED, not "
                "resolved).", len(contracts), len(sa), (contracts["n_rows"] > 1).sum(), n_mixed)
    return contracts


def attach_olmjobcode(contracts, ces):
    """For each (contractid, itemcode) pair, the set of OLMJobCode tokens (comma-split) found
    across ALL matching Cube_CES rows (join on ContractID=contractid, ItemCode=itemcode,
    unbounded time -- a batch reference can predate the specific delivery row it is attached to).
    """
    ces_local = ces.dropna(subset=["OLMJobCode"]).copy()
    ces_local["tokens"] = ces_local["OLMJobCode"].apply(split_tokens)
    grp = ces_local.groupby(["ContractID", "ItemCode"])["tokens"].apply(
        lambda s: set().union(*s) if len(s) else set()
    )
    grp = grp.rename("olm_tokens").reset_index()
    grp = grp.rename(columns={"ContractID": "contractid", "ItemCode": "itemcode"})
    merged = contracts.merge(grp, on=["contractid", "itemcode"], how="left")
    merged["olm_tokens"] = merged["olm_tokens"].apply(lambda v: v if isinstance(v, set) else set())
    n_have_ces_match = (merged["olm_tokens"].apply(len) > 0).sum()
    logger.info("%d/%d contract-item pairs have >=1 matching Cube_CES row with a populated "
                "OLMJobCode.", n_have_ces_match, len(merged))
    return merged


def compute_links(merged, jobno_set):
    merged["linked_via_jobcode"] = merged["jobcode_tokens"].apply(
        lambda s: bool(s & jobno_set))
    merged["linked_via_olmjobcode"] = merged["olm_tokens"].apply(
        lambda s: bool(s & jobno_set))
    merged["linked"] = merged["linked_via_jobcode"] | merged["linked_via_olmjobcode"]
    return merged


def monthly_channel_table(merged):
    df = merged.dropna(subset=["createDate"]).copy()
    df = df[df["createDate"] >= WINDOW_START]
    df["month"] = df["createDate"].dt.to_period("M").astype(str)
    df["is_partial_month"] = df["createDate"] > pd.Timestamp(LATEST_COMPLETE_MONTH_END)

    two_channel = df[df["revenue_type"].isin(["Omni Channel", "Tendering"])].copy()
    other = df[~df["revenue_type"].isin(["Omni Channel", "Tendering"])].copy()

    def agg(g):
        return pd.Series({
            "n_contracts": len(g),
            "n_linked": g["linked"].sum(),
            "link_rate_count": g["linked"].mean(),
            "n_linked_via_jobcode": g["linked_via_jobcode"].sum(),
            "n_linked_via_olmjobcode": g["linked_via_olmjobcode"].sum(),
            "qty_total": g["qty"].sum(),
            "qty_linked": g.loc[g["linked"], "qty"].sum(),
            "link_rate_qty": (g.loc[g["linked"], "qty"].sum() / g["qty"].sum()
                               if g["qty"].sum() > 0 else float("nan")),
        })

    table = two_channel.groupby(["month", "revenue_type"]).apply(agg).reset_index()
    table = table.sort_values(["revenue_type", "month"])

    other_summary = other.groupby("revenue_type").agg(
        n_contracts=("linked", "size"),
        qty_total=("qty", "sum"),
    ).reset_index()
    total_value_all = df["qty"].sum()
    other_summary["qty_share_of_all"] = other_summary["qty_total"] / total_value_all if total_value_all else float("nan")

    return table, other_summary, df


def format_check(sa, ces, cf):
    """Part 2: format of jobcode/OLMJobCode tokens before vs after the established Oct/Nov 2024
    change point (DATA_MAP.md Sec.7). Reports token length, prefix (first 2 chars), separator,
    and tokens-per-contract, with concrete before/after samples.
    """
    lines = []

    # --- cube_Sale_APD.jobcode, split by createDate ---
    sa2 = sa.dropna(subset=["jobcode"]).copy()
    sa2["tokens"] = sa2["jobcode"].apply(lambda v: [t.strip() for t in str(v).split(",") if t.strip()])
    sa2["n_tokens"] = sa2["tokens"].apply(len)
    before = sa2[sa2["createDate"] < CHANGE_POINT]
    after = sa2[sa2["createDate"] >= CHANGE_POINT]

    def token_stats(sub, label):
        all_tokens = [t for toks in sub["tokens"] for t in toks]
        lens = pd.Series([len(t) for t in all_tokens])
        prefixes = pd.Series([t[:2] for t in all_tokens if len(t) >= 2])
        has_comma = (sub["n_tokens"] > 1).mean() if len(sub) else float("nan")
        lines.append(f"  {label}: {len(sub)} rows, {len(all_tokens)} tokens")
        lines.append(f"    token length distribution: {lens.value_counts().sort_index().to_dict()}")
        lines.append(f"    prefix (first 2 chars) distribution: {prefixes.value_counts().to_dict()}")
        lines.append(f"    rows with >1 token (comma-separated): {has_comma:.4f}" if pd.notna(has_comma) else "    rows with >1 token: n/a")
        lines.append(f"    n_tokens per row distribution: {sub['n_tokens'].value_counts().sort_index().to_dict()}")
        lines.append(f"    sample values: {sub['jobcode'].sample(min(8, len(sub)), random_state=1).tolist() if len(sub) else []}")
        return lens, prefixes

    lines.append("cube_Sale_APD.jobcode, split at createDate " + CHANGE_POINT + ":")
    len_before, pfx_before = token_stats(before, "BEFORE")
    len_after, pfx_after = token_stats(after, "AFTER")

    # --- Cube_CES.OLMJobCode, split by CtrDate ---
    ces2 = ces.dropna(subset=["OLMJobCode"]).copy()
    ces2["tokens"] = ces2["OLMJobCode"].apply(lambda v: [t.strip() for t in str(v).split(",") if t.strip()])
    ces2["n_tokens"] = ces2["tokens"].apply(len)
    ces_before = ces2[ces2["CtrDate"] < CHANGE_POINT]
    ces_after = ces2[ces2["CtrDate"] >= CHANGE_POINT]

    lines.append("")
    lines.append("Cube_CES.OLMJobCode, split at CtrDate " + CHANGE_POINT + ":")

    def ces_token_stats(sub, label):
        all_tokens = [t for toks in sub["tokens"] for t in toks]
        lens = pd.Series([len(t) for t in all_tokens])
        prefixes = pd.Series([t[:2] for t in all_tokens if len(t) >= 2])
        has_comma = (sub["n_tokens"] > 1).mean() if len(sub) else float("nan")
        lines.append(f"  {label}: {len(sub)} rows, {len(all_tokens)} tokens")
        lines.append(f"    token length distribution: {lens.value_counts().sort_index().to_dict()}")
        lines.append(f"    prefix (first 2 chars) distribution: {prefixes.value_counts().to_dict()}")
        lines.append(f"    rows with >1 token (comma-separated): {has_comma:.4f}" if pd.notna(has_comma) else "    rows with >1 token: n/a")
        lines.append(f"    sample values: {sub['OLMJobCode'].sample(min(8, len(sub)), random_state=1).tolist() if len(sub) else []}")

    ces_token_stats(ces_before, "BEFORE")
    ces_token_stats(ces_after, "AFTER")

    # --- cube_final.jobno, split by final_date, for reference ---
    cf2 = cf.dropna(subset=["jobno"]).copy()
    cf2["final_date"] = pd.to_datetime(cf2["final_date"], errors="coerce")
    cf_before = cf2[cf2["final_date"] < CHANGE_POINT]
    cf_after = cf2[cf2["final_date"] >= CHANGE_POINT]
    lines.append("")
    lines.append("cube_final.jobno, split at final_date " + CHANGE_POINT + " (for reference):")
    for sub, label in [(cf_before, "BEFORE"), (cf_after, "AFTER")]:
        lens = sub["jobno"].astype(str).str.len()
        prefixes = sub["jobno"].astype(str).str[:2]
        lines.append(f"  {label}: {len(sub)} rows")
        lines.append(f"    token length distribution: {lens.value_counts().sort_index().to_dict()}")
        lines.append(f"    prefix (first 2 chars) distribution: {prefixes.value_counts().to_dict()}")
        lines.append(f"    sample values: {sub['jobno'].sample(min(8, len(sub)), random_state=1).tolist() if len(sub) else []}")

    return "\n".join(lines)


def main():
    cf, ces, sa = load()
    jobno_set = set(cf["jobno"].dropna().astype(str).unique())
    logger.info("cube_final jobno set: %d distinct values (all-time, PEM107 item scope).", len(jobno_set))

    contracts = build_contracts(sa)
    merged = attach_olmjobcode(contracts, ces)
    merged = compute_links(merged, jobno_set)

    table, other_summary, df_all = monthly_channel_table(merged)

    # Drop set/collection columns before saving to CSV (not serialisable usefully).
    save_cols = [c for c in merged.columns if c not in ("jobcode_tokens", "olm_tokens", "revenue_types", "statuses")]
    merged[save_cols].to_csv(OUT_DIR / "phase25_explorer1_contract_link_detail.csv", index=False)
    table.to_csv(OUT_DIR / "phase25_explorer1_monthly_link_rate.csv", index=False)
    other_summary.to_csv(OUT_DIR / "phase25_explorer1_other_revenue_type_summary.csv", index=False)

    fmt_report = format_check(sa, ces, cf)
    with open(OUT_DIR / "phase25_explorer1_format_check.txt", "w", encoding="utf-8") as f:
        f.write(fmt_report)

    logger.info("Monthly link-rate table (Omni Channel / Tendering):\n%s", table.to_string())
    logger.info("Other revenue_type summary:\n%s", other_summary.to_string())
    logger.info("Format check:\n%s", fmt_report)

    # Before/after overall link rate summary (count and qty), pooled across the two channels,
    # split at the established change point, for the headline verdict.
    df_all["before_after"] = df_all["createDate"].apply(lambda d: "before_2024-10" if d < pd.Timestamp(CHANGE_POINT) else "on_or_after_2024-10")
    ba = df_all[df_all["revenue_type"].isin(["Omni Channel", "Tendering"])].groupby(["before_after", "revenue_type"]).apply(
        lambda g: pd.Series({
            "n_contracts": len(g),
            "n_linked": g["linked"].sum(),
            "link_rate_count": g["linked"].mean(),
            "qty_total": g["qty"].sum(),
            "qty_linked": g.loc[g["linked"], "qty"].sum(),
            "link_rate_qty": g.loc[g["linked"], "qty"].sum() / g["qty"].sum() if g["qty"].sum() > 0 else float("nan"),
        })
    ).reset_index()
    ba.to_csv(OUT_DIR / "phase25_explorer1_before_after_summary.csv", index=False)
    logger.info("Before/after (2024-10) summary:\n%s", ba.to_string())


if __name__ == "__main__":
    main()
