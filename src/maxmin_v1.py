"""Max-Min v1 for PEM101 (week 1; decision D2 of 2026-10-05; METRICS.md Sec.5, 20, 22).

Min and Max use the lead time the calibration supports: the ensemble fitted with lead time free on the 92 stock_policy items (the control run
of src/investigations/week1_recalibration.py). The per-item material lead time (METRICS.md Sec.5, item lead time version 1) is shown beside
each item and kept for the week 3 material plan; it is not used for Min and Max.

This module
  * verifies the control run's recorded files against their SHA-256 (`week1_recal_integrity.json`) before anything is read from them;
  * summarises the ensemble (distinct members, lead range, today's point, trade-off to 99 percent);
  * builds the page's inputs from those files, with no database and no new simulation of the calibration (`build_page_inputs`: the dense
    grid of per-item Min and Max over the trade-off curve, and the relative-service-cost ratio grid), recorded with a SHA-256;
  * reads the per-item material lead time with its hash check (`material_lead_table`);
  * builds data/assumptions.json (`build_assumptions`), the in-use assumptions the index.html tab reads at runtime.

Every number is computed from recorded outputs or config; config block `maxmin_v1` names the files.
"""
import hashlib
import json
import logging
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DAYS_PER_MONTH = 30.44            # phase23_page_precompute.DAYS_PER_MONTH (METRICS.md Sec.5 and 16)
ASSUMPTIONS_FIELDS = ["id", "topic", "unknown", "used_now", "affects", "value_source", "updated_date"]
ASSUMPTIONS_SCHEMA_VERSION = 2
logger = logging.getLogger("maxmin_v1")


class MaxMinV1Error(Exception):
    """A recorded output is missing, does not hash to its recorded value, or does not hold what the build needs; the build stops."""


# ------------------------------------------------------------------ config and integrity
def load_full_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config() -> dict:
    return load_full_config()["maxmin_v1"]


def path_of(rel: str) -> str:
    return os.path.join(PROJECT_ROOT, *rel.split("/"))


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def verify_files(integrity_path: str, only: list = None) -> dict:
    """Checks the files listed in an integrity JSON ({"files": {name: {"sha256": ...}}}, names relative to the JSON's own folder) against
    their recorded SHA-256. `only` limits the check to those names (each must be listed). Raises MaxMinV1Error on a missing file, an
    unlisted name or a hash that differs; returns the integrity record."""
    if not os.path.exists(integrity_path):
        raise MaxMinV1Error(f"integrity file missing: {integrity_path}")
    with open(integrity_path, encoding="utf-8") as f:
        meta = json.load(f)
    folder = os.path.dirname(integrity_path)
    names = only if only is not None else list(meta["files"])
    for name in names:
        if name not in meta["files"]:
            raise MaxMinV1Error(f"{name} is not listed in {os.path.basename(integrity_path)}")
        p = os.path.join(folder, name)
        if not os.path.exists(p):
            raise MaxMinV1Error(f"recorded output missing: {p}")
        if sha256_file(p) != meta["files"][name]["sha256"]:
            raise MaxMinV1Error(f"{name} does not hash to the value recorded in {os.path.basename(integrity_path)}")
    return meta


def verify_ensemble_files(cfg: dict = None) -> dict:
    """The control run's files this module reads, against week1_recal_integrity.json."""
    cfg = cfg or load_config()
    names = [os.path.basename(cfg[k]) for k in ("ensemble_members_file", "ensemble_tradeoff_points_file",
                                                  "ensemble_tradeoff_envelope_file", "ensemble_targets_file")]
    return verify_files(path_of(cfg["ensemble_integrity_file"]), only=names)


# ------------------------------------------------------------------ the ensemble
def ensemble_summary(cfg: dict = None) -> dict:
    """Distinct members, lead range, today's point and the trade-off to 99 percent of the lead-time-free ensemble on the 92 items.

    * n_members, lead_min, lead_max, lead_median: the distinct members (deduplicated on reorder level, order-up-to level, review interval
      and replenishment lead time, METRICS.md Sec.22) of the control run.
    * observed: unit-weighted not_late (validation window) and current stock value of the 92 items (the targets the calibration matched).
    * simulated_today: the members' median simulated validation point.
    * tradeoff_to_99: the trade-off envelope (min, median, max stock value per not_late bin over the members): the 99 percent bin against
      the 98 percent bin, as week1_leadtime_calibration.md states it (median ratio, and the ratio of the minima and of the maxima).
    """
    cfg = cfg or load_config()
    integrity = verify_ensemble_files(cfg)
    members = pd.read_csv(path_of(cfg["ensemble_members_file"]))
    with open(path_of(cfg["ensemble_targets_file"]), encoding="utf-8") as f:
        targets = json.load(f)
    env = pd.read_csv(path_of(cfg["ensemble_tradeoff_envelope_file"])).set_index("not_late_bin_pct")
    if len(members) == 0:
        raise MaxMinV1Error("the control run has no distinct members")
    if int(targets["control_distinct_members"]) != len(members):
        raise MaxMinV1Error("the targets file and the members file disagree on the number of distinct members")
    lo, hi = env.loc[98.0], env.loc[99.0]
    return {
        "n_members": int(len(members)),
        "n_items": int(targets["n_items"]),
        "lead_min": int(members["lead_time_days"].min()), "lead_max": int(members["lead_time_days"].max()),
        "lead_median": float(members["lead_time_days"].median()),
        "observed": {"not_late_pct": round(100 * targets["not_late_validation"]["not_late"], 2),
                     "stock_value_thb": round(targets["stock_value_current_by_definition"]["current"], 2)},
        "simulated_today": {"not_late_pct": 100 * float(members["valid_not_late"].median()),
                            "stock_value_thb": float(members["valid_stock_value"].median())},
        "tradeoff_to_99": {"median_pct": 100 * (hi["median"] / lo["median"] - 1), "min_pct": 100 * (hi["min"] / lo["min"] - 1),
                           "max_pct": 100 * (hi["max"] / lo["max"] - 1), "stock_at_98_median": float(lo["median"]),
                           "stock_at_99_median": float(hi["median"])},
        "validation_end": str(targets["validation_end"]),
        "calibrated_on": str(integrity["recorded_at"])[:10],
        "n_item_matched_unit_cost": int(targets["n_items_with_unit_cost"]),
    }


# ------------------------------------------------------------------ the page's inputs
def _interp_presets(dense_grid: list, today_not_late_pct: float, today_stock_thb: float) -> dict:
    """The three presets of phase23_page_precompute.py, same method, on the new median curve."""
    r_arr = np.array([g["r"] for g in dense_grid])
    nl_arr = np.array([g["not_late_median_pct"] for g in dense_grid])
    sv_arr = np.array([g["stock_value_median"] for g in dense_grid])
    if not (np.all(np.diff(nl_arr) > 0) and np.all(np.diff(sv_arr) > 0)):
        raise MaxMinV1Error("the median curve is not strictly increasing in the reorder level, so the presets cannot be interpolated")
    r1 = float(np.interp(today_not_late_pct, nl_arr, r_arr))
    r2 = float(np.interp(today_stock_thb, sv_arr, r_arr))
    max_nl = float(nl_arr.max())
    p1 = {"not_late_pct": round(today_not_late_pct, 3), "r": round(r1, 4),
          "stock_value_median": round(float(np.interp(r1, r_arr, sv_arr)), 2),
          "label": f"Today's not_late ({today_not_late_pct:.2f}%) at the lowest median stock value"}
    p2 = {"not_late_pct": round(float(np.interp(r2, r_arr, nl_arr)), 3), "r": round(r2, 4),
          "stock_value_median": round(today_stock_thb, 2), "label": "Highest not_late the median curve reaches at today's stock value"}
    if max_nl >= 99.0:
        r3 = float(np.interp(99.0, nl_arr, r_arr))
        p3 = {"not_late_pct": 99.0, "r": round(r3, 4), "stock_value_median": round(float(np.interp(r3, r_arr, sv_arr)), 2),
              "capped": False, "label": "Stretch target: 99% not_late"}
    else:
        p3 = {"not_late_pct": round(max_nl, 3), "r": round(float(r_arr[-1]), 4), "stock_value_median": round(float(sv_arr[-1]), 2),
              "capped": True, "label": f"Stretch target: curve's highest point ({max_nl:.2f}%, 99% not reached)"}
    return {"today_lowest_stock": p1, "highest_at_today_stock": p2, "stretch_99pct": p3}


def demand_history_window(cfg: dict = None) -> tuple:
    """(first month, last month) of the sales history the PEM101 Min and Max are computed from: the daily series from the calibration start to the end of the
    last complete month of the saved sales pull (`build_page_inputs`: mean daily demand over jc.CALIBRATION_START..validation_end). The forecast is not an input."""
    sys.path.insert(0, os.path.join(HERE, "investigations"))
    import phaseJ3_calibration_engine as jc
    cfg = cfg or load_config()
    return str(jc.CALIBRATION_START)[:7], str(ensemble_summary(cfg)["validation_end"])[:7]


def build_page_inputs(cfg: dict = None) -> dict:
    """Builds the dense grid and the ratio grid the PEM101 calibrated section of forecast/inventory.html reads, from the control run's
    recorded files (verified first), and records both with a SHA-256. No database. The only simulation-engine call is the daily demand
    series of the 92 items (to get each item's mean daily demand, as phase23_page_precompute.py did); no calibration is re-run.

    Per reorder level r on the config trade_off_curve grid: the median, min and max over members of stock value and the median not_late
    (from the members' own trade-off points); per item, Min = r x mean daily demand x 30.44 and the Max across members from each member's
    own order-up-to gap (Max = (r + gap) x ...).  Returns the two written paths."""
    sys.path.insert(0, os.path.join(HERE, "investigations"))
    import phaseJ3_calibration_engine as jc
    import task2b_part3_relative_service_cost as rsc
    cfg = cfg or load_config()
    summary = ensemble_summary(cfg)
    members = pd.read_csv(path_of(cfg["ensemble_members_file"]))
    points = pd.read_csv(path_of(cfg["ensemble_tradeoff_points_file"]))
    with open(path_of(cfg["ensemble_stock_items_file"]), encoding="utf-8") as f:
        items = sorted(json.load(f))
    if len(items) != summary["n_items"]:
        raise MaxMinV1Error(f"{len(items)} stock items on file, the calibration was fitted on {summary['n_items']}")
    raw = pd.read_csv(path_of(cfg["ensemble_raw_sales_file"]))
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw = raw[raw["itemcode"].isin(items)]
    validation_end = jc.determine_validation_end(raw)
    if validation_end != summary["validation_end"]:
        raise MaxMinV1Error(f"the saved sales pull ends {validation_end}, the calibration's validation ended {summary['validation_end']}")
    daily = jc.build_full_daily_series(raw, items, jc.CALIBRATION_START, validation_end)["series"]
    mean_demand = {c: float(daily[c].mean()) for c in items}

    gaps = (members["s_months"] - members["r_months"]).to_numpy()
    valid = points.dropna(subset=["not_late", "stock_value"])
    agg = valid.groupby("swept_r_months").agg(
        not_late_median=("not_late", "median"), stock_value_min=("stock_value", "min"), stock_value_median=("stock_value", "median"),
        stock_value_max=("stock_value", "max"), n_members=("stock_value", "count")).reset_index().rename(columns={"swept_r_months": "r"}).sort_values("r")
    dense = []
    for _, row in agg.iterrows():
        r = float(row["r"])
        rows = []
        for c in items:
            md = mean_demand[c]
            max_vals = (r + gaps) * DAYS_PER_MONTH * md
            rows.append({"code": c, "Min": round(r * DAYS_PER_MONTH * md, 2), "Max_median": round(float(np.median(max_vals)), 2),
                         "Max_min": round(float(max_vals.min()), 2), "Max_max": round(float(max_vals.max()), 2)})
        dense.append({"r": r, "not_late_median_pct": round(float(row["not_late_median"]) * 100, 3),
                      "stock_value_min": round(float(row["stock_value_min"]), 2), "stock_value_median": round(float(row["stock_value_median"]), 2),
                      "stock_value_max": round(float(row["stock_value_max"]), 2), "n_members": int(row["n_members"]), "items": rows})
    obs = summary["observed"]
    presets = _interp_presets(dense, obs["not_late_pct"], obs["stock_value_thb"])
    nl = [g["not_late_median_pct"] for g in dense]
    out = {"grid": dense, "n_distinct_members": summary["n_members"], "n_items_calibrated": summary["n_items"], "items_order": items,
           "today_point": {"not_late_pct": obs["not_late_pct"], "stock_value_thb": obs["stock_value_thb"],
                           "source": "output/summary/week1_recal_targets.json (observed validation not_late, current stock value of the 92 items)"},
           "simulated_today_point": {k: round(v, 2) for k, v in summary["simulated_today"].items()},
           "lead_time_days": {"min": summary["lead_min"], "max": summary["lead_max"], "median": summary["lead_median"]},
           "presets": presets, "not_late_range_pct": [round(min(nl), 3), round(max(nl), 3)],
           "calibrated_on": summary["calibrated_on"], "last_month_of_data": summary["validation_end"][:7],
           "source_report": "docs/reports/summary/week1_leadtime_calibration.md"}

    today = obs["not_late_pct"]
    lo_pct, hi_pct = out["not_late_range_pct"]
    grid_targets = np.round(np.arange(lo_pct, hi_pct + 0.01, 0.25), 3).tolist()
    ratio_grid = []
    for t in grid_targets:
        r = rsc.ratio_at_target(points, today, t)
        if r is not None:
            ratio_grid.append({"not_late_pct": t, **r})
    ratio = {"today_not_late_pct": today, "grid": ratio_grid,
             "source": "src/maxmin_v1.py, from output/summary/week1_recal_control_tradeoff_points_PEM101_92.csv"}

    dpath, rpath = path_of(cfg["dense_grid_file"]), path_of(cfg["ratio_grid_file"])
    for p, payload in ((dpath, out), (rpath, ratio)):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    record_outputs(cfg, [dpath, rpath])
    logger.info("dense grid %d reorder levels x %d items, %d members; ratio grid %d points", len(dense), len(items), summary["n_members"], len(ratio_grid))
    return {"dense_grid": dpath, "ratio_grid": rpath}


def record_outputs(cfg: dict, paths: list) -> dict:
    meta = {"recorded_at": datetime.now().isoformat(timespec="seconds"),
            "inputs_integrity": os.path.basename(cfg["ensemble_integrity_file"]),
            "files": {os.path.basename(p): {"sha256": sha256_file(p)} for p in paths}}
    with open(path_of(cfg["recorded_outputs_integrity_file"]), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return meta


def load_page_inputs(cfg: dict = None) -> tuple:
    """(dense grid, ratio grid) as dicts, after the hash check. Raises MaxMinV1Error when a file is missing or was changed."""
    cfg = cfg or load_config()
    names = [os.path.basename(cfg["dense_grid_file"]), os.path.basename(cfg["ratio_grid_file"])]
    verify_files(path_of(cfg["recorded_outputs_integrity_file"]), only=names)
    with open(path_of(cfg["dense_grid_file"]), encoding="utf-8") as f:
        dense = json.load(f)
    with open(path_of(cfg["ratio_grid_file"]), encoding="utf-8") as f:
        ratio = json.load(f)
    return dense, ratio


# ------------------------------------------------------------------ per-item material lead time
def material_lead_table(cfg: dict = None) -> pd.DataFrame:
    """One row per item: material_lead_days (the slowest material's lead time, production time excluded) and source_key (observed,
    supplier_quoted or assumed) of that material's value, from output/summary/item_lead_time_v1.csv after the hash check (METRICS.md Sec.5).
    An item with no walkable BOM carries the assumed value and source 'assumed'; the check below stops the build if it did not."""
    cfg = cfg or load_config()
    meta_path = path_of(cfg["item_lead_time_integrity_file"])
    csv_path = path_of(cfg["item_lead_time_file"])
    if not os.path.exists(meta_path) or not os.path.exists(csv_path):
        raise MaxMinV1Error("the per-item lead time output or its integrity file is missing")
    with open(meta_path, encoding="utf-8") as f:
        recorded = json.load(f)["sha256"]
    if sha256_file(csv_path) != recorded:
        raise MaxMinV1Error("item_lead_time_v1.csv does not hash to the value recorded in its integrity file")
    d = pd.read_csv(csv_path)
    unknown = set(d["bottleneck_source"]) - set(cfg["material_source_labels"])
    if unknown:
        raise MaxMinV1Error(f"a material source with no label: {sorted(unknown)}")
    if (d["no_bom"].astype(bool) & (d["bottleneck_source"] != "assumed")).any():
        raise MaxMinV1Error("an item with no walkable BOM does not carry an assumed material value")
    return d.rename(columns={"item": "code", "bottleneck_days": "material_lead_days", "bottleneck_source": "source_key"})[
        ["code", "material_lead_days", "source_key", "production_days", "production_source"]].reset_index(drop=True)


def material_lead_for_page(codes: list, cfg: dict = None) -> dict:
    """What the PEM101 calibrated section shows for `codes`: {code: {"days", "source" (the approved label)}}, the median of the slowest-material
    lead time over the item lead-time output's items, and the count per label. Every code must be in the lead-time output."""
    cfg = cfg or load_config()
    t = material_lead_table(cfg)
    missing = sorted(set(codes) - set(t["code"]))
    if missing:
        raise MaxMinV1Error(f"no per-item lead time for: {missing}")
    labels = cfg["material_source_labels"]
    by = t.set_index("code")
    per_item = {c: {"days": float(by.loc[c, "material_lead_days"]), "source": labels[by.loc[c, "source_key"]]} for c in codes}
    shown = t[t["code"].isin(codes)]
    observed = shown[shown["source_key"] == "observed"]
    return {"per_item": per_item, "median_days": float(t["material_lead_days"].median()),
            # D3 (the user, 2026-10-06): the page states the median over the shown items whose value comes from observed purchase records only,
            # with their count and the number of items shown.
            "median_observed_days": float(observed["material_lead_days"].median()) if len(observed) else None,
            "n_observed": int(len(observed)), "n_items_shown": int(len(shown)),
            "label_counts": {labels[k]: int(v) for k, v in t["source_key"].value_counts().items()}, "n_items": int(len(t))}


# ------------------------------------------------------------------ assumptions
def _fmt_days(x: float) -> str:
    return str(int(round(x))) if float(x).is_integer() else f"{x:g}"


THAI_MONTH_NAMES = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]


def thai_window(start: str, end: str) -> str:
    """'2024-01', '2025-12' -> 'มกราคม 2567 ถึง ธันวาคม 2568' (Thai month name and Buddhist year, both ends)."""
    def one(ym):
        return f"{THAI_MONTH_NAMES[int(ym[5:7]) - 1]} {int(ym[:4]) + 543}"
    return f"{one(start)} ถึง {one(end)}"


def assumption_values(cfg: dict = None) -> dict:
    """The values the braces in config maxmin_v1.assumptions name, each from its recorded source."""
    cfg = cfg or load_config()
    full = load_full_config()
    s = ensemble_summary(cfg)
    t = material_lead_table(cfg)
    assumed = t[t["production_source"] == "assumed"]
    days = sorted(set(assumed["production_days"]))
    if len(days) != 1:
        raise MaxMinV1Error(f"the assumed production time is not one value: {days}")
    import build_inventory_page_data as bd
    seg = bd._load_fulfilment_segmentation("PEM101")
    return {"lead_min": s["lead_min"], "lead_max": s["lead_max"],
            "assumed_production_days": _fmt_days(days[0]), "n_assumed_production": int(len(assumed)),
            "sellable_warehouses": ", ".join(full["phase_e1_assumptions"]["sellable_warehouse_codes"]["PEM101"]),
            "n_undetermined": int((seg["class"] == "conflict").sum()),
            "calibration_window": thai_window(cfg["calibration_window"]["start"], cfg["calibration_window"]["end"])}


def build_assumptions(cfg: dict = None, today: str = None) -> dict:
    """The payload of data/assumptions.json: {"schema_version", "assumptions": [{id, topic, unknown, used_now, affects, value_source,
    updated_date}, ...], "pending_criteria": [{topic, to_decide, now_used, who, when}, ...]} in config order. updated_date is the build date (`today`, or the clock)."""
    cfg = cfg or load_config()
    values = assumption_values(cfg)
    stamp = today or datetime.now().strftime("%Y-%m-%d")
    records = []
    for a in cfg["assumptions"]:
        rec = {k: a[k].format(**values) for k in ("id", "topic", "unknown", "used_now", "affects", "value_source")}
        rec["updated_date"] = stamp
        records.append(rec)
    return {"schema_version": ASSUMPTIONS_SCHEMA_VERSION, "assumptions": records, "pending_criteria": pending_criteria_rows(cfg)}


def pending_criteria_rows(cfg: dict = None) -> list:
    """The rows of the table "เกณฑ์ที่รอกำหนด": [{topic, to_decide, now_used, who, when}, ...] in config order, the braces filled from config
    `pending_criteria_values` (numbers as written in config, the decision date as 'd MMM yy' by the shared Thai date formatter). The values are drafts: nothing
    in the project passes or fails against them."""
    import reader_values as rv
    cfg = cfg or load_config()
    v = cfg["pending_criteria_values"]
    values = {"mase_pass": f"{v['mase_pass']:g}", "mase_good": f"{v['mase_good']:g}", "tracking_signal_limit": f"{v['tracking_signal_limit']:g}",
              "decision_date": rv.thai_date_short(v["decision_date"])}
    return [{k: r[k].format(**values) for k in ("topic", "to_decide", "now_used", "who", "when")} for r in cfg["pending_criteria_rows"]]


def write_assumptions(path: str = None, cfg: dict = None, today: str = None) -> str:
    """Writes the assumptions file (UTF-8, indent 1, Thai kept as Thai) and returns its path. The default is the tracked data/assumptions.json."""
    cfg = cfg or load_config()
    path = path or path_of(cfg["assumptions_file"])
    payload = build_assumptions(cfg, today)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return path


# ------------------------------------------------------------------ Min and Max on the stock share of mixed items (week 4, computed only)
def mixed_item_min_max(page_data: dict, item_level: pd.DataFrame, members: pd.DataFrame, first_month: str) -> dict:
    """Min and Max for the mixed items, on the share of their demand sold from stock: each month's forecast times the item's MTS share of ordered quantity over the
    last 12 months (item-level file column mts_share_12m). Nothing in the operation plan, the material plan or any page reads the result.

    * a PEM101 item: the page's calibrated ensemble at the setting the page applies on load (preset today_lowest_stock, reorder level r in months): Min = r x M,
      Max = the median over the control run's distinct members of (r + gap) x M, gap = order-up-to minus reorder level in months, M = mean monthly stock demand over the
      forecast horizon (the page's own items use their history's mean daily demand x 30.44; for a mixed item the stock share of the forecast is used, as asked);
    * any other division: the uncalibrated scenario defaults the page uses for PEM107 stock items (`tier_a_defaults`), the Python mirror of the page's engine, on the
      stock-share forecast and the history scaled by the same share.
    Returns {"meta": ..., "items": [{division, item, method, share, months, forecast, stock_demand, min, max, ...}]}."""
    import inventory_recompute_reference as ref
    mixed = item_level[item_level["mixed_applied"].astype(bool)].sort_values(["division", "code"])
    controls, dpm = page_data["tier_a_defaults"], float(page_data["days_per_month"])
    gaps = (members["s_months"] - members["r_months"]).to_numpy()
    out = []
    for _, row in mixed.iterrows():
        div, code, share = row["division"], row["code"], float(row["mts_share_12m"])
        hit = [i for i in page_data["divisions"][div]["items"] if i["code"] == code]
        if not hit:
            raise MaxMinV1Error(f"{code} of {div} is not on the inventory page, so it has no forecast and history to take the stock share of")
        it = hit[0]
        forecast = [float(x) for x in it["forecast"]]
        stock_demand = [x * share for x in forecast]
        months = [str(pd.Period(first_month, freq="M") + k) for k in range(len(forecast))]
        rec = {"division": div, "item": code, "share": share, "months": months, "forecast": forecast, "stock_demand": stock_demand}
        ct = page_data["divisions"][div].get("curve_target")
        if ct:
            r = float(ct["presets"]["today_lowest_stock"]["r"])
            level = float(np.mean(stock_demand))
            rec.update({"method": "calibrated_section_default", "r_months": r, "n_members": int(len(gaps)), "level_monthly_stock_demand": level,
                        "min": r * level, "max": float(np.median((r + gaps) * level))})
        else:
            scaled = dict(it, forecast=stock_demand, actual_history=[float(x) * share for x in it["actual_history"]])
            res = ref.compute_item_min_max(scaled, controls, dpm)
            rec.update({"method": "scenario_default_uncalibrated", "min": res["min"], "max": res["max"], "ltd": res["ltd"], "safety_stock": res["safety_stock"],
                        "unreliable": bool(res["unreliable"])})
        out.append(rec)
    return {"meta": {"basis": "forecast x MTS share of ordered quantity over the last 12 months", "first_month": first_month, "controls": controls,
                     "days_per_month": dpm, "n_items": len(out), "calibrated_preset": "today_lowest_stock"}, "items": out}


def _hash_payload(payload: dict) -> str:
    body = json.dumps({"meta": payload["meta"], "items": payload["items"]}, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def write_mixed_item_min_max(path: str, payload: dict) -> str:
    """Writes the recorded output: one JSON file that carries the SHA-256 of its own meta and items (checked by `read_mixed_item_min_max`)."""
    rec = dict(payload, recorded_at=datetime.now().isoformat(timespec="seconds"), sha256=_hash_payload(payload))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1, allow_nan=False)
        f.write("\n")
    return path


def read_mixed_item_min_max(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    if rec.get("sha256") != _hash_payload(rec):
        raise MaxMinV1Error(f"{path} does not hash to the value it records")
    return rec


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build-inputs":
        print(json.dumps(build_page_inputs(), indent=1))
    elif cmd == "assumptions":
        print(write_assumptions())
    elif cmd == "summary":
        print(json.dumps(ensemble_summary(), indent=1))
    elif cmd == "mixed-item-min-max":
        import operation_plan as _op
        _cfg = load_full_config()
        _mc, _oc = _cfg["maxmin_v1"], _cfg["operation_plan"]
        verify_ensemble_files(_mc)
        _om = _op.read_outputs(PROJECT_ROOT, _oc)[2]
        _res = mixed_item_min_max(_op.read_page_data(path_of(_oc["inventory_page_file"])), pd.read_csv(path_of(_oc["item_class_file"])),
                                  pd.read_csv(path_of(_mc["ensemble_members_file"])), _om["months"][0])
        print(write_mixed_item_min_max(path_of(_mc["mixed_item_min_max_file"]), _res))
    else:
        raise SystemExit("usage: python src/maxmin_v1.py build-inputs | assumptions | summary | mixed-item-min-max")
