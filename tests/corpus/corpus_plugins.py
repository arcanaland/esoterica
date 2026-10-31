"""The test-only parser and extractor the fixture sources name, and where they are"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from esoterica_corpus.input import InputText
from esoterica_corpus.manifest import Mapping
from esoterica_corpus.records import EXTRACTORS, PARSERS, Consumed, Entry, Plugin, Record

TRUMP = re.compile(r"\ATrump ([0-9]+): .+\Z")
MINOR = re.compile(r"\A(Ace) of (Wands)\Z")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SUPPLIED_INPUT = FIXTURES / "supplied-input" / "fixture.txt"


class FixtureParser:
    """Card headings, `Label: value` lines under them, and group headings."""

    def parse(self, text: InputText, mapping: Mapping) -> Iterator[Record]:
        table = mapping.raw["fixture"]
        target = None
        for number, line in zip(text.units(), text.lines, strict=True):
            if trump := TRUMP.match(line):
                target = f'card."major_arcana.{int(trump.group(1)):02d}"'
            elif minor := MINOR.match(line):
                target = (
                    f'card."minor_arcana.{minor.group(2).lower()}.{minor.group(1).lower()}"'
                )
            elif line in table["groups"]:
                target = table["groups"][line]
            else:
                label, sep, value = line.partition(": ")
                if sep and target and label in table["labels"]:
                    yield Entry(target, table["labels"][label], value, (number,))
                continue
            yield Consumed((number,), target)


class PlainExtractor:
    """Bytes to UTF-8, and nothing else."""

    def extract(self, path: Path) -> str:
        return path.read_bytes().decode("utf-8")


REGISTERED = {
    (PARSERS, "fixture"): FixtureParser,
    (EXTRACTORS, "plain"): PlainExtractor,
}


def lookup(group: str, name: str) -> Plugin | None:
    obj = REGISTERED.get((group, name))
    if obj is None:
        return None
    return Plugin(group, name, obj, distribution="esoterica-tests", version="0")
