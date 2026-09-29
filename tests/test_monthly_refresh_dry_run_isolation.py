"""A dry run of src/monthly_refresh.py changes nothing outside a temporary folder.

The runner is started as the scheduled task would start it (its own python, absolute script path,
working directory elsewhere) in dry-run mode with --offline (no database connection; step 1 reuses
the data already under output/data) and --skip-tests (step 8 would otherwise run this test inside
itself). Every file under output/ and every tracked page is hashed before and after; the only
difference allowed is the new run log under output/runs/.

The dry run copies the project into a temporary root and runs every step there, so refreshed
analysis inputs, snapshots, forward-test rows and rebuilt pages never reach the real project. This
test removes the run log it created.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(PROJECT_ROOT, "src", "monthly_refresh.py")
RUNS_DIR = os.path.join(PROJECT_ROOT, "output", "runs")
TRACKED_PAGES = [os.path.join(PROJECT_ROOT, "forecast", "sales_report.html"),
                 os.path.join(PROJECT_ROOT, "forecast", "inventory.html"),
                 os.path.join(PROJECT_ROOT, "index.html")]

pytestmark = pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1",
                                reason="already running inside a dry-run copy of the project")


def _hash_tree(root):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            full = os.path.join(dirpath, f)
            h = hashlib.sha1()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            out[os.path.relpath(full, PROJECT_ROOT)] = h.hexdigest()
    return out


def _snapshot_state():
    state = _hash_tree(os.path.join(PROJECT_ROOT, "output"))
    for page in TRACKED_PAGES:
        with open(page, "rb") as f:
            state[os.path.relpath(page, PROJECT_ROOT)] = hashlib.sha1(f.read()).hexdigest()
    return state


def test_dry_run_changes_nothing_but_its_run_log(tmp_path):
    before = _snapshot_state()
    proc = subprocess.run([sys.executable, RUNNER, "--dry-run", "--offline", "--skip-tests"], cwd=str(tmp_path),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1500)
    after = _snapshot_state()
    new_logs = [k for k in after if k not in before]
    try:
        assert proc.returncode == 0, f"dry run failed:\n{proc.stderr[-3000:]}"
        changed = sorted(k for k in before if k in after and before[k] != after[k])
        removed = sorted(k for k in before if k not in after)
        assert not changed, f"a dry run changed real files: {changed[:10]}"
        assert not removed, f"a dry run removed real files: {removed[:10]}"
        unexpected = [k for k in new_logs if not (k.replace("\\", "/").startswith("output/runs/monthly_refresh_")
                                                  and k.endswith(".json"))]
        assert not unexpected, f"a dry run created files other than its run log: {unexpected[:10]}"
        assert len(new_logs) == 1, f"expected exactly one new run log, found {new_logs}"
        with open(os.path.join(PROJECT_ROOT, new_logs[0]), encoding="utf-8") as f:
            log = json.load(f)
        assert log["dry_run"] is True and log["dry_run_in_temporary_copy"] is True
        assert "aborted_at_step" not in log, log.get("aborted_at_step")
        for step in ("1_pull_data", "2_validate", "3_frozen_snapshot", "4_backtest", "5_new_forward_test_vintage",
                     "6_fill_and_score", "7_rebuild_pages", "9_scan_sensitive_content", "10_change_magnitude",
                     "11_commit_and_push"):
            assert log["steps"][step]["status"] == "ok", step
        # the rebuilt pages and the refreshed inputs exist only in the copy
        rendered = log["steps"]["7_rebuild_pages"]["result"]["inventory_rendered_path"]
        assert not os.path.exists(rendered), "the dry run's rebuilt inventory page should have been removed with its temporary copy"
    finally:
        for k in new_logs:
            try:
                os.remove(os.path.join(PROJECT_ROOT, k))
            except OSError:
                pass
