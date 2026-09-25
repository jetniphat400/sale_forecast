"""Shared helpers for the CURRENT (v2) forward-test log: generation
(src/forward_test_v2.py) and scoring (src/score_forward_test_v2.py) both need the identical
scope-hash convention and metadata file format, so this module holds them once rather than
duplicating the logic in two places (CONVENTIONS.md: separate data access/computation into
different modules; avoid hidden duplicated logic that could drift out of sync).

Why a scope hash at all: the forward-test log's schema (see src/forward_test_v2.py's docstring)
must let a later consistency check verify the log's ITEM SCOPE still matches the CURRENT
128-item Category scope, not just its config_version and series key -- a scope could change
(an item added/removed/renamed in the pricelist) without config.yaml or the series key changing
at all, so scope needs its own independent fingerprint.
"""
import json
import hashlib


class ForwardTestConsistencyError(Exception):
    """Raised when a forward-test log's recorded config_version/date_key/item_level_approach/
    scope_hash does not match the CURRENT config.yaml and CURRENT 128-item scope file. Never
    caught and silently ignored anywhere -- CONVENTIONS.md requires validation failures to be
    raised loudly, and scoring a stale or mismatched log risks comparing forecasts built under a
    different method/scope to actuals pulled under the one currently adopted."""


def compute_scope_hash(item_codes) -> str:
    """md5 (first 12 hex chars, same convention as forward_test.config_version) of the sorted,
    de-duplicated item-code list. Order-independent and duplicate-independent by construction
    (sorted + set), so it changes if and only if the actual SET of codes changes -- an added,
    removed, or renamed code changes this hash; nothing else does."""
    codes = sorted(set(item_codes))
    joined = ",".join(codes)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()[:12]


def load_metadata(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_metadata(path: str, metadata: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)


# --- Vintage integrity (METRICS.md Sec.27 forward_test_vintage; added for the vintage-1 ---------
# migration/Sec.28 monthly_refresh task) -----------------------------------------------------

ROW_HASH_COLUMNS = [
    "itemcode", "division", "level", "category", "type", "forecast_run_date", "data_cutoff_date",
    "fit_last_month", "model", "config_version", "date_key", "scope_hash", "scope_n_items",
    "horizon", "target_month", "forecast_qty",
]


def compute_row_integrity_hash(vintage_rows) -> str:
    """sha256 (full 64 hex chars -- an integrity/tamper-evidence hash, not a short fingerprint)
    of one vintage's OWN rows at generation time, over every column except `vintage_id` (the
    grouping key itself) and `actual_qty` (METRICS.md Sec.27: "actual_qty is filled once the
    target month becomes eligible" -- the only column this project's own rules allow to change
    after a vintage is written, so it must never be part of what "unchanged" means here).

    Deterministic regardless of input row order: sorts by (itemcode, level, horizon) first, then
    hashes a canonical '|'-joined, newline-separated string built ONLY from ROW_HASH_COLUMNS, in
    that fixed order -- so a re-computation over the log's CURRENT rows for this vintage can be
    compared byte-for-byte against the hash recorded in this vintage's own metadata at generation
    time, independent of the CURRENT live config.yaml or CURRENT item scope (CONVENTIONS.md:
    verify against a direct recomputation, not recall)."""
    df = vintage_rows.sort_values(["itemcode", "level", "horizon"]).reset_index(drop=True)
    lines = []
    for _, row in df.iterrows():
        lines.append("|".join(str(row[c]) for c in ROW_HASH_COLUMNS))
    canonical = "\n".join(lines)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
