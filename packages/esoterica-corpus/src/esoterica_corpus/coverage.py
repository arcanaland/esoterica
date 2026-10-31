"""Account for every unit of a source's input

Each unit is mapped (a record claimed it), dropped (drops.toml says why it was
left out) or unclaimed. An unclaimed unit fails the build.

This is the gate that makes the corpus's central claim checkable. A hand
transcription cannot prove it lost nothing; a build whose every input unit is
either in the output or in a list of stated exclusions can.

Coverage asks the input adapter for its units and never counts lines itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from esoterica_corpus.ledger import Ledger
from esoterica_corpus.manifest import Drops
from esoterica_corpus.records import Unit, Units

# How many of one kind of problem are listed before the rest are summed up
SHOWN = 20


@dataclass
class Coverage:
    total: int = 0
    content: int = 0
    structure: int = 0
    dropped: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        return (
            f"{self.total} units = {self.content} content + {self.structure} structure "
            f"+ {self.dropped} dropped"
        )


def _listed(problems: list[str], items: list[str], what: str) -> None:
    problems.extend(items[:SHOWN])
    if len(items) > SHOWN:
        problems.append(f"...and {len(items) - SHOWN} more {what}")


def dropped_units(adapter: Units, drops: Drops) -> tuple[dict[Unit, str], list[str]]:
    """Each dropped unit with its reason, plus any problems with drops.toml."""
    known = set(adapter.units())
    dropped: dict[Unit, str] = {}
    problems: list[str] = []
    for drop in drops.drop:
        for unit in adapter.drop_units(drop):
            if unit not in known:
                problems.append(f"drops.toml names {unit!r}, which is outside the input")
            elif unit in dropped:
                problems.append(f"{adapter.describe(unit)} is dropped twice")
            else:
                dropped[unit] = drop.reason
    return dropped, problems


def cover(adapter: Units, ledger: Ledger, drops: Drops) -> Coverage:
    units = adapter.units()
    known = set(units)
    dropped, problems = dropped_units(adapter, drops)
    claims = ledger.by_unit

    outside = [
        f"a record claims {u!r}, which is outside the input" for u in claims if u not in known
    ]
    _listed(problems, outside, "claims outside the input")

    both = [
        f"{adapter.describe(u)} is both mapped ({claims[u].claim}) and dropped, "
        f"so one of the two is stale"
        for u in units
        if u in claims and u in dropped
    ]
    _listed(problems, both, "units claimed twice")

    unclaimed = [
        f"{adapter.describe(u)} is unclaimed"
        for u in units
        if u not in claims and u not in dropped
    ]
    _listed(problems, unclaimed, "unclaimed units")

    structure = sum(1 for c in claims.values() if c.kind == "structure")
    return Coverage(
        total=len(units),
        content=len(claims) - structure,
        structure=structure,
        dropped=len(dropped),
        problems=problems,
    )
