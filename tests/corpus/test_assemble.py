from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from corpus_plugins import FIXTURES, SUPPLIED_INPUT
from esoterica_corpus import pipeline, provenance
from esoterica_corpus.document import DocumentError, assemble, check_rights, put
from esoterica_corpus.input import Locator, load
from esoterica_corpus.manifest import Output, load_source
from esoterica_corpus.records import Entry
from esoterica_corpus.tomlwrite import dumps

MCELROY = Path(__file__).resolve().parents[2] / "sources/mcelroy"
ORDER = Output(
    filename="x.toml",
    passage_order=["text", "light", "shadow", "advice"],
    advice_order=["relationships", "work"],
    correspondence_order=["number", "x_numerology"],
    group_order=["group.arcana.major", "group.suits.wands"],
)


def entry(target, key, value, unit=1):
    return Entry(target, key, value, (unit,))


def test_cards_are_in_deck_order_and_keys_in_mapping_order():
    doc = assemble(
        {"name": "x"},
        [
            entry('card."minor_arcana.wands.king"', "passages.light", "k"),
            entry('card."minor_arcana.cups.ace"', "passages.light", "a"),
            entry('card."major_arcana.21"', "passages.shadow", "s"),
            entry('card."major_arcana.21"', "passages.light", "l"),
            entry('card."minor_arcana.wands.ace"', "passages.light", "w"),
            entry('card."major_arcana.03"', "passages.advice.work", "w"),
            entry('card."major_arcana.03"', "passages.advice.relationships", "r"),
        ],
        ORDER,
    )
    assert list(doc) == ["meta", "card", "group"]
    assert list(doc["card"]) == [
        "major_arcana.03",
        "major_arcana.21",
        "minor_arcana.wands.ace",
        "minor_arcana.wands.king",
        "minor_arcana.cups.ace",
    ]
    assert list(doc["card"]["major_arcana.21"]["passages"]) == ["light", "shadow"]
    assert list(doc["card"]["major_arcana.03"]["passages"]["advice"]) == [
        "relationships",
        "work",
    ]


def test_symbols_keep_the_order_they_arrived_in():
    doc = assemble(
        {},
        [
            entry('card."major_arcana.00"', "symbols.zebra", {"label": "Z", "text": "z"}),
            entry('card."major_arcana.00"', "symbols.ant", {"label": "A", "text": "a"}),
        ],
        ORDER,
    )
    assert list(doc["card"]["major_arcana.00"]["symbols"]) == ["zebra", "ant"]


def test_a_table_value_is_merged_key_by_key():
    doc = assemble(
        {},
        [
            entry(
                'card."major_arcana.00"',
                "correspondences",
                {"x_numerology": "0, nothing", "number": 0},
            )
        ],
        ORDER,
    )
    assert doc["card"]["major_arcana.00"]["correspondences"] == {
        "number": 0,
        "x_numerology": "0, nothing",
    }


def test_groups_nest_in_group_order():
    doc = assemble(
        {},
        [
            entry("group.suits.wands", "correspondences", {"number": 1}),
            entry("group.arcana.major", "passages.text", "t"),
        ],
        ORDER,
    )
    assert doc["group"] == {
        "arcana": {"major": {"passages": {"text": "t"}}},
        "suits": {"wands": {"correspondences": {"number": 1}}},
    }


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([entry('card."major_arcana.00"', "passages.x_new", "x")], "passage order omits"),
        ([entry("group.classes.pip", "passages.text", "x")], "group_order omits"),
        ([entry("card.major_arcana.00", "passages.light", "x")], "not a card or group"),
        ([entry('card."major_arcana.00"', "passages.light", "x")] * 2, "set twice"),
        ([entry('card."cups.ace"', "passages.light", "x")], "can order"),
        ([entry('card."major_arcana.00"', "app.x", "x")], "can't order"),
    ],
)
def test_what_cannot_be_ordered_or_placed_fails(entries, message):
    with pytest.raises(DocumentError, match=message):
        assemble({}, entries, ORDER)


def test_put_refuses_to_replace_a_value_with_a_table():
    table = {"a": "x"}
    with pytest.raises(DocumentError, match="set twice"):
        put(table, "a", {"b": "y"})


@pytest.mark.parametrize("value", ["full", "unstated", None])
def test_rights_fail_unless_none(value):
    meta = {"redistribution": "none", "derivation": "none"}
    if value is None:
        del meta["derivation"]
    else:
        meta["derivation"] = value
    with pytest.raises(DocumentError, match="derivation"):
        check_rights(meta)


def test_rights_pass_on_none():
    check_rights({"redistribution": "none", "derivation": "none"})


def test_a_supplied_build_fails_on_full_rights(source_copy):
    directory = source_copy("supplied")
    mapping = directory / "mapping.toml"
    mapping.write_text(
        mapping.read_text(encoding="utf-8").replace(
            'redistribution = "none"', 'redistribution = "full"'
        ),
        encoding="utf-8",
    )
    source = pipeline.Source.open(directory)
    loaded = load(directory, source.manifest, Locator(file=SUPPLIED_INPUT)).loaded
    assert loaded is not None
    with pytest.raises(DocumentError, match="redistribution is 'full'"):
        pipeline.build(pipeline.parse(source, loaded))


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def values(table):
    for value in table.values():
        if isinstance(value, dict):
            yield from values(value)
        else:
            yield value


def test_supplied_provenance_names_no_input_path(tmp_path):
    located = tmp_path / "somewhere-private" / "book.txt"
    located.parent.mkdir()
    located.write_bytes(SUPPLIED_INPUT.read_bytes())
    source = pipeline.Source.open(FIXTURES / "supplied")
    loaded = load(source.directory, source.manifest, Locator(file=located)).loaded
    assert loaded is not None
    record = pipeline.build(pipeline.parse(source, loaded)).provenance

    assert set(record["input"]) == {
        "kind",
        "file_sha256",
        "accepted",
        "canonical_sha256",
        "lines",
        "extractor",
    }
    for value in values(record):
        assert not (isinstance(value, str) and ("book.txt" in value or str(tmp_path) in value))


def test_vendored_provenance_reproduces_mcelroy_s_shape():
    committed_text = (MCELROY / "dist/PROVENANCE.toml").read_text(encoding="utf-8")
    committed = tomllib.loads(committed_text)
    manifest = load_source(MCELROY / "SOURCE.toml")
    loaded = load(MCELROY, manifest).loaded
    assert loaded is not None
    name = Path(committed["output"]["path"]).name

    record = provenance.vendored(
        builder=committed["build"]["builder"],
        identifier=manifest.identifier,
        input_record=loaded.record,
        output_name=name,
        output_text=(MCELROY / "dist" / name).read_text(encoding="utf-8"),
        counts=committed["counts"],
    )
    assert dumps(record) == committed_text
