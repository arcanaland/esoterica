"""The `esoterica` command, in process, with the fixture plugins registered"""

from __future__ import annotations

from pathlib import Path

import pytest
from corpus_plugins import FIXTURES, SUPPLIED_INPUT
from esoterica_corpus.cli import app
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED = str(FIXTURES / "vendored")
SUPPLIED = str(FIXTURES / "supplied")
MCELROY_SHA = "4f365123c518c05beb013a784b79e9a742c823ae221e626a5ab5a009d2c1e317"


@pytest.fixture(autouse=True)
def at_root(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("ESOTERICA_SUPPLIED", raising=False)


def run(*args: str, **env: str):
    return CliRunner().invoke(app, list(args), env=env or None)


def test_help_lists_six_subcommands():
    result = run("--help")
    assert result.exit_code == 0
    for command in ("build", "coverage", "validate", "verify-input", "textfree", "check"):
        assert command in result.output


def test_verify_input_on_mcelroy():
    result = run("verify-input", "sources/mcelroy")
    assert result.exit_code == 0
    assert result.output == f"ok   sources/mcelroy  {MCELROY_SHA}\n"


def test_discovery_without_arguments_finds_mcelroy():
    result = run("verify-input")
    assert result.exit_code == 0
    assert f"ok   sources/mcelroy  {MCELROY_SHA}" in result.output


def test_building_mcelroy_fails_clearly_until_its_parser_exists():
    result = run("build", "sources/mcelroy")
    assert result.exit_code == 1
    assert "FAIL sources/mcelroy: mapping.toml has no [build].parser" in result.output


def test_an_unregistered_parser_is_named(source_copy):
    directory = source_copy("vendored")
    mapping = directory / "mapping.toml"
    mapping.write_text(
        mapping.read_text(encoding="utf-8").replace('"fixture"', '"mcelroy"'), encoding="utf-8"
    )
    result = run("build", str(directory))
    assert result.exit_code == 1
    assert "nothing named 'mcelroy' is registered" in result.output
    assert '"esoterica.sources"' in result.output


def test_check_is_green_on_the_vendored_fixture():
    result = run("check", VENDORED)
    assert result.exit_code == 0, result.output
    assert "FAIL" not in result.output
    for gate in ("coverage:", "build --check:", "validate:"):
        assert gate in result.output


def test_check_is_green_on_the_supplied_fixture():
    result = run("check", SUPPLIED, "--input", str(SUPPLIED_INPUT))
    assert result.exit_code == 0, result.output
    assert "FAIL" not in result.output
    for gate in ("textfree:", "coverage:", "build --check:", "validate:"):
        assert gate in result.output
    assert "supplied-input" not in result.output


def test_check_finds_the_supplied_input_through_the_environment():
    result = run("check", SUPPLIED, ESOTERICA_SUPPLIED=str(SUPPLIED_INPUT.parent))
    assert result.exit_code == 0, result.output


def test_check_with_the_input_absent_is_unverified_and_fails():
    result = run("check", SUPPLIED)
    assert result.exit_code == 1
    assert result.output.startswith("unverified ")
    assert "ok " not in result.output


def test_allow_absent_exits_zero_and_still_says_unverified():
    result = run("verify-input", SUPPLIED, "--allow-absent")
    assert result.exit_code == 0
    assert result.output.startswith("unverified ")
    assert "ok " not in result.output


def test_every_source_gets_exactly_one_result_line():
    result = run("verify-input", VENDORED, SUPPLIED, "sources/mcelroy")
    assert result.exit_code == 1
    assert len(result.output.splitlines()) == 3


def test_input_needs_exactly_one_source_dir():
    result = run("verify-input", VENDORED, SUPPLIED, "--input", str(SUPPLIED_INPUT))
    assert result.exit_code == 2


def test_input_refuses_a_vendored_source():
    result = run("verify-input", VENDORED, "--input", str(SUPPLIED_INPUT))
    assert result.exit_code == 2


def test_a_source_outside_the_repository_builds(source_copy):
    directory = source_copy("vendored")
    assert not directory.is_relative_to(REPO_ROOT)
    result = run("check", str(directory))
    assert result.exit_code == 0, result.output


def test_build_check_finds_a_stale_dist(source_copy):
    directory = source_copy("vendored")
    built = directory / "dist/fixture-vendored.toml"
    built.write_text(built.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = run("build", str(directory), "--check")
    assert result.exit_code == 1
    assert "differs from a fresh build" in result.output
    assert "records a different output sha256" not in result.output


def test_build_check_on_a_supplied_source_compares_provenance(source_copy):
    directory = source_copy("supplied")
    sidecar = directory / "dist/PROVENANCE.toml"
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace('sha256 = "3', 'sha256 = "4'),
        encoding="utf-8",
    )
    result = run("build", str(directory), "--check", "--input", str(SUPPLIED_INPUT))
    assert result.exit_code == 1
    assert "records a different output sha256" in result.output


def test_build_writes_dist(source_copy):
    directory = source_copy("vendored")
    (directory / "dist/fixture-vendored.toml").unlink()
    assert run("build", str(directory)).exit_code == 0
    assert run("build", str(directory), "--check").exit_code == 0


def test_textfree_fails_on_a_pasted_passage_without_printing_it(source_copy):
    directory = source_copy("supplied")
    passage = "Twenty-two cards, one road, and a traveller who keeps coming back."
    with (directory / "mapping.toml").open("a", encoding="utf-8") as handle:
        handle.write(f'\n[notes]\nwhy = "{passage}"\n')
    result = run("textfree", str(directory), "--input", str(SUPPLIED_INPUT))
    assert result.exit_code == 1
    assert "mapping.toml at notes.why holds a 66-character string" in result.output
    assert "traveller" not in result.output


def test_textfree_skips_a_vendored_source():
    result = run("textfree", VENDORED)
    assert result.exit_code == 0
    assert result.output.startswith("skip ")


def test_coverage_fails_on_an_unclaimed_line(source_copy):
    directory = source_copy("vendored")
    drops = directory / "drops.toml"
    drops.write_text(drops.read_text(encoding="utf-8").replace('lines = "1"', 'lines = "2"'))
    result = run("coverage", str(directory))
    assert result.exit_code == 1
    assert "line 1: 'A Fixture Book of Three Cards' is unclaimed" in result.output


def test_validate_delegates_to_the_spec_validator():
    result = run("validate", str(FIXTURES / "vendored/dist/fixture-vendored.toml"))
    assert result.exit_code == 0, result.output
