"""Synthetic contracts for the site-group membership product."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sites.site_groups import extract_site_groups


def _write(directory, rows):
    (directory / "mysekaiSiteGroups.json").write_text(
        json.dumps(rows), encoding="utf-8", newline="\n")


def test_groups_keep_master_table_order(tmp_path):
    _write(tmp_path, [
        {"id": 1, "groupId": 1, "mysekaiSiteId": 1},
        {"id": 2, "groupId": 2, "mysekaiSiteId": 2},
        {"id": 3, "groupId": 2, "mysekaiSiteId": 3},
        {"id": 4, "groupId": 2, "mysekaiSiteId": 4},
        {"id": 5, "groupId": 3, "mysekaiSiteId": 5},
        {"id": 9, "groupId": 4, "mysekaiSiteId": 1},
    ])
    out = tmp_path / "site-groups.json"
    summary = extract_site_groups(str(tmp_path), out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert doc["groups"] == [
        {"siteGroupId": 1, "sites": [1]},
        {"siteGroupId": 2, "sites": [2, 3, 4]},
        {"siteGroupId": 3, "sites": [5]},
        {"siteGroupId": 4, "sites": [1]},
    ]
    assert summary == {"rows": 6, "groups": 4, "siteIds": 5}


def test_the_same_site_in_two_groups_is_two_memberships(tmp_path):
    # 组 4 装下全部四站是源数据自己说的:同一站 id 在两组各记一次,
    # 求成员资格按组查,合并去重会把第四组的门开错。
    _write(tmp_path, [
        {"id": 1, "groupId": 1, "mysekaiSiteId": 1},
        {"id": 2, "groupId": 4, "mysekaiSiteId": 1},
    ])
    out = tmp_path / "site-groups.json"
    summary = extract_site_groups(str(tmp_path), out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["groups"] == [
        {"siteGroupId": 1, "sites": [1]},
        {"siteGroupId": 4, "sites": [1]},
    ]
    assert summary["rows"] == 2 and summary["groups"] == 2


def test_an_empty_table_is_an_error_not_an_empty_product(tmp_path):
    _write(tmp_path, [])
    with pytest.raises(ValueError, match="mysekaiSiteGroups"):
        extract_site_groups(str(tmp_path), tmp_path / "site-groups.json")


def test_an_incomplete_membership_row_names_itself(tmp_path):
    _write(tmp_path, [{"id": 7, "groupId": 2, "mysekaiSiteId": None}])
    with pytest.raises(ValueError, match="row 7"):
        extract_site_groups(str(tmp_path), tmp_path / "site-groups.json")
