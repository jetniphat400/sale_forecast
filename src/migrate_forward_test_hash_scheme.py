"""One-off (task C2b, 2026-10-02): records, per forward-test vintage, the scheme its row_integrity_hash was
computed under (`row_hash_scheme` in output/summary/forward_test_log_all_divisions_metadata.json), so that
verification re-computes each hash the way it was made.

Why: vintage 1's hash was computed from rows read back from a CSV (an empty `type` is NaN, hashed as "nan");
vintage 2's hash was computed in memory by src/monthly_refresh.py (an empty `type` hashed as ""). Verification
used one scheme for both and refused vintage 2. The user decided to keep vintage 2's rows untouched and fix the
check (STATUS.md, phase C2b).

What it does: archives the log and the metadata with their SHA-256, finds for each vintage lacking a recorded
scheme the one scheme under which the recorded hash is reproduced from the log's CURRENT rows (and refuses if
none is), writes the scheme into the metadata, and proves that the forward-test log file itself is byte-for-byte
unchanged (it never writes the log). It makes no database connection.
"""
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forward_test_common import (HASH_SCHEMES, compute_row_integrity_hash, load_metadata, read_forward_test_log,
                                 save_metadata)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions.csv")
METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_log_all_divisions_metadata.json")
ARCHIVE_DIR = os.path.join(SUMMARY_DIR, "archive")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> dict:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    log_archive = os.path.join(ARCHIVE_DIR, f"forward_test_log_all_divisions_pre_hash_scheme_{stamp}.csv")
    meta_archive = os.path.join(ARCHIVE_DIR, f"forward_test_log_all_divisions_metadata_pre_hash_scheme_{stamp}.json")
    shutil.copy2(LOG_PATH, log_archive)
    shutil.copy2(METADATA_PATH, meta_archive)
    log_hash_before = sha256_of(LOG_PATH)
    report = {"archive_log": log_archive, "archive_metadata": meta_archive, "log_sha256_before": log_hash_before,
              "vintages": {}}

    log = read_forward_test_log(LOG_PATH)
    metadata = load_metadata(METADATA_PATH)
    for vkey, vmeta in metadata.items():
        rows = log[log["vintage_id"] == int(vkey)]
        recorded = vmeta["row_integrity_hash"]
        if "row_hash_scheme" in vmeta:
            ok = compute_row_integrity_hash(rows, vmeta["row_hash_scheme"]) == recorded
            report["vintages"][vkey] = {"scheme": vmeta["row_hash_scheme"], "already_recorded": True, "verifies": ok}
            if not ok:
                raise SystemExit(f"vintage {vkey}: recorded scheme {vmeta['row_hash_scheme']!r} does not reproduce its hash")
            continue
        matching = [s for s in HASH_SCHEMES if compute_row_integrity_hash(rows, s) == recorded]
        if not matching:
            raise SystemExit(f"vintage {vkey}: its recorded hash {recorded[:16]}... is reproduced by no known scheme -- "
                             f"the rows differ from what was hashed; nothing written")
        vmeta["row_hash_scheme"] = matching[0]
        report["vintages"][vkey] = {"scheme": matching[0], "all_matching_schemes": matching, "n_rows": len(rows),
                                    "recorded_hash": recorded[:16], "verifies": True}
    save_metadata(METADATA_PATH, metadata)

    log_hash_after = sha256_of(LOG_PATH)
    if log_hash_after != log_hash_before or sha256_of(log_archive) != log_hash_before:
        raise SystemExit("the forward-test log changed or does not equal its archive -- this must never happen")
    report["log_sha256_after"] = log_hash_after
    report["log_unchanged_byte_for_byte"] = True
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
