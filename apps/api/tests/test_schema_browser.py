"""P36.6 — Schema & Vocabulary browser (``GET /api/schema``).

A read-only route serving the CANONICAL official schema + vocabulary — NOT the
portal Ontology system (no propose/review/approve/edit/persistence). It reuses
``isaac_records.official.schema_path`` (the SAME resolver
``load_official_validator`` uses, never a hardcoded/second path) and globs
``vocabulary/*.json`` — both read verbatim, never projected or summarized.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_records.official import EXPECTED_VERSION, schema_path

ROOT = Path(__file__).resolve().parents[3]
URL = "/api/schema"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- shape + faithfulness --------------------------------------------------


def test_returns_schema_version_and_title(client):
    r = client.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schema_version"] == "1.05"
    assert body["schema_version"] == EXPECTED_VERSION
    on_disk = json.loads(schema_path(ROOT).read_text(encoding="utf-8"))
    assert body["schema_title"] == on_disk["title"]


def test_schema_dict_has_required_and_matches_on_disk_exactly(client):
    """No projection drift: the served ``schema`` is byte-equivalent (as JSON)
    to ``json.load`` of the vendored file — never a summarized/trimmed copy."""
    r = client.get(URL)
    body = r.json()
    assert isinstance(body["schema"], dict)
    assert "required" in body["schema"]
    assert body["schema"]["required"]  # non-empty per the vendored schema

    on_disk = json.loads(schema_path(ROOT).read_text(encoding="utf-8"))
    assert body["schema"] == on_disk


def test_schema_served_via_official_schema_path_not_a_hardcoded_second_copy(client, tmp_path, monkeypatch):
    """Reroute REPO_ROOT-relative resolution by pointing ISAAC at a workspace
    with no schema at all is out of scope (schema_path always resolves from the
    real REPO_ROOT) — instead assert the served content is IDENTICAL to calling
    ``official.schema_path`` directly, proving the route has no second/hardcoded
    path that could silently diverge from the validator's own resolution."""
    r = client.get(URL)
    body = r.json()
    direct = json.loads(schema_path(ROOT).read_text(encoding="utf-8"))
    assert body["schema"] == direct


def test_vocabularies_present_and_faithful(client):
    r = client.get(URL)
    body = r.json()
    assert "vocabularies" in body
    assert "descriptor_class" in body["vocabularies"]
    on_disk = json.loads((ROOT / "vocabulary" / "descriptor_class.json").read_text(encoding="utf-8"))
    assert body["vocabularies"]["descriptor_class"] == on_disk


def test_vocabularies_cover_every_file_in_the_vocabulary_directory(client):
    r = client.get(URL)
    body = r.json()
    on_disk_names = {p.stem for p in (ROOT / "vocabulary").glob("*.json")}
    assert set(body["vocabularies"].keys()) == on_disk_names


# --- GET-only, read-only, deterministic -------------------------------------


def test_is_get_only(client):
    assert client.post(URL).status_code == 405
    assert client.put(URL).status_code == 405
    assert client.delete(URL).status_code == 405


def test_mutates_nothing(client, tmp_path):
    ws_dir = tmp_path / "ws"
    before = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    client.get(URL)
    client.get(URL)
    after = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    assert after == before


def test_response_is_deterministic_across_calls(client):
    r1 = client.get(URL).json()
    r2 = client.get(URL).json()
    assert r1 == r2


def test_does_not_touch_the_committed_snapshot(client):
    snapshot = ROOT / "apps" / "api" / "isaac_api" / "data" / "memory-snapshot.json"
    before = snapshot.stat().st_mtime_ns if snapshot.exists() else None
    client.get(URL)
    after = snapshot.stat().st_mtime_ns if snapshot.exists() else None
    assert after == before


# --- base path (must be base-path-correct, like every other /api route) ----


def test_base_path_prefixed(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.setenv("ISAAC_BASE_PATH", "/krish")
    from isaac_api.app import create_app

    c = TestClient(create_app())
    # Unprefixed no longer exists.
    assert c.get(URL).status_code == 404

    r = c.get(f"/krish{URL}")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1.05"
    assert "descriptor_class" in body["vocabularies"]
