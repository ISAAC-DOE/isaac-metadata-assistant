"""P26.0b — guarded synthetic-demo reset (`POST /api/demo/reset`).

TEST-FIRST acceptance contract (authored before implementation; must be RED until
the endpoint + workspace helper exist). The reset restores the shared *synthetic*
demo workspace to EXACTLY the five canonical P26.0a scenarios, safely:

  * it NEVER accepts caller-supplied ids or filesystem paths,
  * it removes ONLY records proven to belong to the managed synthetic-demo dataset
    (canonical fixed ids, or the committed synthetic-demo `source` marker),
  * it REFUSES if any ambiguous / unmanaged record would be affected,
  * it reuses the existing deterministic seed (never fabricates a record),
  * it is idempotent and reports a typed, path-free result,
  * there is NO general per-experiment delete route.

All fixtures are synthetic. Truth core is never bypassed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_records.official import validate_official  # truth-core authority

CONFIRM = "RESET SYNTHETIC DEMO"
CANONICAL_IDS = {
    ws.SEED_NEW_DRAFT_ID,
    ws.SEED_PARTIAL_ID,
    ws.SEED_READY_ID,
    ws.SEED_REVIEW_ID,
    ws.SEED_DONE_ID,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _experiments(client) -> list[dict]:
    return client.get("/api/experiments").json()["experiments"]


def _ids(client) -> set[str]:
    return {e["id"] for e in _experiments(client)}


def _make_managed_legacy(title: str = "Synthetic XANES — CuO (Cu K-edge) Demo (demo/run)"):
    """A pre-P26.0a demo record: random id + the committed synthetic-demo marker."""
    return ws.create_experiment(
        title=title,
        source={
            "description": "Synthetic XANES campaign (CuO, Cu K-edge) — committed demo fixtures",
            "files": list(ws.SOURCE_FILES),
        },
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )


def _make_ambiguous(title: str = "Some other experiment"):
    """A record WITHOUT the managed-demo marker — must never be auto-removed."""
    return ws.create_experiment(
        title=title,
        source={"description": "hand-authored / unknown provenance", "files": []},
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )


def _reset(client, mode, confirmation=None, **extra):
    body = {"mode": mode}
    if confirmation is not None:
        body["confirmation"] = confirmation
    body.update(extra)
    return client.post("/api/demo/reset", json=body)


# --- 1. authentication --------------------------------------------------------


def test_reset_requires_auth_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    c = TestClient(create_app())
    assert c.post("/api/demo/reset", json={"mode": "preview"}).status_code == 401
    ok = c.post(
        "/api/demo/reset",
        json={"mode": "preview"},
        headers={"Authorization": "Bearer demo-secret"},
    )
    assert ok.status_code == 200


# --- 2. synthetic-only mode ---------------------------------------------------


def test_reset_requires_synthetic_only_mode(client, monkeypatch):
    monkeypatch.setattr(ws, "is_synthetic_only", lambda: False, raising=False)
    r = _reset(client, "execute", CONFIRM)
    assert r.status_code in (403, 409)
    assert r.json().get("status") == "refused"
    assert len(_experiments(client)) == 5  # unchanged


# --- 3. preview never mutates -------------------------------------------------


def test_preview_makes_no_changes(client):
    _make_managed_legacy()
    before = _ids(client)
    body = _reset(client, "preview").json()
    assert body["mode"] == "preview"
    assert body["removed_count"] == 0
    assert _ids(client) == before  # nothing removed


def test_preview_reports_typed_counts(client):
    # arrange: lazy-seed the canonical five via a real GET (create_app is read-only,
    # so the baseline is established the same way the deployed app seeds on first
    # access), then add two managed-legacy demo records.
    assert len(_experiments(client)) == 5
    _make_managed_legacy()
    _make_managed_legacy()
    body = _reset(client, "preview").json()
    assert body["canonical_count"] == 5
    assert body["legacy_count"] == 2
    assert body["ambiguous_count"] == 0
    assert body["final_count"] == 5
    assert len(body["removable"]) == 2
    assert set(body["canonical_ids"]) == CANONICAL_IDS
    assert body["state_counts"] == {
        "needs_attention": 2,
        "ready_to_export": 1,
        "in_review": 1,
        "done": 1,
    }
    # no filesystem paths leak into the response: each removable row exposes ONLY
    # id + title, and no value contains the workspace root path. (A title may
    # legitimately contain "/" — e.g. "Demo (demo/run)" — so the real leak check
    # is the workspace root, not a bare slash.)
    root = str(ws.workspace_root())
    for row in body["removable"]:
        assert set(row.keys()) == {"id", "title"}
        for val in row.values():
            assert root not in val


# --- 4. execute requires the exact confirmation phrase ------------------------


def test_execute_requires_exact_confirmation(client):
    _make_managed_legacy()
    before = _ids(client)
    for bad in (None, "", "reset", "RESET", "reset synthetic demo"):
        r = _reset(client, "execute", bad)
        assert r.json().get("status") == "refused", bad
    assert _ids(client) == before  # still nothing removed


# --- 5 & 6. caller cannot target ids or paths ---------------------------------


def test_caller_supplied_ids_and_paths_are_ignored(client):
    canonical_before = CANONICAL_IDS & _ids(client)
    r = _reset(
        client,
        "execute",
        CONFIRM,
        ids=[ws.SEED_DONE_ID],
        experiment_id=ws.SEED_DONE_ID,
        path="/etc/passwd",
        paths=["../../"],
    )
    # extra fields must not delete a canonical record nor escape the workspace
    assert CANONICAL_IDS <= _ids(client)
    assert canonical_before <= _ids(client)
    # strictly rejected by the typed model (extra="forbid") — a model that silently
    # ignored extras would weaken the "caller cannot target ids/paths" guarantee.
    assert r.status_code == 422


# --- 7 & 8. canonical preserved, verified legacy removed ----------------------


def test_execute_removes_only_managed_legacy_and_keeps_canonical(client):
    a = _make_managed_legacy()
    b = _make_managed_legacy()
    assert {a.id, b.id} <= _ids(client)
    body = _reset(client, "execute", CONFIRM).json()
    assert body["status"] == "ok"
    ids_after = _ids(client)
    assert ids_after == CANONICAL_IDS  # exactly five canonical
    assert a.id not in ids_after and b.id not in ids_after
    assert body["removed_count"] == 2


# --- 9 & 10. ambiguous causes refusal; unmanaged preserved --------------------


def test_ambiguous_record_causes_refusal_and_no_removal(client):
    amb = _make_ambiguous()
    legacy = _make_managed_legacy()
    before = _ids(client)
    r = _reset(client, "execute", CONFIRM)
    assert r.json().get("status") == "refused"
    assert r.json().get("ambiguous_count", 0) >= 1
    # NOTHING removed — not even the clearly-managed legacy record
    assert _ids(client) == before
    assert amb.id in _ids(client) and legacy.id in _ids(client)


def test_filename_overlap_without_marker_is_ambiguous_not_removed(client):
    # Provenance is proven ONLY by the exact description marker. A record that
    # merely references the fixture filenames but has an unrelated description is
    # NOT proven managed-demo: it must classify ambiguous (forcing refusal), never
    # be auto-deleted. (Guards against a filename-overlap heuristic mis-deleting a
    # real record.)
    assert len(_experiments(client)) == 5  # baseline
    imposter = ws.create_experiment(
        title="Real user experiment",
        source={"description": "hand-authored real data", "files": list(ws.SOURCE_FILES)},
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )
    prev = _reset(client, "preview").json()
    assert prev["ambiguous_count"] >= 1
    assert imposter.id not in {r["id"] for r in prev["removable"]}
    # execute refuses (ambiguous present) and removes nothing
    assert _reset(client, "execute", CONFIRM).json()["status"] == "refused"
    assert imposter.id in _ids(client)


# --- 11 & 12. missing canonical recreated; existing repaired via seed ---------


def test_missing_canonical_is_recreated(client):
    import shutil

    # arrange: lazy-seed the canonical five via a real GET (create_app is read-only),
    # then remove one canonical experiment directly on disk.
    assert CANONICAL_IDS <= _ids(client)
    shutil.rmtree(ws.workspace_root() / ws.SEED_READY_ID)
    # reset execute must recreate the missing canonical via the deterministic seed
    _reset(client, "execute", CONFIRM)
    assert CANONICAL_IDS <= _ids(client)


def test_canonical_titles_and_ids_stable_after_reset(client):
    before = {e["id"]: e["title"] for e in _experiments(client)}
    _reset(client, "execute", CONFIRM)
    after = {e["id"]: e["title"] for e in _experiments(client)}
    for cid in CANONICAL_IDS:
        assert after[cid] == before[cid]


# --- 13. idempotent -----------------------------------------------------------


def test_repeated_execute_stays_at_five(client):
    _make_managed_legacy()
    for _ in range(3):
        _reset(client, "execute", CONFIRM)
        assert _ids(client) == CANONICAL_IDS


# --- 14. final workflow-state distribution ------------------------------------


def test_final_state_distribution(client):
    _make_managed_legacy()
    _reset(client, "execute", CONFIRM)
    dist: dict[str, int] = {}
    for e in _experiments(client):
        dist[e["status"]] = dist.get(e["status"], 0) + 1
    assert dist == {"needs_attention": 2, "ready_to_export": 1, "in_review": 1, "done": 1}


# --- 15 & 16. exported canonical artifact valid; truth core not bypassed ------


def test_exported_canonical_record_remains_schema_valid(client):
    _reset(client, "execute", CONFIRM)
    art = client.get(f"/api/experiments/{ws.SEED_DONE_ID}/artifacts").json()
    assert art.get("record") is not None
    # the truth core — not the reset — is the validation authority
    assert validate_official(art["record"], ws.REPO_ROOT).ok


# --- 17. no general per-experiment delete route -------------------------------


def test_no_general_experiment_delete_route(client):
    r = client.request("DELETE", f"/api/experiments/{ws.SEED_DONE_ID}")
    assert r.status_code in (404, 405)


# --- 18. existing experiment routes unchanged ---------------------------------


def test_existing_experiment_routes_unchanged(client):
    _reset(client, "execute", CONFIRM)
    assert client.get("/api/experiments").status_code == 200
    assert client.get(f"/api/experiments/{ws.SEED_DONE_ID}").status_code == 200
    assert client.get(f"/api/experiments/{ws.SEED_DONE_ID}/draft").status_code == 200


# --- 19. concurrency safety (§8) ----------------------------------------------


def test_concurrent_execute_is_safe(client):
    """Near-simultaneous resets (e.g. two browser tabs) — plus records being
    created at the same time — must be safe: NO uncaught server error, and once
    quiescent the workspace converges to exactly the five canonical scenarios with
    its exported artifact intact.

    This drives ``reset_to_canonical_seed`` DIRECTLY under real threads with a
    concurrent creator, because the Starlette ``TestClient`` portal serialises HTTP
    requests and would under-exercise the delete-vs-read window. The race the guard
    protects against: one reset deletes a managed-legacy dir between another reset's
    directory-listing and its ``experiment.json`` read."""
    import concurrent.futures as cf

    ws.ensure_seeded()  # the reset path is deliberately no-seed; establish canonical first
    for _ in range(4):
        _make_managed_legacy()

    errors: list[BaseException] = []

    def resetter():
        # a raise here is exactly what would surface as an uncaught HTTP 500
        try:
            ws.reset_to_canonical_seed(dry_run=False)
        except BaseException as exc:  # noqa: BLE001 - the whole point is to catch ANY raise
            errors.append(exc)

    def creator():
        try:
            _make_managed_legacy()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futures = [ex.submit(resetter) for _ in range(8)]
        futures += [ex.submit(creator) for _ in range(4)]
        for f in futures:
            f.result()

    # THE contract: concurrency never produces an uncaught server error.
    assert errors == [], f"concurrent reset raised: {errors!r}"

    # Once quiescent, a final reset converges to exactly the five canonical — no
    # canonical lost, never fewer than five, no leftover legacy — with the exported
    # artifact still schema-valid (not corrupted by the race).
    ws.reset_to_canonical_seed(dry_run=False)
    assert _ids(client) == CANONICAL_IDS
    art = client.get(f"/api/experiments/{ws.SEED_DONE_ID}/artifacts").json()
    assert art.get("record") is not None
    assert validate_official(art["record"], ws.REPO_ROOT).ok


def test_load_tolerates_dir_removed_between_listing_and_read(client, monkeypatch):
    """DETERMINISTIC proof of the read-path concurrency guard (the timing-based
    test above cannot guarantee it fires). Simulate the exact window two concurrent
    resets create: a managed-legacy dir is removed AFTER ``_experiment_dirs()`` has
    listed it but BEFORE its ``experiment.json`` is read. The load must SKIP the
    vanished dir, never raise. Without the ``except FileNotFoundError`` guard this
    raises ``FileNotFoundError`` — which would surface as an uncaught HTTP 500."""
    import shutil

    ws.ensure_seeded()
    legacy = _make_managed_legacy()
    ghost = ws.workspace_root() / legacy.id
    assert ghost.exists()

    real_experiment_dirs = ws._experiment_dirs

    def list_then_delete_ghost():
        listing = real_experiment_dirs()  # ghost still present, so it IS listed
        if ghost.exists():
            shutil.rmtree(ghost)  # a concurrent reset deletes it right after listing
        return listing  # still references the now-deleted ghost -> read must tolerate

    monkeypatch.setattr(ws, "_experiment_dirs", list_then_delete_ghost)

    # the no-seed reset read path must skip the vanished dir without raising
    ids = {e.id for e in ws._load_all_experiments()}
    assert legacy.id not in ids
    assert CANONICAL_IDS <= ids
