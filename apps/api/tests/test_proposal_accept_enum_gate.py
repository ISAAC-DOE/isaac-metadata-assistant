"""AN ACCEPTED PROPOSAL MUST SATISFY THE SCHEMA'S OWN ENUM AT A RUN FIELD.

THE DEFECT (QA A-10, measured over HTTP under the fixture verifier). A finalized
transcript reading *"The environment was in situ."* mints a run-scoped proposal at
``context.environment`` whose value is the phrase EXACTLY AS WRITTEN — ``"in situ"``,
with a space — because the transcript reader matches no vocabulary
(``transcript_capture._RULES``, the ``environment`` rule's own sentence). "Accept as
Proposed" then answered ``200`` and stored ``"in situ"``, which is not a member of the
schema's enum (``operando``, ``in_situ``, ``ex_situ``, ``in_silico``). The run editor's
select then read *Not set* for a field that held a value, and Check Run failed on it.

The record-level enum branch of ``_apply_accepted_proposal`` already refused an
off-enum value with ``422 not_an_allowed_value``; the run-field branch did not. This
file pins the run-field branch to the same refusal, with the allowed set READ FROM
THE VENDORED SCHEMA rather than transcribed here.

WHAT IS DELIBERATELY NOT ASSERTED: that ``"in situ"`` is mapped to ``in_situ``. It
never is. Choosing the member is the scientist's act ("Correct the Value, Then
Accept"), and the test below that walks that path sends the member explicitly.

ACCEPTANCE STILL NEEDS THE FIXTURE VERIFIER, and the default-configuration refusal
(``409 human_actor_required``) is asserted here too so this file cannot be read as
having weakened it.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.identity as identity
import isaac_api.workspace as ws
from isaac_records.official import schema_path

ACTOR = "synthetic.enum.gate.reviewer"
PATH = "context.environment"
OFF_ENUM = "in situ"
NOTE_TEXT = "Synthetic note (fake): The environment was in situ."


def _schema_enum(path: str) -> list:
    """The enum the vendored official schema declares at ``path`` — read, never copied."""
    from isaac_api.routes import REPO_ROOT

    node = json.loads(schema_path(REPO_ROOT).read_text(encoding="utf-8"))
    for segment in path.split("."):
        node = node["properties"][segment]
    return list(node["enum"])


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    return ws


@pytest.fixture()
def armed(workspace, monkeypatch):
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _client() -> TestClient:
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def record(workspace):
    exp = ws.create_experiment("Synthetic enum gate (fake)", {"kind": "synthetic"}, {})
    exp.add_run(label="Run 1", draft={})
    exp.capture_note(text=NOTE_TEXT, source="typed_note")
    exp.save_versioned()
    return ws.load_experiment(exp.id)


def _etag(client, eid):
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _propose(client, exp, value):
    response = client.post(
        f"/api/experiments/{exp.id}/proposals",
        json={
            "note_id": exp.notes[0].id,
            "run_id": exp.runs[0].id,
            "target_field_path": PATH,
            "proposed_value": value,
            "rule": "the phrase after 'environment', as written",
        },
        headers={"If-Match": _etag(client, exp.id)},
    )
    assert response.status_code == 200, response.text
    return response.json()["proposal"]


def _review(client, eid, pid, **body):
    body.setdefault("confirmed_by_user", True)
    return client.post(
        f"/api/experiments/{eid}/proposals/{pid}/review",
        json=body,
        headers={"If-Match": _etag(client, eid)},
    )


def _run_fields(client, exp) -> dict:
    response = client.get(f"/api/experiments/{exp.id}/runs/{exp.runs[0].id}")
    assert response.status_code == 200, response.text
    return response.json()["run"]["fields"]


def _proposal(client, exp, pid) -> dict:
    response = client.get(f"/api/experiments/{exp.id}/proposals")
    assert response.status_code == 200, response.text
    return next(p for p in response.json()["proposals"] if p["proposal_id"] == pid)


def test_the_schema_really_closes_the_target_and_the_phrase_is_outside_it():
    """The premise, measured — otherwise the refusal below would be vacuous."""
    allowed = _schema_enum(PATH)
    assert "in_situ" in allowed
    assert OFF_ENUM not in allowed


def test_accept_as_proposed_refuses_an_off_enum_run_value_and_writes_nothing(record, armed):
    """MUTATION: deleting the run-field enum check in `_apply_accepted_proposal` turns
    this 422 back into the measured 200 that stored ``"in situ"``."""
    client = _client()
    proposal = _propose(client, record, OFF_ENUM)
    before = _run_fields(client, record)

    response = _review(
        client, record.id, proposal["proposal_id"], action="accept", accepted_from="candidate"
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "not_an_allowed_value"
    assert body["key"] == PATH
    assert body["allowed"] == _schema_enum(PATH)
    # The rejected value is never echoed back — an error body is not a reflection surface.
    assert OFF_ENUM not in json.dumps(body)
    assert _run_fields(client, record) == before
    assert _proposal(client, record, proposal["proposal_id"])["state"] == "open"


def test_correct_the_value_then_accept_with_the_schema_member_writes_it(record, armed):
    """The path the screen steers to: the SCIENTIST chooses the member. Nothing maps it."""
    client = _client()
    proposal = _propose(client, record, OFF_ENUM)

    response = _review(
        client,
        record.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="edited",
        value="in_situ",
    )

    assert response.status_code == 200, response.text
    assert _run_fields(client, record)[PATH]["value"] == "in_situ"
    reviewed = _proposal(client, record, proposal["proposal_id"])
    assert reviewed["state"] == "accepted"
    # The proposal keeps what it proposed — the correction is the acceptance's, not its.
    assert reviewed["proposed_value"] == OFF_ENUM


def test_a_correction_that_is_itself_off_enum_is_refused_the_same_way(record, armed):
    client = _client()
    proposal = _propose(client, record, OFF_ENUM)
    before = _run_fields(client, record)

    response = _review(
        client,
        record.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="edited",
        value="In-Situ",
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"] == "not_an_allowed_value"
    assert _run_fields(client, record) == before


def test_an_on_enum_proposal_is_still_accepted_as_proposed(record, armed):
    """Negative control: the gate refuses off-enum values only, not the path."""
    client = _client()
    proposal = _propose(client, record, "operando")

    response = _review(
        client, record.id, proposal["proposal_id"], action="accept", accepted_from="candidate"
    )

    assert response.status_code == 200, response.text
    assert _run_fields(client, record)[PATH]["value"] == "operando"


def test_the_default_configuration_still_refuses_acceptance_first(record):
    """I4 is untouched: with no verifier the refusal is the 409, before any value check."""
    client = _client()
    proposal = _propose(client, record, OFF_ENUM)

    response = _review(
        client, record.id, proposal["proposal_id"], action="accept", accepted_from="candidate"
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "human_actor_required"
