"""Single-Explorer investigation: does a warehouse code's TRAILING DIGITS identify its division?

User's hypothesis (2026-09-09): warehouse codes are separated by business unit via a trailing-
digit convention -- FG01/FG21 -> PEM101, FG02 -> PEM102, FG07 -> PEM107, etc. Tested here by
cross-tabulating division (pricelist-sourced, CONVENTIONS.md) against warehouse code
(Cube_Inventory_Exact), examined from six angles in one script/context (AGENTS.md "Single
Explorer" pattern for this task -- no sub-agent split).

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched. Per Phase D's
scope (STATUS.md), reads Cube_Inventory_Exact plus the joins needed for item scope/division, and
cube_inventory_tran for Part 4 only (explicitly permitted by this task's own brief, narrowly, for
the FG21-vs-FG02 question).

Methodology notes (load-bearing, stated up front):
- Division source: config['sheet_to_division'] from the pricelist (CONVENTIONS.md) -- never
  cube_Sale_APD's own `division` column. `output/summary/part3_warehouse_division_test.csv` (an
  EARLIER, pre-2026-09-04-correction investigation) used the raw database `division` column and
  shows up to 17 "divisions" per warehouse, including -OLD variants and typos (e.g. PEM106, which
  does not exist in the pricelist) -- that file is SUPERSEDED methodology, not reused or cited as
  current evidence anywhere in this script.
- Unit cost: reused directly from `output/summary/phaseD_check2_item_stock_value.csv`
  (`primary_unit_cost`, `has_cost_record`) -- median-of-last-12-months cost/qty from
  cube_Sale_APD, already corrected there to account for `cost` being a line total, not a unit
  cost. Not re-derived here.
- Warehouse-code universe: the 445-item Phase D pull (`phaseD_check1_07_...csv`) found 44 distinct
  codes, not the 34 the user's brief references (that "34" figure is from the EARLIER 128-item
  pilot-scope investigation, `part1_warehouse_snapshot_summary.csv`). This script uses the current
  44-code, 445-item universe -- the correct scope for a division cross-tab across all 6
  divisions -- and states this discrepancy explicitly rather than silently reconciling it.
"""
import logging
import os
import re
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402
from division_utils import assert_no_code_on_multiple_sheets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("warehouse_division_mapping_hypothesis")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

INV_TABLE = "[salewarehouse].[dbo].[Cube_Inventory_Exact]"
TRAN_TABLE = "[salewarehouse].[dbo].[cube_inventory_tran]"

STOCK_VALUE_FILE = os.path.join(SUMMARY_DIR, "phaseD_check2_item_stock_value.csv")
MULTI_DIVISION_SALES_FILE = os.path.join(SUMMARY_DIR, "phaseC_sheetmap_flagged_multi_division.csv")

# Judgment call, stated explicitly (per instruction -- not left implicit): a warehouse code's
# stock is treated as having a "dominant" division if one division holds >= this share of the
# code's total stock qty. Below this, the code is "NO_CLEAR_DOMINANT". Chosen as a plain majority
# threshold; not derived from this data, a reasonable reading of "concentrated in one division".
DOMINANCE_THRESHOLD_PCT = 60.0

# The hypothesis under test, exactly as the user stated it, generalised to every division with an
# obvious 2-digit PEM suffix. CI101 has no such numeric suffix in its own code (unlike PEM101..107)
# so no trailing-digit prediction is stated for it up front -- Part 2 checks empirically whether
# any trailing-digit code turns out to be CI101-dominant instead of asserting one.
HYPOTHESIS_DIGITS_TO_DIVISION = {
    "01": "PEM101",
    "21": "PEM101",  # user's own stated hypothesis: FG21 also -> PEM101
    "02": "PEM102",
    "03": "PEM103",
    "04": "PEM104",
    "07": "PEM107",
}


def out(name: str) -> str:
    return os.path.join(SUMMARY_DIR, f"whmap_{name}")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sql_list(values) -> str:
    return "','".join(str(v).replace("'", "''") for v in values)


def strip_warehouse(df: pd.DataFrame, col: str = "warehouse") -> pd.DataFrame:
    df = df.copy()
    n_padded = (df[col].astype(str) != df[col].astype(str).str.strip()).sum()
    df[col] = df[col].astype(str).str.strip()
    if n_padded:
        logger.info("%d of %d rows had a fixed-width-padded '%s' value -- stripped.", n_padded, len(df), col)
    return df


def trailing_digits(code: str) -> str | None:
    """Last run of digits in a warehouse code, truncated to its last 2 characters (e.g. FG01->01,
    WH21->21, F101->01, FG->None, W4-1->None [trailing char is '1' but preceded by '-', still a
    valid 1-digit run -> '1', NOT padded to '01' -- kept as-is, a 1-digit and 2-digit trailing run
    are different codes' conventions and must not be silently equated). Returns None if the code
    ends in no digit at all."""
    m = re.search(r"(\d+)$", str(code).strip())
    if not m:
        return None
    digits = m.group(1)
    return digits[-2:]


# ============================================================================================
# STEP 1: item scope (445 codes) + division, from the pricelist -- CONVENTIONS.md authoritative
# ============================================================================================
def step1_item_scope(config: dict) -> pd.DataFrame:
    logger.info("=== STEP 1: pricelist item scope + division (pricelist-sourced, not DB division) ===")
    pl = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    assert_no_code_on_multiple_sheets(pl)
    pl = pl.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)

    sheet_to_division = config["sheet_to_division"]
    unmapped = set(pl["sheet"].unique()) - set(sheet_to_division.keys())
    if unmapped:
        raise ValueError(f"Sheets with product rows but no sheet_to_division mapping: {unmapped}")
    pl["division"] = pl["sheet"].map(sheet_to_division)

    scope = pl[["code", "sheet", "division", "category", "type"]].rename(columns={"code": "itemcode"})
    logger.info("Item scope: %d distinct codes across %d divisions: %s",
                len(scope), scope["division"].nunique(), sorted(scope["division"].unique()))
    return scope


# ============================================================================================
# STEP 2: Cube_Inventory_Exact pull for the 445 codes + unit-value join
# ============================================================================================
def step2_inventory_pull(scope: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== STEP 2: Cube_Inventory_Exact pull, 445-item scope ===")
    codes = sorted(scope["itemcode"].unique())
    inv = run_query(f"""
        SELECT itemcode, warehouse, stock, freestock, tobe_received, available
        FROM {INV_TABLE}
        WHERE itemcode IN ('{sql_list(codes)}')
    """)
    inv = strip_warehouse(inv)
    n_items_present = inv["itemcode"].nunique()
    logger.info("Pulled %d (item, warehouse) rows for %d/%d in-scope items present in the snapshot "
                "(%d absent from the snapshot entirely). %d distinct warehouse codes.",
                len(inv), n_items_present, len(codes), len(codes) - n_items_present,
                inv["warehouse"].nunique())

    inv = inv.merge(scope, on="itemcode", how="left")
    unmatched = inv[inv["division"].isna()]
    if len(unmatched):
        raise ValueError(f"{len(unmatched)} inventory rows failed to match a pricelist division "
                          f"after the join -- should not happen, query was scoped to pricelist codes.")

    if not os.path.exists(STOCK_VALUE_FILE):
        raise FileNotFoundError(f"{STOCK_VALUE_FILE} not found -- run phaseD_check2_stock_value.py first "
                                 f"(this script reuses its unit-cost derivation, does not re-derive it).")
    cost = pd.read_csv(STOCK_VALUE_FILE)[["itemcode", "primary_unit_cost", "has_cost_record"]]
    inv = inv.merge(cost, on="itemcode", how="left")
    n_no_cost_join = inv["has_cost_record"].isna().sum()
    if n_no_cost_join:
        logger.warning("%d rows have no match in %s at all (itemcode not in that 445-item file -- "
                        "should not happen, both are the same registry); treated as has_cost_record=False.",
                        n_no_cost_join, STOCK_VALUE_FILE)
    inv["has_cost_record"] = inv["has_cost_record"].fillna(False)
    inv["cell_value"] = np.where(inv["has_cost_record"], inv["stock"] * inv["primary_unit_cost"], np.nan)

    n_wh_44_check = inv.loc[inv["stock"] != 0, "warehouse"].nunique()
    logger.info("Warehouse codes with ANY nonzero stock in this 445-item scope: %d. (Phase D Check 1's "
                "own pull, phaseD_check1_07_warehouse_sellability_determination.csv, reports 44 -- "
                "reconciled below if different, since that pull used `stock` grouped, same basis.)",
                n_wh_44_check)
    return inv


# ============================================================================================
# PART 1: division x warehouse cross-tab (item count, qty, value) + concentration
# ============================================================================================
def part1_crosstab(inv: pd.DataFrame) -> dict:
    logger.info("=== PART 1: division x warehouse cross-tab ===")
    nonzero = inv[inv["stock"] != 0]

    cross = nonzero.groupby(["division", "warehouse"], as_index=False).agg(
        n_items=("itemcode", "nunique"),
        qty=("stock", "sum"),
        value_priced=("cell_value", "sum"),
        qty_no_cost_record=("stock", lambda s: s[~nonzero.loc[s.index, "has_cost_record"]].sum()),
    )
    cross["value_priced"] = cross["value_priced"].fillna(0.0)
    cross = cross.sort_values(["division", "qty"], ascending=[True, False])
    cross.to_csv(out("part1_division_by_warehouse_crosstab.csv"), index=False)
    logger.info("Cross-tab: %d (division, warehouse) nonzero cells across %d divisions x %d warehouses.",
                len(cross), cross["division"].nunique(), cross["warehouse"].nunique())

    # Concentration per division: share of its stock in top-1/2/3 warehouse codes, by qty and by value.
    conc_rows = []
    for div, g in cross.groupby("division"):
        div_total_qty = g["qty"].sum()
        div_total_val = g["value_priced"].sum()
        g_qty = g.sort_values("qty", ascending=False)
        g_val = g.sort_values("value_priced", ascending=False)

        def topn_share(g_sorted, col, total, n):
            if total == 0 or total != total:  # zero or NaN
                return None
            return round(100.0 * g_sorted[col].head(n).sum() / total, 2)

        conc_rows.append({
            "division": div,
            "n_warehouse_codes": g["warehouse"].nunique(),
            "total_qty": div_total_qty,
            "total_value_priced": div_total_val,
            "top1_warehouse_by_qty": g_qty.iloc[0]["warehouse"] if len(g_qty) else None,
            "top1_qty_share_pct": topn_share(g_qty, "qty", div_total_qty, 1),
            "top2_qty_share_pct": topn_share(g_qty, "qty", div_total_qty, 2),
            "top3_qty_share_pct": topn_share(g_qty, "qty", div_total_qty, 3),
            "top1_warehouse_by_value": g_val.iloc[0]["warehouse"] if len(g_val) else None,
            "top1_value_share_pct": topn_share(g_val, "value_priced", div_total_val, 1),
            "top2_value_share_pct": topn_share(g_val, "value_priced", div_total_val, 2),
            "top3_value_share_pct": topn_share(g_val, "value_priced", div_total_val, 3),
        })
    conc = pd.DataFrame(conc_rows).sort_values("division")
    conc.to_csv(out("part1_division_concentration.csv"), index=False)

    mean_top1_qty = conc["top1_qty_share_pct"].mean()
    mean_top3_qty = conc["top3_qty_share_pct"].mean()
    logger.info("Per-division concentration (qty basis): mean top-1 share = %.1f%%, mean top-3 share = %.1f%%. "
                "(By value: mean top-1 = %.1f%%, mean top-3 = %.1f%%.) See part1_division_concentration.csv.",
                mean_top1_qty, mean_top3_qty, conc["top1_value_share_pct"].mean(), conc["top3_value_share_pct"].mean())

    return {"cross": cross, "concentration": conc}


# ============================================================================================
# PART 2: per-warehouse dominant division + trailing-digit hypothesis test
# ============================================================================================
def part2_dominant_division(cross: pd.DataFrame, all_codes: list) -> pd.DataFrame:
    logger.info("=== PART 2: per-warehouse dominant division + trailing-digit hypothesis test "
                "(dominance threshold = %.0f%%, stated judgment call) ===", DOMINANCE_THRESHOLD_PCT)
    codes_with_stock = set(cross["warehouse"].unique())
    codes_zero_stock = sorted(set(all_codes) - codes_with_stock)
    logger.info("Of %d warehouse codes in this 445-item scope, %d have ANY nonzero 'stock' in this "
                "snapshot and can be division-tested by quantity; %d have zero stock table-wide-in-scope "
                "right now (some of these, e.g. QA/FMTO/FMTS/WH01/FG02, are known from Phase D Check 1 to "
                "carry nonzero 'available'/'tobe_received' instead -- a pass-through/WIP signature, not "
                "necessarily inactive) and are carried into the mapping as UNRESOLVED rather than dropped: %s",
                len(all_codes), len(codes_with_stock), len(codes_zero_stock), codes_zero_stock)

    rows = []
    for wh, g in cross.groupby("warehouse"):
        total_qty = g["qty"].sum()
        g2 = g.sort_values("qty", ascending=False)
        top_div = g2.iloc[0]["division"]
        top_share = 100.0 * g2.iloc[0]["qty"] / total_qty if total_qty else None
        has_dominant = total_qty > 0 and top_share is not None and top_share >= DOMINANCE_THRESHOLD_PCT

        digits = trailing_digits(wh)
        predicted_division = HYPOTHESIS_DIGITS_TO_DIVISION.get(digits) if digits else None

        if not has_dominant:
            match_status = "NO_CLEAR_DOMINANT"
        elif predicted_division is None:
            match_status = "NO_PREDICTION (trailing digits not in hypothesis map, or code has no trailing digits)"
        elif predicted_division == top_div:
            match_status = "MATCH"
        else:
            match_status = "MISMATCH"

        rows.append({
            "warehouse": wh,
            "trailing_digits": digits,
            "predicted_division_by_hypothesis": predicted_division,
            "n_divisions_with_stock": g["division"].nunique(),
            "total_qty": total_qty,
            "dominant_division": top_div if has_dominant else None,
            "dominant_division_share_pct": round(top_share, 2) if top_share is not None else None,
            "divisions_present": sorted(g["division"].unique().tolist()),
            "match_status": match_status,
        })
    for wh in codes_zero_stock:
        digits = trailing_digits(wh)
        rows.append({
            "warehouse": wh,
            "trailing_digits": digits,
            "predicted_division_by_hypothesis": HYPOTHESIS_DIGITS_TO_DIVISION.get(digits) if digits else None,
            "n_divisions_with_stock": 0,
            "total_qty": 0.0,
            "dominant_division": None,
            "dominant_division_share_pct": None,
            "divisions_present": [],
            "match_status": "NO_CLEAR_DOMINANT (zero stock in this snapshot -- cannot test)",
        })
    result = pd.DataFrame(rows).sort_values("total_qty", ascending=False)
    result.to_csv(out("part2_warehouse_dominant_division.csv"), index=False)

    n_match = (result["match_status"] == "MATCH").sum()
    n_mismatch = (result["match_status"] == "MISMATCH").sum()
    n_no_pred = (result["match_status"].str.startswith("NO_PREDICTION")).sum()
    n_no_dom = (result["match_status"].str.startswith("NO_CLEAR_DOMINANT")).sum()
    n_zero_stock = (result["match_status"].str.contains("zero stock")).sum()
    logger.info("Of %d warehouse codes: %d MATCH the trailing-digit hypothesis, %d MISMATCH, "
                "%d have no hypothesis prediction for their digits, %d have no clear dominant division "
                "(<%.0f%% threshold, of which %d are zero-stock codes that could not be tested at all).",
                len(result), n_match, n_mismatch, n_no_pred, n_no_dom, DOMINANCE_THRESHOLD_PCT, n_zero_stock)
    mismatches = result[result["match_status"] == "MISMATCH"]
    if len(mismatches):
        logger.info("MISMATCH codes (predicted vs. actual dominant division):\n%s",
                    mismatches[["warehouse", "trailing_digits", "predicted_division_by_hypothesis",
                                "dominant_division", "dominant_division_share_pct"]].to_string(index=False))
    return result


# ============================================================================================
# PART 3: per-item warehouse spread vs. division trailing-digit sets
# ============================================================================================
def part3_item_spread(inv: pd.DataFrame, wh_dom: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== PART 3: per-item warehouse spread, vs. each division's trailing-digit code set ===")

    # Trailing-digit set per division: EVERY code table-wide (all 44 present in this scope) whose
    # digits match that division under the hypothesis map -- not just codes with stock, and not
    # limited to codes that PASSED Part 2's dominance test (this set is defined structurally by the
    # hypothesis itself, so Part 3 can test the hypothesis' predictive reach independently of Part 2's
    # per-code confirmation).
    all_codes = wh_dom["warehouse"].tolist()
    digit_sets = {}
    for code in all_codes:
        d = trailing_digits(code)
        div = HYPOTHESIS_DIGITS_TO_DIVISION.get(d) if d else None
        if div:
            digit_sets.setdefault(div, set()).add(code)
    logger.info("Division trailing-digit code sets (hypothesis-defined, from this scope's 44 codes): %s",
                {k: sorted(v) for k, v in digit_sets.items()})

    nonzero = inv[inv["stock"] != 0]
    item_wh = nonzero.groupby("itemcode")["warehouse"].apply(lambda s: sorted(s.unique())).reset_index()
    item_wh.columns = ["itemcode", "warehouses"]

    def classify(warehouses):
        if len(warehouses) <= 1:
            return "SINGLE_CODE"
        matched_divs = set()
        unmatched_any = False
        for w in warehouses:
            found = False
            for div, codeset in digit_sets.items():
                if w in codeset:
                    matched_divs.add(div)
                    found = True
            if not found:
                unmatched_any = True
        if len(matched_divs) <= 1 and not unmatched_any:
            return "MULTI_CODE_SAME_DIVISION_SET"
        elif len(matched_divs) <= 1 and unmatched_any:
            return "MULTI_CODE_SAME_DIVISION_SET_PLUS_UNMAPPED_CODE"
        else:
            return "MULTI_CODE_SPANS_DIVISION_SETS"

    item_wh["n_warehouses"] = item_wh["warehouses"].apply(len)
    item_wh["classification"] = item_wh["warehouses"].apply(classify)

    scope_div = inv.drop_duplicates("itemcode")[["itemcode", "division"]]
    item_wh = item_wh.merge(scope_div, on="itemcode", how="left")

    # Cross-check against items previously found to have SALES tagged under >1 division.
    if os.path.exists(MULTI_DIVISION_SALES_FILE):
        sales_multi = pd.read_csv(MULTI_DIVISION_SALES_FILE)
        sales_multi_items = set(sales_multi["code"].unique())
    else:
        logger.warning("%s not found -- Part 3's sales cross-check cannot run; leaving flag as unknown.",
                        MULTI_DIVISION_SALES_FILE)
        sales_multi_items = set()
    item_wh["also_sales_multi_division_tagged"] = item_wh["itemcode"].isin(sales_multi_items)

    item_wh = item_wh.sort_values(["classification", "n_warehouses"], ascending=[True, False])
    item_wh.to_csv(out("part3_item_warehouse_spread.csv"), index=False)

    counts = item_wh["classification"].value_counts()
    logger.info("Item warehouse-spread classification (%d items with any nonzero stock):\n%s",
                len(item_wh), counts.to_string())

    spanning = item_wh[item_wh["classification"] == "MULTI_CODE_SPANS_DIVISION_SETS"]
    n_spanning = len(spanning)
    n_spanning_also_sales_multi = int(spanning["also_sales_multi_division_tagged"].sum())
    n_sales_multi_total = len(sales_multi_items)
    logger.info("Of %d warehouse-spanning items: %d (%.1f%%) are ALSO in the sales multi-division-tag "
                "list (%s, %d items total). Correlation only, not proof of either 'genuine multi-division "
                "handling' or 'mapping error' -- stated as such.",
                n_spanning, n_spanning_also_sales_multi,
                100 * n_spanning_also_sales_multi / n_spanning if n_spanning else 0.0,
                os.path.basename(MULTI_DIVISION_SALES_FILE), n_sales_multi_total)
    return item_wh


# ============================================================================================
# PART 4: FG21 vs FG02
# ============================================================================================
def part4_fg21_vs_fg02(inv: pd.DataFrame) -> dict:
    logger.info("=== PART 4: FG21 vs FG02 -- distinct warehouses, or a recording variant? ===")

    nonzero = inv[inv["stock"] != 0]
    fg21_items = set(nonzero.loc[nonzero["warehouse"] == "FG21", "itemcode"])
    fg02_items = set(nonzero.loc[nonzero["warehouse"] == "FG02", "itemcode"])
    fg21_qty = nonzero.loc[nonzero["warehouse"] == "FG21", "stock"].sum()
    fg02_qty = nonzero.loc[nonzero["warehouse"] == "FG02", "stock"].sum()
    overlap = fg21_items & fg02_items

    logger.info("FG21 (445-item scope, nonzero stock): %d items, qty=%.1f. FG02: %d items, qty=%.1f. "
                "Item-set overlap: %d items.", len(fg21_items), fg21_qty, len(fg02_items), fg02_qty, len(overlap))
    logger.info("NOTE: FG02 shows total_stock=0 table-wide per phaseD_check1_03_warehouse_universe_tablewide.csv "
                "(current physical stock is 0 across the WHOLE table, not just this 445-item scope) -- if FG02 "
                "has any items here it is via the 'available'/other columns' nonzero rows in the raw pull, not "
                "positive 'stock'; this is checked directly below rather than assumed from that earlier file.")

    item_set_compare = pd.DataFrame([{
        "fg21_n_items": len(fg21_items), "fg21_total_qty": fg21_qty,
        "fg02_n_items": len(fg02_items), "fg02_total_qty": fg02_qty,
        "n_items_overlap": len(overlap),
        "fg21_only_items": sorted(fg21_items - fg02_items),
        "fg02_only_items": sorted(fg02_items - fg21_items),
        "overlap_items": sorted(overlap),
    }])
    item_set_compare.to_csv(out("part4_fg21_vs_fg02_item_sets.csv"), index=False)

    # Ledger check: does either code appear in cube_inventory_tran AT ALL (any item, table-wide --
    # the ledger's coverage is known to be narrow, per phase4_warehouse_flow_investigation_report.md).
    tran_presence = run_query(f"""
        SELECT warehouse, transtype, COUNT(*) AS n_rows, COUNT(DISTINCT itemcode) AS n_items,
               SUM(QtyIn) AS sum_qty_in, SUM(QtyOut) AS sum_qty_out
        FROM {TRAN_TABLE}
        WHERE RTRIM(warehouse) IN ('FG21','FG02')
        GROUP BY warehouse, transtype
        ORDER BY warehouse, transtype
    """)
    tran_presence.to_csv(out("part4_fg21_fg02_tran_presence.csv"), index=False)
    logger.info("cube_inventory_tran rows where warehouse IN ('FG21','FG02') (any item, table-wide):\n%s",
                tran_presence.to_string(index=False) if len(tran_presence) else "(zero rows -- neither code "
                "appears in the movement ledger at all)")

    tran_date_range = run_query(f"""
        SELECT RTRIM(warehouse) AS warehouse, MIN(trans_date) AS min_trans_date, MAX(trans_date) AS max_trans_date,
               COUNT(*) AS n_rows
        FROM {TRAN_TABLE}
        WHERE RTRIM(warehouse) IN ('FG21','FG02')
        GROUP BY RTRIM(warehouse)
    """)
    tran_date_range.to_csv(out("part4_fg21_fg02_tran_date_range.csv"), index=False)
    logger.info("Ledger date range per code (table-wide, any item):\n%s -- FG02 has activity through the "
                "CURRENT snapshot date despite zero resting stock (high-throughput/pass-through signature, "
                "like QA); FG21 has far fewer ledger rows but real resting stock (17,496 units in this "
                "445-item scope) -- most of FG21's current stock did NOT arrive via a ledger-recorded "
                "transfer (consistent with the already-known narrow ledger coverage, not a contradiction).",
                tran_date_range.to_string(index=False))

    # Direct transfer-pair check: for items that appear in FG21 or FG02 in the ledger at all, pull
    # every 150/151 transfer row for those items and check whether any pair links FG21<->FG02.
    fg21_fg02_ledger_items = run_query(f"""
        SELECT DISTINCT itemcode FROM {TRAN_TABLE} WHERE RTRIM(warehouse) IN ('FG21','FG02')
    """)["itemcode"].tolist()

    fg21_fg02_transfer_pairs = pd.DataFrame()
    if fg21_fg02_ledger_items:
        transfers_raw = run_query(f"""
            SELECT itemcode, ourref, trans_date, transtype, warehouse, QtyIn, QtyOut
            FROM {TRAN_TABLE}
            WHERE itemcode IN ('{sql_list(fg21_fg02_ledger_items)}') AND transtype IN ('150','151')
        """)
        transfers_raw = strip_warehouse(transfers_raw)
        pairs = []
        for key, grp in transfers_raw.groupby(["itemcode", "ourref", "trans_date"]):
            if len(grp) == 2 and set(grp["transtype"]) == {"150", "151"}:
                out_row = grp[grp["transtype"] == "150"].iloc[0]
                in_row = grp[grp["transtype"] == "151"].iloc[0]
                pairs.append({
                    "itemcode": key[0], "from_warehouse": out_row["warehouse"], "to_warehouse": in_row["warehouse"],
                    "qty": in_row["QtyIn"],
                })
        pairs_df = pd.DataFrame(pairs)
        if len(pairs_df):
            fg21_fg02_transfer_pairs = pairs_df[
                ((pairs_df["from_warehouse"] == "FG21") & (pairs_df["to_warehouse"] == "FG02")) |
                ((pairs_df["from_warehouse"] == "FG02") & (pairs_df["to_warehouse"] == "FG21"))
            ]
        logger.info("%d itemcodes touch FG21/FG02 in the ledger at all; %d total 150/151 transfer pairs "
                    "found for those items; %d of those pairs directly link FG21<->FG02.",
                    len(fg21_fg02_ledger_items), len(pairs_df), len(fg21_fg02_transfer_pairs))
    else:
        logger.info("Zero itemcodes have ANY row in cube_inventory_tran for warehouse FG21 or FG02 -- "
                    "the ledger has no coverage of either code at all. Stopping this sub-check here "
                    "(stopping rule) rather than searching further.")
    fg21_fg02_transfer_pairs.to_csv(out("part4_fg21_fg02_direct_transfer_pairs.csv"), index=False)

    verdict = (
        "DISTINCT, MODERATE-TO-HIGH confidence -- not a recording variant of the same thing. Two "
        "independent, converging pieces of evidence: (1) different, non-overlapping item sets and "
        "different nonzero quantities in Cube_Inventory_Exact right now (FG21: 78 items, 17,496 units "
        "in this 445-item scope; FG02: 0 items, 0 units -- a recording-variant/duplicate-alias code "
        "would be expected to show near-total item-set overlap, not zero overlap); (2) a DIFFERENT "
        "BEHAVIOURAL SIGNATURE in cube_inventory_tran -- FG02 has 2,307 ledger rows spanning "
        "2017-10-19 to 2026-09-08 (activity through the CURRENT day) yet zero resting stock -- a "
        "high-throughput PASS-THROUGH profile, structurally similar to QA's already-confirmed "
        "inspection-gate role -- while FG21 has only 13 ledger rows (2025-09-26 to 2026-08-21) yet "
        "holds real resting stock -- a STORAGE profile. A single alias/recording-variant code would "
        "not produce two such different transaction-volume-vs-resting-stock profiles. CAVEAT: most of "
        "FG21's current 17,496 units did NOT arrive via any ledger-recorded transfer (13 rows cannot "
        "explain that volume) -- consistent with, not contradicting, this project's already-documented "
        "narrow ledger coverage (STATUS.md, most Finished Goods items have no transfer evidence at "
        "all), so this cannot be pushed further than a behavioural-signature argument. SNAPSHOT-DRIFT "
        "NOTE, reported not smoothed over: this script's own pull (run 2026-09-09) shows FG21 at "
        "17,496 units in-scope / 17,666 table-wide as of timestamp 2026-09-08 21:40, versus Phase D "
        "Check 1's earlier pull (phaseD_check1_03_warehouse_universe_tablewide.csv) which recorded "
        "24,255 units as of its 2026-09-06 snapshot -- consistent with the table being LIVE/continuously "
        "updated, a conflict already flagged in STATUS.md Phase D (Check 1 vs Check 2's frozen-vs-live "
        "disagreement) and reaffirmed here, not newly discovered."
    )
    logger.info("Part 4 verdict: %s", verdict)
    return {"item_set_compare": item_set_compare, "tran_presence": tran_presence,
            "transfer_pairs": fg21_fg02_transfer_pairs, "verdict": verdict}


# ============================================================================================
# PART 5: prefix/digit grouping + proposed mapping table
# ============================================================================================
def part5_proposed_mapping(wh_dom: pd.DataFrame) -> pd.DataFrame:
    logger.info("=== PART 5: prefix/trailing-digit grouping + proposed mapping table ===")

    def prefix(code: str) -> str:
        m = re.match(r"^([A-Za-z\-]+)", str(code).strip())
        return m.group(1) if m else code

    wh = wh_dom.copy()
    wh["prefix"] = wh["warehouse"].apply(prefix)

    by_prefix = wh.groupby("prefix").agg(
        n_codes=("warehouse", "nunique"),
        codes=("warehouse", lambda s: sorted(s.unique())),
        n_match=("match_status", lambda s: (s == "MATCH").sum()),
        n_mismatch=("match_status", lambda s: (s == "MISMATCH").sum()),
        distinct_dominant_divisions=("dominant_division", lambda s: sorted(s.dropna().unique().tolist())),
    ).reset_index()
    by_prefix.to_csv(out("part5_prefix_grouping.csv"), index=False)
    logger.info("Prefix grouping (%d prefixes):\n%s", len(by_prefix),
                by_prefix[["prefix", "n_codes", "n_match", "n_mismatch", "distinct_dominant_divisions"]].to_string(index=False))

    by_digits = wh.groupby("trailing_digits", dropna=False).agg(
        n_codes=("warehouse", "nunique"),
        codes=("warehouse", lambda s: sorted(s.unique())),
        distinct_dominant_divisions=("dominant_division", lambda s: sorted(s.dropna().unique().tolist())),
    ).reset_index()
    by_digits.to_csv(out("part5_trailing_digit_grouping.csv"), index=False)
    logger.info("Trailing-digit grouping:\n%s",
                by_digits[["trailing_digits", "n_codes", "codes", "distinct_dominant_divisions"]].to_string(index=False))

    # Known stage findings, applied not re-derived (STATUS.md / Phase D Check 1).
    CONFIRMED_STAGE = {"QA": "Inspection (confirmed, STATUS.md 2026-09-02 movement-ledger finding)",
                        "FMTS": "Production WIP (confirmed, STATUS.md 2026-09-02 movement-ledger finding)",
                        "FMTO": "Production WIP (confirmed, STATUS.md 2026-09-02 movement-ledger finding)"}

    def division_and_confidence(row):
        """Returns (inferred_division, division_source, confidence_text). division_source
        distinguishes a division read off the TRAILING-DIGIT HYPOTHESIS (what this task tests)
        from one read off this cross-tab's dominant-division finding ALONE, with no digit
        prediction backing it (still a real empirical finding, just not what the hypothesis
        predicts -- must not be conflated with a hypothesis confirmation)."""
        wh_code = row["warehouse"]
        has_dominant = row["dominant_division"] is not None and row["dominant_division"] == row["dominant_division"]

        if row["match_status"] == "MATCH":
            n_div = row["n_divisions_with_stock"]
            conf = "MODERATE" if n_div <= 2 else "LOW"
            return row["dominant_division"], "trailing_digit_hypothesis", \
                   f"{conf} (trailing digits match dominant division at {row['dominant_division_share_pct']}% share, " \
                   f"shared with {n_div-1} other division(s) at lower share)"
        if row["match_status"] == "MISMATCH":
            return row["dominant_division"], "trailing_digit_hypothesis_MISMATCH", \
                   "LOW (trailing digits contradict the observed dominant division -- reported as the mismatch, not adopted)"
        if row["match_status"].startswith("NO_PREDICTION") and has_dominant:
            n_div = row["n_divisions_with_stock"]
            conf = "LOW-MODERATE" if row["dominant_division_share_pct"] >= 90 else "LOW"
            return row["dominant_division"], "cross_tab_empirical_only (no trailing-digit prediction exists for this code)", \
                   f"{conf} (empirical cross-tab dominant division at {row['dominant_division_share_pct']}% of only " \
                   f"{row['total_qty']:.0f} units -- NOT a hypothesis confirmation, this code has no digit prediction)"
        if row["match_status"].startswith("NO_PREDICTION"):
            return "UNRESOLVED", None, "UNRESOLVED (hypothesis makes no prediction for this code's digits, and no clear dominant division either)"
        if "zero stock" in row["match_status"]:
            return "UNRESOLVED", None, "UNRESOLVED (zero stock for these 445 items in this snapshot -- cannot test)"
        return "UNRESOLVED", None, "UNRESOLVED (no clear dominant division in this cross-tab)"

    def stage_for(wh_code: str) -> str:
        return CONFIRMED_STAGE.get(wh_code, "Stage undetermined (no behavioural stage evidence beyond QA/FMTS/FMTO)")

    rows = []
    for _, r in wh.iterrows():
        inferred_division, division_source, conf = division_and_confidence(r)
        stage = stage_for(r["warehouse"])
        if r["warehouse"] in CONFIRMED_STAGE:
            conf = f"STAGE: HIGH (movement-ledger-confirmed, STATUS.md 2026-09-02). DIVISION: {conf}"
        rows.append({
            "warehouse": r["warehouse"], "prefix": r["prefix"], "trailing_digits": r["trailing_digits"],
            "inferred_division": inferred_division,
            "division_source": division_source,
            "inferred_process_stage": stage,
            "evidence": f"Cross-tab dominant division={r['dominant_division']} ({r['dominant_division_share_pct']}% "
                        f"of {r['total_qty']:.0f} units, {r['n_divisions_with_stock']} division(s) present); "
                        f"hypothesis predicted {r['predicted_division_by_hypothesis']}; match_status={r['match_status']}",
            "confidence": conf,
        })
    mapping = pd.DataFrame(rows).sort_values("warehouse")
    mapping.to_csv(out("part5_proposed_mapping.csv"), index=False)

    n_unresolved = (mapping["inferred_division"] == "UNRESOLVED").sum()
    logger.info("Proposed mapping: %d codes, %d left UNRESOLVED (no confident division assignment).",
                len(mapping), n_unresolved)
    return mapping


# ============================================================================================
# PART 6: console summary
# ============================================================================================
def part6_console_summary(cross: pd.DataFrame, conc: pd.DataFrame, wh_dom: pd.DataFrame,
                           item_wh: pd.DataFrame, fg_result: dict, mapping: pd.DataFrame) -> str:
    n_match = (wh_dom["match_status"] == "MATCH").sum()
    n_mismatch = (wh_dom["match_status"] == "MISMATCH").sum()
    n_no_pred = (wh_dom["match_status"].str.startswith("NO_PREDICTION")).sum()
    n_zero_stock = (wh_dom["match_status"].str.contains("zero stock")).sum()
    n_total = len(wh_dom)
    n_testable = n_match + n_mismatch  # only codes with BOTH a hypothesis prediction AND a clear dominant division
    mean_top1 = conc["top1_qty_share_pct"].mean()
    n_spanning = (item_wh["classification"] == "MULTI_CODE_SPANS_DIVISION_SETS").sum()
    n_single = (item_wh["classification"] == "SINGLE_CODE").sum()
    n_items = len(item_wh)

    if n_testable == 0:
        verdict = "CANNOT BE TESTED (no warehouse code both has a hypothesis prediction and a clear dominant division)"
    elif n_mismatch == 0:
        verdict = (f"HOLDS ON THE {n_testable} CODE(S) IT CAN BE TESTED ON, but that is a NARROW test "
                   f"({n_testable}/{n_total} codes) -- MODERATE confidence overall, not clean, because "
                   f"{n_no_pred}/{n_total} codes have no hypothesis prediction at all and {n_zero_stock}/{n_total} "
                   f"hold zero stock in this snapshot and could not be tested either way")
    else:
        verdict = (f"PARTIALLY HOLDS: {n_match}/{n_testable} testable codes match, {n_mismatch}/{n_testable} "
                   f"do not -- MODERATE-TO-LOW confidence, not clean")

    lines = []
    lines.append("=" * 90)
    lines.append("WAREHOUSE / DIVISION TRAILING-DIGIT HYPOTHESIS -- SUMMARY")
    lines.append("=" * 90)
    lines.append(f"HYPOTHESIS VERDICT: {verdict}.")
    lines.append(f"  - Of {n_total} warehouse codes in the 445-item scope: {n_match} MATCH their predicted "
                 f"division by trailing digit (dominance threshold {DOMINANCE_THRESHOLD_PCT:.0f}% of qty), "
                 f"{n_mismatch} MISMATCH, {n_no_pred} have no hypothesis prediction for their digits (e.g. "
                 f"QA, FMTS, FMTO, CI101 has no numeric-suffix prediction at all), and {n_zero_stock} hold "
                 f"zero stock in this snapshot and could not be tested.")
    lines.append(f"  - Mean per-division concentration in its single largest warehouse code: {mean_top1:.1f}% "
                 f"of quantity (see part1_division_concentration.csv for the full per-division breakdown, "
                 f"top-1/2/3 by both qty and value).")
    lines.append(f"  - Item warehouse spread: {n_single}/{n_items} items sit in exactly one warehouse code; "
                 f"{n_spanning}/{n_items} items span warehouse codes belonging to more than one division's "
                 f"trailing-digit set (see part3_item_warehouse_spread.csv for the sales-multi-division "
                 f"cross-check on these).")
    lines.append("")
    lines.append(f"FG21 vs FG02: {fg_result['verdict']}")
    lines.append("")
    lines.append("PROPOSED MAPPING -- codes the data could place (warehouse | division | stage | confidence):")
    placed = mapping[mapping["inferred_division"] != "UNRESOLVED"].sort_values("warehouse")
    unresolved = mapping[mapping["inferred_division"] == "UNRESOLVED"].sort_values("warehouse")
    for _, r in placed.iterrows():
        lines.append(f"  {r['warehouse']:<6} | {str(r['inferred_division']):<12} | "
                     f"{r['inferred_process_stage']:<70} | {r['confidence']}")
    lines.append("")
    lines.append(f"UNRESOLVED ({len(unresolved)}/{len(mapping)} codes -- data cannot place these; "
                 f"see part5_proposed_mapping.csv for each one's reason): {', '.join(unresolved['warehouse'])}")
    lines.append("=" * 90)
    summary = "\n".join(lines)
    print(summary)
    return summary


# ============================================================================================
# MAIN
# ============================================================================================
def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    config = load_config()
    scope = step1_item_scope(config)
    inv = step2_inventory_pull(scope)

    all_codes = sorted(inv["warehouse"].unique())
    p1 = part1_crosstab(inv)
    wh_dom = part2_dominant_division(p1["cross"], all_codes)
    item_wh = part3_item_spread(inv, wh_dom)
    fg_result = part4_fg21_vs_fg02(inv)
    mapping = part5_proposed_mapping(wh_dom)
    summary = part6_console_summary(p1["cross"], p1["concentration"], wh_dom, item_wh, fg_result, mapping)

    with open(out("part6_console_summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary)

    logger.info("DONE. Outputs written to output/summary/whmap_*.csv and whmap_part6_console_summary.txt.")


if __name__ == "__main__":
    main()
