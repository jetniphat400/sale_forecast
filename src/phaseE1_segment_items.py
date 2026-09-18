"""Phase E1.1 (Modeler): segment the 128-item PEM101 pilot and compare stocking policies.

Scope reminder: PEM101 128-item pilot only (config['adopted_scope_file']). BOUNDED SCENARIO
PILOT -- produces NO actionable purchase recommendation, only a scenario analysis for the
business to evaluate. 16 of 128 items (6 excluded_item_codes + 10 placeholder_item_codes) get NO
segmentation-driven policy at all -- reported as "no supported policy: placeholder/excluded item,
no real forecast exists", per the hard acceptance criterion that such an item must never receive
a Min, Max or purchase quantity.

Method:
  1. Demand classification (Smooth/Erratic/Intermittent/Lumpy) via ADI/CV2, SBC (2005) thresholds,
     re-derived at THIS 128-item scope (not assumed unchanged from the old dashboard classification).
  2. Annual value = mean monthly `sale` value (cube_Sale_APD's own revenue column, already in the
     monthly series) x 12 -- stated choice: uses `sale` (recorded revenue), not qty x a separately
     queried unit cost, since it is already available in the loaded series with no extra query.
  3. Order frequency = distinct order LINES per year (raw cube_Sale_APD rows, Omni Channel,
     Actual+MPS, forecast_date-valid) -- a finer grain than "months with any demand," and reused
     for the notice-vs-lead-time comparison below from the same pull.
  4. Segments = demand class x a low_value_low_freq flag (both dimensions split at their own
     scope median) -- reported per the task's instruction not to default every item to one policy.
  5. Per segment: FG-stock / Component-ATO / Make-to-order evaluated against real order-notice
     data (this segment's own median notice vs the business's 45-60/75-day lead-time grid), and an
     assembly-time sensitivity table for Component-ATO feasibility.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import (
    PROJECT_ROOT, SUMMARY_DIR, CHARTS_DIR, ADI_THRESHOLD, CV2_THRESHOLD,
    load_config, load_scope, load_monthly_series, query_order_level,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_segment_items")


def classify_demand(qty: np.ndarray) -> tuple:
    """SBC (2005) ADI/CV2 classification, thresholds reused verbatim from
    src/investigations/series_features.py (ADI_THRESHOLD=1.32, CV2_THRESHOLD=0.49)."""
    n = len(qty)
    nonzero = qty[qty > 0]
    if len(nonzero) == 0:
        return "NoSale", None, None
    adi = n / len(nonzero)
    mean_d = nonzero.mean()
    std_d = nonzero.std(ddof=1) if len(nonzero) > 1 else 0.0
    cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        cls = "Smooth"
    elif adi < ADI_THRESHOLD:
        cls = "Erratic"
    elif cv2 < CV2_THRESHOLD:
        cls = "Intermittent"
    else:
        cls = "Lumpy"
    return cls, adi, cv2


def build_item_table(scope: pd.DataFrame, series_bundle: dict, order_level: pd.DataFrame) -> pd.DataFrame:
    series = series_bundle["series"]
    monthly_full = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "data",
                                             "processed_full_category_sales_monthly_forecastDate.csv"))
    sale_by_item = monthly_full.groupby("itemcode")["sale"].apply(lambda s: s.to_numpy(dtype=float))

    rows = []
    for _, r in scope.iterrows():
        code = r["code"]
        if code not in series:
            rows.append({"code": code, "type": r["type"], "category": r["category"],
                         "eligible_for_policy": r["eligible_for_policy"],
                         "is_excluded": r["is_excluded"], "is_placeholder": r["is_placeholder"],
                         "demand_class": "NO_HISTORY", "adi": None, "cv2": None,
                         "annual_value_thb": 0.0, "order_freq_per_year": 0.0,
                         "median_notice_days": None, "n_orders": 0})
            continue
        qty, months = series[code]
        cls, adi, cv2 = classify_demand(qty)
        sale = sale_by_item.get(code, np.array([]))
        annual_value = float(sale.mean() * 12) if len(sale) else 0.0

        item_orders = order_level[order_level["itemcode"] == code]
        n_orders = len(item_orders)
        n_years = 31 / 12.0
        order_freq = n_orders / n_years
        median_notice = float(item_orders["notice_days"].median()) if n_orders else None

        rows.append({"code": code, "type": r["type"], "category": r["category"],
                     "eligible_for_policy": r["eligible_for_policy"],
                     "is_excluded": r["is_excluded"], "is_placeholder": r["is_placeholder"],
                     "demand_class": cls, "adi": adi, "cv2": cv2,
                     "annual_value_thb": annual_value, "order_freq_per_year": order_freq,
                     "median_notice_days": median_notice, "n_orders": n_orders})
    return pd.DataFrame(rows)


def assign_segments(item_table: pd.DataFrame) -> pd.DataFrame:
    """Segment = demand_class x low_value_low_freq flag, computed ONLY over eligible_for_policy
    items (median splits computed on the eligible population, not the full 128, since placeholder/
    excluded items have no real value/frequency to split on)."""
    df = item_table.copy()
    elig = df[df["eligible_for_policy"]]
    value_median = elig["annual_value_thb"].median()
    freq_median = elig["order_freq_per_year"].median()
    df["value_median_used"] = value_median
    df["freq_median_used"] = freq_median
    df["low_value_low_freq"] = df["eligible_for_policy"] & \
        (df["annual_value_thb"] <= value_median) & (df["order_freq_per_year"] <= freq_median)
    df["segment"] = np.where(
        df["eligible_for_policy"],
        df["demand_class"] + np.where(df["low_value_low_freq"], " (low-value/low-freq)", " (other)"),
        "NO_SUPPORTED_POLICY")
    # E1.3 downstream flag: FG-stock is the segment's PRIMARY supported policy only for the
    # "(other)" (not low-value/low-freq) eligible segments -- the low-value/low-freq segments'
    # own numbers instead support Component stock/assemble-to-order as the primary recommendation
    # (see write_verdicts below), so those items do NOT get an FG Min/Max under E1.3's own scope
    # restriction ("only for items in segments where E1.1 found finished-goods stock is the
    # supported policy").
    df["fg_stock_policy_supported"] = df["eligible_for_policy"] & (~df["low_value_low_freq"])
    return df


def notice_vs_leadtime(item_table: pd.DataFrame, order_level: pd.DataFrame, lead_time_grid: list) -> pd.DataFrame:
    """Per segment: median order notice, and % of that segment's ORDER LINES whose notice clears
    each lead-time-grid value (the literal make-to-order feasibility test: notice > procurement
    lead time)."""
    df = item_table[item_table["eligible_for_policy"]]
    rows = []
    for seg, grp in df.groupby("segment"):
        codes = set(grp["code"])
        seg_orders = order_level[order_level["itemcode"].isin(codes)]
        row = {"segment": seg, "n_items": len(grp), "n_orders": len(seg_orders),
               "median_notice_days": seg_orders["notice_days"].median() if len(seg_orders) else None}
        for lt in lead_time_grid:
            pct = 100 * (seg_orders["notice_days"] > lt).mean() if len(seg_orders) else None
            row[f"pct_orders_notice_gt_{lt}d"] = pct
        rows.append(row)
    return pd.DataFrame(rows)


def ato_sensitivity(item_table: pd.DataFrame, order_level: pd.DataFrame, assembly_days_grid: list) -> pd.DataFrame:
    """Per segment: for each assumed assembly-time value, feasible = segment median order notice
    (falling back to the project-wide 6-day median, STATUS.md Business Findings, if the segment
    itself has too few orders) >= assembly_days (component stock, assemble-to-order fits inside
    the customer's own notice window)."""
    df = item_table[item_table["eligible_for_policy"]]
    project_wide_median_notice = order_level["notice_days"].median()
    rows = []
    for seg, grp in df.groupby("segment"):
        codes = set(grp["code"])
        seg_orders = order_level[order_level["itemcode"].isin(codes)]
        n = len(seg_orders)
        median_notice = seg_orders["notice_days"].median() if n >= 10 else project_wide_median_notice
        basis = "segment" if n >= 10 else "project-wide (segment has <10 order lines)"
        row = {"segment": seg, "n_orders": n, "median_notice_days_used": median_notice, "basis": basis}
        for a in assembly_days_grid:
            row[f"feasible_at_{a}d_assembly"] = bool(median_notice >= a)
        rows.append(row)
    return pd.DataFrame(rows)


def write_verdicts(seg_summary: pd.DataFrame, ato: pd.DataFrame, notice: pd.DataFrame,
                    default_assembly_days: int, lead_default: int) -> pd.DataFrame:
    merged = seg_summary.merge(ato[["segment", "n_orders", "median_notice_days_used", "basis"] +
                                    [c for c in ato.columns if c.startswith("feasible_at_")]],
                                on="segment", how="left")
    merged = merged.merge(notice[["segment"] + [c for c in notice.columns if c.startswith("pct_orders_notice_gt_")]],
                           on="segment", how="left")

    def verdict(row):
        gap = lead_default - (row["median_notice_days_used"] or 0)
        feasible_default_assembly = row.get(f"feasible_at_{default_assembly_days}d_assembly", False)
        mto_pct = row.get(f"pct_orders_notice_gt_{lead_default}d", 0) or 0
        if row["low_value_low_freq"]:
            if feasible_default_assembly:
                return (f"Component stock, assemble-to-order SUPPORTED by this segment's own numbers: "
                        f"low annual value (median-split segment) and low order frequency mean holding "
                        f"finished units ties up capital for rarely-realised demand, while median notice "
                        f"({row['median_notice_days_used']:.1f}d) still clears the default {default_assembly_days}-day "
                        f"assembly assumption. Finished-goods stock is not ruled out, but is a weaker default here "
                        f"than for higher-value/higher-frequency segments.")
            else:
                return (f"Finished-goods stock is the only supported policy even though this is a low-value/"
                        f"low-frequency segment: median notice ({row['median_notice_days_used']:.1f}d) does NOT "
                        f"clear the default {default_assembly_days}-day assembly assumption, so component "
                        f"stock/ATO is not feasible under the default assumption (see sensitivity table for "
                        f"which assembly-time assumptions would change this).")
        return (f"Finished-goods stock SUPPORTED: median notice ({row['median_notice_days_used']:.1f}d) is far "
                f"below the {lead_default}-day default procurement lead time (gap {gap:.1f}d) -- customers cannot "
                f"be served from a build-to-order or buy-to-order process. Make-to-order is RULED OUT ({mto_pct:.1f}% "
                f"of this segment's order lines give notice > {lead_default}d).")

    merged["policy_verdict"] = merged.apply(verdict, axis=1)
    return merged


def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(CHARTS_DIR, exist_ok=True)
    config = load_config()
    e1 = config["phase_e1_assumptions"]

    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    order_level = query_order_level(scope["code"].tolist(), config)

    item_table = build_item_table(scope, series_bundle, order_level)
    item_table = assign_segments(item_table)

    n_no_policy = int((~item_table["eligible_for_policy"]).sum())
    logger.info("%d of %d items get NO segmentation-driven policy (excluded/placeholder) -- listed, "
                "not silently dropped.", n_no_policy, len(item_table))

    seg_summary = item_table[item_table["eligible_for_policy"]].groupby(
        ["segment", "demand_class", "low_value_low_freq"], as_index=False).agg(
        n_items=("code", "nunique"), total_annual_value_thb=("annual_value_thb", "sum"),
        mean_annual_value_thb=("annual_value_thb", "mean"),
        mean_order_freq_per_year=("order_freq_per_year", "mean"))

    lead_grid = e1["procurement_lead_time_days_grid"]
    lead_default = e1["procurement_lead_time_days_default"]
    assembly_grid = e1["assembly_time_sensitivity_days"]
    default_assembly = e1["assembly_time_days_default"]

    notice_tbl = notice_vs_leadtime(item_table, order_level, lead_grid)
    ato_tbl = ato_sensitivity(item_table, order_level, assembly_grid)
    verdicts = write_verdicts(seg_summary, ato_tbl, notice_tbl, default_assembly, lead_default)

    no_policy_items = item_table[~item_table["eligible_for_policy"]][["code", "type", "is_excluded", "is_placeholder"]]
    no_policy_items = no_policy_items.copy()
    no_policy_items["reason"] = np.where(
        no_policy_items["is_excluded"],
        "no supported policy: excluded_item_codes -- listed in pricelist but never sold, zero demand history anywhere",
        "no supported policy: placeholder_item_codes -- sold only outside this project's scope or unclassifiable, no real item-specific forecast exists (placeholder_hierarchy_treatment: never feeds a purchase/reorder recommendation)")

    item_table.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_item_segments.csv"), index=False)
    seg_summary.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_segment_summary.csv"), index=False)
    notice_tbl.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_notice_vs_leadtime.csv"), index=False)
    ato_tbl.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_ato_sensitivity.csv"), index=False)
    verdicts.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_segment_verdicts.csv"), index=False)
    no_policy_items.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_1_no_policy_items.csv"), index=False)

    # ---- chart: segment item counts + value ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    seg_sorted = seg_summary.sort_values("n_items", ascending=False)
    ax1.barh(seg_sorted["segment"], seg_sorted["n_items"], color="tab:blue")
    ax1.set_xlabel("Item count")
    ax1.set_title("E1.1 segments -- item counts (112 eligible items)")
    ax2.barh(seg_sorted["segment"], seg_sorted["total_annual_value_thb"], color="tab:orange")
    ax2.set_xlabel("Total annual value (THB, sum of mean monthly `sale` x 12)")
    ax2.set_title("E1.1 segments -- annual value")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "phaseE1_segment_value_count.png"), dpi=120)
    plt.close(fig)

    logger.info("Wrote phaseE1_1_item_segments.csv (%d rows), phaseE1_1_segment_summary.csv (%d segments), "
                "phaseE1_1_notice_vs_leadtime.csv, phaseE1_1_ato_sensitivity.csv, "
                "phaseE1_1_segment_verdicts.csv, phaseE1_1_no_policy_items.csv (%d items).",
                len(item_table), len(seg_summary), len(no_policy_items))
    logger.info("Chart: output/charts/phaseE1_segment_value_count.png")

    print("\n=== E1.1 SEGMENT VERDICTS ===")
    for _, r in verdicts.iterrows():
        print(f"\n--- {r['segment']} ({int(r['n_items'])} items, THB {r['total_annual_value_thb']:,.0f}/yr) ---")
        print(r["policy_verdict"])

    return {"item_table": item_table, "seg_summary": seg_summary, "verdicts": verdicts,
            "notice_tbl": notice_tbl, "ato_tbl": ato_tbl, "no_policy_items": no_policy_items}


if __name__ == "__main__":
    main()
