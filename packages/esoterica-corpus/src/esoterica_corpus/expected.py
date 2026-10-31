"""Expected counts for output"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class ExpectedError(Exception):
    pass


def leaves(table: dict[str, Any], prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    for key, value in table.items():
        if isinstance(value, dict):
            yield from leaves(value, (*prefix, key))
        else:
            yield (*prefix, key)


def matches(pattern: str, path: tuple[str, ...]) -> bool:
    parts = tuple(pattern.split("."))
    if parts[-1] == "*":
        head = parts[:-1]
        return len(path) > len(head) and path[: len(head)] == head
    return path == parts


def targets(document: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """The card tables and the group tables of an assembled document."""
    cards = list(document.get("card", {}).values())
    groups = []
    for family in document.get("group", {}).values():
        groups.extend(family.values())
    return cards, groups


def measure(document: dict[str, Any], expected: dict[str, int]) -> dict[str, int]:
    cards, groups = targets(document)
    paths = [path for target in cards + groups for path in leaves(target)]
    counts = {}
    for key in expected:
        if key == "cards":
            counts[key] = len(cards)
        elif key == "groups":
            counts[key] = len(groups)
        else:
            counts[key] = sum(1 for path in paths if matches(key, path))
    return counts


def check(document: dict[str, Any], expected: dict[str, int] | None) -> dict[str, int]:
    """The measured counts, if every one is as expected."""
    if expected is None:
        raise ExpectedError("mapping.toml has no [expected] table, and absence is not a pass")
    if not expected:
        raise ExpectedError("mapping.toml's [expected] table is empty")
    counts = measure(document, expected)
    wrong = [
        f"    {key}: expected {want}, built {counts[key]}"
        for key, want in expected.items()
        if counts[key] != want
    ]
    if wrong:
        raise ExpectedError(
            "the build did not reproduce the input's counts:\n" + "\n".join(wrong)
        )
    return counts
