"""Q23 Part 2 -- Modeler: same-target accuracy comparison (METRICS.md Sec.21).

Compares, per division (PEM101/PEM103/PEM107) and for the 3 focus items (config.yaml
pilot_item_codes), two ways of forecasting Omni Channel demand, both scored against ACTUAL Omni
demand only:
  A: Top-down combination on the omni series (Type-level combination_forecast, allocated to items
     by each item's own historical Omni qty share of its Type's Omni total, training window only --
     this project's existing adopted method, applied to the Omni-only series).
  B: Top-down combination on the omni_tendering (Omni+Tendering) series (same Type-level
     combination_forecast + item allocation, but on the COMBINED series), then allocated down to
     Omni by that item's own historical Omni share of ITS OWN combined qty, computed from the
     training window only (point-in-time -- no look-ahead). If an item has zero combined demand in
     the training window, falls back to the Type-level Omni share of combined (same training
     window) -- this fallback is a disclosed modeling decision (METRICS.md Sec.21 does not spell
     out the exact tie-break), every occurrence is counted and reported, never hidden.

Separately (never mixed into the A-vs-B accuracy comparison, per Sec.21's own warning): reports
MASE and relative_bias for the omni series and the omni_tendering series EACH SCORED AGAINST ITS
OWN ACTUALS -- a predictability description, not an accuracy claim.

No new database access -- reuses output/data/phaseQ23_raw_sales_allchannels_351full.csv (the
Explorer's Part 1 pull, all revenue_types, PEM101=171/PEM103=87/PEM107=136 pricelist codes).

Rolling-origin machinery reused unchanged from src/backtest_rekeyed.py (get_origins,
compute_metrics, MIN_TRAIN_MONTHS=13/ORIGIN_STEP=2/HOLDOUT=6) and src/models.py
(combination_forecast, the 6-model equal-weight average). Paired significance test reuses
src/transferability_all_divisions.py's exact method: item-mean-first (mean MAE per item across
origins), one-sample t-test on the paired (A,B) differences, |t|>2 read as "distinguishable".
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backtest_rekeyed import HOLDOUT, MIN_TRAIN_MONTHS, ORIGIN_STEP, TOTAL_MONTHS, compute_metrics, get_origins  # noqa: E402
from leakage_guard import check_window_closed, load_min_margin_days  # noqa: E402
from models import combination_forecast  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseQ23_modeler_part2")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
RAW_FILE = os.path.join(DATA_DIR, "phaseQ23_raw_sales_allchannels_351full.csv")

DIVISIONS = ["PEM101", "PEM103", "PEM107"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_scope(config: dict) -> pd.DataFrame:
    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pdf = load_visible_product_rows(pricelist_path)
    sheet_to_division = config["sheet_to_division"]
    pdf = pdf[pdf["sheet"].isin(sheet_to_division)].copy()
    pdf["division"] = pdf["sheet"].map(sheet_to_division)
    pdf = pdf[pdf["division"].isin(DIVISIONS)]
    scope = pdf[["code", "division", "type"]].drop_duplicates(subset=["code"])
    logger.info("Scope: %s", scope.groupby("division")["code"].nunique().to_dict())
    return scope


def load_raw() -> pd.DataFrame:
    raw = pd.read_csv(RAW_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    return raw


def determine_common_months(raw: pd.DataFrame, config: dict) -> tuple:
    """forecast_date-keyed common window, leakage-guard-safe, capped at TOTAL_MONTHS (31) most
    recent safe months -- same recipe as src/load_data_all_divisions.py, applied to THIS pull
    (2024-2026 only, no 2023 -- confirmed by the Explorer)."""
    d = raw.dropna(subset=["forecast_date"]).copy()
    d = d[d["forecast_date"] >= d["createDate"]]
    d["year_month"] = d["forecast_date"].dt.to_period("M")
    max_createdate = raw["createDate"].max()
    latest_createdate_month = pd.Period(max_createdate, freq="M")
    all_months = sorted(d["year_month"].unique())
    complete_months = [m for m in all_months if m < latest_createdate_month]

    min_margin_days = load_min_margin_days(config)
    pull_ts = pd.Timestamp(max_createdate).normalize()
    safe_months = [m for m in complete_months
                   if (pull_ts - m.end_time.normalize()).days >= min_margin_days]
    n_excluded = len(complete_months) - len(safe_months)
    if n_excluded:
        logger.info("Leakage guard excluded %d of %d complete months too close to pull date %s.",
                    n_excluded, len(complete_months), pull_ts.date())

    if len(safe_months) > TOTAL_MONTHS:
        common = safe_months[-TOTAL_MONTHS:]
        logger.info("%d safe months available; truncated to the most recent %d (%s to %s).",
                    len(safe_months), TOTAL_MONTHS, common[0], common[-1])
    else:
        common = safe_months
        logger.warning("Only %d safe months available (< the usual %d) -- proceeding with what "
                        "exists, reported explicitly.", len(common), TOTAL_MONTHS)
    return sorted(common), max_createdate


def build_monthly_qty(raw_subset: pd.DataFrame, codes: list, common_months: list) -> pd.DataFrame:
    d = raw_subset.dropna(subset=["forecast_date"]).copy()
    d = d[d["forecast_date"] >= d["createDate"]]
    d["year_month"] = d["forecast_date"].dt.to_period("M")
    common_set = set(common_months)
    d = d[d["year_month"].isin(common_set)]
    monthly = d.groupby(["itemcode", "year_month"], as_index=False)["qty"].sum()
    full_index = pd.MultiIndex.from_product([codes, common_months], names=["itemcode", "year_month"])
    full = monthly.set_index(["itemcode", "year_month"]).reindex(full_index, fill_value=0.0).reset_index()
    return full


def item_series_dict(monthly_df: pd.DataFrame) -> dict:
    out = {}
    for code, g in monthly_df.groupby("itemcode"):
        out[code] = g.sort_values("year_month")["qty"].to_numpy(dtype=float)
    return out


def type_series_dict(monthly_df: pd.DataFrame, code_to_type: dict) -> dict:
    d = monthly_df.copy()
    d["type"] = d["itemcode"].map(code_to_type)
    agg = d.groupby(["type", "year_month"], as_index=False)["qty"].sum()
    out = {}
    for t, g in agg.groupby("type"):
        out[t] = g.sort_values("year_month")["qty"].to_numpy(dtype=float)
    return out


def run_division(config, division, codes, code_to_type, omni_item, comb_item, omni_type, comb_type,
                  common_months, pull_date, min_margin_days, ma_windows):
    n_months = len(common_months)
    origins = get_origins(n_months, HOLDOUT)
    rows = []
    fallback_count = 0
    total_item_origin = 0
    types_here = sorted(set(code_to_type[c] for c in codes))

    for origin_idx, train_size in enumerate(origins, start=1):
        window_end_month = common_months[train_size + HOLDOUT - 1]
        check_window_closed(window_end_month, pull_date, min_margin_days)

        type_fc_omni, type_fc_comb, type_train_tot_omni, type_train_tot_comb = {}, {}, {}, {}
        for t in types_here:
            om = omni_type.get(t, np.zeros(n_months))[:train_size]
            cb = comb_type.get(t, np.zeros(n_months))[:train_size]
            type_fc_omni[t] = combination_forecast(om, HOLDOUT, ma_windows)
            type_fc_comb[t] = combination_forecast(cb, HOLDOUT, ma_windows)
            type_train_tot_omni[t] = om.sum()
            type_train_tot_comb[t] = cb.sum()

        for code in codes:
            t = code_to_type[code]
            item_omni = omni_item[code]
            item_comb = comb_item[code]
            train_omni, test_omni = item_omni[:train_size], item_omni[train_size:train_size + HOLDOUT]
            train_comb, test_comb = item_comb[:train_size], item_comb[train_size:train_size + HOLDOUT]
            item_tot_omni, item_tot_comb = train_omni.sum(), train_comb.sum()
            total_item_origin += 1

            # --- A: Top-down on omni series ---
            share_a = item_tot_omni / type_train_tot_omni[t] if type_train_tot_omni[t] > 0 else np.nan
            fc_a = type_fc_omni[t] * share_a if pd.notna(share_a) else np.full(HOLDOUT, np.nan)

            # --- B: Top-down on combined series, then allocate to Omni ---
            share_b_comb = item_tot_comb / type_train_tot_comb[t] if type_train_tot_comb[t] > 0 else np.nan
            fc_comb_item = type_fc_comb[t] * share_b_comb if pd.notna(share_b_comb) else np.full(HOLDOUT, np.nan)

            fallback_used = False
            if item_tot_comb > 0:
                omni_share_of_item = item_tot_omni / item_tot_comb
            elif type_train_tot_comb[t] > 0:
                omni_share_of_item = type_train_tot_omni[t] / type_train_tot_comb[t]
                fallback_used = True
            else:
                omni_share_of_item = np.nan
                fallback_used = True
            if fallback_used:
                fallback_count += 1
            fc_b = fc_comb_item * omni_share_of_item if pd.notna(omni_share_of_item) else np.full(HOLDOUT, np.nan)

            if not np.any(np.isnan(fc_a)):
                m = compute_metrics(test_omni, fc_a, train_omni)
                rows.append({"division": division, "type": t, "itemcode": code, "origin": origin_idx,
                             "train_size": train_size, "approach": "A_omni_topdown", **m})
            if not np.any(np.isnan(fc_b)):
                m = compute_metrics(test_omni, fc_b, train_omni)
                rows.append({"division": division, "type": t, "itemcode": code, "origin": origin_idx,
                             "train_size": train_size, "approach": "B_combined_allocated", "fallback_used": fallback_used, **m})

            # --- predictability-only: combined Top-down forecast vs its OWN (combined) actual ---
            if not np.any(np.isnan(fc_comb_item)):
                m = compute_metrics(test_comb, fc_comb_item, train_comb)
                rows.append({"division": division, "type": t, "itemcode": code, "origin": origin_idx,
                             "train_size": train_size, "approach": "omni_tendering_vs_own_actual",
                             "mean_actual": float(test_comb.mean()), **m})
            if not np.any(np.isnan(fc_a)):
                m = compute_metrics(test_omni, fc_a, train_omni)
                rows.append({"division": division, "type": t, "itemcode": code, "origin": origin_idx,
                             "train_size": train_size, "approach": "omni_vs_own_actual",
                             "mean_actual": float(test_omni.mean()), **m})

    return pd.DataFrame(rows), fallback_count, total_item_origin


def paired_significance_by_origin(results: pd.DataFrame, a: str, b: str, itemcode: str) -> dict:
    """For a SINGLE item, pairs A vs B MAE across its own rolling-origins (not across items --
    there is only one item here) -- a one-sample paired t-test on the per-origin MAE differences,
    same t_stat formula as the item-level test."""
    sub = results[results["itemcode"] == itemcode]
    pivot = sub[sub["approach"].isin([a, b])].pivot_table(index="origin", columns="approach", values="MAE")
    if a not in pivot.columns or b not in pivot.columns:
        return {"itemcode": itemcode, "n_origins": 0, "mean_diff_B_minus_A": np.nan, "t_stat": np.nan, "distinguishable": None}
    paired = pivot[[a, b]].dropna()
    diff = paired[b] - paired[a]
    n = len(diff)
    if n < 2:
        return {"itemcode": itemcode, "n_origins": n, "mean_diff_B_minus_A": diff.mean() if n else np.nan,
                "t_stat": np.nan, "distinguishable": None}
    se = diff.std(ddof=1) / np.sqrt(n)
    t_stat = diff.mean() / se if se else np.nan
    return {"itemcode": itemcode, "n_origins": n, "mean_diff_B_minus_A": diff.mean(), "t_stat": t_stat,
            "distinguishable": bool(abs(t_stat) > 2) if pd.notna(t_stat) else None}


def paired_significance(results: pd.DataFrame, a: str, b: str, group_col=None) -> pd.DataFrame:
    """Item-mean-first paired t-test, identical recipe to transferability_all_divisions.py."""
    out_rows = []
    groups = results.groupby(group_col) if group_col else [(None, results)]
    for key, sub in groups:
        item_means = sub.groupby(["itemcode", "approach"])["MAE"].mean().unstack()
        if a not in item_means.columns or b not in item_means.columns:
            continue
        paired = item_means[[a, b]].dropna()
        diff = paired[b] - paired[a]  # B - A, per this task's instruction
        n = len(diff)
        if n < 2:
            out_rows.append({group_col: key, "n_items": n, "mean_diff_B_minus_A": diff.mean() if n else np.nan,
                             "t_stat": np.nan, "distinguishable": None})
            continue
        se = diff.std(ddof=1) / np.sqrt(n)
        t_stat = diff.mean() / se if se else np.nan
        row = {"n_items": n, "mean_diff_B_minus_A": diff.mean(), "t_stat": t_stat,
               "distinguishable": bool(abs(t_stat) > 2) if pd.notna(t_stat) else None}
        if group_col:
            row[group_col] = key
        out_rows.append(row)
    return pd.DataFrame(out_rows)


def summarize_approach(results: pd.DataFrame, approach: str, group_col: str) -> pd.DataFrame:
    sub = results[results["approach"] == approach]
    return sub.groupby(group_col, as_index=False).agg(
        MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), Bias=("Bias", "mean"),
        MASE=("MASE", "mean"), n_scored=("MAE", "size"))


def main():
    config = load_config()
    ma_windows = config["moving_average_windows"]
    focus_items = config["pilot_item_codes"]
    min_margin_days = load_min_margin_days(config)

    raw = load_raw()
    scope = build_scope(config)
    common_months, pull_date = determine_common_months(raw, config)
    logger.info("Common window: %d months, %s to %s. Pull date (max createDate): %s",
                len(common_months), common_months[0], common_months[-1], pull_date)

    raw_omni = raw[raw["revenue_type"] == "Omni Channel"]
    raw_comb = raw[raw["revenue_type"].isin(["Omni Channel", "Tendering"])]

    all_results = []
    fallback_summary = []
    for division in DIVISIONS:
        div_scope = scope[scope["division"] == division]
        codes = sorted(div_scope["code"].unique())
        code_to_type = dict(zip(div_scope["code"], div_scope["type"]))

        omni_monthly = build_monthly_qty(raw_omni[raw_omni["itemcode"].isin(codes)], codes, common_months)
        comb_monthly = build_monthly_qty(raw_comb[raw_comb["itemcode"].isin(codes)], codes, common_months)
        omni_item = item_series_dict(omni_monthly)
        comb_item = item_series_dict(comb_monthly)
        omni_type = type_series_dict(omni_monthly, code_to_type)
        comb_type = type_series_dict(comb_monthly, code_to_type)

        logger.info("[%s] %d items, %d types. Running rolling-origin...", division, len(codes), len(set(code_to_type.values())))
        df, fb_count, total = run_division(config, division, codes, code_to_type, omni_item, comb_item,
                                            omni_type, comb_type, common_months, pull_date, min_margin_days, ma_windows)
        all_results.append(df)
        fallback_summary.append({"division": division, "fallback_count": fb_count, "total_item_origin": total,
                                 "fallback_pct": 100 * fb_count / total if total else np.nan})
        logger.info("[%s] done: %d rows scored, %d/%d item-origins used the Type-level Omni-share "
                    "fallback (%.1f%%).", division, len(df), fb_count, total, 100 * fb_count / total if total else 0)

    results = pd.concat(all_results, ignore_index=True)
    results.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_modeler_part2_item_origin_results.csv"), index=False)
    pd.DataFrame(fallback_summary).to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_modeler_part2_fallback_summary.csv"), index=False)

    # --- Per-division A vs B summary + significance ---
    a_div = summarize_approach(results, "A_omni_topdown", "division").rename(columns=lambda c: f"A_{c}" if c != "division" else c)
    b_div = summarize_approach(results, "B_combined_allocated", "division").rename(columns=lambda c: f"B_{c}" if c != "division" else c)
    div_compare = a_div.merge(b_div, on="division")
    sig_div = paired_significance(results, "A_omni_topdown", "B_combined_allocated", group_col="division")
    div_compare = div_compare.merge(sig_div, on="division", how="left")
    div_compare.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_modeler_part2_division_comparison.csv"), index=False)

    # --- Per-focus-item A vs B ---
    focus_results = results[results["itemcode"].isin(focus_items)]
    a_item = summarize_approach(focus_results, "A_omni_topdown", "itemcode").rename(columns=lambda c: f"A_{c}" if c != "itemcode" else c)
    b_item = summarize_approach(focus_results, "B_combined_allocated", "itemcode").rename(columns=lambda c: f"B_{c}" if c != "itemcode" else c)
    item_compare = a_item.merge(b_item, on="itemcode", how="outer")
    # Item-level (across-item) pairing is meaningless for n=1 -- instead pair EACH focus item's own
    # A-vs-B MAE across its 7 rolling-origins (a genuine paired sample of size 7, not 1).
    sig_item = pd.DataFrame([paired_significance_by_origin(focus_results, "A_omni_topdown", "B_combined_allocated", code)
                             for code in focus_items])
    item_compare = item_compare.merge(sig_item, on="itemcode", how="left")
    item_compare.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_modeler_part2_focusitem_comparison.csv"), index=False)

    # --- Predictability-only: omni vs own actual, omni_tendering vs own actual ---
    predict_rows = []
    for approach in ["omni_vs_own_actual", "omni_tendering_vs_own_actual"]:
        for division in DIVISIONS:
            sub = results[(results["approach"] == approach) & (results["division"] == division)]
            if len(sub) == 0:
                continue
            mase_mean = sub["MASE"].dropna().mean()
            bias_mean = sub["Bias"].mean()
            mean_actual = sub["mean_actual"].mean()
            relative_bias_pct = 100 * bias_mean / mean_actual if mean_actual else np.nan
            predict_rows.append({"division": division, "series": approach, "MASE_mean": mase_mean,
                                 "Bias_mean": bias_mean, "relative_bias_pct": relative_bias_pct,
                                 "n_scored": len(sub)})
    predict_df = pd.DataFrame(predict_rows)
    predict_df.to_csv(os.path.join(SUMMARY_DIR, "phaseQ23_modeler_part2_predictability.csv"), index=False)

    print("\n" + "=" * 100)
    print("Q23 PART 2 -- SAME-TARGET COMPARISON (A: omni top-down vs B: combined-allocated-to-omni)")
    print("=" * 100)
    print(div_compare.round(4).to_string(index=False))
    print("\n--- Focus items ---")
    print(item_compare.round(4).to_string(index=False))
    print("\n--- Predictability only (MASE against own actuals -- NOT an accuracy comparison) ---")
    print(predict_df.round(4).to_string(index=False))
    print("\nFallback usage:")
    print(pd.DataFrame(fallback_summary).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
