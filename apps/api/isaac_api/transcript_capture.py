"""Manual transcript capture — reading a FINALIZED transcript, deterministically.

WHAT THIS MODULE IS, AND WHAT IT IS NOT
=======================================
It is the repository's own deterministic reader for a transcript a scientist
**typed, pasted, or dictated and then explicitly finalized**. It is a closed table
of literal patterns over the five run-level official field paths this build can
write. It has no model, no scoring, no ranking, no learning, and no network.

**It is deliberately NOT the ``capture_extraction`` provider seam.** That seam
stands in for a model, its production implementation is ``unconfigured`` by
decision, and ``providers/config.validate_provider_config_or_raise`` refuses to
boot an application that selects its test double. Routing this feature through it
would mean the scientist workflow only worked when a model provider existed, which
is exactly backwards: reading ``temperature was 300 K`` out of a sentence needs no
model, and pretending it does would make an honest, always-available capability
look like an AI one. The seam is untouched by this module and stays unconsumed.

THE FOUR RULES THIS MODULE EXISTS TO ENFORCE
============================================

**(1) Nothing is read until a human finalizes.** This module is a pure function
and writes nothing anywhere; the route that calls it refuses without an explicit
``finalized: true``. There is no debounce, no timer, and no partial pass.

**(2) A candidate is never a value.** Every proposal is a
:class:`~.providers.extraction.FieldCandidate` — the existing type, with its
existing structural guarantees: ``status`` / ``verified`` / ``is_evidence`` /
``requires_user_confirmation`` are read-only properties returning constants on a
frozen, slotted dataclass, so a candidate that presents as confirmed is not
constructible. No parallel type is defined here.

**(3) An ambiguous run or field reference is never resolved by preference.**
Every ambiguity lands in exactly one of four typed outcomes, and the choice per
case is recorded in :data:`AMBIGUITY_POLICY`:

* :class:`Clarification` — the reading knows what it does not know and can name
  the alternatives, so it asks. Used for every run-reference ambiguity, because a
  run is a *choice a person makes*, and this build already refuses to infer "the
  only run that happens to exist" when capturing a note.
* :class:`ReviewRequired` — two statements propose different values for the same
  field. BOTH candidates are returned; neither is dropped and neither is
  preferred. Picking one would be a guess, and dropping both would lose a thing
  the scientist said twice. **CORRECTED 2026-09-12: until then this outcome was
  unreachable from a SINGLE sentence**, because every rule was matched with
  ``re.search`` — which returns the first match and nothing else. *"The temperature
  was around 425 K, maybe 430 K"* therefore produced one candidate of 425 and an
  empty ``review_required``, and **430 was lost in silence**: no candidate, no
  clarification, no abstention, no grouping. The text survived as a note, so
  nothing was destroyed; what was lost was the reading, and with it the
  scientist's chance to accept either value. ~~Two changes were needed, not one~~
  — **THREE, corrected 2026-09-12 by independent review.** ``finditer`` for a
  sentence that repeats the LABEL, a restatement read for a sentence that repeats
  only the VALUE (which is the form people actually speak), **and a gate on that
  restatement read**, which the first two shipped without. Unbounded, the
  restatement scan read the whole remainder of the segment and proposed a ramp
  rate, a step size, a pressure, a cryostat setpoint, an END instant and a FUTURE
  run's instant as alternative values for the labelled field — each with a
  ``rule`` string asserting the sentence had restated the quantity. **That is
  strictly worse than the omission it replaced: an omission loses a reading, an
  assertion invents one**, and §5 forbids the second in terms. The gate is
  :data:`_HEDGE_BRIDGE`, and the invariant is that a hedging connective from a
  closed list must sit immediately between the two values with nothing else in
  the gap.
  Note what is still refused: ``[425, 430]`` is never constructed. That asserts a
  continuous interval nobody stated, and the official schema's only uncertainty
  representation is ``$.descriptors.outputs[].descriptors[].uncertainty``, which
  ``context.temperature_K`` has no sibling of.
* :class:`Abstention` — the reading recognises the subject and declines to
  propose anything, because a proposal would require a conversion or a schema
  decision nobody made. Nothing is asked, because there is no alternative to
  offer.
* an **unmapped note** — the default, and by far the commonest. Text nothing
  matched is stored verbatim; see (4).

**(4) Scientist-entered text is never silently discarded.** EVERY segment of a
finalized transcript becomes an Unmapped Note, including the segments that DID
produce a candidate. That is the deliberate, slightly redundant choice: ~~a
candidate is not stored anywhere~~ — **CORRECTED 2026-09-10: since the transcript
producer shipped, a candidate's VALUE is stored, as the ``proposed_value`` of a
durable ``IngestionProposal`` minted by ``routes._mint_transcript_proposals`` in the
same write as these notes. The candidate object itself is still stored nowhere, and
the reasoning below is UNCHANGED and is why: a proposal is not a durable home for
the scientist's words, because it can be rejected, superseded or withdrawn, and
neither of those acts returns the sentence it came from** — so if notes were
captured only for the unmatched segments, then rejecting a candidate — or failing to
accept one — would destroy the words it came from. Capturing every segment makes text survival independent of
what the reader proposed and of whether any acceptance ever succeeded.

WHY THE PROPOSED VALUE IS ALWAYS A QUOTE
========================================
Every rule below proposes either the literal substring the scientist wrote or a
number parsed from it. Nothing normalises a vocabulary term, expands an
abbreviation, converts a unit, or reformats a timestamp. A scientist reviewing a
candidate is therefore checking their own words, not a paraphrase they now have to
reverse-engineer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .providers.extraction import ORIGIN_TRANSCRIPT, FieldCandidate

__all__ = [
    "AMBIGUITY_POLICY",
    "MAX_CANDIDATES",
    "MAX_CANDIDATE_QUOTE_BYTES",
    "MAX_SEGMENTS",
    "OUTCOME_ABSTENTION",
    "OUTCOME_CLARIFICATION",
    "OUTCOME_NEEDS_REVIEW",
    "OUTCOME_UNMAPPED",
    "PRODUCED_BY",
    "READABLE_FIELD_PATHS",
    "RETENTION_ENFORCED_STATE",
    "RETENTION_STATES_NOT_IMPLEMENTED",
    "Abstention",
    "Clarification",
    "ReviewRequired",
    "RunRef",
    "Segment",
    "TranscriptReading",
    "TranscriptTooDense",
    "read_transcript",
    "segment_transcript",
]


class TranscriptTooDense(Exception):
    """One finalized transcript whose reading would exceed a candidate ceiling.

    **RAISED RATHER THAN REPORTED ON THE READING, AND THAT IS THE WHOLE POINT.**
    The obvious alternative — return a :class:`TranscriptReading` carrying a
    ``too_dense`` marker and an empty ``candidates`` tuple — was rejected because a
    caller that ignores the marker gets an empty list that looks like a complete
    reading of a transcript that read nothing, which is the silent discard this
    module exists to refuse, reached through the fix instead of through the defect.
    A truncated list is worse still. An exception is the one shape a caller cannot
    accidentally treat as a successful reading, and this route already has the
    idiom: ``notes.UnsupportedNote`` is raised by the model and becomes a typed
    ``422`` at the route.

    It carries the EXACT numbers rather than "at least" ones. Both are known
    exactly before any candidate is constructed, because locating the matches and
    de-duplicating the values is cheap and building
    :class:`~.providers.extraction.FieldCandidate` objects is not — see
    :func:`_segment_readings`.
    """

    def __init__(
        self,
        *,
        candidates: int,
        candidate_quote_bytes: int,
        maximum_candidates: int,
        maximum_candidate_quote_bytes: int,
    ) -> None:
        self.candidates = candidates
        self.candidate_quote_bytes = candidate_quote_bytes
        self.maximum_candidates = maximum_candidates
        self.maximum_candidate_quote_bytes = maximum_candidate_quote_bytes
        super().__init__(
            f"this transcript reads {candidates} candidates carrying "
            f"{candidate_quote_bytes} quoted bytes; the ceilings are "
            f"{maximum_candidates} candidates and "
            f"{maximum_candidate_quote_bytes} quoted bytes"
        )

#: Named on every candidate this module produces. It is NOT
#: ``deterministic-fake``: that name belongs to the provider seam's test double,
#: and reusing it would file an always-on product capability under a label whose
#: whole meaning is "a stand-in for a model that does not exist".
PRODUCED_BY = "transcript-reader"

#: The largest number of segments one finalized transcript may yield.
#:
#: A CEILING THAT REFUSES, NEVER TRUNCATES. Every segment becomes a stored note,
#: so an unbounded transcript is an unbounded write. A transcript over this size is
#: refused whole, with nothing written, because a partially-captured transcript is
#: the silent discard this feature exists to end — and a scientist who is told
#: "refused, split it" still has every word, while one who is told "captured" does
#: not.
MAX_SEGMENTS = 100

#: The largest number of candidates one finalized transcript may read.
#:
#: WHY A COUNT CEILING EXISTS IN THE READER AT ALL. ``MAX_SEGMENTS`` does not bound
#: this, and the reason is what punctuation-free ASR emits: a transcript with no
#: ``.``, ``!``, ``?`` or newline anywhere is **one** segment, so it passes the
#: segment ceiling whatever it contains. Measured on the code that shipped without
#: this bound, through the real route: a **27,025-byte single segment** naming 3,000
#: distinct kelvin values produced **3,001 candidates** and a **165,828,285-byte**
#: response, built and serialised INSIDE ``record_lock``. Every individual refusal
#: worked exactly as designed — the durable write refused all 3,001 as
#: ``proposals_too_large`` and minted none — because the durable write is not where
#: the cost is. The RESPONSE and the LOCK HOLD are.
#:
#: **THE NUMBER IS A JUDGEMENT, NOT A MEASUREMENT, AND SAYING SO IS PART OF IT** —
#: ``routes._MAX_PROPOSALS_PER_RECORD`` makes the same disclosure for the same
#: reason. Nothing here has measured a response-assembly or lock-hold cost at any
#: candidate count on the deployed pod, so no figure in this comment is derived from
#: one. What it IS derived from is the worst LEGITIMATE case it must still admit: a
#: transcript at the segment ceiling with a hedged chain in every sentence —
#: ``MAX_SEGMENTS`` × 4 = 400 — which this admits with headroom. A single 256 KiB
#: ASR blob is the other worst legitimate case, and it is bounded by BYTES rather
#: than by count; see below.
MAX_CANDIDATES = 500

#: The largest total quoted-segment size, in bytes, one transcript's candidates may
#: carry: ``sum(len(segment.text.encode()) for each candidate)``.
#:
#: **THE TWO BOUNDS DO NOT COMPOSE, AND THIS EXISTS BECAUSE THEY DO NOT.** This
#: repository has already solved exactly this shape once and the precedent is worth
#: citing rather than re-deriving: ``routes._MAX_PROPOSALS_PER_RECORD``
#: (``routes.py`` ~12132) beside ``routes._MAX_PROPOSAL_STATE_BYTES`` (~12176),
#: whose comment reads *"THE TWO BOUNDS ABOVE DO NOT COMPOSE, AND THIS EXISTS
#: BECAUSE THEY DO NOT … a bound on rows that a client can defeat by making each
#: row large is not a bound."* It is the same defeat here, and it is cheap: every
#: candidate carries the whole segment TWICE — once as ``quote`` and once inside the
#: ``rule`` sentence — so the cost is O(values × segment length), and a caller that
#: has run out of COUNT still has 256 KiB of transcript to spend on LENGTH.
#:
#: Measured, and this is the measurement that proves the pair is needed rather than
#: one of them: with ``", maybe "`` between the values — i.e. hedged, and therefore
#: still accepted by :data:`_HEDGE_BRIDGE` — the same attack produced **3,001
#: candidates** and a **273,900,285-byte** response. **The adjacency gate does not
#: bound size, and a size bound does not make values honest.** Two defects, two
#: fixes.
#:
#: **THE NUMBER IS A JUDGEMENT, NOT A MEASUREMENT.** It is written as a multiple of
#: the transcript ceiling rather than as a bare literal, so it follows that constant
#: instead of drifting from it: ``routes._MAX_TRANSCRIPT_BYTES`` is
#: ``_MAX_NOTE_BYTES`` = 256 KiB, and a transcript that fills it and reads two
#: candidates per segment costs 2 × 256 KiB of quotes. That is the worst LEGITIMATE
#: case, it is admitted, and this is twice it. ``test_transcript_capture_ceilings``
#: pins the two constants against each other so the multiple cannot silently stop
#: being one. At the ceiling the response is roughly 2 MiB rather than the 274 MB
#: above, because the quote is carried twice.
MAX_CANDIDATE_QUOTE_BYTES = 4 * 256 * 1024

OUTCOME_CLARIFICATION = "clarification"
OUTCOME_NEEDS_REVIEW = "needs_review"
OUTCOME_ABSTENTION = "abstention"
OUTCOME_UNMAPPED = "unmapped"


# --- retention: exactly one state, because exactly one is enforced -------------

#: The ONE retention state this build's storage architecture actually enforces.
#:
#: A finalized transcript is stored as Unmapped Notes inside the experiment's own
#: state document, and it stays there for the life of the experiment. That is not a
#: policy this module chose; it is what the notes model *is* — it offers no delete,
#: by design, and dismissal is a recorded state rather than a removal.
RETENTION_ENFORCED_STATE = "retained_with_experiment"

#: The retention states this build DOES NOT offer, each with the reason.
#:
#: They are listed rather than omitted. A settings screen with one option looks
#: like an oversight; a settings screen with one option and a stated reason for
#: each absent one is a disclosure. Neither of these can be implemented honestly
#: today: both are deletion guarantees, and there is no deletion anywhere in the
#: notes model to build one on. Offering a control that quietly did nothing would
#: be worse than offering none.
RETENTION_STATES_NOT_IMPLEMENTED: tuple[dict[str, str], ...] = (
    {
        "state": "retain_during_draft",
        "reason": (
            "This would require the transcript to be removed when the record is "
            "exported or submitted. Captured content is stored as notes, and this "
            "build has no operation that removes a note — dismissing one records a "
            "review decision and leaves the text readable. Offering this state "
            "would promise a deletion that nothing performs."
        ),
    },
    {
        "state": "remove_after_extraction",
        "reason": (
            "This would require the transcript to be removed once candidates have "
            "been reviewed. The same missing deletion applies, and it would also "
            "destroy the words behind every candidate a scientist rejected, which "
            "is the loss this feature is built to prevent."
        ),
    },
)


# --- the ambiguity policy, stated once and served -----------------------------

#: EVERY ambiguity this reader can encounter, with the outcome it produces and why
#: that outcome rather than another. Served by the route so the policy a client
#: explains and the policy the reader applies are one expression.
AMBIGUITY_POLICY: tuple[dict[str, str], ...] = (
    {
        "kind": "run_target_required",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "No run was selected for this capture. Every value this reader can "
            "propose is a run-level field, so it asks which run rather than "
            "choosing one. A record with exactly one run is not an exception: "
            "attaching content to the only run that happens to exist is an "
            "invention, and this build already refuses it when capturing a note."
        ),
    },
    {
        "kind": "unknown_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript names a run this record does not have. The reference "
            "is reported with the runs that do exist, and no candidate is "
            "proposed from this transcript — the scientist may have selected the "
            "wrong run, or may be describing work not yet recorded here."
        ),
    },
    {
        "kind": "ambiguous_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript names something that matches more than one run of "
            "this record. The matching runs are listed and none is chosen; "
            "preferring the first would make the target depend on creation order "
            "rather than on what was said."
        ),
    },
    {
        "kind": "conflicting_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript names a run other than the one selected for this "
            "capture. Both are reported and neither wins: a selection is a "
            "deliberate act and so is saying a run's name, and this reader has no "
            "grounds to decide which one the scientist meant."
        ),
    },
    {
        "kind": "vague_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript refers to a run by position or by relation — 'the "
            "second run', 'the previous run' — rather than by name, number or id. "
            "This reader performs no positional arithmetic: 'the second run' is "
            "not the same claim as 'run 2', and treating them as equal would "
            "silently retarget a value."
        ),
    },
    {
        "kind": "conflicting_values_for_one_field",
        "outcome": OUTCOME_NEEDS_REVIEW,
        "rule": (
            "Two statements propose different values for the same field — in two "
            "sentences, or inside ONE sentence such as 'around 425 K, maybe 430 "
            "K'. Both candidates are returned and grouped, so the scientist "
            "resolves the contradiction. Choosing the later one would be a guess "
            "dressed as a convention, and dropping both would lose something that "
            "was said twice. The same value restated inside one sentence is not a "
            "contradiction and produces one candidate. Inside ONE sentence a "
            "second value is read only when a hedging word — 'maybe', 'perhaps', "
            "'or', 'about', 'and again' and the like, from a closed list — sits "
            "immediately between the two, with nothing else in the gap; "
            "'425 K and the pressure was 3 K' states two different quantities, "
            "and reading the second as a temperature would invent a value the "
            "transcript does not give."
        ),
    },
    {
        "kind": "temperature_not_in_kelvin",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "A temperature was stated in a unit other than kelvin, and the field "
            "records kelvin. Converting it would put a number in the record that "
            "nobody said, so nothing is proposed and the statement is reported. "
            "The scientist can state the kelvin value, or accept nothing."
        ),
    },
    {
        "kind": "implicit_only_subject",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "The transcript describes the absorbing element or the absorption "
            "edge. This build treats both as implicit, sidecar-only content "
            "because the official record schema it validates against provides no "
            "native field for them, so there is no path to propose and none is "
            "invented."
        ),
    },
    {
        "kind": "unmatched_text",
        "outcome": OUTCOME_UNMAPPED,
        "rule": (
            "No rule matched. The text is stored verbatim as an Unmapped Note for "
            "review; it is never dropped and never guessed at."
        ),
    },
)


# --- the value shapes ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Segment:
    """One sentence-ish span of the finalized transcript, located by character.

    Offsets index back into the original text exactly — they are computed by
    scanning forward through it — so a quote a candidate stakes its provenance on
    can always be checked against the source.
    """

    index: int
    text: str
    start_char: int
    end_char: int

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }


@dataclass(frozen=True, slots=True)
class RunRef:
    """The identifiers of one run, as this reader is allowed to see them.

    Deliberately NOT the run itself: matching a spoken reference against a run's
    measured values would make the target depend on a classification this reader
    has no grounds to make. Label, ordinal, id and record id are what a person
    says out loud.
    """

    id: str
    label: str
    ordinal: int
    record_id: str | None = None

    def to_option(self) -> dict:
        """The shape a clarification offers as a choice. Identifiers only."""
        return {"run_id": self.id, "label": self.label, "ordinal": self.ordinal}


@dataclass(frozen=True, slots=True)
class Clarification:
    """A question this reader cannot answer, with the alternatives it can see."""

    kind: str
    question: str
    quote: str | None
    options: tuple[dict, ...] = ()
    segment_index: int | None = None

    @property
    def outcome(self) -> str:
        return OUTCOME_CLARIFICATION

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "kind": self.kind,
            "question": self.question,
            "quote": self.quote,
            "options": [dict(option) for option in self.options],
            "segment_index": self.segment_index,
        }


@dataclass(frozen=True, slots=True)
class Abstention:
    """A subject this reader recognised and deliberately proposed nothing for."""

    kind: str
    reason: str
    quote: str
    segment_index: int

    @property
    def outcome(self) -> str:
        return OUTCOME_ABSTENTION

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "kind": self.kind,
            "reason": self.reason,
            "quote": self.quote,
            "segment_index": self.segment_index,
        }


@dataclass(frozen=True, slots=True)
class ReviewRequired:
    """Two or more candidates that contradict each other at one field path."""

    kind: str
    field_path: str
    reason: str
    #: Indexes into :attr:`TranscriptReading.candidates`. Every one of them is
    #: still present there; this groups them, it never removes them.
    candidate_indexes: tuple[int, ...]

    @property
    def outcome(self) -> str:
        return OUTCOME_NEEDS_REVIEW

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "kind": self.kind,
            "field_path": self.field_path,
            "reason": self.reason,
            "candidate_indexes": list(self.candidate_indexes),
        }


@dataclass(frozen=True, slots=True)
class TranscriptReading:
    """One pass over one finalized transcript. Proposes; never applies.

    ``applied`` is a constant ``False`` property rather than a field, for the
    reason ``ExtractionResult.applied`` is one: a reading cannot be constructed
    claiming it wrote something.
    """

    segments: tuple[Segment, ...]
    candidates: tuple[FieldCandidate, ...]
    clarifications: tuple[Clarification, ...]
    abstentions: tuple[Abstention, ...]
    review_required: tuple[ReviewRequired, ...]
    #: Segment index -> the single candidate index it produced, when it produced
    #: exactly one. A segment producing none, or more than one, is absent — see
    #: :func:`candidate_for_segment`.
    candidate_by_segment: Mapping[int, int]
    #: The run every candidate is proposed against, or ``None`` when no candidate
    #: was proposed at all.
    run_target: str | None

    @property
    def applied(self) -> bool:
        """Always ``False``. This module writes nothing, anywhere."""
        return False

    @property
    def unmapped_segment_indexes(self) -> tuple[int, ...]:
        """Segments that produced no candidate. Every one becomes a note — but so
        does every other segment; see the module docstring, rule (4)."""
        return tuple(
            segment.index
            for segment in self.segments
            if segment.index not in self.candidate_by_segment
        )

    def candidate_for_segment(self, index: int) -> FieldCandidate | None:
        """The one candidate a segment produced, or ``None``.

        ``None`` for a segment that produced two, deliberately. A note carries at
        most one ``candidate_field_path``, and recording one of two proposals
        there would state a preference this reader does not hold.
        """
        position = self.candidate_by_segment.get(index)
        return None if position is None else self.candidates[position]


# --- segmentation -------------------------------------------------------------

#: A sentence boundary or a line break. Fixed and simple on purpose: a cleverer
#: splitter would be a language model in disguise, and the offsets are what a
#: quote's honesty rests on.
_SEGMENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def segment_transcript(text: str) -> tuple[Segment, ...]:
    """Split a transcript into located segments. Offsets round-trip exactly."""
    pieces = [piece for piece in _SEGMENT_BOUNDARY.split(text) if piece and piece.strip()]
    segments: list[Segment] = []
    cursor = 0
    for index, piece in enumerate(pieces):
        start = text.index(piece, cursor)
        end = start + len(piece)
        cursor = end
        segments.append(Segment(index=index, text=piece, start_char=start, end_char=end))
    return tuple(segments)


# --- the closed rule table ----------------------------------------------------
#
# EVERY PATH BELOW IS RUN-LEVEL, and that is not a coincidence: the only operation
# in this application that writes a confirmed value at a dotted official path is
# the run edit, and this reader refuses to propose anything it cannot show a
# scientist a way to accept. The route re-checks every path against the set that
# operation enforces, so the two cannot drift.

#: ``<number>`` — a plain decimal. No exponents, no thousands separators, no
#: unicode digits: a number a person dictates, not a number a machine emits.
_NUMBER = r"(-?\d{1,6}(?:\.\d{1,6})?)"

#: temperature ... N K. The unit is REQUIRED and must be kelvin.
_TEMPERATURE_K = re.compile(
    rf"\btemperatures?\b[^.;:]{{0,40}}?{_NUMBER}\s*(?:K\b|kelvin\b)", re.IGNORECASE
)

#: The KELVIN VALUE FORM ALONE — the same value the rule above reads, without the
#: label in front of it.
#:
#: WHY A SECOND PATTERN EXISTS AT ALL. ``_TEMPERATURE_K`` is anchored on the literal
#: word ``temperature``, and a scientist states a second value without saying the
#: word again: *"the temperature was around 425 K, maybe 430 K"*. Matching the rule
#: repeatedly over that sentence finds ONE match, because there is one label — so
#: ``finditer`` alone left 430 unread, which is the silent loss this whole reader
#: exists to refuse. This pattern is what a restatement of an already-labelled
#: quantity looks like, and :func:`read_transcript` will only apply it AFTER the
#: label-anchored rule has matched in the same segment. A bare number is still never
#: read: the unit is required here exactly as it is required above.
#:
#: ``(?<![\d.])`` keeps a scan that resumes mid-number from reading ``30`` out of
#: ``430``.
_TEMPERATURE_K_RESTATED = re.compile(
    rf"(?<![\d.]){_NUMBER}\s*(?:K\b|kelvin\b)", re.IGNORECASE
)

#: temperature ... N <any other unit>. Matched only to ABSTAIN, never to propose.
_TEMPERATURE_OTHER = re.compile(
    rf"\btemperatures?\b[^.;:]{{0,40}}?{_NUMBER}\s*(?:°\s*)?"
    r"(?:C\b|F\b|celsius\b|centigrade\b|fahrenheit\b|degrees?\b)",
    re.IGNORECASE,
)

#: ``atmosphere`` / ``environment`` followed by a short literal phrase. The value
#: is the phrase EXACTLY as written, trimmed of surrounding whitespace and of a
#: single trailing sentence terminator. Nothing is normalised into a vocabulary.
_PHRASE = r"([A-Za-z0-9][A-Za-z0-9 _%/+.()-]{0,60}?)"

#: The separator between the label and the phrase. AT LEAST ONE SIGNAL IS
#: REQUIRED — a copula, a colon, or an equals sign — so a bare "atmosphere dry
#: nitrogen" does not match. Without it the rule would read the next few words
#: after the word "atmosphere" wherever it appeared in a sentence, which is how a
#: quotative rule turns into a guessing one.
_LABEL_SEPARATOR = r"(?:\s+(?:was|is|were|of)\s*[:=]?|\s*[:=])\s*"
_ATMOSPHERE = re.compile(
    rf"\batmosphere\b{_LABEL_SEPARATOR}{_PHRASE}\s*[.;!?]?\s*$", re.IGNORECASE
)
_ENVIRONMENT = re.compile(
    rf"\benvironment\b{_LABEL_SEPARATOR}{_PHRASE}\s*[.;!?]?\s*$", re.IGNORECASE
)

#: An ISO-8601 instant in UTC, written out. Taken VERBATIM — never reformatted,
#: never completed from a partial date, never defaulted to today.
_INSTANT = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
_ACQUIRED_START = re.compile(
    rf"\b(?:started|start|beginning|began)\b[^.;:]{{0,40}}?{_INSTANT}", re.IGNORECASE
)
_ACQUIRED_END = re.compile(
    rf"\b(?:ended|end|finished|stopped)\b[^.;:]{{0,40}}?{_INSTANT}", re.IGNORECASE
)

#: The instant form ALONE, for the same reason ``_TEMPERATURE_K_RESTATED`` exists:
#: *"the run started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z"* says the
#: start word once.
#:
#: ~~"A full UTC instant is self-identifying, so a restatement of one cannot be
#: mistaken for something else."~~ — **FALSE, and CORRECTED 2026-09-12 by
#: independent review.** The form is self-identifying as *an instant*; it says
#: nothing about *which* instant of the run it is. Measured on the code that
#: shipped this comment: *"The scan started …01-01T00:00:00Z, ran until
#: …01-02T00:00:00Z"* proposed the END instant as an alternative acquisition
#: START, and *"…started …01-01T00:00:00Z and we will repeat it
#: …02-01T00:00:00Z"* proposed a FUTURE scan's instant as this one's start. The
#: sentence quoted above is exactly what made that look safe. What actually keeps
#: a restatement honest is :data:`_HEDGE_BRIDGE` below, not the value's format —
#: and the phrase rules still get no restatement pattern, for the separate and
#: still-correct reason ``_Rule`` gives.
_INSTANT_RESTATED = re.compile(_INSTANT)

#: THE ONE THING THAT MAKES A RESTATEMENT READABLE AS A RESTATEMENT.
#:
#: A restatement pattern (``_TEMPERATURE_K_RESTATED``, ``_INSTANT_RESTATED``) is a
#: bare value form with no label in front of it, so on its own it matches *every*
#: later value of that shape in the sentence — including values that belong to a
#: different quantity entirely. Measured on the code that shipped without this
#: gate, each of these proposed TWO values for ``context.temperature_K`` or for
#: ``timestamps.acquired_start_utc``, and the second one is not in the transcript:
#:
#: ===================================================================  =============
#: sentence                                                             falsely read
#: ===================================================================  =============
#: ``The temperature was 425 K, ramped at 3 K/min``                     a ramp RATE
#: ``The temperature was 425 K and the step size was 0.5 K``            a STEP SIZE
#: ``Sample temperature 425 K, cryostat setpoint 80 K, base 4 K``       TWO others
#: ``The temperature was 425 K and the pressure was 3 K``               a PRESSURE
#: ``…started …01-01T00:00:00Z, ran until …01-02T00:00:00Z``            the END
#: ``…started …01-01T00:00:00Z and we will repeat it …02-01T00:00:00Z`` a FUTURE run
#: ===================================================================  =============
#:
#: Each of those shipped a ``rule`` string asserting that the sentence *restated*
#: the quantity, which is a statement about the transcript that the transcript does
#: not support — ``CLAUDE.md`` §5. It is strictly worse than the silent omission it
#: replaced: an omission loses a reading, an assertion invents one.
#:
#: THE GATE, STATED AS THE INVARIANT IT IMPLEMENTS. A restatement is read only if
#: the text lying between the end of the previous accepted reading of that rule and
#: the start of this restatement's VALUE consists ENTIRELY of an optional comma,
#: optional HORIZONTAL whitespace (never a line break — see ``_H_SPACE``), and
#: exactly one connective drawn from the closed hedge list below. Nothing else may
#: sit in that gap — no noun, no verb, no second label.
#:
#: WHY A HEDGE AND NOT MERELY ADJACENCY. The hedge is what makes the second value a
#: statement about the SAME quantity. ``425 K, 430 K`` is adjacent and means
#: nothing in particular; ``425 K, maybe 430 K`` is a person being uncertain about
#: one number, which is the case the project owner asked for.
#:
#: **BARE ``and`` IS DELIBERATELY NOT IN THE LIST.** It is conjunctive, not
#: hedging: *"425 K and 430 K"* may well be two different quantities, and half the
#: table above is a bare ``and``. ``and again`` IS in the list, because ``again``
#: is what makes it a restatement of one quantity rather than a second one.
#:
#: **CLAUSE-BOUNDING COMES FREE AND IS NOT A SEPARATE CHECK.** The pattern admits
#: only a comma, horizontal whitespace and letters, so a ``.``, ``;`` or ``:`` in
#: the gap refuses — which is the clause bound ``_TEMPERATURE_K`` imposes on itself
#: with ``[^.;:]``. It is stated here rather than added as a second check.
#:
#: **AND CLAUSE-BOUNDING ALONE WOULD HAVE BEEN INSUFFICIENT BY A WIDER MARGIN THAN
#: THE REVIEW SAID.** The review's phrasing was *"two of the rows above have no
#: punctuation"*, which reads as though clause-bounding caught the other four.
#: Measured over all six gaps (``test_clause_bounding_alone_would_have_caught``):
#:
#: * clause-bounding on ``.;:`` — the bound ``_TEMPERATURE_K`` already uses —
#:   refuses **0 of 6**. Not one gap contains any of those characters.
#: * clause-bounding that ALSO breaks at a comma refuses **3 of 6**; the three
#:   bare-``and`` rows survive it.
#:
#: So the hedge is not a refinement of clause-bounding, it is the whole gate; and
#: a comma cannot be treated as a clause break here anyway, because the owner's
#: own sentence — *"around 425 K, maybe 430 K"* — bridges across one.
#:
#: **ADJACENCY CHAINS.** After a restatement is accepted the anchor advances to the
#: end of it, so *"425 K, maybe 430 K, or perhaps 435 K"* reads all three — each
#: hedged against the value before it. A REFUSED restatement does not advance the
#: anchor, which is why *"425 K, cryostat setpoint 80 K, base 4 K"* refuses both
#: rather than refusing 80 and then measuring 4's gap from it.
_HEDGE_CONNECTIVES: tuple[str, ...] = (
    "maybe",
    "perhaps",
    "possibly",
    "around",
    "about",
    "roughly",
    "approximately",
    "and again",
    "again",
    "alternatively",
    "or",
)
#: Horizontal whitespace: every whitespace character EXCEPT a line break.
#:
#: ``\s`` was the first spelling and it was WRONG in a way only a test caught: it
#: admits ``\n``, so ``", maybe \n"`` bridged, and a hedge on the far side of a line
#: break is not "immediately between" two values. Matching with ``fullmatch`` rather
#: than ``$`` does NOT fix that — ``$``'s before-a-trailing-newline laxity is a
#: different hole — and believing it did was the error. A segment cannot contain a
#: newline today (``_SEGMENT_BOUNDARY`` splits on them), so this closes nothing
#: live; it is written so nothing opens if segmentation ever changes. It is a
#: character class rather than ``[ \t]`` so a non-breaking space in dictated text
#: still bridges.
_H_SPACE = r"[^\S\n]"

#: Matched with ``fullmatch``, never ``search`` or ``$``: the hedge must be the
#: WHOLE gap between the two values, and ``$`` would also match before a trailing
#: newline.
_HEDGE_BRIDGE = re.compile(
    rf",?{_H_SPACE}*(?:or{_H_SPACE}+)?(?:"
    + "|".join(
        connective.replace(" ", f"{_H_SPACE}+")
        for connective in _HEDGE_CONNECTIVES
    )
    + rf"){_H_SPACE}*",
    re.IGNORECASE,
)

#: The absorbing element / absorption edge, which this build records as implicit,
#: sidecar-only content because the official schema has no native field for them.
_IMPLICIT_ONLY = re.compile(
    r"\b(?:absorbing element|absorption edge|[KL]\d?[- ]edge)\b", re.IGNORECASE
)

#: A run named by number, label or id.
_RUN_REFERENCE = re.compile(r"\brun\s+(?:number\s+|#\s*)?([A-Za-z0-9][A-Za-z0-9_-]{0,63})\b", re.IGNORECASE)

#: A run named by position or relation. Matched only to ASK, never to resolve.
_VAGUE_RUN = re.compile(
    r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|last|latest|previous|prior|next|"
    r"other|same|earlier|later)\s+run\b",
    re.IGNORECASE,
)

#: Words that follow ``run`` but never name one. Without this, "run at 300 K" and
#: "run was repeated" would each be read as a reference to a run called "at" or
#: "was" and would produce a spurious unknown-run clarification on almost every
#: sentence.
_NOT_A_RUN_NAME: frozenset[str] = frozenset(
    {
        "at", "was", "were", "is", "in", "on", "for", "with", "the", "a", "an",
        "and", "to", "from", "by", "of", "again", "twice", "under", "over",
        "started", "ended", "finished", "began", "completed", "aborted", "failed",
        "repeated", "took", "had", "has", "used", "using", "after", "before",
        "this", "that", "these", "those", "it", "we", "i",
    }
)


@dataclass(frozen=True, slots=True)
class _Rule:
    """One entry of the closed table: a pattern, a path, and how to read a value.

    ``restatement`` is the rule's value form WITHOUT its label, and it is ``None``
    for every rule whose value is a free phrase. That is a decision, not an
    omission: ``430 K`` and ``2026-01-02T00:00:00Z`` carry a unit or a format that
    says what they are, so a second one in the same sentence is recognisably another
    statement of the same quantity. A bare phrase carries nothing — a second phrase
    after ``atmosphere was dry nitrogen`` could be about anything, and reading it as
    another atmosphere would be a guess. The phrase rules are also anchored to the
    end of the segment and so can match at most once regardless.

    ``restated_sentence`` exists because a candidate's ``rule`` is how a scientist
    checks WHY a value was read. ``sentence`` claims the label and the value appeared
    in one clause, which is not true of a restatement, so a restatement must not
    borrow it. **And it must state the MECHANISM, not just the conclusion** — that a
    hedging word sat immediately between the two values, which is the whole of why
    the second one was readable. The first version of these three strings asserted
    only that "the same sentence restates the …", which was a claim about the
    transcript that the reader had not checked and, on six measured sentences, that
    the transcript did not support; see :data:`_HEDGE_BRIDGE`.
    """

    name: str
    pattern: re.Pattern[str]
    field_path: str
    numeric: bool
    sentence: str
    restatement: re.Pattern[str] | None = None
    restated_sentence: str | None = None


_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="temperature_kelvin",
        pattern=_TEMPERATURE_K,
        field_path="context.temperature_K",
        numeric=True,
        sentence=(
            "the words 'temperature' and a number followed by K or kelvin appear "
            "in one clause; the number is read as written and the unit is not "
            "converted"
        ),
        restatement=_TEMPERATURE_K_RESTATED,
        restated_sentence=(
            "the same sentence restates the temperature: a HEDGING WORD — 'maybe', "
            "'perhaps', 'or', 'about', 'around', 'and again' or another from a "
            "closed list — sits immediately between the number the word "
            "'temperature' introduced and a further number followed by K or "
            "kelvin, with nothing else at all in the gap. That hedge is the ONLY "
            "reason this number is read as an ALTERNATIVE value for the same "
            "field: without one, a later number followed by K is a different "
            "quantity — a ramp rate, a step size, a setpoint — and is not read. "
            "It is not a correction, not a preference, and NOT a range or an "
            "interval, neither of which anybody stated"
        ),
    ),
    _Rule(
        name="acquisition_start",
        pattern=_ACQUIRED_START,
        field_path="timestamps.acquired_start_utc",
        numeric=False,
        sentence=(
            "a start word and a full UTC instant appear in one clause; the instant "
            "is taken exactly as written and is never completed or reformatted"
        ),
        restatement=_INSTANT_RESTATED,
        restated_sentence=(
            "the same sentence restates the start: a HEDGING WORD — 'maybe', "
            "'perhaps', 'or', 'about', 'around', 'and again' or another from a "
            "closed list — sits immediately between the instant the start word "
            "introduced and a further full UTC instant, with nothing else at all "
            "in the gap. That hedge is the ONLY reason this instant is read as an "
            "ALTERNATIVE value for the same field: without one, a later instant "
            "belongs to something else — the end of this run, or another run "
            "entirely — and is not read. It is taken exactly as written, and it is "
            "not a correction and not a range"
        ),
    ),
    _Rule(
        name="acquisition_end",
        pattern=_ACQUIRED_END,
        field_path="timestamps.acquired_end_utc",
        numeric=False,
        sentence=(
            "an end word and a full UTC instant appear in one clause; the instant "
            "is taken exactly as written and is never completed or reformatted"
        ),
        restatement=_INSTANT_RESTATED,
        restated_sentence=(
            "the same sentence restates the end: a HEDGING WORD — 'maybe', "
            "'perhaps', 'or', 'about', 'around', 'and again' or another from a "
            "closed list — sits immediately between the instant the end word "
            "introduced and a further full UTC instant, with nothing else at all "
            "in the gap. That hedge is the ONLY reason this instant is read as an "
            "ALTERNATIVE value for the same field: without one, a later instant "
            "belongs to something else and is not read. It is taken exactly as "
            "written, and it is not a correction and not a range"
        ),
    ),
    _Rule(
        name="atmosphere",
        pattern=_ATMOSPHERE,
        field_path="context.thermodynamics.atmosphere",
        numeric=False,
        sentence=(
            "the word 'atmosphere' is followed by a short phrase that ends the "
            "sentence; the phrase is proposed exactly as written and is not "
            "matched against any vocabulary"
        ),
    ),
    _Rule(
        name="environment",
        pattern=_ENVIRONMENT,
        field_path="context.environment",
        numeric=False,
        sentence=(
            "the word 'environment' is followed by a short phrase that ends the "
            "sentence; the phrase is proposed exactly as written and is not "
            "matched against any vocabulary"
        ),
    ),
)

#: Every path the closed table above can propose. Exported so a route can assert
#: it against the set the write operation actually enforces, rather than a
#: reviewer noticing.
READABLE_FIELD_PATHS: frozenset[str] = frozenset(rule.field_path for rule in _RULES)


def _read_number(raw: str) -> Any:
    """``int`` when the text has no decimal point, else ``float``. Never rounded."""
    return float(raw) if "." in raw else int(raw)


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Whether two half-open character spans share any character."""
    return left[0] < right[1] and right[0] < left[1]


# --- locating the readings, separately from constructing the candidates -------


@dataclass(frozen=True, slots=True)
class _Reading:
    """One value this reader HAS read, before it becomes a candidate.

    It exists so the two ceilings can be enforced on an EXACT count and an EXACT
    byte total without the allocation they are there to prevent: a match object
    and a parsed value per reading, rather than a
    :class:`~.providers.extraction.FieldCandidate` carrying the segment text
    twice. Internal and never served.
    """

    rule: "_Rule"
    match: re.Match[str]
    restated: bool
    value: Any


def _segment_readings(segment: Segment) -> list["_Reading"]:
    """Every value one segment states, in the order a candidate list wants them.

    Pure and cheap. It allocates no candidate and formats no ``rule`` sentence,
    which is what lets :func:`read_transcript` learn what a segment WOULD cost
    before it pays it.
    """
    # PASS ONE — EVERY label-anchored match of every rule, not just the first.
    #
    # ~~`match = rule.pattern.search(segment.text)`~~ — CORRECTED. `search`
    # returns the FIRST match and nothing else, so a sentence that names the
    # label twice ("the temperature was 425 K and the temperature at the end was
    # 430 K") proposed one value and lost the other in silence: no candidate, no
    # clarification, no abstention, no `review_required` row. The transcript
    # survived as a note, so nothing was destroyed — what was lost was the
    # READING, and with it the scientist's chance to accept either value.
    labelled = [list(rule.pattern.finditer(segment.text)) for rule in _RULES]

    # The VALUE spans every label-anchored match of every rule has claimed.
    # ACROSS rules, which is what stops pass two from reading a value another
    # rule read under its own label: "started X and ended Y" states two
    # DIFFERENT fields, and a restatement scan that saw only "another instant
    # after the start word" would propose Y as a second acquisition START,
    # contradicting the word "ended" sitting in front of it. Value spans rather
    # than whole-match spans for the reason the abstention guard elsewhere gives.
    #
    # KEPT AS DEFENCE IN DEPTH now that `_HEDGE_BRIDGE` also refuses that
    # sentence. The two guards are independent and they AGREE on it — proven by
    # measurement rather than asserted, in
    # `test_both_restatement_guards_refuse_started_A_and_ended_B` — and keeping
    # both means a widened hedge list cannot reintroduce a cross-field read.
    claimed_value_spans = [
        match.span(1) for matches in labelled for match in matches
    ]

    found: list["_Reading"] = []
    for rule, matches in zip(_RULES, labelled, strict=True):
        if not matches:
            continue
        # `(match, restated)`, label-anchored readings first so a field's
        # candidates stay contiguous and in the order they were said.
        readings: list[tuple[re.Match[str], bool]] = [
            (match, False) for match in matches
        ]

        # PASS TWO — the same sentence restating the quantity WITHOUT restating
        # the label. Gated on pass one having matched, so a bare number is never
        # read; scanned only from the end of the last label-anchored match, so
        # the label still PRECEDES the value exactly as the rule's own pattern
        # requires ("At 300 K the temperature was 425 K" reads 425 alone).
        #
        # AND GATED ON AN ADJACENT HEDGED CONNECTIVE, which is the correction of
        # 2026-09-12: without it this scan read the whole remainder of the segment
        # for a bare value form and proposed a ramp rate, a step size, a pressure,
        # a cryostat setpoint, an END instant and a FUTURE run's instant as
        # alternatives for the labelled field. `_HEDGE_BRIDGE` carries the table.
        #
        # `fullmatch`, NOT `$`. The bridge must be the WHOLE gap, and `$` also
        # matches before a trailing newline — the exact laxity this repository
        # already ships an exactness gate for (`src/isaac_records/exactness.py`).
        # A segment cannot contain a newline today (`_SEGMENT_BOUNDARY` splits on
        # them), so this is not a live hole being closed; it is a guard written so
        # it does not become one if segmentation ever changes.
        if rule.restatement is not None:
            anchor = max(match.end() for match in matches)
            for extra in rule.restatement.finditer(segment.text, anchor):
                if any(
                    _spans_overlap(extra.span(1), claimed)
                    for claimed in claimed_value_spans
                ):
                    continue
                if _HEDGE_BRIDGE.fullmatch(segment.text[anchor : extra.start(1)]) is None:
                    continue
                readings.append((extra, True))
                # THE ANCHOR ADVANCES ONLY ON AN ACCEPTED RESTATEMENT, so the
                # chain is a chain of hedges rather than a chain of positions:
                # "425 K, maybe 430 K, or perhaps 435 K" reads all three, while
                # "425 K, cryostat setpoint 80 K, base 4 K" refuses both — 4's gap
                # is measured from 425, not from the 80 that was just refused.
                #
                # It advances even for a restatement the de-duplication below then
                # drops as an identical value, deliberately: adjacency is a fact
                # about the TEXT, so "425 K, maybe 425 K, or perhaps 430 K" still
                # reads 430.
                anchor = extra.end()

        # ONE VALUE STATED TWICE IN ONE SENTENCE IS ONE CANDIDATE.
        # "425 K, and again 425 K" is emphasis, not disagreement. Two identical
        # candidates would mint two durable proposals — `routes`'
        # `_mint_transcript_proposals` keys on the candidate INDEX, so they do
        # not collapse — giving one fact two independently acceptable rows.
        # SCOPED TO ONE SEGMENT, deliberately: two sentences are two statements,
        # and `test_the_same_value_said_twice_is_not_a_conflict` pins that as two
        # candidates. The equality is `repr`, the same one the grouping in
        # `read_transcript` uses, so the two cannot disagree about what "the same
        # value" means.
        seen: set[str] = set()
        for match, restated in readings:
            raw = match.group(1).strip()
            if not raw:
                continue
            value = _read_number(raw) if rule.numeric else raw
            if repr(value) in seen:
                continue
            seen.add(repr(value))
            found.append(
                _Reading(rule=rule, match=match, restated=restated, value=value)
            )
    return found


# --- run reference resolution -------------------------------------------------


def _matching_runs(token: str, known_runs: tuple[RunRef, ...]) -> tuple[RunRef, ...]:
    """Runs a spoken token could name. Identifiers only; never a measured value.

    The precedence copies the run search this application already ships: an id
    matches WHOLE (a ULID's leading characters are shared by every run created in
    one session, so a substring test against one is a match-everything), a label
    matches by substring because a label is prose a person wrote, and an all-digit
    token additionally matches by ordinal.
    """
    needle = token.strip().lower()
    if not needle:
        return ()
    ordinal = int(needle) if needle.isdigit() and len(needle) <= 6 else None
    matched: list[RunRef] = []
    for run in known_runs:
        if needle == run.id.lower():
            matched.append(run)
        elif run.record_id is not None and needle == run.record_id.lower():
            matched.append(run)
        elif needle in run.label.lower():
            matched.append(run)
        elif ordinal is not None and run.ordinal == ordinal:
            matched.append(run)
    return tuple(matched)


def _run_clarifications(
    segments: tuple[Segment, ...],
    *,
    selected_run: str | None,
    known_runs: tuple[RunRef, ...],
) -> tuple[Clarification, ...]:
    """Every run-reference ambiguity in the transcript. Resolves nothing."""
    found: list[Clarification] = []
    options = tuple(run.to_option() for run in known_runs)
    for segment in segments:
        vague = _VAGUE_RUN.search(segment.text)
        if vague is not None:
            found.append(
                Clarification(
                    kind="vague_run_reference",
                    question=(
                        "This sentence refers to a run by position rather than by "
                        "name, number or id. Which run is it?"
                    ),
                    quote=vague.group(0),
                    options=options,
                    segment_index=segment.index,
                )
            )
            continue
        for match in _RUN_REFERENCE.finditer(segment.text):
            token = match.group(1)
            if token.lower() in _NOT_A_RUN_NAME:
                continue
            matched = _matching_runs(token, known_runs)
            if not matched:
                found.append(
                    Clarification(
                        kind="unknown_run_reference",
                        question=(
                            "This record has no run matching the run named here. "
                            "Which run is it, or should one be created?"
                        ),
                        quote=match.group(0),
                        options=options,
                        segment_index=segment.index,
                    )
                )
            elif len(matched) > 1:
                found.append(
                    Clarification(
                        kind="ambiguous_run_reference",
                        question=(
                            "The run named here matches more than one run of this "
                            "record. Which one is it?"
                        ),
                        quote=match.group(0),
                        options=tuple(run.to_option() for run in matched),
                        segment_index=segment.index,
                    )
                )
            elif selected_run is not None and matched[0].id != selected_run:
                found.append(
                    Clarification(
                        kind="conflicting_run_reference",
                        question=(
                            "This capture is addressed to one run and the "
                            "transcript names another. Which run should the values "
                            "be proposed against?"
                        ),
                        quote=match.group(0),
                        options=tuple(
                            run.to_option()
                            for run in known_runs
                            if run.id in {selected_run, matched[0].id}
                        ),
                        segment_index=segment.index,
                    )
                )
    return tuple(found)


# --- the reading ---------------------------------------------------------------


def read_transcript(
    text: str,
    *,
    selected_run: str | None,
    known_runs: tuple[RunRef, ...],
) -> TranscriptReading:
    """Read a FINALIZED transcript. Pure: no clock, no randomness, no I/O.

    ``selected_run`` is the run a scientist chose for this capture, and it is the
    ONLY thing that settles the target. A run named inside the transcript is
    checked against it and can raise a clarification, but it never becomes the
    target on its own — inferring a write target from prose is the guess this
    whole feature is arranged to refuse.

    **Candidates are withheld whenever the run target is unsettled**, which is
    every case where a clarification about the run was raised, and the case where
    no run was selected at all. That is deliberately blunt: a candidate a
    scientist could accept against the wrong run is worse than no candidate, and
    the transcript itself is retained either way, so nothing is lost by asking.
    """
    segments = segment_transcript(text)
    clarifications = list(
        _run_clarifications(segments, selected_run=selected_run, known_runs=known_runs)
    )
    if selected_run is None:
        clarifications.insert(
            0,
            Clarification(
                kind="run_target_required",
                question=(
                    "Which run do these notes describe? Every value this reader "
                    "can propose belongs to a run, and the run is never chosen "
                    "automatically — not even when the record has exactly one."
                ),
                quote=None,
                options=tuple(run.to_option() for run in known_runs),
                segment_index=None,
            ),
        )

    abstentions: list[Abstention] = []
    candidates: list[FieldCandidate] = []
    candidate_by_segment: dict[int, int] = {}
    #: Every reading this transcript will turn into a candidate, LOCATED but not
    #: yet constructed, with the two running totals the ceilings are checked
    #: against. See the check below for why construction is deferred.
    located: list[tuple[Segment, list["_Reading"]]] = []
    candidate_count = 0
    quote_bytes = 0
    # The run target is settled only when a run was selected AND nothing about a
    # run was left open. See the docstring.
    settled = selected_run is not None and not clarifications

    for segment in segments:
        implicit = _IMPLICIT_ONLY.search(segment.text)
        if implicit is not None:
            abstentions.append(
                Abstention(
                    kind="implicit_only_subject",
                    reason=(
                        "The absorbing element and the absorption edge are recorded "
                        "by this build as implicit, sidecar-only content: the "
                        "official record schema it validates against provides no "
                        "field for either, so there is no path to propose a value "
                        "at and none is invented."
                    ),
                    quote=implicit.group(0),
                    segment_index=segment.index,
                )
            )
        # THE NON-KELVIN DISCLOSURE, SPAN-GUARDED RATHER THAN SEGMENT-GUARDED.
        #
        # ~~`if other_unit is not None and not _TEMPERATURE_K.search(segment.text)`~~
        # — CORRECTED, because it asked "does this sentence contain ANY kelvin
        # reading?" and a kelvin reading ANYWHERE suppressed the disclosure for a
        # non-kelvin statement ELSEWHERE in the same sentence. Measured on the old
        # code: "Temperature was 425 K, maybe 430 C." proposed 425 and produced NO
        # abstention at all, so `430 C` vanished from the reading exactly as `430 K`
        # did — the same silent loss, reached through the guard instead of through
        # `search`.
        #
        # The narrow and correct question is whether THIS non-kelvin statement is
        # the one the kelvin rule already read, and the VALUE spans answer it. The
        # value spans rather than the whole-match spans, because `_TEMPERATURE_OTHER`
        # starts at the same `temperature` label and therefore always overlaps the
        # kelvin rule's whole match — comparing those would suppress every
        # disclosure and would look like it was working.
        kelvin_value_spans = [
            match.span(1) for match in _TEMPERATURE_K.finditer(segment.text)
        ]
        for other_unit in _TEMPERATURE_OTHER.finditer(segment.text):
            if any(
                _spans_overlap(other_unit.span(1), claimed)
                for claimed in kelvin_value_spans
            ):
                continue
            abstentions.append(
                Abstention(
                    kind="temperature_not_in_kelvin",
                    reason=(
                        "The temperature field records kelvin and this statement "
                        "gives another unit. Converting it would place a number in "
                        "the record that nobody stated, so nothing is proposed. "
                        "State the value in kelvin to propose one."
                    ),
                    quote=other_unit.group(0),
                    segment_index=segment.index,
                )
            )
        if not settled:
            continue
        found = _segment_readings(segment)
        if not found:
            continue
        located.append((segment, found))
        candidate_count += len(found)
        # EVERY CANDIDATE CARRIES THE WHOLE SEGMENT, so the segment's byte length
        # times the number of readings over it IS the quoted cost, exactly. It is
        # carried TWICE per candidate (`quote`, and inside the `rule` sentence), so
        # the served size is about twice this plus per-candidate overhead; the
        # ceiling is stated over the quoted bytes rather than over a guess at the
        # serialised size, because this half is a measurement and that half is not.
        quote_bytes += len(segment.text.encode("utf-8")) * len(found)

    # THE CEILINGS ARE APPLIED BEFORE THE FIRST `FieldCandidate` IS CONSTRUCTED,
    # AND THAT ORDERING IS THE POINT RATHER THAN AN OPTIMISATION. Building the
    # 3,001 candidates of the measured attack and then discarding them allocates
    # **137,256,245 bytes** of `rule` strings and **135,120,025** of `quote`,
    # inside `record_lock` — paying the ceiling in full in order to enforce it.
    # (Measured here, on the 45,025-byte hedged payload, with both ceilings lifted.
    # The reviewer's "~81 MB" is right for the 27,025-byte BARE payload, which the
    # adjacency gate now reads as ONE candidate, so it is no longer the payload
    # these ceilings fire on. Quoting the number for the wrong payload is the kind
    # of inherited figure this file corrects rather than carries.)
    #
    # The locating pass above allocates match objects and one value per reading,
    # which is what makes an EXACT count and an EXACT byte total available here for
    # nothing — and the byte total is exact, not an estimate: `quote_bytes` equals
    # `sum(len(candidate.quote.encode()))` over the candidates that would have been
    # built, measured identical at 135,120,025.
    if (
        candidate_count > MAX_CANDIDATES
        or quote_bytes > MAX_CANDIDATE_QUOTE_BYTES
    ):
        raise TranscriptTooDense(
            candidates=candidate_count,
            candidate_quote_bytes=quote_bytes,
            maximum_candidates=MAX_CANDIDATES,
            maximum_candidate_quote_bytes=MAX_CANDIDATE_QUOTE_BYTES,
        )

    for segment, found in located:
        produced: list[int] = []
        for reading in found:
            rule = reading.rule
            candidates.append(
                FieldCandidate(
                    field_path=rule.field_path,
                    proposed_value=reading.value,
                    quote=segment.text,
                    start_char=segment.start_char,
                    end_char=segment.end_char,
                    origin=ORIGIN_TRANSCRIPT,
                    produced_by=PRODUCED_BY,
                    rule=(
                        f"in the sentence {segment.text.strip()!r}, "
                        f"{rule.restated_sentence if reading.restated else rule.sentence}; "
                        f"the value is quoted from the transcript, not interpreted"
                    ),
                    provenance=MappingProxyType(
                        {
                            "reader_rule": rule.name,
                            "run_id": selected_run,
                            "segment_index": segment.index,
                            "matched_text": reading.match.group(0),
                            # A RESTATEMENT SAYS SO. Its `rule` sentence already
                            # explains it in prose; this is the same fact where a
                            # surface can branch on it without parsing English.
                            "restated_in_same_sentence": reading.restated,
                        }
                    ),
                )
            )
            produced.append(len(candidates) - 1)
        # Exactly one, or none. See `candidate_for_segment`.
        if len(produced) == 1:
            candidate_by_segment[segment.index] = produced[0]

    review: list[ReviewRequired] = []
    by_path: dict[str, list[int]] = {}
    for position, candidate in enumerate(candidates):
        by_path.setdefault(candidate.field_path, []).append(position)
    for field_path, positions in by_path.items():
        values = {repr(candidates[position].proposed_value) for position in positions}
        if len(values) > 1:
            review.append(
                ReviewRequired(
                    kind="conflicting_values_for_one_field",
                    field_path=field_path,
                    reason=(
                        "This transcript proposes more than one value for this "
                        "field. Both proposals are listed and neither is preferred "
                        "— choosing the later one would be a guess, and dropping "
                        "them would lose something that was said twice. Accept at "
                        "most one."
                    ),
                    candidate_indexes=tuple(positions),
                )
            )

    return TranscriptReading(
        segments=segments,
        candidates=tuple(candidates),
        clarifications=tuple(clarifications),
        abstentions=tuple(abstentions),
        review_required=tuple(sorted(review, key=lambda entry: entry.field_path)),
        candidate_by_segment=MappingProxyType(dict(candidate_by_segment)),
        run_target=selected_run if candidates else None,
    )
