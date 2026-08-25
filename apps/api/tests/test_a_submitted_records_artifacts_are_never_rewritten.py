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

WHY EVERY ATTEMPT NOW CARRIES A DECLARED EXPECTATION, AND WHY THIS PARAGRAPH USED TO
ARGUE THE OPPOSITE. It said the status codes were *"deliberately not asserted"*, because
pinning them "would duplicate twenty focused tests and break whenever any one of them
legitimately changes", and it guarded only ``< 500`` and ``!= 404`` — *"because either
would mean the sweep stopped exercising the route it names and would let this file pass
while checking nothing"*. **``422`` has exactly that property, and it was unguarded.**

*(That quoted "twenty" was wrong as well, and in three places: the list held **19**
attempts. Every count in the assertion messages below is now interpolated from
``len(attempts)`` rather than written out, and the two figures this prose does state are
HISTORICAL — measurements of what was there in August 2026, which a later route cannot
falsify.)*

Instrumented, SIX of the 19 attempts never reached a write path at all, and five of those
six were the sweep's own payloads being wrong rather than any route refusing anything
interesting:

    422 POST /answers              unrecognized_field    (`sample.material.name` is not
    422 POST /edit                 unrecognized_field     an answer key these routes take
    422 POST /runs/{run}/answers   unrecognized_field     — only `qc`, `series`,
    422 POST /runs/{run}/edit      unrecognized_field     `descriptor`, `descriptor_label`,
                                                          `edge` and stored asset URIs are)
    422 POST /runs/{run}/overrides invalid_envelope      (a `verified` envelope with no
                                                          evidence, refused by the envelope
                                                          check before any write)
    422 POST /conflicts/resolve    address_not_conflicting

The last was the sharpest: it contributed **nothing** in the very change whose subject is
conflict resolution, because the fixture carried no conflict. So the sweep read as
whole-write-surface coverage and delivered 13, and the blanket assertion could not tell
the difference. **The remedy is not a blanket ``!= 422``** — that is one status class
better and still cannot distinguish "this route refused for a reason worth pinning" from
"our payload was nonsense". Each attempt now declares what it expects, and the loop
asserts it:

  * :data:`WRITES` — accepted (``< 300``) **and the document's version token advanced**.
    This is the reviewer's stronger alternative — assert that the document actually MOVED
    — and it is adopted for every attempt that can move it, because a ``200`` that changes
    nothing exercises the invariant no better than a ``422`` does. How many that is, is
    counted by the ratchet below rather than asserted in this prose.
  * :data:`WRITES_ROWS` — accepted, and a new submission row appended, while the document
    does NOT move. One attempt, ``POST /submit``, and it earns its own class rather than a
    weakened :data:`WRITES`: a submission writes to the submission store, not to the
    experiment document, so ``rev`` is the wrong oracle for it and pretending otherwise
    would mean either a failing assertion or a blanket one. Measured, not assumed — the
    first version of this file asserted ``WRITES`` here and went red.
  * :data:`ACCEPTED_UNCHANGED` — accepted and deliberately changes nothing. One attempt,
    ``POST /ingestion/csv/preview``, which is a preview and writes by design nowhere. If it
    ever starts moving the document, that is a real change and it fails here.
  * :func:`refused` — an exact ``(status, error)``, with the reason recorded in the table.
    Three attempts, and each refusal is either the invariant itself or the honest reason
    the route cannot write on a submitted record. These are the only statuses this file
    pins, which is the narrow form of what the old paragraph was right to be wary of: a
    pinned status is a liability, so it is spent only where the refusal is the point.

ONE CONSEQUENCE OF THE FIXTURE CARRYING A REAL CONFLICT, stated because it is a genuine
behaviour change and not an accident of ordering: once ``POST /conflicts/resolve``
succeeds, the record's content signature moves (``submissions.content_signature`` covers
the stored decisions), so ``POST /submit`` a second time is a NEW submission rather than
an ``already_submitted`` refusal. It writes a second revision row and a second submission
row — and the assertions below check that every row **already on file** is untouched, not
that no row was added, so a second submission is exactly the case they exist to police.

ORDERING IS PART OF THE FIXTURE. ``POST /runs`` (add) is issued LAST rather than sixth,
because an added run is incomplete and made two later attempts uninteresting: ``/export``
answered ``200 {"ok": false}`` (refused for the new run's missing fields, never reaching
the immutability check) and ``/submit`` answered ``409 submission_blocked`` (for the same
reason). With the add moved to the end, ``/export`` answers ``409 record_exists`` — which
IS the immutability refusal this file is about — and ``/submit`` exercises the real
second-submission write path.

Promoted from an adversarial probe that printed these rows rather than asserting them.
Nothing here was failing when it was promoted; the value is that a future change which
starts rewriting a submitted record's artifacts fails HERE, at the invariant, instead of
being discovered from a corrupted record.
"""
from __future__ import annotations

import copy
import hashlib

import pytest

import isaac_api.identity as identity
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws
from fastapi.testclient import TestClient
from isaac_records.models import user_confirmation

from submission_fake import FakeSubmissionConnection, fake_store
from test_export_fan_out import _split_full_draft

EXPERIMENT_ID = "01SUBMITTEDIMMUTABLE00001"
ACTOR = "ada.lovelace"

#: The record-level address whose evidence is deliberately made to disagree with itself,
#: so ``POST /conflicts/resolve`` has something to resolve. Both runs inherit it, so the
#: submission discloses two conflicting units — which is the shape this product normally
#: produces and the one the resolution defect was measured on.
CONFLICT_ADDRESS = "sample.material.name"

#: Accepted, AND the experiment's ``(rev, generation)`` advanced. The strong form: a
#: route that answered ``200`` and moved nothing has not exercised the invariant.
WRITES = "writes"

#: Accepted, and a new submission row appended — the document deliberately does NOT
#: move. A submission is recorded in the submission store rather than in the experiment
#: document, so ``rev`` cannot witness it; the row count can.
WRITES_ROWS = "writes_rows"

#: Accepted, and deliberately moves nothing. Reserved for routes that write by design
#: nowhere; a route drifting INTO this class fails, because its expectation says WRITES.
ACCEPTED_UNCHANGED = "accepted_unchanged"


def refused(status: int, error: str, why: str) -> tuple[str, int, str, str]:
    """An exact expected refusal, with the reason it is expected written beside it.

    ``why`` is never asserted on — it is there so that a future reader deciding whether
    a changed status is a regression or a legitimate change can see what this file
    believed, rather than having to reconstruct it from a bare number.
    """
    return ("refused", status, error, why)


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


def _version(exp) -> tuple:
    """The document's version token — what the API serves as its ETag components.

    Used as the "did anything happen?" oracle. ``rev`` counts every authoritative
    mutation, so it moves for a run-level write as well as a record-level one, and
    ``generation`` is carried with it so a re-creation could never look like a no-op.
    """
    return (exp.rev, exp.generation)


def _competing(*answers: str) -> dict:
    """A draft envelope whose evidence asserts two different values — a conflict.

    ``evidence_classify._classify_entry`` rule 1 makes a field ``conflicting_evidence``
    as soon as two distinct non-null answers are recorded for it, which is the same
    shape ordinary re-answering produces. Built here rather than imported from
    ``test_a_conflict_decision_reaches_the_submission_history`` so that neither file's
    fixture can be changed out from under the other.
    """
    return {
        "value": answers[0],
        "status": "verified",
        "evidence": [
            user_confirmation("What material?", answer, "2026-01-01T00:00:00Z")
            for answer in answers
        ],
    }


def _rows_by_id(rows, key) -> dict:
    return {row[key]: copy.deepcopy(row) for row in rows}


def test_no_write_route_rewrites_a_submitted_records_artifacts_or_rows(client, db):
    experiment_draft, run_draft = _split_full_draft()
    experiment_draft["fields"][CONFLICT_ADDRESS] = _competing("CuO", "Cu2O")
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
    assert submitted.json()["conflict_summary"]["unresolved_field_count"] > 0, (
        "the fixture must actually carry an unresolved conflict, or the "
        "POST /conflicts/resolve attempt below proves nothing — which is precisely "
        "what it used to do"
    )
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

    attempts: list[tuple[str, object, object]] = [
        (
            # `edge` rather than a field path: the answering routes take the `id` values
            # the pending-questions operation serves, which are `qc`, `series`,
            # `descriptor`, `descriptor_label`, `edge` and stored asset URIs — never a
            # dotted field address. `edge` is also the one of those that is NOT
            # run-owned on a fan-out record, so it is the one that can write here;
            # `qc` and `descriptor_label` were measured answering `409
            # belongs_to_a_run`, correctly, which is a far more useful refusal than the
            # `unrecognized_field` the old payload earned.
            "POST /answers",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/answers",
                json={"confirmed_by_user": True, "answers": {"edge": "K"}},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /edit",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/edit",
                json={"confirmed_by_user": True, "answers": {"edge": "L3"}},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "PATCH /runs/{run}",
            WRITES,
            lambda: client.patch(
                f"/api/experiments/{eid}/runs/{run_a}",
                json={"confirmed_by_user": True, "fields": {"context.temperature_K": 4711}},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            # THE EVIDENCE ENTRY IS THE POINT. A `verified` envelope with an empty
            # evidence list is refused `422 invalid_envelope` by the no-guessing check
            # before any write, which is the envelope contract working — and which meant
            # this attempt used to exercise nothing at all.
            "POST /runs/{run}/overrides",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/overrides",
                json={
                    "confirmed_by_user": True,
                    "address": f"field:{CONFLICT_ADDRESS}",
                    "payload": {
                        "value": "SWEEP-OVR",
                        "status": "verified",
                        "evidence": [
                            user_confirmation(
                                "What material?", "SWEEP-OVR", "2026-01-01T00:00:00Z"
                            )
                        ],
                    },
                },
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs/{run}/overrides/clear",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/overrides/clear",
                json={"confirmed_by_user": True, "address": f"field:{CONFLICT_ADDRESS}"},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        ("POST /notes", WRITES, capture_note),
        (
            "POST /notes/{id}/review",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/notes/{note_id.get('id', 'missing')}/review",
                json={"confirmed_by_user": True, "action": "keep"},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /transcript",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/transcript",
                json={"text": "the sample was copper oxide", "finalized": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /assets",
            WRITES,
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
            WRITES,
            lambda: client.patch(
                f"/api/experiments/{eid}/assets/sweep_asset",
                json={"confirmed_by_user": True, "sha256": "b" * 64},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /assets/{id}/remove",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/assets/sweep_asset/remove",
                json={"confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /runs/{run}/answers",
            refused(
                422,
                "already_answered",
                # THE ONE ROUTE THAT GENUINELY CANNOT WRITE HERE, and it is a property
                # of the fixture rather than of the payload. A record is only
                # submittable if it is exportable, and exportable means every run-level
                # answerable block is already answered — so `/answers`, whose whole job
                # is OPEN questions, can only ever be told so. The refusal is asserted
                # rather than tolerated, and it is a real one: `descriptor` names a
                # block this run holds, so the route reaches its already-answered check
                # and directs the caller to `/edit`. (The old payload's
                # `unrecognized_field` said something quite different and far less
                # useful — that the key was never an answer key at all.)
                "a submitted record is exportable, so every run-level answerable block "
                "is already answered and this route has nothing open to write",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/answers",
                json={
                    "confirmed_by_user": True,
                    "answers": {
                        "descriptor": {
                            "class": "spectrum_summary",
                            "values": {"edge_position_eV": 8979.0},
                        }
                    },
                },
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            # The correction path, which is what a submitted record's run-level blocks
            # are reachable through, and which does write.
            "POST /runs/{run}/edit",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/edit",
                json={
                    "confirmed_by_user": True,
                    "answers": {"qc": {"status": "compromised", "note": "sweep edit"}},
                },
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /conflicts/resolve",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/conflicts/resolve",
                json={
                    "confirmed_by_user": True,
                    "address": CONFLICT_ADDRESS,
                    "outcome": "resolved",
                    "chosen_value": "CuO",
                    "chosen_from": "candidate",
                },
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /ingestion/csv/preview",
            ACCEPTED_UNCHANGED,
            lambda: client.post(
                f"/api/experiments/{eid}/ingestion/csv/preview",
                content=b"field,value\nsample.material.name,SWEEP-CSV\n",
                headers={"Content-Type": "text/csv", "If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /export",
            refused(
                409,
                "record_exists",
                # THIS REFUSAL IS THE INVARIANT, not an obstacle to it. The record's
                # official artifacts exist and are immutable, so a second export of the
                # same units is refused by name rather than republishing over them —
                # and the attempt is made AFTER a dozen writes have moved the document,
                # which is the case where a republish would be most tempting and most
                # destructive.
                "the official records already exist and are immutable; no route "
                "republishes one",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/export", headers={"If-Match": _etag(client, eid)}
            ),
        ),
        (
            # A SECOND SUBMISSION, ACCEPTED — see the ordering note in the module
            # docstring. The conflict decision above moved the content signature, so
            # this is new content rather than a replay, and it writes a second revision
            # row and a second submission row while every earlier row stays put.
            "POST /submit (again)",
            WRITES_ROWS,
            lambda: client.post(
                f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
            ),
        ),
        (
            "POST /runs (add)",
            WRITES,
            lambda: client.post(
                f"/api/experiments/{eid}/runs",
                json={"confirmed_by_user": True, "label": "Run C"},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /runs/{run}/remove",
            refused(
                409,
                "run_exported",
                # Also the invariant: removing an exported run would orphan a published
                # official record. Left as the last attempt because it is the one whose
                # success would be most visible in `_artifacts`.
                "an exported run cannot be removed; its official record is published",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/remove",
                json={"confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
    ]

    # THE COVERAGE RATCHET. The prose above quotes no route count of its own — the two
    # figures a reader needs are derived here, so a payload that quietly stops writing
    # cannot leave a stale number behind it. This is the guard the old `< 500` /
    # `!= 404` pair could not be: it fails if an attempt is DOWNGRADED, not only if it
    # errors.
    writing = [name for name, expectation, _ in attempts if expectation is WRITES]
    assert len(attempts) == 19, (
        f"the sweep now issues {len(attempts)} attempts, not 19. Adding a route here is "
        f"welcome; do it deliberately, give the new attempt an expectation, and update "
        f"this number and the WRITES count below in the same edit."
    )
    assert len(writing) == 14, (
        f"{len(writing)} of {len(attempts)} attempts expect to move the document, not "
        f"14. If a route legitimately stopped writing, change its expectation AND this "
        f"number in the same edit; do not lower one silently. Writing: {writing}"
    )
    assert [n for n, e, _ in attempts if e is WRITES_ROWS] == ["POST /submit (again)"], (
        "WRITES_ROWS exists for the submission path alone; any other route landing in "
        "it is a route whose write nothing in this file is checking"
    )

    for name, expectation, attempt in attempts:
        before = _version(ws.load_experiment(eid))
        response = attempt()
        after = ws.load_experiment(eid)
        assert after is not None, f"{name} destroyed the record"

        # The blanket guards, kept: a 5xx or a 404 means the sweep stopped exercising
        # the route it names. They are now the floor rather than the whole check —
        # every attempt's declared expectation is stricter than both.
        assert response.status_code < 500, f"{name} raised: {response.text[:300]}"
        assert response.status_code != 404, (
            f"{name} answered 404 — this sweep is no longer exercising that route, so "
            "it would pass while checking nothing"
        )

        if expectation is WRITES:
            assert response.status_code < 300, (
                f"{name} expects to reach the write path and answered "
                f"{response.status_code}: {response.text[:300]}. Six attempts in this "
                f"list once answered 422 for payload reasons and this file passed "
                f"while exercising 13 of {len(attempts)} routes; either fix the "
                f"payload or declare the refusal."
            )
            assert _version(after) != before, (
                f"{name} was accepted and moved nothing — the document's version token "
                f"is still {before}. A no-op exercises this file's invariant no better "
                f"than a refusal does; either make it write or declare it "
                f"ACCEPTED_UNCHANGED with the reason."
            )
        elif expectation is WRITES_ROWS:
            assert response.status_code < 300, (
                f"{name} expects to record a submission and answered "
                f"{response.status_code}: {response.text[:300]}"
            )
            assert len(db.submissions) > len(baseline_submissions), (
                f"{name} was accepted and recorded no submission row. It is only a "
                f"new submission because the conflict decision above moved the content "
                f"signature; if that stops being true this attempt is a replay and "
                f"exercises nothing."
            )
            assert _version(after) == before, (
                f"{name} moved the experiment document from {before} to "
                f"{_version(after)} — a submission records rows and does not rewrite "
                f"the document, and this file would rather fail than quietly widen "
                f"what a submission may touch"
            )
        elif expectation is ACCEPTED_UNCHANGED:
            assert response.status_code < 300, (
                f"{name} expects to be accepted and answered {response.status_code}: "
                f"{response.text[:300]}"
            )
            assert _version(after) == before, (
                f"{name} is declared to change nothing and moved the document from "
                f"{before} to {_version(after)}"
            )
        else:
            _, status, error, why = expectation
            body = response.json() if response.content else {}
            assert (response.status_code, body.get("error")) == (status, error), (
                f"{name} is declared to be refused {status} {error} because {why} — it "
                f"answered {response.status_code} {body.get('error')!r}. If that is a "
                f"legitimate change, update the expectation and say why; if the route "
                f"now writes, this file's invariant is what changed."
            )
            assert _version(after) == before, (
                f"{name} was refused {status} and still moved the document from "
                f"{before} to {_version(after)}"
            )

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
