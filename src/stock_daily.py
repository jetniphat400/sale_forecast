"""The stock file the Min-Max page loads at runtime: data/stock_daily.json.

It holds every figure on that page that depends on stock (on-hand quantity per item and warehouse) and the two
source load times plus the pull time that the page shows next to those figures. Min, Max and every sales-derived
input stay embedded in the page and change monthly; only this file changes daily.

One format, one builder. The daily job (src/daily_stock_job.py) and the monthly runner's step 7 both call
build_payload() with the same saved pull (build_inventory_dataset.save_pulls), so the same pull gives byte-identical
JSON on both paths (tests/test_daily_stock.py).

Times are this machine's own clock (ICT), 'YYYY-MM-DD HH:MM:SS', never typed: the stock load time is the earliest
`timestamp` of the Cube_Inventory_Exact rows pulled, the reserved load time is the earliest `Timestamp` of the
Cube_CES Status='Backlog' rows pulled, the pull time is the moment the pull finished.
"""
import json
import math
import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK_JSON_PATH = os.path.join(PROJECT_ROOT, "data", "stock_daily.json")
STOCK_JSON_RELATIVE = "data/stock_daily.json"
FORMAT_VERSION = 1
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class StockPayloadError(Exception):
    """The stock payload is malformed or cannot be built from the pull."""


def _earliest(series) -> str:
    ts = pd.to_datetime(series, errors="coerce").dropna()
    return ts.min().strftime(TIME_FORMAT) if len(ts) else None


def build_payload(inventory: pd.DataFrame, backlog_ces: pd.DataFrame, pull_time_local: str) -> dict:
    """Payload from the two pulls. `inventory` needs itemcode, warehouse, stock, timestamp; `backlog_ces` needs
    Timestamp (may be empty). Rows with zero stock are left out: they change no sum the page computes."""
    for c in ("itemcode", "warehouse", "stock", "timestamp"):
        if c not in inventory.columns:
            raise StockPayloadError(f"inventory pull has no {c} column")
    inv = inventory.copy()
    if inv["itemcode"].isna().any() or (inv["itemcode"].astype(str).str.strip() == "").any():
        raise StockPayloadError("inventory pull has a null or empty item code")
    inv["itemcode"] = inv["itemcode"].astype(str).str.strip()
    inv["warehouse"] = inv["warehouse"].astype(str).str.strip()
    grouped = inv.groupby(["itemcode", "warehouse"], as_index=False)["stock"].sum()
    grouped = grouped[grouped["stock"] != 0]
    items = {}
    for code, g in grouped.groupby("itemcode"):
        rows = sorted(((w, round(float(q), 3)) for w, q in zip(g["warehouse"], g["stock"])), key=lambda r: (-r[1], r[0]))
        items[code] = [[w, q] for w, q in rows]
    reserved = _earliest(backlog_ces["Timestamp"]) if backlog_ces is not None and len(backlog_ces) and "Timestamp" in backlog_ces.columns else None
    payload = {
        "format_version": FORMAT_VERSION,
        "pull_time": str(pull_time_local)[:19],
        "stock_source_load_time": _earliest(inv["timestamp"]),
        "reserved_source_load_time": reserved,
        "items": items,
    }
    validate_payload(payload)
    return payload


def validate_payload(payload: dict) -> None:
    """Raises StockPayloadError naming what is wrong. The page applies the same checks before it trusts the file."""
    if not isinstance(payload, dict) or payload.get("format_version") != FORMAT_VERSION:
        raise StockPayloadError(f"format_version is not {FORMAT_VERSION}")
    for k in ("pull_time", "stock_source_load_time"):
        try:
            if not isinstance(payload[k], str) or pd.isna(pd.Timestamp(payload[k])):
                raise ValueError(k)
        except Exception as e:  # noqa: BLE001
            raise StockPayloadError(f"{k} is missing or not a time: {payload.get(k)!r}") from e
    if payload.get("reserved_source_load_time") is not None:
        pd.Timestamp(payload["reserved_source_load_time"])
    items = payload.get("items")
    if not isinstance(items, dict):
        raise StockPayloadError("items is not an object")
    for code, rows in items.items():
        if not code or not isinstance(rows, list):
            raise StockPayloadError(f"bad item entry {code!r}")
        for r in rows:
            if not (isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and isinstance(r[1], (int, float))
                    and math.isfinite(r[1])):
                raise StockPayloadError(f"bad warehouse row for {code}: {r!r}")


def dumps(payload: dict) -> str:
    """The one serialisation: sorted keys, compact, UTF-8, one trailing newline, so equal payloads are equal bytes."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def write_payload(payload: dict, path: str = STOCK_JSON_PATH) -> str:
    validate_payload(payload)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(payload))
    os.replace(tmp, path)
    return path


def read_payload(path: str = STOCK_JSON_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    validate_payload(payload)
    return payload


def from_pulls(pull_dir: str) -> dict:
    """Payload from a pull saved by build_inventory_dataset.save_pulls (no database connection)."""
    import build_inventory_dataset as bid
    frames, meta = bid.load_pulls(pull_dir)
    return build_payload(frames["inventory"], frames["backlog_ces"], meta["pulled_at_local"])


def apply_to_data(data: dict, payload: dict) -> dict:
    """Puts the payload's per-warehouse stock into the page's embedded data (Python side of the page's applyStock),
    so reference computations and tests see what the page sees after it loads the file."""
    by_code = payload["items"]
    for division in data["divisions"].values():
        for item in division["items"]:
            item["by_warehouse"] = [{"code": w, "qty": q} for w, q in by_code.get(item["code"], [])]
    return data
