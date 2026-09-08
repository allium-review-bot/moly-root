"""The site-map screen layer: the UI prefab the runtime loads from the APK
player data, not from a downloadable bundle.

The screen-layer loading law (``ScreenLayerData.LoadScreenLayerPrefab``) is
``Resources.Load<GameObject>("Screen/Prefabs/" + layerData.name)``, so the
world-map screen's whole layout -- where the six site icons sit, how big the
map ground is, where the weather button hangs -- lives in the player data's
``resources.assets`` and in no bundle the router can name.  This module opens
that file and writes the layout truth out as one document.

Two of the three values that matter are not plain fields on the root
behaviour; they are serialized object lists whose order *is* the law:

* ``_siteMapIcons`` (List<SiteMapIconBase>) and ``_siteMapIconPositions``
  (List<Transform>) are consumed index-locked: the runtime positions icon *i*
  at position *i* before the icons animate in.  Any join that is not by list
  index scrambles the map.
* The festival-garden icon is repositioned once more, onto
  ``_secretSiteMapIconPosition`` -- which in this prefab *is* the ``Delivery``
  entry of the position list (the same object, serialized twice).

The root behaviour and the icon behaviours ship without typetrees, so their
few consumed fields are hand-decoded along the declaration order the managed
types fix: base-class fields first, then derived.  Every hand parse must land
exactly on the end of its object; a leftover byte means the field chain was
wrong and the read aborts instead of writing a half-truth.
"""
from __future__ import annotations

import struct
from pathlib import Path

import UnityPy
import warnings

warnings.filterwarnings("ignore")

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f3"

SCREEN_LAYER_NAME = "ScreenLayerMysekaiSiteMap"

# siteType enum values (managed MysekaiSiteType), by declaration order.
SITE_TYPES = ("home_site", "first_floor", "second_floor", "third_floor",
              "grassland", "shore", "flower_garden", "memorial_place",
              "festival_garden")

# Icon prefab internals, from the home instance and one outdoor instance
# (the home button ships a different size; the rest are the same tree).
ICON_PREFAB_NODES = ("HomeIconButton", "site_line", "site_shadow",
                     "DefaultWorldNameBase", "NameText", "HereRoot",
                     "WorldMapHere", "UIPartsReleaseSiteBalloon")

# Nodes whose image tint is consumed (a tinted shadow is a visible truth).
# The UGUI Image colour sits at a fixed offset after the material pointer;
# a candidate only counts when all four floats are inside [0, 1].
COLOR_NODES = ("site_shadow", "HomeIconButton", "site_line", "WorldMapHere",
               "bg_background_image", "img_map_shadow",
               "PhenometaBackgroundIcon", "PhenometaIcon", "weatherButton",
               "open_direction_background")

_COLOR_OFFSET = 32 + 12  # behaviour header + m_Material PPtr


def node_color(go_pid, tt, read_raw, components_of, obj_type):
    import struct as _struct
    for cpid in components_of(go_pid):
        if obj_type(cpid) != "MonoBehaviour":
            continue
        raw = read_raw(cpid)
        if len(raw) < _COLOR_OFFSET + 16:
            continue
        r, g, b, a = _struct.unpack_from("<4f", raw, _COLOR_OFFSET)
        if all(0.0 <= value <= 1.0 for value in (r, g, b, a)):
            return [round(r, 4), round(g, 4), round(b, 4), round(a, 4)]
    return None


def collect_colors(root_path, nodes, go_by_path, tt, read_raw,
                   components_of, obj_type):
    colors = {}
    for path, frame in nodes.items():
        if not path.startswith(root_path + "/"):
            continue
        leaf = path.rsplit("/", 1)[-1]
        if leaf not in COLOR_NODES or leaf in colors:
            continue
        go_pid = go_by_path.get(path)
        if go_pid is None:
            continue
        color = node_color(go_pid, tt, read_raw, components_of, obj_type)
        if color is not None:
            colors[path] = color
    return colors

SEMANTICS = {
    "loading": ("the screen layer is built into the APK player data; "
                "Resources.Load(\"Screen/Prefabs/\" + layerData.name) fetches "
                "it, so no bundle name routes to it"),
    "iconPositions": ("`_siteMapIcons[i]` is placed at `_siteMapIconPositions[i]` "
                      "before the in-animation; the pairing is by list index and "
                      "nothing else"),
    "secretSiteIconPosition": ("the festival-garden icon is placed once more onto "
                               "`_secretSiteMapIconPosition`, which here is the "
                               "same transform as one entry of the position list"),
    "mapGround": ("the world-panorama image ships with an empty sprite; the "
                  "runtime LoadSprite() assigns it from the site-map texture "
                  "set, and the assigned texture's native size matches the "
                  "rect below"),
    "anchors": ("anchoredPosition is Unity UI: relative to the anchor point, "
                "y up.  Edge anchors (top / corner) hang off the canvas edge, "
                "not off the map centre"),
    "canvas": ("the screen canvas follows ScreenManager.SetUpScreenResolution: "
               "a 1920x1080 reference, matched on height when the display is "
               "taller than 16:9 and on width when wider"),
}


class ParseError(Exception):
    """A hand parse did not land exactly on the end of its object."""


class Reader:
    """Sequential little-endian reads with an align-everything-endian rule."""

    def __init__(self, raw: bytes):
        self.raw = raw
        self.off = 0

    def _take(self, size: int) -> bytes:
        if self.off + size > len(self.raw):
            raise ParseError(f"read past end at {self.off}+{size} of {len(self.raw)}")
        chunk = self.raw[self.off:self.off + size]
        self.off += size
        return chunk

    def pptr(self):
        file_id, path_id = struct.unpack("<iq", self._take(12))
        return {"fileId": file_id, "pathId": path_id}

    def i32(self):
        return struct.unpack("<i", self._take(4))[0]

    def f32(self):
        return struct.unpack("<f", self._take(4))[0]

    def u8(self):
        return self._take(1)[0]

    def align(self):
        self.off = (self.off + 3) & ~3

    def string(self):
        length = self.i32()
        if length < 0 or self.off + length > len(self.raw):
            raise ParseError(f"string length {length} out of range at {self.off}")
        text = self.raw[self.off:self.off + length].decode("utf-8", "replace")
        self.off += length
        self.align()
        return text

    def boolean(self):
        value = self.u8()
        self.align()
        return value

    def leftover(self) -> int:
        return len(self.raw) - self.off


def parse_screen_layer_fields(raw: bytes) -> dict:
    """The serialized fields of ScreenLayerMysekaiSiteMap, in declaration order.

    Base ScreenLayer contributes ``layerCamera`` and the public ``isBootDone``;
    everything serialized on the derived class is a private [SerializeField].
    The parse is only trusted when it consumes the object exactly.
    """
    r = Reader(raw)
    fields = {
        "gameObject": r.pptr(),
        "enabled": r.boolean(),
        "script": r.pptr(),
        "name": r.string(),
        "layerCamera": r.pptr(),
        "isBootDone": r.boolean(),
    }

    def plist():
        count = r.i32()
        return [r.pptr() for _ in range(count)]

    fields["_siteMapIcons"] = plist()
    fields["_secretSiteMapIconPosition"] = r.pptr()
    fields["_siteMapIconPositions"] = plist()
    for name in ("_siteMapOpenBackgroundImage", "_siteMapPhenomenaView",
                 "_weatherButton", "_siteMapBackgroundImage",
                 "_siteMapBackgroundGradientImage", "_siteMapGroundHighlightImage",
                 "_siteMapRightGradientImage", "_siteMapLeftGradientImage",
                 "_siteMapSphereImage"):
        fields[name] = r.pptr()
    if r.leftover() != 0:
        raise ParseError(f"screen-layer behaviour has {r.leftover()} leftover bytes")
    return fields


def parse_icon_base_fields(raw: bytes) -> dict:
    """The first SiteMapIconBase fields: button, icon image, site type."""
    r = Reader(raw)
    fields = {
        "gameObject": r.pptr(),
        "enabled": r.boolean(),
        "script": r.pptr(),
        "name": r.string(),
        "_mysekaiCustomButton": r.pptr(),
        "_iconImage": r.pptr(),
        "_mysekaiSiteType": r.i32(),
    }
    # Only the prefix is consumed here: the derived SiteMapIcon fields include
    # inline AnimationCurves whose layout is not needed for the layout truth.
    return fields


def extract_screen_layer(player_data: str, out_dir) -> dict:
    """Write the screen-layer layout truth into *out_dir*; return counts."""
    env = UnityPy.load(player_data)
    objects = {}
    for obj in env.objects:
        if obj.assets_file.name == "resources.assets":
            objects[obj.path_id] = obj
    if not objects:
        raise ParseError("resources.assets not found in the player data")

    typetrees: dict[int, dict] = {}
    game_object_names: dict[int, str] = {}

    def tt(pid):
        if pid not in typetrees:
            typetrees[pid] = objects[pid].read_typetree()
        return typetrees[pid]

    def read_raw(pid):
        return objects[pid].get_raw_data()

    def go_name(pid):
        if pid not in game_object_names:
            game_object_names[pid] = tt(pid).get("m_Name", f"go:{pid}")
        return game_object_names[pid]

    def obj_type(pid):
        obj = objects.get(pid)
        return obj.type.name if obj is not None else None

    for pid, obj in objects.items():
        if obj.type.name == "GameObject":
            try:
                game_object_names[pid] = obj.read_typetree().get("m_Name", "")
            except Exception:
                pass

    # -- locate the screen layer root by name (no id is hardcoded) --
    roots = [pid for pid, name in game_object_names.items()
             if name == SCREEN_LAYER_NAME]
    if len(roots) != 1:
        raise ParseError(
            f"expected exactly one {SCREEN_LAYER_NAME} GameObject, found {len(roots)}")
    root_pid = roots[0]

    def components_of(go_pid):
        out = []
        for entry in tt(go_pid)["m_Component"]:
            out.append(entry["component"]["m_PathID"])
        return out

    def component_of_type(go_pid, type_name):
        for cpid in components_of(go_pid):
            if obj_type(cpid) == type_name:
                return cpid
        return None

    root_mb = next(cpid for cpid in components_of(root_pid)
                   if obj_type(cpid) == "MonoBehaviour")
    fields = parse_screen_layer_fields(read_raw(root_mb))

    # -- transform tree over the whole file (rects are engine-typed) --
    transform_of_go: dict[int, int] = {}
    children_of: dict[int, list[int]] = {}
    rect_by_pid: dict[int, dict] = {}
    for pid, obj in objects.items():
        if obj.type.name not in ("Transform", "RectTransform"):
            continue
        value = tt(pid)
        rect_by_pid[pid] = value
        transform_of_go[value["m_GameObject"]["m_PathID"]] = pid
        father = value["m_Father"]["m_PathID"]
        if father:
            children_of.setdefault(father, []).append(pid)

    def rect_of(go_pid):
        tpid = transform_of_go.get(go_pid)
        return None if tpid is None else rect_of_gameobject_frame(rect_by_pid[tpid])

    def walk(go_pid, path, table):
        name = go_name(go_pid)
        child_path = f"{path}/{name}" if path else name
        remember(go_pid, child_path, table)
        for kid_go in (tt(kid)["m_GameObject"]["m_PathID"]
                       for kid in sorted(children_of.get(transform_of_go[go_pid], []),
                                         key=lambda t: t)):
            walk(kid_go, child_path, table)

    def remember(go_pid, path, table):
        table[path] = rect_of(go_pid)
        go_by_path[path] = go_pid

    nodes: dict[str, dict] = {}
    go_by_path: dict[str, int] = {}
    root_transform = tt(transform_of_go[root_pid])
    nodes[SCREEN_LAYER_NAME] = rect_of_gameobject_frame(root_transform)
    go_by_path[SCREEN_LAYER_NAME] = root_pid
    for kid in sorted(children_of.get(transform_of_go[root_pid], [])):
        walk(tt(kid)["m_GameObject"]["m_PathID"], SCREEN_LAYER_NAME, nodes)

    # -- icon list: behaviour per entry, first serialized fields only --
    def child_path_of(go_pid):
        # walk up to the root building the path (roots have no father)
        parts = []
        current = go_pid
        while True:
            tpid = transform_of_go[current]
            father = rect_by_pid[tpid]["m_Father"]["m_PathID"]
            parts.append(go_name(current))
            if not father:
                break
            current = rect_by_pid[father]["m_GameObject"]["m_PathID"]
        return "/".join(reversed(parts))

    icons = []
    for ref in fields["_siteMapIcons"]:
        pid = ref["pathId"]
        icon = parse_icon_base_fields(read_raw(pid))
        site_type = icon["_mysekaiSiteType"]
        if not 0 <= site_type < len(SITE_TYPES):
            raise ParseError(f"icon behaviour {pid} names siteType {site_type}")
        button_pid = icon["_mysekaiCustomButton"]["pathId"]
        button_go = None
        if button_pid in objects and obj_type(button_pid) == "MonoBehaviour":
            # The button behaviour has no typetree either; its first field is
            # the m_GameObject PPtr, which is all the tree walk needs.
            file_id, go_pid = struct.unpack_from("<iq", read_raw(button_pid), 0)
            button_go = go_pid if go_pid in objects else None
        icons.append({
            "node": go_name(icon["gameObject"]["pathId"]),
            "path": child_path_of(icon["gameObject"]["pathId"]),
            "siteType": SITE_TYPES[site_type],
            "siteTypeValue": site_type,
            "behaviourPathId": pid,
            # The runtime only assigns the position; the authored root scale
            # stays effective (it is not reset per site).
            "rootRect": rect_of(icon["gameObject"]["pathId"]),
            "buttonNode": go_name(button_go) if button_go else None,
            "buttonPath": child_path_of(button_go) if button_go else None,
            "buttonRect": rect_of(button_go) if button_go else None,
        })

    positions = []
    for ref in fields["_siteMapIconPositions"]:
        pid = ref["pathId"]
        if obj_type(pid) not in ("Transform", "RectTransform"):
            raise ParseError(f"icon position {pid} is a {obj_type(pid)}")
        go_pid = tt(pid)["m_GameObject"]["m_PathID"]
        positions.append({
            "node": go_name(go_pid),
            "path": child_path_of(go_pid),
            "rect": rect_of(go_pid),
        })

    if len(icons) != len(positions):
        raise ParseError(f"{len(icons)} icons against {len(positions)} positions")
    secret_ref = fields["_secretSiteMapIconPosition"]["pathId"]
    secret_entry = next((entry for entry, ref in zip(positions, fields["_siteMapIconPositions"])
                         if ref["pathId"] == secret_ref), None)

    def named_ref(field):
        pid = fields[field]["pathId"]
        obj = objects.get(pid)
        if obj is None:
            raise ParseError(f"{field} references missing object {pid}")
        if obj.type.name in ("Transform", "RectTransform"):
            go_pid = tt(pid)["m_GameObject"]["m_PathID"]
        else:
            file_id, go_pid = struct.unpack_from("<iq", obj.get_raw_data(), 0)
        if go_pid not in objects:
            raise ParseError(f"{field} references missing GameObject {go_pid}")
        return {"field": field, "node": go_name(go_pid),
                "path": child_path_of(go_pid), "rect": rect_of(go_pid)}

    curated = {
        "mapGround": named_ref("_siteMapSphereImage"),
        "groundHighlight": named_ref("_siteMapGroundHighlightImage"),
        "backgroundImage": named_ref("_siteMapBackgroundImage"),
        "backgroundGradient": named_ref("_siteMapBackgroundGradientImage"),
        "groundRightGradient": named_ref("_siteMapRightGradientImage"),
        "groundLeftGradient": named_ref("_siteMapLeftGradientImage"),
        "openBackground": named_ref("_siteMapOpenBackgroundImage"),
        "phenomenaView": named_ref("_siteMapPhenomenaView"),
        "weatherButtonRoot": named_ref("_weatherButton"),
    }

    # Icon prefab internals, from the home instance and one outdoor instance
    # (the home button ships a different size; the rest are the same tree).
    def icon_prefab_nodes(instance_path, names):
        prefix = instance_path + "/"
        picked = {}
        for path, frame in nodes.items():
            if not path.startswith(prefix):
                continue
            leaf = path.rsplit("/", 1)[-1]
            if leaf in names and leaf not in picked:
                picked[leaf] = frame
        return picked

    home_icon = next(icon for icon in icons if icon["siteType"] == "home_site")
    outdoor_icon = next(icon for icon in icons if icon["siteType"] != "home_site")
    icon_prefab = {
        "home": {"instance": home_icon["path"],
                 "nodes": icon_prefab_nodes(home_icon["path"], ICON_PREFAB_NODES)},
        "outdoor": {"instance": outdoor_icon["path"],
                    "nodes": icon_prefab_nodes(outdoor_icon["path"], ICON_PREFAB_NODES)},
    }
    colors = collect_colors(SCREEN_LAYER_NAME, nodes, go_by_path, tt, read_raw,
                            components_of, obj_type)

    counts = {
        "nodes": len(nodes),
        "icons": len(icons),
        "iconPositions": len(positions),
        "siteTypes": sorted({icon["siteType"] for icon in icons}),
        "prefabNodes": len(icon_prefab["outdoor"]["nodes"]),
        "colors": len(colors),
    }
    document = {
        "version": 1,
        "semantics": SEMANTICS,
        "source": {
            "gameObject": SCREEN_LAYER_NAME,
            "serializedFile": "resources.assets",
            "rootPathId": root_pid,
            "rootBehaviourPathId": root_mb,
            "loading": "Resources.Load(\"Screen/Prefabs/\" + layerData.name)",
        },
        "canvas": {
            "referenceResolution": [1920, 1080],
            "matchLaw": ("ScreenManager.SetUpScreenResolution: 1080/1920 <= H/W "
                         "matches height, else width"),
        },
        "iconPositions": positions,
        "icons": icons,
        "secretSiteIconPosition": (None if secret_entry is None
                                   else {"path": secret_entry["path"],
                                         "node": secret_entry["node"]}),
        "screen": curated,
        "iconPrefab": icon_prefab,
        "colors": colors,
        "nodes": nodes,
        "summary": counts,
    }
    from core.jsonio import write_json
    path = write_json(Path(out_dir) / "screen_layer.json", document)
    return {"counts": counts, "path": str(path)}


def rect_of_gameobject_frame(transform: dict) -> dict:
    """The RectTransform truth of one node, with plain-Transform fallback."""
    is_rect = "m_AnchoredPosition" in transform
    frame = {
        "anchorsMin": _vec2(transform["m_AnchorMin"]) if is_rect else None,
        "anchorsMax": _vec2(transform["m_AnchorMax"]) if is_rect else None,
        "pivot": _vec2(transform["m_Pivot"]) if is_rect else None,
        "anchoredPosition": (_vec2(transform["m_AnchoredPosition"])
                             if is_rect else None),
        "sizeDelta": _vec2(transform["m_SizeDelta"]) if is_rect else None,
        "localScale": _vec3(transform["m_LocalScale"]),
        "localPosition": _vec3(transform["m_LocalPosition"]),
    }
    return frame


def _vec2(value):
    return [round(value["x"], 4), round(value["y"], 4)]


def _vec3(value):
    return [round(value["x"], 4), round(value["y"], 4), round(value["z"], 4)]
