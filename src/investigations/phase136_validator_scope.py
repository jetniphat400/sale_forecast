"""Phase 136 Validator -- Part 0: derive PEM103/PEM107 pricelist scope independently.

Reads reference/pricelist.xlsx via src/pricelist_reader.py (visible sheets only) and maps sheets
to divisions using config.yaml's sheet_to_division, exactly as CONVENTIONS.md requires (pricelist
is authoritative for division, database division column is reference-only).
"""
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pricelist_reader import load_visible_product_rows

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

with open(ROOT / "config" / "config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

pricelist_path = ROOT / cfg["pricelist_path"]
sheet_to_division = cfg["sheet_to_division"]

df = load_visible_product_rows(str(pricelist_path))
df["division"] = df["sheet"].map(sheet_to_division)

unmapped = df[df["division"].isna()]
if len(unmapped):
    logger.info("%d rows on visible sheets not in sheet_to_division (excluded): sheets=%s",
                len(unmapped), unmapped["sheet"].unique().tolist())

scope = df[df["division"].isin(["PEM103", "PEM107"])].copy()
scope = scope.drop_duplicates(subset=["code", "division"])

for div in ["PEM103", "PEM107"]:
    codes = scope.loc[scope["division"] == div, "code"].unique().tolist()
    logger.info("%s: %d distinct item codes", div, len(codes))
    out_path = ROOT / "output" / "data" / f"phase136_validator_{div}_codes.csv"
    scope.loc[scope["division"] == div, ["code", "division", "sheet", "category", "type"]] \
        .drop_duplicates().to_csv(out_path, index=False)
    logger.info("Wrote %s", out_path)

combined_codes = scope["code"].unique().tolist()
logger.info("Combined PEM103+PEM107 distinct codes: %d", len(combined_codes))
