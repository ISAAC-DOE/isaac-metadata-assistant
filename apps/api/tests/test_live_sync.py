"""P27.6 — live-sync backend contract: conditional GET (If-None-Match → 304).

TEST-FIRST acceptance contract (authored BEFORE implementation; RED until
`GET /api/experiments/{id}` honours `If-None-Match`). Live sync is bounded
revision-aware polling: the client polls the record detail with its last-observed
ETag; the backend returns 304 Not Modified when unchanged (a cheap change signal)
or 200 + the current authoritative bundle + new ETag when it changed. Polling is
ONLY a change signal — the fetched Workspace snapshot remains authoritative.

Chosen pattern: Option A (conditional read on the EXISTING detail endpoint), not a
new revision endpoint — the `_detail` bundle is small and already carries the
authoritative `version`/ETag, so no new route is warranted. SSE was ruled out
(EventSource cannot send the Bearer header; no cookie auth; sync single-process
deployment). 304 carries NO body (no content leak). Auth + CORS unchanged.

All fixtures synthetic; truth core untouched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _etag(client, exp_id):
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200
    return r.headers["ETag"]


def _im(client, exp_id):
    return {"If-Match": _etag(client, exp_id)}


def _real_answers_payload():
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


# --- 1. matching If-None-Match → 304, no body --------------------------------


def test_matching_if_none_match_returns_304(client):
    etag = _etag(client, ws.SEED_NEW_DRAFT_ID)
    r = client.get(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}", headers={"If-None-Match": etag}
    )
    assert r.status_code == 304, r.text
    assert r.headers.get("ETag") == etag  # 304 still carries the validator
    assert r.content == b"", "304 must carry NO body (no content leak, cheap signal)"


def test_absent_if_none_match_returns_200_full(client):
    r = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}")
    assert r.status_code == 200
    assert "version" in r.json()


# --- 2. changed record → 200 + new ETag --------------------------------------


def test_changed_record_returns_200_and_new_etag(client):
    etag = _etag(client, ws.SEED_NEW_DRAFT_ID)
    # mutate → rev bumps → ETag changes
    client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": etag},
    )
    r = client.get(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}", headers={"If-None-Match": etag}
    )
    assert r.status_code == 200, "a changed record must return the fresh bundle, not 304"
    assert r.headers["ETag"] != etag
    assert "version" in r.json()


# --- 4. auth required --------------------------------------------------------


def test_conditional_get_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    c = TestClient(create_app())
    r = c.get(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}",
        headers={"If-None-Match": '"whatever.0"'},
    )
    assert r.status_code == 401, "conditional GET must still require the Bearer key"


# --- 5 + 6. CORS: unapproved origin denied; If-None-Match allowed, ETag exposed


def _cors_client(tmp_path, monkeypatch, origin="https://isaac-demo-web.vercel.app"):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_CORS_ORIGINS", origin)
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app()), origin


def test_cors_preflight_allows_if_none_match(tmp_path, monkeypatch):
    client, origin = _cors_client(tmp_path, monkeypatch)
    r = client.options(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "if-none-match",
        },
    )
    assert r.status_code in (200, 204)
    allowed = r.headers.get("access-control-allow-headers", "").lower()
    assert "if-none-match" in allowed or allowed == "*"


def test_cors_304_exposes_etag_and_allows_origin(tmp_path, monkeypatch):
    client, origin = _cors_client(tmp_path, monkeypatch)
    etag = _etag(client, ws.SEED_NEW_DRAFT_ID)
    r = client.get(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}",
        headers={"Origin": origin, "If-None-Match": etag},
    )
    assert r.status_code == 304
    assert r.headers.get("access-control-allow-origin") == origin
    assert "etag" in r.headers.get("access-control-expose-headers", "").lower()


def test_cors_denies_unapproved_origin_on_conditional_get(tmp_path, monkeypatch):
    client, _ = _cors_client(tmp_path, monkeypatch)
    r = client.get(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}",
        headers={"Origin": "https://evil.example.com", "If-None-Match": '"x.0"'},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


# --- 7. missing record → typed 404 (even with If-None-Match) -----------------


def test_missing_record_is_404_typed_even_conditional(client):
    r = client.get(
        "/api/experiments/01MISSINGRECORD00000000000",
        headers={"If-None-Match": '"x.0"'},
    )
    assert r.status_code == 404
    assert r.json()["error"] == "experiment_not_found"


# --- 8. reset produces a detectable lifecycle/version change -----------------


def test_reset_makes_prior_etag_detect_change(client):
    etag = _etag(client, ws.SEED_READY_ID)
    # unchanged → 304
    assert (
        client.get(
            f"/api/experiments/{ws.SEED_READY_ID}", headers={"If-None-Match": etag}
        ).status_code
        == 304
    )
    # reset re-materialises canonical with a fresh generation → ETag changes
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
    after = client.get(
        f"/api/experiments/{ws.SEED_READY_ID}", headers={"If-None-Match": etag}
    )
    assert after.status_code == 200, "after reset, a pre-reset ETag must detect the change"
    assert after.headers["ETag"] != etag


# --- 9. export produces a detectable change ----------------------------------


def test_export_makes_prior_etag_detect_change(client):
    etag = _etag(client, ws.SEED_READY_ID)
    r = client.post(
        f"/api/experiments/{ws.SEED_READY_ID}/export", headers={"If-Match": etag}
    )
    assert r.status_code == 200 and r.json().get("ok") is True
    after = client.get(
        f"/api/experiments/{ws.SEED_READY_ID}", headers={"If-None-Match": etag}
    )
    assert after.status_code == 200
    assert after.headers["ETag"] != etag


# --- 10. "restart" (reload from disk) does NOT spuriously invalidate ----------


def test_reload_preserves_etag_no_false_change(client, tmp_path, monkeypatch):
    etag = _etag(client, ws.SEED_DONE_ID)
    # simulate a backend restart: a fresh Experiment loaded from the same on-disk
    # state must carry the SAME generation/rev, so a client's ETag still matches.
    reloaded = ws.load_experiment(ws.SEED_DONE_ID)
    assert reloaded.etag() == etag, "generation/rev persist across reload — no false change"
    r = client.get(
        f"/api/experiments/{ws.SEED_DONE_ID}", headers={"If-None-Match": etag}
    )
    assert r.status_code == 304, "a reload must not manufacture a spurious change signal"
