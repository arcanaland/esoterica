"""McElroy's keywords: the first is lowercased and nothing else changes (TASK-071)"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "sources" / "mcelroy"


def load_build():
    spec = importlib.util.spec_from_file_location("mcelroy_build", SOURCE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def printed_keywords() -> dict[str, list[str]]:
    """Each card's Keywords line, split but otherwise as the input prints it."""
    build = load_build()
    builder, _, _ = build.build()
    separator = builder.mapping["sections"]["keywords_separator"]
    printed = {}
    for line_no, claim in builder.claims.by_line.items():
        target = claim["claim"]
        if target.endswith(".passages.keywords"):
            card_id = target.split('"')[1]
            text = build.undent(builder.lines[line_no - 1])
            printed[card_id] = [w for w in text.split(separator) if w]
    return printed


def built_keywords() -> dict[str, list[str]]:
    (path,) = (SOURCE / "dist").glob("mcelroy-*.toml")
    cards = tomllib.loads(path.read_text(encoding="utf-8"))["card"]
    return {card_id: card["passages"]["keywords"] for card_id, card in cards.items()}


def test_first_keyword_is_lowercase_and_no_other_changes():
    printed, built = printed_keywords(), built_keywords()
    assert len(built) == 78
    assert printed.keys() == built.keys()
    for card_id, words in built.items():
        first, *rest = printed[card_id]
        assert words[0][:1].islower(), card_id
        assert words == [first[:1].lower() + first[1:], *rest], card_id
