"""Task 1 (Modeler, single-agent per the task brief — Task 1/2/3 are sequential/dependent):
does excluding EEE-F-FC-1040010002 make the 7th-origin forecast_date-vs-createDate reversal
(found in src/leakage_check_forecastdate.py, output/summary/b4_per_origin_comparison.csv)
disappear at Category, Type, and Item level?

Method: reuses src/backtest_rekeyed.py's exact rolling-origin machinery (get_origins,
compute_metrics, run_rolling_origin, MIN_TRAIN_MONTHS=13/ORIGIN_STEP=2/HOLDOUT=6 -> 7 origins)
and src/bias_item_isolation.py's build_group_series pattern (rebuild Category/Type series with
the item excluded), extended from B2's single train/val/test split to all 7 rolling origins.

Category level: "Fuse" rebuilt with vs without EEE-F-FC-1040010002.
Type level: "High Voltage Distribution Fuse Cutout" (the item's own Type) rebuilt with vs without.
Control: "Surge Arrester" (untouched by this exclusion, recomputed fresh here for self-consistency).
Item level: does NOT need rebuilding — src/backtest_rekeyed.py's Item-level rolling-origin output
(output/summary/b1_rolling_origin_results_{key}.csv) already scores every item independently;
"with"/"without" here means the cross-item MEAN with vs without this one item in it, same
convention as B2's item-level comparison (the item is excluded from the average, not resummed).

Only the Combination model is used for the primary comparison (this project's selected approach,
STATUS.md Phase 2), consistent with B4's per-origin comparison. Base models are not rescored here
since B4 established Combination as the comparison vehicle for this exact question.

Outputs: output/summary/task1_rolling_origin_item_excluded.csv (long form, per level/group/variant/
origin/date_key), output/summary/task1_reversal_verdict.csv (per level, does origin 7 flip once
excluded), chart output/charts/task1_seven_origin_with_without_item.png.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from backtest_rekeyed import (HOLDOUT, TOTAL_MONTHS, compute_metrics, get_origins,
                               run_rolling_origin)
from bias_item_isolation import build_group_series
from models import get_models, combination_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task1_item_isolation_rolling_origin")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

FOCUS_ITEM = "EEE-F-FC-1040010002"
KEYS = ["createDate", "forecastDate"]
MA_WINDOWS = [3, 6, 12]


def rolling_origin_single_series(qty: np.ndarray, models: dict) -> pd.DataFrame:
    """Combination-only rolling-origin scoring of one 1-D monthly series, using the exact
    same origin/holdout mechanics as backtest_rekeyed.run_rolling_origin."""
    n = len(qty)
    origins = get_origins(n, HOLDOUT)
    rows = []
    for origin_idx, train_size in enumerate(origins, start=1):
        train = qty[:train_size]
        test = qty[train_size:train_size + HOLDOUT]
        if len(test) < HOLDOUT:
            continue
        combo = np.clip(combination_forecast(train, HOLDOUT, MA_WINDOWS), 0, None)
        m = compute_metrics(test, combo, train)
        rows.append({"origin": origin_idx, "train_size": train_size, "model": "Combination", **m})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    item_row = scope[scope["code"] == FOCUS_ITEM].iloc[0]
    item_category, item_type = item_row["category"], item_row["type"]
    logger.info("%s belongs to Category=%s, Type=%s", FOCUS_ITEM, item_category, item_type)
    models = get_models(MA_WINDOWS)

    all_rows = []
    for key in KEYS:
        monthly = pd.read_csv(os.path.join(DATA_DIR, f"processed_full_category_sales_monthly_{key}.csv"))

        groups = {
            ("Category", item_category, "with_item"): build_group_series(monthly, "category", item_category),
            ("Category", item_category, "without_item"): build_group_series(monthly, "category", item_category, exclude_item=FOCUS_ITEM),
            ("Category", "Surge Arrester (control)", "with_item"): build_group_series(monthly, "category", "Surge Arrester"),
            ("Type", item_type, "with_item"): build_group_series(monthly, "type", item_type),
            ("Type", item_type, "without_item"): build_group_series(monthly, "type", item_type, exclude_item=FOCUS_ITEM),
        }
        for (level, group, variant), qty in groups.items():
            if len(qty) != TOTAL_MONTHS:
                raise ValueError(f"[{key}] {level}/{group}/{variant}: series has {len(qty)} months, expected {TOTAL_MONTHS}")
            scored = rolling_origin_single_series(qty, models)
            scored["level"], scored["group"], scored["variant"], scored["date_key"] = level, group, variant, key
            all_rows.append(scored)

    category_type_df = pd.concat(all_rows, ignore_index=True)

    # ============================= ITEM LEVEL: cross-item mean, with vs without =============================
    item_rows = []
    for key in KEYS:
        ro = pd.read_csv(os.path.join(SUMMARY_DIR, f"b1_rolling_origin_results_{key}.csv"))
        ro_item = ro[(ro["level"] == "Item") & (ro["model"] == "Combination")]
        n_items_with_history = ro_item["key"].nunique()
        with_all = ro_item.groupby(["origin", "train_size"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        with_all["level"], with_all["group"], with_all["variant"], with_all["date_key"] = \
            "Item", f"all {n_items_with_history} items with history", "with_item", key
        without_focus = ro_item[ro_item["key"] != FOCUS_ITEM]
        without_all = without_focus.groupby(["origin", "train_size"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        without_all["level"], without_all["group"], without_all["variant"], without_all["date_key"] = \
            "Item", f"other {n_items_with_history - 1} items", "without_item", key
        item_rows.extend([with_all, without_all])
        logger.info("[%s] Item level: %d items with history in b1_rolling_origin_results (mean computed with vs "
                    "without %s excluded from the cross-item average, same convention as B2)", key, n_items_with_history, FOCUS_ITEM)
    item_df = pd.concat(item_rows, ignore_index=True)

    result_df = pd.concat([category_type_df, item_df], ignore_index=True)
    result_df.to_csv(os.path.join(SUMMARY_DIR, "task1_rolling_origin_item_excluded.csv"), index=False)

    # ============================= PER-ORIGIN createDate vs forecastDate, per level/group/variant =============================
    compare_rows = []
    groups_seen = result_df[["level", "group", "variant"]].drop_duplicates()
    for _, g in groups_seen.iterrows():
        level, group, variant = g["level"], g["group"], g["variant"]
        cd = result_df[(result_df["level"] == level) & (result_df["group"] == group) & (result_df["variant"] == variant)
                        & (result_df["date_key"] == "createDate")][["origin", "train_size", "MAE"]].rename(columns={"MAE": "MAE_createDate"})
        fd = result_df[(result_df["level"] == level) & (result_df["group"] == group) & (result_df["variant"] == variant)
                        & (result_df["date_key"] == "forecastDate")][["origin", "train_size", "MAE"]].rename(columns={"MAE": "MAE_forecastDate"})
        merged = cd.merge(fd, on=["origin", "train_size"])
        if len(merged) == 0:
            continue
        merged["level"], merged["group"], merged["variant"] = level, group, variant
        merged["forecastDate_better"] = merged["MAE_forecastDate"] < merged["MAE_createDate"]
        merged["pct_diff"] = 100 * (merged["MAE_forecastDate"] - merged["MAE_createDate"]) / merged["MAE_createDate"]
        compare_rows.append(merged)
    compare_df = pd.concat(compare_rows, ignore_index=True)
    compare_df.to_csv(os.path.join(SUMMARY_DIR, "task1_per_origin_with_without_comparison.csv"), index=False)

    # ============================= VERDICT: does the origin-7 reversal disappear without the item? =============================
    origins_list = get_origins(TOTAL_MONTHS, HOLDOUT)
    last_train_size = origins_list[-1]
    verdict_rows = []
    for level, group_with, group_without in [
        ("Category", item_category, item_category),
        ("Type", item_type, item_type),
        ("Item", None, None),
    ]:
        if level == "Item":
            with_row = compare_df[(compare_df["level"] == "Item") & (compare_df["variant"] == "with_item") & (compare_df["train_size"] == last_train_size)]
            without_row = compare_df[(compare_df["level"] == "Item") & (compare_df["variant"] == "without_item") & (compare_df["train_size"] == last_train_size)]
        else:
            with_row = compare_df[(compare_df["level"] == level) & (compare_df["group"] == group_with) & (compare_df["variant"] == "with_item") & (compare_df["train_size"] == last_train_size)]
            without_row = compare_df[(compare_df["level"] == level) & (compare_df["group"] == group_without) & (compare_df["variant"] == "without_item") & (compare_df["train_size"] == last_train_size)]
        if len(with_row) == 0 or len(without_row) == 0:
            continue
        w, wo = with_row.iloc[0], without_row.iloc[0]
        verdict_rows.append({
            "level": level, "origin7_train_size": last_train_size,
            "pct_diff_with_item": w["pct_diff"], "forecastDate_better_with_item": w["forecastDate_better"],
            "pct_diff_without_item": wo["pct_diff"], "forecastDate_better_without_item": wo["forecastDate_better"],
            "reversal_disappears": bool(w["forecastDate_better"] and not wo["forecastDate_better"]),
        })
    verdict_df = pd.DataFrame(verdict_rows)
    verdict_df.to_csv(os.path.join(SUMMARY_DIR, "task1_reversal_verdict.csv"), index=False)

    # ============================= CHART =============================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharex=False)
    level_groups = [
        ("Category", item_category, item_category, "Category: Fuse"),
        ("Type", item_type, item_type, "Type: High Voltage Distribution Fuse Cutout"),
        ("Item", None, None, "Item level: cross-item mean"),
    ]
    for ax, (level, gw, gwo, title) in zip(axes, level_groups):
        if level == "Item":
            w = compare_df[(compare_df["level"] == "Item") & (compare_df["variant"] == "with_item")].sort_values("train_size")
            wo = compare_df[(compare_df["level"] == "Item") & (compare_df["variant"] == "without_item")].sort_values("train_size")
        else:
            w = compare_df[(compare_df["level"] == level) & (compare_df["group"] == gw) & (compare_df["variant"] == "with_item")].sort_values("train_size")
            wo = compare_df[(compare_df["level"] == level) & (compare_df["group"] == gwo) & (compare_df["variant"] == "without_item")].sort_values("train_size")
        ax.plot(w["train_size"], w["MAE_createDate"], marker="o", color="tab:blue", linestyle="-", label="createDate, WITH item")
        ax.plot(w["train_size"], w["MAE_forecastDate"], marker="o", color="tab:red", linestyle="-", label="forecast_date, WITH item")
        ax.plot(wo["train_size"], wo["MAE_createDate"], marker="s", color="tab:blue", linestyle="--", label="createDate, WITHOUT item")
        ax.plot(wo["train_size"], wo["MAE_forecastDate"], marker="s", color="tab:red", linestyle="--", label="forecast_date, WITHOUT item")
        ax.axvline(last_train_size, color="gray", linestyle=":", linewidth=1)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Train size (months) at this origin")
        ax.set_ylabel("Combination test MAE")
        ax.legend(fontsize=7)
    fig.suptitle(f"Seven rolling origins: createDate vs forecast_date MAE, with vs without {FOCUS_ITEM}", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "task1_seven_origin_with_without_item.png"), dpi=130)
    plt.close(fig)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 100)
    print(f"# TASK 1: does excluding {FOCUS_ITEM} make the origin-7 reversal disappear?")
    print("#" * 100)
    for level, gw, gwo in [("Category", item_category, item_category), ("Type", item_type, item_type), ("Item", None, None)]:
        print(f"\n--- {level} ---")
        if level == "Item":
            w = compare_df[(compare_df["level"] == "Item") & (compare_df["variant"] == "with_item")].sort_values("train_size")
            wo = compare_df[(compare_df["level"] == "Item") & (compare_df["variant"] == "without_item")].sort_values("train_size")
        else:
            w = compare_df[(compare_df["level"] == level) & (compare_df["group"] == gw) & (compare_df["variant"] == "with_item")].sort_values("train_size")
            wo = compare_df[(compare_df["level"] == level) & (compare_df["group"] == gwo) & (compare_df["variant"] == "without_item")].sort_values("train_size")
        print("WITH item:")
        print(w[["origin", "train_size", "MAE_createDate", "MAE_forecastDate", "pct_diff", "forecastDate_better"]].round(2).to_string(index=False))
        print("WITHOUT item:")
        print(wo[["origin", "train_size", "MAE_createDate", "MAE_forecastDate", "pct_diff", "forecastDate_better"]].round(2).to_string(index=False))

    print("\n--- VERDICT (origin 7, train_size=%d) ---" % last_train_size)
    print(verdict_df.round(2).to_string(index=False))
    for _, r in verdict_df.iterrows():
        if r["reversal_disappears"]:
            print(f"[{r['level']}] Reversal DISAPPEARS once {FOCUS_ITEM} is excluded (WITH: forecast_date better "
                  f"by {abs(r['pct_diff_with_item']):.1f}%; WITHOUT: forecast_date now WORSE by "
                  f"{r['pct_diff_without_item']:.1f}%).")
        else:
            print(f"[{r['level']}] Reversal PERSISTS without {FOCUS_ITEM} (WITH: pct_diff={r['pct_diff_with_item']:.1f}%; "
                  f"WITHOUT: pct_diff={r['pct_diff_without_item']:.1f}%) — the item is NOT the explanation at this level.")

    print("\nOutputs: output/summary/task1_rolling_origin_item_excluded.csv, "
          "task1_per_origin_with_without_comparison.csv, task1_reversal_verdict.csv")
    print("Chart: output/charts/task1_seven_origin_with_without_item.png")
