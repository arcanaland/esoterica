"""Every row of RFC-015 §2's table, and the vendored gate it sits beside"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import corpus_plugins
import pytest
from corpus_plugins import FIXTURES, SUPPLIED_INPUT
from esoterica_corpus import records
from esoterica_corpus.input import (
    STEPS,
    Locator,
    Status,
    hash_file,
    load,
    normalize,
    repair,
)
from esoterica_corpus.manifest import NormalizeStep, Repairs, load_source

REPO_ROOT = Path(__file__).resolve().parents[2]
MCELROY = REPO_ROOT / "sources/mcelroy"
FILE = hash_file(SUPPLIED_INPUT)
OTHER_SHA = "0" * 64
OTHER_MD5 = "0" * 32


def verdict(directory: Path, locator: Locator | None = None):
    return load(directory, load_source(directory / "SOURCE.toml"), locator)


def edit(directory: Path, old: str, new: str) -> None:
    path = directory / "SOURCE.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------

MESSY = "\n\nfirst \r\nsecond\rthird  \n\n\n\nfourth\n"


def test_steps_are_the_manifest_steps():
    assert set(STEPS) == set(NormalizeStep.__args__)


def test_nfc():
    assert normalize("é", ["nfc"]) == "é"


def test_lf():
    assert normalize(MESSY, ["lf"]) == "\n\nfirst \nsecond\nthird  \n\n\n\nfourth\n"


def test_rstrip_strips_nbsp_and_spaces_but_not_newlines():
    assert normalize("a \nb  \n", ["rstrip"]) == "a\nb\n"
    # A lone \r is whitespace to str.rstrip, so before lf it is stripped too
    assert normalize("a\r\nb", ["rstrip"]) == "a\nb"


def test_squeeze_blank():
    assert normalize("a\n\n\n\nb\n\nc\n\n\nd", ["squeeze-blank"]) == "a\n\nb\n\nc\n\nd"


def test_trim():
    assert normalize("\n\na\nb\n\n\n", ["trim"]) == "a\nb\n"


def test_all_steps_in_order():
    steps = ["nfc", "lf", "rstrip", "squeeze-blank", "trim"]
    assert normalize(MESSY, steps) == "first\nsecond\nthird\n\nfourth\n"


def test_repair():
    repairs = Repairs(mojibake={"Õ": "’"}, accents={"[as]": "acute"})
    assert repair("ClichÕs cafe[as]", repairs) == "Clich’s café"


# ---------------------------------------------------------------------------
# Vendored
# ---------------------------------------------------------------------------


def test_mcelroy_hash_is_the_one_verify_input_prints():
    result = verdict(MCELROY)
    printed = subprocess.run(
        [str(REPO_ROOT / "tools/verify_input.py")], capture_output=True, text=True, check=True
    ).stdout
    assert result.status is Status.OK
    assert f"ok   sources/mcelroy/input/mcelroy.txt  {result.detail}" in printed


def test_mcelroy_line_count_is_provenance_s():
    committed = tomllib.loads((MCELROY / "dist/PROVENANCE.toml").read_text(encoding="utf-8"))
    loaded = verdict(MCELROY).loaded
    assert loaded is not None
    assert len(loaded.text) == committed["input"]["lines"] == loaded.record["lines"]


def test_mcelroy_is_repaired():
    loaded = verdict(MCELROY).loaded
    assert loaded is not None
    assert not any("Õ" in line or "[as]" in line for line in loaded.text.lines)


def test_vendored_mismatch_fails(source_copy):
    directory = source_copy("vendored")
    (directory / "input/fixture.txt").write_text("changed\n", encoding="utf-8")
    result = verdict(directory)
    assert result.status is Status.FAIL
    assert "sha256 mismatch" in result.detail


def test_vendored_missing_fails(source_copy):
    directory = source_copy("vendored")
    (directory / "input/fixture.txt").unlink()
    assert verdict(directory).status is Status.FAIL


def test_fetched_is_unverified(source_copy):
    directory = source_copy("vendored")
    edit(directory, 'kind = "vendored"\npath = "input/fixture.txt"', 'kind = "fetched"')
    edit(directory, '[input.encoding]\ndeclared = "utf-8"\n', "")
    assert verdict(directory).status is Status.UNVERIFIED


# ---------------------------------------------------------------------------
# Supplied, row by row
# ---------------------------------------------------------------------------

SUPPLIED = FIXTURES / "supplied"


def test_accepted_and_canonical_is_ok():
    result = verdict(SUPPLIED, Locator(file=SUPPLIED_INPUT))
    assert result.status is Status.OK
    assert result.notes == ()
    assert result.loaded is not None
    assert result.loaded.record["accepted"] is True
    assert len(result.loaded.text) == 15


def test_unlisted_but_canonical_is_ok_and_says_so(tmp_path):
    unlisted = tmp_path / "other.txt"
    unlisted.write_bytes(SUPPLIED_INPUT.read_bytes() + b"\r\n\r\n   \r\n")
    found = hash_file(unlisted)
    result = verdict(SUPPLIED, Locator(file=unlisted))
    assert result.status is Status.OK
    assert result.notes == (
        f"unlisted file sha256={found.sha256} md5={found.md5} size={found.size}",
    )
    assert result.loaded is not None
    assert result.loaded.record["accepted"] is False


def test_accepted_entry_whose_md5_disagrees_fails(source_copy):
    directory = source_copy("supplied")
    edit(directory, FILE.md5, OTHER_MD5)
    result = verdict(directory, Locator(file=SUPPLIED_INPUT))
    assert result.status is Status.FAIL
    assert "manifest error" in result.detail


def test_accepted_entry_without_md5_is_ok(source_copy):
    directory = source_copy("supplied")
    edit(directory, f'md5 = "{FILE.md5}", ', "")
    assert verdict(directory, Locator(file=SUPPLIED_INPUT)).status is Status.OK


def test_md5_alone_never_matches(source_copy):
    directory = source_copy("supplied")
    edit(directory, FILE.sha256, OTHER_SHA)
    # The file's md5 is still on the entry, but its sha256 isn't
    result = verdict(directory, Locator(file=SUPPLIED_INPUT))
    assert result.status is Status.OK
    assert result.loaded is not None
    assert result.loaded.record["accepted"] is False
    assert result.notes[0].startswith("unlisted file")
    # and a search, which only ever matches accepted entries, finds nothing
    searched = verdict(directory, Locator(supplied=SUPPLIED_INPUT.parent))
    assert searched.status is Status.UNVERIFIED


def drifting(monkeypatch):
    class Drifted(corpus_plugins.PlainExtractor):
        def extract(self, path):
            return super().extract(path) + "a line a new release added\n"

    def lookup(group, name):
        plugin = corpus_plugins.lookup(group, name)
        if plugin and group == records.EXTRACTORS:
            return records.Plugin(group, name, Drifted, "esoterica-tests", "1")
        return plugin

    monkeypatch.setattr(records, "lookup", lookup)


def test_accepted_but_not_canonical_fails_as_drift(monkeypatch):
    drifting(monkeypatch)
    result = verdict(SUPPLIED, Locator(file=SUPPLIED_INPUT))
    assert result.status is Status.FAIL
    assert "drifted" in result.detail


def test_neither_accepted_nor_canonical_fails(tmp_path):
    other = tmp_path / "other.txt"
    other.write_text("Some other book entirely.\n", encoding="utf-8")
    result = verdict(SUPPLIED, Locator(file=other))
    assert result.status is Status.FAIL
    assert "not accepted" in result.detail


def test_absent_is_unverified():
    result = verdict(SUPPLIED)
    assert result.status is Status.UNVERIFIED
    assert result.loaded is None


def test_absent_from_the_supplied_directory_is_unverified(tmp_path):
    (tmp_path / "unrelated.txt").write_bytes(b"x" * FILE.size)
    assert verdict(SUPPLIED, Locator(supplied=tmp_path)).status is Status.UNVERIFIED


def test_search_finds_an_accepted_file_by_size_then_sha256(tmp_path):
    (tmp_path / "a-same-size.txt").write_bytes(b"x" * FILE.size)
    (tmp_path / "b.mobi").write_bytes(SUPPLIED_INPUT.read_bytes())
    result = verdict(SUPPLIED, Locator(supplied=tmp_path))
    assert result.status is Status.OK
    assert result.notes == ()


def test_an_input_file_that_is_missing_fails(tmp_path):
    result = verdict(SUPPLIED, Locator(file=tmp_path / "nothing.txt"))
    assert result.status is Status.FAIL
    assert str(tmp_path) not in result.detail


def test_unregistered_extractor_fails_naming_group_and_name(source_copy):
    directory = source_copy("supplied")
    edit(directory, 'extractor = "plain"', 'extractor = "mobi"')
    result = verdict(directory, Locator(file=SUPPLIED_INPUT))
    assert result.status is Status.FAIL
    assert "'mobi'" in result.detail and "esoterica.extractors" in result.detail


def test_canonical_line_count_must_agree(source_copy):
    directory = source_copy("supplied")
    edit(directory, "lines = 15", "lines = 16")
    result = verdict(directory, Locator(file=SUPPLIED_INPUT))
    assert result.status is Status.FAIL
    assert "manifest error" in result.detail


@pytest.mark.parametrize("located", ["file", "supplied"])
def test_no_output_names_the_located_path(located):
    locator = (
        Locator(file=SUPPLIED_INPUT)
        if located == "file"
        else Locator(supplied=SUPPLIED_INPUT.parent)
    )
    result = verdict(SUPPLIED, locator)
    assert result.loaded is not None
    said = repr(result.loaded.record) + result.detail + "".join(result.notes)
    assert "supplied-input" not in said and "fixture.txt" not in said
