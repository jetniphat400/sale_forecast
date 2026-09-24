"""METRICS.md Sec.22 (robust_minmax) — the two core rules, as small, independently testable
functions: ensemble deduplication and range_ratio. Reusable by any future full-pipeline
integration; used by the analysis in `src/investigations/phase22_modeler*.py` (verified against
this module's logic, not re-derived ad hoc).
"""


def dedup_ensemble_members(raw_members: list) -> list:
    """Deduplicates ensemble members per this task's own rule: two members are identical if
    every parameter matches (r_months, s_months, review_interval_days, lead_time_days) AND their
    usable-stock definitions resolve to the SAME SET of warehouse codes.

    `raw_members` is a list of dicts, each with keys: r_months, s_months, review_interval_days,
    lead_time_days, wh_set (a frozenset or any hashable set-like object of warehouse codes).
    `stockdef` (the definition's name) is NOT part of the identity key -- only the resolved
    warehouse set is, per the task's literal rule ("their usable-stock definitions RESOLVE TO the
    same set of warehouse codes", not "have the same definition name").

    Returns the deduplicated list, keeping the FIRST occurrence of each identity key encountered.
    """
    seen = set()
    out = []
    for m in raw_members:
        key = (m["r_months"], m["s_months"], m["review_interval_days"], m["lead_time_days"],
               frozenset(m["wh_set"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def compute_range_ratio(min_values: list) -> float | None:
    """range_ratio = max_e(Min_e) / min_e(Min_e), over members with Min_e > 0 (METRICS.md Sec.22).
    Items where every Min_e is 0 must be reported separately, not assigned a range_ratio -- this
    function returns None for that case (an empty or all-zero input), never 0 or a fabricated
    value, so a caller cannot silently treat "no ratio" as "ratio zero".
    """
    positive = [v for v in min_values if v > 0]
    if not positive:
        return None
    return max(positive) / min(positive)
