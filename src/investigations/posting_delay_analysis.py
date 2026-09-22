"""Analyse output/snapshots/posting_delay.csv (written by src/snapshot_daily.py) to measure the
actual posting delay: for each createDate, how many days after that createDate did its row count
in cube_Sale_APD stop changing (i.e. reach the value it still holds in the most recent snapshot,
and hold it in every snapshot after that)? This is the prospective measurement STATUS.md's
posting-delay entry (2026-09-22) proposed in place of the impossible retrospective one --
`timeStamp` is a full-table-reload artifact and no insert/modified-date column exists, so
first-appearance cannot be reconstructed from the table itself; only watching it change over time,
going forward, can answer this.

DO NOT CHANGE THE LEAKAGE GUARD'S 30-DAY MARGIN (src/leakage_guard.py, config.yaml
leakage_guard.min_margin_days) based on this script's output UNTIL:
  (a) at least 60 days of daily snapshots exist (config below: MIN_DAYS_TO_REPORT for a first
      look at 30 days, MIN_DAYS_FOR_MARGIN_DECISION for an actual margin decision at 60), AND
  (b) its 99th-percentile days-to-stabilize figure is known from that data.
Before both hold, the 30-day margin remains the reasoned-but-unmeasured precaution recorded in
STATUS.md -- this script reports evidence, it does not itself decide or change the margin.

This is read-only: no config or leakage_guard code is touched here.
"""
import json
import logging
import os
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_CSV = os.path.join(PROJECT_ROOT, "output", "snapshots", "posting_delay.csv")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("posting_delay_analysis")

MIN_DAYS_TO_REPORT = 30
MIN_DAYS_FOR_MARGIN_DECISION = 60


def load_snapshots() -> pd.DataFrame:
    if not os.path.exists(SNAPSHOT_CSV):
        raise FileNotFoundError(
            f"{SNAPSHOT_CSV} does not exist -- src/snapshot_daily.py has not been run yet.")
    df = pd.read_csv(SNAPSHOT_CSV, dtype=str)
    df["run_date"] = pd.to_datetime(df["run_date"])
    df = df.sort_values("run_date").reset_index(drop=True)
    return df


def build_createdate_timeseries(snapshots: pd.DataFrame) -> dict:
    """{createDate: [(run_date, count), ...]} sorted by run_date, pooled across every snapshot
    that had that createDate in its (rolling, 60-day) window."""
    series = {}
    for _, row in snapshots.iterrows():
        counts = json.loads(row["counts_by_createdate_json"])
        for cd_str, count in counts.items():
            series.setdefault(cd_str, []).append((row["run_date"], int(count)))
    for cd_str in series:
        series[cd_str].sort(key=lambda t: t[0])
    return series


def days_to_stabilize(series: dict) -> pd.DataFrame:
    """For each createDate with >=2 observations: the final observed count is whatever it reads
    in its LAST available observation. Stabilization day = the earliest run_date from which every
    subsequent observation (through the last) already equals that final count. A createDate whose
    count is still changing as of the last available snapshot is NOT included (not yet resolved)."""
    rows = []
    for cd_str, obs in series.items():
        if len(obs) < 2:
            continue
        final_count = obs[-1][1]
        # Walk backward from the end; find the earliest index where the run holds the final value
        # continuously through to the end.
        stabilize_idx = len(obs) - 1
        for i in range(len(obs) - 1, -1, -1):
            if obs[i][1] == final_count:
                stabilize_idx = i
            else:
                break
        if stabilize_idx == 0 and obs[0][1] != final_count:
            continue  # never actually reached a stable run in the observed window
        # Require confirmation: the value must have been reached AND held for at least one
        # observation before the end, OR the createDate has aged fully out of view (i.e. this is
        # as much data as will ever exist for it). Otherwise a single trailing observation could
        # be mistaken for "stable" when it might still change tomorrow.
        confirmed = (len(obs) - stabilize_idx) >= 2 or stabilize_idx == 0
        if not confirmed:
            continue
        stabilize_run_date = obs[stabilize_idx][0]
        create_date = pd.to_datetime(cd_str)
        gap_days = (stabilize_run_date - create_date).days
        if gap_days < 0:
            continue  # createDate after the run that "stabilized" it -- not a real measurement
        rows.append({"createDate": cd_str, "final_count": final_count,
                     "stabilize_run_date": stabilize_run_date, "days_to_stabilize": gap_days,
                     "n_observations": len(obs)})
    return pd.DataFrame(rows)


def main():
    snapshots = load_snapshots()
    n_days = snapshots["run_date"].nunique()
    logger.info("%d distinct snapshot day(s) available in %s.", n_days, SNAPSHOT_CSV)

    if n_days < MIN_DAYS_TO_REPORT:
        print(f"Only {n_days} snapshot day(s) collected so far -- need at least "
              f"{MIN_DAYS_TO_REPORT} before reporting a distribution. Not reported. "
              f"The 30-day leakage-guard margin stays unchanged.")
        return

    series = build_createdate_timeseries(snapshots)
    result = days_to_stabilize(series)
    if result.empty:
        print("No createDate in the collected snapshots has a confirmed-stable count yet. "
              "Not reported. The 30-day leakage-guard margin stays unchanged.")
        return

    gaps = result["days_to_stabilize"].to_numpy()
    pct = {p: float(np.percentile(gaps, p)) for p in (50, 90, 95, 99)}
    print(f"Snapshot days available: {n_days}")
    print(f"createDates with a confirmed stabilization point: {len(result)}")
    print(f"days-to-stabilize: median={pct[50]:.1f}, p90={pct[90]:.1f}, p95={pct[95]:.1f}, "
          f"p99={pct[99]:.1f}, max={gaps.max():.0f}")

    if n_days < MIN_DAYS_FOR_MARGIN_DECISION:
        print(f"Only {n_days} of the {MIN_DAYS_FOR_MARGIN_DECISION} days needed for a margin "
              f"decision are available -- this is a preliminary look, not yet sufficient evidence "
              f"to change leakage_guard.min_margin_days. It stays at 30 until "
              f"{MIN_DAYS_FOR_MARGIN_DECISION} days of data exist and p99 is known from that data.")
    else:
        print(f"{n_days} days of data available (>= {MIN_DAYS_FOR_MARGIN_DECISION}) -- p99 above "
              f"is now evidence-backed. Changing the margin is still a separate decision, not made "
              f"by this script.")


if __name__ == "__main__":
    main()
