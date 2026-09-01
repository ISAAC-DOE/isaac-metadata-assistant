"""A BOUNDED, CURSOR-PAGED **STATE FEED** — deliberately not an event log.

WHAT THIS IS, IN THE ONE SENTENCE THAT HAS TO TRAVEL WITH IT
============================================================
This feed reports **"this entity is at a version later than your cursor"**. It does
not report "here is every act that happened". Those are different products and
conflating them is the honesty defect this module is written to avoid.

The distinction is forced by the storage, not chosen for taste. There is no event
table — the 2026-08-29 authorization deliberately adds none, and `CLAUDE.md` §15
enumerates every table this application may write, so appending immutable event rows
is not something this slice may do even if it wanted to. What exists is the CURRENT
state of an experiment document: each `Experiment` and each `Run` carries `rev`,
`updated_utc` and `generation`, and each entity of the record carries the record's
`rev` AT THE SAVE THAT LAST CHANGED IT (`workspace.py` — `Run.changed_at_rev`,
`Experiment.proposal_change_revs`), all maintained by `save_versioned`. So the only
thing derivable is a projection of where each entity stands *now*.

Three consequences follow, and every one of them is a limitation a caller can be
bitten by, so each is published rather than buried:

* **The feed COALESCES.** Ten edits to one run between two polls are one entry. A
  caller cannot count changes, cannot reconstruct intermediate values, and cannot
  learn the order in which two fields of the same run were written. What it CAN
  learn is that the run moved, and to which version.
* **The feed CANNOT REPORT DELETIONS.** See `DELETION_LIMITATION` below.
* **A cursor CANNOT EXPIRE.** See `EXPIRY_PROPERTY` below.

THE ORDER IS A SEQUENCE, NOT A CLOCK — AND IT USED TO BE A CLOCK
================================================================
The sort key's leading component is `changed_at_rev`: the record's own strictly
increasing `rev` at the save that last changed that entity. It was `updated_utc`,
and that was a MEASURED defect rather than a stylistic one — `workspace._now_iso`
formats `%Y-%m-%dT%H:%M:%SZ`, so a change landing inside the second a cursor already
names could move an entity's version without moving its key, and that change was
then never reported by that cursor. `SEQUENCE_PROOF` states why the sequence closes
it and `GAP_GUARANTEE` states what is now promised. The fix is deliberately NOT a
sub-second timestamp: that would be a repo-wide storage change (exports, snapshots,
record timestamps) and would trade a proven defect for the unproven assumption that
two writes never share a microsecond.

WHAT IT IS FOR
==============
A POLLED change signal that is O(returned) in what it sends, so a surface watching a
1,000-run record does not download the record to learn that nothing moved.

IT IS CALLED POLLING RATHER THAN "near-real-time", WHICH IS WHAT THIS LINE USED TO
SAY. "Near-real-time" is a claim about LATENCY, and no latency figure is measured
anywhere in this repository — the delay depends on a client's cadence, its jitter,
its backoff and whether its tab is visible, none of which this module can see or
bound. The word is only earned by a measurement, so the honest word is the mechanism.
`useRecordSync`'s conditional GET already answers "did the RECORD change?" in one
bit; this answers "WHICH entities changed, and to what version?" without composing a
single draft.

WHAT IT DELIBERATELY DOES NOT TOUCH
===================================
Nothing here writes. Nothing here composes a draft, resolves inheritance, runs an
export dry run, or asks `pending()`. That is a hard performance property, measured,
and it is the reason the feed is cheap on a record whose detail response is not —
see `changes_page`'s measurement table. It is also why this module imports nothing
from the truth core: a change feed that could reach `transform` would be one refactor
away from being O(runs) with an export-sized constant.

IT IMPORTS NOTHING FROM `proposals.py` EITHER, and that is load-bearing now that a
`proposal` kind is served. Every collector below reads STORED ATTRIBUTES and nothing
else — no lifecycle function, no view builder, no model. A module that could not
reach a proposal's content cannot leak it, which is a structural guarantee rather
than a review one.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Sequence

#: The default page size, and the same number as `serialize.PENDING_WINDOW` — on
#: purpose. This repository already has ONE established answer to "how much does a
#: bounded read hand back by default", it is 50, and a second number would be a second
#: thing for a reader to hold in their head with no measurement behind the difference.
#: It is NOT imported from `serialize`: these two bounds are free to diverge if one is
#: ever re-measured, and importing would make a change to one silently move the other.
CHANGE_FEED_WINDOW = 50

#: The server maximum. A caller asking for more is CLAMPED, never refused — a `422` on
#: `limit=1000` would make a client guess the ceiling, and the effective limit is
#: reported back in every response so the clamp is observable rather than silent.
CHANGE_FEED_LIMIT_MAX = 200

#: The cursor payload version. Bumped only if the tuple's SHAPE changes; a cursor
#: carrying any other value is refused rather than guessed at.
#:
#: **VERSION 1 -> 2, AND THE TRANSITION IS STATED RATHER THAN LEFT TO THE NUMBER.**
#: A v1 cursor's leading component was a `%Y-%m-%dT%H:%M:%SZ` STRING; a v2 cursor's is
#: an INTEGER sequence position. The two are not comparable and neither converts into
#: the other — a timestamp does not name a `rev`, and no arithmetic recovers one. So a
#: v1 cursor is **refused, not migrated and not misread**: `decode_cursor` rejects any
#: payload whose `v` is not this constant, before it looks at anything else, and the
#: refusal is the published `422 malformed_cursor` whose single remedy is already
#: "drop the cursor and resync". A build that tried to interpret a v1 payload with v2
#: rules would compare a string against an integer key and answer from a position the
#: caller never asked for, which is the wrong-answer-instead-of-an-error failure this
#: whole module's tone is aimed at. The payload's key for that component was also
#: renamed `t` -> `q`, so a v1 token is missing a required component as well as
#: carrying the wrong version — two independent refusals, not one.
CURSOR_VERSION = 2

#: The sort key that precedes every real entry, and the position an absent cursor
#: resolves to. It is `(-1, "", "")` rather than a `None` special case so that "start
#: of the order" is an ordinary key and every comparison below is one comparison.
#:
#: IT IS STRICTLY BELOW EVERY REAL KEY, and that now rests on ARITHMETIC rather than on
#: a claim about strings. Every entity's sequence component is a NON-NEGATIVE integer,
#: and that is enforced HERE by `_position` rather than argued from three other
#: modules. The previous `("", "", "")` needed a supporting argument about `kind` being
#: a non-empty literal; this needs none, which is a strictly better footing for the one
#: key the whole order is anchored to.
#:
#: THE ARGUMENT-FROM-OTHER-MODULES WAS WRITTEN HERE FIRST AND WAS FALSE, and it is
#: recorded rather than replaced because it is the shape of mistake this file exists to
#: refuse. It read: "`save_versioned` only ever stamps a `rev` it is about to write,
#: which is `>= 1`, and `workspace` clamps a persisted negative to `0` on hydration
#: (`Run.__post_init__`, `_hydrate_change_revs`)." Both halves were true of RUNS and
#: PROPOSALS and neither was true of the EXPERIMENT, whose sequence component is
#: `exp.rev` itself — hydrated by `_as_int`, which never raises and never validates, so
#: a persisted `"rev": -5` reached this key unclamped and put the record's own entry
#: BELOW the start of the order, where no read of any kind returns it. The entry the
#: module documents as "exactly one, always present" was absent. Two changes close it:
#: `save_versioned` floors what it writes, and `_position` floors what is read.
ZERO_KEY: tuple[int, str, str] = (-1, "", "")


# --- the four published properties ---------------------------------------------
#
# These are module constants rather than prose inside a docstring because the route
# description, the tests and the frontend copy all have to make the SAME claim, and a
# claim written three times is a claim free to drift. Compare `dependencies.MISSING_REASON`.

#: WHY THE ORDER CANNOT SKIP A CHANGE. The argument, written out, because the previous
#: key's failure was not that anyone reasoned badly about it — it was that nobody
#: reasoned about it in writing at all, so two successive wordings of `GAP_GUARANTEE`
#: were measured false before the third was written about the right thing.
SEQUENCE_PROOF = (
    "The key's leading component is a SEQUENCE POSITION, not a clock: it is the "
    "record's own `rev` at the save that last changed that entity. `rev` is durable, "
    "per-record and strictly increasing — every write that changes anything inside "
    "the record takes it to `max(in-memory rev, on-disk rev, 0) + 1`, so the persisted "
    "value never repeats, never goes back, and is always at least 1. THE PROOF, in "
    "three steps, because two of them are properties the code has to hold up rather "
    "than facts about arithmetic. STEP ONE: a position never moves backwards. A save "
    "either stamps an entity with the rev it is about to write, or leaves that entity "
    "alone — and the leave-alone branch clamps to the position already on disk rather "
    "than writing back whatever an in-memory copy holds, so a stale reader cannot "
    "regress an entity into a range a cursor has already passed. STEP TWO: a cursor's "
    "sequence component R_c is, by construction, at most the record's rev at the "
    "moment that cursor was issued (floored at zero, which is the identity for every "
    "record this application has ever written): the record's own entry sits exactly "
    "there and every other entity sits at the rev of some earlier save. STEP THREE: "
    "any change made afterwards is written at a rev R_new strictly greater than the "
    "rev on disk when it ran, which is itself at least the rev the cursor was issued "
    "from. So R_new > R_c, and the changed entity's new key (R_new, kind, id) is "
    "strictly greater than the cursor key (R_c, k, e) ON THE FIRST COMPONENT ALONE — "
    "regardless of how the kind and entity-id tie-break falls. That is exactly the "
    "property the timestamp key lacked: a whole-second stamp could advance into the "
    "second a cursor already sat in, leaving the tie-break to decide, and the "
    "tie-break could put the changed entity behind the cursor. It cannot happen to an "
    "integer that must increase. "
    "WHERE THAT PROOF HOLDS, AND IT IS PUBLISHED BECAUSE ALL THREE STEPS READ ONE "
    "FILESYSTEM RATHER THAN THE DURABLE ROW. Every number the three steps compare is "
    "read from this deployment's own workspace file: STEP ONE's clamp reads the "
    "on-disk positions, and STEP THREE's R_new is computed from the on-disk rev. So "
    "what is proven is a property of ONE PROCESS READING ONE WORKSPACE FILESYSTEM, "
    "which is the deployment as documented — the workspace is per-pod ephemeral "
    "storage. It is NOT a proof about two processes sharing one database, and this "
    "text is where that scope belongs: the wording this replaced carried a caveat "
    "saying the residue is small BECAUSE the application runs as one process reading "
    "one clock, and that it was the reason it is small rather than a proof that it is "
    "zero. That caveat was deleted when the key stopped being a clock, and its "
    "scoping half is restored here rather than left out. Two things are deliberately "
    "not claimed in the other direction. This repository does not record how many "
    "replicas the hosted deployment runs and nothing here claims it runs more than "
    "one — but a rollout overlaps an old process with a new one whether or not it "
    "does, so the scope is worth stating either way. And the shared layer is not "
    "unguarded: the durable write is a COMPARE-AND-SWAP that admits a write only "
    "when its rev is strictly ahead of the rev the stored row already holds, or the "
    "offered document is byte-identical, so a writer whose file is behind the row "
    "cannot commit a duplicate or a regressed position at all. It is refused as a "
    "stale write, and the winner's document is written into that process's workspace "
    "file before the refusal is raised, so that process's next write is strictly "
    "ahead. WHAT NEITHER OF THOSE CLOSES, named rather than implied: a process whose "
    "workspace file is behind the stored row keeps serving that record from that file "
    "until one of its writes is refused, because hydration deliberately does not "
    "refresh a record whose file is already present. That is staleness of the READ "
    "COPY — every read of that record is equally behind, this feed included — and not "
    "a property of the order, so no cursor discipline can fix it and none is offered."
)

#: THE GAP GUARANTEE, stated honestly. Quoted verbatim by the route description and
#: pinned by `test_change_feed.py`.
GAP_GUARANTEE = (
    "Paging this feed returns no entity twice, and reports an entity exactly when its "
    "SORT KEY advances strictly past the cursor you hold. That is the whole rule, and "
    "it is stated as a property of the KEY rather than of the clock because three "
    "earlier versions of this sentence were stated about the clock and every one of "
    "them was measured false. The key is `(changed_at_rev, kind, entity_id)`, and "
    "`changed_at_rev` is a durable strictly-increasing SEQUENCE POSITION rather than a "
    "timestamp, so a change to an entity ALWAYS moves that entity's key strictly past "
    "any cursor issued before it — see the ordering proof published beside this. "
    "THE SAME-SECOND GAP THIS SENTENCE USED TO DISCLOSE IS CLOSED, and the disclosure "
    "is recorded rather than deleted so a reader can see what changed: the key used to "
    "lead with `updated_utc`, formatted to WHOLE SECONDS, so a change that moved an "
    "entity's stamp forward only into the second the cursor already sat in — where the "
    "`kind`/`entity_id` tie-break could place it behind — was silently never reported "
    "by that cursor. It was fixed by changing the KEY, not the clock: `updated_utc` is "
    "still published because clients display it, and it is no longer load-bearing for "
    "correctness. Two things are still NOT promised, and neither is a clock problem. "
    "This is a guarantee about ORDERING, not exactly-once delivery: an entity that "
    "changes again after you were told about it is reported again, which is what a "
    "state feed is for. And the sequence belongs to ONE record — an entity whose "
    "position was never recorded sits at 0 (a document written before the sequence "
    "existed, or an entity first persisted by the unversioned save primitive), and a "
    "record that is destroyed and re-materialised, as the example-workspace reset does, "
    "starts a fresh sequence at 0, so a cursor held across either must be dropped. The "
    "remedy for both is the same, is always available and costs one request: ask for "
    "the feed with no cursor at all, which is computed from current state and so "
    "reports every entity at the version it holds right now."
)

#: THE DELETION LIMITATION. Quoted verbatim by the route description and pinned by test.
DELETION_LIMITATION = (
    "This feed cannot report deletions. A removed run is simply gone from the record "
    "document, and this feed is derived from that document's current state rather "
    "than from a retained log, so there is nothing left to report — inventing a "
    "tombstone would mean claiming a durability the storage does not have. A client "
    "that needs to know a run disappeared must compare the ids it holds against the "
    "ones the feed returns. What the feed CAN do is make a delete-then-recreate of "
    "the same id distinguishable: a recreated entity carries a new `generation`, so "
    "its `version` differs from the one you held even when its `rev` has returned "
    "to 0."
)

#: THE EXPIRY PROPERTY. Quoted verbatim by the route description and pinned by test.
#:
#: This is the one place where the "no event log" constraint BUYS something rather
#: than costing something, which is why it is published beside the two costs.
EXPIRY_PROPERTY = (
    "A cursor never expires. The feed is derived from current state rather than from "
    "a retained log, so there is no retention window a cursor could fall outside of. "
    "This API therefore publishes no `cursor_expired` status and contains no code "
    "that handles one. A cursor is refused for exactly two reasons, and both are "
    "`422 malformed_cursor`: it could not be decoded — which includes a cursor this "
    "server issued under an older payload VERSION, refused rather than reinterpreted "
    "— or it belongs to a different feed than the one it was sent to."
)


# --- entries ------------------------------------------------------------------


@dataclass(frozen=True)
class ChangeEntry:
    """One entity's position in the feed's order.

    Every field is read straight off the stored version coordinates. Nothing here is
    derived, composed, or looked up — which is the property that keeps the feed cheap,
    and it is asserted rather than assumed: see
    `test_change_feed.py::test_a_feed_request_composes_no_draft_and_runs_no_dry_run`.

    THE COORDINATES AFTER `changed_at_rev` ARE PER-KIND, AND ABSENT RATHER THAN NULL
    WHEN AN ENTITY DOES NOT CARRY ONE. An `Experiment` and a `Run` each carry their own
    `rev`/`generation` series, so they publish a `version` token. A proposal carries
    neither — `proposals.py` gives it no version series at all — so no `rev`,
    `generation` or `version` appears on a proposal entry. The alternative would be to
    synthesise one, and a fabricated version is worse than a missing one: a client
    would compare two numbers that never came from a counter. What a proposal DOES
    carry is its lifecycle `state`, which is a stored value on the entity.
    """

    kind: str
    entity_id: str
    #: THE ORDERING COORDINATE. See `SEQUENCE_PROOF`.
    changed_at_rev: int
    #: The entity's own version series, for the kinds that have one.
    rev: int | None = None
    generation: str | None = None
    #: KEPT ON THE WIRE, NO LONGER LOAD-BEARING. Clients display "last updated"; the
    #: order and the cursor no longer depend on it in any way. Saying so here rather
    #: than only in `GAP_GUARANTEE` because this is the field a later tidy-up would
    #: delete on the grounds that "nothing reads it" — something does, just not this
    #: module.
    updated_utc: str | None = None
    #: The entity's lifecycle state, for the kinds that have one. A stored value read
    #: verbatim; this module classifies nothing and defines no state of its own.
    state: str | None = None

    @property
    def version_token(self) -> str | None:
        """`<generation>.<rev>` — the SAME value `Experiment.version_token` mints.

        NAMED FOR THE CODE, PUBLISHED AS `version`. `workspace` calls this
        `version_token` and every route that serves it publishes it as `version`,
        `experiment_version` or `run_version` (`_run_view`, `get_run`, `list_notes`,
        …). This follows both conventions rather than inventing a third: the property
        matches the model, `to_wire` matches the wire.

        Recomputed here rather than read off the object, so a `ChangeEntry` built for a
        test — or, later, for an entity kind that is not a workspace object — cannot
        publish a version that disagrees with its own two components.

        `None` WHEN EITHER COMPONENT IS MISSING, which is the proposal case. Returning
        `"None.None"` would be a token that compares, sorts and looks real.
        """
        if self.rev is None or self.generation is None:
            return None
        return f"{self.generation}.{self.rev}"

    @property
    def key(self) -> tuple[int, str, str]:
        """The TOTAL ORDER key: `(changed_at_rev, kind, entity_id)`.

        WHY THE TIE-BREAK IS NOT DECORATION, AND WHY IT IS STILL NEEDED AFTER THE
        SEQUENCE FIX. One `save_versioned` stamps every entity it changed with the
        SAME `rev` — that is the whole design, since they changed in one write — so on
        a record whose runs were all created together the sequence component is
        constant and `(kind, entity_id)` is doing all of the ordering. Without it,
        `sorted` would be merely stable and a page boundary could reorder between two
        requests, which is precisely how a cursor-paged reader loses an entity. The
        sequence fixed a different failure: the tie-break deciding an order that a
        CHANGE should have decided.

        THE ORDER IS TOTAL BECAUSE `(kind, entity_id)` IS UNIQUE, and that uniqueness
        is enforced rather than assumed: run ids are unique within an experiment
        (`Experiment.add_run` refuses a duplicate, `workspace._hydrate_runs` drops
        one — the same invariant `sorted_runs` rests on), proposal ids likewise
        (`_hydrate_proposals` files a duplicate as unreadable, and unreadable entries
        are not served), and the experiment's own entry is the only one of its kind. An
        experiment id that happened to equal a run id still produces two distinct keys,
        because `kind` differs.
        """
        return (self.changed_at_rev, self.kind, self.entity_id)

    def to_wire(self) -> dict:
        """The published shape: the common core, plus the coordinates this kind has.

        A COORDINATE THIS ENTITY DOES NOT CARRY IS ABSENT, never `null`. Both choices
        are expressible; absence is the one that cannot be mistaken for a value, and it
        is what makes the projection test below a statement about what the feed emits
        rather than about which nulls it happens to emit.
        """
        wire: dict = {
            "kind": self.kind,
            "entity_id": self.entity_id,
            "changed_at_rev": self.changed_at_rev,
        }
        token = self.version_token
        if token is not None:
            wire["version"] = token
        if self.rev is not None:
            wire["rev"] = self.rev
        if self.generation is not None:
            wire["generation"] = self.generation
        if self.updated_utc is not None:
            wire["updated_utc"] = self.updated_utc
        if self.state is not None:
            wire["state"] = self.state
        return wire


# --- collectors: the kind set is DERIVED, never hard-coded --------------------


@dataclass(frozen=True)
class KindCollector:
    """One entity kind and the function that reads its entries off an experiment.

    WHY A REGISTRY RATHER THAN THREE INLINE LOOPS. It is what let the `proposal` kind
    be added by writing one function and appending one tuple entry, while
    `feed_kinds()` publishes the truth about which kinds a deployment actually serves
    instead of a hopeful literal. The wrong way to prepare for a kind would have been a
    `try: import proposals` here, or a branch on a feature flag; a collector passed in
    as a parameter needs neither, and the `proposal` collector below imports nothing.

    THIS DOCSTRING HAS BEEN WRONG ABOUT PROPOSALS TWICE AND THE HISTORY IS KEPT,
    because both wordings are the kind a future reader would act on. It first said the
    kind "does NOT exist at this commit — it lives in an unmerged PR", which became
    false when the proposals work merged. It was then corrected to say that serving a
    `proposal` kind was "STILL DELIBERATELY NOT DONE", which is false as of this
    change: `_proposal_entries` below serves it. What was true under BOTH wordings, and
    remains true, is the mechanism they described — proposals are part of the record's
    authoritative signature (`workspace._authoritative_signature` hashes them), so a
    proposal act also moves the record's own `rev` and therefore its `experiment`
    entry. A client now learns both "this record moved" and "this proposal moved".

    IT IS A TUPLE PASSED BY THE CALLER, NOT A MUTABLE MODULE-LEVEL REGISTRY. A global
    that tests append to is a global that leaks between tests; `changes_page` takes
    `collectors` as an argument defaulting to `RECORD_COLLECTORS`, so extension is a
    parameter rather than a side effect.
    """

    kind: str
    read: Callable[[Any], Iterable[ChangeEntry]]


def _position(raw: Any) -> int:
    """A stored sequence coordinate, as a NON-NEGATIVE `int`. The one clamp.

    Every collector below runs its coordinate through this, so `ZERO_KEY`'s "strictly
    below every real key" is a property of this module rather than a claim about what
    `workspace` happens to persist. The three coordinates arrive from three different
    places — `Experiment.rev`, `Run.changed_at_rev`, a value out of
    `Experiment.proposal_change_revs` — and only a persisted document decides what is
    in them; a reader must not have to check three modules to know the order holds.

    NEGATIVE BECOMES `0`, NOT `ZERO_KEY`'s `-1`. `0` already has a defined meaning
    here — "no versioned save has recorded this entity changing" — and it is the
    honest bucket for a coordinate that cannot be read as a position at all. Putting
    such an entity at `-1` would place it AT the start key, where `key > start` is
    false and a cursorless resync would silently omit it.

    NON-INTEGER BECOMES `0` TOO, and `bool` is excluded from `int` explicitly because
    `isinstance(True, int)` is `True` in Python.

    THAT TYPE GUARD IS DEFENCE IN DEPTH AND IS UNREACHABLE FROM ANY PERSISTED
    DOCUMENT AT ALL THREE CALL SITES, which is the opposite of what this paragraph
    used to say. It read: "a `changed_at_rev` of `True` would otherwise read as the
    position `1`, a real position nothing ever wrote. Nothing is coerced: `int("7")`
    would invent a position out of a value that was never one." **BOTH NAMED EXAMPLES
    ARE EXACTLY WHAT HAPPENS, measured over HTTP on a persisted document: a
    `changed_at_rev` of `"7"` is served as the position 7, `true` as 1, `3.9` as 3 —
    and the same for the experiment's `rev`.** The cause is one function earlier.
    Hydration reaches these coordinates first and `workspace._as_int` COERCES
    (`int("7") == 7`, `int(True) == 1`, `int(3.9) == 3`), so a value arriving here is
    already an `int` and the `isinstance` branch cannot fire from stored state. It is
    kept because it CAN fire from a directly-constructed `ChangeEntry` and from a
    future collector reading something `workspace` does not hydrate — and it is now
    tested rather than assumed
    (`test_change_feed_sequence.py::test_position_refuses_a_non_integer_and_a_bool`).

    THE REFUSAL IS REAL WHERE IT IS CLAIMED, ONE MODULE OVER, and that is where a
    reader should look for it: `decode_cursor` refuses a non-`int` or `bool` `q` on
    the CURSOR, and `workspace._hydrate_change_revs` refuses a non-`int`, `bool` or
    negative value in the proposal position map. The asymmetry between those two and
    this one is `CLAUDE.md` §11's rule: a malformed value in a REQUEST may be refused,
    because the caller sent it and a typed refusal names what to fix; a malformed
    value already PERSISTED must be READ, because the reader did nothing wrong and
    their record must not vanish. The coercion is a weaker form of that same
    tolerance, and it is deliberately left in place rather than tightened at the
    hydration boundary: `rev` is not only this feed's coordinate, it is the record's
    served `version` token and the basis of every `If-Match`, so dropping a coerced
    `"7"` to `0` would move a record's version BACKWARDS and could let a stale token
    match. That trades a wrong docstring for a concurrency hazard.

    SO THE ONE THING THIS FUNCTION ACTUALLY CONTRIBUTES IS THE LOWER FLOOR, and that
    IS live: `Experiment.rev` is hydrated by `_as_int`, which admits a persisted
    `-5`, and nothing else clamps it. (`Run.changed_at_rev` is clamped again by
    `Run.__post_init__`, and the proposal map by `_hydrate_change_revs`, so at those
    two sites this is belt-and-braces; at the experiment's it is the only guard.)

    THERE IS NO UPPER CLAMP, and "the one clamp" above is about the lower bound alone.
    A persisted `changed_at_rev` of `10 ** 30` is served verbatim as a position, and
    the consequence is the mirror of the one the floor closes: no cursor a client can
    hold will ever advance past it, so that entity is reported on EVERY poll for as
    long as it holds that value. It is disclosed rather than clamped because the
    failure direction is the recoverable one — over-reporting, never a silent
    omission, and a cursorless resync still returns the whole record at its current
    positions — whereas an upper clamp would have to invent a ceiling, and a ceiling
    set wrong WOULD silently omit.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return raw if raw > 0 else 0


def _experiment_entries(exp: Any) -> Iterator[ChangeEntry]:
    """The record's own entry — exactly one, always present.

    Always present even for a record that has never been written since creation:
    `Experiment.__post_init__` anchors `updated_utc` to `created_utc` and `generation`
    to a deterministic legacy value, so there is no state in which this yields nothing.
    A feed whose first page could be empty would make "nothing has changed" and "this
    record does not exist" look identical to a client.

    ITS SEQUENCE POSITION IS `exp.rev` FLOORED AT ZERO, with nothing stored and nothing
    derived. The floor is `_position` and it changes the value for exactly one input —
    a persisted negative `rev`, which `_as_int` admits and nothing else refuses. For
    every record this application has ever written it is the identity.

    AND `exp.rev` IS EXACT RATHER THAN APPROXIMATE: `save_versioned` bumps `rev` on every write
    whose authoritative signature moved, and the signature covers the record's title,
    source, draft, record id, runs, notes and proposals — so the record's own entry
    changed at exactly the rev it holds. It is also the reason `SEQUENCE_PROOF`'s "R_c
    is at most the record's rev" step is airtight: this entry sits AT the maximum, so
    no entity can ever sit above it.
    """
    yield ChangeEntry(
        kind="experiment",
        entity_id=exp.id,
        changed_at_rev=_position(exp.rev),
        # PUBLISHED VERBATIM, deliberately not through `_position`. `rev` is the
        # entity's own version number and a client compares it to the `rev` every
        # other route serves; a floor applied here would make this one surface
        # disagree with all of them. Only the ORDER is clamped.
        rev=exp.rev,
        generation=exp.generation,
        updated_utc=exp.updated_utc,
    )


def _run_entries(exp: Any) -> Iterator[ChangeEntry]:
    """One entry per run, read from `exp.runs` directly.

    `exp.runs` RATHER THAN `exp.sorted_runs()`: this generator's output is sorted by
    `key` moments later, so paying for a second sort on `(ordinal, created_utc, id)`
    would buy an order that is then discarded. The feed's order is deliberately NOT
    the record's presentation order — a feed ordered by ordinal could not be paged by
    a cursor at all.
    """
    for run in exp.runs:
        yield ChangeEntry(
            kind="run",
            entity_id=run.id,
            changed_at_rev=_position(run.changed_at_rev),
            rev=run.rev,
            generation=run.generation,
            updated_utc=run.updated_utc,
        )


def _proposal_entries(exp: Any) -> Iterator[ChangeEntry]:
    """One entry per readable proposal: its id, where it sits, and its lifecycle state.

    WHAT IS AND IS NOT ON AN ENTRY, and the list is short on purpose. A feed entry is
    the minimum an authorized consumer needs to decide "re-read this proposal from the
    route that owns it": the id, the kind, the position in the order, when it last
    moved, and the state it is in. NOTHING ELSE. No `proposed_value`, no
    `target_field_path`, no `rule`, no note text, no excerpt, no evidence, no actor, no
    digest. A change feed that carried scientific content would be a second read
    surface for that content with none of the review the first one got, and the
    authorization boundary is the ROUTE plus `record_scope_tag`, which is not weakened
    here. The structural guarantee is that this module imports nothing from
    `proposals.py`, so it holds no function that could render a value even by mistake.

    `state` IS REPORTED, AND IT IS THE ONE THING THAT MAKES A PROPOSAL ENTRY USEFUL —
    but read what it is. It is the proposal's CURRENT stored state, one of the five
    `proposals.PROPOSAL_STATES`. It is NOT an event, and this feed does not report
    lifecycle transitions: a proposal that was accepted between two polls is reported
    as being `accepted` NOW, with no entry saying an acceptance happened, no actor and
    no ordering against any other act. That is the module's coalescing property applied
    to a lifecycle, and it is stated here plainly because "a proposal kind in a change
    feed" is exactly the phrase a reader would take to mean an event stream. The
    proposal's own history is an append-only audit trail on the entity; the route that
    serves a proposal is where it is read.

    NOTHING IS CLASSIFIED, DERIVED OR DEFAULTED. `state` is passed through verbatim, so
    a state this build has never heard of reaches the client unchanged rather than
    being mapped onto one this build does know — mapping would be this feed inventing a
    judgement about a lifecycle it does not own.

    UNREADABLE PROPOSALS ARE NOT SERVED, for `_hydrate_runs`' reason. An entry the
    proposal model refused is kept verbatim in `Experiment.unreadable_proposals` so a
    save cannot discard it, but this module cannot name it: it has no id this
    application is willing to read, and an entity a client cannot address is one it
    could not act on if it were told.

    `updated_utc` IS THE LAST RECORDED ACT'S TIMESTAMP, falling back to when the
    proposal was made. Both are stored on the entity; neither is computed. It is
    display metadata exactly as it is for the other kinds, and exactly as
    non-load-bearing.
    """
    positions = exp.proposal_change_revs
    for proposal in exp.proposals:
        history = proposal.history
        yield ChangeEntry(
            kind="proposal",
            entity_id=proposal.proposal_id,
            changed_at_rev=_position(positions.get(proposal.proposal_id, 0)),
            updated_utc=(history[-1].at if history else proposal.proposed_utc),
            state=proposal.state,
        )


#: The kinds a RECORD-SCOPED feed serves at this commit. Extended by passing a longer
#: tuple, never by mutating this one.
RECORD_COLLECTORS: tuple[KindCollector, ...] = (
    KindCollector(kind="experiment", read=_experiment_entries),
    KindCollector(kind="run", read=_run_entries),
    KindCollector(kind="proposal", read=_proposal_entries),
)


def feed_kinds(collectors: Sequence[KindCollector] = RECORD_COLLECTORS) -> list[str]:
    """The kinds this feed serves, DERIVED from the collectors and sorted.

    Published in every response so a client learns the kind set from the server rather
    than from a literal compiled into its bundle — which is what makes adding a kind a
    server-side change instead of a coordinated release.
    """
    return sorted({c.kind for c in collectors})


# --- the cursor ---------------------------------------------------------------


class MalformedCursor(Exception):
    """A cursor this feed will not act on. Carries WHICH of the two causes it was.

    ONE STATUS, TWO REASONS, and that split is deliberate. The published contract has
    exactly one refusal — `422 malformed_cursor` — because a client only ever has one
    remedy (drop the cursor and resync). But "I could not decode this" and "this is a
    cursor for a different record" are different mistakes in the caller's code, and
    collapsing them into one message would make the second one, which is the more
    likely bug, invisible.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def scope_digest(*parts: str | None) -> str:
    """A stable 16-hex-character digest of a feed's identity.

    WHAT IT IS FOR: a cursor issued by record A's feed must not silently page record
    B's, and an ordinary-workspace cursor must not silently page a worked-example
    session's. Both would return a well-formed page computed from the wrong order —
    a wrong answer rather than an error, which is the failure this whole module's
    tone is aimed at.

    WHAT IT IS NOT: a signature. There is no secret here and none is wanted. Anyone
    who knows the experiment id can compute this digest, and that is fine — the digest
    is a CONSISTENCY check on which feed a cursor came from, not an authorization
    check on who may read it. Authorization is the route: the path names the record
    and `TutorialScopeDep` names the scope, and a caller who can reach neither cannot
    reach the feed by forging a cursor.

    WHAT DIGESTING BUYS, stated narrowly because the obvious wider claim is FALSE.
    It keeps the WORKSPACE SCOPE — in practice a worked-example session id — out of a
    token that gets logged and pasted into bug reports. It does NOT make the cursor
    free of readable identifiers: `encode_cursor` embeds the entity id of the cursor
    position in the clear, because that id IS the position and there is nothing to
    hash it against. A cursor therefore names one entity of a record the holder was
    already reading, and nothing else.
    """
    joined = "\x1f".join("" if p is None else p for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def record_scope_tag(experiment_id: str, session_id: str | None) -> str:
    """The scope digest for ONE record's feed in ONE workspace scope."""
    return scope_digest("record", experiment_id, session_id)


def encode_cursor(key: tuple[int, str, str], *, scope: str) -> str:
    """A key plus its feed identity, as base64url of a compact versioned JSON object.

    OPAQUE BY CONTRACT, NOT BY CRYPTOGRAPHY, and saying which matters. Anyone can
    base64-decode this and read the tuple; it carries no secret and is not meant to.
    "Opaque" here is a rule for CLIENTS — do not construct one, do not parse one, do
    not reason about its contents — enforced by the fact that the server is free to
    change the payload shape behind `CURSOR_VERSION` at any time. That freedom has now
    been EXERCISED rather than merely asserted: v1's `t` (a timestamp string) became
    v2's `q` (an integer sequence position), and every v1 token in the wild is refused.
    A client that had hand-built a cursor is a client that broke on that bump, which is
    why the tests below construct one only to prove a bad one is refused.

    Base64URL WITHOUT PADDING so the token is safe in a query string with no escaping
    (`+`, `/` and `=` all need it; `-`, `_` do not).
    """
    payload = {
        "v": CURSOR_VERSION,
        "s": scope,
        "q": key[0],
        "k": key[1],
        "e": key[2],
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


#: `-_` -> `+/`, so a base64url token can be handed to `b64decode(validate=True)`.
#: `urlsafe_b64decode` has no `validate` parameter (signature `(s)`), which is why the
#: translation is done here rather than by asking that function for strictness.
_B64URL_TO_STANDARD = str.maketrans("-_", "+/")


def decode_cursor(token: str, *, scope: str) -> tuple[int, str, str]:
    """The key a cursor names, or `MalformedCursor`.

    STRICT AT EVERY STEP, and every step is a real failure mode rather than defensive
    padding: a token that is not base64url; base64url that is not UTF-8; UTF-8 that is
    not JSON; JSON that is not an object; an object of a version this build does not
    serve — **which is every cursor issued before `CURSOR_VERSION` became 2** — a
    payload missing a component or carrying one of the wrong type; and a payload whose
    scope digest belongs to a different feed. Each answers the SAME `422`, so a client
    has one thing to handle, and each records its own `reason`.

    NOTHING IS COERCED. A `q` that arrived as the string `"7"` is refused, not
    `int()`-ed, and a `k` that arrived as the integer `7` is refused, not `str()`-ed —
    coercing either would build a key that compares against real keys and silently
    answers from a position the caller never asked for. This is also where a v1 cursor
    dies twice over: its version is wrong AND its leading component is a string under a
    key this version does not read.

    `bool` IS REFUSED AS THE SEQUENCE COMPONENT, explicitly, because
    `isinstance(True, int)` is `True` in Python. A payload carrying `"q": true` would
    otherwise decode to the position `1` — a real key, silently, from a value that was
    never a number.

    A NEGATIVE `q` IS ADMITTED, AND THAT IS DELIBERATE RATHER THAN AN OVERSIGHT — it
    is written down because "STRICT AT EVERY STEP" above, and the wire-published
    `EXPIRY_PROPERTY`'s "refused for exactly two reasons", both invite a reader to
    assume otherwise. `{"q": -99}` decodes and answers `200` with the whole feed.
    Two reasons it stays. `-1` is a position this feed genuinely ISSUES —
    `changes_page` encodes `ZERO_KEY` as the `next_cursor` of an empty first page —
    so "negative" cannot be the test, and a bound of exactly `>= -1` would refuse
    only values that are already harmless. And harmless is the whole point: every
    real key's first component is `>= 0` by `_position`, so a `q` below that can only
    place the caller EARLIER in the order than they asked for. The outcome is a
    resync — every entity reported at its current position — which is precisely the
    remedy `GAP_GUARANTEE` offers for everything, reached by a different route. It
    can over-report and it cannot skip, so refusing it would buy a client one more
    error to handle and buy correctness nothing.
    """
    if not isinstance(token, str) or not token:
        raise MalformedCursor("not_decodable", "The cursor is empty.")
    # `encode_cursor` STRIPS padding, so a token carrying `=` is not one this feed
    # issued. It is refused explicitly because `=` is a legal base64 character and
    # `validate=True` therefore accepts it: without this line `<cursor>` and
    # `<cursor>=` both decode to the identical key, and two distinct strings naming
    # one position is exactly what the strictness the docstring promises rules out.
    if "=" in token:
        raise MalformedCursor(
            "not_decodable", "The cursor is not one this feed issued."
        )
    # `+ "=" * (-len % 4)` restores the padding `encode_cursor` stripped, and
    # `validate=True` refuses a token containing characters outside the base64url
    # alphabet rather than silently DISCARDING them, which is `b64decode`'s default.
    #
    # THE FLAG WAS DESCRIBED HERE BEFORE IT WAS PASSED, and an independent review
    # measured the difference over HTTP: appending `****` to a valid cursor decoded to
    # the IDENTICAL key and answered `200`, as did appending stray `=`. Two distinct
    # cursor strings therefore named one position, while this comment, the docstring's
    # "STRICT AT EVERY STEP", and the wire-published `EXPIRY_PROPERTY` — which tells
    # clients a cursor is refused for exactly two reasons — all said otherwise. No
    # security consequence (the scope digest must still match and the caller already
    # holds the record), but three published claims were false, which is the defect.
    #
    # AND `urlsafe_b64decode` CANNOT TAKE THAT FLAG AT ALL — its signature is `(s)`.
    # Passing it raises `TypeError`, so the fix is not a keyword: the token is
    # translated to the standard alphabet first and `b64decode` is called with
    # `validate=True`, which is the only way to get the refusal this comment has
    # always described.
    try:
        raw = base64.b64decode(
            token.translate(_B64URL_TO_STANDARD) + "=" * (-len(token) % 4),
            validate=True,
        )
    except (binascii.Error, ValueError):
        raise MalformedCursor(
            "not_decodable", "The cursor is not one this feed issued."
        ) from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise MalformedCursor(
            "not_decodable", "The cursor is not one this feed issued."
        ) from None
    if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
        raise MalformedCursor(
            "not_decodable", "The cursor is not one this feed issued."
        )
    sequence = payload.get("q")
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise MalformedCursor(
            "not_decodable", "The cursor is not one this feed issued."
        )
    parts = [payload.get("k"), payload.get("e")]
    if not all(isinstance(p, str) for p in parts):
        raise MalformedCursor(
            "not_decodable", "The cursor is not one this feed issued."
        )
    if payload.get("s") != scope:
        raise MalformedCursor(
            "wrong_feed",
            "That cursor was issued by a different feed — a different record, or a "
            "different workspace scope. Ask for this feed with no cursor to resync.",
        )
    return (sequence, parts[0], parts[1])  # type: ignore[return-value]


# --- bounds -------------------------------------------------------------------


def effective_limit(limit: int | None) -> int:
    """The page size actually used: CLAMPED into `[1, CHANGE_FEED_LIMIT_MAX]`.

    `None` -> the default. Anything below 1 -> 1, anything above the maximum -> the
    maximum. Clamping to the NEAREST valid value rather than falling back to the
    default is the rule a caller can predict without reading this docstring: `limit=0`
    meaning "1" is surprising once, whereas `limit=0` meaning "50" is surprising every
    time someone computes a limit that came out at zero.

    The clamp is REPORTED, never silent — `changes_page` puts the result in the
    response as `limit`, so a client asking for 1,000 can see it got 200.
    """
    if limit is None:
        return CHANGE_FEED_WINDOW
    return max(1, min(int(limit), CHANGE_FEED_LIMIT_MAX))


# --- the page -----------------------------------------------------------------


def collect(
    exp: Any, collectors: Sequence[KindCollector] = RECORD_COLLECTORS
) -> list[ChangeEntry]:
    """Every entity's entry, in the feed's total order.

    O(entities) in cheap key extraction plus one sort, and that cost is unavoidable
    rather than accepted: the runs and proposals live inside ONE experiment document
    that `load_experiment` has already read whole, so there is no index to seek into
    and no way to skip an entity without looking at it. What IS avoidable — and is
    avoided — is doing anything expensive per entity. Compare `routes.list_experiments`,
    which is O(runs) per ANSWERED record because it composes drafts it does not thread;
    this function touches a handful of stored attributes per entity and composes
    nothing.
    """
    entries: list[ChangeEntry] = []
    for collector in collectors:
        entries.extend(collector.read(exp))
    entries.sort(key=lambda e: e.key)
    return entries


def changes_page(
    exp: Any,
    *,
    scope_tag: str,
    cursor: str | None = None,
    limit: int | None = None,
    collectors: Sequence[KindCollector] = RECORD_COLLECTORS,
) -> dict:
    """One bounded page of the feed, starting strictly after `cursor`.

    An ABSENT cursor is the start of the order — the resync path — and is spelled as
    the ordinary key `ZERO_KEY` rather than as a branch, so "resync" and "resume" are
    one code path and cannot drift apart.

    STRICTLY AFTER, never at-or-after: `key > start` is what makes the page boundary
    non-overlapping, and it is why `next_cursor` is the key of the LAST RETURNED entry
    rather than one past it.

    A CURSOR THAT NAMES AN ENTITY WHICH HAS SINCE CHANGED RESUMES CORRECTLY, FULL STOP,
    and this paragraph used to carry a proviso that is now gone. It read "…WHENEVER
    that change moved the entity into a later second", because the key led with a
    whole-second `updated_utc` and a write inside the second a key already named moved
    `rev` without moving the key. The leading component is now `changed_at_rev`, a
    strictly-increasing per-record sequence position, so any change puts the entity
    ahead of any earlier cursor on the first component alone — see `SEQUENCE_PROOF`.
    The strictness of `>` is unchanged and was never the problem: relaxing it to `>=`
    would have re-emitted every entity of the boundary position on every poll while
    STILL missing an entity earlier in it, buying duplicates without buying the gap
    back.

    MEASURED, at this commit, over HTTP against a record created through
    `POST /api/experiments` and given N runs in process (the `_with_runs` harness
    `test_pending_reads_are_boundable.py` uses). `resolved_run_draft`, `export_draft`
    and `Experiment.pending` are counted by monkeypatching them for the request::

        runs   GET /changes bytes   entries   resolved_run_draft   export_draft   pending
          25                4,997        26                    0              0        0
         250                9,390        50                    0              0        0
        1000                9,390        50                    0              0        0

    THE BYTE COLUMN HAS NOW BEEN WRONG THREE TIMES, and every one is recorded rather
    than quietly replaced, because the third is the one that matters most: it was wrong
    while claiming to have been re-measured.

    1. It first read 4,676 / 8,757 / 8,757, measured honestly.
    2. The wire key was renamed `version_token` -> `version` (six characters shorter,
       once per entry) and the table was not re-run: 4,520 / 8,457 / 8,457 corrected it.
    3. The ordering fix added a `changed_at_rev` key to every entry and a third `kinds`
       member, and the table was updated to 5,196 / 9,757 / 9,757 **beside a sentence
       saying "the numbers above are from the benchmark below, re-run afterwards".**
       The benchmark had NOT been re-run: running it produces the figures now in the
       table, and 5,196 / 9,757 / 9,757 correspond to no build. A wrong number is
       cheap; a wrong number wearing a provenance claim is what makes the next reader
       stop checking.

    The lesson, now earned three times: a measurement is invalidated by a change to the
    thing measured, including a change that looks purely cosmetic — and "re-measured"
    is itself a claim, which is why the command to re-derive it is printed below rather
    than the figures being asked to be believed.

    Two things that table is claiming. The response is FLAT past the window — 250 runs
    and 1,000 runs are BYTE-IDENTICAL in length, because every entry is the same width
    (a 26-character id, a 16-hex generation, a one-second timestamp, a sequence
    position) and the window stops at 50 either way. And the three expensive
    derivations are entered ZERO times at every size, which is what makes the flatness
    durable rather than incidental: a future edit reaching for `resolved_run_draft`
    here would give the feed the shape `routes.list_experiments` already has, and the
    counter test fails if it does.

    WHAT THE TABLE DOES NOT CLAIM. No wall-clock figure appears in it or in any
    assertion. This repository has been bitten by timing assertions under CPU
    contention (`CLAUDE.md` §7), and bytes and call counts are deterministic for a
    given workload while a duration is not.

    Re-derive rather than quoting::

        ISAAC_PERF_BENCH=1 .venv/bin/pytest \\
          apps/api/tests/test_change_feed.py -q -s -k benchmark
    """
    start = ZERO_KEY if cursor is None else decode_cursor(cursor, scope=scope_tag)
    size = effective_limit(limit)

    entries = collect(exp, collectors)
    after = [e for e in entries if e.key > start]
    window = after[:size]

    # `next_cursor` IS ALWAYS PRESENT, including on an empty page, and on an empty page
    # it is the position the caller was ALREADY at — so a poller that keeps sending
    # back what it was handed makes no progress and loses nothing, which is exactly the
    # behaviour a poller wants. Encoding it (rather than echoing the caller's token
    # verbatim) means a caller that sent nothing gets a real cursor on its first empty
    # page instead of a `null` it has to special-case.
    last_key = window[-1].key if window else start
    return {
        "changes": [e.to_wire() for e in window],
        "next_cursor": encode_cursor(last_key, scope=scope_tag),
        "has_more": len(after) > len(window),
        "limit": size,
        "returned": len(window),
        "remaining": len(after) - len(window),
        "kinds": feed_kinds(collectors),
    }
