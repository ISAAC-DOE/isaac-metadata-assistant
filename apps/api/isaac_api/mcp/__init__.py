"""ISAAC's MCP tool server: least-privilege tools over ISAAC's own HTTP API.

ONE-WAY, AND THAT IS THE PRODUCT FACT
=====================================
A scientist's own Claude calls these tools, billed to that scientist's own
subscription. ISAAC gets no inference from the connection — MCP servers answer
clients, they do not call models (``docs/mcp-capability-audit.md`` §1). Anything
that implies otherwise on a product screen is false.

WHAT IS AND IS NOT WIRED
========================
* **Wired, and fully exercisable locally and in CI:** the tool layer, the scope
  model, the operation allowlist, the argument validation, the JSON-RPC surface,
  composition with the existing worked-example session scoping, and — since
  ``transport.py`` — a **Streamable HTTP endpoint that a real MCP client can
  actually speak to**, mounted only when ``ISAAC_MCP_DEPLOYMENT`` resolves to a
  binding that serves one. No network egress, no credential, no new dependency.
* **Not wired, on purpose:** any *remotely reachable* connection. The one binding
  that serves a transport, ``local-loopback``, refuses every request whose socket
  peer is not a loopback address, refuses one that came through a proxy, and
  refuses a credential it cannot verify. Reachability (D1) and the authentication
  model (D2) are still outstanding infrastructure decisions;
  :mod:`isaac_api.mcp.deployment` is the seam they drop into, and the DEFAULT
  binding mounts no route at all rather than mounting one that refuses.

  *This paragraph previously read "Not wired, on purpose: any transport, and
  therefore any real connection." It is corrected rather than deleted, because
  the thing it was protecting — that no scientist's Claude can reach hosted ISAAC
  until Dean answers D1 and D2 — is unchanged. Only the mechanism moved.*

The module map, in the order a reader should take them:

``policy``      the closed sets — scopes, operations, permitted tool names
``deployment``  who may call, and the unconfigured default that says nobody
``client``      the only path to ISAAC, hard-bound to the operation allowlist
``tools``       the tools and their schemas
``server``      JSON-RPC framing and the authorization checks around each call
``transport``   the HTTP endpoint, the loopback guard, and the mount decision
"""

from __future__ import annotations

from .client import ApiRefusal, ApiResult, AsgiApiClient, IsaacApiClient
from .deployment import (
    Credential,
    DeploymentBinding,
    DeploymentRefused,
    LocalLoopbackDeployment,
    Principal,
    UnconfiguredDeployment,
    resolve_binding,
)
from .policy import OPERATIONS, PERMITTED_TOOL_NAMES, Operation, Scope
from .server import MCP_PROTOCOL_VERSION, McpServer
from .tools import TOOLS, Tool, registered_tool_names
from .transport import MCP_PATH, McpHttpTransport, mcp_transport_or_none

__all__ = [
    "ApiRefusal",
    "MCP_PATH",
    "McpHttpTransport",
    "mcp_transport_or_none",
    "ApiResult",
    "AsgiApiClient",
    "Credential",
    "DeploymentBinding",
    "DeploymentRefused",
    "IsaacApiClient",
    "LocalLoopbackDeployment",
    "MCP_PROTOCOL_VERSION",
    "McpServer",
    "OPERATIONS",
    "Operation",
    "PERMITTED_TOOL_NAMES",
    "Principal",
    "Scope",
    "TOOLS",
    "Tool",
    "UnconfiguredDeployment",
    "registered_tool_names",
    "resolve_binding",
]
