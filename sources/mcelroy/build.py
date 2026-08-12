#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Build the McElroy source into a conforming esoterica document

build.py                  write dist/ and PROVENANCE.toml
build.py --check          rebuild into memory and diff against what is committed
build.py --mapped-lines   print, as JSON, which input line produced what

"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tomllib
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import emit  # noqa: E402  (path is set immediately above)

# Manually checked
EXPECTED = {
    "lines": 2658,
    "cards": 78,
    "majors": 22,
    "minors": 56,
    "keywords": 78,
    "light": 78,
    "shadow": 78,
    "advice": 78 * 6,
    "symbols": 331,
    "questions": 234,
    "notes": 3,
    "archetype": 22,
    "hebrew": 22,
    "numbers": 22,
    "planetary": 22,
    "mythical_spiritual": 22,
    "numerology": 40,
    "astrology": 40,
    "affirmation": 56,
    "personality": 16,
    "elemental": 16,
    "story": 78,
}

ACCENT_MARKS = {"acute": "́", "grave": "̀"}
CUSTOM_NAME_RE = re.compile(r"\A[a-z_][a-z0-9_]*\Z")

# The lookahead keeps "Vau/Nail or Spike/6" whose "or" is inside the meaning
HEBREW_ALT_RE = re.compile(r",?\s+or,?\s+(?:in some decks,\s+)?(?=[^/]+/[^/]+/\s*\d+\s*\Z)")

# Handle both "Mars/Aries" and "Leo or Libra"
PLANETARY_SPLIT_RE = re.compile(r"\s*/\s*|\s+or\s+")


# "Enigmas never age, have you noticed that?"
# https://en.wikipedia.org/wiki/Jeffrey_Epstein%27s_birthday_book
TRUMP_REGEX = re.compile(r"\ATrump ([0-9]+): (.+)\Z")


class BuildError(Exception):
    pass


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def read_input(source: dict) -> list[str]:
    """Return the input's lines, repaired."""
    spec = source["input"]
    path = HERE / spec["path"]
    raw = path.read_bytes()

    actual = hashlib.sha256(raw).hexdigest()
    if actual != spec["sha256"]:
        raise BuildError(
            f"{path} does not match SOURCE.toml: recorded {spec['sha256']}, found {actual}."
        )

    text = raw.decode(spec["encoding"]["declared"])
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    return [repair(line, source) for line in lines]


def repair(line: str, source: dict) -> str:
    """Undo the input's encoding defects."""
    for wrong, right in source["input"]["mojibake"].items():
        line = line.replace(wrong, right)

    accents = source["input"].get("accents", {})
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


class Claims:
    """A record of what each input line was used for, for coverage."""

    def __init__(self) -> None:
        self.by_line: dict[int, dict[str, str]] = {}

    def add(self, line: int, kind: str, claim: str) -> None:
        if line in self.by_line:
            raise BuildError(
                f"input line {line} claimed twice: "
                f"{self.by_line[line]['claim']!r} and {claim!r}"
            )
        self.by_line[line] = {"kind": kind, "claim": claim}


def parse_range(spec: str) -> list[int]:
    if "-" in spec:
        first, last = spec.split("-", 1)
        return list(range(int(first), int(last) + 1))
    return [int(spec)]


def slugify(label: str) -> str:
    """A symbol label to a custom name."""
    text = label.rstrip(".?!").lower()
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def apply_transform(value: str, transform: str) -> str:
    if transform == "verbatim":
        return value
    if transform == "lowercase":
        return value.lower()
    if transform == "lowercase_no_period":
        return value.lower().rstrip(".")
    if transform == "unquote":
        for opening, closing in (('"', '"'), ("“", "”")):
            if value.startswith(opening) and value.endswith(closing) and len(value) > 1:
                return value[1:-1]
        return value
    raise BuildError(f"mapping.toml names a transform build.py does not have: {transform!r}")


def triple(printed: str, label: str, line_no: int) -> list[str]:
    """A Hebrew row's `Letter/Meaning/Value` split and stripped."""
    parts = [part.strip() for part in printed.split("/")]
    if len(parts) != 3 or not parts[2].isdigit():
        raise BuildError(f"line {line_no}: {label} is not Letter/Meaning/Value: {printed!r}")
    return parts


def split_hebrew_alt(printed: str) -> tuple[str, str]:
    """A Hebrew row into its primary attribution and its alternate, if any."""
    parts = HEBREW_ALT_RE.split(printed, maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def blocks(texts: list[str]) -> str:
    """Join source lines into one passage.

    Each line of the book is its own paragraph, so lines are separated by a
    blank line.
    """
    out: list[str] = []
    run: list[str] = []
    for text in texts:
        if text.startswith("* "):
            run.append(text)
            continue
        if run:
            out.append("\n".join(run))
            run = []
        out.append(text)
    if run:
        out.append("\n".join(run))
    return "\n\n".join(out)


def undent(line: str) -> str:
    return line.removeprefix("  ")


def set_path(table: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        table = table.setdefault(part, {})
    if parts[-1] in table:
        raise BuildError(f"{dotted} is set twice")
    table[parts[-1]] = value


# ---------------------------------------------------------------------------
# The structure walk
# ---------------------------------------------------------------------------


class Builder:
    def __init__(self, source: dict, mapping: dict, lines: list[str]) -> None:
        self.source = source
        self.mapping = mapping
        self.lines = lines
        self.claims = Claims()
        self.cards: dict[str, dict] = {}
        self.groups: dict[str, dict] = {}
        self.tally: dict[str, int] = dict.fromkeys(EXPECTED, 0)
        self.tally["lines"] = len(lines)

        structure = mapping["structure"]
        self.card_sections = set(structure["card_sections"])
        self.dividers = set(structure["chapter_dividers"])
        self.suits = structure["suits"]
        self.ranks = structure["ranks"]
        self.minor_re = re.compile(
            r"\A(" + "|".join(self.ranks) + r") of (" + "|".join(self.suits) + r")\Z"
        )

    # -- entry points -------------------------------------------------------

    def run(self) -> dict:
        self.walk_cards()
        self.walk_front_matter()
        self.check_counts()
        return self.assemble()

    # -- cards --------------------------------------------------------------

    def headings(self) -> list[tuple[int, str]]:
        return [
            (n, text)
            for n, text in enumerate(self.lines, 1)
            if text and not text.startswith(" ") and not text.startswith("* ")
        ]

    def walk_cards(self) -> None:
        heads = self.headings()
        card_id = None
        for index, (line_no, text) in enumerate(heads):
            end = heads[index + 1][0] if index + 1 < len(heads) else len(self.lines) + 1
            body = [
                (n, self.lines[n - 1])
                for n in range(line_no + 1, end)
                if self.lines[n - 1].strip()
            ]

            new_id = self.card_id(text)
            if new_id is not None:
                if new_id in self.cards:
                    raise BuildError(f"{new_id} appears twice, at line {line_no}")
                card_id = new_id
                self.cards[card_id] = {"passages": {}, "correspondences": {}}
                self.tally["cards"] += 1
                self.tally["majors" if card_id.startswith("major") else "minors"] += 1
                self.claims.add(line_no, "structure", f'card."{card_id}"')
                continue

            if text in self.dividers:
                card_id = None
                continue

            if card_id is not None and text in self.card_sections:
                self.claims.add(line_no, "structure", f'card."{card_id}" / {text}')
                self.section(card_id, text, body)
                continue

            # Any other column-0 heading ends the card and belongs to the front
            # matter, which walk_front_matter and drops.toml account for.
            card_id = None

    def card_id(self, text: str) -> str | None:
        major = TRUMP_REGEX.match(text)
        if major:
            return f"major_arcana.{int(major.group(1)):02d}"
        minor = self.minor_re.match(text)
        if minor:
            return f"minor_arcana.{self.suits[minor.group(2)]}.{self.ranks[minor.group(1)]}"
        return None

    def section(self, card_id: str, name: str, body: list[tuple[int, str]]) -> None:
        handler = {
            "Keywords": self.keywords,
            "Range of Meaning": self.range_of_meaning,
            "Correspondences": self.correspondences,
            "Advice": self.advice,
            "Symbols and Insights": self.symbols,
            "Questions to Ask": self.questions,
            "Note": self.note,
        }[name]
        handler(card_id, body)

    def put(self, card_id: str, dotted: str, value, line_no: int) -> None:
        set_path(self.cards[card_id], dotted, value)
        self.claims.add(line_no, "content", f'card."{card_id}".{dotted}')

    # -- one section at a time ---------------------------------------------

    def keywords(self, card_id: str, body: list[tuple[int, str]]) -> None:
        if len(body) != 1:
            raise BuildError(f"{card_id}: Keywords is {len(body)} lines, expected 1")
        line_no, text = body[0]
        sep = self.mapping["sections"]["keywords_separator"]
        words = [w for w in undent(text).split(sep) if w]
        if len(words) < 3:
            raise BuildError(f"{card_id}: {len(words)} keywords at line {line_no}")
        self.put(card_id, self.mapping["sections"]["keywords_target"], words, line_no)
        self.tally["keywords"] += 1

    def range_of_meaning(self, card_id: str, body: list[tuple[int, str]]) -> None:
        table = self.mapping["range_of_meaning"]
        for line_no, text in body:
            label, _, value = undent(text).partition(": ")
            if label not in table:
                raise BuildError(f"line {line_no}: unknown Range of Meaning label {label!r}")
            self.put(card_id, table[label], value, line_no)
            self.tally[label.lower()] += 1

    def advice(self, card_id: str, body: list[tuple[int, str]]) -> None:
        table = self.mapping["advice"]
        for line_no, text in body:
            stripped = undent(text)
            for label, target in table.items():
                marker = label if label.endswith("?") else label + "."
                if stripped.startswith(marker + " "):
                    self.put(card_id, target, stripped[len(marker) + 1 :], line_no)
                    self.tally["advice"] += 1
                    break
            else:
                raise BuildError(f"line {line_no}: unknown Advice label in {stripped[:40]!r}")

    def questions(self, card_id: str, body: list[tuple[int, str]]) -> None:
        target = self.mapping["sections"]["questions_target"]
        items = []
        for line_no, text in body:
            if not text.startswith("* "):
                raise BuildError(f"line {line_no}: Questions to Ask entry is not a bullet")
            items.append(text[2:])
            self.claims.add(line_no, "content", f'card."{card_id}".{target}')
            self.tally["questions"] += 1
        set_path(self.cards[card_id], target, items)

    def note(self, card_id: str, body: list[tuple[int, str]]) -> None:
        target = self.mapping["sections"]["note_target"]
        for line_no, _ in body:
            self.claims.add(line_no, "content", f'card."{card_id}".{target}')
        set_path(self.cards[card_id], target, blocks([undent(t) for _, t in body]))
        self.tally["notes"] += 1

    def symbols(self, card_id: str, body: list[tuple[int, str]]) -> None:
        config = self.mapping["symbols"]
        prefix = config["target_prefix"]
        seen: dict[str, int] = {}
        for line_no, text in body:
            label, rest = self.split_symbol(undent(text), config)
            if not rest:
                raise BuildError(f"line {line_no}: symbol entry has a label and no body")
            key = slugify(label)
            if not CUSTOM_NAME_RE.match(key):
                raise BuildError(f"line {line_no}: {key!r} is not a custom name")
            if key in seen:
                raise BuildError(
                    f"{card_id}: symbol key {key!r} at lines {seen[key]} and {line_no} collide"
                )
            seen[key] = line_no
            self.put(card_id, f"{prefix}.{key}", rest, line_no)
            self.tally["symbols"] += 1

    @staticmethod
    def split_symbol(text: str, config: dict) -> tuple[str, str]:
        abbreviations = {a.lower() for a in config["abbreviations"]}
        best = None
        for terminator in config["terminators"]:
            start = 0
            while True:
                at = text.find(terminator, start)
                if at < 0:
                    break
                word = re.search(r"([A-Za-z]+)\Z", text[:at])
                if word and word.group(1).lower() in abbreviations:
                    start = at + 1
                    continue
                if best is None or at < best[0]:
                    best = (at, len(terminator))
                break
        if best is None:
            raise BuildError(f"symbol entry has no label terminator: {text[:60]!r}")
        at, width = best
        return text[: at + 1], text[at + width :]

    # -- correspondences ----------------------------------------------------

    def correspondences(self, card_id: str, body: list[tuple[int, str]]) -> None:
        labels = self.mapping["correspondences"]["labels"]
        for line_no, text in body:
            label, sep, value = undent(text).partition(": ")
            if not sep or label not in labels:
                raise BuildError(f"line {line_no}: unknown Correspondences label {label!r}")
            rule = labels[label]
            if "handler" in rule:
                getattr(self, f"corr_{rule['handler']}")(card_id, label, value, line_no)
            else:
                self.put(
                    card_id,
                    rule["target"],
                    apply_transform(value, rule.get("transform", "verbatim")),
                    line_no,
                )
                self.tally[self.tally_key(label)] += 1

    @staticmethod
    def tally_key(label: str) -> str:
        return {
            "Archetype": "archetype",
            "Astrology": "astrology",
            "Affirmation": "affirmation",
            "Personality": "personality",
            "Story": "story",
            "Mythical/Spiritual": "mythical_spiritual",
            "Elemental": "elemental",
        }[label]

    def corr_number(self, card_id: str, label: str, value: str, line_no: int) -> None:
        config = self.mapping["correspondences"]["number"]
        leading = re.match(r"\A([0-9]+)\b", value)
        if not leading:
            raise BuildError(f"line {line_no}: {label} has no leading integer: {value!r}")
        set_path(self.cards[card_id], config["target"], int(leading.group(1)))
        set_path(self.cards[card_id], config["gloss_target"], value)
        self.claims.add(
            line_no,
            "content",
            f'card."{card_id}".{config["target"]} + {config["gloss_target"]}',
        )
        self.tally["numbers" if label == "Numbers" else "numerology"] += 1

    def corr_hebrew(self, card_id: str, label: str, value: str, line_no: int) -> None:
        config = self.mapping["correspondences"]["hebrew"]
        card = self.cards[card_id]

        primary, alt = split_hebrew_alt(value.lower())
        letter, meaning, printed = (part.strip() for part in triple(primary, label, line_no))

        set_path(card, config["letter_target"], letter)
        set_path(card, config["meaning_target"], meaning)
        set_path(card, config["value_target"], int(printed))
        claimed = "hebrew_letter*"
        if alt:
            set_path(card, config["alt_target"], "/".join(triple(alt, label, line_no)))
            claimed += " + x_hebrew_letter_alt"

        self.claims.add(line_no, "content", f'card."{card_id}".correspondences.{claimed}')
        self.tally["hebrew"] += 1

    def corr_planetary(self, card_id: str, label: str, value: str, line_no: int) -> None:
        config = self.mapping["correspondences"]["planetary"]
        vocabulary = config["terms"]

        terms = [term.strip().lower() for term in PLANETARY_SPLIT_RE.split(value)]
        kinds = []
        for term in terms:
            if term not in vocabulary:
                raise BuildError(
                    f"line {line_no}: {label} names {term!r}, which mapping.toml's "
                    f"planetary vocabulary does not classify"
                )
            kinds.append(vocabulary[term])

        if len(set(kinds)) == 1:
            # An alternation, or a compound of one kind.
            routed = [(kinds[0], value.lower())]
        elif len(set(kinds)) != len(kinds):
            raise BuildError(
                f"line {line_no}: {label} compounds two terms of one kind, so "
                f"neither can hold the key: {value!r}"
            )
        else:
            routed = list(zip(kinds, terms, strict=True))

        for kind, routed_value in routed:
            set_path(self.cards[card_id], config["kind_targets"][kind], routed_value)
        self.claims.add(
            line_no,
            "content",
            f'card."{card_id}".correspondences.' + "+".join(kind for kind, _ in routed),
        )
        self.tally["planetary"] += 1

    # -- front matter -------------------------------------------------------

    def group(self, target: str) -> dict:
        return self.groups.setdefault(target, {"passages": {}, "correspondences": {}})

    def walk_front_matter(self) -> None:
        for entry in self.mapping.get("front_matter", []):
            numbers = parse_range(entry["lines"])
            texts = []
            slot, _, key = entry["key"].partition(".")
            for n in numbers:
                text = self.lines[n - 1]
                if not text.strip():
                    continue  # a blank line inside a range is drops.toml's
                text = undent(text)
                prefix = entry.get("strip_prefix")
                if prefix:
                    if not text.startswith(prefix):
                        raise BuildError(f"line {n} does not start with {prefix!r}")
                    text = text[len(prefix) :]
                texts.append(text)
                self.claims.add(n, "content", f"{entry['target']}.{entry['key']}")
            if not texts:
                raise BuildError(f"front matter entry {entry['lines']} claimed nothing")
            set_path(self.group(entry["target"])[slot], key, blocks(texts))

        for entry in self.mapping.get("group_correspondences", []):
            for n in parse_range(entry["lines"]):
                self.claims.add(n, "content", f"{entry['target']}.correspondences")
            for key, value in entry["values"].items():
                set_path(self.group(entry["target"])["correspondences"], key, value)

    # -- assertions ---------------------------------------------------------

    def check_counts(self) -> None:
        wrong = {k: (v, self.tally[k]) for k, v in EXPECTED.items() if self.tally[k] != v}
        if wrong:
            report = "\n".join(
                f"    {k}: expected {want}, built {got}" for k, (want, got) in wrong.items()
            )
            raise BuildError("the build did not reproduce the input's counts:\n" + report)

    # -- output -------------------------------------------------------------

    def assemble(self) -> dict:
        out: dict = {"meta": self.meta()}

        order = self.mapping["output"]
        cards: dict = {}
        for card_id in sorted(self.cards, key=self.card_sort_key):
            cards[card_id] = self.ordered_target(self.cards[card_id], order)
        out["card"] = cards

        groups: dict = {}
        for target in order["group_order"]:
            if target not in self.groups:
                continue
            body = self.ordered_target(self.groups[target], order)
            table = groups
            for part in target.split(".")[1:]:
                table = table.setdefault(part, {})
            table.update(body)
        unplaced = set(self.groups) - set(order["group_order"])
        if unplaced:
            raise BuildError(f"mapping.toml's group_order omits {sorted(unplaced)}")
        out["group"] = groups
        return out

    @staticmethod
    def card_sort_key(card_id: str) -> tuple:
        parts = card_id.split(".")
        if parts[0] == "major_arcana":
            return (0, int(parts[1]), 0)
        suits = ["wands", "cups", "swords", "pentacles"]
        ranks = [
            "ace",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "page",
            "knight",
            "queen",
            "king",
        ]
        return (1, suits.index(parts[1]), ranks.index(parts[2]))

    def ordered_target(self, target: dict, order: dict) -> dict:
        out: dict = {}
        passages = target.get("passages") or {}
        if passages:
            out["passages"] = self.ordered(passages, order["passage_order"], "passage")
            advice = out["passages"].get("advice")
            if advice:
                out["passages"]["advice"] = self.ordered(
                    advice, order["advice_order"], "advice"
                )
            symbols = out["passages"].get("symbols")
            if symbols:
                # Symbol keys are the author's, so they keep the book's order.
                out["passages"]["symbols"] = symbols
        correspondences = target.get("correspondences") or {}
        if correspondences:
            out["correspondences"] = self.ordered(
                correspondences, order["correspondence_order"], "correspondence"
            )
        return out

    @staticmethod
    def ordered(table: dict, order: list[str], what: str) -> dict:
        unknown = set(table) - set(order)
        if unknown:
            raise BuildError(
                f"mapping.toml's {what} order omits {sorted(unknown)}, so the built "
                f"file's key order would not be fixed"
            )
        return {key: table[key] for key in order if key in table}

    def meta(self) -> dict:
        work = self.source["work"]
        licence = self.source["license"]
        fixed = self.mapping["meta"]
        return {
            "schema_version": fixed["schema_version"],
            "identifier": self.source["identifier"],
            "name": work["title"],
            "type": fixed["type"],
            "author": work["author"],
            "published_date": fixed["published_date"],
            "license": licence["spdx"],
            "version": fixed["version"],
            "citation": fixed["citation"],
            "default_language": fixed["default_language"],
            "attribution": licence["attribution_requested"],
            "redistribution": fixed["redistribution"],
            "derivation": fixed["derivation"],
        }


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def git_commit() -> str:
    """The commit the builder ran at, or "uncommitted" in a dirty tree."""
    try:
        head = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return "uncommitted"
    return "uncommitted" if dirty else head


def provenance(builder: Builder, output_name: str, output_text: str) -> dict:
    spec = builder.source["input"]
    return {
        "schema": 1,
        "note": "Provenance for the built file beside this one.",
        "build": {
            "builder": "sources/mcelroy/build.py",
            "commit": git_commit(),
            "identifier": builder.source["identifier"],
        },
        "input": {
            "path": spec["path"],
            "sha256": spec["sha256"],
            "lines": len(builder.lines),
        },
        "output": {
            "path": f"dist/{output_name}",
            "sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
        },
        "counts": {key: builder.tally[key] for key in EXPECTED},
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build() -> tuple[Builder, str, str]:
    source = load_toml(HERE / "SOURCE.toml")
    mapping = load_toml(HERE / "mapping.toml")
    builder = Builder(source, mapping, read_input(source))
    document = builder.run()

    # REUSE-IgnoreStart
    header = f"# SPDX-License-Identifier: {source['license']['spdx']}\n\n"
    # REUSE-IgnoreEnd
    return builder, mapping["output"]["filename"], header + emit.dumps(document)


def main(argv: list[str]) -> int:
    unknown = set(argv) - {"--check", "--mapped-lines"}
    if unknown:
        print(f"build.py: unknown argument {min(unknown)}", file=sys.stderr)
        return 2

    try:
        builder, name, text = build()
    except BuildError as exc:
        print(f"FAIL build.py: {exc}", file=sys.stderr)
        return 1

    if "--mapped-lines" in argv:
        json.dump(
            {"source": "mcelroy", "lines": builder.claims.by_line},
            sys.stdout,
            indent=1,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 0

    dist = HERE / "dist"
    built = dist / name
    sidecar = dist / "PROVENANCE.toml"
    record = provenance(builder, name, text)

    if "--check" in argv:
        failed = False
        if not built.is_file():
            print(f"FAIL build.py --check: {built} is not committed", file=sys.stderr)
            failed = True
        elif built.read_text(encoding="utf-8") != text:
            print(
                f"FAIL build.py --check: {built} differs from a fresh build",
                file=sys.stderr,
            )
            failed = True
        if sidecar.is_file():
            committed = load_toml(sidecar)
            if committed.get("output", {}).get("sha256") != record["output"]["sha256"]:
                print(
                    "FAIL build.py --check: PROVENANCE.toml records a different output sha256",
                    file=sys.stderr,
                )
                failed = True
        else:
            print(f"FAIL build.py --check: {sidecar} is not committed", file=sys.stderr)
            failed = True
        if failed:
            return 1
        print(f"ok   build.py --check: {built.relative_to(REPO_ROOT)} is current")
        return 0

    dist.mkdir(exist_ok=True)
    built.write_text(text, encoding="utf-8")
    sidecar.write_text(emit.dumps(record), encoding="utf-8")
    print(
        f"ok   build.py: {built.relative_to(REPO_ROOT)}  "
        f"{builder.tally['cards']} cards, {builder.tally['symbols']} symbols, "
        f"{len(text)} bytes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
