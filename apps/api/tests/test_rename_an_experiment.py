"""A scientist can correct what they named an experiment — and the note beside it.

WHY THIS FILE EXISTS
====================

`PATCH /api/experiments/{experiment_id}` did not exist. `title` was written exactly
once, by `POST /api/experiments`, and `source.description` was written once and then
published by NO operation at all — so a note typed into the create form could never
be read back, let alone corrected. `0001_experiments` is applied to the hosted
database, which is what turned "a typo you cannot fix" from an inconvenience into a
permanent property of a stored record.

EVERY ASSERTION HERE IS OVER HTTP, AND EVERY REFUSAL IS CHECKED AGAINST THE STORED
DOCUMENT rather than against the response body. A status code alone is satisfied by a
request FastAPI rejected before it reached any guard, which proves nothing about the
guard; so each refusal additionally asserts the record's `ETag` and its stored title
and note are exactly what they were.

WHAT THIS FILE DELIBERATELY DOES NOT COVER
==========================================

**There is no discard operation to test.** A scientist still cannot remove an
experiment they created, and that is an authorization boundary rather than an
unfinished test: see the slice report and the comment above the route. Nothing here
should be read as evidence that a delete was considered and found safe.

Nothing here connects to a database. `PGHOST` is deleted by the fixture, so the
filesystem repository is in play everywhere, exactly as in the rest of this package.
Everything is synthetic and nothing outside `tmp_path` is read or written.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.experiment_repository as repo
import isaac_api.workspace as ws

from conftest import tutorial_client

# Imported rather than re-declared, for the reason `test_lifecycle_concurrency`
# gives: a second copy of `_LockRendezvous` would be a second definition of what
# "these two requests overlapped" means, free to drift from the one
# `test_handler_concurrency` maintains.
from test_handler_concurrency import _LockRendezvous, _outcome, _race  # noqa: E402

# The three answers a person types, and the two helpers that submit and export them,
# come from the file that exists to keep the create -> export walk honest. Re-typing
# them here would be a second copy free to drift from the walk it borrows nothing for.
from test_scientist_can_finish_a_record import (  # noqa: E402
    DESCRIPTOR,
    QC,
    SERIES,
    _answer,
    _export,
    _record_on_disk,
)

TYPO_TITLE = "Ni foil calibraton"
FIXED_TITLE = "Ni foil calibration"
#: Two sentinels no code path can invent, one per concurrent writer.
TITLE_A = "renamed by writer A 4711"
TITLE_B = "renamed by writer B 4712"


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """The real app over a throwaway ORDINARY-scope workspace.

    Ordinary scope, not a worked-example session: this operation refuses inside one
    by design, and the test that proves the refusal opens its own session.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _create(client, *, title=TYPO_TITLE, description="an early note") -> tuple[str, str]:
    body = {"title": title}
    if description is not None:
        body["description"] = description
    response = client.post("/api/experiments", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"], response.headers["ETag"]


def _stored(experiment_id: str) -> tuple[str, str | None, str]:
    """`(title, note, version_token)` READ FROM THE WORKSPACE, never from a response."""
    exp = ws.load_experiment(experiment_id, session_id=None)
    assert exp is not None
    return exp.title, (exp.source or {}).get("description"), exp.version_token()


# =============================================================================
# 1. the operation exists, and the note it edits is finally readable
# =============================================================================


def test_a_typo_in_a_title_can_be_corrected(client):
    experiment_id, etag = _create(client)
    assert _stored(experiment_id)[0] == TYPO_TITLE

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE},
        headers={"If-Match": etag},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == FIXED_TITLE
    title, note, _ = _stored(experiment_id)
    assert title == FIXED_TITLE
    # THE NOTE IS UNTOUCHED. A request that named only a title must not destroy text
    # the reader never mentioned — the whole reason the request model branches on
    # `model_fields_set` rather than on the value being `None`.
    assert note == "an early note"


def test_the_note_is_published_on_the_detail_bundle(client):
    """It was WRITE-ONLY before this slice, and that is the defect being closed.

    Without a read, no client could offer to correct a note without first destroying
    whatever was there, because it would have nothing to prefill the field with.
    """
    experiment_id, _ = _create(client, description="the note as first typed")
    detail = client.get(f"/api/experiments/{experiment_id}").json()
    assert detail["description"] == "the note as first typed"
    # It is on the DETAIL bundle only. The list row is a summary and a
    # thousand-character note does not belong in it.
    row = next(
        r
        for r in client.get("/api/experiments").json()["experiments"]
        if r["id"] == experiment_id
    )
    assert "description" not in row


def test_the_note_can_be_corrected_and_cleared(client):
    experiment_id, etag = _create(client, description="wrong note")

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"description": "  the right note  "},
        headers={"If-Match": etag},
    )
    assert response.status_code == 200, response.text
    # Trimmed, exactly as the create path trims.
    assert response.json()["description"] == "the right note"
    # And the TITLE is untouched — the mirror of the assertion above.
    assert _stored(experiment_id)[0] == TYPO_TITLE

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"description": None},
        headers={"If-Match": response.headers["ETag"]},
    )
    assert response.status_code == 200, response.text
    # CLEARED means "restored to what a brand-new experiment carries", not "absent".
    # An absent `source.description` would make the record classify AMBIGUOUS by a
    # different route than a real note does, and the source block would stop being
    # named at all.
    assert response.json()["description"] == repo.NEW_EXPERIMENT_SOURCE_DESCRIPTION
    assert _stored(experiment_id)[1] == repo.NEW_EXPERIMENT_SOURCE_DESCRIPTION


def test_an_empty_note_clears_it_and_a_blank_title_does_not(client):
    """The asymmetry is the contract, and it is deliberate.

    Blank is a real choice for a note (there is a "no note" state) and is not one for
    a title (there is no nameless record). Collapsing them would either make clearing
    a note impossible or make a nameless record reachable.
    """
    experiment_id, etag = _create(client)

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"description": "   "},
        headers={"If-Match": etag},
    )
    assert response.status_code == 200, response.text
    assert response.json()["description"] == repo.NEW_EXPERIMENT_SOURCE_DESCRIPTION

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": "   "},
        headers={"If-Match": response.headers["ETag"]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_title"


def test_re_sending_the_same_values_does_not_advance_the_revision(client):
    """A rename that changed nothing must not look like a revision.

    `save_versioned`'s byte-stable no-op already guarantees this; the test exists
    because a route that wrote through `save()` instead would pass every other test
    in this file and quietly bump `rev` on every keystroke a client synced.
    """
    experiment_id, etag = _create(client)
    first = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE},
        headers={"If-Match": etag},
    )
    assert first.status_code == 200, first.text
    settled = first.headers["ETag"]

    again = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE},
        headers={"If-Match": settled},
    )
    assert again.status_code == 200, again.text
    assert again.headers["ETag"] == settled
    assert again.json()["rev"] == first.json()["rev"]


# =============================================================================
# 2. the compare-and-swap contract
# =============================================================================


@pytest.mark.parametrize(
    "header,status,error",
    [
        (None, 428, "precondition_required"),
        ('W/"x.1"', 400, "malformed_if_match"),
        ('"nosuchgeneration.0"', 412, "stale_write"),
    ],
    ids=["absent-428", "weak-400", "stale-412"],
)
def test_the_if_match_gate_refuses_and_writes_nothing(client, header, status, error):
    experiment_id, etag = _create(client)
    before = _stored(experiment_id)

    headers = {} if header is None else {"If-Match": header}
    response = client.patch(
        f"/api/experiments/{experiment_id}", json={"title": FIXED_TITLE}, headers=headers
    )
    assert response.status_code == status, response.text
    assert response.json()["error"] == error
    # The stored document, not the response body: a refusal that wrote anyway would
    # still report the refusal honestly.
    assert _stored(experiment_id) == before
    assert client.get(f"/api/experiments/{experiment_id}").headers["ETag"] == etag


def test_a_star_if_match_is_accepted_because_the_record_exists(client):
    """RFC 9110: `*` matches iff the resource exists, and we loaded it."""
    experiment_id, _ = _create(client)
    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE},
        headers={"If-Match": "*"},
    )
    assert response.status_code == 200, response.text
    assert _stored(experiment_id)[0] == FIXED_TITLE


def test_a_stale_412_echoes_the_version_that_actually_exists(client):
    """So a client can recover in ONE further request rather than looping."""
    experiment_id, etag = _create(client)
    ok = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE},
        headers={"If-Match": etag},
    )
    assert ok.status_code == 200, ok.text

    stale = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": "a third name"},
        headers={"If-Match": etag},
    )
    assert stale.status_code == 412, stale.text
    body = stale.json()
    assert body["error"] == "stale_write"
    # `expected_version` is what the CLIENT held; `current_version` is what exists.
    # Both are needed: the first tells the client which of its tabs is behind, the
    # second is what it must re-apply against.
    assert body["expected_version"] == etag.strip('"')
    assert body["current_version"] == ok.json()["version"]
    # And the header echoes the current validator, so recovery is one hop.
    assert stale.headers["ETag"] == ok.headers["ETag"]
    assert _stored(experiment_id)[0] == FIXED_TITLE


# =============================================================================
# 3. two concurrent clients, deterministically interleaved
# =============================================================================


def test_two_concurrent_renames_holding_the_same_token_leave_exactly_one_name(
    client, monkeypatch
):
    """Both writers load before either can hold the lock; exactly one wins.

    The rendezvous is what makes this deterministic rather than a one-in-a-thousand
    scheduling accident: a handler that checked its precondition OUTSIDE the lock
    would fail here on every run, because both requests would have read the same
    pre-write document and both would have passed.

    NEITHER ORDERING IS PINNED. Whichever writer acquires first wins; the invariant
    asserted holds in both orderings — one 200, one 412, and the stored title is the
    winner's, never a mixture and never the loser's.
    """
    experiment_id, etag = _create(client)
    rendezvous = _LockRendezvous(monkeypatch, experiment_id, parties=2)

    def rename(new_title):
        return lambda: client.patch(
            f"/api/experiments/{experiment_id}",
            json={"title": new_title},
            headers={"If-Match": etag},
        )

    responses = _race([rename(TITLE_A), rename(TITLE_B)])
    assert not rendezvous.timed_out, "the two requests never overlapped"
    # The seam's own half: the real lock contended on the ORDINARY-scope key. An
    # unscoped/mis-scoped acquisition would mean the two threads never serialised and
    # this test would stop pinning anything while still passing.
    assert set(rendezvous.lock_keys) == {ws._lock_key(experiment_id, None)}

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 412], _outcome(responses)
    winner = next(r for r in responses if r.status_code == 200)
    loser = next(r for r in responses if r.status_code == 412)
    assert loser.json()["error"] == "stale_write"

    title, _, token = _stored(experiment_id)
    assert title == winner.json()["title"]
    assert title in {TITLE_A, TITLE_B}
    assert f'"{token}"' == winner.headers["ETag"]
    # The loser's value reached NOTHING — not the title, not the note, not the log.
    lost = TITLE_B if title == TITLE_A else TITLE_A
    exp = ws.load_experiment(experiment_id, session_id=None)
    assert lost not in json.dumps(exp.to_state())


def test_a_concurrent_title_and_note_edit_do_not_merge_into_one_document(
    client, monkeypatch
):
    """The two fields are NOT independently mergeable, and clients need to know.

    They live in one document behind one validator, so a client renaming the title
    while another edits the note is the same one-wins race — not a pair of
    field-scoped writes that both land. Worth pinning separately from the
    same-field case because a handler that had merged them (by re-reading inside the
    lock and applying only the named field, without checking the precondition) would
    pass the same-field test and lose one of these two edits silently.

    NEITHER ORDERING IS PINNED; the invariant holds in both.
    """
    experiment_id, etag = _create(client, description="the original note")
    rendezvous = _LockRendezvous(monkeypatch, experiment_id, parties=2)

    def rename_title():
        return client.patch(
            f"/api/experiments/{experiment_id}",
            json={"title": TITLE_A},
            headers={"If-Match": etag},
        )

    def edit_note():
        return client.patch(
            f"/api/experiments/{experiment_id}",
            json={"description": "note rewritten by writer B 4712"},
            headers={"If-Match": etag},
        )

    responses = _race([rename_title, edit_note])
    assert not rendezvous.timed_out, "the two requests never overlapped"
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 412], _outcome(responses)

    title, note, _ = _stored(experiment_id)
    state = json.dumps(ws.load_experiment(experiment_id, session_id=None).to_state())
    if responses[0].status_code == 200:  # the title rename won
        assert title == TITLE_A
        assert note == "the original note"
        assert "4712" not in state
    else:  # the note edit won
        assert title == TYPO_TITLE
        assert note == "note rewritten by writer B 4712"
        assert TITLE_A not in state


# =============================================================================
# 4. body refusals — each one writes nothing
# =============================================================================


@pytest.mark.parametrize(
    "body,error",
    [
        ({}, "unrecognized_field"),
        ({"title": None}, "invalid_title"),
        ({"title": ""}, "invalid_title"),
    ],
    ids=["names-nothing", "title-null", "title-empty"],
)
def test_a_typed_refusal_writes_nothing(client, body, error):
    experiment_id, etag = _create(client)
    before = _stored(experiment_id)
    response = client.patch(
        f"/api/experiments/{experiment_id}", json=body, headers={"If-Match": etag}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == error
    assert _stored(experiment_id) == before


@pytest.mark.parametrize(
    "body",
    [
        {"title": "ok", "id": "01AAAAAAAAAAAAAAAAAAAAAAAA"},
        {"title": "ok", "record_id": "01AAAAAAAAAAAAAAAAAAAAAAAA"},
        {"title": "ok", "rev": 99},
        {"title": "ok", "draft": {}},
        {"title": 5},
        {"title": "x" * 201},
        {"description": "y" * 1001},
    ],
    ids=[
        "id",
        "record_id",
        "rev",
        "draft",
        "title-not-a-string",
        "title-too-long",
        "note-too-long",
    ],
)
def test_the_request_model_refuses_anything_it_does_not_declare(client, body):
    """`extra="forbid"` and the two `max_length` caps, over HTTP.

    The four unrecognised keys matter most: without `extra="forbid"` a client could
    name `record_id` or `rev` and this handler would silently ignore it, which reads
    to the caller as "accepted". Rejecting is what makes "this operation writes
    exactly two fields" a property of the contract rather than of the handler
    remembering not to look.
    """
    experiment_id, etag = _create(client)
    before = _stored(experiment_id)
    response = client.patch(
        f"/api/experiments/{experiment_id}", json=body, headers={"If-Match": etag}
    )
    assert response.status_code == 422, response.text
    assert _stored(experiment_id) == before


def test_the_length_caps_are_the_same_two_the_create_path_uses(client):
    """A title you can create must be a title you can rename TO.

    A stricter cap here would produce a record whose own name could not be
    re-entered — measured while writing this route: a 512-BYTE cap borrowed from the
    run-label path refuses ~171 emoji, all of which `POST /api/experiments` accepts.
    So the caps are asserted equal rather than assumed equal.
    """
    long_title = "é" * 200  # 200 characters, 400 UTF-8 bytes
    long_note = "é" * 1000
    experiment_id, etag = _create(client, title=long_title, description=long_note)

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": long_title, "description": long_note},
        headers={"If-Match": etag},
    )
    assert response.status_code == 200, response.text


def test_the_provenance_marker_is_refused_as_a_note(client):
    """A record a person created must not wear this application's own marker.

    `ws.classify_experiment` reads that exact string as proof that this application
    generated the record from its own committed fixtures, and `managed_legacy` is the
    one bucket `ws.remove_experiment` will delete.

    DEFENCE IN DEPTH, and the test says so rather than implying a live exposure:
    `remove_experiment`'s only caller is the demo reset, which refuses without a
    tutorial session and addresses that session's scope alone, so no
    ordinary-workspace record reaches it today whatever its note says.
    """
    experiment_id, etag = _create(client)
    before = _stored(experiment_id)
    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"description": ws.MANAGED_SOURCE_DESCRIPTION},
        headers={"If-Match": etag},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "reserved_description"
    assert _stored(experiment_id) == before
    assert ws.classify_experiment(
        ws.load_experiment(experiment_id, session_id=None)
    ) == ws.AMBIGUOUS


def test_an_unknown_id_is_not_found_rather_than_created(client):
    response = client.patch(
        "/api/experiments/01NOSUCHRECORDIDAAAAAAAAAA",
        json={"title": FIXED_TITLE},
        headers={"If-Match": "*"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


# =============================================================================
# 5. the worked-example session is not renameable
# =============================================================================


def test_it_refuses_inside_a_worked_example_session_and_changes_nothing(
    tmp_path, monkeypatch
):
    """The five built-in examples are fixed teaching material.

    Renaming one would make the tutorial's own narrative disagree with the screen,
    and `POST /api/demo/reset` would revert it — a write reported as applied and then
    undone by an unrelated act.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    client = tutorial_client(create_app(), raise_server_exceptions=False)
    seeded = client.get("/api/experiments").json()["experiments"][0]

    response = client.patch(
        f"/api/experiments/{seeded['id']}",
        json={"title": "renamed example"},
        headers={"If-Match": "*"},
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "ordinary_scope_required"
    assert body["header"] == "X-Isaac-Tutorial-Session"
    after = client.get(f"/api/experiments/{seeded['id']}").json()
    assert after["title"] == seeded["title"]


# =============================================================================
# 6. a rename is not a scientific change
# =============================================================================


def test_renaming_an_exported_record_leaves_its_artifact_current(client):
    """The honesty property, and it is the reason this route is safe to ship.

    A record is created, answered and EXPORTED through the public API, and only then
    renamed. `dependencies.artifact_state` compares the WRITTEN record against a
    freshly composed draft, so a field reaching no exported record cannot stale one —
    and neither `title` nor `source.description` reaches one
    (`src/isaac_records/export.py` names neither).

    IF EITHER EVER STARTS REACHING AN EXPORTED RECORD, THIS GOES RED, which is
    exactly when someone needs to be told: the reader would otherwise be shown
    "the record changed after export; regenerate it" for a typo fix, and the memory
    index records that this `stale` state was previously not UI-reachable at all. A
    rename is the first mutation on an exported record a scientist can reach, so it
    is the first thing that could produce a false one.

    The three answers and the two helpers are IMPORTED from
    `test_scientist_can_finish_a_record` rather than re-typed: they are values a
    person writes out, and a second copy would be free to drift from the walk that
    file exists to protect.
    """
    experiment_id, _ = _create(client)
    filled = _answer(client, experiment_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    assert filled.status_code == 200, filled.text
    exported = _export(client, experiment_id)
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True, exported.json()

    before = client.get(f"/api/experiments/{experiment_id}").json()
    assert before["artifact"]["state"] == "current", before["artifact"]
    record_on_disk = _record_on_disk(experiment_id)

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE, "description": "renamed after export"},
        headers={"If-Match": f'"{before["version"]}"'},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == FIXED_TITLE
    # THE WHOLE POINT: still `current`, so nobody is asked to re-export a typo fix.
    assert response.json()["artifact"]["state"] == "current", response.json()["artifact"]
    # And the exported record on disk is byte-identical — the rename reached it in no
    # way at all, not even through a field the freshness check happens to ignore.
    assert _record_on_disk(experiment_id) == record_on_disk
    assert FIXED_TITLE not in json.dumps(record_on_disk)


def test_an_unexported_record_stays_none_rather_than_inventing_an_export(client):
    """The control for the test above: `none` must not become `stale` either."""
    experiment_id, etag = _create(client)
    assert client.get(f"/api/experiments/{experiment_id}").json()["artifact"]["state"] == "none"
    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE},
        headers={"If-Match": etag},
    )
    assert response.status_code == 200, response.text
    assert response.json()["artifact"]["state"] == "none"


def test_a_rename_touches_no_draft_field_and_no_pending_question(client):
    """It is not a second way to edit the science, and the counts prove it."""
    experiment_id, etag = _create(client)
    before = client.get(f"/api/experiments/{experiment_id}").json()

    response = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": FIXED_TITLE, "description": "a note"},
        headers={"If-Match": etag},
    )
    assert response.status_code == 200, response.text
    after = response.json()

    for key in (
        "pending_count",
        "evidenced_field_count",
        "draft_ok",
        "exported",
        "record_id",
        "status",
    ):
        assert after[key] == before[key], key
    exp = ws.load_experiment(experiment_id, session_id=None)
    assert exp.draft == repo.blank_draft()
    assert exp.answer_log == []


def test_the_operation_is_published_in_the_openapi_document(client):
    """A route the contract does not describe is a route no client can find."""
    spec = client.get("/api/openapi").json()
    operation = spec["paths"]["/api/experiments/{experiment_id}"]["patch"]
    assert operation["summary"] == "Rename an Experiment"
    assert "If-Match" in operation["description"]
    # The 409 is DECLARED, not merely implemented: a client that cannot see it will
    # render a worked-example refusal as an unknown error.
    assert "409" in operation["responses"]


# =============================================================================
# 7. the guard that proves the concurrency seam is not vacuous
# =============================================================================


def test_the_rendezvous_actually_holds_both_requests(client, monkeypatch):
    """Guards the guard.

    If the seam silently stopped rendezvousing, every concurrency assertion above
    would still pass — sequentially — while pinning nothing. This asserts the
    overlap positively: the second arrival cannot proceed until the first has
    arrived, so a thread started alone must time out.
    """
    experiment_id, etag = _create(client)
    rendezvous = _LockRendezvous(monkeypatch, experiment_id, parties=2)

    result: list = []

    def lone():
        result.append(
            client.patch(
                f"/api/experiments/{experiment_id}",
                json={"title": TITLE_A},
                headers={"If-Match": etag},
            ).status_code
        )

    thread = threading.Thread(target=lone, name="lone-writer")
    thread.start()
    thread.join(timeout=1.0)
    assert thread.is_alive(), (
        "a single request reached the lock without waiting for a second party, so the "
        "rendezvous is not holding anything and the concurrency tests above prove "
        "nothing about interleaving"
    )
    # Release it by sending the second party, then let both settle.
    client.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": TITLE_B},
        headers={"If-Match": etag},
    )
    thread.join(timeout=30.0)
    assert not thread.is_alive()
    assert result and result[0] in (200, 412)
