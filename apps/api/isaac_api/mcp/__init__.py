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
  and composition with the existing worked-example session scoping. No network, no
  credential, no new dependency.
* **Not wired, on purpose:** any transport, and therefore any real connection.
  Reachability (D1) and the authentication model (D2) are outstanding
  infrastructure decisions. :mod:`isaac_api.mcp.deployment` is the seam they drop
  into, and its default binding refuses honestly rather than defaulting open.

The module map, in the order a reader should take them:

``policy``      the closed sets — scopes, operations, permitted tool names
``deployment``  who may call, and the unconfigured default that says nobody
``client``      the only path to ISAAC, hard-bound to the operation allowlist
``tools``       the eight tools and their schemas
``server``      JSON-RPC framing and the authorization checks around each call
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

__all__ = [
    "ApiRefusal",
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
