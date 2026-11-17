"""The fields the schema vendored on 2026-11-16 (upstream ``a1cb1c8``, the portal's pinned
commit) adds, through the whole truth path: official validation, exactness,
``validate_draft``, ``export.transform``, the evidence sidecar and the audit.

Everything here is SYNTHETIC: the draft is ``tests/fixtures/cuo_xanes_draft.json`` (made-up
values) and every added value says SYNTHETIC. Nothing is read from a real artifact.

What the refresh widened, and what each test pins:

* ``attribution.produced_by`` (who produced the result) is a claim. A record carrying it is
  valid; a draft must cite it (field envelopes, never the attribution block); it survives a
  draft that also holds contributors; its leaves are audit targets.
* ``context.temperature_K`` is ``number | null`` and ``context.temperature_basis`` exists,
  tied by a ``context.allOf`` rule. A null temperature WITH ``not_reported`` is valid and
  exports; a null temperature WITHOUT it is refused; ``not_reported`` beside a number is
  refused. Nothing defaults a temperature.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from isaac_records import validate_draft
from isaac_records.audit import _sidecar_coverage
from isaac_records.exactness import check_exactness
from isaac_records.export import build_sidecar, export_draft, transform
from isaac_records.official import validate_official

ROOT = Path(__file__).resolve().parents[1]
DRAFT_PATH = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"
RID = "01JQZ0SYNTHPRODUCEDBY00000"
NOW = "2099-01-01T00:00:00Z"

EVIDENCE = [{"source_type": "user_confirmation", "quote": "SYNTHETIC answer for a test"}]
PRODUCED_BY = {"group": "SYNTHETIC test group", "organization": "SYNTHETIC test organisation"}


@pytest.fixture
def draft() -> dict:
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def record(draft) -> dict:
    result = export_draft(draft, ROOT, record_id=RID, now=NOW)
    assert result.ok, (result.draft_report.render(), result.official_report and result.official_report.render())
    return result.record


def _envelope(value) -> dict:
    return {"value": value, "status": "verified", "evidence": copy.deepcopy(EVIDENCE)}


def _not_reported(draft: dict) -> dict:
    """The draft's evidenced answer: the source does not state the temperature."""
    draft["fields"]["context.temperature_K"] = {"value": None, "status": "missing", "evidence": []}
    draft["fields"]["context.temperature_basis"] = _envelope("not_reported")
    return draft


def _errors(report) -> str:
    return " | ".join(f"{e.path}: {e.message}" for e in report.errors)


# --- the vendored schema declares them -------------------------------------------------------


def test_vendored_schema_declares_the_portal_fields():
    schema = json.loads((ROOT / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8"))
    context = schema["properties"]["context"]
    assert "produced_by" in schema["properties"]["attribution"]["properties"]
    assert context["properties"]["temperature_K"]["type"] == ["number", "null"]
    assert context["properties"]["temperature_basis"]["enum"] == ["stated", "room_temperature", "not_reported"]
    assert "temperature_K" in context["required"]  # required, so "absent" is never "not reported"


# --- a record with produced_by ----------------------------------------------------------------


def test_a_record_with_produced_by_is_valid_and_exact(record):
    record["attribution"]["produced_by"] = dict(PRODUCED_BY)
    assert validate_official(record, ROOT).ok, _errors(validate_official(record, ROOT))
    assert check_exactness(record, ROOT).ok


def test_produced_by_still_refuses_an_unknown_key(record):
    record["attribution"]["produced_by"] = {**PRODUCED_BY, "SYNTHETIC_unknown": "x"}
    assert not validate_official(record, ROOT).ok


def test_produced_by_as_field_envelopes_exports_beside_contributors(draft):
    # The fixture draft carries `attribution.contributors` in the block. Before the merge in
    # `transform`, assigning that block replaced `record["attribution"]` and silently dropped
    # the produced_by values the `fields` loop had just written.
    draft["fields"]["attribution.produced_by.group"] = _envelope(PRODUCED_BY["group"])
    draft["fields"]["attribution.produced_by.organization"] = _envelope(PRODUCED_BY["organization"])
    result = export_draft(draft, ROOT, record_id=RID, now=NOW)
    assert result.ok, result.draft_report.render()
    assert result.record["attribution"]["produced_by"] == PRODUCED_BY
    assert result.record["attribution"]["contributors"] == draft["attribution"]["contributors"]
    # The sidecar files the evidence under the dotted paths, which resolve in the record.
    assert result.sidecar["evidence"]["attribution.produced_by.group"] == EVIDENCE
    assert result.sidecar["evidence"]["attribution.produced_by.organization"] == EVIDENCE


def test_produced_by_envelope_without_evidence_is_refused(draft):
    draft["fields"]["attribution.produced_by.group"] = {"value": "SYNTHETIC group", "status": "verified", "evidence": []}
    report = validate_draft(draft)
    assert not report.ok
    assert any(where == "fields.attribution.produced_by.group" for where, _ in report.errors)


def test_produced_by_inside_the_attribution_block_is_refused(draft):
    # The block spelling carries no per-value evidence, so it would export uncited.
    draft["attribution"]["produced_by"] = dict(PRODUCED_BY)
    report = validate_draft(draft)
    assert any(where == "attribution.produced_by" for where, _ in report.errors), report.render()
    assert not export_draft(draft, ROOT, record_id=RID, now=NOW).ok


def test_the_attribution_merge_leaves_the_draft_untouched(draft):
    draft["fields"]["attribution.produced_by.group"] = _envelope(PRODUCED_BY["group"])
    before = copy.deepcopy(draft)
    transform(draft, record_id=RID, now=NOW)
    assert draft == before


def test_produced_by_leaves_are_audit_targets(tmp_path, record):
    record["attribution"]["produced_by"] = dict(PRODUCED_BY)
    sidecar = tmp_path / f"{RID}.evidence.json"
    sidecar.write_text(json.dumps({"evidence": {}}), encoding="utf-8")
    _, _, uncovered, _ = _sidecar_coverage(record, sidecar)
    assert "attribution.produced_by.group" in uncovered
    assert "attribution.produced_by.organization" in uncovered
    # The server-stamped field is still not an evidence target.
    record["attribution"]["uploaded_by"] = "SYNTHETIC server identity"
    _, _, uncovered, _ = _sidecar_coverage(record, sidecar)
    assert "attribution.uploaded_by" not in uncovered


# --- a record with a null temperature and not_reported ---------------------------------------


def test_a_null_temperature_with_not_reported_is_valid_and_exact(record):
    record["context"]["temperature_K"] = None
    record["context"]["temperature_basis"] = "not_reported"
    assert validate_official(record, ROOT).ok, _errors(validate_official(record, ROOT))
    assert check_exactness(record, ROOT).ok


def test_a_not_reported_draft_exports_temperature_null(draft):
    result = export_draft(_not_reported(draft), ROOT, record_id=RID, now=NOW)
    assert result.ok, (result.draft_report.render(), result.official_report and result.official_report.render())
    context = result.record["context"]
    assert "temperature_K" in context and context["temperature_K"] is None
    assert context["temperature_basis"] == "not_reported"
    # The evidence is the basis's; nothing is filed under the null, and the audit does not
    # count the null as an uncovered claim.
    assert "context.temperature_K" not in result.sidecar["evidence"]
    assert result.sidecar["evidence"]["context.temperature_basis"] == EVIDENCE


def test_audit_does_not_report_a_null_temperature_as_uncovered(tmp_path, draft):
    result = export_draft(_not_reported(draft), ROOT, record_id=RID, now=NOW)
    sidecar = tmp_path / f"{RID}.evidence.json"
    sidecar.write_text(json.dumps(result.sidecar), encoding="utf-8")
    covered, expected, uncovered, dangling = _sidecar_coverage(result.record, sidecar)
    assert "context.temperature_K" not in uncovered
    assert "context.temperature_basis" not in uncovered
    assert dangling == []


def test_a_stated_temperature_is_unchanged_by_the_basis(draft):
    draft["fields"]["context.temperature_basis"] = _envelope("stated")
    result = export_draft(draft, ROOT, record_id=RID, now=NOW)
    assert result.ok, result.draft_report.render()
    assert result.record["context"]["temperature_K"] == 298
    assert result.record["context"]["temperature_basis"] == "stated"


def test_build_sidecar_handles_a_null_temperature_record(draft):
    draft = _not_reported(draft)
    record = transform(draft, record_id=RID, now=NOW)
    sidecar = build_sidecar(draft, record)
    assert "context.temperature_K" not in sidecar["evidence"]


# --- the conditional rule refuses a null temperature WITHOUT a basis -------------------------


def test_a_null_temperature_without_a_basis_is_refused(record):
    record["context"]["temperature_K"] = None
    record["context"].pop("temperature_basis", None)
    report = validate_official(record, ROOT)
    assert not report.ok
    assert "temperature_basis" in _errors(report)


@pytest.mark.parametrize("basis", ["stated", "room_temperature"])
def test_a_null_temperature_with_another_basis_is_refused(record, basis):
    record["context"]["temperature_K"] = None
    record["context"]["temperature_basis"] = basis
    assert not validate_official(record, ROOT).ok


def test_not_reported_beside_a_number_is_refused(record):
    record["context"]["temperature_K"] = 298
    record["context"]["temperature_basis"] = "not_reported"
    assert not validate_official(record, ROOT).ok


def test_an_absent_temperature_is_still_a_missing_required_value(draft):
    # Without the basis nothing writes a null: the export is refused, never defaulted.
    draft["fields"]["context.temperature_K"] = {"value": None, "status": "missing", "evidence": []}
    result = export_draft(draft, ROOT, record_id=RID, now=NOW)
    assert not result.ok
    assert "temperature_K" not in result.record["context"]
    assert "temperature_K" in _errors(result.official_report)


def test_not_reported_with_a_drafted_number_is_refused_not_overwritten(draft):
    draft["fields"]["context.temperature_basis"] = _envelope("not_reported")  # temperature_K stays 298
    result = export_draft(draft, ROOT, record_id=RID, now=NOW)
    assert not result.ok
    assert result.record["context"]["temperature_K"] == 298


# --- review of #323 ---------------------------------------------------------------------------


def _coverage(tmp_path, record, evidence):
    sidecar = tmp_path / f"{RID}.evidence.json"
    sidecar.write_text(json.dumps({"evidence": evidence}), encoding="utf-8")
    return _sidecar_coverage(record, sidecar)


def test_an_unevidenced_produced_by_people_list_is_uncovered(tmp_path, record):
    # MEDIUM 1: lists were skipped, so an uncited `people` list audited as fully covered.
    record["attribution"]["produced_by"] = {**PRODUCED_BY, "people": ["SYNTHETIC Person A"]}
    evidence = {"attribution.produced_by.group": EVIDENCE, "attribution.produced_by.organization": EVIDENCE}
    _, _, uncovered, dangling = _coverage(tmp_path, record, evidence)
    assert "attribution.produced_by.people" in uncovered
    assert dangling == []
    evidence["attribution.produced_by.people"] = EVIDENCE
    _, _, uncovered, _ = _coverage(tmp_path, record, evidence)
    assert not any(k.startswith("attribution.produced_by") for k in uncovered)


def test_an_unevidenced_modulation_levels_list_is_uncovered(tmp_path, record):
    record["context"]["modulation"] = {"levels": [{"label": "SYNTHETIC low", "value": 0.1, "unit": "V"}]}
    _, _, uncovered, _ = _coverage(tmp_path, record, {})
    assert "context.modulation.levels" in uncovered


def test_an_empty_people_list_is_not_a_target(tmp_path, record):
    record["attribution"]["produced_by"] = {**PRODUCED_BY, "people": []}
    _, _, uncovered, _ = _coverage(tmp_path, record, {})
    assert "attribution.produced_by.people" not in uncovered


def test_a_whole_object_produced_by_envelope_covers_its_leaves(tmp_path, draft):
    # LOW 3: one envelope for the whole object files one sidecar entry, at its own path.
    draft["fields"]["attribution.produced_by"] = _envelope({**PRODUCED_BY, "people": ["SYNTHETIC Person A"]})
    result = export_draft(draft, ROOT, record_id=RID, now=NOW)
    assert result.ok, result.draft_report.render()
    assert result.record["attribution"]["produced_by"]["group"] == PRODUCED_BY["group"]
    _, _, uncovered, dangling = _coverage(tmp_path, result.record, result.sidecar["evidence"])
    assert not any(k.startswith("attribution.produced_by") for k in uncovered), uncovered
    assert dangling == []


def test_a_needs_confirmation_temperature_is_not_closed_by_the_basis(draft):
    # LOW 1: an evidenced `not_reported` basis must not answer an open temperature question.
    draft["fields"]["context.temperature_K"] = {"value": None, "status": "needs_confirmation", "evidence": []}
    draft["fields"]["context.temperature_basis"] = _envelope("not_reported")
    result = export_draft(draft, ROOT, record_id=RID, now=NOW)
    assert not result.ok
    assert "temperature_K" not in result.record["context"]
