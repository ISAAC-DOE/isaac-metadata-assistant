"""Slice-3B draft builder: assemble a validate-clean draft envelope from the
deterministic Slice-3A parsers, with NOTHING guessed (no sha256, no fabricated
series/descriptor). Hermetic: reads only the committed synthetic fixtures under
``tests/fixtures/synthetic`` — never ``examples/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from isaac_records.draft_validator import validate_draft
from isaac_records.extract.draft_builder import build_draft

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic" / "mock_campaign.csv"
LISTING_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic" / "raw_scan_listing.txt"


def _draft():
    return build_draft(CSV_PATH, LISTING_PATH)


def test_built_draft_passes_no_guessing():
    draft = _draft()
    report = validate_draft(draft)
    assert report.ok is True, report.render()


def test_meta_is_the_xanes_characterization_path():
    assert _draft()["meta"] == {
        "record_type": "evidence",
        "record_domain": "characterization",
        "source_type": "facility",
    }


def test_representative_fields_present_with_precise_evidence():
    fields = _draft()["fields"]
    # ~25 evidenced scalar fields.
    assert len(fields) == 25

    beamline = fields["system.facility.beamline"]
    assert beamline["value"] == "15-2"
    assert isinstance(beamline["value"], str)
    assert len(beamline["evidence"]) == 1
    assert beamline["evidence"][0]["locator"] == "Sheet 'Campaign Info', field=beamline"

    temp = fields["context.temperature_K"]
    assert temp["value"] == 298
    assert isinstance(temp["value"], int) and not isinstance(temp["value"], bool)
    assert len(temp["evidence"]) == 1
    assert temp["evidence"][0]["locator"] == "Sheet 'Configurations', field=temperature_K"


def test_assets_empty_and_pending_blockers_present():
    draft = _draft()
    assert draft["assets"] == []

    pending = draft["pending"]
    assert len(pending) >= 4

    asset_blocks = [p for p in pending if p["kind"] == "asset"]
    assert len(asset_blocks) == 3  # raw pointer + reduced product + notebook
    assert all(p["blocker"] == "sha256" for p in asset_blocks)
    assert all(p["evidence"] for p in asset_blocks)
    assert {p["content_role"] for p in asset_blocks} == {
        "raw_data_pointer",
        "reduction_product",
        "processing_script",
    }
    for p in asset_blocks:
        assert p["question"] == f"What is the sha256 of {p['uri']}?"

    series_block = next(p for p in pending if p["kind"] == "series")
    assert series_block["blocker"] == "reduced_spectrum"
    assert series_block["evidence"]  # carries the reduction_product's file_listing evidence
    assert series_block["evidence"][0]["source_type"] == "file_listing"

    descriptor_block = next(p for p in pending if p["kind"] == "descriptor")
    assert descriptor_block["blocker"] == "required_for_evidence_record"


def test_qc_read_from_sheet_not_hardcoded():
    # The value comes from the sheet's qc_status cell ("valid"), not a literal.
    assert _draft()["qc"]["status"] == "valid"


def test_implicit_absorbing_element_and_edge_candidate():
    imp = {i["about"]: i for i in _draft()["implicit"]}

    absorber = imp["absorbing_element"]
    assert absorber["value"] == "Cu"
    assert absorber["evidence"][0]["source_type"] == "derivation"
    assert absorber["evidence"][0]["rule"]

    edge = imp["edge"]
    assert edge["value"] is None  # needs scientific confirmation — never asserted
    assert edge["evidence"][0]["source_type"] == "derivation"
    assert "confirmation" in edge["evidence"][0]["rule"]


def test_attribution_has_two_experimenters_schema_clean():
    contributors = _draft()["attribution"]["contributors"]
    assert {c["name"] for c in contributors} == {"Ada Lovelace", "Grace Hopper"}
    for c in contributors:
        assert set(c) == {"name", "role"}  # evidence deferred to sidecar


def test_no_sha256_value_anywhere():
    draft = _draft()
    # No asset carries a sha256 (assets empty; none smuggled in).
    for a in draft["assets"]:
        assert "sha256" not in a
    # 'sha256' appears ONLY as a pending blocker label / question text — never as a
    # hash value anywhere else in the draft.
    non_pending = json.dumps({k: v for k, v in draft.items() if k != "pending"})
    assert "sha256" not in non_pending


def test_nothing_guessed():
    draft = _draft()
    # No fabricated measurement.series (it is a pending blocker instead).
    assert "series" not in draft
    # descriptors_outputs absent or empty.
    assert not draft.get("descriptors_outputs")
