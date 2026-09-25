"""Phase 24 Validator Part 1 (PEM107 dual-channel batch share) and Part 2 (MTS/MTO/ETO dominant
counts). No DB access -- uses the cached pulls from phase24_validator_pull.py."""
import os

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

# ============================================================================
# Part 1: PEM107 dual-channel batch share by month
# ============================================================================

def part1():
    cube_final = pd.read_csv(os.path.join(DATA_DIR, "phase24_validator_cube_final_351items.csv"))
    combined = pd.read_csv(os.path.join(DATA_DIR, "phaseI_combined_scope_351items.csv"))
    items_pem107 = set(combined.loc[combined["division"] == "PEM107", "code"])

    cf = cube_final[cube_final["itemcode"].isin(items_pem107)].copy()
    cf["final_date"] = pd.to_datetime(cf["final_date"], errors="coerce")
    print(f"[Part1] cube_final rows for PEM107 itemcode scope: {len(cf)} "
          f"(of {len(cube_final)} total 351-item pull)")
    print(f"[Part1] distinct jobno values in PEM107 cube_final rows: {cf['jobno'].nunique()}")

    ces = pd.read_csv(os.path.join(DATA_DIR, "phase24_validator_cube_ces_pem107.csv"))
    ces = ces.dropna(subset=["OLMJobCode"])
    print(f"[Part1] Cube_CES PEM107 rows with non-null OLMJobCode: {len(ces)} of {len(pd.read_csv(os.path.join(DATA_DIR, 'phase24_validator_cube_ces_pem107.csv')))}")
    print(f"[Part1] RevenueType distinct values in this CES pull: {sorted(ces['RevenueType'].dropna().unique().tolist())}")

    # jobno -> set of RevenueType values seen across Cube_CES (OLMJobCode = jobno join)
    job_to_types = ces.groupby("OLMJobCode")["RevenueType"].apply(lambda s: set(s.dropna())).to_dict()

    def classify(jobno):
        types = job_to_types.get(jobno)
        if not types:
            return "unmatched"
        has_omni = "Omni Channel" in types
        has_tender = "Tendering" in types
        if has_omni and has_tender:
            return "dual"
        elif has_omni or has_tender:
            return "single"
        else:
            return "other_only"  # matched contracts exist but neither Omni nor Tendering

    cf["link_class"] = cf["jobno"].apply(classify)
    print("[Part1] cube_final PEM107 batch link_class counts:")
    print(cf["link_class"].value_counts())

    cf_valid = cf[cf["final_date"].notna()].copy()
    cf_valid["year_month"] = cf_valid["final_date"].dt.to_period("M").astype(str)

    matched = cf_valid[cf_valid["link_class"] != "unmatched"].copy()
    matched["is_dual"] = matched["link_class"] == "dual"

    monthly = matched.groupby("year_month").agg(
        n_batches_matched=("is_dual", "size"), n_dual=("is_dual", "sum")).reset_index()
    monthly["dual_share"] = monthly["n_dual"] / monthly["n_batches_matched"]
    monthly = monthly.sort_values("year_month")

    # Also report total batches (incl. unmatched) per month for context
    total_monthly = cf_valid.groupby("year_month").size().rename("n_batches_total").reset_index()
    monthly = monthly.merge(total_monthly, on="year_month", how="left")

    monthly.to_csv(os.path.join(SUMMARY_DIR, "phase24_validator_pem107_dualchannel_monthly.csv"), index=False)
    print("\n[Part1] Monthly dual-channel batch share (Jan 2025 onward):")
    m2025 = monthly[monthly["year_month"] >= "2025-01"]
    print(m2025.to_string(index=False))

    return monthly


# ============================================================================
# Part 2: MTS/MTO/ETO dominant-type counts per division
# ============================================================================

def part2():
    results = {}
    for div, fname in [("PEM101", "phase24_validator_mtype_pem101.csv"),
                        ("PEM103", "phase24_validator_mtype_pem103.csv"),
                        ("PEM107", "phase24_validator_mtype_pem107.csv")]:
        df = pd.read_csv(os.path.join(DATA_DIR, fname))
        print(f"\n[Part2] {div}: {len(df)} order rows pulled, "
              f"manufacturing_type null count: {df['manufacturing_type'].isna().sum()}")
        df = df[df["manufacturing_type"].notna() & df["qty"].notna() & (df["qty"] != 0)].copy()
        # keep only the three known values; report any others separately
        known = {"MTS", "MTO", "ETO"}
        other_vals = sorted(set(df["manufacturing_type"].unique()) - known)
        if other_vals:
            print(f"[Part2] {div}: manufacturing_type values outside {{MTS,MTO,ETO}}: {other_vals} "
                  f"({df[df['manufacturing_type'].isin(other_vals)].shape[0]} rows, kept in denominator)")

        per_item = df.groupby(["itemcode", "manufacturing_type"])["qty"].sum().reset_index()
        totals = per_item.groupby("itemcode")["qty"].sum().rename("total_qty")
        per_item = per_item.merge(totals, on="itemcode")
        per_item["share"] = per_item["qty"] / per_item["total_qty"]

        dominant = per_item.loc[per_item.groupby("itemcode")["qty"].idxmax()].copy()
        dominant["classification"] = np.where(
            dominant["share"] >= 0.60, dominant["manufacturing_type"], "mixed")

        n_items_with_mtype = dominant["itemcode"].nunique()
        counts = dominant["classification"].value_counts()
        print(f"[Part2] {div}: {n_items_with_mtype} items with manufacturing_type data; "
              f"dominant-class counts:\n{counts}")

        dominant["division"] = div
        results[div] = dominant

    all_dom = pd.concat(results.values(), ignore_index=True)
    all_dom.to_csv(os.path.join(SUMMARY_DIR, "phase24_validator_mts_mto_eto_dominant.csv"), index=False)
    return all_dom


if __name__ == "__main__":
    part1()
    part2()
