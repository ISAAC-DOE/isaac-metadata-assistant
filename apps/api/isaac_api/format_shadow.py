"""SHADOW format-aware validation. Advisory only; it arms nothing.

WHAT "SHADOW" MEANS, AND WHY IT IS NOT A SECOND VALIDATOR
=========================================================
:func:`isaac_records.official.validate_official` is the authority. This module
runs *alongside* it, over the same vendored schema, with one extra capability —
a JSON Schema ``format`` checker for ``date-time`` — and reports what that
capability would have found. It decides nothing. It gates nothing. No caller may
turn a :class:`ShadowResult` into a validity verdict, and nothing in this module
returns an ``ok``/``valid`` field, deliberately: the field is named ``passed``
and documented as *"the shadow found nothing"*, which is a weaker claim than
*"the record is valid"*.

The reason it exists as a shadow rather than as a fix: **arming ``format``
enforcement is Dean's decision, not ours.** It is question **Q20** in
``docs/dean-authorization-packet.md`` and it is UNANSWERED. Arming it would
change the meaning — and possibly the value — of
``records_passing_full_schema``, which ``apps/api/isaac_api/db_recon.py``
reports over 30 production-derived rows that belong to him. Until Q20 is
answered, ``format`` enforcement stays OFF and this module is how the question
can be *measured* without being *decided*.

THE TWO CAUSES, AND WHY NEITHER IS TOUCHED HERE
===============================================
``tests/test_truthpath_characterization.py`` pins both independent causes of
ISAAC's format-blindness, and both must remain true after importing this module:

* **Cause 1 (code)** — ``official.load_official_validator`` builds
  ``Draft202012Validator(schema)`` with no ``format_checker=``. Untouched: this
  module constructs its OWN validator and never reaches into ``official``.
* **Cause 2 (packaging)** — ``pyproject.toml`` declares plain ``jsonschema``,
  not ``jsonschema[format]``, so ``rfc3339-validator`` is absent and
  ``date-time`` is **not in the shared checker registry at all**. Untouched: no
  dependency is added, and the RFC3339 predicate below is hand-rolled from
  ``re`` + ``datetime``.

The mechanism that keeps Cause 2 true is worth stating explicitly, because the
obvious implementation breaks it. ``FormatChecker.checkers`` is a **class**
attribute; ``FormatChecker.cls_checks`` and ``@FormatChecker.cls_checks(...)``
register into it PROCESS-WIDE, so a module that used them would silently arm
``date-time`` for every ``FormatChecker()`` anyone constructs anywhere —
including any future one handed to the official validator. Instead:

    ``FormatChecker(formats=())`` → ``self.checkers = {}`` (a fresh INSTANCE
    dict, shadowing the class attribute), then ``instance.checks("date-time")``
    writes into that instance dict only.

Measured on jsonschema 4.26: the class registry is byte-identical before and
after this module is imported, and ``Draft202012Validator.FORMAT_CHECKER`` still
does not know ``date-time``. ``test_format_shadow.py`` re-measures it rather
than trusting this paragraph.

Starting from an EMPTY checker set (rather than from ``FormatChecker()``, which
inherits ``date``, ``email``, ``ipv4``, ``regex``, ``uuid``, …) is also
deliberate: the shadow then checks exactly the one format it implements and
claims nothing about any other. The vendored v1.05 schema declares only
``date-time``, so nothing is lost.

WHAT A FINDING MAY CARRY — THE RULE THAT MATTERS MOST
=====================================================
A :class:`ShadowFinding` carries a stable code, a pointer into the **schema**, a
rule-family label, and a pointer into the **instance**. It carries NO validator
message, NO instance value, and nothing else derived from record content.

This is not paranoia about a hypothetical. ``jsonschema`` messages echo the
offending value verbatim — ``"'not-a-date' is not a 'date-time'"``,
``"'CuO nanopowder' is not one of [...]"`` — so a finding that forwarded
``error.message`` would be a direct scientific-value leak the moment this ran
over anything but public fixtures. ``error.message`` is therefore **discarded**,
not truncated, not sanitized, not stored anywhere on the dataclass. The code is
constructed here, from ``(rule_family, schema_pointer)``, both of which are
properties of the PUBLIC vendored schema.

The price is paid honestly: two required properties missing from the same object
produce two errors that differ ONLY in the discarded message, so they collapse
into two *identical* findings. Multiplicity is preserved (findings are not
de-duplicated); identity is not recoverable. That is the trade, and it is the
right way round.

**Instance pointers are masked against the schema, which is more than the API
shape suggests.** An instance pointer looks like pure structure, but the v1.05
schema is ``additionalProperties``-open in places where the writer legitimately
keys a map by a scientific value (this repo's own fixtures key
``sample.composition`` by species). So an unmasked pointer such as
``/sample/composition/CuO`` would be a value leak wearing a path's clothing.
Every non-numeric segment is therefore emitted only if the vendored schema
declares that name somewhere; anything else becomes
:data:`MASK_UNDECLARED_SEGMENT`. Array **indices** are kept as digits, so the
pointer stays a well-formed RFC 6901 pointer — that is a deliberate, stated
residual: an index is a position in the record, and over a real corpus positions
are record-derived. If these are ever aggregated for publication, apply
``apps/api/isaac_api/disclosure.suppress_small_cells`` and read
``docs/superpowers/plans/2026-08-02-corpus-validation-authorization.md`` §3
first — a per-instance-path breakdown is the aggregate this project withdrew.

RFC3339 ``date-time`` — WHAT IS ACCEPTED AND WHAT IS REJECTED
=============================================================
Accepted, per RFC3339 §5.6 ``date-time``::

    YYYY-MM-DDThh:mm:ss[.fraction](Z | ±hh:mm)

* The offset is **REQUIRED**. RFC3339 has no offset-less ``date-time``; a naive
  local timestamp is rejected. (This is stricter than
  ``datetime.fromisoformat``, which is why that function is not used.)
* The ``T`` separator is required, and **lowercase ``t`` and ``z`` are
  accepted** — RFC3339 §5.6's NOTE explicitly permits lower case for both. The
  alternate space separator that the same NOTE mentions is **rejected**: the
  NOTE permits it only "for readability" in "some protocols", and JSON Schema's
  ``date-time`` is defined against the ABNF, where the separator is ``"T"``.
* A fraction, if present, must be ``.`` followed by at least one digit.
* The date must be a real calendar date: month, day and leap years are checked
  by constructing a :class:`datetime.date`, so ``2026-13-01`` and ``2026-02-30``
  are rejected.
* ``hh`` ≤ 23, ``mm`` ≤ 59; offset ``hh`` ≤ 23, offset ``mm`` ≤ 59.
  ``-00:00`` is accepted (RFC3339 §4.3: "unknown local offset").

**Leap seconds: ``:60`` IS ACCEPTED. Decision, reason, and limit.** RFC3339's
ABNF is ``time-second = 2DIGIT`` with the stated range 00–60, so ``:60`` is
conformant and a checker that rejected it would be *stricter than the standard
the schema points at* — the shadow would then report a violation of a rule
nobody wrote. What is NOT done is verifying that a given ``:60`` falls on an
actual announced leap second: that needs an IERS leap-second table this project
does not vendor, and inventing one would be guessing (``CLAUDE.md`` §5). So the
honest contract is: *shape-conformant leap seconds pass; whether the instant
existed is not checked.*

This deliberately DIVERGES from ``is_canonical_rfc3339`` in
``tests/test_truthpath_characterization.py``, which rejects ``:60`` because it
routes through ``strptime``. That helper says so in its own docstring, and its
job is different — it is compatibility evidence about the public corpus, where
no value uses a leap second, so the two never disagree on real input.

There is a **second** divergence, and unlike the first it was not documented
anywhere before this module existed: that helper anchors with ``$``, which in
Python also matches immediately before a trailing newline, so it accepts
``"2026-08-02T12:00:00Z\\n"``. This module anchors with ``\\Z`` and rejects it.
That is a small real defect in the helper; it does not affect the helper's
corpus conclusion (no public example carries trailing whitespace, re-measured
here through the strict checker), and it is recorded rather than fixed because
that file is outside this module's write scope.
``test_format_shadow.py::test_the_two_date_checkers_in_this_repo_disagree_in_exactly_two_places``
pins both divergences rather than leaving either to be discovered.

WHAT THIS MODULE IS NOT
=======================
* **No database, no network, no filesystem write.** The only file read is the
  vendored schema, resolved through ``isaac_records.official.schema_path`` so
  there is exactly one notion of "the authoritative schema" in the process.
* **Not in the truth path.** It imports from ``isaac_records.official`` and
  writes to nothing under ``src/`` or ``schema/``.
* **No clock, no randomness.** Findings are sorted deterministically; the
  RFC3339 predicate never consults "now".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from isaac_records.official import schema_path

__all__ = [
    "FORMAT_DATE_TIME",
    "MASK_UNDECLARED_SEGMENT",
    "SHADOW_ERROR_CODES",
    "ShadowFinding",
    "ShadowResult",
    "declared_format_paths",
    "declared_formats",
    "is_rfc3339_date_time",
    "shadow_error_code",
    "shadow_validate",
]

# --------------------------------------------------------------------------
# RFC3339 date-time
# --------------------------------------------------------------------------

#: The one format name this module implements. Named as a constant so the code
#: table and the checker registration cannot drift apart.
FORMAT_DATE_TIME = "date-time"

#: Shape gate. Deliberately hand-rolled: no dependency is added (Cause 2 must
#: stay unfixed), and ``datetime.fromisoformat`` is unusable here because it
#: accepts an offset-less string and a date-only string, both of which RFC3339's
#: ``date-time`` production forbids.
#:
#: ``[Tt]`` / ``[Zz]``: RFC3339 §5.6 NOTE permits lower case for both.
#: ``\Z`` not ``$``: Python's ``$`` also matches immediately before a trailing
#: newline, so ``^...$`` would let ``"2026-01-01T00:00:00Z\n"`` through.
_RFC3339_SHAPE = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"[Tt]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?P<fraction>\.\d+)?"
    r"(?P<offset>[Zz]|[+-]\d{2}:\d{2})\Z"
)


def is_rfc3339_date_time(value: Any) -> bool:
    """True only for a full RFC3339 ``date-time`` with a real calendar date.

    See the module docstring for the complete accept/reject contract. In short:
    the offset is required, the ``T``/``Z`` may be lower case, a space separator
    is refused, the calendar date is really checked, and a shape-conformant
    ``:60`` leap second is ACCEPTED without being verified against a
    leap-second table.

    Never raises. Anything that is not a :class:`str` — including ``None`` and
    numbers — is False, because a non-string is not an RFC3339 ``date-time``.

    Note the deliberate split with :func:`_check_date_time`, the adapter
    registered with the format checker, which returns **True** for a non-string.
    That is not an inconsistency: this predicate answers *"is this value an
    RFC3339 date-time?"*, while a JSON Schema ``format`` checker answers *"does
    this value violate the format?"* — and ``format`` applies only to instances
    of the type it is defined for. A checker that objected to ``12345`` would
    emit a format finding on top of the ``type: string`` finding the schema
    already produces, inventing a rule the schema does not state and
    contradicting
    ``tests/test_truthpath_characterization.py::test_a_non_string_is_rejected_by_type_not_by_format``.
    """
    if not isinstance(value, str):
        return False
    match = _RFC3339_SHAPE.match(value)
    if match is None:
        return False

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        # Real calendar check, including leap years: 2026-02-30 and 2026-13-01
        # are rejected here, not by the regex.
        date(year, month, day)
    except ValueError:
        return False

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
    if hour > 23 or minute > 59:
        return False
    # 60 is the leap second. See the module docstring for the decision and its
    # stated limit: the shape is accepted, the instant is not verified.
    if second > 60:
        return False

    offset = match.group("offset")
    if offset not in ("Z", "z"):
        if int(offset[1:3]) > 23 or int(offset[4:6]) > 59:
            return False
    return True


# --------------------------------------------------------------------------
# The private, instance-scoped format checker
# --------------------------------------------------------------------------

# `formats=()` starts from an EMPTY registry and, critically, rebinds
# `self.checkers` to a fresh INSTANCE dict. Registering through the resulting
# instance therefore cannot reach `FormatChecker.checkers` (the class
# attribute), `FormatChecker()` constructed elsewhere, or
# `Draft202012Validator.FORMAT_CHECKER`. `FormatChecker.cls_checks` would reach
# all three and is never used here.
_SHADOW_FORMAT_CHECKER = FormatChecker(formats=())


@_SHADOW_FORMAT_CHECKER.checks(FORMAT_DATE_TIME)
def _check_date_time(value: Any) -> bool:
    """Adapter for :func:`is_rfc3339_date_time`; registered on the INSTANCE.

    Returns True for a non-string, which is the convention every stdlib
    jsonschema format checker follows: JSON Schema's ``format`` applies only to
    instances of the type it is defined for, so a non-string is *not applicable*
    rather than *invalid*. Without this, ``created_utc = 12345`` would produce a
    ``FORMAT_DATE_TIME`` finding stacked on the real ``TYPE_MISMATCH`` — a
    second complaint about a rule the schema does not state, and a direct
    contradiction of the behaviour
    ``tests/test_truthpath_characterization.py`` pins.
    """
    if not isinstance(value, str):
        return True
    return is_rfc3339_date_time(value)


# --------------------------------------------------------------------------
# Schema introspection — everything below is derived from the vendored schema
# --------------------------------------------------------------------------

#: An instance-pointer segment the vendored schema does not declare as a
#: property name. It is either drift or a value used as a map key (v1.05 is
#: ``additionalProperties``-open in ~14 places), so it must not be named.
MASK_UNDECLARED_SEGMENT = "<undeclared>"


def _escape(segment: str) -> str:
    """RFC 6901 escaping: ``~`` → ``~0``, ``/`` → ``~1``. Order matters."""
    return str(segment).replace("~", "~0").replace("/", "~1")


def _pointer(segments: tuple[str, ...]) -> str:
    """Render already-escaped segments as an RFC 6901 pointer.

    The root is ``""``, per RFC 6901 — NOT ``"/"``, which is the pointer to a
    member whose key is the empty string. (``corpus_mutation.pointer`` renders
    the root as ``"/"``; that module's targets are never the root, so the
    difference never surfaces there. Stated here so the two are not assumed
    interchangeable.)
    """
    return "".join("/" + seg for seg in segments)


@lru_cache(maxsize=4)
def _introspect(path_str: str, mtime_ns: int, size: int) -> tuple[
    tuple[tuple[str, str], ...], frozenset[str]
]:
    """Cached walk of the vendored schema.

    Returns ``((schema_pointer, format_name), ...)`` for every subschema that
    declares a ``format``, plus every property name the schema declares
    anywhere.

    Cache key parity with ``official._checked_schema_text``: path +
    ``st_mtime_ns`` + ``st_size``, with the same honest limit — an edit landing
    in the same nanosecond tick AND leaving the byte length unchanged is served
    stale. It is a heuristic, not content identity.
    """
    document = json.loads(Path(path_str).read_text(encoding="utf-8"))
    formats: dict[str, str] = {}
    declared: set[str] = set()

    def walk(node: Any, segments: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            fmt = node.get("format")
            if isinstance(fmt, str):
                formats[_pointer(segments)] = fmt
            properties = node.get("properties")
            if isinstance(properties, dict):
                for name in properties:
                    declared.add(str(name))
            for key, value in node.items():
                walk(value, segments + (_escape(str(key)),))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, segments + (str(index),))

    walk(document, ())
    return (
        tuple(sorted(formats.items())),
        frozenset(declared),
    )


def _introspect_root(root: Path) -> tuple[tuple[tuple[str, str], ...], frozenset[str]]:
    path = schema_path(Path(root))
    stat = path.stat()
    return _introspect(str(path), stat.st_mtime_ns, stat.st_size)


def declared_formats(root: Path) -> tuple[tuple[str, str], ...]:
    """Every ``(schema_pointer, format_name)`` the vendored schema declares.

    Sorted by pointer, so the order is a property of the schema and not of dict
    iteration. For v1.05 this is six entries, all ``date-time`` — re-derived
    here rather than written down, so it cannot drift from the schema.
    """
    formats, _ = _introspect_root(root)
    return formats


def declared_format_paths(root: Path) -> tuple[str, ...]:
    """Every schema pointer that declares a ``format``. See :func:`declared_formats`."""
    return tuple(pointer for pointer, _ in declared_formats(root))


# --------------------------------------------------------------------------
# Stable, CLOSED error codes
# --------------------------------------------------------------------------

#: jsonschema keyword → code. Anything absent maps to ``OTHER``; the set below
#: is CLOSED so a new jsonschema keyword, or a keyword that only appears once a
#: future schema uses it, can never invent a code a consumer has not seen.
_KEYWORD_CODES: dict[str, str] = {
    "additionalProperties": "ADDITIONAL_PROPERTIES",
    "const": "CONST_MISMATCH",
    "enum": "ENUM_NOT_ALLOWED",
    "pattern": "PATTERN_MISMATCH",
    "required": "REQUIRED_MISSING",
    "type": "TYPE_MISMATCH",
}

#: Declared ``format`` name → code. The format name is read out of the SCHEMA at
#: the finding's schema pointer, never off the validator's error message and
#: never off the instance, so the code is a function of public information only.
_FORMAT_CODES: dict[str, str] = {
    FORMAT_DATE_TIME: "FORMAT_DATE_TIME",
}

#: The complete, closed code vocabulary. A consumer may switch on this tuple
#: exhaustively.
SHADOW_ERROR_CODES: tuple[str, ...] = tuple(
    sorted({*_KEYWORD_CODES.values(), *_FORMAT_CODES.values(), "OTHER"})
)


def shadow_error_code(
    rule_family: str,
    schema_pointer: str,
    formats: Mapping[str, str] | None = None,
) -> str:
    """Derive a stable code from ``(rule_family, schema_pointer)``.

    TOTAL by construction: every input returns a member of
    :data:`SHADOW_ERROR_CODES`, with ``OTHER`` as the terminal fallback. That
    includes a ``format`` family whose declared format this module does not
    implement — it is reported as ``OTHER`` rather than as a date-time finding,
    because the shadow only knows how to check ``date-time`` and must not imply
    otherwise.

    ``formats`` is the ``pointer → format-name`` map from
    :func:`declared_formats`. It is a parameter so tests can drive the table
    directly; it is not a widening seam — every value in it comes from the
    public vendored schema.
    """
    if rule_family == "format":
        declared = (formats or {}).get(schema_pointer)
        return _FORMAT_CODES.get(str(declared), "OTHER")
    return _KEYWORD_CODES.get(str(rule_family), "OTHER")


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ShadowFinding:
    """One shadow observation. Carries no message and no instance value.

    Every field is safe to serialise:

    * ``code`` — a member of :data:`SHADOW_ERROR_CODES`, constructed here.
    * ``schema_path`` — an RFC 6901 pointer into the PUBLIC vendored schema,
      with the trailing keyword segment stripped so it addresses the subschema
      that declared the rule rather than the keyword itself.
    * ``rule_family`` — the jsonschema keyword (``format``, ``type``, …).
    * ``instance_path`` — an RFC 6901 pointer into the record, with every
      non-numeric segment masked unless the schema declares that property name.
      See the module docstring for the stated residual about array indices.
    """

    code: str
    schema_path: str
    rule_family: str
    instance_path: str


@dataclass(frozen=True)
class ShadowResult:
    """The outcome of one shadow run.

    ``passed`` means *the shadow found nothing*. It is deliberately NOT called
    ``ok`` or ``valid``: only ``isaac_records.official.validate_official``
    decides validity, and a caller that renamed this field would be inventing a
    second authority.
    """

    passed: bool
    findings: tuple[ShadowFinding, ...]


def _mask_instance_segment(segment: Any, declared: frozenset[str]) -> str:
    """Emit an instance-pointer segment only if it is public information.

    Integers are array indices and are emitted as digits (see the module
    docstring for the stated residual). A string survives only if the vendored
    schema declares it as a property name somewhere; everything else — an
    undeclared key, or a scientific value used as a key inside an
    ``additionalProperties``-open map — becomes :data:`MASK_UNDECLARED_SEGMENT`.

    Same policy, and the same reasoning, as ``db_recon.safe_key_segment``. It is
    reimplemented rather than imported because ``db_recon`` pulls in the API
    workspace layer and a database driver's worth of module docstring, and this
    module must stay importable from the truth-path test suite with nothing else
    loaded.
    """
    if isinstance(segment, bool):  # bool before int: bool is an int subclass
        return MASK_UNDECLARED_SEGMENT
    if isinstance(segment, int):
        return str(segment)
    text = str(segment)
    if text in declared:
        return _escape(text)
    return MASK_UNDECLARED_SEGMENT


def _finding_from_error(
    error: Any, formats: Mapping[str, str], declared: frozenset[str]
) -> ShadowFinding:
    """Build a finding from a ``ValidationError``, DISCARDING ``error.message``.

    ``error.message`` is never read. It is the field that echoes the offending
    value verbatim, and the whole redaction posture of this module rests on it
    never being touched.
    """
    rule_family = str(error.validator)

    schema_segments = [_escape(str(seg)) for seg in error.absolute_schema_path]
    # Strip the trailing keyword so the pointer addresses the SUBSCHEMA that
    # declared the rule (``/properties/timestamps/properties/created_utc``)
    # rather than the keyword node (``.../format``). The keyword is carried
    # separately as ``rule_family``, so nothing is lost.
    if schema_segments and schema_segments[-1] == _escape(rule_family):
        schema_segments.pop()
    schema_pointer = _pointer(tuple(schema_segments))

    instance_pointer = _pointer(
        tuple(_mask_instance_segment(seg, declared) for seg in error.absolute_path)
    )

    return ShadowFinding(
        code=shadow_error_code(rule_family, schema_pointer, formats),
        schema_path=schema_pointer,
        rule_family=rule_family,
        instance_path=instance_pointer,
    )


@lru_cache(maxsize=4)
def _shadow_validator(path_str: str, mtime_ns: int, size: int) -> Draft202012Validator:
    """A SEPARATE validator, armed with this module's private format checker.

    Constructed here and nowhere else. ``official.load_official_validator`` is
    not called, not wrapped and not modified — the two validators share only the
    schema file they both read.
    """
    schema = json.loads(Path(path_str).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=_SHADOW_FORMAT_CHECKER)


def shadow_validate(record: Mapping[str, Any], root: Path) -> ShadowResult:
    """Validate ``record`` against the vendored schema WITH format checking.

    Advisory. The result must not be turned into a validity verdict — see the
    module docstring, and Q20 in ``docs/dean-authorization-packet.md``.

    ``record`` is never modified. Findings are returned in a deterministic order
    — ``(instance_path, schema_path, code, rule_family)`` — and are deliberately
    NOT de-duplicated: two required properties missing from one object differ
    only in the message this module discards, so collapsing them would silently
    under-count. Multiplicity is preserved; which property is missing is not
    recoverable, and that is the intended trade.
    """
    root = Path(root)
    path = schema_path(root)
    stat = path.stat()
    validator = _shadow_validator(str(path), stat.st_mtime_ns, stat.st_size)

    formats = dict(declared_formats(root))
    _, declared = _introspect_root(root)

    findings = [
        _finding_from_error(error, formats, declared)
        for error in validator.iter_errors(dict(record))
    ]
    findings.sort(
        key=lambda f: (f.instance_path, f.schema_path, f.code, f.rule_family)
    )
    return ShadowResult(passed=not findings, findings=tuple(findings))
