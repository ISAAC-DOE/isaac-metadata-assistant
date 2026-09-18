"""A CROSS-EXPERIMENT **SUMMARY** OF THE APPEND-ONLY ACTIVITY HISTORY. Reads only.

WHAT THIS IS, AND THE ONE THING IT MUST NEVER BECOME
====================================================
``DEC-44`` is explicit in both directions: *"Statistics may SUMMARIZE this history;
Statistics must never be its source of truth."* This module is the summarizing half,
and ``ACT-004`` is the ledger row. The source of truth is
:mod:`isaac_api.activity` — the append-only events themselves — read one record at a
time through :mod:`isaac_api.activity_history` and
``GET /api/experiments/{id}/activity``.

So every figure here is a COUNT OF EVENTS, and nothing here is addressable, citable,
or a substitute for an event. There is no event id in a summary row, no
``before``/``after`` pair, and no way to reconstruct an act from this payload — by
construction rather than by policy. A reader who needs the act itself is sent to the
record's own activity history, which is why every record-shaped row carries the
``experiment_id`` a client turns into a link.

**IT ADDS NO WRITE PATH.** There is no function in this module that assigns to an
event, appends one, removes one or edits one; it takes hydrated
:class:`~isaac_api.workspace.Experiment` rows and returns dictionaries. The activity
history is append-only and this is a reader of it.

WHY IT EXISTS AT ALL — THE MEASURED GAP
=======================================
Activity is stored at :data:`~isaac_api.activity.ACTIVITY_STATE_KEY`, a top-level key
in each experiment's own state document. That placement is
:mod:`isaac_api.activity`'s deliberate choice (it is what makes "no migration" and
"structurally inert to export" true rather than asserted), and its consequence is
that **no cross-experiment reader existed**: every read path was per-record, so a
question like *how much changed this week* had no answer that did not mean N requests
from a client. This module is that reader, in one place, so the arithmetic is done
once and tested once rather than in a frontend loop.

``db_write.OWNED_TABLES`` IS UNCHANGED, no migration is added, and no database
connection is opened here. The rows are already in memory by the time this is called
— the same property :mod:`isaac_api.activity_history` documents about itself.

THE BOUND, AND THE MEASUREMENT THAT CHOSE IT
============================================
Summarizing across experiments is O(workspace), so it is bounded and the bound is
reported. :data:`EXPERIMENT_LIMIT` records are summarized; when the scope holds more,
``scope.truncated`` is ``True``, ``scope.experiments_in_scope`` reports how many the
read enumerated, and every total in the response is a total **over the summarized
subset and no more**. A summary computed over a truncated set that reads as complete
is the exact honesty defect ``CLAUDE.md`` §11 records repeatedly, so the truncation is
on the wire and the caller cannot render the figure without meeting it.

**AND THE MEASUREMENT FOUND THAT THE BOUND IS NOT WHERE THE COST IS, which is
recorded rather than implied.** Measured on this host (Python 3.12, a synthetic
workspace under a temporary directory, one warm read discarded, ``time.perf_counter``
around each call):

===========================  =============================  ==================
workspace                    ``list_experiments_with_``      :func:`summarize`
                             ``hydration`` (the read)        (this module)
===========================  =============================  ==================
100 records x 50 events      0.0259 s                        0.0033 s
250 records x 100 events     0.1232 s                        0.0159 s
500 records x 100 events     0.2750 s                        0.0321 s
700 records x 100 events     0.4248 s                        0.0318 s
===========================  =============================  ==================

Two things in that table, and the second is the one worth carrying:

* the enumeration-and-hydration pass costs roughly **8x** the aggregation at every
  size, and it is paid in full before this module is entered — it is the same pass
  ``GET /api/experiments`` already performs on every load of My Experiments. So
  bounding the aggregation does **not** bound the request, and saying otherwise would
  be exactly the kind of claim this repository has been caught publishing.
* the 700-record row is the bound working and is why it is in the table: the read
  keeps growing (0.2750 -> 0.4248 s) while the aggregation **stops** (0.0321 ->
  0.0318 s) because it summarized 500 of the 700. That is the honest description of
  what the bound buys — a bounded RESPONSE and a bounded per-event loop — and it is
  also the row where ``scope.truncated`` becomes ``True``.

Closing the read half would mean a relational store for activity (a migration, i.e. a
hard stop this slice's authorization does not lift) or a persisted per-record counter
(a second source of truth for a number ``DEC-44`` says the events own). Neither is
this slice's, and both are named here rather than left to be rediscovered.

``EXPERIMENT_LIMIT`` is 500 because at that size the aggregation is ~32 ms against a
read of ~275 ms, so raising it adds to a cost that is already dominated by the read,
and lowering it would truncate a workspace this application can plausibly hold.

WHICH RECORDS ARE SUMMARIZED WHEN THE SCOPE IS LARGER
=====================================================
The **most recently created** ones, and the rule is stated on the wire
(``scope.selection``) rather than left for a reader to infer.
``workspace.list_experiments_with_hydration`` returns rows ordered by ``created_utc``
ascending, so this takes the tail. That is a SELECTION RULE, not a guess about which
records are active: it does not claim the newest records are the busiest, and the
response says which rule it applied so a truncated summary is interpretable instead
of merely disclosed.

THREE THINGS THIS MODULE REFUSES TO COMPUTE
===========================================
**1. A NUMBER OF PEOPLE.** Every event in every deployment of this build carries
``actor: "unattributed"`` — ``ACT-005`` is externally blocked on ``EXT-01``, no
trusted authentication boundary exists, and
``activity.actor_from_identity`` can return nothing else. So a "distinct
collaborators" figure would be structurally ``0``, and ``0`` there is a claim about
*the people* when the true statement is about *the deployment*. This module therefore
reports ``attribution`` as three EVENT counts plus the list of names that were
actually recorded (empty in this build) — never a count of people, and never a
``collaborators`` key that a caller could render as one.

**2. A COMPLETENESS CLAIM.** ``hydration_complete`` is passed IN, from
``list_experiments_with_hydration``'s outcome, and served. This module cannot
discover that a durably-stored row failed to restore, and a summary that reported a
total while silently omitting an unrestored record would be understating a
scientist's work. ``workspace.list_experiments``'s own docstring names that gap as
real and unclosed for two existing endpoints; this one closes it for itself by
disclosing the answer rather than discarding it.

**3. ANYTHING ABOUT A MALFORMED ENTRY'S CONTENT.** Stored entries the model could not
read are COUNTED (``unreadable_entries``) exactly as
``activity_history.activity_page`` counts them, never rendered and never dropped.
``CLAUDE.md`` §11's rule is that a malformed **persisted** value must be READ, not
refused — a read-path refusal has twice taken a whole list screen down in this
repository — so nothing in here raises on a stored event: a wrong-typed one is already
in ``exp.unreadable_activity`` by the time it arrives, and a *readable* event with an
**unparseable timestamp** is counted into its own disclosed bucket rather than being
quietly placed inside or outside the window.

TIME IS DECIDED SERVER-SIDE, AND THE WINDOW TRAVELS WITH THE FIGURE
===================================================================
"This week" is relative to a clock, and two clocks disagree. The window is computed
HERE, from a ``now`` the route reads at request time, and the response carries
``window.since_utc``, ``window.computed_at_utc`` and ``window.days`` — so a client
renders its label FROM THE SAME PAYLOAD the count came out of and the two cannot
disagree. No boundary is computed at import time, so nothing drifts as a process ages.

The window is **inclusive of its start and has no upper bound**: an event counts when
``recorded_utc >= since_utc``. That is deliberate. Clamping the top at ``now`` would
create a silent third bucket for an event timestamped in the future, and this module
would then hold a number it did not report. "Recorded since <instant>" is true of
every event it counts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from .activity import (
    ACTIVITY_ACTIONS,
    ACTIVITY_CHANNELS,
    ACTIVITY_OBJECT_TYPES,
    ACTOR_UNATTRIBUTED,
    ActivityEvent,
)

__all__ = [
    "DEFAULT_WINDOW_DAYS",
    "EXPERIMENT_LIMIT",
    "RECORD_ROWS",
    "SELECTION_MOST_RECENTLY_CREATED",
    "WINDOW_DAYS_MAX",
    "instant",
    "summarize",
]


#: How many experiments one summary reads. See the module docstring for the
#: measurement — and for why this bounds the aggregation and NOT the request.
EXPERIMENT_LIMIT = 500

#: How many changed-record rows the summary carries. A HANDFUL, deliberately:
#: ``DEC-25`` attaches a standing obligation that Statistics be scientist-first, and
#: the measurement behind it (``UX-017``: 3,820 px, 422 visible text elements) is the
#: acceptance bar. A row per record would make this section a second My Experiments.
#: The TRUE number of changed records is served separately as
#: ``changed_records.total``, so the short list never stands in for the count.
RECORD_ROWS = 5

#: The default window. SEVEN DAYS, because the question this summary exists to answer
#: is "what changed this week" and a default of "all time" would answer a different
#: one. Every response states the window it used.
DEFAULT_WINDOW_DAYS = 7

#: The largest window a caller may ask for. A ceiling rather than a refusal of large
#: values is ``activity_history.ACTIVITY_LIMIT_MAX``'s rule; here the route declares
#: the bound in OpenAPI so an out-of-range request is refused at the boundary with the
#: admissible range, which is what tells a caller the ceiling instead of making them
#: guess it.
WINDOW_DAYS_MAX = 365

#: The selection rule applied when the scope holds more than :data:`EXPERIMENT_LIMIT`.
#: Served as a token so a client renders the rule rather than inventing one.
SELECTION_MOST_RECENTLY_CREATED = "most_recently_created"

#: The one timestamp format this module writes, matching ``workspace._now_iso``
#: exactly so a ``since_utc`` served here is comparable to a ``recorded_utc`` stored
#: there without a client reformatting either.
_WIRE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def instant(when: datetime) -> str:
    """One UTC instant in this application's wire format.

    Requires an aware datetime and REFUSES a naive one, rather than assuming UTC:
    guessing a timezone is exactly the class of invention ``CLAUDE.md`` §5 forbids,
    and the only caller is a route that reads ``datetime.now(timezone.utc)``.
    """
    if when.tzinfo is None:
        raise ValueError(
            "a naive datetime has no instant to serve; pass an aware one "
            "(datetime.now(timezone.utc)) rather than letting this module assume a zone"
        )
    return when.astimezone(timezone.utc).strftime(_WIRE_FORMAT)


def _parse_recorded(value: object) -> datetime | None:
    """A stored ``recorded_utc`` as an aware datetime, or ``None`` when unreadable.

    ``None`` IS NOT "OUTSIDE THE WINDOW", and the caller must not treat it as such:
    it means *this event's time could not be read*, which is a third answer and is
    reported as its own count. Silently bucketing it either way would make one of the
    two window figures wrong by an amount nothing on the wire discloses.

    Tolerant of the trailing ``Z`` (which ``datetime.fromisoformat`` accepts only from
    Python 3.11) and intolerant of everything else, including a naive timestamp — see
    :func:`instant` for why a zone is never assumed.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _latest(events: Sequence[ActivityEvent]) -> ActivityEvent:
    """The newest event by the canonical order, in one pass.

    ``max`` on ``(seq, id)`` rather than ``sorted_events(events)[-1]``, and the two
    are the SAME event by construction because that is ``activity.sorted_events``'
    own key — stated here because a reader is entitled to check it, and pinned by
    ``test_activity_summary.py`` so a future change to the canonical key cannot make
    this silently disagree with what the per-record history serves.
    """
    return max(events, key=lambda event: (event.seq, event.id))


def _zeroed(vocabulary: Iterable[str]) -> dict[str, int]:
    """A complete count map over a bounded vocabulary, every key at zero.

    COMPLETE rather than sparse, so the response shape does not change with the data
    and a client never has to branch on a key's presence to read a count. The
    vocabularies come from :mod:`isaac_api.activity` and are never transcribed here.
    """
    return {term: 0 for term in sorted(vocabulary)}


def summarize(
    experiments: Sequence,
    *,
    now: datetime,
    window_days: int = DEFAULT_WINDOW_DAYS,
    hydration_complete: bool,
    experiment_limit: int = EXPERIMENT_LIMIT,
    record_rows: int = RECORD_ROWS,
) -> dict:
    """One cross-experiment activity summary. Pure, and it reads no clock of its own.

    ``now`` is an argument rather than a call to ``datetime.now`` inside, for the
    reason ``statisticsModel.ts`` holds no clock: a function that reads the time
    cannot be tested for what it says about a boundary, and this one's whole subject
    is a boundary.

    ``window_days`` is validated here as well as at the route, so a direct caller
    cannot produce a window with no meaning. ``hydration_complete`` has NO DEFAULT on
    purpose: it is a completeness claim about the input, this module cannot discover
    it, and a default would let a caller publish "complete" by omission.
    """
    if isinstance(window_days, bool) or not isinstance(window_days, int):
        raise ValueError(
            f"window_days must be an integer number of days, not "
            f"{type(window_days).__name__}"
        )
    if window_days < 1 or window_days > WINDOW_DAYS_MAX:
        raise ValueError(
            f"window_days must be between 1 and {WINDOW_DAYS_MAX}; got {window_days}"
        )
    if experiment_limit < 0 or record_rows < 0:
        raise ValueError("experiment_limit and record_rows must not be negative")

    computed_at = now.astimezone(timezone.utc) if now.tzinfo else None
    if computed_at is None:
        raise ValueError(
            "a naive `now` has no instant to compute a window from; pass "
            "datetime.now(timezone.utc)"
        )
    since = computed_at - timedelta(days=window_days)

    in_scope = len(experiments)
    # THE TAIL, because the input is ordered by `created_utc` ASCENDING. See the
    # module docstring: this is a stated selection rule, not a claim that the newest
    # records are the busiest ones.
    summarized = list(experiments[-experiment_limit:]) if experiment_limit else []

    events_all_time = 0
    events_in_window = 0
    events_unreadable_timestamp = 0
    unreadable_entries = 0
    by_action = _zeroed(ACTIVITY_ACTIONS)
    by_channel = _zeroed(ACTIVITY_CHANNELS)
    by_object_type = _zeroed(ACTIVITY_OBJECT_TYPES)
    attributed_events = 0
    unattributed_events = 0
    attributed_names: set[str] = set()
    changed: list[dict] = []

    for exp in summarized:
        events = list(getattr(exp, "activity", []) or [])
        unreadable_entries += len(getattr(exp, "unreadable_activity", []) or [])
        events_all_time += len(events)
        window_events: list[ActivityEvent] = []
        for event in events:
            recorded = _parse_recorded(event.recorded_utc)
            if recorded is None:
                # COUNTED, NOT BUCKETED. See `_parse_recorded`.
                events_unreadable_timestamp += 1
                continue
            if recorded < since:
                continue
            window_events.append(event)

        for event in window_events:
            events_in_window += 1
            # `.get`-free increments would raise on a vocabulary this build does not
            # have — but an event carrying one cannot exist: `ActivityEvent` refuses
            # an unknown action, channel or object type at construction, so a stored
            # entry with a fifth channel is already in `unreadable_activity`. The
            # membership check is belt-and-braces and is deliberately silent rather
            # than inventing a bucket.
            if event.action in by_action:
                by_action[event.action] += 1
            if event.channel in by_channel:
                by_channel[event.channel] += 1
            if event.object_type in by_object_type:
                by_object_type[event.object_type] += 1
            if event.actor == ACTOR_UNATTRIBUTED:
                unattributed_events += 1
            else:
                attributed_events += 1
                attributed_names.add(event.actor)

        if window_events:
            newest = _latest(window_events)
            changed.append(
                {
                    "experiment_id": getattr(exp, "id", ""),
                    "title": getattr(exp, "title", ""),
                    "events_in_window": len(window_events),
                    "last_event_utc": newest.recorded_utc,
                    "last_action": newest.action,
                    "last_seq": newest.seq,
                }
            )

    # DETERMINISTIC ORDER, and the tie-break is the id so two records with equal
    # counts cannot swap places between two reads of the same workspace. Busiest
    # first, because the question the list answers is "where did the work happen".
    changed.sort(key=lambda row: (-row["events_in_window"], row["experiment_id"]))
    changed_rows = changed[:record_rows] if record_rows else []

    # THE NONZERO SLICES, ORDERED HERE RATHER THAN IN A CLIENT, so every consumer
    # renders one order and a test can pin it. Descending by count, then by name.
    # These are ORDERINGS of the complete maps above, never a replacement for them:
    # `by_action` still carries every verb in the vocabulary at its true count.
    def _ranked(counts: dict[str, int]) -> list[dict]:
        present = [(name, n) for name, n in counts.items() if n > 0]
        present.sort(key=lambda pair: (-pair[1], pair[0]))
        return [{"name": name, "count": n} for name, n in present]

    ranked_actions = _ranked(by_action)
    ranked_channels = _ranked(by_channel)

    return {
        # ---- the window, so a label cannot disagree with its figure -------------
        "window": {
            "days": window_days,
            # INCLUSIVE, and with no upper bound: an event counts when its
            # `recorded_utc` is at or after this instant. See the module docstring.
            "since_utc": instant(since),
            "computed_at_utc": instant(computed_at),
        },
        # ---- what this summary actually covered ---------------------------------
        "scope": {
            "experiments_in_scope": in_scope,
            "experiments_summarized": len(summarized),
            "experiment_limit": experiment_limit,
            "truncated": len(summarized) < in_scope,
            "selection": SELECTION_MOST_RECENTLY_CREATED,
            # PASSED IN, never discovered here. A false `true` would understate a
            # scientist's work without saying so.
            "hydration_complete": bool(hydration_complete),
        },
        # ---- the counts. EVERY ONE IS OVER `scope.experiments_summarized` --------
        "totals": {
            "events_in_window": events_in_window,
            "events_all_time": events_all_time,
            # Readable events whose stored timestamp this build could not parse. They
            # ARE in `events_all_time` and are in NEITHER window bucket, which is why
            # they are reported rather than folded into one.
            "events_with_unreadable_timestamp": events_unreadable_timestamp,
            # Stored entries the model could not read at all — counted exactly as
            # `activity_history.activity_page` counts them, never rendered.
            "unreadable_entries": unreadable_entries,
        },
        # ---- WHAT changed, and through which surface ----------------------------
        # Complete maps over the server's own bounded vocabularies, plus the ranked
        # nonzero slices. `*_with_events` is the TRUE number of distinct kinds seen,
        # so a client showing the first few never has to take a count from a list.
        "by_action": by_action,
        "by_channel": by_channel,
        "by_object_type": by_object_type,
        "ranked_actions": ranked_actions,
        "actions_with_events": len(ranked_actions),
        "ranked_channels": ranked_channels,
        "channels_with_events": len(ranked_channels),
        # ---- WHO. THREE EVENT COUNTS AND A LIST OF NAMES — NEVER A HEADCOUNT -----
        "attribution": {
            "unattributed_events": unattributed_events,
            "attributed_events": attributed_events,
            # The names actually recorded. EMPTY in this build, because
            # `ACT-005` is blocked on `EXT-01` and nothing can mint an actor. A
            # LIST rather than a number on purpose: a count of names invites
            # rendering "0 collaborators", which is a claim about people where the
            # true statement is about the deployment.
            "attributed_actors": sorted(attributed_names),
            # Why the above reads the way it does, as a token a client can branch on
            # rather than a sentence it has to parse.
            "actor_basis": ACTOR_UNATTRIBUTED,
        },
        # ---- WHERE. Every row is addressable: `experiment_id` is the drill-down. --
        "changed_records": {
            "rows": changed_rows,
            # HOW MANY RECORDS CHANGED IN THE WINDOW, over the summarized set. NOT
            # `len(rows)` — `CLAUDE.md` §11 records the measured defect of a count
            # taken from a bounded list, and this is the same shape.
            "total": len(changed),
            "returned": len(changed_rows),
            "limit": record_rows,
        },
        # The server's own vocabularies, SERVED rather than transcribed, for
        # `activity_page`'s reason: a frontend copy is free to drift from the set the
        # routes enforce.
        "actions": sorted(ACTIVITY_ACTIONS),
        "channels": sorted(ACTIVITY_CHANNELS),
        "object_types": sorted(ACTIVITY_OBJECT_TYPES),
    }
