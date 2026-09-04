"""End-to-end pipeline: pull data from the database, validate, aggregate to monthly at
all three levels (Category/Type/Item), forecast, backtest with rolling-origin, generate
the forward-test log, and export results -- in one documented run order, so this project
can be reproduced without knowing which of the 30-odd scripts in src/ to run and in what
sequence (STATUS.md, Phase B closeout task).

Every parameter comes from config/config.yaml -- this script hardcodes nothing itself; it
only decides WHICH existing script runs WHEN. Each stage is one of this project's existing,
already-tested scripts (src/load_data_full.py, src/aggregate_levels.py,
src/item_level_reconciliation.py, src/backtest_rekeyed.py, src/forward_test_v2.py,
src/score_forward_test_v2.py), run in-process as a subprocess of the same Python
interpreter this script runs under, so a failure in any stage raises loudly (non-zero
return code -> RuntimeError with the stage's full stdout/stderr attached) and stops the
run rather than continuing on partial/invalid state (CONVENTIONS.md: "Validation failures
must be raised loudly, never silently skipped").

WHY SUBPROCESSES, NOT DIRECT IMPORTS: every stage script is also a standalone,
independently-runnable tool with its own `if __name__ == "__main__":` block (useful for
re-running one stage in isolation while investigating something, a pattern used throughout
this project's history). Running each stage the same way a human would from the command
line -- rather than importing and calling internal functions -- guarantees the pipeline
exercises the exact same code path already validated stage by stage, with no risk of this
orchestrator silently drifting out of sync with what each stage's own script does when run
directly.

RUN LOG (CONVENTIONS.md: "Record for every run which data cutoff date and which config
were used, so results can be compared across runs"): every run appends one row to
output/summary/pipeline_run_log.csv and writes a matching
output/summary/pipeline_run_log_latest.json, recording the config hash (md5 of
config.yaml's bytes, src/forward_test.config_version -- the same hash already used to
version forward-test logs), the data pull timestamp (the frozen snapshot_pull_date written
by src/load_data_full.py), and row counts at each stage's key output files.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from forward_test import config_version

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_pipeline")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
RUN_LOG_CSV = os.path.join(SUMMARY_DIR, "pipeline_run_log.csv")
RUN_LOG_LATEST_JSON = os.path.join(SUMMARY_DIR, "pipeline_run_log_latest.json")

# Each stage: (label, script filename, key output files to count rows for after it runs).
# Order matters -- later stages depend on files earlier stages write (e.g. backtest_rekeyed.py
# reads part1_category_scope_all_codes.csv, written by load_data_full.py).
STAGES = [
    {
        "label": "pull_validate_aggregate_item_level",
        "script": "load_data_full.py",
        "outputs": {
            "category_scope": "part1_category_scope_all_codes.csv",
            "raw_sales": os.path.join("..", "data", "raw_full_category_sales.csv"),
            "monthly_createDate": os.path.join("..", "data", "processed_full_category_sales_monthly_createDate.csv"),
            "monthly_forecastDate": os.path.join("..", "data", "processed_full_category_sales_monthly_forecastDate.csv"),
        },
    },
    {
        "label": "aggregate_three_levels",
        "script": "aggregate_levels.py",
        "outputs": {
            "category_level_stats": "part2_category_level_stats.csv",
            "type_level_stats": "part2_type_level_stats.csv",
            "item_level_stats": "part2_item_level_stats.csv",
        },
    },
    {
        "label": "forecast_item_level_approaches",
        "script": "item_level_reconciliation.py",
        "outputs": {
            "item_level_test_scores": "b3_item_level_test_scores.csv",
            "item_level_summary": "b3_item_level_summary.csv",
        },
    },
    {
        "label": "backtest_rolling_origin_and_train_val_test",
        "script": "backtest_rekeyed.py",
        "outputs": {
            "rolling_origin_createDate": "b1_rolling_origin_results_createDate.csv",
            "rolling_origin_forecastDate": "b1_rolling_origin_results_forecastDate.csv",
            "test_results_forecastDate": "b1_test_results_forecastDate.csv",
        },
    },
    {
        "label": "generate_forward_test_log",
        "script": "forward_test_v2.py",
        "outputs": {
            "forward_test_log": "forward_test_log_v2.csv",
        },
    },
    {
        "label": "score_forward_test_log",
        "script": "score_forward_test_v2.py",
        "outputs": {
            "forward_test_scored": "forward_test_scored_v2.csv",
        },
        # This stage legitimately produces nothing scoreable yet if no target month has cleared
        # the leakage-guard margin -- that is expected, not a pipeline failure.
        "allow_missing_outputs": True,
    },
]


def run_stage(stage: dict) -> dict:
    """Runs one stage's script as a subprocess. Raises RuntimeError (loudly, with the
    stage's full stdout/stderr attached) on a non-zero return code -- a pipeline stage
    failing must stop the run, never be silently skipped."""
    script_path = os.path.join(SRC_DIR, stage["script"])
    logger.info("=== STAGE START: %s (%s) ===", stage["label"], stage["script"])
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    duration_s = time.time() - t0
    if result.returncode != 0:
        raise RuntimeError(
            f"PIPELINE STAGE FAILED: '{stage['label']}' ({stage['script']}) exited with code "
            f"{result.returncode}. Stopping the run -- a failed stage's outputs cannot be "
            f"trusted by any later stage.\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    logger.info("=== STAGE OK: %s (%.1fs) ===", stage["label"], duration_s)

    row_counts = {}
    for name, rel_path in stage["outputs"].items():
        abs_path = os.path.join(SUMMARY_DIR, rel_path)
        if not os.path.exists(abs_path):
            if stage.get("allow_missing_outputs"):
                row_counts[name] = None
                continue
            raise RuntimeError(
                f"PIPELINE STAGE '{stage['label']}' ({stage['script']}) completed with exit code 0 "
                f"but its expected output {abs_path} does not exist -- refusing to report this stage "
                f"as successful without its output present."
            )
        row_counts[name] = len(pd.read_csv(abs_path))
    return {"label": stage["label"], "script": stage["script"], "duration_s": round(duration_s, 1),
            "row_counts": row_counts, "stdout_tail": result.stdout[-2000:]}


def get_data_pull_timestamp() -> str:
    """Reads the frozen snapshot_pull_date written by src/load_data_full.py's pull this run --
    the single source of truth for "which data cutoff was used" (CONVENTIONS.md reproducibility
    rule), never re-derived or re-queried separately here."""
    monthly_path = os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")
    monthly = pd.read_csv(monthly_path, usecols=["snapshot_pull_date"])
    values = monthly["snapshot_pull_date"].unique()
    if len(values) != 1:
        raise RuntimeError(f"Expected exactly one snapshot_pull_date in {monthly_path}, found {values}")
    return str(values[0])


def append_run_log(run_record: dict) -> None:
    """Appends this run's summary to output/summary/pipeline_run_log.csv (one row per run,
    kept across runs so results can be compared over time) and overwrites
    output/summary/pipeline_run_log_latest.json with the full detail of just this run."""
    row = {
        "run_started_at": run_record["run_started_at"],
        "run_finished_at": run_record["run_finished_at"],
        "config_hash": run_record["config_hash"],
        "data_pull_timestamp": run_record["data_pull_timestamp"],
        "total_duration_s": run_record["total_duration_s"],
    }
    for stage in run_record["stages"]:
        for name, count in stage["row_counts"].items():
            row[f"{stage['label']}.{name}_rows"] = count
    row_df = pd.DataFrame([row])
    if os.path.exists(RUN_LOG_CSV):
        existing = pd.read_csv(RUN_LOG_CSV)
        combined = pd.concat([existing, row_df], ignore_index=True, sort=False)
    else:
        combined = row_df
    combined.to_csv(RUN_LOG_CSV, index=False)

    with open(RUN_LOG_LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(run_record, f, indent=2, default=str)


def write_export_manifest(run_record: dict) -> str:
    """'Export results' stage: consolidates a manifest of every file this run produced or
    confirmed present, with row counts and last-modified time, into one file a human can read
    to see the whole run's output at a glance without opening output/data and output/summary
    separately. Returns the manifest path."""
    rows = []
    for stage in run_record["stages"]:
        stage_def = next(s for s in STAGES if s["label"] == stage["label"])
        for name, rel_path in stage_def["outputs"].items():
            abs_path = os.path.join(SUMMARY_DIR, rel_path)
            exists = os.path.exists(abs_path)
            rows.append({
                "stage": stage["label"],
                "output_name": name,
                "path": os.path.relpath(abs_path, PROJECT_ROOT).replace("\\", "/"),
                "exists": exists,
                "rows": stage["row_counts"].get(name),
                "last_modified": (
                    datetime.fromtimestamp(os.path.getmtime(abs_path)).isoformat(timespec="seconds")
                    if exists else None
                ),
            })
    manifest = pd.DataFrame(rows)
    manifest_path = os.path.join(SUMMARY_DIR, "pipeline_run_manifest.csv")
    manifest.to_csv(manifest_path, index=False)
    return manifest_path


def main(stages_to_run=None) -> dict:
    run_started_at = datetime.now().isoformat(timespec="seconds")
    t0 = time.time()
    cfg_hash = config_version()
    logger.info("Pipeline run starting. config_hash=%s", cfg_hash)

    stages = STAGES if stages_to_run is None else [s for s in STAGES if s["label"] in stages_to_run]
    if not stages:
        raise ValueError(f"No matching stages for {stages_to_run} -- valid labels: {[s['label'] for s in STAGES]}")

    stage_records = []
    for stage in stages:
        stage_records.append(run_stage(stage))

    data_pull_timestamp = get_data_pull_timestamp() if os.path.exists(
        os.path.join(DATA_DIR, "processed_full_category_sales_monthly_forecastDate.csv")) else None

    run_record = {
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now().isoformat(timespec="seconds"),
        "config_hash": cfg_hash,
        "data_pull_timestamp": data_pull_timestamp,
        "total_duration_s": round(time.time() - t0, 1),
        "stages": stage_records,
    }
    append_run_log(run_record)
    manifest_path = write_export_manifest(run_record)

    logger.info("Pipeline run complete in %.1fs. Run log: %s / %s. Manifest: %s",
                run_record["total_duration_s"], RUN_LOG_CSV, RUN_LOG_LATEST_JSON, manifest_path)
    return run_record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", nargs="*", default=None,
                         help="Run only these stage labels (default: all stages, in order). "
                              f"Valid labels: {[s['label'] for s in STAGES]}")
    args = parser.parse_args()

    record = main(args.stages)

    print("\n" + "=" * 92)
    print("PIPELINE RUN SUMMARY")
    print("=" * 92)
    print(f"config_hash: {record['config_hash']}")
    print(f"data_pull_timestamp (frozen forecast_date snapshot): {record['data_pull_timestamp']}")
    print(f"Started: {record['run_started_at']}   Finished: {record['run_finished_at']}   "
          f"Total: {record['total_duration_s']}s")
    for stage in record["stages"]:
        print(f"\n[{stage['label']}] ({stage['script']}, {stage['duration_s']}s)")
        for name, count in stage["row_counts"].items():
            print(f"  {name}: {count if count is not None else 'not produced (expected for this stage)'} rows")
    print(f"\nFull run log: output/summary/pipeline_run_log.csv (all runs), "
          f"output/summary/pipeline_run_log_latest.json (this run in full)")
    print("Manifest: output/summary/pipeline_run_manifest.csv")
