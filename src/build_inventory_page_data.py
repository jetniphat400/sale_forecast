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
from phaseE2_pilot_recompute import load_division_scope, pull_raw_sales, build_monthly_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_inventory_page_data")

FORECAST_HORIZON_MONTHS = 10
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
PILOT_DIVISIONS = ["PEM101", "PEM103", "PEM107"]
DISABLED_DIVISIONS = {
    "CI101": "6 of 13 items ever have any on-hand stock (46.2%); the tiny amount that exists "
             "co-locates in PEM101's own FG01, not a CI101-specific location -- too thin a base "
             "for an independent sellable-warehouse set (output/summary/phaseE2_readiness_report.md).",
    "PEM102": "Only 3 of 26 items ever have any on-hand stock (11.5%), 3 units total -- far too "
              "few to establish a confident sellable-warehouse set.",
    "PEM104": "Made to order by business model -- no stock policy applicable (DATA_MAP.md Sec.7, "
              "PROJECT_GRAPH.md dead end DE4, business-confirmed 2026-09-23). Consistent with the "
              "data: only 1 of 12 items ever has any on-hand stock (8.3%), 1 unit total.",
}


def _build_curve_target_pem101() -> dict:
    """METRICS.md Sec.22 selectable not_late target data for PEM101, added 2026-09-24 (Phase 23,
    Part 5) -- reads the already-computed dense grid (output/summary/phase23_dense_grid_PEM101.json,
    built by src/investigations/phase23_page_precompute.py from the Modeler's locked-config curve),
    no database access. Supersedes the prior robust/sensitive table (every item returned the same
    range_ratio, carrying no item-level information -- see output/summary/phase23_modeler_report.md).
    """
    with open(os.path.join(SUMMARY_DIR, "phase23_dense_grid_PEM101.json"), encoding="utf-8") as f:
        return json.load(f)


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

    items = []
    for _, r in policy_df.iterrows():
        code = r["code"]
        if r["policy"] not in ("finished_goods_stock", "component_stock_ato"):
            continue
        uc_row = unit_cost_df[unit_cost_df["itemcode"] == code]
        oh_row = inv_summary[inv_summary["code"] == code]
        qty_hist = series[code][0].tolist() if code in series else []
        forecast = fc_all.get(code, np.zeros(FORECAST_HORIZON_MONTHS)).tolist()
        items.append({
            "code": code, "type": r["type"], "policy": r["policy"],
            "actual_history": [round(x, 3) for x in qty_hist],
            "forecast": [round(x, 3) for x in forecast],
            "unit_cost": float(uc_row["unit_cost"].iloc[0]) if len(uc_row) and pd.notna(uc_row["unit_cost"].iloc[0]) else None,
            "unit_cost_fallback": bool(uc_row["unit_cost_fallback"].iloc[0]) if len(uc_row) else None,
            "no_unit_cost_item": bool(uc_row["no_unit_cost_item"].iloc[0]) if len(uc_row) else True,
            "on_hand_sellable": float(oh_row["sellable_stock"].iloc[0]) if len(oh_row) else 0.0,
        })

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

    no_policy = policy_df[policy_df["policy"].isin(["placeholder", "excluded"])][["code", "type", "policy"]].to_dict("records")

    return {
        "items": items, "no_policy_items": no_policy,
        "sellable_warehouse_codes": e1["sellable_warehouse_codes"]["PEM101"],
        "segment_policy": sp,
        "snapshot_pull_date": series_bundle["pull_date"],
        "n_items_label": f"{len(items)} รายการ",
        "warehouse_scope_note": "PEM101 128-item Fuse/Surge-Arrester pilot -- see STATUS.md whmap_report.md. "
                                 "PARTIALLY CALIBRATED (METRICS.md Sec.22, 80 distinct ensemble members -- "
                                 "see the Trade-off Curve Target section below).",
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

    inv = query_inventory_exact(codes)
    current_mm = current_minmax_per_item(inv, codes)
    current_mm_by_code = {row["itemcode"]: {"current_min": row["current_total_min"], "current_max": row["current_total_max"]}
                          for _, row in current_mm.iterrows()}

    items = []
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
        })

    logger.info("[%s] Embedded %d finished_goods_stock/component_stock_ato items.", division, len(items))
    return {
        "items": items, "no_policy_items": [],
        "sellable_warehouse_codes": e1["sellable_warehouse_codes"][division],
        "segment_policy": {"p50_annual_value_thb": None, "note": "computed per-division, see output/summary/phaseE2pilot_report.md"},
        "snapshot_pull_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (live pull, not a frozen file)",
        "n_items_label": f"{len(items)} รายการ (ของทั้งหมด {len(codes)}, เฉพาะที่มีนโยบาย)",
        "warehouse_scope_note": f"{division} -- E2 scoped pilot, sellable-warehouse list is a business assumption "
                                 f"(output/summary/phaseE2_readiness_report.md, phaseE2pilot_report.md). "
                                 + _division_calibration_note(division),
    }


def _division_calibration_note(division: str) -> str:
    """Sec.22 (2026-09-24): per-division calibration/planning status shown in the page's scope
    note, so a reader never mistakes this page's scenario values for a calibrated recommendation
    outside PEM101's own Robust Ensemble section. Cited: PROJECT_GRAPH.md Q10/Q22/Q23 nodes."""
    if division == "PEM103":
        return ("PLANNED UNDER G3, NOT G2 (PROJECT_GRAPH.md Q22, business-confirmed 2026-09-23): "
                "PEM103 is a transformers/tendering-pipeline business, not a stock-policy division -- "
                "the Tier A scenario values on this page are illustrative only, not a basis for "
                "planning PEM103.")
    if division == "PEM107":
        return ("UNCALIBRATED (METRICS.md Sec.20; Phase J3 found no stock-based policy fits both "
                "the 2024-2025 and 2026 periods simultaneously) -- the Tier A scenario values on "
                "this page are a scenario tool only, not a calibrated policy.")
    return ""


def build_data() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    e1 = config["phase_e1_assumptions"]

    divisions = {"PEM101": _build_pem101_division(config)}

    pilot_codes = []
    for division in ["PEM103", "PEM107"]:
        scope = load_division_scope(config, division)
        pilot_codes.extend(scope["code"].tolist())
    raw = pull_raw_sales(config, sorted(set(pilot_codes)))
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
        "model_calibrated_at": {
            "run_date": "2026-09-23",
            "last_month_of_data": "2026-07",
            "source": "output/summary/phaseJ3_report.md header ('Date: 2026-09-23') and Part 1 "
                       "('Phase J bounds by ForecastDelDate in [2024-01, 2026-07]') -- METRICS.md "
                       "Sec.20 inverse calibration, Phase J3.",
        },
        "division_order": PILOT_DIVISIONS,
        "default_division": "PEM101",
        "disabled_divisions": DISABLED_DIVISIONS,
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
    }
    logger.info("Built multi-division data: %s", {k: len(v["items"]) for k, v in divisions.items()})
    return data


if __name__ == "__main__":
    d = build_data()
    print(json.dumps({div: len(v["items"]) for div, v in d["divisions"].items()}))
