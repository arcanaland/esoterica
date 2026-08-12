from __future__ import annotations

import pytest

PASSAGE = 'text = "A passage."'


@pytest.mark.parametrize(
    "key",
    [
        "major_arcana.00",
        "major_arcana.21",
        "major_arcana.x_the_dreamer",
        "minor_arcana.wands.ace",
        "minor_arcana.pentacles.king",
        "minor_arcana.coins.ace",
    ],
)
def test_canonical_card_key(validate, key):
    assert validate(card=f'[card."{key}".passages]\n{PASSAGE}\n').findings == []


@pytest.mark.parametrize(
    "key, spec",
    [
        ("minor_arcana.wands.ace:alt", "3.2"),
        ("minor_arcana.wands.Ace", "3.2"),
        ("major_arcana.0", "3.2"),
        ("major_arcana.00.extra", "3.2"),
    ],
)
def test_malformed_card_key(validate, key, spec):
    report = validate(card=f'[card."{key}".passages]\n{PASSAGE}\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", spec)]


def test_canonical_id_written_as_a_key_path(validate):
    """`[card.major_arcana.00.passages]` names a table `major_arcana`, not a card."""
    report = validate(card=f"[card.major_arcana.00.passages]\n{PASSAGE}\n")
    # 3.5 for the key, then 4.3 because `00` lands in the slot position.
    assert [(f.level, f.spec) for f in report.findings] == [("E", "3.5"), ("E", "4.3")]
