"""The site/phenomena commands refuse a --bundle that names no file.

A bare package name under ``--bundle`` keys the store by basename while
``UnityPy.load`` answers the nonexistent path with an empty environment, so
without the entrance check the run reports zero objects and exits green.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import cli


def _argv(cmd, bundles, out):
    argv = [cmd]
    for bundle in bundles:
        argv += ["--bundle", bundle]
    return argv + ["--out-dir", str(out)]


def test_phenomena_refuses_a_bare_bundle_name(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        cli.main(_argv("phenomena", ["mysekai__environment__001_sunny__common"],
                       tmp_path / "out"))


def test_site_refuses_a_bare_bundle_name(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        cli.main(_argv("site", ["mysekai__site__field__grasslands"],
                       tmp_path / "out"))


def test_phenomena_accepts_a_path_that_exists(tmp_path, monkeypatch):
    """Positive control: a real path passes the entrance and reaches the
    extractor, so the refusal above cannot be a door that is always shut."""
    bundle = tmp_path / "mysekai__environment__001_sunny__common"
    bundle.write_bytes(b"")
    reached = {}
    import phenomena.environments as environments

    def fake(bundles, out_dir, **kwargs):
        reached["bundles"] = list(bundles)
        return {"summary": {}}

    monkeypatch.setattr(environments, "extract_phenomena", fake)
    # cli imports the function at call time; patch the module attribute the
    # import resolves to.
    monkeypatch.setitem(sys.modules, "phenomena.environments", environments)
    cli.main(_argv("phenomena", [str(bundle)], tmp_path / "out"))
    assert reached["bundles"] == [str(bundle)]


def test_site_accepts_a_path_that_exists(tmp_path, monkeypatch):
    bundle = tmp_path / "mysekai__site__field__grasslands"
    bundle.write_bytes(b"")
    reached = {}
    import sites.pack as pack

    def fake(bundles, out_dir, **kwargs):
        reached["bundles"] = list(bundles)
        return {"summary": {}}

    monkeypatch.setattr(pack, "extract_sites", fake)
    monkeypatch.setitem(sys.modules, "sites.pack", pack)
    cli.main(_argv("site", [str(bundle)], tmp_path / "out"))
    assert reached["bundles"] == [str(bundle)]
