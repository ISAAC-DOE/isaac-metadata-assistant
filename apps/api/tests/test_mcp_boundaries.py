"""The negative controls: what the MCP server must NOT be able to do.

Each case here is written so that the way somebody would later break it — adding
a submit tool, letting a scope nest, reading a session id out of a tool argument,
making the unconfigured binding "helpfully" grant read access, importing the truth
core for convenience — turns this file red rather than turning a docstring stale.

Nothing here opens a network connection, reads real data, or touches a database.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api import mcp
from isaac_api.mcp import (
    Credential,
    DeploymentRefused,
    LocalLoopbackDeployment,
    McpServer,
    Scope,
    UnconfiguredDeployment,
    resolve_binding,
)
from isaac_api.mcp.client import ApiRefusal, AsgiApiClient
from isaac_api.mcp.deployment import (
    DEPLOYMENT_ENV,
    LOCAL_LOOPBACK,
    LOCAL_SCOPES_ENV,
    RESERVED_BINDING_NAMES,
)
from isaac_api.mcp.policy import (
    ALLOWED_METHODS,
    FORBIDDEN_PATH_TOKENS,
    FORBIDDEN_TOOL_TOKENS,
    OPERATIONS,
    PERMITTED_TOOL_NAMES,
    forbidden_tool_reason,
)
from isaac_api.mcp.server import DEPLOYMENT_UNCONFIGURED, INSUFFICIENT_SCOPE, INVALID_PARAMS
from isaac_api.mcp.tools import TOOLS, _validate_tool, registered_tool_names

MCP_PACKAGE = Path(mcp.__file__).parent

#: Everything this server must never be able to do, expressed as the tool names a
#: future author would reach for. The assertion is against the REGISTRY, so a tool
#: added under any of these names — or any name carrying one of their capability
#: tokens — fails here before it is ever exposed.
FORBIDDEN_TOOL_NAMES = (
    "isaac_submit_record",
    "isaac_submit",
    "submit_record",
    "isaac_finalize_record",
    "isaac_finalise_record",
    "isaac_publish_record",
    "isaac_export_record",
    "isaac_export",
    "isaac_delete_experiment",
    "isaac_delete_run",
    "isaac_remove_record",
    "isaac_purge_workspace",
    "isaac_reset_demo",
    "isaac_apply_migration",
    "isaac_migrate_database",
    "isaac_update_governance",
    "isaac_grant_scope",
    "isaac_revoke_scope",
    "isaac_approve_record",
    "isaac_drop_table",
    "isaac_truncate_records",
)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    for name in (DEPLOYMENT_ENV, LOCAL_SCOPES_ENV):
        monkeypatch.delenv(name, raising=False)
    from isaac_api.app import create_app

    return create_app()


def rpc(server, method, params=None, *, credential=None):
    message = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        message["params"] = params
    return asyncio.run(server.handle(message, credential=credential))


# ==========================================================================
# 1. No submit-like tool is reachable, and adding one fails this file
# ==========================================================================

def test_the_registry_is_exactly_the_permitted_set_in_both_directions():
    assert registered_tool_names() == PERMITTED_TOOL_NAMES
    assert len(PERMITTED_TOOL_NAMES) == 8


def test_no_forbidden_capability_is_registered_under_any_name():
    registered = registered_tool_names()
    for name in FORBIDDEN_TOOL_NAMES:
        assert name not in registered, f"{name!r} is registered as an MCP tool"
        assert forbidden_tool_reason(name) is not None, (
            f"{name!r} would be accepted by the policy gate — the capability-token "
            "set no longer covers it"
        )


def test_no_registered_tool_name_carries_a_forbidden_capability_token():
    for name in registered_tool_names():
        lowered = name.lower()
        for token in FORBIDDEN_TOOL_TOKENS:
            assert token not in lowered, f"{name!r} contains {token!r}"


def test_registering_a_submit_tool_raises_rather_than_being_ignored():
    """The gate is import-time, so the failure is an ImportError in production too.

    Mutation-checked: a `Tool` named `isaac_submit_record` was built and passed to
    `_validate_tool`, which raised. Deleting the `forbidden_tool_reason` call from
    `_validate_tool` makes this case green and every other case in this file stay
    green, which is why the case exists.
    """
    from isaac_api.mcp.tools import Tool

    async def _handler(ctx, args):  # pragma: no cover - never invoked
        raise AssertionError("unreachable")

    forbidden = Tool(
        name="isaac_submit_record",
        title="Submit",
        description="",
        scope=Scope.DRAFT_WRITE,
        operation_ids=("create_run",),
        input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        handler=_handler,
        read_only=False,
        idempotent=False,
    )
    with pytest.raises(RuntimeError, match="forbidden capability token 'submit'"):
        _validate_tool(forbidden)


def test_the_operation_allowlist_cannot_express_a_deletion_or_a_finalisation():
    assert "DELETE" not in ALLOWED_METHODS
    assert "PUT" not in ALLOWED_METHODS
    for operation in OPERATIONS.values():
        assert operation.method in ALLOWED_METHODS
        lowered = operation.path_template.lower()
        for token in FORBIDDEN_PATH_TOKENS:
            assert token not in lowered, f"{operation.id} targets {token!r}"


def test_every_mutating_operation_costs_the_write_scope_and_needs_a_precondition():
    for operation in OPERATIONS.values():
        if operation.mutates:
            assert operation.scope is Scope.DRAFT_WRITE
            assert operation.requires_if_match


def test_a_scope_named_submit_cannot_be_expressed_at_all():
    """There is no value of :class:`Scope` that means "may finalise".

    This is the structural half of "no Submit": even if a tool existed, no
    deployment could grant it a permission, because the permission is an enum
    member and the enum has two.
    """
    assert {s.value for s in Scope} == {"isaac:read", "isaac:draft.write"}
    from isaac_api.mcp.policy import parse_scope

    for pretender in ("isaac:submit", "submit", "isaac:admin", "*", "isaac:export"):
        assert parse_scope(pretender) is None


# ==========================================================================
# 2. A read-scope caller cannot invoke a write tool
# ==========================================================================

def _reader(app, session_id):
    return McpServer(
        app,
        binding=LocalLoopbackDeployment(
            scopes=frozenset({Scope.READ}), tutorial_session_id=session_id
        ),
    )


def test_a_read_scope_caller_is_refused_every_write_tool(app):
    session_id, _ = ws.create_tutorial_session()
    reader = _reader(app, session_id)
    listed = {t["name"] for t in rpc(reader, "tools/list")["result"]["tools"]}

    for name, tool in TOOLS.items():
        if tool.scope is not Scope.DRAFT_WRITE:
            continue
        assert name not in listed
        envelope = rpc(reader, "tools/call", {"name": name, "arguments": {}})
        assert envelope["error"]["code"] == INSUFFICIENT_SCOPE, name


def test_a_caller_cannot_grant_itself_a_scope_in_the_request(app):
    """Identity and permissions are the server's to state, never the caller's."""
    session_id, ids = ws.create_tutorial_session()
    reader = _reader(app, session_id)
    envelope = rpc(
        reader,
        "tools/call",
        {
            "name": "isaac_create_run",
            "arguments": {"experiment_id": ids[0], "if_match": '"x.0"'},
            "scopes": ["isaac:read", "isaac:draft.write"],
        },
    )
    assert envelope["error"]["code"] == INVALID_PARAMS
    assert "cannot be asserted by a caller" in envelope["error"]["message"]


def test_the_write_scope_does_not_imply_the_read_scope(app):
    session_id, _ = ws.create_tutorial_session()
    write_only = McpServer(
        app,
        binding=LocalLoopbackDeployment(
            scopes=frozenset({Scope.DRAFT_WRITE}), tutorial_session_id=session_id
        ),
    )
    envelope = rpc(write_only, "tools/call", {"name": "isaac_list_experiments", "arguments": {}})
    assert envelope["error"]["code"] == INSUFFICIENT_SCOPE


# ==========================================================================
# 3. A tool cannot escape tutorial-session isolation
# ==========================================================================

def test_a_session_bound_server_cannot_see_an_ordinary_workspace_record(app):
    from fastapi.testclient import TestClient

    http = TestClient(app)
    created = http.post("/api/experiments", json={"title": "An ordinary record"})
    assert created.status_code == 201, created.text
    ordinary_id = created.json()["id"]

    session_id, _ = ws.create_tutorial_session()
    reader = _reader(app, session_id)

    listed = rpc(reader, "tools/call", {"name": "isaac_list_experiments", "arguments": {}})
    ids = {
        row["id"]
        for row in listed["result"]["structuredContent"]["data"]["experiments"]
    }
    assert ordinary_id not in ids

    fetched = rpc(
        reader,
        "tools/call",
        {"name": "isaac_get_experiment", "arguments": {"experiment_id": ordinary_id}},
    )["result"]
    assert fetched["isError"] is True
    assert fetched["structuredContent"]["status"] == 404


def test_an_ordinary_server_cannot_see_a_sessions_example_records(app):
    session_id, ids = ws.create_tutorial_session()
    ordinary = McpServer(
        app, binding=LocalLoopbackDeployment(scopes=frozenset({Scope.READ}))
    )
    fetched = rpc(
        ordinary,
        "tools/call",
        {"name": "isaac_get_experiment", "arguments": {"experiment_id": ids[0]}},
    )["result"]
    assert fetched["isError"] is True
    assert fetched["structuredContent"]["status"] == 404


def test_no_tool_declares_an_argument_by_which_a_scope_could_be_named():
    from isaac_api.mcp.tools import RESERVED_ARGUMENT_NAMES

    for tool in TOOLS.values():
        declared = set(tool.input_schema.get("properties", {}))
        assert not (declared & RESERVED_ARGUMENT_NAMES), tool.name


def test_the_session_header_is_written_from_the_principal_and_from_nowhere_else():
    """``AsgiApiClient`` takes the session at construction; no method can change it.

    Mutation-checked: adding a ``tutorial_session_id`` key to ``_render_headers``'s
    inputs is impossible without changing the signature, and the signature is what
    this asserts.
    """
    signature = inspect.signature(AsgiApiClient.call)
    assert set(signature.parameters) == {
        "self",
        "operation_id",
        "path_params",
        "query",
        "json_body",
        "if_match",
    }
    header_signature = inspect.signature(AsgiApiClient._render_headers)
    assert set(header_signature.parameters) == {"self", "operation", "if_match"}


# ==========================================================================
# 4. The unconfigured deployment boundary refuses honestly
# ==========================================================================

@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "enabled", "true", "public", "hosted", "authentik"]
    + list(RESERVED_BINDING_NAMES),
)
def test_every_value_that_is_not_a_registered_binding_resolves_to_unconfigured(value):
    env = {} if value is None else {DEPLOYMENT_ENV: value}
    binding = resolve_binding(env)
    assert isinstance(binding, UnconfiguredDeployment)
    assert binding.name == "unconfigured"


def test_a_misconfigured_scope_list_falls_back_to_unconfigured_not_to_read(app):
    """The failure mode that would otherwise be invisible.

    ``isaac:submit`` in the scope list must not produce a working read-only server
    that an operator then believes reflects what they wrote.
    """
    binding = resolve_binding(
        {DEPLOYMENT_ENV: LOCAL_LOOPBACK, LOCAL_SCOPES_ENV: "isaac:read,isaac:submit"}
    )
    assert isinstance(binding, UnconfiguredDeployment)
    assert "misconfigured" in binding.reason


def test_the_local_binding_default_grant_is_read_only():
    binding = resolve_binding({DEPLOYMENT_ENV: LOCAL_LOOPBACK})
    principal = binding.authenticate(None)
    assert principal.scopes == frozenset({Scope.READ})


def test_an_unconfigured_server_refuses_the_handshake_the_listing_and_every_call(app):
    server = McpServer(app, env={})
    for method, params in (
        ("initialize", {}),
        ("tools/list", None),
        ("tools/call", {"name": "isaac_list_experiments", "arguments": {}}),
    ):
        envelope = rpc(server, method, params)
        assert "result" not in envelope, method
        assert envelope["error"]["code"] == DEPLOYMENT_UNCONFIGURED, method
        data = envelope["error"]["data"]
        assert data["code"] == "deployment_unconfigured"
        assert [d["id"] for d in data["outstanding_decisions"]] == ["D1", "D2"]
        # It does not fabricate a challenge pointing at an authorization server
        # that does not exist.
        assert data["challenge"]["resource_metadata"] is None


def test_the_unconfigured_refusal_names_the_deferral_rather_than_a_fault(app):
    envelope = rpc(McpServer(app, env={}), "initialize", {})
    message = envelope["error"]["message"]
    assert "no configured MCP deployment binding" in message
    assert "DEFERRED 2026-08-12" in str(envelope["error"]["data"])


def test_a_reserved_binding_name_is_a_placeholder_and_not_a_working_binding(app):
    for reserved in RESERVED_BINDING_NAMES:
        server = McpServer(app, env={DEPLOYMENT_ENV: reserved})
        envelope = rpc(server, "tools/list")
        assert envelope["error"]["code"] == DEPLOYMENT_UNCONFIGURED
        assert envelope["error"]["data"]["reason"] == "reserved_pending_decision"


def test_the_loopback_binding_refuses_a_credential_rather_than_pretending_to_check_it():
    binding = LocalLoopbackDeployment()
    with pytest.raises(DeploymentRefused) as raised:
        binding.authenticate(Credential(scheme="Bearer", token="s3cret-value"))
    assert raised.value.code == "credential_not_verifiable"
    assert "s3cret-value" not in str(raised.value.data)


def test_a_refusal_never_echoes_the_credential_over_the_wire(app):
    envelope = rpc(
        McpServer(app, env={}),
        "initialize",
        {},
        credential=Credential(scheme="Bearer", token="s3cret-value"),
    )
    assert "s3cret-value" not in str(envelope)


def test_no_mcp_transport_is_mounted_on_the_default_application(app):
    """The default deployment registers no MCP route. THIS TEST HAS BEEN REPLACED.

    Its previous form asserted that the application had no MCP path at all, and
    carried the instruction: *"If a future slice adds a Streamable HTTP transport
    this test must be replaced by one that asserts the transport is authenticated
    — not deleted."* That slice has landed (``isaac_api.mcp.transport``), and this
    is the replacement, narrowed to the claim that is still true and still worth
    holding: with ``ISAAC_MCP_DEPLOYMENT`` unset — which the ``app`` fixture
    guarantees — nothing is mounted.

    Absence, not refusal, is the assertion. A path that exists and answers 403
    still advertises that ISAAC speaks MCP.

    The other half of the instruction — that the transport, WHEN mounted, is
    gated — lives in ``apps/api/tests/test_mcp_transport.py``: the loopback peer
    check, the proxy-header and cross-origin refusals, the credential refusal, the
    per-call scope check, and four negative controls that disable one guard each
    and assert the behaviour changes.
    """
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any("mcp" in path.lower() for path in paths)
    assert not any("mcp" in path.lower() for path in app.openapi()["paths"])


# ==========================================================================
# 5. The client is the last gate: nothing reaches a route off the allowlist
# ==========================================================================

def test_the_client_refuses_an_operation_that_is_not_in_the_allowlist(app):
    client = AsgiApiClient(app)
    for pretender in ("export", "post_export", "demo_reset", "delete_experiment"):
        with pytest.raises(ApiRefusal) as raised:
            asyncio.run(client.call(pretender))
        assert raised.value.code == "operation_not_allowlisted"


def test_the_client_refuses_a_path_parameter_it_would_have_had_to_escape(app):
    client = AsgiApiClient(app)
    for hostile in ("../../etc/passwd", "abc/../../x", "%2e%2e%2f", "a b", "a\nb", ""):
        with pytest.raises(ApiRefusal) as raised:
            asyncio.run(
                client.call("get_experiment", path_params={"experiment_id": hostile})
            )
        assert raised.value.code == "invalid_path_parameter"


def test_the_client_refuses_an_if_match_carrying_a_header_injection(app):
    client = AsgiApiClient(app)
    with pytest.raises(ApiRefusal) as raised:
        asyncio.run(
            client.call(
                "create_run",
                path_params={"experiment_id": "01SYNTHXANESSEED0000000001"},
                if_match='"x.0"\r\nX-Isaac-Tutorial-Session: elsewhere',
            )
        )
    assert raised.value.code == "invalid_if_match"


def test_the_client_refuses_a_query_parameter_the_operation_does_not_declare(app):
    client = AsgiApiClient(app)
    with pytest.raises(ApiRefusal) as raised:
        asyncio.run(
            client.call(
                "list_runs",
                path_params={"experiment_id": "01SYNTHXANESSEED0000000001"},
                query={"include_deleted": True},
            )
        )
    assert raised.value.code == "unsupported_query_parameter"


# ==========================================================================
# 6. Source scan: the MCP module does not reach the truth path
# ==========================================================================

def _mcp_sources() -> list[Path]:
    sources = sorted(MCP_PACKAGE.glob("*.py"))
    assert len(sources) >= 5, "the MCP package source scan found almost nothing"
    return sources


def test_nothing_in_the_mcp_package_imports_the_truth_path():
    """``CLAUDE.md`` §13, held mechanically.

    The MCP layer reaches ISAAC only through ISAAC's own HTTP routes, which keep
    every gate they have. Importing ``isaac_records`` here would let a tool call a
    validator, an exporter or a writer directly, around the route that decides
    whether it may.
    """
    forbidden_roots = ("isaac_records", "graphify")
    offences = []
    for path in _mcp_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for root in forbidden_roots:
                    if name == root or name.startswith(root + "."):
                        offences.append(f"{path.name}: {name}")
    assert offences == [], f"the MCP package imports the truth path: {offences}"


def test_the_mcp_package_adds_no_third_party_dependency():
    """Zero new dependencies was a constraint, so it is asserted rather than trusted.

    ``httpx`` and ``fastapi``/``starlette`` are already declared in
    ``pyproject.toml``'s ``[api]`` extra; anything else appearing here is a new
    dependency arriving without a decision.
    """
    permitted_third_party = {"httpx"}
    stdlib_or_local: set[str] = set()
    for path in _mcp_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                stdlib_or_local.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                stdlib_or_local.add(node.module.split(".")[0])
    import sys

    unexpected = {
        name
        for name in stdlib_or_local
        if name not in sys.stdlib_module_names
        and name not in permitted_third_party
        and name != "isaac_api"
    }
    assert unexpected == set(), f"unexpected third-party imports: {sorted(unexpected)}"


def test_no_mcp_module_reads_the_environment_except_the_deployment_boundary():
    """Configuration is one seam, so "fail closed" has one place to be got right."""
    for path in _mcp_sources():
        if path.name == "deployment.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "os.environ" not in source, path.name
        assert "getenv" not in source, path.name
