from __future__ import annotations

import pytest

TARGET = '[card."major_arcana.00"'


@pytest.mark.parametrize(
    "body",
    [
        'text = "A passage."',
        'keywords = ["freedom", "faith"]',
        '[card."major_arcana.00".passages.advice]\nwork = "Leap."',
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


def test_passages_symbols_is_legacy(validate):
    """Each draft-spelling entry is warned about, and not also as unregistered."""
    body = f'{TARGET}.passages.symbols]\njester = "A wit."\nbeggar = "A bag."\n'
    report = validate(card=body)
    assert [(f.level, f.spec) for f in report.findings] == [("W", "Appendix B")] * 2


@pytest.mark.parametrize(
    "body",
    [
        'jester = ""',
        "jester = 4",
        'Jester = "A wit."',
        '[card."major_arcana.00".passages.symbols.a]\nb = ""',
    ],
)
def test_passages_symbols_entries_take_only_their_own_warning(validate, body):
    """11.4: what an application ignores, a validator does not otherwise check."""
    report = validate(card=f"{TARGET}.passages.symbols]\n{body}\n")
    assert [(f.level, f.spec) for f in report.findings] == [("W", "Appendix B")]


def test_passage_named_symbols_is_only_unregistered(validate):
    """Its entry key is `symbols`, which does not begin `symbols.`."""
    report = validate(card=f'{TARGET}.passages]\nsymbols = "A list."\n')
    assert [(f.level, f.spec) for f in report.findings] == [("W", "11.4")]


@pytest.mark.parametrize(
    "body",
    [
        'text = "A wit."',
        'label = "The Jester"\ntext = "A wit."',
        'label = "The Rose and Lilly Cross."\ntext = ["A wit.", "A bag."]',
    ],
)
def test_symbol_accepted(validate, body):
    card = f'{TARGET}.passages]\ntext = "A passage."\n{TARGET}.symbols.the_jester]\n{body}\n'
    assert validate(card=card).findings == []


@pytest.mark.parametrize(
    "body, level, spec",
    [
        ('label = "The Jester"', "E", "5.4"),
        ('text = ""', "E", "5.4"),
        ("text = 4", "E", "5.4"),
        ('label = ""\ntext = "A wit."', "E", "5.4"),
        ('label = 4\ntext = "A wit."', "E", "5.4"),
        ('text = "A wit."\nnote = "Undefined."', "W", "5.4"),
        # 5.4 asks no x_ prefix of a field, so an x_ field is warned about too.
        ('text = "A wit."\nx_note = 4', "W", "5.4"),
        # The one-segment rule: `edge` is a field of `the_jester`, not a symbol.
        ('text = "A wit."\nedge = "Undefined."', "W", "5.4"),
    ],
)
def test_symbol_rejected(validate, body, level, spec):
    card = f"{TARGET}.symbols.the_jester]\n{body}\n"
    report = validate(card=card)
    assert [(f.level, f.spec) for f in report.findings] == [(level, spec)]


def test_symbol_must_be_a_table(validate):
    report = validate(card=f'{TARGET}.symbols]\nthe_jester = "A wit."\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", "5.4")]


def test_symbol_key_is_a_custom_name(validate):
    report = validate(card=f'{TARGET}.symbols.The_Jester]\ntext = "A wit."\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", "5.4")]


def test_symbols_slot_on_a_group(validate):
    """The slot is positional, so a group target carries it too."""
    body = '[group.suits.cups.symbols.the_cup]\ntext = "A vessel."\n'
    assert validate(body).findings == []


def test_slot_position(validate):
    report = validate(card=f'{TARGET}.meanings]\ntext = "A passage."\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", "4.3")]
