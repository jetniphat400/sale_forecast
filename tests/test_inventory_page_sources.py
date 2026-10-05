"""The monthly runner builds forecast/inventory.html's stock section from the latest daily stock
snapshot (src/snapshot_daily.py), shows that snapshot's load time as the stock section's data-pulled
time, and shows the staleness notice when it is older than the configured threshold.

No database and no browser is needed. The stock figures and their dates are tested in tests/test_daily_stock_page.py.
"""
import json
import os
import re
import sys

import pandas as pd
import pytest

import inventory_page_sources as ips

STOCK_ROWS = [("AA-1", "FG01", 10.0, 2.0, 5.0, 0.0), ("AA-1", "WH21", 4.0, 1.0, 3.0, 0.0), ("BB-2", "FG01", 0.0, 0.0, 0.0, 0.0)]


def _write_snapshot(folder, day, load_time, with_settings=True):
    cols = ["itemcode", "warehouse", "stock", "minimum", "maximum", "reserve_bywa"]
    df = pd.DataFrame(STOCK_ROWS, columns=cols)
    if not with_settings:
        df = df[["itemcode", "warehouse", "stock"]]
    df["load_timestamp"] = load_time
    df.to_csv(os.path.join(str(folder), f"inventory_daily_{day}.csv"), index=False)


def test_the_latest_daily_snapshot_is_used_and_its_load_time_is_the_stock_pull_time(tmp_path):
    _write_snapshot(tmp_path, "2026-09-20", "2026-09-19 21:41:30")
    _write_snapshot(tmp_path, "2026-09-28", "2026-09-27 21:41:30")
    assert os.path.basename(ips.latest_daily_snapshot(str(tmp_path))) == "inventory_daily_2026-09-28.csv"
    source, meta = ips._stock_from_daily(str(tmp_path))
    assert meta["load_time"] == "2026-09-27 21:41:30" and meta["minmax_source"] == "daily snapshot"
    rows = source(["AA-1"])
    assert sorted(rows["warehouse"]) == ["FG01", "WH21"] and rows["stock"].sum() == 14.0
    assert {"minimum", "maximum", "reserve_bywa"} <= set(rows.columns)


def test_a_snapshot_without_settings_and_without_a_saved_pull_stops_loudly(tmp_path):
    _write_snapshot(tmp_path, "2026-09-28", "2026-09-27 21:41:30", with_settings=False)
    with pytest.raises(ips.SourceError):
        ips._stock_from_daily(str(tmp_path))


def test_no_snapshot_at_all_stops_loudly(tmp_path):
    with pytest.raises(ips.SourceError):
        ips.latest_daily_snapshot(str(tmp_path))


def test_snapshot_daily_keeps_the_settings_columns():
    with open(os.path.join(os.path.dirname(ips.__file__), "snapshot_daily.py"), encoding="utf-8") as f:
        text = f.read()
    assert '["itemcode", "warehouse", "stock", "minimum", "maximum", "reserve_bywa"]' in text


def test_page_embeds_no_stock_the_stock_file_carries_it():
    """The monthly runner builds the page from the latest daily snapshot for the Min and Max settings, but every
    stock-dependent input lives in data/stock_daily.json (src/stock_daily.py), which the page loads when it opens."""
    import build_inventory_page as bp
    sources = ips.daily_snapshot_sources("2026-09-29 12:13:32")
    page = bp.build_page(**sources)
    data = json.loads(re.search(r'id="inventory-data">(.*?)</script>', page, re.S).group(1))
    assert sources["stock_pulled_at"] == sources["stock_meta"]["load_time"]
    for division, dd in data["divisions"].items():
        assert "stock_pulled_at" not in dd, division
        for it in dd["items"]:
            assert "by_warehouse" not in it and "on_hand_sellable" not in it, (division, it["code"])
    assert "stock_meta" not in data
    assert 'id="stock-labels"' in page and "data/stock_daily.json" in page
    # Min, Max and the current settings stay embedded
    first = next(iter(data["divisions"].values()))["items"][0]
    assert "current_min" in first and "forecast" in first
