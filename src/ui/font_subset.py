"""Build the open UI font subset from shipped text and runtime source text.

Requires fonttools. Retains the previous subset's coverage and font names;
never substitutes a missing character with a different glyph.
"""
import argparse
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont


def string_codepoints(value):
    if isinstance(value, str):
        return set(map(ord, value))
    if isinstance(value, dict):
        return set().union(*(string_codepoints(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(string_codepoints(v) for v in value))
    return set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with TTFont(args.previous) as previous:
        points = set(previous.getBestCmap())
    # Include every exported UI page, even pages not opened during development.
    documents = list((args.data / "ui-layout-v2").rglob("*.json"))
    documents.extend(args.data / name for name in (
        "site/sites.json", "tweets.json", "tweet-tables.json", "talks.json",
        "fixture-talks/out/fixture-talks.json",
    ))
    for path in documents:
        points.update(string_codepoints(json.loads(path.read_text(encoding="utf-8"))))
    # A conservative superset also covers dynamic labels and our settings UI.
    for path in args.source.rglob("*.rs"):
        points.update(map(ord, path.read_text(encoding="utf-8")))
    font = TTFont(args.font)
    supported = set(font.getBestCmap())
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    builder = subset.Subsetter(options=options)
    builder.populate(unicodes=points & supported)
    builder.subset(font)
    font.save(args.out)
    print(f"Wrote {args.out}: {len(points & supported)} codepoints")
    # Controls, comments and asset identifiers are included in the conservative
    # corpus too; report unsupported scalars without hiding them in the renderer.
    print("Unsupported corpus scalars:", " ".join(
        f"U+{point:04X}" for point in sorted(points - supported)
        if not chr(point).isspace()
    ))


if __name__ == "__main__":
    main()
