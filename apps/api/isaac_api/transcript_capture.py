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
  the scientist said twice.
* :class:`Abstention` — the reading recognises the subject and declines to
  propose anything, because a proposal would require a conversion or a schema
  decision nobody made. Nothing is asked, because there is no alternative to
  offer.
* an **unmapped note** — the default, and by far the commonest. Text nothing
  matched is stored verbatim; see (4).

**(4) Scientist-entered text is never silently discarded.** EVERY segment of a
finalized transcript becomes an Unmapped Note, including the segments that DID
produce a candidate. That is the deliberate, slightly redundant choice: a
candidate is not stored anywhere, so if notes were captured only for the unmatched
segments, then rejecting a candidate — or failing to accept one — would destroy the
words it came from. Capturing every segment makes text survival independent of
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
    "read_transcript",
    "segment_transcript",
]

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
            "Two statements propose different values for the same field. Both "
            "candidates are returned and grouped, so the scientist resolves the "
            "contradiction. Choosing the later one would be a guess dressed as a "
            "convention, and dropping both would lose something that was said "
            "twice."
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
    """One entry of the closed table: a pattern, a path, and how to read a value."""

    name: str
    pattern: re.Pattern[str]
    field_path: str
    numeric: bool
    sentence: str


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
        other_unit = _TEMPERATURE_OTHER.search(segment.text)
        if other_unit is not None and not _TEMPERATURE_K.search(segment.text):
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
        produced: list[int] = []
        for rule in _RULES:
            match = rule.pattern.search(segment.text)
            if match is None:
                continue
            raw = match.group(1).strip()
            if not raw:
                continue
            value = _read_number(raw) if rule.numeric else raw
            candidates.append(
                FieldCandidate(
                    field_path=rule.field_path,
                    proposed_value=value,
                    quote=segment.text,
                    start_char=segment.start_char,
                    end_char=segment.end_char,
                    origin=ORIGIN_TRANSCRIPT,
                    produced_by=PRODUCED_BY,
                    rule=(
                        f"in the sentence {segment.text.strip()!r}, {rule.sentence}; "
                        f"the value is quoted from the transcript, not interpreted"
                    ),
                    provenance=MappingProxyType(
                        {
                            "reader_rule": rule.name,
                            "run_id": selected_run,
                            "segment_index": segment.index,
                            "matched_text": match.group(0),
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
