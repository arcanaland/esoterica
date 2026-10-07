from __future__ import annotations

import pytest

WORK = '[meta.work]\nname = "Example Tarot Book"\n'


def with_work(meta: str, relation: str = "transcribes", work: str = WORK) -> str:
    """[meta] with a relation line, then [meta.work]; each may be empty."""
    line = f'relation = "{relation}"\n' if relation else ""
    return meta + line + work


def test_transcription_is_clean(validate, meta):
    assert validate(meta=with_work(meta)).findings == []


@pytest.mark.parametrize(
    "line",
    [
        'published_date = "2014"',
        'published_date = "2014-02"',
        'published_date = "2014-02-28"',
        'url = "https://example.com/x"',
        'isbn = "978-0-00-000000-0"',
        "x_edition = 2",
    ],
)
def test_work_field_accepted(validate, meta, line):
    assert validate(meta=with_work(meta, work=WORK + line + "\n")).findings == []


@pytest.mark.parametrize(
    "line, spec",
    [
        # 4.1.3: a bare 2014 is a TOML integer and a bare 2014-09-30 a local
        # date. Both fail the type rule, not the date grammar.
        ("published_date = 2014", "4.1.4"),
        ("published_date = 2014-09-30", "4.1.4"),
        ('published_date = "2014-13"', "4.1.3"),
        ('published_date = "2014-02-30"', "4.1.3"),
        ('url = "example.com"', "4.1.4"),
        ("author = 4", "4.1.4"),
        ("rights_status = []", "4.1.4"),
    ],
)
def test_work_field_rejected(validate, meta, line, spec):
    report = validate(meta=with_work(meta, work=WORK + line + "\n"))
    assert [(f.level, f.spec) for f in report.findings] == [("E", spec)]


def test_work_must_be_a_table(validate, meta):
    report = validate(meta=meta + 'relation = "transcribes"\nwork = "Example Tarot Book"\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", "4.1.4")]


@pytest.mark.parametrize("relation", ["transcribes", "abridges", "annotates", "x_responds_to"])
def test_relation_accepted(validate, meta, relation):
    assert validate(meta=with_work(meta, relation)).findings == []


def test_unregistered_relation(validate, meta):
    report = validate(meta=with_work(meta, "responds_to"))
    assert [(f.level, f.spec) for f in report.findings] == [("W", "4.1.4")]


def test_relation_without_work(validate, meta):
    report = validate(meta=with_work(meta, work=""))
    assert [(f.level, f.spec) for f in report.findings] == [("W", "4.1.4")]


def test_work_without_relation(validate, meta):
    report = validate(meta=with_work(meta, relation=""))
    assert [(f.level, f.spec) for f in report.findings] == [("W", "8.4")]


@pytest.mark.parametrize(
    "relation, level",
    [("annotates", ["W"]), ("abridges", ["W"]), ("transcribes", [])],
)
def test_work_name_borrowed(validate, meta, relation, level):
    """Under transcribes the document may share the work's title; otherwise not."""
    work = '[meta.work]\nname = "Example"\n'
    report = validate(meta=with_work(meta, relation, work))
    assert [(f.level, f.spec) for f in report.findings] == [(lv, "8.4") for lv in level]


@pytest.mark.parametrize(
    "line",
    [
        'publisher = "Example Press"',
        'published_date = "2014"',
        'isbn = "978-0-00-000000-0"',
        'url = "https://example.com/x"',
        'rights_status = "https://rightsstatements.org/vocab/InC/1.0/"',
    ],
)
def test_work_key_under_meta(validate, meta, line):
    report = validate(meta=meta + line + "\n")
    assert [(f.level, f.spec) for f in report.findings] == [("W", "Appendix B")]


def test_work_key_under_meta_is_not_typed(validate, meta):
    """4.1 no longer defines it, so it is ignored rather than typed, and only warned."""
    report = validate(meta=meta + "published_date = 2014\n")
    assert [(f.level, f.spec) for f in report.findings] == [("W", "Appendix B")]
