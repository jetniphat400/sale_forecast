"""Phase J Part 6 -- regenerate forecast/inventory.html from the newly-written pipeline CSVs
(Part 4's robust defaults), WITHOUT a second database connection.

CORRECTION (recorded here, not hidden -- see STATUS.md Phase J entry): the first run of this
script DID make an unintended second live database connection, because
src/build_inventory_page_data.py's build_data() calls phaseE2_pilot_recompute.pull_raw_sales(...)
directly for PEM103/PEM107, in addition to _build_pilot_division's query_inventory_exact(...) call
-- only the second of those two live-query call sites had been monkeypatched. Both are patched
below now. The one unintended query was a read-only SELECT over the same 223 already-cached item
codes (no data modified, no credential exposure) -- but it is a real violation of this task's
"one connection attempt only" rule, disclosed here and in STATUS.md's Phase J entry rather than
silently corrected.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseE1_common
import build_inventory_page_data
import build_inventory_page

CACHED_INV_FILE = os.path.join(phaseE1_common.PROJECT_ROOT, "output", "data",
                                "phaseI_inventory_exact_351items.csv")
CACHED_RAW_SALES_FILE = os.path.join(phaseE1_common.PROJECT_ROOT, "output", "data",
                                      "phaseI_raw_sales_351items.csv")


def _cached_query_inventory_exact(item_codes: list) -> pd.DataFrame:
    df = pd.read_csv(CACHED_INV_FILE)
    df["warehouse"] = df["warehouse"].astype(str).str.strip()
    out = df[df["itemcode"].isin(item_codes)].copy()
    print(f"[monkeypatch] served {len(out)} cached inventory rows for {len(item_codes)} codes "
          f"from {CACHED_INV_FILE} (no new DB connection)")
    return out


def _cached_pull_raw_sales(config: dict, codes: list) -> pd.DataFrame:
    df = pd.read_csv(CACHED_RAW_SALES_FILE)
    df["createDate"] = pd.to_datetime(df["createDate"])
    df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
    out = df[df["itemcode"].isin(codes)].copy()
    print(f"[monkeypatch] served {len(out)} cached raw-sales rows for {len(codes)} codes "
          f"from {CACHED_RAW_SALES_FILE} (no new DB connection)")
    return out


def main():
    # Patch the names as imported into build_inventory_page_data's own namespace.
    build_inventory_page_data.query_inventory_exact = _cached_query_inventory_exact
    build_inventory_page_data.pull_raw_sales = _cached_pull_raw_sales
    out_path = build_inventory_page.main()
    print(f"Regenerated {out_path}")
    return out_path


if __name__ == "__main__":
    main()
