"""THE ACTIVITY HISTORY OVER HTTP, AND THE CHANNEL STAMPED AT EVERY WRITE PATH.

Every assertion here is BEHAVIOURAL: a real request through the real application to a
real workspace, then a read of the stored rows. Nothing asserts that a sentence
exists. ``CLAUDE.md`` §11 records a slice whose central claim was pinned by string
presence and which passed 25 tests beside a fabricating seam, so the distinction is
kept visible.

DATA BOUNDARY: **none.** Every value is synthetic and unmistakably so, in a
``tmp_path`` workspace. No database connection is opened, no migration is applied, no
external host is contacted, and nothing production-derived is read.

AUTHORIZATION BASIS: ``CLAUDE.md`` §15's application-side scope extension of
2026-08-29 (the durable contract and "the associated tests"), plus ``DEC-44`` and
``DEC-45``. See :mod:`isaac_api.activity`'s docstring, which cites the persistence
LOCATION clause rather than re-arguing it.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import activity, identity

SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8970, 8980, 8990]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.02, 0.85, 1.45],
            }
        ],
    }
]
QC = {"status": "valid", "evidence": "I0 stable across all scans; no glitches."}
QC_COMPROMISED = {"status": "compromised", "evidence": "Shutter stuck on scan 3."}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A plain client on an empty workspace — NO worked-example session."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _version(client, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").json()["version"]


def _etag(client, exp_id: str) -> dict:
    return {"If-Match": f'"{_version(client, exp_id)}"'}


def _create(client, title="Cu K-edge XANES, 300 K") -> str:
    created = client.post("/api/experiments", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _activity(client, exp_id: str, **params) -> dict:
    response = client.get(f"/api/experiments/{exp_id}/activity", params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


# ==========================================================================
# the read surface
# ==========================================================================


def test_a_fresh_record_has_an_empty_history_and_says_so_honestly(client):
    """Not an error, not a 404 — an empty history, with the vocabularies served."""
    body = _activity(client, _create(client))
    assert body["events"] == []
    assert body["total"] == 0
    assert body["matched"] == 0
    assert body["returned"] == 0
    assert body["highest_seq"] == 0
    assert body["next_before_seq"] is None
    assert body["next_since_seq"] is None
    assert body["unreadable_entries"] == 0
    assert set(body["channels"]) == {"web", "mcp", "historical_import", "system"}
    assert "field_answered" in body["actions"]


def test_an_answer_is_recorded_with_before_ABSENT_and_after_the_value(client):
    """THE CENTRAL CLAIM of the record path, measured over HTTP."""
    exp_id = _create(client)
    answered = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    assert answered.status_code == 200, answered.text

    events = _activity(client, exp_id)["events"]
    qc_events = [e for e in events if e["field_path"] == "qc"]
    assert len(qc_events) == 1, events
    event = qc_events[0]
    assert event["action"] == "field_answered"
    assert event["object_type"] == "field"
    assert event["run_id"] is None
    assert event["channel"] == "web"
    assert event["actor"] == "unattributed"
    assert event["actor_trust_basis"] == "unattributed"
    assert event["seq"] == 1
    # `before` says THERE WAS NONE — which is exactly what `/answers` guarantees,
    # since `_refuse_answering_an_already_answered_key` refuses an answered key.
    assert event["before"] == {"present": False, "value": None}
    assert event["after"]["present"] is True
    assert event["after"]["value"]["status"] == "valid"


def test_a_correction_records_field_corrected_with_the_real_prior_value(client):
    """The verb AND the pair. `field_answered` here would hide that this was a change."""
    exp_id = _create(client)
    client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    corrected = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"answers": {"qc": QC_COMPROMISED}, "confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    assert corrected.status_code == 200, corrected.text

    events = _activity(client, exp_id, newest_first=False)["events"]
    verbs = [e["action"] for e in events if e["field_path"] == "qc"]
    assert verbs == ["field_answered", "field_corrected"], events

    correction = [e for e in events if e["action"] == "field_corrected"][0]
    assert correction["before"]["present"] is True
    assert correction["before"]["value"]["status"] == "valid"
    assert correction["after"]["value"]["status"] == "compromised"


def test_a_resubmission_that_changes_nothing_records_nothing(client):
    """A no-op must not pad the history. The staging guarantee, over HTTP."""
    exp_id = _create(client)
    client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    after_first = _activity(client, exp_id)["total"]

    # Re-sending the identical value through `/edit` is idempotent in the writers.
    again = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    assert again.status_code == 200, again.text
    assert _activity(client, exp_id)["total"] == after_first

    # And a rename to the name the record already has.
    title = client.get(f"/api/experiments/{exp_id}").json()["title"]
    renamed = client.patch(
        f"/api/experiments/{exp_id}",
        json={"title": title},
        headers=_etag(client, exp_id),
    )
    assert renamed.status_code == 200, renamed.text
    assert _activity(client, exp_id)["total"] == after_first


def test_a_rename_and_a_move_record_the_real_prior_label(client):
    exp_id = _create(client, title="First name")
    client.patch(
        f"/api/experiments/{exp_id}",
        json={"title": "Second name"},
        headers=_etag(client, exp_id),
    )
    client.patch(
        f"/api/experiments/{exp_id}/folder",
        json={"folder": "beamtime-2099"},
        headers=_etag(client, exp_id),
    )
    events = {e["action"]: e for e in _activity(client, exp_id)["events"]}
    assert events["experiment_renamed"]["before"] == {
        "present": True,
        "value": "First name",
    }
    assert events["experiment_renamed"]["after"]["value"] == "Second name"
    # `""` IS THE UNFILED VALUE AND IS PRESENT, not absent — an un-filing must be
    # distinguishable from a first filing.
    assert events["experiment_moved_to_folder"]["before"] == {
        "present": True,
        "value": "",
    }
    assert events["experiment_moved_to_folder"]["after"]["value"] == "beamtime-2099"


def test_a_run_added_and_removed_are_both_recorded(client):
    """The removal is the act neither the change feed nor any other surface reports."""
    exp_id = _create(client)
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "Run 1"},
        headers=_etag(client, exp_id),
    )
    assert added.status_code in (200, 201), added.text
    run_id = added.json()["run"]["id"]

    removed = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/remove",
        json={"confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    assert removed.status_code == 200, removed.text

    events = _activity(client, exp_id, newest_first=False)["events"]
    verbs = [e["action"] for e in events]
    assert verbs == ["run_added", "run_removed"], events
    assert events[0]["run_id"] == run_id
    assert events[0]["before"] == {"present": False, "value": None}
    assert events[1]["before"]["value"]["label"] == "Run 1"
    assert events[1]["after"] == {"present": False, "value": None}
    # And the history OUTLIVES the run it describes, which is the whole point of an
    # append-only model: the run is gone from the record and its rows are not.
    listed = client.get(f"/api/experiments/{exp_id}/runs")
    assert listed.status_code == 200, listed.text
    assert listed.json()["runs"] == []


def test_a_note_capture_and_review_are_recorded_without_copying_the_words(client):
    """A note's verbatim text must not be duplicated into the audit row."""
    exp_id = _create(client)
    spoken = "The cell sat at 301 K throughout; shutter stuck on scan three."
    captured = client.post(
        f"/api/experiments/{exp_id}/notes",
        json={"text": spoken, "source": "typed_note"},
        headers=_etag(client, exp_id),
    )
    assert captured.status_code == 201, captured.text
    note_id = captured.json()["note"]["id"]

    reviewed = client.post(
        f"/api/experiments/{exp_id}/notes/{note_id}/review",
        json={"action": "keep", "confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    assert reviewed.status_code == 200, reviewed.text

    events = _activity(client, exp_id, newest_first=False)["events"]
    assert [e["action"] for e in events] == ["note_captured", "note_reviewed"], events
    assert all(e["source_ref"] == note_id for e in events)
    assert events[1]["before"]["value"] == "unreviewed"
    assert events[1]["after"]["value"] == "kept"
    # THE WORDS ARE NOT IN THE HISTORY. They are on the note, which survives every
    # review outcome; copying them would store a scientist's prose twice.
    assert spoken not in json.dumps(events)


def test_an_export_records_one_event_per_published_record(client):
    exp_id = _create(client)
    client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {
                "series": SERIES,
                "qc": QC,
                "descriptor": {
                    "name": "inflection_point_energy",
                    "kind": "absolute",
                    "source": "manual",
                    "value": 9001.2,
                    "unit": "eV",
                    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
                },
            },
            "confirmed_by_user": True,
        },
        headers=_etag(client, exp_id),
    )
    exported = client.post(
        f"/api/experiments/{exp_id}/export", headers=_etag(client, exp_id)
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True

    published = [
        e for e in _activity(client, exp_id)["events"] if e["action"] == "record_exported"
    ]
    assert len(published) == 1, published
    assert published[0]["object_type"] == "record"
    assert published[0]["after"]["value"] == exp_id
    assert published[0]["channel"] == "web"


# ==========================================================================
# the counts, which is where this repository has been bitten before
# ==========================================================================


def test_a_page_smaller_than_the_history_still_reports_the_TRUE_total(client):
    """``CLAUDE.md`` §11's measured defect: a count taken from a fetched page."""
    exp_id = _create(client)
    for n in range(7):
        client.patch(
            f"/api/experiments/{exp_id}",
            json={"title": f"Name {n}"},
            headers=_etag(client, exp_id),
        )
    full = _activity(client, exp_id)
    assert full["total"] == 7

    page = _activity(client, exp_id, limit=3)
    assert page["returned"] == 3
    assert len(page["events"]) == 3
    assert page["total"] == 7, "the total came from the page"
    assert page["matched"] == 7, "the matched count came from the page"
    assert page["highest_seq"] == 7, "the resume position came from the page"
    # THE CONTINUATION IS DIRECTION-SPECIFIC, and exactly one key carries it. Serving
    # a `before_seq` to an oldest-first caller would page them BACKWARDS through
    # history they had already read, which is why these are two keys and not one.
    assert page["next_before_seq"] == 5
    assert page["next_since_seq"] is None

    forward = _activity(client, exp_id, limit=3, newest_first=False)
    assert [e["seq"] for e in forward["events"]] == [1, 2, 3]
    assert forward["next_since_seq"] == 3
    assert forward["next_before_seq"] is None
    # …and following it lands on the next three rather than re-reading the first.
    second = _activity(
        client, exp_id, limit=3, newest_first=False, since_seq=forward["next_since_seq"]
    )
    assert [e["seq"] for e in second["events"]] == [4, 5, 6]

    # THE LAST PAGE CARRIES NEITHER CURSOR, so a client cannot loop forever.
    last = _activity(client, exp_id, limit=100)
    assert last["next_before_seq"] is None and last["next_since_seq"] is None


def test_newest_first_takes_the_page_from_the_NEWEST_end(client):
    """Not "sorted then truncated from the front", which would hand back the oldest."""
    exp_id = _create(client)
    for n in range(5):
        client.patch(
            f"/api/experiments/{exp_id}",
            json={"title": f"Name {n}"},
            headers=_etag(client, exp_id),
        )
    newest = _activity(client, exp_id, limit=2)
    assert [e["seq"] for e in newest["events"]] == [5, 4]
    oldest = _activity(client, exp_id, limit=2, newest_first=False)
    assert [e["seq"] for e in oldest["events"]] == [1, 2]


def test_since_seq_is_exclusive_so_a_poller_loses_nothing_and_repeats_nothing(client):
    exp_id = _create(client)
    for n in range(3):
        client.patch(
            f"/api/experiments/{exp_id}",
            json={"title": f"Name {n}"},
            headers=_etag(client, exp_id),
        )
    seen = _activity(client, exp_id)["highest_seq"]
    assert seen == 3
    assert _activity(client, exp_id, since_seq=seen)["events"] == []

    client.patch(
        f"/api/experiments/{exp_id}",
        json={"title": "Later"},
        headers=_etag(client, exp_id),
    )
    fresh = _activity(client, exp_id, since_seq=seen)
    assert [e["seq"] for e in fresh["events"]] == [4]
    # `total` still describes the RECORD, not the window.
    assert fresh["total"] == 4
    assert fresh["matched"] == 1


def test_a_filter_narrows_matched_and_leaves_total_alone(client):
    exp_id = _create(client)
    client.patch(
        f"/api/experiments/{exp_id}",
        json={"title": "Renamed"},
        headers=_etag(client, exp_id),
    )
    client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers=_etag(client, exp_id),
    )
    narrowed = _activity(client, exp_id, action="experiment_renamed")
    assert narrowed["matched"] == 1
    assert narrowed["total"] == 2
    assert [e["action"] for e in narrowed["events"]] == ["experiment_renamed"]


def test_an_unknown_filter_value_is_refused_rather_than_answered_as_empty(client):
    """An empty list would be a claim about the RECORD. The honest answer is 422."""
    exp_id = _create(client)
    for key, value in (
        ("action", "did_something"),
        ("channel", "carrier-pigeon"),
        ("object_type", "thingummy"),
    ):
        refused = client.get(
            f"/api/experiments/{exp_id}/activity", params={key: value}
        )
        assert refused.status_code == 422, (key, refused.text)
        body = refused.json()
        assert body["error"] == "unknown_activity_filter"
        # The admissible sets travel with the refusal, so a client never guesses.
        assert "actions" in body and "channels" in body and "object_types" in body


def test_the_limit_is_clamped_rather_than_refused_and_the_clamp_is_observable(client):
    exp_id = _create(client)
    body = _activity(client, exp_id, limit=100000)
    assert body["limit"] == 200


# ==========================================================================
# the actor, and the header that must never become one
# ==========================================================================


def test_a_forged_edge_identity_header_does_not_become_the_actor(client):
    """``DEC-45``, measured: seven planted headers, every event still unattributed.

    This is the HTTP half of ``activity.actor_from_identity``'s claim. The function
    reads no request; this proves that nothing ELSE in the write path does either.
    """
    planted = "attacker-supplied-name"
    forged = {
        "X-authentik-username": planted,
        "X-authentik-uid": planted,
        "X-authentik-email": f"{planted}@example.invalid",
        "X-authentik-name": planted,
        "X-authentik-groups": "admin",
        "X-authentik-entitlements": "everything",
        "X-Isaac-Edge": "traversed",
    }
    exp_id = _create(client)
    renamed = client.patch(
        f"/api/experiments/{exp_id}",
        json={"title": "Renamed by a forged caller"},
        headers={**_etag(client, exp_id), **forged},
    )
    assert renamed.status_code == 200, renamed.text

    events = _activity(client, exp_id)["events"]
    assert events, "nothing was recorded, so this test proves nothing"
    for event in events:
        assert event["actor"] == "unattributed", event
        assert event["actor_trust_basis"] == "unattributed", event
    # And the planted value reaches no part of the stored history.
    assert planted not in json.dumps(events)


def test_even_a_fixture_attributed_deployment_records_unattributed_today(
    tmp_path, monkeypatch
):
    """``ACT-005`` IS NOT BUILT, and this is what "not built" looks like measurably.

    The fixture verifier CAN attribute a request — it is what makes proposal
    acceptance reachable at all — and the activity history deliberately does not
    consume it. Wiring it is ``ACT-005``, blocked on ``EXT-01``. Asserting the
    current behaviour means a future slice that wires it has to change a test on
    purpose rather than by accident.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, "synthetic-test-scientist")
    from isaac_api.app import create_app

    armed = TestClient(create_app(), raise_server_exceptions=False)
    # The verifier really is armed, so this is not vacuous.
    assert identity.actor_attribution_status()["can_attribute"] is True

    exp_id = _create(armed)
    armed.patch(
        f"/api/experiments/{exp_id}",
        json={"title": "Renamed under the fixture verifier"},
        headers=_etag(armed, exp_id),
    )
    events = _activity(armed, exp_id)["events"]
    assert events
    assert {e["actor"] for e in events} == {"unattributed"}


# ==========================================================================
# ACT-002: the channel
# ==========================================================================


def test_an_http_write_records_the_web_channel(client):
    exp_id = _create(client)
    client.patch(
        f"/api/experiments/{exp_id}",
        json={"title": "Renamed"},
        headers=_etag(client, exp_id),
    )
    assert {e["channel"] for e in _activity(client, exp_id)["events"]} == {"web"}


def test_an_MCP_write_records_the_mcp_channel_and_an_http_one_does_not(
    tmp_path, monkeypatch
):
    """THE CHANNEL DISTINCTION, DRIVEN. Both surfaces reach the SAME route function.

    This is the test that would catch the whole mechanism failing silently: if the
    ``ContextVar`` did not reach the route handler, an agent's write would be
    recorded as ``web`` and nothing else in the build would notice.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app
    from isaac_api.mcp.deployment import LocalLoopbackDeployment
    from isaac_api.mcp.policy import Scope
    from isaac_api.mcp.server import McpServer

    app = create_app()
    http = TestClient(app, raise_server_exceptions=False)
    exp_id = _create(http)

    # A note first, because a proposal must cite one — the agent's own entry point.
    agent = McpServer(
        app,
        binding=LocalLoopbackDeployment(
            # The scope set `isaac_capture_note` needs, taken from
            # `test_mcp_note_pathway_end_to_end.py` rather than guessed: this build
            # has exactly three scopes (`READ`, `DRAFT_WRITE`, `PROPOSALS_WRITE`) and
            # a note capture costs the last two of those.
            scopes=frozenset({Scope.READ, Scope.PROPOSALS_WRITE}),
            tutorial_session_id=None,
        ),
    )

    def _tool(name, **arguments):
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        reply = asyncio.run(agent.handle(message))
        assert "error" not in reply, reply
        assert reply["result"].get("isError") is not True, reply
        return reply["result"]

    # THE QUOTED `ETag` HEADER, not the bare `version` token: `_check_if_match`
    # requires one or more STRONG QUOTED validators and the MCP layer forwards this
    # string verbatim, so a bare token is `400 malformed_if_match`.
    etag = http.get(f"/api/experiments/{exp_id}").headers["ETag"]
    _tool(
        "isaac_capture_note",
        experiment_id=exp_id,
        text="Agent heard: the cell sat at 301 K throughout.",
        if_match=etag,
        client_request_key="synthetic-agent-key-1",
    )

    events = _activity(http, exp_id)["events"]
    assert events, "the agent's write recorded nothing"
    captured = [e for e in events if e["action"] == "note_captured"]
    assert len(captured) == 1, events
    assert captured[0]["channel"] == "mcp", (
        "an agent's write was recorded as though a person had made it; the ambient "
        "channel did not reach the route handler"
    )

    # And the ambient scope did NOT leak: a subsequent HTTP write is `web`.
    http.patch(
        f"/api/experiments/{exp_id}",
        json={"title": "Renamed by a person"},
        headers=_etag(http, exp_id),
    )
    renamed = [
        e for e in _activity(http, exp_id)["events"] if e["action"] == "experiment_renamed"
    ]
    assert [e["channel"] for e in renamed] == ["web"]


# ==========================================================================
# tutorial isolation — inherited, not re-invented
# ==========================================================================


def test_a_worked_example_session_never_persists_activity_as_a_normal_experiment(
    tmp_path, monkeypatch
):
    """``CLAUDE.md`` §15's invariant, asserted for the new key rather than assumed.

    The isolation is INHERITED: activity lives inside the experiment state document,
    and a worked-example record's document lives in the session scope, which
    ``PostgresOrdinaryStore.refuse_if_not_persistable`` refuses to persist. Nothing
    new was built for it — this test is what says so.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app
    from isaac_api.experiment_repository import PostgresOrdinaryStore

    app = create_app()
    tutorial = TestClient(app, raise_server_exceptions=False)
    opened = tutorial.post("/api/tutorial/sessions")
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["session_id"]
    record_id = opened.json()["record_ids"][0]
    tutorial.headers["X-Isaac-Tutorial-Session"] = session_id

    # A NOTE CAPTURE RATHER THAN A RENAME, AND THE REASON IS ITSELF WORTH KEEPING:
    # `PATCH /api/experiments/{id}` answers `409 ordinary_scope_required` inside a
    # worked-example session, because the built-in examples are fixed teaching
    # material. Capturing a note is accepted there, so it is the act that actually
    # puts activity on a session-scoped record — which is what this test needs.
    captured = tutorial.post(
        f"/api/experiments/{record_id}/notes",
        json={"text": "A remark made inside the worked example.", "source": "typed_note"},
        headers=_etag(tutorial, record_id),
    )
    assert captured.status_code == 201, captured.text
    assert _activity(tutorial, record_id)["total"] >= 1

    # THE RECORD CARRYING THAT ACTIVITY IS REFUSED BY THE DURABLE STORE, so the row
    # cannot reach the database under any configuration.
    scoped = ws.load_experiment(record_id, session_id=session_id)
    assert scoped is not None and scoped.activity
    with pytest.raises(Exception):
        PostgresOrdinaryStore.refuse_if_not_persistable(scoped)

    # And the ordinary workspace holds no such record at all.
    assert ws.load_experiment(record_id) is None
