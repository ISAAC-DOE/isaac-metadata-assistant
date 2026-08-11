"""String-gate EXACTNESS: refuse values the official schema's anchored patterns
accept only because of a regex-flavour accident.

THE DEFECT, STATED PRECISELY
============================
The vendored official schema declares five ``pattern`` gates. Every one of them
is written ``^...$``, which in every ordinary reading means "the whole string
must look like this". Under Python's ``re`` — which is what ``jsonschema`` uses —
``$`` ALSO matches immediately before a single trailing ``\\n``. So all five gates
accept one value they visibly intend to refuse:

    record_id        "A"*26 + "\\n"              accepted
    links[].target   "B"*26 + "\\n"              accepted
    descriptors name "alpha_beta" + "\\n"        accepted
    orcid            "0000-0002-1825-0097\\n"    accepted
    tags[]           "campaign\\n"               accepted

The last is the sharpest: ``^\\S(.*\\S)?$`` exists for the SOLE purpose of
forbidding leading and trailing whitespace, and it refuses a trailing space and a
trailing tab while admitting a trailing newline.

BE EXACT ABOUT THE CAUSE, because an earlier description of it was wrong. It is
NOT that JSON Schema ``pattern`` uses search rather than match semantics. ``^``
without ``re.M`` still pins offset 0, which is exactly why LEADING and EMBEDDED
newlines ARE correctly refused (measured — see
``tests/test_schema_string_gate_exactness.py``). The cause is narrower: Python's
``$`` matches before one trailing newline. Nothing else leaks. ``\\r``, ``\\x0b``,
``\\x0c``, ``\\x1c``, ``\\x85``, a space and a tab are all refused in every
position by all five gates.

WHY THIS IS NOT IN ``official.py``
==================================
``validate_official`` answers one question — "does this conform to the vendored
official schema?" — and its report says so in words: "PASS — valid against
official ISAAC schema v1.05". A value with a trailing newline DOES conform to
that schema as written. Folding this rule into that function would make ISAAC
report a local policy decision as an upstream schema error, which is a
misattribution, and ``CLAUDE.md`` §1 makes the official schema the authority on
record structure.

It would also silently move the corpus-mutation harness's oracle.
``corpus_mutation`` cross-checks ``validate_official`` against
``diagnostics.diagnose`` and reports any disagreement as ``engine_disagreement``;
arming a rule in one engine and not the other manufactures disagreements over a
production-derived corpus this environment cannot test against. The recorded
"0 oracle failures" from the 2026-08-08 private-30 run would have been
invalidated blind.

So this is a SEPARATE, SEPARATELY-NAMED gate, applied at the points where ISAAC
decides something: export, ``isaac validate --official``, and
``POST /api/validate/record``. ``validate_official``, ``diagnose``, the audit and
the verification/mutation planes are untouched.

REFUSE, DO NOT STRIP
====================
This gate never repairs a value. Stripping a trailing control character would
mutate scientific metadata the user supplied and hand back a record they did not
write — the quiet fixing ``CLAUDE.md`` §5 forbids. The same posture the sha256
gate and the record-id gate already take: say what is wrong, name the field, and
stop.

WHAT THE RULE IS
================
For a pattern that DECLARES ITSELF whole-string — begins ``^`` and ends with an
unescaped ``$`` — the value must satisfy ``re.fullmatch``. An unanchored pattern
is left alone: JSON Schema legitimately permits substring patterns, and demanding
``fullmatch`` of one would be over-refusal. The rule is derived from the schema
document at run time rather than from a hand-copied list of five paths, so an
upstream schema refresh that adds, moves or removes a pattern is covered without
anyone remembering to update this file — with ONE stated exception, immediately
below.

THE LIMIT OF THAT COVERAGE CLAIM, STATED RATHER THAN IMPLIED
============================================================
"Covered without anyone remembering to update this file" was written as an
unqualified promise and it is not one. Two separate things break it, and only ONE
of them is fixed here.

FIXED — findings wrapped by a composition keyword. ``anyOf``/``oneOf`` do not
re-raise their branch errors: the error they yield carries their OWN keyword name
(``err.validator == "anyOf"``) and hangs the branch errors off ``err.context``.
``check_exactness`` used to keep only ``err.validator == "pattern"`` at the top
level, so a pattern that MOVED under one of those keywords in a schema refresh
would have had its finding SILENTLY DISCARDED — no error, no warning, a clean
PASS from a gate that had stopped looking. Measured before the fix: bare,
``items``, ``allOf`` and ``if``/``then`` placements all arrive as
``validator == "pattern"`` and were kept; ``anyOf`` and ``oneOf`` were dropped.
``_pattern_findings`` below now walks ``context`` recursively. (``absolute_path``
on a context error already resolves through its parent, so the reported path is
right at any depth — measured with jsonschema 4.26.0, not assumed.)

NOT FIXED, AND NOT FIXABLE THIS WAY — a pattern in one branch of an ``anyOf``
where ANOTHER branch validates the value. ``anyOf`` succeeds as soon as one branch
succeeds, so jsonschema emits NO error at all and there is nothing to walk; the
same holds for ``oneOf`` when exactly one, different, branch matches. A finding in
that position is invisible to this mechanism however the errors are collected,
because the traversal never reports a failure to collect from. Closing it would
mean walking the schema by hand to locate patterns — the second traversal engine
the ``_ExactnessValidator`` comment below explains why we do not build. It is
pinned as characterization in ``tests/test_schema_string_gate_exactness.py`` so
the gap is a recorded fact rather than a surprise.

Neither case is live: the vendored schema's five patterns all sit under plain
``properties``/``items``, with no ``anyOf`` or ``oneOf`` anywhere on the path to
one. The first is nevertheless fixed and the second is nevertheless written down,
because a silent drop inside a gate whose entire subject is "a rule that looks
like it holds and does not" is the same defect one level up.

KNOWN, DELIBERATELY UNFIXED — a NUL byte in a tag
=================================================
``tags[]``'s ``^\\S(.*\\S)?$`` also accepts ``"\\x00"`` in EVERY position —
leading, trailing and embedded — because ``\\S`` matches NUL (NUL is not
whitespace) and ``.`` matches it too. ``"\\x00"`` on its own is a valid tag.
That is a real defect, but it is a DIFFERENT one: it is about which characters
``\\S`` covers, not about what ``$`` anchors, and ``fullmatch`` does not catch it
(the match legitimately consumes the whole string). It is pinned as
characterization in ``tests/test_schema_string_gate_exactness.py`` and reported
rather than silently folded in here, because widening this gate into a general
control-character policy is a scope decision for a human, not a side effect of an
anchoring fix.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError, validators

from .official import load_official_validator

__all__ = [
    "EXACTNESS_HEADING",
    "ExactnessError",
    "ExactnessReport",
    "check_exactness",
    "combined_summary",
    "declares_whole_string",
    "describe_characters",
]

#: Printed above the findings wherever they are shown to a person. It says "not a
#: schema rule" ON PURPOSE and that wording is load-bearing: the record under
#: discussion IS valid against the vendored official schema, and a surface that
#: let a reader think otherwise would be attributing an ISAAC policy to upstream.
EXACTNESS_HEADING = "Anchored-pattern exactness (ISAAC gate, not a schema rule):"


def declares_whole_string(pattern: str) -> bool:
    """True when a pattern says, in its own text, "this is the whole string".

    ``^...$``. The trailing ``$`` must be a real ANCHOR, not an escaped literal
    dollar, so the backslashes immediately before it are counted: an EVEN number
    (including none) leaves the ``$`` unescaped and anchoring; an ODD number means
    the last backslash escapes it and the pattern ends in a literal ``$``.

        ``^[0-9A-Z]{26}$``   0 backslashes, even -> anchored
        ``^costs \\\\$``       2 backslashes, even -> anchored (literal backslash)
        ``^costs \\$``        1 backslash,  odd  -> NOT anchored (literal dollar)
    """
    if not pattern.startswith("^") or not pattern.endswith("$"):
        return False
    backslashes = len(pattern[:-1]) - len(pattern[:-1].rstrip("\\"))
    return backslashes % 2 == 0


_CONTROL_NAMES = {
    "\t": "CHARACTER TABULATION",
    "\n": "LINE FEED",
    "\v": "LINE TABULATION",
    "\f": "FORM FEED",
    "\r": "CARRIAGE RETURN",
    "\x00": "NULL",
    "\x1c": "INFORMATION SEPARATOR FOUR",
    "\x1d": "INFORMATION SEPARATOR THREE",
    "\x1e": "INFORMATION SEPARATOR TWO",
    "\x85": "NEXT LINE",
}


def describe_characters(text: str) -> str:
    """Name characters WITHOUT reproducing them.

    A refusal message is rendered into a terminal, a JSON response and a web
    page. Echoing the offending bytes back would put a raw control character —
    the very thing being refused — into all three, and a message carrying a
    literal ``\\r`` or ``\\x1b`` can overwrite the line that explains it. So the
    character is always named, never emitted: ``U+000A LINE FEED``.

    ``unicodedata.name`` raises for control characters, which is precisely the
    class this gate deals with, hence the explicit table above and the
    ``U+XXXX <category>`` fallback for anything unlisted.
    """
    seen: list[str] = []
    for ch in text:
        name = _CONTROL_NAMES.get(ch)
        if name is None:
            try:
                name = unicodedata.name(ch)
            except ValueError:
                name = f"category {unicodedata.category(ch)}"
        label = f"U+{ord(ch):04X} {name}"
        if label not in seen:
            seen.append(label)
    return ", ".join(seen)


@dataclass
class ExactnessError:
    path: str
    message: str

    def render(self) -> str:
        return f"✗ {self.path} — {self.message}"


@dataclass
class ExactnessReport:
    errors: list[ExactnessError]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        if self.ok:
            return "PASS — every anchored schema pattern matches its value exactly"
        lines = [e.render() for e in self.errors]
        lines.append(f"FAIL ({len(self.errors)} inexact pattern matches)")
        return "\n".join(lines)


def _exact_pattern(validator, patrn, instance, schema):
    """Replacement for the ``pattern`` keyword that reports ONLY the leniency.

    Three deliberate silences, each of which would otherwise duplicate or
    contradict ``validate_official``:

    * a non-string instance is a ``type`` error, not this gate's business;
    * an unanchored pattern is left entirely alone (see the module docstring);
    * a value the schema ALREADY rejects (``re.search`` finds nothing) is passed
      over in silence, so a genuinely malformed value is reported once, by the
      schema, in the schema's own words — not twice in two vocabularies.

    What is left is exactly the gap: the schema says valid, the pattern's own
    text says it should not be.
    """
    if not validator.is_type(instance, "string"):
        return
    if not declares_whole_string(patrn):
        return
    if re.search(patrn, instance) is None:
        return
    if re.fullmatch(patrn, instance) is not None:
        return

    # The anchored match stops short of the end; whatever follows is what the
    # pattern's `$` let through.
    consumed = re.match(patrn, instance)
    tail = instance[consumed.end():] if consumed is not None else instance
    yield ValidationError(
        f"value is accepted by the schema pattern {patrn!r} only because Python's "
        f"'$' also matches before a trailing newline; the pattern is anchored and "
        f"the value does not match it exactly. Offending trailing character(s): "
        f"{describe_characters(tail)}. Remove them and resubmit — ISAAC will not "
        f"strip them for you, because editing a value you supplied would change "
        f"metadata you did not ask to change."
    )


#: The official schema, revalidated with ONE keyword swapped. Everything else
#: (``required``, ``enum``, ``type``, ``additionalProperties``, the ``if``/``then``
#: conditionals) still runs and still produces errors; ``check_exactness`` throws
#: those away. That is wasteful by a few hundred microseconds and correct by
#: construction: the alternative — walking the schema by hand to find the pattern
#: locations and resolving them against the record — is a second traversal engine
#: that would have to track ``properties``/``items``/``$ref``/conditionals and
#: would drift from what jsonschema actually does. Reusing the real traversal also
#: means ``absolute_path`` is right for free, including array indices.
_ExactnessValidator = validators.extend(
    Draft202012Validator, {"pattern": _exact_pattern}
)


def combined_summary(schema_summary: str, report: ExactnessReport) -> str:
    """The human-readable verdict for BOTH gates, in one string, clearly separated.

    Exists because the two consumers must not drift. ``POST /api/validate/record``
    returns ``summary`` and the web Validator renders it under "Full validator
    summary"; ``isaac validate --official`` prints the same thing. Without this,
    the web Validator showed a FAIL badge (``ok: false``) above a summary pane
    reading "PASS — valid against official ISAAC schema v1.05", with an empty
    structured error list and therefore no stated reason anywhere on screen — a
    surface contradicting itself about why it refused something.

    The schema summary is left FIRST and VERBATIM. An exact record returns it
    unchanged, so nothing about the ordinary path moves.
    """
    if report.ok:
        return schema_summary
    return f"{schema_summary}\n\n{EXACTNESS_HEADING}\n{report.render()}"


def _pattern_findings(errors) -> "list[ValidationError]":
    """Every ``_exact_pattern`` finding in a tree of validation errors.

    RECURSIVE ON ``context``, AND THAT IS THE WHOLE POINT. This used to be a flat
    ``if err.validator == "pattern"`` filter over ``iter_errors``, which is correct
    only while every pattern in the schema sits somewhere jsonschema reports
    directly. ``anyOf`` and ``oneOf`` do not report their branch errors: they yield
    ONE error carrying their own keyword name and hang the branch errors off
    ``.context``. Under the flat filter the top-level error was discarded for not
    being ``"pattern"`` and the real finding inside it was never looked at — a gate
    that silently stopped gating, reporting PASS.

    Every OTHER keyword's errors are still dropped by the caller: they belong to
    ``validate_official``, which reports them in its own words. This function
    selects, it does not judge.
    """
    found: list[ValidationError] = []
    for err in errors:
        if err.validator == "pattern":
            found.append(err)
            continue
        # `context` is None for every non-composition error, so this recursion is
        # a no-op on the ordinary path and costs one attribute read.
        found.extend(_pattern_findings(err.context or ()))
    return found


def check_exactness(record: dict, root: Path) -> ExactnessReport:
    """Report every anchored-pattern gate the record passes only by leniency.

    An empty report is the normal case and means nothing was found — NOT that
    the record is valid. Validity is ``validate_official``'s answer and this
    function deliberately does not duplicate it.
    """
    schema = load_official_validator(root).schema
    validator = _ExactnessValidator(schema)
    # DEDUPLICATED on (path, message). Composition keywords can present the same
    # finding more than once — two `anyOf` branches that both carry the same
    # pattern each fail, and both failures reach `context`. One value, one
    # sentence: reporting it twice would overstate what was found. The sort
    # includes the message so ordering is total, not merely stable-by-accident,
    # for the several-findings-at-one-path case.
    seen: dict[tuple[tuple[str, ...], str], ExactnessError] = {}
    for err in _pattern_findings(validator.iter_errors(record)):
        segments = tuple(str(p) for p in err.absolute_path)
        seen.setdefault(
            (segments, err.message),
            ExactnessError(path=".".join(segments) or "$", message=err.message),
        )
    return ExactnessReport([seen[key] for key in sorted(seen)])
