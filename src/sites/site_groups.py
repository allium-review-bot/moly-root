"""Extract the mysekai site-group table: which sites each group holds.

``mysekaiSiteGroups`` is a pure membership table — rows of (groupId,
siteId), nothing else.  The environment-site talk gate reads it as a
mapping: a talk row names a ``mysekaiSiteGroupId``, and the gate asks
whether the site the player stands in is a member of that group.  The
product keeps the rows in master-table order as an array of groups, each
carrying its site ids in table order; a membership the table does not
state is never invented, and a table with no rows is an error rather than
an empty product — both states a consumer must be told, not left to infer.
"""
from core.jsonio import write_json
from core.master import Master


SITE_GROUPS_TABLE = "mysekaiSiteGroups"


def extract_site_groups(master_source, out_path, master_cache=None):
    """Write site-groups.json: the site-group membership the gates read.

    *master_source* is a directory of master tables or a base URL to fetch
    them from; no bundle is read — this table lives entirely in master.
    """
    master = Master(master_source, cache_dir=master_cache)
    rows = master.table(SITE_GROUPS_TABLE)
    if not rows:
        raise ValueError(f"{SITE_GROUPS_TABLE}: table is empty; a membership "
                         "table with no rows cannot be told apart from a "
                         "table that was never read")
    order, members = [], {}
    for row in rows:
        group_id = row.get("groupId")
        site_id = row.get("mysekaiSiteId")
        if group_id is None or site_id is None:
            raise ValueError(
                f"{SITE_GROUPS_TABLE} row {row.get('id')}: incomplete "
                f"membership row: groupId={group_id}, "
                f"mysekaiSiteId={site_id}")
        if group_id not in members:
            members[group_id] = []
            order.append(group_id)
        members[group_id].append(site_id)
    groups = [{"siteGroupId": group_id, "sites": members[group_id]}
              for group_id in order]
    doc = {
        "version": 1,
        "semantics": {
            "groups": (
                "one entry per siteGroupId, in master-table order, sites in "
                "table order; the source carries nothing but membership, so "
                "the list implies no order or weight among a group's sites"
            ),
        },
        "groups": groups,
        "summary": {
            "rows": len(rows),
            "groups": len(groups),
            "siteIds": len({site for group in groups
                            for site in group["sites"]}),
        },
    }
    write_json(out_path, doc)
    return doc["summary"]
