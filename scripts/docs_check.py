#!/usr/bin/env python3
"""Validate this fork's current docs without rewriting historical reports."""

from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md", "AGENTS.md", "ARCHITECTURE.md", "CHANGELOG.md",
    "docs/API.md", "docs/CLI.md", "docs/CONFIG.md", "docs/DATA_MODEL.md",
    "docs/TESTING.md", "docs/FEATURES.md", "docs/CONTRACTS.md",
    "docs/native-responses-identity.md",
)
ID = re.compile(r"\b[FC]-\d{3}\b")


def definitions(text: str, prefix: str) -> dict[str, str]:
    sections = re.split(rf"(?m)^## ({prefix}-\d{{3}}) [^\n]*\n", text)
    result = {}
    for index in range(1, len(sections), 2):
        identity = sections[index]
        if identity in result:
            raise ValueError(f"duplicate definition: {identity}")
        result[identity] = sections[index + 1]
    return result


def check(root: Path = ROOT) -> list[str]:
    errors = []
    for name in REQUIRED:
        if not (root / name).is_file():
            errors.append(f"missing required document: {name}")
    if errors:
        return errors

    contents = {name: (root / name).read_text() for name in REQUIRED}
    try:
        features = definitions(contents["docs/FEATURES.md"], "F")
        contracts = definitions(contents["docs/CONTRACTS.md"], "C")
    except ValueError as error:
        return [str(error)]
    if not features or not contracts:
        errors.append("Feature and Contract definitions must both be nonempty")

    tree = [(len(indent), identity) for indent, identity in re.findall(
        r"(?m)^([ \t]*)- `(F-\d{3})` [^\n]+$", contents["docs/FEATURES.md"]
    )]
    tree_ids = [identity for _, identity in tree]
    if len(tree_ids) != len(set(tree_ids)):
        errors.append("duplicate Feature ID in tree")
    leaves = {identity for index, (indent, identity) in enumerate(tree)
              if index + 1 == len(tree) or tree[index + 1][0] <= indent}
    if leaves != set(features):
        errors.append(f"tree leaves and Feature definitions differ: {leaves ^ set(features)}")

    known = set(tree_ids) | set(contracts)
    for name, content in contents.items():
        for identity in set(ID.findall(content)) - known:
            errors.append(f"{name}: unknown reference {identity}")

    for identity, body in {**features, **contracts}.items():
        related = "关联契约" if identity.startswith("F-") else "关联功能"
        related_ids = contracts if identity.startswith("F-") else features
        match = re.search(rf"(?m)^- {related}：([^\n]+)$", body)
        if not match or not (set(ID.findall(match[1])) & set(related_ids)):
            errors.append(f"{identity}: missing valid {related}")
        evidence = re.search(r"(?m)^- 证据：([^\n]+)$", body)
        paths = re.findall(r"`([^`]+)`", evidence[1]) if evidence else []
        if not paths:
            errors.append(f"{identity}: missing evidence paths")
        for value in paths:
            path = (root / value).resolve()
            if not path.is_relative_to(root.resolve()) or not path.exists():
                errors.append(f"{identity}: missing or unsafe evidence path {value}")

    # README contains inherited historical links outside this correction's scope.
    # Its new section is checked; every other current document is checked in full.
    contents["README.md"] = contents["README.md"].split(
        "## Native Responses identity backport", 1
    )[-1]
    for name, content in contents.items():
        for target in re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", content):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            path = (root / name).parent / unquote(parsed.path) if parsed.path else root / name
            if not path.is_file():
                errors.append(f"{name}: broken relative link {target}")
                continue
            if parsed.fragment:
                headings = re.findall(r"(?m)^#{1,6} (.+)$", path.read_text())
                anchors = {re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
                           for heading in headings}
                if unquote(parsed.fragment) not in anchors:
                    errors.append(f"{name}: broken fragment {target}")
    return errors


def main() -> int:
    errors = check()
    for error in errors:
        print(f"docs-check: {error}", file=sys.stderr)
    if errors:
        return 1
    print("docs-check: current documents, IDs, references, evidence and links are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
