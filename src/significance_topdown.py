"""Does Top-down forecast more accurately than Direct and than Naive? Computed every monthly run (METRICS.md section 41).

Reads the current backtest's item x origin rows (output/summary/phaseC_step2_transferability_item_rolling_origin.csv, written
by src/transferability_all_divisions.py in the same step 4) and writes output/summary/topdown_significance.csv, one row per
division and comparison. The sales report builder reads that file for its "does Top-down beat the others" block.

Per division and comparison, on item-level pairs (each item's MAE averaged over its origins, then paired across items):
  difference = Top-down minus the other method, so negative means Top-down made the smaller error
  n, mean difference, paired t, two-sided p (t distribution, n - 1 degrees of freedom)
  Wilcoxon signed-rank p (scipy, two-sided) and the sign of the median difference
  relative difference in percent = (mean MAE Top-down - mean MAE other) / mean MAE other
  verdict: better / worse when |t| >= the configured threshold AND Wilcoxon p < the configured level AND the sign of t and
  the sign of the median difference agree; otherwise unclear. A Wilcoxon result alone never gives a verdict.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml
from scipy import stats

logger = logging.getLogger("significance_topdown")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
ITEM_ROWS_PATH = os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_item_rolling_origin.csv")
PER_DIVISION_PATH = os.path.join(SUMMARY_DIR, "phaseC_step2_transferability_per_division.csv")
OUTPUT_PATH = os.path.join(SUMMARY_DIR, "topdown_significance.csv")
OTHERS = ("Direct", "Naive")
COLUMNS = ["division", "other_method", "n_items", "mean_diff", "t_stat", "p_value", "wilcoxon_p", "median_diff", "median_sign",
           "mean_MAE_topdown", "mean_MAE_other", "rel_diff_pct", "verdict", "t_threshold", "wilcoxon_p_threshold", "n_origins",
           "first_test_month", "last_test_month", "snapshot_pull_date"]


def load_thresholds(config: dict) -> tuple:
    stats_cfg = config["report_statistics"]
    return float(stats_cfg["paired_t_threshold"]), float(stats_cfg["wilcoxon_p_threshold"])


def verdict_for(t_stat: float, wilcoxon_p: float, median_diff: float, t_threshold: float, p_threshold: float) -> str:
    """better / worse / unclear. Needs |t| >= threshold, Wilcoxon p < level, and t and the median difference of the same sign
    (a zero median or an undefined statistic never agrees)."""
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in (t_stat, wilcoxon_p, median_diff)):
        return "unclear"
    if abs(t_stat) < t_threshold or wilcoxon_p >= p_threshold:
        return "unclear"
    if t_stat < 0 and median_diff < 0:
        return "better"
    if t_stat > 0 and median_diff > 0:
        return "worse"
    return "unclear"


def item_level_pairs(division_rows: pd.DataFrame, other: str) -> pd.DataFrame:
    """Per item: Top-down MAE and the other method's MAE, each averaged over the item's origins; items with both only."""
    means = division_rows.groupby(["itemcode", "approach"])["MAE"].mean().unstack()
    if "Top-down" not in means.columns or other not in means.columns:
        return pd.DataFrame(columns=["Top-down", other])
    return means[["Top-down", other]].dropna()


def compare(pairs: pd.DataFrame, other: str, t_threshold: float, p_threshold: float) -> dict:
    d = pairs["Top-down"] - pairs[other]
    n = len(d)
    if n < 2:
        return {"n_items": n, "verdict": "unclear"}
    se = d.std(ddof=1) / np.sqrt(n)
    t = d.mean() / se if se else np.nan
    p = 2 * stats.t.sf(abs(t), n - 1) if not np.isnan(t) else np.nan
    try:
        w_p = float(stats.wilcoxon(d).pvalue) if (d != 0).any() else np.nan
    except ValueError:
        w_p = np.nan
    median = float(d.median())
    other_mean = float(pairs[other].mean())
    return {"n_items": n, "mean_diff": float(d.mean()), "t_stat": float(t), "p_value": float(p), "wilcoxon_p": w_p, "median_diff": median,
            "median_sign": int(np.sign(median)), "mean_MAE_topdown": float(pairs["Top-down"].mean()), "mean_MAE_other": other_mean,
            "rel_diff_pct": 100 * (float(pairs["Top-down"].mean()) - other_mean) / other_mean if other_mean else np.nan,
            "verdict": verdict_for(float(t), w_p, median, t_threshold, p_threshold)}


def compute(item_rows: pd.DataFrame, t_threshold: float, p_threshold: float, pull_date: str = None) -> pd.DataFrame:
    rows = []
    for division, g in item_rows.groupby("division"):
        for other in OTHERS:
            r = compare(item_level_pairs(g, other), other, t_threshold, p_threshold)
            rows.append({"division": division, "other_method": other, **r, "t_threshold": t_threshold, "wilcoxon_p_threshold": p_threshold,
                         "n_origins": int(g["origin"].nunique()), "first_test_month": g["first_test_month"].min(),
                         "last_test_month": g["last_test_month"].max(), "snapshot_pull_date": pull_date})
    return pd.DataFrame(rows).reindex(columns=COLUMNS)


def main() -> pd.DataFrame:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    t_threshold, p_threshold = load_thresholds(config)
    item_rows = pd.read_csv(ITEM_ROWS_PATH)
    pull_date = pd.read_csv(PER_DIVISION_PATH)["snapshot_pull_date"].iloc[0]
    out = compute(item_rows, t_threshold, p_threshold, pull_date)
    out.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %s (%d rows from %d item x origin rows).", OUTPUT_PATH, len(out), len(item_rows))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = main()
    print(result.round(4).to_string(index=False))
    sys.exit(0)
