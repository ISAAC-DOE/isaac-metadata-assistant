"""An adversarial-input sweep over the CAPTURE surface, and only the NEW ground.

WHY THIS FILE EXISTS, AND WHAT IT DELIBERATELY DOES NOT RE-TEST
=================================================================
Voice/transcript capture is the product's largest unstructured-input surface —
``POST .../transcript``, ``POST .../notes`` (+ its review), ``POST .../proposals``
(+ its review), and ``POST /api/transcription`` — and, per a coverage survey run
before this file was written, it had never had a dedicated sweep of its own. That
survey read ``test_attack_unrepresentable_request_values.py``,
``test_attack_injection_and_containment.py``, ``test_transcript_capture.py``,
``test_transcript_capture_mints_proposals.py``, ``test_ingestion_proposals.py``,
``test_run_scoped_proposal_lifecycle.py`` and ``test_notes.py`` end to end. Each
test below closes a SPECIFIC gap that survey named; none re-asserts something one
of those files already pins. The most consequential things the survey found
ALREADY covered, so a reader does not go looking for them here:

* the segment ceiling (``MAX_SEGMENTS``) on ``/transcript``,
* blank/whitespace text on ``/transcript`` and ``/notes``,
* oversized and lone-surrogate ``proposed_value`` (size, not depth) on
  ``/proposals``,
* stale ``If-Match`` and duplicate ``client_request_key``/transcript-finalize on
  every one of these five routes,
* wildcard ``If-Match`` on both proposal routes,
* NaN/Infinity across the whole OpenAPI surface via a generic fuzz sweep
  (:mod:`test_attack_unrepresentable_request_values`) — this file adds the ONE
  case that generic sweep does not aim at: ``proposed_value`` itself, by name,
  on ``/proposals``.

WHAT COUNTS AS A DEFECT HERE, PER THE BRIEF THAT AUTHORIZED THIS FILE
=======================================================================
A 5xx from any of the five routes is always a defect. A typed 4xx is correct
behaviour. Every test below asserts the MEASURED status and body, not a status
this file's author expected in advance — where a measurement disagreed with an
intuition, the intuition lost.

DATA BOUNDARY: none. Everything here is synthetic, written into a ``tmp_path``
workspace. No file outside it is read or written, nothing connects to a database,
and no production-derived content is touched. No application code was changed to
write this file — see the report accompanying this change for findings that were
measured but deliberately left unfixed.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.routes as routes
import isaac_api.workspace as ws

from conftest import client_ws, tutorial_client
from test_export_fan_out import _split_full_draft

# =============================================================================
# Shared fixtures and helpers — tutorial scope, for /transcript and /notes
# =============================================================================


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
        "Capture-sweep fixture", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
    )
    return exp.id


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _make_run(client, experiment_id: str) -> dict:
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]


def _finalize(client, experiment_id: str, text: str, *, if_match=..., **extra):
    body: dict = {"text": text, "finalized": True}
    body.update(extra)
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(
        f"/api/experiments/{experiment_id}/transcript", json=body, headers=headers
    )


def _capture_note(client, experiment_id: str, text: str, *, if_match=..., **extra):
    body: dict = {"text": text, "source": "typed_note", **extra}
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(f"/api/experiments/{experiment_id}/notes", json=body, headers=headers)


def _notes(client, experiment_id: str) -> list[dict]:
    response = client.get(f"/api/experiments/{experiment_id}/notes")
    assert response.status_code == 200, response.text
    return response.json()["notes"]


# =============================================================================
# 1. TRANSCRIPT — exact byte ceiling, measured rather than assumed
# =============================================================================


def test_transcript_text_exactly_at_the_byte_ceiling_is_accepted_and_over_it_is_refused(
    client, experiment_id
):
    """``_MAX_TRANSCRIPT_BYTES`` at the boundary, on the ROUTE this build enforces it on.

    ``test_text_too_large_is_refused_rather_than_truncated`` (``test_notes.py``)
    already proves ``_MAX_NOTE_BYTES + 1`` is refused on ``/notes`` — but
    ``/transcript`` has never been probed for its OWN size ceiling at all, and
    "one byte over" is not "exactly at". Rendered length is MEASURED with the
    route's own renderer rather than assumed to be ``len(text) + 2``, so this
    does not silently start passing for the wrong reason if the encoder changes.
    """
    limit = routes._MAX_TRANSCRIPT_BYTES
    at_limit_len = limit
    while len(routes._render_exactly_as_a_response_would("A" * at_limit_len)) > limit:
        at_limit_len -= 1
    text_at_limit = "A" * at_limit_len
    assert len(routes._render_exactly_as_a_response_would(text_at_limit)) == limit

    accepted = _finalize(client, experiment_id, text_at_limit)
    assert accepted.status_code == 200, accepted.text
    assert len(_notes(client, experiment_id)) == 1

    over_limit_len = at_limit_len + 1
    text_over_limit = "A" * over_limit_len
    assert len(routes._render_exactly_as_a_response_would(text_over_limit)) == limit + 1

    refused = _finalize(client, experiment_id, text_over_limit)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "unrepresentable_value"
    # Nothing new was stored: still exactly the one note from the accepted call.
    assert len(_notes(client, experiment_id)) == 1


# =============================================================================
# 2. TRANSCRIPT and NOTES — wildcard If-Match
# =============================================================================
#
# Both proposal routes are already proven to accept `*` (test_ingestion_proposals.py).
# Neither /transcript, /notes, nor /notes/{id}/review had ever been probed for it.


def test_a_wildcard_if_match_is_accepted_by_the_transcript_route(client, experiment_id):
    response = _finalize(client, experiment_id, "A clean sentence with no ambiguity.", if_match="*")
    assert response.status_code == 200, response.text
    assert len(_notes(client, experiment_id)) == 1


def test_a_wildcard_if_match_is_accepted_by_the_notes_route(client, experiment_id):
    response = _capture_note(client, experiment_id, "captured with a wildcard validator", if_match="*")
    assert response.status_code == 201, response.text


def test_a_wildcard_if_match_is_accepted_by_the_note_review_route(client, experiment_id):
    note = _capture_note(client, experiment_id, "prose to keep").json()["note"]
    response = client.post(
        f"/api/experiments/{experiment_id}/notes/{note['id']}/review",
        json={"confirmed_by_user": True, "action": "keep"},
        headers={"If-Match": "*"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["note"]["state"] == "kept"


# =============================================================================
# 3. TRANSCRIPT — Unicode edge cases the survey found untested on THIS route
# =============================================================================
#
# Combining marks, RTL override, ZWJ and astral-plane characters were exercised
# on note text in test_attack_injection_and_containment.py, and lone surrogates
# were exercised on proposal/notes BODY FIELDS (source, run_id) in
# test_attack_unrepresentable_request_values.py — never on transcript TEXT.


def test_transcript_text_with_combining_marks_zwj_and_astral_plane_characters_round_trips_verbatim(
    client, experiment_id
):
    payload = (
        "Sample labeled éclass with a zero‍joiner and an emoji \U0001F9EA stayed intact."
    )
    response = _finalize(client, experiment_id, payload)
    assert response.status_code == 200, response.text

    stored = _notes(client, experiment_id)
    assert len(stored) == 1
    assert stored[0]["text"] == payload

    # And on disk, which is what a later read actually returns.
    on_disk = ws.load_experiment(experiment_id, session_id=client.tutorial_session_id)
    assert on_disk.notes[0].text == payload


def test_a_lone_surrogate_in_transcript_text_is_refused_not_stored(client, experiment_id):
    """JSON permits a lone UTF-16 surrogate; this build's renderer does not.

    Sent as raw bytes, exactly as the neighbouring proposals test does it
    (``test_DEC4_an_unrepresentable_value_is_a_different_refusal``), because the
    test client's own encoder refuses the surrogate before the request is built.
    """
    body = json.dumps(
        {"text": "temperature drifted \ud800 overnight", "finalized": True}
    ).encode("ascii")
    response = client.post(
        f"/api/experiments/{experiment_id}/transcript",
        content=body,
        headers={
            "If-Match": _etag(client, experiment_id),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    assert _notes(client, experiment_id) == []


# =============================================================================
# 4. NUL bytes and other control characters, transcript and notes
# =============================================================================
#
# The brief names this case explicitly. Neither file the survey read sends a raw
# NUL byte inside a text BODY FIELD (only as a hostile PATH id, elsewhere). §5's
# losslessness rule says a scientist's words are stored verbatim; NUL is a legal
# JSON string codepoint, so the measured (and correct) outcome is "stored", not
# "refused" — and this pins that measurement rather than assuming it.


def test_transcript_text_with_nul_and_control_bytes_is_stored_and_read_back_verbatim(
    client, experiment_id
):
    payload = "Detector reported ok\x00 then \x07 recovered\x1b."
    response = _finalize(client, experiment_id, payload)
    assert response.status_code == 200, response.text

    stored = _notes(client, experiment_id)
    assert len(stored) == 1
    assert stored[0]["text"] == payload

    reread = client.get(f"/api/experiments/{experiment_id}/notes").json()["notes"]
    assert reread[0]["text"] == payload


def test_note_text_with_nul_and_control_bytes_is_stored_and_read_back_verbatim(
    client, experiment_id
):
    payload = "logbook entry\x00 with an embedded NUL and a bell \x07"
    response = _capture_note(client, experiment_id, payload)
    assert response.status_code == 201, response.text
    assert response.json()["note"]["text"] == payload

    note_id = response.json()["note"]["id"]
    reread = client.get(f"/api/experiments/{experiment_id}/notes/{note_id}").json()
    assert reread["note"]["text"] == payload


# =============================================================================
# 5. Script-like text in an ERROR context, not just a success context
# =============================================================================
#
# test_attack_injection_and_containment.py proves markup/instruction-shaped
# content round-trips byte-identically on a SUCCESS path (title, run label, note
# text). The brief asks a narrower and different question: is such content ever
# reflected UNESCAPED inside an ERROR message. This drives it through an actual
# refusal (`unknown_run`, which echoes the caller's `run_id` back) rather than a
# storage round trip.


def test_script_like_run_id_on_the_transcript_route_is_refused_and_echoed_as_literal_data(
    client, experiment_id
):
    hostile = "<script>alert(1)</script><img src=x onerror=alert(1)>"
    response = _finalize(client, experiment_id, "A clean sentence.", run_id=hostile)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unknown_run"
    # Echoed EXACTLY, character for character, inside a JSON string — never
    # unescaped into a raw fragment and never dropped/altered by the refusal.
    assert body["run_id"] == hostile
    assert hostile in response.text  # present verbatim in the raw JSON bytes too
    assert _notes(client, experiment_id) == []


# =============================================================================
# 6. A run_id naming a REAL run on a DIFFERENT experiment — not a fabricated one
# =============================================================================
#
# Both survey passes flagged this as the same code path as "unknown run" but
# "not directly measured" with a genuine foreign id rather than a made-up ULID.
# This proves cross-experiment run ids are not accidentally resolvable.


def test_a_run_id_belonging_to_a_different_experiment_is_refused_as_unknown_on_the_transcript_route(
    client, experiment_id
):
    other_id = client_ws(client).create_experiment(
        "Other experiment", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
    ).id
    foreign_run = _make_run(client, other_id)

    response = _finalize(client, experiment_id, "A clean sentence.", run_id=foreign_run["id"])
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"
    assert _notes(client, experiment_id) == []


def test_a_run_id_belonging_to_a_different_experiment_is_refused_as_unknown_on_the_note_route(
    client, experiment_id
):
    other_id = client_ws(client).create_experiment(
        "Other experiment", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
    ).id
    foreign_run = _make_run(client, other_id)

    response = _capture_note(client, experiment_id, "prose", run_id=foreign_run["id"])
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"


# =============================================================================
# 7. A non-boolean confirmed_by_user — note review and proposal review
# =============================================================================
#
# The check is `is not True` on both routes, so `1`/`"true"` should refuse
# identically to an ABSENT confirmation — but no test sent a truthy NON-bool.


@pytest.mark.parametrize("value", [1, "true", "True", 1.0])
def test_a_non_boolean_confirmed_by_user_is_refused_on_note_review(client, experiment_id, value):
    note = _capture_note(client, experiment_id, "prose to keep").json()["note"]
    response = client.post(
        f"/api/experiments/{experiment_id}/notes/{note['id']}/review",
        json={"confirmed_by_user": value, "action": "keep"},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "confirmation_required"


# =============================================================================
# 8. POST /api/transcription — whitespace-only manual_transcript
# =============================================================================
#
# The existing test only ever sends a MISSING manual_transcript (and an
# audio_ref-only body) to reach `input_not_supplied`. A present-but-blank string
# takes a different branch of the fake provider (`not text.strip()`), which had
# never been exercised over HTTP.


@pytest.fixture()
def transcription_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_whitespace_only_manual_transcript_is_input_not_supplied_not_501(
    transcription_client, monkeypatch, blank
):
    from isaac_api.providers.transcription import DeterministicTranscriptionFake

    monkeypatch.setattr(
        routes.provider_config,
        "resolve_transcription_provider",
        lambda: DeterministicTranscriptionFake(),
    )
    response = transcription_client.post(
        "/api/transcription", json={"manual_transcript": blank}
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["reason"] == "input_not_supplied"
    assert body["refused"] is True


# =============================================================================
# Shared fixtures and helpers — ORDINARY scope, for /proposals
# =============================================================================


@pytest.fixture()
def proposals_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


@pytest.fixture()
def proposals_client(proposals_workspace):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _new_experiment(label: str):
    experiment_draft, run_draft = _split_full_draft()
    exp = ws.create_experiment(label, {"kind": "synthetic"}, experiment_draft)
    exp.add_run(label="Run A", draft=copy.deepcopy(run_draft))
    exp.capture_note(
        text="the pellet was CuO2 and the cell sat at 300 K throughout",
        source="typed_note",
    )
    exp.save_versioned()
    return ws.load_experiment(exp.id)


@pytest.fixture()
def experiment(proposals_workspace):
    return _new_experiment("Proposals capture-sweep fixture")


OVERRIDE_PATH = "sample.material.name"


def _proposals_etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _create_proposal(client, exp, *, path=OVERRIDE_PATH, value="Cu2O", **body):
    body.setdefault("note_id", exp.notes[0].id)
    body.setdefault("target_field_path", path)
    body.setdefault("proposed_value", value)
    body.setdefault("rule", "the token after `the pellet was` matched a material label")
    if "run_id" not in body:
        body["run_id"] = exp.runs[0].id
    return client.post(
        f"/api/experiments/{exp.id}/proposals",
        json=body,
        headers={"If-Match": _proposals_etag(client, exp.id)},
    )


# =============================================================================
# 9. PROPOSALS — depth-exceeding proposed_value (size was tested; depth was not)
# =============================================================================


def test_a_deeply_nested_proposed_value_over_the_depth_ceiling_is_refused(
    proposals_client, experiment
):
    nested = "leaf"
    for _ in range(routes._MAX_VALUE_DEPTH + 8):
        nested = [nested]

    response = _create_proposal(proposals_client, experiment, value=nested)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    assert ws.load_experiment(experiment.id).proposals == []


# =============================================================================
# 10. PROPOSALS — non-finite proposed_value, by NAME rather than by fuzzing
# =============================================================================
#
# test_attack_unrepresentable_request_values.py fuzzes an unrelated body key
# (`zzz_probe`) across every route; this targets `proposed_value` itself, the
# field a caller would actually use, on the route that has its own dedicated
# non-null/depth/render/size pipeline (`_proposal_value_problem`).


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_proposed_value_is_refused_as_unrepresentable(
    proposals_client, experiment, literal
):
    raw = (
        '{"note_id": "%s", "target_field_path": "%s", "proposed_value": %s, '
        '"rule": "a rule", "run_id": "%s"}'
        % (experiment.notes[0].id, OVERRIDE_PATH, literal, experiment.runs[0].id)
    ).encode("ascii")
    response = proposals_client.post(
        f"/api/experiments/{experiment.id}/proposals",
        content=raw,
        headers={
            "If-Match": _proposals_etag(proposals_client, experiment.id),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    assert ws.load_experiment(experiment.id).proposals == []


# =============================================================================
# 11. PROPOSALS — script-like and control-character `rule` text, round-tripped
# =============================================================================
#
# test_attack_injection_and_containment.py's INJECTION_SHAPED sweep covers a
# title, a run label and note text; it never reaches a proposal's `rule` field,
# which is free text stored verbatim on the same model.


def test_script_like_rule_text_round_trips_verbatim_through_the_proposal(
    proposals_client, experiment
):
    hostile_rule = "</script><img src=x onerror=alert(1)><!-- " + "the pellet was CuO2"
    created = _create_proposal(proposals_client, experiment, rule=hostile_rule)
    assert created.status_code == 200, created.text
    assert created.json()["proposal"]["rule"] == hostile_rule

    listed = proposals_client.get(f"/api/experiments/{experiment.id}/proposals")
    assert listed.status_code == 200, listed.text
    rules = [p["rule"] for p in listed.json()["proposals"]]
    assert hostile_rule in rules


def test_nul_and_control_bytes_in_rule_text_round_trip_verbatim(proposals_client, experiment):
    hostile_rule = "matched the pellet\x00 material token \x07"
    created = _create_proposal(proposals_client, experiment, rule=hostile_rule)
    assert created.status_code == 200, created.text
    assert created.json()["proposal"]["rule"] == hostile_rule
    assert ws.load_experiment(experiment.id).proposals[0].rule == hostile_rule


# =============================================================================
# 12. PROPOSALS — a run_id belonging to a DIFFERENT experiment, at create
# =============================================================================


def test_a_run_id_belonging_to_a_different_experiment_is_refused_as_unknown_on_proposal_create(
    proposals_client, experiment
):
    other = _new_experiment("Other proposals experiment")

    response = _create_proposal(proposals_client, experiment, run_id=other.runs[0].id)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"
    assert ws.load_experiment(experiment.id).proposals == []


# =============================================================================
# 13. PROPOSALS — a non-boolean confirmed_by_user on review
# =============================================================================


@pytest.mark.parametrize("value", [1, "true", "True", 1.0])
def test_a_non_boolean_confirmed_by_user_is_refused_on_proposal_review(
    proposals_client, experiment, value
):
    proposal = _create_proposal(proposals_client, experiment).json()["proposal"]
    response = proposals_client.post(
        f"/api/experiments/{experiment.id}/proposals/{proposal['proposal_id']}/review",
        json={"confirmed_by_user": value, "action": "reject"},
        headers={"If-Match": _proposals_etag(proposals_client, experiment.id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "confirmation_required"
