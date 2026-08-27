"""The PRECONDITION itself under concurrency: two layers, two token scopes, one log.

WHY A SIXTH CONCURRENCY FILE, AND WHAT IT DELIBERATELY DOES NOT REPEAT
=====================================================================
``test_handler_concurrency`` proves the record-level compare-and-swap and the
absent-``If-Match`` rules; ``test_lifecycle_concurrency`` proves the run,
submission and decision races; ``test_concurrent_write_pairs_lose_no_update``
proves eight cross-route pairs including both ``If-Match: *`` cases;
``test_discard_concurrency`` proves the destructive path. All four take the
precondition contract as given and race the OPERATIONS.

This file races the CONTRACT. Four things about it have no coverage anywhere, and
each is a place where a client is told one thing and the record does another:

1. **The same ``412 stale_write`` is enforced at two different distances** — the
   HTTP ``If-Match`` check (*does this client's version match the copy THIS
   PROCESS just read?*) and ``experiment_repository``'s ``DurableWriteConflict``
   (*…and is that copy still current for every process?*). ``_save_versioned``'s
   docstring says a client cannot act on the difference. Section C constructs the
   case refused by the SECOND and not the first, on four routes, and asserts
   nothing was written — plus a control proving the identical request succeeds
   when the durable layer is not refusing, which is what makes "not refused by the
   first" a measurement rather than an assumption.

2. **Run-scoped and record-scoped preconditions are DIFFERENT TOKENS**, and two
   sibling routes on the same URL prefix disagree on which they want:
   ``POST .../runs/{id}/overrides`` compares the RUN's, ``POST
   .../runs/{id}/remove`` compares the RECORD's. ``patch_run``'s own description
   records how easily the two get confused. Section A hands each route the wrong
   one *while a legitimate writer is inside the lock* and asserts a clean 412 with
   nothing partially written.

3. **``answer_log`` is excluded from the rev signature**, and both write routes
   append to it *speculatively* before ``save_versioned`` decides whether anything
   changed, popping the entry when nothing did. Section B fires two concurrent
   byte-stable no-ops and asserts the log cannot end up describing a write that
   never landed.

4. **A stale MCP write** goes through a second client with its own error envelope.
   Section D pins that an agent losing a race is told the same typed refusal a
   browser is, and writes nothing.

Section E is about the ROW a submission creates: a revision is a snapshot of what
was submitted, and an edit queued behind that submission must not appear in it.

DETERMINISM
===========
The ordering device is ``test_discard_concurrency._OrderedInterleave`` — imported,
not re-declared, for the reason every file here imports ``_LockRendezvous``: a
second definition of "the leader held the lock first" is free to drift from the
one that is maintained. Its docstring carries the five-step argument that no
interleaving exists in which the follower wins. There is no sleep in this file.

Section C is deliberately NOT a thread race and says so: the durable
compare-and-swap guards the writers this process cannot lock against, so the only
honest way to reach it here is to inject the refusal at the store seam — the same
technique ``test_run_removal`` and ``test_experiment_repository`` already use, and
the same shape a real collision presents to the route. No database is contacted,
and the host is deliberately unroutable so a regression that tried to connect
fails loudly instead of hanging.

Every fixture is the committed synthetic seed draft. Nothing here reads real data.
"""

from __future__ import annotations

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.routes as routes
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws

from isaac_records.models import field_value, user_confirmation

from submission_fake import FakeSubmissionConnection, fake_reader, fake_store
# The ordering device is IMPORTED, not re-declared, for the reason every file here
# imports `_LockRendezvous`: a second definition of "the leader held the lock
# first" is free to drift from the one that is maintained. Its docstring carries
# the five-step argument that no interleaving exists in which the follower wins.
from test_discard_concurrency import _OrderedInterleave, _ordered_race  # noqa: E402

EXPERIMENT_ID = "01PRECONDITIONRACE00000001"
ACTOR = "ada.lovelace"

#: An asset uri the committed seed draft carries ALREADY ANSWERED, so ``/edit``
#: is the operation entitled to write it (``_full_draft()`` has
#: ``pending_count() == 0``, which is what makes it export-ready).
ANSWERED_URI = "ssrl-archive://BL15-2/2099_run_000/raw/"

#: Two well-formed 64-hex sentinels the system can never invent, one per writer.
SHA_A = "a" * 64
SHA_B = "b" * 64

#: A run-level official field path, and a record-level one overridable on a run.
RUN_FIELD = "context.temperature_K"
OVERRIDE_ADDRESS = "field:sample.material.name"


def _confirmed(value: str) -> dict:
    """A ``verified`` draft envelope whose single evidence entry asserts ``value``.

    Built through the truth core's own constructors rather than written out here,
    so the fixture is the same shape the write routes append. A hand-written
    literal is refused: the override route runs the deterministic draft validator
    and answers ``422 invalid_envelope`` for a verified field with no evidence —
    which is how this file first learned that its payload was not a real one.
    """
    return field_value(
        value,
        status="verified",
        evidence=[user_confirmation("What value?", value, "2026-01-01T00:00:00Z")],
    )


# =============================================================================
# fixtures and reads used for ASSERTIONS ONLY
# =============================================================================


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv("PGDATABASE", raising=False)
    return ws


@pytest.fixture()
def armed(workspace, monkeypatch):
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _app():
    from isaac_api.app import create_app

    return create_app()


def _client(app=None) -> TestClient:
    return TestClient(app or _app(), raise_server_exceptions=False)


def _make(*, runs: tuple[str, ...] = (), experiment_id: str = EXPERIMENT_ID):
    exp = ws.create_experiment(
        "Precondition race fixture",
        {"kind": "synthetic"},
        copy.deepcopy(ws._full_draft()),
        id=experiment_id,
    )
    run_draft = copy.deepcopy(exp.draft)
    for label in runs:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


def _record_etag(client, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, run_id: str, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _persisted(experiment_id: str = EXPERIMENT_ID):
    exp = ws.load_experiment(experiment_id)
    assert exp is not None, experiment_id
    return exp


def _state_json(exp) -> str:
    return json.dumps(exp.to_state())


def _versions(exp) -> dict:
    return {
        "record": exp.version_token(),
        "generation": exp.generation,
        "runs": {
            run.id: {"version": run.version_token(), "generation": run.generation}
            for run in exp.sorted_runs()
        },
    }


def _asset_sha(exp, uri: str = ANSWERED_URI) -> str | None:
    for asset in exp.draft.get("assets") or []:
        if isinstance(asset, dict) and asset.get("uri") == uri:
            return asset.get("sha256")
    return None


def _log(exp) -> list:
    return copy.deepcopy(exp.answer_log)


# =============================================================================
# A. RUN-SCOPED vs RECORD-SCOPED PRECONDITIONS — the wrong token, mid-race
# =============================================================================


def test_an_override_handed_the_RECORDS_token_is_a_clean_412_naming_BOTH_ids(
    workspace, monkeypatch
):
    """``POST .../runs/{id}/overrides`` compares the RUN's validator, not the record's.

    The two are always different values, so a client that confused them would be
    refused even with nothing else happening. The race is what makes the assertion
    worth something: a legitimate run edit is inside the lock when the confused
    write arrives, so this pins that the confused client gets the SAME clean 412 it
    would get quietly — not a partial write, and not the winner's outcome.

    THE BODY NAMES BOTH IDS, and that is the property ``_precondition_identity``
    exists for: filing a run id under the key ``experiment_id`` would be a false
    statement in the one body a client reads when its write is refused.
    """
    exp = _make(runs=("run A",))
    run_id = exp.sorted_runs()[0].id
    client = _client()
    record_token = _record_etag(client)
    run_token = _run_etag(client, run_id)
    assert record_token != run_token, "the fixture cannot tell the two tokens apart"
    before = _versions(exp)

    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    legitimate, confused = _ordered_race(
        interleave,
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{run_id}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: 291}},
            headers={"If-Match": run_token},
        ),
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{run_id}/overrides",
            json={
                "confirmed_by_user": True,
                "address": OVERRIDE_ADDRESS,
                "payload": _confirmed(SHA_A),
            },
            headers={"If-Match": record_token},
        ),
    )

    assert legitimate.status_code == 200, legitimate.text
    assert confused.status_code == 412, confused.text
    body = confused.json()
    assert body["error"] == "stale_write", body
    assert body["experiment_id"] == EXPERIMENT_ID, body
    assert body["run_id"] == run_id, body
    assert body["expected_version"] == record_token.strip('"'), body

    after = _persisted()
    assert SHA_A not in _state_json(after), (
        "the refused override's payload reached the document"
    )
    # The run's own overrides map is untouched, and no OTHER validator moved: the
    # legitimate edit moved the run and the record, and nothing else.
    assert (after.get_run(run_id).overrides or {}) == (
        exp.get_run(run_id).overrides or {}
    )
    assert set(_versions(after)["runs"]) == set(before["runs"])


def test_a_run_removal_handed_the_RUNS_token_is_a_clean_412_and_removes_NOTHING(
    workspace, monkeypatch
):
    """``POST .../runs/{id}/remove`` compares the RECORD's validator, not the run's.

    The sibling of the case above, and the pair is the point: the two routes live
    under the same URL prefix, take an ``If-Match`` of the same syntactic shape, and
    want DIFFERENT tokens. A client that reads a run and then removes it — the
    natural sequence — is holding the wrong one.

    The refusal must arrive before the removal. Both runs are still present
    afterwards, with their ordinals and versions unmoved, and that is asserted from
    the persisted document rather than the response.
    """
    exp = _make(runs=("run A", "run B"))
    victim, survivor = [run.id for run in exp.sorted_runs()]
    client = _client()
    run_token = _run_etag(client, victim)
    record_token = _record_etag(client)
    ordinals_before = {run.id: run.ordinal for run in exp.sorted_runs()}
    versions_before = _versions(exp)

    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    legitimate, confused = _ordered_race(
        interleave,
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": "A rename the removing client never saw"},
            headers={"If-Match": record_token},
        ),
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{victim}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": run_token},
        ),
    )

    assert legitimate.status_code == 200, legitimate.text
    assert confused.status_code == 412, confused.text
    body = confused.json()
    assert body["error"] == "stale_write", body
    assert body["experiment_id"] == EXPERIMENT_ID, body
    # A record-scoped refusal names ONE id. `_precondition_identity` falls back to
    # `{"experiment_id": <id>}` for an `Experiment`, and this route guards the
    # record even though its URL names a run.
    assert "run_id" not in body, body

    after = _persisted()
    assert [run.id for run in after.sorted_runs()] == [victim, survivor]
    assert {run.id: run.ordinal for run in after.sorted_runs()} == ordinals_before
    assert _versions(after)["runs"] == versions_before["runs"], (
        "a refused removal moved a run's validator"
    )
    assert after.title == "A rename the removing client never saw"


def test_a_run_edit_handed_the_RECORDS_token_writes_nothing_while_a_sibling_lands(
    workspace, monkeypatch
):
    """``PATCH /runs/{id}`` compares the RUN's validator; the record's is refused.

    The third of the three, and the one with a scientific value at stake. A
    legitimate edit of the OTHER run is inside the lock when the confused write
    arrives, so a build that mixed the two tokens up would corrupt run B while
    reporting success about run A.
    """
    exp = _make(runs=("run A", "run B"))
    first, second = [run.id for run in exp.sorted_runs()]
    client = _client()
    record_token = _record_etag(client)
    first_token = _run_etag(client, first)
    before = _versions(exp)

    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    legitimate, confused = _ordered_race(
        interleave,
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{first}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: 292}},
            headers={"If-Match": first_token},
        ),
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{second}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: 4711}},
            headers={"If-Match": record_token},
        ),
    )

    assert legitimate.status_code == 200, legitimate.text
    assert confused.status_code == 412, confused.text
    body = confused.json()
    assert body["error"] == "stale_write", body
    assert body["run_id"] == second, body
    assert body["expected_version"] == record_token.strip('"'), body

    after = _persisted()
    assert "4711" not in _state_json(after), "the refused run edit's value was stored"
    assert _versions(after)["runs"][second] == before["runs"][second], (
        "the refused write moved the run it was addressed to"
    )


# =============================================================================
# B. THE SPECULATIVE ``answer_log`` APPEND
# =============================================================================


def test_two_concurrent_NO_OP_corrections_leave_no_log_entry_at_all(
    workspace, monkeypatch
):
    """The stored log must never describe a write that did not land.

    Both writers send the value the record ALREADY holds, with ``If-Match: *`` so
    the compare-and-swap cannot separate them and both really do run the write
    path. Each appends ``{"edited": …}`` to ``answer_log`` SPECULATIVELY, before
    ``save_versioned`` has decided anything.

    WHAT MAKES THE PROPERTY TRUE, STATED PRECISELY, BECAUSE THE OBVIOUS ANSWER IS
    NOT THE WHOLE ONE. ``routes`` pops the speculative entry when
    ``save_versioned`` reports no change, and that pop is what keeps the IN-MEMORY
    object honest for the rest of the request. It is not what keeps the FILE
    honest: ``Experiment.save_versioned`` compares the authoritative signature and
    returns ``False`` *before* reaching ``save()`` at all, so a byte-stable no-op
    rewrites nothing. This test asserts the observable composite — no revision, no
    log entry, and no rewrite of the state file — rather than claiming to isolate
    one of the two mechanisms, and the state file is compared BY BYTES so "the file
    was not rewritten" is measured rather than inferred from ``rev``.

    The value is READ OUT of the record and sent straight back, so this is a
    byte-stable resubmission by construction rather than by a literal that could
    drift from the committed seed.
    """
    exp = _make()
    stored = _asset_sha(exp)
    assert stored, "the seed carries no sha at the address this test resubmits"
    log_before = _log(exp)
    rev_before = exp.rev
    state_path = ws.scope_root(None) / EXPERIMENT_ID / "experiment.json"
    bytes_before = state_path.read_bytes()

    client = _client()
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    def _noop():
        return client.post(
            f"/api/experiments/{EXPERIMENT_ID}/edit",
            json={"confirmed_by_user": True, "answers": {ANSWERED_URI: stored}},
            headers={"If-Match": "*"},
        )

    first, second = _ordered_race(interleave, _noop, _noop)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    # THE RESPONSE CARRIES `rev`, NOT A `changed` FLAG. Measured: `POST /edit`
    # returns `{invalidation, pending, pending_page, rev, status, updated_utc,
    # version, workflow}`. A no-op leaves `rev` where it was, which is the same
    # fact stated by the field the wire actually has.
    assert first.json()["rev"] == rev_before, first.text
    assert second.json()["rev"] == rev_before, second.text

    after = _persisted()
    assert after.rev == rev_before, "a no-op bumped the revision"
    assert _log(after) == log_before, (
        "a byte-stable no-op left a log entry describing a write that did not land"
    )
    assert state_path.read_bytes() == bytes_before, (
        "a byte-stable no-op rewrote the state document"
    )


def test_a_REAL_correction_racing_a_no_op_logs_exactly_the_one_that_landed(
    workspace, monkeypatch
):
    """The control that stops the test above passing for the wrong reason.

    A file asserting only that no entry appears would also pass in a build that
    never logged anything. Here the LEADER changes the value (one entry must
    appear) and the follower resubmits what the leader just wrote — a no-op
    relative to the document it finds, though not to the one it read — so exactly
    one entry may exist afterwards, and it must be the leader's.

    Both use ``If-Match: *`` deliberately: with a real token the follower would be
    refused 412 at the precondition and never reach the log at all, which is a
    different (and already-covered) property.
    """
    exp = _make()
    log_before = _log(exp)
    rev_before = exp.rev
    client = _client()
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    def _edit(sha):
        return client.post(
            f"/api/experiments/{EXPERIMENT_ID}/edit",
            json={"confirmed_by_user": True, "answers": {ANSWERED_URI: sha}},
            headers={"If-Match": "*"},
        )

    real, echo = _ordered_race(interleave, lambda: _edit(SHA_A), lambda: _edit(SHA_A))

    assert real.status_code == 200, real.text
    assert echo.status_code == 200, echo.text
    assert real.json()["rev"] == rev_before + 1, real.text
    assert echo.json()["rev"] == rev_before + 1, (
        "the echo either changed the record again or read a different revision"
    )

    after = _persisted()
    assert _asset_sha(after) == SHA_A
    assert after.rev == rev_before + 1, "two writes, and only one of them changed"
    entries = _log(after)
    assert len(entries) == len(log_before) + 1, entries
    assert entries[:-1] == log_before, entries
    assert "edited" in entries[-1], entries[-1]
    assert entries[-1]["edited"], entries[-1]


# =============================================================================
# C. THE TWO LAYERS THAT BOTH SAY ``412 stale_write``
# =============================================================================
#
# NOT A THREAD RACE, AND THAT IS THE HONEST SHAPE. The durable compare-and-swap
# guards the writers THIS PROCESS CANNOT LOCK AGAINST — a second replica — so
# there is no in-process interleaving that reaches it. The refusal is injected at
# the store seam, which is the same technique `test_run_removal` and
# `test_experiment_repository` use and the same shape a real collision presents to
# the route. `PGHOST` is deliberately unroutable: the seam is patched, so no
# connection should be attempted, and an unroutable host makes a regression that
# tried to connect fail loudly instead of hanging.


def _durable_conflict(monkeypatch, winner_state: dict, *, ahead: int = 3):
    """Arm the DURABLE layer to refuse every write, echoing ``winner_state``.

    THE WINNER IS BUILT FROM THE PERSISTED DOCUMENT, NOT FROM THE MUTATED ONE, and
    that distinction is load-bearing rather than stylistic. A real durable refusal
    means ANOTHER writer got there first, so the winning document is THAT writer's
    — one that never carried this request's change. ``Experiment.save`` adopts the
    winner into the workspace file before re-raising, so handing back a "winner"
    that already contained the change would make adoption write the change to disk
    and the test would report a product defect that is really a lying fixture.
    ``test_run_removal`` records paying for exactly that mistake.

    BOTH environment variables, because ``_postgres_available`` runs two gates:
    ``PGHOST`` set AND ``PGDATABASE`` equal to ``dbw.EXPECTED_DATABASE``. Setting
    only the first selects the FILESYSTEM store, the durable path is never entered,
    and every assertion below would pass vacuously as "no 412 here".
    """
    winner = dict(copy.deepcopy(winner_state), rev=winner_state["rev"] + ahead)

    def _always_conflict(self, exp):
        raise repo.DurableWriteConflict(winner, experiment_id=exp.id)

    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    monkeypatch.setattr(repo.PostgresOrdinaryStore, "persist", _always_conflict)
    return winner


def _disarm(monkeypatch):
    """Read the workspace back on the FILESYSTEM path, as any later reader would."""
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv("PGDATABASE", raising=False)


@pytest.mark.parametrize(
    "name",
    ("rename", "correct", "create_run", "override"),
)
def test_a_write_the_HEADER_accepts_is_still_refused_by_the_DURABLE_layer(
    workspace, monkeypatch, name
):
    """The case refused by the SECOND layer and not the first, on four routes.

    The token every request carries is the CURRENT one, so ``_check_if_match``
    returns ``None`` and the request reaches the write. The control below proves
    that: the identical request, with the durable layer not refusing, returns 2xx.
    So the 412 here can only have come from ``DurableWriteConflict``.

    WHAT IS ASSERTED BEYOND THE STATUS. The same ``error`` string and the same body
    keys the header layer emits — one condition must not have two shapes — the
    winner's ``current_rev`` rather than the losing write's, the client's own token
    echoed back as ``expected_version``, and the persisted document read back on
    the filesystem path afterwards to prove the change is not there.
    """
    # ONLY THE RUN CASES GET A RUN, and that is not tidiness. On a record that HAS
    # runs, an asset sha belongs to the run that measured it, so `POST /edit` naming
    # one answers `409 belongs_to_a_run` BEFORE any precondition — a refusal that
    # would have satisfied a status-only assertion while proving nothing about the
    # durable layer. The control below is what surfaced it.
    needs_run = name in {"create_run", "override"}
    exp = _make(runs=("run A",) if needs_run else ())
    run_id = exp.sorted_runs()[0].id if needs_run else None
    client = _client()
    record_token = _record_etag(client)
    run_token = _run_etag(client, run_id) if needs_run else None
    persisted_before = copy.deepcopy(exp.to_state())
    sentinel = "a title no writer landed" if name == "rename" else SHA_B

    winner = _durable_conflict(monkeypatch, persisted_before)

    if name == "rename":
        response = client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": sentinel},
            headers={"If-Match": record_token},
        )
        expected_token, expected_identity = record_token, {"experiment_id": EXPERIMENT_ID}
    elif name == "correct":
        response = client.post(
            f"/api/experiments/{EXPERIMENT_ID}/edit",
            json={"confirmed_by_user": True, "answers": {ANSWERED_URI: sentinel}},
            headers={"If-Match": record_token},
        )
        expected_token, expected_identity = record_token, {"experiment_id": EXPERIMENT_ID}
    elif name == "create_run":
        response = client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs",
            json={"label": "a run no writer landed"},
            headers={"If-Match": record_token},
        )
        expected_token, expected_identity = record_token, {"experiment_id": EXPERIMENT_ID}
    else:
        response = client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{run_id}/overrides",
            json={
                "confirmed_by_user": True,
                "address": OVERRIDE_ADDRESS,
                "payload": _confirmed(sentinel),
            },
            headers={"If-Match": run_token},
        )
        # THE RUN ROUTES ANSWER A DIFFERENT — AND DELIBERATE — BODY HERE, and this
        # is the reason the parametrisation carries an expected token at all rather
        # than assuming one shape for all four.
        #
        # `post_run_override` calls `_save_versioned(exp, None)`, passing the
        # client's validator NOWHERE, and says why: "the client's validator is the
        # RUN's ... echoing a run version as a record conflict's `expected_version`
        # would be two things wearing one name" (`patch_run` states the same rule at
        # greater length and this route cites it). So `expected_rev` and
        # `expected_version` are `null` — the honest answer, not a fabricated one —
        # while `current_rev`/`current_version` still come from the winner. The
        # identity is `{"experiment_id": ...}` and carries no `run_id` for the same
        # reason: a durable refusal is a statement about the RECORD's document.
        #
        # This is therefore NOT the same body the HTTP layer emits on this route
        # (that one names both ids and echoes the run token), and the divergence is
        # a decision rather than a drift. It is pinned so that "the two layers are
        # one contract" is read with the exception that the code actually makes.
        expected_token, expected_identity = None, {"experiment_id": EXPERIMENT_ID}

    assert response.status_code == 412, response.text
    body = response.json()
    assert body["error"] == "stale_write", body
    for key, value in expected_identity.items():
        assert body[key] == value, body
    if expected_token is None:
        assert body["expected_version"] is None, body
        assert body["expected_rev"] is None, body
    else:
        assert body["expected_version"] == expected_token.strip('"'), body
        assert body["expected_rev"] == int(expected_token.strip('"').rsplit(".", 1)[-1]), body
    assert body["current_rev"] == winner["rev"], body
    assert set(body) >= {
        "error",
        "experiment_id",
        "expected_rev",
        "current_rev",
        "expected_version",
        "current_version",
    }, sorted(body)

    _disarm(monkeypatch)
    after = _persisted()
    assert sentinel not in _state_json(after), (
        "a write the durable layer refused reached the workspace document"
    )
    assert [run.id for run in after.sorted_runs()] == ([run_id] if needs_run else []), (
        "a refused write changed the run set"
    )
    assert after.title == persisted_before["title"]


@pytest.mark.parametrize("name", ("rename", "correct", "create_run", "override"))
def test_the_SAME_request_succeeds_when_only_the_durable_layer_is_disarmed(
    workspace, name
):
    """The control that makes the four cases above mean something.

    A guard that refused these requests for ANY reason — a malformed body, a wrong
    token, an unreachable route — would produce a non-2xx and satisfy a test that
    only checked for one. Here the identical request runs with no durable layer
    armed at all, and every one returns 2xx. So in the test above the header check
    passed, the handler reached the write, and the refusal came from the second
    layer and nowhere else.
    """
    needs_run = name in {"create_run", "override"}
    exp = _make(runs=("run A",) if needs_run else ())
    run_id = exp.sorted_runs()[0].id if needs_run else None
    client = _client()
    record_token = _record_etag(client)
    run_token = _run_etag(client, run_id) if needs_run else None

    if name == "rename":
        response = client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": "a title no writer landed"},
            headers={"If-Match": record_token},
        )
    elif name == "correct":
        response = client.post(
            f"/api/experiments/{EXPERIMENT_ID}/edit",
            json={"confirmed_by_user": True, "answers": {ANSWERED_URI: SHA_B}},
            headers={"If-Match": record_token},
        )
    elif name == "create_run":
        response = client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs",
            json={"label": "a run no writer landed"},
            headers={"If-Match": record_token},
        )
    else:
        response = client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{run_id}/overrides",
            json={
                "confirmed_by_user": True,
                "address": OVERRIDE_ADDRESS,
                "payload": _confirmed(SHA_B),
            },
            headers={"If-Match": run_token},
        )

    assert 200 <= response.status_code < 300, response.text


def test_the_durable_refusal_of_a_DISCARD_free_record_leaves_the_ARTIFACTS_alone(
    workspace, monkeypatch
):
    """The one call site whose "NOTHING WAS WRITTEN" is qualified, asserted.

    ``_save_versioned``'s docstring states per layer what survives a durable
    refusal, and names ``post_export`` as the exception: it writes the official
    record and its evidence sidecar BEFORE calling the save, so those two files
    remain on disk while the record's own state does not move. That is the
    half-written shape ``_published_stems`` exists to catch, and it is asserted
    here rather than left as prose: the pair IS on disk, the state does NOT claim
    it, and the record is therefore not exportable-clean but also not destroyed.
    """
    exp = _make()
    persisted_before = copy.deepcopy(exp.to_state())
    client = _client()
    token = _record_etag(client)
    _durable_conflict(monkeypatch, persisted_before)

    response = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/export", headers={"If-Match": token}
    )

    assert response.status_code == 412, response.text
    assert response.json()["error"] == "stale_write", response.text

    _disarm(monkeypatch)
    after = _persisted()
    published = sorted(
        path.name for path in after.records_dir.iterdir() if path.is_file()
    ) if after.records_dir.is_dir() else []
    assert len(published) == 2, published
    assert after.record_id is None, (
        "the state claims a record id the durable layer refused to persist"
    )
    # And the disk-not-only-state check sees them, which is the whole reason it
    # asks the disk: a discard decided from state alone would remove this pair.
    assert routes._published_stems(after), "the orphan pair is invisible to the guard"


# =============================================================================
# D. A STALE MCP WRITE, LOSING A RACE TO A BROWSER
# =============================================================================


def test_a_stale_MCP_write_loses_the_race_and_is_told_the_typed_refusal(
    workspace, monkeypatch
):
    """An agent working from a stale read must lose, not the scientist's edit.

    ``mcp/tools.py`` states exactly that property, and ``mcp/policy.py`` refuses to
    import if any mutating operation lacks ``requires_if_match``. Both are
    satisfied by the header being PRESENT; neither can see what happens when the
    header is a token another writer has just invalidated.
    ``test_mcp_if_match_wildcard`` drives that SEQUENTIALLY (read, write, replay).
    Here the invalidating write is still inside the record lock when the agent's
    request arrives, which is the arrangement the promise is actually about.

    Nothing is asserted about the wildcard here: the MCP client refuses ``*`` while
    it is building the request, and that refusal has its own file.
    """
    from isaac_api.mcp.client import AsgiApiClient

    _make()
    app = _app()
    client = _client(app)
    agent = AsgiApiClient(app)
    token = _record_etag(client)

    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    def _agent_write():
        return asyncio.run(
            agent.call(
                "create_run",
                path_params={"experiment_id": EXPERIMENT_ID},
                if_match=token,
                json_body={"label": "a run the agent never landed"},
            )
        )

    scientist, agent_result = _ordered_race(
        interleave,
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": "the scientist's edit"},
            headers={"If-Match": token},
        ),
        _agent_write,
    )

    assert scientist.status_code == 200, scientist.text
    assert agent_result.status == 412, agent_result.body
    assert agent_result.body["error"] == "stale_write", agent_result.body
    assert agent_result.body["experiment_id"] == EXPERIMENT_ID, agent_result.body

    after = _persisted()
    assert after.title == "the scientist's edit", "the agent overwrote the scientist"
    assert list(after.runs) == [], "a run the agent was refused was created anyway"
    assert "the agent never landed" not in _state_json(after)


# =============================================================================
# E. WHAT A REVISION ROW CONTAINS WHEN AN EDIT IS QUEUED BEHIND THE SUBMIT
# =============================================================================


def test_a_revision_snapshots_what_was_SUBMITTED_not_what_the_record_became(
    armed, monkeypatch
):
    """A revision is an immutable snapshot of a declaration, so its content matters.

    ``test_lifecycle_concurrency`` proves that two concurrent submits create
    exactly ONE revision row. What no test asks is what that row CONTAINS when a
    write is queued behind the submit — and a revision that captured a change the
    submitter never saw would attribute to a person a document they did not
    declare, in an append-only table nothing can correct.

    The editor uses ``If-Match: *`` deliberately: with a real token it would be
    refused 412 at the precondition (the submit moved the record) and would never
    land, so nothing would be queued behind the revision at all and the test would
    prove nothing.
    """
    db = FakeSubmissionConnection()
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(db))

    exp = _make()
    rev_at_submit = exp.rev
    client = _client()
    token = _record_etag(client)

    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, routes.submissions, "blocker_report")

    submit, rename = _ordered_race(
        interleave,
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/submit", headers={"If-Match": token}
        ),
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": "renamed after the declaration"},
            headers={"If-Match": "*"},
        ),
    )

    assert submit.status_code == 200, submit.text
    assert rename.status_code == 200, rename.text
    assert len(db.revisions) == 1, db.revisions
    assert len(db.submissions) == 1, db.submissions

    revision = db.revisions[0]
    assert revision["experiment_id"] == EXPERIMENT_ID, revision
    assert revision["subject"] == ACTOR, revision
    assert revision["experiment_rev"] >= rev_at_submit, revision
    assert "renamed after the declaration" not in json.dumps(revision["state"]), (
        "the revision captured a rename the submitter never declared"
    )
    assert "renamed after the declaration" not in json.dumps(
        [db.revisions, db.run_revisions, db.submissions, db.submission_runs, db.changes]
    ), "the queued edit reached a durable history row"

    after = _persisted()
    assert after.title == "renamed after the declaration"
    assert after.rev > revision["experiment_rev"], (
        "the queued edit did not advance the record past the revision it follows"
    )
