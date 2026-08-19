"""Multi-client concurrency over the SCIENTIFIC LIFECYCLE — runs, submission, decisions.

WHY THIS FILE EXISTS, AND WHAT IT IS NOT A SECOND COPY OF
=========================================================

``test_handler_concurrency.py`` proves the compare-and-swap under
``ws.record_lock`` for the two RECORD-level mutations that existed when it was
written (``/answers`` and ``/edit``), driven through the real app by real threads.
Everything the lifecycle added since — creating and editing and removing RUNS,
overriding and reverting an inherited value, SUBMITTING, and recording a human
DECISION about an evidence conflict — has no concurrency coverage at all.
``test_run_row_parity.py`` is explicit that its own "concurrent" case is
*sequential, two real connections, not concurrent*, and nothing else races these
routes.

That gap matters more here than it did there, because these operations carry
**three different validators over one document**:

* the RECORD's ``ETag`` — ``/runs`` (create), ``/runs/{id}/remove``, ``/submit``,
  ``/conflicts/resolve``;
* the RUN's own ``ETag`` — ``PATCH /runs/{id}``, ``/overrides``,
  ``/overrides/clear``;
* and, for a submission, a durable uniqueness constraint in a database this
  process does not hold a lock over.

Two of those can be current at the same moment while the third is not, so "the
loser is refused" is not one property, it is several, and each refusal leaves a
DIFFERENT amount of state behind: a refused run edit leaves nothing, a refused
removal may be refused because the run was PUBLISHED a moment earlier, and a
refused submission may be refused *after* official records were written to disk.

THE BAR EVERY TEST HERE MEETS
=============================

For every REFUSED write this file asserts the **authoritative state afterwards**,
never only the status code:

* the specific ``error`` string (a bare non-2xx assertion is satisfied by a
  request FastAPI rejected before it reached any guard, which proves nothing);
* the stored document, read back from the workspace — never the response body;
* the version tokens: the record's ``rev`` AND every run's ``rev``/``generation``,
  because a refused write that silently advanced a sibling's version is the defect
  ``save_versioned``'s rollback loop exists to prevent;
* the published artifacts on disk — the official record AND its evidence sidecar,
  by filename — for anything that can publish;
* the durable rows: submissions, revisions, run revisions and change rows;
* and, where a value could have leaked, that the loser's sentinel appears NOWHERE
  in the serialised state.

DETERMINISM: NO TEST HERE DEPENDS ON THREAD SCHEDULING
======================================================

Two devices, both borrowed from ``test_handler_concurrency`` rather than
reinvented, and neither is a sleep:

* :class:`~test_handler_concurrency._LockRendezvous` — installed on
  ``ws.record_lock``, it holds the first two arrivals at the target's lock until
  BOTH have arrived, then lets them acquire normally. That guarantees the property
  every assertion below rests on: *whatever each request loaded before it reached
  the lock, it loaded before either request could hold the lock.* A handler that
  read its precondition subject outside the lock therefore fails here on EVERY
  run, not one in a thousand.
* ``threading.Event`` for the two tests that suspend a write mid-flight. Their
  timeouts are safety nets whose expiry is itself asserted NOT to have happened,
  so a build that serialised these requests would fail this file loudly rather
  than pass it vacuously.

WHERE A RACE CAN LEGITIMATELY GO EITHER WAY — and most of these can — the test
asserts the invariant that holds in BOTH orderings and its docstring names the
orderings and why each is legal. No test pins an ordering the scheduler chooses.

WHAT THIS FILE CANNOT PROVE
===========================

* **Nothing here is a multi-PROCESS race.** ``ws.record_lock`` is in-process, and
  the deployed server is single-process uvicorn, so this is the concurrency the
  product actually has. The durable compare-and-swap that guards the *other* case
  (``experiment_repository.DurableWriteConflict``) is reachable only against a
  database, and is covered by ``test_experiment_repository.py``. Where a branch is
  only reachable that way, the test below says so rather than pretending.
* **Nothing here connects to PostgreSQL.** Submissions run against
  ``submission_fake.FakeSubmissionConnection``, the established in-process double,
  so the real ``db_write`` transaction machinery is exercised and only the server
  is fake. Experiments themselves use the filesystem repository, as everywhere
  else in this package (``PGHOST`` is deleted by the fixture).
* Everything is synthetic. No file outside the ``tmp_path`` workspace is read or
  written.
"""

from __future__ import annotations

import copy
import json
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.conflict_resolution as cr
import isaac_api.identity as identity
import isaac_api.routes as routes
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws
from isaac_records.models import field_value, user_confirmation

from conftest import client_ws, tutorial_client
from submission_fake import FakeSubmissionConnection, fake_store

# The interleaving seam and the thread runner are IMPORTED, not re-declared. A
# second copy of `_LockRendezvous` would be a second definition of what "these two
# requests overlapped" means, free to drift from the one `test_handler_concurrency`
# maintains — and its `assert_scoped` half exists precisely because a silently
# unforwarded scope makes every test in a file like this stop pinning anything.
from test_handler_concurrency import (  # noqa: E402
    _EVENT_TIMEOUT_S,
    _LockRendezvous,
    _outcome,
    _race,
)

# The draft split is imported for the same reason: it uses the APPLICATION's own
# `field_level` / `block_level` classifiers to divide the committed export-ready
# seed into its record-level and run-level halves. A hand-written list here would
# be a third copy of the split and could pass while the product's composition was
# wrong.
from test_export_fan_out import _split_full_draft  # noqa: E402

#: A run-level official field path, and the address most run tests write at.
RUN_FIELD = "context.temperature_K"
#: A second run-level path, for the test that needs two writers not to collide by
#: address alone.
RUN_FIELD_2 = "context.environment"
#: A record-level official field path that is overridable on a run.
OVERRIDE_ADDRESS = "field:sample.material.name"
#: A record-level official field path used for the record-scope conflict fixture.
RECORD_CONFLICT_ADDRESS = "sample.material.formula"

#: Two sentinels the system can never invent, one per writer. Distinct enough that
#: `assert <sentinel> not in json.dumps(state)` is a real statement.
VALUE_A = 4711
VALUE_B = 4712
VALUE_C = 4713

EXPERIMENT_ID = "01LIFECYCLECONCURRENCY0001"
ACTOR = "ada.lovelace"
OTHER_ACTOR = "grace.hopper"


# =============================================================================
# fixtures
# =============================================================================


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The real app over a throwaway workspace, in a worked-example session.

    Same idiom as ``test_handler_concurrency`` and ``test_run_api``: the run and
    conflict operations are all reachable in a worked-example scope, so these tests
    use one. The SUBMIT tests deliberately do not — a worked-example session is
    never submitted, by design — and take the ordinary-scope fixtures below.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    """An ordinary-scope deployment that CAN attribute a submission.

    The two seams are exactly the ones ``test_submission.py`` uses, for the reasons
    its module docstring gives: ``FixtureEdgeVerifier`` reads its subject from the
    PROCESS ENVIRONMENT and never from a request, and it mints
    ``trust_basis="test_fixture"`` so every row it causes is permanently labelled.
    """
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
def wired(monkeypatch, db):
    """Point the submit route's store factory at the connection double."""
    store = fake_store(db)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    return store


@pytest.fixture()
def submit_client(armed, wired):
    """A plain ``TestClient`` — no worked-example header, so ``scope`` is ``None``.

    ``raise_server_exceptions=False`` matches ``test_submission``: a handler that
    raised would otherwise kill the racing thread and be reported as "the thread
    did not finish", which names the wrong problem. Here it surfaces as a 500
    response and every assertion below states the code it expects.
    """
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


# =============================================================================
# helpers — reads used for ASSERTIONS ONLY, never to perform a mutation
# =============================================================================


def _record_etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, experiment_id: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _versions(exp) -> dict:
    """Every version token this record carries — the record's and every run's.

    Returned as one mapping so a test can assert "nothing moved" or "exactly this
    moved" in a single comparison, including ``generation``, which no legitimate
    operation in this file ever changes.
    """
    return {
        "record": exp.version_token(),
        "runs": {
            run.id: {"version": run.version_token(), "generation": run.generation}
            for run in exp.sorted_runs()
        },
    }


def _run_field(exp, run_id: str, path: str):
    """The stored value at one run-level path, or ``None`` if the run has none."""
    run = exp.get_run(run_id)
    assert run is not None, f"{run_id} is gone"
    fields = (run.draft or {}).get("fields") or {}
    entry = fields.get(path)
    return entry.get("value") if isinstance(entry, dict) else None


def _state_json(exp) -> str:
    """The whole persisted state as text — used to prove a value is nowhere in it."""
    return json.dumps(exp.to_state())


def _artifacts(exp) -> set[str]:
    """Every file in this record's records dir, by name. Absent dir -> empty set."""
    records_dir = exp.records_dir
    if not records_dir.is_dir():
        return set()
    return {path.name for path in records_dir.iterdir()}


def _assert_ordinary_scope(rendezvous: _LockRendezvous, experiment_id: str) -> None:
    """The ordinary-scope counterpart of ``_LockRendezvous.assert_scoped``.

    ``assert_scoped`` asserts a worked-example session id; a submit runs with
    ``scope is None`` and the real key is ``"/<id>"``. Both halves are checked for
    the same reason that helper checks both: the scope the handler PASSED and the
    key the real lock COMPUTED. Two threads on two different keys do not serialise,
    and every race below would silently stop being a race.
    """
    assert rendezvous.scopes, "the seam saw no acquisition of the target's lock"
    assert set(rendezvous.scopes) == {None}, (
        f"an ordinary-scope request passed scope(s) {sorted(map(str, set(rendezvous.scopes)))}"
    )
    assert set(rendezvous.lock_keys) == {f"/{experiment_id}"}, rendezvous.lock_keys


def _assert_raced(rendezvous: _LockRendezvous, session_id: str | None, experiment_id: str) -> None:
    """Both requests really overlapped, on one scope-qualified lock key."""
    assert rendezvous.arrivals == 2, (
        "both requests must have reached the record lock — the race did not happen"
    )
    assert not rendezvous.timed_out, (
        "the two requests did not overlap; this run proved nothing about concurrency"
    )
    if session_id is None:
        _assert_ordinary_scope(rendezvous, experiment_id)
    else:
        rendezvous.assert_scoped(session_id)


def _confirmed(value, *, question: str = "What value?", at: str = "2026-01-01T00:00:00Z") -> dict:
    """A ``verified`` draft envelope whose single evidence entry asserts ``value``.

    Built through the truth core's own constructors, so a fixture conflict is the
    same shape the answers, edit and run-edit routes append rather than a
    hand-written literal that could drift from them.
    """
    return field_value(
        value, status="verified", evidence=[user_confirmation(question, value, at)]
    )


def _competing(*answers, question: str = "What value?") -> dict:
    """A draft envelope whose evidence asserts each of ``answers`` — a conflict."""
    return {
        "value": answers[0],
        "status": "verified",
        "evidence": [
            user_confirmation(question, answer, "2026-01-01T00:00:00Z")
            for answer in answers
        ],
    }


# --- fixture builders ---------------------------------------------------------


def _experiment_with_runs(store, *, labels: tuple[str, ...], run_draft=None, experiment_id=None):
    """A record with N runs, persisted in ``store``'s scope, and reloaded.

    The record-level half of the committed export-ready seed goes on the record and
    the run-level half on every run, so each run is a real export unit — which is
    what makes the submission and removal races below reach the code they claim to.
    """
    experiment_draft, default_run_draft = _split_full_draft()
    exp = store.create_experiment(
        "Lifecycle concurrency fixture",
        {"kind": "synthetic"},
        experiment_draft,
        **({"id": experiment_id} if experiment_id else {}),
    )
    for label in labels:
        exp.add_run(
            label=label,
            draft=copy.deepcopy(default_run_draft if run_draft is None else run_draft),
        )
    exp.save_versioned()
    return store.load_experiment(exp.id)


# =============================================================================
# 1. Two writers on ONE run, holding ONE run validator
# =============================================================================


def test_two_edits_of_one_run_with_one_token_leave_exactly_the_winner(client, monkeypatch):
    """Two ``PATCH /runs/{id}`` writers, one run ``ETag``: one 200, one 412
    ``stale_write``, the run's ``rev`` advances EXACTLY once, and the loser's value
    is nowhere in the persisted state.

    LEGITIMATE ORDERINGS: either writer may win — the scheduler decides which
    reaches the lock first — so nothing below names a winner. What is NOT
    ordering-dependent is that exactly one wins, and that the stored value is the
    winner's own.

    This is the test a handler that resolved ``exp.get_run(run_id)`` OUTSIDE
    ``record_lock`` cannot pass: both writers would then hold a pre-mutation run,
    both would find their validator current, and the second write would silently
    erase the first.

    The 412 body is asserted in full because a RUN's refusal has to name TWO ids.
    Filing the run id under ``experiment_id`` would be a false statement in the one
    body a client reads when its write is refused, and only this assertion would
    catch it.
    """
    store = client_ws(client)
    exp = _experiment_with_runs(store, labels=("Run A",))
    eid, rid = exp.id, exp.runs[0].id
    token = _run_etag(client, eid, rid)
    before = store.load_experiment(eid)
    before_versions = _versions(before)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.patch(
            f"/api/experiments/{eid}/runs/{rid}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_A}},
            headers={"If-Match": token},
        ),
        lambda: client.patch(
            f"/api/experiments/{eid}/runs/{rid}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_B}},
            headers={"If-Match": token},
        ),
    ])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    codes = sorted(response.status_code for response in responses)
    assert codes == [200, 412], (
        f"exactly one writer may win the run's compare-and-swap, got {codes}: "
        f"{_outcome(responses)}"
    )

    loser = next(response for response in responses if response.status_code == 412)
    body = loser.json()
    assert body["error"] == "stale_write"
    assert body["experiment_id"] == eid
    assert body["run_id"] == rid, (
        "a refused RUN write must name the run it was addressed to; filing the run "
        "id under experiment_id would be a false statement"
    )
    assert "experiment_id" in body and body["experiment_id"] != rid

    after = store.load_experiment(eid)
    run_before = before_versions["runs"][rid]["version"]
    assert after.get_run(rid).rev == before.get_run(rid).rev + 1, (
        "the run's rev must advance exactly once, not twice"
    )
    assert after.get_run(rid).generation == before.get_run(rid).generation
    assert loser.headers["ETag"] == f'"{after.get_run(rid).version_token()}"', (
        "the 412 must echo the RUN's CURRENT validator so a client refreshes in one hop"
    )
    assert run_before != after.get_run(rid).version_token()

    # ``responses`` keeps submission order, so index 0 is the VALUE_A writer.
    won, lost = (
        (VALUE_A, VALUE_B) if responses[0].status_code == 200 else (VALUE_B, VALUE_A)
    )
    assert _run_field(after, rid, RUN_FIELD) == won, "the winner's change was not persisted"
    assert str(lost) not in _state_json(after), (
        "the rejected writer's value reached the record — this is a lost update"
    )


# =============================================================================
# 2. Two writers on TWO DIFFERENT runs of one record
# =============================================================================


def test_concurrent_edits_of_two_runs_both_land_and_neither_disturbs_the_other(
    client, monkeypatch
):
    """Two ``PATCH`` writers on DIFFERENT runs, each holding its OWN run's current
    validator: BOTH succeed, each run stores exactly its own writer's value, and
    every OTHER run's ``rev`` and ``generation`` are untouched.

    LEGITIMATE ORDERINGS: both. The two runs' validators are independent, so
    neither ordering may refuse either request — that is the whole point of a
    per-run validator over a per-record lock. What the lock has to guarantee is
    that the SECOND writer loads the document the first one saved; without it the
    second save would drop the first run's edit, because both runs live in ONE
    state file.

    A third, untouched run is present precisely so "neither disturbs the other" is
    a statement about a bystander too, and not only about the two participants.
    """
    store = client_ws(client)
    exp = _experiment_with_runs(store, labels=("Run A", "Run B", "Run C"))
    eid = exp.id
    run_a, run_b, run_c = (run.id for run in exp.sorted_runs())
    token_a = _run_etag(client, eid, run_a)
    token_b = _run_etag(client, eid, run_b)
    before = store.load_experiment(eid)
    before_versions = _versions(before)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.patch(
            f"/api/experiments/{eid}/runs/{run_a}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_A}},
            headers={"If-Match": token_a},
        ),
        lambda: client.patch(
            f"/api/experiments/{eid}/runs/{run_b}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_B}},
            headers={"If-Match": token_b},
        ),
    ])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    assert [response.status_code for response in responses] == [200, 200], (
        f"independent runs must not refuse each other: {_outcome(responses)}"
    )

    after = store.load_experiment(eid)
    assert _run_field(after, run_a, RUN_FIELD) == VALUE_A, (
        "run A's edit was lost — the second writer saved a document that predated it"
    )
    assert _run_field(after, run_b, RUN_FIELD) == VALUE_B, "run B's edit was lost"
    # The bystander still holds the SEED value — it was never `None`, so asserting
    # absence here would have passed for the wrong reason on an empty run.
    assert _run_field(after, run_c, RUN_FIELD) == _run_field(before, run_c, RUN_FIELD)
    assert after.get_run(run_c).draft == before.get_run(run_c).draft

    after_versions = _versions(after)
    assert after_versions["runs"][run_c] == before_versions["runs"][run_c], (
        "the bystander run's version moved; a write to one run must not bump another"
    )
    for run_id in (run_a, run_b):
        assert (
            after_versions["runs"][run_id]["generation"]
            == before_versions["runs"][run_id]["generation"]
        ), "no operation here may mint a new run generation"
        assert after.get_run(run_id).rev == before.get_run(run_id).rev + 1, (
            "each edited run advances exactly one revision"
        )
    assert after.rev == before.rev + 2, (
        "two accepted writes are exactly two record revisions"
    )


# =============================================================================
# 3. Overriding an inherited value vs reverting to inherited, same address
# =============================================================================


def test_override_and_revert_to_inherited_race_leaves_exactly_the_winners_outcome(
    client, monkeypatch
):
    """One run already holds an override at one address. A re-override with a NEW
    payload and a revert-to-inherited race, both holding the run's current
    validator: exactly one 200 and one 412, and the stored document is exactly what
    the winner asked for.

    LEGITIMATE ORDERINGS, and they end in OPPOSITE states, which is why the
    assertion is a branch rather than a single expected document:

    * the override wins -> the address carries an override whose payload is the
      NEW value, and the clear is refused 412 with nothing removed;
    * the clear wins -> the address carries NO override at all and the run
      inherits again, and the override is refused 412 with nothing recorded.

    Neither ordering may leave the address carrying the ORIGINAL payload: that
    would mean the winner's write was applied and then silently rolled back. And
    neither may leave the loser's effect present, which is what the second half of
    each branch asserts.

    THE FIXTURE STARTS WITH AN OVERRIDE ON PURPOSE. Starting without one makes the
    race trivially non-exclusive — a clear at an address carrying no override is a
    documented no-op that writes nothing and does not advance the run, so the
    override's validator would still be current afterwards and BOTH requests would
    succeed. That is correct behaviour and it is a different test; here the clear
    has something to remove, so the two writes genuinely contend.
    """
    store = client_ws(client)
    exp = _experiment_with_runs(store, labels=("Run A",))
    eid, rid = exp.id, exp.runs[0].id

    original = client.post(
        f"/api/experiments/{eid}/runs/{rid}/overrides",
        json={
            "confirmed_by_user": True,
            "address": OVERRIDE_ADDRESS,
            "payload": _confirmed("ORIGINAL-OVERRIDE"),
        },
        headers={"If-Match": _run_etag(client, eid, rid)},
    )
    assert original.status_code == 200, original.text

    token = _run_etag(client, eid, rid)
    before = store.load_experiment(eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{rid}/overrides",
            json={
                "confirmed_by_user": True,
                "address": OVERRIDE_ADDRESS,
                "payload": _confirmed("REPLACEMENT-OVERRIDE"),
            },
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{rid}/overrides/clear",
            json={"confirmed_by_user": True, "address": OVERRIDE_ADDRESS},
            headers={"If-Match": token},
        ),
    ])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    override_response, clear_response = responses
    assert sorted(r.status_code for r in responses) == [200, 412], (
        f"exactly one may win: {_outcome(responses)}"
    )

    after = store.load_experiment(eid)
    # `Run.overrides` is a mapping address -> Override; the ABSENCE of a key is the
    # inheritance, so "the run inherits again" is asserted as a missing key.
    stored_overrides = after.get_run(rid).overrides
    state = _state_json(after)
    assert after.get_run(rid).rev == before.get_run(rid).rev + 1, (
        "exactly one accepted write is exactly one run revision"
    )

    if override_response.status_code == 200:
        assert clear_response.json()["error"] == "stale_write"
        assert clear_response.json()["run_id"] == rid
        assert OVERRIDE_ADDRESS in stored_overrides, (
            "the override won, so the address must still carry one"
        )
        assert stored_overrides[OVERRIDE_ADDRESS].payload["value"] == "REPLACEMENT-OVERRIDE"
        assert "ORIGINAL-OVERRIDE" not in state, (
            "the winner's payload replaced the original — the original must be gone"
        )
        assert override_response.json()["override"]["address"] == OVERRIDE_ADDRESS
    else:
        assert override_response.json()["error"] == "stale_write"
        assert override_response.json()["run_id"] == rid
        assert clear_response.json()["cleared"] is True
        assert OVERRIDE_ADDRESS not in stored_overrides, (
            "the clear won, so the run must inherit again — no override may remain"
        )
        assert "REPLACEMENT-OVERRIDE" not in state, (
            "the refused override's payload reached the record"
        )
        assert "ORIGINAL-OVERRIDE" not in state


# =============================================================================
# 4. Removing a run while that same run is being edited
# =============================================================================


def test_removing_a_run_while_it_is_being_edited(client, monkeypatch):
    """``POST /runs/{id}/remove`` (the RECORD's validator) races ``PATCH
    /runs/{id}`` (the RUN's validator) on the SAME run. The two validators are
    different objects and BOTH are current when the race starts, so this is the
    case where "the loser is refused" is not one rule but two.

    LEGITIMATE ORDERINGS, and the loser's refusal is a DIFFERENT status in each:

    * the removal wins -> the run is gone, and the edit is refused **404
      run_not_found** (not 412): the run's existence is resolved inside the lock,
      before any precondition, so the edit is told the truth about the run rather
      than sent to re-read a version for something that no longer exists;
    * the edit wins -> the record moved, so the removal's RECORD validator is
      stale and it is refused **412 stale_write**, and the run survives carrying
      the edit.

    In BOTH orderings the edited value must be present exactly when the run is, and
    absent from the whole document when it is not — a removal that dropped the run
    while leaving its edit behind, or an edit that resurrected a removed run, are
    both states this asserts against.
    """
    store = client_ws(client)
    exp = _experiment_with_runs(store, labels=("Run A", "Run B"))
    eid = exp.id
    run_a, run_b = (run.id for run in exp.sorted_runs())
    record_token = _record_etag(client, eid)
    run_token = _run_etag(client, eid, run_a)
    before = store.load_experiment(eid)
    before_versions = _versions(before)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    remove, edit = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{run_a}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": record_token},
        ),
        lambda: client.patch(
            f"/api/experiments/{eid}/runs/{run_a}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_A}},
            headers={"If-Match": run_token},
        ),
    ])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    after = store.load_experiment(eid)
    state = _state_json(after)
    # The bystander run is untouched whichever way the race went.
    assert _versions(after)["runs"][run_b] == before_versions["runs"][run_b]

    if remove.status_code == 200:
        assert edit.status_code == 404, _outcome([remove, edit])
        edit_body = edit.json()
        assert edit_body["error"] == "run_not_found"
        assert edit_body["experiment_id"] == eid
        assert edit_body["id"] == run_a
        assert after.get_run(run_a) is None, "the removal won, so the run must be gone"
        assert {run.id for run in after.runs} == {run_b}
        assert str(VALUE_A) not in state, (
            "the refused edit's value survived the removal of the run it addressed"
        )
        assert remove.json()["removed_run_id"] == run_a
        assert remove.json()["remaining_run_count"] == 1
    else:
        assert edit.status_code == 200, _outcome([remove, edit])
        assert remove.status_code == 412, _outcome([remove, edit])
        remove_body = remove.json()
        assert remove_body["error"] == "stale_write"
        assert remove_body["experiment_id"] == eid
        assert "run_id" not in remove_body, (
            "the removal's validator is the RECORD's, so its refusal names the record"
        )
        assert after.get_run(run_a) is not None, "the edit won, so the run must survive"
        assert _run_field(after, run_a, RUN_FIELD) == VALUE_A
        assert remove.headers["ETag"] == after.etag()


# =============================================================================
# 5. Removing a run while the record is being SUBMITTED
# =============================================================================


def test_removing_a_run_while_the_record_is_being_submitted(
    submit_client, armed, db, monkeypatch
):
    """The two most destructive operations, racing on one record validator.

    LEGITIMATE ORDERINGS, and each leaves an entirely different disk:

    * **the submission wins** -> every unit is published, so the run now keeps an
      official record AND an evidence sidecar. The removal is then refused **409
      ``run_exported``** — NOT 412 — because the published check is deliberately
      ordered before the precondition: a run that keeps an immutable artifact
      claimed must be told why it cannot be removed, not sent to re-read a version.
      The run survives, the artifacts survive, and exactly one submission row
      names both units.
    * **the removal wins** -> the record moved, the submission's validator is
      stale, and it is refused **412 stale_write** before anything is published.
      NOTHING is on disk: no record, no sidecar, no submission row, no revision
      row.

    The invariant that holds in both, and the reason this test asserts artifacts
    rather than status codes: **the loser never erases the winner's outcome.** A
    removal that succeeded after publication would leave an immutable published
    pair claimed by no unit, which the next export prunes — deleting a published
    official record at a distance with no confirmation. That is the failure
    ``_run_published_stem`` exists to prevent and this is the concurrent case of it.
    """
    exp = _experiment_with_runs(ws, labels=("run A", "run B"), experiment_id=EXPERIMENT_ID)
    eid = exp.id
    run_a, run_b = (run.id for run in exp.sorted_runs())
    token = _record_etag(submit_client, eid)
    assert _artifacts(ws.load_experiment(eid)) == set(), "the fixture must start unpublished"
    rendezvous = _LockRendezvous(monkeypatch, eid)

    remove, submit = _race([
        lambda: submit_client.post(
            f"/api/experiments/{eid}/runs/{run_a}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": token},
        ),
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        ),
    ])

    _assert_raced(rendezvous, None, eid)
    after = ws.load_experiment(eid)
    artifacts = _artifacts(after)

    if submit.status_code == 200:
        assert remove.status_code == 409, _outcome([remove, submit])
        body = remove.json()
        assert body["error"] == "run_exported"
        assert body["id"] == run_a
        assert body["record_stem"] == after.get_run(run_a).record_id
        assert "Nothing was written." in body["message"]

        assert after.get_run(run_a) is not None, (
            "the submission won, so the run it published must still be there"
        )
        assert {run.id for run in after.runs} == {run_a, run_b}
        published = {entry["record_id"] for entry in submit.json()["records"]}
        assert len(published) == 2, submit.json()["records"]
        for record_id in published:
            assert f"{record_id}.json" in artifacts, artifacts
            assert f"{record_id}.evidence.json" in artifacts, artifacts
        assert artifacts == {
            name for record_id in published
            for name in (f"{record_id}.json", f"{record_id}.evidence.json")
        }
        assert len(db.submissions) == 1, db.submissions
        assert db.submissions[0]["unit_count"] == 2
        assert {row["unit_id"] for row in db.submission_runs} == published
    else:
        assert remove.status_code == 200, _outcome([remove, submit])
        assert submit.status_code == 412, _outcome([remove, submit])
        body = submit.json()
        assert body["error"] == "stale_write"
        assert body["experiment_id"] == eid
        assert body["current_version"] == after.version_token()

        assert after.get_run(run_a) is None, "the removal won, so the run must be gone"
        assert {run.id for run in after.runs} == {run_b}
        assert artifacts == set(), (
            "the refused submission published artifacts before it was refused — a "
            "record refused on its PRECONDITION must write nothing at all"
        )
        assert db.submissions == [], db.submissions
        assert db.revisions == [], db.revisions
        assert db.submission_runs == [], db.submission_runs
        assert remove.json()["removed_run_id"] == run_a


# =============================================================================
# 6. Submit double-click
# =============================================================================


def test_submit_double_click_on_an_unpublished_record_publishes_once(
    submit_client, armed, db, monkeypatch
):
    """The same submission issued TWICE, concurrently, on a record that has not
    been published: one 200, one 412, ONE set of official records on disk, and ONE
    durable submission.

    LEGITIMATE ORDERINGS: either request may be the one that publishes. Neither may
    publish a second time — publication advances the record, so the loser's
    validator is stale and it is refused before it reaches materialisation.

    THE FILENAMES ARE COMPARED, not just counted. A second publication would mint
    a second ``record_id`` per unit and leave FOUR artifacts for two runs, which a
    count of "some records exist" would not notice.
    """
    exp = _experiment_with_runs(ws, labels=("run A", "run B"), experiment_id=EXPERIMENT_ID)
    eid = exp.id
    token = _record_etag(submit_client, eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    first, second = _race([
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        ),
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        ),
    ])

    _assert_raced(rendezvous, None, eid)
    codes = sorted(r.status_code for r in [first, second])
    assert codes == [200, 412], _outcome([first, second])
    winner = first if first.status_code == 200 else second
    loser = second if first.status_code == 200 else first
    assert loser.json()["error"] == "stale_write"

    after = ws.load_experiment(eid)
    published = {entry["record_id"] for entry in winner.json()["records"]}
    assert len(published) == 2
    assert _artifacts(after) == {
        name for record_id in published
        for name in (f"{record_id}.json", f"{record_id}.evidence.json")
    }, "a second publication left extra artifacts"
    assert len(db.submissions) == 1, db.submissions
    assert db.submissions[0]["submission_id"] == winner.json()["submission_id"]
    assert len(db.revisions) == 1, db.revisions
    assert len(db.submission_runs) == 2, db.submission_runs


def test_submit_double_click_on_a_published_record_records_exactly_one_submission(
    submit_client, armed, db, monkeypatch
):
    """The double-click that actually reaches the durable uniqueness constraint.

    A record whose units are ALREADY published is the case where a submit changes
    no state at all — it publishes nothing and never calls ``save_versioned`` — so
    the record's validator stays current and BOTH concurrent requests get past
    ``If-Match``. The only thing between one submission and two is the store's own
    ``ON CONFLICT`` behaviour, which is exactly what this asserts.

    LEGITIMATE ORDERINGS: either request may be the one recorded. The other is
    refused **409 ``already_submitted``** and its body echoes the submission that
    IS on record — the same submission id, so a client cannot be told a different
    one exists.

    THE ARTIFACT BYTES ARE COMPARED before and after, because "no duplicate
    publication" has to mean the files did not change, not merely that their names
    did not.
    """
    exp = _experiment_with_runs(ws, labels=("run A", "run B"), experiment_id=EXPERIMENT_ID)
    eid = exp.id
    export = submit_client.post(
        f"/api/experiments/{eid}/export", headers={"If-Match": _record_etag(submit_client, eid)}
    )
    assert export.status_code == 200, export.text
    published_before = {
        path.name: path.read_bytes()
        for path in ws.load_experiment(eid).records_dir.iterdir()
    }
    assert len(published_before) == 4, sorted(published_before)

    token = _record_etag(submit_client, eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    first, second = _race([
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        ),
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        ),
    ])

    _assert_raced(rendezvous, None, eid)
    codes = sorted(r.status_code for r in [first, second])
    assert codes == [200, 409], _outcome([first, second])
    winner = first if first.status_code == 200 else second
    loser = second if first.status_code == 200 else first

    loser_body = loser.json()
    assert loser_body["error"] == "already_submitted"
    assert loser_body["submission"]["submission_id"] == winner.json()["submission_id"], (
        "the refusal must echo the submission that IS on record"
    )
    assert loser_body["published_record_count"] == 0, loser_body
    assert loser_body["records"] == [], loser_body

    after = ws.load_experiment(eid)
    assert {
        path.name: path.read_bytes() for path in after.records_dir.iterdir()
    } == published_before, (
        "an already-published record was republished — official records are immutable"
    )
    assert winner.json()["published_record_count"] == 0, (
        "submitting an already-exported record publishes nothing"
    )
    assert len(db.submissions) == 1, db.submissions
    assert len(db.revisions) == 1, db.revisions
    assert len(db.submission_runs) == 2, db.submission_runs


# =============================================================================
# 7. Two different scientists submitting the same record at once
# =============================================================================


class _RoundRobinSubjectVerifier:
    """A verifier that hands each request a DIFFERENT subject, from process state.

    WHY THIS DOUBLE EXISTS, AND WHY IT IS NOT A WEAKENING. ``FixtureEdgeVerifier``
    reads one subject from the process ENVIRONMENT, so two concurrent requests in
    one process are necessarily the same person and "two scientists" is
    unreachable through the shipped seam. This double keeps the one property that
    matters — **it never touches the request** (``request`` is typed ``object`` and
    is never read, exactly as ``FixtureEdgeVerifier`` and
    ``UnconfiguredEdgeVerifier`` never read it) — and only changes WHERE in process
    state the subject comes from: a lock-protected iterator instead of one env var.
    Reading a header here, even "only in a test", would rebuild the precise hazard
    Q4 is answered against, so it is not done.

    It is installed by monkeypatching ``identity.edge_trust_verifier`` for ONE
    test. It is never added to ``identity._VERIFIERS``, so no deployment can select
    it, and it mints ``TRUST_BASIS_TEST_FIXTURE`` so any row it caused would say so
    about itself.

    WHICH request gets WHICH subject is decided by arrival order and is therefore
    arbitrary — which is exactly why the test below asserts an ordering-independent
    property rather than naming a winner.
    """

    verifier_id = "test_fixture"

    def __init__(self, subjects):
        self._subjects = list(subjects)
        self._guard = threading.Lock()
        self._index = 0
        #: Every subject actually handed out, so the test can prove both were used.
        self.issued: list[str] = []

    def verify(self, request: object):  # noqa: ARG002 — never read; see docstring
        with self._guard:
            subject = self._subjects[min(self._index, len(self._subjects) - 1)]
            self._index += 1
            self.issued.append(subject)
        return identity.Traversed(
            assertion=identity.EdgeAssertion(
                subject=subject,
                groups=frozenset(),
                verifier_id=self.verifier_id,
                trust_basis=identity.TRUST_BASIS_TEST_FIXTURE,
            )
        )

    def can_attribute(self) -> bool:
        return True


def test_two_scientists_submitting_at_once_record_exactly_one_attributed_submission(
    submit_client, armed, db, monkeypatch
):
    """Two people press Submit on the same finished record at the same moment.

    LEGITIMATE ORDERINGS: either scientist may be the one recorded. The identity is
    resolved per request before either reaches the lock, so which of them wins is
    the scheduler's decision and nothing here names one.

    THE INVARIANT, and it is about attribution rather than about counting: there is
    **exactly one durable submission, it names exactly one of the two, and the
    other's name appears NOWHERE in any durable row.** A submission is a declaration
    by a named person; a race that recorded one row while leaving the loser's name
    on the revision row beside it would attribute a declaration to somebody who did
    not make it. The loser is refused and its body echoes the winner's — including
    the winner's subject, so the loser is told who did submit rather than being left
    to assume it was them.

    The record is published first so that BOTH requests get past ``If-Match`` and
    the contention is over the durable row rather than over the record's version —
    see the previous test for why that is the case where the store is the only
    thing standing between one submission and two.
    """
    verifier = _RoundRobinSubjectVerifier([ACTOR, OTHER_ACTOR])
    monkeypatch.setattr(identity, "edge_trust_verifier", lambda: verifier)

    exp = _experiment_with_runs(ws, labels=("run A",), experiment_id=EXPERIMENT_ID)
    eid = exp.id
    export = submit_client.post(
        f"/api/experiments/{eid}/export", headers={"If-Match": _record_etag(submit_client, eid)}
    )
    assert export.status_code == 200, export.text
    token = _record_etag(submit_client, eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    first, second = _race([
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        ),
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        ),
    ])

    _assert_raced(rendezvous, None, eid)
    assert sorted(verifier.issued) == sorted([ACTOR, OTHER_ACTOR]), (
        f"the two requests were not attributed to two different people: {verifier.issued}"
    )
    assert sorted(r.status_code for r in [first, second]) == [200, 409], (
        _outcome([first, second])
    )
    winner = first if first.status_code == 200 else second
    loser = second if first.status_code == 200 else first

    assert len(db.submissions) == 1, db.submissions
    recorded = db.submissions[0]
    assert recorded["subject"] in (ACTOR, OTHER_ACTOR)
    assert recorded["trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
    assert recorded["subject"] == winner.json()["subject"]

    refused_subject = OTHER_ACTOR if recorded["subject"] == ACTOR else ACTOR
    durable = json.dumps(
        [db.submissions, db.revisions, db.run_revisions, db.changes, db.submission_runs]
    )
    assert refused_subject not in durable, (
        "the refused scientist's name reached a durable row — a submission would be "
        "attributed to somebody who did not make it"
    )
    assert len(db.revisions) == 1, db.revisions
    assert db.revisions[0]["subject"] == recorded["subject"]

    body = loser.json()
    assert body["error"] == "already_submitted"
    assert body["submission"]["subject"] == recorded["subject"], (
        "the refused caller must be told WHO submitted, not left to assume it was them"
    )


# =============================================================================
# 8. An edit arriving while a submit is in flight
# =============================================================================


def test_a_run_edit_arriving_while_a_submit_is_in_flight(
    submit_client, armed, db, monkeypatch
):
    """A scientist is still typing into a run when somebody presses Submit.

    THE EDIT HERE IS ``PATCH /runs/{id}``, NOT ``POST /edit``, and the choice is
    forced rather than preferred. ``/edit`` accepts only the keys
    ``_answers_to_apply_shape`` recognises — an asset uri already stored in the
    RECORD's draft, or ``series`` / ``descriptor`` / ``descriptor_label`` / ``edge``
    — and on a fanned-out record every one of those lives on the RUN's draft, not
    the record's. So a record-level correction is not a thing a fanned-out record
    has (its record-level half carries no assets and no series), and the edit a
    scientist actually issues against such a record is the run edit. The
    record-level correction path racing itself is already covered by
    ``test_handler_concurrency::test_concurrent_edit_same_token_exactly_one_wins``.

    That makes this the most interesting shape in the file: the two requests hold
    DIFFERENT validators — the submission the record's, the edit the run's — and
    both are current when the race starts. Neither refusal comes from the other
    request's validator directly; each comes from the fact that the winner rewrote
    the document the loser's validator described.

    LEGITIMATE ORDERINGS:

    * **the submission wins** -> every unit is published, which stamps
      ``record_id`` onto the run and therefore moves THE RUN's version too (a
      run's authoritative signature includes ``record_id``). The edit is refused
      412 naming the run, and its value is nowhere: not in the record's state, and
      **not in the official record or evidence sidecar that were published from
      it**.
    * **the edit wins** -> the run edit rewrites the record's document, so the
      submission's validator is stale and it is refused 412 before anything is
      materialised. NOTHING is published: no record, no sidecar, no submission row,
      no revision row.

    THE PUBLISHED-BYTES ASSERTION IS THE POINT of the first branch. A submission
    publishes official records from the draft it read; if an edit could interleave
    between that read and the publication, the artifact on disk would carry content
    nobody submitted, and a 412 on the edit would not reveal it.
    """
    exp = _experiment_with_runs(ws, labels=("run A",), experiment_id=EXPERIMENT_ID)
    eid = exp.id
    rid = exp.runs[0].id
    record_token = _record_etag(submit_client, eid)
    run_token = _run_etag(submit_client, eid, rid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    submit, edit = _race([
        lambda: submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": record_token}
        ),
        lambda: submit_client.patch(
            f"/api/experiments/{eid}/runs/{rid}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_A}},
            headers={"If-Match": run_token},
        ),
    ])

    _assert_raced(rendezvous, None, eid)
    after = ws.load_experiment(eid)
    assert sorted(r.status_code for r in [submit, edit]) == [200, 412], (
        _outcome([submit, edit])
    )

    if submit.status_code == 200:
        assert edit.json()["error"] == "stale_write"
        assert edit.json()["run_id"] == rid, (
            "the refused RUN write must name the run, not only the record"
        )
        assert _run_field(after, rid, RUN_FIELD) != VALUE_A, (
            "the refused edit reached the run"
        )
        assert str(VALUE_A) not in _state_json(after)
        published = {entry["record_id"] for entry in submit.json()["records"]}
        assert published, submit.json()
        for record_id in published:
            record_bytes = (after.records_dir / f"{record_id}.json").read_bytes()
            sidecar_bytes = (after.records_dir / f"{record_id}.evidence.json").read_bytes()
            assert str(VALUE_A).encode() not in record_bytes, (
                "a published official record carries content that was never submitted"
            )
            assert str(VALUE_A).encode() not in sidecar_bytes
        assert len(db.submissions) == 1, db.submissions
    else:
        assert edit.status_code == 200, _outcome([submit, edit])
        assert submit.json()["error"] == "stale_write"
        assert submit.json()["experiment_id"] == eid
        assert _run_field(after, rid, RUN_FIELD) == VALUE_A
        assert _artifacts(after) == set(), (
            "a submission refused on its precondition published artifacts anyway"
        )
        assert db.submissions == [], db.submissions
        assert db.revisions == [], db.revisions
        assert db.submission_runs == [], db.submission_runs


def test_no_writer_can_observe_the_window_between_publication_and_the_state_save(
    submit_client, armed, db, monkeypatch
):
    """The ORDERING inside a submission is publish-then-save, and the whole of it is
    inside the record lock.

    That ordering is deliberate and is documented as a recoverability property: a
    fault between the two leaves official records on disk and no submission, which
    a retry repairs, whereas the reverse leaves a submission naming records that
    were never written. What makes it safe is that no other writer can act while
    the record is in that intermediate shape.

    This test suspends the submission at the moment it writes the FIRST official
    record — provably after publication has begun and provably before the state was
    saved — and then, from a second thread, sends an edit of the same record.

    Two assertions, and they are deliberately of different strengths:

    * **Load-bearing and deterministic:** while the submission is suspended, the
      state file on disk still reads the PRE-submission revision even though an
      artifact has already been written. That is the intermediate shape itself, and
      it is asserted by reading bytes, not by timing.
    * **Supporting:** the concurrent edit has provably reached ``record_lock`` (the
      seam records its arrival) and has NOT completed. This direction is safe under
      machine load — a loaded machine makes a blocked thread more blocked, never
      less — so it can only ever fail when the edit genuinely was not blocked. It
      can, under load, PASS while a regression is present, which is why it is not
      the load-bearing half.

    Afterwards the edit is refused 412 and the submission is intact.
    """
    exp = _experiment_with_runs(ws, labels=("run A",), experiment_id=EXPERIMENT_ID)
    eid = exp.id
    rid = exp.runs[0].id
    token = _record_etag(submit_client, eid)
    run_token = _run_etag(submit_client, eid, rid)
    state_path = ws.workspace_root() / eid / "experiment.json"
    before_state = state_path.read_bytes()

    publishing = threading.Event()
    release = threading.Event()
    real_write = routes.atomic_write_text

    def _suspended_write(path, text):
        # The write HAPPENS FIRST and the suspension comes after it, so the state
        # observed below is the real intermediate one — an artifact on disk and the
        # record's own document not yet replaced. Suspending before the write would
        # observe a window in which nothing had been published at all, which is a
        # different (and uninteresting) claim. `routes.atomic_write_text` has
        # exactly one caller, `_write_record`, so only official records and their
        # sidecars pass through here; `Experiment.save` writes the state file
        # through the workspace module's own binding, which is untouched.
        result = real_write(path, text)
        if path.parent.name == "records" and not publishing.is_set():
            publishing.set()
            release.wait(timeout=_EVENT_TIMEOUT_S)
        return result

    monkeypatch.setattr(routes, "atomic_write_text", _suspended_write)

    # A second seam that only OBSERVES: it records the moment a caller reaches
    # `record_lock`, so "the edit was blocked" is a statement about a thread that
    # provably got there, not about one that may never have been scheduled.
    at_lock = threading.Event()
    arrivals = {"count": 0}
    guard = threading.Lock()
    real_lock = ws.record_lock

    def _observing_lock(experiment_id: str, *, session_id: str | None = None):
        with guard:
            arrivals["count"] += 1
            second = arrivals["count"] == 2
        if second and experiment_id == eid:
            at_lock.set()
        return real_lock(experiment_id, session_id=session_id)

    monkeypatch.setattr(ws, "record_lock", _observing_lock)

    submit_result: dict = {}
    edit_result: dict = {}

    def submitter():
        submit_result["response"] = submit_client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": token}
        )

    def editor():
        edit_result["response"] = submit_client.patch(
            f"/api/experiments/{eid}/runs/{rid}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_A}},
            headers={"If-Match": run_token},
        )

    submit_thread = threading.Thread(target=submitter, name="submitter")
    submit_thread.start()
    try:
        assert publishing.wait(timeout=_EVENT_TIMEOUT_S), (
            "the submission never reached the official-record write"
        )
        edit_thread = threading.Thread(target=editor, name="editor")
        edit_thread.start()
        try:
            assert at_lock.wait(timeout=_EVENT_TIMEOUT_S), (
                "the concurrent edit never reached the record lock"
            )
            # LOAD-BEARING: the intermediate shape, read from disk.
            assert state_path.read_bytes() == before_state, (
                "the record's state was saved before its official records were "
                "written — the publish-then-save ordering is inverted, and a fault "
                "between the two would now leave a record claiming artifacts that "
                "do not exist"
            )
            assert _artifacts(ws.load_experiment(eid)), (
                "no artifact was written, so this test did not observe the window "
                "it claims to"
            )
            # SUPPORTING (see the docstring for why this half is weaker).
            edit_thread.join(timeout=0.25)
            assert edit_thread.is_alive(), (
                "the edit completed while the submission held the record lock — a "
                "writer observed the record mid-publication"
            )
        finally:
            release.set()
            edit_thread.join(timeout=_EVENT_TIMEOUT_S)
            assert not edit_thread.is_alive(), "the editor deadlocked"
    finally:
        release.set()
        submit_thread.join(timeout=_EVENT_TIMEOUT_S)
        assert not submit_thread.is_alive(), "the submitter deadlocked"

    assert submit_result["response"].status_code == 200, submit_result["response"].text
    assert edit_result["response"].status_code == 412, edit_result["response"].text
    assert edit_result["response"].json()["error"] == "stale_write"

    after = ws.load_experiment(eid)
    assert _run_field(after, rid, RUN_FIELD) != VALUE_A
    assert str(VALUE_A) not in _state_json(after)
    assert len(db.submissions) == 1, db.submissions
    assert state_path.read_bytes() != before_state, (
        "the submission's own state save never landed"
    )


# =============================================================================
# 9. Two decisions about one conflicting address, at once
# =============================================================================


def _conflicted_experiment(store):
    """A record whose ``sample.material.formula`` evidence asserts two values."""
    exp = store.create_experiment(
        "Conflict concurrency fixture",
        {"kind": "synthetic"},
        {
            "meta": {},
            "fields": {
                RECORD_CONFLICT_ADDRESS: _competing(
                    "LiFePO4", "LiFePO3", question="What is the formula?"
                )
            },
            "pending": [],
        },
    )
    return exp


def _decisions(exp) -> list:
    readable, unreadable = cr.resolutions_from_draft(exp.draft)
    assert unreadable == [], unreadable
    return readable


def test_two_decisions_about_one_conflict_at_once_store_exactly_one(client, monkeypatch):
    """Two scientists record a decision about the SAME conflicting address at the
    same moment, both holding the record's current validator.

    LEGITIMATE ORDERINGS: either decision may be the one recorded — nothing here
    names a winner.

    THE INVARIANTS, and the third is the one a status-code test would miss:

    * exactly one 200 and one 412 ``stale_write``;
    * the stored decision list holds **exactly one row for that address**, carrying
      the winner's ``chosen_value`` — never two competing decisions with no rule
      for which is current;
    * its ``history`` holds **exactly one** transition, and that transition is an
      opening ``record`` rather than a ``revise``. A loser whose write had been
      applied and then only partly rolled back would show up here as a second
      history entry, or as a ``revise`` with the loser's value in
      ``superseded_chosen_value`` — which is a durable, human-readable claim that
      somebody changed their mind when nobody did.

    Recording a decision writes no scientific value, so the field's own value is
    asserted unchanged too.
    """
    store = client_ws(client)
    exp = _conflicted_experiment(store)
    eid = exp.id
    listing = client.get(f"/api/experiments/{eid}/conflicts")
    assert listing.status_code == 200, listing.text
    assert [c["address"] for c in listing.json()["conflicts"]] == [RECORD_CONFLICT_ADDRESS]

    token = _record_etag(client, eid)
    before = store.load_experiment(eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    def _resolve(value):
        return client.post(
            f"/api/experiments/{eid}/conflicts/resolve",
            json={
                "confirmed_by_user": True,
                "address": RECORD_CONFLICT_ADDRESS,
                "outcome": "resolved",
                "chosen_value": value,
                "chosen_from": "candidate",
            },
            headers={"If-Match": token},
        )

    responses = _race([lambda: _resolve("LiFePO4"), lambda: _resolve("LiFePO3")])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    assert sorted(r.status_code for r in responses) == [200, 412], _outcome(responses)
    loser = next(r for r in responses if r.status_code == 412)
    assert loser.json()["error"] == "stale_write"
    assert loser.json()["experiment_id"] == eid

    after = store.load_experiment(eid)
    stored = _decisions(after)
    assert len(stored) == 1, (
        f"exactly one decision may be stored for one address, found {len(stored)}"
    )
    decision = stored[0]
    assert decision.address == RECORD_CONFLICT_ADDRESS
    assert decision.run_id is None
    won = "LiFePO4" if responses[0].status_code == 200 else "LiFePO3"
    lost = "LiFePO3" if won == "LiFePO4" else "LiFePO4"
    assert decision.chosen_value == won, "the stored decision is not the winner's"
    assert [t.action for t in decision.history] == [cr.ACTION_RECORD], (
        "the decision's history is corrupted: a refused write left a transition behind"
    )
    assert decision.history[0].superseded_chosen_value is None
    # The digest covers the address's answers AS THE DOCUMENT HOLDS THEM — derived
    # from the stored evidence rather than from a hand-written pair, because the
    # competing set is the canonical form of each answer and a literal here would
    # be a second (and, as first written, wrong) definition of that canonicalisation.
    current = cr.competing_from_evidence(
        after.draft["fields"][RECORD_CONFLICT_ADDRESS]["evidence"]
    )
    assert len(current) == 2, current
    assert decision.competing_values == tuple(sorted(current))
    assert decision.competing_digest == cr.competing_digest(current)
    assert after.rev == before.rev + 1, "exactly one accepted write is one revision"

    # A decision is not a value: the field is untouched, and the loser's choice
    # exists only as one of the competing ANSWERS it already was.
    assert after.draft["fields"][RECORD_CONFLICT_ADDRESS]["value"] == "LiFePO4"
    assert (
        before.draft["fields"][RECORD_CONFLICT_ADDRESS]
        == after.draft["fields"][RECORD_CONFLICT_ADDRESS]
    ), "recording a decision changed the field's evidence"
    assert lost in _state_json(after)  # still a candidate, as it always was


# =============================================================================
# 10. A decision racing an edit that CHANGES the competing set
# =============================================================================


def test_a_decision_racing_an_edit_that_changes_the_competing_set(client, monkeypatch):
    """A run-scoped decision races a run edit that adds a THIRD competing answer.

    The two hold DIFFERENT validators over one document: a decision is stored in
    the RECORD's own draft and takes the record's ``ETag``, while the run edit
    takes the RUN's. Both are current when the race starts.

    LEGITIMATE ORDERINGS — and there are only two, because the pairing is
    ASYMMETRIC:

    * **the decision reaches the lock first** -> it is recorded over the two
      answers that existed at that moment. The edit then adds a third answer, and
      the decision becomes ``stale``: it no longer covers the disagreement a reader
      now sees. Both requests return 200.
    * **the edit reaches the lock first** -> the edit succeeds, and because a run
      lives inside the record's document a run edit rewrites the RECORD, so the
      decision's record-level validator is now stale and the decision is refused
      **412**, with NO decision stored at all.

    THE THIRD ORDERING DOES NOT EXIST, and that is worth stating because it is the
    one a reader would expect: a decision recorded over all THREE answers is
    unreachable through this race. Editing any run invalidates the record's
    validator, so a decision that arrives after an edit is refused rather than
    re-read. That is a real, documented consequence of runs sharing the record's
    document — not a defect and not a gap in this test — and it is asserted here
    rather than worked around.

    THE INVARIANT THAT HOLDS IN BOTH ORDERINGS, and the thing that would break if
    the handler computed the competing set OUTSIDE the record lock: **a stored
    decision is never ``current`` over a set it was not chosen from.** Whichever
    way the race goes, either no decision exists, or the decision's stored
    ``competing_values`` are exactly the answers that were present in the document
    it was written into — so after the third answer arrives it must read ``stale``
    and its values must be a STRICT SUBSET of the answers now recorded. A decision
    chosen from ``{300, 310}`` sitting over a document holding ``{300, 310, 320}``
    and reporting ``current`` is exactly the corruption this asserts against.
    """
    store = client_ws(client)
    exp = store.create_experiment(
        "Run conflict concurrency fixture", {"kind": "synthetic"},
        {"meta": {}, "fields": {}, "pending": []},
    )
    run = exp.add_run(
        label="Run A",
        draft={
            "fields": {
                RUN_FIELD: _competing(300, 310, question="What temperature?"),
            },
            "pending": [],
        },
    )
    exp.save_versioned()
    eid, rid = exp.id, run.id

    record_token = _record_etag(client, eid)
    run_token = _run_etag(client, eid, rid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    decide, edit = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/conflicts/resolve",
            json={
                "confirmed_by_user": True,
                "address": RUN_FIELD,
                "run_id": rid,
                "outcome": "resolved",
                "chosen_value": 300,
                "chosen_from": "candidate",
            },
            headers={"If-Match": record_token},
        ),
        lambda: client.patch(
            f"/api/experiments/{eid}/runs/{rid}",
            json={"confirmed_by_user": True, "fields": {RUN_FIELD: VALUE_C}},
            headers={"If-Match": run_token},
        ),
    ])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    assert edit.status_code == 200, edit.text
    assert decide.status_code in (200, 412), decide.text

    after = store.load_experiment(eid)
    # Whichever way it went, the edit's own value landed and the run advanced once.
    assert _run_field(after, rid, RUN_FIELD) == VALUE_C
    assert after.get_run(rid).rev == run.rev + 1

    # The competing set the document ACTUALLY holds now, derived from the stored
    # evidence rather than from the API's own report of it.
    current_entry = (after.get_run(rid).draft.get("fields") or {})[RUN_FIELD]
    current = cr.competing_from_evidence(current_entry.get("evidence"))
    assert len(current) == 3, (
        f"the edit must have added a third competing answer, got {current}"
    )

    listed = client.get(f"/api/experiments/{eid}/conflicts", params={"run": rid}).json()
    entry = next(c for c in listed["conflicts"] if c["address"] == RUN_FIELD)
    stored = _decisions(after)

    if decide.status_code == 412:
        assert decide.json()["error"] == "stale_write"
        assert decide.json()["experiment_id"] == eid
        assert stored == [], (
            "the decision was refused, so NO decision may be stored for that address"
        )
        assert entry["resolution_state"] == cr.RESOLUTION_ABSENT
        assert entry["resolution"] is None
        return

    assert len(stored) == 1, f"exactly one decision may be stored, found {len(stored)}"
    decision = stored[0]
    assert decision.run_id == rid
    assert decision.address == RUN_FIELD
    assert decision.chosen_value == 300
    assert [t.action for t in decision.history] == [cr.ACTION_RECORD]
    assert decision.competing_digest == cr.competing_digest(decision.competing_values)

    stored_values = set(decision.competing_values)
    assert stored_values < set(current), (
        "the decision was recorded before the third answer arrived, so its competing "
        "set must be a STRICT subset of the answers the document now holds"
    )
    assert entry["resolution_state"] == cr.RESOLUTION_STALE, (
        "the decision reports CURRENT over a set it was not chosen from — the "
        "competing answers were read outside the record lock, or the staleness "
        "comparison is not being made against the live evidence"
    )
    assert entry["resolution_stale"] is True
    assert entry["resolved"] is False, (
        "a superseded decision must not go on clearing the conflict"
    )
    # The decision is still there in full — nothing deletes a recorded decision.
    assert entry["resolution"]["chosen_value"] == 300
