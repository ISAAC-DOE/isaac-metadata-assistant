"""A SWEEP: after a submission, no write route rewrites an artifact or a stored row.

WHAT THIS PINS THAT NO SINGLE-ROUTE TEST DOES. Exported official records are IMMUTABLE
and no route republishes one; a submission's revision row is append-only. Both
properties are asserted in places for the routes that were being written at the time —
``test_export_fan_out.py`` for the export path, ``test_submission_store.py`` for the
rows — but nothing walked the WHOLE write surface of a submitted record and checked
that none of it reaches back. This does: it submits a two-run record and then issues
every mutating request the API offers against it, one after another, asserting after
each one that

  * every file in the record's ``records`` directory has the same sha256 it had the
    moment the submission was recorded, and no file has appeared or vanished; and
  * every revision and submission row already on file is byte-for-byte what it was.

WHY THE STATUS CODES ARE DELIBERATELY NOT ASSERTED. The interesting property is what
the request DID, not what it answered, and pinning twenty status codes here would
duplicate twenty focused tests and break whenever any one of them legitimately
changes. Some of these requests are refused, some succeed and change the document, and
both are fine — an accepted write that leaves the published artifacts alone is exactly
the invariant. What IS asserted about the responses is narrow and load-bearing: none
may be a ``5xx`` and none may be a ``404``, because either would mean the sweep stopped
exercising the route it names and would let this file pass while checking nothing.

Promoted from an adversarial probe that printed these twenty rows rather than asserting
them. Nothing here was failing when it was promoted; the value is that a future change
which starts rewriting a submitted record's artifacts fails HERE, at the invariant,
instead of being discovered from a corrupted record.
"""
from __future__ import annotations

import copy
import hashlib

import pytest

import isaac_api.identity as identity
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws
from fastapi.testclient import TestClient

from submission_fake import FakeSubmissionConnection, fake_store
from test_export_fan_out import _split_full_draft

EXPERIMENT_ID = "01SUBMITTEDIMMUTABLE00001"
ACTOR = "ada.lovelace"


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return ws


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def client(armed, db, monkeypatch):
    store = fake_store(db)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _etag(client, eid):
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, eid, run_id):
    response = client.get(f"/api/experiments/{eid}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _artifacts(exp) -> dict[str, str]:
    """``filename -> sha256`` for every file in this record's records directory."""
    directory = exp.records_dir
    if not directory.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _rows_by_id(rows, key) -> dict:
    return {row[key]: copy.deepcopy(row) for row in rows}


def test_no_write_route_rewrites_a_submitted_records_artifacts_or_rows(client, db):
    experiment_draft, run_draft = _split_full_draft()
    exp = ws.create_experiment(
        "Submitted record", {"kind": "synthetic"}, experiment_draft, id=EXPERIMENT_ID
    )
    for label in ("Run A", "Run B"):
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    eid = EXPERIMENT_ID
    run_a = ws.load_experiment(eid).sorted_runs()[0].id

    submitted = client.post(
        f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
    )
    assert submitted.status_code == 200, submitted.text
    baseline_artifacts = _artifacts(ws.load_experiment(eid))
    assert len(baseline_artifacts) == 4, (
        f"two runs must have published two record/sidecar pairs: {baseline_artifacts}"
    )
    baseline_revisions = _rows_by_id(db.revisions, "revision_id")
    baseline_submissions = _rows_by_id(db.submissions, "submission_id")

    note_id: dict[str, str] = {}

    def capture_note():
        response = client.post(
            f"/api/experiments/{eid}/notes",
            json={"text": "a note after the submission", "source": "typed_note"},
            headers={"If-Match": _etag(client, eid)},
        )
        if response.status_code == 201:
            note_id["id"] = response.json()["note"]["id"]
        return response

    attempts: list[tuple[str, object]] = [
        (
            "POST /answers",
            lambda: client.post(
                f"/api/experiments/{eid}/answers",
                json={
                    "confirmed_by_user": True,
                    "answers": {"sample.material.name": "SWEEP-A"},
                },
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /edit",
            lambda: client.post(
                f"/api/experiments/{eid}/edit",
                json={
                    "confirmed_by_user": True,
                    "answers": {"sample.material.name": "SWEEP-EDIT"},
                },
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "PATCH /runs/{run}",
            lambda: client.patch(
                f"/api/experiments/{eid}/runs/{run_a}",
                json={"confirmed_by_user": True, "fields": {"context.temperature_K": 4711}},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs/{run}/overrides",
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/overrides",
                json={
                    "confirmed_by_user": True,
                    "address": "field:sample.material.name",
                    "payload": {"value": "SWEEP-OVR", "status": "verified", "evidence": []},
                },
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs/{run}/overrides/clear",
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/overrides/clear",
                json={"confirmed_by_user": True, "address": "field:sample.material.name"},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs (add)",
            lambda: client.post(
                f"/api/experiments/{eid}/runs",
                json={"confirmed_by_user": True, "label": "Run C"},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /runs/{run}/remove",
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/remove",
                json={"confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        ("POST /notes", capture_note),
        (
            "POST /notes/{id}/review",
            lambda: client.post(
                f"/api/experiments/{eid}/notes/{note_id.get('id', 'missing')}/review",
                json={"confirmed_by_user": True, "action": "keep"},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /transcript",
            lambda: client.post(
                f"/api/experiments/{eid}/transcript",
                json={"text": "the sample was copper oxide", "finalized": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /assets",
            lambda: client.post(
                f"/api/experiments/{eid}/assets",
                json={
                    "confirmed_by_user": True,
                    "asset_id": "sweep_asset",
                    "content_role": "reduction_product",
                    "uri": "synthetic://example/sweep/CuO2.xdi",
                    "sha256": "a" * 64,
                },
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "PATCH /assets/{id}",
            lambda: client.patch(
                f"/api/experiments/{eid}/assets/sweep_asset",
                json={"confirmed_by_user": True, "sha256": "b" * 64},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /assets/{id}/remove",
            lambda: client.post(
                f"/api/experiments/{eid}/assets/sweep_asset/remove",
                json={"confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /conflicts/resolve",
            lambda: client.post(
                f"/api/experiments/{eid}/conflicts/resolve",
                json={
                    "confirmed_by_user": True,
                    "address": "sample.material.name",
                    "outcome": "resolved",
                    "chosen_value": "SWEEP-RES",
                },
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /export",
            lambda: client.post(
                f"/api/experiments/{eid}/export", headers={"If-Match": _etag(client, eid)}
            ),
        ),
        (
            "POST /submit (again)",
            lambda: client.post(
                f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
            ),
        ),
        (
            "POST /ingestion/csv/preview",
            lambda: client.post(
                f"/api/experiments/{eid}/ingestion/csv/preview",
                content=b"field,value\nsample.material.name,SWEEP-CSV\n",
                headers={"Content-Type": "text/csv", "If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /runs/{run}/answers",
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/answers",
                json={"confirmed_by_user": True, "answers": {"context.temperature_K": 4712}},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs/{run}/edit",
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/edit",
                json={"confirmed_by_user": True, "answers": {"context.temperature_K": 4713}},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
    ]

    for name, attempt in attempts:
        response = attempt()
        assert response.status_code < 500, f"{name} raised: {response.text[:300]}"
        assert response.status_code != 404, (
            f"{name} answered 404 — this sweep is no longer exercising that route, so "
            "it would pass while checking nothing"
        )

        after = ws.load_experiment(eid)
        assert after is not None, f"{name} destroyed the record"
        assert _artifacts(after) == baseline_artifacts, (
            f"{name} changed the published artifacts of a submitted record. Exported "
            "records are immutable and no route republishes one, so a submission's "
            "record ids would now name bytes nobody submitted."
        )
        for revision_id, row in baseline_revisions.items():
            current = _rows_by_id(db.revisions, "revision_id").get(revision_id)
            assert current == row, f"{name} rewrote revision row {revision_id}"
        for submission_id, row in baseline_submissions.items():
            current = _rows_by_id(db.submissions, "submission_id").get(submission_id)
            assert current == row, f"{name} rewrote submission row {submission_id}"
