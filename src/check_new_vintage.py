"""Manual check after the first real monthly run (Prompt 63): compares the totals of the NEW forward-test vintage with the previous one on the months both forecast, per division and for the company,
and flags any that moved by more than the threshold (default 30 percent). It replaces step 10's backtest gate for 2026-11-05, which is "not tested" because no earlier real run is recognised as a success
(STATUS.md, Prompt 60c, rehearsal item 4).

Read only: it opens the forward-test log (default output/summary/forward_test_log_all_divisions.csv) and writes nothing. Item-level rows only (the Category and Type rows repeat the same quantities).
Units are the log's forecast_qty units; the company total adds every division's units together, so read the division lines first.

    python src/check_new_vintage.py                       # latest vintage against the one before it, threshold 30
    python src/check_new_vintage.py --new 3 --old 2 --threshold 30

Exit code 0: nothing flagged. 1: at least one division (or the company) moved by more than the threshold, or has no old total to compare with. 2: the log or a vintage is missing, or the two vintages
share no month.
"""
import argparse
import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOG = os.path.join(PROJECT_ROOT, "output", "summary", "forward_test_log_all_divisions.csv")
DEFAULT_THRESHOLD = 30.0


class VintageCheckError(Exception):
    """The log or a vintage cannot be compared (exit code 2)."""


def compare(log: pd.DataFrame, new: int = None, old: int = None, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """{"new", "old", "months", "rows": [{"division", "old_total", "new_total", "change_pct", "flag"}], "flagged": [...]} for the overlapping months of two vintages."""
    items = log[log["level"] == "Item"]
    ids = sorted(int(v) for v in items["vintage_id"].unique())
    if not ids:
        raise VintageCheckError("the forward-test log has no Item rows")
    new = int(new) if new is not None else ids[-1]
    old = int(old) if old is not None else new - 1
    for v in (new, old):
        if v not in ids:
            raise VintageCheckError(f"vintage {v} is not in the log (vintages present: {ids})")
    a, b = items[items["vintage_id"] == old], items[items["vintage_id"] == new]
    months = sorted(set(a["target_month"]) & set(b["target_month"]))
    if not months:
        raise VintageCheckError(f"vintages {old} and {new} share no target month")
    a, b = a[a["target_month"].isin(months)], b[b["target_month"].isin(months)]
    old_tot, new_tot = a.groupby("division")["forecast_qty"].sum(), b.groupby("division")["forecast_qty"].sum()
    rows = []
    for division in sorted(set(old_tot.index) | set(new_tot.index)) + ["COMPANY"]:
        o = float(old_tot.sum()) if division == "COMPANY" else float(old_tot.get(division, 0.0))
        n = float(new_tot.sum()) if division == "COMPANY" else float(new_tot.get(division, 0.0))
        change = 100.0 * (n - o) / o if o else None
        rows.append({"division": division, "old_total": o, "new_total": n, "change_pct": change, "flag": change is None or abs(change) > threshold})
    return {"new": new, "old": old, "months": months, "threshold": threshold, "rows": rows, "flagged": [r["division"] for r in rows if r["flag"]]}


def render(result: dict) -> str:
    lines = [f"Vintage {result['new']} against vintage {result['old']}, {len(result['months'])} overlapping months ({result['months'][0]} to {result['months'][-1]}), Item rows, forecast_qty units, flag above {result['threshold']:g}%",
             f"{'division':<10}{'old total':>16}{'new total':>16}{'change %':>12}  flag"]
    for r in result["rows"]:
        change = "no old total" if r["change_pct"] is None else f"{r['change_pct']:+.1f}"
        lines.append(f"{r['division']:<10}{r['old_total']:>16,.1f}{r['new_total']:>16,.1f}{change:>12}  {'FLAG' if r['flag'] else 'ok'}")
    lines.append("RESULT: " + ("flagged: " + ", ".join(result["flagged"]) + " (a person decides whether the new vintage stays; nothing was changed by this check)" if result["flagged"] else "nothing flagged"))
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Compare the newest forward-test vintage with the one before it (read only).")
    p.add_argument("--log", default=DEFAULT_LOG)
    p.add_argument("--new", type=int, default=None)
    p.add_argument("--old", type=int, default=None)
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = p.parse_args(argv)
    try:
        if not os.path.exists(args.log):
            raise VintageCheckError(f"the forward-test log does not exist: {args.log}")
        result = compare(pd.read_csv(args.log), args.new, args.old, args.threshold)
    except VintageCheckError as e:
        print(f"CANNOT COMPARE: {e}")
        return 2
    print(render(result))
    return 1 if result["flagged"] else 0


if __name__ == "__main__":
    sys.exit(main())
