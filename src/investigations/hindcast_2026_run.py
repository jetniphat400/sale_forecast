"""Runs the 2026 hindcast (Prompt 64 step 3) on the monthly series of a kept temporary copy of the project: `python src/investigations/hindcast_2026_run.py <copy root>`.

Reads: the copy's monthly series, scope file and sale series (the fresh pull of the dry run), the real project's saved backtest choice of the moving-average windows and its forward-test log (read only).
Writes: output/summary/hindcast_2026_forecasts.csv (every simulated forecast row, untracked), output/summary/hindcast_2026_tables/*.csv (untracked) and the two charts in docs/reports/summary.
Nothing else: the config file is hashed before and after and the run stops if it changed."""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import hindcast_2026 as hc  # noqa: E402

PROJECT_ROOT = hc.PROJECT_ROOT
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "summary", "hindcast_2026_tables")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs", "reports", "summary")
DIVISIONS = ["CI101", "PEM101", "PEM102", "PEM103", "PEM107"]


def step5_item_rows_in_copy(copy_root: str) -> pd.DataFrame:
    """Runs step 5's own `compute_new_vintage()` inside the copy (it only computes: nothing is written) and returns its Item rows."""
    code = ("import sys,json; sys.path.insert(0,'src'); import monthly_refresh as mr; c=mr.compute_new_vintage(); df=c['rows_df']; "
            "df=df[df['level']=='Item'][['itemcode','horizon','forecast_qty']]; print('JSONSTART'+df.to_json(orient='records'))")
    p = subprocess.run([sys.executable, "-c", code], cwd=copy_root, capture_output=True, text=True, encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = p.stdout
    if "JSONSTART" not in out:
        raise hc.HindcastError("step 5's compute_new_vintage did not return rows in the copy: " + (p.stderr or out)[-800:])
    return pd.DataFrame(json.loads(out.split("JSONSTART", 1)[1].strip().splitlines()[0]))


def canary(monthly: pd.DataFrame, scope: pd.DataFrame, windows: dict) -> dict:
    """Changes every value AFTER the origin's fit month (times 7, plus a spike) and runs the same origin again: the forecast must not move by a single digit."""
    fit_last = "2025-11"
    base = hc.forecast_run(monthly, scope, fit_last, 6, windows)
    bad = monthly.copy()
    after = bad["year_month"] > fit_last
    bad.loc[after, "qty"] = bad.loc[after, "qty"] * 7 + 1000
    again = hc.forecast_run(bad, scope, fit_last, 6, windows)
    diff = float((base[["f_topdown", "f_naive", "f_ma"]].to_numpy() - again[["f_topdown", "f_naive", "f_ma"]].to_numpy()).__abs__().max())
    if diff != 0.0:
        raise hc.HindcastError(f"canary failed: values after the fit month moved the forecast by {diff}")
    return {"origin_fit_last": fit_last, "values_changed_after": int(after.sum()), "max_abs_forecast_change": diff}


def main(copy_root: str) -> dict:
    cfg_path = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    hash_before = hc.sha256_file(cfg_path)
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    import ma_comparator
    import reader_values as rv
    from leakage_guard import load_min_margin_days
    margin = load_min_margin_days(cfg)
    monthly = pd.read_csv(os.path.join(copy_root, "output", "data", "processed_all_divisions_monthly_qty.csv"))
    scope = pd.read_csv(os.path.join(copy_root, "output", "summary", "phaseC_step2_scope_335items.csv"))
    if len(scope) != 335 or monthly["itemcode"].nunique() != 335:
        raise hc.HindcastError(f"the scope is not the 335 items: scope {len(scope)}, series {monthly['itemcode'].nunique()}")
    windows = ma_comparator.chosen_windows(ma_comparator.current_choice(cfg))
    result = {"pull_date": str(monthly["snapshot_pull_date"].iloc[0]), "months": [monthly["year_month"].min(), monthly["year_month"].max()], "margin_days": margin,
              "ma_windows_by_division": windows, "n_scope_items": int(len(scope))}

    result["step5_equivalence"] = hc.check_driver_against_step5(monthly, scope, windows, step5_item_rows_in_copy(copy_root))
    if result["step5_equivalence"]["unmatched"] or result["step5_equivalence"]["max_abs_difference"] > 1e-3:
        raise hc.HindcastError(f"the driver does not reproduce step 5: {result['step5_equivalence']}")
    result["canary"] = canary(monthly, scope, windows)

    sim = hc.simulate(monthly, scope, windows, margin)
    # one fixed price per item (the executive tab's price chain, on the fit window of the full fresh series), applied to actual AND forecast
    basis = cfg["report"]["price_basis"]
    codes = sorted(scope["code"].unique())
    info = rv.unit_prices(codes, basis, monthly["year_month"].min(), monthly["year_month"].max(), os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx"), copy_root)
    prices = {c: (v["price"] if v and v["price"] is not None else np.nan) for c, v in info["prices"].items()}
    result["price_sources"] = pd.Series([(v or {}).get("source", "none") for v in info["prices"].values()]).value_counts().to_dict()
    df = hc.attach_actuals_and_prices(sim, monthly, prices)
    df["no_price"] = df["price"].isna()
    result["items_without_price"] = int(df.loc[df["no_price"], "item"].nunique())
    df.loc[df["no_price"], "price"] = 0.0          # an item with no price (none in the saved series nor the Price List) has no baht value: it adds 0 baht to a total and is listed above

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(os.path.join(PROJECT_ROOT, "output", "summary", "hindcast_2026_forecasts.csv"), index=False, encoding="utf-8")

    # items with no history before each run's fit month
    nh = (sim.groupby(["family", "run_month", "fit_last_month"]).apply(lambda g: int((g.drop_duplicates("item")["history_months_nonzero"] == 0).sum()), include_groups=False)
          .rename("items_with_no_nonzero_history").reset_index())
    nh.to_csv(os.path.join(OUT_DIR, "no_history_per_run.csv"), index=False)
    runs = sim.drop_duplicates(["family", "run_month"])[["family", "run_month", "run_date", "fit_last_month"]]
    runs.to_csv(os.path.join(OUT_DIR, "runs.csv"), index=False)

    scored = df[(df["target_month"] >= hc.FIRST_SCORED_MONTH) & (df["target_month"] <= hc.LAST_SCORED_MONTH) & df["division"].isin(DIVISIONS)]
    a = scored[scored["family"] == "A"]
    main = hc.main_line(a)
    result["main_line_horizon_values"] = sorted(main["horizon"].unique().tolist())
    tables = {
        "A_main_item_by_division": hc.item_level_table(main, ["division"]),
        "A_main_item_company": hc.item_level_table(main.assign(division="COMPANY"), ["division"]),
        "A_by_horizon_item_company": hc.item_level_table(a.assign(division="COMPANY"), ["division", "horizon"]),
        "A_by_horizon_item_by_division": hc.item_level_table(a, ["division", "horizon"]),
        "B_by_horizon_item_company": hc.item_level_table(scored[scored["family"] == "B"].assign(division="COMPANY"), ["division", "horizon"]),
        "B_by_division": hc.item_level_table(scored[scored["family"] == "B"], ["division"]),
        "A_main_totals_monthly": hc.totals_by_month(main),
        "B_totals_monthly": hc.totals_by_month(scored[scored["family"] == "B"]),
    }
    tables["A_main_totals_summary"] = hc.totals_summary(tables["A_main_totals_monthly"])
    tables["B_totals_summary"] = hc.totals_summary(tables["B_totals_monthly"])

    # the real vintages (the only true out-of-sample points), read from the forward-test log; Naive and MA computed from the fresh series cut at the vintage's own fit month (labelled simulated)
    log = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "summary", "forward_test_log_all_divisions.csv"))
    real_rows, restate = [], []
    for vid in sorted(log["vintage_id"].unique()):
        v = log[(log["vintage_id"] == vid) & (log["level"] == "Item")]
        fit_last = str(v["fit_last_month"].iloc[0])
        mine = hc.forecast_run(monthly, scope, fit_last, 6, windows)
        m = mine.merge(v[["itemcode", "horizon", "forecast_qty", "target_month"]].rename(columns={"itemcode": "item"}), on=["item", "horizon", "target_month"], how="inner")
        restate.append({"vintage_id": int(vid), "fit_last_month": fit_last, "run_date": str(v["forecast_run_date"].iloc[0]), "items": int(m["item"].nunique()),
                        "max_abs_diff_driver_vs_logged_topdown": float((m["f_topdown"] - m["forecast_qty"]).abs().max()), "n_rows_differing_over_0.001": int(((m["f_topdown"] - m["forecast_qty"]).abs() > 1e-3).sum())})
        m["f_topdown"] = m["forecast_qty"]                    # the real, logged Top-down forecast
        real_rows.append(m.drop(columns=["forecast_qty"]).assign(vintage_id=int(vid), fit_last_month=fit_last))
    real = pd.concat(real_rows, ignore_index=True)
    real = hc.attach_actuals_and_prices(real, monthly, prices)
    real["price"] = real["price"].fillna(0.0)
    real = real[real["actual"].notna() & real["division"].isin(DIVISIONS)]
    tables["real_vintages_item_by_vintage_horizon"] = hc.item_level_table(real.assign(division="COMPANY"), ["division", "vintage_id", "horizon"])
    tables["real_vintages_totals"] = real.groupby(["vintage_id", "target_month", "horizon"]).apply(
        lambda g: pd.Series({"n_items": g["item"].nunique(), "actual_baht": (g["actual"] * g["price"]).sum(), "topdown_baht": (g["f_topdown"] * g["price"]).sum(),
                             "naive_baht": (g["f_naive"] * g["price"]).sum(), "ma_baht": (g["f_ma"] * g["price"]).sum()}), include_groups=False).reset_index()
    tables["real_vintages_totals_by_division"] = real.groupby(["vintage_id", "target_month", "division"]).apply(
        lambda g: pd.Series({"n_items": g["item"].nunique(), "actual_baht": (g["actual"] * g["price"]).sum(), "topdown_baht": (g["f_topdown"] * g["price"]).sum()}), include_groups=False).reset_index()
    result["restatement_check"] = restate

    for name, t in tables.items():
        t.to_csv(os.path.join(OUT_DIR, name + ".csv"), index=False)
    hash_after = hc.assert_unchanged(cfg_path, hash_before)
    result["config_sha256_before"], result["config_sha256_after"] = hash_before, hash_after
    result["no_history"] = nh.to_dict("records")
    result["runs"] = runs.to_dict("records")
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    return result


if __name__ == "__main__":
    r = main(sys.argv[1])
    print(json.dumps({k: r[k] for k in ("pull_date", "months", "step5_equivalence", "canary", "main_line_horizon_values", "items_without_price", "price_sources", "restatement_check", "config_sha256_after")}, ensure_ascii=False, indent=1, default=str))
