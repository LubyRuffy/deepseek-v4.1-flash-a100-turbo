"""The runtime patch must fail closed before touching an unknown package."""

import importlib.util
import difflib
import hashlib
import json
import os
from pathlib import Path

import pytest


def load_installer():
    path = Path(__file__).parents[1] / "patches/responses_identity/install.py"
    spec = importlib.util.spec_from_file_location("responses_identity_install", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unknown_package_is_unchanged(tmp_path):
    installer = load_installer()
    target = tmp_path / "entrypoints/openai/responses"
    target.mkdir(parents=True)
    for name in ("context.py", "serving.py", "streaming_events.py"):
        (target / name).write_text("unknown = True\n")
    before = {p: p.read_bytes() for p in target.iterdir()}
    with pytest.raises(installer.PatchError, match="unknown|mixed"):
        installer.install(tmp_path)
    assert {p: p.read_bytes() for p in target.iterdir()} == before


def test_profiles_are_exact_and_cover_both_deployments():
    installer = load_installer()
    manifest = json.loads((installer.RESOURCE_DIR / "profiles.json").read_text())
    assert {p["name"] for p in manifest["profiles"]} == {"h100-v0.31.0", "a100-v0.13.0"}
    for profile in manifest["profiles"]:
        assert set(profile["files"]) == {"context.py", "serving.py", "streaming_events.py"}
        for item in profile["files"].values():
            assert len(item["before_sha256"]) == len(item["after_sha256"]) == 64
            assert item["before_sha256"] != item["after_sha256"]


@pytest.fixture
def fixture_package(tmp_path, monkeypatch):
    installer = load_installer()
    resources = tmp_path / "resources"
    resources.mkdir()
    package = tmp_path / "vllm"
    target = package / installer.RELATIVE_DIR
    target.mkdir(parents=True)
    files = {}
    originals = {}
    replacements = {}
    for index, name in enumerate(sorted(installer.MODULES)):
        before = f"value = {index}\nlabel = 'old'\n".encode()
        after = f"value = {index}\nlabel = 'fixed'\n".encode()
        (target / name).write_bytes(before)
        (target / name).chmod(0o640)
        patch_name = name + ".patch"
        (resources / patch_name).write_text("".join(difflib.unified_diff(
            before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True),
            fromfile=name, tofile=name,
        )))
        files[name] = {"before_sha256": hashlib.sha256(before).hexdigest(),
                       "after_sha256": hashlib.sha256(after).hexdigest(), "patch": patch_name}
        originals[name] = before
        replacements[name] = after
    manifest = {"profiles": [{"name": "fixture", "files": files}]}
    (resources / "profiles.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(installer, "RESOURCE_DIR", resources)
    return installer, package, target, resources, manifest, originals, replacements


def snapshot(target):
    return {p.name: (p.read_bytes(), p.stat().st_mode & 0o777) for p in target.iterdir()}


def test_install_check_idempotence_and_file_modes(fixture_package):
    installer, package, target, _, _, before, after = fixture_package
    initial = snapshot(target)
    assert installer.install(package, check=True) == "applicable:fixture"
    assert snapshot(target) == initial
    assert installer.install(package) == "applied:fixture"
    assert snapshot(target) == {name: (data, 0o640) for name, data in after.items()}
    assert installer.install(package) == "already-applied:fixture"
    assert {p.name for p in target.iterdir()} == set(before)


def test_mixed_package_fails_without_writes(fixture_package):
    installer, package, target, _, _, _, after = fixture_package
    (target / "context.py").write_bytes(after["context.py"])
    before = snapshot(target)
    with pytest.raises(installer.PatchError, match="unknown or mixed"):
        installer.install(package)
    assert snapshot(target) == before


@pytest.mark.parametrize("failure", ["digest", "syntax", "resource", "module_set"])
def test_preflight_failure_changes_no_source(fixture_package, failure):
    installer, package, target, resources, manifest, _, after = fixture_package
    spec = manifest["profiles"][0]["files"]["streaming_events.py"]
    if failure == "digest":
        spec["after_sha256"] = "0" * 64
    elif failure == "syntax":
        patch_path = resources / spec["patch"]
        patch_path.write_text(patch_path.read_text().replace("+label = 'fixed'", "+label = ("))
        spec["after_sha256"] = hashlib.sha256(after["streaming_events.py"].replace(b"label = 'fixed'", b"label = (")).hexdigest()
    elif failure == "resource":
        spec["patch"] = "../outside.patch"
    else:
        del manifest["profiles"][0]["files"]["context.py"]
    (resources / "profiles.json").write_text(json.dumps(manifest))
    before = snapshot(target)
    with pytest.raises((installer.PatchError, SyntaxError)):
        installer.install(package)
    assert snapshot(target) == before


def test_missing_or_symlink_module_is_refused(fixture_package):
    installer, package, target, _, _, _, _ = fixture_package
    (target / "context.py").unlink()
    with pytest.raises(installer.PatchError, match="unavailable"):
        installer.install(package)
    (target / "context.py").symlink_to(target / "serving.py")
    with pytest.raises(installer.PatchError, match="symbolic"):
        installer.install(package)


def test_replacement_failure_rolls_back_and_cleans_stages(fixture_package, monkeypatch):
    installer, package, target, _, _, _, _ = fixture_package
    before = snapshot(target)
    original_replace = os.replace
    calls = []

    def fail_second(source, destination):
        calls.append(destination)
        if len(calls) == 2:
            raise OSError("simulated replacement failure")
        original_replace(source, destination)

    monkeypatch.setattr(installer.os, "replace", fail_second)
    with pytest.raises(OSError, match="simulated"):
        installer.install(package)
    assert len(calls) == 3
    assert snapshot(target) == before


def test_staging_failure_leaves_sources_unchanged(fixture_package, monkeypatch):
    installer, package, target, _, _, _, _ = fixture_package
    before = snapshot(target)
    original_stage = installer._stage
    calls = []

    def fail_second(*args):
        calls.append(args)
        if len(calls) == 2:
            raise OSError("simulated staging failure")
        return original_stage(*args)

    monkeypatch.setattr(installer, "_stage", fail_second)
    with pytest.raises(OSError, match="staging"):
        installer.install(package)
    assert snapshot(target) == before


def test_concurrent_change_is_preserved_without_replacement(fixture_package, monkeypatch):
    installer, package, target, _, _, _, _ = fixture_package
    original_stage = installer._stage

    def mutate_source(*args):
        staged = original_stage(*args)
        (target / "context.py").write_text("concurrent = True\n")
        return staged

    monkeypatch.setattr(installer, "_stage", mutate_source)
    with pytest.raises(installer.PatchError, match="changed during preflight"):
        installer.install(package)
    assert (target / "context.py").read_text() == "concurrent = True\n"
    assert {p.name for p in target.iterdir()} == installer.MODULES


def test_rollback_failure_retains_original_recovery_file(fixture_package, monkeypatch):
    installer, package, target, _, _, originals, _ = fixture_package
    original_replace = os.replace
    calls = []

    def fail_replace_and_rollback(source, destination):
        calls.append(destination)
        if len(calls) >= 2:
            raise OSError("simulated failure")
        original_replace(source, destination)

    monkeypatch.setattr(installer.os, "replace", fail_replace_and_rollback)
    with pytest.raises(installer.PatchError, match="rollback failed; originals retained"):
        installer.install(package)
    recovery = list(target.glob(".responses-identity-*"))
    assert len(recovery) == 1
    assert recovery[0].read_bytes() == originals["context.py"]
    assert recovery[0].stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("patch", ["", "bad\n", "@@ -1 +1 @@\n?bad\n", "@@ -1 +1 @@\n-wrong\n+new\n", "@@ -9 +9 @@\n-a\n+b\n", "@@ -1,2 +1 @@\n-a\n+b\n"])
def test_malformed_diff_is_refused(patch):
    installer = load_installer()
    with pytest.raises(installer.PatchError):
        installer.apply_diff(b"a\n", patch)


def test_diff_handles_multiple_hunks_and_insert_delete():
    installer = load_installer()
    before = "a\nb\nc\nd\ne\nf\ng\nh\n"
    after = "start\na\nb\nc\nd\ne\nf\ng\n"
    diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), n=0))
    assert installer.apply_diff(before.encode(), diff) == after.encode()
