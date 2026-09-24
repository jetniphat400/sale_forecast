"""Q23 Part 1 -- Explorer: channel mix per division per year (PEM101/PEM103/PEM107, FULL
pricelist scope, all database revenue_type values, all -OLD division tags included).

Target node: Q23 (PROJECT_GRAPH.md) -- does the Omni Channel scope explain observed stock/delivery
behaviour, or must production/stock shared with Tendering be included? Unblocks Q22 (PEM103's path
into G3) and the PEM107 part of Q10 (its unexplained 2026 decline).

ONE DB connection attempt (this task's DATABASE ACCESS RULE) -- if the first query fails to
connect/authenticate, this script raises and stops; if it succeeds, every subsequent query in this
same run is normal use of an established connection, not a retry.

Division scope: FULL pricelist codes (NOT the 128-item PEM101 pilot, NOT the 351-item combined
Omni-only scope already cached on disk) -- PEM101=171, PEM103=87, PEM107=136 codes, from
reference/pricelist.xlsx via config['sheet_to_division'], per CONVENTIONS.md (pricelist is
authoritative; database `division`, including -OLD tags, is reference-only, never a filter).

No revenue_type filter and no status filter at pull time -- this task needs the FULL channel/status
mix, not the project's usual Omni-Channel/Actual+MPS scope.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseQ23_explorer")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

DIVISIONS = ["PEM101", "PEM103", "PEM107"]
PILOT_CATEGORIES = ["Fuse", "Surge Arrester"]  # the 128-item PEM101 pilot's own definition


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_full_scope(config):
    pdf = load_visible_product_rows(os.path.join(PROJECT_ROOT, config["pricelist_path"]))
    sheet_to_division = config["sheet_to_division"]
    pdf = pdf[pdf["sheet"].isin([s for s, d in sheet_to_division.items() if d in DIVISIONS])].copy()
    pdf["division"] = pdf["sheet"].map(sheet_to_division)
    pdf = pdf.drop_duplicates(subset=["code"])
    counts = pdf.groupby("division")["code"].nunique().to_dict()
    logger.info("Full pricelist scope per division: %s", counts)
    return pdf


def main():
    config = load_config()
    scope = get_full_scope(config)
    all_codes = sorted(scope["code"].unique())
    division_by_code = dict(zip(scope["code"], scope["division"]))
    logger.info("Total distinct codes across PEM101/PEM103/PEM107: %d", len(all_codes))

    code_list = "','".join(all_codes)
    sql = f"""
        SELECT itemcode, createDate, forecast_date, qty, sale, cost, status, contractid,
               division AS division_db_raw, revenue_type
        FROM [salewarehouse].[dbo].[cube_Sale_APD]
        WHERE itemcode IN ('{code_list}')
          AND createDate >= '2023-01-01'
    """
    raw = run_query(sql)  # <-- the one DB connection attempt
    logger.info("DB connection succeeded. Pulled %d raw rows (all revenue_type, all status, no division filter).", len(raw))

    raw["createDate"] = pd.to_datetime(raw["createDate"])
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"], errors="coerce")
    raw["division"] = raw["itemcode"].map(division_by_code)
    unmapped = raw[raw["division"].isna()]
    if len(unmapped):
        raise ValueError(f"{len(unmapped)} rows have an itemcode with no pricelist division mapping.")
    raw["year"] = raw["createDate"].dt.year

    neg = raw[(raw["qty"] < 0) | (raw["sale"] < 0)]
    logger.info("%d rows with negative qty/sale (kept, reported, not silently dropped): status values %s",
                len(neg), neg["status"].value_counts().to_dict() if len(neg) else {})

    raw_path = os.path.join(DATA_DIR, "phaseQ23_raw_sales_allchannels_351full.csv")
    raw.to_csv(raw_path, index=False)
    logger.info("Saved raw pull: %s", raw_path)

    status_counts = raw["status"].value_counts()
    logger.info("Status value counts (all, before any status filter): %s", status_counts.to_dict())
    confirmed = raw[raw["status"].isin(["Actual", "MPS"])].copy()
    n_excluded_status = len(raw) - len(confirmed)
    logger.info("%d of %d rows (%.2f%%) excluded by the Actual+MPS status basis (reported, not silently dropped): "
                "excluded status values = %s", n_excluded_status, len(raw),
                100 * n_excluded_status / len(raw) if len(raw) else 0,
                raw.loc[~raw["status"].isin(["Actual", "MPS"]), "status"].value_counts().to_dict())

    # ---- Channel mix crosstab: value (sale) and qty by division x year x revenue_type ----
    mix = confirmed.groupby(["division", "year", "revenue_type"], as_index=False).agg(
        value=("sale", "sum"), qty=("qty", "sum"))
    totals = mix.groupby(["division", "year"])[["value", "qty"]].transform("sum")
    mix["value_share_pct"] = 100 * mix["value"] / totals["value"]
    mix["qty_share_pct"] = 100 * mix["qty"] / totals["qty"]
    mix = mix.sort_values(["division", "year", "value_share_pct"], ascending=[True, True, False])
    mix_path = os.path.join(SUMMARY_DIR, "phaseQ23_channel_mix_by_division_year.csv")
    mix.to_csv(mix_path, index=False)

    # Reconciliation: mix totals must equal confirmed's own filtered totals
    recon_value = abs(mix["value"].sum() - confirmed["sale"].sum())
    recon_qty = abs(mix["qty"].sum() - confirmed["qty"].sum())
    assert recon_value < 1e-6 and recon_qty < 1e-6, "Reconciliation FAILED"
    logger.info("Reconciliation OK: crosstab totals match confirmed-source totals exactly "
                "(value diff=%.6f, qty diff=%.6f)", recon_value, recon_qty)

    # Flags: any revenue_type other than Omni Channel/Tendering above 2% of a division-year's value
    flags = mix[(~mix["revenue_type"].isin(["Omni Channel", "Tendering"])) & (mix["value_share_pct"] > 2.0)]
    flags_path = os.path.join(SUMMARY_DIR, "phaseQ23_gt2pct_other_channel_flags.csv")
    flags.to_csv(flags_path, index=False)
    logger.info("%d (division, year, revenue_type) rows flagged >2%% value share, non-Omni/Tendering:\n%s",
                len(flags), flags.to_string(index=False) if len(flags) else "(none)")

    # ---- PEM101: full 171 codes vs 128-item Fuse/Surge-Arrester pilot -- Omni-dominance ----
    pilot_scope = scope[(scope["division"] == "PEM101") & (scope["category"].isin(PILOT_CATEGORIES))]
    pilot_codes = set(pilot_scope["code"].unique())
    full101_codes = set(scope.loc[scope["division"] == "PEM101", "code"].unique())
    logger.info("PEM101 pilot codes (Fuse/Surge Arrester on PEM101 sheet): %d ; full PEM101 sheet codes: %d",
                len(pilot_codes), len(full101_codes))

    pem101_confirmed = confirmed[confirmed["division"] == "PEM101"]

    def omni_share(df, codes):
        sub = df[df["itemcode"].isin(codes)]
        total_value = sub["sale"].sum()
        omni_value = sub.loc[sub["revenue_type"] == "Omni Channel", "sale"].sum()
        return {
            "n_codes": len(codes), "n_codes_with_rows": sub["itemcode"].nunique(),
            "total_value": float(total_value), "omni_value": float(omni_value),
            "omni_value_share_pct": 100 * omni_value / total_value if total_value else np.nan,
        }

    pilot_result = omni_share(pem101_confirmed, pilot_codes)
    full_result = omni_share(pem101_confirmed, full101_codes)
    pem101_compare = pd.DataFrame([
        {"scope": "128-item pilot (Fuse/Surge Arrester)", **pilot_result},
        {"scope": "full 171-code PEM101 scope", **full_result},
    ])
    pem101_compare_path = os.path.join(SUMMARY_DIR, "phaseQ23_pem101_omni_dominance_compare.csv")
    pem101_compare.to_csv(pem101_compare_path, index=False)
    logger.info("PEM101 Omni-dominance comparison:\n%s", pem101_compare.to_string(index=False))

    # ---- Second-direction cross-check: existing cached Omni-only 351-item pull ----
    cross_check = None
    existing_path = os.path.join(DATA_DIR, "phaseI_raw_sales_351items.csv")
    if os.path.exists(existing_path):
        existing = pd.read_csv(existing_path)
        existing["createDate"] = pd.to_datetime(existing["createDate"])
        existing["year"] = existing["createDate"].dt.year
        existing_scope_codes = set(existing["itemcode"].unique())
        this_pull_same_scope = confirmed[
            confirmed["itemcode"].isin(existing_scope_codes) & (confirmed["revenue_type"] == "Omni Channel")
            & confirmed["year"].between(2024, existing["year"].max())
        ]
        v_new = this_pull_same_scope["sale"].sum()
        v_old = existing.loc[existing["year"] <= this_pull_same_scope["year"].max(), "sale"].sum()
        cross_check = {"existing_351_item_omni_value_2024plus": float(v_old),
                        "this_pull_same_351_items_omni_value_2024plus": float(v_new),
                        "abs_diff": float(abs(v_old - v_new)),
                        "pct_diff": float(100 * abs(v_old - v_new) / v_old) if v_old else None}
        logger.info("Cross-check vs cached Omni-only 351-item pull (consistency check, not independent "
                    "correctness proof -- CONVENTIONS.md): %s", cross_check)

    # ---- Cube_CES pull (for Part 4's channel-split not_late; check schema first) ----
    schema = run_query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'Cube_CES'
    """)
    ces_cols = set(schema["COLUMN_NAME"])
    logger.info("Cube_CES columns: %s", sorted(ces_cols))
    has_native_revenue_type = any("revenue" in c.lower() for c in ces_cols)
    logger.info("Cube_CES has a native revenue-type-like column: %s", has_native_revenue_type)

    ces = run_query(f"""
        SELECT ItemCode, ContractID, Status, CtrDate, PlanDelDate, ForecastDelDate, ActualDelDate, ActualQty,
               RevenueType
        FROM Cube_CES
        WHERE ItemCode IN ('{code_list}')
          AND CtrDate >= '2023-01-01'
    """)
    logger.info("Pulled %d Cube_CES rows for the 394-code scope.", len(ces))

    # Cube_CES carries its OWN native RevenueType column (confirmed by the schema check above) --
    # use it directly as the primary source (same table, no join needed, no join-key ambiguity).
    # ALSO cross-check it against cube_Sale_APD's revenue_type via a (contractid, itemcode) join,
    # as a consistency check (CONVENTIONS.md: agreement between two same-upstream-fed tables shows
    # consistency, not independent correctness) -- not a replacement for the native column.
    ces = ces.rename(columns={"RevenueType": "revenue_type_ces_native"})
    rt_map = raw[["contractid", "itemcode", "revenue_type"]].drop_duplicates()
    dupe_check = rt_map.groupby(["contractid", "itemcode"])["revenue_type"].nunique()
    n_multi_revenue_type_contracts = int((dupe_check > 1).sum())
    logger.info("%d of %d (contractid, itemcode) pairs have MORE THAN ONE revenue_type in cube_Sale_APD "
                "(join ambiguity, reported not hidden).", n_multi_revenue_type_contracts, len(dupe_check))
    rt_map_dedup = rt_map.drop_duplicates(subset=["contractid", "itemcode"], keep="first")
    ces["ContractID"] = ces["ContractID"].astype(str)
    rt_map_dedup["contractid"] = rt_map_dedup["contractid"].astype(str)
    ces_with_rt = ces.merge(rt_map_dedup, left_on=["ContractID", "ItemCode"],
                             right_on=["contractid", "itemcode"], how="left")
    ces_with_rt = ces_with_rt.rename(columns={"revenue_type": "revenue_type_apd_joined"})
    ces_with_rt["revenue_type"] = ces_with_rt["revenue_type_ces_native"]  # authoritative, same-table field
    n_matched_join = ces_with_rt["revenue_type_apd_joined"].notna().sum()
    both = ces_with_rt.dropna(subset=["revenue_type_ces_native", "revenue_type_apd_joined"])
    n_agree = (both["revenue_type_ces_native"] == both["revenue_type_apd_joined"]).sum()
    logger.info("Cube_CES.RevenueType (native, used as authoritative) vs cube_Sale_APD.revenue_type "
                "(joined via ContractID+ItemCode): join covers %d/%d (%.2f%%) CES rows; of those, "
                "%d/%d (%.2f%%) AGREE with the native RevenueType value (consistency check only).",
                n_matched_join, len(ces_with_rt), 100 * n_matched_join / len(ces_with_rt) if len(ces_with_rt) else 0,
                n_agree, len(both), 100 * n_agree / len(both) if len(both) else 0)
    ces_path = os.path.join(DATA_DIR, "phaseQ23_cube_ces_351full.csv")
    ces_with_rt.to_csv(ces_path, index=False)
    logger.info("Saved Cube_CES extract with revenue_type attached: %s", ces_path)

    # ---- Report ----
    report_path = os.path.join(SUMMARY_DIR, "phaseQ23_explorer_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Q23 Part 1 -- Explorer: channel mix per division per year\n\n")
        f.write(f"One DB connection, succeeded on first attempt. Raw pull: {len(raw)} rows, "
                f"{len(all_codes)} distinct pricelist codes (PEM101={full_result['n_codes']}, "
                f"PEM103={(scope['division']=='PEM103').sum()}, PEM107={(scope['division']=='PEM107').sum()}), "
                f"createDate >= 2023-01-01, max createDate = {raw['createDate'].max()}.\n\n")
        f.write("## Status basis\n\n")
        f.write(f"All statuses in this pull: {status_counts.to_dict()}. Headline channel-mix table below "
                f"uses Actual+MPS only (project convention, config.yaml status_basis) -- "
                f"{n_excluded_status} of {len(raw)} rows ({100*n_excluded_status/len(raw):.2f}%) excluded, "
                f"not silently dropped. **Level: V1** (one pull, one direction).\n\n")
        f.write("## Channel mix crosstab (division x year x revenue_type)\n\n")
        f.write("```\n" + mix.to_string(index=False) + "\n```\n\n")
        f.write("Reconciled exactly against the confirmed-status source total (CONVENTIONS.md). **V1**.\n\n")
        f.write("## >2% non-Omni/Tendering flags\n\n")
        f.write("```\n" + (flags.to_string(index=False) if len(flags) else "None found.") + "\n```\n\n")
        f.write("## PEM101: full 171-code scope vs 128-item pilot -- Omni-dominance\n\n")
        f.write("```\n" + pem101_compare.to_string(index=False) + "\n```\n\n")
        f.write(f"**Answer**: {'YES, comparably Omni-dominated' if abs(pilot_result['omni_value_share_pct']-full_result['omni_value_share_pct']) < 5 else 'NO, meaningfully different'} "
                f"-- pilot Omni share {pilot_result['omni_value_share_pct']:.2f}% vs full-171 Omni share "
                f"{full_result['omni_value_share_pct']:.2f}% (diff {abs(pilot_result['omni_value_share_pct']-full_result['omni_value_share_pct']):.2f}pp). "
                f"**Level: V1** (one pull, one direction; not independently recomputed by a second agent here -- "
                f"see Part 6 Validator).\n\n")
        if cross_check:
            f.write("## Cross-check vs cached Omni-only 351-item pull (consistency, not independent correctness -- CONVENTIONS.md)\n\n")
            f.write(f"{cross_check}\n\n")
        f.write("## Cube_CES revenue_type (for Part 4)\n\n")
        f.write(f"Correction during this run: Cube_CES DOES carry its own native `RevenueType` column "
                f"(full schema: {sorted(ces_cols)}) -- used directly as the authoritative revenue_type for "
                f"CES rows (no join needed for the primary value). As a secondary consistency check "
                f"(CONVENTIONS.md: agreement between two same-upstream tables shows consistency, not "
                f"independent correctness), it was also joined against cube_Sale_APD's own revenue_type via "
                f"(ContractID, ItemCode): join covers {n_matched_join}/{len(ces_with_rt)} "
                f"({100*n_matched_join/len(ces_with_rt):.2f}%) of CES rows; of those matched, "
                f"{n_agree}/{len(both)} ({100*n_agree/len(both) if len(both) else 0:.2f}%) agree with the native "
                f"RevenueType value. {n_multi_revenue_type_contracts} of {len(dupe_check)} (contractid,itemcode) "
                f"pairs have more than one revenue_type in cube_Sale_APD (ambiguous, first-seen kept for the "
                f"join, reported not hidden). **Level: V2 for 'Cube_CES.RevenueType exists and is usable directly'** "
                f"(same-table native field, no join uncertainty); **V1 for the cross-table agreement rate** "
                f"(one pull, one direction, consistency only).\n\n")
        f.write("## Files written\n\n")
        f.write(f"- {raw_path}\n- {mix_path}\n- {flags_path}\n- {pem101_compare_path}\n- {ces_path}\n- {report_path}\n")

    logger.info("Report written: %s", report_path)
    print("DONE.")
    print(f"Raw rows: {len(raw)}")
    print(mix.to_string(index=False))
    print(pem101_compare.to_string(index=False))
    if cross_check:
        print("Cross-check:", cross_check)
    print(f"Cube_CES native RevenueType used; cross-join agreement: {n_agree}/{len(both)}")


if __name__ == "__main__":
    main()
