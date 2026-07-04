"""Every trust rule has a fixture that must fail.

The golden CuO/XAS record passes finalization; each test below mutates one
thing and asserts the validator catches exactly that class of problem.
"""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from isaac_records.models import derivation, user_confirmation
from isaac_records.validator import load_schema, load_vocabularies, validate_record

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "golden_cuo_xas.json"


@pytest.fixture(scope="module")
def schema():
    return load_schema(ROOT)


@pytest.fixture(scope="module")
def vocabularies():
    return load_vocabularies(ROOT)


@pytest.fixture
def golden():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def error_codes(report):
    return {issue.code for issue in report.errors}


def test_schema_itself_is_valid_draft_2020_12(schema):
    Draft202012Validator.check_schema(schema)


def test_golden_record_passes_finalization(golden, schema, vocabularies):
    report = validate_record(golden, schema, vocabularies, finalize=True)
    assert report.ok, report.render()


def test_verified_field_without_evidence_fails(golden, schema, vocabularies):
    golden["conditions"]["temperature"]["evidence"] = []
    report = validate_record(golden, schema, vocabularies)
    assert "EVIDENCE_MISSING" in error_codes(report)


def test_out_of_vocabulary_term_fails(golden, schema, vocabularies):
    golden["sample"]["physical_form"]["value"] = "gooey"
    report = validate_record(golden, schema, vocabularies)
    assert "VOCAB_UNSUPPORTED" in error_codes(report)


def test_wrong_unit_dimension_fails(golden, schema, vocabularies):
    golden["conditions"]["temperature"]["unit"] = "bar"
    report = validate_record(golden, schema, vocabularies)
    assert "UNIT_WRONG_DIMENSION" in error_codes(report)


def test_missing_unit_fails(golden, schema, vocabularies):
    golden["conditions"]["temperature"]["unit"] = None
    report = validate_record(golden, schema, vocabularies)
    assert "UNIT_MISSING" in error_codes(report)


def test_unparseable_unit_fails(golden, schema, vocabularies):
    golden["conditions"]["temperature"]["unit"] = "blorps"
    report = validate_record(golden, schema, vocabularies)
    assert "UNIT_UNPARSEABLE" in error_codes(report)


def test_missing_required_field_blocks_finalization_only(golden, schema, vocabularies):
    golden["technique"]["xas"]["absorbing_element"] = {
        "value": None,
        "status": "missing",
        "evidence": [],
    }
    draft_report = validate_record(golden, schema, vocabularies, finalize=False)
    assert draft_report.ok, "a draft with an honestly-missing field must still validate"
    final_report = validate_record(golden, schema, vocabularies, finalize=True)
    assert "FINALIZATION_INCOMPLETE" in error_codes(final_report)


def test_needs_confirmation_blocks_finalization(golden, schema, vocabularies):
    golden["technique"]["xas"]["detection_mode"]["status"] = "needs_confirmation"
    report = validate_record(golden, schema, vocabularies, finalize=True)
    assert "FINALIZATION_INCOMPLETE" in error_codes(report)


def test_raw_data_copied_instead_of_linked_fails(golden, schema, vocabularies):
    golden["raw_data"]["uris"]["value"] = ["0.123, 0.456, 0.789 (scan data)"]
    report = validate_record(golden, schema, vocabularies)
    assert "RAW_DATA_NOT_URI" in error_codes(report)


def test_value_present_with_status_missing_fails(golden, schema, vocabularies):
    golden["conditions"]["temperature"]["status"] = "missing"
    golden["conditions"]["temperature"]["evidence"] = []
    report = validate_record(golden, schema, vocabularies)
    assert "STATUS_VALUE_MISMATCH" in error_codes(report)


def test_inferred_requires_a_derivation_rule(golden, schema, vocabularies):
    element = golden["technique"]["xas"]["absorbing_element"]
    element["status"] = "inferred"
    element["evidence"] = [user_confirmation("What element?", "Cu", "2026-07-04T10:00:00Z")]
    report = validate_record(golden, schema, vocabularies)
    assert "EVIDENCE_MISSING" in error_codes(report)

    element["evidence"] = [
        derivation("absorbing element taken as the metal in sample.formula (CuO → Cu)"),
        user_confirmation("Confirm Cu?", "yes", "2026-07-04T10:00:00Z"),
    ]
    report = validate_record(golden, schema, vocabularies, finalize=True)
    assert report.ok, report.render()


def test_inferred_without_observed_support_warns(golden, schema, vocabularies):
    element = golden["technique"]["xas"]["absorbing_element"]
    element["status"] = "inferred"
    element["evidence"] = [derivation("absorbing element taken as the metal in sample.formula")]
    report = validate_record(golden, schema, vocabularies)
    assert report.ok
    assert "INFERRED_NO_SOURCE" in {issue.code for issue in report.warnings}


def test_technique_requirements_are_conditional(golden, schema, vocabularies):
    golden["technique"]["name"]["value"] = "XRD"
    del golden["technique"]["xas"]
    report = validate_record(golden, schema, vocabularies, finalize=True)
    assert report.ok, "XAS-specific fields must not be required for an XRD record"
