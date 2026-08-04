"""P27.6-reset — Reset Demo restores canonical CONTENT, not merely the id set.

TEST-FIRST acceptance contract (authored BEFORE the fix; RED until
`reset_to_canonical_seed` re-materialises ALL five canonical records to their
deterministic seed baseline on execute — currently it only removes managed_legacy
dirs and recreates MISSING canonical, so a present-but-mutated canonical record
keeps its drift).

The hosted P27.5 QA proved the defect: an exported `...0003` and a partially
answered `...0001` survived "Reset Demo" (which returned 200) because the five ids
still existed. A control labelled "Reset Demo" must restore the managed synthetic
state, not just guarantee the ids exist.

Required post-reset invariants (mandate):
  * exactly five canonical ids exist;
  * every canonical record matches its intended seed scenario (content restored);
  * distribution: needs_attention 2, in_review 1, ready_to_export 1, done 1;
  * the DONE scenario has its exported artifact + sidecar; others are NOT exported;
  * partial answers / stale evidence / pending drift are removed or replaced;
  * ALL pre-reset ETags/tokens are invalid afterward (fresh generation);
  * ambiguous records still cause refusal (no changes); unrelated managed_legacy
    records are the only removals; NO general delete route; repeated reset is
    idempotent in content; preview is non-mutating; concurrent readers stay safe.

Uses the existing managed-demo provenance + canonical-ID boundaries; NOT a broad
filesystem wipe. All fixtures synthetic; truth core untouched.
"""

from __future__ import annotations

import concurrent.futures
import copy
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import client_ws, open_tutorial_scope, tutorial_client, tutorial_ws


@pytest.fixture()
def tmp_ws(tmp_path, monkeypatch):
    """The store bound to an isolated worked-example session (no HTTP).

    Re-pointed from the normal workspace, which is no longer auto-seeded. The five
    canonical records and every assertion about them are unchanged; only the
    directory they live in is.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return open_tutorial_scope()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


_EXPECTED_DISTRIBUTION = {
    ws_status: n
    for ws_status, n in [
        ("needs_attention", 2),
        ("ready_to_export", 1),
        ("in_review", 1),
        ("done", 1),
    ]
}


def _distribution(tmp_ws):
    counts: dict[str, int] = {}
    for exp in tmp_ws.list_experiments():
        if exp.id in tmp_ws.CANONICAL_IDS:
            counts[exp.status()] = counts.get(exp.status(), 0) + 1
    return counts


def _baseline_by_id(tmp_ws):
    """The intended baseline scenario for each canonical id (title + draft)."""
    return {s.id: s for s in tmp_ws._seed_specs()}


# --- 1. mutated canonical content is restored --------------------------------


def test_reset_restores_mutated_canonical_title_and_draft(tmp_ws):
    tmp_ws.ensure_tutorial_seeded()
    specs = _baseline_by_id(tmp_ws)
    # drift EVERY canonical record away from its baseline
    for exp in tmp_ws.list_experiments():
        if exp.id in tmp_ws.CANONICAL_IDS:
            exp.title = exp.title + " (drifted)"
            exp.draft = {"fields": {}, "pending": []}  # wipe the scientific content
            exp.save_versioned()

    tmp_ws.reset_to_canonical_seed(dry_run=False)

    for exp in tmp_ws.list_experiments():
        if exp.id in tmp_ws.CANONICAL_IDS:
            spec = specs[exp.id]
            assert exp.title == spec.title, f"{exp.id} title not restored"
            assert exp.draft == spec.draft_fn(), f"{exp.id} draft not restored to baseline"


def test_reset_removes_partial_answers(client):
    # apply real answers to the raw NEW-DRAFT seed (drives pending 5 -> fewer)
    v = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()["version"]
    answers = ws.load_demo_answers()
    client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json={"confirmed_by_user": True, "answers": {"series": answers.get("series")}},
        headers={"If-Match": f'"{v}"'},
    )
    before = tutorial_ws().load_experiment(ws.SEED_NEW_DRAFT_ID)
    assert before.answer_log, "precondition: an answer was logged"

    tutorial_ws().reset_to_canonical_seed(dry_run=False)

    after = tutorial_ws().load_experiment(ws.SEED_NEW_DRAFT_ID)
    assert after.answer_log == [], "reset must clear partial answers"
    assert after.draft == _baseline_by_id(ws)[ws.SEED_NEW_DRAFT_ID].draft_fn()


# --- 2. exported drift is un-done; only the DONE scenario stays exported ------


def test_reset_unexports_a_wrongly_exported_scenario(client):
    # export the READY scenario (it passes export) — it should NOT stay exported
    v = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()["version"]
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers={"If-Match": f'"{v}"'})
    assert r.status_code == 200 and r.json().get("ok") is True
    assert tutorial_ws().load_experiment(ws.SEED_READY_ID).exported() is True

    tutorial_ws().reset_to_canonical_seed(dry_run=False)

    restored = tutorial_ws().load_experiment(ws.SEED_READY_ID)
    assert restored.exported() is False, "reset must un-export a wrongly-exported scenario"
    # and its on-disk record artifact must be gone
    assert not (restored.records_dir / f"{ws.SEED_READY_ID}.json").exists()


def test_reset_done_scenario_keeps_its_artifact(tmp_ws):
    tmp_ws.ensure_tutorial_seeded()
    tmp_ws.reset_to_canonical_seed(dry_run=False)
    done = tmp_ws.load_experiment(tmp_ws.SEED_DONE_ID)
    assert done.exported() is True
    assert (done.records_dir / f"{done.record_id}.json").exists()
    assert (done.records_dir / f"{done.record_id}.evidence.json").exists()


# --- 3. exact state distribution ---------------------------------------------


def test_reset_restores_exact_distribution(client):
    # drift a couple scenarios via HTTP, then reset
    v = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()["version"]
    client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers={"If-Match": f'"{v}"'})
    scoped = client_ws(client)
    scoped.reset_to_canonical_seed(dry_run=False)
    assert _distribution(scoped) == _EXPECTED_DISTRIBUTION


# --- 4. pre-reset tokens are stale afterward ---------------------------------


def test_pre_reset_tokens_are_all_stale_after_reset(tmp_ws):
    tmp_ws.ensure_tutorial_seeded()
    before = {e.id: e.version_token() for e in tmp_ws.list_experiments() if e.id in tmp_ws.CANONICAL_IDS}
    tmp_ws.reset_to_canonical_seed(dry_run=False)
    for exp in tmp_ws.list_experiments():
        if exp.id in tmp_ws.CANONICAL_IDS:
            assert exp.version_token() != before[exp.id], (
                f"{exp.id}: pre-reset token must be invalid after reset (fresh generation)"
            )


# --- 5. idempotent in content -------------------------------------------------


def test_repeated_reset_is_idempotent_in_content(tmp_ws):
    tmp_ws.ensure_tutorial_seeded()
    tmp_ws.reset_to_canonical_seed(dry_run=False)
    first = {
        e.id: (e.title, e.status(), e.exported()) for e in tmp_ws.list_experiments()
    }
    tmp_ws.reset_to_canonical_seed(dry_run=False)
    second = {
        e.id: (e.title, e.status(), e.exported()) for e in tmp_ws.list_experiments()
    }
    assert first == second
    assert _distribution(tmp_ws) == _EXPECTED_DISTRIBUTION


# --- 6. preview is non-mutating ----------------------------------------------


def test_preview_does_not_restore_or_mutate(tmp_ws):
    tmp_ws.ensure_tutorial_seeded()
    exp = tmp_ws.load_experiment(tmp_ws.SEED_NEW_DRAFT_ID)
    exp.title = "drifted-title"
    exp.save_versioned()
    tmp_ws.reset_to_canonical_seed(dry_run=True)  # PREVIEW
    still = tmp_ws.load_experiment(tmp_ws.SEED_NEW_DRAFT_ID)
    assert still.title == "drifted-title", "preview must not mutate/restore"


# --- 7. guards preserved: ambiguous refusal, unrelated untouched -------------


def test_ambiguous_record_still_refuses_and_makes_no_change(tmp_ws):
    tmp_ws.ensure_tutorial_seeded()
    # an ambiguous record: not canonical, no managed-demo provenance marker
    amb = tmp_ws.create_experiment(
        title="unrelated user record",
        source={"description": "some other provenance", "files": []},
        draft={"fields": {}, "pending": []},
    )
    # drift a canonical too
    c = tmp_ws.load_experiment(tmp_ws.SEED_NEW_DRAFT_ID)
    c.title = "drifted"
    c.save_versioned()

    result = tmp_ws.reset_to_canonical_seed(dry_run=False)
    assert result["refused"] is True
    # refusal => NO changes: the ambiguous record and the drifted canonical both remain
    assert tmp_ws.load_experiment(amb.id) is not None
    assert tmp_ws.load_experiment(tmp_ws.SEED_NEW_DRAFT_ID).title == "drifted"


# --- 8. concurrent readers stay safe during reset ----------------------------


def test_concurrent_readers_safe_during_reset(tmp_ws):
    tmp_ws.ensure_tutorial_seeded()
    stop = threading.Event()
    errors: list[Exception] = []

    def reader():
        while not stop.is_set():
            try:
                tmp_ws.list_experiments()  # tolerates transient missing dirs
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(reader) for _ in range(2)]
        for _ in range(5):
            tmp_ws.reset_to_canonical_seed(dry_run=False)
        stop.set()
        for f in futs:
            f.result()
    assert errors == [], f"readers observed corruption during reset: {errors}"


# --- 9. reset-vs-reader race is closed: ensure_seeded materialises under the lock


def test_ensure_seeded_materialise_observes_record_lock(tmp_ws):
    """DETERMINISTIC proof the seeder-vs-reset race is closed: the seeder, when it
    must materialise a MISSING canonical id, acquires ``record_lock(id)`` first — the
    SAME lock the reset holds around its remove+re-materialise. So while that lock is
    held by another thread, the seeder cannot materialise (and thus cannot write into
    a dir a concurrent reset is rmtree-ing). We assert the seeder BLOCKS while the
    lock is held and completes promptly after release.

    RE-POINTED, and one contract genuinely changed. It used to trigger the seeder
    through ``load_experiment`` — reads called ``ensure_seeded`` on every access. They
    no longer do (the normal workspace is never auto-seeded, and a worked-example
    session is seeded once at creation), so the seeder is invoked directly here. The
    property under test — the materialise of a missing id happens under that id's own
    record lock — is asserted at exactly the same strength; only the caller that
    reaches it has changed."""
    tmp_ws.ensure_tutorial_seeded()
    # Make SEED_READY_ID missing so ``ensure_tutorial_seeded`` must materialise it (the
    # branch that takes the lock). This comment said "load_experiment -> ensure_seeded",
    # contradicting the docstring directly above it: reads no longer seed, and the
    # seeder is invoked directly below.
    shutil.rmtree(tmp_ws.workspace_root() / tmp_ws.SEED_READY_ID)

    holder_acquired = threading.Event()
    release_holder = threading.Event()
    loader_done = threading.Event()

    def holder():
        with tmp_ws.record_lock(tmp_ws.SEED_READY_ID):
            holder_acquired.set()
            release_holder.wait(timeout=5)  # hold until the main thread lets go

    def loader():
        # Must block on record_lock(SEED_READY_ID): the missing id forces the
        # materialise-under-lock branch.
        tmp_ws.ensure_tutorial_seeded()
        loader_done.set()

    h = threading.Thread(target=holder)
    h.start()
    assert holder_acquired.wait(timeout=2), "holder failed to acquire the lock"

    lt = threading.Thread(target=loader)
    lt.start()
    # While the lock is held, the loader must NOT complete (it is blocked on the
    # missing-id materialise under record_lock).
    assert not loader_done.wait(timeout=0.3), (
        "the seeder completed while the record lock was held — it did not observe "
        "the lock (seeder-vs-reset race still open)"
    )
    # Release the lock; the loader must now finish promptly and materialise the id.
    release_holder.set()
    assert loader_done.wait(timeout=3), "loader did not complete after lock release"
    h.join(timeout=3)
    lt.join(timeout=3)

    restored = tmp_ws.load_experiment(tmp_ws.SEED_READY_ID)
    assert restored is not None, "the missing canonical must be materialised after release"
