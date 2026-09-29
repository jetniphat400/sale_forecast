"""Task 2b, Part 7 -- Validator independent recomputation of four Modeler figures from task 2b
(2026-09-28): METRICS.md Sec.23 fulfilment_segmentation (PEM101/PEM107), a fresh
on_hand_sellable/excess-stock figure for a non-default warehouse/threshold selection (PEM101),
METRICS.md Sec.24 relative_service_cost median ratio_e (PEM101, presets 1 and 3), and the PEM107
delivery-timeliness alert (before/after not_late, top-3 late Product Codes).

Per this task's brief (AGENTS.md Validator role): this script does NOT read, import, or otherwise
rely on any of the Modeler's task 2b files (src/investigations/task2b_part2_*.py,
task2b_part3_*.py, task2b_part4_*.py, or the new formulas added to build_inventory_page_data.py /
build_inventory_page.py / inventory_recompute_reference.py this same task). All aggregation,
classification and ratio logic below is written independently from METRICS.md's own prose
definitions (Sec.9, Sec.19, Sec.23, Sec.24, Sec.40) and from PRE-EXISTING project infrastructure
established before task 2b (src/phaseE1_common.py, src/cube_final_pull.py, src/cube_ces_pull.py,
src/pricelist_reader.py, and the batch-traceability join method already used in
src/investigations/phase25_analyst3_analysis.py's measure3_batch_traceability, which predates task
2b and is reused here as the established join pattern -- jobno <-> Cube_CES.OLMJobCode, batch
"existed" date = earliest cube_final.final_date per jobno, compared against Cube_CES.CtrDate as the
createDate/PO-date proxy).

DATABASE ACCESS RULE (binding, this task's brief): ONE connection attempt for this whole script.
On a failed login, stop immediately and report the failure -- no retry. All SELECTs run over the
same connection/session.
"""
import json
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_SRC = os.path.dirname(SRC_DIR)
sys.path.insert(0, PROJECT_SRC)

from db import get_connection  # noqa: E402
from cube_final_pull import pull_cube_final_for_items  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task2b_part7_validator")

PROJECT_ROOT = os.path.dirname(PROJECT_SRC)
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")

ITEM_STATUS_FILE = os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv")
TRADEOFF_CURVE_FILE = os.path.join(SUMMARY_DIR, "phase23_modeler_tradeoff_curve_points.csv")
NOT_LATE_RECONCILED_FILE = os.path.join(SUMMARY_DIR, "phaseJ3_validator_not_late_reconciled.csv")
MONTHS_OF_COVER_128_FILE = os.path.join(SUMMARY_DIR, "phaseE1fix_2_months_of_cover.csv")

SALE_APD_TABLE = "[salewarehouse].[dbo].[cube_Sale_APD]"
INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def code_list_sql(codes):
    return "','".join(sorted(set(codes)))


# ==================================================================================================
# CHECK 1: METRICS.md Sec.23 fulfilment_segmentation, PEM101 + PEM107
# ==================================================================================================

def check1_fulfilment_segmentation(conn, config):
    logger.info("=== CHECK 1: fulfilment_segmentation (METRICS.md Sec.23), PEM101/PEM107 ===")
    status_df = pd.read_csv(ITEM_STATUS_FILE)
    universe = status_df[(status_df["division"].isin(["PEM101", "PEM107"])) &
                          (status_df["status_category"] == "forecast")].copy()
    n_pem101 = int((universe["division"] == "PEM101").sum())
    n_pem107 = int((universe["division"] == "PEM107").sum())
    logger.info("Item universe (status_category=='forecast'): PEM101=%d, PEM107=%d (source: %s)",
                n_pem101, n_pem107, ITEM_STATUS_FILE)
    assert n_pem101 == 144 and n_pem107 == 112, "Universe counts do not match DATA_MAP's cited 144/112"

    codes = universe["itemcode"].tolist()
    code_list = code_list_sql(codes)

    # --- label: dominant manufacturing_type by qty, Omni Channel / Actual+MPS / createDate>=2024-01-01
    # (this project's standard demand-scope window, config['date_range']['start'] /
    # src/phaseE1_common.py TOTAL_MONTHS window -- reused for consistency, not re-derived) ---
    sql_label = f"""
        SELECT itemcode, qty, manufacturing_type
        FROM {SALE_APD_TABLE}
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = 'Omni Channel'
          AND status IN ('Actual','MPS')
          AND createDate >= '{config["date_range"]["start"]}'
    """
    apd = pd.read_sql(sql_label, conn)
    logger.info("cube_Sale_APD pull for label: %d rows", len(apd))
    apd["manufacturing_type"] = apd["manufacturing_type"].fillna("MISSING")
    apd["qty"] = apd["qty"].fillna(0)

    label = {}
    for code, g in apd.groupby("itemcode"):
        qty_tot = g["qty"].sum()
        if qty_tot <= 0:
            label[code] = "mixed"  # no positive-qty history in this window -- cannot assert dominance
            continue
        share = g.groupby("manufacturing_type")["qty"].sum() / qty_tot
        top_type = share.idxmax()
        label[code] = top_type if share[top_type] >= 0.60 else "mixed"
    for code in codes:
        if code not in label:
            label[code] = "mixed"  # zero rows at all in this window -- no basis for dominance

    # --- S1: on-hand stock > 0, ANY warehouse, current snapshot ---
    sql_inv = f"SELECT itemcode, warehouse, stock FROM {INV_TABLE} WHERE itemcode IN ('{code_list}')"
    inv = pd.read_sql(sql_inv, conn)
    logger.info("Cube_Inventory_Exact pull for S1: %d rows", len(inv))
    onhand = inv.groupby("itemcode")["stock"].sum()
    s1 = {code: bool(onhand.get(code, 0.0) > 0) for code in codes}

    # --- S2/S3: Cube_CES (delivered contracts, Status='Actual'), joined to cube_final via
    # jobno <-> OLMJobCode (established pre-task-2b join, phase25_analyst3_analysis.py) ---
    sql_ces = f"""
        SELECT ItemCode, Status, CtrDate, ActualDelDate, ActualQty, RevenueType, OLMJobCode
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
    """
    ces = pd.read_sql(sql_ces, conn)
    logger.info("Cube_CES pull for S2/S3: %d rows", len(ces))
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")
    delivered = ces[ces["Status"] == "Actual"].copy()
    logger.info("Delivered (Status='Actual') rows: %d", len(delivered))

    cf = pull_cube_final_for_items(codes, allow_empty=True)
    logger.info("cube_final pull: %d rows", len(cf))
    if len(cf):
        cf["final_date"] = pd.to_datetime(cf["final_date"], errors="coerce")
        batch_avail = cf.groupby("jobno")["final_date"].min()
    else:
        batch_avail = pd.Series(dtype="datetime64[ns]")

    def is_blank(x):
        if pd.isna(x):
            return True
        s = str(x).strip()
        return s == "" or s.lower() == "none"

    delivered["has_token"] = ~delivered["OLMJobCode"].apply(is_blank)
    delivered["batch_avail_date"] = delivered["OLMJobCode"].map(batch_avail)

    def trace_class(r):
        if pd.isna(r["CtrDate"]):
            return "no_ctrdate"
        if not r["has_token"]:
            return "no_token"
        if pd.isna(r["batch_avail_date"]):
            return "no_cube_final_link"
        return "traceable_pre_existing" if r["batch_avail_date"] < r["CtrDate"] else "not_pre_existing"

    delivered["trace_class"] = delivered.apply(trace_class, axis=1)

    s2 = {}
    s2_computable = {}
    for code in codes:
        g = delivered[delivered["ItemCode"] == code]
        n_total = len(g)
        n_known = int(g["trace_class"].isin(["traceable_pre_existing", "not_pre_existing"]).sum())
        if n_total == 0 or n_known == 0:
            s2_computable[code] = False
            s2[code] = None
            continue
        s2_computable[code] = True
        n_pre = int((g["trace_class"] == "traceable_pre_existing").sum())
        s2[code] = (n_pre / n_total) >= 0.50  # literal METRICS.md reading: share of ALL delivered contracts

    # --- S3: median days CtrDate -> ActualDelDate <= 14, per item ---
    s3 = {}
    for code in codes:
        g = delivered[(delivered["ItemCode"] == code) & delivered["ActualDelDate"].notna() &
                       delivered["CtrDate"].notna()]
        if len(g) == 0:
            s3[code] = None
            continue
        notice = (g["ActualDelDate"] - g["CtrDate"]).dt.days
        s3[code] = bool(notice.median() <= 14)

    # --- classification ---
    rows = []
    for code in codes:
        lab = label[code]
        sig1, sig2, sig3 = s1[code], s2[code], s3[code]
        if sig2 is None:
            # S2 not computable -- fall back per METRICS.md Sec.23's own stated rule for
            # stock_policy ("evaluate on S1 and S3 and require both to hold"); symmetric extension
            # applied here to confirmed_to_order/conflict too (own inference, flagged below).
            n_hold = int(sig1) + int(sig3)
            n_signals = 2
        else:
            n_hold = int(sig1) + int(sig2) + int(sig3)
            n_signals = 3

        if lab == "MTS":
            if sig2 is None:
                cls = "stock_policy" if (sig1 and sig3) else "conflict"
            else:
                cls = "stock_policy" if n_hold >= 2 else "conflict"
        elif lab in ("MTO", "ETO"):
            max_allowed = 1 if n_signals == 3 else 0  # "at most 1 of 3" -> "at most 0 of 2" when S2 dropped -- OWN INFERENCE
            cls = "confirmed_to_order" if n_hold <= max_allowed else "conflict"
        else:  # mixed
            cls = "conflict"

        rows.append(dict(itemcode=code, division=universe.set_index("itemcode").loc[code, "division"],
                          label=lab, S1=sig1, S2=sig2, S2_computable=s2_computable[code], S3=sig3,
                          n_signals_hold=n_hold, n_signals_evaluated=n_signals, klass=cls))

    result = pd.DataFrame(rows)
    result.to_csv(os.path.join(SUMMARY_DIR, "task2b_validator_part7_fulfilment_segmentation.csv"),
                  index=False)

    counts = {}
    for div in ("PEM101", "PEM107"):
        d = result[result["division"] == div]
        counts[div] = d["klass"].value_counts().to_dict()
    logger.info("Class counts: %s", counts)
    return result, counts, n_pem101, n_pem107


# ==================================================================================================
# CHECK 2: on_hand_sellable + excess count, PEM101, warehouse=[FG01] only, threshold=3 months
# ==================================================================================================

def check2_fresh_warehouse_threshold(conn):
    logger.info("=== CHECK 2: on_hand_sellable/excess, PEM101, warehouse=[FG01], threshold=3mo ===")
    moc128 = pd.read_csv(MONTHS_OF_COVER_128_FILE)
    codes = moc128["code"].tolist()
    logger.info("Item universe: 128-item PEM101 pilot scope with a computable mean_monthly_forecast "
                "(source: %s, pre-existing, not this task's Modeler output). NOTE: this is narrower "
                "than the full 144-item PEM101 forecast universe (task 2b's own noted 10-item "
                "coverage gap outside the 128-item pilot pipeline applies here too -- same gap, "
                "not a new one).", MONTHS_OF_COVER_128_FILE)

    code_list = code_list_sql(codes)
    sql = f"SELECT itemcode, warehouse, stock FROM {INV_TABLE} WHERE itemcode IN ('{code_list}')"
    inv = pd.read_sql(sql, conn)
    logger.info("Cube_Inventory_Exact fresh pull: %d rows", len(inv))
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()

    fg01_only = inv[inv["warehouse"] == "FG01"]
    onhand = fg01_only.groupby("itemcode")["stock"].sum()

    out = moc128[["code", "mean_monthly_forecast"]].copy()
    out["on_hand_sellable_fg01_only"] = out["code"].map(onhand).fillna(0.0)
    out["months_of_cover_fg01_only"] = np.where(
        out["mean_monthly_forecast"] > 0,
        out["on_hand_sellable_fg01_only"] / out["mean_monthly_forecast"],
        np.inf)
    threshold = 3
    out["excess_stock_flag"] = np.where(
        out["mean_monthly_forecast"] > 0,
        out["months_of_cover_fg01_only"] > threshold,
        out["on_hand_sellable_fg01_only"] > 0)  # zero-forecast items: excess iff any on-hand stock (METRICS Sec.40)

    out.to_csv(os.path.join(SUMMARY_DIR, "task2b_validator_part7_check2_fg01_threshold3.csv"), index=False)

    total_onhand = float(out["on_hand_sellable_fg01_only"].sum())
    excess_count = int(out["excess_stock_flag"].sum())
    n_zero_forecast = int((out["mean_monthly_forecast"] <= 0).sum())
    logger.info("Total on_hand_sellable (FG01 only, %d items): %.1f. Excess count (threshold=3mo): %d "
                "(%d items have zero forecast, handled per METRICS Sec.40's separate rule).",
                len(out), total_onhand, excess_count, n_zero_forecast)
    return total_onhand, excess_count, len(out), n_zero_forecast


# ==================================================================================================
# CHECK 3: METRICS.md Sec.24 relative_service_cost median ratio_e, PEM101, presets 1 and 3
# ==================================================================================================

def check3_relative_service_cost():
    logger.info("=== CHECK 3: relative_service_cost median ratio_e, PEM101, presets 1 & 3 ===")
    curve = pd.read_csv(TRADEOFF_CURVE_FILE)
    n_members = curve["member_idx"].nunique()
    logger.info("Loaded %d rows, %d distinct members from %s", len(curve), n_members, TRADEOFF_CURVE_FILE)
    assert n_members == 80

    reconciled = pd.read_csv(NOT_LATE_RECONCILED_FILE)
    row = reconciled[(reconciled["division"] == "PEM101") &
                      (reconciled["weighting"] == "unit_ActualQty") &
                      (reconciled["period"] == "validation_2026-01-01_onward")]
    assert len(row) == 1, "Expected exactly one matching row for today's real not_late"
    today_not_late = float(row["not_late"].iloc[0])  # fraction, e.g. 0.98276
    logger.info("Today's real not_late (PEM101, unit-weighted, most recent validation period): "
                "%.6f (%.3f%%) -- source: %s", today_not_late, today_not_late * 100, NOT_LATE_RECONCILED_FILE)

    def interp_member(member_df, target_not_late):
        m = member_df.sort_values("not_late")
        nl = m["not_late"].to_numpy()
        sv = m["stock_value"].to_numpy()
        in_range = nl.min() <= target_not_late <= nl.max()
        val = float(np.interp(target_not_late, nl, sv))
        return val, in_range

    preset1_target = today_not_late
    preset3_target = 0.99

    ratios_p1, ratios_p3 = [], []
    n_oor_p1, n_oor_p3 = 0, 0
    for mi, g in curve.groupby("member_idx"):
        sv_today, ok_today = interp_member(g, today_not_late)
        sv_p1, ok_p1 = interp_member(g, preset1_target)
        sv_p3, ok_p3 = interp_member(g, preset3_target)
        if not ok_today or not ok_p1:
            n_oor_p1 += 1
        else:
            ratios_p1.append(sv_p1 / sv_today)
        if not ok_today or not ok_p3:
            n_oor_p3 += 1
        else:
            ratios_p3.append(sv_p3 / sv_today)

    def summarize(vals):
        a = np.array(vals)
        return dict(n=len(a), median=float(np.median(a)), min=float(a.min()), max=float(a.max()))

    p1_summary = summarize(ratios_p1)
    p3_summary = summarize(ratios_p3)
    logger.info("Preset 1 (target=today's not_late, ratio_e should be 1.000 by construction): %s", p1_summary)
    logger.info("Preset 3 (target=99.0%%): %s", p3_summary)
    logger.info("Out-of-range members: preset1=%d, preset3=%d (of %d)", n_oor_p1, n_oor_p3, n_members)

    pd.DataFrame({"preset1_ratio_e": ratios_p1}).to_csv(
        os.path.join(SUMMARY_DIR, "task2b_validator_part7_check3_preset1_ratios.csv"), index=False)
    pd.DataFrame({"preset3_ratio_e": ratios_p3}).to_csv(
        os.path.join(SUMMARY_DIR, "task2b_validator_part7_check3_preset3_ratios.csv"), index=False)

    return p1_summary, p3_summary, n_oor_p1, n_oor_p3, today_not_late


# ==================================================================================================
# CHECK 4: PEM107 alert -- before/after not_late, top 3 Product Codes by units late
# ==================================================================================================

def check4_pem107_alert(conn, config):
    logger.info("=== CHECK 4: PEM107 alert, before/after not_late + top3 late codes ===")
    pricelist = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    pem107_rows = pricelist[pricelist["sheet"] == "PEM107 CT-Version 2"].drop_duplicates("code")
    codes = pem107_rows["code"].tolist()
    logger.info("PEM107 pricelist item universe (visible sheet 'PEM107 CT-Version 2', PRICELIST "
                "RULE): %d codes", len(codes))

    code_list = code_list_sql(codes)
    sql = f"""
        SELECT ItemCode, Status, RevenueType, ForecastDelDate, ActualDelDate, ActualQty
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
          AND Status = 'Actual'
          AND RevenueType = 'Omni Channel'
          AND ForecastDelDate >= '2024-01-01'
    """
    ces = pd.read_sql(sql, conn)
    logger.info("Cube_CES fresh pull (Status='Actual', RevenueType='Omni Channel', "
                "ForecastDelDate>='2024-01-01', PEM107 itemcodes): %d rows", len(ces))
    ces["ForecastDelDate"] = pd.to_datetime(ces["ForecastDelDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")
    n_before_drop = len(ces)
    ces = ces.dropna(subset=["ForecastDelDate", "ActualDelDate"]).copy()
    logger.info("Dropped %d rows missing ForecastDelDate/ActualDelDate; %d usable",
                n_before_drop - len(ces), len(ces))
    ces["ActualQty"] = ces["ActualQty"].fillna(0)
    ces["not_late"] = ces["ActualDelDate"] <= ces["ForecastDelDate"]
    ces["late"] = ~ces["not_late"]

    before = ces[ces["ForecastDelDate"] < "2026-05-01"]
    after = ces[ces["ForecastDelDate"] >= "2026-05-01"]

    def unit_weighted_not_late(d):
        qty = d["ActualQty"].sum()
        if qty <= 0:
            return np.nan, 0.0
        return float((d["not_late"] * d["ActualQty"]).sum() / qty), float(qty)

    nl_before, units_before = unit_weighted_not_late(before)
    nl_after, units_after = unit_weighted_not_late(after)
    logger.info("not_late (unit-weighted): before 2026-05-01 = %.4f%% (n=%.0f units); "
                "from 2026-05-01 = %.4f%% (n=%.0f units)",
                nl_before * 100, units_before, nl_after * 100, units_after)

    late_after = after[after["late"]]
    top3 = (late_after.groupby("ItemCode")["ActualQty"].sum()
            .sort_values(ascending=False).head(3))
    top3_df = top3.reset_index().rename(columns={"ItemCode": "code", "ActualQty": "units_late"})
    top3_df = top3_df.merge(pricelist[["code", "type", "description"]].drop_duplicates("code"),
                             on="code", how="left")
    logger.info("Top 3 Product Codes by units late (post-2026-05-01 window):\n%s", top3_df.to_string())

    ces.to_csv(os.path.join(SUMMARY_DIR, "task2b_validator_part7_check4_ces_raw.csv"), index=False)
    top3_df.to_csv(os.path.join(SUMMARY_DIR, "task2b_validator_part7_check4_top3.csv"), index=False)

    return dict(nl_before=nl_before, units_before=units_before, nl_after=nl_after,
                units_after=units_after, top3=top3_df, n_codes=len(codes))


# ==================================================================================================

def main():
    config = load_config()

    logger.info("DATABASE ACCESS RULE: opening the single connection attempt now. No retry on failure.")
    try:
        engine = get_connection()
        conn = engine.connect()
    except Exception as exc:
        logger.error("Connection FAILED -- STOPPING, not retrying. Verbatim error: %r", exc)
        print(f"CONNECTION FAILED: {exc!r}")
        with open(os.path.join(SUMMARY_DIR, "task2b_validator_report.md"), "w", encoding="utf-8") as f:
            f.write("# Task 2b Validator report\n\nDATABASE CONNECTION FAILED on the single "
                    f"attempt. Verbatim error: {exc!r}\n\nNo checks could be run. Stopping per "
                    "the DB access rule and AGENTS.md's stopping rule -- report the gap, do not "
                    "retry or improvise.\n")
        return
    logger.info("Connected successfully. Running all queries in this one session.")

    try:
        c1_result, c1_counts, n_pem101, n_pem107 = check1_fulfilment_segmentation(conn, config)
        c2_total_onhand, c2_excess_count, c2_n_items, c2_n_zero_forecast = check2_fresh_warehouse_threshold(conn)
        c4 = check4_pem107_alert(conn, config)
    finally:
        conn.close()
        logger.info("Connection closed.")

    # Check 3 needs no DB access -- runs after the connection is closed.
    c3_p1, c3_p3, c3_oor1, c3_oor3, c3_today_notlate = check3_relative_service_cost()

    with open(os.path.join(SUMMARY_DIR, "task2b_part7_validator_results.json"), "w", encoding="utf-8") as f:
        json.dump({
            "check1_counts": c1_counts,
            "check1_n_pem101": n_pem101, "check1_n_pem107": n_pem107,
            "check2_total_onhand_fg01": c2_total_onhand, "check2_excess_count": c2_excess_count,
            "check2_n_items": c2_n_items, "check2_n_zero_forecast": c2_n_zero_forecast,
            "check3_preset1": c3_p1, "check3_preset3": c3_p3,
            "check3_today_not_late": c3_today_notlate,
            "check4_nl_before": c4["nl_before"], "check4_units_before": c4["units_before"],
            "check4_nl_after": c4["nl_after"], "check4_units_after": c4["units_after"],
            "check4_top3": c4["top3"].to_dict(orient="records"),
        }, f, indent=2, default=str)

    print("VALIDATOR RUN DONE")


if __name__ == "__main__":
    main()
