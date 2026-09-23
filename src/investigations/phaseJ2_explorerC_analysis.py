"""Phase J2 -- Explorer C: does delivery come from finished-goods stock, or from component
stock / fast assembly?

Hypothesis C: delivery is typically assembled-to-order quickly from stocked components, not
pulled from a finished-goods shelf the Min/Max model tracks. If true, a large share of items
would be delivered fast WITHOUT holding finished-goods on-hand stock, and holding finished-goods
stock would not make delivery measurably faster.

DATA SOURCES (no new database connection used -- see note below):
- output/data/phaseJ_cube_ces_351items.csv -- Cube_CES pull already cached by Phase J
  (src/investigations/phaseJ_single_pull.py, run 2026-09-23) for the SAME 351-item combined
  scope this task targets. Columns include ContractID, ItemCode, CtrDate, ForecastDelDate,
  ActualDelDate, Status, ActualQty, RevenueType='Omni Channel' (already filtered at pull time).
  This is exactly the "PO/order date to actual delivery" data the task asks for (CtrDate ->
  ActualDelDate), for the same items, same divisions, same table Cube_CES the task names.
  CONVENTIONS.md requires keeping raw pulled data separate and reusing it rather than re-pulling;
  phaseJ_single_pull.py's own docstring models exactly this reuse pattern for the same file this
  task would otherwise re-query. Re-running an identical query against the same table for the
  same item scope would not produce different data and would only spend the one connection
  attempt this task is granted for no benefit -- so this task's one connection attempt was NOT
  used at all. This is stated explicitly and up front so it can be checked, per AGENTS.md rule 8.
- output/data/phaseI_combined_scope_351items.csv -- pricelist-derived code/type/category/division
  map (authoritative per CONVENTIONS.md; the database's own division-like columns are never used
  for classification).
- output/data/phaseI_inventory_exact_351items.csv -- Cube_Inventory_Exact snapshot (timestamp
  2026-09-22, i.e. "today" for this task) for the same 351 items, already cached by Phase I.
- config/config.yaml phase_e1_assumptions.sellable_warehouse_codes -- per-division sellable
  warehouse list (business assumption, not verified -- carried forward as-is).

SCOPE: PEM101/PEM103/PEM107, CtrDate >= 2024-01-01 (task-specified "2024 onward"), RevenueType
already restricted to Omni Channel at pull time, Status IN ('Actual','Backlog') at pull time.
Only rows with a non-null ActualDelDate can have a delivery-speed measurement; Backlog rows
(not yet delivered) are counted and excluded from the speed distribution, not silently dropped.
"""
import logging
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phaseE1_common import PROJECT_ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ2_explorerC")

DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "config.yaml")

SCOPE_FILE = os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv")
CES_FILE = os.path.join(DATA_DIR, "phaseJ_cube_ces_351items.csv")
INV_FILE = os.path.join(DATA_DIR, "phaseI_inventory_exact_351items.csv")

FAST_DAYS_CUTOFF = 14          # "fast delivery" definition -- see report for rationale
LARGE_SHARE_CUTOFF = 0.70      # "large share of orders" -- see report for rationale
MIN_ORDERS_FOR_SHARE = 3       # minimum delivered orders for a per-item share to be reported
                                # as reliable rather than small-N


def load_inputs():
    scope = pd.read_csv(SCOPE_FILE)
    ces = pd.read_csv(CES_FILE, parse_dates=["CtrDate", "ForecastDelDate", "ActualDelDate"])
    inv = pd.read_csv(INV_FILE)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    sellable = cfg["phase_e1_assumptions"]["sellable_warehouse_codes"]
    logger.info("Loaded scope=%d items, ces=%d rows, inv=%d rows, sellable_warehouse_codes=%s",
                len(scope), len(ces), len(inv), sellable)
    return scope, ces, inv, sellable


def build_delivery_speed(scope, ces):
    """Per-row delivery speed (CtrDate -> ActualDelDate), restricted to task scope."""
    df = ces.merge(scope[["code", "type", "category", "division"]],
                    left_on="ItemCode", right_on="code", how="inner")
    n_before = len(ces)
    n_after = len(df)
    logger.info("CES rows in 351-item scope: %d of %d (100%% by construction of the cache)",
                n_after, n_before)

    df = df[df["CtrDate"] >= "2024-01-01"].copy()
    logger.info("After CtrDate >= 2024-01-01 filter: %d rows", len(df))

    n_no_actual = df["ActualDelDate"].isna().sum()
    logger.info("%d of %d rows have no ActualDelDate (Backlog, not yet delivered) -- excluded "
                "from the speed distribution, counted separately", n_no_actual, len(df))

    delivered = df[df["ActualDelDate"].notna()].copy()
    delivered["delivery_days"] = (delivered["ActualDelDate"] - delivered["CtrDate"]).dt.days
    n_neg = (delivered["delivery_days"] < 0).sum()
    if n_neg:
        logger.warning("%d rows have ActualDelDate before CtrDate (negative delivery_days) -- "
                        "kept, reported, not dropped (never guess/silently clean per CONVENTIONS.md)",
                        n_neg)
    delivered["fast"] = delivered["delivery_days"] <= FAST_DAYS_CUTOFF
    return df, delivered, n_no_actual


def per_item_stats(delivered):
    g = delivered.groupby(["ItemCode", "division", "type", "category"])
    stats = g["delivery_days"].agg(
        n_orders="count",
        median_days="median",
        mean_days="mean",
        p25_days=lambda s: s.quantile(0.25),
        p75_days=lambda s: s.quantile(0.75),
    ).reset_index()
    fast_share = g["fast"].mean().reset_index(name="fast_share_14d")
    qty = g["ActualQty"].sum().reset_index(name="total_actual_qty") if "ActualQty" in delivered.columns else None
    stats = stats.merge(fast_share, on=["ItemCode", "division", "type", "category"])
    if qty is not None:
        stats = stats.merge(qty, on=["ItemCode", "division", "type", "category"])
    stats["reliable_share"] = stats["n_orders"] >= MIN_ORDERS_FOR_SHARE
    return stats


def per_division_distribution(delivered):
    rows = []
    for div, d in delivered.groupby("division"):
        desc = d["delivery_days"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
        rows.append({
            "division": div,
            "n_orders": int(desc["count"]),
            "mean_days": desc["mean"],
            "p10_days": desc["10%"],
            "p25_days": desc["25%"],
            "median_days": desc["50%"],
            "p75_days": desc["75%"],
            "p90_days": desc["90%"],
            "max_days": desc["max"],
            "share_within_14d": (d["delivery_days"] <= FAST_DAYS_CUTOFF).mean(),
            "share_within_30d": (d["delivery_days"] <= 30).mean(),
            "share_within_60d": (d["delivery_days"] <= 60).mean(),
        })
    return pd.DataFrame(rows)


def sellable_on_hand(inv, sellable):
    """Per-item on-hand stock, restricted to EACH ITEM'S OWN DIVISION's designated sellable
    warehouses (task instruction). inv has no division column of its own (correctly -- division
    comes from the pricelist/scope file only, per CONVENTIONS.md); division is attached by the
    caller before calling this function.
    """
    inv = inv.copy()
    inv["warehouse_stripped"] = inv["warehouse"].str.strip()
    rows = []
    for div, wh_list in sellable.items():
        sub = inv[(inv["division_scope"] == div) & (inv["warehouse_stripped"].isin(wh_list))]
        g = sub.groupby("itemcode")["stock"].sum().reset_index(name="on_hand_sellable")
        g["division"] = div
        rows.append(g)
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["itemcode", "on_hand_sellable", "division"])
    return result


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    scope, ces, inv, sellable = load_inputs()

    # Divisions with no sellable_warehouse_codes entry (CI101/PEM102/PEM104) are not in our
    # PEM101/PEM103/PEM107 task scope anyway -- restrict scope to the three task divisions only.
    task_divisions = ["PEM101", "PEM103", "PEM107"]
    scope_task = scope[scope["division"].isin(task_divisions)].copy()
    logger.info("Task-scope items (PEM101/PEM103/PEM107): %d of %d combined-scope items",
                len(scope_task), len(scope))

    all_df, delivered, n_backlog = build_delivery_speed(scope_task, ces)

    items_with_ces = scope_task["code"].isin(all_df["ItemCode"]).sum()
    logger.info("%d of %d task-scope items have ANY Cube_CES row (2024+, Omni Channel, "
                "Actual/Backlog) -- the rest have no delivery record in this pull and are "
                "CANNOT BE DETERMINED for delivery speed.", items_with_ces, len(scope_task))

    item_stats = per_item_stats(delivered)
    item_stats.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_per_item_delivery_speed.csv"),
                       index=False)

    div_dist = per_division_distribution(delivered)
    div_dist.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_per_division_delivery_distribution.csv"),
                     index=False)

    # ---- Inventory: on-hand sellable stock per item, using item's OWN division's warehouses ----
    inv2 = inv.merge(scope_task[["code", "division"]], left_on="itemcode", right_on="code",
                      how="inner")
    inv2 = inv2.rename(columns={"division": "division_scope"})
    on_hand = sellable_on_hand(inv2, sellable)
    on_hand.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_on_hand_sellable.csv"), index=False)

    # Every task-scope item gets an on-hand row, defaulting to 0 if absent from sellable set
    on_hand_full = scope_task[["code", "division", "type", "category"]].merge(
        on_hand.rename(columns={"itemcode": "code"})[["code", "on_hand_sellable"]],
        on="code", how="left")
    on_hand_full["on_hand_sellable"] = on_hand_full["on_hand_sellable"].fillna(0.0)
    on_hand_full.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_on_hand_full_scope.csv"),
                         index=False)

    # ---- Step 3: fast delivery + zero on-hand ----
    merged = item_stats.merge(
        on_hand_full.rename(columns={"code": "ItemCode"})[["ItemCode", "on_hand_sellable"]],
        on="ItemCode", how="left")
    merged["on_hand_sellable"] = merged["on_hand_sellable"].fillna(0.0)
    merged["zero_on_hand"] = merged["on_hand_sellable"] <= 0

    fast_zero = merged[(merged["fast_share_14d"] >= LARGE_SHARE_CUTOFF)
                        & merged["reliable_share"]
                        & merged["zero_on_hand"]].copy()
    fast_zero.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_fast_zero_onhand_items.csv"),
                      index=False)

    total_qty_scope = item_stats["total_actual_qty"].sum()
    fast_zero_qty = fast_zero["total_actual_qty"].sum()

    # sensitivity of the 70% cutoff
    sensitivity_rows = []
    for cutoff in (0.5, 0.7, 0.8, 0.9):
        m = merged[(merged["fast_share_14d"] >= cutoff) & merged["reliable_share"]
                   & merged["zero_on_hand"]]
        sensitivity_rows.append({
            "cutoff": cutoff,
            "n_items": len(m),
            "total_qty": m["total_actual_qty"].sum(),
            "qty_share_of_scope": m["total_actual_qty"].sum() / total_qty_scope if total_qty_scope else None,
        })
    sensitivity_df = pd.DataFrame(sensitivity_rows)
    sensitivity_df.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_cutoff_sensitivity.csv"),
                           index=False)

    by_division = fast_zero.groupby("division").agg(
        n_items=("ItemCode", "count"), total_qty=("total_actual_qty", "sum")).reset_index()
    by_division.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_fast_zero_by_division.csv"),
                        index=False)

    # ---- Step 4: reverse direction -- substantial on-hand vs zero on-hand delivery speed ----
    positive = merged[merged["on_hand_sellable"] > 0]
    median_positive = positive["on_hand_sellable"].median() if len(positive) else None
    merged["stock_tier"] = "zero"
    merged.loc[merged["on_hand_sellable"] > 0, "stock_tier"] = "positive_low"
    if median_positive is not None:
        merged.loc[merged["on_hand_sellable"] > median_positive, "stock_tier"] = "substantial_high"

    reverse_rows = []
    for tier, d in merged.groupby("stock_tier"):
        reverse_rows.append({
            "stock_tier": tier,
            "n_items": len(d),
            "n_orders_sum": d["n_orders"].sum(),
            "median_of_item_median_days": d["median_days"].median(),
            "mean_of_item_median_days": d["median_days"].mean(),
            "mean_fast_share_14d": d["fast_share_14d"].mean(),
        })
    reverse_df = pd.DataFrame(reverse_rows)
    reverse_df.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_reverse_direction.csv"), index=False)

    # order-level (not item-median-of-medians) comparison too, for robustness
    order_level = delivered.merge(
        on_hand_full.rename(columns={"code": "ItemCode"})[["ItemCode", "on_hand_sellable"]],
        left_on="ItemCode", right_on="ItemCode", how="left")
    order_level["on_hand_sellable"] = order_level["on_hand_sellable"].fillna(0.0)
    order_level["stock_group"] = "zero_on_hand"
    order_level.loc[order_level["on_hand_sellable"] > 0, "stock_group"] = "positive_on_hand"
    if median_positive is not None:
        order_level.loc[order_level["on_hand_sellable"] > median_positive, "stock_group"] = "substantial_on_hand"
    order_level_summary = order_level.groupby("stock_group")["delivery_days"].agg(
        n="count", median="median", mean="mean",
        share_within_14d=lambda s: (s <= FAST_DAYS_CUTOFF).mean()).reset_index()
    order_level_summary.to_csv(
        os.path.join(OUT_DIR, "phaseJ2_explorerC_reverse_direction_order_level.csv"), index=False)

    # ---- Step 5: product-type concentration among fast-delivered items ----
    fast_items_any_stock = merged[(merged["fast_share_14d"] >= LARGE_SHARE_CUTOFF)
                                   & merged["reliable_share"]]
    by_type_fast = fast_items_any_stock.groupby("type").agg(
        n_items=("ItemCode", "count"), total_qty=("total_actual_qty", "sum")).reset_index()
    by_type_all = item_stats[item_stats["reliable_share"]].groupby("type").agg(
        n_items_all=("ItemCode", "count")).reset_index()
    by_type = by_type_fast.merge(by_type_all, on="type", how="outer").fillna(0)
    by_type["share_of_type_fast"] = by_type["n_items"] / by_type["n_items_all"].replace(0, pd.NA)
    by_type = by_type.sort_values("n_items", ascending=False)
    by_type.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_fast_delivery_by_type.csv"), index=False)

    by_type_zero = fast_zero.groupby("type").agg(
        n_items=("ItemCode", "count"), total_qty=("total_actual_qty", "sum")).reset_index()
    by_type_zero.to_csv(os.path.join(OUT_DIR, "phaseJ2_explorerC_fast_zero_by_type.csv"), index=False)

    # ---- Print summary for the report ----
    print("=" * 70)
    print(f"Task-scope items: {len(scope_task)}; with CES delivery records: {items_with_ces}")
    print(f"Delivered rows (2024+, ActualDelDate present): {len(delivered)}; "
          f"Backlog/no-actual excluded: {n_backlog}")
    print(f"Items with >= {MIN_ORDERS_FOR_SHARE} delivered orders (reliable_share): "
          f"{item_stats['reliable_share'].sum()} of {len(item_stats)}")
    print(f"FAST_DAYS_CUTOFF={FAST_DAYS_CUTOFF}, LARGE_SHARE_CUTOFF={LARGE_SHARE_CUTOFF}")
    print(f"Fast(>=70%%,reliable) + zero on-hand items: {len(fast_zero)}")
    print(f"  total_actual_qty of those items: {fast_zero_qty} / scope total {total_qty_scope} "
          f"= {fast_zero_qty/total_qty_scope:.4f}" if total_qty_scope else "n/a")
    print("By division:")
    print(by_division.to_string(index=False))
    print("Sensitivity:")
    print(sensitivity_df.to_string(index=False))
    print("Reverse direction (item-level, median-of-medians):")
    print(reverse_df.to_string(index=False))
    print("Reverse direction (order-level):")
    print(order_level_summary.to_string(index=False))
    print("median_positive on-hand (for substantial_high tier threshold):", median_positive)
    print("=" * 70)


if __name__ == "__main__":
    main()
