"""Reusable division/pricelist consistency checks (2026-09-04, "Division source-of-truth
correction" — STATUS.md Locked Decisions). Extracted into their own module, separate from any one
investigation script, so they can be unit-tested with synthetic data (no live DB or pricelist file
needed, CONVENTIONS.md code-structure rule: separate data access from computation) and reused by
any script that needs them.
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

OLD_SUFFIX = "-OLD"


def assert_no_code_on_multiple_sheets(pricelist_df: pd.DataFrame) -> None:
    """Raises ValueError if any item code appears on more than one DISTINCT visible sheet.

    `pricelist_df` must have 'sheet' and 'code' columns (e.g. from
    pricelist_reader.load_visible_product_rows). A code repeated as more than one ROW on the SAME
    sheet is a separate, already-known issue (e.g. DS-F-99-0308 on the CI101 sheet) and is not an
    error here — only a code appearing under two DIFFERENT sheet names is, since that would
    silently double-count the item across two divisions (each sheet maps to one division via
    config['sheet_to_division'])."""
    counts = pricelist_df.drop_duplicates(subset=["sheet", "code"]).groupby("code")["sheet"].nunique()
    offenders = counts[counts > 1]
    if len(offenders):
        raise ValueError(
            f"{len(offenders)} item code(s) appear on more than one visible sheet — would be "
            f"counted twice under two different divisions: {offenders.to_dict()}"
        )
    logger.info("Sheet-uniqueness check passed: no code found on more than one visible sheet "
                "(%d distinct codes checked).", pricelist_df["code"].nunique())


def classify_old_tag_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Finds every (contractid, itemcode) pair with at least one row under an -OLD-suffixed
    division_db_raw and at least one row under a non-OLD division_db_raw, and classifies each
    candidate pair as 'CONFIRMED_DUPLICATE' (qty, sale AND forecast_date all match exactly between
    the two rows) or 'distinct_order_or_instalment' (any of the three differs) — this project's
    established split-lot-vs-duplicate key (STATUS.md, "Deep investigation of the 29 remaining
    confirmed duplicate sets").

    `df` must have columns: contractid, itemcode, division_db_raw, qty, sale, forecast_date.
    Returns one row per candidate pair (empty DataFrame, same columns, if no candidates exist —
    never raises just because there is nothing to check)."""
    required = {"contractid", "itemcode", "division_db_raw", "qty", "sale", "forecast_date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"classify_old_tag_duplicates: missing required column(s) {missing}")

    empty_cols = ["contractid", "itemcode", "division_db_raw_old", "division_db_raw_normal",
                  "qty_old", "qty_normal", "sale_old", "sale_normal",
                  "forecast_date_old", "forecast_date_normal", "classification"]

    old_rows = df[df["division_db_raw"].str.endswith(OLD_SUFFIX, na=False)]
    normal_rows = df[~df["division_db_raw"].str.endswith(OLD_SUFFIX, na=False)]
    if old_rows.empty or normal_rows.empty:
        return pd.DataFrame(columns=empty_cols)

    candidates = old_rows.merge(normal_rows, on=["contractid", "itemcode"], suffixes=("_old", "_normal"))
    if candidates.empty:
        return pd.DataFrame(columns=empty_cols)

    candidates["classification"] = np.where(
        (candidates["qty_old"] == candidates["qty_normal"])
        & (candidates["sale_old"] == candidates["sale_normal"])
        & (candidates["forecast_date_old"] == candidates["forecast_date_normal"]),
        "CONFIRMED_DUPLICATE", "distinct_order_or_instalment",
    )
    return candidates[empty_cols]
