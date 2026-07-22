"""P27.5-strict — mandatory If-Match preconditions (grace retired).

TEST-FIRST acceptance contract (authored BEFORE the strict flip; RED until
`version_contract.precondition_required()` returns True and the handlers reject a
missing If-Match with 428). The deployed frontend has been hosted-verified to send
`If-Match` on every mutation, so the one-release compatibility grace is now retired:

  * matching If-Match  -> 200 (proceeds)
  * stale If-Match     -> 412 Precondition Failed (unchanged, no mutation)
  * MISSING If-Match   -> 428 Precondition Required (NEW — was 200 under the grace)
  * malformed / weak   -> 400 (unchanged)
  * existing export 409 immutability preserved for a CURRENT client
  * NO deprecation header anywhere (the grace signal is gone)
  * a missing/stale precondition performs NO mutation

Applies to the two version-protected scientific-record mutations
(`POST /answers`, `POST /export`). Reset/demo/validate/audit are NOT version-gated.
All fixtures synthetic; truth core untouched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _real_answers_payload():
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


def _version(client, exp_id):
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.json()["version"]


def _im(client, exp_id):
    return {"If-Match": f'"{_version(client, exp_id)}"'}


# --- the grace is retired: the single toggle is now ON ------------------------


def test_precondition_is_now_required():
    from isaac_api import version_contract as vc

    assert vc.precondition_required() is True


# --- MISSING If-Match -> 428 (the core strict behavior) -----------------------


def test_missing_if_match_on_answers_returns_428(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload()
    )
    assert r.status_code == 428, r.text
    body = r.json()
    assert body["error"] == "precondition_required"
    assert body["experiment_id"] == ws.SEED_NEW_DRAFT_ID


def test_missing_if_match_on_export_returns_428(client):
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export")
    assert r.status_code == 428, r.text
    assert r.json()["error"] == "precondition_required"


def test_missing_if_match_performs_no_mutation(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload()
    )
    assert r.status_code == 428
    after = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    assert after["version"] == before["version"], "a 428 must not have mutated the record"


def test_missing_export_precondition_writes_no_record(client):
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export")
    assert r.status_code == 428
    assert ws.load_experiment(ws.SEED_READY_ID).exported() is False


# --- matching still succeeds; stale/malformed unchanged -----------------------


def test_matching_if_match_still_succeeds(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=_im(client, ws.SEED_NEW_DRAFT_ID),
    )
    assert r.status_code == 200, r.text


def test_stale_if_match_still_412(client):
    im = _im(client, ws.SEED_NEW_DRAFT_ID)
    client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload(), headers=im
    )
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload(), headers=im
    )
    assert r.status_code == 412, r.text
    assert r.json()["error"] == "stale_write"


def test_malformed_if_match_still_400(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": "garbage"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "malformed_if_match"


def test_wildcard_if_match_still_matches_existing(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": "*"},
    )
    assert r.status_code == 200, r.text


# --- 428 must precede the 422 confirmation gate? NO: shape(422) precedes -------
# (documented ordering: request-shape validation precedes precondition). A missing
# body confirmation is still 422 regardless of If-Match. We assert the mandate order.


def test_unconfirmed_answers_still_422_even_without_if_match(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json={"confirmed_by_user": False, "answers": {}},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "confirmation_required"


# --- current client still hits the 409 immutability guard ---------------------


def test_current_client_still_409_on_already_exported(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_DONE_ID}/export", headers=_im(client, ws.SEED_DONE_ID)
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "record_exists"


def test_missing_if_match_on_exported_record_is_428_not_409(client):
    """Ordering guard: precondition precedes the export-domain conflict. A MISSING
    If-Match on an ALREADY-exported record must return 428 (refresh first), NOT the
    409 immutability response — a version-less client must refresh before it can
    make any current-state decision."""
    r = client.post(f"/api/experiments/{ws.SEED_DONE_ID}/export")  # no If-Match
    assert r.status_code == 428, r.text
    assert r.json()["error"] == "precondition_required"


# --- no deprecation header survives the grace removal -------------------------


def test_no_deprecation_header_on_successful_mutation(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=_im(client, ws.SEED_NEW_DRAFT_ID),
    )
    assert r.status_code == 200
    assert not r.headers.get("X-ISAAC-Deprecation"), "grace signal must be gone in strict mode"
