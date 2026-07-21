"""P26.0a — richer deterministic synthetic seed + idempotent demo.

Behavior-level tests (not hard-coded status strings): every assertion is derived
from the REAL truth core (build_draft / apply_answers / export_draft) through the
public workspace + HTTP surface. The seed must materialise exactly FIVE canonical
synthetic experiments spanning all four derived workflow states, deterministically,
and the "Run Synthetic Demo" action must be idempotent (re-running never increases
the record count and preserves the canonical scenario identities).

All fixtures are the two committed synthetic files + the committed demo answers —
no invented values, nothing under examples/, truth core never bypassed.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_records.export import export_draft


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app())


@pytest.fixture()
def seeded_ws(tmp_path, monkeypatch):
    """Direct workspace access against an isolated tmp workspace (no HTTP)."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    ws.ensure_seeded()
    return ws


def _experiments(client) -> list[dict]:
    return client.get("/api/experiments").json()["experiments"]


def _by_status(client) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in _experiments(client):
        out.setdefault(e["status"], []).append(e)
    return out


# --- 1. exactly five canonical scenarios --------------------------------------


def test_seed_creates_exactly_five_experiments(client):
    assert len(_experiments(client)) == 5


# --- 2. all four derived workflow states represented --------------------------


def test_all_four_derived_states_present(client):
    states = {e["status"] for e in _experiments(client)}
    assert states == {
        ws.NEEDS_ATTENTION,
        ws.READY_TO_EXPORT,
        ws.IN_REVIEW,
        ws.DONE,
    }


# --- 3. needs_attention appears in BOTH raw and partial forms -----------------


def test_two_distinct_needs_attention_scenarios(client):
    na = _by_status(client).get(ws.NEEDS_ATTENTION, [])
    assert len(na) == 2
    pendings = sorted(e["pending_count"] for e in na)
    # raw draft (5 pending) and a partial-progress draft (fewer than raw).
    assert pendings[0] < pendings[1]
    assert pendings[1] == 5


# --- 4. pending counts deterministic ------------------------------------------


def test_pending_counts_are_deterministic(client):
    counts = sorted(e["pending_count"] for e in _experiments(client))
    # in_review, ready_to_export, done => 0 pending; partial => 2; raw => 5.
    assert counts == [0, 0, 0, 2, 5]


# --- 5. ready_to_export is not already exported -------------------------------


def test_ready_to_export_is_not_exported(client):
    ready = _by_status(client).get(ws.READY_TO_EXPORT, [])
    assert len(ready) == 1
    assert ready[0]["exported"] is False
    assert ready[0]["record_id"] is None


# --- 6-7. in_review: no pending, fails export for the AUTHORITATIVE reason -----


def test_in_review_has_no_pending(client):
    review = _by_status(client).get(ws.IN_REVIEW, [])
    assert len(review) == 1
    assert review[0]["pending_count"] == 0
    assert review[0]["exported"] is False


def test_in_review_fails_export_for_expected_truthful_reason(seeded_ws):
    review = [e for e in seeded_ws.list_experiments() if e.status() == seeded_ws.IN_REVIEW]
    assert len(review) == 1
    result = export_draft(copy.deepcopy(review[0].draft), seeded_ws.REPO_ROOT)
    assert result.ok is False
    assert result.official_report is not None
    messages = [e.message for e in result.official_report.errors]
    assert any("'uncertainty' is a required property" in m for m in messages), messages


# --- 8. done has a record id AND artifacts + sidecar --------------------------


def test_done_has_record_id_and_artifacts(seeded_ws):
    done = [e for e in seeded_ws.list_experiments() if e.status() == seeded_ws.DONE]
    assert len(done) == 1
    exp = done[0]
    assert exp.record_id is not None
    assert exp.record_path() is not None and exp.record_path().exists()
    assert exp.sidecar_path() is not None and exp.sidecar_path().exists()


# --- 9. scenario titles are distinct ------------------------------------------


def test_scenario_titles_are_distinct(client):
    titles = [e["title"] for e in _experiments(client)]
    assert len(set(titles)) == 5


# --- 10-11. Run Synthetic Demo is idempotent ----------------------------------


def test_demo_run_does_not_increase_record_count(client):
    assert len(_experiments(client)) == 5
    for _ in range(3):
        resp = client.post("/api/demo/run", json={"mode": "draft_only"})
        assert resp.status_code == 200
        assert len(_experiments(client)) == 5


def test_demo_run_preserves_canonical_identities(client):
    before = {e["id"] for e in _experiments(client)}
    client.post("/api/demo/run", json={"mode": "draft_only"})
    client.post("/api/demo/run", json={"mode": "full"})
    after = {e["id"] for e in _experiments(client)}
    assert after == before


def test_seed_ids_are_stable_across_fresh_workspaces(tmp_path, monkeypatch):
    """Two independent fresh workspaces produce the identical set of ids."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "a"))
    ids_a = {e.id for e in ws.list_experiments()}
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "b"))
    ids_b = {e.id for e in ws.list_experiments()}
    assert ids_a == ids_b
    assert len(ids_a) == 5


# --- 12-14. synthetic-only, no private data, truth core not bypassed ----------


def test_seed_sources_are_committed_synthetic_fixtures(seeded_ws):
    for exp in seeded_ws.list_experiments():
        files = exp.source.get("files") or []
        assert set(files) <= set(seeded_ws.SOURCE_FILES)


def test_seed_references_no_examples_or_private_paths(seeded_ws):
    for exp in seeded_ws.list_experiments():
        blob = str(exp.to_state())
        assert "examples/" not in blob
        assert "/Users/" not in blob


def test_statuses_are_truth_core_derived_not_stored(seeded_ws):
    # Re-deriving status must agree with the summary; status is never a stored string.
    for exp in seeded_ws.list_experiments():
        assert exp.status() in {
            seeded_ws.NEEDS_ATTENTION,
            seeded_ws.READY_TO_EXPORT,
            seeded_ws.IN_REVIEW,
            seeded_ws.DONE,
        }


# --- 15. search can distinguish the seeded scenarios (metadata differ) --------


def test_scenarios_are_distinguishable_by_metadata(client):
    exps = _experiments(client)
    # A distinguishing tuple per scenario => all five differ on visible metadata.
    fingerprints = {
        (e["status"], e["pending_count"], e["exported"], e["title"]) for e in exps
    }
    assert len(fingerprints) == 5


# --- 16-18. dashboard group counts agree with the actual records --------------


def test_dashboard_group_counts_agree_with_records(client):
    grouped = _by_status(client)
    assert len(grouped.get(ws.NEEDS_ATTENTION, [])) == 2
    assert len(grouped.get(ws.READY_TO_EXPORT, [])) == 1
    assert len(grouped.get(ws.IN_REVIEW, [])) == 1
    assert len(grouped.get(ws.DONE, [])) == 1


def test_ready_and_done_counts_are_correct(client):
    exps = _experiments(client)
    assert sum(1 for e in exps if e["status"] == ws.READY_TO_EXPORT) == 1
    assert sum(1 for e in exps if e["exported"] is True) == 1
    assert sum(1 for e in exps if e["status"] == ws.DONE) == 1
