"""Task 2b, Part 3 -- METRICS.md Sec.24 relative_service_cost, PEM101 only (the only division with
a non-empty robust_ensemble, METRICS.md Sec.22).

No database access -- reads already-computed Phase 23 outputs:
  output/summary/phase23_modeler_tradeoff_curve_points.csv: per DISTINCT ensemble member (80,
    METRICS.md Sec.22 dedup), 20 points of (not_late, stock_value) from sweeping that member's own
    reorder level (its gap to order-up-to level held constant, per Sec.22's trade-off-curve
    definition) -- this is the per-member curve ratio_e needs, not the aggregate envelope.
  output/summary/phase23_dense_grid_PEM101.json: today's ACTUAL not_late (98.28%, the real
    business figure, phaseJ3_validator_stock_value_summary.csv) and the 3 presets' target not_late
    values -- "today's level" in Sec.24's formula is this single real figure, applied identically
    to every member's own curve (not each member's own simulated-at-today point), because
    Sec.24's own reasoning is that the unidentifiable reorder level cancels WITHIN a member's
    ratio of two points on its OWN curve, not against a member-specific baseline.

For each member, linearly interpolates its own (not_late -> stock_value) curve (sorted by
not_late) to get stock_value at today's not_late and at each target not_late. ratio_e(target) =
stock_value_e(target) / stock_value_e(today). Members whose own curve does not span both points
(interpolation out of range) are excluded from that target's aggregate and counted separately --
never extrapolated.
"""
import json
import logging
import os

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task2b_part3")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

CURVE_POINTS_PATH = os.path.join(SUMMARY_DIR, "phase23_modeler_tradeoff_curve_points.csv")
DENSE_GRID_PATH = os.path.join(SUMMARY_DIR, "phase23_dense_grid_PEM101.json")

OUT_RATIO_GRID = os.path.join(SUMMARY_DIR, "task2b_part3_ratio_grid_PEM101.json")
OUT_PRESET_REPORT = os.path.join(SUMMARY_DIR, "task2b_part3_preset_report.csv")
OUT_REPORT = os.path.join(SUMMARY_DIR, "task2b_part3_report.md")


def member_curve_interp(sub: pd.DataFrame):
    """Returns (interp_fn, not_late_min, not_late_max) for one member's own 20-point curve,
    sorted and de-duplicated on not_late (percent, 0-100 scale to match the dense grid's own
    convention)."""
    g = sub.sort_values("not_late").drop_duplicates("not_late")
    x = (g["not_late"].to_numpy() * 100.0)
    y = g["stock_value"].to_numpy()

    def f(target_pct):
        if target_pct < x.min() or target_pct > x.max():
            return None
        return float(np.interp(target_pct, x, y))

    return f, float(x.min()), float(x.max())


def ratio_at_target(curve_points: pd.DataFrame, today_pct: float, target_pct: float):
    ratios = []
    n_excluded = 0
    for member_idx, sub in curve_points.groupby("member_idx"):
        f, lo, hi = member_curve_interp(sub)
        v_today = f(today_pct)
        v_target = f(target_pct)
        if v_today is None or v_target is None or v_today == 0:
            n_excluded += 1
            continue
        ratios.append(v_target / v_today)
    if not ratios:
        return None
    return {
        "median": float(np.median(ratios)), "min": float(np.min(ratios)), "max": float(np.max(ratios)),
        "n_members": len(ratios), "n_excluded": n_excluded,
    }


def absolute_band_at(target_pct: float, envelope: pd.DataFrame):
    """Nearest not_late_bin_pct row in the existing Sec.22 envelope (min/median/max stock_value,
    the ABSOLUTE band Sec.24 requires comparing the ratio band against)."""
    idx = (envelope["not_late_bin_pct"] - target_pct).abs().idxmin()
    row = envelope.loc[idx]
    return {"bin_pct": float(row["not_late_bin_pct"]), "min": float(row["min"]),
            "median": float(row["median"]), "max": float(row["max"])}


def main():
    curve_points = pd.read_csv(CURVE_POINTS_PATH)
    with open(DENSE_GRID_PATH, encoding="utf-8") as f:
        dense = json.load(f)
    envelope = pd.read_csv(os.path.join(SUMMARY_DIR, "phase23_modeler_tradeoff_envelope.csv"))

    today_pct = dense["today_point"]["not_late_pct"]
    presets = dense["presets"]
    lo_pct, hi_pct = dense["not_late_range_pct"]

    # Fine grid for the live page (0.25pp step, clipped to the range every member could possibly
    # be interpolated in -- the union of member ranges, per-target exclusion still applies).
    grid_targets = np.round(np.arange(lo_pct, hi_pct + 0.01, 0.25), 3).tolist()
    ratio_grid = []
    for t in grid_targets:
        r = ratio_at_target(curve_points, today_pct, t)
        if r is not None:
            ratio_grid.append({"not_late_pct": t, **r})

    with open(OUT_RATIO_GRID, "w", encoding="utf-8") as f:
        json.dump({"today_not_late_pct": today_pct, "grid": ratio_grid,
                    "source": "src/investigations/task2b_part3_relative_service_cost.py, "
                              "from output/summary/phase23_modeler_tradeoff_curve_points.csv"}, f)
    logger.info("Ratio grid written: %d points.", len(ratio_grid))

    # Per-preset report, plus the band-narrowness comparison Sec.24 requires.
    rows = []
    for name, preset in presets.items():
        target_pct = preset["not_late_pct"]
        ratio = ratio_at_target(curve_points, today_pct, target_pct)
        abs_band = absolute_band_at(target_pct, envelope)
        if ratio is None:
            rows.append(dict(preset=name, target_not_late_pct=target_pct, ratio_median=None,
                              ratio_min=None, ratio_max=None, n_members=0, n_excluded=80,
                              abs_min=abs_band["min"], abs_median=abs_band["median"], abs_max=abs_band["max"],
                              ratio_band_narrower=None))
            continue
        ratio_band_width_pct_of_median = 100 * (ratio["max"] - ratio["min"]) / ratio["median"] if ratio["median"] else None
        abs_band_width_pct_of_median = 100 * (abs_band["max"] - abs_band["min"]) / abs_band["median"] if abs_band["median"] else None
        narrower = (ratio_band_width_pct_of_median is not None and abs_band_width_pct_of_median is not None
                    and ratio_band_width_pct_of_median < abs_band_width_pct_of_median)
        rows.append(dict(preset=name, target_not_late_pct=target_pct,
                          ratio_median=ratio["median"], ratio_min=ratio["min"], ratio_max=ratio["max"],
                          n_members=ratio["n_members"], n_excluded=ratio["n_excluded"],
                          abs_min=abs_band["min"], abs_median=abs_band["median"], abs_max=abs_band["max"],
                          ratio_band_width_pct_of_median=ratio_band_width_pct_of_median,
                          abs_band_width_pct_of_median=abs_band_width_pct_of_median,
                          ratio_band_narrower=narrower))
    preset_df = pd.DataFrame(rows)
    preset_df.to_csv(OUT_PRESET_REPORT, index=False)
    logger.info("Preset report:\n%s", preset_df.to_string(index=False))

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# Task 2b Part 3 -- METRICS.md Sec.24 relative_service_cost (PEM101)\n\n")
        f.write(f"today_not_late_pct (real business figure, phaseJ3_validator_stock_value_summary.csv) = {today_pct}\n\n")
        f.write("## Per-preset ratio_e vs. absolute band\n\n```\n" + preset_df.to_string(index=False) + "\n```\n")

    print("DONE")


if __name__ == "__main__":
    main()
