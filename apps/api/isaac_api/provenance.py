"""Provenance, unified — TWO INDEPENDENT DIMENSIONS, derived and never stored.

WHY THIS MODULE EXISTS
======================

"Where did this value come from?" and "how well is it backed?" are two different
questions, and this repository answers them across at least six unrelated closed
vocabularies:

* ``isaac_records.models.SOURCE_TYPES`` — the EVIDENCE type system (truth core).
* ``isaac_api.notes.NOTE_SOURCES`` — what produced a captured note. Deliberately
  NOT an evidence type; see ``notes.py``'s "WHY A NOTE CARRIES NO source_type".
* ``workspace.PROVENANCE_INHERITED`` / ``PROVENANCE_OVERRIDDEN`` — how a RUN comes
  to hold a record-level value, surfaced by ``routes._resolution_state`` as
  ``inherited`` / ``overridden`` / ``absent``.
* ``isaac_records.models.STATUSES`` — the draft field status (truth core).
* ``evidence_classify`` — the six evidence-SUPPORT classes.
* ``notes.NOTE_STATES`` — a note's review state.

A scientist reading a record has to hold all six in their head to answer two
questions. This module answers exactly those two, as two SEPARATE dimensions,
by READING what those vocabularies already say. It is a VIEW.

WHAT IT IS NOT
==============

* It is **not** a store. Nothing here is persisted, no new field is written to a
  draft, a run, a note or a record, and no new vocabulary is added to the truth
  core. Every value below is recomputed from stored data on every call.
* It is **not** a verdict. No result carries ``ok`` / ``valid`` / ``exportable``
  / ``complete``. Naming a field ``supported`` on the review dimension does not
  make a record exportable and does not make it schema-valid; those decisions
  stay in the frozen truth core (``official.py`` / ``export.py`` / ``audit.py``),
  which this module does not touch and does not import.
* It is **not** a second copy of anything. Conflict detection is delegated to
  ``evidence_classify.classify_fields``; the evidence trail is read through
  ``serialize.evidence_trail_from_draft``; inheritance is read through
  ``workspace.resolve_inherited`` (the caller passes its output in). The only
  ISAAC-core import is the ``SOURCE_TYPES`` tuple itself, so the mapping table
  below cannot silently fall out of date with the vocabulary it maps.

THE TWO DIMENSIONS ARE INDEPENDENT, AND THAT IS ENFORCED BY SHAPE
================================================================

:func:`review_state` does not take an origin, and there is no code path in this
module that lets one decide the other. That is deliberate and load-bearing: the
single most tempting mistake in a provenance model is to let ``file`` (or
``derived``, or ``assistant``) read as "backed", when where a value came from
says nothing at all about whether anything establishes it. A value read out of a
spreadsheet can be entirely unconfirmed; a value proposed by a rule can be a
candidate nobody has accepted.

Pure, non-mutating, deterministic, Graphify-free.
"""

from __future__ import annotations

from isaac_records.models import SOURCE_TYPES

from . import conflict_resolution as cr
from . import evidence_classify, notes as notes_module, serialize, workspace as ws

# =============================================================================
# Dimension 1 — ORIGIN: where the value came from.
# =============================================================================

#: A person supplied this value through this application. Today that means an
#: ``user_confirmation`` evidence entry, which is the ONLY evidence type this
#: application mints for a person's own act (``POST .../answers`` /
#: ``POST .../edit`` with ``confirmed_by_user: true``).
ORIGIN_MANUAL = "manual"

#: Read out of an artifact — a document, a spreadsheet, a screenshot, a raw-file
#: listing, or a captured web form.
ORIGIN_FILE = "file"

#: A spoken capture that was transcribed. See :data:`NOTE_SOURCE_ORIGIN` — and
#: read the reachability note there before assuming this build produces one.
ORIGIN_VOICE = "voice"

#: This RUN does not hold the value; it resolves to the record-level value it
#: inherits. Read from ``workspace.resolve_inherited``, never stored on the run
#: (contract §2 D2: inheritance is by reference, never by copy).
ORIGIN_INHERITED = "inherited"

#: An assistant produced the value. **NOTHING IN THIS BUILD PRODUCES THIS.**
#: ``isaac_records.models.SOURCE_TYPES`` has no ``assistant`` member and
#: ``notes.NOTE_SOURCES`` has none either, so no mapping below can emit it and no
#: stored document can be read into it. The member exists so that the dimension
#: is describable as a whole; it is pinned as unreachable by
#: ``test_provenance.py``. Do not add a mapping to it without an actual producer,
#: and do not surface it in any static UI list — that would advertise a
#: capability this build does not have.
ORIGIN_ASSISTANT = "assistant"

#: Produced by a documented derivation RULE (``source_type == "derivation"``).
#: Deterministic and rule-backed — which is a statement about the mechanism, not
#: about whether anybody has accepted the result.
ORIGIN_DERIVED = "derived"

#: A stored evidence entry backs this value, but this build cannot name the
#: channel that produced it — the entry records a ``source_type`` outside
#: :data:`SOURCE_TYPE_ORIGIN`, or records none at all.
#:
#: DELIBERATELY NOT :data:`ORIGIN_UNKNOWN`. The two are different facts: here a
#: citation demonstrably exists and only its channel is unnameable, whereas
#: ``unknown`` says nothing at all is recorded to derive an origin from. Stored
#: documents are untrusted input everywhere else in this package (see
#: ``serialize``'s per-item isolation and ``workspace._hydrate_notes``), and the
#: frontend already renders an unrecognised source type verbatim with an
#: ``src-unknown`` class rather than crashing — so this arm describes data this
#: application can be handed, even though no writer here mints it.
ORIGIN_EVIDENCE = "evidence"

#: Nothing stored on this item says where the value came from. A POSITIVE
#: statement about the record — "no origin is recorded" — and the answer whenever
#: an origin cannot be determined. Never a plausible default (CLAUDE.md §5).
ORIGIN_UNKNOWN = "unknown"

#: The closed origin vocabulary. Order here is declaration order and carries NO
#: precedence meaning — see :data:`ORIGIN_PRECEDENCE` for that.
ORIGINS: tuple[str, ...] = (
    ORIGIN_MANUAL,
    ORIGIN_FILE,
    ORIGIN_VOICE,
    ORIGIN_INHERITED,
    ORIGIN_ASSISTANT,
    ORIGIN_DERIVED,
    ORIGIN_EVIDENCE,
    ORIGIN_UNKNOWN,
)

#: EVERY member of ``isaac_records.models.SOURCE_TYPES``, mapped. Exhaustiveness
#: is pinned by ``test_provenance.py`` against the tuple itself, so adding an
#: eighth evidence type to the truth core fails here rather than silently
#: producing :data:`ORIGIN_EVIDENCE` for it.
#:
#: ``web_form`` IS A FILE, NOT A MANUAL ENTRY, and this is the one judgement call
#: in the table. The reasoning, checkable in this repository:
#:
#: * ``docs/extraction.md:54`` describes it as a "Web-form screenshot", produced
#:   by the vision extraction row alongside ``screenshot``, cited with a
#:   ``source_file`` and a ``<section> → <field>`` locator.
#: * The committed draft fixture ``tests/fixtures/cuo_xanes_draft.json`` cites it
#:   exactly that way — ``source_file: "examples/webform_dump.txt"`` with a
#:   locator and a quote.
#: * ``user_confirmation`` is the ONLY evidence type this application mints when
#:   a person supplies a value here; nothing in this build ever writes
#:   ``web_form``.
#:
#: So a ``web_form`` entry is an artifact the extractor READ — a form the
#: scientist filled in somewhere else and whose capture was ingested — not a
#: person typing into ISAAC. Calling it ``manual`` would credit this application
#: with a human act it did not witness.
SOURCE_TYPE_ORIGIN: dict[str, str] = {
    # A person answered a question in this application. The strongest provenance
    # ISAAC records, and the only human-act evidence type it mints.
    "user_confirmation": ORIGIN_MANUAL,
    # Artifacts the extractor read. All four cite a source_file + locator.
    "document": ORIGIN_FILE,
    "spreadsheet": ORIGIN_FILE,
    "screenshot": ORIGIN_FILE,
    "file_listing": ORIGIN_FILE,
    # See the paragraph above — an ingested capture of a form, not a typed entry.
    "web_form": ORIGIN_FILE,
    # A documented derivation rule. `draft_validator._has_derivation` requires
    # the rule text to be present for it to count at all.
    "derivation": ORIGIN_DERIVED,
}

#: EVERY member of ``notes.NOTE_SOURCES``, mapped. Also pinned exhaustively.
#:
#: REACHABILITY, STATED PRECISELY, because the two easy summaries are both wrong.
#: ``notes.py``'s own docstring says the only producer today is a person typing
#: into the Unmapped Notes panel, and ``UnmappedNotesPanel.tsx:455`` does hard-code
#: ``'typed_note'``. But ``POST /api/experiments/{id}/notes`` validates ``source``
#: against ``NOTE_SOURCES`` and accepts ANY member of it, so a direct API caller
#: CAN create a ``transcript`` note today and this module WILL report
#: :data:`ORIGIN_VOICE` for it. What does not exist is a transcription producer:
#: nothing in this build records speech, transcribes anything, or writes such a
#: note on its own. So "unreachable" is false at the API boundary and true of the
#: application — and no surface may present voice capture as a feature that
#: exists. The same holds for ``csv_column``, ``file_listing_line`` and
#: ``extraction_residue``: accepted by the route, produced by nothing.
NOTE_SOURCE_ORIGIN: dict[str, str] = {
    # Someone typed it into this application.
    "typed_note": ORIGIN_MANUAL,
    # A line of a spoken or dictated transcript. See the reachability note above.
    "transcript": ORIGIN_VOICE,
    # All three are content lifted out of an artifact this application read: a
    # CSV column, a line of a raw-file listing, and a label the deterministic
    # extractor saw in an ingested file and refused to guess at.
    "csv_column": ORIGIN_FILE,
    "file_listing_line": ORIGIN_FILE,
    "extraction_residue": ORIGIN_FILE,
}

#: THE ORDER :func:`primary_origin` READS, HIGHEST FIRST. Explicit, total, and
#: pinned — the primary is NEVER "whichever evidence entry happened to be first
#: in the array", because array order is an accident of how a document was
#: written and would make the headline origin of a mixed-origin value unstable.
#:
#: THE PRINCIPLE: a mixed-origin value is announced under the origin a reader most
#: needs to know about, which is the one carrying the LEAST direct human
#: accountability — never under its most reassuring source. A field backed by both
#: a spreadsheet row and a person's confirmation leads with ``file``, because
#: "part of this came out of a file" is the half a reader can check and the half
#: they might otherwise miss. The full set travels beside it, so nothing is lost.
#:
#: :data:`ORIGIN_INHERITED` leads regardless, as a structural exception rather than
#: an accountability judgement: for a run it is not a claim about how the value was
#: produced but about WHOSE value it is — the run does not hold it at all.
#: :data:`ORIGIN_UNKNOWN` is last so that any determinate origin outranks it; it is
#: the primary only when it is the whole set.
ORIGIN_PRECEDENCE: tuple[str, ...] = (
    # Not this run's value at all.
    ORIGIN_INHERITED,
    # Machine-generated prose. Unreachable today; ranked first among the
    # produced origins so that it can never be masked by a reassuring one.
    ORIGIN_ASSISTANT,
    # A citation exists but its channel cannot be named — less accountable than
    # a rule, whose text is on the entry and can be read.
    ORIGIN_EVIDENCE,
    # Rule-backed and deterministic, but nobody has accepted the result.
    ORIGIN_DERIVED,
    # A human act, but machine-transcribed, and transcription is lossy in a way
    # reading a stored file is not.
    ORIGIN_VOICE,
    # Deterministic extraction from a stored artifact.
    ORIGIN_FILE,
    # A person said so, in this application. The most accountable origin there
    # is, so it never displaces another one as the headline.
    ORIGIN_MANUAL,
    # Only ever primary when it is the entire set.
    ORIGIN_UNKNOWN,
)


# =============================================================================
# Dimension 2 — REVIEW STATE: what, if anything, establishes the value.
# =============================================================================

#: The value is present, its stored status is ``verified``, and at least one
#: readable evidence entry backs it. NOT a claim of schema validity, completion,
#: or exportability, and NOT the truth core's word "verified" repeated — it is
#: this dimension's own name for "nothing here is outstanding".
REVIEW_SUPPORTED = "supported"

#: Something is outstanding: the status is ``needs_confirmation`` / ``inferred``
#: / ``missing`` / ``rejected``, or the entry carries no readable evidence, or its
#: stored evidence could not be read at all. The catch-all, on purpose — an item
#: this module cannot positively place lands here rather than in
#: :data:`REVIEW_SUPPORTED`.
REVIEW_NEEDS_REVIEW = "needs_review"

#: ``evidence_classify`` reports ``conflicting_evidence`` for this item: two or
#: more evidence entries assert incompatible non-null values. A person must
#: decide. Delegated entirely — the rule lives in ``evidence_classify``, and this
#: module does not re-implement it.
REVIEW_CONFLICT = "conflict"

#: Captured content with no confident schema home that nobody has reviewed yet —
#: a note in ``notes.NOTE_UNREVIEWED``. Deliberately its own state: an unmapped
#: note is not a weakly-supported field, it is content that is not a field at all.
REVIEW_UNMAPPED = "unmapped"

#: A conflict a PERSON decided. Reached only through
#: :mod:`isaac_api.conflict_resolution` — an explicit, confirmed, recorded decision
#: naming which competing answer is right — and only while that decision still
#: covers the conflict a reader is looking at.
#:
#: NOT "the conflict went away", and not a claim about the field's VALUE. The
#: competing citations are all still stored (nothing in this application removes an
#: evidence entry) and the field's value is whatever it was; what changed is that
#: somebody said which answer they stand behind, so nobody has to look again.
#:
#: A STALE decision — one made over a different competing set, because new competing
#: evidence arrived afterwards — is NOT this state. It reads
#: :data:`REVIEW_CONFLICT`, because a person does have to look again. See
#: :func:`review_state` for why staleness is a boolean on the resolution rather than
#: a fifth review state.
REVIEW_RESOLVED = "resolved"

#: The closed review-state vocabulary. Declaration order; see
#: :func:`review_state` for the precedence actually applied.
REVIEW_STATES: tuple[str, ...] = (
    REVIEW_SUPPORTED,
    REVIEW_NEEDS_REVIEW,
    REVIEW_CONFLICT,
    REVIEW_UNMAPPED,
    REVIEW_RESOLVED,
)

#: Draft statuses that mean the value is established as fact by its author.
#: ``inferred`` is NOT here: it is rule-backed rather than confirmed, and this
#: dimension asks whether a person needs to look.
_STATUS_ESTABLISHED = frozenset({"verified"})

#: The one classification :func:`review_state` consumes. Every other class
#: ``evidence_classify`` produces is deliberately ignored here, because this is a
#: different axis and folding six classes into four would make one a lossy rename
#: of the other.
_CONFLICT_CLASSIFICATION = "conflicting_evidence"


# =============================================================================
# Pure derivations.
# =============================================================================


def origins_from_evidence(evidence: object) -> list[str]:
    """The SET of origins one item's evidence list implies, sorted, deduplicated.

    A set rather than a single value because an item legitimately carries several
    citations of different kinds — a spreadsheet row AND the confirmation that
    accepted it — and collapsing that to one would delete a fact.

    Returns ``[]`` when the list implies nothing; callers add
    :data:`ORIGIN_UNKNOWN` themselves, so this function stays composable with the
    other origin sources (inheritance) that a caller may union in.

    Non-list payloads and non-dict entries contribute nothing rather than raising:
    ``serialize`` has already isolated unreadable stored evidence and marked it,
    and an unreadable entry is a reason to say nothing, not a reason to invent an
    origin for it.
    """
    if not isinstance(evidence, list):
        return []
    found: set[str] = set()
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        source_type = entry.get("source_type")
        if isinstance(source_type, str) and source_type in SOURCE_TYPE_ORIGIN:
            found.add(SOURCE_TYPE_ORIGIN[source_type])
        else:
            # A stored evidence entry whose channel this build cannot name — an
            # unrecognised `source_type`, or none at all. The citation exists; only
            # its channel is unknown, which is exactly ORIGIN_EVIDENCE and exactly
            # not ORIGIN_UNKNOWN.
            found.add(ORIGIN_EVIDENCE)
    return sorted(found)


def note_origins(source: object) -> list[str]:
    """The origin set a note's ``source`` implies — one member, or none.

    An unrecognised source yields ``[]`` (the caller renders
    :data:`ORIGIN_UNKNOWN`) rather than a guess. ``notes.Note`` refuses to
    construct with a source outside ``NOTE_SOURCES``, so this arm is reachable
    only for a note object built outside that constructor.
    """
    mapped = NOTE_SOURCE_ORIGIN.get(source) if isinstance(source, str) else None
    return [mapped] if mapped is not None else []


def primary_origin(origins: object) -> str:
    """The single headline origin, chosen by :data:`ORIGIN_PRECEDENCE`.

    NEVER by array position. An origin outside the closed vocabulary is ignored
    rather than returned, and an empty (or entirely unrecognised) set yields
    :data:`ORIGIN_UNKNOWN` — which is a real answer, not a fallback.
    """
    present = set(origins) if isinstance(origins, (list, tuple, set, frozenset)) else set()
    for origin in ORIGIN_PRECEDENCE:
        if origin in present:
            return origin
    return ORIGIN_UNKNOWN


def review_state(
    *,
    status: object = None,
    evidence_count: int = 0,
    classification: object = None,
    note_state: object = None,
    unavailable: bool = False,
    resolution_state: object = None,
) -> str:
    """Which of the five review states this item is in.

    **THIS FUNCTION TAKES NO ORIGIN, AND THAT IS THE POINT.** Where a value came
    from must never decide whether anything establishes it, so there is no
    parameter through which it could. ``test_provenance.py`` asserts the signature
    itself, so a later edit cannot quietly add one.

    Precedence, highest first — each arm is the answer a person most needs:

    1a. :data:`REVIEW_RESOLVED` — ``evidence_classify`` found incompatible
       assertions AND a person recorded a decision that still covers exactly those
       assertions (``conflict_resolution.RESOLUTION_CURRENT``).
    1b. :data:`REVIEW_CONFLICT` — incompatible assertions with no such decision.
       Nothing below matters until a person resolves them.

    **``resolution_state`` IS READ ONLY UNDER THE CONFLICT ARM, DELIBERATELY.** A
    decision recorded against an address that is not conflicting resolves nothing —
    there was no disagreement to decide — and reporting ``resolved`` there would
    announce a resolution of something that never happened. The one arm is also why a
    stale decision needs no state of its own: it falls through to
    :data:`REVIEW_CONFLICT`, which is exactly the answer a reader needs, and a fifth
    member that every surface had to treat identically to ``conflict`` would be an
    invitation for one surface to treat it differently and quietly stop showing a
    live disagreement. The staleness itself is not lost: it travels as
    ``conflict_resolution.RESOLUTION_STALE`` on the entry and in the resolution view.
    2. :data:`REVIEW_UNMAPPED` — an unreviewed note. Not a field, so none of the
       field-shaped answers below can be true of it.
    3. :data:`REVIEW_SUPPORTED` — status ``verified`` AND at least one readable
       evidence entry. Both halves are required: a ``verified`` status with no
       citation is exactly the unsupported claim the no-guessing rule exists to
       surface.
    4. :data:`REVIEW_NEEDS_REVIEW` — everything else, including every status this
       module does not recognise and ``serialize.UNAVAILABLE_STATUS``. The
       catch-all is deliberately the CONSERVATIVE state: an item this module
       cannot positively place is one a person should look at, never one it
       declares fine.
    """
    if classification == _CONFLICT_CLASSIFICATION:
        if resolution_state == cr.RESOLUTION_CURRENT:
            return REVIEW_RESOLVED
        return REVIEW_CONFLICT
    if note_state == notes_module.NOTE_UNREVIEWED:
        return REVIEW_UNMAPPED
    # A PARTIALLY UNREADABLE PAYLOAD IS NEVER SUPPORT.
    #
    # `serialize._trail_entry` passes a draft field's stored `status` through
    # VERBATIM, and sets `unavailable` when only part of the payload could be
    # read. Its own docstring is explicit that the verbatim pass-through "is
    # defensible only BECAUSE `unavailable`/`unavailable_reason` travel with it.
    # Nothing here may present that status as fully justified support."
    #
    # This function used not to read `unavailable` at all, and `ENTRY_KEYS` had
    # no slot to carry it, so the wire shape could not express it either. A field
    # with `status: verified` and one readable citation beside one unreadable one
    # returned `supported` — and `EvidenceTrailPanel` painted a green Supported
    # chip directly beneath the row it had ALREADY marked unavailable. Of the
    # three surfaces that read this data, provenance was the only one that lost
    # the disclosure; `evidence_classify` keeps it in its explanation.
    #
    # Demoted rather than merely flagged, because the conservative arm is what
    # this precedence is for: an item this module cannot positively place is one
    # a person should look at.
    if unavailable:
        return REVIEW_NEEDS_REVIEW
    if status in _STATUS_ESTABLISHED and evidence_count >= 1:
        return REVIEW_SUPPORTED
    return REVIEW_NEEDS_REVIEW


# =============================================================================
# Composition — one entry per address, from data the caller already holds.
# =============================================================================

#: The keys every entry carries. Frozen so a response shape change is a visible
#: edit here rather than an accident at a call site.
ENTRY_KEYS: frozenset[str] = frozenset(
    {
        "address",
        "origins",
        "primary_origin",
        "review_state",
        "evidence_count",
        "inherited",
        "note_refs",
        # Carried so a PARTIALLY unreadable payload cannot present as plain
        # support. See `_entry` and `review_state` for why this is not optional.
        "unavailable",
        # WHICH RECORDED DECISION, IF ANY, COVERS THIS ADDRESS — one of
        # `conflict_resolution.RESOLUTION_STATES`. On the wire and not merely
        # consumed, for `unavailable`'s reason: `review_state` collapses `stale` and
        # `absent` into the same `conflict`, so a client that cannot see this key
        # cannot tell "nobody has looked" from "somebody decided and then the
        # evidence moved on" — and only the second one has a superseded decision to
        # show.
        "resolution_state",
    }
)

#: The draft keys `serialize.evidence_trail_from_draft` actually walks, and
#: therefore the only ones this module can describe. Everything else in a draft
#: is a block it must OWN UP TO not describing, rather than pass over in silence.
#:
#: Kept beside the reader it mirrors: `evidence_trail_from_draft` iterates
#: `draft["fields"]`, then `_bundle_list(draft, "implicit", …)`, then
#: `_bundle_list(draft, "assets", …)`, and nothing else. A test pins this against
#: that function's source so the two cannot drift apart silently.
_DESCRIBED_DRAFT_KEYS: frozenset[str] = frozenset({"fields", "implicit", "assets"})


def _entry(
    address: str,
    *,
    evidence: object,
    status: object,
    classification: object,
    inherited: bool,
    note_refs: list[str],
    extra_origins: tuple[str, ...] = (),
    unavailable: bool = False,
    resolution_state: str = cr.RESOLUTION_ABSENT,
) -> dict:
    """One entry, both dimensions, from one item's already-read stored data.

    ``resolution_state`` arrives ALREADY DERIVED, from
    ``conflict_resolution.resolution_states``. This module does not look a resolution
    up, does not know which scope's decisions apply to which subject, and does not
    compare a staleness digest — the same delegation that keeps the conflict RULE in
    ``evidence_classify`` keeps the resolution rule in its own module, so there is one
    place each can be wrong.
    """
    origins = sorted(set(origins_from_evidence(evidence)) | set(extra_origins))
    if not origins:
        origins = [ORIGIN_UNKNOWN]
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    return {
        "address": address,
        "origins": origins,
        "primary_origin": primary_origin(origins),
        "review_state": review_state(
            status=status,
            evidence_count=evidence_count,
            classification=classification,
            unavailable=unavailable,
            resolution_state=resolution_state,
        ),
        "evidence_count": evidence_count,
        "inherited": inherited,
        "note_refs": note_refs,
        # Carried on the wire, not just consumed: a client that renders its own
        # chip must be able to reach the same verdict, and the frontend mirror
        # does exactly that.
        "unavailable": bool(unavailable),
        "resolution_state": resolution_state,
    }


def _note_refs_by_path(note_list) -> dict[str, list[str]]:
    """``{field path: [note id, ...]}`` for notes a PERSON mapped to that path.

    ``candidate_field_path`` is deliberately excluded. It is what something
    deterministic PROPOSED, and ``notes.py`` keeps the two apart precisely so a
    suggestion is never indistinguishable from a decision; linking a field to a
    note nobody has accepted would undo that here.
    """
    refs: dict[str, list[str]] = {}
    for note in note_list:
        path = getattr(note, "mapped_field_path", None)
        if isinstance(path, str) and path:
            refs.setdefault(path, []).append(note.id)
    return refs


def _note_entry(note) -> dict:
    """One unreviewed note as a provenance entry.

    ``evidence_count`` is 0 by construction, not by omission: ``notes.Note``
    carries ``is_evidence: false`` as a read-only constant, so a note has no
    evidence to count and never will.
    """
    origins = note_origins(getattr(note, "source", None)) or [ORIGIN_UNKNOWN]
    return {
        "address": f"note:{note.id}",
        "origins": origins,
        "primary_origin": primary_origin(origins),
        "review_state": review_state(note_state=note.state),
        "evidence_count": 0,
        "inherited": False,
        "note_refs": [note.id],
        # A note is read whole or not at all — there is no partial-payload state
        # for one. Written explicitly rather than omitted so every entry on the
        # wire carries the same keys, which is what `ENTRY_KEYS` is for.
        "unavailable": False,
        # A note carries no evidence (`is_evidence: false`, a read-only constant), so
        # it can never be in conflict and there is nothing about it to resolve.
        # `absent` rather than a fifth "not applicable" member, for the same reason:
        # every entry carries the same keys.
        "resolution_state": cr.RESOLUTION_ABSENT,
    }


def _trail_entries(
    draft: dict,
    *,
    note_refs: dict[str, list[str]],
    inherited: bool = False,
    extra_origins: tuple[str, ...] = (),
    resolution_states: dict[str, str] | None = None,
) -> list[dict]:
    """Entries for one draft's own evidence trail, in the draft's own order.

    Both reads are delegated: the trail comes from
    ``serialize.evidence_trail_from_draft`` (which owns per-item isolation of
    unreadable stored evidence) and the conflict signal from
    ``evidence_classify.classify_fields`` (which owns the conflict rule). Neither
    is re-implemented here.
    """
    classes = {
        result["field"]: result["classification"]
        for result in evidence_classify.classify_fields(draft)
    }
    entries: list[dict] = []
    for item in serialize.evidence_trail_from_draft(draft):
        address = str(item.get("path"))
        entries.append(
            _entry(
                address,
                evidence=item.get("evidence") or [],
                status=item.get("status"),
                classification=classes.get(item.get("path")),
                inherited=inherited,
                note_refs=list(note_refs.get(address, ())),
                extra_origins=extra_origins,
                # `serialize._trail_entry` sets this when only PART of the stored
                # payload could be read, and its docstring makes the verbatim
                # `status` pass-through conditional on it travelling alongside.
                unavailable=bool(item.get("unavailable")),
                resolution_state=(resolution_states or {}).get(
                    address, cr.RESOLUTION_ABSENT
                ),
            )
        )
    return entries


def describe_experiment(draft: object, note_list=(), resolution_states=None) -> dict:
    """Provenance for an experiment's OWN draft, plus its unreviewed notes.

    ``inherited`` is ``False`` on every entry: an experiment inherits from
    nothing. Only UNREVIEWED notes become entries — the reason is on the
    ``notes_summary`` key of the result, and the count of what was left out is
    beside it, so the list never reads as the whole picture.
    """
    return _describe(
        draft if isinstance(draft, dict) else {},
        {},
        note_list,
        resolution_states=resolution_states,
    )


def describe_run(
    run_draft: object, resolutions: dict, note_list=(), resolution_states=None
) -> dict:
    """Provenance for one RUN: its own draft fields plus what it inherits.

    ``resolutions`` is ``workspace.resolve_inherited(experiment_draft, run)``
    passed through unchanged — this module does not resolve inheritance itself and
    does not import the resolver's traversal.

    Only ``field:`` addresses are described. A ``block:`` address (``tags``,
    ``attribution``, ``series``, ``qc`` …) carries no ``{value, status,
    evidence}`` envelope at all, so neither dimension can be derived for it
    without inventing one: the honest answer is to leave it out and SAY SO, which
    the result's ``blocks_not_described`` list does. Reporting it as
    ``needs_review`` would be a finding about content nobody has made a claim
    about.
    """
    return _describe(
        run_draft if isinstance(run_draft, dict) else {},
        resolutions or {},
        note_list,
        resolution_states=resolution_states,
    )


def _describe(draft: dict, resolutions: dict, note_list, *, resolution_states=None) -> dict:
    """The one composer both public entry points use.

    Ordering, and why it is fixed: the item's OWN draft first (what it stores),
    then what it inherits, then unreviewed notes. An address already described by
    the draft is not described a second time by a resolution — one address, one
    entry, and the item's own stored content is the one that wins, because that is
    what it holds. (The overlap needs malformed stored data to arise at all:
    ``PATCH .../runs/{id}`` refuses a non-run-level path, and
    ``resolve_inherited`` only ever keys on experiment-level addresses and stored
    override addresses.)
    """
    note_list = list(note_list or ())
    refs = _note_refs_by_path(note_list)

    states: dict[str, str] = dict(resolution_states or {})
    entries = _trail_entries(draft, note_refs=refs, resolution_states=states)
    seen = {entry["address"] for entry in entries}

    # THE SUBJECT'S OWN UNDESCRIBED BLOCKS, SEEDED FIRST.
    #
    # This list used to be populated ONLY from `resolutions`, and
    # `describe_experiment` passes `resolutions = {}` — so on the RECORD path,
    # which is the default call every client makes first, it was unconditionally
    # empty while `attribution`, `qc`, `series`, `descriptors_outputs`, `links`,
    # `meta` and `block_evidence` were every bit as undescribed as they are for a
    # run. `serialize.evidence_trail_from_draft` reads only `fields`, `implicit`
    # and `assets`.
    #
    # The route's own response description promises this field carries "the
    # record-level blocks that carry no value envelope to describe". Answering
    # that with `[]` every time is worse than not offering the field at all: a
    # reader whose `attribution` block is unevidenced was told nothing had been
    # omitted, and asking for the same record's RUN would name
    # `block:attribution` — the record-level answer being the less honest of the
    # two, in the one field whose entire purpose is to prevent that.
    #
    # Seeding from the subject draft closes the run side too: a run's OWN
    # `series`/`qc`/`descriptors_outputs` blocks were undescribed and unlisted as
    # well, because `resolutions` only ever carries EXPERIMENT-level addresses.
    described: list[str] = []
    if isinstance(draft, dict):
        described = [
            ws.block_address(key) for key in sorted(draft) if key not in _DESCRIBED_DRAFT_KEYS
        ]
    blocks_not_described: list[str] = list(described)
    field_payloads: dict[str, object] = {}
    inherited_names: set[str] = set()
    for address in sorted(resolutions):
        resolution = resolutions[address]
        try:
            kind, name = ws.parse_address(address)
        except ValueError:
            # Unclassifiable garbage in a persisted document. `resolve_inherited`
            # already skips these, so this is defence in depth rather than a live
            # arm; either way, nothing is invented for it.
            continue
        if kind != ws.ADDRESS_FIELD:
            # Deduped against the subject's own blocks seeded above: an
            # experiment-level block address can arrive from both sources, and
            # naming it twice would misreport how much is undescribed.
            if address not in blocks_not_described:
                blocks_not_described.append(address)
            continue
        if name in seen:
            continue
        field_payloads[name] = resolution.payload
        if resolution.provenance != ws.PROVENANCE_OVERRIDDEN:
            inherited_names.add(name)

    if field_payloads:
        # One synthetic draft, so the resolved envelopes are read by exactly the
        # same two delegates the draft's own fields are — same unreadable-entry
        # handling, same conflict rule, no second implementation.
        synthetic = {"fields": field_payloads}
        classes = {
            result["field"]: result["classification"]
            for result in evidence_classify.classify_fields(synthetic)
        }
        for item in serialize.evidence_trail_from_draft(synthetic):
            name = str(item.get("path"))
            is_inherited = name in inherited_names
            entries.append(
                _entry(
                    name,
                    evidence=item.get("evidence") or [],
                    status=item.get("status"),
                    classification=classes.get(item.get("path")),
                    inherited=is_inherited,
                    note_refs=list(refs.get(name, ())),
                    extra_origins=(ORIGIN_INHERITED,) if is_inherited else (),
                    # An INHERITED envelope can be partially unreadable too, and
                    # the resolved payload goes through the very same reader.
                    unavailable=bool(item.get("unavailable")),
                    # AN INHERITED ADDRESS IS RESOLVED AT THE RECORD, NOT AT THE RUN,
                    # so the caller merges the record's states under the run's own —
                    # see `routes.get_provenance`. Read from the same map for that
                    # reason: a second lookup here would be a second scope rule.
                    resolution_state=states.get(name, cr.RESOLUTION_ABSENT),
                )
            )

    unreviewed = [n for n in note_list if n.state == notes_module.NOTE_UNREVIEWED]
    entries.extend(_note_entry(note) for note in unreviewed)

    return {
        "entries": entries,
        # WHAT IS NOT LISTED, COUNTED RATHER THAN OMITTED. A reviewed note —
        # mapped, kept or dismissed — is not an entry, because none of the four
        # review states is true of it: it is not unmapped any more, and calling it
        # supported would assert that something backs a value it does not carry.
        # Saying how many exist is the alternative to letting the list read as the
        # whole picture.
        "notes_summary": {
            "total": len(note_list),
            "listed_as_unmapped": len(unreviewed),
        },
        "blocks_not_described": blocks_not_described,
    }
