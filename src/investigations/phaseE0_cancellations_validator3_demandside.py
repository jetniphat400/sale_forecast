"""Phase E0.2 re-verification, DEMAND-SIDE direction (2026-09-22).

Written independently of `src/investigations/phaseE0_cancellations_validator2.py` (that script's
own code was not reused or imported here) -- this task's own brief is the sole methodology
source. E0.2 checked one direction only: Cube_CES Cancel rows -> cube_Sale_APD (does a cancelled
(contract, item) pair resurface as Actual/MPS demand?). CONVENTIONS.md now requires the reverse
direction before "zero cancellation contamination" can be recorded as a conclusion rather than a
one-direction finding: cube_Sale_APD demand -> Cube_CES (does any row IN the demand series
correspond to a contract that Cube_CES shows as Cancel?).

Scope: the 128-item PEM101 pilot (config['adopted_scope_file']), Omni Channel, Actual+MPS,
createDate >= config['date_range']['start'] -- the exact filter the production series uses
(src/load_data_full.py / src/phaseE1_common.py's own convention), at ROW level (not deduplicated
to (contract, item) pairs) since the task asks about every demand row.

For each distinct (contractid, itemcode) pair actually present in that demand series, this script
pulls EVERY Cube_CES row sharing that exact key (any status) and classifies the pair:
  - NO_CES_MATCH        : the pair has zero rows in Cube_CES at all (third signal the task asks
                           for -- a cancelled-and-purged contract could look like this).
  - ONLY_CANCEL         : every Cube_CES row for the pair is Status='Cancel' -- a cancelled order
                           that survived into the demand series (task's 2nd clause, cleanly).
  - CANCEL_PLUS_OTHER   : the pair has at least one Cancel row AND at least one non-Cancel row --
                           reported separately, not silently folded into ONLY_CANCEL.
  - NO_CANCEL           : the pair has Cube_CES rows, none of them Status='Cancel'.
Every demand ROW inherits its pair's classification, so qty/value totals are at row granularity
(a pair with 3 demand rows contributes 3 rows' worth of qty/value to its bucket).

DATABASE ACCESS RULE: one connection attempt only. If the first query fails, this script stops
and raises -- nothing here retries a failed login.
"""
import logging
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/
from db import run_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE0_cancellations_validator3_demandside")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sql_list(values) -> str:
    return "','".join(str(v).replace("'", "''") for v in values)


def load_128_scope(config: dict) -> list:
    scope_path = os.path.join(PROJECT_ROOT, config["adopted_scope_file"])
    scope = pd.read_csv(scope_path)
    codes = sorted(scope["code"].unique())
    logger.info("128-item PEM101 pilot scope loaded from %s: %d codes.", config["adopted_scope_file"], len(codes))
    return codes


def pull_demand_series(config: dict, codes: list):
    """Every ROW in the current production demand series for the 128-item scope -- the exact
    filter src/load_data_full.py uses to build the series this project actually forecasts on."""
    statuses = "','".join(config["status_basis"])
    start_date = config["date_range"]["start"]
    sql = f"""
        SELECT itemcode, contractid, forecast_date, createDate, qty, sale, status
        FROM cube_Sale_APD
        WHERE itemcode IN ('{sql_list(codes)}')
          AND revenue_type = '{config["revenue_type"]}'
          AND status IN ('{statuses}')
          AND createDate >= '{start_date}'
    """
    try:
        demand = run_query(sql)
    except Exception as exc:
        logger.error("DATABASE ACCESS RULE: single connection attempt failed, not retrying. Error: %r", exc)
        raise
    demand["createDate"] = pd.to_datetime(demand["createDate"])
    logger.info("Demand series (128-item scope, %s, status IN %s, createDate >= %s): %d rows, "
                "qty=%.1f, value=%.2f, %d distinct (contractid, itemcode) pairs.",
                config["revenue_type"], config["status_basis"], start_date, len(demand),
                demand["qty"].sum(), demand["sale"].sum(),
                demand[["contractid", "itemcode"]].drop_duplicates().shape[0])
    return demand


def pull_ces_for_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    """Every Cube_CES row (any status) for the exact (ContractID, ItemCode) pairs present in the
    demand series -- pulled by ItemCode (a much smaller IN-list than pulling by ContractID) then
    filtered to the exact pair set in Python, since ContractID has far higher cardinality."""
    items = sorted(pairs["itemcode"].unique())
    ces = run_query(f"""
        SELECT ContractID, ItemCode, Status, ActualQty, BacklogQty, ActualPrice, BacklogPrice, CtrDate
        FROM Cube_CES
        WHERE ItemCode IN ('{sql_list(items)}')
    """)
    pair_set = set(zip(pairs["contractid"], pairs["itemcode"]))
    ces["_key"] = list(zip(ces["ContractID"], ces["ItemCode"]))
    ces_matched = ces[ces["_key"].isin(pair_set)].drop(columns="_key")
    logger.info("Cube_CES rows (any status) pulled for the demand series's %d itemcodes: %d rows; "
                "%d of those rows key-match one of the demand series's (contractid, itemcode) pairs.",
                len(items), len(ces), len(ces_matched))
    return ces_matched


def classify_pairs(demand_pairs: pd.DataFrame, ces_matched: pd.DataFrame) -> pd.DataFrame:
    status_sets = ces_matched.groupby(["ContractID", "ItemCode"])["Status"].apply(
        lambda s: set(s.dropna())).reset_index()
    status_sets.columns = ["contractid", "itemcode", "ces_status_set"]

    merged = demand_pairs.merge(status_sets, on=["contractid", "itemcode"], how="left")

    def classify(status_set):
        if status_set is None or (isinstance(status_set, float)):  # NaN from the left-join miss
            return "NO_CES_MATCH"
        if "Cancel" not in status_set:
            return "NO_CANCEL"
        if status_set == {"Cancel"}:
            return "ONLY_CANCEL"
        return "CANCEL_PLUS_OTHER"

    merged["classification"] = merged["ces_status_set"].apply(classify)
    merged["ces_status_set"] = merged["ces_status_set"].apply(
        lambda s: sorted(s) if isinstance(s, set) else [])
    return merged


def main():
    config = load_config()
    codes = load_128_scope(config)
    demand = pull_demand_series(config, codes)

    demand_pairs = demand[["contractid", "itemcode"]].drop_duplicates()
    ces_matched = pull_ces_for_pairs(demand_pairs)
    pair_classification = classify_pairs(demand_pairs, ces_matched)
    pair_classification.to_csv(os.path.join(SUMMARY_DIR,
        "phaseE0_validator3_demandside_pair_classification.csv"), index=False)

    # Join the pair-level classification back onto every DEMAND ROW (row-level qty/value totals).
    demand_rows = demand.merge(pair_classification[["contractid", "itemcode", "classification", "ces_status_set"]],
                                on=["contractid", "itemcode"], how="left")
    demand_rows.to_csv(os.path.join(SUMMARY_DIR,
        "phaseE0_validator3_demandside_rows_classified.csv"), index=False)

    row_summary = demand_rows.groupby("classification", as_index=False).agg(
        n_rows=("qty", "size"), total_qty=("qty", "sum"), total_value=("sale", "sum"),
        n_distinct_pairs=("contractid", lambda s: len(set(zip(s, demand_rows.loc[s.index, "itemcode"])))))
    row_summary.to_csv(os.path.join(SUMMARY_DIR,
        "phaseE0_validator3_demandside_row_summary.csv"), index=False)

    total_qty = demand_rows["qty"].sum()
    total_value = demand_rows["sale"].sum()

    # CES status distribution of demand rows (a row can appear under multiple statuses if its
    # pair's CES rows carry more than one status -- stated explicitly, not summed to 100%).
    status_rows = []
    all_statuses = sorted(set(s for lst in demand_rows["ces_status_set"] for s in lst))
    for st in all_statuses:
        mask = demand_rows["ces_status_set"].apply(lambda lst: st in lst)
        status_rows.append({"ces_status": st, "n_demand_rows": int(mask.sum()),
                             "qty": float(demand_rows.loc[mask, "qty"].sum()),
                             "value": float(demand_rows.loc[mask, "sale"].sum())})
    status_rows.append({"ces_status": "NO_CES_MATCH_AT_ALL",
                         "n_demand_rows": int((demand_rows["classification"] == "NO_CES_MATCH").sum()),
                         "qty": float(demand_rows.loc[demand_rows["classification"] == "NO_CES_MATCH", "qty"].sum()),
                         "value": float(demand_rows.loc[demand_rows["classification"] == "NO_CES_MATCH", "sale"].sum())})
    status_dist = pd.DataFrame(status_rows).sort_values("n_demand_rows", ascending=False)
    status_dist.to_csv(os.path.join(SUMMARY_DIR,
        "phaseE0_validator3_demandside_ces_status_distribution.csv"), index=False)

    # ---- Headline: cancelled orders that survived into the demand series ----
    survived = demand_rows[demand_rows["classification"].isin(["ONLY_CANCEL", "CANCEL_PLUS_OTHER"])]
    only_cancel = demand_rows[demand_rows["classification"] == "ONLY_CANCEL"]
    mixed = demand_rows[demand_rows["classification"] == "CANCEL_PLUS_OTHER"]

    # ---- Third signal: pairs with no Cube_CES counterpart at all ----
    no_match = demand_rows[demand_rows["classification"] == "NO_CES_MATCH"]
    no_match_pairs = no_match[["contractid", "itemcode"]].drop_duplicates()
    no_match_detail = no_match.groupby(["contractid", "itemcode"], as_index=False).agg(
        n_rows=("qty", "size"), qty=("qty", "sum"), value=("sale", "sum"),
        min_createDate=("createDate", "min"), max_createDate=("createDate", "max"))
    no_match_detail.to_csv(os.path.join(SUMMARY_DIR,
        "phaseE0_validator3_demandside_no_ces_match_pairs.csv"), index=False)

    # ---- Focus items ----
    focus_rows = demand_rows[demand_rows["itemcode"].isin(FOCUS_ITEMS)]
    focus_survived = focus_rows[focus_rows["classification"].isin(["ONLY_CANCEL", "CANCEL_PLUS_OTHER"])]

    print("\n" + "=" * 90)
    print("PHASE E0.2 RE-VERIFICATION -- DEMAND-SIDE DIRECTION (independent of validator2.py)")
    print("=" * 90)
    print(f"Demand series (128-item PEM101 scope, {config['revenue_type']}, status IN "
          f"{config['status_basis']}, createDate>={config['date_range']['start']}): "
          f"{len(demand_rows)} rows, qty={total_qty:,.1f}, value={total_value:,.2f}, "
          f"{len(demand_pairs)} distinct (contractid, itemcode) pairs.")
    print("\nCube_CES status distribution of demand rows (a row can appear under >1 status if its "
          "pair has multiple Cube_CES rows -- does not sum to the row total):")
    print(status_dist.to_string(index=False))
    print("\nPair classification (row-level totals):")
    print(row_summary.to_string(index=False))
    print(f"\nHEADLINE -- cancelled orders that survived into the demand series:")
    print(f"  ONLY_CANCEL (every Cube_CES row for the pair is Cancel): {len(only_cancel)} rows, "
          f"qty={only_cancel['qty'].sum():,.1f} ({100*only_cancel['qty'].sum()/total_qty:.4f}% of series qty), "
          f"value={only_cancel['sale'].sum():,.2f} ({100*only_cancel['sale'].sum()/total_value:.4f}% of series value)")
    print(f"  CANCEL_PLUS_OTHER (pair has a Cancel row AND a non-Cancel row): {len(mixed)} rows, "
          f"qty={mixed['qty'].sum():,.1f}, value={mixed['sale'].sum():,.2f}")
    print(f"  COMBINED (ONLY_CANCEL + CANCEL_PLUS_OTHER): {len(survived)} rows, "
          f"qty={survived['qty'].sum():,.1f} ({100*survived['qty'].sum()/total_qty:.4f}% of series qty), "
          f"value={survived['sale'].sum():,.2f} ({100*survived['sale'].sum()/total_value:.4f}% of series value)")
    print(f"\nTHIRD SIGNAL -- demand pairs with NO Cube_CES counterpart at all (possible "
          f"cancelled-and-purged contracts):")
    print(f"  {len(no_match_pairs)} distinct pairs, {len(no_match)} demand rows, "
          f"qty={no_match['qty'].sum():,.1f} ({100*no_match['qty'].sum()/total_qty:.4f}% of series qty), "
          f"value={no_match['sale'].sum():,.2f} ({100*no_match['sale'].sum()/total_value:.4f}% of series value)")
    if len(no_match_detail):
        print(f"  createDate range of these rows: {no_match['createDate'].min()} to {no_match['createDate'].max()}")
        print(f"  Top 10 by value:\n{no_match_detail.sort_values('value', ascending=False).head(10).to_string(index=False)}")
    print(f"\nFocus items ({FOCUS_ITEMS}): {len(focus_rows)} demand rows, "
          f"{len(focus_survived)} classified ONLY_CANCEL/CANCEL_PLUS_OTHER.")
    print("\nCSV outputs written to output/summary/ with prefix phaseE0_validator3_demandside_")

    return {
        "total_qty": total_qty, "total_value": total_value, "n_rows": len(demand_rows),
        "n_only_cancel": len(only_cancel), "qty_only_cancel": float(only_cancel["qty"].sum()),
        "value_only_cancel": float(only_cancel["sale"].sum()),
        "n_mixed": len(mixed), "qty_mixed": float(mixed["qty"].sum()), "value_mixed": float(mixed["sale"].sum()),
        "n_no_match_pairs": len(no_match_pairs), "n_no_match_rows": len(no_match),
        "qty_no_match": float(no_match["qty"].sum()), "value_no_match": float(no_match["sale"].sum()),
    }


if __name__ == "__main__":
    main()
