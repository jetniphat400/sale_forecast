"""Task 2a, Part 4 (2026-09-25): compute `not_late` per year alongside the existing
`on_time_exact` figure in delivery_by_year.csv.

METRICS.md Sec.19 (delivery_timeliness): on_time_exact = delivered ON the due date;
not_late = delivered ON OR BEFORE the due date. `delivery_by_year.csv`'s existing
`pct_on_time` column was established this task (grep + read,
src/investigations/delivery_performance.py lines 71-75 `classify_delay` and 155-161
`by_year` aggregation) to be on_time_exact, row-weighted, against `PlanDelDate`, PEM101
128-item scope only -- METRICS.md Sec.19's "Correction 2026-09-22" explicitly forbids
presenting on_time_exact as a fill-rate/delivery benchmark without also showing not_late.

This script reuses the SAME already-pulled raw data
(output/data/raw_cube_ces_delivery_128items.csv, pulled by delivery_performance.py,
last modified 2026-09-01 16:37 per `ls -la`) -- no new DB connection -- and recomputes
not_late against ForecastDelDate (not PlanDelDate, per this task's own instruction),
both row-weighted (each assessable delivery counts once) and unit-weighted (weighted by
ActualQty, the quantity actually delivered on that row). Unit-weighted is the version
charted on forecast/sales_report.html, because METRICS.md Sec.10 fill_rate is explicitly
unit-based ("not order-based") and this not_late figure is meant to be read alongside
fill_rate/service-level figures elsewhere in this project, not as an order-count share.
"""
import logging
import os
import sys

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task2a_delivery_notlate_by_year")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
RAW_PATH = os.path.join(DATA_DIR, "raw_cube_ces_delivery_128items.csv")
OUT_PATH = os.path.join(SUMMARY_DIR, "delivery_not_late_by_year.csv")


def main() -> pd.DataFrame:
    if not os.path.exists(RAW_PATH):
        raise FileNotFoundError(
            f"{RAW_PATH} not found -- run src/investigations/delivery_performance.py first "
            "to pull Cube_CES data for the PEM101 128-item scope."
        )
    raw = pd.read_csv(RAW_PATH)
    for c in ["CtrDate", "ForecastDelDate", "ActualDelDate"]:
        raw[c] = pd.to_datetime(raw[c], errors="coerce")

    # snapshot_pull_date: read forward from the raw pull's OWN recorded pull time (task 2cfix2,
    # Part 3 -- consuming pages must read a real pull-time field, never a file mtime proxy).
    # delivery_performance.py records this column on every pull since this task; a raw file
    # generated before that fix won't have it -- fail loudly rather than silently fall back to a
    # file mtime (CONVENTIONS.md: validation failures must be raised loudly).
    if "snapshot_pull_date" not in raw.columns:
        raise ValueError(
            f"{RAW_PATH} has no snapshot_pull_date column -- it was pulled by an older version of "
            "src/investigations/delivery_performance.py. Re-run that script first (it now records "
            "its own pull time into this raw file) before running this script."
        )
    snapshot_pull_date = str(raw["snapshot_pull_date"].iloc[0])

    # Same "assessable" definition as delivery_performance.py: completed (Actual) deliveries
    # with a real ActualDelDate. Backlog rows are not yet delivered and cannot be scored.
    assessable = raw[(raw["Status"] == "Actual") & raw["ActualDelDate"].notna()].copy()
    assessable["year"] = assessable["CtrDate"].dt.year
    assessable["delay_vs_forecast"] = (assessable["ActualDelDate"] - assessable["ForecastDelDate"]).dt.days
    assessable["not_late"] = assessable["delay_vs_forecast"] <= 0
    assessable["qty_weight"] = assessable["ActualQty"].fillna(0)

    rows = []
    for year, g in assessable.groupby("year"):
        n = len(g)
        row_weighted = 100.0 * g["not_late"].mean()
        total_qty = g["qty_weight"].sum()
        unit_weighted = (100.0 * g.loc[g["not_late"], "qty_weight"].sum() / total_qty
                          if total_qty > 0 else float("nan"))
        rows.append({
            "year": int(year), "n": n,
            "not_late_pct_row_weighted": row_weighted,
            "not_late_pct_unit_weighted": unit_weighted,
            "total_qty_assessable": total_qty,
        })
    out = pd.DataFrame(rows).sort_values("year")
    out["snapshot_pull_date"] = snapshot_pull_date
    out.to_csv(OUT_PATH, index=False)
    logger.info("Wrote %s (%d years, source rows: %d assessable of %d raw)",
                OUT_PATH, len(out), len(assessable), len(raw))
    return out


if __name__ == "__main__":
    result = main()
    print(result.to_string(index=False))
