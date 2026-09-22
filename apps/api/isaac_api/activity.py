"""THE APPEND-ONLY EXPERIMENT ACTIVITY / AUDIT HISTORY — one immutable row per act.

WHAT THIS IS
============
``DEC-44`` (``docs/superpowers/plans/ISAAC_PRODUCT_DECISIONS.md``) makes a durable
Experiment Activity / Audit History a product requirement, recording *actor, action,
object, field, before, after, timestamp* and *source channel*. This module is the
model and the write helper for exactly that. :mod:`isaac_api.activity_history` is
the READ path, and the split is ``revision_history.py``'s split for
``revision_history.py``'s reason — ``DEC-44`` names it as the precedent to reuse
rather than re-invent.

WHY THE CHANGE FEED COULD NOT BE EXTENDED INTO THIS
===================================================
``change_feed.py``'s own first sentence is *"A BOUNDED, CURSOR-PAGED STATE FEED —
deliberately not an event log"*, and it publishes the three properties that make it
unusable here rather than leaving them to be discovered:

* **it COALESCES** — ten edits to one run between two polls are ONE entry, so a
  caller "cannot count changes, cannot reconstruct intermediate values, and cannot
  learn the order in which two fields of the same run were written". An audit log's
  whole job is the thing that sentence rules out;
* it carries **no actor**, **no before/after pair** and **no channel**, because it
  is a projection of where each entity stands *now*;
* it **cannot report deletions**.

So this is a separate append-only model, not an extension of the feed. Whether the
feed should additionally serve an ``activity`` *kind* is a different question and is
answered NO — see :data:`WHY_NO_CHANGE_FEED_KIND`.

WHERE IT IS STORED, AND WHY THAT IS NOT A MIGRATION
===================================================
At :data:`ACTIVITY_STATE_KEY` — a new top-level key in the experiment's state
document, BESIDE ``notes`` and ``proposals`` and deliberately **NOT** inside
``draft``. This is ``proposals.STATE_KEY``'s location for ``proposals.STATE_KEY``'s
reasons, and the ledger row ``ACT-001`` that says this model *"Needs migration
``0006``"* is **answered rather than obeyed**: it does not.

``CLAUDE.md`` §15's application-side scope extension of 2026-08-29 records that
persistent ingestion proposals added **no table** *deliberately*, because that same
section documents **four** separate occasions on which a table reached
``db_write.OWNED_TABLES`` before any committed sentence named it — *"and a fifth is
avoidable by not needing one"*. It also states the mechanical consequence: *"a
feature that needed ``0006`` would be a feature that does not work until an operator
acts, which is a hard stop this authorization does not lift."* An activity history
that only exists once somebody applies a migration is an activity history that
records nothing in the deployment that has it today.

``db_write.OWNED_TABLES`` IS UNCHANGED, no migration file is added, and
``Experiment.from_state`` reads every optional key with ``.get`` and a default — so a
document written before activity existed hydrates to an EMPTY history rather than
raising, and needs no backfill and no operator act.

**The disclosed cost, stated rather than discovered:** an event is durable exactly
where the experiment document is durable and no more. The document is rewritten whole
on every save, so a very long history makes that document larger; that is the same
cost runs, notes and proposals each already disclose, and the same fix (contract §8
D7's relational rows) applies to all four at once.

AUTHORIZATION BASIS
===================
* ``CLAUDE.md`` §15, the *APPLICATION-SIDE SCOPE EXTENSION — PROJECT OWNER,
  2026-08-29*, which authorizes *"persistent ingestion proposals and the durable
  contract they need"* and whose own ``NO NEW TABLE IS ADDED`` paragraph states that
  *"the persistence LOCATION was already covered by the 2026-08-07 lift's 'app-owned
  tables for experiments and their normal application state'; it is the FEATURE that
  needed authorizing, and a slice should cite that sentence for the location rather
  than re-argue it."* This module takes that instruction literally: the location is
  cited, not re-argued.
* ``DEC-44``, which makes the Activity History a confirmed product requirement and
  names the two precedents to reuse.
* ``DEC-45``, which requires a **stable canonical principal**, a **trust basis
  recorded beside every stamped actor**, and a **channel on every recorded act** —
  *"``DEC-44``'s event model must carry all three from day one, because retrofitting
  an actor onto an append-only history is not possible."* :class:`ActivityEvent`
  carries all three as REQUIRED fields.

WHAT IS DELIBERATELY NOT BUILT HERE
===================================
``ACT-005`` — populating :attr:`ActivityEvent.actor` from a trusted boundary — is
externally blocked (``EXT-01``) and is **not** built. Nothing in this module reads a
request, a header, or a body: the only way to a named actor is
:func:`actor_from_identity`, which takes an already-settled
:class:`~isaac_api.identity.RequestIdentity` and returns
:data:`ACTOR_UNATTRIBUTED` on every tier this build can produce. A forwarded
edge header can therefore never become an actor, which is
``docs/identity-trust-contract.md`` §7 and ``DEC-45``'s second clause enforced by
construction rather than by review.

**This module deliberately does not SPELL any edge header's name**, and the reason is
mechanical rather than stylistic: ``test_identity_trust.test_no_backend_module_names_an_identity_header``
scans every backend module for the edge prefix and fails on any file except
:mod:`isaac_api.identity`. ``record_attribution.py``'s own docstring records that
guard catching ITS first draft doing exactly this.

*This module's first draft named the prefix in a docstring too, and the guard did
NOT catch it — it was removed before the test was ever run, by reading the guard
rather than by failing it. The distinction is worth keeping: a defect a human
noticed is not evidence that the control works, and this repository has been caught
reporting the two as one thing.*

The guard is a text scan and so is easy to satisfy dishonestly; satisfying it
honestly means the names live in one place and every other module points at it —
which is also what stops a reader here from concluding that this module has any
business with headers. It has none.

THREE ACTS THAT RECORD NOTHING, NAMED RATHER THAN LEFT AS A GAP TO BE DISCOVERED
================================================================================
``ACT-002`` says "every write path", and three of them record no event. Each has a
reason, and none of them is "it was not worth it".

**CREATE.** ``workspace.create_experiment`` persists through ``Experiment.save()``,
not ``save_versioned()`` — correctly, because a brand-new record has no prior
signature to compare against — and a staged event is committed only by
``save_versioned``. It is also unnecessary: ``created_utc`` is on the record itself,
so *when this record came into existence* is already available to every reader of the
history without a row asserting it. There is deliberately no
``ACTION_EXPERIMENT_CREATED``.

**DISCARD** (``POST /api/experiments/{id}/discard``) **and the workspace RESET**
(``POST /api/demo/reset``). Both destroy the experiment document, and the history
lives INSIDE that document — so the only place this design can write the row is the
thing being deleted. Recording it anywhere else means a table, which is exactly the
``0006`` this module's authorization does not lift. There is deliberately no
``ACTION_EXPERIMENT_DISCARDED``: a constant with no write site is a verb a reader
would go looking for rows of.

**THIS IS A REAL LIMITATION AND IT IS THE SAME ONE** ``change_feed.DELETION_LIMITATION``
publishes about itself. It is stated here so a future slice inherits the measurement
rather than the surprise: a deletion is the one act neither the feed nor this history
can report, and closing it needs a store outside the record — a decision, not an
extension. ``ACTION_RUN_REMOVED`` is NOT in this class: a run's removal is recorded,
because the record it belongs to survives it.

APPEND-ONLY, AND WHAT THAT MEANS MECHANICALLY
=============================================
:class:`ActivityEvent` is ``frozen=True, slots=True``. ``slots=True`` is load-bearing
rather than a micro-optimisation, for the reason ``notes.Note`` gives: it removes the
instance ``__dict__``, so no attribute can be attached after construction, and
``object.__setattr__`` on a name that is not a declared field raises
``AttributeError`` instead of quietly succeeding.

**There is no revise function, no replace function and no delete function anywhere in
this module or in :mod:`isaac_api.activity_history`.** ``notes.py`` needs
:func:`~isaac_api.notes.revise_note` because a note has a review lifecycle; an
activity event has none — it records one act that already happened, and a recorded
act cannot later become a different act. So the honest shape is not "a guarded
mutator" but *no mutator at all*, and :data:`IMMUTABLE_EVENT_FIELDS` names every
field for that reason rather than a capture-shaped subset.

INERT TO EXPORT, STRUCTURALLY
=============================
An event is not in ``draft``, so it is invisible to ``export.transform``, absent from
``submissions.content_signature`` (computed from export units), and absent from every
run's ``resolved_run_draft`` — because nothing that exports looks here.
``src/isaac_records/``, ``schema/`` and ``apps/api/isaac_api/export.py`` are untouched
by this slice. That is ``proposals``' invariant **I2** argument, and it is structural
rather than asserted: there is no code path from an export to this key.

AND IT IS OUTSIDE ``_authoritative_signature`` TOO, WHICH IS THE OPPOSITE CHOICE
FROM NOTES AND PROPOSALS
========================================================================
Notes and proposals are IN that signature because capturing or accepting one is
itself an authoritative change. An activity event is not: it is
``answer_log``'s class — *"an audit trail, not scientific state"*, which
``workspace._authoritative_signature`` already excludes by name.

Including it would have broken the byte-stable no-op that the whole version contract
rests on. ``save_versioned`` writes nothing when the signature is unchanged, so an
event appended BEFORE that comparison would make every idempotent re-entry look like
a change, bump ``rev``, invalidate every held ETag and fire a change-feed event — for
an act that did nothing.

Excluding it has its own hazard, and it is handled structurally rather than by
per-site discipline: an event appended to a save that turns out to be a no-op would be
silently dropped. So an event is never appended directly. :meth:`Experiment.record_activity`
stages it, and ``save_versioned`` commits the staged events **only on the write
branch**, minting :attr:`ActivityEvent.seq` there. A no-op therefore records nothing
and advances no sequence, and no call site can forget to undo a speculative append —
``answer_log``'s ``pop()`` discipline made unnecessary rather than repeated.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

__all__ = [
    "ABSENT",
    "ACTION_ARCHIVE_ATTACHED",
    "ACTION_ASSET_ADDED",
    "ACTION_ASSET_REMOVED",
    "ACTION_ASSET_UPDATED",
    "ACTION_CONFLICT_DECISION_RECORDED",
    "ACTION_CONVENTION_RULE_RECORDED",
    "ACTION_EXPERIMENT_MOVED",
    "ACTION_EXPERIMENT_RENAMED",
    "ACTION_FIELD_ANSWERED",
    "ACTION_FIELD_CORRECTED",
    "ACTION_NOTE_CAPTURED",
    "ACTION_NOTE_REVIEWED",
    "ACTION_PROPOSAL_CREATED",
    "ACTION_PROPOSAL_REVIEWED",
    "ACTION_RECORD_EXPORTED",
    "ACTION_RUN_ADDED",
    "ACTION_RUN_OVERRIDE_CLEARED",
    "ACTION_RUN_OVERRIDE_RECORDED",
    "ACTION_RUN_REMOVED",
    "ACTION_RUN_UPDATED",
    "ACTION_TRANSCRIPT_FINALIZED",
    "ACTIVITY_ACTIONS",
    "ACTIVITY_CHANNELS",
    "ACTIVITY_OBJECT_TYPES",
    "ACTIVITY_STATE_KEY",
    "ACTOR_UNATTRIBUTED",
    "ActivityEvent",
    "Absent",
    "CHANNEL_HISTORICAL_IMPORT",
    "CHANNEL_MCP",
    "CHANNEL_SYSTEM",
    "CHANNEL_WEB",
    "CHANNELS_WITHOUT_A_WRITE_SITE",
    "IMMUTABLE_EVENT_FIELDS",
    "OBJECT_ARCHIVE",
    "OBJECT_ASSET",
    "OBJECT_CONFLICT",
    "OBJECT_CONVENTION_RULE",
    "OBJECT_EXPERIMENT",
    "OBJECT_FIELD",
    "OBJECT_IMPORT",
    "OBJECT_NOTE",
    "OBJECT_PROPOSAL",
    "OBJECT_RECORD",
    "OBJECT_RUN",
    "TRUST_BASIS_UNATTRIBUTED",
    "UnsupportedActivityEvent",
    "WHY_NO_CHANGE_FEED_KIND",
    "actor_from_identity",
    "ambient_channel",
    "channel_scope",
    "new_event",
    "sorted_events",
]


#: The experiment state document's top-level key. BESIDE ``notes`` and
#: ``proposals``, and deliberately NOT inside ``draft`` — see the module docstring
#: for why that placement is what makes "inert to export" structural.
ACTIVITY_STATE_KEY = "activity"


# --------------------------------------------------------------------------
# The channel — ``DEC-44``'s fourth column and ``ACT-002``'s whole subject
# --------------------------------------------------------------------------

#: An act reached through this application's own HTTP API.
#:
#: **THE WORD PROMISES MORE THAN IT DELIVERS, AND THAT IS SAID HERE RATHER THAN
#: LEFT TO A READER TO ASSUME.** It does NOT mean "a person in a browser". The
#: browser client, a ``curl``, an OpenAPI consumer and a script are
#: indistinguishable at the route — nothing in a request separates them — and
#: ``DEC-44``'s vocabulary is exactly four values with no term for "some other HTTP
#: caller", so inventing a fifth would be a change to a committed decision rather
#: than a fix. ``web`` is the widest of the four that is TRUE of every request that
#: reaches it. See ``routes._api_channel``.
CHANNEL_WEB = "web"

#: An agent acting through the remote MCP server. Established by
#: :func:`channel_scope`, which ``mcp/client.py`` enters around every in-process
#: call — NEVER by a header, which a caller outside this process could forge.
CHANNEL_MCP = "mcp"

#: An act performed while adding historical/archive material to a record.
CHANNEL_HISTORICAL_IMPORT = "historical_import"

#: The application itself, with no external caller to name: seeding, materialising
#: derived units, a reset, a migration-shaped repair.
#:
#: **IT IS ALSO THE HONEST FALLBACK, AND THAT IS DELIBERATE RATHER THAN LAZY.**
#: ``ACT-002`` says the channel is knowable at every write site today, and it is —
#: but "knowable" is a property of the sites that exist now. A site that genuinely
#: cannot say which external surface reached it records ``system`` and says so in a
#: comment at the site. It must NOT record ``web``: guessing the most common
#: channel would put a false fact in an audit log, which is worse than recording a
#: true but uninformative one.
CHANNEL_SYSTEM = "system"

#: The bounded set. A channel outside it is REFUSED at construction, not coerced —
#: ``DEC-44`` enumerates exactly these four, and an audit row carrying a fifth
#: describes a surface this application does not have.
ACTIVITY_CHANNELS: frozenset[str] = frozenset(
    {CHANNEL_WEB, CHANNEL_MCP, CHANNEL_HISTORICAL_IMPORT, CHANNEL_SYSTEM}
)

#: CHANNELS IN THE VOCABULARY THAT NO WRITE SITE IN THIS BUILD RECORDS — and why.
#:
#: **``system`` IS HERE, MEASURED 2026-09-22, and this map is the answer to
#: ``docs/session-closure-2026-09-18.md`` §8's residue** ("``CHANNEL_SYSTEM`` has no write
#: site, so ``by_channel.system`` is permanently 0"). Two ways to close it were weighed:
#:
#: * RECORD A SYSTEM EVENT SOMEWHERE — rejected, because no legitimate one exists today.
#:   The application-originated acts this build performs are creating a record (not
#:   recorded — see "THREE ACTS THAT RECORD NOTHING" above), materialising a worked
#:   example (``save()``, a brand-new document with nothing to record against) and the
#:   workspace reset (it destroys the document the history lives in). Inventing an
#:   event to give the zero company would put a false row in an audit log, which is the
#:   one thing ``CHANNEL_SYSTEM``'s own comment forbids.
#: * SAY THE ZERO IS STRUCTURAL — adopted. ``DEC-44`` enumerates four channels and that
#:   decision is unchanged, so ``system`` stays in :data:`ACTIVITY_CHANNELS`; what
#:   changes is that every served vocabulary now carries this map beside it, so a
#:   surface can say *"no act in this build is recorded through this channel"* instead of
#:   rendering a ``0`` that reads as a measurement of inactivity.
#:
#: ``test_activity_channel_guard.py`` fails if a write site starts recording one of these
#: channels while it is still listed here, so the claim cannot go stale silently.
CHANNELS_WITHOUT_A_WRITE_SITE: dict[str, str] = {
    CHANNEL_SYSTEM: (
        "Reserved for acts the application performs with no external caller. No write "
        "path in this build records one — the application-originated acts it has "
        "(creating a record, materialising a worked example, resetting the workspace) "
        "either write a brand-new document or destroy the one the history lives in — so "
        "a count of zero here is structural, not a measurement of inactivity."
    ),
}

#: The process-wide ambient channel, or ``None`` when nothing established one.
#:
#: A ``ContextVar`` RATHER THAN A HEADER, AND THE DIFFERENCE IS THE WHOLE POINT.
#: ``mcp/client.py`` reaches the routes over ``httpx.ASGITransport`` **in this
#: process** (``mcp/transport.py``: *"The tools call ISAAC in-process"*), and
#: ``httpx``'s ``ASGITransport.handle_async_request`` does ``await self.app(scope,
#: receive, send)`` — a direct await in the same context — so a variable set by the
#: MCP client is visible to the route handler and to nothing else.
#:
#: A header would have been forgeable. ``docs/identity-trust-contract.md`` §2 (Q4)
#: records that the Service is a plain ClusterIP with no NetworkPolicy, so any
#: in-cluster pod can send this application whatever headers it likes; an
#: ``X-Isaac-Channel: mcp`` would let an arbitrary caller write a false line into an
#: audit log. That is not an authorization hole — a channel authorizes nothing —
#: but a false audit row is exactly the defect an audit log exists to prevent, and
#: ``DEC-45``'s *"no authorization decision may ever be derived from an untrusted
#: forwarded header"* is the same instinct one step out.
#:
#: ``None`` IS NOT A CHANNEL. Readers go through :func:`ambient_channel`, which
#: takes the caller's own default, so there is no path by which an unset variable
#: becomes a silent ``web``.
_AMBIENT_CHANNEL: ContextVar[str | None] = ContextVar(
    "isaac_activity_channel", default=None
)


@contextmanager
def channel_scope(channel: str) -> Iterator[None]:
    """Establish the ambient channel for the duration of the block.

    Set/reset with the token, so nesting is exact and a leak across requests is not
    representable: the variable is restored to whatever it held on entry rather than
    to ``None``.

    The channel is validated here as well as at construction. A caller entering an
    unknown scope should fail at the ``with`` statement, where the mistake is, and
    not later at the one write site that happens to record an event.
    """
    if channel not in ACTIVITY_CHANNELS:
        raise UnsupportedActivityEvent(
            f"unknown activity channel {channel!r}; allowed: {sorted(ACTIVITY_CHANNELS)}"
        )
    token = _AMBIENT_CHANNEL.set(channel)
    try:
        yield
    finally:
        _AMBIENT_CHANNEL.reset(token)


def ambient_channel(default: str) -> str:
    """The established channel, or ``default``.

    THE DEFAULT IS THE CALLER'S AND HAS NO DEFAULT OF ITS OWN, on purpose. A
    signature of ``ambient_channel(default=CHANNEL_WEB)`` would let a future write
    site record ``web`` by forgetting an argument, which is precisely the guess
    :data:`CHANNEL_SYSTEM` exists to make unnecessary. Making the parameter required
    forces each site to state, in its own source, what it believes reached it.
    """
    if default not in ACTIVITY_CHANNELS:
        raise UnsupportedActivityEvent(
            f"unknown activity channel {default!r}; allowed: {sorted(ACTIVITY_CHANNELS)}"
        )
    established = _AMBIENT_CHANNEL.get()
    return established if established is not None else default


# --------------------------------------------------------------------------
# The actor — ``DEC-45``, and ``ACT-005`` deliberately left unbuilt
# --------------------------------------------------------------------------

#: The actor recorded when no trusted boundary named one. A LITERAL, not ``None``:
#: an audit row whose actor is absent is indistinguishable from an audit row a
#: reader forgot to render, and ``ACT-003`` requires the history to *"render
#: ``unattributed`` honestly rather than hiding entries that lack an actor"*.
ACTOR_UNATTRIBUTED = "unattributed"

#: The trust basis that travels with :data:`ACTOR_UNATTRIBUTED`.
#:
#: **REUSED FROM** ``submissions.TRUST_BASIS_UNATTRIBUTED`` rather than minted here:
#: it is the same fact with the same name, and that module already explains at length
#: why it is deliberately NOT a member of ``identity.RECOGNISED_TRUST_BASES`` (that
#: set is what a ``HumanActor`` may CLAIM, and "nobody" is not a person). Two
#: spellings of one value is how a vocabulary drifts.
TRUST_BASIS_UNATTRIBUTED = "unattributed"


def actor_from_identity(identity: Any) -> tuple[str, str]:
    """``(actor, actor_trust_basis)`` for a settled request identity.

    **THIS IS THE ``ACT-005`` SEAM, AND ``ACT-005`` IS NOT BUILT.** It is named
    rather than left implicit so a future slice has one place to change, and so a
    reader can see that the unattributed answer is a CONSEQUENCE of the deployment
    rather than a shortcut taken here.

    It reads nothing from a request. Its argument is an already-settled
    :class:`~isaac_api.identity.RequestIdentity`, and the only value it will accept as
    an actor is one carried on an :class:`~isaac_api.identity.HumanActor` — which
    ``identity.py`` can only mint from a verifier that vouched for the request. No
    verifier in this build mints
    ``identity.TRUST_BASIS_VERIFIED_EDGE_ASSERTION``, and neither shipped verifier
    reads a request at all, so on every default deployment and on the hosted pod this
    returns ``(unattributed, unattributed)``. A forged forwarded header cannot reach
    this function's return value by any path.

    ``None`` is accepted and answers unattributed, because most write sites in this
    build have no identity dependency at all and adding one to each would be
    ``ACT-005``'s work, not this slice's.

    THE TRUST BASIS IS TAKEN FROM THE ACTOR, NEVER ASSUMED. ``DEC-45`` requires *"a
    trust basis recorded beside every stamped actor"*, and a basis this function chose
    for itself would be a claim about how the name was established made by something
    that did not establish it.
    """
    if identity is None:
        return ACTOR_UNATTRIBUTED, TRUST_BASIS_UNATTRIBUTED
    human = getattr(identity, "human", None)
    if human is None:
        return ACTOR_UNATTRIBUTED, TRUST_BASIS_UNATTRIBUTED
    subject = getattr(human, "subject", None)
    basis = getattr(human, "trust_basis", None)
    if not isinstance(subject, str) or not subject.strip():
        return ACTOR_UNATTRIBUTED, TRUST_BASIS_UNATTRIBUTED
    if not isinstance(basis, str) or not basis.strip():
        # A name with no basis is exactly the shape the identity seam exists to
        # refuse. Refusing it here too costs nothing and means a future verifier
        # cannot produce a half-attributed row by omission.
        return ACTOR_UNATTRIBUTED, TRUST_BASIS_UNATTRIBUTED
    return subject, basis


# --------------------------------------------------------------------------
# The bounded action and object vocabularies
# --------------------------------------------------------------------------

ACTION_EXPERIMENT_RENAMED = "experiment_renamed"
ACTION_EXPERIMENT_MOVED = "experiment_moved_to_folder"
ACTION_FIELD_ANSWERED = "field_answered"
ACTION_FIELD_CORRECTED = "field_corrected"
ACTION_RUN_ADDED = "run_added"
ACTION_RUN_UPDATED = "run_updated"
ACTION_RUN_REMOVED = "run_removed"
ACTION_RUN_OVERRIDE_RECORDED = "run_override_recorded"
ACTION_RUN_OVERRIDE_CLEARED = "run_override_cleared"
ACTION_NOTE_CAPTURED = "note_captured"
ACTION_NOTE_REVIEWED = "note_reviewed"
ACTION_PROPOSAL_CREATED = "proposal_created"
ACTION_PROPOSAL_REVIEWED = "proposal_reviewed"
ACTION_TRANSCRIPT_FINALIZED = "transcript_finalized"
ACTION_CONFLICT_DECISION_RECORDED = "conflict_decision_recorded"
ACTION_ASSET_ADDED = "asset_added"
ACTION_ASSET_UPDATED = "asset_updated"
ACTION_ASSET_REMOVED = "asset_removed"
ACTION_RECORD_EXPORTED = "record_exported"
ACTION_ARCHIVE_ATTACHED = "archive_attached"
#: A scientist confirmed a convention rule on this record (2026-09-22,
#: :mod:`isaac_api.convention_rules`) — a profile binding, a conflict resolution or a
#: channel assignment. The rule itself is content the record holds; this row records
#: that the act happened, through which channel, and by whom (honestly: unattributed).
ACTION_CONVENTION_RULE_RECORDED = "convention_rule_recorded"

#: The bounded verb vocabulary. **NOT free text**, and the refusal is the reason:
#: a history whose ``action`` a caller may spell freely cannot be grouped, counted
#: or filtered without a normalisation step that would have to guess.
#:
#: Adding a verb here is a deliberate act, and the guard in
#: ``test_activity_channel_guard.py`` is what makes it one: a new write path that
#: records nothing fails a test, so the vocabulary grows with the write sites rather
#: than drifting behind them.
ACTIVITY_ACTIONS: frozenset[str] = frozenset(
    {
        ACTION_EXPERIMENT_RENAMED,
        ACTION_EXPERIMENT_MOVED,
        ACTION_FIELD_ANSWERED,
        ACTION_FIELD_CORRECTED,
        ACTION_RUN_ADDED,
        ACTION_RUN_UPDATED,
        ACTION_RUN_REMOVED,
        ACTION_RUN_OVERRIDE_RECORDED,
        ACTION_RUN_OVERRIDE_CLEARED,
        ACTION_NOTE_CAPTURED,
        ACTION_NOTE_REVIEWED,
        ACTION_PROPOSAL_CREATED,
        ACTION_PROPOSAL_REVIEWED,
        ACTION_TRANSCRIPT_FINALIZED,
        ACTION_CONFLICT_DECISION_RECORDED,
        ACTION_ASSET_ADDED,
        ACTION_ASSET_UPDATED,
        ACTION_ASSET_REMOVED,
        ACTION_RECORD_EXPORTED,
        ACTION_ARCHIVE_ATTACHED,
        ACTION_CONVENTION_RULE_RECORDED,
    }
)

OBJECT_EXPERIMENT = "experiment"
OBJECT_RUN = "run"
OBJECT_FIELD = "field"
OBJECT_NOTE = "note"
OBJECT_PROPOSAL = "proposal"
OBJECT_ASSET = "asset"
OBJECT_ARCHIVE = "archive"
OBJECT_IMPORT = "import"
OBJECT_RECORD = "record"
OBJECT_CONFLICT = "conflict"
OBJECT_CONVENTION_RULE = "convention_rule"

#: What kind of thing the act was performed ON. Bounded for
#: :data:`ACTIVITY_ACTIONS`' reason.
ACTIVITY_OBJECT_TYPES: frozenset[str] = frozenset(
    {
        OBJECT_EXPERIMENT,
        OBJECT_RUN,
        OBJECT_FIELD,
        OBJECT_NOTE,
        OBJECT_PROPOSAL,
        OBJECT_ASSET,
        OBJECT_ARCHIVE,
        OBJECT_IMPORT,
        OBJECT_RECORD,
        OBJECT_CONFLICT,
        OBJECT_CONVENTION_RULE,
    }
)


class UnsupportedActivityEvent(ValueError):
    """An event that cannot be recorded without inventing something."""


# --------------------------------------------------------------------------
# "there was none" is not "it was null"
# --------------------------------------------------------------------------


class Absent:
    """The sentinel meaning *there was no value here at all*.

    **THE DISTINCTION IS NOT COSMETIC AND IT IS THE REASON THIS CLASS EXISTS.**
    ``None`` is a value a field can legitimately hold in a draft — ``notes.py``'s
    ``_clean_optional`` makes exactly this point about ``None`` versus ``""`` — so an
    audit row that spelled both "the field did not exist" and "the field held null"
    as ``None`` would be unable to tell a scientist whether their edit CREATED a
    value or CHANGED one to null. Those are different acts.

    A singleton with a stable ``repr`` and a hard ``False`` truthiness, so a site
    that writes ``if before:`` gets the same answer for absent and for a falsy
    value and therefore cannot accidentally branch on the distinction without
    naming it.
    """

    __slots__ = ()
    _instance: "Absent | None" = None

    def __new__(cls) -> "Absent":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "ABSENT"

    def __bool__(self) -> bool:
        return False


#: The one instance. Compare with ``is ABSENT``.
ABSENT = Absent()


def _value_envelope(value: Any) -> dict:
    """The WIRE form of a before/after slot: ``{present, value}``.

    **A NESTED ENVELOPE RATHER THAN A SIBLING BOOLEAN FLAG**, and the choice is
    argued because the flat form is the obvious first draft. ``{"before": null,
    "before_present": false}`` is equally expressive and is one forgotten key away
    from being wrong: a consumer that reads ``before`` and never learns that
    ``before_present`` exists silently reads "absent" as "null", which is the exact
    conflation :class:`Absent` was introduced to end. An envelope cannot be read
    without meeting ``present``.
    """
    if value is ABSENT:
        return {"present": False, "value": None}
    return {"present": True, "value": value}


def _value_from_envelope(raw: Any) -> Any:
    """Read a before/after slot back. A slot this build cannot read is ABSENT.

    A wrong-typed or missing envelope reads as :data:`ABSENT` rather than raising,
    and that is ``CLAUDE.md`` §11's rule applied at the leaf: a malformed
    **persisted** value must be READ, not refused, because the reader did nothing
    wrong and their history must not vanish. ``ABSENT`` is the fail-closed reading —
    it claims nothing about a value — where ``None`` would assert that the field
    held null.
    """
    if not isinstance(raw, dict):
        return ABSENT
    if raw.get("present") is not True:
        return ABSENT
    return raw.get("value")


#: Every field of a recorded event, which is to say: all of them.
#:
#: ``notes.IMMUTABLE_NOTE_FIELDS`` is a capture-shaped SUBSET because a note has a
#: review lifecycle and some of its fields are revisable. An activity event has no
#: lifecycle — it records an act that already happened — so the honest set is the
#: whole set, and there is no ``revise_event`` for it to guard. It is published so a
#: test can assert the two facts together: that the set is total, and that no
#: mutator exists.
IMMUTABLE_EVENT_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "experiment_id",
        "seq",
        "recorded_utc",
        "actor",
        "actor_trust_basis",
        "channel",
        "action",
        "object_type",
        "object_id",
        "run_id",
        "field_path",
        "before",
        "after",
        "source_ref",
    }
)


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """ONE act, recorded once, never revised and never removed.

    ``slots=True`` removes the instance ``__dict__``, so nothing can be attached to
    a recorded event after construction; ``frozen=True`` refuses assignment to a
    declared field. Together with the absence of any mutator in this module, that is
    what "append-only" means here mechanically rather than aspirationally.
    """

    id: str
    experiment_id: str
    #: THE DURABLE PER-EXPERIMENT MONOTONIC POSITION, starting at 1.
    #:
    #: NOT the record's ``rev``, and the difference is arithmetic rather than
    #: stylistic: several events can be recorded by ONE save, so ``rev`` is not
    #: injective over events and could not order two acts inside one request.
    #: ``Run.changed_at_rev`` and ``Experiment.proposal_change_revs`` are the
    #: change feed's coordinate and answer a different question — *where does this
    #: entity stand now* — which is the question ``DEC-44`` measured the feed
    #: unable to replace this with.
    #:
    #: Minted by ``save_versioned`` on the WRITE branch only, as
    #: ``max(existing) + 1``, so a byte-stable no-op never advances it and no
    #: number is ever burned by a save that did not happen. ``(seq, id)`` is a
    #: total order.
    seq: int
    recorded_utc: str
    #: :data:`ACTOR_UNATTRIBUTED` unless a trusted boundary named somebody. Never
    #: guessed, never read from a header, never defaulted to a request's claim.
    actor: str
    #: ``DEC-45``: the basis travels BESIDE the actor, always, so a reader can tell
    #: a verified name from a fixture one without a second lookup.
    actor_trust_basis: str
    #: One of :data:`ACTIVITY_CHANNELS`. ``ACT-002``.
    channel: str
    #: One of :data:`ACTIVITY_ACTIONS`.
    action: str
    #: One of :data:`ACTIVITY_OBJECT_TYPES`.
    object_type: str
    #: The id of the thing acted on. The experiment's own id for a record-level act
    #: — never blank, because an audit row that names no object is unaddressable.
    object_id: str
    #: The run this act belongs to WHEN IT BELONGS TO ONE, ``None`` otherwise.
    #: ``notes.Note.run_id``'s rule: "the only run that happens to exist" is an
    #: inference about the science, not a stored fact.
    run_id: str | None = None
    #: The field path this act touched, when it touched one. ``None`` otherwise.
    field_path: str | None = None
    #: The prior value, or :data:`ABSENT` when there was none. See :class:`Absent`.
    before: Any = ABSENT
    #: The new value, or :data:`ABSENT` when the act removed one.
    after: Any = ABSENT
    #: A provenance reference — a note id, a proposal id, an import id, a digest.
    #: ``None`` when the act cites nothing; never a composed sentence.
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise UnsupportedActivityEvent(
                "an activity event must have an id; an unaddressable event cannot be cited"
            )
        if not isinstance(self.experiment_id, str) or not self.experiment_id:
            raise UnsupportedActivityEvent(
                "an activity event must name the experiment it belongs to"
            )
        # `bool` IS REFUSED EXPLICITLY, before the `int` check, because `True` IS an
        # `int` in Python and would otherwise become sequence position 1 — a real
        # position, silently colliding with the first genuine event.
        if isinstance(self.seq, bool) or not isinstance(self.seq, int):
            raise UnsupportedActivityEvent(
                f"seq must be an integer position, not {type(self.seq).__name__}"
            )
        if self.seq < 1:
            raise UnsupportedActivityEvent(
                f"seq must be >= 1; got {self.seq}. Position 0 would sit below the "
                "start of the order, where no reader would report it."
            )
        if not isinstance(self.recorded_utc, str) or not self.recorded_utc:
            raise UnsupportedActivityEvent(
                "an activity event must record when it happened"
            )
        if not isinstance(self.actor, str) or not self.actor.strip():
            raise UnsupportedActivityEvent(
                "an activity event must name an actor; use ACTOR_UNATTRIBUTED when "
                "no trusted boundary established one. A blank actor is a name a "
                "reader cannot tell from a rendering bug."
            )
        if not isinstance(self.actor_trust_basis, str) or not self.actor_trust_basis.strip():
            raise UnsupportedActivityEvent(
                "an activity event must record what vouched for its actor (DEC-45)"
            )
        if self.actor == ACTOR_UNATTRIBUTED and self.actor_trust_basis != TRUST_BASIS_UNATTRIBUTED:
            # The pairing the database CHECK on `isaac_submissions` already enforces
            # for submission rows, applied here in the model for the same reason:
            # "nobody" carrying a real basis would read as an attributed act.
            raise UnsupportedActivityEvent(
                f"an unattributed actor must carry the {TRUST_BASIS_UNATTRIBUTED!r} "
                f"trust basis, not {self.actor_trust_basis!r}"
            )
        if self.actor != ACTOR_UNATTRIBUTED and self.actor_trust_basis == TRUST_BASIS_UNATTRIBUTED:
            raise UnsupportedActivityEvent(
                f"actor {self.actor!r} carries the unattributed trust basis; a name "
                "nothing vouched for is the one shape this seam exists to refuse"
            )
        if self.channel not in ACTIVITY_CHANNELS:
            raise UnsupportedActivityEvent(
                f"unknown activity channel {self.channel!r}; allowed: "
                f"{sorted(ACTIVITY_CHANNELS)}"
            )
        if self.action not in ACTIVITY_ACTIONS:
            raise UnsupportedActivityEvent(
                f"unknown activity action {self.action!r}; allowed: "
                f"{sorted(ACTIVITY_ACTIONS)}"
            )
        if self.object_type not in ACTIVITY_OBJECT_TYPES:
            raise UnsupportedActivityEvent(
                f"unknown activity object type {self.object_type!r}; allowed: "
                f"{sorted(ACTIVITY_OBJECT_TYPES)}"
            )
        if not isinstance(self.object_id, str) or not self.object_id:
            raise UnsupportedActivityEvent(
                "an activity event must name the object it acted on"
            )
        for label in ("run_id", "field_path", "source_ref"):
            value = getattr(self, label)
            if value is None:
                continue
            if not isinstance(value, str):
                raise UnsupportedActivityEvent(
                    f"{label} must be a string or absent, not {type(value).__name__}"
                )
            if not value.strip():
                # `notes._clean_optional`'s refusal, for its reason: absent is a
                # meaning here, and folding a blank into it would discard the fact
                # that a caller supplied something.
                raise UnsupportedActivityEvent(
                    f"{label} was supplied as blank; omit it rather than sending an "
                    "empty string, which would be stored as though something were there"
                )

    # --- the constants that make "an event is not a value" survive the wire ---

    @property
    def is_field_value(self) -> bool:
        """Always ``False``. An event RECORDS that a value changed; it is not one.

        A read-only property with no field behind it, which is
        ``notes.Note``'s arrangement for ``notes.Note``'s reasons:
        ``dataclasses.replace`` raises, the frozen ``__setattr__`` refuses, and
        ``object.__setattr__`` raises ``AttributeError`` because ``slots=True``
        declares no such slot. Serialised by :meth:`to_state` so the guarantee
        crosses the JSON boundary instead of stopping at it.
        """
        return False

    @property
    def is_evidence(self) -> bool:
        """Always ``False``. An audit trail is not evidence about the science."""
        return False

    def to_state(self) -> dict:
        """The persistence AND wire shape — one function, so the two cannot drift."""
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "seq": self.seq,
            "recorded_utc": self.recorded_utc,
            "actor": self.actor,
            "actor_trust_basis": self.actor_trust_basis,
            "channel": self.channel,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "run_id": self.run_id,
            "field_path": self.field_path,
            "before": _value_envelope(self.before),
            "after": _value_envelope(self.after),
            "source_ref": self.source_ref,
            "is_field_value": self.is_field_value,
            "is_evidence": self.is_evidence,
        }

    @classmethod
    def from_state(cls, state: dict) -> "ActivityEvent":
        """Rehydrate one event. RAISES on a document it cannot represent honestly.

        ``notes.Note.from_state``'s posture and its reason: the only caller is
        ``workspace._hydrate_activity``, which CATCHES this and preserves the raw
        entry verbatim rather than dropping it. So raising here is not a route back
        to the whole-list 500 that ``CLAUDE.md`` §11's read-path rule was written
        for — nothing is lost, nothing is guessed, and the entry is counted and
        disclosed rather than rendered.
        """
        return cls(
            id=state.get("id"),  # type: ignore[arg-type]
            experiment_id=state.get("experiment_id"),  # type: ignore[arg-type]
            seq=state.get("seq"),  # type: ignore[arg-type]
            recorded_utc=state.get("recorded_utc"),  # type: ignore[arg-type]
            actor=state.get("actor"),  # type: ignore[arg-type]
            actor_trust_basis=state.get("actor_trust_basis"),  # type: ignore[arg-type]
            channel=state.get("channel"),  # type: ignore[arg-type]
            action=state.get("action"),  # type: ignore[arg-type]
            object_type=state.get("object_type"),  # type: ignore[arg-type]
            object_id=state.get("object_id"),  # type: ignore[arg-type]
            run_id=state.get("run_id"),
            field_path=state.get("field_path"),
            before=_value_from_envelope(state.get("before")),
            after=_value_from_envelope(state.get("after")),
            source_ref=state.get("source_ref"),
        )


def new_event(
    *,
    id: str,
    experiment_id: str,
    seq: int,
    recorded_utc: str,
    action: str,
    object_type: str,
    object_id: str,
    channel: str,
    actor: str = ACTOR_UNATTRIBUTED,
    actor_trust_basis: str = TRUST_BASIS_UNATTRIBUTED,
    run_id: str | None = None,
    field_path: str | None = None,
    before: Any = ABSENT,
    after: Any = ABSENT,
    source_ref: str | None = None,
) -> ActivityEvent:
    """Mint one event.

    ``channel`` IS KEYWORD-ONLY AND HAS NO DEFAULT, which is the mechanical half of
    ``ACT-002``: a write path that records an event without stating a channel does
    not compile — it raises ``TypeError`` at the call. The textual half (that a new
    write path records an event at all) is
    ``test_activity_channel_guard.py``'s job, because no signature can enforce it.

    ``actor``/``actor_trust_basis`` DO have defaults, and the pair is the honest one:
    nobody, vouched for by nothing. ``ACT-005`` will pass a real pair from
    :func:`actor_from_identity`; until then the default is the truth rather than a
    placeholder.
    """
    return ActivityEvent(
        id=id,
        experiment_id=experiment_id,
        seq=seq,
        recorded_utc=recorded_utc,
        actor=actor,
        actor_trust_basis=actor_trust_basis,
        channel=channel,
        action=action,
        object_type=object_type,
        object_id=object_id,
        run_id=run_id,
        field_path=field_path,
        before=before,
        after=after,
        source_ref=source_ref,
    )


def sorted_events(events: Iterable[ActivityEvent]) -> list[ActivityEvent]:
    """Canonical order: oldest first, by ``(seq, id)``.

    IT LIVES IN THE MODEL MODULE AND NOT IN THE READ MODULE, deliberately. The order
    is a property of the entity, and it is needed in two places that must not be able
    to disagree — ``workspace._activity_state_payload``, which decides the bytes on
    disk, and :mod:`isaac_api.activity_history`, which decides what a reader is
    handed. A second sort key would eventually page a reader past an event that the
    persisted order had put somewhere else.

    ``seq`` first because it IS the durable order; ``id`` second so the order is TOTAL
    even in the pathological case of a persisted document carrying two events at one
    position — which ``workspace._hydrate_activity`` deliberately does not prevent,
    because it de-duplicates on ``id`` and filing a real recorded act as unreadable to
    tidy a coordinate would lose more than it fixes. A non-total order would make
    paging non-deterministic, and a reader would see an event twice or not at all
    depending on nothing they could observe.

    **The timestamp is deliberately NOT in the key.** ``workspace._now_iso`` formats to
    whole seconds, so several events recorded in one save share one timestamp;
    ordering on it would be the exact whole-second-clock defect ``change_feed.py``'s
    docstring records having measured and replaced with a sequence.
    """
    return sorted(events, key=lambda e: (e.seq, e.id))


#: WHY THE CHANGE FEED DOES **NOT** SERVE AN ``activity`` KIND — the decision, its
#: arithmetic, and what a future slice would have to accept to reverse it.
#:
#: Published as a constant rather than left in a commit message because the obvious
#: next request is "surface activity through the feed", and the reason not to is a
#: measurement about ``change_feed.CURSOR_VERSION`` that is cheap to re-derive and
#: expensive to rediscover.
WHY_NO_CHANGE_FEED_KIND = """\
`change_feed.RECORD_COLLECTORS` keys `experiment`, `run`, `proposal`, `note` and
`CURSOR_VERSION` is 3. The sort key is `(changed_at_rev, kind, entity_id)` with
`kind` compared as a STRING, so `activity` sorts FIRST of the five —
`activity < experiment < note < proposal < run`.

A v3 cursor resting at `(R, "experiment", X)` is therefore ALREADY PAST every
position an activity event at that same rev would occupy. A build that read such a
cursor under v4 rules would walk forward from it and never report those events: not
late, never. That is exactly the arithmetic `CURSOR_VERSION`'s own comment writes out
for the `note` kind, and it forces `CURSOR_VERSION` 3 -> 4 and the REFUSAL (422
`malformed_cursor`) of every v3 cursor in flight.

That cost buys nothing here, and that is the decision rather than the caution:

* an activity event is IMMUTABLE, so "this entity is at a version later than your
  cursor" — the only thing the feed reports — is true of it exactly once, at birth.
  The feed's coalescing, which `DEC-44` measured as disqualifying for an audit log,
  would be harmless for an append-only stream; it is the VERSION BUMP that would be
  meaningless.
* every event is recorded inside the same save as the authoritative change it
  describes, so the feed ALREADY fires an `experiment`, `run`, `note` or `proposal`
  entry at that rev. A client that wants the new events has already been told to
  refetch, and `GET /api/experiments/{id}/activity?since_seq=` answers precisely and
  cheaply.
* so the feed would gain a kind that duplicates a signal it already sends, and pay
  for it by forcing every deployed client to resync.

TO REVERSE THIS, a slice must: bump `CURSOR_VERSION` to 4, refuse v3, extend
`RECORD_COLLECTORS`, extend the feed's `kind` enum on the wire and in OpenAPI, and
state what the kind gives a caller that `since_seq` does not. It is a decision, not
an extension.
"""
