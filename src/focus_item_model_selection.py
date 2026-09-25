"""Item-specific model selection for this project's three focus codes
(EEE-F-FC-1040010002, HS-F-99-02110, HS-F-99-0213) — evaluated individually, not as part of an
aggregate Category/Type/division comparison. Every model available in the pipeline is scored on
each item separately: Naive, MA3/6/12, SES, Holt, Croston, SBA, TSB, the adopted six-model
Combination, and Top-down allocation from Type (the current default, compared against directly).

Data: reuses output/data/processed_all_divisions_monthly_qty.csv (335-item, 5-division scope,
2024-01 to 2026-07, forecast_date-keyed, snapshot_pull_date frozen by Phase C step 2's
src/load_data_all_divisions.py run) — NOT a fresh pull. This is deliberate: "Top-down
combination," the baseline every candidate here is compared against, was itself scored on this
exact data; a fresh pull would compare apples to a slightly different basket.

Evaluation: rolling-origin (src/backtest_rekeyed.py's get_origins/compute_metrics, imported
unchanged) is PRIMARY, train/val/test SECONDARY, per this project's adopted evaluation policy —
restated here because the task explicitly asks for it again given the known Feb-Jul 2026 window
anomaly (STATUS.md, closed without further pursuit, Section 8).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from backtest_rekeyed import (HOLDOUT, MA_WINDOWS, TEST_MONTHS, TOTAL_MONTHS, TRAIN_MONTHS,
                               VAL_MONTHS, compute_metrics, get_origins)
from leakage_guard import check_window_closed, load_min_margin_days
from models import (combination_forecast, croston_forecast, holt_forecast,
                     moving_average_forecast, naive_forecast, sba_forecast, ses_forecast,
                     tsb_forecast)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("focus_item_model_selection")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]

# Pre-recovery supplementary split for EEE-F-FC-1040010002 (Part 3). Derived directly from the
# item's own monthly series (output/data/processed_all_divisions_monthly_qty.csv), not assumed:
# qty is genuinely 0 for 2025-01 through 2025-03 (the trough) and recovers steadily from 2025-04
# onward. 9 months train (2024-01 to 2024-09) / 6 months test (2024-10 to 2025-03) is the
# largest train/test split that stays entirely within the pre-recovery window (test ends exactly
# at the last confirmed zero month). This is NOT one of the standard rolling-origin points
# (MIN_TRAIN_MONTHS=13 in backtest_rekeyed.py makes every standard origin's test window already
# overlap the recovery — stated explicitly, not hidden) — a separate, single-split, smaller-n
# check, reported as supplementary evidence only.
EEE_PRE_RECOVERY_TRAIN_MONTHS = 9
EEE_PRE_RECOVERY_TEST_MONTHS = 6


def individual_model_candidates() -> dict:
    """All 9 individually-scored candidates (not the six-model Combination average, which is
    scored separately below, unchanged from its locked definition)."""
    models = {
        "Naive": naive_forecast,
        "MA3": lambda train, horizon: moving_average_forecast(train, horizon, 3),
        "MA6": lambda train, horizon: moving_average_forecast(train, horizon, 6),
        "MA12": lambda train, horizon: moving_average_forecast(train, horizon, 12),
        "SES": ses_forecast,
        "Holt": holt_forecast,
        "Croston": croston_forecast,
        "SBA": sba_forecast,
        "TSB": tsb_forecast,
    }
    return models


def build_item_and_type_series(monthly: pd.DataFrame, scope: pd.DataFrame, item_code: str) -> tuple:
    """Returns (item_qty, item_months, type_qty, type_months, division, type_name)."""
    row = scope[scope["code"] == item_code]
    if len(row) != 1:
        raise ValueError(f"{item_code}: expected exactly one scope row, found {len(row)}.")
    division, type_name = row["division"].iloc[0], row["type"].iloc[0]

    item_g = monthly[monthly["itemcode"] == item_code].sort_values("year_month")
    item_qty = item_g["qty"].to_numpy(dtype=float)
    item_months = item_g["year_month"].astype(str).tolist()

    type_items = scope[(scope["division"] == division) & (scope["type"] == type_name)]["code"].tolist()
    type_g = monthly[monthly["itemcode"].isin(type_items)].groupby("year_month", as_index=False)["qty"].sum().sort_values("year_month")
    type_qty = type_g["qty"].to_numpy(dtype=float)
    type_months = type_g["year_month"].astype(str).tolist()

    return item_qty, item_months, type_qty, type_months, division, type_name


def score_all_candidates_at_origin(train: np.ndarray, test: np.ndarray, type_train: np.ndarray) -> dict:
    """Fits every candidate on `train`, scores against `test`. Returns {model_name: metrics_dict}.
    Raises nothing on an individual model failure -- records the failure reason instead, per
    instruction ("report why rather than silently omitting it")."""
    results = {}
    for name, fn in individual_model_candidates().items():
        try:
            fc = np.clip(fn(train, len(test)), 0, None)
            results[name] = {"metrics": compute_metrics(test, fc, train), "forecast": fc, "error": None}
        except Exception as e:
            results[name] = {"metrics": None, "forecast": None, "error": f"{type(e).__name__}: {e}"}

    try:
        fc = np.clip(combination_forecast(train, len(test), MA_WINDOWS), 0, None)
        results["Combination"] = {"metrics": compute_metrics(test, fc, train), "forecast": fc, "error": None}
    except Exception as e:
        results["Combination"] = {"metrics": None, "forecast": None, "error": f"{type(e).__name__}: {e}"}

    try:
        type_fc = np.clip(combination_forecast(type_train, len(test), MA_WINDOWS), 0, None)
        item_total, type_total = train.sum(), type_train.sum()
        share = item_total / type_total if type_total > 0 else np.nan
        if pd.notna(share):
            fc = type_fc * share
            results["Top-down"] = {"metrics": compute_metrics(test, fc, train), "forecast": fc, "error": None}
        else:
            results["Top-down"] = {"metrics": None, "forecast": None, "error": "Type total qty is 0 over this training window -- share undefined."}
    except Exception as e:
        results["Top-down"] = {"metrics": None, "forecast": None, "error": f"{type(e).__name__}: {e}"}

    return results


def run_rolling_origin_all_candidates(item_qty, item_months, type_qty, type_months,
                                       pull_date, min_margin_days) -> pd.DataFrame:
    origins = get_origins(TOTAL_MONTHS, HOLDOUT)
    rows = []
    for origin_idx, train_size in enumerate(origins, start=1):
        train = item_qty[:train_size]
        test = item_qty[train_size:train_size + HOLDOUT]
        type_train = type_qty[:train_size]
        if len(test) < HOLDOUT:
            continue
        window_end_month = item_months[train_size + HOLDOUT - 1]
        check_window_closed(window_end_month, pull_date, min_margin_days)

        scored = score_all_candidates_at_origin(train, test, type_train)
        for model_name, r in scored.items():
            row = {"origin": origin_idx, "train_size": train_size, "model": model_name,
                   "window_end_month": window_end_month, "error": r["error"]}
            if r["metrics"] is not None:
                row.update(r["metrics"])
            rows.append(row)
    return pd.DataFrame(rows)


def run_train_val_test_all_candidates(item_qty, type_qty, pull_date, min_margin_days, item_months) -> tuple:
    if len(item_qty) != TOTAL_MONTHS:
        raise ValueError(f"Expected {TOTAL_MONTHS} months, got {len(item_qty)}.")
    train = item_qty[:TRAIN_MONTHS]
    val = item_qty[TRAIN_MONTHS:TRAIN_MONTHS + VAL_MONTHS]
    train_val = item_qty[:TRAIN_MONTHS + VAL_MONTHS]
    test = item_qty[TRAIN_MONTHS + VAL_MONTHS:]
    type_train = type_qty[:TRAIN_MONTHS]
    type_train_val = type_qty[:TRAIN_MONTHS + VAL_MONTHS]

    check_window_closed(item_months[TRAIN_MONTHS + VAL_MONTHS - 1], pull_date, min_margin_days)
    check_window_closed(item_months[TOTAL_MONTHS - 1], pull_date, min_margin_days)

    val_scored = score_all_candidates_at_origin(train, val, type_train)
    test_scored = score_all_candidates_at_origin(train_val, test, type_train_val)

    val_rows = [{"model": k, "error": v["error"], **(v["metrics"] or {})} for k, v in val_scored.items()]
    test_rows = [{"model": k, "error": v["error"], **(v["metrics"] or {})} for k, v in test_scored.items()]
    return pd.DataFrame(val_rows), pd.DataFrame(test_rows)


def bias_sign_summary(ro: pd.DataFrame) -> pd.DataFrame:
    """Per model: mean signed Bias, and how many origins were positive vs negative -- a model
    whose Bias flips sign across origins is a materially different result from one that is
    steadily biased in one direction, even if the MEAN happens to look similar."""
    rows = []
    for model, g in ro.dropna(subset=["Bias"]).groupby("model"):
        n = len(g)
        n_pos = (g["Bias"] > 0).sum()
        n_neg = (g["Bias"] < 0).sum()
        n_zero = n - n_pos - n_neg
        consistent = (n_pos == n) or (n_neg == n)
        rows.append({"model": model, "mean_bias": g["Bias"].mean(), "n_origins": n,
                     "n_positive": n_pos, "n_negative": n_neg, "n_zero": n_zero,
                     "sign_consistent": consistent})
    return pd.DataFrame(rows)


def winner_per_origin(ro: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for origin, g in ro.dropna(subset=["MAE"]).groupby("origin"):
        best = g.loc[g["MAE"].idxmin()]
        rows.append({"origin": origin, "winner": best["model"], "winner_MAE": best["MAE"]})
    win_counts = pd.DataFrame(rows)["winner"].value_counts()
    return pd.DataFrame(rows), win_counts


def paired_significance_vs_topdown(ro: pd.DataFrame, candidate_model: str) -> dict:
    """Paired t-test across origins, SAME methodology as
    src/transferability_all_divisions.py / src/item_level_reconciliation.py: pair by origin,
    diff = candidate_MAE - topdown_MAE, t = mean(diff)/se(diff)."""
    cand = ro[ro["model"] == candidate_model][["origin", "MAE"]].rename(columns={"MAE": "MAE_cand"})
    topdown = ro[ro["model"] == "Top-down"][["origin", "MAE"]].rename(columns={"MAE": "MAE_topdown"})
    paired = cand.merge(topdown, on="origin").dropna()
    n = len(paired)
    if n < 2:
        return {"candidate": candidate_model, "n_origins": n, "mean_diff": np.nan, "t_stat": np.nan}
    diff = paired["MAE_cand"] - paired["MAE_topdown"]
    se = diff.std(ddof=1) / np.sqrt(n)
    t_stat = diff.mean() / se if se else np.nan
    return {"candidate": candidate_model, "n_origins": n, "mean_diff": diff.mean(), "t_stat": t_stat}


if __name__ == "__main__":
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    min_margin_days = load_min_margin_days(config)

    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    logger.info("Data: processed_all_divisions_monthly_qty.csv, snapshot_pull_date=%s, "
                "leakage guard min_margin_days=%d", pull_date, min_margin_days)

    all_ro, all_val, all_test, all_bias, all_winners, all_sig = [], [], [], [], [], []

    for item in FOCUS_ITEMS:
        logger.info("=== %s ===", item)
        item_qty, item_months, type_qty, type_months, division, type_name = build_item_and_type_series(
            monthly, scope, item)
        logger.info("%s: division=%s, type=%s, %d months, total qty=%.0f, %d zero months (%.1f%%)",
                    item, division, type_name, len(item_qty), item_qty.sum(),
                    int((item_qty == 0).sum()), 100 * (item_qty == 0).mean())

        ro = run_rolling_origin_all_candidates(item_qty, item_months, type_qty, type_months,
                                                pull_date, min_margin_days)
        ro["itemcode"] = item
        ro.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_rolling_origin.csv".replace("/", "_")), index=False)
        all_ro.append(ro)

        val_df, test_df = run_train_val_test_all_candidates(item_qty, type_qty, pull_date,
                                                              min_margin_days, item_months)
        val_df["itemcode"], test_df["itemcode"] = item, item
        val_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_val.csv".replace("/", "_")), index=False)
        test_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_test.csv".replace("/", "_")), index=False)
        all_val.append(val_df)
        all_test.append(test_df)

        bias_df = bias_sign_summary(ro)
        bias_df["itemcode"] = item
        bias_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_bias_sign.csv".replace("/", "_")), index=False)
        all_bias.append(bias_df)

        winners_df, win_counts = winner_per_origin(ro)
        winners_df["itemcode"] = item
        winners_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_winner_per_origin.csv".replace("/", "_")), index=False)
        all_winners.append(winners_df)

        sig_rows = []
        for model in ro["model"].unique():
            if model == "Top-down":
                continue
            sig_rows.append({**paired_significance_vs_topdown(ro, model), "itemcode": item})
        sig_df = pd.DataFrame(sig_rows)
        sig_df.to_csv(os.path.join(SUMMARY_DIR, f"focus_{item}_significance_vs_topdown.csv".replace("/", "_")), index=False)
        all_sig.append(sig_df)

        logger.info("%s: rolling-origin done (%d origins x %d candidates), val/test done, "
                    "%d/%d origins won by each model: %s", item, ro["origin"].nunique(),
                    ro["model"].nunique(), ro["origin"].nunique(), ro["origin"].nunique(),
                    win_counts.to_dict())

    pd.concat(all_ro, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_rolling_origin_all.csv"), index=False)
    pd.concat(all_val, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_val_all.csv"), index=False)
    focus_items_test_all_df = pd.concat(all_test, ignore_index=True)
    # snapshot_pull_date recorded so a consuming page (src/build_report.py) can show WHEN the
    # data was pulled, never a file mtime proxy (task 2cfix2, Part 3) -- same pull that produced
    # processed_all_divisions_monthly_qty.csv, read above.
    focus_items_test_all_df["snapshot_pull_date"] = pull_date
    focus_items_test_all_df.to_csv(os.path.join(SUMMARY_DIR, "focus_items_test_all.csv"), index=False)
    pd.concat(all_bias, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_bias_sign_all.csv"), index=False)
    pd.concat(all_winners, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_winner_per_origin_all.csv"), index=False)
    pd.concat(all_sig, ignore_index=True).to_csv(os.path.join(SUMMARY_DIR, "focus_items_significance_vs_topdown_all.csv"), index=False)

    # ============================= EEE-F-FC-1040010002: pre-recovery supplementary split =============================
    logger.info("=== EEE-F-FC-1040010002: pre-recovery supplementary split ===")
    item_qty, item_months, type_qty, type_months, division, type_name = build_item_and_type_series(
        monthly, scope, "EEE-F-FC-1040010002")
    pre_train = item_qty[:EEE_PRE_RECOVERY_TRAIN_MONTHS]
    pre_test = item_qty[EEE_PRE_RECOVERY_TRAIN_MONTHS:EEE_PRE_RECOVERY_TRAIN_MONTHS + EEE_PRE_RECOVERY_TEST_MONTHS]
    pre_type_train = type_qty[:EEE_PRE_RECOVERY_TRAIN_MONTHS]
    window_end_month = item_months[EEE_PRE_RECOVERY_TRAIN_MONTHS + EEE_PRE_RECOVERY_TEST_MONTHS - 1]
    check_window_closed(window_end_month, pull_date, min_margin_days)
    logger.info("Pre-recovery split: train %s to %s (%d months), test %s to %s (%d months)",
                item_months[0], item_months[EEE_PRE_RECOVERY_TRAIN_MONTHS - 1], EEE_PRE_RECOVERY_TRAIN_MONTHS,
                item_months[EEE_PRE_RECOVERY_TRAIN_MONTHS], window_end_month, EEE_PRE_RECOVERY_TEST_MONTHS)
    pre_scored = score_all_candidates_at_origin(pre_train, pre_test, pre_type_train)
    pre_rows = [{"model": k, "error": v["error"], **(v["metrics"] or {})} for k, v in pre_scored.items()]
    pre_df = pd.DataFrame(pre_rows)
    pre_df.to_csv(os.path.join(SUMMARY_DIR, "focus_EEE-F-FC-1040010002_pre_recovery_split.csv"), index=False)
    print("\nEEE-F-FC-1040010002 pre-recovery split (train 2024-01/09, test 2024-10/2025-03):")
    print(pre_df[["model", "MAE", "RMSE", "Bias", "MASE", "error"]].round(2).to_string(index=False))

    print("\n" + "=" * 92)
    print("FOCUS ITEM MODEL SELECTION — SUMMARY")
    print("=" * 92)
    for item in FOCUS_ITEMS:
        ro = pd.concat(all_ro, ignore_index=True)
        item_ro = ro[ro["itemcode"] == item]
        summary = item_ro.dropna(subset=["MAE"]).groupby("model", as_index=False)[["MAE", "RMSE", "Bias", "MASE"]].mean().sort_values("MAE")
        print(f"\n--- {item} (rolling-origin mean, primary) ---")
        print(summary.round(2).to_string(index=False))

    print("\nOutputs: output/summary/focus_<item>_*.csv, focus_items_*_all.csv, "
          "focus_EEE-F-FC-1040010002_pre_recovery_split.csv")
