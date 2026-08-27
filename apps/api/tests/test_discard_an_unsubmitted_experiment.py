"""``POST /api/experiments/{id}/discard`` — taking back a record nobody published.

WHAT WAS MISSING
================
``POST /api/experiments`` could CREATE a record and nothing could take one away.
``routes.py``'s reset description says so in as many words — *"there is
deliberately no general per-experiment delete operation"* — so a scientist who
created a record by mistake owned it forever, in the workspace and, on a
deployment with a database, in that database.

THE AUTHORIZATION, QUOTED, BECAUSE EVERYTHING BELOW IS SHAPED BY IT
===================================================================
The project owner authorized, narrowly: **explicit Discard semantics for
unsubmitted Draft/capture state only.** It explicitly does NOT permit a generic
destructive DELETE primitive, and it explicitly forbids using Discard to erase an
official submitted ISAAC record, an immutable submitted revision, revision
history, submission history, a published evidence sidecar, historical conflict
evidence, or audit history.

That sentence, not this operation's convenience, is why the refusals are wide and
why there is no HTTP ``DELETE`` verb anywhere in it.

THE ONE THING THIS SUITE EXISTS TO PROTECT
==========================================
**No path through this operation can destroy anything anyone published or
declared.** Four separate things are at stake and they live in four places:

  * the OFFICIAL RECORD and its evidence sidecar — files under the experiment's
    ``records/`` directory, written by an export and never rewritten;
  * the REVISION SNAPSHOT — ``isaac_experiment_revisions`` /
    ``isaac_run_revisions``, append-only;
  * the SUBMISSION — ``isaac_submissions`` / ``isaac_submission_runs``, the
    attributable declaration a person made;
  * and the production-derived ``records`` table, which this application must
    never name in any statement at all.

Three independent mechanisms keep them, and all three are asserted here rather
than assumed:

  1. **The route refuses first.** Five domain refusals, each writing nothing.
  2. **The statement set cannot express the damage.** ``experiment_repository``
     declares exactly three DELETEs and they name ``isaac_run_projection``,
     ``isaac_runs`` and ``isaac_experiments``. No statement in this application
     names a history table after DELETE or UPDATE — the same property
     ``test_submission_store.test_no_submission_statement_updates_or_deletes_history``
     asserts package-wide, stated again here over THIS module because this module
     is where a future delete would be written.
  3. **The database refuses as a backstop.** No migration here writes an
     ``ON DELETE`` clause, so ``NO ACTION`` applies to every foreign key into
     ``isaac_experiments``; a record that still carries history is refused by the
     server at the last of the three statements and the whole transaction rolls
     back.

WHAT THIS FILE PROVES AND WHAT IT CANNOT
========================================
The connection doubles exercise the real transaction machinery — explicit
transaction, statement policy, ``PGDATABASE`` gate, rollback, close — and only the
SERVER is fake. So this proves WHICH STATEMENTS ARE ISSUED, WITH WHICH PARAMETERS,
IN WHICH ORDER, and what a caller sees. It does NOT prove the SQL is valid
PostgreSQL, nor that the real foreign keys refuse what the fake refuses. That half
is ``.github/workflows/ci.yml``'s ``postgres-migration`` job against a real
``postgres:18``, and where the two could disagree CI is the authority.

Every fixture is built from the committed synthetic seed drafts. Nothing here
reads real data and no test in this file writes a scientific value it did not read
out of the committed seed.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws

from conftest import tutorial_client
from submission_fake import FakeSubmissionConnection, fake_env, fake_reader, fake_store
from test_experiment_repository import (
    FakeConnection,
    ForeignKeyViolation,
    _connector,
    _env,
)

EXPERIMENT_ID = "01DISCARDFIXTURE0000000001"
OTHER_ID = "01DISCARDFIXTURE0000000002"
ACTOR = "ada.lovelace"


# =============================================================================
# fixtures
# =============================================================================


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A private ORDINARY-scope workspace with no database configured.

    Ordinary rather than worked-example scope: that is the scope a scientist's own
    record lives in, and the only scope from which a submission or a durable write
    is reachable at all. The worked-example half has its own section at the end.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def wired(monkeypatch, db):
    """Point BOTH the submit store and the history reader at one connection double.

    The SAME connection, deliberately: a discard precheck reading from a store of
    its own could not see what a submission actually wrote, which is precisely the
    thing this operation must not get wrong.
    """
    store = fake_store(db)
    reader = fake_reader(db)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    monkeypatch.setattr(rhist, "reader", lambda env=None: reader)
    return store


@pytest.fixture()
def armed(workspace, monkeypatch):
    """A deployment that CAN attribute a submission: the fixture verifier."""
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _client():
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _make(experiment_id: str = EXPERIMENT_ID, *, runs: tuple[str, ...] = ()):
    """An export-ready ordinary-scope experiment carrying ``runs``.

    The run drafts are a deep copy of the experiment's own committed seed draft, so
    every unit really is exportable — which is what makes an export and a submission
    reachable in the refusal tests. Nothing here composes a scientific value.
    """
    exp = ws.create_experiment(
        "Discard fixture",
        {"kind": "synthetic"},
        copy.deepcopy(ws._full_draft()),
        id=experiment_id,
    )
    run_draft = copy.deepcopy(exp.draft)
    for label in runs:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


def _create_over_http(client, title: str = "A record made by mistake") -> str:
    """A record created through the PRODUCT'S OWN path, not composed by a fixture.

    The gap this operation closes is about a record a scientist CREATED, so the
    first case has to be one the create route made — a fixture-built record could
    differ from it in exactly the way that matters.
    """
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _etag(client, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _discard(
    client,
    experiment_id: str = EXPERIMENT_ID,
    *,
    if_match=...,
    body=...,
    headers=None,
):
    """The discard request. ``if_match=None`` omits the header entirely."""
    sent = dict(headers or {})
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    if tag is not None:
        sent["If-Match"] = tag
    payload = {"confirmed_by_user": True} if body is ... else body
    return client.post(
        f"/api/experiments/{experiment_id}/discard", json=payload, headers=sent
    )


def _export(client, experiment_id: str = EXPERIMENT_ID):
    return client.post(
        f"/api/experiments/{experiment_id}/export",
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _submit(client, experiment_id: str = EXPERIMENT_ID):
    return client.post(
        f"/api/experiments/{experiment_id}/submit",
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _listed_ids(client) -> list[str]:
    response = client.get("/api/experiments")
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()["experiments"]]


def _artifacts(exp) -> dict:
    """Every file in this experiment's records dir, by name, as BYTES."""
    records_dir = exp.records_dir
    if not records_dir.is_dir():
        return {}
    return {p.name: p.read_bytes() for p in records_dir.iterdir() if p.is_file()}


def _state_bytes(experiment_id: str) -> bytes:
    return (ws.scope_root(None) / experiment_id / "experiment.json").read_bytes()


# =============================================================================
# 1. the ordinary discard — the gap this closes
# =============================================================================


def test_a_record_created_by_mistake_can_be_discarded_and_is_GONE(workspace):
    """The whole point, over the product's own create path.

    Created through `POST /api/experiments`, discarded, and then absent from the
    listing, from the by-id read, and from the filesystem — three independent
    readings, because a record that merely stopped being LISTED would still be
    there.
    """
    client = _client()
    experiment_id = _create_over_http(client)
    assert experiment_id in _listed_ids(client)

    response = _discard(client, experiment_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["discarded_experiment_id"] == experiment_id
    assert body["discarded_title"] == "A record made by mistake"
    assert body["discarded_run_count"] == 0
    assert body["durable_rows_removed"] == 0  # no database on this deployment
    assert experiment_id not in _listed_ids(client)
    assert client.get(f"/api/experiments/{experiment_id}").status_code == 404
    assert not (ws.scope_root(None) / experiment_id).exists()
    assert ws.load_experiment(experiment_id) is None


def test_a_record_with_runs_and_answers_but_no_export_can_be_discarded(workspace):
    """Answered work is still DRAFT work, and the authorization covers it.

    A record with runs, run-level content and an answer log has never published or
    declared anything, so it is discardable — and every one of its runs goes with
    it rather than being left behind as an unreachable fragment.
    """
    exp = _make(runs=("run A", "run B"))
    assert len(exp.runs) == 2
    client = _client()

    response = _discard(client)

    assert response.status_code == 200, response.text
    assert response.json()["discarded_run_count"] == 2
    assert ws.load_experiment(EXPERIMENT_ID) is None
    assert not (ws.scope_root(None) / EXPERIMENT_ID).exists()


def test_no_ETag_is_returned_because_the_record_no_longer_exists(workspace):
    """A validator for a resource that is gone would be a validator for nothing."""
    client = _client()
    experiment_id = _create_over_http(client)
    response = _discard(client, experiment_id)
    assert response.status_code == 200, response.text
    assert "ETag" not in response.headers


# =============================================================================
# 2. the refusals — every one of them writes NOTHING
# =============================================================================


def test_an_EXPORTED_RUN_refuses_the_discard_and_NOTHING_was_written(workspace):
    """THE CASE THIS OPERATION IS JUDGED ON.

    An export writes an official ISAAC record and its evidence sidecar, and nothing
    in this application ever rewrites one. So a discard that removed the experiment
    directory would delete a published record — the single act the authorization
    names first among the things Discard may not do.

    Asserted by RE-READING everything afterwards, byte for byte, rather than by
    trusting the status code: the record document, the run set, and every artifact
    file.
    """
    _make(runs=("run A", "run B"))
    client = _client()
    assert _export(client).status_code == 200

    exported = ws.load_experiment(EXPERIMENT_ID)
    artifacts_before = _artifacts(exported)
    assert len(artifacts_before) == 4, artifacts_before  # two records, two sidecars
    state_before = _state_bytes(EXPERIMENT_ID)

    response = _discard(client)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "runs_exported"
    assert sorted(body["run_ids"]) == sorted(run.id for run in exported.sorted_runs())
    assert body["record_stems"]
    # NOTHING WAS WRITTEN — the record, its runs, and every published file.
    after = ws.load_experiment(EXPERIMENT_ID)
    assert after is not None
    assert [run.id for run in after.sorted_runs()] == [
        run.id for run in exported.sorted_runs()
    ]
    assert _artifacts(after) == artifacts_before
    assert _state_bytes(EXPERIMENT_ID) == state_before


def test_a_record_exported_UNDER_ITS_OWN_IDENTITY_refuses_the_discard(workspace):
    """The run-free export, which is a different code path from the fan-out.

    A record with no runs exports as ONE unit under its own id and carries a
    `record_id` of its own; the run scan would find nothing to refuse on.
    """
    _make()  # no runs
    client = _client()
    assert _export(client).status_code == 200
    exported = ws.load_experiment(EXPERIMENT_ID)
    assert exported.record_id is not None
    artifacts_before = _artifacts(exported)

    response = _discard(client)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "experiment_exported"
    assert body["record_id"] == exported.record_id
    assert ws.load_experiment(EXPERIMENT_ID) is not None
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == artifacts_before


def test_a_PUBLISHED_PAIR_ON_DISK_refuses_even_when_no_state_claims_it(workspace):
    """THE DISK, NOT ONLY THE STATE — the same lesson `_run_published_stem` records.

    An export writes both files BEFORE it persists the state, so a refused state
    save leaves a published pair on disk that no `record_id` names. It is also what
    a run that was itself removed leaves behind. A discard decided from state alone
    would delete exactly that pair, and the response would say nothing about it.

    Modelled by writing the pair directly, which is the shape both faults produce.
    """
    exp = _make()
    orphan = "01ORPHANEDRECORDSTEM000001"
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    (exp.records_dir / f"{orphan}.json").write_text('{"record_id": "x"}')
    (exp.records_dir / f"{orphan}.evidence.json").write_text("{}")
    before = _artifacts(ws.load_experiment(EXPERIMENT_ID))
    client = _client()

    response = _discard(client)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "published_artifacts_present"
    assert body["record_stems"] == [orphan]
    assert ws.load_experiment(EXPERIMENT_ID) is not None
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == before


def test_EITHER_HALF_of_a_published_pair_alone_is_enough_to_refuse(workspace):
    """A record without its sidecar, and a sidecar without its record.

    Either alone is a published artifact this application never wrote a deletion
    for, and refusing only when BOTH are present would make the guard depend on a
    fault having been symmetric.
    """
    for filename in ("01HALFPAIRSTEM000000000001.json", "01HALFPAIRSTEM000000000002.evidence.json"):
        exp = _make()
        exp.records_dir.mkdir(parents=True, exist_ok=True)
        (exp.records_dir / filename).write_text("{}")
        client = _client()
        response = _discard(client)
        assert response.status_code == 409, (filename, response.text)
        assert response.json()["error"] == "published_artifacts_present"
        assert ws.load_experiment(EXPERIMENT_ID) is not None
        # Clean up for the next iteration of this loop only.
        ws._remove_experiment_dir(exp.dir, session_id=None)


def test_a_SUBMITTED_record_refuses_and_its_history_rows_are_UNTOUCHED(
    armed, wired, db
):
    """THE SECOND CASE THIS OPERATION IS JUDGED ON, asserted positively.

    A submission is an attributable declaration a person made, and its revision and
    submission rows are append-only. Not "the discard returned 409" — the whole row
    sets are compared before and after, so a rewritten `state` document or a
    dropped row fails here rather than being absorbed by a count.

    It reaches the 409 through the SUBMITTED refusal specifically, which is the one
    the history precheck produces. (An exported run would also refuse it, and would
    do so first; this fixture has no runs, so the submission is the only reason
    left and the assertion is about the reason as much as the status.)
    """
    _make()
    client = _client()
    assert _submit(client).status_code == 200
    assert db.revisions and db.submissions

    revisions_before = copy.deepcopy(db.revisions)
    run_revisions_before = copy.deepcopy(db.run_revisions)
    submissions_before = copy.deepcopy(db.submissions)
    submission_runs_before = copy.deepcopy(db.submission_runs)
    artifacts_before = _artifacts(ws.load_experiment(EXPERIMENT_ID))

    response = _discard(client)

    assert response.status_code == 409, response.text
    body = response.json()
    # A submission MATERIALISES every unit, so the record is also exported by now
    # and either refusal is truthful. The one that must not happen is a 200.
    assert body["error"] in {"submitted", "experiment_exported", "runs_exported"}

    assert db.revisions == revisions_before
    assert db.run_revisions == run_revisions_before
    assert db.submissions == submissions_before
    assert db.submission_runs == submission_runs_before
    assert ws.load_experiment(EXPERIMENT_ID) is not None
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == artifacts_before


def test_the_SUBMITTED_refusal_is_reached_by_the_history_read_on_its_own(
    armed, wired, db
):
    """The history precheck, ISOLATED from the export guard that shadows it.

    In the real world every submitted record is also exported, so the `submitted`
    refusal is normally unreachable — which would leave the history read untested
    and would let it be deleted without a single failure. Here the published
    artifacts and the `record_id` are cleared after the submission, leaving ONLY
    the history rows, so the refusal that fires is the one this test is about.
    """
    _make()
    client = _client()
    assert _submit(client).status_code == 200
    assert len(db.revisions) == 1 and len(db.submissions) == 1

    # Strip everything the LOCAL guards would refuse on, leaving only the rows.
    exp = ws.load_experiment(EXPERIMENT_ID)
    for path in list(exp.records_dir.iterdir()):
        path.unlink()
    exp.record_id = None
    exp.save()

    response = _discard(client)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "submitted"
    assert body["revision_count"] == 1
    assert body["submission_count"] == 1
    assert ws.load_experiment(EXPERIMENT_ID) is not None
    assert db.revisions and db.submissions


def test_a_CANONICAL_worked_example_is_refused(workspace):
    """The built-in examples are fixed teaching material, not anyone's record.

    Asserted in the ORDINARY scope, where an older build could have left one — the
    same historical accident `refuse_if_not_persistable` names — because that is
    where a discard could otherwise reach one.
    """
    canonical = sorted(ws.CANONICAL_IDS)[0]
    ws.create_experiment(
        "A canonical id in the ordinary scope",
        {"kind": "synthetic"},
        copy.deepcopy(ws._raw_draft()),
        id=canonical,
    )
    client = _client()

    response = _discard(client, canonical)

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "canonical_example_record"
    assert ws.load_experiment(canonical) is not None


def test_the_workspace_helper_refuses_a_canonical_id_even_called_directly(workspace):
    """DEFENCE IN DEPTH, and it is not redundant with the route's check.

    The route's refusal is the one a client sees; this is the one that holds if a
    future caller reaches the store without going through the route. It raises
    rather than returning, because a caller that ignored a return value would
    proceed to delete.
    """
    canonical = sorted(ws.CANONICAL_IDS)[0]
    exp = ws.create_experiment(
        "A canonical id in the ordinary scope",
        {"kind": "synthetic"},
        copy.deepcopy(ws._raw_draft()),
        id=canonical,
    )
    with pytest.raises(ValueError, match="canonical"):
        ws.discard_experiment(exp)
    assert ws.load_experiment(canonical) is not None


# =============================================================================
# 3. confirmation and the precondition — the refusal ORDER is the contract
# =============================================================================


def test_confirmation_is_required_and_an_unconfirmed_request_discards_nothing(
    workspace,
):
    _make()
    before = _state_bytes(EXPERIMENT_ID)
    client = _client()

    for payload in ({}, {"confirmed_by_user": False}, {"confirmed_by_user": "yes"}, []):
        response = _discard(client, body=payload)
        assert response.status_code == 422, (payload, response.text)
        assert ws.load_experiment(EXPERIMENT_ID) is not None
        assert _state_bytes(EXPERIMENT_ID) == before


def test_omitting_if_match_is_428_and_discards_nothing(workspace):
    _make()
    client = _client()
    response = _discard(client, if_match=None)
    assert response.status_code == 428, response.text
    assert response.json()["error"] == "precondition_required"
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_a_malformed_if_match_is_400_and_discards_nothing(workspace):
    _make()
    client = _client()
    for header in ('W/"weak"', "not-a-validator", ","):
        response = _discard(client, if_match=header)
        assert response.status_code == 400, (header, response.text)
        assert response.json()["error"] == "malformed_if_match"
        assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_a_stale_if_match_is_412_and_discards_nothing(workspace):
    """The record moved after the token was read, so the discard is refused.

    A discard is irreversible, so this is the precondition doing the one job that
    matters most here: the client is holding a version of a record that no longer
    exists, and destroying the version that does would destroy work it never saw.
    """
    _make()
    client = _client()
    stale = _etag(client)
    renamed = client.patch(
        f"/api/experiments/{EXPERIMENT_ID}",
        json={"title": "Renamed after the token was read"},
        headers={"If-Match": stale},
    )
    assert renamed.status_code == 200, renamed.text

    response = _discard(client, if_match=stale)

    assert response.status_code == 412, response.text
    assert response.json()["error"] == "stale_write"
    after = ws.load_experiment(EXPERIMENT_ID)
    assert after is not None
    assert after.title == "Renamed after the token was read"


def test_the_domain_refusal_PRECEDES_the_precondition_so_it_is_never_a_412(workspace):
    """THE ORDER OF THE FIVE REFUSALS IS THE CONTRACT, and this is the half of it
    a client can observe.

    An exported record answered with a stale token must say `runs_exported`, not
    `stale_write`. A 412 tells the client to re-read and retry, and for a record
    that has published something the retry can never succeed — the same shape of
    defect the reset path recorded when a permanent condition wore a recoverable
    status code.
    """
    _make(runs=("run A",))
    client = _client()
    stale = _etag(client)
    assert _export(client).status_code == 200

    response = _discard(client, if_match=stale)

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "runs_exported"


def test_the_confirmation_refusal_precedes_the_domain_refusal(workspace):
    """Unconfirmed FIRST, so an unconfirmed request against an exported record is
    422 rather than 409 — matching `post_run_remove`'s stated order exactly:
    exists -> confirmed -> domain refusal -> precondition -> write."""
    _make(runs=("run A",))
    client = _client()
    assert _export(client).status_code == 200
    response = _discard(client, body={})
    assert response.status_code == 422, response.text


# =============================================================================
# 4. idempotency, isolation, and the id that never existed
# =============================================================================


def test_REPEATING_the_discard_is_a_404_and_never_a_500(workspace):
    """404, NOT a second 200, matching `post_run_remove`'s precedent.

    A retry whose first attempt succeeded is the case that matters: the record is
    gone, and telling the truth about that is better than a 200 claiming a record
    "was discarded" for an id that may never have existed here.
    """
    client = _client()
    experiment_id = _create_over_http(client)
    tag = _etag(client, experiment_id)
    assert _discard(client, experiment_id, if_match=tag).status_code == 200

    again = _discard(client, experiment_id, if_match=tag)

    assert again.status_code == 404, again.text
    assert again.json()["error"] == "experiment_not_found"


def test_discarding_an_id_that_never_existed_is_a_404(workspace):
    _make()
    client = _client()
    response = _discard(client, "01NOSUCHRECORDATALL0000001", if_match='"anything.0"')
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


def test_a_document_that_does_not_CLAIM_its_own_address_is_refused(workspace):
    """THE CONFUSED DEPUTY, closed on the one path that destroys something.

    `_readable_experiment_state` resolves `id` as `state["id"] or <directory name>`
    — the DOCUMENT wins — while `Experiment.dir` is `scope_root / self.id`. A
    document stored under `<root>/A` whose own `id` reads `B` therefore hydrates
    into a record that is ADDRESSED as A and POINTS AT B, and a discard that acted
    on it would have scanned B's records directory for published artifacts, counted
    A's history rows, deleted B's durable rows, and removed `<root>/B` — B's
    official ISAAC records and evidence sidecars with it.

    Nothing in this application can write that document, which is why this is
    defence in depth rather than a live hole; it is asserted because the read path
    tolerates the mismatch and this path acts on it. The other record is compared
    BYTE FOR BYTE afterwards, because the failure being guarded against is
    precisely one that leaves counts looking right.
    """
    victim = _make(OTHER_ID, runs=("run B",))
    victim_state = _state_bytes(OTHER_ID)
    victim_artifacts = _artifacts(victim)

    # A document filed under EXPERIMENT_ID that claims to be OTHER_ID.
    liar_dir = ws.scope_root(None) / EXPERIMENT_ID
    liar_dir.mkdir(parents=True, exist_ok=True)
    (liar_dir / "experiment.json").write_text(
        json.dumps(
            {
                "id": OTHER_ID,
                "title": "a document that lies about its own address",
                "created_utc": "2026-01-01T00:00:00Z",
                "rev": 0,
                "generation": "g",
                "source": {},
                "draft": {"fields": {}, "pending": []},
            }
        ),
        encoding="utf-8",
    )
    assert ws.load_experiment(EXPERIMENT_ID).id == OTHER_ID  # the mismatch is real

    client = _client()
    response = _discard(client, EXPERIMENT_ID, if_match="*")

    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"
    # NOTHING was removed, on either side of the mismatch.
    assert (liar_dir / "experiment.json").exists()
    assert _state_bytes(OTHER_ID) == victim_state
    assert _artifacts(ws.load_experiment(OTHER_ID)) == victim_artifacts


def test_a_discard_leaves_a_DIFFERENT_experiment_BYTE_IDENTICAL(workspace):
    """The blast radius, measured rather than argued.

    Two records; one is discarded; the other's stored document is compared BYTE FOR
    BYTE. A count would survive a rewrite, and the failure this guards against —
    a path-safety mistake that removed a sibling directory — is exactly the kind
    that leaves counts looking right.
    """
    _make(EXPERIMENT_ID, runs=("run A",))
    _make(OTHER_ID, runs=("run B", "run C"))
    before = _state_bytes(OTHER_ID)
    other_artifacts = _artifacts(ws.load_experiment(OTHER_ID))
    client = _client()

    assert _discard(client, EXPERIMENT_ID).status_code == 200

    assert _state_bytes(OTHER_ID) == before
    assert _artifacts(ws.load_experiment(OTHER_ID)) == other_artifacts
    assert _listed_ids(client) == [OTHER_ID]


# =============================================================================
# 5. the DURABLE half — three statements, one transaction, dependency order
# =============================================================================


def _durable_store(conn: FakeConnection) -> repo.PostgresOrdinaryStore:
    return repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))


def _persisted(conn: FakeConnection, *, runs: tuple[str, ...] = ()) -> "ws.Experiment":
    """An experiment written through the real durable path, so the rows are real."""
    exp = ws.Experiment(
        id=EXPERIMENT_ID,
        title="Durable discard fixture",
        created_utc="2026-01-01T00:00:00Z",
        source={"description": "x", "files": []},
        draft={"fields": {}, "pending": []},
        generation="gen-1",
    )
    for label in runs:
        exp.add_run(label=label, draft={"fields": {}, "pending": []})
    _durable_store(conn).persist(exp)
    # THE COUNTERS ARE RESET, NOT JUST THE STATEMENT LOG. `persist` opens and
    # commits a transaction of its own, so a case asserting "one transaction,
    # committed once" over the discard would otherwise be reading the fixture's.
    conn.statements.clear()
    conn.commits = 0
    conn.rollbacks = 0
    return exp


def test_the_three_deletes_are_issued_in_FOREIGN_KEY_DEPENDENCY_ORDER(workspace):
    """CHILDREN FIRST, and the order is a requirement rather than a preference.

    No migration in this repository writes an `ON DELETE` clause, so `NO ACTION`
    applies: PostgreSQL refuses to delete a parent row that still has children.
    Issuing the experiment delete first would abort the transaction on every record
    that had a single run.
    """
    conn = FakeConnection()
    exp = _persisted(conn, runs=("run A", "run B"))
    assert conn.runs and EXPERIMENT_ID in conn.projections
    conn.statements.clear()

    removed = _durable_store(conn).discard(exp)

    issued = [sql for sql, _ in conn.statements]
    deletes = [sql for sql in issued if sql.lower().startswith("delete")]
    assert deletes == [
        repo.Q_DELETE_RUN_PROJECTION_FOR_EXPERIMENT,
        repo.Q_DELETE_RUNS_FOR_EXPERIMENT,
        repo.Q_DELETE_EXPERIMENT,
    ], issued
    assert removed == 1
    assert conn.runs == {}
    assert conn.projections == {}
    assert EXPERIMENT_ID not in conn.experiments
    # ONE transaction, committed once.
    assert conn.commits == 1 and conn.rollbacks == 0


def test_every_delete_carries_the_experiment_id_as_a_PARAMETER(workspace):
    """No caller-supplied SQL, and no id interpolated into a statement.

    `db_write`'s primary guarantee is that no caller-supplied SQL exists in the
    write path. Each statement is a module-level constant with `%s` placeholders,
    and the id arrives beside it.
    """
    conn = FakeConnection()
    exp = _persisted(conn, runs=("run A",))
    conn.statements.clear()
    _durable_store(conn).discard(exp)
    for sql, params in conn.statements:
        if sql.lower().startswith("delete"):
            assert params == (EXPERIMENT_ID,), (sql, params)
            assert EXPERIMENT_ID not in sql


def test_a_FOREIGN_KEY_REFUSAL_removes_NOTHING_AT_ALL(workspace):
    """THE BACKSTOP, asserted as an OUTCOME rather than as a protocol shape.

    If the route's precheck were ever wrong and a record with history reached the
    durable delete, the server refuses the LAST of the three statements and the two
    already issued roll back with it. So the run rows and the completeness claim
    are still there afterwards — not merely "an exception was raised".
    """
    conn = FakeConnection()
    exp = _persisted(conn, runs=("run A", "run B"))
    conn.history_for.add(EXPERIMENT_ID)
    runs_before = dict(conn.runs)
    assert runs_before

    with pytest.raises(repo.DiscardRefusedByHistory):
        _durable_store(conn).discard(exp)

    assert conn.runs == runs_before
    assert set(conn.projections) == {EXPERIMENT_ID}
    assert EXPERIMENT_ID in conn.experiments
    assert conn.rollbacks == 1 and conn.commits == 0


def test_a_foreign_key_refusal_is_NOT_recorded_as_a_storage_outage(workspace):
    """The round trip worked and the server behaved as designed.

    Recording an outage would send an operator to look at a healthy database and
    would make `/api/health` claim durability had failed — the same reasoning
    `DurableWriteConflict` already carries.
    """
    conn = FakeConnection()
    exp = _persisted(conn, runs=("run A",))
    conn.history_for.add(EXPERIMENT_ID)
    repo.forget_storage_failure()
    with pytest.raises(repo.DiscardRefusedByHistory):
        _durable_store(conn).discard(exp)
    assert repo.storage_failure() is None


def test_a_route_level_backstop_refusal_is_a_409_that_removed_nothing(
    workspace, monkeypatch
):
    """What a CLIENT sees when the backstop fires: a typed 409, and the record
    still there.

    The durable refusal is injected rather than reached through a real history row,
    because reaching it for real would require the precheck to be wrong — which is
    the thing that is not true. What is being pinned is that the route renders it
    as a refusal rather than as a 500 or, worse, as a success.
    """
    _make()
    client = _client()

    def _refuse(_exp):
        raise repo.DiscardRefusedByHistory(EXPERIMENT_ID)

    monkeypatch.setattr(ws, "discard_experiment", _refuse)
    response = _discard(client)

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "history_rows_present"
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_a_DEPLOYMENT_WITHOUT_0002_OR_0005_still_discards_the_experiment(workspace):
    """The pod between a merge and the operator's `--apply`, which is normal here.

    The image rolls out on merge and migrations are applied separately by hand, so
    this build routinely runs against a database missing a table of its own.
    Naming an absent relation would abort the transaction and take the experiment
    delete down with it — a discard that fails for a table NOTHING READS.
    """
    conn = FakeConnection(run_table=False, projection_table=False)
    exp = _persisted(conn)
    conn.statements.clear()

    removed = _durable_store(conn).discard(exp)

    issued = [sql for sql, _ in conn.statements]
    assert repo.Q_DELETE_EXPERIMENT in issued
    assert repo.Q_DELETE_RUNS_FOR_EXPERIMENT not in issued
    assert repo.Q_DELETE_RUN_PROJECTION_FOR_EXPERIMENT not in issued
    assert removed == 1
    assert conn.commits == 1


def test_a_record_the_database_never_held_reports_ZERO_rows_removed(workspace):
    """`0` is honest, not an error.

    A record created before the migration reached this deployment, or written while
    the database was unreachable, has no durable row. `rowcount` is MEASURED and
    reported, so the response never claims a removal that did not happen.
    """
    conn = FakeConnection()
    exp = ws.Experiment(
        id=OTHER_ID,
        title="Never persisted",
        created_utc="2026-01-01T00:00:00Z",
        source={"description": "x", "files": []},
        draft={"fields": {}, "pending": []},
        generation="gen-1",
    )
    assert _durable_store(conn).discard(exp) == 0


def test_a_WORKED_EXAMPLE_record_can_never_reach_the_durable_discard(workspace):
    """The isolation guard, asserted on THIS method rather than inherited by faith.

    `refuse_if_not_persistable` is the guard `persist` runs, in the same place, for
    the same reason. It raises before anything is opened, so no statement is issued
    and no storage failure is recorded.
    """
    conn = FakeConnection()
    session_record = ws.Experiment(
        id=EXPERIMENT_ID,
        title="A session record",
        created_utc="2026-01-01T00:00:00Z",
        source={"description": "x", "files": []},
        draft={"fields": {}, "pending": []},
        generation="gen-1",
        session_id="a-worked-example-session",
    )
    with pytest.raises(repo.NotPersistable):
        _durable_store(conn).discard(session_record)
    assert conn.statements == []

    canonical = ws.Experiment(
        id=sorted(ws.CANONICAL_IDS)[0],
        title="A canonical example",
        created_utc="2026-01-01T00:00:00Z",
        source={"description": "x", "files": []},
        draft={"fields": {}, "pending": []},
        generation="gen-1",
    )
    with pytest.raises(repo.NotPersistable):
        _durable_store(conn).discard(canonical)
    assert conn.statements == []


def test_an_UNAVAILABLE_database_refuses_the_discard_and_keeps_the_directory(
    workspace, monkeypatch
):
    """THE DURABLE DELETE GOES FIRST, and this is why.

    If the database does not accept the removal, the workspace directory is NOT
    removed — so the record is still there and the reader is told the discard did
    not happen. The other ordering loses the directory and leaves a durable row
    that hydration writes straight back: a discard that silently undoes itself at
    the next pod restart.
    """
    _make()
    exp = ws.load_experiment(EXPERIMENT_ID)

    class _Refusing:
        @staticmethod
        def discard(_exp):
            raise repo.StorageUnavailable(repo.STORAGE_DISCARD_FAILED_MESSAGE)

    monkeypatch.setattr(ws, "_ordinary_store", lambda session_id: _Refusing)
    with pytest.raises(repo.StorageUnavailable):
        ws.discard_experiment(exp)
    assert (ws.scope_root(None) / EXPERIMENT_ID).exists()
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_the_discard_failure_message_names_no_host_path_user_or_driver_message():
    """It reaches a response body, so it must never acquire one.

    And it must not say "nothing was saved", which is the WRITE wording: a reader
    told that about a failed discard would conclude the discard had worked.
    """
    message = repo.STORAGE_DISCARD_FAILED_MESSAGE
    for forbidden in ("/", "\\", "psycopg", "postgres://", "PGHOST", "password", "@"):
        assert forbidden not in message, forbidden
    assert "Nothing was discarded" in message
    assert "Nothing was saved" not in message


# =============================================================================
# 6. the history read — three answers, never two
# =============================================================================


def test_a_deployment_with_NO_DATABASE_can_discard_without_reading_any_history(
    workspace,
):
    """`revision_history.reader()` is `None`, so there is nothing to read.

    The gate is `repo._postgres_available`, the SAME function the submit path gates
    on — so a deployment that cannot RECORD a submission is exactly a deployment
    that cannot HOLD one, and "no history read was possible" and "no history can
    exist" are the same fact here rather than two hopeful ones.
    """
    client = _client()
    experiment_id = _create_over_http(client)
    assert rhist.reader() is None
    assert _discard(client, experiment_id).status_code == 200


def test_ABSENT_HISTORY_TABLES_are_not_the_same_as_a_ZERO_COUNT(workspace, monkeypatch):
    """`tables_present: False` must never be read as "the counts are 0".

    On an unmigrated deployment nobody computed a count, and a caller that read one
    off it would be reading a number that does not exist. Both are safe answers for
    a discard; only one of them is a measurement.
    """
    conn = FakeSubmissionConnection(tables=False)
    reader = fake_reader(conn)
    assert reader.presence(EXPERIMENT_ID) == {
        "tables_present": False,
        "revision_count": 0,
        "submission_count": 0,
    }
    monkeypatch.setattr(rhist, "reader", lambda env=None: reader)
    client = _client()
    experiment_id = _create_over_http(client)
    assert _discard(client, experiment_id).status_code == 200


def test_an_UNREADABLE_history_is_a_503_and_discards_NOTHING(workspace, monkeypatch):
    """FAIL CLOSED. The question that decides whether this record may be destroyed
    has no answer, so the record is not destroyed.

    A 503 and not a 409: this is a fact about the SERVER, not about the record, and
    a reader who was told "this record was submitted" about a database timeout
    would go looking for a submission nobody made.
    """
    class _Broken:
        @staticmethod
        def presence(_experiment_id):
            raise RuntimeError("the connection dropped mid-transaction")

    monkeypatch.setattr(rhist, "reader", lambda env=None: _Broken)
    _make()
    before = _state_bytes(EXPERIMENT_ID)
    client = _client()

    response = _discard(client)

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "submission_history_unreadable"
    assert body["failure"] == "RuntimeError"
    # THE CLASS NAME AND NOTHING ELSE — psycopg2's messages carry the host, the
    # user and the connection string.
    assert "connection dropped" not in json.dumps(body)
    assert ws.load_experiment(EXPERIMENT_ID) is not None
    assert _state_bytes(EXPERIMENT_ID) == before


def test_the_history_precheck_reads_TWO_COUNTS_and_no_document(workspace, wired, db):
    """It asks whether ANY row exists, and it asks it of BOTH foreign-key parents.

    `isaac_submissions.experiment_id` is its own foreign key into
    `isaac_experiments`, declared by `0004` independently of `0003`'s — so counting
    only revisions would be reasoning about one parent's children and calling it
    both. And it fetches no `state`, no subject and no signature: this operation
    has no business reading the content of history it is about to refuse to touch.
    """
    reader = fake_reader(db)
    db.statements.clear()
    assert reader.presence(EXPERIMENT_ID) == {
        "tables_present": True,
        "revision_count": 0,
        "submission_count": 0,
    }
    issued = [sql for sql, _ in db.statements]
    assert rhist.Q_REVISION_COUNT in issued
    assert rhist.Q_SUBMISSION_COUNT_FOR_EXPERIMENT in issued
    for forbidden in (
        rhist.Q_REVISION_BY_NO,
        rhist.Q_REVISIONS_FOR_EXPERIMENT,
        rhist.Q_CHANGES_FOR_REVISION,
        rhist.Q_RUN_REVISIONS_FOR_REVISION,
    ):
        assert forbidden not in issued, forbidden


# =============================================================================
# 7. the statement set — what discard CANNOT express
# =============================================================================

# --- ADDED BY INDEPENDENT REVIEW -------------------------------------------
#
# Two claims this slice made that nothing in it checked, and one of which was
# false in the PUBLISHED contract. Both are pinned here as measurements rather
# than restated as prose, because prose is what was wrong.


def test_the_503_description_names_BOTH_facts_it_can_report(workspace):
    """THE PUBLISHED `503` DESCRIBED ONE OF ITS TWO BRANCHES.

    ``responses=`` spreads ``_R_STORAGE_UNAVAILABLE`` and then
    ``_R_DISCARD_HISTORY_UNREADABLE``, both keyed ``503``, so the later one
    REPLACES the earlier one outright — which is fine and is how
    ``/experiments/{id}/pending`` and ``/experiments/{id}/submit`` already resolve
    their own collisions, but it makes the winner the only text a client reads.
    The winner asserted *"`error` is `submission_history_unreadable`"* flatly,
    while the route reachably answers ``503 {"error":
    "experiment_storage_unavailable"}`` — measured below over HTTP, not argued.
    ``test_about_and_openapi``'s own comment for this route already said the 503
    "carries TWO DIFFERENT FACTS"; the contract carried one.

    Asserted over the SERVED document and over both reachable branches, so a
    future edit that drops either half fails here rather than at a reader.
    """
    from isaac_api.app import create_app

    served = (
        create_app()
        .openapi()["paths"]["/api/experiments/{experiment_id}/discard"]["post"]
        ["responses"]["503"]["description"]
    )
    assert "submission_history_unreadable" in served
    assert "experiment_storage_unavailable" in served
    # And the winner really is the discard-specific dict, not the shared one — if
    # the spread order were ever reversed this would catch it, because the shared
    # storage description names neither error value.
    assert "NOTHING WAS REMOVED" in served

    # BRANCH 2, REACHED FOR REAL. Branch 1 has its own test above
    # (`test_an_UNREADABLE_history_is_a_503_and_discards_NOTHING`).
    class _RefusingStore:
        def discard(self, exp):
            raise repo.StorageUnavailable(repo.STORAGE_DISCARD_FAILED_MESSAGE)

    _make()
    client = _client()
    import isaac_api.workspace as _ws

    original = _ws._ordinary_store
    _ws._ordinary_store = lambda session_id: _RefusingStore()
    try:
        response = _discard(client)
    finally:
        _ws._ordinary_store = original
    assert response.status_code == 503, response.text
    assert response.json()["error"] == "experiment_storage_unavailable"
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_the_FK_BACKSTOP_is_TWO_direct_keys_and_the_rest_are_TRANSITIVE():
    """THE BACKSTOP'S OWN COUNT, MEASURED FROM THE MIGRATION SQL.

    Two docstrings in `experiment_repository` said `0003`/`0004` declare "four
    more foreign keys into the same parent". They declare SIX between them and
    exactly TWO name `isaac_experiments`; the claim overstated the direct backstop
    in the one place that argues for it. The guarantee is unchanged and is
    TRANSITIVE — every other history table reaches `isaac_experiments` through one
    of those two — which is why the miscount was never a hole, and which is
    exactly the part a bare number could not have told a reader.

    (The reviewer's own first correction said FIVE and was wrong by one. That is
    recorded here rather than tidied away: a count nobody executes is a guess
    however carefully it is reasoned, and this test is the execution.)

    Measured over the SQL with comment lines stripped, because every `ON DELETE`
    string in these files lives in a comment explaining why there is none.
    """
    import re

    migrations = Path(repo.__file__).parent / "migrations"
    tables = (
        "isaac_experiments",
        "isaac_runs",
        "isaac_run_projection",
        *_HISTORY_TABLES,
    )
    #: child table -> the parent tables it declares a foreign key into.
    edges: dict[str, set[str]] = {}
    declared_by_0003_0004: list[str] = []
    for path in sorted(migrations.glob("0*.sql")):
        if "rollback" in path.name:
            continue
        body = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("--")
        )
        # THE WHOLE BACKSTOP RESTS ON THIS: no `ON DELETE`, so `NO ACTION` applies.
        # Asserted over the SQL body only — every `ON DELETE` string in these files
        # lives in a comment explaining why there is none, so a scan over the raw
        # text would report the opposite of the truth.
        assert not re.search(r"\bON\s+DELETE\b", body, re.I), path.name
        assert not re.search(r"\bON\s+UPDATE\b", body, re.I), path.name
        for match in re.finditer(
            r"CONSTRAINT\s+(\w+)\s*\n?\s*REFERENCES\s+(\w+)\s*\(", body
        ):
            constraint, parent = match.group(1), match.group(2)
            # The constraint name is prefixed with its own table's name; the
            # LONGEST match wins so `isaac_run_revisions_*` is not read as
            # `isaac_runs_*`.
            child = max(
                (t for t in tables if constraint.startswith(t + "_")),
                key=len,
                default=None,
            )
            assert child is not None, constraint
            edges.setdefault(child, set()).add(parent)
            if path.name.startswith(("0003", "0004")):
                declared_by_0003_0004.append(constraint)

    assert len(declared_by_0003_0004) == 6, sorted(declared_by_0003_0004)
    direct = sorted(
        constraint
        for constraint in declared_by_0003_0004
        if "isaac_experiments"
        in edges[
            max((t for t in tables if constraint.startswith(t + "_")), key=len)
        ]
        and constraint.endswith("_experiment_fk")
    )
    assert direct == [
        "isaac_experiment_revisions_experiment_fk",
        "isaac_submissions_experiment_fk",
    ], direct

    # THE TRANSITIVE HALF, which is what makes two enough: every history table
    # reaches `isaac_experiments` by following foreign keys, so no history row can
    # exist without a row that directly blocks the experiment delete.
    for table in _HISTORY_TABLES:
        seen: set[str] = set()
        frontier = {table}
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            frontier |= edges.get(current, set())
        assert "isaac_experiments" in seen, (table, sorted(seen))




#: Every table whose rows must never be updated or deleted by this application.
_HISTORY_TABLES = (
    "isaac_experiment_revisions",
    "isaac_run_revisions",
    "isaac_revision_changes",
    "isaac_submissions",
    "isaac_submission_runs",
)


def _module_q_constants(module) -> dict[str, str]:
    """Every module-level ``Q_*`` string constant in one module, from its SOURCE.

    Parsed from the AST rather than read off the module object, so a statement
    assembled at run time — which is exactly how someone would slip past a scan
    over attributes — shows up as a non-``Constant`` and is reported rather than
    silently skipped. The same device
    ``test_submission_store._module_statements`` uses.
    """
    out: dict[str, str] = {}
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.startswith("Q_"):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                out[target.id] = value.value
            else:
                resolved = getattr(module, target.id, None)
                if isinstance(resolved, str):
                    out[target.id] = resolved
    return out


def test_no_statement_in_the_repository_module_deletes_or_updates_HISTORY():
    """THE GUARD THIS SLICE OWES, stated over the module the deletes live in.

    `test_submission_store.test_no_submission_statement_updates_or_deletes_history`
    already scans every backend module for this, and it is not superseded — but it
    is filed under the submission store, and `experiment_repository` is where a
    future delete would be WRITTEN. A guard the author of that delete will not open
    is a guard that does not do its job, so the same property is asserted here, in
    the place the mistake would be made.

    The five tables are append-only. This is the whole of that guarantee for this
    application, because the database cannot provide one: a `BEFORE DELETE` trigger
    needs a dollar-quoted body, which `db_migrate.split_statements` refuses, and
    `REVOKE` is a forbidden verb.
    """
    offenders: list[str] = []
    for name, sql in _module_q_constants(repo).items():
        lowered = " ".join(sql.lower().split())
        for table in _HISTORY_TABLES:
            if table not in lowered:
                continue
            offenders.append(f"{name} names {table}: {sql[:90]}")
    assert offenders == [], (
        "a statement in experiment_repository names an append-only history table, "
        f"which discard must never be able to reach: {offenders}"
    )


def test_the_scan_above_is_not_vacuous():
    """Guards the guard, three ways.

    It must be READING this module's statements, it must really SEE the three
    deletes the discard added, and its table match must really match the shape it
    forbids. Without the third, a scan whose needle was misspelled would report a
    clean tree forever.
    """
    constants = _module_q_constants(repo)
    assert "Q_DELETE_EXPERIMENT" in constants
    assert "Q_DELETE_RUNS_FOR_EXPERIMENT" in constants
    assert "Q_DELETE_RUN_PROJECTION_FOR_EXPERIMENT" in constants
    assert "Q_UPSERT_EXPERIMENT" in constants
    # The match really matches: a statement of the forbidden shape trips it.
    forbidden = "DELETE FROM isaac_experiment_revisions WHERE experiment_id = %s"
    assert any(table in forbidden.lower() for table in _HISTORY_TABLES)


def test_the_repository_declares_EXACTLY_THREE_deletes_and_they_name_three_tables():
    """THE BLAST RADIUS OF DISCARD, as a property of the statement set.

    Not "the route only deletes three things" — that is control flow, and control
    flow changes. This is what the module can EXPRESS: three DELETEs, naming
    `isaac_run_projection`, `isaac_runs` and `isaac_experiments`, plus the shadow
    write's own run diff. A fourth DELETE, or one naming a fourth table, fails here.
    """
    deletes = {
        name: sql
        for name, sql in _module_q_constants(repo).items()
        if sql.lower().lstrip().startswith("delete")
    }
    assert set(deletes) == {
        "Q_DELETE_ABSENT_RUNS",  # the shadow write's diff — predates this slice
        "Q_DELETE_RUN_PROJECTION_FOR_EXPERIMENT",
        "Q_DELETE_RUNS_FOR_EXPERIMENT",
        "Q_DELETE_EXPERIMENT",
    }, sorted(deletes)
    named = set()
    for sql in deletes.values():
        for table in ("isaac_run_projection", "isaac_runs", "isaac_experiments"):
            if table in sql.lower():
                named.add(table)
    assert named == {"isaac_run_projection", "isaac_runs", "isaac_experiments"}


def test_no_statement_this_discard_can_cause_names_the_PRODUCTION_TABLE(workspace):
    """`records` holds the production-derived 30-row sample.

    Refused twice over and independently: `db_write._FORBIDDEN_TABLES` refuses any
    statement whose token stream contains the identifier at all, and `OWNED_TABLES`
    does not list it. Asserted over the statements a real discard issues, not over
    prose about them.
    """
    conn = FakeConnection()
    exp = _persisted(conn, runs=("run A",))
    _durable_store(conn).discard(exp)
    for sql, _ in conn.statements:
        assert "records" not in sql.lower(), sql
    # And the two independent mechanisms, asserted rather than described. The
    # membership check reads `db_write` because that is where the list LIVES —
    # reading it off `experiment_repository` would have made this line vacuous.
    assert "records" not in dbw.OWNED_TABLES
    with pytest.raises(dbw.WriteRefused):
        dbw.WriteStatementPolicy().check("DELETE FROM records WHERE record_id = %s")


def test_there_is_no_HTTP_DELETE_verb_on_any_experiment_route(workspace):
    """A domain operation, not a generic delete — asserted on the route table.

    A `DELETE` on `/experiments/{id}` would tell every client the resource is
    generically deletable, which is exactly what was not authorized. The only
    `DELETE` this API publishes is the worked-example session's own lifecycle.
    """
    from isaac_api.app import create_app

    schema = create_app().openapi()
    deletes = [
        path for path, ops in schema["paths"].items() if "delete" in ops
    ]
    assert deletes == ["/api/tutorial/sessions/{session_id}"], deletes
    assert "post" in schema["paths"]["/api/experiments/{experiment_id}/discard"]


# =============================================================================
# 8. worked-example scope isolation
# =============================================================================


@pytest.fixture()
def tclient(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def test_a_SESSION_header_can_never_reach_an_ORDINARY_record(tclient, tmp_path):
    """Scope isolation, in the direction that would be a data-loss bug.

    An ordinary record addressed with a session header resolves in the SESSION, not
    in the ordinary workspace, so it is a 404 — the request is never silently
    answered from the other scope instead.
    """
    _make()  # an ORDINARY record, in the same workspace root
    assert ws.load_experiment(EXPERIMENT_ID) is not None

    response = tclient.post(
        f"/api/experiments/{EXPERIMENT_ID}/discard",
        json={"confirmed_by_user": True},
        headers={"If-Match": "*"},
    )

    assert response.status_code == 404, response.text
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_an_ORDINARY_request_can_never_reach_a_SESSION_record(tclient):
    """And the other direction. A canonical id in a session is not in the ordinary
    workspace, so the unheadered request is a 404 rather than a cross-scope read."""
    session_id = tclient.tutorial_session_id
    canonical = sorted(ws.CANONICAL_IDS)[0]
    assert ws.load_experiment(canonical, session_id=session_id) is not None

    client = _client()
    response = _discard(client, canonical, if_match="*")

    assert response.status_code == 404, response.text
    assert ws.load_experiment(canonical, session_id=session_id) is not None


def test_a_discard_inside_a_session_refuses_because_every_record_there_is_canonical(
    tclient,
):
    """A stated consequence rather than one left to be discovered.

    Every record a worked-example session can hold IS a canonical example — the
    session is seeded with exactly five and `POST /api/experiments` refuses the
    session header — and canonical examples are refused. So a discard inside a
    session always answers 409 in this build. Threading the scope is still what
    makes that refusal correct: it is a refusal about THAT session's record.
    """
    canonical = sorted(ws.CANONICAL_IDS)[0]
    session_id = tclient.tutorial_session_id

    response = tclient.post(
        f"/api/experiments/{canonical}/discard",
        json={"confirmed_by_user": True},
        headers={"If-Match": "*"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "canonical_example_record"
    assert ws.load_experiment(canonical, session_id=session_id) is not None


# =============================================================================
# 9. THE REAL ENGINE — opt-in, loopback-only, and it WRITES
# =============================================================================
#
# EVERYTHING ABOVE IS A CONNECTION DOUBLE. These four are not: they run the three
# deletes against a real PostgreSQL and read the rows back. They answer the half
# this file's own docstring says it cannot — whether the SQL is valid, whether the
# `NO ACTION` foreign keys really refuse a parent row with children, and whether
# the transaction really rolls the other two deletes back when one is refused.
#
# THE GATE IS `test_run_row_parity`'s, REUSED RATHER THAN COPIED, and reusing it is
# the point rather than a convenience: it is a consent env var checked FIRST and
# unconditionally, plus a loopback-only `PGHOST` check, plus a `PGHOSTADDR`
# refusal, plus the `PGDATABASE` gate, plus a probe that the tables exist. That
# module's own comments record the accident each layer closes, including one an
# independent security review measured. A second, weaker gate written here would be
# exactly the kind of drift those layers exist to prevent. Set
# `ISAAC_RUN_REAL_ENGINE_PARITY=1` only against a throwaway engine.
#
# THEY SKIP EVERYWHERE ELSE, INCLUDING THE ORDINARY CI BACKEND JOB. A skipped test
# is a visible non-result; that is deliberate, and it is why the doubles above are
# not thinned out to compensate.

from test_run_row_parity import (  # noqa: E402 - after the fixtures it reuses
    _execute,
    _new_experiment,
    _query,
    real_engine,
)

#: A read of the history table, issued BY THE TEST. It is a legal, policy-passing
#: SELECT against an owned table — and it is deliberately not an application
#: statement: nothing in `experiment_repository` may ever name this relation, which
#: `test_no_statement_in_the_repository_module_deletes_or_updates_HISTORY` asserts.
Q_TEST_REVISIONS_OF = (
    "SELECT revision_id FROM isaac_experiment_revisions WHERE experiment_id = %s"
)

#: The out-of-band INSERT that plants a history row so the backstop can be reached.
#: Only a test issues this; the application's own writer is `submission_store`.
Q_TEST_PLANT_A_REVISION = (
    "INSERT INTO isaac_experiment_revisions"
    " (revision_id, experiment_id, revision_no, experiment_rev, generation,"
    " content_signature, state, reason, subject, trust_basis)"
    " VALUES (%s, %s, 1, 0, %s, %s, %s::jsonb, 'submission', NULL, 'unattributed')"
)

Q_TEST_UNPLANT_A_REVISION = (
    "DELETE FROM isaac_experiment_revisions WHERE revision_id = %s"
)

# --- ADDED BY INDEPENDENT REVIEW: the OTHER direct foreign key ----------------
#
# TWO foreign keys name `isaac_experiments` from the history side —
# `isaac_experiment_revisions_experiment_fk` and `isaac_submissions_experiment_fk`
# — and the four scenarios above exercise ONLY THE FIRST. The planted row is always
# a revision, so the key that protects a SUBMISSION, which is the artifact this
# operation's authorization names first among the things it may not erase, is
# proven by nothing on any engine. `CLAUDE.md` §15 records that
# `isaac_submissions_experiment_fk` is one of the FIVE declared constraints the
# migration job's coverage step drives no refusal off either, so this is not
# covered elsewhere in CI.
#
# THE SUBMISSION'S PARENT REVISION IS PLANTED ON A DIFFERENT EXPERIMENT, which is
# what makes the scenario isolating rather than duplicative: `isaac_submissions`
# carries its OWN `experiment_id` foreign key, independent of the revision's, so a
# submission of experiment A may name a revision of experiment B. A then has a
# submission row and NO revision row, and the only key that can refuse its delete
# is the one under test.
#
# IT ALSO GIVES `Q_SUBMISSION_COUNT_FOR_EXPERIMENT` ITS FIRST REAL EXECUTION. That
# statement is new in this slice and is otherwise matched only by an in-process
# double that compares it by string equality, so a wrong column or table name in it
# is invisible to every test in this repository.

Q_TEST_PLANT_A_SUBMISSION = (
    "INSERT INTO isaac_submissions"
    " (submission_id, experiment_id, revision_id, content_signature, unit_count,"
    " subject, trust_basis)"
    " VALUES (%s, %s, %s, %s, 1, NULL, 'unattributed')"
)

Q_TEST_UNPLANT_A_SUBMISSION = (
    "DELETE FROM isaac_submissions WHERE submission_id = %s"
)

Q_TEST_SUBMISSIONS_OF = (
    "SELECT submission_id FROM isaac_submissions WHERE experiment_id = %s"
)

#: A value that SATISFIES `isaac_experiment_revisions_signature_shape`
#: (`CHECK (content_signature ~ '^[0-9a-f]{64}$')`) and is unmistakably not a
#: digest of anything: 64 hex characters of `dead`/`beef`. The CHECK is why a
#: plain descriptive string cannot be used here — the engine refuses it, which is
#: the constraint doing its job.
_SYNTHETIC_SIGNATURE = ("deadbeef" * 8)

Q_TEST_EXPERIMENT_ROWS = (
    "SELECT experiment_id FROM isaac_experiments WHERE experiment_id = %s"
)

Q_TEST_RUN_ROWS_OF = "SELECT run_id FROM isaac_runs WHERE experiment_id = %s"

Q_TEST_PROJECTION_OF = (
    "SELECT experiment_id FROM isaac_run_projection WHERE experiment_id = %s"
)


def _history_tables_present() -> bool:
    """Are `0003`/`0004` applied on this engine? Asked LAZILY, never at import."""
    for table in sstore.REQUIRED_TABLES:
        rows = _query(sstore.Q_TABLE_PRESENT, (table,))
        if not rows or rows[0][0] is None:
            return False
    return True


@real_engine
def test_REAL_ENGINE_the_three_deletes_remove_exactly_this_experiments_rows(tmp_path, monkeypatch):
    """The rows are GONE, read back from the server rather than from a fake.

    A SECOND experiment is created and asserted untouched, because "the delete ran"
    and "the delete removed only what it was addressed to" are different claims and
    a `WHERE` clause is exactly where the second one goes wrong.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    target = _new_experiment("discard: the real-engine target")
    target.add_run(label="run A")
    target.add_run(label="run B")
    assert target.save_versioned() is True
    bystander = _new_experiment("discard: the bystander")
    bystander.add_run(label="run C")
    assert bystander.save_versioned() is True

    assert len(_query(Q_TEST_RUN_ROWS_OF, (target.id,))) == 2
    assert _query(Q_TEST_EXPERIMENT_ROWS, (target.id,))

    removed = repo.ordinary_store().discard(target)

    assert removed == 1
    assert _query(Q_TEST_EXPERIMENT_ROWS, (target.id,)) == []
    assert _query(Q_TEST_RUN_ROWS_OF, (target.id,)) == []
    assert _query(Q_TEST_PROJECTION_OF, (target.id,)) == []
    # The bystander is untouched, in all three tables.
    assert _query(Q_TEST_EXPERIMENT_ROWS, (bystander.id,))
    assert len(_query(Q_TEST_RUN_ROWS_OF, (bystander.id,))) == 1
    assert _query(Q_TEST_PROJECTION_OF, (bystander.id,))


@real_engine
def test_REAL_ENGINE_the_experiment_delete_would_FAIL_if_issued_first(tmp_path, monkeypatch):
    """WHY THE ORDER IS A REQUIREMENT, proved against the engine that requires it.

    `0002_runs` writes no `ON DELETE` clause, so `NO ACTION` applies and the server
    refuses to delete a parent row that still has run rows. The application never
    issues them in this order — this is the statement it would have to issue if it
    did, and the refusal is the reason it does not.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    exp = _new_experiment("discard: the ordering proof")
    exp.add_run(label="run A")
    assert exp.save_versioned() is True

    with pytest.raises(Exception) as raised:  # noqa: PT011 - the driver's own class
        _execute(repo.Q_DELETE_EXPERIMENT, (exp.id,))
    assert repo.is_foreign_key_violation(raised.value), raised.value

    # And the correct order works on the same rows.
    assert repo.ordinary_store().discard(exp) == 1
    assert _query(Q_TEST_EXPERIMENT_ROWS, (exp.id,)) == []


@real_engine
def test_REAL_ENGINE_a_planted_HISTORY_ROW_refuses_the_discard_and_rolls_back(
    tmp_path, monkeypatch
):
    """THE BACKSTOP, against a real engine and a real history row.

    A revision row is planted OUT OF BAND — by the test, never by the application —
    so the state the route's precheck refuses is reachable here without the
    precheck being wrong. The server then refuses the experiment delete, and the
    two deletes issued before it roll back: the run rows and the completeness claim
    are still there afterwards.

    The planted row is removed in a `finally` so it cannot outlive this test and
    wedge the next one on a shared throwaway engine.
    """
    if not _history_tables_present():
        pytest.skip("0003_revisions / 0004_submissions are not applied on this engine")
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    exp = _new_experiment("discard: the real backstop")
    exp.add_run(label="run A")
    assert exp.save_versioned() is True
    revision_id = "01REALENGINEBACKSTOPREV001"

    _execute(
        Q_TEST_PLANT_A_REVISION,
        (
            revision_id,
            exp.id,
            exp.generation,
            _SYNTHETIC_SIGNATURE,
            json.dumps({"id": exp.id, "synthetic": True}),
        ),
    )
    try:
        assert _query(Q_TEST_REVISIONS_OF, (exp.id,))

        with pytest.raises(repo.DiscardRefusedByHistory):
            repo.ordinary_store().discard(exp)

        # NOTHING WAS REMOVED — all three tables, read back from the server.
        assert _query(Q_TEST_EXPERIMENT_ROWS, (exp.id,))
        assert len(_query(Q_TEST_RUN_ROWS_OF, (exp.id,))) == 1
        assert _query(Q_TEST_PROJECTION_OF, (exp.id,))
        # And the history row itself is untouched, which is the whole point.
        assert _query(Q_TEST_REVISIONS_OF, (exp.id,))
    finally:
        _execute(Q_TEST_UNPLANT_A_REVISION, (revision_id,))


@real_engine
def test_REAL_ENGINE_a_discard_after_the_history_row_is_gone_succeeds(
    tmp_path, monkeypatch
):
    """The control for the case above: without the planted row, the same experiment
    discards cleanly. Without it, a backstop test could pass because the discard was
    broken for some unrelated reason."""
    if not _history_tables_present():
        pytest.skip("0003_revisions / 0004_submissions are not applied on this engine")
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    exp = _new_experiment("discard: the backstop control")
    exp.add_run(label="run A")
    assert exp.save_versioned() is True
    revision_id = "01REALENGINEBACKSTOPREV002"
    _execute(
        Q_TEST_PLANT_A_REVISION,
        (
            revision_id,
            exp.id,
            exp.generation,
            _SYNTHETIC_SIGNATURE,
            json.dumps({"id": exp.id, "synthetic": True}),
        ),
    )
    with pytest.raises(repo.DiscardRefusedByHistory):
        repo.ordinary_store().discard(exp)
    _execute(Q_TEST_UNPLANT_A_REVISION, (revision_id,))

    assert repo.ordinary_store().discard(exp) == 1
    assert _query(Q_TEST_EXPERIMENT_ROWS, (exp.id,)) == []
    assert _query(Q_TEST_RUN_ROWS_OF, (exp.id,)) == []



@real_engine
def test_REAL_ENGINE_a_planted_SUBMISSION_alone_refuses_the_discard(
    tmp_path, monkeypatch
):
    """THE SECOND DIRECT FOREIGN KEY, AND NOTHING ELSE PROVES IT BEHAVES.

    See the comment above `Q_TEST_PLANT_A_SUBMISSION`. The submission names a
    revision of a DIFFERENT experiment, so the target carries a submission row and
    no revision row and `isaac_submissions_experiment_fk` is the only constraint
    that can refuse the delete.

    It also asserts the route's own precheck over the real engine: `presence`
    reports `revision_count: 0` and `submission_count: 1`, which is the exact
    combination the precheck exists to distinguish and the first execution
    `Q_SUBMISSION_COUNT_FOR_EXPERIMENT` has ever had against a server.

    Both planted rows are removed in a `finally`, submission first, because the
    submission references the revision.
    """
    if not _history_tables_present():
        pytest.skip("0003_revisions / 0004_submissions are not applied on this engine")
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    target = _new_experiment("discard: the submission backstop")
    target.add_run(label="run A")
    assert target.save_versioned() is True
    decoy = _new_experiment("discard: the decoy that owns the revision")
    # NO SECOND SAVE, and this line is the one that failed on this scenario's FIRST
    # EXECUTION ANYWHERE. It read `assert decoy.save_versioned() is True`, copied from
    # the target above — but the target is MUTATED first (`add_run`), and the decoy is
    # not. `_new_experiment` goes through `repository.create()`, which already
    # persists; a `save_versioned()` over a byte-identical document is a correct no-op
    # and returns False. The assertion was wrong, not the product.
    #
    # What the decoy is actually for is that `isaac_experiments` holds its id, so the
    # planted revision's foreign key resolves — and `create()` is what guarantees that.
    # So the row is asserted directly, which is both the real precondition and a
    # stronger check than a save that had nothing to save.
    assert _query(Q_TEST_EXPERIMENT_ROWS, (decoy.id,)), (
        "the decoy must exist in isaac_experiments, or the planted revision's "
        "foreign key could not resolve and this scenario would prove nothing"
    )

    revision_id = "01REALENGINESUBMITREV0001"
    submission_id = "01REALENGINESUBMITSUB0001"
    _execute(
        Q_TEST_PLANT_A_REVISION,
        (
            revision_id,
            decoy.id,  # the DECOY owns it — the target must have no revision row
            decoy.generation,
            _SYNTHETIC_SIGNATURE,
            json.dumps({"id": decoy.id, "synthetic": True}),
        ),
    )
    try:
        _execute(
            Q_TEST_PLANT_A_SUBMISSION,
            (submission_id, target.id, revision_id, _SYNTHETIC_SIGNATURE),
        )
        try:
            # The target really does have a submission and NO revision.
            assert not _query(Q_TEST_REVISIONS_OF, (target.id,))
            assert len(_query(Q_TEST_SUBMISSIONS_OF, (target.id,))) == 1

            # THE PRECHECK, over the real engine: two counts, one transaction.
            presence = rhist.reader().presence(target.id)
            assert presence == {
                "tables_present": True,
                "revision_count": 0,
                "submission_count": 1,
            }, presence

            # AND THE BACKSTOP BEHIND IT, with the revision key out of the picture.
            with pytest.raises(repo.DiscardRefusedByHistory):
                repo.ordinary_store().discard(target)

            # Nothing was removed, all three tables read back from the server.
            assert _query(Q_TEST_EXPERIMENT_ROWS, (target.id,))
            assert len(_query(Q_TEST_RUN_ROWS_OF, (target.id,))) == 1
            assert _query(Q_TEST_PROJECTION_OF, (target.id,))
            assert len(_query(Q_TEST_SUBMISSIONS_OF, (target.id,))) == 1
        finally:
            _execute(Q_TEST_UNPLANT_A_SUBMISSION, (submission_id,))
    finally:
        _execute(Q_TEST_UNPLANT_A_REVISION, (revision_id,))


def test_the_planted_submission_names_every_column_the_DDL_requires():
    """THE SHAPE CHECK THAT RUNS WITHOUT AN ENGINE.

    The scenario above cannot execute on a developer machine — this repository has
    no container runtime and no PostgreSQL — so its `INSERT` would otherwise reach
    CI unexamined, and a missing `NOT NULL` column would fail there as a red build
    with no local reproduction. This parses `0004_submissions.sql` and asserts the
    statement names every column that is `NOT NULL` and carries no `DEFAULT`, which
    is the error that shape of statement actually makes.

    It cannot prove the SQL is valid PostgreSQL — nothing here can. It removes the
    one class of mistake that is checkable without a server.
    """
    import re

    ddl = (Path(repo.__file__).parent / "migrations" / "0004_submissions.sql").read_text(
        encoding="utf-8"
    )
    body = "\n".join(
        line for line in ddl.splitlines() if not line.lstrip().startswith("--")
    )
    start = body.index("CREATE TABLE IF NOT EXISTS isaac_submissions")
    end = body.index("CREATE INDEX", start)
    table = body[start:end]
    # One entry per column declaration line: `    name  type  ...`
    required = []
    for match in re.finditer(
        r"^    (\w+)\s+(text|bigint|jsonb|timestamptz)\b(.*?)(?=^    \w+\s+(?:text|bigint|jsonb|timestamptz)\b|^    CONSTRAINT|\Z)",
        table,
        re.S | re.M,
    ):
        name, _type, rest = match.groups()
        declaration = " ".join((match.group(0)).split())
        if "NOT NULL" in declaration and "DEFAULT" not in declaration:
            required.append(name)
    assert required, table  # the parse itself must not be vacuous
    named = set(
        re.search(r"\(([^)]*)\)\s*VALUES", Q_TEST_PLANT_A_SUBMISSION.replace(
            "INSERT INTO isaac_submissions", ""
        ), re.S).group(1).replace("\n", " ").split(",")
    )
    named = {n.strip() for n in named}
    missing = [column for column in required if column not in named]
    assert not missing, (missing, sorted(named))
