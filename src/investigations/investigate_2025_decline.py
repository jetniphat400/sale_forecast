"""Analyst task A2: decompose the 2024->2025 Jan-Jul sale-value decline (and 2025->2026
recovery) and test whether it is a genuine business change or a recording/classification
artifact, following the same method used for the 2022/2023 break (STATUS.md).

Read-only investigation. Does not modify config.yaml, does not select a forecasting model,
does not compute Max-Min. Writes only to output/summary/ and output/data/ with a
phaseA_a2_ prefix, per the Analyst role's output convention (AGENTS.md).

Project-standard filters throughout unless stated otherwise:
  division='PEM101', revenue_type='Omni Channel', status IN ('Actual','MPS'),
  createDate >= 2024-01-01.
Jan-Jul window used for year comparability, since 2026 data is partial (through 2026-08-28).
"""
import logging
import sys

import pandas as pd

sys.path.insert(0, "src")
from db import run_query  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT_SUMMARY = "output/summary/"
OUT_DATA = "output/data/"

BASE_FILTER = (
    "division='PEM101' AND revenue_type='Omni Channel' AND status IN ('Actual','MPS') "
    "AND createDate >= '2024-01-01'"
)
JAN_JUL_FILTER = BASE_FILTER + " AND MONTH(createDate) BETWEEN 1 AND 7"


def log_rows(name: str, df: pd.DataFrame) -> None:
    log.info("%s: %d rows", name, len(df))


def task_monthly_whole_population():
    """Month-by-month whole-population series (not limited to 128 items) from 2024-01
    through the latest available date, to test for a ramp vs. a step-change at the
    2024/2025 boundary (task 3 methodology, same as the 2022/2023 break investigation)."""
    sql = f"""
    SELECT YEAR(createDate) AS yr, MONTH(createDate) AS mo,
           SUM(sale) AS total_sale, SUM(qty) AS total_qty,
           COUNT(DISTINCT contractid) AS n_orders,
           COUNT(DISTINCT customerid) AS n_customers,
           COUNT(DISTINCT itemcode) AS n_items,
           COUNT(*) AS n_rows
    FROM cube_Sale_APD
    WHERE {BASE_FILTER}
    GROUP BY YEAR(createDate), MONTH(createDate)
    ORDER BY yr, mo
    """
    df = run_query(sql)
    df["avg_price_per_unit"] = df["total_sale"] / df["total_qty"]
    log_rows("monthly_whole_population", df)
    df.to_csv(OUT_SUMMARY + "phaseA_a2_monthly_whole_population.csv", index=False)
    return df


def task_item_level_jan_jul_whole_population():
    """Item x year Jan-Jul sale AND qty, whole population (not the 128-item scope), to
    (a) add the missing delta_2025_vs_2024 to the existing item-level breakdown, cross-
    validated against it, and (b) support a price/volume/mix decomposition."""
    sql = f"""
    SELECT itemcode, YEAR(createDate) AS yr,
           SUM(sale) AS total_sale, SUM(qty) AS total_qty
    FROM cube_Sale_APD
    WHERE {JAN_JUL_FILTER}
    GROUP BY itemcode, YEAR(createDate)
    """
    df = run_query(sql)
    log_rows("item_level_jan_jul_whole_population", df)
    df.to_csv(OUT_DATA + "phaseA_a2_raw_item_year_qty_sale.csv", index=False)
    return df


def task_customer_level_jan_jul():
    """Customer x year Jan-Jul sale/qty/orders, whole population, to identify which
    customers dropped out in 2025 and whether they returned in 2026 (task 2)."""
    sql = f"""
    SELECT customerid, YEAR(createDate) AS yr,
           SUM(sale) AS total_sale, SUM(qty) AS total_qty,
           COUNT(DISTINCT contractid) AS n_orders, COUNT(*) AS n_rows
    FROM cube_Sale_APD
    WHERE {JAN_JUL_FILTER}
    GROUP BY customerid, YEAR(createDate)
    """
    df = run_query(sql)
    log_rows("customer_level_jan_jul", df)
    df.to_csv(OUT_DATA + "phaseA_a2_raw_customer_year_sale.csv", index=False)
    return df


def task_revenue_type_composition():
    """Within division=PEM101 only (NOT filtered to revenue_type='Omni Channel'), check
    whether the revenue_type composition shifted 2024->2025 -- the same test that
    revealed the 2022/2023 break was a reclassification (RevenueType NULL -> populated).
    Here we check the reverse direction: did Omni Channel lose share to another
    revenue_type in 2025?"""
    sql = """
    SELECT YEAR(createDate) AS yr, revenue_type,
           COUNT(*) AS n_rows, SUM(sale) AS total_sale,
           COUNT(DISTINCT contractid) AS n_orders
    FROM cube_Sale_APD
    WHERE division='PEM101' AND status IN ('Actual','MPS')
      AND createDate >= '2024-01-01' AND MONTH(createDate) BETWEEN 1 AND 7
    GROUP BY YEAR(createDate), revenue_type
    ORDER BY yr, revenue_type
    """
    df = run_query(sql)
    log_rows("revenue_type_composition", df)
    df.to_csv(OUT_SUMMARY + "phaseA_a2_revenue_type_composition_pem101.csv", index=False)
    return df


def task_status_composition():
    """Actual vs MPS composition by year, Jan-Jul, within the standard filter -- checks
    whether a shift in Actual/MPS mix could explain the price or value collapse."""
    sql = f"""
    SELECT YEAR(createDate) AS yr, status,
           COUNT(*) AS n_rows, SUM(sale) AS total_sale, SUM(qty) AS total_qty
    FROM cube_Sale_APD
    WHERE {JAN_JUL_FILTER}
    GROUP BY YEAR(createDate), status
    ORDER BY yr, status
    """
    df = run_query(sql)
    log_rows("status_composition", df)
    df.to_csv(OUT_SUMMARY + "phaseA_a2_status_composition.csv", index=False)
    return df


def task_category_type_mix():
    """Category/Type x year Jan-Jul sale & qty, to test whether the price collapse is a
    mix shift (a low-price category/type gaining share) rather than a same-product price
    change."""
    sql = f"""
    SELECT YEAR(createDate) AS yr, productCateName, productTypeName,
           SUM(sale) AS total_sale, SUM(qty) AS total_qty
    FROM cube_Sale_APD
    WHERE {JAN_JUL_FILTER}
    GROUP BY YEAR(createDate), productCateName, productTypeName
    ORDER BY yr, total_sale DESC
    """
    df = run_query(sql)
    log_rows("category_type_mix", df)
    df.to_csv(OUT_SUMMARY + "phaseA_a2_category_type_mix_jan_jul.csv", index=False)
    return df


def task_division_wide_check():
    """Whole PEM101 division (any revenue_type), Jan-Jul by year -- checks whether the
    decline is specific to the Omni Channel slice or affects the whole division, which
    would point toward a genuine broad business change rather than a channel-specific
    reclassification."""
    sql = """
    SELECT YEAR(createDate) AS yr,
           SUM(sale) AS total_sale, SUM(qty) AS total_qty,
           COUNT(DISTINCT contractid) AS n_orders,
           COUNT(DISTINCT customerid) AS n_customers
    FROM cube_Sale_APD
    WHERE division='PEM101' AND status IN ('Actual','MPS')
      AND createDate >= '2024-01-01' AND MONTH(createDate) BETWEEN 1 AND 7
    GROUP BY YEAR(createDate)
    ORDER BY yr
    """
    df = run_query(sql)
    log_rows("division_wide_check", df)
    df.to_csv(OUT_SUMMARY + "phaseA_a2_division_wide_pem101_jan_jul.csv", index=False)
    return df


def build_item_delta_and_pvm(item_year_df: pd.DataFrame):
    """Add delta_2025_vs_2024 to the existing item-level file (cross-validated against
    it), and compute a price/volume/mix decomposition of the 2024->2025 sale delta."""
    pivot_sale = item_year_df.pivot(index="itemcode", columns="yr", values="total_sale").fillna(0.0)
    pivot_qty = item_year_df.pivot(index="itemcode", columns="yr", values="total_qty").fillna(0.0)
    pivot_sale.columns = [f"sale_{c}" for c in pivot_sale.columns]
    pivot_qty.columns = [f"qty_{c}" for c in pivot_qty.columns]
    merged = pivot_sale.join(pivot_qty).reset_index()

    for y in (2024, 2025, 2026):
        if f"sale_{y}" not in merged.columns:
            merged[f"sale_{y}"] = 0.0
        if f"qty_{y}" not in merged.columns:
            merged[f"qty_{y}"] = 0.0

    merged["delta_2025_vs_2024"] = merged["sale_2025"] - merged["sale_2024"]
    merged["delta_2026_vs_2025"] = merged["sale_2026"] - merged["sale_2025"]
    merged["price_2024"] = merged.apply(
        lambda r: r["sale_2024"] / r["qty_2024"] if r["qty_2024"] else None, axis=1
    )
    merged["price_2025"] = merged.apply(
        lambda r: r["sale_2025"] / r["qty_2025"] if r["qty_2025"] else None, axis=1
    )

    # Cross-validate against the existing part4_item_level_jan_jul.csv (sale_2024/2025/2026)
    existing = pd.read_csv(OUT_SUMMARY + "part4_item_level_jan_jul.csv")
    existing = existing.rename(
        columns={"2024": "existing_2024", "2025": "existing_2025", "2026": "existing_2026"}
    )
    check = merged.merge(existing, on="itemcode", how="outer", indicator=True)
    mismatch = check[
        (check["_merge"] != "both")
        | ((check["sale_2024"].fillna(0) - check["existing_2024"].fillna(0)).abs() > 1.0)
        | ((check["sale_2025"].fillna(0) - check["existing_2025"].fillna(0)).abs() > 1.0)
    ]
    log.info(
        "Cross-validation of fresh item-level pull vs existing part4_item_level_jan_jul.csv: "
        "%d of %d items mismatch by >1 THB or missing on one side",
        len(mismatch), len(check),
    )
    check.to_csv(OUT_SUMMARY + "phaseA_a2_item_level_crossvalidation.csv", index=False)

    merged = merged.sort_values("delta_2025_vs_2024")
    merged.to_csv(OUT_SUMMARY + "phaseA_a2_item_level_jan_jul_with_deltas.csv", index=False)

    # Price-volume decomposition of the 2024->2025 total delta:
    #   volume_effect_i = price_2024_i * (qty_2025_i - qty_2024_i)   [qty change valued at old price]
    #   price_effect_i  = qty_2025_i   * (price_2025_i - price_2024_i) [price change valued at new qty]
    #   volume_effect_i + price_effect_i == sale_2025_i - sale_2024_i  (exact, no cross term)
    # For items with qty_2024==0 (new in 2025) or qty_2025==0 (dropped after 2024), the whole
    # delta is treated as a volume/entry-exit effect (price effect undefined/zero) since there
    # is no "old price" or "new qty" to compare against.
    def pvm_row(r):
        q24, q25 = r["qty_2024"], r["qty_2025"]
        s24, s25 = r["sale_2024"], r["sale_2025"]
        if q24 > 0 and q25 > 0:
            p24 = s24 / q24
            vol = p24 * (q25 - q24)
            price = q25 * (r["price_2025"] - p24)
            return pd.Series({"volume_effect": vol, "price_effect": price, "kind": "continuing"})
        elif q24 > 0 and q25 == 0:
            return pd.Series({"volume_effect": s25 - s24, "price_effect": 0.0, "kind": "dropped_out_2025"})
        elif q24 == 0 and q25 > 0:
            return pd.Series({"volume_effect": s25 - s24, "price_effect": 0.0, "kind": "new_in_2025"})
        else:
            return pd.Series({"volume_effect": 0.0, "price_effect": 0.0, "kind": "absent_both"})

    pvm = merged.apply(pvm_row, axis=1)
    merged = pd.concat([merged, pvm], axis=1)
    merged.to_csv(OUT_SUMMARY + "phaseA_a2_item_level_price_volume_decomposition.csv", index=False)

    totals = {
        "total_delta_2025_vs_2024": merged["delta_2025_vs_2024"].sum(),
        "sum_volume_effect": merged["volume_effect"].sum(),
        "sum_price_effect": merged["price_effect"].sum(),
        "delta_from_continuing_items": merged.loc[merged["kind"] == "continuing", "delta_2025_vs_2024"].sum(),
        "delta_from_dropped_out_items": merged.loc[merged["kind"] == "dropped_out_2025", "delta_2025_vs_2024"].sum(),
        "delta_from_new_items": merged.loc[merged["kind"] == "new_in_2025", "delta_2025_vs_2024"].sum(),
        "n_continuing": (merged["kind"] == "continuing").sum(),
        "n_dropped_out": (merged["kind"] == "dropped_out_2025").sum(),
        "n_new": (merged["kind"] == "new_in_2025").sum(),
    }
    totals_df = pd.DataFrame([totals])
    totals_df.to_csv(OUT_SUMMARY + "phaseA_a2_price_volume_decomposition_totals.csv", index=False)
    log.info("PVM decomposition totals: %s", totals)
    return merged, totals_df


def build_customer_classification(cust_year_df: pd.DataFrame):
    """Classify each customer active in Jan-Jul 2024 and/or 2025 and/or 2026 into
    disappeared-in-2025-and-returned-2026, disappeared-and-not-returned, continuing,
    new-in-2025, new-in-2026, etc."""
    pivot = cust_year_df.pivot(index="customerid", columns="yr", values="total_sale").fillna(0.0)
    for y in (2024, 2025, 2026):
        if y not in pivot.columns:
            pivot[y] = 0.0
    pivot.columns = [f"sale_{c}" for c in pivot.columns]
    pivot = pivot.reset_index()

    def classify(r):
        a24 = r["sale_2024"] > 0
        a25 = r["sale_2025"] > 0
        a26 = r["sale_2026"] > 0
        if a24 and not a25 and a26:
            return "dipped_out_2025_returned_2026"
        if a24 and not a25 and not a26:
            return "dropped_after_2024_not_returned"
        if a24 and a25 and a26:
            return "continuing_all_3_years"
        if a24 and a25 and not a26:
            return "active_2024_2025_not_yet_seen_2026"
        if not a24 and a25 and a26:
            return "new_in_2025_continuing"
        if not a24 and a25 and not a26:
            return "new_in_2025_only"
        if not a24 and not a25 and a26:
            return "new_in_2026_only"
        return "other/none"

    pivot["classification"] = pivot.apply(classify, axis=1)
    pivot["delta_2025_vs_2024"] = pivot["sale_2025"] - pivot["sale_2024"]
    pivot = pivot.sort_values("delta_2025_vs_2024")
    pivot.to_csv(OUT_SUMMARY + "phaseA_a2_customer_classification_jan_jul.csv", index=False)

    summary = pivot.groupby("classification").agg(
        n_customers=("customerid", "count"),
        total_sale_2024=("sale_2024", "sum"),
        total_sale_2025=("sale_2025", "sum"),
        total_sale_2026=("sale_2026", "sum"),
        total_delta_2025_vs_2024=("delta_2025_vs_2024", "sum"),
    ).reset_index()
    summary.to_csv(OUT_SUMMARY + "phaseA_a2_customer_classification_summary.csv", index=False)
    log.info("Customer classification summary:\n%s", summary.to_string())
    return pivot, summary


def main():
    log.info("Task: monthly whole-population series (ramp vs step-change test)")
    task_monthly_whole_population()

    log.info("Task: item-level Jan-Jul whole population (qty+sale)")
    item_year_df = task_item_level_jan_jul_whole_population()
    build_item_delta_and_pvm(item_year_df)

    log.info("Task: customer-level Jan-Jul whole population")
    cust_year_df = task_customer_level_jan_jul()
    build_customer_classification(cust_year_df)

    log.info("Task: revenue_type composition within PEM101 (reclassification test)")
    task_revenue_type_composition()

    log.info("Task: status (Actual/MPS) composition")
    task_status_composition()

    log.info("Task: category/type mix Jan-Jul")
    task_category_type_mix()

    log.info("Task: whole-division (any revenue_type) Jan-Jul check")
    task_division_wide_check()

    log.info("All tasks complete.")


if __name__ == "__main__":
    main()
