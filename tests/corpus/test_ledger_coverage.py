"""The ledger and coverage, once over line numbers and once over string units"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from esoterica_corpus.coverage import cover
from esoterica_corpus.input import InputText
from esoterica_corpus.ledger import Ledger, LedgerError
from esoterica_corpus.manifest import Drop, Drops
from esoterica_corpus.records import Consumed, Entry


@dataclass(frozen=True)
class Keyed:
    """A test-only adapter whose units are record ids, not lines."""

    names: tuple[str, ...]

    def units(self):
        return self.names

    def drop_units(self, drop: Drop):
        assert drop.lines is not None
        return drop.lines.split(",")

    def describe(self, unit):
        return f"record {unit}"


TEXT = InputText(["Trump 0: The Fool", "Light: Out.", "", "Colophon"])
KEYED = Keyed(("fool", "fool/light", "spacer", "colophon"))


@pytest.fixture(params=["lines", "strings"])
def case(request):
    """An adapter, its four units, and a drop of the last two in its own terms."""
    if request.param == "lines":
        return TEXT, (1, 2, 3, 4), [Drop(rule="blank", reason="r"), Drop(lines="4", reason="r")]
    return KEYED, KEYED.names, [Drop(lines="spacer,colophon", reason="r")]


def records(units):
    heading, light, *_ = units
    return [
        Consumed((heading,), 'card."major_arcana.00"'),
        Entry('card."major_arcana.00"', "passages.light", "Out.", (light,)),
    ]


def test_every_unit_accounted_for(case):
    adapter, units, drops = case
    result = cover(adapter, Ledger.of(records(units)), Drops(schema=1, drop=drops))
    assert result.ok, result.problems
    assert (result.total, result.content, result.structure, result.dropped) == (4, 1, 1, 2)


def test_a_double_claim_names_both_claims(case):
    _, units, _ = case
    clash = Entry('card."major_arcana.00"', "passages.shadow", "x", (units[1],))
    with pytest.raises(LedgerError) as caught:
        Ledger.of([*records(units), clash])
    message = str(caught.value)
    assert repr(units[1]) in message
    assert 'card."major_arcana.00".passages.light' in message
    assert 'card."major_arcana.00".passages.shadow' in message


def test_a_record_with_no_units_is_refused():
    with pytest.raises(LedgerError, match="claims no input unit"):
        Ledger.of([Entry('card."major_arcana.00"', "passages.light", "x", ())])


def test_an_unclaimed_unit_fails(case):
    adapter, units, drops = case
    result = cover(adapter, Ledger.of(records(units)[:1]), Drops(schema=1, drop=drops))
    assert not result.ok
    assert result.problems == [f"{adapter.describe(units[1])} is unclaimed"]


def test_mapped_and_dropped_fails(case):
    adapter, units, drops = case
    ledger = Ledger.of([*records(units), Consumed((units[3],), "colophon")])
    result = cover(adapter, ledger, Drops(schema=1, drop=drops))
    assert len(result.problems) == 1
    assert "both mapped (colophon) and dropped" in result.problems[0]


def test_dropped_twice_fails(case):
    adapter, units, drops = case
    result = cover(adapter, Ledger.of(records(units)), Drops(schema=1, drop=drops + drops))
    assert any("dropped twice" in p for p in result.problems)


def test_a_claim_outside_the_input_fails(case):
    adapter, units, drops = case
    stray = 99 if isinstance(units[0], int) else "elsewhere"
    ledger = Ledger.of([*records(units), Consumed((stray,), "stray")])
    result = cover(adapter, ledger, Drops(schema=1, drop=drops))
    assert any("outside the input" in p for p in result.problems)


def test_a_drop_outside_the_input_fails():
    drops = Drops(schema=1, drop=[Drop(lines="3-5", reason="r")])
    result = cover(TEXT, Ledger.of(records((1, 2))), drops)
    assert "drops.toml names 5, which is outside the input" in result.problems
