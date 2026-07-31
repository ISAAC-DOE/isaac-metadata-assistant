"""Deterministic, machine-comparable normalization of official-schema errors.

This module introduces **no schema of its own**. It is a pure normalization
layer over :mod:`isaac_records.official`, whose vendored
``schema/isaac_record_v1.json`` (pinned v1.05) is the sole authority on record
structure, required fields and vocabulary.

Why this layer exists
---------------------
``official.validate_official`` renders errors for humans. Four properties it
does not provide are needed to compare, diff and address validation results
mechanically:

1. **A pointer to the missing field.** jsonschema's ``required`` errors carry no
   path to the absent property: for ``{"isaac_record_version": "1.05"}`` every
   root ``required`` error has ``absolute_path == []``, so
   ``validate_official`` collapses all of them onto ``$``. Here the pointer is
   ``absolute_path + [missing_name]`` — the pointer of the missing field itself.
2. **Plain vs. conditional requirement.** Instance paths cannot tell them apart;
   *schema* paths can. A plain root requirement has schema path ``['required']``;
   the ``record_type == evidence`` ⇒ ``descriptors`` rule has
   ``['allOf', 0, 'then', 'required']``. ``conditional`` is True iff the schema
   path traverses ``if``/``then``/``else``. ``allOf`` alone is *not* conditional.
3. **A total, stable order.** ``official.py`` sorts on
   ``list(map(str, e.absolute_path))``, which string-sorts array indices, so
   index ``10`` sorts before index ``2``. Here integer segments sort numerically.
4. **Missing vs. invalid.** ``required`` failures mean "no value at all"; every
   other keyword means "a value is present and wrong". Those are different
   remedies and are labelled distinctly.

The full-schema invariant
-------------------------
**As written**, this module validates only against the complete authoritative
schema:

* the validator is obtained **only** from ``official.load_official_validator``;
* ``diagnose`` takes exactly ``(record, root)`` — there is no schema, subschema,
  validator or keyword-filter parameter to inject a partial schema through;
* this module never imports ``jsonschema``, never constructs a validator, and
  never parses a schema document (no ``json.load``/``json.loads`` anywhere);
* the only direct read of the schema file is ``read_bytes()`` of the *whole*
  file, via ``official.schema_path``, to fingerprint it.

The tests below enforce each of those properties against this module's own
source. **They guard known regression shapes; they are not a proof that no
bypass exists**, and an earlier version of this docstring wrongly claimed the
module was "structurally incapable" of anything else. An independent review
refuted that in one edit: ``load_official_validator(root).evolve(schema=trimmed)``
needs no new import, no file read and no identifier containing "Validator", so
it passed every structural test while silently dropping ``required`` failures —
and the report still advertised the full-schema fingerprint. A module-global
``_VALIDATOR_OVERRIDE`` consulted before the loader passed too. Both shapes are
now explicitly forbidden by tests, but the honest statement is "the enforced
list above", not "incapable by construction".

Relatedly, in :mod:`isaac_records.official`: ``load_official_validator`` used to
hand every caller the **same** ``lru_cache``d validator, so mutating
``load_official_validator(root).schema`` in one place changed what both
``diagnose`` and ``validate_official`` enforced everywhere else, while
:attr:`DiagnosticReport.schema_fingerprint` kept reporting the pristine file.
That cross-caller channel is closed: only the schema *text* is cached, and each
call parses it afresh into a private validator. A caller can still mutate the
object *it* was handed — Python cannot prevent that — but the mutation cannot
reach another caller or a later validation.

What the fingerprint attests is unchanged by that fix, and should not be
overread: it is the sha256 of the bytes on disk, i.e. the document this report's
validator was built from, not a proof that the in-memory object was never
touched between construction and use.

Every diagnostic is ``blocking``: each one is an official-schema hard failure.
The soft-warning tier (``NO_LINKS``, ``MISSING_PH``, ...) is a different tier
entirely (see :mod:`isaac_records.portal_warnings`) and is never represented
here, so ``blocking`` can never be False. It is carried explicitly so callers
read the tier off the diagnostic rather than assuming it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .official import EXPECTED_VERSION, load_official_validator, schema_path

__all__ = [
    "MISSING",
    "INVALID",
    "Diagnostic",
    "DiagnosticReport",
    "DiagnosticsIntegrityError",
    "diagnose",
    "json_pointer",
    "schema_fingerprint",
]

#: A value is absent altogether (the ``required`` keyword).
MISSING = "missing"
#: A value is present but violates the schema (every other keyword).
INVALID = "invalid"

_REQUIRED_SUFFIX = " is a required property"

# Keywords whose value is a mapping of *names* to subschemas. A segment that
# directly follows one of these is a property name, never a schema keyword —
# without this, a record field legitimately named "if"/"then"/"else" would be
# misread as a conditional.
_NAME_MAP_KEYWORDS = frozenset(
    {
        "properties",
        "patternProperties",
        "dependentSchemas",
        "dependentRequired",
        "$defs",
        "definitions",
    }
)

_CONDITIONAL_KEYWORDS = frozenset({"if", "then", "else"})


class DiagnosticsIntegrityError(RuntimeError):
    """An internal assumption about the underlying validator no longer holds.

    Raised instead of emitting a diagnostic that could point at the wrong field.
    A silently wrong pointer is the worst possible outcome for a no-guessing
    system, so this failure is loud and stops the whole report.
    """


def json_pointer(segments: Sequence[Any]) -> str:
    """Build an RFC 6901 JSON Pointer from path segments.

    Escaping is ``~`` → ``~0`` then ``/`` → ``~1``, in that order (reversing the
    order would corrupt ``~`` in a segment that also contains ``/``). Integer
    segments are array indices and are rendered verbatim. The root pointer is
    the empty string.
    """
    out = []
    for segment in segments:
        if isinstance(segment, bool):  # bool is an int subclass; not a valid segment
            raise DiagnosticsIntegrityError(
                f"boolean path segment is not a valid JSON Pointer token: {segment!r}"
            )
        if isinstance(segment, int):
            out.append(str(segment))
        else:
            out.append(str(segment).replace("~", "~0").replace("/", "~1"))
    return "".join("/" + token for token in out)


def schema_fingerprint(root: Path) -> str:
    """Lowercase hex sha256 of the authoritative schema file's raw bytes.

    Deliberately hashes the *bytes*, not a parsed-and-re-serialized form: the
    fingerprint must change if the file changes at all, including formatting.
    Deliberately uncached so it can never report a stale digest.
    """
    return hashlib.sha256(schema_path(root).read_bytes()).hexdigest()


@dataclass(frozen=True)
class Diagnostic:
    """One normalized official-schema failure.

    Attributes:
        pointer: RFC 6901 pointer into the **record** instance. For a missing
            field this is the pointer of the missing field itself.
        schema_pointer: RFC 6901 pointer into the **schema**, at the keyword
            that failed. This is what distinguishes a plain requirement from a
            conditional one.
        rule_family: the jsonschema keyword that failed (``required``, ``type``,
            ``enum``, ``const``, ``pattern``, ``additionalProperties``,
            ``minItems``, ``oneOf``, ``not``, ...). Taken from the validator, not
            from a catalog of our own.
        kind: :data:`MISSING` or :data:`INVALID`.
        label: human-readable trail, derived from ``pointer`` (see
            :func:`_derive_label`).
        message: the raw jsonschema message, verbatim and unedited.
        conditional: True iff ``schema_pointer`` traverses ``if``/``then``/
            ``else``.
        blocking: always True — see the module docstring.
    """

    #: RFC 6901 JSON Pointer into the RECORD.
    #:
    #: CAVEAT for consumers that highlight a field: for ``required`` this points
    #: at the missing field itself, but for ``additionalProperties`` it points at
    #: the PARENT object — the offending key name exists only inside
    #: :attr:`message`. Both keywords occur 37 times in v1.05, so this is the
    #: second-largest failure class, not an edge case.
    pointer: str
    schema_pointer: str
    rule_family: str
    kind: str
    label: str
    message: str
    conditional: bool
    blocking: bool


@dataclass(frozen=True)
class DiagnosticReport:
    """The complete, deterministically ordered diagnostic set for one record."""

    #: Hex sha256 of the schema file's raw BYTES ON DISK.
    #:
    #: It attests the *file on disk at report time*, re-read fresh here — NOT,
    #: strictly, the document the validator was built from. Those are the same
    #: document in every realistic case, but ``official`` serves the schema text
    #: from a cache keyed on ``(path, st_mtime_ns, st_size)``, so a replacement
    #: written in the same nanosecond tick at the same byte length would leave
    #: the two disagreeing. Do not read this digest as proof of what ran.
    #:
    #: What DID improve: ``official.load_official_validator`` now parses the
    #: schema afresh per call, so a mutation made through one caller's validator
    #: can no longer change what this module or ``validate_official`` enforce for
    #: anyone else. This value remains a digest of a document, not a certificate
    #: that this report's own validator object went untouched between
    #: construction and use.
    diagnostics: tuple[Diagnostic, ...]
    schema_version: str
    schema_fingerprint: str

    @property
    def ok(self) -> bool:
        """True iff the record has no official-schema failures."""
        return not self.diagnostics

    def missing(self) -> tuple[Diagnostic, ...]:
        """Diagnostics for absent fields, in report order."""
        return tuple(d for d in self.diagnostics if d.kind == MISSING)

    def invalid(self) -> tuple[Diagnostic, ...]:
        """Diagnostics for present-but-wrong values, in report order."""
        return tuple(d for d in self.diagnostics if d.kind == INVALID)


def _missing_required_name(err: Any) -> str:
    """Resolve which property a ``required`` error is about.

    jsonschema gives no path to the missing property; the name appears only in
    the message, formatted as ``f"{name!r} is a required property"``. Rather
    than trust prose, the name is resolved **out of the schema's own required
    list**: candidates are the entries of ``validator_value`` that are genuinely
    absent from ``instance``, and the message is used only to pick which
    candidate. The returned name is therefore always a real element of the
    authoritative required list that is really missing.

    The self-check is then restated explicitly, and any failure to resolve
    exactly one candidate raises :class:`DiagnosticsIntegrityError`.
    """
    required = getattr(err, "validator_value", None)
    instance = getattr(err, "instance", None)
    message = getattr(err, "message", None)

    if not isinstance(required, (list, tuple)):
        raise DiagnosticsIntegrityError(
            "'required' error carries a non-list validator_value "
            f"({type(required).__name__}); cannot resolve the missing property"
        )
    if not isinstance(instance, dict):
        raise DiagnosticsIntegrityError(
            "'required' error carries a non-object instance "
            f"({type(instance).__name__}); cannot resolve the missing property"
        )
    if not isinstance(message, str) or not message.endswith(_REQUIRED_SUFFIX):
        raise DiagnosticsIntegrityError(
            "jsonschema 'required' message format changed; expected a message "
            f"ending in {_REQUIRED_SUFFIX!r}, got {message!r}. Refusing to guess "
            "which property is missing."
        )

    token = message[: -len(_REQUIRED_SUFFIX)]
    absent = [name for name in required if name not in instance]
    candidates = [name for name in absent if repr(name) == token]

    if len(candidates) != 1:
        raise DiagnosticsIntegrityError(
            f"could not resolve the missing property for message {message!r}: "
            f"{len(candidates)} of the absent required properties {absent!r} "
            "match it. Refusing to emit a possibly-wrong pointer."
        )

    name = candidates[0]
    # Restate the invariant explicitly; unreachable while the above holds.
    if name not in required or name in instance:
        raise DiagnosticsIntegrityError(
            f"self-check failed for resolved property {name!r}: "
            f"in required={name in required}, present in instance={name in instance}"
        )
    return name


def _is_conditional(schema_path_segments: Sequence[Any]) -> bool:
    """True iff the schema path traverses ``if``/``then``/``else``.

    A segment counts only in *keyword* position: one that directly follows
    ``properties`` (or another name-mapping keyword) is a field name and is
    skipped, so a record field named ``then`` cannot masquerade as a
    conditional. ``allOf`` on its own is not conditional.
    """
    previous: Any = None
    for segment in schema_path_segments:
        if isinstance(previous, str) and previous in _NAME_MAP_KEYWORDS:
            # This segment is a property NAME, not a keyword. Reset to None
            # rather than to the name: a NAME can never itself open a name map,
            # so carrying it forward would skip the FOLLOWING segment too. With
            # ``previous = segment`` a field literally named ``properties``
            # caused ('properties', 'properties', 'then', 'required') to report
            # False — the mirror image of the bug this function exists to
            # prevent. Not reachable in v1.05 (no declared name collides with a
            # name-map keyword) but a schema refresh could introduce one.
            previous = None
            continue
        if isinstance(segment, str) and segment in _CONDITIONAL_KEYWORDS:
            return True
        previous = segment
    return False


def _title_word(word: str) -> str:
    """Capitalize a word only when it carries no casing information of its own.

    ``record`` → ``Record``, but ``K``, ``mA``, ``pH``, ``RHE`` and ``cm2`` are
    left exactly as the schema wrote them. Blanket title-casing would destroy
    unit and symbol casing (``mA_cm2`` → ``Ma Cm2``), which for a scientific
    record is a loss of meaning, not a cosmetic difference.
    """
    if word.isalpha() and word.islower():
        return word[:1].upper() + word[1:]
    return word


def _label_segment(segment: Any) -> str:
    if isinstance(segment, int):
        # 0-based, matching the JSON Pointer exactly: label "item 10" always
        # corresponds to pointer segment "/10". 1-based numbering would read
        # more naturally but would let a reader mistrust a correct pointer.
        return f"item {segment}"
    words = [_title_word(w) for w in str(segment).split("_") if w]
    return " ".join(words) or "(unnamed field)"


def _derive_label(segments: Sequence[Any]) -> str:
    """Derive a human-readable trail from the record path segments.

    Purely positional: nothing is read out of the schema, so no vocabulary,
    title or description is duplicated here. The authoritative schema declares
    exactly one ``title`` (the root schema's own) and no property titles, so
    there is nothing to reuse in any case.

    Underscores become spaces, words that carry no casing of their own are
    capitalized, array indices render as ``item <n>`` (0-based), and segments
    join with ``→`` so nesting reads as a trail. The root is ``Record``. The
    result is never empty and never contains a raw ``$`` or a JSON Pointer.
    """
    if not segments:
        return "Record"
    return " → ".join(_label_segment(s) for s in segments)


def _sort_key(entry: tuple[tuple[Any, ...], Diagnostic]) -> tuple:
    """Total, stable order over diagnostics.

    Primary key is the instance path with **integer segments compared
    numerically** (``(0, index, "")`` for ints, ``(1, 0, key)`` for strings), so
    ``/links/2`` precedes ``/links/10``. Then ``rule_family``, then ``message``,
    then unconditional before conditional, then ``schema_pointer``.

    The last two tiebreakers matter for de-duplication: when the same missing
    field is asserted by more than one schema branch, the retained diagnostic is
    the unconditional one if any, and otherwise the lowest schema pointer — never
    whichever the validator happened to yield first.
    """
    segments, diagnostic = entry
    path_key = tuple(
        (0, s, "") if isinstance(s, int) else (1, 0, str(s)) for s in segments
    )
    return (
        path_key,
        diagnostic.rule_family,
        diagnostic.message,
        diagnostic.conditional,
        diagnostic.schema_pointer,
    )


def diagnose(record: dict, root: Path) -> DiagnosticReport:
    """Normalize official-schema validation of ``record`` into diagnostics.

    The validator is obtained solely from
    :func:`isaac_records.official.load_official_validator`, i.e. always the
    complete authoritative schema. There is deliberately no parameter through
    which a partial schema, subschema or alternative validator could be
    supplied.

    Raises:
        DiagnosticsIntegrityError: if a ``required`` error's missing property
            cannot be resolved unambiguously from the schema's required list.
    """
    validator = load_official_validator(root)

    entries: list[tuple[tuple[Any, ...], Diagnostic]] = []
    for err in validator.iter_errors(record):
        instance_segments: tuple[Any, ...] = tuple(err.absolute_path)
        schema_segments: tuple[Any, ...] = tuple(err.absolute_schema_path)
        rule_family = str(err.validator)

        if rule_family == "required":
            instance_segments = instance_segments + (_missing_required_name(err),)
            kind = MISSING
        else:
            kind = INVALID

        entries.append(
            (
                instance_segments,
                Diagnostic(
                    pointer=json_pointer(instance_segments),
                    schema_pointer=json_pointer(schema_segments),
                    rule_family=rule_family,
                    kind=kind,
                    label=_derive_label(instance_segments),
                    message=err.message,
                    conditional=_is_conditional(schema_segments),
                    blocking=True,
                ),
            )
        )

    entries.sort(key=_sort_key)

    deduped: list[Diagnostic] = []
    seen: set[tuple[str, str, str]] = set()
    for _segments, diagnostic in entries:
        identity = (diagnostic.pointer, diagnostic.rule_family, diagnostic.message)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(diagnostic)

    return DiagnosticReport(
        diagnostics=tuple(deduped),
        schema_version=EXPECTED_VERSION,
        schema_fingerprint=schema_fingerprint(root),
    )
