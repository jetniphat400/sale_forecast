"""The revenue_type value a query selects on: config['revenue_type'] ('Omni Channel') only.

The pilot scope is Price List items under the Omni Channel filter. The 'omni_tendering' option
(Omni Channel plus Tendering) and the config key channel_scope were removed on 2026-10-12
(Prompt 27); METRICS.md Sec.21 keeps the history.
"""


def revenue_types_for_scope(config: dict) -> list:
    """The list of revenue_type values a query filters on: [config['revenue_type']]."""
    return [config["revenue_type"]]


def revenue_type_sql_clause(config: dict) -> str:
    """The SQL fragment of the revenue_type filter, `revenue_type = 'Omni Channel'`, byte-for-byte
    the text this project's queries always used."""
    return f"revenue_type = '{config['revenue_type']}'"
