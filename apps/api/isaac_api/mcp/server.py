"""The MCP protocol surface: JSON-RPC 2.0 in, JSON-RPC 2.0 out, and nothing else.

WHY THIS IS HAND-ROLLED, AND WHAT IT DELIBERATELY DOES NOT DO
=============================================================
The slice's constraint was zero new dependencies, and an MCP **tool server** is a
small enough protocol to meet honestly: ``initialize``, ``tools/list``,
``tools/call``, ``ping``, and the JSON-RPC framing around them. That is what is
here, targeting protocol revision :data:`MCP_PROTOCOL_VERSION`.

**No transport ships with it, and that is a decision rather than an omission.**
There is no HTTP route, no stdio loop, no socket. :meth:`McpServer.handle` takes a
decoded JSON-RPC message and returns one; wiring it to Streamable HTTP is the work
that begins when D1 and D2 are answered (``deployment.py``). Two consequences a
future session should not have to rediscover:

* the whole surface is exercisable locally and in CI with no network and no
  credential, which is why the test suite is deterministic; and
* ``ISAAC_MCP_DEPLOYMENT=local-loopback`` cannot expose anything remotely, because
  there is nothing listening. ``test_mcp_boundaries.py`` asserts the FastAPI app
  registers no MCP path.

The features this surface does not implement — resources, prompts, sampling,
elicitation, completion, logging, progress, cancellation — are not advertised in
:meth:`_initialize`'s ``capabilities``, so a compliant client will not attempt
them. Notably **sampling is absent on purpose**: sampling is the one MCP feature
by which a server asks a client's model to infer something, and offering it would
quietly contradict the audit's §1 finding that this connection gives ISAAC no
inference.

WHERE AUTHORIZATION LIVES
=========================
Every request re-authenticates through the deployment binding. Not once at
``initialize`` and cached: a cached principal is a principal that outlives the
grant that produced it, and re-checking an in-process binding costs nothing.

Two different refusal channels, and the split is deliberate:

* **JSON-RPC errors** for anything that is not a tool's output — the deployment
  is unconfigured, the scope was not granted, the arguments did not validate, the
  method does not exist. A model must not be able to read "you may not do this"
  as a result the tool produced.
* **``isError`` results** for what the ISAAC API itself answered — ``404``,
  ``412``, ``422``. Those *are* the tool's output: the call happened and the API
  refused it, which is information the caller should reason about.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from .client import ApiRefusal, AsgiApiClient, IsaacApiClient
from .deployment import (
    Credential,
    DeploymentBinding,
    DeploymentRefused,
    Principal,
    resolve_binding,
)
from .policy import Scope
from .tools import TOOLS, InvalidArguments, ToolContext, validate_arguments

__all__ = ["MCP_PROTOCOL_VERSION", "McpServer"]

_log = logging.getLogger(__name__)

#: The MCP revision this surface implements. Pinned rather than negotiated
#: downward: it is the revision whose authorization chapter mandates RFC 9728
#: protected-resource metadata, which is the shape ``deployment.py`` is built to
#: accept. A client asking for a different revision is answered with this one, per
#: the specification's negotiation rule, and may disconnect.
MCP_PROTOCOL_VERSION = "2025-06-18"

SERVER_INFO = {
    "name": "isaac-metadata-assistant",
    "title": "ISAAC Metadata Assistant",
    "version": "0.1.0",
}

#: JSON-RPC error codes. The two above -32000 are this server's own, which the
#: JSON-RPC specification reserves -32000..-32099 for.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
#: The deployment boundary refused: nobody could be authenticated.
DEPLOYMENT_UNCONFIGURED = -32001
#: A principal exists but was not granted the scope this call costs.
INSUFFICIENT_SCOPE = -32002

_SUPPORTED_METHODS = (
    "initialize",
    "notifications/initialized",
    "ping",
    "tools/list",
    "tools/call",
)

#: ``params`` keys ``tools/call`` accepts. Everything else is refused rather than
#: ignored, because a silently-ignored ``scopes`` key looks to a caller like a
#: request that was honoured.
_CALL_PARAM_KEYS = frozenset({"name", "arguments", "_meta"})


class McpServer:
    """An MCP tool server over one ISAAC application instance.

    ``app`` is the FastAPI application. ``binding`` defaults to whatever
    :func:`~.deployment.resolve_binding` makes of the environment, which is
    :class:`~.deployment.UnconfiguredDeployment` unless a deployment has said
    otherwise — so constructing one without arguments yields a server that
    truthfully refuses.
    """

    def __init__(
        self,
        app: Any,
        *,
        binding: DeploymentBinding | None = None,
        env: Mapping[str, str] | None = None,
        client_factory=None,
    ) -> None:
        self._app = app
        self._binding = binding if binding is not None else resolve_binding(env)
        self._client_factory = client_factory or self._default_client

    # -- public -------------------------------------------------------------

    @property
    def binding(self) -> DeploymentBinding:
        return self._binding

    async def handle(
        self, message: Mapping[str, Any], *, credential: Credential | None = None
    ) -> dict | None:
        """One JSON-RPC request in, one response out (``None`` for a notification)."""
        if not isinstance(message, Mapping):
            return _error(None, INVALID_REQUEST, "A JSON-RPC message must be an object.")
        if message.get("jsonrpc") != "2.0":
            return _error(
                message.get("id"), INVALID_REQUEST, "jsonrpc must be exactly '2.0'."
            )
        method = message.get("method")
        if not isinstance(method, str):
            return _error(message.get("id"), INVALID_REQUEST, "method must be a string.")
        request_id = message.get("id")
        is_notification = "id" not in message

        if method not in _SUPPORTED_METHODS:
            if is_notification:
                # A notification gets no response, including no error response.
                # Unknown notifications are ignorable by specification.
                return None
            return _error(
                request_id,
                METHOD_NOT_FOUND,
                f"{method!r} is not a method this server implements.",
                data={"supported": list(_SUPPORTED_METHODS)},
            )

        if is_notification:
            # By specification a notification is never answered — not with a
            # result and not with an error. Every method above is idempotent or a
            # read, so there is nothing to run for its side effects.
            return None

        params = message.get("params") or {}
        if not isinstance(params, Mapping):
            return _error(request_id, INVALID_PARAMS, "params must be an object.")

        try:
            if method == "notifications/initialized":
                # Sent WITH an id, which is a client bug rather than ours.
                # Answered benignly instead of erroring on the handshake.
                return _result(request_id, {})
            if method == "ping":
                return _result(request_id, {})
            if method == "initialize":
                return _result(request_id, self._initialize(credential))
            if method == "tools/list":
                return _result(request_id, self._tools_list(credential))
            return _result(
                request_id, await self._tools_call(params, credential=credential)
            )
        except DeploymentRefused as refusal:
            return _error(
                request_id,
                DEPLOYMENT_UNCONFIGURED,
                refusal.message,
                data={
                    "code": refusal.code,
                    **refusal.data,
                    "challenge": self._binding.challenge(),
                },
            )
        except _ScopeDenied as denied:
            return _error(request_id, INSUFFICIENT_SCOPE, denied.message, data=denied.data)
        except InvalidArguments as invalid:
            return _error(request_id, INVALID_PARAMS, str(invalid))
        except Exception:  # noqa: BLE001 - the protocol loop must not raise
            # THE EXCEPTION IS NOT INTERPOLATED, matching the fail-closed
            # vocabulary the ISAAC routes already use for the same reason: a
            # driver message, a path or a stack frame reaching a model is a leak,
            # and an agent can do nothing useful with it either way.
            _log.exception("MCP request failed method=%s", method)
            return _error(
                request_id,
                INTERNAL_ERROR,
                "The request could not be completed.",
            )

    # -- methods ------------------------------------------------------------

    def _initialize(self, credential: Credential | None) -> dict:
        # Authenticated here too, so an unconfigured deployment refuses the
        # handshake rather than completing one and failing every later call.
        principal = self._binding.authenticate(credential)
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            # Only what is implemented. `listChanged` is false because the tool set
            # is frozen at import; claiming it and never sending the notification
            # would be a contract this server does not keep.
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": dict(SERVER_INFO),
            "instructions": (
                "ISAAC's tools read and edit DRAFT metadata records. Nothing here "
                "finalises, exports, submits, deletes or migrates anything, and no "
                "such tool exists to be asked for. Values are never invented: a "
                "field without evidence stays missing or becomes a blocking "
                "question. Writes require the ETag from a prior read."
            ),
            "_isaac": {
                "binding": principal.binding,
                "grantedScopes": sorted(s.value for s in principal.scopes),
                "workspaceScope": (
                    "worked-example-session"
                    if principal.tutorial_session_id
                    else "ordinary"
                ),
            },
        }

    def _tools_list(self, credential: Credential | None) -> dict:
        principal = self._binding.authenticate(credential)
        return {
            "tools": [
                tool.descriptor()
                for name, tool in sorted(TOOLS.items())
                if principal.permits(tool.scope)
            ]
        }

    async def _tools_call(
        self, params: Mapping[str, Any], *, credential: Credential | None
    ) -> dict:
        unknown = sorted(set(params) - _CALL_PARAM_KEYS)
        if unknown:
            raise InvalidArguments(
                f"params carries unrecognised key(s) {unknown}. Identity and "
                "permissions are decided by the server and cannot be asserted by a "
                "caller."
            )
        name = params.get("name")
        if not isinstance(name, str):
            raise InvalidArguments("params.name must be a tool name.")
        tool = TOOLS.get(name)
        if tool is None:
            raise InvalidArguments(f"{name!r} is not a tool this server exposes.")

        principal = self._binding.authenticate(credential)
        if not principal.permits(tool.scope):
            raise _ScopeDenied(tool.name, tool.scope, principal)

        arguments = params.get("arguments", {})
        accepted = validate_arguments(tool.input_schema, arguments)

        context = ToolContext(client=self._client_factory(principal))
        try:
            outcome = await tool.handler(context, accepted)
        except ApiRefusal as refusal:
            return _content(
                {
                    "operation": refusal.data.get("operation_id"),
                    "error": refusal.code,
                    "data": {"message": refusal.message, **refusal.data},
                },
                is_error=True,
            )
        return _content(outcome.payload, is_error=outcome.is_error)

    # -- wiring -------------------------------------------------------------

    def _default_client(self, principal: Principal) -> IsaacApiClient:
        # The session comes off the PRINCIPAL. It is the single line that composes
        # this server with the existing worked-example scoping: whatever scope the
        # binding put the connection in, every call this server makes carries it,
        # and no tool argument can name a different one.
        return AsgiApiClient(
            self._app, tutorial_session_id=principal.tutorial_session_id
        )


class _ScopeDenied(Exception):
    def __init__(self, tool_name: str, required: Scope, principal: Principal) -> None:
        self.message = (
            f"{tool_name!r} requires the {required.value!r} scope, which this "
            "connection was not granted."
        )
        super().__init__(self.message)
        self.data = {
            "tool": tool_name,
            "requiredScope": required.value,
            "grantedScopes": sorted(s.value for s in principal.scopes),
            "binding": principal.binding,
        }


# --------------------------------------------------------------------------
# JSON-RPC / MCP envelopes
# --------------------------------------------------------------------------

def _result(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, *, data: dict | None = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _content(payload: dict, *, is_error: bool) -> dict:
    """A ``tools/call`` result: the canonical JSON as text, plus structured content.

    ``sort_keys`` and no whitespace padding, so the same call produces the same
    bytes — a determinism the test suite depends on and an agent's cache benefits
    from.
    """
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, sort_keys=True, ensure_ascii=False)}
        ],
        "structuredContent": payload,
        "isError": is_error,
    }
