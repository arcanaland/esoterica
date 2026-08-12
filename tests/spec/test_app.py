from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "key", ["land.arcana", "land.arcana.cartomancer", "a.b"]
)
def test_realm_accepted(validate, key):
    assert validate(f'[app."{key}"]\nanything = true\n').findings == []


@pytest.mark.parametrize("key", ["land", "land.", ".arcana", "Land.Arcana"])
def test_realm_rejected(validate, key):
    report = validate(f'[app."{key}"]\nanything = true\n')
    assert [(f.level, f.spec) for f in report.findings] == [("E", "10")]
