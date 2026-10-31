"""The three TOML files in a source directory"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MD5 = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]

# The closed set of normalize steps. input.STEPS implements exactly these.
NormalizeStep = Literal["nfc", "lf", "rstrip", "squeeze-blank", "trim"]
Accent = Literal["acute", "grave"]


class ManifestError(Exception):
    pass


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Open(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


# ---------------------------------------------------------------------------
# SOURCE.toml
# ---------------------------------------------------------------------------


class Work(Open):
    title: str


class License(Open):
    spdx: str
    attribution_requested: str | None = None


class Encoding(Strict):
    declared: str


class Repairs(Strict):
    """Encoding defects undone line by line, after every hash gate."""

    mojibake: dict[str, str] = {}
    accents: dict[str, Accent] = {}


class VendoredInput(Repairs):
    kind: Literal["vendored"]
    path: str
    sha256: SHA256
    encoding: Encoding


class FetchedInput(Open):
    kind: Literal["fetched"]
    sha256: SHA256


class Accepted(Strict):
    sha256: SHA256
    md5: MD5 | None = None
    size: Annotated[int, Field(ge=0)]
    format: str


class Extraction(Strict):
    extractor: str
    normalize: list[NormalizeStep]


class Canonical(Strict):
    sha256: SHA256
    lines: Annotated[int, Field(ge=0)]


class SuppliedInput(Repairs):
    kind: Literal["supplied"]
    accepted: Annotated[list[Accepted], Field(min_length=1)]
    extraction: Extraction
    canonical: Canonical


Input = Annotated[VendoredInput | FetchedInput | SuppliedInput, Field(discriminator="kind")]


class SourceManifest(Open):
    schema_: int = Field(alias="schema")
    identifier: str
    work: Work
    license: License
    input: Input


# ---------------------------------------------------------------------------
# mapping.toml
# ---------------------------------------------------------------------------


class Build(Open):
    parser: str


class Output(Open):
    filename: str
    passage_order: list[str] = []
    advice_order: list[str] = []
    correspondence_order: list[str] = []
    group_order: list[str] = []


class Mapping(Open):
    """The parts of mapping.toml the pipeline reads."""

    build: Build | None = None
    expected: dict[str, Annotated[int, Field(strict=True, ge=0)]] | None = None
    meta: dict[str, Any] = {}
    output: Output

    _raw: dict[str, Any] = PrivateAttr(default_factory=dict)

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw


# ---------------------------------------------------------------------------
# drops.toml
# ---------------------------------------------------------------------------


class Drop(Strict):
    reason: Annotated[str, Field(min_length=1)]
    lines: str | None = None
    rule: Literal["blank"] | None = None

    @model_validator(mode="after")
    def one_selector(self) -> Drop:
        if (self.lines is None) == (self.rule is None):
            raise ValueError("a drop names exactly one of `lines` or `rule`")
        return self


class Drops(Strict):
    schema_: int = Field(alias="schema")
    drop: list[Drop] = []


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"{path.name}: {exc}") from exc


def _model[M: BaseModel](cls: type[M], path: Path, data: dict[str, Any]) -> M:
    try:
        return cls.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or '(root)'}: {error['msg']}"
            for error in exc.errors()
        )
        raise ManifestError(f"{path.name}: {problems}") from exc


def load_source(path: Path) -> SourceManifest:
    return _model(SourceManifest, path, read_toml(path))


def load_mapping(path: Path) -> Mapping:
    data = read_toml(path)
    mapping = _model(Mapping, path, data)
    mapping._raw = data
    return mapping


def load_drops(path: Path) -> Drops:
    return _model(Drops, path, read_toml(path))
