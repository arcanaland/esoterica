"""Records to an esoterica document, in a fixed key order"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from esoterica_corpus.manifest import Mapping, Output, SourceManifest
from esoterica_corpus.records import Entry, Value

CARD_TARGET = re.compile(r'\Acard\."([^"]+)"\Z')
SUITS = ["wands", "cups", "swords", "pentacles"]
RANKS = [
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
]


class DocumentError(Exception):
    pass


def put(table: dict, dotted: str, value: Value) -> None:
    """Set one value. A table value is merged in key by key, and nothing is set twice."""
    parts = dotted.split(".")
    for part in parts[:-1]:
        table = table.setdefault(part, {})
        if not isinstance(table, dict):
            raise DocumentError(f"{dotted} passes through a value that is not a table")
    last = parts[-1]
    if isinstance(value, dict):
        if not value:
            raise DocumentError(f"{dotted} is set to an empty table")
        inside = table.setdefault(last, {})
        if not isinstance(inside, dict):
            raise DocumentError(f"{dotted} is set twice")
        for key, inner in value.items():
            put(inside, key, inner)
        return
    if last in table:
        raise DocumentError(f"{dotted} is set twice")
    table[last] = value


def collect(entries: Iterable[Entry]) -> tuple[dict[str, dict], dict[str, dict]]:
    """Cards by id and groups by target, in the order the records arrived."""
    cards: dict[str, dict] = {}
    groups: dict[str, dict] = {}
    for entry in entries:
        card = CARD_TARGET.match(entry.target)
        if card:
            table = cards.setdefault(card.group(1), {})
        elif entry.target.startswith("group.") and entry.target.count(".") == 2:
            table = groups.setdefault(entry.target, {})
        else:
            raise DocumentError(f"{entry.target!r} is not a card or group target")
        try:
            put(table, entry.key, entry.value)
        except DocumentError as exc:
            raise DocumentError(f"{entry.target}: {exc}") from None
    return cards, groups


def card_sort_key(card_id: str) -> tuple:
    parts = card_id.split(".")
    try:
        if parts[0] == "major_arcana" and len(parts) == 2:
            return (0, int(parts[1]), 0)
        if parts[0] == "minor_arcana" and len(parts) == 3:
            return (1, SUITS.index(parts[1]), RANKS.index(parts[2]))
    except ValueError:
        pass
    raise DocumentError(f"{card_id!r} is not a card id this pipeline can order")


def ordered(table: dict, order: list[str], what: str) -> dict:
    unknown = set(table) - set(order)
    if unknown:
        raise DocumentError(
            f"mapping.toml's {what} order omits {sorted(unknown)}, so the built "
            f"file's key order would not be fixed"
        )
    return {key: table[key] for key in order if key in table}


def ordered_target(target: dict, order: Output) -> dict:
    unknown = set(target) - {"passages", "symbols", "correspondences"}
    if unknown:
        raise DocumentError(
            f"a target holds {sorted(unknown)}, which this pipeline can't order"
        )
    out: dict = {}
    passages = target.get("passages") or {}
    if passages:
        out["passages"] = ordered(passages, order.passage_order, "passage")
        advice = out["passages"].get("advice")
        if advice:
            out["passages"]["advice"] = ordered(advice, order.advice_order, "advice")
    symbols = target.get("symbols") or {}
    if symbols:
        # Symbol keys are the author's, so they keep the book's order.
        out["symbols"] = symbols
    correspondences = target.get("correspondences") or {}
    if correspondences:
        out["correspondences"] = ordered(
            correspondences, order.correspondence_order, "correspondence"
        )
    return out


def assemble(meta: dict[str, Any], entries: Iterable[Entry], order: Output) -> dict:
    cards, groups = collect(entries)
    out: dict = {"meta": meta}

    out["card"] = {
        card_id: ordered_target(cards[card_id], order)
        for card_id in sorted(cards, key=card_sort_key)
    }

    unplaced = set(groups) - set(order.group_order)
    if unplaced:
        raise DocumentError(f"mapping.toml's group_order omits {sorted(unplaced)}")
    tables: dict = {}
    for target in order.group_order:
        if target not in groups:
            continue
        table = tables
        for part in target.split(".")[1:]:
            table = table.setdefault(part, {})
        table.update(ordered_target(groups[target], order))
    out["group"] = tables
    return out


def meta(source: SourceManifest, mapping: Mapping) -> dict[str, Any]:
    """mapping.toml's [meta], with the identifier SOURCE.toml mints."""
    fixed = dict(mapping.meta)
    if "identifier" in fixed:
        raise DocumentError("mapping.toml's [meta] sets identifier, which is SOURCE.toml's")
    if fixed.get("license", source.license.spdx) != source.license.spdx:
        raise DocumentError("mapping.toml's [meta].license disagrees with SOURCE.toml's spdx")
    out = {"schema_version": fixed.pop("schema_version", None), "identifier": source.identifier}
    if out["schema_version"] is None:
        raise DocumentError("mapping.toml's [meta] has no schema_version")
    out.update(fixed)
    return out


def check_rights(meta: dict[str, Any]) -> None:
    """A supplied input may not be redistributed or derived from (ESOTERICA.md 8.3)."""
    wrong = [
        f"[meta].{key} is {meta.get(key)!r}"
        for key in ("redistribution", "derivation")
        if meta.get(key) != "none"
    ]
    if wrong:
        raise DocumentError(
            "a supplied source must set redistribution and derivation to "
            '"none": ' + ", ".join(wrong)
        )
