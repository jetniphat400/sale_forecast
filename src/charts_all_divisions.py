"""Phase C step 2: per-division backtest charts (actual vs Top-down test-set forecast, summed
across each division's forecast-status items) plus the three focus codes individually.

Reuses src/item_level_reconciliation.py's forecast_all_approaches (Top-down branch) and this
project's fixed TRAIN(19)+VAL(6)+TEST(6)=31-month split (src/backtest_rekeyed.py), applied to the
335-item, 5-division scope with division-qualified Type keys (src/forward_test_all_divisions.py's
build_item_series_div/build_type_series_div, imported not copied).
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS, VAL_MONTHS
from forward_test_all_divisions import build_item_series_div, build_type_series_div
from item_level_reconciliation import forecast_all_approaches

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

if __name__ == "__main__":
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))

    item_series = build_item_series_div(monthly, scope, TOTAL_MONTHS)
    type_series = build_type_series_div(monthly, TOTAL_MONTHS)
    fc_test = forecast_all_approaches(item_series, type_series, TRAIN_MONTHS + VAL_MONTHS, TEST_MONTHS)
    topdown_test = fc_test["Top-down"]

    item_to_division = scope.set_index("code")["division"].to_dict()

    # ---- Per-division: actual total qty vs Top-down test forecast, summed across items ----
    divisions = sorted(scope["division"].unique())
    fig, axes = plt.subplots(len(divisions), 1, figsize=(10, 3.2 * len(divisions)), sharex=False)
    if len(divisions) == 1:
        axes = [axes]
    for ax, div in zip(axes, divisions):
        codes = [c for c in item_series if item_to_division.get(c) == div]
        actual_total = np.sum([item_series[c][0] for c in codes], axis=0)
        forecast_total = np.sum([topdown_test[c] for c in codes if c in topdown_test], axis=0)
        ax.plot(range(TOTAL_MONTHS), actual_total, label="Actual (all items summed)", color="black", linewidth=1.3)
        ax.plot(range(TRAIN_MONTHS + VAL_MONTHS, TOTAL_MONTHS), forecast_total, label="Top-down forecast (test)",
                 color="tab:red", marker="o")
        ax.axvline(TRAIN_MONTHS + VAL_MONTHS, color="gray", linestyle="--", linewidth=1)
        ax.set_title(f"{div} — {len(codes)} items, total qty")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "phaseC_step2_per_division_actual_vs_topdown.png"), dpi=120)
    plt.close(fig)

    # ---- Focus items individually ----
    for item in FOCUS_ITEMS:
        if item not in item_series:
            continue
        qty, type_key, cat = item_series[item]
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(range(TOTAL_MONTHS), qty, label="Actual", color="black", linewidth=1.5)
        ax.plot(range(TRAIN_MONTHS + VAL_MONTHS, TOTAL_MONTHS), topdown_test[item], label="Top-down forecast",
                 color="tab:red", marker="o", linewidth=1.5)
        ax.axvline(TRAIN_MONTHS + VAL_MONTHS, color="gray", linestyle="--", linewidth=1)
        ax.set_title(f"{item} (Type={type_key})\nPhase C step 2, Top-down combination, forecast_date-keyed")
        ax.set_xlabel("Month index (0-30)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, f"phaseC_step2_focus_{item.replace('/', '_')}.png"), dpi=120)
        plt.close(fig)

    print("Charts written: output/charts/phaseC_step2_per_division_actual_vs_topdown.png, "
          "phaseC_step2_focus_<item>.png (3 focus items)")
