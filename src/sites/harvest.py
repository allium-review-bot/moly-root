"""The harvest-object family of the field path, as one joined index.

The packages under ``mysekai/site/field/object/`` are the objects a harvest
site spawns at runtime -- the trees, stones, plants, treasure boxes and drop
items -- rather than geometry baked into a scene.  The site pack already
extracts every one of them (the census classes the family as ``prop`` and the
geometry lands in ``props/``), so nothing here re-reads a bundle: this module
joins what that extraction produced into the one view a consumer of this
family wants -- per package, its status, its geometry, its materials and
clips, the prefab contract its view behaviour carries, and the master rows
that name it.

Two joins decide the shape, and both directions of each are reported rather
than one being silently dropped:

* **Fixture rows** (``mysekaiSiteHarvestFixtures``) name a package by the leaf
  of the field/object path in their ``assetbundleName``.  A row naming a
  package this run did not extract, and a package no row names, are both
  listed -- the first is a master/disk disagreement, the second is a companion
  package another family member declares as a dependency, and those are
  different facts that a single "unmatched" count would merge.
* **Material rows** (``mysekaiMaterials``) name the model of a *dropped* item
  the same way, through ``modelAssetbundleName``.  The drop models are a
  different population from the fixtures -- a log bundle is not a harvestable
  tree -- so the two joins are kept apart instead of folded into one "named
  by master" flag.

The view behaviour is identified by data, not by a class list: the
discriminator is the serialized field ``mysekaiSiteHarvestFixtureType``,
which every harvest view carries and which nothing else in these packages
does.  A class-name list would route by spelling; the field routes by what
the prefab itself declares, and a future class this extractor has never seen
is picked up by carrying the field rather than landing in a default bucket.
"""
from . import census

# The family's key prefix inside the site path (as the census writes it: the
# site prefix is already stripped, so a package's key is
# ``field__object__<leaf>``).
FAMILY_PREFIX = "field__object__"

# The one serialized field that identifies a harvest view behaviour.  Measured
# over the family: every behaviour carrying it is a view of one harvest object
# type, and no other behaviour in these packages has it.
CONTRACT_FIELD = "mysekaiSiteHarvestFixtureType"

# The contract fields copied into the index verbatim.  They are the prefab's
# own declaration of what it is (interaction radius, object type, collision
# layer, rare flag); the full component tree stays in the package document.
CONTRACT_FIELDS = ("radius", CONTRACT_FIELD, "collisionType", "isRareObject")

# Master tables this family is joined against.  The fixture table is the
# harvestable objects themselves; the material table names the drop-item
# models.  The remaining family tables carry no bundle names -- they are
# spawn-zone rectangles and refresh schedules -- so they are reported by
# presence and row count only, never by a join they cannot answer.
FIXTURE_TABLE = "mysekaiSiteHarvestFixtures"
MATERIAL_TABLE = "mysekaiMaterials"
FAMILY_TABLES = (
    FIXTURE_TABLE,
    MATERIAL_TABLE,
    "mysekaiSiteHarvestUnavailableSpots",
    "birthdayPartyMysekaiSiteHarvestFixtureRepeatRefreshes",
    "mysekaiTutorialMysekaiSiteHarvestFixtureGroups",
)

NO_MASTER = ("no master directory supplied; which rows name a harvest object "
             "is only in caller-supplied master tables, so the fixture and "
             "material joins are reported as missing rather than invented "
             "from the package names")

NO_GEOMETRY = "the package opened but wrote no geometry (particles or data only)"
ZERO_VERTICES = "the package's geometry has zero vertices"

SEMANTICS = {
    "family": ("the packages under the field/object path -- the objects a "
               "harvest site spawns at runtime rather than baking into its "
               "scene.  The site pack extracts them with everything else; "
               "this index is the joined view of that extraction, not a "
               "second one"),
    "status": ("exported = a geometry file with at least one vertex; "
               "no-mesh = the package opened but produced no geometry (or "
               "produced one with zero vertices), and the reason says which; "
               "failed = the package could not be opened at all -- the same "
               "three-way vocabulary the furniture-geometry index uses, so a "
               "consumer reads both families with one rule"),
    "view": ("the behaviour whose serialized fields carry "
             "`mysekaiSiteHarvestFixtureType` is the object's view, and the "
             "four contract fields (radius, fixture type, collision type, "
             "rare flag) are copied verbatim.  A package whose behaviours "
             "carry none of them is a model or effect companion, not a "
             "harvestable object, and is reported without a view rather than "
             "guessed at"),
    "masterJoin": ("a fixture row names its package by the leaf of the "
                   "field/object path (`assetbundleName`); a material row "
                   "names a drop-item model the same way "
                   "(`modelAssetbundleName`).  Both directions of both joins "
                   "are reported: a row naming an unextracted package and a "
                   "package no row names are different facts, listed "
                   "separately"),
}


def is_harvest(document):
    """True when a site-pack document is one of the field/object packages."""
    return (document.get("kind") == "prop"
            and str(document.get("key", "")).startswith(FAMILY_PREFIX))


def _leaf(document):
    """The family leaf of a document's key (the master rows' naming unit)."""
    return str(document["key"])[len(FAMILY_PREFIX):]


def _status(document):
    """``(status, reason)`` for one package, on the furniture index's rule."""
    if "file" not in document:
        # The site pack's failure shape: a package that raised is reported as
        # a stub document with no ``file`` of its own, so its status is
        # failed rather than no-mesh -- an unopenable package is not the same
        # fact as an openable one without geometry.
        return "failed", str((document.get("unsupported") or [{}])[0]
                             .get("reason", "package failed"))
    geometry = document.get("geometry") or {}
    if not geometry.get("file"):
        return "no-mesh", NO_GEOMETRY
    if not geometry.get("vertices"):
        return "no-mesh", ZERO_VERTICES
    return "exported", None


def _view(document):
    """The harvest view's contract fields, or ``None`` with the reason.

    Every behaviour instance whose fields carry :data:`CONTRACT_FIELD` is
    collected; the family measured so far has exactly one per package, but
    the shape holds a list so two instances are two rows rather than one
    silently overwritten.
    """
    views = []
    for class_name, entry in sorted((document.get("components") or {}).items()):
        if not isinstance(entry, dict):
            continue
        for instance in entry.get("instances") or []:
            fields = instance.get("fields") or {}
            if CONTRACT_FIELD not in fields:
                continue
            views.append({"class": class_name,
                          **{field: fields.get(field)
                             for field in CONTRACT_FIELDS}})
    if not views:
        return None, (f"no behaviour carries {CONTRACT_FIELD}, so this "
                      "package is a model or effect companion of the family "
                      "rather than a harvestable object")
    return views, None


def _shaders(document):
    """The shader family names the package's materials draw with."""
    names = set()
    for material in document.get("materials") or []:
        if not isinstance(material, dict):
            continue
        shader = material.get("shader") or {}
        if isinstance(shader, str):
            names.add(shader)
        elif shader.get("name"):
            names.add(str(shader["name"]))
    return sorted(names)


def _master_tables(master, master_cache):
    """The fixture and material rows, and which family tables were absent."""
    from core.master import Master, MissingTable
    source = Master(master, cache_dir=master_cache)
    rows, absent = {}, []
    for table in (FIXTURE_TABLE, MATERIAL_TABLE):
        try:
            rows[table] = source.table(table)
        except MissingTable:
            absent.append(table)
    return rows, absent


def _family_table_report(master, master_cache):
    """Which harvest-family tables this master source holds, with row counts.

    A table nobody reads a bundle name from is still reported by presence:
    ``absent`` says the caller's master snapshot has no such table, which is
    a different fact from the table existing with rows in it.
    """
    from core.master import Master, MissingTable
    source = Master(master, cache_dir=master_cache)
    report = {}
    for table in FAMILY_TABLES:
        try:
            rows = source.table(table)
        except MissingTable:
            report[table] = {"rows": None, "status": "absent"}
            continue
        report[table] = {"rows": len(rows), "status": "present"}
    return report


def _fixture_rows(rows, leaf):
    """Fixture master rows joined onto one package leaf, trimmed to identity."""
    return [{"id": row.get("id"),
             "mysekaiSiteHarvestFixtureType": row.get("mysekaiSiteHarvestFixtureType"),
             "hp": row.get("hp"),
             "lastAttackStamina": row.get("lastAttackStamina"),
             "mysekaiSiteHarvestFixtureRarityType": row.get(
                 "mysekaiSiteHarvestFixtureRarityType")}
            for row in rows if row.get("assetbundleName") == leaf]


def _material_rows(rows, leaf):
    """Material master rows joined onto one package leaf, trimmed to identity."""
    return [{"id": row.get("id"),
             "mysekaiMaterialType": row.get("mysekaiMaterialType"),
             "mysekaiMaterialRarityType": row.get("mysekaiMaterialRarityType")}
            for row in rows if row.get("modelAssetbundleName") == leaf]


def harvest_document(documents, master=None, master_cache=None):
    """The field/object family's index, from the site pack's own documents.

    *documents* are the per-package documents the site pack produced, family
    members selected by :func:`is_harvest`.  With *master*, fixture and
    material rows are joined onto the packages; without it the joins are
    reported as missing with the reason, the same rule the placement table
    follows.  The summary uses the furniture-geometry index's status
    vocabulary (``bundles`` / ``exported`` / ``noMesh`` / ``failed``) so the
    two model families are read with one rule.
    """
    members = [document for document in documents if is_harvest(document)]
    fixture_rows = material_rows = None
    master_section = {"fixtureTable": FIXTURE_TABLE,
                      "materialTable": MATERIAL_TABLE,
                      "missing": None, "absentTables": []}
    if master:
        rows, absent = _master_tables(master, master_cache)
        fixture_rows = rows.get(FIXTURE_TABLE)
        material_rows = rows.get(MATERIAL_TABLE)
        master_section["absentTables"] = sorted(absent)
        master_section["tables"] = _family_table_report(master, master_cache)
    else:
        master_section["missing"] = NO_MASTER

    packages, summary = {}, {"bundles": len(members), "exported": 0,
                             "noMesh": 0, "failed": 0, "noMeshNames": [],
                             "failedNames": [], "prefabRoots": 0,
                             "withView": 0, "withoutView": 0}
    for document in sorted(members, key=lambda d: d["package"]):
        leaf = _leaf(document)
        status, reason = _status(document)
        geometry = document.get("geometry") or {}
        views, view_reason = _view(document)
        entry = {
            "name": document["package"],
            "status": status,
            "document": document.get("file"),
            "glb": (None if not (document.get("file") and geometry.get("file"))
                    else (document["file"].rsplit("/", 1)[0] + "/"
                          + geometry["file"])),
            "reason": reason,
            "prefabRoots": len(document.get("roots") or []),
            "meshes": geometry.get("meshes", 0),
            "uniqueMeshes": geometry.get("uniqueMeshes", 0),
            "vertices": geometry.get("vertices", 0),
            "triangles": geometry.get("triangles", 0),
            "scenes": len(geometry.get("scenes") or []),
            "defaultScene": geometry.get("defaultScene"),
            "materials": len(document.get("materials") or []),
            "shaders": _shaders(document),
            "clips": sorted(str(clip.get("name"))
                            for clip in (document.get("animations") or {})
                            .get("clips") or []),
            "particleEmitters": len(document.get("particles") or []),
            "textures": len(document.get("textures") or []),
            "view": views,
            "viewReason": view_reason,
            "masterRows": (_fixture_rows(fixture_rows, leaf)
                           if fixture_rows is not None else None),
            "materialRows": (_material_rows(material_rows, leaf)
                             if material_rows is not None else None),
        }
        packages[document["package"]] = entry
        summary[{"exported": "exported", "no-mesh": "noMesh",
                 "failed": "failed"}[status]] += 1
        summary["prefabRoots"] += entry["prefabRoots"]
        if status == "no-mesh":
            summary["noMeshNames"].append(document["package"])
        elif status == "failed":
            summary["failedNames"].append(document["package"])
        if views:
            summary["withView"] += 1
        else:
            summary["withoutView"] += 1

    if fixture_rows is not None:
        leaves = {_leaf(document) for document in members}
        unmatched = sorted({str(row.get("assetbundleName")) for row in fixture_rows
                            if row.get("assetbundleName") not in leaves})
        joined = sorted({row.get("assetbundleName") for row in fixture_rows
                         if row.get("assetbundleName") in leaves})
        summary["masterRows"] = len(fixture_rows)
        summary["masterRowsMatched"] = len([row for row in fixture_rows
                                            if row.get("assetbundleName") in leaves])
        summary["masterRowsUnmatched"] = unmatched
        master_section["joinedLeaves"] = joined
    if material_rows is not None:
        leaves = {_leaf(document) for document in members}
        summary["materialRows"] = len([row for row in material_rows
                                       if row.get("modelAssetbundleName")])
        summary["materialRowsMatched"] = len(
            [row for row in material_rows
             if row.get("modelAssetbundleName") in leaves])
        summary["materialRowsUnmatched"] = sorted(
            {str(row.get("modelAssetbundleName")) for row in material_rows
             if row.get("modelAssetbundleName")
             and row.get("modelAssetbundleName") not in leaves})
    if members and fixture_rows is not None:
        named = set()
        if fixture_rows:
            named = {row.get("assetbundleName") for row in fixture_rows}
        if material_rows:
            named |= {row.get("modelAssetbundleName") for row in material_rows}
        summary["packagesWithoutMasterRow"] = sorted(
            document["package"] for document in members
            if _leaf(document) not in named)

    return {"version": 1, "semantics": SEMANTICS, "summary": summary,
            "master": master_section, "packages": packages}
