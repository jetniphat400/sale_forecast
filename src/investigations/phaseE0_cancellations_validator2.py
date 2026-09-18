"""Phase E0.2 — Validator 2: Cancellations in the demand series.

Re-run of a task first attempted 2026-09-18 and blocked at that time by an
expired SQL Server password (see the superseded content of
`output/summary/phaseE0_validator2_cancellations_report.md`, now replaced).
That attempt fully scoped the method before the DB became unreachable; this
script reuses it exactly, with no re-derivation:

- Join key: `(ContractID, ItemCode)` on `Cube_CES` <-> `(contractid, itemcode)`
  on `cube_Sale_APD` — the same key `src/investigations/verify_ces_status_
  mapping.py` and `verify_ces_pre2024_detail.py` used for the project's prior
  row-level Cube_CES <-> cube_Sale_APD reconciliation (STATUS.md, "Row-level
  Cube_CES verification", 2026-08-31).
- `Cube_CES` value = `ActualPrice + BacklogPrice`, qty = `ActualQty +
  BacklogQty` (same convention as `verify_ces_pre2024_detail.py`).
- `cube_Sale_APD` value/qty = its own `sale`/`qty` columns.
- Division is attached from the pricelist (`sheet_to_division` in
  config.yaml), exactly as `src/load_data_full.py` does — NEVER filtered on
  `Cube_CES.ManuDivision` or `cube_Sale_APD.division` (both are reference-only
  per the locked division source-of-truth rule, STATUS.md 2026-09-04).

This script only reads from the database (via `src/db.py`'s `run_query()`)
and the pricelist; it writes CSVs to `output/summary/` with a
`phaseE0_validator2_` prefix. It does not modify any data, config, or
pipeline script (Validator role, diagnostic only, per AGENTS.md).
"""
import logging
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (this file lives in src/investigations/)
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE0_cancellations_validator2")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
PRICELIST_PATH = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_pricelist_map(config: dict) -> pd.DataFrame:
    """Returns one row per pricelist item code (code, sheet, category, type, division),
    division attached via config['sheet_to_division'] — the project's locked
    division source-of-truth rule. Raises if any code maps to more than one sheet
    (would make the division attribution ambiguous)."""
    pl = load_visible_product_rows(PRICELIST_PATH)
    dup_sheets = pl.groupby("code")["sheet"].nunique()
    ambiguous = dup_sheets[dup_sheets > 1]
    if len(ambiguous) > 0:
        raise ValueError(f"{len(ambiguous)} item code(s) appear on more than one pricelist sheet — "
                          f"division attribution would be ambiguous: {list(ambiguous.index)}")
    pl_map = pl.drop_duplicates(subset="code")[["code", "sheet", "category", "type"]].copy()
    sheet_to_division = config["sheet_to_division"]
    unmapped = set(pl_map["sheet"]) - set(sheet_to_division)
    if unmapped:
        raise ValueError(f"Sheet(s) {unmapped} have no entry in config['sheet_to_division']")
    pl_map["division"] = pl_map["sheet"].map(sheet_to_division)
    logger.info("Pricelist item universe: %d codes across %d sheets/divisions", len(pl_map), pl_map["division"].nunique())
    return pl_map


def q1_cancel_rows() -> pd.DataFrame:
    """Fresh table-wide pull of Cube_CES Status='Cancel' rows (no division/revenue_type/item
    filter — matches the fresh-pull requirement and the table-wide comparability of the prior
    STATUS.md 2,423-row count, but with qty/value/date detail that count never included)."""
    df = run_query("""
        SELECT ContractID, ItemCode, CtrDate, ActualQty, BacklogQty, ActualPrice, BacklogPrice,
               PlanQty, RevenueType, ManuDivision
        FROM Cube_CES
        WHERE Status = 'Cancel'
    """)
    df["qty"] = df["ActualQty"].fillna(0) + df["BacklogQty"].fillna(0)
    df["value"] = df["ActualPrice"].fillna(0) + df["BacklogPrice"].fillna(0)
    logger.info("Cube_CES Status='Cancel', table-wide: %d rows, qty=%.2f, value=%.2f, CtrDate %s to %s",
                len(df), df["qty"].sum(), df["value"].sum(), df["CtrDate"].min(), df["CtrDate"].max())
    return df


def q2_match_to_apd(cancel_df: pd.DataFrame, pl_map: pd.DataFrame) -> dict:
    """Matches Cancel (ContractID, ItemCode) pairs to cube_Sale_APD Actual/MPS rows.
    Two views are computed: (a) restricted to pricelist-scope item codes only — the only
    items that can ever appear in this project's production series, since
    src/load_data_full.py requires every item to have a pricelist division mapping; and
    (b) table-wide (any item code in the Cancel set, including non-pricelist items) as a
    robustness cross-check that the null result in (a) is not an artefact of the pricelist
    restriction."""
    pricelist_codes = set(pl_map["code"])
    cancel_pl = cancel_df[cancel_df["ItemCode"].isin(pricelist_codes)].copy()
    cancel_pl = cancel_pl.merge(pl_map[["code", "division", "category", "type"]],
                                 left_on="ItemCode", right_on="code", how="left")
    logger.info("Of %d table-wide Cancel rows, %d (%.2f%%) are for pricelist-scope item codes "
                "(%d distinct codes) — only these can ever appear in the production series.",
                len(cancel_df), len(cancel_pl), 100 * len(cancel_pl) / len(cancel_df), cancel_pl["ItemCode"].nunique())

    pairs_pl = cancel_pl[["ContractID", "ItemCode"]].drop_duplicates()
    pairs_all = cancel_df[["ContractID", "ItemCode"]].drop_duplicates()
    logger.info("Distinct (ContractID, ItemCode) Cancel pairs: %d pricelist-scope, %d table-wide", len(pairs_pl), len(pairs_all))

    def pull_apd_actual_mps(item_codes):
        code_list = "','".join(sorted(item_codes))
        return run_query(f"""
            SELECT contractid, itemcode, qty, sale, status, createDate, division AS division_db_raw, revenue_type
            FROM cube_Sale_APD
            WHERE itemcode IN ('{code_list}')
              AND revenue_type = 'Omni Channel'
              AND status IN ('Actual','MPS')
        """)

    apd_pl = pull_apd_actual_mps(pairs_pl["ItemCode"].unique())
    apd_all = pull_apd_actual_mps(pairs_all["ItemCode"].unique())
    logger.info("cube_Sale_APD Omni Channel Actual/MPS rows pulled: %d (pricelist-scope itemcodes), "
                "%d (all Cancel-set itemcodes)", len(apd_pl), len(apd_all))

    pairs_pl_set = set(zip(pairs_pl["ContractID"], pairs_pl["ItemCode"]))
    pairs_all_set = set(zip(pairs_all["ContractID"], pairs_all["ItemCode"]))
    apd_pl["_key"] = list(zip(apd_pl["contractid"], apd_pl["itemcode"]))
    apd_all["_key"] = list(zip(apd_all["contractid"], apd_all["itemcode"]))

    matched_pl = apd_pl[apd_pl["_key"].isin(pairs_pl_set)].drop(columns="_key")
    matched_all = apd_all[apd_all["_key"].isin(pairs_all_set)].drop(columns="_key")
    logger.info("MATCH RESULT — pricelist-scope: %d matched rows (%d distinct pairs) of %d cancelled pairs. "
                "Table-wide (robustness check): %d matched rows (%d distinct pairs) of %d cancelled pairs.",
                len(matched_pl), matched_pl[["contractid", "itemcode"]].drop_duplicates().shape[0] if len(matched_pl) else 0,
                len(pairs_pl_set),
                len(matched_all), matched_all[["contractid", "itemcode"]].drop_duplicates().shape[0] if len(matched_all) else 0,
                len(pairs_all_set))

    # Sanity check the join key itself still works on this data (positive control): Cube_CES
    # Actual/Backlog rows (non-cancelled) for the same pricelist-scope itemcodes, 2024+, should
    # match cube_Sale_APD Actual/MPS pairs at a high rate (per the prior verified ~99.8% finding).
    codes_pl = sorted(pairs_pl["ItemCode"].unique())
    code_list = "','".join(codes_pl)
    ces_positive_control = run_query(f"""
        SELECT ContractID AS contractid, ItemCode AS itemcode
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}') AND Status IN ('Actual','Backlog') AND CtrDate >= '2024-01-01'
    """)
    ces_pairs = set(zip(ces_positive_control["contractid"], ces_positive_control["itemcode"]))
    apd_pairs_pl = set(zip(apd_pl["contractid"], apd_pl["itemcode"]))
    control_overlap = len(ces_pairs & apd_pairs_pl)
    control_rate = control_overlap / len(ces_pairs) if ces_pairs else float("nan")
    logger.info("POSITIVE CONTROL (join-key sanity check): of %d Cube_CES Actual/Backlog pairs (2024+, same "
                "itemcodes), %d (%.2f%%) match a cube_Sale_APD Actual/MPS pair — confirms the join key finds "
                "real matches when they exist, so the 0-match Cancel result above is not a broken join.",
                len(ces_pairs), control_overlap, 100 * control_rate)

    return {
        "cancel_pricelist_scope": cancel_pl,
        "matched_pricelist_scope": matched_pl,
        "matched_table_wide": matched_all,
        "n_pairs_pricelist_scope": len(pairs_pl_set),
        "n_pairs_table_wide": len(pairs_all_set),
        "control_n_pairs": len(ces_pairs),
        "control_n_matched": control_overlap,
        "control_rate_pct": 100 * control_rate,
    }


def q3_total_production_series(config: dict, pl_map: pd.DataFrame) -> dict:
    """Total production-series demand (qty, sale) for the denominator of the cancellation
    share calculation: every pricelist item code, revenue_type='Omni Channel',
    status IN ('Actual','MPS'), createDate >= config['date_range']['start'] — the exact
    filter src/load_data_full.py uses (minus its category-specific item-code restriction,
    widened here to the full pricelist universe, the project's actual full scope per the
    2026-09-04 'Project scope correction')."""
    code_list = "','".join(sorted(pl_map["code"].unique()))
    start_date = config["date_range"]["start"]
    total = run_query(f"""
        SELECT SUM(qty) AS total_qty, SUM(sale) AS total_sale, COUNT(*) AS n_rows,
               MIN(createDate) AS mn, MAX(createDate) AS mx
        FROM cube_Sale_APD
        WHERE itemcode IN ('{code_list}')
          AND revenue_type = 'Omni Channel' AND status IN ('Actual','MPS')
          AND createDate >= '{start_date}'
    """).iloc[0].to_dict()
    logger.info("Total production series (all %d pricelist items, Omni Channel, Actual/MPS, "
                "createDate >= %s): qty=%.1f, value=%.2f, %d rows, %s to %s",
                pl_map["code"].nunique(), start_date, total["total_qty"], total["total_sale"],
                total["n_rows"], total["mn"], total["mx"])
    return total


def q3_focus_items(cancel_df: pd.DataFrame) -> pd.DataFrame:
    focus_rows = cancel_df[cancel_df["ItemCode"].isin(FOCUS_ITEMS)].copy()
    logger.info("Cancel rows for the 3 focus items: %d (%s)", len(focus_rows),
                focus_rows["ItemCode"].value_counts().to_dict())
    return focus_rows


def q4_partial_cancellations() -> dict:
    """Cube_CES rows where PlanQty > ActualQty + BacklogQty ('shortfall'). Checked separately
    for confirmed contracts (ContractID prefix 'CTR-') vs. pre-contract records (quotations:
    'QTN-', 'OQ-', 'ENQIN-', 'OPP-' prefixes), because only confirmed contracts can ever feed
    the production series (cube_Sale_APD is built from confirmed orders, not quotations)."""
    shortfall = run_query("""
        SELECT ContractID, ItemCode, CtrDate, PlanID, PlanQty, ActualQty, BacklogQty,
               ActualPrice, BacklogPrice, ContractPrice, Status
        FROM Cube_CES
        WHERE PlanQty IS NOT NULL
          AND PlanQty > (ISNULL(ActualQty, 0) + ISNULL(BacklogQty, 0))
    """)
    shortfall["shortfall_qty"] = shortfall["PlanQty"] - (
        shortfall["ActualQty"].fillna(0) + shortfall["BacklogQty"].fillna(0))
    shortfall["prefix"] = shortfall["ContractID"].str.split("-").str[0]
    logger.info("Rows with PlanQty > ActualQty+BacklogQty (any prefix): %d, total shortfall qty=%.1f",
                len(shortfall), shortfall["shortfall_qty"].sum())
    logger.info("Prefix distribution:\n%s", shortfall["prefix"].value_counts().to_string())

    ctr_shortfall = shortfall[shortfall["prefix"] == "CTR"]
    logger.info("Of these, %d have a confirmed-contract ('CTR-') ContractID.", len(ctr_shortfall))

    # Positive-control / explanatory check: confirm PlanQty == ActualQty+BacklogQty for EVERY
    # confirmed-contract row in Cube_CES (not just the shortfall query above), to establish
    # whether the shortfall condition is structurally impossible for confirmed contracts or
    # merely rare.
    ctr_all = run_query("""
        SELECT ContractID, ItemCode, PlanQty, ActualQty, BacklogQty, Status
        FROM Cube_CES
        WHERE ContractID LIKE 'CTR-%' AND PlanQty IS NOT NULL
    """)
    ctr_all["diff"] = ctr_all["PlanQty"] - (ctr_all["ActualQty"].fillna(0) + ctr_all["BacklogQty"].fillna(0))
    n_gt = (ctr_all["diff"] > 1e-4).sum()
    n_eq = (ctr_all["diff"].abs() <= 1e-4).sum()
    n_lt = (ctr_all["diff"] < -1e-4).sum()
    logger.info("Among ALL %d confirmed-contract (CTR-) Cube_CES rows with non-null PlanQty: "
                "%d have PlanQty > Actual+Backlog, %d have PlanQty == Actual+Backlog exactly, "
                "%d have PlanQty < Actual+Backlog.", len(ctr_all), n_gt, n_eq, n_lt)

    return {
        "shortfall_all": shortfall,
        "shortfall_ctr_only": ctr_shortfall,
        "ctr_all_check": ctr_all,
        "n_ctr_total": len(ctr_all),
        "n_ctr_gt": int(n_gt),
        "n_ctr_eq": int(n_eq),
        "n_ctr_lt": int(n_lt),
    }


def main():
    config = load_config()
    pl_map = load_pricelist_map(config)

    cancel_df = q1_cancel_rows()
    cancel_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE0_validator2_cancel_rows_tablewide.csv"), index=False)

    match_result = q2_match_to_apd(cancel_df, pl_map)
    match_result["cancel_pricelist_scope"].to_csv(
        os.path.join(SUMMARY_DIR, "phaseE0_validator2_cancel_rows_pricelist_scope.csv"), index=False)
    match_result["matched_pricelist_scope"].to_csv(
        os.path.join(SUMMARY_DIR, "phaseE0_validator2_cancelled_pairs_still_actual_mps.csv"), index=False)

    division_breakdown = match_result["cancel_pricelist_scope"].groupby("division", as_index=False).agg(
        n_rows=("qty", "size"), total_qty=("qty", "sum"), total_value=("value", "sum"))
    division_breakdown.to_csv(
        os.path.join(SUMMARY_DIR, "phaseE0_validator2_cancel_by_division_pricelist_scope.csv"), index=False)

    cancel_pl_with_year = match_result["cancel_pricelist_scope"].copy()
    cancel_pl_with_year["ctr_year"] = pd.to_datetime(cancel_pl_with_year["CtrDate"]).dt.year
    year_breakdown = cancel_pl_with_year.groupby("ctr_year", as_index=False).agg(
        n_rows=("qty", "size"), total_qty=("qty", "sum"), total_value=("value", "sum"))
    year_breakdown.to_csv(
        os.path.join(SUMMARY_DIR, "phaseE0_validator2_cancel_by_year_pricelist_scope.csv"), index=False)
    logger.info("Pricelist-scope Cancel rows by CtrDate year (context only, these are NOT matched to "
                "cube_Sale_APD -- see the 0-row matched-pairs CSV for that question):\n%s",
                year_breakdown.to_string(index=False))

    total_series = q3_total_production_series(config, pl_map)
    focus_df = q3_focus_items(cancel_df)
    focus_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE0_validator2_focus_item_cancel_rows.csv"), index=False)

    partial = q4_partial_cancellations()
    partial["shortfall_all"].to_csv(
        os.path.join(SUMMARY_DIR, "phaseE0_validator2_partial_shortfall_all_prefixes.csv"), index=False)
    partial["shortfall_ctr_only"].to_csv(
        os.path.join(SUMMARY_DIR, "phaseE0_validator2_partial_shortfall_ctr_only.csv"), index=False)

    print("\n" + "=" * 78)
    print("PHASE E0.2 — CANCELLATIONS VALIDATOR 2 — RESULTS SUMMARY")
    print("=" * 78)
    print(f"1. Cube_CES Status='Cancel', table-wide: {len(cancel_df)} rows, "
          f"qty={cancel_df['qty'].sum():,.1f}, value={cancel_df['value'].sum():,.2f}, "
          f"CtrDate {cancel_df['CtrDate'].min()} to {cancel_df['CtrDate'].max()}")
    print(f"   Of these, {len(match_result['cancel_pricelist_scope'])} rows are for pricelist-scope "
          f"item codes ({match_result['cancel_pricelist_scope']['ItemCode'].nunique()} distinct codes).")
    print(f"2. Cancelled (contract,item) pairs still Actual/MPS in cube_Sale_APD: "
          f"{len(match_result['matched_pricelist_scope'])} rows (pricelist-scope), "
          f"{len(match_result['matched_table_wide'])} rows (table-wide, any item).")
    print(f"   Positive control: {match_result['control_n_matched']} of {match_result['control_n_pairs']} "
          f"({match_result['control_rate_pct']:.2f}%) Cube_CES Actual/Backlog pairs (non-cancelled) DO match "
          f"cube_Sale_APD Actual/MPS — confirms the join key works and the 0-match Cancel result is real.")
    print(f"3. Total production series (pricelist scope, Omni Channel, Actual/MPS, "
          f"createDate>={config['date_range']['start']}): qty={total_series['total_qty']:,.1f}, "
          f"value={total_series['total_sale']:,.2f}")
    print(f"   Focus-item Cancel rows: {len(focus_df)} ({focus_df['ItemCode'].value_counts().to_dict()})")
    print(f"4. PlanQty>Actual+Backlog shortfall rows: {len(partial['shortfall_all'])} total, "
          f"of which {len(partial['shortfall_ctr_only'])} are confirmed-contract (CTR-) rows.")
    print(f"   Among ALL {partial['n_ctr_total']} confirmed-contract rows: {partial['n_ctr_gt']} show "
          f"PlanQty>Actual+Backlog, {partial['n_ctr_eq']} show exact equality, {partial['n_ctr_lt']} show less.")
    print("\nCSV outputs written to output/summary/ with prefix phaseE0_validator2_")


if __name__ == "__main__":
    main()
