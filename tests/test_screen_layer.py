"""Screen-layer layout extraction: the hand-parsed field chains must consume
their objects exactly, order the icon/position pairing by serialized list
index, and refuse a truncated or overlong read instead of writing half a
truth.

The fixtures are synthetic bytes in the layout the managed declarations fix:
MonoBehaviour header (GameObject PPtr, enabled, script PPtr, name), then the
declared fields in order.  A real player-data file is not in the repository.
"""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sites.screen_layer import (ParseError, SITE_TYPES,
                                parse_icon_base_fields,
                                parse_screen_layer_fields,
                                rect_of_gameobject_frame)


def _header(raw, name=""):
    raw += struct.pack("<iq", 0, 73717)          # m_GameObject
    raw += struct.pack("<B", 1)                   # m_Enabled
    raw += b"\x00\x00\x00"                        # (alignment of bool)
    raw += struct.pack("<iq", 1, 4384)           # m_Script
    raw += struct.pack("<i", len(name)) + name.encode()  # m_Name
    while len(raw) % 4:
        raw += b"\x00"
    return raw


def _pptr(raw, file_id, path_id):
    return raw + struct.pack("<iq", file_id, path_id)


def _string(raw, text):
    raw += struct.pack("<i", len(text)) + text.encode()
    while len(raw) % 4:
        raw += b"\x00"
    return raw


def _screen_layer_raw(icon_pids, secret_pid, position_pids, ref_pids):
    raw = _header(b"")
    raw = _pptr(raw, 0, 0)          # layerCamera
    raw += struct.pack("<B", 0) + b"\x00\x00\x00"   # isBootDone
    raw += struct.pack("<i", len(icon_pids))
    for pid in icon_pids:
        raw = _pptr(raw, 0, pid)
    raw = _pptr(raw, 0, secret_pid)
    raw += struct.pack("<i", len(position_pids))
    for pid in position_pids:
        raw = _pptr(raw, 0, pid)
    for pid in ref_pids:
        raw = _pptr(raw, 0, pid)
    return raw


def test_screen_layer_fields_round_trip():
    raw = _screen_layer_raw([11, 12, 13], 22, [21, 22, 23, 24, 25, 26],
                            list(range(31, 40)))
    fields = parse_screen_layer_fields(raw)
    assert fields["gameObject"] == {"fileId": 0, "pathId": 73717}
    assert [ref["pathId"] for ref in fields["_siteMapIcons"]] == [11, 12, 13]
    assert fields["_secretSiteMapIconPosition"]["pathId"] == 22
    assert [ref["pathId"] for ref in fields["_siteMapIconPositions"]] == \
        [21, 22, 23, 24, 25, 26]
    assert fields["_siteMapSphereImage"]["pathId"] == 39
    # every curated screen reference lands on the tail refs in order
    names = ["_siteMapOpenBackgroundImage", "_siteMapPhenomenaView",
             "_weatherButton", "_siteMapBackgroundImage",
             "_siteMapBackgroundGradientImage", "_siteMapGroundHighlightImage",
             "_siteMapRightGradientImage", "_siteMapLeftGradientImage",
             "_siteMapSphereImage"]
    assert [fields[name]["pathId"] for name in names] == list(range(31, 40))


def test_screen_layer_fields_reject_bad_length():
    raw = _screen_layer_raw([11], 22, [21], [31])
    with pytest.raises(ParseError):
        parse_screen_layer_fields(raw[:-4])
    with pytest.raises(ParseError):
        parse_screen_layer_fields(raw + b"\x00\x00\x00\x00")


def test_icon_base_fields_and_site_type():
    raw = _header(b"")
    raw = _pptr(raw, 0, 101)     # _mysekaiCustomButton
    raw = _pptr(raw, 0, 102)     # _iconImage
    raw += struct.pack("<i", SITE_TYPES.index("grassland"))
    fields = parse_icon_base_fields(raw)
    assert fields["_mysekaiCustomButton"]["pathId"] == 101
    assert fields["_iconImage"]["pathId"] == 102
    assert SITE_TYPES[fields["_mysekaiSiteType"]] == "grassland"
    assert fields["gameObject"]["pathId"] == 73717


def test_icon_base_fields_reject_truncation():
    raw = _header(b"") + struct.pack("<iq", 0, 101)
    with pytest.raises(ParseError):
        parse_icon_base_fields(raw)


def test_rect_frame_reads_rect_transform():
    frame = rect_of_gameobject_frame({
        "m_AnchorMin": {"x": 0.5, "y": 1.0},
        "m_AnchorMax": {"x": 0.5, "y": 1.0},
        "m_Pivot": {"x": 0.5, "y": 0.5},
        "m_AnchoredPosition": {"x": 144.0, "y": -24.0},
        "m_SizeDelta": {"x": 242.0, "y": 96.0},
        "m_LocalScale": {"x": 1.0, "y": 1.0, "z": 1.0},
        "m_LocalPosition": {"x": 0.0, "y": 0.0, "z": 0.0},
    })
    assert frame["anchorsMin"] == [0.5, 1.0]
    assert frame["anchoredPosition"] == [144.0, -24.0]
    assert frame["sizeDelta"] == [242.0, 96.0]
    # plain Transforms carry no anchor family: the fields stay deliberately
    # None instead of being invented as zeros
    plain = rect_of_gameobject_frame({
        "m_LocalScale": {"x": 5.0, "y": 5.0, "z": 1.0},
        "m_LocalPosition": {"x": 796.0, "y": -399.6, "z": 0.0},
    })
    assert plain["anchorsMin"] is None
    assert plain["anchoredPosition"] is None
    assert plain["localScale"] == [5.0, 5.0, 1.0]
