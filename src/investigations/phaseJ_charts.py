"""Phase J Part 6 -- extended service-level curve charts, one per division: stock_value panel
(with the current on-hand value marked) and fill_rate panel (with actual_on_time marked).
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

CURRENT_ONHAND_VALUE = {"PEM101": 18_070_000, "PEM103": 6_060_000, "PEM107": 3_280_000}


def main():
    curve_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseJ_2_service_level_curve_extended.csv"))
    calib_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseJ_1_calibration_summary.csv")).set_index("division")

    for division in eng.DIVISIONS:
        g = curve_df[curve_df["division"] == division].sort_values("cycle_service_level")
        actual_on_time = float(calib_df.loc[division, "actual_on_time"])
        onhand = CURRENT_ONHAND_VALUE[division]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)

        ax1.plot(g["cycle_service_level"], g["stock_value"], marker="o", color="#1f77b4")
        ax1.axhline(onhand, color="red", linestyle="--", linewidth=1.5,
                    label=f"current on-hand value (THB {onhand:,.0f})")
        ax1.set_ylabel("stock_value (THB)")
        ax1.set_title(f"{division} -- extended service-level curve (0.50-0.98)")
        ax1.legend(loc="upper left", fontsize=8)
        ax1.ticklabel_format(style="plain", axis="y")

        ax2.plot(g["cycle_service_level"], g["fill_rate"] * 100, marker="o", color="#2ca02c")
        ax2.axhline(actual_on_time * 100, color="red", linestyle="--", linewidth=1.5,
                    label=f"actual_on_time ({actual_on_time*100:.1f}%)")
        ax2.set_xlabel("cycle service level (model input)")
        ax2.set_ylabel("model fill_rate (%)")
        ax2.legend(loc="lower right", fontsize=8)

        fig.tight_layout()
        out_path = os.path.join(CHARTS_DIR, f"phaseJ_service_level_curve_{division}.png")
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"{division}: chart written to {out_path}")


if __name__ == "__main__":
    main()
