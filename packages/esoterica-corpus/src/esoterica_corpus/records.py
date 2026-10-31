"""What a parser yields"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator, Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from esoterica_corpus.input import InputText
    from esoterica_corpus.manifest import Drop, Mapping

type Unit = Hashable
type Value = str | int | list[str] | dict[str, Any]

PARSERS = "esoterica.sources"
EXTRACTORS = "esoterica.extractors"


@dataclass(frozen=True, slots=True)
class Entry:
    """One value in the built document, and the units it came from."""

    target: str  # 'card."major_arcana.00"' | 'group.suits.wands'
    key: str  # 'passages.light' | 'correspondences.number'
    value: Value  # a table is merged into the target key by key
    units: tuple[Unit, ...]


@dataclass(frozen=True, slots=True)
class Consumed:
    """Units read as structure, which carry no value into the document."""

    units: tuple[Unit, ...]
    claim: str  # what the unit selected, carrying no text


type Record = Entry | Consumed


class SourceParser(Protocol):
    def parse(self, text: InputText, mapping: Mapping) -> Iterator[Record]: ...


class Units(Protocol):
    """An input as coverage sees it"""

    def units(self) -> Sequence[Unit]: ...

    def drop_units(self, drop: Drop) -> list[Unit]:
        """The units one drops.toml entry names, in this adapter's terms."""
        ...

    def describe(self, unit: Unit) -> str:
        """A short label for a unit in a failure message."""
        ...


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


class PluginError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Plugin:
    group: str
    name: str
    obj: Any
    distribution: str
    version: str


def installed(group: str, name: str) -> Plugin | None:
    """Find a registered entry point in the installed distributions."""
    for point in entry_points(group=group, name=name):
        dist = point.dist
        return Plugin(
            group=group,
            name=name,
            obj=point.load(),
            distribution=dist.name if dist else "",
            version=dist.version if dist else "",
        )
    return None


# The one lookup every resolution goes through.
lookup: Callable[[str, str], Plugin | None] = installed


def resolve(group: str, name: str) -> Plugin:
    plugin = lookup(group, name)
    if plugin is None:
        raise PluginError(
            f'nothing named {name!r} is registered in entry-point group "{group}"'
        )
    return plugin
