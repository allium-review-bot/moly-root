"""Extract the birthday-party master table the site-map gate reads.

``birthdayParties`` is the server-delivered campaign table: one row per
birthday party session, carrying the window the gate asks about (``startAt``
/ ``closedAt``, epoch milliseconds) plus the delivery-domain ids the
festival site consumes once the gate opens.  The site map's festival-garden
click asks whether any row is *in session* — the client-side predicate is
restored in the game, so the product keeps the rows themselves, verbatim and
in master-table order: a window the table does not state is never invented,
and a table with no rows is an error rather than an empty product — both
states a consumer must be told, not left to infer.

Row fields ride through as given.  Snapshots differ in which optional fields
they carry (older ones lack the harvest-fixture column), so nothing beyond
the three fields the predicate reads is required or dropped.
"""
from core.jsonio import write_json
from core.master import Master


BIRTHDAY_PARTIES_TABLE = "birthdayParties"

# The gate's predicate reads exactly these; a row without them cannot be
# asked "is this party in session", which is the only question this table
# exists to answer.
REQUIRED_FIELDS = ("id", "startAt", "closedAt")


def extract_birthday_parties(master_source, out_path, master_cache=None):
    """Write birthday-parties.json: the party rows the festival gate reads.

    *master_source* is a directory of master tables or a base URL to fetch
    them from; no bundle is read — this table lives entirely in master.
    """
    master = Master(master_source, cache_dir=master_cache)
    rows = master.table(BIRTHDAY_PARTIES_TABLE)
    if not rows:
        raise ValueError(f"{BIRTHDAY_PARTIES_TABLE}: table is empty; a campaign "
                         f"table with no rows cannot be told apart from a "
                         f"table that was never read")
    kept = []
    for row in rows:
        for field in REQUIRED_FIELDS:
            if not isinstance(row.get(field), int):
                raise ValueError(
                    f"{BIRTHDAY_PARTIES_TABLE} row {row.get('id')}: incomplete "
                    f"row: {field}={row.get(field)!r}")
        kept.append(row)
    doc = {
        "version": 1,
        "semantics": {
            "rows": (
                "one entry per party, verbatim in master-table order; the "
                "gate reads startAt/closedAt (epoch ms, closedAt 0 = no end) "
                "and the remaining fields belong to the delivery domain that "
                "runs after the gate opens"
            ),
        },
        "rows": kept,
        "summary": {
            "rows": len(kept),
            "characters": len({row["gameCharacterUnitId"] for row in kept
                               if isinstance(row.get("gameCharacterUnitId"), int)}),
        },
    }
    write_json(out_path, doc)
    return doc["summary"]
