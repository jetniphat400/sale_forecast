"""Task 2b, Part 4 -- PEM107 delivery-decline alert (the one-off entry point).

Since Prompt 35 (2026-10-15) the computation lives in production code, src/cube_ces_pull.py (`compute_pem107_alert`, `pull_pem107_alert`), which the monthly runner calls in
step 1 (`python src/cube_ces_pull.py --pem107-alert`). This script only runs that same code by hand: one read-only session through src/db.py, one login attempt, no retry.
It writes the same files the runner writes (output/summary/task2b_part4_pem107_alert.json, task2b_part4_pem107_alert_items.csv, task2b_part4_cube_ces_raw.csv). The
definitions, the scope (Cube_CES, RevenueType 'Omni Channel' in the SQL, Status 'Actual') and the limitations are documented beside the code there.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from cube_ces_pull import pull_pem107_alert  # noqa: E402
from db import session  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task2b_part4")


def main():
    with session(preflight=True):
        result = pull_pem107_alert(in_open_session=True)
    logger.info("Written: %s (%s)", result["written_to"], result["rows"])
    print("DONE")


if __name__ == "__main__":
    main()
