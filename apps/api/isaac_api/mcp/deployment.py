"""The authenticated-deployment boundary: who is calling, and may they call at all.

WHAT IS ACTUALLY UNDECIDED, STATED BEFORE ANYTHING ELSE
=======================================================
Two infrastructure decisions gate a real connection, and both were **DEFERRED on
2026-08-12** (``docs/mcp-capability-audit.md`` §6):

* **D1** — may the MCP path be reachable from a scientist's own machine over the
  public internet at all? A Claude client connects *from the client side*; an
  endpoint reachable only inside SLAC's network cannot be added as a connector.
* **D2** — what authenticates that caller, given ISAAC sits behind an Authentik
  forward-auth edge that a Claude client cannot interactively traverse?

Neither is application work and neither is guessed here. This module's DEFAULT is
therefore a binding that serves nothing and says why.

WHAT A STANDARDS-COMPLIANT ANSWER TO D2 LOOKS LIKE
==================================================
Verified against the MCP authorization specification (revision ``2025-06-18``,
the revision this package's protocol surface targets):

* MCP authorization lives at the **transport** layer, not in the JSON-RPC body.
  A bearer token travels in ``Authorization``, never in a query string, and never
  as a tool argument.
* The server is an **OAuth 2.1 protected resource**. It MUST implement **RFC 9728
  Protected Resource Metadata**: an unauthenticated request is answered ``401``
  with a ``WWW-Authenticate`` header carrying ``resource_metadata=<url>``, and
  that document's ``authorization_servers`` names where a client gets a token.
  The June 2025 revision removed the older fallback-endpoint mechanism, so PRM is
  mandatory rather than one of two options.
* The client names this server as the target resource (**RFC 8707** resource
  indicators) and validates the issuer (**RFC 9207**), which is what stops a
  malicious server harvesting a token minted for somebody else.
* Claude Code and Claude.ai custom connectors additionally accept **fixed header
  auth** — a static pre-issued bearer — for services that do not run an
  authorization server. That is the pragmatic alternative, not the standard one.

Both shapes fit :class:`DeploymentBinding` without redesign, and that is the
point of the seam: an OAuth binding validates a token and maps its ``scope``
claim onto :class:`~.policy.Scope` members; an edge-issued-bearer binding
validates a token the edge minted and maps a fixed grant. Both produce a
:class:`Principal`. Neither exists here.

**No binding is implemented that would weaken Authentik, and none invents a
shared secret.** The two candidate names are recorded in
:data:`RESERVED_BINDING_NAMES` and are deliberately NOT registered, so selecting
one today resolves to :class:`UnconfiguredDeployment` — a reserved name is a
placeholder for a decision, and a placeholder that served traffic would be the
decision.

FAIL-CLOSED, IN ALL FOUR DIRECTIONS
===================================
Unset, empty, unrecognised, and *misconfigured* all resolve to
:class:`UnconfiguredDeployment`. The fourth is the one that is easy to miss: a
recognised binding name whose scope list contains a string that is not a
:class:`~.policy.Scope` does not fall back to "grant what we understood" — it
falls back to granting nothing, because ``isaac:submit`` in a scope list must not
quietly become a working read-only server that somebody then trusts.

THE BINDING ALSO DECIDES WHETHER A TRANSPORT EXISTS AT ALL
==========================================================
Since the Streamable HTTP transport landed (``transport.py``) a binding answers
two further questions, and both are **declared by the binding rather than
inferred from its class**, because an ``isinstance`` check is what silently
admits the next binding somebody adds:

* :attr:`serves_transport` — may a route be mounted for this binding? The
  application reads this at construction and, when it is false, **registers no
  route at all**. Not a route that refuses: an absent route. A 403 from a mounted
  path still advertises that ISAAC speaks MCP and still invites somebody to go
  looking for the credential that would open it.
* :attr:`requires_loopback_peer` — must the request's own socket peer be a
  loopback address? True for :data:`LOCAL_LOOPBACK`, which is the whole content
  of the name.

Both are read through ``getattr`` with the **safe** value as the default
(``False`` and ``True`` respectively), so a binding that forgets to declare them
serves nothing and, if it somehow serves, serves only itself.

THE ONE FLAG THAT CONTROLLED THREE GUARDS IS NOW THREE FLAGS
============================================================
This section used to warn that ``requires_loopback_peer`` gated **three**
distinct refusals in ``transport.py`` — the socket-peer check it is named for,
the proxy-header refusal, and the cross-origin/DNS-rebinding refusal — and that
the author of the first internet-adjacent binding would set it ``False`` for the
first reason and silently lose the other two. **That is exactly what would have
happened**: ``oauth.py`` is that binding, and it needs a non-loopback peer.

So the flag was split, and the warning is recorded here as history rather than
deleted, because the shape of the mistake is the useful part. Three independent
attributes now exist — :attr:`DeploymentBinding.requires_loopback_peer`,
:attr:`~DeploymentBinding.refuses_proxy_headers`,
:attr:`~DeploymentBinding.requires_loopback_origin` — each read through
``getattr`` with the **safe** value (``True``) as its default, so a binding that
declares none of them gets every defence. Both shipped bindings are unchanged in
behaviour: :class:`LocalLoopbackDeployment` declares all three ``True``, which is
what the single flag already gave it, and :class:`UnconfiguredDeployment` serves
nothing at all.

The rule the old note was reaching for still stands, and is now enforceable:
**a new binding answers all three questions explicitly.** ``oauth.py``'s class
docstring gives its own reason for each, which is what "explicit" has to mean if
it is to be worth anything.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from ..config import base_path
from .policy import Scope, parse_scope

__all__ = [
    "Credential",
    "DeploymentBinding",
    "DeploymentRefused",
    "LOCAL_LOOPBACK",
    "OAUTH_RESOURCE_SERVER",
    "LocalLoopbackDeployment",
    "Principal",
    "RESERVED_BINDING_NAMES",
    "UNCONFIGURED",
    "UnconfiguredDeployment",
    "resolve_binding",
]

#: Selects the binding. Unset/empty/unrecognised/misconfigured -> unconfigured.
DEPLOYMENT_ENV = "ISAAC_MCP_DEPLOYMENT"
#: Comma-separated scope strings for the local-loopback binding. Unset -> read only.
LOCAL_SCOPES_ENV = "ISAAC_MCP_LOCAL_SCOPES"
#: Optional worked-example session the local-loopback binding is pinned to.
LOCAL_SESSION_ENV = "ISAAC_MCP_LOCAL_TUTORIAL_SESSION"

#: The default, and the honest one.
UNCONFIGURED = "unconfigured"

#: In-process development and automated tests, and — since ``transport.py`` — a
#: Streamable HTTP endpoint that accepts **loopback peers only**.
#:
#: The older comment here said "there is no network transport in this package at
#: all … so this binding cannot be reached from off the machine no matter how the
#: variable is set". That was true and is now false, and it is corrected rather
#: than deleted because the guarantee it stated still has to hold — it is simply
#: held by a different mechanism. The mechanism is now
#: :attr:`LocalLoopbackDeployment.requires_loopback_peer`, enforced per request
#: against the socket peer address in ``transport.py``, and pinned by
#: ``test_mcp_transport.py``.
LOCAL_LOOPBACK = "local-loopback"

#: The OAuth 2.1 protected-resource binding, implemented in ``oauth.py``.
#:
#: **Naming it here is not turning it on.** Selecting it still resolves to
#: :class:`UnconfiguredDeployment` unless a complete, valid configuration is
#: present — an issuer, a canonical resource URI, a verification key set — and
#: none of those exists in any shipped deployment or anywhere in this repository.
#: The constant lives in this module rather than in ``oauth.py`` so that
#: :func:`resolve_binding` can branch on it without importing OAuth code on the
#: default path.
OAUTH_RESOURCE_SERVER = "oauth-resource-server"

#: Names held for an answer D2 could take. NOT REGISTERED: selecting one resolves
#: to :class:`UnconfiguredDeployment`, which is the correct answer while the
#: decision is outstanding.
#:
#: **``oauth-resource-server`` WAS IN THIS TABLE AND HAS MOVED.** It is now an
#: implemented binding (``oauth.py``) and is registered by :func:`resolve_binding`.
#: Read that as the narrow claim it is: the APPLICATION half exists, is disabled
#: by default, and still resolves to :class:`UnconfiguredDeployment` unless an
#: operator supplies a complete configuration. **D1 and D2 remain DEFERRED and
#: this did not answer them** — an issuer, a registered client, a reachable host
#: and a routing decision are all external and none of them exists. What changed
#: is that they are now answerable against reviewable code instead of a plan.
#: ``test_mcp_oauth_binding.py`` pins that the name appears in exactly one of the
#: two tables, so it can never read as both reserved and served.
RESERVED_BINDING_NAMES: Mapping[str, str] = {
    "edge-issued-bearer": (
        "The Authentik edge is configured to accept a pre-issued static bearer on "
        "the MCP path specifically. Blocked on D2, and on the edge configuration "
        "itself, which is not application work."
    ),
}


#: A syntactic ``auth-scheme`` and nothing else: RFC 9110 defines it as a ``token``,
#: and every scheme anyone actually sends (``Bearer``, ``Basic``, ``Negotiate``,
#: ``DPoP``) is a short alphabetic word. The 32-character bound is far above every
#: registered scheme and far below any credential worth exfiltrating.
_AUTH_SCHEME = re.compile(r"\A[A-Za-z][A-Za-z0-9+.\-]{0,31}\Z")


def _reportable_scheme(scheme: str) -> str:
    """The scheme, but only if it IS one. Anything else reports as ``""``.

    THE SECOND OF TWO INDEPENDENT CONDITIONS, and it exists because the first one
    was not enough on its own. ``transport._credential_from`` now parses a
    delimiter-less ``Authorization`` header as a bare TOKEN with no scheme, which
    closes the shape that was measured leaking. This bounds what may be PUBLISHED
    whatever the parse produces — a header like ``<very-long-secret> trailing``
    does have a delimiter, and would otherwise put the secret in ``scheme`` by a
    different route.

    Written as an allowlist rather than as a length cap, deliberately: a cap alone
    would still publish the first 32 characters of a secret, which is not a
    redaction. A value that is not a scheme is not truncated to look like one; it
    is replaced, so a reader cannot mistake a fragment for the real header.
    """
    return scheme if _AUTH_SCHEME.match(scheme or "") else ""


@dataclass(frozen=True)
class Credential:
    """Transport-level authentication material, as a binding would receive it.

    Deliberately opaque and deliberately never logged.

    ~~"the refusal bodies in this module name the *scheme* at most, never the
    token"~~ — **THIS WAS FALSE WHEN IT WAS WRITTEN, and it is struck rather than
    reworded because it read as a guarantee about a credential.** It described
    intent accurately and behaviour inaccurately, and the gap was entirely in a
    parse two modules away: ``transport._credential_from`` split on the first
    space, so an ``Authorization`` header carrying a BARE token — no ``Bearer``, no
    space, which is a shape real clients send — assigned the whole credential to
    ``scheme``. :meth:`LocalLoopbackBinding.authenticate` then reported that
    "scheme" in the ``data`` of its ``credential_not_verifiable`` refusal, so the
    token came back to the caller **in full, in the body of the 401**. Measured: a
    48-character stand-in JWT appeared verbatim in the response text.

    ``test_mcp_transport.py``'s credential test could not see it — it sends
    ``"Bearer s3cret-value"``, the well-formed shape, and asserts the token is not
    echoed. That assertion was true of the shape it tested and of no other.

    **The claim now holds, and is enforced at two independent points rather than
    asserted**: the parse assigns no scheme when there is no delimiter, and
    :func:`_reportable_scheme` refuses to publish anything that is not a syntactic
    ``auth-scheme`` however the parse turned out. The token member is still never
    logged and never echoed by anything in this package.
    """

    scheme: str
    token: str


@dataclass(frozen=True)
class Principal:
    """Who the server decided the caller is, and what it decided they may do.

    Constructed only by a binding, from transport-level evidence. **Nothing a
    client sends in a JSON-RPC message can produce or amend one** — that is the
    whole content of "server-side authorization is authoritative", and
    ``test_mcp_boundaries.py`` pins it by sending a ``scopes`` field in
    ``tools/call`` params and asserting it changes nothing.
    """

    subject: str
    binding: str
    scopes: frozenset[Scope]
    #: The worked-example session this connection is confined to, or ``None`` for
    #: the ordinary workspace. It comes from the BINDING, never from a tool
    #: argument, so a tool cannot move itself between scopes.
    tutorial_session_id: str | None = None

    def permits(self, scope: Scope) -> bool:
        return scope in self.scopes

    def missing(self, required: frozenset[Scope]) -> frozenset[Scope]:
        """The required scopes this principal was NOT granted.

        Set difference rather than a loop with an early ``return True``, because
        the refusal must be able to name *every* scope that was missing. A caller
        told only the first one re-requests a grant that is still insufficient.
        """
        return frozenset(required) - self.scopes

    def permits_all(self, required: frozenset[Scope]) -> bool:
        """Whether every scope in ``required`` was granted.

        ``all`` over the set, NOT ``required & self.scopes`` — an intersection is
        non-empty as soon as *one* scope matches, which is exactly how a tool
        costing two scopes would become reachable by a caller holding one.
        """
        return not self.missing(required)


class DeploymentRefused(Exception):
    """The deployment boundary refused. Carries a machine-readable reason.

    ``data`` is safe to serialise to a caller: it names decisions, owners and
    documents, and never a credential, host, path or environment value that could
    be a secret.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        data: dict | None = None,
        challenge: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = dict(data or {})
        #: The challenge THIS refusal should carry, when it differs from the
        #: binding's generic one. ``None`` — the default, and what every existing
        #: construction passes — means ``server.py`` falls back to
        #: :meth:`DeploymentBinding.challenge`, so neither shipped binding changes
        #: in any respect.
        #:
        #: It exists because RFC 6750 §3 distinguishes two cases a single generic
        #: challenge cannot. A request that carried NO credential must not be
        #: answered ``error="invalid_token"`` — that is the normal first step of
        #: an authorization flow, not a failure, and reporting an error for it
        #: sends conforming clients down an error path. An expired or forged one
        #: must be.
        self.challenge = dict(challenge) if challenge is not None else None


class DeploymentBinding(Protocol):
    """How a deployment turns transport-level evidence into a :class:`Principal`.

    Deliberately NOT ``runtime_checkable``: a structural ``isinstance`` would
    report any object carrying a ``name`` and two methods as a valid binding,
    which is precisely the check somebody would reach for and precisely the one
    that must not be trusted. Bindings are constructed by
    :func:`resolve_binding`, and that function is the whole registry.
    """

    name: str
    #: May the application mount an HTTP transport for this binding? See the
    #: module docstring: false means NO ROUTE IS REGISTERED, not a route that
    #: refuses.
    serves_transport: bool
    #: Must the request's own socket peer be a loopback address? Read with a
    #: default of ``True`` wherever it is consulted, so forgetting it narrows
    #: rather than widens.
    #:
    #: ~~"**It also gates two guards the name does not mention**"~~ — **NO LONGER
    #: TRUE, and struck rather than deleted because the warning it carried is why
    #: the split happened.** It gated the proxy-header refusal and the
    #: cross-origin/DNS-rebinding refusal too, and the module docstring predicted
    #: that the author of an internet-adjacent binding would set this ``False``
    #: and silently switch both off. Rather than let the first such binding
    #: (``oauth.py``) do exactly that, the flag is now three flags. This one means
    #: what its name says and nothing more.
    requires_loopback_peer: bool
    #: Must a request carrying any of :data:`~.transport.PROXY_HEADERS` be
    #: refused? Read with a default of ``True``, so a binding that does not
    #: declare it narrows rather than widens. Refusing is right for a local
    #: server (a loopback peer behind a proxy says nothing about the originator)
    #: and wrong for a binding that is *meant* to be reached through an edge —
    #: which is why it is now a separate answer rather than a side effect.
    #:
    #: Setting it ``False`` does not start TRUSTING a forwarded header. No code
    #: in this package reads one's value, and none may: ``CLAUDE.md`` records
    #: that the Service is a plain ClusterIP with no NetworkPolicy, so any
    #: in-cluster caller can forge one.
    refuses_proxy_headers: bool
    #: Must an ``Origin`` header, when present, name a loopback host? The
    #: DNS-rebinding defence the specification requires **of a local server**.
    #: Default ``True``. A token-authenticated remote binding answers ``False``,
    #: because a page on another origin cannot obtain a bearer the issuer signed
    #: and the browser will not attach one for it.
    requires_loopback_origin: bool

    def authenticate(self, credential: Credential | None) -> Principal:
        """The caller's principal, or raise :class:`DeploymentRefused`."""

    def challenge(self) -> dict:
        """What a standards-compliant ``401`` would carry for this binding.

        Returned in the refusal payload rather than as an HTTP header, because
        this package ships no HTTP transport. It is the shape a hosted binding
        would emit — ``WWW-Authenticate`` with an RFC 9728 ``resource_metadata``
        pointer — recorded so the eventual transport has something to implement
        rather than something to invent.
        """


@dataclass(frozen=True)
class UnconfiguredDeployment:
    """The default. Serves nothing, and says exactly what is missing.

    It is not "disabled" and does not present itself as a switch somebody can
    flip: there is no configuration of this object that authenticates anybody.
    Turning the server on means implementing a binding for whichever answer D1
    and D2 receive.
    """

    name: str = UNCONFIGURED
    #: The value that was selected, when one was, so an operator can see their
    #: typo. ``None`` when the variable was unset. A reserved name is echoed
    #: because it is a documented constant, never a secret.
    supplied: str | None = None
    #: Why this binding was chosen over a working one.
    reason: str = "unset"
    #: **The default deployment mounts nothing.** There is no configuration of
    #: this object that flips it: the field is not read from the environment and
    #: the class is frozen. Turning the transport on means resolving to a
    #: different binding, which means implementing one for whichever answer D1
    #: and D2 receive.
    serves_transport: bool = False
    #: Vacuous while :attr:`serves_transport` is false, and set to the safe value
    #: anyway so that a future edit which mounts this binding by mistake still
    #: refuses every non-loopback peer.
    requires_loopback_peer: bool = True
    #: Same reasoning, for the two guards that used to ride on the flag above.
    refuses_proxy_headers: bool = True
    requires_loopback_origin: bool = True

    def authenticate(self, credential: Credential | None) -> Principal:
        raise DeploymentRefused(
            "deployment_unconfigured",
            "This ISAAC deployment has no configured MCP deployment binding, so no "
            "caller can be authenticated and no tool can be called. This is not a "
            "fault: reachability (D1) and the authentication model (D2) are "
            "outstanding infrastructure decisions, deferred 2026-08-12.",
            data=self.detail(),
        )

    def detail(self) -> dict:
        return {
            "binding": self.name,
            "reason": self.reason,
            "selected_by": DEPLOYMENT_ENV,
            "supplied_value": self.supplied,
            "outstanding_decisions": [
                {
                    "id": "D1",
                    "question": (
                        "May the MCP path be reachable from a scientist's own "
                        "machine over the public internet?"
                    ),
                    "owner": "Dean / SLAC infrastructure",
                    "status": "DEFERRED 2026-08-12",
                },
                {
                    "id": "D2",
                    "question": (
                        # CORRECTED 2026-08-29. This read "an ISAAC-hosted OAuth "
                        # 2.1 authorization server", which was never what the
                        # option meant and is now contradicted by working code:
                        # `oauth.py` makes ISAAC an OAuth 2.1 RESOURCE server. It
                        # issues no token, registers no client and hosts no
                        # authorization server — it validates tokens an EXTERNAL
                        # issuer minted, and naming that issuer is the decision.
                        "What authenticates that caller — an OAuth 2.1 access "
                        "token from an institutional authorization server, which "
                        "ISAAC validates as a protected resource and advertises "
                        "via RFC 9728, or a pre-issued bearer the Authentik edge "
                        "accepts on the MCP path?"
                    ),
                    "owner": "Dean / SLAC infrastructure",
                    "status": "DEFERRED 2026-08-12",
                },
            ],
            "reserved_binding_names": dict(RESERVED_BINDING_NAMES),
            "reference": "docs/mcp-capability-audit.md §3, §6",
        }

    def challenge(self) -> dict:
        return {
            "scheme": "Bearer",
            "www_authenticate": None,
            "resource_metadata": None,
            "note": (
                "An RFC 9728 protected-resource-metadata document would be served "
                "here once D2 is answered. None is published, and none is "
                "fabricated: a challenge pointing at an authorization server that "
                "does not exist would be worse than no challenge."
            ),
        }


@dataclass(frozen=True)
class LocalLoopbackDeployment:
    """Local development and automated tests. Authenticates nobody, serves loopback.

    **This docstring used to say the guarantee was structural — "this package
    registers no HTTP route and opens no socket".** That stopped being true when
    ``transport.py`` landed, and the honest replacement is not a weaker promise
    but a differently-located one:

    * the route exists **only** when this binding is the resolved one, because
      :attr:`serves_transport` is what the application consults, and the default
      binding sets it ``False``;
    * every request is refused unless its **socket peer** is a loopback address
      (:attr:`requires_loopback_peer`), checked against ``scope["client"]`` and
      never against a forwarded header, which any caller can write;
    * a request carrying a proxy header at all is refused, because the peer being
      loopback then says nothing about who originated the request.

    The residual limit, stated rather than glossed: this refuses non-loopback
    *peers*. It cannot stop a reverse proxy running on the same host from
    relaying a remote caller whose forwarded headers it strips. Loopback binding
    of the listening socket is the operator's half of that (``--host 127.0.0.1``),
    and it is documented in ``docs/mcp-local-transport.md`` as the operator's
    half — an application cannot enforce what address a process it does not own
    chose to bind.

    It **refuses a credential** rather than accepting one. Accepting a token it
    cannot validate would let somebody point a real client at it and believe an
    authentication happened.

    Its default grant is :attr:`~.policy.Scope.READ` alone. The write scope is
    reachable only by naming it explicitly in :data:`LOCAL_SCOPES_ENV`.
    """

    scopes: frozenset[Scope] = field(default_factory=lambda: frozenset({Scope.READ}))
    tutorial_session_id: str | None = None
    name: str = LOCAL_LOOPBACK
    #: The one binding in this build that serves a transport.
    serves_transport: bool = True
    #: The name is the contract, and this is where the name is kept.
    requires_loopback_peer: bool = True
    #: Both were previously implied by the flag above and are now declared. A
    #: loopback peer that arrived through a relay is not the caller, and a page
    #: on any origin can post to ``127.0.0.1``; a local server needs both.
    refuses_proxy_headers: bool = True
    requires_loopback_origin: bool = True

    def authenticate(self, credential: Credential | None) -> Principal:
        if credential is not None:
            raise DeploymentRefused(
                "credential_not_verifiable",
                "The local-loopback binding cannot verify a credential and will not "
                "accept one. It exists for in-process development and tests, where "
                "there is no transport to carry a credential in the first place.",
                data={
                    "binding": self.name,
                    # NEVER `credential.scheme` raw — see `_reportable_scheme`.
                    "scheme": _reportable_scheme(credential.scheme),
                },
            )
        return Principal(
            subject="local-loopback-development",
            binding=self.name,
            scopes=frozenset(self.scopes),
            tutorial_session_id=self.tutorial_session_id,
        )

    def challenge(self) -> dict:
        return {
            "scheme": None,
            "www_authenticate": None,
            "resource_metadata": None,
            "note": "No credential is accepted or expected on the loopback binding.",
        }


def _parse_scopes(raw: str | None) -> frozenset[Scope] | str:
    """The scope set for a configured scope string, or an error reason.

    An unrecognised token is an error rather than a token that is dropped. A
    dropped token yields a server that runs with fewer permissions than the
    operator wrote down, which reads as working and is the shape in which a
    "grant" nobody reviewed goes unnoticed in the other direction later.
    """
    if raw is None or not raw.strip():
        return frozenset({Scope.READ})
    granted: set[Scope] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        scope = parse_scope(token)
        if scope is None:
            return (
                f"the scope {token!r} is not a scope this server can express; the "
                f"only scopes are {sorted(s.value for s in Scope)}"
            )
        granted.add(scope)
    if not granted:
        return frozenset({Scope.READ})
    return frozenset(granted)


def resolve_binding(env: Mapping[str, str] | None = None) -> DeploymentBinding:
    """The binding this process is configured for. Never raises; fails closed.

    Every failure mode — unset, empty, unrecognised, reserved-but-unimplemented,
    and misconfigured — produces an :class:`UnconfiguredDeployment` carrying the
    reason, so a caller gets one refusal shape and an operator gets a specific
    explanation.
    """
    environ = os.environ if env is None else env
    raw = (environ.get(DEPLOYMENT_ENV) or "").strip()

    if not raw:
        return UnconfiguredDeployment(supplied=None, reason="unset")
    if raw in RESERVED_BINDING_NAMES:
        return UnconfiguredDeployment(
            supplied=raw,
            reason="reserved_pending_decision",
        )
    if raw == OAUTH_RESOURCE_SERVER:
        # Imported here rather than at module scope, and the reason is the same
        # one `app.py` gives for importing this package lazily: `oauth.py`
        # imports `..identity`, which imports Starlette, and this module is
        # otherwise reachable from a context that has neither. It also keeps the
        # default path — the only one any shipped deployment takes — from
        # executing a line of OAuth code.
        from .oauth import resolve_oauth_binding

        resolved = resolve_oauth_binding(environ, base_path())
        if isinstance(resolved, str):
            # A configuration this build will not serve fails closed to the same
            # binding as a typo, carrying the specific reason. `app.py`
            # additionally refuses to BOOT on it, so this branch is what a
            # direct `resolve_binding` call sees rather than what an operator
            # experiences.
            return UnconfiguredDeployment(supplied=raw, reason=resolved)
        return resolved
    if raw != LOCAL_LOOPBACK:
        return UnconfiguredDeployment(supplied=raw, reason="unrecognised")

    scopes = _parse_scopes(environ.get(LOCAL_SCOPES_ENV))
    if isinstance(scopes, str):
        return UnconfiguredDeployment(supplied=raw, reason=f"misconfigured: {scopes}")
    session = (environ.get(LOCAL_SESSION_ENV) or "").strip() or None
    return LocalLoopbackDeployment(scopes=scopes, tutorial_session_id=session)
