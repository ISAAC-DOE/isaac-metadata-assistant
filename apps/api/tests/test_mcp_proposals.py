"""The MCP ingestion-proposal surface, and — mostly — what it must never be able to do.

WHAT THIS SLICE CLOSED
======================
The product workflow ``docs/ingestion-proposal-contract.md`` §4 authorizes is
*Claude voice or chat → authenticated ISAAC MCP → durable structured proposal → website
review*. **The MCP step did not exist.** Measured at ``7ff8194``: ten permitted tool
names, none of them proposal- or changes-related, and two ``Scope`` members, neither of
them ``isaac:proposals.write``. The HTTP routes were complete; nothing could reach them.

Four tools now can — ``isaac_propose_field_value``, ``isaac_list_proposals``,
``isaac_get_proposal`` and ``isaac_get_changes`` — and the fifth route is deliberately
still unreachable.

WHY MOST OF THIS FILE IS NEGATIVE
=================================
Every safety claim the slice makes is written here as a case that goes RED if the defect
is reintroduced, and each asserts BEHAVIOUR rather than the presence of a string. That
is not a stylistic preference: this repository has repeatedly shipped guards that passed
while being wrong — a case-sensitive scan for "Connected" that a lowercase claim walked
past, a seam guard satisfied by a constant while the function it guarded fabricated a
success, a table-driven test whose fixture made every row reachable so it could not see
which rows had been reachable before. So the acceptance refusal is driven through the
real client against the real router, the scope separation is driven from a real
principal holding one scope, and the "no record content" projection is checked by
planting distinctive words in a note and looking for them.

Everything here is synthetic. Nothing opens a network connection, reads real data, or
touches a database.
"""

from __future__ import annotations

import asyncio
import copy
import json

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_api.mcp import LocalLoopbackDeployment, McpServer, Scope
from isaac_api.mcp.client import ApiRefusal, AsgiApiClient
from isaac_api.mcp.policy import (
    OPERATIONS,
    PERMITTED_TOOL_NAMES,
    forbidden_tool_reason,
)
from isaac_api.mcp.server import INSUFFICIENT_SCOPE, INVALID_PARAMS
from isaac_api.mcp.tools import TOOLS
from isaac_records.export import transform

from test_export_fan_out import _split_full_draft

#: A run-level target, taken from the application's own derived set rather than written
#: out, for the reason ``test_ingestion_proposals`` gives: a hand-copied literal is a
#: second definition of "a real target" and can rot into a test that passes for the
#: wrong reason.
RUN_PATH = "context.temperature_K"
RECORD_PATH = "system.technique"
#: A second run-level target whose value is a STRING, used where a numeric value would
#: collide by chance with a base32 id inside an assertion about what a payload omits.
CONTEXT_PATH = "context.environment"
RECORD_VALUE = routes._record_enum_fields()[RECORD_PATH][0]

#: DISTINCTIVE ON PURPOSE. The projection assertions below search the propose result for
#: these words; a note reading "the sample was measured" would let a leak hide behind
#: vocabulary that appears everywhere.
NOTE_TEXT = "zarquon pellet held at 301 K by the flimflam controller throughout"
#: The span of `NOTE_TEXT` a proposal cites, so the derived excerpt is a known string.
SPAN = (0, 21)
RULE = "the number before ` K` in the captured sentence was read as a temperature"


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def experiment(app):
    """An ordinary-workspace record with one run and one note, and no proposals."""
    experiment_draft, run_draft = _split_full_draft()
    exp = ws.create_experiment(
        "MCP proposals fixture", {"kind": "synthetic"}, experiment_draft
    )
    exp.add_run(label="Run A", draft=copy.deepcopy(run_draft))
    exp.capture_note(text=NOTE_TEXT, source="typed_note")
    exp.save_versioned()
    return ws.load_experiment(exp.id)


def _server(app, *scopes: Scope, session: str | None = None) -> McpServer:
    return McpServer(
        app,
        binding=LocalLoopbackDeployment(
            scopes=frozenset(scopes), tutorial_session_id=session
        ),
    )


@pytest.fixture()
def reader(app) -> McpServer:
    return _server(app, Scope.READ)


@pytest.fixture()
def proposer(app) -> McpServer:
    """The realistic model-derived grant: read AND propose, and NOT draft-write."""
    return _server(app, Scope.READ, Scope.PROPOSALS_WRITE)


@pytest.fixture()
def propose_only(app) -> McpServer:
    """``isaac:proposals.write`` alone. Reaches no read tool at all."""
    return _server(app, Scope.PROPOSALS_WRITE)


@pytest.fixture()
def draft_writer(app) -> McpServer:
    """Read plus draft-write, which is what the product's agent grant was before."""
    return _server(app, Scope.READ, Scope.DRAFT_WRITE)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def rpc(server: McpServer, method: str, params: dict | None = None) -> dict:
    message = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        message["params"] = params
    return asyncio.run(server.handle(message))


def call(server: McpServer, name: str, **arguments) -> dict:
    envelope = rpc(server, "tools/call", {"name": name, "arguments": arguments})
    assert "error" not in envelope, envelope["error"]
    return envelope["result"]


def payload(server: McpServer, name: str, **arguments) -> dict:
    result = call(server, name, **arguments)
    assert result["isError"] is False, result["structuredContent"]
    return result["structuredContent"]


def refused(server: McpServer, name: str, **arguments) -> dict:
    """A tool call the ROUTE refused. Distinct from a scope denial and from a schema one."""
    result = call(server, name, **arguments)
    assert result["isError"] is True, result["structuredContent"]
    return result["structuredContent"]


def denied(server: McpServer, name: str, **arguments) -> dict:
    envelope = rpc(server, "tools/call", {"name": name, "arguments": arguments})
    assert "error" in envelope, envelope
    assert envelope["error"]["code"] == INSUFFICIENT_SCOPE, envelope["error"]
    return envelope["error"]


def etag_of(server: McpServer, experiment_id: str) -> str:
    return payload(server, "isaac_get_experiment", experiment_id=experiment_id)["etag"]


def propose(server: McpServer, exp, *, etag_from=None, **overrides) -> dict:
    """One accepted proposal through MCP, with every required argument defaulted.

    Returns the ROUTE's body — ``{"proposal": ..., "deduplicated": ...,
    "experiment_version": ...}`` — because that is what the handler forwards. It used to
    return a flat acknowledgement built by a projection in the handler; see
    ``test_the_create_result_is_the_ROUTES_OWN_BODY_like_every_other_tool``.
    """
    source = etag_from if etag_from is not None else server
    arguments = {
        "experiment_id": exp.id,
        "if_match": etag_of(source, exp.id),
        "note_id": exp.notes[0].id,
        "target_field_path": RUN_PATH,
        "proposed_value": 301.0,
        "rule": RULE,
        "run_id": exp.runs[0].id,
        "start_char": SPAN[0],
        "end_char": SPAN[1],
        "client_request_key": "mcp-test-key-1",
    }
    arguments.update(overrides)
    return payload(server, "isaac_propose_field_value", **arguments)["data"]


def stored(experiment_id: str):
    """The record as the STORE holds it, never as a response reported it."""
    return ws.load_experiment(experiment_id)


def authoritative_snapshot(exp) -> str:
    """Contract **I1**'s exact shape: every export unit's draft, every run's resolved
    draft, and the record's own draft, byte-for-byte."""
    return json.dumps(
        {
            "export": [unit.draft for unit in exp.export_units()],
            "resolved": [exp.resolved_run_draft(run) for run in exp.sorted_runs()],
            "draft": exp.draft,
        },
        sort_keys=True,
        default=str,
    )


def exported_bytes(exp) -> str:
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


# ==========================================================================
# 1. THE SURFACE EXISTS — and the gap it closed is named, so a future reader
#    can tell a capability from an accident
# ==========================================================================

def test_the_four_tools_are_registered_with_the_scopes_the_contract_assigns():
    """``docs/ingestion-proposal-contract.md`` §4's amended surface, as a table.

    The scope split is the whole design and is asserted per tool rather than in
    aggregate: creating a proposal must NOT cost ``DRAFT_WRITE``, which can change draft
    content directly, and reading proposal status must not cost a write at all.
    """
    assert {
        "isaac_propose_field_value",
        "isaac_list_proposals",
        "isaac_get_proposal",
        "isaac_get_changes",
    } <= PERMITTED_TOOL_NAMES
    assert TOOLS["isaac_propose_field_value"].scope is Scope.PROPOSALS_WRITE
    for name in ("isaac_list_proposals", "isaac_get_proposal", "isaac_get_changes"):
        assert TOOLS[name].scope is Scope.READ, name
        assert TOOLS[name].read_only is True, name
    assert TOOLS["isaac_propose_field_value"].read_only is False


def test_a_proposal_created_through_mcp_is_the_one_the_website_reads(proposer, experiment):
    """END TO END, and against the STORE rather than against the response.

    A response saying "created" is the claim; the record holding the proposal is the
    fact. This is also the positive control every negative case below depends on — a
    create that silently did nothing would make the refusals meaningless.
    """
    acknowledged = propose(proposer, experiment)["proposal"]

    held = stored(experiment.id).proposals
    assert len(held) == 1
    only = held[0]
    assert only.proposal_id == acknowledged["proposal_id"]
    assert only.target_field_path == RUN_PATH
    assert only.proposed_value == 301.0
    assert only.rule == RULE
    assert only.run_id == experiment.runs[0].id
    assert only.state == "open"

    # …and the website's own read operation returns it, which is the workflow's point.
    read_back = payload(
        proposer,
        "isaac_get_proposal",
        experiment_id=experiment.id,
        proposal_id=only.proposal_id,
    )["data"]["proposal"]
    assert read_back["proposed_value"] == 301.0
    assert read_back["state"] == "open"


def test_the_proposal_is_marked_unconfirmed_on_the_wire_and_not_only_in_the_store(
    proposer, experiment
):
    """Contract **I5**. The four constants must CROSS the boundary.

    An agent reading JSON does not see the class invariant, so a proposal that arrived
    without these could be reported to a scientist as a recorded value. Both surfaces
    are checked, because the acknowledgement is a PROJECTION and dropping them there to
    save four keys would drop the guarantee where it is most likely to be read.
    """
    acknowledged = propose(proposer, experiment)["proposal"]
    full = payload(
        proposer,
        "isaac_get_proposal",
        experiment_id=experiment.id,
        proposal_id=acknowledged["proposal_id"],
    )["data"]["proposal"]
    for view in (acknowledged, full):
        assert view["status"] == "ingestion_proposal"
        assert view["verified"] is False
        assert view["is_evidence"] is False
        assert view["is_field_value"] is False
        assert view["applied"] is False


# ==========================================================================
# 2. NEGATIVE CONTROL — MCP CANNOT ACCEPT
# ==========================================================================

def test_no_accept_tool_exists_and_the_name_for_one_is_an_import_error():
    """The refusal is structural at TWO independent layers, and both are asserted.

    ``accept`` is in ``FORBIDDEN_TOOL_TOKENS``, so ``isaac_accept_proposal`` cannot be
    registered under that name; and it is not in ``PERMITTED_TOOL_NAMES``, so it could
    not be registered even if the token set forgot it. Neither is trusted alone.
    """
    for name in (
        "isaac_accept_proposal",
        "isaac_accept_value",
        "isaac_approve_proposal",
        "accept_proposal",
    ):
        reason = forbidden_tool_reason(name)
        assert reason is not None, name
        assert name not in TOOLS, name
        # ~~`assert "accept" in forbidden_tool_reason(...)`~~ — **THAT ASSERTION WAS
        # SATISFIED BY THE NAME IT QUOTES, and this file's own header says it exists to
        # avoid exactly that.** `forbidden_tool_reason` falls through to *"the tool name
        # 'isaac_accept_proposal' is not in PERMITTED_TOOL_NAMES"*, which contains the
        # substring `accept` because the NAME does. Measured: with `accept` removed from
        # `FORBIDDEN_TOOL_TOKENS` this file still passed every case.
        #
        # The two refusals are different and only one of them is the token gate, so the
        # assertion names the gate's own wording AND the quoted token.
        assert "forbidden capability token" in reason, (name, reason)
        assert "'accept'" in reason or "'approve'" in reason, (name, reason)

    # And no registered name carries it — including the four added by this slice, which
    # is the check that would have caught a tool called `isaac_accept_field_value`.
    for name in TOOLS:
        assert "accept" not in name.lower(), name
        assert "approve" not in name.lower(), name


def test_registering_an_accept_tool_RAISES_rather_than_being_quietly_dropped():
    """The gate is import-time, so in production the failure is an application that
    will not start rather than a tool that quietly works.

    ~~"MUTATION-CHECKED: removing ``accept`` from ``FORBIDDEN_TOOL_TOKENS`` leaves this
    case green on its second assertion and RED on the first."~~ — **THAT CLAIM WAS
    FALSE, and it is struck rather than deleted because a false mutation claim is worse
    than none: it tells the next reader the guard has been tested when it has not.**
    Measured on 2026-09-01 with the token removed, this whole FILE stayed at 39 passed;
    the only failures were in other files. The reason is the one above — the refusal
    message quotes the name, so a substring check for ``accept`` passed on the
    not-permitted fallback.

    It is mutation-checked NOW, against the assertion above and this one, and the
    transcript is in the slice report rather than in this docstring, because a docstring
    cannot be re-run.
    """
    from isaac_api.mcp.tools import Tool, _validate_tool

    async def _handler(ctx, args):  # pragma: no cover - never invoked
        raise AssertionError("unreachable")

    forbidden = Tool(
        name="isaac_accept_proposal",
        title="Accept a proposal",
        description="",
        scope=Scope.PROPOSALS_WRITE,
        operation_ids=("create_proposal",),
        input_schema={"type": "object", "properties": {}, "required": [],
                      "additionalProperties": False},
        handler=_handler,
        read_only=False,
        idempotent=True,
    )
    with pytest.raises(RuntimeError) as raised:
        _validate_tool(forbidden)
    assert "accept" in str(raised.value)


def test_the_review_route_is_unreachable_from_mcp_BY_THE_OPERATION_TABLE(app):
    """The path is in no allowlist entry, and the client refuses to invent one.

    Two facts, because either alone is a single point of failure. The first is the
    table; the second is driven through the real client, which resolves an operation
    *id* and will not build a request for anything it cannot find — so a tool that tried
    to reach ``/review`` by naming it gets a refusal rather than a request.
    """
    assert not any("/review" in op.path_template for op in OPERATIONS.values())
    assert not any("review" in op.id for op in OPERATIONS.values())

    client = AsgiApiClient(app)
    for invented in ("review_proposal", "accept_proposal", "proposal_review"):
        with pytest.raises(ApiRefusal) as raised:
            asyncio.run(
                client.call(
                    invented,
                    path_params={"experiment_id": "0" * 26, "proposal_id": "0" * 26},
                )
            )
        assert raised.value.code == "operation_not_allowlisted", invented


def test_an_mcp_created_proposal_stays_OPEN_and_no_tool_at_any_scope_can_move_it(
    app, experiment
):
    """THE BEHAVIOURAL FORM OF "MCP CANNOT ACCEPT", and the one that survives a
    refactor that renames every constant above.

    A proposal is created through MCP by a caller granted EVERY scope this server can
    express, and then every tool in the registry is invoked against the record. The
    proposal must still be ``open`` and no value may have been written at its target.
    A caller holding every scope is the strongest form of the claim: it cannot be
    satisfied by the caller simply lacking a permission.
    """
    everything = _server(app, *Scope)
    created = propose(everything, experiment)["proposal"]
    pid = created["proposal_id"]
    target_before = stored(experiment.id).get_run(experiment.runs[0].id).draft.get(
        "fields", {}
    ).get(RUN_PATH)

    for name, tool in TOOLS.items():
        arguments = {"experiment_id": experiment.id}
        if "run_id" in tool.input_schema["properties"]:
            arguments["run_id"] = experiment.runs[0].id
        if "proposal_id" in tool.input_schema["properties"]:
            arguments["proposal_id"] = pid
        if "if_match" in tool.input_schema["properties"]:
            arguments["if_match"] = etag_of(everything, experiment.id)
        for required in tool.input_schema["required"]:
            arguments.setdefault(required, _plausible(required))
        envelope = rpc(everything, "tools/call", {"name": name, "arguments": arguments})
        # Whatever each answers — a result, a route refusal, an argument refusal — the
        # proposal may not move. A JSON-RPC error is a fine outcome here; a state change
        # is not.
        assert "result" in envelope or "error" in envelope, name

    after = stored(experiment.id)
    assert [p.state for p in after.proposals if p.proposal_id == pid] == ["open"]
    assert after.get_run(experiment.runs[0].id).draft.get("fields", {}).get(
        RUN_PATH
    ) == target_before


def _plausible(argument: str):
    """A syntactically acceptable value for a required argument this sweep does not
    otherwise supply. Deliberately values the ROUTE will reject: the sweep is about
    whether a proposal can be MOVED, not about making every call succeed."""
    return {
        "confirmed_by_user": True,
        "answers": {"edge": "L3"},
        "fields": {"context.environment": "vacuum"},
        "note_id": "0" * 26,
        "target_field_path": RUN_PATH,
        "proposed_value": 1,
        "rule": "sweep",
        "client_request_key": "sweep",
    }.get(argument, "0" * 26)


# ==========================================================================
# 3. NEGATIVE CONTROL — MCP CANNOT SUBMIT, EXPORT, OR FINALISE
# ==========================================================================

def test_the_new_surface_added_no_finalising_capability_of_any_kind():
    """Asserted over the whole operation table rather than over the four new entries.

    A slice that added a proposal create is exactly the slice a future author would use
    as precedent for adding an "apply" or a "publish", so the sweep is total.
    """
    for operation in OPERATIONS.values():
        lowered = f"{operation.id} {operation.path_template}".lower()
        for banned in (
            "submit",
            "export",
            "finalis",
            "finaliz",
            "publish",
            "delete",
            "discard",
            "remove",
            "purge",
            "migrat",
            "governance",
        ):
            assert banned not in lowered, f"{operation.id}: {banned}"


def test_a_stored_proposal_changes_no_exported_record_AT_ALL(proposer, experiment):
    """Contract **I2**, driven through MCP rather than through HTTP.

    The exported official record must be byte-identical with a proposal on the record
    and without one. This is structural — proposals live at ``state["proposals"]``,
    outside ``draft``, and ``export_draft`` reads ``draft`` — but structure is exactly
    what a future refactor changes, so it is measured.
    """
    before = exported_bytes(stored(experiment.id))
    propose(proposer, experiment)
    after = exported_bytes(stored(experiment.id))
    assert after == before

    # And the record is no more exportable than it was: a proposal cannot unblock one.
    assert stored(experiment.id).pending_count() == experiment.pending_count()


def test_creating_a_proposal_through_mcp_mutates_no_authoritative_metadata(
    proposer, experiment
):
    """Contract **I1**, in the contract's own shape and through the MCP client.

    MUTATION: applying the value at create time (calling the run-field writer from
    ``post_proposal``) turns this RED on the ``resolved`` and ``draft`` keys. Without
    it, "creating a proposal is safe" would rest on reading the route.
    """
    before = authoritative_snapshot(stored(experiment.id))
    propose(proposer, experiment)
    assert authoritative_snapshot(stored(experiment.id)) == before


# ==========================================================================
# 4. NEGATIVE CONTROL — THE SCOPES DO NOT NEST
# ==========================================================================

def test_a_proposals_write_only_principal_reaches_NOTHING_AT_ALL(propose_only, experiment):
    """``isaac:proposals.write`` confers no read, and therefore reaches no tool.

    ~~``test_a_proposals_write_only_principal_can_READ_NOTHING``, plus
    ``..._IS_ADMITTED_and_then_meets_the_precondition``, which asserted that such a
    principal could still CREATE.~~ — **both replaced on 2026-09-01, and the reason is
    below in ``test_a_refusal_from_this_route_can_carry_record_derived_facts``.** The
    create tool briefly cost ``PROPOSALS_WRITE`` alone so that §4's *"can create a
    proposal and read nothing else"* would be literally true. It was measurably not
    safe, so the tool now costs ``{READ, PROPOSALS_WRITE}`` like every other write and
    this principal is in exactly the position a ``DRAFT_WRITE``-only one is: inert.

    THE OLD TEST WOULD STILL PASS TODAY, WHICH IS WHY IT IS NAMED. It asserted the 412
    and then handed the principal a validator from a ``reader`` fixture — it never tried
    the ``current_version`` the 412 had just disclosed, so it read as a proof of
    containment while demonstrating none.
    """
    listed = rpc(propose_only, "tools/list")["result"]["tools"]
    assert listed == [], "a principal holding one write scope was shown a tool"

    for name, tool in TOOLS.items():
        arguments = {"experiment_id": experiment.id}
        for required in tool.input_schema["required"]:
            arguments.setdefault(required, _plausible(required))
        error = denied(propose_only, name, **arguments)
        assert "isaac:read" in error["data"]["missingScopes"], name


def test_a_refusal_from_this_route_can_carry_record_derived_facts(proposer, experiment):
    """THE MEASUREMENT THAT DECIDED THE SCOPE, KEPT AS A REGRESSION GUARD.

    ``_failed`` forwards a route's refusal body whole — correctly, and for every tool —
    and this route's refusals were written for a caller holding ``READ``. That is fine
    now and was NOT fine while ``isaac_propose_field_value`` cost ``PROPOSALS_WRITE``
    alone, because two of these bodies are enough to bootstrap a create and one of them
    reports a fact about a scientist's own note.

    This asserts the bodies still carry those fields — it is a guard on the REASON, not
    a complaint about the route. If a future author proposes a read-free write tool
    again, this test is the thing to read first: it shows what such a caller would be
    handed. **Do not "fix" it by making the route stop reporting them**; a client that
    cannot learn the current version from a 412 cannot recover from one.
    """
    stale = etag_of(proposer, experiment.id)
    propose(proposer, experiment, client_request_key="occupy")

    conflict = refused(
        proposer,
        "isaac_propose_field_value",
        experiment_id=experiment.id,
        if_match=stale,
        note_id=experiment.notes[0].id,
        target_field_path=RUN_PATH,
        proposed_value=301.0,
        rule=RULE,
        run_id=experiment.runs[0].id,
        client_request_key="bootstrap",
    )
    assert conflict["status"] == 412
    # THE BOOTSTRAP. The refusal names the version the next request needs.
    disclosed = conflict["data"]["current_version"]
    assert disclosed and disclosed != stale.strip('"')
    landed = payload(
        proposer,
        "isaac_propose_field_value",
        experiment_id=experiment.id,
        if_match=f'"{disclosed}"',
        note_id=experiment.notes[0].id,
        target_field_path=RUN_PATH,
        proposed_value=301.0,
        rule=RULE,
        run_id=experiment.runs[0].id,
        client_request_key="bootstrap",
    )
    assert landed["data"]["deduplicated"] is False
    assert len(stored(experiment.id).proposals) == 2

    # AND A REFUSAL THAT REPORTS A FACT ABOUT THE SCIENTIST'S OWN WORDS.
    span = refused(
        proposer,
        "isaac_propose_field_value",
        experiment_id=experiment.id,
        if_match=etag_of(proposer, experiment.id),
        note_id=experiment.notes[0].id,
        target_field_path=RUN_PATH,
        proposed_value=301.0,
        rule=RULE,
        run_id=experiment.runs[0].id,
        client_request_key="span",
        start_char=0,
        end_char=9999,
    )
    assert span["data"]["error"] == "invalid_span"
    assert span["data"]["note_text_length"] == len(NOTE_TEXT)


def test_a_read_only_principal_cannot_propose(reader, experiment):
    """The mirror. Reading a record is not permission to suggest a value for it."""
    listed = {t["name"] for t in rpc(reader, "tools/list")["result"]["tools"]}
    assert "isaac_propose_field_value" not in listed
    error = denied(
        reader,
        "isaac_propose_field_value",
        experiment_id=experiment.id,
        if_match='"x.0"',
        note_id=experiment.notes[0].id,
        target_field_path=RUN_PATH,
        proposed_value=301.0,
        rule=RULE,
        client_request_key="k",
    )
    assert error["data"]["missingScopes"] == ["isaac:proposals.write"]


def test_a_DRAFT_WRITE_principal_cannot_propose_and_a_PROPOSER_cannot_write_a_draft(
    draft_writer, proposer, experiment
):
    """THE SEPARATION IN BOTH DIRECTIONS, which is the reason the third scope exists.

    Folding the create into ``DRAFT_WRITE`` would have been one line and would have
    handed every existing read-write agent the model-derived channel, and every
    proposing agent the ability to change draft content directly.
    """
    denied(
        draft_writer,
        "isaac_propose_field_value",
        experiment_id=experiment.id,
        if_match=etag_of(draft_writer, experiment.id),
        note_id=experiment.notes[0].id,
        target_field_path=RUN_PATH,
        proposed_value=301.0,
        rule=RULE,
        client_request_key="k",
    )
    denied(
        proposer,
        "isaac_update_draft",
        experiment_id=experiment.id,
        run_id=experiment.runs[0].id,
        if_match='"x.0"',
        confirmed_by_user=True,
        fields={"context.environment": "vacuum"},
    )
    # …and the proposer's own capability still works, so the two denials above are not
    # a broken fixture.
    assert propose(proposer, experiment)["proposal"]["proposal_id"]


def test_the_write_scopes_do_not_imply_each_other_in_the_required_scope_sets():
    """Derived from ``Tool.required_scopes`` rather than from the enum, because that
    property is what the server actually checks."""
    assert TOOLS["isaac_propose_field_value"].required_scopes == frozenset(
        {Scope.READ, Scope.PROPOSALS_WRITE}
    )
    assert Scope.PROPOSALS_WRITE not in TOOLS["isaac_update_draft"].required_scopes
    assert Scope.DRAFT_WRITE not in TOOLS["isaac_propose_field_value"].required_scopes
    # EVERY tool costs READ on top of its own scope, with NO exemptions — the blanket
    # rule, restored. ~~"the exemption is one named tool, not a general relaxation"~~:
    # an exemption existed for one commit and is withdrawn, so this loop has no
    # `continue` in it. A `continue` is how a sweep passes over the case it exists for.
    for name, tool in TOOLS.items():
        assert Scope.READ in tool.required_scopes, name


# ==========================================================================
# 5. THE CREATE RESULT, AND THE PROJECTION THAT USED TO SHAPE IT
# ==========================================================================

def test_the_create_result_is_the_ROUTES_OWN_BODY_like_every_other_tool(
    proposer, experiment
):
    """~~Two tests asserted this result carried NO record content.~~ — **removed with
    the projection they guarded, on 2026-09-01.**

    They were correct about the projection and the projection worked: an independent
    review confirmed a key added to ``proposals.to_state`` could not have leaked through
    it. What they could not see is that they described the SUCCESS branch of a handler
    whose failure branch forwarded the route's refusals whole — see
    ``test_a_refusal_from_this_route_can_carry_record_derived_facts``. Once the tool
    costs ``READ`` the projection guards nothing (every key it withheld is one
    ``isaac_get_proposal`` away) while still LOOKING like a confidentiality boundary,
    which is worse than not having one.

    So the handler forwards the body like the other thirteen, and this pins that —
    because "it forwards the body" is the claim, and an agent that needs the excerpt to
    confirm its span landed on the right words now gets it in the same round trip.
    """
    result = propose(proposer, experiment)
    proposal = result["proposal"]
    assert result["deduplicated"] is False
    assert proposal["proposed_value"] == 301.0
    assert proposal["rule"] == RULE
    assert proposal["note_id"] == experiment.notes[0].id
    assert "zarquon" in proposal["excerpt"]
    # The four I5 constants still cross the boundary — that is `to_state`'s job and it
    # never depended on the projection.
    assert proposal["verified"] is False
    assert proposal["is_field_value"] is False


# ==========================================================================
# 6. NEGATIVE CONTROL — DEC-13, THE IDEMPOTENCY KEY
# ==========================================================================

def test_a_retry_with_the_SAME_client_request_key_returns_the_SAME_proposal(
    proposer, experiment
):
    """Contract **DEC-13**, driven as a real retry rather than asserted about.

    A retrying MCP client must not duplicate. The second call re-reads the etag first,
    because the first attempt advanced the record — which is itself part of the
    contract: the precondition is checked BEFORE the deduplication branch, so a client
    replaying its original etag meets ``412`` and re-reads.
    """
    first = propose(proposer, experiment)
    assert first["deduplicated"] is False

    second = propose(proposer, experiment)
    assert second["deduplicated"] is True
    assert second["proposal"]["proposal_id"] == first["proposal"]["proposal_id"]

    assert len(stored(experiment.id).proposals) == 1


def test_a_DIFFERENT_client_request_key_makes_a_SECOND_proposal(proposer, experiment):
    """The negative control for the case above. A deduplicator that returned the first
    proposal for every request would pass it while breaking the feature."""
    first = propose(proposer, experiment)
    second = propose(proposer, experiment, client_request_key="mcp-test-key-2")
    assert second["deduplicated"] is False
    assert second["proposal"]["proposal_id"] != first["proposal"]["proposal_id"]
    assert len(stored(experiment.id).proposals) == 2


def test_the_key_is_REQUIRED_by_the_tool_though_it_is_OPTIONAL_over_http(
    proposer, experiment
):
    """The MCP boundary is deliberately narrower than the API it calls.

    A person clicking a button can see whether their proposal landed; a model retrying a
    timed-out call cannot. Both halves are asserted, because "narrower than the API" is
    only true if the API is still wider — and the HTTP route must not have been
    tightened by this slice.
    """
    envelope = rpc(
        proposer,
        "tools/call",
        {
            "name": "isaac_propose_field_value",
            "arguments": {
                "experiment_id": experiment.id,
                "if_match": etag_of(proposer, experiment.id),
                "note_id": experiment.notes[0].id,
                "target_field_path": RUN_PATH,
                "proposed_value": 301.0,
                "rule": RULE,
                "run_id": experiment.runs[0].id,
            },
        },
    )
    assert envelope["error"]["code"] == INVALID_PARAMS
    assert "client_request_key" in envelope["error"]["message"]
    assert "client_request_key" not in routes._PROPOSAL_CREATE_KEYS - {"client_request_key"}
    # The HTTP route still accepts a body without it, which is what "narrower" means.
    assert "client_request_key" in routes._PROPOSAL_CREATE_KEYS


def test_the_tool_declares_idempotent_and_earns_it(proposer, experiment):
    """``idempotentHint: true`` is published to clients, so it must be true.

    ``isaac_create_run`` declares ``false`` for the opposite reason — it has no such key
    — and the pair is what makes this annotation informative rather than decorative.
    """
    assert TOOLS["isaac_propose_field_value"].annotations()["idempotentHint"] is True
    assert TOOLS["isaac_create_run"].annotations()["idempotentHint"] is False
    propose(proposer, experiment)
    rev_after_first = stored(experiment.id).rev
    propose(proposer, experiment)
    assert stored(experiment.id).rev == rev_after_first, (
        "a deduplicated create advanced the record, so the retry was not a no-op"
    )


# ==========================================================================
# 7. NEGATIVE CONTROL — DEC-2, ATTRIBUTION DOES NOT COLLAPSE
# ==========================================================================

def test_an_mcp_created_proposal_is_UNATTRIBUTED_and_names_no_human(
    proposer, experiment
):
    """Contract **DEC-2**: the two identities must never collapse.

    A proposal's ``trust_basis`` describes the act that CREATED it, and the accepting
    scientist's identity is a separate field on a separate transition. This build
    establishes no actor at create time — creating a proposal writes no scientific value
    — so the honest answer is ``unattributed`` with a ``null`` subject, and a
    placeholder name would be worse than nothing.
    """
    created = propose(proposer, experiment)["proposal"]
    assert created["subject"] is None
    assert created["trust_basis"] == "unattributed"

    held = stored(experiment.id).proposals[0]
    assert held.subject is None
    assert held.attributed is False
    # THE ACCEPT TRANSITION'S IDENTITY IS A DIFFERENT FIELD ENTIRELY, and it is empty
    # because nothing has accepted: `accepted_by` is read off the accept act, not off
    # the proposal, so the two can never be read as one.
    full = payload(
        proposer,
        "isaac_get_proposal",
        experiment_id=experiment.id,
        proposal_id=created["proposal_id"],
    )["data"]["proposal"]
    assert full["accepted_by"] is None
    assert full["trust_basis"] == "unattributed"


def test_no_verified_edge_assertion_can_be_minted_by_this_path(proposer, experiment):
    """The strong form: nothing an MCP caller sends becomes an attribution.

    The tool's own schema is what makes this structural — there is no argument by which
    a caller could name itself — and ``RESERVED_ARGUMENT_NAMES`` refuses the shapes
    somebody would reach for.
    """
    from isaac_api.mcp.tools import RESERVED_ARGUMENT_NAMES

    properties = set(TOOLS["isaac_propose_field_value"].input_schema["properties"])
    assert not properties & RESERVED_ARGUMENT_NAMES
    for invented in ("subject", "actor", "trust_basis", "uploaded_by"):
        envelope = rpc(
            proposer,
            "tools/call",
            {
                "name": "isaac_propose_field_value",
                "arguments": {
                    "experiment_id": experiment.id,
                    "if_match": etag_of(proposer, experiment.id),
                    "note_id": experiment.notes[0].id,
                    "target_field_path": RUN_PATH,
                    "proposed_value": 301.0,
                    "rule": RULE,
                    "run_id": experiment.runs[0].id,
                    "client_request_key": "k",
                    invented: "ada.lovelace",
                },
            },
        )
        assert envelope["error"]["code"] == INVALID_PARAMS, invented


# ==========================================================================
# 8. NEGATIVE CONTROL — DEC-7, THE DETAIL PAYLOAD DID NOT WIDEN
# ==========================================================================

def test_isaac_get_experiment_still_carries_no_proposals(proposer, experiment):
    """Contract **DEC-7**, restated over MCP after the surface widened.

    Adding dedicated proposal tools is a REVIEWED widening; adding a ``proposals`` key
    to the experiment detail payload would be an unreviewed one, because
    ``isaac_get_experiment`` reaches it and ``mcp/client.py`` is bound to the operation
    allowlist rather than to a response shape. The two are deliberately different acts,
    and this asserts the second did not happen alongside the first.
    """
    from isaac_api import proposals as proposals_module

    propose(proposer, experiment)
    detail = payload(proposer, "isaac_get_experiment", experiment_id=experiment.id)
    assert "proposals" not in detail["data"]
    # A BARE SUBSTRING SCAN WOULD FAIL FOR THE WRONG REASON, and saying so is part of
    # the test: this fixture's own TITLE is "MCP proposals fixture". What must be absent
    # is the state key and every id this feature mints — the same distinction
    # `test_ingestion_proposals` draws for `system.configuration.proposal_id`.
    for rendered in (
        json.dumps(detail),
        json.dumps(payload(proposer, "isaac_list_experiments")["data"]),
    ):
        assert f'"{proposals_module.STATE_KEY}":' not in rendered
        for held in stored(experiment.id).proposals:
            assert held.proposal_id not in rendered


# ==========================================================================
# 9. NEGATIVE CONTROL — I7, WORKED-EXAMPLE ISOLATION
# ==========================================================================

def test_a_proposal_made_inside_a_worked_example_is_invisible_outside_it(app):
    """Contract **I7**, which ``CLAUDE.md`` §15 calls the invariant this feature must
    not break, driven through MCP in both directions.

    The session binding is written from the PRINCIPAL and there is no tool argument that
    can change it (``RESERVED_ARGUMENT_NAMES`` refuses ``session_id``), so a tutorial
    proposal cannot be addressed from ordinary scope and vice versa.
    """
    session_id, ids = ws.create_tutorial_session()
    in_session = _server(app, Scope.READ, Scope.PROPOSALS_WRITE, session=session_id)
    outside = _server(app, Scope.READ, Scope.PROPOSALS_WRITE)

    # The worked-example record is not addressable at all from ordinary scope.
    result = call(outside, "isaac_list_proposals", experiment_id=ids[0])
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 404

    # A REAL IN-SESSION PROPOSAL. ~~This asserted `total == 0` and stopped.~~ — that
    # assertion was VACUOUS: it held over an empty set and would have passed
    # byte-identically if an in-session create had written into ordinary scope, which is
    # the direction the docstring claims to test. The property does hold; the test did
    # not measure it.
    session_note = ws.load_experiment(ids[0], session_id=session_id).notes
    if not session_note:
        exp_in_session = ws.load_experiment(ids[0], session_id=session_id)
        exp_in_session.capture_note(text=NOTE_TEXT, source="typed_note")
        exp_in_session.save_versioned()
    exp_in_session = ws.load_experiment(ids[0], session_id=session_id)
    created = payload(
        in_session,
        "isaac_propose_field_value",
        experiment_id=ids[0],
        if_match=etag_of(in_session, ids[0]),
        note_id=exp_in_session.notes[0].id,
        target_field_path=RECORD_PATH,
        proposed_value=RECORD_VALUE,
        rule=RULE,
        client_request_key="tutorial-isolation",
    )["data"]["proposal"]

    # It is there IN the session...
    listed = payload(in_session, "isaac_list_proposals", experiment_id=ids[0])["data"]
    assert listed["total"] == 1
    assert listed["proposals"][0]["proposal_id"] == created["proposal_id"]

    # ...and the ordinary-scope store does not hold it under any record. This is the
    # direction the old assertion never exercised.
    assert ws.load_experiment(ids[0]) is None
    for ordinary in ws.list_experiments():
        held = ws.load_experiment(ordinary.id)
        assert all(
            proposal.proposal_id != created["proposal_id"]
            for proposal in (held.proposals if held else [])
        ), ordinary.id

    # A tool cannot name a session: the argument is reserved and the schema is closed.
    envelope = rpc(
        outside,
        "tools/call",
        {
            "name": "isaac_list_proposals",
            "arguments": {"experiment_id": ids[0], "session_id": session_id},
        },
    )
    assert envelope["error"]["code"] == INVALID_PARAMS


# ==========================================================================
# 10. THE READS — bounded, honest about being bounded, and cursor-safe
# ==========================================================================

def test_the_list_is_a_WINDOW_and_says_so(proposer, experiment):
    """``GET .../proposals`` is bounded by default, unlike every other list this server
    exposes, and a tool that hid that would reproduce the silent truncation the bound
    exists to prevent."""
    for index in range(3):
        propose(proposer, experiment, client_request_key=f"k{index}")

    page = payload(
        proposer, "isaac_list_proposals", experiment_id=experiment.id, limit=2
    )["data"]
    assert page["total"] == 3
    assert page["returned"] == 2
    assert page["has_more"] is True
    assert page["next_cursor"] is not None

    rest = payload(
        proposer,
        "isaac_list_proposals",
        experiment_id=experiment.id,
        limit=2,
        after=page["next_cursor"],
    )["data"]
    assert rest["returned"] == 1
    assert rest["has_more"] is False
    assert rest["total"] == 3, "total must be what the record HOLDS, never what was returned"


def test_an_unknown_cursor_is_refused_rather_than_restarting_the_walk(
    proposer, experiment
):
    """Silently restarting would return the same window forever to a client that
    believed it was advancing — a wrong answer, which is worse than an error."""
    propose(proposer, experiment)
    body = refused(
        proposer,
        "isaac_list_proposals",
        experiment_id=experiment.id,
        after="0" * 26,
    )
    assert body["status"] == 422
    assert body["error"] == "unknown_cursor"


def test_the_state_filter_is_a_CLOSED_set_refused_before_a_request_is_built(
    proposer, experiment
):
    """The route's own ``Literal`` travels into the published schema, so a model sending
    a value the route would reject is told what the values ARE rather than handed a
    ``422`` that reads like a broken filter."""
    spec = TOOLS["isaac_list_proposals"].input_schema["properties"]["state"]
    assert set(spec["enum"]) == {"open", "accepted", "rejected", "superseded", "withdrawn"}
    envelope = rpc(
        proposer,
        "tools/call",
        {
            "name": "isaac_list_proposals",
            "arguments": {"experiment_id": experiment.id, "state": "pending"},
        },
    )
    assert envelope["error"]["code"] == INVALID_PARAMS
    assert "open" in envelope["error"]["message"]


def test_the_target_paths_are_published_as_a_closed_set_derived_from_the_route(
    proposer, experiment
):
    """A path this build cannot write is refused HERE, naming the permitted ones.

    Derived from ``routes.PROPOSAL_TARGET_PATHS`` at import, so it widens on its own the
    day one of the seven currently-unwritable paths gains a write route — and a
    transcribed copy could not.
    """
    spec = TOOLS["isaac_propose_field_value"].input_schema["properties"][
        "target_field_path"
    ]
    assert set(spec["enum"]) == set(routes.PROPOSAL_TARGET_PATHS)
    assert "maxLength" not in spec, "a closed set needs no length bound"

    envelope = rpc(
        proposer,
        "tools/call",
        {
            "name": "isaac_propose_field_value",
            "arguments": {
                "experiment_id": experiment.id,
                "if_match": etag_of(proposer, experiment.id),
                "note_id": experiment.notes[0].id,
                # One of the seven the contract names: a real official field this build
                # has no write route for.
                "target_field_path": "system.configuration.beam_current_mA",
                "proposed_value": 1,
                "rule": RULE,
                "client_request_key": "k",
            },
        },
    )
    assert envelope["error"]["code"] == INVALID_PARAMS
    assert stored(experiment.id).proposals == []


def test_the_change_feed_reports_the_proposal_and_carries_no_proposal_CONTENT(
    proposer, experiment
):
    """The feed is how an agent notices a person answered, and it is deliberately thin.

    A ``proposal`` entry says an entity is at a later version and what state it is in
    NOW. It carries no proposed value, no target path, no rule and no note text — read
    the proposal itself for those — and this asserts the absence rather than trusting
    the description that promises it.
    """
    start = payload(proposer, "isaac_get_changes", experiment_id=experiment.id)["data"]
    cursor = start["next_cursor"]
    assert "proposal" in start["kinds"]

    # A NON-NUMERIC VALUE, DELIBERATELY. The assertion below that "301" does not appear
    # in the entry is a ~0.07%-per-run flake against a 26-character Crockford-base32
    # id, which can legitimately contain the digits `301` in sequence. The proposal's
    # value is not what this test is about, so it is chosen not to collide.
    created = propose(
        proposer, experiment, proposed_value="vacuum", target_field_path=CONTEXT_PATH
    )["proposal"]

    page = payload(
        proposer, "isaac_get_changes", experiment_id=experiment.id, cursor=cursor
    )["data"]
    entries = {entry["kind"]: entry for entry in page["changes"]}
    assert "proposal" in entries, page
    entry = entries["proposal"]
    assert entry["entity_id"] == created["proposal_id"]
    assert entry["state"] == "open"
    rendered = json.dumps(entry)
    assert RULE not in rendered
    assert CONTEXT_PATH not in rendered
    assert "zarquon" not in rendered
    assert "vacuum" not in rendered


def test_a_cursor_from_ANOTHER_record_is_refused_rather_than_answered(
    proposer, experiment, app
):
    """A cursor is bound to one record and one workspace scope. Answering one from the
    wrong feed would be a wrong answer, which the route refuses in favour of an error."""
    other_draft, other_run = _split_full_draft()
    other = ws.create_experiment("Another record", {"kind": "synthetic"}, other_draft)
    other.add_run(label="Run A", draft=copy.deepcopy(other_run))
    other.save_versioned()

    foreign = payload(proposer, "isaac_get_changes", experiment_id=other.id)["data"][
        "next_cursor"
    ]
    body = refused(
        proposer,
        "isaac_get_changes",
        experiment_id=experiment.id,
        cursor=foreign,
    )
    assert body["status"] == 422
    assert body["data"]["reason"] == "wrong_feed"


def test_an_oversized_cursor_is_refused_before_a_request_is_built(proposer, experiment):
    """The reviewed bound at this boundary, exercised. The failure it replaces was
    measured on another parameter: a 60 KB value forwarded, echoed back in a refusal
    body, and past ~64 KB failing URL construction as an unhandled error."""
    envelope = rpc(
        proposer,
        "tools/call",
        {
            "name": "isaac_get_changes",
            "arguments": {"experiment_id": experiment.id, "cursor": "x" * 257},
        },
    )
    assert envelope["error"]["code"] == INVALID_PARAMS
    assert "256" in envelope["error"]["message"]


# ==========================================================================
# 11. THE ROUTE'S OWN REFUSALS REACH THE AGENT INTACT
# ==========================================================================

@pytest.mark.parametrize(
    "overrides,expected",
    (
        ({"note_id": "0" * 26}, "unknown_note"),
        ({"run_id": "0" * 26}, "unknown_run"),
        ({"rule": "   "}, "invalid_rule"),
        ({"target_field_path": RECORD_PATH, "run_id": None}, None),
    ),
)
def test_a_refused_create_stores_nothing_and_says_why(
    proposer, experiment, overrides, expected
):
    """The API's error bodies are already typed and carefully worded, so they are
    forwarded rather than restated — and nothing is written by any of them.

    The fourth case is not a refusal at all: ``system.technique`` is the one
    record-scoped target, so omitting ``run_id`` is CORRECT there. It is in the same
    parametrisation deliberately, as the control that stops the three refusals above
    from passing on a create route that refuses everything.
    """
    arguments = {k: v for k, v in overrides.items() if v is not None}
    if overrides.get("target_field_path") == RECORD_PATH:
        arguments["proposed_value"] = RECORD_VALUE
        result = payload(
            proposer,
            "isaac_propose_field_value",
            experiment_id=experiment.id,
            if_match=etag_of(proposer, experiment.id),
            note_id=experiment.notes[0].id,
            target_field_path=RECORD_PATH,
            proposed_value=RECORD_VALUE,
            rule=RULE,
            client_request_key="k",
        )
        assert result["data"]["proposal"]["target_field_path"] == RECORD_PATH
        assert len(stored(experiment.id).proposals) == 1
        return

    body = refused(
        proposer,
        "isaac_propose_field_value",
        **{
            "experiment_id": experiment.id,
            "if_match": etag_of(proposer, experiment.id),
            "note_id": experiment.notes[0].id,
            "target_field_path": RUN_PATH,
            "proposed_value": 301.0,
            "rule": RULE,
            "run_id": experiment.runs[0].id,
            "client_request_key": "k",
            **arguments,
        },
    )
    assert body["error"] == expected, body
    assert stored(experiment.id).proposals == []


def test_a_stale_etag_loses_the_race_and_writes_nothing(proposer, experiment):
    """The precondition is the record's, because a proposal lives in the record's own
    document — and it is checked BEFORE the deduplication branch, so a client cannot be
    answered ``200`` for a request that presented no current validator."""
    stale = etag_of(proposer, experiment.id)
    propose(proposer, experiment, client_request_key="first")
    body = refused(
        proposer,
        "isaac_propose_field_value",
        experiment_id=experiment.id,
        if_match=stale,
        note_id=experiment.notes[0].id,
        target_field_path=RUN_PATH,
        proposed_value=301.0,
        rule=RULE,
        run_id=experiment.runs[0].id,
        client_request_key="second",
    )
    assert body["status"] == 412
    assert len(stored(experiment.id).proposals) == 1


def test_the_wildcard_precondition_is_refused_before_a_request_is_built(
    proposer, experiment
):
    """``If-Match: *`` means "apply this whatever the record now says". The HTTP API
    accepts it deliberately; this layer does not, because its caller is a language model
    and a single character is a shorter path out of a retry loop than re-reading."""
    envelope = rpc(
        proposer,
        "tools/call",
        {
            "name": "isaac_propose_field_value",
            "arguments": {
                "experiment_id": experiment.id,
                "if_match": "*",
                "note_id": experiment.notes[0].id,
                "target_field_path": RUN_PATH,
                "proposed_value": 301.0,
                "rule": RULE,
                "run_id": experiment.runs[0].id,
                "client_request_key": "k",
            },
        },
    )
    # THE REFUSAL IS AN `isError` RESULT, NOT A JSON-RPC ERROR, because `McpServer`
    # catches `ApiRefusal` and reports it as the tool's own outcome. Asserted in the
    # shape it actually arrives in rather than in the shape a reader would guess.
    assert "error" not in envelope, envelope["error"]
    body = envelope["result"]["structuredContent"]
    assert envelope["result"]["isError"] is True, body
    assert body["error"] == "invalid_if_match", body
    assert stored(experiment.id).proposals == []


def test_a_structured_proposed_value_survives_the_argument_validator(
    proposer, experiment
):
    """``proposed_value`` is declared as a list of JSON types, and that list has to
    actually admit them — a schema saying ``string`` would refuse the numeric and
    structured values the writable paths hold.

    The control at the end is the one that matters: ``null`` is still refused, because a
    null would CLEAR the field if it were ever applied.
    """
    spec = TOOLS["isaac_propose_field_value"].input_schema["properties"]["proposed_value"]
    assert isinstance(spec["type"], list)
    assert set(spec["type"]) == {
        "string",
        "number",
        "integer",
        "boolean",
        "object",
        "array",
    }

    for index, value in enumerate((301.0, 301, "vacuum", True, {"a": 1}, [1, 2])):
        result = propose(
            proposer,
            experiment,
            proposed_value=value,
            client_request_key=f"typed-{index}",
        )
        assert result["deduplicated"] is False

    envelope = rpc(
        proposer,
        "tools/call",
        {
            "name": "isaac_propose_field_value",
            "arguments": {
                "experiment_id": experiment.id,
                "if_match": etag_of(proposer, experiment.id),
                "note_id": experiment.notes[0].id,
                "target_field_path": RUN_PATH,
                "proposed_value": None,
                "rule": RULE,
                "run_id": experiment.runs[0].id,
                "client_request_key": "null-case",
            },
        },
    )
    assert envelope["error"]["code"] == INVALID_PARAMS
