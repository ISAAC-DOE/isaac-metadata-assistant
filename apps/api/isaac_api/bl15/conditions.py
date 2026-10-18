"""What the LOGBOOK says about the experiment's environment, reaction and cell.

THE ANSWER THIS MODULE IMPLEMENTS
=================================

The domain owner (Angel), relayed by the project owner on 2026-10-12, in two parts the
same day:

* *"those markers or descriptors or values need to be extracted by the skill within the
  metadata available. If not available, then the claude skill needs to leave it blank for
  a human to select the appropriate value."*
* *"the skill should be able to know if it is a three electrode or two electrode or
  electrolyzer or battery or whatever it is from the logbook that it will ingest. Then, if
  the information is not there, it can leave it blank for the user to select. Same for
  'operando' and for the type of reaction under study 'OER' or 'HER' or 'ORR' etc."*

So a logbook sentence that NAMES one of these is read, and a logbook that names none
leaves the field blank for a person. Nothing is inferred and nothing is defaulted.

WHAT IS READ, AND THE THREE WAYS A TERM PROPOSES NOTHING
========================================================

Each lexicon maps a term to ONE member of the vendored official schema's own enum for
that field. **The member list is read from the schema at runtime**
(:func:`bl15.mapping.schema_enum`) and never transcribed: every member's own spelling,
with ``_`` read as a space or a hyphen, is a term for it; a short, versioned table adds
the few spellings a member's name does not give (``3-electrode``, a reaction's full
name). A table entry whose member the schema no longer declares proposes nothing.

A term proposes nothing, and is kept verbatim, when:

* it is **not one of the schema's options** — ``two-electrode``, ``battery``, a generic
  ``electrolyzer``. The schema's ``cell_type`` has no member for any of them, which is a
  vocabulary gap for the domain owner and upstream, not something this build decides;
* it **fits more than one option** — ``water oxidation`` is OER or water_splitting;
  ``nitrogen reduction`` is NRR or N2RR;
* its sentence **negates or contrasts** it (``not``, ``no``, ``none``, ``nothing``,
  ``neither``/``nor``, ``without``, ``instead of``, ``replaced`` …). A negation is a
  reading this build does not interpret;
* its sentence is **hedged or planned rather than stated** — a ``?``, ``possibly``,
  ``maybe``, ``perhaps``, ``might``, ``could``, ``planned``, ``to be``, ``TBD``,
  ``check`` … (2026-10-12, after an independent review: *"Operando? check…"* and
  *"possibly OER"* had been proposed as facts). **When in doubt, nothing is proposed.**

**WHAT IS NEVER A STATEMENT AT ALL**, and so is not even kept as one:

* an abbreviation inside an ALL-CAPITALS clause of two or more words — *"NOTE: GIVE HER
  THE CELL KEYS"* is not the hydrogen evolution reaction (the reason ``FOR`` is never
  read, applied to every abbreviation);
* a term touching ``/``, ``\\`` or a file extension — ``/data/OER/2099`` and ``OER.dat``
  are a path and a file name, not a sentence about the reaction.

Matching is on word boundaries, case-insensitive for words and CASE-SENSITIVE for a
reaction's abbreviation, so ``her`` the pronoun is never ``HER`` the reaction. ``FOR``
is not read as an abbreviation at all: it is an ordinary English word in capitals, and
this lexicon knows no full name for it it could rely on instead. The schema's reaction
member ``None`` is a value a person may choose and is never read from prose.

Pure functions over text. No I/O beyond the cached schema read.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from . import evidence as ev
from . import mapping as mp

__all__ = [
    "FIELDS",
    "LexiconHit",
    "LineScope",
    "STATUS_HEDGED",
    "STATUS_NOT_UNDER_STUDY",
    "STATUS_SUBSET",
    "scope_of_line",
    "STATUS_AMBIGUOUS",
    "STATUS_MEMBER",
    "STATUS_NEGATED",
    "STATUS_NOT_AN_OPTION",
    "read_line",
]

#: concept -> (official path, rule id, the field's name in a sentence a scientist reads).
FIELDS: Mapping[str, tuple[str, str, str]] = {
    ev.CONCEPT_ENVIRONMENT_STATEMENT: (
        "context.environment",
        mp.RULE_LOGBOOK_ENVIRONMENT,
        "environment",
    ),
    ev.CONCEPT_REACTION_STATEMENT: (
        "context.electrochemistry.reaction",
        mp.RULE_LOGBOOK_REACTION,
        "reaction",
    ),
    ev.CONCEPT_CELL_TYPE_STATEMENT: (
        "context.electrochemistry.cell_type",
        mp.RULE_LOGBOOK_CELL_TYPE,
        "cell type",
    ),
}

STATUS_MEMBER = "member"
STATUS_NOT_AN_OPTION = "not_an_option"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NEGATED = "negated"
STATUS_HEDGED = "hedged"
#: A reaction named as one that was suppressed, inhibited, avoided, minimised, or as a
#: side or competing reaction (re-review, 2026-10-12): it is not the reaction UNDER STUDY.
STATUS_NOT_UNDER_STUDY = "not_under_study"
#: Inside a sample section, a sentence that singles out PART of it ("only", "except", a
#: sample code) — which part, this build does not decide.
STATUS_SUBSET = "subset"

#: SPELLINGS A MEMBER'S OWN NAME DOES NOT GIVE, per field. ``term -> member``. Versioned
#: with the rule ids above: changing this table is a new version of the lexicon.
_SYNONYMS: Mapping[str, Mapping[str, str]] = {
    ev.CONCEPT_CELL_TYPE_STATEMENT: {
        "3-electrode": "three_electrode",
        "3 electrode": "three_electrode",
    },
    ev.CONCEPT_REACTION_STATEMENT: {
        "oxygen evolution reaction": "OER",
        "oxygen evolution": "OER",
        "hydrogen evolution reaction": "HER",
        "hydrogen evolution": "HER",
        "oxygen reduction reaction": "ORR",
        "oxygen reduction": "ORR",
        "CO2 reduction reaction": "CO2RR",
        "CO2 reduction": "CO2RR",
        "carbon dioxide reduction": "CO2RR",
        "CO reduction": "CORR",
        "carbon monoxide reduction": "CORR",
        "nitrate reduction": "NO3RR",
    },
}

#: TERMS THAT FIT MORE THAN ONE MEMBER. ``term -> the members it could be``.
_AMBIGUOUS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    ev.CONCEPT_REACTION_STATEMENT: {
        "water oxidation": ("OER", "water_splitting"),
        "nitrogen reduction": ("NRR", "N2RR"),
    },
}

#: TERMS THAT NAME A THING THE SCHEMA HAS NO MEMBER FOR. Kept verbatim; propose nothing.
_NOT_AN_OPTION: Mapping[str, tuple[str, ...]] = {
    ev.CONCEPT_CELL_TYPE_STATEMENT: (
        "two-electrode",
        "two electrode",
        "2-electrode",
        "2 electrode",
        "battery",
        "batteries",
        "electrolyzer",
        "electrolyser",
    ),
}

#: Members never read from prose. ``None`` is the schema's own "no reaction" choice —
#: a person may pick it; a sentence containing the word "none" says nothing about it.
_NEVER_FROM_PROSE = frozenset({"None"})
#: Abbreviations never read, because they are ordinary words in capitals.
_NOT_READ_AS_ABBREVIATIONS = frozenset({"FOR"})

_NEGATION = re.compile(
    r"\b(?:not|no|none|nothing|neither|nor|nobody|never|without|non|no\s+one|"
    r"instead\s+of|rather\s+than|replaced|previously|formerly|switched)\b|n't\b"
    # "w/o" is "without" (re-review, 2026-10-12: "operando w/o potential" was read).
    r"|(?<![\w/])w/o(?![\w/])",
    re.IGNORECASE,
)
#: Words that make a named reaction something OTHER than the one studied.
_NOT_UNDER_STUDY = re.compile(
    r"\b(?:suppress\w*|inhibit\w*|avoid\w*|minimi[sz]\w*|side[\s-]+reactions?|"
    r"competing|competitive|parasitic|unwanted)\b",
    re.IGNORECASE,
)
#: HEDGES: a sentence that plans, wonders or reports a guess states nothing to propose.
_HEDGE = re.compile(
    r"\?|\b(?:possibly|maybe|perhaps|might|could|probably|likely|presumably|"
    r"planned|plan|plans|planning|intended|intend|to\s+be|tbd|tbc|check|unclear|unsure|"
    r"uncertain|unknown|if|whether|expected|tentative|tentatively|should|would|hope|"
    r"hoped|assume|assumed)\b",
    re.IGNORECASE,
)
_ABBREVIATION = re.compile(r"^[A-Z][A-Z0-9]*$")
#: Where a clause ends, for the all-capitals check.
_CLAUSE_BREAK = re.compile(r"[.;:!?()\[\]{},]")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")

#: SCOPE WORDS (2026-10-12, review I3). A sentence that names particular samples, or a
#: subset, is not about every measurement.
_SAMPLE_NUMBERS = re.compile(
    r"\bsamples?\s+(\d+(?:\s*(?:,|&|-|–|—|\band\b|\bor\b|\bto\b)\s*\d+)*)",
    re.IGNORECASE,
)
_RANGE = re.compile(r"(\d+)\s*(?:-|–|—|\bto\b)\s*(\d+)", re.IGNORECASE)
_SUBSET = re.compile(
    r"\b(?:only|some|several|certain|a\s+few|one\s+of|except|excluding|but\s+not|"
    r"all\s+but|apart\s+from|other\s+than)\b",
    re.IGNORECASE,
)
_EXCLUSION = re.compile(
    r"\b(?:except|excluding|but\s+not|all\s+but|apart\s+from|other\s+than)\b",
    re.IGNORECASE,
)
#: A sample CODE (a group name such as `ZZ3`) — the convention's shape, read as a subset.
_SAMPLE_CODE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,}[0-9]+[A-Z]?(?![A-Za-z0-9])")
#: At most this many sample numbers one sentence may name (a range is expanded).
MAX_NAMED_SAMPLES = 50


@dataclass(frozen=True)
class LexiconHit:
    """One term one line states, and what it maps to."""

    concept: str
    path: str
    #: The text that matched, exactly as written in the line.
    term: str
    status: str
    #: The schema member, only when :attr:`status` is :data:`STATUS_MEMBER`.
    member: str | None = None
    #: The members an ambiguous term could be.
    options: tuple[str, ...] = ()

    def to_state(self) -> dict:
        return {
            "term": self.term,
            "status": self.status,
            "member": self.member,
            "options": list(self.options),
        }


def _phrase_pattern(phrase: str) -> str:
    """A term as a regex: words separated by a space OR a hyphen, word-bounded — and
    never touching a path separator or a file extension (review I2): ``/data/OER/2099``
    and ``OER.dat`` are not statements about the reaction."""
    words = re.split(r"[\s_-]+", phrase.strip())
    return (
        r"(?<![\w/\\.-])"
        + r"[\s-]+".join(re.escape(w) for w in words)
        + r"(?![\w/\\-])(?!\.\w)"
    )


def _in_all_caps_clause(line: str, start: int, end: int) -> bool:
    """Whether ``line[start:end]`` sits in a clause of 2+ words with no lowercase letter."""
    left = max((m.end() for m in _CLAUSE_BREAK.finditer(line, 0, start)), default=0)
    following = _CLAUSE_BREAK.search(line, end)
    right = following.start() if following else len(line)
    clause = line[left:right]
    words = _WORD.findall(clause)
    return len(words) >= 2 and not any(c.islower() for c in clause)


@dataclass(frozen=True)
class LineScope:
    """Which measurements a logbook sentence is about, as far as its WORDS say."""

    #: Sample numbers it names (``samples 3 and 4``, ``samples 7–8``), sorted.
    named_samples: tuple[int, ...] = ()
    #: It uses a subset word (``only``, ``some``, ``except`` …).
    subset_words: bool = False
    #: It names a sample CODE (a group name such as ``ZZ3``).
    names_code: bool = False
    #: It EXCLUDES some (``except``, ``all but`` …) — never mapped onto measurements.
    excluding: bool = False

    @property
    def subset(self) -> bool:
        """About fewer than all of the measurements, by its own words."""
        return bool(self.named_samples) or self.subset_words or self.names_code


def scope_of_line(line: str) -> LineScope:
    """The scope words of one sentence. Deterministic; never raises."""
    numbers: set[int] = set()
    for match in _SAMPLE_NUMBERS.finditer(line):
        listed = match.group(1)
        for low, high in _RANGE.findall(listed):
            a, b = int(low), int(high)
            if a <= b and b - a < MAX_NAMED_SAMPLES:
                numbers.update(range(a, b + 1))
        numbers.update(int(n) for n in re.findall(r"\d+", listed))
    return LineScope(
        named_samples=tuple(sorted(numbers))[:MAX_NAMED_SAMPLES],
        subset_words=bool(_SUBSET.search(line)),
        names_code=bool(_SAMPLE_CODE.search(line)),
        excluding=bool(_EXCLUSION.search(line)),
    )


@lru_cache(maxsize=None)
def _patterns(concept: str) -> tuple[tuple[re.Pattern, str, str | None, tuple[str, ...]], ...]:
    """``(pattern, status, member, options)`` for one field, LONGEST TERM FIRST.

    Built from the schema's enum at first use and cached for the process — a schema
    refresh is a restart, exactly as for every other schema read in this application.
    """
    path = FIELDS[concept][0]
    members = mp.schema_enum(path)
    entries: list[tuple[str, str, str | None, tuple[str, ...], bool]] = []
    for member in members:
        if member in _NEVER_FROM_PROSE:
            continue
        if _ABBREVIATION.match(member):
            if member in _NOT_READ_AS_ABBREVIATIONS:
                continue
            entries.append((member, STATUS_MEMBER, member, (), True))
        else:
            entries.append((member.replace("_", " "), STATUS_MEMBER, member, (), False))
    for term, member in (_SYNONYMS.get(concept) or {}).items():
        if member in members:
            entries.append((term, STATUS_MEMBER, member, (), False))
    for term, options in (_AMBIGUOUS.get(concept) or {}).items():
        present = tuple(o for o in options if o in members)
        if len(present) > 1:
            entries.append((term, STATUS_AMBIGUOUS, None, present, False))
        elif len(present) == 1:
            entries.append((term, STATUS_MEMBER, present[0], (), False))
    for term in _NOT_AN_OPTION.get(concept) or ():
        entries.append((term, STATUS_NOT_AN_OPTION, None, (), False))
    entries.sort(key=lambda e: -len(e[0]))
    out = []
    for term, status, member, options, case_sensitive in entries:
        pattern = re.compile(
            _phrase_pattern(term), 0 if case_sensitive else re.IGNORECASE
        )
        out.append((pattern, status, member, options))
    return tuple(out)


def read_line(line: str) -> list[LexiconHit]:
    """Every term ``line`` states for any of the three fields, in order. Never raises.

    A span claimed by a longer term is not read again by a shorter one inside it, so
    ``microfluidic flow cell`` is one statement, not two.
    """
    hits: list[tuple[int, LexiconHit]] = []
    # LINE-LEVEL, ON PURPOSE: a negation or a hedge anywhere in the sentence makes every
    # term in it a reading this build does not interpret. Clause-level parsing would be
    # this module deciding what a sentence means.
    override = (
        STATUS_NEGATED
        if _NEGATION.search(line)
        else STATUS_HEDGED
        if _HEDGE.search(line)
        else None
    )
    not_studied = _NOT_UNDER_STUDY.search(line) is not None
    for concept, (path, _rule, _name) in FIELDS.items():
        taken: list[tuple[int, int]] = []
        for pattern, status, member, options in _patterns(concept):
            abbreviation = not (pattern.flags & re.IGNORECASE)
            for match in pattern.finditer(line):
                start, end = match.span()
                if any(start < e and s < end for s, e in taken):
                    continue
                if abbreviation and _in_all_caps_clause(line, start, end):
                    continue  # "GIVE HER THE CELL KEYS" is not the reaction
                taken.append((start, end))
                final = override or (
                    STATUS_NOT_UNDER_STUDY
                    if not_studied and concept == ev.CONCEPT_REACTION_STATEMENT
                    else status
                )
                hits.append(
                    (
                        start,
                        LexiconHit(
                            concept=concept,
                            path=path,
                            term=match.group(0),
                            status=final,
                            member=member if final == STATUS_MEMBER else None,
                            options=options,
                        ),
                    )
                )
    return [hit for _start, hit in sorted(hits, key=lambda pair: pair[0])]


def field_name(concept: str) -> str:
    return FIELDS[concept][2]


def rule_for(concept: str) -> str:
    return FIELDS[concept][1]


def members_of(hits: Sequence[LexiconHit]) -> set[str]:
    return {h.member for h in hits if h.status == STATUS_MEMBER and h.member}
