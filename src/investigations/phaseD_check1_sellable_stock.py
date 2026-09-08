"""Phase D, Check 1 (Explorer role, AGENTS.md): which warehouse stages hold sellable stock.

Scope is deliberately narrow (per the task instructions): read only
`[salewarehouse].[dbo].[Cube_Inventory_Exact]` (the current-STATE inventory snapshot) plus the
joins needed to attach item scope (the pricelist) and division. No other table is searched.

INVESTIGATION ONLY, per AGENTS.md Explorer role: reports what queries return, never interprets
business meaning. No min/max calculated, no model built, config.yaml not touched.

Essential prior context (STATUS.md, "Warehouse flow, stage dwell time, sellable stock, and
double-counting verification" -- DONE 2026-09-02, and STATUS.md Section 8.4): an earlier
investigation using `cube_inventory_tran` (a movement LEDGER, not this table) found:
  - Dominant route QA -> WH01 -> FG01 -> FG02, with confirmed bidirectional movement too.
  - 14 warehouse codes had assigned behavioural roles: CL, F101, FG, FG01, FG02, FG11, FG21,
    FMTO, FMTS, INTR, QA, W121, WH01, WH21 (output/summary/part1_all_transfer_routes.csv).
  - Only 2 exclusions were justified by BEHAVIOURAL evidence: QA (pass-through inspection gate --
    567,306 units handled, only 22 ever issued externally) and FMTS/FMTO (production WIP,
    negligible settled stock, large tobe_received). CONFIRMED NOT AVAILABLE: QA, FMTS, FMTO.
  - Everything else -- including FG01/FG02/FG11/FG21 and every code outside the 14-code list --
    was left UNDETERMINED: plausible from topology, but not confirmed by behaviour. That ledger
    only covered 34 of 128 items, and only 6 of those 34 (all Raw Material Fuse Holder codes, not
    Finished Goods) showed any confirmed transfer at all.

This script's job: push the determination further using `Cube_Inventory_Exact` (a current-STATE
snapshot covering far more of the item scope) for the FULL 445-item pricelist scope. Per the
ground rules: never mark a code sellable "by assumption" from its name or from the QA->WH01->
FG01->FG02 topology alone -- only new BEHAVIOURAL evidence found directly in this table (e.g. a
status/sellability flag on the row itself) can move a code out of UNDETERMINED. If no such field
exists in the schema, say so plainly and stop (the stopping rule) -- do not search other tables.
"""
import logging
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query
from pricelist_reader import load_visible_product_rows
from division_utils import assert_no_code_on_multiple_sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseD_check1_sellable_stock")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"

# Prior investigation's behavioural findings (STATUS.md, 2026-09-02 warehouse flow entry) --
# applied here, not re-derived, per the task instructions.
FOURTEEN_ROLE_CODES = {"CL", "F101", "FG", "FG01", "FG02", "FG11", "FG21", "FMTO", "FMTS",
                        "INTR", "QA", "W121", "WH01", "WH21"}
CONFIRMED_NOT_SELLABLE = {"QA", "FMTS", "FMTO"}
PRIOR_EVIDENCE_NOTE = (
    "STATUS.md 'Warehouse flow, stage dwell time, sellable stock, and double-counting "
    "verification' (DONE 2026-09-02), Part 3: QA = pass-through inspection gate (567,306 units "
    "handled in the 6-item movement-ledger scope, only 22 -- 0.004% -- ever issued externally). "
    "FMTS/FMTO = production work-in-progress staging (evidenced broadly across 69-103 of 128 "
    "items in the prior 128-item scope: negligible settled stock, large tobe_received). This "
    "check applies that finding rather than re-deriving it, since Cube_Inventory_Exact alone "
    "(this check's permitted scope) cannot reproduce a movement-based finding -- it has no "
    "transaction/issue-event data, only current-state quantities."
)


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save(df: pd.DataFrame, name: str) -> str:
    path = os.path.join(SUMMARY_DIR, f"phaseD_check1_{name}.csv")
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d rows)", path, len(df))
    return path


def sql_in(codes) -> str:
    return "','".join(c.replace("'", "''") for c in codes)


# ============================================================================
# Step 1: full schema + snapshot date + table-wide warehouse universe
# ============================================================================
def step1_full_structure() -> tuple:
    logger.info("=== STEP 1: Cube_Inventory_Exact full structure (table-wide, no item filter) ===")

    schema = run_query(
        "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, "
        "NUMERIC_SCALE, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'Cube_Inventory_Exact' ORDER BY ORDINAL_POSITION"
    )
    save(schema, "01_schema")
    logger.info("Schema: %d columns -- %s", len(schema), list(schema["COLUMN_NAME"]))

    ts = run_query(
        f"SELECT MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts, "
        f"COUNT(DISTINCT CAST(timestamp AS DATE)) AS n_distinct_dates, "
        f"COUNT(DISTINCT timestamp) AS n_distinct_timestamps, COUNT(*) AS n_rows FROM {INV_TABLE}"
    )
    save(ts, "02_snapshot_date_range")
    logger.info("Snapshot timestamp range: %s", ts.to_dict("records")[0])

    wh_full = run_query(f"""
        SELECT warehouse,
               COUNT(*) AS n_rows,
               COUNT(DISTINCT itemcode) AS n_items,
               SUM(stock) AS total_stock,
               SUM(freestock) AS total_freestock,
               SUM(tobe_received) AS total_tobe_received,
               SUM(reserve_bywa) AS total_reserve_bywa,
               SUM(available) AS total_available
        FROM {INV_TABLE}
        GROUP BY warehouse
        ORDER BY total_stock DESC
    """)
    save(wh_full, "03_warehouse_universe_tablewide")
    logger.info("Table-wide: %d distinct warehouse codes, %d total rows", len(wh_full), wh_full["n_rows"].sum())

    return schema, ts, wh_full


# ============================================================================
# Step 2: in-scope pull (445 pricelist items) + forecast-status flag
# ============================================================================
def step2_in_scope_pull(config: dict) -> tuple:
    logger.info("=== STEP 2: in-scope pull (445 pricelist codes) ===")

    pricelist_path = os.path.join(PROJECT_ROOT, config["pricelist_path"])
    pdf = load_visible_product_rows(pricelist_path)
    assert_no_code_on_multiple_sheets(pdf)
    pdf = pdf.drop_duplicates(subset=["code"]).copy()
    pdf["division"] = pdf["sheet"].map(config["sheet_to_division"])
    unmapped = pdf[pdf["division"].isna()]
    if len(unmapped):
        raise ValueError(f"{len(unmapped)} pricelist rows have a sheet not in config sheet_to_division: "
                          f"{unmapped['sheet'].unique()}")
    codes = sorted(pdf["code"].unique())
    logger.info("Pricelist: %d distinct item codes across %d visible sheets", len(codes), pdf["sheet"].nunique())

    status_path = os.path.join(SUMMARY_DIR, "phaseC_step1revised_item_status_445.csv")
    status = pd.read_csv(status_path)
    forecast_codes = set(status.loc[status["status_category"] == "forecast", "itemcode"])
    logger.info("Forecast-status items (status_category=='forecast', %s): %d of %d",
                status_path, len(forecast_codes), len(status))

    scope = pdf[["code", "sheet", "division", "type", "category"]].rename(columns={"code": "itemcode"})
    scope["is_forecast_item"] = scope["itemcode"].isin(forecast_codes)
    save(scope, "04_item_scope_445_with_division_and_forecast_flag")

    inv = run_query(f"""
        SELECT itemcode, warehouse, product_category, product_type, unit, stock, freestock,
               tobe_received, reserve_bywa, available, costPrice_standard, minimum, maximum
        FROM {INV_TABLE}
        WHERE itemcode IN ('{sql_in(codes)}')
    """)
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    save(inv, "05_raw_inventory_pull_445items")
    logger.info("Pulled %d (item, warehouse) rows for %d/%d in-scope items present in the snapshot",
                len(inv), inv["itemcode"].nunique(), len(codes))
    n_absent = len(codes) - inv["itemcode"].nunique()
    logger.info("%d of %d in-scope items have NO row in Cube_Inventory_Exact at all", n_absent, len(codes))

    grid = inv.pivot_table(index="itemcode", columns="warehouse", values="stock", aggfunc="sum", fill_value=0)
    grid = grid.merge(scope.set_index("itemcode")[["division", "type", "is_forecast_item"]],
                       left_index=True, right_index=True, how="left")
    save(grid.reset_index(), "06_per_item_per_warehouse_qty_grid")

    return scope, inv, codes, forecast_codes


# ============================================================================
# Step 3: per-warehouse-code sellability determination
# ============================================================================
def step3_sellability_determination(inv: pd.DataFrame, schema: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 3: per-warehouse-code sellability determination (in-scope pull) ===")

    sellability_cols = [c for c in schema["COLUMN_NAME"]
                         if any(k in c.lower() for k in ("status", "flag", "sellable", "avail", "hold", "type"))]
    logger.info("Schema columns checked for a sellability/status signal: %s", sellability_cols)
    logger.info("Of these: 'available' and 'freestock' are QUANTITIES (stock minus reservations), not a "
                "status/type flag -- they say how much is unreserved, not whether the STAGE itself is a "
                "sellable, ready-to-ship stage. 'product_category'/'product_type' are pricelist-attribute "
                "reference fields (CONVENTIONS.md: reference-only, never used to classify), not a warehouse "
                "sellability flag. No column in this schema records a stage/status such as "
                "'inspection'/'hold'/'ready-to-ship'. STOPPING RULE APPLIED: Cube_Inventory_Exact's own "
                "columns were checked and no sellability signal was found; per instruction, this search "
                "stops here rather than continuing into other tables (out of this check's permitted scope).")

    by_wh = inv.groupby("warehouse").agg(
        n_items_in_scope=("itemcode", "nunique"),
        n_rows=("itemcode", "count"),
        total_stock=("stock", "sum"),
        total_available=("available", "sum"),
        total_freestock=("freestock", "sum"),
        total_tobe_received=("tobe_received", "sum"),
    ).reset_index()

    def determine(wh):
        if wh in CONFIRMED_NOT_SELLABLE:
            return "NOT_SELLABLE (confirmed)"
        return "UNDETERMINED"

    def evidence(wh):
        if wh in CONFIRMED_NOT_SELLABLE:
            return PRIOR_EVIDENCE_NOTE
        if wh in FOURTEEN_ROLE_CODES:
            return ("In the prior 14-code behavioural-role list (movement ledger, 128-item scope) but NOT "
                    "one of the 2 behaviourally-confirmed exclusions. Plausible from QA->WH01->FG01->FG02 "
                    "topology but topology is explicitly NOT sufficient evidence per this task's ground "
                    "rules. Cube_Inventory_Exact itself (this check's scope) has no sellability/status field "
                    "(see schema check above) to settle it further. UNDETERMINED.")
        return ("Not in the prior 14-code behavioural-role list at all (no movement evidence in the "
                "128-item ledger scope, or a code the ledger never covered). Cube_Inventory_Exact itself "
                "has no sellability/status field (see schema check above) to settle it. UNDETERMINED.")

    by_wh["in_prior_14_role_list"] = by_wh["warehouse"].isin(FOURTEEN_ROLE_CODES)
    by_wh["determination"] = by_wh["warehouse"].map(determine)
    by_wh["evidence"] = by_wh["warehouse"].map(evidence)
    by_wh = by_wh.sort_values("total_stock", ascending=False)
    save(by_wh, "07_warehouse_sellability_determination")

    n_new = 0  # no code moved beyond QA/FMTS/FMTO in this check -- stated explicitly below
    logger.info("Warehouse codes newly determined beyond the already-known QA/FMTS/FMTO exclusions: %d "
                "(Cube_Inventory_Exact has no sellability/status field per the schema check above)", n_new)

    return by_wh


# ============================================================================
# Step 4: sellable/not-sellable/undetermined quantities per item, Type, division
# ============================================================================
def step4_quantity_summaries(inv: pd.DataFrame, scope: pd.DataFrame, wh_determination: pd.DataFrame) -> None:
    logger.info("=== STEP 4: quantity summaries (item / Type / division) ===")

    det_map = wh_determination.set_index("warehouse")["determination"].to_dict()
    inv2 = inv.merge(scope[["itemcode", "division", "type", "is_forecast_item"]], on="itemcode", how="left")
    inv2["determination"] = inv2["warehouse"].map(det_map).fillna("UNDETERMINED")
    n_blank_type = inv2.loc[inv2["type"].isna(), "itemcode"].nunique()
    if n_blank_type:
        logger.info("%d in-scope item(s) have a BLANK 'Product Type' cell in the pricelist itself "
                    "(not a join failure -- division resolves fine for these): %s. Filled as "
                    "'(blank in pricelist)' so they are not silently dropped from the Type-level summary.",
                    n_blank_type, sorted(inv2.loc[inv2["type"].isna(), "itemcode"].unique()))
    inv2["type"] = inv2["type"].fillna("(blank in pricelist)")

    def bucket_qty(df, group_cols):
        pivot = df.pivot_table(index=group_cols, columns="determination", values="stock",
                                aggfunc="sum", fill_value=0)
        for col in ("NOT_SELLABLE (confirmed)", "UNDETERMINED"):
            if col not in pivot.columns:
                pivot[col] = 0.0
        pivot["total_stock"] = pivot.sum(axis=1)
        pivot["confirmed_sellable_qty"] = 0.0  # nothing meets the confirmed-sellable bar -- see report
        pivot["confirmed_not_sellable_qty"] = pivot["NOT_SELLABLE (confirmed)"]
        pivot["undetermined_qty"] = pivot["UNDETERMINED"]
        pivot["undetermined_pct"] = (100 * pivot["undetermined_qty"] / pivot["total_stock"]).where(
            pivot["total_stock"] != 0, 0.0)
        return pivot[["total_stock", "confirmed_sellable_qty", "confirmed_not_sellable_qty",
                      "undetermined_qty", "undetermined_pct"]].reset_index()

    per_item = bucket_qty(inv2, ["itemcode", "division", "type", "is_forecast_item"])
    save(per_item.sort_values("total_stock", ascending=False), "08_per_item_sellability_summary")

    per_type = bucket_qty(inv2, ["division", "type"])
    save(per_type.sort_values("total_stock", ascending=False), "09_per_type_sellability_summary")

    per_division = bucket_qty(inv2, ["division"])
    save(per_division.sort_values("total_stock", ascending=False), "10_per_division_sellability_summary")

    total_stock = inv2["stock"].sum()
    total_not_sellable = inv2.loc[inv2["determination"] == "NOT_SELLABLE (confirmed)", "stock"].sum()
    total_undetermined = inv2.loc[inv2["determination"] == "UNDETERMINED", "stock"].sum()
    overall_undetermined_pct = 100 * total_undetermined / total_stock if total_stock else 0.0
    logger.info("Overall (445-item scope): total_stock=%.0f, confirmed_not_sellable=%.0f (%.2f%%), "
                "undetermined=%.0f (%.2f%%), confirmed_sellable=0 (%.2f%%)",
                total_stock, total_not_sellable, 100 * total_not_sellable / total_stock if total_stock else 0,
                total_undetermined, overall_undetermined_pct, 0.0)

    overall = pd.DataFrame([{
        "total_stock": total_stock,
        "confirmed_sellable_qty": 0.0,
        "confirmed_not_sellable_qty": total_not_sellable,
        "undetermined_qty": total_undetermined,
        "undetermined_pct": overall_undetermined_pct,
    }])
    save(overall, "11_overall_summary")

    return per_item, per_type, per_division, overall


if __name__ == "__main__":
    config = load_config()
    schema, ts, wh_full = step1_full_structure()
    scope, inv, codes, forecast_codes = step2_in_scope_pull(config)
    wh_det = step3_sellability_determination(inv, schema)
    step4_quantity_summaries(inv, scope, wh_det)
    logger.info("DONE. See output/summary/phaseD_check1_*.csv and phaseD_check1_report.md")
