"""P28.5 — typed evidence-classification API (bound to record_rev).

TEST-FIRST contract (authored BEFORE implementation; RED until
`GET /api/experiments/{id}/evidence-classification` exists). Exposes the P28.4
deterministic `classify_fields` view for the CURRENT record, bound to the
authoritative `record_rev` so a client can detect a stale view.

Axis-cleanliness decision: the mandate's sample `audit_summary {blocking,warnings}`
would mix schema-validity + advisory into the evidence-support result, which the
mandate ELSEWHERE forbids ("keep these axes separate"). This endpoint therefore
carries only the evidence-support axis — `field_results` + a same-axis class
`counts` histogram. Validity/advisory stay in their existing endpoints.

Auth + 404 behave like the other record reads. Truth core untouched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import bind_tutorial_session, tutorial_client

CLASSES = {"supported", "inferred_candidate", "insufficient_evidence", "conflicting_evidence", "unknown"}
FIELD_KEYS = {"field", "classification", "value_state", "explanation", "sources"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def test_endpoint_returns_typed_field_results_bound_to_rev(client):
    r = client.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence-classification")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "record_rev" in body and isinstance(body["record_rev"], int)
    assert "field_results" in body and isinstance(body["field_results"], list) and body["field_results"]
    for fr in body["field_results"]:
        assert set(fr) == FIELD_KEYS, fr
        assert fr["classification"] in CLASSES
    # record_rev matches the authoritative version's rev
    detail = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()
    assert body["record_rev"] == int(detail["version"].split(".")[-1])


def test_counts_are_same_axis_histogram_only(client):
    body = client.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence-classification").json()
    assert "counts" in body
    assert set(body["counts"]) == CLASSES, "counts is a class histogram (evidence-support axis only)"
    assert sum(body["counts"].values()) == len(body["field_results"])
    # axis separation: the evidence result must NOT carry validity/completion verdicts
    assert not ({"valid", "ok", "exportable", "complete", "blocking", "warnings"} & set(body))


def test_ready_record_is_predominantly_supported(client):
    body = client.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence-classification").json()
    assert body["counts"]["supported"] >= 1
    assert body["counts"]["unknown"] == 0  # a ready record earns its values


def test_view_changes_with_record_rev_after_edit(client):
    before = client.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence-classification").json()
    # export bumps rev → the classification view must report the new rev
    etag = client.get(f"/api/experiments/{ws.SEED_READY_ID}").headers["ETag"]
    client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers={"If-Match": etag})
    after = client.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence-classification").json()
    assert after["record_rev"] > before["record_rev"], "the view rev must track the record rev"


def test_missing_record_is_404(client):
    r = client.get("/api/experiments/01MISSINGRECORD00000000000/evidence-classification")
    assert r.status_code == 404
    assert r.json()["error"] == "experiment_not_found"


def test_requires_auth_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    # The session is opened in-process rather than over HTTP: this deployment
    # requires the key, and pinning it as a client default would destroy the 401
    # this test asserts. Same scope either way.
    c = bind_tutorial_session(TestClient(create_app()))
    r = c.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence-classification")
    assert r.status_code == 401


def test_counts_histogram_holds_on_a_raw_partial_seed(client):
    """The class histogram invariant (sum == #fields, keys == the 5 classes) holds
    on a not-yet-ready seed too, not just the ready record."""
    body = client.get(f"/api/experiments/{ws.SEED_PARTIAL_ID}/evidence-classification").json()
    assert set(body["counts"]) == CLASSES
    assert sum(body["counts"].values()) == len(body["field_results"])
    assert all(v >= 0 for v in body["counts"].values())


def test_sources_never_leak_over_the_wire(client):
    """The API must not surface raw answers/tokens/private paths (P28.4 leak-safety
    holds end-to-end)."""
    body = client.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence-classification").text
    assert "/Users/" not in body
