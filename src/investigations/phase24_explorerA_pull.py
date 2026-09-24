"""Phase 24 Explorer A: test the business's "PEM107 Tendering/Omni shared production/stock,
separated mid-2026" claim (DATA_MAP.md Sec.7, level A, added 2026-09-24) against cube_final +
Cube_CES data.

Linkage used: cube_final.jobno <-> Cube_CES.OLMJobCode (both established as the same
production-batch-reference concept, DATA_MAP.md Sec.2 jobcode/jobno/OLMJobCode entry). This is
chosen over cube_Sale_APD.jobcode because OLMJobCode is a single-token column (no comma-list
splitting needed), and Cube_CES already carries a native RevenueType column (DATA_MAP.md Sec.2,
Cube_CES.RevenueType entry) -- no further join to cube_Sale_APD is required to know a row's
channel.

One connection attempt: two loader calls (pull_cube_final_for_items, pull_cube_ces_for_items) in
the same script/session -- per this project's established precedent, multiple queries in one
connection count as one "attempt".
"""
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cube_final_pull import pull_cube_final_for_items
from cube_ces_pull import pull_cube_ces_for_items, CUBE_CES_COLUMNS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("phase24_explorerA_pull")

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCOPE_FILE = Path(__file__).resolve().parents[2] / "output" / "data" / "phaseI_combined_scope_351items.csv"


def main():
    scope = pd.read_csv(SCOPE_FILE)
    pem107_items = scope.loc[scope["division"] == "PEM107", "code"].dropna().unique().tolist()
    logger.info("PEM107 item scope: %d items (from %s)", len(pem107_items), SCOPE_FILE)

    cube_final_df = pull_cube_final_for_items(pem107_items, allow_empty=False)
    logger.info("cube_final: %d rows, %d distinct jobno", len(cube_final_df),
                cube_final_df["jobno"].nunique())

    ces_cols = CUBE_CES_COLUMNS + ["OLMJobCode"]
    cube_ces_df = pull_cube_ces_for_items(pem107_items, columns=ces_cols, allow_empty=False)
    logger.info("Cube_CES: %d rows, %d distinct OLMJobCode, RevenueType values: %s",
                len(cube_ces_df), cube_ces_df["OLMJobCode"].nunique(),
                cube_ces_df["RevenueType"].value_counts().to_dict())

    # Save raw pulls (customer_name / CustomerName dropped before saving -- privacy rule).
    cf_save = cube_final_df.drop(columns=[c for c in ["customer_name"] if c in cube_final_df.columns])
    ces_save = cube_ces_df.drop(columns=[c for c in ["CustomerName"] if c in cube_ces_df.columns])
    cf_save.to_csv(OUT_DIR / "phase24_explorerA_cube_final_raw.csv", index=False)
    ces_save.to_csv(OUT_DIR / "phase24_explorerA_cube_ces_raw.csv", index=False)
    logger.info("Saved raw pulls to %s", OUT_DIR)


if __name__ == "__main__":
    main()
