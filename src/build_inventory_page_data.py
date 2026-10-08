"""Builds the embedded multi-division JSON data block for forecast/inventory.html.

Extended 2026-09-22 (Phase E2 Part 3) from a PEM101-only page to a division selector covering
PEM101, PEM103, PEM107 -- data is now keyed `divisions.<DIVISION>.items` instead of a single flat
`items` list. CI101/PEM102/PEM104 are listed under `disabled_divisions` with the reason they are
excluded (too few stocked items for a confident sellable-warehouse set, per
output/summary/phaseE2_readiness_report.md) -- never silently dropped from the page.

PEM101: unchanged data source (the frozen 31-month series + src/phaseE1fix_recompute.py's already
-written output files). PEM103/PEM107: no frozen series exists (that file is scoped to the
Fuse+Surge-Arrester product category, i.e. PEM101 only) -- this script's own fresh live pull and
in-memory series build, reusing src/phaseE2_pilot_recompute.py's already-written, already-run
scope/raw-pull/monthly-series functions directly (not re-deriving them), then re-reading that
same script's already-computed policy/Min/Max/stock-value/sellable-stock output files (this is
the page-BUILDER reading the Modeler's own output, exactly as it always has for PEM101 -- not a
Validator independence question, which does not apply to this presentation-layer script).

The page's client-side JS recomputes Min/Max/stock_value/months_of_cover/holding_cost from this
embedded RAW data (per division) whenever a Tier A control or the division selector changes -- it
never re-derives a number from a different source than this embedded block.

DATABASE ACCESS RULE: one connection attempt for this script's own PEM103/PEM107 live pull
(PEM101 needs none -- it reads the frozen file). If that first query fails, stop and raise.
"""
import json
import logging
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reader_values as rv
from phaseE1_common import (
    PROJECT_ROOT, SUMMARY_DIR, load_config, load_scope, load_monthly_series, topdown_item_forecast,
    query_inventory_exact, current_minmax_per_item,
)


SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "output", "snapshots")


def _persist_and_reload(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Task 2b Part 5: PEM103/PEM107's inventory.html data is pulled live at build time and was
    never otherwise kept -- every such pull is now written to a DATED file under
    output/snapshots/ (gitignored, per CONVENTIONS.md "never commit generated output") with its
    own pull time, and the page is built from THAT FILE (read back immediately), not the
    in-memory DataFrame the query returned -- so a later reader can verify any figure on the page
    against exactly the bytes this build used, not merely "whatever query ran that day"."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    pull_time = datetime.now()
    out = df.copy()
    out["_pull_time"] = pull_time.strftime("%Y-%m-%d %H:%M:%S")
    path = os.path.join(SNAPSHOT_DIR, f"inventory_page_pull_{name}_{pull_time.date().isoformat()}.csv")
    out.to_csv(path, index=False)
    logger.info("[%s] Live pull persisted to %s (%d rows, %.1f KB) -- building from this file, "
                "not the in-memory result.", name, path, len(out), os.path.getsize(path) / 1024)
    reloaded = pd.read_csv(path)
    # CSV round-tripping loses datetime dtype (becomes plain strings) -- restore it for any column
    # that was datetime64 in the original pull, so downstream .dt accessor code (build_monthly_
    # series's forecast_date.dt.to_period, etc.) sees the same dtypes it would have from the live
    # in-memory DataFrame, not a broken string column.
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            reloaded[col] = pd.to_datetime(reloaded[col], errors="coerce")
    return reloaded


def _by_warehouse_map(inv: pd.DataFrame) -> dict:
    """{itemcode: [{code, qty}, ...]} sorted by qty descending -- same shape/convention as
    index.html's stock panel (data/inventory.json's own `by_warehouse` field), added task 2b Part
    1 so the client-side checklist can recompute on_hand_sellable from whichever warehouses are
    checked, without a second database round-trip."""
    out = {}
    for code, g in inv.groupby("itemcode"):
        rows = (g.groupby("warehouse", as_index=False)["stock"].sum()
                 .sort_values("stock", ascending=False))
        out[code] = [{"code": w, "qty": round(float(q), 3)} for w, q in zip(rows["warehouse"], rows["stock"])]
    return out
from phaseE2_pilot_recompute import load_division_scope, pull_raw_sales, build_monthly_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_inventory_page_data")

FORECAST_HORIZON_MONTHS = 10


def latest_vintage_item_forecasts(horizon: int = FORECAST_HORIZON_MONTHS, root: str = PROJECT_ROOT) -> tuple:
    """(item forecast arrays, vintage info) from the LATEST vintage of the forward-test log, hash-checked (decision D2 of the user, 2026-10-08: Max-Min is built on the
    latest forecast vintage, not on a refit of its own). Each item's array holds the vintage's monthly forecasts in target-month order, extended to `horizon` months by
    repeating the vintage's last month (the Top-down combination is flat over its horizon, and the page's engine reads only the first months). The info names the
    vintage, its run date, data cutoff, fit end and target months; it is embedded in the page data as `forecast_vintage` so the runner's gate can compare it."""
    import operation_plan as op
    import forward_test_common as ftc
    cfg = op.load_config(root)
    wide, vid, months, _ = op.latest_vintage_forecast(root, cfg)
    log = ftc.read_forward_test_log(op.path_of(root, cfg["forecast_log_file"]))
    rows = log[(log["vintage_id"] == vid) & (log["level"] == cfg["forecast_level"])]
    out = {}
    for code, r in wide.iterrows():
        vals = [float(r[m]) for m in months]
        vals = vals + [vals[-1]] * max(0, horizon - len(vals))
        out[str(code).strip()] = np.asarray(vals[:horizon], dtype=float)
    info = {"vintage_id": int(vid), "forecast_run_date": str(rows["forecast_run_date"].iloc[0]), "data_cutoff_date": str(rows["data_cutoff_date"].iloc[0]),
            "fit_last_month": str(rows["fit_last_month"].iloc[0]), "target_months": [str(m) for m in months], "source": "forward-test log, level " + cfg["forecast_level"]}
    return out, info
def latest_vintage_item_history(root: str = PROJECT_ROOT) -> tuple:
    """(item series, info): the monthly quantities behind the Max-Min percentile, from the SAME series and fit window as the latest vintage of the forward-test log
    (decision D2 of the user, 2026-10-08), replacing the builder's own older series. The series is the one the vintage was fitted on: when the vintage's metadata
    records `fit_series_file` (vintage 3 on) that saved file, hash-checked; otherwise (vintages 1 and 2 predate it) `output/data/processed_all_divisions_monthly_qty.csv`,
    the file step 5 snapshots, cut to the vintage's `fit_first_month`..`fit_last_month`, and the info says it is not hash-verified. Stops when the window is not the
    vintage's `fit_n_months` months for an item."""
    import io
    import operation_plan as op
    import forward_test_common as ftc
    import vintage_series
    cfg = op.load_config(root)
    meta = ftc.load_metadata(op.path_of(root, cfg["forecast_log_metadata_file"]))
    log = ftc.read_forward_test_log(op.path_of(root, cfg["forecast_log_file"]))
    vid = int(log["vintage_id"].max())
    entry = meta[str(vid)] if str(vid) in meta else meta[vid]
    first, last, n_months = str(entry["fit_first_month"]), str(entry["fit_last_month"]), int(entry["fit_n_months"])
    verified = False
    if entry.get("fit_series_sha256"):
        data = vintage_series.read_series(vid)
        if vintage_series.sha256_hex(data) != entry["fit_series_sha256"]:
            raise ValueError(f"vintage {vid}: the saved fit series does not hash to the value its metadata records")
        df, verified, source = pd.read_csv(io.BytesIO(data)), True, entry["fit_series_file"]
    else:
        source = vintage_series.SERIES_SOURCE
        df = pd.read_csv(os.path.join(root, *source.split("/")))
    df = df[(df["year_month"] >= first) & (df["year_month"] <= last)]
    months = sorted(df["year_month"].unique())
    series = {}
    for code, g in df.groupby("itemcode"):
        g = g.sort_values("year_month")
        if len(g) != n_months or g["year_month"].tolist() != months:
            raise ValueError(f"{code}: {len(g)} months in the fit window {first}..{last}, expected {n_months}")
        series[str(code).strip()] = g["qty"].to_numpy(dtype=float)
    pull = str(df["snapshot_pull_date"].iloc[0]) if "snapshot_pull_date" in df.columns and len(df) else ""
    return series, {"vintage_id": vid, "months": months, "fit_first_month": first, "fit_last_month": last, "source": source, "hash_verified": verified, "series_pull_date": pull}


CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
PILOT_DIVISIONS = ["PEM101", "PEM103", "PEM107"]
# Short option label per disabled division. Reasons are built by disabled_division_reasons() so the
# "n of total" counts come from the data at build time, not from typed numbers.
DISABLED_DIVISION_LABELS = {"CI101": "ยังไม่เปิด", "PEM102": "ยังไม่เปิด", "PEM104": "ผลิตตามสั่ง"}
# Source of the stocked-item counts: output/summary/phaseE2_1_item_to_warehouse_reverse.csv
# (column has_stock_anywhere, one row per item; see output/summary/phaseE2_readiness_report.md).
# Earlier English reasons cited: CI101's small stock co-locates in PEM101's own FG01, not a
# CI101-specific location; PEM104 is made to order by business model (DATA_MAP.md Sec.7,
# PROJECT_GRAPH.md dead end DE4, business-confirmed 2026-09-23), consistent with 1 of 12 items
# (8.3%, 1 unit) ever holding stock.
STOCK_COVERAGE_PATH = os.path.join(SUMMARY_DIR, "phaseE2_1_item_to_warehouse_reverse.csv")


def _stocked_item_counts(division: str) -> tuple:
    """(items that ever hold stock, total items) for one division, from STOCK_COVERAGE_PATH."""
    if not os.path.exists(STOCK_COVERAGE_PATH):
        raise FileNotFoundError(f"Required source file missing: {STOCK_COVERAGE_PATH} "
                                f"(needed for the disabled-division reasons).")
    df = pd.read_csv(STOCK_COVERAGE_PATH)
    sub = df[df["division"] == division]
    if sub.empty:
        raise ValueError(f"{STOCK_COVERAGE_PATH} has no rows for division {division}.")
    return int(sub["has_stock_anywhere"].astype(bool).sum()), int(len(sub))


# Approved text (the user, 2026-10-06), shown for every division that has no Min and Max; {n_stock} is the number of items of the division classed
# stock_policy by METRICS.md Sec.23 (the item-level file, forecast-status and placeholder items).
NO_MIN_MAX_TEXT = "ยังไม่ได้คำนวณ Min/Max ให้ {n_stock} รหัสที่เข้าเกณฑ์เก็บ stock"
NO_MIN_MAX_TEXT_ZERO = "ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock"
NO_MIN_MAX_SEPARATOR = " · "


def stock_class_count(division: str) -> int:
    """Items of `division` classed stock_policy in the Sec.23 item-level file (column class_used). Stops when the file or the column is missing."""
    path = os.path.join(SUMMARY_DIR, "task2b_part2_item_level.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required source file missing: {path} (needed for the divisions without Min and Max).")
    df = pd.read_csv(path)
    if "class_used" not in df.columns:
        raise ValueError(f"{path} has no class_used column (the week 3 item-level file).")
    return int(((df["division"] == division) & (df["class_used"] == "stock_policy")).sum())


def no_min_max_line(division: str) -> str:
    """The approved line for a division without Min and Max: the count of its stock items, or the zero text."""
    n = stock_class_count(division)
    return NO_MIN_MAX_TEXT.format(n_stock=n) if n else NO_MIN_MAX_TEXT_ZERO


def disabled_division_reasons() -> dict:
    n_ci, t_ci = _stocked_item_counts("CI101")
    n_102, t_102 = _stocked_item_counts("PEM102")
    reasons = {
        "CI101": f"ยังไม่เปิด มีของในคลังแค่ {n_ci} จาก {t_ci} รหัส และอยู่ในคลังเดียวกับ PEM101 ยังกำหนดคลังของฝ่ายนี้ไม่ได้",
        "PEM102": f"ยังไม่เปิด มีของในคลังแค่ {n_102} จาก {t_102} รหัส น้อยเกินกว่าจะกำหนดคลังได้",
        "PEM104": "ไม่มีนโยบาย stock ฝ่ายนี้ผลิตตามสั่งทั้งหมด",
    }
    return {d: reason + NO_MIN_MAX_SEPARATOR + no_min_max_line(d) for d, reason in reasons.items()}


FULFILMENT_SEGMENTATION_DIVISIONS = ["PEM101", "PEM107"]  # task 2b Part 2 scope; PEM103 unaffected


def _load_fulfilment_segmentation(division: str) -> pd.DataFrame:
    """METRICS.md Sec.23, computed by src/investigations/task2b_part2_fulfilment_segmentation.py
    (task 2b Part 2) -- supersedes section 15 for G2 item eligibility on PEM101/PEM107. Returns one
    row per FORECAST-STATUS item (144 PEM101 / 112 PEM107 -- the full universe, wider than the
    128/136-item pilot scopes the pre-existing forecast/unit_cost pipeline covers)."""
    path = os.path.join(SUMMARY_DIR, "task2b_part2_item_level.csv")
    df = pd.read_csv(path)
    if "status_category" in df.columns:        # week 3: the file also holds placeholder items and the other divisions; the page's universe is the forecast-status items
        df = df[df["status_category"] == "forecast"]
    df = apply_class_decisions(df, load_config().get("fulfilment_class_decisions", {}))
    return df[df["division"] == division].set_index("code")


CLASS_BASIS_DECIDED = "decided_from_data_pending_confirmation"


def apply_class_decisions(df: pd.DataFrame, decisions: dict) -> pd.DataFrame:
    """The user's per-item class decisions on top of the Sec.23 rule (config `fulfilment_class_decisions`; the rule is not changed).
    `class_overrides`: items moved to stock_policy or confirmed_to_order from output/summary/phaseA_pem101_conflict_lean.md; they get
    class_basis = CLASS_BASIS_DECIDED so the page can label them. `g3_made_to_order`: PEM107's G3 list, which must already be
    confirmed_to_order under Sec.23 -- a code that is not stops the build rather than being reclassified here."""
    df = df.copy()
    df["class_basis"] = ""
    for division, codes in (decisions.get("g3_made_to_order") or {}).items():
        have = df[(df["division"] == division) & df["code"].isin(codes)]
        bad = sorted(set(codes) - set(have.loc[have["class"] == "confirmed_to_order", "code"]))
        if bad:
            raise ValueError(f"G3 made-to-order list for {division} holds code(s) not classed confirmed_to_order by Sec.23: {bad}")
    for division, spec in (decisions.get("class_overrides") or {}).items():
        for new_class in ("stock_policy", "confirmed_to_order"):
            for code in spec.get(new_class, []):
                hit = (df["division"] == division) & (df["code"] == code)
                if hit.sum() != 1:
                    raise ValueError(f"class override for {division} {code}: expected exactly one item, found {int(hit.sum())}")
                if df.loc[hit, "class"].iloc[0] != "conflict":
                    raise ValueError(f"class override for {division} {code}: the item is not in the conflict class today")
                df.loc[hit, "class"] = new_class
                df.loc[hit, "class_basis"] = CLASS_BASIS_DECIDED
    return df


def _build_curve_target_pem101() -> dict:
    """The PEM101 calibrated section's data (METRICS.md Sec.20 and 22), read from the recorded outputs of the Max-Min v1 ensemble
    (src/maxmin_v1.py, config `maxmin_v1`): the lead-time-free calibration on the 92 stock_policy items. Each file is hash-verified
    before it is read, and the build stops if one is missing or was changed. No database.
    Adds the lead-time lines' values (the lead range across the ensemble's members and the median slowest-material lead time) and, per
    item, the slowest-material lead time with the source of its value (METRICS.md Sec.5, item lead time version 1)."""
    import maxmin_v1
    cfg = maxmin_v1.load_config()
    data, data["relative_service_cost"] = maxmin_v1.load_page_inputs(cfg)
    seg_counts = _load_fulfilment_segmentation("PEM101")["class"].value_counts()
    n_current_set = int(seg_counts.get("stock_policy", 0))
    n_fitted = int(data["n_items_calibrated"])
    # The note states the fitted item count from the ensemble's own output. When the current stock_policy set differs from the fitted
    # set, the earlier approved clause saying so is kept.
    data["item_set_note"] = f"ปรับให้ตรงกับผลจริงจากสินค้า {n_fitted} รายการ"
    if n_current_set != n_fitted:
        data["item_set_note"] += f" ตอนนี้สินค้าที่เข้าเกณฑ์เก็บ stock มี {n_current_set} รายการ ยังไม่ได้ปรับใหม่ตามชุดนี้"
    first, last = maxmin_v1.demand_history_window(cfg)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data["demand_input_note"] = yaml.safe_load(f)["inventory_page"]["pem101_demand_note"].format(
            first_month=rv.thai_month_short(first), last_month=rv.thai_month_short(last))
    data["item_set_ref"] = ("count: n_items_calibrated of the Max-Min v1 ensemble output (src/maxmin_v1.py, week1_recal_targets.json n_items); "
                            "stock_policy count: task2b_part2_item_level.csv class stock_policy; METRICS.md Sec.23")
    lead = maxmin_v1.material_lead_for_page(data["items_order"], cfg)
    if lead["median_observed_days"] is None:
        raise ValueError("no item of the calibrated section has a material lead time from observed purchase records, so the median of the observed values is undefined")
    data["lead_time_lines"] = {"lead_min": data["lead_time_days"]["min"], "lead_max": data["lead_time_days"]["max"],
                               "material_lead_median_observed": lead["median_observed_days"], "n_observed": lead["n_observed"],
                               "n_items": lead["n_items_shown"]}
    data["item_material_lead"] = lead["per_item"]
    data["material_lead_label_counts"] = lead["label_counts"]
    data["lead_time_ref"] = ("lead_min and lead_max: smallest and largest lead_time_days over the distinct members of the lead-time-free "
                             "calibration (week1_recal_control_members_PEM101_92.csv); material_lead_median_observed: median of the slowest "
                             "material's lead time, production time excluded, over the shown items whose value comes from observed purchase records only; n_observed: "
                             "their count; n_items: the stock_policy items shown (item_lead_time_v1.csv, METRICS.md Sec.5); decisions D2, 2026-10-05, and D3, 2026-10-06")
    return data


def _build_pem101_division(config: dict, inventory_source=None) -> dict:
    e1 = config["phase_e1_assumptions"]
    sp = config["segment_policy"]
    scope = load_scope(config)
    hist, hist_info = latest_vintage_item_history()
    series = {c: (v, hist_info["months"]) for c, v in hist.items()}                 # D2: the log vintage's own series and fit window
    series_bundle = {"series": series, "pull_date": hist_info["series_pull_date"]}

    policy_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_item_policy.csv"))
    unit_cost_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_unit_cost.csv"))
    inv_summary = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_stock_value_inputs.csv"))

    fc_all, _vintage = latest_vintage_item_forecasts(FORECAST_HORIZON_MONTHS)

    # Task 2b Part 2 (METRICS.md Sec.23): item universe is now every PEM101 FORECAST-STATUS item
    # (144), classified stock_policy/confirmed_to_order/conflict -- superseding section 15's
    # finished_goods_stock/component_stock_ato policy for WHICH items get a Min/Max. The
    # pre-existing forecast/unit_cost pipeline (policy_df/unit_cost_df/inv_summary/series) still
    # only covers the older 128-item Fuse/Surge-Arrester pilot (PROJECT_GRAPH.md D3) -- 10 of the
    # 82 stock_policy items fall outside it and get min_max_computable=False rather than a
    # fabricated number (AGENTS.md rule 1/3: never guess, report the gap).
    seg = _load_fulfilment_segmentation("PEM101")
    codes_for_inv = list(seg.index)
    if inventory_source is not None:
        inv_raw = inventory_source(codes_for_inv, allow_empty=True)
    else:
        inv_raw = _persist_and_reload(query_inventory_exact(codes_for_inv, allow_empty=True), "PEM101_inventory")
    by_wh = _by_warehouse_map(inv_raw)
    policy_by_code = policy_df.set_index("code")["type"].to_dict()  # type/category still section-15-sourced, unaffected

    items = []
    for code, seg_row in seg.iterrows():
        fulfilment_class = seg_row["class"]
        in_pilot_scope = code in unit_cost_df["itemcode"].values
        uc_row = unit_cost_df[unit_cost_df["itemcode"] == code]
        oh_row = inv_summary[inv_summary["code"] == code]
        qty_hist = series[code][0].tolist() if code in series else []
        forecast = fc_all[code].tolist() if code in fc_all else []
        items.append({
            "code": code, "type": seg_row["type"] if pd.notna(seg_row.get("type")) else policy_by_code.get(code),
            "policy": fulfilment_class, "class_basis": seg_row["class_basis"],
            "fulfilment_label": seg_row["label"], "S1": bool(seg_row["S1"]) if pd.notna(seg_row["S1"]) else None,
            "S2": (bool(seg_row["S2"]) if pd.notna(seg_row["S2"]) else None), "S2_computable": bool(seg_row["S2_computable"]),
            "S3": bool(seg_row["S3"]) if pd.notna(seg_row["S3"]) else None,
            "min_max_computable": in_pilot_scope,
            "actual_history": [round(x, 3) for x in qty_hist],
            "forecast": [round(x, 3) for x in forecast],
            "unit_cost": float(uc_row["unit_cost"].iloc[0]) if len(uc_row) and pd.notna(uc_row["unit_cost"].iloc[0]) else None,
            "unit_cost_fallback": bool(uc_row["unit_cost_fallback"].iloc[0]) if len(uc_row) else None,
            "no_unit_cost_item": bool(uc_row["no_unit_cost_item"].iloc[0]) if len(uc_row) else True,
            "on_hand_sellable": float(oh_row["sellable_stock"].iloc[0]) if len(oh_row) else 0.0,
            "by_warehouse": by_wh.get(code, []),
        })

    n_stock_policy_outside_pilot = sum(
        1 for it in items if it["policy"] == "stock_policy" and not it["min_max_computable"])
    logger.info("[PEM101] %d stock_policy items are outside the 128-item pilot's forecast/"
                "unit_cost pipeline -- Min/Max not computable this task (min_max_computable=False).",
                n_stock_policy_outside_pilot)

    current_mm_path = os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_minmax.csv")
    current_mm = {}
    if os.path.exists(current_mm_path):
        cmm = pd.read_csv(current_mm_path)
        current_mm = {row["itemcode"]: {"current_min": row["current_total_min"], "current_max": row["current_total_max"]}
                      for _, row in cmm.iterrows()}
    for it in items:
        cm = current_mm.get(it["code"], {"current_min": None, "current_max": None})
        it["current_min"] = cm["current_min"]
        it["current_max"] = cm["current_max"]
        # a Max of 0 is "not filled in" only where the item has a record at all (src/build_inventory_page.py systemMaxText)
        it["current_has_record"] = cm["current_max"] is not None

    # task 2b Part 2: "no policy" now means status_category != 'forecast' (placeholder/excluded
    # from the full 445-item registry), not the old 128-item-pilot-scoped policy_df list.
    status_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv"))
    non_forecast = status_df[(status_df["division"] == "PEM101") & (status_df["status_category"] != "forecast")]
    no_policy = [{"code": r["itemcode"], "type": policy_by_code.get(r["itemcode"], ""), "policy": r["status_category"]}
                 for _, r in non_forecast.iterrows()]

    return {
        "items": items, "no_policy_items": no_policy,
        "sellable_warehouse_codes": e1["sellable_warehouse_codes"]["PEM101"],
        "segment_policy": sp,
        "snapshot_pull_date": series_bundle["pull_date"],
        "n_items_label": f"{len(items)} รายการ",
        "warehouse_scope_note": warehouse_scope_note_and_ref("PEM101")[0],
        # Reference kept off screen (the page renders it as an HTML comment).
        "warehouse_scope_ref": warehouse_scope_note_and_ref("PEM101")[1],
        "curve_target": _build_curve_target_pem101(),
    }


def _build_pilot_division(config: dict, division: str, raw: pd.DataFrame, inventory_source=None,
                          pull_label: str = None) -> dict:
    e1 = config["phase_e1_assumptions"]
    scope = load_division_scope(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)]
    hist, hist_info = latest_vintage_item_history()
    series = {c: (hist[c], hist_info["months"]) for c in codes if c in hist}        # D2: the log vintage's own series and fit window

    fc_all, _vintage = latest_vintage_item_forecasts(FORECAST_HORIZON_MONTHS)

    policy_df = pd.read_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_1_item_policy.csv"))
    detail_df = pd.read_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_2_minmax_stockvalue_twogroup.csv"))

    if inventory_source is not None:
        inv = inventory_source(codes)
    else:
        inv = _persist_and_reload(query_inventory_exact(codes), f"{division}_inventory")
    current_mm = current_minmax_per_item(inv, codes)
    current_mm_by_code = {row["itemcode"]: {"current_min": row["current_total_min"], "current_max": row["current_total_max"],
                                            "has_record": bool(row["n_warehouses"] > 0)}
                          for _, row in current_mm.iterrows()}
    by_wh = _by_warehouse_map(inv)  # task 2b Part 1: same-connection reuse, no extra query

    seg = _load_fulfilment_segmentation(division) if division in FULFILMENT_SEGMENTATION_DIVISIONS else None
    policy_by_code = policy_df.set_index("code")["type"].to_dict()

    items = []
    no_policy = []
    if seg is not None:
        # task 2b Part 2 (METRICS.md Sec.23): item universe is this division's forecast-status
        # items (112 for PEM107), classified stock_policy/confirmed_to_order/conflict, superseding
        # section 15. PEM107's existing forecast/unit_cost pipeline already covers its full
        # division scope (136 codes, confirmed this task), so unlike PEM101 there is no coverage
        # gap here -- every forecast-status item's Min/Max is computable.
        for code, seg_row in seg.iterrows():
            d_row = detail_df[detail_df["code"] == code]
            qty_hist = series[code][0].tolist() if code in series else []
            forecast = fc_all.get(code, np.zeros(FORECAST_HORIZON_MONTHS)).tolist()
            unit_cost = float(d_row["unit_cost"].iloc[0]) if len(d_row) and "unit_cost" in d_row and pd.notna(d_row["unit_cost"].iloc[0]) else None
            no_cost = bool(d_row["no_unit_cost_item"].iloc[0]) if len(d_row) and "no_unit_cost_item" in d_row else (unit_cost is None)
            cm = current_mm_by_code.get(code, {"current_min": None, "current_max": None, "has_record": False})
            items.append({
                "code": code, "type": seg_row["type"] if pd.notna(seg_row.get("type")) else policy_by_code.get(code),
                "policy": seg_row["class"], "class_basis": seg_row["class_basis"],
                "fulfilment_label": seg_row["label"], "S1": bool(seg_row["S1"]) if pd.notna(seg_row["S1"]) else None,
                "S2": (bool(seg_row["S2"]) if pd.notna(seg_row["S2"]) else None), "S2_computable": bool(seg_row["S2_computable"]),
                "S3": bool(seg_row["S3"]) if pd.notna(seg_row["S3"]) else None,
                "min_max_computable": True,
                "actual_history": [round(x, 3) for x in qty_hist],
                "forecast": [round(x, 3) for x in forecast],
                "unit_cost": unit_cost, "unit_cost_fallback": None, "no_unit_cost_item": no_cost,
                "on_hand_sellable": float(d_row["sellable_stock"].iloc[0]) if len(d_row) else 0.0,
                "current_min": cm["current_min"], "current_max": cm["current_max"], "current_has_record": cm["has_record"],
                "by_warehouse": by_wh.get(code, []),
            })
        status_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv"))
        non_forecast = status_df[(status_df["division"] == division) & (status_df["status_category"] != "forecast")]
        no_policy = [{"code": r["itemcode"], "type": policy_by_code.get(r["itemcode"], ""), "policy": r["status_category"]}
                     for _, r in non_forecast.iterrows()]
    else:
        for _, r in policy_df.iterrows():
            code = r["code"]
            if r["policy"] not in ("finished_goods_stock", "component_stock_ato"):
                continue
            d_row = detail_df[detail_df["code"] == code]
            qty_hist = series[code][0].tolist() if code in series else []
            forecast = fc_all.get(code, np.zeros(FORECAST_HORIZON_MONTHS)).tolist()
            unit_cost = float(d_row["unit_cost"].iloc[0]) if len(d_row) and "unit_cost" in d_row and pd.notna(d_row["unit_cost"].iloc[0]) else None
            no_cost = bool(d_row["no_unit_cost_item"].iloc[0]) if len(d_row) and "no_unit_cost_item" in d_row else (unit_cost is None)
            cm = current_mm_by_code.get(code, {"current_min": None, "current_max": None, "has_record": False})
            items.append({
                "code": code, "type": r["type"], "policy": r["policy"],
                "actual_history": [round(x, 3) for x in qty_hist],
                "forecast": [round(x, 3) for x in forecast],
                "unit_cost": unit_cost, "unit_cost_fallback": None, "no_unit_cost_item": no_cost,
                "on_hand_sellable": float(d_row["sellable_stock"].iloc[0]) if len(d_row) else 0.0,
                "current_min": cm["current_min"], "current_max": cm["current_max"], "current_has_record": cm["has_record"],
                "by_warehouse": by_wh.get(code, []),
            })

    logger.info("[%s] Embedded %d items.", division, len(items))
    return {
        "items": items, "no_policy_items": no_policy,
        "sellable_warehouse_codes": e1["sellable_warehouse_codes"][division],
        "segment_policy": {"p50_annual_value_thb": None, "note": "computed per-division, see output/summary/phaseE2pilot_report.md"},
        "snapshot_pull_date": pull_label or (datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (live pull, not a frozen file)"),
        "n_items_label": f"{len(items)} รายการ (ของทั้งหมด {len(codes)}, เฉพาะที่มีนโยบาย)",
        "warehouse_scope_note": warehouse_scope_note_and_ref(division)[0],
        "warehouse_scope_ref": warehouse_scope_note_and_ref(division)[1],
    }


def _pem107_split_label() -> str:
    """Thai month and year of the PEM107 split date, from task2b_part4_pem107_alert.json split_date."""
    with open(os.path.join(SUMMARY_DIR, "task2b_part4_pem107_alert.json"), encoding="utf-8") as f:
        return rv.thai_month_year(json.load(f)["split_date"])


def warehouse_scope_note_and_ref(division: str) -> tuple:
    """(on-screen scope note, facts and references kept for an HTML comment) for one enabled division."""
    if division == "PEM101":
        return ("PEM101 ปรับให้ตรงกับผลจริงแล้วบางส่วน ใช้ส่วนเลือกเป้าการส่งทันด้านล่าง",
                "previous English note: PEM101 128-item Fuse/Surge-Arrester pilot. PARTIALLY CALIBRATED "
                "(80 distinct ensemble members). See STATUS.md whmap_report.md; METRICS.md Sec.22.")
    if division == "PEM103":
        return ("PEM103 ผลิตตามงานประมูล วางแผนแบบผลิตตามสั่ง ตัวเลขในหน้านี้ใช้ดูทิศทางเท่านั้น",
                "previous English note: PEM103 -- E2 scoped pilot, sellable-warehouse list is a business assumption. "
                "PLANNED UNDER G3, NOT G2 (PROJECT_GRAPH.md Q22, business-confirmed): PEM103 is a "
                "transformers/tendering-pipeline business, not a stock-policy division; the Tier A scenario values "
                "are illustrative only. Sources: output/summary/phaseE2_readiness_report.md, phaseE2pilot_report.md.")
    if division == "PEM107":
        return (f"PEM107 ยังไม่ได้ปรับให้ตรงกับผลจริง เพราะระบบเปลี่ยนเมื่อ {_pem107_split_label()} "
                f"และข้อมูลหลังเปลี่ยนยังน้อย ตัวเลขใช้ดูทิศทางเท่านั้น",
                "previous English note: PEM107 -- E2 scoped pilot, sellable-warehouse list is a business assumption. "
                "UNCALIBRATED (Phase J3 found no stock-based policy fits both the 2024-2025 and 2026 periods "
                "simultaneously; METRICS.md Sec.20); the Tier A scenario values are a scenario tool only. "
                "Sources: output/summary/phaseE2_readiness_report.md, phaseE2pilot_report.md.")
    raise ValueError(f"No scope note for division {division}")


def _load_pem107_alert() -> dict:
    with open(os.path.join(SUMMARY_DIR, "task2b_part4_pem107_alert.json"), encoding="utf-8") as f:
        alert = json.load(f)
    items = pd.read_csv(os.path.join(SUMMARY_DIR, "task2b_part4_pem107_alert_items.csv"))
    # BUG FIX (task 2b Part 4/8, found by the Part 8 visual check): pandas re-introduces NaN for
    # items with zero rows in a period (e.g. not_late_from_may_pct when a code has no post-May
    # deliveries at all) even though the source script wrote None -- json.dumps() serializes a
    # bare float NaN as the literal token `NaN`, which is NOT valid JSON and made the WHOLE
    # embedded data block (not just this one field) fail JSON.parse() client-side, silently
    # blanking every number on the page. Converted to None (-> JSON null) here, once, for every
    # column, rather than trusting each column to already be clean.
    items = items.astype(object).where(pd.notna(items), None)
    alert["items"] = items.to_dict("records")
    # References are kept off screen: the limitations lose their DATA_MAP pointer here (it is
    # returned separately for an HTML comment), the source block is only ever shown in a comment.
    ref_pattern = " -- DATA_MAP.md Sec.7 (PEM107 branch):"
    alert["split_label"] = rv.thai_month_year(alert["split_date"])
    # The four English limitation bullets are replaced on screen by Thai wording built from these
    # numbers; the English originals are kept for an HTML comment.
    alert["limitations_english"] = list(alert["limitations"])
    del alert["limitations"]
    return alert


def model_calibrated_at() -> dict:
    """METRICS.md Sec.26 (page_timestamps): when the model was last calibrated and the last month of data it used, from the Max-Min v1
    ensemble's recorded output (run date of the calibration, validation end). "source" is a reference only; the page renders it as an
    HTML comment, never on screen."""
    import maxmin_v1
    dense, _ = maxmin_v1.load_page_inputs()
    return {"run_date": dense["calibrated_on"], "last_month_of_data": dense["last_month_of_data"],
            "source": "output/summary/week1_recal_integrity.json recorded_at and week1_recal_targets.json validation_end -- METRICS.md "
                      "Sec.20 inverse calibration, lead time free, 92 stock_policy items (week 1, 2026-10-05)."}


def apply_class_file_divisions(data: dict, config: dict) -> None:
    """Divisions listed in config inventory_page.class_file_divisions follow METRICS.md Sec.23 (decision of the user, 2026-10-06): every item still carrying the
    older policy (finished_goods_stock, component_stock_ato) takes its class from the item-level file (class_used, label, signals); a placeholder item (no forecast)
    moves to the table of items without a policy. A division left with no stock_policy item gets the approved line for a division without stock items. The
    function does nothing for an item that already carries a class, so it can run on data it has already changed."""
    names = config["inventory_page"].get("class_file_divisions") or []
    if not names:
        return
    path = os.path.join(SUMMARY_DIR, "task2b_part2_item_level.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required source file missing: {path} (needed for the divisions that follow Sec.23).")
    table = pd.read_csv(path)
    for division in names:
        dd = data["divisions"][division]
        sub = table[table["division"] == division].set_index("code")
        forecast = sub[sub["status_category"] == "forecast"]
        no_policy = list(dd.get("no_policy_items") or [])
        known = {r["code"] for r in no_policy}
        items = []
        for it in dd["items"]:
            if it["policy"] not in ("finished_goods_stock", "component_stock_ato"):
                items.append(it)
                continue
            if it["code"] in forecast.index:
                row = forecast.loc[it["code"]]
                s2c = bool(row["S2_computable"])
                it.update({"policy": row["class_used"], "class_basis": "", "fulfilment_label": row["label"], "S1": bool(row["S1"]),
                           "S2": (bool(row["S2"]) if s2c and pd.notna(row["S2"]) else None), "S2_computable": s2c,
                           "S3": bool(row["S3"]), "min_max_computable": True})
                items.append(it)
            elif it["code"] in sub.index and it["code"] not in known:
                no_policy.append({"code": it["code"], "type": it.get("type", ""), "policy": sub.loc[it["code"], "status_category"]})
        total = len(items) + len(no_policy)
        dd["items"], dd["no_policy_items"] = items, no_policy
        dd["n_items_label"] = f"{len(items)} รายการ (ของทั้งหมด {total}, เฉพาะที่มีนโยบาย)"
        if not any(it["policy"] == "stock_policy" for it in items):
            dd["no_min_max_line"] = no_min_max_line(division)
        else:
            dd.pop("no_min_max_line", None)


def apply_reader_text(data: dict) -> dict:
    """Sets every reader-facing text/value that needs no database: disabled-division reasons, scope
    notes, the curve item-set note, the PEM107 alert block, the staleness threshold and the PEM101
    monthly-versus-daily gap. build_data() calls it; tests/test_reader_text.py calls it on the
    tracked page's embedded data so a rebuild without a database still exercises the builder's text."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    data["disabled_divisions"] = disabled_division_reasons()
    data["disabled_division_labels"] = DISABLED_DIVISION_LABELS
    data["model_calibrated_at"] = model_calibrated_at()
    data["staleness_threshold_days"] = rv.staleness_threshold_days(config)
    data["tier_a_ranges"] = config["inventory_page"]["tier_a_ranges"]
    data["service_level_chart_step"] = config["inventory_page"]["service_level_chart_step"]
    data["fulfilment_notice_days"] = rv.fulfilment_notice_threshold_days()
    data["fulfilment_signal_count"] = rv.fulfilment_signal_count()
    apply_class_file_divisions(data, config)
    for division, dd in data["divisions"].items():
        dd["warehouse_scope_note"], dd["warehouse_scope_ref"] = warehouse_scope_note_and_ref(division)
    ct = _build_curve_target_pem101()
    data["divisions"]["PEM101"]["curve_target"] = ct
    data["pem107_alert"] = _load_pem107_alert()
    data["forecast_round_label"] = rv.thai_month_short(rv.vintage_facts()["run_date"])        # the round of the vintage the page uses (shared formatter)
    # Gap between this page's monthly-prorated stock value and the recorded daily-window figure,
    # PEM101, default scenario (src/reader_values.py::pipeline_gap_pct).
    data["pipeline_gap_pct"] = rv.pipeline_gap_pct(data["divisions"]["PEM101"], data["tier_a_defaults"],
                                                     data["days_per_month"])
    return data


def build_data(inventory_source=None, sales_source=None, pull_labels: dict = None, stock_pulled_at: str = None,
               stock_meta: dict = None) -> dict:
    """Builds the page's embedded data. By default it pulls live (one connection attempt each for
    stock and for PEM103/PEM107 sales). The optional arguments let a caller supply already-pulled
    data instead, with no database access: inventory_source(codes, allow_empty=False) -> stock rows,
    sales_source(codes) -> raw sales rows, pull_labels {division: 'data pulled at' text}, stock_pulled_at
    (the stock section's own pull time, shown as its data-pulled time)
    (src/inventory_page_sources.py provides them from saved snapshots or from the monthly runner's pull)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    e1 = config["phase_e1_assumptions"]
    e1_page = config["inventory_page"]

    divisions = {"PEM101": _build_pem101_division(config, inventory_source)}

    pilot_codes = []
    for division in ["PEM103", "PEM107"]:
        scope = load_division_scope(config, division)
        pilot_codes.extend(scope["code"].tolist())
    if sales_source is not None:
        raw = sales_source(sorted(set(pilot_codes)))
    else:
        raw = _persist_and_reload(pull_raw_sales(config, sorted(set(pilot_codes))), "PEM103_PEM107_sales")
    for division in ["PEM103", "PEM107"]:
        divisions[division] = _build_pilot_division(config, division, raw, inventory_source,
                                                     (pull_labels or {}).get(division))

    data = {
        "focus_items": ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"],
        "days_per_month": 30.44,
        "forecast_horizon_months": FORECAST_HORIZON_MONTHS,
        "forecast_vintage": latest_vintage_item_forecasts(FORECAST_HORIZON_MONTHS)[1],
        # METRICS.md Sec.26 (page_timestamps), added 2026-09-25 (task 2a, Part 2 -- ONLY these two
        # fields touched on this page this task; Min/Max logic, segmentation, PEM107 alert etc.
        # are explicitly out of scope, per task instruction, for a separate task 2b).
        "page_built_at": datetime.now().strftime("%Y-%m-%d %H:%M") + " ICT (UTC+7) -- this build run's own clock",
        "model_calibrated_at": model_calibrated_at(),
        "division_order": PILOT_DIVISIONS,
        "default_division": "PEM101",
        "disabled_divisions": {}, "disabled_division_labels": {},
        "tier_a_defaults": {
            "procurement_lead_time_days": e1["procurement_lead_time_days_default"],
            "assembly_time_days": e1["assembly_time_days_default"],
            "review_interval_days": e1["review_interval_days_default"],
            "cycle_service_level": e1["default_scenario"]["cycle_service_level"],
            "holding_cost_rate_annual": e1["holding_cost_rate_annual"],
            "obsolescence_threshold_months": e1["obsolescence_threshold_months"],
        },
        "tier_a_ranges": e1_page["tier_a_ranges"],
        "service_level_chart_step": e1_page["service_level_chart_step"],
        "divisions": divisions,
        # task 2b Part 4: PEM107 delivery-decline alert, precomputed by
        # src/investigations/task2b_part4_pem107_alert.py (Cube_CES, no live DB access from this
        # builder itself -- reads that script's already-written JSON).
        "pem107_alert": {},
    }
    apply_reader_text(data)
    if stock_pulled_at:
        for dd in data["divisions"].values():
            dd["stock_pulled_at"] = stock_pulled_at
        data["stock_meta"] = stock_meta or {}
    logger.info("Built multi-division data: %s", {k: len(v["items"]) for k, v in divisions.items()})
    return data


if __name__ == "__main__":
    d = build_data()
    print(json.dumps({div: len(v["items"]) for div, v in d["divisions"].items()}))
