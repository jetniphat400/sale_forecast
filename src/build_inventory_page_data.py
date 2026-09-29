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


def disabled_division_reasons() -> dict:
    n_ci, t_ci = _stocked_item_counts("CI101")
    n_102, t_102 = _stocked_item_counts("PEM102")
    return {
        "CI101": f"ยังไม่เปิด มีของในคลังแค่ {n_ci} จาก {t_ci} รหัส และอยู่ในคลังเดียวกับ PEM101 ยังกำหนดคลังของฝ่ายนี้ไม่ได้",
        "PEM102": f"ยังไม่เปิด มีของในคลังแค่ {n_102} จาก {t_102} รหัส น้อยเกินกว่าจะกำหนดคลังได้",
        "PEM104": "ไม่มีนโยบาย stock ฝ่ายนี้ผลิตตามสั่งทั้งหมด",
    }


FULFILMENT_SEGMENTATION_DIVISIONS = ["PEM101", "PEM107"]  # task 2b Part 2 scope; PEM103 unaffected


def _load_fulfilment_segmentation(division: str) -> pd.DataFrame:
    """METRICS.md Sec.23, computed by src/investigations/task2b_part2_fulfilment_segmentation.py
    (task 2b Part 2) -- supersedes section 15 for G2 item eligibility on PEM101/PEM107. Returns one
    row per FORECAST-STATUS item (144 PEM101 / 112 PEM107 -- the full universe, wider than the
    128/136-item pilot scopes the pre-existing forecast/unit_cost pipeline covers)."""
    path = os.path.join(SUMMARY_DIR, "task2b_part2_item_level.csv")
    df = pd.read_csv(path)
    return df[df["division"] == division].set_index("code")


def _build_curve_target_pem101() -> dict:
    """METRICS.md Sec.22 selectable not_late target data for PEM101, added 2026-09-24 (Phase 23,
    Part 5) -- reads the already-computed dense grid (output/summary/phase23_dense_grid_PEM101.json,
    built by src/investigations/phase23_page_precompute.py from the Modeler's locked-config curve),
    no database access. Supersedes the prior robust/sensitive table (every item returned the same
    range_ratio, carrying no item-level information -- see output/summary/phase23_modeler_report.md).
    """
    with open(os.path.join(SUMMARY_DIR, "phase23_dense_grid_PEM101.json"), encoding="utf-8") as f:
        data = json.load(f)
    # task 2b Part 3 (METRICS.md Sec.24): relative_service_cost ratio grid, computed by
    # src/investigations/task2b_part3_relative_service_cost.py from the SAME 80-member curve
    # points as the section-22 curve above, no database access.
    with open(os.path.join(SUMMARY_DIR, "task2b_part3_ratio_grid_PEM101.json"), encoding="utf-8") as f:
        data["relative_service_cost"] = json.load(f)
    # task 2b Part 2 (METRICS.md Sec.23): this curve/ensemble was built (Phase 22/23, 2026-09-24)
    # on the pre-Sec.23 finished_goods_stock item set, before Sec.23 changed which items are
    # Min/Max-eligible. Not recalibrated on the new stock_policy set this task (explicit scope
    # decision, STATUS.md/PROJECT_GRAPH.md G2) -- labelled here so the page states its own scope,
    # not just the documentation.
    policy_counts = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_item_policy.csv"))["policy"].value_counts()
    n_calibrated_on = int(policy_counts.get("finished_goods_stock", 0))
    seg_counts = _load_fulfilment_segmentation("PEM101")["class"].value_counts()
    n_current_set = int(seg_counts.get("stock_policy", 0))
    # Restored as written (pending Thai wording): removing the internal names and section numbers
    # would leave the sentence meaningless, so it stays whole and is listed for rewriting.
    data["item_set_note"] = (
        f"Calibrated on the pre-Sec.23 finished_goods_stock item set ({n_calibrated_on} items, "
        f"section 15 criterion). NOT recalibrated on the current Sec.23 stock_policy item set "
        f"({n_current_set} items) this task -- recalibrating on the new set is scheduled follow-up "
        f"work, not yet done (DATA_MAP.md 'Task 2b' entries, PROJECT_GRAPH.md node G2)."
    )
    return data


def _build_pem101_division(config: dict) -> dict:
    e1 = config["phase_e1_assumptions"]
    sp = config["segment_policy"]
    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    series = series_bundle["series"]

    policy_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_item_policy.csv"))
    unit_cost_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_unit_cost.csv"))
    inv_summary = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_stock_value_inputs.csv"))

    fc_all = topdown_item_forecast(scope, series, fit_end=len(next(iter(series.values()))[0]),
                                    horizon=FORECAST_HORIZON_MONTHS)

    # Task 2b Part 2 (METRICS.md Sec.23): item universe is now every PEM101 FORECAST-STATUS item
    # (144), classified stock_policy/confirmed_to_order/conflict -- superseding section 15's
    # finished_goods_stock/component_stock_ato policy for WHICH items get a Min/Max. The
    # pre-existing forecast/unit_cost pipeline (policy_df/unit_cost_df/inv_summary/series) still
    # only covers the older 128-item Fuse/Surge-Arrester pilot (PROJECT_GRAPH.md D3) -- 10 of the
    # 82 stock_policy items fall outside it and get min_max_computable=False rather than a
    # fabricated number (AGENTS.md rule 1/3: never guess, report the gap).
    seg = _load_fulfilment_segmentation("PEM101")
    codes_for_inv = list(seg.index)
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
        forecast = fc_all.get(code, np.zeros(FORECAST_HORIZON_MONTHS)).tolist() if code in series else []
        items.append({
            "code": code, "type": seg_row["type"] if pd.notna(seg_row.get("type")) else policy_by_code.get(code),
            "policy": fulfilment_class,
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


def _build_pilot_division(config: dict, division: str, raw: pd.DataFrame) -> dict:
    e1 = config["phase_e1_assumptions"]
    scope = load_division_scope(config, division)
    codes = sorted(scope["code"].unique())
    raw_div = raw[raw["itemcode"].isin(codes)]
    series_bundle = build_monthly_series(raw_div, codes)
    series = series_bundle["series"]

    fc_all = topdown_item_forecast(scope, series, fit_end=len(next(iter(series.values()))[0]),
                                    horizon=FORECAST_HORIZON_MONTHS)

    policy_df = pd.read_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_1_item_policy.csv"))
    detail_df = pd.read_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_2_minmax_stockvalue_twogroup.csv"))

    inv = _persist_and_reload(query_inventory_exact(codes), f"{division}_inventory")
    current_mm = current_minmax_per_item(inv, codes)
    current_mm_by_code = {row["itemcode"]: {"current_min": row["current_total_min"], "current_max": row["current_total_max"]}
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
            cm = current_mm_by_code.get(code, {"current_min": None, "current_max": None})
            items.append({
                "code": code, "type": seg_row["type"] if pd.notna(seg_row.get("type")) else policy_by_code.get(code),
                "policy": seg_row["class"],
                "fulfilment_label": seg_row["label"], "S1": bool(seg_row["S1"]) if pd.notna(seg_row["S1"]) else None,
                "S2": (bool(seg_row["S2"]) if pd.notna(seg_row["S2"]) else None), "S2_computable": bool(seg_row["S2_computable"]),
                "S3": bool(seg_row["S3"]) if pd.notna(seg_row["S3"]) else None,
                "min_max_computable": True,
                "actual_history": [round(x, 3) for x in qty_hist],
                "forecast": [round(x, 3) for x in forecast],
                "unit_cost": unit_cost, "unit_cost_fallback": None, "no_unit_cost_item": no_cost,
                "on_hand_sellable": float(d_row["sellable_stock"].iloc[0]) if len(d_row) else 0.0,
                "current_min": cm["current_min"], "current_max": cm["current_max"],
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
            cm = current_mm_by_code.get(code, {"current_min": None, "current_max": None})
            items.append({
                "code": code, "type": r["type"], "policy": r["policy"],
                "actual_history": [round(x, 3) for x in qty_hist],
                "forecast": [round(x, 3) for x in forecast],
                "unit_cost": unit_cost, "unit_cost_fallback": None, "no_unit_cost_item": no_cost,
                "on_hand_sellable": float(d_row["sellable_stock"].iloc[0]) if len(d_row) else 0.0,
                "current_min": cm["current_min"], "current_max": cm["current_max"],
                "by_warehouse": by_wh.get(code, []),
            })

    logger.info("[%s] Embedded %d items.", division, len(items))
    return {
        "items": items, "no_policy_items": no_policy,
        "sellable_warehouse_codes": e1["sellable_warehouse_codes"][division],
        "segment_policy": {"p50_annual_value_thb": None, "note": "computed per-division, see output/summary/phaseE2pilot_report.md"},
        "snapshot_pull_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (live pull, not a frozen file)",
        "n_items_label": f"{len(items)} รายการ (ของทั้งหมด {len(codes)}, เฉพาะที่มีนโยบาย)",
        "warehouse_scope_note": warehouse_scope_note_and_ref(division)[0],
        "warehouse_scope_ref": warehouse_scope_note_and_ref(division)[1],
    }


def warehouse_scope_note_and_ref(division: str) -> tuple:
    """(on-screen scope note, references kept for an HTML comment) for one enabled division."""
    if division == "PEM101":
        return ("PEM101 128-item Fuse/Surge-Arrester pilot. PARTIALLY CALIBRATED (80 distinct ensemble members).",
                "see STATUS.md whmap_report.md; METRICS.md Sec.22; the Trade-off Curve Target section below")
    return (f"{division} -- E2 scoped pilot, sellable-warehouse list is a business assumption. "
            + _division_calibration_note(division),
            "output/summary/phaseE2_readiness_report.md, phaseE2pilot_report.md; "
            + _division_calibration_ref(division))


def _division_calibration_note(division: str) -> str:
    """Sec.22 (2026-09-24): per-division calibration/planning status shown in the page's scope
    note, so a reader never mistakes this page's scenario values for a calibrated recommendation
    outside PEM101's own Robust Ensemble section. Cited: PROJECT_GRAPH.md Q10/Q22/Q23 nodes."""
    if division == "PEM103":
        return ("PLANNED UNDER G3, NOT G2: "
                "PEM103 is a transformers/tendering-pipeline business, not a stock-policy division -- "
                "the Tier A scenario values on this page are illustrative only, not a basis for "
                "planning PEM103.")
    if division == "PEM107":
        return ("UNCALIBRATED (Phase J3 found no stock-based policy fits both "
                "the 2024-2025 and 2026 periods simultaneously) -- the Tier A scenario values on "
                "this page are a scenario tool only, not a calibrated policy.")
    return ""


def _division_calibration_ref(division: str) -> str:
    """References removed from _division_calibration_note's on-screen text, kept for an HTML comment."""
    if division == "PEM103":
        return "PROJECT_GRAPH.md Q22, business-confirmed 2026-09-23"
    if division == "PEM107":
        return "METRICS.md Sec.20"
    return ""


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
    alert["limitations_refs"] = [ref_pattern.strip(" -:") for x in alert["limitations"] if ref_pattern in x]
    alert["limitations"] = [x.replace(ref_pattern, ":") for x in alert["limitations"]]
    return alert


# METRICS.md Sec.26 (page_timestamps): when the model was last calibrated. "source" is a reference
# only; the page renders it as an HTML comment, never on screen.
MODEL_CALIBRATED_AT = {
    "run_date": "2026-09-23",
    "last_month_of_data": "2026-07",
    "source": "output/summary/phaseJ3_report.md header ('Date: 2026-09-23') and Part 1 "
               "('Phase J bounds by ForecastDelDate in [2024-01, 2026-07]') -- METRICS.md "
               "Sec.20 inverse calibration, Phase J3.",
}


def build_data() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    e1 = config["phase_e1_assumptions"]

    divisions = {"PEM101": _build_pem101_division(config)}

    pilot_codes = []
    for division in ["PEM103", "PEM107"]:
        scope = load_division_scope(config, division)
        pilot_codes.extend(scope["code"].tolist())
    raw = _persist_and_reload(pull_raw_sales(config, sorted(set(pilot_codes))), "PEM103_PEM107_sales")
    for division in ["PEM103", "PEM107"]:
        divisions[division] = _build_pilot_division(config, division, raw)

    data = {
        "focus_items": ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"],
        "days_per_month": 30.44,
        "forecast_horizon_months": FORECAST_HORIZON_MONTHS,
        # METRICS.md Sec.26 (page_timestamps), added 2026-09-25 (task 2a, Part 2 -- ONLY these two
        # fields touched on this page this task; Min/Max logic, segmentation, PEM107 alert etc.
        # are explicitly out of scope, per task instruction, for a separate task 2b).
        "page_built_at": datetime.now().strftime("%Y-%m-%d %H:%M") + " ICT (UTC+7) -- this build run's own clock",
        "model_calibrated_at": MODEL_CALIBRATED_AT,
        "division_order": PILOT_DIVISIONS,
        "default_division": "PEM101",
        "disabled_divisions": disabled_division_reasons(),
        "disabled_division_labels": DISABLED_DIVISION_LABELS,
        "tier_a_defaults": {
            "procurement_lead_time_days": e1["procurement_lead_time_days_default"],
            "assembly_time_days": e1["assembly_time_days_default"],
            "review_interval_days": e1["review_interval_days_default"],
            "cycle_service_level": e1["default_scenario"]["cycle_service_level"],
            "holding_cost_rate_annual": e1["holding_cost_rate_annual"],
            "obsolescence_threshold_months": e1["obsolescence_threshold_months"],
        },
        "tier_a_ranges": {
            "procurement_lead_time_days": [30, 90], "assembly_time_days": [0, 20],
            "review_interval_days": [7, 90], "cycle_service_level": [0.80, 0.99],
            "holding_cost_rate_annual": [0.05, 0.40], "obsolescence_threshold_months": [1, 12],
        },
        "divisions": divisions,
        # task 2b Part 4: PEM107 delivery-decline alert, precomputed by
        # src/investigations/task2b_part4_pem107_alert.py (Cube_CES, no live DB access from this
        # builder itself -- reads that script's already-written JSON).
        "pem107_alert": _load_pem107_alert(),
    }
    logger.info("Built multi-division data: %s", {k: len(v["items"]) for k, v in divisions.items()})
    return data


if __name__ == "__main__":
    d = build_data()
    print(json.dumps({div: len(v["items"]) for div, v in d["divisions"].items()}))
