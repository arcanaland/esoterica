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

Deliberately absent: anything needing a whole library, a deck or a graph.

Exits 0 when every source passes with no errors.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from esoterica_spec import grammar, registry

DEFAULT_GLOB = "sources/*/dist/*.toml"


@dataclass(frozen=True, slots=True)
class Finding:
    level: Literal["E", "W"]
    spec: str
    where: str
    message: str


class Report:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def error(self, spec: str, where: str, message: str) -> None:
        self.findings.append(Finding("E", spec, where, message))

    def warn(self, spec: str, where: str, message: str) -> None:
        self.findings.append(Finding("W", spec, where, message))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "E"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "W"]

    def specs(self, level: str | None = None) -> list[str]:
        """The spec citations raised, for tests to assert on instead of prose."""
        return [f.spec for f in self.findings if level is None or f.level == level]


def render(finding: Finding) -> str:
    return f"{finding.message} ({finding.spec})" if finding.spec else finding.message


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def check_card_key(key: str, report: Report) -> None:
    where = f'card."{key}"'
    if ":" in key:
        report.error("3.2", where, f'[card."{key}"] carries a variant suffix')
        return
    if not grammar.is_canonical_id(key):
        if "." not in key:
            report.error(
                "3.5",
                where,
                f"[card.{key}] is a table named {key!r} rather than a card. A "
                f"canonical ID is written as one quoted key",
            )
        else:
            report.error("3.2", where, f'[card."{key}"] is not a well-formed canonical ID')


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------


def check_leaf(where: str, value, slot: str, report: Report) -> None:
    if slot == "passages":
        if isinstance(value, str):
            if not value:
                report.error("5.1", where, f"{where} is an empty string")
        elif isinstance(value, list):
            if not value:
                report.error("5.1", where, f"{where} is an empty array")
            elif not all(isinstance(v, str) and v for v in value):
                report.error(
                    "5.1", where, f"{where} is not an array of non-empty strings"
                )
        else:
            report.error(
                "5.1",
                where,
                f"{where} is a {type(value).__name__}; a passage is a string or "
                f"an array of strings",
            )
        return

    scalars = (str, int, float, bool)
    if isinstance(value, list):
        if not value:
            report.error("6.1", where, f"{where} is an empty array")
        elif not all(isinstance(v, scalars) for v in value):
            report.error("6.1", where, f"{where} is not an array of scalars")
    elif not isinstance(value, scalars):
        report.error(
            "6.1",
            where,
            f"{where} is a {type(value).__name__}; a correspondence is a string, "
            f"integer, float or boolean, or an array of those",
        )


def check_registry(where: str, entry_key: str, slot: str, report: Report) -> None:
    if registry.is_registered(slot, entry_key):
        return
    report.warn(
        "11.4",
        where,
        f"{where} is outside the {slot} registry and is not prefixed x_. It is "
        f"preserved either way, and a later version may claim the name",
    )


def check_slot(where: str, table, slot: str, report: Report) -> None:
    if not isinstance(table, dict):
        report.error("", where, f"{where} is not a table")
        return

    def walk(node: dict, path: list[str]) -> None:
        for key, value in node.items():
            if not grammar.is_custom_name(key):
                report.error(
                    "3.4",
                    where,
                    f"{where}.{'.'.join(path + [key])} is not a well-formed custom name",
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
        report.error("", where, f"{where} is not a table")
        return
    for slot, body in target.items():
        if slot not in registry.SLOTS:
            report.error(
                "4.3",
                f"{where}.{slot}",
                f"{where}.{slot} is in the slot position and is not passages, "
                f"correspondences or cards",
            )
            continue
        if slot == "cards":
            check_cards_slot(f"{where}.cards", body, is_custom_group, report)
            continue
        check_slot(f"{where}.{slot}", body, slot, report)


def check_cards_slot(where: str, value, is_custom_group: bool, report: Report) -> None:
    if not is_custom_group:
        report.error(
            "4.5", where, f"{where} appears on a target that is not group.custom.<name>"
        )
        return
    if not isinstance(value, list) or not value:
        report.error("4.5", where, f"{where} is not a non-empty array")
        return
    seen = set()
    for item in value:
        if not isinstance(item, str):
            report.error("", where, f"{where} carries a non-string member")
        elif ":" in item:
            report.error("4.5", where, f"{where} carries a variant suffix: {item!r}")
        elif not grammar.is_canonical_id(item):
            report.error(
                "4.5", where, f"{where} carries {item!r}, which is not a canonical ID"
            )
        elif item in seen:
            report.error("4.5", where, f"{where} lists {item!r} twice")
        else:
            seen.add(item)


# ---------------------------------------------------------------------------
# Top-level tables
# ---------------------------------------------------------------------------


def check_meta(meta: dict, report: Report) -> None:
    for key in registry.REQUIRED_META_FIELDS:
        if key not in meta:
            report.error("4.1", f"meta.{key}", f"[meta].{key} is required and absent")

    for key in registry.LEGACY_META_KEYS:
        if key in meta:
            report.warn(
                "Appendix B",
                f"meta.{key}",
                f"[meta].{key} is a version 0.1 spelling and is not defined",
            )

    for key, value in meta.items():
        expected = registry.META_FIELDS.get(key)
        if expected == "String" and not isinstance(value, str):
            report.error(
                "4.1",
                f"meta.{key}",
                f"[meta].{key} must be a String, got {type(value).__name__}",
            )
        elif expected == "Array of String" and not (
            isinstance(value, list) and all(isinstance(v, str) for v in value)
        ):
            report.error("4.1", f"meta.{key}", f"[meta].{key} must be an Array of String")

    version = meta.get("schema_version")
    if isinstance(version, str) and not grammar.is_schema_version(version):
        report.error(
            "1.4",
            "meta.schema_version",
            f'[meta].schema_version must be "<major>.<minor>", got {version!r}',
        )

    identifier = meta.get("identifier")
    if isinstance(identifier, str):
        if "#" in identifier:
            report.error("3.1", "meta.identifier", "[meta].identifier carries a fragment")
        elif not grammar.is_qualified_id(identifier, allow_fragment=False):
            report.error(
                "3.1",
                "meta.identifier",
                f"[meta].identifier is not a well-formed qualified identifier: "
                f"{identifier!r}",
            )
        elif identifier.split("/")[1] != "esoterica":
            # 3.1 grades this a MUST and 11.4 grades it a W. A validator
            # implements 11.4; see STATUS finding 1 in the agents KB.
            report.warn(
                "3.1",
                "meta.identifier",
                f"[meta].identifier's first path segment is "
                f"{identifier.split('/')[1]!r} and not `esoterica`",
            )

    published = meta.get("published_date")
    if isinstance(published, str):
        if not grammar.is_published_date(published):
            report.error(
                "4.1.3",
                "meta.published_date",
                f"[meta].published_date is not a published-date: {published!r}",
            )
        elif grammar.parse_published_date(published) is None:
            report.error(
                "4.1.3",
                "meta.published_date",
                f"[meta].published_date names no real date: {published!r}",
            )

    url = meta.get("url")
    if isinstance(url, str) and not grammar.is_absolute_url(url):
        report.error(
            "4.1", "meta.url", f"[meta].url is not an absolute http(s) URL: {url!r}"
        )

    language = meta.get("default_language")
    if isinstance(language, str) and not grammar.is_language_tag(language):
        report.error(
            "7.2",
            "meta.default_language",
            f"[meta].default_language is not a well-formed BCP 47 tag: {language!r}",
        )

    for key in ("redistribution", "derivation"):
        value = meta.get(key)
        if isinstance(value, str) and value not in registry.SHARING:
            report.error(
                "8.3",
                f"meta.{key}",
                f"[meta].{key} must be one of {registry.SHARING}, got {value!r}",
            )

    source_type = meta.get("type")
    if (
        isinstance(source_type, str)
        and source_type not in registry.SOURCE_TYPES
        and not source_type.startswith("x_")
    ):
        report.warn(
            "4.1.1",
            "meta.type",
            f"[meta].type {source_type!r} is outside the registry and is not "
            f"prefixed x_",
        )


def check_group(groups: dict, report: Report) -> None:
    for key, value in groups.items():
        if "/" in key:
            if not grammar.is_qualified_id(key, allow_fragment=True):
                report.error(
                    "3.3",
                    f'group."{key}"',
                    f'[group."{key}"] contains a / and is not a well-formed '
                    f"qualified identifier",
                )
            else:
                check_target(f'group."{key}"', value, False, report)
            continue

        if key not in registry.BUILTIN_FAMILIES:
            report.error(
                "3.3",
                f"group.{key}",
                f"[group.{key}] contains no / and is not one of 4.4's six builtin "
                f"family names",
            )
            continue

        if key == "all":
            check_target("group.all", value, False, report)
            continue

        if not isinstance(value, dict):
            report.error("", f"group.{key}", f"[group.{key}] is not a table")
            continue

        for member, body in value.items():
            where = f"group.{key}.{member}"
            if key in registry.CLOSED_FAMILIES:
                if member not in registry.FAMILY_MEMBERS[key]:
                    report.error(
                        "4.4",
                        where,
                        f"[{where}] is not one of {registry.FAMILY_MEMBERS[key]}",
                    )
                    continue
            elif not (
                member in registry.FAMILY_MEMBERS.get(key, ())
                or grammar.is_custom_name(member)
            ):
                report.error("4.4", where, f"[{where}] is not a well-formed member name")
                continue

            if key == "custom" and isinstance(body, dict) and "cards" not in body:
                report.warn(
                    "4.5", where, f"[{where}] declares no cards slot and names no cards"
                )
            check_target(where, body, key == "custom", report)


def check_app(apps: dict, report: Report) -> None:
    for key in apps:
        if not grammar.is_realm(key):
            report.error(
                "10",
                f'app."{key}"',
                f'[app."{key}"] is not a well-formed realm with two labels or more',
            )


def check(path: Path, explicit: bool = True) -> tuple[Report, bool]:
    """Validate one file. Returns its report and whether it was a source at all."""
    report = Report()
    where = str(path)

    try:
        raw = path.read_bytes()
    except OSError as exc:
        report.error("", where, f"unreadable: {exc.strerror}")
        return report, True

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        report.error("", where, f"not valid UTF-8 at byte {exc.start}")
        return report, True

    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        # 2.2.1: a candidate that does not parse is not a source. Named on the
        # command line it is still worth complaining about.
        if not explicit:
            return report, False
        report.error("", where, f"not valid TOML 1.0.0: {exc}")
        return report, True

    meta = doc.get("meta")
    if not isinstance(meta, dict) or "schema_version" not in meta:
        if not explicit:
            return report, False
        report.error("2.2.1", where, "no [meta] table with a schema_version key")
        return report, True

    check_meta(meta, report)

    for name in registry.LEGACY_TOP_LEVEL_TABLES:
        if name in doc:
            report.warn(
                "Appendix B", name, f"a top-level [{name}] table is a version 0.1 spelling"
            )

    for name in doc:
        if name not in registry.TOP_LEVEL_TABLES:
            report.error("4", name, f"[{name}] is not one of meta, card, group or app")

    cards = doc.get("card") or {}
    if isinstance(cards, dict):
        for key, value in cards.items():
            check_card_key(key, report)
            check_target(f'card."{key}"', value, False, report)
    else:
        report.error("", "card", "[card] is not a table")

    groups = doc.get("group") or {}
    if isinstance(groups, dict):
        check_group(groups, report)
    else:
        report.error("", "group", "[group] is not a table")

    apps = doc.get("app") or {}
    if isinstance(apps, dict):
        check_app(apps, report)
    else:
        report.error("", "app", "[app] is not a table")

    if not cards and not groups:
        report.warn("11.1", where, "the source declares no card and no group target")

    return report, True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="esoterica-validate", description=__doc__.splitlines()[0]
    )
    parser.add_argument("files", nargs="*", type=Path, metavar="FILE")
    args = parser.parse_args(argv)

    explicit = bool(args.files)
    paths = args.files if explicit else sorted(Path().glob(DEFAULT_GLOB))

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
            print(f"WARN {path}: {render(warning)}")
        if report.errors:
            failed = True
            for error in report.errors:
                print(f"FAIL {path}: {render(error)}")
        else:
            note = f" ({len(report.warnings)} warnings)" if report.warnings else ""
            print(f"ok   {path}{note}")

    if sources == 0:
        print("validate: no sources found")
        return 1

    return 1 if failed else 0


def cli() -> None:
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
