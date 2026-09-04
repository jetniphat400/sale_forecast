"""Task 1, part 2: examine EEE-F-FC-1040010002's orders in the Feb-Jul 2026 anomalous window.
Tests the specific hypothesis: is createDate (receipt) concentrated in one calendar month while
forecast_date (delivery) is spread across several, in exactly this window and not elsewhere? That
pattern would make the forecast_date-keyed series smoother in this window only.

PRIMARY analysis: ALL orders (rows) whose forecast_date falls in the window, grouped by
createDate month vs forecast_date month, concentration measured by HHI (Herfindahl-Hirschman
Index, sum of squared qty-shares by month -- higher = more concentrated in fewer months), n
distinct months touched, and busiest-month qty share. Using ALL orders (not just a large-order
subset) is deliberate: the anomalous window has 116 rows and the contrast window only 11 (and a
"large order" >=90th-percentile cut leaves only 6 and 1 rows respectively, too few for a stable
HHI) -- ALL-orders concentration directly measures the re-keying's smoothing mechanism (the same
total qty reshuffled across months depending on which date field places it), which is exactly
what a "receipt concentrated, delivery spread out" pattern would produce at ANY order size, not
only the largest ones.

SECONDARY, explicitly labelled low-n robustness check: the same statistic restricted to "large
orders" (row qty >= this item's own 90th percentile of row qty over its full history) -- reported
for completeness per the task brief's explicit request, with the small-sample caveat stated, not
hidden.

Contrast 1 (same item, non-anomalous window): the origin-1 rolling-origin test window (2025-02 to
2025-07), which task1_reversal_verdict / b4_per_origin_comparison did NOT show as reversing in
forecast_date's favour -- if the smoothing pattern is specific to the anomalous window, it should
be weak or absent here.
Contrast 2 (other items, same anomalous window): the other two focus codes, same 2026-02 to
2026-07 window -- if the pattern is specific to this item, other items in the identical window
should not show the same forecast_date-smoother signature.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task1_large_order_examination")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

FOCUS_ITEM = "EEE-F-FC-1040010002"
LARGE_ORDER_PERCENTILE = 0.90
ANOMALOUS_WINDOW = (pd.Period("2026-02", freq="M"), pd.Period("2026-07", freq="M"))   # origin 7 test window
CONTRAST_WINDOW = (pd.Period("2025-02", freq="M"), pd.Period("2025-07", freq="M"))     # origin 1 test window, non-anomalous
OTHER_ITEMS_SAMPLE = ["HS-F-99-02110", "HS-F-99-0213"]  # the two other focus codes, per the task brief


def concentration_stats(rows: pd.DataFrame, date_col: str) -> dict:
    if len(rows) == 0:
        return {"n_rows": 0, "total_qty": 0.0, "n_distinct_months": 0, "hhi": np.nan, "busiest_month_share": np.nan,
                "by_month": pd.Series(dtype=float)}
    by_month = rows.groupby(rows[date_col].dt.to_period("M"))["qty"].sum()
    total = by_month.sum()
    shares = by_month / total
    hhi = float((shares ** 2).sum())
    busiest_share = float(shares.max())
    return {"n_rows": len(rows), "total_qty": float(total), "n_distinct_months": int(by_month.size),
            "hhi": hhi, "busiest_month_share": busiest_share, "by_month": by_month}


def rows_in_window(raw: pd.DataFrame, itemcode: str, window: tuple, min_qty: float = None) -> pd.DataFrame:
    item_rows = raw[raw["itemcode"] == itemcode].copy()
    if min_qty is not None:
        item_rows = item_rows[item_rows["qty"] >= min_qty]
    return item_rows[(item_rows["forecast_date"].dt.to_period("M") >= window[0]) &
                      (item_rows["forecast_date"].dt.to_period("M") <= window[1])]


def report_pair(label: str, rows: pd.DataFrame) -> dict:
    cd = concentration_stats(rows, "createDate")
    fd = concentration_stats(rows, "forecast_date")
    smoother = (fd["hhi"] < cd["hhi"]) if (pd.notna(cd["hhi"]) and pd.notna(fd["hhi"])) else None
    print(f"\n--- {label}: n={len(rows)} rows ---")
    if len(rows):
        print("By createDate month:")
        print(cd["by_month"].to_string())
        print("By forecast_date month:")
        print(fd["by_month"].to_string())
    print(f"createDate: {cd['n_distinct_months']} months, HHI={cd['hhi']:.3f}, busiest-month share={cd['busiest_month_share']:.3f}" if len(rows) else "createDate: n/a")
    print(f"forecast_date: {fd['n_distinct_months']} months, HHI={fd['hhi']:.3f}, busiest-month share={fd['busiest_month_share']:.3f}" if len(rows) else "forecast_date: n/a")
    if smoother is not None:
        print(f"forecast_date {'IS' if smoother else 'is NOT'} more spread out (lower HHI) than createDate.")
    return {"label": label, "n_rows": len(rows), "createDate_hhi": cd["hhi"], "forecastDate_hhi": fd["hhi"],
            "createDate_n_months": cd["n_distinct_months"], "forecastDate_n_months": fd["n_distinct_months"],
            "createDate_busiest_share": cd["busiest_month_share"], "forecastDate_busiest_share": fd["busiest_month_share"],
            "forecastDate_smoother": smoother}


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw = raw.dropna(subset=["forecast_date"])
    raw = raw[raw["forecast_date"] >= raw["createDate"]]  # same B1/leakage_check filter, consistent scope

    print("\n" + "#" * 100)
    print(f"# TASK 1 PART 2: {FOCUS_ITEM} order timing, Feb-Jul 2026 (anomalous origin-7 window)")
    print("#" * 100)

    item_all = raw[raw["itemcode"] == FOCUS_ITEM]
    threshold = item_all["qty"].quantile(LARGE_ORDER_PERCENTILE)
    print(f"\n{FOCUS_ITEM}: {len(item_all)} total rows (all history, forecast_date-valid). "
          f"Large-order threshold (own {int(LARGE_ORDER_PERCENTILE*100)}th percentile of row qty, full history): {threshold:.2f}")
    print(f"Row-qty distribution: min={item_all['qty'].min():.1f}, median={item_all['qty'].median():.1f}, "
          f"90th pct={threshold:.1f}, max={item_all['qty'].max():.1f}")

    summary_rows = []

    # ================= PRIMARY: ALL ORDERS, anomalous vs contrast window (same item) =================
    print("\n" + "=" * 100)
    print("PRIMARY: ALL orders (every row, any size) -- most reliable sample size")
    print("=" * 100)
    anom_all = rows_in_window(raw, FOCUS_ITEM, ANOMALOUS_WINDOW)
    r = report_pair(f"{FOCUS_ITEM}, ANOMALOUS window {ANOMALOUS_WINDOW[0]}-{ANOMALOUS_WINDOW[1]}, ALL orders", anom_all)
    r["variant"] = "all_orders"; summary_rows.append(r)

    contrast_all = rows_in_window(raw, FOCUS_ITEM, CONTRAST_WINDOW)
    r = report_pair(f"{FOCUS_ITEM}, CONTRAST window {CONTRAST_WINDOW[0]}-{CONTRAST_WINDOW[1]}, ALL orders", contrast_all)
    r["variant"] = "all_orders"; summary_rows.append(r)

    print(f"\n--- CONTRAST: other focus items, SAME anomalous window {ANOMALOUS_WINDOW[0]}-{ANOMALOUS_WINDOW[1]}, ALL orders ---")
    for other_item in OTHER_ITEMS_SAMPLE:
        other_win = rows_in_window(raw, other_item, ANOMALOUS_WINDOW)
        r = report_pair(f"{other_item}, ANOMALOUS window, ALL orders", other_win)
        r["variant"] = "all_orders"; summary_rows.append(r)

    # ================= SECONDARY: LARGE-ORDER (p90) subset, labelled low-n =================
    print("\n" + "=" * 100)
    print("SECONDARY (explicit low-n caveat): large orders only (row qty >= item's own 90th percentile)")
    print("=" * 100)
    anom_large = rows_in_window(raw, FOCUS_ITEM, ANOMALOUS_WINDOW, min_qty=threshold)
    r = report_pair(f"{FOCUS_ITEM}, ANOMALOUS window, LARGE orders only (n may be very small)", anom_large)
    r["variant"] = "large_orders_p90"; summary_rows.append(r)

    contrast_large = rows_in_window(raw, FOCUS_ITEM, CONTRAST_WINDOW, min_qty=threshold)
    r = report_pair(f"{FOCUS_ITEM}, CONTRAST window, LARGE orders only (n may be very small)", contrast_large)
    r["variant"] = "large_orders_p90"; summary_rows.append(r)

    for other_item in OTHER_ITEMS_SAMPLE:
        other_all_hist = raw[raw["itemcode"] == other_item]
        other_threshold = other_all_hist["qty"].quantile(LARGE_ORDER_PERCENTILE)
        other_large = rows_in_window(raw, other_item, ANOMALOUS_WINDOW, min_qty=other_threshold)
        r = report_pair(f"{other_item}, ANOMALOUS window, LARGE orders only (own p90={other_threshold:.1f}, n may be very small)", other_large)
        r["variant"] = "large_orders_p90"; summary_rows.append(r)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(os.path.join(SUMMARY_DIR, "task1_large_order_concentration_summary.csv"), index=False)
    anom_all.to_csv(os.path.join(SUMMARY_DIR, "task1_orders_anomalous_window_detail.csv"), index=False)
    contrast_all.to_csv(os.path.join(SUMMARY_DIR, "task1_orders_contrast_window_detail.csv"), index=False)

    print("\n" + "=" * 100)
    print("SUMMARY TABLE (all rows, both variants)")
    print("=" * 100)
    print(summary_df[["label", "variant", "n_rows", "createDate_hhi", "forecastDate_hhi", "createDate_n_months",
                       "forecastDate_n_months", "forecastDate_smoother"]].round(3).to_string(index=False))

    # ================= VERDICT (based on the PRIMARY, all-orders analysis) =================
    focus_anom = summary_df[(summary_df["label"].str.contains(FOCUS_ITEM)) & (summary_df["label"].str.contains("ANOMALOUS")) & (summary_df["variant"] == "all_orders")].iloc[0]
    focus_contrast = summary_df[(summary_df["label"].str.contains(FOCUS_ITEM)) & (summary_df["label"].str.contains("CONTRAST")) & (summary_df["variant"] == "all_orders")].iloc[0]
    other_smoother_flags = summary_df[(summary_df["variant"] == "all_orders") & (~summary_df["label"].str.contains(FOCUS_ITEM))]["forecastDate_smoother"].tolist()

    print("\n--- VERDICT (primary, all-orders basis) ---")
    print(f"Focus item, ANOMALOUS window: createDate HHI={focus_anom['createDate_hhi']:.3f} vs forecast_date HHI={focus_anom['forecastDate_hhi']:.3f} "
          f"-> forecast_date_smoother={focus_anom['forecastDate_smoother']}")
    print(f"Focus item, CONTRAST window: createDate HHI={focus_contrast['createDate_hhi']:.3f} vs forecast_date HHI={focus_contrast['forecastDate_hhi']:.3f} "
          f"-> forecast_date_smoother={focus_contrast['forecastDate_smoother']}")
    print(f"Other items, SAME anomalous window: forecast_date_smoother flags = {other_smoother_flags}")

    is_specific = bool(focus_anom["forecastDate_smoother"]) and not bool(focus_contrast["forecastDate_smoother"]) and not any(other_smoother_flags)
    print(f"\nPattern judged {'SPECIFIC to this item AND this window' if is_specific else 'NOT cleanly specific (see individual flags above)'} "
          f"on the primary (all-orders) analysis.")

    # ================= CHART =================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    panels = [
        (f"{FOCUS_ITEM}\nAnomalous window (2026-02 to 2026-07)", anom_all),
        (f"{FOCUS_ITEM}\nContrast window (2025-02 to 2025-07)", contrast_all),
        (f"{OTHER_ITEMS_SAMPLE[0]}\nAnomalous window (2026-02 to 2026-07)", rows_in_window(raw, OTHER_ITEMS_SAMPLE[0], ANOMALOUS_WINDOW)),
        (f"{OTHER_ITEMS_SAMPLE[1]}\nAnomalous window (2026-02 to 2026-07)", rows_in_window(raw, OTHER_ITEMS_SAMPLE[1], ANOMALOUS_WINDOW)),
    ]
    for ax, (title, rows) in zip(axes.flat, panels):
        if len(rows) == 0:
            ax.set_title(title + " (no rows)", fontsize=9)
            continue
        cd_by_month = rows.groupby(rows["createDate"].dt.to_period("M"))["qty"].sum()
        fd_by_month = rows.groupby(rows["forecast_date"].dt.to_period("M"))["qty"].sum()
        all_months = sorted(set(cd_by_month.index) | set(fd_by_month.index))
        x = np.arange(len(all_months))
        width = 0.35
        ax.bar(x - width/2, [cd_by_month.get(m, 0) for m in all_months], width, label="by createDate", color="tab:blue")
        ax.bar(x + width/2, [fd_by_month.get(m, 0) for m in all_months], width, label="by forecast_date", color="tab:red")
        ax.set_xticks(x)
        ax.set_xticklabels([str(m) for m in all_months], rotation=45, ha="right", fontsize=7)
        ax.set_title(title, fontsize=9)
        ax.set_ylabel("Qty")
        ax.legend(fontsize=7)
    fig.suptitle("All orders whose forecast_date falls in the window, grouped by createDate vs forecast_date month", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "task1_large_order_concentration.png"), dpi=130)
    plt.close(fig)

    print("\nOutputs: output/summary/task1_large_order_concentration_summary.csv, "
          "task1_orders_anomalous_window_detail.csv, task1_orders_contrast_window_detail.csv")
    print("Chart: output/charts/task1_large_order_concentration.png")
