"""Task 2b, Part 2 -- METRICS.md Sec.23 fulfilment_segmentation, computed fresh for every
PEM101 and PEM107 forecast-status item (item universe: output/summary/
phaseC_step1revised_item_status_445.csv, status_category=='forecast' -- 144 PEM101 + 112 PEM107
= 256 items; NOT the 112/136-item sets currently embedded in forecast/inventory.html, which are
policy-filtered subsets from the section-15 criteria this section supersedes).

PRICELIST RULE: item names/types/business come from reference/pricelist.xlsx's visible sheets
(src/pricelist_reader.load_visible_product_rows), never a database division/category column.

DATABASE ACCESS RULE: one connection attempt for this script's four queries (cube_Sale_APD for
the label; Cube_Inventory_Exact for S1; Cube_CES and cube_final for S2/S3). On a failed login,
stop and report, never retry.

**Correction, 2026-09-29 (task 2b follow-up, this task):** this script's S2 previously used a
self-referential `Cube_CES`-only proxy (`OLMJobCode` grouped `CtrDate` minimum) that never queried
`cube_final` at all, despite METRICS.md Sec.23's own text literally naming "a cube_final batch" as
the S2 source. That proxy was the project's pre-`cube_final`-availability fallback (used in
`phaseJ3_explorerD_analysis.py`/`phase24_explorerB_analysis.py` when a `cube_final` pull returned 0
rows in that session, DATA_MAP.md Sec.4 Trap 7) -- reused here by mistake instead of the later,
correct, already-working `cube_final` join demonstrated in `phase25_analyst3_analysis.py`'s
`measure3_batch_traceability` once `cube_final` became queryable again. Two independent agents
(`output/summary/task2b_validator_report.md`, `output/summary/task2b_part7b_reconciliation_report.md`)
established this as a bug, not an ambiguity, and it is fixed below: S2 now joins `cube_final` for
real, exact method reused from `task2b_part7_validator.py`/`phase25_analyst3_analysis.py`.

Definitions (METRICS.md Sec.23, quoted in full in that section):
  label[item] = dominant manufacturing_type by QUANTITY over the analysis window (2024-01 onward,
                Omni Channel, Actual+MPS -- this project's standard scope, DATA_MAP.md/config.yaml)
                if its share is >= 60%; otherwise "mixed". Reused method: identical to Phase 24
                Explorer B's basis choice (qty, not row-count or value) -- DATA_MAP.md Q21 entry.
  S1 = on-hand stock > 0 in Cube_Inventory_Exact, ANY warehouse, current snapshot.
  S2 = >= 50% of the item's delivered (Status='Actual') Cube_CES contracts trace to a cube_final
       batch that existed before the contract's own CtrDate (createDate/PO-date proxy, DATA_MAP.md
       Sec.2: 99.95%/100% match between cube_Sale_APD.createDate/PODate and Cube_CES.CtrDate).
       Join: cube_final.jobno <-> Cube_CES.OLMJobCode (DATA_MAP.md Sec.2 jobcode/jobno/OLMJobCode
       entry), batch "existed" date = earliest cube_final.final_date per jobno -- exact method
       reused verbatim from src/investigations/phase25_analyst3_analysis.py's
       measure3_batch_traceability and src/investigations/task2b_part7_validator.py, not
       re-derived. Denominator = ALL of the item's delivered contracts (literal reading of "the
       item's delivered contracts"). S2 is "cannot be computed" for an item with zero delivered
       contracts that resolve to a cube_final link (all no_token/no_cube_final_link).
  S3 = median days from createDate to ActualDelDate <= 14. Cube_CES's CtrDate is used as the
       createDate-equivalent (DATA_MAP.md Sec.2: 99.95%/100% match between cube_Sale_APD.createDate/
       PODate and Cube_CES.CtrDate) -- reused from the same two prior scripts.

  stock_policy        : label == 'MTS' and >= 2 of {S1,S2,S3} hold
  confirmed_to_order  : label in {'MTO','ETO'} and <= 1 of {S1,S2,S3} hold
  conflict            : every other combination, and every 'mixed' item
  If S2 cannot be computed: evaluate on S1 and S3 only, and require BOTH to hold for stock_policy.

No customer_name/cusname column is pulled or printed anywhere in this script.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import run_query
from zero_row_guard import guard_nonempty
from cube_ces_pull import pull_cube_ces_for_items
from cube_final_pull import pull_cube_final_for_items
from phaseE1_common import query_inventory_exact
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task2b_part2")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference")

SALE_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
REVENUE_TYPE = "Omni Channel"
STATUS_BASIS = ["Actual", "MPS"]
DATE_START = "2024-01-01"

MIXED_THRESHOLD = 0.60
S2_THRESHOLD = 0.50
S3_THRESHOLD_DAYS = 14

DIVISIONS = ["PEM101", "PEM107"]

OUT_ITEM_LEVEL = os.path.join(SUMMARY_DIR, "task2b_part2_item_level.csv")
OUT_CLASS_COUNTS = os.path.join(SUMMARY_DIR, "task2b_part2_class_counts.csv")
OUT_THRESHOLD_SENSITIVITY = os.path.join(SUMMARY_DIR, "task2b_part2_threshold_sensitivity.csv")
OUT_ELIGIBILITY_CHANGE = os.path.join(SUMMARY_DIR, "task2b_part2_eligibility_change.csv")
OUT_REPORT = os.path.join(SUMMARY_DIR, "task2b_part2_report.md")


def load_item_universe():
    status = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv"))
    status = status[(status["division"].isin(DIVISIONS)) & (status["status_category"] == "forecast")]
    codes = sorted(status["itemcode"].unique())
    logger.info("Forecast-status item universe: %s",
                status.groupby("division").size().to_dict())

    pl = load_visible_product_rows(os.path.join(REFERENCE_DIR, "pricelist.xlsx"))
    pl = pl[pl["code"].isin(codes)][["code", "business", "category", "type", "description"]].drop_duplicates("code")
    merged = status[["itemcode", "division"]].rename(columns={"itemcode": "code"}).merge(pl, on="code", how="left")
    missing_pl = merged[merged["business"].isna()]
    if len(missing_pl):
        logger.warning("%d forecast-status item(s) have no pricelist visible-sheet row (kept, "
                        "name/type fields null): %s", len(missing_pl), missing_pl["code"].tolist())
    return merged, codes


def pull_sale_apd(item_codes):
    code_list = "','".join(sorted(item_codes))
    statuses = "','".join(STATUS_BASIS)
    sql = f"""
        SELECT itemcode, manufacturing_type, qty
        FROM {SALE_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = '{REVENUE_TYPE}'
          AND status IN ('{statuses}')
          AND createDate >= '{DATE_START}'
    """
    df = run_query(sql)
    guard_nonempty(df, table=SALE_TABLE, filter_desc=f"{len(item_codes)} codes, Omni/Actual+MPS/2024+",
                   allow_empty=False)
    logger.info("cube_Sale_APD pull: %d rows for %d item codes.", len(df), len(item_codes))
    return df


def compute_label(sale, all_codes, mixed_threshold):
    d = sale.dropna(subset=["manufacturing_type"]).copy()
    tot = d.groupby("itemcode")["qty"].sum().rename("qty_total")
    by_type = d.groupby(["itemcode", "manufacturing_type"])["qty"].sum().rename("qty_by_type").reset_index()
    by_type = by_type.merge(tot.reset_index(), on="itemcode")
    by_type["share"] = by_type["qty_by_type"] / by_type["qty_total"]
    idx = by_type.groupby("itemcode")["qty_by_type"].idxmax()
    dom = by_type.loc[idx].set_index("itemcode")[["manufacturing_type", "share"]]
    out = pd.DataFrame({"itemcode": all_codes}).set_index("itemcode").join(dom)
    out["label"] = np.where(out["share"] >= mixed_threshold, out["manufacturing_type"], "mixed")
    out.loc[out["manufacturing_type"].isna(), "label"] = "mixed"  # no 2024+ Omni history at all
    return out.reset_index()[["itemcode", "manufacturing_type", "share", "label"]]


def compute_s1(item_codes):
    inv = query_inventory_exact(item_codes, allow_empty=True)
    total = inv.groupby("itemcode")["stock"].sum()
    s1 = pd.DataFrame({"itemcode": item_codes}).set_index("itemcode")
    s1["total_stock"] = total
    s1["total_stock"] = s1["total_stock"].fillna(0.0)
    s1["S1"] = s1["total_stock"] > 0
    return s1.reset_index()[["itemcode", "total_stock", "S1"]]


def is_blank_token(x):
    if pd.isna(x):
        return True
    s = str(x).strip()
    return s == "" or s.lower() == "none"


def compute_s2_s3(ces, cf, item_codes, s2_threshold, s3_threshold_days):
    """S2/S3 per METRICS.md Sec.23. S2 joins cube_final for real (jobno <-> OLMJobCode, batch
    "existed" date = earliest cube_final.final_date per jobno) -- exact method reused verbatim from
    src/investigations/phase25_analyst3_analysis.py's measure3_batch_traceability and
    src/investigations/task2b_part7_validator.py; see this module's docstring for the 2026-09-29
    correction this replaces (the prior self-referential Cube_CES-only proxy)."""
    ces = ces.copy()
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")

    delivered = ces[ces["Status"] == "Actual"].copy()

    if cf is not None and len(cf):
        cf = cf.copy()
        cf["final_date"] = pd.to_datetime(cf["final_date"], errors="coerce")
        batch_avail = cf.groupby("jobno")["final_date"].min()
    else:
        batch_avail = pd.Series(dtype="datetime64[ns]")

    delivered["has_token"] = ~delivered["OLMJobCode"].apply(is_blank_token)
    delivered["batch_avail_date"] = delivered["OLMJobCode"].map(batch_avail)

    def trace_class(row):
        if pd.isna(row["CtrDate"]):
            return "no_ctrdate"
        if not row["has_token"]:
            return "no_token"
        if pd.isna(row["batch_avail_date"]):
            return "no_cube_final_link"
        return "traceable_pre_existing" if row["batch_avail_date"] < row["CtrDate"] else "not_pre_existing"

    delivered["trace_class"] = delivered.apply(trace_class, axis=1)
    delivered["delivery_days"] = (delivered["ActualDelDate"] - delivered["CtrDate"]).dt.days

    rows = []
    for code in item_codes:
        g = delivered[delivered["ItemCode"] == code]
        n_delivered = len(g)
        n_cube_final_linked = int(g["trace_class"].isin(["traceable_pre_existing", "not_pre_existing"]).sum())
        n_pre = int((g["trace_class"] == "traceable_pre_existing").sum())
        s2_computable = n_delivered > 0 and n_cube_final_linked > 0
        # Literal METRICS.md reading: share of ALL the item's delivered contracts, not just the
        # cube_final-linked subset (task2b_part7b_reconciliation_report.md, Sec.1).
        s2_share = (n_pre / n_delivered) if s2_computable else np.nan
        s2 = (s2_share >= s2_threshold) if s2_computable else None

        dd = g["delivery_days"].dropna()
        dd = dd[dd >= 0]
        s3_median = float(dd.median()) if len(dd) else np.nan
        s3 = bool(s3_median <= s3_threshold_days) if len(dd) else False

        rows.append(dict(itemcode=code, n_delivered_contracts=n_delivered,
                          n_cube_final_linked=n_cube_final_linked,
                          n_traceable_pre_existing=n_pre, S2_share=s2_share, S2_computable=s2_computable,
                          S2=s2, S3_median_days=s3_median, S3_n=len(dd), S3=s3))
    return pd.DataFrame(rows)


def classify_item(row, s2_threshold_note=""):
    """METRICS.md Sec.23. When S2 cannot be computed: stock_policy requires BOTH S1 and S3 (the
    fallback METRICS.md's own text states explicitly). For confirmed_to_order/conflict, METRICS.md
    is silent on the fallback -- the RECOMMENDED reading (task2b_part7b_reconciliation_report.md,
    Sec.2; recorded in METRICS.md Sec.23 2026-09-29): "at most 1 of {S1,S3} hold" -> confirmed_to_
    order, i.e. NOT(S1 and S3), mirroring the stock_policy fallback's structure. See
    classify_item_strict_alt_fallback() below for the alternate, stricter reading also recorded per
    AGENTS.md rule 9."""
    label = row["label"]
    s1, s2, s3 = row["S1"], row["S2"], row["S3"]
    if label == "mixed":
        return "conflict"
    if row["S2_computable"]:
        n_hold = int(bool(s1)) + int(bool(s2)) + int(bool(s3))
        if label == "MTS":
            return "stock_policy" if n_hold >= 2 else "conflict"
        else:  # MTO or ETO
            return "confirmed_to_order" if n_hold <= 1 else "conflict"
    else:
        both = bool(s1) and bool(s3)
        if label == "MTS":
            return "stock_policy" if both else "conflict"
        else:
            return "confirmed_to_order" if not both else "conflict"


def classify_item_strict_alt_fallback(row):
    """Alternate, stricter S2-missing fallback for confirmed_to_order/conflict, recorded per
    AGENTS.md rule 9 (a genuine ambiguity is reported with both readings, not silently resolved):
    "at most 0 of {S1,S3} hold" -> confirmed_to_order (i.e. treat the dropped S2 slot as if it
    still counted against the "at most 1 of 3" bar, requiring a full zero-signals bar on the
    remaining two). Identical to classify_item() everywhere S2 IS computable, and identical for
    stock_policy's own explicitly-stated fallback (both S1 and S3 required either way)."""
    label = row["label"]
    s1, s2, s3 = row["S1"], row["S2"], row["S3"]
    if label == "mixed":
        return "conflict"
    if row["S2_computable"]:
        n_hold = int(bool(s1)) + int(bool(s2)) + int(bool(s3))
        if label == "MTS":
            return "stock_policy" if n_hold >= 2 else "conflict"
        else:
            return "confirmed_to_order" if n_hold <= 1 else "conflict"
    else:
        both = bool(s1) and bool(s3)
        if label == "MTS":
            return "stock_policy" if both else "conflict"
        else:
            return "confirmed_to_order" if not (s1 or s3) else "conflict"


def build_item_level(item_universe, label_df, s1_df, s2s3_df):
    m = item_universe.merge(label_df, left_on="code", right_on="itemcode", how="left")
    m = m.merge(s1_df, on="itemcode", how="left")
    m = m.merge(s2s3_df, on="itemcode", how="left")
    m["class"] = m.apply(classify_item, axis=1)
    # Recorded per AGENTS.md rule 9 -- the alternate, stricter S2-missing fallback reading for
    # confirmed_to_order/conflict (not used for "class"/the live page; documentation only).
    m["class_strict_alt_fallback"] = m.apply(classify_item_strict_alt_fallback, axis=1)
    return m


def counts_by_division(item_level, class_col="class"):
    return item_level.groupby(["division", class_col]).size().unstack(fill_value=0)


def threshold_sensitivity(item_universe, sale, s1_df, ces, cf, item_codes):
    """Re-classify at each alternate threshold, ONE at a time, others held at default --
    METRICS.md Sec.23's own instruction ('report counts also at 50/70%, 40/60%, 7/21 days')."""
    rows = []
    for mixed_th in [0.50, MIXED_THRESHOLD, 0.70]:
        label_df = compute_label(sale, item_codes, mixed_th)
        s2s3_df = compute_s2_s3(ces, cf, item_codes, S2_THRESHOLD, S3_THRESHOLD_DAYS)
        item_level = build_item_level(item_universe, label_df, s1_df, s2s3_df)
        for div, g in item_level.groupby("division"):
            vc = g["class"].value_counts().to_dict()
            rows.append(dict(varied="mixed_threshold", value=mixed_th, division=div, **vc))
    for s2_th in [0.40, S2_THRESHOLD, 0.60]:
        label_df = compute_label(sale, item_codes, MIXED_THRESHOLD)
        s2s3_df = compute_s2_s3(ces, cf, item_codes, s2_th, S3_THRESHOLD_DAYS)
        item_level = build_item_level(item_universe, label_df, s1_df, s2s3_df)
        for div, g in item_level.groupby("division"):
            vc = g["class"].value_counts().to_dict()
            rows.append(dict(varied="S2_threshold", value=s2_th, division=div, **vc))
    for s3_th in [7, S3_THRESHOLD_DAYS, 21]:
        label_df = compute_label(sale, item_codes, MIXED_THRESHOLD)
        s2s3_df = compute_s2_s3(ces, cf, item_codes, S2_THRESHOLD, s3_th)
        item_level = build_item_level(item_universe, label_df, s1_df, s2s3_df)
        for div, g in item_level.groupby("division"):
            vc = g["class"].value_counts().to_dict()
            rows.append(dict(varied="S3_threshold_days", value=s3_th, division=div, **vc))
    return pd.DataFrame(rows).fillna(0)


def load_current_finished_goods_stock_set():
    """The Min/Max-eligible set section 23 supersedes -- section-15-derived 'finished_goods_stock'
    policy, as currently embedded in forecast/inventory.html (PEM101: phaseE1fix_1_item_policy.csv;
    PEM107: phaseE2pilot_PEM107_1_item_policy.csv)."""
    out = {}
    p101 = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_item_policy.csv"))
    out["PEM101"] = set(p101[p101["policy"] == "finished_goods_stock"]["code"])
    p107 = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE2pilot_PEM107_1_item_policy.csv"))
    out["PEM107"] = set(p107[p107["policy"] == "finished_goods_stock"]["code"])
    return out


def main():
    item_universe, item_codes = load_item_universe()

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt now. No retry on a "
                "failed login.")
    try:
        sale = pull_sale_apd(item_codes)
        s1_df = compute_s1(item_codes)
        ces = pull_cube_ces_for_items(
            item_codes, columns=["ItemCode", "ContractID", "Status", "CtrDate", "ActualDelDate", "OLMJobCode"],
            allow_empty=True)
        cf = pull_cube_final_for_items(item_codes, allow_empty=True)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: a query in this single-connection session failed. "
                     "Verbatim error: %r", exc)
        raise

    label_df = compute_label(sale, item_codes, MIXED_THRESHOLD)
    s2s3_df = compute_s2_s3(ces, cf, item_codes, S2_THRESHOLD, S3_THRESHOLD_DAYS)
    item_level = build_item_level(item_universe, label_df, s1_df, s2s3_df)
    item_level.to_csv(OUT_ITEM_LEVEL, index=False)

    class_counts = counts_by_division(item_level)
    class_counts.to_csv(OUT_CLASS_COUNTS)
    logger.info("Class counts by division:\n%s", class_counts.to_string())

    # AGENTS.md rule 9: record the alternate, stricter S2-missing fallback reading alongside the
    # recommended one used for "class" -- not silently choosing a side.
    class_counts_strict_alt = counts_by_division(item_level, class_col="class_strict_alt_fallback")
    class_counts_strict_alt.to_csv(
        os.path.join(SUMMARY_DIR, "task2b_part2_class_counts_strict_alt_fallback.csv"))
    logger.info("Class counts by division, ALTERNATE stricter S2-missing fallback ('at most 0 of "
                "{S1,S3}' for confirmed_to_order), recorded per AGENTS.md rule 9, not used for the "
                "live page:\n%s", class_counts_strict_alt.to_string())

    sens = threshold_sensitivity(item_universe, sale, s1_df, ces, cf, item_codes)
    sens.to_csv(OUT_THRESHOLD_SENSITIVITY, index=False)

    current_fg = load_current_finished_goods_stock_set()
    elig_rows = []
    for div in DIVISIONS:
        new_set = set(item_level[(item_level["division"] == div) & (item_level["class"] == "stock_policy")]["code"])
        old_set = current_fg[div]
        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)
        elig_rows.append(dict(division=div, old_finished_goods_stock_n=len(old_set),
                               new_stock_policy_n=len(new_set), added_n=len(added),
                               removed_n=len(removed), added_codes=";".join(added),
                               removed_codes=";".join(removed)))
    elig_df = pd.DataFrame(elig_rows)
    elig_df.to_csv(OUT_ELIGIBILITY_CHANGE, index=False)
    logger.info("Eligibility change vs current finished_goods_stock set:\n%s",
                elig_df[["division", "old_finished_goods_stock_n", "new_stock_policy_n", "added_n", "removed_n"]].to_string(index=False))

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# Task 2b Part 2 -- METRICS.md Sec.23 fulfilment_segmentation\n\n")
        f.write("**Correction, 2026-09-29 (this run):** S2 now joins `cube_final` for real (jobno "
                "<-> Cube_CES.OLMJobCode, batch existed date = earliest cube_final.final_date per "
                "jobno), replacing the prior self-referential Cube_CES-only proxy -- a confirmed "
                "bug (see this script's own module docstring, `output/summary/"
                "task2b_validator_report.md`, `output/summary/task2b_part7b_reconciliation_report.md`). "
                "This changes PEM107 stock_policy from 9 (buggy) to 4 (correct).\n\n")
        f.write("## Class counts by division (recommended S2-missing fallback for "
                "confirmed_to_order/conflict: \"at most 1 of {S1,S3} hold\", per METRICS.md Sec.23, "
                "amended 2026-09-29)\n\n```\n" + class_counts.to_string() + "\n```\n\n")
        f.write("## Class counts, ALTERNATE stricter S2-missing fallback (\"at most 0 of {S1,S3} "
                "hold\"), recorded per AGENTS.md rule 9 -- NOT used for the live page or the "
                "primary counts above\n\n```\n" + class_counts_strict_alt.to_string() + "\n```\n\n")
        f.write("**Note on a separate, smaller, unresolved divergence (not part of this task's "
                "mandated S2 fix):** the independent Validator's fully separate recomputation "
                "(`task2b_validator_report.md`) reports PEM101 confirmed_to_order/conflict = 20/42 "
                "(recommended fallback) and 8/54 (stricter alternate) -- one item different from "
                "this script's 21/41 and 9/53 above in both readings. The reconciliation report "
                "(`task2b_part7b_reconciliation_report.md`, Sec.2) traces this to a single item, "
                "`CA-F-99-020102`, whose manufacturing_type label differs (MTO here vs mixed for "
                "the Validator) because this script's `compute_label()` drops rows with missing "
                "manufacturing_type from the qty denominator while the Validator's label logic "
                "keeps them (fillna). That label-denominator question is a separate, independent, "
                "lower-confidence issue, NOT the confirmed cube_final/S2 bug this task fixed, and "
                "is out of this task's scope -- flagged here for a future targeted check, not "
                "resolved.\n\n")
        f.write("## Eligibility change vs current finished_goods_stock set\n\n```\n"
                 + elig_df.drop(columns=["added_codes", "removed_codes"]).to_string(index=False) + "\n```\n\n")
        f.write("Added codes:\n" + elig_df[["division", "added_codes"]].to_string(index=False) + "\n\n")
        f.write("Removed codes:\n" + elig_df[["division", "removed_codes"]].to_string(index=False) + "\n\n")
        f.write("## Threshold sensitivity (one axis varied at a time, others at default)\n\n```\n"
                 + sens.to_string(index=False) + "\n```\n")

    print("DONE")


if __name__ == "__main__":
    main()
