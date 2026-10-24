#!/usr/bin/env python3
"""Install the reviewed vLLM Responses fix for exact, known source profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

RESOURCE_DIR = Path(__file__).resolve().parent
MODULES = {"context.py", "serving.py", "streaming_events.py"}
RELATIVE_DIR = Path("entrypoints/openai/responses")


class PatchError(RuntimeError):
    """The package cannot be safely modified by this exact patch."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_diff(source: bytes, patch: str) -> bytes:
    """Apply unified hunks at their exact source offsets, without fuzz."""
    original = source.decode("utf-8").splitlines(keepends=True)
    lines = patch.splitlines(keepends=True)
    result: list[str] = []
    cursor = 0
    index = 0
    hunks = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith(("--- ", "+++ ")):
            index += 1
            continue
        match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n?", line)
        if match is None:
            raise PatchError("invalid unified diff header")
        start = int(match[1]) - (int(match[2] or 1) != 0)
        if start < cursor or start > len(original):
            raise PatchError("overlapping or out-of-range diff hunk")
        result.extend(original[cursor:start])
        cursor = start
        old_count = new_count = 0
        index += 1
        while index < len(lines) and not lines[index].startswith("@@ "):
            entry = lines[index]
            if not entry or entry[0] not in " +-":
                raise PatchError("invalid unified diff entry")
            operation, payload = entry[0], entry[1:]
            if operation in " -":
                if cursor >= len(original) or original[cursor] != payload:
                    raise PatchError("unified diff context does not match")
                cursor += 1
                old_count += 1
            if operation in " +":
                result.append(payload)
                new_count += 1
            index += 1
        if old_count != int(match[2] or 1) or new_count != int(match[4] or 1):
            raise PatchError("unified diff hunk counts do not match")
        hunks += 1
    if hunks == 0:
        raise PatchError("empty unified diff")
    result.extend(original[cursor:])
    return "".join(result).encode("utf-8")


def _stage(path: Path, data: bytes, mode: int) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".responses-identity-", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def install(package_root: Path, *, check: bool = False) -> str:
    """Preflight all modules, then replace; restore all originals on failure."""
    manifest = json.loads((RESOURCE_DIR / "profiles.json").read_text())
    directory = Path(package_root) / RELATIVE_DIR
    originals: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    for name in sorted(MODULES):
        path = directory / name
        if path.is_symlink():
            raise PatchError("source modules must not be symbolic links")
        try:
            originals[name] = path.read_bytes()
            modes[name] = stat.S_IMODE(path.stat().st_mode)
        except OSError as error:
            raise PatchError("required Responses source module is unavailable") from error
    hashes = {name: sha256(data) for name, data in originals.items()}
    selected = None
    for profile in manifest["profiles"]:
        if set(profile["files"]) != MODULES:
            raise PatchError("invalid profile module set")
        if all(hashes[name] == spec["after_sha256"] for name, spec in profile["files"].items()):
            return "already-applied:" + profile["name"]
        if all(hashes[name] == spec["before_sha256"] for name, spec in profile["files"].items()):
            selected = profile
    if selected is None:
        raise PatchError("unknown or mixed Responses source profile; no files changed")
    replacements: dict[str, bytes] = {}
    for name, spec in selected["files"].items():
        patch_path = RESOURCE_DIR / spec["patch"]
        if patch_path.parent != RESOURCE_DIR:
            raise PatchError("invalid patch resource path")
        data = apply_diff(originals[name], patch_path.read_text())
        if sha256(data) != spec["after_sha256"]:
            raise PatchError("patched module digest mismatch")
        compile(data, str(directory / name), "exec")
        replacements[name] = data
    if check:
        return "applicable:" + selected["name"]
    stages: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    replaced: list[str] = []
    try:
        for name in sorted(MODULES):
            stages[name] = _stage(directory / name, replacements[name], modes[name])
            backups[name] = _stage(directory / name, originals[name], modes[name])
        # Refuse a concurrent package update after the potentially slow preflight.
        if any((directory / name).read_bytes() != data for name, data in originals.items()):
            raise PatchError("source changed during preflight; no files changed")
        for name in sorted(MODULES):
            os.replace(stages[name], directory / name)
            replaced.append(name)
    except BaseException as error:
        rollback_errors = []
        for name in reversed(replaced):
            try:
                os.replace(backups[name], directory / name)
            except OSError:
                rollback_errors.append(name)
        if rollback_errors:
            # Preserve the named original recovery files on rollback failure.
            retained = [str(backups[name]) for name in rollback_errors]
            raise PatchError("rollback failed; originals retained at " + ", ".join(retained)) from error
        raise
    finally:
        for path in stages.values():
            path.unlink(missing_ok=True)
        for name, path in backups.items():
            if name not in locals().get("rollback_errors", []):
                path.unlink(missing_ok=True)
    return "applied:" + selected["name"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True, help="installed vllm package directory")
    parser.add_argument("--check", action="store_true", help="preflight only; do not write")
    args = parser.parse_args()
    try:
        print(install(args.package_root, check=args.check))
    except (PatchError, OSError, SyntaxError, ValueError) as error:
        parser.exit(1, f"Responses identity patch refused: {error}\n")


if __name__ == "__main__":
    main()
