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
`updated_utc` and `generation` (`workspace.py`), bumped by `save_versioned`. So the
only thing derivable is a projection of where each entity stands *now*.

Three consequences follow, and every one of them is a limitation a caller can be
bitten by, so each is published rather than buried:

* **The feed COALESCES.** Ten edits to one run between two polls are one entry. A
  caller cannot count changes, cannot reconstruct intermediate values, and cannot
  learn the order in which two fields of the same run were written. What it CAN
  learn is that the run moved, and to which version.
* **The feed CANNOT REPORT DELETIONS.** See `DELETION_LIMITATION` below.
* **A cursor CANNOT EXPIRE.** See `EXPIRY_PROPERTY` below.

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
CURSOR_VERSION = 1

#: The sort key that precedes every real entry, and the position an absent cursor
#: resolves to. It is `("", "", "")` rather than a `None` special case so that "start
#: of the order" is an ordinary key and every comparison below is one comparison.
#:
#: IT IS STRICTLY BELOW EVERY REAL KEY, and that rests on a stated invariant rather
#: than on a hope: `kind` is a non-empty literal for every collector in this module
#: (`"experiment"`, `"run"`), so even an entity whose `updated_utc` hydrated as `""`
#: from a malformed document produces `("", "experiment", id) > ("", "", "")`.
ZERO_KEY: tuple[str, str, str] = ("", "", "")


# --- the three published properties -------------------------------------------
#
# These are module constants rather than prose inside a docstring because the route
# description, the tests and the frontend copy all have to make the SAME claim, and a
# claim written three times is a claim free to drift. Compare `dependencies.MISSING_REASON`.

#: THE GAP GUARANTEE, stated honestly. Quoted verbatim by the route description and
#: pinned by `test_change_feed.py`.
GAP_GUARANTEE = (
    "Paging this feed returns no entity twice, and reports an entity exactly when its "
    "SORT KEY advances strictly past the cursor you hold. That is the whole rule, and "
    "it is stated as a property of the KEY rather than of the clock because two "
    "earlier versions of this sentence were stated about the clock and both were "
    "measured false. The key is `(updated_utc, kind, entity_id)` and `updated_utc` is "
    "formatted to WHOLE SECONDS, so any change that leaves an entity's key at or "
    "behind your cursor is not reported by that cursor — whether the stamp did not "
    "move at all, or moved forward only into the second your cursor already sits in, "
    "where the `kind`/`entity_id` tie-break can still place it behind. A guarantee "
    "worded as *\"provided `updated_utc` strictly advances\"* does NOT cover that "
    "second case: the stamp genuinely advances and the entity is still skipped, which "
    "is why the wording here is about the key. This is a guarantee about ORDERING, not "
    "exactly-once delivery, and it is not claimed to be. In every such case the change "
    "appears the next time that entity moves into a LATER second, so nothing is lost "
    "permanently on an entity that is still being written. The exposure is bounded by "
    "one second per poll, and it is small because this application runs as a single "
    "pod reading one clock \u2014 that is the REASON it is small, not a proof that it "
    "is zero. The remedy is always available and costs one request: ask for the feed "
    "with no cursor at all, which is computed from current state and so reports every "
    "entity at the version it holds right now."
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
    "`422 malformed_cursor`: it could not be decoded, or it belongs to a different "
    "feed than the one it was sent to."
)


# --- entries ------------------------------------------------------------------


@dataclass(frozen=True)
class ChangeEntry:
    """One entity's position in the feed's order.

    Every field is read straight off the stored version coordinates. Nothing here is
    derived, composed, or looked up — which is the property that keeps the feed cheap,
    and it is asserted rather than assumed: see
    `test_change_feed.py::test_a_feed_request_composes_no_draft_and_runs_no_dry_run`.
    """

    kind: str
    entity_id: str
    updated_utc: str
    rev: int
    generation: str

    @property
    def version_token(self) -> str:
        """`<generation>.<rev>` — the SAME value `Experiment.version_token` mints.

        NAMED FOR THE CODE, PUBLISHED AS `version`. `workspace` calls this
        `version_token` and every route that serves it publishes it as `version`,
        `experiment_version` or `run_version` (`_run_view`, `get_run`, `list_notes`,
        …). This follows both conventions rather than inventing a third: the property
        matches the model, `to_wire` matches the wire.

        Recomputed here rather than read off the object, so a `ChangeEntry` built for a
        test — or, later, for an entity kind that is not a workspace object — cannot
        publish a version that disagrees with its own two components.
        """
        return f"{self.generation}.{self.rev}"

    @property
    def key(self) -> tuple[str, str, str]:
        """The TOTAL ORDER key: `(updated_utc, kind, entity_id)`.

        WHY THE TIE-BREAK IS NOT DECORATION. `updated_utc` has one-second resolution
        (`workspace._now_iso` formats `%Y-%m-%dT%H:%M:%SZ`), and a single
        `save_versioned` stamps every changed run with the SAME instant — so on a
        record whose runs were all created in one write, the timestamp is constant and
        `(kind, entity_id)` is doing all of the ordering. Without it, `sorted` would be
        merely stable and a page boundary could reorder between two requests, which is
        precisely how a cursor-paged reader loses an entity.

        THE ORDER IS TOTAL BECAUSE `(kind, entity_id)` IS UNIQUE, and that uniqueness
        is enforced rather than assumed: run ids are unique within an experiment
        (`Experiment.add_run` refuses a duplicate, `workspace._hydrate_runs` drops
        one — the same invariant `sorted_runs` rests on), and the experiment's own
        entry is the only one of its kind. An experiment id that happened to equal a
        run id still produces two distinct keys, because `kind` differs.
        """
        return (self.updated_utc, self.kind, self.entity_id)

    def to_wire(self) -> dict:
        return {
            "kind": self.kind,
            "entity_id": self.entity_id,
            "version": self.version_token,
            "rev": self.rev,
            "generation": self.generation,
            "updated_utc": self.updated_utc,
        }


# --- collectors: the kind set is DERIVED, never hard-coded --------------------


@dataclass(frozen=True)
class KindCollector:
    """One entity kind and the function that reads its entries off an experiment.

    WHY A REGISTRY RATHER THAN TWO INLINE LOOPS. The brief names a third kind,
    `proposal`, and a collector tuple is what lets the slice that owns that kind add
    it without touching this module, while `feed_kinds()` publishes the truth about
    which kinds a deployment actually serves instead of a hopeful literal. The wrong
    way to prepare for it would be a `try: import proposals` here, or a branch on a
    feature flag; a collector passed in as a parameter needs neither.

    THIS PARAGRAPH USED TO SAY THAT KIND "does NOT exist at this commit — it lives in
    an unmerged PR", AND THAT IS CORRECTED RATHER THAN REPHRASED, because it was true
    when written and is FALSE at this commit. The proposals work merged into this
    branch's own history: `isaac_api/proposals.py` is in this tree and every
    `Experiment` carries `.proposals`. A future reader must not take this docstring
    as evidence that the feature is unavailable.

    SERVING A `proposal` KIND IS STILL DELIBERATELY NOT DONE, and what IS observable
    today is stated so the shortfall is measured rather than implied: proposals are
    part of the record's AUTHORITATIVE SIGNATURE (`workspace._authoritative_signature`
    hashes them), so proposing, accepting or refusing one moves the record's own `rev`
    and `updated_utc`, and therefore moves the `experiment` entry of this feed. A
    client learns "something about this record moved" and must re-read to learn what;
    it does NOT learn which proposal moved, and no page carries a proposal id.
    `test_change_feed.py` pins that mechanism, so a later change that took proposals
    out of the signature — which would make this feed silent about them altogether —
    fails a test instead of passing quietly.

    IT IS A TUPLE PASSED BY THE CALLER, NOT A MUTABLE MODULE-LEVEL REGISTRY. A global
    that tests append to is a global that leaks between tests; `changes_page` takes
    `collectors` as an argument defaulting to `RECORD_COLLECTORS`, so extension is a
    parameter rather than a side effect.
    """

    kind: str
    read: Callable[[Any], Iterable[ChangeEntry]]


def _experiment_entries(exp: Any) -> Iterator[ChangeEntry]:
    """The record's own entry — exactly one, always present.

    Always present even for a record that has never been written since creation:
    `Experiment.__post_init__` anchors `updated_utc` to `created_utc` and `generation`
    to a deterministic legacy value, so there is no state in which this yields nothing.
    A feed whose first page could be empty would make "nothing has changed" and "this
    record does not exist" look identical to a client.
    """
    yield ChangeEntry(
        kind="experiment",
        entity_id=exp.id,
        updated_utc=exp.updated_utc,
        rev=exp.rev,
        generation=exp.generation,
    )


def _run_entries(exp: Any) -> Iterator[ChangeEntry]:
    """One entry per run, read from `exp.runs` directly.

    `exp.runs` RATHER THAN `exp.sorted_runs()`: this generator's output is sorted by
    `key` moments later, so paying for a second sort on `(ordinal, created_utc, id)`
    would buy an order that is then discarded. The feed's order is deliberately NOT
    the record's presentation order — a feed ordered by ordinal could not be paged by
    a timestamp cursor at all.
    """
    for run in exp.runs:
        yield ChangeEntry(
            kind="run",
            entity_id=run.id,
            updated_utc=run.updated_utc,
            rev=run.rev,
            generation=run.generation,
        )


#: The kinds a RECORD-SCOPED feed serves at this commit. Extended by passing a longer
#: tuple, never by mutating this one.
RECORD_COLLECTORS: tuple[KindCollector, ...] = (
    KindCollector(kind="experiment", read=_experiment_entries),
    KindCollector(kind="run", read=_run_entries),
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


def encode_cursor(key: tuple[str, str, str], *, scope: str) -> str:
    """A key plus its feed identity, as base64url of a compact versioned JSON object.

    OPAQUE BY CONTRACT, NOT BY CRYPTOGRAPHY, and saying which matters. Anyone can
    base64-decode this and read the tuple; it carries no secret and is not meant to.
    "Opaque" here is a rule for CLIENTS — do not construct one, do not parse one, do
    not reason about its contents — enforced by the fact that the server is free to
    change the payload shape behind `CURSOR_VERSION` at any time. A client that has
    hand-built a cursor is a client that breaks on the next version bump, which is why
    the tests below construct one only to prove a bad one is refused.

    Base64URL WITHOUT PADDING so the token is safe in a query string with no escaping
    (`+`, `/` and `=` all need it; `-`, `_` do not).
    """
    payload = {
        "v": CURSOR_VERSION,
        "s": scope,
        "t": key[0],
        "k": key[1],
        "e": key[2],
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


#: `-_` -> `+/`, so a base64url token can be handed to `b64decode(validate=True)`.
#: `urlsafe_b64decode` has no `validate` parameter (signature `(s)`), which is why the
#: translation is done here rather than by asking that function for strictness.
_B64URL_TO_STANDARD = str.maketrans("-_", "+/")


def decode_cursor(token: str, *, scope: str) -> tuple[str, str, str]:
    """The key a cursor names, or `MalformedCursor`.

    STRICT AT EVERY STEP, and every step is a real failure mode rather than defensive
    padding: a token that is not base64url; base64url that is not UTF-8; UTF-8 that is
    not JSON; JSON that is not an object; an object of a version this build does not
    serve; a payload missing a component or carrying a non-string one; and a payload
    whose scope digest belongs to a different feed. Each answers the SAME `422`, so a
    client has one thing to handle, and each records its own `reason`.

    NOTHING IS COERCED. A `t` that arrived as the integer `7` is refused, not
    `str()`-ed — coercing it would build a key that compares against real keys and
    silently answers from a position the caller never asked for.
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
    parts = [payload.get("t"), payload.get("k"), payload.get("e")]
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
    return (parts[0], parts[1], parts[2])  # type: ignore[return-value]


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
    rather than accepted: the runs live inside ONE experiment document that
    `load_experiment` has already read whole, so there is no index to seek into and
    no way to skip an entity without looking at it. What IS avoidable — and is
    avoided — is doing anything expensive per entity. Compare `routes.list_experiments`,
    which is O(runs) per ANSWERED record because it composes drafts it does not thread;
    this function touches five stored attributes per entity and composes nothing.
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
    rather than one past it. A cursor that names an entity which has since changed
    resumes correctly WHENEVER that change moved the entity into a later second,
    because its new key is then later than the old one and so is ahead of the cursor.

    IT DOES **NOT** RESUME CORRECTLY WHEN THE CHANGE LANDED IN THE SAME SECOND, and
    that is stated here rather than only in `GAP_GUARANTEE` because this is the
    comparison it is a property of. `updated_utc` is whole seconds, so a write inside
    the second a key already names moves `rev` without moving the key; `key > start`
    is then false and the change is not reported until the entity moves again. The
    strictness is still right — relaxing it to `>=` would re-emit every entity of the
    boundary second on every poll while STILL missing an entity earlier in that
    second, so it would buy duplicates without buying the gap back. Closing the gap
    properly needs either a sub-second stamp (a storage change, in `workspace`) or a
    lagging watermark that deliberately trades the no-duplicate property for it;
    neither is this function's to choose, and `test_change_feed.py` measures the
    exposure so it cannot be re-described as absent.

    MEASURED, at this commit, over HTTP against a record created through
    `POST /api/experiments` and given N runs in process (the `_with_runs` harness
    `test_pending_reads_are_boundable.py` uses). `resolved_run_draft`, `export_draft`
    and `Experiment.pending` are counted by monkeypatching them for the request::

        runs   GET /changes bytes   entries   resolved_run_draft   export_draft   pending
          25                4,520        26                    0              0        0
         250                8,457        50                    0              0        0
        1000                8,457        50                    0              0        0

    THE BYTE COLUMN WAS WRONG ONCE AND IS RECORDED RATHER THAN QUIETLY REPLACED. It
    first read 4,676 / 8,757 / 8,757, measured honestly — and then the wire key was
    renamed from `version_token` to `version` (six characters shorter, once per entry:
    26 x 6 = 156, 50 x 6 = 300) and the table was not re-run. The numbers above are
    from the benchmark below, after the rename. The lesson is the cheap one and worth
    keeping: a measurement is invalidated by a change to the thing measured, including
    a change that looks purely cosmetic.

    Two things that table is claiming. The response is FLAT past the window — 250 runs
    and 1,000 runs are BYTE-IDENTICAL in length, because every entry is the same width
    (a 26-character id, a 16-hex generation, a one-second timestamp) and the window
    stops at 50 either way. And the three expensive derivations are entered ZERO times
    at every size, which is what makes the flatness durable rather than incidental: a
    future edit reaching for `resolved_run_draft` here would give the feed the shape
    `routes.list_experiments` already has, and the counter test fails if it does.

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
