"""HISTORICAL IMPORT over HTTP — the nine operations, and the whole chain.

``HIST-001`` (session + bundle + manifest), ``HIST-003a`` (the provider-neutral
reconstruction contract) and the review half of ``HIST-004``.

THE CHAIN ``HIST-003a`` REQUIRES, PROVEN END TO END IN ONE TEST
===============================================================

    Parsed Source Evidence -> Semantic Candidate Reconstruction
      -> the SHARED proposal model -> Scientist Review -> ISAAC Draft
      -> Deterministic Validation

``test_the_whole_chain_from_a_parsed_source_to_a_validated_draft`` walks it over
HTTP with nothing stubbed, under the fixture edge verifier (the only
configuration in which a person can accept anything — see **I4** in
``test_ingestion_proposals.py``), and finishes by reading the value out of the
record's own exported draft and running the deterministic validator over it.

AND THE OTHER HALF OF THAT CLAIM — that semantic output CANNOT become record
truth automatically — is proven by
``test_a_default_configured_deployment_refuses_the_acceptance`` and
``test_reconstructing_and_proposing_changes_no_field_anywhere``.

MUTATION-CHECKED
================

A test whose docstring carries a ``MUTATION:`` line was verified by BREAKING the
production code in the way the test claims to catch, confirming it went RED, and
reverting. A test without one does not claim to have been.

DATA BOUNDARY: none. Every source is one of the two committed synthetic fixtures
or a pointer string written here; the workspace is a ``tmp_path``; no database
connection is opened and nothing under ``examples/`` is read.
"""

from __future__ import annotations

import copy
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.routes as routes
import isaac_api.workspace as ws

BUNDLE_A = "SYNTHETIC-bundle-a.txt"
BUNDLE_B = "SYNTHETIC-bundle-b.txt"

#: The one record-scoped writable path, so the chain can be proven on a record
#: with NO runs. Taken from the application's own derived set rather than written
#: out: a hand-copied literal would be a second definition of "a real target".
RECORD_PATH = "system.technique"
RUN_PATH = "sample.material.name"

ACTOR = "ada.lovelace"


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    return ws


@pytest.fixture()
def client(workspace):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def armed_client(workspace, monkeypatch):
    """A deployment that CAN attribute: the fixture verifier, with a subject.

    No shipped deploy artifact sets these two variables (``test_deploy_config.py``
    pins that), so this is deliberately a configuration no deployment has. Both
    the refusal path and the acceptance path are real behaviour and a suite that
    could reach only one would assert half the contract.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


# --- helpers ------------------------------------------------------------------


def _new_import(client, label="An old CuO campaign") -> str:
    response = client.post("/api/imports", json={"label": label})
    assert response.status_code == 200, response.text
    return response.json()["import"]["import_id"]


def _add_fixture(client, import_id: str, name: str):
    return client.post(
        f"/api/imports/{import_id}/sources",
        json={"kind": "synthetic_fixture", "fixture_name": name},
    )


def _add_pointer(client, import_id: str, **over):
    body = {
        "kind": "reference",
        "filename": "scan_0012.mac",
        "reference": "/nfs/fake-beamline/2019/scan_0012.mac",
    }
    body.update(over)
    return client.post(f"/api/imports/{import_id}/sources", json=body)


def _bundle(client) -> str:
    """A session holding both fixtures and one pointer, parsed and reconstructed."""
    import_id = _new_import(client)
    assert _add_fixture(client, import_id, BUNDLE_A).status_code == 200
    assert _add_fixture(client, import_id, BUNDLE_B).status_code == 200
    assert _add_pointer(client, import_id).status_code == 200
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    response = client.post(f"/api/imports/{import_id}/reconstruct")
    assert response.status_code == 200, response.text
    return import_id


def _candidate(client, import_id: str, path: str) -> dict:
    response = client.get(f"/api/imports/{import_id}")
    assert response.status_code == 200, response.text
    for candidate in response.json()["import"]["reconstruction"]["candidates"]:
        if candidate["target_field_path"] == path:
            return candidate
    raise AssertionError(f"no candidate at {path}")


def _structural_candidate(client, import_id: str) -> dict:
    response = client.get(f"/api/imports/{import_id}")
    for candidate in response.json()["import"]["reconstruction"]["candidates"]:
        if candidate["kind"] != "field":
            return candidate
    raise AssertionError("no structural candidate")


def _record(client, title="An old CuO campaign") -> str:
    response = client.post("/api/experiments", json={"title": title})
    # 201, not 200: this operation always creates. Measured rather than assumed —
    # the first version of this helper asserted 200 and read `["experiment"]["id"]`,
    # and the real route answers 201 with the experiment as the WHOLE body.
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _draft(client, eid: str) -> dict:
    """The record's draft, read through the detail route.

    The detail payload does not carry `draft`, so this reads it off the stored
    record — measured, not assumed: an earlier version of this helper reached for
    `json()["experiment"]["draft"]` and found neither key.
    """
    exp = ws.load_experiment(eid)
    assert exp is not None
    return copy.deepcopy(exp.draft)


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _propose(client, import_id, candidate_id, eid, *, if_match=..., **body):
    body.setdefault("experiment_id", eid)
    tag = _etag(client, eid) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(
        f"/api/imports/{import_id}/candidates/{candidate_id}/propose",
        json=body,
        headers=headers,
    )


# --- §1 the session -----------------------------------------------------------


def test_a_new_session_is_empty_and_says_it_is_not_durable(client):
    body = client.post("/api/imports", json={"label": "A bundle"}).json()["import"]
    assert body["label"] == "A bundle"
    assert body["sources"] == []
    assert body["reconstruction"] is None
    assert body["furthest_step"] == "new_import"
    assert "not part of the durable record store" in body["durability"]
    # THE WORKFLOW COMES FROM THE SERVER, so a client carries no second copy.
    assert [row["label"] for row in body["workflow"]] == [
        "New Import",
        "Sources",
        "Parse",
        "Reconstruct",
        "Review",
        "Add to Experiments",
    ]
    # EVERY STEP IS BUILT since 2026-09-15. This asserted
    # `[row["id"] for row in unbuilt] == ["add_to_experiments"]` and that its
    # disclosure said "Not built in this build"; `HIST-005` shipped that step, so
    # the old assertion is now the assertion of a defect. The property that
    # mattered is kept and is stronger here: the server declares `built` for
    # every row, so a client cannot show an unbuilt step as available by omission.
    assert [row["id"] for row in body["workflow"] if not row["built"]] == []
    assert all(row["disclosure"] is None for row in body["workflow"])


def test_creating_a_session_creates_no_experiment(client):
    _new_import(client)
    assert client.get("/api/experiments").json()["experiments"] == []


def test_a_body_key_this_operation_does_not_accept_is_refused_by_name(client):
    response = client.post("/api/imports", json={"label": "x", "title": "y"})
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"
    assert response.json()["keys"] == ["title"]


def test_the_list_carries_counts_and_never_the_bundle(client):
    import_id = _bundle(client)
    body = client.get("/api/imports").json()
    assert body["total"] == 1
    (entry,) = body["imports"]
    assert entry["import_id"] == import_id
    assert entry["source_count"] == 3
    assert entry["parsed_source_count"] == 2
    assert entry["candidate_count"] == 4
    for absent in ("sources", "parsed", "reconstruction"):
        assert absent not in entry, absent


def test_an_unknown_session_is_a_named_404(client):
    response = client.get("/api/imports/01AAAAAAAAAAAAAAAAAAAAAAAA")
    assert response.status_code == 404
    assert response.json()["error"] == "import_session_not_found"


def test_discarding_a_session_leaves_its_proposal_and_its_note_on_the_record(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    minted = _propose(client, import_id, candidate["candidate_id"], eid)
    assert minted.status_code == 200, minted.text
    proposal_id = minted.json()["proposal"]["proposal_id"]
    note_id = minted.json()["note"]["id"]

    assert client.delete(f"/api/imports/{import_id}").status_code == 200
    assert client.get(f"/api/imports/{import_id}").status_code == 404

    proposals = client.get(f"/api/experiments/{eid}/proposals").json()["proposals"]
    assert [p["proposal_id"] for p in proposals] == [proposal_id]
    listed = client.get(f"/api/experiments/{eid}/notes").json()["notes"]
    assert [n["id"] for n in listed] == [note_id]


# --- §2 the manifest ----------------------------------------------------------


def test_a_pointer_is_recorded_with_the_reason_it_cannot_be_parsed(client):
    import_id = _new_import(client)
    body = _add_pointer(client, import_id).json()
    assert body["source"]["parse_state"] == "no_content_path"
    assert "has not opened the file" in body["source"]["parse_detail"]
    assert body["source"]["provenance"]["bytes_read_by_this_application"] is False


def test_no_upload_operation_exists_and_the_upload_route_is_untouched(client):
    """The import surface adds no way to send bytes, and changes nothing about the
    one route that refuses them."""
    schema = client.get("/api/openapi").json()
    import_ops = [
        (path, method, op)
        for path, item in schema["paths"].items()
        if "/imports" in path
        for method, op in item.items()
        if method in ("get", "post", "put", "patch", "delete")
    ]
    # 10 since 2026-09-15 — `HIST-005` added `POST .../add-to-experiment`, which
    # is JSON-only like every other one, so the property this test exists for is
    # unchanged and the count is the thing that moved.
    assert len(import_ops) == 10
    for path, method, op in import_ops:
        content = ((op.get("requestBody") or {}).get("content") or {})
        assert set(content) <= {"application/json"}, f"{method} {path}: {list(content)}"
    assert client.post("/api/uploads").status_code == 403


def test_a_digest_of_the_wrong_shape_is_refused_and_never_computed(client):
    import_id = _new_import(client)
    bad = _add_pointer(client, import_id, sha256="nope")
    assert bad.status_code == 422
    assert bad.json()["error"] == "malformed_sha256"
    assert "never computes one" in bad.json()["message"]
    # And a fixture this build DOES read still carries no digest.
    good = _add_fixture(client, import_id, BUNDLE_A)
    assert good.json()["source"]["sha256"] is None


def test_a_fixture_name_off_the_allowlist_is_refused_and_reveals_nothing(client):
    import_id = _new_import(client)
    for name in ("../../../etc/passwd", "/etc/passwd", "does-not-exist.txt"):
        response = client.post(
            f"/api/imports/{import_id}/sources",
            json={"kind": "synthetic_fixture", "fixture_name": name},
        )
        assert response.status_code == 422, name
        body = response.json()
        assert body["error"] == "unknown_fixture", name
        # THE SAME BRANCH for a traversal attempt and for a merely-absent name, so
        # this operation cannot be used to find out what files exist.
        assert sorted(body["available"]) == sorted(hist.fixture_names())


def test_removing_a_source_discards_the_reading_and_the_candidates(client):
    import_id = _bundle(client)
    before = client.get(f"/api/imports/{import_id}").json()["import"]
    victim = before["sources"][0]["source_id"]
    response = client.delete(f"/api/imports/{import_id}/sources/{victim}")
    assert response.status_code == 200, response.text
    after = response.json()["import"]
    assert len(after["sources"]) == 2
    assert after["parsed"] == []
    assert after["reconstruction"] is None
    assert after["unmapped_keys"] == []


def test_removing_a_source_this_session_does_not_hold_is_its_own_404(client):
    import_id = _bundle(client)
    response = client.delete(f"/api/imports/{import_id}/sources/nope")
    assert response.status_code == 404
    # DISTINCT from `import_session_not_found`: one says the workspace has no such
    # session, this says the session was read and holds no such entry.
    assert response.json()["error"] == "import_source_not_found"


# --- §3 parse -----------------------------------------------------------------


def test_parse_reads_the_fixtures_leaves_the_pointer_and_reports_what_it_skipped(client):
    import_id = _new_import(client)
    _add_fixture(client, import_id, BUNDLE_A)
    _add_pointer(client, import_id)
    body = client.post(f"/api/imports/{import_id}/parse").json()["import"]

    assert body["source_counts"] == {
        "total": 2,
        "parsed": 1,
        "failed": 0,
        "no_content_path": 1,
        "unparsed": 0,
        "parsable_by_this_build": 1,
    }
    (parsed,) = body["parsed"]
    keys = {row["key"] for row in parsed["statements"]}
    assert keys == {
        "system.technique",
        "sample.material.name",
        "system.configuration.detector_model",
        "operator_initials",
    }
    # A LINE IT COULD NOT READ IS REPORTED, not dropped.
    assert [row["reason"] for row in parsed["skipped"]] == ["no_key_value_separator"]
    # EVERY value is verbatim and carries the line it came from.
    for row in parsed["statements"]:
        assert row["locator"].startswith("line ")


def test_parse_writes_nothing_about_any_record(client):
    eid = _record(client)
    before = client.get(f"/api/experiments/{eid}").json()
    import_id = _bundle(client)
    assert import_id
    after = client.get(f"/api/experiments/{eid}").json()
    assert after == before


# --- §4 reconstruct -----------------------------------------------------------


def test_reconstruct_applies_nothing_and_says_so_on_the_wire(client):
    import_id = _bundle(client)
    body = client.get(f"/api/imports/{import_id}").json()["import"]
    assert body["reconstruction"]["applied"] is False
    assert body["provider"]["applied"] is False
    assert body["provider"]["provider_id"] == "deterministic_fake"


def test_the_beamline_profile_this_build_offers_encodes_no_convention(client):
    import_id = _bundle(client)
    profile = client.get(f"/api/imports/{import_id}").json()["import"]["beamline_profile"]
    assert profile["is_empty"] is True
    assert profile["conventions_encoded"] == 0


def test_a_deterministic_candidate_names_the_key_and_the_line_it_was_read_from(client):
    import_id = _bundle(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    assert candidate["determinism"] == "deterministic"
    assert candidate["proposed_value"] == "XAS"
    assert candidate["proposable"] is True
    assert "system.technique" in candidate["rule"]
    assert "No alias, synonym or normalisation was applied." in candidate["rule"]
    # WHICH SOURCES SUPPORT IT — both fixtures state it.
    assert len(candidate["supporting_source_ids"]) == 2
    assert len(candidate["supporting_statements"]) == 2


def test_a_disagreement_is_served_with_every_competing_value_and_no_choice(client):
    import_id = _bundle(client)
    candidate = _candidate(client, import_id, RUN_PATH)
    assert candidate["unresolved_reason"] == "sources_disagree"
    assert candidate["proposed_value"] is None
    assert candidate["proposable"] is False
    assert sorted(row["value"] for row in candidate["disagreement"]) == [
        "SYNTHETIC-CuO-FAKE-001",
        "SYNTHETIC-CuO-FAKE-002",
    ]


def test_a_key_that_is_not_a_field_path_is_reported_and_never_guessed_at(client):
    import_id = _bundle(client)
    body = client.get(f"/api/imports/{import_id}").json()["import"]
    unmapped = {row["key"]: row for row in body["unmapped_keys"]}
    assert "operator_initials" in unmapped
    assert unmapped["operator_initials"]["value"] == "ZZ"
    assert unmapped["operator_initials"]["reason"] == "not_an_official_field_path"
    paths = {c["target_field_path"] for c in body["reconstruction"]["candidates"]}
    assert "operator_initials" not in paths


def test_reconstructing_with_nothing_parsed_is_refused_rather_than_empty(client):
    import_id = _new_import(client)
    _add_pointer(client, import_id)
    client.post(f"/api/imports/{import_id}/parse")
    response = client.post(f"/api/imports/{import_id}/reconstruct")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "nothing_parsed"


# --- §5 propose: the shared review pipeline ----------------------------------


def test_proposing_mints_one_open_proposal_citing_one_note(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    body = _propose(client, import_id, candidate["candidate_id"], eid).json()

    assert body["deduplicated"] is False
    proposal = body["proposal"]
    assert proposal["state"] == "open"
    assert proposal["target_field_path"] == RECORD_PATH
    assert proposal["proposed_value"] == "XAS"
    # THE RECONSTRUCTION'S OWN RULE SENTENCE, carried verbatim.
    assert proposal["rule"] == candidate["rule"]
    # A PROPOSAL IS NOT A VALUE AND NOT EVIDENCE, and the constants cross the wire.
    assert proposal["is_field_value"] is False
    assert proposal["is_evidence"] is False
    assert proposal["verified"] is False

    note = body["note"]
    assert proposal["note_id"] == note["id"]
    assert note["source"] == "historical_source_line"
    # THE SOURCE'S OWN WORDS, with the file and line they were read from.
    assert note["text"].startswith(f"{BUNDLE_A} (line ")
    assert note["text"].endswith("system.technique = XAS")


def test_the_excerpt_is_derived_and_is_exactly_the_proposed_value(client):
    """The end-to-end half. **NOT mutation-proof on its own — see the test below.**

    Measured: replacing the span computation with `text.find(value)` leaves this
    test GREEN, because the committed fixtures' values appear exactly once in the
    note text. It is an EQUIVALENT MUTANT here, and saying so is the point: this
    test proves the excerpt is derived and correct on a real request, and the unit
    test below is what makes the span rule itself non-vacuous.
    """
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    proposal = _propose(client, import_id, candidate["candidate_id"], eid).json()[
        "proposal"
    ]
    assert proposal["excerpt"] == "XAS"


def test_the_span_is_computed_from_the_pieces_not_searched_for():
    """MUTATION: `text.find(value)` makes this RED.

    WHY IT NEEDED A UNIT TEST. The end-to-end test above cannot fail for this
    reason on the committed fixtures — every value there occurs once — so a
    `find`-based span would ship green. Here the value occurs in the FILENAME and
    in the KEY before it occurs as the value, which is exactly the case a search
    gets wrong: `find` returns the first occurrence, and the excerpt would then be
    a slice of the filename.
    """
    statement = {"key": "XAS.note", "value": "XAS", "locator": "line 1"}
    filename = "XAS-campaign.txt"
    text = routes._import_note_text(statement, filename)
    start, end = routes._import_note_value_span(statement, filename)
    assert text[start:end] == "XAS"
    # The proof that a search would have been wrong: the first occurrence is not
    # the value.
    assert text.find("XAS") != start
    assert text.find("XAS") == 0


def test_proposing_is_exactly_once_per_candidate_on_one_record(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    first = _propose(client, import_id, candidate["candidate_id"], eid)
    assert first.json()["deduplicated"] is False
    second = _propose(client, import_id, candidate["candidate_id"], eid)
    assert second.status_code == 200, second.text
    assert second.json()["deduplicated"] is True
    assert second.json()["note"] is None
    assert (
        second.json()["proposal"]["proposal_id"]
        == first.json()["proposal"]["proposal_id"]
    )
    proposals = client.get(f"/api/experiments/{eid}/proposals").json()["proposals"]
    assert len(proposals) == 1


def test_the_exactly_once_guarantee_does_not_depend_on_the_session(client):
    """MUTATION: the guarantee is the record's own `client_request_key` lookup, so
    it survives the session being discarded and rebuilt over the same sources —
    which is the case a session-side record of what was proposed cannot cover."""
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    assert _propose(client, import_id, candidate["candidate_id"], eid).status_code == 200
    # The session forgets, by being deleted and its candidate id reused directly.
    assert client.delete(f"/api/imports/{import_id}").status_code == 200
    # A second attempt through the same session id and candidate id now 404s at the
    # session, which is correct — but the RECORD still holds exactly one proposal
    # and its key is the one this import minted.
    again = _propose(client, import_id, candidate["candidate_id"], eid)
    assert again.status_code == 404
    proposals = client.get(f"/api/experiments/{eid}/proposals").json()["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["client_request_key"] == (
        f"import:{import_id}:{candidate['candidate_id']}"
    )


def test_the_session_records_which_candidates_were_sent(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    _propose(client, import_id, candidate["candidate_id"], eid)
    body = client.get(f"/api/imports/{import_id}").json()["import"]
    (row,) = body["proposed"].values()
    assert row["experiment_id"] == eid

    # `add_to_experiments` SINCE 2026-09-15, and it is not a loosening: this
    # bundle has exactly ONE proposable candidate — measured here rather than
    # assumed, because the assertion below only means what it says if that is
    # true — so sending it really does finish the step. The other three are
    # reported unproposable for reasons the review surface shows: sources that
    # disagree, a path this build cannot write, and a structural candidate.
    # `test_the_furthest_step_is_derived_and_reaches_the_last_step_only_when_done`
    # covers the partial case, where one send of several is still `review`.
    candidates = body["reconstruction"]["candidates"]
    assert [c["target_field_path"] for c in candidates if c["proposable"]] == [
        RECORD_PATH
    ]
    assert body["furthest_step"] == "add_to_experiments"


def test_the_record_etag_is_required_not_the_session(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)

    absent = _propose(client, import_id, candidate["candidate_id"], eid, if_match=None)
    assert absent.status_code == 428, absent.text
    malformed = _propose(
        client, import_id, candidate["candidate_id"], eid, if_match="not-a-validator"
    )
    assert malformed.status_code == 400
    stale = _propose(
        client, import_id, candidate["candidate_id"], eid, if_match='"nope.0"'
    )
    assert stale.status_code == 412
    # NOTHING WAS WRITTEN by any of the three.
    assert client.get(f"/api/experiments/{eid}/proposals").json()["proposals"] == []
    assert client.get(f"/api/experiments/{eid}/notes").json()["notes"] == []


def test_a_disagreeing_candidate_cannot_be_proposed(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RUN_PATH)
    response = _propose(client, import_id, candidate["candidate_id"], eid)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "candidate_unresolved"
    assert body["unresolved_reason"] == "sources_disagree"
    assert len(body["disagreement"]) == 2
    assert client.get(f"/api/experiments/{eid}/proposals").json()["proposals"] == []


def test_a_structural_candidate_cannot_be_proposed_and_says_why(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _structural_candidate(client, import_id)
    assert candidate["determinism"] == "inferred"
    response = _propose(client, import_id, candidate["candidate_id"], eid)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "candidate_not_proposable"
    assert "creates an experiment or a run from an import" in response.json()["message"]


def test_a_recognised_path_with_no_write_route_cannot_be_proposed(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, "system.configuration.detector_model")
    assert candidate["proposable"] is False
    response = _propose(client, import_id, candidate["candidate_id"], eid)
    assert response.status_code == 422, response.text
    message = response.json()["message"]
    # THE LIMITATION IS THIS BUILD'S, and the refusal never speaks for the schema.
    assert "LIMITATION OF THIS BUILD" in message
    assert "NOT A STATEMENT ABOUT THE OFFICIAL ISAAC SCHEMA" in message


def test_a_run_scoped_candidate_needs_the_run_named_and_never_infers_it(client):
    """The record has exactly ONE run, and it is still not chosen for the caller."""
    import_id = _new_import(client)
    _add_fixture(client, import_id, BUNDLE_A)
    client.post(f"/api/imports/{import_id}/parse")
    client.post(f"/api/imports/{import_id}/reconstruct")
    candidate = _candidate(client, import_id, RUN_PATH)
    assert candidate["proposable"] is True

    eid = _record(client)
    run = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "Run A"},
        headers={"If-Match": _etag(client, eid)},
    )
    # 201, measured: adding a run always creates.
    assert run.status_code == 201, run.text
    run_id = run.json()["run"]["id"]

    without = _propose(client, import_id, candidate["candidate_id"], eid)
    assert without.status_code == 422, without.text
    assert without.json()["error"] == "target_requires_a_run"

    with_run = _propose(client, import_id, candidate["candidate_id"], eid, run_id=run_id)
    assert with_run.status_code == 200, with_run.text
    assert with_run.json()["proposal"]["run_id"] == run_id


def test_a_record_scoped_candidate_refuses_a_run(client):
    import_id = _bundle(client)
    eid = _record(client)
    run = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "Run A"},
        headers={"If-Match": _etag(client, eid)},
    )
    run_id = run.json()["run"]["id"]
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = _propose(
        client, import_id, candidate["candidate_id"], eid, run_id=run_id
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "target_is_record_scoped"


def test_an_unknown_run_is_refused_rather_than_ignored(client):
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = _propose(
        client, import_id, candidate["candidate_id"], eid, run_id="nope"
    )
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_run"


def test_the_experiment_is_never_chosen_for_the_caller(client):
    """Not even when the workspace holds exactly one record."""
    import_id = _bundle(client)
    only = _record(client)
    assert only
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = client.post(
        f"/api/imports/{import_id}/candidates/{candidate['candidate_id']}/propose",
        json={},
        headers={"If-Match": _etag(client, only)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "missing_experiment_id"


def test_proposing_onto_a_record_that_does_not_exist_is_the_records_404(client):
    import_id = _bundle(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = client.post(
        f"/api/imports/{import_id}/candidates/{candidate['candidate_id']}/propose",
        json={"experiment_id": "01AAAAAAAAAAAAAAAAAAAAAAAA"},
        headers={"If-Match": '"x.0"'},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "experiment_not_found"


# --- §6 semantic output cannot become record truth ---------------------------


def test_reconstructing_and_proposing_changes_no_field_anywhere(client):
    """The **I1**/**I2** property, restated for the import producer.

    MUTATION: applying the candidate's value in the propose handler (rather than
    only minting a proposal) makes both halves of this RED.
    """
    eid = _record(client)
    import_id = _bundle(client)
    before = _draft(client, eid)
    before_detail = client.get(f"/api/experiments/{eid}").json()

    candidate = _candidate(client, import_id, RECORD_PATH)
    assert _propose(client, import_id, candidate["candidate_id"], eid).status_code == 200

    after = _draft(client, eid)
    assert after == before, "the propose operation wrote a field"

    # AND THE DETAIL ROUTE'S DERIVED STATE CANNOT SEE IT EITHER except as a
    # PROPOSAL COUNT: a proposal is outside `draft`, so the workflow spine, the
    # pending count and the export verdict are all unmoved by one existing.
    detail = client.get(f"/api/experiments/{eid}").json()
    assert detail["open_proposal_count"] == 1
    assert detail["pending_count"] == before_detail["pending_count"]
    assert detail["workflow"]["current_step"] == before_detail["workflow"]["current_step"]
    assert detail["draft_ok"] == before_detail["draft_ok"]


def test_a_default_configured_deployment_refuses_the_acceptance(client):
    """The other half of ``HIST-003a``'s central claim.

    A candidate reaching a record as an OPEN proposal is the whole of what an
    import can do. Turning it into a value needs a trusted human identity, and no
    default-configured deployment establishes one.
    """
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    proposal = _propose(client, import_id, candidate["candidate_id"], eid).json()[
        "proposal"
    ]
    response = client.post(
        f"/api/experiments/{eid}/proposals/{proposal['proposal_id']}/review",
        json={
            "action": "accept",
            "accepted_from": "candidate",
            "confirmed_by_user": True,
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "human_actor_required"
    # STILL OPEN, and the record still holds nothing at that path.
    listed = client.get(f"/api/experiments/{eid}/proposals").json()["proposals"]
    assert listed[0]["state"] == "open"


def test_the_whole_chain_from_a_parsed_source_to_a_validated_draft(armed_client):
    """``HIST-003a`` END TO END, over HTTP, with nothing stubbed.

        parsed source evidence -> semantic candidate -> shared proposal model
          -> scientist review -> ISAAC draft -> deterministic validation

    Run under the fixture edge verifier, which is the ONLY configuration in which
    a person can accept anything — see **I4** in ``test_ingestion_proposals.py``.
    The point of running it there is that the chain is provably complete, and the
    point of the test above is that in every shipped configuration it stops at the
    proposal.
    """
    client = armed_client
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)

    # 1-3. parsed evidence -> candidate -> proposal.
    minted = _propose(client, import_id, candidate["candidate_id"], eid)
    assert minted.status_code == 200, minted.text
    proposal_id = minted.json()["proposal"]["proposal_id"]

    # 4. scientist review, by a person the deployment can attribute.
    accepted = client.post(
        f"/api/experiments/{eid}/proposals/{proposal_id}/review",
        json={
            "action": "accept",
            "accepted_from": "candidate",
            "confirmed_by_user": True,
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["proposal"]["state"] == "accepted"

    # 5. THE ISAAC DRAFT now holds the value, with the evidence the writer minted.
    #
    # `draft["fields"][path]`, measured — NOT a nested `draft["system"]["technique"]`,
    # which is what the first version of this test reached for and which raised
    # `KeyError: 'system'`. The record's own field map is what `_apply_record_fields`
    # writes and what `serialize`/`export` read; the nested official shape is
    # composed on the way OUT, not stored.
    exp = ws.load_experiment(eid)
    envelope = exp.draft["fields"][RECORD_PATH]
    assert envelope["value"] == "XAS"
    assert envelope["status"] == "verified"
    assert envelope["evidence"], "the accepted value carries no evidence"
    # THE EVIDENCE IS A USER CONFIRMATION, minted by the writer manual entry uses —
    # not by anything in the import path, which mints none.
    assert envelope["evidence"][0]["source_type"] == "user_confirmation"

    # 6. DETERMINISTIC VALIDATION over that draft — the truth core, unmodified.
    from isaac_records.draft_validator import validate_draft

    report = validate_draft(exp.draft)
    # `DraftReport` is a dataclass carrying `errors` and `warnings` — measured, not
    # assumed: the first version of this test called `report.get("issues")` and
    # raised `AttributeError`.
    offending = [
        issue for issue in report.errors if RECORD_PATH in str(issue)
    ]
    assert offending == [], offending
    # AND THE WHOLE DRAFT STILL PASSES the no-guessing validator: the accepted
    # value did not introduce an unevidenced field anywhere.
    assert report.errors == [], report.errors


def test_the_accepted_value_is_attributed_to_the_person_not_to_the_import(armed_client):
    """An import proposes; a PERSON accepts. The attribution must say the second.

    MUTATION: stamping the import as the actor makes this RED — which is the
    defect class §11 records for `descriptors.outputs[].generated_by`, where a
    demo agent claimed authorship of a scientist's descriptor.
    """
    client = armed_client
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    proposal = _propose(client, import_id, candidate["candidate_id"], eid).json()[
        "proposal"
    ]
    # The PROPOSER is unattributed: creating a proposal writes no value, so no
    # actor is established for it.
    assert proposal["trust_basis"] == "unattributed"
    assert proposal["subject"] is None

    accepted = client.post(
        f"/api/experiments/{eid}/proposals/{proposal['proposal_id']}/review",
        json={
            "action": "accept",
            "accepted_from": "candidate",
            "confirmed_by_user": True,
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert accepted.status_code == 200, accepted.text
    history = accepted.json()["proposal"]["history"]
    accept_row = [row for row in history if row["action"] == "accept"][-1]
    assert accept_row["actor_subject"] == ACTOR
    assert accept_row["actor_trust_basis"] != "unattributed"


def test_a_corrected_value_is_what_lands_not_the_imports(armed_client):
    """A scientist disagreeing with a source is the point of the review step."""
    client = armed_client
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    proposal = _propose(client, import_id, candidate["candidate_id"], eid).json()[
        "proposal"
    ]
    other = [
        value for value in routes._record_enum_fields()[RECORD_PATH] if value != "XAS"
    ][0]
    accepted = client.post(
        f"/api/experiments/{eid}/proposals/{proposal['proposal_id']}/review",
        json={
            "action": "accept",
            "accepted_from": "edited",
            # THE KEY IS `value`, measured — `accepted_value` is refused by name.
            "value": other,
            "confirmed_by_user": True,
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert accepted.status_code == 200, accepted.text
    exp = ws.load_experiment(eid)
    assert exp.draft["fields"][RECORD_PATH]["value"] == other
    # The proposal still records what the SOURCE said, which is the audit trail.
    assert accepted.json()["proposal"]["proposed_value"] == "XAS"


# --- §7 scope isolation -------------------------------------------------------


def test_an_import_session_is_invisible_to_the_experiment_list(client):
    """Structural: `_imports` is `_`-prefixed and `_experiment_dirs` skips it."""
    _bundle(client)
    assert client.get("/api/experiments").json()["experiments"] == []
    assert ws._experiment_dirs(ws.workspace_root()) == []


def test_a_worked_example_sessions_imports_are_invisible_to_the_ordinary_scope(client):
    created = client.post("/api/tutorial/sessions")
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]
    headers = {"X-Isaac-Tutorial-Session": session_id}

    scoped = client.post("/api/imports", json={"label": "in a session"}, headers=headers)
    assert scoped.status_code == 200, scoped.text
    scoped_id = scoped.json()["import"]["import_id"]

    assert client.get("/api/imports").json()["imports"] == []
    assert client.get(f"/api/imports/{scoped_id}").status_code == 404
    listed = client.get("/api/imports", headers=headers).json()["imports"]
    assert [row["import_id"] for row in listed] == [scoped_id]


def test_a_worked_example_session_header_naming_nothing_is_refused(client):
    response = client.get(
        "/api/imports", headers={"X-Isaac-Tutorial-Session": "a" * 22}
    )
    assert response.status_code == 404, response.text


# --- §8 the refusals are typed, never tracebacks ------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "reference"},  # no filename, no reference
        {"kind": "reference", "filename": "f"},  # no reference
        {"kind": "synthetic_fixture"},  # no fixture name
        {"kind": "not_a_kind", "filename": "f", "reference": "r"},
        {"kind": "reference", "filename": "f", "reference": "r", "size_bytes": -1},
        {"kind": "reference", "filename": "f", "reference": "r", "size_bytes": True},
        {"kind": "reference", "filename": "f", "reference": "r", "media_type": 7},
        {"kind": "reference", "filename": "", "reference": "r"},
    ],
)
def test_a_malformed_source_is_a_typed_422_and_never_a_500(client, body):
    import_id = _new_import(client)
    response = client.post(f"/api/imports/{import_id}/sources", json=body)
    assert response.status_code == 422, response.text
    assert "error" in response.json()
    assert response.json()["error"] != "internal_error"
    # And nothing was stored.
    assert client.get(f"/api/imports/{import_id}").json()["import"]["sources"] == []


def test_a_lone_surrogate_body_key_is_echoed_safely_rather_than_500ing(client):
    """The `_echoable_key` bound, at this publication boundary too.

    MUTATION: echoing `key` unbounded reproduces the `UnicodeEncodeError` that
    `_asset_refusal`'s docstring records — a 500 out of a refusal.
    """
    import_id = _new_import(client)
    response = client.post(
        f"/api/imports/{import_id}/sources",
        content='{"\\ud800": 1}'.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] in {"unrecognized_field", "invalid_body"}


def test_a_non_object_body_is_refused_on_every_operation_that_takes_one(client):
    import_id = _new_import(client)
    for path in (
        "/api/imports",
        f"/api/imports/{import_id}/sources",
    ):
        response = client.post(path, json=["not", "an", "object"])
        assert response.status_code == 422, f"{path}: {response.text}"


def test_an_import_id_that_could_name_a_path_never_reaches_a_filesystem_read(client):
    for bad in ("..", "lowercase", "a" * 200):
        for method, path in (
            ("get", f"/api/imports/{bad}"),
            ("delete", f"/api/imports/{bad}"),
            ("post", f"/api/imports/{bad}/parse"),
            ("post", f"/api/imports/{bad}/reconstruct"),
        ):
            response = getattr(client, method)(path)
            assert response.status_code in (404, 422), f"{method} {path}: {response.text}"


# --- §9 the per-record ceilings bind on THIS route too -----------------------


def test_the_note_ceilings_bind_on_the_propose_route(client, monkeypatch):
    """FOUND IN MY OWN CODE, BY READING `post_note` RATHER THAN BY A FAILING TEST.

    This operation mints a NOTE as well as a proposal, and the note lands in the
    same document — which is parsed on every read and hashed on every save, the
    reason the bound exists at all. The first version of this route checked the
    proposal ROW count and neither note ceiling, so a large import could have
    grown the notes block past what `POST .../notes` refuses.

    `_note_capacity_refusal` is CALLED rather than reimplemented, so this route is
    its SECOND caller. **A PRE-EXISTING GAP IS NAMED AND NOT FIXED:**
    `POST .../transcript` mints one note per segment and calls that helper at no
    point, so the note ceilings do not bind there either. That is a separate change.

    MUTATION: removing the `capacity` check makes this RED.
    """
    monkeypatch.setattr(routes, "_MAX_NOTES_PER_RECORD", 0)
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = _propose(client, import_id, candidate["candidate_id"], eid)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "too_many_notes"
    assert response.json()["max_per_record"] == 0
    # NOTHING WAS WRITTEN — neither half of the pair.
    assert client.get(f"/api/experiments/{eid}/notes").json()["notes"] == []
    assert client.get(f"/api/experiments/{eid}/proposals").json()["proposals"] == []


def test_the_proposal_byte_ceiling_binds_on_the_propose_route(client, monkeypatch):
    """The other half of the parity with `POST .../proposals`.

    MUTATION: removing the projected-byte check makes this RED.
    """
    monkeypatch.setattr(routes, "_MAX_PROPOSAL_STATE_BYTES", 1)
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = _propose(client, import_id, candidate["candidate_id"], eid)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "proposals_too_large"
    assert client.get(f"/api/experiments/{eid}/proposals").json()["proposals"] == []


def test_the_proposal_row_ceiling_binds_on_the_propose_route(client, monkeypatch):
    monkeypatch.setattr(routes, "_MAX_PROPOSALS_PER_RECORD", 0)
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = _propose(client, import_id, candidate["candidate_id"], eid)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "too_many_proposals"


def test_all_three_ceilings_leave_the_import_session_untouched(client, monkeypatch):
    """A refused send must not record itself as sent.

    The session's `proposed` map is written AFTER the record and outside the
    record lock, so a refusal that returned before the write is the case that
    matters: the surface must not show a candidate as sent when no proposal
    exists.
    """
    monkeypatch.setattr(routes, "_MAX_PROPOSALS_PER_RECORD", 0)
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    assert _propose(client, import_id, candidate["candidate_id"], eid).status_code == 422
    body = client.get(f"/api/imports/{import_id}").json()["import"]
    assert body["proposed"] == {}
    assert body["furthest_step"] == "reconstruct"


def test_discarding_a_worked_example_session_takes_its_imports_with_it(client):
    """The isolation guarantee, for imports too — and it is STRUCTURAL.

    A worked-example session's imports live at `<session root>/_imports/`, and
    `dispose_tutorial_session` removes that root, so nothing about imports had to
    be taught to the disposal path. Asserted rather than assumed: a session's
    working area outliving the session would be exactly the leak `CLAUDE.md` §15
    calls the invariant this feature must not break.
    """
    created = client.post("/api/tutorial/sessions")
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]
    headers = {"X-Isaac-Tutorial-Session": session_id}

    scoped = client.post("/api/imports", json={"label": "in a session"}, headers=headers)
    assert scoped.status_code == 200, scoped.text
    scoped_id = scoped.json()["import"]["import_id"]
    assert client.get(f"/api/imports/{scoped_id}", headers=headers).status_code == 200

    disposed = client.delete(f"/api/tutorial/sessions/{session_id}")
    assert disposed.status_code == 204, disposed.text

    # The session's whole root is gone, so the import went with it -- and the
    # ordinary workspace never held it in the first place.
    assert hist.list_sessions() == []
    assert not (hist.imports_root() / scoped_id).exists()


def test_an_unreadable_shipped_source_refuses_with_no_filesystem_path(client, monkeypatch, tmp_path):
    """A deployment fault, refused with a STABLE CODE and NO PATH.

    An `OSError` message carries the filename it failed on, which is why this
    route catches `OSError` and answers a fixed sentence instead of interpolating
    the exception. `workspace._log`'s own rule is the same: a log line is an
    exfiltration surface too, and an `OSError` in particular names the file.

    MUTATION: interpolating `str(exc)` into the body makes this RED.
    """
    import_id = _new_import(client)
    assert _add_fixture(client, import_id, BUNDLE_A).status_code == 200

    secret = tmp_path / "a-path-nobody-should-see" / "secret.txt"

    def explode(_source):
        raise OSError(f"[Errno 13] Permission denied: '{secret}'")

    monkeypatch.setattr(hist, "_fixture_text", explode)
    response = client.post(f"/api/imports/{import_id}/parse")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "source_unreadable"
    assert "problem with the deployment" in body["message"]
    # THE PATH IS NOT IN THE RESPONSE, anywhere in it.
    serialized = json.dumps(body)
    assert str(secret) not in serialized
    assert "a-path-nobody-should-see" not in serialized
    assert str(tmp_path) not in serialized
    assert "Errno" not in serialized


def test_a_note_larger_than_one_note_may_be_is_refused_not_shortened(client, monkeypatch):
    """THE PER-NOTE BYTE BOUND, and `_note_text_refusal` is its THIRD caller.

    A note's own size limit is enforced at the ROUTE — `notes.Note` does not check
    it — so a route that mints a note without calling that helper has no per-note
    bound at all. The per-RECORD ceilings are a DIFFERENT bound and do not imply
    this one: `_MAX_NOTE_STATE_BYTES` is sixteen times `_MAX_NOTE_BYTES`, so one
    oversized note passes it.

    UNREACHABLE ON THE COMMITTED EXAMPLE SOURCES, which is why it is worth a test
    rather than an argument: their lines are short, but a parsed line is bounded
    only by `MAX_SOURCE_TEXT_BYTES` (1,000,000) while a note is bounded by
    256 KiB. The ceiling is lowered here rather than a giant source invented,
    because the bound is what is under test and not the parser.

    MUTATION: removing the `_note_text_refusal` call makes this RED.
    """
    monkeypatch.setattr(routes, "_MAX_NOTE_BYTES", 8)
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    response = _propose(client, import_id, candidate["candidate_id"], eid)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    assert "REFUSED rather than shortened" in response.json()["message"]
    # NEITHER HALF OF THE PAIR WAS WRITTEN.
    assert client.get(f"/api/experiments/{eid}/notes").json()["notes"] == []
    assert client.get(f"/api/experiments/{eid}/proposals").json()["proposals"] == []

# --- HIST-005 · Add an Import to a Record -------------------------------------
#
# The import workflow's SIXTH step, which until 2026-09-15 the surface rendered
# as unbuilt with the server's own reason and no control at all. It is one
# operation because the scientist's act is one act: a client looping over the
# single-candidate route would make N requests, each able to fail on its own, and
# a `412` partway through would leave a record holding part of an import with
# nothing able to say which part.
#
# EVERY TEST BELOW THAT CLAIMS "NOTHING WAS WRITTEN" CHECKS THREE THINGS — the
# record's `rev` did not move, its proposal list is unchanged, and its note list
# is unchanged. Checking only the proposals would pass while a batch left orphan
# notes on the record, which is the exact half-written state one lock and one
# save exist to make impossible.


def _bundle_a_only(client) -> str:
    """One fixture, parsed and reconstructed.

    SEPARATE FROM `_bundle` ON PURPOSE, and the difference is the point: adding
    BUNDLE_B makes the sources DISAGREE about `sample.material.name`, which makes
    that candidate unproposable. `_bundle` therefore has exactly one proposable
    candidate and it is record-scoped; this one has a proposable RUN-scoped
    candidate, which is the only way to exercise the run half of the batch.
    """
    import_id = _new_import(client)
    assert _add_fixture(client, import_id, BUNDLE_A).status_code == 200
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return import_id


def _add_to(client, import_id, eid, *, if_match=..., **body):
    body.setdefault("experiment_id", eid)
    tag = _etag(client, eid) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(
        f"/api/imports/{import_id}/add-to-experiment", json=body, headers=headers
    )


def _record_shape(client, eid):
    """(rev, proposal ids, note ids) — what "nothing was written" is measured over."""
    exp = ws.load_experiment(eid)
    assert exp is not None
    return (
        exp.rev,
        sorted(p.proposal_id for p in exp.proposals),
        sorted(n.id for n in exp.notes),
    )


def _run_on(client, eid, label="Run A") -> str:
    run = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": label},
        headers={"If-Match": _etag(client, eid)},
    )
    assert run.status_code == 201, run.text
    return run.json()["run"]["id"]


def test_the_batch_sends_every_proposable_candidate_and_names_the_rest(client):
    import_id = _bundle(client)
    eid = _record(client)
    before = _record_shape(client, eid)

    response = _add_to(client, import_id, eid)
    assert response.status_code == 200, response.text
    body = response.json()

    # ONE candidate is proposable in this bundle; three are not, each for a
    # reason the review surface already shows. Asserted by PATH rather than by
    # count, so a fixture change cannot make this pass for the wrong candidate.
    assert [row["target_field_path"] for row in body["sent"]] == [RECORD_PATH]
    assert body["sent"][0]["already_sent"] is False
    assert body["sent"][0]["run_id"] is None
    assert {row["error"] for row in body["not_sent"]} == {
        "candidate_unresolved",
        "candidate_not_proposable",
    }
    assert body["counts"] == {
        "candidates": 4,
        "sent": 1,
        "already_sent": 0,
        "not_sent": 3,
    }
    # THE COUNTS SUM, which is what makes the report a report rather than four
    # independent numbers.
    assert (
        body["counts"]["sent"]
        + body["counts"]["already_sent"]
        + body["counts"]["not_sent"]
        == body["counts"]["candidates"]
    )
    # EVERY unproposable candidate carries its own reason, not a generic one.
    for row in body["not_sent"]:
        assert row["reason"], row
        assert row["candidate_id"]

    after = _record_shape(client, eid)
    # ONE new revision for the whole batch, and the note and the proposal landed
    # together.
    assert after[0] == before[0] + 1
    assert len(after[1]) == 1
    assert len(after[2]) == 1


def test_the_batch_is_one_write_for_many_candidates(client):
    """Two proposable candidates, one revision, two proposals and two notes."""
    import_id = _bundle_a_only(client)
    eid = _record(client)
    run_id = _run_on(client, eid)
    before = _record_shape(client, eid)

    response = _add_to(client, import_id, eid, run_id=run_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["sent"] >= 2, body["counts"]

    after = _record_shape(client, eid)
    # THE REVISION MOVED BY EXACTLY ONE for N candidates. This is the assertion
    # that fails if this route is ever reimplemented as a loop over the
    # single-candidate one.
    assert after[0] == before[0] + 1, (before[0], after[0], body["counts"])
    assert len(after[1]) == body["counts"]["sent"]
    assert len(after[2]) == body["counts"]["sent"]


def test_the_batch_writes_no_scientific_value(client):
    import_id = _bundle_a_only(client)
    eid = _record(client)
    run_id = _run_on(client, eid)
    before = _draft(client, eid)

    assert _add_to(client, import_id, eid, run_id=run_id).status_code == 200
    # BYTE-FOR-BYTE. A proposal is a suggestion awaiting a person's judgement;
    # this operation puts an import in front of a scientist and applies nothing.
    assert _draft(client, eid) == before


def test_every_proposal_the_batch_mints_is_open_and_cites_a_note_on_the_record(client):
    import_id = _bundle_a_only(client)
    eid = _record(client)
    run_id = _run_on(client, eid)
    assert _add_to(client, import_id, eid, run_id=run_id).status_code == 200

    proposals = client.get(f"/api/experiments/{eid}/proposals").json()["proposals"]
    note_ids = {n["id"] for n in client.get(f"/api/experiments/{eid}/notes").json()["notes"]}
    assert proposals
    for proposal in proposals:
        assert proposal["state"] == "open"
        # THE CITATION RESOLVES. A proposal citing a note the record does not hold
        # is the broken state the one-write guarantee exists to prevent, and it
        # would be invisible to a test that only counted rows.
        assert proposal["note_id"] in note_ids
        assert proposal["client_request_key"].startswith(f"import:{import_id}:")


def test_the_batch_is_exactly_once_and_a_second_run_writes_nothing(client):
    import_id = _bundle(client)
    eid = _record(client)
    assert _add_to(client, import_id, eid).status_code == 200
    after_first = _record_shape(client, eid)

    second = _add_to(client, import_id, eid)
    assert second.status_code == 200, second.text
    body = second.json()
    assert [row["already_sent"] for row in body["sent"]] == [True]
    assert body["counts"]["sent"] == 0
    assert body["counts"]["already_sent"] == 1
    # NO SECOND PROPOSAL, AND NO SECOND REVISION. The revision matters as much as
    # the count: the record's `version` is the basis of every `If-Match`, so a
    # save for a request that changed nothing would invalidate a token another
    # reader is legitimately holding.
    assert _record_shape(client, eid) == after_first


def test_the_batch_and_the_single_candidate_route_are_exactly_once_together(client):
    """A candidate sent by hand and then included in a batch mints ONE proposal."""
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    assert _propose(client, import_id, candidate["candidate_id"], eid).status_code == 200

    response = _add_to(client, import_id, eid)
    assert response.status_code == 200, response.text
    assert response.json()["sent"][0]["already_sent"] is True
    proposals = client.get(f"/api/experiments/{eid}/proposals").json()["proposals"]
    assert len(proposals) == 1
    # THE SHARED KEY IS WHY. Both operations derive it from the import id and the
    # candidate id, so neither can be fooled by the other having gone first.
    assert proposals[0]["client_request_key"] == (
        f"import:{import_id}:{candidate['candidate_id']}"
    )


def test_a_run_scoped_candidate_without_a_run_refuses_the_WHOLE_batch(client):
    import_id = _bundle_a_only(client)
    eid = _record(client)
    _run_on(client, eid)  # the record HAS a run, and it is still not chosen for you
    before = _record_shape(client, eid)

    response = _add_to(client, import_id, eid)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "target_requires_a_run"
    assert RUN_PATH in [row["target_field_path"] for row in body["candidates"]]
    assert "WHOLE BATCH IS REFUSED" in body["message"]

    # NOTHING WAS WRITTEN — not even the record-scoped candidates that COULD have
    # gone. Sending only those would silently leave the run's values behind, and
    # the scientist would have no way to tell a finished import from a partial one.
    assert _record_shape(client, eid) == before


def test_the_run_goes_only_to_the_candidates_written_on_a_run(client):
    import_id = _bundle_a_only(client)
    eid = _record(client)
    run_id = _run_on(client, eid)

    body = _add_to(client, import_id, eid, run_id=run_id).json()
    by_path = {row["target_field_path"]: row for row in body["sent"]}
    assert by_path[RUN_PATH]["run_id"] == run_id
    # AND THE RECORD-SCOPED ONE DID NOT GET IT. This is the documented difference
    # from the single-candidate route, which REFUSES a run_id for a record-scoped
    # target; here one run is given for a whole import and applied where it
    # belongs, because a record-scoped candidate in the same batch is not a
    # mistake.
    assert by_path[RECORD_PATH]["run_id"] is None

    proposals = {
        p["target_field_path"]: p
        for p in client.get(f"/api/experiments/{eid}/proposals").json()["proposals"]
    }
    assert proposals[RUN_PATH]["run_id"] == run_id
    assert proposals[RECORD_PATH]["run_id"] is None


def test_an_unknown_run_refuses_the_batch_and_writes_nothing(client):
    import_id = _bundle_a_only(client)
    eid = _record(client)
    _run_on(client, eid)
    before = _record_shape(client, eid)

    response = _add_to(client, import_id, eid, run_id="01NOPE")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"
    assert _record_shape(client, eid) == before


def test_the_record_etag_is_required_for_the_batch_not_the_sessions(client):
    import_id = _bundle(client)
    eid = _record(client)
    before = _record_shape(client, eid)

    assert _add_to(client, import_id, eid, if_match=None).status_code == 428
    assert _add_to(client, import_id, eid, if_match="not-a-validator").status_code == 400
    # A WELL-FORMED BUT WRONG STRONG VALIDATOR. `W/"0"` was the first attempt and
    # it answers 400 `malformed_if_match`, not 412 — a weak validator never
    # reaches the comparison, so that version proved the malformed branch twice
    # and the stale branch not at all.
    stale = _add_to(client, import_id, eid, if_match='"nope.0"')
    assert stale.status_code == 412, stale.text
    # Three refusals, and the record is exactly as it was after all of them.
    assert _record_shape(client, eid) == before


def test_the_batch_refuses_an_unknown_record_and_a_missing_one(client):
    import_id = _bundle(client)
    eid = _record(client)

    unknown = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": "01NOSUCHRECORD"},
        headers={"If-Match": _etag(client, eid)},
    )
    assert unknown.status_code == 404, unknown.text

    missing = _add_to(client, import_id, eid, experiment_id="   ")
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"] == "missing_experiment_id"
    # It is never chosen for you, not even with exactly one record in the
    # workspace — which is the case here.
    assert "never chosen for you" in missing.json()["message"]


def test_a_body_key_the_batch_does_not_accept_is_refused_by_name(client):
    import_id = _bundle(client)
    eid = _record(client)
    response = _add_to(client, import_id, eid, apply="yes")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"
    assert response.json()["keys"] == ["apply"]


def test_an_unknown_session_is_a_named_404_for_the_batch(client):
    eid = _record(client)
    response = client.post(
        "/api/imports/01NOSUCHIMPORT/add-to-experiment",
        json={"experiment_id": eid},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 404, response.text


def test_a_session_with_candidates_but_none_proposable_refuses_and_lists_why(client):
    """Candidates exist and NONE can be proposed: refused whole, each reason given.

    WHY THIS ONE PATCHES AND THE OTHERS DO NOT, stated rather than left to be
    found. No committed fixture reaches this state — `_bundle` always has exactly
    one proposable candidate (`system.technique`), and making it unproposable
    would need two sources DISAGREEING about the technique, which no fixture
    here provides. Two wrong ways were tried first and are recorded so nobody
    repeats them: sending the proposable candidate by hand does not help (exactly-
    once makes the batch report it `already_sent`, which is a 200), and a
    pointer-only session cannot be reconstructed at all (`POST /reconstruct`
    answers 422), so it has no candidates and lands in the OTHER branch.

    WHAT IS PATCHED IS THE DATA SOURCE, NOT THE LOGIC UNDER TEST. The candidates
    handed to the route are the REAL objects a real reconstruction produced, with
    the one proposable member filtered out — not fabricated stand-ins. The route's
    own partitioning, message selection and refusal all run unmodified, which is
    the behaviour this test is about. A control below proves the filter did what
    it claims rather than silently returning everything.
    """
    import_id = _bundle(client)
    eid = _record(client)
    before = _record_shape(client, eid)

    session = hist.load_session(import_id)
    assert session is not None
    real = list(hist.candidates_of(session))
    unproposable = [c for c in real if not c.proposable]
    # THE CONTROL: the filter must actually have removed something, or this test
    # would be asserting the refusal of a batch that had work to do.
    assert len(unproposable) == len(real) - 1 == 3, (len(real), len(unproposable))

    with mock.patch.object(hist, "candidates_of", return_value=unproposable):
        response = _add_to(client, import_id, eid)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "nothing_to_send"
    assert "nothing to send" in body["message"]
    assert body["counts"] == {
        "candidates": 3,
        "sent": 0,
        "already_sent": 0,
        "not_sent": 3,
    }
    # THE ANSWER EXPLAINS ITSELF: every candidate is listed with its own reason,
    # so a scientist is not told "nothing could be sent" and left to guess which
    # of four things went wrong.
    assert len(body["not_sent"]) == 3
    for row in body["not_sent"]:
        assert row["reason"]
        assert row["error"] in ("candidate_unresolved", "candidate_not_proposable")
    assert _record_shape(client, eid) == before


def test_a_session_with_no_reconstruction_yet_says_to_reconstruct_it_first(client):
    import_id = _new_import(client)
    assert _add_fixture(client, import_id, BUNDLE_A).status_code == 200
    eid = _record(client)
    before = _record_shape(client, eid)

    response = _add_to(client, import_id, eid)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "nothing_to_send"
    # A DIFFERENT SENTENCE FOR A DIFFERENT SITUATION. "Nothing can be proposed"
    # and "you have not reconstructed yet" are not the same problem, and telling
    # a scientist the first when the second is true sends them looking for a
    # defect in their sources.
    assert "reconstruct it first" in body["message"]
    assert body["counts"]["candidates"] == 0
    assert _record_shape(client, eid) == before


def test_the_batch_records_every_send_in_the_session_and_finishes_the_step(client):
    import_id = _bundle_a_only(client)
    eid = _record(client)
    run_id = _run_on(client, eid)

    body = _add_to(client, import_id, eid, run_id=run_id).json()
    view = client.get(f"/api/imports/{import_id}").json()["import"]

    # EVERY sent candidate is recorded, not just the last one.
    assert set(view["proposed"]) == {row["candidate_id"] for row in body["sent"]}
    for row in view["proposed"].values():
        assert row["experiment_id"] == eid
        assert row["proposal_id"]
        assert row["note_id"]

    # AND THE WORKFLOW REACHES ITS LAST STEP, because every proposable candidate
    # has now been sent. That is the strict criterion: `furthest_step` returns
    # `review` while any remain.
    assert view["furthest_step"] == "add_to_experiments"
    assert [row["id"] for row in view["workflow"] if not row["built"]] == []


def test_the_batch_appears_in_the_openapi_document_as_json_only(client):
    schema = client.get("/api/openapi").json()
    path = "/api/imports/{import_id}/add-to-experiment"
    assert path in schema["paths"], sorted(schema["paths"])
    operation = schema["paths"][path]["post"]
    assert set((operation.get("requestBody") or {}).get("content") or {}) == {
        "application/json"
    }
    # THE DESCRIPTION MUST NOT CLAIM TO APPLY ANYTHING. This route's whole safety
    # argument is that it writes no value, and the document a machine reads is
    # where that claim has to be true too.
    assert "WRITES NO VALUE" in operation["description"]
    assert "ignored for the ones written on the record" in operation["description"]


def test_a_persisted_candidate_whose_writer_is_gone_is_refused_not_crashed(client):
    """A session document outlives the code that wrote it.

    `candidate.proposable` means the RECONSTRUCTION found a write path. A session
    saved by an older build could name a path this one no longer writes, and
    `_proposal_writer_for` would answer `None` — which, without the guard, makes
    the `_PROPOSAL_WRITER_SCOPE` lookup a `KeyError`, i.e. a **500 out of a route
    whose whole job is to refuse clearly**.

    DRIVEN BY NARROWING WHAT THIS BUILD WRITES, not by hand-editing a session
    document: `_proposal_writer_for` is patched to answer `None`, which is exactly
    what a build that dropped a write operation would do. The candidates are the
    real ones a real reconstruction produced and are still `proposable`, which is
    the whole point — that flag records a past build's finding.

    THE SINGLE-CANDIDATE ROUTE HAS THE SAME EXPOSURE and is deliberately not
    covered here; it is pre-existing and is named in the route's own comment.
    """
    import_id = _bundle(client)
    eid = _record(client)
    before = _record_shape(client, eid)

    with mock.patch.object(routes, "_proposal_writer_for", return_value=None):
        response = _add_to(client, import_id, eid)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "no_write_path_for_field"
    assert [row["target_field_path"] for row in body["candidates"]] == [RECORD_PATH]
    # THE CLAUSE THAT MATTERS SCIENTIFICALLY: this says something about the build,
    # never about the official schema, which defines the field.
    assert "NOT A STATEMENT ABOUT THE OFFICIAL ISAAC SCHEMA" in body["message"]
    assert _record_shape(client, eid) == before


def test_the_guard_does_not_fire_when_every_writer_is_present(client):
    """A negative control: the refusal above is reachable ONLY by removing a writer.

    Without this, the test above would pass just as well if the guard fired on
    every request, and the batch would refuse everything.
    """
    import_id = _bundle(client)
    eid = _record(client)
    response = _add_to(client, import_id, eid)
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["sent"] == 1


def test_the_single_candidate_route_refuses_a_vanished_writer_too(client):
    """The sibling of `test_a_persisted_candidate_whose_writer_is_gone_...`.

    Both routes reach `_PROPOSAL_WRITER_SCOPE[_proposal_writer_for(path)]`, and
    both would raise `KeyError` on a session reconstructed by a build that had a
    writer this one does not. The batch route's guard shipped first and NAMED this
    one as open; it is closed here in the same change, so that comment is a
    correction rather than a standing pointer at a defect.
    """
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)
    before = _record_shape(client, eid)

    with mock.patch.object(routes, "_proposal_writer_for", return_value=None):
        response = _propose(client, import_id, candidate["candidate_id"], eid)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "no_write_path_for_field"
    assert body["target_field_path"] == RECORD_PATH
    assert "NOT A STATEMENT ABOUT THE OFFICIAL ISAAC SCHEMA" in body["message"]
    assert _record_shape(client, eid) == before


def test_neither_route_refuses_when_the_writer_is_present(client):
    """A negative control covering BOTH routes in one place.

    Without it, the two patched tests above would pass just as well if the guards
    fired unconditionally — in which case nothing from an import could ever reach
    a record, which is the one thing these routes are for.
    """
    import_id = _bundle(client)
    eid = _record(client)
    candidate = _candidate(client, import_id, RECORD_PATH)

    single = _propose(client, import_id, candidate["candidate_id"], eid)
    assert single.status_code == 200, single.text
    assert single.json()["deduplicated"] is False

    # And the batch, on a second record, so the first one's exactly-once does not
    # make this vacuous.
    other = _record(client, title="A second destination")
    batch = _add_to(client, import_id, other)
    assert batch.status_code == 200, batch.text
    assert batch.json()["counts"]["sent"] == 1
