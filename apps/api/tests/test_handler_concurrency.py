"""Handler-level concurrency: the compare-and-swap under test is the PRODUCTION one.

Why this file exists
--------------------
``test_version_contract.py`` §6 already proves that a load->compare->mutate->save
critical section guarded by ``ws.record_lock`` is race-safe — but it proves it about
a compare-and-swap **re-implemented in the test body** out of workspace primitives
(``record_lock`` / ``load_experiment`` / ``version_token`` / ``save_versioned``).
Neither of those two tests calls an HTTP handler. So if someone moved
``exp = ws.load_experiment(...)`` OUTSIDE ``with ws.record_lock(...)`` in
``routes.post_answers``, both of them would still pass while production silently
lost updates. The suite could not see it.

These tests close that hole: every mutation here goes through the real FastAPI app
(``create_app()`` + ``TestClient``), driven by real threads, so the code under test
is the handler's own composition — the order in which it loads, checks the
precondition, mutates and saves.

Determinism (why there is not a single sleep)
---------------------------------------------
A bare "start both threads at a barrier and hope they interleave" race is not a
test: the winner can finish before the loser even loads, in which case a lost-update
bug produces a PASS. So the interleaving is pinned with a rendezvous installed on
``ws.record_lock`` itself (:class:`_LockRendezvous`): the first two arrivals at
``record_lock(<target>)`` block until BOTH have arrived, then the real lock is
acquired as normal and the rendezvous is permanently open.

That seam changes only *timing*; it never changes what the handler does. What it
guarantees is the property the whole contract rests on: **whatever each request
loaded before it reached the lock, it loaded before either request could hold the
lock.** So a handler that loads outside the lock has both requests holding
pre-mutation state — deterministically, on every run — and a handler that loads
inside the lock has neither. No sleep is used as synchronisation anywhere; the only
timeouts are safety nets whose expiry is itself asserted to have NOT happened
(``rendezvous.timed_out``), so a future TestClient that serialised requests would
fail this file loudly rather than pass it vacuously.

Scope: synthetic canonical seeds only, read-only workspace access for *assertions*
only (never for a mutation), truth core untouched, no new dependency.
"""

from __future__ import annotations

import contextlib
import json
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

# Safety-net ceilings. NOTHING synchronises on these: every passing path trips its
# rendezvous/event immediately, and the tests assert the net was never hit. They
# exist so a genuine deadlock fails the run instead of hanging it.
_RENDEZVOUS_TIMEOUT_S = 15.0
_EVENT_TIMEOUT_S = 15.0
#: The concurrent read in test 4 gets its OWN, much shorter budget. It is a
#: fail-fast assertion, not a safety net: if reads are serialised behind the
#: write lock the GET never returns on its own, and waiting 15s to learn that
#: (or inheriting the writer's wait, as this test used to) turns a clean
#: failure into a hang.
_READ_TIMEOUT_S = 2.0

# Two still-pending asset blockers on the NEW-DRAFT seed (answers path). Two are
# needed because ``/answers`` only FILLS an OPEN blocker: once the first uri is
# answered it is no longer pending, so a later ``/answers`` naming it again is a
# documented no-op (correcting an answered field is ``/edit``'s job). The retry in
# test 5 therefore answers the SECOND open blocker.
PENDING_URI = "ssrl-archive://BL15-2/2099_run_000/raw/"
RETRY_URI = "ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi"
# The same asset, already answered, on the READY seed (edit path).
ANSWERED_URI = "ssrl-archive://BL15-2/2099_run_000/raw/"
# Two well-formed 64-hex sentinels the system can never invent, one per writer.
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The real app over a throwaway workspace (same idiom as test_version_contract)."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- read-only helpers (assertions only; never used to perform a mutation) -----


def _detail(client, exp_id) -> dict:
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _etag(client, exp_id) -> str:
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.headers["ETag"]


def _persisted(exp_id):
    exp = ws.load_experiment(exp_id)
    assert exp is not None, exp_id
    return exp


def _asset_sha(exp_id, uri) -> str | None:
    for asset in _persisted(exp_id).draft.get("assets") or []:
        if isinstance(asset, dict) and asset.get("uri") == uri:
            return asset.get("sha256")
    return None


def _state_json(exp_id) -> str:
    """The whole persisted state as text — used to prove a value is nowhere in it."""
    return json.dumps(_persisted(exp_id).to_state())


def _answers_body(uri, sha) -> dict:
    return {"confirmed_by_user": True, "answers": {uri: sha}}


# --- the deterministic interleaving seam --------------------------------------


class _LockRendezvous:
    """Hold the first ``parties`` arrivals at ``record_lock(target)`` until all arrive.

    Installed by monkeypatching ``ws.record_lock``, which ``routes`` reaches by
    module attribute (``ws.record_lock(...)``), so the production handler picks it
    up. The wrapper always delegates to the real context manager — it only decides
    *when* the acquisition attempt is made.

    Arrivals are counted for the target id only, and only the first ``parties`` of
    them block; every later call (including a re-entrant one from ``ensure_seeded``
    under the same RLock) passes straight through, so the seam cannot deadlock the
    reentrancy the real lock depends on.
    """

    def __init__(self, monkeypatch, target: str, parties: int = 2):
        self.target = target
        self.parties = parties
        self.timed_out = False
        self.arrivals = 0
        self._guard = threading.Lock()
        self._open = threading.Event()
        real = ws.record_lock

        @contextlib.contextmanager
        def _patched(experiment_id: str):
            rendezvous = False
            last = False
            with self._guard:
                if experiment_id == self.target and self.arrivals < self.parties:
                    self.arrivals += 1
                    rendezvous = True
                    last = self.arrivals == self.parties
            if rendezvous:
                if last:
                    self._open.set()
                elif not self._open.wait(timeout=_RENDEZVOUS_TIMEOUT_S):
                    # Never reached on a healthy run; recorded so the test can fail
                    # with a real explanation instead of hanging.
                    self.timed_out = True
            with real(experiment_id):
                yield

        monkeypatch.setattr(ws, "record_lock", _patched)


def _race(fns) -> list:
    """Run ``fns`` in parallel threads and return their results in order.

    The threads are only the transport; the pinned interleaving comes from the
    rendezvous, not from thread start order, so no start barrier is needed here.
    """
    results: list = [None] * len(fns)

    def runner(i, fn):
        results[i] = fn()

    threads = [
        threading.Thread(target=runner, args=(i, fn), name=f"writer-{i}")
        for i, fn in enumerate(fns)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_EVENT_TIMEOUT_S * 2)
        assert not t.is_alive(), f"{t.name} did not finish — the handler deadlocked"
    return results


def _outcome(responses) -> str:
    """A compact failure message: status + the first 160 chars of each body.

    Full bodies are several KB of pending-question JSON and drown the assertion.
    """
    return " | ".join(f"{r.status_code}: {r.text[:160]}" for r in responses)


# =============================================================================
# 1. Two concurrent /answers writers holding the SAME token
# =============================================================================


def test_concurrent_answers_same_token_exactly_one_wins(client, monkeypatch):
    """Two HTTP writers, one token: exactly one 200 and one 412, ``rev`` advances
    EXACTLY once, the winner's value is what is stored, and the loser's value is
    nowhere in the persisted state.

    This is the test that a handler loading its record OUTSIDE ``record_lock``
    cannot pass: both requests would then compare a pre-mutation token against a
    pre-mutation record, both would be accepted, and the second write would silently
    erase the first (last-write-wins).
    """
    target = ws.SEED_NEW_DRAFT_ID
    before = _detail(client, target)
    token = f'"{before["version"]}"'
    rendezvous = _LockRendezvous(monkeypatch, target)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json=_answers_body(PENDING_URI, SHA_A),
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json=_answers_body(PENDING_URI, SHA_B),
            headers={"If-Match": token},
        ),
    ])

    assert rendezvous.arrivals == 2, (
        "both requests must have reached the record lock — the race did not happen"
    )
    assert not rendezvous.timed_out, (
        "the two requests did not overlap; this run proved nothing about concurrency"
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 412], (
        f"exactly one writer may win the compare-and-swap, got {codes}: {_outcome(responses)}"
    )

    winner = next(r for r in responses if r.status_code == 200)
    loser = next(r for r in responses if r.status_code == 412)
    assert loser.json()["error"] == "stale_write"

    after = _detail(client, target)
    assert after["rev"] == before["rev"] + 1, "rev must advance exactly once, not twice"
    assert winner.json()["rev"] == after["rev"]

    # Which sentinel the winner sent is decided by the OS scheduler; which one is
    # stored is not — it must be the winner's, and only the winner's.
    # ``responses`` keeps the submission order, so index 0 is the SHA_A writer.
    won_sha, lost_sha = (SHA_A, SHA_B) if responses[0].status_code == 200 else (SHA_B, SHA_A)
    assert _asset_sha(target, PENDING_URI) == won_sha, "the winner's change was not persisted"
    assert lost_sha not in _state_json(target), (
        "the rejected writer's value reached the record — this is a lost update"
    )


# =============================================================================
# 2. The same contract on /edit
# =============================================================================


def test_concurrent_edit_same_token_exactly_one_wins(client, monkeypatch):
    """``/edit`` is a separate handler with its own copy of the critical section,
    so it needs its own proof: same token, two concurrent corrections of the SAME
    already-answered field -> one 200, one 412, one rev bump, no last-write-wins."""
    target = ws.SEED_READY_ID
    before = _detail(client, target)
    token = f'"{before["version"]}"'
    original_sha = _asset_sha(target, ANSWERED_URI)
    assert original_sha not in (None, SHA_A, SHA_B), original_sha
    rendezvous = _LockRendezvous(monkeypatch, target)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{target}/edit",
            json=_answers_body(ANSWERED_URI, SHA_A),
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/edit",
            json=_answers_body(ANSWERED_URI, SHA_B),
            headers={"If-Match": token},
        ),
    ])

    assert rendezvous.arrivals == 2 and not rendezvous.timed_out

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 412], (
        f"exactly one editor may win, got {codes}: {_outcome(responses)}"
    )
    assert next(r for r in responses if r.status_code == 412).json()["error"] == "stale_write"

    after = _detail(client, target)
    assert after["rev"] == before["rev"] + 1

    stored = _asset_sha(target, ANSWERED_URI)
    assert stored in (SHA_A, SHA_B), stored
    assert stored != original_sha, "the winning correction must actually have landed"
    other = SHA_B if stored == SHA_A else SHA_A
    assert other not in _state_json(target), (
        "the rejected editor's value reached the record — this is a lost update"
    )


# =============================================================================
# 3. Absent If-Match — refused 428 AND provably inert
# =============================================================================


@pytest.mark.parametrize(
    "endpoint,target,uri",
    [
        ("answers", ws.SEED_NEW_DRAFT_ID, PENDING_URI),
        ("edit", ws.SEED_READY_ID, ANSWERED_URI),
    ],
)
def test_absent_if_match_is_428_and_mutates_nothing(client, endpoint, target, uri):
    """A version-less mutation is refused 428 by the real handler, and the refusal is
    total: rev, version and the field's stored value are all unchanged afterwards.

    The status code alone is not enough — a handler that mutated and *then* refused
    would still return 428. The content assertions are what make this a mutation test.
    """
    before = _detail(client, target)
    before_sha = _asset_sha(target, uri)
    before_state = _state_json(target)

    r = client.post(f"/api/experiments/{target}/{endpoint}", json=_answers_body(uri, SHA_C))
    assert r.status_code == 428, r.text
    assert r.json()["error"] == "precondition_required"

    after = _detail(client, target)
    assert after["rev"] == before["rev"], "a refused mutation must not advance rev"
    assert after["version"] == before["version"]
    assert _asset_sha(target, uri) == before_sha
    assert SHA_C not in _state_json(target), "the refused value reached the record"
    assert _state_json(target) == before_state, "the persisted state changed at all"


# =============================================================================
# 4. A read concurrent with an in-flight write
# =============================================================================


def test_read_during_in_flight_write_sees_a_consistent_state(client, monkeypatch):
    """A GET issued while a write is mid-flight — the handler holds the record lock
    and the state file has NOT yet been replaced — returns promptly, and returns the
    pre-write revision: valid JSON, an ETag that is exactly the quoted body
    ``version``, and ``rev`` still at the pre-write value.

    WHAT THIS PROVES, precisely: reads are NOT serialised behind the per-record write
    lock. The GET completes while the writer is suspended inside that lock, which it
    could not do if reads acquired it.

    WHAT THIS DOES NOT PROVE — corrected after independent review, which is the whole
    reason this paragraph exists. The suspension point is *before* ``real_write`` is
    called, so the target file on disk is never partially written while the read
    happens: the reader sees the intact OLD file, not a torn one. This test therefore
    cannot fail on a non-atomic write, and a reviewer confirmed that by replacing
    ``atomic_write_text`` with a genuinely torn truncate-sleep-write — all six tests
    here stayed green.

    Do not read the assertions below as atomicity evidence. Atomicity of the replace
    is covered where it can actually be exercised:
    ``apps/api/tests/test_versioning.py::test_atomic_write_failure_leaves_original_intact``,
    which does fail under that mutation.
    """
    target = ws.SEED_NEW_DRAFT_ID
    before = _detail(client, target)
    token = f'"{before["version"]}"'

    write_reached = threading.Event()
    read_done = threading.Event()
    real_write = ws.atomic_write_text
    state_path = ws.workspace_root() / target / "experiment.json"

    def _suspended_write(path, text):
        # Only the target's own state file is suspended; everything else (records,
        # sidecars, other ids) is written normally.
        if path == state_path:
            write_reached.set()
            read_done.wait(timeout=_EVENT_TIMEOUT_S)
        return real_write(path, text)

    monkeypatch.setattr(ws, "atomic_write_text", _suspended_write)

    writer_result: dict = {}

    def writer():
        writer_result["response"] = client.post(
            f"/api/experiments/{target}/answers",
            json=_answers_body(PENDING_URI, SHA_A),
            headers={"If-Match": token},
        )

    t = threading.Thread(target=writer, name="in-flight-writer")
    t.start()
    try:
        assert write_reached.wait(timeout=_EVENT_TIMEOUT_S), (
            "the writer never reached the state-file write"
        )
        # The write is suspended INSIDE the record lock. This read must still work.
        #
        # It runs on its OWN thread with a short join, so that a regression which
        # serialises reads behind the write lock FAILS HERE in ~2s. Previously the
        # read ran inline with no timeout of its own and could only unblock when the
        # writer's 15s wait expired — so a "reads are now serialised" regression cost
        # 16s, and a variant where the writer waited longer would HANG the suite
        # instead of failing it. That is the opposite of what a safety net is for.
        read_result: dict = {}

        def reader():
            resp = client.get(f"/api/experiments/{target}")
            read_result["response"] = resp

        rt = threading.Thread(target=reader, name="concurrent-reader")
        rt.start()
        rt.join(timeout=_READ_TIMEOUT_S)
        assert not rt.is_alive(), (
            f"the GET did not complete within {_READ_TIMEOUT_S}s while a write was "
            "in flight — reads are being serialised behind the per-record write lock"
        )

        r = read_result["response"]
        assert r.status_code == 200, r.text
        mid = r.json()  # would raise if the response were not valid JSON
        assert r.headers["ETag"] == f'"{mid["version"]}"', "ETag and body version disagree"
        assert mid["version"].endswith(f".{mid['rev']}"), "version and rev disagree"
        assert mid["rev"] == before["rev"], (
            "the not-yet-replaced state file must still read as the pre-write revision"
        )
        assert not read_done.is_set()
    finally:
        read_done.set()
        t.join(timeout=_EVENT_TIMEOUT_S)
        assert not t.is_alive(), "the writer deadlocked"

    assert writer_result["response"].status_code == 200, writer_result["response"].text
    after = _detail(client, target)
    assert after["rev"] == before["rev"] + 1
    assert after["version"].endswith(f".{after['rev']}")
    assert _asset_sha(target, PENDING_URI) == SHA_A
    # The landed file parses. NOT an atomicity proof (see the docstring): the
    # write was suspended before it began, so nothing torn was ever on disk.
    json.loads(state_path.read_text(encoding="utf-8"))


# =============================================================================
# 5. Retry after conflict — the documented client recovery path
# =============================================================================


def test_conflict_loser_refreshes_and_retries_successfully(client, monkeypatch):
    """The 412 is recoverable, and recovering costs exactly one more revision.

    The loser re-reads (the 412 already echoes the current ETag, so this is one hop),
    retries with the fresh validator against the next open blocker, and is accepted.
    Total: rev advanced exactly TWICE — one accepted race write, one accepted retry —
    and the winner's value survives the retry. That is the difference from test 1: a
    write applied on top of a state the client has actually seen is accepted and
    additive; a write applied blind is refused.
    """
    target = ws.SEED_NEW_DRAFT_ID
    before = _detail(client, target)
    token = f'"{before["version"]}"'
    rendezvous = _LockRendezvous(monkeypatch, target)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json=_answers_body(PENDING_URI, SHA_A),
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json=_answers_body(PENDING_URI, SHA_B),
            headers={"If-Match": token},
        ),
    ])
    assert rendezvous.arrivals == 2 and not rendezvous.timed_out
    assert sorted(r.status_code for r in responses) == [200, 412], _outcome(responses)

    loser = next(r for r in responses if r.status_code == 412)
    # The 412 hands back the current validator, so no extra GET is required...
    echoed = loser.headers.get("ETag")
    assert echoed == _etag(client, target), "the 412 must echo the CURRENT ETag"

    after_race = _detail(client, target)
    assert after_race["rev"] == before["rev"] + 1

    # ...and retrying with it against the next open blocker is accepted.
    race_winner_sha = _asset_sha(target, PENDING_URI)
    assert race_winner_sha in (SHA_A, SHA_B), race_winner_sha
    retry = client.post(
        f"/api/experiments/{target}/answers",
        json=_answers_body(RETRY_URI, SHA_C),
        headers={"If-Match": echoed},
    )
    assert retry.status_code == 200, retry.text

    final = _detail(client, target)
    assert final["rev"] == before["rev"] + 2, (
        "one accepted race write plus one accepted retry is exactly two revisions"
    )
    assert _asset_sha(target, RETRY_URI) == SHA_C, "the retry's value must be the stored one"
    assert _asset_sha(target, PENDING_URI) == race_winner_sha, (
        "the retry must not have disturbed the race winner's value"
    )
    # A THIRD replay of the same, now doubly-stale, original token is still refused.
    stale_again = client.post(
        f"/api/experiments/{target}/answers",
        json=_answers_body(PENDING_URI, SHA_A),
        headers={"If-Match": token},
    )
    assert stale_again.status_code == 412, stale_again.text
    assert _detail(client, target)["rev"] == before["rev"] + 2
