"""Extract the embedded UI cue sheets using the shared audio decoder."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

from phenomena.audio import Library


def extract_ui_audio(apk, out, *, decoder=None, transcoder=None):
    library = Library(Path(out) / "ui" / "audio", "ui/audio", decoder, transcoder)
    with zipfile.ZipFile(apk) as archive:
        for name in ("MenuCommon", "MenuCommon_Built_in"):
            entry = f"assets/{name}.acb"
            data = archive.read(entry)
            package = library.add(name, name, data)
            package["sourceSha256"] = hashlib.sha256(data).hexdigest()
    return library.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--vgmstream")
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    print(json.dumps(extract_ui_audio(args.apk, args.out,
                                     decoder=args.vgmstream, transcoder=args.ffmpeg)))


if __name__ == "__main__":
    main()
