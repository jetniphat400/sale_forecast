"""Phase J2 Part 0 -- recompute METRICS.md Sec.19 delivery_timeliness (on_time_exact, not_late,
late; row- and unit-weighted) for 2023-2026, per division, to replace the superseded 73.2%
on_time_exact/row-weighted/2026-only figure wherever STATUS.md used it as a fill-rate-comparable
benchmark.

Due-date field: ForecastDelDate, per METRICS.md Sec.18's established convention ("actual_on_time
... from Cube_CES ActualDelDate against ForecastDelDate") -- consistent with Phase J, not a new
choice. PlanDelDate and ForecastDelDate are identical on 97.9% of assessable rows
(src/investigations/delivery_performance.py finding), so this differs negligibly from the
original 73.2% figure's own PlanDelDate basis.

Year grouping: CtrDate year (order/contract date), matching delivery_performance.py's own
precedent for "by year" on-time performance (not ActualDelDate or ForecastDelDate year).

NO new database query -- reuses output/data/phaseJ_cube_ces_351items.csv (Phase J's Cube_CES
pull, unbounded by CtrDate, covers 2017-2027) and output/data/phaseI_combined_scope_351items.csv
(code -> division mapping, pricelist-sourced, no DB).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CES_FILE = os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")


def classify(days):
    if pd.isna(days):
        return None
    if days == 0:
        return "on_time_exact"
    return "early" if days < 0 else "late"


def weighted_shares(df: pd.DataFrame, weight_col: str = None) -> dict:
    if weight_col is None:
        w = pd.Series(1.0, index=df.index)
    else:
        w = df[weight_col].astype(float)
    total = w.sum()
    if total <= 0:
        return {"on_time_exact": np.nan, "not_late": np.nan, "late": np.nan, "n_or_units": 0.0}
    on_time = w[df["status"] == "on_time_exact"].sum()
    early = w[df["status"] == "early"].sum()
    late = w[df["status"] == "late"].sum()
    return {"on_time_exact": on_time / total, "not_late": (on_time + early) / total,
            "late": late / total, "n_or_units": total}


def main():
    ces = pd.read_csv(CES_FILE)
    scope = pd.read_csv(SCOPE_FILE)
    code_to_division = dict(zip(scope["code"], scope["division"]))

    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["ForecastDelDate"] = pd.to_datetime(ces["ForecastDelDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")
    ces["division"] = ces["ItemCode"].map(code_to_division)
    ces = ces[ces["division"].notna()].copy()

    assessable = ces[(ces["Status"] == "Actual") & ces["ActualDelDate"].notna() &
                     ces["ForecastDelDate"].notna()].copy()
    assessable["year"] = assessable["CtrDate"].dt.year
    assessable["delay_days"] = (assessable["ActualDelDate"] - assessable["ForecastDelDate"]).dt.days
    assessable["status"] = assessable["delay_days"].apply(classify)

    n_excluded_no_actualdel = int(((ces["Status"] == "Actual") & ces["ActualDelDate"].isna()).sum())
    n_excluded_no_forecastdel = int(((ces["Status"] == "Actual") & ces["ActualDelDate"].notna() &
                                     ces["ForecastDelDate"].isna()).sum())

    window = assessable[(assessable["year"] >= 2023) & (assessable["year"] <= 2026)].copy()

    overall_rows = []
    for division, g in window.groupby("division"):
        row_w = weighted_shares(g, None)
        unit_w = weighted_shares(g, "ActualQty")
        overall_rows.append({"division": division, "weighting": "row", **row_w})
        overall_rows.append({"division": division, "weighting": "unit_ActualQty", **unit_w})
    overall_df = pd.DataFrame(overall_rows)

    byyear_rows = []
    for (division, year), g in window.groupby(["division", "year"]):
        row_w = weighted_shares(g, None)
        unit_w = weighted_shares(g, "ActualQty")
        byyear_rows.append({"division": division, "year": int(year), "weighting": "row", **row_w})
        byyear_rows.append({"division": division, "year": int(year), "weighting": "unit_ActualQty", **unit_w})
    byyear_df = pd.DataFrame(byyear_rows)

    overall_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_0_not_late_overall.csv"), index=False)
    byyear_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_0_not_late_byyear.csv"), index=False)

    print("=" * 100)
    print("PHASE J2 PART 0 -- delivery_timeliness (METRICS.md Sec.19), 2023-2026, due date = ForecastDelDate")
    print("=" * 100)
    print(f"Excluded (Status=Actual, no ActualDelDate): {n_excluded_no_actualdel}; "
          f"(no ForecastDelDate): {n_excluded_no_forecastdel}")
    print("\nOVERALL 2023-2026:")
    print(overall_df.to_string(index=False))
    print("\nBY YEAR:")
    print(byyear_df.to_string(index=False))
    return overall_df, byyear_df


if __name__ == "__main__":
    main()
