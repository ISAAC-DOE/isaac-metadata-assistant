"""P28.3 — revisit / correct an already-answered field (POST /experiments/{id}/edit).

TEST-FIRST (authored RED before the endpoint + `complete.apply_corrections` exist).

The `/answers` mutation only FILLS open `pending[]` blockers, so a value that was
already confirmed (0 pending) cannot be corrected. `/edit` is the version-protected
correct/re-confirm counterpart: it OVERWRITES the current value for the SAME answer
keys `/answers` accepts (asset uri / series / descriptor / edge) and records a FRESH
`user_confirmation` evidence entry. It reuses the P27 machinery verbatim (record_lock,
save_versioned single rev bump + no-op guard, `_check_if_match` If-Match precondition,
P28.2 `build_invalidation`). No guessing: a value only ever comes from the submitted
answer; an unrecognized field writes nothing / is rejected. Truth core untouched; all
fixtures synthetic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import tutorial_client, tutorial_ws

# The raw-scan-set asset that exists in the ready seed's completed draft (0 pending).
RAW_URI = "ssrl-archive://BL15-2/2099_run_000/raw/"
RAW_ASSET_ID = "raw_scan_set"
CURRENT_RAW_SHA = "a3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b123"
# A NEW, well-formed (64 lowercase hex) sentinel — a value the system never invents.
NEW_SHA = "f" * 64

INVALIDATION_KEYS = {"changed", "rev", "changed_fields", "reopened_steps", "artifact", "reason"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _detail(client, exp_id) -> dict:
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _etag(client, exp_id) -> str:
    return client.get(f"/api/experiments/{exp_id}").headers["ETag"]


def _im(client, exp_id) -> dict:
    return {"If-Match": _etag(client, exp_id)}


def _evidence_value(client, exp_id, path) -> object:
    r = client.get(f"/api/experiments/{exp_id}/evidence")
    assert r.status_code == 200, r.text
    for e in r.json()["evidence"]:
        if e["path"] == path:
            return e["value"]
    raise AssertionError(f"no evidence entry for {path}")


def _edit(client, exp_id, answers, *, confirmed=True, headers=None):
    body = {"answers": answers, "confirmed_by_user": confirmed}
    return client.post(f"/api/experiments/{exp_id}/edit", json=body, headers=headers)


# --- happy path: correct an already-answered field ----------------------------


def test_edit_corrects_answered_field_bumps_once_and_reflects_new_value(client):
    d0 = _detail(client, ws.SEED_READY_ID)
    assert d0["pending_count"] == 0 and d0["status"] == "ready_to_export"
    rev0 = d0["rev"]

    r = _edit(client, ws.SEED_READY_ID, {RAW_URI: NEW_SHA}, headers=_im(client, ws.SEED_READY_ID))
    assert r.status_code == 200, r.text
    body = r.json()

    # response carries the /answers-shaped bundle + P28.2 signals
    assert "pending" in body and "status" in body
    assert {"rev", "updated_utc", "version"} <= set(body)
    assert "workflow" in body
    assert set(body["invalidation"]) == INVALIDATION_KEYS
    assert body["invalidation"]["changed"] is True
    assert r.headers["ETag"] == f'"{body["version"]}"'

    # version bumped EXACTLY once (single save_versioned)
    assert body["rev"] == rev0 + 1

    # the correction is now the current value — HTTP round-trip via /evidence
    assert _evidence_value(client, ws.SEED_READY_ID, f"assets:{RAW_ASSET_ID}") == NEW_SHA
    # …and in the persisted draft
    persisted = tutorial_ws().load_experiment(ws.SEED_READY_ID).draft
    raw = next(a for a in persisted["assets"] if a["uri"] == RAW_URI)
    assert raw["sha256"] == NEW_SHA


def test_edit_with_current_value_is_a_byte_stable_no_op(client):
    rev0 = _detail(client, ws.SEED_READY_ID)["rev"]
    r = _edit(
        client, ws.SEED_READY_ID, {RAW_URI: CURRENT_RAW_SHA}, headers=_im(client, ws.SEED_READY_ID)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["invalidation"]["changed"] is False
    assert body["invalidation"]["changed_fields"] == []
    assert body["rev"] == rev0, "an identical re-confirm must not bump rev"


# --- version precondition (SAME order as /answers) ----------------------------


def test_edit_missing_if_match_returns_428(client):
    r = _edit(client, ws.SEED_READY_ID, {RAW_URI: NEW_SHA})
    assert r.status_code == 428, r.text
    # no mutation
    assert tutorial_ws().load_experiment(ws.SEED_READY_ID).draft["assets"]


def test_edit_stale_if_match_returns_412(client):
    im = _im(client, ws.SEED_READY_ID)
    # first edit consumes the token
    assert _edit(client, ws.SEED_READY_ID, {RAW_URI: NEW_SHA}, headers=im).status_code == 200
    # reusing the now-stale token → 412
    r = _edit(client, ws.SEED_READY_ID, {RAW_URI: "e" * 64}, headers=im)
    assert r.status_code == 412, r.text


def test_edit_malformed_if_match_returns_400(client):
    r = _edit(client, ws.SEED_READY_ID, {RAW_URI: NEW_SHA}, headers={"If-Match": "garbage"})
    assert r.status_code == 400, r.text


def test_edit_unconfirmed_returns_422_even_without_if_match(client):
    r = _edit(client, ws.SEED_READY_ID, {RAW_URI: NEW_SHA}, confirmed=False)
    assert r.status_code == 422, r.text


# --- no guessing --------------------------------------------------------------


def test_edit_unknown_field_writes_nothing(client):
    before = tutorial_ws().load_experiment(ws.SEED_READY_ID).draft
    raw_before = next(a for a in before["assets"] if a["uri"] == RAW_URI)["sha256"]
    r = _edit(
        client,
        ws.SEED_READY_ID,
        {"totally_unknown_field": "made up"},
        headers=_im(client, ws.SEED_READY_ID),
    )
    # rejected (unrecognized) — never silently invents a value
    assert r.status_code == 422, r.text
    after = tutorial_ws().load_experiment(ws.SEED_READY_ID).draft
    raw_after = next(a for a in after["assets"] if a["uri"] == RAW_URI)["sha256"]
    assert raw_after == raw_before
    assert "made up" not in str(after)


def test_edit_malformed_sha256_is_refused_and_never_written(client):
    """A DELIBERATE BEHAVIOUR CHANGE, and the old expectation is quoted rather than lost.

    This test was `test_edit_malformed_sha256_is_a_no_op_never_written` and asserted
    ``200`` with ``invalidation.changed is False``. The "never written" half is
    unchanged and still asserted below — nothing about the stored value moved. What
    changed is the STATUS, from an unexplained 200 to a typed 422.

    Why: the test directly above it, `test_edit_unknown_field_writes_nothing`, asserts
    422 for a field this route does not recognise, on the reasoning that answering 200
    to a request that changed nothing is silent. A recognised field carrying a value the
    route cannot store is the same case — and the route's own description now says so.
    Two tests, ten lines apart, under one "no guessing" heading, disagreed about it.

    Measured before the change, on the malformed shas a scientist can actually produce
    (``"Z" * 64``, ``"abc"``, 63 and 65 hex chars, trailing whitespace, uppercase hex):
    ``200``, ``rev`` unmoved, nothing written, and no indication anywhere that the
    correction had not been kept.

    NOT extended to ``POST /answers``, where a malformed sha still leaves the blocker
    open and the response therefore already says the question was not answered. That
    asymmetry is pinned in `test_answers_wrong_type.py`.
    """
    r = _edit(
        client, ws.SEED_READY_ID, {RAW_URI: "not-a-hash"}, headers=_im(client, ws.SEED_READY_ID)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "invalid_field_value"
    assert r.json()["key"] == RAW_URI
    raw = next(a for a in tutorial_ws().load_experiment(ws.SEED_READY_ID).draft["assets"] if a["uri"] == RAW_URI)
    assert raw["sha256"] == CURRENT_RAW_SHA


# --- editing an exported record stales the artifact (P28.2) -------------------


def test_editing_exported_record_stales_the_artifact(client):
    # export the ready seed first
    exp_r = client.post(
        f"/api/experiments/{ws.SEED_READY_ID}/export", headers=_im(client, ws.SEED_READY_ID)
    )
    assert exp_r.status_code == 200, exp_r.text
    assert _detail(client, ws.SEED_READY_ID)["artifact"]["state"] == "current"

    # edit a scientific field (asset sha256 is in the official record)
    r = _edit(client, ws.SEED_READY_ID, {RAW_URI: NEW_SHA}, headers=_im(client, ws.SEED_READY_ID))
    assert r.status_code == 200, r.text
    assert r.json()["invalidation"]["artifact"]["state"] == "stale"
    # …and a fresh GET reflects the stale artifact (records are immutable)
    assert _detail(client, ws.SEED_READY_ID)["artifact"]["state"] == "stale"


# --- fresh user_confirmation evidence for the edited field --------------------


def test_edit_records_a_user_confirmation_evidence_entry(client):
    r = _edit(client, ws.SEED_READY_ID, {RAW_URI: NEW_SHA}, headers=_im(client, ws.SEED_READY_ID))
    assert r.status_code == 200, r.text
    raw = next(a for a in tutorial_ws().load_experiment(ws.SEED_READY_ID).draft["assets"] if a["uri"] == RAW_URI)
    confs = [e for e in raw["evidence"] if e.get("source_type") == "user_confirmation"]
    assert confs, "the correction must record a user_confirmation evidence entry"
    assert any(e.get("answer") == NEW_SHA for e in confs)
