"""The writer is the one thing between a document and the product bytes"""

from __future__ import annotations

import tomllib
from pathlib import Path

from esoterica_corpus.tomlwrite import dumps

REPO_ROOT = Path(__file__).resolve().parents[2]
MCELROY = REPO_ROOT / "sources/mcelroy/dist/mcelroy-a-guide-to-tarot-card-meanings-2014.toml"

DOC = {
    "meta": {
        "schema_version": "1.0",
        "name": 'A "quoted" name',
        "count": 78,
        "ok": True,
        "long": "x" * 150,
        "para": "First line.\n\nSecond line.",
        "tail": 'ends in a quote"',
        "triple": 'a """ b',
        "list": ["one", "two"],
        "wide": ["a rather long element indeed", "another long element here"],
        "related": [{"rel": "pattern", "target": "example.org/pattern/x", "n": 1}],
    },
    "card": {
        "major_arcana.00": {
            "passages": {"light": "Light.", "advice": {"work": "Work."}},
            "correspondences": {"number": 0},
        }
    },
}


def test_mcelroy_round_trips_byte_for_byte():
    header, _, body = MCELROY.read_text(encoding="utf-8").partition("\n\n")
    # REUSE-IgnoreStart
    assert header.startswith("# SPDX-License-Identifier: ")
    # REUSE-IgnoreEnd
    assert dumps(tomllib.loads(body)) == body


def test_round_trip_is_equal():
    assert tomllib.loads(dumps(DOC)) == DOC


def test_two_runs_are_identical():
    assert dumps(DOC) == dumps(DOC)


def test_ends_in_a_newline():
    assert dumps(DOC).endswith("\n")
