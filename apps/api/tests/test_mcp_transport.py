"""The transport: what is reachable, in which configuration, and what refuses.

Three things this file exists to hold, and each is written so that the way
somebody would break it turns the file red rather than turning a docstring stale:

1. **The default deployment mounts NOTHING.** Asserted against the route table
   AND the generated OpenAPI document AND a live request, because "there is no
   route" is a claim about the application, not about one path returning 404.
2. **`local-loopback` means loopback.** Asserted against the socket peer the ASGI
   scope reports, never a header — including the case where a loopback peer sent
   a forwarded header, which is refused, and the case where a browser origin off
   loopback posts to 127.0.0.1, which is the DNS-rebinding attack the MCP
   specification requires a local server to defend against.
3. **The transport inherits every gate and adds none of its own bypasses.** The
   CAS parity cases drive the SAME write over the transport and over plain HTTP
   and require the same refusal from both.

Four cases are deliberate NEGATIVE CONTROLS (``..._is_load_bearing``): each
disables one guard and asserts the behaviour changes. They are here because a
test that only ever sees the guard pass cannot distinguish "the guard refused" from
"nothing was reachable anyway".

ONE TEST BINDS A REAL SOCKET, AND IT IS THE POINT OF IT
=======================================================
*This paragraph used to read "Nothing here opens a socket", which was false.*
``test_a_real_client_over_a_real_loopback_socket_completes_a_session`` starts a
real ``uvicorn`` server on a real ``127.0.0.1`` TCP socket with an ephemeral port
and drives it with a real ``httpx`` client. That is deliberate and must stay: it
is the only case where ``scope["client"]`` is supplied by the KERNEL rather than
by the test, so it is the only evidence that the loopback guard reads a genuine
peer address instead of a tuple this file wrote.

The true claim, which is the one that was being protected: **nothing here leaves
this machine.** The bind is loopback, no DNS is resolved, no real data is read
and no database is touched. Every record is a committed synthetic example inside
an isolated worked-example session.

**Practical consequence:** that one test is the only one that can fail in a
restricted CI sandbox — one that forbids ``bind()``/``listen()`` even on
loopback, or that has no loopback interface. Every other test in this file drives
the ASGI application in process. If it fails there, check the sandbox before
concluding the transport regressed.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api.mcp.deployment import (
    DEPLOYMENT_ENV,
    LOCAL_LOOPBACK,
    LOCAL_SCOPES_ENV,
    LOCAL_SESSION_ENV,
    RESERVED_BINDING_NAMES,
    LocalLoopbackDeployment,
    Principal,
    UnconfiguredDeployment,
)
from isaac_api.mcp.policy import FORBIDDEN_PATH_TOKENS, OPERATIONS, PERMITTED_TOOL_NAMES, Scope
from isaac_api.mcp.server import (
    DEPLOYMENT_UNCONFIGURED,
    INSUFFICIENT_SCOPE,
    INVALID_PARAMS,
    MCP_PROTOCOL_VERSION,
)
from isaac_api.mcp.transport import (
    MAX_REQUEST_BYTES,
    MCP_PATH,
    TRANSPORT_REFUSED,
    is_loopback_host,
    mcp_transport_or_none,
)

#: A loopback peer, in the shape ASGI reports one. Passed to every ``TestClient``
#: that is meant to be served: the default is ``("testclient", 50000)``, which is
#: not an address at all and which this transport correctly refuses.
LOOPBACK_PEER = ("127.0.0.1", 51234)

#: The tool names a future author would reach for, and none of which may exist.
#: Duplicated from ``test_mcp_boundaries.py`` on purpose — that file asserts they
#: are not in the REGISTRY, this one asserts they are not reachable OVER THE WIRE,
#: and a shared constant would let one import hide the loss of the other.
FORBIDDEN_OVER_THE_WIRE = (
    "isaac_submit_record",
    "isaac_submit",
    "isaac_export_record",
    "isaac_export",
    "isaac_delete_experiment",
    "isaac_apply_migration",
    "isaac_update_governance",
    "isaac_reset_demo",
    "isaac_read_secret",
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """An isolated workspace with every MCP variable cleared. Nothing is mounted."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    for name in (DEPLOYMENT_ENV, LOCAL_SCOPES_ENV, LOCAL_SESSION_ENV):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def build_app():
    """A fresh application for the CURRENT environment.

    Deliberately not a fixture and deliberately re-imported per call: the mount
    decision is made inside ``create_app``, so a test that changes the environment
    has to build the app afterwards or it is testing the wrong configuration.
    """
    from isaac_api.app import create_app

    return create_app()


def configured(monkeypatch, *, scopes: str | None = None, session: str | None = None):
    """Turn the gate on, then build the app. Returns ``(app, client)``."""
    monkeypatch.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    if scopes is not None:
        monkeypatch.setenv(LOCAL_SCOPES_ENV, scopes)
    if session is not None:
        monkeypatch.setenv(LOCAL_SESSION_ENV, session)
    app = build_app()
    return app, TestClient(app, client=LOOPBACK_PEER)


BOTH_SCOPES = f"{Scope.READ.value},{Scope.DRAFT_WRITE.value}"


def rpc(client, method, params=None, *, mid=1, **kwargs):
    """One JSON-RPC round trip over HTTP. Returns the httpx response."""
    message = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        message["params"] = params
    return client.post(MCP_PATH, json=message, **kwargs)


def result_of(client, method, params=None):
    response = rpc(client, method, params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body["error"]
    return body["result"]


def call_tool(client, name, **arguments):
    return result_of(client, "tools/call", {"name": name, "arguments": arguments})


def structured(client, name, **arguments):
    return call_tool(client, name, **arguments)["structuredContent"]


# ==========================================================================
# 1. The default deployment mounts NOTHING
# ==========================================================================

def _all_route_paths(routes) -> list[str]:
    """Every registered path, INCLUDING the ones nested inside an included router.

    ``app.routes`` is six entries in this FastAPI version: the four documentation
    routes, one ``_IncludedRouter`` holding all forty-odd API routes, and whatever
    else was appended. A flat comprehension over ``app.routes`` therefore reports
    that ``/api/experiments`` does not exist — a false negative that would make
    every "no such route" assertion in this file vacuously true.
    """
    found: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            found.append(path)
        # Two different nesting attributes, because two different objects nest:
        # a Starlette ``Mount`` exposes ``routes``, and this FastAPI version's
        # ``_IncludedRouter`` wrapper exposes ``original_router``. Reading only
        # one of them silently loses forty routes.
        nested = getattr(route, "routes", None)
        if nested:
            found.extend(_all_route_paths(nested))
        original = getattr(route, "original_router", None)
        if original is not None and getattr(original, "routes", None):
            found.extend(_all_route_paths(original.routes))
    return found


def _mcp_route_paths(app) -> list[str]:
    return [path for path in _all_route_paths(app.routes) if "mcp" in path.lower()]


def test_the_default_deployment_registers_no_mcp_route_at_all(workspace):
    """Three independent witnesses, because one of them could be a false negative.

    A 404 alone would also be produced by a route that exists and refuses; a route
    table alone would miss a path registered somewhere else. Asserting the OpenAPI
    document as well is what makes "not advertised" a checked claim rather than an
    intention.
    """
    app = build_app()
    assert _mcp_route_paths(app) == []
    assert [p for p in app.openapi()["paths"] if "mcp" in p.lower()] == []

    client = TestClient(app, client=LOOPBACK_PEER)
    for method in ("post", "get", "delete"):
        response = getattr(client, method)(MCP_PATH)
        assert response.status_code == 404, (method, response.status_code)


@pytest.mark.parametrize(
    "value",
    ["", "   ", "true", "enabled", "hosted", "LOCAL_LOOPBACK", "local_loopback"]
    + list(RESERVED_BINDING_NAMES),
)
def test_no_value_but_the_registered_binding_name_mounts_anything(workspace, value):
    """Unrecognised, reserved and near-miss spellings all mount nothing.

    ``LOCAL_LOOPBACK`` and ``local_loopback`` are in the list on purpose: an
    operator's near miss must fail closed, not fall through to a case-insensitive
    or punctuation-insensitive match somebody added for convenience.
    """
    workspace.setenv(DEPLOYMENT_ENV, value)
    assert _mcp_route_paths(build_app()) == []


def test_a_misconfigured_scope_list_mounts_nothing_rather_than_mounting_a_reader(
    workspace,
):
    """The failure that would otherwise be invisible, at the transport layer.

    ``isaac:submit`` in the scope list resolves to the unconfigured binding, and
    the consequence must be an ABSENT endpoint — not a working read-only endpoint
    that an operator believes reflects what they wrote.
    """
    workspace.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    workspace.setenv(LOCAL_SCOPES_ENV, "isaac:read,isaac:submit")
    assert _mcp_route_paths(build_app()) == []


def test_the_configured_deployment_registers_exactly_one_route(workspace):
    app, _ = configured(workspace)
    assert _mcp_route_paths(app) == [MCP_PATH]
    # Still absent from the OpenAPI document: MCP is not an OpenAPI protocol, and
    # the Endpoint Explorer renders that document to scientists.
    assert [p for p in app.openapi()["paths"] if "mcp" in p.lower()] == []


def test_the_route_honours_the_deployment_base_path(workspace):
    """``ISAAC_BASE_PATH`` prefixes it, exactly as it prefixes every other route.

    Worth pinning: a transport registered at a hard-coded ``/api/mcp`` would be
    unreachable in the hosted deployment and reachable at an unexpected path in a
    prefixed one.
    """
    workspace.setenv("ISAAC_BASE_PATH", "/krish")
    app, _ = configured(workspace)
    assert _mcp_route_paths(app) == ["/krish/api/mcp"]


def test_a_binding_that_forgets_to_declare_itself_serves_nothing(workspace):
    """The ``getattr`` default is the safe one, so silence is a refusal.

    A future binding class that omits ``serves_transport`` must not be mounted.
    ``object()`` stands in for it: no attribute at all is the strongest form of
    forgetting.
    """
    assert mcp_transport_or_none(build_app(), binding=object()) is None
    assert mcp_transport_or_none(build_app(), binding=UnconfiguredDeployment()) is None
    assert (
        mcp_transport_or_none(build_app(), binding=LocalLoopbackDeployment()) is not None
    )


# --------------------------------------------------------------------------
# 1b. …and an application that will not serve MCP does not IMPORT the package
#
# This is an availability property, not tidiness. `policy.py` builds `OPERATIONS`
# at module scope and RAISES `RuntimeError` on an unreviewed `list_runs` query
# parameter or an annotation it cannot render — a review-time guard that is
# correct and stays. But `app = create_app()` runs at module scope, so an
# UNCONDITIONAL `from .mcp.transport import ...` inside `create_app` turns that
# guard into "uvicorn cannot import the application": no API, no UI, no health
# endpoint, on a deployment that was never going to serve MCP. `policy.py`'s own
# comment records that the run-list route is growing filters on other branches,
# so the trigger is a merge order, not a hypothetical.
# --------------------------------------------------------------------------

def test_the_env_name_app_py_duplicates_is_the_one_deployment_py_defines():
    """`app.py` cannot import the constant, so it copies it. Pin the copy.

    Importing `isaac_api.mcp.deployment` to read `DEPLOYMENT_ENV` would execute
    `isaac_api/mcp/__init__.py` — which is the entire thing the pre-check exists
    to avoid. A duplicated string literal is the price, and this assertion is what
    stops it drifting into a gate that never opens.
    """
    from isaac_api import app as app_module

    assert app_module._MCP_DEPLOYMENT_ENV == DEPLOYMENT_ENV


def _unimportable_transport_module(monkeypatch):
    """Make `from .mcp.transport import ...` raise the way `policy.py` would.

    The real failure is a `RuntimeError` raised while `isaac_api.mcp.policy`
    executes, which happens the first time anything imports the package. By the
    time this test runs the package is already in `sys.modules` (this file
    imported it), so re-importing would be a no-op. Substituting a module object
    whose attribute access raises reproduces the OBSERVABLE effect at the one
    place `app.py` touches: the `from ... import` statement raises `RuntimeError`.
    """
    exploding = types.ModuleType("isaac_api.mcp.transport")
    exploding.__spec__ = sys.modules["isaac_api.mcp.transport"].__spec__

    def _raise(name):
        raise RuntimeError(
            "the run-list route exposes an unreviewed query parameter 'sort'"
        )

    exploding.__getattr__ = _raise
    monkeypatch.setitem(sys.modules, "isaac_api.mcp.transport", exploding)


def test_an_unconfigured_app_boots_even_when_the_mcp_package_cannot_import(
    workspace, monkeypatch
):
    """The default deployment builds fine while the MCP package is on fire.

    Before the import was made conditional this raised out of `create_app`, and —
    because `app = create_app()` is module scope — out of `import isaac_api.app`,
    which is uvicorn's entry point. An MCP review guard must not be able to take
    the API, the UI and `/api/health` down with it.
    """
    _unimportable_transport_module(monkeypatch)

    app = build_app()  # must not raise

    assert _mcp_route_paths(app) == []
    client = TestClient(app, client=LOOPBACK_PEER)
    assert client.get("/api/health").status_code == 200


def test_a_configured_app_still_fails_loudly_when_the_mcp_package_cannot_import(
    workspace, monkeypatch
):
    """The other half, and the reason this is a narrowing rather than a bypass.

    The guard is not weakened for anybody who asked for MCP: an operator who set
    `ISAAC_MCP_DEPLOYMENT` gets the `RuntimeError`, unswallowed, at boot. Silently
    serving no MCP route because the package failed to import would be strictly
    worse than failing — it looks like a working deployment with a missing feature.
    """
    _unimportable_transport_module(monkeypatch)
    workspace.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)

    with pytest.raises(RuntimeError, match="unreviewed query parameter"):
        build_app()


def test_an_unrecognised_value_still_reaches_the_package_rather_than_being_judged_here(
    workspace, monkeypatch
):
    """The pre-check is a NECESSARY condition only, and deliberately not a registry.

    `app.py` must not learn which binding names serve a transport — a second copy
    of that registry would silently refuse to mount the next binding somebody
    adds. So any non-empty value imports the package and lets
    `mcp_transport_or_none` decide; the fail-closed answer still comes from there.
    Asserted by the failure propagating for a value that is NOT a real binding.
    """
    _unimportable_transport_module(monkeypatch)
    workspace.setenv(DEPLOYMENT_ENV, "hosted")

    with pytest.raises(RuntimeError, match="unreviewed query parameter"):
        build_app()


# ==========================================================================
# 2. A real JSON-RPC session over the mounted transport
# ==========================================================================

def test_a_full_json_rpc_session_runs_over_http_and_exposes_exactly_the_eight(
    workspace,
):
    """initialize -> initialized notification -> tools/list -> tools/call.

    The one test that answers "is this actually usable by a client". Every message
    goes over the HTTP endpoint, through the application's own middleware, into the
    transport, into the JSON-RPC handler, and — for the call — back into the same
    application over ASGI.
    """
    _, client = configured(workspace, scopes=BOTH_SCOPES)

    initialize = result_of(
        client,
        "initialize",
        {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0"},
        },
    )
    assert initialize["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert initialize["serverInfo"]["name"] == "isaac-metadata-assistant"
    assert initialize["_isaac"]["grantedScopes"] == [
        Scope.DRAFT_WRITE.value,
        Scope.READ.value,
    ]

    # The handshake's notification carries no id, so the transport answers 202 with
    # NO BODY — not 200 with an empty object, which a client would try to parse.
    notified = client.post(
        MCP_PATH, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert notified.status_code == 202
    assert notified.content == b""

    listed = {tool["name"] for tool in result_of(client, "tools/list")["tools"]}
    assert listed == set(PERMITTED_TOOL_NAMES)
    assert len(listed) == 8

    body = structured(client, "isaac_list_experiments")
    assert body["status"] == 200
    assert "experiments" in body["data"]


def test_a_tool_call_over_http_returns_real_record_content(workspace):
    session_id, ids = ws.create_tutorial_session()
    _, client = configured(workspace, scopes=BOTH_SCOPES, session=session_id)

    rows = structured(client, "isaac_list_experiments")["data"]["experiments"]
    assert {row["id"] for row in rows} == set(ids)

    detail = structured(client, "isaac_get_experiment", experiment_id=ws.SEED_READY_ID)
    assert detail["status"] == 200
    assert detail["etag"]


def test_the_response_is_canonical_json_and_is_not_cached(workspace):
    _, client = configured(workspace)
    response = rpc(client, "ping")
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    # Byte-stable: the same request twice produces the same bytes.
    assert response.content == rpc(client, "ping").content
    # No session is minted, so there is no bearer of authority this layer created.
    assert "mcp-session-id" not in {k.lower() for k in response.headers}


def test_a_real_client_over_a_real_loopback_socket_completes_a_session(workspace):
    """The one test with an actual TCP socket, an actual server, an actual client.

    Everything else in this file drives the ASGI application directly, which means
    ``scope["client"]`` is a tuple the test supplied. That is the right way to
    exercise a peer this machine cannot produce — and it is exactly why one case
    has to come from the kernel instead: it is what proves the loopback guard reads
    a real peer address correctly and does not refuse every genuine local client.

    ``uvicorn`` is already a declared dependency (``pyproject.toml`` ``[api]``),
    the bind is ``127.0.0.1`` with an ephemeral port, and nothing leaves the
    machine.

    **The only test in this file that binds a socket**, and therefore the only one
    that can fail in a CI sandbox which forbids ``bind()``/``listen()`` or has no
    loopback interface. A failure here is a sandbox question first and a transport
    question second. It is not skipped preemptively: a guard that is only ever
    exercised against test-supplied peers is a guard nothing has checked, so this
    case is worth being noisy about when the environment cannot run it.
    """
    import threading

    import httpx
    import uvicorn

    session_id, _ids = ws.create_tutorial_session()
    workspace.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    workspace.setenv(LOCAL_SCOPES_ENV, BOTH_SCOPES)
    workspace.setenv(LOCAL_SESSION_ENV, session_id)

    config = uvicorn.Config(build_app(), host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = 10.0
        waited = 0.0
        while not server.started and waited < deadline:  # pragma: no branch
            import time

            time.sleep(0.05)
            waited += 0.05
        assert server.started, "the loopback server did not start"
        port = server.servers[0].sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}{MCP_PATH}"

        with httpx.Client(timeout=30.0) as http:
            def send(method, params=None, mid=1):
                message = {"jsonrpc": "2.0", "id": mid, "method": method}
                if params is not None:
                    message["params"] = params
                response = http.post(
                    base,
                    json=message,
                    headers={
                        "accept": "application/json, text/event-stream",
                        "mcp-protocol-version": MCP_PROTOCOL_VERSION,
                    },
                )
                assert response.status_code == 200, response.text
                body = response.json()
                assert "error" not in body, body["error"]
                return body["result"]

            handshake = send(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "loopback-socket-test", "version": "0"},
                },
                mid=1,
            )
            assert handshake["protocolVersion"] == MCP_PROTOCOL_VERSION

            assert (
                http.post(
                    base, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
                ).status_code
                == 202
            )

            names = {tool["name"] for tool in send("tools/list", mid=2)["tools"]}
            assert names == set(PERMITTED_TOOL_NAMES)

            called = send(
                "tools/call",
                {"name": "isaac_list_experiments", "arguments": {}},
                mid=3,
            )
            assert called["isError"] is False
            assert called["structuredContent"]["status"] == 200
    finally:
        server.should_exit = True
        thread.join(timeout=10)


# ==========================================================================
# 3. LOCAL_LOOPBACK means loopback
# ==========================================================================

@pytest.mark.parametrize(
    "peer",
    ["10.0.0.5", "192.168.1.20", "8.8.8.8", "172.16.0.1", "2001:db8::1", "testclient"],
)
def test_a_non_loopback_peer_is_refused_before_the_body_is_read(workspace, peer):
    _, _ = configured(workspace)
    app = build_app()
    client = TestClient(app, client=(peer, 5000))
    response = rpc(client, "ping")
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == TRANSPORT_REFUSED
    assert body["error"]["data"]["code"] == "loopback_only"
    # The refusal does not echo the address it saw back to the caller.
    assert peer not in response.text


@pytest.mark.parametrize("method", ["get", "delete", "put", "patch", "options"])
def test_a_non_loopback_caller_is_refused_before_the_method_is_considered(
    workspace, method
):
    """403, not 405 — the peer check runs first, as both docstrings say it does.

    With the method check first, a caller from off loopback got
    ``405 Allow: POST``, which answers "does ISAAC speak MCP at this path?" for a
    scanner that never sent a POST and contradicts ``transport.py``'s stated axis
    2 and ``deployment.py``. Nothing about the verb may reach a peer this binding
    will not serve.
    """
    app, _ = configured(workspace)
    remote = TestClient(app, client=("203.0.113.9", 5000))

    response = getattr(remote, method)(MCP_PATH)

    assert response.status_code == 403
    assert response.json()["error"]["data"]["code"] == "loopback_only"
    # Specifically NOT the method refusal: no `Allow`, and no MCP vocabulary.
    assert "allow" not in {k.lower() for k in response.headers}
    assert "Mcp-Session-Id" not in response.text


def test_a_loopback_caller_still_gets_the_method_refusal(workspace):
    """The reorder narrows what a REMOTE caller learns and changes nothing local.

    Paired with the test above on purpose: moving a guard earlier is only safe if
    the behaviour it now precedes is intact for everybody it was written for.
    """
    _, client = configured(workspace)
    response = client.get(MCP_PATH)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_a_request_with_no_reported_peer_is_refused(workspace):
    """ASGI permits ``client`` to be absent. Absent must mean refused, not skipped."""
    app, _ = configured(workspace)
    client = TestClient(app, client=None)
    assert rpc(client, "ping").status_code == 403


@pytest.mark.parametrize("peer", ["127.0.0.1", "127.0.0.53", "::1", "::ffff:127.0.0.1"])
def test_every_loopback_form_is_served(workspace, peer):
    """Including the IPv4-mapped form, which ``is_loopback`` reports as False.

    A dual-stack listener reports v4 loopback peers as ``::ffff:127.0.0.1``. Without
    the explicit unmapping in ``is_loopback_host`` every local client on such a
    listener would be refused, and the bug would look like "MCP does not work".
    """
    app, _ = configured(workspace)
    client = TestClient(app, client=(peer, 5000))
    assert rpc(client, "ping").status_code == 200


@pytest.mark.parametrize(
    "header",
    ["x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip", "forwarded"],
)
def test_a_proxy_header_is_refused_even_from_a_loopback_peer(workspace, header):
    """Presence is the refusal; the VALUE is never read.

    ``CLAUDE.md`` records that ISAAC's Service is a plain ClusterIP with no
    NetworkPolicy, so any in-cluster caller can forge a forwarded header. This
    transport therefore never uses one as evidence of who is calling. It uses the
    fact that one exists as evidence that the loopback peer is a relay, which is a
    refusal rather than a trust decision.
    """
    _, client = configured(workspace)
    response = rpc(client, "ping", headers={header: "198.51.100.7"})
    assert response.status_code == 403
    assert response.json()["error"]["data"]["code"] == "proxied_request_refused"
    assert "198.51.100.7" not in response.text


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "http://attacker.test:8080", "null", "http://[::2]"]
)
def test_a_cross_origin_browser_caller_is_refused(workspace, origin):
    """The DNS-rebinding defence. The peer check alone does not provide it.

    A page served from any site can POST to ``http://127.0.0.1:8000`` and the
    socket peer will be loopback, because the browser really is on this machine.
    """
    _, client = configured(workspace)
    response = rpc(client, "ping", headers={"origin": origin})
    assert response.status_code == 403
    assert response.json()["error"]["data"]["code"] == "cross_origin_refused"


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:8000", "http://[::1]:8000", "https://localhost"],
)
def test_a_loopback_origin_is_served(workspace, origin):
    _, client = configured(workspace)
    assert rpc(client, "ping", headers={"origin": origin}).status_code == 200


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("127.1.2.3", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),
        ("localhost", True),
        ("", False),
        (None, False),
        ("0.0.0.0", False),
        ("10.0.0.1", False),
        ("2001:db8::1", False),
        ("LOCALHOST", False),
        ("localhost.evil.example", False),
        ("127.0.0.1.evil.example", False),
        ("127.0.0.1 ", False),
    ],
)
def test_is_loopback_host_refuses_everything_that_is_not_an_address(host, expected):
    """A name is not resolved and a lookalike is not matched.

    ``127.0.0.1.evil.example`` and ``localhost.evil.example`` are the classic
    rebinding names: both resolve to whatever their owner chooses and both would
    pass a ``startswith``/``in`` check.
    """
    assert is_loopback_host(host) is expected


# ==========================================================================
# 4. Fail-closed on every other axis
# ==========================================================================

@pytest.mark.parametrize("method", ["get", "delete", "put", "patch"])
def test_only_post_is_implemented(workspace, method):
    _, client = configured(workspace)
    response = getattr(client, method)(MCP_PATH)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_get_and_delete_explain_themselves_rather_than_looking_unfinished(workspace):
    _, client = configured(workspace)
    assert "server-initiated stream" in client.get(MCP_PATH).json()["error"]["message"]
    assert "Mcp-Session-Id" in client.delete(MCP_PATH).json()["error"]["message"]


def test_batching_is_refused_because_the_revision_removed_it(workspace):
    _, client = configured(workspace)
    response = client.post(
        MCP_PATH, json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}]
    )
    assert response.status_code == 400
    assert response.json()["error"]["data"]["code"] == "batching_not_supported"


def test_a_malformed_body_is_refused_without_echoing_any_of_it(workspace):
    _, client = configured(workspace)
    secret = "hunter2-not-json"
    response = client.post(
        MCP_PATH, content=secret.encode(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["data"]["code"] == "parse_error"
    assert secret not in response.text


def test_a_json_scalar_is_not_a_json_rpc_message(workspace):
    _, client = configured(workspace)
    response = client.post(MCP_PATH, json="ping")
    assert response.status_code == 400
    assert response.json()["error"]["data"]["code"] == "invalid_request"


def test_a_body_over_the_cap_is_refused_rather_than_buffered(workspace):
    _, client = configured(workspace)
    oversize = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"x": "a" * MAX_REQUEST_BYTES}}
    ).encode()
    response = client.post(
        MCP_PATH, content=oversize, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", ""])
def test_a_non_json_content_type_is_refused(workspace, content_type):
    _, client = configured(workspace)
    response = client.post(
        MCP_PATH, content=b'{"jsonrpc":"2.0","id":1,"method":"ping"}',
        headers={"content-type": content_type} if content_type else {},
    )
    assert response.status_code == 415


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "APPLICATION/JSON",
        "Application/Json",
        "application/json; charset=UTF-8",
        "  application/json  ",
    ],
)
def test_the_media_type_is_matched_case_insensitively(workspace, content_type):
    """RFC 9110 §8.3.1 makes type/subtype case-insensitive, so 415 here is a bug.

    It failed closed rather than open, which is why it is a usability defect and
    not a security one — but a conforming client refused with 415 has no way to
    tell that from "this server does not take JSON". ``Accept`` was already
    lowercased; only ``Content-Type`` was not.
    """
    _, client = configured(workspace)
    response = client.post(
        MCP_PATH,
        content=b'{"jsonrpc":"2.0","id":1,"method":"ping"}',
        headers={"content-type": content_type},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"] == {}


def test_a_client_that_cannot_accept_json_is_refused(workspace):
    _, client = configured(workspace)
    assert rpc(client, "ping", headers={"accept": "text/event-stream"}).status_code == 406
    # The shapes a real client sends are all served.
    for accept in ("application/json", "application/json, text/event-stream", "*/*"):
        assert rpc(client, "ping", headers={"accept": accept}).status_code == 200


def test_a_client_declaring_another_protocol_revision_is_refused(workspace):
    _, client = configured(workspace)
    response = rpc(client, "ping", headers={"mcp-protocol-version": "2024-11-05"})
    assert response.status_code == 400
    assert response.json()["error"]["data"]["supported"] == [MCP_PROTOCOL_VERSION]
    assert rpc(
        client, "ping", headers={"mcp-protocol-version": MCP_PROTOCOL_VERSION}
    ).status_code == 200


def test_the_three_implementation_defined_error_codes_are_distinct(workspace):
    """A duplicated code is a client mis-branching on an authorization failure."""
    codes = {DEPLOYMENT_UNCONFIGURED, INSUFFICIENT_SCOPE, TRANSPORT_REFUSED}
    assert len(codes) == 3
    assert all(-32099 <= code <= -32000 for code in codes)


# ==========================================================================
# 5. The authorization seam
# ==========================================================================

def test_a_credential_is_refused_rather_than_accepted_unvalidated(workspace):
    """``401``, and no invented challenge.

    The loopback binding cannot verify a token and will not pretend to. Accepting
    one would let somebody point a real client at this endpoint and believe an
    authentication happened.
    """
    _, client = configured(workspace)
    response = rpc(
        client, "initialize", {}, headers={"authorization": "Bearer s3cret-value"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["data"]["code"] == "credential_not_verifiable"
    # The token is never echoed, and no WWW-Authenticate points at an
    # authorization server that does not exist.
    assert "s3cret-value" not in response.text
    assert "www-authenticate" not in {k.lower() for k in response.headers}


def test_the_unconfigured_binding_would_answer_401_with_no_fabricated_challenge(
    workspace,
):
    """Reached only by forcing the mount, because the default mounts nothing.

    Worth asserting anyway: it is the shape a hosted binding inherits, and the
    ``resource_metadata: null`` is the honest statement that ISAAC publishes no
    RFC 9728 document.
    """
    app = build_app()
    transport = mcp_transport_or_none(app, binding=_forced(UnconfiguredDeployment()))
    assert transport is not None
    app.router.routes.append(_route(MCP_PATH, transport))
    client = TestClient(app, client=LOOPBACK_PEER)
    response = rpc(client, "initialize", {})
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == DEPLOYMENT_UNCONFIGURED
    assert error["data"]["challenge"]["resource_metadata"] is None
    assert [d["id"] for d in error["data"]["outstanding_decisions"]] == ["D1", "D2"]
    assert "www-authenticate" not in {k.lower() for k in response.headers}


def test_the_apps_own_api_key_and_the_mcp_binding_conflict_in_the_safe_direction(
    workspace,
):
    """A misconfiguration that refuses is the correct outcome, and it is pinned.

    With ``ISAAC_UI_API_KEY`` set, ``ApiKeyAuthMiddleware`` demands the key in
    ``Authorization`` on every path including this one — and this transport hands
    whatever is in ``Authorization`` to the binding, which cannot verify it. So
    both the wrong key and the right key are refused, by different layers, and
    neither combination produces a working unauthenticated MCP endpoint.

    Do not "fix" this by teaching the transport to recognise and swallow the app's
    own key: that would make a shared secret intended for the UI into an MCP
    credential nobody decided to issue.
    """
    workspace.setenv("ISAAC_UI_API_KEY", "ui-key")
    _, client = configured(workspace)
    # No credential at all: the middleware refuses first.
    assert rpc(client, "ping").status_code == 401
    # The app's own key: the middleware admits it, the binding refuses it.
    response = rpc(client, "initialize", {}, headers={"authorization": "Bearer ui-key"})
    assert response.status_code == 401
    assert response.json()["error"]["data"]["code"] == "credential_not_verifiable"


def test_the_read_grant_is_the_default_and_the_write_tools_are_absent(workspace):
    """Unset ``ISAAC_MCP_LOCAL_SCOPES`` grants read alone, over the wire too."""
    _, client = configured(workspace)
    listed = {tool["name"] for tool in result_of(client, "tools/list")["tools"]}
    assert "isaac_create_run" not in listed
    assert "isaac_update_draft" not in listed
    assert len(listed) == 6


def test_a_read_only_caller_is_refused_a_write_tool_with_403(workspace):
    session_id, ids = ws.create_tutorial_session()
    _, client = configured(workspace, session=session_id)
    response = rpc(
        client,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": ids[0], "if_match": '"x.0"'}},
    )
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == INSUFFICIENT_SCOPE
    assert error["data"]["missingScopes"] == [Scope.DRAFT_WRITE.value]


def test_the_write_scope_alone_now_reaches_nothing_at_all(workspace):
    """Non-nesting, in BOTH directions, asserted over the transport.

    A write tool requires read as well, because it returns the state it produced.
    That makes ``isaac:draft.write`` alone a grant with no usable tool — strictly
    narrower than before, and the opposite of implication.
    """
    session_id, ids = ws.create_tutorial_session()
    _, client = configured(workspace, scopes=Scope.DRAFT_WRITE.value, session=session_id)

    assert result_of(client, "tools/list")["tools"] == []
    read_denied = rpc(
        client, "tools/call", {"name": "isaac_list_experiments", "arguments": {}}
    )
    assert read_denied.status_code == 403
    assert read_denied.json()["error"]["data"]["missingScopes"] == [Scope.READ.value]

    write_denied = rpc(
        client,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": ids[0], "if_match": '"x.0"'}},
    )
    assert write_denied.status_code == 403
    assert write_denied.json()["error"]["data"]["missingScopes"] == [Scope.READ.value]


def test_a_caller_cannot_grant_itself_a_scope_over_the_transport(workspace):
    """Identity and permission are the server's to state. HTTP 200, JSON-RPC error.

    Deliberately NOT 403: nothing about authorization failed. The request was
    malformed, because it tried to carry a claim the protocol has no field for.
    """
    session_id, ids = ws.create_tutorial_session()
    _, client = configured(workspace, session=session_id)
    response = rpc(
        client,
        "tools/call",
        {
            "name": "isaac_create_run",
            "arguments": {"experiment_id": ids[0], "if_match": '"x.0"'},
            "scopes": [Scope.READ.value, Scope.DRAFT_WRITE.value],
        },
    )
    assert response.status_code == 200
    assert response.json()["error"]["code"] == INVALID_PARAMS
    assert "cannot be asserted by a caller" in response.json()["error"]["message"]


def test_a_tool_cannot_reach_a_workspace_scope_the_binding_did_not_bind(workspace):
    """The worked-example session comes off the binding, not off a request."""
    session_id, ids = ws.create_tutorial_session()
    _, bound = configured(workspace, session=session_id)
    assert structured(bound, "isaac_get_experiment", experiment_id=ids[0])["status"] == 200

    # A second app for the ordinary scope. The same id is invisible to it, and no
    # header the caller adds changes that: the client writes the session header
    # from the principal.
    workspace.delenv(LOCAL_SESSION_ENV, raising=False)
    ordinary_app = build_app()
    ordinary = TestClient(ordinary_app, client=LOOPBACK_PEER)
    body = structured(ordinary, "isaac_get_experiment", experiment_id=ids[0])
    assert body["status"] == 404
    forged = ordinary.post(
        MCP_PATH,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "isaac_get_experiment", "arguments": {"experiment_id": ids[0]}},
        },
        headers={"x-isaac-tutorial-session": session_id},
    )
    assert forged.json()["result"]["structuredContent"]["status"] == 404


# ==========================================================================
# 6. Submit, export, migration, governance, deletion and secrets are unreachable
# ==========================================================================

@pytest.mark.parametrize("name", FORBIDDEN_OVER_THE_WIRE)
def test_no_forbidden_tool_can_be_invoked_over_the_mounted_surface(workspace, name):
    """Asked for by name, over the wire, with the widest grant this build can issue."""
    _, client = configured(workspace, scopes=BOTH_SCOPES)
    response = rpc(client, "tools/call", {"name": name, "arguments": {}})
    assert response.status_code == 200
    error = response.json()["error"]
    assert error["code"] == INVALID_PARAMS
    assert "is not a tool this server exposes" in error["message"]


def test_the_mounted_surface_cannot_reach_a_submit_or_export_path(workspace):
    """Every operation the transport can reach, checked against the real route table.

    ``policy.py`` refuses a forbidden token in an operation's path template at
    import. This is the same question asked one layer out: of the routes this
    application actually registers, none that the MCP layer can reach is a
    submit/export/delete/migration/governance route.
    """
    app, _ = configured(workspace, scopes=BOTH_SCOPES)
    registered = set(_all_route_paths(app.routes))
    reachable = {operation.path_template for operation in OPERATIONS.values()}
    assert reachable <= registered, sorted(reachable - registered)
    for path in reachable:
        lowered = path.lower()
        for token in FORBIDDEN_PATH_TOKENS:
            assert token not in lowered, (path, token)
    # And the routes that DO carry those tokens exist, so the assertion above is
    # not vacuously true of an application that has no export route.
    assert any("/export" in path for path in registered)


def test_a_path_parameter_cannot_be_bent_into_another_route(workspace):
    """``../export`` is refused by the character class, not escaped and retried."""
    _, client = configured(workspace, scopes=BOTH_SCOPES)
    for hostile in ("../export", "..%2fexport", "x/../../export", "a b"):
        body = structured(client, "isaac_get_experiment", experiment_id=hostile)
        assert body["error"] == "invalid_path_parameter", hostile


def test_the_transport_exposes_no_second_path_of_its_own(workspace):
    """No metadata document, no discovery endpoint, no sub-path.

    RFC 9728 discovery is deliberately unpublished: a protected-resource document
    naming an authorization server ISAAC does not run would be an invitation to a
    flow that cannot complete.
    """
    app, client = configured(workspace)
    for path in (
        f"{MCP_PATH}/tools",
        f"{MCP_PATH}/sse",
        f"{MCP_PATH}/message",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
    ):
        assert client.post(path, json={}).status_code == 404, path
    assert _mcp_route_paths(app) == [MCP_PATH]

    # The trailing-slash form is NOT a second endpoint: Starlette redirects it to
    # the canonical path, which is one route answering under two spellings. Pinned
    # so a future reader does not mistake the 200 for an extra registration.
    redirected = client.post(
        f"{MCP_PATH}/", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, follow_redirects=False
    )
    assert redirected.status_code in (307, 308)
    assert redirected.headers["location"].endswith(MCP_PATH)


# ==========================================================================
# 7. CAS and validation are the API's, and the transport cannot skip them
# ==========================================================================

def _record_etag(client, experiment_id: str) -> str:
    return structured(client, "isaac_get_experiment", experiment_id=experiment_id)["etag"]


def test_a_write_without_if_match_never_reaches_the_api(workspace):
    """Refused by the tool schema, before a request is built.

    The API's own answer would be ``428``. This layer refuses earlier and says so,
    which is the same gate held one step sooner — never a way around it.
    """
    session_id, ids = ws.create_tutorial_session()
    _, client = configured(workspace, scopes=BOTH_SCOPES, session=session_id)
    response = rpc(
        client, "tools/call", {"name": "isaac_create_run", "arguments": {"experiment_id": ids[0]}}
    )
    assert response.status_code == 200
    assert response.json()["error"]["code"] == INVALID_PARAMS
    assert "if_match" in response.json()["error"]["message"]


def test_a_stale_etag_is_refused_with_412_and_nothing_is_written(workspace):
    session_id, _ = ws.create_tutorial_session()
    _, client = configured(workspace, scopes=BOTH_SCOPES, session=session_id)
    experiment_id = ws.SEED_READY_ID

    stale = _record_etag(client, experiment_id)
    structured(client, "isaac_create_run", experiment_id=experiment_id, if_match=stale, label="A")

    refused = structured(
        client, "isaac_create_run", experiment_id=experiment_id, if_match=stale, label="B"
    )
    assert refused["status"] == 412
    runs = structured(client, "isaac_list_runs", experiment_id=experiment_id)["data"]["runs"]
    assert [run["label"] for run in runs] == ["A"]


def test_the_transport_gets_the_same_refusal_the_http_route_gives(workspace):
    """CAS/validation PARITY, asserted by driving both and comparing.

    A record-level field path sent to the run PATCH route is a ``422``. If the MCP
    path could reach a different validator, or skip one, this is where it would
    show — the two calls are the same write expressed twice.
    """
    session_id, _ = ws.create_tutorial_session()
    app, client = configured(workspace, scopes=BOTH_SCOPES, session=session_id)
    experiment_id = ws.SEED_READY_ID

    created = structured(
        client,
        "isaac_create_run",
        experiment_id=experiment_id,
        if_match=_record_etag(client, experiment_id),
        label="Parity",
    )
    run_id = created["data"]["run"]["id"]
    run = structured(client, "isaac_get_run", experiment_id=experiment_id, run_id=run_id)
    run_etag = run["etag"]

    over_mcp = structured(
        client,
        "isaac_update_draft",
        experiment_id=experiment_id,
        run_id=run_id,
        if_match=run_etag,
        confirmed_by_user=True,
        fields={"sample.material.name": "not a run-level path"},
    )

    plain = TestClient(app, client=LOOPBACK_PEER).patch(
        f"/api/experiments/{experiment_id}/runs/{run_id}",
        json={
            "confirmed_by_user": True,
            "fields": {"sample.material.name": "not a run-level path"},
        },
        headers={"If-Match": run_etag, "X-Isaac-Tutorial-Session": session_id},
    )

    assert over_mcp["status"] == plain.status_code == 422
    assert over_mcp["data"]["error"] == plain.json()["error"]


def test_a_confirmation_the_caller_did_not_give_is_not_manufactured(workspace):
    """``confirmed_by_user: false`` earns the API's own ``422``.

    The tool passes the caller's assertion through unchanged. Hard-coding ``true``
    would manufacture the evidence the API records for a value that has no other
    support — a no-guessing violation dressed as a convenience.
    """
    session_id, _ = ws.create_tutorial_session()
    _, client = configured(workspace, scopes=BOTH_SCOPES, session=session_id)
    experiment_id = ws.SEED_READY_ID
    created = structured(
        client,
        "isaac_create_run",
        experiment_id=experiment_id,
        if_match=_record_etag(client, experiment_id),
        label="Unconfirmed",
    )
    run_id = created["data"]["run"]["id"]
    run_etag = structured(
        client, "isaac_get_run", experiment_id=experiment_id, run_id=run_id
    )["etag"]
    refused = structured(
        client,
        "isaac_update_draft",
        experiment_id=experiment_id,
        run_id=run_id,
        if_match=run_etag,
        confirmed_by_user=False,
        fields={"context.temperature_K": 300},
    )
    assert refused["status"] == 422


def test_an_mcp_write_cannot_disturb_an_exported_records_official_artifact(workspace):
    """The immutable thing in ISAAC is the EXPORTED ARTIFACT, and MCP cannot touch it.

    Stated precisely, because it is easy to overclaim: the run PATCH route does not
    refuse a draft edit on a record that has been exported — editing the draft
    afterwards marks the artifact *stale*, which is the product's designed
    behaviour and not something this layer may change. What MCP cannot do is
    rewrite, re-mint or delete the official record and sidecar on disk, because no
    operation it can reach targets export. This asserts the bytes.
    """
    session_id, _ = ws.create_tutorial_session()
    _, client = configured(workspace, scopes=BOTH_SCOPES, session=session_id)
    exported_id = ws.SEED_DONE_ID

    detail = structured(client, "isaac_get_experiment", experiment_id=exported_id)["data"]
    assert detail["exported"] is True, detail

    records_dir = ws.load_experiment(exported_id, session_id=session_id).records_dir
    before = {path.name: path.read_bytes() for path in sorted(records_dir.glob("*.json"))}
    assert before, "the exported seed wrote no artifact; this test would be vacuous"

    created = structured(
        client,
        "isaac_create_run",
        experiment_id=exported_id,
        if_match=_record_etag(client, exported_id),
        label="After export",
    )
    assert created["status"] in (200, 201, 409, 412, 422)

    after = {path.name: path.read_bytes() for path in sorted(records_dir.glob("*.json"))}
    assert after == before


# ==========================================================================
# 8. Negative controls: each guard is disabled, and the behaviour changes
# ==========================================================================

def test_the_mount_gate_is_load_bearing(workspace, monkeypatch):
    """Disable it and the route appears — so its absence is caused by the gate.

    Without this, "the default mounts nothing" is also satisfied by an application
    where the mount is broken for an unrelated reason, and the test above would
    keep passing after somebody deleted the feature.

    The break is applied at the ONE place the gate is read: the binding the
    transport module resolves. Everything else — ``create_app``, the route
    registration — is left as it is.

    ``ISAAC_MCP_DEPLOYMENT`` is SET here, to a value that is not a binding. There
    are two gates in series since the import was made conditional, and this test
    is about the inner one: a set-but-unrecognised value clears ``app.py``'s cheap
    env pre-check (so the package is imported and the real decision is made) and
    still resolves to :class:`UnconfiguredDeployment`. The OUTER gate has its own
    control immediately below.
    """
    import isaac_api.mcp.transport as transport_module

    workspace.setenv(DEPLOYMENT_ENV, "hosted")
    assert _mcp_route_paths(build_app()) == []
    monkeypatch.setattr(
        transport_module,
        "resolve_binding",
        lambda env=None: _forced(UnconfiguredDeployment()),
    )
    assert _mcp_route_paths(build_app()) == [MCP_PATH]


def test_the_env_precheck_is_the_outer_gate_and_is_load_bearing(workspace, monkeypatch):
    """With the binding forced to serve, the env pre-check alone still mounts nothing.

    Same forced binding in both halves, so the only variable is the environment.
    Unset, ``app.py`` never imports the package, so the forced binding is never
    consulted and no route appears — which is the property that keeps a raising
    ``policy.py`` out of the boot path. Set, the package is imported, the forced
    binding is consulted, and the route appears.
    """
    import isaac_api.mcp.transport as transport_module

    monkeypatch.setattr(
        transport_module,
        "resolve_binding",
        lambda env=None: _forced(UnconfiguredDeployment()),
    )
    assert _mcp_route_paths(build_app()) == []

    workspace.setenv(DEPLOYMENT_ENV, "hosted")
    assert _mcp_route_paths(build_app()) == [MCP_PATH]


def test_the_loopback_guard_is_load_bearing(workspace, monkeypatch):
    """Disable it and a remote peer is served — so the 403 is this check, not luck.

    **This control is also a warning, and must not be read as an endorsement.**
    The flip it performs — ``requires_loopback_peer=False`` — switches off THREE
    guards, not one: the peer check, the proxy-header refusal and the
    cross-origin/DNS-rebinding refusal all sit behind that single flag in
    ``transport.py``. Serving a remote peer 200 is the correct assertion *here*,
    because this is a control on an unmountable binding in a test process. It
    would be the wrong thing to reproduce in a real binding: an
    ``edge-issued-bearer`` author who copies this flip to admit edge traffic
    silently disables the other two on the one binding that is internet-adjacent.
    See the comments at ``transport.py``'s ``if self._loopback_only`` and in
    ``deployment.py``; splitting the flag is a follow-up.
    """
    import isaac_api.mcp.transport as transport_module

    app, _ = configured(workspace)
    remote = TestClient(app, client=("203.0.113.9", 5000))
    assert rpc(remote, "ping").status_code == 403

    monkeypatch.setattr(
        transport_module,
        "resolve_binding",
        lambda env=None: _forced(LocalLoopbackDeployment(), requires_loopback_peer=False),
    )
    reopened = build_app()
    assert rpc(TestClient(reopened, client=("203.0.113.9", 5000)), "ping").status_code == 200


def test_the_scope_check_is_load_bearing(workspace, monkeypatch):
    """Neuter ``Principal.missing`` and the read-only caller reaches a write tool.

    This is the control that proves the 403 above comes from the scope comparison
    rather than from the tool being unreachable for some other reason.
    """
    session_id, _ = ws.create_tutorial_session()
    _, client = configured(workspace, session=session_id)
    experiment_id = ws.SEED_READY_ID

    denied = rpc(
        client,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": experiment_id, "if_match": '"x.0"'}},
    )
    assert denied.status_code == 403

    monkeypatch.setattr(Principal, "missing", lambda self, required: frozenset())
    reached = rpc(
        client,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": experiment_id, "if_match": '"x.0"'}},
    )
    # It now reaches the API, which refuses it on its OWN terms (a stale ETag) —
    # which is the point: the scope check was the only thing stopping it.
    assert reached.status_code == 200
    assert reached.json()["result"]["structuredContent"]["status"] == 412


# --------------------------------------------------------------------------
# helpers used by one test each, kept at the bottom
# --------------------------------------------------------------------------

def _forced(binding, **overrides):
    """A copy of ``binding`` with one gate flipped, for a negative control.

    ``dataclasses.replace`` rather than ``monkeypatch.setattr`` on the class:
    ``serves_transport`` and ``requires_loopback_peer`` are dataclass FIELDS, so
    every instance carries its own value and patching the class attribute changes
    nothing. That is not an inconvenience — it is the reason a control is needed
    here at all, because a patch that silently does nothing produces a test that
    passes while proving the opposite of what it claims.
    """
    import dataclasses

    return dataclasses.replace(binding, serves_transport=True, **overrides)


def _route(path: str, transport):
    from starlette.routing import Route

    return Route(path, transport, name="mcp", methods=None, include_in_schema=False)
