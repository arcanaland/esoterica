#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Verify every vendored source input against its sha256

Exits 0 when every vendored input matches.
"""

from __future__ import annotations

import hashlib
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_GLOB = "sources/*/SOURCE.toml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(manifest: Path) -> list[str]:
    """Return a list of problems with one source. Empty means it verified."""
    try:
        doc = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [f"unreadable manifest: {exc}"]

    spec = doc.get("input")
    if not isinstance(spec, dict):
        return ["no [input] table"]

    kind = spec.get("kind")
    if kind == "fetched":
        print(f"skip {manifest.parent.name}: kind = \"fetched\", no local bytes")
        return []
    if kind != "vendored":
        return [f"[input].kind must be \"vendored\" or \"fetched\", got {kind!r}"]

    rel = spec.get("path")
    if not isinstance(rel, str):
        return ["[input].path is required for a vendored source"]

    path = manifest.parent / rel
    if not path.is_file():
        return [f"[input].path does not exist: {path}"]

    problems = []

    expected = spec.get("sha256")
    actual = sha256(path)
    if not isinstance(expected, str):
        problems.append("[input].sha256 is required")
    elif actual != expected:
        problems.append(f"sha256 mismatch: recorded {expected}, found {actual}")

    size = path.stat().st_size
    if "bytes" in spec and spec["bytes"] != size:
        problems.append(f"byte length mismatch: recorded {spec['bytes']}, found {size}")

    if "lines" in spec:
        count = path.read_bytes().count(b"\n")
        if spec["lines"] != count:
            problems.append(f"line count mismatch: recorded {spec['lines']}, found {count}")

    if not problems:
        print(f"ok   {path.relative_to(REPO_ROOT)}  {actual}")

    return problems


def main() -> int:
    manifests = sorted(REPO_ROOT.glob(SOURCE_GLOB))
    if not manifests:
        print(f"verify_input: no files matched {SOURCE_GLOB}")
        # TODO:: This should be an error as soon as we implement the first source
        #return 1
        return 0

    failed = False
    for manifest in manifests:
        for problem in verify(manifest):
            failed = True
            print(f"FAIL {manifest.relative_to(REPO_ROOT)}: {problem}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
