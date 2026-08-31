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
* **Not wired, on purpose:** any *remotely reachable* connection **in any
  deployment that exists**. Two bindings can now serve a transport, and neither
  is reachable: ``local-loopback`` refuses every request whose socket peer is not
  a loopback address, refuses one that came through a proxy, and refuses a
  credential it cannot verify; ``oauth-resource-server`` (``oauth.py``) is
  ~~a complete OAuth 2.1 protected resource~~ **an OAuth 2.1 protected resource
  for the MCP authorization chapter** and **resolves to the unconfigured
  binding unless an operator supplies an issuer, a canonical resource URI and a
  verification key set** — none of which exists here, in any manifest, or in this
  repository at all. The DEFAULT binding mounts no route whatsoever, and
  ``ISAAC_MCP_DEPLOYMENT`` is unset in every deployment.

  *"Complete" is struck 2026-08-30, and this was the FOURTH site carrying it — the
  other three being ``oauth.py``'s module docstring, ``docs/mcp-capability-audit.md``
  §"Read the boundary precisely", and by implication ``jwt.py``'s ``typ`` note. The
  word named no chapter, so it read as covering a specification of which the module
  implements one part; and it was written while three JSON-RPC methods still
  answered before authentication. Both are corrected, and* ``oauth.py`` *now
  enumerates four deliberate divergences rather than implying none. The
  unreachability claim in this paragraph was true throughout and is unchanged.*

  Reachability (**D1**) and the authentication model (**D2**) are still
  outstanding infrastructure decisions and **``oauth.py`` did not answer either**.
  It makes them answerable: the application half is now reviewable code rather
  than a plan, and what remains — a firewall allowlist for Anthropic's egress
  range to *two* hosts, an issuer, a registered client — is external and is
  Dean's. See ``docs/mcp-oauth-operator-requirements-2026-08-27.md``.

  *This paragraph has been corrected twice, and both corrections are kept because
  each protected the same claim through a different mechanism. It first read "Not
  wired, on purpose: any transport, and therefore any real connection", which
  stopped being true when ``transport.py`` landed. It then named ``local-loopback``
  as "the one binding that serves a transport", which stopped being true when
  ``oauth.py`` landed. The thing being protected has never changed: **no
  scientist's Claude can reach hosted ISAAC until D1 and D2 are answered.***

The module map, in the order a reader should take them:

``policy``      the closed sets — scopes, operations, permitted tool names
``deployment``  who may call, and the unconfigured default that says nobody
``client``      the only path to ISAAC, hard-bound to the operation allowlist
``tools``       the tools and their schemas
``server``      JSON-RPC framing and the authorization checks around each call
``transport``   the HTTP endpoint, the entry guards, and the mount decision
``jwt``         JWS/JWT verification, standard library only, no network
``oauth``       the OAuth 2.1 protected-resource binding — disabled by default
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
