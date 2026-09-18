"""THE READ SURFACE OVER THE EXTENDED CONTEXT COMPANION — `CTX-004`. SELECTs nothing,
writes nothing, and decides no verdict.

WHY THIS IS ITS OWN MODULE
==========================

:mod:`isaac_api.extended_context` is the MODEL: frozen dataclasses, pure functions,
and a stated contract of *"no I/O, no clock, no id minting"*. Paging, windowing and
wire shape are a different concern with a different failure mode, and this repository
has already split exactly this way twice — ``activity_history.py`` beside
``activity.py``, and ``revision_history.py`` beside ``submission_store.py``, whose own
docstring gives the reason: growing the model module with a read surface *"would blur
what the module is for"*.

So the model stays the model. Nothing here mutates an :class:`ExtendedContext`, and
nothing here interprets a stored literal.

WHAT `CTX-004` FOUND, AND WHAT THIS MODULE IS THE ANSWER TO
===========================================================

The companion was durable, exported to ``records/<ULID>.context.json``, and served on
the wire — and then it stopped. Measured at ``938e4829``:

* ``rg --text --files-with-matches "extended_context|extendedContext" apps/web/src/``
  returned **nothing**: no frontend file mentioned it, and ``ApiArtifactsResponse`` did
  not declare either of the two keys ``GET .../artifacts`` serves.
* ``GET .../artifacts`` is the ONLY route that served the companion's content, and it
  serves it **only once the record has been exported** — the non-exported branch
  answers ``extended_context: None``. So a record that had imported extended context
  and had not yet exported had **no read surface for it at all**, in any client.

That second point is why this module exists rather than a frontend adapter over the
artifacts route: the durable companion lives at ``extended_context.STATE_KEY``, beside
``draft``, and is readable the moment it is written. Reading the EXPORTED FILE and
reading the RECORD'S OWN STATE are different claims, and only the second is available
before an export.

THREE THINGS THIS MODULE MUST NEVER DO
======================================

1. **It must never imply that a level-4 entry is an official field value.** Every
   entry already serialises ``is_official_field_value: False`` from a derived property
   with no field behind it, and :data:`extended_context.NOT_OFFICIAL_CLAIM` is carried
   in every response this module builds — not as decoration but because it is the one
   claim a surface must not get wrong about these entries.
2. **It must never interpret, normalise, unit-convert or classify a stored literal.**
   ``CLAUDE.md`` §5. Where a meaning cannot be presented, the literal and its source
   are presented, which is exactly what the artifact is for.
3. **It must never report the length of the page as the size of the record.**
   ``CLAUDE.md`` §11's 2026-09-02 rule, and ``historical_import.ARCHIVE_PAGE_WINDOW``
   states it for this feature's own producer: *the window bounds what is FETCHED,
   never what is CLAIMED*. Every count below is taken from the whole collection.
"""

from __future__ import annotations

from typing import Any, Sequence

from . import extended_context as ctx
from .bl15 import mapping as mp

__all__ = [
    "EXTENDED_CONTEXT_LIMIT_MAX",
    "EXTENDED_CONTEXT_WINDOW",
    "context_page",
    "context_summary",
    "entry_view",
]


#: How many companion entries one page returns by default.
#:
#: 50, WHICH IS THIS REPOSITORY'S ESTABLISHED ANSWER to "how much does a bounded read
#: hand back": ``serialize.PENDING_WINDOW``, ``change_feed.CHANGE_FEED_WINDOW`` and
#: ``activity_history.ACTIVITY_WINDOW`` are all 50, and ``ACTIVITY_WINDOW``'s own note
#: argues that a fourth number would be a fourth thing for a reader to hold in their
#: head with no measurement behind the difference.
#:
#: Deliberately NOT imported from any of the three, for the reason that note also
#: gives: the bounds are free to diverge if one is ever re-measured, and importing
#: would make a change to one silently move the others.
EXTENDED_CONTEXT_WINDOW = 50

#: The server maximum. A caller asking for more is CLAMPED, never refused —
#: ``activity_history.ACTIVITY_LIMIT_MAX``'s rule, and it is the same 200: a ``422`` on
#: ``limit=1000`` would make a client guess the ceiling, and the effective limit is
#: reported back in every response so the clamp is observable rather than silent.
#:
#: **THIS ONE IS DERIVED RATHER THAN MATCHED.** ``historical_import``'s
#: ``MAX_EXTENDED_CONTEXT_ENTRIES`` is 1,000 — the most entries ONE import may
#: contribute to a record — so a ceiling of 200 means a complete read of an import's
#: whole contribution is five requests. That is the relation the number is chosen
#: against; it is not a coincidence that it equals ``ARCHIVE_PAGE_WINDOW``, which
#: bounds the same feature's producer for the same reason.
EXTENDED_CONTEXT_LIMIT_MAX = 200


def entry_view(entry: ctx.ContextEntry) -> dict:
    """The wire shape of one companion entry.

    IT IS ``to_state()`` UNCHANGED, for the reason ``activity_history.event_view``
    gives about its own events: there is nothing in a companion entry that is fit to
    persist and unfit to serve. An entry holds the verbatim literal a source stated,
    the source, the locator, and the registry's own reason — all four of which are the
    POINT of the artifact, and none of which is a credential, a draft value or a
    scientific interpretation.

    The function exists anyway, rather than callers reaching for ``to_state()``, so
    that the day the two must diverge there is one place to make them diverge.
    """
    return entry.to_state()


def context_summary(context: ctx.ExtendedContext | None) -> dict:
    """What this record's companion HOLDS, in constant size whatever it holds.

    Every member is an integer, a short string, or a mapping with one key per
    ``DEC-41`` level — so this is safe to compose into a response that also carries a
    page, and safe to read on a record with a thousand entries.

    **``None`` IS THE NORMAL STATE AND IS NOT AN ERROR.** Extended context arrives
    through historical import and through nothing else in this build, so almost every
    record has none. ``present: False`` with ``entry_count: 0`` is what that looks
    like, and a caller must not have to distinguish an absent companion from a
    missing artifact — ``routes.get_artifacts``'s own comment argues the same point
    for the exported file, and deliberately keeps the companion out of the ``stale``
    decision for it.
    """
    if context is None:
        return {
            "present": False,
            "entry_count": 0,
            "unreadable_entries": 0,
            "concept_count": 0,
            "run_count": 0,
            "by_level": {str(level): 0 for level in mp.PLACEMENT_LEVELS},
            "generated_utc": "",
            "artifact_kind": ctx.ARTIFACT_KIND,
            "artifact_version": ctx.ARTIFACT_VERSION,
            "open_domain_questions": [],
        }
    return {
        # `present` IS ABOUT THE DOCUMENT, NOT ABOUT ITS CONTENT. A companion that
        # holds only entries this build cannot read is PRESENT and has an
        # `entry_count` of 0, and collapsing those two would make an unreadable
        # companion indistinguishable from no companion — which is the one outcome
        # `extended_context.hydrate`'s "never discards" promise exists to prevent.
        "present": True,
        "entry_count": len(context.entries),
        "unreadable_entries": len(context.unreadable),
        "concept_count": len(context.concepts()),
        "run_count": len(context.run_ids()),
        "by_level": dict(context.by_level()),
        "generated_utc": context.generated_utc,
        "artifact_kind": ctx.ARTIFACT_KIND,
        "artifact_version": context.artifact_version,
        "open_domain_questions": list(context.open_questions()),
    }


def _select(
    context: ctx.ExtendedContext,
    *,
    run_id: str | None,
    concept: str | None,
) -> Sequence[ctx.ContextEntry]:
    """The entries matching every supplied filter, in STORED ORDER.

    **``run_id`` MEANS ``applying_to_run`` AND NOT ``for_run``, AND THE CHOICE IS
    LOAD-BEARING.** The model is emphatic that the two are different claims: ``for_run``
    is *entries taken on this run*, ``applying_to_run`` is *everything that applies to
    it*, which includes the experiment-scoped readings a run INHERITS. Serving the
    narrow one would hide the beamtime-wide statements — the ones a reader asking
    "what context applies to this measurement?" most needs — and would do it
    silently, because a short list looks like a complete one.

    Nothing is copied or flattened to achieve that: every entry still carries its own
    ``scope`` and its own ``run_id``, so a caller that wants only the run's own
    entries can tell them apart, and the inheritance stays visible rather than being
    asserted. That is ``ExtendedContext.applying_to_run``'s own stated posture and
    this function only forwards it.

    ``concept`` is an EXACT match and is never fuzzy, stemmed or case-folded. A
    concept name is an identifier the registry owns; matching it loosely would answer
    a question the caller did not ask and would do so under the caller's own label.
    """
    selected: Sequence[ctx.ContextEntry]
    selected = (
        context.applying_to_run(run_id) if run_id is not None else context.entries
    )
    if concept is not None:
        selected = tuple(e for e in selected if e.concept == concept)
    return selected


def context_page(
    exp,
    *,
    limit: int | None = None,
    offset: int = 0,
    run_id: str | None = None,
    concept: str | None = None,
) -> dict:
    """One bounded page of a record's extended context, with honest totals.

    **OLDEST-FIRST, IN STORED ORDER, AND THAT IS WHAT MAKES ``offset`` SAFE HERE.**
    ``proposals`` had to grow an ``order=newest_first`` parameter after a measured
    defect (``CLAUDE.md`` §11, 2026-09-02) because a new arrival past the window was
    counted but not reachable. **That defect cannot occur here, and the reason is
    structural rather than lucky:** ``Experiment.add_extended_context_entries`` only
    ever APPENDS — there is no ``remove_extended_context_entry`` and no
    ``replace_extended_context_entry``, and ``extended_context`` exposes no mutation at
    all — so an arrival lands at the END, after the offsets a caller has already read,
    and shifts none of them. A newest-first order over an append-only list would make
    every offset a caller holds wrong the moment anything arrived, which is the
    opposite trade to the one ``proposals`` faced.

    ``total`` is what the RECORD holds and ``matched`` is what satisfied the filters —
    both read off the whole collection, so a filtered or paged read never understates
    the record. ``returned`` is the length of this page and is the ONLY number here
    derived from it.

    ``unreadable_entries`` counts stored rows this build could not read. They are
    preserved in the record untouched and COUNTED rather than rendered, because this
    server cannot say what a refused row contains without inventing it — which is
    ``extended_context.hydrate``'s "never discards" promise kept at the read surface
    as well as in the document.
    """
    if offset < 0:
        raise ValueError("offset must not be negative")
    effective_limit = EXTENDED_CONTEXT_WINDOW if limit is None else limit
    if effective_limit < 0:
        raise ValueError("limit must not be negative")
    effective_limit = min(effective_limit, EXTENDED_CONTEXT_LIMIT_MAX)

    context = getattr(exp, "extended_context", None)
    summary = context_summary(context)
    if context is None:
        matched: Sequence[ctx.ContextEntry] = ()
    else:
        matched = _select(context, run_id=run_id, concept=concept)
    window = list(matched)[offset : offset + effective_limit]

    payload: dict[str, Any] = {
        "entries": [entry_view(entry) for entry in window],
        # `total` AND `entry_count` ARE THE SAME NUMBER FROM THE SAME EXPRESSION, and
        # that is deliberate rather than redundant: `total` is this repository's
        # paging key (`_page`, `activity_page`) and `entry_count` is the summary's,
        # and a client reading either must get the record's own figure. Taking both
        # from `summary` is what stops them ever disagreeing.
        "total": summary["entry_count"],
        "matched": len(matched),
        "returned": len(window),
        "limit": effective_limit,
        "offset": offset,
        "has_more": offset + len(window) < len(matched),
        # THE COMPANION'S OWN DENIAL, ON THE WIRE, in every response — not left to a
        # client's documentation. `routes`' import summary block already says this for
        # the same reason, in its own words: this is the one claim a surface must not
        # get wrong about these entries.
        "not_official": ctx.NOT_OFFICIAL_CLAIM,
        # `DEC-41`'s levels, served rather than transcribed, so a client naming level 4
        # in its own copy is naming what this server named.
        "placement_hierarchy": {
            str(level): mp.PLACEMENT_NAMES[level] for level in mp.PLACEMENT_LEVELS
        },
    }
    payload.update(summary)
    return payload
