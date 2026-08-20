"""Manual transcript capture — the reader, the three operations, and their refusals.

WHAT THIS FEATURE PROMISES, AND WHERE EACH PROMISE IS HELD HERE
===============================================================

1. **Authoritative metadata never moves from unfinished text.** There is no
   operation that reads a transcript without an explicit finalize, and typing
   alone reaches no operation at all.
   (``test_typing_alone_writes_nothing``,
   ``test_reading_a_transcript_without_finalize_is_refused_and_stores_nothing``)
2. **A candidate is never a value.** The reader emits the existing
   ``FieldCandidate``, whose four constants are unconstructible otherwise, and the
   operation writes no field anywhere.
   (``test_a_candidate_is_never_presented_as_a_value``,
   ``test_reading_a_transcript_writes_no_draft_field``)
3. **An ambiguous run or field reference is never resolved by preference.** Each
   of the four outcomes has its own test.
   (``test_no_run_selected_asks_which_run``, ``test_a_run_this_record_does_not_have_is_a_clarification``,
   ``test_a_reference_matching_two_runs_is_a_clarification``,
   ``test_a_run_other_than_the_selected_one_is_a_clarification``,
   ``test_a_positional_run_reference_is_a_clarification``,
   ``test_two_values_for_one_field_are_both_returned_for_review``,
   ``test_a_temperature_in_another_unit_is_an_abstention``,
   ``test_the_absorption_edge_is_an_abstention``,
   ``test_text_no_rule_matched_becomes_an_unmapped_note``)
4. **Scientist-entered text is never silently discarded.** Every segment is
   stored, so neither a failed reading nor a failed acceptance can lose it.
   (``test_text_survives_a_reading_that_proposed_nothing``,
   ``test_text_survives_a_failed_accept``, ``test_every_segment_becomes_a_note``)
5. **An unconfigured seam says so and claims nothing.**
   (``test_transcription_is_reported_as_unconfigured``,
   ``test_no_seam_reports_a_configured_provider``,
   ``test_the_transcription_operation_refuses_and_names_what_is_missing``)

Everything here is synthetic. No file outside the tmp workspace is read or
written, nothing connects to a database, and no network call is made — the one
operation that names a provider resolves the unconfigured implementation, which
by construction contacts nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

import isaac_api.notes as notes
import isaac_api.routes as routes
import isaac_api.transcript_capture as tc
from isaac_api.providers import base as provider_base
from isaac_api.providers import config as provider_config
from isaac_api.providers.extraction import FieldCandidate

from conftest import client_ws, tutorial_client


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
        "Transcript fixture", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
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


def _finalize(client, experiment_id: str, text: str, *, run_id: str | None = None, **extra):
    body: dict = {"text": text, "finalized": True}
    if run_id is not None:
        body["run_id"] = run_id
    body.update(extra)
    return client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json=body,
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _notes(client, experiment_id: str) -> list[dict]:
    response = client.get(f"/api/experiments/{experiment_id}/notes")
    assert response.status_code == 200, response.text
    return response.json()["notes"]


def _kinds(entries: list[dict]) -> set[str]:
    return {entry["kind"] for entry in entries}


#: A transcript whose every proposal is unambiguous, used wherever the test is
#: about something other than ambiguity.
CLEAN = "Temperature was 300 K. Atmosphere was: dry nitrogen"


# --- 1. nothing moves from unfinished text ------------------------------------


def test_typing_alone_writes_nothing(client, experiment_id):
    """Typing reaches no operation, so it can change nothing.

    The strongest form of the claim is structural rather than behavioural: this
    asserts the record's revision and note count after a read-only browse, and
    that the ONLY operation that reads a transcript is the finalize one — there is
    no draft/preview/debounce endpoint for a client to call per keystroke.

    MUTATION: adding a second `POST .../transcript/preview` route that captures
    notes turns the path assertion RED.
    """
    before = client.get(f"/api/experiments/{experiment_id}").json()
    assert _notes(client, experiment_id) == []

    paths = {
        route.path
        for route in routes.router.routes
        if "transcript" in getattr(route, "path", "")
    }
    assert paths == {
        "/api/transcription",
        "/api/experiments/{experiment_id}/transcript",
    }, paths

    after = client.get(f"/api/experiments/{experiment_id}").json()
    assert after["rev"] == before["rev"]
    assert _notes(client, experiment_id) == []


def test_reading_a_transcript_without_finalize_is_refused_and_stores_nothing(
    client, experiment_id
):
    """MUTATION: deleting the `finalized is not True` branch turns this RED."""
    run = _make_run(client, experiment_id)
    before = client.get(f"/api/experiments/{experiment_id}").json()
    response = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": CLEAN, "run_id": run["id"]},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "finalize_required"
    assert _notes(client, experiment_id) == []
    assert client.get(f"/api/experiments/{experiment_id}").json()["rev"] == before["rev"]


def test_finalize_false_is_refused_exactly_as_an_absent_one(client, experiment_id):
    run = _make_run(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": CLEAN, "finalized": False, "run_id": run["id"]},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "finalize_required"
    assert _notes(client, experiment_id) == []


def test_the_finalize_gate_is_checked_before_the_precondition(client, experiment_id):
    """An unfinalized request is refused whether or not the caller's tag is current.

    The ordering matters: if the precondition were checked first, a client could
    learn that its unfinalized request "would have worked", and a stale-tag retry
    loop would eventually read text nobody finalized.
    """
    response = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": CLEAN},
        headers={"If-Match": '"nope-not-current"'},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "finalize_required"


# --- 2. a candidate is never a value ------------------------------------------


def test_a_candidate_is_never_presented_as_a_value(client, experiment_id):
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    assert payload["candidates"], payload
    for candidate in payload["candidates"]:
        assert candidate["status"] == "needs_confirmation"
        assert candidate["verified"] is False
        assert candidate["is_evidence"] is False
        assert candidate["requires_user_confirmation"] is True
    assert payload["applied"] is False


def test_the_reader_reuses_the_existing_candidate_type_rather_than_a_parallel_one():
    """MUTATION: defining a local candidate dataclass in `transcript_capture`
    and returning it instead turns this RED."""
    reading = tc.read_transcript(
        CLEAN,
        selected_run="run-1",
        known_runs=(tc.RunRef(id="run-1", label="Run 1", ordinal=1),),
    )
    assert reading.candidates
    for candidate in reading.candidates:
        assert isinstance(candidate, FieldCandidate)


def test_a_reader_candidate_cannot_be_made_to_present_as_confirmed():
    reading = tc.read_transcript(
        CLEAN,
        selected_run="run-1",
        known_runs=(tc.RunRef(id="run-1", label="Run 1", ordinal=1),),
    )
    candidate = reading.candidates[0]
    with pytest.raises(TypeError):
        dataclasses.replace(candidate, verified=True)
    with pytest.raises((TypeError, dataclasses.FrozenInstanceError)):
        candidate.verified = True  # type: ignore[misc]
    with pytest.raises(AttributeError):
        object.__setattr__(candidate, "verified", True)


def test_reading_a_transcript_writes_no_draft_field(client, experiment_id):
    """The record's draft fields are untouched; only notes appear.

    MUTATION: making the operation call `apply_corrections` with the candidates
    turns this RED.
    """
    run = _make_run(client, experiment_id)
    before = client.get(f"/api/experiments/{experiment_id}/draft").json()
    response = _finalize(client, experiment_id, CLEAN, run_id=run["id"])
    assert response.status_code == 200, response.text
    after = client.get(f"/api/experiments/{experiment_id}/draft").json()
    assert after == before

    run_after = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()
    assert run_after["run"]["fields"] == {}


def test_the_operation_states_where_accepting_actually_writes(client, experiment_id):
    run = _make_run(client, experiment_id)
    contract = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()[
        "accept_contract"
    ]
    assert contract["method"] == "PATCH"
    assert contract["path"] == "/api/experiments/{experiment_id}/runs/{run_id}"
    assert "confirmed_by_user: true" in contract["requires"]


def test_every_proposable_path_is_one_the_run_edit_will_actually_write():
    """A candidate a scientist cannot accept is a control with one outcome.

    MUTATION: adding a rule for an experiment-level path (`sample.sample_form`)
    to the reader's table makes `routes` fail to import, which turns every test
    in this file RED — which is the point of putting the check at import.
    """
    assert tc.READABLE_FIELD_PATHS
    assert tc.READABLE_FIELD_PATHS <= routes.RUN_WRITABLE_FIELD_PATHS


# --- 3. ambiguity: the clarification outcome ----------------------------------


def test_no_run_selected_asks_which_run(client, experiment_id):
    _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN).json()
    assert "run_target_required" in _kinds(payload["clarifications"])
    assert payload["candidates"] == []
    assert len(_notes(client, experiment_id)) == 2


def test_the_only_run_is_never_chosen_automatically(client, experiment_id):
    """One run is not an exception, and this is the sentence the note model
    already enforces from the other direction.

    MUTATION: defaulting `selected_run` to the single run turns this RED.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN).json()
    assert "run_target_required" in _kinds(payload["clarifications"])
    assert payload["candidates"] == []
    options = payload["clarifications"][0]["options"]
    assert [entry["run_id"] for entry in options] == [run["id"]]


def test_a_run_this_record_does_not_have_is_a_clarification(client, experiment_id):
    run = _make_run(client, experiment_id, label="Alpha")
    payload = _finalize(
        client,
        experiment_id,
        "This is run 47. Temperature was 300 K.",
        run_id=run["id"],
    ).json()
    assert "unknown_run_reference" in _kinds(payload["clarifications"])
    assert payload["candidates"] == []
    assert len(_notes(client, experiment_id)) == 2


def test_a_reference_matching_two_runs_is_a_clarification(client, experiment_id):
    first = _make_run(client, experiment_id, label="Cooling sweep")
    _make_run(client, experiment_id, label="Cooling repeat")
    payload = _finalize(
        client, experiment_id, "Notes for run Cooling. Temperature was 300 K.",
        run_id=first["id"],
    ).json()
    entries = [
        entry
        for entry in payload["clarifications"]
        if entry["kind"] == "ambiguous_run_reference"
    ]
    assert entries, payload["clarifications"]
    assert len(entries[0]["options"]) == 2
    assert payload["candidates"] == []


def test_a_run_other_than_the_selected_one_is_a_clarification(client, experiment_id):
    first = _make_run(client, experiment_id, label="Alpha")
    second = _make_run(client, experiment_id, label="Beta")
    payload = _finalize(
        client, experiment_id, "Notes for run Beta. Temperature was 300 K.",
        run_id=first["id"],
    ).json()
    entries = [
        entry
        for entry in payload["clarifications"]
        if entry["kind"] == "conflicting_run_reference"
    ]
    assert entries, payload["clarifications"]
    assert {entry["run_id"] for entry in entries[0]["options"]} == {
        first["id"],
        second["id"],
    }
    assert payload["candidates"] == []


def test_a_positional_run_reference_is_a_clarification(client, experiment_id):
    run = _make_run(client, experiment_id)
    _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "Repeating the second run. Temperature was 300 K.",
        run_id=run["id"],
    ).json()
    assert "vague_run_reference" in _kinds(payload["clarifications"])
    assert payload["candidates"] == []


def test_an_unsettled_run_withholds_candidates_but_keeps_every_word(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    text = "This is run 47. Temperature was 300 K. Atmosphere was: dry nitrogen"
    payload = _finalize(client, experiment_id, text, run_id=run["id"]).json()
    assert payload["candidates"] == []
    stored = [note["text"] for note in _notes(client, experiment_id)]
    assert len(stored) == 3
    assert "".join(stored).count("300 K") == 1
    assert any("dry nitrogen" in entry for entry in stored)


def test_ordinary_uses_of_the_word_run_are_not_read_as_references(
    client, experiment_id
):
    """'the run was repeated' names no run, and reporting one would put a
    clarification on nearly every sentence a scientist dictates."""
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "The run was repeated. Temperature was 300 K.",
        run_id=run["id"],
    ).json()
    assert payload["clarifications"] == []
    assert [entry["field_path"] for entry in payload["candidates"]] == [
        "context.temperature_K"
    ]


# --- 3b. ambiguity: the needs-review outcome ----------------------------------


def test_two_values_for_one_field_are_both_returned_for_review(client, experiment_id):
    """MUTATION: keeping only the last candidate per path turns this RED."""
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "Temperature was 300 K. Later the temperature was 320 K.",
        run_id=run["id"],
    ).json()
    review = payload["review_required"]
    assert len(review) == 1, payload
    assert review[0]["kind"] == "conflicting_values_for_one_field"
    assert review[0]["outcome"] == "needs_review"
    assert review[0]["field_path"] == "context.temperature_K"
    assert sorted(review[0]["candidate_indexes"]) == [0, 1]
    values = {payload["candidates"][i]["proposed_value"] for i in [0, 1]}
    assert values == {300, 320}


def test_the_same_value_said_twice_is_not_a_conflict(client, experiment_id):
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "Temperature was 300 K. To confirm, temperature was 300 K.",
        run_id=run["id"],
    ).json()
    assert payload["review_required"] == []
    assert len(payload["candidates"]) == 2


# --- 3c. ambiguity: the abstention outcome ------------------------------------


def test_a_temperature_in_another_unit_is_an_abstention(client, experiment_id):
    """MUTATION: converting Celsius to kelvin turns this RED — and would put a
    number in the record that nobody stated."""
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client, experiment_id, "Temperature was 25 C.", run_id=run["id"]
    ).json()
    assert payload["candidates"] == []
    assert _kinds(payload["abstentions"]) == {"temperature_not_in_kelvin"}
    assert payload["abstentions"][0]["outcome"] == "abstention"


def test_the_absorption_edge_is_an_abstention(client, experiment_id):
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "We measured the Cu K-edge on this sample.",
        run_id=run["id"],
    ).json()
    assert _kinds(payload["abstentions"]) == {"implicit_only_subject"}
    assert payload["candidates"] == []


def test_an_abstention_does_not_suppress_a_clean_candidate(client, experiment_id):
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "We measured the Cu K-edge. Temperature was 300 K.",
        run_id=run["id"],
    ).json()
    assert _kinds(payload["abstentions"]) == {"implicit_only_subject"}
    assert [entry["field_path"] for entry in payload["candidates"]] == [
        "context.temperature_K"
    ]


# --- 3d. ambiguity: the unmapped-note outcome ---------------------------------


def test_text_no_rule_matched_becomes_an_unmapped_note(client, experiment_id):
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "The cryostat made an unusual noise about halfway through.",
        run_id=run["id"],
    ).json()
    assert payload["candidates"] == []
    stored = _notes(client, experiment_id)
    assert len(stored) == 1
    assert stored[0]["text"] == "The cryostat made an unusual noise about halfway through."
    assert stored[0]["source"] == "transcript"
    assert stored[0]["state"] == "unreviewed"
    assert stored[0]["candidate_field_path"] is None


def test_every_ambiguity_kind_is_covered_by_the_published_policy():
    """The policy the operation serves must describe the outcomes it produces.

    MUTATION: adding a clarification kind without adding its policy row turns
    this RED.
    """
    published = {entry["kind"] for entry in tc.AMBIGUITY_POLICY}
    outcomes = {entry["outcome"] for entry in tc.AMBIGUITY_POLICY}
    assert outcomes == {
        tc.OUTCOME_CLARIFICATION,
        tc.OUTCOME_NEEDS_REVIEW,
        tc.OUTCOME_ABSTENTION,
        tc.OUTCOME_UNMAPPED,
    }
    assert {
        "run_target_required",
        "unknown_run_reference",
        "ambiguous_run_reference",
        "conflicting_run_reference",
        "vague_run_reference",
        "conflicting_values_for_one_field",
        "temperature_not_in_kelvin",
        "implicit_only_subject",
        "unmatched_text",
    } == published


# --- 4. text is never silently discarded --------------------------------------


def test_every_segment_becomes_a_note(client, experiment_id):
    """Including the segments that produced a candidate. See the module docstring.

    MUTATION: capturing notes only for `unmapped_segment_indexes` turns this RED.
    """
    run = _make_run(client, experiment_id)
    text = "Temperature was 300 K. The cryostat rattled. Atmosphere was: dry nitrogen"
    payload = _finalize(client, experiment_id, text, run_id=run["id"]).json()
    assert payload["capture"]["segments"] == 3
    stored = _notes(client, experiment_id)
    assert [note["text"] for note in stored] == [
        "Temperature was 300 K.",
        "The cryostat rattled.",
        "Atmosphere was: dry nitrogen",
    ]
    assert {note["source"] for note in stored} == {"transcript"}


def test_text_survives_a_reading_that_proposed_nothing(client, experiment_id):
    """A negative control: the reading fails to place anything and loses nothing."""
    run = _make_run(client, experiment_id)
    text = "Nothing here resembles a field. Ambient conditions felt normal."
    payload = _finalize(client, experiment_id, text, run_id=run["id"]).json()
    assert payload["candidates"] == []
    assert payload["review_required"] == []
    assert [note["text"] for note in _notes(client, experiment_id)] == [
        "Nothing here resembles a field.",
        "Ambient conditions felt normal.",
    ]


def test_text_survives_a_failed_accept(client, experiment_id):
    """The acceptance is refused by the run edit, and the words are still stored.

    MUTATION: making the operation store a note only after a successful accept
    (there is no such coupling, and this test is what keeps it that way) turns
    this RED.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    candidate = payload["candidates"][0]

    # A stale run tag: the accept is refused with nothing written.
    refused = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        json={
            "confirmed_by_user": True,
            "fields": {candidate["field_path"]: candidate["proposed_value"]},
        },
        headers={"If-Match": '"0-not-the-current-tag"'},
    )
    assert refused.status_code == 412, refused.text

    stored = _notes(client, experiment_id)
    assert len(stored) == 2
    assert "Temperature was 300 K." in [note["text"] for note in stored]
    fields = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()
    assert fields["run"]["fields"] == {}


def test_text_survives_a_transcript_the_reader_could_not_address(client, experiment_id):
    """Even when every candidate is withheld, every word is stored."""
    _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN).json()
    assert payload["candidates"] == []
    assert len(_notes(client, experiment_id)) == 2


def test_a_transcript_over_the_ceiling_is_refused_whole_not_partly_stored(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    text = " ".join(f"Sentence number {n}." for n in range(tc.MAX_SEGMENTS + 5))
    response = _finalize(client, experiment_id, text, run_id=run["id"])
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "transcript_too_long"
    assert _notes(client, experiment_id) == []


def test_a_blank_transcript_is_refused_rather_than_stored_as_an_empty_note(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": "   ", "finalized": True, "run_id": run["id"]},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_note_text"


# --- 5. the accepted candidate goes through the existing write path -----------


def test_an_accepted_candidate_is_written_by_the_existing_run_edit_with_a_precondition(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    by_path = {
        candidate["field_path"]: candidate["proposed_value"]
        for candidate in payload["candidates"]
    }
    assert by_path == {
        "context.temperature_K": 300,
        "context.thermodynamics.atmosphere": "dry nitrogen",
    }

    fresh = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()
    accepted = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        json={
            "confirmed_by_user": True,
            "fields": {"context.temperature_K": by_path["context.temperature_K"]},
        },
        headers={"If-Match": f'"{fresh["run"]["version"]}"'},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["run"]["fields"]["context.temperature_K"]["value"] == 300


def test_accepting_without_confirmation_is_refused_by_the_existing_write_path(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    payload = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()
    candidate = payload["candidates"][0]
    fresh = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()
    response = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        json={"fields": {candidate["field_path"]: candidate["proposed_value"]}},
        headers={"If-Match": f'"{fresh["run"]["version"]}"'},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "confirmation_required"


def test_the_transcript_operation_requires_the_records_precondition(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    omitted = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": CLEAN, "finalized": True, "run_id": run["id"]},
    )
    assert omitted.status_code == 428, omitted.text
    stale = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": CLEAN, "finalized": True, "run_id": run["id"]},
        headers={"If-Match": '"0-stale"'},
    )
    assert stale.status_code == 412, stale.text
    assert _notes(client, experiment_id) == []


# --- 6. refusals that keep the surface honest ---------------------------------


def test_an_unknown_body_key_is_refused_rather_than_ignored(client, experiment_id):
    run = _make_run(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={
            "text": CLEAN,
            "finalized": True,
            "run_id": run["id"],
            "confirmed_by_user": True,
        },
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422
    assert response.json()["key"] == "confirmed_by_user"
    assert _notes(client, experiment_id) == []


def test_a_run_this_record_does_not_hold_is_refused_before_anything_is_stored(
    client, experiment_id
):
    response = _finalize(client, experiment_id, CLEAN, run_id="not-a-real-run")
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_run"
    assert _notes(client, experiment_id) == []


def test_an_unknown_experiment_is_a_404(client):
    response = client.post(
        "/api/experiments/does-not-exist/transcript",
        json={"text": CLEAN, "finalized": True},
        headers={"If-Match": '"1"'},
    )
    assert response.status_code == 404


# --- 7. retention: exactly what is enforced, and nothing else -----------------


def test_the_one_enforced_retention_state_is_reported(client, experiment_id):
    run = _make_run(client, experiment_id)
    retention = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()[
        "capture"
    ]["retention"]
    assert retention["state"] == "retained_with_experiment"
    assert retention["notes_captured"] == 2
    assert retention["deletable"] is False


def test_the_retention_states_this_build_cannot_enforce_are_named_not_offered(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    retention = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()[
        "capture"
    ]["retention"]
    absent = {entry["state"] for entry in retention["not_implemented"]}
    assert absent == {"retain_during_draft", "remove_after_extraction"}
    for entry in retention["not_implemented"]:
        assert entry["reason"].strip()


def test_an_unenforceable_retention_state_is_refused_not_accepted_and_ignored(
    client, experiment_id
):
    """MUTATION: accepting `remove_after_extraction` and storing the notes anyway
    turns this RED — which is the shape of a control that quietly does nothing."""
    run = _make_run(client, experiment_id)
    response = _finalize(
        client,
        experiment_id,
        CLEAN,
        run_id=run["id"],
        retention="remove_after_extraction",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unsupported_retention"
    assert _notes(client, experiment_id) == []


def test_no_raw_audio_retention_setting_is_offered_because_none_is_stored(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    retention = _finalize(client, experiment_id, CLEAN, run_id=run["id"]).json()[
        "capture"
    ]["retention"]
    assert retention["raw_audio"]["stored"] is False
    assert "no raw-audio retention setting" in retention["raw_audio"]["reason"]


def test_this_operation_never_accepts_audio(client, experiment_id):
    """The transcript body carries text and nothing else; an audio key is refused.

    Together with the upload refusal below, this is the whole of "no audio reaches
    this server".
    """
    run = _make_run(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": CLEAN, "finalized": True, "run_id": run["id"], "audio": "..."},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422
    assert response.json()["key"] == "audio"


def test_file_upload_is_still_refused_unconditionally(client):
    """Unchanged by this feature, and asserted here because a voice surface is
    exactly the thing that would tempt somebody to open it."""
    assert client.post("/api/uploads").status_code == 403


# --- 8. the transcription seam says what it is, and claims nothing ------------


def test_transcription_is_reported_as_unconfigured(client):
    payload = client.get("/api/providers/capabilities").json()
    assert payload["any_provider_configured"] is False
    by_seam = {entry["seam"]: entry for entry in payload["seams"]}
    transcription = by_seam["transcription"]
    assert transcription["configured"] is False
    assert transcription["implementation"] == "unconfigured"
    assert transcription["is_test_double"] is False


def test_no_seam_reports_a_configured_provider(client):
    payload = client.get("/api/providers/capabilities").json()
    assert [entry["configured"] for entry in payload["seams"]] == [False, False, False]


def test_the_capability_report_says_manual_transcript_stays_available(client):
    payload = client.get("/api/providers/capabilities").json()
    assert payload["manual_transcript_available"] is True


def test_the_capability_report_echoes_no_environment_value(client, monkeypatch):
    monkeypatch.setenv(provider_config.TRANSCRIPTION_PROVIDER_ENV, "unconfigured")
    body = client.get("/api/providers/capabilities").text
    assert "unconfigured" in body  # the resolved implementation's NAME, which is fine
    payload = client.get("/api/providers/capabilities").json()
    for entry in payload["seams"]:
        assert entry["selected_by"] in provider_config.PROVIDER_ENV_VARS.values()


def test_the_transcription_operation_refuses_and_names_what_is_missing(client):
    response = client.post("/api/transcription", json={"audio_ref": "browser-memory-1"})
    assert response.status_code == 501, response.text
    body = response.json()
    assert body["refused"] is True
    assert body["seam"] == "transcription"
    assert body["reason"] == "no_provider_configured"
    assert body["missing"]
    assert body["decision_reference"] == "docs/ai-integration-decision-packet.md"


def test_the_transcription_refusal_never_implies_a_provider_exists(client):
    message = client.post(
        "/api/transcription", json={"audio_ref": "browser-memory-1"}
    ).json()["message"]
    lowered = message.lower()
    for banned in ("temporarily", "try again", "retry", "connected", "coming soon"):
        assert banned not in lowered


def test_the_transcription_operation_accepts_a_handle_and_never_audio(client):
    """`audio_ref` is a string handle. There is no multipart form to send bytes to.

    MUTATION: adding `python-multipart` and an `UploadFile` parameter turns the
    dependency assertion RED.
    """
    import isaac_api.app as app_module

    generated = app_module.create_app().openapi()
    operation = generated["paths"]["/api/transcription"]["post"]
    content = operation["requestBody"]["content"]
    assert list(content) == ["application/json"], content

    with pytest.raises(ImportError):
        __import__("multipart")


def test_a_transcription_request_with_no_input_is_a_422_not_a_501(client, monkeypatch):
    """The two refusal reasons must not collapse into one status.

    MUTATION: returning 501 for every refusal turns this RED, and would tell a
    caller who sent an empty body that the deployment is missing a provider.

    THE TEST DOUBLE IS CONSTRUCTED DIRECTLY AND THE RESOLVER IS REPLACED FOR THE
    DURATION OF THIS TEST — the environment variable is never set, so the boot
    refusal is untouched. That is exactly what the provider configuration
    module's own docstring prescribes: "Tests construct fakes directly, or via
    `resolve_*`, which is not a boot."
    """
    from isaac_api.providers.transcription import DeterministicTranscriptionFake

    monkeypatch.setattr(
        routes.provider_config,
        "resolve_transcription_provider",
        lambda: DeterministicTranscriptionFake(),
    )
    refused = client.post("/api/transcription", json={"audio_ref": "browser-memory-1"})
    assert refused.status_code == 422, refused.text
    assert refused.json()["reason"] == "input_not_supplied"

    transcribed = client.post(
        "/api/transcription", json={"manual_transcript": "First. Second."}
    )
    assert transcribed.status_code == 200, transcribed.text
    body = transcribed.json()
    assert body["refused"] is False
    assert body["verbatim"] is True
    assert [segment["text"] for segment in body["segments"]] == ["First.", "Second."]


def test_a_transcription_request_of_the_wrong_shape_is_refused(client):
    response = client.post("/api/transcription", json={"audio_ref": 5})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_field_value"


def test_the_boot_refusal_of_the_test_double_is_unchanged(monkeypatch):
    """This slice did NOT weaken the provider boot check, and this pins it.

    The fake stays unreachable through a booted application; the tests that need
    one construct it directly, which is what the configuration module's own
    docstring prescribes.
    """
    monkeypatch.setenv(
        provider_config.TRANSCRIPTION_PROVIDER_ENV,
        provider_base.IMPLEMENTATION_DETERMINISTIC_FAKE,
    )
    with pytest.raises(RuntimeError):
        provider_config.validate_provider_config_or_raise()


def test_the_transcript_reader_is_not_the_provider_seam():
    """The working path does not depend on any provider being configured.

    MUTATION: routing the reading through `resolve_capture_extraction_provider`
    turns this RED — and would make the scientist workflow refuse in every
    deployment.
    """
    assert tc.PRODUCED_BY != provider_base.IMPLEMENTATION_DETERMINISTIC_FAKE
    assert tc.PRODUCED_BY != provider_base.IMPLEMENTATION_UNCONFIGURED
    reading = tc.read_transcript(
        CLEAN,
        selected_run="run-1",
        known_runs=(tc.RunRef(id="run-1", label="Run 1", ordinal=1),),
    )
    assert {candidate.produced_by for candidate in reading.candidates} == {tc.PRODUCED_BY}


# --- 9. the reader itself ------------------------------------------------------


def test_segment_offsets_round_trip_into_the_original_text():
    text = "First sentence. Second sentence!\nThird line"
    for segment in tc.segment_transcript(text):
        assert text[segment.start_char : segment.end_char] == segment.text


def test_the_reader_is_a_pure_function_of_its_input():
    runs = (tc.RunRef(id="run-1", label="Run 1", ordinal=1),)
    first = tc.read_transcript(CLEAN, selected_run="run-1", known_runs=runs)
    second = tc.read_transcript(CLEAN, selected_run="run-1", known_runs=runs)
    assert [c.to_dict() for c in first.candidates] == [
        c.to_dict() for c in second.candidates
    ]


def test_a_proposed_value_is_always_present_in_the_transcript():
    """MUTATION: normalising 'dry nitrogen' to an enum member turns this RED."""
    text = "Temperature was 300 K. Atmosphere was: dry nitrogen"
    reading = tc.read_transcript(
        text,
        selected_run="run-1",
        known_runs=(tc.RunRef(id="run-1", label="Run 1", ordinal=1),),
    )
    for candidate in reading.candidates:
        assert str(candidate.proposed_value) in text
        assert candidate.quote in text


def test_a_reading_never_reports_itself_as_applied():
    reading = tc.read_transcript("Nothing at all.", selected_run=None, known_runs=())
    assert reading.applied is False


def test_a_segment_producing_two_candidates_records_neither_on_its_note():
    """A note carries one candidate path; recording one of two states a
    preference this reader does not hold."""
    text = "Temperature was 300 K and started at 2024-01-01T00:00:00Z"
    reading = tc.read_transcript(
        text,
        selected_run="run-1",
        known_runs=(tc.RunRef(id="run-1", label="Run 1", ordinal=1),),
    )
    assert len(reading.candidates) == 2
    assert reading.candidate_for_segment(0) is None
    assert reading.unmapped_segment_indexes == (0,)


def test_a_note_records_the_candidate_its_segment_produced(client, experiment_id):
    run = _make_run(client, experiment_id)
    _finalize(client, experiment_id, "Temperature was 300 K.", run_id=run["id"])
    stored = _notes(client, experiment_id)
    assert len(stored) == 1
    assert stored[0]["candidate_field_path"] == "context.temperature_K"
    assert stored[0]["candidate_rule"]
    assert stored[0]["is_field_value"] is False
    assert stored[0]["verified"] is False


def test_a_notes_run_comes_from_the_selection_and_is_never_inferred(
    client, experiment_id
):
    run = _make_run(client, experiment_id)
    _finalize(client, experiment_id, "The cryostat rattled.", run_id=run["id"])
    assert _notes(client, experiment_id)[0]["run_id"] == run["id"]

    other = client_ws(client).create_experiment(
        "Second", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
    )
    _make_run(client, other.id)
    _finalize(client, other.id, "The cryostat rattled.")
    assert _notes(client, other.id)[0]["run_id"] is None


# =============================================================================
# The ASSISTANT seam, over HTTP
# =============================================================================
#
# WHY THESE LIVE IN THIS FILE. `providers/assistant.py` had no route at all: it was
# a fully-built, fully-tested seam with no HTTP consumer, so "does this deployment
# have a native assistant?" was answerable only by reading Python. That is the same
# gap `POST /api/transcription` was written to close for its own seam, and the route
# is deliberately its twin — same two-status split, same refusal vocabulary, same
# "no fake connected state" rule. Testing it beside its twin is what keeps the two
# from drifting into two different policies for one question.
#
# WHAT THESE CANNOT SHOW: that a real provider behaves. None exists, none is
# authorized, and `validate_provider_config_or_raise` refuses to boot an
# application that names the fake. Every 200 below is produced by a test double
# constructed directly in the test, exactly as the transcription cases do it.

ASK = "/api/assistant/ask"


def _fake_assistant(monkeypatch):
    from isaac_api.providers.assistant import DeterministicAssistantFake

    monkeypatch.setattr(
        routes.provider_config,
        "resolve_assistant_provider",
        lambda: DeterministicAssistantFake(),
    )


def test_the_assistant_seam_refuses_and_names_what_is_missing(client):
    response = client.post(ASK, json={"question": "What is the edge?"})
    assert response.status_code == 501, response.text
    body = response.json()
    assert body["refused"] is True
    assert body["seam"] == "assistant"
    assert body["reason"] == "no_provider_configured"
    assert body["missing"]
    assert body["decision_reference"] == "docs/ai-integration-decision-packet.md"


def test_the_assistant_refusal_never_implies_a_provider_exists(client):
    message = client.post(ASK, json={"question": "anything"}).json()["message"]
    lowered = message.lower()
    for banned in ("temporarily", "try again", "retry", "connected", "coming soon"):
        assert banned not in lowered


def test_an_uncovered_question_is_a_422_not_a_501(client, monkeypatch):
    """The two refusal reasons must not collapse into one status.

    `501` says this deployment has no provider — an institutional decision, not a
    wait. `422` says the context you sent does not cover the question. A client
    that retried the first would be waiting for something nobody has decided to
    build; a client shown the first for the second would think the deployment was
    broken when its own request was the problem.
    """
    _fake_assistant(monkeypatch)
    refused = client.post(
        ASK,
        json={
            "question": "What temperature was this measured at?",
            "context": [
                {"key": "title", "text": "Copper oxide study", "origin": "the record"}
            ],
        },
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["reason"] == "outside_grounded_context"


def test_an_answer_cites_the_context_it_used_and_claims_no_authority(client, monkeypatch):
    """THE STRUCTURAL COMMITMENT OF THIS SEAM, over HTTP.

    An uncited answer cannot be constructed — `AssistantAnswer` raises — so this
    asserts the citation reaches the wire, and that `authoritative` is there and
    false. A client that rendered an answer without `grounded_in` would be showing
    a scientist a paragraph with no stated basis, which is the failure the whole
    seam is shaped around.
    """
    _fake_assistant(monkeypatch)
    response = client.post(
        ASK,
        json={
            "question": "What temperature was recorded?",
            "context": [
                {
                    "key": "context.temperature_K",
                    "text": "temperature 298 K",
                    "origin": "the run's own draft, read by the caller",
                },
                {"key": "title", "text": "Copper oxide study", "origin": "the record"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert body["authoritative"] is False
    # ONLY the item that shares a token, so the citation is a statement about what
    # was used rather than an echo of everything supplied.
    assert body["grounded_in"] == ["context.temperature_K"]
    assert "298 K" in body["text"]
    assert body["produced_by"] == "deterministic-fake"


def test_the_seam_fetches_nothing_so_an_unknown_key_is_REFUSED(client):
    """A caller sending `record_id` is asking this operation to fetch something.

    Answering `200` while dropping the key would leave them believing the answer
    was grounded in a record nobody read — which is worse than a refusal, because
    the answer would look grounded and cite whatever context they happened to send.
    """
    response = client.post(
        ASK, json={"question": "what is missing?", "record_id": "01SYNTHXANESSEED0000000002"}
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field"
    assert body["keys"] == ["record_id"]


def test_a_context_item_with_no_stated_origin_is_refused_rather_than_sent(client, monkeypatch):
    """`ContextItem.__post_init__`'s rule, relayed rather than re-implemented:
    "unattributed context is how an answer loses its grounding"."""
    _fake_assistant(monkeypatch)
    response = client.post(
        ASK,
        json={
            "question": "What temperature was recorded?",
            "context": [{"key": "temp", "text": "298 K"}],
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_field_value"
    assert body["key"] == "context[0]"


@pytest.mark.parametrize(
    "body,key",
    [
        ({"question": ""}, "question"),
        ({"question": "   "}, "question"),
        ({"question": 5}, "question"),
        ({}, "question"),
        ({"question": "ok", "context": "not a list"}, "context"),
        ({"question": "ok", "context": [5]}, "context[0]"),
    ],
)
def test_an_unaskable_request_is_refused_naming_the_key(client, body, key):
    response = client.post(ASK, json=body)
    assert response.status_code == 422, response.text
    assert response.json()["key"] == key


def test_an_unknown_key_INSIDE_a_context_item_is_refused_too(client):
    response = client.post(
        ASK,
        json={
            "question": "ok",
            "context": [
                {"key": "k", "text": "t", "origin": "o", "verified": True}
            ],
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field"
    assert body["keys"] == ["verified"]
    # `verified: true` is the exact key worth refusing rather than ignoring: it is
    # the vocabulary of an EVIDENCE envelope, and a caller who sent it would be
    # asserting a classification this seam has no power to make.


def test_a_context_key_that_would_trip_the_refusal_guard_is_not_a_500(client, monkeypatch):
    """A REFUSAL ROUTE MUST NOT 500, and this one could — by shape.

    `ProviderRefusal.__post_init__` refuses a message containing any of
    `_FORBIDDEN_MESSAGE_SUBSTRINGS` ("retry", "timeout", "connected", …), which exists
    so a refusal can never imply a provider is coming back. The deterministic double
    built its out-of-context message by LISTING THE CONTEXT KEYS — and those are
    caller data. So a context item keyed `retry_policy` raised `ValueError` out of a
    constructor, and an HTTP caller saw a 500 from the one route whose entire subject
    is refusing honestly. An independent review found it by reading the shape.

    Unreachable in a booted application — `validate_provider_config_or_raise` refuses
    to boot with the double selected — but "unreachable today" is not "cannot happen",
    and the message says everything the list did by reporting the COUNT instead.
    """
    _fake_assistant(monkeypatch)
    result = client.post(
        ASK,
        json={
            "question": "what is the absorbing element?",
            "context": [
                {
                    "key": "retry_policy",
                    "text": "timeout after 30s, then connected again",
                    "origin": "a caller who chose these words",
                }
            ],
        },
    )
    # A TYPED 422, not a 500.
    assert result.status_code == 422, result.text
    body = result.json()
    assert body["reason"] == "outside_grounded_context"
    # AND THE CALLER'S OWN WORDS ARE NOT ECHOED BACK into the refusal.
    assert "retry_policy" not in body["message"]
    assert "1 item(s)" in body["message"]


def test_the_assistant_seam_declares_no_multipart_form_either(client):
    import isaac_api.app as app_module

    operation = app_module.create_app().openapi()["paths"][ASK]["post"]
    assert list(operation["requestBody"]["content"]) == ["application/json"]


def test_the_assistant_boot_refusal_of_the_test_double_is_unchanged(monkeypatch):
    """The fake stays unreachable through a booted application (DECISION D6).

    This is what makes "no deployment can show a connected assistant" structural
    rather than a promise: an operator who names the fake gets a refusal to boot,
    not a working demo.
    """
    monkeypatch.setenv(
        provider_config.ASSISTANT_PROVIDER_ENV,
        provider_base.IMPLEMENTATION_DETERMINISTIC_FAKE,
    )
    with pytest.raises(RuntimeError):
        provider_config.validate_provider_config_or_raise()


def test_the_deterministic_memory_QA_is_not_this_seam(client):
    """The shipped Q&A does not depend on any provider being configured.

    MUTATION: routing `/assistant/memory/query` through
    `resolve_assistant_provider` turns this RED — and would make the one working
    question-answering path in the product refuse in every deployment, which is
    precisely the confusion the route description exists to prevent.
    """
    seam = client.post(ASK, json={"question": "anything"})
    assert seam.status_code == 501
    shipped = client.post(
        "/api/assistant/memory/query", json={"question": "what changed recently?"}
    )
    assert shipped.status_code == 200, shipped.text
