"""Phase J3 -- Validator reconciliation task.

Part A: reconcile Phase J's actual_on_time (97.8%, PEM101, METRICS.md Sec.18,
src/investigations/phaseJ_calibration.py::compute_actual_on_time) against Phase J2's not_late
(87.9%, PEM101, unit-weighted, METRICS.md Sec.19, src/investigations/phaseJ2_not_late_recompute.py)
by isolating every methodological difference between the two scripts on the SAME cached data,
one difference at a time.

Part B: reconciled not_late targets (METRICS.md Sec.19, both weightings), calibration period
(2024-01-01 to 2025-12-31) and validation period (2026-01-01 onward), per division, due-date field
= ForecastDelDate (METRICS.md Sec.18/19 convention -- NOT Phase J2's CtrDate calendar year, which
Part A shows is what caused the discrepancy).

Part C: current on-hand stock value per division (Cube_Inventory_Exact is a single-refresh
snapshot -- DATA_MAP.md Sec.1 -- so this is CURRENT value, not a time-averaged figure).

NO new database query. Reuses:
  output/data/phaseJ_cube_ces_351items.csv        (Cube_CES, 351-item scope, no date filter at pull)
  output/data/phaseI_combined_scope_351items.csv  (item -> division mapping, pricelist-sourced)
  output/data/phaseI_inventory_exact_351items.csv (Cube_Inventory_Exact, 351-item scope)
  output/data/phaseI_raw_sales_351items.csv       (cube_Sale_APD, 351-item scope, for unit_cost)
and imports (does not reimplement) phaseI_sensitivity_engine.compute_unit_cost_from_raw and
phaseE1_common.sellable_stock_per_item, per task instruction.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT, load_config, sellable_stock_per_item
from phaseI_sensitivity_engine import compute_unit_cost_from_raw

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CES_FILE = os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv")
SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")
INV_FILE = os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv")
RAW_FILE = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")

DIVISIONS = ["PEM101", "PEM103", "PEM107"]


def load_ces_with_division():
    ces = pd.read_csv(CES_FILE)
    scope = pd.read_csv(SCOPE_FILE)
    code_to_division = dict(zip(scope["code"], scope["division"]))
    ces["CtrDate"] = pd.to_datetime(ces["CtrDate"], errors="coerce")
    ces["ForecastDelDate"] = pd.to_datetime(ces["ForecastDelDate"], errors="coerce")
    ces["ActualDelDate"] = pd.to_datetime(ces["ActualDelDate"], errors="coerce")
    ces["division"] = ces["ItemCode"].map(code_to_division)
    return ces, scope


def classify(days):
    if pd.isna(days):
        return None
    if days == 0:
        return "on_time_exact"
    return "early" if days < 0 else "late"


def weighted_shares(df: pd.DataFrame, weight_col: str = None) -> dict:
    if weight_col is None:
        w = pd.Series(1.0, index=df.index)
    else:
        w = df[weight_col].astype(float)
    total = w.sum()
    if total <= 0:
        return {"on_time_exact": np.nan, "not_late": np.nan, "late": np.nan, "n_or_units": 0.0}
    on_time = w[df["status"] == "on_time_exact"].sum()
    early = w[df["status"] == "early"].sum()
    late = w[df["status"] == "late"].sum()
    return {"on_time_exact": on_time / total, "not_late": (on_time + early) / total,
            "late": late / total, "n_or_units": total}


# ================================================================================================
# PART A -- isolate the discrepancy, PEM101, one variable at a time
# ================================================================================================

def part_a():
    ces, _ = load_ces_with_division()
    div = "PEM101"
    sub = ces[ces["division"] == div].copy()

    def unit_not_late(df):
        if len(df) == 0:
            return np.nan, 0.0
        w = df["ActualQty"].astype(float)
        total = w.sum()
        if total <= 0:
            return np.nan, 0.0
        ontime = df["ActualDelDate"] <= df["ForecastDelDate"]
        return float(w[ontime].sum() / total), float(total)

    rows = []

    # A: Phase J's exact method (compute_actual_on_time) -- ForecastDelDate window
    # 2024-01-01..2026-07-31, no explicit Status filter, require ActualDelDate notna.
    winA = sub[(sub["ForecastDelDate"] >= "2024-01-01") & (sub["ForecastDelDate"] <= "2026-07-31")].copy()
    scoredA = winA[winA["ActualDelDate"].notna()]
    v, n = unit_not_late(scoredA)
    rows.append({"variant": "A_phaseJ_exact (ForecastDelDate window, no Status filter)", "n_rows": len(scoredA),
                 "unit_weighted_not_late": v, "total_units": n})

    # A2: same window, WITH explicit Status=='Actual' filter -- tests whether the Status filter
    # (which Phase J2 applies and Phase J does not) makes any difference.
    scoredA2 = winA[(winA["ActualDelDate"].notna()) & (winA["Status"] == "Actual")]
    v, n = unit_not_late(scoredA2)
    rows.append({"variant": "A2_phaseJ_window_plus_Status_Actual_filter", "n_rows": len(scoredA2),
                 "unit_weighted_not_late": v, "total_units": n})

    # B: Phase J2's exact assessable filter (Status=='Actual', ActualDelDate & ForecastDelDate
    # notna), but windowed on ForecastDelDate identically to Phase J (isolates: does the
    # CtrDate-vs-ForecastDelDate windowing choice matter, holding the date RANGE fixed?)
    assessable = sub[(sub["Status"] == "Actual") & sub["ActualDelDate"].notna() &
                     sub["ForecastDelDate"].notna()].copy()
    winB = assessable[(assessable["ForecastDelDate"] >= "2024-01-01") &
                       (assessable["ForecastDelDate"] <= "2026-07-31")]
    v, n = unit_not_late(winB)
    rows.append({"variant": "B_phaseJ2_method_ForecastDelDate_window_like_J", "n_rows": len(winB),
                 "unit_weighted_not_late": v, "total_units": n})

    # C: Phase J2's method, CtrDate YEAR 2024-2026 (drop 2023, but use full calendar years,
    # order-date keyed -- isolates the residual effect of CtrDate-year vs ForecastDelDate-window
    # bucketing, holding "2023 excluded" fixed).
    assessable["year"] = assessable["CtrDate"].dt.year
    winC = assessable[(assessable["year"] >= 2024) & (assessable["year"] <= 2026)]
    v, n = unit_not_late(winC)
    rows.append({"variant": "C_phaseJ2_method_CtrDate_year_2024_2026", "n_rows": len(winC),
                 "unit_weighted_not_late": v, "total_units": n})

    # D: Phase J2's EXACT published figure -- CtrDate year 2023-2026 (includes 2023).
    winD = assessable[(assessable["year"] >= 2023) & (assessable["year"] <= 2026)]
    v, n = unit_not_late(winD)
    rows.append({"variant": "D_phaseJ2_exact_CtrDate_year_2023_2026 (published 87.9%)", "n_rows": len(winD),
                 "unit_weighted_not_late": v, "total_units": n})

    # E: 2023 CtrDate-year alone -- shows the poor-performing, heavily-weighted population that
    # Phase J's window excludes entirely and Phase J2's overall figure includes.
    winE = assessable[assessable["year"] == 2023]
    v, n = unit_not_late(winE)
    rows.append({"variant": "E_2023_CtrDate_year_alone", "n_rows": len(winE),
                 "unit_weighted_not_late": v, "total_units": n})

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ3_validator_partA_isolation_PEM101.csv"), index=False)
    print(df.to_string(index=False))
    return df


# ================================================================================================
# PART B -- reconciled not_late targets, ForecastDelDate window, both weightings, 3 divisions
# ================================================================================================

def part_b():
    ces, _ = load_ces_with_division()
    ces = ces[ces["division"].isin(DIVISIONS)].copy()

    assessable = ces[(ces["Status"] == "Actual") & ces["ForecastDelDate"].notna()].copy()
    assessable["delay_days"] = (assessable["ActualDelDate"] - assessable["ForecastDelDate"]).dt.days
    assessable["status"] = assessable["delay_days"].apply(classify)

    periods = {
        "calibration_2024-01-01_to_2025-12-31": ("2024-01-01", "2025-12-31"),
        "validation_2026-01-01_onward": ("2026-01-01", None),
    }

    rows = []
    excl_rows = []
    for period_name, (start, end) in periods.items():
        if end is None:
            win = assessable[assessable["ForecastDelDate"] >= start]
        else:
            win = assessable[(assessable["ForecastDelDate"] >= start) & (assessable["ForecastDelDate"] <= end)]
        for division, g in win.groupby("division"):
            n_excl = int(g["ActualDelDate"].isna().sum())
            scored = g[g["ActualDelDate"].notna()]
            row_w = weighted_shares(scored, None)
            unit_w = weighted_shares(scored, "ActualQty")
            rows.append({"period": period_name, "division": division, "weighting": "row",
                         "n_excluded_no_actualdel": n_excl, **row_w})
            rows.append({"period": period_name, "division": division, "weighting": "unit_ActualQty",
                         "n_excluded_no_actualdel": n_excl, **unit_w})
            excl_rows.append({"period": period_name, "division": division,
                              "n_rows_in_window_status_actual_forecastdel_notna": len(g),
                              "n_excluded_no_actualdel": n_excl,
                              "n_scored": len(scored)})

    result = pd.DataFrame(rows)
    excl = pd.DataFrame(excl_rows)
    result.to_csv(os.path.join(SUMMARY_DIR, "phaseJ3_validator_not_late_reconciled.csv"), index=False)
    excl.to_csv(os.path.join(SUMMARY_DIR, "phaseJ3_validator_not_late_exclusions.csv"), index=False)
    print(result.to_string(index=False))
    print(excl.to_string(index=False))
    return result, excl


# ================================================================================================
# PART C -- current on-hand stock value per division (snapshot, not a time-average)
# ================================================================================================

def part_c():
    config = load_config()
    scope = pd.read_csv(SCOPE_FILE)
    raw = pd.read_csv(RAW_FILE)
    raw["createDate"] = pd.to_datetime(raw["createDate"], errors="coerce")
    inv = pd.read_csv(INV_FILE)
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()

    sellable_map = config["phase_e1_assumptions"]["sellable_warehouse_codes"]

    rows = []
    item_rows = []
    for division in DIVISIONS:
        codes = sorted(scope.loc[scope["division"] == division, "code"].unique())
        raw_div = raw[raw["itemcode"].isin(codes)].copy()
        inv_div = inv[inv["itemcode"].isin(codes)].copy()
        sellable_wh = sellable_map[division]

        onhand = sellable_stock_per_item(inv_div, codes, sellable_wh)
        cost = compute_unit_cost_from_raw(raw_div, codes, window_months=12)

        merged = onhand.merge(cost, on="itemcode", how="left")
        merged["division"] = division
        merged["stock_value"] = np.where(merged["no_unit_cost_item"], np.nan,
                                          merged["sellable_stock"] * merged["unit_cost"])
        item_rows.append(merged)

        n_no_cost = int(merged["no_unit_cost_item"].sum())
        n_no_cost_with_stock = int((merged["no_unit_cost_item"] & (merged["sellable_stock"] > 0)).sum())
        total_value = float(merged["stock_value"].sum(skipna=True))
        total_units = float(merged["sellable_stock"].sum())
        rows.append({
            "division": division, "sellable_warehouses": ",".join(sellable_wh),
            "n_items": len(codes), "total_onhand_units": total_units,
            "current_stock_value_thb": total_value,
            "n_no_unit_cost_items": n_no_cost,
            "n_no_unit_cost_items_with_nonzero_stock": n_no_cost_with_stock,
        })

    summary = pd.DataFrame(rows)
    items = pd.concat(item_rows, ignore_index=True)
    summary.to_csv(os.path.join(SUMMARY_DIR, "phaseJ3_validator_stock_value_summary.csv"), index=False)
    items.to_csv(os.path.join(SUMMARY_DIR, "phaseJ3_validator_stock_value_by_item.csv"), index=False)
    print(summary.to_string(index=False))
    return summary, items


if __name__ == "__main__":
    print("=" * 100)
    print("PART A -- isolating the 97.8% vs 87.9% discrepancy (PEM101)")
    print("=" * 100)
    part_a()
    print("\n" + "=" * 100)
    print("PART B -- reconciled not_late targets, ForecastDelDate window")
    print("=" * 100)
    part_b()
    print("\n" + "=" * 100)
    print("PART C -- current on-hand stock value per division")
    print("=" * 100)
    part_c()
