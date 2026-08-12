#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""A simple deterministic TOML 1.0.0 writer

Guarantees:

    - Key order is the insertion order of the dicts handed in.
    - The same input produces the same bytes
    - Values longer than a line are written as multi-line basic strings,
      which the spec says it SHOULD for passage text.
"""

from __future__ import annotations

import math
import sys

# A value at least this long is written as a multi-line basic string
MULTILINE_THRESHOLD = 100

# An inline array wider than this is broken one element per line.
ARRAY_WIDTH = 76

BARE_KEY_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def _render_key(key: str) -> str:
    if key and all(c in BARE_KEY_CHARS for c in key):
        return key
    return _basic_string(key)


def _escape_common(text: str) -> str:
    """Escape backslashes and control characters. Quotes are the caller's."""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\n":
            out.append("\n")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return "".join(out)


def _basic_string(text: str) -> str:
    return '"' + _escape_common(text).replace("\n", "\\n").replace('"', '\\"') + '"'


def _multiline_string(text: str) -> str:
    body = _escape_common(text)
    # A run of three or more quotes would close the delimiter early.
    while '"""' in body:
        body = body.replace('"""', '""\\"')
    # So would a quote sitting immediately before the closing delimiter.
    if body.endswith('"'):
        body = body[:-1] + '\\"'
    # The newline directly after the opening delimiter is trimmed by TOML, so
    # this costs nothing and puts the first line of text at column zero.
    return '"""\n' + body + '"""'


def _render_string(text: str) -> str:
    if "\n" in text or len(text) > MULTILINE_THRESHOLD:
        return _multiline_string(text)
    return _basic_string(text)


def _render_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise TypeError(f"TOML cannot carry {value!r} portably")
        return repr(value)
    if isinstance(value, str):
        return _render_string(value)
    raise TypeError(f"not a TOML scalar: {type(value).__name__}")


def _render_array(values: list) -> str:
    if not values:
        return "[]"
    rendered = [_render_scalar(v) for v in values]
    oneline = "[" + ", ".join(rendered) + "]"
    if len(oneline) <= ARRAY_WIDTH and not any("\n" in r for r in rendered):
        return oneline
    return "[\n" + "".join(f"  {r},\n" for r in rendered) + "]"


def _render_value(value: object) -> str:
    if isinstance(value, list):
        return _render_array(value)
    return _render_scalar(value)


def _emit_table(table: dict, path: list[str], out: list[str]) -> None:
    pairs = []
    subtables = []
    for key, value in table.items():
        if not isinstance(key, str):
            raise TypeError(f"table key is not a string: {key!r}")
        if isinstance(value, dict):
            subtables.append((key, value))
        else:
            pairs.append((key, value))

    # A table with only subtables under it needs no header of its own
    if path and pairs:
        if out:
            out.append("")
        out.append("[" + ".".join(_render_key(p) for p in path) + "]")

    for key, value in pairs:
        out.append(f"{_render_key(key)} = {_render_value(value)}")

    for key, value in subtables:
        _emit_table(value, path + [key], out)


def dumps(table: dict) -> str:
    """Render one TOML document. Key order is the order of the dicts given."""
    if not isinstance(table, dict):
        raise TypeError("the document root must be a table")
    out: list[str] = []
    _emit_table(table, [], out)
    return "\n".join(out) + "\n"


def _self_test() -> int:
    import tomllib

    doc = {
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
        },
        "card": {
            "major_arcana.00": {
                "passages": {"light": "Light.", "advice": {"work": "Work."}},
                "correspondences": {"number": 0},
            }
        },
    }
    text = dumps(doc)
    roundtrip = tomllib.loads(text)
    if roundtrip != doc:
        print("FAIL emit.py: round trip is not equal", file=sys.stderr)
        print(text, file=sys.stderr)
        return 1
    if dumps(doc) != text:
        print("FAIL emit.py: two runs differ", file=sys.stderr)
        return 1
    if not text.endswith("\n"):
        print("FAIL emit.py: no trailing newline", file=sys.stderr)
        return 1
    print("ok   emit.py: round trip, determinism, trailing newline")
    return 0


if __name__ == "__main__":
    sys.exit(_self_test())
