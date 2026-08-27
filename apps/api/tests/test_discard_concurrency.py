"""``POST /api/experiments/{id}/discard`` under CONCURRENCY — the destructive path.

WHY A FIFTH CONCURRENCY FILE, AND WHAT IT IS NOT A SECOND COPY OF
=================================================================
Four files already race this application's write paths, and none of them can
reach this one because it did not exist when they were written:

* ``test_handler_concurrency.py`` — the record-level ``/answers`` and ``/edit``
  compare-and-swap, the absent/stale precondition rules, a read concurrent with a
  write, and the documented retry-after-conflict recovery.
* ``test_lifecycle_concurrency.py`` — run edit vs run edit, two runs at once,
  override vs revert, run removal vs run edit, run removal vs submit, submit
  double-click, two scientists submitting, an edit arriving mid-submit, two
  conflict decisions, a decision racing an edit, and the run-level answer routes.
* ``test_concurrent_write_pairs_lose_no_update.py`` — asset edit vs asset edit,
  asset removal vs asset edit, ``/answers`` vs ``/edit`` on one address, the two
  ``If-Match: *`` cases, transcript finalize vs ``/edit``, two note reviews, and
  run removal vs note capture.
* ``test_run_row_parity.py`` — the durable run-row projection, whose own
  "concurrent" case is explicit that it is *sequential, two real connections*.

**Every pair in this file has a DISCARD on one side.** Discard is the only
operation in this API that destroys a record, and the four files above race
operations that all leave the record standing. A refusal that arrives one
instruction too late is a different kind of event here: this repository has a
written record of a destructive path that returned a recoverable-sounding
``412 plan_digest_stale`` **after** it had already destroyed a record and could
never succeed on retry (the reset, ``main`` before ``#183``/``#187``). That is the
class of defect these tests exist to detect on the new path.

THE ORDER OF THE FIVE REFUSALS IS THE THING UNDER ATTACK
========================================================
``post_experiment_discard``'s contract is ``exists (404) -> confirmed (422) ->
domain refusal (409/503) -> precondition (428/400/412) -> write``, with the
precondition checked INSIDE the same ``record_lock`` as the mutation. The
question a sequential test cannot ask is whether a record can become **submitted,
exported, or gain a run BETWEEN the domain refusal and the delete**. Two tests
below suspend the discard at exactly those two points — after every local domain
refusal (``_submission_history_refusal``) and after the precondition, one call
before the removal (``ws.discard_experiment``) — and fire the competing write
while it is held.

DETERMINISM: THE ORDERING IS A PROPERTY OF THE LOCK, NOT OF THE SCHEDULER
========================================================================
``_LockRendezvous`` (``test_handler_concurrency``) guarantees two requests
*overlap* but leaves which one acquires the lock first to the operating system.
For a destructive pair that is not enough: "discard wins" and "the other writer
wins" have completely different aftermaths, and a test asserting only the
invariant common to both would pass while one of the two orderings was broken.
:class:`_OrderedInterleave` forces the order instead — see its docstring for the
five-step argument that no interleaving exists in which the follower wins. There
is no sleep anywhere in this file, and every safety-net timeout is itself asserted
NOT to have expired.

THE BAR EVERY REFUSAL HERE MEETS
================================
Never only the status code. For every refused call:

* the EXACT typed ``error`` value and the exact status;
* the authoritative state, RE-READ from the workspace after the call — never
  inferred from a response body, and never from the in-memory object the handler
  mutated;
* the version tokens, the record's and every run's, so a refusal that silently
  advanced a validator fails here;
* the revision and submission rows, compared whole rather than counted;
* the files on disk under the experiment, by name AND by bytes — an official
  record and its evidence sidecar must never be orphaned or destroyed;
* and, for the winner, that the record's directory is gone and no file of it
  survives anywhere under the scope root.

SCOPE, DATA AND WHAT THIS FILE CANNOT PROVE
===========================================
Ordinary scope throughout (``PGHOST`` unset unless a test says otherwise): a
worked-example session holds only canonical example records, and every discard
there answers ``409 canonical_example_record`` before any race could matter.
Every fixture is the committed synthetic seed draft; nothing here reads real data,
opens a network connection, or contacts a database.

Nothing here is a multi-PROCESS race — ``ws.record_lock`` is in-process and the
deployed server is single-process uvicorn, which is the concurrency the product
actually has. The cross-process half of the same contract is the durable
compare-and-swap, and the discard's own backstop against it is the foreign key
from ``0003``/``0004``, proved against a real ``postgres:18`` by
``test_discard_an_unsubmitted_experiment.py``'s real-engine section and by CI.
Where a branch is only reachable that way this file says so rather than pretending.
"""

from __future__ import annotations

import contextlib
import copy
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.routes as routes
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws

from submission_fake import FakeSubmissionConnection, fake_reader, fake_store

# The overlap seam, the thread runner and the compact failure message are
# IMPORTED, not re-declared, for the reason `test_lifecycle_concurrency` gives for
# importing them: a second copy of "these two requests overlapped" is free to
# drift from the one `test_handler_concurrency` maintains.
from test_handler_concurrency import (  # noqa: E402
    _EVENT_TIMEOUT_S,
    _LockRendezvous,
    _outcome,
    _race,
)

# The ordinary-scope counterpart of `_LockRendezvous.assert_scoped` is imported for
# the same reason. It checks BOTH halves — the scope the handler passed down and
# the key the real lock computed — because two threads on two different keys do not
# serialise and every race here would silently stop being a race.
from test_lifecycle_concurrency import _assert_ordinary_scope  # noqa: E402

#: 26-character ULID-shaped ids. `_EXPERIMENT_ID_MAX_LENGTH` is 128, so these are
#: well inside the boundary the path parameter refuses.
EXPERIMENT_ID = "01DISCARDRACE0000000000001"
OTHER_ID = "01DISCARDRACE0000000000002"
ACTOR = "ada.lovelace"

#: A well-formed 64-hex sentinel the system can never invent, so
#: ``assert SENTINEL not in json.dumps(state)`` is a real statement.
SENTINEL_SHA = "d" * 64
#: An asset uri the committed seed draft carries ALREADY ANSWERED, so ``/edit`` is
#: the operation that may write it. Measured: ``_full_draft()`` has
#: ``pending_count() == 0``, which is what makes it export-ready.
ANSWERED_URI = "ssrl-archive://BL15-2/2099_run_000/raw/"


# =============================================================================
# fixtures
# =============================================================================


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A private ORDINARY-scope workspace with no database configured.

    Ordinary rather than worked-example scope, for the reason
    ``test_discard_an_unsubmitted_experiment`` gives: it is the scope a scientist's
    own record lives in and the only one from which a submission, a durable write
    or a successful discard is reachable at all.
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
    """Point BOTH the submit store and the discard's history reader at ONE double.

    The same connection deliberately: a discard precheck reading from a store of
    its own could not see what a submission actually wrote, which is precisely the
    thing a discard-vs-submit race must not get wrong.
    """
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(db))
    return db


@pytest.fixture()
def armed(workspace, monkeypatch):
    """A deployment that CAN attribute a submission: the fixture verifier.

    ``FixtureEdgeVerifier`` reads its subject from the PROCESS ENVIRONMENT and
    never from a request, and it mints ``trust_basis="test_fixture"``, so every row
    it causes is permanently labelled as fixture-attributed.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _client() -> TestClient:
    """A plain client — no worked-example header, so ``scope`` is ``None``.

    ``raise_server_exceptions=False`` matches ``test_submission`` and
    ``test_lifecycle_concurrency``: a handler that raised inside a racing thread
    would otherwise be reported as "the thread did not finish", which names the
    wrong problem. Here it surfaces as a 500 and every assertion states its code.
    """
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _make(experiment_id: str = EXPERIMENT_ID, *, runs: tuple[str, ...] = ()):
    """An export-ready ordinary-scope experiment carrying ``runs``.

    The run drafts are a deep copy of the record's own committed seed draft, so
    every unit really is exportable — which is what makes an export and a
    submission reachable in the races below. Nothing here composes a scientific
    value; every value comes out of the committed synthetic seed.
    """
    exp = ws.create_experiment(
        "Discard race fixture",
        {"kind": "synthetic"},
        copy.deepcopy(ws._full_draft()),
        id=experiment_id,
    )
    run_draft = copy.deepcopy(exp.draft)
    for label in runs:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


# =============================================================================
# reads used for ASSERTIONS ONLY — never to perform a mutation
# =============================================================================


def _etag(client, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, experiment_id: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _discard(client, experiment_id: str = EXPERIMENT_ID, *, if_match, body=...):
    payload = {"confirmed_by_user": True} if body is ... else body
    headers = {} if if_match is None else {"If-Match": if_match}
    return client.post(
        f"/api/experiments/{experiment_id}/discard", json=payload, headers=headers
    )


def _listed_ids(client) -> list[str]:
    response = client.get("/api/experiments")
    assert response.status_code == 200, response.text
    return sorted(row["id"] for row in response.json()["experiments"])


def _tree(experiment_id: str = EXPERIMENT_ID) -> dict[str, bytes]:
    """Every file under this experiment's directory, by relative path, as BYTES.

    The whole subtree rather than just ``records/``: a discard removes the
    directory, and "the official record survived" and "the state document
    survived" are different claims that a name-only comparison would blur.
    """
    root = ws.scope_root(None) / experiment_id
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _scope_tree() -> dict[str, bytes]:
    """Every file under the ORDINARY scope root, by relative path, as bytes.

    Used to prove a winner left NO orphan anywhere — not merely that the record's
    own directory is gone.
    """
    root = ws.scope_root(None)
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _versions(exp) -> dict:
    """Every version token this record carries — the record's and every run's.

    One mapping so "nothing moved" or "exactly this moved" is a single comparison,
    including ``generation``, which no operation in this file legitimately changes.
    """
    return {
        "record": exp.version_token(),
        "generation": exp.generation,
        "runs": {
            run.id: {"version": run.version_token(), "generation": run.generation}
            for run in exp.sorted_runs()
        },
    }


def _history(db) -> dict:
    """Every durable history row set the fake connection holds, deep-copied."""
    return {
        "revisions": copy.deepcopy(db.revisions),
        "run_revisions": copy.deepcopy(db.run_revisions),
        "submissions": copy.deepcopy(db.submissions),
        "submission_runs": copy.deepcopy(db.submission_runs),
    }


def _assert_record_is_wholly_gone(client, experiment_id: str = EXPERIMENT_ID) -> None:
    """The four independent ways this workspace could still be holding the record."""
    assert ws.load_experiment(experiment_id) is None, "the store still loads it"
    assert not (ws.scope_root(None) / experiment_id).exists(), "its directory survived"
    assert _tree(experiment_id) == {}, "a file of it survived"
    assert experiment_id not in _listed_ids(client), "it is still listed"
    detail = client.get(f"/api/experiments/{experiment_id}")
    assert detail.status_code == 404, detail.text
    assert detail.json()["error"] == "experiment_not_found", detail.text


def _assert_nothing_was_removed(
    client, before_tree: dict, before_versions: dict, experiment_id: str = EXPERIMENT_ID
) -> None:
    """The record is still here, byte-identical, with every validator unmoved."""
    after = ws.load_experiment(experiment_id)
    assert after is not None, "the record was removed by a call that refused"
    assert _tree(experiment_id) == before_tree, "a file under the record changed"
    assert _versions(after) == before_versions, "a refused call moved a version token"
    assert experiment_id in _listed_ids(client)


# =============================================================================
# THE DETERMINISTIC ORDERING DEVICE
# =============================================================================


class _OrderedInterleave:
    """Force WHICH of two concurrent requests holds ``record_lock`` first.

    ``_LockRendezvous`` — imported above and used unchanged where order does not
    matter — guarantees the two requests OVERLAP. It does not decide which one
    acquires the lock, and for a destructive pair that is the whole question: "the
    discard won" and "the other writer won" have different aftermaths, so a test
    that asserted only their common invariant would pass while one of the two
    orderings was broken.

    THE ARGUMENT THAT THE ORDER IS FORCED, in five steps, none of which is a sleep:

    1. The LEADER's request is issued first and reaches ``record_lock``
       uncontended, so it acquires it.
    2. Inside its critical section it calls a seam this test installed with
       :meth:`hold` on a function only the leader calls under the lock. The seam
       sets :attr:`entered` — which therefore PROVES the leader holds the lock —
       and then waits for :attr:`arrivals` to reach ``parties``.
    3. The main thread starts the FOLLOWER only after :attr:`entered` is set.
    4. The follower's request reaches ``record_lock`` (``arrivals`` becomes 2) and
       cannot acquire it, because the leader is holding it.
    5. The leader's seam returns, the leader finishes its critical section and
       releases; only then can the follower enter.

    Step 4 has a deliberately harmless window: ``arrivals`` is counted just BEFORE
    the acquire attempt, so the leader may resume a moment before the follower is
    actually blocked. It changes nothing — the follower cannot enter the critical
    section while the leader holds the lock, so the ordering holds in either case,
    and the handshake is what establishes that the follower was genuinely in flight
    rather than merely started.

    Every timeout below is a SAFETY NET, not a synchroniser: a healthy run trips
    each event immediately, and :meth:`assert_ordered` asserts the net was never
    hit, so a build that serialised these requests would fail loudly rather than
    pass vacuously.

    The scope forwarding is recorded exactly as ``_LockRendezvous`` records it —
    the ``session_id`` the seam was HANDED and the key the REAL lock COMPUTED —
    because an unforwarded scope makes two threads contend on two different keys,
    and every test here would go on passing while its race had stopped happening.
    """

    def __init__(self, monkeypatch, target: str, *, parties: int = 2):
        self.target = target
        self.parties = parties
        self.arrivals = 0
        self.scopes: list[str | None] = []
        self.lock_keys: list[str] = []
        self.entered = threading.Event()
        self.timed_out = False
        self.held = False
        self._cond = threading.Condition(threading.Lock())
        real = ws.record_lock
        real_key = ws._lock_key

        def _recording_key(experiment_id: str, session_id: str | None) -> str:
            key = real_key(experiment_id, session_id)
            if experiment_id == self.target:
                with self._cond:
                    self.lock_keys.append(key)
            return key

        monkeypatch.setattr(ws, "_lock_key", _recording_key)

        @contextlib.contextmanager
        def _patched(experiment_id: str, *, session_id: str | None = None):
            if experiment_id == self.target:
                with self._cond:
                    self.arrivals += 1
                    self.scopes.append(session_id)
                    self._cond.notify_all()
            with real(experiment_id, session_id=session_id):
                yield

        monkeypatch.setattr(ws, "record_lock", _patched)

    def _await_arrivals(self, count: int) -> bool:
        deadline = time.monotonic() + _EVENT_TIMEOUT_S
        with self._cond:
            while self.arrivals < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._cond.wait(timeout=remaining):
                    if self.arrivals < count:
                        return False
        return True

    def hold(self, monkeypatch, obj, name: str):
        """Suspend the LEADER inside its critical section at ``obj.name``.

        ``obj.name`` must be something ONLY the leader calls while holding the
        target's lock; each test names one and its comment says why the follower
        cannot reach it. Only the first invocation holds — a leader that calls the
        seam twice is not suspended twice.
        """
        real = getattr(obj, name)
        guard = threading.Lock()

        def _wrapped(*args, **kwargs):
            with guard:
                first = not self.held
                if first:
                    self.held = True
            if first:
                self.entered.set()
                if not self._await_arrivals(self.parties):
                    # Never reached on a healthy run. Recorded rather than raised so
                    # the failure is reported by the main thread's assertion instead
                    # of as a 500 from a worker.
                    self.timed_out = True
            return real(*args, **kwargs)

        monkeypatch.setattr(obj, name, _wrapped)

    def assert_ordered(self) -> None:
        """Both requests really overlapped, on ONE ordinary-scope lock key."""
        assert self.held, (
            "the leader never reached the seam inside its critical section — this "
            "run proved nothing about ordering"
        )
        assert not self.timed_out, (
            "the follower never reached the record lock while the leader held it; "
            "the two requests did not overlap"
        )
        assert self.arrivals == self.parties, (
            f"{self.arrivals} request(s) reached the target's lock, expected "
            f"{self.parties} — the race did not happen"
        )
        _assert_ordinary_scope(self, self.target)


def _ordered_race(interleave: _OrderedInterleave, leader, follower):
    """Run ``leader`` then ``follower`` concurrently, in that lock order.

    The follower is started only once the leader is provably INSIDE the target's
    critical section, which is what makes the ordering a property of the lock
    rather than of thread start order.
    """
    results: dict = {}

    def run(key, fn):
        results[key] = fn()

    leader_thread = threading.Thread(target=run, args=("leader", leader), name="leader")
    leader_thread.start()
    assert interleave.entered.wait(timeout=_EVENT_TIMEOUT_S), (
        "the leader never reached its seam inside the record lock"
    )
    follower_thread = threading.Thread(
        target=run, args=("follower", follower), name="follower"
    )
    follower_thread.start()
    for thread in (leader_thread, follower_thread):
        thread.join(timeout=_EVENT_TIMEOUT_S * 2)
        assert not thread.is_alive(), f"{thread.name} did not finish — a deadlock"
    interleave.assert_ordered()
    return results["leader"], results["follower"]


# =============================================================================
# 1. DISCARD vs DISCARD
# =============================================================================


def test_two_discards_of_one_record_leave_exactly_one_winner(workspace, monkeypatch):
    """Two clients, one token, one record: one ``200``, one ``404``.

    The loser's ``404`` is the branch ``post_experiment_discard`` comments as
    "discarded in the pre-check->lock window" — its existence pre-check ran while
    the record was still there, and the re-read INSIDE the lock is what tells it
    the truth. That branch is unreachable without a race, which is why it is here.

    ``404`` and not a second ``200`` is the CONTRACT, and it is the assertion that
    matters: a second ``200`` would claim a record "was discarded" by a request
    that removed nothing.
    """
    _make()
    _make(OTHER_ID)
    client = _client()
    tag = _etag(client)
    sibling_before = _tree(OTHER_ID)
    rendezvous = _LockRendezvous(monkeypatch, EXPERIMENT_ID)

    responses = _race([lambda: _discard(client, if_match=tag)] * 2)

    assert rendezvous.arrivals == 2, "the two discards did not reach the lock"
    assert not rendezvous.timed_out, "the two requests did not overlap"
    _assert_ordinary_scope(rendezvous, EXPERIMENT_ID)
    assert sorted(r.status_code for r in responses) == [200, 404], _outcome(responses)

    winner = next(r for r in responses if r.status_code == 200)
    loser = next(r for r in responses if r.status_code == 404)
    assert winner.json()["discarded_experiment_id"] == EXPERIMENT_ID, winner.text
    assert winner.json()["discarded_run_count"] == 0, winner.text
    assert winner.json()["durable_rows_removed"] == 0, winner.text
    assert "ETag" not in winner.headers, "a discarded record has no validator to echo"
    assert loser.json() == {"error": "experiment_not_found", "id": EXPERIMENT_ID}

    _assert_record_is_wholly_gone(client)
    assert _tree(OTHER_ID) == sibling_before, "an unrelated record was disturbed"
    assert _listed_ids(client) == [OTHER_ID]


def test_two_WILDCARD_discards_are_BOTH_refused_and_the_record_survives(
    workspace, monkeypatch
):
    """``If-Match: *`` is no longer a usable precondition for THIS operation.

    ~~"``_check_if_match`` returns early on ``*``, so nothing separates two wildcard
    discards at the PRECONDITION at all. What separates them is the existence
    re-read inside the lock."~~ **That premise stopped being true, and the test is
    rewritten rather than deleted because the premise is the interesting part.**

    Discard now refuses ``*`` outright with ``400 wildcard_precondition_refused``.
    Two independent reviewers reached that recommendation separately, from opposite
    directions: one measured that a wildcard discard destroys an edit it never read
    (see the sibling test below), and one observed that the operation's own
    description says *"There is no undo. That is why the confirmation and the
    precondition are both required"* — a sentence ``*`` made vacuous while it went
    on being published.

    THE REFUSAL HAPPENS INSIDE THE LOCK, NOT BEFORE IT, and that is deliberate
    rather than an oversight — the first version of this test asserted the opposite
    and was wrong. ``post_discard``'s documented refusal order is
    ``exists -> confirmed -> domain refusal -> precondition -> write``, and the
    precondition is checked in the SAME critical section as the mutation because
    this repository has a written history of that exact defect on the reset path.
    Hoisting a cheap wildcard check above the lock would buy nothing and would put
    one precondition branch on a different side of the boundary from the other
    three. So both requests still arrive, and both are refused there.

    The guard this test was originally written to exercise — the existence re-read
    that made two wildcard discards idempotent — is no longer what decides the
    race. It is still present and still correct; it is simply unreachable by this
    route, which is why the assertions below are about the refusal and the survival
    of the record rather than about a winner and a loser.

    ``*`` remains accepted on run removal, asset removal and every ordinary write.
    That is deliberate and is asserted elsewhere: both removals are recoverable by
    re-adding, and ``test_mcp_if_match_wildcard.py`` pins the wildcard's general
    behaviour as NOT to be "made consistent" by tightening.
    """
    _make()
    client = _client()
    rendezvous = _LockRendezvous(monkeypatch, EXPERIMENT_ID)

    responses = _race([lambda: _discard(client, if_match="*")] * 2)

    assert [r.status_code for r in responses] == [400, 400], _outcome(responses)
    for response in responses:
        assert response.json()["error"] == "wildcard_precondition_refused", response.text
    assert rendezvous.arrivals == 2, "both discards should still reach the lock"
    assert not rendezvous.timed_out, "the two requests did not overlap"
    _assert_ordinary_scope(rendezvous, EXPERIMENT_ID)
    assert _listed_ids(client) == [EXPERIMENT_ID], (
        "both refusals must leave the record exactly where it was"
    )
    assert _tree(EXPERIMENT_ID), "the record's own state document is gone"


# =============================================================================
# 2. DISCARD vs SAVE
# =============================================================================


def test_a_discard_that_wins_leaves_the_concurrent_save_a_clean_404(
    workspace, monkeypatch
):
    """Discard first, rename second: the rename is a ``404`` that wrote nothing.

    The seam is ``ws.discard_experiment`` — the call one step AFTER the
    precondition and immediately before the removal, so the follower is queued at
    the lock across the narrowest window the operation has. The rename cannot
    reach that seam: it never calls it.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws, "discard_experiment")

    discard, rename = _ordered_race(
        interleave,
        lambda: _discard(client, if_match=tag),
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": "Renamed by a client that never saw the discard"},
            headers={"If-Match": tag},
        ),
    )

    assert discard.status_code == 200, discard.text
    assert rename.status_code == 404, rename.text
    assert rename.json() == {"error": "experiment_not_found", "id": EXPERIMENT_ID}
    _assert_record_is_wholly_gone(client)
    # The loser's value is nowhere in the workspace — not in a stray file, not in
    # a half-written directory the removal left behind.
    assert "Renamed by a client" not in json.dumps(
        {k: v.decode("utf-8", "replace") for k, v in _scope_tree().items()}
    )


def test_a_save_that_wins_refuses_the_concurrent_discard_with_a_stale_write(
    workspace, monkeypatch
):
    """Rename first, discard second: ``412 stale_write``, and the record STANDS.

    This is the ordering that matters most on a destructive path. The discarding
    client is holding a version of a record that no longer exists; destroying the
    version that does exist would destroy an edit it never saw. The refusal has to
    arrive BEFORE the removal, and "the record is still here afterwards" is the
    only assertion that can tell the difference.

    The seam is ``Experiment.save_versioned`` — the rename's own write, taken
    under the lock. The discard never calls it: it removes a directory.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    rename, discard = _ordered_race(
        interleave,
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": "Work the discarding client never saw"},
            headers={"If-Match": tag},
        ),
        lambda: _discard(client, if_match=tag),
    )

    assert rename.status_code == 200, rename.text
    assert discard.status_code == 412, discard.text
    body = discard.json()
    assert body["error"] == "stale_write", body
    assert body["experiment_id"] == EXPERIMENT_ID, body
    assert body["expected_version"] == tag.strip('"'), body
    assert body["current_version"] != body["expected_version"], body

    after = ws.load_experiment(EXPERIMENT_ID)
    assert after is not None, "a 412 discarded the record anyway"
    assert after.title == "Work the discarding client never saw"
    assert after.rev == body["current_rev"]
    assert discard.headers["ETag"] == after.etag()
    assert EXPERIMENT_ID in _listed_ids(client)
    assert _tree(EXPERIMENT_ID), "the record's own state document is gone"


def test_a_WILDCARD_discard_can_no_longer_destroy_the_edit_it_never_saw(
    workspace, monkeypatch
):
    """THE CHARACTERISATION BECAME A DECISION, and the record of both is the point.

    This test WAS a characterisation, and it said so: ``*`` returned ``200`` and
    the response body echoed ``discarded_title`` = the title a concurrent writer
    had just committed — *"the discard did not even see the title it destroyed"*.
    It asserted what happened rather than that it was right, explicitly so that
    "a decision to refuse ``*`` on the destructive path is made against a
    measurement rather than an assumption".

    **That decision was then made, on this branch, and it went the way the
    measurement pointed.** Two independent reviewers reached it separately — one
    from this measurement, one from the observation that the operation's own
    published description says *"There is no undo. That is why the confirmation
    and the precondition are both required"*, which ``*`` made vacuous while the
    sentence went on being served. Discard now answers
    ``400 wildcard_precondition_refused``.

    ``400`` rather than ``428`` or ``412``, and the reasoning is worth keeping:
    ``428`` would state the header was OMITTED, which is false of a request that
    sent one; ``412`` would state a validator was compared and lost, and its body
    carries ``expected_version``/``expected_rev``, which are ``None`` for ``*`` —
    so it would echo nulls into the two fields a client reads to recover, and
    promise a retry that converges when re-reading changes nothing.

    THE SCOPE OF THE REFUSAL IS DISCARD ALONE. Run removal, asset removal and
    every ordinary write still accept ``*``: both removals are recoverable by
    re-adding, and ``test_mcp_if_match_wildcard.py`` pins the wildcard's general
    behaviour as deliberate and NOT to be "made consistent" by tightening. What
    distinguishes discard is that it is the only operation whose whole design
    assumes the caller knows what it is destroying — and ``*`` is the canonical
    idiom for a caller saying it holds no validator.

    The assertions below are the previous ones INVERTED rather than deleted: the
    rename that won now survives, and the record is still there.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    rename, discard = _ordered_race(
        interleave,
        lambda: client.patch(
            f"/api/experiments/{EXPERIMENT_ID}",
            json={"title": "Work the wildcard client never saw"},
            headers={"If-Match": tag},
        ),
        lambda: _discard(client, if_match="*"),
    )

    assert rename.status_code == 200, rename.text
    assert discard.status_code == 400, discard.text
    assert discard.json()["error"] == "wildcard_precondition_refused", discard.text

    after = ws.load_experiment(EXPERIMENT_ID)
    assert after is not None, "a refused wildcard discarded the record anyway"
    assert after.title == "Work the wildcard client never saw", (
        "the edit the wildcard client never read must survive it"
    )
    assert EXPERIMENT_ID in _listed_ids(client)
    assert _tree(EXPERIMENT_ID), "the record's own state document is gone"


def test_a_discard_that_wins_leaves_a_concurrent_CORRECTION_a_clean_404(
    workspace, monkeypatch
):
    """The same shape over ``POST /edit``, carrying a SCIENTIFIC VALUE.

    A rename touches only the title. This is a client correcting an answered field
    — a value with evidence behind it — and the assertion is that the value reaches
    NO file anywhere under the scope root, not merely that the response was a 404.

    ``/edit`` rather than ``/answers`` because the committed seed draft is fully
    answered (measured: ``pending_count() == 0``), so correcting an answered
    address is the legal record-level write here and filling an open one is not.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws, "discard_experiment")

    discard, correction = _ordered_race(
        interleave,
        lambda: _discard(client, if_match=tag),
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/edit",
            json={"confirmed_by_user": True, "answers": {ANSWERED_URI: SENTINEL_SHA}},
            headers={"If-Match": tag},
        ),
    )

    assert discard.status_code == 200, discard.text
    assert correction.status_code == 404, correction.text
    assert correction.json() == {"error": "experiment_not_found", "id": EXPERIMENT_ID}
    _assert_record_is_wholly_gone(client)
    assert SENTINEL_SHA not in json.dumps(
        {k: v.decode("utf-8", "replace") for k, v in _scope_tree().items()}
    ), "the loser\'s value survived the discard somewhere in the workspace"


# =============================================================================
# 3. DISCARD vs SUBMIT — the worst outcome in this codebase
# =============================================================================


def test_a_submit_that_wins_refuses_the_discard_and_keeps_EVERY_row_and_FILE(
    armed, wired, monkeypatch
):
    """Submit first, discard second: ``409``, and the declaration is intact.

    A submission is an attributable declaration a person made, its rows are
    append-only, and the official records it published are never rewritten. So the
    assertions are the whole row sets and the whole file tree compared BEFORE and
    AFTER, not counts: a rewritten ``state`` document or a dropped row fails here
    rather than being absorbed by a number that happens to match.

    The seam is ``submissions.blocker_report``, called under the lock after the
    storage preflight and before anything is materialised. The discard never
    reaches it.
    """
    _make()
    db = wired
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, routes.submissions, "blocker_report")

    submit, discard = _ordered_race(
        interleave,
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/submit", headers={"If-Match": tag}
        ),
        lambda: _discard(client, if_match=tag),
    )

    assert submit.status_code == 200, submit.text
    history_after_submit = _history(db)
    assert history_after_submit["revisions"] and history_after_submit["submissions"]
    files_after_submit = _tree(EXPERIMENT_ID)
    assert any(name.startswith("records/") for name in files_after_submit), (
        f"the submission published nothing: {sorted(files_after_submit)}"
    )

    assert discard.status_code == 409, discard.text
    body = discard.json()
    # A submission MATERIALISES every unit, so this record is exported too and
    # three of the six refusals are truthful. The one that must not happen is a 200.
    assert body["error"] in {"submitted", "experiment_exported", "runs_exported"}, body
    assert body["experiment_id"] == EXPERIMENT_ID, body
    assert "Nothing was removed" in body["message"], body

    assert _history(db) == history_after_submit, "a refused discard touched history"
    assert _tree(EXPERIMENT_ID) == files_after_submit, "a refused discard touched a file"
    after = ws.load_experiment(EXPERIMENT_ID)
    assert after is not None and after.record_id is not None
    assert EXPERIMENT_ID in _listed_ids(client)


def test_a_discard_that_wins_leaves_the_submit_a_404_and_NO_declaration(
    armed, wired, monkeypatch
):
    """Discard first, submit second — **the ordering to hunt for.**

    A discard that races a submit and WINS is the worst outcome this codebase can
    produce: an attributable declaration recorded against a record that no longer
    exists, or an official ISAAC record left on disk with nothing naming it. The
    assertions are therefore about what did NOT happen — no revision row, no
    submission row, and no published artifact ANYWHERE under the scope root, not
    merely none under the removed directory.

    The discard is suspended at ``_submission_history_refusal``: the point AFTER
    every local domain refusal and BEFORE the precondition and the removal. That
    is precisely the window the contract's refusal order has to survive — "can a
    record become submitted between the domain refusal and the delete?" — and the
    answer this test records is that it cannot, because the submit is queued at the
    same ``record_lock`` and never enters.
    """
    _make()
    db = wired
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, routes, "_submission_history_refusal")

    discard, submit = _ordered_race(
        interleave,
        lambda: _discard(client, if_match=tag),
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/submit", headers={"If-Match": tag}
        ),
    )

    assert discard.status_code == 200, discard.text
    assert submit.status_code == 404, submit.text
    assert submit.json() == {"error": "experiment_not_found", "id": EXPERIMENT_ID}

    assert _history(db) == {
        "revisions": [],
        "run_revisions": [],
        "submissions": [],
        "submission_runs": [],
    }, "a submission was declared over a record that no longer exists"
    _assert_record_is_wholly_gone(client)
    assert _scope_tree() == {}, (
        f"an artifact was orphaned by the discard: {sorted(_scope_tree())}"
    )


def test_the_discard_and_the_submit_can_never_BOTH_report_success(armed, monkeypatch):
    """The invariant, asserted over BOTH orderings in one test.

    The two tests above each pin one ordering's aftermath. This one pins the
    property that must hold whichever way the lock goes, and it is deliberately
    written as a property rather than as a third narrative: **at most one of the
    two returns a 2xx.** A build in which both succeeded would have recorded an
    attributable declaration about a record it had just destroyed, and both
    narrative tests could still pass if the ordering device were ever weakened.

    A FRESH connection double per ordering, wired inside the loop rather than by a
    fixture. Sharing one would let the first ordering's submission rows decide the
    second ordering's discard (the history precheck reads by ``experiment_id``),
    and the second half would then pass for a reason that has nothing to do with
    the race — the failure mode this file's own history-vs-state distinction exists
    to avoid.
    """
    outcomes: list[tuple[str, int, int]] = []
    for leader_is_discard in (True, False):
        with pytest.MonkeyPatch.context() as mp:
            db = FakeSubmissionConnection()
            mp.setattr(sstore, "store", lambda env=None, _db=db: fake_store(_db))
            mp.setattr(rhist, "reader", lambda env=None, _db=db: fake_reader(_db))
            _make()
            client = _client()
            tag = _etag(client)
            interleave = _OrderedInterleave(mp, EXPERIMENT_ID)

            def _submit(_client_=client, _tag=tag):
                return _client_.post(
                    f"/api/experiments/{EXPERIMENT_ID}/submit", headers={"If-Match": _tag}
                )

            def _discard_now(_client_=client, _tag=tag):
                return _discard(_client_, if_match=_tag)

            if leader_is_discard:
                interleave.hold(mp, routes, "_submission_history_refusal")
                first, second = _ordered_race(interleave, _discard_now, _submit)
                label = "discard-then-submit"
            else:
                interleave.hold(mp, routes.submissions, "blocker_report")
                first, second = _ordered_race(interleave, _submit, _discard_now)
                label = "submit-then-discard"
            outcomes.append((label, first.status_code, second.status_code))
            # A row set that survived a discard is a declaration about a record
            # that is gone; a discarded record with rows is the same defect read
            # the other way. Asserted per ordering, while this double is still the
            # one that saw the race.
            record_gone = ws.load_experiment(EXPERIMENT_ID) is None
            has_rows = bool(db.revisions or db.submissions)
            assert not (record_gone and has_rows), (
                f"{label}: history rows survive a record that was discarded"
            )
        leftover = ws.load_experiment(EXPERIMENT_ID)
        if leftover is not None:
            ws._remove_experiment_dir(leftover.dir, session_id=None)

    assert [row[0] for row in outcomes] == ["discard-then-submit", "submit-then-discard"]
    for label, first, second in outcomes:
        assert not (200 <= first < 300 and 200 <= second < 300), outcomes
        # And neither ordering may be vacuous: the LEADER always succeeds, because
        # it holds the lock over a record nothing else has touched.
        assert 200 <= first < 300, (label, first, second)


# =============================================================================
# 4. DISCARD vs RUN REMOVAL, and vs a run being CREATED
# =============================================================================


def test_a_run_removal_that_wins_refuses_the_discard_and_the_record_STANDS(
    workspace, monkeypatch
):
    """Both operations take the RECORD's validator, so the loser is a clean 412.

    ``POST .../runs/{id}/remove`` rewrites the record document, so it moves the
    record's ``ETag`` — and the discard, holding the pre-removal token, must be
    refused rather than destroy a record whose shape it no longer knows.

    The aftermath is asserted at BOTH levels: the record is still here, the removed
    run is still removed, and the surviving run's own validator did not move.
    """
    exp = _make(runs=("run A", "run B"))
    victim, survivor = [run.id for run in exp.sorted_runs()]
    client = _client()
    tag = _etag(client)
    survivor_version_before = exp.get_run(survivor).version_token()
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    removal, discard = _ordered_race(
        interleave,
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{victim}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": tag},
        ),
        lambda: _discard(client, if_match=tag),
    )

    assert removal.status_code == 200, removal.text
    assert discard.status_code == 412, discard.text
    assert discard.json()["error"] == "stale_write", discard.text
    assert discard.json()["experiment_id"] == EXPERIMENT_ID, discard.text

    after = ws.load_experiment(EXPERIMENT_ID)
    assert after is not None, "a 412 discarded the record anyway"
    assert [run.id for run in after.sorted_runs()] == [survivor]
    assert after.get_run(survivor).version_token() == survivor_version_before, (
        "the refused discard, or the removal, moved a surviving run's validator"
    )
    assert EXPERIMENT_ID in _listed_ids(client)


def test_a_discard_that_wins_leaves_a_run_removal_a_clean_404(workspace, monkeypatch):
    """Discard first: the removal is told the RECORD is gone, not the run.

    ``_not_found`` and ``_run_not_found`` are deliberately different bodies, and
    which one a client gets decides where it goes looking. A removal that arrived
    after the whole record went must say ``experiment_not_found``.
    """
    exp = _make(runs=("run A",))
    victim = exp.sorted_runs()[0].id
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws, "discard_experiment")

    discard, removal = _ordered_race(
        interleave,
        lambda: _discard(client, if_match=tag),
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs/{victim}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": tag},
        ),
    )

    assert discard.status_code == 200, discard.text
    assert discard.json()["discarded_run_count"] == 1, discard.text
    assert removal.status_code == 404, removal.text
    assert removal.json() == {"error": "experiment_not_found", "id": EXPERIMENT_ID}
    _assert_record_is_wholly_gone(client)


def test_a_record_cannot_GAIN_A_RUN_between_the_domain_refusal_and_the_delete(
    workspace, monkeypatch
):
    """The contract's refusal ORDER, attacked directly.

    The discard counts the runs it is about to destroy after its domain refusals.
    If a run could be created in the window between that decision and the removal,
    the response would UNDERSTATE what it destroyed — a false statement in the one
    body a scientist reads about an irreversible act.

    It cannot, and this pins why: the create is queued at the same ``record_lock``
    and does not enter until the record is gone, so it answers ``404`` and
    ``discarded_run_count`` is exactly what was there.
    """
    _make(runs=("run A",))
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, routes, "_submission_history_refusal")

    discard, create = _ordered_race(
        interleave,
        lambda: _discard(client, if_match=tag),
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs",
            json={"label": "a run created mid-discard"},
            headers={"If-Match": tag},
        ),
    )

    assert discard.status_code == 200, discard.text
    assert discard.json()["discarded_run_count"] == 1, discard.text
    assert create.status_code == 404, create.text
    assert create.json() == {"error": "experiment_not_found", "id": EXPERIMENT_ID}
    _assert_record_is_wholly_gone(client)


# =============================================================================
# 5. DISCARD vs EXPORT — can it gain a PUBLISHED ARTIFACT mid-flight?
# =============================================================================


def test_a_record_cannot_gain_a_PUBLISHED_ARTIFACT_between_the_check_and_the_delete(
    workspace, monkeypatch
):
    """The second half of the same attack, and the one with a file at stake.

    ``_published_stems`` asks the DISK, not the state, because an export writes the
    official record and its evidence sidecar BEFORE it persists the state. If an
    export could land in the window after that check, the discard would remove an
    official ISAAC record — the single act its authorization names first among the
    things it may not do.

    The discard is suspended one call later than ``_published_stems``, at
    ``_submission_history_refusal``, so the window under test is exactly "after the
    disk was inspected". The export is queued at the lock, never enters, and
    publishes nothing.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, routes, "_submission_history_refusal")

    discard, export = _ordered_race(
        interleave,
        lambda: _discard(client, if_match=tag),
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/export", headers={"If-Match": tag}
        ),
    )

    assert discard.status_code == 200, discard.text
    assert export.status_code == 404, export.text
    assert export.json() == {"error": "experiment_not_found", "id": EXPERIMENT_ID}
    _assert_record_is_wholly_gone(client)
    assert _scope_tree() == {}, (
        f"an official record or sidecar was orphaned: {sorted(_scope_tree())}"
    )


def test_an_export_that_wins_refuses_the_discard_and_keeps_BOTH_artifacts(
    workspace, monkeypatch
):
    """Export first: ``409 experiment_exported``, and both files survive byte-for-byte.

    Both halves of the published pair are named in the assertion rather than
    counted — ``test_discard_an_unsubmitted_experiment`` records that EITHER half
    alone is enough to refuse, so a test that only counted files could pass while
    one of them had been removed.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    export, discard = _ordered_race(
        interleave,
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/export", headers={"If-Match": tag}
        ),
        lambda: _discard(client, if_match=tag),
    )

    assert export.status_code == 200, export.text
    published = {name: data for name, data in _tree().items() if name.startswith("records/")}
    assert len(published) == 2, sorted(published)

    assert discard.status_code == 409, discard.text
    body = discard.json()
    assert body["error"] == "experiment_exported", body
    assert body["record_id"], body
    assert "Nothing was removed" in body["message"], body

    after = ws.load_experiment(EXPERIMENT_ID)
    assert after is not None
    assert {
        name: data for name, data in _tree().items() if name.startswith("records/")
    } == published, "a refused discard rewrote or removed a published artifact"
    assert after.record_id == body["record_id"]


# =============================================================================
# 6. THE DOMAIN REFUSAL IS NOT A PRECONDITION, EVEN UNDER A RACE
# =============================================================================


def test_a_racing_discard_of_an_EXPORTED_record_is_409_and_never_a_412(
    workspace, monkeypatch
):
    """A permanent condition must never wear a recoverable status code.

    The reset path in this repository once answered ``412 plan_digest_stale`` — a
    code whose documented meaning is *"recoverable in one further request"* — for a
    condition every retry would hit identically, after it had already destroyed a
    record. The discard's refusal ORDER exists to make that impossible here, and
    a race is where an order can quietly invert: the export moves the record's
    ``ETag``, so a naive implementation that checked the precondition first would
    answer ``412`` and send the client into a retry loop it can never leave.

    The token this discard holds IS stale — the export moved it — and the answer is
    still ``409``.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")

    export, discard = _ordered_race(
        interleave,
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/export", headers={"If-Match": tag}
        ),
        lambda: _discard(client, if_match=tag),
    )

    assert export.status_code == 200, export.text
    after = ws.load_experiment(EXPERIMENT_ID)
    assert after.etag() != tag, "the export did not move the validator; no order to test"
    assert discard.status_code == 409, discard.text
    assert discard.json()["error"] == "experiment_exported", discard.text
    # And the retry with a FRESH token is refused the same way, which is what makes
    # 409 rather than 412 the honest code: re-reading changes nothing.
    retry = _discard(client, if_match=_etag(client))
    assert retry.status_code == 409, retry.text
    assert retry.json()["error"] == "experiment_exported", retry.text
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_a_racing_UNCONFIRMED_discard_is_422_before_anything_else_is_decided(
    workspace, monkeypatch
):
    """``exists -> confirmed -> domain -> precondition`` holds under a race too.

    The record is exported by the leader and the follower's token is stale, so a
    build with the order wrong could answer ``409`` or ``412``. It must answer
    ``422``: the request is malformed, and telling a client to re-read a version or
    to un-export a record would send it to fix the wrong thing.
    """
    _make()
    client = _client()
    tag = _etag(client)
    interleave = _OrderedInterleave(monkeypatch, EXPERIMENT_ID)
    interleave.hold(monkeypatch, ws.Experiment, "save_versioned")
    before_versions = _versions(ws.load_experiment(EXPERIMENT_ID))

    export, discard = _ordered_race(
        interleave,
        lambda: client.post(
            f"/api/experiments/{EXPERIMENT_ID}/export", headers={"If-Match": tag}
        ),
        lambda: _discard(client, if_match=tag, body={}),
    )

    assert export.status_code == 200, export.text
    assert discard.status_code == 422, discard.text
    assert ws.load_experiment(EXPERIMENT_ID) is not None
    # The export legitimately moved the record; the DISCARD moved nothing further.
    assert _versions(ws.load_experiment(EXPERIMENT_ID)) != before_versions
    settled = _versions(ws.load_experiment(EXPERIMENT_ID))
    again = _discard(client, if_match=_etag(client), body={})
    assert again.status_code == 422, again.text
    assert _versions(ws.load_experiment(EXPERIMENT_ID)) == settled


# =============================================================================
# 7. A read concurrent with a discard
# =============================================================================


def test_a_read_in_flight_while_a_discard_holds_the_lock_is_never_a_500(
    workspace, monkeypatch
):
    """The list screen must not break because one record is being destroyed.

    This repository has a written record of a single malformed document taking
    ``GET /api/experiments`` down for every record with a ``500``. A record being
    REMOVED is the same hazard from the other direction, and the honest outcomes
    are two: the reader sees the record, or it does not. It must never see a server
    error, and it must never see a half-removed record.

    DETERMINISM WITHOUT THE ORDERING DEVICE, because reads deliberately do not take
    ``record_lock`` and so cannot be counted as an arrival at it. A two-event
    handshake pins the overlap instead: the discard is suspended one call before
    the removal, announces that it is INSIDE its critical section, and does not
    proceed until the reader has finished both reads. So the reads are guaranteed
    to run while the record is locked and still present — the exact window a
    half-removed read could appear in — and the safety-net timeout is asserted not
    to have expired.
    """
    _make()
    _make(OTHER_ID)
    client = _client()
    tag = _etag(client)

    inside = threading.Event()
    reads_done = threading.Event()
    seam: dict = {"timed_out": False}
    real_discard = ws.discard_experiment

    def _suspended(exp):
        inside.set()
        if not reads_done.wait(timeout=_EVENT_TIMEOUT_S):
            seam["timed_out"] = True
        return real_discard(exp)

    monkeypatch.setattr(ws, "discard_experiment", _suspended)

    reads: dict = {}

    def _reader():
        if not inside.wait(timeout=_EVENT_TIMEOUT_S):
            return
        try:
            reads["list"] = client.get("/api/experiments")
            reads["detail"] = client.get(f"/api/experiments/{EXPERIMENT_ID}")
        finally:
            reads_done.set()

    reader = threading.Thread(target=_reader, name="reader")
    reader.start()
    discard = _discard(client, if_match=tag)
    reader.join(timeout=_EVENT_TIMEOUT_S * 2)

    assert not reader.is_alive(), "the reads never returned — reads are behind the lock"
    assert not seam["timed_out"], "the reads did not overlap the discard's lock"
    assert set(reads) == {"list", "detail"}, "the reader never ran; nothing was proved"

    assert discard.status_code == 200, discard.text
    assert reads["list"].status_code == 200, reads["list"].text
    listed = {row["id"] for row in reads["list"].json()["experiments"]}
    assert OTHER_ID in listed, "an unrelated record vanished from the list"
    assert EXPERIMENT_ID in listed, (
        "the record was already absent from the list while the discard still held "
        "its lock — the removal happened before the operation committed to it"
    )
    assert reads["detail"].status_code == 200, reads["detail"].text
    assert reads["detail"].json()["id"] == EXPERIMENT_ID
    _assert_record_is_wholly_gone(client)
