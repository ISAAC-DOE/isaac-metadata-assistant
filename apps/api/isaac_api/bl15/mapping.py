"""Corpus concept -> official ISAAC v1.05 path. A REGISTRY, not a converter.

**This module maps and refuses to map. It never decides a scientific question**, and
five of its outcomes are ways of saying "not here" — which is the point. A registry
that only recorded successes would tell a scientist nothing about the part of a
historical corpus the schema has no home for, and this corpus has a lot of it.

The analysis behind every entry, with each path and enum walked out of
``schema/isaac_record_v1.json`` rather than recalled, is
``docs/bl15-2-schema-mapping-analysis-2026-09-16.md``. Read it before changing a row.

**THE SCHEMA IS THE AUTHORITY** (``CLAUDE.md`` §1). Nothing here validates, accepts, or
refuses a value on the schema's behalf: :func:`mapping_for` answers *"is there a path for
this concept, and what is the warrant"*, and the official validator answers whether a
value at that path is any good. Two different questions, kept apart on purpose.

**The most important thing in this file is §3 of that analysis, so it is restated here:
the schema already carries vocabulary for saying a value is NOT KNOWN, and this corpus's
central gap is exactly that.** A filename says ``850mV`` and says nothing about what it is
measured against. ``context.electrochemistry.potential_scale``'s six members are each a
specific claim with no "unknown" member — so the honest act is to leave that field
**absent**, not to pick one. Meanwhile
``context.electrochemistry.potential_vs_RHE.rhe_basis`` offers ``not_reported`` and
``not_convertible_no_reference_offset`` verbatim, with ``value_V`` nullable. So *"no RHE
value, and here is why"* is a complete, valid statement, and §5's no-guessing rule is
satisfiable without leaving the record silent about why.

**A magnitude with no scale is therefore the CORRECT mapping of this corpus, not an
incomplete one**, and :data:`MAPPINGS` says so with two separate entries rather than one
entry with a hole in it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import evidence as ev

# --- mapping status ----------------------------------------------------------
#
# All five are FIRST-CLASS OUTCOMES. None of them is a failure, and a consumer that
# treated the last three as "not done yet" would be wrong about all three.

#: A source states it and one official path takes it as-is.
STATUS_DETERMINISTIC = "deterministic"
#: A source states it and a NAMED rule carries it across (``mV`` -> V, ``p`` -> decimal
#: point, a doubled-prefix typo). The rule travels with the value; the literal survives.
STATUS_NORMALIZED = "normalized"
#: The schema has a path and choosing among its options is a scientific judgement this
#: repository may not make. **Not a gap to be closed by a later slice** — it is closed by
#: a domain owner answering, and `docs/bl15-2-domain-questions-2026-09-16.md` is the ask.
STATUS_NEEDS_DOMAIN_REVIEW = "needs_domain_review"
#: The official schema has no field for this concept at all. Preserved as source evidence.
#: **Inventing a path is forbidden** (``CLAUDE.md`` §5); requesting one is upstream's
#: decision (§1).
STATUS_NOT_EXPRESSIBLE = "not_expressible"
#: The schema HAS a path and THIS BUILD cannot reach it. Distinct from
#: :data:`STATUS_NOT_EXPRESSIBLE` because the remedy is different: an application change,
#: not a schema request. Today this is ``assets[]`` and nothing else — see
#: :data:`ASSETS_BLOCKED_REASON`.
STATUS_BLOCKED_BY_BUILD = "blocked_by_build"

MAPPING_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_DETERMINISTIC,
        STATUS_NORMALIZED,
        STATUS_NEEDS_DOMAIN_REVIEW,
        STATUS_NOT_EXPRESSIBLE,
        STATUS_BLOCKED_BY_BUILD,
    }
)

#: Statuses that may carry a value toward a candidate. The other three carry a REASON.
PROPOSABLE_STATUSES: frozenset[str] = frozenset(
    {STATUS_DETERMINISTIC, STATUS_NORMALIZED}
)


ASSETS_BLOCKED_REASON = (
    "The official schema requires both assets[].uri and assets[].sha256. This build "
    "does not publish either for a historical source: a manifest digest is only ever "
    "what the scientist stated, never one this application computed, and the location "
    "of a file inside an archive is not a URI anything outside this working area could "
    "resolve. So a historical file cannot become an official asset entry without this "
    "application asserting two things it has no standing to assert. The asset "
    "content_role vocabulary otherwise fits this corpus exactly (raw_data_pointer, "
    "reduction_product, calibration_reference), which is why this is named as a "
    "boundary rather than left to surface as a failing export."
)

#: ~~"this build computes no digest for any historical source — not even for a file it
#: reads"~~ — **THAT WAS THE REASON ABOVE UNTIL 2026-09-16, AND IT WENT FALSE ON THIS
#: BRANCH.** Found by independent review, which measured 14 member digests computed
#: while this sentence was being served to a scientist on the same payload.
#:
#: The archive walk computes a SHA-256 per member, and it must: content hashing is the
#: only thing that stops the corpus doubling (94 measurements became 181 without it) and
#: the only correct way to recognise the 96 duplicate groups. So the digest now EXISTS,
#: and the blocker is no longer its absence.
#:
#: **The conclusion did not change and the reason had to.** What blocks an asset entry is
#: a POLICY about publishing, not an arithmetic gap: a manifest ``sha256`` is "what the
#: scientist said", and a computed one published in the same field would put two meanings
#: behind one name — which is the argument ``historical_import`` has made since
#: ``HIST-001``. The ``uri`` half is new here and is the firmer of the two: an archive
#: member's path resolves nowhere outside this working area.
#:
#: This is the sibling of the claim the wiring slice corrected one module away, and it is
#: another instance of §15's incomplete-correction-sweep pattern — made worse by
#: ``test_bl15_mapping.py``'s pinning this constant to ONE home, which guaranteed the
#: false text was byte-identical in both places it was served.
#:
#: **Consequence worth naming rather than leaving implied:** a future slice COULD reach
#: ``assets[]`` for an archive member, by deciding that a computed digest may be published
#: in a field distinguishable from a stated one, and by giving the member a resolvable
#: URI. Both are decisions; neither is blocked by a missing number.
_ASSETS_BLOCKED_REASON_CORRECTION = "2026-09-16"

TEMPERATURE_ABSENT_REASON = (
    "context.temperature_K is required by the official schema whenever a context block "
    "is present, and this corpus states no temperature anywhere — not in the beamtime "
    "README, not in the notes, not in any acquisition header. A candidate assembled "
    "from these sources is therefore incomplete by the schema's own rule. That is the "
    "correct outcome: room temperature is the obvious guess, and 298 must not be "
    "defaulted into context.temperature_K, because a plausible number in a required "
    "field is a fabricated measurement that nothing downstream can tell from a "
    "measured one."
)

CYCLING_STATE_NO_FIELD_REASON = (
    "The official schema has no field for electrochemical cycling history "
    "(beforeCycling / after1500Cycling / after1stCycling). It is the single most "
    "important experimental variable in this corpus, which makes it the strongest "
    "schema-request case the corpus produced — and a schema request is upstream's "
    "decision, not this repository's. measurement.series[].conditions is a schema-legal "
    "candidate home for it as a per-series condition; nothing here places it there."
)

SYSTEM_CONFIGURATION_CAUTION = (
    "The schema describes system.configuration as 'THE designated open extension "
    "namespace' for instrument- and station-specific configuration that does not "
    "generalize across facilities — naming slits, pass energies and logbook fields, "
    "which is what a filter index and a spectrometer crystal are. So a natural home "
    "exists. BUT the six system.configuration.* fields are recorded as unclassified "
    "with the domain owner's classification outstanding, and no write route in this "
    "build accepts them. Candidate home; NOT a settled mapping and not writable today."
)


@dataclass(frozen=True)
class ConceptMapping:
    """What the official schema can and cannot do with ONE corpus concept.

    :attr:`official_path` is ``None`` for every status outside
    :data:`PROPOSABLE_STATUSES` **except** :data:`STATUS_NEEDS_DOMAIN_REVIEW` and
    :data:`STATUS_BLOCKED_BY_BUILD`, where a path exists and the obstacle is elsewhere.
    Naming the path in those two cases is deliberate: a scientist asked to decide between
    ``operando`` and ``in_situ`` is owed the field the decision lands in.
    """

    concept: str
    status: str
    #: Dotted official path, ``[]`` marking an array. ``None`` when none exists.
    official_path: str | None
    #: WHY this status — in a sentence a scientist reads, not a code.
    reason: str
    #: The named rule, required when :attr:`status` is :data:`STATUS_NORMALIZED`.
    rule: str | None = None
    #: Sibling paths the schema REQUIRES alongside this one, so a consumer can see that
    #: satisfying this mapping is not sufficient on its own. ``electrolyte`` is the case
    #: that makes this field necessary: the schema requires BOTH ``name`` and
    #: ``concentration_M``, and ``acid``/``base`` supplies neither.
    requires_siblings: tuple[str, ...] = ()
    #: Enum members the schema allows here, when it constrains the value. Quoted so a
    #: domain question can be asked as "which of these" rather than open-ended.
    allowed_values: tuple[str, ...] = ()
    #: Candidate homes for a concept with no field of its own. Named, never applied.
    candidate_homes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in MAPPING_STATUSES:
            raise ValueError(f"unknown mapping status: {self.status!r}")
        if self.concept not in ev.CONCEPTS:
            raise ValueError(f"unknown concept: {self.concept!r}")
        if self.status == STATUS_NORMALIZED and not self.rule:
            raise ValueError(f"{self.concept}: normalized mapping needs a rule")
        if self.status in PROPOSABLE_STATUSES and not self.official_path:
            raise ValueError(f"{self.concept}: {self.status} needs an official_path")
        if self.status == STATUS_NOT_EXPRESSIBLE and self.official_path:
            raise ValueError(
                f"{self.concept}: not_expressible must name no official_path"
            )

    @property
    def proposable(self) -> bool:
        """Whether a value at this concept may travel toward a candidate at all.

        Derived, with no field behind it, so it cannot be persisted out of step with
        the status that decides it — the same discipline
        ``historical_import.SemanticCandidate.proposable`` already uses.
        """
        return self.status in PROPOSABLE_STATUSES

    def to_state(self) -> dict:
        return {
            "concept": self.concept,
            "status": self.status,
            "official_path": self.official_path,
            "reason": self.reason,
            "rule": self.rule,
            "requires_siblings": list(self.requires_siblings),
            "allowed_values": list(self.allowed_values),
            "candidate_homes": list(self.candidate_homes),
            "proposable": self.proposable,
        }


# --- the registry ------------------------------------------------------------

_MAPPINGS: tuple[ConceptMapping, ...] = (
    # ---- deterministic ------------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_TIMESTAMP,
        status=STATUS_DETERMINISTIC,
        official_path="timestamps.acquired_start_utc",
        reason=(
            "Each acquisition file states its own start time in its SPEC header. The "
            "epoch line and the date line are two separate statements and are NOT "
            "reconciled here: if they disagree, both are read and the disagreement is "
            "a conflict for a scientist, not an arithmetic problem."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_EPOCH,
        status=STATUS_NORMALIZED,
        official_path="timestamps.acquired_start_utc",
        reason=(
            "The SPEC header states the acquisition instant twice — once as Unix "
            "seconds and once as a formatted local date — and the epoch line is the "
            "one that converts without assuming a timezone, which is why the rule "
            "hangs off it. THE TWO ARE NOT RECONCILED HERE: they are two statements "
            "the file makes, and if they disagree both are read and the disagreement "
            "belongs to a scientist. Choosing the epoch as the mappable one is a "
            "statement about which is convertible, not about which is right."
        ),
        rule="unix_epoch_seconds_to_iso8601_utc",
    ),
    # ---- normalized ---------------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_POTENTIAL_MAGNITUDE,
        status=STATUS_NORMALIZED,
        official_path="context.electrochemistry.potential_setpoint_V",
        reason=(
            "Filenames state a potential magnitude in two unit conventions. The "
            "schema's field is in volts. THE MAGNITUDE IS ALL THAT IS MAPPED HERE — "
            "the electrochemical reference it is measured against is a separate "
            "concept with a separate and usually absent mapping, and collapsing the "
            "two would assert a basis no source states."
        ),
        rule="millivolts_to_volts_and_p_as_decimal_point",
        requires_siblings=("context.electrochemistry.control_mode",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_PH,
        status=STATUS_NORMALIZED,
        official_path="context.electrochemistry.pH",
        reason=(
            "The beamtime notes state a pH for the later oxide samples. The schema "
            "pairs it with pH_basis, whose members are 'measured', 'nominal' and "
            "'buffered_assumed'; a figure quoted beside a hydroxide concentration is "
            "evidenced as nominal, and no source states a basis for any other sample."
        ),
        rule="ph_figure_read_verbatim_basis_nominal_only_where_quoted_with_a_concentration",
        requires_siblings=("context.electrochemistry.pH_basis",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_FLOW_RATE,
        status=STATUS_NORMALIZED,
        official_path="context.transport.feed.flow_rate",
        reason=(
            "The notes state a flow rate for the flow-cell samples. The schema keeps "
            "the unit in a sibling field rather than in the number, so both are "
            "carried; the feed object additionally REQUIRES phase and composition, "
            "which a flow rate alone does not supply."
        ),
        rule="flow_rate_value_and_unit_carried_separately_never_converted",
        requires_siblings=(
            "context.transport.feed.flow_rate_unit",
            "context.transport.feed.phase",
            "context.transport.feed.composition",
        ),
    ),
    # ---- needs domain review ------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_POTENTIAL_REFERENCE,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.electrochemistry.potential_vs_RHE.rhe_basis",
        reason=(
            "THIS IS THE COROLLARY OF THE POTENTIAL MAGNITUDE MAPPING AND THE MOST "
            "CONSEQUENTIAL ENTRY IN THIS REGISTRY. A filename states a magnitude and "
            "says nothing about the basis. potential_scale's six members are each a "
            "specific claim with no 'unknown' member, so that field is left ABSENT "
            "rather than guessed. rhe_basis, by contrast, has vocabulary FOR the "
            "absence: 'not_reported' where no source names a basis, and "
            "'not_convertible_no_reference_offset' where a reference is mentioned but "
            "its offset is not. value_V is nullable, so 'no RHE value, and here is "
            "why' is a complete and valid statement. Which member applies to which "
            "sample group is a domain judgement, because only a scientist can say "
            "whether a note naming RHE for one group covers its neighbours."
        ),
        allowed_values=(
            "measured_direct",
            "derived_calibrated",
            "reported_as_RHE",
            "derived_nominal",
            "in_silico_setpoint",
            "not_convertible_no_pH",
            "not_convertible_no_reference_offset",
            "not_reported",
            "not_applicable",
        ),
        candidate_homes=("context.electrochemistry.potential_scale",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ELECTROLYTE_OR_MEDIUM,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.electrochemistry.electrolyte.name",
        reason=(
            "Filenames say only 'acid' or 'base', which is a medium class and not an "
            "electrolyte name, and the schema REQUIRES both a name and a molar "
            "concentration in the same object. The notes name a specific acid for one "
            "sample; the one sentence that would supply a concentration for the rest "
            "is the corpus's own contradicted broad claim — it asserts a single "
            "hydroxide for ALL experiments while sitting above a sample section "
            "labelled acid, in a document whose preparation steps specify the acid. "
            "So this concept cannot be mapped from a filename at all, and the note "
            "that would complete it is in conflict with the same document."
        ),
        requires_siblings=("context.electrochemistry.electrolyte.concentration_M",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_GAS_CONDITION,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.transport.feed.composition",
        reason=(
            "The notes describe purging an inert gas and saturating the later samples "
            "with it. Whether that is the cell's FEED in the schema's sense — the "
            "transport block is written for flowing reactant feeds — or an atmosphere "
            "belonging in context.thermodynamics.atmosphere, is a judgement about the "
            "experiment rather than about the text."
        ),
        requires_siblings=("context.transport.feed.phase",),
        candidate_homes=("context.thermodynamics.atmosphere",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_NAME,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="sample.material.name",
        reason=(
            "A filename's sample token is the scientist's own shorthand — an electrode "
            "label for some samples and a material description for others. Which of "
            "those two it is decides whether it belongs at sample.material.name or "
            "sample.sample_id, and only the scientist who wrote it can say. The schema "
            "also requires a sample_form alongside, which no filename states."
        ),
        requires_siblings=("sample.sample_form",),
        candidate_homes=("sample.sample_id", "sample.electrode_type"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="sample.sample_id",
        reason=(
            "The second numeric filename token behaves like a sample or electrode "
            "instance, and the grouping it implies agrees with the beamtime notes' own "
            "sample sections. AGREEMENT IS NOT CONFIRMATION: whether that token always "
            "means the instance is the first question in the domain packet, and the "
            "notes could agree with a token that means something else."
        ),
        candidate_homes=("sample.library.sample_no",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_LOADING_OR_THICKNESS,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path=None,
        reason=(
            "One filename slot carries two physically different quantities in this "
            "corpus — an overlayer thickness in nanometres for the oxide samples and a "
            "weight loading in percent for the pellets. The schema has a composition "
            "object and a geometry object and a natural home for neither, so this is "
            "both a mapping question and a question about what the token means."
        ),
        candidate_homes=("sample.composition", "sample.geometry"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ELEMENT,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path=None,
        reason=(
            "The beamtime README names the absorbing element in one line, for the whole "
            "beamtime. The official schema has no absorber-element field; the absorbing "
            "element and edge are recorded as implicit/sidecar-only for the XANES path "
            "and must not be forced into the official record where the schema provides "
            "no valid path."
        ) + " " + SYSTEM_CONFIGURATION_CAUTION,
        candidate_homes=("system.configuration",),
    ),
    # ---- not expressible ----------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_CYCLING_STATE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=CYCLING_STATE_NO_FIELD_REASON,
        candidate_homes=("measurement.series[].conditions",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEFORE_AFTER_STATE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The before/after qualifier is one half of the cycling-state concept and "
            "has no field for the same reason."
        ),
        candidate_homes=("measurement.series[].conditions",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_FILTER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "An attenuator index is beamline-specific instrument state. The official "
            "schema has no field for it. " + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=(
            "measurement.series[].conditions",
            "system.configuration",
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_EMISSION_ENERGY,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The emission energy the spectrometer is parked at is stated by the "
            "acquisition headers and by the macro call, and the official schema has no "
            "field for it. " + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=(
            "measurement.series[].conditions",
            "system.configuration",
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_LEGACY_NUMBER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The leading filename number is the CORPUS'S identifier, not ISAAC's. It "
            "must not be forced into record_id, which the server mints, nor into "
            "sample.sample_id, which identifies a sample rather than a measurement. It "
            "is preserved as source evidence and is the right label to show a "
            "scientist, because it is the handle they already use."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_NEW_SPOT,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Moving to an unexposed spot on the same electrode is a real experimental "
            "act with no schema field. It is not a replicate — the sample is the same "
            "one — so links[].rel = replica_of would be wrong about it."
        ),
        candidate_homes=("measurement.series[].conditions",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_MONOCHROMATOR_CALIBRATION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The README states which foil the monochromator was calibrated against. "
            "There is no calibration field; links[].rel = calibration_of with basis "
            "same_absorber_edge can express the RELATIONSHIP once a calibration record "
            "exists to point at, which this corpus does not contain. "
            + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration", "links[]"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SPECTROMETER_CONFIG,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Slit width, analyser crystal and emission line are exactly the "
            "facility-specific configuration the schema declines to generalize. "
            + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEAMSIZE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Beam dimensions at a stated energy are station configuration. "
            + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_UNKNOWN_TOKEN,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A token no profile recognised has no concept, so it can have no mapping. "
            "IT IS STILL CARRIED: an unrecognised token is preserved as source "
            "evidence and shown to the scientist, because the alternative is dropping "
            "part of a filename silently."
        ),
    ),
    # ---- blocked by build ---------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_SCAN_COMMAND,
        status=STATUS_BLOCKED_BY_BUILD,
        official_path="assets[].uri",
        reason=ASSETS_BLOCKED_REASON,
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ENERGY_GRID,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="measurement.series[].independent_variables[].values",
        reason=(
            "The scan grid is stated literally by the acquisition command and by the "
            "method macro, so the VALUES are evidenced. What the schema needs "
            "alongside them is a channel set with a role for each, and which detector "
            "column carries the primary signal among the many a scan export records is "
            "a domain fact this repository must not choose."
        ),
        requires_siblings=(
            "measurement.series[].series_id",
            "measurement.series[].independent_variables[].name",
            "measurement.series[].independent_variables[].unit",
            "measurement.series[].channels[]",
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_DETECTOR_COLUMN,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="measurement.series[].channels[].name",
        reason=(
            "A scan export names its columns, so the names are evidenced. The schema "
            "requires a role for each from a closed set, and assigning those roles is "
            "a scientific reading of the detector set, not a transcription."
        ),
        requires_siblings=(
            "measurement.series[].channels[].unit",
            "measurement.series[].channels[].role",
        ),
        allowed_values=(
            "primary_signal",
            "measured_response",
            "simulated_observable",
            "derived_signal",
            "auxiliary_signal",
            "control_readback",
            "quality_monitor",
        ),
    ),
    # ---- the acquisition and instrument vocabulary --------------------------
    #
    # Examined together because they share one answer: an acquisition header states a
    # great deal about the INSTRUMENT, and the official schema is deliberately not an
    # instrument log. Each entry below says so in its own terms rather than deferring to
    # a shared note, because a scientist reading one of them should not have to find
    # another to learn why.
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_METHOD,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="system.technique",
        reason=(
            "~~The acquisition-method macro defines a named high-energy-resolution "
            "fluorescence-detected absorption scan … so this is a transcription rather "
            "than a judgement.~~ CORRECTED 2026-09-16, the same day, by the slice that "
            "wired this registry to a route and MEASURED what the concept actually "
            "carries. The reasoning was about what a human reading the corpus knows; "
            "the mapping is about what the readers emit, and those are different. "
            "Measured: from a macro this concept carries THE MACRO'S OWN NAME — the "
            "file a `qdo` includes, or the symbol a `def` block defines — and from a "
            "filename it carries the profile's alias reading, whose normalised values "
            "are lowercase shorthands. NOT ONE OF THOSE IS A MEMBER OF THE SCHEMA'S "
            "TECHNIQUE ENUM, so the old status proposed an off-enum value from every "
            "source, and a proposal at this path is then work a scientist is offered "
            "and cannot complete. Two further reasons it is a judgement and not a "
            "transcription: one alias normalises to a DETECTION MODE, which the enum "
            "has no member for at all and which is not a technique; and the strongest "
            "evidence for the real technique is a word in the beamtime document's "
            "TITLE, which no reader in this build reads as a technique statement. So "
            "the enum member is a scientist's to choose, and the options are named "
            "below so that choice is one word."
        ),
        allowed_values=("XAS", "HERFD-XAS", "XES", "RIXS"),
        requires_siblings=("system.domain",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_REPEAT_MARKER,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="links[].rel",
        reason=(
            "A repeat qualifier on an otherwise identical filename is the corpus "
            "saying 'this is the same measurement again', and the schema has exactly "
            "that relationship — replica_of, with basis replicate_preparation. But a "
            "link needs a TARGET RECORD, and whether the earlier acquisition is a "
            "replicate or a failed first attempt that should not be linked at all is a "
            "scientific reading. Note the contrast with a new-spot qualifier, which "
            "looks similar and is NOT a replicate: the sample is the same one."
        ),
        requires_siblings=("links[].target", "links[].basis"),
        allowed_values=("replica_of", "follows", "same_sample_as"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_QUALITY_NOTE,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="measurement.qc.notes",
        reason=(
            "The beamtime notes carry the scientist's own remarks about which "
            "acquisitions were poor, which sample misbehaved, and which were repeated. "
            "The prose has a home. THE VERDICT DOES NOT FOLLOW FROM IT: qc.status is a "
            "closed set of four, and reading a human's aside as 'compromised' or "
            "'failed' is a scientific classification this repository may not perform. "
            "A record already carries the stronger constraint that a status must have "
            "evidence behind it."
        ),
        requires_siblings=("measurement.qc.status",),
        allowed_values=("valid", "compromised", "failed", "pending"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_PREPARATION,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="sample.material.provenance",
        reason=(
            "The notes describe ink preparation, dropcasting and electrode assembly at "
            "length. The schema has a provenance string and a notes string on the "
            "material, so there is a home — but the preparation described is "
            "beamtime-wide prose covering several samples, and deciding how much of it "
            "is provenance OF ONE SAMPLE is a scoping judgement, not an extraction."
        ),
        candidate_homes=("sample.material.notes",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ECHEM_PROCEDURE,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.electrochemistry.notes",
        reason=(
            "The notes tabulate the electrochemical program step by step, including an "
            "impedance-compensation step whose parameters the schema models properly in "
            "its ir_compensation object rather than as prose. So part of this concept "
            "has a STRUCTURED home and part has only a notes field, and which rows are "
            "which is a reading of the protocol."
        ),
        candidate_homes=(
            "context.electrochemistry.ir_compensation.method",
            "context.electrochemistry.control_mode",
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEAMTIME_DATES,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path=None,
        reason=(
            "The notes state the beamtime window. The schema's timestamps are per "
            "record — an acquisition's own start and end — and a campaign window is "
            "neither. Writing it into a record's acquired_start_utc would claim a "
            "measurement began when the beamtime did."
        ),
        candidate_homes=("timestamps.revision_note",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEAMTIME_PURPOSE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The scientific aim of the campaign is stated in the notes' own words. "
            "There is no purpose or abstract field; tags is a free array and would "
            "reduce a paragraph to keywords, which loses the statement rather than "
            "recording it. Preserved as source evidence."
        ),
        candidate_homes=("tags",),
    ),
    # ---- instrument state: real, stated, and not the schema's business ------
    ConceptMapping(
        concept=ev.CONCEPT_MOTOR_POSITION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "An acquisition header records roughly a hundred and eighty motor "
            "positions. They are genuine instrument state and the schema has no field "
            "for any of them. " + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_POSITION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Stage coordinates are how the corpus distinguishes one spot on an "
            "electrode from another, which makes them scientifically load-bearing here "
            "and still gives them no schema field. The library block holds plate "
            "coordinates for combinatorial samples, which is a different thing from a "
            "stage position and must not be reused for it."
        ) + " " + SYSTEM_CONFIGURATION_CAUTION,
        candidate_homes=("system.configuration",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_COUNTING_TIME,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Dwell time per point is stated by the acquisition header and by the macro "
            "call. It is an acquisition parameter with no schema field; as a per-series "
            "operating condition it has a schema-legal candidate home."
        ),
        candidate_homes=("measurement.series[].conditions",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SCAN_COUNT,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "How many scans a macro asked for is intent; how many scan files exist is "
            "fact, and in this corpus THEY DISAGREE. Neither has a schema field, and "
            "mapping either one would quietly pick a side of a real conflict."
        ),
        candidate_homes=("measurement.series[].conditions",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_POINT_COUNT,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The number of points in a scan is a property OF the series values, not a "
            "separate field. If the values are ever carried, the count is implied by "
            "them; recording it alongside would create a second place for one fact to "
            "be wrong."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_EDGE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The absorbing element and its edge are implicit/sidecar-only for this "
            "technique path and must not be forced into the official record while the "
            "schema provides no valid field. That is a standing project rule, not a "
            "judgement made here."
        ) + " " + SYSTEM_CONFIGURATION_CAUTION,
        candidate_homes=("system.configuration",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_DRY_STATE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A dry or as-received measurement is a condition with no schema field. It "
            "interacts with the environment enum — an ex-situ reading is plausible for "
            "these — but the enum describes the MEASUREMENT context and this token "
            "describes the sample's state, and conflating them would assert something "
            "no source states."
        ),
        candidate_homes=("measurement.series[].conditions",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_STEP_NUMBER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A step index refers to a position in the electrochemical program, which "
            "the notes tabulate and the schema does not model. It is the join key "
            "between a filename and a human note row, which makes it valuable as "
            "evidence and still not a record field."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_TRIGGER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A trigger command in a macro is the handshake between the acquisition and "
            "the potentiostat. It explains how the two instruments were synchronised "
            "and asserts nothing about the sample, so there is nothing for it to map "
            "to. It matters for relationship reconstruction, where it marks where one "
            "measurement ends and the next begins."
        ),
    ),
    # ---- structural and provenance-only: examined and deliberately refused --
    ConceptMapping(
        concept=ev.CONCEPT_SPEC_USER_STRING,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "REFUSED ON PURPOSE, AND THIS IS THE ONE ENTRY THAT WOULD BE ACTIVELY "
            "HARMFUL TO 'FIX'. An acquisition header carries the account string the "
            "beamline software was running under. The schema does have an uploader "
            "field — and it is SERVER-STAMPED, requires a verified trust basis that no "
            "verifier in this build mints, and is therefore absent from every record "
            "this deployment produces. Copying a beamline account string into it would "
            "manufacture exactly the attribution the trust boundary exists to withhold. "
            "It stays raw source evidence, and it is never an ISAAC identity or actor."
        ),
        candidate_homes=(),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SPEC_FILE_DECLARATION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The name an acquisition file declares for ITSELF, internally. It is not a "
            "value to map — it is the ANCHOR for conflict detection, because in this "
            "corpus an internal declaration and the external filename disagree about "
            "the experimental state of the sample. Mapping it anywhere would settle "
            "that disagreement by accident."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_TARGET,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The measurement name a macro DECLARES it is about to write. It is intent, "
            "and in this corpus nine declared targets were never acquired while nine "
            "acquisitions were never declared. It is a relationship key, not a field."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_NOTE_FILE_NUMBER_ROW,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A row from the human file-number table is the scientist's own independent "
            "mapping from a file number to a condition. Its VALUE is as corroboration "
            "and as a cross-check against the filesystem — which is a relationship "
            "question — and the individual concepts inside such a row have their own "
            "entries in this registry."
        ),
    ),
)

MAPPINGS: dict[str, ConceptMapping] = {m.concept: m for m in _MAPPINGS}


def mapping_for(concept: str) -> ConceptMapping | None:
    """The registry entry for one concept, or ``None`` if the registry is silent.

    **``None`` is not the same as :data:`STATUS_NOT_EXPRESSIBLE`.** An explicit
    ``not_expressible`` entry is a measured finding — somebody read the schema and
    established there is no field. ``None`` means nobody has looked yet. A consumer that
    treated them alike would report unexamined concepts as settled, so
    :func:`unmapped_concepts` exists to keep the difference visible.
    """
    return MAPPINGS.get(concept)


def unmapped_concepts() -> tuple[str, ...]:
    """Concepts this registry has NOT examined, sorted.

    Deliberately exposed rather than left implicit: it is the honest measure of how
    much of a corpus's vocabulary the registry has actually been reasoned about, and it
    should be quoted alongside any claim about mapping coverage.
    """
    return tuple(sorted(ev.CONCEPTS - set(MAPPINGS)))


def coverage() -> dict[str, int]:
    """Counts per status, plus the unexamined remainder. For reports, not for gating."""
    out = {status: 0 for status in sorted(MAPPING_STATUSES)}
    for m in MAPPINGS.values():
        out[m.status] += 1
    out["examined"] = len(MAPPINGS)
    out["not_examined"] = len(unmapped_concepts())
    out["concepts_total"] = len(ev.CONCEPTS)
    return out


# --- the schema, read rather than recalled -----------------------------------


@lru_cache(maxsize=1)
def _schema() -> dict:
    root = Path(__file__).resolve().parents[4]
    return json.loads(
        (root / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def official_paths() -> frozenset[str]:
    """Every dotted path the vendored official schema declares, ``[]`` marking an array.

    Walked out of the schema file at runtime. **Nothing in this module transcribes a
    path list**, so a schema refresh moves this set and :func:`registry_paths_exist`
    fails rather than the registry quietly pointing at a field that no longer exists.
    """
    out: set[str] = set()

    def walk(node: object, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        props = node.get("properties")
        if isinstance(props, dict):
            for key, child in props.items():
                path = f"{prefix}.{key}" if prefix else key
                out.add(path)
                walk(child, path)
                if isinstance(child, dict) and isinstance(child.get("items"), dict):
                    out.add(f"{path}[]")
                    walk(child["items"], f"{path}[]")

    walk(_schema(), "")
    return frozenset(out)


def registry_paths_exist() -> tuple[str, ...]:
    """Registry paths the official schema does NOT declare, sorted. Empty is correct.

    The guard that makes this registry checkable rather than merely asserted. It covers
    ``official_path`` AND ``requires_siblings`` AND ``candidate_homes`` — a sibling or a
    candidate home naming a field that does not exist would be exactly as misleading as
    a bad primary path, and a scientist sent to decide between two paths deserves both
    to be real.
    """
    declared = official_paths()
    missing: set[str] = set()
    for m in MAPPINGS.values():
        for path in (
            (m.official_path,) + m.requires_siblings + m.candidate_homes
        ):
            if path and path not in declared:
                missing.add(path)
    return tuple(sorted(missing))
