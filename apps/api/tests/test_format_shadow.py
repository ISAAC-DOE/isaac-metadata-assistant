"""Tests for the SHADOW format-aware validator.

Three things are being proved here, and they are of very different kinds.

**1. That importing this module arms nothing.** ``format`` enforcement is Q20 in
``docs/dean-authorization-packet.md`` and it is UNANSWERED, so the two
independent causes pinned by ``tests/test_truthpath_characterization.py`` must
both survive. Part A re-measures both *after* importing ``format_shadow``,
because the failure mode is a process-wide side effect at import time
(``FormatChecker.cls_checks`` writes into a class attribute), which no amount of
reading the source proves absent.

**2. That the RFC3339 predicate is honest.** A shadow whose date checker is
wrong is worse than no shadow: it would report violations of a rule nobody
wrote. Part B pins the accept/reject contract value by value, including the leap
second decision and the deliberate divergence from the compatibility helper in
the truth-path characterization module.

**3. That a finding cannot carry record content.** Part E is the leak canary and
is the single most important test in this file. ``jsonschema`` error messages
echo the offending value verbatim, so the only safe design is to discard the
message entirely — and the only way to *know* it was discarded is to push a
distinctive sentinel through every format-declaring field and assert it comes
out nowhere.

The corpus is ``tests/fixtures/official/*.json`` — ten example records copied
verbatim from the PUBLIC upstream ``ISAAC-DOE/isaac-ai-ready-record`` repository
(provenance: ``schema/PROVENANCE.md``). Nothing here touches a database, a
network, or any real experimental artifact.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from isaac_api import format_shadow as fs
from isaac_api.workspace import REPO_ROOT
from isaac_records.official import load_official_validator, validate_official

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "official"
XANES = "ex_situ_xanes_cuo2_record.json"
CO2RR = "co2rr_performance_record.json"

#: A value no schema, no fixture and no validator vocabulary can produce. If it
#: appears in a serialized ``ShadowResult``, record content escaped.
CANARY = "SECRET-CANARY-VALUE"


def load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def set_at(record: dict, address: tuple, value) -> None:
    node = record
    for part in address[:-1]:
        node = node[part]
    node[address[-1]] = value


#: The six ``format: date-time`` locations, as (label, example file, address).
#: Mirrors ``FORMAT_LOCATIONS`` in ``tests/test_truthpath_characterization.py``
#: on purpose: if the two ever disagree, one of them is lying about the schema.
#: Re-derived against the schema in
#: :func:`test_declared_format_paths_are_the_six_the_schema_declares`.
FORMAT_LOCATIONS = [
    ("timestamps.created_utc", XANES, ("timestamps", "created_utc")),
    ("timestamps.acquired_start_utc", XANES, ("timestamps", "acquired_start_utc")),
    ("timestamps.acquired_end_utc", XANES, ("timestamps", "acquired_end_utc")),
    ("timestamps.last_updated_utc", XANES, ("timestamps", "last_updated_utc")),
    (
        "context…conversion.converted_utc",
        CO2RR,
        ("context", "electrochemistry", "potential_vs_RHE", "conversion", "converted_utc"),
    ),
    (
        "descriptors.outputs[0].generated_utc",
        XANES,
        ("descriptors", "outputs", 0, "generated_utc"),
    ),
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


# =============================================================================
# PART A — the shadow must arm NOTHING
# =============================================================================
#
# ###########################################################################
# #  IF ANY TEST IN PART A FAILS, DO NOT "JUST UPDATE IT".                  #
# #                                                                         #
# #  A failure here means importing `format_shadow` changed global format   #
# #  enforcement, which is a decision reserved to Dean (Q20, UNANSWERED)    #
# #  and which changes the meaning of `records_passing_full_schema` over 30 #
# #  production-derived rows that are his data, not ours.                   #
# ###########################################################################


def test_importing_the_shadow_leaves_the_official_validator_format_blind():
    """Cause 1 must survive. This is the guard the module exists under.

    ``tests/test_truthpath_characterization.py`` asserts the same thing, but it
    does not import ``format_shadow``, so it cannot see a side effect this
    module introduces. This module IS imported here, above, before the
    assertion runs.
    """
    validator = load_official_validator(REPO_ROOT)
    assert validator.format_checker is None, (
        "importing isaac_api.format_shadow armed a format checker on the "
        "OFFICIAL validator. The shadow must build its own validator and touch "
        "nothing in isaac_records.official."
    )


def test_importing_the_shadow_leaves_the_shared_checker_registry_untouched():
    """Cause 2 must survive, in all three places it could be broken.

    ``FormatChecker.checkers`` is a CLASS attribute. ``cls_checks`` and the
    module-level ``@FormatChecker.cls_checks`` decorator write into it
    process-wide, so a shadow implemented that way would arm ``date-time`` for
    every ``FormatChecker()`` anyone constructs anywhere — including a future
    one handed to the official validator. Each of the three observations below
    would independently catch that.
    """
    assert fs.FORMAT_DATE_TIME not in FormatChecker.checkers, (
        "the class-level registry now knows 'date-time'; the shadow registered "
        "globally instead of on its own instance"
    )
    assert fs.FORMAT_DATE_TIME not in FormatChecker().checkers, (
        "a freshly constructed FormatChecker inherits 'date-time'; the shadow "
        "polluted the class registry"
    )
    assert fs.FORMAT_DATE_TIME not in Draft202012Validator.FORMAT_CHECKER.checkers, (
        "Draft202012Validator.FORMAT_CHECKER now knows 'date-time'. Either the "
        "shadow polluted it, or the rfc3339-validator dependency landed — in "
        "which case Cause 2 is fixed and Q20 must be re-read before anything "
        "else changes."
    )


def test_the_project_still_declares_no_rfc3339_dependency():
    """Cause 2 in its DECLARED form — no dependency was added by this slice.

    Read-only assertion over ``pyproject.toml``, which this slice must not
    modify. Mirrors the truth-path characterization test so a dependency added
    for the shadow's benefit fails here too, next to the module that would have
    wanted it.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "rfc3339" not in text.lower()
    assert "jsonschema[format" not in text


def test_the_shadow_checker_is_a_private_instance_that_knows_exactly_one_format():
    """The positive half: the shadow really is armed, privately, and narrowly.

    Starting from ``FormatChecker(formats=())`` rather than ``FormatChecker()``
    is deliberate — the shadow then checks exactly the one format it implements
    and claims nothing about ``email``, ``ipv4``, ``uuid`` or the others a
    default instance would inherit.
    """
    assert set(fs._SHADOW_FORMAT_CHECKER.checkers) == {fs.FORMAT_DATE_TIME}
    assert fs._SHADOW_FORMAT_CHECKER is not Draft202012Validator.FORMAT_CHECKER
    assert fs._SHADOW_FORMAT_CHECKER.checkers is not FormatChecker.checkers


def test_the_shadow_validator_and_the_official_validator_are_different_objects():
    """The shadow consumes the schema; it does not wrap or patch the authority."""
    official = load_official_validator(REPO_ROOT)
    path = REPO_ROOT / "schema" / "isaac_record_v1.json"
    stat = path.stat()
    shadow = fs._shadow_validator(str(path), stat.st_mtime_ns, stat.st_size)
    assert shadow is not official
    assert shadow.format_checker is fs._SHADOW_FORMAT_CHECKER
    assert official.format_checker is None


# =============================================================================
# PART B — RFC3339 date-time semantics
# =============================================================================

GOOD_DATE_TIMES = [
    "2026-08-02T00:00:00Z",
    "2026-08-02T12:00:00.500Z",
    "2026-08-02T12:00:00.123456789Z",
    "2026-08-02T12:00:00+02:00",
    "2026-08-02T12:00:00-07:30",
    "2026-08-02T12:00:00-00:00",  # RFC3339 §4.3: unknown local offset
    "2026-08-02t12:00:00z",  # §5.6 NOTE: lower case is permitted
    "2026-08-02T12:00:00Z",
    "2024-02-29T00:00:00Z",  # a real leap day
    "2026-08-02T23:59:59+23:59",  # extreme but legal offset
]

BAD_DATE_TIMES = [
    "not-a-date",
    "TBD",
    "",
    "   ",
    "2026-08-02",  # date only; no time, no offset
    "2026-08-02T12:00:00",  # no offset — RFC3339 requires one
    "2026-08-02 12:00:00Z",  # space separator: permitted by the §5.6 NOTE for
    #                          "some protocols", not by the ABNF the schema uses
    "2026-13-01T00:00:00Z",  # month 13
    "2026-02-30T00:00:00Z",  # calendar-invalid day
    "2023-02-29T00:00:00Z",  # 2023 is not a leap year
    "2026-08-02T25:00:00Z",  # hour 25
    "2026-08-02T12:60:00Z",  # minute 60
    "2026-08-02T12:00:61Z",  # second 61 — beyond even the leap second
    "2026-8-2T12:00:00Z",  # unpadded fields
    "2026-08-02T12:00:00.Z",  # fraction marker with no digits
    "2026-08-02T12:00:00+24:00",  # offset hour 24
    "2026-08-02T12:00:00+02:60",  # offset minute 60
    "2026-08-02T12:00:00+0200",  # offset missing its colon
    "2026-08-02T12:00:00Z\n",  # trailing newline — why the regex uses \\Z, not $
    " 2026-08-02T12:00:00Z",  # leading whitespace
]


@pytest.mark.parametrize("value", GOOD_DATE_TIMES)
def test_rfc3339_accepts_canonical_values(value):
    """Desired behaviour of the predicate, value by value."""
    assert fs.is_rfc3339_date_time(value), value


@pytest.mark.parametrize("value", BAD_DATE_TIMES)
def test_rfc3339_rejects_non_conforming_values(value):
    """Desired behaviour of the predicate. Every entry names its own reason
    inline in ``BAD_DATE_TIMES``; the list is the documentation."""
    assert not fs.is_rfc3339_date_time(value), value


@pytest.mark.parametrize("value", [None, 12345, 12.5, True, [], {}, b"2026-08-02T00:00:00Z"])
def test_rfc3339_predicate_is_false_for_non_strings(value):
    """A non-string is not an RFC3339 date-time. Never raises."""
    assert fs.is_rfc3339_date_time(value) is False


def test_the_leap_second_decision_is_accept_and_it_is_pinned_here():
    """THE DOCUMENTED DECISION, stated as a test so it cannot drift silently.

    RFC3339's ABNF gives ``time-second`` the range 00–60, so ``:60`` is
    conformant and a checker that rejected it would be stricter than the
    standard the schema points at — the shadow would report a violation of a
    rule nobody wrote.

    What is deliberately NOT done: verifying that a given ``:60`` falls on an
    announced leap second. That needs an IERS table this project does not
    vendor, and inventing one would be guessing (``CLAUDE.md`` §5). So a
    ``:60`` that never happened is accepted, and that limit is the price of not
    guessing.
    """
    assert fs.is_rfc3339_date_time("2016-12-31T23:59:60Z"), (
        "a real announced leap second is rejected; the documented decision is ACCEPT"
    )
    assert fs.is_rfc3339_date_time("2026-08-02T12:00:60Z"), (
        "a shape-conformant leap second at an instant that never had one is "
        "rejected. That would mean a leap-second table was introduced — which "
        "is a real strengthening, but it must be a deliberate one: update this "
        "test and the module docstring together."
    )
    assert not fs.is_rfc3339_date_time("2026-08-02T12:00:61Z"), (
        ":61 must still be rejected; 60 is the ceiling, not an open door"
    )


def _truthpath_helper():
    """Import the compatibility helper from the truth-path characterization
    module. That module lives under ``tests/`` (a different rootdir package
    from ``apps/api/tests``), so the path is extended for exactly this import
    and then restored."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "tests"))
    try:
        from test_truthpath_characterization import is_canonical_rfc3339
    finally:
        sys.path.pop(0)
    return is_canonical_rfc3339


def test_the_two_date_checkers_in_this_repo_disagree_in_exactly_two_places():
    """PINS TWO KNOWN DISAGREEMENTS between the repository's two date checkers.

    ``tests/test_truthpath_characterization.py::is_canonical_rfc3339`` is
    compatibility evidence about the public corpus. It is not this module's
    checker, it is not the truth path, and it is not being changed here — this
    slice may not modify that file. But two checkers of the same standard in
    one repository must not silently disagree, so both differences are pinned:

    **1. Leap seconds.** The helper routes through ``strptime``, which rejects
    ``:60``. Its own docstring says so ("Known strictness, stated rather than
    hidden"). This module ACCEPTS ``:60``; see
    :func:`test_the_leap_second_decision_is_accept_and_it_is_pinned_here`.

    **2. A trailing newline — and this one was NOT previously documented
    anywhere.** The helper anchors with ``$``, and in Python ``$`` also matches
    immediately before a trailing newline, so ``is_canonical_rfc3339(
    "2026-08-02T12:00:00Z\\n")`` returns **True**. This module anchors with
    ``\\Z`` and rejects it. The strings are different values and only one of
    them is an RFC3339 ``date-time``.

    That is a real (if small) defect in the helper, found by this test rather
    than reasoned about: it means the helper's corpus sweep would pass a value
    with trailing whitespace. It has no effect on the corpus conclusion — no
    public example carries one, which is re-measured by
    :func:`test_all_ten_public_examples_pass_the_shadow` through the strict
    checker — and it is recorded here rather than fixed, because
    ``tests/test_truthpath_characterization.py`` is out of this slice's write
    scope. Flagged for the orchestrator.

    Everything else must agree. If a third disagreement appears, this fails and
    names the value.
    """
    is_canonical_rfc3339 = _truthpath_helper()

    leap = "2016-12-31T23:59:60Z"
    assert fs.is_rfc3339_date_time(leap) is True
    assert is_canonical_rfc3339(leap) is False, (
        "the truth-path compatibility helper now accepts a leap second, so "
        "divergence 1 is gone; update both docstrings"
    )

    newline = "2026-08-02T12:00:00Z\n"
    assert fs.is_rfc3339_date_time(newline) is False
    assert is_canonical_rfc3339(newline) is True, (
        "the truth-path compatibility helper now rejects a trailing newline, "
        "so divergence 2 is gone — someone changed its `$` anchor to `\\Z`. "
        "That is a fix; delete this half of the test and say so."
    )

    known_divergences = {leap, newline}
    for value in GOOD_DATE_TIMES + BAD_DATE_TIMES:
        if value in known_divergences or ":60" in value:
            continue
        assert fs.is_rfc3339_date_time(value) == is_canonical_rfc3339(value), value


# =============================================================================
# PART C — schema introspection
# =============================================================================


def test_declared_format_paths_are_the_six_the_schema_declares():
    """The six locations are DERIVED from the schema, never written down.

    Same expectation set as
    ``tests/test_truthpath_characterization.py::test_the_schema_declares_exactly_these_six_date_time_locations``.
    Two independent walks of the same file must agree; if they stop agreeing,
    one walk is wrong.
    """
    paths = fs.declared_format_paths(REPO_ROOT)
    assert set(paths) == EXPECTED_FORMAT_POINTERS
    assert len(paths) == 6
    assert list(paths) == sorted(paths), "the order must be a property of the schema"


def test_every_declared_format_in_the_vendored_schema_is_date_time():
    """If the schema ever declares another format, the shadow must be extended
    deliberately rather than silently reporting it as ``OTHER``."""
    formats = fs.declared_formats(REPO_ROOT)
    assert {name for _, name in formats} == {fs.FORMAT_DATE_TIME}
    assert len(formats) == len(EXPECTED_FORMAT_POINTERS)


def test_declared_format_paths_is_deterministic_across_calls():
    assert fs.declared_format_paths(REPO_ROOT) == fs.declared_format_paths(REPO_ROOT)


def test_every_format_the_schema_declares_is_actually_implemented_by_the_shadow():
    """DRIFT GUARD. It is about the future, not about present coverage.

    Measured today: the vendored schema declares exactly ONE format name,
    ``date-time``, at six sites, and the shadow implements exactly that one. So
    this passes trivially right now — which is the point. It is placed here to
    fail LOUDLY the first time a schema refresh introduces a second format name.

    Why the test above is not enough. ``test_every_declared_format_in_the_
    vendored_schema_is_date_time`` pins the name, so it fires on any new format
    whether or not the shadow handles it, and the obvious way to "fix" that
    failure is to widen the expected set — which silences the alarm without
    implementing anything. This one cannot be satisfied that way: it compares
    what the SCHEMA declares against what the CHECKER registers and what the
    CODE TABLE can name, so the only way to make it pass is to actually add the
    checker and the code.

    The silent failure it prevents, stated exactly: an unimplemented format is
    not an error. ``jsonschema`` simply does not evaluate a format its checker
    does not know, so the shadow would report NOTHING for those fields while
    still presenting itself as the stricter validator. The
    ``format_shadow.records_failing`` figure in the Record Verification report
    would then be an undercount that looks like a clean result — in BOTH modes,
    including the datastore mode where nobody can inspect the records to notice.
    """
    declared = {name for _, name in fs.declared_formats(REPO_ROOT)}
    implemented = set(fs._SHADOW_FORMAT_CHECKER.checkers)
    nameable = set(fs._FORMAT_CODES)

    assert declared, "the schema declared no format at all; that is itself drift"

    unchecked = sorted(declared - implemented)
    assert not unchecked, (
        "the vendored schema declares format(s) the shadow checker does not "
        f"implement: {unchecked}. jsonschema silently SKIPS an unknown format, so "
        "the shadow would report nothing for those fields while still claiming to "
        "be the stricter validator. Register a checker on "
        "`_SHADOW_FORMAT_CHECKER` (never `cls_checks`) before widening anything."
    )

    unnamed = sorted(declared - nameable)
    assert not unnamed, (
        f"the shadow can check {sorted(declared)} but has no stable error code "
        f"for {unnamed}, so a finding would be published as the opaque `OTHER`. "
        "Add an entry to `_FORMAT_CODES`; `SHADOW_ERROR_CODES` is derived from it."
    )

    # Every code the table can produce must be in the closed vocabulary the
    # served report projects through, or a real finding would be dropped by the
    # verification report's structural allowlist.
    assert set(fs._FORMAT_CODES.values()) <= set(fs.SHADOW_ERROR_CODES)

    # And the converse direction, so an implemented-but-undeclared checker is
    # visible too: a checker for a format the schema never declares is dead
    # code that will silently start firing after a schema refresh.
    assert implemented <= declared, sorted(implemented - declared)


def test_the_format_drift_guard_would_actually_fire(monkeypatch):
    """NEGATIVE CONTROL for the guard above.

    The guard passes today because nothing has drifted, and a guard that has
    never been seen to fail is indistinguishable from one that cannot. Here a
    schema revision declaring ``uri`` is simulated, and the guard's own
    comparisons are asserted to produce a violation.
    """
    monkeypatch.setattr(
        fs, "declared_formats", lambda root: (("/properties/pretend", "uri"),)
    )
    declared = {name for _, name in fs.declared_formats(REPO_ROOT)}

    assert declared - set(fs._SHADOW_FORMAT_CHECKER.checkers) == {"uri"}
    assert declared - set(fs._FORMAT_CODES) == {"uri"}


# =============================================================================
# PART D — shadow validation behaviour
# =============================================================================


def test_all_ten_public_examples_pass_the_shadow():
    """COMPATIBILITY EVIDENCE, restated from the shadow's side.

    Every value at a ``format: date-time`` location in the ten public upstream
    examples is already canonical RFC3339, so arming enforcement would reject
    nothing in the public corpus. That is the evidence Part D of the truth-path
    characterization module assembles; here it is measured end-to-end through
    the actual checker rather than through a test-local helper.

    Scope limit, stated honestly: this is about the PUBLIC corpus. It says
    nothing about records in the production database, which this test cannot
    and must not read.
    """
    examples = sorted(FIXTURE_DIR.glob("*.json"))
    assert len(examples) == 10
    for path in examples:
        record = json.loads(path.read_text(encoding="utf-8"))
        result = fs.shadow_validate(record, REPO_ROOT)
        assert result.passed, f"{path.name}: {result.findings}"
        assert result.findings == ()


@pytest.mark.parametrize(
    "label, example, address", FORMAT_LOCATIONS, ids=[x[0] for x in FORMAT_LOCATIONS]
)
@pytest.mark.parametrize("bad", BAD_DATE_TIMES[:8], ids=[repr(b) for b in BAD_DATE_TIMES[:8]])
def test_the_shadow_sees_what_the_official_validator_does_not(label, example, address, bad):
    """THE POINT OF THE WHOLE MODULE, at all six locations.

    The official validator accepts every one of these strings — that is the
    defect ``tests/test_truthpath_characterization.py`` Part B pins, and this
    test re-asserts it so the two cannot drift apart. The shadow reports it.

    Both halves are asserted in the same test on purpose: "the shadow found
    something" is only interesting alongside "and the authority still says
    PASS". If the official half ever starts failing, format enforcement was
    armed, and Q20 must be re-read before anything here is updated.
    """
    record = load(example)
    assert validate_official(record, REPO_ROOT).ok, "the unmutated example must be valid first"

    set_at(record, address, bad)

    assert validate_official(record, REPO_ROOT).ok, (
        f"{label} = {bad!r} is now REJECTED by the OFFICIAL validator. Format "
        f"enforcement may have been armed — that is Dean's call (Q20). Do not "
        f"update this test without re-reading docs/dean-authorization-packet.md."
    )

    result = fs.shadow_validate(record, REPO_ROOT)
    assert not result.passed, f"the shadow missed {label} = {bad!r}"
    codes = {(f.code, f.rule_family) for f in result.findings}
    assert ("FORMAT_DATE_TIME", "format") in codes, result.findings


@pytest.mark.parametrize(
    "label, example, address", FORMAT_LOCATIONS, ids=[x[0] for x in FORMAT_LOCATIONS]
)
def test_a_non_string_is_reported_as_a_type_finding_and_not_as_a_format_finding(
    label, example, address
):
    """The shadow must not double-report a type error as a format error.

    JSON Schema's ``format`` applies only to instances of the type it is
    defined for, so a non-string is *not applicable* rather than *invalid*.
    Reporting both would invent a rule the schema does not state and would
    contradict
    ``tests/test_truthpath_characterization.py::test_a_non_string_is_rejected_by_type_not_by_format``.

    This is the behaviour that the first draft of the checker got WRONG: the
    adapter forwarded ``is_rfc3339_date_time(12345) -> False`` straight to
    jsonschema and produced a ``FORMAT_DATE_TIME`` finding stacked on the real
    ``TYPE_MISMATCH``.
    """
    record = load(example)
    set_at(record, address, 12345)
    result = fs.shadow_validate(record, REPO_ROOT)

    families = {f.rule_family for f in result.findings}
    assert "type" in families, result.findings
    assert "format" not in families, (
        f"{label}: a non-string produced a FORMAT finding as well as a TYPE "
        f"finding: {result.findings}"
    )


def test_shadow_validate_does_not_modify_the_record():
    """The shadow observes; it never populates, corrects or normalises."""
    record = load(XANES)
    record["timestamps"]["created_utc"] = "not-a-date"
    before = json.dumps(record, sort_keys=True, separators=(",", ":"))

    fs.shadow_validate(record, REPO_ROOT)

    assert json.dumps(record, sort_keys=True, separators=(",", ":")) == before
    assert record["timestamps"]["created_utc"] == "not-a-date", (
        "the shadow rewrote the value it was asked to inspect"
    )


def test_shadow_validate_is_repeatable_and_order_stable():
    """Same input, same findings, same ORDER — no dict-iteration dependence."""
    record = load(XANES)
    record["timestamps"]["created_utc"] = "not-a-date"
    record["record_type"] = "SYNTHETIC_INVALID_ENUM_TOKEN_ZZ9"

    runs = [fs.shadow_validate(record, REPO_ROOT) for _ in range(5)]
    assert all(run == runs[0] for run in runs)
    assert all(run.findings == runs[0].findings for run in runs)


@pytest.mark.parametrize(
    "mutation, expected_code, expected_family",
    [
        ("enum", "ENUM_NOT_ALLOWED", "enum"),
        ("const", "CONST_MISMATCH", "const"),
        ("pattern", "PATTERN_MISMATCH", "pattern"),
        ("additional", "ADDITIONAL_PROPERTIES", "additionalProperties"),
        ("required", "REQUIRED_MISSING", "required"),
    ],
)
def test_non_format_rule_families_get_their_own_stable_codes(
    mutation, expected_code, expected_family
):
    """The shadow is a full validator, not a format-only probe.

    It reports every rule family the schema states, each with a code
    constructed here from the PUBLIC ``(rule_family, schema_pointer)`` pair —
    never from the validator's message.
    """
    record = load(XANES)
    if mutation == "enum":
        record["record_type"] = "SYNTHETIC_INVALID_ENUM_TOKEN_ZZ9"
    elif mutation == "const":
        record["isaac_record_version"] = "9.99"
    elif mutation == "pattern":
        record["record_id"] = "not-a-ulid"
    elif mutation == "additional":
        record["synthetic_unknown_field_zz9"] = 1
    elif mutation == "required":
        record.pop("record_type")

    result = fs.shadow_validate(record, REPO_ROOT)
    assert not result.passed
    assert (expected_code, expected_family) in {
        (f.code, f.rule_family) for f in result.findings
    }, result.findings


def test_two_missing_required_properties_produce_two_findings_not_one():
    """MULTIPLICITY IS PRESERVED; IDENTITY IS NOT. A documented trade.

    Two required properties missing from the same object produce two
    ``jsonschema`` errors that differ ONLY in the message — and the message is
    the field this module discards, because it echoes the offending value
    verbatim. The two findings are therefore identical, and the module
    deliberately does NOT de-duplicate: collapsing them would silently
    under-count, which is a worse failure than not knowing which property is
    missing.
    """
    record = load(XANES)
    record.pop("record_type")
    record.pop("source_type")

    result = fs.shadow_validate(record, REPO_ROOT)
    required = [f for f in result.findings if f.code == "REQUIRED_MISSING"]
    assert len(required) >= 2, result.findings
    assert len(set(required)) == 1, (
        "the two findings are no longer identical, which means something is "
        "distinguishing them — check that it is not the discarded message"
    )
    assert required[0].schema_path == "", "root-level required lives at the root pointer"
    assert required[0].instance_path == ""


def test_the_root_pointer_is_the_empty_string_not_a_slash():
    """RFC 6901: ``""`` addresses the root; ``"/"`` addresses a member whose key
    is the empty string. ``corpus_mutation.pointer`` renders the root as ``"/"``
    because its targets are never the root — the two are not interchangeable and
    this pins which convention this module uses."""
    record = load(XANES)
    record["synthetic_unknown_field_zz9"] = 1
    finding = fs.shadow_validate(record, REPO_ROOT).findings[0]
    assert finding.schema_path == ""
    assert finding.instance_path == ""


def test_schema_pointers_address_the_subschema_not_the_keyword():
    """``/properties/timestamps/properties/created_utc``, not ``…/format``.

    The keyword is carried separately as ``rule_family``, so stripping it loses
    nothing — and it makes the pointer join directly against
    :func:`declared_format_paths`, which is what a consumer aggregating by
    schema location needs.
    """
    record = load(XANES)
    record["timestamps"]["created_utc"] = "not-a-date"
    findings = fs.shadow_validate(record, REPO_ROOT).findings
    assert len(findings) == 1
    assert findings[0].schema_path == "/properties/timestamps/properties/created_utc"
    assert findings[0].schema_path in fs.declared_format_paths(REPO_ROOT)
    assert not findings[0].schema_path.endswith("/format")


def test_array_indices_survive_in_the_instance_pointer():
    """An index is a position, not content, so it is emitted as a digit and the
    pointer stays a well-formed RFC 6901 pointer. The module docstring records
    this as a stated residual: over a real corpus, positions are record-derived,
    so an aggregate keyed by instance path still needs
    ``disclosure.suppress_small_cells``."""
    record = load(XANES)
    record["descriptors"]["outputs"][0]["generated_utc"] = "TBD"
    findings = fs.shadow_validate(record, REPO_ROOT).findings
    assert [f.instance_path for f in findings] == ["/descriptors/outputs/0/generated_utc"]


# =============================================================================
# PART E — THE LEAK CANARY
# =============================================================================


def _serialisations(result: fs.ShadowResult) -> list[str]:
    """Every plausible way a caller could render a result, as text.

    A canary that only checks ``repr()`` proves less than it looks: a caller
    serialises with ``dataclasses.asdict`` + ``json.dumps``, or reads the fields
    one at a time. All three are checked.
    """
    return [
        repr(result),
        str(result),
        json.dumps(dataclasses.asdict(result), sort_keys=True, default=str),
        "\n".join(
            f"{f.code}|{f.schema_path}|{f.rule_family}|{f.instance_path}"
            for f in result.findings
        ),
    ]


def test_a_sentinel_in_every_format_field_appears_nowhere_in_the_result():
    """THE MOST IMPORTANT TEST IN THIS FILE.

    ``jsonschema`` messages echo the offending value verbatim
    (``"'not-a-date' is not a 'date-time'"``), so a finding that forwarded
    ``error.message`` would be a direct scientific-value leak the moment this
    ran over anything but public fixtures. The design answer is to discard the
    message entirely — and the only way to *know* it was discarded is to push a
    value that cannot come from anywhere else through every format-declaring
    field and assert it comes out nowhere.

    Two example files are needed because the six locations do not all exist in
    one record: ``converted_utc`` is under the electrochemistry block.
    """
    for example in (XANES, CO2RR):
        record = load(example)
        planted = 0
        for _label, source, address in FORMAT_LOCATIONS:
            if source != example:
                continue
            try:
                set_at(record, address, CANARY)
                planted += 1
            except (KeyError, IndexError, TypeError):  # pragma: no cover
                pytest.fail(f"could not plant the canary at {address} in {example}")
        assert planted, f"no format location was planted in {example}"

        result = fs.shadow_validate(record, REPO_ROOT)
        assert not result.passed, f"{example}: the canary was not even detected"

        for text in _serialisations(result):
            assert CANARY not in text, (
                f"{example}: the sentinel escaped into a ShadowResult. A "
                f"validator message or an instance value is being carried. "
                f"error.message must be DISCARDED, not truncated or sanitised."
            )

        # And field-by-field, so a future field added to the dataclass is covered
        # by construction rather than by hoping the serialisers caught it.
        for finding in result.findings:
            for field in dataclasses.fields(finding):
                assert CANARY not in str(getattr(finding, field.name)), field.name


def test_a_sentinel_in_non_format_fields_also_appears_nowhere():
    """The canary is not a format-only concern.

    ``enum`` messages read ``"'X' is not one of [...]"`` and
    ``additionalProperties`` messages read ``"('X' was unexpected)"`` — both
    echo attacker- or record-controlled text. A sentinel is planted as an enum
    value, as an unknown property NAME, and as a pattern-constrained value.
    """
    record = load(XANES)
    record["record_type"] = CANARY
    record["record_id"] = CANARY
    record[CANARY] = "planted as an unknown property NAME, not a value"
    record["sample"]["composition"][CANARY] = 1.0

    result = fs.shadow_validate(record, REPO_ROOT)
    assert not result.passed

    for text in _serialisations(result):
        assert CANARY not in text, (
            "the sentinel escaped through a non-format rule family; every "
            "family must go through the same message-discarding path"
        )


def test_an_undeclared_instance_segment_is_masked():
    """DEFENCE IN DEPTH, and honest about what it currently catches.

    v1.05 is ``additionalProperties``-open in places where the writer
    legitimately keys a map by a scientific value — this repo's own fixture
    keys ``sample.composition`` by species. An unmasked instance pointer such
    as ``/sample/composition/CuO2_mass_fraction`` would be a value leak wearing
    a path's clothing.

    Stated limit: no v1.05 rule is known to fire *inside* an open map, so no
    end-to-end finding currently exercises this. The mask is a guard against a
    future schema revision or a drifting writer, and it is unit-tested here
    rather than left to be discovered.
    """
    declared = frozenset({"timestamps", "created_utc", "sample"})
    assert fs._mask_instance_segment("timestamps", declared) == "timestamps"
    assert fs._mask_instance_segment("CuO2_mass_fraction", declared) == (
        fs.MASK_UNDECLARED_SEGMENT
    )
    assert fs._mask_instance_segment(CANARY, declared) == fs.MASK_UNDECLARED_SEGMENT
    # Indices are positions, and are emitted.
    assert fs._mask_instance_segment(0, declared) == "0"
    assert fs._mask_instance_segment(7, declared) == "7"
    # bool is an int subclass; `True` must not render as "1" and pass for an index.
    assert fs._mask_instance_segment(True, declared) == fs.MASK_UNDECLARED_SEGMENT


def test_a_declared_segment_containing_pointer_metacharacters_is_escaped():
    """RFC 6901 escaping is applied to the segments that survive the mask, so a
    property name containing ``/`` or ``~`` cannot forge a pointer boundary. No
    v1.05 name does; this is why that stays true if one ever did."""
    declared = frozenset({"a/b", "c~d"})
    assert fs._mask_instance_segment("a/b", declared) == "a~1b"
    assert fs._mask_instance_segment("c~d", declared) == "c~0d"


# =============================================================================
# PART F — the code vocabulary is CLOSED and the mapping is TOTAL
# =============================================================================


def test_the_code_vocabulary_is_sorted_unique_and_contains_the_fallback():
    assert fs.SHADOW_ERROR_CODES == tuple(sorted(set(fs.SHADOW_ERROR_CODES)))
    assert "OTHER" in fs.SHADOW_ERROR_CODES
    assert "FORMAT_DATE_TIME" in fs.SHADOW_ERROR_CODES
    assert all(code.isupper() for code in fs.SHADOW_ERROR_CODES)


@pytest.mark.parametrize(
    "keyword",
    # Every validation keyword Draft 2020-12 defines, plus the applicator
    # keywords that can surface as `error.validator`. The point is that the
    # mapping is TOTAL: an unmapped keyword must fall to OTHER, never raise and
    # never invent a code.
    sorted(
        {
            "additionalProperties", "allOf", "anyOf", "const", "contains",
            "dependentRequired", "dependentSchemas", "else", "enum",
            "exclusiveMaximum", "exclusiveMinimum", "format", "if", "items",
            "maxContains", "maxItems", "maxLength", "maxProperties", "maximum",
            "minContains", "minItems", "minLength", "minProperties", "minimum",
            "multipleOf", "not", "oneOf", "pattern", "patternProperties",
            "prefixItems", "properties", "propertyNames", "required", "then",
            "type", "unevaluatedItems", "unevaluatedProperties", "uniqueItems",
        }
    ),
)
def test_every_jsonschema_keyword_maps_into_the_closed_code_set(keyword):
    code = fs.shadow_error_code(keyword, "/properties/anything", {})
    assert code in fs.SHADOW_ERROR_CODES, (keyword, code)


@pytest.mark.parametrize(
    "junk",
    ["", "   ", "Format", "FORMAT", "unknownKeyword", "1234", "../../etc/passwd", CANARY],
)
def test_unrecognised_rule_families_map_to_other(junk):
    """A CLOSED set means a family nobody anticipated can never invent a code a
    consumer has not seen. Case-sensitive on purpose: ``Format`` is not
    ``format``, and silently normalising it would hide a real drift."""
    assert fs.shadow_error_code(junk, "/properties/x", {}) == "OTHER"


def test_a_format_this_module_cannot_check_is_reported_as_other():
    """The shadow only knows how to check ``date-time``, and must not imply
    otherwise. If the vendored schema ever declares ``email`` or ``uri``, the
    code is ``OTHER`` until someone deliberately implements a checker — which
    is also why the empty-registry construction matters: no unimplemented
    format is silently checked by an inherited stdlib checker."""
    formats = {"/properties/x": "email", "/properties/y": fs.FORMAT_DATE_TIME}
    assert fs.shadow_error_code("format", "/properties/x", formats) == "OTHER"
    assert fs.shadow_error_code("format", "/properties/y", formats) == "FORMAT_DATE_TIME"
    assert fs.shadow_error_code("format", "/properties/unknown", formats) == "OTHER"
    assert fs.shadow_error_code("format", "/properties/x", None) == "OTHER"


def test_every_code_a_real_run_can_produce_is_in_the_closed_set():
    """End-to-end totality: sweep a battery of mutations and assert no run ever
    produces a code outside :data:`SHADOW_ERROR_CODES`."""
    mutations = [
        lambda r: r.__setitem__("record_type", "ZZZ"),
        lambda r: r.__setitem__("isaac_record_version", "9.99"),
        lambda r: r.__setitem__("record_id", "nope"),
        lambda r: r.__setitem__("synthetic_unknown_zz9", 1),
        lambda r: r.pop("timestamps"),
        lambda r: r["timestamps"].__setitem__("created_utc", "TBD"),
        lambda r: r["timestamps"].__setitem__("created_utc", []),
        lambda r: r.__setitem__("tags", [""]),
        lambda r: r.__setitem__("measurement", 5),
        lambda r: r.__setitem__("links", [{"target": "x"}]),
    ]
    seen: set[str] = set()
    for mutate in mutations:
        record = copy.deepcopy(load(XANES))
        mutate(record)
        for finding in fs.shadow_validate(record, REPO_ROOT).findings:
            assert finding.code in fs.SHADOW_ERROR_CODES, finding
            seen.add(finding.code)
    # Non-vacuity: the sweep really did reach several distinct families.
    assert len(seen) >= 4, seen
