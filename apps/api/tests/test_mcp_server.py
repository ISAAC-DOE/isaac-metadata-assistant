"""The MCP tool server, exercised end to end against the real application.

Every case here drives ``McpServer.handle`` with a JSON-RPC message and lets the
call land on the real FastAPI router, the real dependencies and the real
precondition machinery, in process, over ``httpx.ASGITransport``. No network is
opened and no credential exists: the deployment binding used throughout is
``local-loopback``, which authenticates nobody and refuses a credential outright.

Every tool gets three cases, which is the shape the slice was specified in:

* a **happy path** that asserts on real content, not merely on a 200;
* a **refusal** — either the API's own typed refusal surfacing as an ``isError``
  result, or this layer refusing before a request is built;
* **scope enforcement** — the same call, denied, from a caller the deployment did
  not grant the scope to.

The scope cases deliberately use a principal granted ONLY the write scope to test
read tools, and one granted only the read scope to test write tools. That is what
pins ``Scope.DRAFT_WRITE`` not implying ``Scope.READ``: if the scopes ever start
nesting, half of these go green while claiming to prove a denial.

Everything is synthetic — the committed seed drafts inside a worked-example
session. Nothing here reads real data and nothing connects to a database.
"""

from __future__ import annotations

import asyncio

import pytest

import isaac_api.workspace as ws
from isaac_api.mcp import (
    LocalLoopbackDeployment,
    McpServer,
    Scope,
)
from isaac_api.mcp.server import (
    INSUFFICIENT_SCOPE,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
)

RUN_LEVEL_FIELD = "context.temperature_K"
#: The already-answered asset in the ready seed's completed draft, and a new
#: well-formed sha256 that the system never invents (see ``test_edit_field.py``).
RAW_URI = "ssrl-archive://BL15-2/2099_run_000/raw/"
NEW_SHA = "f" * 64


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def session_id(app) -> str:
    """A worked-example session holding the five committed example records."""
    sid, _ids = ws.create_tutorial_session()
    return sid


def _server(app, session_id, *scopes: Scope) -> McpServer:
    return McpServer(
        app,
        binding=LocalLoopbackDeployment(
            scopes=frozenset(scopes), tutorial_session_id=session_id
        ),
    )


@pytest.fixture()
def reader(app, session_id) -> McpServer:
    return _server(app, session_id, Scope.READ)


@pytest.fixture()
def writer(app, session_id) -> McpServer:
    return _server(app, session_id, Scope.READ, Scope.DRAFT_WRITE)


@pytest.fixture()
def write_only(app, session_id) -> McpServer:
    """Granted the write scope and NOT the read scope. Proves the two are separate."""
    return _server(app, session_id, Scope.DRAFT_WRITE)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def rpc(server: McpServer, method: str, params: dict | None = None, *, mid: int = 1):
    """One JSON-RPC round trip. Returns the whole envelope."""
    message = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        message["params"] = params
    return asyncio.run(server.handle(message))


def call(server: McpServer, name: str, **arguments) -> dict:
    """A ``tools/call`` that must not produce a JSON-RPC error. Returns the result."""
    envelope = rpc(server, "tools/call", {"name": name, "arguments": arguments})
    assert "error" not in envelope, envelope["error"]
    return envelope["result"]


def payload(server: McpServer, name: str, **arguments) -> dict:
    result = call(server, name, **arguments)
    assert result["isError"] is False, result["structuredContent"]
    return result["structuredContent"]


def denied(server: McpServer, name: str, **arguments) -> dict:
    """A ``tools/call`` that must be refused by the SCOPE check. Returns the error."""
    envelope = rpc(server, "tools/call", {"name": name, "arguments": arguments})
    assert "error" in envelope, envelope
    assert envelope["error"]["code"] == INSUFFICIENT_SCOPE, envelope["error"]
    return envelope["error"]


def etag_of(reader: McpServer, experiment_id: str) -> str:
    return payload(reader, "isaac_get_experiment", experiment_id=experiment_id)["etag"]


def a_record(reader: McpServer) -> str:
    rows = payload(reader, "isaac_list_experiments")["data"]["experiments"]
    return rows[0]["id"]


def new_run(writer: McpServer, experiment_id: str, label: str = "Run A") -> dict:
    got = payload(
        writer,
        "isaac_create_run",
        experiment_id=experiment_id,
        if_match=etag_of(writer, experiment_id),
        label=label,
    )
    return got["data"]["run"]


# ==========================================================================
# protocol surface
# ==========================================================================

def test_initialize_advertises_only_tools_and_names_the_granted_scopes(reader):
    result = rpc(reader, "initialize", {})["result"]
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert set(result["capabilities"]) == {"tools"}
    assert result["_isaac"]["grantedScopes"] == ["isaac:read"]
    assert result["_isaac"]["workspaceScope"] == "worked-example-session"


def test_sampling_is_not_advertised_because_mcp_is_one_way(reader):
    """The audit's §1 finding, held as a protocol assertion.

    Sampling is the single MCP feature by which a server asks the client's model
    to infer something. Advertising it would make ISAAC an inference consumer
    through the back door of a capability nobody read.
    """
    capabilities = rpc(reader, "initialize", {})["result"]["capabilities"]
    assert "sampling" not in capabilities
    assert "elicitation" not in capabilities


def test_ping_answers_and_an_unknown_method_is_a_json_rpc_error(reader):
    assert rpc(reader, "ping")["result"] == {}
    error = rpc(reader, "tools/subscribe")["error"]
    assert error["code"] == METHOD_NOT_FOUND


@pytest.mark.parametrize("method", ["notifications/initialized", "ping", "tools/list"])
def test_a_notification_produces_no_response_at_all(reader, method):
    """No id means no answer — not a result, and not an error either."""
    assert asyncio.run(reader.handle({"jsonrpc": "2.0", "method": method})) is None


def test_an_unexpected_failure_is_a_json_rpc_error_that_says_nothing_about_itself(
    app, session_id, monkeypatch
):
    """The protocol loop must not raise, and must not narrate what went wrong.

    A driver message, a filesystem path or a stack frame reaching a model is a
    leak, and the ISAAC routes already refuse to interpolate an exception for the
    same reason. Verified by breaking the client rather than by mocking the
    server's own error path.
    """
    from isaac_api.mcp import client as client_module

    async def _explode(*args, **kwargs):
        raise RuntimeError("postgres://user:hunter2@db.internal:5432 exploded")

    monkeypatch.setattr(client_module.AsgiApiClient, "call", _explode)
    server = _server(app, session_id, Scope.READ)
    envelope = rpc(server, "tools/call", {"name": "isaac_list_experiments", "arguments": {}})
    assert envelope["error"]["code"] == INTERNAL_ERROR
    assert "hunter2" not in str(envelope)
    assert "postgres" not in str(envelope)


def test_tools_list_is_filtered_by_the_callers_scopes(reader, writer):
    read_only = {t["name"] for t in rpc(reader, "tools/list")["result"]["tools"]}
    both = {t["name"] for t in rpc(writer, "tools/list")["result"]["tools"]}
    assert "isaac_create_run" not in read_only
    assert "isaac_update_draft" not in read_only
    assert {"isaac_create_run", "isaac_update_draft"} <= both
    assert len(both) == 8


def test_every_descriptor_states_the_scope_a_call_will_cost(writer):
    for tool in rpc(writer, "tools/list")["result"]["tools"]:
        assert tool["_isaac"]["requiredScope"] in {"isaac:read", "isaac:draft.write"}
        assert tool["inputSchema"]["additionalProperties"] is False


# ==========================================================================
# 1. isaac_list_experiments
# ==========================================================================

def test_list_experiments_returns_the_sessions_example_records(reader):
    body = payload(reader, "isaac_list_experiments")
    assert body["status"] == 200
    rows = body["data"]["experiments"]
    assert len(rows) == 5
    assert all({"id", "title", "status", "pending_count"} <= set(r) for r in rows)


def test_list_experiments_refuses_an_argument_it_does_not_declare(reader):
    error = rpc(
        reader, "tools/call", {"name": "isaac_list_experiments", "arguments": {"all": True}}
    )["error"]
    assert error["code"] == INVALID_PARAMS
    assert "unknown argument" in error["message"]


def test_list_experiments_is_denied_without_the_read_scope(write_only):
    error = denied(write_only, "isaac_list_experiments")
    assert error["data"]["requiredScope"] == "isaac:read"
    assert error["data"]["grantedScopes"] == ["isaac:draft.write"]


# ==========================================================================
# 2. isaac_get_experiment
# ==========================================================================

def test_get_experiment_returns_detail_and_the_records_own_etag(reader):
    experiment_id = a_record(reader)
    body = payload(reader, "isaac_get_experiment", experiment_id=experiment_id)
    assert body["data"]["id"] == experiment_id
    assert body["etag"] and body["etag"].startswith('"')


def test_get_experiment_reports_an_unknown_id_as_the_apis_own_refusal(reader):
    result = call(reader, "isaac_get_experiment", experiment_id="01NOTAREALRECORDID00000000")
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 404
    assert result["structuredContent"]["error"] == "experiment_not_found"


def test_get_experiment_is_denied_without_the_read_scope(write_only, reader):
    denied(write_only, "isaac_get_experiment", experiment_id=a_record(reader))


# ==========================================================================
# 3. isaac_list_runs
# ==========================================================================

def test_list_runs_pages_and_reports_total_returned_and_offset(writer):
    experiment_id = a_record(writer)
    new_run(writer, experiment_id, "Run A")
    new_run(writer, experiment_id, "Run B")

    first = payload(writer, "isaac_list_runs", experiment_id=experiment_id, limit=1)["data"]
    assert first["total"] == 2 and first["returned"] == 1 and first["offset"] == 0
    second = payload(
        writer, "isaac_list_runs", experiment_id=experiment_id, limit=1, offset=1
    )["data"]
    assert second["total"] == 2 and second["returned"] == 1 and second["offset"] == 1
    assert first["runs"][0]["id"] != second["runs"][0]["id"]


def test_list_runs_exposes_exactly_the_filters_the_route_implements():
    """The tool's filter set is DERIVED from the route, and must equal it.

    A hand-written list would drift in the dangerous direction: FastAPI ignores an
    unknown query parameter, so advertising a filter the route has not got yet
    would return an unfiltered list that a caller believes is filtered. This is
    the assertion that keeps the two identical, whichever way the route moves.
    """
    import typing

    from isaac_api.mcp.policy import OPERATIONS
    from isaac_api.routes import list_runs

    # `get_type_hints`, not `inspect.signature(...).annotation`: `routes.py` uses
    # `from __future__ import annotations`, so the raw annotations are STRINGS and
    # a naive reader finds no parameters at all — which would make this test pass
    # by measuring nothing.
    hints = typing.get_type_hints(list_runs, include_extras=True)
    route_params = {
        name
        for name, annotation in hints.items()
        if hasattr(annotation, "__metadata__")
        and any(type(m).__name__ == "Query" for m in annotation.__metadata__)
    }
    assert route_params, "no Query parameters were found on the run-list route"
    assert OPERATIONS["list_runs"].query_parameters == frozenset(route_params)
    # The bounded page is present at this commit; the assertion above is what
    # carries the relevance filters in when they land.
    assert {"limit", "offset"} <= route_params


def test_list_runs_refuses_a_filter_the_route_does_not_have(reader):
    """`q` is not on this route at this commit, so the tool must refuse it here.

    This is the case that distinguishes "refused" from "ignored". Passing it
    through would reach FastAPI, be dropped, and return every run under a claim of
    a filtered search.
    """
    from isaac_api.mcp.policy import OPERATIONS

    if "q" in OPERATIONS["list_runs"].query_parameters:
        pytest.skip("the run-list route implements `q` in this checkout")
    error = rpc(
        reader,
        "tools/call",
        {"name": "isaac_list_runs", "arguments": {"experiment_id": a_record(reader), "q": "cu"}},
    )["error"]
    assert error["code"] == INVALID_PARAMS


def test_list_runs_refuses_a_page_size_beyond_the_routes_own_bound(reader):
    from isaac_api.routes import RUN_PAGE_MAX

    error = rpc(
        reader,
        "tools/call",
        {
            "name": "isaac_list_runs",
            "arguments": {"experiment_id": a_record(reader), "limit": RUN_PAGE_MAX + 1},
        },
    )["error"]
    assert error["code"] == INVALID_PARAMS
    assert str(RUN_PAGE_MAX) in error["message"]


def test_list_runs_is_denied_without_the_read_scope(write_only, reader):
    denied(write_only, "isaac_list_runs", experiment_id=a_record(reader))


# ==========================================================================
# 4. isaac_get_run
# ==========================================================================

def test_get_run_returns_the_runs_own_etag_not_the_records(writer):
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    body = payload(writer, "isaac_get_run", experiment_id=experiment_id, run_id=run["id"])
    assert body["data"]["run"]["id"] == run["id"]
    assert body["etag"] == f'"{run["version"]}"'
    assert body["etag"] != etag_of(writer, experiment_id)


def test_get_run_reports_an_unknown_run_as_the_apis_own_refusal(reader):
    result = call(
        reader,
        "isaac_get_run",
        experiment_id=a_record(reader),
        run_id="01NOTAREALRUNID0000000000",
    )
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 404


def test_get_run_is_denied_without_the_read_scope(write_only, writer):
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    denied(write_only, "isaac_get_run", experiment_id=experiment_id, run_id=run["id"])


# ==========================================================================
# 5. isaac_create_run
# ==========================================================================

def test_create_run_adopts_the_records_run_level_science_and_advances_it(writer):
    """THE FIRST RUN IS NOT EMPTY ANY MORE, and the old claim is quoted because it was
    a deliberate assertion rather than an accident.

    It read: *"# EMPTY. No record-level value is copied down into a new run."* — and
    `assert run["fields"] == {}`. That was true, and it was the defect: `series`, `qc`,
    `assets`, `descriptors_outputs` and the run-level `context.*` / `timestamps.*`
    fields are read off the RUN at export, so a run that copied nothing meant adding one
    silently removed every evidenced value from the record it exports.

    What has NOT changed, and is asserted below, is the half the old comment was really
    protecting: no EXPERIMENT-level value is copied down. `attribution` is inherited by
    reference at read time, not duplicated onto the run, and a SECOND run copies nothing
    at all. See `apps/api/tests/test_run_seeding.py` for both halves.
    """
    experiment_id = a_record(writer)
    before = etag_of(writer, experiment_id)
    body = payload(
        writer,
        "isaac_create_run",
        experiment_id=experiment_id,
        if_match=before,
        label="Cu K-edge, 300 K",
    )
    assert body["status"] == 201
    run = body["data"]["run"]
    assert run["label"] == "Cu K-edge, 300 K"

    adopted = set(run["fields"])
    assert adopted, "the first run adopted nothing, so the record's science is lost"
    for path in adopted:
        assert ws.field_level(path) == ws.LEVEL_RUN, (
            f"{path} is not run-level and must not be copied onto a run"
        )
    assert etag_of(writer, experiment_id) != before


def test_create_run_with_a_stale_etag_is_refused_and_nothing_is_written(writer):
    experiment_id = a_record(writer)
    stale = etag_of(writer, experiment_id)
    new_run(writer, experiment_id, "First")  # moves the record past `stale`

    result = call(
        writer, "isaac_create_run", experiment_id=experiment_id, if_match=stale, label="Second"
    )
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 412
    listing = payload(writer, "isaac_list_runs", experiment_id=experiment_id)["data"]
    assert listing["total"] == 1


def test_create_run_without_an_if_match_never_reaches_the_api(writer):
    """Refused by the schema, before a request is built.

    The API would answer ``428`` and that would be correct too — but a write tool
    whose precondition is optional is a write tool an agent will call without one.
    """
    error = rpc(
        writer,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": a_record(writer)}},
    )["error"]
    assert error["code"] == INVALID_PARAMS
    assert "if_match" in error["message"]


def test_create_run_is_denied_to_a_read_only_caller(reader):
    experiment_id = a_record(reader)
    error = denied(
        reader, "isaac_create_run", experiment_id=experiment_id, if_match=etag_of(reader, experiment_id)
    )
    assert error["data"]["requiredScope"] == "isaac:draft.write"
    # and nothing was created
    assert payload(reader, "isaac_list_runs", experiment_id=experiment_id)["data"]["total"] == 0


# ==========================================================================
# 6. isaac_update_draft
# ==========================================================================

def test_update_draft_writes_a_run_level_field_with_the_runs_etag(writer):
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    body = payload(
        writer,
        "isaac_update_draft",
        experiment_id=experiment_id,
        run_id=run["id"],
        if_match=f'"{run["version"]}"',
        confirmed_by_user=True,
        fields={RUN_LEVEL_FIELD: 300.0},
    )
    assert body["operation"] == "update_run_draft"
    refreshed = payload(
        writer, "isaac_get_run", experiment_id=experiment_id, run_id=run["id"]
    )["data"]["run"]
    assert refreshed["fields"][RUN_LEVEL_FIELD]["value"] == 300.0


def test_update_draft_corrects_a_record_level_field_with_the_records_etag(writer):
    body = payload(
        writer,
        "isaac_update_draft",
        experiment_id=ws.SEED_READY_ID,
        if_match=etag_of(writer, ws.SEED_READY_ID),
        confirmed_by_user=True,
        fields={RAW_URI: NEW_SHA},
    )
    assert body["operation"] == "correct_record_field"
    assert body["data"]["invalidation"]["changed"] is True
    trail = payload(writer, "isaac_inspect_evidence", experiment_id=ws.SEED_READY_ID)["data"]
    values = {e["path"]: e["value"] for e in trail["evidence"]}
    assert values["assets:raw_scan_set"] == NEW_SHA


def test_update_draft_passes_a_false_confirmation_through_and_is_refused(writer):
    """The tool does not manufacture the confirmation, so the API refuses the write.

    Hard-coding ``confirmed_by_user: true`` here would have been one line and
    would have recorded a user confirmation that no user gave — for a value whose
    only support IS that confirmation.
    """
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    before_fields = dict(run["fields"])
    result = call(
        writer,
        "isaac_update_draft",
        experiment_id=experiment_id,
        run_id=run["id"],
        if_match=f'"{run["version"]}"',
        confirmed_by_user=False,
        fields={RUN_LEVEL_FIELD: 300.0},
    )
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "confirmation_required"
    refreshed = payload(
        writer, "isaac_get_run", experiment_id=experiment_id, run_id=run["id"]
    )["data"]["run"]
    # UNCHANGED, not empty. This asserted `== {}` and passed only because a new
    # run started empty; the first run now adopts the record's run-level science,
    # so "nothing was written" has to be measured against what was there BEFORE.
    # That is strictly the stronger claim — an empty comparison would also pass on
    # a run whose values had been wiped by the refused call.
    assert refreshed["fields"] == before_fields


def test_update_draft_refuses_a_field_path_that_is_not_run_level(writer):
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    result = call(
        writer,
        "isaac_update_draft",
        experiment_id=experiment_id,
        run_id=run["id"],
        if_match=f'"{run["version"]}"',
        confirmed_by_user=True,
        fields={"context.typo_K": 1},
    )
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 422


def test_update_draft_refuses_a_label_without_a_run_before_calling_anything(writer):
    result = call(
        writer,
        "isaac_update_draft",
        experiment_id=ws.SEED_READY_ID,
        if_match=etag_of(writer, ws.SEED_READY_ID),
        confirmed_by_user=True,
        fields={RAW_URI: NEW_SHA},
        label="not a record title",
    )
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "label_requires_run"


def test_update_draft_is_denied_to_a_read_only_caller(reader, writer):
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    before_fields = dict(run["fields"])
    denied(
        reader,
        "isaac_update_draft",
        experiment_id=experiment_id,
        run_id=run["id"],
        if_match=f'"{run["version"]}"',
        confirmed_by_user=True,
        fields={RUN_LEVEL_FIELD: 300.0},
    )
    refreshed = payload(
        reader, "isaac_get_run", experiment_id=experiment_id, run_id=run["id"]
    )["data"]["run"]
    # UNCHANGED, not empty. This asserted `== {}` and passed only because a new
    # run started empty; the first run now adopts the record's run-level science,
    # so "nothing was written" has to be measured against what was there BEFORE.
    # That is strictly the stronger claim — an empty comparison would also pass on
    # a run whose values had been wiped by the refused call.
    assert refreshed["fields"] == before_fields


# ==========================================================================
# 7. isaac_check_run
# ==========================================================================

def test_check_run_returns_both_verdicts_and_moves_no_version(writer):
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    before_record = etag_of(writer, experiment_id)
    before_run = payload(
        writer, "isaac_get_run", experiment_id=experiment_id, run_id=run["id"]
    )["etag"]

    body = payload(writer, "isaac_check_run", experiment_id=experiment_id, run_id=run["id"])
    assert set(body["data"]) >= {"ok", "draft", "official", "blockers", "checked_run_version"}
    assert body["data"]["checked_run_version"] == run["version"]

    assert etag_of(writer, experiment_id) == before_record
    after_run = payload(
        writer, "isaac_get_run", experiment_id=experiment_id, run_id=run["id"]
    )["etag"]
    assert after_run == before_run


def test_check_run_costs_only_the_read_scope_although_it_is_a_post(reader, writer):
    """A read that would otherwise have cost a write scope because of its verb.

    ``POST .../check`` writes nothing. Deriving the permission from the HTTP method
    would teach a read-only agent to ask for ``isaac:draft.write``, which is the
    opposite of least privilege.
    """
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    body = payload(reader, "isaac_check_run", experiment_id=experiment_id, run_id=run["id"])
    assert body["status"] == 200


def test_check_run_reports_an_unknown_run_as_the_apis_own_refusal(reader):
    result = call(
        reader,
        "isaac_check_run",
        experiment_id=a_record(reader),
        run_id="01NOTAREALRUNID0000000000",
    )
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 404


def test_check_run_is_denied_without_the_read_scope(write_only, writer):
    experiment_id = a_record(writer)
    run = new_run(writer, experiment_id)
    denied(write_only, "isaac_check_run", experiment_id=experiment_id, run_id=run["id"])


# ==========================================================================
# 8. isaac_inspect_evidence
# ==========================================================================

def test_inspect_evidence_returns_the_trail_with_its_cited_sources(reader):
    body = payload(reader, "isaac_inspect_evidence", experiment_id=ws.SEED_READY_ID)
    entries = body["data"]["evidence"]
    assert entries
    assert all("path" in e and "value" in e for e in entries)


def test_inspect_evidence_reports_an_unknown_record_as_the_apis_own_refusal(reader):
    result = call(reader, "isaac_inspect_evidence", experiment_id="01NOTAREALRECORDID00000000")
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 404


def test_inspect_evidence_is_denied_without_the_read_scope(write_only):
    denied(write_only, "isaac_inspect_evidence", experiment_id=ws.SEED_READY_ID)


# ==========================================================================
# determinism of the wire shape
# ==========================================================================

def test_the_text_block_and_the_structured_content_are_the_same_document(reader):
    import json

    result = call(reader, "isaac_list_experiments")
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


def test_an_ordinary_scope_server_sees_an_empty_workspace(app):
    """The same tools, bound to no session, see the ordinary workspace — which is
    empty on a fresh deployment and is not silently answered from the examples."""
    ordinary = McpServer(
        app, binding=LocalLoopbackDeployment(scopes=frozenset({Scope.READ}))
    )
    assert payload(ordinary, "isaac_list_experiments")["data"]["experiments"] == []


def test_the_api_key_deployment_surfaces_as_a_typed_refusal_not_a_leak(
    tmp_path, monkeypatch, session_id
):
    """When the app requires its own API key, the MCP layer says so and holds none.

    Plumbing ``ISAAC_UI_API_KEY`` into a second consumer would have made this test
    pass and would have decided D2 by accident.
    """
    monkeypatch.setenv("ISAAC_UI_API_KEY", "a-shared-secret-this-layer-must-not-hold")
    from isaac_api.app import create_app

    guarded = McpServer(
        create_app(),
        binding=LocalLoopbackDeployment(
            scopes=frozenset({Scope.READ}), tutorial_session_id=session_id
        ),
    )
    result = call(guarded, "isaac_list_experiments")
    assert result["isError"] is True
    body = result["structuredContent"]
    assert body["error"] == "upstream_unauthenticated"
    assert "a-shared-secret-this-layer-must-not-hold" not in str(body)
