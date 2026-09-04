"""Phase B, task B2: re-measure bias with EEE-F-FC-1040010002 separated out.

Phase A found this item accounts for ~51% of the 2025 Jan-Jul decline and that its real
2025-collapse/2026-recovery swing sits inside the existing backtest's test window (the last 6 of
31 months). This task tests directly whether the measured negative (under-forecasting) bias is
inflated by that one item's recovery, or whether it is a general property of demand across the
rest of the scope.

Method: for Category ("Fuse") and Type ("High Voltage Distribution Fuse Cutout", the item's own
Type), rebuild the aggregate monthly series WITH and WITHOUT this item's contribution, and run
the identical train/val/test (19/6/6) backtest (Combination + 6 base models) on both, for both
date keyings (createDate, forecast_date — reusing B1's re-keyed series). For Item level, "with"
is the mean bias across all 113 items with history; "without" is the mean across the other 112
(the item itself is simply excluded from the cross-item average, since item-level series are not
summed the way Category/Type are).

Reuses output/data/processed_full_category_sales_monthly_{createDate,forecastDate}.csv (B1) and
output/summary/b1_test_results_{key}.csv (B1, per-item test-set results) — nothing is re-pulled
from the database.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from backtest_rekeyed import (MA_WINDOWS, TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS, VAL_MONTHS,
                               compute_metrics)
from models import combination_forecast, get_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bias_item_isolation")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

FOCUS_ITEM = "EEE-F-FC-1040010002"
OTHER_FOCUS_ITEMS = ["HS-F-99-02110", "HS-F-99-0213"]
KEYS = ["createDate", "forecastDate"]
# Bias-is-mostly-artifact threshold, stated explicitly (a reasoned judgment, not a database
# fact): if excluding the item removes at least this fraction of the |Bias| magnitude, the
# earlier bias measurement is called "substantially an artifact of this one item."
ARTIFACT_FRACTION_THRESHOLD = 0.5


def build_group_series(monthly: pd.DataFrame, item_filter_col: str, item_filter_val: str,
                        exclude_item: str = None) -> np.ndarray:
    g = monthly[monthly[item_filter_col] == item_filter_val]
    if exclude_item is not None:
        g = g[g["itemcode"] != exclude_item]
    agg = g.groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
    return agg["qty"].to_numpy(dtype=float)


def backtest_series(qty: np.ndarray, models: dict) -> pd.DataFrame:
    if len(qty) != TOTAL_MONTHS:
        raise ValueError(f"Series has {len(qty)} months, expected {TOTAL_MONTHS}")
    train_val, test = qty[:TRAIN_MONTHS + VAL_MONTHS], qty[TRAIN_MONTHS + VAL_MONTHS:]
    rows = []
    for name, fn in models.items():
        fc = np.clip(fn(train_val, TEST_MONTHS), 0, None)
        rows.append({"model": name, **compute_metrics(test, fc, train_val)})
    combo = np.clip(combination_forecast(train_val, TEST_MONTHS, MA_WINDOWS), 0, None)
    rows.append({"model": "Combination", **compute_metrics(test, combo, train_val)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    item_row = scope[scope["code"] == FOCUS_ITEM].iloc[0]
    item_category, item_type = item_row["category"], item_row["type"]
    logger.info("%s belongs to Category=%s, Type=%s (from part1_category_scope_all_codes.csv)",
                FOCUS_ITEM, item_category, item_type)
    models = get_models(MA_WINDOWS)

    all_rows = []
    for key in KEYS:
        monthly = pd.read_csv(os.path.join(DATA_DIR, f"processed_full_category_sales_monthly_{key}.csv"))

        # ---- Category level: Fuse, with vs without the item ----
        cat_with = build_group_series(monthly, "category", item_category)
        cat_without = build_group_series(monthly, "category", item_category, exclude_item=FOCUS_ITEM)
        r_cat_with = backtest_series(cat_with, models)
        r_cat_with["level"], r_cat_with["group"], r_cat_with["variant"], r_cat_with["date_key"] = "Category", item_category, "with_item", key
        r_cat_without = backtest_series(cat_without, models)
        r_cat_without["level"], r_cat_without["group"], r_cat_without["variant"], r_cat_without["date_key"] = "Category", item_category, "without_item", key
        all_rows.extend([r_cat_with, r_cat_without])

        # Control: Surge Arrester category, entirely unaffected by this item's exclusion —
        # included so the "without" delta for Fuse can be judged against a series that should
        # show ~zero change, as a sanity check that the method isn't introducing spurious drift.
        cat_control = build_group_series(monthly, "category", "Surge Arrester")
        r_control = backtest_series(cat_control, models)
        r_control["level"], r_control["group"], r_control["variant"], r_control["date_key"] = "Category", "Surge Arrester (control)", "with_item", key
        all_rows.append(r_control)

        # ---- Type level: the item's own Type, with vs without ----
        typ_with = build_group_series(monthly, "type", item_type)
        typ_without = build_group_series(monthly, "type", item_type, exclude_item=FOCUS_ITEM)
        r_typ_with = backtest_series(typ_with, models)
        r_typ_with["level"], r_typ_with["group"], r_typ_with["variant"], r_typ_with["date_key"] = "Type", item_type, "with_item", key
        r_typ_without = backtest_series(typ_without, models)
        r_typ_without["level"], r_typ_without["group"], r_typ_without["variant"], r_typ_without["date_key"] = "Type", item_type, "without_item", key
        all_rows.extend([r_typ_with, r_typ_without])

        # ---- Item level: mean across all 113 items vs mean across the other 112 ----
        item_test = pd.read_csv(os.path.join(SUMMARY_DIR, f"b1_test_results_{key}.csv"))
        item_test = item_test[item_test["level"] == "Item"]
        with_all = item_test.groupby("model", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        with_all["level"] = "Item"; with_all["group"] = "all 113 items"; with_all["variant"] = "with_item"; with_all["date_key"] = key
        without_item = item_test[item_test["key"] != FOCUS_ITEM]
        without_112 = without_item.groupby("model", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean()
        without_112["level"] = "Item"; without_112["group"] = "other 112 items"; without_112["variant"] = "without_item"; without_112["date_key"] = key
        all_rows.extend([with_all, without_112])

    result_df = pd.concat(all_rows, ignore_index=True)
    result_df.to_csv(os.path.join(SUMMARY_DIR, "b2_bias_with_without_item.csv"), index=False)

    # ============================= COMPARISON TABLE =============================
    compare_rows = []
    for key in KEYS:
        for level, group in [("Category", item_category), ("Type", item_type), ("Item", None)]:
            if level == "Item":
                w = result_df[(result_df["date_key"] == key) & (result_df["level"] == "Item") & (result_df["variant"] == "with_item")]
                wo = result_df[(result_df["date_key"] == key) & (result_df["level"] == "Item") & (result_df["variant"] == "without_item")]
            else:
                w = result_df[(result_df["date_key"] == key) & (result_df["level"] == level) & (result_df["group"] == group) & (result_df["variant"] == "with_item")]
                wo = result_df[(result_df["date_key"] == key) & (result_df["level"] == level) & (result_df["group"] == group) & (result_df["variant"] == "without_item")]
            merged = w.merge(wo, on="model", suffixes=("_with", "_without"))
            merged["level"] = level
            merged["date_key"] = key
            merged["Bias_removed_by_exclusion"] = merged["Bias_with"] - merged["Bias_without"]
            merged["pct_of_with_Bias_removed"] = np.where(
                merged["Bias_with"].abs() > 1e-9,
                100 * merged["Bias_removed_by_exclusion"] / merged["Bias_with"].abs(), np.nan)
            compare_rows.append(merged)
    compare_df = pd.concat(compare_rows, ignore_index=True)
    compare_df.to_csv(os.path.join(SUMMARY_DIR, "b2_bias_comparison.csv"), index=False)

    # ============================= FOCUS ITEMS INDIVIDUALLY =============================
    focus_rows = []
    for key in KEYS:
        item_test = pd.read_csv(os.path.join(SUMMARY_DIR, f"b1_test_results_{key}.csv"))
        item_test = item_test[item_test["level"] == "Item"]
        for item in [FOCUS_ITEM] + OTHER_FOCUS_ITEMS:
            sub = item_test[(item_test["key"] == item) & (item_test["model"] == "Combination")]
            if len(sub):
                focus_rows.append({"date_key": key, "itemcode": item, **sub.iloc[0][["MAE", "RMSE", "Bias", "MASE"]].to_dict()})
    focus_df = pd.DataFrame(focus_rows)
    focus_df.to_csv(os.path.join(SUMMARY_DIR, "b2_focus_items_bias.csv"), index=False)

    # ============================= CONSOLE OUTPUT =============================
    print("\n" + "#" * 92)
    print("# B2: BIAS WITH vs WITHOUT EEE-F-FC-1040010002")
    print("#" * 92)
    print(f"\n{FOCUS_ITEM} belongs to Category={item_category}, Type={item_type}.")

    for key in KEYS:
        print(f"\n{'='*92}\nDATE KEY: {key}\n{'='*92}")
        for level, group in [("Category", item_category), ("Type", item_type), ("Item", "all items")]:
            sub = compare_df[(compare_df["date_key"] == key) & (compare_df["level"] == level)].sort_values("model")
            print(f"\n--- {level} ({group}) ---")
            print(sub[["model", "Bias_with", "Bias_without", "Bias_removed_by_exclusion",
                        "pct_of_with_Bias_removed", "MAE_with", "MAE_without"]].round(2).to_string(index=False))

        # Control check
        ctrl = result_df[(result_df["date_key"] == key) & (result_df["group"] == "Surge Arrester (control)") & (result_df["model"] == "Combination")]
        combo_fuse_with = result_df[(result_df["date_key"] == key) & (result_df["level"] == "Category") & (result_df["group"] == item_category) & (result_df["variant"] == "with_item") & (result_df["model"] == "Combination")]
        if len(ctrl) and len(combo_fuse_with):
            print(f"\nControl check (Surge Arrester, untouched by this exclusion): Combination Bias = "
                  f"{ctrl.iloc[0]['Bias']:.2f} (this category's own bias, for reference — not expected to "
                  f"change since it does not contain the excluded item).")

        combo_row = compare_df[(compare_df["date_key"] == key) & (compare_df["level"] == "Category") & (compare_df["model"] == "Combination")]
        if len(combo_row):
            pct = combo_row.iloc[0]["pct_of_with_Bias_removed"]
            verdict = ("SUBSTANTIALLY AN ARTIFACT of this one item" if abs(pct) >= 100 * ARTIFACT_FRACTION_THRESHOLD
                       else "PERSISTS beyond this one item — not just an artifact")
            print(f"\nCombination, Category level: excluding {FOCUS_ITEM} removes {pct:.1f}% of the |Bias| "
                  f"magnitude -> {verdict}.")

    print(f"\n--- FOCUS ITEMS INDIVIDUALLY (Combination, test set) ---")
    print(focus_df.round(2).to_string(index=False))

    print("\n--- INTERPRETATION (stated per instruction) ---")
    for key in KEYS:
        for level, group in [("Category", item_category), ("Type", item_type)]:
            row = compare_df[(compare_df["date_key"] == key) & (compare_df["level"] == level) & (compare_df["model"] == "Combination")]
            if len(row):
                r = row.iloc[0]
                if abs(r["pct_of_with_Bias_removed"]) >= 100 * ARTIFACT_FRACTION_THRESHOLD:
                    print(f"[{key}] {level} ({group}), Combination: {r['pct_of_with_Bias_removed']:.1f}% of bias "
                          f"removed by excluding {FOCUS_ITEM} — EARLIER BIAS MEASUREMENT WAS SUBSTANTIALLY AN "
                          f"ARTIFACT of this one item at this level.")
                else:
                    print(f"[{key}] {level} ({group}), Combination: only {r['pct_of_with_Bias_removed']:.1f}% of "
                          f"bias removed — remaining bias ({r['Bias_without']:.1f} units/month) PERSISTS across "
                          f"the rest of the group and should still inform safety stock, though at a smaller "
                          f"magnitude than the unadjusted figure implied.")

    print("\nOutputs: output/summary/b2_bias_with_without_item.csv, b2_bias_comparison.csv, b2_focus_items_bias.csv")
