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
    # 25 evidenced scalar fields from the sheet + 1 deterministically-inferred
    # system.domain (required by the official schema once a system block exists).
    assert len(fields) == 26

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

    # system.domain is inferred (facility ⇒ experimental) with a derivation rule,
    # never guessed — the official schema requires it whenever system exists.
    domain = fields["system.domain"]
    assert domain["value"] == "experimental"
    assert domain["status"] == "inferred"
    assert domain["evidence"][0]["source_type"] == "derivation"
    assert domain["evidence"][0]["rule"]


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


def test_contributor_evidence_reaches_block_evidence():
    # Contributors stay record-shaped (name + role); their spreadsheet provenance is
    # ALSO routed into block_evidence under the attribution natural key.
    be = _draft()["block_evidence"]
    for name in ("Ada Lovelace", "Grace Hopper"):
        key = f"attribution:{name}|curated_record"
        assert key in be, sorted(be)
        entries = be[key]
        assert len(entries) == 1
        assert entries[0]["source_type"] == "spreadsheet"
        assert entries[0]["quote"] == name  # the contributor value, verbatim


def test_qc_evidence_reaches_block_evidence():
    # The qc_status row provenance lands in block_evidence["qc:status"] (singleton
    # key; the colon marks it namespaced for the audit, never a dotted record path).
    be = _draft()["block_evidence"]
    assert "qc:status" in be
    entries = be["qc:status"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_type"] == "spreadsheet"
    assert entry["locator"] == "Sheet 'Configurations', field=qc_status"
    assert entry["quote"] == "valid"


def test_qc_blocker_when_sheet_lacks_qc(tmp_path):
    # A sheet with no qc_status row cannot source a qc verdict, so the builder emits a
    # pending qc blocker (never a default 'valid') — deterministic from what's absent.
    src = CSV_PATH.read_text(encoding="utf-8")
    lines = [ln for ln in src.splitlines() if not ln.startswith("Configurations,qc_status,")]
    no_qc_csv = tmp_path / "no_qc.csv"
    no_qc_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    draft = build_draft(no_qc_csv, LISTING_PATH)

    assert "qc" not in draft  # nothing sourced -> no qc block
    assert "qc:status" not in (draft.get("block_evidence") or {})
    qc_blocks = [p for p in draft["pending"] if p.get("kind") == "qc"]
    assert len(qc_blocks) == 1
    assert "QC verdict" in qc_blocks[0]["question"]


# --- the absorbing-element rule, split so a caller can tell its outcomes apart --
#
# `_absorbing_element` collapses "several candidates" and "no candidates" into the
# same `None`, which is correct for a builder that must not guess either way. A
# caller that wants to say *ambiguous* in one case and *not inferable* in the other
# needs the candidate list, so the tokenizing half is now public. These tests pin
# that the split is a REFACTOR: one tokenizer, two readings, no drift.


def test_non_oxygen_elements_reports_the_candidates_in_order():
    from isaac_records.extract.draft_builder import non_oxygen_elements

    assert non_oxygen_elements("CuO2") == ("Cu",)
    assert non_oxygen_elements("CuFeO2") == ("Cu", "Fe")
    assert non_oxygen_elements("Fe2O3") == ("Fe",)   # repeats collapse
    assert non_oxygen_elements("O2") == ()           # oxygen only
    assert non_oxygen_elements("???") == ()          # unparseable
    assert non_oxygen_elements("") == ()
    assert non_oxygen_elements(None) == ()


def test_absorbing_element_still_derives_from_the_same_tokenizer():
    from isaac_records.extract.draft_builder import _absorbing_element, non_oxygen_elements

    for formula in ("CuO2", "CuFeO2", "Fe2O3", "O2", "???", "", None):
        candidates = non_oxygen_elements(formula)
        expected = candidates[0] if len(candidates) == 1 else None
        assert _absorbing_element(formula) == expected
