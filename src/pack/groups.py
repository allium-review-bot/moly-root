"""Build dependency-labelled asset groups using the shared content-addressed packer."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

from .build import build, iter_files


ROOT_DOCUMENTS = (
    "manifest.json", "characters.json", "motion-library.glb", "motion-library.index.json",
    "alone-actions.json", "facial-tables.json", "client-config.json", "birthday-parties.json",
    "mysekai-blueprints.json", "mysekai-fixtures.json", "mysekai-items.json",
    "mysekai-music-records.json", "site-groups.json", "talks.json", "tweets.json",
    "tweet-tables.json", "wordings.json",
    "mysekai-tools.json", "mysekai-staminas.json", "mysekai-stamina-recovery.json",
    "mysekai-materials.json", "mysekai-fixture-possessions.json",
    "mysekai-material-possessions.json", "mysekai-system-fixtures.json",
    "mysekai-blueprint-material-costs.json", "mysekai-blueprint-terms.json",
)
ASSET_DIRECTORIES = (
    "avatar", "avatar-parts", "camera", "cutscene-timeline", "emoticons", "fixture-areas",
    "fixture-attach", "fixture-interface", "fixture-meshes", "fixture-models",
    "fixture-particles-v2", "fixture-talks", "fixture-timeline", "perf-animations",
    "phenomena", "site", "ui", "ui-layout-v2",
)
FORMATS = {".json", ".glb", ".gltf", ".png", ".jpg", ".jpeg", ".webp", ".ktx2", ".ogg", ".wav", ".bin"}


def character_files(root: Path):
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    for unit in manifest["units"]:
        for key in ("glb", "rig"):
            if unit.get(key):
                yield unit[key]
        if unit.get("rig"):
            rig_path = root / unit["rig"]
            if not rig_path.resolve().is_relative_to(root.resolve()):
                raise ValueError("character rig must stay inside the asset source")
            rig = json.loads(rig_path.read_text("utf-8"))
            for texture in rig.get("textures", []):
                yield (Path(unit["rig"]).parent / texture).as_posix()
        path = root / unit["glb"]
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("character geometry must stay inside the asset source")
        data = path.read_bytes()
        length = int.from_bytes(data[12:16], "little")
        document = json.loads(data[20:20 + length])
        for row in document.get("images", []) + document.get("buffers", []):
            uri = row.get("uri", "")
            if uri and not uri.startswith("data:"):
                yield (Path(unit["glb"]).parent / uri).as_posix()


def group_of(path: str) -> tuple[str, str]:
    parts = path.split("/")
    top = parts[0]
    if len(parts) == 1:
        character = re.match(r"(?:tex_)?sd_(\d+)(?:[_.])", top)
        if character:
            return f"character/{character[1]}", "character"
        return ("common/motion" if top.startswith("motion-library") else "common/tables"), "common"
    if top in {"avatar", "avatar-parts"}:
        return "character/avatar", "character"
    if top == "site" and len(parts) > 2 and parts[1] in {"scenes", "props"}:
        return f"site/{parts[1]}/{parts[2]}", "site"
    if top == "site" and len(parts) > 3 and parts[1:3] == ["indoor", "modules"]:
        return f"site/room/{parts[3]}", "site"
    if top.startswith("fixture-"):
        package = next((part.split(".")[0] for part in parts[1:] if part.startswith("mysekai__")), None)
        return (f"furniture/{package}", "furniture") if package else ("common/furniture", "common")
    if top == "phenomena" and re.match(r"\d+_", parts[1]):
        return f"weather/{parts[1]}", "weather"
    if top == "phenomena":
        return "common/weather", "common"
    if top in {"ui", "ui-layout-v2"}:
        return "common/ui", "common"
    if top == "emoticons":
        return "common/emoticons", "common"
    return f"common/{top}", "common"


def build_groups(source, output, version):
    source, output = Path(source), Path(output)
    paths = {path for path in ROOT_DOCUMENTS if (source / path).is_file()}
    paths.update(character_files(source))
    for directory in ASSET_DIRECTORIES:
        base = source / directory
        if not base.is_dir() or base.is_symlink() or getattr(base, "is_junction", lambda: False)():
            continue
        paths.update(p.relative_to(source).as_posix() for p in iter_files(base)
                     if p.suffix.lower() in FORMATS and ".pre-" not in p.as_posix())
    grouped = defaultdict(list)
    kinds = {}
    for path in sorted(paths):
        group, kind = group_of(path)
        grouped[group].append(path)
        kinds[group] = kind
    packages = []
    common = {group for group in grouped if kinds[group] == "common"}
    dependency_groups = {
        "character": ["common/tables", "common/motion", "common/emoticons"],
        "furniture": ["common/tables", "common/furniture"],
        "weather": ["common/tables", "common/weather"],
        "site": ["common/tables", "common/site", "common/weather"],
    }
    for group, files in sorted(grouped.items()):
        name = "packages/" + hashlib.sha256(group.encode()).hexdigest()[:24] + ".json"
        report = build(source, output, version, paths=files, manifest_name=name,
                       categories_path=Path(__file__).with_name("groups.toml"))
        packages.append({
            "id": group, "kind": kinds[group], "manifest": name,
            "dependencies": [key for key in dependency_groups.get(kinds[group], []) if key in common],
            "paths": files, "download_bytes": report["download_bytes"],
            "content_bytes": report["content_bytes"],
        })
        print(f"{group}: {len(files)} files, {report['download_bytes']} bytes", flush=True)
    catalog = {"schema": "moly-asset-packs/1", "version": version, "packages": packages}
    output.mkdir(parents=True, exist_ok=True)
    (output / "asset-packs.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    build_groups(args.src, args.out, args.version)


if __name__ == "__main__":
    main()
