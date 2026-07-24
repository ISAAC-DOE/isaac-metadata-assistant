"""P28.2 — dependency-aware downstream invalidation (contract shape).

TEST-FIRST contract (authored BEFORE implementation; RED until `_detail` carries
an `artifact` freshness block and the two authoritative mutations return
`workflow` + `invalidation`). This file pins the RESPONSE CONTRACT; the
behavioral fixture cases (stale-on-scientific-change, current-on-presentation-
change, reopened-named, reset-baseline) are added alongside the implementation
under the same red-first discipline.

Design (grounded in the P28.0 audit + export.transform):
  * Artifact freshness is DERIVED from official-record content, not the draft
    signature: an exported artifact is `stale` iff transform(current_draft) differs
    from the on-disk exported record (normalising the export timestamp). `title`/
    `source` are NOT in the official record, so a presentation-only change never
    stales; a scientific field change does.
  * The workflow (P28.1) is already derived; a mutation reports the reopen DELTA.
  * No new persisted field; atomic inside the existing record_lock + one
    save_versioned rev-bump. A byte-stable no-op invalidates nothing.
Truth core untouched. All fixtures synthetic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.dependencies as dependencies
import isaac_api.workspace as ws

ARTIFACT_STATES = {"none", "current", "stale"}
INVALIDATION_KEYS = {"changed", "rev", "changed_fields", "reopened_steps", "artifact", "reason"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _real_answers_payload():
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


def _etag(client, exp_id):
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200
    return r.headers["ETag"]


# --- detail carries an artifact freshness block -------------------------------


def test_detail_has_artifact_state_none_when_not_exported(client):
    d = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    assert "artifact" in d, "detail must carry a derived artifact freshness block"
    assert d["artifact"]["state"] == "none"  # nothing exported yet
    assert set(d["artifact"]) >= {"state", "reason"}


def test_detail_has_artifact_state_current_when_exported_and_fresh(client):
    d = client.get(f"/api/experiments/{ws.SEED_DONE_ID}").json()
    assert d["artifact"]["state"] == "current", "a freshly-exported record is current"
    assert d["artifact"]["state"] in ARTIFACT_STATES


# --- mutation returns workflow + invalidation ---------------------------------


def test_answers_response_carries_workflow_and_invalidation(client):
    im = {"If-Match": _etag(client, ws.SEED_NEW_DRAFT_ID)}
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=im,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "workflow" in body and "ordered_steps" in body["workflow"]
    assert "invalidation" in body
    inv = body["invalidation"]
    assert set(inv) >= INVALIDATION_KEYS, f"invalidation keys: {set(inv)}"
    assert inv["changed"] is True  # a real scientific answer changed the draft
    # invalidation is reported at the SAME new revision as the record (mandate #12)
    assert inv["rev"] == body["version"].split(".")[-1] or inv["rev"] == int(
        body["version"].split(".")[-1]
    )
    assert inv["artifact"]["state"] in ARTIFACT_STATES


def test_noop_resubmission_invalidates_nothing_and_does_not_bump_rev(client):
    im = {"If-Match": _etag(client, ws.SEED_NEW_DRAFT_ID)}
    first = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=im,
    )
    assert first.status_code == 200, first.text
    rev_after_first = first.json()["version"]
    # resubmit the SAME answers with the fresh token → byte-stable no-op
    im2 = {"If-Match": f'"{rev_after_first}"'}
    second = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=im2,
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["version"] == rev_after_first, "a no-op must not bump the version"
    inv = body["invalidation"]
    assert inv["changed"] is False, "identical value → nothing changed"
    assert inv["changed_fields"] == []
    assert inv["reopened_steps"] == []


def test_export_response_carries_workflow_and_invalidation(client):
    im = {"If-Match": _etag(client, ws.SEED_READY_ID)}
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers=im)
    assert r.status_code == 200 and r.json().get("ok") is True, r.text
    body = r.json()
    assert "workflow" in body and "invalidation" in body
    # after export the artifact is current and the workflow is fully completed
    assert body["invalidation"]["artifact"]["state"] == "current"
    assert body["workflow"]["current_step"] is None


# --- behavioral fixtures (added red-first alongside the implementation) --------


def _first_scientific_field(draft: dict) -> str:
    """A draft field path whose value transform() actually writes into the record
    (non-null, not honestly-missing). Mutating it changes the official record."""
    for path, env in (draft.get("fields") or {}).items():
        if (
            isinstance(env, dict)
            and env.get("value") is not None
            and env.get("status") != "missing"
        ):
            return path
    raise AssertionError("no scientific field with a written value found in draft")


def test_scientific_change_stales_the_exported_artifact(client):
    # Export the ready seed through the real API (with a valid If-Match).
    im = {"If-Match": _etag(client, ws.SEED_READY_ID)}
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers=im)
    assert r.status_code == 200 and r.json().get("ok") is True, r.text
    # Fresh out of export the artifact is a faithful projection of the draft.
    d0 = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()
    assert d0["artifact"]["state"] == "current"

    # A completed record has no pending blockers, so /answers cannot change a
    # scientific field (apply_answers only fills existing pending). Construct the
    # scientific change at the workspace level, exactly as the spec directs.
    exp = ws.load_experiment(ws.SEED_READY_ID)
    assert exp.exported()
    path = _first_scientific_field(exp.draft)
    exp.draft["fields"][path]["value"] = "STALE-SENTINEL-CHANGED"
    exp.save()

    d1 = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()
    assert d1["artifact"]["state"] == "stale", "a scientific field change must stale the artifact"
    assert d1["artifact"]["reason"], "a stale artifact must carry a human reason"


def test_presentation_only_change_does_not_stale(client):
    # Export a record, then change ONLY the presentation title (not in the official
    # record). The exported artifact must stay current.
    im = {"If-Match": _etag(client, ws.SEED_READY_ID)}
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export", headers=im)
    assert r.status_code == 200 and r.json().get("ok") is True, r.text

    exp = ws.load_experiment(ws.SEED_READY_ID)
    exp.title = "Renamed Experiment"
    exp.save()

    # Direct unit assertion on the pure derivation.
    exp2 = ws.load_experiment(ws.SEED_READY_ID)
    assert exp2.title == "Renamed Experiment"
    assert dependencies.artifact_state(exp2)["state"] == "current"

    # And through the HTTP detail bundle.
    d = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()
    assert d["artifact"]["state"] == "current", "title is not in the official record; stays current"


def test_exported_then_regressed_workflow_and_artifact_are_coherent(client):
    """Construct an exported-then-regressed record (as in test_workflow_order.py):
    reintroduce a pending blocker AND change a scientific field on the exported
    DONE seed. The DERIVED workflow reopens the downstream steps and the artifact
    goes stale — the two invalidation signals are coherent.

    Note: no FORWARD API mutation (/answers fills pending, /export completes) can
    itself un-complete a step, so an invalidation DELTA's ``reopened_steps`` is []
    for forward mutations by design; the reopen lives in the derived workflow. This
    asserts that derived reopen + stale artifact agree after a real regression.
    """
    # Borrow a real, serialize-accepted pending entry from the fresh-draft seed.
    fresh = ws.load_experiment(ws.SEED_NEW_DRAFT_ID)
    borrowed_pending = fresh.pending()[0]

    exp = ws.load_experiment(ws.SEED_DONE_ID)
    assert exp.exported() and exp.record_id is not None
    exp.draft.setdefault("pending", []).append(borrowed_pending)
    # Also change a scientific field so the exported artifact no longer matches.
    path = _first_scientific_field(exp.draft)
    exp.draft["fields"][path]["value"] = "REGRESSED-SENTINEL"
    exp.save()

    body = client.get(f"/api/experiments/{ws.SEED_DONE_ID}").json()
    steps = {s["id"]: s for s in body["workflow"]["ordered_steps"]}
    # Downstream steps reopened (a later step — export — is still satisfied).
    assert body["workflow"]["current_step"] == "complete_metadata"
    assert steps["review_evidence"]["state"] == "reopened"
    assert steps["review_export_readiness"]["state"] == "reopened"
    assert steps["export"]["state"] == "completed"
    # The record is still exported (regression is derived, not a de-export)...
    assert body["exported"] is True
    # ...but the exported artifact is now stale (scientific field changed).
    assert body["artifact"]["state"] == "stale"


def test_reset_restores_artifact_baseline(client):
    r = client.post(
        "/api/demo/reset",
        json={"mode": "execute", "confirmation": "RESET SYNTHETIC DEMO"},
    )
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    # The exported canonical record is current against its own baseline draft.
    done = client.get(f"/api/experiments/{ws.SEED_DONE_ID}").json()
    assert done["artifact"]["state"] == "current"
    # A non-exported canonical draft has no artifact.
    new = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    assert new["artifact"]["state"] == "none"


def test_rev_increments_exactly_once_and_invalidation_rev_matches(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    rev_before = before["rev"]
    im = {"If-Match": f'"{before["version"]}"'}
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=im,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rev"] == rev_before + 1, "a real change bumps rev exactly once"
    assert body["invalidation"]["changed"] is True
    assert body["invalidation"]["rev"] == body["rev"], "invalidation.rev == post-mutation rev"
