"""Seam 2 — transcript or note text becomes CANDIDATE field patches.

THE ONE INVARIANT THIS MODULE EXISTS TO ENFORCE
===============================================
**Extraction proposes; a scientist disposes.** Every output of this seam is a
:class:`FieldCandidate`: a proposed value, the verbatim words it came from, and
the rule that read them. It is never a value, never evidence, and never applied.

The invariant is structural, not documentary. :class:`FieldCandidate` has **no
field** for status, verification, evidence, or acceptance. ``status``,
``verified``, ``is_evidence`` and ``requires_user_confirmation`` are read-only
properties returning constants, on a frozen, slotted dataclass — so

* ``FieldCandidate(..., verified=True)`` raises ``TypeError`` — no such field,
* ``dataclasses.replace(c, verified=True)`` raises ``TypeError``,
* ``c.verified = True`` is refused by the frozen ``__setattr__``,
* ``object.__setattr__(c, "verified", True)`` — the escape hatch that DOES work
  on an ordinary frozen dataclass field — raises ``AttributeError``, because
  ``verified`` is a property with no setter and never a field,
* ``object.__setattr__(c, "some_new_flag", True)`` raises ``AttributeError`` too,
  because ``slots=True`` leaves no instance ``__dict__`` to smuggle it into.

``test_providers.py`` exercises all five as the negative control for this slice.

Two precisions, because an overstated guarantee is worse than a modest one.
**(a)** ``object.__setattr__`` can still overwrite an ordinary *field* — that is
true of every frozen dataclass, and this module uses it itself in
``__post_init__``. What it cannot reach is the four constants, because they are
not fields. **(b)** ``frozen=True`` combined with ``slots=True`` makes a plain
``c.anything = x`` raise ``TypeError`` rather than ``FrozenInstanceError`` on
CPython: ``slots=True`` rebuilds the class, leaving the generated
``__setattr__``'s zero-argument ``super()`` cell pointing at the original. The
assignment is refused either way; only the exception type is surprising, and the
test accepts both rather than pinning an implementation detail.

The point is that there is no *careful code* holding this together, and therefore
nothing for a later edit to be careless about. Making a candidate present as
verified requires adding a field, which is a visible change to this file.

HOW A CANDIDATE BECOMES A VALUE — AND IT IS NOT THROUGH HERE
============================================================
Through the contract that already exists: ``POST /experiments/{id}/answers`` with
``confirmed_by_user: true`` and a matching ``If-Match``, applied by
``isaac_records.complete.apply_answers`` under the per-record lock, and recorded
as ``user_confirmation`` evidence. That path is untouched by this slice and is
not imported here. A candidate nobody confirms leaves no trace at all.

WHY A CANDIDATE CARRIES NO ``source_type``
==========================================
Because none of the seven would be true. ``src/isaac_records/models.py``'s
``SOURCE_TYPES`` is closed at ``document``, ``spreadsheet``, ``screenshot``,
``web_form``, ``file_listing``, ``user_confirmation``, ``derivation`` — no member
describes *a person speaking*, and adding an eighth is a truth-core change under
``CLAUDE.md`` §13 that this slice deliberately does not make. A candidate
therefore records its ``origin`` ("transcript" / "typed_note") in its own
vocabulary and stays outside the evidence type system entirely, rather than
borrowing the nearest label and quietly widening what ``document`` means.

CONFIDENCE IS REFUSED, BY THE EXISTING RULE
===========================================
``__post_init__`` runs :func:`.guards.check_candidate_provenance`, which calls
``inferability._confidence_keys_in`` and reads
``inferability.NON_EVIDENCE_SOURCE_TYPES``. No key list is restated here. A
candidate whose ``provenance`` carries ``confidence``, ``probability`` or
``score`` at any depth raises ``UnsupportedSuggestion`` — the truth-plane
exception type, not a local one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar, Protocol, Union, runtime_checkable

from .base import (
    IMPLEMENTATION_DETERMINISTIC_FAKE,
    IMPLEMENTATION_UNCONFIGURED,
    SEAM_CAPTURE_EXTRACTION,
)
from .guards import UnsupportedSuggestion, check_candidate_provenance
from .refusal import (
    REASON_INPUT_NOT_SUPPLIED,
    ProviderRefusal,
    unconfigured_refusal,
)

__all__ = [
    "CANDIDATE_STATUS",
    "ORIGINS",
    "ORIGIN_TRANSCRIPT",
    "ORIGIN_TYPED_NOTE",
    "FORBIDDEN_PROVENANCE_KEYS",
    "ExtractionRequest",
    "FieldCandidate",
    "ExtractionResult",
    "ExtractionOutcome",
    "CaptureExtractionProvider",
    "UnconfiguredCaptureExtractionProvider",
    "DeterministicCaptureExtractionFake",
]

#: The ONLY status a candidate can have. Not a default — a constant returned by a
#: read-only property, so there is no second value to set.
CANDIDATE_STATUS = "needs_confirmation"

ORIGIN_TRANSCRIPT = "transcript"
ORIGIN_TYPED_NOTE = "typed_note"

#: Where the text came from, in this seam's own vocabulary. Deliberately NOT an
#: ISAAC ``source_type``; see the module docstring.
ORIGINS: frozenset[str] = frozenset({ORIGIN_TRANSCRIPT, ORIGIN_TYPED_NOTE})

#: Keys a candidate's free-form ``provenance`` may never carry. Each one would
#: assert, from inside a bag of extra detail, the very thing the class's shape
#: forbids: that this candidate is settled. Refusing them keeps the invariant from
#: being routed around instead of broken.
FORBIDDEN_PROVENANCE_KEYS: frozenset[str] = frozenset(
    {
        "status",
        "verified",
        "evidence",
        "confirmed",
        "confirmed_by_user",
        "accepted",
        "applied",
    }
)


@dataclass(frozen=True)
class ExtractionRequest:
    """Text in, candidates out. ``experiment_id`` is context, never a source."""

    text: str | None = None
    origin: str = ORIGIN_TRANSCRIPT
    #: Which experiment the candidates would be proposed against. Carried so a
    #: caller can route the result; never read to fill a value, because another
    #: record's content is that record's fact (``inferability`` refuses
    #: ``other_record`` for the same reason).
    experiment_id: str | None = None

    def __post_init__(self) -> None:
        if self.origin not in ORIGINS:
            raise ValueError(
                f"unknown origin {self.origin!r}; allowed: {sorted(ORIGINS)}"
            )

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "origin": self.origin,
            "experiment_id": self.experiment_id,
        }


@dataclass(frozen=True, slots=True)
class FieldCandidate:
    """A PROPOSED field value, with the words it came from. Never a value.

    ``slots=True`` is load-bearing, not a micro-optimisation: it removes the
    instance ``__dict__``, which is the last route by which an attribute like
    ``verified`` could be attached after construction.
    """

    #: Dotted path the value would go to. A plain string: this module performs no
    #: schema lookup and makes no claim that the path is valid — the truth plane
    #: decides that, later, on a record a human confirmed.
    field_path: str
    #: The proposed value. Proposed. See every other sentence in this file.
    proposed_value: Any
    #: The words this came from, verbatim, so a human can check the proposal
    #: against what was actually said rather than against a paraphrase.
    quote: str
    #: Where ``quote`` sits in the source text. Offsets must round-trip.
    start_char: int
    end_char: int
    #: One of :data:`ORIGINS`.
    origin: str
    #: The implementation that produced this.
    produced_by: str
    #: The rule that read the quote, stated in full — the sentence, not an id, so
    #: a reader can check the inference without a lookup table (the convention
    #: ``inferability.SuggestionProvenance.rule`` already sets).
    rule: str
    #: Optional extra detail. Screened by :mod:`.guards` and by
    #: :data:`FORBIDDEN_PROVENANCE_KEYS`; replaced with a read-only view.
    #:
    #: `default_factory`, NOT a bare `MappingProxyType({})`, AND THE REASON IS A
    #: PYTHON VERSION DIFFERENCE THAT NO LOCAL RUN CAN SEE.
    #:
    #: `dataclasses` rejects a mutable default by testing
    #: `default.__class__.__hash__ is None`. On CPython 3.11 `mappingproxy` has no
    #: `__hash__`, so that test fires and the class raises `ValueError: mutable
    #: default <class 'mappingproxy'> ... use default_factory` AT DEFINITION TIME.
    #: CPython 3.12 GAVE `mappingproxy` a `__hash__` (it hashes when the underlying
    #: mapping does), so the identical line is accepted there — measured on this
    #: machine: `MappingProxyType({}).__class__.__hash__ is not None` -> True on
    #: 3.12.3.
    #:
    #: So this passed every local run and failed CI on import, taking every test
    #: that reaches `create_app` down with it — the blast radius came from wiring
    #: the boot validator into `create_app`, which put this module on the import
    #: path of the whole application. `pyproject.toml` declares
    #: `requires-python = ">=3.10"`, so 3.11 is squarely supported and the LOCAL
    #: interpreter is the outlier, not CI.
    #:
    #: The empty mapping is still shared and still read-only — `__post_init__`
    #: replaces whatever arrives with a fresh `MappingProxyType`, so the factory
    #: only has to survive class construction.
    provenance: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.field_path:
            raise UnsupportedSuggestion("a candidate must name the field it proposes")
        if self.origin not in ORIGINS:
            raise UnsupportedSuggestion(
                f"{self.field_path}: unknown origin {self.origin!r}"
            )
        if not self.rule:
            raise UnsupportedSuggestion(
                f"{self.field_path}: a candidate must state the rule that produced "
                "it; an unexplained proposal is a guess"
            )
        if not self.quote:
            raise UnsupportedSuggestion(
                f"{self.field_path}: a candidate must quote the words it came from"
            )
        if self.start_char < 0 or self.end_char < self.start_char:
            raise UnsupportedSuggestion(
                f"{self.field_path}: quote offsets must be a non-negative, "
                "ordered span"
            )
        if not isinstance(self.provenance, Mapping):
            raise UnsupportedSuggestion(
                f"{self.field_path}: provenance must be a mapping"
            )
        forbidden = sorted(set(self.provenance) & FORBIDDEN_PROVENANCE_KEYS)
        if forbidden:
            raise UnsupportedSuggestion(
                f"{self.field_path}: provenance carries {forbidden} — a candidate "
                "may not assert its own acceptance from inside a detail bag"
            )
        # The EXISTING no-guessing refusals. Not a second copy: see guards.py.
        check_candidate_provenance(self.field_path, dict(self.provenance))
        object.__setattr__(
            self, "provenance", MappingProxyType(dict(self.provenance))
        )

    # --- the four constants that make "verified" unconstructible -------------

    @property
    def status(self) -> str:
        """Always :data:`CANDIDATE_STATUS`. No setter exists."""
        return CANDIDATE_STATUS

    @property
    def verified(self) -> bool:
        """Always ``False``."""
        return False

    @property
    def is_evidence(self) -> bool:
        """Always ``False``. A quote of speech is not evidence about a record."""
        return False

    @property
    def requires_user_confirmation(self) -> bool:
        """Always ``True``."""
        return True

    def to_dict(self) -> dict:
        """The wire shape — and it repeats the four constants on purpose.

        A consumer reading JSON does not see the class invariant. Serialising
        ``status``/``verified``/``is_evidence``/``requires_user_confirmation``
        means the guarantee survives the boundary instead of stopping at it.
        """
        return {
            "field_path": self.field_path,
            "proposed_value": self.proposed_value,
            "quote": self.quote,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "origin": self.origin,
            "produced_by": self.produced_by,
            "rule": self.rule,
            "provenance": dict(self.provenance),
            "status": self.status,
            "verified": self.verified,
            "is_evidence": self.is_evidence,
            "requires_user_confirmation": self.requires_user_confirmation,
        }


@dataclass(frozen=True)
class ExtractionResult:
    """The candidates from one pass, plus what was deliberately NOT extracted."""

    candidates: tuple[FieldCandidate, ...]
    produced_by: str
    #: Labels the text carried that no rule recognised. Reported rather than
    #: dropped: "the extractor saw a label it will not guess at" is information a
    #: scientist can act on, and silence about it looks like the label was absent.
    unrecognised_labels: tuple[str, ...] = ()

    @property
    def refused(self) -> bool:
        return False

    @property
    def applied(self) -> bool:
        """Always ``False``. Nothing in this package writes anything anywhere."""
        return False

    def to_dict(self) -> dict:
        return {
            "refused": False,
            "applied": False,
            "candidates": [c.to_dict() for c in self.candidates],
            "produced_by": self.produced_by,
            "unrecognised_labels": list(self.unrecognised_labels),
        }


ExtractionOutcome = Union[ExtractionResult, ProviderRefusal]


@runtime_checkable
class CaptureExtractionProvider(Protocol):
    """Text in, candidates out — or a typed refusal. Never applied values."""

    SEAM: ClassVar[str]
    IMPLEMENTATION: ClassVar[str]
    PRODUCTION_CONFIGURED: ClassVar[bool]

    def status_reason(self) -> str: ...

    def extract(self, request: ExtractionRequest) -> ExtractionOutcome: ...


class UnconfiguredCaptureExtractionProvider:
    """The production default. Proposes nothing and says so."""

    SEAM: ClassVar[str] = SEAM_CAPTURE_EXTRACTION
    IMPLEMENTATION: ClassVar[str] = IMPLEMENTATION_UNCONFIGURED
    PRODUCTION_CONFIGURED: ClassVar[bool] = False

    MISSING: ClassVar[tuple[str, ...]] = (
        "an approved model provider (decision D3)",
        "an institutional credential for it (decision D4)",
        "an approved egress and data policy for record text (decisions D6, D8)",
    )

    def status_reason(self) -> str:
        return (
            "No extraction provider is configured. Field values are entered and "
            "confirmed by a person; nothing proposes them."
        )

    def extract(self, request: ExtractionRequest) -> ExtractionOutcome:
        return unconfigured_refusal(
            SEAM_CAPTURE_EXTRACTION,
            missing=self.MISSING,
            what="propose field values from text",
        )


#: ``label: value`` on one line. Anchored, non-greedy on the label, and it will
#: not match a bare sentence — a colon is the whole signal.
_LABELLED = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _/-]{0,40}?)\s*:\s*(\S.*?)\s*$")

#: The test double's ENTIRE vocabulary. A closed table of explicit labels, mapped
#: to dotted paths that exist in this repository's draft field-map space.
#:
#: Fixed and tiny on purpose. A fake that matched fuzzily, scored alternatives, or
#: "understood" a sentence would be a small language model, and its output would
#: stop being checkable by reading this dict. Anything not in this table is
#: reported as unrecognised, never guessed at.
_LABEL_TO_PATH: Mapping[str, str] = MappingProxyType(
    {
        "facility": "system.facility",
        "instrument": "system.instrument",
        "beamline": "system.instrument",
        "technique": "system.technique",
        "sample id": "sample.sample_id",
        "sample form": "sample.sample_form",
        "formula": "sample.material.formula",
    }
)


class DeterministicCaptureExtractionFake:
    """A test double. Pure function of its input: no clock, no randomness, no I/O.

    The rule, in full, is: *for each line of the form* ``label: value`` *whose
    lower-cased label appears in* :data:`_LABEL_TO_PATH`, *propose that value for
    the mapped path, quoting the whole line*. Nothing else is extracted. A line
    with an unrecognised label is reported in ``unrecognised_labels``; a line with
    no colon is ignored entirely.

    Two properties worth stating because they are what make it a *safe* fake:
    it never produces a candidate the input does not literally contain, and it
    never ranks or scores — so there is no confidence number for it to leak.
    """

    SEAM: ClassVar[str] = SEAM_CAPTURE_EXTRACTION
    IMPLEMENTATION: ClassVar[str] = IMPLEMENTATION_DETERMINISTIC_FAKE
    PRODUCTION_CONFIGURED: ClassVar[bool] = False

    def status_reason(self) -> str:
        return (
            "A deterministic test double is selected for the extraction seam. It "
            "matches a closed table of explicit labels and proposes nothing else."
        )

    def extract(self, request: ExtractionRequest) -> ExtractionOutcome:
        text = request.text
        if text is None or not text.strip():
            return ProviderRefusal(
                seam=SEAM_CAPTURE_EXTRACTION,
                reason=REASON_INPUT_NOT_SUPPLIED,
                missing=("text",),
                message=(
                    "The deterministic test double has no text to read. It "
                    "proposes nothing from an empty input rather than returning "
                    "an empty result that looks like a considered answer."
                ),
            )

        candidates: list[FieldCandidate] = []
        unrecognised: list[str] = []
        cursor = 0
        for raw_line in text.split("\n"):
            start = text.index(raw_line, cursor) if raw_line else cursor
            cursor = start + len(raw_line)
            match = _LABELLED.match(raw_line)
            if not match:
                continue
            label, value = match.group(1).strip(), match.group(2).strip()
            path = _LABEL_TO_PATH.get(label.lower())
            if path is None:
                if label.lower() not in unrecognised:
                    unrecognised.append(label.lower())
                continue
            candidates.append(
                FieldCandidate(
                    field_path=path,
                    proposed_value=value,
                    quote=raw_line.strip(),
                    start_char=start,
                    end_char=start + len(raw_line),
                    origin=request.origin,
                    produced_by=IMPLEMENTATION_DETERMINISTIC_FAKE,
                    rule=(
                        f"the line {raw_line.strip()!r} is of the form 'label: "
                        f"value' and the label {label.lower()!r} is mapped to "
                        f"{path} by a closed table; the value is quoted, not "
                        "interpreted"
                    ),
                )
            )
        return ExtractionResult(
            candidates=tuple(candidates),
            produced_by=IMPLEMENTATION_DETERMINISTIC_FAKE,
            unrecognised_labels=tuple(unrecognised),
        )
