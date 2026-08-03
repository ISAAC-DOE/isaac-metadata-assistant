"""CHARACTERIZATION tests: what the truth path does TODAY with JSON Schema
``format`` and with empty values.

Read this first, because almost every assertion below pins a DEFECT:

The vendored official schema declares ``"format": "date-time"`` at exactly six
locations. ISAAC enforces NONE of them, and it would still enforce none of them
if someone "fixed" the obvious cause. There are TWO independent causes:

  Cause 1 (code)      ``src/isaac_records/official.py`` builds
                      ``Draft202012Validator(schema)`` with no ``format_checker=``.
                      Under JSON Schema, ``format`` is annotation-only unless a
                      format checker is supplied, so the keyword is inert.

  Cause 2 (packaging) ``pyproject.toml`` declares ``"jsonschema>=4.21"``, NOT
                      ``jsonschema[format]``. The ``date-time`` checker in
                      ``Draft202012Validator.FORMAT_CHECKER`` is registered only
                      when ``rfc3339-validator`` is installed. It is not
                      installed, so ``date-time`` is absent from the checker
                      registry.

The consequence, and the reason this module exists:

    FIXING CAUSE 1 ALONE IS A SILENT NO-OP. The validator would carry a
    ``format_checker``, look armed to every reader and every code reviewer, and
    still accept ``created_utc = "not-a-date"``, because the registry it
    consults has no ``date-time`` entry to consult.

Part A pins both causes separately so that no single-cause change can pass
review unnoticed. Parts B and C pin the observable behaviour. Part D collects
the evidence that arming enforcement is safe for the public corpus.

Nothing here asserts desired behaviour. When enforcement is genuinely armed,
these tests are SUPPOSED to fail; the failure messages say what to change.

EVERY TEST THAT ARMING ENFORCEMENT WILL BREAK. A fixer needs the whole list up
front, because the fix is one change and the fallout is spread across three
files. Measured by an independent reviewer who actually applied the full fix:

  * this module — Part A (4 tests) and Part B (39 tests) — 43 in total;
  * ``apps/api/tests/test_corpus_mutation.py`` — the ``stayed_valid``
    assertions for ``created_utc``, which record the same leniency from the
    mutation-harness side. Its comment now states the SAME two-cause model as
    this module; if the two ever disagree, one of them is lying.
  * ``tests/test_diagnostics.py`` —
    ``test_format_is_present_in_the_schema_but_not_enforced_by_this_validator``.
    This one was previously unnamed here, and a fixer following the old note
    would have been ambushed by it.

Three files, one reality. They must stay consistent.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from isaac_records import validate_draft
from isaac_records.export import export_draft, transform
from isaac_records.official import load_official_validator, validate_official

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "tests" / "fixtures" / "official"
TRUTHPATH = ROOT / "tests" / "fixtures" / "truthpath"
DRAFT_PATH = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"

XANES = "ex_situ_xanes_cuo2_record.json"
CO2RR = "co2rr_performance_record.json"

RID = "01JFH3Q8Z1Q9F0XG3V7N4K2M8C"
FIXED_NOW = "2026-01-01T00:00:00Z"  # no clock dependence anywhere in this module


def load_example(name: str) -> dict:
    return json.loads((OFFICIAL / name).read_text(encoding="utf-8"))


def load_probe(name: str) -> dict:
    return json.loads((TRUTHPATH / f"{name}.json").read_text(encoding="utf-8"))


def set_at(record: dict, parts: tuple, value) -> None:
    """Set a nested location addressed by dict keys and list indices."""
    node = record
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


# =============================================================================
# PART A — the dual-cause guard
# =============================================================================
#
# ############################################################################
# #  THE THREE TESTS IN PART A MUST BE UPDATED TOGETHER.                     #
# #                                                                          #
# #  Arming format enforcement requires BOTH:                                #
# #    (1) pass `format_checker=` when constructing the validator in          #
# #        src/isaac_records/official.py, AND                                 #
# #    (2) declare `jsonschema[format]` (or `rfc3339-validator`) in           #
# #        pyproject.toml so a `date-time` checker actually exists.           #
# #                                                                          #
# #  If you change one and only one of these tests starts failing, you have   #
# #  a HALF-FIX: a validator that looks armed and enforces nothing. Do not    #
# #  "just update the failing test" — go and do the other half.               #
# ############################################################################


def test_cause_2_date_time_checker_is_absent_from_the_registry():
    """CURRENT BEHAVIOUR, and a pinned DEFECT (packaging half).

    ``date-time`` is not a registered format checker in this environment,
    because ``pyproject.toml`` asks for plain ``jsonschema``, not
    ``jsonschema[format]``. Supplying a ``format_checker`` to the validator
    therefore cannot enforce ``date-time`` — the checker does not exist.
    """
    checkers = sorted(Draft202012Validator.FORMAT_CHECKER.checkers)
    assert "date-time" not in checkers, (
        "GOOD NEWS AND A WARNING: a 'date-time' format checker is now registered, "
        "so the rfc3339-validator dependency landed (Cause 2 is fixed).\n"
        "Cause 1 must now be fixed in the SAME change: "
        "src/isaac_records/official.py must pass format_checker= when it builds "
        "Draft202012Validator, or ISAAC still enforces nothing and the "
        "enforcement story in this repo is internally inconsistent.\n"
        "Then update Parts B and D of this module, which pin the LENIENT behaviour.\n"
        f"registered checkers: {checkers}"
    )


def test_cause_2_the_rfc3339_dependency_is_not_declared():
    """CURRENT BEHAVIOUR, and a pinned DEFECT (packaging half, declared form).

    Pins the *declaration*, not just the installed state, so that the runtime
    observation above cannot be satisfied by an accidental transitive install
    that a fresh environment would not reproduce.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Assert the ABSENCE of a format-capable declaration, never the presence of
    # one exact pinned version string. Reviewed change: this used to require the
    # literal '"jsonschema>=4.21"', so a routine unrelated version bump failed
    # with a message about format enforcement — a false alarm pointing at the
    # wrong file.
    assert "rfc3339" not in text.lower(), (
        "pyproject now declares an RFC3339 date-time implementation, so Cause 2 "
        "is fixed. Cause 1 (format_checker= in src/isaac_records/official.py) "
        "must be fixed in the SAME change, or ISAAC lands in the silent "
        "half-fix state."
    )
    assert "jsonschema[format" not in text, (
        "pyproject now requests the jsonschema[format] extra, so Cause 2 is "
        "fixed. Cause 1 must be fixed in the same change."
    )


def test_cause_1_the_official_validator_carries_no_format_checker():
    """CURRENT BEHAVIOUR, and a pinned DEFECT (code half).

    ``load_official_validator`` returns a validator whose ``format_checker``
    attribute is ``None`` (verified against the installed jsonschema, 4.x), so
    every ``format`` keyword in the official schema is inert annotation.
    """
    validator = load_official_validator(ROOT)
    assert hasattr(validator, "format_checker"), (
        "jsonschema renamed the attribute this guard reads; re-derive it before "
        "trusting any conclusion about format enforcement."
    )
    assert validator.format_checker is None, (
        "A format_checker is now supplied (Cause 1 fixed).\n"
        "READ THIS BEFORE UPDATING THIS TEST: if "
        "test_cause_2_date_time_checker_is_absent_from_the_registry still PASSES, "
        "you have shipped a SILENT HALF-FIX — the validator looks armed but "
        "'date-time' is not in the checker registry, so 'not-a-date' still "
        "validates. Add jsonschema[format] (or rfc3339-validator) to "
        "pyproject.toml as well."
    )


def test_the_two_causes_agree_that_enforcement_is_dead():
    """CURRENT BEHAVIOUR: the interlock, stated end-to-end.

    Computes whether ``date-time`` enforcement is ACTUALLY live by validating a
    record with a nonsense required timestamp, and asserts that this matches the
    conjunction of the two causes. Today every term is False.

    This is the test that makes a half-fix impossible to ship quietly: after
    arming only Cause 1, ``cause_1_armed`` is True while ``observed_enforcement``
    is still False, and the message below names the missing half.
    """
    cause_1_armed = load_official_validator(ROOT).format_checker is not None
    cause_2_available = "date-time" in Draft202012Validator.FORMAT_CHECKER.checkers

    record = load_probe("SYNTHETIC-FORMAT-PROBE-01")  # created_utc = "not-a-date"

    # BASELINE GUARD (added after independent review). Without this, ANY schema
    # error anywhere in the fixture — a corrupted ULID, a renamed enum, an
    # unrelated schema edit — would read as `observed_enforcement = True` and
    # this test would tell the reader that format enforcement had come alive.
    # A reviewer proved that exact misdiagnosis by corrupting `record_id`. So
    # first establish that the fixture is otherwise clean: with a canonical
    # RFC3339 timestamp in place, it must validate.
    baseline = load_probe("SYNTHETIC-FORMAT-PROBE-01")
    baseline["timestamps"]["created_utc"] = "2099-01-01T00:00:00Z"
    baseline_report = validate_official(baseline, ROOT)
    assert baseline_report.ok, (
        "The probe fixture is invalid for a reason that has nothing to do with "
        "`format`. Fix that first — until it validates with a canonical "
        "timestamp, this test cannot say anything about format enforcement.\n"
        f"{baseline_report.render()}"
    )

    # ATTRIBUTABLE observation. Enforcement is 'live' only if the validator
    # objects AT `timestamps.created_utc` ABOUT the date-time format — not
    # merely if it objects to something.
    report = validate_official(record, ROOT)
    observed_enforcement = any(
        err.path == "timestamps.created_utc" and "date-time" in err.message
        for err in report.errors
    )

    assert (cause_1_armed, cause_2_available, observed_enforcement) == (False, False, False), (
        "The format-enforcement state changed.\n"
        f"  Cause 1 (validator has a format_checker): {cause_1_armed}\n"
        f"  Cause 2 ('date-time' checker registered): {cause_2_available}\n"
        f"  Observed (a nonsense created_utc is rejected): {observed_enforcement}\n"
        "Both causes must be True for enforcement to exist. If exactly one is "
        "True, ISAAC is in the SILENT HALF-FIX state: it appears to validate "
        "timestamps and does not."
    )
    assert observed_enforcement == (cause_1_armed and cause_2_available), (
        "Enforcement no longer follows from the two causes; re-derive the model "
        "in this module's docstring before trusting it."
    )


# =============================================================================
# PART B — format characterization
# =============================================================================

#: (label, example file, address) for each of the six ``format: date-time``
#: locations in schema/isaac_record_v1.json. Re-verified in
#: ``test_the_schema_declares_exactly_these_six_date_time_locations``.
FORMAT_LOCATIONS = [
    ("timestamps.created_utc", XANES, ("timestamps", "created_utc")),
    ("timestamps.acquired_start_utc", XANES, ("timestamps", "acquired_start_utc")),
    ("timestamps.acquired_end_utc", XANES, ("timestamps", "acquired_end_utc")),
    ("timestamps.last_updated_utc", XANES, ("timestamps", "last_updated_utc")),
    (
        "context.electrochemistry.potential_vs_RHE.conversion.converted_utc",
        CO2RR,
        ("context", "electrochemistry", "potential_vs_RHE", "conversion", "converted_utc"),
    ),
    (
        "descriptors.outputs[0].generated_utc",
        XANES,
        ("descriptors", "outputs", 0, "generated_utc"),
    ),
]

#: Strings that are NOT valid RFC3339 date-times. Every one is accepted today.
BAD_DATE_TIMES = [
    "not-a-date",
    "2026-13-45T99:99:99Z",  # well-shaped, impossible calendar values
    "",  # empty
    "2026-08-02",  # date only, no time
    "   ",  # whitespace
    "TBD",  # placeholder
]

EXPECTED_FORMAT_POINTERS = {
    "/properties/timestamps/properties/created_utc",
    "/properties/timestamps/properties/acquired_start_utc",
    "/properties/timestamps/properties/acquired_end_utc",
    "/properties/timestamps/properties/last_updated_utc",
    "/properties/context/properties/electrochemistry/properties/potential_vs_RHE"
    "/properties/conversion/properties/converted_utc",
    "/properties/descriptors/properties/outputs/items/properties/generated_utc",
}


def test_the_schema_declares_exactly_these_six_date_time_locations():
    """CURRENT BEHAVIOUR of the vendored schema (desired — this is upstream's
    design, not a defect). Re-derived here so Part B's table cannot silently
    drift away from the schema it claims to cover."""
    schema = json.loads((ROOT / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8"))
    found: dict[str, str] = {}

    def walk(node, pointer: str) -> None:
        if isinstance(node, dict):
            fmt = node.get("format")
            if isinstance(fmt, str):
                found[pointer] = fmt
            for key, value in node.items():
                walk(value, f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{pointer}/{i}")

    walk(schema, "")
    assert set(found) == EXPECTED_FORMAT_POINTERS, sorted(found)
    assert set(found.values()) == {"date-time"}
    assert len(FORMAT_LOCATIONS) == len(EXPECTED_FORMAT_POINTERS) == 6


@pytest.mark.parametrize("label, example, address", FORMAT_LOCATIONS, ids=[x[0] for x in FORMAT_LOCATIONS])
@pytest.mark.parametrize("bad", BAD_DATE_TIMES, ids=[repr(b) for b in BAD_DATE_TIMES])
def test_invalid_date_time_strings_are_accepted_at_every_format_location(label, example, address, bad):
    """PINS A DEFECT — this is NOT desired behaviour.

    At all six ``format: date-time`` locations, a string that is not remotely a
    date-time validates against the official schema today, because no format
    checker is in play (Part A). ``created_utc`` and
    ``descriptors.outputs[].generated_utc`` are REQUIRED fields, and the schema's
    own description of ``generated_utc`` says placeholder strings are not
    allowed — the schema says so, and nothing enforces it.

    When enforcement is armed these 36 cases must be inverted to assert
    rejection, together with Part A and Part D.
    """
    record = load_example(example)
    assert validate_official(record, ROOT).ok, "the unmutated public example must be valid first"

    set_at(record, address, bad)
    report = validate_official(record, ROOT)
    assert report.ok, (
        f"{label} = {bad!r} is now REJECTED. If format enforcement was armed "
        f"deliberately, invert this test (and Part A, and Part D). Errors:\n"
        f"{report.render()}"
    )


@pytest.mark.parametrize("label, example, address", FORMAT_LOCATIONS, ids=[x[0] for x in FORMAT_LOCATIONS])
def test_a_non_string_is_rejected_by_type_not_by_format(label, example, address):
    """CURRENT BEHAVIOUR, and this part IS desired.

    The one thing that is still caught at these locations is a non-string, and it
    is caught by ``type: string`` — never by ``format``. The distinction matters:
    a reader who sees ``12345`` rejected must not conclude that timestamps are
    validated. Only the JSON type is.
    """
    record = load_example(example)
    set_at(record, address, 12345)
    report = validate_official(record, ROOT)
    assert not report.ok
    messages = [e.message for e in report.errors]
    assert any("is not of type 'string'" in m for m in messages), messages
    assert not any("date-time" in m for m in messages), (
        f"a format error appeared at {label}; format enforcement may have been armed: {messages}"
    )


@pytest.mark.parametrize(
    "probe, address, bad",
    [
        ("SYNTHETIC-FORMAT-PROBE-01", ("timestamps", "created_utc"), "not-a-date"),
        (
            "SYNTHETIC-FORMAT-PROBE-05",
            ("context", "electrochemistry", "potential_vs_RHE", "conversion", "converted_utc"),
            "   ",
        ),
        ("SYNTHETIC-FORMAT-PROBE-06", ("descriptors", "outputs", 0, "generated_utc"), "TBD"),
    ],
)
def test_promoted_format_reproducers_validate_today(probe, address, bad):
    """PINS A DEFECT. Standing, human-inspectable artifacts of it.

    Each committed reproducer is a WHOLE record that ISAAC calls officially valid
    today while carrying a nonsense timestamp. They exist so the defect can be
    seen without running Python.

    Synthetic by construction: derived from a public example in
    ``tests/fixtures/official/``, re-keyed to a marked record_id, with
    ``sample.material.name`` overwritten to an unmistakable placeholder and a
    ``synthetic-truthpath-probe`` tag. No private or real experimental data.
    """
    record = load_probe(probe)
    node = record
    for part in address[:-1]:
        node = node[part]
    assert node[address[-1]] == bad, "reproducer no longer carries the mutation it documents"
    assert record["sample"]["material"]["name"] == "SYNTHETIC PROBE MATERIAL - NOT REAL DATA"
    assert "synthetic-truthpath-probe" in record["tags"]

    report = validate_official(record, ROOT)
    assert report.ok, (
        f"{probe} is now rejected — expected if format enforcement was armed on "
        f"purpose, in which case update Part A and Part B together:\n{report.render()}"
    )


# =============================================================================
# PART C — empty-value characterization
# =============================================================================


def _with_empty(mutation: str) -> dict:
    record = load_example(XANES)
    if mutation == "measurement.series = []":
        record["measurement"]["series"] = []
    elif mutation == "descriptors.outputs = []":
        record["descriptors"]["outputs"] = []
    elif mutation == 'sample.sample_form = ""':
        record["sample"]["sample_form"] = ""
    elif mutation == 'sample.sample_form = "   "':
        record["sample"]["sample_form"] = "   "
    elif mutation == "sample.material = {}":
        record["sample"]["material"] = {}
    elif mutation == "series[0].channels = []":
        record["measurement"]["series"][0]["channels"] = []
    elif mutation == "series[0].independent_variables = []":
        record["measurement"]["series"][0]["independent_variables"] = []
    elif mutation == 'series[0].series_id = ""':
        record["measurement"]["series"][0]["series_id"] = ""
    elif mutation == "attribution = {}":
        record["attribution"] = {}
    else:  # pragma: no cover - guards the table below against typos
        raise AssertionError(f"unknown mutation {mutation!r}")
    return record


ACCEPTED_EMPTY_VALUES = [
    "measurement.series = []",
    "descriptors.outputs = []",
    'sample.sample_form = ""',
    'sample.sample_form = "   "',
    "sample.material = {}",
    "series[0].channels = []",
    "series[0].independent_variables = []",
    'series[0].series_id = ""',
    "attribution = {}",
]


@pytest.mark.parametrize("mutation", ACCEPTED_EMPTY_VALUES)
def test_empty_values_are_accepted_by_official_validation(mutation):
    """PINS A DEFECT (or at least a gap) — NOT desired behaviour.

    The official schema sets no ``minItems``, ``minLength`` or ``minProperties``
    at these locations, so a record can be officially valid while containing a
    measurement with zero spectra, a spectrum with zero data channels, an
    anonymous sample, or an empty attribution block.

    Unlike the ``format`` defect, this one is genuinely UPSTREAM: it is a
    property of the vendored schema, not of ISAAC's validator configuration.
    Closing it means either an upstream schema change or an ISAAC-side rule
    outside the official schema. Nothing here proposes either.
    """
    record = _with_empty(mutation)
    report = validate_official(record, ROOT)
    assert report.ok, f"{mutation} is now rejected:\n{report.render()}"


@pytest.mark.parametrize("probe", ["SYNTHETIC-EMPTY-PROBE-01", "SYNTHETIC-EMPTY-PROBE-06"])
def test_promoted_empty_reproducers_validate_today(probe):
    """PINS A DEFECT. Standing artifacts of the hollow-record gap.

    ``SYNTHETIC-EMPTY-PROBE-01`` is the ``measurement.series = []`` case, kept as
    a file because it is the one empty value with a downstream export consequence
    (see the falsy-guard tests below).

    ``SYNTHETIC-EMPTY-PROBE-06`` is the maximally hollow record: ``series``,
    ``assets`` and ``descriptors.outputs`` all empty and ``sample_form`` blank —
    a record that claims a QC verdict of "valid" over zero data, and that ISAAC
    accepts as an official ISAAC record.
    """
    record = load_probe(probe)
    assert "synthetic-truthpath-probe" in record["tags"]
    assert validate_official(record, ROOT).ok, validate_official(record, ROOT).render()

    if probe == "SYNTHETIC-EMPTY-PROBE-06":
        assert record["measurement"]["series"] == []
        assert record["assets"] == []
        assert record["descriptors"]["outputs"] == []
        assert record["sample"]["sample_form"] == ""
        # ...while still asserting a QC verdict over the zero spectra it contains.
        assert record["measurement"]["qc"]["status"] == "valid"


# --- the two falsy guards on `draft.get("series")` ----------------------------
#
# src/isaac_records/draft_validator.py:150  `if draft.get("series"):`
# src/isaac_records/export.py:83            `if draft.get("series"):`
#
# `[]` is falsy, so an EMPTY series list takes the same branch as NO series at
# all. Both guards were written for "no series"; neither distinguishes it from
# "zero spectra".


@pytest.fixture
def draft():
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


def test_empty_series_skips_the_qc_evidence_rule_in_draft_validation(draft):
    """PINS A DEFECT — NOT desired behaviour.

    The no-guessing rule "a measurement with series must carry an EVIDENCED qc
    verdict" is guarded by ``if draft.get("series"):``. Setting ``series`` to
    ``[]`` makes that guard falsy, so the rule never runs: the very same draft
    that is REFUSED with a spectrum present is ACCEPTED once the spectrum list is
    emptied. Emptying data must not be a way to switch off a no-guessing rule.
    """
    unevidenced = copy.deepcopy(draft)
    unevidenced["block_evidence"].pop("qc:status", None)

    assert not validate_draft(unevidenced).ok, (
        "baseline: with a spectrum present, an unevidenced qc verdict is refused"
    )

    unevidenced["series"] = []
    assert validate_draft(unevidenced).ok, (
        "the rule now fires for an empty series list too — that would be a FIX; "
        "update this test and say so"
    )


def test_empty_series_exports_a_record_with_no_measurement_and_no_qc_verdict(draft):
    """PINS A DEFECT, end to end — NOT desired behaviour.

    A draft whose ``series`` is ``[]`` EXPORTS SUCCESSFULLY, and the exported
    official record has NO ``measurement`` key at all — so the QC verdict the
    draft carried has silently DISAPPEARED from the record. The export is not
    refused, and nothing in the record says a verdict was dropped.

    The evidence sidecar makes it sharper: it still publishes a ``qc:status``
    evidence entry for a verdict that is nowhere in the record it accompanies.
    """
    baseline = export_draft(copy.deepcopy(draft), ROOT, record_id=RID, now=FIXED_NOW)
    assert baseline.ok
    assert baseline.record["measurement"]["qc"]["status"] == "valid", (
        "baseline: with a spectrum present, the QC verdict reaches the record"
    )

    hollow = copy.deepcopy(draft)
    hollow["series"] = []

    record = transform(hollow, record_id=RID, now=FIXED_NOW)
    assert "measurement" not in record, (
        "transform now emits a measurement block for an empty series list — a FIX; "
        "update this test"
    )

    result = export_draft(hollow, ROOT, record_id=RID, now=FIXED_NOW)
    assert result.ok, (
        "export now refuses an empty series list — a FIX; update this test.\n"
        f"{result.draft_report.render()}\n"
        f"{result.official_report.render() if result.official_report else ''}"
    )
    assert "measurement" not in result.record
    blob = json.dumps(result.record)
    assert "qc" not in result.record.get("measurement", {})
    assert '"status": "valid"' not in blob

    # The sidecar still claims evidence for the vanished verdict.
    assert "qc:status" in result.sidecar["evidence"], (
        "the sidecar no longer advertises evidence for a verdict absent from the "
        "record — a FIX; update this test"
    )


def test_a_nonsense_timestamp_survives_the_whole_export_path_unchanged(draft):
    """PINS A DEFECT — the third of the claim the rest of this module missed.

    Added after independent review. Every other format test above stops at
    VALIDATION: it proves the validator accepts a nonsense ``date-time``. That
    leaves the more consequential half unpinned — that such a value travels the
    whole export path and is written into the official record VERBATIM.

    The gap was not theoretical. A reviewer armed a rejection inside
    ``export_draft`` and the entire 76-test suite stayed green, because nothing
    exercised the export gate with a bad timestamp. A fix (or a regression)
    landing there would have shipped invisibly.

    ``now`` is the exported record's ``timestamps.created_utc``, which is a
    REQUIRED field carrying ``"format": "date-time"``.
    """
    result = export_draft(copy.deepcopy(draft), ROOT, record_id=RID, now="not-a-date")

    assert result.ok, (
        "the export path now REFUSES a non-RFC3339 created_utc — that is a FIX; "
        "update this test and re-read the module docstring.\n"
        f"{result.draft_report.render()}\n"
        f"{result.official_report.render() if result.official_report else ''}"
    )
    assert result.official_report.ok, (
        "official validation now objects to the timestamp; enforcement may be armed"
    )
    assert result.record["timestamps"]["created_utc"] == "not-a-date", (
        "the exported record no longer carries the nonsense value verbatim — "
        "something now normalises or rejects it; update this test"
    )
    # And it is really in the serialized artifact, not merely in a dict field.
    assert '"created_utc": "not-a-date"' in json.dumps(result.record, indent=2)


# =============================================================================
# PART D — compatibility evidence for arming enforcement
# =============================================================================

#: Strict RFC3339 `date-time`, deliberately hand-rolled: no new dependency, and
#: NOT `datetime.fromisoformat`, which accepts date-only strings such as
#: "2026-08-02" and would therefore pass one of the very values Part B pins as
#: bad. Shape first, then a real calendar check via `strptime`.
RFC3339_SHAPE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def is_canonical_rfc3339(value: object) -> bool:
    """True only for a genuine RFC3339 date-time with a real calendar date.

    Known strictness, stated rather than hidden: RFC3339 permits a ``:60`` leap
    second, which ``strptime`` rejects. No value in the public corpus uses one.
    """
    if not isinstance(value, str):
        return False
    match = RFC3339_SHAPE.match(value)
    if not match:
        return False
    offset = match.group(8)
    if offset not in ("Z", "z"):
        hours, minutes = int(offset[1:3]), int(offset[4:6])
        if hours > 23 or minutes > 59:
            return False
    try:
        datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            datetime.strptime(value[:19], "%Y-%m-%dt%H:%M:%S")
        except ValueError:
            return False
    return True


@pytest.mark.parametrize("bad", BAD_DATE_TIMES, ids=[repr(b) for b in BAD_DATE_TIMES])
def test_the_rfc3339_helper_rejects_every_value_part_b_calls_bad(bad):
    """The compatibility evidence is only worth anything if its date checker is
    honest. This is desired behaviour of the TEST HELPER, not of ISAAC."""
    assert not is_canonical_rfc3339(bad)


@pytest.mark.parametrize(
    "good",
    ["2026-08-02T00:00:00Z", "2025-12-10T18:30:00Z", "2026-08-02T12:00:00.500Z", "2026-08-02T12:00:00+02:00"],
)
def test_the_rfc3339_helper_accepts_canonical_values(good):
    """Desired behaviour of the TEST HELPER."""
    assert is_canonical_rfc3339(good)


def collect_corpus_date_times() -> list[tuple[str, str, object]]:
    """Every value sitting at a ``format: date-time`` location in the ten public
    upstream examples, as (file, location, value)."""
    out: list[tuple[str, str, object]] = []
    for path in sorted(OFFICIAL.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for key in ("created_utc", "acquired_start_utc", "acquired_end_utc", "last_updated_utc"):
            if key in record.get("timestamps", {}):
                out.append((path.name, f"timestamps.{key}", record["timestamps"][key]))
        conversion = (
            record.get("context", {})
            .get("electrochemistry", {})
            .get("potential_vs_RHE", {})
            .get("conversion", {})
        )
        if "converted_utc" in conversion:
            out.append((path.name, "…conversion.converted_utc", conversion["converted_utc"]))
        for i, output in enumerate(record.get("descriptors", {}).get("outputs", []) or []):
            if "generated_utc" in output:
                out.append((path.name, f"descriptors.outputs[{i}].generated_utc", output["generated_utc"]))
    return out


def test_all_ten_public_examples_validate_today():
    """CURRENT BEHAVIOUR, and desired. The baseline that everything above
    mutates away from. (``tests/test_official.py`` asserts this per file; it is
    restated here so Part D's safety argument is self-contained.)"""
    examples = sorted(OFFICIAL.glob("*.json"))
    assert len(examples) == 10
    for path in examples:
        record = json.loads(path.read_text(encoding="utf-8"))
        report = validate_official(record, ROOT)
        assert report.ok, f"{path.name}:\n{report.render()}"


def test_every_public_corpus_date_time_is_canonical_rfc3339():
    """COMPATIBILITY EVIDENCE, not a characterization of ISAAC.

    Arming ``date-time`` enforcement would reject nothing in the public corpus:
    every value at a ``format: date-time`` location in the ten upstream examples
    is already canonical RFC3339. That removes the "it might break the examples"
    objection to fixing both causes in Part A.

    Scope limit, stated honestly: this proves the PUBLIC corpus is safe. It says
    nothing about records in the production database, which this test cannot and
    must not read.
    """
    values = collect_corpus_date_times()
    assert len(values) >= 31, (
        f"expected at least the 31 date-time values measured in the committed "
        f"corpus, found {len(values)} — re-measure before trusting this evidence"
    )
    offenders = [(f, loc, v) for f, loc, v in values if not is_canonical_rfc3339(v)]
    assert offenders == [], offenders

    # Non-vacuity: the collector really did reach several distinct locations.
    assert len({loc for _, loc, _ in values}) >= 5
    assert len({f for f, _, _ in values}) == 10


def test_last_updated_utc_is_unexercised_by_the_public_corpus():
    """A HONEST GAP in the compatibility evidence above, pinned so it is not
    forgotten: no public example sets ``timestamps.last_updated_utc``, so the
    corpus proves nothing about that one location. Part B still covers it by
    mutation."""
    locations = {loc for _, loc, _ in collect_corpus_date_times()}
    assert "timestamps.last_updated_utc" not in locations
