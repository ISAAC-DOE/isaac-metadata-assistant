"""P28.1 — fixed canonical workflow order, backend-derived.

TEST-FIRST acceptance contract (authored BEFORE implementation; RED until
`isaac_api.workflow.derive_workflow` exists and `_detail` surfaces a `workflow`
block). The workflow is ONE permanent ordered sequence, DERIVED from current
record truth — never persisted, never reordered, never recomputed on the client.

Canonical order (fixed, app-native ids):
    load_record → complete_metadata → review_evidence
                → review_export_readiness → export

Each step carries `{id, label, state, current, reopened, blocked, reason}` where
`state ∈ {completed, current, reopened, blocked}` is DERIVED from the current
signals only:

  satisfied(step):
    load_record             = True (a loaded record always exists)
    complete_metadata       = pending_count == 0
    review_evidence         = pending_count == 0 and draft_ok
    review_export_readiness = ready           (official dry-run passes; implies pending==0)
    export                  = exported

  current_step = the FIRST step whose criterion is not satisfied (None if all satisfied).
  For an unsatisfied step:
    reopened = some LATER step IS satisfied  (⇒ the record progressed past this step,
               then upstream data regressed — derivable WITHOUT persisting history)
    current  = it is the first unsatisfied step
    blocked  = unsatisfied, not current, not reopened (a prerequisite is unmet)

No persisted "completed" flag; visiting/reading never mutates state or bumps rev.
Truth core untouched. All fixtures synthetic.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

CANONICAL_ORDER = [
    "load_record",
    "complete_metadata",
    "review_evidence",
    "review_export_readiness",
    "export",
]

CANONICAL_LABELS = {
    "load_record": "Load Record",
    "complete_metadata": "Complete Metadata",
    "review_evidence": "Review Evidence",
    "review_export_readiness": "Review Export Readiness",
    "export": "Export",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _workflow(client, exp_id):
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "workflow" in body, "detail bundle must carry a backend-derived 'workflow' block"
    return body["workflow"]


def _ids(wf):
    return [s["id"] for s in wf["ordered_steps"]]


def _by_id(wf):
    return {s["id"]: s for s in wf["ordered_steps"]}


# --- the pure derivation: exhaustive state coverage ---------------------------


def test_pure_derive_importable_and_shaped():
    from isaac_api.workflow import derive_workflow

    wf = derive_workflow(pending_count=0, draft_ok=True, ready=True, exported=True, rev=7)
    assert _ids(wf) == CANONICAL_ORDER
    assert wf["record_rev"] == 7
    assert wf["current_step"] is None  # all satisfied
    for s in wf["ordered_steps"]:
        assert set(s) == {"id", "label", "state", "current", "reopened", "blocked", "reason"}
        assert s["label"] == CANONICAL_LABELS[s["id"]]  # Title Case, canonical


def test_fresh_draft_current_is_complete_metadata():
    from isaac_api.workflow import derive_workflow

    wf = derive_workflow(pending_count=5, draft_ok=False, ready=False, exported=False, rev=0)
    steps = _by_id(wf)
    assert wf["current_step"] == "complete_metadata"
    assert steps["load_record"]["state"] == "completed"
    assert steps["complete_metadata"]["state"] == "current"
    assert steps["complete_metadata"]["current"] is True
    # downstream never-completed steps are BLOCKED, not "reopened", not "current"
    for later in ("review_evidence", "review_export_readiness", "export"):
        assert steps[later]["state"] == "blocked", later
        assert steps[later]["blocked"] is True
        assert steps[later]["reopened"] is False
        assert steps[later]["current"] is False


def test_ready_record_current_is_export():
    from isaac_api.workflow import derive_workflow

    wf = derive_workflow(pending_count=0, draft_ok=True, ready=True, exported=False, rev=3)
    steps = _by_id(wf)
    assert wf["current_step"] == "export"
    for done in ("load_record", "complete_metadata", "review_evidence", "review_export_readiness"):
        assert steps[done]["state"] == "completed", done
    assert steps["export"]["state"] == "current"


def test_exported_record_all_completed_no_current():
    from isaac_api.workflow import derive_workflow

    wf = derive_workflow(pending_count=0, draft_ok=True, ready=True, exported=True, rev=9)
    assert wf["current_step"] is None
    for s in wf["ordered_steps"]:
        assert s["state"] == "completed"
        assert s["current"] is False and s["reopened"] is False and s["blocked"] is False


def test_reopened_is_derived_not_persisted():
    """Regression: exported (a LATER step satisfied) but metadata incomplete again.
    complete_metadata is the first-unsatisfied → current, and flagged reopened
    because a later step (export) is satisfied. review_evidence/readiness are
    reopened (not blocked) for the same reason. Derived purely from signals."""
    from isaac_api.workflow import derive_workflow

    wf = derive_workflow(pending_count=2, draft_ok=False, ready=False, exported=True, rev=12)
    steps = _by_id(wf)
    assert wf["current_step"] == "complete_metadata"
    assert steps["complete_metadata"]["current"] is True
    assert steps["complete_metadata"]["reopened"] is True  # later step (export) satisfied
    for mid in ("review_evidence", "review_export_readiness"):
        assert steps[mid]["state"] == "reopened", mid
        assert steps[mid]["reopened"] is True
        assert steps[mid]["blocked"] is False
    assert steps["export"]["state"] == "completed"
    # a reopened step must be distinguishable from a never-completed (blocked) one
    assert steps["review_evidence"]["state"] != "blocked"


def test_blocked_reason_names_the_current_step():
    from isaac_api.workflow import derive_workflow

    wf = derive_workflow(pending_count=3, draft_ok=False, ready=False, exported=False, rev=0)
    steps = _by_id(wf)
    assert steps["export"]["blocked"] is True
    assert steps["export"]["reason"], "a blocked step must carry a human reason"
    assert "Complete Metadata" in steps["export"]["reason"]


# --- HTTP integration: order fixed across records, derived, non-mutating -------


def test_workflow_present_and_fixed_order_across_all_seeds(client):
    seeds = [
        ws.SEED_NEW_DRAFT_ID,
        ws.SEED_PARTIAL_ID,
        ws.SEED_READY_ID,
        ws.SEED_REVIEW_ID,
        ws.SEED_DONE_ID,
    ]
    for sid in seeds:
        wf = _workflow(client, sid)
        assert _ids(wf) == CANONICAL_ORDER, f"{sid}: order must never reorder"


def test_seed_states_match_derived_status(client):
    # needs_attention seed → complete_metadata current
    wf = _workflow(client, ws.SEED_NEW_DRAFT_ID)
    assert _by_id(wf)["complete_metadata"]["current"] is True
    # ready seed → export current, everything before completed
    wf = _workflow(client, ws.SEED_READY_ID)
    assert wf["current_step"] == "export"
    # done seed → all completed
    wf = _workflow(client, ws.SEED_DONE_ID)
    assert wf["current_step"] is None


def test_reading_workflow_is_idempotent_and_does_not_bump_rev(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    wf1 = before["workflow"]
    after = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    wf2 = after["workflow"]
    assert wf1 == wf2, "visiting/reading a workflow must not change it"
    assert before["version"] == after["version"], "a read must not bump the version"


def test_workflow_is_not_persisted_in_state(client):
    """No hidden second workflow store: the persisted experiment state carries no
    step/completion field — the workflow is derived on read only."""
    client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}")  # force a read
    exp = ws.load_experiment(ws.SEED_NEW_DRAFT_ID)
    state = exp.to_state()
    for forbidden in ("workflow", "ordered_steps", "steps", "current_step", "completed_steps"):
        assert forbidden not in state, f"{forbidden!r} must not be persisted (completion is derived)"


def test_reopened_exported_record_is_route_reachable(client):
    """The REAL production reopened case: an ALREADY-EXPORTED record edited back to
    pending>0. `ready` must reflect the CURRENT draft (NOT export-ready), so the
    readiness step reopens rather than showing green above reopened metadata.

    Regression guard for the dishonest `status() in (READY_TO_EXPORT, DONE)` signal
    (status() returns DONE for any exported record regardless of pending_count).
    Built deterministically from seeds; the tmp workspace fixture keeps it hermetic.
    """
    # Borrow a real, serialize-accepted pending entry from the fresh-draft seed.
    fresh = ws.load_experiment(ws.SEED_NEW_DRAFT_ID)
    borrowed_pending = copy.deepcopy(fresh.pending()[0])

    # Reintroduce a pending blocker on the EXPORTED seed while it stays exported.
    exp = ws.load_experiment(ws.SEED_DONE_ID)
    assert exp.exported() and exp.record_id is not None  # precondition: exported
    exp.draft.setdefault("pending", []).append(borrowed_pending)
    assert exp.pending_count() > 0
    exp.save()

    body = client.get(f"/api/experiments/{ws.SEED_DONE_ID}").json()
    steps = _by_id(body["workflow"])

    assert body["workflow"]["current_step"] == "complete_metadata"
    assert steps["complete_metadata"]["current"] is True
    # readiness/evidence reopened (a later step — export — is satisfied), NOT green.
    assert steps["review_evidence"]["state"] == "reopened"
    assert steps["review_export_readiness"]["state"] == "reopened"
    assert steps["export"]["state"] == "completed"
    # the record is still exported — the regression is derived, not a de-export.
    assert body["exported"] is True
    assert body["record_id"] is not None
