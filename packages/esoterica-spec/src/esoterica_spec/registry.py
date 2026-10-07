"""ESOTERICA.md's registries, as data: 4.1, 4.1.1, 4.1.4, 4.4, 5.2, 6.2, 8.3, Appendix B."""

from __future__ import annotations

from esoterica_spec.grammar import CANONICAL_RANKS, CANONICAL_SUITS

TOP_LEVEL_TABLES = ("meta", "card", "group", "app")

# 4.1. The value is the spec's own type name, which the diagnostic quotes back.
META_FIELDS = {
    "schema_version": "String",
    "identifier": "String",
    "name": "String",
    "license": "String",
    "type": "String",
    "version": "String",
    "author": "String",
    "relation": "String",
    "citation": "String",
    "description": "String",
    "default_language": "String",
    "translates": "String",
    "copyright": "String",
    "attribution": "String",
    "redistribution": "String",
    "derivation": "String",
    "tags": "Array of String",
}
REQUIRED_META_FIELDS = ("schema_version", "identifier", "name", "license")

# 4.1.4. [meta.work] describes the work, and [meta].relation how the document
# stands to it.
WORK_FIELDS = {
    "name": "String",
    "author": "String",
    "type": "String",
    "publisher": "String",
    "published_date": "String",
    "isbn": "String",
    "url": "String",
    "rights_status": "String",
}
RELATIONS = frozenset({"transcribes", "abridges", "annotates"})
# 4.1.4 and Appendix B: facts about the work, which [meta] carried before 1.0.
WORK_KEYS_UNDER_META = ("publisher", "published_date", "isbn", "url", "rights_status")
# 4.1.4: the relations under which the document is not the work, so must not
# borrow its name.
RENAMING_RELATIONS = ("annotates", "abridges")

# 4.1.1
SOURCE_TYPES = frozenset(
    {"book", "chapter", "article", "webpage", "manuscript", "document", "tradition"}
)

# 8.3
SHARING = ("full", "none", "unstated")

# 3.3, 4.4
BUILTIN_FAMILIES = ("all", "arcana", "classes", "suits", "ranks", "custom")
FAMILY_MEMBERS = {
    "arcana": ("major", "minor"),
    "classes": ("pip", "court"),
    "suits": CANONICAL_SUITS,
    "ranks": CANONICAL_RANKS,
}
# arcana and classes are closed; a suit or a rank may be the source's own.
CLOSED_FAMILIES = ("arcana", "classes")

# 4.3
SLOTS = ("passages", "correspondences", "cards", "symbols")

# 5.4
SYMBOL_FIELDS = ("text", "label")
REQUIRED_SYMBOL_FIELDS = ("text",)

# 5.2
PASSAGE_KEYS = frozenset(
    {
        "text",
        "keywords",
        "theme",
        "light",
        "shadow",
        "questions",
        "affirmation",
        "story",
        "personality",
        "approach",
        "advice.relationships",
        "advice.work",
        "advice.spirituality",
        "advice.personal_growth",
        "advice.fortune_telling",
        "advice.timing",
    }
)
# 5.3. A property of the registry entry, not of any passage. No rule reads this;
# it is here so an application filtering by category has one place to read it.
DIVINATORY_KEYS = frozenset({"advice.fortune_telling", "advice.timing"})

# 6.2
CORRESPONDENCE_KEYS = frozenset(
    {
        "element",
        "number",
        "astrology",
        "planet",
        "zodiac",
        "decan",
        "season",
        "direction",
        "color",
        "archetype",
        "hebrew_letter",
        "hebrew_letter_meaning",
        "hebrew_letter_value",
    }
)

# Appendix B: version 0.1 spellings this version does not define.
LEGACY_META_KEYS = ("id",)
LEGACY_TOP_LEVEL_TABLES = ("passages",)
# The first part of a passage entry key that is the draft spelling of a symbol.
LEGACY_PASSAGE_PREFIXES = ("symbols",)


def is_registered(slot: str, entry_key: str) -> bool:
    """Whether 5.2 or 6.2 claims an entry key, or the author has claimed it.

    The `x_` test reads "any part prefixed x_", so `x_symbols.jester` and
    `x_upright.work` both pass. 11.4 does not say which part must carry the
    prefix for a dotted key; this is the reading STATUS finding 10 records as
    ambiguous, and it is deliberately the permissive one, since the rule is a
    warning about a name a later version might claim.
    """
    parts = entry_key.split(".")
    if any(part.startswith("x_") for part in parts):
        return True
    if slot == "passages":
        return entry_key in PASSAGE_KEYS
    return entry_key in CORRESPONDENCE_KEYS
