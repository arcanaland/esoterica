"""The `esoterica` command"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from esoterica_spec import validate as spec

from esoterica_corpus import pipeline, textfree
from esoterica_corpus.input import Locator, Status, Verdict, load
from esoterica_corpus.pipeline import FAILURES, Built, Parsed, Source

app = typer.Typer(no_args_is_help=True, add_completion=False)

SourceDirs = Annotated[
    list[Path] | None,
    typer.Argument(
        metavar="[SOURCE_DIR]...",
        help="Directories holding a SOURCE.toml. Default: sources/*/ in the workspace.",
        show_default=False,
    ),
]
InputFile = Annotated[
    Path | None,
    typer.Option("--input", help="The supplied input file, for exactly one SOURCE_DIR."),
]
SuppliedDir = Annotated[
    Path | None,
    typer.Option(
        "--supplied",
        envvar="ESOTERICA_SUPPLIED",
        help="A directory searched for accepted supplied inputs.",
    ),
]
AllowAbsent = Annotated[
    bool,
    typer.Option(
        "--allow-absent", help="Exit 0 when an input is unverified. It still says so."
    ),
]


class Report:
    def __init__(self, allow_absent: bool) -> None:
        self.allow_absent = allow_absent
        self.failed = False

    def ok(self, name: str, detail: str) -> None:
        typer.echo(f"ok   {name}  {detail}")

    def note(self, name: str, detail: str) -> None:
        typer.echo(f"     {name}  {detail}")

    def fail(self, name: str, detail: str) -> None:
        self.failed = True
        typer.echo(f"FAIL {name}: {detail}")

    def unverified(self, name: str, detail: str) -> None:
        if not self.allow_absent:
            self.failed = True
        typer.echo(f"unverified {name}: {detail}")

    def verdict(self, name: str, verdict: Verdict) -> None:
        {
            Status.OK: self.ok,
            Status.FAIL: self.fail,
            Status.UNVERIFIED: self.unverified,
        }[verdict.status](name, verdict.detail)
        for note in verdict.notes:
            self.note(name, note)

    def exit(self) -> None:
        raise typer.Exit(1 if self.failed else 0)


def display(directory: Path) -> str:
    try:
        return str(directory.relative_to(Path.cwd()))
    except ValueError:
        return str(directory)


def directories(given: list[Path] | None) -> list[Path]:
    if given:
        return [d.resolve() for d in given]
    root = pipeline.workspace_root(Path.cwd())
    found = pipeline.discover(root)
    if not found:
        typer.echo(f"esoterica: no files matched {pipeline.SOURCE_GLOB} under {root}")
        raise typer.Exit(1)
    return found


def locator(dirs: list[Path], input_file: Path | None, supplied: Path | None) -> Locator:
    if input_file is not None and len(dirs) != 1:
        raise typer.BadParameter("--input needs exactly one SOURCE_DIR", param_hint="--input")
    return Locator(file=input_file, supplied=supplied)


type Step = Callable[[Report, str, Source, Verdict], None]


def each(
    given: list[Path] | None,
    input_file: Path | None,
    supplied: Path | None,
    allow_absent: bool,
    step: Step,
) -> None:
    """Open every source, load its input, and hand the result to one step."""
    dirs = directories(given)
    where = locator(dirs, input_file, supplied)
    report = Report(allow_absent)
    for directory in dirs:
        name = display(directory)
        try:
            source = Source.open(directory)
            if input_file is not None and not source.supplied:
                raise typer.BadParameter(
                    "--input applies only to a supplied source", param_hint="--input"
                )
            step(report, name, source, load(directory, source.manifest, where))
        except FAILURES as exc:
            report.fail(name, str(exc))
    report.exit()


def loaded(report: Report, name: str, verdict: Verdict) -> bool:
    """Report an input that can't be built from, once. True when it can."""
    if verdict.status is Status.OK:
        return True
    report.verdict(name, verdict)
    return False


# ---------------------------------------------------------------------------
# One gate each
# ---------------------------------------------------------------------------


def gate_build_check(report: Report, name: str, built: Built) -> None:
    problems = pipeline.dist_problems(built)
    for problem in problems:
        report.fail(name, f"build --check: {problem}")
    if problems:
        return
    if (built.parsed.source.directory / "dist" / built.output_name).is_file():
        report.ok(name, f"build --check: dist/{built.output_name} is current")
    else:
        report.ok(name, "build --check: the output matches PROVENANCE.toml's sha256")


def gate_coverage(report: Report, name: str, parsed: Parsed) -> None:
    result = pipeline.coverage(parsed)
    for problem in result.problems:
        report.fail(name, f"coverage: {problem}")
    if result.ok:
        report.ok(name, f"coverage: {result.summary()}")


def gate_validate(report: Report, name: str, built: Built) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / built.output_name
        path.write_text(built.output_text, encoding="utf-8")
        result, _ = spec.check(path, explicit=True)
    for warning in result.warnings:
        typer.echo(f"WARN {name}: validate: {spec.render(warning)}")
    for error in result.errors:
        report.fail(name, f"validate: {spec.render(error)}")
    if not result.errors:
        report.ok(name, f"validate: {built.output_name}")


def gate_textfree(report: Report, name: str, source: Source, verdict: Verdict) -> None:
    assert verdict.loaded is not None and verdict.loaded.canonical is not None
    findings = textfree.scan(source.directory, verdict.loaded.canonical)
    for finding in findings:
        report.fail(name, f"textfree: {finding}")
    if not findings:
        report.ok(name, f"textfree: nothing of {textfree.MIN_LENGTH}+ characters is verbatim")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def build(
    sources: SourceDirs = None,
    check: Annotated[
        bool, typer.Option("--check", help="Rebuild in memory and diff against dist/.")
    ] = False,
    input_file: InputFile = None,
    supplied: SuppliedDir = None,
    allow_absent: AllowAbsent = False,
) -> None:
    """Build every source's dist/ file, or check that it is current."""

    def step(report: Report, name: str, source: Source, verdict: Verdict) -> None:
        if not loaded(report, name, verdict):
            return
        assert verdict.loaded is not None
        built = pipeline.build(pipeline.parse(source, verdict.loaded))
        if check:
            gate_build_check(report, name, built)
        else:
            output = pipeline.write_dist(built)
            report.ok(name, f"build: dist/{output.name}  {len(built.output_text)} characters")

    each(sources, input_file, supplied, allow_absent, step)


@app.command()
def coverage(
    sources: SourceDirs = None,
    input_file: InputFile = None,
    supplied: SuppliedDir = None,
    allow_absent: AllowAbsent = False,
) -> None:
    """Fail unless every input unit is mapped or dropped."""

    def step(report: Report, name: str, source: Source, verdict: Verdict) -> None:
        if loaded(report, name, verdict):
            assert verdict.loaded is not None
            gate_coverage(report, name, pipeline.parse(source, verdict.loaded))

    each(sources, input_file, supplied, allow_absent, step)


@app.command()
def validate(
    files: Annotated[list[Path] | None, typer.Argument(metavar="[FILE]...")] = None,
) -> None:
    """Validate built files against the spec's rules."""
    raise typer.Exit(spec.main([str(f) for f in files or []]))


@app.command("verify-input")
def verify_input(
    sources: SourceDirs = None,
    input_file: InputFile = None,
    supplied: SuppliedDir = None,
    allow_absent: AllowAbsent = False,
) -> None:
    """Verify every source's input against its recorded hashes."""

    def step(report: Report, name: str, source: Source, verdict: Verdict) -> None:
        report.verdict(name, verdict)

    each(sources, input_file, supplied, allow_absent, step)


@app.command("textfree")
def textfree_command(
    sources: SourceDirs = None,
    input_file: InputFile = None,
    supplied: SuppliedDir = None,
    allow_absent: AllowAbsent = False,
) -> None:
    """Fail if a supplied source's TOML carries its input's text."""

    def step(report: Report, name: str, source: Source, verdict: Verdict) -> None:
        if not source.supplied:
            typer.echo(f"skip {name}: textfree applies only to supplied sources")
        elif loaded(report, name, verdict):
            gate_textfree(report, name, source, verdict)

    each(sources, input_file, supplied, allow_absent, step)


@app.command("check")
def check_command(
    sources: SourceDirs = None,
    input_file: InputFile = None,
    supplied: SuppliedDir = None,
    allow_absent: AllowAbsent = False,
) -> None:
    """Every gate: verify-input, build --check, coverage, validate and textfree."""

    def step(report: Report, name: str, source: Source, verdict: Verdict) -> None:
        report.verdict(name, verdict)
        if verdict.status is not Status.OK:
            return
        assert verdict.loaded is not None
        # Ordered so that a failure, which ends the source's run, hides as little as it can
        if source.supplied:
            gate_textfree(report, name, source, verdict)
        parsed = pipeline.parse(source, verdict.loaded)
        gate_coverage(report, name, parsed)
        built = pipeline.build(parsed)
        gate_build_check(report, name, built)
        gate_validate(report, name, built)

    each(sources, input_file, supplied, allow_absent, step)
