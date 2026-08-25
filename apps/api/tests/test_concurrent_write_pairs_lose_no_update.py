"""Concurrent write PAIRS no other file covers: exactly one lands, nothing is lost.

WHY A THIRD CONCURRENCY FILE. ``test_handler_concurrency.py`` pins the record-level
``/answers`` and ``/edit`` same-token races and the precondition rules;
``test_lifecycle_concurrency.py`` pins the scientific lifecycle — run edits, overrides,
run removal, submission, conflict decisions. The eight pairs here are the ones neither
reaches, and each was chosen because the two routes write DIFFERENT parts of one
document, which is where a lost update can hide without any single-route test noticing:

  A. ``PATCH /assets/{id}`` vs ``PATCH /assets/{id}``   (asset edit race)
  B. ``POST /assets/{id}/remove`` vs ``PATCH /assets/{id}``
  C. ``POST /answers`` vs ``POST /edit`` on ONE address
  D. two ``If-Match: *`` writers on the SAME open blocker
  E. two ``If-Match: *`` writers on DIFFERENT open blockers
  F. ``POST /transcript`` (finalize) vs ``POST /edit``
  G. two ``POST /notes/{id}/review`` on one note
  H. ``POST /runs/{id}/remove`` vs ``POST /notes``

Every test meets the bar ``test_lifecycle_concurrency``'s module docstring sets: the
interleaving is PINNED by the imported ``_LockRendezvous`` (never a sleep), every
refusal is asserted as an EXACT status AND an EXACT ``error`` string, and every
refusal's AFTERMATH is read back out of the workspace rather than believed from the
response body. Where a race can legitimately go either way the docstring names both
orderings and the assertion is the invariant that holds in both.

D IS THE ONE WHOSE GUARD WAS MUTATION-TESTED, AND THE MEASURED RESULT IS NOT WHAT A
READER WOULD GUESS. ``If-Match: *`` disables the compare-and-swap by design, so the
only thing separating two wildcard writers answering ONE question is
``routes._refuse_answering_an_already_answered_key``. Replacing that guard with a
function that always returns ``None`` and re-running the race produced **two ``200``
responses, one revision, and the second writer's digest stored nowhere** — so the
failure it prevents is not a last-write-wins overwrite but a *false success*: a client
told its answer was accepted when nothing was written. That is why test D asserts the
status pair ``[200, 422]`` and asserts the loser's ``error``, ``keys`` and ``answer_at``
rather than only checking the stored value: with the guard gone the values look right
and the responses lie.
"""

from __future__ import annotations

import copy
import json

import pytest

import isaac_api.workspace as ws

from conftest import client_ws, tutorial_client
from test_export_fan_out import _split_full_draft
from test_handler_concurrency import _LockRendezvous, _outcome, _race

#: Well-formed 64-hex sentinels the system can never invent, one per writer, so
#: ``assert <sentinel> not in json.dumps(state)`` is a real statement.
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

#: The two asset blockers that are OPEN on the new-draft seed.
OPEN_URI_1 = "ssrl-archive://BL15-2/2099_run_000/raw/"
OPEN_URI_2 = "ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi"
#: The same asset, already answered, on the READY seed.
ANSWERED_URI = "ssrl-archive://BL15-2/2099_run_000/raw/"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# --- reads used for ASSERTIONS ONLY, never to perform a mutation --------------


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _state(exp) -> str:
    return json.dumps(exp.to_state())


def _asset(exp, asset_id: str):
    for entry in exp.draft.get("assets") or []:
        if isinstance(entry, dict) and entry.get("asset_id") == asset_id:
            return entry
    return None


def _zero_run(store, eid: str):
    """An experiment whose ONE export unit is the record itself, carrying the seed's
    assets. Assets are a run-level block, so a fan-out fixture would put them on the
    runs and there would be nothing at ``/assets`` to race over."""
    exp = store.create_experiment(
        "Probe", {"kind": "synthetic"}, copy.deepcopy(ws._full_draft()), id=eid
    )
    exp.save_versioned()
    return store.load_experiment(eid)


def _with_runs(store, eid: str, labels):
    experiment_draft, run_draft = _split_full_draft()
    exp = store.create_experiment("Probe", {"kind": "synthetic"}, experiment_draft, id=eid)
    for label in labels:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return store.load_experiment(eid)


def _raced(rendezvous, client, eid: str) -> None:
    assert rendezvous.arrivals == 2, (
        "both requests must have reached the record lock — the race did not happen"
    )
    assert not rendezvous.timed_out, (
        "the two requests did not overlap; this run proved nothing about concurrency"
    )
    rendezvous.assert_scoped(client.tutorial_session_id)


# =============================================================================
# A. asset PATCH vs asset PATCH, one token
# =============================================================================
def test_two_asset_edits_with_one_token_leave_exactly_the_winner(client, monkeypatch):
    """Exactly one 200 and one 412 ``stale_write``; the record's ``rev`` advances
    EXACTLY once; the loser's sha is nowhere in the persisted state.

    LEGITIMATE ORDERINGS: either writer may win, so nothing here names one. The
    asset routes carry no validator of their own — the RECORD's ``ETag`` is the
    precondition, which ``patch_asset``'s own ``If-Match`` description states — so
    this is the record-level compare-and-swap asked of a route that reaches into
    ``draft["assets"]`` rather than into ``draft["fields"]``.
    """
    store = client_ws(client)
    eid = "01PROBEASSETPATCHRACE0001"
    _zero_run(store, eid)
    token = _etag(client, eid)
    before = store.load_experiment(eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.patch(
            f"/api/experiments/{eid}/assets/reduced_spectrum",
            json={"confirmed_by_user": True, "sha256": SHA_A},
            headers={"If-Match": token},
        ),
        lambda: client.patch(
            f"/api/experiments/{eid}/assets/reduced_spectrum",
            json={"confirmed_by_user": True, "sha256": SHA_B},
            headers={"If-Match": token},
        ),
    ])

    _raced(rendezvous, client, eid)
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 412], f"exactly one writer may win: {_outcome(responses)}"

    loser = next(r for r in responses if r.status_code == 412)
    body = loser.json()
    assert body["error"] == "stale_write"
    assert body["experiment_id"] == eid
    assert "run_id" not in body, (
        "an asset edit is validated by the RECORD's ETag, so its refusal names the record"
    )

    after = store.load_experiment(eid)
    assert after.rev == before.rev + 1, "rev must advance exactly once, not twice"
    won, lost = (
        (SHA_A, SHA_B) if responses[0].status_code == 200 else (SHA_B, SHA_A)
    )
    assert _asset(after, "reduced_spectrum")["sha256"] == won
    assert lost not in _state(after), (
        "the rejected writer's sha reached the record — this is a lost update"
    )


# =============================================================================
# B. asset REMOVE vs asset PATCH, same asset
# =============================================================================
def test_removing_an_asset_while_it_is_being_edited(client, monkeypatch):
    """Both operations are validated by the RECORD's ``ETag``, so whichever loses
    loses on the precondition: exactly one 200 and one 412 ``stale_write``.

    LEGITIMATE ORDERINGS, and they end in OPPOSITE states, which is why the
    assertion is a branch:

    * the removal wins -> the asset is gone AND the edit's sha is nowhere in the
      document; a removal that dropped the asset while leaving the refused edit's
      hash behind would be a sha256 this application invented, which §5 forbids;
    * the edit wins -> the asset survives carrying the NEW sha, and the removal is
      refused **412 stale_write** with nothing removed.

    THE TWO REFUSALS ARE DIFFERENT STATUSES AND THAT IS THE INTERESTING HALF. The
    edit loses with **404 asset_not_found**, not 412 — ``patch_asset`` resolves the
    asset INSIDE the lock, before the precondition, so a caller addressing something
    that no longer exists is told that rather than sent to re-read a version for a
    thing that is gone. It is the same ordering ``patch_run`` uses for
    ``run_not_found``, and asserting the exact code here is what would catch a future
    edit that reordered the two checks in only one of the two routes.
    """
    store = client_ws(client)
    eid = "01PROBEASSETREMOVEVSPAT01"
    _zero_run(store, eid)
    token = _etag(client, eid)
    before = store.load_experiment(eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    remove, patch = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/assets/reduced_spectrum/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": token},
        ),
        lambda: client.patch(
            f"/api/experiments/{eid}/assets/reduced_spectrum",
            json={"confirmed_by_user": True, "sha256": SHA_C},
            headers={"If-Match": token},
        ),
    ])

    _raced(rendezvous, client, eid)
    after = store.load_experiment(eid)
    assert after.rev == before.rev + 1, "exactly one accepted write is exactly one revision"

    if remove.status_code == 200:
        assert patch.status_code == 404, _outcome([remove, patch])
        patch_body = patch.json()
        assert patch_body["error"] == "asset_not_found"
        assert patch_body["experiment_id"] == eid
        assert patch_body["id"] == "reduced_spectrum", (
            "a refused ASSET edit must name the asset it was addressed to"
        )
        assert _asset(after, "reduced_spectrum") is None, "the removal won"
        assert SHA_C not in _state(after), (
            "the refused edit's sha survived the removal of the asset it addressed"
        )
        assert remove.json()["removed_asset_id"] == "reduced_spectrum"
    else:
        assert patch.status_code == 200, _outcome([remove, patch])
        assert remove.status_code == 412, _outcome([remove, patch])
        assert remove.json()["error"] == "stale_write"
        assert remove.json()["experiment_id"] == eid
        entry = _asset(after, "reduced_spectrum")
        assert entry is not None, "the edit won, so the asset must survive"
        assert entry["sha256"] == SHA_C


# =============================================================================
# C. /answers vs /edit on ONE address
# =============================================================================
def test_an_answer_and_a_correction_of_the_same_address_race(client, monkeypatch):
    """``POST /answers`` FILLS an open blocker; ``POST /edit`` CORRECTS an answered
    one. On one address exactly one of them is legal at any instant, and which one
    depends on whether the other has landed — so this pair is the record-level
    counterpart of ``test_a_run_level_answer_racing_a_correction_of_the_same_field``,
    which covers only the RUN.

    LEGITIMATE ORDERINGS, and the loser's refusal is a DIFFERENT status in each:

    * the answer wins -> the record moved, so the correction's ``If-Match`` is stale
      and it is refused **412 stale_write**;
    * the correction wins -> it never had an editable target (the uri is still
      pending, so ``_answers_to_apply_shape(edit_only=True)`` carries nothing) and
      it is refused **422 unrecognized_field** having written nothing, and the
      answer then lands normally.

    In BOTH orderings the invariant is the same and it is what is asserted: the
    ANSWER's sha is stored, the CORRECTION's sha is nowhere in the document, and the
    record advanced exactly one revision.
    """
    target = ws.SEED_NEW_DRAFT_ID
    store = client_ws(client)
    token = _etag(client, target)
    before = store.load_experiment(target)
    rendezvous = _LockRendezvous(monkeypatch, target)

    answer, correction = _race([
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json={"confirmed_by_user": True, "answers": {OPEN_URI_1: SHA_A}},
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/edit",
            json={"confirmed_by_user": True, "answers": {OPEN_URI_1: SHA_B}},
            headers={"If-Match": token},
        ),
    ])

    _raced(rendezvous, client, target)
    assert answer.status_code == 200, _outcome([answer, correction])
    assert correction.status_code in (412, 422), _outcome([answer, correction])
    body = correction.json()
    assert body["error"] in ("stale_write", "unrecognized_field"), body
    if body["error"] == "stale_write":
        assert body["experiment_id"] == target

    after = store.load_experiment(target)
    assert after.rev == before.rev + 1, "exactly one accepted write is exactly one revision"
    assert SHA_A in _state(after), "the answer's value was not persisted"
    assert SHA_B not in _state(after), (
        "the refused correction's sha reached the record — a value no route accepted"
    )


# =============================================================================
# D/E. the WILDCARD precondition, which `_check_if_match` deliberately accepts
# =============================================================================
def test_two_wildcard_writers_on_one_blocker_are_separated_by_the_SEMANTIC_guard(
    client, monkeypatch
):
    """``If-Match: *`` disables the compare-and-swap, so the loser is NOT 412 — it is
    **422 ``already_answered``**, decided inside the lock over a freshly loaded
    document.

    THIS IS THE TEST THAT SAYS WHAT PROTECTS A WILDCARD WRITER, because nothing else
    does. ``_check_if_match`` passes ``*`` unconditionally and
    ``_expected_rev_from_token`` yields no expected revision, so both writers clear
    the precondition; the ONLY thing standing between them and a silent last-write-wins
    is ``_refuse_answering_an_already_answered_key`` — and that refusal is only
    trustworthy because it runs on the document loaded INSIDE ``record_lock``. A
    handler that hoisted it above the lock would let both writers see an open blocker
    and the second would overwrite the first's answer with no refusal at all.

    LEGITIMATE ORDERINGS: either writer may win. What is asserted is that exactly one
    does, that the loser is told the truth about WHY (its question was already
    closed, not that its token was stale — it sent no token to be stale), that the
    record advanced exactly once, and that the loser's sha is nowhere.
    """
    target = ws.SEED_NEW_DRAFT_ID
    store = client_ws(client)
    before = store.load_experiment(target)
    rendezvous = _LockRendezvous(monkeypatch, target)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json={"confirmed_by_user": True, "answers": {OPEN_URI_1: SHA_A}},
            headers={"If-Match": "*"},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json={"confirmed_by_user": True, "answers": {OPEN_URI_1: SHA_B}},
            headers={"If-Match": "*"},
        ),
    ])

    _raced(rendezvous, client, target)
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 422], (
        f"a wildcard precondition must not let both writers answer one question: "
        f"{_outcome(responses)}"
    )
    loser = next(r for r in responses if r.status_code == 422)
    body = loser.json()
    assert body["error"] == "already_answered", body
    assert body["experiment_id"] == target
    assert body["keys"] == [OPEN_URI_1]
    assert body["answer_at"] == "POST /api/experiments/{experiment_id}/edit", (
        "the refusal must name the operation that CAN take the correction"
    )

    after = store.load_experiment(target)
    assert after.rev == before.rev + 1, "rev must advance exactly once, not twice"
    won, lost = (
        (SHA_A, SHA_B) if responses[0].status_code == 200 else (SHA_B, SHA_A)
    )
    assert won in _state(after)
    assert lost not in _state(after), "the refused wildcard writer's sha reached the record"


def test_two_wildcard_writers_on_DIFFERENT_blockers_both_land(client, monkeypatch):
    """The negative control for the test above, and it is not decoration: without it
    that one passes for a build that refused ``If-Match: *`` outright, or that
    serialised wildcard writers into a single winner.

    Two ``*`` writers filling DIFFERENT open blockers must BOTH succeed, the record
    must advance EXACTLY twice, and both shas must be stored — which is only true if
    the second writer loaded the document the first one saved. That is what
    ``record_lock`` buys a caller who supplied no validator of their own.
    """
    target = ws.SEED_NEW_DRAFT_ID
    store = client_ws(client)
    before = store.load_experiment(target)
    rendezvous = _LockRendezvous(monkeypatch, target)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json={"confirmed_by_user": True, "answers": {OPEN_URI_1: SHA_A}},
            headers={"If-Match": "*"},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/answers",
            json={"confirmed_by_user": True, "answers": {OPEN_URI_2: SHA_B}},
            headers={"If-Match": "*"},
        ),
    ])

    _raced(rendezvous, client, target)
    assert [r.status_code for r in responses] == [200, 200], (
        f"independent blockers must not refuse each other: {_outcome(responses)}"
    )
    after = store.load_experiment(target)
    assert after.rev == before.rev + 2, "two accepted writes are exactly two revisions"
    assert SHA_A in _state(after), "the first wildcard write was lost"
    assert SHA_B in _state(after), "the second wildcard write was lost"


# =============================================================================
# F. transcript finalize vs /edit
# =============================================================================
def test_finalising_a_transcript_while_the_record_is_being_corrected(client, monkeypatch):
    """``POST /transcript`` is a MUTATION — it captures notes into the record — and it
    is validated by the record's ``ETag`` like every other record-level write. Racing
    it against ``POST /edit`` on one token: exactly one 200, one 412 ``stale_write``,
    and the loser left NOTHING behind.

    The aftermath assertion is the point. A refused transcript that had already
    appended its notes would be captured content the scientist was told was not
    recorded — the ``retention`` block the 200 returns says content is "retained with
    the experiment", so a partial write here is content retained under a refusal. The
    note count and the transcript's own text are therefore both read back out of the
    workspace, not believed from the response.

    LEGITIMATE ORDERINGS: either may win; neither is named.
    """
    target = ws.SEED_READY_ID
    store = client_ws(client)
    token = _etag(client, target)
    before = store.load_experiment(target)
    notes_before = len(before.notes)
    rendezvous = _LockRendezvous(monkeypatch, target)

    transcript, edit = _race([
        lambda: client.post(
            f"/api/experiments/{target}/transcript",
            json={"text": "PROBE-TRANSCRIPT-SENTINEL", "finalized": True},
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/edit",
            json={"confirmed_by_user": True, "answers": {ANSWERED_URI: SHA_B}},
            headers={"If-Match": token},
        ),
    ])

    _raced(rendezvous, client, target)
    codes = sorted(r.status_code for r in [transcript, edit])
    assert codes == [200, 412], f"exactly one writer may win: {_outcome([transcript, edit])}"
    after = store.load_experiment(target)
    assert after.rev == before.rev + 1, "rev must advance exactly once, not twice"

    if transcript.status_code == 412:
        assert transcript.json()["error"] == "stale_write"
        assert transcript.json()["experiment_id"] == target
        assert len(after.notes) == notes_before, (
            "a REFUSED transcript captured notes anyway — content retained under a refusal"
        )
        assert "PROBE-TRANSCRIPT-SENTINEL" not in _state(after), (
            "the refused transcript's text reached the record"
        )
        assert SHA_B in _state(after), "the winning correction was not persisted"
    else:
        assert edit.json()["error"] == "stale_write"
        assert edit.json()["experiment_id"] == target
        assert "PROBE-TRANSCRIPT-SENTINEL" in _state(after)
        assert SHA_B not in _state(after), "the refused correction's sha reached the record"


# =============================================================================
# G. two reviews of ONE note
# =============================================================================
def test_two_reviews_of_one_note_store_exactly_one_decision(client, monkeypatch):
    """A note has NO validator of its own — ``post_note_review``'s ``If-Match``
    description says so explicitly — so two reviewers holding the record's one token
    contend on it: exactly one 200, one 412 ``stale_write``, and the note carries
    exactly the winner's decision.

    ``keep`` and ``dismiss`` are chosen because they are terminal and mutually
    exclusive, so "exactly one decision" is observable in the stored note's ``state``
    rather than inferable from the response.

    LEGITIMATE ORDERINGS: either reviewer may win. A note is never deleted, so the
    invariant that holds in both is that the note still exists, is in a REVIEWED
    state, and is in exactly one of the two the winner asked for.
    """
    target = ws.SEED_READY_ID
    store = client_ws(client)
    created = client.post(
        f"/api/experiments/{target}/notes",
        json={"text": "the beamline tripped", "source": "typed_note"},
        headers={"If-Match": _etag(client, target)},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["note"]["id"]
    token = _etag(client, target)
    before = store.load_experiment(target)
    rendezvous = _LockRendezvous(monkeypatch, target)

    keep, dismiss = _race([
        lambda: client.post(
            f"/api/experiments/{target}/notes/{note_id}/review",
            json={"confirmed_by_user": True, "action": "keep"},
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{target}/notes/{note_id}/review",
            json={"confirmed_by_user": True, "action": "dismiss"},
            headers={"If-Match": token},
        ),
    ])

    _raced(rendezvous, client, target)
    codes = sorted(r.status_code for r in [keep, dismiss])
    assert codes == [200, 412], f"exactly one reviewer may win: {_outcome([keep, dismiss])}"
    loser = next(r for r in [keep, dismiss] if r.status_code == 412)
    assert loser.json()["error"] == "stale_write"
    assert loser.json()["experiment_id"] == target

    after = store.load_experiment(target)
    assert after.rev == before.rev + 1, "rev must advance exactly once, not twice"
    note = after.get_note(note_id)
    assert note is not None, "a review must never remove a note"
    expected = "kept" if keep.status_code == 200 else "dismissed"
    assert note.state == expected, (
        f"the note carries {note.state!r}; the winner asked for {expected!r}"
    )
    assert len(after.notes) == len(before.notes), "a review may not create a second note"


# =============================================================================
# H. run removal vs a record-level note capture
# =============================================================================
def test_removing_a_run_while_a_note_is_being_captured(client, monkeypatch):
    """Both are validated by the RECORD's ``ETag`` even though one addresses a run
    and the other addresses nothing in particular: exactly one 200 (or 201) and one
    412 ``stale_write``.

    The aftermath is asserted in both directions because the two writes touch
    disjoint parts of one document and a naive implementation would let both land:
    if the removal won, the note's sentinel text must be NOWHERE (a refused capture
    that stored its text would be retained content under a refusal); if the capture
    won, the run must still be present with its ordinal untouched.
    """
    store = client_ws(client)
    eid = "01PROBEREMOVEVSNOTE00001"
    exp = _with_runs(store, eid, ("Run A", "Run B"))
    run_a, run_b = (run.id for run in exp.sorted_runs())
    token = _etag(client, eid)
    before = store.load_experiment(eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    remove, note = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{run_a}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/notes",
            json={"text": "PROBE-NOTE-SENTINEL", "source": "typed_note"},
            headers={"If-Match": token},
        ),
    ])

    _raced(rendezvous, client, eid)
    after = store.load_experiment(eid)
    assert after.rev == before.rev + 1, "exactly one accepted write is exactly one revision"
    # The bystander run is untouched whichever way the race went.
    assert after.get_run(run_b) is not None
    assert after.get_run(run_b).version_token() == before.get_run(run_b).version_token()

    if remove.status_code == 200:
        assert note.status_code == 412, _outcome([remove, note])
        assert note.json()["error"] == "stale_write"
        assert note.json()["experiment_id"] == eid
        assert after.get_run(run_a) is None
        assert len(after.notes) == len(before.notes)
        assert "PROBE-NOTE-SENTINEL" not in _state(after), (
            "a REFUSED note capture stored its text — content retained under a refusal"
        )
    else:
        assert note.status_code == 201, _outcome([remove, note])
        assert remove.status_code == 412, _outcome([remove, note])
        assert remove.json()["error"] == "stale_write"
        assert remove.json()["experiment_id"] == eid
        assert after.get_run(run_a) is not None, "the note won, so the run must survive"
        assert after.get_run(run_a).ordinal == before.get_run(run_a).ordinal
        assert "PROBE-NOTE-SENTINEL" in _state(after)
