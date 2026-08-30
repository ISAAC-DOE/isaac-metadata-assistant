"""The Streamable HTTP transport: the thing that makes the tools reachable.

WHY STREAMABLE HTTP AND NOT STDIO
=================================
:meth:`~.server.McpServer.handle` already takes one decoded JSON-RPC message and
returns one. That is precisely the contract of a Streamable HTTP ``POST``, and it
is *not* the contract of stdio, which needs a framing loop, a process lifetime and
a second copy of the application. Three further reasons, in the order they
mattered:

1. **The tools call ISAAC in-process.** ``client.py`` reaches the routes over
   ``httpx.ASGITransport`` against the live FastAPI application object. A stdio
   server is a separate process, so it would have to construct a *second*
   application — a second workspace, a second lock map, a second view of every
   record. Two writers to one workspace with independent per-record locks is a
   lost-update bug, not a transport choice.
2. **The gate would have nowhere to live.** ISAAC's whole MCP safety story is one
   configuration seam (``deployment.py``). A stdio entry point is reachable by
   anybody who can execute the module; the gate would become "did the operator
   choose not to run it", which is not a gate.
3. **It is what the clients speak.** ``claude mcp add --transport http`` is the
   documented shape, and the audit records the SSE-only transport as deprecated
   (``docs/mcp-capability-audit.md`` §2).

WHAT IS DELIBERATELY NOT IMPLEMENTED, AND WHY EACH IS A REFUSAL
===============================================================
* **``GET`` (the server-initiated SSE stream)** — ``405``. The specification
  permits a server with no server-initiated messages to refuse it, and this server
  has none: the tool set is frozen at import, so there is no ``listChanged``, and
  sampling and elicitation are absent on purpose (``server.py``). Returning an
  empty stream would be a channel that exists so a client can wait on it forever.
* **Sessions (``Mcp-Session-Id``)** — never issued, so ``DELETE`` is ``405`` too.
  Every request re-authenticates through the binding; a session id would be a
  bearer of authority minted by this layer, which is the one thing an unanswered
  D2 must not produce.
* **JSON-RPC batching** — ``400``. Revision ``2025-06-18`` removed it. Accepting a
  batch would mean deciding what a partially-authorized batch returns, which is a
  security question nobody has been asked.
* ~~**A protected-resource-metadata document** — not published, and no
  ``WWW-Authenticate`` is fabricated.~~ **NARROWED, NOT REVERSED.** The rule that
  motivated it is unchanged and is now enforced in a stronger place: *a challenge
  pointing at an authorization server that does not exist is worse than no
  challenge*, so the two shipped bindings still return an empty challenge and
  **no header is emitted** (:meth:`~.deployment.UnconfiguredDeployment.challenge`,
  :meth:`~.deployment.LocalLoopbackDeployment.challenge`). What changed is that a
  binding which *does* have an authorization server can now publish one:
  ``oauth.py`` serves RFC 9728 metadata and emits the challenge, and
  :func:`metadata_routes_or_none` registers those paths **only** for a binding
  that asks for them — which is none by default, so an unconfigured deployment
  still publishes nothing at all.
* **A token in the query string** — ``400``, refused rather than ignored. The MCP
  specification says access tokens *"**MUST NOT** be included in the URI query
  string"* — **as an obligation on the CLIENT**, in its list of client
  requirements, and OAuth 2.1 §5.1 defines no query-parameter method at all for a
  resource server to have an opinion about. So this ``400`` is ISAAC's own choice
  and not a conformance requirement, which is worth being exact about because
  refusing is a divergence from the obvious alternative. Ignoring the parameter
  would be defensible and useless: by the time the request arrives the token is
  already in whatever access logs sit in front of this process, and a client doing
  it needs to be told to stop rather than quietly served. See
  :data:`QUERY_TOKEN_PARAMETERS`.

RAW ASGI, WITH NO IMPORT OF STARLETTE OR FASTAPI
================================================
The transport is a bare ``async def __call__(scope, receive, send)``. That is not
minimalism for its own sake: ``test_mcp_boundaries.py`` asserts that this package
imports no third-party module except ``httpx``, and the assertion is worth more
than the convenience of ``Request``/``JSONResponse``. It also means the guards
below run against the ASGI scope itself — ``scope["client"]`` is the kernel's idea
of the peer, not a header anybody can write.

The application's own middleware still wraps this, because middleware is added to
the app and the route lives inside it. So when ``ISAAC_UI_API_KEY`` is set,
``ApiKeyAuthMiddleware`` guards this path as well. That combination does not work,
and it fails in the safe direction: the app demands its key in ``Authorization``,
this transport hands whatever is in ``Authorization`` to the binding as a
:class:`~.deployment.Credential`, and the loopback binding refuses a credential it
cannot verify. A misconfiguration that produces an honest refusal is the correct
outcome; ``test_mcp_transport.py`` pins it so nobody later "fixes" it by teaching
the transport to recognise and swallow the app's own key.

THE FOUR AXES THIS FAILS CLOSED ON
==================================
1. **Deployment unresolved** → no route is registered at all. Not a 403: an absent
   path. :func:`mcp_transport_or_none` returns ``None`` and ``app.py`` registers
   nothing.
2. **Peer not loopback** → ``403``, before the method is looked at and before the
   body is read, so a caller this binding will not serve cannot learn from a
   ``405`` that ISAAC speaks MCP here. Includes the case
   where ASGI reports no peer at all, and the case where a proxy header is
   present (a loopback peer behind a proxy tells you nothing about the origin).
3. **Origin present and not loopback** → ``403``. This is the DNS-rebinding
   defence the specification requires of a local server: the peer check alone
   passes a page on ``https://evil.example`` that posts to ``127.0.0.1``.
4. **Credential present but unverifiable** → ``401`` from the binding, with no
   fabricated challenge.

Nothing here is default-allow. Every branch that does not positively establish a
condition returns a refusal.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any, Awaitable, Callable, Iterable, Mapping
from urllib.parse import unquote_plus, urlsplit

from .deployment import Credential, DeploymentBinding, resolve_binding
from .server import (
    DEPLOYMENT_UNCONFIGURED,
    ERA_MODERN,
    HEADER_MISMATCH,
    INSUFFICIENT_SCOPE,
    METHOD_NOT_FOUND,
    UNSUPPORTED_PROTOCOL_VERSION,
    McpServer,
    protocol_era,
)

__all__ = [
    "MAX_REQUEST_BYTES",
    "MCP_PATH",
    "QUERY_TOKEN_PARAMETERS",
    "McpHttpTransport",
    "TRANSPORT_REFUSED",
    "is_loopback_host",
    "mcp_transport_or_none",
    "metadata_routes_or_none",
]

_log = logging.getLogger(__name__)

#: The single endpoint, relative to the deployment's base path. One path for the
#: whole protocol is the Streamable HTTP shape; ``app.py`` prefixes it with
#: ``ISAAC_BASE_PATH``.
MCP_PATH = "/api/mcp"

#: This layer's JSON-RPC error code, and the third of ISAAC's three.
#:
#: **MOVED OUT OF THE JSON-RPC RESERVED RANGE, 2026-08-30, with the other two.**
#: ~~"JSON-RPC reserves -32000..-32099 for implementation-defined errors"~~ is
#: true of JSON-RPC and no longer sufficient: ``2026-07-28`` partitions that block
#: and leaves an implementation nowhere in it — ``-32000``..``-32019`` is a legacy
#: sub-range *"new implementations **SHOULD NOT** use … at all"*, and
#: ``-32020``..``-32099`` is reserved for the specification's own codes. See
#: ``server.py``'s error-code block for the full quotation and for the one value
#: (``-32002``) that was a MUST NOT rather than a SHOULD NOT.
#:
#: ``test_mcp_transport.py`` asserts the three are distinct AND outside the
#: reserved range: a duplicated code is a client mis-branching on an authorization
#: failure, and a reserved one is a client branching on somebody else's meaning.
TRANSPORT_REFUSED = -31003

#: Request body cap. The largest legitimate message is a ``tools/call`` whose
#: arguments are a handful of scalars and one flat ``fields`` object; a megabyte
#: is orders of magnitude more than that and still small enough that a hostile
#: caller cannot use this endpoint to occupy memory.
MAX_REQUEST_BYTES = 1_048_576

#: Headers whose mere presence means a proxy handled this request. Their VALUES
#: are never read, and that is the point — ``CLAUDE.md`` records that ISAAC's
#: Service is a plain ClusterIP with no NetworkPolicy, so a forwarded header is
#: forgeable by any in-cluster caller. Presence is used as evidence that the
#: socket peer is not the originator, which is a refusal; a value is never used as
#: evidence of anything, which would be trust.
PROXY_HEADERS = (
    b"forwarded",
    b"x-forwarded-for",
    b"x-forwarded-host",
    b"x-forwarded-proto",
    b"x-real-ip",
)

#: Query-parameter names that carry, or have historically carried, a bearer
#: token. Their presence is a refusal on every binding — see the module
#: docstring. The VALUE is never read, never decoded and never logged; only the
#: NAME is looked at, so nothing this refusal does can put a credential anywhere.
#:
#: **WHOSE OBLIGATION THIS IS — CORRECTED 2026-08-30, because the previous comment
#: had it backwards and the correction changes what may be claimed, not what the
#: code does.** ~~"which OAuth 2.1 removes and the MCP specification forbids in as
#: many words"~~ is right about MCP and wrong about who is bound:
#:
#: * MCP's authorization chapter states it in a numbered list of **client**
#:   requirements — *"2. Access tokens **MUST NOT** be included in the URI query
#:   string"* — under *"MCP client **MUST** use the Authorization request header
#:   field"*. It is an obligation on the sender.
#: * OAuth 2.1 (draft-ietf-oauth-v2-1-13) **§5.1 has exactly two subsections** —
#:   ``5.1.1`` Authorization Request Header Field and ``5.1.2`` Form-Encoded
#:   Content Parameter. RFC 6750 §2.3's *"URI Query Parameter"* method is simply
#:   **absent**; the draft was re-read on 2026-08-30 and **contains no sentence
#:   saying a resource server MUST ignore, or MUST reject, a token in the query
#:   string.** There is no server-side rule here to conform to or to diverge from.
#:
#: So refusing with ``400`` is **ISAAC's choice**, made freely rather than under a
#: MUST, and the module docstring gives the reason: by the time the request
#: arrives the credential is already in every access log in front of this process,
#: and a client doing it needs to be told to stop rather than quietly served.
#:
#: ``access_token`` is RFC 6750 §2.3's own parameter name. **``bearer_token``,
#: ``token`` and ``apikey`` are not OAuth parameters at all**, and are kept
#: deliberately after re-examination: they are the names credential-bearing query
#: parameters carry in the wild, this endpoint reads **no** query parameter for
#: any purpose, and so refusing them costs a legitimate caller nothing. A
#: parameter that is never read cannot be a parameter this refusal takes away.
QUERY_TOKEN_PARAMETERS = ("access_token", "bearer_token", "token", "apikey")

_JSON_CONTENT_TYPE = "application/json"


# --------------------------------------------------------------------------
# Loopback, decided on the socket and nowhere else
# --------------------------------------------------------------------------

def is_loopback_host(host: str | None) -> bool:
    """Whether ``host`` is a loopback ADDRESS. Fail-closed on anything else.

    Deliberately not a name resolver and deliberately not a string comparison
    against ``"localhost"``:

    * a resolver turns an attacker-chosen name into a lookup this process
      performs, and a name that resolves to ``127.0.0.1`` today may not tomorrow;
    * ``"localhost"`` is accepted, but only as a literal, because it is the one
      name that cannot be repointed without editing the machine's own hosts file
      — at which point the attacker already has the machine.

    ``::ffff:127.0.0.1`` is handled explicitly. Python reports
    ``IPv6Address('::ffff:127.0.0.1').is_loopback`` as **False**, which is correct
    for the v6 loopback question and wrong for the one being asked here: a dual
    stack listener reports v4 loopback peers in exactly that form, so without the
    unmapping every loopback client on such a listener would be refused.
    """
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return address.is_loopback


def _origin_is_loopback(origin: str) -> bool:
    """Whether an ``Origin`` header names a loopback host.

    ``"null"`` is refused: it is what a sandboxed iframe, a ``file://`` document
    and several redirect chains send, and none of those is a caller this endpoint
    should serve.
    """
    if not origin or origin == "null":
        return False
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https"):
        return False
    host = parts.hostname  # already strips [] from a v6 literal and lowercases
    return is_loopback_host(host)


# --------------------------------------------------------------------------
# The transport
# --------------------------------------------------------------------------

class McpHttpTransport:
    """A Streamable HTTP endpoint over one :class:`~.server.McpServer`.

    Constructed only by :func:`mcp_transport_or_none`, which is the one place the
    mount decision is made.
    """

    def __init__(self, server: McpServer, binding: DeploymentBinding) -> None:
        self._server = server
        self._binding = binding
        # Read once, with the SAFE default, so a binding that never declares it
        # gets the narrow behaviour rather than the wide one.
        #
        # NAME UNDERSTATES SCOPE: this one flag gates THREE guards in
        # `_handle_http` — the socket-peer check, the proxy-header refusal and the
        # cross-origin/DNS-rebinding refusal. The comment at that `if` says why
        # that matters and why splitting them is a follow-up rather than this
        # slice.
        self._loopback_only = bool(getattr(binding, "requires_loopback_peer", True))
        # THE OTHER TWO THIRDS OF WHAT THAT FLAG USED TO MEAN. Each read with the
        # SAFE default, so a binding that declares neither gets both — which is
        # what every binding written before the split already had.
        self._refuse_proxied = bool(getattr(binding, "refuses_proxy_headers", True))
        self._loopback_origin_only = bool(
            getattr(binding, "requires_loopback_origin", True)
        )

    # -- ASGI -----------------------------------------------------------------

    async def __call__(self, scope: Mapping[str, Any], receive, send) -> None:
        kind = scope.get("type")
        if kind == "websocket":
            # This protocol is not offered over websockets. Closing is the only
            # correct answer; an HTTP response on a websocket scope is a crash.
            await send({"type": "websocket.close", "code": 1008})
            return
        if kind != "http":
            # Starlette routes nothing but ``http`` and ``websocket`` to a route's
            # ASGI app today. Doing nothing with an unrecognised scope type is the
            # fail-closed direction for one it starts routing tomorrow.
            return
        await self._handle_http(scope, receive, send)

    async def _handle_http(self, scope: Mapping[str, Any], receive, send) -> None:
        headers = _Headers(scope.get("headers") or ())

        # No path check here, deliberately. The application registers this as an
        # EXACT route rather than a prefix mount, so `/api/mcp/anything` is a 404
        # from the router and never reaches this object — one path-matching
        # implementation instead of two that can disagree. `app.py` explains the
        # choice; `test_mcp_transport.py` asserts the sub-path 404.

        # FIRST, BEFORE THE METHOD CHECK AND BEFORE THE BODY IS READ. The order is
        # deliberate and was wrong once: with the method check first, a caller from
        # off loopback got `405 Allow: POST` naming this as an MCP endpoint — a
        # refusal that still answers "does ISAAC speak MCP here?" for a scanner
        # that never sent a POST. A caller this binding will not serve learns
        # nothing from a verb. The module docstring's axis 2 ("Peer not loopback ->
        # 403, before the body is read") and `deployment.py` both state this order;
        # `test_mcp_transport.py` pins a non-loopback GET at 403.
        #
        # ONE FLAG USED TO GATE THREE GUARDS. IT NOW GATES ONE, AND THE OTHER TWO
        # HAVE THEIR OWN. The old comment here warned that whoever wrote the first
        # internet-adjacent binding would set `requires_loopback_peer=False` for
        # the peer check and silently lose the proxy-header and DNS-rebinding
        # defences with it. `oauth.py` is that binding, so the split was made
        # rather than the warning re-read: `deployment.DeploymentBinding` declares
        # three attributes, each defaulting to the SAFE value, and a new binding
        # answers all three questions with its own reason.
        #
        # Nothing about the two shipped bindings moves. `local-loopback` declares
        # all three True — which is exactly what one flag set to True already gave
        # it — and the unconfigured binding serves no route at all.
        refusal = self._entry_refusal(scope, headers)
        if refusal is not None:
            code, message = refusal
            # Logged at INFO with no peer address and no header value: the
            # operator needs to know the guard fired, and a log line naming a
            # remote address is a record this application has no reason to keep.
            _log.info("MCP transport refused a request: %s", code)
            await self._refuse(send, 403, code, message)
            return

        # AFTER the entry guards, so a caller this binding will not serve learns
        # nothing extra from it, and BEFORE everything else, because a request
        # that put a credential in its URL must not be processed as though it had
        # not. 400, per the specification's own status table: this is a malformed
        # authorization request, not a failed one. The parameter's VALUE is never
        # read, so this refusal cannot itself become the thing that logs a token.
        offending = _query_token_parameter(scope)
        if offending is not None:
            _log.info("MCP transport refused a request: token_in_query_string")
            await self._refuse(
                send,
                400,
                "token_in_query_string",
                "An access token may never be sent in the URI query string. Put "
                "it in the Authorization header. This request was refused rather "
                "than served without it, because the credential has already "
                "reached every access log in front of this process and the "
                "client needs to stop doing it.",
                data={"parameter": offending},
            )
            return

        method = (scope.get("method") or "").upper()
        if method != "POST":
            # Named individually so the refusal explains the design rather than
            # reading as an omission.
            reason = {
                "GET": (
                    "This server opens no server-initiated stream, so there is "
                    "nothing for a GET to subscribe to."
                ),
                "DELETE": (
                    "This server issues no Mcp-Session-Id, so there is no session "
                    "to delete."
                ),
            }.get(method, "Only POST is implemented on the MCP endpoint.")
            await self._refuse(send, 405, "method_not_allowed", reason, allow="POST")
            return

        # PROTOCOL-VERSION VALIDATION USED TO LIVE HERE AND HAS MOVED INTO
        # `server.py`, WHICH IS A BEHAVIOUR CHANGE AND IS THE POINT OF THE DUAL-ERA
        # WORK. Two reasons it could not stay:
        #
        # 1. **It could not see the body.** The modern revision carries the version
        #    in `params._meta["io.modelcontextprotocol/protocolVersion"]` as well
        #    as in the header, and requires the two to MATCH. A check that reads
        #    only the header cannot enforce a rule about two values.
        # 2. **It answered before authentication.** Every other pre-auth answer
        #    this transport gives is about the HTTP envelope; this one was about
        #    the MCP protocol, and an unauthenticated caller learned this server's
        #    supported revisions from it.
        #
        # What replaces it is a real `UnsupportedProtocolVersionError` (JSON-RPC
        # `-32022`), which `_status_for` maps to `400` — the status the revision
        # names for it. The refusal body changed shape deliberately: the old one
        # was this transport's own invention and a modern client could not
        # recognise it.

        # Lowercased like `Accept` is: RFC 9110 §8.3.1 makes a media type's type
        # and subtype case-insensitive, so `APPLICATION/JSON` is `application/json`
        # and a case-sensitive comparison refuses a conforming client with 415.
        # (Only the type/subtype is folded — parameter VALUES such as a boundary
        # are case-sensitive, and everything after the first `;` is discarded here
        # anyway.)
        content_type = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type != _JSON_CONTENT_TYPE:
            await self._refuse(
                send,
                415,
                "unsupported_media_type",
                f"The MCP endpoint takes {_JSON_CONTENT_TYPE}.",
            )
            return

        accept = headers.get("accept")
        if accept is not None and not _accepts_json(accept):
            await self._refuse(
                send,
                406,
                "not_acceptable",
                "This server answers application/json. It never returns an SSE "
                "stream, so a client that accepts only text/event-stream cannot be "
                "served.",
            )
            return

        body, too_large = await _read_body(receive, MAX_REQUEST_BYTES)
        if too_large:
            await self._refuse(
                send,
                413,
                "request_too_large",
                f"An MCP message may not exceed {MAX_REQUEST_BYTES} bytes.",
            )
            return

        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            # The parse error is not interpolated. Echoing a parser's message
            # echoes a fragment of the caller's body back into a log and a model's
            # context, and tells an attacker where their probe stopped parsing.
            await self._refuse(send, 400, "parse_error", "The body is not valid JSON.")
            return

        if isinstance(message, list):
            await self._refuse(
                send,
                400,
                "batching_not_supported",
                "JSON-RPC batching was removed in MCP revision 2025-06-18 and is "
                "not accepted. Send one message per request.",
            )
            return
        if not isinstance(message, dict):
            await self._refuse(
                send, 400, "invalid_request", "A JSON-RPC message must be an object."
            )
            return

        credential = _credential_from(headers)
        # The headers travel WITH the message, lowercased, because the modern
        # revision makes the server validate one against the other: *"Servers that
        # process the request body **MUST** reject requests where the values
        # specified in the headers do not match the corresponding values in the
        # request body."* A check split across two layers is a check that can be
        # satisfied by neither.
        header_map = headers.mapping()
        envelope = await self._server.handle(
            message, credential=credential, headers=header_map
        )

        if envelope is None:
            # A notification, from a caller who authenticated. The specification
            # says 202 with no body — NOT 200 with an empty object, which a client
            # would try to parse as a result. A notification whose CALLER did not
            # authenticate never reaches here: `handle` returns a refusal envelope
            # for it, and it is answered 401 with a challenge, because "no response
            # to a notification" is a JSON-RPC rule about results and not a licence
            # to serve an unauthenticated request.
            await _send(send, 202, b"", extra_headers=())
            return

        await _send(
            send,
            self._status_for(envelope, message, header_map),
            _encode(envelope),
            extra_headers=self._challenge_headers(envelope),
        )

    # -- response shaping -----------------------------------------------------

    def _entry_refusal(
        self, scope: Mapping[str, Any], headers: _Headers
    ) -> tuple[str, str] | None:
        """``(code, message)`` when this request must be refused, else ``None``.

        THREE INDEPENDENT GUARDS, EACH ASKING ITS OWN BINDING ATTRIBUTE. It was
        one ``if`` over one flag; ``deployment.py``'s module docstring records
        why that had to change before the first non-loopback binding shipped.
        The order is unchanged, and so is the behaviour of every binding that
        answers ``True`` to all three.
        """
        if self._loopback_only:
            client = scope.get("client")
            peer = client[0] if isinstance(client, (tuple, list)) and client else None
            if not is_loopback_host(peer):
                # The peer is NOT named in the message. An error body that echoes
                # the address it saw is a reflection primitive and tells a scanner
                # what the server believes about it; the operator gets the fact
                # from the status code and the log line.
                return (
                    "loopback_only",
                    "This MCP deployment binding serves loopback callers only, "
                    "and this request did not arrive from one. The check is made "
                    "against the connection's own peer address, never against a "
                    "header.",
                )
        if self._refuse_proxied:
            for name in PROXY_HEADERS:
                if headers.has(name):
                    return (
                        "proxied_request_refused",
                        "This request carries a proxy header, so the loopback "
                        "peer is a relay rather than the caller. The header's "
                        "value is not read and is not trusted; its presence alone "
                        "is the refusal.",
                    )
        if self._loopback_origin_only:
            origin = headers.get("origin")
            if origin is not None and not _origin_is_loopback(origin):
                return (
                    "cross_origin_refused",
                    "A browser origin outside loopback may not call this "
                    "endpoint. A page on any site can post to 127.0.0.1, so the "
                    "peer check alone is not a defence against DNS rebinding.",
                )
        return None

    def _status_for(
        self,
        envelope: Mapping[str, Any],
        message: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> int:
        """The HTTP status for a JSON-RPC envelope.

        Authorization outcomes get their HTTP status, because that is what an MCP
        client branches on: ``401`` starts an authorization flow, ``403`` does
        not. Every other JSON-RPC error stays ``200`` — the request was
        transported successfully and the *application* refused it, which is
        exactly the distinction JSON-RPC's error object exists to carry.

        TWO PROTOCOL-DEFINED CODES AND ONE ERA-DEPENDENT ONE, added with the
        dual-era work:

        * ``-32022`` (``UnsupportedProtocolVersionError``) and ``-32020``
          (``HeaderMismatch``) map to ``400`` **without consulting the era**,
          because the specification names ``400`` for each unconditionally.

          Which era can PRODUCE them is a separate question, and stating it
          loosely is easy: ``-32020`` is only ever raised on a modern request
          (``server.py`` runs the header rules in that branch alone), while
          ``-32022`` **can** reach a legacy client and should. A ``2025-06-18``
          client sends ``MCP-Protocol-Version: 2025-06-18``, which this server
          serves, and declares its negotiated revision in ``initialize``'s
          ``params``, which the version check never reads — so it never sees the
          error. A client speaking an *older* revision that sends, say,
          ``2024-11-05`` in the header does see it, and that is the correct
          outcome: it is the message naming the revisions that do exist.
        * ``-32601`` (``Method not found``) is ``404`` **for a modern request
          only**: *"If the server does not implement the requested RPC method, it
          **MUST** respond with ``404 Not Found`` and a JSON-RPC error with code
          ``-32601``."* That is a rule of the ``2026-07-28`` transport binding, and
          applying it to a legacy request would change a status this server has
          returned since it shipped, for a client whose own revision does not ask
          for it. The era is computed by ``server.protocol_era``, the same function
          the server dispatched on, so the two cannot disagree.
        """
        error = envelope.get("error")
        if not isinstance(error, Mapping):
            return 200
        code = error.get("code")
        if code == DEPLOYMENT_UNCONFIGURED:
            return 401
        if code == INSUFFICIENT_SCOPE:
            return 403
        if code in (UNSUPPORTED_PROTOCOL_VERSION, HEADER_MISMATCH):
            return 400
        if code == METHOD_NOT_FOUND:
            method = message.get("method")
            params = message.get("params") or {}
            if not isinstance(params, Mapping):
                params = {}
            if isinstance(method, str) and protocol_era(method, params, headers) == ERA_MODERN:
                return 404
        return 200

    def _challenge_headers(self, envelope: Mapping[str, Any]) -> Iterable[tuple[bytes, bytes]]:
        """``WWW-Authenticate``, but only if the binding actually has one.

        RFC 9728 says a protected resource answers an unauthenticated request with
        a challenge naming its ``resource_metadata``. A binding with no
        authorization server returns nothing here and **no header is sent** —
        emitting ``Bearer`` alone would tell a client to go and get a token from
        somewhere that does not exist, which is the rule the two shipped bindings
        still hold to.

        TWO STATUSES CARRY A CHALLENGE, NOT ONE, and the specification is explicit
        that they say different things:

        * ``401`` — no credential, or one that did not verify. The challenge comes
          from the refusal itself when it has one (``DeploymentRefused.challenge``,
          threaded through ``server.py`` into ``data.challenge``), because only the
          refusal knows whether to carry ``error="invalid_token"``: RFC 6750 §3
          says a request that presented nothing must NOT be answered with an error
          code. Falls back to the binding's generic challenge.
        * ``403`` — the token verified and does not carry the scope needed. The
          specification asks for ``error="insufficient_scope"`` plus ``scope=``
          naming **every** missing scope in one challenge, and ``_ScopeDenied``
          has already computed exactly that set. Read through ``getattr`` so a
          binding without ``scope_challenge`` simply emits no header.
        """
        error = envelope.get("error")
        if not isinstance(error, Mapping):
            return ()
        code = error.get("code")
        data = error.get("data")
        data = data if isinstance(data, Mapping) else {}

        if code == DEPLOYMENT_UNCONFIGURED:
            challenge = data.get("challenge")
            if not isinstance(challenge, Mapping):
                challenge = self._binding.challenge() or {}
        elif code == INSUFFICIENT_SCOPE:
            builder = getattr(self._binding, "scope_challenge", None)
            if builder is None:
                return ()
            missing = data.get("missingScopes")
            required = data.get("requiredScopes")
            wanted = missing if isinstance(missing, (list, tuple)) else None
            if not wanted:
                wanted = required if isinstance(required, (list, tuple)) else ()
            challenge = builder(tuple(wanted)) or {}
        else:
            return ()

        value = challenge.get("www_authenticate")
        if not isinstance(value, str) or not value.strip():
            return ()
        if "\r" in value or "\n" in value:  # pragma: no cover - defensive
            return ()
        return ((b"www-authenticate", value.encode("latin-1", "replace")),)

    async def _refuse(
        self,
        send,
        status: int,
        code: str,
        message: str,
        *,
        data: dict | None = None,
        allow: str | None = None,
    ) -> None:
        """A transport-level refusal, shaped as a JSON-RPC error envelope.

        ``id`` is ``null`` because the refusal happens before, or instead of,
        parsing one. The envelope shape is used even for pre-JSON refusals so an
        MCP client has one body shape to parse rather than two.
        """
        error: dict[str, Any] = {
            "code": TRANSPORT_REFUSED,
            "message": message,
            "data": {"code": code, **(data or {})},
        }
        extra: list[tuple[bytes, bytes]] = []
        if allow is not None:
            extra.append((b"allow", allow.encode("ascii")))
        await _send(
            send,
            status,
            _encode({"jsonrpc": "2.0", "id": None, "error": error}),
            extra_headers=extra,
        )


# --------------------------------------------------------------------------
# The mount decision
# --------------------------------------------------------------------------

def mcp_transport_or_none(
    app: Any,
    *,
    env: Mapping[str, str] | None = None,
    binding: DeploymentBinding | None = None,
) -> McpHttpTransport | None:
    """The transport to register a route for, or ``None`` — meaning REGISTER NOTHING.

    ``None`` is the default answer, because :func:`~.deployment.resolve_binding`
    fails closed to :class:`~.deployment.UnconfiguredDeployment` for unset, empty,
    unrecognised, reserved and misconfigured values alike, and that binding
    declares ``serves_transport = False``.

    The distinction this function exists to preserve: an unconfigured deployment
    must have **no route**, not a route that answers 403. A path that refuses is
    still a path that says "ISAAC speaks MCP, find the credential" — it is
    discoverable by a scanner, it appears in a route table, and it is one
    conditional away from being opened by somebody who reads the 403 as a bug.
    """
    resolved = binding if binding is not None else resolve_binding(env)
    if not getattr(resolved, "serves_transport", False):
        return None
    return McpHttpTransport(McpServer(app, binding=resolved), resolved)


# --------------------------------------------------------------------------
# ASGI plumbing
# --------------------------------------------------------------------------

class _Headers:
    """Case-insensitive read-only view over the raw ASGI header list."""

    __slots__ = ("_raw",)

    def __init__(self, raw: Iterable[tuple[bytes, bytes]]) -> None:
        self._raw = list(raw)

    def has(self, lowered_name: bytes) -> bool:
        return any(name.lower() == lowered_name for name, _ in self._raw)

    def get(self, lowered_name: str) -> str | None:
        wanted = lowered_name.encode("ascii")
        for name, value in self._raw:
            if name.lower() == wanted:
                return value.decode("latin-1")
        return None

    def mapping(self) -> dict[str, str]:
        """Every header, lowercased name to value, FIRST occurrence wins.

        First-wins rather than last-wins or comma-joined, so this agrees with
        :meth:`get` exactly — two readers of the same header list that disagree
        about a duplicate is how a header-versus-body check gets satisfied by a
        value the dispatcher never saw. RFC 9110 permits joining repeated fields
        into a list; none of the headers this server validates is a list header,
        so a duplicate is a malformed request rather than a value to assemble, and
        the first one is what the rest of this transport already acts on.
        """
        collected: dict[str, str] = {}
        for name, value in self._raw:
            key = name.lower().decode("latin-1")
            if key not in collected:
                collected[key] = value.decode("latin-1")
        return collected


def _accepts_json(accept: str) -> bool:
    """Whether an ``Accept`` header admits ``application/json``.

    Quality values are not parsed: ``q=0`` on a type this server must send is a
    request this server cannot satisfy anyway, and a partial parser that gets
    ``q`` wrong refuses correct clients. Presence of a compatible type is enough.
    """
    for part in accept.split(","):
        media = part.split(";", 1)[0].strip().lower()
        if media in ("*/*", "application/*", _JSON_CONTENT_TYPE):
            return True
    return False


def _credential_from(headers: _Headers) -> Credential | None:
    """The ``Authorization`` header as a :class:`~.deployment.Credential`.

    Parsed, never validated, and never logged. Handing it to the binding is the
    whole authorization seam: a binding that can verify a token verifies it here,
    and the loopback binding — which cannot — refuses rather than accepting.

    A malformed header still produces a credential (scheme ``""``), because
    "somebody sent authentication material" is the fact the binding needs;
    discarding it would silently downgrade the request to anonymous, which is the
    wrong direction.

    THE SCHEMELESS CASE IS SPLIT OUT, AND THE CODE USED TO CONTRADICT THE
    PARAGRAPH ABOVE IT. ``str.partition(" ")`` returns ``(whole, "", "")`` when
    there is no delimiter, so a header carrying a BARE token — ``Authorization:
    eyJhbGciOi…`` , a raw JWT or an opaque secret with no ``Bearer`` in front of it,
    which is a shape real clients send — put the ENTIRE CREDENTIAL into ``scheme``
    and left ``token`` empty. That is the exact opposite of the sentence three lines
    up, and it mattered because ``scheme`` is the one member the refusal path is
    allowed to report: ``LocalLoopbackBinding.authenticate`` puts it in the ``data``
    of a ``credential_not_verifiable`` refusal, so the whole bare token came back to
    the caller in the body of the ``401``. Measured before this fix: a 48-character
    stand-in JWT appeared verbatim in the response.

    A value with no delimiter has NO scheme, so it is reported as none and the
    whole value is carried as the token — where it is opaque, never echoed, and
    handed only to a binding. ``deployment._reportable_scheme`` independently
    refuses to publish anything that is not a syntactic ``auth-scheme``, so this and
    that are two conditions and not one written twice: this one gets the PARSE
    right, that one bounds what may be PUBLISHED however the parse turns out.
    """
    raw = headers.get("authorization")
    if raw is None or not raw.strip():
        return None
    raw = raw.strip()
    scheme, delimiter, token = raw.partition(" ")
    if not delimiter:
        return Credential(scheme="", token=raw)
    return Credential(scheme=scheme.strip(), token=token.strip())


def _query_token_parameter(scope: Mapping[str, Any]) -> str | None:
    """The name of a credential-bearing query parameter, or ``None``.

    **Only NAMES are examined.** The value is never sliced out, never decoded and
    never returned, so this check cannot itself become the thing that puts a token
    in a log line — which would be a comic way to fail at enforcing *"Access
    tokens MUST NOT be included in the URI query string"*.

    Parsed by hand rather than with ``parse_qsl`` for the same reason:
    ``parse_qsl`` materialises every value, and there is no need for any of them
    to exist as a Python object at all. The returned name is one of
    :data:`QUERY_TOKEN_PARAMETERS` — a constant of this module, never
    caller-controlled text — so it is safe to put in the refusal body.
    """
    raw = scope.get("query_string") or b""
    if not raw:
        return None
    if isinstance(raw, str):  # pragma: no cover - ASGI gives bytes
        raw = raw.encode("latin-1", "replace")
    for pair in raw.split(b"&"):
        if not pair:
            continue
        name_bytes = pair.split(b"=", 1)[0]
        try:
            name = unquote_plus(name_bytes.decode("ascii")).strip().lower()
        except (UnicodeDecodeError, ValueError):  # pragma: no cover - defensive
            continue
        if name in QUERY_TOKEN_PARAMETERS:
            return name
    return None


def metadata_routes_or_none(
    *,
    env: Mapping[str, str] | None = None,
    binding: DeploymentBinding | None = None,
    base: str = "",
) -> tuple[tuple[str, Any], ...]:
    """``((path, asgi_app), …)`` for the binding's discovery documents, or ``()``.

    ``()`` IS THE DEFAULT AND IS WHAT EVERY SHIPPED DEPLOYMENT GETS. The two
    bindings that exist without an OAuth configuration expose no
    ``protected_resource_metadata`` attribute at all, so this returns nothing and
    ``app.py`` registers no route — matching the MCP endpoint's own rule that an
    unconfigured deployment has an *absent* path rather than one that refuses.
    Publishing an RFC 9728 document naming an authorization server that does not
    exist would be worse than publishing none.

    Read through ``getattr`` rather than ``isinstance`` for the reason
    ``deployment.DeploymentBinding`` is not ``runtime_checkable``: a structural
    check is the one somebody reaches for and the one that must not be trusted.
    """
    resolved = binding if binding is not None else resolve_binding(env)
    document = getattr(resolved, "protected_resource_metadata", None)
    paths = getattr(resolved, "metadata_paths", None)
    if document is None or paths is None:
        return ()
    from .oauth import ProtectedResourceMetadataApp

    app = ProtectedResourceMetadataApp(document())
    return tuple((path, app) for path in paths(base))


async def _read_body(receive: Callable[[], Awaitable[Mapping[str, Any]]], cap: int):
    """``(body, too_large)``. Stops reading at ``cap`` rather than buffering on."""
    chunks: list[bytes] = []
    total = 0
    while True:
        event = await receive()
        if event.get("type") == "http.disconnect":
            return b"", False
        chunks.append(event.get("body") or b"")
        total += len(chunks[-1])
        if total > cap:
            return b"", True
        if not event.get("more_body"):
            return b"".join(chunks), False


def _encode(payload: Mapping[str, Any]) -> bytes:
    """Canonical JSON bytes: sorted keys, no padding — the same shape ``server.py``
    uses for tool content, so a response is byte-stable across runs."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


async def _send(
    send, status: int, body: bytes, *, extra_headers: Iterable[tuple[bytes, bytes]]
) -> None:
    headers: list[tuple[bytes, bytes]] = [
        (b"content-length", str(len(body)).encode("ascii")),
        # Told not to cache, and told not to guess the type. An MCP response can
        # carry record content; a shared cache holding it is a data-governance
        # problem this endpoint should not create.
        (b"cache-control", b"no-store"),
        (b"x-content-type-options", b"nosniff"),
    ]
    if body:
        headers.insert(0, (b"content-type", b"application/json; charset=utf-8"))
    headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
