from __future__ import annotations

import pytest


def test_minimal_document_is_clean(validate):
    assert validate().findings == []


@pytest.mark.parametrize(
    "line, level, spec",
    [
        ("published_date = 2014", "E", "4.1"),
        ('published_date = "2014-13"', "E", "4.1.3"),
        ('published_date = "2014-02-30"', "E", "4.1.3"),
        ('tags = "book"', "E", "4.1"),
        ('tags = ["book", 2]', "E", "4.1"),
        ('url = "example.com"', "E", "4.1"),
        ('default_language = "e n"', "E", "7.2"),
        ('redistribution = "yes"', "E", "8.3"),
        ('derivation = "maybe"', "E", "8.3"),
        ('type = "lecture"', "W", "4.1.1"),
        ('id = "example"', "W", "Appendix B"),
    ],
)
def test_meta_field(validate, meta, line, level, spec):
    report = validate(meta=meta + line + "\n")
    assert [(f.level, f.spec) for f in report.findings] == [(level, spec)]


@pytest.mark.parametrize(
    "line",
    [
        'published_date = "2014"',
        'published_date = "2014-02"',
        'published_date = "2014-02-28"',
        'tags = ["book"]',
        'url = "https://example.com/x"',
        'default_language = "en-GB"',
        'redistribution = "unstated"',
        'type = "book"',
        'type = "x_lecture"',
    ],
)
def test_meta_field_accepted(validate, meta, line):
    assert validate(meta=meta + line + "\n").findings == []


# schema_version is absent from this list on purpose: without it the file is not
# a source at all (2.2.1), which test_document covers.
@pytest.mark.parametrize("key", ["identifier", "name", "license"])
def test_required_meta_field_absent(validate, meta, key):
    without = "".join(
        line + "\n" for line in meta.splitlines() if not line.startswith(key)
    )
    report = validate(meta=without)
    assert ("E", "4.1") in [(f.level, f.spec) for f in report.findings]


def test_schema_version_needs_two_parts(validate, meta):
    report = validate(meta=meta.replace('schema_version = "1.0"', 'schema_version = "1"'))
    assert [(f.level, f.spec) for f in report.findings] == [("E", "1.4")]


@pytest.mark.parametrize(
    "identifier",
    ["land.arcana.dev/esoterica", "land.arcana.dev/esoterica/a/b", "a.b/esoterica/c"],
)
def test_identifier_accepted(validate, meta, identifier):
    report = validate(meta=meta.replace("land.arcana.dev/esoterica/example", identifier))
    assert report.findings == []


@pytest.mark.parametrize(
    "identifier, level",
    [
        ("land.arcana.dev/esoterica/foo#frag", "E"),
        ("land.arcana.dev/x_esoterica_source/foo", "E"),
        ("arcana/esoterica/foo", "E"),
        ("land.arcana.dev/Esoterica/foo", "E"),
        # 3.1 grades the type segment a MUST and 11.4 grades the same rule a W.
        # The test asserts W because 11.4 is what a validator implements. This is
        # finding 1 in the agents KB, not a bug in this test.
        ("land.arcana.dev/x-esoterica-source/foo", "W"),
    ],
)
def test_identifier(validate, meta, identifier, level):
    report = validate(meta=meta.replace("land.arcana.dev/esoterica/example", identifier))
    assert [(f.level, f.spec) for f in report.findings] == [(level, "3.1")]
