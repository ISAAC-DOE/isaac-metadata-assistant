"""The ONE representation every BL15 reader emits, and the concept vocabulary.

**WHY A SEPARATE LAYER FROM THE SCHEMA.** A filename token, a SPEC header line
and a sentence in a beamtime document are three different kinds of statement
about the same measurement, and none of them is an ISAAC field value. Mapping
them to official paths is a decision with a domain owner
(``docs/bl15-2-domain-questions-2026-09-16.md``); reading them is not. Keeping
the two apart is what lets a source be read completely while its mapping is
still unresolved — which is the normal state of this corpus, not an edge case.

Every item answers one question: **where did ISAAC get this?**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- the concept vocabulary --------------------------------------------------
#
# A concept is a THING A SOURCE CAN STATE, named in the scientist's language and
# deliberately NOT named after an ISAAC field path. Adding an official path to
# one of these is `bl15.mapping`'s job and several of them have no path at all.
#
# The first ten come from the naming convention the project owner supplied on
# 2026-09-16 for Angel's files:
#
#   runNo_sample/electrodeNo_sampleName_loading_electrolyte_gas_condition_
#   pH_flowRate_filter_Potential
#
# THAT IS A VOCABULARY, NOT A GRAMMAR. It is recorded here as the set of things
# worth recognising; `bl15.filenames` recognises them by SHAPE and by alias, not
# by position, because the real corpus omits, reorders and adds fields — measured:
# `71_07_IrTiO2_0p5nm_AsIs_NoElectrolyte` carries no potential and no filter,
# `52_05_JK1_base_after1stCycling_filter20_850mV_step05` carries a step index the
# convention does not mention, and `46_04_..._ffilter35_...` misspells one.

CONCEPT_LEGACY_NUMBER = "legacy_run_or_file_number"
CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER = "sample_or_electrode_number"
CONCEPT_SAMPLE_NAME = "sample_name"
CONCEPT_LOADING_OR_THICKNESS = "loading_or_thickness"
CONCEPT_ELECTROLYTE_OR_MEDIUM = "electrolyte_or_medium"
CONCEPT_GAS_CONDITION = "gas_condition"
CONCEPT_PH = "ph"
CONCEPT_FLOW_RATE = "flow_rate"
CONCEPT_FILTER = "filter"
CONCEPT_POTENTIAL_MAGNITUDE = "potential_magnitude"

#: The electrochemical reference a potential is measured against. **A SEPARATE
#: CONCEPT FROM THE MAGNITUDE, ON PURPOSE.** A filename says `850mV` and says
#: nothing about the basis; the beamtime notes say "vs reference" for the JK
#: samples and "RHE" for the later TiO2 ones. A magnitude with an unknown basis
#: is a different fact from a magnitude with a known one, and collapsing them
#: would be this package answering a question only the scientist can.
CONCEPT_POTENTIAL_REFERENCE = "potential_reference_basis"

CONCEPT_CYCLING_STATE = "cycling_state"
CONCEPT_BEFORE_AFTER_STATE = "before_after_state"
CONCEPT_STEP_NUMBER = "step_number"
CONCEPT_DRY_STATE = "dry_state"
CONCEPT_NEW_SPOT = "new_spot"
CONCEPT_REPEAT_MARKER = "repeat_marker"

# Instrument and acquisition concepts, from the SPEC headers, the `.dat` exports
# and the macros.
CONCEPT_ELEMENT = "element"
CONCEPT_EDGE = "absorption_edge"
CONCEPT_EMISSION_ENERGY = "emission_energy"
CONCEPT_MOTOR_POSITION = "motor_position"
CONCEPT_SCAN_COMMAND = "scan_command"
CONCEPT_ENERGY_GRID = "energy_grid"
CONCEPT_COUNTING_TIME = "counting_time"
CONCEPT_SCAN_COUNT = "scan_count"
CONCEPT_ACQUISITION_TIMESTAMP = "acquisition_timestamp"
CONCEPT_ACQUISITION_EPOCH = "acquisition_epoch"
CONCEPT_DETECTOR_COLUMN = "detector_column"
CONCEPT_POINT_COUNT = "point_count"
CONCEPT_SPEC_FILE_DECLARATION = "spec_file_declaration"
CONCEPT_SPEC_USER_STRING = "spec_user_string"
CONCEPT_ACQUISITION_TARGET = "acquisition_target"
CONCEPT_ACQUISITION_METHOD = "acquisition_method"
CONCEPT_SAMPLE_POSITION = "sample_position"
CONCEPT_TRIGGER = "trigger"

# Shared beamtime context, from `readme.txt` and the notes.
CONCEPT_BEAMSIZE = "beamsize"
CONCEPT_SPECTROMETER_CONFIG = "spectrometer_configuration"
CONCEPT_MONOCHROMATOR_CALIBRATION = "monochromator_calibration"
CONCEPT_BEAMTIME_DATES = "beamtime_dates"
CONCEPT_BEAMTIME_PURPOSE = "beamtime_purpose"
CONCEPT_SAMPLE_PREPARATION = "sample_preparation"
CONCEPT_ECHEM_PROCEDURE = "echem_procedure"
CONCEPT_NOTE_FILE_NUMBER_ROW = "note_file_number_row"
CONCEPT_QUALITY_NOTE = "quality_note"

#: A token a reader SAW and could not name. **It is a first-class concept, not a
#: failure.** ``HIST-004``'s banned pattern is "Upload -> Spinner -> Mysterious
#: JSON", and silently dropping the third of a filename a profile does not
#: recognise is the same defect one layer down: the scientist would have no way
#: to see what was passed over. A partially-recognised filename is useful.
CONCEPT_UNKNOWN_TOKEN = "unknown_token"

CONCEPTS: frozenset[str] = frozenset(
    {
        CONCEPT_LEGACY_NUMBER,
        CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER,
        CONCEPT_SAMPLE_NAME,
        CONCEPT_LOADING_OR_THICKNESS,
        CONCEPT_ELECTROLYTE_OR_MEDIUM,
        CONCEPT_GAS_CONDITION,
        CONCEPT_PH,
        CONCEPT_FLOW_RATE,
        CONCEPT_FILTER,
        CONCEPT_POTENTIAL_MAGNITUDE,
        CONCEPT_POTENTIAL_REFERENCE,
        CONCEPT_CYCLING_STATE,
        CONCEPT_BEFORE_AFTER_STATE,
        CONCEPT_STEP_NUMBER,
        CONCEPT_DRY_STATE,
        CONCEPT_NEW_SPOT,
        CONCEPT_REPEAT_MARKER,
        CONCEPT_ELEMENT,
        CONCEPT_EDGE,
        CONCEPT_EMISSION_ENERGY,
        CONCEPT_MOTOR_POSITION,
        CONCEPT_SCAN_COMMAND,
        CONCEPT_ENERGY_GRID,
        CONCEPT_COUNTING_TIME,
        CONCEPT_SCAN_COUNT,
        CONCEPT_ACQUISITION_TIMESTAMP,
        CONCEPT_ACQUISITION_EPOCH,
        CONCEPT_DETECTOR_COLUMN,
        CONCEPT_POINT_COUNT,
        CONCEPT_SPEC_FILE_DECLARATION,
        CONCEPT_SPEC_USER_STRING,
        CONCEPT_ACQUISITION_TARGET,
        CONCEPT_ACQUISITION_METHOD,
        CONCEPT_SAMPLE_POSITION,
        CONCEPT_TRIGGER,
        CONCEPT_BEAMSIZE,
        CONCEPT_SPECTROMETER_CONFIG,
        CONCEPT_MONOCHROMATOR_CALIBRATION,
        CONCEPT_BEAMTIME_DATES,
        CONCEPT_BEAMTIME_PURPOSE,
        CONCEPT_SAMPLE_PREPARATION,
        CONCEPT_ECHEM_PROCEDURE,
        CONCEPT_NOTE_FILE_NUMBER_ROW,
        CONCEPT_QUALITY_NOTE,
        CONCEPT_UNKNOWN_TOKEN,
    }
)


# --- source classification ---------------------------------------------------
#
# What KIND of thing a file in the archive is. Classification is `bl15.classify`'s
# job and is CONTENT-LED where content is available, because the real corpus
# proves a filename cannot carry it: `run29` has no extension and is a MACRO,
# `alignment` has no extension and is a SPEC ACQUISITION, and `run29.mac.mac`
# and `run29.mac` are two different files whose names suggest one.

SOURCE_TYPE_SPEC_ACQUISITION = "spec_acquisition"
SOURCE_TYPE_SCAN_EXPORT = "scan_export"
SOURCE_TYPE_MACRO = "macro"
SOURCE_TYPE_ACQUISITION_METHOD_MACRO = "acquisition_method_macro"
SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO = "motor_snapshot_macro"
SOURCE_TYPE_PROCESSED_SPECTRUM = "processed_spectrum"
SOURCE_TYPE_DETECTOR_PRODUCT = "detector_product"
SOURCE_TYPE_SHARED_README = "shared_readme"
SOURCE_TYPE_BEAMTIME_NOTES = "beamtime_notes"
SOURCE_TYPE_ALIGNMENT = "alignment"
SOURCE_TYPE_STANDARD_OR_REFERENCE = "standard_or_reference"
SOURCE_TYPE_UNKNOWN = "unknown"

SOURCE_TYPES: frozenset[str] = frozenset(
    {
        SOURCE_TYPE_SPEC_ACQUISITION,
        SOURCE_TYPE_SCAN_EXPORT,
        SOURCE_TYPE_MACRO,
        SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
        SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO,
        SOURCE_TYPE_PROCESSED_SPECTRUM,
        SOURCE_TYPE_DETECTOR_PRODUCT,
        SOURCE_TYPE_SHARED_README,
        SOURCE_TYPE_BEAMTIME_NOTES,
        SOURCE_TYPE_ALIGNMENT,
        SOURCE_TYPE_STANDARD_OR_REFERENCE,
        SOURCE_TYPE_UNKNOWN,
    }
)

#: Which source types may become a candidate Run at all. **`macro` is NOT here,
#: and that is ``CLAUDE.md``-level mandatory** (the master brief's §10): a
#: ``.mac`` file is script evidence and one macro in this corpus declares up to
#: EIGHT measurements. `scan_export` is not here either (§11): 908 ``.dat``
#: files are scan children of ~92 measurements, and turning each into a Run
#: would invent 816 measurements nobody performed.
RUN_CANDIDATE_SOURCE_TYPES: frozenset[str] = frozenset(
    {SOURCE_TYPE_SPEC_ACQUISITION}
)


# --- the scope of a statement ------------------------------------------------
#
# How WIDELY a statement applies. `readme.txt` states the spectrometer crystal
# for the whole beamtime; a filename states a potential for one measurement.
# Both are evidence; treating the first as a per-Run manual entry would be a
# lie about where it came from (the master brief's §19 and §48).

SCOPE_BEAMTIME = "beamtime"
SCOPE_SAMPLE_GROUP = "sample_group"
SCOPE_MEASUREMENT = "measurement"
SCOPE_SCAN = "scan"

SCOPES: frozenset[str] = frozenset(
    {SCOPE_BEAMTIME, SCOPE_SAMPLE_GROUP, SCOPE_MEASUREMENT, SCOPE_SCAN}
)


# --- how a value was arrived at ----------------------------------------------

#: The source says this, literally, at this locator. ``normalized_value`` is
#: either absent or byte-equal to ``raw_literal``.
DETERMINISM_READ = "read"
#: The source says ``raw_literal`` and a STORED, NAMED rule in this package
#: produces ``normalized_value`` from it. The rule is in ``normalization_rule``
#: and the literal is never overwritten. ``ffilter35`` -> filter 35 is this.
DETERMINISM_NORMALIZED = "normalized"
#: No source states this; a stored rule over several sources produces it. Used
#: sparingly and never for a scientific judgement.
DETERMINISM_INFERRED = "inferred"

DETERMINISM_KINDS: frozenset[str] = frozenset(
    {DETERMINISM_READ, DETERMINISM_NORMALIZED, DETERMINISM_INFERRED}
)


@dataclass(frozen=True)
class SourceEvidence:
    """ONE statement one source makes, with everything needed to audit it.

    **``raw_literal`` IS VERBATIM AND IS NEVER REPLACED.** Where a stored rule
    produces a cleaner reading, it goes in :attr:`normalized_value` beside the
    literal with :attr:`normalization_rule` saying which rule and why. The real
    corpus makes this concrete: ``ffilter35`` is preserved exactly, and "filter
    35" sits next to it labelled as a doubled-prefix normalisation. Rewriting
    the source would destroy the only thing that lets a scientist disagree.

    :attr:`concept` may be :data:`CONCEPT_UNKNOWN_TOKEN` and
    :attr:`normalized_value` may be ``None``. Neither is a failure; both are
    states a reader is required to be able to report.
    """

    #: Stable within one import session. Assigned by the caller that assembled
    #: the session, not by the reader, so a reader stays a pure function of text.
    evidence_id: str
    #: Archive-relative path of the file this was read from. The scientist's own
    #: handle on the source — never an opaque id.
    source_path: str
    #: What kind of source it is; one of :data:`SOURCE_TYPES`.
    source_type: str
    #: WHERE in the source. A SPEC header key (``#F``), a line number
    #: (``line 42``), a filename character span (``filename[6:9]``), a macro
    #: block (``newfile block 3``). Scientist-readable, not a byte offset alone.
    locator: str
    #: Exactly what the source says there.
    raw_literal: str
    #: What this statement is ABOUT; one of :data:`CONCEPTS`.
    concept: str
    #: The reader that produced it.
    parser_id: str
    #: One of :data:`DETERMINISM_KINDS`.
    determinism: str = DETERMINISM_READ
    #: One of :data:`SCOPES`.
    scope: str = SCOPE_MEASUREMENT
    #: The cleaned reading, when a stored rule produced one.
    normalized_value: Any = None
    #: The unit the normalised value is in, when the concept has one. Separate
    #: from the value because ``060mV`` and ``1p2V`` are the same concept in two
    #: units and a scientist comparing them needs both stated.
    unit: str | None = None
    #: Which named rule produced :attr:`normalized_value`. REQUIRED whenever
    #: :attr:`determinism` is not :data:`DETERMINISM_READ`; enforced in
    #: :meth:`__post_init__` so an unexplained normalisation cannot exist.
    normalization_rule: str | None = None
    #: The naming profile in force, and its version. ``None`` for readers that
    #: consult no profile (the SPEC and scan readers read a documented format,
    #: not a convention).
    profile_id: str | None = None
    profile_version: str | None = None
    #: An ISO-8601 UTC instant the source itself states, when it states one.
    #: Never a clock reading taken at parse time.
    timestamp_utc: str | None = None
    #: The measurement stem this statement belongs to, when the reader can tell
    #: from the source alone. Relationship reconstruction lives in
    #: ``bl15.relate``; this is only what the file itself names.
    measurement_stem: str | None = None

    def __post_init__(self) -> None:
        if self.concept not in CONCEPTS:
            raise ValueError(f"unknown concept: {self.concept!r}")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unknown source_type: {self.source_type!r}")
        if self.determinism not in DETERMINISM_KINDS:
            raise ValueError(f"unknown determinism: {self.determinism!r}")
        if self.scope not in SCOPES:
            raise ValueError(f"unknown scope: {self.scope!r}")
        if self.determinism != DETERMINISM_READ and not self.normalization_rule:
            # A normalisation nobody can name is indistinguishable from a
            # guess, which §5 forbids. Refused at construction rather than
            # reported later, because by then the literal is already beside a
            # value with no warrant.
            raise ValueError(
                "determinism "
                f"{self.determinism!r} requires normalization_rule"
            )

    def to_state(self) -> dict:
        """The wire and on-disk shape. Every field, including the empty ones.

        Omitting ``None``s would make "this reader looked and found no unit"
        indistinguishable from "this reader does not report units", and the
        review surface has to tell those apart.
        """
        return {
            "evidence_id": self.evidence_id,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "locator": self.locator,
            "raw_literal": self.raw_literal,
            "concept": self.concept,
            "parser_id": self.parser_id,
            "determinism": self.determinism,
            "scope": self.scope,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "normalization_rule": self.normalization_rule,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "timestamp_utc": self.timestamp_utc,
            "measurement_stem": self.measurement_stem,
        }


@dataclass(frozen=True)
class ReaderResult:
    """What ONE reader read out of ONE source, and what it passed over.

    :attr:`skipped` is not optional and is the same discipline
    ``historical_import.ParsedSource`` already enforces one layer up: a reader
    that reported only what it understood would leave a scientist unable to see
    what it ignored.
    """

    source_path: str
    parser_id: str
    evidence: tuple[SourceEvidence, ...] = ()
    skipped: tuple[dict, ...] = ()
    #: Set when the reader declined the source whole — too large, undecodable,
    #: not its format. A reader NEVER raises for bad input; a refusal a
    #: scientist can see beats an exception a log swallows.
    refused_reason: str | None = None

    def to_state(self) -> dict:
        return {
            "source_path": self.source_path,
            "parser_id": self.parser_id,
            "evidence": [e.to_state() for e in self.evidence],
            "skipped": [dict(entry) for entry in self.skipped],
            "refused_reason": self.refused_reason,
        }


# --- reader resource ceilings ------------------------------------------------
#
# Measured against the real corpus so they are bounds, not guesses: the largest SPEC
# acquisition file is **1,620,639 bytes** (`alignment`), the largest NUMBERED acquisition
# 874,026 bytes, the largest `.dat` ~40 KB, the beamtime notes ~30 KB, and the whole
# archive 89,163,651 bytes over 1,192 files.
#
# ~~the largest SPEC acquisition file is ~500 KB~~ — CORRECTED 2026-09-16, the same day,
# by the slice that implemented the walk and re-measured independently here. The ceiling
# below is unchanged and was never in danger: 1.6 MB clears 8 MB. It is the stated fact
# that was wrong, and it is struck rather than replaced because a bound justified by a
# wrong measurement invites a later "correction" downward on the strength of that same
# wrong number.

#: Largest single source a reader will accept. Over it the reader REFUSES with
#: the measured size and this ceiling, so nothing is read partly and reported
#: as whole.
MAX_SOURCE_BYTES = 8_000_000
#: Most evidence items one source may contribute. A SPEC acquisition file
#: carries ~180 motor positions plus headers; the ceiling is well clear of that
#: and well under anything that could exhaust memory.
MAX_EVIDENCE_PER_SOURCE = 4_000
#: Most data rows a reader will walk in one scan export or processed spectrum.
MAX_DATA_ROWS = 20_000
