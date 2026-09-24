"""Phase 23, Part 1: confirm PEM101's distinct robust_minmax ensemble member count.

METRICS.md Sec.22, as amended this task: deduplicate ensemble members on reorder level
(r_months), order-up-to level (s_months), review interval and replenishment lead time only --
usable-stock definition does not enter Min_e/Max_e/range_ratio/the trade-off curve at all (the
prior task's own phase22_modeler_stockdef_effect.csv found a difference of exactly 0.0 for every
item; DATA_MAP.md Sec.4 Trap 19).

No new database access -- reuses output/summary/phaseJ3_2_grid_PEM101.csv (the existing,
already-computed 4,130-row grid, unchanged since Phase J3), filtered to METRICS.md Sec.20's own
both-window tolerance (calib/valid not_late diff <=3pp, calib/valid stock-value pctdiff <=15%) for
each of the 3 usable-stock definitions, then deduplicated to the 4-parameter identity.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from robust_minmax import dedup_ensemble_members

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
GRID_CSV = os.path.join(SUMMARY_DIR, "phaseJ3_2_grid_PEM101.csv")

STOCKDEFS = ["current", "fg_prefixed_only", "all_stockholding_except_qa_fmto_fmts"]
DEDUP_COLS = ["r_months", "s_months", "review_interval_days", "lead_time_days"]


def main():
    df = pd.read_csv(GRID_CSV)
    print(f"Loaded {len(df)} grid rows from {GRID_CSV}")

    passing_by_def = {}
    for d in STOCKDEFS:
        mask = (
            (df["calib_notlate_diff_pp"] <= 3)
            & (df["valid_notlate_diff_pp"] <= 3)
            & (df[f"calib_stockval_pctdiff_{d}"] <= 15)
            & (df[f"valid_stockval_pctdiff_{d}"] <= 15)
        )
        sub = df[mask].copy()
        sub["stockdef"] = d
        passing_by_def[d] = sub
        print(f"  {d}: {len(sub)} passing combinations")

    raw_members = pd.concat(passing_by_def.values(), ignore_index=True)
    raw_count = len(raw_members)
    print(f"Raw total (stockdef included in identity): {raw_count} "
          f"({' + '.join(str(len(v)) for v in passing_by_def.values())})")

    # dedup on the 4 simulation-affecting parameters only (METRICS.md Sec.22, amended this task) --
    # reuse the same robust_minmax.dedup_ensemble_members function used by the rest of this
    # project's Sec.22 code, with wh_set held constant (irrelevant for this identity now) so the
    # function's existing (params, wh_set) key collapses to a pure 4-parameter key.
    raw_dicts = [
        {
            "r_months": row.r_months, "s_months": row.s_months,
            "review_interval_days": row.review_interval_days, "lead_time_days": row.lead_time_days,
            "wh_set": frozenset(),  # constant -- usable-stock definition no longer part of identity
            "stockdef": row.stockdef,
        }
        for row in raw_members.itertuples()
    ]
    deduped = dedup_ensemble_members(raw_dicts)
    distinct_count = len(deduped)
    print(f"Distinct members (dedup on reorder level, order-up-to level, review interval, "
          f"replenishment lead time): {distinct_count}")

    r_range = raw_members["r_months"].agg(["min", "max"])
    print(f"r_months range across raw passing combinations: {r_range['min']}-{r_range['max']}")

    out = pd.DataFrame(deduped).drop(columns=["wh_set"])
    out_path = os.path.join(SUMMARY_DIR, "phase23_ensemble_distinct_members_PEM101.csv")
    out.to_csv(out_path, index=False)
    print(f"Saved {distinct_count} distinct members to {out_path}")

    assert distinct_count == 80, (
        f"Expected 80 distinct members (matches output/summary/phase22_validator_report.md Part 1, "
        f"lines 81-95), got {distinct_count} -- investigate before proceeding."
    )
    print("Confirmed: 80 distinct members, matching the prior task's independent Validator finding.")


if __name__ == "__main__":
    main()
