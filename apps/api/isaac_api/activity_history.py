"""The READ path over the append-only activity history. SELECTS NOTHING, WRITES NOTHING.

WHY THIS IS A SEPARATE MODULE FROM :mod:`isaac_api.activity`
============================================================
``DEC-44`` names ``revision_history.py`` as *"the precedent for a read module that is
separate from its write module"*, and this is that split applied one layer in.
:mod:`isaac_api.activity` is the model and the write helper; its central claim is an
inventory claim — **it exposes no mutator at all**, so an event once recorded cannot
be revised or removed. Growing that module with a browsing surface would not break
the claim, but "the module with the model in it" is a much easier thing to review
than "the module with the model and also the filtering and paging".

**A stronger property is available here and is asserted rather than described: this
module performs no attribute assignment and no ``del`` at all.** It reads a list and
returns dictionaries. ``test_activity_channel_guard.py``'s
``test_the_read_module_assigns_nothing_and_deletes_nothing`` pins it by AST
inventory, the same way ``revision_history.py``'s "every ``Q_*`` is a ``SELECT``" is
pinned. *(An earlier revision of this paragraph cited a ``test_activity_history.py``
that does not exist. It is corrected rather than deleted because a false test
citation in committed prose is a defect this repository has shipped before and
recorded in ``CLAUDE.md`` §11.)*

IT TOUCHES NO DATABASE, AND THAT IS THE ONE DIFFERENCE FROM ITS PRECEDENT
=========================================================================
``revision_history.py`` reads relational rows because the submission history lives in
five relational tables. The activity history lives in the experiment's own state
document (:data:`~isaac_api.activity.ACTIVITY_STATE_KEY`; see that module for why no
migration is added), so the rows are already in memory by the time this module is
called. There is no new connection path, no new statement, and no new table —
``db_write.OWNED_TABLES`` is unchanged.

THE ONE THING A CALLER MUST NOT DO WITH THIS MODULE
===================================================
**It must never let a count come from the length of a page.** ``CLAUDE.md`` §11
records the measured version of this defect: a screen took its outstanding-work count
from the bounded list it had fetched and understated the record. So :func:`activity_page`
returns FOUR separate numbers, and the split is the point:

* ``total`` — how many events this record HOLDS, whatever the filter matched;
* ``matched`` — how many satisfied the filters, whatever the page returned;
* ``returned`` — how many are in this page, which is the only one a caller may
  compute from the list it was handed;
* ``unreadable_entries`` — stored entries this build could not present, counted
  rather than rendered.

A caller rendering "showing N of M" must read ``returned`` and ``matched``; a caller
stating how much history exists must read ``total``. Neither is derivable from
``events``.
"""

from __future__ import annotations

from typing import Sequence

from .activity import (
    ACTIVITY_ACTIONS,
    ACTIVITY_CHANNELS,
    CHANNELS_WITHOUT_A_WRITE_SITE,
    ACTIVITY_OBJECT_TYPES,
    ActivityEvent,
)

# RE-EXPORTED, NOT RE-IMPLEMENTED. The canonical order lives on the model
# (`activity.sorted_events`) because `workspace._activity_state_payload` decides the
# bytes on disk with it and this module decides what a reader is handed with it, and
# two sort keys would eventually page a reader past an event the persisted order had
# put somewhere else. It is named in `__all__` here so a caller of the READ module
# does not have to reach into the model to order a list.
from .activity import sorted_events as sorted_events

__all__ = [
    "ACTIVITY_LIMIT_MAX",
    "ACTIVITY_WINDOW",
    "activity_page",
    "event_view",
    "filter_events",
    "sorted_events",
]


#: How many events one page returns by default.
#:
#: 50, WHICH IS THIS REPOSITORY'S ESTABLISHED ANSWER to "how much does a bounded read
#: hand back" — ``serialize.PENDING_WINDOW`` and ``change_feed.CHANGE_FEED_WINDOW`` are
#: both 50, and a third number would be a third thing for a reader to hold in their
#: head with no measurement behind the difference. It is deliberately NOT imported from
#: either: the three bounds are free to diverge if one is ever re-measured, and
#: importing would make a change to one silently move the others.
ACTIVITY_WINDOW = 50

#: The server maximum. A caller asking for more is CLAMPED, never refused —
#: ``change_feed.CHANGE_FEED_LIMIT_MAX``'s rule: a ``422`` on ``limit=1000`` would make
#: a client guess the ceiling, and the effective limit is reported back in every
#: response so the clamp is observable rather than silent.
ACTIVITY_LIMIT_MAX = 200


def filter_events(
    events: Sequence[ActivityEvent],
    *,
    action: str | None = None,
    channel: str | None = None,
    object_type: str | None = None,
    run_id: str | None = None,
    since_seq: int | None = None,
    before_seq: int | None = None,
) -> list[ActivityEvent]:
    """The subset matching every supplied predicate. An unsupplied one matches all.

    ``since_seq`` is EXCLUSIVE and ``before_seq`` is EXCLUSIVE, and both are stated
    here because an off-by-one in either direction is a lost event or a duplicated
    one. ``since_seq=N`` means *strictly after position N*, so a poller that has seen
    up to ``highest_seq`` passes exactly that value and is handed exactly what
    arrived since.

    **A filter value outside the bounded vocabulary is REFUSED, not silently
    unmatched.** ``action="nonsense"`` returning an empty list would tell a caller
    "this record has no such activity", which is a claim about the record; the honest
    answer is that no such action exists. The refusal is a ``ValueError`` here and a
    typed ``422`` at the route — ``CLAUDE.md`` §11's rule that a malformed value in a
    REQUEST may be refused, while a malformed value already PERSISTED must be read.
    """
    if action is not None and action not in ACTIVITY_ACTIONS:
        raise ValueError(f"unknown activity action {action!r}")
    if channel is not None and channel not in ACTIVITY_CHANNELS:
        raise ValueError(f"unknown activity channel {channel!r}")
    if object_type is not None and object_type not in ACTIVITY_OBJECT_TYPES:
        raise ValueError(f"unknown activity object type {object_type!r}")
    selected = []
    for event in events:
        if action is not None and event.action != action:
            continue
        if channel is not None and event.channel != channel:
            continue
        if object_type is not None and event.object_type != object_type:
            continue
        if run_id is not None and event.run_id != run_id:
            continue
        if since_seq is not None and event.seq <= since_seq:
            continue
        if before_seq is not None and event.seq >= before_seq:
            continue
        selected.append(event)
    return selected


def event_view(event: ActivityEvent) -> dict:
    """The wire shape of one event.

    IT IS ``to_state()`` UNCHANGED, and that is deliberate rather than lazy: there is
    nothing in a recorded event that is fit to persist and unfit to serve. An event
    holds no verbatim capture, no credential and no draft content — ``before``/``after``
    are the values the record itself already serves through its own detail route, and
    ``actor`` is either a name a trusted boundary vouched for or the literal
    ``unattributed``.

    The function exists anyway, rather than callers reaching for ``to_state()``, so
    that the day the two must diverge there is one place to make them diverge.
    """
    return event.to_state()


def activity_page(
    exp,
    *,
    limit: int | None = None,
    action: str | None = None,
    channel: str | None = None,
    object_type: str | None = None,
    run_id: str | None = None,
    since_seq: int | None = None,
    before_seq: int | None = None,
    newest_first: bool = True,
) -> dict:
    """One bounded page of an experiment's activity, with four honest counts.

    ``newest_first`` DEFAULTS TO ``True``, and the default is argued rather than
    inherited. ``proposals`` had to grow an ``order=newest_first`` parameter after a
    measured defect (``CLAUDE.md`` §11, 2026-09-02): serving oldest-first meant a new
    arrival past the window was *counted but not reachable*. An audit history is read
    newest-first by every reader who opens it — "what just happened to my record" —
    so the same defect would be the DEFAULT behaviour here. Oldest-first is still
    available, because a reader reconstructing a sequence wants it.

    **The page is taken from the newest end when ``newest_first``, and from the
    oldest end otherwise** — not "sorted then truncated from the front" in both
    cases, which would hand a newest-first caller the oldest 50 in reverse.
    THE CONTINUATION IS TWO KEYS, NOT ONE: ``next_before_seq`` for the newest-first
    direction and ``next_since_seq`` for the oldest-first one, because the two
    directions page through DIFFERENT parameters. Exactly one is non-null on a page
    that has a successor, and both are ``None`` on the last page.
    """
    effective_limit = ACTIVITY_WINDOW if limit is None else limit
    if effective_limit < 0:
        raise ValueError("limit must not be negative")
    effective_limit = min(effective_limit, ACTIVITY_LIMIT_MAX)

    ordered = sorted_events(exp.activity)
    matched = filter_events(
        ordered,
        action=action,
        channel=channel,
        object_type=object_type,
        run_id=run_id,
        since_seq=since_seq,
        before_seq=before_seq,
    )
    if newest_first:
        window = list(reversed(matched))[:effective_limit]
    else:
        window = matched[:effective_limit]

    # THE CURSOR FOR THE NEXT PAGE, AND IT IS TWO CURSORS BECAUSE PAGING IN THE TWO
    # DIRECTIONS USES TWO DIFFERENT PARAMETERS. An earlier draft served ONE
    # `next_before_seq` for both, which was simply wrong for the oldest-first
    # direction: walking forward from the oldest end needs `since_seq`, and handing a
    # caller a `before_seq` there would page them BACKWARDS through history they had
    # already read. Two named keys, exactly one of them non-null, makes the parameter
    # to pass unambiguous instead of something a client has to infer from
    # `newest_first`.
    #
    # Both are `None` rather than a plausible number when the page exhausted the
    # match set: a cursor that always has a value makes a client loop forever on the
    # last page.
    next_before_seq: int | None = None
    next_since_seq: int | None = None
    if window and len(window) < len(matched):
        if newest_first:
            next_before_seq = window[-1].seq
        else:
            next_since_seq = window[-1].seq

    return {
        "events": [event_view(event) for event in window],
        # HOW MANY THIS RECORD HOLDS. Taken from the record's own hydrated list, never
        # from ``window`` — see the module docstring for the measured defect that rule
        # exists for.
        "total": len(ordered),
        # HOW MANY SATISFIED THE FILTERS, whatever the page returned. A client showing
        # "the first 50 of 312 field edits" needs this and cannot derive it.
        "matched": len(matched),
        # THE ONLY NUMBER A CALLER MAY COMPUTE FROM ``events``.
        "returned": len(window),
        # Stored entries this build could not present as events. Preserved verbatim in
        # the document and written back out on every save; counted rather than
        # rendered, because this server cannot say what a refused entry contains
        # without inventing it. Reporting zero when there are some would be the silent
        # discard an append-only history exists to make impossible.
        "unreadable_entries": len(exp.unreadable_activity),
        "limit": effective_limit,
        "newest_first": newest_first,
        # PASS THIS BACK AS `before_seq` — the newest-first continuation.
        "next_before_seq": next_before_seq,
        # PASS THIS BACK AS `since_seq` — the oldest-first continuation. Exactly one
        # of the two is non-null on a page that has a successor; see the comment above.
        "next_since_seq": next_since_seq,
        # THE POSITION A POLLER PASSES BACK AS ``since_seq``. Computed over the WHOLE
        # history rather than over the page, so a filtered or paged read still hands
        # back a resumable coordinate. ``0`` on an empty history, which is
        # ``Run.changed_at_rev``'s "no save has recorded anything here" and is below
        # every real position (``seq >= 1`` by construction).
        "highest_seq": ordered[-1].seq if ordered else 0,
        # The bounded vocabularies, served rather than transcribed, for the reason
        # ``_notes_payload`` serves ``mappable_field_paths``: the alternative is a
        # frontend copy that is free to drift from the set the route enforces.
        "actions": sorted(ACTIVITY_ACTIONS),
        "channels": sorted(ACTIVITY_CHANNELS),
        # 2026-09-22: which channels no write site in this build records, and why — so a
        # filter offering `system` can say it will always be empty rather than imply
        # the record simply has had no such activity yet.
        "channels_without_a_write_site": dict(CHANNELS_WITHOUT_A_WRITE_SITE),
        "object_types": sorted(ACTIVITY_OBJECT_TYPES),
        "experiment_version": exp.version_token(),
    }
