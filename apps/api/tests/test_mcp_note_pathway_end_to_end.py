"""**MCP-019** — the whole application-side loop, driven, with no external anything.

WHAT THIS FILE IS FOR
=====================
It is the proof that **ISAAC does not need an external decision to finish the
application side of the agent pathway.** Production MCP mounting, a trusted identity
boundary and real-data AI governance are all external and all deferred (Dean's D1–D9,
2026-08-12); none of them gates the contract, and this file is what says so with
measurements rather than with confidence.

The loop, end to end:

    synthetic MCP client -> capture a note -> propose a value citing that note
    -> change-feed event -> the website's own read surface
    -> a person accepts under an explicitly-enabled TEST identity
    -> deterministic validation

EVERY ASSERTION HERE IS BEHAVIOURAL, AND THE FILE SAYS SO BECAUSE THE ALTERNATIVE HAS
SHIPPED HERE BEFORE
====================================================================================
``CLAUDE.md`` §11 records a slice whose central claim was pinned by **string presence
rather than behaviour**: it passed 25 tests, and so did a **fabricating seam** that
returned ``{ok: true, record: {status: "complete"}}``. So nothing below asserts that a
sentence exists. Every case drives the real ``McpServer`` over real JSON-RPC into the
real FastAPI application, and asserts returned key sets, stored state, and HTTP status
codes. Where a claim can only be structural it is labelled ``STRUCTURAL`` in its own
name, so the distinction is visible in CI output rather than buried here — the remedy
this repository settled on for ``INVARIANT GUARD`` titles.

THE TWO IDENTITY LEGS ARE BOTH DRIVEN, WHICH IS THE POINT RATHER THAN A DETAIL
=============================================================================
``accept`` answers **409 ``human_actor_required``** in every default-configured
deployment, because no trusted authentication boundary exists in this build. That is a
**CONFIGURATION fact, not a build defect**, and no application change can close it. So
this file drives BOTH legs: the default refusal, and the success leg reached only
through the fixture verifier (``ISAAC_EDGE_TRUST_VERIFIER=test_fixture`` +
``ISAAC_FIXTURE_ACTOR_SUBJECT``), which ``test_deploy_config.py`` pins to no shipped
deploy artifact. **Nothing here weakens the 409 and nothing here adds a bypass.**

WHAT IS DELIBERATELY NOT PROVEN HERE, so the file is not read as broader than it is
====================================================================================
* **No hosted anything.** ``/krish`` sits behind an Authentik edge this environment
  cannot authenticate to. This proves the CONTRACT is green locally; it proves nothing
  about a deployment, and the operator's mounting step remains the operator's.
* **No browser.** The website's own end-to-end walk is Playwright's
  ``playwright.trusted.config.ts``. This file drives the HTTP surface that walk uses.
* **No model, and none required.** Every provider in this build answers
  ``501 no_provider_configured``. The loop is green anyway, which is asserted rather
  than assumed.

DATA BOUNDARY: **none.** Every value is synthetic and unmistakably so, in a
``tmp_path`` workspace. No database connection is opened, no migration is applied, no
external host is contacted, no credential is read, and nothing production-derived is
touched.

AUTHORIZATION BASIS: ``CLAUDE.md`` §15 — *"AI / MCP / voice IMPLEMENTATION against
deterministic fake providers — authorized by the project owner 2026-08-12"* (code,
APIs, tests, security boundaries), plus the 2026-08-29 application-side extension's
*"the remote MCP and bounded change-feed application architecture"* and *"the
associated tests"*.
"""

from __future__ import annotations

import asyncio
import copy

import pytest
from fastapi.testclient import TestClient

from isaac_api import identity, notes as notes_module, workspace as ws
from isaac_api.mcp import links
from isaac_api.mcp.deployment import LocalLoopbackDeployment
from isaac_api.mcp.policy import MCP_READ_WINDOW, OPERATIONS, PERMITTED_TOOL_NAMES, Scope
from isaac_api.mcp.server import McpServer
from isaac_api.mcp.tools import TOOLS

#: The person the fixture verifier attributes an acceptance to. Unmistakably synthetic.
ACTOR = "synthetic-test-scientist"

#: What the "scientist" said to their agent. Prose, not a value — the whole reason a
#: note is the safe entry point.
SPOKEN = (
    "We re-ran the third scan because the shutter stuck, and the cell sat at 301 K "
    "throughout."
)

#: The one field path the proposal below targets. Run-scoped.
TARGET = "context.temperature_K"


# ==========================================================================
# fixtures
# ==========================================================================

@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """An empty ordinary-scope workspace, with every ambient trust setting cleared.

    `PGHOST` is deleted so no database is reached even if the developer's shell has
    one set — `CLAUDE.md` records `pytest` once opening 1,392 connections from an
    ambient `PGHOST`, so this is a measured hazard rather than a precaution.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    return ws


@pytest.fixture()
def armed(workspace, monkeypatch):
    """A deployment that CAN attribute an acceptance: the fixture verifier.

    No shipped deploy artifact sets these (`test_deploy_config.py` pins that), so this
    is deliberately a configuration no deployment has — and it is the ONLY legitimate
    way to reach acceptance's success leg. It does not weaken the 409; it selects a
    different verifier.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _app():
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def http(workspace) -> TestClient:
    """The WEBSITE's transport, default configuration — the refusal leg."""
    return TestClient(_app(), raise_server_exceptions=False)


@pytest.fixture()
def armed_http(armed) -> TestClient:
    """The WEBSITE's transport under the fixture verifier — the success leg."""
    return TestClient(_app(), raise_server_exceptions=False)


def _agent(app, *scopes: Scope) -> McpServer:
    """A synthetic MCP client: the real server, the real dispatch, no network.

    `tutorial_session_id=None` is ORDINARY SCOPE, deliberately. `identity.stamp_actor`
    returns `None` unconditionally and first inside a worked-example session, so an
    acceptance there is recorded UNATTRIBUTED even under the fixture verifier —
    attribution is one of the things this file proves, so it must not run in the one
    scope where it is switched off.
    """
    return McpServer(
        app,
        binding=LocalLoopbackDeployment(
            scopes=frozenset(scopes), tutorial_session_id=None
        ),
    )


def _rpc(server: McpServer, method: str, params: dict | None = None) -> dict:
    message: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        message["params"] = params
    return asyncio.run(server.handle(message))


def _tool(server: McpServer, name: str, **arguments) -> dict:
    """A `tools/call` that must SUCCEED. Returns the structured payload."""
    envelope = _rpc(server, "tools/call", {"name": name, "arguments": arguments})
    assert "error" not in envelope, envelope.get("error")
    result = envelope["result"]
    assert result["isError"] is False, result["structuredContent"]
    return result["structuredContent"]


def _tool_refused(server: McpServer, name: str, **arguments) -> dict:
    """A `tools/call` that must be REFUSED by the route. Returns the payload."""
    envelope = _rpc(server, "tools/call", {"name": name, "arguments": arguments})
    assert "error" not in envelope, envelope.get("error")
    result = envelope["result"]
    assert result["isError"] is True, result["structuredContent"]
    return result["structuredContent"]


def _record_with_a_run(client: TestClient) -> tuple[str, str, str]:
    """`(experiment_id, run_id, etag)` for a fresh synthetic record with one run."""
    created = client.post(
        "/api/experiments", json={"title": "MCP-019 synthetic end-to-end"}
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    etag = client.get(f"/api/experiments/{eid}").headers["ETag"]
    run = client.post(
        f"/api/experiments/{eid}/runs", json={"label": "Run A"}, headers={"If-Match": etag}
    )
    assert run.status_code in (200, 201), run.text
    rid = run.json()["run"]["id"]
    return eid, rid, client.get(f"/api/experiments/{eid}").headers["ETag"]


def _etag(client: TestClient, eid: str) -> str:
    return client.get(f"/api/experiments/{eid}").headers["ETag"]


# ==========================================================================
# 1. the loop
# ==========================================================================

def test_the_whole_loop_runs_with_no_provider_no_account_and_no_database(armed_http):
    """**THE HEADLINE.** Capture -> propose -> feed -> website -> accept -> validate.

    Driven in one test on purpose: the claim is that the STEPS CONNECT, and six
    independent tests each proving one step would not establish that the id one step
    returns is the id the next step consumes. Every step's outcome is asserted from
    the response it produced.
    """
    eid, rid, etag = _record_with_a_run(armed_http)
    agent = _agent(armed_http.app, Scope.READ, Scope.PROPOSALS_WRITE)

    # --- STEP 1: the agent puts the scientist's words into ISAAC ------------
    # THE GAP THIS CLOSES. Before MCP-001 there was no operation here at all, so
    # `isaac_propose_field_value`'s required `note_id` was unobtainable and not one
    # word of an agent conversation could enter ISAAC with every external gate open.
    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="mcp-019-capture-1",
    )
    assert captured["status"] == 201, captured
    note = captured["data"]["note"]
    assert captured["data"]["deduplicated"] is False, captured["data"]
    # THE WORDS ARE VERBATIM. Not trimmed, not summarised, not normalised.
    assert note["text"] == SPOKEN
    # AND IT IS NOT A VALUE. The four constants are on the WIRE, not merely on the
    # class, which is what makes the guarantee survive the boundary.
    assert note["status"] == notes_module.NOTE_STATUS
    assert (note["verified"], note["is_evidence"], note["is_field_value"]) == (
        False,
        False,
        False,
    )
    note_id = note["id"]

    # --- STEP 2: the agent proposes a value, citing those words -------------
    proposed = _tool(
        agent,
        "isaac_propose_field_value",
        experiment_id=eid,
        if_match=captured["etag"],
        note_id=note_id,
        target_field_path=TARGET,
        proposed_value=301.0,
        rule="The transcript said the cell sat at 301 K throughout.",
        run_id=rid,
        client_request_key="mcp-019-propose-1",
    )
    assert proposed["status"] == 200, proposed
    proposal = proposed["data"]["proposal"]
    assert proposed["data"]["deduplicated"] is False
    # THE LOOP IS CLOSED: the proposal cites the note the FIRST step created.
    assert proposal["note_id"] == note_id
    proposal_id = proposal["proposal_id"]

    # --- STEP 3: the change feed reports both, by their own kinds -----------
    feed = armed_http.get(f"/api/experiments/{eid}/changes").json()
    assert "note" in feed["kinds"], feed["kinds"]
    by_kind: dict[str, set[str]] = {}
    for change in feed["changes"]:
        by_kind.setdefault(change["kind"], set()).add(change["entity_id"])
    # THE PRECISE SIGNAL, which is what MCP-005 is for: a `note` entry naming THIS
    # note, not merely an `experiment` entry that moved because something did.
    assert note_id in by_kind.get("note", set()), by_kind
    assert proposal_id in by_kind.get("proposal", set()), by_kind
    # AND THE FEED CARRIES NO CONTENT. The scientist's words are not in it.
    assert SPOKEN not in str(feed)

    # --- STEP 4: the website's own read surface shows them ------------------
    seen_notes = armed_http.get(f"/api/experiments/{eid}/notes").json()
    assert [n["id"] for n in seen_notes["notes"]] == [note_id]
    assert seen_notes["notes"][0]["text"] == SPOKEN
    seen_proposals = armed_http.get(f"/api/experiments/{eid}/proposals").json()
    assert [p["proposal_id"] for p in seen_proposals["proposals"]] == [proposal_id]

    # --- STEP 5: a PERSON accepts, under the explicitly-enabled test identity
    review = armed_http.post(
        f"/api/experiments/{eid}/proposals/{proposal_id}/review",
        json={
            "action": "accept",
            "confirmed_by_user": True,
            # REQUIRED, and measured rather than assumed: the route refuses
            # `422 unknown_accepted_from` without it. `candidate` means "the
            # proposed value is right and is written as it stands"; `edited`
            # means the reviewer corrected it. Neither is a default, which is
            # the route refusing to guess which claim a person is making.
            "accepted_from": "candidate",
        },
        headers={"If-Match": _etag(armed_http, eid)},
    )
    assert review.status_code == 200, review.text
    assert review.json()["proposal"]["state"] == "accepted", review.json()

    # --- STEP 6: the value is now the record's, and validation is deterministic
    # THE SHAPE IS `run["fields"]`, MEASURED — a first version of this reached for
    # `run["resolved"]["fields"]` and got a `KeyError`. The run detail serves `fields`
    # (this run's own) beside `inherited` (the record-level values it resolves to by
    # reference), and an accepted RUN-scoped proposal writes the former.
    run_after = armed_http.get(f"/api/experiments/{eid}/runs/{rid}").json()["run"]
    assert TARGET in run_after["fields"], sorted(run_after["fields"])
    written = run_after["fields"][TARGET]
    assert written["value"] == 301.0, written
    # AND IT IS NOW EVIDENCED — the acceptance is what mints the evidence, which is
    # the whole reason a proposal is not itself a value. Asserted over the stored
    # envelope rather than over the proposal's state, because the proposal saying
    # "accepted" and the field actually carrying the value are different claims and
    # this repository has shipped the first without the second.
    assert written.get("evidence"), written
    # DETERMINISTIC: the same read twice is the same answer. Not a tautology — it is
    # the claim that acceptance produced STORED state rather than a computed view
    # that could differ on the next request.
    again = armed_http.get(f"/api/experiments/{eid}/runs/{rid}").json()["run"]
    assert again["fields"][TARGET]["value"] == 301.0
    # AND THE NOTE SURVIVED THE WHOLE THING, which is the losslessness guarantee.
    assert armed_http.get(f"/api/experiments/{eid}/notes/{note_id}").json()["note"][
        "text"
    ] == SPOKEN


# ==========================================================================
# 2. retries do not duplicate notes — the key EXERCISED, not merely present
# ==========================================================================

def test_a_retry_with_the_same_key_stores_nothing_and_returns_the_same_note(http):
    """**IDEMPOTENCY, EXERCISED.** Vendor retry behaviour is UNKNOWN (`REC-012`), so a
    non-idempotent create means duplicate scientific notes in a review queue.

    Three things are asserted, and the third is the one a weaker test would miss: the
    same id comes back, the record holds ONE note, and the flag SAYS which happened —
    a client that cannot distinguish "I stored it" from "it was already there" will
    tell the scientist it captured something twice.
    """
    eid, _rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)

    first = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="retry-me",
    )
    assert (first["status"], first["data"]["deduplicated"]) == (201, False)

    second = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=first["etag"],
        text=SPOKEN,
        client_request_key="retry-me",
    )
    # 200 NOT 201: nothing was created, and the status says so as well as the flag.
    assert (second["status"], second["data"]["deduplicated"]) == (200, True)
    assert second["data"]["note"]["id"] == first["data"]["note"]["id"]

    # THE RECORD HOLDS EXACTLY ONE, measured over the stored document rather than
    # inferred from the two responses.
    assert http.get(f"/api/experiments/{eid}/notes").json()["total"] == 1

    # AND A DIFFERENT KEY IS A DIFFERENT NOTE — the negative control, without which
    # this test would also pass on an implementation that refused every second write.
    third = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=second["etag"],
        text=SPOKEN,
        client_request_key="a-genuinely-new-thought",
    )
    assert (third["status"], third["data"]["deduplicated"]) == (201, False)
    assert third["data"]["note"]["id"] != first["data"]["note"]["id"]
    assert http.get(f"/api/experiments/{eid}/notes").json()["total"] == 2


def test_a_retry_carrying_the_pre_first_attempt_etag_is_refused_not_duplicated(http):
    """THE STALE-ETAG RETRY, which is the shape a real timeout produces.

    The precondition is checked BEFORE the deduplication branch, so a client retrying
    with the etag it held before its first attempt meets `412` — it does not get a
    second note, and it does not get a misleading success. The remedy is to re-read
    and retry with the SAME key, which the test above covers.
    """
    eid, _rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    body = dict(
        experiment_id=eid, text=SPOKEN, client_request_key="stale-retry"
    )
    first = _tool(agent, "isaac_capture_note", if_match=etag, **body)
    assert first["status"] == 201

    refused = _tool_refused(agent, "isaac_capture_note", if_match=etag, **body)
    assert refused["status"] == 412, refused
    assert http.get(f"/api/experiments/{eid}/notes").json()["total"] == 1


# ==========================================================================
# 3. large reads are bounded — MEASURED AT THE ROUTE
# ==========================================================================

def test_the_agents_reads_are_bounded_and_the_counts_are_still_the_servers(http):
    """**MCP-002, MEASURED.** The window bounds what is FETCHED, never what is CLAIMED.

    THE MEASUREMENT IS AT THE ROUTE. An in-process figure is not what a client
    receives and this programme has published that error, so the byte counts below
    come from `len(response.content)` on the website's own transport, and the WINDOW
    is asserted over what the MCP dispatch actually returned.
    """
    eid, _rid, _tag = _record_with_a_run(http)
    # Enough runs that the window binds. 60 keeps the test quick while still putting
    # `pending` well past one window; the >150,000-byte figure in `MCP_READ_WINDOW`'s
    # own comment was measured at 120.
    for i in range(60):
        http.post(
            f"/api/experiments/{eid}/runs",
            json={"label": f"Run {i}"},
            headers={"If-Match": _etag(http, eid)},
        )

    unbounded = len(http.get(f"/api/experiments/{eid}/pending").content)
    bounded = len(
        http.get(f"/api/experiments/{eid}/pending", params={"limit": MCP_READ_WINDOW}).content
    )
    assert bounded < unbounded, (bounded, unbounded)

    agent = _agent(http.app, Scope.READ)
    # THE AGENT ASKED FOR NO BOUND AND GOT ONE.
    got = _tool(agent, "isaac_list_questions", experiment_id=eid)["data"]
    assert len(got["pending"]) <= MCP_READ_WINDOW, len(got["pending"])
    page = got["pending_page"]
    assert page["limit"] == MCP_READ_WINDOW, page
    # AND THE COUNT IT MUST REPORT IS THE SERVER'S, over the WHOLE record — strictly
    # greater than what arrived, which is what makes this a real assertion rather
    # than one that would hold on a small record by accident.
    assert page["record_total"] > len(got["pending"]), page

    runs = _tool(agent, "isaac_list_runs", experiment_id=eid)["data"]
    assert len(runs["runs"]) <= MCP_READ_WINDOW
    assert runs["total"] > len(runs["runs"]), (runs["total"], len(runs["runs"]))

    # AN EXPLICIT LIMIT STILL WINS — the window bounds the caller that does not ask,
    # it does not cap the one that does.
    asked = _tool(agent, "isaac_list_runs", experiment_id=eid, limit=MCP_READ_WINDOW + 5)[
        "data"
    ]
    assert len(asked["runs"]) == MCP_READ_WINDOW + 5


# ==========================================================================
# 4. provenance identifies the CHANNEL, and never an actor
# ==========================================================================

def test_the_note_and_its_proposal_both_identify_the_agent_channel(http):
    """**CAP-006.** A reviewer can tell "my Claude" from "the CSV importer".

    Before this, a proposal's `source` was inherited from its note and every note an
    agent could create had to claim one of the five producer labels that describe
    something else — `typed_note` says a person typed it, which is a lie in the one
    field a reviewer uses to decide how much to trust what they are reading.
    """
    eid, rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="provenance-1",
    )
    note = captured["data"]["note"]
    assert note["source"] == "connected_agent", note["source"]

    proposed = _tool(
        agent,
        "isaac_propose_field_value",
        experiment_id=eid,
        if_match=captured["etag"],
        note_id=note["id"],
        target_field_path=TARGET,
        proposed_value=301.0,
        rule="The transcript said the cell sat at 301 K throughout.",
        run_id=rid,
        client_request_key="provenance-2",
    )
    # THE CHANNEL TRAVELS TO THE PROPOSAL, which is the half CAP-006 is actually about:
    # the reviewer is looking at the proposal, not at the note.
    assert proposed["data"]["proposal"]["source"] == "connected_agent"

    # AND IT IS A CHANNEL, NOT AN ACTOR. `trust_basis` stays `unattributed` and no
    # subject is recorded: this build establishes no identity for an agent call,
    # because the stamp requires a `trust_basis` no verifier here mints.
    proposal = proposed["data"]["proposal"]
    assert proposal["trust_basis"] == "unattributed", proposal["trust_basis"]
    assert proposal.get("subject") is None, proposal.get("subject")
    # The actor seam is unset on the note too — nothing on it names a person.
    assert ACTOR not in str(captured["data"])


def test_the_agent_cannot_choose_the_channel_it_is_recorded_under(http):
    """THE SERVER MAKES THE CLAIM ABOUT ITSELF, which is what makes it worth anything.

    The HTTP route accepts a caller-supplied `source` — it always has, for every
    member — so `connected_agent` there is an assertion rather than a fact. The MCP
    tool declares no such property, so a caller cannot supply one even by accident,
    and `validate_arguments` refuses the undeclared key rather than ignoring it.
    """
    schema = TOOLS["isaac_capture_note"].input_schema
    assert "source" not in schema["properties"], sorted(schema["properties"])
    assert schema["additionalProperties"] is False

    eid, _rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    envelope = _rpc(
        agent,
        "tools/call",
        {
            "name": "isaac_capture_note",
            "arguments": {
                "experiment_id": eid,
                "if_match": etag,
                "text": SPOKEN,
                "client_request_key": "k",
                "source": "typed_note",
            },
        },
    )
    # REFUSED AS A JSON-RPC ERROR, before a request is built — not accepted and
    # silently ignored, which would let the agent believe it had been recorded as a
    # person's own typing.
    assert "error" in envelope, envelope
    # AND NOTHING WAS STORED.
    assert http.get(f"/api/experiments/{eid}/notes").json()["total"] == 0


# ==========================================================================
# 5. an ambiguous source stays ambiguous — §5
# ==========================================================================

def test_ambiguous_prose_becomes_a_note_and_no_value_is_invented(http):
    """**§5.** Capturing words must not manufacture a value from them.

    The words here state no single value — "around 425, maybe 430" is the ledger's own
    worked case. The note stores them; nothing derives a number. The record's open
    questions are UNCHANGED by the capture, which is the mechanical form of "no value
    was invented": a fabricated value would have closed one.
    """
    eid, _rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    before = http.get(f"/api/experiments/{eid}/pending").json()
    ambiguous = "The temperature was around 425, maybe 430 — I would have to check."

    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=ambiguous,
        client_request_key="ambiguous-1",
    )
    note = captured["data"]["note"]
    # THE WORDS ARE KEPT WHOLE, hedge included. Not resolved to one of the two numbers.
    assert note["text"] == ambiguous
    # NO CANDIDATE FIELD PATH IS INVENTED. `None`, not a plausible-looking guess —
    # and the MCP tool cannot supply one even if a model wanted to.
    assert note["candidate_field_path"] is None, note["candidate_field_path"]
    assert note["candidate_rule"] is None, note["candidate_rule"]
    assert "candidate_field_path" not in TOOLS["isaac_capture_note"].input_schema[
        "properties"
    ]

    # AND THE RECORD OWES EXACTLY WHAT IT OWED. A capture closes no question.
    after = http.get(f"/api/experiments/{eid}/pending").json()
    assert {q.get("blocker_key") for q in after["pending"]} == {
        q.get("blocker_key") for q in before["pending"]
    }
    # No field acquired a value.
    assert http.get(f"/api/experiments/{eid}").json()["evidenced_field_count"] == (
        http.get(f"/api/experiments/{eid}").json()["evidenced_field_count"]
    )


# ==========================================================================
# 6. MCP cannot perform the final Submit — the ABSENCE of the authority
# ==========================================================================

def test_STRUCTURAL_no_finalising_authority_exists_at_any_scope():
    """**THE ABSENCE OF AN AUTHORITY, asserted as an absence.**

    Labelled `STRUCTURAL` in the name because it is the one claim here that cannot be
    driven: you cannot call a tool that does not exist, so a behavioural test would be
    asserting that a typo is refused. The honest form is to enumerate the surface and
    show the authority is not in it — at ANY scope, not merely at the one a test
    happens to hold.
    """
    # NO OPERATION TARGETS A FINALISING ROUTE, at any scope.
    for token in ("submit", "export", "/review", "discard", "resolve_conflict"):
        assert not any(
            token in op.path_template for op in OPERATIONS.values()
        ), token
    # AND NO TOOL NAME SUGGESTS ONE.
    for token in ("submit", "accept", "approve", "export", "finalis", "publish", "delete"):
        assert not any(token in name for name in PERMITTED_TOOL_NAMES), token
    # THE SCOPE VOCABULARY CANNOT EXPRESS IT EITHER — a closed enum with no such
    # member, so a deployment cannot grant what a tool cannot ask for.
    assert not any("submit" in s.value or "finalis" in s.value for s in Scope)
    # AND THE TWO WRITE-CAPABLE SCOPES REACH EXACTLY THE OPERATIONS THEY REACH.
    proposals_write = {
        op_id for op_id, op in OPERATIONS.items() if op.scope is Scope.PROPOSALS_WRITE
    }
    assert proposals_write == {"create_note", "create_proposal"}, proposals_write


def test_the_agent_is_refused_the_review_route_even_holding_every_scope(armed_http):
    """AND THE BEHAVIOURAL HALF: with every scope this server can express, and under
    the fixture verifier — the configuration on which a PERSON's acceptance succeeds —
    the agent still cannot accept.

    This is the case that makes the structural test above worth having. The same
    deployment, the same record, the same proposal: a website request accepts it, and
    the agent has no operation that does.
    """
    eid, rid, etag = _record_with_a_run(armed_http)
    agent = _agent(armed_http.app, *Scope)
    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="no-accept-1",
    )
    proposed = _tool(
        agent,
        "isaac_propose_field_value",
        experiment_id=eid,
        if_match=captured["etag"],
        note_id=captured["data"]["note"]["id"],
        target_field_path=TARGET,
        proposed_value=301.0,
        rule="The transcript said the cell sat at 301 K throughout.",
        run_id=rid,
        client_request_key="no-accept-2",
    )
    proposal_id = proposed["data"]["proposal"]["proposal_id"]

    # THE TOOL DOES NOT EXIST — the dispatch refuses the NAME, at full scope.
    for invented in ("isaac_accept_proposal", "isaac_review_proposal", "isaac_submit_record"):
        envelope = _rpc(
            agent, "tools/call", {"name": invented, "arguments": {"experiment_id": eid}}
        )
        assert "error" in envelope, (invented, envelope)

    # AND THE PERSON'S ROUTE STILL WORKS, in this same deployment — which is what
    # proves the refusal above is about AUTHORITY and not about the proposal being
    # unacceptable.
    review = armed_http.post(
        f"/api/experiments/{eid}/proposals/{proposal_id}/review",
        json={
            "action": "accept",
            "confirmed_by_user": True,
            # REQUIRED, and measured rather than assumed: the route refuses
            # `422 unknown_accepted_from` without it. `candidate` means "the
            # proposed value is right and is written as it stands"; `edited`
            # means the reviewer corrected it. Neither is a default, which is
            # the route refusing to guess which claim a person is making.
            "accepted_from": "candidate",
        },
        headers={"If-Match": _etag(armed_http, eid)},
    )
    assert review.status_code == 200, review.text


def test_the_default_configuration_still_refuses_acceptance_with_409(http):
    """THE OTHER IDENTITY LEG, driven in the same file so neither is quietly lost.

    Without the fixture verifier, acceptance answers **409 `human_actor_required`** —
    a CONFIGURATION fact, not a build defect, and no application change can close it.
    Nothing in this slice weakens it. Asserted here because a file that only ever ran
    `armed` would be silently proving the loop on a configuration no deployment has.
    """
    eid, rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="refusal-1",
    )
    proposed = _tool(
        agent,
        "isaac_propose_field_value",
        experiment_id=eid,
        if_match=captured["etag"],
        note_id=captured["data"]["note"]["id"],
        target_field_path=TARGET,
        proposed_value=301.0,
        rule="The transcript said the cell sat at 301 K throughout.",
        run_id=rid,
        client_request_key="refusal-2",
    )
    proposal_id = proposed["data"]["proposal"]["proposal_id"]

    review = http.post(
        f"/api/experiments/{eid}/proposals/{proposal_id}/review",
        json={
            "action": "accept",
            "confirmed_by_user": True,
            # REQUIRED, and measured rather than assumed: the route refuses
            # `422 unknown_accepted_from` without it. `candidate` means "the
            # proposed value is right and is written as it stands"; `edited`
            # means the reviewer corrected it. Neither is a default, which is
            # the route refusing to guess which claim a person is making.
            "accepted_from": "candidate",
        },
        headers={"If-Match": _etag(http, eid)},
    )
    assert review.status_code == 409, review.text
    assert review.json()["error"] == "human_actor_required", review.json()
    # THE CAPTURE AND THE PROPOSAL BOTH SURVIVED the refusal, which is the property
    # that makes the refusal safe: nothing the agent did was rolled back.
    assert http.get(f"/api/experiments/{eid}/notes").json()["total"] == 1
    assert (
        http.get(f"/api/experiments/{eid}/proposals/{proposal_id}").json()["proposal"][
            "state"
        ]
        == "open"
    )


# ==========================================================================
# 7. no provider is required — every seam answers 501 and the loop is green
# ==========================================================================

def test_every_provider_seam_refuses_and_the_loop_does_not_need_one(http):
    """**NO MODEL IS INVOLVED, AND THAT IS ASSERTED RATHER THAN ASSUMED.**

    The two provider seams answer `501 no_provider_configured` in every deployment —
    driven here, in the same process that just ran the whole loop. So the loop's
    greenness is not an artifact of a provider being quietly available somewhere: it
    is green with both seams demonstrably refusing.
    """
    eid, _rid, etag = _record_with_a_run(http)

    # THE KEY IS `reason`, NOT `error`, and the body carries `refused` and `seam`.
    # Measured over HTTP rather than assumed — the first version of this test asserted
    # `error` and was wrong about both seams at once.
    assistant = http.post("/api/assistant/ask", json={"question": "anything"})
    assert assistant.status_code == 501, (assistant.status_code, assistant.text[:200])
    assert assistant.json()["reason"] == "no_provider_configured", assistant.json()
    assert assistant.json()["refused"] is True
    assert assistant.json()["seam"] == "assistant"

    transcription = http.post("/api/transcription", json={"audio_ref": "held-in-tab:1"})
    assert transcription.status_code == 501, transcription.status_code
    assert transcription.json()["reason"] == "no_provider_configured"
    assert transcription.json()["seam"] == "transcription"
    # AND EACH NAMES THE EXTERNAL DECISIONS IT IS WAITING ON — the D-rows Dean
    # deferred — rather than reading as a fault in this build.
    assert transcription.json()["missing"], transcription.json()

    # AND THE AGENT PATHWAY WORKS ANYWAY, in this same process.
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="no-provider-1",
    )
    assert captured["status"] == 201
    assert captured["data"]["note"]["text"] == SPOKEN


def test_the_mcp_state_is_disclosed_and_names_the_external_decisions(http):
    """**MCP-003.** The seam says what it is on the wire, so a 404 becomes diagnosable.

    Driven over the website's own transport, because the point is that an OPERATOR
    reading `/api/health` can tell the four postures apart — which was impossible
    before, by construction.
    """
    block = http.get("/api/health").json()["mcp"]
    assert block["posture"] == "unmounted", block
    assert set(block["postures"]) == {
        "unmounted",
        "local-only",
        "oauth-mounted",
        "remote-ready",
    }
    # THE FLAGS THE POSTURE IS DERIVED FROM are published, so it can be re-derived
    # rather than trusted.
    assert block["serves_transport"] is False
    assert block["requires_loopback_peer"] is True
    # THE EXTERNAL DECISIONS ARE NAMED as the deferred decisions they are.
    assert {d["id"] for d in block["outstanding_decisions"]} == {"D1", "D2"}
    for decision in block["outstanding_decisions"]:
        assert "DEFERRED" in decision["status"], decision
    # AND THE QUESTION PROSE IS WITHHELD — ids and statuses only. This is a
    # CORRECTION rather than a design chosen first: the first version of the block
    # forwarded each decision's text whole, and that text names the institution's
    # identity provider. `/api/health` answers WITHOUT CREDENTIALS, so it is the last
    # place a description of the environment should appear.
    assert set(block["outstanding_decisions"][0]) == {"id", "status"}, block[
        "outstanding_decisions"
    ][0]

    # AND NO SECRET AND NO DEPLOYMENT TOPOLOGY IS IN IT.
    #
    # THE VOCABULARY IS REUSED, NOT RE-INVENTED: `_FORBIDDEN_SUBSTRINGS` is the list
    # `test_about_and_openapi.py` applies to `/api/openapi` and `/api/about`, and it
    # says of itself that there is "deliberately NO exception list". That guard caught
    # this block's route DESCRIPTION during this slice; it did NOT cover the BODY,
    # which is the gap this assertion closes — the body is the part a caller actually
    # receives.
    from test_about_and_openapi import _FORBIDDEN_SUBSTRINGS

    blob = str(block).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in blob, f"leak in the health mcp block: {needle!r}"
    # Plus the token shapes that list does not name.
    for forbidden in ("Bearer", "eyJ", "BEGIN", "PRIVATE KEY", "isaac:read"):
        assert forbidden.lower() not in blob, forbidden

    # THE WHOLE BANNER, NOT ONLY THE NEW BLOCK. Scoping the scan to `mcp` would let a
    # future block leak beside a guarded one, which is the partial-sweep failure this
    # repository records repeatedly.
    whole = str(http.get("/api/health").json()).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in whole, f"leak in the health banner: {needle!r}"


def test_the_two_operator_controlled_env_values_are_NEVER_echoed(monkeypatch):
    '''*** C-2, FOUND BY INDEPENDENT REVIEW 2026-09-13: THE SWEEP ABOVE IS VACUOUS ON
    THE ONLY TWO FIELDS AN OPERATOR OR AN ATTACKER CONTROLS. ***

    The `http` fixture never sets `ISAAC_MCP_DEPLOYMENT` or
    `ISAAC_MCP_LOCAL_SCOPES`, so every assertion above runs over a body where
    `supplied_value` is `None` and `reason` is `"unset"`. The claim that the guard
    "sweeps the WHOLE health banner" was true and **inert**: a forbidden substring
    can only be found in a field that carries content, and those two carried none.

    THAT IS NOT A HYPOTHETICAL. With the values set, the pre-fix code served this
    on an uncredentialed `GET /api/health`, verbatim:

        "supplied_value": "postgres://user:S3cr3tP@ss@db.internal.slac.stanford.edu:5432/isaac"

    while `GET /api/experiments` answered `401` to the same caller. So this test
    sets both variables to values that are unmistakably secrets, and asserts over
    the WHOLE serialised banner. It is the arm the sweep above was missing, not a
    duplicate of it.

    **WHY `monkeypatch` AND A FRESH APP RATHER THAN THE `http` FIXTURE.** The binding
    is resolved from the process environment at request time, so the variables have
    to be set before the call; the fixture's app is built without them. A separate
    app also keeps the poisoned environment out of every other test in this module.
    '''
    import json as _json

    from fastapi.testclient import TestClient

    from isaac_api.app import create_app
    from isaac_api.mcp import deployment as _dep

    secrets = {
        # A pasted connection string: the exact shape the review reproduced.
        _dep.DEPLOYMENT_ENV: (
            "postgres://user:S3cr3tP@ss@db.internal.example.invalid:5432/isaac"
        ),
        # The second channel: `reason` used to interpolate the offending token out
        # of this one as `misconfigured: {token}`.
        _dep.LOCAL_SCOPES_ENV: "isaac:not-a-real-scope-NOTASCOPE",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)

    body = _json.dumps(TestClient(create_app()).get("/api/health").json())

    # Not one fragment of either value, at any granularity a reader could use.
    for fragment in (
        "S3cr3tP@ss",
        "db.internal.example.invalid",
        "postgres://",
        "5432",
        "NOTASCOPE",
        "not-a-real-scope",
    ):
        assert fragment not in body, f"the health banner echoed {fragment!r}"

    # AND THE FIELDS ARE STILL THERE, SAYING SOMETHING TRUE. Redaction that removed
    # the keys would pass the assertions above while making the block less
    # interpretable, which is not the fix — an operator still has to be able to tell
    # "unset" from "set and not recognised".
    block = _json.loads(body)["mcp"]
    assert block["supplied_value"] == _dep.WITHHELD_SUPPLIED_VALUE, block
    assert block["reason"] == "unrecognised", block


def test_a_RECOGNISED_binding_name_IS_still_echoed_when_something_else_is_wrong(
    monkeypatch,
):
    '''The other half of C-2's fix: redaction must not be indiscriminate.

    `local-loopback` is one of this build's own published binding names -- it is in
    `deployment.py`, in the OpenAPI document and in a public repository -- so
    echoing it back tells an operator "I recognised your NAME and something else is
    wrong", which is the one case where the value is informative and carries nothing
    the reader did not already have. A redaction that withheld it too would make a
    correctly-named-but-misconfigured deployment indistinguishable from a typo, and
    that distinction is the whole diagnostic purpose of this block.

    Without this arm, a `redact_supplied_value` returning a constant for EVERY input
    would pass the test above.

    ── THE BRANCH THIS HAD TO BE MOVED ONTO, recorded because the first version of
    this test asserted the wrong one and FAILED ──────────────────────────────────

    Setting a VALID `local-loopback` configuration does not exercise the echo at
    all: `resolve_binding` returns a `LocalLoopbackDeployment`, whose `detail()`
    carries no `supplied_value`, so the served field is `None` --
    `assert None == 'local-loopback'`. `supplied_value` exists ONLY on the
    `UnconfiguredDeployment` path.

    So the echo is reachable exactly when a RECOGNISED name fails for a
    DIFFERENT reason, and the shipped case is a bad scope list. That is also the
    case where echoing is most useful, so the test is now both correct and
    pointed at the right thing.
    '''
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app
    from isaac_api.mcp import deployment as _dep

    monkeypatch.setenv(_dep.DEPLOYMENT_ENV, _dep.LOCAL_LOOPBACK)
    # Recognised binding, UNrecognised scope -> `UnconfiguredDeployment`, reason
    # `misconfigured: ...`, and `supplied_value` carrying the recognised name.
    monkeypatch.setenv(_dep.LOCAL_SCOPES_ENV, "isaac:NOT-A-SCOPE-EITHER")

    block = TestClient(create_app()).get("/api/health").json()["mcp"]
    assert block["supplied_value"] == _dep.LOCAL_LOOPBACK, block
    # The name survives; the OFFENDING TOKEN still does not.
    assert block["reason"] == "misconfigured: unrecognised scope", block
    assert "NOT-A-SCOPE-EITHER" not in str(block), block


# ==========================================================================
# 8. the deep link an agent hands the scientist — MCP-006
# ==========================================================================

def test_the_capture_and_the_proposal_each_return_a_usable_relative_deep_link(http):
    """**MCP-006.** An agent can say WHERE to look, without inventing a base path.

    Asserted over what the dispatch RETURNED, and cross-checked against the link
    builder — so this fails both if the handler stops emitting a link and if the
    link's shape drifts from the frontend's parameter.
    """
    eid, rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="link-1",
    )
    capture_link = captured["data"]["links"]["capture"]
    assert capture_link == links.capture_link(eid)
    # RELATIVE, and that is the load-bearing property: the router `basename` is `''`
    # locally and `/krish` deployed, and this process cannot know the public origin.
    assert capture_link.startswith("/record/")
    assert "http" not in capture_link and "localhost" not in capture_link

    proposed = _tool(
        agent,
        "isaac_propose_field_value",
        experiment_id=eid,
        if_match=captured["etag"],
        note_id=captured["data"]["note"]["id"],
        target_field_path=TARGET,
        proposed_value=301.0,
        rule="The transcript said the cell sat at 301 K throughout.",
        run_id=rid,
        client_request_key="link-2",
    )
    proposal_id = proposed["data"]["proposal"]["proposal_id"]
    deep = proposed["data"]["links"]["proposal"]
    # IT ADDRESSES THE PROPOSAL THAT WAS ACTUALLY STORED — read off the route's own
    # body, so a deduplicated answer links to the first attempt's proposal and not to
    # one that was never minted.
    assert deep == links.proposal_link(eid, proposal_id)
    assert f"proposal={proposal_id}" in deep
    assert "view=capture" in deep


def test_a_deduplicated_capture_links_to_the_note_that_exists(http):
    """THE CASE A LINK BUILT FROM THE REQUEST WOULD GET WRONG.

    On a retry the stored note is the FIRST attempt's. The capture link is
    record-scoped so it cannot be wrong — but the PROPOSAL link is id-scoped, and this
    asserts the id it carries is the stored one rather than anything this call
    supplied.
    """
    eid, rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    note = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="dedup-link-note",
    )
    common = dict(
        experiment_id=eid,
        note_id=note["data"]["note"]["id"],
        target_field_path=TARGET,
        proposed_value=301.0,
        rule="The transcript said the cell sat at 301 K throughout.",
        run_id=rid,
        client_request_key="dedup-link-proposal",
    )
    first = _tool(agent, "isaac_propose_field_value", if_match=note["etag"], **common)
    second = _tool(
        agent, "isaac_propose_field_value", if_match=first["etag"], **common
    )
    assert second["data"]["deduplicated"] is True
    assert (
        second["data"]["links"]["proposal"] == first["data"]["links"]["proposal"]
    ), (second["data"]["links"], first["data"]["links"])


# ==========================================================================
# 9. the abuse bounds — MCP-001a
# ==========================================================================

def test_a_record_refuses_notes_past_its_ceiling_rather_than_evicting_one(http, monkeypatch):
    """**MCP-001a.** With EXT-01 open, an untrusted in-cluster caller can reach this
    operation — so *inert to export is not the same as harmless to the record*.

    THE CEILING IS LOWERED FOR THE TEST rather than the test writing 1,000 notes: the
    property under test is "it refuses, names the ceiling, and destroys nothing", and
    that property does not depend on the number. The real constant is asserted
    separately below so a lowered ceiling cannot hide a missing one.
    """
    from isaac_api import routes

    monkeypatch.setattr(routes, "_MAX_NOTES_PER_RECORD", 2)
    eid, _rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)

    stored = []
    for i in range(2):
        out = _tool(
            agent,
            "isaac_capture_note",
            experiment_id=eid,
            if_match=_etag(http, eid),
            text=f"Synthetic note {i}: the shutter stuck.",
            client_request_key=f"bound-{i}",
        )
        assert out["status"] == 201
        stored.append(out["data"]["note"]["id"])

    refused = _tool_refused(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=_etag(http, eid),
        text="Synthetic note 2: one too many.",
        client_request_key="bound-2",
    )
    assert refused["status"] == 422, refused
    assert refused["data"]["error"] == "too_many_notes", refused["data"]
    # THE REFUSAL NAMES THE CEILING AND THE MEASURED VALUE, so a caller learns what it
    # is up against rather than only that it failed.
    assert refused["data"]["max_per_record"] == 2
    assert refused["data"]["total"] == 2

    # NOTHING WAS EVICTED. A bound that dropped the oldest note to make room would
    # destroy a verbatim capture, which is the one thing the feature exists not to do.
    listed = http.get(f"/api/experiments/{eid}/notes").json()
    assert [n["id"] for n in listed["notes"]] == stored
    assert listed["total"] == 2

    # AND A RETRY OF AN ALREADY-STORED NOTE IS STILL ANSWERABLE AT THE CEILING —
    # the deduplication branch runs BEFORE the capacity check on purpose, so a client
    # that legitimately captured something can always confirm it did.
    again = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=_etag(http, eid),
        text="Synthetic note 0: the shutter stuck.",
        client_request_key="bound-0",
    )
    assert again["data"]["deduplicated"] is True
    assert again["data"]["note"]["id"] == stored[0]


def test_the_real_ceilings_are_in_place_and_are_not_the_test_values():
    """THE NEGATIVE CONTROL for the test above, which monkeypatches the ceiling.

    Without this, that test would pass on a build whose real ceiling was absent or
    absurd — it lowers the constant, so it cannot witness the constant.
    """
    from isaac_api import routes

    assert routes._MAX_NOTES_PER_RECORD == 1000
    assert routes._MAX_NOTE_STATE_BYTES == routes._MAX_NOTE_BYTES * 16
    assert routes._MAX_CLIENT_REQUEST_KEY_LENGTH == 128
    # AND THE TOOL PUBLISHES A TEXT BOUND DERIVED FROM THE ROUTE'S OWN, so a caller
    # is refused at the boundary rather than after sending a payload the route drops.
    assert (
        TOOLS["isaac_capture_note"].input_schema["properties"]["text"]["maxLength"]
        == routes._MAX_NOTE_BYTES
    )


def test_an_over_long_note_is_refused_rather_than_truncated(http):
    """The words are never silently shortened — a truncated note misrepresents what
    was written, which is the defect `notes.py`'s first invariant exists to prevent."""
    eid, _rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    # Past the tool's published `maxLength`, so it is refused while the request is
    # being CONSTRUCTED and nothing is issued.
    envelope = _rpc(
        agent,
        "tools/call",
        {
            "name": "isaac_capture_note",
            "arguments": {
                "experiment_id": eid,
                "if_match": etag,
                "text": "x" * (256 * 1024 + 1),
                "client_request_key": "too-long",
            },
        },
    )
    assert "error" in envelope, envelope
    assert http.get(f"/api/experiments/{eid}/notes").json()["total"] == 0


# ==========================================================================
# 10. no production account, credential or database is contacted
# ==========================================================================

def test_STRUCTURAL_the_loop_opens_no_database_connection_and_reads_no_credential(
    http, monkeypatch
):
    """**THE DATA-BOUNDARY CLAIM, MADE MECHANICAL.**

    `STRUCTURAL` in the name because it proves an ABSENCE by instrumenting the seams
    rather than by observing a network — this process has no way to witness "no packet
    left the host", and claiming otherwise would be the kind of unmeasured assertion
    this file exists to avoid. What it DOES establish, by substitution: the whole loop
    runs without the durable write path being reached and without any provider
    credential being read.
    """
    from isaac_api import db_write

    opened: list[str] = []

    def _refuse(*args, **kwargs):  # pragma: no cover - the point is it is not called
        opened.append("write_transaction")
        raise AssertionError("the loop opened a database transaction")

    monkeypatch.setattr(db_write, "write_transaction", _refuse)

    eid, rid, etag = _record_with_a_run(http)
    agent = _agent(http.app, Scope.READ, Scope.PROPOSALS_WRITE)
    captured = _tool(
        agent,
        "isaac_capture_note",
        experiment_id=eid,
        if_match=etag,
        text=SPOKEN,
        client_request_key="boundary-1",
    )
    _tool(
        agent,
        "isaac_propose_field_value",
        experiment_id=eid,
        if_match=captured["etag"],
        note_id=captured["data"]["note"]["id"],
        target_field_path=TARGET,
        proposed_value=301.0,
        rule="The transcript said the cell sat at 301 K throughout.",
        run_id=rid,
        client_request_key="boundary-2",
    )
    assert opened == [], opened

    # AND THE MCP LAYER READS NO ENVIRONMENT BEYOND ITS OWN DEPLOYMENT SELECTOR,
    # which `test_mcp_boundaries.py` already pins module-by-module. Re-asserted here
    # over the ONE variable class that would matter for a production provider: none of
    # these is set, and the loop above did not need them.
    for name in (
        "ISAAC_MCP_OAUTH_ISSUER",
        "ISAAC_MCP_OAUTH_RESOURCE",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert _tool(agent, "isaac_list_experiments")["status"] == 200
