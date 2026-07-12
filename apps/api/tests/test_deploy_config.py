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
