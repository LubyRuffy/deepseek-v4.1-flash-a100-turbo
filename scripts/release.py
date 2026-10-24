"""Version and publish the source-only native Responses backport bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def next_version(tags: list[str], current: str = "") -> str:
    versions = [tuple(map(int, match.groups())) for tag in tags
                if (match := re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag))]
    latest = max(versions, default=(0, 0, 0))
    if re.fullmatch(r"\d+\.\d+\.\d+", current):
        if tuple(map(int, current.split("."))) > latest:
            return current
    return "0.1.0" if not versions else f"{latest[0]}.{latest[1]}.{latest[2] + 1}"


def archive(root: Path, output: Path, version: str) -> tuple[Path, Path]:
    sha = git(root, "rev-parse", "HEAD")
    output.mkdir(parents=True, exist_ok=True)
    bundle = output / f"native-responses-identity-v{version}.tar.gz"
    subprocess.run(["git", "-C", str(root), "archive", "--format=tar.gz",
                    f"--output={bundle}", "HEAD"], check=True)
    receipt = output / f"native-responses-identity-v{version}.json"
    receipt.write_text(json.dumps({
        "version": version, "source_commit": sha, "bundle": bundle.name,
        "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "upstream_fix": "7ca31ef5993dc4426d912f32b8eb3cd70fb7a078",
    }, indent=2) + "\n")
    return bundle, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("version", "publish"))
    args = parser.parse_args()
    subprocess.run(["git", "-C", str(ROOT), "fetch", "origin", "--tags"], check=True)
    version_file = ROOT / "VERSION"
    if args.action == "version":
        current = version_file.read_text().strip() if version_file.exists() else ""
        version = next_version(git(ROOT, "tag", "--list").splitlines(), current)
        version_file.write_text(version + "\n")
        print(version)
        return
    version = version_file.read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("VERSION must contain a semantic version")
    if git(ROOT, "branch", "--show-current") != "main" or git(ROOT, "status", "--porcelain"):
        raise SystemExit("Publish requires a clean main checkout")
    sha = git(ROOT, "rev-parse", "HEAD")
    if sha != git(ROOT, "rev-parse", "origin/main"):
        raise SystemExit("Publish requires main to match origin/main")
    tag = "v" + version
    if tag in git(ROOT, "tag", "--list").splitlines():
        raise SystemExit("Release tag already exists; inspect its outcome before retrying")
    bundle, receipt = archive(ROOT, ROOT / "dist", version)
    subprocess.run(["git", "-C", str(ROOT), "tag", "-a", tag, "-m", tag], check=True)
    subprocess.run(["git", "-C", str(ROOT), "push", "origin", tag], check=True)
    subprocess.run(["gh", "release", "create", tag, str(bundle), str(receipt),
                    "--verify-tag", "--title", f"Native Responses identity fix {tag}",
                    "--notes-file", str(ROOT / "docs/native-responses-identity.md")],
                   cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
