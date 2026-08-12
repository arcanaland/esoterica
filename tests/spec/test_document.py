from __future__ import annotations

import pytest


def test_unknown_top_level_table(validate):
    report = validate('[extra]\nanything = true\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", "4")]


def test_top_level_passages_table(validate):
    """A 0.1 spelling, warned about by Appendix B and rejected by 4 as a table."""
    report = validate('[passages]\ntext = "A passage."\n')
    assert [(f.level, f.spec) for f in report.findings] == [
        ("W", "Appendix B"),
        ("E", "4"),
    ]


def test_no_card_and_no_group_target(validate):
    report = validate(card="")
    assert [(f.level, f.spec) for f in report.findings] == [("W", "11.1")]


@pytest.mark.parametrize(
    "text",
    ["this is not toml at all\n", 'name = "no meta table"\n', "[meta]\nname = \"x\"\n"],
)
def test_not_a_source_when_globbed(scan, text):
    """2.2.1: a candidate that does not parse or carries no schema_version."""
    report, is_source = scan(text, explicit=False)
    assert not is_source
    assert report.findings == []


@pytest.mark.parametrize(
    "text, spec",
    [("this is not toml at all\n", ""), ('name = "no meta table"\n', "2.2.1")],
)
def test_named_on_the_command_line_it_is_still_reported(scan, text, spec):
    report, is_source = scan(text, explicit=True)
    assert is_source
    assert [(f.level, f.spec) for f in report.findings] == [("E", spec)]
