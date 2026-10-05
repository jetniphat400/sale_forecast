"""Lead time per item, version 1 (week 1, item 1.3 of STATUS.md's plan; METRICS.md Sec.5, "Item lead time").

    item lead time = slowest material's lead time + the item's production time

Materials: the components of the item in Cube_BOM_Exact, one level, excluding the header row (Sequenceno 0 / blank component) and the
Machine Hour pseudo-codes. A component that has no purchase record and no price-list quote and whose code marks it as an in-house
sub-assembly (code kind W) is NOT walked: its own materials are not in the saved BOM pull, so it is listed and left out of the
maximum; an item left with no purchased material is treated like an item with no BOM (assumed values, labelled).

Per material, one statistic, the median, in this order of sources:
  1. observed: median over the material's purchase orders (Cube_PO_Exact) of the days from PO date to the first receipt (Cube_ReceiveRM,
     key PO number + item), one lead time per (PO, item), usable between 0 and 730 days;
  2. supplier quoted: median of the non-zero Cube_PriceList.DeliveryTime days over the material's suppliers ("0 Days" is not used);
  3. assumed: one configured fallback (config lead_time_v1.fallback_material_days, set at the observed 90th percentile across materials).
The median is used because per-material samples are small and the 0-730 day range holds outliers.

Production time per item, in this order, a source being used only where the tests of week1_leadtime_calibration.md Part 0 support its
meaning:
  1. standard time (Cube_Standard_Time): NOT used. It is the incoming-inspection plan of raw materials (rmid, work instruction, test
     method, sample sizes), not production time;
  2. measured: median over the item's jobs of the days from Cube_Production_Order.start_date to the latest cube_final.final_date of the
     same job and item, when the item has at least config lead_time_v1.production_min_jobs matched jobs;
  3. assumed: one configured value (config lead_time_v1.production_days_assumed).
"""
import hashlib
import json
import os
import re
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
INPUT_DIR = os.path.join(PROJECT_ROOT, "output", "data", "lead_time_inputs")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "output", "summary", "item_lead_time_v1.csv")
META_PATH = os.path.join(PROJECT_ROOT, "output", "summary", "item_lead_time_v1_integrity.json")
USABLE_MIN_DAYS, USABLE_MAX_DAYS = 0, 730
STATISTIC = "median"
OUT_COLUMNS = ["item", "lead_time_days", "bottleneck_material", "bottleneck_days", "bottleneck_source", "production_days", "production_source",
               "production_n_jobs", "n_materials", "n_observed", "n_quoted", "n_assumed", "no_bom", "inhouse_not_walked", "note"]

SRC_OBSERVED, SRC_QUOTED, SRC_ASSUMED = "observed", "supplier_quoted", "assumed"
PROD_MEASURED, PROD_ASSUMED = "measured", "assumed"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["lead_time_v1"]


def _clean(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def walk_bom(bom: pd.DataFrame, item: str) -> list:
    """The material codes of `item`: its one-level components, header rows (Sequenceno 0 or blank component) and Machine Hour
    pseudo-codes excluded, upper-cased, de-duplicated, in code order. An item with no row returns []."""
    b = bom[_clean(bom["ItemFG"]) == item.strip().upper()]
    b = b[b["ItemRawmat"].notna()]
    comp = _clean(b["ItemRawmat"])
    seq = pd.to_numeric(b["Sequenceno"], errors="coerce").fillna(0)
    keep = (comp != "") & (comp != "NAN") & (seq != 0) & (b["Type"].astype(str).str.strip().str.lower() != "machine hour")
    return sorted(set(comp[keep]))


def observed_lead_times(po: pd.DataFrame, receipts: pd.DataFrame) -> pd.DataFrame:
    """One row per (PO, item): days from the PO date to the first receipt, usable between 0 and 730 days."""
    p = po.copy()
    p["po_no"] = _clean(p["po_no"]); p["item"] = _clean(p["item_code"]); p["po_date"] = pd.to_datetime(p["po_date"], errors="coerce")
    p = p.groupby(["po_no", "item"], as_index=False)["po_date"].min()
    r = receipts.copy()
    r["po_no"] = _clean(r["PO"]); r["item"] = _clean(r["Itemcode"]); r["Receive_date"] = pd.to_datetime(r["Receive_date"], errors="coerce")
    r = r.groupby(["po_no", "item"], as_index=False)["Receive_date"].min()
    m = p.merge(r, on=["po_no", "item"], how="inner")
    m["lead_days"] = (m["Receive_date"] - m["po_date"]).dt.days
    return m[m["lead_days"].between(USABLE_MIN_DAYS, USABLE_MAX_DAYS)][["po_no", "item", "lead_days"]].reset_index(drop=True)


def parse_delivery_days(text) -> float:
    """'30 Days' -> 30.0; anything without a number -> NaN. 0 is returned as 0.0 (the caller does not use it)."""
    m = re.search(r"(\d+(?:\.\d+)?)", str(text))
    return float(m.group(1)) if m else float("nan")


def quoted_days_by_material(pricelist: pd.DataFrame) -> dict:
    """{material: median of its non-zero quoted delivery days over suppliers}; materials with only 0 Days are absent."""
    p = pricelist.copy()
    p["item"] = _clean(p["ItemCode"]); p["days"] = p["DeliveryTime"].map(parse_delivery_days)
    p = p[p["days"] > 0]
    return p.groupby("item")["days"].median().to_dict()


def material_lead_time(material: str, observed: dict, quoted: dict, fallback_days: float) -> tuple:
    """(days, source) for one material in the order observed, supplier quoted, assumed."""
    m = material.strip().upper()
    if m in observed:
        return float(observed[m]), SRC_OBSERVED
    if m in quoted:
        return float(quoted[m]), SRC_QUOTED
    return float(fallback_days), SRC_ASSUMED


def is_inhouse_subassembly(material: str) -> bool:
    """Code kind W (for example CA-W-99-010101): made in-house, no purchase record; its own BOM is not in the saved pull."""
    return re.match(r"^[A-Z0-9]+-W-", material.strip().upper()) is not None


def measured_production_days(prod_order: pd.DataFrame, cube_final: pd.DataFrame, since: str = "2023-01-01") -> pd.DataFrame:
    """Per item: number of matched jobs and the median days from Cube_Production_Order.start_date to the latest cube_final.final_date of
    the same job and item. A job counts when both exist and the final date is not before the start date."""
    p = prod_order.copy()
    p["item"] = _clean(p["itemcode"]); p["job"] = p["job"].astype(str).str.strip(); p["start_date"] = pd.to_datetime(p["start_date"], errors="coerce")
    p = p[(p["start_date"] >= since) & (p["job"] != "0") & (p["job"] != "")].drop_duplicates(["job", "item"])
    f = cube_final.copy()
    f["item"] = _clean(f["itemcode"]); f["job"] = f["jobno"].astype(str).str.strip(); f["final_date"] = pd.to_datetime(f["final_date"], errors="coerce")
    f = f.dropna(subset=["final_date"]).groupby(["job", "item"], as_index=False)["final_date"].max()
    m = p.merge(f, on=["job", "item"], how="inner")
    m["days"] = (m["final_date"] - m["start_date"]).dt.days
    m = m[m["days"] >= 0]
    return m.groupby("item").agg(production_n_jobs=("days", "count"), production_median_days=("days", "median")).reset_index()


def compute_item_lead_times(items: list, bom: pd.DataFrame, observed_df: pd.DataFrame, pricelist: pd.DataFrame, production: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """One row per item (OUT_COLUMNS). `cfg` holds fallback_material_days, production_days_assumed and production_min_jobs."""
    observed = observed_df.groupby("item")["lead_days"].median().to_dict()
    n_obs_by_mat = observed_df.groupby("item")["lead_days"].count().to_dict()
    quoted = quoted_days_by_material(pricelist)
    prod = production.set_index("item") if len(production) else pd.DataFrame(columns=["production_n_jobs", "production_median_days"])
    fb, pa, minj = float(cfg["fallback_material_days"]), float(cfg["production_days_assumed"]), int(cfg["production_min_jobs"])
    rows = []
    for item in items:
        it = item.strip().upper()
        mats = walk_bom(bom, it)
        no_bom = len(mats) == 0
        walked, skipped = [], []
        for m in mats:
            d, s = material_lead_time(m, observed, quoted, fb)
            if s == SRC_ASSUMED and is_inhouse_subassembly(m):
                skipped.append(m)
            else:
                walked.append((m, d, s))
        note = ""
        if no_bom:
            note = "no BOM: assumed material and production values"
        elif not walked:
            no_bom = True
            note = "BOM holds only in-house sub-assemblies (not walked): assumed material and production values"
        if no_bom:
            walked = [("(assumed)", fb, SRC_ASSUMED)]
        elif skipped:
            note = "in-house sub-assemblies not walked: " + ", ".join(skipped)
        bott = sorted(walked, key=lambda x: (-x[1], x[0]))[0]
        if it in prod.index and int(prod.loc[it, "production_n_jobs"]) >= minj and not no_bom:
            pdays, psrc, pn = float(prod.loc[it, "production_median_days"]), PROD_MEASURED, int(prod.loc[it, "production_n_jobs"])
        else:
            pdays, psrc, pn = pa, PROD_ASSUMED, int(prod.loc[it, "production_n_jobs"]) if it in prod.index else 0
        rows.append({"item": it, "lead_time_days": round(bott[1] + pdays, 1), "bottleneck_material": bott[0], "bottleneck_days": round(bott[1], 1),
                     "bottleneck_source": bott[2], "production_days": round(pdays, 1), "production_source": psrc, "production_n_jobs": pn,
                     "n_materials": 0 if no_bom else len(walked), "n_observed": sum(1 for w in walked if w[2] == SRC_OBSERVED),
                     "n_quoted": sum(1 for w in walked if w[2] == SRC_QUOTED), "n_assumed": sum(1 for w in walked if w[2] == SRC_ASSUMED),
                     "no_bom": bool(no_bom), "inhouse_not_walked": len(skipped), "note": note})
    return pd.DataFrame(rows, columns=OUT_COLUMNS)


# ---------------------------------------------------------------------------------------------- recorded output with an integrity hash
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_recorded(df: pd.DataFrame, path: str = OUTPUT_PATH, meta_path: str = META_PATH, extra: dict = None) -> dict:
    """Writes the csv, reads it back and records the SHA-256 of the text read back in the integrity json."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    try:
        rel = os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")
    except ValueError:                      # another drive (a temporary test folder)
        rel = path
    meta = {"file": rel, "sha256": sha256_text(text), "n_rows": int(len(df)),
            "columns": list(df.columns), "statistic": STATISTIC, "recorded_at": datetime.now().isoformat(timespec="seconds"), **(extra or {})}
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, default=str)
    return meta


def verify_recorded(path: str = OUTPUT_PATH, meta_path: str = META_PATH) -> bool:
    """True when the csv's text hashes to the recorded value; raises ValueError otherwise."""
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    with open(path, encoding="utf-8", newline="") as f:
        actual = sha256_text(f.read())
    if actual != meta["sha256"]:
        raise ValueError(f"{path} hashes to {actual}, the integrity file records {meta['sha256']}")
    return True


def _read(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(os.path.join(INPUT_DIR, name), **kw)


def main() -> pd.DataFrame:
    cfg = load_config()
    items = json.load(open(os.path.join(INPUT_DIR, "stock92.json"), encoding="utf-8"))
    bom = _read("bom_stock92.csv", dtype=str)
    po = _read("po_rm.csv", dtype=str)
    rcv = _read("receiverm_rm.csv", dtype=str)
    pl = _read("pricelist_rm.csv", dtype=str)
    prod = measured_production_days(_read("prodorder_all.csv", dtype=str), _read("cube_final_all.csv", dtype=str))
    obs = observed_lead_times(po, rcv)
    df = compute_item_lead_times(items, bom, obs, pl, prod, cfg)
    inputs = {}
    for n in ("stock92.json", "bom_stock92.csv", "po_rm.csv", "receiverm_rm.csv", "pricelist_rm.csv", "prodorder_all.csv", "cube_final_all.csv"):
        with open(os.path.join(INPUT_DIR, n), "rb") as f:
            inputs[n] = hashlib.sha256(f.read()).hexdigest()
    meta = write_recorded(df, extra={"config": cfg, "input_sha256": inputs})
    print(df["lead_time_days"].describe().round(1).to_dict(), meta["sha256"])
    return df


if __name__ == "__main__":
    main()
