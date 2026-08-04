"""P31.1 — safe CSV ingress + read-only typed preview.

TEST-FIRST contract (authored BEFORE implementation; RED until
`POST /api/experiments/{id}/ingestion/csv/preview` exists). The endpoint accepts a
RAW `text/csv` body (NOT multipart — no python-multipart dep, no SpooledTemporaryFile,
no temp file), bounded in-memory, authenticated + runtime-mode + version gated, and
returns a READ-ONLY typed preview of candidates mapped via the existing
`extract.structured` FIELD_MAP. It performs NO Workspace mutation, guesses nothing,
and leaks no server path/secret/stack trace.

CSV v1 = the ISAAC campaign metadata sheet: `section,field,value,unit,notes` (long
format, one row per field). Truth core untouched. All fixtures synthetic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import bind_tutorial_session, tutorial_client

URL = "/api/experiments/{id}/ingestion/csv/preview"
CT = {"Content-Type": "text/csv"}

VALID_CSV = (
    "section,field,value,unit,notes\n"
    "system,beamline,BL-SYNTH-01,,\n"
    "sample,material_name,Synthetic Oxide,,\n"
    "sample,formula,ZzO2,,\n"
    "sample,CuO2_mass_fraction,0.42,,\n"
    "misc,totally_unmapped_field,SHOULD-NOT-MAP,,\n"  # unmapped → must be skipped, never guessed
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _etag(client, exp_id):
    return client.get(f"/api/experiments/{exp_id}").headers["ETag"]


def _post(client, exp_id, body, headers=None, if_match=True):
    h = dict(CT)
    if if_match:
        h["If-Match"] = _etag(client, exp_id)
    if headers:
        h.update(headers)
    return client.post(URL.format(id=exp_id), content=body, headers=h)


# --- version binding + auth + existence ---------------------------------------


def test_missing_if_match_rejected(client):
    r = client.post(URL.format(id=ws.SEED_NEW_DRAFT_ID), content=VALID_CSV, headers=CT)
    assert r.status_code == 428, r.text


def test_stale_if_match_rejected(client):
    stale = {"If-Match": _etag(client, ws.SEED_NEW_DRAFT_ID)}
    # advance the record so the captured etag goes stale
    ans = ws.load_demo_answers()
    client.post(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
                json={"confirmed_by_user": True, "answers": {"series": ans.get("series")}}, headers=stale)
    r = client.post(URL.format(id=ws.SEED_NEW_DRAFT_ID), content=VALID_CSV, headers={**CT, **stale})
    assert r.status_code == 412, r.text


def test_unknown_experiment_404(client):
    r = _post(client, "01MISSINGRECORD00000000000", VALID_CSV, if_match=False)
    assert r.status_code == 404


def test_requires_auth_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    # The session is opened in-process rather than over HTTP: this deployment
    # requires the key, and pinning it as a client default would destroy the 401
    # this test asserts. Same scope either way.
    c = bind_tutorial_session(TestClient(create_app()))
    assert c.post(URL.format(id=ws.SEED_NEW_DRAFT_ID), content=VALID_CSV, headers=CT).status_code == 401


# --- valid preview: deterministic mapping, no guessing, no mutation -----------


def test_valid_csv_previews_mapped_candidates_no_mutation(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()["version"]
    r = _post(client, ws.SEED_NEW_DRAFT_ID, VALID_CSV)
    assert r.status_code == 200, r.text
    body = r.json()
    fields = {c["field"] for c in body["candidates"]}
    assert "system.facility.beamline" in fields  # FIELD_MAP official path
    assert "sample.material.formula" in fields
    assert "SHOULD-NOT-MAP" not in r.text  # unmapped field never surfaced/guessed
    assert body["source_record_rev"] == int(before.split(".")[-1])  # version-bound
    for c in body["candidates"]:
        assert c["locator"]  # row/field locator preserved
    # READ-ONLY: no mutation, version unchanged after preview
    after = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()["version"]
    assert after == before, "preview must not mutate the record"


def test_preview_is_deterministic(client):
    a = _post(client, ws.SEED_NEW_DRAFT_ID, VALID_CSV).json()["candidates"]
    b = _post(client, ws.SEED_NEW_DRAFT_ID, VALID_CSV).json()["candidates"]
    assert a == b


# --- CSV v1 validation (typed errors) -----------------------------------------


def test_empty_body_rejected(client):
    assert _post(client, ws.SEED_NEW_DRAFT_ID, "").status_code in (400, 422)


def test_nul_byte_rejected(client):
    assert _post(client, ws.SEED_NEW_DRAFT_ID, "field,value\nx,\x00y\n").status_code in (400, 422)


def test_invalid_utf8_rejected(client):
    r = _post(client, ws.SEED_NEW_DRAFT_ID, b"field,value\nx,\xff\xfe\n")
    assert r.status_code in (400, 422)


def test_duplicate_header_rejected(client):
    assert _post(client, ws.SEED_NEW_DRAFT_ID, "field,field,value\na,b,c\n").status_code in (400, 422)


def test_missing_required_header_rejected(client):
    assert _post(client, ws.SEED_NEW_DRAFT_ID, "section,notes\nx,y\n").status_code in (400, 422)


def test_oversized_body_rejected_413(client):
    big = "section,field,value,unit,notes\n" + ("sample,formula,X,,\n" * 200000)  # >256KB
    assert _post(client, ws.SEED_NEW_DRAFT_ID, big).status_code == 413


def test_too_many_rows_rejected(client):
    many = "section,field,value,unit,notes\n" + ("sample,formula,X,,\n" * 600)  # >500 rows, <256KB
    assert _post(client, ws.SEED_NEW_DRAFT_ID, many).status_code in (400, 413, 422)


# --- formula safety + no unit guessing ----------------------------------------


def test_formula_in_numeric_field_is_not_executed(client):
    csv = "section,field,value,unit,notes\nsample,CuO2_mass_fraction,=SUM(1+2),,\n"
    body = _post(client, ws.SEED_NEW_DRAFT_ID, csv).json()
    cand = [c for c in body["candidates"] if c["field"] == "sample.composition.CuO2_mass_fraction"]
    assert cand, "a mapped numeric field is still surfaced"
    # In a PREVIEW every value is a candidate (never confirmed). A formula string
    # fails strict numeric coercion → status needs_confirmation, and is NEVER
    # executed/guessed (the parser keeps the raw text, does not evaluate it).
    assert cand[0]["value_state"] == "candidate"
    assert cand[0]["status"] == "needs_confirmation"
    assert "3" not in str(cand[0].get("proposed_value", ""))  # =SUM(1+2) not evaluated to 3


def test_negative_number_is_accepted_not_blanket_rejected(client):
    csv = "section,field,value,unit,notes\nsample,pellet_diameter_mm,-1.5,,\n"
    body = _post(client, ws.SEED_NEW_DRAFT_ID, csv).json()
    cand = [c for c in body["candidates"] if c["field"] == "sample.geometry.pellet_diameter_mm"]
    assert cand, "a mapped numeric field is surfaced"
    assert cand[0]["value_state"] == "candidate"  # a preview proposes, never confirms
    assert cand[0]["status"] == "verified"  # -1.5 is a valid number (not blanket-rejected)


# --- leak safety --------------------------------------------------------------


def test_preview_leaks_no_server_path_or_stack(client):
    blob = _post(client, ws.SEED_NEW_DRAFT_ID, VALID_CSV).text
    for bad in ["/data/", "/Users/", "/tmp/", "/var/", "isaac-workspace", "Traceback"]:
        assert bad not in blob, f"preview leaked {bad!r}"
