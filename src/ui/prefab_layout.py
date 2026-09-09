"""UI prefab layout: the RectTransform truth of the screens and dialogs the
game builds from the APK player data.

Where the layout lives is not a guess.  Screen layers are fetched with
``Resources.Load("Screen/Prefabs/" + layerData.name)`` and dialogs with
``Resources.Load("Dialog/" + dialogType.ToString())``, so the whole hierarchy
of every screen and dialog -- anchors, anchored positions, sizes, pivots,
scales, sprite references, static text -- is serialized in the player data's
``resources.assets`` and in no downloadable bundle.  The per-screen download
packages (``mysekai/ui/*`` and neighbours) carry textures, atlases and effect
prefabs instead; the census in this module reports them as the second source
so a consumer knows which half of a screen comes from where.

MonoBehaviours in the player data ship without typetrees, so every game
component is hand-decoded along the declaration order the managed types fix
(the rule ``ui.talk`` established; the decoders live there and three more are
added here for the components these screens actually use).  A hand decode is
only trusted when it consumes its object exactly -- a nonzero residual fails
the extraction rather than writing a half-truth.

Server-decided values (stamina, rank, jewel balance, weather schedules, reward
contents) are **not** in a prefab: the serialized text and image slots they
fill are placeholders.  Each document names them under ``runtimeValues`` so a
consumer can tell layout truth (real data) from runtime state (a named mock,
per the scope rule), instead of mistaking the placeholder for content.
"""
from __future__ import annotations

import struct
import warnings
from pathlib import Path

import UnityPy

warnings.filterwarnings("ignore")

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f3"

from core.jsonio import write_json
import ui.talk as talk

# ---------------------------------------------------------------------------
# Which prefabs this extractor exports, by screen family.
# ---------------------------------------------------------------------------

# The families the order names.  The settings family holds two prefabs: the
# info screen (quality and the other-options page, rank page) and OptionDialog
# -- the volume screen, whose LiveVolume/SystemVolume sliders are the audio
# settings the owner named.  The menu family carries the menu dialog with the
# shared button bases its dialogs derive from, and the fill cover DialogBase
# instantiates as its first sibling; the HUD family is the site-switch,
# weather and resource-bar layer.
SCREENS = {
    "info": ("ScreenLayerMysekaiInfo", "OptionDialog"),
    "menu": ("MysekaiMenuDialog", "MysekaiGetResourceSubWindowDialog",
             "SubWindowDialog", "Common1ButtonDialog", "Common2ButtonDialog",
             "UIPartsDialogFillCover"),
    "hud": ("ScreenLayerMysekaiHUD", "ScreenLayerMysekaiSiteMove",
            "MysekaiWeatherDialog"),
}

# How each family is fetched at runtime; stated per name because it is the
# reason the layout is in the player data and not in a bundle.
LOADING = {
    "info": 'Resources.Load("Screen/Prefabs/ScreenLayerMysekaiInfo")',
    "menu": 'Resources.Load("Dialog/" + dialogType.ToString())',
    "hud": 'Resources.Load("Screen/Prefabs/…") / "Dialog/…" per name',
}

SEMANTICS = {
    "rect": ("RectTransform is engine-typed and read from its typetree; "
             "anchoredPosition is relative to the anchor point, y up"),
    "sprites": ("an Image's sprite is resolved to its name, its atlas (the "
                "sprite's own m_AtlasTags entry, or the atlas the AtlasImage "
                "points at), and its texture with native size"),
    "text": ("CustomTextMesh is TMPro: content, font asset name, font size "
             "and alignment come from the hand-decoded TMP field chain"),
    "residual": ("every hand-decoded component must consume its bytes exactly; "
                 "one leftover byte fails the prefab instead of half-decoding"),
    "runtimeValues": ("server-decided slots are named here; the serialized "
                      "text and images they hold are placeholders, and the "
                      "values themselves are a named mock per the scope rule"),
}

# Server-decided values each family's placeholders stand for.  The field names
# are the ones the dialog census reads off the runtime code; they name the
# mock a consumer of this layout pairs with the placeholder slot.  The volume
# sliders are neither server state nor static content: their values are the
# player's own local settings (ApplicationLocalSettings persists them on
# device), so the layout ships the sliders and their serialized defaults and
# the product reads/writes them as local state.
RUNTIME_VALUES = {
    "info": ["UserMysekaiGamedata (rank / refreshedAt, per the rank page)",
             "volume slider values (local ApplicationLocalSettings, not "
             "server state: LiveVolume / SystemVolume persist on device)"],
    "menu": ["stamina value (MysekaiStaminaView)",
             "mysekai rank gauge (UIPartsMysekaiRankGauge)",
             "jewel balance (menu cells)",
             "UserResource (MysekaiGetResourceSubWindowDialog contents)"],
    "hud": ["UserMysekaiPhenomenaSchedules (weather cells)",
            "UserResource (HUD resource bar)",
            "stamina value (HUD MysekaiStaminaView)"],
}


# ---------------------------------------------------------------------------
# The three decoders these screens need beyond ui.talk's registry.
# Declaration order fixed by the managed types; a decode must end exactly.
# ---------------------------------------------------------------------------

def decode_raw_image_base(r: talk.Reader) -> dict:
    """UnityEngine.UI.RawImage : MaskableGraphic.

    Serialized fields in declaration order: m_Texture(PPtr) + m_UVRect(Rect,
    four floats).  Sekai.UI.CustomRawImage adds none of its own (the managed
    declaration holds only a ctor), so this chain is its whole tail.
    """
    d = {}
    d.update(talk.decode_graphic_base(r))
    d.update(talk.decode_maskable_graphic_base(r))
    d["m_Texture"] = r.pptr()
    d["m_UVRect"] = r.vec4()
    return d


def decode_unity_toggle(r: talk.Reader) -> dict:
    """UnityEngine.UI.Toggle : Selectable.

    Declaration order: toggleTransition(enum) + graphic(PPtr) + m_Group(PPtr)
    + onValueChanged(ToggleEvent, a UnityEvent) + m_IsOn(bool).
    """
    d = talk.decode_selectable_base(r)
    d["toggleTransition"] = r.i32()
    d["graphic"] = r.pptr()
    d["m_Group"] = r.pptr()
    d["onValueChanged"] = talk.decode_unity_event(r)
    d["m_IsOn"] = r.bool4()
    return d


def decode_custom_toggle(r: talk.Reader) -> dict:
    """Sekai.UI.CustomToggle : Toggle, then its own [SerializeField] chain.

    se(enum) + interval(enum) + disableActionType(enum) + coverImage(PPtr)
    + optionalCoverImages(List<Graphic>) + interaction(PPtr)
    + _captionText(PPtr).  onPointerClickAction and the readonly Lazy are not
    serialized and stay off the chain.
    """
    d = decode_unity_toggle(r)
    d["se"] = r.i32()
    d["interval"] = r.i32()
    d["disableActionType"] = r.i32()
    d["coverImage"] = r.pptr()
    d["optionalCoverImages"] = talk.decode_pptr_list(r)
    d["interaction"] = r.pptr()
    d["_captionText"] = r.pptr()
    return d


def decode_menu_dialog_cell(r: talk.Reader) -> dict:
    """Sekai.MenuDialogCell : MonoBehaviour -- badge(PPtr) + button(PPtr).

    menuSetting and the transition Action are not [SerializeField].
    """
    d = {}
    d["badge"] = r.pptr()
    d["button"] = r.pptr()
    return d


EXTRA_DECODERS = {
    "Sekai.UI.CustomRawImage": decode_raw_image_base,
    "Sekai.UI.CustomToggle": decode_custom_toggle,
    "Sekai.MenuDialogCell": decode_menu_dialog_cell,
}


# ---------------------------------------------------------------------------
# Asset resolution: sprite / atlas / texture / font names for the references
# the decoded components carry.
# ---------------------------------------------------------------------------

def scriptable_object_name(raw: bytes) -> str:
    """The m_Name of a ScriptableObject such as TMP_FontAsset.

    The serialized header is m_GameObject(PPtr) + m_Enabled(bool) +
    m_Script(PPtr) -- 28 bytes -- and m_Name follows as a length-prefixed
    string.  Verified on both font assets the target screens reference.
    """
    if len(raw) < 32:
        return ""
    length = struct.unpack_from("<i", raw, 28)[0]
    if not 0 < length < 128 or 32 + length > len(raw):
        return ""
    return raw[32:32 + length].decode("utf-8", "replace")


class Resolver:
    """Names for the PPtr targets a layout document references.

    Everything a screen prefab points at lives in the same ``resources.assets``
    (sprites, sprite atlases, textures, font assets), so one object table and
    per-type typetree reads cover it.  An unresolvable reference is reported
    as such -- ``{"unresolved": …}`` -- and never as a guessed name.
    """

    def __init__(self, objects: dict, mono_index: dict):
        self.objects = objects
        self.mono_index = mono_index
        self._sprite_cache = {}
        self._texture_cache = {}
        self._atlas_cache = {}
        self._font_cache = {}

    def _tree(self, pid: int):
        obj = self.objects.get(pid)
        if obj is None:
            return None
        try:
            return obj.read_typetree()
        except Exception:
            return None

    def sprite(self, pp: tuple) -> dict:
        key = tuple(pp)
        if key in self._sprite_cache:
            return self._sprite_cache[key]
        fid, pid = pp
        entry = {"fileId": fid, "pathId": pid}
        if not pid:
            entry["state"] = "none"
        elif fid != 0:
            entry["state"] = "external"
        else:
            tree = self._tree(pid)
            obj = self.objects.get(pid)
            if tree is None or obj is None or obj.type.name != "Sprite":
                entry["state"] = "unresolved"
            else:
                entry.update(state="ok", name=tree.get("m_Name", ""),
                             atlas=(tree.get("m_AtlasTags") or [""])[0])
                tex_pid = ((tree.get("m_RD") or {}).get("texture")
                           or {}).get("m_PathID", 0)
                entry["texture"] = self.texture_name(tex_pid)
        self._sprite_cache[key] = entry
        return entry

    def texture_name(self, pid: int) -> dict:
        if pid in self._texture_cache:
            return self._texture_cache[pid]
        tree = self._tree(pid)
        obj = self.objects.get(pid)
        if tree is None or obj is None or obj.type.name != "Texture2D":
            entry = {"pathId": pid, "state": "unresolved"}
        else:
            entry = {"pathId": pid, "state": "ok", "name": tree.get("m_Name", ""),
                     "size": [tree.get("m_Width", 0), tree.get("m_Height", 0)]}
        self._texture_cache[pid] = entry
        return entry

    def atlas_name(self, pp: tuple) -> dict:
        key = tuple(pp)
        if key in self._atlas_cache:
            return self._atlas_cache[key]
        fid, pid = pp
        entry = {"fileId": fid, "pathId": pid}
        if not pid:
            entry["state"] = "none"
        elif fid != 0:
            entry["state"] = "external"
        else:
            tree = self._tree(pid)
            obj = self.objects.get(pid)
            if tree is None or obj is None or obj.type.name != "SpriteAtlas":
                entry["state"] = "unresolved"
            else:
                entry.update(state="ok", name=tree.get("m_Name", ""))
        self._atlas_cache[key] = entry
        return entry

    def font(self, pp: tuple) -> dict:
        key = tuple(pp)
        if key in self._font_cache:
            return self._font_cache[key]
        fid, pid = pp
        entry = {"fileId": fid, "pathId": pid}
        if not pid:
            entry["state"] = "none"
        elif fid != 0:
            entry["state"] = "external"
        else:
            obj = self.objects.get(pid)
            if obj is None or obj.type.name != "MonoBehaviour":
                entry["state"] = "unresolved"
            else:
                name = scriptable_object_name(obj.get_raw_data())
                entry.update(state="ok" if name else "unnamed", name=name)
        self._font_cache[key] = entry
        return entry


# ---------------------------------------------------------------------------
# Layout extraction
# ---------------------------------------------------------------------------

def _pptr(value):
    """A decoded PPtr tuple as JSON-able [fileId, pathId]."""
    return [value[0], value[1]] if isinstance(value, tuple) else value


def _component_record(env, obj, resolver):
    """One component as a document record, with its references resolved.

    ``talk._DECODERS`` carries the combined registry (``EXTRA_DECODERS`` is
    merged into it by :func:`extract_layout`), which is what
    ``talk.decode_object`` consults.
    """
    record = talk.decode_object(env, obj, resolver.mono_index)
    cls = record["class"]
    if (record["type"] == "MonoBehaviour" and record.get("hand_decoded")
            and record["residual"] != 0):
        # decode_object itself never raises on residual; a nonzero residual on
        # a hand decode means the chain was wrong.  Fail the prefab, loudly.
        raise ValueError(f"{cls} left {record['residual']} bytes undecoded")
    out = {
        "class": cls,
        "type": record["type"],
        "handDecoded": record.get("hand_decoded", False),
        "partial": (record["type"] == "MonoBehaviour"
                    and not record.get("hand_decoded")),
    }
    fields = record.get("fields") or {}
    if out["partial"]:
        out["state"] = "no decoder (partial; raw length kept)"
        out["rawLength"] = record.get("raw_len")
        return out
    out["fields"] = fields

    # Reference resolution per component family.
    if cls in ("Sekai.UI.CustomImage", "Sekai.AtlasImage", "UnityEngine.UI.Image"):
        sprite = fields.get("m_Sprite")
        if sprite and sprite[1]:
            out["sprite"] = resolver.sprite(sprite)
        if fields.get("atlas") and fields["atlas"][1]:
            ref = resolver.atlas_name(fields["atlas"])
            ref["spriteName"] = fields.get("spriteName", "")
            out["atlasImage"] = ref
    if cls in ("Sekai.UI.CustomRawImage", "UnityEngine.UI.RawImage"):
        texture = fields.get("m_Texture")
        if texture and texture[1]:
            out["texture"] = resolver.texture_name(texture[1])
    if cls in ("Sekai.UI.CustomTextMesh", "TMPro.TextMeshProUGUI"):
        font = fields.get("m_fontAsset")
        if font and font[1]:
            out["font"] = resolver.font(font)
    return out


def _fields_plain(fields):
    """PPtr tuples as lists so the document is plain JSON types."""
    return {key: ([v[0], v[1]] if isinstance(v, tuple) else
                  [ _fields_plain(item) if isinstance(item, dict) else
                    ([p[0], p[1]] if isinstance(p, tuple) else p)
                    for p in v ] if isinstance(v, list) else v)
            for key, v in fields.items()}


def extract_prefab(env, objects, root_go_pid, root_transform_pid, resolver,
                   prefab_name, family):
    """Walk one prefab's RectTransform tree and build its layout document."""
    tt_cache = {}

    def tt(pid):
        if pid not in tt_cache:
            tt_cache[pid] = objects[pid].read_typetree()
        return tt_cache[pid]

    nodes = []

    def walk(transform_pid, path):
        frame = tt(transform_pid)
        go_pid = frame["m_GameObject"]["m_PathID"]
        name = tt(go_pid).get("m_Name", "")
        here = f"{path}/{name}" if path else name
        components = []
        for entry in tt(go_pid)["m_Component"]:
            cpid = entry["component"]["m_PathID"]
            obj = objects.get(cpid)
            if obj is None or obj.type.name == "RectTransform":
                continue
            components.append(_component_record(env, obj, resolver))
        nodes.append({
            "path": here,
            "name": name,
            "rect": {
                "anchorsMin": [round(frame["m_AnchorMin"]["x"], 4),
                               round(frame["m_AnchorMin"]["y"], 4)],
                "anchorsMax": [round(frame["m_AnchorMax"]["x"], 4),
                               round(frame["m_AnchorMax"]["y"], 4)],
                "anchoredPosition": [round(frame["m_AnchoredPosition"]["x"], 4),
                                     round(frame["m_AnchoredPosition"]["y"], 4)],
                "sizeDelta": [round(frame["m_SizeDelta"]["x"], 4),
                              round(frame["m_SizeDelta"]["y"], 4)],
                "pivot": [round(frame["m_Pivot"]["x"], 4),
                          round(frame["m_Pivot"]["y"], 4)],
                "localScale": [round(frame["m_LocalScale"][k], 4)
                               for k in ("x", "y", "z")],
                "localRotation": [round(frame["m_LocalRotation"][k], 4)
                                  for k in ("x", "y", "z", "w")],
            },
            "components": components,
        })
        for kid in frame["m_Children"]:
            kpid = kid["m_PathID"]
            if kpid in objects:
                walk(kpid, here)

    walk(root_transform_pid, "")

    component_counts, partial_classes = {}, []
    sprites, texts = 0, 0
    for node in nodes:
        for comp in node["components"]:
            component_counts[comp["class"]] = component_counts.get(comp["class"], 0) + 1
            if comp.get("partial"):
                partial_classes.append(f"{node['path']} :: {comp['class']}")
            if "sprite" in comp or "atlasImage" in comp:
                sprites += 1
            if comp["class"] in ("Sekai.UI.CustomTextMesh",
                                 "TMPro.TextMeshProUGUI"):
                texts += 1
    document = {
        "version": 1,
        "prefab": prefab_name,
        "family": family,
        "source": {
            "serializedFile": "resources.assets",
            "rootGameObjectPathId": root_go_pid,
            "rootTransformPathId": root_transform_pid,
            "loading": LOADING[family],
        },
        "semantics": SEMANTICS,
        "runtimeValues": {
            "note": ("the serialized text and image slots these name are "
                     "placeholders; the values are server state and enter the "
                     "product as a named mock, never as these bytes"),
            "named": RUNTIME_VALUES[family],
        },
        "nodes": nodes,
        "summary": {
            "nodes": len(nodes),
            "components": component_counts,
            "spriteReferences": sprites,
            "textComponents": texts,
            "partialComponents": partial_classes,
        },
    }
    return document


def find_prefab_root(objects, name: str):
    """The prefab root for *name*: a RectTransform with no father whose
    GameObject carries exactly this name.

    Player-data resources hold one prefab per screen/dialog name; a same-named
    GameObject under another root is a nested instance (MysekaiMenuDialog has
    one), which the father check keeps out.
    """
    roots = []
    for pid, obj in objects.items():
        if obj.type.name != "RectTransform":
            continue
        try:
            frame = obj.read_typetree()
        except Exception:
            continue
        if frame["m_Father"]["m_PathID"]:
            continue
        go_pid = frame["m_GameObject"]["m_PathID"]
        go = objects.get(go_pid)
        if go is None or go.type.name != "GameObject":
            continue
        if go.read_typetree().get("m_Name") == name:
            roots.append((go_pid, pid))
    return roots


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------

# Download-package families that dress the screens the player data builds.
# A package under these prefixes is opened and counted, never silently
# dropped; a name matching nothing here lands in "unclassified" instead.
BUNDLE_PREFIXES = (
    "mysekai__ui__",
    "mysekai__ui_anim__",
    "mysekai__site__sitemap__",
    "mysekai__effect__ui_anim__",
)

# Player-data name families: the Resources.Load path each is fetched by.
# Dialog prefabs are named after their DialogType member (Mysekai*Dialog,
# Common1ButtonDialog), so that family matches on a suffix; screen layers and
# UI parts match on their prefixes.
PD_NAME_FAMILIES = (
    ("screenLayer", ("ScreenLayer",), None),
    ("dialog", None, "Dialog"),
    ("uiParts", ("UIParts",), None),
)


def census_player_data(objects) -> dict:
    """Count prefab-name families in the player data's resources.assets.

    GameObjects are bucketed by name prefix; the families are the
    Resources.Load roots the runtime reads (Screen/Prefabs/, Dialog/, UI/).
    Counts are of distinct names, with per-family totals.
    """
    names = {}
    for obj in objects.values():
        if obj.type.name != "GameObject":
            continue
        try:
            name = obj.read_typetree().get("m_Name", "")
        except Exception:
            continue
        names[name] = names.get(name, 0) + 1
    families = {}
    for family, prefixes, suffix in PD_NAME_FAMILIES:
        def _match(n, prefixes=prefixes, suffix=suffix):
            if prefixes and any(n.startswith(p) for p in prefixes):
                return True
            return bool(suffix) and n.endswith(suffix) and len(n) > len(suffix)
        matched = {n: c for n, c in names.items() if _match(n)}
        mysekai = {n: c for n, c in matched.items() if "Mysekai" in n}
        families[family] = {
            "distinctNames": len(matched),
            "gameObjects": sum(matched.values()),
            "mysekaiNames": len(mysekai),
            "names": sorted(matched),
        }
    return {"gameObjects": len(names), "distinctNames": len(names),
            "families": families}


def census_bundles(bundles_root, bundle_manifest=None) -> dict:
    """What the per-screen download packages contain.

    *bundles_root* is the decrypted package directory.  *bundle_manifest*,
    when given, is the game's own bundle manifest (AssetBundleInfoNew.json):
    it supplies the isBuiltin split (built-in packages ship in the APK player
    data, not on the download path) and the declared file sizes.
    """
    root = Path(bundles_root)
    if not root.is_dir():
        return {"error": f"bundles root not found: {bundles_root}"}

    manifest = {}
    if bundle_manifest:
        mpath = Path(bundle_manifest)
        if not mpath.is_file():
            return {"error": f"bundle manifest not found: {bundle_manifest}"}
        import json
        data = json.loads(mpath.read_text(encoding="utf-8"))
        entries = data.get("bundles", data) if isinstance(data, dict) else {}
        for name, row in entries.items():
            manifest[str(name).replace("/", "__")] = row

    packages = []
    for path in sorted(root.iterdir()):
        name = path.name
        if not any(name.startswith(p) for p in BUNDLE_PREFIXES):
            continue
        from collections import Counter
        row = {"package": name, "declared": name in manifest}
        if name in manifest:
            entry = manifest[name]
            row["isBuiltin"] = bool(entry.get("isBuiltin"))
            row["fileSize"] = entry.get("fileSize")
        try:
            env = UnityPy.load(str(path))
            kinds = Counter()
            for obj in env.objects:
                kinds[obj.type.name] += 1
            row["objects"] = sum(kinds.values())
            row["kinds"] = dict(sorted(kinds.items()))
            row["state"] = "ok"
        except Exception as exc:  # noqa: BLE001 - a census reports, never guesses
            row["state"] = f"unreadable: {type(exc).__name__}"
        packages.append(row)

    classified = {p["package"]: p for p in packages}
    missing = sorted(name for name in manifest
                     if any(name.startswith(p) for p in BUNDLE_PREFIXES)
                     and name not in classified)
    return {
        "packages": packages,
        "packageCount": len(packages),
        "declaredButNotOnDisk": missing,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract_layout(player_data: str, out_dir, bundles_root=None,
                   bundle_manifest=None) -> dict:
    """Write one layout document per target prefab plus the census.

    Returns the counts the caller reports.  Every hand decode that does not
    end exactly raises, so a document on disk means its whole tree decoded.
    """
    if not player_data:
        raise ValueError("player data path is required (the layout lives in "
                         "the APK player data, in no download bundle)")
    pd = Path(player_data)
    if not pd.is_file():
        raise FileNotFoundError(f"player data not found: {player_data}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    env = UnityPy.load(str(pd))
    objects = talk.objects_by_file(env, "resources.assets")
    if not objects:
        raise ValueError("resources.assets not found in the player data")
    mono_index = talk.build_monoscript_index(env)

    talk._DECODERS.update(EXTRA_DECODERS)
    resolver = Resolver(objects, mono_index)

    written, failures = [], []
    for family, prefabs in SCREENS.items():
        for prefab in prefabs:
            roots = find_prefab_root(objects, prefab)
            if len(roots) != 1:
                failures.append({"prefab": prefab, "family": family,
                                 "reason": f"{len(roots)} candidate roots"})
                continue
            go_pid, transform_pid = roots[0]
            document = extract_prefab(env, objects, go_pid, transform_pid,
                                      resolver, prefab, family)
            path = write_json(out / family / f"{prefab}.json", document)
            written.append({"prefab": prefab, "family": family,
                            "path": str(path),
                            "summary": document["summary"]})

    census = {"playerData": census_player_data(objects)}
    if bundles_root:
        census["bundles"] = census_bundles(bundles_root, bundle_manifest)
    census["targets"] = [{"prefab": w["prefab"], "family": w["family"]}
                         for w in written]
    census_path = write_json(out / "census.json", census)

    return {"written": written, "failures": failures,
            "census": census, "censusPath": str(census_path)}
