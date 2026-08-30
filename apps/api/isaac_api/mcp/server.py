"""The MCP protocol surface: JSON-RPC 2.0 in, JSON-RPC 2.0 out, and nothing else.

WHY THIS IS HAND-ROLLED, AND WHAT IT DELIBERATELY DOES NOT DO
=============================================================
The slice's constraint was zero new dependencies, and an MCP **tool server** is a
small enough protocol to meet honestly: ``initialize``, ``tools/list``,
``tools/call``, ``ping``, ``server/discover``, and the JSON-RPC framing around
them.

THIS SERVER IS DUAL-ERA, AND THE TWO ERAS ARE NAMED BY THE SPECIFICATION
=======================================================================
Revision ``2026-07-28`` gives the two shapes names and says a server may serve
both: *"**Modern**: protocol versions that convey version, identity, and
capabilities as per-request metadata (revision ``2026-07-28`` and later).
**Legacy**: protocol versions that establish a session with an ``initialize``
handshake (``2025-11-25`` and earlier). **Dual-era**: an implementation that
supports both modern and legacy versions."* And: *"A server that wishes to
support both legacy clients (which expect an ``initialize`` handshake) and modern
clients (which use per-request metadata) **MAY** implement both behaviors."*

The selection rule is the specification's, quoted here as the two bullets it
actually is rather than compressed into a sentence: *"A dual-era **server**
selects its behavior from how the client opens: … A request carrying modern
per-request ``_meta`` is served statelessly according to this revision. … An
``initialize`` request selects legacy semantics, scoped to the stdio process
(stdio) or the session (HTTP), as specified by the negotiated legacy protocol
version."* It lives in :func:`protocol_era`, which is a pure function so the
transport and this module cannot disagree about which era a request is in.

**WHY THIS MATTERED ENOUGH TO BUILD.** Before it, this server implemented
``2025-06-18`` alone and :mod:`.transport` refused every other declared value with
a body of its own invention. A dual-era client would have fallen back to
``initialize`` and worked — but only because that body *happened* not to look like
a modern error, which the compatibility matrix keys the fallback on
(*"the modern request returns a ``4xx`` without a recognized modern error body,
and the client falls back to ``initialize``"*). It worked by accident. It now
works by design, and the accident is replaced by the real
``UnsupportedProtocolVersionError`` for a version that is genuinely unsupported —
which is what tells a modern client to retry rather than to give up.

EVERY METHOD AUTHENTICATES BEFORE IT DOES ANYTHING
==================================================
:meth:`McpServer.handle` authenticates **once, up front**, before the method is
dispatched, before an unknown method is named, and before a notification is
swallowed. That ordering is the fix for a real exposure: ``ping`` and
``notifications/initialized`` used to return a result *above* the first
``authenticate()`` call, and the unknown-method error published the whole
supported-method list. That was harmless while the only serving binding refused
non-loopback peers on the socket — and the OAuth binding sets
``requires_loopback_peer=False``, which removed the accident that was holding it
up. The specification's own words are unambiguous: *"authorization **MUST** be
included in every HTTP request from client to server."*

**A transport now ships, in ``transport.py``, and this module still has none.**
:meth:`McpServer.handle` takes a decoded JSON-RPC message and returns one; the
Streamable HTTP framing, the loopback guard and the HTTP status mapping all live
next door, so this file stays a pure message handler that a test can drive
directly. Two consequences a future session should not have to rediscover:

* the whole surface is exercisable locally and in CI with no network and no
  credential, which is why the test suite is deterministic; and
* ``ISAAC_MCP_DEPLOYMENT=local-loopback`` is the ONLY value that causes a route to
  exist. The paragraph here used to say a loopback binding "cannot expose anything
  remotely, because there is nothing listening"; that reason has expired, and the
  guarantee is now carried by ``transport.py``'s per-request peer check rather
  than by the absence of a listener. Unset — the default — still mounts nothing at
  all, and ``test_mcp_transport.py`` asserts it against the route table and the
  OpenAPI document.

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

import base64
import json
import logging
import re
from typing import Any, Mapping

from ..identity import IdentityRefusal, RequestIdentity
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

__all__ = [
    "ERA_LEGACY",
    "ERA_MODERN",
    "HEADER_MISMATCH",
    "LEGACY_PROTOCOL_VERSION",
    "MCP_PROTOCOL_VERSION",
    "MODERN_PROTOCOL_VERSION",
    "PROTOCOL_VERSION_META_KEY",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "UNSUPPORTED_PROTOCOL_VERSION",
    "McpServer",
    "protocol_era",
]

_log = logging.getLogger(__name__)

#: The modern revision. Per-request ``_meta``, no handshake, mandatory
#: ``server/discover``, and the revision whose authorization chapter mandates
#: RFC 9728 protected-resource metadata.
MODERN_PROTOCOL_VERSION = "2026-07-28"

#: The legacy revision this server has always spoken, and still does. Kept rather
#: than dropped because a legacy client has **no fall-forward mechanism** —
#: ``2026-07-28``'s own compatibility matrix records "Legacy client / Modern
#: server" as *"Fails"*, so dropping it would have broken every client that works
#: against this endpoint today in exchange for nothing.
LEGACY_PROTOCOL_VERSION = "2025-06-18"

#: **The version the LEGACY handshake answers with.** Unchanged, and the name is
#: kept because ``transport.py``, ``app.py`` and the test suite all read it as
#: "what ``initialize`` returns". It is deliberately NOT "the newest revision this
#: server supports" — that is :data:`MODERN_PROTOCOL_VERSION`, and conflating the
#: two would make ``initialize`` answer a revision that has no ``initialize``.
MCP_PROTOCOL_VERSION = LEGACY_PROTOCOL_VERSION

#: Every revision this server serves, newest first — the order a client reads out
#: of an :data:`UNSUPPORTED_PROTOCOL_VERSION` error's ``supported`` list and
#: ``server/discover``'s ``supportedVersions``.
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    MODERN_PROTOCOL_VERSION,
    LEGACY_PROTOCOL_VERSION,
)

#: The subset of the above that is served with modern (stateless, per-request
#: ``_meta``) semantics. A frozenset rather than a single string so adding the
#: next modern revision is one entry rather than a rewrite of :func:`protocol_era`.
MODERN_PROTOCOL_VERSIONS: frozenset[str] = frozenset({MODERN_PROTOCOL_VERSION})

#: The ``_meta`` key every modern request carries its protocol version in.
#: Prefixed, per the revision's ``_meta`` key naming rules.
PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"

#: Where ``server/discover`` puts :data:`SERVER_INFO`. *"``_meta``
#: ``['io.modelcontextprotocol/serverInfo']``: Name and version of the server
#: software. Servers **SHOULD** include this field."*
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"

#: HTTP header names the modern revision marks REQUIRED, lowercased for the
#: case-insensitive comparison it also mandates (*"Clients and servers **MUST**
#: use case-insensitive comparisons for header names"*).
PROTOCOL_VERSION_HEADER = "mcp-protocol-version"
METHOD_HEADER = "mcp-method"
NAME_HEADER = "mcp-name"

#: The revision's Base64 sentinel for a header value that cannot be carried as
#: plain ASCII: ``=?base64?{Base64EncodedValue}?=``. *"These markers are
#: case-sensitive and **MUST** appear exactly as shown (lowercase). Servers and
#: intermediaries that need to inspect these values **MUST** decode them
#: accordingly."*
_BASE64_SENTINEL_PREFIX = "=?base64?"
_BASE64_SENTINEL_SUFFIX = "?="

SERVER_INFO = {
    "name": "isaac-metadata-assistant",
    "title": "ISAAC Metadata Assistant",
    "version": "0.1.0",
}

#: One string, returned by BOTH ``initialize`` and ``server/discover``. A constant
#: rather than two literals because the two eras must describe the same server;
#: two copies is how a legacy client and a modern client end up being told
#: different things about what this endpoint will and will not do.
_INSTRUCTIONS = (
    "ISAAC's tools read and edit DRAFT metadata records. Nothing here "
    "finalises, exports, submits, deletes or migrates anything, and no "
    "such tool exists to be asked for. Values are never invented: a "
    "field without evidence stays missing or becomes a blocking "
    "question. Writes require the ETag from a prior read."
)

#: The standard JSON-RPC codes, which MCP uses unchanged: *"MCP uses the standard
#: JSON-RPC 2.0 error codes (``-32700``, ``-32600`` to ``-32603``) for general
#: protocol failures."*
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# --------------------------------------------------------------------------
# ISAAC's own two codes — MOVED OUT OF THE JSON-RPC RESERVED RANGE, 2026-08-30
# --------------------------------------------------------------------------
#
# ~~"The two above -32000 are this server's own, which the JSON-RPC specification
# reserves -32000..-32099 for."~~ **That reading of JSON-RPC was right and is no
# longer sufficient, and one of the two values was a straight MUST NOT under the
# revision this server now declares.**
#
# ``2026-07-28`` partitions the block JSON-RPC set aside:
#
# * *"``-32000`` to ``-32019`` — legacy. Codes in this sub-range were allocated by
#   implementations before this policy was introduced. New codes **MUST NOT** be
#   allocated in this sub-range, and new implementations **SHOULD NOT** use codes
#   from this sub-range at all."*
# * *"``-32020`` to ``-32099`` — reserved for the MCP specification. …
#   Implementations **MUST NOT** emit any code from this sub-range that is not
#   defined by this specification."*
#
# And, specifically: *"Codes defined by earlier protocol versions remain reserved
# and will not be reused. Implementations of this protocol version **MUST NOT**
# emit these codes: ``-32002`` — resource not found (2025-11-25 and earlier;
# replaced by ``-32602``)."*
#
# **THIS SERVER WAS EMITTING ``-32002`` FOR INSUFFICIENT SCOPE**, and the harm is
# not paper-thin: the same section tells clients they *"**SHOULD** still accept
# ``-32002``"* from older servers as **resource not found**, so a conforming
# client could read a scope refusal as a missing resource and retry, or report the
# wrong thing to a user. Declaring ``2026-07-28`` is what turned a collision into
# a MUST NOT, so the slice that declared it is the slice that fixes it.
#
# The specification names the destination: *"New error codes for purposes not
# defined by this specification **SHOULD** be allocated outside the JSON-RPC
# reserved range (``-32768`` to ``-32000``); the remainder of the integer space is
# available for application-defined errors."* ``-31001``/``-31002``/``-31003``
# sit just outside it, keep their ordinals, and cannot collide with anything MCP
# allocates later, because MCP allocates only inside the reserved range.
#
# **This is a wire change on an endpoint no deployment serves.** Every consumer in
# this repository reads the constant by name; the numbers appear as literals in one
# prose comment in a frontend test (``apps/web/src/__tests__/connect-your-agent.test.tsx``),
# which this slice does not touch.

#: The deployment boundary refused: nobody could be authenticated.
DEPLOYMENT_UNCONFIGURED = -31001
#: A principal exists but was not granted the scope this call costs.
INSUFFICIENT_SCOPE = -31002

#: **Allocated by the MCP specification, not by this server**, out of the
#: ``-32020``..``-32099`` sub-range it reserves for protocol-defined errors. This
#: server may emit them **only** with the meanings the specification gives them —
#: *"Implementations … **MUST** use defined codes only with their specified
#: meanings"* — which is why neither is reused for anything of ISAAC's.
#: ``-32020`` is ``HeaderMismatch``: *"The HTTP headers do not match the
#: corresponding values in the request body, or required headers are
#: missing/malformed."*
HEADER_MISMATCH = -32020
#: ``-32022`` is ``UnsupportedProtocolVersionError``. The message string is the
#: specification's own example text, verbatim, because a client that pattern-matches
#: on it should match.
UNSUPPORTED_PROTOCOL_VERSION = -32022
UNSUPPORTED_PROTOCOL_VERSION_MESSAGE = "Unsupported protocol version"

#: The two eras. Strings rather than an enum because :func:`protocol_era` is read
#: by ``transport.py`` for status mapping and a bare string keeps that seam free
#: of an import of this module's types.
ERA_LEGACY = "legacy"
ERA_MODERN = "modern"

#: Methods served under the legacy (`initialize`-handshake) semantics.
_LEGACY_METHODS = (
    "initialize",
    "notifications/initialized",
    "ping",
    "tools/list",
    "tools/call",
)

#: Methods served under the modern (stateless, per-request ``_meta``) semantics.
#: ``initialize`` and ``notifications/initialized`` are absent because the modern
#: revision has no handshake; ``server/discover`` is present because it
#: **replaces** one — *"Servers **MUST** implement ``server/discover``."*
_MODERN_METHODS = (
    "server/discover",
    "ping",
    "tools/list",
    "tools/call",
)

#: **THERE IS DELIBERATELY NO UNION CONSTANT.** ``_SUPPORTED_METHODS`` used to be
#: the single method table and is not replaced by a merged one, because the
#: per-era tuple is what a refusal must name: telling a legacy client about
#: ``server/discover`` advertises a method its revision has never heard of, and
#: telling a modern client about ``initialize`` sends it into a handshake this
#: revision removed. A union would exist only to be sliced, and the slice is what
#: is correct.

#: ``params`` keys ``tools/call`` accepts. Everything else is refused rather than
#: ignored, because a silently-ignored ``scopes`` key looks to a caller like a
#: request that was honoured.
_CALL_PARAM_KEYS = frozenset({"name", "arguments", "_meta"})


# --------------------------------------------------------------------------
# Era selection and the modern revision's header rules
# --------------------------------------------------------------------------

def _meta_of(params: Mapping[str, Any]) -> Mapping[str, Any]:
    meta = params.get("_meta")
    return meta if isinstance(meta, Mapping) else {}


def protocol_era(
    method: str,
    params: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> str:
    """:data:`ERA_MODERN` or :data:`ERA_LEGACY` for one request.

    **A pure function, and public, because two layers must agree.** This module
    decides which methods exist and which header rules apply; ``transport.py``
    decides whether an unknown method is ``404`` (modern) or ``200`` (legacy).
    Computing the era twice from two different rules is how those two answers
    drift apart, so it is computed once here and read from both.

    The rule is the specification's, in its order:

    * *"An ``initialize`` request selects legacy semantics, scoped to the stdio
      process (stdio) or the session (HTTP), as specified by the negotiated legacy
      protocol version."* — unconditionally here, even if the request also carries
      modern ``_meta``. That is what makes the dual-era fallback work: a client
      that fell back to ``initialize`` has *decided* it is speaking legacy, and
      second-guessing it from a stray ``_meta`` key would answer a handshake in a
      revision that has none.
    * ``server/discover`` exists only in the modern revision, so naming it is
      itself a modern opening.
    * *"a request carrying modern per-request ``_meta`` is served statelessly
      according to this revision"* — the ``_meta`` protocol version, or the
      ``MCP-Protocol-Version`` header naming a modern revision.
    * Anything else is legacy, which is the safe default: it is what this server
      did before it was dual-era.
    """
    if method == "initialize":
        return ERA_LEGACY
    if method == "server/discover":
        return ERA_MODERN
    if PROTOCOL_VERSION_META_KEY in _meta_of(params):
        return ERA_MODERN
    if headers is not None and headers.get(PROTOCOL_VERSION_HEADER) in MODERN_PROTOCOL_VERSIONS:
        return ERA_MODERN
    return ERA_LEGACY


#: What ``UnsupportedProtocolVersionError``'s ``data.requested`` may echo. A
#: protocol version is a date string; anything outside this shape is not one.
_ECHOABLE_VERSION = re.compile(r"\A[\x21-\x7E]{1,64}\Z")

#: What is echoed instead. A fixed string, so the field the specification requires
#: is still present and still says *which* declaration was rejected, without the
#: body carrying an arbitrary length of caller-controlled text.
_UNECHOABLE_VERSION = "<not a protocol version>"


def _echoable(version: str) -> str:
    """``version``, or a fixed placeholder.

    **THE ONLY PLACE IN THIS SURFACE WHERE CALLER TEXT REACHES A RESPONSE BODY,
    and it is bounded rather than trusted.** The specification's error shape
    requires ``data.requested`` — a client with two declarations needs to know
    which one was rejected — so the field cannot simply be dropped. What can be
    dropped is the assumption that the value is a version string: a caller can put
    anything in ``MCP-Protocol-Version``, including, by a plausible copy-paste
    accident, their bearer token.

    Reflecting that back is not a disclosure to anyone new — the sender already
    had it — but it makes this the one branch that turns the endpoint into a
    reflection primitive, and it breaks the rule the rest of the package holds:
    ``transport._refuse`` never interpolates caller text, ``jwt.py`` never
    interpolates token material, and ``_entry_refusal`` deliberately does not name
    the peer address it saw. One exception is how that habit is lost.

    Every real version passes through untouched — ``2026-07-28`` is eight
    printable characters.
    """
    return version if _ECHOABLE_VERSION.match(version) else _UNECHOABLE_VERSION


def _decode_header_value(raw: str) -> str | None:
    """A ``Mcp-Name`` / ``Mcp-Param-*`` value, Base64 sentinel decoded if present.

    ``None`` when the sentinel is present and its payload is not decodable — which
    is a header-validation failure, not a value to compare against.
    """
    if not (
        raw.startswith(_BASE64_SENTINEL_PREFIX) and raw.endswith(_BASE64_SENTINEL_SUFFIX)
    ):
        return raw
    encoded = raw[len(_BASE64_SENTINEL_PREFIX) : -len(_BASE64_SENTINEL_SUFFIX)]
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.b64decode(encoded + padding, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


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
        self,
        message: Mapping[str, Any],
        *,
        credential: Credential | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict | None:
        """One JSON-RPC request in, one response out (``None`` for a notification).

        ``headers`` is the request's HTTP headers, **lowercased**, or ``None`` when
        this server is being driven directly rather than over HTTP. The
        distinction is load-bearing rather than a convenience: the modern
        revision's ``Mcp-Method`` / ``Mcp-Name`` / ``MCP-Protocol-Version``
        requirements are requirements *of the Streamable HTTP binding*, so they
        apply when there is an HTTP request to apply them to and are silent when
        there is not. ``transport.py`` always passes a mapping — an empty one is
        still a mapping, and still fails the modern header rules, which is the
        point.

        **AUTHENTICATION HAPPENS FIRST AND IT HAPPENS FOR EVERY METHOD**, above
        the method table, above the unknown-method refusal and above the
        notification short-circuit. See the module docstring for what that
        replaced.
        """
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

        params = message.get("params") or {}
        if not isinstance(params, Mapping):
            return _error(request_id, INVALID_PARAMS, "params must be an object.")

        # --- the authorization boundary, before anything method-specific ------
        # Nothing above this line names a method, reveals which methods exist, or
        # produces a result. Everything below it has a principal.
        try:
            principal = self._binding.authenticate(credential)
        except DeploymentRefused as refusal:
            return self._refusal_envelope(request_id, refusal)

        era = protocol_era(method, params, headers)
        version_refusal = self._version_refusal(request_id, params, headers)
        if version_refusal is not None:
            return version_refusal
        if era == ERA_MODERN:
            header_refusal = self._header_refusal(request_id, method, params, headers)
            if header_refusal is not None:
                return header_refusal

        available = _MODERN_METHODS if era == ERA_MODERN else _LEGACY_METHODS
        if method not in available:
            if is_notification:
                # A notification gets no response, including no error response.
                # Unknown notifications are ignorable by specification.
                return None
            return _error(
                request_id,
                METHOD_NOT_FOUND,
                f"{method!r} is not a method this server implements.",
                # The era's OWN method list, not the union. Naming `initialize` to
                # a modern client would send it into a handshake this revision
                # removed, and naming `server/discover` to a legacy one would send
                # it to a method its revision has never heard of.
                data={"supported": list(available), "era": era},
            )

        if is_notification:
            # By specification a notification is never answered — not with a
            # result and not with an error. Every method above is idempotent or a
            # read, so there is nothing to run for its side effects.
            return None

        try:
            if method == "notifications/initialized":
                # Sent WITH an id, which is a client bug rather than ours.
                # Answered benignly instead of erroring on the handshake.
                return _result(request_id, {})
            if method == "ping":
                return _result(request_id, {})
            if method == "initialize":
                return _result(request_id, self._initialize(principal))
            if method == "server/discover":
                return _result(request_id, self._discover(principal))
            if method == "tools/list":
                return _result(request_id, self._tools_list(principal))
            return _result(
                request_id, await self._tools_call(params, principal=principal)
            )
        except DeploymentRefused as refusal:  # pragma: no cover - authenticated above
            return self._refusal_envelope(request_id, refusal)
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

    # -- negotiation ---------------------------------------------------------

    def _refusal_envelope(self, request_id: Any, refusal: DeploymentRefused) -> dict:
        return _error(
            request_id,
            DEPLOYMENT_UNCONFIGURED,
            refusal.message,
            data={
                "code": refusal.code,
                **refusal.data,
                # The refusal's OWN challenge when it has one, else the
                # binding's generic one. Written after the spread so a
                # `challenge` key inside `refusal.data` cannot displace it,
                # and `or` rather than a conditional because an empty dict is
                # not a usable challenge either.
                #
                # Both shipped bindings pass `challenge=None` and so are
                # unaffected. It matters for a binding that must distinguish
                # "no credential was presented" from "this credential is bad"
                # — RFC 6750 §3 says the first carries no `error` and the
                # second does, and one challenge per binding cannot say both.
                "challenge": refusal.challenge or self._binding.challenge(),
            },
        )

    def _version_refusal(
        self,
        request_id: Any,
        params: Mapping[str, Any],
        headers: Mapping[str, str] | None,
    ) -> dict | None:
        """The real ``UnsupportedProtocolVersionError``, or ``None``.

        *"If the server does not implement the requested version (whether the
        version is unknown to the server, or is a known version the server has
        chosen not to support), it **MUST** respond with an
        ``UnsupportedProtocolVersionError`` listing the versions it does
        support."*

        **THE LEGACY HANDSHAKE CANNOT REACH THIS, AND THAT IS DELIBERATE.** A
        legacy client declares its revision in ``initialize``'s
        ``params.protocolVersion``, which this function never reads; only the
        ``_meta`` field and the HTTP header — both of which a legacy client sends
        either correctly or not at all — can produce the modern error. Emitting it
        on the handshake path would break the fallback the compatibility matrix
        keys on a ``4xx`` *without* a recognized modern error body.
        """
        declared: list[str] = []
        header_version = headers.get(PROTOCOL_VERSION_HEADER) if headers else None
        if isinstance(header_version, str) and header_version:
            declared.append(header_version)
        meta_version = _meta_of(params).get(PROTOCOL_VERSION_META_KEY)
        if meta_version is not None and not isinstance(meta_version, str):
            return _error(
                request_id,
                INVALID_PARAMS,
                f"params._meta[{PROTOCOL_VERSION_META_KEY!r}] must be a string.",
            )
        if meta_version:
            declared.append(meta_version)
        for version in declared:
            if version not in SUPPORTED_PROTOCOL_VERSIONS:
                return _error(
                    request_id,
                    UNSUPPORTED_PROTOCOL_VERSION,
                    UNSUPPORTED_PROTOCOL_VERSION_MESSAGE,
                    data={
                        "supported": list(SUPPORTED_PROTOCOL_VERSIONS),
                        # Bounded, not trusted — see `_echoable`. A real version
                        # is unchanged by this.
                        "requested": _echoable(version),
                    },
                )
        return None

    def _header_refusal(
        self,
        request_id: Any,
        method: str,
        params: Mapping[str, Any],
        headers: Mapping[str, str] | None,
    ) -> dict | None:
        """``HeaderMismatch``, or ``None``. **Modern era only.**

        The revision's Server Validation rules, applied in its own words:
        *"Every POST request to the MCP endpoint **MUST** include an
        ``MCP-Protocol-Version`` header"*; *"The header value **MUST** match the
        ``io.modelcontextprotocol/protocolVersion`` field carried in the request
        body's ``_meta``"*; and the standard-header table making ``Mcp-Method``
        required for all requests and ``Mcp-Name`` required for ``tools/call``.
        *"Servers **MUST** reject requests with a ``400 Bad Request`` HTTP status
        and JSON-RPC error code ``-32020`` (``HeaderMismatch``) if any validation
        fails."*

        These are requirements of the HTTP binding, so ``headers is None`` — this
        server driven in-process — skips them entirely rather than inventing a
        failure for a request that has no headers to get wrong.

        **ONE PLACE THE SPECIFICATION IS SILENT AND THIS BUILD CHOOSES, NAMED
        RATHER THAN LEFT AS AN ACCIDENT.** The transport chapter says of
        notification POSTs: *"header requirements for notification POSTs are not
        defined by this revision."* This function applies the same rules to a
        notification as to a request, which is the fail-closed reading. It costs
        no conforming client anything, because the same chapter says *"This
        revision of the core protocol defines no client-to-server notifications
        over Streamable HTTP"* — so a modern notification is a message no modern
        client sends. The alternative, exempting notifications, would create a
        shape that skips header validation and is answered ``202``, which is a
        worse thing to have than a refusal nobody triggers.
        """
        if headers is None:
            return None

        def mismatch(detail: str) -> dict:
            return _error(request_id, HEADER_MISMATCH, detail)

        header_version = headers.get(PROTOCOL_VERSION_HEADER)
        if not header_version:
            return mismatch(
                "Header mismatch: MCP-Protocol-Version is required on every "
                f"request in revision {MODERN_PROTOCOL_VERSION} and was not sent."
            )
        meta_version = _meta_of(params).get(PROTOCOL_VERSION_META_KEY)
        if isinstance(meta_version, str) and meta_version != header_version:
            # Neither value is echoed. Both are protocol version strings and so
            # carry nothing sensitive, but the vocabulary of this file is that a
            # refusal states the rule rather than reflecting the input, and one
            # exception is how the habit is lost.
            return mismatch(
                "Header mismatch: the MCP-Protocol-Version header does not match "
                f"the {PROTOCOL_VERSION_META_KEY} field in the request body."
            )

        declared_method = headers.get(METHOD_HEADER)
        if declared_method is None:
            return mismatch("Header mismatch: Mcp-Method is required and was not sent.")
        if declared_method != method:
            return mismatch(
                "Header mismatch: the Mcp-Method header does not match the "
                "request body's method."
            )

        if method == "tools/call":
            name = params.get("name")
            if isinstance(name, str):
                raw = headers.get(NAME_HEADER)
                if raw is None:
                    return mismatch(
                        "Header mismatch: Mcp-Name is required on a tools/call "
                        "request and was not sent."
                    )
                if _decode_header_value(raw) != name:
                    return mismatch(
                        "Header mismatch: the Mcp-Name header does not match "
                        "params.name in the request body."
                    )
        return None

    # -- methods ------------------------------------------------------------

    def _initialize(self, principal: Principal) -> dict:
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            # Only what is implemented. `listChanged` is false because the tool set
            # is frozen at import; claiming it and never sending the notification
            # would be a contract this server does not keep.
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": dict(SERVER_INFO),
            "instructions": _INSTRUCTIONS,
            "_isaac": self._isaac_block(principal),
        }

    def _discover(self, principal: Principal) -> dict:
        """``server/discover``. *"Servers **MUST** implement it."*

        **IT IS A PROTECTED RESOURCE LIKE EVERYTHING ELSE.** A client is free to
        call it before any other request, and that is a statement about protocol
        ordering, not about authorization: :meth:`handle` has already
        authenticated by the time this runs, so an unauthenticated caller gets the
        ``401`` and its challenge rather than this server's capability list.

        The result's shape is the revision's ``DiscoverResult``:
        ``supportedVersions``, ``capabilities``, ``instructions``, and
        ``serverInfo`` under its ``_meta`` key — which the specification marks
        ``SHOULD`` include, and also warns is *"self-reported by the server and is
        not verified by the protocol"*, so it is deliberately the same fixed
        dictionary ``initialize`` has always returned and carries nothing derived
        from the caller.

        ``resultType: "complete"`` because this server pages nothing: the tool set
        is frozen at import, so there is never a second page to fetch. No
        ``ttlMs``/``cacheScope`` is emitted — the capability list is fixed for the
        process, but the GRANTED-scope block below it is not, so telling a shared
        cache the whole document may be reused would be wrong for the half that
        varies per token.
        """
        return {
            "resultType": "complete",
            "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "capabilities": {"tools": {"listChanged": False}},
            "instructions": _INSTRUCTIONS,
            "_meta": {SERVER_INFO_META_KEY: dict(SERVER_INFO)},
            "_isaac": self._isaac_block(principal),
        }

    def _isaac_block(self, principal: Principal) -> dict:
        """What this connection is, in ISAAC's own vocabulary.

        ``trustTier`` and ``trustBasis`` come from the identity plane rather than
        from this module's opinion, which is the whole reason
        :meth:`request_identity` exists: the binding decides what a verified
        credential is worth, and this surface reports it rather than restating it.
        """
        identity = self.request_identity(principal)
        block = {
            "binding": principal.binding,
            "grantedScopes": sorted(s.value for s in principal.scopes),
            "workspaceScope": (
                "worked-example-session"
                if principal.tutorial_session_id
                else "ordinary"
            ),
            "trustTier": identity.trust.value,
        }
        if identity.service is not None:
            block["trustBasis"] = identity.service.trust_basis
        if identity.refusal is not None:
            block["trustRefusal"] = identity.refusal.value
        return block

    def request_identity(self, principal: Principal) -> RequestIdentity:
        """The identity-plane view of an authenticated MCP caller.

        **THIS IS THE CALL SITE ``identity.py`` DESCRIBES**, and it did not exist
        when that description was written: ``ServicePrincipal``'s docstring said
        the OAuth binding *"builds one … at the MCP transport boundary"* while
        ``oauth.py``'s ``service_identity`` had zero production callers. Prose
        describing behaviour nothing performs is worse than no prose, so either
        this had to exist or that had to be deleted.

        A binding without a ``service_identity`` — both shipped ones — yields
        ``UNTRUSTED`` with :attr:`~..identity.IdentityRefusal.NO_VERIFIER_CONFIGURED`,
        which is the truthful answer for ``local-loopback``: a socket-peer address
        is an *access* control and identifies nobody.

        **A SERVICE PRINCIPAL CAN NEVER BE AN AUTHOR**, and this method does not
        arrange that — it inherits it. ``require_human_actor`` reads
        :attr:`~..identity.RequestIdentity.human`, which is ``None`` on this tier;
        ``stamp_actor`` reads the same field; and
        :class:`~..identity.ServicePrincipal` has no ``subject`` attribute for a
        stamping call site to reach for by mistake. Asserted through this exact
        path in ``test_mcp_oauth_binding.py`` rather than against a
        hand-constructed object.
        """
        builder = getattr(self._binding, "service_identity", None)
        if builder is None:
            return RequestIdentity.untrusted(IdentityRefusal.NO_VERIFIER_CONFIGURED)
        return builder(principal)

    def _tools_list(self, principal: Principal) -> dict:
        return {
            "tools": [
                tool.descriptor()
                for name, tool in sorted(TOOLS.items())
                # `permits_all`, not `permits`: the listing must show exactly the
                # tools a call would succeed for. A tool listed and then refused
                # teaches an agent that the server is unreliable, and a tool
                # hidden that would have worked wastes the grant.
                if principal.permits_all(tool.required_scopes)
            ]
        }

    async def _tools_call(
        self, params: Mapping[str, Any], *, principal: Principal
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

        missing = principal.missing(tool.required_scopes)
        if missing:
            raise _ScopeDenied(tool, missing, principal)

        arguments = params.get("arguments", {})
        accepted = validate_arguments(tool.input_schema, arguments)

        # The identity travels WITH the call rather than being recomputed by a
        # handler that wanted it. No handler reads it today; what it buys is that
        # a handler which one day needs to know whether a person is present cannot
        # answer that question by looking at a header, because there is no header
        # here — there is a `RequestIdentity` whose tier is `SERVICE` and whose
        # `human` is `None`.
        context = ToolContext(
            client=self._client_factory(principal),
            identity=self.request_identity(principal),
        )
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
    """Refused for scope. Names every missing scope, not the first one found.

    ``requiredScope`` stays the tool's DEFINING scope — the one that separates it
    from a read tool — because that is the field clients and tests already read.
    ``requiredScopes`` and ``missingScopes`` carry the complete picture beside it,
    so a caller can request a grant that will actually be sufficient rather than
    discovering the second missing scope on the retry.
    """

    def __init__(self, tool, missing: frozenset[Scope], principal: Principal) -> None:
        missing_values = sorted(s.value for s in missing)
        self.message = (
            f"{tool.name!r} requires the scope(s) "
            f"{sorted(s.value for s in tool.required_scopes)}, and this connection "
            f"was not granted {missing_values}."
        )
        super().__init__(self.message)
        self.data = {
            "tool": tool.name,
            "requiredScope": tool.scope.value,
            "requiredScopes": sorted(s.value for s in tool.required_scopes),
            "missingScopes": missing_values,
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
