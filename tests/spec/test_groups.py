from __future__ import annotations

import pytest

PASSAGE = 'text = "A passage."'


@pytest.mark.parametrize(
    "body",
    [
        f"[group.all.passages]\n{PASSAGE}",
        f"[group.arcana.major.passages]\n{PASSAGE}",
        f"[group.classes.court.passages]\n{PASSAGE}",
        f"[group.suits.wands.passages]\n{PASSAGE}",
        f"[group.suits.coins.passages]\n{PASSAGE}",
        f"[group.ranks.ace.passages]\n{PASSAGE}",
        '[group.custom.lunar]\ncards = ["major_arcana.02"]',
        f'[group."land.arcana.dev/esoterica/other".passages]\n{PASSAGE}',
    ],
)
def test_group_accepted(validate, body):
    assert validate(body).findings == []


@pytest.mark.parametrize(
    "body, level, spec",
    [
        (f"[group.bogus.thing.passages]\n{PASSAGE}", "E", "3.3"),
        (f'[group."land.arcana.dev/ESOTERICA".passages]\n{PASSAGE}', "E", "3.3"),
        (f"[group.arcana.middle.passages]\n{PASSAGE}", "E", "4.4"),
        (f"[group.classes.trump.passages]\n{PASSAGE}", "E", "4.4"),
        (f"[group.suits.Wands.passages]\n{PASSAGE}", "E", "4.4"),
        (f"[group.custom.lunar.passages]\n{PASSAGE}", "W", "4.5"),
        ('[group.suits.wands]\ncards = ["major_arcana.02"]', "E", "4.5"),
        ('[group.custom.lunar]\ncards = []', "E", "4.5"),
        ('[group.custom.lunar]\ncards = ["major_arcana.02:alt"]', "E", "4.5"),
        ('[group.custom.lunar]\ncards = ["the_moon"]', "E", "4.5"),
        (
            '[group.custom.lunar]\ncards = ["major_arcana.02", "major_arcana.02"]',
            "E",
            "4.5",
        ),
    ],
)
def test_group_rejected(validate, body, level, spec):
    report = validate(body)
    assert [(f.level, f.spec) for f in report.findings] == [(level, spec)]
