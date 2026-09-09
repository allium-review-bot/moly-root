"""Synthetic contracts for the key-addressed master-table exports."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.master_tables import TABLES, extract_master_tables


def _write(directory, table, rows):
    (directory / f"{table}.json").write_text(
        json.dumps(rows), encoding="utf-8", newline="\n")


def _corpus():
    return {
        "mysekaiBlueprints": [
            {"id": 1, "craftTargetId": 101, "mysekaiCraftType": "fixture"},
            {"id": 2, "craftTargetId": 102, "mysekaiCraftType": "fixture"},
        ],
        "mysekaiItems": [
            {"id": 1, "mysekaiItemType": "material", "seq": 1},
        ],
        "mysekaiMusicRecords": [
            {"id": 1, "externalId": 34, "mysekaiMusicTrackType": "normal"},
        ],
        "wordings": [
            {"wordingKey": "mysekai.craft.title", "value": "x"},
            {"wordingKey": "mysekai.record.title", "value": "y"},
        ],
    }


def _populate(directory, corpus):
    for table, rows in corpus.items():
        _write(directory, table, rows)


def test_every_row_lands_verbatim_under_its_key(tmp_path):
    corpus = _corpus()
    _populate(tmp_path, corpus)
    summary = extract_master_tables(str(tmp_path), str(tmp_path / "out"))
    for table, (key_field, filename) in TABLES.items():
        doc = json.loads(
            (tmp_path / "out" / filename).read_text(encoding="utf-8"))
        assert doc["version"] == 1
        assert doc["semantics"]["table"] == table
        assert doc["semantics"]["keyField"] == key_field
        expected = {str(row[key_field]): row for row in corpus[table]}
        assert doc["entries"] == expected
        assert doc["summary"] == {"rows": len(corpus[table]),
                                  "externalUrlsMasked": 0}
        assert summary[table] == {"rows": len(corpus[table]), "file": filename,
                                  "externalUrlsMasked": 0}


def test_an_empty_table_is_an_error_not_an_empty_product(tmp_path):
    corpus = _corpus()
    corpus["wordings"] = []
    _populate(tmp_path, corpus)
    with pytest.raises(ValueError, match="wordings"):
        extract_master_tables(str(tmp_path), str(tmp_path / "out"))


def test_a_duplicate_key_is_an_error_not_a_silent_overwrite(tmp_path):
    corpus = _corpus()
    corpus["mysekaiItems"] = [
        {"id": 1, "mysekaiItemType": "material", "seq": 1},
        {"id": 1, "mysekaiItemType": "material", "seq": 2},
    ]
    _populate(tmp_path, corpus)
    with pytest.raises(ValueError, match="duplicate key"):
        extract_master_tables(str(tmp_path), str(tmp_path / "out"))


def test_a_row_without_its_key_field_is_an_error(tmp_path):
    corpus = _corpus()
    corpus["mysekaiBlueprints"] = [{"craftTargetId": 101}]
    _populate(tmp_path, corpus)
    with pytest.raises(ValueError, match="key field"):
        extract_master_tables(str(tmp_path), str(tmp_path / "out"))


def test_a_missing_table_is_an_error(tmp_path):
    corpus = _corpus()
    del corpus["mysekaiMusicRecords"]
    _populate(tmp_path, corpus)
    with pytest.raises(LookupError, match="mysekaiMusicRecords"):
        extract_master_tables(str(tmp_path), str(tmp_path / "out"))
