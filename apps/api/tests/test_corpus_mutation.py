"""Tests for the deterministic mutation-testing harness.

The corpus is ``tests/fixtures/official/*.json`` — ten example records copied
verbatim from the PUBLIC upstream ``ISAAC-DOE/isaac-ai-ready-record`` repository
(provenance: ``schema/PROVENANCE.md``). Nothing here touches a database, a
network, or any real experimental artifact.

The most valuable tests in this file are the ones under
"PROVING THE ORACLES CAN FAIL". A harness whose oracles cannot fail is worthless:
it would report ``0 failures`` forever, including on the day something broke. So
each of those tests constructs a deliberately broken operator, evaluation
sequence or report block and asserts the oracle CATCHES it.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from isaac_api import corpus_mutation as cm
from isaac_api.workspace import REPO_ROOT

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "official"


# --------------------------------------------------------------------------
# Corpus and harness fixtures (module-scoped: the full sweep is expensive)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    ]
    assert records, "the public fixture corpus must not be empty"
    return records


@pytest.fixture(scope="module")
def operators() -> tuple[cm.MutationOperator, ...]:
    return cm.build_operators(REPO_ROOT)


@pytest.fixture(scope="module")
def harness(corpus, operators) -> cm.HarnessResult:
    return cm.run_harness(corpus, REPO_ROOT, operators=operators)


@pytest.fixture(scope="module")
def report(harness) -> dict:
    return cm.build_report(harness)


# --------------------------------------------------------------------------
# The corpus itself
# --------------------------------------------------------------------------


def test_corpus_is_the_ten_public_upstream_examples(corpus):
    assert len(corpus) == 10
    # Spans more than one domain and record type, so the conditional branches of
    # the schema are actually reachable.
    assert {r["record_domain"] for r in corpus} >= {
        "characterization",
        "performance",
        "simulation",
    }
    assert {r["record_type"] for r in corpus} >= {"evidence", "intent"}


def test_every_public_fixture_passes_baseline(corpus):
    for record in corpus:
        evaluation = cm.evaluate(record, REPO_ROOT)
        assert evaluation.schema_valid, record.get("record_id")
        assert evaluation.error_count == 0
        assert not evaluation.engines_disagree


# --------------------------------------------------------------------------
# Schema introspection — the catalog must be DERIVED, not hardcoded
# --------------------------------------------------------------------------


def test_schema_model_matches_the_vendored_schema():
    model = cm.introspect_schema(REPO_ROOT)
    document = json.loads(
        (REPO_ROOT / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )

    # Root requirements come from the document, not from this test's memory.
    assert model.root_required == tuple(document["required"])
    root_fields = {f.name for f in model.fields if len(f.path) == 1}
    assert root_fields == set(document["properties"])

    # Every unconditionally-required field is required by its own parent object
    # subschema, reached only through `properties`/`items`.
    for entry in model.fields:
        if not entry.required_unconditionally:
            continue
        node = document
        for segment in entry.path[:-1]:
            node = node["items"] if segment == cm.ARRAY_ITEM else node["properties"][segment]
        assert entry.name in node["required"]


def test_conditional_requirements_are_excluded_from_the_unconditional_set():
    model = cm.introspect_schema(REPO_ROOT)

    # v1.05's four root `allOf` rules plus the three nested `potential_vs_RHE`
    # rules. `descriptors` is the load-bearing one: it is NOT in the root
    # `required` list, so a naive reading would classify it optional and then
    # expect an evidence record to stay valid without it.
    assert ("descriptors",) in model.conditional_required
    assert ("context", "electrochemistry", "control_mode") in model.conditional_required
    assert (
        "context",
        "electrochemistry",
        "current_setpoint_mA_cm2",
    ) in model.conditional_required
    assert (
        "context",
        "electrochemistry",
        "potential_setpoint_V",
    ) in model.conditional_required

    # A name appearing only in an `if` states a CONDITION, not a requirement.
    # `allOf[1].if.required` lists `context`; misreading it would silently drop
    # `context` from the optional-removal catalog.
    assert ("context",) not in model.conditional_required

    conditional_names = {
        entry.path for entry in model.fields if entry.required_conditionally
    }
    assert conditional_names <= model.conditional_required
    assert not any(
        entry.required_unconditionally and entry.required_conditionally
        for entry in model.fields
    )


def test_object_locations_record_open_and_closed_alike():
    model = cm.introspect_schema(REPO_ROOT)
    by_path = {loc.path: loc for loc in model.objects}
    assert by_path[()].closed is True  # the root is additionalProperties: false
    assert by_path[("sample", "composition")].closed is False  # open by design
    assert by_path[("system",)].closed is True
    # Both branches must be populated or category G would only test one rule.
    assert sum(1 for loc in model.objects if loc.closed) > 0
    assert sum(1 for loc in model.objects if not loc.closed) > 0


# --------------------------------------------------------------------------
# The operator catalog
# --------------------------------------------------------------------------


def test_catalog_covers_every_implemented_category(operators):
    by_category: dict[str, int] = {}
    for operator in operators:
        by_category[operator.category] = by_category.get(operator.category, 0) + 1

    expected = {
        cm.CATEGORY_REQUIRED_REMOVAL,
        cm.CATEGORY_OPTIONAL_REMOVAL,
        cm.CATEGORY_EMPTINESS,
        cm.CATEGORY_ENUM,
        cm.CATEGORY_TYPE,
        cm.CATEGORY_UNKNOWN_FIELD,
        cm.CATEGORY_COMBINED,
    }
    assert set(by_category) == expected
    for category in expected:
        assert by_category[category] > 0, category

    # Category L is bounded, not exhaustive. Stated in the module; asserted here.
    assert by_category[cm.CATEGORY_COMBINED] <= 10


def test_catalog_is_deterministic_and_unique(operators):
    again = cm.build_operators(REPO_ROOT)
    assert [o.operator_id for o in again] == [o.operator_id for o in operators]
    ids = [o.operator_id for o in operators]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_enum_catalog_includes_a_near_miss_for_record_type(operators):
    """The near miss is the operator that would catch nearest-match guessing."""
    near = next(
        o for o in operators if o.operator_id == "violate_enum_near_miss@/record_type"
    )
    # Derived from the schema's own first permitted term, minus one character.
    assert near.steps[0].payload == "evidenc"
    assert near.expected_outcome == cm.EXPECT_INVALID


def test_unknown_field_expectation_is_read_off_each_location(operators):
    root_op = next(o for o in operators if o.operator_id == "add_unknown_field@/")
    assert root_op.expected_outcome == cm.EXPECT_INVALID
    open_op = next(
        o for o in operators if o.operator_id == "add_unknown_field@/sample/composition"
    )
    assert open_op.expected_outcome == cm.EXPECT_VALID


def test_type_violation_payload_is_outside_the_declared_types(operators):
    model = cm.introspect_schema(REPO_ROOT)
    by_path = {cm.pointer(f.path): f for f in model.fields}
    for operator in operators:
        if operator.category != cm.CATEGORY_TYPE:
            continue
        if not operator.operator_id.startswith("violate_type@"):
            continue
        entry = by_path[operator.target]
        payload = operator.steps[0].payload
        assert not cm._type_permitted(cm._json_type(payload), entry.types), operator


# --------------------------------------------------------------------------
# apply() contract
# --------------------------------------------------------------------------


def test_apply_returns_a_deep_clone_and_never_touches_the_input(corpus, operators):
    record = corpus[0]
    applied = 0
    for operator in operators:
        if not operator.applicability(record):
            continue
        before = cm.canonical(record)
        clone = operator.apply(record)
        assert cm.canonical(record) == before
        assert clone is not record
        assert not cm.shares_container(record, clone)
        assert cm.canonical(clone) != before
        applied += 1
    assert applied > 50, "the first fixture should exercise many operators"


def test_apply_raises_when_the_operator_is_not_applicable(operators):
    operator = next(
        o for o in operators if o.operator_id == "remove_required_field@/record_id"
    )
    empty: dict = {}
    assert operator.applicability(empty) is False
    with pytest.raises(ValueError):
        operator.apply(empty)


def test_array_item_template_is_unresolvable_against_an_empty_array():
    operator = cm.MutationOperator(
        operator_id="probe",
        category=cm.CATEGORY_REQUIRED_REMOVAL,
        target="/links/*/rel",
        expected_outcome=cm.EXPECT_INVALID,
        steps=(cm.MutationStep(cm.OP_REMOVE, ("links", cm.ARRAY_ITEM, "rel")),),
    )
    assert operator.applicability({"links": []}) is False
    assert operator.applicability({"links": [{"rel": "follows"}]}) is True


def test_removing_an_array_item_is_refused_structurally():
    """The targeted undo writes back by index, so deleting an element would
    overwrite a sibling rather than re-insert. Refused at construction."""
    with pytest.raises(ValueError, match="array item"):
        cm.MutationStep(cm.OP_REMOVE, ("links", cm.ARRAY_ITEM))
    with pytest.raises(ValueError, match="unknown mutation step kind"):
        cm.MutationStep("obliterate", ("links",))
    # Setting an array item is fine: the index still exists afterwards.
    assert cm.MutationStep(cm.OP_SET, ("links", cm.ARRAY_ITEM), None)


def test_overlapping_steps_make_an_operator_inapplicable():
    """An overlap would make the targeted undo ambiguous, so it is refused."""
    operator = cm.MutationOperator(
        operator_id="overlapping",
        category=cm.CATEGORY_COMBINED,
        target="/sample,/sample/material",
        expected_outcome=cm.EXPECT_INVALID,
        steps=(
            cm.MutationStep(cm.OP_REMOVE, ("sample",)),
            cm.MutationStep(cm.OP_REMOVE, ("sample", "material")),
        ),
    )
    assert operator.applicability({"sample": {"material": {}}}) is False


# --------------------------------------------------------------------------
# The full sweep
# --------------------------------------------------------------------------


def test_full_sweep_report(report, harness):
    assert report["status"] == "ok"
    assert report["report_format_version"] == cm.REPORT_FORMAT_VERSION
    assert report["schema_version"] == "1.05"
    assert len(report["schema_fingerprint"]) == 64

    assert report["corpus"] == {
        "records_scanned": 10,
        "records_passing_baseline": 10,
        "records_failing_baseline": 0,
    }

    mutations = report["mutations"]
    assert mutations["operators_defined"] == harness.operators_defined
    assert mutations["trials_attempted"] == 10 * harness.operators_defined
    assert mutations["trials_applicable"] > 1000
    assert (
        mutations["trials_applicable"] + mutations["trials_skipped_not_applicable"]
        == mutations["trials_attempted"]
    )
    assert (
        mutations["expected_outcome_matches"]
        + mutations["unexpected_outcomes"]
        + mutations["observation_only_trials"]
        == mutations["trials_applicable"]
    )

    # THE claim of this slice: over the public corpus, every mutation whose
    # outcome the schema predicts produced that outcome.
    assert mutations["unexpected_outcomes"] == 0, [
        (t.operator_id, t.observed_valid) for t in harness.unexpected[:20]
    ]
    assert mutations["expected_outcome_matches"] > 1000
    assert mutations["observation_only_trials"] > 0  # category D actually ran


def test_full_sweep_oracles_all_clean(report, harness):
    assert report["oracles"] == {
        "source_mutation_failures": 0,
        "restoration_failures": 0,
        "repeatability_failures": 0,
        "ordering_instability_failures": 0,
        "no_guessing_failures": 0,
        "workflow_consistency_failures": 0,
        "engine_disagreements": 0,
    }
    for label in (
        cm.ORACLE_SOURCE_MUTATED,
        cm.ORACLE_RESTORATION,
        cm.ORACLE_REPEATABILITY,
        cm.ORACLE_ORDERING,
        cm.ORACLE_NO_GUESSING,
        cm.ORACLE_WORKFLOW,
        cm.ORACLE_ENGINE_DISAGREEMENT,
    ):
        assert harness.oracle_failures(label) == (), label


def test_every_implemented_category_produced_applicable_trials(harness):
    seen = {t.category for t in harness.trials if t.applicable}
    assert seen == {
        cm.CATEGORY_REQUIRED_REMOVAL,
        cm.CATEGORY_OPTIONAL_REMOVAL,
        cm.CATEGORY_EMPTINESS,
        cm.CATEGORY_ENUM,
        cm.CATEGORY_TYPE,
        cm.CATEGORY_UNKNOWN_FIELD,
        cm.CATEGORY_COMBINED,
    }


def test_category_d_is_observed_never_asserted(harness):
    emptiness = [
        t
        for t in harness.trials
        if t.applicable and t.category == cm.CATEGORY_EMPTINESS
    ]
    assert emptiness
    for trial in emptiness:
        assert trial.expected_outcome == cm.EXPECT_OBSERVE_ONLY
        assert trial.outcome_matched is None
        assert trial.observation in {"valid", "invalid"}

    # Both outcomes actually occur, which is the point of the category: the
    # vendored schema does NOT reject every empty value. (Recorded, not judged —
    # the schema is upstream and authoritative; see the module docstring.)
    observations = {t.observation for t in emptiness}
    assert observations == {"valid", "invalid"}

    stayed_valid = {t.operator_id for t in emptiness if t.observation == "valid"}
    # An empty required array is accepted: neither `measurement.series` nor
    # `descriptors.outputs` declares `minItems`, so an evidence record can
    # satisfy the conditional `descriptors` requirement with zero outputs.
    assert "set_empty_array@/measurement/series" in stayed_valid
    assert "set_empty_array@/descriptors/outputs" in stayed_valid
    # `timestamps.created_utc` accepts "" and "   ". CORRECTED after review: an
    # earlier version of this comment said the field is `type: string` "with no
    # `format`/`pattern`". That is FALSE -- it declares `"format": "date-time"`,
    # as do five other paths.
    #
    # The real reason, and it is a broader finding than the one it replaces:
    # `official.py` builds `Draft202012Validator(schema)` with **no
    # `format_checker`**, so under JSON Schema `format` is annotation-only and
    # ISAAC enforces NO format constraint anywhere. `created_utc =
    # "NOT-A-DATE-AT-ALL"` validates too. This is therefore a property of OUR
    # VALIDATOR CONFIGURATION, not of the upstream schema -- unlike the three
    # observations above, which are genuinely upstream.
    #
    # Recorded rather than fixed: adding a `format_checker` would change what
    # every existing record validates as, which is a truth-path change and needs
    # its own slice and its own review.
    assert "set_empty_string@/timestamps/created_utc" in stayed_valid
    assert "set_whitespace_string@/timestamps/created_utc" in stayed_valid


# --------------------------------------------------------------------------
# Report sanitization
# --------------------------------------------------------------------------


def _strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        out: set[str] = set()
        for key, item in value.items():
            out.add(key)
            out |= _strings(item)
        return out
    if isinstance(value, list):
        out = set()
        for item in value:
            out |= _strings(item)
        return out
    return set()


def test_report_keys_are_exactly_the_frozen_allowlists(report):
    assert tuple(report) == cm._REPORT_KEYS
    assert tuple(report["corpus"]) == cm._CORPUS_KEYS
    assert tuple(report["mutations"]) == cm._MUTATION_KEYS
    assert tuple(report["oracles"]) == cm._ORACLE_KEYS


def test_report_contains_only_compile_time_strings(report, harness):
    allowed = (
        set(cm.LIMITATIONS)
        | set(cm._REPORT_KEYS)
        | set(cm._CORPUS_KEYS)
        | set(cm._MUTATION_KEYS)
        | set(cm._ORACLE_KEYS)
        | {"ok", "1.05", harness.schema_fingerprint}
    )
    assert _strings(report) <= allowed


def _allowlisted_keys() -> set[str]:
    return (
        set(cm._REPORT_KEYS)
        | set(cm._CORPUS_KEYS)
        | set(cm._MUTATION_KEYS)
        | set(cm._ORACLE_KEYS)
    )


def _scannable(value, allow_keys: set[str], out: set[str]) -> None:
    """Collect every string a leak could inhabit: leaf values, and any key that
    is NOT a frozen-allowlist name.

    Nested KEYS are deliberately in scope. The leak shape §3 of the
    authorization audit warns about is exactly a dict keyed by record-derived
    content (``by_instance_path``, ``path_presence``), so a scan that looked
    only at values would be blind to the case that matters most. Allowlisted key
    names are excluded because they are compile-time constants, proven so by
    ``test_report_keys_are_exactly_the_frozen_allowlists``.
    """
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in allow_keys:
                out.add(key)
            _scannable(item, allow_keys, out)
    elif isinstance(value, list):
        for item in value:
            _scannable(item, allow_keys, out)


def test_report_leaks_no_fixture_content(report, corpus):
    """Scan the report for distinctive strings from the fixtures.

    Each candidate string is searched inside each report string individually
    rather than inside one concatenated blob: a blob search reports matches that
    straddle two unrelated fields, and it collides with the frozen key names
    (``not_applicable`` is a real ``rhe_basis`` term AND a substring of the key
    ``trials_skipped_not_applicable``). Neither is a leak.
    """

    def leaves(value, out: set[str]) -> None:
        if isinstance(value, str):
            out.add(value)
        elif isinstance(value, dict):
            for item in value.values():
                leaves(item, out)
        elif isinstance(value, list):
            for item in value:
                leaves(item, out)

    distinctive: set[str] = set()
    for record in corpus:
        distinctive.add(record["record_id"])
        values: set[str] = set()
        leaves(record, values)
        distinctive |= {v for v in values if len(v) >= 12}

    assert len(distinctive) > 50, "the scan must actually have something to look for"

    haystack: set[str] = set()
    _scannable(report, _allowlisted_keys(), haystack)
    assert haystack, "the scan must actually have something to look at"
    for token in sorted(distinctive):
        for text in haystack:
            assert token not in text, (token, text)


def test_report_carries_no_per_operator_or_per_record_breakdown(report):
    """§3 of the authorization audit: applicability breakdowns are a
    field-presence map over the corpus. The report shape must make one
    impossible, not merely omit it today.

    Asserted structurally — every key anywhere in the report is a frozen
    allowlist name, and every value in the three count blocks is an integer — so
    there is nowhere for a per-operator or per-path table to live.
    """
    keys: set[str] = set()

    def collect(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                keys.add(key)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(report)
    assert keys == _allowlisted_keys()
    for block in ("corpus", "mutations", "oracles"):
        assert all(isinstance(v, int) for v in report[block].values()), block


def test_failure_envelope_is_projected_without_raising():
    failure = cm.build_failure_report("refused")
    assert tuple(failure) == cm._REPORT_KEYS
    assert failure["status"] == "refused"
    # The blocks a failed run cannot produce are present and null, not absent:
    # a caller must not have to guess whether a missing key means zero.
    assert failure["corpus"] is None
    assert failure["mutations"] is None
    assert failure["oracles"] is None
    assert failure["limitations"] == list(cm.LIMITATIONS)


# --------------------------------------------------------------------------
# PROVING THE ORACLES CAN FAIL
#
# Each test below breaks one thing deliberately and asserts the oracle catches
# it. Without these, `0 failures` would be an unfalsifiable claim.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _MutatesItsInputOperator(cm.MutationOperator):
    """(a) Mutates the caller's record instead of a clone."""

    def apply(self, record):
        record["record_type"] = "SYNTHETIC_TAMPERED_ZZ9"
        return record


@dataclass(frozen=True)
class _ShallowCopyOperator(cm.MutationOperator):
    """(a') Returns a SHALLOW copy — every nested container is still aliased."""

    def apply(self, record):
        return dict(record)


@dataclass(frozen=True)
class _UndeclaredSideEffectOperator(cm.MutationOperator):
    """(b) Does something its declared steps do not describe, so the targeted
    undo cannot put it back."""

    def apply(self, record):
        clone = super().apply(record)
        clone["source_type"] = "literature" if clone.get("source_type") != "literature" else "database"
        return clone


def _optional_removal_steps() -> tuple[cm.MutationStep, ...]:
    return (cm.MutationStep(cm.OP_REMOVE, ("tags",)),)


def test_oracle_catches_an_operator_that_mutates_its_input(corpus):
    record = copy.deepcopy(corpus[0])
    operator = _MutatesItsInputOperator(
        operator_id="broken_mutates_input",
        category=cm.CATEGORY_OPTIONAL_REMOVAL,
        target="/record_type",
        expected_outcome=cm.EXPECT_VALID,
        steps=(cm.MutationStep(cm.OP_SET, ("record_type",), "synthesis"),),
    )
    outcome = cm.run_trial(record, operator, REPO_ROOT, repeat=1)
    assert cm.ORACLE_SOURCE_MUTATED in outcome.oracle_failures


def test_oracle_catches_a_shallow_copy_that_aliases_the_input(corpus):
    record = copy.deepcopy(corpus[0])
    operator = _ShallowCopyOperator(
        operator_id="broken_shallow_copy",
        category=cm.CATEGORY_OPTIONAL_REMOVAL,
        target="/timestamps/created_utc",
        expected_outcome=cm.EXPECT_VALID,
        steps=(cm.MutationStep(cm.OP_REMOVE, ("timestamps", "created_utc")),),
    )
    outcome = cm.run_trial(record, operator, REPO_ROOT, repeat=1)
    # The record's bytes are untouched, so ONLY the aliasing arm can catch this.
    assert cm.canonical(record) == cm.canonical(corpus[0])
    assert cm.ORACLE_SOURCE_MUTATED in outcome.oracle_failures


def test_oracle_catches_a_mutation_that_does_not_restore(corpus):
    record = copy.deepcopy(next(r for r in corpus if "tags" in r))
    good = cm.MutationOperator(
        operator_id="honest_optional_removal",
        category=cm.CATEGORY_OPTIONAL_REMOVAL,
        target="/tags",
        expected_outcome=cm.EXPECT_VALID,
        steps=_optional_removal_steps(),
    )
    broken = _UndeclaredSideEffectOperator(
        operator_id="broken_restoration",
        category=cm.CATEGORY_OPTIONAL_REMOVAL,
        target="/tags",
        expected_outcome=cm.EXPECT_VALID,
        steps=_optional_removal_steps(),
    )

    # The honest operator with identical declared steps restores cleanly, which
    # is what makes the failure below attributable to the side effect.
    assert cm.ORACLE_RESTORATION not in cm.run_trial(
        record, good, REPO_ROOT, repeat=1
    ).oracle_failures
    assert cm.ORACLE_RESTORATION in cm.run_trial(
        record, broken, REPO_ROOT, repeat=1
    ).oracle_failures


def _evaluation(signature, *, valid=False):
    return cm.Evaluation(
        schema_valid=valid,
        error_count=len(signature),
        rule_families=tuple(sorted({s[1] for s in signature})),
        schema_paths=tuple(sorted({s[0] for s in signature})),
        signature=tuple(signature),
        engines_disagree=False,
    )


def test_oracle_catches_a_non_deterministic_result():
    """(c) Different content across runs is a repeatability failure."""
    a = _evaluation([("/record_id", "required", "missing", "m1", False)])
    b = _evaluation(
        [
            ("/record_id", "required", "missing", "m1", False),
            ("/record_type", "enum", "invalid", "m2", False),
        ]
    )
    assert cm.check_repeatability([a, a, a]) is True
    assert cm.check_repeatability([a, b, a]) is False


def test_ordering_instability_is_reported_separately_from_repeatability():
    """Same diagnostics, different order: an ORDERING failure, not a content
    failure. Reporting them under one counter would misfile the defect."""
    first = ("/a", "required", "missing", "m1", False)
    second = ("/b", "enum", "invalid", "m2", False)
    a = _evaluation([first, second])
    b = _evaluation([second, first])
    assert cm.check_repeatability([a, b]) is True
    assert cm.check_ordering_stable([a, b]) is False
    assert cm.check_ordering_stable([a, a]) is True


def test_empty_evaluation_sequence_fails_closed():
    assert cm.check_repeatability([]) is False
    assert cm.check_ordering_stable([]) is False


def test_report_projection_rejects_an_unlisted_key():
    """(d) An unlisted key can never be served, and on the success path it
    raises rather than being silently dropped."""
    built = {key: 0 for key in cm._CORPUS_KEYS}
    built["records_from_slac_postgres"] = 30
    with pytest.raises(cm.ReportKeyError):
        cm._project(built, cm._CORPUS_KEYS, strict=True)

    # Non-strict: dropped, not raised — the failure envelope is what a raise
    # degrades into, so it must not raise in turn.
    projected = cm._project(built, cm._CORPUS_KEYS, strict=False)
    assert "records_from_slac_postgres" not in projected
    assert tuple(projected) == cm._CORPUS_KEYS


def test_report_projection_rejects_a_missing_key():
    built = {key: 0 for key in cm._CORPUS_KEYS if key != "records_scanned"}
    with pytest.raises(cm.ReportKeyError):
        cm._project(built, cm._CORPUS_KEYS, strict=True)
    assert cm._project(built, cm._CORPUS_KEYS, strict=False)["records_scanned"] is None


def test_workflow_oracle_catches_an_invalid_record_reaching_export():
    """The workflow invariant holds in BOTH validity states — which is the
    property, not a weakness.

    Docstring corrected after review. It previously claimed the oracle
    "distinguishes the two validity states rather than returning True for
    everything", directly above two asserts that both expect `True`, which reads
    as the opposite of the claim. The oracle returns True whenever the workflow
    is CONSISTENT with the validity it was given; consistency is expected in
    both states, so `True, True` is correct. What makes it non-vacuous is that
    the two states produce DIFFERENT workflows — asserted below — and that
    `_workflow_consistent` would return False if either produced the other's.

    See also the function's own docstring: this is a `derive_workflow`
    regression check, not an independent per-trial oracle.
    """
    assert cm._workflow_consistent(True) is True
    assert cm._workflow_consistent(False) is True
    derived_invalid = cm.derive_workflow(
        pending_count=0, draft_ok=False, ready=False, exported=False, rev=1
    )
    assert derived_invalid["current_step"] == "review_evidence"
    derived_valid = cm.derive_workflow(
        pending_count=0, draft_ok=True, ready=True, exported=False, rev=1
    )
    assert derived_valid["current_step"] == "export"


def test_no_guessing_oracle_is_wired_to_a_real_check(corpus):
    """A removed required field must still be absent after validation, and a
    substituted enum token must still be exactly the token we wrote."""
    record = copy.deepcopy(corpus[0])
    removal = cm.MutationOperator(
        operator_id="probe_removal",
        category=cm.CATEGORY_REQUIRED_REMOVAL,
        target="/record_id",
        expected_outcome=cm.EXPECT_INVALID,
        steps=(cm.MutationStep(cm.OP_REMOVE, ("record_id",)),),
    )
    clone = removal.apply(record)
    assert "record_id" not in clone
    evaluation = cm.evaluate(clone, REPO_ROOT)
    assert evaluation.schema_valid is False
    assert "record_id" not in clone  # the validator populated nothing

    substitution = cm.MutationOperator(
        operator_id="probe_near_miss",
        category=cm.CATEGORY_ENUM,
        target="/record_type",
        expected_outcome=cm.EXPECT_INVALID,
        steps=(cm.MutationStep(cm.OP_SET, ("record_type",), "evidenc"),),
    )
    near = substitution.apply(record)
    assert cm.evaluate(near, REPO_ROOT).schema_valid is False
    # Not corrected to "evidence", not annotated, not replaced.
    assert near["record_type"] == "evidenc"

    outcome = cm.run_trial(record, substitution, REPO_ROOT, repeat=1)
    assert outcome.oracle_failures == ()
    assert outcome.outcome_matched is True


# --------------------------------------------------------------------------
# Module purity — this harness must never grow a database or a route
# --------------------------------------------------------------------------


MODULE_PATH = REPO_ROOT / "apps" / "api" / "isaac_api" / "corpus_mutation.py"


def test_module_imports_nothing_beyond_its_declared_dependencies():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
    assert imported == {
        "copy",
        "json",
        "dataclasses",
        "pathlib",
        "typing",
        "__future__",
        "isaac_records.diagnostics",
        "isaac_records.official",
        ".workflow",
    }


def _module_code_without_prose() -> str:
    """The module's executable code with every docstring removed.

    Comments and docstrings discuss ``datetime``, ``random`` and ``psycopg`` in
    order to say the module must not use them — so a naive text scan of the raw
    file fails on its own safety documentation. Stripping prose keeps the scan
    pointed at code.
    """
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_module_contains_no_database_network_route_or_clock_surface():
    code = _module_code_without_prose()
    assert "def run_harness" in code, "the stripped source must still be the module"
    for token in (
        "psycopg",
        "libpq",
        "PGHOST",
        "PGPASSWORD",
        "connect(",
        "socket",
        "urllib",
        "requests.",
        "subprocess",
        "os.environ",
        "getenv",
        "fastapi",
        "APIRouter",
        "@router",
        "datetime",
        "time.time",
        "random",
        "uuid",
        "open(",
        "write_text",
    ):
        assert token not in code, token


def test_module_declares_the_unimplemented_categories_and_why():
    doc = cm.__doc__ or ""
    assert "NOT YET IMPLEMENTED, AND WHY" in doc
    for category in ("**B ", "**H ", "**I ", "**J ", "**K "):
        assert category in doc, category
    # The blocked real-corpus runner must stay named and blocked.
    assert "BLOCKED" in doc


def test_no_route_references_this_module():
    """This slice is library + tests only. A route would change the disclosure
    question entirely (audit §3), so its absence is asserted, not assumed."""
    routes = (REPO_ROOT / "apps" / "api" / "isaac_api" / "routes.py").read_text(
        encoding="utf-8"
    )
    assert "corpus_mutation" not in routes


# --- review-mandated guards (independent security/quality review, 2026-08-02) --


def test_failure_report_never_echoes_a_caller_supplied_status():
    """`build_failure_report` must not become a leak channel.

    Review finding: it echoed `status` verbatim on the documented understanding
    that "callers must pass a constant". Nothing enforced it, and the natural
    database-backed caller is `except Exception as exc:
    build_failure_report(str(exc))` -- which would put a connection string, a
    host, or a record id straight into the served envelope. That is exactly the
    leak the rest of this module is engineered to prevent, so the contract is
    mechanical now, and this test is what makes it stay that way.
    """
    hostile = "error: could not connect to isaac-psql-rw as 01D2Z6B3Y1K8M4P7Q2R5T9V0WX"
    report = cm.build_failure_report(hostile)
    assert report["status"] == "error"
    assert "isaac-psql-rw" not in json.dumps(report)
    assert "01D2Z6B3Y1K8M4P7Q2R5T9V0WX" not in json.dumps(report)
    # Every allowlisted status still passes through unchanged.
    for status in cm.FAILURE_STATUSES:
        assert cm.build_failure_report(status)["status"] == status


def test_a_raising_operator_does_not_abort_the_sweep():
    """Fail-closed must include the closing.

    Review proved a pathological operator raised straight out of `run_trial`,
    aborting the whole sweep and producing no report at all -- fail-closed was
    designed but not wired. A raising operator is now one unexpected outcome and
    the run continues. The exception is deliberately NOT recorded: its text
    could carry a record value.
    """

    class Exploding(cm.MutationOperator):
        """Raises out of `apply`, which previously aborted the whole sweep."""

        def applicability(self, record):
            return True

        def apply(self, record):
            raise KeyError("a value that must never be serialized")

    good = cm.build_operators(REPO_ROOT)[0]
    boom = Exploding(
        operator_id="zz_exploding_operator",
        category=good.category,
        target=good.target,
        expected_outcome=good.expected_outcome,
        steps=good.steps,
    )
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    ][:1]
    result = cm.run_harness(records, REPO_ROOT, operators=[good, boom], repeat=1)
    report = cm.build_report(result)
    assert report["status"] == "ok"
    assert report["mutations"]["unexpected_outcomes"] >= 1
    # And nothing from the exception reached the payload.
    assert "KeyError" not in json.dumps(report)
    assert "zz_exploding_operator" not in json.dumps(report)
