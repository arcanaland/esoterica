"""Every built source in the tree validates clean: zero errors, zero warnings.

Rooted at the repository, not at the working directory, so pytest finds the same
files wherever it is invoked from.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from esoterica_spec.validate import DEFAULT_GLOB, check, render

REPO_ROOT = Path(__file__).resolve().parent.parent


def sources() -> list[Path]:
    found = []
    for path in sorted(REPO_ROOT.glob(DEFAULT_GLOB)):
        # 2.2.1: a candidate that is not a source is not one of ours to check.
        if check(path, explicit=False)[1]:
            found.append(path)
    return found


def test_at_least_one_source_is_built():
    assert sources(), f"no source matched {DEFAULT_GLOB}"


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.parent.parent.name)
def test_source_is_clean(path):
    report, _ = check(path)
    assert [render(f) for f in report.findings] == []
