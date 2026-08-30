"""Can a caller make this application believe it is somebody? Measured, over HTTP.

WHAT THIS FILE IS
=================
An attack pass on the identity seam, driven through the **product's own HTTP
surface** rather than against ``isaac_api.identity``'s functions. That distinction
is the reason it exists beside ``test_identity_trust.py`` rather than inside it:
that file proves the RESOLVER cannot be fooled, one function at a time, with
hand-built ``Request`` objects. It does not walk a write route. A resolver that
refuses every header is worth nothing if some route reads a body key instead, and
nothing in this repository was asserting that.

Four vectors, each tried against every write operation a client can drive:

1. **All seven forwarded identity headers, forged.** Dean reconfirmed on 2026-08-12
   that the Service is a plain ClusterIP with no NetworkPolicy, so any in-cluster pod
   can send these. ``docs/identity-trust-contract.md`` §2, Q4.
2. **An actor named in the request BODY** — nine spellings, including the schema's
   own server-owned ``attribution.uploaded_by``.
3. **An actor named in the QUERY STRING.**
4. **An actor named as an MCP TOOL ARGUMENT.**

EVERY ONE OF THEM CORRECTLY FAILED. That is the result, and an asserted absence is a
result: these tests are negative controls, and the file's value is that the absence
is now checked rather than believed. The measurements are recorded per test so a
future reader can see what was tried rather than inferring it from what passed.

THE SHARPEST SINGLE MEASUREMENT
===============================
``POST /api/experiments/{id}/submit`` answers **409 ``human_actor_required``** with
all seven headers forged and every body spelling of an actor supplied at once. A
caller who controls every input the wire can carry still cannot become a person.

WHAT IS DELIBERATELY NOT RE-TESTED HERE, BECAUSE IT IS ALREADY PINNED ELSEWHERE
==============================================================================
* The resolver's own refusal of planted headers — ``test_identity_trust.py``
  (``test_five_planted_edge_headers_establish_no_identity`` and the 19 beside it).
* ``FORBIDDEN_TOOL_TOKENS`` firing at IMPORT, and ``accept``/``approve`` both being
  in it — ``test_mcp_boundaries.py``
  (``test_registering_a_submit_tool_raises_rather_than_being_ignored``,
  ``test_the_approval_verbs_include_their_synonym_because_one_of_them_was_missing``,
  ``test_no_mcp_scope_can_reach_an_accepting_finalising_or_exporting_operation``).
  Re-asserting them would be a second copy free to drift from the first.
* A service principal failing ``require_human_actor`` —
  ``test_mcp_oauth_binding.py::test_a_service_principal_is_refused_by_require_human_actor_with_its_own_reason``
  and ``test_identity_trust.py::test_a_service_principal_is_refused_as_an_author_with_its_own_reason``.

Everything is synthetic. No database, no network, no credential; the only files
touched are inside the test's own ``tmp_path`` workspace.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import identity

from conftest import client_ws, tutorial_client

#: A name this application can never invent. `assert PLANTED not in <anything>` is
#: therefore a real statement rather than a coincidence.
PLANTED = "mallory-the-forger-4711"

#: All seven headers the identity contract names — the five the edge injects, plus
#: the two permanently disqualified from proving anything (§6A.2). A forging pod
#: sends whichever it likes, so the attack sends all of them.
FORGED_HEADERS = {
    name: PLANTED
    for name in tuple(identity.EDGE_INJECTED_HEADERS)
    + tuple(identity.PERMANENTLY_UNTRUSTED_HEADERS)
}

#: Nine ways a request body could try to name who is acting. ``uploaded_by`` and
#: ``attribution.uploaded_by`` are the schema's own server-owned field, spelled both
#: as the API might flatten it and as the record nests it.
BODY_ACTOR_KEYS = {
    "actor": PLANTED,
    "attribution": {"uploaded_by": PLANTED},
    "author": PLANTED,
    "confirmed_by": PLANTED,
    "reviewed_by": PLANTED,
    "submitted_by": PLANTED,
    "uploaded_by": PLANTED,
    "user": PLANTED,
    "username": PLANTED,
}

#: The same claim in the query string.
QUERY_ACTOR = f"actor={PLANTED}&uploaded_by={PLANTED}&username={PLANTED}&user={PLANTED}"

#: Argument names that could ONLY be a claim about who the caller is. Deliberately
#: narrower than "anything person-shaped": ``contributors``, ``author`` and
#: ``generated_by`` name RECORD CONTENT — a scientific fact about the measurement —
#: and reserving those would forbid a legitimate future capability rather than an
#: illegitimate one. These nine cannot mean anything but the caller.
CALLER_NAMING_ARGUMENTS = frozenset(
    {
        "actor",
        "as_user",
        "identity",
        "impersonate",
        "on_behalf_of",
        "submitted_by",
        "uploaded_by",
        "user",
        "username",
    }
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def example(tmp_path, monkeypatch):
    """A client inside a worked-example session — the only scope with a READY,
    exportable record, which the export test needs."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# =============================================================================
# helpers
# =============================================================================


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _write_table(client, headers=None) -> list[tuple[str, str, dict]]:
    """A fresh record + run, and every write operation a client can drive on them.

    Built per call so the control run and the attack run act on DIFFERENT records
    in the same workspace: the statuses are then comparable without either run
    seeing the other's side effects, which is what makes a status-by-status
    comparison a fair test rather than an ordering artefact.
    """
    extra = dict(headers or {})
    created = client.post("/api/experiments", json={"title": "attack"}, headers=extra)
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    run = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "run A"},
        headers={"If-Match": _etag(client, eid), **extra},
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["run"]["id"]
    return eid, run_id, [
        ("POST", "/api/experiments", {"title": "second"}),
        ("PATCH", f"/api/experiments/{eid}", {"title": "renamed"}),
        (
            "POST",
            f"/api/experiments/{eid}/answers",
            {"confirmed_by_user": True, "answers": {"system.technique": "XAS"}},
        ),
        (
            "POST",
            f"/api/experiments/{eid}/edit",
            {"confirmed_by_user": True, "field": "system.technique", "value": "XES"},
        ),
        ("POST", f"/api/experiments/{eid}/runs", {"label": "run B"}),
        (
            "PATCH",
            f"/api/experiments/{eid}/runs/{run_id}",
            {"confirmed_by_user": True, "label": "run A2"},
        ),
        (
            "POST",
            f"/api/experiments/{eid}/runs/{run_id}/overrides",
            {
                "confirmed_by_user": True,
                "address": "field:system.technique",
                "value": "XAS",
            },
        ),
        ("POST", f"/api/experiments/{eid}/notes", {"text": "n", "source": "typed_note"}),
        (
            "POST",
            f"/api/experiments/{eid}/assets",
            {
                "confirmed_by_user": True,
                "asset_id": "a1",
                "content_role": "raw_data",
                "uri": "ssrl-archive://BL15-2/x/raw/",
                "sha256": "a" * 64,
            },
        ),
        ("POST", f"/api/experiments/{eid}/validate", {}),
        ("POST", f"/api/experiments/{eid}/export", {"confirmed_by_user": True}),
        ("POST", f"/api/experiments/{eid}/submit", {"confirmed_by_user": True}),
    ]


def _drive(client, table, eid, run_id, *, headers=None, body_extra=None, query=""):
    """Run the table and return one ``(method, shape, status)`` row per operation.

    ``shape`` is the path with this run's server-minted ULIDs replaced by tokens.
    The ids differ between two runs by construction — that is the whole point of
    giving each run its own record — so comparing raw paths would compare the ids
    rather than the outcomes.
    """
    rows = []
    for method, path, body in table:
        payload = dict(body)
        if body_extra:
            payload.update(body_extra)
        sent = dict(headers or {})
        sent["If-Match"] = _etag(client, eid)
        url = path + (("?" + query) if query else "")
        response = client.request(method, url, json=payload, headers=sent)
        shape = path.replace(eid, "{experiment_id}").replace(run_id, "{run_id}")
        rows.append((method, shape, response.status_code))
    return rows


def _workspace_contains(root) -> str:
    """Every byte under the workspace, as one string, for a leak assertion."""
    chunks = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


# =============================================================================
# 1. forged headers
# =============================================================================


def test_forging_all_seven_identity_headers_changes_no_write_outcome(client):
    """The bypass Dean reconfirmed, driven at the product rather than the resolver.

    Two runs of the same twelve-operation table over two freshly created records
    in one workspace — one plain, one with all seven headers forged — and the
    status sequences must be identical. A route that read a header would show up
    here as a single differing cell.

    Measured on ``c2a93a7``: identical, including the ``409`` on ``submit``.

    MUTATION: replacing ``identity.resolve_identity_for_request`` with a
    header-trusting version — one that builds a ``HumanActor`` from
    ``x-authentik-username`` when it is present, which is precisely the defect Q4
    says an in-cluster caller could exploit — turns this RED::

        At index 10 diff: ('POST', '/api/experiments/{experiment_id}/export', 200)
                       != ('POST', '/api/experiments/{experiment_id}/export', 500)

    **The FIRST divergence is not on ``submit``, and that is worth recording:** a
    forged identity changes ``export`` before it changes ``submit``, so a test
    that had only checked the submit cell would have watched an identity arrive
    and reported nothing. Choosing the whole sequence over the interesting cell is
    what caught it.

    *An earlier candidate mutation — arming the deterministic FIXTURE verifier —
    was run and does NOT turn this red, because that verifier attributes
    identically with and without the headers, so both sequences move together. It
    is kept as the mutation for
    :func:`test_the_attribution_seam_stays_unarmed_however_the_request_arrives`
    instead. An ineffective mutation is worth naming: it is how a reader can tell
    which property each test actually holds.*
    """
    eid_a, run_a, table_a = _write_table(client)
    plain = _drive(client, table_a, eid_a, run_a)

    eid_b, run_b, table_b = _write_table(client, headers=FORGED_HEADERS)
    forged = _drive(client, table_b, eid_b, run_b, headers=FORGED_HEADERS)

    assert [row[:2] for row in plain] == [row[:2] for row in forged]
    assert plain == forged, (plain, forged)
    # And the sweep must actually have swept: an empty table would pass trivially.
    assert len(plain) == 12, plain


def test_a_forged_header_is_never_echoed_and_never_persisted(client, tmp_path):
    """Not merely unused — absent. The planted name reaches no response body and
    no byte of the workspace.

    ``repr``-level absence matters because a value that is stored but unread today
    is a value some future surface will read.

    MUTATION: giving ``create_experiment_route`` a ``request`` and appending
    ``request.headers.get('x-authentik-username')`` to the title turns this RED at
    the response assertion, before the workspace scan is even reached::

        AssertionError: ('POST', '/api/experiments')
        assert 'mallory-the-forger-4711' not in
               '…"title":"secondmallory-the-forger-4711","scenario":null,…'
    """
    eid, _, table = _write_table(client, headers=FORGED_HEADERS)
    for method, path, body in table:
        response = client.request(
            method,
            path,
            json=body,
            headers={**FORGED_HEADERS, "If-Match": _etag(client, eid)},
        )
        assert PLANTED not in response.text, (method, path)

    assert PLANTED not in _workspace_contains(tmp_path / "ws")
    for experiment in ws.list_experiments():
        assert PLANTED not in json.dumps(experiment.to_state()), experiment.id


def test_submit_still_refuses_a_caller_who_forged_every_input_it_could(client):
    """THE SHARPEST ONE. Every header forged AND every body spelling of an actor
    supplied, on the one operation that requires a person.

    ``409 human_actor_required`` with ``trust: untrusted`` is the honest answer in
    a build with no trusted authentication boundary, and it is the answer a caller
    who controls the whole wire still gets.

    MUTATION: the same header-trusting ``resolve_identity_for_request`` turns
    this RED::

        AssertionError: Internal Server Error
        assert 500 == 409

    The ``500`` rather than a ``200`` is itself informative: a forged identity does
    not merely get in, it reaches a submission path that has no durable store
    configured. The assertion that matters is that ``409`` stopped being the
    answer.
    """
    eid, _, _ = _write_table(client, headers=FORGED_HEADERS)
    response = client.post(
        f"/api/experiments/{eid}/submit",
        json={"confirmed_by_user": True, **BODY_ACTOR_KEYS},
        headers={**FORGED_HEADERS, "If-Match": _etag(client, eid)},
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == identity.HUMAN_ACTOR_REQUIRED_ERROR, body
    assert body["trust"] == "untrusted", body
    assert PLANTED not in response.text


def test_the_attribution_seam_stays_unarmed_however_the_request_arrives(client):
    """The seam's own report, after the whole attack table has been driven at it.

    ``can_attribute: false`` with ``trust_basis: null`` is what
    ``record_attribution`` reads before it stamps anything, so this is the
    single value that decides whether a forged name could ever become
    ``attribution.uploaded_by``.

    MUTATION: making ``identity._raw_verifier_selection`` return
    ``FIXTURE_VERIFIER`` unconditionally turns this RED::

        AssertionError: {'verifier_id': 'test_fixture', 'can_attribute': False,
                         'trust_basis': None}
        assert 'test_fixture' == 'unconfigured'

    **Note which cell moved.** ``can_attribute`` stayed ``False`` — the fixture
    verifier only attributes when its own subject variable is set — so a test that
    had checked only ``can_attribute`` would have passed while the seam was armed
    with a different verifier. All three keys are asserted for that reason.
    """
    eid, run_id, table = _write_table(client, headers=FORGED_HEADERS)
    _drive(client, table, eid, run_id, headers=FORGED_HEADERS, body_extra=BODY_ACTOR_KEYS)

    status = identity.actor_attribution_status()
    assert status["can_attribute"] is False, status
    assert status["trust_basis"] is None, status
    assert status["verifier_id"] == "unconfigured", status


# =============================================================================
# 2. an actor named in the body
# =============================================================================


def test_no_write_route_lets_the_body_name_an_actor(client):
    """Nine spellings, twelve operations: each is REFUSED or IGNORED, never obeyed.

    **The two outcomes are both acceptable and they are not the same, so the
    measurement is recorded rather than averaged.** On ``c2a93a7``:

    * REFUSED with ``422`` — ``POST /api/experiments`` and
      ``PATCH /api/experiments/{id}`` (their models set ``extra="forbid"``),
      ``POST .../notes`` and ``POST .../assets`` (``unrecognized_field``).
    * ACCEPTED AND IGNORED — the rest, whose bodies are untyped ``dict``s that read
      only the keys they name. ``POST .../runs`` returns ``201`` with all nine keys
      present.

    What must hold either way is that nothing is obeyed, which the workspace scan
    below is the actual assertion for.

    MUTATION: two edits, because one alone is not enough and that is the point —
    relaxing ``CreateExperimentRequest`` to ``extra="allow"`` (so the key is no
    longer refused) AND folding ``getattr(body, "actor", "")`` into the stored
    ``description``. Together they turn this RED::

        AssertionError: 01M19N8FW2062XCXN8M4REH0Y3
        assert 'mallory-the-forger-4711' not in
               '…"description": "mallory-the-forger-4711", "files": []}…'

    ``extra="allow"`` ALONE leaves this green: the key is accepted and still not
    stored, which is the "accepted and ignored" outcome this test permits. It is
    the storing that is forbidden, and only the second edit does that.
    """
    eid, run_id, table = _write_table(client)
    outcomes = _drive(client, table, eid, run_id, body_extra=BODY_ACTOR_KEYS)

    assert len(outcomes) == 12, outcomes
    # Nothing 500s, and nothing succeeded by obeying the actor.
    for method, tail, status in outcomes:
        assert status < 500, (method, tail, status)

    for experiment in ws.list_experiments():
        assert PLANTED not in json.dumps(experiment.to_state()), experiment.id


def test_the_refusing_routes_and_the_ignoring_routes_are_both_still_there(client):
    """The negative control for the test above, and the reason it is not vacuous.

    "Refused or ignored" is satisfied by an application that refuses everything, so
    the claim is made per operation and against a control rather than over the set
    of statuses — a ``422`` appears in the control run anyway (``/edit`` refuses the
    control body's shape), which is exactly how a set-level assertion would have
    read as coverage while proving nothing.

    Two named exemplars, each measured both ways on ``c2a93a7``:

    * ``POST /api/experiments`` — ``201`` without the actor keys, ``422``
      ``extra_forbidden`` with them. A REFUSER.
    * ``POST .../runs`` — ``201`` both ways, with all nine keys present in the
      body of the second. An IGNORER.

    MUTATION: relaxing ``CreateExperimentRequest`` to ``extra="allow"`` turns this
    RED::

        AssertionError: POST /api/experiments stopped refusing a body-named actor
        assert 201 == 422
    """
    plain = client.post("/api/experiments", json={"title": "control"})
    assert plain.status_code == 201, plain.text
    attacked = client.post(
        "/api/experiments", json={"title": "attacked", **BODY_ACTOR_KEYS}
    )
    assert attacked.status_code == 422, (
        "POST /api/experiments stopped refusing a body-named actor"
    )

    eid = plain.json()["id"]
    ignored = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "run X", **BODY_ACTOR_KEYS},
        headers={"If-Match": _etag(client, eid)},
    )
    assert ignored.status_code == 201, (
        "POST .../runs stopped accepting-and-ignoring a body-named actor: "
        f"{ignored.status_code} {ignored.text[:200]}"
    )
    assert PLANTED not in ignored.text
    assert PLANTED not in json.dumps(ws.load_experiment(eid).to_state())


def test_an_exported_record_carries_no_uploaded_by_however_the_request_asked(example):
    """The one place a forged actor would actually matter: the official artifact.

    An export is driven on a READY record with all seven headers forged and the
    server-owned field named in the body twice — flat and nested. The artifact on
    disk must carry no ``attribution.uploaded_by`` at all, and no trace of the
    planted name.

    The schema itself says this field is *"Set by the server; any client value is
    overwritten"*, and ``record_attribution`` omits it rather than writing an empty
    string, because ``""`` would assert an identity of "".

    MUTATION: making ``record_attribution.resolve_uploaded_by`` return a constant
    instead of consulting the identity turns this RED::

        AssertionError: {'contributors': [{'name': 'Ada Lovelace', …}],
                         'uploaded_by': 'someone-the-server-invented'}
        assert 'uploaded_by' not in {…}
    """
    ready = ws.SEED_READY_ID
    response = example.post(
        f"/api/experiments/{ready}/export",
        json={
            "confirmed_by_user": True,
            "uploaded_by": PLANTED,
            "attribution": {"uploaded_by": PLANTED},
        },
        headers={**FORGED_HEADERS, "If-Match": _etag(example, ready)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True, response.text

    experiment = client_ws(example).load_experiment(ready)
    assert experiment.record_id is not None
    raw = experiment.record_path().read_text(encoding="utf-8")
    document = json.loads(raw)
    assert "uploaded_by" not in (document.get("attribution") or {}), document.get(
        "attribution"
    )
    assert PLANTED not in raw
    # The block is not empty — the record does carry real, evidenced contributors —
    # so this is not passing because attribution is absent altogether.
    assert document["attribution"]["contributors"], document["attribution"]


# =============================================================================
# 3. an actor named in the query string
# =============================================================================


def test_no_write_route_lets_a_query_parameter_name_an_actor(client):
    """The same claim moved out of the body, where a route reading ``request.
    query_params`` would pick it up.

    Measured on ``c2a93a7``: every operation answered exactly what it answers
    without the parameters — FastAPI does not bind undeclared query parameters, so
    they reach no handler — and nothing was persisted.

    MUTATION: adding ``actor: str | None = Query(None)`` to
    ``create_experiment_route`` AND appending it to the title turns this RED::

        AssertionError: 01M19N7RW1Q5FE0C56PCS6JBSW
        assert 'mallory-the-forger-4711' not in
               '…"title": "secondmallory-the-forger-4711", "created_utc": …'

    Binding the parameter without storing it leaves this green, which is correct:
    a parameter nobody reads is not an actor claim being obeyed.
    """
    eid_a, run_a, table_a = _write_table(client)
    plain = _drive(client, table_a, eid_a, run_a)

    eid_b, run_b, table_b = _write_table(client)
    with_query = _drive(client, table_b, eid_b, run_b, query=QUERY_ACTOR)

    assert [row[:2] for row in plain] == [row[:2] for row in with_query]
    assert plain == with_query, (plain, with_query)
    for experiment in ws.list_experiments():
        assert PLANTED not in json.dumps(experiment.to_state()), experiment.id


# =============================================================================
# 4. an actor named as an MCP tool argument
# =============================================================================


def test_no_registered_tool_declares_an_argument_that_could_name_the_caller():
    """Nine names that can only be a claim about who is calling, checked against
    every registered tool's schema.

    **STATED PRECISELY, BECAUSE THE OBVIOUS STRONGER CLAIM IS FALSE.**
    ``tools.RESERVED_ARGUMENT_NAMES`` refuses ``principal``, ``subject``, ``token``,
    ``scope`` and thirteen more at import — the MECHANISM words. It does **not**
    contain any of the nine below, so a tool declaring ``actor`` or ``username``
    would import cleanly. Measured 2026-08-30: the intersection of
    :data:`CALLER_NAMING_ARGUMENTS` with ``RESERVED_ARGUMENT_NAMES`` is EMPTY.

    That gap is not reachable today — no tool declares one, which is exactly what
    this test pins — and closing it belongs to a slice that can argue which names
    are caller-claims and which are record content. This guard covers the hole from
    the other side: the day such an argument is added, this goes red.

    The nine deliberately exclude ``author``, ``contributors`` and ``generated_by``:
    those name a scientific fact about the measurement, and forbidding them would
    refuse a legitimate future capability.

    MUTATION: adding ``"actor": {"type": "string"}`` to ``isaac_create_run``'s
    input schema turns this RED::

        AssertionError: isaac_create_run declares caller-naming argument(s) ['actor']
        assert not ['actor']
    """
    from isaac_api.mcp import tools as mcp_tools

    for name, tool in mcp_tools.TOOLS.items():
        declared = set(tool.input_schema.get("properties", {}))
        offending = sorted(declared & CALLER_NAMING_ARGUMENTS)
        assert not offending, f"{name} declares caller-naming argument(s) {offending}"
    # The sweep must have seen the real registry.
    assert len(mcp_tools.TOOLS) >= 10, sorted(mcp_tools.TOOLS)


def test_a_tool_call_supplying_an_actor_argument_is_refused_at_call_time(client):
    """And the live path: a caller sending one anyway is refused, not ignored.

    Every tool schema sets ``additionalProperties: false``, which the argument
    validator enforces, so an undeclared ``actor`` is an ``invalid params`` error
    rather than a silently dropped key. Driven over the mounted transport under the
    loopback binding, which is the only binding this test can serve without a
    token.

    MUTATION: making ``tools.validate_arguments`` DROP unknown arguments instead
    of refusing them — the plausible "accept and ignore" weakening — turns this
    RED::

        AssertionError: {'id': 1, 'jsonrpc': '2.0', 'result': {'content': [{'text':
        '{"data": {"experiments": []}, …'}], …}}
        assert 'error' in {…'result': …}

    *Deleting the check outright is NOT a usable mutation: the validator then
    raises ``KeyError: 'actor'`` two lines later and the call still errors, so the
    test stays green against a broken program. The realistic weakening is the one
    above.*
    """
    import os

    from isaac_api.mcp.deployment import DEPLOYMENT_ENV, LOCAL_LOOPBACK, LOCAL_SCOPES_ENV
    from isaac_api.mcp.policy import Scope
    from isaac_api.mcp.transport import MCP_PATH

    previous = {
        key: os.environ.get(key)
        for key in (DEPLOYMENT_ENV, LOCAL_SCOPES_ENV)
    }
    os.environ[DEPLOYMENT_ENV] = LOCAL_LOOPBACK
    os.environ[LOCAL_SCOPES_ENV] = f"{Scope.READ.value},{Scope.DRAFT_WRITE.value}"
    try:
        from isaac_api.app import create_app

        mcp = TestClient(create_app(), client=("127.0.0.1", 51999))
        response = mcp.post(
            MCP_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "isaac_list_experiments",
                    "arguments": {"actor": PLANTED, "username": PLANTED},
                },
            },
        )
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" in body, body
    assert PLANTED not in response.text


# =============================================================================
# 5. cross-user and cross-record access — an ABSENCE, stated plainly
# =============================================================================


def test_there_is_no_per_record_or_per_user_scoping_and_this_says_so(client):
    """**NO SUCH SCOPING EXISTS, AND WRITING A TEST THAT PASSED VACUOUSLY WOULD BE
    WORSE THAN WRITING NONE.**

    The attack asked for was: a principal scoped to one experiment must not reach
    another. Measured on ``c2a93a7``, that principal does not exist.

    * ``mcp.deployment.Principal`` carries ``subject``, ``binding``, ``scopes`` and
      ``tutorial_session_id`` — **no record, no owner, no ACL field**. Asserted
      below over its annotations rather than described.
    * ``Experiment`` carries no owner or principal either, so there is nothing for a
      request to be compared against.
    * Over HTTP there is no principal at all in a default deployment: every caller
      reaches every record in the workspace, which the two-record read below
      measures rather than assumes.

    **The ONE scoping that does exist is the worked-example session**, and it is
    real: a session-bound caller cannot see an ordinary record and vice versa. It is
    pinned by ``test_mcp_boundaries.py::test_a_session_bound_server_cannot_see_an_ordinary_workspace_record``
    / ``test_an_ordinary_server_cannot_see_a_sessions_example_records`` and by
    ``test_tutorial_scope.py``, and is deliberately not re-asserted here.

    So the honest report is: cross-record isolation is not implemented, is not
    claimed anywhere, and the correct remedy is a product decision about ownership —
    not a test.

    MUTATION: adding an ``owner`` field to ``Principal`` turns this RED, which is
    the point — the day per-caller scoping is introduced, this test must be
    rewritten rather than kept::

        AssertionError: ['binding', 'owner', 'scopes', 'subject', 'tutorial_session_id']
        Extra items in the left set: 'owner'
    """
    from isaac_api.mcp.deployment import Principal

    assert set(Principal.__annotations__) == {
        "subject",
        "binding",
        "scopes",
        "tutorial_session_id",
    }, sorted(Principal.__annotations__)

    from isaac_api.workspace import Experiment

    owner_ish = {
        name
        for name in dir(Experiment)
        if name in ("owner", "owner_id", "principal", "acl", "visible_to")
    }
    assert not owner_ish, owner_ish

    # And the measurement over the wire: one caller, two records, both readable.
    first = client.post("/api/experiments", json={"title": "one"}).json()["id"]
    second = client.post("/api/experiments", json={"title": "two"}).json()["id"]
    assert client.get(f"/api/experiments/{first}").status_code == 200
    assert client.get(f"/api/experiments/{second}").status_code == 200
    listed = {row["id"] for row in client.get("/api/experiments").json()["experiments"]}
    assert {first, second} <= listed, listed
