"""Investigates demand spikes across the 58 pilot items: what drives them,
whether they are a general pattern, and how much they affect demand
classification and forecast difficulty.

Investigation only. Does not modify any dataset, does not change any model,
does not re-run the full backtest.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("investigate_spikes")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

SPIKE_MULTIPLIER = 3.0  # a month qualifies as a spike if qty > 3x the item's own median non-zero month
ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49


def classify(adi, cv2):
    if adi is None:
        return "NoSale"
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        return "Smooth"
    if adi < ADI_THRESHOLD:
        return "Erratic"
    if cv2 < CV2_THRESHOLD:
        return "Intermittent"
    return "Lumpy"


def compute_adi_cv2(qty_series: np.ndarray):
    n = len(qty_series)
    nonzero = qty_series[qty_series > 0]
    if len(nonzero) == 0:
        return None, None
    adi = n / len(nonzero)
    mean_d = nonzero.mean()
    std_d = nonzero.std(ddof=1) if len(nonzero) > 1 else 0.0
    cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
    return adi, cv2


def find_spikes(monthly: pd.DataFrame) -> pd.DataFrame:
    """A month is a spike if qty > SPIKE_MULTIPLIER x the item's own median non-zero
    monthly qty across its full available history. Threshold stated explicitly per item."""
    records = []
    for item, grp in monthly.groupby("itemcode"):
        grp = grp.sort_values("year_month")
        qty = grp["qty"].to_numpy()
        nonzero = qty[qty > 0]
        if len(nonzero) == 0:
            continue
        median_nonzero = np.median(nonzero)
        threshold = SPIKE_MULTIPLIER * median_nonzero
        spike_rows = grp[grp["qty"] > threshold]
        for _, r in spike_rows.iterrows():
            records.append({
                "itemcode": item, "year_month": r["year_month"], "qty": r["qty"], "sale": r["sale"],
                "item_median_nonzero_qty": median_nonzero, "threshold": threshold,
            })
    return pd.DataFrame(records)


def pull_transaction_detail(config_scope: dict, spikes: pd.DataFrame) -> pd.DataFrame:
    """Pulls the underlying transaction rows for every flagged spike (item, month)."""
    frames = []
    for _, r in spikes.iterrows():
        year, month = r["year_month"].split("-")
        start = f"{year}-{month}-01"
        end_month = int(month) + 1
        end_year = int(year)
        if end_month > 12:
            end_month = 1
            end_year += 1
        end = f"{end_year}-{end_month:02d}-01"
        sql = f"""
            SELECT itemcode, contractid, customerid, cusname, qty, sale, createDate, status
            FROM cube_Sale_APD
            WHERE itemcode = '{r['itemcode']}' AND division = 'PEM101' AND revenue_type = 'Omni Channel'
              AND status IN ('Actual','MPS') AND createDate >= '{start}' AND createDate < '{end}'
        """
        rows = run_query(sql)
        rows["year_month"] = r["year_month"]
        frames.append(rows)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_pilot_sales_monthly.csv"))
    monthly = monthly[monthly["year_month"] != "2026-08"]  # exclude partial month, consistent with backtest.py
    logger.info("Loaded monthly data: %d items, %d rows (2026-08 excluded as partial)", monthly["itemcode"].nunique(), len(monthly))

    spikes = find_spikes(monthly)
    spikes.to_csv(os.path.join(SUMMARY_DIR, "task3_spike_months.csv"), index=False)
    logger.info("Found %d spike months across %d items (threshold: qty > %sx item's own median non-zero month)",
                len(spikes), spikes["itemcode"].nunique() if len(spikes) else 0, SPIKE_MULTIPLIER)

    detail = pull_transaction_detail({}, spikes)
    detail.to_csv(os.path.join(DATA_DIR, "raw_spike_transaction_detail.csv"), index=False)
    logger.info("Pulled %d underlying transaction rows for all spike months", len(detail))

    # Per spike: number of orders (rows), distinct customers, largest single order
    spike_summary = detail.groupby(["itemcode", "year_month"]).agg(
        n_orders=("contractid", "nunique"), n_customers=("customerid", "nunique"),
        total_qty=("qty", "sum"), max_single_order_qty=("qty", "max"),
    ).reset_index()
    spike_summary["max_order_share_pct"] = (spike_summary["max_single_order_qty"] / spike_summary["total_qty"] * 100).round(1)
    spike_summary.to_csv(os.path.join(SUMMARY_DIR, "task3_spike_order_summary.csv"), index=False)

    # Recurring customers across spikes (table-wide, not per item)
    spike_customers = detail.groupby("customerid").agg(
        n_spike_months_involved=("year_month", "nunique"), n_spike_orders=("contractid", "nunique"),
        total_qty_in_spikes=("qty", "sum"),
    ).reset_index().sort_values("n_spike_months_involved", ascending=False)
    spike_customers.to_csv(os.path.join(SUMMARY_DIR, "task3_recurring_spike_customers.csv"), index=False)

    # Value in spike months vs normal months, across all 58 items
    spike_key = set(zip(spikes["itemcode"], spikes["year_month"]))
    monthly["is_spike"] = monthly.apply(lambda r: (r["itemcode"], r["year_month"]) in spike_key, axis=1)
    value_split = monthly.groupby("is_spike").agg(total_sale=("sale", "sum"), n_months=("year_month", "size")).reset_index()
    value_split.to_csv(os.path.join(SUMMARY_DIR, "task3_spike_vs_normal_value.csv"), index=False)
    logger.info("Value split (spike vs normal months):\n%s", value_split.to_string(index=False))

    # --- Task 4: recompute ADI/CV2 excluding spike months, compare classification ---
    class_records = []
    for item, grp in monthly.groupby("itemcode"):
        grp = grp.sort_values("year_month")
        qty_full = grp["qty"].to_numpy()
        adi_full, cv2_full = compute_adi_cv2(qty_full)
        cls_full = classify(adi_full, cv2_full)

        is_spike_mask = grp["is_spike"].to_numpy()
        qty_excl = qty_full[~is_spike_mask]  # remove spike months entirely from the series (shortens n too)
        adi_excl, cv2_excl = compute_adi_cv2(qty_excl)
        cls_excl = classify(adi_excl, cv2_excl)

        class_records.append({
            "itemcode": item, "n_spike_months": int(is_spike_mask.sum()),
            "adi_full": adi_full, "cv2_full": cv2_full, "classification_full": cls_full,
            "adi_excl_spikes": adi_excl, "cv2_excl_spikes": cv2_excl, "classification_excl_spikes": cls_excl,
            "classification_changed": cls_full != cls_excl,
        })
    class_df = pd.DataFrame(class_records)
    class_df.to_csv(os.path.join(SUMMARY_DIR, "task4_classification_with_without_spikes.csv"), index=False)
    n_changed = class_df["classification_changed"].sum()
    logger.info("Classification changed for %d of %d items when spikes are excluded", n_changed, len(class_df))

    print("\n" + "=" * 70)
    print("TASK 3 & 4 SUMMARY")
    print("=" * 70)
    print(f"Spike months found: {len(spikes)} across {spikes['itemcode'].nunique() if len(spikes) else 0} items (threshold: qty > {SPIKE_MULTIPLIER}x item's own median non-zero month)")
    print("\nValue split (spike vs normal months):")
    print(value_split.to_string(index=False))
    print("\nSpike order summary (first 20):")
    print(spike_summary.head(20).to_string(index=False))
    print("\nTop recurring spike customers:")
    print(spike_customers.head(10).to_string(index=False))
    print(f"\nItems whose demand classification changes when spikes are excluded: {n_changed} of {len(class_df)}")
    print(class_df[class_df["classification_changed"]].to_string(index=False))
