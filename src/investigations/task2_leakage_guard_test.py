"""Task 2, step 4: prove the leakage guard actually stops a run, WITHOUT editing
config/config.yaml back and forth. Every violating scenario below passes an explicit
min_margin_days OVERRIDE directly to the guard/backtest functions (never touching the config
file), so config/config.yaml stays at its real, intended default (30) throughout this entire
script, before, during and after the test.

Three scenarios, increasing realism:
  1. Direct unit call to src/leakage_guard.check_window_closed with a deliberately huge
     min_margin_days (1000) against the real window end and real pull date.
  2. Same, but with a min_margin_days set to exactly 1 more day than the REAL actual gap (33),
     i.e. the smallest possible violating margin -- proves the boundary condition is exact, not
     off-by-one.
  3. Full end-to-end call through src/backtest_rekeyed.run_train_val_test with the real monthly
     data and real pull_date, but an inflated min_margin_days passed as an override argument
     (never written to config.yaml) -- proves the guard is actually wired into the backtest
     function itself, not just the standalone unit.

Also demonstrates the guard is silent (raises nothing) when the margin is satisfied, using the
REAL config default (30) and REAL data -- i.e., a passing case alongside the failing ones.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from backtest_rekeyed import build_level_series, run_train_val_test
from leakage_guard import LeakageGuardError, check_window_closed

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

if __name__ == "__main__":
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv"))
    pull_date = monthly["snapshot_pull_date"].iloc[0]
    window_end_month = sorted(monthly["year_month"].unique())[-1]
    real_gap_days = (pd.Timestamp(pull_date).normalize() - pd.Period(window_end_month, freq="M").end_time.normalize()).days
    print("#" * 100)
    print("TASK 2 STEP 4: LEAKAGE GUARD TEST (config/config.yaml is NOT touched by this script)")
    print("#" * 100)
    print(f"\nReal window end month: {window_end_month}. Real pull_date: {pull_date}. "
          f"Real actual gap: {real_gap_days} day(s). Real config default (config.yaml): 30.")

    print("\n" + "=" * 100)
    print("SCENARIO 1: direct call, min_margin_days OVERRIDE = 1000 (deliberately far larger than the real gap)")
    print("=" * 100)
    try:
        check_window_closed(window_end_month, pull_date, min_margin_days=1000)
        print("UNEXPECTED: no exception raised -- guard did NOT work.")
    except LeakageGuardError as e:
        print("EXPECTED FAILURE -- LeakageGuardError raised:")
        print(str(e))

    print("\n" + "=" * 100)
    print(f"SCENARIO 2: boundary case, min_margin_days OVERRIDE = {real_gap_days + 1} (exactly 1 day more than the real gap)")
    print("=" * 100)
    try:
        check_window_closed(window_end_month, pull_date, min_margin_days=real_gap_days + 1)
        print("UNEXPECTED: no exception raised -- guard did NOT work.")
    except LeakageGuardError as e:
        print("EXPECTED FAILURE -- LeakageGuardError raised:")
        print(str(e))

    print("\n" + "=" * 100)
    print(f"SANITY CHECK: min_margin_days OVERRIDE = {real_gap_days} (exactly the real gap) -- must PASS (>= is not <)")
    print("=" * 100)
    try:
        check_window_closed(window_end_month, pull_date, min_margin_days=real_gap_days)
        print("PASSED as expected: no exception (actual_gap_days == min_margin_days is NOT a violation, "
              "the guard's condition is `actual_gap_days < min_margin_days`).")
    except LeakageGuardError as e:
        print("UNEXPECTED FAILURE:")
        print(str(e))

    print("\n" + "=" * 100)
    print("SCENARIO 3: END-TO-END through backtest_rekeyed.run_train_val_test, min_margin_days OVERRIDE = 1000")
    print("(config/config.yaml's real value of 30 is never read or edited in this scenario -- the override is "
          "passed straight as a function argument, exactly as Task 2 instructs: 'a temporary override in the "
          "test rather than editing config.yaml back and forth')")
    print("=" * 100)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    series = build_level_series(monthly, scope)
    models = {}  # not needed -- the guard raises before any model is ever scored
    from models import get_models
    models = get_models([3, 6, 12])
    try:
        run_train_val_test(series, models, pull_date, min_margin_days=1000)
        print("UNEXPECTED: run_train_val_test completed -- guard did NOT stop the run.")
    except LeakageGuardError as e:
        print("EXPECTED FAILURE -- the real backtest function refused to run:")
        print(str(e))

    print("\n" + "=" * 100)
    print("CONTROL: same end-to-end call with the REAL config default (30) and REAL data -- must PASS")
    print("=" * 100)
    import yaml
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), "r", encoding="utf-8") as f:
        real_config = yaml.safe_load(f)
    from leakage_guard import load_min_margin_days
    real_min_margin = load_min_margin_days(real_config)
    print(f"config/config.yaml leakage_guard.min_margin_days = {real_min_margin} (read, not modified)")
    val_df, test_df = run_train_val_test(series, models, pull_date, real_min_margin)
    print(f"PASSED as expected: run_train_val_test completed normally with the real config default -- "
          f"{len(val_df)} val rows, {len(test_df)} test rows scored, no exception raised.")

    print("\nconfig/config.yaml was NEVER modified by this test script -- verify below.")
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), "r", encoding="utf-8") as f:
        tail = f.read()[-700:]
    print("--- last 700 chars of config/config.yaml (unchanged, real value still 30) ---")
    print(tail)
