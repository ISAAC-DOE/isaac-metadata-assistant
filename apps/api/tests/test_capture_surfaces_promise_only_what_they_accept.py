"""Two surfaces told a scientist to do something this build refuses. Measured, then pinned.

Both defects here have the shape ``CLAUDE.md`` §12 records for the three scoped
Governance claims: a true-sounding sentence pointing at a locked door. Neither had a
test on ``origin/main``; both are asserted here against real HTTP responses, and each
assertion was verified to go RED with the fix reverted.

D1 — *"a value still has to be entered and confirmed on the field itself"*
--------------------------------------------------------------------------
``UnmappedNotesPanel``, the ``review`` operation's description and ``notes.map_note``'s
docstring all said it, of all 25 mappable paths. Measured over HTTP against every write
route this application has, seven of them are refused by every one. Worse, the notes
module docstring named ``POST .../answers`` and ``POST .../edit`` as "the path that
turns a value into a confirmed field", and those two accept **none of the 25**.

:func:`test_the_served_writable_set_is_what_the_write_routes_actually_do` is the load-
bearing one: it does not compare two constants, it SENDS a write at all 25 paths to all
five routes and compares 125 observed statuses to the served set.

D3 — a contributor set through the only available write path could never export
-------------------------------------------------------------------------------
``POST .../runs/{run_id}/overrides`` at ``block:attribution`` answered ``200`` and wrote
no ``block_evidence``, so ``draft_validator``'s ``attribution:<name>|<role>`` coverage
rule then refused the export with ``official_report: null`` — for a contributor whose
only write path in this build is that route. The evidence requirement is NOT weakened
anywhere; the write now records the ``user_confirmation`` it had already earned, on the
same flag and with the same ``models.user_confirmation`` shape ``_apply_run_field``
already uses for a run field value.

Everything here is synthetic: a tmp workspace, records created through
``POST /api/experiments``, no database, no network, no file outside the workspace.
"""

from __future__ import annotations

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws



@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _stored_run(experiment_id: str):
    """The persisted Run, read from the ORDINARY workspace scope.

    Deliberately not ``conftest.client_ws``: that binds to a worked-example session, and
    every record here is created through ``POST /api/experiments``, which refuses to run
    inside one. Reading the stored document is how a test can see that no evidence entry
    was minted, which no response body reports.
    """
    experiment = ws.load_experiment(experiment_id, session_id=None)
    assert experiment is not None, experiment_id
    return experiment.runs[0]


def _etag(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _experiment(client, title="Capture-surface fixture") -> str:
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _run(client, experiment_id: str) -> str:
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, f"/api/experiments/{experiment_id}")},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]["id"]


#: A value the coercers and the storable-value guard will each accept, per path. Only
#: the numeric paths need one; everything else takes a string. The point of the probe is
#: WHICH ROUTE ACCEPTS THE PATH, so a value refused for being the wrong TYPE would
#: measure the wrong thing.
_NUMERIC = {
    "context.temperature_K": 300,
    "sample.composition.CuO2_mass_fraction": 0.5,
    "sample.composition.sucrose_mass_fraction": 0.5,
    "sample.geometry.pellet_diameter_mm": 5,
    "system.configuration.n_scans": 3,
}


def _envelope(value):
    """A draft field envelope the no-guessing rules accept, built the repository's way."""
    from isaac_records.models import field_value, user_confirmation

    return field_value(
        value,
        status="verified",
        evidence=[user_confirmation("probe", str(value), "2026-08-26T00:00:00Z")],
    )


# --- D1 -----------------------------------------------------------------------


def test_the_served_writable_set_is_what_the_write_routes_actually_do(client):
    """125 real requests, not a comparison of two constants.

    THIS IS THE TEST THE COPY CLAIM NEEDED AND DID NOT HAVE. A test asserting that
    ``value_writable_field_paths`` equals ``NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT``
    would pass against any set at all, including the empty one and the full 25 — it would
    only prove the server is self-consistent, which is exactly what the false sentence
    also was. So every mappable path is sent to every write operation this application
    has, and the served set is required to be precisely the paths that at least one of
    them accepted.

    MUTATION: serving ``sorted(NOTE_MAPPABLE_FIELD_PATHS)`` (the old, false claim, made
    machine-readable) turns this RED on 7 paths; serving ``[]`` turns it RED on 18.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    exp = f"/api/experiments/{experiment_id}"
    run = f"{exp}/runs/{run_id}"

    served = client.get(f"{exp}/notes").json()
    mappable = served["mappable_field_paths"]
    assert sorted(mappable) == sorted(routes.NOTE_MAPPABLE_FIELD_PATHS)

    accepted: set[str] = set()
    observed: dict[str, dict[str, int]] = {}
    for path in mappable:
        value = _NUMERIC.get(path, "PROBE-VALUE")
        attempts = {
            "record_answers": client.post(
                f"{exp}/answers",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
            "record_edit": client.post(
                f"{exp}/edit",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
            "run_answers": client.post(
                f"{run}/answers",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, run)},
            ),
            "run_patch": client.patch(
                run,
                json={"confirmed_by_user": True, "fields": {path: value}},
                headers={"If-Match": _etag(client, run)},
            ),
            "run_override": client.post(
                f"{run}/overrides",
                json={
                    "confirmed_by_user": True,
                    "address": ws.field_address(path),
                    "payload": _envelope(value),
                },
                headers={"If-Match": _etag(client, run)},
            ),
        }
        observed[path] = {name: r.status_code for name, r in attempts.items()}
        if any(r.status_code < 300 for r in attempts.values()):
            accepted.add(path)
        # Undo the override so one path's stored value cannot change the next path's
        # answer. The run's own fields are harmless: they are additive and per-path.
        client.post(
            f"{run}/overrides/clear",
            json={"confirmed_by_user": True, "address": ws.field_address(path)},
            headers={"If-Match": _etag(client, run)},
        )

    assert sorted(served["value_writable_field_paths"]) == sorted(accepted), observed

    # BOTH POLARITIES ARE ACTUALLY PRESENT, so the equality above cannot pass vacuously.
    refused = sorted(set(mappable) - accepted)
    assert accepted, observed
    assert refused == [
        "system.configuration.detector_model",
        "system.configuration.monochromator_crystal",
        "system.configuration.n_scans",
        "system.configuration.proposal_id",
        "system.configuration.session_id",
        "system.configuration.spectrometer_geometry",
        "timestamps.created_utc",
    ], observed

    # And the refusal for a path nothing accepts is a TYPED 422 from every route, never
    # a 500 and never a 200 that wrote nothing. This is what makes "no route accepts it"
    # a fact about the contract rather than about one probe's payload.
    for path in refused:
        assert set(observed[path].values()) == {422}, (path, observed[path])


def test_the_two_write_routes_that_do_accept_these_paths_are_both_a_runs(client):
    """A record with NO runs can write none of the 25, and the served set does not lie
    about that — it says a route exists, not that you can use it right now.

    Recorded because it is the one thing the served key cannot express and the copy
    therefore must not imply. Both accepting routes are addressed under
    ``/runs/{run_id}``, so on a record that has no run yet every one of the 25 is
    refused, including the 18.

    MUTATION: adding either record-level route to the set of routes that accept an
    official field path would turn this RED.
    """
    experiment_id = _experiment(client)
    exp = f"/api/experiments/{experiment_id}"
    for path in sorted(routes.NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT):
        value = _NUMERIC.get(path, "PROBE-VALUE")
        for response in (
            client.post(
                f"{exp}/answers",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
            client.post(
                f"{exp}/edit",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
        ):
            assert response.status_code == 422, (path, response.text)
            assert response.json()["error"] == "unrecognized_field", path


def test_no_surface_still_promises_a_value_can_be_entered_at_every_mapped_path(client):
    """The three copies of the false sentence, pinned so none of them comes back.

    ``notes.py``'s module docstring and ``map_note``'s docstring, and the ``review``
    operation's published description, each carried a promise that was true of 18 paths
    and false for 7. The literal is asserted absent from the SERVED contract and from the
    module, and the correction is asserted present — checking only for absence would pass
    on a file that deleted the whole paragraph and said nothing at all.

    MUTATION: restoring the old sentence in either place turns this RED.
    """
    import inspect

    import isaac_api.notes as notes

    dead = "confirmed-edit path that already exists"
    module_text = notes.__doc__ or ""
    map_text = inspect.getdoc(notes.map_note) or ""

    # It survives ONLY as a quoted correction, never as a live claim. The COUNT is the
    # load-bearing part and was added after a mutation run: asserting the struck
    # quotation is present says nothing about whether a live copy sits beside it, and
    # the first version of this test passed with the old sentence restored one line
    # above the correction that retracts it.
    assert dead not in module_text
    assert map_text.count(dead) == 1
    assert f'~~"through the {dead}"~~' in map_text
    assert "value_writable_field_paths" in module_text
    assert "value_writable_field_paths" in map_text

    spec = client.app.openapi()
    review = spec["paths"]["/api/experiments/{experiment_id}/notes/{note_id}/review"]
    description = review["post"]["description"]
    assert dead not in description
    assert "value_writable_field_paths" in description
    listing = spec["paths"]["/api/experiments/{experiment_id}/notes"]["get"]["description"]
    assert "value_writable_field_paths" in listing


def test_mapping_to_an_unwritable_path_is_still_accepted_and_still_keeps_the_text(client):
    """The honest sentence is a DISCLOSURE, not a new gate.

    Refusing to map a note whose field can hold no value would throw away a scientist's
    own judgement about where their prose belongs in order to avoid having to say one
    awkward thing. The note is mapped, the mapping is recorded, and the verbatim text is
    unchanged.

    MUTATION: gating ``map`` on ``NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT`` turns
    this RED.
    """
    experiment_id = _experiment(client)
    exp = f"/api/experiments/{experiment_id}"
    unwritable = sorted(
        routes.NOTE_MAPPABLE_FIELD_PATHS - routes.NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT
    )[0]
    text = "detector was swapped between scans 2 and 3"

    captured = client.post(
        f"{exp}/notes",
        json={"text": text, "source": "typed_note"},
        headers={"If-Match": _etag(client, exp)},
    )
    assert captured.status_code == 201, captured.text
    note_id = captured.json()["note"]["id"]

    reviewed = client.post(
        f"{exp}/notes/{note_id}/review",
        json={"confirmed_by_user": True, "action": "map", "field_path": unwritable},
        headers={"If-Match": _etag(client, exp)},
    )
    assert reviewed.status_code == 200, reviewed.text
    note = reviewed.json()["note"]
    assert note["state"] == "mapped"
    assert note["mapped_field_path"] == unwritable
    assert note["text"] == text


# --- D3 -----------------------------------------------------------------------


def _set_attribution(client, experiment_id, run_id, payload):
    run = f"/api/experiments/{experiment_id}/runs/{run_id}"
    return client.post(
        f"{run}/overrides",
        json={
            "confirmed_by_user": True,
            "address": ws.block_address("attribution"),
            "payload": payload,
        },
        headers={"If-Match": _etag(client, run)},
    )


def _draft_errors(client, experiment_id, run_id):
    response = client.post(
        f"/api/experiments/{experiment_id}/runs/{run_id}/check", json={}
    )
    assert response.status_code == 200, response.text
    return [e["message"] for e in response.json()["draft"]["errors"]]


def test_a_contributor_set_through_the_only_available_write_path_can_be_exported(client):
    """The measured defect, from the outside: ``200`` accepted, export refused forever.

    On ``origin/main`` this sequence produced
    ``attribution.contributors[0]: "contributor has no evidence; attribution must cite
    its source or be user-confirmed"`` and no ``official_report`` at all — the DRAFT
    validator refused before official validation was reached, and no later request could
    clear it, because ``block:attribution`` is the only contributor write path this build
    offers and it wrote no evidence.

    MUTATION: removing the ``_rewrite_run_attribution_evidence`` call from
    ``post_run_override`` turns this RED with exactly that message.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)

    assert _draft_errors(client, experiment_id, run_id) == []
    response = _set_attribution(
        client,
        experiment_id,
        run_id,
        {"contributors": [{"name": "A Scientist", "role": "operator"}]},
    )
    assert response.status_code == 200, response.text
    assert _draft_errors(client, experiment_id, run_id) == []


def test_the_evidence_recorded_is_the_repositorys_own_user_confirmation_shape(client):
    """Reused, not invented, and it claims nothing about WHO.

    The entry must be the four-key ``models.user_confirmation`` shape ``complete.py``
    writes for ``qc:status`` and each ``series:<id>``, keyed under the natural key
    ``draft_validator`` looks a contributor up by. And it must name no person: this
    application has no trusted authentication boundary (``CLAUDE.md`` §15), which is the
    same reason ``attribution.uploaded_by`` is refused outright.

    MUTATION: keying the entry as ``attribution:<name>`` (dropping the role) turns the
    key assertion RED and the export assertion above RED with it.
    """
    from isaac_records.models import user_confirmation

    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    _set_attribution(
        client,
        experiment_id,
        run_id,
        {"contributors": [{"name": "A Scientist", "role": "operator"}]},
    )

    block_evidence = _stored_run(experiment_id).draft["block_evidence"]
    assert list(block_evidence) == ["attribution:A Scientist|operator"]
    entry = block_evidence["attribution:A Scientist|operator"][0]

    reference = user_confirmation("q", "a", "t")
    assert set(entry) == set(reference)
    assert entry["source_type"] == "user_confirmation"
    assert entry["answer"] == "A Scientist | operator"
    # The question names the OPERATION and says outright that the person is not
    # recorded. The second assertion is the one that carries the claim: "no verified
    # user identity" alone passed a mutation that appended *"but we record the operator
    # as `isaac-operator`"* to the same sentence, because the phrase it looked for was
    # still there in front of the new claim.
    assert "confirmed_by_user: true" in entry["question"]
    assert entry["question"].endswith("deliberately not recorded.")


def test_recording_the_same_contributor_twice_does_not_move_the_run(client, monkeypatch):
    """The operation's published contract promises this, and a timestamp would break it.

    ``POST .../overrides`` documents that recording the same override twice is a no-op
    which does not restamp and does not advance the run's revision. An evidence entry
    carries a timestamp, so an unconditional rewrite would silently make that false.

    **THE CLOCK IS STUBBED, AND THIS TEST WAS GREEN-BY-LUCK WITHOUT IT.** ``_now_iso``
    has one-second resolution and the two requests below run in about a millisecond, so
    an unconditional rewrite produced a byte-identical entry and the guard passed —
    measured, on the mutation it names. The stub returns a DIFFERENT second per call, so
    the only thing that can keep the document stable is the ``_same`` check. Real
    requests are seconds or minutes apart, which is the case the stub represents.

    MUTATION: writing the fresh entry unconditionally (dropping the ``_same`` check in
    ``_rewrite_run_attribution_evidence``) turns this RED.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    payload = {"contributors": [{"name": "A Scientist", "role": "operator"}]}

    ticks = iter(f"2026-08-26T00:00:{n:02d}Z" for n in range(10, 60))
    monkeypatch.setattr(routes, "_now_iso", lambda: next(ticks))

    _set_attribution(client, experiment_id, run_id, payload)
    before = _stored_run(experiment_id).version_token()
    stored_before = _stored_run(experiment_id).draft["block_evidence"]

    assert _set_attribution(client, experiment_id, run_id, payload).status_code == 200
    after_run = _stored_run(experiment_id)
    assert after_run.version_token() == before
    assert after_run.draft["block_evidence"] == stored_before

    # NEGATIVE CONTROL ON THE STUB ITSELF: a genuinely NEW confirmation must take the
    # next tick, or the assertions above would also pass against a frozen clock — which
    # is exactly the accident that made the first version of this test meaningless.
    assert _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "B", "role": "analyst"}]}
    ).status_code == 200
    fresh = _stored_run(experiment_id).draft["block_evidence"]["attribution:B|analyst"][0]
    assert fresh["timestamp"] != stored_before["attribution:A Scientist|operator"][0][
        "timestamp"
    ]


def test_replacing_the_contributors_does_not_leave_the_old_ones_confirmation_behind(client):
    """A confirmation for somebody the record no longer names is a false provenance claim.

    An override REPLACES the whole ``attribution`` block, so a dropped contributor is
    gone from the record. Their evidence entry must go with them, or ``build_sidecar``
    would emit provenance for a person the exported record does not mention — and a
    stale key could later cover a re-added contributor nobody confirmed again.

    MUTATION: merging instead of replacing (dropping the ``attribution:`` prefix filter)
    turns this RED with two keys.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "A", "role": "operator"}]}
    )
    _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "B", "role": "analyst"}]}
    )

    assert list(_stored_run(experiment_id).draft["block_evidence"]) == ["attribution:B|analyst"]


def test_clearing_the_override_takes_its_confirmations_with_it(client):
    """"The run inherits again" has to mean the evidence too.

    MUTATION: removing the ``_rewrite_run_attribution_evidence(run, {})`` call from the
    clear route turns this RED.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    run = f"/api/experiments/{experiment_id}/runs/{run_id}"
    _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "A", "role": "operator"}]}
    )

    cleared = client.post(
        f"{run}/overrides/clear",
        json={"confirmed_by_user": True, "address": ws.block_address("attribution")},
        headers={"If-Match": _etag(client, run)},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["cleared"] is True

    assert "block_evidence" not in _stored_run(experiment_id).draft


@pytest.mark.parametrize(
    "contributor, expected",
    [
        ({}, "contributor missing name/role — cannot key its evidence"),
        (
            {"name": ["a"], "role": "b"},
            "contributor has no evidence; attribution must cite its source or be user-confirmed",
        ),
    ],
)
def test_a_contributor_this_build_cannot_key_gets_no_confirmation_and_stays_refused(
    client, contributor, expected
):
    """FAIL-CLOSED, and this is the assertion that keeps the fix from being a hole.

    ``_refuse_override_payload`` applies no contributor SHAPE check — measured, and
    recorded in its own docstring — so both of these are stored with ``200``. Minting an
    evidence entry keyed off a list-valued name would let a contributor the official
    schema cannot hold pass the coverage gate and reach an exported record. So no entry
    is minted and the gate goes on refusing them.

    MUTATION: relaxing the ``isinstance(name, str)`` guard to a truthiness test turns the
    second case RED — it would be silently confirmed and would export.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)

    response = _set_attribution(client, experiment_id, run_id, {"contributors": [contributor]})
    assert response.status_code == 200, response.text

    assert _stored_run(experiment_id).draft.get("block_evidence") in (None, {})
    assert _draft_errors(client, experiment_id, run_id) == [expected]
