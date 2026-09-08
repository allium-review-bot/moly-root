"""Extract the ClientConfig deliverable panel from the master table.

``clientConfigs`` is the server-delivered configuration the game reads through
four typed dictionaries (``ClientConfig.FloatConfigs`` and its Int/String/Bool
siblings, keyed by integer id).  The master table carries the same rows in a
stringly form — one ``{id, type, value}`` row per key — so the product panel
is a straight re-typing: each row lands in the dictionary its type names,
with ``value`` parsed into that type.  Nothing is selected or filtered: the
panel is the payload, and a key the table states is never dropped.

A consumer that needs a key the panel does not carry must fail loudly, so the
extraction refuses every shape that would silently shrink the panel: an empty
table, a row with an unknown type, a duplicate id (two rows claiming one key),
and a value that does not parse as its own type are all errors.
"""
from core.jsonio import write_json
from core.master import Master


CLIENT_CONFIGS_TABLE = "clientConfigs"

# Row type -> the dictionary the game reads it through (the nested ClientConfig
# classes name their getter by table, so the panel keeps those names).
TYPE_TABLES = {
    "Float": "FloatConfigs",
    "Int": "IntConfigs",
    "String": "StringConfigs",
    "Bool": "BoolConfigs",
}


def _typed_value(row):
    """The row's value parsed as its own type; raises on any mismatch."""
    kind, value = row.get("type"), row.get("value")
    if not isinstance(value, str):
        raise ValueError(f"{CLIENT_CONFIGS_TABLE} row {row.get('id')}: "
                         f"value is not a string cell: {value!r}")
    if kind == "Float":
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"{CLIENT_CONFIGS_TABLE} row {row.get('id')}: "
                             f"Float value does not parse: {value!r}") from None
    if kind == "Int":
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{CLIENT_CONFIGS_TABLE} row {row.get('id')}: "
                             f"Int value does not parse: {value!r}") from None
    if kind == "String":
        return value
    if kind == "Bool":
        if value not in ("true", "false"):
            raise ValueError(f"{CLIENT_CONFIGS_TABLE} row {row.get('id')}: "
                             f"Bool value is neither true nor false: {value!r}")
        return value == "true"
    raise ValueError(f"{CLIENT_CONFIGS_TABLE} row {row.get('id')}: unknown "
                     f"type {kind!r} (known: {', '.join(sorted(TYPE_TABLES))})")


def extract_client_config(master_source, out_path, master_cache=None):
    """Write client-config.json: the four typed dictionaries, keyed by id.

    *master_source* is a directory of master tables or a base URL to fetch
    them from; no bundle is read — this table lives entirely in master.
    """
    master = Master(master_source, cache_dir=master_cache)
    rows = master.table(CLIENT_CONFIGS_TABLE)
    if not rows:
        raise ValueError(f"{CLIENT_CONFIGS_TABLE}: table is empty; a config "
                         f"table with no rows cannot be told apart from a "
                         f"table that was never read")
    tables = {name: {} for name in TYPE_TABLES.values()}
    for row in rows:
        if not isinstance(row.get("id"), int):
            raise ValueError(f"{CLIENT_CONFIGS_TABLE} row {row.get('id')}: "
                             f"id is not an integer: {row.get('id')!r}")
        if row.get("type") not in TYPE_TABLES:
            raise ValueError(f"{CLIENT_CONFIGS_TABLE} row {row['id']}: unknown "
                             f"type {row.get('type')!r} "
                             f"(known: {', '.join(sorted(TYPE_TABLES))})")
        key = str(row["id"])
        table = TYPE_TABLES[row["type"]]
        if key in tables[table]:
            raise ValueError(f"{CLIENT_CONFIGS_TABLE}: duplicate id "
                             f"{row['id']} in {table}")
        tables[table][key] = _typed_value(row)
    doc = {
        "version": 1,
        "semantics": {
            "tables": (
                "the four dictionaries the game reads ClientConfig through, "
                "each keyed by the integer id the client's table lookups use; "
                "values are verbatim from the master table, typed per row"
            ),
        },
        **tables,
        "summary": {name: len(entries) for name, entries in tables.items()},
    }
    write_json(out_path, doc)
    return doc["summary"]
