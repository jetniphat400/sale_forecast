"""One-off migration: adds METRICS.md Sec.27's `vintage_id` column to the existing
output/summary/forward_test_log_all_divisions.csv, and restructures its companion metadata file
from one flat dict into a dict keyed by vintage_id string, each entry carrying its own
row_integrity_hash (src/forward_test_common.compute_row_integrity_hash) -- so a later scoring run
can verify each vintage against ITS OWN recorded metadata/hash instead of the CURRENT live config
(src/score_forward_test_all_divisions.verify_consistency, adapted the same task).

METRICS.md Sec.27 already defines every other column this schema needs (itemcode,
forecast_run_date, data_cutoff_date, config hash [= the existing `config_version` column],
model, horizon, target_month, forecast_qty, actual_qty) -- confirmed column-by-column against the
existing log's header before this script was written (see this task's final report). The ONLY
column genuinely missing is a vintage identifier, so this migration adds exactly one column.

SAFETY (CONVENTIONS.md: keep raw data separate from processed, never overwrite raw without an
archive; verify, never recall):
  1. The log's CURRENT bytes are archived, unmodified, to
     output/summary/archive/forward_test_log_all_divisions_pre_vintage_migration_<date>.csv, and
     that archive copy's own SHA-256 is recorded (both in this script's printed report and in the
     new metadata file), so the pre-migration state can always be independently re-checked.
  2. After migration, every PRE-EXISTING column's values are diffed value-for-value against the
     archived copy (not just row-counted) -- this script refuses to proceed (raises) if anything
     other than the new vintage_id column differs.
"""
import hashlib
import logging
import os
import shutil
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from forward_test_common import ROW_HASH_COLUMNS, compute_row_integrity_hash, load_metadata, save_metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("migrate_forward_test_vintage")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
ARCHIVE_DIR = os.path.join(SUMMARY_DIR, "archive")
LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions.csv")
METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions_metadata.json")

PRE_EXISTING_COLUMNS = [
    "itemcode", "division", "level", "category", "type", "forecast_run_date", "data_cutoff_date",
    "fit_last_month", "model", "config_version", "date_key", "scope_hash", "scope_n_items",
    "horizon", "target_month", "forecast_qty", "actual_qty",
]


def sha256_of_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(today: str) -> dict:
    if not os.path.exists(LOG_PATH):
        raise FileNotFoundError(f"{LOG_PATH} does not exist -- nothing to migrate.")
    if not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(f"{METADATA_PATH} does not exist -- nothing to migrate.")

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = os.path.join(
        ARCHIVE_DIR, f"forward_test_log_all_divisions_pre_vintage_migration_{today}.csv")
    if os.path.exists(archive_path):
        raise FileExistsError(f"{archive_path} already exists -- migration already run today; refusing to overwrite.")
    shutil.copy2(LOG_PATH, archive_path)
    pre_migration_sha256 = sha256_of_file(archive_path)
    logger.info("Archived pre-migration log: %s (SHA-256 %s)", archive_path, pre_migration_sha256)

    original = pd.read_csv(LOG_PATH, dtype=str)
    original["forecast_qty"] = original["forecast_qty"].astype(float)
    original["horizon"] = original["horizon"].astype(int)
    original["scope_n_items"] = original["scope_n_items"].astype(int)
    n_rows_before = len(original)
    if list(original.columns) != PRE_EXISTING_COLUMNS:
        raise ValueError(f"Unexpected column set/order in {LOG_PATH}: {list(original.columns)}")

    migrated = original.copy()
    migrated.insert(0, "vintage_id", 1)

    # ---- Verify row count and every pre-existing value unchanged, value-for-value ----
    reread_archive = pd.read_csv(archive_path, dtype=str)
    reread_archive["forecast_qty"] = reread_archive["forecast_qty"].astype(float)
    reread_archive["horizon"] = reread_archive["horizon"].astype(int)
    reread_archive["scope_n_items"] = reread_archive["scope_n_items"].astype(int)
    if len(reread_archive) != n_rows_before:
        raise ValueError(f"Row count mismatch: archive has {len(reread_archive)}, expected {n_rows_before}.")
    compare_migrated = migrated[PRE_EXISTING_COLUMNS].reset_index(drop=True)
    compare_archive = reread_archive[PRE_EXISTING_COLUMNS].reset_index(drop=True)
    # actual_qty is entirely blank (NaN) in both -- compare as strings so NaN == NaN reads True.
    diff_mask = ~(compare_migrated.astype(str).eq(compare_archive.astype(str)))
    n_diffs = int(diff_mask.to_numpy().sum())
    if n_diffs != 0:
        bad_cols = diff_mask.any(axis=0)
        raise ValueError(
            f"{n_diffs} value(s) differ between the migrated file's pre-existing columns and the "
            f"archived pre-migration copy -- columns affected: {bad_cols[bad_cols].index.tolist()}. "
            f"Migration must change ONLY by adding vintage_id."
        )
    logger.info("Verified: %d rows before and after migration (unchanged), 0 value differences "
                "across all %d pre-existing columns (full value-for-value diff against the "
                "archived copy).", n_rows_before, len(PRE_EXISTING_COLUMNS))

    migrated.to_csv(LOG_PATH, index=False)
    n_rows_after = len(pd.read_csv(LOG_PATH))
    if n_rows_after != n_rows_before:
        raise ValueError(f"Post-write row count {n_rows_after} != pre-migration {n_rows_before}.")

    # ---- Metadata: restructure from one flat dict into {vintage_id_str: {...}} ----
    old_metadata = load_metadata(METADATA_PATH)
    archive_metadata_path = os.path.join(
        ARCHIVE_DIR, f"forward_test_log_all_divisions_metadata_pre_vintage_migration_{today}.json")
    shutil.copy2(METADATA_PATH, archive_metadata_path)

    vintage1_rows = migrated[migrated["vintage_id"] == 1]
    row_integrity_hash = compute_row_integrity_hash(vintage1_rows)

    new_metadata = {
        "1": {
            **old_metadata,
            "vintage_id": 1,
            "row_integrity_hash": row_integrity_hash,
            "row_integrity_hash_columns": ROW_HASH_COLUMNS,
            "row_integrity_hash_algorithm": "sha256",
            "migrated_from_flat_metadata_on": today,
            "migrated_by_script": "src/migrate_forward_test_vintage.py",
            "pre_migration_archive_csv": os.path.relpath(archive_path, PROJECT_ROOT).replace("\\", "/"),
            "pre_migration_archive_csv_sha256": pre_migration_sha256,
            "pre_migration_archive_metadata_json": os.path.relpath(archive_metadata_path, PROJECT_ROOT).replace("\\", "/"),
        }
    }
    save_metadata(METADATA_PATH, new_metadata)
    logger.info("Metadata restructured to per-vintage form: %s (vintage '1' row_integrity_hash=%s)",
                METADATA_PATH, row_integrity_hash[:16] + "...")

    return {
        "n_rows_before": n_rows_before,
        "n_rows_after": n_rows_after,
        "pre_migration_archive_csv": archive_path,
        "pre_migration_archive_csv_sha256": pre_migration_sha256,
        "row_integrity_hash_vintage1": row_integrity_hash,
        "n_value_diffs_vs_archive": n_diffs,
    }


if __name__ == "__main__":
    today_str = datetime.now().date().isoformat()
    result = main(today_str)
    print("\n" + "=" * 92)
    print("FORWARD-TEST LOG VINTAGE MIGRATION")
    print("=" * 92)
    for k, v in result.items():
        print(f"{k}: {v}")
