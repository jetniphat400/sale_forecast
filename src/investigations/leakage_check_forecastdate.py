"""Phase B follow-up (single Validator task, per AGENTS.md — re-examines one series, results
must be interpreted together, not split): test whether re-keying's train/val/test improvement is
leakage from future-dated forecast_date rows, and resolve why rolling-origin disagreed.

INVESTIGATION task. No model choice written to config.yaml. Does not modify any existing data
file — reads output/data/raw_full_category_sales.csv (already pulled, snapshot frozen by
src/load_data_full.py) and output/summary/b1_rolling_origin_results_{key}.csv (already computed
by src/backtest_rekeyed.py), and writes new output only.

Hypothesis under test: forecast_date is a delivery date, so at the pull, some rows carry a
forecast_date AFTER the pull date — demand already known to be coming. If such rows sit inside
the evaluated test window, the model would be scored on months partly built from demand that was
visible at forecast time, inflating apparent accuracy (leakage), not reflecting real forecasting
skill.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from backtest_rekeyed import (HOLDOUT, MA_WINDOWS, TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS,
                               VAL_MONTHS, build_level_series, compute_metrics, get_origins,
                               run_rolling_origin, run_train_val_test)
from leakage_guard import load_min_margin_days
from models import get_models
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("leakage_check_forecastdate")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

COMMON_MONTHS = pd.period_range("2024-01", "2026-07", freq="M")  # fixed by src/load_data_full.py, B1


if __name__ == "__main__":
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    monthly_fd = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv"))
    pull_date = pd.Timestamp(monthly_fd["snapshot_pull_date"].iloc[0])
    logger.info("Pull date (frozen snapshot, from processed_full_category_sales_monthly_forecastDate.csv's "
                "snapshot_pull_date column): %s", pull_date)

    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw = raw.merge(scope[["code", "category", "type"]].rename(columns={"code": "itemcode"}), on="itemcode", how="left")

    # ================= PART 1: QUANTIFY FUTURE-DATED ROWS =================
    print("\n" + "#" * 92)
    print("# PART 1: QUANTIFY FUTURE-DATED (relative to pull date) forecast_date ROWS")
    print("#" * 92)
    print(f"\nPull date: {pull_date}. Source: raw_full_category_sales.csv ({len(raw)} rows, same "
          f"snapshot as the forecast_date-keyed monthly file's snapshot_pull_date column.")

    future = raw[raw["forecast_date"] > pull_date].copy()
    print(f"\nRows with forecast_date > pull date, ANYWHERE in the raw pull (unrestricted by any "
          f"analysis window): {len(future)} of {len(raw)} ({100*len(future)/len(raw):.3f}%). "
          f"Qty = {future['qty'].sum():,.0f}. Sale value = THB {future['sale'].sum():,.2f}.")

    future["fc_year_month"] = future["forecast_date"].dt.to_period("M")
    by_month = future.groupby("fc_year_month", as_index=False).agg(n_rows=("qty", "size"), qty=("qty", "sum"), sale=("sale", "sum"))
    by_month.to_csv(os.path.join(SUMMARY_DIR, "b4_future_dated_rows_by_month.csv"), index=False)
    print("\nDistribution by forecast_date month:")
    print(by_month.to_string(index=False))

    by_item = future.groupby("itemcode", as_index=False).agg(n_rows=("qty", "size"), qty=("qty", "sum"), sale=("sale", "sum")).sort_values("qty", ascending=False)
    by_item.to_csv(os.path.join(SUMMARY_DIR, "b4_future_dated_rows_by_item.csv"), index=False)
    print(f"\n{by_item['itemcode'].nunique()} distinct items carry a future-dated row. Top 10 by qty:")
    print(by_item.head(10).to_string(index=False))

    by_level = future.groupby(["category", "type"], as_index=False).agg(n_rows=("qty", "size"), qty=("qty", "sum"), sale=("sale", "sum"))
    by_level.to_csv(os.path.join(SUMMARY_DIR, "b4_future_dated_rows_by_level.csv"), index=False)
    print("\nDistribution by Category/Type:")
    print(by_level.to_string(index=False))

    raw["fc_year_month"] = raw["forecast_date"].dt.to_period("M")
    in_window_future = raw[(raw["forecast_date"] > pull_date) & (raw["fc_year_month"].isin(set(COMMON_MONTHS)))]
    test_window_months = COMMON_MONTHS[-TEST_MONTHS:]
    in_test_window_future = raw[(raw["forecast_date"] > pull_date) & (raw["fc_year_month"].isin(set(test_window_months)))]
    print(f"\n*** DECISIVE CHECK: rows with forecast_date > pull date that fall WITHIN the 31-month "
          f"common window (2024-01 to 2026-07): {len(in_window_future)}.")
    print(f"*** Rows with forecast_date > pull date that fall WITHIN the final 6-month TEST window "
          f"({test_window_months[0]} to {test_window_months[-1]}): {len(in_test_window_future)}.")
    if len(in_window_future) == 0:
        print("\nCONFIRMED, HIGH CONFIDENCE: zero rows with forecast_date after the pull date fall inside "
              "the 31-month window used for every backtest in this project (and therefore inside every "
              "rolling-origin test window too, all of which are subsets of these 31 months). This is because "
              "the window was fixed (src/load_data_full.py, Phase B1) to end at 2026-07, and the pull "
              "happened on 2026-09-02 — over a month AFTER the window's last month fully elapsed. All "
              f"{len(future)} future-dated rows found above fall in {sorted(future['fc_year_month'].astype(str).unique())} "
              "— entirely AFTER the window ends, not inside it.")
    pd.DataFrame([{"pull_date": str(pull_date), "n_future_rows_total": len(future),
                    "qty_future_total": future["qty"].sum(), "sale_future_total": future["sale"].sum(),
                    "n_future_rows_in_31mo_window": len(in_window_future),
                    "n_future_rows_in_test_window": len(in_test_window_future)}]).to_csv(
        os.path.join(SUMMARY_DIR, "b4_future_dated_window_overlap_summary.csv"), index=False)

    # ================= PART 2: RE-RUN WITHOUT LEAKED ROWS =================
    print("\n" + "#" * 92)
    print("# PART 2: RE-RUN WITHOUT FUTURE-DATED ROWS — 3-WAY COMPARISON")
    print("#" * 92)

    # Build the "no-leak" forecast_date series: same filters as B1's forecast_date keying, PLUS
    # excluding forecast_date > pull_date.
    d = raw.copy()
    n_before = len(d)
    d = d.dropna(subset=["forecast_date"])
    d = d[d["forecast_date"] >= d["createDate"]]  # same negative-interval exclusion as B1
    n_after_b1_filters = len(d)
    d_noleak = d[d["forecast_date"] <= pull_date]
    n_excluded_for_leakage = len(d) - len(d_noleak)
    print(f"\n{n_before} raw rows -> {n_after_b1_filters} after B1's existing forecast_date filters "
          f"(null/negative-interval excluded) -> {len(d_noleak)} after ALSO excluding forecast_date > "
          f"pull_date ({n_excluded_for_leakage} additional rows excluded here).")

    d_noleak = d_noleak.copy()
    d_noleak["year_month"] = d_noleak["forecast_date"].dt.to_period("M")
    monthly_noleak = d_noleak[d_noleak["year_month"].isin(set(COMMON_MONTHS))].groupby(
        ["itemcode", "year_month"], as_index=False).agg(qty=("qty", "sum"), sale=("sale", "sum"))
    forecastable_codes = sorted(scope["code"].unique())
    full_index = pd.MultiIndex.from_product([forecastable_codes, COMMON_MONTHS], names=["itemcode", "year_month"])
    monthly_noleak_full = monthly_noleak.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()
    monthly_noleak_full = monthly_noleak_full.merge(scope[["code", "category", "type"]].rename(columns={"code": "itemcode"}), on="itemcode", how="left")
    monthly_noleak_full.to_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDateNoLeak.csv"), index=False)

    # Verify numerically identical to the existing forecast_date-keyed file (expected, given 0 in-window rows excluded)
    monthly_fd_sorted = monthly_fd[["itemcode", "year_month", "qty", "sale"]].sort_values(["itemcode", "year_month"]).reset_index(drop=True)
    monthly_noleak_sorted = monthly_noleak_full[["itemcode", "year_month", "qty", "sale"]].sort_values(["itemcode", "year_month"]).reset_index(drop=True)
    monthly_noleak_sorted["year_month"] = monthly_noleak_sorted["year_month"].astype(str)
    monthly_fd_sorted["year_month"] = monthly_fd_sorted["year_month"].astype(str)
    identical = monthly_fd_sorted.equals(monthly_noleak_sorted)
    max_qty_diff = (monthly_fd_sorted["qty"] - monthly_noleak_sorted["qty"]).abs().max()
    print(f"\nVerification: forecast_date-keyed (as-is) vs forecast_date-keyed-no-leak monthly grids are "
          f"{'IDENTICAL' if identical else 'DIFFERENT'} (max qty difference across all item-months: {max_qty_diff}).")

    models = get_models(MA_WINDOWS)
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    min_margin_days = load_min_margin_days(_config)
    logger.info("Leakage guard (Task 2): min_margin_days=%d. All three keyings below share the same "
                "underlying raw pull, so the same frozen pull_date=%s applies to all of them, "
                "including forecastDateNoLeak (derived from the same pull, no separate snapshot).",
                min_margin_days, pull_date)
    keyed_monthly = {
        "createDate": pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly_createDate.csv")),
        "forecastDate": monthly_fd,
        "forecastDateNoLeak": monthly_noleak_full,
    }
    ro_all, val_all, test_all = {}, {}, {}
    for key, m in keyed_monthly.items():
        series = build_level_series(m, scope)
        ro_all[key] = run_rolling_origin(series, models, pull_date, min_margin_days)
        val_all[key], test_all[key] = run_train_val_test(series, models, pull_date, min_margin_days)
        for df in (ro_all[key], val_all[key], test_all[key]):
            df["date_key"] = key
    ro_all["forecastDateNoLeak"].to_csv(os.path.join(SUMMARY_DIR, "b4_rolling_origin_results_forecastDateNoLeak.csv"), index=False)
    test_all["forecastDateNoLeak"].to_csv(os.path.join(SUMMARY_DIR, "b4_test_results_forecastDateNoLeak.csv"), index=False)

    # ---- 3-way comparison, train/val/test (test stage), mean per level+model ----
    test_summary = {k: v.groupby(["level", "model"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean() for k, v in test_all.items()}
    three_way_test = test_summary["createDate"].merge(
        test_summary["forecastDate"], on=["level", "model"], suffixes=("_createDate", "_forecastDate")
    ).merge(
        test_summary["forecastDateNoLeak"].rename(columns={c: f"{c}_forecastDateNoLeak" for c in ["MAE", "RMSE", "Bias", "MASE"]}),
        on=["level", "model"]
    )
    three_way_test.to_csv(os.path.join(SUMMARY_DIR, "b4_three_way_comparison_test.csv"), index=False)

    ro_summary = {k: v.groupby(["level", "model"], as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean() for k, v in ro_all.items()}
    three_way_ro = ro_summary["createDate"].merge(
        ro_summary["forecastDate"], on=["level", "model"], suffixes=("_createDate", "_forecastDate")
    ).merge(
        ro_summary["forecastDateNoLeak"].rename(columns={c: f"{c}_forecastDateNoLeak" for c in ["MAE", "RMSE", "Bias", "MASE"]}),
        on=["level", "model"]
    )
    three_way_ro.to_csv(os.path.join(SUMMARY_DIR, "b4_three_way_comparison_rolling_origin.csv"), index=False)

    print("\n--- TRAIN/VAL/TEST (test stage), mean MAE per level+model, 3-way ---")
    for level in ["Category", "Type", "Item"]:
        sub = three_way_test[three_way_test["level"] == level].sort_values("MAE_createDate")
        print(f"\n--- {level} ---")
        print(sub[["model", "MAE_createDate", "MAE_forecastDate", "MAE_forecastDateNoLeak"]].round(2).to_string(index=False))

    combo_test = three_way_test[three_way_test["model"] == "Combination"]
    leak_effect = (combo_test["MAE_forecastDate"] - combo_test["MAE_forecastDateNoLeak"]).abs().max()
    print(f"\nMax |MAE(forecastDate) - MAE(forecastDateNoLeak)| across levels, Combination: {leak_effect:.6f}")
    if leak_effect < 1e-6:
        print("CONCLUSION (Part 2): excluding future-dated-relative-to-pull rows changes NOTHING — there were "
              "none inside the evaluated window (Part 1). The train/val/test improvement under forecast_date-"
              "keying is THEREFORE NOT explained by this specific leakage mechanism: it is genuine with respect "
              "to this hypothesis, and this specific proposed cause is not what is happening. (This does not by "
              "itself prove the improvement is meaningful in every sense — see Part 3.)")
    else:
        print(f"CONCLUSION (Part 2): excluding future-dated rows changed results by up to {leak_effect:.2f} MAE — "
              "some leakage-attributable effect exists, quantified above.")

    # ================= PART 3: RESOLVE THE DIRECTION CONFLICT =================
    print("\n" + "#" * 92)
    print("# PART 3: WHY DID ROLLING-ORIGIN AND TRAIN/VAL/TEST DISAGREE? (window-position test)")
    print("#" * 92)

    ro_cd = pd.read_csv(os.path.join(SUMMARY_DIR, "b1_rolling_origin_results_createDate.csv"))
    ro_fd = pd.read_csv(os.path.join(SUMMARY_DIR, "b1_rolling_origin_results_forecastDate.csv"))
    per_origin_rows = []
    for level in ["Category", "Type", "Item"]:
        cd = ro_cd[(ro_cd["level"] == level) & (ro_cd["model"] == "Combination")].groupby(
            ["origin", "train_size"], as_index=False)["MAE"].mean().rename(columns={"MAE": "MAE_createDate"})
        fd = ro_fd[(ro_fd["level"] == level) & (ro_fd["model"] == "Combination")].groupby(
            ["origin", "train_size"], as_index=False)["MAE"].mean().rename(columns={"MAE": "MAE_forecastDate"})
        merged = cd.merge(fd, on=["origin", "train_size"])
        merged["level"] = level
        merged["forecastDate_better"] = merged["MAE_forecastDate"] < merged["MAE_createDate"]
        merged["pct_diff"] = 100 * (merged["MAE_forecastDate"] - merged["MAE_createDate"]) / merged["MAE_createDate"]
        per_origin_rows.append(merged)
    per_origin_df = pd.concat(per_origin_rows, ignore_index=True)
    per_origin_df.to_csv(os.path.join(SUMMARY_DIR, "b4_per_origin_comparison.csv"), index=False)

    print("\n--- Per-origin Combination MAE, createDate vs forecast_date, all 3 levels ---")
    for level in ["Category", "Type", "Item"]:
        sub = per_origin_df[per_origin_df["level"] == level].sort_values("train_size")
        print(f"\n--- {level} ---")
        print(sub[["origin", "train_size", "MAE_createDate", "MAE_forecastDate", "forecastDate_better", "pct_diff"]].round(2).to_string(index=False))

    origins_list = get_origins(TOTAL_MONTHS, HOLDOUT)
    last_origin_train_size = origins_list[-1]
    print(f"\nOrigins (train sizes): {origins_list}. The LAST origin (train_size={last_origin_train_size}) tests "
          f"the SAME 6 months (months {last_origin_train_size+1}-{TOTAL_MONTHS}) as the train/val/test split's "
          f"test stage — a direct sanity-check point between the two methodologies.")
    for level in ["Category", "Type", "Item"]:
        last_row = per_origin_df[(per_origin_df["level"] == level) & (per_origin_df["train_size"] == last_origin_train_size)]
        tvt_row = three_way_test[(three_way_test["level"] == level) & (three_way_test["model"] == "Combination")]
        if len(last_row) and len(tvt_row):
            print(f"  {level}: rolling-origin's last-origin MAE_createDate={last_row.iloc[0]['MAE_createDate']:.2f} "
                  f"vs train/val/test MAE_createDate={tvt_row.iloc[0]['MAE_createDate']:.2f} "
                  f"(should match, both fit on the same 25 months for the same 6-month test) — "
                  f"{'MATCH' if abs(last_row.iloc[0]['MAE_createDate'] - tvt_row.iloc[0]['MAE_createDate']) < 1e-6 else 'DO NOT MATCH — investigate'}")

    print("\n--- WINDOW-POSITION PATTERN TEST ---")
    for level in ["Category", "Type", "Item"]:
        sub = per_origin_df[per_origin_df["level"] == level].sort_values("train_size")
        n_better = sub["forecastDate_better"].sum()
        n_total = len(sub)
        # Correlation between train_size (position along the series) and pct_diff (positive = forecastDate worse)
        corr = np.corrcoef(sub["train_size"], sub["pct_diff"])[0, 1] if len(sub) > 2 else np.nan
        print(f"\n{level}: forecast_date better at {n_better} of {n_total} origins. "
              f"Correlation(train_size, %diff where positive=forecastDate worse) = {corr:.3f}.")
        if n_better == n_total:
            print(f"  forecast_date is better at EVERY origin including the earliest ones — the pattern does NOT "
                  f"depend on where the origin sits. WINDOW-POSITION HYPOTHESIS NOT SUPPORTED for this level.")
        elif n_better == 0:
            print(f"  forecast_date is worse at EVERY origin including the last one (which matches train/val/test's "
                  f"own window) — but train/val/test showed an IMPROVEMENT for this level, so if this row shows "
                  f"0 wins, that is an internal inconsistency to flag explicitly, not resolved by the window-"
                  f"position hypothesis either.")
        elif sub.iloc[-1]["forecastDate_better"] and not sub.iloc[0]["forecastDate_better"]:
            print(f"  forecast_date is WORSE at the earliest origin(s) and BETTER at the latest origin(s) — "
                  f"CONSISTENT WITH the window-position hypothesis: the advantage is concentrated near the end "
                  f"of the series (train_size={sub.iloc[-1]['train_size']}), the same origin train/val/test used.")
        else:
            print(f"  Mixed pattern, not a clean early-vs-late split — reported as-is, not forced into either "
                  f"conclusion.")

    # ============================= CHARTS =============================
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharex=False)
    for ax, level in zip(axes, ["Category", "Type", "Item"]):
        sub = per_origin_df[per_origin_df["level"] == level].sort_values("train_size")
        ax.plot(sub["train_size"], sub["MAE_createDate"], marker="o", label="createDate", color="tab:blue")
        ax.plot(sub["train_size"], sub["MAE_forecastDate"], marker="o", label="forecast_date", color="tab:red")
        ax.axvline(last_origin_train_size, color="gray", linestyle="--", linewidth=1, label="train/val/test origin")
        ax.set_title(f"{level}: rolling-origin test MAE\n(Combination)")
        ax.set_xlabel("Train size (months) at this origin")
        ax.set_ylabel("Test MAE")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "b4_per_origin_mae_comparison.png"), dpi=120)
    plt.close(fig)

    print("\nOutputs: output/summary/b4_future_dated_rows_by_month.csv, _by_item.csv, _by_level.csv, "
          "b4_future_dated_window_overlap_summary.csv, b4_three_way_comparison_test.csv, "
          "b4_three_way_comparison_rolling_origin.csv, b4_per_origin_comparison.csv, "
          "b4_rolling_origin_results_forecastDateNoLeak.csv, b4_test_results_forecastDateNoLeak.csv")
    print("Charts: output/charts/b4_per_origin_mae_comparison.png")
