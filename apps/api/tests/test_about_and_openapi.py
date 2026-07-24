"""P36.4 — Settings "Help / About" + "API Documentation" backend routes.

Two read-only, mutation-free GET routes:

  - ``GET /api/about``   — non-sensitive app/provenance metadata, reusing the
    SAME authoritative sources ``/health`` uses (``__version__``,
    ``_build_commit()``, ``runtime_mode.runtime_mode()``) plus
    ``isaac_records.official.EXPECTED_VERSION`` (read-only import — the truth
    core is never modified here).
  - ``GET /api/openapi`` — the app's own generated OpenAPI schema
    (``request.app.openapi()``), reachable under the base-path-prefixed
    ``/api`` router so the frontend docs render correctly under a deployed
    base path. No hand-maintained duplicate API description.

Both must be base-path-correct (``ISAAC_BASE_PATH=/krish`` -> the routes move
to ``/krish/api/about`` / ``/krish/api/openapi``, matching every other route
in this module), GET-only, and side-effect free.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from isaac_api.routes import _build_commit
from isaac_records.official import EXPECTED_VERSION


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- GET /api/about ------------------------------------------------------------


def test_about_returns_expected_non_sensitive_fields(client):
    r = client.get("/api/about")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "app_version",
        "build_commit",
        "record_schema_version",
        "runtime_mode",
        "persistence",
        "data_regime",
        "core",
    }
    assert body["record_schema_version"] == "1.05"
    assert body["record_schema_version"] == EXPECTED_VERSION
    assert body["runtime_mode"] == "synthetic-only"
    assert body["persistence"] == "ephemeral"
    assert body["data_regime"] == "synthetic-only"
    assert body["core"] == "isaac_records"
    assert isinstance(body["app_version"], str) and body["app_version"]


def test_about_build_commit_matches_build_commit_helper_when_unset(client):
    # No ISAAC_BUILD_COMMIT / RAILWAY_GIT_COMMIT_SHA set by the fixture -> None,
    # matching the live (uncached) `_build_commit()` read.
    r = client.get("/api/about")
    assert r.json()["build_commit"] == _build_commit()
    assert r.json()["build_commit"] is None


def test_about_build_commit_reuses_build_commit_helper_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "fakecommit0000aboutp364")
    from isaac_api.app import create_app

    c = TestClient(create_app())
    r = c.get("/api/about")
    assert r.json()["build_commit"] == "fakecommit0000aboutp364"
    assert r.json()["build_commit"] == _build_commit()


# --- no sensitive infra / secret / absolute-path leakage ------------------------

_FORBIDDEN_SUBSTRINGS = (
    "authentik",
    "ingress",
    "k8s",
    "kubernetes",
    "railway.app",
    "vercel.app",
    "127.0.0.1",
    "localhost",
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "/Users/",
    "/home/",
    "C:\\",
)


def test_about_contains_no_secret_or_infra_host_strings(client, tmp_path):
    r = client.get("/api/about")
    dumped = json.dumps(r.json()).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in dumped, f"unexpected leak: {needle!r} in {dumped!r}"
    # Never leaks the local workspace path used by this very test.
    assert str(tmp_path).lower() not in dumped


def test_about_is_get_only(client):
    assert client.post("/api/about").status_code == 405
    assert client.put("/api/about").status_code == 405
    assert client.delete("/api/about").status_code == 405


def test_about_mutates_nothing(client, tmp_path):
    ws_dir = tmp_path / "ws"
    before = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    client.get("/api/about")
    client.get("/api/about")
    after = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    assert after == before


# --- GET /api/openapi ------------------------------------------------------------


def test_openapi_returns_schema_with_paths(client):
    r = client.get("/api/openapi")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "openapi" in body
    assert "paths" in body
    assert isinstance(body["paths"], dict)


def test_openapi_includes_a_known_route(client):
    r = client.get("/api/openapi")
    paths = r.json()["paths"]
    assert "/api/health" in paths
    assert "get" in paths["/api/health"]
    # The new routes document themselves too.
    assert "/api/about" in paths
    assert "/api/openapi" in paths


def test_openapi_matches_root_openapi_json(client):
    """Same generated schema FastAPI already serves at the root — no second
    hand-maintained description."""
    root = client.get("/openapi.json").json()
    api = client.get("/api/openapi").json()
    assert api == root


def test_openapi_is_get_only(client):
    assert client.post("/api/openapi").status_code == 405


def test_openapi_mutates_nothing(client, tmp_path):
    ws_dir = tmp_path / "ws"
    before = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    client.get("/api/openapi")
    after = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    assert after == before


# --- base path (P36.4 must be base-path-correct, like every other /api route) ---


def test_about_and_openapi_base_path_prefixed(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.setenv("ISAAC_BASE_PATH", "/krish")
    from isaac_api.app import create_app

    c = TestClient(create_app())

    # Unprefixed no longer exists.
    assert c.get("/api/about").status_code == 404
    assert c.get("/api/openapi").status_code == 404

    r_about = c.get("/krish/api/about")
    assert r_about.status_code == 200
    assert r_about.json()["record_schema_version"] == "1.05"

    r_openapi = c.get("/krish/api/openapi")
    assert r_openapi.status_code == 200
    paths = r_openapi.json()["paths"]
    # Under a base path, the generated schema's own paths carry the prefix too.
    assert "/krish/api/health" in paths
    assert "/krish/api/about" in paths
