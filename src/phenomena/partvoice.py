"""Part-voice routing: which variant-voice packages a speaker loads.

A talk's part-voice cues are not addressed by package name; the game loads
the packages by *speaker*.  Every main-chain participant whose home unit is
piapro gets two packages loaded — a scenario-side one and a mysekai-side one,
both named after the character2d row's assetName — and every fixture
character gets its single-parameter mysekai package, with no gate and no
scenario side.  A speaker whose home unit is not piapro gets no package at
all: that is the load-time gate, not a missing row, and the table says so
with a named skip instead of an absent key.

The participants' universe is the roster (characters.json): a character not
placed in a world never speaks, so a character2d row outside the roster has
no consumer and is not routed.  The fixtures' universe is the whole
mysekaiFixtureCharacter2ds table.  The derivation has no free parameters —
same master tables and roster in, same routes out.

Package names are written flattened (a bundle path with each ``/`` doubled to
``__``), the same keys the loop sidecar and the stream table use, so a
consumer can look streams up by them verbatim.
"""
from pathlib import Path

from core.jsonio import dumps

#: The gate reads the character's *home* unit — the gameCharacters row of the
#: identity's gameCharacterId — not the variant unit, so a light_sound
#: variant of a piapro-home character passes.
GATE_UNIT = "piapro"
SKIP_REASON = "unit-type gate: home unit is not piapro"

#: The character2d row type the main chain looks up, and the generation it
#: takes (the table carries two generations of every character).
CHARACTER_TYPE = "game_character"

#: The two package paths of the main chain: each side puts the same asset
#: name under its own prefix, and the fixture chain uses the mysekai asset
#: name without a unit suffix.
SCENARIO_PREFIX = "sound/scenario/voice/"
MYSEKAI_PREFIX = "mysekai/talk/part_voice/"

SEMANTICS = {
    "participants": ("keyed by characterUnitId in roster order; the universe "
                     "is the roster (characters.json), because a character "
                     "not placed in a world never speaks.  A gated row "
                     "carries only `skip` — the game loads no package for it "
                     "— and a routed row carries the character2d identity "
                     "and both package names"),
    "gate": ("the speaker's home unit (the gameCharacters row of the "
             "identity's gameCharacterId) must be piapro; the gate reads the "
             "character's home unit, not the variant unit, so a light_sound "
             "variant of a piapro-home character passes"),
    "packages": ("flattened package names (bundle paths with `/` doubled to "
                 "`__`), the same keys the loop sidecar and the stream table "
                 "use, so a consumer can look streams up verbatim: the "
                 "scenario side is `part_voice_<asset>_<unit>` under "
                 "`sound/scenario/voice/`, the mysekai side "
                 "`mysekai_part_voice_<asset>_<unit>` under "
                 "`mysekai/talk/part_voice/`, and a fixture character's "
                 "package is the mysekai asset name without a unit suffix"),
    "fixtures": ("keyed by mysekaiFixtureId over the whole "
                 "mysekaiFixtureCharacter2ds table; a fixture character has "
                 "no gate and no scenario-side package"),
}


class RouteError(LookupError):
    """A speaker resolves to no character2d row, or a fixture names a
    character2d id the table does not carry: a structural break in the
    inputs, not a skip the game itself makes."""


def flatten(name):
    """The store form of a bundle path, the way the decrypted tree and the
    loop sidecar name packages."""
    return name.replace("/", "__")


def build_partvoice_routes(master, roster):
    """The routing table for *master*'s tables and the *roster* document
    (characters.json, the registry artifact).

    Returns the document as it is written to ``audio/partvoice.json``; the
    caller writes it and reports the counts.
    """
    characters = roster.get("characters") or {}
    if not characters:
        raise RouteError("the roster carries no characters: the participants' "
                         "universe is empty, which is a broken input, not an "
                         "empty world")
    game_characters = master.game_characters()
    rows = master.table("character2ds")
    by_id = {row["id"]: row for row in rows}

    participants = {}
    for unit_id, entry in characters.items():
        identity = entry.get("identity") or {}
        game_character_id = identity.get("gameCharacterId")
        unit = identity.get("unit")
        home = (game_characters.get(game_character_id) or {}).get("unit")
        if home != GATE_UNIT:
            participants[str(unit_id)] = {"skip": SKIP_REASON}
            continue
        # FirstOrDefault over the four-part predicate, in table order: the
        # game takes the first row that matches and never looks further.
        row = next((row for row in rows
                    if row.get("characterType") == CHARACTER_TYPE
                    and row.get("characterId") == game_character_id
                    and row.get("unit") == unit
                    and row.get("isNextGrade")), None)
        if row is None:
            raise RouteError(
                f"participant {unit_id} (gameCharacterId {game_character_id}, "
                f"unit {unit}) passes the gate but no character2d row matches "
                f"the predicate, so no package can be named for it")
        asset = row["assetName"]
        participants[str(unit_id)] = {
            "gameCharacterId": game_character_id,
            "unit": unit,
            "assetName": asset,
            "scenarioPackage": flatten(
                SCENARIO_PREFIX + f"part_voice_{asset}_{unit}"),
            "mysekaiPackage": flatten(
                MYSEKAI_PREFIX + f"mysekai_part_voice_{asset}_{unit}"),
        }

    fixtures = {}
    for row in master.table("mysekaiFixtureCharacter2ds"):
        character2d = by_id.get(row["character2dId"])
        if character2d is None:
            raise RouteError(f"fixture {row['mysekaiFixtureId']} names "
                             f"character2d {row['character2dId']}, which the "
                             f"character2ds table does not carry")
        asset = character2d["assetName"]
        fixtures[str(row["mysekaiFixtureId"])] = {
            "character2dId": row["character2dId"],
            "assetName": asset,
            "mysekaiPackage": flatten(
                MYSEKAI_PREFIX + f"mysekai_part_voice_{asset}"),
        }

    return {"version": 1, "semantics": SEMANTICS,
            "participants": participants, "fixtures": fixtures}


def write_partvoice_routes(document, out_dir):
    """Write the routing table under *out_dir*'s ``audio/``, beside the loop
    sidecar and the corpus ledger, and return the path written."""
    path = Path(out_dir) / "audio" / "partvoice.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(document) + "\n", encoding="utf-8", newline="\n")
    return path


def route_counts(document):
    """The one-line account of a routing table: how many participants route,
    how many are gated, how many fixtures."""
    participants = document["participants"].values()
    return {"participants": len(document["participants"]),
            "routed": sum(1 for row in participants if "skip" not in row),
            "gated": sum(1 for row in participants if "skip" in row),
            "fixtures": len(document["fixtures"])}
