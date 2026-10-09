from __future__ import annotations

import pytest

PATTERN = '{ rel = "pattern", target = "land.arcana/pattern/rider-waite-smith" }'


def with_related(meta: str, *entries: str) -> str:
    return meta + "related = [" + ", ".join(entries) + "]\n"


def found(report) -> list[tuple[str, str]]:
    return [(f.level, f.spec) for f in report.findings]


@pytest.mark.parametrize(
    "entries",
    [
        (),
        (PATTERN,),
        (PATTERN, '{ rel = "about", target = "land.arcana/deck/rider-waite-smith" }'),
        ('{ rel = "about", target = "land.arcana/pattern/thoth", title = "Thoth" }',),
        (
            '{ rel = "about", target = "com.example/deck/a" }',
            '{ rel = "about", target = "com.example/deck/b" }',
        ),
        ('{ rel = "x_responds_to", target = "com.example/esoterica/other" }',),
    ],
)
def test_related_accepted(validate, meta, entries):
    assert validate(meta=with_related(meta, *entries)).findings == []


@pytest.mark.parametrize(
    "line, spec",
    [
        ('related = "land.arcana/pattern/rider-waite-smith"', "4.1"),
        ('related = ["land.arcana/pattern/rider-waite-smith"]', "4.1"),
        ('related = [{ target = "land.arcana/pattern/rider-waite-smith" }]', "4.1.5"),
        ('related = [{ rel = "pattern" }]', "4.1.5"),
        ('related = [{ rel = "pattern", target = 8 }]', "4.1.5"),
        ('related = [{ rel = "Pattern", target = "land.arcana/pattern/x" }]', "4.1.5"),
    ],
)
def test_related_entry_shape_rejected(validate, meta, line, spec):
    assert found(validate(meta=meta + line + "\n")) == [("E", spec)]


@pytest.mark.parametrize(
    "target",
    [
        "rider-waite-smith",
        "land.arcana/deck/rider-waite-smith#major_arcana.08",
        "land.arcana/deck/rider-waite-smith#major_arcana.06:two_women",
        "major_arcana.08",
    ],
)
def test_related_target_must_be_an_unfragmented_identifier(validate, meta, target):
    entry = f'{{ rel = "about", target = "{target}" }}'
    assert found(validate(meta=with_related(meta, entry))) == [("E", "4.1.5")]


def test_pattern_target_must_be_a_pattern(validate, meta):
    entry = '{ rel = "pattern", target = "land.arcana/deck/rider-waite-smith" }'
    assert found(validate(meta=with_related(meta, entry))) == [("E", "4.1.5")]


def test_at_most_one_pattern(validate, meta):
    other = '{ rel = "pattern", target = "land.arcana/pattern/tarot-de-marseille" }'
    assert found(validate(meta=with_related(meta, PATTERN, other))) == [("E", "4.1.5")]


def test_unprefixed_unregistered_rel_warns(validate, meta):
    entry = '{ rel = "responds_to", target = "com.example/esoterica/other" }'
    assert found(validate(meta=with_related(meta, entry))) == [("W", "4.1.5")]


def test_about_something_other_than_a_deck_or_pattern_warns(validate, meta):
    entry = '{ rel = "about", target = "com.example/esoterica/other" }'
    assert found(validate(meta=with_related(meta, entry))) == [("W", "4.1.5")]


def test_overlay_carrying_related_warns(validate, meta):
    overlay = meta + 'translates = "land.arcana.dev/esoterica/base"\n'
    assert found(validate(meta=with_related(overlay, PATTERN))) == [("W", "7.1")]


def test_overlay_with_empty_related_is_clean(validate, meta):
    overlay = meta + 'translates = "land.arcana.dev/esoterica/base"\n'
    assert validate(meta=with_related(overlay)).findings == []
