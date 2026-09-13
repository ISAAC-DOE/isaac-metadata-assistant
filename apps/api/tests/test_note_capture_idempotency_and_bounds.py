"""`POST .../notes` — exactly-once, the capacity ceilings, and the agent channel.

**MCP-001 / MCP-001a / CAP-006, at the HTTP layer.** `test_mcp_note_pathway_end_to_end.py`
drives the same behaviour through the MCP dispatch; this file drives the ROUTE, because
the two callers have deliberately different contracts and a test at one layer cannot
speak for the other:

* `client_request_key` is **optional here and required by the MCP tool**. Both halves
  need proving — the optional half because the website relies on it, and the required
  half because vendor retry behaviour is UNKNOWN (`REC-012`).
* `source` is **caller-asserted here and server-stamped there**. So this file proves
  the route accepts the agent channel as a value, and the MCP file proves a caller
  cannot choose it. Neither claim implies the other, and reading the first as the
  second would be exactly the false-provenance defect `CAP-006` exists to close.

DATA BOUNDARY: none. Synthetic values in a `tmp_path` workspace; no database, no
network, no credential.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from isaac_api import notes as notes_module, routes


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def record(client) -> str:
    created = client.post("/api/experiments", json={"title": "note capture"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _etag(client: TestClient, eid: str) -> str:
    return client.get(f"/api/experiments/{eid}").headers["ETag"]


def _capture(client: TestClient, eid: str, **body):
    payload = {"text": "Synthetic: the shutter stuck.", "source": "typed_note", **body}
    return client.post(
        f"/api/experiments/{eid}/notes", json=payload, headers={"If-Match": _etag(client, eid)}
    )


# ==========================================================================
# 1. exactly-once
# ==========================================================================

def test_the_same_key_twice_stores_one_note_and_says_which_call_stored_it(client, record):
    first = _capture(client, record, client_request_key="k1")
    assert first.status_code == 201, first.text
    assert first.json()["deduplicated"] is False
    note_id = first.json()["note"]["id"]

    second = _capture(client, record, client_request_key="k1")
    # 200 NOT 201, because nothing was created. The status and the flag agree, so a
    # client need not infer one from the other.
    assert second.status_code == 200, second.text
    assert second.json()["deduplicated"] is True
    assert second.json()["note"]["id"] == note_id

    assert client.get(f"/api/experiments/{record}/notes").json()["total"] == 1


def test_the_existing_note_is_returned_even_when_the_retry_sends_different_text(
    client, record
):
    """THE CASE THE TOOL DESCRIPTION WARNS A MODEL ABOUT.

    A deduplicated result is the note the FIRST attempt stored — its text may differ
    from what this call sent. That is the correct behaviour (the key identifies the
    REQUEST, not the content) and it is the reason `deduplicated` has to be read
    before reporting what happened: a client that describes the returned note as
    "what I just captured" would be wrong about the words.
    """
    first = _capture(client, record, text="The first wording.", client_request_key="same")
    assert first.status_code == 201
    second = _capture(
        client, record, text="A completely different sentence.", client_request_key="same"
    )
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["note"]["text"] == "The first wording."
    assert client.get(f"/api/experiments/{record}/notes").json()["total"] == 1


def test_omitting_the_key_is_supported_and_every_call_stores_a_note(client, record):
    """THE WEBSITE'S CONTRACT, and it is deliberately NOT the agent's.

    A person clicking a button can see whether their note landed, so the key is
    optional here. Two keyless captures are two notes — which is correct, because two
    keyless requests are two separate acts as far as anything can tell.
    """
    for _ in range(2):
        assert _capture(client, record).status_code == 201
    assert client.get(f"/api/experiments/{record}/notes").json()["total"] == 2


def test_keyless_notes_do_not_collide_with_each_other_through_the_lookup(client, record):
    """`find_by_client_request_key` requires the STORED key to be present AND equal.

    If "no key" were treated as a key, every keyless note would deduplicate against
    the first one and the website would silently stop capturing. Asserted over the
    stored documents rather than over the function, because the function being right
    and the route calling it correctly are different claims.
    """
    _capture(client, record)
    _capture(client, record)
    stored = client.get(f"/api/experiments/{record}/notes").json()["notes"]
    assert len(stored) == 2
    assert all(n["client_request_key"] is None for n in stored), stored
    # And a keyed capture still deduplicates on the same record, so the two mechanisms
    # coexist rather than one disabling the other.
    a = _capture(client, record, client_request_key="mixed")
    b = _capture(client, record, client_request_key="mixed")
    assert (a.status_code, b.status_code) == (201, 200)
    assert client.get(f"/api/experiments/{record}/notes").json()["total"] == 3


@pytest.mark.parametrize("bad", ["", "   ", "\t", 7, True, None, [], {}])
def test_a_malformed_key_is_refused_and_never_silently_ignored(client, record, bad):
    """A BLANK KEY IS REFUSED RATHER THAN TREATED AS ABSENT, and that is the whole
    point: a caller that sent a key is relying on exactly-once, and quietly ignoring
    it would downgrade that to at-least-once with nothing on the wire saying so.

    `None` is the exception and is tested for the OPPOSITE outcome below, because JSON
    `null` is how a client spells "absent".
    """
    response = _capture(client, record, client_request_key=bad)
    if bad is None:
        assert response.status_code == 201, response.text
        return
    assert response.status_code == 422, (bad, response.status_code, response.text[:200])
    assert response.json()["error"] == "invalid_client_request_key", response.json()
    assert client.get(f"/api/experiments/{record}/notes").json()["total"] == 0


def test_an_over_long_key_is_refused_and_the_key_is_not_echoed_back(client, record):
    """The refusal names the CEILING and the MEASURED LENGTH, and not the value.

    The key is caller-supplied, and `_note_refusal`'s own docstring records that this
    route's echo enumeration has been wrong twice — so a bound that reported the value
    would be a third instance. The ceiling and the length are enough to fix a request.
    """
    key = "x" * (routes._MAX_CLIENT_REQUEST_KEY_LENGTH + 1)
    response = _capture(client, record, client_request_key=key)
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_client_request_key"
    assert body["max_length"] == routes._MAX_CLIENT_REQUEST_KEY_LENGTH
    assert body["length"] == len(key)
    assert key not in response.text, "the refusal echoed the caller's key"
    # AND THE CEILING ITSELF IS ACCEPTED — an off-by-one the other way would refuse a
    # legitimate key, which this would not otherwise catch.
    ok = _capture(
        client, record, client_request_key="y" * routes._MAX_CLIENT_REQUEST_KEY_LENGTH
    )
    assert ok.status_code == 201, ok.text


def test_the_key_is_immutable_once_stored(client, record):
    """It is in `IMMUTABLE_NOTE_FIELDS` for `id`'s reason: it is what a retry's
    exactly-once guarantee is looked up by, so a later act that could rewrite it could
    make one create appear to have happened twice."""
    assert "client_request_key" in notes_module.IMMUTABLE_NOTE_FIELDS
    note = _capture(client, record, client_request_key="frozen").json()["note"]
    stored = client.get(f"/api/experiments/{record}/notes/{note['id']}").json()["note"]
    with pytest.raises(notes_module.ImmutableCapture):
        notes_module.revise_note(
            notes_module.Note.from_state(stored), client_request_key="rewritten"
        )


def test_the_key_survives_a_reload_so_a_retry_after_a_restart_still_deduplicates(
    client, record
):
    """SERIALISED, not held in memory. A key that did not survive the boundary would
    make exactly-once a property of one process's lifetime."""
    from isaac_api import workspace as ws

    _capture(client, record, client_request_key="durable")
    reloaded = ws.load_experiment(record)
    assert [n.client_request_key for n in reloaded.notes] == ["durable"]
    assert notes_module.find_by_client_request_key(reloaded.notes, "durable") is not None


# ==========================================================================
# 2. the capacity ceilings — MCP-001a
# ==========================================================================

def test_the_per_record_note_ceiling_refuses_and_destroys_nothing(
    client, record, monkeypatch
):
    """**MCP-001a.** Before this slice there was NO per-record note bound of any kind —
    no count ceiling, no document ceiling, no `too_many_notes` anywhere in the
    application. Only ONE note's text was bounded.

    The ceiling is lowered for the test. The property under test is "refuses, names the
    ceiling, destroys nothing", which does not depend on the number; the real constant
    is asserted separately below so a lowered ceiling cannot hide a missing one.
    """
    monkeypatch.setattr(routes, "_MAX_NOTES_PER_RECORD", 3)
    stored = [
        _capture(client, record, text=f"Synthetic {i}", client_request_key=f"c{i}")
        .json()["note"]["id"]
        for i in range(3)
    ]
    refused = _capture(client, record, text="one too many", client_request_key="c3")
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "too_many_notes"
    assert (body["max_per_record"], body["total"]) == (3, 3)

    # NOTHING WAS EVICTED, and the order is unchanged. A bound that dropped the oldest
    # note to make room would destroy a verbatim capture, which is `notes.py`'s first
    # invariant and the one thing the feature exists not to do.
    listed = client.get(f"/api/experiments/{record}/notes").json()
    assert [n["id"] for n in listed["notes"]] == stored
    assert listed["total"] == 3


def test_a_retry_is_still_answerable_at_the_ceiling(client, record, monkeypatch):
    """THE ORDERING DECISION, ASSERTED. Deduplication runs BEFORE the capacity check.

    A retry of a note the record already holds adds nothing, so refusing it for want
    of capacity would make a record at its ceiling unable to answer a question it had
    already answered — and would leave a client that legitimately captured something
    permanently unable to confirm it did.
    """
    monkeypatch.setattr(routes, "_MAX_NOTES_PER_RECORD", 1)
    first = _capture(client, record, client_request_key="only")
    assert first.status_code == 201
    # At the ceiling: a NEW note is refused...
    assert _capture(client, record, client_request_key="another").status_code == 422
    # ...and the RETRY is still answered.
    retry = _capture(client, record, client_request_key="only")
    assert retry.status_code == 200, retry.text
    assert retry.json()["deduplicated"] is True
    assert retry.json()["note"]["id"] == first.json()["note"]["id"]


def test_the_document_ceiling_is_a_second_bound_with_its_own_error(
    client, record, monkeypatch
):
    """TWO BOUNDS, DIFFERENT ERRORS, WHICHEVER BINDS FIRST.

    A record whose notes are long meets the document ceiling BEFORE the count, and
    never sees `too_many_notes`. They carry different `error` values for exactly that
    reason, which is the same shape the proposal pair uses.
    """
    monkeypatch.setattr(routes, "_MAX_NOTE_STATE_BYTES", 4096)
    monkeypatch.setattr(routes, "_MAX_NOTES_PER_RECORD", 1000)
    errors = []
    for i in range(40):
        response = _capture(
            client, record, text="S" * 512 + f" {i}", client_request_key=f"big{i}"
        )
        if response.status_code != 201:
            errors.append(response.json())
            break
    assert errors, "the document ceiling never bound"
    body = errors[0]
    # THE COUNT CEILING WAS NOWHERE NEAR, so this is the document bound and not the
    # other one wearing a different name.
    assert body["error"] == "notes_too_large", body
    assert body["max_bytes"] == 4096
    assert body["stored_bytes"] >= 4096, body
    assert body["total"] < 1000, body


def test_the_real_ceilings_are_the_shipped_ones():
    """THE NEGATIVE CONTROL for the three tests above, each of which lowers a
    constant and therefore cannot witness it."""
    assert routes._MAX_NOTES_PER_RECORD == 1000
    assert routes._MAX_NOTE_STATE_BYTES == routes._MAX_NOTE_BYTES * 16
    assert routes._MAX_NOTE_BYTES == 256 * 1024


def test_an_unbounded_flood_is_no_longer_possible_at_all(client, record, monkeypatch):
    """THE CLAIM MCP-001a ACTUALLY MAKES: the route STOPS. Not "slows", not "warns".

    With EXT-01 open — no trusted authentication boundary, Dean having reconfirmed the
    ClusterIP bypass — an untrusted in-cluster caller can reach this route. So the
    honest test is that a loop trying to grow the record without limit hits a wall and
    the record stays readable.
    """
    monkeypatch.setattr(routes, "_MAX_NOTES_PER_RECORD", 5)
    accepted = 0
    for i in range(50):
        if _capture(client, record, client_request_key=f"flood{i}").status_code == 201:
            accepted += 1
    assert accepted == 5, accepted
    # AND THE RECORD IS STILL READABLE, which is what the bound is protecting.
    listed = client.get(f"/api/experiments/{record}/notes")
    assert listed.status_code == 200
    assert listed.json()["total"] == 5


# ==========================================================================
# 3. the agent channel — CAP-006, route side
# ==========================================================================

def test_the_route_accepts_the_agent_channel_and_reports_it_in_the_sources_list(
    client, record
):
    assert "connected_agent" in notes_module.NOTE_SOURCES
    listed = client.get(f"/api/experiments/{record}/notes").json()
    assert "connected_agent" in listed["sources"], listed["sources"]
    note = _capture(client, record, source="connected_agent").json()["note"]
    assert note["source"] == "connected_agent"
    # AND IT IS STILL NOT A VALUE. The channel says where prose came from; the four
    # constants say what it is worth, and they are unchanged by it.
    assert (note["verified"], note["is_evidence"], note["is_field_value"]) == (
        False,
        False,
        False,
    )
    assert note["status"] == notes_module.NOTE_STATUS


def test_the_route_still_refuses_an_invented_source(client, record):
    """The vocabulary is CLOSED. Adding a member did not open it, which is the thing
    a reader would most plausibly assume had happened."""
    response = _capture(client, record, source="my_special_agent")
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_note_source"
    assert sorted(response.json()["allowed"]) == sorted(notes_module.NOTE_SOURCES)


def test_the_channel_is_a_claim_the_caller_makes_here_and_the_route_says_so(client):
    """**THE HONESTY POINT, PINNED.** `source` is caller-asserted on this route, for
    every member — nothing stops a program sending `typed_note`.

    That has always been true and was never stated, and it matters more now that one
    member names a CHANNEL rather than a format: a reader who took
    `source: connected_agent` as proof would be trusting a value the caller chose. The
    route's own description has to say so, because it is the published contract; the
    MCP tool is where the claim is trustworthy, and it accepts no `source` at all.
    """
    schema = client.get("/api/openapi").json()
    description = schema["paths"]["/api/experiments/{experiment_id}/notes"]["post"][
        "description"
    ]
    assert "ASSERTED BY THE CALLER" in description, description[:400]
    assert "not proof" in description.lower(), description[:400]
    # And it names where the claim IS trustworthy, so the disclosure is useful rather
    # than merely discouraging.
    assert "stamps it server-side" in description, description[:400]
