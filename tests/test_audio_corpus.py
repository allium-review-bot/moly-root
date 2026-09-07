"""Synthetic contracts for the mysekai sound corpus extraction."""
import json
import os
import stat
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from phenomena import audio_corpus


TALKS = {
    "units": {
        "21": {"talks": [
            {"lua": "mysekai_talk_alpha_001", "voices": [
                "voice_mysekai_talk_alpha_001_01_001",
                "voice_mysekai_talk_alpha_001_02_001",
                "partvoice_01_021_idol",
            ]},
            {"lua": "mysekai_talk_alpha_002", "voices": []},
        ]},
        "22": {"talks": [
            {"lua": "mysekai_talk_beta_001", "voices": [
                "voice_mysekai_talk_beta_001_01_001",
                "partvoice_01_021_band",
            ]},
            # A deeper script name: the mapping keeps everything but the
            # trailing line/variant pair.
            {"lua": "mysekai_talk_gamma_001_02", "voices": [
                "voice_mysekai_talk_gamma_001_02_03_001",
            ]},
        ]},
    },
}

MANIFEST = {
    "bundles": {
        name: {} for name in [
            "mysekai/talk/voice/mysekai_talk_alpha_001",
            "mysekai/talk/voice/mysekai_talk_beta_001",
            "mysekai/talk/voice/mysekai_talk_gamma_001_02",
            "mysekai/sound/se/se_mysekai",
            "mysekai/sound/se/fixture/basketball",
            "mysekai/sound/bgm/bgm_mysekai_beach",
            "mysekai/sound/bgm/music0001",
            "mysekai/talk/part_voice/mysekai_part_voice_v2_21miku_idol",
        ]
    },
}

# The archive each package holds, as its decoder-visible stream names; one
# stream can answer several cue names (the container allows it).
STREAM_NAMES = {
    "mysekai__talk__voice__mysekai_talk_alpha_001":
        "voice_mysekai_talk_alpha_001_01_001;"
        "voice_mysekai_talk_alpha_001_02_001",
    "mysekai__talk__voice__mysekai_talk_beta_001":
        "voice_mysekai_talk_beta_001_01_001",
    "mysekai__talk__voice__mysekai_talk_gamma_001_02":
        "voice_mysekai_talk_gamma_001_02_03_001",
    "mysekai__sound__se__fixture__basketball": "se_bounce",
    "mysekai__sound__bgm__music0001": "music0001",
    "mysekai__talk__part_voice__mysekai_part_voice_v2_21miku_idol":
        "partvoice_01_021_idol",
}


def test_voice_stem_drops_prefix_and_line_pair():
    assert audio_corpus.voice_stem(
        "voice_mysekai_talk_release_001_0136_02_001"
    ) == "mysekai_talk_release_001_0136"
    assert audio_corpus.voice_stem(
        "voice_mysekai_talk_gamma_001_02_03_001"
    ) == "mysekai_talk_gamma_001_02"


def test_voice_requests_group_by_script_and_skip_other_prefixes():
    requests, cues = audio_corpus.voice_requests(TALKS)
    assert requests == {
        "mysekai/talk/voice/mysekai_talk_alpha_001": [
            "voice_mysekai_talk_alpha_001_01_001",
            "voice_mysekai_talk_alpha_001_02_001",
        ],
        "mysekai/talk/voice/mysekai_talk_beta_001": [
            "voice_mysekai_talk_beta_001_01_001",
        ],
        "mysekai/talk/voice/mysekai_talk_gamma_001_02": [
            "voice_mysekai_talk_gamma_001_02_03_001",
        ],
    }
    assert len(cues) == 4            # the partvoice cue is not a voice_ cue


def test_prefix_packages_selects_a_family_and_excludes_existing():
    names = list(MANIFEST["bundles"])
    se = audio_corpus.prefix_packages(
        names, audio_corpus.SE, "mysekai__sound__se__",
        exclude={"mysekai/sound/se/se_mysekai"})
    assert se == ["mysekai__sound__se__fixture__basketball"]
    bgm = audio_corpus.prefix_packages(names, audio_corpus.BGM,
                                       "mysekai__sound__bgm__")
    assert bgm == ["mysekai__sound__bgm__bgm_mysekai_beach",
                   "mysekai__sound__bgm__music0001"]


class _Record:
    def __init__(self, tree):
        self.kinds = {7: "TextAsset"}
        self._tree = tree

    def tree(self, path_id):
        return self._tree


class _FakeStore:
    """A package store whose every known package holds one text asset."""

    def __init__(self, paths, root=None):
        assert paths == []
        self.root = root

    def forget(self, name):
        pass

    def package(self, name, record_missing=True):
        if name not in STREAM_NAMES:
            return None
        return type("Package", (), {
            "name": name, "files": [], "dependencies": [],
            "contents": [(name, _Record({"m_Name": name + ".acb",
                                         "m_Script": b"FAKE"}), 7)],
        })()


@pytest.fixture
def decoder(tmp_path):
    """A stand-in vgmstream-cli: stream names from STREAM_NAMES, a tiny wav."""
    script = tmp_path / "fake_decoder.py"
    script.write_text(textwrap.dedent(f'''
        import json, os, sys, wave, struct
        names = json.load(open({json.dumps(str(tmp_path / "names.json"))}))
        argv = sys.argv[1:]
        archive = argv[-1]
        package = os.path.basename(archive)[:-len(".acb")]
        if argv[0] == "-m":
            index = argv[argv.index("-s") + 1] if "-s" in argv else "1"
            print("sample rate: 44100 Hz")
            print("channels: 1")
            print("stream total samples: 4410 (0:00.100 seconds)")
            print("encoding: CRI HCA")
            print("stream count: 1")
            print("stream index: " + index)
            print("stream name: " + names.get(package, "cue"))
            sys.exit(0)
        out = argv[argv.index("-o") + 1]
        w = wave.open(out, "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(struct.pack("<441h", *([0] * 441)))
        w.close()
        sys.exit(0)
    '''), encoding="utf-8")
    (tmp_path / "names.json").write_text(json.dumps(STREAM_NAMES),
                                         encoding="utf-8")
    if sys.platform == "win32":
        path = tmp_path / "vgmstream-cli.bat"
        path.write_text(f'@"{sys.executable}" "{script}" %*\r\n',
                        encoding="utf-8")
    else:
        path = tmp_path / "vgmstream-cli"
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
                        encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


@pytest.fixture
def corpus_inputs(tmp_path):
    talks = tmp_path / "talks.json"
    talks.write_text(json.dumps(TALKS), encoding="utf-8", newline="\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(MANIFEST), encoding="utf-8", newline="\n")
    out = tmp_path / "phenomena"
    audio = out / "audio"
    audio.mkdir(parents=True)
    # One package already in the library — the shared ambience package, as the
    # real phenomena job leaves it.
    (audio / "loop.json").write_text(json.dumps({
        "status": "succeeded", "packages": [
            {"package": "mysekai__sound__se__se_mysekai", "streams": []}],
    }), encoding="utf-8", newline="\n")
    return talks, manifest, out


def test_corpus_extraction_end_to_end(tmp_path, monkeypatch, decoder,
                                      corpus_inputs):
    talks, manifest, out = corpus_inputs
    monkeypatch.setattr("core.assets.packages.PackageStore", _FakeStore)
    report = audio_corpus.extract_audio_corpus(
        talks, manifest, str(tmp_path / "bundles"), out, decoder=decoder)

    families = report["families"]
    # talk voices: three packages requested, every corpus cue decoded.
    assert families["talk-voice"]["requested"] == 3
    assert families["talk-voice"]["succeeded"] == 3
    assert families["talk-voice"]["failed"] == []
    assert families["talk-voice"]["requestedCues"] == 4
    assert families["talk-voice"]["decodedCues"] == 4
    assert families["talk-voice"]["missingPackages"] == []
    assert families["talk-voice"]["uncovered"] == []
    # se: the already-extracted ambience package is not requested again.
    assert families["se"]["requested"] == 1
    assert families["se"]["succeeded"] == 1
    # bgm and part voices: the whole family, none of it on disk yet.
    assert families["bgm"]["requested"] == 2
    assert families["part-voice"]["requested"] == 1
    # one of the corpus's partvoice cues is answered by the whole-family
    # extraction, the other names a real gap
    assert report["partVoiceCues"] == {"requested": 2, "answered": 1,
                                       "missing": ["partvoice_01_021_band"]}

    audio = out / "audio"
    corpus = json.loads((audio / "corpus.json").read_text(encoding="utf-8"))
    assert corpus["version"] == 1
    loop = json.loads((audio / "loop.json").read_text(encoding="utf-8"))
    names = [entry["package"] for entry in loop["packages"]]
    # the pre-existing entry keeps its place at the head of the document
    assert names[0] == "mysekai__sound__se__se_mysekai"
    assert "mysekai__talk__voice__mysekai_talk_alpha_001" in names
    # a decoded waveform exists under the cue's own name
    assert (audio / "mysekai__talk__voice__mysekai_talk_alpha_001" /
            "voice_mysekai_talk_alpha_001_01_001.wav").exists()
    # the shipped document does not carry this machine's directory layout
    assert "path" not in corpus


def test_corpus_names_a_missing_script_instead_of_failing(tmp_path,
                                                          monkeypatch,
                                                          decoder,
                                                          corpus_inputs):
    talks, manifest, out = corpus_inputs
    document = json.loads(manifest.read_text(encoding="utf-8"))
    del document["bundles"]["mysekai/talk/voice/mysekai_talk_beta_001"]
    manifest.write_text(json.dumps(document), encoding="utf-8", newline="\n")
    monkeypatch.setattr("core.assets.packages.PackageStore", _FakeStore)
    report = audio_corpus.extract_audio_corpus(
        talks, manifest, str(tmp_path / "bundles"), out, decoder=decoder)

    family = report["families"]["talk-voice"]
    assert family["requested"] == 3
    assert family["succeeded"] == 2
    assert family["missingPackages"] == [{
        "package": "mysekai__talk__voice__mysekai_talk_beta_001",
        "cues": ["voice_mysekai_talk_beta_001_01_001"],
        "reason": audio_corpus.NO_PACKAGE,
    }]
    assert family["uncovered"] == [{
        "cue": "voice_mysekai_talk_beta_001_01_001",
        "reason": audio_corpus.NO_PACKAGE,
    }]
    assert family["decodedCues"] == 3


def test_loop_merge_replaces_and_keeps_order(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "loop.json").write_text(json.dumps({"packages": [
        {"package": "a", "streams": [1]},
        {"package": "b", "streams": []},
    ]}), encoding="utf-8", newline="\n")

    class _Lib:
        status = "succeeded"
        decoder = True
        transcoder = True
        packages = [{"package": "b", "streams": [2]},
                    {"package": "c", "streams": []}]

    document = audio_corpus._merge_loop(audio, _Lib)
    assert [entry["package"] for entry in document["packages"]] == \
        ["a", "b", "c"]
    assert document["packages"][1]["streams"] == [2]   # the new entry won
    assert document["file"] == "audio/loop.json"
