import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest


spec = importlib.util.spec_from_file_location("native_release", Path(__file__).parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
FIXTURE_FILES = ("VERSION", "README.md", "scripts/example.py", "docs/native-responses-identity.md")


def test_version_allocation_is_numeric_and_retry_keeps_unpublished_version():
    assert release.next_version([]) == "0.1.0"
    assert release.next_version(["v0.1.9", "v0.1.10", "unrelated"]) == "0.1.11"
    assert release.next_version(["v0.1.10"], "0.1.11") == "0.1.11"
    assert release.next_version(["v0.1.11"], "0.1.11") == "0.1.12"
    assert release.next_version([], "invalid") == "0.1.0"


def test_bundle_contains_only_committed_sources_and_provenance(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name in FIXTURE_FILES:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("reviewed source\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
    (root / "credential.local").write_text("must never ship")
    (root / "VERSION").write_text("uncommitted version")
    bundle, receipt = release.archive(root, tmp_path / "out", "0.1.0")
    with tarfile.open(bundle) as archive:
        assert set(archive.getnames()) >= set(FIXTURE_FILES)
        assert "credential.local" not in archive.getnames()
        assert archive.extractfile("VERSION").read() == b"reviewed source\n"
    value = json.loads(receipt.read_text())
    assert value["source_commit"] == release.git(root, "rev-parse", "HEAD")
    assert value["sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    original = bundle.read_bytes()
    release.archive(root, tmp_path / "out", "0.1.0")
    assert bundle.read_bytes() == original


def repository(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    root = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(bare), str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "checkout", "-qb", "main"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    for name in FIXTURE_FILES:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("0.1.0\n" if name == "VERSION" else "source\n")
    (root / ".gitignore").write_text("dist/\n")
    commit(root, "fixture")
    subprocess.run(["git", "-C", str(root), "push", "-qu", "origin", "main"], check=True)
    return root


def commit(root, message):
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", message], check=True)


def test_version_cli_and_publish_push_exact_committed_tag(tmp_path, monkeypatch):
    root = repository(tmp_path)
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["release.py", "version"])
    release.main()
    assert (root / "VERSION").read_text() == "0.1.0\n"
    monkeypatch.setattr(sys, "argv", ["release.py", "publish"])
    original_run = subprocess.run
    uploads = []

    def run(command, **kwargs):
        if command[0] != "gh":
            return original_run(command, **kwargs)
        uploads.append(command)
        assert command[:4] == ["gh", "release", "create", "v0.1.0"]
        for artifact in command[4:6]:
            assert Path(artifact).is_file()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    release.main()
    assert len(uploads) == 1
    assert release.git(root, "rev-parse", "v0.1.0^{commit}") == release.git(root, "rev-parse", "HEAD")
    assert "refs/tags/v0.1.0" in release.git(root, "ls-remote", "--tags", "origin")
    with pytest.raises(SystemExit, match="already exists"):
        release.main()
    assert len(uploads) == 1


@pytest.mark.parametrize("failure", ["invalid", "dirty", "branch", "unpublished"])
def test_publish_rejects_unreviewable_sources(tmp_path, monkeypatch, failure):
    root = repository(tmp_path)
    if failure == "invalid":
        (root / "VERSION").write_text("broken\n")
    elif failure == "dirty":
        (root / "unreviewed.txt").write_text("change")
    elif failure == "branch":
        subprocess.run(["git", "-C", str(root), "checkout", "-qb", "topic"], check=True)
    else:
        (root / "VERSION").write_text("0.1.1\n")
        commit(root, "unpublished")
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["release.py", "publish"])
    with pytest.raises(SystemExit):
        release.main()
    assert not release.git(root, "tag", "--list")
    assert not (root / "dist").exists()
