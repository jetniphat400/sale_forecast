"""Forward-test scores, on the SAME definition as the backtest (task C-fix, METRICS.md Sec.13/25/27).

How the backtest aggregates (src/backtest_rekeyed.py::compute_metrics, lines 105-116, and
src/transferability_all_divisions.py::run_transferability_rolling_origin, then the per-division
groupby-mean in its __main__):
  * an item is scored only if its series has the full length and a non-zero sum;
  * per item and window: errors = forecast - actual; MAE = mean|e|; RMSE = sqrt(mean e^2);
    Bias = mean e; MASE = MAE / scale, scale = mean |first difference| of the series the forecast was
    fitted on (NaN when the scale is 0);
  * per division: the plain mean of those per-item values (an undefined MASE is left out of its mean,
    never set to 0 or infinity).
Forward-test scoring uses exactly that: the same compute_metrics, the same item rule, the same
per-division mean. The only difference is the window: a backtest window is the six forecast months of an
origin; a forward score is one (vintage, target month, horizon) at a time, so a vintage's six horizons
are six separate records and are never pooled.

The fit series of a vintage (months fit_first_month..fit_last_month of its own metadata) is rebuilt from
output/data/raw_all_divisions_sales.csv, the raw sales pull, by the rule load_data_all_divisions.py uses:
rows with a forecast_date on or after createDate, month = calendar month of forecast_date, quantities
summed per item per month, empty months zero.

Scores are appended to output/summary/forward_test_scores.csv, an append-only record; each batch of rows
(one scoring run) has an integrity hash in forward_test_scores_integrity.json, computed after the rows
were written and read back as text, and re-checked before anything is appended. Existing rows are never edited.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_rekeyed import compute_metrics

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SCORES_PATH = os.path.join(SUMMARY_DIR, "forward_test_scores.csv")
INTEGRITY_PATH = os.path.join(SUMMARY_DIR, "forward_test_scores_integrity.json")
RAW_HISTORY_PATH = os.path.join(DATA_DIR, "raw_all_divisions_sales.csv")
FOCUS_CODES = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
DEFINITION = "backtest_item_mean_v1"
SCORE_COLUMNS = ["score_run_id", "vintage_id", "scope", "key", "target_month", "horizon", "n_items", "n_mase_defined",
                 "MAE", "RMSE", "RMSE_pooled", "Bias", "MASE", "definition", "fit_first_month", "fit_last_month", "recorded_at"]
KEY_COLUMNS = ["vintage_id", "scope", "key", "target_month", "horizon"]
HASH_COLUMNS = [c for c in SCORE_COLUMNS if c != "recorded_at"]


class ScoreRecordError(Exception):
    """The score record failed its integrity check, or a score could not be computed from its inputs."""


def fit_series_from_raw(raw: pd.DataFrame, codes, fit_first: str, fit_last: str) -> dict:
    """{itemcode: monthly quantity array over fit_first..fit_last} (see the module docstring for the rule)."""
    d = raw.copy()
    d["createDate"] = pd.to_datetime(d["createDate"])
    d["forecast_date"] = pd.to_datetime(d["forecast_date"], errors="coerce")
    d = d[d["forecast_date"].notna() & (d["forecast_date"] >= d["createDate"])]
    d["year_month"] = d["forecast_date"].dt.to_period("M").astype(str)
    months = [str(p) for p in pd.period_range(fit_first, fit_last, freq="M")]
    grid = (d[d["itemcode"].isin(set(codes)) & d["year_month"].isin(months)]
            .groupby(["itemcode", "year_month"])["qty"].sum().unstack(fill_value=0.0)
            .reindex(index=sorted(codes), columns=months, fill_value=0.0))
    return {code: grid.loc[code].to_numpy(dtype=float) for code in grid.index}


def score_items(rows: pd.DataFrame, series: dict) -> pd.DataFrame:
    """Per-item metrics for rows holding one horizon of one vintage (columns itemcode, division, forecast_qty,
    actual_qty). An item is left out when its fit series is all zero (the backtest's own rule)."""
    out = []
    for _, r in rows.iterrows():
        fit = series.get(r["itemcode"])
        if fit is None or float(np.sum(fit)) == 0.0:
            continue
        m = compute_metrics(np.array([float(r["actual_qty"])]), np.array([float(r["forecast_qty"])]), fit)
        out.append({"itemcode": r["itemcode"], "division": r["division"], "model": r.get("model", ""), **m})
    return pd.DataFrame(out, columns=["itemcode", "division", "model", "MAE", "RMSE", "Bias", "MASE"])


def _summary_row(per_item: pd.DataFrame, **ids) -> dict:
    return {**ids, "n_items": int(len(per_item)), "n_mase_defined": int(per_item["MASE"].notna().sum()),
            "MAE": float(per_item["MAE"].mean()), "RMSE": float(per_item["RMSE"].mean()),
            # METRICS Sec.25 pooled RMSE: sqrt(mean of squared errors). One forecast month per item, so the item's
            # signed error is its Bias; the backtest-style "RMSE" above (mean of per-item RMSE) is then just |error|.
            "RMSE_pooled": float(np.sqrt((per_item["Bias"] ** 2).mean())),
            "Bias": float(per_item["Bias"].mean()),
            "MASE": float(per_item["MASE"].mean()) if per_item["MASE"].notna().any() else float("nan"),
            "definition": DEFINITION}


COMPARATOR_SCOPES = {"division": "comparator_division", "focus_code": "comparator_focus_code"}


def compute_score_rows(log: pd.DataFrame, metadata: dict, raw: pd.DataFrame, run_id: str, comparator: bool = False) -> pd.DataFrame:
    """Score rows for every (vintage, target month, horizon) whose Item rows all have an actual_qty. With comparator=True `log` is
    the moving-average comparator log: the same metrics and rules, recorded under the scopes 'comparator_division' and
    'comparator_focus_code' with key '<division or code>|<model>' (for example 'PEM101|MA12'), so the existing score rows,
    their keys and their batch hashes are untouched."""
    item_rows = log[(log["level"] == "Item")].copy()
    item_rows["actual_num"] = pd.to_numeric(item_rows["actual_qty"], errors="coerce")
    records = []
    for (vid, tm, h), g in item_rows.groupby(["vintage_id", "target_month", "horizon"]):
        if g["actual_num"].isna().any():
            continue                       # not fully scored yet
        vmeta = metadata[str(int(vid))]
        series = fit_series_from_raw(raw, g["itemcode"].unique(), vmeta["fit_first_month"], vmeta["fit_last_month"])
        g = g.assign(actual_qty=g["actual_num"])
        per_item = score_items(g, series)
        if per_item.empty:
            continue
        common = {"score_run_id": run_id, "vintage_id": int(vid), "target_month": tm, "horizon": int(h),
                  "fit_first_month": vmeta["fit_first_month"], "fit_last_month": vmeta["fit_last_month"]}
        for division, d in per_item.groupby("division"):
            key = f"{division}|{d['model'].iloc[0]}" if comparator else division
            records.append(_summary_row(d, scope=COMPARATOR_SCOPES["division"] if comparator else "division", key=key, **common))
        for code in FOCUS_CODES:
            d = per_item[per_item["itemcode"] == code]
            if len(d):
                key = f"{code}|{d['model'].iloc[0]}" if comparator else code
                records.append(_summary_row(d, scope=COMPARATOR_SCOPES["focus_code"] if comparator else "focus_code", key=key, **common))
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=SCORE_COLUMNS)
    df["recorded_at"] = datetime.now().isoformat(timespec="seconds")
    return df[SCORE_COLUMNS]


# ---------------------------------------------------------------- shadow forecasts (METRICS.md Sec.51)
SHADOW_SCOPE = "shadow_group"
SHADOW_DEFINITION = "shadow_group_series_v1"


def scoreable_run_date(target_month: str, margin_days: int, run_day: int):
    """The first monthly run (the run_day of a month) whose date is at least `margin_days` after the end of `target_month`: the run at which the leakage guard lets the month be scored.
    Derived, never typed; check_window_closed agrees with it (tested)."""
    d = pd.Period(target_month, freq="M").end_time.date() + timedelta(days=int(margin_days))
    while d.day != int(run_day):
        d += timedelta(days=1)
    return d


def decide_rule(holt_mae: list, current_mae: list, rule: dict) -> dict:
    """The pre-registered decision (config shadow.rule, METRICS.md Sec.51) on the MAE of each target month, in the same month order: 'recommend_switch' only if Holt's MAE is lower than current's in at
    least rule.min_months_holt_lower months (a tie is not lower) AND, when rule.sum_must_be_lower, Holt's summed MAE is lower than current's; otherwise 'keep_current'."""
    n_lower = sum(1 for h, c in zip(holt_mae, current_mae) if h < c)
    sum_lower = sum(holt_mae) < sum(current_mae)
    ok = n_lower >= int(rule["min_months_holt_lower"]) and (sum_lower or not rule["sum_must_be_lower"])
    return {"months_holt_lower": n_lower, "holt_sum": float(sum(holt_mae)), "current_sum": float(sum(current_mae)), "sum_lower": bool(sum_lower),
            "outcome": rule["outcome_if_true"] if ok else rule["outcome_otherwise"]}


def shadow_score_rows(shadow_log: pd.DataFrame, production_log: pd.DataFrame, shadow_metadata: dict, config: dict, run_id: str, now, min_margin_days: int) -> pd.DataFrame:
    """Score rows of the shadow forecasts, recorded in the score record under scope 'shadow_group': for each (vintage, target month, horizon) of each shadow group, the absolute error of the group's
    monthly total (the pilot-group MAE of the forecast page: the group series as one series) for the shadow method ('<group label>|<method>'), for the production forecast of the same items
    ('<group label>|current') and for Naive ('<group label>|Naive', the group's units in the last fit month). A month is scored ONLY if it has passed the leakage guard (check_window_closed against
    `now`): a month still inside the margin is skipped here whatever the log holds, no exception, no override. MAE = absolute error; Bias = forecast minus actual; RMSE and RMSE_pooled = the absolute error;
    MASE is not defined for a group total."""
    from leakage_guard import check_window_closed, LeakageGuardError
    from forward_test_all_divisions import SHADOW_METHODS
    labels = config["report"]["pilot_labels"]
    items = shadow_log[shadow_log["level"] == "Item"].copy()
    items["actual_num"] = pd.to_numeric(items["actual_qty"], errors="coerce")
    prod = production_log[production_log["level"] == "Item"]
    records = []
    for (vid, group, tm, h), g in items.groupby(["vintage_id", "shadow_group", "target_month", "horizon"]):
        try:
            check_window_closed(tm, now, min_margin_days)
        except LeakageGuardError:
            continue
        if g["actual_num"].isna().any():
            continue
        vmeta = shadow_metadata[str(int(vid))]
        method_label = SHADOW_METHODS[g["method"].iloc[0]][0]
        p = prod[(prod["vintage_id"] == vid) & (prod["target_month"] == tm) & (prod["horizon"] == h) & prod["itemcode"].isin(g["itemcode"])]
        if len(p) != len(g):
            raise ScoreRecordError(f"shadow vintage {vid} {tm}: the production log holds {len(p)} rows for the {len(g)} shadow items")
        actual = float(g["actual_num"].sum())
        fcs = {method_label: float(g["forecast_qty"].sum()), "current": float(p["forecast_qty"].sum()), "Naive": float(vmeta["naive_last_fit_month_units"][group])}
        for name, fc in fcs.items():
            err = fc - actual
            records.append({"score_run_id": run_id, "vintage_id": int(vid), "scope": SHADOW_SCOPE, "key": f"{labels[group]}|{name}", "target_month": tm, "horizon": int(h),
                            "n_items": int(len(g)), "n_mase_defined": 0, "MAE": abs(err), "RMSE": abs(err), "RMSE_pooled": abs(err), "Bias": err, "MASE": float("nan"),
                            "definition": SHADOW_DEFINITION, "fit_first_month": vmeta["fit_first_month"], "fit_last_month": vmeta["fit_last_month"]})
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=SCORE_COLUMNS)
    df["recorded_at"] = datetime.now().isoformat(timespec="seconds")
    return df[SCORE_COLUMNS]


def shadow_rule_status(config: dict, scores_path: str = SCORES_PATH) -> dict:
    """The status of the pre-registered rule for each shadow pair, from the score record only: per target month the MAE of the shadow method and of current (vintage `rule.vintage_compared` only),
    the run date on which the month becomes scoreable (derived from the guard and the monthly run day), the evaluation run (the latest of those) and the outcome once all months are scored, else
    'pending'. Also, over every scored shadow point of every vintage (vintage 3 and later are recorded but do not count toward the rule): Relative MAE against Naive and the Tracking Signal
    (None until shadow.min_points_tracking_signal points exist). Nothing is adopted: the outcome is a recommendation."""
    from forward_test_all_divisions import SHADOW_METHODS
    sh, rule = config["shadow"], config["shadow"]["rule"]
    margin, day = int(config["leakage_guard"]["min_margin_days"]), int(sh["monthly_run_day_of_month"])
    rows = _read_text(scores_path)
    rows = rows[rows["scope"] == SHADOW_SCOPE] if len(rows) else rows
    months = list(rule["target_months"])
    runs = {m: scoreable_run_date(m, margin, day) for m in months}
    out = {}
    for group, method in sh["pairs"].items():
        label, mname = config["report"]["pilot_labels"][group], SHADOW_METHODS[method][0]
        g = rows[rows["key"].str.startswith(label + "|")] if len(rows) else rows

        def val(vintage, month, name):
            m = g[(g["vintage_id"] == str(vintage)) & (g["target_month"] == month) & (g["key"] == f"{label}|{name}")] if len(g) else g
            return float(m["MAE"].iloc[0]) if len(m) else None
        per_month = []
        for m in months:
            h, c = val(rule["vintage_compared"], m, mname), val(rule["vintage_compared"], m, "current")
            per_month.append({"month": m, "holt_mae": h, "current_mae": c, "scored": h is not None and c is not None, "scoreable_run": str(runs[m])})
        scored = [p for p in per_month if p["scored"]]
        res = {"group": group, "label": label, "method": mname, "months": per_month, "n_scored": len(scored), "n_months": len(months),
               "evaluation_run": str(max(runs.values())), "state": "pending", "outcome": None}
        if len(scored) == len(months):
            d = decide_rule([p["holt_mae"] for p in per_month], [p["current_mae"] for p in per_month], rule)
            res.update({"state": "evaluated", "outcome": d["outcome"], "decision": d})
        pts = g[g["key"] == f"{label}|{mname}"] if len(g) else g
        keyed = {(r.vintage_id, r.target_month, r.horizon): r for r in pts.itertuples()}
        naive = {(r.vintage_id, r.target_month, r.horizon): float(r.MAE) for r in g[g["key"] == f"{label}|Naive"].itertuples()} if len(g) else {}
        both = [k for k in keyed if k in naive]
        nsum = sum(naive[k] for k in both)
        res["relative_mae_vs_naive"] = (sum(float(keyed[k].MAE) for k in both) / nsum) if both and nsum > 0 else None
        errs = [float(keyed[k].Bias) for k in sorted(keyed, key=lambda k: (k[1], k[2]))]
        mean_abs = sum(abs(e) for e in errs) / len(errs) if errs else 0.0
        res["n_points"] = len(errs)
        res["tracking_signal"] = (sum(errs) / mean_abs) if len(errs) >= int(sh["min_points_tracking_signal"]) and mean_abs > 0 else None
        out[group] = res
    return out


# ---------------------------------------------------------------- Naive on the scored forward months (METRICS.md Sec.48)
def forward_naive_items(log: pd.DataFrame, metadata: dict, raw: pd.DataFrame) -> pd.DataFrame:
    """One row per scored item (horizon 1, every vintage and target month whose Item rows all have an actual_qty), for the items the score itself uses (score_items: the fit series is not all zero):
    columns vintage_id, target_month, division, type, itemcode, forecast, actual, naive (the quantity of the last month of the vintage's fit window), e_model (forecast - actual),
    e_naive (naive - actual). Nothing is written; the score record is not touched."""
    item_rows = log[(log["level"] == "Item") & (log["horizon"] == 1)].copy()
    item_rows["actual_num"] = pd.to_numeric(item_rows["actual_qty"], errors="coerce")
    out = []
    for (vid, tm), g in item_rows.groupby(["vintage_id", "target_month"]):
        if g["actual_num"].isna().any():
            continue
        vmeta = metadata[str(int(vid))]
        series = fit_series_from_raw(raw, g["itemcode"].unique(), vmeta["fit_first_month"], vmeta["fit_last_month"])
        used = set(score_items(g.assign(actual_qty=g["actual_num"]), series)["itemcode"])
        for r in g[g["itemcode"].isin(used)].itertuples():
            naive = float(series[r.itemcode][-1])
            out.append({"vintage_id": int(vid), "target_month": tm, "division": r.division, "type": r.type, "itemcode": r.itemcode, "forecast": float(r.forecast_qty),
                        "actual": float(r.actual_num), "naive": naive, "e_model": float(r.forecast_qty) - float(r.actual_num), "e_naive": naive - float(r.actual_num)})
    return pd.DataFrame(out, columns=["vintage_id", "target_month", "division", "type", "itemcode", "forecast", "actual", "naive", "e_model", "e_naive"])


def forward_naive_by_division(items: pd.DataFrame) -> pd.DataFrame:
    """Per vintage, target month and division: n_items, MAE (model), MAE_naive, relative_mae (sum |model e| / sum |Naive e|, None when Naive's errors are all 0) and e_total (sum of forecast - actual)."""
    rows = []
    for (vid, tm, div), g in items.groupby(["vintage_id", "target_month", "division"]):
        sm, sn = float(g["e_model"].abs().sum()), float(g["e_naive"].abs().sum())
        rows.append({"vintage_id": vid, "target_month": tm, "division": div, "n_items": len(g), "MAE": sm / len(g), "MAE_naive": sn / len(g),
                     "relative_mae": (sm / sn) if sn > 0 else None, "e_total": float(g["e_model"].sum())})
    return pd.DataFrame(rows, columns=["vintage_id", "target_month", "division", "n_items", "MAE", "MAE_naive", "relative_mae", "e_total"])


# ---------------------------------------------------------------- the append-only record

def _batch_hash(rows_text: pd.DataFrame) -> str:
    """sha256 over the text of the batch's rows (sorted by key), HASH_COLUMNS only, as read back from the file."""
    df = rows_text.sort_values(KEY_COLUMNS).reset_index(drop=True)
    lines = ["|".join(str(df.at[i, c]) for c in HASH_COLUMNS) for i in range(len(df))]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _read_text(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False) if os.path.exists(path) else pd.DataFrame(columns=SCORE_COLUMNS)


def verify_score_record(scores_path: str = SCORES_PATH, integrity_path: str = INTEGRITY_PATH) -> int:
    """Re-computes every batch's hash from the file as it is now; raises ScoreRecordError on any difference.
    Returns the number of batches verified."""
    rows = _read_text(scores_path)
    integrity = json.load(open(integrity_path, encoding="utf-8")) if os.path.exists(integrity_path) else {"batches": {}}
    batches = integrity["batches"]
    seen = set()
    for run_id, g in rows.groupby("score_run_id"):
        seen.add(run_id)
        rec = batches.get(run_id)
        if rec is None:
            raise ScoreRecordError(f"score rows of run {run_id} have no recorded integrity hash")
        if len(g) != rec["n_rows"] or _batch_hash(g) != rec["hash"]:
            raise ScoreRecordError(f"score record batch {run_id}: rows differ from the hash recorded when they were written")
    missing = set(batches) - seen
    if missing:
        raise ScoreRecordError(f"score record batches {sorted(missing)} are recorded in the integrity file but missing from the scores file")
    return len(batches)


def append_scores(new_rows: pd.DataFrame, scores_path: str = SCORES_PATH, integrity_path: str = INTEGRITY_PATH) -> dict:
    """Appends rows whose (vintage, scope, key, target month, horizon) is not yet recorded. Existing rows are verified
    first and never edited. The batch hash is taken from the rows READ BACK from the file after writing."""
    verify_score_record(scores_path, integrity_path)
    existing = _read_text(scores_path)
    have = set(map(tuple, existing[KEY_COLUMNS].astype(str).to_numpy())) if len(existing) else set()
    fresh = new_rows[[tuple(map(str, r)) not in have for r in new_rows[KEY_COLUMNS].to_numpy()]]
    if fresh.empty:
        return {"appended": 0, "skipped_already_recorded": len(new_rows)}
    run_id = str(fresh["score_run_id"].iloc[0])
    if run_id in set(existing.get("score_run_id", [])):
        raise ScoreRecordError(f"run {run_id} already has a batch in the record; a batch is written once")
    os.makedirs(os.path.dirname(scores_path), exist_ok=True)
    before = len(existing)
    fresh.to_csv(scores_path, mode="a", header=not os.path.exists(scores_path) or before == 0, index=False)
    back = _read_text(scores_path)
    batch_back = back[back["score_run_id"] == run_id]
    if len(batch_back) != len(fresh) or len(back) != before + len(fresh):
        raise ScoreRecordError("the scores file did not read back as written")
    integrity = json.load(open(integrity_path, encoding="utf-8")) if os.path.exists(integrity_path) else {"batches": {}}
    integrity["batches"][run_id] = {"n_rows": int(len(batch_back)), "hash": _batch_hash(batch_back),
                                    "scheme": "text_of_hash_columns_read_back_v1", "recorded_at": datetime.now().isoformat(timespec="seconds")}
    with open(integrity_path, "w", encoding="utf-8") as f:
        json.dump(integrity, f, indent=2)
    verify_score_record(scores_path, integrity_path)
    return {"appended": int(len(fresh)), "skipped_already_recorded": int(len(new_rows) - len(fresh)), "batch_hash": integrity["batches"][run_id]["hash"]}


def record_scores(log: pd.DataFrame, metadata: dict, run_id: str, raw_path: str = RAW_HISTORY_PATH,
                  scores_path: str = SCORES_PATH, integrity_path: str = INTEGRITY_PATH,
                  comparator_log: pd.DataFrame = None, comparator_metadata: dict = None, shadow: dict = None) -> dict:
    """Computes the scores of every fully-actualised (vintage, target month, horizon) and appends the unrecorded ones. When a
    moving-average comparator log is given its months are scored the same way and appended in the same batch; `shadow` ({log, metadata, config, now, min_margin_days}) adds the
    shadow forecasts' group scores (shadow_score_rows), guard-checked against `now`."""
    if not os.path.exists(raw_path):
        raise ScoreRecordError(f"{raw_path} is missing: it is the history the fit series are rebuilt from")
    raw = pd.read_csv(raw_path)
    rows = compute_score_rows(log, metadata, raw, run_id)
    if comparator_log is not None and len(comparator_log):
        cmp_rows = compute_score_rows(comparator_log, comparator_metadata, raw, run_id, comparator=True)
        rows = pd.concat([rows, cmp_rows], ignore_index=True) if len(rows) else cmp_rows
    if shadow is not None and len(shadow["log"]):
        sh_rows = shadow_score_rows(shadow["log"], log, shadow["metadata"], shadow["config"], run_id, shadow["now"], shadow["min_margin_days"])
        rows = pd.concat([rows, sh_rows], ignore_index=True) if len(rows) else sh_rows
    return append_scores(rows, scores_path, integrity_path) if len(rows) else {"appended": 0, "skipped_already_recorded": 0}
