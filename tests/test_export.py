"""Draft → official record + sidecar: no-guessing at authoring, schema-gated export."""

import copy
import json
import sys
from pathlib import Path

import pytest

from isaac_records import validate_draft
from isaac_records.export import export_draft, get_path, transform
from isaac_records.ids import is_record_id
from isaac_records.official import validate_official

ROOT = Path(__file__).resolve().parents[1]
DRAFT_PATH = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"
XANES = ROOT / "tests" / "fixtures" / "official" / "ex_situ_xanes_cuo2_record.json"
RID = "01JFH3Q8Z1Q9F0XG3V7N4K2M8C"


@pytest.fixture
def draft():
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


def test_golden_draft_passes_no_guessing(draft):
    assert validate_draft(draft).ok, validate_draft(draft).render()


def test_golden_draft_exports_to_valid_record(draft):
    result = export_draft(draft, ROOT, record_id=RID)
    assert result.ok, (result.draft_report.render(), result.official_report and result.official_report.render())
    assert validate_official(result.record, ROOT).ok


def test_exported_record_shape_matches_official_xanes(draft):
    """The transform output covers the same blocks as the official golden record."""
    record = transform(draft, record_id=RID)
    golden = json.loads(XANES.read_text())
    assert set(golden).issubset(set(record)), set(golden) - set(record)
    assert record["record_type"] == "evidence"
    assert record["record_domain"] == "characterization"
    assert record["system"]["technique"] == "HERFD-XAS"
    assert record["assets"][0]["sha256"]
    # Envelope keys must never leak into the record.
    assert "status" not in record["sample"]["material"]
    assert "evidence" not in record["assets"][0]


def test_verified_field_without_evidence_fails_draft(draft):
    draft["fields"]["context.temperature_K"]["evidence"] = []
    assert not validate_draft(draft).ok


def test_missing_status_must_be_null(draft):
    draft["fields"]["context.temperature_K"]["status"] = "missing"
    assert not validate_draft(draft).ok  # value still 298


def test_inferred_needs_derivation_rule(draft):
    draft["fields"]["system.domain"]["evidence"] = [
        {"source_type": "screenshot", "source_file": "x.png", "locator": "title"}
    ]
    assert not validate_draft(draft).ok  # inferred but no derivation rule


def test_asset_without_sha256_blocks_export(draft):
    del draft["assets"][0]["sha256"]
    result = export_draft(draft, ROOT, record_id=RID)
    assert not result.ok
    assert not result.draft_report.ok


def test_export_refuses_when_record_would_be_invalid(draft):
    # Break a required official field: drop the technique.
    del draft["fields"]["system.technique"]
    result = export_draft(draft, ROOT, record_id=RID)
    assert not result.ok
    assert result.official_report is not None and not result.official_report.ok


def test_bad_record_id_rejected(draft):
    result = export_draft(draft, ROOT, record_id="not-a-ulid")
    assert not result.ok


def test_generated_record_id_is_ulid(draft):
    result = export_draft(draft, ROOT)
    assert result.ok
    assert is_record_id(result.record["record_id"])


def test_sidecar_dotted_paths_resolve_in_record(draft):
    result = export_draft(draft, ROOT, record_id=RID)
    assert result.ok
    for key in result.sidecar["evidence"]:
        if ":" in key:  # namespaced (assets:/descriptors:/implicit:) — not literal paths
            continue
        _, found = get_path(result.record, key)
        assert found, f"sidecar path does not resolve: {key}"


def test_implicit_inferences_stay_out_of_record(draft):
    record = transform(draft, record_id=RID)
    blob = json.dumps(record)
    # absorbing element / edge are implicit — must not appear as invented fields.
    assert "absorbing_element" not in blob
    assert '"edge"' not in blob


def test_core_never_imports_graphify():
    assert not any(n == "graphify" or n.startswith("graphify.") for n in sys.modules)
