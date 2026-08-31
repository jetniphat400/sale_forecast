"""Phase 2 Step 1 exploration: schema verification, pricelist cross-check,
Phase 1 figure re-verification, and Fuse/Surge Arrester sales overview.

Data exploration only. Does not build a forecasting model and does not
touch config.yaml.
"""
import logging
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import run_query
from pricelist_reader import load_visible_product_rows

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("explore_fuse_surge")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")
PRICELIST_PATH = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49
CUTOFF_DATE = "2024-01-01"


def classify(adi: float, cv2: float) -> str:
    """Syntetos-Boylan demand classification from ADI and CV-squared."""
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        return "Smooth"
    if adi < ADI_THRESHOLD and cv2 >= CV2_THRESHOLD:
        return "Erratic"
    if adi >= ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        return "Intermittent"
    return "Lumpy"


def step3_pricelist(pricelist_path: str) -> pd.DataFrame:
    logger.info("=== STEP 3: reading pricelist (visible sheets only) ===")
    df = load_visible_product_rows(pricelist_path)
    df.to_csv(os.path.join(DATA_DIR, "raw_pricelist_visible_rows.csv"), index=False)

    distinct_codes = df["code"].nunique()
    logger.info("Total distinct product codes across visible sheets: %d", distinct_codes)

    dup = df.groupby("code")["sheet"].nunique()
    dup_codes = dup[dup > 1]
    if len(dup_codes) > 0:
        logger.info("%d product codes appear on more than one visible sheet", len(dup_codes))
    else:
        logger.info("No product code appears on more than one visible sheet")

    fuse_surge = df[df["category"].isin(["Fuse", "Surge Arrester"])]
    by_type = fuse_surge.groupby(["category", "type"])["code"].nunique().reset_index()
    by_type.columns = ["category", "type", "item_count"]
    by_type.to_csv(os.path.join(SUMMARY_DIR, "step3_fuse_surge_by_type.csv"), index=False)

    return df, dup_codes, fuse_surge, by_type


def step4_verify_phase1(pricelist_df: pd.DataFrame):
    logger.info("=== STEP 4: re-verifying provisional Phase 1 figures ===")
    total_codes = pricelist_df["code"].nunique()
    logger.info("Recomputed distinct pricelist product codes: %d (STATUS.md claims 448)", total_codes)

    db_codes = run_query("SELECT DISTINCT itemcode FROM cube_Sale_APD WHERE itemcode IS NOT NULL")
    db_code_set = set(db_codes["itemcode"].str.strip())
    pricelist_code_set = set(pricelist_df["code"])
    matched = pricelist_code_set & db_code_set
    logger.info("Recomputed matched codes (pricelist ∩ db itemcode): %d (STATUS.md claims 344)", len(matched))

    candidates = {}
    q_actual_all = run_query(
        f"SELECT SUM(sale) AS total_sale FROM cube_Sale_APD WHERE status = 'Actual' AND createDate >= '{CUTOFF_DATE}'"
    )
    candidates["Actual only, all items, createDate>=2024-01-01"] = q_actual_all["total_sale"].iloc[0]

    q_actual_mps_all = run_query(
        f"SELECT SUM(sale) AS total_sale FROM cube_Sale_APD WHERE status IN ('Actual','MPS') AND createDate >= '{CUTOFF_DATE}'"
    )
    candidates["Actual+MPS, all items, createDate>=2024-01-01"] = q_actual_mps_all["total_sale"].iloc[0]

    matched_list = "','".join(sorted(matched))
    q_actual_matched = run_query(
        f"SELECT SUM(sale) AS total_sale FROM cube_Sale_APD WHERE status = 'Actual' AND createDate >= '{CUTOFF_DATE}' AND itemcode IN ('{matched_list}')"
    )
    candidates["Actual only, matched items only, createDate>=2024-01-01"] = q_actual_matched["total_sale"].iloc[0]

    for label, val in candidates.items():
        val_m = (val or 0) / 1_000_000
        logger.info("Candidate total sales [%s] = %.1f million THB (STATUS.md claims 2,015.3)", label, val_m)

    return total_codes, matched, candidates


def step5_sales_overview(fuse_surge_df: pd.DataFrame):
    logger.info("=== STEP 5: sales overview for Fuse and Surge Arrester groups ===")
    codes = sorted(fuse_surge_df["code"].unique())
    code_list = "','".join(codes)

    raw_sql = (
        "SELECT itemcode, status, createDate, qty, sale "
        "FROM cube_Sale_APD "
        f"WHERE itemcode IN ('{code_list}') "
        f"AND status IN ('Actual','MPS') AND createDate >= '{CUTOFF_DATE}'"
    )
    raw = run_query(raw_sql)
    raw.to_csv(os.path.join(DATA_DIR, "raw_fuse_surge_sales.csv"), index=False)
    logger.info("Rows pulled from database: %d", len(raw))

    before = len(raw)
    raw["createDate"] = pd.to_datetime(raw["createDate"])
    neg_qty = (raw["qty"] < 0).sum()
    neg_sale = (raw["sale"] < 0).sum()
    if neg_qty or neg_sale:
        logger.warning("Found %d rows with negative qty and %d rows with negative sale — kept, not dropped (could be legitimate returns/credit notes; flagged for review, not silently excluded)", neg_qty, neg_sale)

    raw["year_month"] = raw["createDate"].dt.to_period("M")
    dropped = before - len(raw)
    logger.info("Rows processed: %d, rows dropped: %d (reason: none dropped at this stage)", len(raw), dropped)

    monthly = raw.groupby(["itemcode", "year_month"], as_index=False).agg(
        qty=("qty", "sum"), sale=("sale", "sum")
    )
    monthly.to_csv(os.path.join(DATA_DIR, "processed_fuse_surge_monthly.csv"), index=False)

    all_months = pd.period_range(monthly["year_month"].min(), monthly["year_month"].max(), freq="M")
    total_periods = len(all_months)
    logger.info("Observation window: %s to %s (%d months)", all_months.min(), all_months.max(), total_periods)

    code_to_type = fuse_surge_df.drop_duplicates("code").set_index("code")[["category", "type"]]

    item_stats = []
    for code in codes:
        sub = monthly[monthly["itemcode"] == code]
        nonzero_months = (sub["qty"] > 0).sum()
        total_qty = sub["qty"].sum()
        total_sale = sub["sale"].sum()
        if nonzero_months == 0:
            adi = None
            cv2 = None
            cls = "No sales"
        else:
            adi = total_periods / nonzero_months
            demand_vals = sub.loc[sub["qty"] > 0, "qty"]
            mean_d = demand_vals.mean()
            std_d = demand_vals.std(ddof=1) if len(demand_vals) > 1 else 0.0
            cv2 = (std_d / mean_d) ** 2 if mean_d else 0.0
            cls = classify(adi, cv2)
        row = code_to_type.loc[code] if code in code_to_type.index else pd.Series({"category": None, "type": None})
        item_stats.append({
            "code": code, "category": row["category"], "type": row["type"],
            "nonzero_months": nonzero_months, "total_qty": total_qty, "total_sale": total_sale,
            "adi": adi, "cv2": cv2, "classification": cls,
        })
    item_stats_df = pd.DataFrame(item_stats)
    item_stats_df.to_csv(os.path.join(SUMMARY_DIR, "step5_item_level_stats.csv"), index=False)

    type_summary = []
    for (cat, typ), grp in item_stats_df.groupby(["category", "type"]):
        n_items = len(grp)
        n_with_sales = (grp["classification"] != "No sales").sum()
        n_no_sales = n_items - n_with_sales
        total_value = grp["total_sale"].sum()
        total_qty_g = grp["total_qty"].sum()
        type_summary.append({
            "category": cat, "type": typ, "n_items": n_items,
            "n_with_sales": n_with_sales, "n_no_sales": n_no_sales,
            "total_sale_value": total_value, "total_qty": total_qty_g,
        })
    type_summary_df = pd.DataFrame(type_summary)
    grand_total = type_summary_df["total_sale_value"].sum()
    type_summary_df["share_of_group_total"] = type_summary_df["total_sale_value"] / grand_total if grand_total else 0
    type_summary_df.to_csv(os.path.join(SUMMARY_DIR, "step5_type_summary.csv"), index=False)

    top_items_frames = []
    for (cat, typ), grp in item_stats_df.groupby(["category", "type"]):
        top = grp.sort_values("total_sale", ascending=False).head(10).copy()
        top["category"] = cat
        top["type"] = typ
        top_items_frames.append(top)
    top_items_df = pd.concat(top_items_frames, ignore_index=True) if top_items_frames else pd.DataFrame()
    top_items_df.to_csv(os.path.join(SUMMARY_DIR, "step5_top_items_by_type.csv"), index=False)

    for typ, grp in monthly.merge(code_to_type, left_on="itemcode", right_index=True).groupby("type"):
        pivot = grp.groupby("year_month")["qty"].sum()
        if pivot.empty:
            continue
        fig, ax = plt.subplots(figsize=(10, 4))
        pivot.index = pivot.index.to_timestamp()
        ax.plot(pivot.index, pivot.values, marker="o")
        ax.set_title(f"Monthly qty — {typ}")
        ax.set_xlabel("Month")
        ax.set_ylabel("Quantity")
        fig.tight_layout()
        safe_name = "".join(c if c.isalnum() else "_" for c in typ)[:60]
        fig.savefig(os.path.join(CHARTS_DIR, f"monthly_qty_{safe_name}.png"))
        plt.close(fig)

    logger.info("Step 5 outputs written: item stats, type summary, top items, %d charts",
                len(monthly.merge(code_to_type, left_on="itemcode", right_index=True)["type"].unique()))

    return item_stats_df, type_summary_df, top_items_df, total_periods


def step6_pilot_codes(item_stats_df: pd.DataFrame):
    logger.info("=== STEP 6: pilot code positions ===")
    pilot_codes = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]
    results = []
    for code in pilot_codes:
        row = item_stats_df[item_stats_df["code"] == code]
        if row.empty:
            logger.warning("Pilot code %s not found in Fuse/Surge Arrester pulled data", code)
            continue
        row = row.iloc[0]
        typ = row["type"]
        type_group = item_stats_df[item_stats_df["type"] == typ].sort_values("total_sale", ascending=False).reset_index(drop=True)
        rank = type_group[type_group["code"] == code].index[0] + 1
        type_total = type_group["total_sale"].sum()
        share = row["total_sale"] / type_total if type_total else 0
        results.append({
            "code": code, "type": typ, "rank_in_type": rank, "n_items_in_type": len(type_group),
            "share_of_type_total": share, "nonzero_months": row["nonzero_months"],
            "adi": row["adi"], "cv2": row["cv2"], "classification": row["classification"],
        })
    pilot_df = pd.DataFrame(results)
    pilot_df.to_csv(os.path.join(SUMMARY_DIR, "step6_pilot_codes.csv"), index=False)
    return pilot_df


if __name__ == "__main__":
    pricelist_df, dup_codes, fuse_surge_df, by_type_df = step3_pricelist(PRICELIST_PATH)
    total_codes, matched, sales_candidates = step4_verify_phase1(pricelist_df)
    item_stats_df, type_summary_df, top_items_df, total_periods = step5_sales_overview(fuse_surge_df)
    pilot_df = step6_pilot_codes(item_stats_df)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Distinct pricelist codes (visible sheets): {total_codes} (STATUS.md: 448)")
    print(f"Matched to DB itemcode: {len(matched)} (STATUS.md: 344)")
    for label, val in sales_candidates.items():
        print(f"Total sales [{label}]: {(val or 0)/1_000_000:.1f}M THB (STATUS.md: 2,015.3M)")
    print(f"\nDuplicate codes across visible sheets: {len(dup_codes)}")
    print("\nFuse/Surge Arrester item counts by type:")
    print(by_type_df.to_string(index=False))
    print(f"\nObservation window: {total_periods} months")
    print("\nType summary:")
    print(type_summary_df.to_string(index=False))
    print("\nPilot code positions:")
    print(pilot_df.to_string(index=False))
