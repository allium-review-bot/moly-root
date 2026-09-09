"""Extract the four mysekai master tables whose rows are looked up by key.

``mysekaiBlueprints``, ``mysekaiItems`` and ``mysekaiMusicRecords`` are each
keyed by an integer ``id``; ``wordings`` is keyed by the string
``wordingKey``.  A consumer asks the table for one entry by that key, so the
product keeps every row under its key rather than as an array a reader would
have to search.  Nothing is selected or filtered: a row the table states is
never dropped, a key column that is absent or duplicated is an error rather
than a silent overwrite, and a table with no rows is an error rather than an
empty product — both states a consumer must be told, not left to infer.

The one exception to "verbatim": string values that are external http(s)
links are replaced by ``<external-url>`` (see :func:`_mask_external_urls`).
"""
from core.jsonio import write_json
from core.master import Master


TABLES = {
    "mysekaiBlueprints": ("id", "mysekai-blueprints.json"),
    "mysekaiItems": ("id", "mysekai-items.json"),
    "mysekaiMusicRecords": ("id", "mysekai-music-records.json"),
    "wordings": ("wordingKey", "wordings.json"),
}

_MASKED_URL = "<external-url>"


def _mask_external_urls(table, rows):
    """Replace external http(s) link values with a placeholder, in place.

    A handful of wording rows carry links to the live game's operational
    web pages (policy notices, galleries).  The product never opens them —
    there is no networking — and the published tree must not name vendor
    endpoints, so the value is masked and the count reported in the summary;
    the key and every other field stay verbatim.
    """
    masked = 0
    for row in rows:
        for field, value in row.items():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                row[field] = _MASKED_URL
                masked += 1
    return masked


def _keyed_rows(table, key_field, rows):
    keyed = {}
    for row in rows:
        key = row.get(key_field)
        if key is None:
            raise ValueError(f"{table} row {row.get('id')}: key field "
                             f"{key_field} is absent or null")
        stored = str(key)
        if stored in keyed:
            raise ValueError(f"{table}: duplicate key {key_field}={key!r}")
        keyed[stored] = row
    return keyed


def extract_master_tables(master_source, out_dir, master_cache=None):
    """Write one keyed document per table in :data:`TABLES` into *out_dir*.

    *master_source* is a directory of master tables or a base URL to fetch
    them from; no bundle is read — these tables live entirely in master.
    """
    master = Master(master_source, cache_dir=master_cache)
    summary = {}
    for table, (key_field, filename) in TABLES.items():
        rows = master.table(table)
        if not rows:
            raise ValueError(f"{table}: table is empty; a table with no rows "
                             f"cannot be told apart from a table that was "
                             f"never read")
        masked = _mask_external_urls(table, rows)
        keyed = _keyed_rows(table, key_field, rows)
        doc = {
            "version": 1,
            "semantics": {
                "table": table,
                "keyField": key_field,
                "entries": (
                    "every row of the table, keyed by the field a consumer "
                    "looks it up by; the source carries no ordering the "
                    "consumer reads, so the map implies none"
                ),
                "externalUrls": (
                    "string values that are external http(s) links are "
                    "replaced by the literal <external-url>; the product has "
                    "no networking and the published tree does not name "
                    "vendor endpoints"
                ) if masked else None,
            },
            "entries": keyed,
            "summary": {"rows": len(rows), "externalUrlsMasked": masked},
        }
        write_json(f"{out_dir}/{filename}", doc)
        summary[table] = {"rows": len(rows), "file": filename,
                          "externalUrlsMasked": masked}
    return summary
