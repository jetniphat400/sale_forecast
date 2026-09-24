"""channel_scope (METRICS.md Sec.21) -- which revenue_type value(s) a query selects on.

Q23 (PROJECT_GRAPH.md) asks whether the Omni Channel-only scope explains observed stock/delivery
behaviour, or whether production/stock shared with Tendering must be included. Omni Channel
remains the project's DEFAULT AND OFFICIAL SCOPE regardless of what Q23 finds -- omni_tendering
exists only as a contingency scope for the specific comparisons METRICS.md Sec.21 defines (the
same-target accuracy comparison and the combined-demand calibration re-run), never as a silent
replacement for the project's revenue_type filter.
"""
_TENDERING = "Tendering"


def revenue_types_for_scope(config: dict) -> list:
    """Returns the list of revenue_type values a query should filter on, per config['channel_scope']
    ('omni', the default, or 'omni_tendering'). config['revenue_type'] ('Omni Channel') is always
    included -- omni_tendering adds 'Tendering' to it, it never replaces it."""
    scope = config.get("channel_scope", "omni")
    omni_value = config["revenue_type"]
    if scope == "omni":
        return [omni_value]
    if scope == "omni_tendering":
        return [omni_value, _TENDERING]
    raise ValueError(
        f"Unknown channel_scope {scope!r} in config.yaml -- expected 'omni' or 'omni_tendering' "
        f"(METRICS.md Sec.21)."
    )


def revenue_type_sql_clause(config: dict) -> str:
    """Builds the SQL fragment for the revenue_type filter. Default ('omni') produces
    `revenue_type = 'Omni Channel'`, byte-for-byte identical to this project's query text before
    channel_scope existed. 'omni_tendering' produces `revenue_type IN ('Omni Channel','Tendering')`."""
    values = revenue_types_for_scope(config)
    if len(values) == 1:
        return f"revenue_type = '{values[0]}'"
    value_list = "','".join(values)
    return f"revenue_type IN ('{value_list}')"
