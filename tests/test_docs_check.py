import importlib.util
from pathlib import Path
import re
import shutil

import pytest


spec = importlib.util.spec_from_file_location("docs_check", Path(__file__).parents[1] / "scripts/docs_check.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


@pytest.fixture
def tree(tmp_path):
    for name in docs.REQUIRED:
        source = docs.ROOT / name
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name in ("docs/FEATURES.md", "docs/CONTRACTS.md"):
        for line in (tmp_path / name).read_text().splitlines():
            if line.startswith("- 证据："):
                for value in re.findall(r"`([^`]+)`", line):
                    target = tmp_path / value
                    if target.exists():
                        continue
                    source = docs.ROOT / value
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if source.is_dir():
                        target.mkdir()
                    else:
                        target.write_text(source.read_text())
    return tmp_path


def test_current_documentation_closes_real_evidence():
    assert docs.check() == []


@pytest.mark.parametrize("mutation, expected", [
    ("missing", "missing required"),
    ("duplicate", "duplicate definition"),
    ("empty", "must both be nonempty"),
    ("duplicate_tree", "duplicate Feature ID in tree"),
    ("missing_leaf", "tree leaves"),
    ("reference", "unknown reference"),
    ("relation", "missing valid"),
    ("evidence", "missing or unsafe evidence"),
    ("no_evidence", "missing evidence paths"),
    ("link", "broken relative link"),
    ("fragment", "broken fragment"),
])
def test_invalid_docs_fail_closed(tree, mutation, expected):
    features = tree / "docs/FEATURES.md"
    content = features.read_text()
    if mutation == "missing":
        features.unlink()
    elif mutation == "duplicate":
        features.write_text(content + "\n## F-120 Duplicate\n")
    elif mutation == "empty":
        features.write_text("# Empty\n")
    elif mutation == "duplicate_tree":
        line = next(line for line in content.splitlines() if "- `F-120`" in line)
        features.write_text(content + "\n" + line + "\n")
    elif mutation == "missing_leaf":
        features.write_text(re.sub(r"(?m)^.*- `F-120`.*\n", "", content))
    elif mutation == "reference":
        features.write_text(content + "\n`C-999`\n")
    elif mutation == "relation":
        features.write_text(re.sub(r"(?m)^- 关联契约：.*$", "- 关联契约：none", content))
    elif mutation == "evidence":
        features.write_text(re.sub(r"(?m)^- 证据：.*$", "- 证据：`does-not-exist.py`", content))
    elif mutation == "no_evidence":
        features.write_text(re.sub(r"(?m)^- 证据：.*$", "- 证据：none", content))
    else:
        target = "absent.md" if mutation == "link" else "API.md#not-a-heading"
        features.write_text(content + f"\n[broken]({target})\n")
    assert any(expected in error for error in docs.check(tree))


def test_entrypoint_reports_failure_and_success(monkeypatch, capsys):
    monkeypatch.setattr(docs, "check", lambda: ["controlled failure"])
    assert docs.main() == 1
    assert "controlled failure" in capsys.readouterr().err
    monkeypatch.setattr(docs, "check", lambda: [])
    assert docs.main() == 0
    assert "valid" in capsys.readouterr().out
