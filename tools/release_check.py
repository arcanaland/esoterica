#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Check that one source is releasable under a given version

release_check.py <source> <version>                report every problem
release_check.py <source> <version> --assets       print the asset paths, one per line
release_check.py <source> <version> --identifier   print [meta].identifier

The version is the one a tag claims. It is checked against the built document's
[meta].version.

--require-tag (for CI): check that <source>/v<version> is an annotated tag
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR = "PROVENANCE.toml"


def tag_name(source: str, version: str) -> str:
    return f"{source}/v{version}"


def document(dist: Path) -> tuple[Path | None, str | None]:
    """The one built document in a dist/ directory, or a problem with it."""
    if not dist.is_dir():
        return None, f"no dist/ directory: {dist}"

    found = [p for p in sorted(dist.glob("*.toml")) if p.name != SIDECAR]
    if not found:
        return None, f"dist/ holds no document beside {SIDECAR}"
    if len(found) > 1:
        names = ", ".join(p.name for p in found)
        return None, f"dist/ holds more than one document: {names}"
    return found[0], None


def tag_kind(repo_root: Path, tag: str) -> str | None:
    """The object a tag name resolves to: tag, commit, or None when it is absent.

    An annotated tag is its own object; a lightweight one resolves to a commit.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-t", tag],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def problems(
    repo_root: Path, source: str, version: str, *, require_tag: bool = False
) -> list[str]:
    """Return a list of reasons this source cannot be released. Empty means it can."""
    source_dir = repo_root / "sources" / source
    manifest = source_dir / "SOURCE.toml"
    if not manifest.is_file():
        return [f"no such source: {manifest} does not exist"]

    built, problem = document(source_dir / "dist")
    if problem is not None:
        return [problem]

    try:
        meta = tomllib.loads(built.read_text(encoding="utf-8")).get("meta", {})
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [f"unreadable document: {exc}"]

    found = []

    stated = meta.get("version")
    if stated != version:
        found.append(
            f"the tag claims version {version!r}, "
            f"{built.name} states [meta].version = {stated!r}"
        )

    identifier = meta.get("identifier")
    if not isinstance(identifier, str):
        found.append("[meta].identifier is missing")
    else:
        segment = identifier.rsplit("/", 1)[-1]
        if built.stem != segment:
            found.append(
                f"filename {built.name!r} is not its identifier's last segment "
                f"{segment + '.toml'!r}"
            )

    tag = tag_name(source, version)
    kind = tag_kind(repo_root, tag)
    if kind is None:
        if require_tag:
            found.append(f"tag {tag} does not exist in this checkout")
    elif kind != "tag":
        found.append(f"tag {tag} is lightweight; a release tag must be annotated")

    return found


def identifier(repo_root: Path, source: str) -> str:
    """The built document's [meta].identifier. Only valid once problems() is empty."""
    built, problem = document(repo_root / "sources" / source / "dist")
    if problem is not None:
        raise ValueError(problem)
    meta = tomllib.loads(built.read_text(encoding="utf-8"))["meta"]
    return meta["identifier"]


def assets(repo_root: Path, source: str) -> list[Path]:
    """The files a release publishes, in order. Every one is committed, verbatim."""
    source_dir = repo_root / "sources" / source
    built, problem = document(source_dir / "dist")
    if problem is not None:
        raise ValueError(problem)

    paths = [built, source_dir / "dist" / SIDECAR]

    manifest = tomllib.loads((source_dir / "SOURCE.toml").read_text(encoding="utf-8"))
    license_file = manifest.get("license", {}).get("license_file")
    if isinstance(license_file, str):
        paths.append(repo_root / license_file)

    return paths


def main(argv: list[str]) -> int:
    flags = {arg for arg in argv if arg.startswith("--")}
    positional = [arg for arg in argv if not arg.startswith("--")]

    unknown = flags - {"--assets", "--identifier", "--require-tag"}
    if unknown or len(positional) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print(
            "usage: release_check.py <source> <version> "
            "[--assets] [--identifier] [--require-tag]",
            file=sys.stderr,
        )
        return 2

    source, version = positional

    found = problems(REPO_ROOT, source, version, require_tag="--require-tag" in flags)
    if found:
        for problem in found:
            print(f"FAIL release_check {source} {version}: {problem}", file=sys.stderr)
        return 1

    if "--assets" in flags:
        for path in assets(REPO_ROOT, source):
            print(path.relative_to(REPO_ROOT))
        return 0

    if "--identifier" in flags:
        print(identifier(REPO_ROOT, source))
        return 0

    print(f"ok   release_check: {tag_name(source, version)} may be released")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
