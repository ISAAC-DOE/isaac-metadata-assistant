"""Backend API tests — FastAPI TestClient over a tmp workspace.

Every test runs against an isolated ``ISAAC_UI_WORKSPACE`` (a tmp dir), so the seeded
demo experiment and any exports are created fresh and never touch the repo. The tests
assert the REAL core verdicts flow through unchanged (26/26 evidence, NO_LINKS advisory,
schema-gated export, immutability 409, synthetic-only governance).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- helpers ------------------------------------------------------------------


def _seed_id(client) -> str:
    """The canonical New Draft scenario id (raw, 5-pending) among the five seeds.

    P26.0a seeds FIVE canonical scenarios; these API tests drive the raw draft one
    through completion/export exactly as the old single seed did.
    """
    experiments = client.get("/api/experiments").json()["experiments"]
    assert len(experiments) == 5
    raw = [e for e in experiments if e["pending_count"] == 5]
    assert len(raw) == 1
    return raw[0]["id"]


def _complete_seed(client, exp_id: str) -> dict:
    """Apply every demo answer to the seed experiment via the real answers endpoint."""
    pending = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    answers = {
        b["id"]: b["demo_answer"]["value"]
        for b in pending
        if b["demo_answer"] is not None
    }
    resp = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
    )
    assert resp.status_code == 200
    return resp.json()


# --- 1. health ----------------------------------------------------------------


def test_health(client, monkeypatch):
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "mode": "synthetic-only",
        "core": "isaac_records",
        "version": body["version"],
        "commit": None,
    }
    assert body["version"]


# --- 2. demo run --------------------------------------------------------------


def test_demo_run_draft_only(client):
    body = client.post("/api/demo/run", json={"mode": "draft_only"}).json()
    assert body["status"] == "needs_attention"
    names = [s["name"] for s in body["steps"]]
    assert names == ["build_draft", "validate_draft"]
    assert all(s["ok"] for s in body["steps"])
    pending = client.get(f"/api/experiments/{body['experiment_id']}/pending").json()
    assert len(pending["pending"]) == 5


def test_demo_run_full_exports(client):
    body = client.post("/api/demo/run", json={"mode": "full"}).json()
    assert body["status"] == "done"
    names = [s["name"] for s in body["steps"]]
    assert names == ["build_draft", "validate_draft", "apply_answers", "export_draft"]
    assert all(s["ok"] for s in body["steps"])
    detail = client.get(f"/api/experiments/{body['experiment_id']}").json()
    assert detail["exported"] is True
    assert detail["record_id"] == body["experiment_id"]


def test_demo_run_default_mode_is_draft_only(client):
    body = client.post("/api/demo/run").json()
    assert body["status"] == "needs_attention"


def test_demo_run_rejects_invalid_mode(client):
    resp = client.post("/api/demo/run", json={"mode": "nonsense"})
    assert resp.status_code == 422


# --- 3-4. list / detail / 404 -------------------------------------------------


def test_list_seeds_five_canonical_experiments(client):
    experiments = client.get("/api/experiments").json()["experiments"]
    assert len(experiments) == 5
    # The raw New Draft scenario keeps the old single-seed properties.
    seed = next(e for e in experiments if e["pending_count"] == 5)
    assert "Synthetic" in seed["title"] and "New Draft" in seed["title"]
    assert seed["status"] == "needs_attention"
    assert seed["pending_count"] == 5
    assert seed["evidenced_field_count"] == 26
    assert seed["exported"] is False
    assert seed["record_id"] is None


def test_detail_shape(client):
    exp_id = _seed_id(client)
    detail = client.get(f"/api/experiments/{exp_id}").json()
    assert detail["draft_ok"] is True
    assert detail["artifact_refs"] == {"record_path": None, "sidecar_path": None}
    assert set(detail["source_files"]) == {"mock_campaign.csv", "raw_scan_listing.txt"}


def test_detail_404(client):
    resp = client.get("/api/experiments/NOPE")
    assert resp.status_code == 404


# --- 5. draft grouping --------------------------------------------------------


def test_draft_grouping(client):
    exp_id = _seed_id(client)
    groups = client.get(f"/api/experiments/{exp_id}/draft").json()["groups"]
    assert groups, "expected non-empty groups"
    titles = [g["title"] for g in groups]
    assert "Sample" in titles and "System & Instrument" in titles
    total_fields = sum(len(g["fields"]) for g in groups)
    assert total_fields == 26
    statuses = {f["status"] for g in groups for f in g["fields"]}
    assert "verified" in statuses and "inferred" in statuses
    a_field = groups[0]["fields"][0]
    assert set(a_field) == {"path", "label", "value", "status", "evidence_count", "source_types"}


# --- 6. pending ---------------------------------------------------------------


def test_pending_blockers(client):
    exp_id = _seed_id(client)
    pending = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert len(pending) == 5
    kinds = sorted(b["kind"] for b in pending)
    assert kinds == ["asset", "asset", "asset", "descriptor", "series"]
    # Every blocker has a labeled demo suggestion from the fixture answers.
    assert all(b["demo_answer"] is not None for b in pending)
    assert all(
        b["demo_answer"]["label"] == "Demo answer (synthetic)" for b in pending
    )


# --- 7. answers ---------------------------------------------------------------


def test_answers_requires_confirmation(client):
    exp_id = _seed_id(client)
    resp = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"series": [1, 2, 3]}, "confirmed_by_user": False},
    )
    assert resp.status_code == 422


def test_apply_full_answers_empties_pending(client):
    exp_id = _seed_id(client)
    result = _complete_seed(client, exp_id)
    assert result["pending"] == []
    assert result["status"] == "ready_to_export"


def test_blank_answers_not_applied(client):
    exp_id = _seed_id(client)
    resp = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"series": "", "descriptor": None}, "confirmed_by_user": True},
    )
    assert resp.status_code == 200
    # Nothing was answerable -> all 5 blockers remain.
    assert len(resp.json()["pending"]) == 5


# --- 8. export ----------------------------------------------------------------


def test_export_success_writes_record_and_sidecar(client):
    exp_id = _seed_id(client)
    _complete_seed(client, exp_id)
    resp = client.post(f"/api/experiments/{exp_id}/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    record_path = body["artifact_refs"]["record_path"]
    sidecar_path = body["artifact_refs"]["sidecar_path"]
    assert record_path != sidecar_path
    with open(record_path, encoding="utf-8") as fh:
        record = json.load(fh)
    with open(sidecar_path, encoding="utf-8") as fh:
        sidecar = json.load(fh)
    assert record["record_id"] == exp_id
    assert sidecar["record_id"] == exp_id


def test_export_second_time_is_409(client):
    exp_id = _seed_id(client)
    _complete_seed(client, exp_id)
    assert client.post(f"/api/experiments/{exp_id}/export").json()["ok"] is True
    resp = client.post(f"/api/experiments/{exp_id}/export")
    assert resp.status_code == 409


def test_export_refused_when_incomplete(client):
    exp_id = _seed_id(client)  # seed still has 5 open blockers
    resp = client.post(f"/api/experiments/{exp_id}/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"]
    # Nothing written: still not exported.
    assert client.get(f"/api/experiments/{exp_id}").json()["exported"] is False


# --- 9. validate --------------------------------------------------------------


def test_validate_dry_run_fail_then_pass(client):
    exp_id = _seed_id(client)
    fail = client.post(f"/api/experiments/{exp_id}/validate").json()
    assert fail["dry_run"] is True
    assert fail["ok"] is False
    assert fail["errors"]
    assert fail["schema"] == "ISAAC v1.05"

    _complete_seed(client, exp_id)
    ok = client.post(f"/api/experiments/{exp_id}/validate").json()
    assert ok["dry_run"] is True
    assert ok["ok"] is True
    assert ok["errors"] == []


def test_validate_on_exported_record(client):
    exp_id = _seed_id(client)
    _complete_seed(client, exp_id)
    client.post(f"/api/experiments/{exp_id}/export")
    body = client.post(f"/api/experiments/{exp_id}/validate").json()
    assert body["dry_run"] is False
    assert body["ok"] is True


def test_validate_corrupt_draft_returns_errors_not_exception(client, tmp_path):
    exp_id = _seed_id(client)
    # Corrupt the stored draft directly in the workspace, then validate.
    state_path = tmp_path / "ws" / exp_id / "experiment.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["draft"] = {"meta": {}, "fields": {"bogus.path": "not-an-envelope"}}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    resp = client.post(f"/api/experiments/{exp_id}/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"]


# --- 10. audit ----------------------------------------------------------------


def test_audit_full_coverage_after_export(client):
    exp_id = _seed_id(client)
    _complete_seed(client, exp_id)
    client.post(f"/api/experiments/{exp_id}/export")
    body = client.post(f"/api/experiments/{exp_id}/audit").json()
    assert len(body["records"]) == 1
    rec = body["records"][0]
    assert rec["ok"] is True
    # Honest record-derived denominator: 25 scalar + 8 block targets, all covered.
    assert rec["evidence_present"] == 33
    assert rec["evidence_expected"] == 33
    assert rec["uncovered"] == []
    assert rec["dangling"] == []
    assert "PASS" in body["text"]


def test_audit_empty_before_export(client):
    exp_id = _seed_id(client)
    body = client.post(f"/api/experiments/{exp_id}/audit").json()
    assert body["records"] == []
    assert "message" in body


# --- 11. warnings -------------------------------------------------------------


def test_warnings_advisory_non_gating_with_no_links(client):
    exp_id = _seed_id(client)
    _complete_seed(client, exp_id)
    client.post(f"/api/experiments/{exp_id}/export")
    body = client.get(f"/api/experiments/{exp_id}/warnings").json()
    assert body["advisory"] is True
    assert body["gating"] is False
    assert "ok" not in body and "valid" not in body
    codes = {w["code"] for w in body["warnings"]}
    assert "NO_LINKS" in codes


def test_warnings_accepts_post(client):
    exp_id = _seed_id(client)
    body = client.post(f"/api/experiments/{exp_id}/warnings").json()
    assert body["advisory"] is True and body["gating"] is False


# --- 12. evidence -------------------------------------------------------------


def test_evidence_pre_and_post_export(client):
    exp_id = _seed_id(client)
    pre = client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"]
    assert pre, "pre-export evidence trail should be non-empty"
    assert all({"path", "value", "status", "evidence"} <= set(e) for e in pre)

    _complete_seed(client, exp_id)
    client.post(f"/api/experiments/{exp_id}/export")
    post = client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"]
    assert post
    blob = json.dumps(post)
    # The synthetic sha256 for the raw scan set must be visible post-export.
    assert "a3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b123" in blob


# --- 13. source preview -------------------------------------------------------


def test_source_preview_serves_both_fixtures(client):
    exp_id = _seed_id(client)
    csv = client.get(
        f"/api/experiments/{exp_id}/source-preview", params={"source": "mock_campaign.csv"}
    ).json()
    assert csv["name"] == "mock_campaign.csv"
    assert csv["media_type"] == "text/csv"
    assert csv["lines"] and csv["lines"][0]["n"] == 1

    listing = client.get(
        f"/api/experiments/{exp_id}/source-preview",
        params={"source": "raw_scan_listing.txt"},
    ).json()
    assert listing["media_type"] == "text/plain"
    assert listing["cited_lines"], "listing evidence cites specific lines"


def test_source_preview_unknown_name_404(client):
    exp_id = _seed_id(client)
    resp = client.get(
        f"/api/experiments/{exp_id}/source-preview", params={"source": "secret.xlsx"}
    )
    assert resp.status_code == 404


def test_source_preview_rejects_traversal_and_absolute(client):
    exp_id = _seed_id(client)
    for bad in ("../schema/isaac_record_v1.json", "/etc/passwd", "a/b.csv"):
        resp = client.get(
            f"/api/experiments/{exp_id}/source-preview", params={"source": bad}
        )
        assert resp.status_code == 400


# --- 13b. artifacts -----------------------------------------------------------


def test_artifacts_before_export_are_null(client):
    exp_id = _seed_id(client)
    body = client.get(f"/api/experiments/{exp_id}/artifacts").json()
    assert body == {
        "record": None,
        "sidecar": None,
        "record_path": None,
        "sidecar_path": None,
    }


def test_artifacts_after_export_returns_record_and_sidecar(client):
    exp_id = _seed_id(client)
    _complete_seed(client, exp_id)
    export = client.post(f"/api/experiments/{exp_id}/export").json()
    body = client.get(f"/api/experiments/{exp_id}/artifacts").json()
    # Both payloads present and distinct.
    assert body["record"] is not None and body["sidecar"] is not None
    assert body["record"] != body["sidecar"]
    assert body["record"]["record_id"] == exp_id
    assert body["sidecar"]["record_id"] == exp_id
    # Read from disk matches exactly what export returned/wrote.
    assert body["record"] == export["record"]
    assert body["sidecar"] == export["sidecar"]
    # The two artifacts live at distinct paths.
    assert body["record_path"] != body["sidecar_path"]
    assert body["record_path"].endswith(f"{exp_id}.json")
    assert body["sidecar_path"].endswith(f"{exp_id}.evidence.json")


def test_artifacts_unknown_id_404(client):
    resp = client.get("/api/experiments/NOPE/artifacts")
    assert resp.status_code == 404


# --- 14. graph status ---------------------------------------------------------


def test_graph_status(client, monkeypatch):
    # P24.10: the deployed commit is forced to None so the body is deterministic
    # regardless of whether this dev machine happens to have a real graphify-out/.
    # It is metadata only and never drives any freshness value.
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    body = client.get("/api/graph/status").json()
    assert "status" not in body  # conflated single status removed
    assert body["availability"] in {"available", "unavailable"}
    assert body["memory_policy"] in {"current", "stale", "unknown"}
    assert body["indexed_sources"] in {"current", "stale", "unknown"}
    assert body["plane"] == "memory"
    assert body["note"]
    for banned in ("valid", "invalid", "PASS", "FAIL", "verdict"):
        assert banned not in body["note"]


# --- 15. uploads --------------------------------------------------------------


def test_uploads_always_blocked(client):
    resp = client.post("/api/uploads")
    assert resp.status_code == 403
    body = resp.json()
    assert body["blocked"] is True
    assert "approval-gated" in body["reason"]
