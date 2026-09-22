"""Read-only follow-up investigation: relationship between Cube_Inventory_Exact.reserve_bywa and
outstanding Cube_Backlog quantity, for the 445-code pricelist registry. Decides which is the
better source for a "Reserved" column. See
output/summary/reserve_backlog_relationship_report.md for the write-up.

Does NOT modify index.html, data/inventory.json, or build_inventory_dataset.py. Does not commit.
Live tables (Cube_Inventory_Exact, Cube_Backlog) refresh daily -- re-running will not reproduce
identical figures. This script was run against a snapshot taken 2026-09-10.
"""
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import run_query  # noqa: E402
from pricelist_reader import load_visible_product_rows  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(PROJECT_ROOT, "output", "summary")


def load_registry() -> pd.DataFrame:
    config = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8"))
    df = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    df = df.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    df["division"] = df["sheet"].map(config["sheet_to_division"])
    return df[["code", "division"]]


def query_inventory(codes: list) -> pd.DataFrame:
    code_list = "','".join(sorted(codes))
    df = run_query(f"""
        SELECT company, warehouse, itemcode, unit, stock, reserve_bywa, tobe_received, available, timestamp
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
        WHERE itemcode IN ('{code_list}')
    """)
    df["warehouse"] = df["warehouse"].str.strip()
    return df


def query_inventory_tablewide_summary() -> dict:
    row = run_query("""
        SELECT COUNT(*) n_rows,
               SUM(CASE WHEN reserve_bywa <> 0 THEN 1 ELSE 0 END) n_nonzero_rows,
               SUM(reserve_bywa) total_reserve_bywa,
               SUM(CASE WHEN reserve_bywa <> 0 THEN reserve_bywa ELSE 0 END) total_reserve_bywa_nonzero
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
    """).iloc[0].to_dict()
    return row


def query_inventory_registry_flagged(codes: list) -> pd.DataFrame:
    """All nonzero reserve_bywa rows table-wide, flagged as in/out of the 445 registry."""
    code_list = "','".join(sorted(codes))
    return run_query(f"""
        SELECT itemcode, warehouse, product_category, product_type, product_description,
               stock, reserve_bywa,
               CASE WHEN itemcode IN ('{code_list}') THEN 1 ELSE 0 END AS in_registry
        FROM [salewarehouse].[dbo].[Cube_Inventory_Exact]
        WHERE reserve_bywa <> 0
    """)


def query_backlog_full() -> pd.DataFrame:
    """Full Cube_Backlog table (all itemcodes, not just registry) for dedup-key discovery."""
    return run_query("""
        SELECT id, docID, itemcode, quantity, status, viewType, deliverydate, plan_deliverydate,
               receivedate, division, sale_division, company, manufacturing_type, timestamp
        FROM [salewarehouse].[dbo].[Cube_Backlog]
    """)


def query_contract_by_docid(docids: list) -> pd.DataFrame:
    if not docids:
        return pd.DataFrame()
    docid_list = "','".join(sorted(set(docids)))
    return run_query(f"""
        SELECT contractid, product_id, product, jobname, status, plan_qty, actual_qty, backlog_qty, timestamp
        FROM [salewarehouse].[dbo].[cube_Contract]
        WHERE contractid IN ('{docid_list}')
    """)


def query_tran_near_snapshot(codes: list, snapshot_ts: str) -> pd.DataFrame:
    code_list = "','".join(sorted(codes))
    return run_query(f"""
        SELECT itemcode, ourref, trans_date, warehouse, QtyIn, QtyOut
        FROM [salewarehouse].[dbo].[cube_inventory_tran]
        WHERE itemcode IN ('{code_list}')
          AND trans_date >= DATEADD(day, -14, CAST('{snapshot_ts}' AS date))
        ORDER BY itemcode, trans_date
    """)


def find_dedup_key(bl_full: pd.DataFrame) -> tuple:
    """Search for a grouping key that collapses the near-duplicate two-contract pattern:
    same itemcode/quantity/status/deliverydate/plan_deliverydate under two different docIDs
    and two different sale_division tags. Returns (key_columns, groups_df, n_dup_groups,
    n_rows_removed, qty_removed).
    """
    candidates = [
        ["itemcode", "quantity", "status", "deliverydate", "plan_deliverydate"],
        ["itemcode", "quantity", "status", "deliverydate"],
    ]
    results = {}
    for key in candidates:
        grp = bl_full.groupby(key, dropna=False)
        sizes = grp.size()
        dup_groups = sizes[sizes > 1]
        # Only count as "the duplication pattern" groups where docID varies within the group
        # (i.e. genuinely different contract records, not e.g. legitimate multi-line same contract)
        n_docid_varies = 0
        rows_removed = 0
        qty_removed = 0.0
        for key_vals, idx in grp.groups.items():
            sub = bl_full.loc[idx]
            if len(sub) > 1 and sub["docID"].nunique() > 1:
                n_docid_varies += 1
                # keep first row per group, remove the rest
                rows_removed += len(sub) - 1
                qty_removed += sub["quantity"].iloc[1:].sum()
        results[tuple(key)] = {
            "n_groups_total": len(sizes),
            "n_dup_groups_any": int((sizes > 1).sum()),
            "n_groups_docid_varies": n_docid_varies,
            "rows_removed": rows_removed,
            "qty_removed": qty_removed,
        }
    return results


def dedup_backlog(bl: pd.DataFrame, key: list) -> pd.DataFrame:
    """Keep first row per key-group; drop the rest. Only collapses groups where docID varies
    (genuine cross-contract duplicates) -- groups sharing docID are legitimate multi-line
    schedules and are left alone (they are not what group.size()>1 with docID nunique==1 means
    here; this function still collapses ANY group>1 under the key to be conservative and
    consistent with 'de-duplicated on whatever key makes the duplication collapse')."""
    return bl.drop_duplicates(subset=key, keep="first").reset_index(drop=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    registry = load_registry()
    codes = sorted(registry["code"].unique())
    print(f"Registry: {len(codes)} codes")

    # ---------------- PART 1a: reserve_bywa per code ----------------
    inv = query_inventory(codes)
    inv.to_csv(os.path.join(OUT, "reserve_backlog_inventory445_rows.csv"), index=False)
    inv_agg = inv.groupby("itemcode", as_index=False).agg(
        onhand=("stock", "sum"), reserve_bywa=("reserve_bywa", "sum")
    ).rename(columns={"itemcode": "code"})
    snapshot_ts_min, snapshot_ts_max = inv["timestamp"].min(), inv["timestamp"].max()
    print(f"Cube_Inventory_Exact snapshot: {snapshot_ts_min} to {snapshot_ts_max}, {len(inv)} rows for registry")

    n_codes_reserve_nonzero = (inv_agg["reserve_bywa"] > 0).sum()
    total_reserve = inv_agg["reserve_bywa"].sum()
    print(f"1a: codes with reserve_bywa>0: {n_codes_reserve_nonzero}/445, grand total: {total_reserve}")

    # ---------------- PART 1b: backlog per code, as-is and de-duplicated ----------------
    bl_full = query_backlog_full()
    print(f"Cube_Backlog full table: {len(bl_full)} rows")

    dedup_search = find_dedup_key(bl_full)
    for key, res in dedup_search.items():
        print(f"Dedup key {key}: {res}")

    chosen_key = ["itemcode", "quantity", "status", "deliverydate", "plan_deliverydate"]
    bl_dedup_full = dedup_backlog(bl_full, chosen_key)
    n_rows_removed = len(bl_full) - len(bl_dedup_full)
    qty_removed = bl_full["quantity"].sum() - bl_dedup_full["quantity"].sum()
    print(f"Chosen dedup key {chosen_key}: removed {n_rows_removed} rows, {qty_removed} qty (table-wide)")

    bl_full.to_csv(os.path.join(OUT, "reserve_backlog_full_asis.csv"), index=False)
    bl_dedup_full.to_csv(os.path.join(OUT, "reserve_backlog_full_dedup.csv"), index=False)

    bl_reg = bl_full[bl_full["itemcode"].isin(codes)]
    bl_dedup_reg = bl_dedup_full[bl_dedup_full["itemcode"].isin(codes)]
    n_rows_removed_reg = len(bl_reg) - len(bl_dedup_reg)
    qty_removed_reg = bl_reg["quantity"].sum() - bl_dedup_reg["quantity"].sum()
    print(f"Within 445 registry: dedup removed {n_rows_removed_reg} rows, {qty_removed_reg} qty")

    bl_agg_asis = bl_reg.groupby("itemcode", as_index=False)["quantity"].sum().rename(
        columns={"itemcode": "code", "quantity": "backlog_asis"})
    bl_agg_dedup = bl_dedup_reg.groupby("itemcode", as_index=False)["quantity"].sum().rename(
        columns={"itemcode": "code", "quantity": "backlog_dedup"})

    n_codes_backlog_asis_nonzero = bl_agg_asis["backlog_asis"].gt(0).sum() if len(bl_agg_asis) else 0
    total_backlog_asis = bl_agg_asis["backlog_asis"].sum() if len(bl_agg_asis) else 0
    n_codes_backlog_dedup_nonzero = bl_agg_dedup["backlog_dedup"].gt(0).sum() if len(bl_agg_dedup) else 0
    total_backlog_dedup = bl_agg_dedup["backlog_dedup"].sum() if len(bl_agg_dedup) else 0
    print(f"1b as-is: codes with backlog>0: {n_codes_backlog_asis_nonzero}/445, total: {total_backlog_asis}")
    print(f"1b dedup: codes with backlog>0: {n_codes_backlog_dedup_nonzero}/445, total: {total_backlog_dedup}")

    # ---------------- Join everything ----------------
    joined = registry.merge(inv_agg, on="code", how="left").merge(
        bl_agg_asis, on="code", how="left").merge(bl_agg_dedup, on="code", how="left")
    joined[["onhand", "reserve_bywa", "backlog_asis", "backlog_dedup"]] = \
        joined[["onhand", "reserve_bywa", "backlog_asis", "backlog_dedup"]].fillna(0)
    joined.to_csv(os.path.join(OUT, "reserve_backlog_join445.csv"), index=False)

    # ---------------- PART 2a: 2x2 cross-tab ----------------
    joined["res_nz"] = joined["reserve_bywa"] > 0
    joined["bl_nz"] = joined["backlog_asis"] > 0
    both_nz = int((joined["res_nz"] & joined["bl_nz"]).sum())
    only_res = int((joined["res_nz"] & ~joined["bl_nz"]).sum())
    only_bl = int((~joined["res_nz"] & joined["bl_nz"]).sum())
    both_zero = int((~joined["res_nz"] & ~joined["bl_nz"]).sum())
    print(f"2a (as-is backlog): both_nz={both_nz} only_res={only_res} only_bl={only_bl} both_zero={both_zero} "
          f"sum={both_nz+only_res+only_bl+both_zero}")

    joined["bl_dedup_nz"] = joined["backlog_dedup"] > 0
    both_nz_d = int((joined["res_nz"] & joined["bl_dedup_nz"]).sum())
    only_res_d = int((joined["res_nz"] & ~joined["bl_dedup_nz"]).sum())
    only_bl_d = int((~joined["res_nz"] & joined["bl_dedup_nz"]).sum())
    both_zero_d = int((~joined["res_nz"] & ~joined["bl_dedup_nz"]).sum())
    print(f"2a (dedup backlog): both_nz={both_nz_d} only_res={only_res_d} only_bl={only_bl_d} "
          f"both_zero={both_zero_d} sum={both_nz_d+only_res_d+only_bl_d+both_zero_d}")

    # ---------------- PART 2b: agreement for both-nonzero codes ----------------
    both = joined[joined["res_nz"] & joined["bl_nz"]].copy()
    both["diff"] = both["reserve_bywa"] - both["backlog_asis"]
    both["pct_diff"] = both["diff"] / both["backlog_asis"]
    n_exact = int((both["diff"].abs() < 1e-6).sum())
    n_within_10pct = int((both["pct_diff"].abs() <= 0.10).sum())
    print(f"2b: both nonzero n={len(both)}, exact_match={n_exact}, within_10pct={n_within_10pct}")
    print("diff distribution:\n", both["diff"].describe().to_string())
    top10 = both.reindex(both["diff"].abs().sort_values(ascending=False).index).head(10)
    print("Top 10 disagreements:\n", top10[["code", "division", "reserve_bywa", "backlog_asis", "diff"]].to_string())

    # ---------------- PART 2c: correlation ----------------
    either_nz = joined[(joined["reserve_bywa"] != 0) | (joined["backlog_asis"] != 0)]
    corr_asis = either_nz["reserve_bywa"].corr(either_nz["backlog_asis"])
    either_nz_d = joined[(joined["reserve_bywa"] != 0) | (joined["backlog_dedup"] != 0)]
    corr_dedup = either_nz_d["reserve_bywa"].corr(either_nz_d["backlog_dedup"])
    print(f"2c: n_either_nonzero(as-is)={len(either_nz)}, pearson r (as-is) = {corr_asis:.4f}")
    print(f"2c: n_either_nonzero(dedup)={len(either_nz_d)}, pearson r (dedup) = {corr_dedup:.4f}")

    # ---------------- PART 2d: per-division breakdown ----------------
    div_tab = joined.groupby("division").apply(
        lambda g: pd.Series({
            "n_codes": len(g),
            "both_nz": int((g["res_nz"] & g["bl_nz"]).sum()),
            "only_res": int((g["res_nz"] & ~g["bl_nz"]).sum()),
            "only_bl": int((~g["res_nz"] & g["bl_nz"]).sum()),
            "both_zero": int((~g["res_nz"] & ~g["bl_nz"]).sum()),
            "reserve_nz_count": int(g["res_nz"].sum()),
            "backlog_nz_count": int(g["bl_nz"].sum()),
        })
    ).reset_index()
    print("2d per-division:\n", div_tab.to_string())
    pem104 = joined[joined["division"] == "PEM104"]
    print(f"PEM104: {len(pem104)} codes, reserve_bywa nonzero count = {(pem104['reserve_bywa']>0).sum()}, "
          f"backlog nonzero count = {(pem104['backlog_asis']>0).sum()}")

    # ---------------- PART 3a: reserve_bywa outside 445 registry, table-wide ----------------
    tw = query_inventory_tablewide_summary()
    print(f"3a table-wide: {tw}")
    flagged = query_inventory_registry_flagged(codes)
    flagged.to_csv(os.path.join(OUT, "reserve_backlog_reserve_bywa_nonzero_flagged.csv"), index=False)
    n_in = int(flagged["in_registry"].sum())
    n_out = int((flagged["in_registry"] == 0).sum())
    sum_in = flagged.loc[flagged["in_registry"] == 1, "reserve_bywa"].sum()
    sum_out = flagged.loc[flagged["in_registry"] == 0, "reserve_bywa"].sum()
    print(f"3a: nonzero reserve_bywa rows: in-registry={n_in} (sum={sum_in}), "
          f"outside-registry={n_out} (sum={sum_out}), share outside = {n_out/(n_in+n_out)*100:.1f}% of rows, "
          f"{sum_out/(sum_in+sum_out)*100:.1f}% of qty")

    # ---------------- PART 3b: trace top 5 codes by reserve_bywa ----------------
    top5 = inv_agg.sort_values("reserve_bywa", ascending=False).head(5)
    print("Top 5 codes by reserve_bywa:\n", top5.to_string())
    top5_codes = top5["code"].tolist()
    bl_top5 = bl_full[bl_full["itemcode"].isin(top5_codes)]
    print(f"Backlog rows for top5 codes: {len(bl_top5)}")
    print(bl_top5[["itemcode", "docID", "quantity", "status", "deliverydate"]].to_string())
    docids_top5 = bl_top5["docID"].dropna().unique().tolist()
    contract_top5 = query_contract_by_docid(docids_top5)
    print(f"cube_Contract rows matching top5's docIDs: {len(contract_top5)}")
    tran_top5 = query_tran_near_snapshot(top5_codes, str(snapshot_ts_max))
    tran_top5.to_csv(os.path.join(OUT, "reserve_backlog_top5_tran.csv"), index=False)
    print(f"cube_inventory_tran rows near snapshot for top5 codes: {len(tran_top5)}")

    # ---------------- PART 3c: warehouse variation, staging check ----------------
    staging_wh = {"QA", "FMTS", "FMTO"}
    inv_nz = inv[inv["reserve_bywa"] != 0]
    per_code_wh_count = inv_nz.groupby("itemcode")["warehouse"].nunique()
    n_codes_multi_wh_reserve = int((per_code_wh_count > 1).sum())
    staging_rows = inv_nz[inv_nz["warehouse"].isin(staging_wh)]
    print(f"3c: {n_codes_multi_wh_reserve} of {len(per_code_wh_count)} codes with nonzero reserve_bywa have it "
          f"spread across >1 warehouse")
    print(f"3c: {len(staging_rows)} of {len(inv_nz)} nonzero-reserve_bywa rows (445-registry) sit on staging "
          f"warehouses {staging_wh}: \n{staging_rows.to_string()}")

    print("\nDone. See output/summary/reserve_backlog_relationship_report.md for full write-up.")


if __name__ == "__main__":
    main()
