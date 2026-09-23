"""
Phase J3 Part 2 -- Independent Validator recomputation.

INDEPENDENT re-implementation of the Section 16 simulation mechanics and the
inverse_calibration (Section 20) scoring, written directly from METRICS.md
Sec.16/Sec.20's literal text -- NOT from, and without reading,
src/investigations/phaseJ3_calibration_engine.py or
src/investigations/phaseJ3_run_calibration.py (the Modeler's own scripts).

Purpose: recompute the Modeler's reported calib_not_late / valid_not_late /
calib_stock_value / valid_stock_value for the three "best fit" (r_months,
s_months, review_interval_days, lead_time_days) combinations the Modeler
reported for PEM101 / PEM103 / PEM107, from the cached raw pull only (no
database access), and diff against the Modeler's reported figures.

All data sources are the already-cached Phase I pull:
  - output/data/phaseI_raw_sales_351items.csv       (raw daily sales)
  - output/data/phaseI_combined_scope_351items.csv  (351-item / division map)
  - output/data/phaseI_inventory_exact_351items.csv  (current on-hand snapshot)
  - config/config.yaml                               (sellable_warehouse_codes,
                                                        leakage_guard.min_margin_days)

Writes: output/summary/phaseJ3_validator2_independent_check.md
"""
import logging
from pathlib import Path

import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "output" / "data" / "phaseI_raw_sales_351items.csv"
DATA_SCOPE = ROOT / "output" / "data" / "phaseI_combined_scope_351items.csv"
DATA_INV = ROOT / "output" / "data" / "phaseI_inventory_exact_351items.csv"
CONFIG_PATH = ROOT / "config" / "config.yaml"
OUT_MD = ROOT / "output" / "summary" / "phaseJ3_validator2_independent_check.md"

DAYS_PER_MONTH = 30.44

# The three combinations under check -- given directly as task input, not
# read from any Modeler results file.
COMBOS = {
    "PEM101": dict(r_months=0.5, s_months=2.5, review_interval_days=1, lead_time_days=3),
    "PEM103": dict(r_months=3.0, s_months=7.0, review_interval_days=1, lead_time_days=7),
    "PEM107": dict(r_months=0.25, s_months=6.0, review_interval_days=30, lead_time_days=1),
}

MODELER_REPORTED = {
    "PEM101": dict(calib_not_late=0.9886, valid_not_late=0.9831,
                   calib_stock_value=18_416_287, valid_stock_value=18_196_081),
    "PEM103": dict(calib_not_late=0.9052, valid_not_late=0.9652,
                   calib_stock_value=57_570_082, valid_stock_value=47_401_047),
    "PEM107": dict(calib_not_late=0.7178, valid_not_late=0.7891,
                   calib_stock_value=18_442_316, valid_stock_value=20_453_831),
}

CALIB_START, CALIB_END = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-12-31")
VALID_START = pd.Timestamp("2026-01-01")
WINDOW_START = pd.Timestamp("2024-01-01")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(DATA_RAW, parse_dates=["createDate", "forecast_date"])
    n0 = len(df)
    df = df.dropna(subset=["forecast_date"])
    n1 = len(df)
    df = df[df["forecast_date"] >= df["createDate"]]
    n2 = len(df)
    log.info("raw pull: %d rows -> %d after dropping null forecast_date -> %d after "
             "forecast_date>=createDate filter", n0, n1, n2)
    return df


def compute_window_end(raw: pd.DataFrame) -> pd.Timestamp:
    """Max createDate in the cached pull, backed off to the end of the PRIOR
    calendar month (this project's leakage-guard convention, config.yaml
    leakage_guard.min_margin_days=30)."""
    max_create = raw["createDate"].max()
    first_of_month = max_create.replace(day=1)
    window_end = first_of_month - pd.Timedelta(days=1)
    log.info("global max createDate = %s -> window_end (end of prior calendar month) = %s",
             max_create.date(), window_end.date())
    return window_end


def compute_unit_costs(raw: pd.DataFrame, global_max_create: pd.Timestamp) -> pd.Series:
    """METRICS.md Sec.1: median(cost/qty) over rows in the trailing 12 months
    (anchored to the pull's own global max createDate), qty != 0 rows only.
    Fallback: most recent qty>0 row if fewer than 3 rows in the window.
    Undefined if no row exists at all -> NaN, item excluded from value calc.
    """
    df = raw[raw["qty"] != 0].copy()
    df["cost_per_unit"] = df["cost"] / df["qty"]
    window_start = global_max_create - pd.DateOffset(months=12)
    in_window = df[(df["createDate"] >= window_start) & (df["createDate"] <= global_max_create)]

    counts = in_window.groupby("itemcode").size()
    medians = in_window.groupby("itemcode")["cost_per_unit"].median()

    # fallback for items with <3 rows in the trailing-12mo window (or none there)
    df_sorted = df.sort_values("createDate")
    most_recent = df_sorted.groupby("itemcode").tail(1).set_index("itemcode")["cost_per_unit"]

    unit_cost = {}
    all_items = set(df["itemcode"].unique()) | set(medians.index)
    for item in all_items:
        n = counts.get(item, 0)
        if n >= 3:
            unit_cost[item] = medians[item]
        elif item in most_recent.index:
            unit_cost[item] = most_recent[item]
            log.info("unit_cost fallback (most-recent-transaction) for %s: only %d rows in "
                      "trailing-12mo window", item, n)
        else:
            unit_cost[item] = float("nan")
    return pd.Series(unit_cost, name="unit_cost")


def build_daily_demand(raw: pd.DataFrame, items: list, window_start: pd.Timestamp,
                        window_end: pd.Timestamp) -> pd.DataFrame:
    """Zero-filled daily demand series, forecast_date-keyed, per item, spanning
    window_start..window_end inclusive."""
    idx = pd.date_range(window_start, window_end, freq="D")
    sub = raw[raw["itemcode"].isin(items)]
    daily = sub.groupby(["itemcode", "forecast_date"])["qty"].sum().unstack("itemcode")
    daily = daily.reindex(idx, fill_value=0.0)
    daily = daily.reindex(columns=items, fill_value=0.0)
    daily = daily.fillna(0.0)
    return daily


def simulate_item(demand: "pd.Series", r_abs: float, s_abs: float,
                   review_interval_days: int, lead_time_days: int) -> tuple:
    """METRICS.md Sec.16 mechanics, literal implementation, with this task's
    explicit overrides: lead_time_days given directly (task collapses
    procurement+assembly into one figure), initial stock = S at day 0 (task's
    explicit inverse_calibration instruction, Sec.20: "the historical initial
    stock is unknown; the warm-up absorbs it"), no order in flight at day 0.

    Per-day sequence (position on_hand+on_order is invariant to receipt
    timing, so this ordering does not affect the reorder trigger):
      1. receive any order scheduled to arrive today -> on_hand
      2. that receipt is applied to any outstanding backorder FIRST
         ("filled first from the next receipt" -- Sec.16)
      3. on a review day, if on_hand+on_order <= r, order (S-on_hand-on_order)
      4. today's demand ships from on_hand; shortfall becomes/extends backorder
         (units shipped from a later receipt do not count as shipped "on the
         demand day" -- Sec.16 fill_rate definition)

    Returns (shipped_daily, demand_daily, onhand_end_of_day_daily) as numpy arrays.
    """
    n = len(demand)
    demand_arr = demand.values
    on_hand = s_abs
    on_order = 0.0
    backorder = 0.0
    arrivals = {}  # day -> qty scheduled to arrive

    shipped = [0.0] * n
    onhand_eod = [0.0] * n

    for d in range(n):
        # 1. receive
        if d in arrivals:
            recv = arrivals.pop(d)
            on_hand += recv
            on_order -= recv
            # 2. apply to backorder first
            if backorder > 0:
                fill_b = min(on_hand, backorder)
                on_hand -= fill_b
                backorder -= fill_b

        # 3. review / reorder trigger
        if d % review_interval_days == 0:
            position = on_hand + on_order
            if position <= r_abs:
                order_qty = s_abs - position
                if order_qty > 0:
                    on_order += order_qty
                    arrive_day = d + lead_time_days
                    arrivals[arrive_day] = arrivals.get(arrive_day, 0.0) + order_qty

        # 4. today's demand
        dem = demand_arr[d]
        if on_hand >= dem:
            shipped[d] = dem
            on_hand -= dem
        else:
            shipped[d] = on_hand
            short = dem - on_hand
            on_hand = 0.0
            backorder += short

        onhand_eod[d] = on_hand

    return shipped, demand_arr.tolist(), onhand_eod


def score_window(dates: pd.DatetimeIndex, shipped: dict, demand: dict, onhand: dict,
                  unit_cost: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    mask = (dates >= start) & (dates <= end)
    total_shipped = 0.0
    total_demand = 0.0
    stock_value = 0.0
    for item in shipped:
        s = pd.Series(shipped[item]).to_numpy()[mask]
        total_shipped += s.sum()
    for item in demand:
        d = pd.Series(demand[item]).to_numpy()[mask]
        total_demand += d.sum()
    for item in onhand:
        oh = pd.Series(onhand[item]).to_numpy()[mask]
        mean_oh = oh.mean()
        uc = unit_cost.get(item, float("nan"))
        if pd.notna(uc):
            stock_value += mean_oh * uc
    not_late = total_shipped / total_demand if total_demand > 0 else float("nan")
    return dict(not_late=not_late, stock_value=stock_value,
                total_shipped=total_shipped, total_demand=total_demand)


def compute_current_stock_value(inv: pd.DataFrame, items: list, sellable_wh: list,
                                 unit_cost: pd.Series) -> float:
    sub = inv[inv["itemcode"].isin(items) & inv["warehouse"].str.strip().isin(
        [w.strip() for w in sellable_wh])]
    by_item = sub.groupby("itemcode")["stock"].sum()
    val = 0.0
    for item, qty in by_item.items():
        uc = unit_cost.get(item, float("nan"))
        if pd.notna(uc):
            val += qty * uc
    return val


def main():
    cfg = load_config()
    sellable = cfg["phase_e1_assumptions"]["sellable_warehouse_codes"]

    raw = load_raw()
    scope = pd.read_csv(DATA_SCOPE)
    inv = pd.read_csv(DATA_INV)

    global_max_create = raw["createDate"].max()
    window_end = compute_window_end(raw)
    unit_cost = compute_unit_costs(raw, global_max_create)
    no_cost_items = unit_cost[unit_cost.isna()].index.tolist()
    log.info("%d items with no derivable unit_cost (excluded from stock value): %s",
             len(no_cost_items), no_cost_items)

    dates = pd.date_range(WINDOW_START, window_end, freq="D")

    results = {}
    for division, combo in COMBOS.items():
        items = scope.loc[scope["division"] == division, "code"].tolist()
        log.info("%s: %d items in scope (%s)", division, len(items), DATA_SCOPE.name)

        demand_df = build_daily_demand(raw, items, WINDOW_START, window_end)

        r_months = combo["r_months"]
        s_months = combo["s_months"]
        review = combo["review_interval_days"]
        lead = combo["lead_time_days"]

        shipped_d, demand_d, onhand_d = {}, {}, {}
        for item in items:
            series = demand_df[item]
            mean_daily_demand = series.mean()
            r_abs = r_months * DAYS_PER_MONTH * mean_daily_demand
            s_abs = s_months * DAYS_PER_MONTH * mean_daily_demand
            shipped, dem, onhand = simulate_item(series, r_abs, s_abs, review, lead)
            shipped_d[item] = shipped
            demand_d[item] = dem
            onhand_d[item] = onhand

        calib = score_window(dates, shipped_d, demand_d, onhand_d, unit_cost, CALIB_START, CALIB_END)
        valid = score_window(dates, shipped_d, demand_d, onhand_d, unit_cost, VALID_START, window_end)

        current_stock_value = compute_current_stock_value(inv, items, sellable[division], unit_cost)

        results[division] = dict(
            n_items=len(items),
            window_end=str(window_end.date()),
            calib_not_late=calib["not_late"],
            valid_not_late=valid["not_late"],
            calib_stock_value=calib["stock_value"],
            valid_stock_value=valid["stock_value"],
            calib_total_demand=calib["total_demand"],
            valid_total_demand=valid["total_demand"],
            current_stock_value_snapshot=current_stock_value,
            n_no_unit_cost=len(set(items) & set(no_cost_items)),
        )
        log.info("%s result: %s", division, results[division])

    write_report(results, window_end, global_max_create)
    return results


def write_report(results: dict, window_end: pd.Timestamp, global_max_create: pd.Timestamp):
    lines = []
    lines.append("# Phase J3 Part 2 -- Independent Validator Recomputation\n")
    lines.append(
        "Independent re-implementation of METRICS.md Sec.16 (`simulation_mechanics`) and "
        "Sec.20 (`inverse_calibration`), written from the literal text only. Does NOT read or "
        "import `src/investigations/phaseJ3_calibration_engine.py` or "
        "`src/investigations/phaseJ3_run_calibration.py` (the Modeler's own scripts). No "
        "database access -- all inputs from the cached Phase I pull:\n"
        "- `output/data/phaseI_raw_sales_351items.csv`\n"
        "- `output/data/phaseI_combined_scope_351items.csv`\n"
        "- `output/data/phaseI_inventory_exact_351items.csv`\n"
        "- `config/config.yaml`\n"
    )
    lines.append(f"\nGlobal max `createDate` in the cached pull: **{global_max_create.date()}**. "
                 f"Simulated window end (end of prior calendar month, this project's "
                 f"leakage-guard convention, `config.yaml leakage_guard.min_margin_days=30`): "
                 f"**{window_end.date()}**. Simulated window: 2024-01-01 to {window_end.date()}.\n")
    lines.append("Calibration scoring window: 2024-07-01 to 2025-12-31 (first 6 months warm-up, "
                 "excluded). Validation scoring window: 2026-01-01 to "
                 f"{window_end.date()}.\n")

    def pct(x):
        return f"{x*100:.2f}%"

    def thb(x):
        return f"{x:,.0f}"

    lines.append("\n## Results per division\n")
    lines.append("| Division | Items | calib_not_late | valid_not_late | calib_stock_value | "
                 "valid_stock_value | current on-hand snapshot value (context) |")
    lines.append("|---|---|---|---|---|---|---|")
    for div, r in results.items():
        lines.append(f"| {div} | {r['n_items']} | {pct(r['calib_not_late'])} | "
                     f"{pct(r['valid_not_late'])} | {thb(r['calib_stock_value'])} | "
                     f"{thb(r['valid_stock_value'])} | {thb(r['current_stock_value_snapshot'])} |")

    lines.append("\n## Comparison against Modeler-reported figures\n")
    lines.append("Tolerance: not_late within +/-0.5 percentage points; stock_value within "
                 "+/-1% relative.\n")
    lines.append("| Division | Figure | Validator | Modeler | Abs/Rel diff | Verdict |")
    lines.append("|---|---|---|---|---|---|")
    for div, r in results.items():
        mod = MODELER_REPORTED[div]
        rows = [
            ("calib_not_late", r["calib_not_late"], mod["calib_not_late"], "pp", 0.005),
            ("valid_not_late", r["valid_not_late"], mod["valid_not_late"], "pp", 0.005),
            ("calib_stock_value", r["calib_stock_value"], mod["calib_stock_value"], "rel", 0.01),
            ("valid_stock_value", r["valid_stock_value"], mod["valid_stock_value"], "rel", 0.01),
        ]
        for name, val, modval, kind, tol in rows:
            if kind == "pp":
                diff = val - modval
                verdict = "MATCH" if abs(diff) <= tol else "DISCREPANCY"
                diffstr = f"{diff*100:+.2f}pp"
            else:
                diff = (val - modval) / modval if modval else float("nan")
                verdict = "MATCH" if abs(diff) <= tol else "DISCREPANCY"
                diffstr = f"{diff*100:+.2f}%"
            valstr = pct(val) if kind == "pp" else thb(val)
            modstr = pct(modval) if kind == "pp" else thb(modval)
            lines.append(f"| {div} | {name} | {valstr} | {modstr} | {diffstr} | {verdict} |")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote %s", OUT_MD)


if __name__ == "__main__":
    main()
