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
