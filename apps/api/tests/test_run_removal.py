"""``POST /api/experiments/{id}/runs/{run_id}/remove`` — taking a run back out.

WHAT WAS MISSING, AND WHY IT IS A REMOVAL RATHER THAN A DELETE
==============================================================
The Run API could add, read, edit, override and check a run. It could not take one
out. A run created by a mis-click was permanent, and the only way past it was to
abandon the record. This operation closes that, and it is deliberately NARROWER
than the gap: it removes a run that has never been exported, and refuses one that
has.

THE ONE THING THIS SUITE EXISTS TO PROTECT
==========================================
**No path through this operation can damage history.** Three separate things are
history here and they are stored in three different places:

  * the OFFICIAL RECORD and its evidence sidecar — files under the experiment's
    ``records/`` directory, written by an export and never rewritten;
  * the REVISION SNAPSHOT — ``isaac_experiment_revisions`` and
    ``isaac_run_revisions``, append-only rows capturing every run as it stood at
    submission;
  * the SUBMISSION — ``isaac_submissions`` and ``isaac_submission_runs``, the
    attributable declaration a person made.

The second and third survive by construction: ``submission_store`` issues no
``UPDATE`` and no ``DELETE``, and ``0003_revisions`` deliberately makes
``isaac_run_revisions.run_id`` **not** a foreign key to ``isaac_runs`` precisely so
history outlives a run that no longer exists. Both of those are verified here
rather than assumed.

**THE FIRST DOES NOT SURVIVE BY CONSTRUCTION, AND THAT IS WHY THIS OPERATION
REFUSES AN EXPORTED RUN.** ``_prune_orphan_artifacts`` deletes any record pair in
the experiment's ``records/`` directory that no CURRENT unit claims — its own
docstring says a run removed from the experiment "cannot leave its record behind",
which is the same sentence read from the other side. It runs on the success path of
any later export. So "remove an exported run, then export again for any other
reason" is a path that DELETES A PUBLISHED OFFICIAL RECORD, at a distance, with no
confirmation and no mention of it in the response. That path is not worked around
here and it is not widened: the removal refuses an exported run with ``409
run_exported`` and writes nothing, so it never reaches the prune. Every run that has
appeared in a submitted revision is an exported run — a submission materialises
every unit before it records anything — which is what puts a submitted record out of
this operation's reach.

TWO DECISIONS THIS SUITE PINS BECAUSE EITHER COULD BE REVERSED SILENTLY
======================================================================
* **ORDINALS ARE NOT COMPACTED.** Remove the second of three runs and the survivors
  read 1 and 3. Four reasons live on ``Experiment.remove_run``; the two that a test
  can see are pinned below — a surviving run's ``ETag`` does not move, and a run
  added afterwards does not re-issue a number an earlier sibling once had.
* **A REPEATED REMOVAL IS 404, NOT A SECOND 200.** Every other run operation
  answers 404 for an id this record does not hold, and a 200 would require claiming
  a run "was removed" for an id that may never have existed here.

Every fixture is built from the committed synthetic seed drafts. Nothing here reads
real data, nothing here connects to a database, and no test in this file writes a
scientific value it did not read out of the committed seed.
"""

from __future__ import annotations

import copy
import json

import pytest

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.identity as identity
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws
from isaac_records.models import field_value, user_confirmation

from conftest import client_ws, tutorial_client
from submission_fake import FakeSubmissionConnection, fake_store
from test_experiment_repository import FakeConnection, _connector, _env

EXPERIMENT_ID = "01RUNREMOVALFIXTURE000001"
ACTOR = "ada.lovelace"


# =============================================================================
# fixtures
# =============================================================================


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A private ORDINARY-scope workspace with no database configured.

    Ordinary rather than worked-example scope, because that is the scope a
    scientist's record lives in and the only one a submission or a durable write is
    ever reachable from. The worked-example half has its own section at the end.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def wired(monkeypatch, db):
    """Point the submit route's store factory at the connection double."""
    store = fake_store(db)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    return store


@pytest.fixture()
def armed(workspace, monkeypatch):
    """A deployment that CAN attribute a submission: the fixture verifier."""
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _client():
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _make(experiment_id: str = EXPERIMENT_ID, *, runs: tuple[str, ...] = ()):
    """An export-ready ordinary-scope experiment carrying ``runs``.

    The run drafts are a deep copy of the experiment's own committed seed draft, so
    every unit really is exportable — which is what makes a submission reachable in
    the history tests below. Nothing here composes a scientific value.
    """
    exp = ws.create_experiment(
        "Run removal fixture",
        {"kind": "synthetic"},
        copy.deepcopy(ws._full_draft()),
        id=experiment_id,
    )
    run_draft = copy.deepcopy(exp.draft)
    for label in runs:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


def _etag(client, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, run_id: str, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _remove(
    client,
    run_id: str,
    experiment_id: str = EXPERIMENT_ID,
    *,
    if_match=...,
    body=...,
):
    """The removal request. ``if_match=None`` omits the header entirely."""
    headers = {}
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    if tag is not None:
        headers["If-Match"] = tag
    payload = {"confirmed_by_user": True} if body is ... else body
    return client.post(
        f"/api/experiments/{experiment_id}/runs/{run_id}/remove",
        json=payload,
        headers=headers,
    )


def _run_ids(experiment_id: str = EXPERIMENT_ID) -> list[str]:
    """The ids the STORE holds, in canonical order — never the response's copy."""
    return [run.id for run in ws.load_experiment(experiment_id).sorted_runs()]


def _ordinals(experiment_id: str = EXPERIMENT_ID) -> list[int]:
    return [run.ordinal for run in ws.load_experiment(experiment_id).sorted_runs()]


def _artifacts(exp) -> set[str]:
    records_dir = exp.records_dir
    if not records_dir.is_dir():
        return set()
    return {p.name for p in records_dir.iterdir()}


def _submit(client, experiment_id: str = EXPERIMENT_ID, *, if_match=...):
    headers = {}
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    if tag is not None:
        headers["If-Match"] = tag
    return client.post(f"/api/experiments/{experiment_id}/submit", headers=headers)


# =============================================================================
# 1. the ordinary removal — first, last, middle
# =============================================================================


def test_removing_the_FIRST_run_leaves_the_others_and_reports_what_went(workspace):
    _make(runs=("run A", "run B", "run C"))
    before = _run_ids()
    client = _client()

    response = _remove(client, before[0])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["removed_run_id"] == before[0]
    assert body["removed_run_label"] == "run A"
    assert body["removed_run_ordinal"] == 1
    assert body["remaining_run_count"] == 2
    assert body["ordinals_compacted"] is False
    assert _run_ids() == before[1:]
    # The response's version really is the record's new one, and the header agrees.
    exp = ws.load_experiment(EXPERIMENT_ID)
    assert body["experiment_version"] == exp.version_token()
    assert response.headers["ETag"] == exp.etag()


def test_removing_the_LAST_run_of_a_record_leaves_a_record_with_no_runs(workspace):
    """Zero runs is a real state, not an error: it is what every record starts in.

    The record itself survives, keeps its own draft, and is readable — a removal is
    never a way to delete a record.
    """
    _make(runs=("only run",))
    only = _run_ids()[0]
    client = _client()
    before_draft = copy.deepcopy(ws.load_experiment(EXPERIMENT_ID).draft)

    response = _remove(client, only)

    assert response.status_code == 200, response.text
    assert response.json()["remaining_run_count"] == 0
    assert _run_ids() == []
    listed = client.get(f"/api/experiments/{EXPERIMENT_ID}/runs")
    assert listed.status_code == 200
    assert listed.json()["runs"] == [] and listed.json()["total"] == 0
    assert client.get(f"/api/experiments/{EXPERIMENT_ID}").status_code == 200
    # The record's OWN draft is untouched by removing every run: the same field map,
    # not merely a non-empty one.
    assert ws.load_experiment(EXPERIMENT_ID).draft == before_draft


def test_removing_a_MIDDLE_run_leaves_the_survivors_BYTE_IDENTICAL(workspace):
    """The isolation property, asserted the strongest available way.

    Not "the other runs are still there" — their whole persisted documents, their
    revisions and their per-run ``ETag``s are unchanged. That is what makes it safe
    for a second reader to be editing another run of the same record while this one
    is removed: their held ``If-Match`` still matches.

    MUTATION-CHECKED: compacting ordinals in ``Experiment.remove_run`` (rewriting
    every survivor's ``ordinal`` to its index + 1) turns this RED on the ``to_state``
    comparison and on the ``ETag`` comparison, which is exactly the damage the
    no-compaction decision avoids.
    """
    _make(runs=("run A", "run B", "run C"))
    ids = _run_ids()
    client = _client()
    before = {
        run.id: (run.to_state(), run.version_token())
        for run in ws.load_experiment(EXPERIMENT_ID).sorted_runs()
    }
    before_etags = {rid: _run_etag(client, rid) for rid in ids}

    assert _remove(client, ids[1]).status_code == 200

    after = {
        run.id: (run.to_state(), run.version_token())
        for run in ws.load_experiment(EXPERIMENT_ID).sorted_runs()
    }
    assert set(after) == {ids[0], ids[2]}
    for rid in (ids[0], ids[2]):
        assert after[rid] == before[rid], f"{rid} moved when a sibling was removed"
        assert _run_etag(client, rid) == before_etags[rid]


# =============================================================================
# 2. ordinals are NOT compacted, and the response says so
# =============================================================================


def test_the_survivors_keep_their_numbers_and_the_response_states_that(workspace):
    _make(runs=("run A", "run B", "run C"))
    ids = _run_ids()
    assert _ordinals() == [1, 2, 3]

    body = _remove(_client(), ids[1]).json()

    assert body["ordinals_compacted"] is False
    # 1 and 3 — the gap is the point, and it is observable through the list route.
    assert _ordinals() == [1, 3]
    listed = _client().get(f"/api/experiments/{EXPERIMENT_ID}/runs").json()
    assert [run["ordinal"] for run in listed["runs"]] == [1, 3]


def test_a_run_added_after_a_removal_never_collides_with_a_surviving_number(workspace):
    """The reason ``next_ordinal`` is ``max + 1`` rather than ``len + 1``.

    Remove the MIDDLE of three and add one: ``len + 1`` numbering would hand out 3,
    which the third run still holds, so two runs would tie on the key
    ``sorted_runs`` orders by and their order would depend on their created stamps.
    ``max + 1`` gives 4.

    **THE STRONGER CLAIM IS FALSE AND IS NOT MADE HERE.** A number is not retired by
    a removal: remove the HIGHEST-numbered run and the next run created takes that
    same number back, because ``max`` is taken over the runs that survive. The
    second half of this test states that outcome rather than leaving it to be
    discovered — it is the honest limit of "ordinals are not renumbered", and the
    property that actually holds is the one about collisions.
    """
    _make(runs=("run A", "run B", "run C"))
    ids = _run_ids()
    client = _client()
    assert _remove(client, ids[1]).status_code == 200

    created = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/runs",
        json={},
        headers={"If-Match": _etag(client)},
    )
    assert created.status_code == 201, created.text
    assert created.json()["run"]["ordinal"] == 4
    assert _ordinals() == [1, 3, 4]

    # The limit, stated: removing the top run frees its number for reuse.
    top = _run_ids()[-1]
    assert _remove(client, top).status_code == 200
    reused = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/runs",
        json={},
        headers={"If-Match": _etag(client)},
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["run"]["ordinal"] == 4


# =============================================================================
# 3. the concurrency contract — and it is checked inside the mutation's lock
# =============================================================================


def test_a_stale_record_if_match_is_412_AND_WRITES_NOTHING(workspace):
    """The precondition and the mutation are in ONE critical section.

    The stale token is taken BEFORE another write moves the record, which is the
    only shape in which a check performed outside the lock can pass and then mutate
    a document that has since changed.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    stale = _etag(client)
    # Something else moves the record: a second run is added.
    assert (
        client.post(
            f"/api/experiments/{EXPERIMENT_ID}/runs",
            json={"label": "run C"},
            headers={"If-Match": stale},
        ).status_code
        == 201
    )
    before = _run_ids()
    before_version = ws.load_experiment(EXPERIMENT_ID).version_token()

    response = _remove(client, ids[0], if_match=stale)

    assert response.status_code == 412, response.text
    assert response.json()["error"] == "stale_write"
    # NOTHING was written: the run list and the record's own version are unmoved.
    assert _run_ids() == before
    assert ws.load_experiment(EXPERIMENT_ID).version_token() == before_version


def test_omitting_if_match_is_428_and_removes_nothing(workspace):
    _make(runs=("run A",))
    only = _run_ids()[0]
    response = _remove(_client(), only, if_match=None)
    assert response.status_code == 428, response.text
    assert response.json() == {
        "error": "precondition_required",
        "experiment_id": EXPERIMENT_ID,
    }
    assert _run_ids() == [only]


def test_a_malformed_if_match_is_400_and_removes_nothing(workspace):
    _make(runs=("run A",))
    only = _run_ids()[0]
    response = _remove(_client(), only, if_match='W/"weak"')
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "malformed_if_match"
    assert _run_ids() == [only]


def test_the_RUNS_own_etag_is_not_accepted_it_is_the_RECORDS(workspace):
    """The trap this API's own notes warn about, from the removal's side.

    A run lives inside the record's document, so removing one rewrites the RECORD.
    Sending the run's token is a 412 rather than a silent success — and the run is
    still there afterwards.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    response = _remove(client, ids[0], if_match=_run_etag(client, ids[0]))
    assert response.status_code == 412, response.text
    assert _run_ids() == ids


def test_confirmation_is_required_and_an_unconfirmed_request_removes_nothing(workspace):
    _make(runs=("run A",))
    only = _run_ids()[0]
    for payload in ({}, {"confirmed_by_user": False}, {"confirmed_by_user": "yes"}):
        response = _remove(_client(), only, body=payload)
        assert response.status_code == 422, (payload, response.text)
        assert response.json()["error"] == "confirmation_required"
        assert _run_ids() == [only]


# =============================================================================
# 4. edit / removal races, in both orders
# =============================================================================


def test_EDIT_THEN_REMOVE_with_the_pre_edit_record_token_is_412(workspace):
    """An edit to ONE run moves the RECORD, because a run is part of its document.

    So a removal holding the pre-edit record token is refused. This is the honest
    outcome rather than an inconvenience: the reader's view of the record predates a
    change to it, and this API's whole concurrency contract is that such a writer
    re-reads rather than overwrites.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    stale = _etag(client)

    edited = client.patch(
        f"/api/experiments/{EXPERIMENT_ID}/runs/{ids[1]}",
        json={"confirmed_by_user": True, "label": "run B, renamed"},
        headers={"If-Match": _run_etag(client, ids[1])},
    )
    assert edited.status_code == 200, edited.text

    response = _remove(client, ids[0], if_match=stale)
    assert response.status_code == 412, response.text
    assert _run_ids() == ids
    # And the edit that won is intact.
    assert ws.load_experiment(EXPERIMENT_ID).get_run(ids[1]).label == "run B, renamed"


def test_REMOVE_THEN_EDIT_the_removed_run_is_a_404_not_a_500(workspace):
    """The other order, which is the one a browser actually produces.

    A card's autosave holds the run's own token and fires after the reader removed
    the run in another tab. The run is gone, so the edit is a ``run_not_found`` 404 —
    addressed to the RUN, never to the record, which still exists and is readable.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    run_token = _run_etag(client, ids[0])
    assert _remove(client, ids[0]).status_code == 200

    edited = client.patch(
        f"/api/experiments/{EXPERIMENT_ID}/runs/{ids[0]}",
        json={"confirmed_by_user": True, "label": "too late"},
        headers={"If-Match": run_token},
    )
    assert edited.status_code == 404, edited.text
    body = edited.json()
    assert body["error"] == "run_not_found"
    assert body["experiment_id"] == EXPERIMENT_ID and body["id"] == ids[0]
    assert client.get(f"/api/experiments/{EXPERIMENT_ID}").status_code == 200


def test_TWO_REMOVALS_holding_the_same_token_leave_the_second_run_alone(workspace):
    """Two runs, two removals, one token: the second is refused, not applied.

    This is the shape a double-click on two cards produces. The first removal moves
    the record, so the second one's token is stale — and the run it named is still
    there.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    token = _etag(client)

    assert _remove(client, ids[0], if_match=token).status_code == 200
    second = _remove(client, ids[1], if_match=token)

    assert second.status_code == 412, second.text
    assert _run_ids() == [ids[1]]


# =============================================================================
# 5. idempotency / retry safety
# =============================================================================


def test_REPEATING_the_removal_is_a_404_and_never_a_500(workspace):
    """The decision: a repeat is 404, not a second 200.

    Both the retry-with-a-fresh-token case and the retry-with-the-original-token
    case are exercised, because they are different requests and only one of them is
    obviously a 404. Neither is a 500, and neither changes anything.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    original_token = _etag(client)
    assert _remove(client, ids[0], if_match=original_token).status_code == 200
    after = _run_ids()

    # (a) the retry a client makes after re-reading the record.
    fresh = _remove(client, ids[0])
    assert fresh.status_code == 404, fresh.text
    assert fresh.json()["error"] == "run_not_found"

    # (b) the retry a client makes when the FIRST response never arrived, so it
    # still holds the token from before. The 404 is checked before the
    # precondition, so it is told the truth about the run rather than being sent to
    # refresh a version in order to remove something that is already gone.
    replay = _remove(client, ids[0], if_match=original_token)
    assert replay.status_code == 404, replay.text
    assert replay.json()["error"] == "run_not_found"

    assert _run_ids() == after


def test_removing_a_run_this_record_does_not_have_is_a_run_404(workspace):
    """Never an experiment 404: the record exists and was read successfully."""
    _make(runs=("run A",))
    response = _remove(_client(), "01NOSUCHRUNIDATALL00000001")
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "run_not_found"
    assert body["experiment_id"] == EXPERIMENT_ID
    assert body["id"] == "01NOSUCHRUNIDATALL00000001"
    assert len(_run_ids()) == 1


def test_removing_a_run_of_an_experiment_that_does_not_exist_is_an_experiment_404(
    workspace,
):
    response = _remove(
        _client(), "01ANYRUN00000000000000001", "01NOSUCHRECORD0000000001", if_match="*"
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


# =============================================================================
# 6. searching and filtering follow the removal
# =============================================================================


def test_a_removal_moves_BOTH_counts_the_list_route_reports(workspace):
    """``total`` is what the record HAS; ``matched`` is what the query selects.

    A removal has to move both, and a search that no longer matches anything must
    report an empty page over a record that still has runs — never "this record has
    no runs", which is the conflation the count line on screen exists to prevent.
    """
    _make(runs=("alpha", "beta", "gamma"))
    ids = _run_ids()
    client = _client()
    base = f"/api/experiments/{EXPERIMENT_ID}/runs"

    before = client.get(f"{base}?q=beta").json()
    assert (before["total"], before["matched"]) == (3, 1)

    assert _remove(client, ids[1]).status_code == 200

    after = client.get(f"{base}?q=beta").json()
    assert (after["total"], after["matched"], after["runs"]) == (2, 0, [])
    unfiltered = client.get(base).json()
    assert (unfiltered["total"], unfiltered["matched"]) == (2, 2)


def test_a_removal_does_not_disturb_a_paged_read_of_the_survivors(workspace):
    """Paging is unaffected in the one way this operation could break it: the ids
    that remain are exactly the ids that remain, in canonical order, across pages."""
    _make(runs=tuple(f"run {n}" for n in range(1, 6)))
    ids = _run_ids()
    client = _client()
    assert _remove(client, ids[2]).status_code == 200

    base = f"/api/experiments/{EXPERIMENT_ID}/runs"
    first = client.get(f"{base}?limit=2&offset=0").json()
    second = client.get(f"{base}?limit=2&offset=2").json()
    assert [r["id"] for r in first["runs"]] + [r["id"] for r in second["runs"]] == [
        ids[0],
        ids[1],
        ids[3],
        ids[4],
    ]
    assert first["total"] == 4


# =============================================================================
# 7. what goes with the run, and what does not
# =============================================================================


def test_the_runs_own_overrides_go_with_it_and_the_records_value_stays(workspace):
    """An override is the run's own displacement of a record-level value.

    It is stored on the run, so it goes when the run goes — and the record's value,
    which was never copied down, is exactly where it was.
    """
    _make(runs=("run A",))
    run_id = _run_ids()[0]
    client = _client()
    address = ws.field_address("sample.sample_form")
    # A VALID DRAFT ENVELOPE, and the evidence is a user confirmation because that
    # is literally what it is: a person stating this run's value at the keyboard.
    # Nothing here manufactures observed evidence for a value nobody observed.
    recorded = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/runs/{run_id}/overrides",
        json={
            "confirmed_by_user": True,
            "address": address,
            "payload": field_value(
                "powder",
                status="verified",
                evidence=[
                    user_confirmation(
                        "Value for sample.sample_form on this run?",
                        "powder",
                        "2026-01-01T00:00:00Z",
                    )
                ],
            ),
        },
        headers={"If-Match": _run_etag(client, run_id)},
    )
    assert recorded.status_code == 200, recorded.text
    record_value = copy.deepcopy(
        ws.load_experiment(EXPERIMENT_ID).draft["fields"]["sample.sample_form"]
    )

    assert _remove(client, run_id).status_code == 200

    exp = ws.load_experiment(EXPERIMENT_ID)
    assert exp.runs == []
    assert exp.draft["fields"]["sample.sample_form"] == record_value


def test_the_asset_LIBRARY_survives_and_the_removed_runs_association_is_named(
    workspace,
):
    """A removal names the references that went with the run and keeps the library.

    An asset entry can be cited by other runs and by the record itself, so removing
    one run must not remove the entry — only this run's association with it. The
    response names the ids rather than counting them, for the reason the asset
    removal names its runs: a reader told only "removed" cannot tell which files
    this measurement stopped citing.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    created = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "synthetic_scan",
            "content_role": "raw_data",
            "uri": "synthetic://example/raw/scan.h5",
            # Supplied, never derived: this application does not read the file, so
            # a digest it did not receive is one it must not invent. `a1` repeated
            # is unmistakably a fixture.
            "sha256": "a1" * 32,
            "run_ids": ids,
        },
        headers={"If-Match": _etag(client)},
    )
    assert created.status_code == 201, created.text
    asset_id = created.json()["asset"]["asset_id"]

    # WHAT THE REMOVED RUN ACTUALLY CARRIED, read off the run before it goes — the
    # seed draft each run was built from already cites files of its own, so an
    # assertion naming only the asset this test added would be checking a subset and
    # would pass while the rest went unreported.
    before_library = _library_ids(client)
    doomed = _run_asset_ids(EXPERIMENT_ID, ids[0])
    assert asset_id in doomed and len(doomed) > 1, doomed

    response = _remove(client, ids[0])

    assert response.status_code == 200, response.text
    assert response.json()["asset_references_dropped"] == doomed
    # The library is untouched — every entry, in order...
    assert _library_ids(client) == before_library
    assert asset_id in before_library
    # ...and the SURVIVING run still cites the asset, so nothing was detached
    # wholesale from the record on the way out.
    assert asset_id in _run_asset_ids(EXPERIMENT_ID, ids[1])


def _run_asset_ids(experiment_id: str, run_id: str) -> list[str]:
    from isaac_api import assets as _assets

    run = ws.load_experiment(experiment_id).get_run(run_id)
    return [item["asset_id"] for item in _assets.run_assets(run)]


def _library_ids(client, experiment_id: str = EXPERIMENT_ID) -> list[str]:
    listed = client.get(f"/api/experiments/{experiment_id}/assets")
    assert listed.status_code == 200, listed.text
    return [entry["asset_id"] for entry in listed.json()["assets"]]


# =============================================================================
# 8. HISTORY — the constraint that matters most
# =============================================================================


def test_an_EXPORTED_run_cannot_be_removed_and_its_record_stays_on_disk(workspace):
    """THE HISTORY GUARD, exercised on the artifact it protects.

    A run with a ``record_id`` has a written official record and evidence sidecar.
    The removal refuses it — and the assertion that matters is the second one: the
    files are still there, byte for byte, after the refusal.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    exported = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/export", headers={"If-Match": _etag(client)}
    )
    assert exported.status_code == 200, exported.text
    exp = ws.load_experiment(EXPERIMENT_ID)
    before = {
        name: (exp.records_dir / name).read_bytes() for name in _artifacts(exp)
    }
    assert before, "the fixture did not actually export anything"

    response = _remove(client, ids[0])

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "run_exported"
    assert body["id"] == ids[0]
    assert body["record_id"] == exp.get_run(ids[0]).record_id
    assert "Nothing was written" in body["message"]
    # The run is still in the record, and every published file is untouched.
    assert _run_ids() == ids
    after_exp = ws.load_experiment(EXPERIMENT_ID)
    assert {
        name: (after_exp.records_dir / name).read_bytes()
        for name in _artifacts(after_exp)
    } == before


def test_the_exported_refusal_precedes_the_precondition_so_it_is_never_a_412(workspace):
    """A caller holding a stale token is told the RIGHT thing.

    Refreshing and retrying would not help — the run is exported and will still be
    exported after the refresh — so a 412 here would send a reader round a loop that
    cannot terminate. The 409 is checked first, deliberately.
    """
    _make(runs=("run A",))
    only = _run_ids()[0]
    client = _client()
    assert (
        client.post(
            f"/api/experiments/{EXPERIMENT_ID}/export",
            headers={"If-Match": _etag(client)},
        ).status_code
        == 200
    )
    response = _remove(client, only, if_match='"not-the-current-version"')
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "run_exported"


def test_a_run_ADDED_AND_REMOVED_BEFORE_the_first_submission_leaves_no_trace(
    armed, wired, db
):
    """The ordinary case: a mis-clicked run, removed, then the record is submitted.

    The submission must describe the record as it IS — two units, not three — and no
    revision row may name a run that was removed before the snapshot was taken.
    """
    _make(runs=("run A", "run B"))
    kept = _run_ids()
    client = _client()
    created = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/runs",
        json={"label": "a mistake"},
        headers={"If-Match": _etag(client)},
    )
    assert created.status_code == 201, created.text
    mistake = created.json()["run"]["id"]
    assert _remove(client, mistake).status_code == 200

    response = _submit(client)

    assert response.status_code == 200, response.text
    assert response.json()["unit_count"] == 2
    assert {row["run_id"] for row in db.run_revisions} == set(kept)
    assert {row["run_id"] for row in db.submission_runs} == set(kept)
    assert mistake not in json.dumps(db.revisions)


def test_after_a_submission_EVERY_captured_run_refuses_removal(armed, wired, db):
    """The strongest form of the history guarantee this operation can offer.

    Not "the run we happened to try is protected" — every run the submission
    captured is, and the set is read out of the recorded revision rows rather than
    restated. A submission materialises every unit, so every captured run carries a
    ``record_id``, and that is exactly the condition the removal refuses on.
    """
    _make(runs=("run A", "run B"))
    client = _client()
    assert _submit(client).status_code == 200
    captured = {row["run_id"] for row in db.run_revisions}
    assert captured == set(_run_ids())

    for run_id in sorted(captured):
        response = _remove(client, run_id)
        assert response.status_code == 409, (run_id, response.text)
        assert response.json()["error"] == "run_exported"

    assert set(_run_ids()) == captured


def test_a_run_removed_AFTER_an_earlier_submission_leaves_the_history_INTACT(
    armed, wired, db
):
    """THE CASE THE WHOLE SLICE IS JUDGED ON, asserted positively.

    Submit two runs. Add a third. Remove the third. Then read back — from the rows
    and from the filesystem — that every piece of history is still there and still
    readable:

      * the revision snapshot, including each captured run's own document and the
        ordinal it held;
      * the official records that submission published, byte for byte;
      * the submission itself, with its subject, its basis and its server-assigned
        time.

    Byte-comparisons and full-document comparisons rather than counts, because a
    count survives a rewrite and this is a claim about content.
    """
    _make(runs=("run A", "run B"))
    client = _client()
    assert _submit(client).status_code == 200

    submitted_exp = ws.load_experiment(EXPERIMENT_ID)
    records_before = {
        name: (submitted_exp.records_dir / name).read_bytes()
        for name in _artifacts(submitted_exp)
    }
    assert len(records_before) == 4, records_before  # two records, two sidecars
    revisions_before = copy.deepcopy(db.revisions)
    run_revisions_before = copy.deepcopy(db.run_revisions)
    submissions_before = copy.deepcopy(db.submissions)
    submission_runs_before = copy.deepcopy(db.submission_runs)

    created = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/runs",
        json={"label": "added after the submission"},
        headers={"If-Match": _etag(client)},
    )
    assert created.status_code == 201, created.text
    later_run = created.json()["run"]["id"]

    removal = _remove(client, later_run)
    assert removal.status_code == 200, removal.text

    # 1. THE REVISION SNAPSHOT. Whole rows, so a rewritten `state` document or a
    #    renumbered ordinal fails here rather than being absorbed by a count.
    assert db.revisions == revisions_before
    assert db.run_revisions == run_revisions_before
    for row in db.run_revisions:
        stored = json.loads(row["state"]) if isinstance(row["state"], str) else row["state"]
        assert stored["id"] == row["run_id"]
        assert stored["ordinal"] == row["ordinal"]
        assert stored["record_id"] == row["run_id"], "a captured run lost its record"

    # 2. THE PUBLISHED RECORDS, byte for byte, still on disk and still parseable.
    after_exp = ws.load_experiment(EXPERIMENT_ID)
    records_after = {
        name: (after_exp.records_dir / name).read_bytes()
        for name in _artifacts(after_exp)
    }
    assert records_after == records_before
    for name in records_after:
        assert json.loads(records_after[name].decode()), name

    # 3. THE SUBMISSION HISTORY, including who declared it and on what basis.
    assert db.submissions == submissions_before
    assert db.submission_runs == submission_runs_before
    assert db.submissions[0]["subject"] == ACTOR
    assert db.submissions[0]["trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE

    # And the removal really did happen — otherwise every assertion above is
    # vacuous.
    assert later_run not in _run_ids()


def test_the_run_revision_rows_do_not_depend_on_a_run_row_existing(workspace):
    """``0003_revisions`` makes ``isaac_run_revisions.run_id`` NOT a foreign key.

    That is the schema-level reason history outlives a run, and this reads the
    committed migration rather than trusting a comment about it. It is a statement
    about the SQL this repository ships; whether PostgreSQL agrees is answered by
    CI's ``postgres-migration`` job against a real engine.
    """
    from pathlib import Path

    sql = (
        Path(repo.__file__).resolve().parent / "migrations" / "0003_revisions.sql"
    ).read_text()
    start = sql.index("CREATE TABLE IF NOT EXISTS isaac_run_revisions (")
    table = sql[start : sql.index("\n)", start)]
    assert "run_id" in table
    assert "REFERENCES isaac_runs" not in table
    assert "ON DELETE" not in table
    # And the append-only guarantee the rows rely on, read off the statements this
    # application declares rather than off prose about them.
    for name in dir(sstore):
        if not name.startswith("Q_"):
            continue
        statement = getattr(sstore, name)
        if isinstance(statement, str):
            upper = statement.upper()
            assert " UPDATE " not in f" {upper} " and not upper.startswith("UPDATE")
            assert "DELETE" not in upper


def test_a_removal_that_wins_makes_a_LATER_submit_holding_the_old_token_a_412(
    armed, wired, db
):
    """The submit/removal race, in the order where the removal lands first.

    The submission is refused with nothing recorded and nothing published — not
    silently rewritten to describe a record it never read.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    stale = _etag(client)

    assert _remove(client, ids[0]).status_code == 200

    response = _submit(client, if_match=stale)
    assert response.status_code == 412, response.text
    assert db.is_empty()
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set()


def test_a_submit_that_wins_turns_an_in_flight_removal_into_the_exported_refusal(
    armed, wired, db
):
    """The same race in the other order, and the outcome is the STRONGER refusal.

    A reader opens the confirmation, someone submits, the reader confirms. Their
    token is stale — but by the time the request arrives the run is exported, and
    the exported refusal is checked first. So they are told the durable reason
    ("this run has been exported") rather than the transient one ("refresh and try
    again"), which is the only one of the two that would still be true after a
    refresh.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    stale = _etag(client)

    assert _submit(client).status_code == 200
    before = copy.deepcopy(db.submissions)

    response = _remove(client, ids[0], if_match=stale)
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "run_exported"
    assert _run_ids() == ids
    assert db.submissions == before


# =============================================================================
# 9. the `isaac_runs` SHADOW PROJECTION follows the document
# =============================================================================


def test_the_shadow_run_rows_follow_the_document_the_ROUTE_wrote(workspace):
    """The shadow is a pure function of ``sorted_runs()`` — after a REMOVAL too.

    THE DOCUMENT UNDER TEST IS THE ONE THE HTTP ROUTE PRODUCED. It is reloaded from
    the workspace and then persisted through the real ``PostgresOrdinaryStore``
    against the in-process connection double, so the statement policy, the explicit
    transaction and the row diff all run for real and only the server is fake.

    WHAT THIS CANNOT PROVE, stated because the obvious reading is too generous: the
    fake hands back exactly the document it was given, so it says nothing about
    whether the SQL is valid PostgreSQL or whether ``0002_runs``' constraints accept
    the rows. That half is
    ``test_run_row_parity.test_parity_removing_a_run_over_HTTP_removes_its_row``,
    which runs only against CI's real engine behind its two opt-in variables.
    """
    _make(runs=("run A", "run B", "run C"))
    ids = _run_ids()
    conn = FakeConnection()
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))

    store.persist(ws.load_experiment(EXPERIMENT_ID))
    assert set(conn.runs) == set(ids)

    assert _remove(_client(), ids[1]).status_code == 200

    conn.statements.clear()
    after = ws.load_experiment(EXPERIMENT_ID)
    store.persist(after)

    # The ROW SET is exactly the surviving runs...
    assert set(conn.runs) == {ids[0], ids[2]}
    # ...and each row is the run's own document, ordinal included and NOT renumbered.
    for run in after.sorted_runs():
        experiment_id, ordinal, state, rev, generation = conn.runs[run.id]
        assert experiment_id == EXPERIMENT_ID
        assert (ordinal, state, rev, generation) == (
            run.ordinal,
            run.to_state(),
            run.rev,
            run.generation,
        )
    # The delete is issued as the COMPLEMENT of the surviving set, so a row that
    # appeared between the read and the write goes too.
    issued = [
        (sql, params)
        for sql, params in conn.statements
        if sql == repo.Q_DELETE_ABSENT_RUNS
    ]
    assert len(issued) == 1, issued
    assert issued[0][1][0] == EXPERIMENT_ID
    assert set(issued[0][1][1]) == {ids[0], ids[2]}


def test_removing_the_LAST_run_binds_an_EMPTY_id_array_to_the_shadow_delete(workspace):
    """The one save whose ``%s::text[]`` cast is load-bearing, reached through HTTP.

    An empty array literal carries no element type for the server to infer, so
    clearing a record's runs is the save that would raise without the cast. This
    asserts the PARAMETER — no driver and no engine is involved — and the real
    engine binds it in CI.
    """
    _make(runs=("only run",))
    only = _run_ids()[0]
    conn = FakeConnection()
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    store.persist(ws.load_experiment(EXPERIMENT_ID))
    assert set(conn.runs) == {only}

    assert _remove(_client(), only).status_code == 200

    conn.statements.clear()
    store.persist(ws.load_experiment(EXPERIMENT_ID))
    assert conn.runs == {}
    params = next(
        params for sql, params in conn.statements if sql == repo.Q_DELETE_ABSENT_RUNS
    )
    assert params[1] == []
    assert "::text[]" in repo.Q_DELETE_ABSENT_RUNS


def test_no_statement_this_removal_can_cause_names_a_production_table(workspace):
    """A removal must never issue a statement naming ``records``.

    The write path's statement policy refuses one, and this is the removal-shaped
    proof of it: every statement the persisted removal produced is inspected, and
    the only relations named are the application's own.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    conn = FakeConnection()
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    store.persist(ws.load_experiment(EXPERIMENT_ID))
    assert _remove(_client(), ids[0]).status_code == 200
    conn.statements.clear()
    store.persist(ws.load_experiment(EXPERIMENT_ID))

    for sql, _params in conn.statements:
        lowered = sql.lower()
        assert " records" not in lowered and "from records" not in lowered
        assert "drop " not in lowered and "truncate" not in lowered
    assert conn.rollbacks == 0 and conn.commits >= 1
    assert dbw.EXPECTED_DATABASE  # the gate this store passed through is a real one


# =============================================================================
# 10. worked-example (tutorial) scope
# =============================================================================


@pytest.fixture()
def tclient(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def test_a_run_in_a_worked_example_session_can_be_removed_within_that_session(tclient):
    """A worked-example record is temporary and synthetic; removing a run from one
    is as harmless as adding one, and the same operation serves both."""
    store = client_ws(tclient)
    exp = store.create_experiment(
        "Run removal fixture", {"kind": "synthetic"}, copy.deepcopy(ws._full_draft())
    )
    created = tclient.post(
        f"/api/experiments/{exp.id}/runs",
        json={"label": "session run"},
        headers={"If-Match": _etag(tclient, exp.id)},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run"]["id"]

    response = _remove(tclient, run_id, exp.id)

    assert response.status_code == 200, response.text
    assert store.load_experiment(exp.id).runs == []


def test_a_session_record_is_not_reachable_without_the_session_header(tclient):
    """The fail-closed arm: the request is never answered from the ordinary
    workspace instead."""
    store = client_ws(tclient)
    exp = store.create_experiment(
        "Run removal fixture", {"kind": "synthetic"}, copy.deepcopy(ws._full_draft())
    )
    created = tclient.post(
        f"/api/experiments/{exp.id}/runs",
        json={"label": "session run"},
        headers={"If-Match": _etag(tclient, exp.id)},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run"]["id"]

    from isaac_api.routes import TUTORIAL_SESSION_HEADER

    # A WELL-FORMED session id that names no session. A malformed one is refused
    # earlier, as a 422 about the header, and would not exercise this arm at all.
    other = tclient.tutorial_session_id[:-1] + (
        "A" if tclient.tutorial_session_id[-1] != "A" else "B"
    )
    response = tclient.post(
        f"/api/experiments/{exp.id}/runs/{run_id}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": "*", TUTORIAL_SESSION_HEADER: other},
    )
    assert response.status_code == 404, response.text
    # The refusal names the SESSION, not the record: the request is never silently
    # answered from the ordinary workspace, and it is never told the record is
    # missing when what is missing is the session it named.
    assert response.json()["error"] == "tutorial_session_not_found"
    # And the run is still in the session it belongs to.
    assert [r.id for r in store.load_experiment(exp.id).runs] == [run_id]


# =============================================================================
# 11. the truth path is not touched by any of this
# =============================================================================


def test_the_removal_route_writes_nothing_under_the_truth_core(workspace):
    """A removal is a workspace-document edit and nothing else.

    ``src/isaac_records/`` and ``schema/`` are read-only to this operation, so the
    strongest cheap check is that the removal produced no file outside the
    workspace — asserted by comparing the truth core's own directory listing and
    modification times across the call.
    """
    from pathlib import Path

    import isaac_records

    core = Path(isaac_records.__file__).resolve().parent
    before = {p: p.stat().st_mtime_ns for p in sorted(core.rglob("*")) if p.is_file()}

    _make(runs=("run A",))
    assert _remove(_client(), _run_ids()[0]).status_code == 200

    after = {p: p.stat().st_mtime_ns for p in sorted(core.rglob("*")) if p.is_file()}
    assert after == before


def test_a_HALF_WRITTEN_export_still_refuses_removal_and_keeps_the_published_pair(workspace):
    """CRITICAL from independent review, reproduced and then closed.

    The guard was `run.record_id is not None`, justified by "a run whose
    `record_id` is set HAS a record on disk". That direction is true and is not
    the one the safety argument needs. It needs the CONVERSE — a run whose
    `record_id` is NOT set has no pair on disk — and this codebase names the state
    where the converse is false, in `post_export`'s own 412 branch: "EVERY unit's
    artifact PAIR was already written to disk and the state was not".

    `_write_record` sets `record_id` in memory and writes both files; one
    `_save_versioned` then persists. A lost durable compare-and-swap, or a raise
    between two units' writes, leaves the pair on disk with `record_id`
    unpersisted.

    The reviewer drove the real routes in exactly that shape: removal returned
    **200**, the next export pruned the orphan, and a published official record
    AND its evidence sidecar were deleted — at a distance, with no confirmation,
    and the documented repair ("republish from the current draft") impossible
    because the run was gone.

    This test recreates the documented half-written shape directly: export, then
    clear `record_id` on the persisted document while LEAVING the pair on disk.

    MUTATION: restore the guard to `run.record_id is not None` and this goes RED
    at the first assertion.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    exported = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/export", headers={"If-Match": _etag(client)}
    )
    assert exported.status_code == 200, exported.text

    exp = ws.load_experiment(EXPERIMENT_ID)
    before = {name: (exp.records_dir / name).read_bytes() for name in _artifacts(exp)}
    assert before, "the fixture did not actually export anything"
    target = exp.get_run(ids[0])
    stem = target.record_id
    assert stem is not None, "the fixture did not materialise the run under test"
    assert (exp.records_dir / f"{stem}.json").exists()

    # THE DOCUMENTED HALF-WRITTEN STATE: files on disk, `record_id` not persisted.
    target.record_id = None
    exp.save()
    reloaded = ws.load_experiment(EXPERIMENT_ID)
    assert reloaded.get_run(ids[0]).record_id is None, "the fixture did not take"
    assert (reloaded.records_dir / f"{stem}.json").exists(), "the pair must remain"

    # THE GUARD MUST STILL REFUSE — on disk evidence, not on state.
    response = _remove(client, ids[0])
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "run_exported"
    # And it must name the artifact it is protecting, even though `record_id` is
    # null on this arm — a message built from `record_id` alone would say "null".
    assert body["record_stem"] == stem
    assert body["record_id"] is None

    # The run survives, and so does every published byte.
    assert ids[0] in _run_ids()
    after_exp = ws.load_experiment(EXPERIMENT_ID)
    after = {name: (after_exp.records_dir / name).read_bytes() for name in _artifacts(after_exp)}
    assert after == before, "a published record or sidecar was disturbed"


def test_the_half_written_guard_does_not_refuse_an_ordinary_unexported_run(workspace):
    """The other half: raising the bar must not refuse a run with nothing on disk.

    Without this, the fix above could be 'refuse everything', which would pass the
    test above and destroy the feature.
    """
    _make(runs=("run A", "run B"))
    ids = _run_ids()
    client = _client()
    exp = ws.load_experiment(EXPERIMENT_ID)
    assert not _artifacts(exp), "this test needs a record with nothing exported"

    response = _remove(client, ids[0])
    assert response.status_code == 200, response.text
    assert ids[0] not in _run_ids()
