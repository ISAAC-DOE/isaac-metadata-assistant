"""The datastore-backed verification mode, and the cache that fronts it.

NO CONNECTION IS OPENED ANYWHERE IN THIS FILE. Every "datastore" here is a
:class:`FakeRecordProvider` -- a plain Python object yielding dicts -- so the
whole suite runs with no driver installed, which is the case in this
interpreter.

The theme, inherited from ``test_verification.py``: the report must not be able
to assert more than it measured. The datastore mode raises the stakes, because
four safeguards that were honestly ``not_applicable`` in the public mode become
claims about a real transaction.
"""

from __future__ import annotations

import json
import pickle
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

from isaac_api import verification
from isaac_api.verification import (
    AUTHORIZED_PRIVATE_SAMPLE,
    PUBLIC_REFERENCE,
    VerificationState,
    load_public_corpus,
    run_verification,
)

ROOT = Path(__file__).resolve().parents[3]

#: Distinctive enough that a substring search for it is meaningful, and long
#: enough to clear the leak scan's minimum length.
SENTINEL = "ZZ9-SYNTHETIC-PRIVATE-VALUE-THAT-MUST-NEVER-BE-SERVED"


class FakeRecordProvider:
    """Stands in for ``db_provider.DatastoreRecordProvider``.

    Exposes exactly the attributes ``verification`` reads, so a change in what
    the report expects from a provider shows up here rather than only against a
    real datastore nobody can run in CI.
    """

    def __init__(
        self,
        records,
        *,
        state="ok",
        read_only_verified=True,
        parameterized_only=True,
        dml_statements=0,
        ddl_statements=0,
    ) -> None:
        self._records = [json.loads(json.dumps(r)) for r in records]
        self.state = state
        self.read_only_verified = read_only_verified
        self.parameterized_only = parameterized_only
        self.dml_statements = dml_statements
        self.ddl_statements = ddl_statements
        self.calls = 0
        self.max_alive = 0

    def records(self):
        self.calls += 1
        for record in self._records:
            # A real provider holds one parsed record at a time; this one proves
            # the ENGINE never asks for more than one at a time either.
            self.max_alive = max(self.max_alive, 1)
            yield record


class ExplodingProvider:
    """Any use at all is a failure. Used to prove the public mode ignores it."""

    state = "ok"

    def records(self):  # pragma: no cover - must never be called
        raise AssertionError("the public mode reached for a datastore provider")


@pytest.fixture(scope="module")
def public_records() -> list[dict]:
    return [json.loads(json.dumps(r)) for r in load_public_corpus(ROOT)[:2]]


@pytest.fixture(scope="module")
def private_report(public_records) -> dict:
    """One real sweep through the datastore mode, shared across tests."""
    provider = FakeRecordProvider(public_records)
    return run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )


# ---------------------------------------------------------------------------
# Which source each mode uses
# ---------------------------------------------------------------------------


def test_the_public_mode_needs_no_datastore_at_all():
    """A provider passed to the public mode must be ignored, not merely unused.

    The failure this prevents is a refactor that "helpfully" prefers a provider
    when one is present, which would silently move the public figure onto
    private data.
    """
    report = run_verification(
        ROOT, mode=PUBLIC_REFERENCE, provider=ExplodingProvider(), repeat=1
    )
    assert report["status"] == "ok"
    assert report["metadata"]["verification_mode"] == PUBLIC_REFERENCE
    assert report["metadata"]["corpus_size"] == 10


def test_the_datastore_mode_reads_only_the_approved_provider(
    monkeypatch, public_records
):
    """It must not fall back to the fixtures, and must not top up from them."""

    def forbidden(root):  # pragma: no cover - must never be called
        raise AssertionError("the datastore mode loaded the public fixture corpus")

    monkeypatch.setattr(verification, "load_public_corpus", forbidden)
    provider = FakeRecordProvider(public_records)
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    assert provider.calls == 1
    assert report["metadata"]["corpus_size"] == 2
    assert report["metadata"]["verification_mode"] == AUTHORIZED_PRIVATE_SAMPLE


def test_the_datastore_mode_without_a_provider_is_unavailable_not_public():
    """Fail-closed. The dangerous fallback is the convenient one."""
    report = run_verification(ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, repeat=1)
    assert report["status"] == "unavailable"
    assert report["metadata"] is None


def test_an_unknown_mode_is_refused():
    report = run_verification(ROOT, mode="whatever_corpus", repeat=1)
    assert report["status"] == "refused"


def test_one_engine_serves_both_modes():
    """The modes must differ ONLY in the record source.

    Asserted structurally: there is exactly one sweep function and one report
    builder, and `run_verification` chooses a stream rather than a code path.
    A second validation or mutation implementation is the thing this forbids.
    """
    source = Path(verification.__file__).read_text(encoding="utf-8")
    assert source.count("def _sweep(") == 1
    assert source.count("def build_report(") == 1
    assert source.count("corpus_mutation.run_harness(") == 1
    assert source.count("shadow_validate(") == 1
    assert source.count("validate_official(") == 1


# ---------------------------------------------------------------------------
# The safeguards, which are now measurements
# ---------------------------------------------------------------------------


def test_the_transport_safeguards_are_read_off_the_provider(private_report):
    safeguards = private_report["safeguards"]
    assert safeguards["transaction_read_only"] == "verified"
    assert safeguards["parameterized_queries_only"] == "verified"
    assert safeguards["dml_statements"] == 0
    assert safeguards["ddl_statements"] == 0


def test_an_unverified_read_only_transaction_degrades_the_safeguard(public_records):
    """THE most important assertion in this file.

    `transaction_read_only: "verified"` is only allowed to appear because a
    server read-back confirmed it. A provider that did not verify must produce
    `unverified`, never the word the happy path produces.
    """
    provider = FakeRecordProvider(public_records, read_only_verified=False)
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    assert report["safeguards"]["transaction_read_only"] == "unverified"


def test_a_provider_missing_the_attribute_entirely_degrades_rather_than_passes():
    """`getattr(..., False)` must not become a pass by omission."""

    class Minimal:
        state = "ok"

        def records(self):
            return iter(())

    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=Minimal(), repeat=1
    )
    assert report["safeguards"]["transaction_read_only"] == "unverified"
    assert report["safeguards"]["parameterized_queries_only"] == "unverified"
    assert report["safeguards"]["dml_statements"] == 0


def test_counted_writes_are_reported_as_counted(public_records):
    """The counts come from the policy guard, so a blocked write is VISIBLE.

    A report that could only ever say zero would be an assertion wearing a
    measurement's clothes.
    """
    provider = FakeRecordProvider(public_records, dml_statements=1, ddl_statements=2)
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    assert report["safeguards"]["dml_statements"] == 1
    assert report["safeguards"]["ddl_statements"] == 2


def test_a_boolean_dressed_as_a_count_is_not_accepted(public_records):
    """`True` is an `int` in Python. It must not become `1` statements."""
    provider = FakeRecordProvider(public_records)
    provider.dml_statements = True
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    assert report["safeguards"]["dml_statements"] == 0


def test_the_truth_path_safeguards_hold_in_this_mode_too(private_report):
    assert private_report["safeguards"]["official_validator_unchanged"] == "verified"
    assert private_report["safeguards"]["export_gating_unchanged"] == "verified"


def test_the_source_objects_are_not_modified_by_the_sweep(public_records):
    """Two independent measurements, both asserted.

    The harness's own per-trial oracle, and this module's before/after
    comparison of each source object. The second exists because the first is
    checked by the code under test.
    """
    provider = FakeRecordProvider(public_records)
    before = json.dumps(provider._records, sort_keys=True)
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    assert json.dumps(provider._records, sort_keys=True) == before
    assert report["oracles"]["source_mutation_failures"] == 0
    assert report["safeguards"]["source_records_modified"] == "verified"


def test_the_engine_holds_one_record_at_a_time(private_report, public_records):
    """The provider records how many it was ever asked to have alive at once."""
    provider = FakeRecordProvider(public_records)
    run_verification(ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1)
    assert provider.max_alive == 1


# ---------------------------------------------------------------------------
# The numbers, and the accounting
# ---------------------------------------------------------------------------


def test_the_mutation_accounting_reconciles_exactly(private_report):
    """The identities `test_corpus_mutation.py:318-334` pins, re-asserted over a
    streamed corpus.

    They survive the per-record invocation because they are per-trial and
    additive; if summing ever broke them, this is where it shows.
    """
    mutations = private_report["mutations"]
    assert mutations["trials_attempted"] == (
        mutations["trials_applicable"] + mutations["trials_skipped_not_applicable"]
    )
    assert mutations["trials_applicable"] == (
        mutations["expected_outcome_matches"]
        + mutations["unexpected_outcomes"]
        + mutations["observation_only_trials"]
    )
    assert mutations["trials_applicable"] > 0
    assert mutations["unexpected_outcomes"] == 0


def test_every_oracle_passed(private_report):
    for key, value in private_report["oracles"].items():
        assert value == 0, f"oracle {key} failed {value} times"


def test_the_corpus_block_matches_the_sample_size(private_report):
    assert private_report["corpus"]["records_scanned"] == 2
    assert private_report["metadata"]["corpus_size"] == 2
    assert (
        private_report["corpus"]["records_passing_baseline"]
        + private_report["corpus"]["records_failing_baseline"]
        == 2
    )


def test_the_run_is_deterministic(public_records):
    """Same records in, same report out -- apart from the two fields that are
    supposed to differ."""
    volatile = {"generated_at", "duration_ms", "cache_age_seconds"}

    def stripped(report):
        clone = json.loads(json.dumps(report))
        for key in volatile:
            clone["metadata"].pop(key, None)
        return clone

    first = run_verification(
        ROOT,
        mode=AUTHORIZED_PRIVATE_SAMPLE,
        provider=FakeRecordProvider(public_records),
        repeat=1,
    )
    second = run_verification(
        ROOT,
        mode=AUTHORIZED_PRIVATE_SAMPLE,
        provider=FakeRecordProvider(public_records),
        repeat=1,
    )
    assert stripped(first) == stripped(second)


def test_an_empty_sample_produces_a_report_rather_than_a_crash():
    report = run_verification(
        ROOT,
        mode=AUTHORIZED_PRIVATE_SAMPLE,
        provider=FakeRecordProvider([]),
        repeat=1,
    )
    assert report["status"] == "ok"
    assert report["metadata"]["corpus_size"] == 0
    assert report["mutations"]["trials_attempted"] == 0


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


def test_no_value_from_the_sample_reaches_the_report(public_records):
    """A planted sentinel and a real identifier, neither of which may appear."""
    seeded = json.loads(json.dumps(public_records[0]))
    seeded.setdefault("sample", {}).setdefault("material", {})["notes"] = SENTINEL
    provider = FakeRecordProvider([seeded, public_records[1]])
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    serialized = json.dumps(report)
    assert SENTINEL not in serialized
    assert seeded["record_id"] not in serialized
    assert report["safeguards"]["private_values_exposed"] == "verified"


def test_the_structural_audit_rejects_a_string_it_cannot_account_for(private_report):
    """The audit is an allowlist, not a denylist: a string with no PUBLIC
    explanation fails it, whether or not anyone anticipated that string."""
    assert verification._structural_string_audit(private_report, ROOT) is True

    tampered = json.loads(json.dumps(private_report))
    tampered["format_shadow"]["failures_by_schema_path"]["cells"].append(
        {"key": "/properties/no_such_property_zz9", "count": 7}
    )
    assert verification._structural_string_audit(tampered, ROOT) is False


def test_a_served_schema_pointer_must_actually_resolve_in_the_vendored_schema():
    """`the schema may describe the data; the data may not describe itself`.

    Checking that a pointer RESOLVES is how that stops being an assumption: a
    pointer that does not resolve did not come from the schema.
    """
    schema = verification._vendored_schema(ROOT)
    assert verification._schema_pointer_resolves("", schema) is True
    assert verification._schema_pointer_resolves("/properties", schema) is True
    assert verification._schema_pointer_resolves("/properties/timestamps", schema) is True
    assert verification._schema_pointer_resolves("/properties/zz9_nope", schema) is False
    assert verification._schema_pointer_resolves("properties", schema) is False


def test_the_canary_fires_so_the_audit_is_not_a_no_op(private_report):
    """The runtime negative control. If the audit were weakened into a no-op it
    would still report "no leak found", and this is what notices."""
    assert verification._canary_is_detected(private_report, ROOT) is True

    class Blind:
        """An audit that accepts everything must make the canary fail."""

    original = verification._structural_string_audit
    verification._structural_string_audit = lambda payload, root: True
    try:
        assert verification._canary_is_detected(private_report, ROOT) is False
    finally:
        verification._structural_string_audit = original


def test_the_privacy_safeguard_degrades_when_a_measurement_fails(private_report):
    original = verification._structural_string_audit
    verification._structural_string_audit = lambda payload, root: False
    try:
        assert verification._privacy_holds(private_report, None, ROOT) is False
    finally:
        verification._structural_string_audit = original


def test_a_crashing_measurement_is_not_a_pass(private_report):
    """"The check crashed" and "the check succeeded" must not produce the same
    word."""
    original = verification._structural_string_audit

    def boom(payload, root):
        raise RuntimeError("measurement failed")

    verification._structural_string_audit = boom
    try:
        assert verification._privacy_holds(private_report, None, ROOT) is False
    finally:
        verification._structural_string_audit = original


@pytest.mark.parametrize(
    "planted",
    [
        "9f" * 32,                      # a sha256-shaped digest: a raw_data pointer
        "deadbeef",                     # short hex: what `^[0-9a-f]{8,64}$` admitted
        "a" * 32,                       # a 32-char hex string
        "2019-03-14T09:12:44Z",         # exactly what `created_utc` looks like
        "/properties/not_a_real_zz9",   # pointer-SHAPED but does not resolve
    ],
)
def test_the_audit_rejects_strings_that_merely_LOOK_like_report_content(
    planted, private_report
):
    """I1 REGRESSION. The audit used to admit two whole SHAPES.

    `_TIMESTAMP_RE` and `_HEX_DIGEST_RE` were pure shape checks, and those are
    precisely the shapes an ISAAC record carries -- a `raw_data` sha256 pointer
    and `timestamps.created_utc`. An adversarial review got a real digest,
    `deadbeef`, a 32-character hex string and `2019-03-14T09:12:44Z` all
    ADMITTED, while the docstring claimed there was "deliberately no 'looks
    harmless' branch" and there were two.

    That mattered most in the datastore mode, where `_leak_scan` cannot run
    (the corpus is not retained) and this audit is the ONLY string-level privacy
    check.

    Both are now equality tests against what THIS run emitted, so a *different*
    digest or timestamp fails.
    """
    tampered = json.loads(json.dumps(private_report))
    tampered["format_shadow"]["failures_by_error_code"]["cells"].append(
        {"key": planted, "count": 9}
    )
    assert verification._structural_string_audit(tampered, ROOT) is False


def test_the_audit_still_admits_the_two_values_this_run_really_emitted(private_report):
    """The other half: the tightening must not make a correct report fail.

    The fingerprint is admitted because it is RECOMPUTED from the vendored
    schema's bytes, not read back out of the payload -- so a digest that came
    from a record cannot whitelist itself.
    """
    from isaac_api import corpus_mutation

    assert verification._structural_string_audit(private_report, ROOT) is True
    assert private_report["schema_fingerprint"] == corpus_mutation.schema_fingerprint(
        ROOT
    )

    # Swapping in a DIFFERENT well-formed digest fails, which is the whole point.
    tampered = json.loads(json.dumps(private_report))
    tampered["schema_fingerprint"] = "0" * 64
    assert verification._structural_string_audit(tampered, ROOT) is False


def test_the_canary_covers_the_shapes_that_were_actually_admitted():
    """The original canary was an uppercase English sentence -- no plausible
    admission rule would ever have accepted it, so it proved only that the audit
    was not completely inert. It could not have caught the defect above."""
    assert len(verification._CANARY_SENTINELS) >= 5
    assert any(
        len(s) == 64 and all(c in "0123456789abcdef" for c in s)
        for s in verification._CANARY_SENTINELS
    )
    assert any(
        verification._TIMESTAMP_RE.match(s) for s in verification._CANARY_SENTINELS
    )


def test_no_instance_path_distribution_is_computed_into_the_served_report(
    private_report,
):
    """`by_instance_path` shipped in v0.0.32 and was withdrawn: over a small
    corpus an error count of 1 at an instance path is a single-record fact."""
    serialized = json.dumps(private_report)
    assert "instance_path" not in serialized
    assert "by_instance_path" not in serialized
    assert "path_presence" not in serialized


def test_floor_suppression_runs_in_the_datastore_mode_unconditionally(public_records):
    """A gate that arms only for the private corpus is a gate someone forgets to
    arm -- so it is armed in both. Here it is armed and it BITES: one shadow
    failure over a two-record sample is far below the floor, so nothing is
    published and the withholding is disclosed.

    The same record still passes OFFICIAL validation, because the shadow is
    advisory and `format` enforcement is not armed (Q20).
    """
    bad = json.loads(json.dumps(public_records[0]))
    bad["timestamps"]["created_utc"] = "not-a-date"
    provider = FakeRecordProvider([bad, public_records[1]])
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )

    shadow = report["format_shadow"]
    assert shadow["records_failing"] >= 1
    for name in ("failures_by_error_code", "failures_by_schema_path"):
        histogram = shadow[name]
        assert histogram["floor"] == 5
        assert histogram["cells"] == [], name
        assert histogram["suppressed_categories"] >= 1, name

    assert report["official_validation"]["passing"] == 2
    assert report["official_validation"]["failing"] == 0


def test_a_lone_sub_floor_category_reaches_the_wire_with_its_count_withheld(
    public_records,
):
    """THE LEAK, END TO END — the shape the deployment actually produces.

    The test above proves the floor bites; this one proves what is served when
    it bites all the way down. ONE record with ONE format finding leaves exactly
    one withheld category and nothing published, which is the single input shape
    `disclosure.suppress_small_cells` cannot break up (there is no published cell
    to absorb). Its honest return is that key's exact count, and
    `disclosure.py`'s docstring delegates the withholding to the caller —
    `verification._histogram`, which until now published the number.

    So the served body carried a sub-floor count against a universe an observer
    enumerates from the vendored public schema. Over the authorized 30-record
    corpus this is not a corner case: one record with one finding produces it.

    Asserted on the SERVED report rather than on `_histogram`, because a unit
    test of the helper cannot show the shape is reachable through the run.
    """
    bad = json.loads(json.dumps(public_records[0]))
    bad["timestamps"]["created_utc"] = "not-a-date"
    provider = FakeRecordProvider([bad, public_records[1]])
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )

    lone = [
        (name, hist)
        for name in ("failures_by_error_code", "failures_by_schema_path")
        for hist in [report["format_shadow"][name]]
        if hist["suppressed_categories"] == 1
    ]
    assert lone, (
        "this fixture is supposed to REACH the single-withheld-category shape; "
        "if it no longer does, the regression is untested rather than fixed"
    )
    for name, hist in lone:
        assert hist["cells"] == [], name
        assert hist["suppressed_total"] is None, (
            f"{name} served the lone withheld category's exact count "
            f"({hist['suppressed_total']}) -- that number IS the cell"
        )
        assert hist["suppressed_categories"] == 1, (
            "the withholding must stay disclosed, not be hidden by reporting 0"
        )

    # And it survives serialization as JSON `null`, not as a dropped key: the
    # frontend decoder distinguishes an explicit null (withheld) from an absent
    # field (malformed body it must refuse).
    for name, _ in lone:
        assert (
            '"suppressed_total": null'
            in json.dumps(report["format_shadow"][name], indent=0).replace("\n", " ")
        )


# ---------------------------------------------------------------------------
# Withdrawal must be complete
# ---------------------------------------------------------------------------


def _modes_named_in(payload) -> set[str]:
    """Every mode name that appears anywhere in the served text."""
    text = json.dumps(payload)
    universe = {
        verification.PUBLIC_REFERENCE,
        verification.AUTHORIZED_PRIVATE_SAMPLE,
    }
    return {name for name in universe if name in text}


def test_a_served_report_never_names_a_mode_this_build_does_not_offer(private_report):
    assert _modes_named_in(private_report) <= set(verification.VERIFICATION_MODES)


def test_after_withdrawal_the_public_report_stops_advertising_the_removed_mode(
    monkeypatch,
):
    """I4 REGRESSION, and it goes to the heart of this design's headline claim.

    With the approval flag cleared the engine really does go clean -- the mode is
    refused everywhere and no connection can be opened. But a shared
    `LIMITATIONS` line NAMED `authorized_private_sample` and was published in
    BOTH modes, so a build that no longer had the mode kept telling every reader
    it did. A false disclosure surviving the exact withdrawal path the whole
    derived-mode-tuple argument is about.
    """
    from isaac_api import authorization

    monkeypatch.setattr(
        authorization, "Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED", False
    )
    monkeypatch.setattr(
        verification, "VERIFICATION_MODES", (verification.PUBLIC_REFERENCE,)
    )

    report = run_verification(ROOT, mode=PUBLIC_REFERENCE, repeat=1)
    assert report["status"] == "ok"
    assert AUTHORIZED_PRIVATE_SAMPLE not in json.dumps(report)
    assert _modes_named_in(report) == {verification.PUBLIC_REFERENCE}

    # And the mode is genuinely gone, not merely unmentioned.
    assert run_verification(ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, repeat=1)["status"] == (
        "refused"
    )


def test_the_shared_limitations_name_no_mode_at_all():
    """The shared block is published in every mode, so it must be true in every
    mode. Naming any single mode there is what caused the defect above."""
    for line in verification.LIMITATIONS:
        assert verification.AUTHORIZED_PRIVATE_SAMPLE not in line
        assert verification.PUBLIC_REFERENCE not in line


# ---------------------------------------------------------------------------
# Retained state is bounded by the contract, not by the corpus
# ---------------------------------------------------------------------------


def test_the_sweep_retains_counters_and_not_trials(public_records):
    """I6 REGRESSION. `_SweepResult` used to accumulate every `TrialOutcome`.

    Measured by review: 1510 trials for 2 records at ~497 B, so roughly 188 MB at
    the shipped ceiling of 500 records. No record content was in them, so this
    was resource and not disclosure -- but `MAX_RECORDS_CEILING` claimed to keep
    a large table out of pod memory while bounding only the raw rows, not the
    755-operators-by-N structure derived from them.

    The retained state is now bounded by the FROZEN KEY TUPLES, so it cannot grow
    in the corpus dimension at all.
    """
    from isaac_api import corpus_mutation

    small = verification._sweep(iter(public_records[:1]), ROOT, repeat=1)
    large = verification._sweep(iter(public_records), ROOT, repeat=1)

    for sweep in (small, large):
        for name, value in vars(sweep).items():
            assert isinstance(value, (str, int, Counter)), (name, type(value))
            if isinstance(value, Counter):
                for key in value:
                    assert isinstance(key, str)

    # The counter key sets are the frozen contract keys, identical regardless of
    # how many records were swept. `by_code`/`by_schema_path` are keyed by the
    # closed error-code vocabulary and by schema pointers, neither of which grows
    # with the corpus.
    assert set(small.corpus) == set(large.corpus) == set(verification._CORPUS_KEYS)
    assert set(small.mutations) == set(large.mutations)
    assert set(small.mutations) <= set(corpus_mutation._MUTATION_KEYS)
    assert set(small.oracles) == set(large.oracles) == set(corpus_mutation._ORACLE_KEYS)

    # And the sweep result is measurably the same size for 1 record and for many.
    assert len(pickle.dumps(small)) == pytest.approx(len(pickle.dumps(large)), abs=200)

    # Nothing reachable from it is a trial.
    assert "TrialOutcome" not in repr(vars(small))


# ---------------------------------------------------------------------------
# Provider failure never becomes a partial report
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider_state, expected_status",
    [
        ("unavailable", "unavailable"),
        ("timeout", "unavailable"),
        ("refused", "refused"),
        ("error", "error"),
        ("not_run", "unavailable"),
        ("something_new", "error"),
    ],
)
def test_a_failed_provider_yields_a_status_envelope_not_an_aggregate(
    provider_state, expected_status, public_records
):
    """Whatever the provider managed to yield is DISCARDED.

    Publishing a partial sweep as a report would put a number on screen that
    describes a fraction of the corpus while claiming to describe the corpus.
    """
    provider = FakeRecordProvider(public_records, state=provider_state)
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    assert report["status"] == expected_status
    assert report["metadata"] is None
    assert report["corpus"] is None
    assert report["safeguards"] is None


def test_the_failure_envelope_still_carries_the_frozen_key_set(public_records):
    provider = FakeRecordProvider(public_records, state="refused")
    report = run_verification(
        ROOT, mode=AUTHORIZED_PRIVATE_SAMPLE, provider=provider, repeat=1
    )
    assert list(report) == list(verification._ENVELOPE_KEYS)
    assert any("bounded sample" in line for line in report["limitations"])


# ---------------------------------------------------------------------------
# The cache in front of all of this
# ---------------------------------------------------------------------------


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture(scope="module")
def ok_payload(public_records) -> dict:
    return run_verification(
        ROOT,
        mode=AUTHORIZED_PRIVATE_SAMPLE,
        provider=FakeRecordProvider(public_records),
        repeat=1,
    )


def test_the_first_call_is_answered_running_and_never_blocks(ok_payload):
    calls = []

    def runner(root, *, mode, provider=None):
        calls.append(mode)
        return json.loads(json.dumps(ok_payload))

    state = VerificationState(ROOT, runner=runner)
    assert state.get()["status"] == "running"
    assert _wait_until(lambda: len(calls) == 1)


def test_a_cache_hit_states_its_age(ok_payload):
    def runner(root, *, mode, provider=None):
        return json.loads(json.dumps(ok_payload))

    state = VerificationState(ROOT, runner=runner)
    state.get()
    assert _wait_until(lambda: state.get()["status"] == "ok")
    served = state.get()
    assert served["status"] == "ok"
    assert isinstance(served["metadata"]["cache_age_seconds"], int)
    assert served["metadata"]["cache_age_seconds"] >= 0


def test_a_stale_entry_is_served_while_a_refresh_runs(ok_payload):
    """Stale-while-refresh. A slightly old measurement beats a blank panel, and
    its age is stated rather than hidden."""
    calls = []

    def runner(root, *, mode, provider=None):
        calls.append(mode)
        payload = json.loads(json.dumps(ok_payload))
        payload["metadata"]["duration_ms"] = len(calls)
        return payload

    state = VerificationState(
        ROOT, ttl_seconds=0, min_refresh_interval_seconds=0, runner=runner
    )
    state.get()
    assert _wait_until(lambda: state.get()["status"] == "ok")
    served = state.get()
    assert served["status"] == "ok"  # served immediately, not `running`
    assert _wait_until(lambda: len(calls) >= 2)


def test_a_second_caller_joins_the_run_instead_of_starting_one(ok_payload):
    """Single-flight. One run means one connection, which is what keeps a
    connection limit of 5 out of reach."""
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def runner(root, *, mode, provider=None):
        calls.append(mode)
        entered.set()
        release.wait(5)
        return json.loads(json.dumps(ok_payload))

    state = VerificationState(ROOT, min_refresh_interval_seconds=0, runner=runner)
    assert state.get()["status"] == "running"
    assert entered.wait(5)
    assert state.get()["status"] == "running"
    assert state.get()["status"] == "running"
    release.set()
    assert _wait_until(lambda: state.get()["status"] == "ok")
    assert calls == [PUBLIC_REFERENCE]


def test_a_refresh_is_rate_limited_even_when_the_cache_is_empty():
    """A source that fails fast must not be retried on every request."""
    calls = []

    def runner(root, *, mode, provider=None):
        calls.append(mode)
        return verification.build_pending_report("unavailable", mode=mode)

    state = VerificationState(
        ROOT, ttl_seconds=0, min_refresh_interval_seconds=3600, runner=runner
    )
    assert state.get()["status"] == "running"
    # Wait for the STATUS to settle, not for the call count: the count is
    # incremented on entry to the runner, so it reaches 1 while the worker is
    # still in flight and `running` is still the honest answer.
    assert _wait_until(lambda: state.get()["status"] == "unavailable")
    for _ in range(5):
        assert state.get()["status"] == "unavailable"
    assert len(calls) == 1


def test_a_failed_refresh_preserves_the_last_known_safe_aggregate(ok_payload):
    """THE cache assertion that matters.

    A datastore that goes away must leave the last successful aggregate on
    screen, ageing visibly, rather than blanking it. The cache is written only
    on `status == "ok"`.
    """
    calls = []

    def runner(root, *, mode, provider=None):
        calls.append(mode)
        if len(calls) == 1:
            return json.loads(json.dumps(ok_payload))
        return verification.build_pending_report("unavailable", mode=mode)

    state = VerificationState(
        ROOT, ttl_seconds=0, min_refresh_interval_seconds=0, runner=runner
    )
    state.get()
    assert _wait_until(lambda: state.get()["status"] == "ok")

    # Every `get` here starts a refresh (ttl 0, no rate limit) and every refresh
    # after the first FAILS. The polling has to be explicit: a wait loop that did
    # not call `get` would never trigger another refresh, and the test would
    # prove nothing while appearing to.
    served = state.get()
    for _ in range(40):
        if len(calls) >= 3:
            break
        time.sleep(0.02)
        served = state.get()

    assert len(calls) >= 3, calls
    assert served["status"] == "ok"
    assert served["metadata"]["corpus_size"] == ok_payload["metadata"]["corpus_size"]


def test_a_runner_that_raises_never_escapes_and_never_clobbers_the_cache(ok_payload):
    calls = []

    def runner(root, *, mode, provider=None):
        calls.append(mode)
        if len(calls) == 1:
            return json.loads(json.dumps(ok_payload))
        raise RuntimeError("/Users/someone/secret/path exploded")

    state = VerificationState(
        ROOT, ttl_seconds=0, min_refresh_interval_seconds=0, runner=runner
    )
    state.get()
    assert _wait_until(lambda: state.get()["status"] == "ok")

    served = state.get()
    for _ in range(40):
        if len(calls) >= 3:
            break
        time.sleep(0.02)
        served = state.get()

    assert len(calls) >= 3, calls
    assert served["status"] == "ok"
    # The exception text is never captured: it could carry a path, a credential
    # or a record value.
    assert "secret" not in json.dumps(served)


def test_the_datastore_mode_cannot_run_without_an_injected_provider_factory():
    """Fail-closed by construction: no factory, nothing to open.

    The rate limit is left at a real value on purpose. With it at zero every
    call would start a fresh attempt and the answer would be a permanent
    `running` — which is exactly the behaviour the rate limit exists to prevent
    against a source that fails fast.
    """
    state = VerificationState(ROOT, min_refresh_interval_seconds=3600)
    assert state.get(AUTHORIZED_PRIVATE_SAMPLE)["status"] == "running"
    assert _wait_until(
        lambda: state.get(AUTHORIZED_PRIVATE_SAMPLE)["status"] == "unavailable"
    )
    # And it stays that way rather than hammering a source that is not there.
    assert state.get(AUTHORIZED_PRIVATE_SAMPLE)["status"] == "unavailable"


def test_the_provider_factory_is_called_once_per_run(ok_payload, public_records):
    made = []

    def factory():
        provider = FakeRecordProvider(public_records)
        made.append(provider)
        return provider

    seen = []

    def runner(root, *, mode, provider=None):
        seen.append(provider)
        return json.loads(json.dumps(ok_payload))

    state = VerificationState(
        ROOT, provider_factory=factory, min_refresh_interval_seconds=0, runner=runner
    )
    state.get(AUTHORIZED_PRIVATE_SAMPLE)
    assert _wait_until(lambda: len(made) == 1)
    assert seen[0] is made[0]
    # The public mode is served by the same state object and must get NO provider.
    state.get(PUBLIC_REFERENCE)
    assert _wait_until(lambda: len(seen) == 2)
    assert seen[1] is None


def test_the_cache_is_bounded_by_the_closed_mode_vocabulary(ok_payload):
    def runner(root, *, mode, provider=None):
        return json.loads(json.dumps(ok_payload))

    state = VerificationState(
        ROOT, provider_factory=lambda: FakeRecordProvider([]), runner=runner
    )
    for _ in range(20):
        state.get(PUBLIC_REFERENCE)
        state.get(AUTHORIZED_PRIVATE_SAMPLE)
        state.get("not_a_mode")
    assert _wait_until(lambda: len(state._cached) == 2)
    assert set(state._cached) <= set(verification.VERIFICATION_MODES)
    assert len(state._cached) <= len(verification.VERIFICATION_MODES)


def test_an_unknown_mode_is_refused_by_the_cache_not_silently_downgraded():
    state = VerificationState(ROOT, runner=lambda *a, **k: {})
    assert state.get("private_corpus")["status"] == "refused"


def test_only_the_projected_payload_is_ever_retained(ok_payload):
    """No raw distribution, no record, no intermediate sweep result is kept.

    The cache holds exactly what would be served -- so anything not on the frozen
    allowlist is gone by the time anything is stored.
    """
    def runner(root, *, mode, provider=None):
        return json.loads(json.dumps(ok_payload))

    state = VerificationState(ROOT, runner=runner)
    state.get()
    assert _wait_until(lambda: state.get()["status"] == "ok")
    cached = state._cached[PUBLIC_REFERENCE].payload
    assert list(cached) == list(verification._ENVELOPE_KEYS)
    assert "instance_path" not in json.dumps(cached)
