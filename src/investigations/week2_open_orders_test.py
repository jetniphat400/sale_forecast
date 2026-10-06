"""Week 2, Part 1: can an open production order be identified in Cube_Production_Order, and does its planned finish mean what the plan needs?

Reads two saved pulls (no database): the table as pulled on 2026-10-06 and cube_final's records; and the earlier pull of the table (2026-10-05) for the
one-day comparison of statuses. Tests, with thresholds fixed in config `operation_plan.open_orders_test` before the run:

  structure : one plan row per (job, item) is the row with to_be_realized > 0; rows with to_be_realized = 0 are separate rows of the same job and item
  C1        : for finished orders (a cube_final record for the same job and item), the final record against the planned finish (end_date)
  C2        : the orders a status rule calls open (status open or Released): how many are already long past their planned finish
  C2b       : open by receipts: an order is closed when its zero-remaining rows reach the planned quantity; finished orders should show that
  C3        : cube_final's coverage of orders that should be finished by now: a missing record means open only if the coverage is high
  lifecycle : status transitions between the two pulls, and orders that left the table in one day

The verdict is usable only when C1 holds (the plan needs the finish date) and at least one way of telling an open order passes (C2, C2b or C3).
C1 to C3 and their thresholds were fixed before the first run; C2b was added after it (see config). Writes output/summary/week2_open_orders_test.json (and nothing else).
"""
import hashlib
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))


def _pct(x: float) -> float:
    return round(100 * float(x), 1)


def job_items(po: pd.DataFrame) -> pd.DataFrame:
    """One row per (job, item): the plan row's planned quantity and finish, its status, and the rows with to_be_realized = 0 summarised."""
    po = po.copy()
    for c in ("start_date", "end_date", "actual_date"):
        po[c] = pd.to_datetime(po[c])
    po["is_plan"] = po["to_be_realized"] > 0
    rows = []
    for (job, item), x in po.groupby(["job", "itemcode"]):
        plan, real = x[x["is_plan"]], x[~x["is_plan"]]
        rows.append({"job": job, "item": item, "n_plan_rows": len(plan), "n_other_rows": len(real),
                     "planned_qty": plan["planed"].sum(), "to_be_realized": plan["to_be_realized"].sum(),
                     "other_rows_qty": real["planed"].sum(),
                     "end_date": plan["end_date"].max() if len(plan) else pd.NaT,
                     "plan_actual_equals_end": bool((plan["actual_date"] == plan["end_date"]).all()) if len(plan) else None,
                     "status": plan["status"].iloc[0] if len(plan) else ";".join(sorted(set(x["status"])))})
    return pd.DataFrame(rows)


def run_test(po: pd.DataFrame, cf: pd.DataFrame, earlier: pd.DataFrame, cfg: dict, today: pd.Timestamp, plan_items: set) -> dict:
    t = cfg["open_orders_test"]
    J = job_items(po)
    cf = cf.copy()
    cf["final_date"] = pd.to_datetime(cf["final_date"])
    last_final = cf.groupby(["jobno", "itemcode"])["final_date"].max().rename("final_last").reset_index()
    J = J.merge(last_final, left_on=["job", "item"], right_on=["jobno", "itemcode"], how="left").drop(columns=["jobno", "itemcode"])
    J["finished"] = J["final_last"].notna()
    P = J[J["n_plan_rows"] == 1].copy()
    out = {"tested_on": str(today.date()), "criteria": t, "rows": int(len(po)), "job_items": int(len(J)),
           "job_items_one_plan_row": int(len(P)), "job_items_no_plan_row": int((J["n_plan_rows"] == 0).sum()),
           "job_items_more_than_one_plan_row": int((J["n_plan_rows"] > 1).sum()),
           "status_counts_rows": po["status"].value_counts().to_dict()}

    out["structure"] = {
        "plan_rows_actual_date_equals_end_date": int(P["plan_actual_equals_end"].sum()), "plan_rows": int(len(P)),
        "plan_rows_to_be_realized_equals_planned": _pct((P["to_be_realized"] == P["planned_qty"]).mean()),
        "job_items_with_other_rows": int((P["n_other_rows"] > 0).sum()),
        "other_rows_qty_above_planned_share_pct": _pct((P.loc[P["n_other_rows"] > 0, "other_rows_qty"] > P.loc[P["n_other_rows"] > 0, "planned_qty"]).mean()),
    }

    def c1(frame):
        f = frame[frame["finished"]]
        d = (f["final_last"].dt.normalize() - f["end_date"]).dt.days
        return {"n_finished": int(len(f)), "share_within": _pct((d.abs() <= t["finish_within_days"]).mean()) if len(f) else None,
                "within_7_days_pct": _pct((d.abs() <= 7).mean()) if len(f) else None,
                "median_days": float(d.median()), "p25": float(d.quantile(.25)), "p75": float(d.quantile(.75)),
                "final_before_planned_pct": _pct((d < 0).mean()), "final_after_planned_pct": _pct((d > 0).mean())}
    out["C1_planned_finish_vs_final"] = {"all_items": c1(P), "plan_items": c1(P[P["item"].isin(plan_items)])}
    out["C1_pass"] = bool(out["C1_planned_finish_vs_final"]["all_items"]["share_within"] >= 100 * t["min_share_within"])

    out["status_of_finished_orders"] = {"finished": P[P["finished"]]["status"].value_counts().to_dict(),
                                        "not_finished": P[~P["finished"]]["status"].value_counts().to_dict()}
    P["days_past_planned"] = (today.normalize() - P["end_date"]).dt.days
    opn = P[P["status"].isin(t["open_statuses"]) & ~P["finished"]]
    stale = (opn["days_past_planned"] > t["stale_days"]).mean() if len(opn) else np.nan
    out["C2_open_by_status"] = {
        "orders": int(len(opn)), "past_planned_by_more_than_stale_days_pct": _pct(stale),
        "median_days_past_planned": float(opn["days_past_planned"].median()),
        "plan_items_orders": int(opn["item"].isin(plan_items).sum()),
        "finished_orders_flagged_open": int(P[P["finished"]]["status"].isin(t["open_statuses"]).sum()),
        "printed_orders_with_other_rows_not_finished": int(((P["status"] == "Printed") & ~P["finished"] & (P["n_other_rows"] > 0)).sum())}
    out["C2_pass"] = bool(stale <= t["max_stale_open_share"])

    od = P[P["days_past_planned"] > t["coverage_overdue_days"]]
    cov = od["finished"].mean() if len(od) else np.nan
    out["C3_final_record_coverage"] = {"orders_past_planned_by_more_than_days": int(len(od)), "with_final_record_pct": _pct(cov),
                                       "plan_items_orders": int(od["item"].isin(plan_items).sum()),
                                       "plan_items_with_final_record_pct": _pct(od[od["item"].isin(plan_items)]["finished"].mean())}
    out["C3_pass"] = bool(cov >= t["min_final_coverage"])

    # lifecycle between the two pulls, plan rows only
    E = job_items(earlier)
    E = E[E["n_plan_rows"] == 1]
    m = E.merge(P[["job", "item", "status"]], on=["job", "item"], how="outer", suffixes=("_earlier", "_now"), indicator=True)
    both = m[m["_merge"] == "both"]
    trans = pd.crosstab(both["status_earlier"], both["status_now"])
    out["lifecycle_between_pulls"] = {
        "earlier_pull_job_items": int(len(E)), "now_job_items": int(len(P)), "in_both": int(len(both)),
        "left_the_table": int((m["_merge"] == "left_only").sum()), "new_in_table": int((m["_merge"] == "right_only").sum()),
        "transitions": {a: {b: int(trans.loc[a, b]) for b in trans.columns} for a in trans.index},
        "reverse_transitions": int(trans.loc["Printed"].drop("Printed").sum() + trans.loc["Released"].get("open", 0)) if {"Printed", "Released"} <= set(trans.index) else None}

    closed = P["other_rows_qty"] >= P["planned_qty"]
    out["C2b_open_by_receipts"] = {
        "finished_orders_with_receipts_reaching_plan_pct": _pct(closed[P["finished"]].mean()),
        "unfinished_overdue_orders_with_receipts_reaching_plan_pct": _pct(closed[~P["finished"] & (P["days_past_planned"] > t["coverage_overdue_days"])].mean()),
        "orders_open_by_receipts": int((~closed).sum()), "of_which_without_any_receipt_row_pct": _pct((P.loc[~closed, "n_other_rows"] == 0).mean()),
        "of_which_past_planned_by_more_than_stale_days_pct": _pct((P.loc[~closed, "days_past_planned"] > t["stale_days"]).mean()),
        "plan_items_orders_open_by_receipts": int((~closed & P["item"].isin(plan_items)).sum())}
    out["C2b_pass"] = bool(closed[P["finished"]].mean() >= t["min_finished_closed_share"])

    def month_gap(frame):
        f = frame[frame["finished"]]
        g = (f["final_last"].dt.to_period("M") - f["end_date"].dt.to_period("M")).apply(lambda x: x.n)
        return {"n_finished": int(len(f)), "same_month_pct": _pct((g == 0).mean()), "within_one_month_pct": _pct((g.abs() <= 1).mean())}
    out["C1_supplement_month_level"] = {"all_items": month_gap(P), "plan_items": month_gap(P[P["item"].isin(plan_items)])}

    way = {"C2 status": out["C2_pass"], "C2b receipts": out["C2b_pass"], "C3 missing final record": out["C3_pass"]}
    out["usable"] = bool(out["C1_pass"] and any(way.values()))
    out["n_open_by_status_plan_items"] = out["C2_open_by_status"]["plan_items_orders"]
    if out["usable"]:
        out["verdict"] = "usable: the planned finish holds and " + ", ".join(k for k, ok in way.items() if ok) + " identifies open orders"
    else:
        why = []
        if not out["C1_pass"]:
            why.append("the planned finish does not hold (C1)")
        if not any(way.values()):
            why.append("no way of telling an open order passes (" + "; ".join(way) + ")")
        out["verdict"] = "not usable: " + " and ".join(why)
    return out


def main(today: str = None, out_path: str = None) -> dict:
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["operation_plan"]
    t = cfg["open_orders_test"]
    base = os.path.join(PROJECT_ROOT, *t["plan_row_inputs_dir"].split("/"))
    po = pd.read_csv(os.path.join(base, t["prodorder_file"]))
    cf = pd.read_csv(os.path.join(base, t["cube_final_file"]))
    earlier = pd.read_csv(os.path.join(PROJECT_ROOT, *t["earlier_prodorder_file"].split("/")))
    import operation_plan as op
    page = op.read_page_data(os.path.join(PROJECT_ROOT, *cfg["inventory_page_file"].split("/")))
    plan_items = {it["code"] for d in cfg["divisions"] for it in page["divisions"][d]["items"]}
    today_ts = pd.Timestamp(today) if today else pd.Timestamp(datetime.now().date())
    res = run_test(po, cf, earlier, cfg, today_ts, plan_items)
    res["inputs"] = {n: hashlib.sha256(open(os.path.join(base, n), "rb").read()).hexdigest() for n in (t["prodorder_file"], t["cube_final_file"])}
    out_path = out_path or os.path.join(PROJECT_ROOT, *cfg["open_orders_test_file"].split("/"))
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=str)
        f.write("\n")
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else None), indent=1, ensure_ascii=False, default=str))
