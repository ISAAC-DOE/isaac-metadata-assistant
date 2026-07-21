"""Base-path + single-container SPA serving tests (k8s deployment seams).

Two env-driven seams, both defaulting OFF so local dev stays byte-identical:

- ``ISAAC_BASE_PATH`` prefixes every API route (``/krish`` -> ``/krish/api/*``).
- ``ISAAC_STATIC_DIR`` points at a built Vite ``dist/``; when set, the app also
  serves the SPA under the base path with an ``index.html`` fallback for
  client-side routes (replacing the Vercel rewrite from the retired hosting).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch, base=None, static=False) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    if base is None:
        monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    else:
        monkeypatch.setenv("ISAAC_BASE_PATH", base)
    if static:
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>spa</title>")
        (dist / "assets" / "app.js").write_text("console.log('spa')")
        (dist / "vite.svg").write_text("<svg></svg>")
        monkeypatch.setenv("ISAAC_STATIC_DIR", str(dist))
    else:
        monkeypatch.delenv("ISAAC_STATIC_DIR", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- base path off (default): historical behavior pinned -----------------------


def test_default_routes_unprefixed_and_no_spa(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/health").status_code == 200
    # No SPA catch-all locally: unknown paths are plain 404s.
    assert client.get("/record/demo").status_code == 404


def test_base_path_normalization_blank_and_slash(tmp_path, monkeypatch):
    for raw in ("", "/", "  "):
        client = _make_client(tmp_path, monkeypatch, base=raw)
        assert client.get("/api/health").status_code == 200


# --- base path on: API moves under {base}/api ----------------------------------


def test_api_served_under_base_path(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, base="/krish")
    assert client.get("/krish/api/health").status_code == 200
    assert client.get("/krish/api/experiments").status_code == 200
    # The unprefixed path no longer exists.
    assert client.get("/api/health").status_code == 404


def test_base_path_tolerates_unnormalized_values(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, base="krish/")
    assert client.get("/krish/api/health").status_code == 200


def test_health_stays_open_under_base_path_with_auth(tmp_path, monkeypatch):
    """Pod probes hit {base}/api/health directly and must never need creds."""
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch, base="/krish")
    assert client.get("/krish/api/health").status_code == 200
    assert client.get("/krish/api/experiments").status_code == 401


# --- SPA serving (ISAAC_STATIC_DIR set) -----------------------------------------


def test_spa_index_served_at_base_with_and_without_slash(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, base="/krish", static=True)
    for path in ("/krish", "/krish/"):
        res = client.get(path)
        assert res.status_code == 200
        assert "spa" in res.text


def test_spa_fallback_serves_index_for_client_routes(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, base="/krish", static=True)
    for path in ("/krish/experiments", "/krish/record/EXP-1/evidence"):
        res = client.get(path)
        assert res.status_code == 200
        assert "spa" in res.text


def test_spa_serves_real_static_files(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, base="/krish", static=True)
    assert client.get("/krish/assets/app.js").status_code == 200
    assert client.get("/krish/vite.svg").status_code == 200


def test_spa_fallback_preserves_api_404_semantics(tmp_path, monkeypatch):
    """Unknown API routes stay JSON 404s — never swallowed into index.html."""
    client = _make_client(tmp_path, monkeypatch, base="/krish", static=True)
    res = client.get("/krish/api/definitely-not-a-route")
    assert res.status_code == 404
    assert "text/html" not in res.headers.get("content-type", "")


def test_spa_fallback_rejects_path_traversal(tmp_path, monkeypatch):
    (tmp_path / "outside.txt").write_text("secret")
    client = _make_client(tmp_path, monkeypatch, base="/krish", static=True)
    res = client.get("/krish/%2e%2e/outside.txt")
    # Never the file outside dist: either index fallback or a 4xx.
    assert "secret" not in res.text


def test_spa_works_at_root_base_too(tmp_path, monkeypatch):
    """ISAAC_STATIC_DIR without ISAAC_BASE_PATH serves the SPA at /."""
    client = _make_client(tmp_path, monkeypatch, static=True)
    assert client.get("/api/health").status_code == 200
    res = client.get("/experiments")
    assert res.status_code == 200
    assert "spa" in res.text


def test_missing_static_dir_fails_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_STATIC_DIR", str(tmp_path / "nope"))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_BASE_PATH", "/krish")
    from isaac_api.app import create_app

    client = TestClient(create_app())
    assert client.get("/krish/api/health").status_code == 200
    assert client.get("/krish/experiments").status_code == 404
