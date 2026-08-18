"""Conflict resolution — the two HTTP operations over the recorded-decision model.

WHAT THIS FEATURE PROMISES, AND WHERE EACH PROMISE IS HELD HERE
===============================================================

The feature is five sentences, and every one of them is a claim a test can falsify:

1. **A scientist can finally SEE the competing answers.** The resolution surface
   returns the values themselves, grouped by value, each with the citations that
   assert it — unlike the submission disclosure, which returns addresses only.
   (``test_a_two_source_conflict_is_listed_with_both_values_and_their_sources``,
   ``test_a_three_source_conflict_lists_three_candidates``)
2. **Nothing picks a winner.** A ``chosen_value`` exists only because a request
   carried one together with ``confirmed_by_user: true``; a read never creates a
   decision, and a ``resolved`` outcome with no value is refused.
   (``test_reading_the_conflict_surface_records_no_decision``,
   ``test_a_resolved_outcome_with_no_chosen_value_is_refused``)
3. **Nothing is removed, in either direction.** The evidence payload is byte
   identical before and after a decision, the address goes on being reported as
   conflicting, and a superseded decision is kept on the history rather than
   overwritten.
   (``test_the_evidence_payload_is_byte_identical_before_and_after_a_decision``,
   ``test_revising_a_decision_appends_and_keeps_what_it_superseded``)
4. **A decision that no longer covers the disagreement says so.** A third answer
   arriving after a decision makes it ``stale``, the address returns to
   conflicting, and the decision is still visible.
   (``test_a_third_answer_makes_an_earlier_decision_stale_without_deleting_it``)
5. **A decision is not a value and cannot reach an official record.** The field's
   own value is untouched, and no exported record or sidecar carries the draft key
   decisions are stored under.
   (``test_recording_a_decision_does_not_change_the_field_value``,
   ``test_an_exported_record_carries_no_conflict_resolutions_key``,
   ``test_the_official_transform_ignores_the_decisions_key``)

EVERY REFUSAL TEST ASSERTS THE SPECIFIC ``error`` STRING
========================================================

A non-2xx assertion would be satisfied by a request that FastAPI rejected before
reaching any guard in this feature, which proves nothing about the guard. Every
refusal below names the exact ``error`` and the exact status.

MUTATION-CHECKED
================

``test_a_candidate_value_that_is_none_of_the_competing_answers_is_refused`` was
verified by BREAKING the production guard in the specific way it claims to catch —
the ``chosen_value_not_a_candidate`` condition in
``routes.post_conflict_resolution`` was forced to ``False`` — and confirming the
test went RED. **It did NOT go red on the status**, and that is worth stating here
rather than only in the test: the model's own ``__post_init__`` refuses the same
shape, so the response stayed ``422`` and only the SPECIFIC ``error`` assertion
failed (``'unsupported_resolution' == 'chosen_value_not_a_candidate'``), taking
``test_a_corrected_request_succeeds_after_a_refusal_with_the_same_validator`` down
with it. A status-only assertion would have survived the mutation and proved
nothing. The condition was restored and all tests pass again. The mutation is
recorded in that test's own docstring; a test with no ``MUTATION`` line was not
mutation-checked and does not claim to have been.

Everything here is synthetic. No file outside the tmp workspace is read or
written, and nothing connects to a database.
"""

from __future__ import annotations

import copy
import json

import pytest

import isaac_api.conflict_resolution as cr
import isaac_api.evidence_classify as evidence_classify
import isaac_api.provenance as provenance
import isaac_api.workspace as ws
from isaac_records.export import transform

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


#: The address every fixture below puts a disagreement at. A real official field
#: path, so nothing in this file depends on an invented one.
ADDRESS = "sample.material.formula"

#: A second real path, for the tests that need an address with no conflict.
CLEAN_ADDRESS = "sample.sample_form"


def _answer(value, *, question: str = "what is the formula?", at: str = "2026-01-01T00:00:00Z") -> dict:
    """One ``user_confirmation`` evidence entry asserting ``value``.

    Built through the truth core's own constructor rather than by hand, so the
    entry this test conflicts over is the same shape the answers and edit routes
    append. A hand-written literal would be a second definition of "a confirmation".
    """
    from isaac_records.models import user_confirmation

    return user_confirmation(question, value, at)


def _envelope(*answers, value=None, status: str = "verified", evidence=None) -> dict:
    """A draft field envelope whose evidence asserts each of ``answers``."""
    return {
        "value": answers[0] if value is None and answers else value,
        "status": status,
        "evidence": (
            list(evidence)
            if evidence is not None
            else [_answer(answer) for answer in answers]
        ),
    }


def _draft(fields: dict) -> dict:
    return {"meta": {}, "fields": fields, "pending": []}


def _experiment(client, fields: dict, *, title: str = "Conflict fixture") -> str:
    store = client_ws(client)
    return store.create_experiment(title, {"kind": "synthetic"}, _draft(fields)).id


@pytest.fixture()
def experiment_id(client):
    """An experiment with exactly one conflicting address: two answers, two values."""
    return _experiment(client, {ADDRESS: _envelope("LiFePO4", "LiFePO3")})


# --- helpers ------------------------------------------------------------------


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _conflicts(client, experiment_id: str, *, run: str | None = None):
    params = {} if run is None else {"run": run}
    return client.get(f"/api/experiments/{experiment_id}/conflicts", params=params)


def _listed(client, experiment_id: str, *, run: str | None = None) -> dict:
    response = _conflicts(client, experiment_id, run=run)
    assert response.status_code == 200, response.text
    return response.json()


def _resolve(client, experiment_id: str, *, if_match=..., **body):
    body.setdefault("confirmed_by_user", True)
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(
        f"/api/experiments/{experiment_id}/conflicts/resolve", json=body, headers=headers
    )


def _resolved(client, experiment_id: str, **body) -> dict:
    response = _resolve(client, experiment_id, **body)
    assert response.status_code == 200, response.text
    return response.json()["resolution"]


def _stored(client, experiment_id: str) -> dict:
    """The record's state document as it sits in the workspace."""
    exp = client_ws(client).load_experiment(experiment_id)
    assert exp is not None
    return exp.to_state()


def _only(payload: dict) -> dict:
    assert len(payload["conflicts"]) == 1, payload["conflicts"]
    return payload["conflicts"][0]


# --- 1. the surface: what a person is shown ------------------------------------


def test_a_two_source_conflict_is_listed_with_both_values_and_their_sources(
    client, experiment_id
):
    """The values themselves, grouped, each carrying the citations asserting it.

    THIS IS THE ASYMMETRY THE FEATURE DEPENDS ON. The submission conflict
    disclosure returns addresses and counts only, deliberately; this operation must
    return the values, because a scientist cannot choose between answers they are
    not shown.
    """
    body = _listed(client, experiment_id)
    entry = _only(body)
    assert entry["address"] == ADDRESS
    assert entry["run_id"] is None
    assert entry["evidence_count"] == 2
    assert entry["distinct_value_count"] == 2
    assert [candidate["value"] for candidate in entry["candidates"]] == [
        "LiFePO3",
        "LiFePO4",
    ]
    for candidate in entry["candidates"]:
        assert candidate["evidence_count"] == 1
        assert candidate["sources"] == [{"source_type": "user_confirmation"}]
    assert entry["resolution"] is None
    assert entry["resolution_state"] == cr.RESOLUTION_ABSENT
    assert entry["resolved"] is False
    assert entry["resolution_stale"] is False
    assert "2 distinct non-null answers" in entry["explanation"]
    assert body["counts"] == {
        "conflicting_addresses": 1,
        "resolved": 0,
        "deferred": 0,
        "stale": 0,
        "unresolved": 1,
    }
    assert body["scope"] == cr.CONFLICT_SCOPE
    assert body["unreadable_resolution_entries"] == 0
    assert body["outcomes"] == list(cr.RESOLUTION_OUTCOMES)
    assert body["chosen_from_values"] == list(cr.CHOSEN_FROM_VALUES)
    assert body["states"] == list(cr.RESOLUTION_STATES)


def test_the_conflict_surface_carries_the_records_etag(client, experiment_id):
    response = _conflicts(client, experiment_id)
    assert response.status_code == 200, response.text
    assert response.headers["ETag"] == _etag(client, experiment_id)


def test_a_three_source_conflict_lists_three_candidates(client):
    experiment_id = _experiment(
        client, {ADDRESS: _envelope("LiFePO4", "LiFePO3", "LiMnPO4")}
    )
    entry = _only(_listed(client, experiment_id))
    assert entry["distinct_value_count"] == 3
    assert entry["evidence_count"] == 3
    assert [candidate["value"] for candidate in entry["candidates"]] == [
        "LiFePO3",
        "LiFePO4",
        "LiMnPO4",
    ]
    assert "3 distinct non-null answers across 3 stored evidence entries" in (
        entry["explanation"]
    )


def test_same_value_from_different_sources_is_not_a_conflict(client):
    """Two citations asserting the SAME value disagree about nothing.

    A conflict is about VALUES, not about provenance, and the whole feature would
    be noise if a second citation for an already-cited value produced a finding.
    """
    from isaac_records.models import evidence as evidence_entry

    envelope = _envelope(
        value="LiFePO4",
        evidence=[
            _answer("LiFePO4"),
            evidence_entry("document", source_file="notes.pdf", answer="LiFePO4"),
            evidence_entry("spreadsheet", source_file="log.xlsx", answer="LiFePO4"),
        ],
    )
    experiment_id = _experiment(client, {ADDRESS: envelope})
    body = _listed(client, experiment_id)
    assert body["conflicts"] == []
    assert body["counts"]["conflicting_addresses"] == 0
    # ...and the resolve operation says so rather than recording a decision about a
    # disagreement that does not exist.
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "address_not_conflicting"


def test_a_partially_unreadable_payload_is_disclosed_beside_the_conflict(client):
    """Some of the stored evidence could not be read, and the row says so.

    The class describes only the readable part, which is a true statement about
    less than the whole entry — so the rest is said out loud rather than left to
    read as completeness.
    """
    envelope = _envelope(
        value="LiFePO4",
        evidence=[_answer("LiFePO4"), _answer("LiFePO3"), 7],
    )
    experiment_id = _experiment(client, {ADDRESS: envelope})
    entry = _only(_listed(client, experiment_id))
    assert entry["unavailable"] is True
    assert entry["distinct_value_count"] == 2
    # The count is of the READABLE entries, and the disclosure is what stops that
    # from reading as the whole picture.
    assert entry["evidence_count"] == 2
    assert evidence_classify.PARTIAL_DISCLOSURE in entry["explanation"]
    # A decision can still be recorded over the readable disagreement.
    resolution = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert resolution["state"] == cr.RESOLUTION_CURRENT
    assert _only(_listed(client, experiment_id))["unavailable"] is True


def test_reading_the_conflict_surface_records_no_decision(client, experiment_id):
    """A read is a read. Nothing here picks a winner, including by accident."""
    before = _stored(client, experiment_id)
    for _ in range(3):
        _listed(client, experiment_id)
    after = _stored(client, experiment_id)
    assert cr.DRAFT_KEY not in after["draft"]
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


def test_an_unknown_experiment_is_a_404(client):
    response = _conflicts(client, "01JQZZZZZZZZZZZZZZZZZZZZZZ")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


def test_an_unknown_run_on_the_read_is_a_404_naming_the_run(client, experiment_id):
    """Never answered from the record instead: a different subject is a different set."""
    response = _conflicts(client, experiment_id, run="01JQZZZZZZZZZZZZZZZZZZZZZZ")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "run_not_found"


# --- 2. the gap this closes: a conflict inside a run's own fields ---------------


def _with_run(client, experiment_id: str, fields: dict) -> str:
    """Add one run whose OWN draft carries ``fields``. Returns the run id."""
    store = client_ws(client)
    with store.record_lock(experiment_id):
        exp = store.load_experiment(experiment_id)
        run = exp.add_run(label="Run 1", draft=_draft(fields))
        exp.save_versioned()
        return run.id


def test_a_conflict_in_a_runs_own_fields_is_invisible_at_record_scope_and_visible_at_the_runs(
    client,
):
    """The defect the run scope exists to close, stated as two reads of one record.

    The evidence-support classification describes the RECORD's draft only, so a
    disagreement living in a run's own fields was reportable nowhere outside submit
    time. Both halves are asserted, because only the pair is the point.
    """
    experiment_id = _experiment(client, {})
    run_id = _with_run(
        client, experiment_id, {"context.temperature_K": _envelope(300, 310)}
    )
    assert _listed(client, experiment_id)["conflicts"] == []
    body = _listed(client, experiment_id, run=run_id)
    entry = _only(body)
    assert entry["address"] == "context.temperature_K"
    assert entry["run_id"] == run_id
    assert [candidate["value"] for candidate in entry["candidates"]] == [300, 310]


def test_a_run_scoped_decision_takes_the_records_validator_and_is_scoped_to_the_run(
    client,
):
    """A run-scoped decision rewrites the RECORD, so it carries the record's `ETag`.

    And it is scoped: the record's own view of the same address name does not
    inherit the run's decision, and vice versa.
    """
    experiment_id = _experiment(client, {ADDRESS: _envelope("LiFePO4", "LiFePO3")})
    run_id = _with_run(client, experiment_id, {ADDRESS: _envelope("LiFePO4", "LiMnPO4")})
    resolution = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        run_id=run_id,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiMnPO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert resolution["run_id"] == run_id
    assert resolution["state"] == cr.RESOLUTION_CURRENT
    # The run's view is decided; the record's own conflict at the same address name
    # is untouched, because they are different disagreements over different evidence.
    assert _only(_listed(client, experiment_id, run=run_id))["resolved"] is True
    assert _only(_listed(client, experiment_id))["resolved"] is False
    assert _only(_listed(client, experiment_id))["resolution"] is None
    # ONE record-level list holds it, run-scoped rows distinguished by `run_id`.
    stored = _stored(client, experiment_id)["draft"][cr.DRAFT_KEY]
    assert [row["run_id"] for row in stored] == [run_id]


def test_a_decision_naming_a_run_this_record_does_not_have_is_a_typed_422(
    client, experiment_id
):
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        run_id="01JQZZZZZZZZZZZZZZZZZZZZZZ",
        outcome=cr.OUTCOME_DEFERRED,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


# --- 3. recording a decision ---------------------------------------------------


def test_choosing_one_of_the_competing_answers_is_recorded_and_clears_the_conflict(
    client, experiment_id
):
    resolution = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
        rationale="the second entry was a typo",
    )
    assert resolution["outcome"] == cr.OUTCOME_RESOLVED
    assert resolution["chosen_value"] == "LiFePO4"
    assert resolution["chosen_from"] == cr.CHOSEN_FROM_CANDIDATE
    assert resolution["rationale"] == "the second entry was a typo"
    assert resolution["competing_values"] == sorted(
        {json.dumps("LiFePO3"), json.dumps("LiFePO4")}
    )
    assert resolution["state"] == cr.RESOLUTION_CURRENT
    assert resolution["stale"] is False
    # A decision is not a value and not a citation, and it says so on the wire.
    assert resolution["is_field_value"] is False
    assert resolution["is_evidence"] is False
    # NOBODY IS NAMED. This deployment establishes no actor, so the row names none.
    assert resolution["trust_basis"] == "unattributed"
    assert resolution["subject"] is None
    assert resolution["attributed"] is False
    assert [act["action"] for act in resolution["history"]] == [cr.ACTION_RECORD]

    entry = _only(_listed(client, experiment_id))
    # STILL LISTED. The competing citations are still stored, so the address goes on
    # classifying as conflicting; hiding it would hide the decision with it.
    assert entry["resolved"] is True
    assert entry["resolution_state"] == cr.RESOLUTION_CURRENT
    assert entry["resolution"]["resolution_id"] == resolution["resolution_id"]
    counts = _listed(client, experiment_id)["counts"]
    assert counts == {
        "conflicting_addresses": 1,
        "resolved": 1,
        "deferred": 0,
        "stale": 0,
        "unresolved": 0,
    }


def test_an_edited_decision_records_a_value_none_of_the_answers_carried(
    client, experiment_id
):
    """"I picked the second citation" and "all of them are wrong" are different claims."""
    resolution = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4 (hydrated)",
        chosen_from=cr.CHOSEN_FROM_EDITED,
    )
    assert resolution["chosen_from"] == cr.CHOSEN_FROM_EDITED
    assert resolution["chosen_value"] == "LiFePO4 (hydrated)"
    assert json.dumps("LiFePO4 (hydrated)") not in resolution["competing_values"]
    assert resolution["state"] == cr.RESOLUTION_CURRENT
    assert _only(_listed(client, experiment_id))["resolved"] is True


def test_a_candidate_value_that_is_none_of_the_competing_answers_is_refused(
    client, experiment_id
):
    """A value nothing asserted may not be attributed to a citation.

    MUTATION, AND WHAT IT ACTUALLY PROVED — which is not what was expected, so the
    expectation is recorded as corrected rather than quietly replaced. The guard's
    condition in `routes.post_conflict_resolution` was forced to `False` and the
    suite re-run. The request did NOT succeed: the model's own `__post_init__`
    refuses the same shape, so the response stayed `422` and the STATUS assertion
    stayed green. It failed on the next line —
    `assert 'unsupported_resolution' == 'chosen_value_not_a_candidate'` — and
    `test_a_corrected_request_succeeds_after_a_refusal_with_the_same_validator`
    went RED with it, for the same reason. That is exactly why this file asserts
    the specific `error` string: a status-only assertion would have passed the
    mutation and proved nothing about the route's own guard. The condition was
    restored and all 66 tests pass again.
    """
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiCoO2",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "chosen_value_not_a_candidate"
    assert body["candidate_count"] == 2
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


def test_deferring_records_the_decision_and_does_not_clear_the_conflict(
    client, experiment_id
):
    """A person may look and decline to decide. That is an outcome, not an absence."""
    resolution = _resolved(
        client, experiment_id, address=ADDRESS, outcome=cr.OUTCOME_DEFERRED
    )
    assert resolution["outcome"] == cr.OUTCOME_DEFERRED
    assert resolution["chosen_value"] is None
    assert resolution["chosen_from"] is None
    assert resolution["state"] == cr.RESOLUTION_DEFERRED

    body = _listed(client, experiment_id)
    entry = _only(body)
    assert entry["resolution_state"] == cr.RESOLUTION_DEFERRED
    assert entry["resolved"] is False
    assert entry["resolution_stale"] is False
    assert entry["resolution"]["outcome"] == cr.OUTCOME_DEFERRED
    assert body["counts"] == {
        "conflicting_addresses": 1,
        "resolved": 0,
        "deferred": 1,
        "stale": 0,
        "unresolved": 1,
    }


def test_a_deferred_decision_may_not_carry_a_choice(client, experiment_id):
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_DEFERRED,
        chosen_value="LiFePO4",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "deferred_carries_no_choice"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


def test_recording_a_decision_does_not_change_the_field_value(client, experiment_id):
    """THE CHOSEN VALUE IS NOT WRITTEN INTO THE FIELD, and that is deliberate.

    Recording which recorded answer a person chose and writing that answer into the
    field are two different acts, and this application has exactly one path for the
    second (a confirmed answer or edit, stored as user-confirmation evidence).
    """
    before = copy.deepcopy(_stored(client, experiment_id)["draft"]["fields"])
    _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO3",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    after = _stored(client, experiment_id)["draft"]["fields"]
    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)
    assert after[ADDRESS]["value"] == "LiFePO4"


def test_the_evidence_payload_is_byte_identical_before_and_after_a_decision(
    client, experiment_id
):
    """No route in this application removes or rewrites an evidence entry."""
    def evidence_payload() -> str:
        response = client.get(f"/api/experiments/{experiment_id}/evidence")
        assert response.status_code == 200, response.text
        return json.dumps(response.json(), sort_keys=True)

    before = evidence_payload()
    _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert evidence_payload() == before


# --- 4. revising, idempotence, and staleness -----------------------------------


def test_revising_a_decision_appends_and_keeps_what_it_superseded(
    client, experiment_id
):
    first = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    second = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO3",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    # ONE decision per address, revised in place — not two competing rows.
    assert second["resolution_id"] == first["resolution_id"]
    assert second["recorded_utc"] == first["recorded_utc"]
    assert second["chosen_value"] == "LiFePO3"
    assert [act["action"] for act in second["history"]] == [
        cr.ACTION_RECORD,
        cr.ACTION_REVISE,
    ]
    revision = second["history"][-1]
    assert revision["from_outcome"] == cr.OUTCOME_RESOLVED
    assert revision["to_outcome"] == cr.OUTCOME_RESOLVED
    assert revision["superseded_chosen_value"] == "LiFePO4"
    assert revision["superseded_competing_digest"] == first["competing_digest"]
    assert len(_stored(client, experiment_id)["draft"][cr.DRAFT_KEY]) == 1


def test_a_decision_may_be_revised_from_deferred_to_resolved(client, experiment_id):
    _resolved(client, experiment_id, address=ADDRESS, outcome=cr.OUTCOME_DEFERRED)
    revised = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert revised["state"] == cr.RESOLUTION_CURRENT
    revision = revised["history"][-1]
    assert revision["from_outcome"] == cr.OUTCOME_DEFERRED
    # A revision AWAY from deferred superseded no value, and `from_outcome` is what
    # disambiguates that from "superseded a value we failed to record".
    assert revision["superseded_chosen_value"] is None


def test_resubmitting_an_identical_decision_adds_no_history_and_moves_no_revision(
    client, experiment_id
):
    """A double-click is not an audit event."""
    body = dict(
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    first = _resolved(client, experiment_id, **body)
    tag = _etag(client, experiment_id)
    again = _resolved(client, experiment_id, **body)
    assert again == first
    assert _etag(client, experiment_id) == tag


def test_resubmitting_an_identical_decision_is_byte_stable_with_two_decisions_stored(
    client,
):
    """The upsert keeps a row's POSITION, which is what makes the no-op a no-op.

    With two decisions stored, removing the upserted row and appending it would
    reorder the list, rewrite the record and advance its revision — an audit event
    produced by a second click on the FIRST of two conflicts.
    """
    experiment_id = _experiment(
        client,
        {
            ADDRESS: _envelope("LiFePO4", "LiFePO3"),
            CLEAN_ADDRESS: _envelope("powder", "pellet"),
        },
    )
    first = dict(
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    _resolved(client, experiment_id, **first)
    _resolved(
        client,
        experiment_id,
        address=CLEAN_ADDRESS,
        outcome=cr.OUTCOME_DEFERRED,
    )
    stored = _stored(client, experiment_id)["draft"][cr.DRAFT_KEY]
    assert [row["address"] for row in stored] == [ADDRESS, CLEAN_ADDRESS]
    tag = _etag(client, experiment_id)
    _resolved(client, experiment_id, **first)
    assert _etag(client, experiment_id) == tag
    stored_again = _stored(client, experiment_id)["draft"][cr.DRAFT_KEY]
    assert [row["address"] for row in stored_again] == [ADDRESS, CLEAN_ADDRESS]


def _append_answer(client, experiment_id: str, value) -> None:
    """Append one more competing answer to ``ADDRESS``, as the answer routes do."""
    store = client_ws(client)
    with store.record_lock(experiment_id):
        exp = store.load_experiment(experiment_id)
        exp.draft["fields"][ADDRESS]["evidence"].append(_answer(value))
        exp.save_versioned()


def test_a_third_answer_makes_an_earlier_decision_stale_without_deleting_it(
    client, experiment_id
):
    """A decision is about a SPECIFIC set of competing answers.

    When a third arrives the decision no longer covers the disagreement a reader is
    looking at, so the address returns to conflicting — and the superseded decision
    is still there, in full, because presenting it as gone would lose a recorded
    human act.
    """
    resolution = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert _only(_listed(client, experiment_id))["resolved"] is True

    _append_answer(client, experiment_id, "LiMnPO4")

    body = _listed(client, experiment_id)
    entry = _only(body)
    assert entry["distinct_value_count"] == 3
    assert entry["resolution_state"] == cr.RESOLUTION_STALE
    assert entry["resolved"] is False
    assert entry["resolution_stale"] is True
    # STILL VISIBLE, and still saying exactly what was decided and over what.
    assert entry["resolution"]["resolution_id"] == resolution["resolution_id"]
    assert entry["resolution"]["chosen_value"] == "LiFePO4"
    assert entry["resolution"]["competing_values"] == resolution["competing_values"]
    assert entry["resolution"]["stale"] is True
    assert body["counts"] == {
        "conflicting_addresses": 1,
        "resolved": 0,
        "deferred": 0,
        "stale": 1,
        "unresolved": 1,
    }
    # And it can be decided again over the new set, which appends rather than
    # replacing the superseded decision.
    revised = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiMnPO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert revised["state"] == cr.RESOLUTION_CURRENT
    assert revised["history"][-1]["superseded_competing_digest"] == (
        resolution["competing_digest"]
    )


def test_a_deferred_decision_is_reported_deferred_even_after_the_answers_move_on(
    client, experiment_id
):
    """Staleness is not modelled for `deferred`, deliberately.

    A deferred decision covers nothing in the first place, so the address stays
    conflicting either way and a `deferred_stale` member would be a distinction
    with no consumer.
    """
    _resolved(client, experiment_id, address=ADDRESS, outcome=cr.OUTCOME_DEFERRED)
    _append_answer(client, experiment_id, "LiMnPO4")
    entry = _only(_listed(client, experiment_id))
    assert entry["resolution_state"] == cr.RESOLUTION_DEFERRED
    assert entry["resolved"] is False


def test_a_decision_whose_address_stops_conflicting_is_reported_not_dropped(client):
    """The other direction: a stored decision this subject has no conflict at.

    It cannot happen through the routes as they stand — nothing removes evidence —
    but a decision recorded against a run and read at record scope produces exactly
    this shape, and silently omitting it would hide a recorded human act.
    """
    experiment_id = _experiment(client, {ADDRESS: _envelope("LiFePO4", "LiFePO3")})
    run_id = _with_run(client, experiment_id, {ADDRESS: _envelope("LiFePO4", "LiMnPO4")})
    resolution = _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        run_id=run_id,
        outcome=cr.OUTCOME_DEFERRED,
    )
    # Read the RUN, then remove the run's own conflicting evidence entirely.
    store = client_ws(client)
    with store.record_lock(experiment_id):
        exp = store.load_experiment(experiment_id)
        exp.get_run(run_id).draft["fields"].pop(ADDRESS)
        exp.save_versioned()
    body = _listed(client, experiment_id, run=run_id)
    assert body["conflicts"] == []
    assert body["resolutions_without_conflict"] == [
        {
            "address": ADDRESS,
            "run_id": run_id,
            "outcome": cr.OUTCOME_DEFERRED,
            "resolution_id": resolution["resolution_id"],
        }
    ]


def test_a_stored_decision_this_build_cannot_read_is_counted_and_preserved(
    client, experiment_id
):
    """Never dropped, never invented, and disclosed as a count rather than rendered."""
    store = client_ws(client)
    with store.record_lock(experiment_id):
        exp = store.load_experiment(experiment_id)
        exp.draft[cr.DRAFT_KEY] = [{"resolution_id": "x"}, "not even an object"]
        exp.save_versioned()
    body = _listed(client, experiment_id)
    assert body["unreadable_resolution_entries"] == 2
    assert _only(body)["resolution"] is None
    # A later write preserves them verbatim, at the end.
    _resolved(client, experiment_id, address=ADDRESS, outcome=cr.OUTCOME_DEFERRED)
    stored = _stored(client, experiment_id)["draft"][cr.DRAFT_KEY]
    assert stored[-2:] == [{"resolution_id": "x"}, "not even an object"]
    assert _listed(client, experiment_id)["unreadable_resolution_entries"] == 2


# --- 5. preconditions and the race --------------------------------------------


def test_a_decision_with_no_if_match_is_a_428_and_writes_nothing(
    client, experiment_id
):
    response = _resolve(
        client, experiment_id, if_match=None, address=ADDRESS, outcome=cr.OUTCOME_DEFERRED
    )
    assert response.status_code == 428, response.text
    assert response.json()["error"] == "precondition_required"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


def test_a_malformed_if_match_is_a_400_and_writes_nothing(client, experiment_id):
    response = _resolve(
        client,
        experiment_id,
        if_match='W/"weak"',
        address=ADDRESS,
        outcome=cr.OUTCOME_DEFERRED,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "malformed_if_match"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


def test_a_stale_if_match_is_a_412_and_the_earlier_decision_survives(
    client, experiment_id
):
    """The validator this client holds is no longer the record's."""
    stale_tag = _etag(client, experiment_id)
    _resolved(client, experiment_id, address=ADDRESS, outcome=cr.OUTCOME_DEFERRED)
    response = _resolve(
        client,
        experiment_id,
        if_match=stale_tag,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert response.status_code == 412, response.text
    assert response.json()["error"] == "stale_write"
    stored = _stored(client, experiment_id)["draft"][cr.DRAFT_KEY]
    assert [row["outcome"] for row in stored] == [cr.OUTCOME_DEFERRED]


def test_two_writers_holding_one_validator_produce_one_decision(client, experiment_id):
    """CONCURRENT RESOLUTION: one wins, the other is refused, nothing is merged.

    STATED PRECISELY: the race is reproduced deterministically by giving both
    writers the SAME pre-write validator, which is exactly the state two browser
    tabs are in. It does not exercise thread interleaving inside the handler — the
    lock that governs that is `workspace.record_lock`, covered by
    `test_handler_concurrency.py` — and this test does not claim to.
    """
    shared_tag = _etag(client, experiment_id)
    winner = _resolve(
        client,
        experiment_id,
        if_match=shared_tag,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert winner.status_code == 200, winner.text
    loser = _resolve(
        client,
        experiment_id,
        if_match=shared_tag,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO3",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert loser.status_code == 412, loser.text
    assert loser.json()["error"] == "stale_write"
    stored = _stored(client, experiment_id)["draft"][cr.DRAFT_KEY]
    assert len(stored) == 1
    assert stored[0]["chosen_value"] == "LiFePO4"
    assert [act["action"] for act in stored[0]["history"]] == [cr.ACTION_RECORD]


# --- 6. every refusal, by name -------------------------------------------------


@pytest.mark.parametrize("body", [[], "a string", 7, None])
def test_a_body_that_is_not_an_object_is_a_typed_422(client, experiment_id, body):
    """A wrong-typed body is refused by name, never with a traceback.

    `complete.py` once answered a wrong-typed structured value with HTTP 500 out of
    the truth core; the guard here exists so that shape cannot recur.
    """
    response = client.post(
        f"/api/experiments/{experiment_id}/conflicts/resolve",
        json=body,
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.text
    # FastAPI validates the declared `dict` body first for some of these, so the
    # error is either this feature's own or the framework's — both are 422, and
    # neither is a 500. When it IS ours, it is named.
    payload = response.json()
    assert payload.get("error") in (None, "invalid_body"), payload
    if payload.get("error") is None:
        assert "detail" in payload, payload
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


def test_an_unrecognised_body_key_is_refused_by_name(client, experiment_id):
    """A decision cannot be ASKED to be a value, not merely refused when it tries."""
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_DEFERRED,
        applied=True,
        verified=True,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field"
    assert body["keys"] == ["applied", "verified"]
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


@pytest.mark.parametrize("confirmation", [None, False, "true", 1])
def test_a_decision_without_an_explicit_confirmation_is_refused(
    client, experiment_id, confirmation
):
    """NOTHING PICKS A WINNER. A chosen value arrives only with an explicit `true`."""
    body = dict(
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    if confirmation is not None:
        body["confirmed_by_user"] = confirmation
    else:
        body["confirmed_by_user"] = None
    response = _resolve(client, experiment_id, **body)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "confirmation_required"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


@pytest.mark.parametrize("outcome", [None, "", "applied", "RESOLVED", 7])
def test_an_unknown_outcome_is_refused_with_the_allowed_set(
    client, experiment_id, outcome
):
    response = _resolve(client, experiment_id, address=ADDRESS, outcome=outcome)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unknown_resolution_outcome"
    assert body["allowed"] == list(cr.RESOLUTION_OUTCOMES)
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


@pytest.mark.parametrize("chosen_from", [None, "candidates", "typed", 7])
def test_an_unknown_chosen_from_is_refused_with_the_allowed_set(
    client, experiment_id, chosen_from
):
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=chosen_from,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unknown_chosen_from"
    assert body["allowed"] == list(cr.CHOSEN_FROM_VALUES)


def test_a_resolved_outcome_with_no_chosen_value_is_refused(client, experiment_id):
    """"The system resolved it" is not a state this API can be made to store."""
    response = _resolve(
        client, experiment_id, address=ADDRESS, outcome=cr.OUTCOME_RESOLVED
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "resolution_requires_chosen_value"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


@pytest.mark.parametrize("address", [None, "", "   ", 7, ["a"]])
def test_an_address_that_is_not_an_address_is_refused(client, experiment_id, address):
    response = _resolve(
        client, experiment_id, address=address, outcome=cr.OUTCOME_DEFERRED
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_address"


def test_an_address_this_subject_does_not_describe_is_refused(client, experiment_id):
    response = _resolve(
        client,
        experiment_id,
        address="sample.material.invented_path",
        outcome=cr.OUTCOME_DEFERRED,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unknown_address"
    assert body["address"] == "sample.material.invented_path"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


def test_an_address_that_is_described_but_not_conflicting_is_refused(client):
    """Recording a decision here would assert that a disagreement existed."""
    experiment_id = _experiment(
        client,
        {
            ADDRESS: _envelope("LiFePO4", "LiFePO3"),
            CLEAN_ADDRESS: _envelope("powder"),
        },
    )
    response = _resolve(
        client, experiment_id, address=CLEAN_ADDRESS, outcome=cr.OUTCOME_DEFERRED
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "address_not_conflicting"
    assert body["classification"] == "supported"


@pytest.mark.parametrize("rationale", ["", "   ", 7])
def test_a_blank_or_wrong_typed_rationale_is_refused_not_coerced(
    client, experiment_id, rationale
):
    """Absent is a meaning. A blank would be stored as though somebody wrote a reason."""
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_DEFERRED,
        rationale=rationale,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_rationale"


def test_a_chosen_value_that_could_not_be_read_back_is_refused_not_reshaped(
    client, experiment_id
):
    """A value that cannot round-trip would wedge every later read of the record."""
    response = _resolve(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="x" * (128 * 1024),
        chosen_from=cr.CHOSEN_FROM_EDITED,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    assert cr.DRAFT_KEY not in _stored(client, experiment_id)["draft"]


def test_a_refused_decision_leaves_the_record_byte_identical(client, experiment_id):
    """Every input is resolved BEFORE anything is written, so a refusal is inert."""
    before = json.dumps(_stored(client, experiment_id), sort_keys=True)
    tag = _etag(client, experiment_id)
    for body in (
        dict(address=ADDRESS, outcome="applied"),
        dict(address="nope", outcome=cr.OUTCOME_DEFERRED),
        dict(address=ADDRESS, outcome=cr.OUTCOME_RESOLVED),
        dict(
            address=ADDRESS,
            outcome=cr.OUTCOME_RESOLVED,
            chosen_value="LiCoO2",
            chosen_from=cr.CHOSEN_FROM_CANDIDATE,
        ),
        dict(address=ADDRESS, outcome=cr.OUTCOME_DEFERRED, confirmed_by_user=False),
    ):
        response = _resolve(client, experiment_id, **body)
        assert response.status_code == 422, (body, response.text)
    assert json.dumps(_stored(client, experiment_id), sort_keys=True) == before
    assert _etag(client, experiment_id) == tag


def test_a_corrected_request_succeeds_after_a_refusal_with_the_same_validator(
    client, experiment_id
):
    """RETRY AFTER REFUSAL. A refused request wrote nothing, so the client's `ETag`
    is still current and the corrected request needs no extra round trip."""
    tag = _etag(client, experiment_id)
    refused = _resolve(
        client,
        experiment_id,
        if_match=tag,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiCoO2",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "chosen_value_not_a_candidate"
    accepted = _resolve(
        client,
        experiment_id,
        if_match=tag,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiCoO2",
        chosen_from=cr.CHOSEN_FROM_EDITED,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["resolution"]["chosen_from"] == cr.CHOSEN_FROM_EDITED


def test_a_decision_on_an_unknown_experiment_is_a_404(client):
    response = client.post(
        "/api/experiments/01JQZZZZZZZZZZZZZZZZZZZZZZ/conflicts/resolve",
        json={"address": ADDRESS, "outcome": cr.OUTCOME_DEFERRED, "confirmed_by_user": True},
        headers={"If-Match": '"whatever.1"'},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


# --- 7. nothing reaches an official record ------------------------------------


def test_the_official_transform_ignores_the_decisions_key(client, experiment_id):
    """`transform` reads only the keys it names, so a decision cannot be exported."""
    _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    draft = _stored(client, experiment_id)["draft"]
    assert cr.DRAFT_KEY in draft
    record = transform(draft, record_id="01JQZZZZZZZZZZZZZZZZZZZZZZ")
    assert cr.DRAFT_KEY not in record
    assert cr.DRAFT_KEY not in json.dumps(record)


def test_an_exported_record_carries_no_conflict_resolutions_key(client):
    """End to end, through the real export route, over an export-ready record.

    The decision is written straight into the record's draft here rather than
    through the route, because this test is about what EXPORT does with the key —
    the export-ready example record carries no conflict to resolve, and inventing
    one would change what is being exported.
    """
    store = client_ws(client)
    experiment_id = ws.SEED_READY_ID
    with store.record_lock(experiment_id):
        exp = store.load_experiment(experiment_id)
        assert exp is not None, "the worked-example session did not materialise"
        cr.write_resolution(
            exp.draft,
            cr.new_resolution(
                resolution_id="01JQZZZZZZZZZZZZZZZZZZZZZZ",
                address=ADDRESS,
                outcome=cr.OUTCOME_RESOLVED,
                competing_values=(json.dumps("a"), json.dumps("b")),
                recorded_utc="2026-01-01T00:00:00Z",
                trust_basis="unattributed",
                chosen_value="a",
                chosen_from=cr.CHOSEN_FROM_CANDIDATE,
            ),
        )
        exp.save_versioned()

    response = client.post(
        f"/api/experiments/{experiment_id}/export",
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True, response.text

    exp = store.load_experiment(experiment_id)
    record_text = exp.record_path().read_text()
    sidecar_text = exp.sidecar_path().read_text()
    assert cr.DRAFT_KEY not in record_text
    assert cr.DRAFT_KEY not in sidecar_text
    assert cr.DRAFT_KEY in exp.draft, "the decision itself is still in the draft"


# --- 8. the provenance view reads the same decision ----------------------------


def test_provenance_reports_a_decided_conflict_as_resolved_and_a_stale_one_as_conflict(
    client, experiment_id
):
    """The fifth review state is reachable, and staleness falls back to `conflict`.

    A stale decision needs no review state of its own: it reads `conflict`, which
    is exactly the answer a reader needs, and the staleness itself travels as
    `resolution_state` on the entry.
    """
    def entry_for(address: str) -> dict:
        response = client.get(f"/api/experiments/{experiment_id}/provenance")
        assert response.status_code == 200, response.text
        found = [e for e in response.json()["entries"] if e["address"] == address]
        assert len(found) == 1, found
        return found[0]

    before = entry_for(ADDRESS)
    assert before["review_state"] == provenance.REVIEW_CONFLICT
    assert before["resolution_state"] == cr.RESOLUTION_ABSENT

    _resolved(
        client,
        experiment_id,
        address=ADDRESS,
        outcome=cr.OUTCOME_RESOLVED,
        chosen_value="LiFePO4",
        chosen_from=cr.CHOSEN_FROM_CANDIDATE,
    )
    decided = entry_for(ADDRESS)
    assert decided["review_state"] == provenance.REVIEW_RESOLVED
    assert decided["resolution_state"] == cr.RESOLUTION_CURRENT

    _append_answer(client, experiment_id, "LiMnPO4")
    stale = entry_for(ADDRESS)
    assert stale["review_state"] == provenance.REVIEW_CONFLICT
    assert stale["resolution_state"] == cr.RESOLUTION_STALE
