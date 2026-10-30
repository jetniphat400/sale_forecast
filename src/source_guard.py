"""Shared source guard (Prompt 63): one check, configured in one block (config.yaml `source_guard`), applied right after every database pull of the daily job and of the monthly runner's
step 1, before anything pulled is written to a page, published, or used by a fit or a new vintage.

Why: on 2026-10-29 12:00 the Cube_CES table returned 0 rows (Reserved and PEM107). The reserved rows reached the live dashboard because no gate looked at that pull (c791e27 closed that for Reserved
only); any other source table could fail the same way.

What it checks, per source (the settings of the source over the block's defaults):
  * rows band  - zero rows fail unless the source's `zero_allowed` is true; otherwise the row count must lie within `rows_band_pct` percent of the base. The base is the first usable one of the
                 caller's list: the stored base (the last good pull of that source, written by `write_base` only after a pull passed), then what the caller can read of the data now on disk or
                 published. With no base at all the gate FAILS (closed): an unchecked pull is not used.
  * load time  - only for a source whose settings say `load_time: true`: the source table's own load time must exist and be no older than `max_load_age_hours` against the reference time.
  * key columns - only when the caller passes the null counts of the source's key columns: every count must be 0.
A finding is {"gate", "source", "check", "passed", "detail", "values"}; `failed()` filters them. This module only decides; what a failure does (hold the publish, put back the source's files,
abort the monthly run at step 1) is the caller's: see daily_stock_job.check_gates, daily_rebuild.run_extras and monthly_refresh.guard_stage.
"""
import json
import os
from datetime import datetime

import pandas as pd


def settings(config: dict, name: str) -> dict:
    """The settings of source `name`: the block's `defaults` overridden by the source's own entry. KeyError when the source is not listed (an unlisted source is a bug, not a pass)."""
    block = config["source_guard"]
    merged = dict(block.get("defaults", {}))
    merged.update(block["sources"][name])
    return merged


def band(name: str, today: float, base_value: float, pct: float) -> dict:
    """Same semantics as daily_stock_job._band: the relative change in percent and whether it lies within +/-pct."""
    change = 100.0 * (today - base_value) / base_value if base_value else float("inf")
    ok = abs(change) <= pct
    return {"gate": name, "passed": bool(ok), "today": today, "base": base_value, "change_pct": round(change, 2) if change != float("inf") else None, "band_pct": pct,
            "detail": f"{today:,.0f} against {base_value:,.0f} ({change:+.1f}%), allowed +/-{pct}%"}


def _finding(name: str, check: str, passed: bool, detail: str, **values) -> dict:
    return {"gate": f"{name}_{check}", "source": name, "check": check, "passed": bool(passed), "detail": detail, **values}


def check_rows(name: str, config: dict, rows: int, bases: list = None) -> dict:
    """The rows-band finding. `bases` = [(row count or None, label), ...] in order of preference."""
    cfg = settings(config, name)
    label = cfg.get("label", "rows")
    base_rows, base_label = None, None
    for value, text in (bases or []):
        if value and value > 0:
            base_rows, base_label = value, text
            break
    if rows == 0:
        allowed = bool(cfg.get("zero_allowed", False))
        out = _finding(name, "rows_band", allowed,
                       f"0 {label} in the pull: " + (f"allowed (source_guard.sources.{name}.zero_allowed)" if allowed else f"a zero count is not used (source_guard.sources.{name}.zero_allowed is false)")
                       + (f"; the last good count was {base_rows:,}" if base_rows else ""), today=0.0, base=base_rows)
    elif not base_rows:
        out = _finding(name, "rows_band", False, f"{rows:,} {label} but nothing to compare with (no stored count and no earlier data to read): held, not used", today=float(rows), base=None)
    else:
        out = {**band(f"{name}_rows_band", float(rows), float(base_rows), cfg["rows_band_pct"]), "source": name, "check": "rows_band", "base_source": base_label}
        out["detail"] = f"{label}: " + out["detail"]
    return out


def check_load_time(name: str, config: dict, load_time, reference_time=None) -> dict:
    """Present, and not older than max_load_age_hours against `reference_time` (default: now)."""
    cfg = settings(config, name)
    if load_time is None or str(load_time).strip() in ("", "NaT", "None"):
        return _finding(name, "load_time_present", False, f"the {cfg.get('label', name)} source has no load time (no Timestamp in the pull)", load_time=None)
    try:
        loaded = pd.Timestamp(load_time)
        ref = pd.Timestamp(reference_time) if reference_time is not None else pd.Timestamp(datetime.now())
        age_h = (ref - loaded).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return _finding(name, "load_time_present", False, f"the {cfg.get('label', name)} source's load time {load_time!r} cannot be read", load_time=str(load_time))
    limit = cfg.get("max_load_age_hours")
    if limit is not None and age_h > limit:
        return _finding(name, "load_time_present", False, f"the {cfg.get('label', name)} source's load time is {load_time}, {age_h:.1f} h before the pull (allowed {limit} h): the source stopped loading", load_time=str(load_time), age_hours=round(age_h, 1))
    return _finding(name, "load_time_present", True, f"the {cfg.get('label', name)} source's load time is {load_time}" + (f", {age_h:.1f} h before the pull (allowed {limit} h)" if limit is not None else ""),
                    load_time=str(load_time), age_hours=round(age_h, 1))


def check_keys(name: str, key_nulls: dict) -> dict:
    bad = {k: int(v) for k, v in (key_nulls or {}).items() if v}
    return _finding(name, "key_columns", not bad, "no null or empty key column" if not bad else "null or empty keys: " + ", ".join(f"{k} {v}" for k, v in bad.items()), nulls=bad)


def evaluate(name: str, config: dict, *, rows: int, bases: list = None, load_time="__skip__", reference_time=None, key_nulls: dict = None) -> list:
    """Every check that applies to source `name`. `load_time` is checked when the source's settings say `load_time: true` (pass None for a pull that has none); `key_nulls` when given."""
    cfg = settings(config, name)
    out = [check_rows(name, config, int(rows), bases)]
    if cfg.get("load_time"):
        out.append(check_load_time(name, config, None if load_time == "__skip__" else load_time, reference_time))
    if key_nulls is not None:
        out.append(check_keys(name, key_nulls))
    return out


def failed(findings: list) -> list:
    return [f for f in findings if not f["passed"]]


def describe(findings: list) -> str:
    """One line per failed finding: source, check and values, for the log and the exception message."""
    return "; ".join(f"{f['source']} {f['check']}: {f['detail']}" for f in failed(findings))


# ----------------------------------------------------------------------------------------------- the stored base (the last good pull of each source)
def base_path(root: str, config: dict) -> str:
    return os.path.join(root, *config["source_guard"]["state_file"].split("/"))


def read_base(root: str, config: dict) -> dict:
    """{source: {"rows": n, "recorded_at": ..., "by": ...}}; {} when the file is missing or unreadable (the callers then use their fallbacks, or fail closed)."""
    try:
        with open(base_path(root, config), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def stored_rows(stored: dict, name: str):
    try:
        return int(stored[name]["rows"])
    except (KeyError, TypeError, ValueError):
        return None


def write_base(root: str, config: dict, rows_by_source: dict, by: str) -> None:
    """Records the row counts of pulls that PASSED (never call it for a failed pull). Atomic; a failure to write is raised (a base that cannot be stored must be seen)."""
    path = base_path(root, config)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = read_base(root, config)
    stamp = datetime.now().isoformat(timespec="seconds")
    for name, n in rows_by_source.items():
        data[name] = {"rows": int(n), "recorded_at": stamp, "by": by}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------------------------- reading what a pull wrote (used by the monthly runner's step 1)
def frame_stats(df: pd.DataFrame, key_cols=(), load_col: str = None) -> dict:
    """{"rows", "key_nulls", "load_time"} of a pulled frame: null or blank counts of the key columns and the earliest value of the load-time column (None when there is none)."""
    key_nulls = {}
    for col in key_cols:
        if col in df.columns:
            s = df[col]
            key_nulls[col] = int(s.isna().sum() + (s.dropna().astype(str).str.strip() == "").sum())
    load = None
    if load_col and load_col in df.columns and len(df):
        ts = pd.to_datetime(df[load_col], errors="coerce").dropna()
        load = str(ts.min()) if len(ts) else None
    return {"rows": int(len(df)), "key_nulls": key_nulls, "load_time": load}
