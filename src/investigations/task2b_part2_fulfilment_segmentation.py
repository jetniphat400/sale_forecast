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

Week 3 additions (2026-10-06, METRICS.md Sec.23 "Added 2026-10-06"): the item universe is every forecast-status and placeholder item of the
six divisions (PEM104's items are business-confirmed made-to-order), and three definitions are added per item -- data_inconsistent,
no_production_in_system, too_little_data -- plus the mixed-item rule of Part 3 (`mixed_rule`, tested on known items before it is applied) and
the display label of each item (`class_label`). `run_from_pulls` computes everything from saved pulls (no database); the item-level file keeps
the classes of PEM101 and PEM107 forecast-status items (decisions of 2026-09-29 and 2026-10-05) and records the fresh recomputation beside them.

No customer_name/cusname column is pulled or printed anywhere in this script.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

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


# =====================================================================================================================
# Week 3 (2026-10-06): all six divisions, three new definitions, the mixed-item rule, display labels.
# =====================================================================================================================
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
ITEM_STATUS_FILE = os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv")
KEPT_CLASS_DIVISIONS = ["PEM101", "PEM107"]          # forecast-status items keep their class (decisions of 2026-09-29 and 2026-10-05)
NEVER_SOLD_PREFIX = "excluded - listed but never sold"   # status of six PEM101 codes: not in the universe
FORECAST_STATUS = "forecast"
LABEL_KEYS = ["stock_policy", "confirmed_to_order", "conflict", "mixed", "no_production_in_system", "too_little_data"]


def load_week3_config(path: str = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["week3_classification"]


def delivered_contracts_in_window(ces: pd.DataFrame, start: str) -> pd.Series:
    """Per item code, the number of distinct delivered (Status 'Actual') contracts with CtrDate on or after `start`."""
    d = ces.copy()
    d["CtrDate"] = pd.to_datetime(d["CtrDate"], errors="coerce")
    d = d[(d["Status"] == "Actual") & (d["CtrDate"] >= pd.Timestamp(start))]
    return d.groupby("ItemCode")["ContractID"].nunique()


def is_data_inconsistent(label, s1, s2, s3, s2_computable) -> bool:
    """The recorded label contradicts the observed behaviour: MTS while none of S1 to S3 holds, or MTO or ETO while all of them hold.
    When S2 cannot be computed the test uses S1 and S3 only, as the rest of Sec.23 does."""
    held = [bool(s1), bool(s3)] + ([bool(s2)] if s2_computable else [])
    if label == "MTS":
        return not any(held)
    if label in ("MTO", "ETO"):
        return all(held)
    return False


def delivered_lines(apd: pd.DataFrame, ces: pd.DataFrame) -> pd.DataFrame:
    """One row per delivered order line: the cube_Sale_APD line (status Actual, label manufacturing_type, createDate) joined to its Cube_CES
    delivery row on (contract, item, plan id) -- the key is unique on both sides -- with days = ActualDelDate - createDate; lines with negative
    days are dropped (as S3 drops them)."""
    a = apd[apd["status"] == "Actual"].copy()
    a["planid"] = pd.to_numeric(a["planid"], errors="coerce")
    c = ces[ces["Status"] == "Actual"].copy()
    c["PlanID"] = pd.to_numeric(c["PlanID"], errors="coerce")
    m = a.merge(c[["ContractID", "ItemCode", "PlanID", "ActualDelDate"]], left_on=["contractid", "itemcode", "planid"],
                right_on=["ContractID", "ItemCode", "PlanID"], how="inner")
    m["days"] = (pd.to_datetime(m["ActualDelDate"]) - pd.to_datetime(m["createDate"])).dt.days
    return m[m["days"] >= 0][["itemcode", "manufacturing_type", "days"]].reset_index(drop=True)


def mixed_item_stats(lines: pd.DataFrame, rule: dict) -> pd.DataFrame:
    """Part 3 rule per item (index itemcode): n_lines_mts, n_lines_order, median days of each, and mixed_by_rule. An item is mixed when it has at
    least `min_lines_each_kind` delivered lines of each kind, the MTS-labelled median is at most `stock_median_days_max`, the MTO- or ETO-labelled
    median is above `order_median_days_min`, and the medians differ by at least `min_median_gap_days`."""
    cols = ["n_lines_mts", "n_lines_order", "median_days_mts", "median_days_order", "mixed_by_rule"]
    rows = {}
    for code, g in lines.groupby("itemcode"):
        s = g.loc[g["manufacturing_type"] == "MTS", "days"]
        o = g.loc[g["manufacturing_type"].isin(["MTO", "ETO"]), "days"]
        ms, mo = (float(s.median()) if len(s) else np.nan), (float(o.median()) if len(o) else np.nan)
        enough = len(s) >= rule["min_lines_each_kind"] and len(o) >= rule["min_lines_each_kind"]
        mixed = bool(enough and ms <= rule["stock_median_days_max"] and mo > rule["order_median_days_min"]
                     and (mo - ms) >= rule["min_median_gap_days"])
        rows[code] = [int(len(s)), int(len(o)), ms, mo, mixed]
    return pd.DataFrame.from_dict(rows, orient="index", columns=cols)


def mixed_rule_known_test(stats: pd.DataFrame, known_codes, rule: dict) -> dict:
    """Tests the rule on items whose answer is known (stock_policy and confirmed_to_order items): how many it calls mixed. The rule is adopted only
    when that share is at most `max_share_of_known_items`."""
    known = list(known_codes)
    called = sum(bool(stats["mixed_by_rule"].get(c, False)) for c in known)
    share = called / len(known) if known else 0.0
    return {"n_known": len(known), "n_called_mixed": int(called), "share": share, "adopted": bool(share <= rule["max_share_of_known_items"])}


def mts_share_by_quantity(apd: pd.DataFrame, today: pd.Timestamp, months: int) -> pd.Series:
    """Per item, the MTS-labelled share of ordered quantity (Actual and MPS lines) with createDate in the last `months` months up to `today`."""
    a = apd.dropna(subset=["manufacturing_type"]).copy()
    a["createDate"] = pd.to_datetime(a["createDate"], errors="coerce")
    a = a[(a["createDate"] > today - pd.DateOffset(months=months)) & (a["createDate"] <= today)]
    tot = a.groupby("itemcode")["qty"].sum()
    mts = a[a["manufacturing_type"] == "MTS"].groupby("itemcode")["qty"].sum()
    return (mts.reindex(tot.index).fillna(0) / tot).where(tot > 0)


def display_label(cls: str, no_production: bool, too_little: bool, mixed: bool, kept_decided: bool) -> str:
    """The label an item shows on a page, in this order: no_production_in_system; a class decided by the user or by the business (PEM101 and
    PEM107 stock_policy or confirmed_to_order, PEM104) keeps its class; too_little_data; mixed; otherwise the Sec.23 class."""
    if no_production:
        return "no_production_in_system"
    if kept_decided:
        return cls
    if too_little:
        return "too_little_data"
    if mixed:
        return "mixed"
    return cls


def build_week3_item_level(universe: pd.DataFrame, label_df: pd.DataFrame, s1_df: pd.DataFrame, s2s3_df: pd.DataFrame, apd: pd.DataFrame,
                           ces: pd.DataFrame, bom_counts: dict, final_counts: dict, kept_class: dict, today: pd.Timestamp, w3: dict,
                           decisions: dict) -> tuple:
    """The full item-level table for every item of `universe` (columns code, division, status_category) and the Part 3 known-item test.
    `kept_class` maps code -> the class PEM101 and PEM107 forecast-status items keep; `bom_counts` and `final_counts` map item code ->
    number of Cube_BOM_Exact entries and cube_final records. Returns (table, mixed_test dict)."""
    m = universe.copy()
    m["itemcode"] = m["code"]
    m = m.merge(label_df, on="itemcode", how="left").merge(s1_df, on="itemcode", how="left").merge(s2s3_df, on="itemcode", how="left")
    m["class_recomputed"] = m.apply(classify_item, axis=1)
    keep = ((m["division"].isin(KEPT_CLASS_DIVISIONS)) & (m["status_category"] == FORECAST_STATUS) & m["code"].isin(list(kept_class))).to_numpy()
    m["class"] = np.where(keep, m["code"].map(kept_class), m["class_recomputed"])
    m.loc[m["division"] == "PEM104", "class"] = "confirmed_to_order"      # METRICS.md Sec.23: PEM104, every item confirmed_to_order, level A
    # class_used: the class on top of which the user's per-item decisions of 2026-10-05 (config fulfilment_class_decisions) are applied, as the
    # pages read it; `class` stays the Sec.23 result (the existing tests count it)
    import build_inventory_page_data as bd
    decided = bd.apply_class_decisions(m[["division", "code", "class"]], decisions)
    m["class_used"] = decided["class"].to_numpy()
    m["class_basis"] = np.where(keep, np.where(decided["class_basis"].to_numpy() != "", "user_decision", "kept_rule_class"),
                                np.where(m["division"] == "PEM104", "business_confirmed", "rule"))
    ndel = delivered_contracts_in_window(ces, w3["analysis_window_start"])
    m["n_delivered_window"] = m["code"].map(ndel).fillna(0).astype(int)
    m["too_little_data"] = m["n_delivered_window"] < w3["min_delivered_contracts"]
    m["data_inconsistent"] = [is_data_inconsistent(r.label, r.S1, r.S2, r.S3, bool(r.S2_computable)) for r in m.itertuples()]
    m["n_bom_entries"] = m["code"].map(bom_counts).fillna(0).astype(int)
    m["n_cube_final_records"] = m["code"].map(final_counts).fillna(0).astype(int)
    m["no_production_in_system"] = (m["n_bom_entries"] == 0) & (m["n_cube_final_records"] == 0)
    rule = w3["mixed_rule"]
    stats = mixed_item_stats(delivered_lines(apd, ces), rule)
    m = m.merge(stats, left_on="code", right_index=True, how="left")
    m["n_lines_mts"] = m["n_lines_mts"].fillna(0).astype(int)
    m["n_lines_order"] = m["n_lines_order"].fillna(0).astype(int)
    m["mixed_by_rule"] = m["mixed_by_rule"].map(lambda x: bool(x) if pd.notna(x) else False)
    stock_or_order = m["class_used"].isin(["stock_policy", "confirmed_to_order"]).to_numpy()
    known_codes = m.loc[keep & stock_or_order, "code"].tolist()
    test = mixed_rule_known_test(stats, known_codes, rule)
    rule_derived = m.loc[keep & stock_or_order & (m["class_recomputed"] == m["class"]).to_numpy(), "code"].tolist()
    test["n_known_rule_derived"] = len(rule_derived)
    test["n_called_mixed_rule_derived"] = int(sum(bool(stats["mixed_by_rule"].get(c, False)) for c in rule_derived))
    target = ((m["class_used"] == "conflict") | (m["label"] == "mixed")).to_numpy()
    kept_decided = (keep & stock_or_order) | (m["division"] == "PEM104").to_numpy()
    called = bool(test["adopted"]) & m["mixed_by_rule"].to_numpy() & target
    m["mixed_applied"] = called & ~kept_decided          # an item whose class the user or the business decided keeps it, even when the rule calls it mixed
    share = mts_share_by_quantity(apd, today, rule["share_window_months"])
    m["mts_share_12m"] = np.where(called, m["code"].map(share), np.nan)      # recorded for every item the rule calls mixed, kept ones included
    m["class_label"] = [display_label(c, bool(n), bool(t), bool(x), bool(k)) for c, n, t, x, k in
                        zip(m["class_used"], m["no_production_in_system"], m["too_little_data"], m["mixed_applied"], kept_decided)]
    return m, test


def too_little_data_counts(table: pd.DataFrame, report_at: list) -> dict:
    """Counts per division of items with fewer delivered contracts than each value in `report_at` (the section's 3 and its neighbours 2 and 5)."""
    return {k: (table["n_delivered_window"] < k).groupby(table["division"]).sum().astype(int).to_dict() for k in report_at}


def universe_from_status(status: pd.DataFrame) -> pd.DataFrame:
    """Every forecast-status and placeholder item of the six divisions plus PEM104's items (item status file of phase C); the PEM101 codes
    listed but never sold are left out and counted by the caller. Columns code, division, status_category ('forecast' for every forecast-status
    row, the file's own text otherwise)."""
    s = status[~status["status_category"].str.startswith(NEVER_SOLD_PREFIX)].copy()
    s["itemcode"] = s["itemcode"].astype(str).str.strip()
    s["status_category"] = np.where(s["status_category"].str.startswith(FORECAST_STATUS), FORECAST_STATUS, s["status_category"])
    return s.rename(columns={"itemcode": "code"})[["code", "division", "status_category"]].drop_duplicates("code").reset_index(drop=True)


CLASS_EVIDENCE_NAMES = ("p2_apd", "p2_ces", "p2_final", "p2_inv", "p4_bom")


def class_evidence_codes() -> list:
    """The item codes the class evidence is pulled for: every item of the universe (forecast-status and placeholder items, PEM104's items)."""
    return sorted(universe_from_status(pd.read_csv(ITEM_STATUS_FILE))["code"])


def pull_class_evidence(codes: list) -> dict:
    """The five pulls METRICS.md Sec.23 needs, for `codes`, through the open database session (db.run_query; the caller owns the session; read-only):
    cube_Sale_APD lines (Omni Channel, Actual and MPS, createDate from the analysis window start), every Cube_CES row of the items, cube_final rows,
    Cube_Inventory_Exact stock and Cube_BOM_Exact rows. Returns {name: DataFrame} for CLASS_EVIDENCE_NAMES."""
    from db import run_query
    w3 = load_week3_config()
    lst = "','".join(sorted(str(c).replace("'", "") for c in codes))
    sale = SALE_TABLE
    return {
        "p2_apd": run_query(f"SELECT itemcode, manufacturing_type, qty, createDate, contractid, planid, status, forecast_date, revenue_type FROM {sale} "
                            f"WHERE itemcode IN ('{lst}') AND revenue_type = '{REVENUE_TYPE}' AND status IN ('Actual','MPS') AND createDate >= '{w3['analysis_window_start']}'"),
        "p2_ces": run_query(f"SELECT ItemCode, ContractID, PlanID, Status, CtrDate, ForecastDelDate, PlanDelDate, ActualDelDate, OLMJobCode, ActualQty, BacklogQty, PlanQty, "
                            f"RevenueType FROM Cube_CES WHERE ItemCode IN ('{lst}')"),
        "p2_final": run_query(f"SELECT itemcode, jobno, ctrno, final_date, transfer_qty, job_qty, division FROM cube_final WHERE itemcode IN ('{lst}')"),
        "p2_inv": run_query(f"SELECT warehouse, itemcode, stock, freestock, tobe_received, unit, timestamp FROM Cube_Inventory_Exact WHERE itemcode IN ('{lst}')"),
        "p4_bom": run_query(f"SELECT ItemFG, ItemRawmat, Quantity, Unit, Sequenceno, Type, Status, Warehouse, Division, ItemGroup, version, [Timestamp] FROM Cube_BOM_Exact "
                            f"WHERE ItemFG IN ('{lst}')"),
    }


def run_from_pulls(pull_dir: str, out_item_level: str = OUT_ITEM_LEVEL, today: pd.Timestamp = None, write: bool = True) -> dict:
    """The week 3 item-level table from the five class-evidence pulls saved as csv files in `pull_dir` (p2_apd.csv, p2_ces.csv, p2_final.csv, p2_inv.csv,
    p4_bom.csv); see run_from_frames."""
    frames = {n: pd.read_csv(os.path.join(pull_dir, n + ".csv")) for n in CLASS_EVIDENCE_NAMES}
    return run_from_frames(frames, out_item_level, today, write)


def run_from_frames(frames: dict, out_item_level: str = OUT_ITEM_LEVEL, today: pd.Timestamp = None, write: bool = True) -> dict:
    """Computes the week 3 item-level table from the class-evidence frames (no database). The classes of PEM101 and PEM107 forecast-status items are read from
    the existing item-level file and kept. Returns a dict with the table, the mixed-rule test, the too-little-data counts, the threshold sensitivity
    (recomputed classes, every division) and the number of PEM101 codes listed but never sold."""
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.today().normalize()
    w3 = load_week3_config()
    apd, ces, cf, inv, bom = (frames[n].copy() for n in CLASS_EVIDENCE_NAMES)
    status = pd.read_csv(ITEM_STATUS_FILE)
    universe = universe_from_status(status)
    codes = sorted(universe["code"])
    prev = pd.read_csv(out_item_level)
    prev = prev[prev["division"].isin(KEPT_CLASS_DIVISIONS)]
    if "status_category" in prev.columns:
        prev = prev[prev["status_category"] == FORECAST_STATUS]
    kept_class = prev.set_index("code")["class"].to_dict()
    label_df = compute_label(apd, codes, MIXED_THRESHOLD)
    inv["stock"] = pd.to_numeric(inv["stock"], errors="coerce")
    s1 = pd.DataFrame({"itemcode": codes})
    s1["total_stock"] = s1["itemcode"].map(inv.groupby("itemcode")["stock"].sum()).fillna(0.0)
    s1["S1"] = s1["total_stock"] > 0
    s2s3 = compute_s2_s3(ces, cf, codes, S2_THRESHOLD, S3_THRESHOLD_DAYS)
    bom_counts = bom.assign(ItemFG=bom["ItemFG"].astype(str).str.strip()).groupby("ItemFG").size().to_dict()
    final_counts = cf.assign(itemcode=cf["itemcode"].astype(str).str.strip()).groupby("itemcode").size().to_dict()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        decisions = yaml.safe_load(f).get("fulfilment_class_decisions", {})
    table, test = build_week3_item_level(universe, label_df, s1, s2s3, apd, ces, bom_counts, final_counts, kept_class, today, w3, decisions)
    pl = load_visible_product_rows(os.path.join(REFERENCE_DIR, "pricelist.xlsx"))[["code", "business", "category", "type", "description"]]
    table = table.merge(pl.drop_duplicates("code"), on="code", how="left")
    out = {"table": table, "mixed_test": test, "too_little_counts": too_little_data_counts(table, w3["min_delivered_contracts_report_at"]),
           "thresholds": threshold_sensitivity(universe, apd, s1, ces, cf, codes),
           "n_never_sold": int(status["status_category"].str.startswith(NEVER_SOLD_PREFIX).sum())}
    if write:
        table.to_csv(out_item_level, index=False)
        # the class counts and the threshold sensitivity files cover every division now (class_used: the class the pages read)
        table.groupby(["division", "class_used"]).size().unstack(fill_value=0).to_csv(OUT_CLASS_COUNTS)
        out["thresholds"].to_csv(OUT_THRESHOLD_SENSITIVITY, index=False)
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
