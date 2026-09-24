"""Phase 24 -- Explorer B -- analysis over already-pulled data (no further DB access).

Reads the three raw pulls from phase24_explorerB_pull.py and:
  Part 1: per-item manufacturing_type distribution (row count / qty / sale value bases), dominant
          type + share under each basis, "mixed" flag, per-division summary counts.
  Part 2: for every non-mixed item, tests whether its dominant label behaves as MTS/MTO/ETO's
          business-confirmed definition implies -- stock presence/qty, order notice
          (forecast_date - createDate), delivery time (ActualDelDate - CtrDate, Status='Actual'
          rows, Cube_CES; CtrDate used as the createDate-equivalent per DATA_MAP.md Sec.2's
          established 99.95% cube_Sale_APD.createDate <-> Cube_CES.CtrDate match), and
          batch-before-PO share (Cube_CES OLMJobCode reverse-traceability proxy, EXACTLY the method
          already established project-wide -- DATA_MAP.md Sec.2 jobcode/jobno/OLMJobCode entry,
          Sec.3 Joins' OLMJobCode row, reused from src/investigations/phaseJ3_explorerD_analysis.py
          rather than reinvented).
  Part 3: same four tests for PEM104, cross-checked against its business-confirmed "made to order"
          status (DATA_MAP.md Sec.7).

Dominance basis choice (stated per task instructions): QUANTITY is used as the PRIMARY basis for
the "mixed" flag and all downstream Part 2/3 tests. Reasoning: manufacturing_type is a
production-strategy decision made per unit of physical output, not per THB of order value (a single
high-value MTO order should not out-vote many small MTS units in characterising how an ITEM is
typically produced) and not per row (row count conflates order-splitting behaviour with actual
volume). Row-count and value bases are still computed and reported alongside, and any case where
they disagree with the quantity-based dominant type is flagged explicitly, per the task brief.

No customer_name/cusname value is printed or quoted anywhere in this script's output.
"""
import logging
import os

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase24_explorerB_analysis")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

SCOPE_FILE = os.path.join(SUMMARY_DIR, "phase24_explorerB_item_scope.csv")
SALE_FILE = os.path.join(SUMMARY_DIR, "phase24_explorerB_cube_sale_apd_raw.csv")
INV_FILE = os.path.join(SUMMARY_DIR, "phase24_explorerB_inventory_raw.csv")
CES_FILE = os.path.join(SUMMARY_DIR, "phase24_explorerB_cube_ces_raw.csv")

OUT_ITEM_DIST = os.path.join(SUMMARY_DIR, "phase24_explorerB_item_distribution.csv")
OUT_DIV_SUMMARY = os.path.join(SUMMARY_DIR, "phase24_explorerB_division_summary.csv")
OUT_MIXED_ITEMS = os.path.join(SUMMARY_DIR, "phase24_explorerB_mixed_items.csv")
OUT_STOCK_TEST = os.path.join(SUMMARY_DIR, "phase24_explorerB_stock_test.csv")
OUT_NOTICE_TEST = os.path.join(SUMMARY_DIR, "phase24_explorerB_notice_test.csv")
OUT_DELIVERY_TEST = os.path.join(SUMMARY_DIR, "phase24_explorerB_delivery_test.csv")
OUT_BATCH_TOKEN = os.path.join(SUMMARY_DIR, "phase24_explorerB_batch_tokens.csv")
OUT_BATCH_TEST = os.path.join(SUMMARY_DIR, "phase24_explorerB_batch_test.csv")
OUT_BEHAVIOR_ITEM = os.path.join(SUMMARY_DIR, "phase24_explorerB_behavior_per_item.csv")
OUT_BEHAVIOR_DIV = os.path.join(SUMMARY_DIR, "phase24_explorerB_behavior_per_division.csv")

MIXED_THRESHOLD = 0.60  # task brief: dominant share under 60% of the primary basis -> "mixed"
PRIMARY_BASIS = "qty"   # stated reasoning in module docstring


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else np.nan


def dist_stats(series):
    s = pd.Series(series).dropna()
    if len(s) == 0:
        return dict(n=0, median=np.nan, p25=np.nan, p75=np.nan, min=np.nan, max=np.nan, mean=np.nan)
    return dict(n=len(s), median=float(s.median()), p25=pct(s, 25), p75=pct(s, 75),
                min=float(s.min()), max=float(s.max()), mean=float(s.mean()))


# ------------------------------------------------------------------------------------------
# Part 1: distribution
# ------------------------------------------------------------------------------------------

def basis_dominant(df, basis_col, group_cols=("itemcode",)):
    """For each group, returns dominant manufacturing_type and its share of basis_col's total
    within that group (rows with a null manufacturing_type are dropped for this computation --
    they cannot be attributed to any type)."""
    d = df.dropna(subset=["manufacturing_type"]).copy()
    tot = d.groupby(list(group_cols))[basis_col].sum().rename("basis_total")
    by_type = d.groupby(list(group_cols) + ["manufacturing_type"])[basis_col].sum().rename("basis_value")
    by_type = by_type.reset_index().merge(tot.reset_index(), on=list(group_cols))
    by_type["share"] = by_type["basis_value"] / by_type["basis_total"]
    idx = by_type.groupby(list(group_cols))["basis_value"].idxmax()
    dom = by_type.loc[idx].set_index(list(group_cols))[["manufacturing_type", "share"]]
    return dom


def part1_distribution(sale, scope):
    item_div = scope.set_index("code")["division"].to_dict()

    n_null_mfg = int(sale["manufacturing_type"].isna().sum())
    logger.info("Part 1: %d of %d cube_Sale_APD rows have a null manufacturing_type (dropped from "
                "distribution attribution, kept in row totals for context).", n_null_mfg, len(sale))

    rows_dom = basis_dominant(sale, "qty", ("itemcode",)).rename(
        columns={"manufacturing_type": "dominant_by_rowcount", "share": "share_by_rowcount"})
    # row-count basis: use a constant column of 1s
    sale_rc = sale.copy()
    sale_rc["_one"] = 1
    rowcount_dom = basis_dominant(sale_rc, "_one", ("itemcode",)).rename(
        columns={"manufacturing_type": "dominant_by_rowcount", "share": "share_by_rowcount"})
    qty_dom = basis_dominant(sale, "qty", ("itemcode",)).rename(
        columns={"manufacturing_type": "dominant_by_qty", "share": "share_by_qty"})
    value_dom = basis_dominant(sale, "sale", ("itemcode",)).rename(
        columns={"manufacturing_type": "dominant_by_value", "share": "share_by_value"})

    all_items = sorted(sale["itemcode"].unique())
    out = pd.DataFrame({"itemcode": all_items}).set_index("itemcode")
    out = out.join(rowcount_dom).join(qty_dom).join(value_dom)
    out["division"] = out.index.map(item_div)

    out["bases_agree"] = (
        (out["dominant_by_rowcount"] == out["dominant_by_qty"]) &
        (out["dominant_by_qty"] == out["dominant_by_value"])
    )

    primary_col = {"qty": "dominant_by_qty", "rowcount": "dominant_by_rowcount",
                   "value": "dominant_by_value"}[PRIMARY_BASIS]
    primary_share_col = {"qty": "share_by_qty", "rowcount": "share_by_rowcount",
                          "value": "share_by_value"}[PRIMARY_BASIS]
    out["primary_dominant_type"] = out[primary_col]
    out["primary_share"] = out[primary_share_col]
    out["is_mixed"] = out["primary_share"] < MIXED_THRESHOLD

    # row-count and value context columns
    n_rows_per_item = sale.groupby("itemcode").size().rename("n_rows")
    n_rows_with_type = sale.dropna(subset=["manufacturing_type"]).groupby("itemcode").size().rename("n_rows_typed")
    out = out.join(n_rows_per_item).join(n_rows_with_type)

    out = out.reset_index().rename(columns={"index": "itemcode"})
    out.to_csv(OUT_ITEM_DIST, index=False)
    logger.info("Part 1: item distribution table written (%d items), primary basis=%s, mixed "
                "threshold=%.0f%%.", len(out), PRIMARY_BASIS, MIXED_THRESHOLD * 100)
    return out


def part1_division_summary(item_dist):
    rows = []
    for div, g in item_dist.groupby("division"):
        n = len(g)
        counts = g.loc[~g["is_mixed"], "primary_dominant_type"].value_counts().to_dict()
        n_mixed = int(g["is_mixed"].sum())
        n_disagree = int((~g["bases_agree"]).sum())
        rows.append(dict(
            division=div, n_items=n,
            dominant_MTS=counts.get("MTS", 0), dominant_MTO=counts.get("MTO", 0),
            dominant_ETO=counts.get("ETO", 0), n_mixed=n_mixed,
            pct_mixed=round(100 * n_mixed / n, 1) if n else np.nan,
            n_basis_disagreement=n_disagree,
        ))
    div_summary = pd.DataFrame(rows)
    div_summary.to_csv(OUT_DIV_SUMMARY, index=False)
    logger.info("Part 1: per-division summary:\n%s", div_summary.to_string(index=False))
    return div_summary


# ------------------------------------------------------------------------------------------
# Part 2/3: behaviour tests, per item with a clear (non-mixed) dominant type
# ------------------------------------------------------------------------------------------

def test_stock(clear_items, inv):
    sub = inv[inv["itemcode"].isin(clear_items["itemcode"])]
    per_item = sub.groupby("itemcode").agg(
        total_stock=("stock", "sum"), n_warehouse_rows=("itemcode", "size"),
        n_warehouses_with_stock=("stock", lambda s: int((s > 0).sum())),
    ).reset_index()
    out = clear_items[["itemcode", "division", "primary_dominant_type"]].merge(
        per_item, on="itemcode", how="left")
    out["total_stock"] = out["total_stock"].fillna(0.0)
    out["n_warehouse_rows"] = out["n_warehouse_rows"].fillna(0).astype(int)
    out["n_warehouses_with_stock"] = out["n_warehouses_with_stock"].fillna(0).astype(int)
    out["has_any_stock"] = out["total_stock"] > 0
    out.to_csv(OUT_STOCK_TEST, index=False)
    return out


def test_order_notice(clear_items, sale):
    d = sale.copy()
    d["createDate"] = pd.to_datetime(d["createDate"])
    d["forecast_date"] = pd.to_datetime(d["forecast_date"], errors="coerce")
    d = d[d["forecast_date"].notna() & (d["forecast_date"] >= d["createDate"])]
    d["notice_days"] = (d["forecast_date"] - d["createDate"]).dt.days
    d = d[d["itemcode"].isin(clear_items["itemcode"])]
    rows = []
    for item, g in d.groupby("itemcode"):
        rows.append(dict(itemcode=item, **dist_stats(g["notice_days"])))
    out = pd.DataFrame(rows)
    out = clear_items[["itemcode", "division", "primary_dominant_type"]].merge(out, on="itemcode", how="left")
    out.to_csv(OUT_NOTICE_TEST, index=False)
    return out


def test_delivery_time(clear_items, ces):
    d = ces.copy()
    d["CtrDate"] = pd.to_datetime(d["CtrDate"], errors="coerce")
    d["ActualDelDate"] = pd.to_datetime(d["ActualDelDate"], errors="coerce")
    d = d[(d["Status"] == "Actual") & d["CtrDate"].notna() & d["ActualDelDate"].notna()]
    d["delivery_days"] = (d["ActualDelDate"] - d["CtrDate"]).dt.days
    d = d[d["ItemCode"].isin(clear_items["itemcode"])]
    rows = []
    for item, g in d.groupby("ItemCode"):
        rows.append(dict(itemcode=item, **dist_stats(g["delivery_days"])))
    out = pd.DataFrame(rows)
    out = clear_items[["itemcode", "division", "primary_dominant_type"]].merge(out, on="itemcode", how="left")
    out.to_csv(OUT_DELIVERY_TEST, index=False)
    return out


def is_blank_token(x):
    if pd.isna(x):
        return True
    s = str(x).strip()
    return s == "" or s.lower() == "none"


def build_batch_tokens(ces):
    """EXACT method reused from src/investigations/phaseJ3_explorerD_analysis.py (which DATA_MAP.md
    Sec.2 jobcode/jobno/OLMJobCode entry and Sec.3 Joins' OLMJobCode row cite as the project's
    established reverse-traceability proxy): restrict to Status IN ('Actual','Backlog'), build a
    per-OLMJobCode-token summary keyed on first CtrDate appearance (the "batch became available"
    proxy), and classify each delivered (Status='Actual') row as traceable_pre_existing when its
    token's first appearance predates ITS OWN CtrDate."""
    ces_ab = ces[ces["Status"].isin(["Actual", "Backlog"])].copy()
    ces_ab["CtrDate"] = pd.to_datetime(ces_ab["CtrDate"], errors="coerce")
    ces_ab["has_token"] = ~ces_ab["OLMJobCode"].apply(is_blank_token)
    usable = ces_ab[ces_ab["has_token"] & ces_ab["CtrDate"].notna()].copy()

    token_summary = (
        usable.groupby("OLMJobCode")
        .agg(itemcode=("ItemCode", lambda x: x.mode().iat[0] if not x.mode().empty else x.iloc[0]),
             first_ctrdate=("CtrDate", "min"), n_rows=("ContractID", "size"))
        .reset_index()
    )
    token_summary.to_csv(OUT_BATCH_TOKEN, index=False)
    logger.info("Batch tokens (OLMJobCode, Actual+Backlog, non-blank): %d distinct tokens.",
                len(token_summary))
    return ces_ab, token_summary


def test_batch_before_po(clear_items, ces_ab, token_summary):
    token_first = token_summary.set_index("OLMJobCode")["first_ctrdate"]
    actual = ces_ab[ces_ab["Status"] == "Actual"].copy()

    def classify(row):
        tok = row["OLMJobCode"]
        if is_blank_token(tok) or pd.isna(row["CtrDate"]):
            return "no_token"
        first = token_first.get(tok, pd.NaT)
        if pd.isna(first):
            return "no_token"
        if first < row["CtrDate"]:
            return "traceable_pre_existing"
        return "earliest_occurrence"

    actual["trace_class"] = actual.apply(classify, axis=1)
    actual = actual[actual["ItemCode"].isin(clear_items["itemcode"])]

    rows = []
    for item, g in actual.groupby("ItemCode"):
        n = len(g)
        n_pre = int((g["trace_class"] == "traceable_pre_existing").sum())
        rows.append(dict(itemcode=item, n_delivered_contracts=n,
                          n_traceable_pre_existing=n_pre,
                          batch_before_po_share=n_pre / n if n else np.nan))
    out = pd.DataFrame(rows)
    out = clear_items[["itemcode", "division", "primary_dominant_type"]].merge(out, on="itemcode", how="left")
    out.to_csv(OUT_BATCH_TEST, index=False)
    return out


def summarize_behavior(stock, notice, delivery, batch, group_cols):
    """Aggregates the 4 tests by group_cols (division, dominant type)."""
    m = stock[["itemcode"] + list(group_cols) + ["has_any_stock", "total_stock"]].merge(
        notice[["itemcode", "median", "p25", "p75", "n"]].rename(
            columns={"median": "notice_median_days", "p25": "notice_p25", "p75": "notice_p75", "n": "notice_n"}),
        on="itemcode", how="left"
    ).merge(
        delivery[["itemcode", "median", "p25", "p75", "n"]].rename(
            columns={"median": "delivery_median_days", "p25": "delivery_p25", "p75": "delivery_p75", "n": "delivery_n"}),
        on="itemcode", how="left"
    ).merge(
        batch[["itemcode", "batch_before_po_share", "n_delivered_contracts"]],
        on="itemcode", how="left"
    )
    m.to_csv(OUT_BEHAVIOR_ITEM, index=False)

    agg_rows = []
    for keys, g in m.groupby(list(group_cols)):
        keys = keys if isinstance(keys, tuple) else (keys,)
        row = dict(zip(group_cols, keys))
        row.update(dict(
            n_items=len(g),
            pct_with_stock=round(100 * g["has_any_stock"].mean(), 1) if len(g) else np.nan,
            median_notice_days=g["notice_median_days"].median(),
            median_delivery_days=g["delivery_median_days"].median(),
            mean_batch_before_po_share=g["batch_before_po_share"].mean(),
            median_batch_before_po_share=g["batch_before_po_share"].median(),
        ))
        agg_rows.append(row)
    agg = pd.DataFrame(agg_rows)
    agg.to_csv(OUT_BEHAVIOR_DIV, index=False)
    logger.info("Behaviour summary by %s:\n%s", group_cols, agg.to_string(index=False))
    return m, agg


def main():
    scope = pd.read_csv(SCOPE_FILE)
    sale = pd.read_csv(SALE_FILE)
    inv = pd.read_csv(INV_FILE)
    ces = pd.read_csv(CES_FILE)

    item_dist = part1_distribution(sale, scope)
    div_summary = part1_division_summary(item_dist)

    mixed_items = item_dist[item_dist["is_mixed"]].copy()
    mixed_items.to_csv(OUT_MIXED_ITEMS, index=False)
    logger.info("Mixed items (primary_share < %.0f%%): %d of %d total.",
                MIXED_THRESHOLD * 100, len(mixed_items), len(item_dist))

    clear_items = item_dist[~item_dist["is_mixed"]].copy()
    logger.info("Clear (non-mixed) items for Part 2/3 behaviour testing: %d.", len(clear_items))

    stock = test_stock(clear_items, inv)
    notice = test_order_notice(clear_items, sale)
    delivery = test_delivery_time(clear_items, ces)
    ces_ab, token_summary = build_batch_tokens(ces)
    batch = test_batch_before_po(clear_items, ces_ab, token_summary)

    per_item, per_div_type = summarize_behavior(stock, notice, delivery, batch,
                                                  ["division", "primary_dominant_type"])

    # PEM104 cross-check: separate view
    pem104 = per_item[per_item["division"] == "PEM104"]
    logger.info("PEM104 clear-item behaviour rows: %d\n%s", len(pem104), pem104.to_string(index=False))

    print("ANALYSIS DONE")


if __name__ == "__main__":
    main()
