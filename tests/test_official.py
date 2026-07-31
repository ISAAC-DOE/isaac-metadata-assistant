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


# --- the cached validator must not be a shared, mutable object ----------------
#
# `load_official_validator` used to return ONE `lru_cache`d validator to every
# caller. Its `.schema` is a plain dict, so any in-process code could widen an
# enum, drop a `required`, or flip `additionalProperties` and thereby change the
# verdict for every later `validate_official` call in the process — while
# `diagnostics.schema_fingerprint` and `db_recon.schema_authority` kept
# reporting the pristine bytes on disk. The expensive part (`check_schema`,
# ~44 ms) stays cached as text; each caller now parses that text afresh.

LEGACY_RECORD = ROOT / "tests" / "fixtures" / "legacy" / "01JQZ0SYNTHXANESDEMO000000.json"


def test_each_caller_gets_a_private_schema_object():
    from isaac_records.official import load_official_validator

    a = load_official_validator(ROOT)
    b = load_official_validator(ROOT)
    assert a is not b
    assert a.schema is not b.schema
    assert a.schema == b.schema

    record = json.loads(LEGACY_RECORD.read_text(encoding="utf-8"))
    assert validate_official(record, ROOT).ok, "fixture must be valid before mutating"

    # Widen `record_type` on ONE caller's private validator.
    a.schema["properties"]["record_type"]["enum"].append("totally-bogus")
    record["record_type"] = "totally-bogus"

    # The mutation is confined to `a`: it can neither reach `b` nor authorize a
    # bogus record through the public entry point.
    assert "totally-bogus" not in b.schema["properties"]["record_type"]["enum"]
    assert not validate_official(record, ROOT).ok
    assert "totally-bogus" not in load_official_validator(ROOT).schema[
        "properties"
    ]["record_type"]["enum"]


def test_opening_a_closed_block_on_one_validator_does_not_leak():
    """Containment for a second keyword, so the guard is not enum-specific.

    NOT `required`: jsonschema 4.x resolves the ROOT keyword set once at
    construction, so emptying `schema["required"]` on a validator never changed
    that validator's own verdict and so could never have demonstrated the leak.
    Nested subschemas are read live on descent, which is exactly the reachable
    vector — `additionalProperties` deep in the tree is one.
    """
    from isaac_records.official import load_official_validator

    record = json.loads(LEGACY_RECORD.read_text(encoding="utf-8"))
    record["sample"]["totally_undeclared"] = 1
    assert not validate_official(record, ROOT).ok

    victim = load_official_validator(ROOT)
    victim.schema["properties"]["sample"]["additionalProperties"] = True
    assert not validate_official(record, ROOT).ok


def test_the_expensive_schema_check_is_still_cached():
    """Correctness must not have cost the cache: `check_schema` runs once."""
    from isaac_records.official import _checked_schema_text, load_official_validator

    load_official_validator(ROOT)
    before = _checked_schema_text.cache_info()
    for _ in range(5):
        load_official_validator(ROOT)
    after = _checked_schema_text.cache_info()
    assert after.hits - before.hits == 5
    assert after.misses == before.misses


def test_a_same_mtime_schema_replacement_of_a_DIFFERENT_SIZE_is_not_served_from_cache(tmp_path):
    """The cache key carries st_size as well as st_mtime_ns.

    A same-tick rewrite that keeps the mtime would otherwise be masked. Sizes
    differ here, so the key changes and the new bytes are read.
    """
    import os

    from isaac_records.official import load_official_validator, schema_path

    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    target = schema_path(tmp_path)
    original = (ROOT / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    target.write_text(original, encoding="utf-8")
    stamp = target.stat().st_mtime_ns

    first = load_official_validator(tmp_path)
    assert "totally-bogus" not in first.schema["properties"]["record_type"]["enum"]

    doc = json.loads(original)
    doc["properties"]["record_type"]["enum"].append("totally-bogus")
    target.write_text(json.dumps(doc), encoding="utf-8")
    os.utime(target, ns=(stamp, stamp))  # pretend nothing changed
    assert target.stat().st_mtime_ns == stamp
    assert target.stat().st_size != len(original.encode("utf-8"))

    second = load_official_validator(tmp_path)
    assert "totally-bogus" in second.schema["properties"]["record_type"]["enum"]
