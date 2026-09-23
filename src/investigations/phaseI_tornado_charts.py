"""Phase I Part 5 -- tornado chart per division: signed stock_value shift (%) for each swept
assumption's full range, sorted by magnitude. sellable_warehouses is included for completeness
(shows as a zero-width bar -- the empirically-verified decision-insensitive-by-construction
result, Part 1). Concentration threshold is omitted (report-only, never touches stock_value).
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseI_sensitivity_engine as eng

SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(eng.PROJECT_ROOT, "output", "charts")

LABELS = {
    "procurement_lead_time_days": "Procurement lead time",
    "assembly_time_days": "Assembly time",
    "review_interval_days": "Review interval",
    "cycle_service_level": "Cycle service level",
    "unit_cost_window_months": "Unit-cost window",
    "freq_cutoff_per_year": "Segment frequency threshold",
    "sellable_warehouses": "Sellable warehouses",
}


def build_tornado_data(scen_df: pd.DataFrame, division: str) -> pd.DataFrame:
    sub = scen_df[scen_df["division"] == division]
    default_sv = float(sub.loc[sub["is_default"], "stock_value"].iloc[0])
    rows = []
    for assumption in LABELS:
        s = sub[(sub["assumption"] == assumption) & (~sub["is_default"])]
        if not len(s):
            continue
        signed_shift = 100 * (s["stock_value"] - default_sv) / default_sv
        rows.append({
            "assumption": assumption, "label": LABELS[assumption],
            "min_shift_pct": float(signed_shift.min()), "max_shift_pct": float(signed_shift.max()),
            "range_width": float(signed_shift.max() - signed_shift.min()),
        })
    df = pd.DataFrame(rows).sort_values("range_width", ascending=True)
    return df, default_sv


def plot_tornado(division: str, df: pd.DataFrame, default_sv: float, classification: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(9, 5))
    y = range(len(df))
    colors = []
    for _, r in df.iterrows():
        verdict_row = classification[(classification["division"] == division) &
                                      (classification["assumption"] == r["assumption"])]
        relevant = bool(verdict_row["any_policy_flip"].iloc[0]) or (
            len(verdict_row) and verdict_row["verdict_at_10pct"].iloc[0] == "RELEVANT")
        colors.append("#d62728" if relevant else "#7f7f7f")

    ax.barh(list(y), df["max_shift_pct"] - df["min_shift_pct"], left=df["min_shift_pct"],
            color=colors, edgecolor="black", height=0.6)
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(10, color="orange", linestyle="--", linewidth=1, label="+-10% relevance threshold")
    ax.axvline(-10, color="orange", linestyle="--", linewidth=1)
    ax.set_yticks(list(y))
    ax.set_yticklabels(df["label"])
    ax.set_xlabel("stock_value shift from default scenario (%)")
    ax.set_title(f"{division} -- decision-sensitivity tornado chart\n"
                 f"(default stock_value = THB {default_sv:,.0f}; red = RELEVANT at 10%, grey = insensitive)",
                 fontsize=10)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out_path = os.path.join(CHARTS_DIR, f"phaseI_tornado_{division}.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main():
    scen_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseI_1_scenario_results.csv"))
    classification = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseI_2_classification.csv"))
    for division in eng.DIVISIONS:
        df, default_sv = build_tornado_data(scen_df, division)
        out_path = plot_tornado(division, df, default_sv, classification)
        print(f"{division}: tornado chart written to {out_path}")


if __name__ == "__main__":
    main()
