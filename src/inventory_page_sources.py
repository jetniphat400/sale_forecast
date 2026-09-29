"""Data sources for forecast/inventory.html that need no database connection.

build_inventory_page_data.build_data() normally pulls stock and PEM103/PEM107 sales live. This
module supplies the same tables from files already on disk, so the page can be rebuilt without a
second connection (DATABASE ACCESS rule):

  * saved_pull_sources()   -- the pulls a previous page build saved under output/snapshots/
                              (stock and sales), used to rebuild the page without touching the data;
  * daily_snapshot_sources() -- stock from the latest daily snapshot that src/snapshot_daily.py writes
                              (output/snapshots/inventory_daily_YYYY-MM-DD.csv), sales from output/data/
                              raw_all_divisions_sales.csv, which src/monthly_refresh.py step 1
                              (load_data_all_divisions.py) pulls each month. Used by the monthly runner.

Each returns keyword arguments for build_inventory_page.build_page(). The monthly runner pulls no stock
itself; the page shows the daily snapshot's own load time as the stock section's "data pulled" time.
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


DAILY_SNAPSHOT_PATTERN = "inventory_daily_*.csv"


def latest_daily_snapshot(snapshot_dir: str = None) -> str:
    files = sorted(glob.glob(os.path.join(snapshot_dir or SNAPSHOT_DIR, DAILY_SNAPSHOT_PATTERN)))
    if not files:
        raise SourceError(f"No daily stock snapshot ({DAILY_SNAPSHOT_PATTERN}) under {snapshot_dir or SNAPSHOT_DIR}; "
                          f"src/snapshot_daily.py writes one each day")
    return files[-1]


def _stock_from_daily(snapshot_dir: str = None):
    """(source function, metadata) built from the latest daily stock snapshot. The snapshot's own
    load_timestamp is the stock section's pull time. A snapshot written before task M2 has no
    minimum/maximum columns; the current Min/Max settings then come from the latest saved page pull
    (a setting, not a quantity) and the metadata says so."""
    path = latest_daily_snapshot(snapshot_dir)
    df = pd.read_csv(path)
    for c in ("itemcode", "warehouse", "stock", "load_timestamp"):
        if c not in df.columns:
            raise SourceError(f"{path} has no {c} column")
    meta = {"snapshot_file": os.path.basename(path), "load_time": str(df["load_timestamp"].min())[:19],
            "minmax_source": "daily snapshot"}
    if not {"minimum", "maximum"} <= set(df.columns):
        saved = pd.concat([_read_snapshot(n) for n in INVENTORY_NAMES], ignore_index=True) if not snapshot_dir else None
        if saved is None:
            raise SourceError(f"{path} has no minimum/maximum columns and no saved pull to take them from")
        settings = (saved.sort_values("_pull_time").drop_duplicates(["itemcode", "warehouse"], keep="last")
                    [["itemcode", "warehouse", "minimum", "maximum", "reserve_bywa"]])
        df = df.merge(settings, on=["itemcode", "warehouse"], how="left")
        meta["minmax_source"] = "latest saved page pull (the daily snapshot has no minimum/maximum columns yet)"
    if "reserve_bywa" not in df.columns:
        df["reserve_bywa"] = 0.0
    df["warehouse"] = df["warehouse"].astype(str).str.strip()

    def source(codes, allow_empty=False):
        return df[df["itemcode"].isin(set(codes))].reset_index(drop=True)

    return source, meta


def daily_snapshot_sources(runner_pull_time: str, snapshot_dir: str = None) -> dict:
    """Sales from the monthly runner's own pull, stock from the latest daily snapshot (module docstring)."""
    if not os.path.exists(RUNNER_RAW_SALES):
        raise SourceError("output/data/raw_all_divisions_sales.csv is missing -- the runner's step 1 writes it")
    inv, meta = _stock_from_daily(snapshot_dir)
    raw = pd.read_csv(RUNNER_RAW_SALES)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    label = str(runner_pull_time)[:19]
    return {"inventory_source": inv,
            "sales_source": lambda codes: raw[raw["itemcode"].isin(set(codes))][SALES_COLUMNS].reset_index(drop=True),
            "pull_labels": {"PEM103": label, "PEM107": label},
            "stock_pulled_at": meta["load_time"], "stock_meta": meta}
