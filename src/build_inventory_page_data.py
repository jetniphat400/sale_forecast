"""Builds the embedded JSON data block for forecast/inventory.html.

Embeds, per PEM101 finished_goods_stock / component_stock_ato item: the raw 31-month actual
history and a 10-month Top-down forecast (fit on all 31 months, the same leakage-free pattern
verified in Phase E0.1), unit_cost, on_hand_sellable, current_min_max, and policy. The 10-month
forecast horizon is generous enough to cover every Tier A slider's max range (procurement up to
90d + assembly up to 20d + review up to 90d = 200d = 6.6 months) with headroom.

The page's client-side JS recomputes Min/Max/stock_value/months_of_cover/holding_cost from this
embedded RAW data whenever a Tier A control changes -- it never re-derives a number from a
different source than this embedded block (tests/test_inventory_page.py checks this).
"""
import json
import logging
import math
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phaseE1_common import PROJECT_ROOT, SUMMARY_DIR, load_config, load_scope, load_monthly_series, topdown_item_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_inventory_page_data")

FORECAST_HORIZON_MONTHS = 10
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")


def build_data() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    e1 = config["phase_e1_assumptions"]
    sp = config["segment_policy"]

    scope = load_scope(config)
    series_bundle = load_monthly_series(scope)
    series = series_bundle["series"]

    policy_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_item_policy.csv"))
    unit_cost_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_unit_cost.csv"))
    moc_df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_months_of_cover.csv"))

    inv_summary = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_stock_value_inputs.csv"))

    fc_all = topdown_item_forecast(scope, series, fit_end=len(next(iter(series.values()))[0]),
                                    horizon=FORECAST_HORIZON_MONTHS)

    items = []
    for _, r in policy_df.iterrows():
        code = r["code"]
        if r["policy"] not in ("finished_goods_stock", "component_stock_ato"):
            continue
        uc_row = unit_cost_df[unit_cost_df["itemcode"] == code]
        moc_row = moc_df[moc_df["code"] == code]
        oh_row = inv_summary[inv_summary["code"] == code]
        qty_hist = series[code][0].tolist() if code in series else []
        forecast = fc_all.get(code, np.zeros(FORECAST_HORIZON_MONTHS)).tolist()
        items.append({
            "code": code,
            "type": r["type"],
            "policy": r["policy"],
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

    data = {
        "focus_items": ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"],
        "days_per_month": 30.44,
        "forecast_horizon_months": FORECAST_HORIZON_MONTHS,
        "tier_a_defaults": {
            "procurement_lead_time_days": e1["procurement_lead_time_days_default"],
            "assembly_time_days": e1["assembly_time_days_default"],
            "review_interval_days": e1["review_interval_days_default"],
            "cycle_service_level": e1["default_scenario"]["cycle_service_level"],
            "holding_cost_rate_annual": e1["holding_cost_rate_annual"],
            "obsolescence_threshold_months": e1["obsolescence_threshold_months"],
            "sellable_warehouse_codes": e1["sellable_warehouse_codes"],
        },
        "tier_a_ranges": {
            "procurement_lead_time_days": [30, 90], "assembly_time_days": [0, 20],
            "review_interval_days": [7, 90], "cycle_service_level": [0.80, 0.99],
            "holding_cost_rate_annual": [0.05, 0.40], "obsolescence_threshold_months": [1, 12],
        },
        "segment_policy": sp,
        "items": items,
        "no_policy_items": no_policy,
        "snapshot_pull_date": series_bundle["pull_date"],
        "warehouse_scope_note": "PEM101 only -- other divisions await a verified warehouse/sellability mapping (STATUS.md whmap_report.md covers PEM101 alone at moderate-to-high confidence)."
    }
    logger.info("Embedded %d finished_goods_stock/component_stock_ato items, %d no-policy items.",
                len(items), len(no_policy))
    return data


if __name__ == "__main__":
    d = build_data()
    print(json.dumps({"n_items": len(d["items"]), "n_no_policy": len(d["no_policy_items"])}))
