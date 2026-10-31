"""A mechanical check that a supplied source's TOML carries none of its input

Every key and string value in SOURCE.toml, mapping.toml and drops.toml is
normalized like the canonical text. One that is MIN_LENGTH characters or longer
and occurs in that text fails. A failure names where, never what.

It doesn't catch paraphrase, text split into strings shorter than MIN_LENGTH,
or anything while the input is absent.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from esoterica_corpus.manifest import read_toml

# A corpus constant, so a source can't loosen its own gate
MIN_LENGTH = 40

FILES = ("SOURCE.toml", "mapping.toml", "drops.toml")

# Bibliographic facts, exempt by where they are rather than how long
EXEMPT = (("work", "title"), ("work", "*", "title"), ("license", "attribution_requested"))


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def strings(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], str]]:
    """Every key and string value, with the key path it sits at."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield (*path, key), key
            yield from strings(inner, (*path, key))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from strings(inner, (*path, str(index)))
    elif isinstance(value, str):
        yield path, value


def exempt(path: tuple[str, ...]) -> bool:
    return any(
        len(rule) == len(path) and all(r in ("*", p) for r, p in zip(rule, path, strict=True))
        for rule in EXEMPT
    )


@dataclass(frozen=True, slots=True)
class Finding:
    file: str
    path: str
    length: int

    def __str__(self) -> str:
        return (
            f"{self.file} at {self.path} holds a {self.length}-character string "
            f"found in the canonical text"
        )


def scan(directory: Path, canonical: str) -> list[Finding]:
    haystack = fold(canonical)
    findings = []
    for name in FILES:
        path = directory / name
        if not path.is_file():
            continue
        for where, text in strings(read_toml(path)):
            if exempt(where):
                continue
            folded = fold(text)
            if len(folded) >= MIN_LENGTH and folded in haystack:
                findings.append(Finding(name, ".".join(where), len(folded)))
    return findings
