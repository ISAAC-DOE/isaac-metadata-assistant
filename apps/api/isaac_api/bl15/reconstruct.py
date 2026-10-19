"""Turn read evidence and reconstructed structure into CANDIDATES a scientist reviews.

**This is the only module in the package that interprets anything, and it is the only
one that may.** Everything below it reads: a reader says what a file literally says, and
:mod:`bl15.relate` says what belongs to what. Here those are combined into a claim —
*"the sources support this value at this official field path"* — and a claim is exactly
what needs a warrant, a provenance trail and a human reviewer.

**WHAT THIS MODULE MAY NOT DO**, each forbidden for a reason measured in this corpus:

* **Choose between disagreeing sources.** The corpus contains a systematic rename — four
  consecutive files whose internal header and filename disagree — so the plausible rule
  *"prefer the header, it is closer to the instrument"* is wrong for exactly the cases it
  would be reached for. A disagreement becomes a candidate with **no value** and every
  reading attached.
* **Invent a value, a unit, a reference basis, or a mapping.** A concept with no schema
  path becomes a candidate carrying the registry's own reason — **39 of 45 concepts land
  there**, so dropping them would discard most of the corpus rather than tidying it.
* **Write anything.** The output is `SemanticCandidate`, which the existing import
  pipeline turns into a *note plus an open proposal*. Acceptance answers
  ``409 human_actor_required`` in every default-configured deployment, so the chain stops
  at a proposal by design.

The mapping is never decided here either: every field candidate's path comes from
:func:`bl15.mapping.mapping_for`, whose own guard checks each path against the vendored
schema at runtime. A path literal in this file would be a second, unchecked opinion.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from dataclasses import replace

from ..historical_import import (
    CANDIDATE_KIND_FIELD,
    CANDIDATE_KIND_RUN,
    CANDIDATE_NOT_PROPOSABLE_LOCAL_TIME,
    DETERMINISM_DETERMINISTIC,
    DETERMINISM_INFERRED,
    UNRESOLVED_SOURCES_DISAGREE,
    EvidenceStatement,
    SemanticCandidate,
    is_zoned_utc_value,
    plain_reason_of,
)
from . import conditions as cond
from . import evidence as ev
from . import mapping as mp
from . import resolution as res
from .relate import (
    CONFLICT_DECLARATION_VS_FILENAME,
    Conflict,
    MeasurementUnit,
    Relationships,
)

#: Why a structural candidate cannot become a proposal. The existing pipeline already
#: refuses one and says why; this is the same sentence for a run.
#:
#: Kept verbatim in spirit with the experiment-creation refusal rather than reworded,
#: because the underlying reason is identical: a proposal is about ONE value at ONE
#: official field path, and "a measurement exists here" has no such shape.
RUN_CANDIDATE_NOT_PROPOSABLE = (
    "A proposal is about one value at one official field path. "
    "'This import contains a measurement' is not a value, so there is nothing to "
    "propose — it is shown so you can see what the import found, and you decide "
    "whether it becomes a Run."
)

#: Why a candidate whose readings VARY by scan has no single value to propose. None of
#: the concepts the cardinality rule currently declares has a proposable mapping, so
#: this is a guard rather than a sentence anyone reads today — and a record field takes
#: ONE value, so a per-scan list must never be proposed as though it were one.
VARIES_NOT_PROPOSABLE = (
    "This value differs from scan to scan, as it is expected to, so there is no single "
    "value to propose. Each scan's reading is kept."
)

#: Why a candidate carrying a disagreement has no value.
DISAGREEMENT_NOT_PROPOSABLE = (
    "Two or more sources disagree about this. Nothing here picks a winner, so there is "
    "no single value to propose until you decide which reading is right."
)


def statement_for(item: ev.SourceEvidence) -> EvidenceStatement:
    """Bridge ONE piece of read evidence into the existing pipeline's 3-field shape.

    **``value`` IS THE RAW LITERAL, NEVER THE NORMALISED ONE**, and that is the whole
    reason this is a named function rather than a dict comprehension at a call site.
    Handing the normalised value across would put ``filter 35`` into the review pipeline
    where the file says ``ffilter35``, and the normalisation would become invisible at
    precisely the moment a scientist is reviewing it. The normalised value and the rule
    that produced it travel on the CANDIDATE, where ``SemanticCandidate.rule`` exists for
    them.

    The locator is prefixed with the archive path because that is the scientist's own
    handle on a source; a bare ``#F`` or ``filename token 4`` means nothing on a screen
    listing evidence from several files.
    """
    return EvidenceStatement(
        key=item.concept,
        value=item.raw_literal,
        locator=statement_locator(item),
    )


@dataclass(frozen=True)
class UnitCandidates:
    """Every candidate one measurement produced, and why each is or is not proposable."""

    stem: str
    candidates: tuple[SemanticCandidate, ...]

    @property
    def proposable(self) -> tuple[SemanticCandidate, ...]:
        return tuple(c for c in self.candidates if c.proposable)

    def to_state(self) -> dict:
        return {
            "stem": self.stem,
            "candidates": [_candidate_state(c) for c in self.candidates],
            "proposable_count": len(self.proposable),
            "candidate_count": len(self.candidates),
        }


@dataclass(frozen=True)
class ReconstructionReport:
    """What the reconstruction produced, at a scale a scientist can read.

    **The counts are the point.** Over the real corpus this produces roughly a thousand
    candidates across 94 measurements, and a surface that rendered them flat would be
    `HIST-004`'s banned pattern. The per-status breakdown is what makes it legible — and
    it is deliberately NOT a ratio: 39 of 45 concepts have no proposable mapping, so a
    "percentage mapped" would report the schema's coverage as this feature's failure.
    """

    units: tuple[UnitCandidates, ...] = ()
    #: Candidates that belong to the import rather than to one measurement — the
    #: beamtime-scope README statements every unit inherits.
    shared: tuple[SemanticCandidate, ...] = ()
    #: ``concept -> count`` — over every FIELD candidate, which is not every candidate.
    #:
    #: ~~over every candidate produced~~ — corrected 2026-09-16 after independent review
    #: measured the arithmetic: `by_concept` and `by_mapping_status` each sum to **89**
    #: against **97** candidates, because they count one per concept GROUP and the
    #: structural `run`-kind candidates (`::unit`, `::conflict::N`) have no concept at
    #: all. 8 + 89 = 97, verified. A surface rendering this breakdown beside a candidate
    #: total will show fewer, and that is correct rather than a gap — but it must say so
    #: rather than leaving a reader to find the difference.
    by_concept: Mapping[str, int] = None  # type: ignore[assignment]
    #: ``mapping status -> count``. Read this instead of a completion percentage.
    #: Same scope as :attr:`by_concept` — field candidates only, so it sums to fewer
    #: than the candidate total by exactly the number of structural candidates.
    by_mapping_status: Mapping[str, int] = None  # type: ignore[assignment]
    #: Concepts read from the sources for which the registry has NO entry. Should be
    #: empty; non-empty means a reader emitted a concept nobody examined, which is a
    #: finding rather than a failure.
    unregistered_concepts: tuple[str, ...] = ()

    def to_state(self) -> dict:
        return {
            "units": [u.to_state() for u in self.units],
            "shared": [_candidate_state(c) for c in self.shared],
            "by_concept": dict(self.by_concept or {}),
            "by_mapping_status": dict(self.by_mapping_status or {}),
            "unregistered_concepts": list(self.unregistered_concepts),
            "candidate_count": sum(len(u.candidates) for u in self.units)
            + len(self.shared),
            "proposable_count": sum(len(u.proposable) for u in self.units)
            + sum(1 for c in self.shared if c.proposable),
        }


def reconstruct(
    *,
    relationships: Relationships,
    evidence_by_source: Mapping[str, Sequence[ev.SourceEvidence]],
    source_ids: Mapping[str, str] | None = None,
) -> ReconstructionReport:
    """Assemble candidates for every measurement, plus the import's shared context.

    :param relationships: the output of :func:`bl15.relate.relate`.
    :param evidence_by_source: ``archive_path -> everything a reader read from it``.
    :param source_ids: ``archive_path -> the import session's own source id``. Optional:
        when the whole archive is ONE manifest entry there is one id for everything, and
        a candidate's ``supporting_source_ids`` then names that entry. The archive path
        is carried in every statement's locator regardless, so provenance never depends
        on this map being supplied.
    """
    source_ids = dict(source_ids or {})
    by_concept: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    unregistered: set[str] = set()

    units: list[UnitCandidates] = []
    for unit in relationships.units:
        items = _evidence_for_unit(unit, evidence_by_source)
        candidates = list(
            _candidates_for_unit(
                unit,
                items,
                source_ids=source_ids,
                by_concept=by_concept,
                by_status=by_status,
                unregistered=unregistered,
            )
        )
        units.append(UnitCandidates(stem=unit.stem, candidates=tuple(candidates)))

    shared = tuple(
        _candidates_from_evidence(
            _shared_evidence(relationships, evidence_by_source),
            candidate_prefix="shared",
            source_ids=source_ids,
            by_concept=by_concept,
            by_status=by_status,
            unregistered=unregistered,
        )
    )

    return ReconstructionReport(
        units=tuple(units),
        shared=shared,
        by_concept=dict(sorted(by_concept.items())),
        by_mapping_status=dict(sorted(by_status.items())),
        unregistered_concepts=tuple(sorted(unregistered)),
    )


# --- per unit ----------------------------------------------------------------


def _evidence_for_unit(
    unit: MeasurementUnit,
    evidence_by_source: Mapping[str, Sequence[ev.SourceEvidence]],
) -> list[ev.SourceEvidence]:
    """Every reading that supports ONE measurement, from every source attached to it.

    **The acquisition, its scans, the macros that declared it and its processed products
    — and deliberately NOT its byte-identical copies.** Reading the same bytes twice
    would double every statement the acquisition makes, which is the statement-level form
    of the unit-level doubling that turned 94 measurements into 181.
    """
    paths: list[str] = [unit.acquisition_path]
    paths.extend(scan.path for scan in unit.scans)
    paths.extend(sorted({block.macro_path for block in unit.declared_by}))
    paths.extend(unit.processed_products)

    # A MACRO FILE DECLARES SEVERAL MEASUREMENTS, one `newfile` block each, so a
    # statement one of its blocks makes about ANOTHER measurement is that measurement's
    # evidence, not this one's. Added 2026-09-22 after measuring the consequence: every
    # unit declared by one nine-block macro received all nine declared targets, and the
    # reconstruction reported them as nine sources disagreeing about which measurement
    # this is. A statement naming no measurement (file-level) still applies.
    declared: dict[str, set[str]] = defaultdict(set)
    for block in unit.declared_by:
        declared[block.macro_path].add(block.declared_target)

    seen: set[str] = set()
    out: list[ev.SourceEvidence] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        targets = declared.get(path)
        for item in evidence_by_source.get(path, ()):
            if (
                targets is not None
                and item.measurement_stem is not None
                and item.measurement_stem not in targets
            ):
                continue
            out.append(item)
    return out


def _candidates_for_unit(
    unit: MeasurementUnit,
    items: Sequence[ev.SourceEvidence],
    *,
    source_ids: Mapping[str, str],
    by_concept: dict[str, int],
    by_status: dict[str, int],
    unregistered: set[str],
) -> Iterable[SemanticCandidate]:
    """The structural candidate, then one per concept, then one per conflict."""
    # 1. THE MEASUREMENT ITSELF. Shown, never sent — see RUN_CANDIDATE_NOT_PROPOSABLE.
    yield SemanticCandidate(
        candidate_id=f"{unit.stem}::unit",
        kind=CANDIDATE_KIND_RUN,
        determinism=DETERMINISM_DETERMINISTIC,
        rule=(
            "One acquisition file with its own scan directory is one measurement. "
            f"This one has {unit.scan_count} scan file(s) and "
            f"{unit.source_count} supporting source(s)."
        ),
        supporting_source_ids=_ids_for((unit.acquisition_path,), source_ids),
        supporting_statements=(
            {
                "key": "measurement",
                "value": unit.stem,
                "locator": f"{unit.acquisition_path} · filename",
            },
        ),
        not_proposable_reason=RUN_CANDIDATE_NOT_PROPOSABLE,
        distinct_sources=1,
    )

    yield from _candidates_from_evidence(
        items,
        candidate_prefix=unit.stem,
        source_ids=source_ids,
        by_concept=by_concept,
        by_status=by_status,
        unregistered=unregistered,
    )

    dry = dry_sample_environment(unit, items, source_ids)
    if dry is not None:
        yield dry

    for index, conflict in enumerate(unit.conflicts):
        yield _candidate_from_conflict(
            conflict, f"{unit.stem}::conflict::{index}", source_ids
        )


def _candidates_from_evidence(
    items: Sequence[ev.SourceEvidence],
    *,
    candidate_prefix: str,
    source_ids: Mapping[str, str],
    by_concept: dict[str, int],
    by_status: dict[str, int],
    unregistered: set[str],
) -> Iterable[SemanticCandidate]:
    """One candidate per concept, then concepts that target ONE FIELD reconciled.

    See :func:`_reconcile_same_field` — added 2026-09-23 because two concepts map to
    the one acquisition-start UTC field and were each proposed, as competing open
    proposals, without ever being compared — and :func:`_cross_check_local_clock`,
    added 2026-10-11 because the zone-less half of that pair was STILL never compared.
    """
    candidates = list(
        _candidates_by_concept(
            items,
            candidate_prefix=candidate_prefix,
            source_ids=source_ids,
            by_concept=by_concept,
            by_status=by_status,
            unregistered=unregistered,
        )
    )
    return _cross_check_local_clock(_reconcile_same_field(candidates), items, source_ids)


#: THE WIDEST GAP A REAL UTC OFFSET CAN EXPLAIN between a zone-less wall-clock reading
#: and the UTC instant it is the local spelling of (2026-10-11, QA finding ``C-09``).
#:
#: Civil time zones run from UTC−12:00 to UTC+14:00, so ``local − UTC`` lies in
#: [−12 h, +14 h]. The bound is **14 h EITHER WAY** — the wider of the two, applied
#: symmetrically — so it can only ever be generous to agreement: a gap inside it is NOT
#: claimed as agreement (no zone is named, so none is assumed), it is merely not
#: evidence of disagreement, and nothing changes. A gap outside it cannot be one instant
#: read in two zones, so it is a disagreement for a scientist.
LOCAL_CLOCK_MAX_OFFSET = timedelta(hours=14)

_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

#: A SPEC ``#D`` line: ``Fri Jan 01 00:00:00 2099``. The weekday is optional and is NOT
#: consulted — it is redundant with the date, and checking it would be a second,
#: unrequested consistency rule (the synthetic corpora's ``Fri Jan 01 2099`` is in fact a
#: Thursday).
_SPEC_DATE = re.compile(
    r"^(?:[A-Za-z]{3}\s+)?([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})\s+(\d{4})$"
)


def zone_less_wall_clock(literal: object) -> datetime | None:
    """The wall-clock time a ZONE-LESS date literal states, or ``None``.

    Read for COMPARISON ONLY — never proposed, never converted into a zone, never
    written anywhere. ``None`` for a literal that names its zone (that reading is
    comparable as an instant, and :func:`_reconcile_same_field` already compares it) and
    for one this build cannot read, which then decides nothing either way.
    """
    if not isinstance(literal, str):
        return None
    text = literal.strip()
    match = _SPEC_DATE.match(text)
    if match is not None:
        month = _MONTHS.get(match.group(1).lower())
        if month is None:
            return None
        try:
            return datetime(
                int(match.group(6)),
                month,
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
                int(match.group(5)),
            )
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is None else None


def _cross_check_local_clock(
    candidates: list[SemanticCandidate],
    items: Sequence[ev.SourceEvidence],
    source_ids: Mapping[str, str],
) -> list[SemanticCandidate]:
    """Compare a file's EPOCH with the zone-less DATE LINE its own header states.

    **THE DEFECT THIS CLOSES (``C-09``, 2026-10-11).** ``mapping.py`` has promised of the
    acquisition time since it was written: *"if they disagree, both are read and the
    disagreement is a conflict for a scientist"*. :func:`_reconcile_same_field` made that
    true only for readings that are both PROPOSABLE — and the ``#D`` line never is
    (:data:`CANDIDATE_NOT_PROPOSABLE_LOCAL_TIME`), so it was never compared at all. The
    synthetic mini corpus says ``#E 4102444800`` (2100-01-01T00:00Z) beside ``#D Fri Jan
    01 00:00:00 2099``, and its epoch was offered as "Ready to Send".

    **WHAT IS COMPARED, AND ONLY THAT.** The epoch (``#E``, normalised to UTC by a named
    rule) against each MEASUREMENT-scope ``acquisition_timestamp`` reading of the SAME
    SOURCE FILE — the header ``#D``, the other spelling of the same instant. A scan's
    ``#D`` is that scan's own start, legitimately hours or days later, and is not this
    comparison. A zone-less reading may differ from UTC only by a real offset
    (:data:`LOCAL_CLOCK_MAX_OFFSET`); beyond it, the epoch candidate becomes a conflict
    carrying both readings verbatim — the epoch as the UTC instant it states, the date
    line as written — and nothing is chosen. Within it NOTHING changes: the local time is
    not converted, reconciled or credited as agreement.
    """
    epochs = [
        item
        for item in items
        if item.concept == ev.CONCEPT_ACQUISITION_EPOCH and isinstance(item.normalized_value, str)
    ]
    if not epochs:
        return candidates
    walls: dict[str, list[tuple[ev.SourceEvidence, datetime]]] = defaultdict(list)
    for item in items:
        if item.concept == ev.CONCEPT_ACQUISITION_TIMESTAMP and item.scope == ev.SCOPE_MEASUREMENT:
            wall = zone_less_wall_clock(item.raw_literal)
            if wall is not None:
                walls[item.source_path].append((item, wall))
    clashing_epochs: list[ev.SourceEvidence] = []
    clashing_walls: list[ev.SourceEvidence] = []
    for epoch in epochs:
        try:
            instant = datetime.fromisoformat(epoch.normalized_value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if instant.tzinfo is None:
            continue
        utc_wall = instant.astimezone(timezone.utc).replace(tzinfo=None)
        for local, wall in walls.get(epoch.source_path, ()):
            if abs(wall - utc_wall) > LOCAL_CLOCK_MAX_OFFSET:
                if epoch not in clashing_epochs:
                    clashing_epochs.append(epoch)
                if local not in clashing_walls:
                    clashing_walls.append(local)
    if not clashing_epochs:
        return candidates

    entry = mp.mapping_for(ev.CONCEPT_ACQUISITION_EPOCH)
    path = entry.official_path if entry is not None else None
    if path is None:  # pragma: no cover - the registry maps the epoch
        return candidates
    instants = {_comparable(e.normalized_value, path) for e in clashing_epochs}
    out = list(candidates)
    # THE CANDIDATE OFFERING THAT INSTANT — the epoch's own, or the reading that offered
    # the same instant in its place (`SAME_FIELD_ALREADY_OFFERED`). One that is already
    # not proposable (a disagreement of its own, a no-run measurement) is left as it is:
    # it offers nothing, so there is nothing to withhold.
    for index, candidate in enumerate(out):
        if not (
            candidate.proposable
            and candidate.target_field_path == path
            and _comparable(candidate.proposed_value, path) in instants
        ):
            continue
        disputed = clashing_epochs + clashing_walls
        distinct = list(dict.fromkeys(_reading_of(i) for i in disputed))
        known = {
            (s.get("key"), s.get("locator"), s.get("value")) for s in candidate.supporting_statements
        }
        extra = tuple(
            s
            for s in (statement_for(i).to_state() for i in clashing_walls)
            if (s.get("key"), s.get("locator"), s.get("value")) not in known
        )
        out[index] = replace(
            candidate,
            proposed_value=None,
            unresolved_reason=UNRESOLVED_SOURCES_DISAGREE,
            rule=(
                "The file states its start twice and the two cannot be one instant: the "
                f"epoch line reads {clashing_epochs[0].normalized_value} (UTC), and the "
                "date line, which names no time zone, reads "
                f"{clashing_walls[0].raw_literal}. They are "
                f"{_gap_words(clashing_epochs[0], clashing_walls[0])} apart — more than "
                "14 hours, the largest real time-zone offset." + _TIMESTAMP
            ),
            supporting_source_ids=tuple(
                sorted(
                    set(candidate.supporting_source_ids)
                    | set(_ids_for(tuple(i.source_path for i in clashing_walls), source_ids))
                )
            ),
            supporting_statements=tuple(candidate.supporting_statements) + extra,
            # THE ROW CONTRACT `_candidates_by_concept` USES for a disagreement —
            # `{value, source_ids, locators}` — so the review surface, the Conflicts
            # stage and a confirmed resolution (`historical_import._apply_resolution`,
            # which matches `value` against `reading_of`) all read it unchanged.
            disagreement=tuple(
                {
                    "value": value,
                    "source_ids": _sources_stating(disputed, value),
                    "locators": _locators_stating(disputed, value),
                }
                for value in distinct
            ),
        )
        break
    return out


def _gap_words(epoch: ev.SourceEvidence, local: ev.SourceEvidence) -> str:
    """How far apart the two readings are — EXACTLY, in words a scientist reads at a glance.

    ~~``f"{hours:.1f} hours"``~~ — just over the bound that read "14.0 hours apart … no
    real time-zone offset exceeds 14 hours", a sentence contradicting itself (independent
    review, 2026-10-11). Written to the second, and only as precisely as the gap needs:
    ``365 days``, ``1 day, 2 h 5 min``, ``14 h 0 min 1 s``. Every unit between the largest
    and the smallest non-zero one is written, so nothing is rounded and no figure can read
    as the bound it exceeds; a fractional second is written, never truncated.
    """
    instant = datetime.fromisoformat(str(epoch.normalized_value).replace("Z", "+00:00"))
    wall = zone_less_wall_clock(local.raw_literal)
    if wall is None:  # pragma: no cover - only called for a reading that parsed
        return "more than 14 hours"
    gap = abs(wall - instant.astimezone(timezone.utc).replace(tzinfo=None))
    hours, rest = divmod(gap.seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    second_text = (
        f"{seconds}.{gap.microseconds:06d}".rstrip("0") if gap.microseconds else str(seconds)
    )
    units = [(hours, f"{hours} h"), (minutes, f"{minutes} min"), (seconds or gap.microseconds, f"{second_text} s")]
    present = [index for index, (amount, _text) in enumerate(units) if amount]
    clock = (
        " ".join(text for _amount, text in units[present[0] : present[-1] + 1]) if present else ""
    )
    days = f"{gap.days} day{'s' if gap.days != 1 else ''}" if gap.days else ""
    return ", ".join(part for part in (days, clock) if part)


#: Why the second of two readings of ONE field that agree is not sent as well.
SAME_FIELD_ALREADY_OFFERED = (
    "Another reading for the same field ({other}) states the same value and is the one "
    "offered, so one proposal carries it. This reading stays as a second witness."
)

#: Why a reading that DISAGREES with another reading of the same field is not sent.
SAME_FIELD_IN_CONFLICT = (
    "Another reading for the same field ({other}) states a different value. The "
    "disagreement is shown on that reading; nothing is sent until you decide."
)


def _reconcile_same_field(candidates: list[SemanticCandidate]) -> list[SemanticCandidate]:
    """Compare every proposable candidate that targets the SAME official field.

    ``mapping.py`` has always said of the acquisition time: *"if they disagree … the
    disagreement is a conflict."* Nothing compared them — each concept became its own
    candidate — so a measurement could send two open proposals for one field. Now:
    readings that AGREE (for a ``*_utc`` field, the same instant) become ONE proposable
    candidate and the rest stay as witnesses; readings that DISAGREE become one conflict,
    carried on the first, with every reading attached. Nothing is chosen.
    """
    by_path: dict[str, list[int]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        if candidate.proposable and candidate.target_field_path:
            by_path[candidate.target_field_path].append(index)
    out = list(candidates)
    for path, indexes in by_path.items():
        if len(indexes) < 2:
            continue
        members = [out[i] for i in indexes]
        first, rest = members[0], members[1:]
        label = _concept_of(first)
        if len({_comparable(c.proposed_value, path) for c in members}) == 1:
            for i in indexes[1:]:
                out[i] = replace(
                    out[i], not_proposable_reason=SAME_FIELD_ALREADY_OFFERED.format(other=label)
                )
            continue
        out[indexes[0]] = replace(
            first,
            proposed_value=None,
            unresolved_reason=UNRESOLVED_SOURCES_DISAGREE,
            rule=(
                f"{len(members)} readings target {path} — "
                f"{', '.join(_concept_of(c) for c in members)} — and they do not agree."
                + (_TIMESTAMP if path.startswith("timestamps.") else " Nothing here picks one.")
            ),
            supporting_source_ids=tuple(
                sorted({sid for c in members for sid in c.supporting_source_ids})
            ),
            supporting_statements=tuple(s for c in members for s in c.supporting_statements),
            disagreement=tuple(
                {
                    "value": str(c.proposed_value),
                    "source_ids": list(c.supporting_source_ids),
                    "locators": [str(s.get("locator", "")) for s in c.supporting_statements],
                }
                for c in members
            ),
        )
        for i in indexes[1:]:
            out[i] = replace(out[i], not_proposable_reason=SAME_FIELD_IN_CONFLICT.format(other=label))
    return out


def _concept_of(candidate: SemanticCandidate) -> str:
    return candidate.candidate_id.rsplit("::", 1)[-1].replace("_", " ")


def _comparable(value, path: str) -> str:
    """A value as it is compared for one field: a ``*_utc`` instant as its UTC moment."""
    if path.endswith("_utc") and isinstance(value, str):
        from datetime import datetime, timezone

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).isoformat()
    return str(value)


#: WHAT A DIFFERENCE WITHIN ONE MEASUREMENT MEANS, per concept, in the domain owner's
#: terms (2026-10-12). Appended to a disagreement's warrant. Each says what is true now
#: and asks nothing: these were "pending the domain owner" until that day (Q21, and the
#: timestamp question), and they are confirmed.
_ACQUISITION_SETTING = (
    " Acquisition settings are kept the same for every scan of a measurement so that "
    "measurements can be compared; a deliberate change belongs in the logbook or run "
    "files. So two values within one measurement are a discrepancy for you to review. "
    "Different measurements may use different settings, and are never compared here."
)
_TIMESTAMP = (
    " Two different start times for one measurement are a real discrepancy for you to "
    "review; nothing here picks one."
)
WITHIN_ONE_MEASUREMENT: Mapping[str, str] = {
    ev.CONCEPT_EMISSION_ENERGY: _ACQUISITION_SETTING,
    ev.CONCEPT_ENERGY_GRID: _ACQUISITION_SETTING,
    ev.CONCEPT_COUNTING_TIME: _ACQUISITION_SETTING,
    ev.CONCEPT_SCAN_COMMAND: _ACQUISITION_SETTING,
    ev.CONCEPT_FILTER: _ACQUISITION_SETTING,
    ev.CONCEPT_ACQUISITION_TIMESTAMP: _TIMESTAMP,
    ev.CONCEPT_ACQUISITION_EPOCH: _TIMESTAMP,
}


def _standing_resolution(
    concept: str,
    group: Sequence[ev.SourceEvidence],
    disputed: Sequence[ev.SourceEvidence],
    cardinality: str,
    source_ids: Mapping[str, str],
) -> dict | None:
    """The domain owner's standing rule for ONE disagreement, or ``None`` where it does
    not reach. See :data:`bl15.resolution.STANDING_RESOLUTIONS`.

    IT REACHES ONLY A DISAGREEMENT BETWEEN EXACTLY ITS TWO ROLES — a plan and a
    recording — and only when the RECORDINGS AGREE AMONG THEMSELVES at the concept's own
    cardinality. Two acquisition files recording different positions for the same motor
    of the same scan is not a plan-versus-recording question, so the rule says nothing
    and the conflict stays open. Every reading stays a source fact; the readings the
    rule uses are named in ``reading_used``.
    """
    rule = res.standing_resolution_for(concept)
    if rule is None:
        return None
    roles = {res.role_of_evidence(item) for item in disputed}
    # DEFENCE, AND NOT SEPARATELY REACHABLE TODAY (an independent review, 2026-10-12, found
    # no test kills its removal, and none can): the only readers that emit a position are
    # a macro (planned) and an acquisition file or scan export (recorded), so a dispute
    # holds no third role, and one between recordings alone is already refused by the
    # recordings-agree check below. It stays so a future reader of positions — a notes
    # line, a filename — cannot be resolved by a rule written about plans and recordings.
    if roles != {rule.chosen_source_role, rule.over_source_role}:
        return None
    recorded = [i for i in group if res.role_of_evidence(i) == rule.chosen_source_role]
    if not recorded:
        return None
    still, _keyed, _scans = _compare(recorded, cardinality, concept)
    if still:
        return None
    used: dict[tuple, dict] = {}
    for item in disputed:
        if res.role_of_evidence(item) != rule.chosen_source_role:
            continue
        key = (item.scan, item.item)
        row = used.setdefault(
            key,
            {
                "scan": item.scan,
                "item": item.item,
                "value": _reading_of(item),
                "source_ids": [],
                "locators": [],
            },
        )
        row["source_ids"] = sorted(set(row["source_ids"]) | set(_ids_for((item.source_path,), source_ids)))
        row["locators"].append(statement_locator(item))
    rows = [used[k] for k in sorted(used, key=lambda k: (str(k[1] or ""), _key_order(("scan", k[0], k[1]))))]
    return rule.to_state(reading_used=rows)


def _candidates_by_concept(
    items: Sequence[ev.SourceEvidence],
    *,
    candidate_prefix: str,
    source_ids: Mapping[str, str],
    by_concept: dict[str, int],
    by_status: dict[str, int],
    unregistered: set[str],
) -> Iterable[SemanticCandidate]:
    """ONE candidate per concept, over however many sources stated it.

    Grouped by concept rather than emitted per statement, because sixteen scan files each
    recording the same filter index is one fact with sixteen witnesses, not sixteen
    candidates. All sixteen statements are attached.

    **A concept whose sources disagree yields a candidate with NO value**, carrying every
    distinct reading — the same discipline :mod:`bl15.relate` applies to structure,
    applied to values.
    """
    grouped: dict[str, list[ev.SourceEvidence]] = defaultdict(list)
    for item in items:
        grouped[item.concept].append(item)

    for concept, group in sorted(grouped.items()):
        by_concept[concept] += 1
        entry = mp.mapping_for(concept)
        if entry is None:
            # A reader emitted a concept the registry has not examined. Reported, and
            # still turned into a candidate — silently dropping it would lose evidence
            # for a bookkeeping reason.
            unregistered.add(concept)
        else:
            by_status[entry.status] += 1

        statements = tuple(statement_for(i).to_state() for i in group)
        ids = _ids_for(tuple(i.source_path for i in group), source_ids)
        # DISTINCT FILES, not statements: sixteen scans stating one filter index are
        # sixteen witnesses; one file read under two conventions is one.
        witnesses = len({i.source_path for i in group})

        # COMPARED AT THE CONCEPT'S OWN CARDINALITY (`mp.RULE_CARDINALITY`, 2026-09-22).
        # A per-measurement concept is one comparison over every reading, exactly as
        # before. A per-scan concept is compared only within each scan (and item, and
        # file) — so scans that simply differ are not reported as sources disagreeing.
        cardinality = mp.cardinality_for(concept)
        disputed, keyed, scans = _compare(group, cardinality, concept)
        if disputed:
            distinct = sorted({_reading_of(i) for i in disputed})
            # THE DOMAIN OWNER'S STANDING RULE (2026-10-12), applied where it reaches:
            # a planned motor move against the recorded position of the same motor.
            standing = _standing_resolution(concept, group, disputed, cardinality, source_ids)
            yield SemanticCandidate(
                candidate_id=f"{candidate_prefix}::{concept}",
                kind=CANDIDATE_KIND_FIELD,
                determinism=DETERMINISM_DETERMINISTIC,
                resolved_by_rule=standing["rule_id"] if standing else None,
                standing_resolution=standing,
                rule=(
                    f"{len(group)} source(s) state {concept.replace('_', ' ')}, and they "
                    "do not agree." + WITHIN_ONE_MEASUREMENT.get(concept, "")
                    if cardinality == mp.CARDINALITY_PER_MEASUREMENT
                    else (
                        f"{len(group)} source(s) state {concept.replace('_', ' ')}, and "
                        f"two or more disagree about the {_SAME[cardinality]}"
                        + (
                            ""
                            if cardinality == mp.CARDINALITY_PER_SOURCE
                            else ", or a statement about the whole measurement disagrees "
                            "with one about a scan"
                        )
                        + f" ({mp.RULE_CARDINALITY.split(':', 1)[0]})."
                    )
                ),
                supporting_source_ids=ids,
                supporting_statements=statements,
                target_field_path=entry.official_path if entry else None,
                # THE ROW SHAPE IS `{value, source_ids, locators}`, NOT `{value,
                # sources}`. Corrected 2026-09-16 after a browser test found the
                # consequence: `CandidateCard` does `row.source_ids.map(...)`, so a
                # candidate carrying a disagreement CRASHED THE WHOLE SCREEN to a
                # blank page — React threw, unmounted the tree, and `main` vanished.
                #
                # This module invented a second spelling for a contract
                # `historical_import`'s own provider had already established. Nothing
                # caught it because no test rendered an archive candidate that
                # disagreed: the shape is only reachable when two sources state
                # different literals for one concept, which the fixture corpus does
                # and the unit tests asserted only on the server side.
                #
                # (2026-09-22) ONLY THE DISPUTED READINGS are competing sides: for a
                # per-scan concept, another scan's different value is that scan's own
                # reading, not a third side of this dispute.
                disagreement=tuple(
                    {
                        "value": value,
                        "source_ids": _sources_stating(disputed, value),
                        "locators": _locators_stating(disputed, value),
                    }
                    for value in distinct
                ),
                unresolved_reason=UNRESOLVED_SOURCES_DISAGREE,
                distinct_sources=witnesses,
            )
            continue

        # THE READINGS AGREE WITHIN EVERY COMPARISON GROUP. If they still differ across
        # groups, that is the concept's expected per-scan variation: kept, row by row.
        variation: tuple[dict, ...] = ()
        if _varies(keyed, cardinality, scans):
            variation = tuple(
                _variation_row(key, members, source_ids)
                for key, members in sorted(keyed.items(), key=lambda kv: _key_order(kv[0]))
            )
        varied = {
            "variation": variation,
            "variation_basis": cardinality if variation else None,
            "variation_scans": (
                (
                    len({row["source"] for row in variation})
                    if cardinality == mp.CARDINALITY_PER_SOURCE
                    else scans
                )
                if variation
                else None
            ),
        }

        if variation and entry is not None and entry.proposable:
            yield SemanticCandidate(
                candidate_id=f"{candidate_prefix}::{concept}",
                kind=CANDIDATE_KIND_FIELD,
                determinism=DETERMINISM_DETERMINISTIC,
                rule=_variation_rule(concept, group, cardinality, scans),
                supporting_source_ids=ids,
                supporting_statements=statements,
                target_field_path=entry.official_path,
                not_proposable_reason=VARIES_NOT_PROPOSABLE,
                distinct_sources=witnesses,
                **varied,
            )
            continue

        if entry is None or not entry.proposable:
            reason = (
                entry.reason
                if entry
                else (
                    "This reading has no entry in the mapping registry, so nothing here "
                    "can say whether the official schema has a place for it. It is kept "
                    "as evidence."
                )
            )
            yield SemanticCandidate(
                candidate_id=f"{candidate_prefix}::{concept}",
                kind=CANDIDATE_KIND_FIELD,
                determinism=DETERMINISM_DETERMINISTIC,
                rule=(
                    _variation_rule(concept, group, cardinality, scans)
                    if variation
                    else _rule_for(concept, group)
                ),
                supporting_source_ids=ids,
                supporting_statements=statements,
                target_field_path=entry.official_path if entry else None,
                not_proposable_reason=reason,
                distinct_sources=witnesses,
                **varied,
            )
            continue

        normalized = _normalized_of(group)
        if not is_zoned_utc_value(entry.official_path, normalized):
            # A ZONE-LESS LOCAL TIME NEVER GOES INTO A UTC FIELD (2026-09-23): kept as
            # evidence, with the reason; the epoch-derived UTC instant is offered instead.
            yield SemanticCandidate(
                candidate_id=f"{candidate_prefix}::{concept}",
                kind=CANDIDATE_KIND_FIELD,
                determinism=DETERMINISM_DETERMINISTIC,
                rule=_rule_for(concept, group),
                supporting_source_ids=ids,
                supporting_statements=statements,
                target_field_path=entry.official_path,
                not_proposable_reason=CANDIDATE_NOT_PROPOSABLE_LOCAL_TIME,
                distinct_sources=witnesses,
            )
            continue
        yield SemanticCandidate(
            candidate_id=f"{candidate_prefix}::{concept}",
            kind=CANDIDATE_KIND_FIELD,
            # A NORMALISED reading is still DETERMINISTIC: a stored, named rule was
            # applied to what a source literally says. `inferred` is reserved for a value
            # NO source states, and nothing in this module produces one.
            determinism=DETERMINISM_DETERMINISTIC,
            rule=_rule_for(concept, group),
            supporting_source_ids=ids,
            supporting_statements=statements,
            target_field_path=entry.official_path,
            proposed_value=normalized,
            distinct_sources=witnesses,
        )


def _candidate_from_conflict(
    conflict: Conflict, candidate_id: str, source_ids: Mapping[str, str]
) -> SemanticCandidate:
    """A structural disagreement, carried with every reading and no chosen value.

    ``kind`` is ``run`` rather than ``field``: these conflicts are about which
    measurement a file IS, not about a value at a field path. `SemanticCandidate` already
    refuses to hold a ``proposed_value`` beside an ``unresolved_reason``, so the
    no-winner property is enforced by the type rather than by this function.
    """
    return SemanticCandidate(
        candidate_id=candidate_id,
        kind=CANDIDATE_KIND_RUN,
        determinism=DETERMINISM_DETERMINISTIC,
        rule=conflict.explanation,
        supporting_source_ids=_ids_for(
            tuple(r.source_path for r in conflict.readings), source_ids
        ),
        supporting_statements=tuple(
            {
                "key": conflict.kind,
                "value": r.value,
                "locator": f"{r.source_path} · {r.locator}",
            }
            for r in conflict.readings
        ),
        # Same contract as above — `source_ids` and `locators`, never `sources`.
        disagreement=tuple(
            {
                "value": r.value,
                "source_ids": [r.source_path],
                "locators": [r.locator],
            }
            for r in conflict.readings
        ),
        unresolved_reason=UNRESOLVED_SOURCES_DISAGREE,
        not_proposable_reason=DISAGREEMENT_NOT_PROPOSABLE,
        distinct_sources=len({r.source_path for r in conflict.readings}),
    )


# --- shared context ----------------------------------------------------------


def _shared_evidence(
    relationships: Relationships,
    evidence_by_source: Mapping[str, Sequence[ev.SourceEvidence]],
) -> list[ev.SourceEvidence]:
    """Beamtime-scope readings, from the sources no measurement claimed.

    **Selected by the reading's own ``scope``, not by which file it came from.** A
    beamtime notes document states things at three scopes at once — the campaign's dates,
    a sample group's preparation, one measurement's quality — so treating a whole file as
    beamtime-scope would attach a sample-specific remark to all 94 measurements.

    These become candidates the import INHERITS. They are deliberately not copied onto
    each unit: a README value rendered 94 times as though it had been entered 94 times is
    a lie about where it came from.
    """
    unattached = {entry["archive_path"] for entry in relationships.unattached}
    out: list[ev.SourceEvidence] = []
    for path in sorted(unattached):
        for item in evidence_by_source.get(path, ()):
            # A LOGBOOK STATEMENT ABOUT THE ENVIRONMENT, REACTION OR CELL is applied PER
            # MEASUREMENT (:func:`logbook_candidates`), because each one is a run's field
            # — a beamtime-wide one is inherited by every measurement there, never sent
            # as a value for the import as a whole.
            if item.scope == ev.SCOPE_BEAMTIME and item.concept not in cond.FIELDS:
                out.append(item)
    return out


# --- helpers -----------------------------------------------------------------


def _reading_of(item: ev.SourceEvidence) -> str:
    """The value two sources are compared ON.

    The NORMALISED value when there is one, else the literal — so ``060mV`` and ``0p06V``
    are recognised as agreeing rather than reported as a conflict, while an unnormalised
    concept still compares on what the file says. Comparing literals alone would
    manufacture disagreements out of the corpus's two unit conventions.
    """
    if (
        item.concept == ev.CONCEPT_SAMPLE_POSITION
        and item.item
        and item.normalized_value is not None
        and not isinstance(item.normalized_value, Mapping)
    ):
        # A RECORDED STAGE POSITION NAMES ITS MOTOR (2026-10-12), so `Sx 12.5` and a
        # plan's `Sx 13.0` read side by side as two accounts of the same motor.
        return f"{item.item} {_text_of(item.normalized_value)}"
    if item.normalized_value is not None:
        return f"{_text_of(item.normalized_value)}{f' {item.unit}' if item.unit else ''}"
    return item.raw_literal


#: The concepts whose readings are motor POSITIONS, compared on their number
#: (`bl15.mapping.cardinality.v3`).
_POSITION_CONCEPTS = frozenset({ev.CONCEPT_SAMPLE_POSITION, ev.CONCEPT_MOTOR_POSITION})


def _is_move(value) -> bool:
    return isinstance(value, Mapping) and set(value) == {"motor", "value", "relative"}


def _is_relative_move(item: ev.SourceEvidence) -> bool:
    """A macro's ``mvr``: a move BY an amount, which is not a position. (``bl15.macros``
    reads ``mv``, ``mvr`` and ``umv``; ``umvr`` is not one of its verbs.)"""
    return _is_move(item.normalized_value) and bool(item.normalized_value.get("relative"))


def _position_number(item: ev.SourceEvidence):
    """The number a position reading states — a recorded value, or a planned move's target."""
    value = item.normalized_value
    if _is_move(value):
        value = value.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _text_of(value) -> str:
    """A normalised value as the text a scientist reads — NEVER a Python repr.

    Corrected 2026-09-22: a scan export's ``acquisition_target`` normalises to
    ``{"measurement_stem": …, "scan_index": 1}``, and formatting that with an f-string
    put ``{'measurement_stem': '01_01_…', 'scan_index': 1}`` on the screen. A mapping is
    written from its fields; the measurement-and-scan pair is written the way the rest
    of the review names a scan.
    """
    if isinstance(value, Mapping):
        if set(value) == {"measurement_stem", "scan_index"}:
            return f"{value['measurement_stem']} · scan {value['scan_index']}"
        if _is_move(value):
            # A MOVE IS WRITTEN AS THE COMMAND SAYS IT (2026-10-12) — `Sx 13.0`, or
            # `Sz by -0.3 (relative move)` — never as `motor Sx; relative False; …`.
            if value.get("relative"):
                return f"{value['motor']} by {_text_of(value['value'])} (relative move)"
            return f"{value['motor']} {_text_of(value['value'])}"
        return "; ".join(f"{str(k).replace('_', ' ')} {_text_of(v)}" for k, v in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return ", ".join(_text_of(v) for v in value)
    return str(value)


#: What a per-scan disagreement is ABOUT, in the rule sentence.
_SAME = {
    mp.CARDINALITY_PER_SCAN: "same scan",
    mp.CARDINALITY_PER_SCAN_ITEM: "same scan and item",
    mp.CARDINALITY_PER_SOURCE: "same token of the same file",
}


def _compare(
    group: Sequence[ev.SourceEvidence], cardinality: str, concept: str
) -> tuple[list[ev.SourceEvidence], dict[tuple, list[ev.SourceEvidence]], int]:
    """Decide what disagrees, at the concept's cardinality. See
    :data:`bl15.mapping.RULE_CARDINALITY` (v2, 2026-09-23).

    Returns ``(disputed readings, the groups each reading belongs to, how many
    distinct scans the readings establish)``.

    * ``per_measurement`` — one group; every reading is compared with every other.
    * ``per_source`` — grouped by file and item; compared within a group.
    * ``per_scan`` / ``per_scan_item`` — a reading whose scan the SOURCE ITSELF states
      (`SourceEvidence.scan`, a SPEC scan number from the source's own ``#S`` line) is
      grouped with the other readings about that scan (and item). **Every other
      reading — a macro's plan, a file-level header, a statement whose scan is not
      established — is compared with EVERY reading of the same item**, on the
      concept's measurement-level projection (`_projection`). v1 kept those in a group
      of their own, so a macro's planned value and the header's recorded value for the
      same, only scan were never compared, and a difference read as variation. It is a
      disagreement.
    """
    if cardinality == mp.CARDINALITY_PER_MEASUREMENT:
        groups = {("measurement", None, None): list(group)}
        disputed = list(group) if len({_reading_of(i) for i in group}) > 1 else []
        return disputed, groups, 0

    if cardinality == mp.CARDINALITY_PER_SOURCE:
        by_source: dict[tuple, list[ev.SourceEvidence]] = defaultdict(list)
        for item in group:
            by_source[("source", item.source_path, item.item)].append(item)
        disputed = [
            member
            for members in by_source.values()
            if len({_reading_of(i) for i in members}) > 1
            for member in members
        ]
        return disputed, dict(by_source), 0

    per_item = cardinality == mp.CARDINALITY_PER_SCAN_ITEM
    scan_groups: dict[tuple, list[ev.SourceEvidence]] = defaultdict(list)
    loose: dict[str | None, list[ev.SourceEvidence]] = defaultdict(list)
    #: A RELATIVE MOVE is a change, not a position (v3): kept, and compared with nothing.
    moves_by: dict[str | None, list[ev.SourceEvidence]] = defaultdict(list)
    for item in group:
        slot = item.item if per_item else None
        if concept in _POSITION_CONCEPTS and _is_relative_move(item):
            moves_by[slot].append(item)
        elif item.scope == ev.SCOPE_SCAN and item.scan is not None:
            scan_groups[(item.scan, slot)].append(item)
        else:
            loose[slot].append(item)

    disputed: list[ev.SourceEvidence] = []
    seen: set[str] = set()

    def dispute(members: Iterable[ev.SourceEvidence]) -> None:
        for member in members:
            if member.evidence_id not in seen:
                seen.add(member.evidence_id)
                disputed.append(member)

    same = (
        (lambda i: _projection(i, concept)) if concept in _POSITION_CONCEPTS else _reading_of
    )
    for members in scan_groups.values():
        if len({same(i) for i in members}) > 1:
            dispute(members)
    for slot, members in loose.items():
        related = members + [
            m for (_scan, other), ms in scan_groups.items() if other == slot for m in ms
        ]
        if len({_projection(m, concept) for m in related}) > 1:
            dispute(related)

    groups: dict[tuple, list[ev.SourceEvidence]] = {
        ("scan", scan, slot): members for (scan, slot), members in scan_groups.items()
    }
    for slot, members in loose.items():
        groups[("measurement", None, slot)] = members
    for slot, members in moves_by.items():
        groups[("measurement", None, f"{slot} (relative move)" if slot else "relative move")] = members
    scans = len({scan for (scan, _slot) in scan_groups})
    return disputed, groups, scans


def _projection(item: ev.SourceEvidence, concept: str) -> str:
    """What a measurement-level reading is compared ON against a scan-level one.

    For ``acquisition_target`` only the MEASUREMENT part: a macro declares a stem, and
    a scan export's basename states that stem plus its own index — so a macro's
    ``01_01_ZZ1`` agrees with ``01_01_ZZ1 · scan 1``. Every other concept is compared
    on the whole reading.
    """
    if concept == ev.CONCEPT_ACQUISITION_TARGET:
        value = item.normalized_value
        if isinstance(value, Mapping) and value.get("measurement_stem"):
            return str(value["measurement_stem"])
        return item.raw_literal
    if concept in _POSITION_CONCEPTS:
        # ON THE NUMBER (v3, 2026-10-12): a header's `13` and a plan's `13.0` are one
        # position. `repr(float)` is exact, so nothing is rounded into agreement.
        number = _position_number(item)
        if number is not None:
            return repr(number)
    return _reading_of(item)


def _varies(keyed: Mapping[tuple, Sequence[ev.SourceEvidence]], cardinality: str, scans: int) -> bool:
    """Whether readings that AGREE within every comparison still differ across them.

    A per-scan concept varies only when at least TWO scans are established and their
    readings differ — one scan cannot "differ from scan to scan". A per-scan-item
    concept varies when its items differ (several per scan), and a per-source concept
    when its files or tokens do. Readings that agree on their projection but are
    written differently (a macro's stem, one scan's ``stem · scan 1``) are agreement.
    """
    if cardinality == mp.CARDINALITY_PER_MEASUREMENT:
        return False
    scan_readings = {
        _reading_of(members[0]) for key, members in keyed.items() if key[0] != "measurement"
    }
    if cardinality == mp.CARDINALITY_PER_SCAN:
        return scans >= 2 and len(scan_readings) > 1
    return len(scan_readings) > 1


def _key_order(key: tuple) -> tuple:
    """Measurement-level first, then scans in their NUMERIC order, then items."""
    if key[0] == "source":
        return (2, 0, str(key[1]), str(key[2] or ""))
    kind, scan, item = key
    number = int(scan) if isinstance(scan, str) and scan.isdigit() else -1
    return (0 if kind == "measurement" else 1, number, str(scan or ""), str(item or ""))


def _variation_row(
    key: tuple, members: Sequence[ev.SourceEvidence], source_ids: Mapping[str, str]
) -> dict:
    """ONE scan's (or item's, or file's) reading. Every member agrees — a group that
    did not would have been a disagreement."""
    value = _reading_of(members[0])
    if key[0] == "source":
        scan, item, source = None, key[2], key[1]
    else:
        scan, item, source = key[1], key[2], None
    return {
        "scan": scan,
        "item": item,
        "source": source,
        "value": value,
        "source_ids": list(_ids_for(tuple(m.source_path for m in members), source_ids)),
        "locators": [statement_locator(m) for m in members],
    }


def _variation_rule(
    concept: str, group: Sequence[ev.SourceEvidence], cardinality: str, scans: int
) -> str:
    """The warrant for a varying candidate: what was read, and why it is not a conflict.

    Worded per cardinality, and "differs from scan to scan" ONLY when two or more scans
    are established — a concept a scan states several of, over one scan, says so.
    """
    count = len(group)
    read = f"Read from {count} source{'s' if count != 1 else ''}."
    subject = concept.replace("_", " ")
    rule = mp.RULE_CARDINALITY.split(":", 1)[0]
    if cardinality == mp.CARDINALITY_PER_SOURCE:
        return (
            f"{read} Each file states its own {subject}, one per token of its name "
            f"({rule}), so different files stating different values is not a "
            "disagreement; no two sources disagree about the same token of the same file."
        )
    if cardinality == mp.CARDINALITY_PER_SCAN_ITEM:
        across = (
            f", and across the {scans} scans each item keeps its own scan's reading"
            if scans >= 2
            else ""
        )
        return (
            f"{read} A scan states several values of {subject}, one per column or motor "
            f"({rule}), so they are kept item by item{across}; no two sources disagree "
            "about the same item of the same scan."
        )
    return (
        f"{read} The value differs from scan to scan across {scans} scans, which is "
        f"expected for {subject} ({rule}): each scan keeps its own reading, and no two "
        "sources disagree about the same scan."
    )


def _normalized_of(group: Sequence[ev.SourceEvidence]):
    """The value to propose: the normalised one if any reading carries it, else the literal."""
    for item in group:
        if item.normalized_value is not None:
            return item.normalized_value
    return group[0].raw_literal


def value_of_reading(items: Sequence[ev.SourceEvidence], reading: str):
    """The value a candidate proposes when ``reading`` is the one CHOSEN among ``items``.

    Exactly what an AGREEING candidate over the items that state that reading would
    propose (:func:`_normalized_of` over them): the normalised value when one of them
    carries it, else the literal as written. ``None`` when no item states the reading.
    Added 2026-09-22 so a scientist-confirmed resolution proposes the SAME value the
    sources would have produced had they agreed — never a number regex-coerced out of
    the comparison string (``'060'`` stays ``'060'``; ``'500 cycles'`` stays itself).
    """
    stating = [item for item in items if _reading_of(item) == reading]
    return _normalized_of(stating) if stating else None


#: The public name of :func:`_reading_of` — what a disagreement row's ``value`` is.
def reading_of(item: ev.SourceEvidence) -> str:
    return _reading_of(item)


def statement_locator(item: ev.SourceEvidence) -> str:
    """The ``locator`` :func:`statement_for` gives ``item`` — the key that links a
    supporting statement back to the evidence it was built from."""
    return f"{item.source_path}{_LOCATOR_JOIN}{item.locator}"


_LOCATOR_JOIN = " · "


def split_statement_locator(locator: str, archive_paths) -> tuple[str, str] | None:
    """Undo :func:`statement_locator` against KNOWN archive paths: ``(path, within)``.

    Defined HERE, beside the format it inverts, so no caller parses this module's
    punctuation (``routes._import_statement_filename``'s rule). The longest known path
    the locator begins with wins, so ``a/b.txt`` is never mistaken for ``a``; ``None`` when
    no known path matches, and the caller then keeps the locator whole. Added 2026-10-11
    so a beamtime statement can be identified by WHICH BYTES said it rather than by where
    the container happened to put the file.
    """
    best = None
    for path in archive_paths:
        if (
            isinstance(path, str)
            and path
            and locator.startswith(f"{path}{_LOCATOR_JOIN}")
            and (best is None or len(path) > len(best))
        ):
            best = path
    if best is None:
        return None
    return best, locator[len(best) + len(_LOCATOR_JOIN) :]


def _sources_stating(group: Sequence[ev.SourceEvidence], reading: str) -> list[str]:
    return sorted({i.source_path for i in group if _reading_of(i) == reading})


def _locators_stating(group: Sequence[ev.SourceEvidence], reading: str) -> list[str]:
    """WHERE each source says it — the third key of the disagreement-row contract.

    A scientist resolving a disagreement needs the locator, not only the filename: two
    readings from one file at different lines are the common case in a SPEC header.
    """
    return [
        f"{i.source_path} · {i.locator}" for i in group if _reading_of(i) == reading
    ]


def _rule_for(concept: str, group: Sequence[ev.SourceEvidence]) -> str:
    """The warrant, in a sentence, naming the normalisation when one was applied."""
    count = len(group)
    witnesses = f"{count} source{'s' if count != 1 else ''}"
    rules = sorted({i.normalization_rule for i in group if i.normalization_rule})
    subject = concept.replace("_", " ")
    if rules:
        return (
            f"Read from {witnesses}, then normalised by: {', '.join(rules)}. "
            "The original text is kept beside the value."
        )
    return f"Read from {witnesses}, exactly as written."


def _ids_for(paths: Sequence[str], source_ids: Mapping[str, str]) -> tuple[str, ...]:
    """Session source ids for these paths, deduplicated and sorted.

    Falls back to the archive path when no id is known. **A candidate always names
    something a scientist can find**, which is why this never returns an empty tuple for
    a non-empty input.
    """
    return tuple(sorted({source_ids.get(path, path) for path in paths}))


def _candidate_state(candidate: SemanticCandidate) -> dict:
    """The wire shape, with `proposable` derived rather than stored."""
    return {
        "candidate_id": candidate.candidate_id,
        "kind": candidate.kind,
        "determinism": candidate.determinism,
        "rule": candidate.rule,
        "supporting_source_ids": list(candidate.supporting_source_ids),
        "supporting_statements": [dict(s) for s in candidate.supporting_statements],
        "target_field_path": candidate.target_field_path,
        "proposed_value": candidate.proposed_value,
        "disagreement": [dict(d) for d in candidate.disagreement],
        "unresolved_reason": candidate.unresolved_reason,
        "not_proposable_reason": candidate.not_proposable_reason,
        # 2026-10-18 — the short sentence beside the full one (`hist.plain_reason`).
        "not_proposable_summary": plain_reason_of(candidate),
        "proposable": candidate.proposable,
        "distinct_sources": candidate.distinct_sources,
        "agreement": candidate.agreement,
        "review_status": candidate.review_status,
    }


# --- the domain owner's 2026-10-12 answers: environment, reaction, cell type ----------
#
# "those markers or descriptors or values need to be extracted by the skill within the
# metadata available. If not available, then the claude skill needs to leave it blank for
# a human to select the appropriate value." — Angel (domain owner), relayed by the project
# owner. So there are exactly two ways a value reaches these three fields from an import,
# both PROPOSALS, both citing what a source said; everything else is left for a person.

#: The one inferred environment. Named and versioned; see :func:`dry_sample_environment`.
RULE_DRY_SAMPLE_IS_EX_SITU = "bl15.environment.dry_sample_is_ex_situ.v1"

#: The field and the member the rule names. The member is CHECKED against the vendored
#: schema at runtime (`mp.schema_enum`) — the rule proposes nothing if the schema stops
#: offering it.
_ENVIRONMENT_PATH = "context.environment"
_EX_SITU = "ex_situ"


#: What may stand beside a dry / no-electrolyte statement in a measurement's own name and
#: still let the rule apply: tokens that IDENTIFY the measurement or the sample — never one
#: that states a condition of the measurement.
_IDENTITY_BESIDE_DRY = frozenset(
    {
        ev.CONCEPT_LEGACY_NUMBER,
        ev.CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER,
        ev.CONCEPT_SAMPLE_NAME,
        ev.CONCEPT_FILTER,
        # a property of the sample (an overlayer thickness or a weight loading), not of
        # the measurement's environment
        ev.CONCEPT_LOADING_OR_THICKNESS,
        ev.CONCEPT_DRY_STATE,
    }
)


def _may_stand_beside_dry(item: ev.SourceEvidence) -> bool:
    """Whether one token of a measurement's own name leaves the dry rule applicable."""
    if item.concept in _IDENTITY_BESIDE_DRY:
        return True
    if item.concept == ev.CONCEPT_ELECTROLYTE_OR_MEDIUM:
        return item.normalized_value == "none"
    # "As received" describes the sample's history, and with no electrolyte it is still
    # dry; any OTHER before/after reading (after cycling …) is a condition.
    if item.concept == ev.CONCEPT_BEFORE_AFTER_STATE:
        return item.normalized_value == "as_is"
    return False


def dry_sample_environment(
    unit: MeasurementUnit,
    items: Sequence[ev.SourceEvidence],
    source_ids: Mapping[str, str],
) -> SemanticCandidate | None:
    """``context.environment = ex_situ`` for a measurement whose OWN NAME says it was dry.

    **THE RULE.** A measurement's own filename (the acquisition file's name, read under
    the convention in force) states that the sample was DRY, or that there was NO
    ELECTROLYTE (``NoElectrolyte`` reads as the medium ``none``). A sample with no
    electrolyte cannot be under reaction conditions, so it was measured outside them —
    ex situ — and the domain owner confirmed exactly that for "the dry or reference
    standard samples" on 2026-10-12. Either statement alone qualifies, because each says
    the same thing: there was no liquid. It is DETERMINISTIC in the sense the import
    uses (a stored rule over what a source states) and labelled ``inferred``, because no
    source writes the word "ex situ".

    **WHAT DOES NOT QUALIFY, AND WHY** — each leaves the environment for a person:

    * an "as-is" (as received) token ALONE. It describes the sample's history, not the
      measurement: an as-received electrode can be measured in electrolyte under
      potential, which is not ex situ. Measured: the multi-operator corpus's
      ``07_03_ZZ3_alk_fresh_f30_1000mV`` reads ``fresh`` as as-is in an alkaline medium
      at 1000 mV under its second convention;
    * a name that says ANYTHING ELSE about the conditions — an electrolyte, a potential,
      a pH, a gas or saturation, a flow rate, a cycling state, or a token no convention
      recognises (:data:`_IDENTITY_BESIDE_DRY` is the whole allowlist). Dry and in
      electrolyte, or dry under a gas flow, is a reading this rule does not settle;
    * a measurement whose name is itself disputed — its file header declares a different
      name. Which name is right decides whether the token applies at all.

    Never written: the candidate is a PROPOSAL a person accepts or rejects, and
    acceptance keeps its trusted-actor gate. ``None`` when the name states neither.
    """
    own = [
        item
        for item in items
        if item.source_path == unit.acquisition_path
        and item.parser_id in res._FILENAME_PARSER_IDS
    ]
    stating = [
        item
        for item in own
        if (item.concept == ev.CONCEPT_DRY_STATE)
        or (
            item.concept == ev.CONCEPT_ELECTROLYTE_OR_MEDIUM
            and item.normalized_value == "none"
        )
    ]
    if not stating:
        return None
    # CONSERVATIVE BY ALLOWLIST (2026-10-12, review I4): the name may say NOTHING ELSE
    # about the measurement's conditions. Only identity tokens and the dry statement
    # itself may stand beside it; anything else — an unrecognised token, a pH, a gas or
    # saturation, a flow rate, an electrolyte, a medium, a potential, a cycling state —
    # leaves the environment for a person. `dry_O2Sat`, `dry_pH13`, `dry_10mLmin`,
    # `dry_O2` and `dry_alk` were proposed ex_situ by the first version, which looked only
    # for an electrolyte or a potential.
    contrary = [item for item in own if not _may_stand_beside_dry(item)]
    renamed = any(c.kind == CONFLICT_DECLARATION_VS_FILENAME for c in unit.conflicts)
    # EACH TOKEN ONCE (re-review, 2026-10-12): one token can be read as two concepts —
    # `afterCV` is a cycling state AND its before/after half — and was named twice.
    said = ", ".join(f"`{literal}`" for literal in dict.fromkeys(i.raw_literal for i in stating))
    statements = tuple(statement_for(item).to_state() for item in (*stating, *contrary))
    common = dict(
        candidate_id=f"{unit.stem}::environment",
        kind=CANDIDATE_KIND_FIELD,
        determinism=DETERMINISM_INFERRED,
        supporting_source_ids=_ids_for((unit.acquisition_path,), source_ids),
        supporting_statements=statements,
        target_field_path=_ENVIRONMENT_PATH,
        distinct_sources=1,
    )
    if contrary or renamed:
        why = (
            "its name also states "
            + ", ".join(f"`{literal}`" for literal in dict.fromkeys(i.raw_literal for i in contrary))
            + ", which this rule does not read as dry"
            if contrary
            else "its own file header declares a different name, so which name is right "
            "is still a question"
        )
        return SemanticCandidate(
            **common,
            rule=(
                f"{RULE_DRY_SAMPLE_IS_EX_SITU}: this measurement's name says {said}, but "
                f"{why}. The rule does not apply."
            ),
            not_proposable_reason=(
                f"The name says {said}, but {why}, so this import does not say the sample "
                "was measured dry. The environment is left blank for a person to choose."
            ),
        )
    if _EX_SITU not in mp.schema_enum(_ENVIRONMENT_PATH):
        return SemanticCandidate(
            **common,
            rule=f"{RULE_DRY_SAMPLE_IS_EX_SITU}: the schema does not offer `{_EX_SITU}`.",
            not_proposable_reason=(
                "The official schema this build carries does not offer ex_situ as an "
                "environment, so nothing is proposed."
            ),
        )
    return SemanticCandidate(
        **common,
        rule=(
            f"{RULE_DRY_SAMPLE_IS_EX_SITU}: this measurement's own name says {said} — the "
            "sample had no electrolyte, so it was not measured under reaction "
            "conditions, and the domain owner has confirmed that a dry sample is measured "
            "ex situ. This is a proposal for a person to accept or reject; nothing is "
            "written."
        ),
        proposed_value=_EX_SITU,
    )


def logbook_candidates(
    stem: str,
    statements: Mapping[str, Sequence[ev.SourceEvidence]],
    source_ids: Mapping[str, str],
) -> list[SemanticCandidate]:
    """ONE candidate per field the LOGBOOK speaks to for this measurement. See
    :mod:`bl15.conditions`.

    ``statements`` holds, per logbook concept, the statements that APPLY to this
    measurement — its own sample section's, or the beamtime-wide ones when its section
    says nothing about that field (a section's statement overrides the beamtime's for
    that section only; the caller decides that, from the notes reader's file numbers).

    * exactly one schema option, and nothing else said about the field → a PROPOSAL of
      that option, citing every sentence that says it;
    * two or more different options → a CONFLICT: every sentence kept, nothing chosen;
    * a term that is not an option, fits several, or sits in a negating sentence → no
      value, the sentence kept, the field left blank for a person — with the reason.

    A logbook that says nothing about a field produces nothing for it.
    """
    out: list[SemanticCandidate] = []
    for concept, (path, rule_id, name) in cond.FIELDS.items():
        items = list(statements.get(concept) or ())
        if not items:
            continue
        readings = [
            (item, item.normalized_value if isinstance(item.normalized_value, Mapping) else {})
            for item in items
        ]
        allowed = set(mp.schema_enum(path))
        members = sorted(
            {
                str(value.get("member"))
                for _item, value in readings
                if value.get("status") == cond.STATUS_MEMBER
                and value.get("member") in allowed
            }
        )
        unusable = [
            (item, value)
            for item, value in readings
            if not (value.get("status") == cond.STATUS_MEMBER and value.get("member") in allowed)
        ]
        scope = (
            "the sample section that lists this measurement"
            if any(value.get("section") for _item, value in readings)
            else "the whole beamtime (no sample section says otherwise)"
        )
        common = dict(
            candidate_id=f"{stem}::{concept}",
            kind=CANDIDATE_KIND_FIELD,
            determinism=DETERMINISM_DETERMINISTIC,
            supporting_source_ids=_ids_for(tuple(i.source_path for i in items), source_ids),
            supporting_statements=tuple(statement_for(i).to_state() for i in items),
            target_field_path=path,
            distinct_sources=len({i.source_path for i in items}),
        )
        if len(members) > 1:
            out.append(
                SemanticCandidate(
                    **common,
                    rule=(
                        f"{rule_id}: the logbook states more than one {name} for this "
                        f"measurement ({', '.join(members)}), in {scope}. Every sentence is "
                        "kept and nothing is chosen."
                    ),
                    disagreement=tuple(
                        {
                            "value": member,
                            "source_ids": list(
                                _ids_for(
                                    tuple(
                                        i.source_path
                                        for i, v in readings
                                        if v.get("member") == member
                                    ),
                                    source_ids,
                                )
                            ),
                            "locators": [
                                statement_locator(i) for i, v in readings if v.get("member") == member
                            ],
                        }
                        for member in members
                    ),
                    unresolved_reason=UNRESOLVED_SOURCES_DISAGREE,
                )
            )
            continue
        if len(members) == 1 and not unusable:
            first = next(item for item, value in readings if value.get("member") == members[0])
            term = next(
                str(value.get("term")) for _item, value in readings if value.get("member") == members[0]
            )
            out.append(
                SemanticCandidate(
                    **common,
                    rule=(
                        f"{rule_id}: the logbook says “{term}” ({statement_locator(first)}), "
                        f"which is the schema's {name} option `{members[0]}`; it is stated in "
                        f"{scope}. This is a proposal for a person to accept or reject; "
                        "nothing is written."
                    ),
                    proposed_value=members[0],
                )
            )
            continue
        _item, value = unusable[0]
        term = str(value.get("term") or "")
        status = value.get("status")
        if status == cond.STATUS_AMBIGUOUS:
            why = (
                f"“{term}” fits more than one of the schema's {name} options "
                f"({', '.join(str(o) for o in value.get('options') or [])}), so nothing is "
                "chosen."
            )
        elif status == cond.STATUS_NEGATED:
            why = (
                f"The logbook mentions “{term}” in a sentence that negates or contrasts it, "
                "which this build does not interpret."
            )
        elif status == cond.STATUS_HEDGED:
            why = (
                f"The logbook mentions “{term}” in a sentence that is a question, a plan or "
                "a guess rather than a statement of what was done, so nothing is filled in."
            )
        elif status == cond.STATUS_NOT_UNDER_STUDY:
            why = (
                f"The logbook names “{term}” as a reaction that was suppressed, avoided or "
                "competing — not the reaction under study — so nothing is filled in."
            )
        elif status == cond.STATUS_SUBSET:
            why = (
                f"The logbook says “{term}” about only part of this sample section, and "
                "which part is not something this build decides."
            )
        elif members:
            why = (
                f"The logbook names `{members[0]}` and also says “{term}”, which is not one "
                f"of the schema's {name} options, so nothing is filled in."
            )
        else:
            why = (
                f"The logbook says “{term}”, which is not one of the {name} options the "
                "official schema offers, so nothing is filled in."
            )
        out.append(
            SemanticCandidate(
                **common,
                rule=f"{rule_id}: {why} The sentence is kept as it was written.",
                not_proposable_reason=f"{why} It is left blank for a person to choose.",
            )
        )
    return out


def logbook_unscoped_candidates(
    items: Sequence[ev.SourceEvidence],
    source_ids: Mapping[str, str],
) -> list[SemanticCandidate]:
    """ONE beamtime-level candidate per field for logbook sentences about samples this
    build cannot map onto measurements (review I3, 2026-10-12).

    A sentence before any sample section that NAMES particular samples ("only samples 3
    and 4 were run in a flow cell") is not about every measurement, and is applied to the
    named ones only when the logbook's numbering and the filenames' sample token agree
    (``historical_import``). When they do not — or the sentence singles out an unnamed
    subset ("only some", "except", a sample code) — it is applied to NO measurement. It is
    still a reading, so it is kept here, verbatim, with no value, and the fields it speaks
    to stay left for a person on every run.
    """
    by_concept: dict[str, list[ev.SourceEvidence]] = defaultdict(list)
    for item in items:
        if item.concept in cond.FIELDS:
            by_concept[item.concept].append(item)
    out: list[SemanticCandidate] = []
    for concept, group in sorted(by_concept.items()):
        path, rule_id, name = cond.FIELDS[concept]
        why = (
            f"The logbook's sentence names particular samples, or only some of them, and "
            f"this import cannot say which measurements those are, so the {name} it "
            "states is applied to none of them."
        )
        out.append(
            SemanticCandidate(
                candidate_id=f"shared::unscoped::{concept}",
                kind=CANDIDATE_KIND_FIELD,
                determinism=DETERMINISM_DETERMINISTIC,
                rule=f"{rule_id}: {why} The sentence is kept as it was written.",
                supporting_source_ids=_ids_for(tuple(i.source_path for i in group), source_ids),
                supporting_statements=tuple(statement_for(i).to_state() for i in group),
                target_field_path=path,
                not_proposable_reason=f"{why} It is left blank for a person to choose on each run.",
                distinct_sources=len({i.source_path for i in group}),
            )
        )
    return out
