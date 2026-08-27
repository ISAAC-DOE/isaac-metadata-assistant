"""AN ADVERSARIAL SWEEP: no shipped route mutates already-submitted science.

BE PRECISE ABOUT WHAT IS PROVED HERE, BECAUSE TWO CLAIMS ARE EASY TO CONFUSE
===========================================================================
This file proves **no shipped route mutates the submission history**. It does NOT
prove **the history cannot be mutated**, and nothing in this repository can prove
that today. ``submission_store.py`` says so itself: append-only is guaranteed by
statement inventory plus ``test_no_submission_statement_updates_or_deletes_history``,
NOT at the database level, because a ``BEFORE UPDATE OR DELETE`` trigger needs dollar
quoting that ``db_migrate.split_statements`` refuses and ``REVOKE UPDATE, DELETE`` is
refused by ``db_write._FORBIDDEN_KEYWORDS``. A psql session, a superuser, or a future
application statement can still change those rows. The first claim is the one this
file makes.

WHAT THIS ADDS TO ``test_a_submitted_records_artifacts_are_never_rewritten.py``
==============================================================================
That file is the existing sweep and it is good. Three gaps, each closed here:

1. **It checks two of the five tables.** It re-reads ``db.revisions`` and
   ``db.submissions`` after every attempt. ``isaac_run_revisions``,
   ``isaac_revision_changes`` and ``isaac_submission_runs`` — the rows that say WHICH
   runs a revision covered, WHAT changed, and WHICH records a submission named — were
   never re-read, so a route that rewrote one of them would have passed. All five are
   deep-copied and compared here, per attempt.
2. **Six write paths were not in it** — counted against that file's 19 attempts, and
   one of them is this branch's new destructive operation: ``POST .../discard``,
   ``PATCH /experiments/{id}`` (rename), ``POST .../warnings``, ``POST .../validate``,
   ``POST .../audit`` and ``POST .../runs/{run}/check``. The last four are POSTs that
   write nothing by design, which is exactly the kind of route that quietly starts
   writing.
3. **MCP was not in it at all.** Six mutating MCP operations exist and reach the same
   handlers through a different client; they are driven here through
   ``AsgiApiClient`` rather than assumed to be equivalent.

It also replaces the sweep's hardcoded ``len(attempts) == 19`` ratchet with a DERIVED
one: :func:`test_the_sweep_covers_every_mutating_route_this_api_publishes` reads the
app's own route table and fails if a mutating route addressed to an experiment is
neither swept nor listed with a written reason.

THE FIXTURE IS BUILT THROUGH THE PUBLIC API, WITH VALUES WRITTEN OUT. The existing
sweep builds its record from ``_split_full_draft()`` — the fixture sheet that already
carries every value a scientist has to supply. This one creates the record through
``POST /api/experiments``, answers its questions, and manufactures its conflict the way
the product manufactures one: by writing the same run-level field twice with different
values. Nothing is harvested.

Nothing here opens a network connection, reads real data, or touches a database.
No production code is modified by anything in this file.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws
from isaac_api.mcp.client import AsgiApiClient
from isaac_api.mcp.policy import OPERATIONS
from isaac_records.models import user_confirmation

from submission_fake import FakeSubmissionConnection, fake_reader, fake_store

ACTOR = "ada.lovelace"

DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}
SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8970, 8980, 8990]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.02, 0.85, 1.45],
            }
        ],
    }
]
QC = {"status": "valid", "evidence": "I0 stable across all scans; no glitches."}

#: The run-level address deliberately written twice, with different values, so the
#: record carries a REAL conflict and ``POST /conflicts/resolve`` has something to
#: decide. ``timestamps.*`` is chosen over ``context.*`` because the official schema
#: declares ``context.required == ["environment", "temperature_K"]``, so writing one
#: ``context`` field alone makes the record un-exportable and therefore un-submittable —
#: which would have made this whole fixture unbuildable.
CONFLICT_ADDRESS = "timestamps.acquired_start_utc"
CONFLICT_VALUES = ("2026-01-01T00:00:00Z", "2026-02-02T00:00:00Z")

#: How many revisions :func:`_submitted_fixture` leaves on file. TWO, deliberately —
#: see the comment there for why one is not enough.
FIXTURE_REVISIONS = 2

#: The five tables a submission touches. Named rather than inlined so the assertion
#: message can say WHICH one moved, and so adding a sixth is a visible edit.
HISTORY_TABLES = ("revisions", "run_revisions", "changes", "submissions", "submission_runs")

#: Declared expectations, in the vocabulary the existing sweep established.
ACCEPTED = "accepted"
#: Accepted and deliberately writes nothing anywhere — a read dressed as a POST.
READ_ONLY_POST = "read_only_post"


def refused(status: int, error: str, why: str):
    """An exact expected refusal, with the reason recorded beside it (never asserted)."""
    return ("refused", status, error, why)


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def app(tmp_path, monkeypatch, db):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(db))
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# --- helpers ------------------------------------------------------------------


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, eid: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{eid}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _artifacts(eid: str) -> dict[str, str]:
    exp = ws.load_experiment(eid)
    if exp is None or not exp.records_dir.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(exp.records_dir.iterdir())
        if path.is_file()
    }


def _history(db) -> dict[str, list]:
    """A DEEP COPY of every row in all five tables, keyed by table name.

    Deep-copied because the fake stores real dicts: a shallow snapshot would compare a
    row against itself and pass however much a route had rewritten it.
    """
    return {name: copy.deepcopy(getattr(db, name)) for name in HISTORY_TABLES}


_ROW_KEY = {
    "revisions": "revision_id",
    "run_revisions": "run_revision_id",
    "changes": "change_id",
    "submissions": "submission_id",
    "submission_runs": "submission_run_id",
}


def _assert_no_row_moved(db, baseline: dict[str, list], what: str) -> None:
    """Every row already on file is byte-for-byte what it was. New rows are allowed."""
    for table, rows in baseline.items():
        current = {row[_ROW_KEY[table]]: row for row in getattr(db, table)}
        for row in rows:
            key = row[_ROW_KEY[table]]
            assert key in current, (
                f"{what} DELETED {table} row {key}. The submission history is "
                f"append-only and no shipped route may remove one."
            )
            assert current[key] == row, (
                f"{what} REWROTE {table} row {key}.\n  was: {row}\n  now: {current[key]}"
            )


def _submitted_fixture(client, db) -> tuple[str, str, str]:
    """A submitted two-run record a person built, carrying a real unresolved conflict.

    Returns ``(experiment_id, first_run_id, second_run_id)``.
    """
    created = client.post("/api/experiments", json={"title": "Cu K-edge XANES"})
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    filled = client.post(
        f"/api/experiments/{eid}/answers",
        json={
            "answers": {
                "series": copy.deepcopy(SERIES),
                "descriptor": copy.deepcopy(DESCRIPTOR),
                "qc": copy.deepcopy(QC),
            },
            "confirmed_by_user": True,
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert filled.status_code == 200, filled.text
    for label in ("300 K", "400 K"):
        added = client.post(
            f"/api/experiments/{eid}/runs",
            json={"label": label, "confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )
        assert added.status_code == 201, added.text
    for question in client.get(f"/api/experiments/{eid}/pending").json()["pending"]:
        answered = client.post(
            f"/api/experiments/{eid}/runs/{question['run_id']}/answers",
            json={
                "answers": {
                    "series": copy.deepcopy(SERIES),
                    "descriptor": copy.deepcopy(DESCRIPTOR),
                    "qc": copy.deepcopy(QC),
                },
                "confirmed_by_user": True,
            },
            headers={"If-Match": _run_etag(client, eid, question["run_id"])},
        )
        assert answered.status_code == 200, answered.text

    run_a, run_b = (run.id for run in ws.load_experiment(eid).sorted_runs())

    def _write_conflicting(value: str) -> None:
        written = client.patch(
            f"/api/experiments/{eid}/runs/{run_a}",
            json={"confirmed_by_user": True, "fields": {CONFLICT_ADDRESS: value}},
            headers={"If-Match": _run_etag(client, eid, run_a)},
        )
        assert written.status_code == 200, written.text

    def _submit() -> dict:
        submitted = client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
        )
        assert submitted.status_code == 200, submitted.text
        return submitted.json()

    # TWO SUBMISSIONS, and the second one is why. A change row only exists where two
    # consecutive revisions differ in a draft FIELD value, so a fixture that submitted
    # once would leave `isaac_revision_changes` empty — and the sweep's guard over that
    # table would be unexercised while reading as though it covered all five. Measured:
    # it WAS empty before this was split in two.
    _write_conflicting(CONFLICT_VALUES[0])
    _submit()
    # The second write does two things at once: it moves the field value (so revision 2
    # records a change row) and it makes the address CONFLICTING, because the same
    # question now has two different confirmed answers.
    _write_conflicting(CONFLICT_VALUES[1])
    second = _submit()

    assert second["revision_no"] == 2
    assert second["conflict_summary"]["unresolved_field_count"] == 1, (
        "the fixture must carry a real unresolved conflict, or POST /conflicts/resolve "
        "below proves nothing — which is exactly what it used to do in the sweep this "
        "file extends"
    )
    assert len(_artifacts(eid)) == 4, _artifacts(eid)
    empty = [table for table in HISTORY_TABLES if not getattr(db, table)]
    assert empty == [], (
        f"these history tables are empty, so the sweep's guard over them would be "
        f"unexercised while reading as though it covered all five: {empty}"
    )
    return eid, run_a, run_b


# ==========================================================================
# 1. THE SWEEP
# ==========================================================================


def test_no_shipped_write_route_mutates_a_submitted_records_history(client, db):
    """EVERY mutating route addressed to a submitted record, then all five tables re-read.

    The record is submitted first, so every attempt below runs against real published
    artifacts and real history rows. After each one:

      * every file in the records directory has the sha256 it had, and none appeared or
        vanished;
      * every row already in every one of the five history tables is byte-identical.

    New rows ARE allowed — the second submission at the end appends one, deliberately,
    because a sweep that forbade appends could not exercise the write path it most needs
    to police.
    """
    eid, run_a, _run_b = _submitted_fixture(client, db)
    baseline_artifacts = _artifacts(eid)
    baseline_history = _history(db)
    note_id: dict[str, str] = {}

    def capture_note():
        response = client.post(
            f"/api/experiments/{eid}/notes",
            json={"text": "a note taken after the submission", "source": "typed_note"},
            headers={"If-Match": _etag(client, eid)},
        )
        if response.status_code == 201:
            note_id["id"] = response.json()["note"]["id"]
        return response

    attempts: list[tuple[str, object, object]] = [
        (
            "PATCH /experiments/{id}",
            ACCEPTED,
            lambda: client.patch(
                f"/api/experiments/{eid}",
                json={"title": "Cu K-edge XANES (renamed after submission)"},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            # MEASURED, AND IT IS A PROPERTY OF A RECORD A PERSON BUILT rather than of
            # this payload. Once a record has runs, every answerable key it holds is
            # run-owned, so the RECORD-level answer and correction routes have nothing
            # they may write and say so by name. The sweep this file extends reached
            # them with `edge`, which only works because the fixture sheet carries an
            # absorption-edge derivation; a created record has none, and `POST /answers`
            # answers `422 no_derivation_to_confirm` for it. The refusal is asserted
            # rather than worked around, because the refusal IS the behaviour a
            # scientist meets.
            "POST /answers",
            refused(
                409,
                "belongs_to_a_run",
                "every answerable key on a record with runs is run-owned, so the "
                "record-level route directs the caller to the run that owns it",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/answers",
                json={"confirmed_by_user": True, "answers": {"qc": copy.deepcopy(QC)}},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /edit",
            refused(
                409,
                "belongs_to_a_run",
                "the same reason as POST /answers above: the correction belongs to a run",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/edit",
                json={
                    "confirmed_by_user": True,
                    "answers": {"qc": {"status": "compromised", "note": "record level"}},
                },
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            # ACCEPTED, and that differs from the seeded sweep's `422 already_answered`
            # for a measurable reason: on a record a person built, the FIRST run adopts
            # the record's blocks rather than owning them, so `qc` is not a block this
            # run has already answered and the route writes it.
            "POST /runs/{run}/answers",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/answers",
                json={"confirmed_by_user": True, "answers": {"qc": QC}},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs/{run}/edit",
            ACCEPTED,
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
            "PATCH /runs/{run}",
            ACCEPTED,
            lambda: client.patch(
                f"/api/experiments/{eid}/runs/{run_a}",
                json={
                    "confirmed_by_user": True,
                    "fields": {"timestamps.acquired_end_utc": "2026-03-03T00:00:00Z"},
                },
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs/{run}/overrides",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/overrides",
                json={
                    "confirmed_by_user": True,
                    # A `field:` address the run INHERITS. `block:qc` is refused
                    # `422 not_overridable` — an override displaces an inherited
                    # record-level value, and `qc` is not one.
                    "address": "field:sample.material.name",
                    "payload": {
                        "value": "CuO",
                        "status": "verified",
                        "evidence": [
                            user_confirmation("What material?", "CuO", "2026-01-01T00:00:00Z")
                        ],
                    },
                },
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /runs/{run}/overrides/clear",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/overrides/clear",
                json={"confirmed_by_user": True, "address": "field:sample.material.name"},
                headers={"If-Match": _run_etag(client, eid, run_a)},
            ),
        ),
        (
            "POST /conflicts/resolve",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/conflicts/resolve",
                json={
                    "confirmed_by_user": True,
                    "run_id": run_a,
                    "address": CONFLICT_ADDRESS,
                    "outcome": "resolved",
                    "chosen_value": CONFLICT_VALUES[1],
                    "chosen_from": "candidate",
                },
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        ("POST /notes", ACCEPTED, capture_note),
        (
            "POST /notes/{id}/review",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/notes/{note_id.get('id', 'missing')}/review",
                json={"confirmed_by_user": True, "action": "keep"},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /transcript",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/transcript",
                json={"text": "the sample was copper oxide", "finalized": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /assets",
            ACCEPTED,
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
            ACCEPTED,
            lambda: client.patch(
                f"/api/experiments/{eid}/assets/sweep_asset",
                json={"confirmed_by_user": True, "sha256": "b" * 64},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /assets/{id}/remove",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/assets/sweep_asset/remove",
                json={"confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            # A POST THAT MUST WRITE NOTHING. Grouped with the two below because a
            # read-only POST is exactly the kind of route that acquires a write later.
            "POST /validate",
            READ_ONLY_POST,
            lambda: client.post(f"/api/experiments/{eid}/validate"),
        ),
        ("POST /audit", READ_ONLY_POST, lambda: client.post(f"/api/experiments/{eid}/audit")),
        ("POST /warnings", READ_ONLY_POST, lambda: client.post(f"/api/experiments/{eid}/warnings")),
        (
            "POST /runs/{run}/check",
            READ_ONLY_POST,
            lambda: client.post(f"/api/experiments/{eid}/runs/{run_a}/check"),
        ),
        (
            "POST /ingestion/csv/preview",
            READ_ONLY_POST,
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
                "the official records already exist and are immutable; no route "
                "republishes one",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/export", headers={"If-Match": _etag(client, eid)}
            ),
        ),
        (
            # THE DESTRUCTIVE OPERATION THIS BRANCH ADDED, aimed at a submitted record.
            "POST /discard",
            refused(
                409,
                "runs_exported",
                "a submitted record's runs have published official ISAAC records, and "
                "discard removes nothing that has published or declared anything",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/discard",
                json={"confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            "POST /runs/{run}/remove",
            refused(
                409,
                "run_exported",
                "removing an exported run would orphan a published official record",
            ),
            lambda: client.post(
                f"/api/experiments/{eid}/runs/{run_a}/remove",
                json={"confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
        (
            # A SECOND SUBMISSION, ACCEPTED. The conflict decision above moved the
            # content signature, so this is new content and it APPENDS rows. Every row
            # already on file must still be untouched, which is the case this whole file
            # exists to police.
            "POST /submit (again)",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
            ),
        ),
        (
            "POST /runs (add)",
            ACCEPTED,
            lambda: client.post(
                f"/api/experiments/{eid}/runs",
                json={"label": "500 K", "confirmed_by_user": True},
                headers={"If-Match": _etag(client, eid)},
            ),
        ),
    ]

    swept = [name for name, _, _ in attempts]
    assert len(swept) == len(set(swept)), f"duplicate attempt in the sweep: {swept}"

    for name, expectation, attempt in attempts:
        response = attempt()
        after = ws.load_experiment(eid)
        assert after is not None, f"{name} destroyed the record"
        assert response.status_code < 500, f"{name} raised: {response.text[:300]}"
        assert response.status_code != 404, (
            f"{name} answered 404 — this sweep is no longer exercising the route it "
            f"names, so it would pass while checking nothing"
        )

        if expectation is ACCEPTED:
            assert response.status_code < 300, (
                f"{name} is declared to reach its write path and answered "
                f"{response.status_code}: {response.text[:300]}. Either fix the payload "
                f"or declare the refusal with a reason."
            )
        elif expectation is READ_ONLY_POST:
            assert response.status_code < 300, (
                f"{name} is declared read-only-and-accepted and answered "
                f"{response.status_code}: {response.text[:300]}"
            )
        else:
            _, status, error, why = expectation
            body = response.json() if response.content else {}
            assert (response.status_code, body.get("error")) == (status, error), (
                f"{name} is declared to be refused {status} {error} because {why} — it "
                f"answered {response.status_code} {body.get('error')!r}"
            )

        assert _artifacts(eid) == baseline_artifacts, (
            f"{name} changed a published artifact of a submitted record. Official "
            f"records and their evidence sidecars are immutable and no route "
            f"republishes one."
        )
        _assert_no_row_moved(db, baseline_history, name)

    # The second submission really did append, or the append-tolerance above was never
    # exercised and this file only proved that refusals refuse.
    assert len(db.submissions) == FIXTURE_REVISIONS + 1, db.submissions
    assert len(db.revisions) == FIXTURE_REVISIONS + 1
    assert len(baseline_history["submissions"]) == FIXTURE_REVISIONS


def test_the_read_only_posts_really_are_read_only(client, db):
    """Isolated, because the sweep above cannot distinguish "wrote nothing" from
    "wrote something and wrote it back identically".

    ``POST .../validate``, ``.../audit``, ``.../warnings`` and ``.../runs/{id}/check``
    take no ``If-Match`` and are POSTs purely because they compute over a body-less
    request. Each is issued against a submitted record and the record's own version
    token is compared before and after — the sweep's per-attempt history check would not
    catch a route that advanced ``rev``.
    """
    eid, run_a, _ = _submitted_fixture(client, db)
    for path in (
        f"/api/experiments/{eid}/validate",
        f"/api/experiments/{eid}/audit",
        f"/api/experiments/{eid}/warnings",
        f"/api/experiments/{eid}/runs/{run_a}/check",
    ):
        before = ws.load_experiment(eid)
        version = (before.rev, before.generation)
        artifacts = _artifacts(eid)
        history = _history(db)
        response = client.post(path)
        assert response.status_code == 200, (path, response.text[:300])
        after = ws.load_experiment(eid)
        assert (after.rev, after.generation) == version, (
            f"{path} advanced the record's version token; it is documented as read-only"
        )
        assert _artifacts(eid) == artifacts, path
        assert _history(db) == history, path


def test_no_mcp_write_reaches_a_submitted_records_history(client, app, db):
    """THE SAME HANDLERS THROUGH THE OTHER CLIENT.

    Six MCP operations mutate. They are driven here with real validators — the ones the
    MCP read operations themselves return — so each genuinely reaches its handler rather
    than being refused while constructing the request. Whatever each one answers, no row
    already in any of the five tables may move and no artifact may change.

    ``isaac_submit`` and ``isaac_discard`` DO NOT EXIST, which is asserted rather than
    assumed: the sweep would otherwise read as MCP coverage while the two operations a
    reader most cares about were simply absent from the registry.
    """
    eid, run_a, _ = _submitted_fixture(client, db)
    artifacts = _artifacts(eid)
    history = _history(db)
    api = AsgiApiClient(app)

    mutating = {op_id for op_id, op in OPERATIONS.items() if op.mutates}
    assert mutating == {
        "create_run",
        "update_run_draft",
        "correct_record_field",
        "answer_record_question",
        "answer_run_question",
        "correct_run_field",
    }, f"the MCP mutating surface changed: {sorted(mutating)}"
    for forbidden in ("submit", "discard", "export", "resolve_conflict"):
        assert forbidden not in OPERATIONS, (
            f"MCP now publishes {forbidden!r}; this file must drive it before it ships"
        )

    # THE VALIDATORS ARE FETCHED LAZILY, one call before it is used. Capturing all six
    # up front is the mistake this test made first: each accepted write advances the
    # record, so every later call arrived with a stale validator and answered `412`.
    # Four of six then "passed" while the invariant was being asserted over refusals,
    # which is why `reached` is checked below.
    calls = (
        ("create_run", lambda: ({"experiment_id": eid}, _etag(client, eid), {"label": "MCP run"})),
        (
            "update_run_draft",
            lambda: (
                {"experiment_id": eid, "run_id": run_a},
                _run_etag(client, eid, run_a),
                {
                    "confirmed_by_user": True,
                    "fields": {"timestamps.acquired_end_utc": "2026-04-04T00:00:00Z"},
                },
            ),
        ),
        (
            "answer_run_question",
            lambda: (
                {"experiment_id": eid, "run_id": run_a},
                _run_etag(client, eid, run_a),
                {"confirmed_by_user": True, "answers": {"qc": copy.deepcopy(QC)}},
            ),
        ),
        (
            "correct_run_field",
            lambda: (
                {"experiment_id": eid, "run_id": run_a},
                _run_etag(client, eid, run_a),
                {
                    "confirmed_by_user": True,
                    "answers": {"qc": {"status": "compromised", "note": "mcp"}},
                },
            ),
        ),
        (
            # These two reach the RECORD-level handlers, which on a record with runs
            # answer `409 belongs_to_a_run` for every answerable key. Driven anyway:
            # a refusal is still a request that reached the handler, and the invariant
            # has to hold over it.
            "correct_record_field",
            lambda: (
                {"experiment_id": eid},
                _etag(client, eid),
                {
                    "confirmed_by_user": True,
                    "answers": {"qc": {"status": "compromised", "note": "mcp"}},
                },
            ),
        ),
        (
            "answer_record_question",
            lambda: (
                {"experiment_id": eid},
                _etag(client, eid),
                {"confirmed_by_user": True, "answers": {"qc": copy.deepcopy(QC)}},
            ),
        ),
    )
    reached = 0
    for operation_id, build in calls:
        path_params, validator, body = build()
        result = asyncio.run(
            api.call(operation_id, path_params=path_params, if_match=validator, json_body=body)
        )
        assert result.status < 500, (operation_id, result.status, str(result.body)[:300])
        if result.status < 300:
            reached += 1
        assert _artifacts(eid) == artifacts, f"MCP {operation_id} rewrote a published record"
        _assert_no_row_moved(db, history, f"MCP {operation_id}")
    assert reached >= 4, (
        "at least four MCP writes must genuinely land, or this test is asserting the "
        "invariant over a set of refusals"
    )
    assert len(db.submissions) == len(history["submissions"]), (
        "no MCP operation may record a submission"
    )


def test_the_sweep_covers_every_mutating_route_this_api_publishes(app):
    """THE RATCHET, DERIVED FROM THE PUBLISHED OPENAPI DOCUMENT rather than hardcoded.

    The sweep it guards issues one attempt per mutating operation addressed to an
    experiment. An operation added tomorrow is either swept or listed below with a
    written reason; nothing else passes. This replaces the ``len(attempts) == 19`` style
    of ratchet, which cannot tell a new route from a renamed one.

    THE OPENAPI DOCUMENT, NOT ``app.routes``. The first version of this test read
    ``app.routes`` and found ZERO mutating routes — the router is included through an
    ``_IncludedRouter`` whose children are not walked by a naive scan, so the assertion
    passed while measuring nothing. The published document is also the thing a client
    author reads, which makes it the right authority for "what this API offers".
    """
    import inspect

    source = inspect.getsource(test_no_shipped_write_route_mutates_a_submitted_records_history)

    #: Mutating operations NOT addressed to one experiment, each with the reason. None
    #: of them can reach a submitted record's history because none of them names one.
    not_addressed_to_a_record = {
        ("POST", "/api/experiments"): "creates a record; there is none to protect yet",
        ("POST", "/api/uploads"): "refuses every upload in this build; names no record",
        ("POST", "/api/demo/reset"): (
            "the worked-example reset; canonical ids only, and refused for any record a "
            "scientist created — covered by test_reset_safety.py"
        ),
        ("POST", "/api/demo/run"): "seeds the worked example; names no scientist record",
        ("POST", "/api/tutorial/sessions"): "opens a worked-example session",
        ("DELETE", "/api/tutorial/sessions/{session_id}"): "closes one; session scope only",
        ("POST", "/api/assistant/ask"): "the provider seam; 501 in every deployment",
        ("POST", "/api/assistant/memory/query"): "read-only memory query",
        ("POST", "/api/experiments/{experiment_id}/assistant/query"): (
            "read-only deterministic Q&A over one record; no If-Match, no write"
        ),
        ("POST", "/api/transcription"): "the provider seam; 501 in every deployment",
        ("POST", "/api/validate/record"): "validates a posted document; names no record",
    }

    spec = app.openapi()
    published = {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations
        if method.lower() in {"post", "patch", "put", "delete"}
    }
    assert len(published) > 20, (
        f"only {len(published)} mutating operations were found; this ratchet is not "
        "reading the document it thinks it is"
    )

    #: How each swept attempt names itself, so the scan matches on intent rather than on
    #: a path template. Keyed by the published (method, path).
    swept_names = {
        ("PATCH", "/api/experiments/{experiment_id}"): "PATCH /experiments/{id}",
        ("POST", "/api/experiments/{experiment_id}/answers"): "POST /answers",
        ("POST", "/api/experiments/{experiment_id}/edit"): "POST /edit",
        ("POST", "/api/experiments/{experiment_id}/runs"): "POST /runs (add)",
        ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/answers"): (
            "POST /runs/{run}/answers"
        ),
        ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/edit"): "POST /runs/{run}/edit",
        ("PATCH", "/api/experiments/{experiment_id}/runs/{run_id}"): "PATCH /runs/{run}",
        ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/overrides"): (
            "POST /runs/{run}/overrides"
        ),
        ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/overrides/clear"): (
            "POST /runs/{run}/overrides/clear"
        ),
        ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/remove"): (
            "POST /runs/{run}/remove"
        ),
        ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/check"): (
            "POST /runs/{run}/check"
        ),
        ("POST", "/api/experiments/{experiment_id}/conflicts/resolve"): "POST /conflicts/resolve",
        ("POST", "/api/experiments/{experiment_id}/notes"): "POST /notes",
        ("POST", "/api/experiments/{experiment_id}/notes/{note_id}/review"): (
            "POST /notes/{id}/review"
        ),
        ("POST", "/api/experiments/{experiment_id}/transcript"): "POST /transcript",
        ("POST", "/api/experiments/{experiment_id}/assets"): "POST /assets",
        ("PATCH", "/api/experiments/{experiment_id}/assets/{asset_id}"): "PATCH /assets/{id}",
        ("POST", "/api/experiments/{experiment_id}/assets/{asset_id}/remove"): (
            "POST /assets/{id}/remove"
        ),
        ("POST", "/api/experiments/{experiment_id}/validate"): "POST /validate",
        ("POST", "/api/experiments/{experiment_id}/audit"): "POST /audit",
        ("POST", "/api/experiments/{experiment_id}/warnings"): "POST /warnings",
        ("POST", "/api/experiments/{experiment_id}/ingestion/csv/preview"): (
            "POST /ingestion/csv/preview"
        ),
        ("POST", "/api/experiments/{experiment_id}/export"): "POST /export",
        ("POST", "/api/experiments/{experiment_id}/discard"): "POST /discard",
        ("POST", "/api/experiments/{experiment_id}/submit"): "POST /submit (again)",
    }

    unaccounted = sorted(
        entry
        for entry in published
        if entry not in not_addressed_to_a_record and entry not in swept_names
    )
    assert unaccounted == [], (
        "these mutating operations are addressed to an experiment and are neither swept "
        "by test_no_shipped_write_route_mutates_a_submitted_records_history nor listed "
        f"in not_addressed_to_a_record with a reason: {unaccounted}"
    )
    missing = sorted(
        name for entry, name in swept_names.items() if f'"{name}"' not in source
    )
    assert missing == [], (
        f"the sweep no longer issues an attempt named: {missing}. The map above and the "
        "sweep must be edited together."
    )
    stale = sorted(
        entry
        for entry in list(not_addressed_to_a_record) + list(swept_names)
        if entry not in published
    )
    assert stale == [], f"this test names operations the API does not publish: {stale}"


# ==========================================================================
# 2. WHAT THE HISTORY SURFACES SAY — AND WHO THEY SAY DID IT
# ==========================================================================


def test_the_history_never_invents_an_actor_it_cannot_vouch_for(client, db):
    """``attribution.uploaded_by`` requires ``verified_edge_assertion`` and nothing mints one.

    So no surface may name a person as an authenticated submitter. What the row DOES
    carry is the fixture basis, and the read surface must pass it through rather than
    flattening it to "attributed" — a reader has to be able to see what the attribution
    is worth. Both halves are asserted, in both the listing and the detail.
    """
    eid, _run_a, _ = _submitted_fixture(client, db)

    listing = client.get(f"/api/experiments/{eid}/revisions")
    assert listing.status_code == 200, listing.text
    row = listing.json()["revisions"][0]
    assert row["actor"] == {
        "subject": ACTOR,
        "trust_basis": "test_fixture",
        "attributed": True,
    }, row["actor"]
    assert row["submission"]["actor"]["trust_basis"] == "test_fixture"

    detail = client.get(f"/api/experiments/{eid}/revisions/1")
    assert detail.status_code == 200, detail.text
    assert detail.json()["revision"]["actor"]["trust_basis"] == "test_fixture"

    # THE HALF THAT MATTERS MOST: no surface upgrades the basis, and no published
    # official record claims an authenticated uploader.
    rendered = json.dumps(listing.json()) + json.dumps(detail.json())
    assert "verified_edge_assertion" not in rendered, rendered[:400]
    for unit in ws.load_experiment(eid).export_units():
        record = json.loads(unit.record_path().read_text(encoding="utf-8"))
        assert "uploaded_by" not in (record.get("attribution") or {}), record.get("attribution")


def test_an_unattributed_row_names_nobody_rather_than_inventing_a_placeholder(client, db):
    """The other direction. A row with no subject must read as nobody, not as "system"."""
    eid, _run_a, _ = _submitted_fixture(client, db)
    db.revisions.append(
        {
            "revision_id": "01ADVERSARIALUNATTRIBUTED01",
            "experiment_id": eid,
            "revision_no": FIXTURE_REVISIONS + 1,
            "experiment_rev": ws.load_experiment(eid).rev,
            "generation": ws.load_experiment(eid).generation,
            "state": "{}",
            "content_signature": "0" * 64,
            "reason": sstore.REASON_SUBMISSION,
            "subject": None,
            "trust_basis": "unattributed",
            "created_utc": "2026-01-01T00:00:00+00:00",
        }
    )
    listing = client.get(f"/api/experiments/{eid}/revisions").json()
    top = listing["revisions"][0]
    assert top["revision_no"] == FIXTURE_REVISIONS + 1
    assert top["actor"] == {"subject": None, "trust_basis": "unattributed", "attributed": False}
    for invented in ("system", "unknown", "anonymous", "isaac", "n/a"):
        assert invented not in json.dumps(top["actor"]).lower(), top["actor"]


def test_the_diff_reports_a_field_change_and_says_what_it_did_not_look_at(client, db):
    """THE REPRESENTATION CHECK, on both the arm that shows and the arm that cannot.

    * A run-level FIELD change appears, addressed to its unit, with both values.
    * A BLOCK change — a QC verdict, which is an answer a scientist gave — produces NO
      change row, because the recorded scope is ``draft_field_values_only``. That is a
      real narrowing and it is DISCLOSED rather than hidden: ``changes_scope`` names it
      and ``content_signature_matches: false`` is the stronger, authoritative statement
      the route's own description points a reader to. Both are asserted, because an
      empty ``changes`` list beside a matching signature would be the defect and an
      empty list beside a differing signature is the documented, honest state.
    """
    eid, run_a, _ = _submitted_fixture(client, db)

    # (a) a FIELD change, which the surface does represent.
    moved = client.patch(
        f"/api/experiments/{eid}/runs/{run_a}",
        json={
            "confirmed_by_user": True,
            "fields": {"timestamps.acquired_end_utc": "2026-05-05T00:00:00Z"},
        },
        headers={"If-Match": _run_etag(client, eid, run_a)},
    )
    assert moved.status_code == 200, moved.text
    diff = client.get(f"/api/experiments/{eid}/revisions/{FIXTURE_REVISIONS}/diff").json()
    assert diff["comparable"] is True
    assert diff["content_signature_matches"] is False
    assert diff["changes_scope"] == "draft_field_values_only"
    entry = [c for c in diff["changes"] if c["address"] == "timestamps.acquired_end_utc"]
    assert len(entry) == 1, diff["changes"]
    assert entry[0]["unit_id"] == run_a
    assert entry[0]["change_kind"] == "added"
    assert entry[0]["current_value"] == "2026-05-05T00:00:00Z"

    # (b) a BLOCK change, which it does not — and says so by the signature, not by
    # silence. A second record is used so the field change above cannot mask it.
    other, other_run, _ = _submitted_fixture(client, db)
    verdict = client.post(
        f"/api/experiments/{other}/runs/{other_run}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "compromised", "note": "reconsidered"}},
        },
        headers={"If-Match": _run_etag(client, other, other_run)},
    )
    assert verdict.status_code == 200, verdict.text
    block_diff = client.get(f"/api/experiments/{other}/revisions/{FIXTURE_REVISIONS}/diff").json()
    assert block_diff["comparable"] is True
    assert block_diff["changes"] == [], (
        "if a block change starts appearing in `changes` that is a widening of the "
        "recorded scope and this test should be updated deliberately"
    )
    assert block_diff["content_signature_matches"] is False, (
        "THE HONESTY REQUIREMENT: the surface may decline to compare blocks, but it may "
        "NOT let an empty `changes` list sit beside a signature that says nothing moved"
    )
    assert block_diff["changes_scope"] == "draft_field_values_only"


def test_a_run_addition_shows_as_a_unit_addition_and_a_removal_cannot_happen(client, db):
    """Both halves of unit membership, and the second one is a structural result.

    A run added after a submission appears in ``units.added``. A run that a submission
    NAMED can never be removed — it is materialised by construction (a unit only reaches
    a revision if its record was published) and ``post_run_remove`` refuses a
    materialised run. So ``units.removed`` is unreachable through any route for a
    submitted unit, which is a stronger statement than "the sweep did not manage it".
    """
    eid, run_a, run_b = _submitted_fixture(client, db)
    added = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "500 K", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert added.status_code == 201, added.text
    new_run = added.json()["run"]["id"]

    diff = client.get(f"/api/experiments/{eid}/revisions/{FIXTURE_REVISIONS}/diff").json()
    assert diff["units"]["added"] == [new_run], diff["units"]
    assert diff["units"]["removed"] == []
    assert sorted(diff["units"]["unchanged"]) == sorted([run_a, run_b])

    for submitted_run in (run_a, run_b):
        refused = client.post(
            f"/api/experiments/{eid}/runs/{submitted_run}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"] == "run_exported"
    assert client.get(f"/api/experiments/{eid}/revisions/{FIXTURE_REVISIONS}/diff").json()["units"]["removed"] == []


def test_a_conflict_decision_reaches_the_submission_that_follows_it(client, db):
    """Provenance the row carries about itself: the decision is disclosed, never the value."""
    eid, run_a, _ = _submitted_fixture(client, db)
    decided = client.post(
        f"/api/experiments/{eid}/conflicts/resolve",
        json={
            "confirmed_by_user": True,
            "run_id": run_a,
            "address": CONFLICT_ADDRESS,
            "outcome": "resolved",
            "chosen_value": CONFLICT_VALUES[1],
            "chosen_from": "candidate",
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert decided.status_code == 200, decided.text

    second = client.post(
        f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
    )
    assert second.status_code == 200, second.text
    summary = second.json()["conflict_summary"]
    assert summary["resolved_field_count"] == 1
    assert summary["unresolved_field_count"] == 0
    assert summary["resolutions_supplied"] is True

    listing = client.get(f"/api/experiments/{eid}/revisions").json()
    stored = listing["revisions"][0]["submission"]["conflict_summary"]
    assert stored["resolved_field_count"] == 1
    assert CONFLICT_ADDRESS in json.dumps(stored), stored
    # THE DISCLOSURE CARRIES ADDRESSES, NEVER VALUES.
    rendered = json.dumps(stored)
    for value in CONFLICT_VALUES:
        assert value not in rendered, rendered


def test_the_submission_event_itself_is_on_the_listing(client, db):
    """The event, its time, its unit count, and the fact it used no idempotency key."""
    eid, run_a, run_b = _submitted_fixture(client, db)
    listing = client.get(f"/api/experiments/{eid}/revisions").json()
    assert listing["total"] == FIXTURE_REVISIONS
    submission = listing["revisions"][0]["submission"]
    assert submission is not None
    assert submission["unit_count"] == 2
    assert submission["idempotency_key_used"] is False
    assert submission["submitted_utc"], submission
    assert listing["lifecycle"]["state"] == "submitted"

    detail = client.get(f"/api/experiments/{eid}/revisions/1").json()["revision"]
    assert {row["record_id"] for row in detail["submission_runs"]} == {run_a, run_b}
    assert {row["run_id"] for row in detail["run_revisions"]} == {run_a, run_b}
    # No stored snapshot ever leaves this surface.
    assert "state" not in detail, detail.keys()


def test_the_history_read_issues_no_statement_that_writes(client, db):
    """The append-only claim at the level this file CAN make it: statement inventory.

    Every statement the read surfaces issue against the history tables is inspected
    after driving all three of them. This is the same property
    ``test_revision_history.py`` asserts over the module's declared constants; here it is
    asserted over the statements a REQUEST actually produced, which is the half a
    constant scan cannot see.
    """
    eid, _run_a, _ = _submitted_fixture(client, db)
    marker = len(db.statements)
    for path in (
        f"/api/experiments/{eid}/revisions",
        f"/api/experiments/{eid}/revisions/1",
        f"/api/experiments/{eid}/revisions/{FIXTURE_REVISIONS}/diff",
    ):
        assert client.get(path).status_code == 200, path

    issued = [sql for sql, _params in db.statements[marker:]]
    assert issued, "the read surfaces issued no statement at all"
    for sql in issued:
        upper = " ".join(sql.split()).upper()
        assert "UPDATE " not in upper, sql
        assert "DELETE " not in upper, sql
        assert "INSERT " not in upper, sql


def test_this_file_does_not_claim_the_database_forbids_what_it_measured(client, db):
    """A GUARD ON THIS FILE'S OWN HONESTY, and it is not decoration.

    The distinction between *no shipped route mutates history* and *history cannot be
    mutated* is the one claim a future edit is most likely to blur, because the
    assertions above read like the stronger sentence. ``submission_store``'s own
    docstring names the two mechanisms that would make it a database guarantee and says
    both are unavailable. If either becomes available, this file's headline claim can be
    strengthened — and this test is what will notice.
    """
    import inspect

    docstring = inspect.getdoc(sstore) or ""
    assert "not** a database guarantee" in docstring or "not a database guarantee" in docstring, (
        "submission_store no longer disclaims the database-level guarantee; if a trigger "
        "or a REVOKE has been added, this file's module docstring must be restated"
    )
    assert "REVOKE UPDATE, DELETE`` is refused" in docstring or "REVOKE" in docstring

    module_doc = __doc__ or ""
    assert "no shipped route mutates" in module_doc
    assert "does NOT" in module_doc and "cannot be mutated" in module_doc
