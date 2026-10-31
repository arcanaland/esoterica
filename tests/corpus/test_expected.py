from __future__ import annotations

import pytest
from esoterica_corpus.expected import ExpectedError, check, measure

DOC = {
    "meta": {"name": "x"},
    "card": {
        "major_arcana.00": {
            "passages": {"light": "a", "advice": {"work": "b", "love": "c"}},
            "symbols": {"dog": {"label": "Dog", "text": "d"}},
        },
        "major_arcana.01": {"passages": {"light": "e", "keywords": ["f", "g"]}},
    },
    "group": {"arcana": {"major": {"passages": {"text": "h"}}}},
}


def test_exact_key():
    assert measure(DOC, {"passages.light": 0}) == {"passages.light": 2}


def test_a_list_is_one_leaf():
    assert measure(DOC, {"passages.keywords": 0}) == {"passages.keywords": 1}


def test_star_across_one_segment():
    assert measure(DOC, {"passages.advice.*": 0}) == {"passages.advice.*": 2}


def test_star_across_two_segments():
    # symbols.dog.label and symbols.dog.text
    assert measure(DOC, {"symbols.*": 0}) == {"symbols.*": 2}
    # light x2, keywords, the two advice leaves, and the group's text
    assert measure(DOC, {"passages.*": 0}) == {"passages.*": 6}


def test_star_needs_at_least_one_segment():
    assert measure(DOC, {"passages.light.*": 0}) == {"passages.light.*": 0}


def test_cards_and_groups_count_tables():
    assert measure(DOC, {"cards": 0, "groups": 0}) == {"cards": 2, "groups": 1}


def test_as_expected_returns_the_counts():
    assert check(DOC, {"cards": 2, "passages.light": 2}) == {"cards": 2, "passages.light": 2}


def test_a_mismatch_fails_naming_the_key():
    with pytest.raises(ExpectedError, match=r"passages.light: expected 3, built 2"):
        check(DOC, {"cards": 2, "passages.light": 3})


def test_a_missing_table_fails():
    with pytest.raises(ExpectedError, match="absence is not a pass"):
        check(DOC, None)


def test_an_empty_table_fails():
    with pytest.raises(ExpectedError, match="empty"):
        check(DOC, {})
