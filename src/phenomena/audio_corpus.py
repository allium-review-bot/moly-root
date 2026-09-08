"""The rest of a world's sound: talk voices, furniture effects, music, part voices.

The phenomena job extracts only the sound packages master rows point at — the
site and phenomenon music, and one shared ambience package.  Everything else a
world ships was never requested by any job, which is a gap in the *asking*, not
in the packages: the manifest lists them, the decrypted tree holds them, and the
archives inside decode like any other.  This job asks for the rest, and it asks
the way the consumers do.

Talk voices are the case that must not be done by rote.  A talk names its voice
cues — ``voice_`` followed by the talk's script name and a line/variant pair —
and each cue lives in the package named after the script name, so the consumer
never asks for a package; it plays cues.  This job therefore walks the talk
corpus, maps every voice cue to its package, and decodes exactly the cues the
corpus names — a package may hold several cues the corpus never uses, and those
stay undecoded rather than blind-extracted.  Cues whose package the manifest
does not list are reported by name: that is a data gap upstream, not a decoding
failure, and naming it beats papering over it.

The other three families are extracted whole.  Furniture effects (``se``), the
music packages the master rows do not name (jukebox tracks, tutorial songs,
variants), and the part-voice packages — which the game gates to one character
kind at load time, so a missing package for the other kind is the truth of the
construction, not an extraction gap — all answer to "everything in the family",
not to a cue list.

Output lands in the same ``audio/`` library the phenomena job writes, in the
same per-package shape, and the loop sidecar is merged: packages already on
disk keep their entries, new ones are appended.  The corpus ledger written
alongside accumulates the same way — counts add up across runs, named gaps
merge by name, and a family a run asked nothing about keeps its previous
summary — so a consumer can tell "never asked" from "asked and missing" over
everything on disk, not just the last run.  A talk corpus arrives in either of
the two shapes the repo's talk extractors write, talks grouped under ``units``
or a flat ``talks`` list, and both name voice cues the same way.
"""
import json
from pathlib import Path

from core.jsonio import dumps
from .audio import DECODER, Library, TRANSCODER, archive_bytes

# Package families, in manifest form (slash-separated) and store form (the
# flattened names the decrypted tree uses).
TALK_VOICE = "mysekai/talk/voice/"
PART_VOICE = "mysekai/talk/part_voice/"
SE = "mysekai/sound/se/"
BGM = "mysekai/sound/bgm/"

# A talk voice cue is ``voice_<script name>_<line>_<variant>``; the package is
# named after the script name alone.
CUE_PREFIX = "voice_"

NO_PACKAGE = "no package for this cue's talk script in the manifest"
NO_BUNDLE = "package is not in the decrypted tree"
NO_ARCHIVE = "package holds no audio archive"

# A run walks a thousand-plus packages; the loop sidecar is rewritten every
# so often so a stopped run resumes from what is already on disk.
CHECKPOINT_EVERY = 50

SEMANTICS = {
    "families": ("per family: `requested` packages against the manifest "
                 "(talk voices instead against talks.json), `succeeded` "
                 "decoded ones, `failed` the named remainder with reasons"),
    "talkVoices": ("one entry per package the talk corpus names, carrying the "
                   "cues asked for; only those cues are decoded, so a package "
                   "holding more cues than the corpus names stays partially "
                   "undecoded on purpose"),
    "uncovered": ("cues whose talk script has no package in the manifest: a "
                  "data gap to fix upstream, named rather than swallowed"),
    "partVoiceCues": ("the talk corpus also names part-voice cues; this is "
                      "whether the part-voice packages on disk answer them, "
                      "as a check only — the packages themselves are "
                      "extracted whole, and the unanswered names accumulate "
                      "across runs"),
    "loop": ("the loop sidecar is shared with the phenomena job: existing "
             "entries keep their places, this job's are appended"),
    "corpus": ("the corpus ledger accumulates across runs the way the loop "
               "sidecar does: a family this run asked nothing about keeps its "
               "previous summary, a family it did ask for adds this run's "
               "counts to the previous ones and merges its named entries by "
               "name with this run's reading winning, and the part-voice "
               "check keeps every unanswered name any run has found — the "
               "ledger describes the corpus on disk, not the last run"),
    "inPackage": ("counts taken from the archives' own reports; a stream "
                  "without a `wav` path failed to decode and says why"),
}


def voice_stem(cue):
    """The talk script name a voice cue belongs to: drop ``voice_`` and the
    trailing line/variant pair."""
    body = cue[len(CUE_PREFIX):] if cue.startswith(CUE_PREFIX) else cue
    return body.rsplit("_", 2)[0]


def _corpus_talks(document):
    """Every talk entry of a corpus, whichever of the two shapes the repo's
    talk extractors write: talks grouped under ``units`` by character, or a
    flat ``talks`` list (the fixture corpus)."""
    for unit in (document.get("units") or {}).values():
        yield from unit.get("talks") or []
    yield from document.get("talks") or []


def voice_requests(document):
    """Voice cues of a talk corpus, grouped into package requests.

    Returns ``(requests, cues)``: a mapping from flattened package name to the
    sorted cues asked of it, and the sorted set of cues themselves.
    """
    cues = set()
    for talk in _corpus_talks(document):
        for cue in talk.get("voices") or []:
            if cue.startswith(CUE_PREFIX):
                cues.add(cue)
    requests = {}
    for cue in sorted(cues):
        requests.setdefault(TALK_VOICE + voice_stem(cue), []).append(cue)
    return requests, sorted(cues)


def prefix_packages(names, prefix, flat_prefix, exclude=()):
    """Family members of a manifest, as flattened store names."""
    skipped = {name.replace("/", "__") for name in exclude}
    return sorted(name.replace("/", "__") for name in names
                  if name.startswith(prefix)
                  and name.replace("/", "__") not in skipped)


def _existing_packages(audio_root):
    """Package names the loop sidecar already carries, in file order."""
    path = Path(audio_root) / "loop.json"
    if not path.exists():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    return [entry.get("package") for entry in document.get("packages") or []
            if entry.get("package")]


def _extract_one(store, library, flat, cues, failures):
    """One package into the library; ``False`` when nothing could be read."""
    package = store.package(flat, record_missing=False)
    if package is None:
        failures.append({"package": flat, "reason": NO_BUNDLE})
        return False
    for asset_name, record, path_id in package.contents:
        if record.kinds.get(path_id) != "TextAsset":
            continue
        tree = record.tree(path_id)
        name = str(tree.get("m_Name", "") or asset_name).rsplit(".", 1)[0]
        library.add(flat, name, archive_bytes(tree.get("m_Script")), cues)
        store.forget(flat)
        return True
    failures.append({"package": flat, "reason": NO_ARCHIVE})
    return False


def _family_summary(requested, succeeded, failures, extra=None):
    summary = {"requested": requested, "succeeded": succeeded,
               "failed": failures}
    if extra:
        summary.update(extra)
    return summary


def _merge_loop(audio_root, library):
    """Append this run's packages to the shared loop sidecar, keeping every
    entry already on disk in its place."""
    document = {"status": library.status, "decoder": DECODER,
                "decoderPresent": bool(library.decoder),
                "transcoder": TRANSCODER,
                "transcoderPresent": bool(library.transcoder),
                "packages": library.packages}
    path = Path(audio_root) / "loop.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        known = {entry.get("package") for entry in document["packages"]}
        kept = [entry for entry in existing.get("packages") or []
                if entry.get("package") not in known]
        document["packages"] = kept + document["packages"]
    if document["packages"]:
        path.write_text(dumps(document) + "\n", encoding="utf-8", newline="\n")
        document["file"] = "audio/loop.json"
    return document


# Count fields of a family summary that accumulate across runs.  `requested`
# and `requestedCues` re-count a corpus that is run again; `succeeded` and
# `decodedCues` do not, because a package already on disk is never re-decoded.
COUNTS = ("requested", "succeeded", "requestedCues", "decodedCues")


def _merge_by_name(prior, current, key):
    """Two named-entry lists as one sorted list; this run's reading of a
    name wins."""
    merged = {entry.get(key): entry for entry in prior}
    merged.update({entry.get(key): entry for entry in current})
    return [merged[name] for name in sorted(merged)]


def _family_asked(family):
    """Whether the run asked anything of this family."""
    return bool(family.get("requested") or family.get("requestedCues")
                or family.get("failed") or family.get("missingPackages"))


def _merge_family(prior, current):
    """A family summary as an accumulating account: the count fields add up
    across runs, the named remainders merge by name."""
    merged = dict(current)
    for field in COUNTS:
        if isinstance(prior.get(field), int) and isinstance(current.get(field), int):
            merged[field] = prior[field] + current[field]
    for field, name in (("failed", "package"), ("missingPackages", "package"),
                        ("uncovered", "cue")):
        if field in prior or field in current:
            merged[field] = _merge_by_name(prior.get(field) or [],
                                           current.get(field) or [], name)
    return merged


def _merge_part_voice(prior, current):
    """The part-voice check as an accumulating account: the counts describe
    the latest corpus, the unanswered names accumulate across runs."""
    if not current.get("requested") and not current.get("missing"):
        return dict(prior)          # this corpus names no part-voice cues
    merged = dict(current)
    merged["missing"] = sorted(set(prior.get("missing") or [])
                               | set(current.get("missing") or []))
    return merged


def _merge_corpus(path, document):
    """Fold this run's account into the corpus ledger already on disk.

    A family this run asked nothing about keeps its previous summary; a
    family it did ask for adds this run's counts and merges its named
    entries by name.  The part-voice check keeps every unanswered name any
    run has found.
    """
    prior = json.loads(path.read_text(encoding="utf-8"))
    merged = dict(document)
    families = dict(document["families"])
    for name, family in families.items():
        old = (prior.get("families") or {}).get(name)
        if old is None:
            continue
        families[name] = (old if not _family_asked(family)
                          else _merge_family(old, family))
    merged["families"] = families
    old_parts = prior.get("partVoiceCues")
    if old_parts is not None:
        merged["partVoiceCues"] = _merge_part_voice(old_parts,
                                                    document["partVoiceCues"])
    return merged


def extract_audio_corpus(talks_path, manifest_path, bundle_root, out_dir,
                         decoder=None, transcoder=None, skip_existing=True):
    """Extract the sound families the phenomena job does not ask for.

    *talks_path* names the talk corpus whose voice cues are the talk-voice
    denominator; *manifest_path* names the bundle manifest that is every other
    family's denominator; *bundle_root* is the decrypted tree the packages are
    read from; *out_dir* is the phenomena output directory whose ``audio/``
    receives the products.
    """
    from core.assets.packages import PackageStore

    talks = json.loads(Path(talks_path).read_text(encoding="utf-8"))
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    names = list((manifest.get("bundles") or {}).keys())
    manifest_set = set(names)

    audio_root = Path(out_dir) / "audio"
    audio_root.mkdir(parents=True, exist_ok=True)
    existing = _existing_packages(audio_root) if skip_existing else []
    existing_set = set(existing)

    requests, voice_cues = voice_requests(talks)

    missing = []
    plan = {"talk-voice": [], "se": [], "bgm": [], "part-voice": []}
    for package, cues in sorted(requests.items()):
        flat = package.replace("/", "__")
        if flat in existing_set:
            continue                       # already in the library
        if package not in manifest_set:
            missing.append({"package": flat, "cues": cues,
                            "reason": NO_PACKAGE})
            continue
        plan["talk-voice"].append((flat, cues))
    for prefix, family in ((SE, "se"), (BGM, "bgm"), (PART_VOICE, "part-voice")):
        for flat in prefix_packages(names, prefix, prefix.replace("/", "__"),
                                    exclude=existing):
            plan[family].append((flat, None))

    library = Library(audio_root, "audio", decoder, transcoder)
    store = PackageStore([], bundle_root)
    done = {"talk-voice": 0, "se": 0, "bgm": 0, "part-voice": 0}
    failures = {family: [] for family in done}
    walked = 0
    for family, wanted in plan.items():
        for flat, cues in wanted:
            if _extract_one(store, library, flat, cues, failures[family]):
                done[family] += 1
            walked += 1
            if walked % CHECKPOINT_EVERY == 0:
                # progress so far is durable: a run stopped here resumes
                # without redoing the packages already on disk
                _merge_loop(audio_root, library)

    families = {}
    for family in ("talk-voice", "se", "bgm", "part-voice"):
        families[family] = _family_summary(
            len(plan[family]) + (len(missing) if family == "talk-voice" else 0),
            done[family], failures[family])
    families["talk-voice"]["requestedCues"] = len(voice_cues)
    decoded = {stream.get("cue") for entry in library.packages
               for stream in entry["streams"] if stream.get("wav")}
    families["talk-voice"]["decodedCues"] = len(decoded & set(voice_cues))
    families["talk-voice"]["missingPackages"] = missing
    families["talk-voice"]["uncovered"] = [
        {"cue": cue, "reason": NO_PACKAGE} for cue in voice_cues
        if TALK_VOICE + voice_stem(cue) not in manifest_set]

    loop = _merge_loop(audio_root, library)

    # The corpus also names part-voice cues; whether the packages answer them
    # is a consumer-side check, not part of any denominator.  It reads the
    # merged library, so streams a previous run decoded count as answered.
    part_cues = sorted(
        {cue for talk in _corpus_talks(talks)
         for cue in talk.get("voices") or []
         if cue.startswith("partvoice_")})
    answered = {stream.get("cue") for entry in loop["packages"]
                if entry["package"].startswith(PART_VOICE.replace("/", "__"))
                for stream in entry["streams"] if stream.get("wav")}
    part_voice_cues = {"requested": len(part_cues),
                       "answered": len(answered & set(part_cues)),
                       "missing": [cue for cue in part_cues
                                   if cue not in answered]}

    document = {"version": 1, "semantics": SEMANTICS, "families": families,
                "partVoiceCues": part_voice_cues,
                "loop": {"file": "audio/loop.json",
                         "packages": len(loop["packages"])}}
    path = audio_root / "corpus.json"
    if path.exists():
        document = _merge_corpus(path, document)
    path.write_text(dumps(document) + "\n", encoding="utf-8", newline="\n")
    document["path"] = str(path)
    document["audio"] = loop
    return document
