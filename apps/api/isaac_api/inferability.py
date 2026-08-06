"""Explicit inferability states + machine-checkable provenance for SUGGESTIONS.

This module is the single place that decides whether the app may put a CONCRETE
value in front of a user that the user did not supply. It is pure, deterministic,
stdlib-only apart from two read-only project reads, and Graphify-free. It decides
nothing about validity or exportability — that stays with ``draft_validator`` /
``official`` / ``export`` (the truth plane), which this module never imports for
any purpose other than the two deterministic derivation rules it wraps.

The contract, in one sentence
----------------------------
A concrete value may exist ONLY under :data:`SUPPORTED_SUGGESTION`, and only with
a :class:`SuggestionProvenance` that names the supporting fields, the applied
rule, whether the inference is unique, why the alternatives were excluded, and
whether user confirmation is still required.

The five states
---------------
``supported_suggestion``   a documented rule fires, uniquely, on evidence THIS
                           record carries. The only state that may carry a value.
``needs_user_input``       the information required to determine the value is not
                           present in the record. A question, never a value.
``ambiguous``              the rule fires but does not single out one answer. The
                           candidates are COUNTED, never offered — picking one
                           would be a guess wearing a rule's clothes.
``contradictory_evidence`` the record's own evidence asserts incompatible values.
                           A human resolves it; this module does not.
``not_inferable``          no rule can reach this field from record content at
                           all (a sha256 of a byte stream we never read, a
                           scientific verdict, a value that lives only in a
                           person's head).

What is NOT evidence
--------------------
:data:`NON_EVIDENCE_SOURCE_TYPES` is a frozen, enumerated refusal list. Each entry
is something that has historically been mistaken for evidence:

* ``model_confidence`` / ``heuristic_confidence`` — a confidence number is a
  statement about a predictor, not about this record. A high one cannot
  manufacture the evidence a low one lacked.
* ``statistical_prior`` / ``commonly_used`` / ``population_default`` — "the value
  most records use" is a fact about other records.
* ``other_record`` — a value found in ANOTHER record is that record's fact.
* ``tutorial_example`` — walkthrough content is authored to be illustrative. It
  is example content for the example record it ships with, never evidence for an
  ordinary record.
* ``schema_default`` / ``schema_enum`` / ``schema_example`` — the schema
  describes the SHAPE a value must have. Knowing a field must be one of three
  enum members does not tell you which one this record's value is. This is the
  "constraint-only" case: :func:`constraint_only` explains the constraint and
  refuses to name the replacement.

Passing any of these as supporting evidence to :func:`supported` raises
:class:`UnsupportedSuggestion` — the guard is a hard failure, not a warning,
because a silently-downgraded suggestion is indistinguishable from a correct one.

Acceptance is not this module's job
-----------------------------------
Nothing here writes, persists, or applies anything. A suggestion becomes a stored
answer only through the existing ``POST /experiments/{id}/answers`` contract:
``confirmed_by_user: true`` plus a matching ``If-Match`` precondition
(``version_contract.precondition_required()`` is ``True``), applied by
``isaac_records.complete.apply_answers`` under the per-record lock, and recorded
as ``user_confirmation`` evidence. A suggestion this module emits and the user
never accepts leaves no trace at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from types import MappingProxyType
from typing import Any, Optional

from isaac_records.draft_validator import OBSERVED_SOURCE_TYPES
from isaac_records.extract.draft_builder import non_oxygen_elements

# --- the five states ----------------------------------------------------------

SUPPORTED_SUGGESTION = "supported_suggestion"
NEEDS_USER_INPUT = "needs_user_input"
AMBIGUOUS = "ambiguous"
CONTRADICTORY_EVIDENCE = "contradictory_evidence"
NOT_INFERABLE = "not_inferable"

#: Every valid state, in display precedence (most-actionable first). Frozen: a
#: consumer that sees a state outside this tuple is looking at a bug.
STATES: tuple[str, ...] = (
    SUPPORTED_SUGGESTION,
    CONTRADICTORY_EVIDENCE,
    AMBIGUOUS,
    NEEDS_USER_INPUT,
    NOT_INFERABLE,
)

#: The ONLY state permitted to carry a concrete value.
_VALUE_BEARING = frozenset({SUPPORTED_SUGGESTION})

#: Source types that are NOT record-specific evidence. See the module docstring —
#: each of these is a reason a suggestion must be refused, not a reason to make one.
NON_EVIDENCE_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "model_confidence",
        "heuristic_confidence",
        "statistical_prior",
        "commonly_used",
        "population_default",
        "other_record",
        "tutorial_example",
        "schema_default",
        "schema_enum",
        "schema_example",
    }
)

#: Evidence keys that, on their own, assert nothing about this record. An entry
#: carrying one of these ANYWHERE IN ITS TREE is refused by :func:`supported`.
#:
#: The depth matters and the first version of this guard got it wrong. It scanned
#: ``set(entry)`` — the top level only — while this repository's own corpus nests
#: exactly this key one level down: ``tests/fixtures/official/
#: operando_xanes_co2rr_record.json`` carries ``"uncertainty": {"confidence":
#: 0.86}``. So the shape the guard was written to refuse was the shape it passed.
_CONFIDENCE_KEYS: frozenset[str] = frozenset({"confidence", "probability", "score"})

#: The evidence source types that DO speak about this record. Mirrors
#: ``draft_validator.OBSERVED_SOURCE_TYPES`` plus ``derivation`` (a documented rule
#: applied to this record's own fields). Deliberately re-stated rather than
#: imported wholesale: this module needs ``derivation`` to count, and the truth
#: plane's tuple must not be widened to make that true.
#:
#: DERIVED, not hand-copied. An earlier revision restated the six observed types
#: as literals, which made this a mirror with nothing holding it up: widening
#: ``OBSERVED_SOURCE_TYPES`` in the truth plane would silently leave this set
#: behind, and every draft using the new type would start raising here — on a
#: READ path. Deriving it means the two can only drift if someone edits this line,
#: and ``test_record_evidence_source_types_is_derived_from_the_truth_plane`` pins
#: the relationship rather than the contents.
RECORD_EVIDENCE_SOURCE_TYPES: frozenset[str] = frozenset(OBSERVED_SOURCE_TYPES) | {
    # A documented rule applied to THIS record's own fields. Deliberately added
    # here and NOT to the truth plane's tuple: `draft_validator` distinguishes
    # observed evidence from a derivation on purpose, and widening its tuple to
    # suit this module would change what `verified` means.
    "derivation",
}


class UnsupportedSuggestion(Exception):
    """A suggestion was constructed that the no-guessing contract forbids.

    Raised — never logged-and-continued — because a suggestion downgraded in
    silence looks exactly like one that was always fine.
    """


# --- provenance ---------------------------------------------------------------


@dataclass(frozen=True)
class SuggestionProvenance:
    """Machine-checkable justification for one supported suggestion.

    Every field is required and every field is checked. ``supporting_fields`` and
    ``rule`` answer "from what, by what rule"; ``unique`` and
    ``alternatives_excluded`` answer "why this answer and not another";
    ``requires_user_confirmation`` answers "may this be treated as settled". A
    provenance that cannot fill all of them is not a provenance.
    """

    #: Dotted official JSON-paths (or ``implicit:``/``meta.`` keys) THIS record
    #: carries that the rule read. Never empty for a supported suggestion.
    supporting_fields: tuple[str, ...]
    #: The evidence entries backing those fields, as ``{source_type, ...}`` dicts.
    supporting_evidence: tuple[dict, ...]
    #: The applied rule, stated in full. Not a rule id — the sentence itself, so a
    #: reader can check the inference without a lookup table.
    rule: str
    #: True iff the rule determines exactly one answer. A supported suggestion
    #: with ``unique=False`` is a contradiction in terms and is refused.
    unique: bool
    #: Why every other candidate was excluded. Empty tuple means "the rule
    #: admitted no other candidate", which is itself an explicit claim.
    alternatives_excluded: tuple[str, ...]
    #: True whenever the value must still be confirmed by a human before it is
    #: stored. Defaults True at every call site in this module.
    requires_user_confirmation: bool

    def to_dict(self) -> dict:
        return {
            "supporting_fields": list(self.supporting_fields),
            "supporting_evidence": [dict(e) for e in self.supporting_evidence],
            "rule": self.rule,
            "unique": self.unique,
            "alternatives_excluded": list(self.alternatives_excluded),
            "requires_user_confirmation": self.requires_user_confirmation,
        }


#: The ONLY ``detail`` keys each state may carry, and the type each must have.
#:
#: An ALLOWLIST, because the denylist it replaces did not work. That version
#: banned four spellings of "value" and accepted everything else, so
#: ``detail={"candidates": ["Cu", "Fe"], "most_likely": "Cu"}`` sailed through on
#: an ``ambiguous`` result — the precise thing `ambiguous` exists to prevent,
#: carried in the field meant to hold counts. Unknown keys are now refused
#: outright, so a future detail key is a deliberate edit here rather than an
#: accident at a call site.
_DETAIL_SCHEMA: dict[str, dict[str, type]] = {
    SUPPORTED_SUGGESTION: {},
    NEEDS_USER_INPUT: {"missing": tuple},
    AMBIGUOUS: {"candidate_count": int},
    CONTRADICTORY_EVIDENCE: {"conflicting_sources": tuple},
    NOT_INFERABLE: {"reason": str, "constraint": str},
}


def _freeze(value: Any) -> Any:
    """Deep-freeze a detail value: lists become tuples, mappings become read-only.

    Without this the immutability is skin deep — ``frozen=True`` stops
    ``x.detail = {...}`` but not ``x.detail["k"] = v``, and a read-only mapping
    alone still leaves ``x.detail["missing"].append("Cu")`` open.
    """
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    return value


@dataclass(frozen=True)
class Inferability:
    """One field's inferability decision.

    Two invariants, both enforced in ``__post_init__``:

    1. ``value is not None`` iff ``state == supported_suggestion``, and a
       supported suggestion always carries a complete, unique provenance.
    2. ``detail`` may carry only the keys :data:`_DETAIL_SCHEMA` allows for that
       state, with the declared type, and is deep-frozen so it cannot be widened
       after construction.

    Honest limit, stated because the first version of this docstring overclaimed:
    (2) closes the structural routes — an unexpected key, a wrong type, and
    post-construction mutation all raise. It does NOT prove no concrete value can
    ever be *encoded inside an allowed key* (a field path in ``missing`` is a
    string, and so is an element symbol). What it guarantees is that every string
    a consumer receives arrived under a key whose meaning is declared here.
    """

    field: str
    state: str
    explanation: str
    value: Any = None
    provenance: Optional[SuggestionProvenance] = None
    #: Extra, non-value detail a UI may render (candidate COUNTS, conflicting
    #: source types, the constraint text). Closed by :data:`_DETAIL_SCHEMA` and
    #: replaced with a deep-frozen view during ``__post_init__``, so the attribute
    #: is a ``MappingProxyType`` by the time anyone outside this class sees it.
    detail: dict = dc_field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise UnsupportedSuggestion(f"unknown inferability state {self.state!r}")
        if not self.explanation:
            raise UnsupportedSuggestion(f"{self.field}: every state must explain itself")
        if self.state in _VALUE_BEARING:
            if self.value is None:
                raise UnsupportedSuggestion(
                    f"{self.field}: {SUPPORTED_SUGGESTION} with no value"
                )
            if self.provenance is None:
                raise UnsupportedSuggestion(
                    f"{self.field}: a concrete value requires provenance"
                )
            if not self.provenance.unique:
                raise UnsupportedSuggestion(
                    f"{self.field}: a non-unique inference is ambiguous, not supported"
                )
            if not self.provenance.rule:
                raise UnsupportedSuggestion(f"{self.field}: provenance names no rule")
            if not self.provenance.supporting_fields:
                raise UnsupportedSuggestion(
                    f"{self.field}: provenance names no supporting field"
                )
        else:
            if self.value is not None:
                raise UnsupportedSuggestion(
                    f"{self.field}: state {self.state!r} may not carry a concrete value"
                )
            if self.provenance is not None:
                raise UnsupportedSuggestion(
                    f"{self.field}: only a supported suggestion carries provenance"
                )
        # `detail` is closed by an allowlist and then frozen. Unknown key, wrong
        # type, or any later mutation attempt: all refused.
        allowed = _DETAIL_SCHEMA[self.state]
        if not isinstance(self.detail, dict):
            raise UnsupportedSuggestion(f"{self.field}: detail must be a mapping")
        for key, raw in self.detail.items():
            if key not in allowed:
                raise UnsupportedSuggestion(
                    f"{self.field}: detail[{key!r}] is not an allowed detail key for "
                    f"state {self.state!r} (allowed: {sorted(allowed) or 'none'}) — an "
                    "unlisted key is how a concrete value gets back in"
                )
            expected = allowed[key]
            frozen = _freeze(raw)
            if expected is tuple:
                if not isinstance(frozen, tuple) or not all(
                    isinstance(v, str) for v in frozen
                ):
                    raise UnsupportedSuggestion(
                        f"{self.field}: detail[{key!r}] must be a sequence of strings"
                    )
            elif expected is int:
                if isinstance(frozen, bool) or not isinstance(frozen, int):
                    raise UnsupportedSuggestion(
                        f"{self.field}: detail[{key!r}] must be an integer count"
                    )
            elif not isinstance(frozen, expected):
                raise UnsupportedSuggestion(
                    f"{self.field}: detail[{key!r}] must be {expected.__name__}"
                )
        # Replace the caller's mutable dict with a deep-frozen view. `frozen=True`
        # blocks rebinding the attribute; this is what blocks writing THROUGH it.
        object.__setattr__(self, "detail", _freeze(dict(self.detail)))

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "state": self.state,
            "explanation": self.explanation,
            "value": self.value,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            # Frozen sequences become lists on the way out: the wire shape is JSON,
            # and the immutability exists to protect the in-process object, not to
            # be exported to a client that gets its own copy anyway.
            "detail": {
                k: (list(v) if isinstance(v, tuple) else v)
                for k, v in self.detail.items()
            },
        }


# --- constructors -------------------------------------------------------------


def _confidence_keys_in(node: Any, _depth: int = 0) -> list[str]:
    """Every confidence-like key anywhere in ``node``'s tree, sorted and deduped.

    Recursive on purpose. The flat ``set(entry)`` check this replaces missed the
    shape the project's own corpus actually writes — ``"uncertainty":
    {"confidence": 0.86}`` in ``operando_xanes_co2rr_record.json`` — so a
    suggestion justified by a nested model score passed a guard named for exactly
    that case. Depth is bounded (evidence entries are small, hand-authored
    mappings) so a pathological structure cannot spin here.
    """
    if _depth > 12:
        return []
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key in _CONFIDENCE_KEYS:
                found.add(key)
            found.update(_confidence_keys_in(value, _depth + 1))
    elif isinstance(node, (list, tuple)):
        for item in node:
            found.update(_confidence_keys_in(item, _depth + 1))
    return sorted(found)


def _check_evidence(field: str, evidence: tuple[dict, ...]) -> None:
    """Refuse evidence that is not about THIS record.

    Three refusals, in order of how often each has been mistaken for evidence:
    a non-record source type, a bare confidence number, and an empty list.
    """
    if not evidence:
        raise UnsupportedSuggestion(f"{field}: a supported suggestion cites no evidence")
    for entry in evidence:
        if not isinstance(entry, dict):
            raise UnsupportedSuggestion(f"{field}: evidence entry is not a mapping")
        source_type = entry.get("source_type")
        if source_type in NON_EVIDENCE_SOURCE_TYPES:
            raise UnsupportedSuggestion(
                f"{field}: {source_type!r} is not record-specific evidence — it "
                "describes a model, a population, another record, or the schema, "
                "never this record"
            )
        if source_type not in RECORD_EVIDENCE_SOURCE_TYPES:
            raise UnsupportedSuggestion(
                f"{field}: unknown evidence source_type {source_type!r}; only "
                f"{sorted(RECORD_EVIDENCE_SOURCE_TYPES)} speak about this record"
            )
        stray = _confidence_keys_in(entry)
        if stray:
            raise UnsupportedSuggestion(
                f"{field}: evidence carries {stray} — a confidence number is a "
                "claim about a predictor, not about this record"
            )
        if source_type == "derivation" and not entry.get("rule"):
            raise UnsupportedSuggestion(
                f"{field}: derivation evidence must state its rule"
            )


def supported(
    field: str,
    value: Any,
    *,
    supporting_fields: tuple[str, ...],
    supporting_evidence: tuple[dict, ...],
    rule: str,
    alternatives_excluded: tuple[str, ...] = (),
    requires_user_confirmation: bool = True,
    explanation: str,
) -> Inferability:
    """A uniquely determined value, with full provenance. The only value path."""
    if value is None:
        raise UnsupportedSuggestion(f"{field}: a supported suggestion needs a value")
    _check_evidence(field, supporting_evidence)
    return Inferability(
        field=field,
        state=SUPPORTED_SUGGESTION,
        explanation=explanation,
        value=value,
        provenance=SuggestionProvenance(
            supporting_fields=tuple(supporting_fields),
            supporting_evidence=tuple(supporting_evidence),
            rule=rule,
            unique=True,
            alternatives_excluded=tuple(alternatives_excluded),
            requires_user_confirmation=requires_user_confirmation,
        ),
    )


def needs_user_input(field: str, explanation: str, *, missing: tuple[str, ...] = ()) -> Inferability:
    """The record does not carry what the rule would need. Ask; never fill."""
    return Inferability(
        field=field,
        state=NEEDS_USER_INPUT,
        explanation=explanation,
        detail={"missing": list(missing)} if missing else {},
    )


def ambiguous(field: str, explanation: str, *, candidate_count: int) -> Inferability:
    """Several answers survive the rule. Count them; never pick one.

    ``candidate_count`` is deliberately a COUNT. Listing the candidates would put
    plausible concrete values on screen next to a "pick one" affordance, which is
    how an ambiguous field becomes a guessed field.
    """
    return Inferability(
        field=field,
        state=AMBIGUOUS,
        explanation=explanation,
        detail={"candidate_count": int(candidate_count)},
    )


def contradictory_evidence(
    field: str, explanation: str, *, conflicting_sources: tuple[str, ...] = ()
) -> Inferability:
    """The record's own evidence disagrees with itself. A human decides."""
    return Inferability(
        field=field,
        state=CONTRADICTORY_EVIDENCE,
        explanation=explanation,
        detail={"conflicting_sources": list(conflicting_sources)}
        if conflicting_sources
        else {},
    )


def not_inferable(field: str, explanation: str, *, reason: str = "") -> Inferability:
    """No rule reaches this field from record content. Say so plainly."""
    return Inferability(
        field=field,
        state=NOT_INFERABLE,
        explanation=explanation,
        detail={"reason": reason} if reason else {},
    )


def constraint_only(field: str, constraint: str) -> Inferability:
    """A constraint is known; the replacement value is NOT.

    The case this exists for: a required field was removed, or a value failed an
    enum. The schema tells us the SHAPE the answer must have — which is a real,
    useful thing to say — and tells us nothing about which answer THIS record's
    was. So the constraint is quoted verbatim into ``detail`` and the state stays
    :data:`NOT_INFERABLE`, where the class invariant makes carrying a replacement
    value impossible rather than merely discouraged.
    """
    return Inferability(
        field=field,
        state=NOT_INFERABLE,
        explanation=(
            "The schema constrains this field but does not determine its value. "
            "The constraint is shown; the replacement is not inferable and must "
            "come from you."
        ),
        detail={"constraint": constraint},
    )


# --- deterministic rules (wrapping the rules that already exist) --------------


def _evidence_of(env) -> tuple[dict, ...]:
    if not isinstance(env, dict):
        return ()
    return tuple(e for e in (env.get("evidence") or []) if isinstance(e, dict))


def absorbing_element(draft: dict) -> Inferability:
    """Wrap the EXISTING absorbing-element rule in the state/provenance model.

    The rule is ``draft_builder``'s and is unchanged: the absorbing element is the
    sole non-oxygen element in ``sample.material.formula``. What is new is that its
    three outcomes are now distinguished instead of collapsing to ``None`` —
    exactly one element is a supported suggestion, several is ``ambiguous``, and
    no parseable element is ``not_inferable``. A formula the record does not carry
    at all is ``needs_user_input``.

    A pre-existing ``implicit['absorbing_element']`` that disagrees with the
    derivation outranks all of it: the record is asserting two different answers,
    which is ``contradictory_evidence``, not a suggestion.
    """
    field = "implicit:absorbing_element"
    fields = draft.get("fields") or {}
    env = fields.get("sample.material.formula")
    formula = env.get("value") if isinstance(env, dict) else None

    if formula in (None, ""):
        return needs_user_input(
            field,
            "The absorbing element is derived from the sample formula, and this "
            "record has no formula. Supply the formula, or the element directly.",
            missing=("sample.material.formula",),
        )

    candidates = non_oxygen_elements(formula)
    if not candidates:
        return not_inferable(
            field,
            "No non-oxygen element symbol could be read from the recorded formula, "
            "so the rule cannot reach an answer. Nothing is proposed.",
            reason="formula_unparseable",
        )
    if len(candidates) > 1:
        return ambiguous(
            field,
            "The recorded formula contains more than one non-oxygen element, so "
            "the rule does not single out an absorber. The candidates are counted, "
            "not offered — choosing between them would be a guess.",
            candidate_count=len(candidates),
        )

    derived = candidates[0]
    for imp in draft.get("implicit") or []:
        if imp.get("about") == "absorbing_element":
            existing = imp.get("value")
            if existing is not None and existing != derived:
                return contradictory_evidence(
                    field,
                    "The record already asserts an absorbing element that the "
                    "formula-derived rule contradicts. Nothing is proposed until a "
                    "human resolves which is right.",
                    conflicting_sources=("implicit:absorbing_element", "sample.material.formula"),
                )

    return supported(
        field,
        derived,
        supporting_fields=("sample.material.formula",),
        supporting_evidence=_evidence_of(env)
        or (
            {
                "source_type": "derivation",
                "rule": "absorbing element = sole non-oxygen element in sample.material.formula",
            },
        ),
        rule=(
            "absorbing element = the sole non-oxygen element symbol in "
            f"sample.material.formula ({formula} -> {derived})"
        ),
        alternatives_excluded=(
            "oxygen is excluded by the rule as the matrix element",
            "no other element symbol appears in the recorded formula",
        ),
        requires_user_confirmation=True,
        explanation=(
            "Uniquely determined by a documented rule from this record's own "
            "formula. It still requires your confirmation before it is stored."
        ),
    )


def system_domain(draft: dict) -> Inferability:
    """Wrap ``draft_builder``'s ``system.domain`` derivation, unchanged.

    ``meta.source_type == "facility"`` implies ``system.domain == "experimental"``
    because the official enum is experimental|computational and a physical
    facility is never computational. Any other source type does not license the
    inference and is refused rather than stretched.
    """
    field = "system.domain"
    meta = draft.get("meta") or {}
    source_type = meta.get("source_type")

    if not source_type:
        return needs_user_input(
            field,
            "The system domain follows from how the record was sourced, and this "
            "record does not record a source type.",
            missing=("meta.source_type",),
        )
    if source_type != "facility":
        return not_inferable(
            field,
            "The documented rule covers facility-sourced records only. This "
            "record's source type does not license the inference, so nothing is "
            "proposed.",
            reason="rule_does_not_apply",
        )
    return supported(
        field,
        "experimental",
        supporting_fields=("meta.source_type",),
        supporting_evidence=(
            {
                "source_type": "derivation",
                "rule": (
                    "system.domain = experimental for a facility-source record "
                    "(meta.source_type=facility => physical experiment, not computation)"
                ),
            },
        ),
        rule=(
            "system.domain = experimental for a facility-source record "
            "(meta.source_type=facility => physical experiment, not computation)"
        ),
        alternatives_excluded=(
            "computational is excluded: a physical facility measurement is not a computation",
        ),
        requires_user_confirmation=True,
        explanation=(
            "Uniquely determined by a documented rule from this record's own "
            "source type. It still requires your confirmation before it is stored."
        ),
    )


def absorption_edge(draft: dict) -> Inferability:
    """The edge is NEVER inferred. It is the canonical constraint-only case.

    ``draft_builder`` already refuses to assert it, recording only the incident-
    energy window. This restates that refusal in the shared vocabulary: knowing
    the window narrows the answer without determining it, so the window is
    reported as context and the value is left to a human.
    """
    field = "implicit:edge"
    return needs_user_input(
        field,
        "The absorption edge cannot be derived from the recorded energy window "
        "without a physics reference this app deliberately does not carry. The "
        "window is shown as context; the edge itself must come from you.",
        missing=("implicit:edge",),
    )


#: The deterministic rule set, in stable output order, each with the field it
#: decides — needed so a rule that REFUSES can still be reported under its own name.
_RULES: tuple[tuple[Any, str], ...] = (
    (absorbing_element, "implicit:absorbing_element"),
    (system_domain, "system.domain"),
    (absorption_edge, "implicit:edge"),
)

#: What a caller is told when a rule refuses to run at all. Deliberately fixed and
#: content-free: the exception message can quote an evidence source type or a
#: field value, and this string is rendered to a user.
_RULE_REFUSED = (
    "This field's derivation rule could not be applied to the evidence this "
    "record carries, so nothing is proposed. The value must come from you."
)


def infer_all(draft: dict) -> list[Inferability]:
    """Every rule's decision for one draft, in a fixed order. Pure; no I/O.

    A rule that raises :class:`UnsupportedSuggestion` DEGRADES to
    ``not_inferable`` rather than propagating. This is not defensive padding — it
    closes a real availability hole. ``_check_evidence`` raises on any evidence
    ``source_type`` outside :data:`RECORD_EVIDENCE_SOURCE_TYPES`, and this
    function is reached from ``GET /pending``, ``POST /answers`` and
    ``POST /edit``. A draft whose formula evidence carried an unlisted type would
    have turned a READ into a 500 — and the refusal is not even a caller error:
    the honest answer to "can you infer this?" for evidence the rule set does not
    understand is *no*, which is a state this vocabulary already has.

    Degrading is safe precisely because the fallback is the most conservative
    state. It can only ever remove a suggestion, never manufacture one.
    """
    out: list[Inferability] = []
    for rule, field_name in _RULES:
        try:
            out.append(rule(draft or {}))
        except UnsupportedSuggestion:
            out.append(not_inferable(field_name, _RULE_REFUSED, reason="rule_refused"))
    return out


# --- completion blockers ------------------------------------------------------

#: Why each open blocker kind cannot be answered by the app. These are refusals,
#: and each names the specific reason rather than a generic "unknown".
_BLOCKER_REFUSALS: dict[str, tuple[str, str]] = {
    "asset": (
        NOT_INFERABLE,
        "A sha256 is a digest of file bytes this app never reads. No amount of "
        "metadata determines it, so none is proposed — paste the digest you "
        "computed.",
    ),
    "series": (
        NEEDS_USER_INPUT,
        "The reduced spectrum's data points exist only in the reduction product. "
        "The record names the file but does not contain its values, so the series "
        "must come from you.",
    ),
    "qc": (
        NOT_INFERABLE,
        "A QC verdict is a scientific judgement about this measurement. There is "
        "no default and none is assumed — not even 'valid'.",
    ),
    "descriptor": (
        NEEDS_USER_INPUT,
        "A descriptor value and its uncertainty are measured or computed results. "
        "The record carries neither, so nothing is proposed.",
    ),
}

_BLOCKER_FALLBACK = (
    NOT_INFERABLE,
    "This blocker has no documented derivation rule, so no value is proposed.",
)

#: Appended when an example answer is available for a walkthrough record. It is
#: stated in the SAME breath as the refusal, so the two can never drift apart.
EXAMPLE_NOT_EVIDENCE = (
    " An example answer ships with this walkthrough record; it is illustrative "
    "content, not evidence about this record, and only your confirmation can "
    "enter it."
)


def blocker_inferability(entry: dict, *, example_available: bool = False) -> Inferability:
    """The inferability decision for one open ``pending[]`` blocker.

    Every blocker kind resolves to a refusal — which is the correct answer, not a
    gap in the rule set. ``example_available`` only ever CHANGES THE EXPLANATION;
    it can never produce a value or promote the state, because a walkthrough
    fixture is not evidence about a record.
    """
    kind = entry.get("kind")
    state, explanation = _BLOCKER_REFUSALS.get(kind, _BLOCKER_FALLBACK)
    if example_available:
        explanation += EXAMPLE_NOT_EVIDENCE
    field = entry.get("uri") or entry.get("blocker") or kind or "blocker"

    # Dispatch on the table's OWN state rather than defaulting anything that is
    # not NEEDS_USER_INPUT to a refusal. The earlier form did the latter, which
    # made the state column unable to lie — but also unable to be checked: an
    # editor who promoted an entry to `supported_suggestion` got a silent refusal
    # instead of an error, so the table and the behaviour could disagree with
    # nothing noticing. Raising is the honest response to a table that asks for a
    # value here: no blocker has a rule that could produce one.
    if state == NEEDS_USER_INPUT:
        return needs_user_input(str(field), explanation)
    if state == NOT_INFERABLE:
        return not_inferable(str(field), explanation, reason=f"blocker:{kind}")
    raise UnsupportedSuggestion(
        f"blocker kind {kind!r} declares state {state!r}; an open blocker has no "
        "derivation rule, so it may only resolve to needs_user_input or not_inferable"
    )


__all__ = [
    "SUPPORTED_SUGGESTION",
    "NEEDS_USER_INPUT",
    "AMBIGUOUS",
    "CONTRADICTORY_EVIDENCE",
    "NOT_INFERABLE",
    "STATES",
    "NON_EVIDENCE_SOURCE_TYPES",
    "RECORD_EVIDENCE_SOURCE_TYPES",
    "EXAMPLE_NOT_EVIDENCE",
    "UnsupportedSuggestion",
    "SuggestionProvenance",
    "Inferability",
    "supported",
    "needs_user_input",
    "ambiguous",
    "contradictory_evidence",
    "not_inferable",
    "constraint_only",
    "absorbing_element",
    "system_domain",
    "absorption_edge",
    "infer_all",
    "blocker_inferability",
]
