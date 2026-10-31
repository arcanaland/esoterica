"""PROVENANCE.toml, the record of what produced a built file

Neither shape names a located input path. A supplied source's record is
text-free, so it can be committed where its input can't.
"""

from __future__ import annotations

import hashlib
import platform
import unicodedata
from typing import Any

NOTE = "Provenance for the built file beside this one."


def output_table(output_name: str, output_text: str) -> dict[str, str]:
    return {
        "path": f"dist/{output_name}",
        "sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
    }


def vendored(
    *,
    builder: str,
    identifier: str,
    input_record: dict[str, Any],
    output_name: str,
    output_text: str,
    counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema": 1,
        "note": NOTE,
        "build": {"builder": builder, "identifier": identifier},
        "input": {
            "path": input_record["path"],
            "sha256": input_record["sha256"],
            "lines": input_record["lines"],
        },
        "output": output_table(output_name, output_text),
        "counts": counts,
    }


def supplied(
    *,
    identifier: str,
    input_record: dict[str, Any],
    output_name: str,
    output_text: str,
) -> dict[str, Any]:
    extractor = input_record["extractor"]
    return {
        "schema": 1,
        "note": NOTE,
        "build": {
            "identifier": identifier,
            "python": platform.python_version(),
            "unidata": unicodedata.unidata_version,
        },
        "input": {
            "kind": "supplied",
            "file_sha256": input_record["file_sha256"],
            "accepted": input_record["accepted"],
            "canonical_sha256": input_record["canonical_sha256"],
            "lines": input_record["lines"],
            "extractor": {
                "name": extractor["name"],
                "distribution": extractor["distribution"],
                "version": extractor["version"],
            },
        },
        "output": output_table(output_name, output_text),
    }
