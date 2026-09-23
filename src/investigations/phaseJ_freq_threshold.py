"""Phase J Part 3 -- segment frequency threshold (2-12 orders/yr) Pareto frontier, at the default
cycle service level (0.95, today's config value -- this sweep runs BEFORE Part 4's default change).
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseI_sensitivity_engine as eng

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ_freq_threshold")

SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")
THRESHOLDS = list(range(2, 13))  # 2..12 inclusive
CURRENT_THRESHOLD = 6.0


def pareto_frontier(df: pd.DataFrame) -> pd.Series:
    """A threshold is ON the frontier if no OTHER threshold has stock_value <= it AND
    fill_rate >= it, with at least one strictly better (minimize stock_value, maximize fill_rate)."""
    on_frontier = []
    for i, row in df.iterrows():
        dominated = False
        for j, other in df.iterrows():
            if i == j:
                continue
            not_worse = (other["stock_value"] <= row["stock_value"]) and (other["fill_rate"] >= row["fill_rate"])
            strictly_better = (other["stock_value"] < row["stock_value"]) or (other["fill_rate"] > row["fill_rate"])
            if not_worse and strictly_better:
                dominated = True
                break
        on_frontier.append(not dominated)
    return pd.Series(on_frontier, index=df.index)


def main():
    config = eng.load_config()
    raw, inv = eng.load_raw()

    rows = []
    for division in eng.DIVISIONS:
        bundle = eng.build_division_bundle(config, division, raw, inv)
        for freq in THRESHOLDS:
            params = dict(eng.DEFAULTS)
            params["freq_cutoff_per_year"] = float(freq)
            result = eng.run_scenario(bundle, **params)
            rows.append({"division": division, "freq_cutoff_per_year": freq,
                        "stock_value": result["stock_value"], "fill_rate": result["fill_rate"],
                        "n_finished_goods_stock": int((result["facts"]["policy"] == "finished_goods_stock").sum())})

    df = pd.DataFrame(rows)
    frontier_flags = []
    for division, g in df.groupby("division"):
        flags = pareto_frontier(g.reset_index(drop=True))
        flags.index = g.index
        frontier_flags.append(flags)
    df["on_pareto_frontier"] = pd.concat(frontier_flags).sort_index()
    df["is_current_threshold"] = df["freq_cutoff_per_year"] == CURRENT_THRESHOLD

    df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_3_freq_threshold_frontier.csv"), index=False)

    print("\n" + "=" * 100)
    print("PHASE J PART 3 -- SEGMENT FREQUENCY THRESHOLD PARETO FRONTIER (default SL=0.95)")
    print("=" * 100)
    print(df.to_string(index=False))

    summary = []
    for division, g in df.groupby("division"):
        frontier_vals = sorted(g.loc[g["on_pareto_frontier"], "freq_cutoff_per_year"].tolist())
        current_on_frontier = bool(g.loc[g["is_current_threshold"], "on_pareto_frontier"].iloc[0])
        summary.append({"division": division, "frontier_thresholds": frontier_vals,
                        "current_threshold": CURRENT_THRESHOLD, "current_on_frontier": current_on_frontier})
        print(f"\n{division}: Pareto frontier = {frontier_vals}; current threshold "
              f"({CURRENT_THRESHOLD}) on frontier = {current_on_frontier}")
    return df, summary


if __name__ == "__main__":
    main()
