#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check built esoterica sources against a deliberately shallow reading of the spec

Only rules that are local, syntactic and cheap, from ESOTERICA.md 11.4:

    E  the file is valid TOML 1.0.0 encoded as UTF-8 and carries a [meta] table
    E  [meta] carries schema_version, identifier, name and license
    E  every key 4.1 defines carries a value of its declared type
    E  [meta].schema_version has the form "<major>.<minor>"
    E  [meta].identifier is a well-formed qualified identifier with no fragment
    W  [meta].identifier's first path segment is `esoterica`
    E  [meta].published_date is a published-date string naming a real date
    E  [meta].url is absolute with an http or https scheme
    E  [meta].default_language is a well-formed BCP 47 tag
    E  redistribution and derivation are `full`, `none` or `unstated`
    W  a [meta].type outside 4.1.1's registry that is not prefixed x_
    E  every top-level table is meta, card, group or app
    E  every key under `card` is a canonical ID, written as one key, unsuffixed
    E  every key directly under `group` is a qualified identifier or a family
    E  a builtin family other than `all` takes exactly one admissible member
    E  the segment in a target's slot position is passages, correspondences or cards
    E  a `cards` slot appears only on group.custom.<name> and lists canonical IDs
    E  every entry key part beneath a slot is a well-formed custom name
    E  every leaf beneath `passages` is a non-empty string or array of them
    E  every leaf beneath `correspondences` is a scalar or array of scalars
    W  a passage or correspondence key outside the registries, unprefixed
    W  a source declaring no card and no group target
    E  every [app] subtable key is a well-formed realm
    W  a top-level `passages` table, or a [meta].id key

Deliberately absent: anything needing a whole library, a deck or a graph. Cross-
source shadowing, group membership and card existence are an application's, and
in this project libarcana's, permanently.

Usage:
    validate.py [FILE ...]

With no arguments it globs sources/*/dist/*.toml relative to the repository
root and, per 2.2.1, passes over candidates that are not sources.

Exits 0 when every source passes with no errors.
"""

from __future__ import annotations

import re
import sys
import tomllib
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOB = "sources/*/dist/*.toml"

# -- grammar, from DECK.md 3.5 ----------------------------------------------

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

CANONICAL_SUITS = ("wands", "cups", "swords", "pentacles")
CANONICAL_RANKS = (
    "ace", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "page", "knight", "queen", "king",
)

BUILTIN_FAMILIES = ("all", "arcana", "classes", "suits", "ranks", "custom")
FAMILY_MEMBERS = {
    "arcana": ("major", "minor"),
    "classes": ("pip", "court"),
}

SLOTS = ("passages", "correspondences", "cards")

# -- registries, from 4.1, 4.1.1, 5.2 and 6.2 -------------------------------

META_TYPES = {
    "str": (
        "schema_version", "identifier", "name", "license", "type", "version",
        "author", "publisher", "published_date", "isbn", "url", "citation",
        "description", "default_language", "translates", "copyright",
        "attribution", "rights_status", "redistribution", "derivation",
    ),
    "list": ("tags",),
}
SOURCE_TYPES = {
    "book", "chapter", "article", "webpage", "manuscript", "document", "tradition",
}
PASSAGE_KEYS = {
    "text", "keywords", "theme", "light", "shadow", "questions", "affirmation",
    "story", "personality", "approach",
    "advice.relationships", "advice.work", "advice.spirituality",
    "advice.personal_growth", "advice.fortune_telling", "advice.timing",
}
CORRESPONDENCE_KEYS = {
    "element", "number", "astrology", "planet", "zodiac", "decan", "season",
    "direction", "color", "archetype", "hebrew_letter", "hebrew_letter_meaning",
    "hebrew_letter_value",
}
SHARING = ("full", "none", "unstated")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def is_canonical_id(key: str) -> bool:
    parts = key.split(".")
    if parts[0] == "major_arcana" and len(parts) == 2:
        return bool(re.fullmatch(r"[0-9]{2}", parts[1])) or bool(
            CUSTOM_NAME_RE.match(parts[1])
        )
    if parts[0] == "minor_arcana" and len(parts) == 3:
        return all(
            part in canonical or CUSTOM_NAME_RE.match(part)
            for part, canonical in (
                (parts[1], CANONICAL_SUITS),
                (parts[2], CANONICAL_RANKS),
            )
        )
    return False


def check_card_key(key: str, report: Report) -> None:
    if ":" in key:
        report.error(f'[card."{key}"] carries a variant suffix (3.2)')
        return
    if not is_canonical_id(key):
        if "." not in key:
            report.error(
                f"[card.{key}] is a table named {key!r} rather than a card. A "
                f"canonical ID is written as one quoted key (3.5)"
            )
        else:
            report.error(f'[card."{key}"] is not a well-formed canonical ID (3.2)')


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------


def check_leaf(where: str, value, slot: str, report: Report) -> None:
    if slot == "passages":
        if isinstance(value, str):
            if not value:
                report.error(f"{where} is an empty string (5.1)")
        elif isinstance(value, list):
            if not value:
                report.error(f"{where} is an empty array (5.1)")
            elif not all(isinstance(v, str) and v for v in value):
                report.error(f"{where} is not an array of non-empty strings (5.1)")
        else:
            report.error(
                f"{where} is a {type(value).__name__}; a passage is a string or "
                f"an array of strings (5.1)"
            )
        return

    scalars = (str, int, float, bool)
    if isinstance(value, list):
        if not value:
            report.error(f"{where} is an empty array (6.1)")
        elif not all(isinstance(v, scalars) for v in value):
            report.error(f"{where} is not an array of scalars (6.1)")
    elif not isinstance(value, scalars):
        report.error(
            f"{where} is a {type(value).__name__}; a correspondence is a string, "
            f"integer, float or boolean, or an array of those (6.1)"
        )


def check_registry(where: str, entry_key: str, slot: str, report: Report) -> None:
    parts = entry_key.split(".")
    if slot == "passages":
        registered = entry_key in PASSAGE_KEYS or (
            len(parts) == 2 and parts[0] == "symbols"
        )
    else:
        registered = entry_key in CORRESPONDENCE_KEYS
    if registered or any(part.startswith("x_") for part in parts):
        return
    report.warn(
        f"{where} is outside the {slot} registry and is not prefixed x_. It is "
        f"preserved either way, and a later version may claim the name (11.4)"
    )


def check_slot(where: str, table, slot: str, report: Report) -> None:
    if not isinstance(table, dict):
        report.error(f"{where} is not a table")
        return

    def walk(node: dict, path: list[str]) -> None:
        for key, value in node.items():
            if not CUSTOM_NAME_RE.match(key):
                report.error(
                    f"{where}.{'.'.join(path + [key])} is not a well-formed custom "
                    f"name (3.4)"
                )
                continue
            if isinstance(value, dict):
                walk(value, path + [key])
            else:
                entry_key = ".".join(path + [key])
                check_leaf(f"{where}.{entry_key}", value, slot, report)
                check_registry(f"{where}.{entry_key}", entry_key, slot, report)

    walk(table, [])


def check_target(where: str, target, is_custom_group: bool, report: Report) -> None:
    if not isinstance(target, dict):
        report.error(f"{where} is not a table")
        return
    for slot, body in target.items():
        if slot not in SLOTS:
            report.error(
                f"{where}.{slot} is in the slot position and is not passages, "
                f"correspondences or cards (4.3)"
            )
            continue
        if slot == "cards":
            check_cards_slot(f"{where}.cards", body, is_custom_group, report)
            continue
        check_slot(f"{where}.{slot}", body, slot, report)


def check_cards_slot(where: str, value, is_custom_group: bool, report: Report) -> None:
    if not is_custom_group:
        report.error(f"{where} appears on a target that is not group.custom.<name> (4.5)")
        return
    if not isinstance(value, list) or not value:
        report.error(f"{where} is not a non-empty array (4.5)")
        return
    seen = set()
    for item in value:
        if not isinstance(item, str):
            report.error(f"{where} carries a non-string member")
        elif ":" in item:
            report.error(f"{where} carries a variant suffix: {item!r} (4.5)")
        elif not is_canonical_id(item):
            report.error(f"{where} carries {item!r}, which is not a canonical ID (4.5)")
        elif item in seen:
            report.error(f"{where} lists {item!r} twice (4.5)")
        else:
            seen.add(item)


# ---------------------------------------------------------------------------
# Top-level tables
# ---------------------------------------------------------------------------


def check_meta(meta: dict, report: Report) -> None:
    for key in ("schema_version", "identifier", "name", "license"):
        if key not in meta:
            report.error(f"[meta].{key} is required and absent (4.1)")

    if "id" in meta:
        report.warn("[meta].id is a version 0.1 spelling and is not defined (Appendix B)")

    for key, value in meta.items():
        if key in META_TYPES["str"] and not isinstance(value, str):
            report.error(
                f"[meta].{key} must be a String, got {type(value).__name__} (4.1)"
            )
        elif key in META_TYPES["list"] and not (
            isinstance(value, list) and all(isinstance(v, str) for v in value)
        ):
            report.error(f"[meta].{key} must be an Array of String (4.1)")

    version = meta.get("schema_version")
    if isinstance(version, str) and not SCHEMA_VERSION_RE.match(version):
        report.error(f'[meta].schema_version must be "<major>.<minor>", got {version!r}')

    identifier = meta.get("identifier")
    if isinstance(identifier, str):
        if "#" in identifier:
            report.error("[meta].identifier carries a fragment (3.1)")
        elif not QUALIFIED_NO_FRAGMENT_RE.match(identifier):
            report.error(
                f"[meta].identifier is not a well-formed qualified identifier: "
                f"{identifier!r} (3.1)"
            )
        elif identifier.split("/")[1] != "esoterica":
            report.warn(
                f"[meta].identifier's first path segment is "
                f"{identifier.split('/')[1]!r} and not `esoterica` (3.1)"
            )

    published = meta.get("published_date")
    if isinstance(published, str):
        match = PUBLISHED_DATE_RE.match(published)
        if not match:
            report.error(
                f"[meta].published_date is not a published-date: {published!r} (4.1.3)"
            )
        else:
            year, month, day = (int(g) if g else None for g in match.groups())
            try:
                date(year, month or 1, day or 1)
            except ValueError:
                report.error(
                    f"[meta].published_date names no real date: {published!r} (4.1.3)"
                )

    url = meta.get("url")
    if isinstance(url, str) and not re.match(r"\Ahttps?://[^\s]+\Z", url):
        report.error(f"[meta].url is not an absolute http(s) URL: {url!r} (4.1)")

    language = meta.get("default_language")
    if isinstance(language, str) and not LANGUAGE_TAG_RE.match(language):
        report.error(
            f"[meta].default_language is not a well-formed BCP 47 tag: "
            f"{language!r} (7.2)"
        )

    for key in ("redistribution", "derivation"):
        value = meta.get(key)
        if isinstance(value, str) and value not in SHARING:
            report.error(f"[meta].{key} must be one of {SHARING}, got {value!r} (8.3)")

    source_type = meta.get("type")
    if (
        isinstance(source_type, str)
        and source_type not in SOURCE_TYPES
        and not source_type.startswith("x_")
    ):
        report.warn(
            f"[meta].type {source_type!r} is outside the registry and is not "
            f"prefixed x_ (4.1.1)"
        )


def check_group(groups: dict, report: Report) -> None:
    for key, value in groups.items():
        if "/" in key:
            if not QUALIFIED_RE.match(key):
                report.error(
                    f'[group."{key}"] contains a / and is not a well-formed '
                    f"qualified identifier (3.3)"
                )
            else:
                check_target(f'group."{key}"', value, False, report)
            continue

        if key not in BUILTIN_FAMILIES:
            report.error(
                f"[group.{key}] contains no / and is not one of the six builtin "
                f"family names (3.3, 4.4)"
            )
            continue

        if key == "all":
            check_target("group.all", value, False, report)
            continue

        if not isinstance(value, dict):
            report.error(f"[group.{key}] is not a table")
            continue

        for member, body in value.items():
            where = f"group.{key}.{member}"
            if key in FAMILY_MEMBERS:
                if member not in FAMILY_MEMBERS[key]:
                    report.error(
                        f"[{where}] is not one of {FAMILY_MEMBERS[key]} (4.4)"
                    )
                    continue
            elif not (
                member in (CANONICAL_SUITS if key == "suits" else CANONICAL_RANKS)
                or CUSTOM_NAME_RE.match(member)
            ):
                report.error(f"[{where}] is not a well-formed member name (4.4)")
                continue

            if key == "custom" and isinstance(body, dict) and "cards" not in body:
                report.warn(f"[{where}] declares no cards slot and names no cards (4.5)")
            check_target(where, body, key == "custom", report)


def check_app(apps: dict, report: Report) -> None:
    for key in apps:
        if not REALM_RE.match(key):
            report.error(
                f'[app."{key}"] is not a well-formed realm with two labels or '
                f"more (10)"
            )


def check(path: Path, explicit: bool) -> tuple[Report, bool]:
    """Validate one file. Returns its report and whether it was a source at all."""
    report = Report()

    try:
        raw = path.read_bytes()
    except OSError as exc:
        report.error(f"unreadable: {exc.strerror}")
        return report, True

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        report.error(f"not valid UTF-8 at byte {exc.start}")
        return report, True

    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        # 2.2.1: a candidate that does not parse is not a source. Named on the
        # command line it is still worth complaining about.
        if not explicit:
            return report, False
        report.error(f"not valid TOML 1.0.0: {exc}")
        return report, True

    meta = doc.get("meta")
    if not isinstance(meta, dict) or "schema_version" not in meta:
        if not explicit:
            return report, False
        report.error("no [meta] table with a schema_version key (2.2.1)")
        return report, True

    check_meta(meta, report)

    if "passages" in doc:
        report.warn(
            "a top-level [passages] table is a version 0.1 spelling (Appendix B)"
        )

    for name, value in doc.items():
        if name not in ("meta", "card", "group", "app"):
            report.error(f"[{name}] is not one of meta, card, group or app (4)")

    cards = doc.get("card") or {}
    if isinstance(cards, dict):
        for key, value in cards.items():
            check_card_key(key, report)
            check_target(f'card."{key}"', value, False, report)
    else:
        report.error("[card] is not a table")

    groups = doc.get("group") or {}
    if isinstance(groups, dict):
        check_group(groups, report)
    else:
        report.error("[group] is not a table")

    apps = doc.get("app") or {}
    if isinstance(apps, dict):
        check_app(apps, report)
    else:
        report.error("[app] is not a table")

    if not cards and not groups:
        report.warn("the source declares no card and no group target (11.1)")

    return report, True


def main(argv: list[str]) -> int:
    explicit = bool(argv)
    paths = [Path(a) for a in argv] if argv else sorted(REPO_ROOT.glob(DEFAULT_GLOB))

    if not paths:
        print(f"validate: no files matched {DEFAULT_GLOB}")
        return 1

    failed = False
    sources = 0
    for path in paths:
        report, is_source = check(path, explicit)
        if not is_source:
            print(f"skip {path}: not a source (2.2.1)")
            continue
        sources += 1
        for warning in report.warnings:
            print(f"WARN {path}: {warning}")
        if report.errors:
            failed = True
            for error in report.errors:
                print(f"FAIL {path}: {error}")
        else:
            note = f" ({len(report.warnings)} warnings)" if report.warnings else ""
            print(f"ok   {path}{note}")

    if sources == 0:
        print("validate: no sources found")
        return 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
