#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Account for every line of every source's input

Each input line is `mapped` (the builder used it), `dropped` (drops.toml says
why it was left out) or `unclaimed`. An unclaimed line fails the build.

This is the gate that makes the corpus's central claim checkable. A hand
transcription cannot prove it lost nothing; a build whose every input line is
either in the output or in a list of stated exclusions can.

Usage:
    coverage.py [SOURCE_DIR ...]

With no arguments it globs sources/*/ relative to the repository root.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_GLOB = "sources/*/SOURCE.toml"


def parse_range(spec: str) -> list[int]:
    if "-" in spec:
        first, last = spec.split("-", 1)
        return list(range(int(first), int(last) + 1))
    return [int(spec)]


def input_lines(directory: Path) -> list[str]:
    source = tomllib.loads((directory / "SOURCE.toml").read_text(encoding="utf-8"))
    spec = source["input"]
    text = (directory / spec["path"]).read_bytes().decode(spec["encoding"]["declared"])
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def mapped_lines(directory: Path) -> dict[int, dict]:
    """Ask the source's builder which input line produced what."""
    result = subprocess.run(
        [str(directory / "build.py"), "--mapped-lines"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "build.py --mapped-lines failed")
    return {int(k): v for k, v in json.loads(result.stdout)["lines"].items()}


def dropped_lines(directory: Path, lines: list[str]) -> tuple[dict[int, str], list[str]]:
    """Return each dropped line with its reason, plus any problems with the file."""
    doc = tomllib.loads((directory / "drops.toml").read_text(encoding="utf-8"))
    dropped: dict[int, str] = {}
    problems: list[str] = []

    for entry in doc.get("drop", []):
        reason = entry.get("reason")
        if not reason:
            problems.append(f"a drop entry has no reason: {entry}")
            continue

        if entry.get("rule") == "blank":
            numbers = [n for n, text in enumerate(lines, 1) if not text.strip()]
        elif "lines" in entry:
            numbers = parse_range(entry["lines"])
        else:
            problems.append(f"a drop entry names neither `lines` nor a rule: {entry}")
            continue

        for n in numbers:
            if not 1 <= n <= len(lines):
                problems.append(f"drop names line {n}, which is outside the input")
            elif n in dropped:
                problems.append(f"line {n} is dropped twice")
            else:
                dropped[n] = reason
    return dropped, problems


def cover(directory: Path) -> list[str]:
    """Return a list of coverage failures for one source. Empty means covered."""
    lines = input_lines(directory)
    try:
        mapped = mapped_lines(directory)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        return [f"could not read the builder's claims: {exc}"]

    dropped, problems = dropped_lines(directory, lines)

    both = sorted(set(mapped) & set(dropped))
    for n in both[:10]:
        problems.append(
            f"line {n} is both mapped ({mapped[n]['claim']}) and dropped, so one of "
            f"the two is stale"
        )
    if len(both) > 10:
        problems.append(f"...and {len(both) - 10} more lines claimed twice")

    unclaimed = sorted(set(range(1, len(lines) + 1)) - set(mapped) - set(dropped))
    for n in unclaimed[:20]:
        problems.append(f"line {n} is unclaimed: {lines[n - 1][:60]!r}")
    if len(unclaimed) > 20:
        problems.append(f"...and {len(unclaimed) - 20} more unclaimed lines")

    if not problems:
        structure = sum(1 for v in mapped.values() if v["kind"] == "structure")
        content = len(mapped) - structure
        print(
            f"ok   {directory.relative_to(REPO_ROOT)}  {len(lines)} lines = "
            f"{content} content + {structure} structure + {len(dropped)} dropped"
        )
    return problems


def main(argv: list[str]) -> int:
    if argv:
        directories = [Path(a).resolve() for a in argv]
    else:
        directories = sorted(p.parent for p in REPO_ROOT.glob(SOURCE_GLOB))

    if not directories:
        print(f"coverage: no files matched {SOURCE_GLOB}")
        return 1

    failed = False
    for directory in directories:
        if not (directory / "build.py").is_file():
            print(f"skip {directory.name}: no build.py, nothing to account for")
            continue
        if not (directory / "drops.toml").is_file():
            print(f"FAIL {directory.name}: has a build.py and no drops.toml")
            failed = True
            continue
        for problem in cover(directory):
            failed = True
            print(f"FAIL {directory.name}: {problem}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
