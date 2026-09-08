"""Synthetic contracts for the partvoice routing table."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.master import Master, MissingTable
from phenomena import partvoice


class _DirMaster(Master):
    """A Master over a directory of synthetic tables, so the derivation is
    exercised against the same reader the CLI uses."""

    def __init__(self, tables):
        import tempfile
        self._dir = tempfile.mkdtemp()
        for name, rows in tables.items():
            with open(os.path.join(self._dir, f"{name}.json"), "w",
                      encoding="utf-8", newline="\n") as handle:
                json.dump(rows, handle)
        super().__init__(self._dir)


# Two home units: 21 is piapro (routes), 1 is not (gated).  The character2d
# table carries two generations and a duplicate next-grade row with the same
# asset name, as the real one does.
TABLES = {
    "gameCharacters": [
        {"id": 1, "unit": "light_sound"},
        {"id": 21, "unit": "piapro"},
    ],
    "character2ds": [
        {"id": 1, "assetName": "01ichika", "characterId": 1,
         "characterType": "game_character", "isNextGrade": False,
         "unit": "light_sound"},
        {"id": 2, "assetName": "21miku", "characterId": 21,
         "characterType": "game_character", "isNextGrade": False,
         "unit": "theme_park"},
        {"id": 3, "assetName": "v2_21miku", "characterId": 21,
         "characterType": "game_character", "isNextGrade": True,
         "unit": "theme_park"},
        {"id": 9, "assetName": "v2_21miku", "characterId": 21,
         "characterType": "game_character", "isNextGrade": True,
         "unit": "theme_park"},
        {"id": 4, "assetName": "v2_21miku", "characterId": 21,
         "characterType": "game_character", "isNextGrade": True,
         "unit": "light_sound"},
        {"id": 5, "assetName": "v2_21miku", "characterId": 21,
         "characterType": "game_character", "isNextGrade": False,
         "unit": "light_sound"},
        # a sub row the fixture chain resolves by id alone
        {"id": 1073, "assetName": "v2_sub_egg_01_mametchi", "characterId": 1,
         "characterType": "sub_game_character", "isNextGrade": True,
         "unit": "none"},
        # a same-unit row of another character type: the predicate requires
        # game_character, so this must not be picked
        {"id": 11, "assetName": "mob_21miku", "characterId": 21,
         "characterType": "mob", "isNextGrade": True,
         "unit": "theme_park"},
    ],
    "mysekaiFixtureCharacter2ds": [
        {"id": 1, "character2dId": 1073, "mysekaiFixtureId": 837},
    ],
}

ROSTER = {"characters": {
    "1": {"identity": {"gameCharacterId": 1, "unit": "light_sound"}},
    "27": {"identity": {"gameCharacterId": 21, "unit": "theme_park"}},
    "28": {"identity": {"gameCharacterId": 21, "unit": "light_sound"}},
}}


def test_gate_rejects_with_a_named_skip_and_keeps_roster_order():
    document = partvoice.build_partvoice_routes(_DirMaster(TABLES), ROSTER)
    assert list(document["participants"]) == ["1", "27", "28"]
    assert document["participants"]["1"] == {"skip":
                                             partvoice.SKIP_REASON}


def test_routed_participant_carries_both_flattened_package_names():
    document = partvoice.build_partvoice_routes(_DirMaster(TABLES), ROSTER)
    assert document["participants"]["27"] == {
        "gameCharacterId": 21,
        "unit": "theme_park",
        "assetName": "v2_21miku",
        "scenarioPackage": "sound__scenario__voice__part_voice_v2_21miku_theme_park",
        "mysekaiPackage": "mysekai__talk__part_voice__mysekai_part_voice_v2_21miku_theme_park",
    }
    assert document["participants"]["28"] == {
        "gameCharacterId": 21,
        "unit": "light_sound",
        "assetName": "v2_21miku",
        "scenarioPackage": "sound__scenario__voice__part_voice_v2_21miku_light_sound",
        "mysekaiPackage": "mysekai__talk__part_voice__mysekai_part_voice_v2_21miku_light_sound",
    }


def test_fixture_routes_single_parameter_package_without_unit():
    document = partvoice.build_partvoice_routes(_DirMaster(TABLES), ROSTER)
    assert document["fixtures"] == {
        "837": {"character2dId": 1073, "assetName": "v2_sub_egg_01_mametchi",
                "mysekaiPackage":
                    "mysekai__talk__part_voice__mysekai_part_voice_v2_sub_egg_01_mametchi"},
    }


def test_a_gated_world_with_no_participants_is_not_an_error():
    roster = {"characters": {
        "1": {"identity": {"gameCharacterId": 1, "unit": "light_sound"}}}}
    document = partvoice.build_partvoice_routes(_DirMaster(TABLES), roster)
    assert partvoice.route_counts(document) == {"participants": 1,
                                                "routed": 0, "gated": 1,
                                                "fixtures": 1}


def test_a_routed_participant_without_a_row_raises():
    roster = {"characters": {
        "29": {"identity": {"gameCharacterId": 21, "unit": "street"}}}}
    with pytest.raises(partvoice.RouteError):
        partvoice.build_partvoice_routes(_DirMaster(TABLES), roster)


def test_an_empty_roster_raises_rather_than_routing_nothing():
    with pytest.raises(partvoice.RouteError):
        partvoice.build_partvoice_routes(_DirMaster(TABLES),
                                         {"characters": {}})


def test_a_missing_master_table_raises():
    tables = {name: rows for name, rows in TABLES.items()
              if name != "character2ds"}
    with pytest.raises(MissingTable):
        partvoice.build_partvoice_routes(_DirMaster(tables), ROSTER)


def test_the_written_document_round_trips(tmp_path):
    document = partvoice.build_partvoice_routes(_DirMaster(TABLES), ROSTER)
    path = partvoice.write_partvoice_routes(document, tmp_path)
    assert path == tmp_path / "audio" / "partvoice.json"
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and "\r" not in text
    assert json.loads(text) == document
