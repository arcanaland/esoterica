from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, get_args

from esoterica_corpus import records
from esoterica_corpus.manifest import (
    Accepted,
    Drop,
    FetchedInput,
    NormalizeStep,
    Repairs,
    SourceManifest,
    SuppliedInput,
    VendoredInput,
)
from esoterica_corpus.records import Unit

ACCENT_MARKS = {"acute": "́", "grave": "̀"}

STEPS: dict[str, Callable[[str], str]] = {
    "nfc": lambda t: unicodedata.normalize("NFC", t),
    "lf": lambda t: t.replace("\r\n", "\n").replace("\r", "\n"),
    "rstrip": lambda t: "\n".join(line.rstrip() for line in t.split("\n")),
    "squeeze-blank": lambda t: re.sub(r"\n{3,}", "\n\n", t),
    "trim": lambda t: t.strip("\n") + "\n",
}

assert set(STEPS) == set(get_args(NormalizeStep)), "manifest and input disagree on steps"


# ---------------------------------------------------------------------------
# The text a parser reads
# ---------------------------------------------------------------------------


def parse_range(spec: str) -> list[int]:
    if "-" in spec:
        first, last = spec.split("-", 1)
        return list(range(int(first), int(last) + 1))
    return [int(spec)]


@dataclass(frozen=True, slots=True)
class InputText:
    """A text input's repaired lines. Its units are 1-based line numbers."""

    lines: tuple[str, ...]

    def __init__(self, lines) -> None:
        object.__setattr__(self, "lines", tuple(lines))

    def __len__(self) -> int:
        return len(self.lines)

    def line(self, number: int) -> str:
        return self.lines[number - 1]

    def units(self) -> range:
        return range(1, len(self.lines) + 1)

    def drop_units(self, drop: Drop) -> list[Unit]:
        if drop.rule == "blank":
            return [n for n, text in enumerate(self.lines, 1) if not text.strip()]

        assert drop.lines is not None
        return list(parse_range(drop.lines))

    def describe(self, unit: Unit) -> str:
        if isinstance(unit, int) and 1 <= unit <= len(self.lines):
            return f"line {unit}: {self.line(unit)[:60]!r}"
        return f"line {unit!r}"


def split_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def repair(line: str, repairs: Repairs) -> str:
    """Undo the input's encoding defects."""
    for wrong, right in repairs.mojibake.items():
        line = line.replace(wrong, right)

    accents = repairs.accents
    if accents:
        pattern = "|".join(re.escape(k) for k in accents)
        line = re.sub(
            f"(.)({pattern})",
            lambda m: unicodedata.normalize(
                "NFC", m.group(1) + ACCENT_MARKS[accents[m.group(2)]]
            ),
            line,
        )
    return line


def normalize(text: str, steps: list[str]) -> str:
    for step in steps:
        text = STEPS[step](text)
    return text


def canonical_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class Status(StrEnum):
    OK = "ok"
    UNVERIFIED = "unverified"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class Loaded:
    text: InputText
    # The [input] table of PROVENANCE.toml
    record: dict[str, Any]
    # Canonical text before repair
    canonical: str | None = None


@dataclass(frozen=True, slots=True)
class Verdict:
    status: Status
    detail: str
    notes: tuple[str, ...] = ()
    loaded: Loaded | None = field(default=None)


def fail(detail: str) -> Verdict:
    return Verdict(Status.FAIL, detail)


@dataclass(frozen=True, slots=True)
class Locator:
    """Where a supplied input may be."""

    file: Path | None = None
    supplied: Path | None = None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load(directory: Path, manifest: SourceManifest, locator: Locator | None = None) -> Verdict:
    spec = manifest.input
    match spec:
        case VendoredInput():
            return load_vendored(directory, spec)
        case SuppliedInput():
            return load_supplied(spec, locator or Locator())
        case FetchedInput():
            return Verdict(Status.UNVERIFIED, 'kind = "fetched": no bytes are local')
    raise AssertionError(spec)


def load_vendored(directory: Path, spec: VendoredInput) -> Verdict:
    path = directory / spec.path
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return fail(f"[input].path {spec.path} cannot be read: {exc.strerror}")

    actual = hashlib.sha256(raw).hexdigest()
    if actual != spec.sha256:
        return fail(f"sha256 mismatch: recorded {spec.sha256}, found {actual}")

    try:
        decoded = raw.decode(spec.encoding.declared)
    except (LookupError, UnicodeDecodeError) as exc:
        return fail(f"{spec.path} does not decode as {spec.encoding.declared}: {exc}")

    text = InputText(repair(line, spec) for line in split_lines(decoded))
    record = {"path": spec.path, "sha256": spec.sha256, "lines": len(text)}
    return Verdict(Status.OK, actual, loaded=Loaded(text, record))


@dataclass(frozen=True, slots=True)
class FileHashes:
    sha256: str
    md5: str
    size: int


def hash_file(path: Path) -> FileHashes:
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return FileHashes(sha.hexdigest(), md5.hexdigest(), size)


def search(directory: Path, accepted: list[Accepted]) -> Path | None:
    """The first file at the directory's top level that is an accepted entry."""
    sizes = {entry.size for entry in accepted}
    wanted = {entry.sha256 for entry in accepted}
    try:
        candidates = sorted(p for p in directory.iterdir() if p.is_file())
    except OSError:
        return None
    for path in candidates:
        if path.stat().st_size in sizes and hash_file(path).sha256 in wanted:
            return path
    return None


def load_supplied(spec: SuppliedInput, locator: Locator) -> Verdict:
    if locator.file is not None:
        path = locator.file
        if not path.is_file():
            return fail("--input does not name a readable file")
    elif locator.supplied is not None:
        found = search(locator.supplied, spec.accepted)
        if found is None:
            return Verdict(
                Status.UNVERIFIED, "input absent: no accepted file in the supplied directory"
            )
        path = found
    else:
        return Verdict(Status.UNVERIFIED, "input absent: pass --input or --supplied")

    # Tier 1: the file
    hashes = hash_file(path)
    entry = next((e for e in spec.accepted if e.sha256 == hashes.sha256), None)
    if entry is not None:
        if entry.md5 is not None and entry.md5 != hashes.md5:
            return fail(
                f"manifest error: the accepted entry sha256={entry.sha256} records "
                f"md5={entry.md5}, but its file's md5 is {hashes.md5}"
            )
        if entry.size != hashes.size:
            return fail(
                f"manifest error: the accepted entry sha256={entry.sha256} records "
                f"size={entry.size}, but its file is {hashes.size} bytes"
            )

    # Extract and normalize
    name = spec.extraction.extractor
    try:
        plugin = records.resolve(records.EXTRACTORS, name)
        extracted = plugin.obj().extract(path)
    except records.PluginError as exc:
        return fail(str(exc))
    except Exception as exc:  # noqa: BLE001  (an extractor is third-party code)
        return fail(f"extractor {name!r} raised {type(exc).__name__}: {exc}")
    if not isinstance(extracted, str):
        return fail(f"extractor {name!r} returned {type(extracted).__name__}, not str")
    canonical = normalize(extracted, spec.extraction.normalize)

    # Tier 2: the canonical text
    actual = canonical_sha256(canonical)
    if actual != spec.canonical.sha256:
        if entry is not None:
            return fail(
                f"an accepted file no longer yields the canonical text, so extractor "
                f"{name!r} drifted: recorded {spec.canonical.sha256}, found {actual}"
            )
        return fail(
            f"the file is not accepted and does not yield the canonical text: "
            f"recorded {spec.canonical.sha256}, found {actual}"
        )

    lines = canonical.count("\n")

    if lines != spec.canonical.lines:
        return fail(
            f"manifest error: the canonical text matches its sha256 and has {lines} "
            f"lines, but [input.canonical].lines records {spec.canonical.lines}"
        )

    notes = ()
    if entry is None:
        notes = (f"unlisted file sha256={hashes.sha256} md5={hashes.md5} size={hashes.size}",)
    text = InputText(repair(line, spec) for line in split_lines(canonical))
    record = {
        "kind": "supplied",
        "file_sha256": hashes.sha256,
        "accepted": entry is not None,
        "canonical_sha256": actual,
        "lines": lines,
        "extractor": {
            "name": name,
            "distribution": plugin.distribution,
            "version": plugin.version,
        },
    }
    return Verdict(
        Status.OK, f"canonical {actual}", notes, Loaded(text, record, canonical=canonical)
    )
