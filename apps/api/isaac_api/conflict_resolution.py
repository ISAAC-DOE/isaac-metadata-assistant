"""CONFLICT RESOLUTION — a recorded human decision that supersedes without removing.

THE DEFECT THIS MODULE EXISTS TO FIX
====================================

``submissions.py`` already writes the defect down in prose, and until this module
existed that prose had nowhere to point:

    ``evidence_classify._classify_entry`` rule 1 flags an entry the moment two
    distinct non-null answers are recorded for it. ``routes._apply_run_field`` and
    ``complete.apply_answers`` / ``apply_corrections`` **append** a
    ``user_confirmation`` entry every time and never replace one, and no route in
    this application removes an evidence entry. So a scientist who answers a
    question, notices a typo, and answers it again has manufactured a conflict
    **they cannot clear through any surface this build offers.**

That is the motivating case, and it is an ordinary one: correcting a mistake
produced a permanent finding. This module gives a person a way to say which of the
competing answers is the right one, in a form that is auditable and that does not
require deleting anything.

WHAT A RESOLUTION IS, AND WHAT IT IS NOT
========================================

A :class:`ConflictResolution` is a **recorded decision about an evidence conflict**.
It is not a value, not an evidence entry, and not a correction of the record's
content.

* **It removes nothing.** ``submissions.py`` states as a property of this
  application that "no route in this application removes an evidence entry", and
  this module keeps that true: it writes a decision *beside* the evidence and never
  touches the evidence list. ``test_conflict_resolution.py`` captures the whole
  evidence payload before and after a resolution and asserts byte equality.
* **It picks no winner by itself.** Nothing here inspects the competing values and
  selects one. Every :attr:`ConflictResolution.chosen_value` arrives from an
  explicit request that carried ``confirmed_by_user: true``; the model refuses a
  ``resolved`` outcome with no value at all, so "the system resolved it" is not a
  state that can be constructed.
* **It does not become the field's value.** See
  :func:`~isaac_api.routes.post_conflict_resolution` — recording *which* competing
  value a scientist chose and *writing* that value into the field are two different
  acts, and the second one already has exactly one path (a confirmed answer/edit,
  recorded as ``user_confirmation`` evidence). Wiring a resolution into that path
  would create a second way for scientific content to change, which is a decision
  for a later slice rather than an assumption for this one.
* **``deferred`` is a first-class outcome**, in the same sense ``notes.NOTE_KEPT``
  is: a person can look at a conflict and decline to decide, and recording that is
  worth more than an empty queue row. It does **not** clear the conflict.

WHERE A RESOLUTION IS STORED, AND WHY NOT IN THE ENVELOPE
=========================================================

In the draft, under the top-level key :data:`DRAFT_KEY`, as a list.

**Not inside the field envelope.** ``serialize.evidence_trail_from_draft`` reads
each envelope's ``value`` / ``status`` / ``evidence`` and *every* view in this
application is built on the shape it returns; adding a key inside an envelope risks
changing a trail entry's shape for three surfaces that never asked for it. A
top-level assistant-only key is what ``CLAUDE.md`` §4 already permits a draft to
carry, and it is inert to everything that reads a draft: ``export.transform`` reads
only the keys it names (``meta``, ``fields``, ``series``, ``qc``, ``assets``,
``descriptors_outputs``, ``links``, ``attribution``, ``tags``), so no exported
official record can carry it — pinned by test rather than asserted here.

**One list at the RECORD level, including run-scoped decisions**, distinguished by
:attr:`ConflictResolution.run_id`. Two consequences a reader should know rather than
discover:

* A run-scoped resolution rewrites the RECORD's document, exactly as a note
  attached to a run does, so the precondition for writing one is the record's
  ``If-Match`` and not the run's.
* ``workspace.resolved_run_draft`` composes a run's export draft from the run's own
  draft plus resolved experiment-level addresses, and it does **not** copy this key,
  so a run's export unit never carries resolutions. A ZERO-RUN experiment's export
  unit *is* ``exp.draft`` itself, so for that shape the key does travel into
  ``submissions.content_signature`` — which means recording a resolution changes the
  content signature and a later submission records a new revision. That is disclosed
  rather than engineered around: a recorded decision **is** a change to the state of
  the record, and excluding it would require editing the submission write path to
  serve a read feature.

STALENESS IS THE CORRECTNESS PROPERTY THAT MATTERS
==================================================

A decision is about a *specific set of competing answers*. If a third answer
arrives afterwards, the decision no longer covers the conflict a reader is looking
at, and continuing to display the address as resolved would be a false statement
about a live disagreement.

So every resolution stores :attr:`ConflictResolution.competing_values` — the exact
set of competing answers at the moment of the decision, canonicalised by the SAME
function ``evidence_classify`` uses to decide a conflict exists — plus
:attr:`competing_digest` over them. :func:`state_of` compares that digest against
the address's *current* competing set: a mismatch is :data:`RESOLUTION_STALE`, the
address returns to ``conflict``, and the superseded decision is neither deleted nor
hidden.

FOUR DERIVED STATES, AND WHY STALENESS IS NOT MODELLED FOR ``deferred``
=======================================================================

:data:`RESOLUTION_STATES` is ``absent`` / ``current`` / ``stale`` / ``deferred``.
A deferred decision is reported as ``deferred`` whether or not the competing set has
moved on, and that asymmetry is deliberate: staleness exists to stop a resolved
decision from silently covering a conflict it was never about, and a deferred
decision covers nothing in the first place — it leaves the address conflicting
either way, so a ``deferred_stale`` member would be a distinction with no consumer
and one more state every surface has to branch on.

Pure functions and frozen dataclasses only. No I/O, no clock, no id minting, no
environment read — the caller supplies ``at`` / ``resolution_id`` / the actor exactly
as ``notes.py`` requires, so this module is testable without a workspace.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from . import evidence_classify
from . import serialize
from . import submissions

__all__ = [
    "ACTION_RECORD",
    "ACTION_REVISE",
    "CHOSEN_FROM_CANDIDATE",
    "CHOSEN_FROM_EDITED",
    "CHOSEN_FROM_VALUES",
    "ConflictResolution",
    "DRAFT_KEY",
    "OUTCOME_DEFERRED",
    "OUTCOME_RESOLVED",
    "RESOLUTION_ABSENT",
    "RESOLUTION_ACTIONS",
    "RESOLUTION_CURRENT",
    "RESOLUTION_DEFERRED",
    "RESOLUTION_OUTCOMES",
    "RESOLUTION_STALE",
    "RESOLUTION_STATES",
    "ResolutionTransition",
    "UnsupportedResolution",
    "competing_digest",
    "competing_from_evidence",
    "conflict_report",
    "find",
    "new_resolution",
    "resolution_states",
    "resolution_view",
    "resolutions_from_draft",
    "revise_resolution",
    "state_of",
    "write_resolution",
]


#: The draft's top-level key. See the module docstring for why it is not in the
#: field envelope and why one record-level list holds run-scoped decisions too.
DRAFT_KEY = "conflict_resolutions"

#: A person decided which of the competing answers is the right one.
OUTCOME_RESOLVED = "resolved"
#: A person LOOKED and declined to decide. A first-class outcome, and it does NOT
#: clear the conflict — see the module docstring.
OUTCOME_DEFERRED = "deferred"

RESOLUTION_OUTCOMES: tuple[str, ...] = (OUTCOME_RESOLVED, OUTCOME_DEFERRED)

#: The chosen value is one of the competing answers already recorded on the entry.
CHOSEN_FROM_CANDIDATE = "candidate"
#: The chosen value is a NEW value the scientist typed, which was none of the
#: competing answers. Kept distinct from :data:`CHOSEN_FROM_CANDIDATE` because
#: "I picked the second citation" and "all the citations are wrong and the value is
#: this" are different claims, and collapsing them would lose the second one.
CHOSEN_FROM_EDITED = "edited"

CHOSEN_FROM_VALUES: tuple[str, ...] = (CHOSEN_FROM_CANDIDATE, CHOSEN_FROM_EDITED)

#: The first act in every resolution's history.
ACTION_RECORD = "record"
#: A later act that changes the decision. It APPENDS; the superseded value and the
#: competing set it was decided over are kept on the transition.
ACTION_REVISE = "revise"

RESOLUTION_ACTIONS: tuple[str, ...] = (ACTION_RECORD, ACTION_REVISE)

#: Nobody has recorded a decision about this address.
RESOLUTION_ABSENT = "absent"
#: A ``resolved`` decision whose competing set still matches the address's current
#: one. The ONLY state that clears a conflict.
RESOLUTION_CURRENT = "current"
#: A ``resolved`` decision made over a DIFFERENT competing set — new competing
#: evidence has arrived since. The address is conflicting again; the decision is
#: kept and disclosed, never deleted.
RESOLUTION_STALE = "stale"
#: A ``deferred`` decision. Reported whether or not the competing set has moved on;
#: see the module docstring for why.
RESOLUTION_DEFERRED = "deferred"

RESOLUTION_STATES: tuple[str, ...] = (
    RESOLUTION_ABSENT,
    RESOLUTION_CURRENT,
    RESOLUTION_STALE,
    RESOLUTION_DEFERRED,
)

#: What a conflict is, echoed into every report so a reader never has to infer the
#: scope of the word from its name. Mirrors ``submissions.CONFLICT_SCOPE``'s purpose.
CONFLICT_SCOPE = "one_entry_evidence_answers"

#: The classification :mod:`isaac_api.evidence_classify` produces for a conflict.
#: Read from there rather than spelled out, exactly as ``provenance`` does, so there
#: is ONE definition of "conflicting" in this application.
CONFLICT_CLASSIFICATION = "conflicting_evidence"


class UnsupportedResolution(ValueError):
    """A resolution that cannot be constructed without inventing something."""


def _clean_optional(value: object, label: str) -> str | None:
    """``None`` or a non-blank string. A blank is REFUSED, never coerced to ``None``.

    ``notes._clean_optional``'s rule, for ``notes._clean_optional``'s reason: ``None``
    means "nobody supplied this" and ``""`` means a caller supplied something empty
    and expects it to have been stored. Folding the second into the first is a silent
    discard of a decision.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise UnsupportedResolution(
            f"{label} must be a string or absent, not {type(value).__name__}"
        )
    if not value.strip():
        raise UnsupportedResolution(
            f"{label} was supplied as blank. Absent is a meaning here — omit it "
            "rather than sending an empty string, which would be stored as though "
            "somebody had written something."
        )
    return value


def _recognised_trust_bases() -> frozenset[str]:
    """``identity.RECOGNISED_TRUST_BASES``, read lazily.

    Lazily so this domain module carries no import of the HTTP layer at module load
    (``identity`` imports ``fastapi``), and READ rather than transcribed so a basis
    added there cannot leave a stale literal here — the mistake
    ``submissions.TRUST_BASIS_UNATTRIBUTED``'s own docstring is written to prevent
    from the other direction.
    """
    from . import identity  # noqa: PLC0415 - see the docstring

    return identity.RECOGNISED_TRUST_BASES


def competing_digest(values: Sequence[str]) -> str:
    """The sha256 identity of one competing-answer SET.

    Over ``sorted(set(values))`` so the digest is a property of the set and not of
    the order the evidence happens to be stored in — which is exactly the property
    ``evidence_classify._asserted_values`` already provides by sorting, restated here
    because this digest is the staleness comparison and must not move for a reason
    that is not a change of content.

    ``submissions.canonical_json`` is USED rather than reimplemented: it is this
    application's one deterministic JSON text form, and a second copy is how two
    digests of the same content come to disagree.
    """
    ordered = sorted({str(value) for value in values})
    payload = {"scope": CONFLICT_SCOPE, "competing_values": ordered}
    return hashlib.sha256(
        submissions.canonical_json(payload).encode("utf-8")
    ).hexdigest()


def competing_from_evidence(evidence: object) -> tuple[str, ...]:
    """The distinct non-null asserted answers on ONE entry, canonicalised and sorted.

    DELEGATED to ``evidence_classify.asserted_values``, which is the function whose
    output length decides that a conflict exists. Recomputing the canonicalisation
    here would let a resolution be recorded over a set the conflict rule does not
    agree with — the two would disagree about what "the same value" means, and the
    disagreement would surface as a resolution that never clears anything.
    """
    return tuple(
        evidence_classify.asserted_values(evidence if isinstance(evidence, list) else [])
    )


@dataclass(frozen=True, slots=True)
class ResolutionTransition:
    """ONE act in a resolution's life, appended and never rewritten.

    ``notes.NoteTransition``'s shape and its naming constraint: a ``slots=True``
    dataclass cannot carry a method whose name collides with a field, and
    ``from_outcome`` / ``to_outcome`` are the names a reader of a stored audit row
    needs, so the serialisers are ``to_state_dict`` / ``from_state_dict``.
    """

    action: str
    at: str
    #: The outcome before this act. ``None`` only for :data:`ACTION_RECORD`.
    from_outcome: str | None
    to_outcome: str
    #: For :data:`ACTION_REVISE`: the value this act superseded, so no decision is
    #: lost. ``None`` is AMBIGUOUS on its own — a revision away from ``deferred``
    #: genuinely superseded no value — and ``from_outcome`` is what disambiguates
    #: it: ``deferred`` means there was nothing to supersede.
    superseded_chosen_value: Any = None
    #: For :data:`ACTION_REVISE`: the competing set the SUPERSEDED decision was made
    #: over. Kept because the resolution itself only carries the CURRENT set, so
    #: without this the history would say a decision changed and lose what it was a
    #: decision about — which is the whole basis of the staleness check.
    superseded_competing_digest: str | None = None

    def __post_init__(self) -> None:
        if self.action not in RESOLUTION_ACTIONS:
            raise UnsupportedResolution(f"unknown resolution action {self.action!r}")
        if self.to_outcome not in RESOLUTION_OUTCOMES:
            raise UnsupportedResolution(f"unknown outcome {self.to_outcome!r}")
        if self.from_outcome is not None and self.from_outcome not in RESOLUTION_OUTCOMES:
            raise UnsupportedResolution(f"unknown prior outcome {self.from_outcome!r}")
        if self.action == ACTION_RECORD and self.from_outcome is not None:
            raise UnsupportedResolution(
                "the opening act of a resolution has no prior outcome; naming one "
                "would claim a decision that was never recorded"
            )
        if self.action == ACTION_REVISE and self.from_outcome is None:
            raise UnsupportedResolution(
                "a revision must name the outcome it moved from, or the history "
                "cannot say what changed"
            )
        if not self.at:
            raise UnsupportedResolution("a transition must record when it happened")

    def to_state_dict(self) -> dict:
        return {
            "action": self.action,
            "at": self.at,
            "from_outcome": self.from_outcome,
            "to_outcome": self.to_outcome,
            "superseded_chosen_value": self.superseded_chosen_value,
            "superseded_competing_digest": self.superseded_competing_digest,
        }

    @classmethod
    def from_state_dict(cls, state: dict) -> "ResolutionTransition":
        return cls(
            action=state.get("action"),  # type: ignore[arg-type]
            at=state.get("at"),  # type: ignore[arg-type]
            from_outcome=state.get("from_outcome"),
            to_outcome=state.get("to_outcome"),  # type: ignore[arg-type]
            superseded_chosen_value=state.get("superseded_chosen_value"),
            superseded_competing_digest=state.get("superseded_competing_digest"),
        )


@dataclass(frozen=True, slots=True)
class ConflictResolution:
    """One recorded decision about one address's conflicting evidence.

    Frozen and slotted for ``notes.Note``'s reason: there is no instance ``__dict__``
    to attach a later ``applied`` / ``authoritative`` / ``verified`` flag to, so a
    resolution cannot grow into something that presents as a confirmed field value.
    """

    resolution_id: str
    #: The trail address this decision is about: a dotted field path,
    #: ``implicit:<about>``, or ``assets:<id>`` — whatever
    #: ``serialize.evidence_trail_from_draft`` calls it. Never a schema path this
    #: module invents.
    address: str
    outcome: str
    #: The competing answers AT THE MOMENT OF THE DECISION, canonicalised exactly as
    #: ``evidence_classify`` canonicalises them, distinct and sorted. At least two —
    #: a "resolution" over fewer describes a conflict that does not exist.
    competing_values: tuple[str, ...]
    competing_digest: str
    recorded_utc: str
    #: The actor seam. ``unattributed`` whenever nobody was established, and this
    #: build establishes nobody by default: no shipped verifier reads a request, so
    #: an arriving edge identity header is worth nothing here (the guard in
    #: test_identity_trust.py is a blunt text scan, so this comment deliberately
    #: does not spell the header name out -- see identity.py, the one module that may).
    trust_basis: str
    #: The run this decision belongs to, or ``None`` for the experiment's own draft.
    #: Never inferred from "the only run that happens to exist" — ``notes.Note``'s
    #: rule, for ``notes.Note``'s reason.
    run_id: str | None = None
    #: What the SCIENTIST selected or typed. ``None`` only for
    #: :data:`OUTCOME_DEFERRED`, which carries no choice at all.
    chosen_value: Any = None
    chosen_from: str | None = None
    #: Free text the scientist supplied, or ``None``. Never composed on their behalf.
    rationale: str | None = None
    #: The canonical Authentik username when a trusted boundary established one, and
    #: ``None`` otherwise. An unattributed row names nobody; an attributed row names
    #: somebody. Both halves are enforced below.
    subject: str | None = None
    #: Append-only. Opens with an :data:`ACTION_RECORD` entry.
    history: tuple[ResolutionTransition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_id, str) or not self.resolution_id:
            raise UnsupportedResolution(
                "a resolution must have an id; an unaddressable decision cannot be "
                "revised or cited"
            )
        if not isinstance(self.address, str) or not self.address.strip():
            raise UnsupportedResolution(
                "a resolution must name the trail address it is about"
            )
        if self.outcome not in RESOLUTION_OUTCOMES:
            raise UnsupportedResolution(
                f"unknown outcome {self.outcome!r}; allowed: {list(RESOLUTION_OUTCOMES)}"
            )
        if not self.recorded_utc:
            raise UnsupportedResolution("a resolution must record when it was made")
        object.__setattr__(self, "run_id", _clean_optional(self.run_id, "run_id"))
        object.__setattr__(self, "rationale", _clean_optional(self.rationale, "rationale"))

        if not isinstance(self.competing_values, tuple) or any(
            not isinstance(value, str) for value in self.competing_values
        ):
            raise UnsupportedResolution(
                "competing_values must be a tuple of canonicalised answer strings"
            )
        if len(self.competing_values) < 2:
            raise UnsupportedResolution(
                "a resolution needs at least two competing answers. Fewer is not a "
                "conflict, and recording a decision about one would assert that a "
                "disagreement existed."
            )
        if tuple(sorted(set(self.competing_values))) != self.competing_values:
            raise UnsupportedResolution(
                "competing_values must be distinct and sorted, exactly as "
                "evidence_classify produces them; any other order would give the "
                "same set two digests"
            )
        expected = competing_digest(self.competing_values)
        if self.competing_digest != expected:
            # A stored digest that disagrees with its own values is worse than a
            # missing one: the staleness check would compare against a set nobody
            # recorded. Refused rather than recomputed, so a hand-edited document is
            # reported as unreadable instead of silently re-blessed.
            raise UnsupportedResolution(
                "competing_digest does not match competing_values, so this "
                "resolution's staleness could not be judged against the set it "
                "claims to have been decided over"
            )

        if self.outcome == OUTCOME_RESOLVED:
            if self.chosen_value is None:
                raise UnsupportedResolution(
                    "a resolved conflict must record the value the scientist chose. "
                    "Nothing here picks one, so a resolution with no value would "
                    "claim a decision nobody made."
                )
            if self.chosen_from not in CHOSEN_FROM_VALUES:
                raise UnsupportedResolution(
                    f"chosen_from must be one of {list(CHOSEN_FROM_VALUES)}; it says "
                    "whether the scientist picked one of the recorded answers or "
                    "typed a new one, and the two are different claims"
                )
            if (
                self.chosen_from == CHOSEN_FROM_CANDIDATE
                and evidence_classify.canonical_answer(self.chosen_value)
                not in self.competing_values
            ):
                raise UnsupportedResolution(
                    "chosen_from is `candidate`, but the chosen value is not one of "
                    "the competing answers. A value that was never asserted is an "
                    "`edited` decision, and labelling it `candidate` would attribute "
                    "it to a citation that does not carry it."
                )
        else:
            # DEFERRED CARRIES NO CHOICE, IN EITHER FIELD. "A person looked and did
            # not decide" and "a person decided but we filed it as undecided" are
            # different facts, and a record that could hold both would make the
            # outcome unreadable.
            if self.chosen_value is not None:
                raise UnsupportedResolution(
                    "a deferred decision records that nobody chose. Supplying a "
                    "chosen value would store a choice under an outcome that says "
                    "none was made."
                )
            if self.chosen_from is not None:
                raise UnsupportedResolution(
                    "a deferred decision has nothing to have chosen from"
                )

        if self.trust_basis == submissions.TRUST_BASIS_UNATTRIBUTED:
            if self.subject is not None:
                raise UnsupportedResolution(
                    "an unattributed resolution must name nobody. A subject beside "
                    "`unattributed` is a name nothing vouched for."
                )
        elif self.trust_basis in _recognised_trust_bases():
            if not isinstance(self.subject, str) or not self.subject.strip():
                raise UnsupportedResolution(
                    "an attributed resolution must name somebody; a recognised trust "
                    "basis with no subject claims a verification of nobody"
                )
        else:
            raise UnsupportedResolution(
                f"unknown trust basis {self.trust_basis!r}; allowed: "
                f"{sorted({submissions.TRUST_BASIS_UNATTRIBUTED} | _recognised_trust_bases())}"
            )

        if not isinstance(self.history, tuple) or any(
            not isinstance(entry, ResolutionTransition) for entry in self.history
        ):
            raise UnsupportedResolution(
                "a resolution's history must be a tuple of transitions"
            )

    # --- constants that make "an applied value" unconstructible ---------------

    @property
    def is_field_value(self) -> bool:
        """Always ``False``. A resolution records a choice; it writes no field."""
        return False

    @property
    def is_evidence(self) -> bool:
        """Always ``False``. A decision about citations is not itself a citation."""
        return False

    @property
    def attributed(self) -> bool:
        return self.trust_basis != submissions.TRUST_BASIS_UNATTRIBUTED

    def to_state(self) -> dict:
        """The persistence AND wire shape, the two constants included.

        ``is_field_value`` / ``is_evidence`` are serialised for ``notes.Note``'s
        reason: a consumer reading JSON does not see the class invariant, so the
        guarantee has to cross the boundary rather than stop at it.
        """
        return {
            "resolution_id": self.resolution_id,
            "address": self.address,
            "run_id": self.run_id,
            "outcome": self.outcome,
            "chosen_value": self.chosen_value,
            "chosen_from": self.chosen_from,
            "competing_values": list(self.competing_values),
            "competing_digest": self.competing_digest,
            "rationale": self.rationale,
            "subject": self.subject,
            "trust_basis": self.trust_basis,
            "recorded_utc": self.recorded_utc,
            "history": [entry.to_state_dict() for entry in self.history],
            "is_field_value": self.is_field_value,
            "is_evidence": self.is_evidence,
        }

    @classmethod
    def from_state(cls, state: dict) -> "ConflictResolution":
        """Rehydrate one resolution. RAISES on a document it cannot represent.

        Deliberately like ``notes.Note.from_state`` and unlike ``Run.from_state``: a
        run coerced to a default is still the same run, while a decision whose
        outcome, chosen value or competing set cannot be read is a decision this
        module would have to invent something about.

        Raising is safe because the ONLY caller is :func:`resolutions_from_draft`,
        which catches it and PRESERVES the raw entry verbatim — nothing is lost, and
        the count of what could not be read is disclosed beside what could.
        """
        competing = state.get("competing_values")
        history = state.get("history")
        return cls(
            resolution_id=state.get("resolution_id"),  # type: ignore[arg-type]
            address=state.get("address"),  # type: ignore[arg-type]
            outcome=state.get("outcome"),  # type: ignore[arg-type]
            competing_values=(
                tuple(competing) if isinstance(competing, list) else competing  # type: ignore[arg-type]
            ),
            competing_digest=state.get("competing_digest"),  # type: ignore[arg-type]
            recorded_utc=state.get("recorded_utc"),  # type: ignore[arg-type]
            trust_basis=state.get("trust_basis"),  # type: ignore[arg-type]
            run_id=state.get("run_id"),
            chosen_value=state.get("chosen_value"),
            chosen_from=state.get("chosen_from"),
            rationale=state.get("rationale"),
            subject=state.get("subject"),
            history=tuple(
                ResolutionTransition.from_state_dict(entry)
                for entry in (history if isinstance(history, list) else [])
                if isinstance(entry, dict)
            ),
        )


def new_resolution(
    *,
    resolution_id: str,
    address: str,
    outcome: str,
    competing_values: Sequence[str],
    recorded_utc: str,
    trust_basis: str,
    run_id: str | None = None,
    chosen_value: Any = None,
    chosen_from: str | None = None,
    rationale: str | None = None,
    subject: str | None = None,
) -> ConflictResolution:
    """Mint a resolution with its opening :data:`ACTION_RECORD` entry already in it.

    The id is supplied by the caller rather than minted here so this module stays
    free of the truth core's id package — ``notes.new_note``'s arrangement, and for
    the same reason. A RESOLUTION ID IS NOT A RECORD ID: it names no exported
    artifact and never will.

    ``chosen_value`` is DEEP-COPIED. ``workspace.set_run_override`` makes the same
    copy for the same reason: a stored reference to a live envelope would let a later
    in-place edit rewrite what a scientist decided, and this record's whole value is
    that it says what they decided at the time.
    """
    values = tuple(sorted({str(value) for value in competing_values}))
    return ConflictResolution(
        resolution_id=resolution_id,
        address=address,
        outcome=outcome,
        competing_values=values,
        competing_digest=competing_digest(values),
        recorded_utc=recorded_utc,
        trust_basis=trust_basis,
        run_id=run_id,
        chosen_value=copy.deepcopy(chosen_value),
        chosen_from=chosen_from,
        rationale=rationale,
        subject=subject,
        history=(
            ResolutionTransition(
                action=ACTION_RECORD,
                at=recorded_utc,
                from_outcome=None,
                to_outcome=outcome,
            ),
        ),
    )


def revise_resolution(
    existing: ConflictResolution,
    *,
    at: str,
    outcome: str,
    competing_values: Sequence[str],
    chosen_value: Any = None,
    chosen_from: str | None = None,
    rationale: str | None = None,
    subject: str | None = None,
    trust_basis: str | None = None,
) -> ConflictResolution:
    """Change a recorded decision, APPENDING to its history. Never overwrites silently.

    The superseded value and the competing digest it was decided over are kept on the
    appended :data:`ACTION_REVISE` transition, so every version of the decision stays
    recoverable rather than only the first and the last.

    ``recorded_utc`` and ``resolution_id`` are NOT changed: they are the identity of
    the decision, and the history says when each act happened.

    IDEMPOTENT. A re-submission that changes nothing — same outcome, same value, same
    ``chosen_from``, same rationale, and the same competing set — returns the existing
    object, so a double-click adds no audit row and does not advance the record's
    revision. It deliberately does NOT compare ``subject``/``trust_basis``: whether
    this deployment could attribute the caller is not a change to the decision, and
    letting it manufacture a revision would make the audit trail a log of
    configuration rather than of decisions.
    """
    values = tuple(sorted({str(value) for value in competing_values}))
    digest = competing_digest(values)
    unchanged = (
        outcome == existing.outcome
        and chosen_value == existing.chosen_value
        and chosen_from == existing.chosen_from
        and _clean_optional(rationale, "rationale") == existing.rationale
        and digest == existing.competing_digest
    )
    if unchanged:
        return existing
    return dataclasses.replace(
        existing,
        outcome=outcome,
        competing_values=values,
        competing_digest=digest,
        chosen_value=copy.deepcopy(chosen_value),
        chosen_from=chosen_from,
        rationale=rationale,
        subject=subject if trust_basis is not None else existing.subject,
        trust_basis=trust_basis if trust_basis is not None else existing.trust_basis,
        history=(
            *existing.history,
            ResolutionTransition(
                action=ACTION_REVISE,
                at=at,
                from_outcome=existing.outcome,
                to_outcome=outcome,
                superseded_chosen_value=copy.deepcopy(existing.chosen_value),
                superseded_competing_digest=existing.competing_digest,
            ),
        ),
    )


def state_of(
    resolution: ConflictResolution | None, current_values: Sequence[str]
) -> str:
    """Which of :data:`RESOLUTION_STATES` this address is in, right now.

    THE STALENESS COMPARISON, and the only place it happens. ``current_values`` is
    the address's competing set as it stands — :func:`competing_from_evidence` of the
    entry's evidence — and a resolved decision whose digest does not match it is
    :data:`RESOLUTION_STALE` rather than current: new competing evidence arrived
    after the decision, so the decision no longer covers the conflict a reader sees.
    """
    if resolution is None:
        return RESOLUTION_ABSENT
    if resolution.outcome == OUTCOME_DEFERRED:
        return RESOLUTION_DEFERRED
    if resolution.competing_digest != competing_digest(current_values):
        return RESOLUTION_STALE
    return RESOLUTION_CURRENT


def resolutions_from_draft(draft: object) -> tuple[list[ConflictResolution], list]:
    """``(readable, unreadable_raw)`` for one draft's stored decisions. NEVER raises.

    An entry this build cannot read is returned VERBATIM in the second list rather
    than dropped, and :func:`write_resolution` writes it back out untouched — the
    arrangement ``workspace._hydrate_notes`` uses, for the same reason: a read path
    that silently deletes a recorded human decision is worse than one that admits it
    could not read it.
    """
    stored = draft.get(DRAFT_KEY) if isinstance(draft, dict) else None
    if not isinstance(stored, list):
        # A non-list container is ONE unreadable container, not N unreadable
        # entries, and there is no position to key an entry by. Preserved whole.
        return [], ([stored] if stored is not None else [])
    readable: list[ConflictResolution] = []
    unreadable: list = []
    for entry in stored:
        if not isinstance(entry, dict):
            unreadable.append(entry)
            continue
        try:
            readable.append(ConflictResolution.from_state(entry))
        except (UnsupportedResolution, TypeError, ValueError, AttributeError):
            unreadable.append(entry)
    return readable, unreadable


def find(
    resolutions: Iterable[ConflictResolution], address: str, run_id: str | None
) -> ConflictResolution | None:
    """THE resolution for one ``(address, run_id)`` pair, or ``None``.

    One decision per pair: revising replaces the record in place and appends to its
    history, so a second row for the same pair would mean two competing decisions
    with no rule for which one is current. The last match wins if a hand-edited
    document contains two — deterministic, and never a silent merge.
    """
    found = None
    for resolution in resolutions:
        if resolution.address == address and resolution.run_id == run_id:
            found = resolution
    return found


def write_resolution(draft: dict, resolution: ConflictResolution) -> None:
    """Upsert one decision into ``draft[DRAFT_KEY]``, IN PLACE. Persists nothing.

    Saving is the caller's, exactly as it is for ``Experiment.capture_note``, so a
    route records and persists once inside the same ``record_lock`` critical section
    every other mutation uses.

    Unreadable stored entries are written back out verbatim, at the end, which is
    what makes "no recorded decision is silently discarded" hold across a save of a
    document this build could not fully parse.
    """
    readable, unreadable = resolutions_from_draft(draft)
    kept = [
        entry
        for entry in readable
        if not (entry.address == resolution.address and entry.run_id == resolution.run_id)
    ]
    kept.append(resolution)
    draft[DRAFT_KEY] = [entry.to_state() for entry in kept] + list(unreadable)


def resolution_view(
    resolution: ConflictResolution, current_values: Sequence[str]
) -> dict:
    """One decision as an API presents it: its whole stored shape plus its state.

    ``state`` and ``stale`` are DERIVED on every read from the address's current
    competing set — never stored — so a resolution cannot be persisted as "current"
    and then quietly stay that way while the evidence moves on.
    """
    state = state_of(resolution, current_values)
    return {
        **resolution.to_state(),
        "state": state,
        "stale": state == RESOLUTION_STALE,
        "attributed": resolution.attributed,
    }


def resolution_states(
    draft: object, resolutions: Iterable[ConflictResolution]
) -> dict[str, str]:
    """``address -> one of RESOLUTION_STATES`` for every address in one draft's trail.

    The caller pre-filters ``resolutions`` to the scope it is describing (record-level
    decisions carry ``run_id is None``; a run's own carry its id), so this function
    does no scope reasoning and cannot get it wrong in a second place.

    Every trail address gets an entry, :data:`RESOLUTION_ABSENT` included, so a
    consumer reading the map can tell "nobody decided" from "this address was not
    described" — which a sparse map cannot express.
    """
    by_address = {
        resolution.address: resolution
        for resolution in resolutions
    }
    states: dict[str, str] = {}
    for entry in serialize.evidence_trail_from_draft(
        draft if isinstance(draft, dict) else {}
    ):
        address = str(entry.get("path"))
        states[address] = state_of(
            by_address.get(address), competing_from_evidence(entry.get("evidence"))
        )
    return states


def _explanation(distinct: int, entry_count: int, unavailable: bool) -> str:
    """The deterministic sentence for one conflict. Quotes no value.

    It names COUNTS and the RULE, never an answer: the competing values travel in
    ``candidates``, where a reader expects scientific content, and repeating one here
    would give the same value two places to be read from and two chances to disagree.
    """
    text = (
        f"This entry records {distinct} distinct non-null answers across "
        f"{entry_count} stored evidence entries, so at most one of them can be "
        "right and nothing in this application chooses between them. A conflict is "
        "always WITHIN one entry's own evidence list: it is not a disagreement "
        "between two fields, and not a disagreement about where a value came from — "
        "two citations that assert the same value are not in conflict however "
        "different their sources."
    )
    if unavailable:
        return f"{text} {evidence_classify.PARTIAL_DISCLOSURE}"
    return text


def _candidates(evidence: object) -> list[dict]:
    """The competing answers, GROUPED BY VALUE, each with the citations asserting it.

    Grouped by the canonical form rather than listed per entry, because the conflict
    rule counts DISTINCT answers: two citations asserting the same value are one
    candidate, and listing them as two would show a scientist a choice between
    identical options. That grouping is the same fact as "same value, different
    provenance is not a conflict", expressed in the surface a person acts on.

    ``sources`` is delegated to ``evidence_classify``'s safe projection —
    ``{source_type, locator?}`` only, never a raw quote, an absolute path or a
    token-shaped blob.
    """
    entries = evidence if isinstance(evidence, list) else []
    grouped: dict[str, dict] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        answer = item.get("answer")
        if answer is None:
            continue
        canonical = evidence_classify.canonical_answer(answer)
        candidate = grouped.get(canonical)
        if candidate is None:
            candidate = {
                "canonical": canonical,
                "value": answer,
                "evidence_count": 0,
                "sources": [],
            }
            grouped[canonical] = candidate
        candidate["evidence_count"] += 1
        candidate["sources"].extend(evidence_classify.sources_for([item]))
    return [grouped[key] for key in sorted(grouped)]


def conflict_report(
    draft: object,
    *,
    resolutions: Iterable[ConflictResolution],
    run_id: str | None,
) -> dict:
    """Every conflicting address in one draft, with what a person needs to decide.

    **THIS RETURNS SCIENTIFIC VALUES, AND ``submissions.conflict_summary``
    DELIBERATELY DOES NOT.** The difference is not an inconsistency to be tidied up
    in one direction or the other:

    * ``conflict_summary`` is a DISCLOSURE stored on a submission row, whose job is
      navigation — "these addresses carried conflicts when this was submitted". The
      values live in the revision snapshot beside it, and copying them into the
      disclosure would give the same value two places to live.
    * this is the RESOLUTION SURFACE. A scientist cannot choose between answers they
      are not shown, so withholding them here would make the feature unusable while
      looking careful.

    A RESOLVED ADDRESS IS STILL LISTED. ``evidence_classify`` keeps calling it
    ``conflicting_evidence`` for as long as the competing citations are stored — and
    they are stored forever, because nothing removes evidence — so hiding resolved
    addresses would hide the decision along with the conflict. ``resolution_state``
    is what a reader branches on.

    ``resolutions_without_conflict`` is the other direction, and it exists so nothing
    is silently dropped: a stored decision whose address this draft has no conflict
    at is reported rather than omitted.
    """
    resolutions = list(resolutions)
    classes = {
        result["field"]: result
        for result in evidence_classify.classify_fields(
            draft if isinstance(draft, dict) else {}
        )
    }
    conflicts: list[dict] = []
    seen_addresses: set[str] = set()
    counts = {state: 0 for state in RESOLUTION_STATES}
    for entry in serialize.evidence_trail_from_draft(
        draft if isinstance(draft, dict) else {}
    ):
        address = str(entry.get("path"))
        classified = classes.get(entry.get("path")) or {}
        if classified.get("classification") != CONFLICT_CLASSIFICATION:
            continue
        seen_addresses.add(address)
        evidence = entry.get("evidence") or []
        current = competing_from_evidence(evidence)
        resolution = find(resolutions, address, run_id)
        state = state_of(resolution, current)
        counts[state] += 1
        candidates = _candidates(evidence)
        conflicts.append(
            {
                "address": address,
                "run_id": run_id,
                "candidates": candidates,
                "distinct_value_count": len(candidates),
                "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
                # Carried for the reason `provenance.ENTRY_KEYS` carries it: an entry
                # whose stored evidence was only PARTLY readable must not present as
                # a complete picture of the disagreement.
                "unavailable": bool(entry.get("unavailable")),
                "explanation": _explanation(
                    len(candidates),
                    len(evidence) if isinstance(evidence, list) else 0,
                    bool(entry.get("unavailable")),
                ),
                "resolution_state": state,
                "resolved": state == RESOLUTION_CURRENT,
                "resolution_stale": state == RESOLUTION_STALE,
                "resolution": (
                    resolution_view(resolution, current) if resolution is not None else None
                ),
            }
        )
    orphaned = [
        {
            "address": resolution.address,
            "run_id": resolution.run_id,
            "outcome": resolution.outcome,
            "resolution_id": resolution.resolution_id,
        }
        for resolution in resolutions
        if resolution.run_id == run_id and resolution.address not in seen_addresses
    ]
    return {
        "scope": CONFLICT_SCOPE,
        "conflicts": conflicts,
        "counts": {
            "conflicting_addresses": len(conflicts),
            "resolved": counts[RESOLUTION_CURRENT],
            "deferred": counts[RESOLUTION_DEFERRED],
            "stale": counts[RESOLUTION_STALE],
            # Written out rather than left to subtraction: `unresolved` is the number
            # a reader acts on, and deriving it at three call sites is how three call
            # sites come to disagree about whether `stale` counts as unresolved. It
            # does.
            "unresolved": len(conflicts) - counts[RESOLUTION_CURRENT],
        },
        "resolutions_without_conflict": sorted(
            orphaned, key=lambda item: (item["address"], item["resolution_id"])
        ),
    }
