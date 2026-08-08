"""Slice R1 — the Example-Workspace reset must not silently destroy confirmed work.

TEST-FIRST. Every test in §1–§3 was authored against the PRE-FIX code and observed
RED; the observed failures are quoted in the slice report. The three defects:

* **D1 — no precondition.** ``POST /api/demo/reset`` accepted only ``mode`` and
  ``confirmation``. A client that ran ``preview``, showed the operator a dialog and
  executed thirty seconds later destroyed anything committed in between: the operator
  approved a CLASSIFICATION that no longer held. The fix is a ``plan_digest``
  precondition — absent -> 428, stale -> 412, and neither mutates.
* **D2 — lock asymmetry.** Managed-legacy removal took NO per-record lock while
  canonical re-materialisation took one, so a concurrent writer to a managed-legacy
  record raced an unlocked ``rmtree`` of its directory.
* **D3 — ``final_count`` was asserted, not measured.** It was set to
  ``len(CANONICAL_IDS)`` on success, so a record created between classification and
  mutation survived while the response stated a count that was false.

Everything here is synthetic: the fixtures are the two committed reference files and
the committed simulated answers. The truth core is never bypassed and nothing in this
file writes outside ``tmp_path``.
"""

from __future__ import annotations

import contextlib
import json
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import tutorial_client, tutorial_ws

CONFIRM = "RESET EXAMPLE WORKSPACE"

CANONICAL_IDS = frozenset(ws.CANONICAL_IDS)

#: Failure-path bounds only. Every ordering below is forced by an ``Event``, never by
#: a sleep; a timeout here means the property under test is BROKEN, not that the
#: machine was slow.
#:
#: There is one thing a barrier cannot do: prove that something never happened. The
#: lock-handoff test below waits for the reset to ANNOUNCE that it wants a lock, and
#: under the fix that announcement is immediate. Under the defect it never comes, so
#: that wait must have a bound — kept SHORTER than the join bound, so the threads
#: always unwind and the assertion that fires names the defect instead of reporting a
#: hung thread.
HANDOFF_TIMEOUT = 10.0
JOIN_TIMEOUT = 30.0


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _post(client, body: dict):
    return client.post("/api/demo/reset", json=body)


def _preview(client) -> dict:
    r = _post(client, {"mode": "preview"})
    assert r.status_code == 200, r.text
    return r.json()


def _plan_digest(client) -> str:
    return _preview(client)["plan_digest"]


def _execute(client, *, token: str | None, confirmation: str | None = CONFIRM):
    body: dict = {"mode": "execute"}
    if confirmation is not None:
        body["confirmation"] = confirmation
    if token is not None:
        body["plan_digest"] = token
    return _post(client, body)


def _ids(client) -> set[str]:
    return {e["id"] for e in client.get("/api/experiments").json()["experiments"]}


def _dirs_on_disk() -> set[str]:
    """Ids present on disk, read WITHOUT ``ensure_seeded`` (so a missing canonical
    stays missing and a resurrected directory is visible as itself)."""
    return {e.id for e in tutorial_ws()._load_all_experiments()}


def _make_managed_legacy(title: str = "Older example record (example run)"):
    """A pre-canonical managed record: random id + the committed provenance marker."""
    return tutorial_ws().create_experiment(
        title=title,
        source={
            "description": ws.MANAGED_SOURCE_DESCRIPTION,
            "files": list(ws.SOURCE_FILES),
        },
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )


def _make_unrelated(title: str = "Some other experiment"):
    """A record with NO managed marker — classifies ambiguous, never removed."""
    return tutorial_ws().create_experiment(
        title=title,
        source={"description": "hand-authored / unknown provenance", "files": []},
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )


def _committed_answer_body() -> dict:
    """The committed simulated answers, exactly as the other suites post them."""
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


def _confirm_an_answer(client, experiment_id: str = ws.SEED_PARTIAL_ID) -> dict:
    """Confirm blocking answers through the REAL answers route (If-Match and all).

    Returns the response body, so a caller can assert the work landed.
    """
    detail = client.get(f"/api/experiments/{experiment_id}")
    assert detail.status_code == 200, detail.text
    r = client.post(
        f"/api/experiments/{experiment_id}/answers",
        json=_committed_answer_body(),
        headers={"If-Match": detail.headers["ETag"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["invalidation"]["changed"] is True, "the answer must really change the draft"
    return r.json()


# --- 1. D1 — the execute precondition ---------------------------------------


def test_d1_preview_returns_a_plan_digest(client):
    """The classification the operator approves is identified by an opaque token."""
    body = _preview(client)
    assert isinstance(body.get("plan_digest"), str) and body["plan_digest"]
    # path-free, exactly like every other field on this response
    assert str(tutorial_ws().workspace_root()) not in body["plan_digest"]


def test_d1_execute_without_a_plan_digest_mutates_nothing(client):
    """D1, the destructive half: a token-less execute used to succeed and wipe work.

    PRE-FIX OBSERVED: 200 + ``removed_count: 1`` — the managed-legacy record was
    gone and the confirmed answer on the canonical example was rebuilt away.
    """
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _confirm_an_answer(client)
    before = _dirs_on_disk()

    r = _execute(client, token=None)

    assert r.status_code == 428, r.text
    assert r.json()["refusal_reason"] == "plan_digest_required"
    assert r.json()["removed_count"] == 0
    assert _dirs_on_disk() == before
    assert legacy.id in _dirs_on_disk()


def test_d1_stale_execute_cannot_destroy_work_committed_after_the_preview(client):
    """The exact 30-seconds-later scenario, end to end through the HTTP contract."""
    tutorial_ws().ensure_tutorial_seeded()
    token = _plan_digest(client)  # the dialog opens and the operator reads the counts

    # ...and then, before they press the button, work is committed.
    _confirm_an_answer(client)
    drafted = client.get(f"/api/experiments/{ws.SEED_PARTIAL_ID}").json()

    r = _execute(client, token=token)

    assert r.status_code == 412, r.text
    assert r.json()["refusal_reason"] == "plan_digest_stale"
    assert r.json()["removed_count"] == 0
    # the confirmed work is byte-identical afterwards
    after = client.get(f"/api/experiments/{ws.SEED_PARTIAL_ID}").json()
    assert after == drafted
    assert after["rev"] == drafted["rev"]


def test_d1_a_record_created_after_the_preview_makes_the_token_stale(client):
    tutorial_ws().ensure_tutorial_seeded()
    token = _plan_digest(client)
    legacy = _make_managed_legacy()
    r = _execute(client, token=token)
    assert r.status_code == 412
    assert legacy.id in _dirs_on_disk()


def test_d1_a_record_removed_after_the_preview_makes_the_token_stale(client):
    import shutil

    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    token = _plan_digest(client)
    shutil.rmtree(tutorial_ws().workspace_root() / legacy.id)
    assert _execute(client, token=token).status_code == 412


def test_d1_an_export_after_the_preview_makes_the_token_stale(client):
    tutorial_ws().ensure_tutorial_seeded()
    token = _plan_digest(client)
    detail = client.get(f"/api/experiments/{ws.SEED_READY_ID}")
    r = client.post(
        f"/api/experiments/{ws.SEED_READY_ID}/export",
        headers={"If-Match": detail.headers["ETag"]},
    )
    assert r.status_code == 200, r.text
    assert _execute(client, token=token).status_code == 412


def test_d1_an_unchanged_workspace_keeps_its_token_stable(client):
    """The token must not churn on its own, or every reset would 412 spuriously."""
    tutorial_ws().ensure_tutorial_seeded()
    first = _plan_digest(client)
    # reads, previews and a no-op re-preview change nothing
    client.get("/api/experiments")
    client.get(f"/api/experiments/{ws.SEED_DONE_ID}")
    assert _plan_digest(client) == first


def test_d1_a_fresh_token_executes_and_reports_a_measured_result(client):
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    token = _plan_digest(client)
    r = _execute(client, token=token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["refusal_reason"] is None
    assert body["removed_count"] == 1
    assert body["final_count"] == 5
    assert _ids(client) == CANONICAL_IDS


def test_d1_the_confirmation_phrase_is_still_required_and_is_checked_first(client):
    """409 stays 409: a wrong phrase is distinguishable from a stale precondition."""
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    token = _plan_digest(client)
    for bad in (None, "", "reset", "RESET", "reset example workspace", "RESET SYNTHETIC DEMO"):
        r = _execute(client, token=token, confirmation=bad)
        assert r.status_code == 409, (bad, r.status_code)
        assert r.json()["refusal_reason"] == "confirmation_required"
    assert legacy.id in _dirs_on_disk()


def test_d1_an_ambiguous_record_still_refuses_with_409_not_412(client):
    tutorial_ws().ensure_tutorial_seeded()
    unrelated = _make_unrelated()
    legacy = _make_managed_legacy()
    token = _plan_digest(client)
    r = _execute(client, token=token)
    assert r.status_code == 409, r.text
    assert r.json()["refusal_reason"] == "ambiguous_records_present"
    assert {unrelated.id, legacy.id} <= _dirs_on_disk()


def test_d1_a_stale_token_beats_an_ambiguous_record_to_the_refusal(client):
    """Precondition first: a client holding a stale plan must be told to re-preview,
    not handed a classification verdict about a workspace it has not seen."""
    tutorial_ws().ensure_tutorial_seeded()
    token = _plan_digest(client)
    _make_unrelated()
    r = _execute(client, token=token)
    assert r.status_code == 412
    assert r.json()["refusal_reason"] == "plan_digest_stale"


def test_d1_the_stale_refusal_echoes_the_current_token_for_a_one_hop_recovery(client):
    tutorial_ws().ensure_tutorial_seeded()
    stale = _plan_digest(client)
    _make_managed_legacy()
    r = _execute(client, token=stale)
    assert r.status_code == 412
    fresh = r.json()["plan_digest"]
    assert fresh != stale
    # the echoed token is immediately usable — no second preview required
    assert _execute(client, token=fresh).status_code == 200


def test_d1_repeated_reset_with_a_fresh_token_is_idempotent_in_content(client):
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    first: dict | None = None
    for _ in range(3):
        r = _execute(client, token=_plan_digest(client))
        assert r.status_code == 200, r.text
        content = {
            e.id: (e.title, e.status(), e.exported()) for e in tutorial_ws().list_experiments()
        }
        if first is None:
            first = content
        else:
            assert content == first
        assert _ids(client) == CANONICAL_IDS


def test_d1_a_preview_never_needs_or_accepts_a_token(client):
    """A preview mutates nothing, so it has no precondition to satisfy."""
    tutorial_ws().ensure_tutorial_seeded()
    assert _post(client, {"mode": "preview"}).status_code == 200
    # ...but the request model still refuses anything it does not name
    assert _post(client, {"mode": "preview", "ids": ["x"]}).status_code == 422
    assert _post(client, {"mode": "execute", "path": "/etc/passwd"}).status_code == 422


def test_d1_no_response_leaks_a_filesystem_path(client):
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    root = str(tutorial_ws().workspace_root())
    bodies = [
        _preview(client),
        _execute(client, token=None).json(),
        _execute(client, token="rp1.deadbeef").json(),
        _execute(client, token=_plan_digest(client)).json(),
    ]
    for body in bodies:
        blob = json.dumps(body)
        assert root not in blob
        for fragment in ("/tmp/", "/private/", "isaac-ui-workspace"):
            assert fragment not in blob, (fragment, blob)


# --- 2. D2 — every id the reset touches is locked -----------------------------


@contextlib.contextmanager
def _record_lock_keys(monkeypatch, keys: list[str]):
    """Record every key the REAL ``record_lock`` computes, then delegate.

    WHY THIS EXISTS SEPARATELY FROM THE SPIES BELOW. Each spy in this file accepts
    ``session_id`` and forwards it to the real lock, and independent review found that
    nothing pinned the forwarding: deleting ``session_id=session_id`` left every spy
    compiling, delegating and passing, while the lock it took became ``"/<id>"``
    instead of ``"<session>/<id>"`` (``workspace._lock_key``) — a DIFFERENT key from
    the one production and any concurrent writer use, so nothing would have serialised.

    An assertion written inside a spy cannot catch that, because it can only restate
    the ``session_id`` the spy already has. So the key is captured where it is actually
    computed, by wrapping ``ws._lock_key`` (which ``record_lock`` reaches as a module
    global). This observes; it changes no behaviour.
    """
    real_key = ws._lock_key

    def recording(experiment_id: str, session_id: str | None) -> str:
        key = real_key(experiment_id, session_id)
        keys.append(key)
        return key

    monkeypatch.setattr(ws, "_lock_key", recording)
    yield


def _assert_scope_qualified(keys: list[str], session_id: str, ids) -> None:
    """Every lock taken for ``ids`` was qualified by ``session_id``."""
    assert keys, "no record lock was taken at all"
    for exp_id in ids:
        expected = f"{session_id}/{exp_id}"
        assert expected in keys, (
            f"{exp_id} was locked as one of {sorted(set(keys))}, expected {expected!r} — "
            f"an unscoped lock contends on a different key than production's"
        )
    unscoped = sorted({k for k in keys if not k.startswith(f"{session_id}/")})
    assert not unscoped, f"these locks were not scope-qualified: {unscoped}"


@contextlib.contextmanager
def _lock_spy(monkeypatch, held: set[str], entered: list[str], keys: list[str] | None = None):
    """Replace ``ws.record_lock`` with a spy that records which ids are held.

    ``keys``, when given, additionally collects the scope-qualified key the REAL lock
    computed for each acquisition — see :func:`_record_lock_keys` for why that is not
    the same thing as recording the ``session_id`` this spy received.
    """
    real_lock = ws.record_lock

    @contextlib.contextmanager
    def spy(experiment_id: str, *, session_id: str | None = None):
        entered.append(experiment_id)
        with real_lock(experiment_id, session_id=session_id):
            held.add(experiment_id)
            try:
                yield
            finally:
                held.discard(experiment_id)

    monkeypatch.setattr(ws, "record_lock", spy)
    if keys is None:
        yield
        return
    with _record_lock_keys(monkeypatch, keys):
        yield


def test_d2_managed_legacy_removal_runs_under_that_records_lock(client, monkeypatch):
    """D2, stated as the property rather than as a race.

    PRE-FIX OBSERVED: ``{legacy.id: False}`` — the ``rmtree`` ran with no lock held
    for that id, while the canonical re-materialisation beside it held one.
    """
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()

    held: set[str] = set()
    entered: list[str] = []
    keys: list[str] = []
    removed_under_lock: dict[str, bool] = {}
    real_remove = ws.remove_experiment

    def spy_remove(exp):
        removed_under_lock[exp.id] = exp.id in held
        real_remove(exp)

    with _lock_spy(monkeypatch, held, entered, keys):
        monkeypatch.setattr(ws, "remove_experiment", spy_remove)
        tutorial_ws().reset_to_canonical_seed(dry_run=False)

    assert removed_under_lock == {legacy.id: True}
    # ...and the canonical re-materialisation is still locked, as it always was
    assert CANONICAL_IDS <= set(entered)
    assert legacy.id in entered
    # no lock is left held
    assert held == set()
    # ...and every one of those locks was the SESSION's, not the ordinary workspace's.
    # Without this the spy would survive `session_id` being dropped from the
    # forwarding, and would then contend on a key production never uses.
    _assert_scope_qualified(keys, tutorial_ws().session_id, {*CANONICAL_IDS, legacy.id})


def test_d2_the_reset_holds_at_most_one_record_lock_at_a_time(client, monkeypatch):
    """Deadlock-freedom by construction, pinned.

    A caller CAN hold two record locks at once. The example this docstring used to
    give no longer exists — it said a mutation handler holds ``record_lock(id)`` and
    then calls ``load_experiment`` -> ``ensure_seeded``, which might take another id's
    lock to heal a missing canonical; ``workspace.py:290-297`` records that reads no
    longer seed, and ``ensure_seeded`` is gone (``ensure_tutorial_seeded`` runs only at
    session creation and holds at most one lock at a time by construction). The
    PROPERTY under test never depended on that example: if the reset held two locks
    while any other caller held two, a lock-ordering cycle would be possible, so the
    reset must take them strictly one at a time. That is what is asserted below, and
    it is asserted about the reset alone.
    """
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    _make_managed_legacy()

    held: set[str] = set()
    entered: list[str] = []
    keys: list[str] = []
    high_water = []
    real_lock = ws.record_lock

    @contextlib.contextmanager
    def spy(experiment_id: str, *, session_id: str | None = None):
        entered.append(experiment_id)
        with real_lock(experiment_id, session_id=session_id):
            held.add(experiment_id)
            high_water.append(len(held))
            try:
                yield
            finally:
                held.discard(experiment_id)

    monkeypatch.setattr(ws, "record_lock", spy)
    with _record_lock_keys(monkeypatch, keys):
        tutorial_ws().reset_to_canonical_seed(dry_run=False)

    assert high_water, "the reset took no record lock at all"
    assert max(high_water) == 1, f"the reset held {max(high_water)} record locks at once"
    # "At most one at a time" is only the property that matters if the ONE is the
    # right lock. This spy also survived `session_id` being dropped from the
    # forwarding, which would have made every acquisition here contend on a key the
    # production reset never takes — so the key is pinned too.
    _assert_scope_qualified(keys, tutorial_ws().session_id, CANONICAL_IDS)


def test_d2_a_concurrent_managed_legacy_write_is_not_lost_and_leaves_no_stub(
    client, monkeypatch
):
    """The interleaving D2 allowed, forced deterministically with events.

    A writer holds ``record_lock(legacy.id)``, reads the record, and then waits for
    the reset thread to SIGNAL that it wants that same lock before finishing its
    write. Ordering is decided by events, never by sleeping.

    * FIXED: the reset blocks on the lock, the writer's ``atomic_write_text``
      completes, the writer releases, the reset removes the directory once — so the
      directory is GONE and the workspace is exactly the canonical five.
    * PRE-FIX: the reset never asks for that lock, so the signal never comes, the
      writer proceeds unsynchronised, and ``atomic_write_text`` re-creates the
      directory it was mid-way through deleting (``mkdir(parents=True)``) — leaving a
      resurrected stub holding a lone ``experiment.json`` and no ``records/``.

    The key is pinned too, via :func:`_record_lock_keys` — the third of the three lock
    spies in this file to get it. It was the one left without the guard, and unlike the
    other two it is behaviourally compensated: this test contends two real threads on
    the SAME key, so dropping ``session_id`` from the forwarding makes the reset take
    ``"/<id>"`` while the writer takes ``"<session>/<id>"``, the two stop serialising,
    and the resurrected-stub assertion at the end fails on its own. The guard is added
    for consistency and for a legible failure — "these locks were not scope-qualified"
    names the cause, where a resurrected directory only shows the symptom.
    """
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    state_path = tutorial_ws().workspace_root() / legacy.id / "experiment.json"

    reset_wants_the_lock = threading.Event()
    writer_is_holding = threading.Event()
    errors: list[BaseException] = []

    real_lock = ws.record_lock

    @contextlib.contextmanager
    def announcing_lock(experiment_id: str, *, session_id: str | None = None):
        # Announce the INTENT before blocking, so the writer can finish first.
        if experiment_id == legacy.id:
            reset_wants_the_lock.set()
        with real_lock(experiment_id, session_id=session_id):
            yield

    session_id = tutorial_ws().session_id

    def writer():
        try:
            # The SAME scope-qualified lock the reset takes — the point of the test is
            # that the two contend, and a differently-scoped key would not.
            with real_lock(legacy.id, session_id=session_id):
                writer_is_holding.set()
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["title"] = "written by a concurrent operator"
                # Wait for the reset to declare it wants this lock. Under the FIX
                # that always happens; the timeout is the failure bound only.
                reset_wants_the_lock.wait(timeout=HANDOFF_TIMEOUT)
                ws.atomic_write_text(state_path, json.dumps(state, indent=2) + "\n")
        except BaseException as exc:  # noqa: BLE001 - any raise is a failure
            errors.append(exc)

    def resetter():
        try:
            tutorial_ws().reset_to_canonical_seed(dry_run=False)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    keys: list[str] = []
    monkeypatch.setattr(ws, "record_lock", announcing_lock)
    # Installed BEFORE the writer starts: the writer holds ``real_lock`` directly, and
    # its key is exactly the one that has to match the reset's for the two to serialise.
    with _record_lock_keys(monkeypatch, keys):
        w = threading.Thread(target=writer, name="writer")
        w.start()
        assert writer_is_holding.wait(timeout=JOIN_TIMEOUT)
        r = threading.Thread(target=resetter, name="resetter")
        r.start()
        w.join(timeout=JOIN_TIMEOUT)
        r.join(timeout=JOIN_TIMEOUT)
    assert not w.is_alive() and not r.is_alive(), "a thread never finished"
    _assert_scope_qualified(keys, session_id, {*CANONICAL_IDS, legacy.id})
    assert reset_wants_the_lock.is_set(), (
        "the reset never asked for record_lock(<the managed-legacy id>) — its removal "
        "is unlocked, so a concurrent writer to that record races an rmtree of its "
        "directory (D2)"
    )
    assert errors == [], f"concurrent write + reset raised: {errors!r}"

    # No partially-removed / resurrected directory, and no lost canonical.
    assert not (tutorial_ws().workspace_root() / legacy.id).exists()
    assert _dirs_on_disk() == CANONICAL_IDS


# --- 3. D3 — final_count is measured ----------------------------------------


def test_d3_final_count_is_measured_after_the_mutation(client, monkeypatch):
    """A record that appears between classification and mutation survives, so the
    reported count must include it.

    PRE-FIX OBSERVED: ``final_count == 5`` while the workspace really held 6.
    """
    tutorial_ws().ensure_tutorial_seeded()
    real_load = ws._load_all_experiments
    appeared: list[str] = []

    def load_then_create_once(session_id=None):
        out = real_load(session_id)
        if not appeared:
            appeared.append(_make_unrelated("appeared after classification").id)
        return out

    monkeypatch.setattr(ws, "_load_all_experiments", load_then_create_once)
    data = tutorial_ws().reset_to_canonical_seed(dry_run=False)

    assert data["refused"] is False
    assert len(appeared) == 1
    on_disk = {e.id for e in real_load(tutorial_ws().session_id)}
    assert appeared[0] in on_disk
    assert len(on_disk) == 6
    assert data["final_count"] == 6, "final_count must be measured, not asserted"


def test_d3_a_refused_preview_reports_the_count_it_measured(client):
    tutorial_ws().ensure_tutorial_seeded()
    _make_unrelated()
    body = _preview(client)
    assert body["status"] == "refused"
    assert body["previous_count"] == 6
    assert body["final_count"] == 6  # a refusal changes nothing
    assert body["removed_count"] == 0


# --- 4. partial failure never reports success -------------------------------


def test_a_failure_mid_reset_never_reports_success(tmp_path, monkeypatch):
    """Inject a raise between the removal and the last re-materialisation.

    The reset must NOT return a body claiming success. The workspace is left
    incomplete (that is what a crash means), and the honest post-condition is that a
    subsequent reset converges — which is asserted here rather than assumed.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    c = tutorial_client(create_app(), raise_server_exceptions=False)
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    token = _plan_digest(c)

    real_materialise = ws._materialise_seed
    calls: list[str] = []

    def boom(spec, *, session_id):
        calls.append(spec.id)
        if len(calls) == 3:
            raise RuntimeError("injected mid-reset failure")
        return real_materialise(spec, session_id=session_id)

    monkeypatch.setattr(ws, "_materialise_seed", boom)
    r = _execute(c, token=token)
    assert r.status_code == 500
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("status") != "ok"
    assert "final_count" not in body
    # the injected failure really did land mid-way (not before, not after)
    assert len(calls) == 3
    assert legacy.id not in _dirs_on_disk()

    # and the state is recoverable: a fresh reset converges to the canonical five
    monkeypatch.setattr(ws, "_materialise_seed", real_materialise)
    ok = _execute(c, token=_plan_digest(c))
    assert ok.status_code == 200, ok.text
    assert ok.json()["final_count"] == 5
    assert _dirs_on_disk() == CANONICAL_IDS


# --- 5. the at-risk disclosure is derived, never guessed ---------------------


def test_at_risk_is_zero_on_an_untouched_workspace(client):
    tutorial_ws().ensure_tutorial_seeded()
    at_risk = _preview(client)["at_risk"]
    assert at_risk == {
        "confirmed_answers": 0,
        "examples_with_progress": 0,
        "exported_artifacts": 0,
    }


def test_at_risk_counts_a_confirmed_answer_and_the_example_carrying_it(client):
    tutorial_ws().ensure_tutorial_seeded()
    _confirm_an_answer(client)
    at_risk = _preview(client)["at_risk"]
    assert at_risk["confirmed_answers"] == 1
    assert at_risk["examples_with_progress"] == 1
    assert at_risk["exported_artifacts"] == 0


def test_at_risk_counts_a_second_answer_on_the_same_example_separately(client):
    tutorial_ws().ensure_tutorial_seeded()
    _confirm_an_answer(client, ws.SEED_PARTIAL_ID)
    _confirm_an_answer(client, ws.SEED_NEW_DRAFT_ID)
    at_risk = _preview(client)["at_risk"]
    assert at_risk["confirmed_answers"] == 2
    assert at_risk["examples_with_progress"] == 2


def test_at_risk_counts_an_export_the_operator_made(client):
    tutorial_ws().ensure_tutorial_seeded()
    detail = client.get(f"/api/experiments/{ws.SEED_READY_ID}")
    r = client.post(
        f"/api/experiments/{ws.SEED_READY_ID}/export",
        headers={"If-Match": detail.headers["ETag"]},
    )
    assert r.status_code == 200, r.text
    at_risk = _preview(client)["at_risk"]
    # the built-in exported example is NOT counted — it is part of the baseline
    assert at_risk["exported_artifacts"] == 1
    assert at_risk["examples_with_progress"] == 1


def test_at_risk_ignores_ambiguous_records_which_the_reset_never_touches(client):
    tutorial_ws().ensure_tutorial_seeded()
    unrelated = _make_unrelated()
    # give the unrelated record an answer of its own
    _confirm_an_answer(client, unrelated.id)
    at_risk = _preview(client)["at_risk"]
    assert at_risk["confirmed_answers"] == 0, "an untouched record is not at risk"


def test_at_risk_counts_answers_on_a_managed_legacy_record_that_will_be_removed(client):
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _confirm_an_answer(client, legacy.id)
    at_risk = _preview(client)["at_risk"]
    assert at_risk["confirmed_answers"] == 1
    # a managed-legacy record is not one of the five examples, so it is reported by
    # `legacy_count`/`removable`, not by `examples_with_progress`
    assert at_risk["examples_with_progress"] == 0


def test_at_risk_returns_to_zero_after_a_reset(client):
    tutorial_ws().ensure_tutorial_seeded()
    _confirm_an_answer(client)
    assert _preview(client)["at_risk"]["confirmed_answers"] == 1
    assert _execute(client, token=_plan_digest(client)).status_code == 200
    assert _preview(client)["at_risk"] == {
        "confirmed_answers": 0,
        "examples_with_progress": 0,
        "exported_artifacts": 0,
    }


# --- 6. the governance gate still comes first -------------------------------


def test_the_synthetic_only_gate_precedes_every_precondition(client, monkeypatch):
    tutorial_ws().ensure_tutorial_seeded()
    token = _plan_digest(client)
    monkeypatch.setattr(ws, "is_synthetic_only", lambda: False, raising=False)
    for body in (
        {"mode": "execute", "confirmation": CONFIRM, "plan_digest": token},
        {"mode": "execute", "confirmation": CONFIRM},
        {"mode": "execute"},
    ):
        r = _post(client, body)
        assert r.status_code == 403, (body, r.status_code)
        assert r.json()["refusal_reason"] == "not_synthetic_only"
    assert _dirs_on_disk() == CANONICAL_IDS


# --- 7. C2 — a write inside the check->mutate window ------------------------
#
# THE DEFECT, and it was documented in the code that carried it
# (``workspace.py`` on ``_reset_lock``): the reset held ``_reset_lock`` across the
# whole operation and took ``record_lock(id)`` only at the moment it mutated that id,
# while a per-record writer (``/answers``, ``/edit``, ``/export``) took ONLY
# ``record_lock``. So the span from the classification snapshot to the per-id mutation
# was open. A write that landed there returned 200 to its caller and was then
# destroyed by a reset that reported success — and the ``at_risk`` summary in that
# success body, computed from the pre-write snapshot, under-reported by exactly what
# had just been destroyed.
#
# THE PROPERTY these two tests assert, and that no test above asserts: a write in that
# window either SURVIVES or the reset REFUSES. Never both false. It is deliberately
# written as a disjunction first — the disjunction is the contract, and a future
# implementation may legitimately satisfy it the other way round — and only then
# narrowed to what this implementation actually does.
#
# THE FIX IS NOT A NEW LOCK. Adding ``_reset_lock`` to the writers would put a
# workspace-wide lock on the hot mutation path and invert the documented ordering, so
# the reset instead re-checks THAT ONE RECORD's plan-digest row inside the same
# ``record_lock`` it is about to mutate under. Deadlock-freedom is therefore
# unchanged, and ``test_d2_the_reset_holds_at_most_one_record_lock_at_a_time`` above
# still pins it.


def test_c2_a_write_landing_after_the_digest_check_survives_or_the_reset_refuses(
    client, monkeypatch
):
    """The C2 interleaving, forced deterministically with events.

    Modelled on ``test_d2_a_concurrent_managed_legacy_write_is_not_lost_and_leaves_no_stub``
    but with the ordering INVERTED. There, the writer went first and the reset waited.
    Here the RESET goes first: it is held inside ``_plan_digest`` — after the
    classification snapshot has been taken and while the digest is being computed from
    it, which is the top of the window — and only then does the writer commit, through
    the real ``/answers`` route, ``If-Match`` and all. The reset is released only once
    that write has fully returned.

    So the reset resumes holding a digest that matches the token it was given (both
    were computed from the same pre-write snapshot), walks past the workspace-wide
    precondition, and arrives at the mutation with a record on disk that nobody told
    it about. That is the whole defect, reproduced without a sleep anywhere.

    PRE-FIX: the reset returns ``refused: False`` and the confirmed answer is gone.
    FIXED: the per-record row for that id no longer matches, so the reset aborts it
    unmutated and refuses ``plan_digest_stale``; the answer is byte-identical after.

    The reset is driven DIRECTLY (not over HTTP) for the same reason
    ``test_concurrent_execute_is_safe`` gives: the ``TestClient`` portal serialises
    HTTP requests, so two concurrent requests would not interleave at all. Exactly one
    of the two actors here uses HTTP, and it is the writer — the one whose 200 the
    property is about.
    """
    tutorial_ws().ensure_tutorial_seeded()
    # A managed-legacy record makes the partial abort MEASURABLE: it is removed before
    # the canonical loop reaches the written-to example, so `previous_count` (6) and
    # the true post-abort count (5) differ, and a `final_count` copied from the
    # snapshot rather than measured would say 6.
    legacy = _make_managed_legacy()
    token = _plan_digest(client)  # the classification the operator approved
    session_id = tutorial_ws().session_id

    reset_is_in_the_window = threading.Event()
    write_has_returned = threading.Event()
    errors: list[BaseException] = []
    result: list[dict] = []

    real_plan_digest = ws._plan_digest

    def holding_plan_digest(buckets):
        """Compute the digest exactly as production does, then hold — ONCE.

        One-shot: ``reset_to_canonical_seed`` also calls ``_plan_digest`` again at the
        end to report the CURRENT digest, and holding there would deadlock the test
        against a writer that has already finished.
        """
        out = real_plan_digest(buckets)
        if not reset_is_in_the_window.is_set():
            reset_is_in_the_window.set()
            assert write_has_returned.wait(timeout=HANDOFF_TIMEOUT), (
                "the writer never reported completing — the window was never entered"
            )
        return out

    def resetter():
        try:
            result.append(
                ws.reset_to_canonical_seed(
                    dry_run=False, expected_plan_digest=token, session_id=session_id
                )
            )
        except BaseException as exc:  # noqa: BLE001 - any raise is a failure
            errors.append(exc)

    monkeypatch.setattr(ws, "_plan_digest", holding_plan_digest)
    r = threading.Thread(target=resetter, name="resetter")
    r.start()
    try:
        assert reset_is_in_the_window.wait(timeout=JOIN_TIMEOUT), (
            "the reset never reached its digest computation"
        )
        # The write lands INSIDE the window, through the real route, and returns 200.
        _confirm_an_answer(client, ws.SEED_PARTIAL_ID)
        committed = client.get(f"/api/experiments/{ws.SEED_PARTIAL_ID}").json()
        assert committed["rev"] > 0, "the write must really have been persisted"
    finally:
        write_has_returned.set()
        r.join(timeout=JOIN_TIMEOUT)
    assert not r.is_alive(), "the reset thread never finished"
    assert errors == [], f"the reset raised: {errors!r}"

    data = result[0]
    after = client.get(f"/api/experiments/{ws.SEED_PARTIAL_ID}").json()
    write_survived = after == committed
    reset_refused = data["refused"] is True

    # THE CONTRACT. Stated as the disjunction, because either outcome is honest and
    # only "neither" is the defect: a write that returned 200, was destroyed, and was
    # never mentioned.
    assert write_survived or reset_refused, (
        "C2: a write that landed between the reset's digest check and its per-id "
        "mutation was DESTROYED while the reset reported success — the operator's "
        "confirmed answer is gone and no response ever said so"
    )

    # ...and now what this implementation actually does, so a regression that trades
    # one arm of the disjunction for the other is still visible in the diff.
    assert reset_refused, "the reset must abort rather than mutate against a stale row"
    assert data["refusal"] == "plan_digest_stale", data["refusal"]
    assert write_survived, "the aborted id must be left exactly as the writer left it"
    assert after["rev"] == committed["rev"] > 0

    # A PARTIAL ABORT MUST NEVER REPORT SUCCESS, AND MUST NOT LIE ABOUT WHAT IT LEFT.
    # `final_count` is measured, not copied from the pre-reset snapshot, so it matches
    # the disk even though ids before the aborted one were already mutated.
    assert data["final_count"] == len(_dirs_on_disk()), (
        "a partial abort must MEASURE what it left behind"
    )
    assert data["previous_count"] == 6
    assert legacy.id not in _dirs_on_disk(), "the abort happened after the legacy removal"
    assert data["removed_count"] == 1

    # The refusal echoes the CURRENT digest, so the operator recovers in one hop —
    # exactly as every other stale refusal on this endpoint does.
    assert data["plan_digest"] != token
    assert _execute(client, token=_plan_digest(client)).status_code == 200
    assert _dirs_on_disk() == CANONICAL_IDS


def test_c2_a_write_to_a_managed_legacy_record_in_the_window_is_not_removed(
    client, monkeypatch
):
    """The same property on the OTHER mutation loop, proven without threads.

    ``record_lock`` is the seam: the spy commits the write immediately BEFORE the
    reset acquires that record's lock, which is precisely the last instant of the
    window. Single-threaded and event-free, so it cannot flake — and the store is
    driven directly rather than over HTTP because the reset is running on this very
    thread and the ``TestClient`` portal is not re-entrant.

    PRE-FIX: the record is rmtree'd and the reset reports success.
    """
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    token = _plan_digest(client)
    session_id = tutorial_ws().session_id

    injected: list[str] = []
    real_lock = ws.record_lock

    @contextlib.contextmanager
    def write_then_lock(experiment_id: str, *, session_id: str | None = None):
        if experiment_id == legacy.id and not injected:
            injected.append(experiment_id)
            exp = ws.load_experiment(legacy.id, session_id)
            exp.title = "written by a concurrent operator"
            assert exp.save_versioned(), "the injected write must really persist"
        with real_lock(experiment_id, session_id=session_id):
            yield

    monkeypatch.setattr(ws, "record_lock", write_then_lock)
    data = ws.reset_to_canonical_seed(
        dry_run=False, expected_plan_digest=token, session_id=session_id
    )

    assert injected == [legacy.id], "the write was never injected into the window"
    survived = legacy.id in _dirs_on_disk()
    assert survived or data["refused"], (
        "C2: a write to a managed-legacy record inside the window was destroyed by a "
        "reset that reported success"
    )
    assert data["refused"] is True
    assert data["refusal"] == "plan_digest_stale"
    assert survived
    assert ws.load_experiment(legacy.id, session_id).title == (
        "written by a concurrent operator"
    )
    # Nothing was mutated at all, so the snapshot IS the truth and is reported as such.
    assert data["removed_count"] == 0
    assert data["final_count"] == len(_dirs_on_disk()) == 6


def test_c2_the_per_record_check_never_refuses_an_untouched_workspace(client):
    """The row re-check must be a precondition, not a source of spurious 412s.

    Re-derived from disk under the lock, an untouched record's row has to be
    byte-identical to the one classified moments earlier — otherwise every reset in
    production would refuse. Driven repeatedly, and over the real HTTP contract, with
    every kind of record the two loops walk.
    """
    tutorial_ws().ensure_tutorial_seeded()
    for _ in range(3):
        _make_managed_legacy()
        _confirm_an_answer(client, ws.SEED_PARTIAL_ID)
        detail = client.get(f"/api/experiments/{ws.SEED_READY_ID}")
        assert (
            client.post(
                f"/api/experiments/{ws.SEED_READY_ID}/export",
                headers={"If-Match": detail.headers["ETag"]},
            ).status_code
            == 200
        )
        r = _execute(client, token=_plan_digest(client))
        assert r.status_code == 200, r.text
        assert r.json()["refusal_reason"] is None
        assert _dirs_on_disk() == CANONICAL_IDS
