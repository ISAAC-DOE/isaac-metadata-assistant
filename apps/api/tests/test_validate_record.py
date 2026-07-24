"""P36.3 — Standalone Validator (`POST /api/validate/record`).

Governance & Safety gets a functional destination: paste/upload a candidate
JSON record and check it against the vendored official ISAAC schema, with NO
experiment, NO draft, and NO workspace mutation. The route REUSES
``isaac_records.official.validate_official`` — the exact function
``POST /experiments/{id}/validate`` already calls for exported records — so
this test suite asserts VERDICT PARITY (same ok/errors) against calling that
function directly, rather than re-deriving pass/fail rules of its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_records.official import validate_official

ROOT = Path(__file__).resolve().parents[3]
VALID_RECORD = json.loads(
    (ROOT / "tests" / "fixtures" / "official" / "ex_situ_xanes_cuo2_record.json").read_text(
        encoding="utf-8"
    )
)

URL = "/api/validate/record"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- valid / invalid records, verdict parity ------------------------------------


def test_valid_record_passes_with_empty_errors(client):
    r = client.post(URL, json=VALID_RECORD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["errors"] == []
    assert "PASS" in body["summary"]
    assert body["schema_version"] == "1.05"


def test_invalid_record_fails_with_structured_errors(client):
    bad = dict(VALID_RECORD)
    bad["system"] = dict(bad["system"])
    bad["system"]["technique"] = "telepathy"  # bad vocabulary — schema violation
    r = client.post(URL, json=bad)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["errors"]
    for err in body["errors"]:
        assert set(err.keys()) == {"path", "message"}
    assert "FAIL" in body["summary"]


@pytest.mark.parametrize(
    "record",
    [
        VALID_RECORD,
        {**VALID_RECORD, "system": {**VALID_RECORD["system"], "technique": "telepathy"}},
        {"isaac_record_version": "1.05"},  # minimal, obviously incomplete
    ],
)
def test_endpoint_matches_validate_official_directly(client, record):
    """The route must never diverge from calling the authoritative function
    directly on the same input — no second validation implementation."""
    direct = validate_official(record, ROOT)
    r = client.post(URL, json=record)
    body = r.json()
    assert body["ok"] == direct.ok
    assert body["errors"] == [{"path": e.path, "message": e.message} for e in direct.errors]


# --- malformed input: clean typed errors, never a 500 ---------------------------


def test_non_object_body_is_clean_error_not_500(client):
    r = client.post(URL, json=["not", "an", "object"])
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "not_a_json_object"
    assert "message" in body


def test_non_object_scalar_body_is_clean_error(client):
    r = client.post(URL, json="just a string")
    assert r.status_code == 422
    assert r.json()["error"] == "not_a_json_object"


def test_malformed_json_is_clean_error_not_500(client):
    r = client.post(
        URL, content=b"{not valid json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_json"


def test_empty_body_is_clean_error_not_500(client):
    r = client.post(URL, content=b"", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


# --- bounded body: 413 before parse ----------------------------------------------


def test_oversized_body_rejected_413(client):
    huge = json.dumps({"padding": "x" * (600 * 1024)}).encode("utf-8")
    r = client.post(URL, content=huge, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"] == "request_too_large"


# --- no mutation / no persistence ------------------------------------------------


def test_no_workspace_file_created(client, tmp_path):
    ws_dir = tmp_path / "ws"
    before = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    client.post(URL, json=VALID_RECORD)
    client.post(URL, json={"bad": "record"})
    after = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    assert after == before, "the standalone validator must never write to the workspace"


def test_no_snapshot_mtime_change(client):
    snapshot = ROOT / "apps" / "api" / "isaac_api" / "data" / "memory-snapshot.json"
    before = snapshot.stat().st_mtime_ns if snapshot.exists() else None
    client.post(URL, json=VALID_RECORD)
    after = snapshot.stat().st_mtime_ns if snapshot.exists() else None
    assert after == before, "the standalone validator must never touch the committed snapshot"


# --- base path (P36.3 must be base-path-correct, like every other /api route) ---


def test_base_path_prefixes_the_route(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.setenv("ISAAC_BASE_PATH", "/krish")
    from isaac_api.app import create_app

    c = TestClient(create_app())
    assert c.post(URL, json=VALID_RECORD).status_code == 404  # unprefixed no longer exists
    r = c.post(f"/krish{URL}", json=VALID_RECORD)
    assert r.status_code == 200
    assert r.json()["ok"] is True
