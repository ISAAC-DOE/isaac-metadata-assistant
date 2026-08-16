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
        # No PGHOST -> no application database -> experiments are stored in the
        # workspace directory only, which on the deployed pod is an `emptyDir`.
        "experiment_storage": {
            "configured": False,
            "backend": "filesystem",
            "durable": False,
            "state": "ephemeral",
        },
        # A deployment with no database and no configured verifier can record no
        # submission, and says so with both reasons rather than one. The field is
        # `configuration_permits` and not `available` deliberately: whether the
        # 0003/0004 tables exist cannot be known without opening a connection, and
        # `/api/health` opens none — so this block reports what the deployment is set
        # up to permit and never promises that the write would land.
        "submission": {
            "configuration_permits": False,
            "blockers": ["no_durable_storage", "no_attributable_actor"],
            "basis": "configuration_only",
            "requires_attributable_actor": True,
            # `null` means no actor can be established here at all. A deployment
            # running the fixture verifier would report `test_fixture`, which is what
            # makes "this deployment attributes on a basis that is not proof anyone
            # authenticated" visible from the health banner rather than only from the
            # manifest.
            "actor_trust_basis": None,
            "verifier_id": "unconfigured",
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


# --- the identity switch is not set by anything that ships ----------------------


def test_no_committed_deploy_artifact_arms_the_edge_trust_verifier():
    """``ISAAC_EDGE_TRUST_VERIFIER`` must not appear in anything that ships (I3).

    THE VARIABLE WAS INERT UNTIL THIS SLICE AND IS NOW LOAD-BEARING. Setting it to
    ``test_fixture`` selects ``identity.FixtureEdgeVerifier``, which mints an actor
    from the PROCESS ENVIRONMENT — so it is the switch that turns
    ``POST /api/experiments/{id}/submit`` from "always refused" into a path that
    writes durable, ATTRIBUTED rows into ``isaac_experiment_revisions`` and
    ``isaac_submissions``. A deployment artifact that set it would attribute
    scientific declarations on a basis that is not proof anyone authenticated.

    Every row it causes is stamped ``trust_basis = 'test_fixture'`` permanently, and
    ``/api/health`` surfaces it — but a label after the fact is a mitigation, not a
    gate, and this is the gate.

    WHAT IS SCANNED, AND WHAT IS DELIBERATELY NOT. The Dockerfile and the
    image-publishing workflow are what produce and configure the running container;
    no Kubernetes manifest is committed to this repository (they live in Dean's
    `isaac-k8`, which this test cannot see and does not claim to cover).
    ``.github/workflows/ci.yml`` is EXCLUDED on purpose: it is a test harness, it
    DOES set the variable for one job, and that is the correct place for it to
    appear. Excluding it is why the assertion below can be an absolute absence
    rather than a count.
    """
    from isaac_api.routes import REPO_ROOT

    artifacts = [
        REPO_ROOT / "Dockerfile",
        REPO_ROOT / ".github" / "workflows" / "build-push.yaml",
        REPO_ROOT / ".github" / "workflows" / "pr-docker-smoke.yml",
    ]
    present = [path for path in artifacts if path.exists()]
    assert present, "no deploy artifact was found, so this test proved nothing"
    for path in present:
        text = path.read_text("utf-8")
        for name in ("ISAAC_EDGE_TRUST_VERIFIER", "ISAAC_FIXTURE_ACTOR_SUBJECT"):
            assert name not in text, f"{path.name} names {name}"
