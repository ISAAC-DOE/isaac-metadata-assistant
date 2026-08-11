"""P30.1 — thin runtime record projection (safe confirmed-facts, filters, freshness).

TEST-FIRST contract (authored BEFORE implementation; RED until
`GET /api/runtime/records` exists). A DERIVED read model over the SAME
`list_experiments()` scan P26 search uses — no index, no cache, current-by-
construction. It emits ONLY safe confirmed facts + freshness metadata, supports a
few typed filters its consumer (a cross-record assistant/triage surface) uses, and
NEVER leaks unconfirmed proposals / inferred values as facts / evidence bodies /
secrets / internal paths / chat / Project-Memory-as-record-data.

Truth core untouched; the provider reuses `_summary`/`derive_workflow`/
`classify_fields` counts/`artifact_state` read-only. All fixtures synthetic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import bind_tutorial_session, tutorial_client, tutorial_ws

# The ONLY keys a projected record may carry — a strict allow-set (governance).
ALLOWED_KEYS = {
    "experiment_id",
    "title",
    "status",
    "pending_count",
    "exported",
    "record_id",
    "workflow",          # {current_step, blocked, reopened} — no values
    "evidence_counts",   # 5-class histogram — counts only, never field values
    "artifact_state",    # none | current | stale
    "record_rev",
    "updated_utc",
    "navigate_to",
}
EVIDENCE_CLASSES = {
    "supported",
    "inferred_candidate",
    "insufficient_evidence",
    "conflicting_evidence",
    "unknown",
    # A read failure, never folded into `unknown` (which claims nothing
    # defensible is recorded). See `runtime_records.EVIDENCE_CLASSES`.
    "unreadable",
}
# Keys/substrings that must NEVER appear anywhere in the projection payload.
FORBIDDEN_SUBSTRINGS = ["/Users/", "\\Users\\", "draft", "answer_log", "proposal", "sidecar"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _records(client, query=""):
    r = client.get(f"/api/runtime/records{query}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "records" in body and isinstance(body["records"], list)
    return body


def test_projection_shape_is_the_strict_safe_allow_set(client):
    body = _records(client)
    assert body["records"], "the canonical seed should yield records"
    for rec in body["records"]:
        assert set(rec) <= ALLOWED_KEYS, f"projection leaked keys: {set(rec) - ALLOWED_KEYS}"
        assert "experiment_id" in rec and "status" in rec
        assert isinstance(rec["record_rev"], int)  # freshness metadata present
        assert rec["navigate_to"].startswith("/")  # a client route, not a filesystem path
        assert set(rec["evidence_counts"]) == EVIDENCE_CLASSES  # counts only
        assert all(isinstance(v, int) for v in rec["evidence_counts"].values())
        assert set(rec["workflow"]) <= {"current_step", "blocked", "reopened"}


def test_projection_never_leaks_unsafe_content(client):
    """No draft/values/evidence-bodies/proposals/secrets/paths in the payload."""
    blob = client.get("/api/runtime/records").text
    for bad in FORBIDDEN_SUBSTRINGS:
        assert bad not in blob, f"projection leaked {bad!r}"


def test_reflects_current_workspace_the_canonical_2_1_1_1(client):
    body = _records(client)
    by_status: dict[str, int] = {}
    for rec in body["records"]:
        by_status[rec["status"]] = by_status.get(rec["status"], 0) + 1
    # canonical distribution: 2 needs_attention / 1 in_review / 1 ready_to_export / 1 done
    assert by_status.get("needs_attention") == 2
    assert by_status.get("in_review") == 1
    assert by_status.get("ready_to_export") == 1
    assert by_status.get("done") == 1


def test_status_filter(client):
    body = _records(client, "?status=ready_to_export")
    assert body["records"], "expected the ready seed"
    assert all(r["status"] == "ready_to_export" for r in body["records"])


def test_artifact_filter_current_only_for_exported(client):
    # Only the exported/done seed can have a non-'none' artifact state.
    body = _records(client, "?artifact=current")
    for r in body["records"]:
        assert r["artifact_state"] == "current"
        assert r["exported"] is True


def test_has_conflict_filter_is_evidence_class_scoped(client):
    """The one evidence filter the consumer uses. Canonical seeds have no conflict,
    so the filtered set is empty — but the filter must be honored, not ignored."""
    body = _records(client, "?has_conflict=true")
    for r in body["records"]:
        assert r["evidence_counts"]["conflicting_evidence"] >= 1


def test_a_mutation_is_reflected_freshly_no_stale_cache(client):
    before = {r["experiment_id"]: r["record_rev"] for r in _records(client)["records"]}
    etag = client.get(f"/api/experiments/{ws.SEED_READY_ID}").headers["ETag"]
    client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers={"If-Match": etag})
    after = {r["experiment_id"]: r for r in _records(client)["records"]}
    # export bumped the rev AND flipped status→done — reflected with no cache
    assert after[ws.SEED_READY_ID]["record_rev"] > before[ws.SEED_READY_ID]
    assert after[ws.SEED_READY_ID]["status"] == "done"


def test_empty_filter_total_is_the_full_canonical_seed(client):
    body = _records(client)
    # No filters → the whole canonical five-scenario seed, and total is the
    # filtered denominator (here the full set).
    assert body["total"] == 5
    assert len(body["records"]) == 5


def test_workflow_state_filter_is_honored(client):
    # `current` = records with an active current step (everything but the exported
    # done seed). `blocked` = records with at least one blocked downstream step.
    current = _records(client, "?workflow_state=current")
    assert current["records"], "in-progress seeds should match `current`"
    assert all(r["workflow"]["current_step"] is not None for r in current["records"])

    blocked = _records(client, "?workflow_state=blocked")
    assert all(r["workflow"]["blocked"] for r in blocked["records"])
    # The exported/done seed has no current step and no blocked step, so it is
    # excluded from both filtered sets.
    done_ids = {r["experiment_id"] for r in _records(client)["records"] if r["status"] == "done"}
    assert done_ids and not (done_ids & {r["experiment_id"] for r in current["records"]})
    assert not (done_ids & {r["experiment_id"] for r in blocked["records"]})


def test_records_are_stably_ordered_by_creation(client):
    # Deterministic ordering is part of the contract (created_utc then id). The
    # canonical seed's ids are lexically ordered by their creation sequence.
    ids = [r["experiment_id"] for r in _records(client)["records"]]
    assert ids == sorted(ids)


def test_crafted_secret_never_reaches_the_projection(client):
    """Regression guard (independent-review must-fix): the clean-seed scan passes
    trivially, so craft a record whose NON-exposed channels (draft field value,
    evidence body/locator, source, answer_log) carry unmistakably-fake secrets and
    assert NONE reaches the projection. Title stays clean (it is a safe exposed
    field). The provider is already safe; this locks it against a future leak."""
    import json as _json

    from isaac_api.runtime_records import project_records

    exp = tutorial_ws().load_experiment(ws.SEED_NEW_DRAFT_ID)
    SECRET = "Bearer NOT-A-REAL-SECRET-SYNTHETIC"
    HEX = "a" * 40
    PATH = "/Users/fake/synthetic-not-real.h5"
    exp.draft.setdefault("fields", {})["sample.secret"] = {
        "value": SECRET,
        "status": "verified",
        "evidence": [{"source_type": "document", "quote": HEX, "locator": PATH}],
    }
    exp.source = {"files": [PATH], "note": SECRET}
    exp.answer_log = [{"applied": {"sample.secret": SECRET}, "at": "2026-01-01T00:00:00Z"}]

    blob = _json.dumps(project_records([exp]))
    assert SECRET not in blob, "a draft/source/answer_log secret must never reach the projection"
    assert HEX not in blob, "an evidence-body token must never reach the projection"
    assert PATH not in blob and "/Users/" not in blob, "an internal path must never reach the projection"


def test_unrecognized_filter_matches_nothing_never_the_full_set(client):
    """Authority guard (independent-review must-fix): an unrecognized filter value
    must match NOTHING, never silently return the whole set (a filter that is
    ignored is a correctness/authority bug)."""
    for q in ("?status=bogus", "?workflow_state=bogus", "?artifact=bogus"):
        body = _records(client, q)
        assert body["total"] == 0, f"unrecognized filter {q} must match nothing, got {body['total']}"
        assert body["records"] == []


def test_reset_is_reflected_freshly(client):
    """P30.4 by-construction: after Reset Demo, the projection re-derives the
    canonical 2/1/1/1 with no stale cache (export a record to drift, then reset)."""
    etag = client.get(f"/api/experiments/{ws.SEED_READY_ID}").headers["ETag"]
    client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers={"If-Match": etag})
    # drifted: the ready seed is now done
    assert any(r["status"] == "done" and r["experiment_id"] == ws.SEED_READY_ID
               for r in _records(client)["records"])
    # R1: an execute carries the plan digest from its own preview (428 without it).
    digest = client.post("/api/demo/reset", json={"mode": "preview"}).json()["plan_digest"]
    r = client.post(
        "/api/demo/reset",
        json={
            "mode": "execute",
            "confirmation": "RESET EXAMPLE WORKSPACE",
            "plan_digest": digest,
        },
    )
    assert r.status_code == 200
    after = _records(client)
    counts: dict[str, int] = {}
    for rec in after["records"]:
        counts[rec["status"]] = counts.get(rec["status"], 0) + 1
    assert counts.get("needs_attention") == 2 and counts.get("ready_to_export") == 1
    assert counts.get("in_review") == 1 and counts.get("done") == 1  # back to canonical


def test_deletion_is_reflected_by_construction_no_stale_retention():
    """P30.4 by-construction: the projection is a pure derivation over the passed
    scan — a record absent from the scan is absent from the projection (no cache
    could retain a deleted record). Function-level, no workspace needed."""
    from isaac_api.runtime_records import project_records

    assert project_records([]) == []  # empty scan → empty projection, never stale


def test_requires_auth_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    # The session is opened in-process rather than over HTTP: this deployment
    # requires the key, and pinning it as a client default would destroy the 401
    # this test asserts. Same scope either way.
    c = bind_tutorial_session(TestClient(create_app()))
    assert c.get("/api/runtime/records").status_code == 401
