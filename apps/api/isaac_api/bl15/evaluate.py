"""The gold-standard harness. What a reconstruction got RIGHT, and what it INVENTED.

``HIST-006``'s headline metric is recorded in the ledger as **fabricated-value rate,
not fields-filled**, and that ordering is the whole design of this module: a
reconstruction that fills forty fields by guessing is worse than one that fills four
and refuses the rest, and a harness whose first number is "coverage" would reward the
first. :func:`evaluate` therefore puts :data:`METRIC_FABRICATED_VALUE_RATE` first in
every report, and :meth:`EvaluationReport.headline` returns it.

TWO HARD RULES, ENFORCED IN CODE AND NOT ONLY WRITTEN DOWN
==========================================================

**1. ``NEEDS_DOMAIN_REVIEW`` IS A FIRST-CLASS OUTCOME, NOT A FAILURE.** A great many
things about this corpus are Angel's to decide: whether ``acid``/``base`` can become
``context.electrochemistry.electrolyte`` (which requires BOTH a name and a
concentration), whether the environment is ``operando`` or ``in_situ``, which ``.dat``
column is the primary signal. A harness that scored those as misses would be a
machine for pressuring a future slice into guessing — the exact failure ``CLAUDE.md``
§5 exists to prevent. So a concept the gold standard declares
:attr:`GoldStandard.needs_domain_review_concepts` is reported under
:data:`NEEDS_DOMAIN_REVIEW` and **excluded from every agreement ratio**.

**The one thing that exclusion does NOT cover, stated because collapsing the two
would be a hole big enough to drive the whole feature through:** it excludes a
concept from the AGREEMENT ratios, and **never** from
:data:`METRIC_FABRICATED_VALUE_RATE` or :data:`METRIC_PROVENANCE_COVERAGE`.
``needs_domain_review`` means *the mapping* is a scientific judgement; it does not
mean the *value* may be invented. A candidate whose value no evidence supports is
fabricated whether or not its destination is decided.

**2. GROUND TRUTH MAY NOT BE PRODUCED BY THE THING BEING MEASURED.** A parser that
scores itself is measuring nothing — it will agree with itself by construction, and
the report will read as a pass at any level of wrongness. So the gold standard is a
**committed declarative file** under ``tests/fixtures/bl15/gold/``, written by a
person, and :class:`GoldStandard` REFUSES at construction any document that declares
it was generated from parser output (:func:`load_gold_standard`,
:meth:`GoldStandard.__post_init__`). There is deliberately **no function anywhere in
this module that takes an** :class:`Observed` **and returns a** :class:`GoldStandard`,
and ``test_bl15_evaluate.py`` asserts that mechanically over this module's own type
hints rather than trusting this paragraph.

**THE COMMITTED GOLD STANDARD IS FOR THE SYNTHETIC FIXTURES, NOT FOR THE REAL
CORPUS.** The real BL15-2 archive is not in this repository (``CLAUDE.md`` §6) and its
scientific ground truth is not ours to declare — the mapping questions are itemised in
``docs/bl15-2-domain-questions-2026-09-16.md`` and are Angel's. A gold standard for it
would be this repository answering them.

EVERY METRIC NAMES THE ARTIFACT IT NEEDS
========================================

:class:`Observed` fields default to ``None``, not to an empty container, and the
distinction is load-bearing: ``None`` means *no producer ran*, and the metric reports
:data:`UNMEASURABLE` with a reason naming what is missing; an empty container means
*a producer ran and found nothing*, which is a MEASURED zero. A harness that reported
0.0 for both would make an unbuilt layer indistinguishable from a broken one — which
is the same defect ``bl15.inventory``'s ``refused`` field exists to prevent one layer
down.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields as dataclass_fields
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import mapping as mapping_registry
from .evidence import (
    CONCEPTS,
    DETERMINISM_INFERRED,
    DETERMINISM_NORMALIZED,
    DETERMINISM_READ,
    RUN_CANDIDATE_SOURCE_TYPES,
    SOURCE_TYPES,
)

__all__ = [
    "GOLD_DIR",
    "MEASURED",
    "NEEDS_DOMAIN_REVIEW",
    "UNMEASURABLE",
    "CandidateValue",
    "EvaluationReport",
    "GoldStandard",
    "MetricResult",
    "Observed",
    "evaluate",
    "load_gold_standard",
    "METRIC_ORDER",
]


def _repo_root() -> Path:
    """Walk up until the vendored official schema is found.

    Deliberately a local copy of ``workspace._find_repo_root`` rather than an import
    of it: ``bl15`` is the LOWEST layer of the historical-import stack and
    ``workspace`` is the largest module in the application. Importing it here to
    borrow one four-line function would make a reader-level package depend on the
    whole record engine, which is the coupling this package's layering exists to
    avoid. The duplication is noted so it reads as a decision rather than an
    oversight.
    """
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[4]


#: Where committed gold standards live. Declarative JSON, human-authored.
GOLD_DIR = _repo_root() / "tests" / "fixtures" / "bl15" / "gold"

# --- metric outcomes ---------------------------------------------------------

#: The metric was computed against a present artifact.
MEASURED = "measured"
#: The artifact the metric needs is absent. **Not a zero.**
UNMEASURABLE = "unmeasurable"
#: A first-class outcome. See rule 1 in the module docstring.
NEEDS_DOMAIN_REVIEW = "needs_domain_review"

#: The producer RAN and produced an empty set, so the check was reachable and had
#: nothing to check. **A third outcome, and it exists because the alternatives are both
#: wrong.**
#:
#: Reporting :data:`MEASURED` with a rate of 0.0 or a coverage of 1.0 is the shape
#: ``CLAUDE.md`` §11 names "0 failures was VACUOUSLY TRUE" — and for the two HARD
#: honesty metrics it is the worst possible instance of it, because a regression in
#: classification or relation that yields no candidates at all would publish
#: ``fabricated_value_rate 0.0 ✓`` and a green report.
#:
#: Reporting :data:`UNMEASURABLE` is closer but still conflates two states that
#: :class:`Observed` deliberately keeps apart: ``candidates=None`` means the producer was
#: never built, and ``candidates=()`` means it ran and found nothing. Those have different
#: causes and different next actions.
#:
#: Like an unmeasurable honesty metric, a vacuous one carries ``passed=None`` and so makes
#: :attr:`EvaluationReport.passed` **False**. "There was nothing to check" must never read
#: the same as "nothing was invented".
VACUOUS = "vacuous"

OUTCOMES: frozenset[str] = frozenset(
    {MEASURED, UNMEASURABLE, NEEDS_DOMAIN_REVIEW, VACUOUS}
)

# --- metric ids, in report order --------------------------------------------
#
# The order is the message. Fabrication first, provenance second, confident-mapping
# correctness third: all three are about whether a number can be TRUSTED. Only then
# does the report say how much was recovered.

METRIC_FABRICATED_VALUE_RATE = "fabricated_value_rate"
METRIC_PROVENANCE_COVERAGE = "provenance_coverage"
METRIC_INCORRECT_CONFIDENT_MAPPING_RATE = "incorrect_confident_mapping_rate"
METRIC_MAPPING_COVERAGE = "mapping_coverage_by_status"
METRIC_SOURCE_CLASSIFICATION = "source_classification_agreement"
METRIC_FILENAME_TOKENS = "filename_token_extraction"
METRIC_LEGACY_NUMBER = "legacy_number_extraction"
METRIC_POTENTIAL_MAGNITUDE = "potential_magnitude_extraction"
METRIC_POTENTIAL_REFERENCE = "potential_reference_basis_extraction"
METRIC_FILTER = "filter_extraction"
METRIC_CYCLING_STATE = "cycling_state_extraction"
METRIC_SAMPLE_GROUPING = "sample_or_electrode_grouping"
METRIC_SCAN_GROUPING = "scan_to_measurement_grouping"
METRIC_MACRO_RELATIONSHIPS = "macro_to_measurement_relationships"
METRIC_README_INHERITANCE = "readme_inheritance_coverage"
METRIC_DUPLICATE_RECOGNITION = "duplicate_source_recognition"
METRIC_CONFLICT_PRESERVATION = "conflict_preservation"
METRIC_UNKNOWN_TOKEN_PRESERVATION = "unknown_token_preservation"
METRIC_TECHNIQUE_MAPPING = "technique_mapping"
METRIC_LINK_MAPPING = "relationship_link_mapping"

METRIC_ORDER: tuple[str, ...] = (
    METRIC_FABRICATED_VALUE_RATE,
    METRIC_PROVENANCE_COVERAGE,
    METRIC_INCORRECT_CONFIDENT_MAPPING_RATE,
    METRIC_MAPPING_COVERAGE,
    METRIC_SOURCE_CLASSIFICATION,
    METRIC_FILENAME_TOKENS,
    METRIC_LEGACY_NUMBER,
    METRIC_POTENTIAL_MAGNITUDE,
    METRIC_POTENTIAL_REFERENCE,
    METRIC_FILTER,
    METRIC_CYCLING_STATE,
    METRIC_SAMPLE_GROUPING,
    METRIC_SCAN_GROUPING,
    METRIC_MACRO_RELATIONSHIPS,
    METRIC_README_INHERITANCE,
    METRIC_DUPLICATE_RECOGNITION,
    METRIC_CONFLICT_PRESERVATION,
    METRIC_UNKNOWN_TOKEN_PRESERVATION,
    METRIC_TECHNIQUE_MAPPING,
    METRIC_LINK_MAPPING,
)

#: The metrics whose violation FAILS the harness, and the value each must hold.
#: Both are honesty properties, not quality ones — which is why they, and only
#: they, are hard. Coverage is reported and never gates.
HARD_REQUIREMENTS: Mapping[str, float] = {
    METRIC_FABRICATED_VALUE_RATE: 0.0,
    METRIC_PROVENANCE_COVERAGE: 1.0,
}


# --- what a reconstruction proposes -----------------------------------------


@dataclass(frozen=True)
class CandidateValue:
    """ONE value a reconstruction proposes, and everything needed to audit it.

    This is deliberately NOT ``SourceEvidence``. Evidence is what a source SAYS;
    a candidate is what a reconstruction PROPOSES, and the gap between the two is
    exactly where a fabrication lives. :attr:`evidence_ids` is the bridge, and a
    candidate that names none is fabricated by definition.
    """

    candidate_id: str
    concept: str
    value: Any
    determinism: str = DETERMINISM_READ
    #: ``SourceEvidence.evidence_id`` values this candidate rests on.
    evidence_ids: tuple[str, ...] = ()
    #: May be ``None`` when the candidate expects to inherit them from its
    #: evidence; :data:`METRIC_PROVENANCE_COVERAGE` resolves either way.
    source_path: str | None = None
    locator: str | None = None
    #: REQUIRED when :attr:`determinism` is not ``read``, and checked against the
    #: gold standard's declared rule names.
    normalization_rule: str | None = None
    #: The official ISAAC path this candidate is proposed for, when one is
    #: decided. ``None`` is normal: see ``bl15-2-schema-mapping-analysis`` §5.
    official_path: str | None = None
    #: Set by the producer when the MAPPING is a scientific judgement.
    needs_domain_review: bool = False

    def to_state(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "concept": self.concept,
            "value": self.value,
            "determinism": self.determinism,
            "evidence_ids": list(self.evidence_ids),
            "source_path": self.source_path,
            "locator": self.locator,
            "normalization_rule": self.normalization_rule,
            "official_path": self.official_path,
            "needs_domain_review": self.needs_domain_review,
        }


@dataclass(frozen=True)
class Observed:
    """What a reconstruction actually produced. **``None`` means ABSENT.**

    Every field defaults to ``None`` and not to ``()``/``{}``, because "the layer
    that produces this has not been built" and "the layer ran and found nothing"
    must reach a different metric outcome. See the module docstring.
    """

    #: ``{archive_path: source_type}``.
    source_classification: Mapping[str, str] | None = None
    #: ``{archive_path: {concept: raw_literal}}``.
    filename_tokens: Mapping[str, Mapping[str, Any]] | None = None
    candidates: tuple[CandidateValue, ...] | None = None
    #: ``SourceEvidence.to_state()`` dicts. The support set for every candidate.
    evidence: tuple[Mapping[str, Any], ...] | None = None
    #: One entry per candidate RUN: ``{"run_id", "source_path", "source_type"}``.
    #: The metric that reads it asserts 0 macros and 0 scan exports became runs.
    run_sources: tuple[Mapping[str, Any], ...] | None = None
    #: ``{measurement_stem: (scan archive_path, ...)}``.
    measurement_groups: Mapping[str, Sequence[str]] | None = None
    #: ``{macro archive_path: (declared target stem, ...)}``.
    macro_declarations: Mapping[str, Sequence[str]] | None = None
    #: ``{group_key: (archive_path, ...)}``.
    sample_groups: Mapping[str, Sequence[str]] | None = None
    #: ``{archive_path: (concept, ...)}`` inherited from beamtime-scope sources.
    inherited_beamtime_context: Mapping[str, Sequence[str]] | None = None
    duplicate_groups: tuple[tuple[str, ...], ...] | None = None
    #: Conflict NAMES that survived; the gold standard declares which must.
    conflicts: tuple[str, ...] | None = None
    #: ``{archive_path: (unrecognised token, ...)}``.
    unknown_tokens: Mapping[str, Sequence[str]] | None = None
    #: ``{"official_path", "value"}`` for the technique decision, or ``None``.
    technique: Mapping[str, Any] | None = None
    #: ``{"rel", "basis", "from", "to"}`` per proposed relationship.
    links: tuple[Mapping[str, Any], ...] | None = None


# --- the gold standard -------------------------------------------------------


class GoldStandardRefused(ValueError):
    """A gold standard this harness will not accept as ground truth."""


@dataclass(frozen=True)
class GoldStandard:
    """DECLARED expectations for one named corpus. Written by a person.

    :attr:`provenance` is validated, not decorative. See rule 2 in the module
    docstring: a gold standard that admits to being generated from parser output is
    refused at construction, because such a document cannot measure the parser that
    produced it and a report built on one would read as a pass regardless.
    """

    corpus_id: str
    provenance: Mapping[str, Any]
    #: Concepts whose MAPPING is Angel's decision. Excluded from agreement
    #: ratios; never from fabrication or provenance.
    needs_domain_review_concepts: frozenset[str] = frozenset()
    #: Named normalisation rules a ``normalized`` candidate may cite.
    declared_normalization_rules: frozenset[str] = frozenset()

    source_classification: Mapping[str, str] | None = None
    filename_tokens: Mapping[str, Mapping[str, Any]] | None = None
    legacy_numbers: Mapping[str, str] | None = None
    #: Paths that must yield NO legacy number. The negative half, and it is the
    #: half a happy-path gold standard omits.
    legacy_numbers_absent: tuple[str, ...] = ()
    potential_magnitudes: Mapping[str, str] | None = None
    #: **Paths whose reference basis must be left UNRESOLVED.** Reported as
    #: recovered when the observation leaves it absent — see
    #: :data:`METRIC_POTENTIAL_REFERENCE`.
    potential_reference_unresolved: tuple[str, ...] = ()
    #: Paths where a basis IS evidenced, and what it is.
    potential_reference_resolved: Mapping[str, str] | None = None
    filters: Mapping[str, str] | None = None
    cycling_states: Mapping[str, str] | None = None
    sample_groups: Mapping[str, Sequence[str]] | None = None
    measurement_groups: Mapping[str, Sequence[str]] | None = None
    #: ``{macro archive_path: (declared target stem, ...)}``.
    macro_declarations: Mapping[str, Sequence[str]] | None = None
    #: Paths expected to inherit beamtime-scope context, and which concepts.
    readme_inheritance: Mapping[str, Sequence[str]] | None = None
    duplicate_groups: tuple[tuple[str, ...], ...] | None = None
    #: Conflict names that MUST survive a reconstruction, by name.
    known_conflicts: tuple[str, ...] = ()
    unknown_tokens: Mapping[str, Sequence[str]] | None = None
    technique: Mapping[str, Any] | None = None
    links: tuple[Mapping[str, Any], ...] | None = None

    def __post_init__(self) -> None:
        if not self.corpus_id or not isinstance(self.corpus_id, str):
            raise GoldStandardRefused("a gold standard must name its corpus")
        _refuse_parser_authored(self.provenance)
        for concept in self.needs_domain_review_concepts:
            if concept not in CONCEPTS:
                raise GoldStandardRefused(f"unknown concept: {concept!r}")
        if self.source_classification:
            for path, source_type in self.source_classification.items():
                if source_type not in SOURCE_TYPES:
                    raise GoldStandardRefused(
                        f"{path!r} declares unknown source_type {source_type!r}"
                    )

    def to_state(self) -> dict:
        return {
            "corpus_id": self.corpus_id,
            "provenance": dict(self.provenance),
            "needs_domain_review_concepts": sorted(self.needs_domain_review_concepts),
            "declared_normalization_rules": sorted(self.declared_normalization_rules),
        }


#: Keys a gold-standard document may NOT carry at all. Each of them, present,
#: would mean the ground truth came from the thing under measurement — so they are
#: refused by NAME rather than by value, which is the same reasoning as the
#: frontend palette guard: the first one arrives looking harmless.
_PARSER_AUTHORSHIP_KEYS: frozenset[str] = frozenset(
    {
        "generator",
        "generated_by",
        "parser_id",
        "derived_from_observed",
        "produced_by_parser",
        "harvested_from",
    }
)


def _refuse_parser_authored(provenance: Mapping[str, Any] | None) -> None:
    """Refuse a gold standard that was, or may have been, machine-derived.

    Three independent checks, because each catches something the others cannot: a
    document that DECLARES human authorship (so silence is not assent), a document
    that declares it was NOT generated from parser output (so the claim is explicit
    and greppable), and the absence of any key naming a generator (so a document
    that simply forgot to lie is still caught).
    """
    if not isinstance(provenance, Mapping):
        raise GoldStandardRefused(
            "a gold standard must carry a provenance block saying who wrote it"
        )
    present = sorted(set(provenance) & _PARSER_AUTHORSHIP_KEYS)
    if present:
        raise GoldStandardRefused(
            "a gold standard may not be produced by the thing it measures; this "
            f"one carries {present}"
        )
    if provenance.get("authored_by_human") is not True:
        raise GoldStandardRefused(
            "a gold standard must declare `authored_by_human: true`; a parser that "
            "scores itself is measuring nothing"
        )
    if provenance.get("generated_from_parser_output") is not False:
        raise GoldStandardRefused(
            "a gold standard must declare `generated_from_parser_output: false`"
        )


def load_gold_standard(path: Path) -> GoldStandard:
    """Read a committed declarative gold standard. Refuses a machine-derived one.

    Unknown top-level keys are refused rather than ignored: a gold standard with a
    typo in a field name would otherwise silently declare NOTHING about that
    dimension, and the report would show it as UNMEASURABLE — which reads as "the
    producer is not built" rather than "the expectation is misspelled".

    **A key beginning with ``_`` is a COMMENT and is dropped.** JSON has no comment
    syntax, and a declarative expectation whose reasoning lives in a separate
    document gets edited without it — which is how a gold standard quietly becomes
    a description of whatever the parser currently does. The prefix cannot collide
    with a dataclass field, so this loosens nothing about the typo guard above: a
    misspelled ``potential_magnitudes`` still fails, because it does not start with
    an underscore.
    """
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GoldStandardRefused(
            f"the gold standard could not be read: {type(exc).__name__}"
        ) from exc
    if not isinstance(document, Mapping):
        raise GoldStandardRefused("a gold standard must be a JSON object")

    document = {k: v for k, v in document.items() if not k.startswith("_")}
    known = {f.name for f in dataclass_fields(GoldStandard)}
    unknown = sorted(set(document) - known)
    if unknown:
        raise GoldStandardRefused(f"unknown gold-standard keys: {unknown}")

    kwargs: dict[str, Any] = dict(document)
    for key in ("needs_domain_review_concepts", "declared_normalization_rules"):
        if key in kwargs:
            kwargs[key] = frozenset(kwargs[key])
    for key in (
        "legacy_numbers_absent",
        "potential_reference_unresolved",
        "known_conflicts",
    ):
        if key in kwargs:
            kwargs[key] = tuple(kwargs[key])
    if "duplicate_groups" in kwargs and kwargs["duplicate_groups"] is not None:
        kwargs["duplicate_groups"] = tuple(
            tuple(group) for group in kwargs["duplicate_groups"]
        )
    if "links" in kwargs and kwargs["links"] is not None:
        kwargs["links"] = tuple(dict(link) for link in kwargs["links"])
    try:
        return GoldStandard(**kwargs)
    except TypeError as exc:
        # A document with no `provenance` at all would otherwise raise a bare
        # `TypeError` about a missing argument — which reads as a defect in this
        # loader rather than as "this gold standard does not say who wrote it",
        # and would escape a caller catching `GoldStandardRefused`.
        raise GoldStandardRefused(
            f"the gold standard is missing a required declaration: {exc}"
        ) from exc


# --- results -----------------------------------------------------------------


@dataclass(frozen=True)
class MetricResult:
    """ONE number, what it needed to compute it, and what it does NOT claim."""

    metric_id: str
    outcome: str
    #: What must be present in :class:`Observed` for this metric to exist. Stated
    #: on every result, including the measured ones, so a reader never has to work
    #: out why something is unmeasurable.
    required_artifact: str
    #: Why it is unmeasurable, or why it needs domain review. ``None`` when
    #: measured.
    reason: str | None = None
    recovered: int = 0
    missed: int = 0
    extra: int = 0
    #: The ratio, when the metric has one. ``None`` for an unmeasurable metric.
    value: float | None = None
    #: A hard requirement, when this metric has one.
    must_be: float | None = None
    #: ``None`` when the metric does not gate or could not be computed.
    passed: bool | None = None
    #: Scientist-readable specifics: which paths were missed, which conflict
    #: names survived. Never a scientific value.
    detail: tuple[str, ...] = ()
    #: Concepts or items set aside as Angel's decision, excluded from the ratio.
    deferred: tuple[str, ...] = ()

    def to_state(self) -> dict:
        return {
            "metric_id": self.metric_id,
            "outcome": self.outcome,
            "required_artifact": self.required_artifact,
            "reason": self.reason,
            "recovered": self.recovered,
            "missed": self.missed,
            "extra": self.extra,
            "value": self.value,
            "must_be": self.must_be,
            "passed": self.passed,
            "detail": list(self.detail),
            "deferred": list(self.deferred),
        }


@dataclass(frozen=True)
class EvaluationReport:
    corpus_id: str
    metrics: tuple[MetricResult, ...]

    def headline(self) -> MetricResult:
        """The fabricated-value rate, which is deliberately ``metrics[0]``."""
        head = self.metrics[0]
        assert head.metric_id == METRIC_FABRICATED_VALUE_RATE, (
            "the report's first metric must be the fabricated-value rate; "
            f"found {head.metric_id!r}"
        )
        return head

    def by_id(self) -> dict[str, MetricResult]:
        return {m.metric_id: m for m in self.metrics}

    @property
    def hard_failures(self) -> tuple[str, ...]:
        return tuple(
            m.metric_id
            for m in self.metrics
            if m.metric_id in HARD_REQUIREMENTS and m.passed is False
        )

    @property
    def passed(self) -> bool:
        """False if any HARD metric failed, **could not be computed, or was vacuous**.

        An unmeasurable honesty metric is not a pass. "We could not check whether
        anything was invented" must never read the same as "nothing was invented" —
        that conflation is the defect this whole module is shaped around.

        **A VACUOUS one is not a pass either, and that was wrong here until 2026-09-16.**
        Both hard metrics hand-wrote a zero-denominator branch that bypassed
        :func:`_ratio` and returned 0.0 / 1.0, so a reconstruction that produced NO
        candidates published a fully green report — ``passed: true``, no hard failures,
        headline ``fabricated_value_rate 0.0 ✓``. Found by independent review. Nothing
        needs to change here, because this loop already fails on ``passed is not True``;
        what changed is that the two metrics now return :data:`VACUOUS` with
        ``passed=None`` instead of inventing a favourable number.
        """
        for metric_id in HARD_REQUIREMENTS:
            result = self.by_id().get(metric_id)
            if result is None or result.passed is not True:
                return False
        return True

    @property
    def unmeasurable(self) -> tuple[str, ...]:
        return tuple(m.metric_id for m in self.metrics if m.outcome == UNMEASURABLE)

    @property
    def vacuous(self) -> tuple[str, ...]:
        """Metrics whose producer ran and produced nothing. Reported SEPARATELY.

        Folding these into :attr:`unmeasurable` would lose the distinction
        :class:`Observed` exists to keep — "never built" against "ran and found
        nothing" — which have different causes and different next actions.
        """
        return tuple(m.metric_id for m in self.metrics if m.outcome == VACUOUS)

    @property
    def needs_domain_review(self) -> tuple[str, ...]:
        return tuple(
            m.metric_id for m in self.metrics if m.outcome == NEEDS_DOMAIN_REVIEW
        )

    def to_state(self) -> dict:
        return {
            "corpus_id": self.corpus_id,
            "passed": self.passed,
            "headline": self.headline().to_state(),
            "hard_failures": list(self.hard_failures),
            "unmeasurable": list(self.unmeasurable),
            "vacuous": list(self.vacuous),
            "needs_domain_review": list(self.needs_domain_review),
            "metrics": [m.to_state() for m in self.metrics],
        }


# --- metric helpers ----------------------------------------------------------


def _unmeasurable(metric_id: str, artifact: str, reason: str) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        outcome=UNMEASURABLE,
        required_artifact=artifact,
        reason=reason,
        must_be=HARD_REQUIREMENTS.get(metric_id),
        passed=None,
    )


def _vacuous(metric_id: str, artifact: str, reason: str) -> MetricResult:
    """The producer ran and produced nothing, so this metric had nothing to check.

    ``passed=None``, which makes a HARD metric fail the report — see :data:`VACUOUS`.
    """
    return MetricResult(
        metric_id=metric_id,
        outcome=VACUOUS,
        required_artifact=artifact,
        reason=reason,
        must_be=HARD_REQUIREMENTS.get(metric_id),
        value=None,
        passed=None,
    )


def _ratio(recovered: int, total: int) -> float | None:
    """``None`` for an empty denominator, never ``1.0``.

    A vacuous ratio reported as a pass is the shape §11 records as "0 failures was
    VACUOUSLY TRUE": the check was never reached and read as a clean result.
    """
    if total <= 0:
        return None
    return recovered / total


def _mapping_agreement(
    metric_id: str,
    artifact: str,
    expected: Mapping[str, Any] | None,
    observed: Mapping[str, Any] | None,
    *,
    label: str,
) -> MetricResult:
    """Recovered / missed / extra over a ``{key: value}`` expectation."""
    if expected is None:
        return MetricResult(
            metric_id=metric_id,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason=f"the gold standard declares no expectation for {label}",
        )
    if observed is None:
        return _unmeasurable(
            metric_id, artifact, f"{artifact} is absent; no producer supplied {label}"
        )

    recovered: list[str] = []
    missed: list[str] = []
    for key, want in expected.items():
        got = observed.get(key, _MISSING)
        if got is _MISSING:
            missed.append(f"{key}: not reported (expected {want!r})")
        elif got == want:
            recovered.append(key)
        else:
            missed.append(f"{key}: reported {got!r}, expected {want!r}")
    extra = sorted(set(observed) - set(expected))

    return MetricResult(
        metric_id=metric_id,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=len(recovered),
        missed=len(missed),
        extra=len(extra),
        value=_ratio(len(recovered), len(expected)),
        detail=tuple(missed) + tuple(f"{k}: not expected" for k in extra),
    )


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


_MISSING = _Missing()


def _normalise_groups(
    groups: Mapping[str, Sequence[str]] | None,
) -> dict[str, tuple[str, ...]] | None:
    if groups is None:
        return None
    return {key: tuple(sorted(values)) for key, values in groups.items()}


# --- the three honesty metrics ----------------------------------------------


def _evidence_index(
    evidence: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    if evidence is None:
        return {}
    return {
        str(item.get("evidence_id")): item
        for item in evidence
        if item.get("evidence_id")
    }


def _candidate_support(
    candidate: CandidateValue,
    index: Mapping[str, Mapping[str, Any]],
    declared_rules: frozenset[str],
) -> tuple[bool, str]:
    """Is this candidate's value supported by evidence? With the reason if not.

    "Supported" is defined per determinism kind rather than as one loose rule,
    because the three kinds make three different promises:

    * ``read`` — the source SAYS this, literally. So a referenced evidence item's
      ``raw_literal`` or ``normalized_value`` must equal the candidate's value.
    * ``normalized`` — a NAMED stored rule produced it. The rule must be one the
      gold standard declares, so a producer cannot legitimise any transformation by
      inventing a rule name for it.
    * ``inferred`` — a stored rule over several sources produced it. It must name a
      rule and rest on at least one real evidence item.

    A candidate naming no evidence at all is fabricated under every kind, which is
    the case this metric exists for.
    """
    if not candidate.evidence_ids:
        return False, f"{candidate.candidate_id}: names no evidence"
    resolved = [index[eid] for eid in candidate.evidence_ids if eid in index]
    if not resolved:
        return (
            False,
            f"{candidate.candidate_id}: names evidence "
            f"{list(candidate.evidence_ids)} that does not exist",
        )

    if candidate.determinism == DETERMINISM_READ:
        for item in resolved:
            if str(item.get("raw_literal")) == str(candidate.value):
                return True, ""
            if item.get("normalized_value") == candidate.value:
                return True, ""
        return (
            False,
            f"{candidate.candidate_id}: claims to be READ but no cited source "
            "states this value",
        )

    if candidate.determinism in (DETERMINISM_NORMALIZED, DETERMINISM_INFERRED):
        if not candidate.normalization_rule:
            return (
                False,
                f"{candidate.candidate_id}: {candidate.determinism} with no named "
                "rule",
            )
        if candidate.normalization_rule not in declared_rules:
            return (
                False,
                f"{candidate.candidate_id}: cites undeclared rule "
                f"{candidate.normalization_rule!r}",
            )
        return True, ""

    return False, f"{candidate.candidate_id}: unknown determinism"


def _fabricated_value_rate(gold: GoldStandard, observed: Observed) -> MetricResult:
    artifact = "observed.candidates + observed.evidence"
    if observed.candidates is None:
        return _unmeasurable(
            METRIC_FABRICATED_VALUE_RATE,
            artifact,
            "observed.candidates is absent; nothing proposed a value, so whether "
            "anything was invented cannot be checked",
        )
    if observed.evidence is None:
        return _unmeasurable(
            METRIC_FABRICATED_VALUE_RATE,
            artifact,
            "observed.evidence is absent; every candidate would score as "
            "fabricated, which would be a measurement of the harness and not of "
            "the reconstruction",
        )

    index = _evidence_index(observed.evidence)
    fabricated: list[str] = []
    for candidate in observed.candidates:
        supported, why = _candidate_support(
            candidate, index, gold.declared_normalization_rules
        )
        if not supported:
            fabricated.append(why)

    total = len(observed.candidates)
    if total == 0:
        # NOT 0.0. A reconstruction that produced no candidate at all invented nothing
        # only in the sense that it did nothing — and this is the headline honesty
        # metric, so a vacuous 0.0 here would turn a total producer failure into a green
        # report. See VACUOUS.
        return _vacuous(
            METRIC_FABRICATED_VALUE_RATE,
            artifact,
            "the reconstruction ran and produced no candidate with a value, so there "
            "was nothing to check for fabrication. A rate of 0 over zero candidates is "
            "not evidence that nothing was invented.",
        )
    rate = len(fabricated) / total
    return MetricResult(
        metric_id=METRIC_FABRICATED_VALUE_RATE,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=total - len(fabricated),
        missed=len(fabricated),
        value=rate,
        must_be=0.0,
        passed=rate == 0.0,
        detail=tuple(sorted(fabricated)),
    )


def _provenance_coverage(gold: GoldStandard, observed: Observed) -> MetricResult:
    artifact = "observed.candidates + observed.evidence"
    if observed.candidates is None or observed.evidence is None:
        return _unmeasurable(
            METRIC_PROVENANCE_COVERAGE,
            artifact,
            "observed.candidates and observed.evidence are both required; "
            "provenance coverage over an absent candidate set is not 1.0, it is "
            "unknown",
        )
    index = _evidence_index(observed.evidence)
    without: list[str] = []
    for candidate in observed.candidates:
        cited = [index[e] for e in candidate.evidence_ids if e in index]
        path = candidate.source_path or next(
            (item.get("source_path") for item in cited if item.get("source_path")),
            None,
        )
        locator = candidate.locator or next(
            (item.get("locator") for item in cited if item.get("locator")), None
        )
        if not path or not locator:
            without.append(
                f"{candidate.candidate_id}: "
                f"{'no source path' if not path else 'no locator'}"
            )

    total = len(observed.candidates)
    if total == 0:
        # NOT 1.0. This metric's own UNMEASURABLE reason already makes the argument —
        # "provenance coverage over an absent candidate set is not 1.0, it is unknown" —
        # and that argument applies verbatim to an EMPTY set. It was written for `None`
        # and not applied to `()`.
        return _vacuous(
            METRIC_PROVENANCE_COVERAGE,
            artifact,
            "the reconstruction ran and produced no candidate, so there was nothing "
            "whose provenance could be checked. Coverage of 1.0 over zero candidates is "
            "not evidence that every value can name its source.",
        )
    coverage = (total - len(without)) / total
    return MetricResult(
        metric_id=METRIC_PROVENANCE_COVERAGE,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=total - len(without),
        missed=len(without),
        value=coverage,
        must_be=1.0,
        passed=coverage == 1.0,
        detail=tuple(sorted(without)),
    )


def _incorrect_confident_mapping_rate(
    gold: GoldStandard, observed: Observed
) -> MetricResult:
    """Candidates asserting a DETERMINISTIC reading whose warrant does not hold.

    Deliberately NOT one of :data:`HARD_REQUIREMENTS`, and the reason is worth
    stating: a confident mapping whose warrant fails is a real defect, but the
    warrant this harness can check is only the mechanical one — that the source
    says what the candidate claims, and that a normalisation cites a declared rule.
    Whether a mechanically-warranted mapping is scientifically right is Angel's,
    and gating on a check that cannot see that would be claiming more than the
    number supports.
    """
    artifact = "observed.candidates + observed.evidence"
    if observed.candidates is None or observed.evidence is None:
        return _unmeasurable(
            METRIC_INCORRECT_CONFIDENT_MAPPING_RATE,
            artifact,
            "observed.candidates and observed.evidence are both required",
        )
    index = _evidence_index(observed.evidence)
    confident = [
        c
        for c in observed.candidates
        if c.determinism in (DETERMINISM_READ, DETERMINISM_NORMALIZED)
    ]
    wrong: list[str] = []
    for candidate in confident:
        supported, why = _candidate_support(
            candidate, index, gold.declared_normalization_rules
        )
        if not supported:
            wrong.append(why)

    rate = _ratio(len(wrong), len(confident))
    return MetricResult(
        metric_id=METRIC_INCORRECT_CONFIDENT_MAPPING_RATE,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=len(confident) - len(wrong),
        missed=len(wrong),
        value=0.0 if rate is None else rate,
        must_be=0.0,
        passed=len(wrong) == 0,
        detail=tuple(sorted(wrong)),
    )


def _mapping_coverage(gold: GoldStandard, observed: Observed) -> MetricResult:
    """**A BREAKDOWN BY STATUS, DELIBERATELY NOT A RATIO.** ``value`` stays ``None``.

    Measured over the committed registry (``bl15.mapping``): of the 45 corpus
    concepts, **only 6 are proposable** (2 ``deterministic`` + 4 ``normalized``),
    **14** need a domain owner, **24** have no official field at all, and **1** is
    blocked by this build (``assets[]`` requires ``sha256``, which historical import
    never computes).

    A "fields mapped" percentage over those numbers would read as **87% failure**,
    and it would be measuring the SCHEMA's coverage of one scientist's naming
    convention while looking like a verdict on the reconstruction. Worse, it would
    improve if a future slice started forcing concepts into
    ``system.configuration`` — which the mapping analysis §6.2 forbids by name
    ("a decision disguised as a default"). So this metric reports counts and
    refuses to divide them.

    It is also the one metric here whose ``required_artifact`` is **not an
    observation**: it describes the registry, which is committed. A reader must not
    mistake it for something the reconstruction did or did not achieve, and the
    ``reason`` string says so on every report.

    The one thing it DOES judge is registry integrity:
    :func:`mapping.registry_paths_exist` re-walks the vendored schema and returns
    any registry path the schema no longer declares. Non-empty is a real
    truthfulness defect — the registry pointing at a field that does not exist —
    and it is reported with ``passed=False``. It is not one of
    :data:`HARD_REQUIREMENTS`, because those two are properties of the
    RECONSTRUCTION and this is a property of the repository, already pinned by
    ``bl15.mapping``'s own tests.
    """
    counts = mapping_registry.coverage()
    missing_paths = mapping_registry.registry_paths_exist()
    proposable = sum(
        counts.get(status, 0) for status in mapping_registry.PROPOSABLE_STATUSES
    )
    detail = [f"{status}: {counts[status]}" for status in sorted(mapping_registry.MAPPING_STATUSES)]
    detail.append(f"proposable (deterministic + normalized): {proposable}")
    detail.append(f"concepts examined: {counts['examined']} of {counts['concepts_total']}")
    if counts.get("not_examined"):
        detail.append(
            f"concepts the registry has not examined: {counts['not_examined']}"
        )
    detail.extend(
        f"REGISTRY POINTS AT A PATH THE SCHEMA DOES NOT DECLARE: {path}"
        for path in missing_paths
    )
    return MetricResult(
        metric_id=METRIC_MAPPING_COVERAGE,
        outcome=MEASURED,
        required_artifact="bl15.mapping.MAPPINGS (the committed registry, NOT an "
        "observation)",
        reason="a breakdown, not a ratio: `not_expressible` and "
        "`needs_domain_review` are correct descriptions of what the official "
        "schema can and cannot take from this corpus, and dividing them into a "
        "coverage percentage would report the schema's shape as the "
        "reconstruction's failure",
        recovered=proposable,
        missed=counts.get(mapping_registry.STATUS_NEEDS_DOMAIN_REVIEW, 0),
        extra=counts.get(mapping_registry.STATUS_NOT_EXPRESSIBLE, 0)
        + counts.get(mapping_registry.STATUS_BLOCKED_BY_BUILD, 0),
        value=None,
        passed=not missing_paths,
        detail=tuple(detail),
        deferred=tuple(
            concept
            for concept, entry in sorted(mapping_registry.MAPPINGS.items())
            if entry.status == mapping_registry.STATUS_NEEDS_DOMAIN_REVIEW
        ),
    )


# --- the recovery metrics ----------------------------------------------------


def _source_classification(gold: GoldStandard, observed: Observed) -> MetricResult:
    return _mapping_agreement(
        METRIC_SOURCE_CLASSIFICATION,
        "observed.source_classification",
        gold.source_classification,
        observed.source_classification,
        label="source classification",
    )


def _filename_tokens(gold: GoldStandard, observed: Observed) -> MetricResult:
    """Per CONCEPT, and with Angel's concepts set aside rather than scored.

    Reported as one metric whose ``detail`` names every per-concept miss, because
    a scientist reading this wants "which concepts did it get" and not nineteen
    separate numbers.
    """
    artifact = "observed.filename_tokens"
    if gold.filename_tokens is None:
        return MetricResult(
            metric_id=METRIC_FILENAME_TOKENS,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason="the gold standard declares no filename-token expectation",
        )
    if observed.filename_tokens is None:
        return _unmeasurable(
            METRIC_FILENAME_TOKENS, artifact, "observed.filename_tokens is absent"
        )

    recovered = missed = extra = 0
    detail: list[str] = []
    deferred: set[str] = set()
    for path, want_tokens in gold.filename_tokens.items():
        got_tokens = observed.filename_tokens.get(path) or {}
        for concept, want in want_tokens.items():
            if concept in gold.needs_domain_review_concepts:
                deferred.add(f"{path}:{concept}")
                continue
            got = got_tokens.get(concept, _MISSING)
            if got is _MISSING:
                missed += 1
                detail.append(f"{path}: {concept} missed (expected {want!r})")
            elif got == want:
                recovered += 1
            else:
                missed += 1
                detail.append(
                    f"{path}: {concept} reported {got!r}, expected {want!r}"
                )
        for concept in sorted(set(got_tokens) - set(want_tokens)):
            if concept in gold.needs_domain_review_concepts:
                deferred.add(f"{path}:{concept}")
                continue
            extra += 1
            detail.append(f"{path}: {concept} not expected")

    return MetricResult(
        metric_id=METRIC_FILENAME_TOKENS,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=recovered,
        missed=missed,
        extra=extra,
        value=_ratio(recovered, recovered + missed),
        detail=tuple(detail),
        deferred=tuple(sorted(deferred)),
    )


def _legacy_numbers(gold: GoldStandard, observed: Observed) -> MetricResult:
    artifact = "observed.filename_tokens[*][legacy_run_or_file_number]"
    if gold.legacy_numbers is None:
        return MetricResult(
            metric_id=METRIC_LEGACY_NUMBER,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason="the gold standard declares no legacy-number expectation",
        )
    if observed.filename_tokens is None:
        return _unmeasurable(
            METRIC_LEGACY_NUMBER, artifact, "observed.filename_tokens is absent"
        )

    got_numbers = {
        path: tokens.get("legacy_run_or_file_number")
        for path, tokens in observed.filename_tokens.items()
    }
    result = _mapping_agreement(
        METRIC_LEGACY_NUMBER,
        artifact,
        gold.legacy_numbers,
        {k: v for k, v in got_numbers.items() if v is not None},
        label="legacy numbers",
    )
    # THE NEGATIVE HALF. A reader that invents a legacy number for `readme.txt`
    # scores perfectly on the positive expectation alone.
    false_positives = [
        path for path in gold.legacy_numbers_absent if got_numbers.get(path) is not None
    ]
    if false_positives:
        return MetricResult(
            metric_id=result.metric_id,
            outcome=result.outcome,
            required_artifact=result.required_artifact,
            recovered=result.recovered,
            missed=result.missed + len(false_positives),
            extra=result.extra,
            value=_ratio(
                result.recovered,
                result.recovered + result.missed + len(false_positives),
            ),
            detail=result.detail
            + tuple(
                f"{path}: reported a legacy number where the gold standard says "
                "there is none"
                for path in false_positives
            ),
        )
    return result


def _simple_token_metric(
    metric_id: str,
    concept: str,
    expected: Mapping[str, str] | None,
    observed: Observed,
    *,
    label: str,
) -> MetricResult:
    artifact = f"observed.filename_tokens[*][{concept}]"
    if expected is None:
        return MetricResult(
            metric_id=metric_id,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason=f"the gold standard declares no expectation for {label}",
        )
    if observed.filename_tokens is None:
        return _unmeasurable(metric_id, artifact, "observed.filename_tokens is absent")
    got = {
        path: tokens[concept]
        for path, tokens in observed.filename_tokens.items()
        if concept in tokens
    }
    return _mapping_agreement(metric_id, artifact, expected, got, label=label)


def _potential_reference(gold: GoldStandard, observed: Observed) -> MetricResult:
    """**Reported SEPARATELY from the magnitude, and this is the reason.**

    A filename says ``850mV`` and says nothing about what it is measured against.
    The official schema's ``context.electrochemistry.potential_scale`` has six
    members and **no "unknown"**, so the honest act on this corpus is to leave the
    field ABSENT — and ``potential_vs_RHE.rhe_basis`` carries ``not_reported`` and
    ``not_convertible_no_reference_offset`` for saying exactly that
    (``docs/bl15-2-schema-mapping-analysis-2026-09-16.md`` §3).

    So a harness that scored an absent basis as a MISS would be a machine for
    pressuring a future slice into picking one, and the number it produced would
    improve as the reconstruction got less truthful. Here, leaving it unresolved
    where the gold standard says it is unresolved counts as RECOVERED.
    """
    artifact = "observed.filename_tokens[*][potential_reference_basis]"
    if observed.filename_tokens is None:
        return _unmeasurable(
            METRIC_POTENTIAL_REFERENCE, artifact, "observed.filename_tokens is absent"
        )
    got = {
        path: tokens.get("potential_reference_basis")
        for path, tokens in observed.filename_tokens.items()
    }

    recovered: list[str] = []
    detail: list[str] = []
    for path in gold.potential_reference_unresolved:
        if got.get(path) in (None, ""):
            recovered.append(path)
        else:
            detail.append(
                f"{path}: reported basis {got[path]!r} where the gold standard "
                "says the source states none — the schema's own answer is to "
                "leave it absent"
            )
    for path, want in (gold.potential_reference_resolved or {}).items():
        if got.get(path) == want:
            recovered.append(path)
        else:
            detail.append(
                f"{path}: reported {got.get(path)!r}, expected {want!r} (a basis "
                "the source does state)"
            )

    total = len(gold.potential_reference_unresolved) + len(
        gold.potential_reference_resolved or {}
    )
    if total == 0:
        return MetricResult(
            metric_id=METRIC_POTENTIAL_REFERENCE,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason="the gold standard declares no reference-basis expectation",
        )
    return MetricResult(
        metric_id=METRIC_POTENTIAL_REFERENCE,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=len(recovered),
        missed=total - len(recovered),
        value=_ratio(len(recovered), total),
        detail=tuple(detail),
    )


def _grouping_metric(
    metric_id: str,
    artifact: str,
    expected: Mapping[str, Sequence[str]] | None,
    observed_groups: Mapping[str, Sequence[str]] | None,
    *,
    label: str,
) -> MetricResult:
    return _mapping_agreement(
        metric_id,
        artifact,
        _normalise_groups(expected),
        _normalise_groups(observed_groups),
        label=label,
    )


def _scan_grouping(gold: GoldStandard, observed: Observed) -> MetricResult:
    """Scans grouped under their measurement — and **0 scans becoming runs**.

    The measured real-corpus expectation (characterization §2.3, §2.8): **908**
    ``.dat`` scan children over **94** candidate measurement units, at most **233**
    in one, and **0** of them becoming a Run. Turning each scan into a Run would
    invent ~814 measurements nobody performed, which is why ``scan_export`` is
    absent from ``RUN_CANDIDATE_SOURCE_TYPES`` and why that absence is CHECKED here
    rather than only asserted in a docstring.

    **TWO of the 94 have ZERO scan children**, so a gold standard declaring "every
    measurement has at least one scan" would be wrong about this corpus, and a
    harness that treated an empty group as a miss would penalise the right answer.
    An expected group of ``()`` is matched by an observed group of ``()``, and
    :func:`_ratio` returns ``None`` rather than 1.0 for an empty denominator so a
    vacuous comparison can never read as a pass.
    """
    base = _grouping_metric(
        METRIC_SCAN_GROUPING,
        "observed.measurement_groups (+ observed.run_sources)",
        gold.measurement_groups,
        observed.measurement_groups,
        label="scan-to-measurement grouping",
    )
    if base.outcome != MEASURED or observed.run_sources is None:
        return base
    offenders = sorted(
        str(row.get("source_path"))
        for row in observed.run_sources
        if row.get("source_type") not in RUN_CANDIDATE_SOURCE_TYPES
        and row.get("source_type") == "scan_export"
    )
    if not offenders:
        return base
    return MetricResult(
        metric_id=base.metric_id,
        outcome=MEASURED,
        required_artifact=base.required_artifact,
        recovered=base.recovered,
        missed=base.missed + len(offenders),
        extra=base.extra,
        value=_ratio(base.recovered, base.recovered + base.missed + len(offenders)),
        detail=base.detail
        + tuple(f"{p}: a scan export became a Run candidate" for p in offenders),
    )


def _macro_relationships(gold: GoldStandard, observed: Observed) -> MetricResult:
    """Macro ``newfile`` declarations recovered — and **0 macros becoming runs**.

    The measured real-corpus expectation (characterization §2.2, §2.8): **156**
    ``newfile`` declarations across **60** macro files — 59 ``.mac`` plus
    ``run29``, which has **no extension** and is a macro, so a macro inventory
    built from the extension alone finds 59 and is wrong by one. **95** distinct
    targets, up to **8** declarations in one macro, and **4** macros declaring
    none at all. One macro is not one measurement, so ``macro`` is absent from
    ``RUN_CANDIDATE_SOURCE_TYPES``; that absence is checked against
    ``observed.run_sources`` here, for all three macro source types.
    """
    base = _grouping_metric(
        METRIC_MACRO_RELATIONSHIPS,
        "observed.macro_declarations (+ observed.run_sources)",
        gold.macro_declarations,
        observed.macro_declarations,
        label="macro declarations",
    )
    if base.outcome != MEASURED or observed.run_sources is None:
        return base
    macro_types = {
        "macro",
        "acquisition_method_macro",
        "motor_snapshot_macro",
    }
    offenders = sorted(
        str(row.get("source_path"))
        for row in observed.run_sources
        if row.get("source_type") in macro_types
    )
    if not offenders:
        return base
    return MetricResult(
        metric_id=base.metric_id,
        outcome=MEASURED,
        required_artifact=base.required_artifact,
        recovered=base.recovered,
        missed=base.missed + len(offenders),
        extra=base.extra,
        value=_ratio(base.recovered, base.recovered + base.missed + len(offenders)),
        detail=base.detail
        + tuple(f"{p}: a macro became a Run candidate" for p in offenders),
    )


def _duplicate_recognition(gold: GoldStandard, observed: Observed) -> MetricResult:
    artifact = "observed.duplicate_groups"
    if gold.duplicate_groups is None:
        return MetricResult(
            metric_id=METRIC_DUPLICATE_RECOGNITION,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason="the gold standard declares no duplicate-group expectation",
        )
    if observed.duplicate_groups is None:
        return _unmeasurable(
            METRIC_DUPLICATE_RECOGNITION, artifact, "observed.duplicate_groups is absent"
        )
    want = {tuple(sorted(group)) for group in gold.duplicate_groups}
    got = {tuple(sorted(group)) for group in observed.duplicate_groups}
    recovered = want & got
    missed = want - got
    extra = got - want
    return MetricResult(
        metric_id=METRIC_DUPLICATE_RECOGNITION,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=len(recovered),
        missed=len(missed),
        extra=len(extra),
        value=_ratio(len(recovered), len(want)),
        detail=tuple(f"missed group: {list(g)}" for g in sorted(missed))
        + tuple(f"unexpected group: {list(g)}" for g in sorted(extra)),
    )


def _conflict_preservation(gold: GoldStandard, observed: Observed) -> MetricResult:
    """**How many known conflicts SURVIVED, BY NAME — never by count.**

    Scored as a set intersection, and the distinction is not pedantry: a
    reconstruction that lost all five known conflicts and invented five different
    ones would pass a count check perfectly. ``recovered`` here is
    ``|want ∩ got|``, ``missed`` names each lost conflict with a ``LOST:`` prefix,
    and an unexpected conflict lands in ``extra`` rather than being credited.

    **The real corpus has FIVE named conflict classes** (characterization §2.5,
    §2.6, §2.6a, §2.7, §3.7), and the harness scores them individually because
    they are independent facts about the archive:

    1. **Duplicate legacy number 32** — two distinct acquisition files carry it.
    2. **Internal ``#F`` versus filename, ×4.** §2.6 named ONE file and read as a
       typo; §2.6a corrected it to **four consecutive files in one sample group
       making the identical substitution** (``beforeCycling`` internally,
       ``after1500Cycling`` externally) — a systematic rename after acquisition,
       which is a different and stronger finding. For that group the macro, the
       header and the filename are THREE sources, at least two of which disagree,
       so a surface must be able to show a three-way disagreement and a
       plausible-sounding "trust the header, it is closer to the instrument" rule
       would be wrong here.
    3. **Macro intent versus acquired** — 9 declared-never-acquired and 9
       acquired-never-declared, and the two sets are not independent.
    4. **The notes' broad claim versus their own sample section** — *"In ALL
       experiments we used <one alkaline electrolyte at a stated
       concentration>"* sitting above an acid sample, in a document
       whose own preparation section says otherwise.
    5. **``ffilter35``** — a literal that must survive its own normalisation. The
       normalised reading (filter 35) sits BESIDE the literal; replacing it would
       destroy the only thing that lets a scientist disagree.

    *"This is a conflict, not a defect to repair."* A reconstruction that silently
    picked a winner would score well on every other metric in this report, which
    is exactly why survival is a metric of its own.
    """
    artifact = "observed.conflicts"
    if not gold.known_conflicts:
        return MetricResult(
            metric_id=METRIC_CONFLICT_PRESERVATION,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason="the gold standard names no known conflicts",
        )
    if observed.conflicts is None:
        return _unmeasurable(
            METRIC_CONFLICT_PRESERVATION, artifact, "observed.conflicts is absent"
        )
    want = set(gold.known_conflicts)
    got = set(observed.conflicts)
    survived = sorted(want & got)
    lost = sorted(want - got)
    return MetricResult(
        metric_id=METRIC_CONFLICT_PRESERVATION,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=len(survived),
        missed=len(lost),
        extra=len(got - want),
        value=_ratio(len(survived), len(want)),
        detail=tuple(f"survived: {name}" for name in survived)
        + tuple(f"LOST: {name}" for name in lost),
    )


def _unknown_token_preservation(gold: GoldStandard, observed: Observed) -> MetricResult:
    """An unrecognised token must be REPORTED, not dropped.

    ``CONCEPT_UNKNOWN_TOKEN`` is a first-class concept for the reason
    ``bl15.evidence`` states: silently dropping the third of a filename a profile
    does not recognise leaves the scientist unable to see what was passed over.
    """
    return _grouping_metric(
        METRIC_UNKNOWN_TOKEN_PRESERVATION,
        "observed.unknown_tokens",
        gold.unknown_tokens,
        observed.unknown_tokens,
        label="unknown-token preservation",
    )


def _technique_mapping(gold: GoldStandard, observed: Observed) -> MetricResult:
    """``system.technique`` = ``HERFD-XAS``, which the schema's own enum contains.

    A fair deterministic expectation: the notes name HERFD and the enum carries
    ``HERFD-XAS`` verbatim (schema-mapping analysis §1). ``XAS`` is the weaker
    reading and is also in the enum, so an observation choosing it is recorded as
    a miss with both values named rather than as a silent pass.
    """
    artifact = "observed.technique"
    if gold.technique is None:
        return MetricResult(
            metric_id=METRIC_TECHNIQUE_MAPPING,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason="the gold standard declares no technique expectation",
        )
    if observed.technique is None:
        return _unmeasurable(
            METRIC_TECHNIQUE_MAPPING, artifact, "observed.technique is absent"
        )
    matched = all(
        observed.technique.get(key) == value for key, value in gold.technique.items()
    )
    return MetricResult(
        metric_id=METRIC_TECHNIQUE_MAPPING,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=1 if matched else 0,
        missed=0 if matched else 1,
        value=1.0 if matched else 0.0,
        detail=()
        if matched
        else (
            f"reported {dict(observed.technique)!r}, expected "
            f"{dict(gold.technique)!r}",
        ),
    )


def _link_mapping(gold: GoldStandard, observed: Observed) -> MetricResult:
    """``_again`` → ``replica_of``/``replicate_preparation``, and same-sample links.

    Both enum values are in the schema verbatim (schema-mapping analysis §1), and
    the ``_again`` token is the evidence — so this is a scorable deterministic
    mapping rather than something to mark unmeasurable. The same-sample link rests
    on the second numeric token being the sample instance, which the domain owner
    **CONFIRMED** on 2026-09-17 (`DEC-47`) — this docstring used to call it "domain
    question 1" and that question is closed. A gold standard may now declare those
    links on the token's meaning; it should still leave them out where it is unsure
    of the TARGET, which is a different uncertainty.
    """
    artifact = "observed.links"
    if gold.links is None:
        return MetricResult(
            metric_id=METRIC_LINK_MAPPING,
            outcome=NEEDS_DOMAIN_REVIEW,
            required_artifact=artifact,
            reason="the gold standard declares no relationship expectation",
        )
    if observed.links is None:
        return _unmeasurable(METRIC_LINK_MAPPING, artifact, "observed.links is absent")

    def key(link: Mapping[str, Any]) -> tuple:
        return (
            link.get("rel"),
            link.get("basis"),
            link.get("from"),
            link.get("to"),
        )

    want = {key(link) for link in gold.links}
    got = {key(link) for link in observed.links}
    recovered = want & got
    missed = want - got
    extra = got - want
    return MetricResult(
        metric_id=METRIC_LINK_MAPPING,
        outcome=MEASURED,
        required_artifact=artifact,
        recovered=len(recovered),
        missed=len(missed),
        extra=len(extra),
        value=_ratio(len(recovered), len(want)),
        # `sorted` over the raw keys would compare `None` with `str` and raise,
        # because `rel`/`basis`/`from`/`to` are each optional on the wire; and an
        # earlier version sorted `map(str, ...)` and then did `list(k)` on the
        # resulting STRING, printing a list of individual characters. Both are
        # avoided by sorting on a stringified key and formatting the tuple.
        detail=tuple(
            f"missed link: {k}"
            for k in sorted(missed, key=lambda t: tuple(str(x) for x in t))
        )
        + tuple(
            f"unexpected link: {k}"
            for k in sorted(extra, key=lambda t: tuple(str(x) for x in t))
        ),
    )


# --- the entry point ---------------------------------------------------------


def evaluate(gold: GoldStandard, observed: Observed) -> EvaluationReport:
    """Measure one reconstruction against one DECLARED gold standard.

    The fabricated-value rate is first in :attr:`EvaluationReport.metrics` and is
    what :meth:`EvaluationReport.headline` returns. Nothing here mutates either
    argument, and nothing here writes a file.
    """
    if not isinstance(gold, GoldStandard):
        raise TypeError("gold must be a GoldStandard read from a committed file")
    if not isinstance(observed, Observed):
        raise TypeError("observed must be an Observed")

    metrics = [
        _fabricated_value_rate(gold, observed),
        _provenance_coverage(gold, observed),
        _incorrect_confident_mapping_rate(gold, observed),
        _mapping_coverage(gold, observed),
        _source_classification(gold, observed),
        _filename_tokens(gold, observed),
        _legacy_numbers(gold, observed),
        _simple_token_metric(
            METRIC_POTENTIAL_MAGNITUDE,
            "potential_magnitude",
            gold.potential_magnitudes,
            observed,
            label="potential magnitudes",
        ),
        _potential_reference(gold, observed),
        _simple_token_metric(
            METRIC_FILTER, "filter", gold.filters, observed, label="filters"
        ),
        _simple_token_metric(
            METRIC_CYCLING_STATE,
            "cycling_state",
            gold.cycling_states,
            observed,
            label="cycling states",
        ),
        _grouping_metric(
            METRIC_SAMPLE_GROUPING,
            "observed.sample_groups",
            gold.sample_groups,
            observed.sample_groups,
            label="sample/electrode grouping",
        ),
        _scan_grouping(gold, observed),
        _macro_relationships(gold, observed),
        _grouping_metric(
            METRIC_README_INHERITANCE,
            "observed.inherited_beamtime_context",
            gold.readme_inheritance,
            observed.inherited_beamtime_context,
            label="README inheritance coverage",
        ),
        _duplicate_recognition(gold, observed),
        _conflict_preservation(gold, observed),
        _unknown_token_preservation(gold, observed),
        _technique_mapping(gold, observed),
        _link_mapping(gold, observed),
    ]

    ordered = {m.metric_id: m for m in metrics}
    assert set(ordered) == set(METRIC_ORDER), (
        "every metric in METRIC_ORDER must be produced exactly once; "
        f"missing {sorted(set(METRIC_ORDER) - set(ordered))}, "
        f"unexpected {sorted(set(ordered) - set(METRIC_ORDER))}"
    )
    return EvaluationReport(
        corpus_id=gold.corpus_id,
        metrics=tuple(ordered[metric_id] for metric_id in METRIC_ORDER),
    )
