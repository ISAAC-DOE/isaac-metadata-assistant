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

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..historical_import import (
    CANDIDATE_KIND_FIELD,
    CANDIDATE_KIND_RUN,
    DETERMINISM_DETERMINISTIC,
    UNRESOLVED_SOURCES_DISAGREE,
    EvidenceStatement,
    SemanticCandidate,
)
from . import evidence as ev
from . import mapping as mp
from .relate import Conflict, MeasurementUnit, Relationships

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

    seen: set[str] = set()
    out: list[ev.SourceEvidence] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.extend(evidence_by_source.get(path, ()))
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

        distinct = sorted({_reading_of(i) for i in group})
        if len(distinct) > 1:
            yield SemanticCandidate(
                candidate_id=f"{candidate_prefix}::{concept}",
                kind=CANDIDATE_KIND_FIELD,
                determinism=DETERMINISM_DETERMINISTIC,
                rule=(
                    f"{len(group)} source(s) state {concept.replace('_', ' ')}, and they "
                    "do not agree."
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
                disagreement=tuple(
                    {
                        "value": value,
                        "source_ids": _sources_stating(group, value),
                        "locators": _locators_stating(group, value),
                    }
                    for value in distinct
                ),
                unresolved_reason=UNRESOLVED_SOURCES_DISAGREE,
                distinct_sources=witnesses,
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
                rule=_rule_for(concept, group),
                supporting_source_ids=ids,
                supporting_statements=statements,
                target_field_path=entry.official_path if entry else None,
                not_proposable_reason=reason,
                distinct_sources=witnesses,
            )
            continue

        normalized = _normalized_of(group)
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
            if item.scope == ev.SCOPE_BEAMTIME:
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
    if item.normalized_value is not None:
        return f"{item.normalized_value}{f' {item.unit}' if item.unit else ''}"
    return item.raw_literal


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
    return f"{item.source_path} · {item.locator}"


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
        "proposable": candidate.proposable,
        "distinct_sources": candidate.distinct_sources,
        "agreement": candidate.agreement,
        "review_status": candidate.review_status,
    }
