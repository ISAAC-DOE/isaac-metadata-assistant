"""The vendored official schema is the authority: the golden examples must pass,
and known violations of the official hard rules must fail."""

import copy
import json
from pathlib import Path

import pytest

from isaac_records.official import EXPECTED_VERSION, validate_official

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "tests" / "fixtures" / "official"
EXAMPLES = sorted(OFFICIAL.glob("*.json"))


def test_expected_version_matches_vendored_schema():
    schema = json.loads((ROOT / "schema" / "isaac_record_v1.json").read_text())
    assert schema["properties"]["isaac_record_version"]["const"] == EXPECTED_VERSION


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name for p in EXAMPLES])
def test_official_examples_validate(path):
    record = json.loads(path.read_text(encoding="utf-8"))
    report = validate_official(record, ROOT)
    assert report.ok, report.render()


def test_ten_examples_present():
    assert len(EXAMPLES) == 10


@pytest.fixture
def xanes():
    return json.loads((OFFICIAL / "ex_situ_xanes_cuo2_record.json").read_text())


def test_unknown_top_level_block_rejected(xanes):
    xanes["literature"] = {"doi": "10.1/x"}
    assert not validate_official(xanes, ROOT).ok


def test_descriptor_null_value_rejected(xanes):
    xanes["descriptors"]["outputs"][0]["descriptors"][0]["value"] = None
    assert not validate_official(xanes, ROOT).ok


def test_bad_technique_enum_rejected(xanes):
    xanes["system"]["technique"] = "telepathy"
    assert not validate_official(xanes, ROOT).ok


def test_record_id_must_be_ulid(xanes):
    xanes["record_id"] = "isaac-2026-cuo-xas-0001"
    assert not validate_official(xanes, ROOT).ok


def test_performance_galvanostatic_requires_current_setpoint():
    # Conditional required-field rule from the schema's allOf.
    rec = {
        "isaac_record_version": "1.05",
        "record_id": "01JFH3Q8Z1Q9F0XG3V7N4K2M8C",
        "record_type": "intent",
        "record_domain": "performance",
        "source_type": "laboratory",
        "timestamps": {"created_utc": "2026-07-06T00:00:00Z"},
        "context": {
            "environment": "operando",
            "temperature_K": 298,
            "electrochemistry": {"control_mode": "galvanostatic"},
        },
    }
    assert not validate_official(rec, ROOT).ok  # missing current_setpoint_mA_cm2
    rec2 = copy.deepcopy(rec)
    rec2["context"]["electrochemistry"]["current_setpoint_mA_cm2"] = 10.0
    assert validate_official(rec2, ROOT).ok, validate_official(rec2, ROOT).render()
