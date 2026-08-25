"""P4 — export crash-recovery: the orphan-artifact wedge and the raising GET.

Two reproduced defects, both on the export path, both fixed here.

DEFECT 1 — the export crash-wedge (Critical)
--------------------------------------------
``post_export`` writes in the order artifact -> sidecar -> state
(``routes._write_record`` then ``Experiment.save_versioned``), all inside
``ws.record_lock(experiment_id)``. So this is a *single-writer crash-consistency*
defect, not a race: a fault anywhere between the artifact write and the state save
leaves the artifact(s) on disk while ``experiment.json`` still says
``record_id: null``.

The immutability guard then tested a FILE (``if record_path.exists()``) while the
endpoint's own documented 409 makes a STATE claim ("This record has already been
exported"). With state and disk disagreeing, the file is not a valid proxy for that
claim, and EVERY clean retry returned ``409 record_exists`` forever. All the wedge
state is on disk, so a restart did not clear it, and there is no per-record
delete/repair route — the only recovery was the destructive whole-workspace
``POST /api/demo/reset``.

The fix makes the guard state-aware AND pair-aware
(``exp.exported() and record_path.exists() and sidecar_path.exists()``) and logs a
path-free reconciliation warning when it heals an orphan.

The SIDECAR conjunction was added by the independent review of this slice, which
found the symmetric wedge: with a record-only file test, ``exported + record present
+ sidecar absent`` hit the immutability 409 permanently and the sidecar could never be
regenerated — and that state is reachable *from the very self-heal this slice blesses*
(fault the sidecar write during the row-3 repair). Rows 3b and 3c below pin both
halves. An export produces a PAIR; "the artifact is present" means both files, which
is the same rule ``get_artifacts`` already applies when it forces ``stale`` whenever
EITHER file fails to read.

DEFECT 2 — a read operation could raise (Important)
---------------------------------------------------
``get_artifacts`` gated on ``exp.exported()`` and then read BOTH files unguarded.
When state said exported but a file was absent, it raised ``FileNotFoundError`` —
an unhandled exception on a GET, whose message carries the ABSOLUTE server path into
the server log (the response body is the framework's bare ``Internal Server Error``,
so nothing leaks to the client). A missing artifact is now a typed, path-free absence.

The review found that ``get_artifacts`` was only ONE of five readers: ``post_validate``,
``_warnings_payload``, ``get_evidence`` and ``_assistant_validate_dryrun`` still raised
in the same state, and ``api.ts`` fetches them in the SAME ``Promise.all`` as
``/artifacts`` — so a sibling's raise took down the whole bundle no matter how well
``/artifacts`` degraded. All five now share ``routes._read_artifact_json`` and each
degrades according to its own contract (section 12). ``post_audit`` needed no change
and section 12 proves why.

FAULT INJECTION — test-only, no production seam
-----------------------------------------------
An import asymmetry makes this injectable with zero production change:

* ``routes.py`` does ``from .workspace import ... atomic_write_text``, so
  ``_write_record`` resolves ``routes.atomic_write_text``.
* ``workspace.Experiment.save`` resolves the module global
  ``workspace.atomic_write_text`` at call time.

Therefore ``monkeypatch.setattr(ws, "atomic_write_text", ...)`` fails ONLY the
state save (both artifact writes go through) -> the wedge exactly; and
``monkeypatch.setattr(routes, "atomic_write_text", ...)`` predicated on
``.evidence.json`` fails ONLY the sidecar -> the other half of the window, a
half-written pair. Both halves are covered because they leave different disk
states. Each patch is predicated on the exact target path so nothing else in the
process is perturbed, and each is applied through its OWN
``pytest.MonkeyPatch.context()`` so it reverts at the end of the ``with`` block and
no instrumentation survives.

That per-fault context is deliberate, not stylistic. Reverting a fault with the
test-scoped ``monkeypatch`` fixture's ``.undo()`` would also undo the ``client``
fixture's ``ISAAC_UI_WORKSPACE`` setenv and this package's autouse
snapshot-neutralizer, silently redirecting every later call to the shared default
workspace root — which made an early draft of this file report a *changed
generation* after a fault that had in fact changed nothing on disk. Do not
"simplify" these back to a shared ``monkeypatch.undo()``.

Truth core (``src/isaac_records/``) untouched; exported record CONTENT unchanged.
All fixtures are the committed synthetic seeds.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import pathlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import isaac_api.assistant_paths as ap
import isaac_api.dependencies as dependencies
import isaac_api.routes as routes
import isaac_api.workspace as ws
import isaac_records.export as core_export

from conftest import tutorial_client, tutorial_ws

# Absolute/server/mount markers that must never reach a client (P30.6), kept in
# step with test_artifact_path_safety.UNSAFE_PATH_MARKERS.
UNSAFE_PATH_MARKERS = (
    "/data/",
    "/Users/",
    "/var/",
    "/tmp/",
    "/app/",
    "/private/",
    "isaac-workspace",
    "\\",
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# --- helpers ------------------------------------------------------------------


def _etag(client, exp_id: str) -> str:
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.headers["ETag"]


def _detail(client, exp_id: str) -> dict:
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _export(client, exp_id: str):
    """POST /export with the CURRENT ETag — i.e. a *clean retry*, never a stale one."""
    return client.post(
        f"/api/experiments/{exp_id}/export", headers={"If-Match": _etag(client, exp_id)}
    )


def _paths(exp_id: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """(record, sidecar, state) paths for an id, derived exactly as the app does."""
    exp = tutorial_ws().load_experiment(exp_id)
    records_dir = exp.records_dir
    return (
        records_dir / f"{exp_id}.json",
        records_dir / f"{exp_id}.evidence.json",
        exp.state_path,
    )


@contextlib.contextmanager
def _fail_state_save(exp_id: str):
    """Fault ONLY the state save: artifact + sidecar are written, experiment.json is not.

    Patches ``workspace.atomic_write_text`` (which ``Experiment.save`` resolves at
    call time) and fires only for this experiment's own ``experiment.json`` — every
    other write in the process, including both artifact writes, goes through.
    Yields a counter so the caller can assert the fault actually fired.
    """
    _, _, state_path = _paths(exp_id)
    real = ws.atomic_write_text
    calls = {"faulted": 0}

    def _maybe_fail(path, text):
        if pathlib.Path(path) == state_path:
            calls["faulted"] += 1
            raise OSError("simulated fault between the artifact write and the state save")
        return real(path, text)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ws, "atomic_write_text", _maybe_fail)
        yield calls


@contextlib.contextmanager
def _fail_sidecar_write(exp_id: str):
    """Fault ONLY the sidecar write: the record is written, the sidecar and the state are not.

    Patches ``routes.atomic_write_text`` (the name ``_write_record`` resolves) and
    fires only for this experiment's own ``*.evidence.json``.
    """
    _, sidecar_path, _ = _paths(exp_id)
    real = routes.atomic_write_text
    calls = {"faulted": 0}

    def _maybe_fail(path, text):
        if pathlib.Path(path) == sidecar_path:
            calls["faulted"] += 1
            raise OSError("simulated fault between the record write and the sidecar write")
        return real(path, text)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(routes, "atomic_write_text", _maybe_fail)
        yield calls


@contextlib.contextmanager
def _advancing_clock(start_epoch: int = 4102444800):
    """Make every ``isaac_records.export._now_iso()`` call advance by ONE second.

    Deterministically forces the second-boundary straddle that made the shipped
    content test flaky, instead of hoping real wall-clock time supplies it. Patches
    the core module's own global (which ``build_sidecar``/``transform`` resolve at
    call time) inside its own ``pytest.MonkeyPatch.context()`` — see this module's
    docstring for why each fault gets its own context. Nothing under ``src/`` is
    written; the clock is restored at the end of the ``with`` block. Yields a call
    counter so a caller can assert the injection actually fired.
    """
    box = {"calls": 0}

    def _tick() -> str:
        stamp = datetime.fromtimestamp(start_epoch + box["calls"], tz=timezone.utc)
        box["calls"] += 1
        return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(core_export, "_now_iso", _tick)
        yield box


def _wedge(client, exp_id: str) -> dict:
    """Drive one export to the state-save fault; return the pre-fault detail.

    Leaves the canonical wedge on disk: both artifacts present, state not-exported.
    """
    before = _detail(client, exp_id)
    with _fail_state_save(exp_id) as calls:
        with pytest.raises(OSError):
            _export(client, exp_id)
    assert calls["faulted"] == 1, "the injected state-save fault never fired"
    record, sidecar, _ = _paths(exp_id)
    assert record.exists() and sidecar.exists(), "the wedge requires orphan artifacts on disk"
    assert tutorial_ws().load_experiment(exp_id).exported() is False, (
        "the wedge requires the persisted state to still say NOT exported"
    )
    return before


# --- 1. the wedge is healed ----------------------------------------------------


def test_wedge_orphan_artifact_does_not_block_a_clean_retry(client):
    """THE defect. Not-exported + orphan artifact present -> the retry PROCEEDS.

    Before the fix every clean retry returned ``409 record_exists`` forever, and the
    only recovery was the destructive whole-workspace reset. (NC1 reverts the guard
    to the file-only predicate and this test must go red.)
    """
    target = ws.SEED_READY_ID
    before = _wedge(client, target)
    # The UI's own signal proves the user was still being told to export.
    assert before["artifact"]["state"] == "none"
    assert _detail(client, target)["artifact"]["state"] == "none"

    r = _export(client, target)
    assert r.status_code == 200, f"the wedge is not healed: {r.status_code} {r.text}"
    body = r.json()
    assert body["ok"] is True, body
    assert body["record_id"] == target
    # rev bumped: record_id null -> id IS an authoritative state change.
    assert body["rev"] > before["rev"], (
        f"the healing export must bump rev (was {before['rev']}, now {body['rev']})"
    )
    assert tutorial_ws().load_experiment(target).exported() is True
    assert _detail(client, target)["artifact"]["state"] == "current"


def test_healed_artifact_is_republished_from_the_current_draft(client):
    """The orphan is REPLACED, not adopted: the healed artifact is a fresh
    projection of the CURRENT draft, so an orphan written from an older draft (or
    corrupted in place) can never survive as the record's official content."""
    target = ws.SEED_READY_ID
    _wedge(client, target)
    record_path, sidecar_path, _ = _paths(target)
    # Stamp the orphan so adopting it instead of republishing would be visible.
    record_path.write_text('{"sentinel": "stale-orphan"}\n', encoding="utf-8")
    sidecar_path.write_text('{"sentinel": "stale-orphan"}\n', encoding="utf-8")

    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    ondisk = json.loads(record_path.read_text(encoding="utf-8"))
    assert "sentinel" not in ondisk, "the stale orphan was adopted instead of republished"
    assert ondisk["record_id"] == target
    ondisk_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert "sentinel" not in ondisk_sidecar, "the stale sidecar was adopted, not republished"
    # And the served artifacts agree with the freshly written files.
    served = client.get(f"/api/experiments/{target}/artifacts").json()
    assert served["record"] == ondisk and served["sidecar"] == ondisk_sidecar


# --- 2. the four-row truth table ----------------------------------------------


def test_truthtable_row1_not_exported_with_orphan_proceeds(client):
    """Row 1 (the wedge): not exported + artifact present -> PROCEEDS, rev bumps."""
    target = ws.SEED_READY_ID
    before = _wedge(client, target)
    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert r.json()["rev"] > before["rev"]


def test_truthtable_row2_exported_with_both_artifacts_present_is_still_409(client):
    """Row 2 (genuine conflict): exported + BOTH artifacts present -> 409, NOT swallowed.

    Records are immutable. Neither the recovery fix nor the sidecar clause added by
    the P4 review may weaken this. (NC2 removes the 409 entirely and this test must go
    red.) "BOTH present" is now asserted explicitly, because the guard's file test is
    a conjunction over the pair — a row-2 fixture with only one artifact would be
    row 3/3b, not a genuine conflict.
    """
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    assert tutorial_ws().load_experiment(target).exported() is True
    assert record_path.exists(), "row 2 requires the record artifact on disk"
    assert sidecar_path.exists(), "row 2 requires the SIDECAR on disk too"
    r = _export(client, target)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "record_exists"
    assert r.json()["record_id"] == target
    # Refused means refused: neither artifact was touched and rev did not move.
    assert record_path.exists() and sidecar_path.exists()


def test_truthtable_row3_exported_without_artifact_self_heals_without_bumping_rev(client):
    """Row 3 (mirror case): exported + artifact absent -> 200 self-heal, rev UNCHANGED.

    The unchanged rev is DELIBERATE, not incidental. ``save_versioned`` compares the
    authoritative signature (title/source/draft/record_id); on this path
    ``record_id`` is ALREADY set, so the signature does not change, it returns
    ``False``, and the file is not rewritten. Republishing a missing artifact is a
    filesystem repair, not a scientific state change, so it must not invalidate
    every client's held validator. (NC3 drops the file check from the guard and this
    test must go red with a 409.)
    """
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    before = _detail(client, target)
    record_path.unlink()
    sidecar_path.unlink()

    r = _export(client, target)
    assert r.status_code == 200, f"the mirror case must self-heal, got {r.status_code}"
    assert r.json()["ok"] is True, r.text
    assert record_path.exists() and sidecar_path.exists(), "the artifacts were not restored"
    after = _detail(client, target)
    assert after["rev"] == before["rev"], (
        "a filesystem-only repair must not bump rev — save_versioned returns False "
        f"when the authoritative signature is unchanged (was {before['rev']}, now {after['rev']})"
    )
    assert after["version"] == before["version"], "the version must be unchanged too"
    assert _etag(client, target) == f'"{before["version"]}"'
    # Prove the no-bump comes from save_versioned's signature comparison, directly.
    exp = tutorial_ws().load_experiment(target)
    assert exp.save_versioned() is False


def test_truthtable_row3b_exported_with_only_the_sidecar_missing_self_heals(client):
    """Row 3b — THE SYMMETRIC WEDGE the P4 review found. Exported + record present +
    sidecar ABSENT -> 200 self-heal that REGENERATES the sidecar.

    The original guard's file test covered the RECORD only, so this state hit the
    immutability 409 and stayed there: measured ``export: 409 record_exists ; retry:
    409 ; sidecar back? False``. That is a permanent wedge whose sidecar can never be
    regenerated — the exact defect class this file exists to remove, one file over —
    with ``/artifacts`` truthfully reporting ``stale`` forever and no repair route.

    (Reverting the guard's ``and sidecar_path.exists()`` conjunction makes this test
    go red with a 409.)
    """
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    before = _detail(client, target)
    record_bytes_before = record_path.read_bytes()
    sidecar_path.unlink()
    assert record_path.exists() and not sidecar_path.exists()
    assert tutorial_ws().load_experiment(target).exported() is True
    # The UI already told the truth about this state; only the repair was missing.
    assert client.get(f"/api/experiments/{target}/artifacts").json()["artifact"]["state"] == "stale"

    r = _export(client, target)
    assert r.status_code == 200, f"the sidecar-only wedge is not healed: {r.status_code} {r.text}"
    assert r.json()["ok"] is True, r.text
    assert sidecar_path.exists(), "the sidecar was not regenerated"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["record_id"] == target, "the regenerated sidecar must describe THIS record"
    assert sidecar["evidence"], "a regenerated sidecar with no evidence would be a stub"
    # Same class as row 3: a filesystem repair, so rev/version/ETag do not move.
    after = _detail(client, target)
    assert after["rev"] == before["rev"] and after["version"] == before["version"]
    assert _etag(client, target) == f'"{before["version"]}"'
    # And the record itself is republished from the current draft, byte-identical here
    # because the draft has not changed.
    assert record_path.read_bytes() == record_bytes_before
    assert _detail(client, target)["artifact"]["state"] == "current"


def test_truthtable_row3c_exported_with_only_the_record_missing_self_heals(client):
    """Row 3c: exported + record ABSENT + sidecar present -> 200 self-heal.

    This already worked before the P4 review (the guard's record-file test was already
    false here), and is pinned so the sidecar clause added for row 3b cannot break the
    mirror-image case by turning the conjunction into the wrong polarity.
    """
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    before = _detail(client, target)
    record_path.unlink()
    assert not record_path.exists() and sidecar_path.exists()

    r = _export(client, target)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True, r.text
    assert record_path.exists(), "the record artifact was not restored"
    assert json.loads(record_path.read_text(encoding="utf-8"))["record_id"] == target
    after = _detail(client, target)
    assert after["rev"] == before["rev"], "a filesystem-only repair must not bump rev"


def test_a_sidecar_fault_during_the_mirror_self_heal_is_recoverable(client):
    """The wedge row 3b was REACHABLE FROM: fault the sidecar write during the row-3
    self-heal this slice blesses.

    Measured before the fix: ``record True / sidecar False / exported True`` and then
    ``clean retry -> 409 record_exists | STUCK``. So the blessed repair path could
    itself manufacture a permanent 409 wedge. A clean retry must now finish the repair.
    """
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    before = _detail(client, target)
    record_path.unlink()
    sidecar_path.unlink()

    with _fail_sidecar_write(target) as calls:
        with pytest.raises(OSError):
            _export(client, target)
    assert calls["faulted"] == 1, "the injected sidecar fault never fired"
    # Exactly the half-repaired state the review measured.
    assert record_path.exists() and not sidecar_path.exists()
    assert tutorial_ws().load_experiment(target).exported() is True

    r = _export(client, target)
    assert r.status_code == 200, f"the half-repaired state is STUCK: {r.status_code} {r.text}"
    assert r.json()["ok"] is True, r.text
    assert record_path.exists() and sidecar_path.exists(), "the pair is still incomplete"
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["record_id"] == target
    assert _detail(client, target)["rev"] == before["rev"], "still a filesystem-only repair"
    assert _detail(client, target)["artifact"]["state"] == "current"


def test_truthtable_row4_not_exported_without_artifact_exports_normally(client):
    """Row 4 (normal): not exported + no artifact -> ordinary export.

    HONEST LIMIT — this is a BASELINE GUARD, not coverage of anything this slice
    changed. Every negative control leaves it green, and it cannot fail under any of
    them, because the normal path never reaches the guard's file test at all
    (``record_path.exists()`` is false, whatever the guard does with it). Its value is
    that a future "fix" to the recovery path which broke ORDINARY export would be
    caught here — not that it demonstrates the fix works. Rows 1, 2, 3, 3b and 3c are
    the coverage.
    """
    target = ws.SEED_READY_ID
    record_path, sidecar_path, _ = _paths(target)
    assert not record_path.exists() and not sidecar_path.exists()
    before = _detail(client, target)
    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert r.json()["rev"] > before["rev"]
    assert record_path.exists() and sidecar_path.exists()


# --- 3. precondition ordering is preserved ------------------------------------


def test_precondition_still_precedes_the_409(client):
    """428/412/400 from ``_check_if_match`` are still evaluated BEFORE the 409.

    Pinned here as well as in ``test_strict_precondition.py`` /
    ``test_version_contract.py`` because the guard this slice edits sits directly
    after the precondition check — a reordering would be invisible to the recovery
    tests above.
    """
    done = ws.SEED_DONE_ID
    assert client.post(f"/api/experiments/{done}/export").status_code == 428
    r = client.post(
        f"/api/experiments/{done}/export", headers={"If-Match": '"definitely-stale.0"'}
    )
    assert r.status_code == 412 and r.json()["error"] == "stale_write"
    r = client.post(f"/api/experiments/{done}/export", headers={"If-Match": "not-a-validator"})
    assert r.status_code == 400 and r.json()["error"] == "malformed_if_match"


def test_precondition_still_precedes_the_409_in_the_wedge_state(client):
    """Same ordering, but with an orphan on disk: a version-less client must still
    get 428 rather than an accidental export triggered by the reconciliation path."""
    target = ws.SEED_READY_ID
    _wedge(client, target)
    assert client.post(f"/api/experiments/{target}/export").status_code == 428
    assert tutorial_ws().load_experiment(target).exported() is False, "a 428 must not have exported"


# --- 4. retry determinism (anti-swallow) --------------------------------------


def test_third_export_after_healing_is_409_again(client):
    """After the wedge heals, the record is exported — so the NEXT export is 409.

    This is the anti-swallow guard: healing must be a one-shot reconciliation, not a
    permanent licence to overwrite an official record.
    """
    target = ws.SEED_READY_ID
    _wedge(client, target)
    second = _export(client, target)
    assert second.status_code == 200 and second.json()["ok"] is True, second.text
    third = _export(client, target)
    assert third.status_code == 409, f"export #3 must be refused, got {third.status_code}"
    assert third.json()["error"] == "record_exists"
    fourth = _export(client, target)
    assert fourth.status_code == 409, "and it must stay refused"


# --- 5. repeated failure still heals ------------------------------------------


def test_two_consecutive_faults_then_a_clean_retry_still_heals(client):
    """Fault twice in a row (the second fault runs with an orphan already on disk),
    then retry cleanly — it still heals, and rev bumps exactly once."""
    target = ws.SEED_READY_ID
    before = _detail(client, target)
    for attempt in (1, 2):
        with _fail_state_save(target) as calls:
            with pytest.raises(OSError):
                _export(client, target)
        assert calls["faulted"] == 1, f"attempt {attempt}: the fault never fired"
        assert tutorial_ws().load_experiment(target).exported() is False

    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert r.json()["rev"] == before["rev"] + 1, (
        "two failed attempts must not have bumped rev; the healing one bumps once"
    )


# --- 6. the sidecar half of the window ---------------------------------------


def test_sidecar_fault_leaves_a_half_written_pair_and_still_heals(client):
    """The OTHER half of the crash window: record written, sidecar not.

    A different disk state from the state-save fault (record present, sidecar
    ABSENT), so it is exercised separately. The clean retry must heal it and the
    final pair must be complete and mutually consistent.
    """
    target = ws.SEED_READY_ID
    record_path, sidecar_path, _ = _paths(target)
    before = _detail(client, target)

    with _fail_sidecar_write(target) as calls:
        with pytest.raises(OSError):
            _export(client, target)
    assert calls["faulted"] == 1, "the injected sidecar fault never fired"
    assert record_path.exists(), "the record write precedes the sidecar write"
    assert not sidecar_path.exists(), "the sidecar must NOT exist after its write faulted"
    assert tutorial_ws().load_experiment(target).exported() is False

    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert record_path.exists() and sidecar_path.exists(), "the pair is still incomplete"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    # Mutually consistent: the sidecar describes THIS record.
    assert record["record_id"] == target
    assert sidecar["record_id"] == target
    assert r.json()["rev"] == before["rev"] + 1
    assert _detail(client, target)["artifact"]["state"] == "current"


# --- 7. the fix deletes nothing ----------------------------------------------


def test_the_reconciliation_never_unlinks_an_artifact(client):
    """Explicit: healing REPLACES via the atomic swap; it never unlinks an artifact.

    ``atomic_write_text`` writes a temp file and ``os.replace``s it over the target,
    and only unlinks its OWN temp file when the swap failed. So no unlink may ever
    name either artifact path. Both artifacts' presence is asserted explicitly at
    every step rather than inferred.
    """
    target = ws.SEED_READY_ID
    _wedge(client, target)
    record_path, sidecar_path, _ = _paths(target)
    assert record_path.exists() and sidecar_path.exists()

    unlinked: list[str] = []
    real_path_unlink = pathlib.Path.unlink
    real_os_unlink = os.unlink
    real_os_remove = os.remove

    def spy_path_unlink(self, *a, **kw):
        unlinked.append(str(self))
        return real_path_unlink(self, *a, **kw)

    def spy_os_unlink(path, *a, **kw):
        unlinked.append(str(path))
        return real_os_unlink(path, *a, **kw)

    def spy_os_remove(path, *a, **kw):
        unlinked.append(str(path))
        return real_os_remove(path, *a, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pathlib.Path, "unlink", spy_path_unlink)
        mp.setattr(os, "unlink", spy_os_unlink)
        mp.setattr(os, "remove", spy_os_remove)
        r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text

    for artifact in (record_path, sidecar_path):
        assert str(artifact) not in unlinked, f"the fix unlinked {artifact.name}"
        assert artifact.exists(), f"{artifact.name} is gone after healing"
    # Sanity: the spy is wired up (the atomic writer's temp-file bookkeeping and
    # nothing else may appear); if it recorded anything, it must be a temp file.
    assert all(".tmp" in p for p in unlinked), f"unexpected unlink(s): {unlinked}"


# --- 8. GET /artifacts never raises and never leaks a path -------------------


def _assert_no_path(text: str, where: str) -> None:
    for marker in UNSAFE_PATH_MARKERS:
        assert marker not in text, f"{where}: leaked path marker {marker!r}"
    assert '":"/' not in text.replace(" ", ""), f"{where}: a value starts with an absolute '/'"


def _assert_no_path_markers(text: str, where: str) -> None:
    """The MARKER half of ``_assert_no_path``, without the leading-``/`` heuristic.

    For the two response shapes where that heuristic is a known false positive and the
    stricter helper must NOT be relaxed for everyone else:

    * a response that legitimately carries an in-app NAVIGATION target
      (``{"to": "/governance?tab=validator"}``) — a client-side route, not a
      filesystem path;
    * a response carrying RENDERED multi-line text, whose JSON-escaped ``\\n``
      newlines each contain a backslash and so trip the Windows-separator marker.
      The escape sequence is stripped here (a literal backslash, encoded ``\\\\``, is
      untouched and still trips it).

    Every absolute/server/mount marker is still asserted, so a real leak is still
    caught in both cases.
    """
    for marker in UNSAFE_PATH_MARKERS:
        if marker == "\\":
            text = text.replace("\\n", " ")
        assert marker not in text, f"{where}: leaked path marker {marker!r}"


def test_artifacts_get_never_raises_in_any_of_the_four_states(client):
    """DEFECT 2. ``GET /artifacts`` must answer, never 500, in every disk/state combo.

    Before the fix, state-says-exported + file-absent raised ``FileNotFoundError``,
    whose message carries the ABSOLUTE server path. (NC4 reverts the fix and this
    test must go red.)
    """
    ready, done = ws.SEED_READY_ID, ws.SEED_DONE_ID

    # Row 4 — not exported, no artifact.
    r = client.get(f"/api/experiments/{ready}/artifacts")
    assert r.status_code == 200, r.text
    assert r.json()["record"] is None and r.json()["sidecar"] is None
    assert r.json()["artifact"] == {"state": "none", "reason": None}
    _assert_no_path(r.text, "row4 /artifacts")

    # Row 1 — the wedge: not exported, orphan artifacts present. Still "none":
    # /artifacts reports the record's STATE, and the state says nothing is exported.
    _wedge(client, ready)
    r = client.get(f"/api/experiments/{ready}/artifacts")
    assert r.status_code == 200, r.text
    assert r.json()["record"] is None and r.json()["artifact"]["state"] == "none"
    _assert_no_path(r.text, "row1 /artifacts")

    # Row 2 — exported with both artifacts present.
    r = client.get(f"/api/experiments/{done}/artifacts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["record"] is not None and body["sidecar"] is not None
    assert body["artifact"]["state"] == "current"
    _assert_no_path(r.text, "row2 /artifacts")

    # Row 3 — exported, artifacts MISSING. This is the raise.
    record_path, sidecar_path, _ = _paths(done)
    record_path.unlink()
    sidecar_path.unlink()
    r = client.get(f"/api/experiments/{done}/artifacts")
    assert r.status_code == 200, f"a missing artifact must not 500: {r.status_code} {r.text}"
    body = r.json()
    assert body["record"] is None and body["sidecar"] is None
    assert body["artifact"]["state"] == "stale"
    assert body["artifact"]["reason"], "an absence must carry the typed reason"
    _assert_no_path(r.text, "row3 /artifacts")


def test_artifacts_get_survives_a_missing_sidecar_alone(client):
    """The half-written-pair state: the record reads, the sidecar is absent. The
    readable half is still served; the absent half is a typed null, not a raise."""
    target = ws.SEED_READY_ID
    assert _export(client, target).status_code == 200
    _, sidecar_path, _ = _paths(target)
    sidecar_path.unlink()

    r = client.get(f"/api/experiments/{target}/artifacts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["record"] is not None, "the readable record must still be served"
    assert body["sidecar"] is None
    assert body["artifact"]["state"] == "stale"
    _assert_no_path(r.text, "half-pair /artifacts")


def test_artifacts_get_survives_an_unreadable_non_json_artifact(client):
    """Truncated/corrupt JSON is the same class of problem as an absent file: a
    typed absence, never a ``JSONDecodeError`` 500."""
    target = ws.SEED_DONE_ID
    record_path, _, _ = _paths(target)
    record_path.write_text("{ this is not json", encoding="utf-8")
    r = client.get(f"/api/experiments/{target}/artifacts")
    assert r.status_code == 200, r.text
    assert r.json()["record"] is None
    assert r.json()["artifact"]["state"] == "stale"
    _assert_no_path(r.text, "corrupt /artifacts")


def test_artifacts_filenames_stay_safe_basenames_when_the_file_is_missing(client):
    """The filenames still name what is expected (matching ``_detail.artifact_refs``,
    which reports the basename whenever ``exported()``), and are still basenames."""
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    record_path.unlink()
    body = client.get(f"/api/experiments/{target}/artifacts").json()
    for key in ("record_filename", "sidecar_filename"):
        name = body[key]
        assert name and name.endswith(".json"), f"{key} should still be a filename, got {name!r}"
        assert "/" not in name and "\\" not in name, f"{key} must be a basename, got {name!r}"


# --- 9. the reconciliation warning -------------------------------------------


_RECONCILE_MARKER = "export reconciliation"


def _reconcile_records(caplog) -> list[logging.LogRecord]:
    return [
        rec
        for rec in caplog.records
        if rec.levelno >= logging.WARNING and _RECONCILE_MARKER in rec.getMessage()
    ]


def test_reconciliation_warning_is_emitted_for_the_wedge(client, caplog):
    """An orphan artifact healed silently would hide a real fault from the operator.
    (NC5 removes the warning and this test must go red.)"""
    target = ws.SEED_READY_ID
    _wedge(client, target)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    found = _reconcile_records(caplog)
    assert len(found) == 1, f"expected exactly one reconciliation warning, got {len(found)}"
    message = found[0].getMessage()
    assert target in message, "the warning must name the record id"
    # A log line is an exfiltration surface too: basename yes, server path never.
    _assert_no_path(message, "reconciliation warning")
    assert f"{target}.json" in message, "the warning should name the artifact basename"


def test_no_reconciliation_warning_on_a_normal_export(client, caplog):
    """The normal path must stay quiet, or the warning means nothing."""
    target = ws.SEED_READY_ID
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert _reconcile_records(caplog) == [], "a clean export must not warn"


def test_no_reconciliation_warning_on_the_genuine_conflict(client, caplog):
    """Nor may the 409 path warn: nothing was reconciled there."""
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        r = _export(client, ws.SEED_DONE_ID)
    assert r.status_code == 409, r.text
    assert _reconcile_records(caplog) == []


def test_no_reconciliation_warning_when_only_the_sidecar_is_missing(client, caplog):
    """Row 3b is a self-heal, NOT an orphan reconciliation — so it must stay silent.

    The decision, and the justification, since either could be defended: the
    reconciliation warning means exactly ONE thing — state and disk disagree about
    whether an export happened. Row 3b is not that: the state says exported and an
    export did happen; one of the pair's two files is simply gone. That is the same
    class as the mirror case immediately below, which the shipped slice deliberately
    left silent. Warning here but not there would make the marker mean two different
    things, and a marker that fires on ordinary self-heals stops being evidence that a
    fault occurred.

    (A distinct "self-heal" log class covering BOTH row 3 and row 3b is defensible and
    is NOT ruled out — but it would change the mirror case too, which the test below
    pins as silent, so it belongs to its own slice rather than to a review fix.)
    """
    target = ws.SEED_DONE_ID
    _, sidecar_path, _ = _paths(target)
    sidecar_path.unlink()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert _reconcile_records(caplog) == [], (
        "a sidecar-only self-heal must not claim the state was wrong"
    )


def test_no_reconciliation_warning_on_the_mirror_case(client, caplog):
    """The mirror case (exported, artifact missing) is a self-heal, not an orphan
    reconciliation — the state was never wrong, so it must not claim it was."""
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    record_path.unlink()
    sidecar_path.unlink()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert _reconcile_records(caplog) == []


# --- 10. a failed export leaves the prior valid state intact -----------------


def test_failed_export_leaves_rev_version_and_record_id_unchanged(client):
    """A fault must not corrupt the record's authoritative state: ``rev``, the
    version/ETag and ``record_id`` are exactly as they were, and the state file is
    still byte-identical (``atomic_write_text`` never leaves a torn target)."""
    target = ws.SEED_READY_ID
    before = _detail(client, target)
    before_etag = _etag(client, target)
    _, _, state_path = _paths(target)
    before_bytes = state_path.read_bytes()

    with _fail_state_save(target) as calls:
        with pytest.raises(OSError):
            _export(client, target)
    assert calls["faulted"] == 1

    after = _detail(client, target)
    assert after["rev"] == before["rev"]
    assert after["version"] == before["version"]
    assert after["record_id"] is None and before["record_id"] is None
    assert after["exported"] is False
    assert _etag(client, target) == before_etag
    assert state_path.read_bytes() == before_bytes, "the state file was modified by a failed export"
    # No orphaned temp files litter the experiment dir either.
    leftovers = [p.name for p in state_path.parent.iterdir() if ".tmp" in p.name]
    assert leftovers == [], f"a failed write left temp litter: {leftovers}"


def test_failed_export_does_not_change_the_exported_record_of_another_id(client):
    """Blast-radius check: faulting one record's export leaves an ALREADY-exported
    sibling's artifact bytes untouched."""
    victim, bystander = ws.SEED_READY_ID, ws.SEED_DONE_ID
    bystander_record, bystander_sidecar, _ = _paths(bystander)
    before_record = bystander_record.read_bytes()
    before_sidecar = bystander_sidecar.read_bytes()

    _wedge(client, victim)
    assert _export(client, victim).status_code == 200

    assert bystander_record.read_bytes() == before_record
    assert bystander_sidecar.read_bytes() == before_sidecar


# --- 11. exported CONTENT is unchanged by this slice -------------------------


def _clean_then_healed(client, target: str) -> tuple[bytes, dict, bytes, dict]:
    """Export cleanly, roll back to pristine not-exported, wedge, heal.

    Returns ``(clean_record_bytes, clean_sidecar, healed_record_bytes, healed_sidecar)``
    so a caller can compare the two exports however it needs to.
    """
    assert _export(client, target).status_code == 200
    record_path, sidecar_path, state_path = _paths(target)
    clean_record_bytes = record_path.read_bytes()
    clean_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["record_id"] = None
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    record_path.unlink()
    sidecar_path.unlink()

    # Now the wedge, then heal.
    _wedge(client, target)
    assert _export(client, target).status_code == 200
    return (
        clean_record_bytes,
        clean_sidecar,
        record_path.read_bytes(),
        json.loads(sidecar_path.read_text(encoding="utf-8")),
    )


def test_healed_export_matches_a_clean_export_record_bytes_and_normalised_sidecar(client):
    """The recovery path must produce EXACTLY what a clean export produces — this
    slice changes WHEN an export is refused, never WHAT it writes.

    Two artifacts, two different comparisons, because they differ in exactly one
    respect — and the name says which is which rather than claiming "byte for byte"
    of both:

    * The RECORD is compared as RAW BYTES. Nothing it contains is wall-clock:
      ``timestamps.created_utc`` is required by the schema, but
      ``src/isaac_records/export.py:80`` ``setdefault``s it, so the draft's own
      verified envelope value wins and ``_now_iso()`` is never consulted. The
      shipped version of this test normalised that field with the rationale that it
      "legitimately differs between two runs" — which was FALSE for this fixture,
      making the normalisation a no-op that quietly hid what the real variable was.
      The normalisation is therefore REMOVED (a no-op with a false rationale is
      worse than nothing) and replaced by the explicit assertion below: if a future
      change ever does make the record's timestamp wall-clock, this test must fail
      loudly and be re-thought, not silently keep passing over a normalised field.

    * The SIDECAR is compared as dicts with ``generated_utc`` NORMALISED, because
      that field genuinely IS wall-clock: ``src/isaac_records/export.py:133``
      populates it from ``export.py:26`` ``_now_iso()``, whose resolution is one
      second. Comparing it strictly (as the shipped version did) passes only while
      the two exports happen inside the same second — it fails the moment they
      straddle a second boundary, which is flaky by construction rather than by bad
      luck. ``test_the_clean_vs_healed_comparison_survives_a_second_boundary`` pins
      that this normalisation is what makes the comparison stable.
    """
    target = ws.SEED_READY_ID
    clean_bytes, clean_sidecar, healed_bytes, healed_sidecar = _clean_then_healed(client, target)

    # The record's created_utc is DRAFT-DERIVED, which is what licenses a byte
    # comparison. Asserted, not assumed.
    draft_created = tutorial_ws().load_experiment(target).draft["fields"]["timestamps.created_utc"]["value"]
    for label, raw in (("clean", clean_bytes), ("healed", healed_bytes)):
        got = json.loads(raw)["timestamps"]["created_utc"]
        assert got == draft_created, (
            f"{label} record's created_utc is no longer the draft's verified value "
            f"({got!r} != {draft_created!r}) — it has become wall-clock, so the raw-byte "
            "comparison below is no longer a valid way to compare two exports"
        )

    assert healed_bytes == clean_bytes, (
        "the healed record bytes differ from a clean export's bytes"
    )

    for obj in (clean_sidecar, healed_sidecar):
        # WALL-CLOCK, one-second resolution: src/isaac_records/export.py:133 ->
        # export.py:26 `_now_iso()`. The ONLY field normalised here.
        assert obj["generated_utc"], "the sidecar must carry a generation timestamp"
        obj["generated_utc"] = "<normalised: wall-clock, export.py:133>"
    assert healed_sidecar == clean_sidecar, (
        "the healed sidecar content differs from a clean export (outside generated_utc)"
    )


def test_the_clean_vs_healed_comparison_survives_a_second_boundary(client):
    """The anti-flake pin for the test above, made DETERMINISTIC.

    Real wall-clock time makes ``generated_utc`` differ only sometimes, so a strict
    comparison passes by luck and a normalised one cannot be shown to be necessary.
    Here ``isaac_records.export._now_iso`` is patched to advance by exactly one second
    per call, so EVERY pair of exports straddles a second boundary:

    * the record bytes must STILL be identical (nothing in the record is wall-clock);
    * the sidecars must differ in ``generated_utc`` and ONLY in ``generated_utc``
      (asserted, so this test also proves the normalisation is not hiding a real
      difference);
    * and the normalised comparison must hold.

    The patch is applied through its own ``pytest.MonkeyPatch.context()`` and targets
    the core module's own global, which ``build_sidecar`` resolves at call time. It
    perturbs the CORE's clock only for the duration of the ``with`` block and writes
    nothing to ``src/``.
    """
    target = ws.SEED_READY_ID
    with _advancing_clock() as clock:
        clean_bytes, clean_sidecar, healed_bytes, healed_sidecar = _clean_then_healed(
            client, target
        )
    assert clock["calls"] > 1, "the injected clock was never consulted"

    assert healed_bytes == clean_bytes, (
        "the record bytes changed when only the clock advanced — something in the "
        "record is wall-clock after all"
    )
    assert healed_sidecar["generated_utc"] != clean_sidecar["generated_utc"], (
        "the advancing clock did not reach generated_utc, so this test proves nothing"
    )
    differing = [
        k
        for k in set(clean_sidecar) | set(healed_sidecar)
        if clean_sidecar.get(k) != healed_sidecar.get(k)
    ]
    assert differing == ["generated_utc"], (
        f"generated_utc must be the ONLY field an advancing clock changes, got {differing}"
    )

    for obj in (clean_sidecar, healed_sidecar):
        obj["generated_utc"] = "<normalised: wall-clock, export.py:133>"
    assert healed_sidecar == clean_sidecar, (
        "normalising generated_utc must make the two sidecars equal across a second "
        "boundary — this is the assertion the shipped test got wrong"
    )


# --- 12. the OTHER artifact readers must not raise either ---------------------
#
# P4 review FIX C. The shipped commit claimed "both frontend consumers already
# null-guard, so where the page used to 500 it now degrades to the pre-export view".
# That was FALSE as a statement about user-visible benefit: `GET /evidence`,
# `POST /validate` and `GET|POST /warnings` still raised `FileNotFoundError` in the
# SAME state, and `api.ts` fetches them in the SAME `Promise.all` as `/artifacts`
# (`getEvidenceBundle` -> evidence + artifacts; `getExportReadiness` -> validate +
# warnings + artifacts). One sibling raising takes the whole bundle down however well
# `/artifacts` degrades, so the null-guard was real but unreachable.
#
# Each endpoint below degrades DIFFERENTLY, on purpose, according to what it already
# promises: `validate` fails closed with the existing crash sentinel (it makes a
# verdict claim, and inventing `ok: true` for a record nobody could read would be a
# false claim of validity); `warnings` falls back to the dry-run candidate and says so
# via its existing `dry_run` flag (it carries NO verdict by design); `evidence` falls
# back to the draft envelopes the sidecar is itself a projection of; `audit` needed no
# change at all.


def _missing_artifacts(client, target: str) -> None:
    """Put an EXPORTED record into the state where both artifacts are gone."""
    record_path, sidecar_path, _ = _paths(target)
    assert tutorial_ws().load_experiment(target).exported() is True
    record_path.unlink()
    sidecar_path.unlink()


def test_validate_reports_no_verdict_instead_of_raising_when_the_artifact_is_gone(client):
    """`POST /validate` must answer, and must NOT claim a verdict it could not reach.

    Fails CLOSED with the EXISTING crash sentinel — the one message
    `assistant_paths.is_validation_unavailable` and the TypeScript `isValidationUnavailable`
    both recognise as "the validator did not run" — so no reader renders it as a
    located schema violation. `ok: true` here would assert the exported record is
    valid; falling back to a dry run would silently swap the SUBJECT of the verdict
    from the written artifact to an in-memory candidate.
    """
    target = ws.SEED_DONE_ID
    _missing_artifacts(client, target)
    r = client.post(f"/api/experiments/{target}/validate")
    assert r.status_code == 200, f"validate must not 500: {r.status_code} {r.text}"
    body = r.json()
    assert body["ok"] is False, "a record that could not be read must not be called valid"
    assert body["dry_run"] is False, "no dry run happened, so dry_run must not claim one"
    assert body["errors"] == [{"path": "$", "message": ap.VALIDATION_UNAVAILABLE_MESSAGE}], (
        "the missing-artifact case must emit the EXISTING crash sentinel, verbatim, or "
        "every reader will describe it as a located validation issue"
    )
    assert ap.is_validation_unavailable(body["errors"]) is True
    _assert_no_path(r.text, "validate with a missing artifact")


def test_warnings_fall_back_to_the_dry_run_candidate_instead_of_raising(client):
    """`GET`/`POST /warnings` must answer, and must say WHICH document they describe.

    This channel carries no pass/fail/validity field by design, and it already
    publishes the one distinction that matters here: `dry_run`. `dry_run: true` states
    "these warnings came from the in-memory export candidate", which is exactly what
    happened — truthful, and useful advice rather than an empty list implying
    "nothing to advise" about a document nobody read.
    """
    target = ws.SEED_DONE_ID
    _missing_artifacts(client, target)
    for method, call in (
        ("GET", lambda: client.get(f"/api/experiments/{target}/warnings")),
        ("POST", lambda: client.post(f"/api/experiments/{target}/warnings")),
    ):
        r = call()
        assert r.status_code == 200, f"{method} /warnings must not 500: {r.status_code} {r.text}"
        body = r.json()
        assert body["dry_run"] is True, (
            f"{method} /warnings: the written record was not readable, so the payload "
            "must not claim it checked one"
        )
        # Still an advisory channel: no verdict field appears, missing artifact or not.
        for forbidden in ("ok", "valid", "exportable", "complete", "pass", "fail"):
            assert forbidden not in body, f"{method} /warnings leaked a verdict field {forbidden!r}"
        _assert_no_path(r.text, f"{method} /warnings with a missing artifact")


def test_evidence_falls_back_to_the_draft_trail_instead_of_raising(client):
    """`GET /evidence` must answer with this record's own evidence, not an empty list.

    The sidecar is a projection of the draft's evidence envelopes, written at export
    time, so the draft trail is the same evidence from its ORIGIN — never fabricated.
    `evidence_trail_from_sidecar` needs BOTH files anyway (values from the record,
    support from the sidecar), so one absent file already makes the sidecar trail
    unbuildable. An empty list would instead assert that no field carries evidence.
    """
    target = ws.SEED_DONE_ID
    before = client.get(f"/api/experiments/{target}/evidence")
    assert before.status_code == 200
    sidecar_entries = before.json()["evidence"]
    assert sidecar_entries, "the fixture must have a non-empty exported evidence trail"

    _missing_artifacts(client, target)
    r = client.get(f"/api/experiments/{target}/evidence")
    assert r.status_code == 200, f"evidence must not 500: {r.status_code} {r.text}"
    entries = r.json()["evidence"]
    assert entries, "the degraded trail must not be empty — that would deny the evidence exists"
    for entry in entries:
        assert entry["path"], "every degraded entry must still name its field"
        assert "evidence" in entry
    _assert_no_path(r.text, "evidence with a missing artifact")


def test_evidence_degrades_only_for_the_sidecar_half_too(client):
    """Half-pair: the RECORD reads but the sidecar is gone. Still no raise.

    Covered separately because `evidence_trail_from_sidecar` consumes both files, so
    the two halves are different code paths through the same guard.
    """
    target = ws.SEED_DONE_ID
    _, sidecar_path, _ = _paths(target)
    sidecar_path.unlink()
    r = client.get(f"/api/experiments/{target}/evidence")
    assert r.status_code == 200, r.text
    assert r.json()["evidence"], "the draft trail must still be served"
    _assert_no_path(r.text, "evidence with a missing sidecar")


def test_audit_already_tolerates_a_missing_artifact(client):
    """`POST /audit` needed NO change — asserted, not assumed.

    It never opens a path derived from `record_id`: `audit.audit_records` GLOBS
    `records_dir/*.json`, so a deleted artifact yields no rows and a corrupt one is
    reported against `path.name` (a basename). This test is the evidence for the
    "checked, not changed" claim in `routes.post_audit`, so a future refactor that
    replaced the glob with a direct read would fail here.
    """
    target = ws.SEED_DONE_ID
    _missing_artifacts(client, target)
    r = client.post(f"/api/experiments/{target}/audit")
    assert r.status_code == 200, f"audit must not 500: {r.status_code} {r.text}"
    assert r.json()["records"] == [], "no artifact on disk means no audited rows"
    _assert_no_path(r.text, "audit with a missing artifact")

    # A corrupt artifact is a report row, not a raise, and names a BASENAME only.
    record_path, _, _ = _paths(target)
    record_path.write_text("{ this is not json", encoding="utf-8")
    r = client.post(f"/api/experiments/{target}/audit")
    assert r.status_code == 200, r.text
    assert len(r.json()["records"]) == 1
    # The rendered `text` field is multi-line, so its JSON-escaped newlines trip the
    # Windows-separator marker; markers are still all asserted (see the helper).
    _assert_no_path_markers(r.text, "audit with a corrupt artifact")
    # What actually matters: the row names a BASENAME, which is where a path would leak.
    assert r.json()["records"][0]["name"] == f"{target}.json"


def test_the_assistant_export_intent_does_not_raise_and_claims_no_finding(client):
    """`_assistant_validate_dryrun`'s docstring said "never raises". It did.

    An export-blockers question resolves the validation thunk, which read the exported
    artifact unguarded. It now returns the same crash sentinel, which
    `assistant_query` already routes to the honest "could not be completed" answer:
    `insufficient_context`, no count, no location, no verdict. Without the sentinel
    (i.e. with any other message) that branch would tell the reader "1 record-level
    validation issue may be blocking export" — a confident claim about an issue the
    validator never located.
    """
    target = ws.SEED_DONE_ID
    _missing_artifacts(client, target)
    r = client.post(
        f"/api/experiments/{target}/assistant/query",
        json={"question": "what's blocking export"},
    )
    assert r.status_code == 200, f"the assistant must not 500: {r.status_code} {r.text}"
    body = r.json()
    assert body["result"] == "insufficient_context", body
    assert body["answer"].startswith(ap.VALIDATION_UNAVAILABLE_SUMMARY), body["answer"]
    assert "validation issue" not in body["answer"], "no finding may be claimed"
    assert not any(ch.isdigit() for ch in ap.VALIDATION_UNAVAILABLE_SUMMARY)
    # This response carries an in-app navigation target ("/governance?tab=validator"),
    # which legitimately starts with "/"; every server-path marker is still asserted.
    _assert_no_path_markers(r.text, "assistant export intent with a missing artifact")


def test_no_artifact_reader_raises_in_the_missing_artifact_state(client):
    """The sweep: EVERY endpoint that reads an exported artifact, in one place.

    A per-endpoint test can be deleted or renamed; this one fails if a NEW reader is
    added without a guard, which is how this defect class recurs.
    """
    target = ws.SEED_DONE_ID
    _missing_artifacts(client, target)
    base = f"/api/experiments/{target}"
    calls = {
        "GET /artifacts": lambda: client.get(f"{base}/artifacts"),
        "GET /evidence": lambda: client.get(f"{base}/evidence"),
        "POST /validate": lambda: client.post(f"{base}/validate"),
        "GET /warnings": lambda: client.get(f"{base}/warnings"),
        "POST /warnings": lambda: client.post(f"{base}/warnings"),
        "POST /audit": lambda: client.post(f"{base}/audit"),
        "GET detail": lambda: client.get(base),
        "GET /evidence-classification": lambda: client.get(f"{base}/evidence-classification"),
    }
    for label, call in calls.items():
        r = call()  # a raise here fails the test with the original traceback
        assert r.status_code == 200, f"{label}: {r.status_code} {r.text}"
        _assert_no_path(r.text, label)


def test_no_artifact_reader_raises_on_a_corrupt_artifact_either(client):
    """Same sweep for CORRUPT (present but not JSON) — a distinct failure mode from
    absent, and the one `ValueError` in the narrow catch exists for."""
    target = ws.SEED_DONE_ID
    record_path, sidecar_path, _ = _paths(target)
    record_path.write_text("{ this is not json", encoding="utf-8")
    sidecar_path.write_text("\x00 not json either", encoding="utf-8")
    base = f"/api/experiments/{target}"
    for label, call in (
        ("GET /artifacts", lambda: client.get(f"{base}/artifacts")),
        ("GET /evidence", lambda: client.get(f"{base}/evidence")),
        ("POST /validate", lambda: client.post(f"{base}/validate")),
        ("GET /warnings", lambda: client.get(f"{base}/warnings")),
        ("GET detail", lambda: client.get(base)),
    ):
        r = call()
        assert r.status_code == 200, f"{label}: {r.status_code} {r.text}"
        _assert_no_path(r.text, f"{label} (corrupt)")


# --- 13. the tolerance itself: narrow, and single-sourced ---------------------


def test_read_artifact_json_returns_none_for_absent_unreadable_and_non_json(tmp_path):
    """The three tolerated cases, as a direct unit check on the helper."""
    missing = tmp_path / "nope.json"
    assert routes._read_artifact_json(missing) is None  # FileNotFoundError -> OSError

    a_directory = tmp_path / "dir.json"
    a_directory.mkdir()
    assert routes._read_artifact_json(a_directory) is None  # IsADirectoryError -> OSError

    not_json = tmp_path / "bad.json"
    not_json.write_text("{ nope", encoding="utf-8")
    assert routes._read_artifact_json(not_json) is None  # JSONDecodeError -> ValueError

    good = tmp_path / "ok.json"
    good.write_text('{"record_id": "X"}', encoding="utf-8")
    assert routes._read_artifact_json(good) == {"record_id": "X"}


def test_read_artifact_json_lets_an_unexpected_exception_propagate(tmp_path):
    """The catch is NARROW on purpose, and the narrowness is now pinned.

    Broadening it to `except Exception` left the whole suite green, which means nothing
    was asserting the boundary. It matters: reporting an arbitrary failure as `None`
    would tell every caller "the artifact is missing" — a false statement about the
    filesystem — and would swallow genuine programming errors into a plausible-looking
    degraded response.

    NOTE, and deliberately NOT changed here: `dependencies.artifact_state` performs the
    same read under a bare `except Exception`, so the codebase is inconsistent about
    this. That function's contract is different (it must always produce a state label
    and never raise) and editing it is outside this review's scope.
    """

    class _Exploding:
        """Quacks like a Path for this helper's single use of it."""

        name = "unexpected.json"

        def read_text(self, *args, **kwargs):
            raise RuntimeError("not an OSError and not a ValueError")

    with pytest.raises(RuntimeError):
        routes._read_artifact_json(_Exploding())

    class _Interrupted:
        name = "interrupted.json"

        def read_text(self, *args, **kwargs):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        routes._read_artifact_json(_Interrupted())


def test_the_missing_artifact_reason_has_exactly_one_definition(client):
    """`MISSING_REASON`'s single-definition rationale, pinned.

    `dependencies.MISSING_REASON` was promoted from `_MISSING_REASON` precisely so the
    route could reuse it instead of copying the string. Nothing asserted that, so a
    second copy could reappear in `routes.py` and drift out of step with the state it
    describes while every test stayed green.
    """
    src = pathlib.Path(routes.__file__).read_text(encoding="utf-8")
    assert dependencies.MISSING_REASON not in src, (
        "routes.py must REFERENCE dependencies.MISSING_REASON, never re-declare the "
        "literal — two copies of a reason string drift"
    )
    assert "dependencies.MISSING_REASON" in src, "routes.py must still consume the shared constant"

    # And the value the wire actually carries is that one constant.
    target = ws.SEED_DONE_ID
    _missing_artifacts(client, target)
    artifact = client.get(f"/api/experiments/{target}/artifacts").json()["artifact"]
    assert artifact == {"state": "stale", "reason": dependencies.MISSING_REASON}


# --- 14. the export response body does not fabricate a mutation --------------


def test_the_self_heal_reports_changed_false_not_a_fabricated_field_update(client):
    """P4 review FIX E. The mirror-case body used to contradict itself.

    Measured before the fix: `{"changed": true, "changed_fields": ["record_id"],
    "reason": "Updated 1 field(s)…"}` while `rev 0 -> 0`, the ETag was unchanged, and
    `save_versioned()` had returned `False` — i.e. the response claimed a mutation that
    provably did not occur, contradicting this very handler's own failure-branch rule
    ("never fabricate a mutation that did not occur"). The two sibling mutation
    handlers (`post_answers`, `post_edit`) pass `save_versioned()`'s return through;
    export now does too.
    """
    target = ws.SEED_DONE_ID
    before = _detail(client, target)
    _missing_artifacts(client, target)

    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    inv = r.json()["invalidation"]
    assert inv["changed"] is False, "no authoritative state changed, so changed must be False"
    assert inv["changed_fields"] == [], "no field was updated, so none may be named"
    assert inv["rev"] == before["rev"], "and the reported rev must match the unchanged rev"
    assert r.json()["rev"] == before["rev"]
    # The repair itself still happened and is still reported honestly.
    record_path, sidecar_path, _ = _paths(target)
    assert record_path.exists() and sidecar_path.exists()
    assert inv["artifact"]["state"] == "current"
    # ~~KNOWN, documented, NOT fixed here: `build_invalidation`'s changed=False `reason`
    # is worded for /answers ("the submitted value was identical"), which is not
    # literally what happened on an export self-heal. That string is SHARED with
    # /answers and /edit, whose tests pin it, so rewording it is a separate slice.~~
    #
    # FIXED 2026-08-25, and the old note is struck rather than deleted because it named
    # the obstacle correctly and the fix is exactly the removal of that obstacle: the
    # sentence is no longer SHARED unconditionally. `build_invalidation` now takes an
    # `identical` argument — the caller's answer to "did you actually compare the
    # values?" — and its DEFAULT is the claim-free sentence. Export passes nothing,
    # because nothing was submitted to it, so "the submitted value" names nothing here.
    # The answering and correcting routes pass what they established, so they keep the
    # confident sentence exactly where it is true.
    assert inv["reason"] == dependencies.NO_OP_UNKNOWN_REASON
    assert "identical" not in inv["reason"], inv["reason"]


def test_a_real_export_still_reports_the_record_id_mutation(client):
    """The pass-through must not weaken the NORMAL path: a first export really does
    change `record_id`, so it must still report `changed: true` and name the field."""
    target = ws.SEED_READY_ID
    before = _detail(client, target)
    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    inv = r.json()["invalidation"]
    assert inv["changed"] is True
    assert inv["changed_fields"] == ["record_id"]
    assert inv["rev"] > before["rev"]


def test_the_wedge_heal_also_reports_a_real_mutation(client):
    """Row 1 heals a NOT-exported record, so `record_id` genuinely changes there too."""
    target = ws.SEED_READY_ID
    _wedge(client, target)
    r = _export(client, target)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert r.json()["invalidation"]["changed"] is True
    assert r.json()["invalidation"]["changed_fields"] == ["record_id"]
