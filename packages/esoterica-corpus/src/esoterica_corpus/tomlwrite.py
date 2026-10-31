"""A simple deterministic TOML 1.0.0 writer.
    - Key order is the insertion order of the dicts handed in.
    - The same input produces the same bytes
    - Values longer than a line are written as multi-line basic strings,
      which the spec says it SHOULD for passage text.
    - A table inside an array is written inline, on one line, so it holds
      scalars only.
"""

# TODO: should we replace this with a lib?

from __future__ import annotations

import math

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
    """Escape backslashes and control characters."""
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


def _render_inline_table(table: dict) -> str:
    pairs = []
    for key, value in table.items():
        if not isinstance(key, str):
            raise TypeError(f"table key is not a string: {key!r}")
        if isinstance(value, str):
            # A multi-line string would break the table across lines.
            pairs.append(f"{_render_key(key)} = {_basic_string(value)}")
        else:
            pairs.append(f"{_render_key(key)} = {_render_scalar(value)}")
    return "{ " + ", ".join(pairs) + " }" if pairs else "{}"


def _render_element(value: object) -> str:
    if isinstance(value, dict):
        return _render_inline_table(value)
    return _render_scalar(value)


def _render_array(values: list) -> str:
    if not values:
        return "[]"
    rendered = [_render_element(v) for v in values]
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
    """Render one TOML document."""
    if not isinstance(table, dict):
        raise TypeError("the document root must be a table")
    out: list[str] = []
    _emit_table(table, [], out)
    return "\n".join(out) + "\n"
