"""Synthetic contracts for the birthday-party campaign product."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sites.birthday_parties import extract_birthday_parties


def _write(directory, rows):
    (directory / "birthdayParties.json").write_text(
        json.dumps(rows), encoding="utf-8", newline="\n")


def test_rows_ride_through_verbatim_in_master_order(tmp_path):
    _write(tmp_path, [
        {"id": 1, "gameCharacterUnitId": 6, "startAt": 1759334400000,
         "birthdayStartAt": 1759593600000, "closedAt": 1759852799000,
         "deliveryItemMaterialId": 179, "assetbundleName": "haruka_2025"},
        {"id": 2, "gameCharacterUnitId": 14, "startAt": 1761235200000,
         "birthdayStartAt": 1761494400000, "closedAt": 0,
         "deliveryItemMaterialId": 180, "assetbundleName": "ichika_2025",
         "mysekaiSiteHarvestFixtureId": 8002},
    ])
    out = tmp_path / "birthday-parties.json"
    summary = extract_birthday_parties(str(tmp_path), out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    # 行逐字段透传:较新快照多出的列(如 mysekaiSiteHarvestFixtureId)照进,
    # 较旧行少列照缺,不发明也不删减——门只读 startAt/closedAt。
    assert doc["rows"][0]["closedAt"] == 1759852799000
    assert doc["rows"][1]["closedAt"] == 0
    assert "mysekaiSiteHarvestFixtureId" in doc["rows"][1]
    assert "mysekaiSiteHarvestFixtureId" not in doc["rows"][0]
    assert [row["id"] for row in doc["rows"]] == [1, 2]
    assert summary == {"rows": 2, "characters": 2}


def test_an_empty_table_is_an_error_not_an_empty_product(tmp_path):
    _write(tmp_path, [])
    with pytest.raises(ValueError, match="birthdayParties"):
        extract_birthday_parties(str(tmp_path), tmp_path / "birthday-parties.json")


@pytest.mark.parametrize("field", ["id", "startAt", "closedAt"])
def test_a_row_missing_the_window_fields_is_an_error(tmp_path, field):
    row = {"id": 1, "startAt": 1759334400000, "closedAt": 0}
    row.pop(field)
    _write(tmp_path, [row])
    with pytest.raises(ValueError, match=field):
        extract_birthday_parties(str(tmp_path), tmp_path / "birthday-parties.json")
