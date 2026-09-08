"""Synthetic contracts for the ClientConfig deliverable panel."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.client_config import extract_client_config


def _write(directory, rows):
    (directory / "clientConfigs.json").write_text(
        json.dumps(rows), encoding="utf-8", newline="\n")


def test_rows_land_in_the_dictionary_their_type_names(tmp_path):
    _write(tmp_path, [
        {"id": 65, "type": "Float", "value": "0.003"},
        {"id": 104, "type": "Float", "value": "1.0"},
        {"id": 69, "type": "Int", "value": "16"},
        {"id": 176, "type": "Int", "value": "8"},
        {"id": 98, "type": "String", "value": "prefab/room_default"},
        {"id": 159, "type": "Bool", "value": "true"},
        {"id": 164, "type": "Bool", "value": "false"},
    ])
    out = tmp_path / "client-config.json"
    summary = extract_client_config(str(tmp_path), out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    # 字符串单元按行 type 落型:Float/Int 落数、Bool 落布尔、String 原样。
    assert doc["FloatConfigs"] == {"65": 0.003, "104": 1.0}
    assert doc["IntConfigs"] == {"69": 16, "176": 8}
    assert doc["StringConfigs"] == {"98": "prefab/room_default"}
    assert doc["BoolConfigs"] == {"159": True, "164": False}
    assert summary == {"FloatConfigs": 2, "IntConfigs": 2,
                       "StringConfigs": 1, "BoolConfigs": 2}


def test_an_empty_table_is_an_error_not_an_empty_product(tmp_path):
    _write(tmp_path, [])
    with pytest.raises(ValueError, match="clientConfigs"):
        extract_client_config(str(tmp_path), tmp_path / "client-config.json")


def test_an_unknown_type_is_an_error(tmp_path):
    _write(tmp_path, [{"id": 1, "type": "Decimal", "value": "1"}])
    with pytest.raises(ValueError, match="unknown type"):
        extract_client_config(str(tmp_path), tmp_path / "client-config.json")


def test_a_duplicate_id_within_one_dictionary_is_an_error(tmp_path):
    # 同一张字典里同 id 两行 = 撞键静默覆盖,必须拒;跨表同 id 合法——
    # 游戏按四张字典各自 TryGetValue,id 69(Int)与 id 69(Float)是两个键。
    _write(tmp_path, [
        {"id": 69, "type": "Int", "value": "16"},
        {"id": 69, "type": "Int", "value": "17"},
        {"id": 69, "type": "Float", "value": "16.0"},
    ])
    with pytest.raises(ValueError, match="duplicate id"):
        extract_client_config(str(tmp_path), tmp_path / "client-config.json")


@pytest.mark.parametrize("kind, value", [
    ("Float", "not-a-number"),
    ("Int", "16.0"),
    ("Bool", "True"),
    ("Bool", "1"),
])
def test_a_value_that_does_not_parse_as_its_type_is_an_error(tmp_path, kind, value):
    _write(tmp_path, [{"id": 1, "type": kind, "value": value}])
    with pytest.raises(ValueError):
        extract_client_config(str(tmp_path), tmp_path / "client-config.json")
