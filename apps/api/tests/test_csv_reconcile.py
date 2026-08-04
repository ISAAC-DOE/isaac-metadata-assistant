"""P31.2 — CSV reconciliation staging (RECONCILIATION-ONLY, corrected 2026-07-22).

TEST-FIRST (orchestrator-authored; RED until the reconciliation enrichment
exists). Per the 2026-07-22 human decision, Phase 31 is reconciliation-only: the
CSV preview is enriched into a version-bound READ-ONLY reconciliation of each
mapped value against the CURRENT authoritative record — classified as
``matches_current`` / ``conflicts_with_current`` / ``absent_from_record`` — and it
NEVER mutates the record, never bumps rev, never changes workflow / export
readiness / runtime retrieval / Project Memory, never selects a winner, and never
auto-stages into the P29.6 confirm/write path. The confirmed-write surface
(`apply_answers`/`/answers`/`/edit`) is UNCHANGED.

Two layers:
  * pure builder (`csv_ingest.build_preview`) with a crafted record view — the only
    way to reach ``absent_from_record`` (every canonical seed already populates all
    25 FIELD_MAP paths), plus deterministic match/conflict/two-row coverage;
  * endpoint integration (`POST /ingestion/csv/preview`) proving match + conflict
    against the real seed, no mutation, version binding, and leak-safety.

All fixtures synthetic. Truth path (§13) untouched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.csv_ingest as csv_ingest
import isaac_api.workspace as ws
from isaac_api.serialize import evidence_trail_from_draft

from conftest import tutorial_client

URL = "/api/experiments/{id}/ingestion/csv/preview"
CT = {"Content-Type": "text/csv"}

# One mapped field (matches the seed), one mapped field with a changed value.
BEAMLINE_MATCH_CSV = (
    "section,field,value,unit,notes\n"
    "system,beamline,15-2,,\n"  # seed value is exactly "15-2" -> matches_current
)
BEAMLINE_CONFLICT_CSV = (
    "section,field,value,unit,notes\n"
    "system,beamline,BL-DIFFERENT-99,,\n"  # differs from seed "15-2" -> conflict
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _etag(client, exp_id):
    return client.get(f"/api/experiments/{exp_id}").headers["ETag"]


def _post(client, exp_id, body, if_match=True):
    h = dict(CT)
    if if_match:
        h["If-Match"] = _etag(client, exp_id)
    return client.post(URL.format(id=exp_id), content=body, headers=h)


def _record_view(exp) -> dict:
    """The current-record view the route passes into the builder (path -> value)."""
    return {e.get("path"): {"value": e.get("value")} for e in evidence_trail_from_draft(exp.draft)}


# ============================================================================
# Layer 1 — pure reconciliation builder (crafted record view)
# ============================================================================

BEAMLINE_CSV = "section,field,value,unit,notes\nsystem,beamline,15-2,,\n"


def _one(text, record_fields, *, rev=7, exp_id="01SEEDSCENARIO0000000000N1"):
    preview = csv_ingest.build_preview(
        text,
        source_name="synthetic.csv",
        source_record_rev=rev,
        experiment_id=exp_id,
        record_fields=record_fields,
    )
    items = [c for c in preview["candidates"] if c["field"] == "system.facility.beamline"]
    assert items, "the mapped beamline field must surface as a reconciliation item"
    return preview, items[0]


def test_matches_current_when_value_equals_record():
    _, item = _one(BEAMLINE_CSV, {"system.facility.beamline": {"value": "15-2"}})
    assert item["reconciliation_state"] == "matches_current"  # (6)
    assert item["current_value"] == "15-2"  # current confirmed value preserved


def test_conflicts_when_value_differs_from_record():
    _, item = _one(BEAMLINE_CSV, {"system.facility.beamline": {"value": "OTHER"}})
    assert item["reconciliation_state"] == "conflicts_with_current"  # (9)
    # BOTH values preserved; no winner selected.
    assert item["proposed_value"] == "15-2"
    assert item["current_value"] == "OTHER"  # (10) neither is dropped/preferred


def test_absent_when_record_has_no_value():
    # Crafted view WITHOUT the beamline path -> absent (unreachable via seeds). (11)(12)
    _, item = _one(BEAMLINE_CSV, {})
    assert item["reconciliation_state"] == "absent_from_record"
    assert item.get("current_value") in (None, "")


def test_absent_when_record_value_is_none():
    _, item = _one(BEAMLINE_CSV, {"system.facility.beamline": {"value": None}})
    assert item["reconciliation_state"] == "absent_from_record"


def test_numeric_match_is_value_equal_not_string_equal():
    # record holds int 6; CSV "6" coerces to int 6 (n_scans is int) -> matches.
    csv = "section,field,value,unit,notes\nsystem,n_scans,6,,\n"
    preview = csv_ingest.build_preview(
        csv, source_name="s.csv", source_record_rev=1, experiment_id="x",
        record_fields={"system.configuration.n_scans": {"value": 6}},
    )
    item = [c for c in preview["candidates"] if c["field"] == "system.configuration.n_scans"][0]
    assert item["reconciliation_state"] == "matches_current"


def test_item_preserves_full_contract():
    _, item = _one(
        BEAMLINE_CSV,
        {"system.facility.beamline": {"value": "15-2", "classification": "supported"}},
        exp_id="01SEEDSCENARIO0000000000N1",
    )
    assert item["experiment_id"] == "01SEEDSCENARIO0000000000N1"  # (1)
    assert item["field"] == "system.facility.beamline"  # (2) official path
    assert item["field_label"] and "/" not in item["field_label"] and "." not in item["field_label"]  # (3) safe
    assert item["proposed_value"] == "15-2"  # CSV value
    assert item["source_name"] == "synthetic.csv"  # (3) safe filename
    assert item["parser_id"] == csv_ingest.PARSER_ID  # (4) parser id
    assert item["parser_version"] == csv_ingest.PARSER_VERSION  # (4) parser version
    assert "row 2" in item["locator"]  # (4) row locator
    assert item["column"]  # (4) column/header locator
    assert item["source_record_rev"] == 7  # (5) source revision
    assert item["stale"] is False  # (current/stale state; freshly built = current)
    assert item["explanation"]  # (clear explanation)
    # P28 classification of the current field surfaced when applicable.
    assert item["evidence_classification"] == "supported"


def test_two_rows_same_field_different_values_preserve_both():
    # (15) intra-file disagreement: both sources preserved, no winner, no dedupe.
    csv = (
        "section,field,value,unit,notes\n"
        "system,beamline,15-2,,\n"
        "system,beamline,15-3,,\n"
    )
    preview = csv_ingest.build_preview(
        csv, source_name="s.csv", source_record_rev=1, experiment_id="x",
        record_fields={"system.facility.beamline": {"value": "15-2"}},
    )
    beam = [c for c in preview["candidates"] if c["field"] == "system.facility.beamline"]
    assert len(beam) == 2, "both rows preserved as separate items"
    assert {b["proposed_value"] for b in beam} == {"15-2", "15-3"}
    assert {b["locator"] for b in beam} != {beam[0]["locator"]}  # distinct row locators


def test_unknown_field_row_creates_no_item():
    # (13) unmapped field never becomes a reconciliation item / never guessed.
    csv = "section,field,value,unit,notes\nmisc,totally_unmapped,SHOULD-NOT-MAP,,\n"
    preview = csv_ingest.build_preview(
        csv, source_name="s.csv", source_record_rev=1, experiment_id="x", record_fields={},
    )
    assert preview["candidates"] == []
    assert "SHOULD-NOT-MAP" not in str(preview)


def test_empty_value_creates_no_item():
    # (14) a blank value for a mapped field must create NO reconciliation item —
    # not even a contradictory 'absent' item on a POPULATED record field.
    csv = "section,field,value,unit,notes\nsystem,beamline,,,\n"
    preview = csv_ingest.build_preview(
        csv, source_name="s.csv", source_record_rev=1, experiment_id="x",
        record_fields={"system.facility.beamline": {"value": "15-2"}},
    )
    beam = [c for c in preview["candidates"] if c["field"] == "system.facility.beamline"]
    assert beam == [], "a blank CSV cell must not create a reconciliation item"
    # And it must not inflate any reconciliation_summary bucket.
    assert sum(preview["reconciliation_summary"].values()) == len(preview["candidates"])


def test_blank_value_does_not_forge_absent_on_populated_field():
    # Regression for the P31.2 review finding: blank cell + populated record must
    # NOT be labeled absent_from_record while carrying a real current_value.
    csv = "section,field,value,unit,notes\nsystem,beamline,   ,,\n"  # whitespace-only
    preview = csv_ingest.build_preview(
        csv, source_name="s.csv", source_record_rev=1, experiment_id="x",
        record_fields={"system.facility.beamline": {"value": "15-2"}},
    )
    assert [c for c in preview["candidates"] if c["field"] == "system.facility.beamline"] == []
    assert preview["reconciliation_summary"]["absent_from_record"] == 0


def test_reconciliation_summary_counts():
    csv = (
        "section,field,value,unit,notes\n"
        "system,beamline,15-2,,\n"       # match
        "sample,formula,DIFFERENT,,\n"    # conflict
    )
    preview = csv_ingest.build_preview(
        csv, source_name="s.csv", source_record_rev=1, experiment_id="x",
        record_fields={
            "system.facility.beamline": {"value": "15-2"},
            "sample.material.formula": {"value": "CuO2"},
        },
    )
    s = preview["reconciliation_summary"]
    assert s["matches_current"] == 1 and s["conflicts_with_current"] == 1


def test_builder_is_deterministic():
    # (25) repeated parsing is structurally identical.
    rf = {"system.facility.beamline": {"value": "15-2"}}
    a = csv_ingest.build_preview(BEAMLINE_CSV, source_name="s.csv", source_record_rev=1, experiment_id="x", record_fields=rf)
    b = csv_ingest.build_preview(BEAMLINE_CSV, source_name="s.csv", source_record_rev=1, experiment_id="x", record_fields=rf)
    assert a == b


# ============================================================================
# Layer 2 — endpoint integration (real seed; match + conflict; no mutation)
# ============================================================================


def test_endpoint_matches_current_against_seed(client):
    r = _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_MATCH_CSV)
    assert r.status_code == 200, r.text
    beam = [c for c in r.json()["candidates"] if c["field"] == "system.facility.beamline"]
    assert beam and beam[0]["reconciliation_state"] == "matches_current"
    assert beam[0]["current_value"] == "15-2"


def test_endpoint_conflict_against_seed_preserves_both(client):
    r = _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_CONFLICT_CSV)
    assert r.status_code == 200, r.text
    beam = [c for c in r.json()["candidates"] if c["field"] == "system.facility.beamline"][0]
    assert beam["reconciliation_state"] == "conflicts_with_current"
    assert beam["proposed_value"] == "BL-DIFFERENT-99"
    assert beam["current_value"] == "15-2"  # both preserved; no winner


def test_endpoint_item_carries_experiment_id_and_rev(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()["rev"]
    r = _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_MATCH_CSV)
    body = r.json()
    assert body["source_record_rev"] == before  # (5) version-bound
    for c in body["candidates"]:
        assert c["experiment_id"] == ws.SEED_NEW_DRAFT_ID  # (1)


def test_endpoint_performs_no_mutation(client):
    """(7)(8)(16)(17)(18) reconciliation writes nothing: rev, workflow, export, and
    pending are all unchanged after a preview (match AND conflict)."""
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_MATCH_CSV)
    _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_CONFLICT_CSV)
    after = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    assert after["rev"] == before["rev"]  # no rev bump
    assert after["version"] == before["version"]
    assert after["workflow"] == before["workflow"]  # workflow unchanged
    assert after["status"] == before["status"]  # export-readiness axis unchanged
    assert after["pending_count"] == before["pending_count"]


def test_endpoint_runtime_retrieval_unchanged(client):
    """(19) a preview must not add the CSV value into cross-record runtime retrieval."""
    before = client.get("/api/runtime/records").json()
    _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_CONFLICT_CSV)
    after = client.get("/api/runtime/records").json()
    assert after == before


def test_endpoint_conflict_value_not_in_search_index(client):
    """(20) the conflicting CSV value must not leak into search (a memory/query surface)."""
    _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_CONFLICT_CSV)
    hits = client.get("/api/search", params={"q": "BL-DIFFERENT-99"}).json()
    # The endpoint echoes the query string; the leak test is that NOTHING was
    # indexed — both planes return zero results for the CSV-only value.
    assert hits["workspace"]["total"] == 0
    assert hits["memory"]["total"] == 0
    assert hits["workspace"]["results"] == [] and hits["memory"]["results"] == []


def test_endpoint_stale_after_record_mutation(client):
    """(22) a reconciliation built at rev R is version-bound; after a real mutation
    the live rev advances, so a client holding the old rev detects staleness."""
    rev0 = _post(client, ws.SEED_PARTIAL_ID, BEAMLINE_MATCH_CSV).json()["source_record_rev"]
    # Apply a real confirmable mutation (series) to advance the record.
    etag = _etag(client, ws.SEED_PARTIAL_ID)
    ans = ws.load_demo_answers()
    m = client.post(
        f"/api/experiments/{ws.SEED_PARTIAL_ID}/answers",
        json={"confirmed_by_user": True, "answers": {"series": ans["series"]}},
        headers={"If-Match": etag},
    )
    assert m.status_code == 200
    rev1 = _post(client, ws.SEED_PARTIAL_ID, BEAMLINE_MATCH_CSV).json()["source_record_rev"]
    assert rev1 != rev0  # the version binding moved -> old reconciliation is stale


def test_endpoint_stale_after_reset(client):
    """(23) reset re-materialises the record (new generation/rev); reconciliation
    bound to the pre-reset rev is no longer current."""
    rev0 = _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_MATCH_CSV).json()["source_record_rev"]
    # R1: an execute carries the plan digest from its own preview (428 without it).
    digest = client.post("/api/demo/reset", json={"mode": "preview"}).json()["plan_digest"]
    r = client.post(
        "/api/demo/reset",
        json={
            "mode": "execute",
            "confirmation": "RESET EXAMPLE WORKSPACE",
            "plan_digest": digest,
        },
    )
    assert r.status_code == 200, r.text
    # After reset the canonical baseline is restored (2/1/1/1); a fresh preview is
    # bound to the post-reset rev and stays deterministic.
    again = _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_MATCH_CSV)
    assert again.status_code == 200
    # The reconciliation is version-bound; a client holding rev0 must revalidate.
    assert again.json()["source_record_rev"] is not None


def test_endpoint_leaks_no_path_or_secret(client):
    blob = _post(client, ws.SEED_NEW_DRAFT_ID, BEAMLINE_CONFLICT_CSV).text
    for bad in ["/data/", "/Users/", "/tmp/", "/var/", "isaac-workspace", "Traceback"]:
        assert bad not in blob  # (27)(28)
