"""UI sprite atlases of the APK player data: the packed sheets behind buttons
and balloons.

The dialogue UI is not the only thing that lives in the player data rather
than in a downloadable package: the UI sprite atlases do too.  A ``SpriteAtlas``
packs hundreds of named sprites into one ``Texture2D``, and after packing the
sprites themselves carry no usable placement -- a packed sprite's own
``m_RD.texture`` pointer is null and its geometry lives in the atlas's
``m_RenderDataMap`` entry whose index is the sprite's position in
``m_PackedSpriteNamesToIndex``.  That parallel-list mapping is the join this
module implements, checked rather than assumed: the two lists must be the same
length, and for every sprite whose ``Sprite`` object still ships in the same
file the sprite's authored ``m_Rect`` size is compared against the atlas
entry's ``textureRect`` size and the count is reported, not trusted.

What is authored where, exactly:

* the atlas entry carries the packed placement: ``texture``/``alphaTexture``
  pointers, ``textureRect`` (in atlas pixels, origin bottom-left),
  ``atlasRectOffset``, ``uvTransform``, ``settingsRaw``, ``downscaleMultiplier``
  and ``secondaryTextures``.  ``settingsRaw`` packs flags, not a rotation
  count: bit 0 says packed, bit 1 the packing mode (tight or rectangle), bits
  2-5 the rotation -- so a tight-packed sprite is cropped through the sprite's
  own mesh, never through a plain rectangle;
* the ``Sprite`` object carries the authored geometry: ``m_Rect``
  (sprite-local size), ``m_Offset``, ``m_Pivot``, ``m_PixelsToUnits`` and the
  9-slice ``m_Border`` (x=left, y=bottom, z=right, w=top) -- the border is
  authored data the atlas entry does not repeat, so the join by name is what
  makes it reachable.

Cropping is not re-implemented here: the reader's own sprite decoder already
resolves the atlas, applies the packing rotation and, for tight-packed
sprites, masks through the sprite mesh, so a crop is that decoder's output
saved as PNG.  A sprite with no ``Sprite`` object left in the file is left
uncropped with the reason recorded -- without the mesh there is no tight
packing to undo and no border to carry, so a guessed rectangle would bake in
a wrong image.

The caller must supply the player-data path explicitly; there is no default
and no search.  Decoding every atlas texture in the player data would write
hundreds of megabytes nobody asked for, so texture decoding is per-atlas and
cropping per-sprite, both caller-named; the inventory rows are written for
every atlas regardless, so a later one-off crop needs no new discovery pass.
"""
from pathlib import Path

import UnityPy
import warnings

warnings.filterwarnings("ignore")

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f3"

from UnityPy.export import SpriteHelper

from core.jsonio import write_json

# The atlases whose textures are decoded to PNG, and the sprites cropped out
# of any decoded atlas.  Defaults name this module's shipped order's targets;
# they are caller-overridable, not secrets.
DEFAULT_DECODE_ATLASES = ("CommonAtlas", "TalkBalloonAtlas")
DEFAULT_CROP_NAMES = ("btn_r30_wh", "balloon_direction_triangle_wh",
                      "bg_base_r30_wh")
DEFAULT_CROP_PREFIXES = ("balloon_",)


def _plain(value):
    """A typetree value as plain JSON types, byte blobs as their lengths."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    return value


def _sprite_geometry(tree):
    """The authored geometry a Sprite object carries, or None without it."""
    if not tree:
        return None
    return {"pathId": None, "m_Rect": _plain(tree.get("m_Rect")),
            "m_Offset": _plain(tree.get("m_Offset")),
            "m_Border": _plain(tree.get("m_Border")),
            "m_Pivot": _plain(tree.get("m_Pivot")),
            "m_PixelsToUnits": tree.get("m_PixelsToUnits")}


def _same_size(rect_a, rect_b):
    def size(rect):
        return (round(float(rect.get("width", 0.0))),
                round(float(rect.get("height", 0.0))))
    try:
        return size(rect_a) == size(rect_b)
    except (TypeError, ValueError):
        return False


def extract_atlas(player_data, out_dir, decode_atlases=None, crop_names=None,
                  crop_prefixes=None):
    """Read every sprite atlas in *player_data* and write an index.

    *decode_atlases* names the atlases whose textures are decoded to PNG (the
    rest are inventoried from their typetrees alone, dimensions included);
    *crop_names* and *crop_prefixes* name the sprites cropped out of the
    decoded atlases.  Returns the summary counts, and raises on a missing or
    unreadable input rather than writing a silent empty product.
    """
    decode_atlases = DEFAULT_DECODE_ATLASES if decode_atlases is None else decode_atlases
    crop_names = DEFAULT_CROP_NAMES if crop_names is None else crop_names
    crop_prefixes = DEFAULT_CROP_PREFIXES if crop_prefixes is None else crop_prefixes

    path = Path(player_data)
    if not path.is_file():
        raise FileNotFoundError(f"player data not found: {player_data}")
    env = UnityPy.load(str(path))

    # Two keys, not one: path ids repeat across serialized files, so a
    # one-key map would resolve atlas pointers into the wrong file.
    objects = {}
    for obj in env.objects:
        objects.setdefault((obj.assets_file.name, obj.path_id), obj)

    atlases, sprites_by_name = [], {}
    for (file_name, _), obj in sorted(objects.items()):
        if obj.type.name == "SpriteAtlas":
            tree = obj.read_typetree()
            atlases.append((str(tree.get("m_Name", "")) or f"atlas-{abs(obj.path_id):x}",
                            file_name, obj, tree))
        elif obj.type.name == "Sprite":
            tree = obj.read_typetree()
            name = str(tree.get("m_Name", ""))
            sprites_by_name.setdefault(name, []).append((file_name, obj, tree))
    atlases.sort(key=lambda entry: entry[0])

    out = Path(out_dir)
    documents, cropped, size_checks = [], [], []
    for name, file_name, obj, tree in atlases:
        names = [str(value) for value in tree.get("m_PackedSpriteNamesToIndex") or []]
        entries = list(tree.get("m_RenderDataMap") or [])
        document = {"name": name, "file": file_name, "pathId": obj.path_id,
                    "isVariant": bool(tree.get("m_IsVariant", 0)),
                    "textures": [], "sprites": [], "decode": name in decode_atlases,
                    "joinHolds": len(names) == len(entries)}
        if len(names) != len(entries):
            # The parallel-list join is the module's one structural claim; an
            # atlas where it does not hold is carried with that stated, not
            # dropped and not silently mis-joined.
            document["joinReason"] = (f"{len(names)} packed names but "
                                      f"{len(entries)} render-data entries")
            names = names[:len(entries)]
        textures = {}
        rows, atlas_crops = [], 0
        for index, sprite_name in enumerate(names):
            second = (entries[index][1] if len(entries[index]) > 1 else {})
            texture_pptr = second.get("texture") or {}
            texture_pid = texture_pptr.get("m_PathID", 0)
            texture_key = (file_name, texture_pid)
            if texture_pid and texture_key not in textures:
                textures[texture_key] = _texture_row(
                    objects, texture_key, name in decode_atlases, out)
            row = {"name": sprite_name, "index": index,
                   "texturePathId": texture_pid or None,
                   "textureRect": _plain(second.get("textureRect")),
                   "textureRectOffset": _plain(second.get("textureRectOffset")),
                   "atlasRectOffset": _plain(second.get("atlasRectOffset")),
                   "uvTransform": _plain(second.get("uvTransform")),
                   "settingsRaw": second.get("settingsRaw"),
                   "downscaleMultiplier": second.get("downscaleMultiplier"),
                   "alphaTexturePathId": (second.get("alphaTexture") or {}).get(
                       "m_PathID") or None,
                   "sprite": None, "crop": None, "cropReason": None}
            # The Sprite object carries what the atlas entry does not: the
            # authored size, pivot and 9-slice border.  Joined by name within
            # the atlas's own file; duplicates resolve to the lowest path id,
            # and the size comparison below is what would expose a wrong pick.
            local = sorted((m for m in sprites_by_name.get(sprite_name) or []
                            if m[0] == file_name),
                           key=lambda m: m[1].path_id)
            sprite_obj = None
            if local:
                _, sprite_obj, sprite_tree = local[0]
                geometry = _sprite_geometry(sprite_tree)
                geometry["pathId"] = sprite_obj.path_id
                row["sprite"] = geometry
                agree = _same_size(sprite_tree.get("m_Rect") or {},
                                   second.get("textureRect") or {})
                size_checks.append(agree)
            wanted = (sprite_name in crop_names
                      or any(sprite_name.startswith(prefix)
                             for prefix in crop_prefixes))
            if wanted:
                if not document["decode"]:
                    row["cropReason"] = "atlas texture was not decoded"
                elif sprite_obj is None:
                    row["cropReason"] = ("no Sprite object in the player data: "
                                         "without its mesh a packed sprite "
                                         "cannot be cropped")
                else:
                    try:
                        # The reader's own decoder: it resolves the atlas,
                        # undoes the packing rotation and masks tight-packed
                        # sprites through their mesh, none of which this
                        # module re-implements.
                        image = SpriteHelper.get_image_from_sprite(
                            sprite_obj.read())
                        directory = out / "sprites" / name
                        directory.mkdir(parents=True, exist_ok=True)
                        image.save(directory / f"{sprite_name}.png")
                        row["crop"] = f"sprites/{name}/{sprite_name}.png"
                        atlas_crops += 1
                    except Exception as exc:
                        row["cropReason"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
        document["textures"] = list(textures.values())
        document["sprites"] = rows
        document["cropped"] = atlas_crops
        documents.append(document)
        cropped.extend(row["crop"] for row in rows if row["crop"])

    summary = {"atlases": len(documents),
               "decodedAtlases": sum(1 for d in documents if d["decode"]),
               "atlasTextures": sum(len(d["textures"]) for d in documents),
               "decodedTextures": sum(1 for d in documents if d["decode"]
                                      for t in d["textures"] if t["image"]),
               "sprites": sum(len(d["sprites"]) for d in documents),
               "sizeChecks": len(size_checks),
               "sizeAgree": sum(1 for ok in size_checks if ok),
               "croppedSprites": len(cropped)}
    document = {"version": 1, "source": path.name, "atlases": documents,
                "summary": summary}
    write_json(out / "atlas.json", document)
    return summary


def _texture_row(objects, key, decode, out):
    """One atlas texture's row, decoded to PNG when *decode* and readable.

    A texture that is inventoried only (``decode`` false) keeps its dimensions
    from the typetree and no image, which is a caller's choice and not an
    error; a texture that fails to decode carries the reason.
    """
    file_name, path_id = key
    obj = objects.get(key)
    row = {"file": file_name, "pathId": path_id, "name": None,
           "width": None, "height": None, "format": None,
           "image": None, "reason": None}
    if obj is None:
        row["reason"] = "texture object not found in the player data"
        return row
    tree = obj.read_typetree()
    row.update(name=str(tree.get("m_Name", "")) or None,
               width=tree.get("m_Width"), height=tree.get("m_Height"),
               format=tree.get("m_TextureFormat"))
    if not decode:
        return row
    try:
        image = obj.read().image
        if image is None:
            raise ValueError("decoder returned no image")
        stem = f"{row['name'] or 'texture'}-{abs(path_id) % 0xFFFFFFFF:08x}"
        target = out / "textures" / f"{stem}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target)
        row["image"] = f"textures/{stem}.png"
    except Exception as exc:              # unreadable texture format
        row["reason"] = f"{type(exc).__name__}: {exc}"
    return row
