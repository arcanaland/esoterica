from __future__ import annotations

import pytest

TARGET = '[card."major_arcana.00"'


@pytest.mark.parametrize(
    "body",
    [
        'text = "A passage."',
        'keywords = ["freedom", "faith"]',
        '[card."major_arcana.00".passages.advice]\nwork = "Leap."',
        '[card."major_arcana.00".passages.symbols]\njester = "A wit."',
        'x_upright = "Whatever the author means."',
    ],
)
def test_passage_accepted(validate, body):
    assert validate(card=f"{TARGET}.passages]\n{body}\n").findings == []


@pytest.mark.parametrize(
    "body, level, spec",
    [
        ('text = ""', "E", "5.1"),
        ("text = []", "E", "5.1"),
        ('text = ["a", ""]', "E", "5.1"),
        ("text = 4", "E", "5.1"),
        ('mymeaning = "A passage."', "W", "11.4"),
        ('Text = "A passage."', "E", "3.4"),
    ],
)
def test_passage_rejected(validate, body, level, spec):
    report = validate(card=f"{TARGET}.passages]\n{body}\n")
    assert [(f.level, f.spec) for f in report.findings] == [(level, spec)]


@pytest.mark.parametrize(
    "body",
    [
        "number = 0",
        'element = "air"',
        'color = ["yellow", "white"]',
        "hebrew_letter_value = 1",
        'x_numerology = "The unnumbered card."',
    ],
)
def test_correspondence_accepted(validate, body):
    assert validate(card=f"{TARGET}.correspondences]\n{body}\n").findings == []


@pytest.mark.parametrize(
    "body, level, spec",
    [
        ('number = ["a", {}]', "E", "6.1"),
        ("number = []", "E", "6.1"),
        ('numerology = "The unnumbered card."', "W", "11.4"),
    ],
)
def test_correspondence_rejected(validate, body, level, spec):
    report = validate(card=f"{TARGET}.correspondences]\n{body}\n")
    assert [(f.level, f.spec) for f in report.findings] == [(level, spec)]


def test_unregistered_symbol_subkey_is_registered(validate):
    """`symbols.<name>` is 5.2's one open subkey; the name is the author's."""
    body = f'{TARGET}.passages.symbols]\nanything_at_all = "A wit."\n'
    assert validate(card=body).findings == []


def test_slot_position(validate):
    report = validate(card=f'{TARGET}.meanings]\ntext = "A passage."\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", "4.3")]
