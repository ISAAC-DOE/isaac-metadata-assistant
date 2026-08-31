"""PERSISTENT INGESTION PROPOSALS — a stored valued suggestion a person accepts or refuses.

THE GAP THIS MODULE CLOSES, AND THE THREE THINGS THAT ALREADY EXISTED
=====================================================================

``docs/ingestion-proposal-contract.md`` §0 measures the gap precisely, and the
measurement is the design. Three of the four parts were already here:

* :mod:`isaac_api.notes` stores captured content durably and reviewably, with an
  append-only history, immutable capture fields and **no delete anywhere**;
* a note already carries the TARGET half of a proposal — ``candidate_field_path``
  plus ``candidate_rule``, and a path with no rule is refused outright;
* :mod:`isaac_api.conflict_resolution` already stores a **human decision that
  carries a value** and still reports ``is_field_value: False``.

What was genuinely absent is exactly one thing: **the valued half of a proposal did
not survive the request.** ``providers/extraction.py``'s ``FieldCandidate`` is a
valued proposal that is deliberately never stored, and there was no
accept-a-stored-value operation anywhere. :class:`IngestionProposal` is the
destination that now exists.

WHY A SIBLING TYPE AND NOT A FIELD ON ``Note``
==============================================

Contract §1 argues it at length and the two mechanical halves are these.
``IMMUTABLE_NOTE_FIELDS`` is capture-shaped — ``{id, experiment_id, captured_utc,
source, text}`` — and a proposal's frozen set is a different set: what is
load-bearing on a proposal is *what was proposed*, not *what was captured*. And a
note lives OUTSIDE the draft while ``conflict_resolution`` lives INSIDE it; a
proposal takes the note's location, which is what makes "a proposal is inert to
export" structural rather than asserted (see :data:`STATE_KEY`).

**A PROPOSAL REFERENCES A NOTE; IT NEVER REPLACES ONE.** :attr:`IngestionProposal.note_id`
is REQUIRED. The verbatim words live on the note, which survives every proposal
outcome including ``rejected``, so refusing a proposal — or never reviewing it —
can never destroy the content behind it. That is contract invariant **I6**, and it
is why this module stores offsets rather than a quote (see below).

WHAT A PROPOSAL IS NOT
======================

Not a value, not evidence, not a confirmation. :class:`IngestionProposal` is frozen
and slotted, and ``status`` / ``verified`` / ``is_evidence`` / ``is_field_value``
are **read-only properties returning constants** with no field behind them — the
arrangement ``notes.Note`` documents at length, for the same five reasons. The
constants are serialised on the wire by :meth:`IngestionProposal.to_state`, so the
guarantee crosses the JSON boundary instead of stopping at it.

Accepting one does not make this module a writer either. **Nothing here writes a
draft field, mints an evidence entry, or builds an envelope.** Contract §5 **I3**
requires that applying reuse the writers manual entry already goes through, and
``routes.py`` is where that happens; this module records that it happened
(:attr:`IngestionProposal.applied_via`). A negative control in
``test_ingestion_proposals.py`` greps this file for the two literals that would give
it away — the verified-envelope status pair, and a call to the truth core's
confirmation-entry constructor — and asserts ZERO hits. The test spells them out so
this file does not have to, which is the only way that check can mean anything. A
second envelope builder would be a second definition of what a confirmed field looks
like, free to drift from the one the exporter and the draft validator read.

FIVE THINGS DELIBERATELY NOT STORED, EACH FOR A MEASURED REASON
===============================================================

* **No ``quote``** (contract §10 DEC-3). A proposal stores :attr:`note_id` plus
  :attr:`start_char` / :attr:`end_char`, and the excerpt is derived on READ. Storing
  the words a second time would put a copy of a scientist's verbatim text somewhere
  ``routes._retention_disclosure`` does not describe, and an edited or dismissed
  note would leave that copy stale.
* **No ``unit``** (DEC-11). "Optional, never derived" still permits a unit the
  source never stated, with nothing requiring the :attr:`rule` sentence to cover it.
  A unit not stated in the source is a guess, which ``CLAUDE.md`` §5 forbids.
* **No confidence, probability or score, at any depth of the proposed value.**
  :func:`~isaac_api.providers.guards.check_candidate_provenance` is REUSED rather
  than reimplemented — see :meth:`IngestionProposal.__post_init__` for the one place
  its coverage is narrower than the requirement that asked for it, stated rather
  than papered over.
* **No ``expires_utc``.** Nothing in this build runs on a timer — no scheduler, no
  sweeper, no cron — so a stored expiry no process enforces is a promise the system
  cannot keep. Staleness is DERIVED instead, from :attr:`target_digest`.
* **No stored vocabulary.** The admissible target paths are derived at import in
  ``routes.py`` from the sets the write routes themselves enforce; transcribing them
  here would create a second copy free to drift.

STALENESS IS ``target_digest``, AND ``base_rev`` IS NOT
=======================================================

Contract §10 DEC-1, which supersedes §2's original answer. ``base_rev`` is the
RECORD's rev and moves on ANY act — a note capture, a rename, an unrelated run
edit — so using it as the acceptance precondition is wrong in BOTH directions:
every proposal on an active record would become permanently un-acceptable, and the
target itself would go unchecked.

So :attr:`target_digest` is a digest over the CURRENT CONTENT AT THE TARGET — the
draft envelope and any run override at that address — computed by
:func:`target_digest` on ``conflict_resolution.competing_digest``'s shape.
:attr:`base_rev` is kept, for the audit record only, and this module never compares
it to anything.

The comparison itself is the caller's, and contract §10.3 states where: the re-read,
the comparison and the mutation happen inside ONE ``record_lock`` block, in that
order, before any write. A digest read before the lock would let two accepts both
pass.

THE ACCEPT/REJECT ASYMMETRY, DISCLOSED RATHER THAN DISCOVERED
=============================================================

Contract §10 DEC-9, and it is stated here because a reader of this module is
otherwise entitled to assume the four review acts are symmetrical. They are not:

* **Accept requires a trusted human actor.** ``routes`` consumes
  ``identity.require_human_actor``, so acceptance answers ``409
  human_actor_required`` in every DEFAULT-CONFIGURED deployment — a claim about
  configuration, not about the build, since ``FixtureEdgeVerifier`` reaches an actor
  from the process environment and no shipped deploy artifact sets its two
  variables. The refusal path is the one that runs everywhere.
* **Reject, supersede and withdraw require no actor.** They record that nobody
  wants the proposal, which attributes nothing to anybody. Gating them would leave
  the queue permanently unclearable in every default deployment — the exact defect
  ``conflict_resolution.py`` was built to fix, reintroduced one feature over.

A consequence a reader must not have to discover: in a default deployment any
caller past ``ApiKeyAuthMiddleware`` can withdraw any proposal, and the act is
recorded ``unattributed`` because that is what it is.

Pure functions and frozen dataclasses only. No I/O, no clock, no id minting, no
environment read — the caller supplies ``at`` / ``proposal_id`` / the actor, exactly
as ``notes.py`` and ``conflict_resolution.py`` require, so this module is testable
without a workspace and cannot reach a database.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from .notes import NOTE_SOURCES

__all__ = [
    "ACCEPTED_FROM_CANDIDATE",
    "ACCEPTED_FROM_EDITED",
    "ACCEPTED_FROM_VALUES",
    "ACTION_ACCEPT",
    "ACTION_PROPOSE",
    "ACTION_REJECT",
    "ACTION_SUPERSEDE",
    "ACTION_WITHDRAW",
    "APPLIED_VIA_RECORD_ENUM",
    "APPLIED_VIA_RUN_FIELD",
    "APPLIED_VIA_RUN_OVERRIDE",
    "APPLIED_VIA_VALUES",
    "IMMUTABLE_PROPOSAL_FIELDS",
    "ImmutableProposal",
    "IngestionProposal",
    "PROPOSAL_ACTIONS",
    "PROPOSAL_SOURCES",
    "PROPOSAL_STATES",
    "PROPOSAL_STATUS",
    "PROPOSAL_TARGET_SCOPE",
    "ProposalTransition",
    "REVIEW_ACTIONS",
    "STATE_ACCEPTED",
    "STATE_KEY",
    "STATE_OPEN",
    "STATE_REJECTED",
    "STATE_SUPERSEDED",
    "STATE_WITHDRAWN",
    "UnsupportedProposal",
    "accept_proposal",
    "excerpt_of",
    "find_by_client_request_key",
    "new_proposal",
    "proposal_view",
    "reject_proposal",
    "revise_proposal",
    "supersede_proposal",
    "target_digest",
    "withdraw_proposal",
]


#: The experiment state document's top-level key, BESIDE ``notes`` and deliberately
#: NOT inside ``draft``.
#:
#: The draft is what export reads. ``conflict_resolution`` lives inside it and has
#: to disclose the consequence — for a zero-run experiment its key travels into
#: ``submissions.content_signature``. Notes' location has no such disclosure to make,
#: because ``export_draft`` reads ``Experiment.draft`` and notes are not in it.
#: Choosing the location with no leak to disclose makes contract invariant **I2** — a
#: proposal is inert to export — STRUCTURAL rather than asserted.
#:
#: Two consequences to state rather than discover: a proposal is not visible to
#: ``export.transform``, is not in the submission content signature, and is not in
#: any run's ``resolved_run_draft``. And no migration is required, because
#: ``Experiment.from_state`` reads every optional key with ``.get`` and a default, so
#: a document written before proposals existed hydrates to an empty pair.
STATE_KEY = "proposals"

#: The ONLY status a proposal can have, and it is deliberately not a draft envelope
#: status — ``notes.NOTE_STATUS``'s rule, for ``notes.NOTE_STATUS``'s reason. A
#: reader who keys on this string sees a token that appears nowhere in the draft
#: vocabulary rather than one that quietly reads as ``verified``.
PROPOSAL_STATUS = "ingestion_proposal"

#: Nobody has acted on this proposal. The state every proposal opens in, and the
#: ONLY state a review act may be performed from — see :func:`_refuse_a_closed_proposal`,
#: which is the single place that rule is enforced.
#:
#: THAT IS A DECISION RATHER THAN AN INEVITABILITY, and it is made in the direction
#: that cannot lose a fact: a proposal that has been rejected and is then accepted
#: would have a history saying both, and a reader would have to know the ordering
#: rule to say which one stands. Re-proposing is expressible — it is a NEW proposal,
#: with its own id, its own digest and its own audit trail — and that keeps every
#: recorded judgement about the old one readable exactly as it was made.
#:
#: **A `TERMINAL_STATES` CONSTANT USED TO SIT BELOW THIS AND IS DELETED.** It was
#: exported and documented and NOTHING READ IT — including the enforcement above,
#: which tests `state != STATE_OPEN` directly. A named set that reads as the rule
#: while enforcing none of it is worse than no set at all: the next reader adds a
#: state, updates the constant, and believes they have changed a behaviour.
STATE_OPEN = "open"
#: A person accepted the value AND it was applied through the manual writer that
#: owns its target. Contract §3 and §6: acceptance-without-application is
#: unconstructible here, because the admissible target set is derived from the
#: routes that write, so ``accepted`` is terminal-and-applied and there is no
#: separate ``applied`` state that could diverge from it.
STATE_ACCEPTED = "accepted"
#: A person refused the value. A STATE, reached by an explicit act and recorded in
#: the history — never a delete. The note behind it is untouched and still listed.
STATE_REJECTED = "rejected"
#: A person replaced this proposal with a later judgement. **Entered by a person,
#: never by the system**: nothing here auto-supersedes on the strength of a second
#: proposal arriving, which mirrors ``conflict_resolution``'s rule that nothing
#: inspects competing values and picks one.
STATE_SUPERSEDED = "superseded"
#: The proposal was taken back — it should not have been made. Distinct from
#: ``rejected``, which is a judgement about the VALUE.
STATE_WITHDRAWN = "withdrawn"

PROPOSAL_STATES: tuple[str, ...] = (
    STATE_OPEN,
    STATE_ACCEPTED,
    STATE_REJECTED,
    STATE_SUPERSEDED,
    STATE_WITHDRAWN,
)

#: The opening entry in every proposal's history, as ``capture`` is for a note. Not
#: a review act: it is what makes the history complete from the first moment rather
#: than starting at the first review.
ACTION_PROPOSE = "propose"
ACTION_ACCEPT = "accept"
ACTION_REJECT = "reject"
ACTION_SUPERSEDE = "supersede"
ACTION_WITHDRAW = "withdraw"

PROPOSAL_ACTIONS: tuple[str, ...] = (
    ACTION_PROPOSE,
    ACTION_ACCEPT,
    ACTION_REJECT,
    ACTION_SUPERSEDE,
    ACTION_WITHDRAW,
)

#: The four a review request may name. ``propose`` is excluded because a proposal
#: cannot be proposed twice.
REVIEW_ACTIONS: tuple[str, ...] = (
    ACTION_ACCEPT,
    ACTION_REJECT,
    ACTION_SUPERSEDE,
    ACTION_WITHDRAW,
)

#: The accepted value is the one that was proposed.
ACCEPTED_FROM_CANDIDATE = "candidate"
#: The accepted value is a NEW one the scientist typed, because the proposed one was
#: wrong. Kept distinct from :data:`ACCEPTED_FROM_CANDIDATE` for
#: ``conflict_resolution``'s stated reason: "I accepted what was proposed" and "what
#: was proposed was wrong and the value is this" are different claims, and collapsing
#: them would lose the second one.
ACCEPTED_FROM_EDITED = "edited"

ACCEPTED_FROM_VALUES: tuple[str, ...] = (ACCEPTED_FROM_CANDIDATE, ACCEPTED_FROM_EDITED)

#: Which existing writer applied an accepted value. Recorded because contract §5
#: **I3** is a claim about WHICH function ran, and a claim about which function ran
#: is worth nothing if the stored row cannot say.
APPLIED_VIA_RUN_FIELD = "run_field"
APPLIED_VIA_RUN_OVERRIDE = "run_override"
APPLIED_VIA_RECORD_ENUM = "record_enum_fields"

APPLIED_VIA_VALUES: tuple[str, ...] = (
    APPLIED_VIA_RUN_FIELD,
    APPLIED_VIA_RUN_OVERRIDE,
    APPLIED_VIA_RECORD_ENUM,
)

#: What produced the content behind a proposal. ``notes.NOTE_SOURCES`` is REUSED, not
#: re-declared, and deliberately not ``isaac_records.models.SOURCE_TYPES``: that is
#: the EVIDENCE type system, a proposal is not evidence, and widening what those
#: words mean is a truth-core change under ``CLAUDE.md`` §13 that this does not make.
#: Read from ``notes`` rather than copied so a member added there cannot leave a
#: stale set here.
PROPOSAL_SOURCES: frozenset[str] = NOTE_SOURCES

#: Echoed into :func:`target_digest`'s payload so a reader never has to infer the
#: scope of the word from its name — ``conflict_resolution.CONFLICT_SCOPE``'s purpose.
PROPOSAL_TARGET_SCOPE = "one_field_path_value_and_evidence"


class UnsupportedProposal(ValueError):
    """A proposal that cannot be constructed without inventing something."""


class ImmutableProposal(ValueError):
    """An attempt to revise a field that records what was proposed."""


#: The keys :func:`revise_proposal` refuses to change, and therefore the keys no
#: review act can touch.
#:
#: **THIS IS A DIFFERENT SET FROM ``notes.IMMUTABLE_NOTE_FIELDS``, AND THE DIFFERENCE
#: IS THE REASON THIS IS A SIBLING TYPE RATHER THAN A FIELD ON ``Note``.** A note's
#: immutable set is capture-shaped; a proposal's is proposal-shaped. What must not
#: move here is *what was proposed* — the value, the target, the rule that produced
#: it, the note it came from, the digest the acceptance precondition compares
#: against, and the identity/audit anchors.
#:
#: ``base_rev`` is in the set because it is an audit anchor and never a comparison
#: input; ``target_digest`` is in it because a proposal whose precondition could be
#: rewritten would have no precondition at all.
#:
#: This is a guard on the ONE function every mutator goes through, not a claim that
#: the attribute is unreachable — ``object.__setattr__`` reaches any frozen dataclass
#: FIELD, here as everywhere. What it buys is that a review act added later cannot
#: rewrite what was proposed by accident, only by deliberately bypassing the only
#: revision helper this module exposes. The four CONSTANTS are unreachable even that
#: way, because they are properties and were never fields.
IMMUTABLE_PROPOSAL_FIELDS: frozenset[str] = frozenset(
    {
        "proposal_id",
        "experiment_id",
        "note_id",
        "target_field_path",
        "proposed_value",
        "rule",
        "source",
        "run_id",
        "base_rev",
        "target_digest",
        "proposed_utc",
        "start_char",
        "end_char",
        "client_request_key",
    }
)


def _clean_optional(value: object, label: str) -> str | None:
    """``None`` or a non-blank string. A blank is REFUSED, never coerced to ``None``.

    ``notes._clean_optional``'s rule, for ``notes._clean_optional``'s reason: ``None``
    means "nobody supplied this" and ``""`` means a caller supplied something empty
    and expects it to have been stored. Folding the second into the first is a silent
    discard.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise UnsupportedProposal(
            f"{label} must be a string or absent, not {type(value).__name__}"
        )
    if not value.strip():
        raise UnsupportedProposal(
            f"{label} was supplied as blank. Absent is a meaning here — omit it "
            "rather than sending an empty string, which would be stored as though "
            "somebody had written something."
        )
    return value


def _recognised_trust_bases() -> frozenset[str]:
    """``identity.RECOGNISED_TRUST_BASES``, read lazily.

    Lazily so this domain module carries no import of the HTTP layer at module load
    (``identity`` imports ``fastapi``), and READ rather than transcribed so a basis
    added there cannot leave a stale literal here. ``conflict_resolution`` makes the
    same call for the same two reasons.
    """
    from . import identity  # noqa: PLC0415 - see the docstring

    return identity.RECOGNISED_TRUST_BASES


def _unattributed() -> str:
    """``submissions.TRUST_BASIS_UNATTRIBUTED``, read lazily and never transcribed."""
    from . import submissions  # noqa: PLC0415 - see :func:`_recognised_trust_bases`

    return submissions.TRUST_BASIS_UNATTRIBUTED


def _check_actor_pair(trust_basis: str, subject: str | None, what: str) -> None:
    """The paired invariant, in ONE place because it is asserted in three.

    ``unattributed`` MUST name nobody, and a recognised basis MUST name somebody.
    ``conflict_resolution.ConflictResolution.__post_init__`` states both halves and
    the reason for each: a subject beside ``unattributed`` is a name nothing vouched
    for, and a recognised basis with no subject claims a verification of nobody.
    """
    if trust_basis == _unattributed():
        if subject is not None:
            raise UnsupportedProposal(
                f"an unattributed {what} must name nobody. A subject beside "
                "`unattributed` is a name nothing vouched for."
            )
        return
    if trust_basis in _recognised_trust_bases():
        if not isinstance(subject, str) or not subject.strip():
            raise UnsupportedProposal(
                f"an attributed {what} must name somebody; a recognised trust basis "
                "with no subject claims a verification of nobody"
            )
        return
    raise UnsupportedProposal(
        f"unknown trust basis {trust_basis!r}; allowed: "
        f"{sorted({_unattributed()} | _recognised_trust_bases())}"
    )


def target_digest(target_state: object) -> str:
    """The sha256 identity of what one proposal's TARGET currently holds.

    THE ACCEPTANCE PRECONDITION, and contract §10 DEC-1's whole point. ``base_rev``
    is the RECORD's rev and moves on any act, so it is wrong in both directions —
    every proposal on an active record would become permanently un-acceptable, and
    the target itself would go unchecked. This digest moves when, and only when, the
    content at the target moves.

    ``target_state`` is supplied by the caller and is whatever that target holds:
    the draft field envelope (value AND evidence, which is why an added confirmation
    moves it) and, for a run-scoped address, the run's override record. Composing it
    is ``routes``' job, because only ``routes`` knows which of the three write
    classes a path belongs to; digesting it is this module's, so there is ONE
    definition of the comparison.

    ``submissions.canonical_json`` is USED rather than reimplemented — it is this
    application's one deterministic JSON text form, and a second copy is how two
    digests of the same content come to disagree. It is imported lazily for the
    reason :func:`_recognised_trust_bases` gives.
    """
    from . import submissions  # noqa: PLC0415 - see :func:`_recognised_trust_bases`

    payload = {"scope": PROPOSAL_TARGET_SCOPE, "target": target_state}
    return hashlib.sha256(
        submissions.canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _refuse_a_confidence(where: str, value: object) -> None:
    """Refuse a confidence-like key anywhere in the proposed value's tree.

    REUSED, NOT REIMPLEMENTED. ``providers.guards.check_candidate_provenance`` is the
    function ``FieldCandidate.__post_init__`` already runs, and running the same one
    here means a stored proposal cannot carry something an unstored candidate is
    refused for. A stored uncertainty is a confidence score with a different name,
    and the ``rule`` sentence already says what was and was not established.

    **ONE THING IT DOES NOT COVER, STATED RATHER THAN IMPLIED.** The requirement that
    asked for this says "no ``uncertainty`` / ``confidence`` / ``probability`` /
    ``score`` at any depth", and ``inferability._CONFIDENCE_KEYS`` is
    ``{confidence, probability, score}`` — **``uncertainty`` is not a member.** A
    nested ``uncertainty: {confidence: 0.86}`` IS caught, because the scan recurses
    and that is the corpus shape it was written for; a bare ``uncertainty: 0.02``
    is NOT. That set is shared with the extraction seam and widening it would change
    what every other caller refuses, so it is left alone and the gap is closed from
    the other side instead: ``routes`` refuses ``uncertainty`` as a REQUEST body key
    by name, alongside ``unit``, ``quote`` and ``expires_utc``. What is deliberately
    NOT refused is an ``uncertainty`` key inside a scientist's own value — that is
    measured scientific content on some ISAAC paths, and refusing it here would be
    this module inventing a rule about science.
    """
    from .providers.guards import (  # noqa: PLC0415 - see :func:`_recognised_trust_bases`
        UnsupportedSuggestion,
        check_candidate_provenance,
    )

    try:
        check_candidate_provenance(where, value)
    except UnsupportedSuggestion as refusal:
        raise UnsupportedProposal(str(refusal)) from refusal


@dataclass(frozen=True, slots=True)
class ProposalTransition:
    """ONE act in a proposal's life, appended and never rewritten.

    ``notes.NoteTransition``'s shape, including its naming constraint: a
    ``slots=True`` dataclass raises at class-creation time if a method shares a
    field's name, and ``from_state`` / ``to_state`` are the names a reader of a
    stored audit row needs — so the serialisers are ``to_state_dict`` /
    ``from_state_dict``.

    THE ACTOR LIVES HERE AND NOWHERE ELSE. Contract §2 wants both an initiating
    principal and a reviewer identity; storing the reviewer on the proposal as well
    would give one fact two homes, which is the mistake §2 itself names for
    ``target scope``. The proposal carries who PROPOSED; each transition carries who
    performed THAT act, and :func:`proposal_view` derives ``accepted_by`` from the
    accept transition.
    """

    action: str
    at: str
    #: The state before this act. ``None`` only for :data:`ACTION_PROPOSE`.
    from_state: str | None
    to_state: str
    #: The actor's trust basis for THIS act. ``unattributed`` whenever nobody was
    #: established — which is every reject/supersede/withdraw, because those
    #: deliberately require no actor (DEC-9), and every act in a worked-example
    #: session, because ``identity.stamp_actor`` returns ``None`` there
    #: unconditionally and first.
    actor_trust_basis: str | None = None
    actor_subject: str | None = None
    #: For :data:`ACTION_ACCEPT`: the value that was written, and whether it was the
    #: proposed one or a corrected one. Kept on the transition as well as on the
    #: proposal so the history says what happened without a second lookup.
    accepted_value: Any = None
    accepted_from: str | None = None
    #: For :data:`ACTION_REJECT`: the scientist's reason, when they gave one. Absent
    #: when they did not — ``notes.dismiss_note``'s rule, for its reason: a
    #: fabricated justification in an audit trail is worse than a missing one.
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.action not in PROPOSAL_ACTIONS:
            raise UnsupportedProposal(f"unknown proposal action {self.action!r}")
        if self.to_state not in PROPOSAL_STATES:
            raise UnsupportedProposal(f"unknown proposal state {self.to_state!r}")
        if self.from_state is not None and self.from_state not in PROPOSAL_STATES:
            raise UnsupportedProposal(f"unknown prior state {self.from_state!r}")
        if self.action == ACTION_PROPOSE and self.from_state is not None:
            raise UnsupportedProposal(
                "the opening act of a proposal has no prior state; naming one would "
                "claim an act that never happened"
            )
        if self.action != ACTION_PROPOSE and self.from_state is None:
            raise UnsupportedProposal(
                "a review act must name the state it moved from, or the history "
                "cannot say what changed"
            )
        if not self.at:
            raise UnsupportedProposal("a transition must record when it happened")
        object.__setattr__(
            self, "actor_subject", _clean_optional(self.actor_subject, "actor_subject")
        )
        object.__setattr__(self, "reason", _clean_optional(self.reason, "reason"))
        if self.actor_trust_basis is not None:
            _check_actor_pair(self.actor_trust_basis, self.actor_subject, "act")
        elif self.actor_subject is not None:
            raise UnsupportedProposal(
                "a transition naming a subject must say what vouched for it; a name "
                "with no trust basis is a name nothing stands behind"
            )
        if self.accepted_from is not None and self.accepted_from not in ACCEPTED_FROM_VALUES:
            raise UnsupportedProposal(
                f"accepted_from must be one of {list(ACCEPTED_FROM_VALUES)}"
            )

    def to_state_dict(self) -> dict:
        return {
            "action": self.action,
            "at": self.at,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "actor_trust_basis": self.actor_trust_basis,
            "actor_subject": self.actor_subject,
            "accepted_value": self.accepted_value,
            "accepted_from": self.accepted_from,
            "reason": self.reason,
        }

    @classmethod
    def from_state_dict(cls, state: dict) -> "ProposalTransition":
        return cls(
            action=state.get("action"),  # type: ignore[arg-type]
            at=state.get("at"),  # type: ignore[arg-type]
            from_state=state.get("from_state"),
            to_state=state.get("to_state"),  # type: ignore[arg-type]
            actor_trust_basis=state.get("actor_trust_basis"),
            actor_subject=state.get("actor_subject"),
            accepted_value=state.get("accepted_value"),
            accepted_from=state.get("accepted_from"),
            reason=state.get("reason"),
        )


@dataclass(frozen=True, slots=True)
class IngestionProposal:
    """One stored suggestion: a value, a target, and the rule that produced them.

    ``slots=True`` is load-bearing rather than a micro-optimisation: it removes the
    instance ``__dict__``, which is the last route by which an attribute like
    ``verified`` or ``authoritative`` could be attached after construction.
    """

    proposal_id: str
    experiment_id: str
    #: THE NOTE THIS PROPOSAL CAME FROM. Required, and required is the point: the
    #: verbatim words live there, the note survives every proposal outcome, and so
    #: rejecting a proposal can never destroy content. Contract invariant **I6**.
    note_id: str
    #: The official field path this proposal is about. Membership-gated by
    #: ``routes.PROPOSAL_TARGET_PATHS``, which is DERIVED from the routes that write
    #: rather than listed anywhere; this module performs no schema lookup and
    #: deliberately does not learn to, exactly as ``notes.py`` does not.
    target_field_path: str
    #: WHAT IS BEING PROPOSED. Deep-copied at construction — ``new_proposal``'s
    #: docstring says why.
    proposed_value: Any
    #: The rule that produced the value and the target, stated in full — the
    #: sentence, not an id, so a reader can check the proposal without a lookup
    #: table. Required UNCONDITIONALLY, which is stricter than ``notes.Note``, where
    #: it is required only alongside a candidate path: a proposal with no target is
    #: not constructible here, so there is no case in which the rule is optional.
    rule: str
    #: One of :data:`PROPOSAL_SOURCES`.
    source: str
    proposed_utc: str
    #: The RECORD's rev when this was proposed. **FOR THE AUDIT RECORD ONLY.** It is
    #: never compared to anything — see the module docstring and :func:`target_digest`.
    base_rev: int
    #: What the target held when this was proposed. THE acceptance precondition.
    target_digest: str
    #: Who PROPOSED. ``unattributed`` in every deployment today, because creating a
    #: proposal requires no actor. The paired invariant is enforced below.
    trust_basis: str
    #: The run this proposal is about, or ``None`` for the record's own draft. NEVER
    #: inferred from the only run that happens to exist — ``notes.Note``'s rule, for
    #: ``notes.Note``'s reason, and the rule that makes ``409 target_run_removed``
    #: correct rather than fussy: a removed run's id is never reissued, so a proposal
    #: naming it goes permanently dangling instead of silently shifting onto a
    #: neighbour.
    run_id: str | None = None
    #: The half-open span of the NOTE's text this proposal was read from, or
    #: ``None``. The excerpt is derived on read (:func:`excerpt_of`) and never
    #: stored — contract §10 DEC-3.
    start_char: int | None = None
    end_char: int | None = None
    #: An optional caller-chosen key making creation exactly-once within one
    #: experiment. Contract §10 DEC-13: two identical creates would otherwise mint
    #: two ids, so a retrying client duplicates. Enforcement is the route's, inside
    #: ``record_lock``, which is why no uniqueness constraint is needed.
    client_request_key: str | None = None
    state: str = STATE_OPEN
    subject: str | None = None
    #: Set by :func:`accept_proposal` only. The value actually written, which is the
    #: proposed one for ``candidate`` and a corrected one for ``edited``.
    accepted_value: Any = None
    accepted_from: str | None = None
    #: Which existing writer applied it, one of :data:`APPLIED_VIA_VALUES`.
    applied_via: str | None = None
    #: The run the write landed on, which is ``run_id`` for every applied proposal
    #: today and is stored separately because "which run this is ABOUT" and "which
    #: run was WRITTEN" are different facts and a future writer could separate them.
    applied_run_id: str | None = None
    #: The record's ``rev`` AS IT STOOD when the write was applied. The act itself
    #: then advances the record past it, so this is the revision the write was
    #: applied ON TOP OF and not the revision it produced. Stated precisely because
    #: an off-by-one in an audit field is indistinguishable from a correct one.
    applied_rev: int | None = None
    #: What the target held immediately AFTER the write. :func:`proposal_view`
    #: re-digests the target on every read and compares, so ``still_current`` is
    #: derived and never stored — contract §10 DEC-8.
    applied_target_digest: str | None = None
    #: Append-only. Opens with an :data:`ACTION_PROPOSE` entry.
    history: tuple[ProposalTransition, ...] = ()

    def __post_init__(self) -> None:
        for name in ("proposal_id", "experiment_id", "note_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise UnsupportedProposal(
                    f"a proposal must have a non-blank {name}; "
                    + (
                        "an unaddressable proposal cannot be reviewed or cited"
                        if name == "proposal_id"
                        else "a proposal that cannot name what it belongs to is "
                        "unreachable from the content behind it"
                    )
                )
        if not isinstance(self.target_field_path, str) or not self.target_field_path.strip():
            raise UnsupportedProposal(
                "a proposal must name the field path it is about. A proposal with no "
                "target is a value with nowhere to go."
            )
        if not isinstance(self.rule, str) or not self.rule.strip():
            raise UnsupportedProposal(
                f"{self.target_field_path}: a proposal must state the rule that "
                "produced it. An unexplained proposal is a guess wearing a field name."
            )
        if self.source not in PROPOSAL_SOURCES:
            raise UnsupportedProposal(
                f"unknown proposal source {self.source!r}; allowed: "
                f"{sorted(PROPOSAL_SOURCES)}"
            )
        if not self.proposed_utc:
            raise UnsupportedProposal("a proposal must record when it was made")
        if self.state not in PROPOSAL_STATES:
            raise UnsupportedProposal(f"unknown proposal state {self.state!r}")
        # `bool` is an `int` in Python, and `base_rev=True` would store a revision of
        # 1 that nothing ever wrote. Refused rather than coerced.
        if not isinstance(self.base_rev, int) or isinstance(self.base_rev, bool) or self.base_rev < 0:
            raise UnsupportedProposal(
                "base_rev must be the record's revision as a non-negative integer"
            )
        if not isinstance(self.target_digest, str) or not self.target_digest.strip():
            raise UnsupportedProposal(
                "a proposal must record what its target held when it was made, or "
                "acceptance has no precondition to check and a stale proposal could "
                "overwrite a newer value"
            )
        object.__setattr__(self, "run_id", _clean_optional(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "client_request_key",
            _clean_optional(self.client_request_key, "client_request_key"),
        )
        object.__setattr__(
            self, "applied_run_id", _clean_optional(self.applied_run_id, "applied_run_id")
        )

        # A PROPOSAL MAY NOT CARRY A CONFIDENCE. See `_refuse_a_confidence`, which
        # states exactly where the reused guard's coverage stops.
        _refuse_a_confidence(self.target_field_path, self.proposed_value)
        if self.accepted_value is not None:
            _refuse_a_confidence(self.target_field_path, self.accepted_value)

        # THE SPAN IS A PAIR OR IT IS NOTHING. Half of one is a claim about the note
        # this module cannot complete, and the bounds check against the note's text
        # is the ROUTE's — this module never sees the note.
        if (self.start_char is None) != (self.end_char is None):
            raise UnsupportedProposal(
                "start_char and end_char travel together; half a span names a "
                "position in the note without saying where it ends"
            )
        for name in ("start_char", "end_char"):
            offset = getattr(self, name)
            if offset is None:
                continue
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                raise UnsupportedProposal(f"{name} must be a non-negative integer")
        if (
            self.start_char is not None
            and self.end_char is not None
            and self.start_char > self.end_char
        ):
            raise UnsupportedProposal(
                "start_char must not be past end_char; a span that ends before it "
                "begins names no text at all"
            )

        _check_actor_pair(self.trust_basis, self.subject, "proposal")

        if self.state == STATE_ACCEPTED:
            if self.accepted_value is None:
                raise UnsupportedProposal(
                    "an accepted proposal must record the value that was written. "
                    "Nothing here writes one on a scientist's behalf, so an accepted "
                    "proposal with no value would claim a decision nobody made."
                )
            if self.accepted_from not in ACCEPTED_FROM_VALUES:
                raise UnsupportedProposal(
                    f"accepted_from must be one of {list(ACCEPTED_FROM_VALUES)}; it "
                    "says whether the proposed value was accepted as it stood or "
                    "corrected first, and the two are different claims"
                )
            if self.applied_via not in APPLIED_VIA_VALUES:
                raise UnsupportedProposal(
                    "an accepted proposal must record WHICH writer applied it; "
                    f"allowed: {list(APPLIED_VIA_VALUES)}. `accepted` is "
                    "terminal-and-applied here, so a row that cannot say how the "
                    "value was written would be claiming an application that may "
                    "never have happened."
                )
            if (
                not isinstance(self.applied_rev, int)
                or isinstance(self.applied_rev, bool)
                or self.applied_rev < 0
            ):
                raise UnsupportedProposal(
                    "an accepted proposal must record the revision the write was "
                    "applied on top of"
                )
            if not isinstance(self.applied_target_digest, str) or not self.applied_target_digest:
                raise UnsupportedProposal(
                    "an accepted proposal must record what its target held after the "
                    "write, or `still_current` could not be derived on read and the "
                    "acceptance would read as a standing claim about the record's "
                    "present content"
                )
        else:
            # AN UNACCEPTED PROPOSAL CARRIES NO TRACE OF AN APPLICATION, in every one
            # of the five fields. "Nobody accepted this" and "somebody accepted it and
            # we filed it as open" are different facts, and a record that could hold
            # both would make the state unreadable.
            for name in (
                "accepted_value",
                "accepted_from",
                "applied_via",
                "applied_run_id",
                "applied_rev",
                "applied_target_digest",
            ):
                if getattr(self, name) is not None:
                    raise UnsupportedProposal(
                        f"a proposal in state {self.state!r} carries no {name}; "
                        "storing one would record an application under a state that "
                        "says none happened"
                    )

        if not isinstance(self.history, tuple) or any(
            not isinstance(entry, ProposalTransition) for entry in self.history
        ):
            raise UnsupportedProposal(
                "a proposal's history must be a tuple of transitions"
            )

    # --- the four constants that make "a confirmed value" unconstructible ------

    @property
    def status(self) -> str:
        """Always :data:`PROPOSAL_STATUS`, which is not a draft envelope status."""
        return PROPOSAL_STATUS

    @property
    def verified(self) -> bool:
        """Always ``False``. A proposal is what somebody suggested, not what is so."""
        return False

    @property
    def is_evidence(self) -> bool:
        """Always ``False``. A suggestion about a field is not a citation for it."""
        return False

    @property
    def is_field_value(self) -> bool:
        """Always ``False``, ACCEPTED PROPOSALS INCLUDED.

        ``conflict_resolution.ConflictResolution`` already demonstrates that carrying
        a value does not violate this repository's invariant: the invariant is never
        PRESENTING as a confirmed field value, not never HOLDING one. An accepted
        proposal records that a value was written by the manual writer that owns the
        target; the field's value lives in the draft envelope that writer produced,
        and reading it from here would give one value two homes.
        """
        return False

    # --- derived reads --------------------------------------------------------

    @property
    def applied(self) -> bool:
        """Whether a value was written through this proposal.

        Serialised on the wire beside the three constants because contract §2
        requires it there, and because a JSON consumer cannot see that ``accepted``
        is terminal-and-applied by reading a state string.
        """
        return self.state == STATE_ACCEPTED

    @property
    def attributed(self) -> bool:
        return self.trust_basis != _unattributed()

    def to_state(self) -> dict:
        """The persistence AND wire shape, the four constants and ``applied`` included.

        A consumer reading JSON does not see the class invariant, so the guarantee
        has to cross the boundary rather than stop at it — the rule
        ``FieldCandidate.to_dict`` set and ``Note.to_state`` follows.
        """
        return {
            "proposal_id": self.proposal_id,
            "experiment_id": self.experiment_id,
            "note_id": self.note_id,
            "run_id": self.run_id,
            "target_field_path": self.target_field_path,
            "proposed_value": self.proposed_value,
            "rule": self.rule,
            "source": self.source,
            "proposed_utc": self.proposed_utc,
            "base_rev": self.base_rev,
            "target_digest": self.target_digest,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "client_request_key": self.client_request_key,
            "state": self.state,
            "subject": self.subject,
            "trust_basis": self.trust_basis,
            "accepted_value": self.accepted_value,
            "accepted_from": self.accepted_from,
            "applied_via": self.applied_via,
            "applied_run_id": self.applied_run_id,
            "applied_rev": self.applied_rev,
            "applied_target_digest": self.applied_target_digest,
            "history": [entry.to_state_dict() for entry in self.history],
            "status": self.status,
            "verified": self.verified,
            "is_evidence": self.is_evidence,
            "is_field_value": self.is_field_value,
            "applied": self.applied,
        }

    @classmethod
    def from_state(cls, state: dict) -> "IngestionProposal":
        """Rehydrate one proposal. RAISES on a document it cannot represent honestly.

        Deliberately like ``notes.Note.from_state`` and ``ConflictResolution.from_state``,
        and unlike ``Run.from_state``: a run coerced to a default is still the same
        run, while a proposal whose value, target or digest cannot be read is
        something this module would have to invent.

        Raising is safe — and is not a route back to the 500s policy was written
        for — because the ONLY caller is ``workspace._hydrate_proposals``, which
        catches it and PRESERVES the raw entry verbatim. Nothing is lost, nothing is
        guessed, the entry is reported as unreadable, and it is written back out
        untouched on the next save.
        """
        history = state.get("history")
        return cls(
            proposal_id=state.get("proposal_id"),  # type: ignore[arg-type]
            experiment_id=state.get("experiment_id"),  # type: ignore[arg-type]
            note_id=state.get("note_id"),  # type: ignore[arg-type]
            target_field_path=state.get("target_field_path"),  # type: ignore[arg-type]
            proposed_value=state.get("proposed_value"),
            rule=state.get("rule"),  # type: ignore[arg-type]
            source=state.get("source"),  # type: ignore[arg-type]
            proposed_utc=state.get("proposed_utc"),  # type: ignore[arg-type]
            base_rev=state.get("base_rev"),  # type: ignore[arg-type]
            target_digest=state.get("target_digest"),  # type: ignore[arg-type]
            trust_basis=state.get("trust_basis"),  # type: ignore[arg-type]
            run_id=state.get("run_id"),
            start_char=state.get("start_char"),
            end_char=state.get("end_char"),
            client_request_key=state.get("client_request_key"),
            state=state.get("state", STATE_OPEN),
            subject=state.get("subject"),
            accepted_value=state.get("accepted_value"),
            accepted_from=state.get("accepted_from"),
            applied_via=state.get("applied_via"),
            applied_run_id=state.get("applied_run_id"),
            applied_rev=state.get("applied_rev"),
            applied_target_digest=state.get("applied_target_digest"),
            history=tuple(
                ProposalTransition.from_state_dict(entry)
                for entry in (history if isinstance(history, list) else [])
                if isinstance(entry, dict)
            ),
        )


def new_proposal(
    *,
    proposal_id: str,
    experiment_id: str,
    note_id: str,
    target_field_path: str,
    proposed_value: Any,
    rule: str,
    source: str,
    proposed_utc: str,
    base_rev: int,
    target_digest: str,
    trust_basis: str,
    run_id: str | None = None,
    start_char: int | None = None,
    end_char: int | None = None,
    client_request_key: str | None = None,
    subject: str | None = None,
) -> IngestionProposal:
    """Mint a proposal with its opening :data:`ACTION_PROPOSE` entry already in it.

    The id is supplied by the caller rather than minted here so this module stays
    free of the truth core's id package — ``notes.new_note``'s and
    ``conflict_resolution.new_resolution``'s arrangement, for the same reason. **A
    PROPOSAL ID IS NOT A RECORD ID:** it names no exported artifact and never will.

    ``proposed_value`` is DEEP-COPIED, exactly as ``new_resolution`` copies
    ``chosen_value`` and ``set_run_override`` copies its payload, and for the same
    reason: a stored reference to a live envelope would let a later in-place edit
    rewrite what was proposed, and this record's whole value is that it says what was
    proposed at the time.
    """
    return IngestionProposal(
        proposal_id=proposal_id,
        experiment_id=experiment_id,
        note_id=note_id,
        target_field_path=target_field_path,
        proposed_value=copy.deepcopy(proposed_value),
        rule=rule,
        source=source,
        proposed_utc=proposed_utc,
        base_rev=base_rev,
        target_digest=target_digest,
        trust_basis=trust_basis,
        run_id=run_id,
        start_char=start_char,
        end_char=end_char,
        client_request_key=client_request_key,
        subject=subject,
        state=STATE_OPEN,
        history=(
            ProposalTransition(
                action=ACTION_PROPOSE,
                at=proposed_utc,
                from_state=None,
                to_state=STATE_OPEN,
                actor_trust_basis=trust_basis,
                actor_subject=subject,
            ),
        ),
    )


def revise_proposal(proposal: IngestionProposal, **changes: Any) -> IngestionProposal:
    """``dataclasses.replace`` with what was proposed and the audit trail held closed.

    THE ONE REVISION HELPER — ``notes.revise_note``'s arrangement, so the two rules
    it enforces cannot be forgotten by an act added later:

    * a field in :data:`IMMUTABLE_PROPOSAL_FIELDS` may not be changed at all;
    * a replacement ``history`` must EXTEND the existing one. A shorter history, or
      one whose earlier entries differ, is refused — an audit trail that can be
      rewritten is not an audit trail.
    """
    forbidden = sorted(set(changes) & IMMUTABLE_PROPOSAL_FIELDS)
    if forbidden:
        raise ImmutableProposal(
            f"{forbidden} record what was proposed and cannot be revised. A review "
            "act records a decision beside the proposal; it never rewrites it."
        )
    new_history = changes.get("history")
    if new_history is not None:
        if len(new_history) < len(proposal.history) or tuple(
            new_history[: len(proposal.history)]
        ) != tuple(proposal.history):
            raise ImmutableProposal(
                "a proposal's history may only be extended. Replacing or shortening "
                "it would erase the record of an act that happened."
            )
    return dataclasses.replace(proposal, **changes)


def _appended(
    proposal: IngestionProposal, transition: ProposalTransition
) -> tuple[ProposalTransition, ...]:
    return (*proposal.history, transition)


def _refuse_a_closed_proposal(proposal: IngestionProposal, action: str) -> None:
    """A review act reaches an OPEN proposal or it reaches none.

    THE ONLY PLACE **THIS MODULE** ENFORCES IT — precisely stated, because
    ``routes.post_proposal_review`` checks the same condition itself and answers
    ``422 proposal_not_open`` before ever calling one of these acts, so a break here
    is invisible from every route. That is why the guard has a test of its own that
    drives all four acts directly rather than over HTTP.

    It tests :data:`STATE_OPEN` directly rather than membership of a set of the
    others — see :data:`STATE_OPEN` for why this is a decision rather than an
    inevitability, and for what a caller does instead (mint a new proposal).
    """
    if proposal.state != STATE_OPEN:
        raise UnsupportedProposal(
            f"this proposal is already {proposal.state!r}, so it cannot be "
            f"{action}ed. Every recorded judgement stays exactly as it was made; a "
            "later view is a NEW proposal, with its own id and its own audit trail."
        )


def accept_proposal(
    proposal: IngestionProposal,
    *,
    at: str,
    accepted_value: Any,
    accepted_from: str,
    applied_via: str,
    applied_rev: int,
    applied_target_digest: str,
    applied_run_id: str | None = None,
    actor_trust_basis: str,
    actor_subject: str | None = None,
) -> IngestionProposal:
    """Record that a value was written through this proposal. APPENDS.

    **THIS FUNCTION WRITES NOTHING.** The caller has already applied the value
    through the writer that owns the target — ``routes._apply_run_field``,
    ``workspace.Experiment.set_run_override`` or ``routes._apply_record_fields``
    — and passes ``applied_via`` naming which one ran. Building an envelope here
    would be a second definition of what a confirmed field looks like, free to drift
    from the one the exporter and the draft validator read.

    ``applied_target_digest`` is what the target held AFTER that write, so
    :func:`proposal_view` can derive ``still_current`` on every read. Contract §10
    DEC-8: without it, an accepted proposal reads as a standing claim about the
    record's present content, when the target can be corrected afterwards through
    ``/edit``, ``/overrides`` or ``PATCH .../runs/{id}``.

    NOT IDEMPOTENT, and that asymmetry with the notes acts is deliberate: acceptance
    is refused from any state but ``open``, so a double-click reaches
    :func:`_refuse_a_closed_proposal` rather than silently appending a second
    application of a write that already happened.
    """
    _refuse_a_closed_proposal(proposal, "accept")
    return revise_proposal(
        proposal,
        state=STATE_ACCEPTED,
        accepted_value=copy.deepcopy(accepted_value),
        accepted_from=accepted_from,
        applied_via=applied_via,
        applied_run_id=applied_run_id,
        applied_rev=applied_rev,
        applied_target_digest=applied_target_digest,
        history=_appended(
            proposal,
            ProposalTransition(
                action=ACTION_ACCEPT,
                at=at,
                from_state=proposal.state,
                to_state=STATE_ACCEPTED,
                actor_trust_basis=actor_trust_basis,
                actor_subject=actor_subject,
                accepted_value=copy.deepcopy(accepted_value),
                accepted_from=accepted_from,
            ),
        ),
    )


def _closed(
    proposal: IngestionProposal,
    *,
    action: str,
    to_state: str,
    at: str,
    reason: str | None = None,
    actor_trust_basis: str | None = None,
    actor_subject: str | None = None,
) -> IngestionProposal:
    """The three non-writing outcomes, which differ only in what they are called.

    ONE implementation because a second one would be a second place the "nothing is
    removed" rule has to be remembered. Each is a STATE reached by an explicit act
    and recorded in the history — never a delete, and the note behind the proposal is
    untouched by all three.
    """
    _refuse_a_closed_proposal(proposal, action)
    return revise_proposal(
        proposal,
        state=to_state,
        history=_appended(
            proposal,
            ProposalTransition(
                action=action,
                at=at,
                from_state=proposal.state,
                to_state=to_state,
                reason=reason,
                actor_trust_basis=actor_trust_basis,
                actor_subject=actor_subject,
            ),
        ),
    )


def reject_proposal(
    proposal: IngestionProposal,
    *,
    at: str,
    reason: str | None = None,
    actor_trust_basis: str | None = None,
    actor_subject: str | None = None,
) -> IngestionProposal:
    """Refuse the value. A STATE CHANGE, NOT A DELETE, and the note is untouched.

    ``reason`` is stored when a scientist gives one and is ABSENT when they do not —
    ``notes.dismiss_note``'s rule, for its reason: a fabricated justification in an
    audit trail is worse than a missing one.

    **NO ACTOR IS REQUIRED**, and the asymmetry with :func:`accept_proposal` is
    disclosed in the module docstring rather than left to be discovered. Rejecting
    records that nobody wants the proposal, which attributes nothing to anybody.
    """
    return _closed(
        proposal,
        action=ACTION_REJECT,
        to_state=STATE_REJECTED,
        at=at,
        reason=reason,
        actor_trust_basis=actor_trust_basis,
        actor_subject=actor_subject,
    )


def supersede_proposal(
    proposal: IngestionProposal,
    *,
    at: str,
    reason: str | None = None,
    actor_trust_basis: str | None = None,
    actor_subject: str | None = None,
) -> IngestionProposal:
    """Record that a later judgement replaces this one. ENTERED BY A PERSON, ALWAYS.

    Nothing in this module auto-supersedes on the strength of a second proposal
    arriving, which mirrors ``conflict_resolution``'s rule that nothing inspects
    competing values and picks one. The superseding judgement is a separate proposal
    with its own audit trail; this act says only that this one no longer stands.
    """
    return _closed(
        proposal,
        action=ACTION_SUPERSEDE,
        to_state=STATE_SUPERSEDED,
        at=at,
        reason=reason,
        actor_trust_basis=actor_trust_basis,
        actor_subject=actor_subject,
    )


def withdraw_proposal(
    proposal: IngestionProposal,
    *,
    at: str,
    reason: str | None = None,
    actor_trust_basis: str | None = None,
    actor_subject: str | None = None,
) -> IngestionProposal:
    """Take the proposal back — it should not have been made.

    Distinct from :func:`reject_proposal`, which is a judgement about the VALUE.
    Requires no actor, for :func:`reject_proposal`'s reason.
    """
    return _closed(
        proposal,
        action=ACTION_WITHDRAW,
        to_state=STATE_WITHDRAWN,
        at=at,
        reason=reason,
        actor_trust_basis=actor_trust_basis,
        actor_subject=actor_subject,
    )


# A ``find(proposals, proposal_id)`` helper used to sit here, mirroring
# ``conflict_resolution.find``, and it is DELETED rather than kept for symmetry:
# nothing called it. ``Experiment.get_proposal`` is what every route uses, and it is
# the only lookup that can be correct here — it searches the experiment that HOLDS
# the proposal, where the deleted helper searched whatever iterable a caller passed.
# Its "last match wins" tie-break was also unreachable by construction:
# ``workspace._hydrate_proposals`` files a duplicate ``proposal_id`` as unreadable, so
# no hydrated list can contain two.


def find_by_client_request_key(
    proposals: Iterable[IngestionProposal], key: str
) -> IngestionProposal | None:
    """The EARLIEST proposal carrying this creation key, or ``None``.

    Earliest rather than latest, which is the opposite of :func:`find` and is not an
    inconsistency: this answers "did this create already happen?", and the answer a
    retrying client must get back is the proposal its FIRST attempt minted. Returning
    a later one would hand a retry a different id from the one the original request
    established.
    """
    for proposal in proposals:
        if proposal.client_request_key is not None and proposal.client_request_key == key:
            return proposal
    return None


def excerpt_of(proposal: IngestionProposal, note_text: str | None) -> str | None:
    """The words this proposal was read from, DERIVED on read and never stored.

    Contract §10 DEC-3. ``None`` when the proposal records no span, when the note is
    unavailable, or when the span no longer falls inside the note's text — which is
    reachable, because ``notes.edit_note`` stores a corrected wording beside the
    verbatim capture and a client may render either.

    **THE VERBATIM ``text`` IS THE SUBJECT, NOT ``display_text``**, and that is the
    half that makes the offsets meaningful: the capture is immutable
    (``IMMUTABLE_NOTE_FIELDS``), so a span into it cannot go stale, while a span into
    an editable string would silently start naming different words. The caller passes
    ``note.text``.

    A span that does not fit answers ``None`` rather than a clamped substring: a
    clamped excerpt is a quotation of words nobody wrote, which is worse than no
    quotation at all.
    """
    if proposal.start_char is None or proposal.end_char is None:
        return None
    if not isinstance(note_text, str):
        return None
    if proposal.end_char > len(note_text):
        return None
    return note_text[proposal.start_char : proposal.end_char]


def proposal_view(
    proposal: IngestionProposal,
    *,
    current_target_digest: str | None = None,
    note_text: str | None = None,
) -> dict:
    """One proposal as an API presents it: its stored shape plus what is derived.

    THREE DERIVED READS, none of them stored, each for a reason contract §10 names:

    * ``target_stale`` — the target has moved since the proposal was made, so
      accepting it now would be accepting a judgement about content that is no
      longer there. Derived from :attr:`IngestionProposal.target_digest` (DEC-1), not
      from ``base_rev``, which moves on every unrelated act.
    * ``still_current`` — for an ACCEPTED proposal, whether the target still holds
      what the acceptance wrote. ``accepted`` is terminal, and the target can be
      corrected afterwards through ``/edit``, ``/overrides`` or ``PATCH .../runs/{id}``;
      without this an accepted proposal reads as a standing claim about the record's
      present content (DEC-8).
    * ``excerpt`` — the note's words, derived from the stored offsets (DEC-3).

    Each is ``None`` when it cannot be answered rather than defaulted to a boolean:
    "the target could not be read" and "the target is unchanged" are different facts,
    and a ``False`` covering both would be the more comfortable of the two.

    ``accepted_by`` is read off the ACCEPT transition rather than stored on the
    proposal, so who accepted has one home. It is ``None`` for an unaccepted
    proposal, and its ``subject`` is ``None`` whenever the act was unattributed — no
    placeholder, ever.
    """
    stale: bool | None = None
    still_current: bool | None = None
    if current_target_digest is not None:
        stale = current_target_digest != proposal.target_digest
        if proposal.applied_target_digest is not None:
            still_current = current_target_digest == proposal.applied_target_digest
    accepted_by = None
    for entry in reversed(proposal.history):
        if entry.action == ACTION_ACCEPT:
            accepted_by = {
                "subject": entry.actor_subject,
                "trust_basis": entry.actor_trust_basis,
                "attributed": entry.actor_trust_basis not in (None, _unattributed()),
                "at": entry.at,
            }
            break
    return {
        **proposal.to_state(),
        "current_target_digest": current_target_digest,
        "target_stale": stale,
        "still_current": still_current,
        "excerpt": excerpt_of(proposal, note_text),
        "attributed": proposal.attributed,
        "accepted_by": accepted_by,
    }
