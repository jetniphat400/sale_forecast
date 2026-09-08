"""Per-item, per-candidate charts for the three focus codes: actual series with every rolling-
origin's 6-month test-window forecast stitched on, one small-multiple subplot per candidate model
(11 candidates), so each model's behaviour across all 7 origins is visible at a glance against the
same actual line.

Recomputes forecasts fresh (cheap — these are fast-fitting models on 31-month series) using the
exact same functions src/focus_item_model_selection.py already scored with, imported not copied,
so the chart is guaranteed to show the same forecasts the metrics were computed from.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import HOLDOUT, TOTAL_MONTHS, get_origins
from focus_item_model_selection import (FOCUS_ITEMS, build_item_and_type_series,
                                         individual_model_candidates, score_all_candidates_at_origin)
from leakage_guard import load_min_margin_days

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

MODEL_ORDER = ["Naive", "MA3", "MA6", "MA12", "SES", "Holt", "Croston", "SBA", "TSB",
               "Combination", "Top-down"]

if __name__ == "__main__":
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)

    for item in FOCUS_ITEMS:
        item_qty, item_months, type_qty, type_months, division, type_name = build_item_and_type_series(
            monthly, scope, item)

        # forecast_by_model[model] = full-length array, NaN outside forecast windows, filled with
        # each origin's own forecast inside its 6-month test window (origins do not overlap in
        # this project's ORIGIN_STEP=2/HOLDOUT=6 scheme except by 4 months, so a later origin's
        # forecast overwrites an earlier one in the shared months -- acceptable for visualization,
        # each origin's own window is also individually inspectable via the *_rolling_origin.csv).
        forecast_by_model = {m: np.full(TOTAL_MONTHS, np.nan) for m in MODEL_ORDER}
        for train_size in origins:
            train = item_qty[:train_size]
            test_len = min(HOLDOUT, TOTAL_MONTHS - train_size)
            if test_len < HOLDOUT:
                continue
            type_train = type_qty[:train_size]
            scored = score_all_candidates_at_origin(train, item_qty[train_size:train_size + HOLDOUT], type_train)
            for model in MODEL_ORDER:
                fc = scored[model]["forecast"]
                if fc is not None:
                    forecast_by_model[model][train_size:train_size + HOLDOUT] = fc

        fig, axes = plt.subplots(4, 3, figsize=(15, 14), sharex=True, sharey=True)
        axes = axes.flatten()
        for i, model in enumerate(MODEL_ORDER):
            ax = axes[i]
            ax.plot(range(TOTAL_MONTHS), item_qty, color="black", linewidth=1.2, label="Actual")
            ax.plot(range(TOTAL_MONTHS), forecast_by_model[model], color="tab:red", marker="o",
                    markersize=3, linewidth=1, label=model)
            for train_size in origins:
                ax.axvline(train_size, color="gray", linestyle=":", linewidth=0.4)
            ax.set_title(model, fontsize=10)
            ax.tick_params(labelsize=7)
        for j in range(len(MODEL_ORDER), len(axes)):
            axes[j].axis("off")
        fig.suptitle(f"{item} (division={division}, type={type_name})\n"
                     f"Rolling-origin forecasts (7 origins, dotted lines = origin train-size boundary) vs actual",
                     fontsize=12)
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        out_path = os.path.join(CHARTS_DIR, f"focus_{item}_all_candidates.png".replace("/", "_"))
        fig.savefig(out_path, dpi=110)
        plt.close(fig)
        print(f"Wrote {out_path}")
