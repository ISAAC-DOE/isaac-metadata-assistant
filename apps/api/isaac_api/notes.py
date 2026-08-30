"""Unmapped Notes — captured content that has no confident schema home.

THE TWO INVARIANTS THIS MODULE EXISTS TO ENFORCE
================================================

**(1) Nothing captured is ever silently discarded.** A scientist writes things
down that the extractor cannot place: a sentence about why a scan was re-run, a
column heading nothing recognises, a remark in a transcript. Every pipeline in
this repository drops such content on the floor — quietly, with no surface saying
so — and **it still does: no pipeline was rewired when this module was added.**
A :class:`Note` is the destination that now EXISTS and is where such content WILL
land once a producer is wired to it; today the only producer is a person typing
into the Unmapped Notes panel, whose captures all carry
``source="typed_note"``. The intended first automatic producer is the
``unrecognised_labels`` list that ``providers/extraction.py`` already computes
and then discards — wiring that seam is a later slice, and until it lands nothing
in this application creates a ``csv_column``, ``transcript``,
``file_listing_line`` or ``extraction_residue`` note, sets a ``run_id``, or
supplies a ``candidate_field_path``. The vocabulary exists ahead of its
producers deliberately; **reading it as evidence that the producers exist is the
misreading this paragraph is worded to prevent.**

What invariant (1) governs is therefore what happens to content that DOES reach
here. Dismissal is a STATE (:data:`NOTE_DISMISSED`), reached by an explicit act,
recorded in an append-only :attr:`Note.history`; it is not a delete, and this
module offers no delete. Editing does not overwrite the capture either:
:attr:`Note.text` is the verbatim original forever, an edit writes
:attr:`Note.revised_text` beside it, and the superseded wording is kept on the
history entry.

**(2) A note can never present as a confirmed field value.** The shape is the
enforcement, in the same way ``providers/extraction.py``'s ``FieldCandidate``
enforces the same thing for a proposed value. :class:`Note` is a frozen, slotted
dataclass whose ``status`` / ``verified`` / ``is_evidence`` / ``is_field_value``
are **read-only properties returning constants** — there is no field to set, so

* ``Note(..., verified=True)`` raises ``TypeError`` — no such field,
* ``dataclasses.replace(n, verified=True)`` raises ``TypeError``,
* ``n.verified = True`` is refused by the frozen ``__setattr__``,
* ``object.__setattr__(n, "verified", True)`` — the escape hatch that DOES work on
  an ordinary frozen dataclass FIELD — raises ``AttributeError``, because
  ``verified`` is a property with no setter and was never a field,
* ``object.__setattr__(n, "some_new_flag", True)`` raises ``AttributeError`` too,
  because ``slots=True`` leaves no instance ``__dict__`` to smuggle it into.

``status`` returns :data:`NOTE_STATUS`, which is deliberately **not** a member of
``isaac_records.models.STATUSES``. A note's status is not a draft-envelope status
and must never be mistaken for one; a reader who keys on the string sees a token
that appears nowhere in the draft vocabulary rather than one that quietly reads as
``verified``.

Two precisions, because an overstated guarantee is worse than a modest one.
**(a)** ``object.__setattr__`` can still overwrite an ordinary *field* — that is
true of every frozen dataclass, and this module uses it itself in
``__post_init__``. What it cannot reach is the four constants, because they are
not fields. **(b)** ``frozen=True`` with ``slots=True`` makes a plain
``n.anything = x`` raise ``TypeError`` rather than ``FrozenInstanceError`` on
CPython; the assignment is refused either way and the test accepts both rather
than pinning an implementation detail.

WHAT A NOTE IS NOT ALLOWED TO GUESS
===================================

:attr:`Note.candidate_field_path` is **absent unless something deterministic
produced it**. ``None`` means "nothing proposed a home", and it is the default.
The empty string is refused outright, because ``""`` is a value that renders as a
path-shaped blank and invites a reader to treat "no candidate" and "a candidate we
could not name" as the same thing. A candidate with no :attr:`candidate_rule` is
refused for the reason ``FieldCandidate`` refuses one: an unexplained proposal is
a guess wearing a field name.

This module performs **no schema lookup**. It does not know whether a path is a
real official field, and it deliberately does not learn: that classification lives
in ``routes.py`` (``NOTE_MAPPABLE_FIELD_PATHS``, derived from the extractor's field
map exactly as ``RUN_WRITABLE_FIELD_PATHS`` is), so there is one derivation of
"real official path" rather than a second copy here free to drift.

WHY A NOTE CARRIES NO ``source_type``
=====================================

For the same reason a ``FieldCandidate`` carries none. ``isaac_records.models``'s
``SOURCE_TYPES`` is closed at ``document``, ``spreadsheet``, ``screenshot``,
``web_form``, ``file_listing``, ``user_confirmation``, ``derivation`` — that is the
EVIDENCE type system, and a note is not evidence. Borrowing a member would widen
what those words mean, and adding an eighth is a truth-core change under
``CLAUDE.md`` §13 that this slice does not make. :data:`NOTE_SOURCES` is this
feature's own closed vocabulary and stays outside the evidence types entirely.

MAPPING RECORDS A TARGET; IT DOES NOT WRITE A VALUE
===================================================

:func:`map_note` stores the field path a scientist says this note belongs to. It
writes no draft field, mints no evidence and confirms nothing. That is not
timidity: turning note text into a field value requires deciding what the value IS,
and deriving one from prose is precisely the guess this project refuses. A mapped
note says "this belongs there"; a person still says what the value is.

**WHICH ROUTE THAT PERSON USES — AND WHETHER ONE EXISTS — WAS STATED WRONG HERE, IN
BOTH HALVES, AND IS CORRECTED RATHER THAN DELETED.** This paragraph read: *"The path
that turns a value into a confirmed field already exists and is unchanged — ``POST
/experiments/{id}/answers`` / ``POST /experiments/{id}/edit`` with
``confirmed_by_user: true`` and a matching ``If-Match``, recorded as
``user_confirmation`` evidence."* Measured over HTTP against a record created through
``POST /api/experiments``, at every one of the 25 mappable paths, those two routes
accept ~~**none of them** — both answer ``422 unrecognized_field`` for all 25, because
they are keyed to a record's open blocking questions and to fields the draft already
holds, not to official field paths~~ — **CORRECTED 2026-08-30: they now accept 13 of
the 25, and this paragraph is struck in place rather than rewritten because it is the
sentence the surfaces copied.** ``POST /experiments/{id}/answers`` and ``POST
/experiments/{id}/edit`` accept every EXPERIMENT-level official path — the sample, the
facility, ``system.technique`` — and the two record-level block addresses
``block:attribution`` and ``block:tags``, recording each as a ``user_confirmation`` on
the record that every run then inherits. They were keyed only to blocking questions and
to fields the draft already held when this was written; they no longer are.

~~The two routes that DO accept these paths are a RUN's~~ — **THREE routes accept them
now.** ``PATCH /api/experiments/{id}/runs/{run_id}`` for the 5 run-level paths; ``POST
/api/experiments/{id}/answers`` (corrected at ``.../edit``) for the 13 record-level
ones, which is the route a record with no runs at all can use; and ``POST
/api/experiments/{id}/runs/{run_id}/overrides`` to record ONE run's divergence from a
record-level value. The
remaining **7** — the six ``system.configuration.*`` paths and
``timestamps.created_utc`` — are accepted by no write route in this build at all, and
that is unchanged: they are ``field_level``-unclassified, and the record-level write
surface is derived by filtering on ``LEVEL_EXPERIMENT``, so they are excluded without a
special case rather than by a list somebody has to remember to keep.

The per-path answer is derived and served rather than described in prose, at
``routes.NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT`` and on the wire as
``value_writable_field_paths``, so a surface can be true about the path in front of
the reader instead of true on average.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

__all__ = [
    "NOTE_STATUS",
    "NOTE_STATES",
    "NOTE_UNREVIEWED",
    "NOTE_MAPPED",
    "NOTE_KEPT",
    "NOTE_DISMISSED",
    "NOTE_SOURCES",
    "NOTE_ACTIONS",
    "ACTION_CAPTURE",
    "ACTION_MAP",
    "ACTION_EDIT",
    "ACTION_KEEP",
    "ACTION_DISMISS",
    "IMMUTABLE_NOTE_FIELDS",
    "ImmutableCapture",
    "UnsupportedNote",
    "NoteTransition",
    "Note",
    "new_note",
    "revise_note",
    "map_note",
    "edit_note",
    "keep_note",
    "dismiss_note",
]


#: The ONLY status a note can have, and it is not a draft status. Not a default —
#: a constant returned by a read-only property, so there is no second value to set.
NOTE_STATUS = "unmapped_note"

#: A note nobody has acted on yet. The state every capture starts in.
NOTE_UNREVIEWED = "unreviewed"
#: A scientist named the official field path this note belongs to. NOT a value.
NOTE_MAPPED = "mapped"
#: A FIRST-CLASS OUTCOME, not a failure. Some of what a scientist writes is prose
#: about the experiment and has no field, and saying so is a decision rather than
#: an unfinished triage.
NOTE_KEPT = "kept"
#: Reviewed and set aside. A STATE, reached by an explicit act and recorded in the
#: history — never a deletion. A dismissed note is still listed, still readable,
#: still exportable to a later revision model.
NOTE_DISMISSED = "dismissed"

NOTE_STATES: frozenset[str] = frozenset(
    {NOTE_UNREVIEWED, NOTE_MAPPED, NOTE_KEPT, NOTE_DISMISSED}
)

ACTION_CAPTURE = "capture"
ACTION_MAP = "map"
ACTION_EDIT = "edit"
ACTION_KEEP = "keep"
ACTION_DISMISS = "dismiss"

#: The acts that appear in a note's history. ``capture`` is not a scientist
#: action — it is the entry every note opens with, so the history is complete from
#: the first moment rather than starting at the first review.
NOTE_ACTIONS: frozenset[str] = frozenset(
    {ACTION_CAPTURE, ACTION_MAP, ACTION_EDIT, ACTION_KEEP, ACTION_DISMISS}
)

#: What produced the captured content, in THIS feature's own vocabulary.
#:
#: Deliberately not an ISAAC ``source_type`` (see the module docstring), and
#: deliberately closed: an open string would let a producer write anything and
#: would make the field unusable for grouping. There is no default and no
#: ``unknown`` member — a producer that cannot say what produced its own output is
#: not a producer this feature can describe honestly, and inventing a label for it
#: would be the guess the whole feature exists to refuse.
NOTE_SOURCES: frozenset[str] = frozenset(
    {
        #: A person typed it into this application.
        "typed_note",
        #: A line of a spoken or dictated transcript.
        "transcript",
        #: A CSV column or cell nothing in the ingest recognised.
        "csv_column",
        #: A line of a raw-file listing that matched no asset rule.
        "file_listing_line",
        #: A label the deterministic extractor saw and refused to guess at — the
        #: ``unrecognised_labels`` the capture/extraction seam already reports.
        "extraction_residue",
    }
)


class UnsupportedNote(ValueError):
    """A note that cannot be constructed without inventing something."""


class ImmutableCapture(ValueError):
    """An attempt to revise a field of a note that records what was captured."""


#: The keys :func:`revise_note` refuses to change, and therefore the keys no
#: review action can touch.
#:
#: ``text`` is the load-bearing one: it is the verbatim capture, and the whole
#: feature is worthless if a later act can rewrite it. ``source`` is here because
#: "what produced this" is a fact about the capture, not an opinion revisable
#: afterwards; ``id`` / ``experiment_id`` / ``captured_utc`` because they are
#: identity.
#:
#: This is a guard on the ONE function every mutator goes through, not a claim
#: that the attribute is unreachable — ``object.__setattr__`` reaches any frozen
#: dataclass field, here as everywhere. What it buys is that a NEW review action
#: added later cannot rewrite the capture by accident, only by deliberately
#: bypassing the only revision helper this module exposes.
IMMUTABLE_NOTE_FIELDS: frozenset[str] = frozenset(
    {"id", "experiment_id", "captured_utc", "source", "text"}
)


def _clean_optional(value: object, label: str) -> str | None:
    """``None`` or a non-blank string. A blank is REFUSED, never coerced to ``None``.

    The distinction is the point of the whole feature. ``None`` means "nobody
    supplied this"; ``""`` means a caller supplied something empty and expects it
    to have been stored. Silently folding the second into the first is a small
    silent discard, which is exactly what this module is for.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise UnsupportedNote(f"{label} must be a string or absent, not {type(value).__name__}")
    if not value.strip():
        raise UnsupportedNote(
            f"{label} was supplied as blank. Absent is a meaning here — omit it "
            "rather than sending an empty string, which would be stored as though "
            "somebody had written something."
        )
    return value


@dataclass(frozen=True, slots=True)
class NoteTransition:
    """ONE act in a note's life, appended and never rewritten.

    The history exists so a later revision model has something to build on: it
    can say when a note was dismissed, what it was dismissed from, and — for an
    edit — exactly what wording was superseded. Nothing in this module removes an
    entry, and :func:`revise_note` refuses a history that is not an extension of
    the one it replaces.
    """

    action: str
    at: str
    #: The state before this act. ``None`` only for :data:`ACTION_CAPTURE`.
    from_state: str | None
    to_state: str
    #: For :data:`ACTION_MAP`: the path the scientist named. Never inferred.
    field_path: str | None = None
    #: For :data:`ACTION_EDIT`: the exact wording this act replaced, so no version
    #: of the text is ever lost.
    superseded_text: str | None = None
    #: For :data:`ACTION_DISMISS`: the scientist's reason, when they gave one.
    #: Absent when they did not — no reason is ever composed on their behalf.
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.action not in NOTE_ACTIONS:
            raise UnsupportedNote(f"unknown note action {self.action!r}")
        if self.to_state not in NOTE_STATES:
            raise UnsupportedNote(f"unknown note state {self.to_state!r}")
        if self.from_state is not None and self.from_state not in NOTE_STATES:
            raise UnsupportedNote(f"unknown prior note state {self.from_state!r}")
        if not self.at:
            raise UnsupportedNote("a transition must record when it happened")

    def to_state_dict(self) -> dict:
        """The wire/persistence shape.

        NAMED ``to_state_dict`` / ``from_state_dict`` AND NOT THE USUAL
        ``to_state`` / ``from_state``, AND THAT IS FORCED RATHER THAN CHOSEN. This
        class has FIELDS called ``from_state`` and ``to_state`` — the states an act
        moved between, which is the natural wording for an audit row. A
        ``slots=True`` dataclass raises ``ValueError: 'from_state' in __slots__
        conflicts with class variable`` at class-creation time if a method shares a
        field's name, so the collision is not a style question: one of the two
        names has to move, and the field is the one a reader of the stored history
        sees.
        """
        return {
            "action": self.action,
            "at": self.at,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "field_path": self.field_path,
            "superseded_text": self.superseded_text,
            "reason": self.reason,
        }

    @classmethod
    def from_state_dict(cls, state: dict) -> "NoteTransition":
        return cls(
            action=state.get("action"),  # type: ignore[arg-type]
            at=state.get("at"),  # type: ignore[arg-type]
            from_state=state.get("from_state"),
            to_state=state.get("to_state"),  # type: ignore[arg-type]
            field_path=state.get("field_path"),
            superseded_text=state.get("superseded_text"),
            reason=state.get("reason"),
        )


@dataclass(frozen=True, slots=True)
class Note:
    """Captured content with no confident schema home. Never a value, never evidence.

    ``slots=True`` is load-bearing rather than a micro-optimisation: it removes the
    instance ``__dict__``, which is the last route by which an attribute like
    ``verified`` could be attached after construction.
    """

    id: str
    experiment_id: str
    #: THE VERBATIM CAPTURE. Stored exactly as it arrived — not stripped, not
    #: normalised, not truncated, not case-folded. Immutable by
    #: :data:`IMMUTABLE_NOTE_FIELDS`; an edit writes :attr:`revised_text` instead.
    text: str
    #: One of :data:`NOTE_SOURCES`.
    source: str
    captured_utc: str
    #: The run this note belongs to WHEN THAT IS KNOWN, and ``None`` otherwise. A
    #: note captured against the record as a whole genuinely has no run, and
    #: attaching it to the only run that happens to exist would be an invention.
    run_id: str | None = None
    #: The field path something DETERMINISTIC proposed, or ``None``. See the module
    #: docstring: ``None`` is the default and the empty string is refused.
    candidate_field_path: str | None = None
    #: The rule that produced :attr:`candidate_field_path`, stated in full — the
    #: sentence, not an id, so a reader can check the proposal without a lookup
    #: table. Required whenever a candidate exists.
    candidate_rule: str | None = None
    state: str = NOTE_UNREVIEWED
    #: The scientist's corrected wording, when they supplied one. The capture in
    #: :attr:`text` is unchanged; this sits beside it.
    revised_text: str | None = None
    #: The path a scientist named through :func:`map_note`. Distinct from
    #: :attr:`candidate_field_path`, which is what a machine proposed — collapsing
    #: the two would make a suggestion indistinguishable from a decision.
    mapped_field_path: str | None = None
    #: Append-only. Opens with a :data:`ACTION_CAPTURE` entry.
    history: tuple[NoteTransition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise UnsupportedNote("a note must have an id; an unaddressable note cannot be reviewed")
        if not isinstance(self.experiment_id, str) or not self.experiment_id:
            raise UnsupportedNote("a note must name the experiment it belongs to")
        if not isinstance(self.text, str) or not self.text.strip():
            raise UnsupportedNote(
                "a note must carry the content that was captured. An empty note "
                "records nothing and would occupy a review queue with a blank row."
            )
        if self.source not in NOTE_SOURCES:
            raise UnsupportedNote(
                f"unknown note source {self.source!r}; allowed: {sorted(NOTE_SOURCES)}"
            )
        if not self.captured_utc:
            raise UnsupportedNote("a note must record when it was captured")
        if self.state not in NOTE_STATES:
            raise UnsupportedNote(f"unknown note state {self.state!r}")
        object.__setattr__(self, "run_id", _clean_optional(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "candidate_field_path",
            _clean_optional(self.candidate_field_path, "candidate_field_path"),
        )
        object.__setattr__(
            self, "candidate_rule", _clean_optional(self.candidate_rule, "candidate_rule")
        )
        object.__setattr__(
            self, "revised_text", _clean_optional(self.revised_text, "revised_text")
        )
        object.__setattr__(
            self,
            "mapped_field_path",
            _clean_optional(self.mapped_field_path, "mapped_field_path"),
        )
        # A CANDIDATE AND ITS RULE TRAVEL TOGETHER, in both directions. A path with
        # no rule is an unexplained proposal, which is a guess with a field name on
        # it; a rule with no path describes a derivation that produced nothing and
        # would render as a claim about a field this note does not name.
        if self.candidate_field_path is not None and self.candidate_rule is None:
            raise UnsupportedNote(
                f"{self.candidate_field_path}: a candidate field path must state the "
                "rule that produced it. An unexplained proposal is a guess."
            )
        if self.candidate_rule is not None and self.candidate_field_path is None:
            raise UnsupportedNote(
                "a candidate rule was supplied with no candidate field path; the "
                "rule would describe a proposal that does not exist"
            )
        if self.state == NOTE_MAPPED and self.mapped_field_path is None:
            raise UnsupportedNote(
                "a mapped note must name the field path it was mapped to; a mapped "
                "state with no target claims a decision nobody made"
            )
        if not isinstance(self.history, tuple) or any(
            not isinstance(entry, NoteTransition) for entry in self.history
        ):
            raise UnsupportedNote("a note's history must be a tuple of transitions")

    # --- the four constants that make "a value" unconstructible ---------------

    @property
    def status(self) -> str:
        """Always :data:`NOTE_STATUS`, which is not a draft envelope status."""
        return NOTE_STATUS

    @property
    def verified(self) -> bool:
        """Always ``False``. Nothing here was checked against anything."""
        return False

    @property
    def is_evidence(self) -> bool:
        """Always ``False``. Captured prose is not evidence about a record."""
        return False

    @property
    def is_field_value(self) -> bool:
        """Always ``False``. A note names, at most, a field it might belong to."""
        return False

    # --- derived reads --------------------------------------------------------

    @property
    def display_text(self) -> str:
        """What to show: the revision when there is one, else the capture.

        Both are always available. This is a convenience for a renderer, never a
        replacement for :attr:`text`, which every serialisation carries.
        """
        return self.revised_text if self.revised_text is not None else self.text

    @property
    def dismissed(self) -> bool:
        return self.state == NOTE_DISMISSED

    def to_state(self) -> dict:
        """The persistence AND wire shape — and it repeats the four constants.

        A consumer reading JSON does not see the class invariant. Serialising
        ``status`` / ``verified`` / ``is_evidence`` / ``is_field_value`` means the
        guarantee survives the boundary instead of stopping at it, which is the
        rule ``FieldCandidate.to_dict`` already set.
        """
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "source": self.source,
            "text": self.text,
            "revised_text": self.revised_text,
            "captured_utc": self.captured_utc,
            "state": self.state,
            "candidate_field_path": self.candidate_field_path,
            "candidate_rule": self.candidate_rule,
            "mapped_field_path": self.mapped_field_path,
            "history": [entry.to_state_dict() for entry in self.history],
            "status": self.status,
            "verified": self.verified,
            "is_evidence": self.is_evidence,
            "is_field_value": self.is_field_value,
        }

    @classmethod
    def from_state(cls, state: dict) -> "Note":
        """Rehydrate one note. RAISES on a document it cannot represent honestly.

        Deliberately unlike ``Run.from_state``, which never raises and coerces every
        wrong-typed key to a safe default. A run coerced to a default is still the
        same run; a note whose ``text`` or ``source`` cannot be read is a piece of
        captured content this module would have to invent something about, and
        inventing is the one thing it may not do.

        Raising is safe here — and is not a route back to the 500s that policy was
        written for — because the ONLY caller is ``workspace._hydrate_notes``, which
        catches this and PRESERVES the raw entry verbatim rather than dropping it.
        Nothing is lost and nothing is guessed; the entry is reported as unreadable
        and written back out untouched on the next save.
        """
        history = state.get("history")
        return cls(
            id=state.get("id"),  # type: ignore[arg-type]
            experiment_id=state.get("experiment_id"),  # type: ignore[arg-type]
            run_id=state.get("run_id"),
            source=state.get("source"),  # type: ignore[arg-type]
            text=state.get("text"),  # type: ignore[arg-type]
            revised_text=state.get("revised_text"),
            captured_utc=state.get("captured_utc"),  # type: ignore[arg-type]
            state=state.get("state", NOTE_UNREVIEWED),
            candidate_field_path=state.get("candidate_field_path"),
            candidate_rule=state.get("candidate_rule"),
            mapped_field_path=state.get("mapped_field_path"),
            history=tuple(
                NoteTransition.from_state_dict(entry)
                for entry in (history if isinstance(history, list) else [])
                if isinstance(entry, dict)
            ),
        )


def new_note(
    *,
    id: str,
    experiment_id: str,
    text: str,
    source: str,
    captured_utc: str,
    run_id: str | None = None,
    candidate_field_path: str | None = None,
    candidate_rule: str | None = None,
) -> Note:
    """Mint a note, with the opening :data:`ACTION_CAPTURE` entry already in it.

    The id is supplied by the caller rather than minted here so this module stays
    free of the truth core's id package; ``workspace.capture_note`` is the one
    place that mints one, using the same ``new_record_id`` a run's id comes from.
    A NOTE ID IS NOT A RECORD ID — it names no exported artifact and never will.
    """
    return Note(
        id=id,
        experiment_id=experiment_id,
        text=text,
        source=source,
        captured_utc=captured_utc,
        run_id=run_id,
        candidate_field_path=candidate_field_path,
        candidate_rule=candidate_rule,
        state=NOTE_UNREVIEWED,
        history=(
            NoteTransition(
                action=ACTION_CAPTURE,
                at=captured_utc,
                from_state=None,
                to_state=NOTE_UNREVIEWED,
            ),
        ),
    )


def revise_note(note: Note, **changes: Any) -> Note:
    """``dataclasses.replace`` with the capture and the audit trail held closed.

    THE ONE REVISION HELPER. Every action below goes through it, so the two rules
    it enforces cannot be forgotten by an action added later:

    * a field in :data:`IMMUTABLE_NOTE_FIELDS` may not be changed at all;
    * a replacement ``history`` must EXTEND the existing one. A shorter history, or
      one whose earlier entries differ, is refused — an audit trail that can be
      rewritten is not an audit trail, and "no silent discard" has to cover the
      record of the discarding too.
    """
    forbidden = sorted(set(changes) & IMMUTABLE_NOTE_FIELDS)
    if forbidden:
        raise ImmutableCapture(
            f"{forbidden} record what was captured and cannot be revised. An edit "
            "writes `revised_text` beside the original; it never replaces it."
        )
    new_history = changes.get("history")
    if new_history is not None:
        if len(new_history) < len(note.history) or tuple(
            new_history[: len(note.history)]
        ) != tuple(note.history):
            raise ImmutableCapture(
                "a note's history may only be extended. Replacing or shortening it "
                "would erase the record of an act that happened."
            )
    return dataclasses.replace(note, **changes)


def _appended(note: Note, transition: NoteTransition) -> tuple[NoteTransition, ...]:
    return (*note.history, transition)


def map_note(note: Note, *, field_path: str, at: str) -> Note:
    """Record the official field path a SCIENTIST says this note belongs to.

    Writes no value anywhere. See the module docstring: turning prose into a field
    value means deciding what the value is, and this application makes a person do
    that through a separate confirmed write.

    ~~"through the confirmed-edit path that already exists"~~ — CORRECTED, and kept
    struck rather than deleted because the old sentence was the source the surfaces
    copied. **For 7 of the 25 mappable paths NO SUCH PATH EXISTS.** Measured over HTTP
    against every write route this application has, on a created record with one run:
    the six ``system.configuration.*`` paths and ``timestamps.created_utc`` are refused
    by all five — ``422 unrecognized_field`` from the record/run answer and edit routes
    and from ``PATCH .../runs/{run_id}``, ``422 not_overridable`` from ``POST
    .../runs/{run_id}/overrides``. A sentence that is true of 18 paths out of 25 is not
    "true on average" in the one place a scientist reads before choosing a target; it
    is false for the path they chose. Which paths do have a route is served per path as
    ``value_writable_field_paths`` — see
    ``routes.NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT``, which derives it from the
    two sets those routes enforce rather than restating it.

    **MAPPING IS UNAFFECTED IN EVERY CASE, and that is why this is a copy fix and not a
    gate.** A note whose field can take no value is still correctly filed, its content
    still stays on the record in full, and refusing the mapping would throw away a
    scientist's own judgement about where their prose belongs in order to avoid saying
    one honest sentence.

    IDEMPOTENT: re-mapping to the path already recorded returns the same note, so a
    double-click does not add a second audit row or move the experiment's revision.
    """
    target = _clean_optional(field_path, "field_path")
    if target is None:
        raise UnsupportedNote("mapping a note requires the field path to map it to")
    if note.state == NOTE_MAPPED and note.mapped_field_path == target:
        return note
    return revise_note(
        note,
        state=NOTE_MAPPED,
        mapped_field_path=target,
        history=_appended(
            note,
            NoteTransition(
                action=ACTION_MAP,
                at=at,
                from_state=note.state,
                to_state=NOTE_MAPPED,
                field_path=target,
            ),
        ),
    )


def edit_note(note: Note, *, text: str, at: str) -> Note:
    """Record a corrected wording BESIDE the verbatim capture.

    The capture is never touched — :data:`IMMUTABLE_NOTE_FIELDS` would refuse it —
    and the wording this edit supersedes is kept on the history entry, so every
    version of the text remains recoverable rather than only the first and the last.

    The review state is deliberately UNCHANGED. Fixing a typo is not a triage
    decision, and silently marking an edited note as reviewed would clear it out of
    the queue a scientist is working through.

    IDEMPOTENT against the text currently displayed.
    """
    revised = _clean_optional(text, "text")
    if revised is None:
        raise UnsupportedNote("editing a note requires the corrected text")
    if revised == note.display_text:
        return note
    return revise_note(
        note,
        revised_text=revised,
        history=_appended(
            note,
            NoteTransition(
                action=ACTION_EDIT,
                at=at,
                from_state=note.state,
                to_state=note.state,
                superseded_text=note.display_text,
            ),
        ),
    )


def keep_note(note: Note, *, at: str) -> Note:
    """Record that this content is prose about the experiment and belongs to no field.

    A FIRST-CLASS OUTCOME. It is not "unresolved", not "skipped" and not a failure
    of the mapping; some of what a scientist writes has no schema home and saying so
    is a decision.

    IDEMPOTENT.
    """
    if note.state == NOTE_KEPT:
        return note
    return revise_note(
        note,
        state=NOTE_KEPT,
        history=_appended(
            note,
            NoteTransition(
                action=ACTION_KEEP, at=at, from_state=note.state, to_state=NOTE_KEPT
            ),
        ),
    )


def dismiss_note(note: Note, *, at: str, reason: str | None = None) -> Note:
    """Set the note aside. A STATE CHANGE, NOT A DELETE.

    The note stays in the experiment, stays listed, stays readable, and keeps every
    earlier act in its history. ``reason`` is stored when a scientist gives one and
    is ABSENT when they do not — no reason is ever composed on their behalf, because
    a fabricated justification in an audit trail is worse than a missing one.

    IDEMPOTENT against an identical re-dismissal, so re-clicking cannot manufacture
    a second audit row. A dismissal that supplies a NEW reason is a real act and is
    appended.
    """
    stated = _clean_optional(reason, "reason")
    if note.state == NOTE_DISMISSED:
        last = next(
            (
                entry
                for entry in reversed(note.history)
                if entry.action == ACTION_DISMISS
            ),
            None,
        )
        if last is not None and last.reason == stated:
            return note
    return revise_note(
        note,
        state=NOTE_DISMISSED,
        history=_appended(
            note,
            NoteTransition(
                action=ACTION_DISMISS,
                at=at,
                from_state=note.state,
                to_state=NOTE_DISMISSED,
                reason=stated,
            ),
        ),
    )
