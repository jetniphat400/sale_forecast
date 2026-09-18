"""Phase E1.2 (Modeler): lead-time (protection-period) demand accuracy, not next-month accuracy.

Protection period = procurement lead time + assembly time + review interval, all read from
config['phase_e1_assumptions'] (Phase E1's own new config section). Evaluates the Top-down
combination forecast over this FULL horizon, at every leakage-guard-cleared rolling origin, for
the 112 eligible items (excluded/placeholder items are reported as excluded, not silently
dropped -- they have no real forecast to evaluate).

Two things are reported, kept explicitly separate:
  (A) Rolling-origin BACKTEST accuracy of the Top-down forecast over the protection-period
      horizon (cumulative MAE, horizon-position bias growth, MASE with undefined cases handled
      explicitly, never silently).
  (B) The EMPIRICAL protection-period demand DISTRIBUTION built from each item's own actual
      history (rolling sums over the raw monthly series, NOT a normal-distribution assumption,
      NOT the forecast) -- this is what E1.3's Min/Max safety-stock percentiles are drawn from.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import (
    SUMMARY_DIR, CHARTS_DIR, TOTAL_MONTHS,
    load_config, load_scope, load_monthly_series, topdown_item_forecast,
    mase_with_flag,
)
from backtest_rekeyed import get_origins
from leakage_guard import check_window_closed, load_min_margin_days

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1_leadtime_demand")

DAYS_PER_MONTH = 30.44  # average month length (365.25/12) -- the rounding basis stated explicitly
MIN_NONZERO_FOR_UPPER_PERCENTILE = 10  # same "meaningful sample" threshold this project already
# used for order-quantity-pattern evidence (STATUS.md Phase 4 prep investigation Part 5: ">=10
# orders... the minimum treated as meaningful") -- reused here, not invented fresh, for an upper
# (90/95/98th) percentile to be treated as statistically meaningful rather than dominated by 1-2 points.

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]


def protection_period_months(lead_days: int, assembly_days: int, review_days: int) -> int:
    """Rounding rule, stated explicitly: total days / average month length, rounded UP (ceiling)
    -- under-covering the protection period is the riskier direction for a stockout-avoidance
    policy, so ties/fractions round toward MORE coverage, not less."""
    total_days = lead_days + assembly_days + review_days
    return int(np.ceil(total_days / DAYS_PER_MONTH))


def all_scenario_horizons(e1: dict) -> pd.DataFrame:
    rows = []
    for lt in e1["procurement_lead_time_days_grid"]:
        for at in [e1["assembly_time_days_default"], e1["assembly_time_days_alternative"]]:
            h = protection_period_months(lt, at, e1["review_interval_days_default"])
            rows.append({"procurement_lead_time_days": lt, "assembly_time_days": at,
                         "review_interval_days": e1["review_interval_days_default"],
                         "protection_period_days": lt + at + e1["review_interval_days_default"],
                         "protection_period_months": h})
    return pd.DataFrame(rows)


def run_leadtime_backtest(scope: pd.DataFrame, series_bundle: dict, horizon: int,
                           pull_date, min_margin_days: int) -> dict:
    """Returns per-item-per-origin cumulative actual/forecast (for MAE/MASE) and per-relative-
    month bias arrays (for the horizon-position bias-growth question)."""
    series = series_bundle["series"]
    eligible_codes = set(scope.loc[scope["eligible_for_policy"], "code"]) & set(series.keys())
    origins = get_origins(TOTAL_MONTHS, horizon)

    cum_rows = []
    position_errors = {p: [] for p in range(horizon)}  # relative month 0..horizon-1 -> list of (fc-actual)
    n_windows_scored = 0
    n_windows_guard_refused = 0

    for origin_idx, train_size in enumerate(origins, start=1):
        test_end = train_size + horizon
        if test_end > TOTAL_MONTHS:
            continue
        months = series[next(iter(eligible_codes))][1]  # all items share the same month grid
        window_end_month = months[test_end - 1]
        try:
            check_window_closed(window_end_month, pull_date, min_margin_days)
        except Exception as e:
            n_windows_guard_refused += 1
            logger.warning("Origin %d (train_size=%d, horizon=%d): leakage guard refused -- %s",
                            origin_idx, train_size, horizon, e)
            continue
        n_windows_scored += 1

        item_fc = topdown_item_forecast(scope, series, fit_end=train_size, horizon=horizon)
        for code in eligible_codes:
            if code not in item_fc:
                continue
            actual = series[code][0][train_size:test_end]
            forecast = item_fc[code]
            train = series[code][0][:train_size]
            mase, undefined = mase_with_flag(float(np.abs(forecast - actual).mean()), train)
            cum_rows.append({
                "itemcode": code, "origin": origin_idx, "train_size": train_size, "horizon": horizon,
                "cum_actual": float(actual.sum()), "cum_forecast": float(forecast.sum()),
                "cum_MAE": float(np.abs(forecast - actual).mean()),
                "cum_bias": float((forecast - actual).mean()),
                "MASE": mase, "MASE_undefined": undefined,
            })
            for p in range(horizon):
                position_errors[p].append(forecast[p] - actual[p])

    logger.info("Horizon=%d months: %d/%d rolling origins scored (%d refused by the leakage guard). "
                "%d item x origin cells scored across %d eligible items.",
                horizon, n_windows_scored, len(origins), n_windows_guard_refused,
                len(cum_rows), len(eligible_codes))

    position_bias = pd.DataFrame([{"relative_month": p + 1, "mean_bias": float(np.mean(v)) if v else None,
                                    "n_obs": len(v)} for p, v in position_errors.items()])
    return {"cum_df": pd.DataFrame(cum_rows), "position_bias": position_bias,
            "n_windows_scored": n_windows_scored, "n_windows_guard_refused": n_windows_guard_refused}


def empirical_distribution(scope: pd.DataFrame, series_bundle: dict, horizon: int) -> pd.DataFrame:
    """Per eligible item: 50/90/95/98th percentiles of ALL overlapping H-month rolling sums built
    from the item's own actual monthly history (31 - H + 1 windows), the mean of that same
    distribution (needed for E1.3's safety-stock convention), and the count of NON-ZERO windows,
    flagged when too few for the upper percentiles to be meaningful."""
    series = series_bundle["series"]
    eligible_codes = set(scope.loc[scope["eligible_for_policy"], "code"]) & set(series.keys())
    rows = []
    for code in eligible_codes:
        qty = series[code][0]
        windows = np.array([qty[i:i + horizon].sum() for i in range(0, TOTAL_MONTHS - horizon + 1)])
        n_nonzero = int((windows > 0).sum())
        rows.append({
            "itemcode": code, "horizon_months": horizon, "n_windows": len(windows),
            "n_nonzero_windows": n_nonzero,
            "too_few_for_upper_percentiles": n_nonzero < MIN_NONZERO_FOR_UPPER_PERCENTILE,
            "mean": float(windows.mean()),
            "p50": float(np.percentile(windows, 50)),
            "p90": float(np.percentile(windows, 90)),
            "p95": float(np.percentile(windows, 95)),
            "p98": float(np.percentile(windows, 98)),
        })
    return pd.DataFrame(rows)


def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(CHARTS_DIR, exist_ok=True)
    config = load_config()
    e1 = config["phase_e1_assumptions"]
    min_margin_days = load_min_margin_days(config)

    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    pull_date = series_bundle["pull_date"]

    scenario_horizons = all_scenario_horizons(e1)
    scenario_horizons.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_2_scenario_horizons.csv"), index=False)
    horizons_needed = sorted(scenario_horizons["protection_period_months"].unique().tolist())
    logger.info("Protection-period horizons needed across the lead-time x assembly-time grid "
                "(review interval fixed at %dd): %s months. Rounding rule: ceil(total_days / %.2f).",
                e1["review_interval_days_default"], horizons_needed, DAYS_PER_MONTH)

    all_cum, all_pos_bias, all_dist = [], [], []
    mase_summary_rows = []
    for h in horizons_needed:
        logger.info("=== Horizon = %d months ===", h)
        bt = run_leadtime_backtest(scope, series_bundle, h, pull_date, min_margin_days)
        cum_df = bt["cum_df"]
        cum_df["horizon_months"] = h
        all_cum.append(cum_df)
        pos_bias = bt["position_bias"]
        pos_bias["horizon_months"] = h
        all_pos_bias.append(pos_bias)

        n_undef = int(cum_df["MASE_undefined"].sum())
        mase_mean = cum_df.loc[~cum_df["MASE_undefined"], "MASE"].mean()
        mase_summary_rows.append({
            "horizon_months": h, "n_item_origin_cells": len(cum_df),
            "n_MASE_undefined": n_undef, "pct_MASE_undefined": 100 * n_undef / len(cum_df) if len(cum_df) else None,
            "mean_MASE_excl_undefined": mase_mean,
            "mean_cum_MAE": cum_df["cum_MAE"].mean(), "mean_cum_bias": cum_df["cum_bias"].mean(),
            "bias_month1": pos_bias.loc[pos_bias["relative_month"] == 1, "mean_bias"].iloc[0],
            "bias_last_month": pos_bias.loc[pos_bias["relative_month"] == h, "mean_bias"].iloc[0],
        })

        dist = empirical_distribution(scope, series_bundle, h)
        all_dist.append(dist)

    cum_all = pd.concat(all_cum, ignore_index=True)
    pos_bias_all = pd.concat(all_pos_bias, ignore_index=True)
    dist_all = pd.concat(all_dist, ignore_index=True)
    mase_summary = pd.DataFrame(mase_summary_rows)

    cum_all.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_2_rolling_origin_cumulative.csv"), index=False)
    pos_bias_all.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_2_horizon_position_bias.csv"), index=False)
    dist_all.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_2_empirical_distribution.csv"), index=False)
    mase_summary.to_csv(os.path.join(SUMMARY_DIR, "phaseE1_2_mase_summary.csv"), index=False)

    for h in horizons_needed:
        sub = dist_all[dist_all["horizon_months"] == h]
        n_flag = int(sub["too_few_for_upper_percentiles"].sum())
        logger.info("Horizon=%d: %d/%d eligible items have fewer than %d non-zero %d-month windows "
                    "(upper 90/95/98th percentiles flagged as not statistically meaningful for these).",
                    h, n_flag, len(sub), MIN_NONZERO_FOR_UPPER_PERCENTILE, h)

    # ---- chart: lead-time-demand distribution for the 3 focus items, at the default scenario's horizon ----
    default_h = protection_period_months(e1["default_scenario"]["procurement_lead_time_days"],
                                          e1["default_scenario"]["assembly_time_days"],
                                          e1["review_interval_days_default"])
    logger.info("Default scenario protection period = %d months.", default_h)
    series = series_bundle["series"]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, item in zip(axes, FOCUS_ITEMS):
        if item not in series:
            ax.set_title(f"{item}\n(no history)")
            continue
        qty = series[item][0]
        windows = np.array([qty[i:i + default_h].sum() for i in range(0, TOTAL_MONTHS - default_h + 1)])
        ax.hist(windows, bins=min(15, max(5, len(set(windows.round(1))))), color="tab:blue", alpha=0.75)
        for pct, style in [(50, "--"), (90, ":"), (95, "-."), (98, "-")]:
            ax.axvline(np.percentile(windows, pct), color="black", linestyle=style, linewidth=1,
                       label=f"p{pct}={np.percentile(windows, pct):.0f}")
        ax.set_title(f"{item}\n{default_h}-month rolling-sum demand (n={len(windows)} windows)")
        ax.set_xlabel("Qty over protection period")
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "phaseE1_leadtime_demand_distribution_focus_items.png"), dpi=120)
    plt.close(fig)
    logger.info("Chart: output/charts/phaseE1_leadtime_demand_distribution_focus_items.png")

    print("\n=== E1.2 MASE / BIAS SUMMARY BY HORIZON ===")
    print(mase_summary.round(3).to_string(index=False))

    return {"cum_all": cum_all, "pos_bias_all": pos_bias_all, "dist_all": dist_all,
            "mase_summary": mase_summary, "scenario_horizons": scenario_horizons, "default_h": default_h}


if __name__ == "__main__":
    main()
