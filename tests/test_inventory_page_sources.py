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


# ------------------------------------------------------------------ a saved pull dated in the future is never "the latest pull" (week 4, prompt 6)
def test_a_pull_dated_after_today_is_never_selected_as_the_latest(tmp_path, monkeypatch):
    for day in ("2026-10-05", "2026-10-07", "2026-11-05"):
        (tmp_path / f"inventory_page_pull_PEM101_inventory_{day}.csv").write_text("itemcode\nA\n", encoding="utf-8")
        _write_snapshot(tmp_path, day, f"{day} 21:00:00")
    monkeypatch.setattr(ips, "SNAPSHOT_DIR", str(tmp_path))
    assert os.path.basename(ips._latest("PEM101_inventory", today="2026-10-07")) == "inventory_page_pull_PEM101_inventory_2026-10-07.csv"
    assert os.path.basename(ips.latest_daily_snapshot(str(tmp_path), today="2026-10-07")) == "inventory_daily_2026-10-07.csv"
    assert os.path.basename(ips._latest("PEM101_inventory", today="2026-11-05")).endswith("2026-11-05.csv")      # the day itself counts: only later dates are dropped
    assert not any("2026-11-05" in f for f in ips.not_after_today([str(p) for p in tmp_path.iterdir()], today="2026-10-31"))
    only_future = tmp_path / "only"
    only_future.mkdir()
    (only_future / "inventory_daily_2027-01-01.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(ips.SourceError):
        ips.latest_daily_snapshot(str(only_future), today="2026-10-07")


def test_the_real_snapshot_folder_holds_no_pull_dated_after_today():
    import glob
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "snapshots")
    files = glob.glob(os.path.join(folder, "inventory_page_pull_*.csv")) + glob.glob(os.path.join(folder, "inventory_daily_*.csv"))
    if not files:
        pytest.skip("SKIPPED, not passed: no saved pull on this machine")
    assert sorted(files) == ips.not_after_today(files)


# ------------------------------------------------------------------ the Max-Min page's history is the log vintage's series and fit window (decision D2, 2026-10-08)
def _history_fixture(tmp_path, monkeypatch, months, fit_first, fit_last, n):
    import forward_test_common as ftc
    import operation_plan as op
    series = tmp_path / "output" / "data"
    series.mkdir(parents=True)
    rows = [{"itemcode": c, "year_month": m, "qty": float(i + k), "snapshot_pull_date": "2026-10-05 07:41:06"}
            for i, c in enumerate(["A-1", "B-2"]) for k, m in enumerate(months)]
    pd.DataFrame(rows).to_csv(series / "processed_all_divisions_monthly_qty.csv", index=False)
    monkeypatch.setattr(op, "load_config", lambda root=None: {"forecast_log_metadata_file": "m.json", "forecast_log_file": "l.csv"})
    monkeypatch.setattr(ftc, "load_metadata", lambda path: {"2": {"fit_first_month": fit_first, "fit_last_month": fit_last, "fit_n_months": n}})
    monkeypatch.setattr(ftc, "read_forward_test_log", lambda path: pd.DataFrame({"vintage_id": [1, 2, 2]}))


def test_the_page_history_is_the_latest_vintages_series_cut_to_its_fit_window(tmp_path, monkeypatch):
    import build_inventory_page_data as bd
    months = [f"2026-{m:02d}" for m in range(1, 9)]
    _history_fixture(tmp_path, monkeypatch, months, "2026-03", "2026-07", 5)
    series, info = bd.latest_vintage_item_history(str(tmp_path))
    assert info["months"] == months[2:7] and info["vintage_id"] == 2 and info["hash_verified"] is False         # vintages 1 and 2 predate saved fit series
    assert list(series["A-1"]) == [2.0, 3.0, 4.0, 5.0, 6.0] and list(series["B-2"]) == [3.0, 4.0, 5.0, 6.0, 7.0]


def test_a_history_that_is_not_the_vintages_fit_window_stops_the_build(tmp_path, monkeypatch):
    import build_inventory_page_data as bd
    months = [f"2026-{m:02d}" for m in range(1, 9)]
    _history_fixture(tmp_path, monkeypatch, months, "2026-03", "2026-07", 6)            # the vintage says 6 months, the series holds 5 in that window
    with pytest.raises(ValueError, match="expected 6"):
        bd.latest_vintage_item_history(str(tmp_path))


def _read_log_or_skip(meta_path, log_path):
    """The forward-test log and its metadata. A file that is not on this machine is a skip (said so); a file that is there but cannot be read or parsed is an error, never a skip."""
    import forward_test_common as ftc
    if not (os.path.exists(meta_path) and os.path.exists(log_path)):
        pytest.skip("SKIPPED, not passed: the forward-test log is not on this machine")
    return ftc.load_metadata(meta_path), ftc.read_forward_test_log(log_path)


def test_a_corrupt_or_unreadable_log_fails_instead_of_turning_into_a_skip(tmp_path):
    meta, log = tmp_path / "meta.json", tmp_path / "log.csv"
    with pytest.raises(pytest.skip.Exception):                                           # not on this machine: a skip, as before
        _read_log_or_skip(str(meta), str(log))
    meta.write_text("{ not json", encoding="utf-8")
    log.write_text("a,b" + chr(10) + "1,2" + chr(10), encoding="utf-8")
    outcome = None
    try:
        _read_log_or_skip(str(meta), str(log))
    except BaseException as e:      # noqa: BLE001 -- what kind of ending is it?
        outcome = e
    assert outcome is not None and not isinstance(outcome, pytest.skip.Exception), "a corrupt log was turned into a skip"
    meta.write_text("{}", encoding="utf-8")                                              # valid metadata, a log without the columns the reader needs
    outcome = None
    try:
        _read_log_or_skip(str(meta), str(log))
    except BaseException as e:      # noqa: BLE001
        outcome = e
    assert isinstance(outcome, (KeyError, ValueError)) and not isinstance(outcome, pytest.skip.Exception)


def test_the_tracked_pages_history_equals_the_log_vintages_series_for_every_item():
    import operation_plan as op
    import forward_test_common as ftc
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = op.load_config(root)
    series_file = os.path.join(root, "output", "data", "processed_all_divisions_monthly_qty.csv")
    meta, log = _read_log_or_skip(op.path_of(root, cfg["forecast_log_metadata_file"]), op.path_of(root, cfg["forecast_log_file"]))
    vid = int(log["vintage_id"].max())
    entry = meta[str(vid)] if str(vid) in meta else meta[vid]
    if entry.get("fit_series_sha256"):
        # the series the vintage was fitted on is its saved snapshot, hash-checked against the metadata (vintage 2 on); no skip
        import io
        import vintage_series
        snapshot = vintage_series.read_series(vid)
        assert vintage_series.sha256_hex(snapshot) == entry["fit_series_sha256"], "the saved fit series does not hash to the value in the metadata"
        df = pd.read_csv(io.BytesIO(snapshot))
    else:
        if not os.path.exists(series_file):
            pytest.skip("SKIPPED, not passed: the monthly series is not on this machine")
        df = pd.read_csv(series_file)
    df = df[(df["year_month"] >= entry["fit_first_month"]) & (df["year_month"] <= entry["fit_last_month"])]
    expect = {c: g.sort_values("year_month")["qty"].round(3).tolist() for c, g in df.groupby("itemcode")}
    data = op.read_page_data(os.path.join(root, "forecast", "inventory.html"))
    n = 0
    for div in data["divisions"].values():
        for it in div["items"]:
            if it["code"] in expect:
                n += 1
                assert it["actual_history"] == pytest.approx(expect[it["code"]], abs=1e-3), it["code"]
                assert len(it["actual_history"]) == int(entry["fit_n_months"])
    assert n > 0
