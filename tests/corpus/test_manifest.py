from __future__ import annotations

from pathlib import Path

import pytest
from corpus_plugins import FIXTURES
from esoterica_corpus.manifest import (
    ManifestError,
    SuppliedInput,
    VendoredInput,
    load_drops,
    load_mapping,
    load_source,
)

MCELROY = Path(__file__).resolve().parents[2] / "sources/mcelroy"


def test_mcelroy_source_loads_unchanged():
    source = load_source(MCELROY / "SOURCE.toml")
    assert isinstance(source.input, VendoredInput)
    assert source.input.path == "input/mcelroy.txt"
    assert source.input.accents == {"[as]": "acute", "[ag]": "grave"}
    assert len(source.input.mojibake) == 7


def test_mcelroy_drops_load():
    drops = load_drops(MCELROY / "drops.toml")
    assert drops.drop[0].rule == "blank"
    assert drops.drop[1].lines == "1-2"


def test_mcelroy_mapping_loads():
    mapping = load_mapping(MCELROY / "mapping.toml")
    assert mapping.build is None
    assert mapping.expected is None
    assert "structure" in mapping.raw


@pytest.mark.parametrize("name", ["vendored", "supplied"])
def test_fixture_loads(name):
    directory = FIXTURES / name
    source = load_source(directory / "SOURCE.toml")
    mapping = load_mapping(directory / "mapping.toml")
    load_drops(directory / "drops.toml")
    assert source.input.kind == name
    assert mapping.build is not None and mapping.build.parser == "fixture"
    assert mapping.expected


def edited(tmp_path, old: str, new: str) -> Path:
    path = tmp_path / "SOURCE.toml"
    text = (FIXTURES / "supplied/SOURCE.toml").read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


def test_supplied_fixture_is_supplied():
    source = load_source(FIXTURES / "supplied/SOURCE.toml")
    assert isinstance(source.input, SuppliedInput)
    assert source.input.accepted[0].md5 is not None


def test_unknown_kind_is_rejected(tmp_path):
    with pytest.raises(ManifestError, match="input"):
        load_source(edited(tmp_path, 'kind = "supplied"', 'kind = "borrowed"'))


def test_unknown_normalize_step_is_rejected(tmp_path):
    with pytest.raises(ManifestError, match="normalize"):
        load_source(edited(tmp_path, '"trim"]', '"trim", "smartquotes"]'))


@pytest.mark.parametrize(
    "md5",
    [
        "DC772F3F9F04FAD52A409C55F410028E",  # upper case
        "dc772f3f9f04fad52a409c55f410028",  # 31 characters
        "dc772f3f9f04fad52a409c55f410028e0",  # 33
        "zc772f3f9f04fad52a409c55f410028e",  # not hex
    ],
)
def test_malformed_md5_is_rejected(tmp_path, md5):
    with pytest.raises(ManifestError, match="md5"):
        load_source(edited(tmp_path, "dc772f3f9f04fad52a409c55f410028e", md5))


def test_supplied_input_has_no_path(tmp_path):
    with pytest.raises(ManifestError, match="path"):
        load_source(
            edited(tmp_path, "[input.extraction]", 'path = "x.txt"\n\n[input.extraction]')
        )


def test_a_drop_names_exactly_one_selector(tmp_path):
    path = tmp_path / "drops.toml"
    path.write_text('schema = 1\n[[drop]]\nreason = "r"\nrule = "blank"\nlines = "1"\n')
    with pytest.raises(ManifestError, match="exactly one"):
        load_drops(path)


def test_a_drop_needs_a_reason(tmp_path):
    path = tmp_path / "drops.toml"
    path.write_text('schema = 1\n[[drop]]\nlines = "1"\n')
    with pytest.raises(ManifestError, match="reason"):
        load_drops(path)
