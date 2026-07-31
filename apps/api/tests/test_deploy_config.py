"""Deployment-config tests: env-driven CORS + shared-secret bearer auth.

Presentation-layer seams for the hosted synthetic demo (Phase 20). Both seams
default OFF so local dev needs zero configuration and stays byte-identical.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- CORS allowlist -----------------------------------------------------------


def test_cors_default_allows_vite_dev_origin(tmp_path, monkeypatch):
    monkeypatch.delenv("ISAAC_UI_CORS_ORIGINS", raising=False)
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_env_override_replaces_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_CORS_ORIGINS", "https://isaac-demo.vercel.app")
    client = _make_client(tmp_path, monkeypatch)

    allowed = client.get("/api/health", headers={"Origin": "https://isaac-demo.vercel.app"})
    assert allowed.headers["access-control-allow-origin"] == "https://isaac-demo.vercel.app"

    # The default dev origin is NOT silently appended — env fully replaces it.
    blocked = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in blocked.headers


def test_cors_env_supports_comma_separated_list(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "ISAAC_UI_CORS_ORIGINS",
        "https://isaac-demo.vercel.app, http://localhost:5173",
    )
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- shared-secret bearer auth --------------------------------------------------


def test_auth_disabled_when_key_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/experiments").status_code == 200


def test_auth_rejects_missing_and_wrong_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)

    missing = client.get("/api/experiments")
    assert missing.status_code == 401
    assert missing.json()["error"] == "unauthorized"

    wrong = client.get(
        "/api/experiments", headers={"Authorization": "Bearer not-the-key"}
    )
    assert wrong.status_code == 401


def test_auth_accepts_correct_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    res = client.get(
        "/api/experiments", headers={"Authorization": "Bearer demo-secret"}
    )
    assert res.status_code == 200


def test_health_stays_open_with_auth_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/health").status_code == 200


def test_cors_preflight_passes_with_auth_enabled(tmp_path, monkeypatch):
    """Preflight OPTIONS carries no credentials by spec — auth must not eat it."""
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    res = client.options(
        "/api/experiments",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200


def test_401_carries_cors_headers(tmp_path, monkeypatch):
    """Browsers must see a readable 401, not an opaque CORS failure."""
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/api/experiments", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 401
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_auth_rejects_non_ascii_header_with_401(tmp_path, monkeypatch):
    """Malformed/non-ASCII credentials must fail closed as 401, never 500.

    Sent as raw latin-1 bytes: httpx refuses non-ASCII *str* header values
    client-side, but on the wire header values are bytes and starlette decodes
    them latin-1 — so this is exactly what dispatch() sees in production.
    """
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    res = client.get(
        "/api/experiments",
        headers={b"Authorization": "Bearer caf\xe9".encode("latin-1")},
    )
    assert res.status_code == 401


def test_auth_rejects_near_miss_header_forms(tmp_path, monkeypatch):
    """Pin the exact-match contract the frontend header must satisfy."""
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    for bad in ("bearer demo-secret", "Bearer  demo-secret"):
        res = client.get("/api/experiments", headers={"Authorization": bad})
        assert res.status_code == 401


# --- build/commit identity (P23D) ----------------------------------------------


def test_health_commit_null_when_neither_env_set(tmp_path, monkeypatch):
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    client = _make_client(tmp_path, monkeypatch)
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "mode": "synthetic-only",
        "core": "isaac_records",
        "version": body["version"],
        "commit": None,
        "database": {
            "configured": False,
            "classification": None,
            "contains_production_derived_records": None,
            "record_display": "closed",
            "last_recon": None,
        },
    }


def test_health_commit_from_isaac_build_commit_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "explicit-sha-123")
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/health").json()["commit"] == "explicit-sha-123"


def test_health_commit_falls_back_to_railway_sha(tmp_path, monkeypatch):
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "railway-sha-456")
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/health").json()["commit"] == "railway-sha-456"


def test_health_commit_isaac_build_commit_wins_over_railway(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "explicit-sha-123")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "railway-sha-456")
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/health").json()["commit"] == "explicit-sha-123"
