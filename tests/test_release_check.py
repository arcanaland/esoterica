"""Every way a release can be refused, and the one way it is allowed"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import release_check

IDENTIFIER = "land.arcana.dev/esoterica/example-source"
DOCUMENT = f"""\
# SPDX-License-Identifier: CC0-1.0

[meta]
schema_version = "1.0"
identifier = "{IDENTIFIER}"
name = "Example"
license = "CC0-1.0"
version = "0.5"
"""

MANIFEST = f"""\
schema = 1
identifier = "{IDENTIFIER}"

[license]
spdx = "CC0-1.0"
license_file = "LICENSES/CC0-1.0.txt"
"""


@pytest.fixture
def repo(tmp_path) -> Path:
    """A tree shaped like this repository, holding one releasable source."""
    dist = tmp_path / "sources" / "example" / "dist"
    dist.mkdir(parents=True)
    (dist.parent / "SOURCE.toml").write_text(MANIFEST, encoding="utf-8")
    (dist / f"{IDENTIFIER.rsplit('/', 1)[-1]}.toml").write_text(DOCUMENT, encoding="utf-8")
    (dist / "PROVENANCE.toml").write_text("schema = 1\n", encoding="utf-8")

    licenses = tmp_path / "LICENSES"
    licenses.mkdir()
    (licenses / "CC0-1.0.txt").write_text("CC0.\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def git(repo):
    """Make the tree a git repository with one commit, and return a `git` runner."""

    def run(*args):
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@e",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@e",
                "PATH": "/usr/bin:/bin",
                "HOME": str(repo),
            },
        )

    run("init", "-q")
    run("add", "-A")
    run("commit", "-qm", "one")
    return run


def problems(repo: Path, version: str = "0.5", **kwargs) -> list[str]:
    return release_check.problems(repo, "example", version, **kwargs)


def test_a_releasable_source_has_no_problems(repo):
    assert problems(repo) == []


def test_unknown_source_is_refused(repo):
    assert release_check.problems(repo, "nobody", "0.5") == [
        f"no such source: {repo / 'sources' / 'nobody' / 'SOURCE.toml'} does not exist"
    ]


def test_version_disagreeing_with_the_document_is_refused(repo):
    (found,) = problems(repo, "0.4")
    assert "the tag claims version '0.4'" in found
    assert "[meta].version = '0.5'" in found


def test_filename_not_the_identifiers_last_segment_is_refused(repo):
    dist = repo / "sources" / "example" / "dist"
    (dist / "example-source.toml").rename(dist / "something-else.toml")

    (found,) = problems(repo)
    assert "is not its identifier's last segment" in found


def test_an_empty_dist_is_refused(repo):
    (repo / "sources" / "example" / "dist" / "example-source.toml").unlink()

    assert problems(repo) == ["dist/ holds no document beside PROVENANCE.toml"]


def test_two_documents_in_dist_are_refused(repo):
    dist = repo / "sources" / "example" / "dist"
    (dist / "another.toml").write_text(DOCUMENT, encoding="utf-8")

    (found,) = problems(repo)
    assert found.startswith("dist/ holds more than one document")


def test_a_missing_dist_is_refused(repo):
    dist = repo / "sources" / "example" / "dist"
    for path in dist.iterdir():
        path.unlink()
    dist.rmdir()

    (found,) = problems(repo)
    assert found.startswith("no dist/ directory")


def test_an_absent_tag_is_ignored_unless_required(repo):
    assert problems(repo) == []
    assert problems(repo, require_tag=True) == [
        "tag example/v0.5 does not exist in this checkout"
    ]


def test_a_lightweight_tag_is_refused(repo, git):
    git("tag", "example/v0.5")

    assert problems(repo, require_tag=True) == [
        "tag example/v0.5 is lightweight; a release tag must be annotated"
    ]
    # Refused even when the tag was not demanded: it exists and it is wrong.
    assert problems(repo) == [
        "tag example/v0.5 is lightweight; a release tag must be annotated"
    ]


def test_an_annotated_tag_is_allowed(repo, git):
    git("tag", "-a", "-m", "release", "example/v0.5")

    assert problems(repo, require_tag=True) == []


def test_identifier_is_read_from_the_document(repo):
    assert release_check.identifier(repo, "example") == IDENTIFIER


def test_assets_are_the_document_the_sidecar_and_the_licence(repo):
    found = [p.relative_to(repo).as_posix() for p in release_check.assets(repo, "example")]

    assert found == [
        "sources/example/dist/example-source.toml",
        "sources/example/dist/PROVENANCE.toml",
        "LICENSES/CC0-1.0.txt",
    ]
