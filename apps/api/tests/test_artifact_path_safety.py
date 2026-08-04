"""P30.6 — internal artifact-path exposure correction (API boundary).

TEST-FIRST (authored BEFORE the fix; RED until the API stops returning absolute
server paths). The export detail bundle (`_detail.artifact_refs`) and the
`GET /artifacts` response currently return `str(exp.record_path())` — an ABSOLUTE
server path (`/data/isaac-workspace/…` on Railway) that reaches the browser. That
is an infrastructure/path leak (CLAUDE.md path-boundary rules). The client only
needs a SAFE filename to label + download; the JSON CONTENT already comes from the
authenticated `/artifacts` route. So the API must expose a safe filename
descriptor and NEVER an absolute/server/mount path.

Truth core untouched; export behavior unchanged. All fixtures synthetic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import tutorial_client

# Absolute/server/mount markers that must NEVER reach the client.
UNSAFE_PATH_MARKERS = ["/data/", "/Users/", "/var/", "/tmp/", "/app/", "/private/", "isaac-workspace", "\\"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _export(client, exp_id):
    etag = client.get(f"/api/experiments/{exp_id}").headers["ETag"]
    r = client.post(f"/api/experiments/{exp_id}/export", headers={"If-Match": etag})
    assert r.status_code == 200 and r.json().get("ok") is True, r.text


def _assert_no_absolute_path(payload_text: str, where: str):
    for m in UNSAFE_PATH_MARKERS:
        assert m not in payload_text, f"{where}: leaked path marker {m!r}"
    # No bare absolute path segment like "/<something>/records/..." either.
    assert '":"/' not in payload_text.replace(" ", ""), f"{where}: a value starts with an absolute '/'"


def test_detail_artifact_refs_carry_no_absolute_path(client):
    _export(client, ws.SEED_READY_ID)
    body = client.get(f"/api/experiments/{ws.SEED_READY_ID}")
    assert body.status_code == 200
    refs = body.json()["artifact_refs"]
    _assert_no_absolute_path(__import__("json").dumps(refs), "detail.artifact_refs")
    # A usable, safe filename must still be present (ends in .json, basename only).
    vals = [v for v in refs.values() if isinstance(v, str) and v]
    assert vals, "artifact_refs should still surface a safe filename when exported"
    for v in vals:
        assert v.endswith(".json"), f"artifact ref should be a filename, got {v!r}"
        assert "/" not in v and "\\" not in v, f"artifact ref must be a basename, got {v!r}"


def test_artifacts_endpoint_carries_no_absolute_path(client):
    _export(client, ws.SEED_READY_ID)
    r = client.get(f"/api/experiments/{ws.SEED_READY_ID}/artifacts")
    assert r.status_code == 200
    body = r.json()
    # The JSON CONTENT must still be returned (View/Download works)...
    assert body["record"] is not None and body["sidecar"] is not None
    # ...but NO absolute server path anywhere in the response.
    _assert_no_absolute_path(r.text, "/artifacts response")


def test_export_response_carries_no_absolute_path(client):
    """Symmetry with detail/artifacts (independent-review suggestion): the POST
    /export response's artifact_refs is the third leak site — run it through the
    same absolute-path sweep so all three are guarded in one place."""
    etag = client.get(f"/api/experiments/{ws.SEED_READY_ID}").headers["ETag"]
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers={"If-Match": etag})
    assert r.status_code == 200 and r.json().get("ok") is True, r.text
    _assert_no_absolute_path(r.text, "POST /export response")
    refs = r.json().get("artifact_refs", {})
    vals = [v for v in refs.values() if isinstance(v, str) and v]
    assert vals and all(v.endswith(".json") and "/" not in v for v in vals)


def test_non_exported_artifact_refs_are_empty_not_pathlike(client):
    body = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    refs = body["artifact_refs"]
    for v in refs.values():
        assert v in (None, ""), f"a non-exported record must not surface an artifact path, got {v!r}"


def test_committed_snapshot_has_no_workspace_path_leak():
    """Defense in depth: the served snapshot manifest must not embed a live volume
    path either (the served content is code/docs, not runtime artifact paths)."""
    from pathlib import Path

    snap = Path("apps/api/isaac_api/data/memory-snapshot.json").read_text(encoding="utf-8")
    assert "/data/isaac-workspace" not in snap
