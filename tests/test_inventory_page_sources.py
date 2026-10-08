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


# ------------------------------------------------------------------ the Max-Min page data is built on the latest forecast vintage (decision D2, 2026-10-08)
def test_the_page_forecast_is_the_latest_vintage_of_the_log_extended_flat_to_the_page_horizon(monkeypatch):
    import build_inventory_page_data as bd
    import forward_test_common as ftc
    import operation_plan as op
    wide = pd.DataFrame({"2026-09": [5.0, 0.0], "2026-10": [6.0, 0.0], "2026-11": [7.0, 1.0]}, index=["A-1", " B-2"])
    monkeypatch.setattr(op, "latest_vintage_forecast", lambda root, cfg: (wide, 3, ["2026-09", "2026-10", "2026-11"], True))
    log = pd.DataFrame({"vintage_id": [3, 3, 2], "level": ["Item", "Item", "Item"], "forecast_run_date": ["2026-11-02"] * 2 + ["2026-10-02"],
                        "data_cutoff_date": ["2026-11-02"] * 2 + ["2026-10-02"], "fit_last_month": ["2026-10"] * 2 + ["2026-08"]})
    monkeypatch.setattr(ftc, "read_forward_test_log", lambda path: log)
    out, info = bd.latest_vintage_item_forecasts(horizon=6)
    assert list(out["A-1"]) == [5.0, 6.0, 7.0, 7.0, 7.0, 7.0] and list(out["B-2"]) == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0]       # codes trimmed, last month repeated
    assert info == {"vintage_id": 3, "forecast_run_date": "2026-11-02", "data_cutoff_date": "2026-11-02", "fit_last_month": "2026-10",
                    "target_months": ["2026-09", "2026-10", "2026-11"], "source": "forward-test log, level Item"}


def test_the_tracked_page_carries_the_latest_log_vintage_and_every_log_item_has_its_forecast_on_the_page():
    import operation_plan as op
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = op.load_config(root)
    try:
        wide, vid, months, _ = op.latest_vintage_forecast(root, cfg)
    except Exception:       # noqa: BLE001
        pytest.skip("SKIPPED, not passed: the forward-test log is not on this machine")
    data = op.read_page_data(os.path.join(root, "forecast", "inventory.html"))
    assert data["forecast_vintage"]["vintage_id"] == vid and data["forecast_vintage"]["target_months"] == months
    n = 0
    for div in data["divisions"].values():
        for it in div["items"]:
            if it["code"] in wide.index:
                n += 1
                assert it["forecast"][:len(months)] == pytest.approx([round(float(wide.loc[it["code"], m]), 3) for m in months], abs=1e-3), it["code"]
    assert n > 0
    empty = [it["code"] for div in data["divisions"].values() for it in div["items"] if not it["forecast"] and it["code"] in wide.index]
    assert empty == []                     # no item that the log forecasts is shown on the page without a forecast
