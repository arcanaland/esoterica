"""DECK.md 3.5's productions, and the predicates over them."""

from __future__ import annotations

import re
from datetime import date

LABEL = r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
SEGMENT = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"

REALM_RE = re.compile(rf"\A{LABEL}(?:\.{LABEL})+\Z")
QUALIFIED_NO_FRAGMENT_RE = re.compile(rf"\A{LABEL}(?:\.{LABEL})+/{SEGMENT}(?:/{SEGMENT})*\Z")
QUALIFIED_RE = re.compile(
    rf"\A{LABEL}(?:\.{LABEL})+/{SEGMENT}(?:/{SEGMENT})*(?:#[a-z0-9._:-]+)?\Z"
)
CUSTOM_NAME_RE = re.compile(r"\A[a-z_][a-z0-9_]*\Z")
SCHEMA_VERSION_RE = re.compile(r"\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
PUBLISHED_DATE_RE = re.compile(r"\A([0-9]{4})(?:-([0-9]{2})(?:-([0-9]{2}))?)?\Z")
LANGUAGE_TAG_RE = re.compile(r"\A[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*\Z")
URL_RE = re.compile(r"\Ahttps?://[^\s]+\Z")

CANONICAL_SUITS = ("wands", "cups", "swords", "pentacles")
CANONICAL_RANKS = (
    "ace",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "page",
    "knight",
    "queen",
    "king",
)


def is_custom_name(value: str) -> bool:
    return bool(CUSTOM_NAME_RE.match(value))


def is_realm(value: str) -> bool:
    return bool(REALM_RE.match(value))


def is_qualified_id(value: str, *, allow_fragment: bool) -> bool:
    pattern = QUALIFIED_RE if allow_fragment else QUALIFIED_NO_FRAGMENT_RE
    return bool(pattern.match(value))


def is_schema_version(value: str) -> bool:
    return bool(SCHEMA_VERSION_RE.match(value))


def is_language_tag(value: str) -> bool:
    return bool(LANGUAGE_TAG_RE.match(value))


def is_absolute_url(value: str) -> bool:
    return bool(URL_RE.match(value))


def is_canonical_id(key: str) -> bool:
    parts = key.split(".")
    if parts[0] == "major_arcana" and len(parts) == 2:
        return bool(re.fullmatch(r"[0-9]{2}", parts[1])) or is_custom_name(parts[1])
    if parts[0] == "minor_arcana" and len(parts) == 3:
        return all(
            part in canonical or is_custom_name(part)
            for part, canonical in (
                (parts[1], CANONICAL_SUITS),
                (parts[2], CANONICAL_RANKS),
            )
        )
    return False


def is_published_date(value: str) -> bool:
    """The shape alone. 4.1.3 grades a malformed date and an unreal one apart."""
    return bool(PUBLISHED_DATE_RE.match(value))


def parse_published_date(value: str) -> date | None:
    """The date a published-date names, or None when it names none.

    A year or a year-month is completed to the first of the period, so this is a
    real-date test rather than a value the caller should keep.
    """
    match = PUBLISHED_DATE_RE.match(value)
    if not match:
        return None
    year, month, day = (int(g) if g else None for g in match.groups())
    try:
        return date(year, month or 1, day or 1)
    except ValueError:
        return None
