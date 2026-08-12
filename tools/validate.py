#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check built esoterica sources against a deliberately shallow implementation of the spec

    E  the file is valid TOML 1.0.0 encoded as UTF-8 and carries a [meta] table
    E  [meta] carries schema_version, identifier, name and license
    E  [meta].schema_version has the form "<major>.<minor>"

Usage:
    validate.py [FILE ...]

With no arguments it globs sources/*/dist/*.toml relative to the repository root.

Exits 0 when every file passes.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOB = "sources/*/dist/*.toml"

REQUIRED_META_KEYS = ("schema_version", "identifier", "name", "license")
SCHEMA_VERSION_RE = re.compile(r"\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def check(path: Path) -> list[str]:
    """Return a list of rule violations for one file. Empty means it passed."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [f"unreadable: {exc.strerror}"]

    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"not valid UTF-8 at byte {exc.start}"]

    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"not valid TOML 1.0.0: {exc}"]

    meta = doc.get("meta")
    if meta is None:
        return ["no [meta] table"]
    if not isinstance(meta, dict):
        return ["[meta] is not a table"]

    errors = []
    for key in REQUIRED_META_KEYS:
        if key not in meta:
            errors.append(f"[meta].{key} is required and absent")
        elif not isinstance(meta[key], str):
            errors.append(
                f"[meta].{key} must be a String, got {type(meta[key]).__name__}"
            )

    version = meta.get("schema_version")
    if isinstance(version, str) and not SCHEMA_VERSION_RE.match(version):
        errors.append(
            f"[meta].schema_version must be \"<major>.<minor>\", got {version!r}"
        )

    return errors


def main(argv: list[str]) -> int:
    if argv:
        paths = [Path(a) for a in argv]
    else:
        paths = sorted(REPO_ROOT.glob(DEFAULT_GLOB))

    if not paths:
        print(f"validate: no files matched {DEFAULT_GLOB}")
        # TODO:: This should be an error as soon as we implement the first source
        #return 1
        return 0

    failed = False
    for path in paths:
        errors = check(path)
        if errors:
            failed = True
            for error in errors:
                print(f"FAIL {path}: {error}")
        else:
            print(f"ok   {path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
