"""One source directory, from its manifests to its built file"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from esoterica_corpus import document, expected, provenance, records, tomlwrite
from esoterica_corpus.coverage import Coverage, cover
from esoterica_corpus.document import DocumentError
from esoterica_corpus.expected import ExpectedError
from esoterica_corpus.input import Loaded
from esoterica_corpus.ledger import Ledger, LedgerError
from esoterica_corpus.manifest import (
    ManifestError,
    Mapping,
    SourceManifest,
    SuppliedInput,
    VendoredInput,
    load_drops,
    load_mapping,
    load_source,
    read_toml,
)
from esoterica_corpus.records import Entry, PluginError, Record

SOURCE_GLOB = "sources/*/SOURCE.toml"
BUILDER = "esoterica-corpus"


class BuildError(Exception):
    pass


FAILURES = (BuildError, DocumentError, ExpectedError, LedgerError, ManifestError, PluginError)


def workspace_root(start: Path) -> Path:
    """The nearest directory at or above `start` whose pyproject.toml is a uv workspace."""
    for directory in (start, *start.parents):
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file() and "workspace" in read_toml(pyproject).get("tool", {}).get(
            "uv", {}
        ):
            return directory
    return start


def discover(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob(SOURCE_GLOB))


@dataclass(frozen=True, slots=True)
class Source:
    directory: Path
    manifest: SourceManifest

    @classmethod
    def open(cls, directory: Path) -> Source:
        manifest = directory / "SOURCE.toml"
        if not manifest.is_file():
            raise ManifestError(f"{directory} holds no SOURCE.toml")
        return cls(directory, load_source(manifest))

    @property
    def supplied(self) -> bool:
        return isinstance(self.manifest.input, SuppliedInput)


@dataclass(frozen=True, slots=True)
class Parsed:
    source: Source
    loaded: Loaded
    mapping: Mapping
    records: tuple[Record, ...]
    ledger: Ledger


@dataclass(frozen=True, slots=True)
class Built:
    parsed: Parsed
    document: dict[str, Any]
    output_name: str
    output_text: str
    provenance: dict[str, Any]

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256(self.output_text.encode("utf-8")).hexdigest()


def parse(source: Source, loaded: Loaded) -> Parsed:
    mapping = load_mapping(source.directory / "mapping.toml")
    if mapping.build is None:
        raise BuildError("mapping.toml has no [build].parser naming the source's parser")
    parser = records.resolve(records.PARSERS, mapping.build.parser).obj()
    found = tuple(parser.parse(loaded.text, mapping))
    return Parsed(source, loaded, mapping, found, Ledger.of(found))


def coverage(parsed: Parsed) -> Coverage:
    drops = parsed.source.directory / "drops.toml"
    if not drops.is_file():
        raise BuildError("no drops.toml, so coverage has nothing to account for drops with")
    return cover(parsed.loaded.text, parsed.ledger, load_drops(drops))


def build(parsed: Parsed) -> Built:
    source = parsed.source.manifest
    meta = document.meta(source, parsed.mapping)
    if parsed.source.supplied:
        document.check_rights(meta)

    entries = [r for r in parsed.records if isinstance(r, Entry)]
    doc = document.assemble(meta, entries, parsed.mapping.output)
    counts = expected.check(doc, parsed.mapping.expected)

    # REUSE-IgnoreStart
    header = f"# SPDX-License-Identifier: {source.license.spdx}\n\n"
    # REUSE-IgnoreEnd
    name = parsed.mapping.output.filename
    text = header + tomlwrite.dumps(doc)

    record = parsed.loaded.record
    if isinstance(source.input, VendoredInput):
        sidecar = provenance.vendored(
            builder=BUILDER,
            identifier=source.identifier,
            input_record=record,
            output_name=name,
            output_text=text,
            counts={"lines": record["lines"], **counts},
        )
    else:
        sidecar = provenance.supplied(
            identifier=source.identifier,
            input_record=record,
            output_name=name,
            output_text=text,
        )
    return Built(parsed, doc, name, text, sidecar)


def dist_problems(built: Built) -> list[str]:
    """What `build --check` finds wrong with the committed dist/. Empty means current."""
    dist = built.parsed.source.directory / "dist"
    output = dist / built.output_name
    sidecar = dist / "PROVENANCE.toml"
    problems = []

    if output.is_file():
        if output.read_text(encoding="utf-8") != built.output_text:
            problems.append(f"dist/{built.output_name} differs from a fresh build")
    elif not built.parsed.source.supplied:
        # Whether a supplied source commits dist/ is its repository's policy
        problems.append(f"dist/{built.output_name} is not committed")

    if not sidecar.is_file():
        problems.append("dist/PROVENANCE.toml is not committed")
    elif read_toml(sidecar).get("output", {}).get("sha256") != built.output_sha256:
        problems.append("dist/PROVENANCE.toml records a different output sha256")
    return problems


def write_dist(built: Built) -> Path:
    dist = built.parsed.source.directory / "dist"
    dist.mkdir(exist_ok=True)
    output = dist / built.output_name
    output.write_text(built.output_text, encoding="utf-8")
    (dist / "PROVENANCE.toml").write_text(tomlwrite.dumps(built.provenance), encoding="utf-8")
    return output
