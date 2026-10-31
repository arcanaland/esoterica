from __future__ import annotations

import shutil
from pathlib import Path

import corpus_plugins
import pytest
from corpus_plugins import FIXTURES
from esoterica_corpus import records


@pytest.fixture(autouse=True)
def registered(monkeypatch):
    """The fixture parser and the `plain` extractor, without installed metadata."""
    monkeypatch.setattr(records, "lookup", corpus_plugins.lookup)


@pytest.fixture
def source_copy(tmp_path):
    """A fixture source copied somewhere a test may change it."""

    def copy(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(FIXTURES / name, target)
        return target

    return copy
