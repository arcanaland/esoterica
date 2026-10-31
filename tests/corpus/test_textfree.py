from __future__ import annotations

import pytest
from esoterica_corpus.textfree import MIN_LENGTH, fold, scan

# Written for the test. 63 characters, the length of the longest exempt
# string the RFC measured.
CANONICAL = (
    "Prelude\n\nThe  owl keeps the lantern lit while the miller sleeps in the loft.\nCoda\n"
)
FORTY = "owl keeps the lantern lit while the mill"
THIRTY_NINE = FORTY[:-1]
SIXTY_THREE = "The owl keeps the lantern lit while the miller sleeps in the lo"


@pytest.fixture
def source(tmp_path):
    def write(mapping: str, source: str = 'schema = 1\n[work]\ntitle = "t"\n') -> object:
        (tmp_path / "SOURCE.toml").write_text(source, encoding="utf-8")
        (tmp_path / "mapping.toml").write_text(mapping, encoding="utf-8")
        return scan(tmp_path, CANONICAL)

    return write


def test_lengths_are_what_the_test_says():
    assert MIN_LENGTH == 40
    assert len(fold(FORTY)) == 40
    assert len(fold(THIRTY_NINE)) == 39
    assert len(SIXTY_THREE) == 63


def test_forty_characters_fail(source):
    [finding] = source(f'[symbols]\nlabel = "{FORTY}"\n')
    assert (finding.file, finding.path, finding.length) == ("mapping.toml", "symbols.label", 40)


def test_thirty_nine_characters_pass(source):
    assert source(f'[symbols]\nlabel = "{THIRTY_NINE}"\n') == []


def test_an_exempt_key_passes_at_sixty_three(source):
    exempt = (
        f'[work]\ntitle = "{SIXTY_THREE}"\n'
        f'[work.prior_publication]\ntitle = "{SIXTY_THREE}"\n'
        f'[license]\nattribution_requested = "{SIXTY_THREE}"\n'
    )
    assert source("schema = 1\n", source=exempt) == []


def test_the_same_string_elsewhere_in_source_toml_fails(source):
    [finding] = source("schema = 1\n", source=f'[work]\nsubtitle = "{SIXTY_THREE}"\n')
    assert finding.path == "work.subtitle"


def test_case_and_whitespace_do_not_hide_a_match(source):
    disguised = "THE OWL keeps\\tthe lantern\\n  lit while the miller"
    [finding] = source(f'[x]\nlabel = "{disguised}"\n')
    assert finding.length == len(fold("the owl keeps the lantern lit while the miller"))


def test_keys_and_array_items_are_checked(source):
    findings = source(f'[x]\n"{FORTY}" = 1\nitems = ["short", "{FORTY}"]\n')
    assert sorted(f.path for f in findings) == ["x.items.1", f"x.{FORTY}"]


def test_a_failure_never_prints_the_matched_text(source):
    [finding] = source(f'[symbols]\nlabel = "{SIXTY_THREE}"\n')
    said = str(finding)
    assert "owl" not in said.casefold() and "lantern" not in said
    assert "63-character" in said
