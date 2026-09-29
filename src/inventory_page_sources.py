"""Data sources for forecast/inventory.html that need no database connection.

build_inventory_page_data.build_data() normally pulls stock and PEM103/PEM107 sales live. This
module supplies the same tables from files already on disk, so the page can be rebuilt without a
second connection (DATABASE ACCESS rule):

  * saved_pull_sources()   -- the pulls a previous page build saved under output/snapshots/
                              (stock and sales), used to rebuild the page without touching the data;
  * runner_pull_sources()  -- stock from the latest saved pull, sales from output/data/
                              raw_all_divisions_sales.csv, which src/monthly_refresh.py step 1
                              (load_data_all_divisions.py) pulls each month.

Each returns keyword arguments for build_inventory_page.build_page(). The stock table is never
pulled by the monthly runner, so runner_pull_sources() reports the saved stock pull's own time and
the page shows the older of the two pull times as its "data pulled" time.
"""
import glob
import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "output", "snapshots")
RUNNER_RAW_SALES = os.path.join(PROJECT_ROOT, "output", "data", "raw_all_divisions_sales.csv")
INVENTORY_NAMES = ("PEM101_inventory", "PEM103_inventory", "PEM107_inventory")
SALES_COLUMNS = ["itemcode", "createDate", "forecast_date", "qty", "sale", "status"]


class SourceError(Exception):
    """A saved source needed to rebuild the page is missing."""


def _latest(name: str) -> str:
    files = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, f"inventory_page_pull_{name}_*.csv")))
    if not files:
        raise SourceError(f"No saved pull inventory_page_pull_{name}_*.csv under output/snapshots/")
    return files[-1]


def _read_snapshot(name: str) -> pd.DataFrame:
    df = pd.read_csv(_latest(name))
    for c in df.columns:
        if "date" in c.lower():
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def _inventory_source():
    frames = {n: _read_snapshot(n) for n in INVENTORY_NAMES}

    def source(codes, allow_empty=False):
        wanted = set(codes)
        best = max(frames.values(), key=lambda df: len(wanted & set(df["itemcode"])))
        return best[best["itemcode"].isin(wanted)].reset_index(drop=True)

    pulled = min(str(df["_pull_time"].max()) for df in frames.values())
    return source, pulled


def saved_pull_sources(pull_labels: dict = None) -> dict:
    """Stock and sales from the saved page pulls; pull_labels overrides the pilot divisions' shown pull time."""
    inv, _ = _inventory_source()
    sales = _read_snapshot("PEM103_PEM107_sales")
    return {"inventory_source": inv, "sales_source": lambda codes: sales[sales["itemcode"].isin(set(codes))].reset_index(drop=True),
            "pull_labels": pull_labels}


def runner_pull_sources(runner_pull_time: str) -> dict:
    """Sales from the monthly runner's own pull, stock from the latest saved pull (see module docstring)."""
    if not os.path.exists(RUNNER_RAW_SALES):
        raise SourceError("output/data/raw_all_divisions_sales.csv is missing -- the runner's step 1 writes it")
    inv, stock_pulled = _inventory_source()
    raw = pd.read_csv(RUNNER_RAW_SALES)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    shown = min(str(runner_pull_time)[:19], stock_pulled[:19])
    label = f"{shown} (sales: monthly run {str(runner_pull_time)[:19]}; stock: saved pull {stock_pulled[:19]})"
    return {"inventory_source": inv,
            "sales_source": lambda codes: raw[raw["itemcode"].isin(set(codes))][SALES_COLUMNS].reset_index(drop=True),
            "pull_labels": {"PEM103": label, "PEM107": label}}
