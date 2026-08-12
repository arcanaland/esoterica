from __future__ import annotations

import pytest
from esoterica_spec.validate import Report, check

META = """\
[meta]
schema_version = "1.0"
identifier = "land.arcana.dev/esoterica/example"
name = "Example"
license = "CC0-1.0"
"""

CARD = """\
[card."major_arcana.00".passages]
text = "A passage."
"""


@pytest.fixture
def meta() -> str:
    """The default [meta] table, for a test that needs to vary one line of it."""
    return META


@pytest.fixture
def scan(tmp_path):
    """Validate a document written from source, as the CLI would find it."""

    def run(text: str, *, explicit: bool = True) -> tuple[Report, bool]:
        path = tmp_path / "doc.toml"
        path.write_text(text, encoding="utf-8")
        return check(path, explicit)

    return run


@pytest.fixture
def validate(scan):
    """Validate a document that is expected to be a source at all.

    The default [meta] and one card keep every fixture down to the one rule
    under test: without the card, every document would also raise 11.1.
    """

    def run(body: str = "", *, meta: str = META, card: str = CARD) -> Report:
        report, is_source = scan(f"{meta}\n{card}\n{body}")
        assert is_source
        return report

    return run
