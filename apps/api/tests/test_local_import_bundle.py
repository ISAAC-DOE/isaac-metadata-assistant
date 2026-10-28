"""LOCAL-1: the ISAAC Local Import Bundle v1 contract.

Round-trip, rejection of malformed and oversize bundles, the evidence model (many
witnesses per value, never one flattened origin), and the value-state rule: parser
output can never yield ``scientist_confirmed``; an AI interpretation can never lift a
value past ``needs_review``; missing stays missing.

DATA BOUNDARY: committed synthetic fixtures only.
"""

from __future__ import annotations

import copy
import json

import pytest

import isaac_api.historical_import as hist
from isaac_api.local_import import bundle as B

NOW = "2026-10-28T00:00:00Z"


@pytest.fixture(scope="module")
def built():
    evidence: dict = {}
    reading, candidates = hist.read_local_archive(
        hist.archive_root_for("bl15_synthetic_semantics_corpus"),
        source_id="local-source",
        evidence_sink=evidence,
    )
    bundle = B.build_bundle(
        reading, candidates, evidence_by_source=evidence, source_kind="folder", created_utc=NOW
    )
    return reading, candidates, bundle, evidence


@pytest.fixture()
def bundle(built):
    return copy.deepcopy(built[2])


def _cand(bundle, **match):
    for c in bundle["candidates"]:
        if all(c.get(k) == v for k, v in match.items()):
            return c
    raise AssertionError(f"no candidate matching {match}")


# --- round trip ------------------------------------------------------------------


def test_a_built_bundle_meets_v1_and_round_trips(bundle, tmp_path):
    assert B.validate_bundle(bundle) == []
    path = tmp_path / "bundle.json"
    path.write_bytes(B.encode(bundle))
    loaded = B.load_bundle(tmp_path)
    assert loaded == bundle
    assert B.check_bundle(tmp_path) == []
    assert loaded["format"] == "isaac.local-import-bundle"
    assert loaded["format_version"] == "1.1.0"
    assert loaded["is_official_record"] is False
    assert "NOT an official ISAAC record" in loaded["official_record_notice"]
    assert loaded["ai_interpretations"] == [] and loaded["scientist_decisions"] == []


def test_the_schema_itself_is_valid_draft_2020_12():
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(B.bundle_schema())


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda b: b.update(is_official_record=True), "is_official_record"),
        (lambda b: b.update(format_version="2.0.0"), "format_version"),
        (lambda b: b.pop("runs"), "runs"),
        (lambda b: b.update(surprise=1), "surprise"),
        (lambda b: b["candidates"][0].update(value_state="verified"), "value_state"),
        (lambda b: b["sources"][0].update(relative_path="/Users/someone/beamtime/x"), "relative_path"),
        (lambda b: b["sources"][0].update(local_only=False), "local_only"),
        (lambda b: b["candidates"][0]["evidence"][0].update(method="guess"), "method"),
        (lambda b: b["readiness"].update(official_record_ready=True), "official_record_ready"),
    ],
)
def test_malformed_bundles_are_refused(bundle, mutate, needle):
    mutate(bundle)
    errors = B.validate_bundle(bundle)
    assert errors, "a malformed bundle validated"
    assert any(needle in e for e in errors), errors


def test_an_escaping_relative_path_is_refused(bundle):
    bundle["sources"][0]["relative_path"] = "../outside/file"
    errors = B.validate_bundle(bundle)
    assert any("escapes the root" in e or ("relative_path" in e and "should not be valid" in e) for e in errors), errors


def test_an_oversize_string_is_refused_by_the_validator(bundle):
    bundle["candidates"][0]["rule"] = "x" * (B.MAX_STRING_CHARS + 1)
    assert any("exceeds" in e for e in B.validate_bundle(bundle))


def test_an_oversize_file_is_refused_before_it_is_parsed(tmp_path, monkeypatch):
    (tmp_path / "bundle.json").write_text("{" + " " * 2000 + "}", encoding="utf-8")
    monkeypatch.setattr(B, "MAX_BUNDLE_BYTES", 1000)
    with pytest.raises(B.BundleInvalid) as raised:
        B.load_bundle(tmp_path)
    assert "over the bound" in str(raised.value)


def test_too_many_evidence_entries_are_refused(bundle):
    c = bundle["candidates"][1]
    c["evidence"] = [dict(c["evidence"][0], evidence_id=f"x{i}") for i in range(B.MAX_EVIDENCE_PER_CANDIDATE + 1)]
    c["evidence_total"] = len(c["evidence"])
    assert B.validate_bundle(bundle)


def test_a_window_that_hides_its_total_is_refused(bundle):
    c = next(c for c in bundle["candidates"] if c["evidence_truncated"])
    c["evidence_truncated"] = False
    assert any("evidence_truncated" in e for e in B.validate_bundle(bundle))


def test_the_builder_clamps_a_long_string_visibly_and_counts_it(built):
    reading, candidates, _, evidence = built
    long = "y" * (B.MAX_STRING_CHARS + 500)
    hacked = [
        hist.SemanticCandidate(**{**c.__dict__, "rule": long}) if i == 0 else c
        for i, c in enumerate(candidates)
    ]
    bundle = B.build_bundle(reading, hacked, evidence_by_source=evidence, source_kind="folder", created_utc=NOW)
    assert bundle["bounds"]["strings_truncated"] >= 1
    assert "truncated by bundle bounds" in bundle["candidates"][0]["rule"]
    assert len(bundle["candidates"][0]["rule"]) <= B.MAX_STRING_CHARS
    assert B.validate_bundle(bundle) == []


def test_the_builder_refuses_more_runs_than_the_bound(built, monkeypatch):
    reading, candidates, _, evidence = built
    monkeypatch.setattr(B, "MAX_RUNS", 3)
    with pytest.raises(B.BundleBoundsExceeded):
        B.build_bundle(reading, candidates, evidence_by_source=evidence, source_kind="folder", created_utc=NOW)


# --- the evidence model --------------------------------------------------------------


def test_one_value_keeps_every_witness_it_rests_on(bundle):
    agreeing = [
        c for c in bundle["candidates"]
        if c["state_basis"]["agreement"] == "sources_agree" and len(c["evidence"]) >= 2
    ]
    assert agreeing
    c = agreeing[0]
    sources = {e["source_id"] for e in c["evidence"]}
    assert len(sources) >= 2, "witnesses were flattened to one origin"
    assert all(e["relation"] == "supports" for e in c["evidence"])
    assert all(e["method"] == "deterministic_parser" and e["method_id"] for e in c["evidence"])
    assert c["distinct_sources"] >= 2


def test_normalisation_is_recorded_beside_the_literal(bundle):
    c = _cand(bundle, statement_key="acquisition_epoch", run_id="run-001")
    (e,) = c["evidence"]
    assert e["literal_value"] == "4102445400"  # what the file says, unchanged
    assert c["value"] == "2100-01-01T00:10:00+00:00"
    assert e["normalization"] == [
        {
            "step": "normalize",
            "rule_id": "bl15.spec.epoch_to_utc_iso.v1",
            "from": "4102445400",
            "to": "2100-01-01T00:10:00+00:00",
            "unit": None,
        }
    ]


def test_a_window_says_it_is_a_window(bundle):
    windows = [c for c in bundle["candidates"] if c["evidence_truncated"]]
    assert windows
    for c in windows:
        assert c["evidence_total"] > len(c["evidence"])
    assert bundle["bounds"]["evidence_windows_truncated"] == len(windows)


def test_every_evidence_source_is_a_manifest_source(bundle):
    ids = {s["source_id"] for s in bundle["sources"]}
    for c in bundle["candidates"]:
        for e in c["evidence"]:
            assert e["source_id"] is None or e["source_id"] in ids


# --- the value-state rule --------------------------------------------------------------


def test_parser_output_never_yields_scientist_confirmed(bundle):
    states = {c["value_state"] for c in bundle["candidates"]} | {
        m["value_state"] for m in bundle["missing_values"]
    }
    assert B.STATE_SCIENTIST_CONFIRMED not in states
    assert B.STATE_REJECTED not in states
    assert states <= B.PARSER_STATES
    assert not any(c["eligibility_for_official_record"]["eligible"] for c in bundle["candidates"])
    assert bundle["readiness"]["eligible_value_count"] == 0
    with pytest.raises(ValueError):
        B.derive_value_state(B.STATE_SCIENTIST_CONFIRMED, decision=None, interpreted=False)


def test_a_hand_edited_confirmation_is_refused(bundle):
    c = _cand(bundle, value_state="candidate_extracted")
    c["value_state"] = "scientist_confirmed"
    c["eligibility_for_official_record"] = {"eligible": True, "reason": "edited"}
    errors = B.validate_bundle(bundle)
    assert any("state:" in e and c["candidate_id"] in e for e in errors), errors


def test_a_scientist_decision_is_the_only_way_to_confirmed(bundle):
    c = _cand(bundle, value_state="candidate_extracted")
    bundle["scientist_decisions"].append(
        {
            "decision_id": "d-1",
            "target": {"kind": "candidate", "id": c["candidate_id"]},
            "decision": "confirm",
            "value": None,
            "chosen_reading_index": None,
            "decided_by": {"name": None, "basis": "self_reported_local_user"},
            "decided_utc": NOW,
            "method": "scientist_answer",
            "note": None,
        }
    )
    # Without re-deriving, the stored state still says candidate_extracted: refused.
    assert any(c["candidate_id"] in e for e in B.validate_bundle(bundle))
    B.apply_derivations(bundle)
    assert c["value_state"] == "scientist_confirmed"
    assert c["eligibility_for_official_record"]["eligible"] is True
    assert bundle["readiness"]["eligible_value_count"] == 1
    assert B.validate_bundle(bundle) == []


def test_an_ai_interpretation_cannot_lift_past_needs_review(bundle):
    m = bundle["missing_values"][0]
    bundle["ai_interpretations"].append(
        {
            "interpretation_id": "ai-1",
            "target": {"kind": "missing_value", "id": m["value_id"]},
            "proposed_value": "something",
            "rationale": "inferred",
            "source_refs": [],
            "method": "ai_interpretation",
            "model": None,
            "created_utc": NOW,
            "max_state": "needs_review",
        }
    )
    m["value_state"] = "scientist_confirmed"
    assert any(m["value_id"] in e for e in B.validate_bundle(bundle))
    B.apply_derivations(bundle)
    assert m["value_state"] == "needs_review"
    assert B.validate_bundle(bundle) == []
    assert B.derive_value_state("conflicting", decision=None, interpreted=True) == "conflicting"
    assert B.derive_value_state("candidate_extracted", decision=None, interpreted=True) == "needs_review"


def test_missing_stays_missing_and_nothing_is_defaulted(bundle):
    assert bundle["missing_values"]
    for m in bundle["missing_values"]:
        assert m["value"] is None
        assert m["value_state"] == "missing"
        assert m["eligibility_for_official_record"]["eligible"] is False
    # DEC-69: no environment / reaction / cell value is filled for a run that states none
    run_paths = {(m["run_id"], m["target_field_path"]) for m in bundle["missing_values"]}
    stated = {(c["run_id"], c["target_field_path"]) for c in bundle["candidates"] if c["target_field_path"]}
    assert not run_paths & stated
    for c in bundle["candidates"]:
        if c["target_field_path"] in {
            "context.environment",
            "context.electrochemistry.reaction",
            "context.electrochemistry.cell_type",
        } and c["value"] is not None:
            assert c["evidence"], "a value with no witness"


def test_a_value_with_no_decision_cannot_appear_on_a_missing_entry(bundle):
    bundle["missing_values"][0]["value"] = "room temperature"
    assert B.validate_bundle(bundle)


def test_the_state_table_covers_every_review_status():
    assert set(B.REVIEW_STATUS_TO_STATE) == {
        "sources_conflict", "unmapped", "ready", "needs_review", "resolved"
    }
    assert set(B.REVIEW_STATUS_TO_STATE.values()) <= B.PARSER_STATES
