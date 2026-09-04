"""Finalizing a transcript mints DURABLE ingestion proposals, in the same save.

WHAT THIS SLICE CLOSED, AND WHY A TEST FILE OF ITS OWN
======================================================

Before it, ``POST /api/experiments/{id}/transcript`` returned ``candidates`` in a
response body and stored nothing but notes. A candidate lived in one browser tab's
state: navigating away destroyed it, no colleague could see it, and the only way to
act on one was a direct ``PATCH .../runs/{run_id}`` issued by the component that
happened to be holding it. ``docs/evidence/two-actor-workflow-proof-2026-09-02.md``
§1 recorded the consequence — *"No surface in this build can create a proposal"*.

Every claim below is a claim the previous behaviour would falsify, which is what
makes this file the evidence rather than a restatement of the route.

THE CONTRACT INVARIANTS THIS TOUCHES, by name, so a reader can check the coverage
against ``docs/ingestion-proposal-contract.md`` §5:

* **I1** — minting mutates no authoritative metadata.
  ``test_I1_minting_proposals_mutates_no_authoritative_metadata``
* **I2** — a proposal is inert to export.
  ``test_I2_a_capture_leaves_the_exported_record_byte_identical``
* **I6** — nothing captured is discarded. Every candidate is either a stored
  proposal or a disclosed ``unproposable`` entry, and its words are a note either
  way. ``test_I6_a_candidate_with_no_write_path_is_disclosed_not_dropped``,
  ``test_I6_every_candidate_is_accounted_for_in_exactly_one_list``
* **I7** — worked-example isolation.
  ``test_I7_a_capture_in_a_tutorial_session_is_invisible_to_the_ordinary_scope``

NEGATIVE CONTROL. ``test_negative_control_with_minting_disabled_nothing_is_stored``
runs the same capture with the mint stubbed out and asserts the record then holds
zero proposals while the notes are unchanged — so the proposals the tests above
observe demonstrably come from this code path and not from a fixture, a seed, or
another route.

DATA BOUNDARY: none. Every record, run, note and proposal here is created by the
test seconds earlier in a ``tmp_path`` workspace. No file outside it is read or
written, nothing connects to a database, and no production-derived content is
touched.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

import isaac_api.routes as routes
import isaac_api.transcript_capture as tc
from isaac_records.export import transform

from conftest import client_ws, tutorial_client

#: A transcript whose every candidate is unambiguous. Two sentences, two rules, two
#: candidates — kept small so a count in an assertion is checkable by eye.
CLEAN = "Temperature was 300 K. Atmosphere was: dry nitrogen"

#: One sentence, two rules, ONE note. The reader emits a candidate for each, so this
#: is the shape that proves the idempotency key is keyed on more than the note id.
ONE_SENTENCE_TWO_VALUES = "Temperature was 300 K and atmosphere was: argon"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def experiment_id(client):
    store = client_ws(client)
    exp = store.create_experiment(
        "Transcript proposal fixture",
        {"kind": "synthetic"},
        {"meta": {}, "fields": {}, "pending": []},
    )
    return exp.id


# --- helpers ------------------------------------------------------------------


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _make_run(client, experiment_id: str, label: str | None = None) -> dict:
    body: dict = {}
    if label is not None:
        body["label"] = label
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json=body,
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]


def _finalize(client, experiment_id: str, text: str, *, run_id: str | None = None, etag=None):
    body: dict = {"text": text, "finalized": True}
    if run_id is not None:
        body["run_id"] = run_id
    return client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json=body,
        headers={"If-Match": etag if etag is not None else _etag(client, experiment_id)},
    )


def _list_proposals(client, experiment_id: str) -> dict:
    response = client.get(f"/api/experiments/{experiment_id}/proposals")
    assert response.status_code == 200, response.text
    return response.json()


def _stored(client, experiment_id: str):
    """The experiment as the STORE holds it — never as a response reported it."""
    return client_ws(client).load_experiment(experiment_id)


def _authoritative_snapshot(exp) -> str:
    """Contract **I1**'s exact shape, borrowed verbatim from ``test_ingestion_proposals``.

    Every export unit's draft AND every run's fully resolved draft, byte-for-byte.
    Borrowed rather than imported because the two files' fixtures differ; the SHAPE
    is what the contract names, and keeping it identical is what makes the two
    results comparable.
    """
    return json.dumps(
        {
            "export": [unit.draft for unit in exp.export_units()],
            "resolved": [exp.resolved_run_draft(run) for run in exp.sorted_runs()],
            "draft": exp.draft,
        },
        sort_keys=True,
        default=str,
    )


def _exported_bytes(exp) -> str:
    """Every official record this experiment would export, deterministically."""
    return json.dumps(
        [
            transform(
                unit.draft,
                record_id="01JQZZ2EXPORT000000000000" + str(index),
                now="2026-01-01T00:00:00Z",
            )
            for index, unit in enumerate(exp.export_units())
        ],
        sort_keys=True,
    )


# =============================================================================
# 1. the capture mints, and what it mints is durable
# =============================================================================


def test_a_finalized_transcript_stores_one_open_proposal_per_candidate(
    client, experiment_id
):
    """The finding this slice closes, stated as the first assertion.

    MUTATION: removing the `_mint_transcript_proposals` call from `post_transcript`
    turns this RED — `total` becomes 0 while `candidates` stays 2.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    assert len(payload["candidates"]) == 2
    assert len(payload["proposals"]) == 2
    assert payload["unproposable"] == []

    # DURABLE, read back through the operation a reviewer's screen actually calls,
    # not out of the response body that created them.
    listed = _list_proposals(client, experiment_id)
    assert listed["total"] == 2
    assert listed["by_state"]["open"] == 2
    stored_ids = {entry["proposal_id"] for entry in listed["proposals"]}
    assert stored_ids == {entry["proposal"]["proposal_id"] for entry in payload["proposals"]}


def test_each_proposal_cites_the_note_the_candidate_came_from(client, experiment_id):
    """The citation is what keeps the verbatim words safe from every outcome.

    Asserted through the DERIVED excerpt as well as the id: the span this route
    stores covers the whole note, so the excerpt a reviewer sees is exactly the
    sentence the rule quoted.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    # NOT VACUOUS. Without this the loop below iterates ZERO times when the mint is
    # disabled or returns nothing, and a test that asserts nothing passes.
    assert len(payload["proposals"]) == 2
    assert len(payload["candidates"]) == 2

    notes_by_id = {note["id"]: note for note in payload["notes"]}
    for entry, candidate in zip(payload["proposals"], payload["candidates"]):
        proposal = entry["proposal"]
        assert proposal["note_id"] in notes_by_id
        note = notes_by_id[proposal["note_id"]]
        assert note["text"] == candidate["quote"]
        assert proposal["excerpt"] == note["text"]
        assert proposal["rule"] == candidate["rule"]
        assert proposal["proposed_value"] == candidate["proposed_value"]
        assert proposal["target_field_path"] == candidate["field_path"]


def test_every_minted_proposal_is_run_scoped_to_the_capture_s_run(client, experiment_id):
    """`run_id` is the run the capture NAMED, never inferred and never another's.

    The record has two runs and the capture names the SECOND, so a route that had
    reached for "the only run" or for the first would be caught here rather than
    passing on a single-run fixture.
    """
    first = _make_run(client, experiment_id, label="Run A")
    second = _make_run(client, experiment_id, label="Run B")
    payload = _finalize(client, experiment_id, CLEAN, run_id=second["id"]).json()

    assert payload["proposals"]
    for entry in payload["proposals"]:
        assert entry["proposal"]["run_id"] == second["id"]
        assert entry["proposal"]["run_id"] != first["id"]


def test_a_capture_with_no_run_selected_mints_nothing_and_says_so(
    client, experiment_id
):
    """The record-scoped case, and it is a case with no candidates at all.

    Every path this reader can propose is run-scoped, and `read_transcript`
    withholds every candidate while the run is unsettled. So "record-scoped
    transcript proposal" is unconstructible rather than merely unbuilt, and the
    honest assertion is that the capture stores the notes and no proposal.
    """
    _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN).json()

    assert payload["candidates"] == []
    assert payload["proposals"] == []
    assert payload["unproposable"] == []
    assert payload["clarifications"]  # it asked which run, rather than choosing one
    assert len(payload["notes"]) == 2
    assert _list_proposals(client, experiment_id)["total"] == 0


def test_the_five_readable_paths_are_all_run_scoped_targets():
    """WHY the test above is the whole record-scoped story, derived not asserted.

    If a future rule gave the reader a record-scoped path, this goes RED and the
    test above stops being a complete account — which is the point of deriving it.
    """
    scopes = {
        routes._PROPOSAL_WRITER_SCOPE[routes._proposal_writer_for(path)]
        for path in tc.READABLE_FIELD_PATHS
    }
    assert scopes == {"run"}
    assert tc.READABLE_FIELD_PATHS <= routes.PROPOSAL_TARGET_PATHS


# =============================================================================
# 2. the idempotency key, and what it does and does not guarantee
# =============================================================================


def test_the_published_key_dedupes_a_client_that_mints_the_same_proposal(
    client, experiment_id
):
    """The key's actual job: two producers, one proposal.

    The response publishes `client_request_key`, so a client holding
    `createProposal` that tries to mint the same candidate is answered with the
    EXISTING proposal rather than creating a second.

    MUTATION: dropping `client_request_key` from `new_proposal` in the mint makes
    this create a SECOND proposal and turns both assertions RED.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    entry = payload["proposals"][0]
    assert entry["deduplicated"] is False
    assert entry["client_request_key"]

    replay = client.post(
        f"/api/experiments/{experiment_id}/proposals",
        json={
            "note_id": entry["proposal"]["note_id"],
            "target_field_path": entry["proposal"]["target_field_path"],
            "proposed_value": entry["proposal"]["proposed_value"],
            "rule": entry["proposal"]["rule"],
            "run_id": entry["proposal"]["run_id"],
            "client_request_key": entry["client_request_key"],
        },
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["deduplicated"] is True
    assert replay.json()["proposal"]["proposal_id"] == entry["proposal"]["proposal_id"]
    assert _list_proposals(client, experiment_id)["total"] == 2


def test_two_candidates_from_one_note_get_different_keys(client, experiment_id):
    """A key on the note id ALONE would collapse these two into one proposal.

    One sentence, two rules: both candidates cite the same note. The reader keeps
    both deliberately — "choosing the later one would be a guess" — so the mint must
    too.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client, experiment_id, ONE_SENTENCE_TWO_VALUES, run_id=run["id"]
    ).json()

    assert len(payload["candidates"]) == 2
    assert len(payload["proposals"]) == 2
    note_ids = {entry["proposal"]["note_id"] for entry in payload["proposals"]}
    assert len(note_ids) == 1, "both candidates came from the one sentence"
    keys = {entry["client_request_key"] for entry in payload["proposals"]}
    assert len(keys) == 2
    assert _list_proposals(client, experiment_id)["total"] == 2


def test_a_retry_with_the_stale_etag_is_412_and_stores_no_second_set(
    client, experiment_id
):
    """WHAT ACTUALLY PROTECTS A RETRY, and it is not the key.

    A capture that reached disk advanced the record's ETag. The retry the network
    made necessary therefore meets `412`, and the record holds ONE set of notes and
    ONE set of proposals. This is the duplicate-submission case in its real shape.
    """
    run = _make_run(client, experiment_id)
    stale = _etag(client, experiment_id)
    first = _finalize(client, experiment_id, CLEAN, run_id=run["id"], etag=stale)
    assert first.status_code == 200, first.text
    assert _list_proposals(client, experiment_id)["total"] == 2

    retry = _finalize(client, experiment_id, CLEAN, run_id=run["id"], etag=stale)
    assert retry.status_code == 412, retry.text
    assert _list_proposals(client, experiment_id)["total"] == 2
    assert len(client.get(f"/api/experiments/{experiment_id}/notes").json()["notes"]) == 2


def test_finalizing_the_same_text_twice_deliberately_is_two_acts(client, experiment_id):
    """AND THE OTHER HALF, stated rather than left to be discovered as a defect.

    A scientist who finalizes the same words a second time, with a CURRENT ETag, has
    performed two acts — and gets two sets of notes and two sets of proposals. That
    is `capture_note`'s existing behaviour, not a new inconsistency: the words are
    stored twice because they were finalized twice, and the proposals follow the
    notes they cite. The keys differ because the note ids do.
    """
    run = _make_run(client, experiment_id)
    first = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    second = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    assert _list_proposals(client, experiment_id)["total"] == 4
    assert {entry["client_request_key"] for entry in first["proposals"]}.isdisjoint(
        {entry["client_request_key"] for entry in second["proposals"]}
    )
    assert all(entry["deduplicated"] is False for entry in second["proposals"])


# =============================================================================
# 3. I1 and I2 — minting writes no value and changes no export
# =============================================================================


def test_I1_minting_proposals_mutates_no_authoritative_metadata(client, experiment_id):
    """Contract **I1**, in the shape the contract specifies.

    Every export unit's draft AND every run's resolved draft, byte-for-byte across a
    capture that mints two proposals.

    MUTATION: making the mint call `_apply_run_field` turns this RED.
    """
    run = _make_run(client, experiment_id)
    before = _authoritative_snapshot(_stored(client, experiment_id))

    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    assert len(payload["proposals"]) == 2

    after = _authoritative_snapshot(_stored(client, experiment_id))
    assert after == before

    # AND THE RUN'S OWN FIELDS ARE STILL EMPTY, read through the API rather than the
    # store, because that is where a scientist would see a value that had leaked.
    run_after = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()
    assert run_after["run"]["fields"] == {}


def test_I2_a_capture_leaves_the_exported_record_byte_identical(client, experiment_id):
    """Contract **I2**. Structural, because proposals live outside `draft`."""
    run = _make_run(client, experiment_id)
    before = _exported_bytes(_stored(client, experiment_id))

    _finalize(client, experiment_id, CLEAN, run_id=run["id"])
    reloaded = _stored(client, experiment_id)
    assert reloaded.proposals, "the capture stored proposals, so this is not vacuous"
    assert _exported_bytes(reloaded) == before

    # AND NO EXPORT UNIT'S DRAFT CARRIES THE KEY AT ALL.
    for unit in reloaded.export_units():
        assert "proposals" not in unit.draft


def test_the_response_still_says_it_applied_nothing(client, experiment_id):
    """`applied` is a constant `False` on the reading and stays serialised as one.

    Minting a durable row is exactly the kind of change that invites a surface to
    start claiming more than it did, which is why this is asserted beside the mint.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    assert payload["applied"] is False
    # NOT VACUOUS, for the same reason: a mint that returned nothing would leave this
    # loop with no iterations and the test would still be green.
    assert len(payload["proposals"]) == 2
    for entry in payload["proposals"]:
        assert entry["proposal"]["state"] == "open"
        assert entry["proposal"]["applied"] is False
        assert entry["proposal"]["verified"] is False
        assert entry["proposal"]["is_field_value"] is False
        assert entry["proposal"]["is_evidence"] is False


# =============================================================================
# 4. I6 — nothing captured is discarded
# =============================================================================


def test_I6_every_candidate_is_accounted_for_in_exactly_one_list(client, experiment_id):
    """Each candidate index appears once across `proposals` + `unproposable`.

    The property, not a count: a candidate that is in neither has been dropped in
    silence, and a candidate in both is two claims about one reading.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    accounted = [entry["candidate_index"] for entry in payload["proposals"]]
    accounted += [entry["candidate_index"] for entry in payload["unproposable"]]
    assert sorted(accounted) == list(range(len(payload["candidates"])))
    assert len(accounted) == len(set(accounted))


def test_I6_a_candidate_with_no_write_path_is_disclosed_not_dropped(
    client, experiment_id, monkeypatch
):
    """The unproposable branch, reached by narrowing the permitted target set.

    THIS BRANCH IS UNREACHABLE THROUGH ANY REQUEST AT THIS HEAD — the module-level
    `_UNACCEPTABLE_READER_PATHS` guard makes every reader path run-writable — so the
    test narrows `PROPOSAL_TARGET_PATHS` to construct it. That is deliberate rather
    than a shortcut: the branch exists so the promise survives a change to either
    set, and a test that could not reach it would be asserting the guard twice.
    """
    run = _make_run(client, experiment_id)
    monkeypatch.setattr(
        routes,
        "PROPOSAL_TARGET_PATHS",
        frozenset(routes.PROPOSAL_TARGET_PATHS - {"context.temperature_K"}),
    )
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    assert len(payload["candidates"]) == 2
    assert len(payload["proposals"]) == 1
    assert len(payload["unproposable"]) == 1
    refused = payload["unproposable"][0]
    assert refused["field_path"] == "context.temperature_K"
    assert refused["error"] == "no_write_path_for_field"
    assert "OFFICIAL ISAAC SCHEMA" in refused["message"]
    # THE WORDS ARE STILL STORED. That is the whole of I6.
    assert refused["note_id"] in {note["id"] for note in payload["notes"]}
    assert len(payload["notes"]) == 2


def test_the_row_ceiling_discloses_rather_than_refusing_the_capture(
    client, experiment_id, monkeypatch
):
    """Over the per-record row bound, the capture still stores every word.

    Refusing the transcript would destroy it for a reason that has nothing to do
    with it, so the ceiling is DISCLOSED per candidate instead.
    """
    run = _make_run(client, experiment_id)
    monkeypatch.setattr(routes, "_MAX_PROPOSALS_PER_RECORD", 0)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    assert payload["proposals"] == []
    assert len(payload["unproposable"]) == 2
    assert {entry["error"] for entry in payload["unproposable"]} == {"too_many_proposals"}
    assert len(payload["notes"]) == 2
    assert _list_proposals(client, experiment_id)["total"] == 0


def test_the_byte_ceiling_is_all_or_nothing_and_says_so(
    client, experiment_id, monkeypatch
):
    """Over the per-record byte bound, NO proposal from the capture is stored.

    All-or-nothing rather than "as many as fit", because a partial batch chosen by
    byte arithmetic would be this route deciding which of a scientist's values are
    worth keeping.
    """
    run = _make_run(client, experiment_id)
    monkeypatch.setattr(routes, "_MAX_PROPOSAL_STATE_BYTES", 1)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    assert payload["proposals"] == []
    assert [entry["candidate_index"] for entry in payload["unproposable"]] == [0, 1]
    assert {entry["error"] for entry in payload["unproposable"]} == {"proposals_too_large"}
    assert len(payload["notes"]) == 2
    assert _list_proposals(client, experiment_id)["total"] == 0


def test_a_null_valued_candidate_is_refused_by_the_SHARED_definition(
    client, experiment_id, monkeypatch
):
    """A `None` value is refused HERE for the reason `POST .../proposals` refuses it.

    WHY THIS TEST EXISTS. The null check used to live inline in `post_proposal`, so
    the route refused a value that would CLEAR the field while THIS producer — the
    only producer in the build — had no null check at all and would have stored one.
    One producer refusing what another accepts is two answers to "what may a proposal
    hold". The check now lives in `_proposal_value_problem`, which both call.

    UNREACHABLE THROUGH ANY REQUEST AT THIS HEAD, exactly like the no-write-path test
    above: every rule in the closed table reads a value out of the words it matched,
    so a candidate carrying `None` cannot be produced. The candidate is therefore
    constructed by patching the reader, which is what lets the shared refusal be
    observed rather than argued.

    MUTATION: deleting the `value is None` case from `_proposal_value_problem` makes
    the capture STORE a null-valued proposal and turns the first assertions RED. It
    breaks the ROUTE in the same stroke — measured: `POST .../proposals` then answers
    `200` and stores `proposed_value: null`, so
    `test_ingestion_proposals.py::test_a_null_value_is_refused_because_it_would_clear_the_field`
    goes RED too. (The route assertion at the END of this test is not what witnesses
    that, because the earlier assertion fails first and the test stops there.) One
    deletion breaks BOTH producers, which is the point of sharing the definition. The
    asymmetry this closes is the one that existed BEFORE the move, when the check
    lived only in the route: the route refused a null while this producer stored one.
    """
    run = _make_run(client, experiment_id)
    real_read = tc.read_transcript

    def reading_with_a_null_candidate(*args, **kwargs):
        reading = real_read(*args, **kwargs)
        candidates = list(reading.candidates)
        assert candidates, "the fixture transcript must produce a candidate to null"
        candidates[0] = dataclasses.replace(candidates[0], proposed_value=None)
        return dataclasses.replace(reading, candidates=tuple(candidates))

    monkeypatch.setattr(tc, "read_transcript", reading_with_a_null_candidate)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    assert len(payload["candidates"]) == 2
    assert [entry["candidate_index"] for entry in payload["unproposable"]] == [0]
    refused = payload["unproposable"][0]
    assert refused["error"] == "invalid_proposed_value"
    assert "must not be null" in refused["message"]
    assert "CLEAR the field" in refused["message"]

    # THE OTHER CANDIDATE IS UNAFFECTED. A shared refusal must reject the value, not
    # the capture: this is a disclosure, not a ceiling.
    assert [entry["candidate_index"] for entry in payload["proposals"]] == [1]
    stored = _list_proposals(client, experiment_id)
    assert stored["total"] == 1
    assert all(
        entry["proposed_value"] is not None for entry in stored["proposals"]
    )
    # AND THE WORDS SURVIVED, which is I6 on this branch too.
    assert refused["note_id"] in {note["id"] for note in payload["notes"]}
    assert len(payload["notes"]) == 2

    # ONE DEFINITION, TWO PRESENTATIONS: the same value at the same path is refused by
    # the route with the SAME error code, as a 422 over the whole request.
    over_the_route = client.post(
        f"/api/experiments/{experiment_id}/proposals",
        json={
            "note_id": payload["notes"][0]["id"],
            "target_field_path": "context.temperature_K",
            "proposed_value": None,
            "rule": "a rule",
            "run_id": run["id"],
        },
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert over_the_route.status_code == 422, over_the_route.text
    assert over_the_route.json()["error"] == refused["error"]
    assert over_the_route.json()["message"] == refused["message"]


# =============================================================================
# 5. I7 — worked-example isolation
# =============================================================================


def test_I7_a_capture_in_a_tutorial_session_is_invisible_to_the_ordinary_scope(
    tmp_path, monkeypatch
):
    """A proposal minted inside a worked example never escapes it.

    Two clients over ONE application: a tutorial-scoped one that captures, and an
    ordinary-scoped one that must not see the record at all. Anything less than a
    404 here would mean a worked example had reached normal content.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    app = create_app()
    tutorial = tutorial_client(app)
    ordinary = TestClient(app)

    store = client_ws(tutorial)
    exp = store.create_experiment(
        "Tutorial capture",
        {"kind": "synthetic"},
        {"meta": {}, "fields": {}, "pending": []},
    )
    run = _make_run(tutorial, exp.id)
    payload = _finalize(tutorial, exp.id, CLEAN, run_id=run["id"]).json()
    assert len(payload["proposals"]) == 2
    assert _list_proposals(tutorial, exp.id)["total"] == 2

    assert ordinary.get(f"/api/experiments/{exp.id}/proposals").status_code == 404
    assert ordinary.get(f"/api/experiments/{exp.id}").status_code == 404


# =============================================================================
# 6. the change feed announces every minted proposal
# =============================================================================


def test_the_capture_is_announced_through_the_change_feed(client, experiment_id):
    """A second browser learns about the proposals without being told by the first.

    The feed derives its positions from `Experiment.proposal_change_revs`, which
    `save_versioned` maintains — so minting inside the capture's existing save emits
    exactly what `POST .../proposals` emits, by the same mechanism rather than by a
    second one this route would have to keep in step.

    The cursor is taken BEFORE the capture, so the assertion is about what the
    capture added rather than about the record's whole history.
    """
    run = _make_run(client, experiment_id)
    drained = client.get(f"/api/experiments/{experiment_id}/changes").json()
    while drained["has_more"]:
        drained = client.get(
            f"/api/experiments/{experiment_id}/changes",
            params={"cursor": drained["next_cursor"]},
        ).json()
    cursor = drained["next_cursor"]

    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    minted = {entry["proposal"]["proposal_id"] for entry in payload["proposals"]}
    assert len(minted) == 2

    seen: dict[str, dict] = {}
    page = client.get(
        f"/api/experiments/{experiment_id}/changes", params={"cursor": cursor}
    ).json()
    while True:
        for entry in page["changes"]:
            if entry["kind"] == "proposal":
                assert entry["entity_id"] not in seen, "no entity served twice"
                seen[entry["entity_id"]] = entry
        if not page["has_more"]:
            break
        page = client.get(
            f"/api/experiments/{experiment_id}/changes",
            params={"cursor": page["next_cursor"]},
        ).json()

    assert set(seen) == minted
    assert {entry["state"] for entry in seen.values()} == {"open"}


# =============================================================================
# 7. the negative control
# =============================================================================


def test_negative_control_with_minting_disabled_nothing_is_stored(
    client, experiment_id, monkeypatch
):
    """The same capture, with the mint stubbed out. Proves the coupling.

    Every assertion in section 1 rests on proposals existing after a capture. If
    they could exist without `_mint_transcript_proposals` having run — from a seed,
    a fixture, or another route — those assertions would be measuring nothing. With
    the mint replaced by a no-op the record holds ZERO proposals and the SAME notes,
    which is the only reading under which the tests above are about this code.
    """
    run = _make_run(client, experiment_id)
    monkeypatch.setattr(
        routes, "_mint_transcript_proposals", lambda *a, **k: ([], [])
    )
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()

    assert len(payload["candidates"]) == 2
    assert len(payload["notes"]) == 2
    assert payload["proposals"] == []
    assert _list_proposals(client, experiment_id)["total"] == 0
