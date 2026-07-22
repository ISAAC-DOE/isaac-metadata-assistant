"""P27.2 — per-record version model + atomic, crash-safe workspace writes.

TEST-FIRST acceptance contract (authored before implementation; RED until the
``rev``/``updated_utc`` model, ``atomic_write_text`` helper, and
``Experiment.save_versioned`` land). This slice is the MODEL + persistence layer
only — there is deliberately NO HTTP/If-Match contract yet (that is P27.3).

Invariants driven here:

  * every experiment carries a monotonic integer ``rev`` and an ``updated_utc``,
  * ``rev`` starts at 0 on create and on the canonical seed,
  * a legacy state file lacking the fields loads safely (rev 0, updated_utc ==
    created_utc) WITHOUT being rewritten on load,
  * a mutation that changes the AUTHORITATIVE scientific state bumps ``rev`` and
    advances ``updated_utc``,
  * an identical (no-op) re-entry does NOT bump ``rev`` and does NOT rewrite the
    file (byte-stable),
  * all workspace writes are atomic (``os.replace``) so a crashed write leaves the
    previous file intact and a concurrent reader never sees a partial file,
  * the export path bumps ``rev`` and persists atomically.

Answer-log vs rev decision (documented): ``answer_log`` is EXCLUDED from the rev
signature. An answer submission is persisted (with its log entry) ONLY when it
changes the authoritative draft; an identical re-entry is neither logged nor
rewritten and does not bump ``rev``.

All fixtures are synthetic. The truth core is never bypassed.
"""

from __future__ import annotations

import copy
import json
import os

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws


@pytest.fixture()
def tmp_ws(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return ws


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _fresh_draft():
    return ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH)


def _if_match(client, exp_id):
    """The current authoritative ETag as an If-Match header (strict preconditions)."""
    v = client.get(f"/api/experiments/{exp_id}").json()["version"]
    return {"If-Match": f'"{v}"'}


# --- 1. new experiment starts at rev 0 with updated_utc set -------------------


def test_new_experiment_starts_at_rev_zero(tmp_ws):
    exp = tmp_ws.create_experiment(
        title="X", source={"description": "d", "files": []}, draft=_fresh_draft()
    )
    assert exp.rev == 0
    assert exp.updated_utc  # non-empty
    assert exp.updated_utc == exp.created_utc
    # persisted shape carries both fields
    state = json.loads(exp.state_path.read_text(encoding="utf-8"))
    assert state["rev"] == 0
    assert state["updated_utc"] == exp.created_utc


# --- 2. legacy load: defaults + NOT rewritten on read -------------------------


def test_legacy_state_loads_with_defaults_and_is_not_rewritten(tmp_ws):
    exp_dir = tmp_ws.workspace_root() / "01LEGACYEXPERIMENT00000001"
    exp_dir.mkdir(parents=True)
    state_path = exp_dir / "experiment.json"
    legacy = {
        "id": "01LEGACYEXPERIMENT00000001",
        "title": "legacy",
        "created_utc": "2020-01-01T00:00:00Z",
        "source": {"description": "d", "files": []},
        "draft": _fresh_draft(),
        "answer_log": [],
        "record_id": None,
        # NOTE: no "rev", no "updated_utc" — a pre-P27.2 file.
    }
    raw = json.dumps(legacy, indent=2) + "\n"
    state_path.write_text(raw, encoding="utf-8")
    bytes_before = state_path.read_bytes()

    exp = tmp_ws.load_experiment("01LEGACYEXPERIMENT00000001")
    assert exp is not None
    assert exp.rev == 0
    assert exp.updated_utc == "2020-01-01T00:00:00Z"  # defaulted to created_utc
    # the file must NOT be rewritten merely because it was loaded
    assert state_path.read_bytes() == bytes_before


# --- 3. authoritative mutation bumps rev + advances updated_utc ---------------


def test_draft_change_bumps_rev_and_advances_updated_utc(tmp_ws, monkeypatch):
    stamps = iter(["2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z", "2026-01-01T00:00:03Z"])
    monkeypatch.setattr(ws, "_now_iso", lambda: next(stamps))

    exp = tmp_ws.create_experiment(
        title="X", source={"description": "d", "files": []}, draft=_fresh_draft()
    )
    assert exp.rev == 0
    before_updated = exp.updated_utc

    exp.draft = ws.apply_answers(exp.draft, copy.deepcopy(tmp_ws.load_demo_answers()))
    changed = exp.save_versioned()
    assert changed is True
    assert exp.rev == 1
    assert exp.updated_utc != before_updated

    reloaded = tmp_ws.load_experiment(exp.id)
    assert reloaded.rev == 1
    assert reloaded.updated_utc == exp.updated_utc


# --- 4. no-op mutation: no bump, byte-stable ----------------------------------


def test_noop_mutation_does_not_bump_or_rewrite(tmp_ws):
    exp = tmp_ws.create_experiment(
        title="X", source={"description": "d", "files": []}, draft=_fresh_draft()
    )
    # one real change to reach rev 1
    exp.draft = ws.apply_answers(exp.draft, copy.deepcopy(tmp_ws.load_demo_answers()))
    assert exp.save_versioned() is True
    assert exp.rev == 1

    bytes_after_change = exp.state_path.read_bytes()
    mtime_after_change = exp.state_path.stat().st_mtime_ns

    # re-apply the SAME authoritative state — nothing scientific changed
    changed = exp.save_versioned()
    assert changed is False
    assert exp.rev == 1  # unchanged
    # the file was not rewritten at all (byte-stable AND mtime unchanged)
    assert exp.state_path.read_bytes() == bytes_after_change
    assert exp.state_path.stat().st_mtime_ns == mtime_after_change


# --- 5. restart persistence: rev round-trips ----------------------------------


def test_rev_persists_across_reload(tmp_ws):
    exp = tmp_ws.create_experiment(
        title="X", source={"description": "d", "files": []}, draft=_fresh_draft()
    )
    for _ in range(3):
        exp.title = exp.title + "!"  # authoritative change each time
        exp.save_versioned()
    assert exp.rev == 3
    reloaded = tmp_ws.load_experiment(exp.id)
    assert reloaded.rev == 3


# --- 6. atomic write: a failure leaves the ORIGINAL file intact ---------------


def test_atomic_write_failure_leaves_original_intact(tmp_ws, monkeypatch):
    exp = tmp_ws.create_experiment(
        title="original", source={"description": "d", "files": []}, draft=_fresh_draft()
    )
    good_bytes = exp.state_path.read_bytes()
    good_state = json.loads(good_bytes)

    # simulate a crash at the final atomic swap
    def boom(src, dst):
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(ws.os, "replace", boom)

    exp.title = "corrupted-attempt"
    with pytest.raises(OSError):
        exp.save()

    # the original file survives untouched and is still valid JSON
    assert exp.state_path.read_bytes() == good_bytes
    assert json.loads(exp.state_path.read_text(encoding="utf-8")) == good_state
    # no orphaned temp files left behind in the experiment dir
    leftovers = [p.name for p in exp.dir.iterdir() if p.name != "experiment.json"]
    assert leftovers == []


# --- 7. concurrent-reader safety: os.replace is the swap mechanism ------------


def test_write_uses_os_replace_no_partial_target(tmp_ws, monkeypatch):
    exp = tmp_ws.create_experiment(
        title="X", source={"description": "d", "files": []}, draft=_fresh_draft()
    )

    calls = {"replace": 0}
    real_replace = os.replace

    def spy_replace(src, dst):
        # at the moment of swap the target already exists (old file) and src is a
        # DISTINCT temp path — i.e. the target is never truncated in place, so a
        # concurrent reader always sees a complete old-or-new file.
        assert str(src) != str(dst)
        calls["replace"] += 1
        return real_replace(src, dst)

    monkeypatch.setattr(ws.os, "replace", spy_replace)

    exp.title = "changed"
    exp.save_versioned()
    assert calls["replace"] >= 1


def test_atomic_helper_is_exposed(tmp_ws):
    # the shared helper exists and performs an atomic create
    target = tmp_ws.workspace_root() / "atomic-probe.txt"
    ws.atomic_write_text(target, "hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"


# --- 8. reset / reseed → canonical records at rev 0 ---------------------------


def test_canonical_seed_records_start_at_rev_zero(tmp_ws):
    tmp_ws.ensure_seeded()
    for exp in tmp_ws.list_experiments():
        if exp.id in tmp_ws.CANONICAL_IDS:
            assert exp.rev == 0, exp.id
            assert exp.updated_utc == exp.created_utc, exp.id


def test_reset_yields_canonical_rev_zero(tmp_ws):
    tmp_ws.ensure_seeded()
    tmp_ws.reset_to_canonical_seed(dry_run=False)
    for exp in tmp_ws.list_experiments():
        assert exp.rev == 0, exp.id


# --- 9. export path bumps rev and persists atomically -------------------------


def test_export_bumps_rev_and_persists(client):
    # the READY seed has 0 pending and passes the dry-run export
    r = client.post(
        f"/api/experiments/{ws.SEED_READY_ID}/export",
        headers=_if_match(client, ws.SEED_READY_ID),
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True

    reloaded = ws.load_experiment(ws.SEED_READY_ID)
    assert reloaded.exported() is True
    assert reloaded.rev >= 1  # bumped from the canonical rev 0 by the export
    assert reloaded.updated_utc  # set


# --- 10. HTTP answers: authoritative change bumps; no-op re-entry does not -----


def test_http_answers_noop_reentry_does_not_bump_rev(client):
    # apply the committed demo answers to the raw NEW-DRAFT seed (changes the draft)
    answers = ws.load_demo_answers()
    payload = {"confirmed_by_user": True, "answers": {}}
    # translate the demo answers into the UI answer-by-id shape the endpoint expects
    payload["answers"]["series"] = answers.get("series")
    payload["answers"]["descriptor"] = answers.get("descriptor")

    first = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=payload,
        headers=_if_match(client, ws.SEED_NEW_DRAFT_ID),
    )
    assert first.status_code == 200
    rev_after_first = ws.load_experiment(ws.SEED_NEW_DRAFT_ID).rev
    assert rev_after_first >= 1

    # re-submit the IDENTICAL answers — authoritative draft does not change.
    # Fetch a FRESH ETag: the first submission bumped rev, so the prior token is stale.
    second = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=payload,
        headers=_if_match(client, ws.SEED_NEW_DRAFT_ID),
    )
    assert second.status_code == 200
    rev_after_second = ws.load_experiment(ws.SEED_NEW_DRAFT_ID).rev
    assert rev_after_second == rev_after_first  # no bump on identical re-entry


# --- 11. stale in-memory instance must not regress the on-disk rev (P27.2 hardening)


def test_save_versioned_does_not_regress_ondisk_rev(tmp_ws, monkeypatch):
    monkeypatch.setattr(ws, "_now_iso", lambda: "2026-01-01T00:00:09Z")
    exp = tmp_ws.create_experiment(
        title="X", source={"description": "d", "files": []}, draft=_fresh_draft()
    )
    # simulate other writers having advanced the ON-DISK rev to 5
    exp.rev = 5
    exp.save()
    assert json.loads(exp.state_path.read_text(encoding="utf-8"))["rev"] == 5

    # a STALE in-memory instance (rev 0) makes a real authoritative change
    stale = tmp_ws.load_experiment(exp.id)
    stale.rev = 0
    stale.title = "X-changed"  # authoritative field -> signature changes
    assert stale.save_versioned() is True

    # the bump comes from max(in-memory, on-disk) + 1 -> 6, never regressing to 1
    on_disk = json.loads(stale.state_path.read_text(encoding="utf-8"))["rev"]
    assert on_disk == 6
    assert stale.rev == 6
