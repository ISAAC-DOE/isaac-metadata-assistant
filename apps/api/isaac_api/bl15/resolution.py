"""The conflict evidence model: SOURCE FACT, NORMALISED READING, SUGGESTED RESOLUTION, and
SCIENTIST-CONFIRMED RESOLUTION — four layers, and only the last is authoritative.

WHY THERE IS STILL NO SOURCE HIERARCHY
======================================

Domain question ``Q15`` asked which source wins when three disagree. On **2026-09-22 the
domain owner (Angel) asked ISAAC to brainstorm it rather than answer it, relayed by the
project owner**, and the policy adopted is this module:

* **No universal hard-coded source precedence.** The sources mean different things
  (:data:`ROLE_MEANINGS`): a macro is PLANNED acquisition, an instrument header is what
  the acquisition system RECORDED, a filename is a HUMAN LABEL that may have been
  corrected later or mistyped, and the final beamtime notes are a RETROSPECTIVE human
  interpretation or correction. None of those meanings makes one of them right.
* **Default: preserve every source, show the disagreement, choose nothing.** That is
  what :mod:`bl15.relate` already does and it is unchanged.
* **ISAAC MAY add a non-authoritative RECOMMENDATION** when independent evidence
  supports one reading — a repeated pattern, the final notes, the neighbouring Run
  sequence. It is labelled ``non_authoritative`` on the wire, it names every piece of
  evidence it rests on, and it changes nothing.
* **Only a scientist-confirmed resolution is authoritative** (:mod:`isaac_api.convention_rules`),
  and even then, for a record field, it goes forward as a PROPOSAL whose acceptance keeps
  its existing ``409 human_actor_required`` trust gate. Nothing here can bypass actor
  trust, because nothing here writes.

A MACRO AND A HEADER THAT AGREE ARE ONE WITNESS, NOT TWO
========================================================

SPEC's ``newfile <target>`` is what writes an acquisition's ``#F`` line, so when a macro
target and the header agree they are one causal chain — the plan, recorded — and counting
them as corroborating each other would double one fact. :func:`recommend` records that
explicitly rather than letting agreement between them read as support.

``DEC-46``: THE DUPLICATE LEGACY NUMBER GETS EVIDENCE, NEVER A RECOMMENDATION
============================================================================

Two distinct acquisitions carry legacy number ``32``. Angel (2026-09-22) does not recall
whether they are two conditions or a typo, so ``Q16`` is recorded as *domain owner does
not know* and the conflict is PERMANENTLY PRESERVED. The final notes' support for one
reading is shown — as evidence, not truth — and the recommendation status is
:data:`RECOMMENDATION_FORBIDDEN`, so no surface can present either acquisition as
preferred.

Pure functions over facts already read. No I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from . import evidence as ev
from .relate import (
    CONFLICT_ACQUIRED_NEVER_DECLARED,
    CONFLICT_DECLARATION_VS_FILENAME,
    CONFLICT_DECLARED_NEVER_ACQUIRED,
    CONFLICT_DUPLICATE_LEGACY_NUMBER,
    Conflict,
    MeasurementUnit,
    Reading,
)

__all__ = [
    "LAYERS",
    "RECOMMENDATION_FORBIDDEN",
    "RECOMMENDATION_NONE",
    "RECOMMENDATION_SUGGESTED",
    "ROLE_MEANINGS",
    "Recommendation",
    "Support",
    "annotate_conflict",
    "conflict_id",
    "recommend",
    "role_of",
]

# --- the four layers ------------------------------------------------------------

LAYER_SOURCE_FACT = "source_fact"
LAYER_NORMALIZED_READING = "normalized_reading"
LAYER_SUGGESTED_RESOLUTION = "suggested_resolution"
LAYER_CONFIRMED_RESOLUTION = "scientist_confirmed_resolution"

#: In order, with the one sentence that says what each is and whether it is authoritative.
LAYERS: tuple[tuple[str, str], ...] = (
    (LAYER_SOURCE_FACT, "What one source literally says, at a locator. Never rewritten."),
    (
        LAYER_NORMALIZED_READING,
        "The same statement after a stored, named rule — the literal kept beside it.",
    ),
    (
        LAYER_SUGGESTED_RESOLUTION,
        "ISAAC's non-authoritative recommendation, with every piece of evidence it "
        "rests on. Changes nothing.",
    ),
    (
        LAYER_CONFIRMED_RESOLUTION,
        "A scientist's confirmed resolution — the only authoritative layer. For a "
        "record field it goes forward as a proposal, and acceptance keeps its "
        "trusted-actor gate.",
    ),
)

# --- what each kind of source means ------------------------------------------------

ROLE_PLANNED_ACQUISITION = "planned_acquisition"
ROLE_INSTRUMENT_HEADER = "instrument_header"
ROLE_HUMAN_LABEL = "human_label"
ROLE_RETROSPECTIVE_NOTE = "retrospective_note"
ROLE_ABSENCE = "absence_of_a_source"
ROLE_OTHER = "other_source"

#: Angel's framing, 2026-09-22, as the sentence a scientist reads beside each reading.
#: Each role's meaning, in plain words — served to a scientist beside every reading.
#: (2026-09-23: the first wording shouted — "HUMAN LABEL", "RETROSPECTIVE" — and quoted
#: raw header syntax like `#F`; an independent review asked for plain words.)
ROLE_MEANINGS: Mapping[str, str] = {
    ROLE_PLANNED_ACQUISITION: (
        "A macro: the acquisition that was planned, written before it ran."
    ),
    ROLE_INSTRUMENT_HEADER: (
        "An instrument header: what the acquisition system recorded at the time. "
        "At BL15-2 the file-name line of the header is written from the macro's "
        "new-file target, so it records the plan, not an independent observation of "
        "the sample."
    ),
    ROLE_HUMAN_LABEL: (
        "A filename: a label a person gave it — possibly corrected after acquisition, "
        "possibly mistyped."
    ),
    ROLE_RETROSPECTIVE_NOTE: (
        "The final beamtime notes: a person's later interpretation or correction."
    ),
    ROLE_ABSENCE: "Not a statement — the absence of one (no source says this).",
    ROLE_OTHER: "Another source; its meaning is not characterised here.",
}


def role_of(reading: Reading) -> str:
    """The role of ONE reading, from its source type and locator. Deterministic."""
    if reading.source_path.startswith("("):
        return ROLE_ABSENCE
    if reading.source_type in {
        ev.SOURCE_TYPE_MACRO,
        ev.SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
        ev.SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO,
    }:
        return ROLE_PLANNED_ACQUISITION
    if reading.source_type == ev.SOURCE_TYPE_BEAMTIME_NOTES:
        return ROLE_RETROSPECTIVE_NOTE
    if reading.locator == "filename":
        return ROLE_HUMAN_LABEL
    if reading.locator.startswith("#"):
        return ROLE_INSTRUMENT_HEADER
    return ROLE_OTHER


def conflict_id(conflict: Conflict) -> str:
    """A STABLE handle for one conflict: its kind and subject. The same on every parse."""
    return f"{conflict.kind}:{conflict.subject}"


# --- recommendations --------------------------------------------------------------

RECOMMENDATION_SUGGESTED = "suggested"
RECOMMENDATION_NONE = "none"
RECOMMENDATION_FORBIDDEN = "forbidden"

SUPPORT_REPEATED_PATTERN = "repeated_pattern"
SUPPORT_FINAL_NOTES = "final_notes"
SUPPORT_NEIGHBOUR_SEQUENCE = "neighbour_sequence"
SUPPORT_ONE_CAUSAL_CHAIN = "macro_and_header_are_one_causal_chain"

#: A pattern must repeat to count as one: at least this many acquisitions (this one
#: included) in one sample group making the identical substitution. Measured basis: the
#: real archive's systematic rename is FOUR consecutive files; a pair could be two
#: typos, three in a contiguous run cannot sensibly be.
MIN_PATTERN_MEMBERS = 3


@dataclass(frozen=True)
class Support:
    """One piece of independent evidence bearing on which reading is right."""

    value: str | None
    kind: str
    sentence: str
    source_path: str = ""
    locator: str = ""
    #: False for a note that explains why something does NOT count as support.
    counts: bool = True

    def to_state(self) -> dict:
        return {
            "value": self.value,
            "kind": self.kind,
            "sentence": self.sentence,
            "source_path": self.source_path,
            "locator": self.locator,
            "counts": self.counts,
        }


@dataclass(frozen=True)
class Recommendation:
    """ISAAC's suggestion for one conflict, or why it has none. NEVER authoritative."""

    status: str
    value: str | None
    why: str
    supports: tuple[Support, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {
            RECOMMENDATION_SUGGESTED,
            RECOMMENDATION_NONE,
            RECOMMENDATION_FORBIDDEN,
        }:
            raise ValueError(f"unknown recommendation status {self.status!r}")
        if self.status != RECOMMENDATION_SUGGESTED and self.value is not None:
            raise ValueError("only a suggested recommendation may carry a value")

    def to_state(self) -> dict:
        return {
            "status": self.status,
            "value": self.value,
            "why": self.why,
            "supports": [s.to_state() for s in self.supports],
            "authority": "non_authoritative",
            "layer": LAYER_SUGGESTED_RESOLUTION,
        }


def _tokens(stem: str) -> list[str]:
    return (stem or "").rsplit("/", 1)[-1].split("_")


def _substitution(filename: str, declared: str) -> tuple[tuple[str, str], ...] | None:
    """The positional token substitutions from ``declared`` to ``filename``.

    ``None`` when the two stems do not have the same token count — a substitution is only
    well defined position by position, and guessing an alignment would be the guess.
    """
    a, b = _tokens(declared), _tokens(filename)
    if len(a) != len(b):
        return None
    pairs = tuple((x, y) for x, y in zip(a, b) if x != y)
    return pairs or None


_NUMBER = re.compile(r"\d+")


def _numbers_in(token: str) -> set[str]:
    return set(_NUMBER.findall(token))


def recommend(
    conflict: Conflict,
    *,
    unit: MeasurementUnit | None,
    units: Sequence[MeasurementUnit],
    note_texts_by_number: Mapping[int, Sequence[Mapping]] | None = None,
) -> Recommendation:
    """A recommendation for ONE conflict, or the reason there is none. Deterministic.

    Only the declaration-versus-filename kind can earn a suggestion, because it is the
    only kind whose readings are ALTERNATIVE VALUES for one thing. The duplicate legacy
    number is ``DEC-46``'s and is forbidden; "declared, never acquired" and "acquired,
    never declared" are statements about an absence and have nothing to choose between.
    """
    note_texts_by_number = note_texts_by_number or {}
    if conflict.kind == CONFLICT_DUPLICATE_LEGACY_NUMBER:
        return _duplicate_number_evidence(conflict, units, note_texts_by_number)
    if conflict.kind in {CONFLICT_DECLARED_NEVER_ACQUIRED, CONFLICT_ACQUIRED_NEVER_DECLARED}:
        return Recommendation(
            status=RECOMMENDATION_NONE,
            value=None,
            why=(
                "One side of this conflict is an ABSENCE — no macro declared it, or no "
                "file was acquired under that name — so there are not two values to "
                "choose between."
            ),
        )
    if conflict.kind != CONFLICT_DECLARATION_VS_FILENAME or unit is None:
        return Recommendation(
            status=RECOMMENDATION_NONE,
            value=None,
            why="No recommendation rule exists for this kind of disagreement.",
        )

    filename = next((r for r in conflict.readings if role_of(r) == ROLE_HUMAN_LABEL), None)
    header = next((r for r in conflict.readings if role_of(r) == ROLE_INSTRUMENT_HEADER), None)
    if filename is None or header is None:
        return Recommendation(
            status=RECOMMENDATION_NONE,
            value=None,
            why="The readings do not include both a filename and a header.",
        )
    supports: list[Support] = []
    macros = [r for r in conflict.readings if role_of(r) == ROLE_PLANNED_ACQUISITION]
    for macro in macros:
        if _tokens(macro.value) == _tokens(header.value):
            supports.append(
                Support(
                    value=header.value,
                    kind=SUPPORT_ONE_CAUSAL_CHAIN,
                    sentence=(
                        "The macro target and the header agree, and at BL15-2 the "
                        "header is written from the macro's `newfile` target — one "
                        "causal chain, counted once, not two witnesses."
                    ),
                    source_path=macro.source_path,
                    locator=macro.locator,
                    counts=False,
                )
            )
    substitution = _substitution(filename.value, header.value)

    # 1. A REPEATED PATTERN in the same sample group.
    if substitution is not None:
        sharing = []
        for other in units:
            if other.group_token != unit.group_token:
                continue
            for c in other.conflicts:
                if c.kind != CONFLICT_DECLARATION_VS_FILENAME:
                    continue
                f = next((r for r in c.readings if role_of(r) == ROLE_HUMAN_LABEL), None)
                h = next((r for r in c.readings if role_of(r) == ROLE_INSTRUMENT_HEADER), None)
                if f and h and _substitution(f.value, h.value) == substitution:
                    sharing.append(other)
        numbers = sorted(u.legacy_number for u in sharing if u.legacy_number is not None)
        contiguous = bool(numbers) and numbers == list(range(numbers[0], numbers[-1] + 1))
        if len(sharing) >= MIN_PATTERN_MEMBERS and contiguous:
            pretty = ", ".join(f"{a} -> {b}" for a, b in substitution)
            supports.append(
                Support(
                    value=filename.value,
                    kind=SUPPORT_REPEATED_PATTERN,
                    sentence=(
                        f"{len(sharing)} consecutive acquisitions in sample group "
                        f"{unit.group_token} (legacy {numbers[0]}-{numbers[-1]}) make the "
                        f"identical substitution ({pretty}) between header and filename. "
                        "A systematic rename after acquisition is likelier a deliberate "
                        "correction than a repeated typo."
                    ),
                )
            )

    # 2. THE FINAL NOTES, for this legacy number.
    if substitution is not None and unit.legacy_number is not None:
        for row in note_texts_by_number.get(unit.legacy_number, ()):
            text = str(row.get("text") or "")
            found_filename = set().union(*(_numbers_in(b) for _, b in substitution)) if substitution else set()
            found_header = set().union(*(_numbers_in(a) for a, _ in substitution)) if substitution else set()
            present = {n for n in _NUMBER.findall(text)}
            only_f = (found_filename - found_header) & present
            only_h = (found_header - found_filename) & present
            if only_f and not only_h:
                supports.append(
                    Support(
                        value=filename.value,
                        kind=SUPPORT_FINAL_NOTES,
                        sentence=(
                            "The final beamtime notes' row for this file number states "
                            "the figure the filename carries and not the header's — "
                            "evidence, not truth: the notes are a retrospective reading."
                        ),
                        source_path=str(row.get("source_path") or ""),
                        locator=str(row.get("locator") or ""),
                    )
                )
            elif only_h and not only_f:
                supports.append(
                    Support(
                        value=header.value,
                        kind=SUPPORT_FINAL_NOTES,
                        sentence=(
                            "The final beamtime notes' row for this file number states "
                            "the figure the header carries and not the filename's — "
                            "evidence, not truth."
                        ),
                        source_path=str(row.get("source_path") or ""),
                        locator=str(row.get("locator") or ""),
                    )
                )

    # 3. THE NEIGHBOURING RUN SEQUENCE.
    if substitution is not None and unit.legacy_number is not None and len(substitution) == 1:
        (old, new), = substitution
        neighbours = [
            u
            for u in units
            if u.group_token == unit.group_token
            and u.legacy_number in {unit.legacy_number - 1, unit.legacy_number + 1}
            and u.stem != unit.stem
            and not any(c.kind == CONFLICT_DECLARATION_VS_FILENAME for c in u.conflicts)
        ]
        carry_new = [u for u in neighbours if new in _tokens(u.stem)]
        carry_old = [u for u in neighbours if old in _tokens(u.stem)]
        if carry_new and not carry_old:
            supports.append(
                Support(
                    value=filename.value,
                    kind=SUPPORT_NEIGHBOUR_SEQUENCE,
                    sentence=(
                        f"Neighbouring acquisition(s) whose name and header agree "
                        f"({', '.join(u.stem for u in carry_new)}) carry `{new}`, the "
                        "filename's token."
                    ),
                )
            )
        elif carry_old and not carry_new:
            supports.append(
                Support(
                    value=header.value,
                    kind=SUPPORT_NEIGHBOUR_SEQUENCE,
                    sentence=(
                        f"Neighbouring acquisition(s) whose name and header agree "
                        f"({', '.join(u.stem for u in carry_old)}) carry `{old}`, the "
                        "header's token."
                    ),
                )
            )

    counting = [s for s in supports if s.counts]
    values = sorted({s.value for s in counting if s.value is not None})
    if not counting:
        return Recommendation(
            status=RECOMMENDATION_NONE,
            value=None,
            why=(
                "No independent evidence beyond the readings themselves points either "
                "way, so ISAAC suggests nothing."
            ),
            supports=tuple(supports),
        )
    if len(values) > 1:
        return Recommendation(
            status=RECOMMENDATION_NONE,
            value=None,
            why=(
                "The independent evidence points both ways, so ISAAC suggests nothing. "
                "Every piece of it is listed."
            ),
            supports=tuple(supports),
        )
    return Recommendation(
        status=RECOMMENDATION_SUGGESTED,
        value=values[0],
        why=(
            f"{len(counting)} piece(s) of independent evidence point to the same reading "
            "and none points the other way. This is a SUGGESTION: a scientist confirms "
            "or rejects it, and nothing is changed until then."
        ),
        supports=tuple(supports),
    )


def _duplicate_number_evidence(
    conflict: Conflict,
    units: Sequence[MeasurementUnit],
    note_texts_by_number: Mapping[int, Sequence[Mapping]],
) -> Recommendation:
    """``DEC-46`` / ``Q16``: show the evidence, forbid the recommendation."""
    supports: list[Support] = []
    try:
        number = int(conflict.subject)
    except ValueError:
        number = None
    stems = [r.value for r in conflict.readings]
    if number is not None:
        for row in note_texts_by_number.get(number, ()):
            text = str(row.get("text") or "")
            present = set(_NUMBER.findall(text))
            for stem in stems:
                others = set().union(*(_numbers_in(t) for s in stems if s != stem for t in _tokens(s)))
                own = set().union(*(_numbers_in(t) for t in _tokens(stem)))
                distinctive = (own - others) & present
                if distinctive:
                    supports.append(
                        Support(
                            value=stem,
                            kind=SUPPORT_FINAL_NOTES,
                            sentence=(
                                "The final beamtime notes' row for this file number "
                                "states a figure only this acquisition's name carries. "
                                "SHOWN AS EVIDENCE, NOT TRUTH (DEC-46): matching a log "
                                "narrows the question without answering it."
                            ),
                            source_path=str(row.get("source_path") or ""),
                            locator=str(row.get("locator") or ""),
                            counts=False,
                        )
                    )
    return Recommendation(
        status=RECOMMENDATION_FORBIDDEN,
        value=None,
        why=(
            "Two distinct acquisitions carry this legacy number. The domain owner does "
            "not recall whether they are two conditions or a typo (2026-09-22), so both "
            "are preserved with distinct identities and neither is recommended — DEC-46."
        ),
        supports=tuple(supports),
    )


def annotate_conflict(
    conflict: Conflict,
    recommendation: Recommendation | None,
    resolution: Mapping | None = None,
) -> dict:
    """``Conflict.to_state()`` plus the three layers above the source facts.

    Additive: every key ``Conflict.to_state()`` carries is carried unchanged, so a
    consumer written against the old shape keeps working.
    """
    state = conflict.to_state()
    state["conflict_id"] = conflict_id(conflict)
    for reading_state, reading in zip(state["readings"], conflict.readings):
        role = role_of(reading)
        reading_state["source_role"] = role
        reading_state["source_role_meaning"] = ROLE_MEANINGS[role]
        reading_state["layer"] = LAYER_SOURCE_FACT
    state["recommendation"] = recommendation.to_state() if recommendation else None
    state["resolution"] = dict(resolution) if resolution else None
    if resolution:
        state["review_status"] = "resolved"
    elif recommendation and recommendation.status == RECOMMENDATION_SUGGESTED:
        state["review_status"] = "needs_review"
    else:
        state["review_status"] = "sources_conflict"
    return state
