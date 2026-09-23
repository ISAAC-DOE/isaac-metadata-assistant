"""THE ADD STAGE PREDICTS WHAT THE BATCH THEN DOES — `hist.send_plan` (2026-09-23).

An independent review measured the Add stage saying "11 can be sent" and the batch then
reporting "9 sent · 2 could not": an alignment acquisition's run-owned values looked
sendable and had no run to go to, and the stage and the report grouped what they would
not send by two different rules. Now the session view publishes `send_plan`, computed by
`hist.batch_partition` — the SAME function the batch route partitions with — so the
prediction and the report are one categorisation by construction. These tests hold that
as a property over both synthetic corpora.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.capabilities as capabilities
import isaac_api.historical_import as hist
import isaac_api.identity as identity

SEMANTICS = "tests/fixtures/bl15/semantics/multi_operator_corpus"
ARCHIVE = "bl15_synthetic_semantics_corpus"
MINI = "bl15_synthetic_mini_corpus"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, ARCHIVE, SEMANTICS)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _session(client, archive):
    import_id = client.post("/api/imports", json={"label": "plan"}).json()["import"]["import_id"]
    assert client.post(
        f"/api/imports/{import_id}/sources", json={"kind": "archive", "fixture_name": archive}
    ).status_code == 200
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return import_id, client.get(f"/api/imports/{import_id}").json()["import"]


def _record(client):
    response = client.post("/api/experiments", json={"title": "plan record"})
    assert response.status_code in (200, 201), response.text
    body = response.json()
    return body.get("id") or body["experiment"]["id"]


def _etag(client, eid):
    return client.get(f"/api/experiments/{eid}").headers["ETag"]


@pytest.mark.parametrize("archive", [ARCHIVE, MINI])
def test_the_published_plan_is_exactly_what_the_batch_then_does(client, archive):
    import_id, view = _session(client, archive)
    plan = view["send_plan"]
    predicted_sent = set(plan["sendable"]) - set(plan["no_run_when_creating_runs"])
    assert predicted_sent, "nothing is predicted sendable — the property would be vacuous"

    eid = _record(client)
    body = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    ).json()

    assert {row["candidate_id"] for row in body["sent"]} == predicted_sent
    no_run = {r["candidate_id"] for r in body["not_sent"] if r["error"] == "no_run_for_this_candidate"}
    assert no_run == set(plan["no_run_when_creating_runs"])
    others = {r["candidate_id"]: r["error"] for r in body["not_sent"] if r["error"] != "no_run_for_this_candidate"}
    assert others == plan["not_sent"]
    assert body["counts"]["sent"] == len(predicted_sent)


def test_the_header_ready_count_is_the_plans_sendable_count(client):
    """"Ready" means a value can go forward — the plan's sendable set, no more."""
    _import_id, view = _session(client, MINI)
    ready = {c["candidate_id"] for c in view["reconstruction"]["candidates"] if c["review_status"] == "ready"}
    assert ready == set(view["send_plan"]["sendable"])
