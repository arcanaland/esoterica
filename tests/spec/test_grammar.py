from __future__ import annotations

from datetime import date

import pytest
from esoterica_spec import grammar, registry


@pytest.mark.parametrize(
    "value, expected",
    [
        ("text", True),
        ("x_upright", True),
        ("_private", True),
        ("advice2", True),
        ("Text", False),
        ("advice-work", False),
        ("2advice", False),
        ("", False),
    ],
)
def test_is_custom_name(value, expected):
    assert grammar.is_custom_name(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [("land.arcana", True), ("a.b.c", True), ("land", False), ("Land.Arcana", False)],
)
def test_is_realm(value, expected):
    assert grammar.is_realm(value) is expected


@pytest.mark.parametrize(
    "value, with_fragment, without_fragment",
    [
        ("land.arcana.dev/esoterica/foo", True, True),
        ("land.arcana.dev/esoterica/foo#frag", True, False),
        ("land.arcana.dev/esoterica_foo", False, False),
        ("land/esoterica/foo", False, False),
    ],
)
def test_is_qualified_id(value, with_fragment, without_fragment):
    assert grammar.is_qualified_id(value, allow_fragment=True) is with_fragment
    assert grammar.is_qualified_id(value, allow_fragment=False) is without_fragment


@pytest.mark.parametrize(
    "value, expected",
    [
        ("major_arcana.00", True),
        ("major_arcana.x_dreamer", True),
        ("minor_arcana.wands.ace", True),
        ("minor_arcana.coins.ace", True),
        ("major_arcana.0", False),
        ("major_arcana", False),
        ("minor_arcana.wands", False),
        ("minor_arcana.wands.ace.extra", False),
    ],
)
def test_is_canonical_id(value, expected):
    assert grammar.is_canonical_id(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2014", date(2014, 1, 1)),
        ("2014-02", date(2014, 2, 1)),
        ("2014-02-28", date(2014, 2, 28)),
        ("2014-02-30", None),
        ("2014-13", None),
        ("14", None),
    ],
)
def test_parse_published_date(value, expected):
    assert grammar.parse_published_date(value) == expected


@pytest.mark.parametrize(
    "slot, entry_key, expected",
    [
        ("passages", "text", True),
        ("passages", "advice.work", True),
        ("passages", "symbols.jester", True),
        ("passages", "symbols.a.b", False),
        ("passages", "mymeaning", False),
        ("passages", "x_upright", True),
        ("passages", "x_upright.work", True),
        ("passages", "advice.x_dreams", True),
        ("passages", "element", False),
        ("correspondences", "number", True),
        ("correspondences", "numerology", False),
        ("correspondences", "x_numerology", True),
        ("correspondences", "symbols.jester", False),
    ],
)
def test_is_registered(slot, entry_key, expected):
    assert registry.is_registered(slot, entry_key) is expected


def test_divinatory_keys_are_registered_passage_keys():
    assert registry.DIVINATORY_KEYS <= registry.PASSAGE_KEYS
