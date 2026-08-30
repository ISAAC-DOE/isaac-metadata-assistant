"""The ``oauth-resource-server`` binding: ISAAC as an OAuth 2.1 protected resource.

WHAT THIS IS, AND WHAT IT IS NOT
================================
This registers the name ``deployment.py`` has been holding open. It is a
**complete, standards-conformant resource server** — RFC 9728 protected-resource
metadata, RFC 8707 audience binding, RFC 6750 challenges, RFC 9068-shaped JWT
access tokens — and it is **disabled by default and reachable in no shipped
deployment**. Nothing here creates an account, a credential, an endpoint, a
billing arrangement or an outbound connection, and nothing here may.

**D1 and D2 are still deferred and this does not answer them.** It makes them
*answerable*: the application half now exists and can be reviewed, so what
remains is exactly the external configuration
``docs/mcp-oauth-operator-requirements-2026-08-27.md`` enumerates — an issuer, a
registered client, a reachable host, a routing decision. All of those are Dean's,
and none of them is written down anywhere in this repository as a value.

DISABLED BY DEFAULT IS CONFORMANT, NOT A COMPROMISE
===================================================
The specification's own words: *"Authorization is **OPTIONAL** for MCP
implementations."* A server that ships this code and never selects the binding is
not a half-finished authorization story — it is an MCP implementation that has
not opted in. What would be non-conformant is a *selected* binding that
authorized anybody, and that is the state
:func:`validate_oauth_selection_or_raise` refuses to boot into.

THE DEFAULT IS UNCHANGED, AND THAT IS THE FIRST PROPERTY TO CHECK
================================================================
With ``ISAAC_MCP_DEPLOYMENT`` unset, ``resolve_binding`` never reaches this
module, ``mcp_transport_or_none`` returns ``None``, **no route of any kind is
registered — neither the MCP endpoint nor the metadata document** — and
``app.py`` does not even import the package. Selecting
``oauth-resource-server`` without a complete configuration does not open
anything either: it fails closed to ``UnconfiguredDeployment``, and
:func:`validate_oauth_selection_or_raise` additionally makes the container
refuse to boot, so a half-configured deployment is loud rather than quiet.

VERIFIED AGAINST THE LIVE SPECIFICATION (fetched 2026-08-29, revision
``2026-07-28``)
====================================================================
The requirements this module implements, each traceable:

* *"MCP servers **MUST** implement OAuth 2.0 Protected Resource Metadata
  (RFC 9728)"* and *"The Protected Resource Metadata document returned by the MCP
  server **MUST** include the ``authorization_servers`` field containing at least
  one authorization server."* → :func:`protected_resource_metadata`, and a
  configuration with no authorization server does not resolve.
* *"MCP servers **MUST** validate that access tokens were issued specifically for
  them as the intended audience"* / *"**MUST** reject tokens that do not include
  them in the audience claim"* → the unconditional ``aud`` check in
  ``jwt.verify_access_token``, compared by exact string equality.
* *"Access tokens **MUST NOT** be included in the URI query string"* →
  ``transport.py`` refuses such a request outright rather than ignoring the
  parameter. Ignoring it would be conformant and useless: the token is already in
  a proxy log by then, and a client that sent it must be told to stop.
* *"Invalid or expired tokens **MUST** receive a HTTP 401 response"*, and the
  status table 401 / 403 / 400 → :func:`bearer_challenge`,
  :func:`insufficient_scope_challenge`, and the transport's status mapping.
* *"MCP servers **MUST** only accept tokens that are valid for use with their own
  resources."* and — the no-passthrough rule, quoted in full because it is the one
  most often violated by accident — *"**MCP servers MUST NOT accept or transit any
  other tokens.**"* Reinforced by the security-considerations page: *"The MCP
  server **MUST NOT** pass through the token it received from the MCP client."*
  Held structurally rather than by discipline: the token never leaves
  :meth:`OAuthResourceServerDeployment.authenticate`. :class:`~.jwt.VerifiedToken`
  has no field for it, :class:`~.deployment.Principal` has no field for it, and
  ``client.py`` — the only thing in this package that makes a request — builds
  its headers from the principal, never from a credential. There is nowhere for a
  passed-through token to be *stored*, so there is nothing to forward.
* *"MCP servers **SHOULD** include a ``scope`` parameter in the
  ``WWW-Authenticate`` header"* and *"servers **SHOULD** include all scopes
  required for the current operation in a single challenge"* → both challenges
  carry ``scope``, and the 403 carries every missing scope at once because
  ``server._ScopeDenied`` already computes the complete set.
* *"The ``scopes_supported`` field is intended to represent the minimal set of
  scopes necessary for basic functionality"* → it advertises ``isaac:read``
  ALONE, not both scopes. See :attr:`OAuthResourceServerConfig.scopes_supported`,
  which also states the counter-argument rather than glossing it.
* *"MCP Servers (Protected Resources) **SHOULD NOT** include ``offline_access``
  in ``WWW-Authenticate`` scope or Protected Resource Metadata
  ``scopes_supported``"* — new in this revision, and held structurally: every
  scope string this module can emit comes from ``policy.Scope``, which has two
  members and neither is ``offline_access``. Derived, never transcribed, so it
  cannot drift into that.

THE SCOPE-HIERARCHY MUST, AND WHY ISAAC SATISFIES IT BY HAVING NO HIERARCHY
===========================================================================
*"Servers **MUST** account for scope hierarchies, where a broader scope implies
narrower ones, when deciding whether a token is sufficient for an operation."*

Read the conditional clause. ISAAC has **no** scope hierarchy, and that is a
recorded design decision predating this module: ``policy.py``'s docstring section
*"WHY THE SCOPES DO NOT NEST"* states that ``DRAFT_WRITE`` deliberately does not
imply ``READ``, because *"implication is convenient and it is also how a caller
ends up holding a permission nobody granted"*. So the requirement is satisfied
vacuously — there is no hierarchy to account for — and the resource server
**must not invent one**. A token carrying only ``isaac:draft.write`` is refused
by every read tool, and that is correct rather than an oversight: a deployment
wanting a read-write agent grants both scopes explicitly.

This is asserted, not assumed. ``test_mcp_oauth_binding.py`` builds a token
carrying only the write scope and proves a read tool answers ``403``, and proves
the reverse too, so nobody can later add an implication without a test going red.

RESOURCE SERVER ONLY. THIS MODULE IS NOT AN AUTHORIZATION SERVER
================================================================
Everything a *client* must do — sending the RFC 8707 ``resource`` parameter,
RFC 9207 ``iss`` validation, PKCE with ``S256``, client registration (Client ID
Metadata Documents or RFC 7591 DCR), and the step-up re-authorization flow — is a
MUST **on the client** and none of it is implemented here. Nothing in this
package issues a token, registers a client, redirects a user agent, or holds a
client secret. :attr:`OAuthResourceServerConfig.authorization_servers` names
external servers; it does not implement one.

THE EXTERNAL REQUIREMENT ISAAC CANNOT SATISFY FROM HERE
=======================================================
A remote connector's requests originate **from Anthropic's servers, not from the
scientist's machine**, so the endpoint *"must be reachable over the public
internet from Anthropic's IP ranges"* and a private network requires
*"allowlist[ing] Anthropic's IP addresses in your firewall"* — the range recorded
in ``docs/mcp-oauth-operator-requirements-2026-08-27.md`` §2 is
``160.79.104.0/21``, and it applies to **two** hosts: this endpoint *and the
authorization server's issuer host*, because discovery comes from the same range.
That is a firewall and DNS decision inside SLAC. **No amount of application code
can satisfy it**, this repository holds no evidence it has been made, and the
honest status is that it is Dean's and outstanding. It is named here rather than
only in a document because it is the requirement most likely to be discovered
after the code is written.

ONE PLACE THIS FILE DELIBERATELY DIVERGES FROM THE LETTER OF RFC 9728
=====================================================================
RFC 9728 §3.1 puts the metadata at the **origin root**:
``https://host/.well-known/oauth-protected-resource/krish/api/mcp``. ISAAC is
path-mounted at ``ISAAC_BASE_PATH`` behind an edge that routes ``/krish/*`` to
it, so **this application cannot serve the origin root** — it never receives
those requests. That is not a bug to work around silently. The specification's
own discovery text and the operator requirements both provide for it: the
``resource_metadata`` URL *"need not be on the MCP server's origin"*. So:

* the application serves the document at every well-known path it *can* reach
  (:func:`metadata_paths`), and
* when ``ISAAC_BASE_PATH`` is non-empty and no explicit metadata URL is
  configured, **the container refuses to boot** rather than advertising a URL it
  cannot serve. A challenge pointing at a 404 is worse than no challenge, and it
  fails at the far end of a browser round-trip where nobody can see why.

WHAT A SERVICE TOKEN BUYS, AND WHAT IT CANNOT BUY
=================================================
A verified token yields a :class:`~..identity.ServicePrincipal` at
:attr:`~..identity.TrustTier.SERVICE`. That tier can *authorize*; it can never
be an *author*. ``require_human_actor`` refuses it by construction with its own
reason, ``stamp_actor`` reads only the human field, and there is no tool to
submit with in any case — ``policy.FORBIDDEN_TOOL_TOKENS`` makes a module that
registers one fail to import. Three independent mechanisms, and this module adds
none of them; it simply does not weaken any.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit

from ..identity import (
    TRUST_BASIS_TEST_FIXTURE,
    TRUST_BASIS_VERIFIED_OAUTH_ACCESS_TOKEN,
    RequestIdentity,
    ServicePrincipal,
)
from .deployment import (
    OAUTH_RESOURCE_SERVER,
    Credential,
    DeploymentRefused,
    Principal,
    _reportable_scheme,
)
from .jwt import (
    JsonWebKeySet,
    TokenRejected,
    VerifiedToken,
    jwks_from_document,
    verify_access_token,
)
from .policy import Scope, parse_scope

__all__ = [
    "FIXTURE_TOKEN_VERIFIER",
    "JWKS_FETCHER",
    "OAUTH_RESOURCE_SERVER",
    "RECOGNISED_TOKEN_VERIFIERS",
    "UNCONFIGURED_TOKEN_VERIFIER",
    "WELL_KNOWN_PREFIX",
    "FetchedKeySource",
    "FixtureKeySource",
    "FileKeySource",
    "OAuthConfigProblem",
    "OAuthResourceServerConfig",
    "OAuthResourceServerDeployment",
    "ProtectedResourceMetadataApp",
    "StaticKeySource",
    "bearer_challenge",
    "insufficient_scope_challenge",
    "metadata_paths",
    "protected_resource_metadata",
    "resolve_oauth_binding",
    "validate_oauth_selection_or_raise",
]

#: RFC 9728 §3.1.
WELL_KNOWN_PREFIX = "/.well-known/oauth-protected-resource"

#: Token-verifier selections. Mirrors ``providers/config.py`` exactly, including
#: its asymmetry: the fixture is RECOGNISED (so tests can construct it and so a
#: typo cannot be mistaken for it) and is REFUSED AT BOOT.
UNCONFIGURED_TOKEN_VERIFIER = "unconfigured"
FIXTURE_TOKEN_VERIFIER = "test_fixture"
FILE_TOKEN_VERIFIER = "jwks-file"
URL_TOKEN_VERIFIER = "jwks-url"

RECOGNISED_TOKEN_VERIFIERS: frozenset[str] = frozenset(
    {
        UNCONFIGURED_TOKEN_VERIFIER,
        FIXTURE_TOKEN_VERIFIER,
        FILE_TOKEN_VERIFIER,
        URL_TOKEN_VERIFIER,
    }
)

#: **THE FETCH SEAM, AND IT IS ``None``.** A future slice that is authorized to
#: make an outbound request installs a callable here; until then, selecting
#: ``jwks-url`` is a configuration error that says so. It is a module attribute
#: rather than a constructor argument precisely so that its being unset is a
#: property of the BUILD and not of one call site somebody forgot.
#:
#: No code in this repository assigns it, and that is asserted by an AST scan
#: over every module in this package rather than by this sentence
#: (``test_mcp_oauth_never_leaks_a_token.py``), alongside a check that neither
#: this module nor ``jwt.py`` imports anything capable of opening a socket.
JWKS_FETCHER: Callable[[str], Mapping[str, Any]] | None = None

#: Bounds a JWKS document read from disk or from the environment. A key set is a
#: handful of kilobytes; a cap means a misconfigured path cannot make boot read a
#: multi-gigabyte file.
MAX_JWKS_BYTES = 262_144

#: ``WWW-Authenticate`` parameter values are ``quoted-string``s. Rather than
#: escaping, this refuses: every value this module emits is a configured URL or a
#: scope string from a closed enum, so a character outside this set means
#: something is wrong and the safe answer is to omit the parameter rather than to
#: emit a header a parser may split.
_SAFE_CHALLENGE_VALUE = re.compile(r"\A[\x20-\x21\x23-\x5B\x5D-\x7E]{1,512}\Z")

#: Schemes an issuer / resource / metadata URL may use. ``http`` is admitted ONLY
#: for a loopback host, so a developer can run the whole flow locally without the
#: production rule being "https unless somebody set a flag".
_HTTPS = "https"
_HTTP = "http"


class OAuthConfigProblem(Exception):
    """A configuration this build will not serve, with a reason for an operator.

    Carries no environment VALUE. An operator gets the variable's name and what
    is wrong with it; a value could be a URL that identifies internal
    infrastructure, and this message reaches logs and, at boot, container output.
    """


# --------------------------------------------------------------------------
# Key sources. None of them opens a socket.
# --------------------------------------------------------------------------


class KeySource(Protocol):
    """Where verification keys come from. Deliberately synchronous and local."""

    #: Stable name, published in the binding's status. Never a path or a URL.
    source_id: str

    def keys(self) -> JsonWebKeySet:
        """The current key set, or raise :class:`~.jwt.TokenRejected`."""


@dataclass(frozen=True)
class StaticKeySource:
    """Keys handed in directly. The shape tests construct, and the shape a future
    fetcher would populate a cache with."""

    key_set: JsonWebKeySet
    source_id: str = "static"

    def keys(self) -> JsonWebKeySet:
        return self.key_set


@dataclass
class FileKeySource:
    """Keys from a JSON file on the local filesystem. **No network, ever.**

    This is the realistic production shape for ISAAC: Kubernetes projects a
    ConfigMap or a Secret into the pod, and the application reads a file. It is
    also the only verifier in this module that both boots and mints the real
    trust basis, which is deliberate — a deployment that verifies tokens must
    have had a human decide, once, which key set it trusts.

    Cached on ``(mtime_ns, size)`` rather than for a fixed interval: a rotated
    key set is picked up on the next request after the file changes, and an
    unchanged file costs one ``stat``. A time-based cache would either serve a
    revoked key for its window or re-read the file on every request.
    """

    path: Path
    source_id: str = "jwks-file"
    _cached: tuple[tuple[int, int], JsonWebKeySet] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def keys(self) -> JsonWebKeySet:
        try:
            stat = self.path.stat()
        except OSError as exc:
            raise TokenRejected(
                "no_usable_jwks_key",
                "This server's key set is not readable, so no token can be "
                "verified.",
            ) from exc
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._cached
        if cached is not None and cached[0] == stamp:
            return cached[1]
        if stat.st_size > MAX_JWKS_BYTES:
            raise TokenRejected(
                "malformed_jwks",
                "This server's key set exceeds the size this build will read.",
            )
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise TokenRejected(
                "malformed_jwks",
                "This server's key set is not a readable JWKS document.",
            ) from exc
        key_set = jwks_from_document(document)
        self._cached = (stamp, key_set)
        return key_set


@dataclass
class FetchedKeySource:
    """Keys from :data:`JWKS_FETCHER`. **Unreachable in this build.**

    THE SEAM IS REAL AND THE DEFAULT IS OFF, AND BOTH HALVES MATTER. Writing this
    class rather than leaving a ``raise`` where a fetcher would go means the shape
    a future authorized slice fills in is reviewable now, and means the refusal
    path is exercised by a test that installs a fake fetcher rather than by a
    branch nothing can reach. What keeps it off is that :data:`JWKS_FETCHER` is
    ``None``, nothing in this repository assigns it — asserted by an AST scan, not
    by this sentence — and :func:`_key_source` refuses ``jwks-url`` outright while
    it is unset.

    **This class opens no socket itself.** It calls a callable somebody else
    installed. That is deliberate: it keeps every I/O decision — timeout, TLS
    verification, proxy, retry, SSRF policy — in the slice that is authorized to
    make an outbound request, instead of half-made here by whoever writes the
    first ``httpx`` call.

    Cached with a TTL and an injected clock. A key set that is re-fetched per
    request turns every MCP call into a dependency on the issuer being up; one
    cached forever cannot survive a key rotation without a restart.
    """

    url: str
    fetch: Callable[[str], Mapping[str, Any]]
    clock: Callable[[], float] = time.time
    ttl_seconds: int = 300
    source_id: str = "jwks-url"
    _cached: tuple[float, JsonWebKeySet] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def keys(self) -> JsonWebKeySet:
        now = self.clock()
        cached = self._cached
        if cached is not None and now < cached[0]:
            return cached[1]
        try:
            document = self.fetch(self.url)
        except Exception as exc:  # noqa: BLE001 - a fetcher may raise anything
            # NOT re-raised and NOT interpolated. The exception could carry a URL,
            # a hostname or a response body, and this message reaches a 401 body.
            # A stale-but-valid cache is deliberately NOT served here either: a
            # key set that cannot be refreshed may be one that was revoked.
            raise TokenRejected(
                "no_usable_jwks_key",
                "This server could not obtain its verification key set, so no "
                "token can be verified.",
            ) from exc
        key_set = jwks_from_document(document)
        self._cached = (now + self.ttl_seconds, key_set)
        return key_set


@dataclass(frozen=True)
class FixtureKeySource:
    """Keys read from the PROCESS ENVIRONMENT, for local and CI testing only.

    IT MIRRORS ``identity.FixtureEdgeVerifier``, INCLUDING THE ONE PROPERTY THAT
    MATTERS: the key set comes from a variable set by whoever *deploys* the
    process, never from anything the *caller* sends. The environment/header
    asymmetry is the entire safety argument there and is the entire safety
    argument here.

    **IT IS NOT AN AUTHENTICATION BYPASS.** It performs the same signature,
    issuer, audience, expiry and scope verification as
    :class:`FileKeySource` — it is a *key source*, not a shortcut, and a token
    signed by the wrong key is refused by it exactly as loudly. A fake that
    accepted anything would make every security test in this slice vacuous.

    IT IS UNREACHABLE THROUGH A BOOTED APPLICATION.
    :func:`validate_oauth_selection_or_raise` refuses to start with it selected,
    following ``providers/config.validate_provider_config_or_raise`` exactly:
    recognised, so a typo cannot be mistaken for it, and refused, so it cannot be
    switched on by an environment variable in a real deployment.

    AND ANYTHING IT VOUCHES FOR SAYS SO, FOREVER. The binding built on it mints
    :data:`~..identity.TRUST_BASIS_TEST_FIXTURE`, not the OAuth basis, so a
    principal it produces is labelled in data as fixture-verified. The label
    cannot be lost and does not depend on anyone remembering how the process was
    configured on the day.
    """

    document: Mapping[str, Any]
    source_id: str = "test_fixture"

    def keys(self) -> JsonWebKeySet:
        return jwks_from_document(self.document)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

#: Every environment variable this binding reads. They are read in
#: ``deployment.py``, which is the package's only configuration seam and the only
#: module permitted to touch the process environment at all
#: (``test_mcp_boundaries.py::test_no_mcp_module_reads_the_environment_except
#: _the_deployment_boundary``, a textual scan). This module is handed an
#: already-materialised mapping, so it never reads the environment directly and
#: every function below is a pure function of its arguments — which is also why
#: the whole configuration surface is testable without ``monkeypatch``.
RESOURCE_ENV = "ISAAC_MCP_OAUTH_RESOURCE"
ISSUER_ENV = "ISAAC_MCP_OAUTH_ISSUER"
AUTHORIZATION_SERVERS_ENV = "ISAAC_MCP_OAUTH_AUTHORIZATION_SERVERS"
TOKEN_VERIFIER_ENV = "ISAAC_MCP_OAUTH_TOKEN_VERIFIER"
JWKS_FILE_ENV = "ISAAC_MCP_OAUTH_JWKS_FILE"
JWKS_URL_ENV = "ISAAC_MCP_OAUTH_JWKS_URL"
FIXTURE_JWKS_ENV = "ISAAC_MCP_OAUTH_FIXTURE_JWKS"
METADATA_URL_ENV = "ISAAC_MCP_OAUTH_METADATA_URL"
RESOURCE_NAME_ENV = "ISAAC_MCP_OAUTH_RESOURCE_NAME"

OAUTH_ENV_VARS: tuple[str, ...] = (
    RESOURCE_ENV,
    ISSUER_ENV,
    AUTHORIZATION_SERVERS_ENV,
    TOKEN_VERIFIER_ENV,
    JWKS_FILE_ENV,
    JWKS_URL_ENV,
    FIXTURE_JWKS_ENV,
    METADATA_URL_ENV,
    RESOURCE_NAME_ENV,
)


def _canonical_uri(raw: str, *, variable: str, allow_path: bool) -> str:
    """A canonical, absolute, fragment-free URI, or raise.

    The MCP specification's canonical-URI rules, applied as refusals rather than
    as normalisations. It does NOT lowercase, strip a trailing slash, or elide a
    default port: a resource server that normalises is a resource server that
    accepts a token minted for a *different* string, and the ``aud`` comparison
    downstream is exact on purpose.
    """
    value = (raw or "").strip()
    if not value:
        raise OAuthConfigProblem(f"{variable} is required and is empty or unset.")
    parts = urlsplit(value)
    if parts.scheme not in (_HTTPS, _HTTP):
        raise OAuthConfigProblem(
            f"{variable} must be an absolute https:// URI (the specification's "
            "canonical form; a bare host with no scheme is not one)."
        )
    if not parts.hostname:
        raise OAuthConfigProblem(f"{variable} must name a host.")
    if parts.scheme == _HTTP and not _is_loopback_hostname(parts.hostname):
        raise OAuthConfigProblem(
            f"{variable} may use http:// only for a loopback host. Every other "
            "host must be https://, per the specification's communication-"
            "security requirements."
        )
    if parts.fragment:
        raise OAuthConfigProblem(f"{variable} must not contain a fragment.")
    if parts.query:
        raise OAuthConfigProblem(f"{variable} must not contain a query string.")
    if parts.username or parts.password:
        raise OAuthConfigProblem(f"{variable} must not contain userinfo.")
    if not allow_path and parts.path not in ("", "/"):
        raise OAuthConfigProblem(f"{variable} must not contain a path component.")
    return value


def _is_loopback_hostname(host: str) -> bool:
    """Literal loopback names and addresses only. No resolution, deliberately."""
    lowered = host.lower()
    if lowered in ("localhost", "127.0.0.1", "::1", "[::1]"):
        return True
    return lowered.startswith("127.")


@dataclass(frozen=True)
class OAuthResourceServerConfig:
    """Everything this binding needs, validated once, at resolution.

    Frozen and complete: there is no partially-valid configuration, because a
    resource server that is *mostly* configured is a resource server whose
    audience check might be the missing half.
    """

    #: The canonical resource URI. This is the string a token's ``aud`` must
    #: contain, verbatim, and the string a scientist types into their client.
    resource: str
    #: The authorization server that issued the token, compared to ``iss``.
    issuer: str
    #: Published in the metadata document. Always non-empty; defaults to the
    #: issuer, because the specification requires at least one entry and
    #: "unspecified" is not an option a client can act on.
    authorization_servers: tuple[str, ...]
    #: The absolute URL a ``WWW-Authenticate`` challenge points at.
    metadata_url: str
    #: Where the verification keys come from.
    key_source: KeySource
    #: What a principal this binding produces cites as its basis. The FIXTURE key
    #: source mints the fixture basis; every other source mints the OAuth one.
    trust_basis: str
    #: Optional human-readable name for the metadata document.
    resource_name: str = ""
    #: Clock skew allowance, in seconds, for ``exp`` and ``nbf``.
    leeway_seconds: int = 60

    @property
    def scopes_supported(self) -> tuple[str, ...]:
        """What the metadata document advertises. **``isaac:read`` ONLY.**

        The specification is explicit about what this field is for: *"The
        ``scopes_supported`` field is intended to represent the minimal set of
        scopes necessary for basic functionality … with additional scopes
        requested incrementally through the step-up authorization flow."* Basic
        functionality here is reading, so that is what is advertised.

        THE COUNTER-ARGUMENT, STATED RATHER THAN GLOSSED. This under-declares
        what the resource supports: :class:`~.policy.Scope` has two members and
        this names one. It is deliberate, and it is not security by obscurity —
        ``isaac:draft.write`` is not hidden, it is *reached differently*. A
        client attempting a write tool gets ``403`` with
        ``scope="isaac:draft.write"`` in the challenge, which the specification
        designates as the way to obtain it, and ``tools/list`` names every tool's
        required scope to any authenticated caller. What advertising both would
        buy is a client following rule 2 of the scope-selection strategy — *"if
        ``scope`` is not available, use all scopes defined in
        ``scopes_supported``"* — requesting the write scope for a read-only
        agent, on its first authorization, forever.

        Derived from the enum rather than transcribed, so it cannot drift from
        what the server enforces, and so ``offline_access`` — which this
        revision says a protected resource **SHOULD NOT** advertise — cannot
        appear unless somebody puts it in :class:`~.policy.Scope`.
        """
        return (Scope.READ.value,)

    @property
    def scopes_expressible(self) -> tuple[str, ...]:
        """Every scope this server can express. NOT what the metadata advertises.

        Kept separate from :attr:`scopes_supported` so the difference between
        "what exists" and "what is advertised as the minimal starting set" is a
        distinction in the code and not a comment somebody deletes.
        """
        return tuple(sorted(scope.value for scope in Scope))


# --------------------------------------------------------------------------
# The RFC 9728 document and the RFC 6750 challenges
# --------------------------------------------------------------------------


def protected_resource_metadata(config: OAuthResourceServerConfig) -> dict:
    """The RFC 9728 protected-resource-metadata document.

    ``bearer_methods_supported`` is ``["header"]`` and that is a load-bearing
    statement, not boilerplate: RFC 6750 defines three ways to present a token
    and this server accepts exactly one. Publishing the other two would be a lie
    a conforming client would act on.
    """
    document: dict[str, Any] = {
        "resource": config.resource,
        "authorization_servers": list(config.authorization_servers),
        "scopes_supported": list(config.scopes_supported),
        "bearer_methods_supported": ["header"],
    }
    if config.resource_name:
        document["resource_name"] = config.resource_name
    return document


def _challenge_parameters(pairs: Sequence[tuple[str, str]]) -> str:
    """``Bearer`` plus ``k="v"`` pairs, omitting anything unsafe to emit.

    A value failing :data:`_SAFE_CHALLENGE_VALUE` is DROPPED rather than escaped
    or truncated. Escaping is a second parser to get right; truncation publishes
    a fragment of something that should not have been published at all.
    """
    rendered = [
        f'{name}="{value}"'
        for name, value in pairs
        if value and _SAFE_CHALLENGE_VALUE.match(value)
    ]
    if not rendered:
        return "Bearer"
    return "Bearer " + ", ".join(rendered)


def bearer_challenge(
    config: OAuthResourceServerConfig,
    *,
    error: str | None = None,
    error_description: str | None = None,
) -> dict:
    """The ``401`` challenge, in the shape ``deployment.DeploymentBinding`` returns.

    ``error`` is **omitted for a request that simply carried no credential**, per
    RFC 6750 §3: *"If the request lacks any authentication information ... the
    resource server SHOULD NOT include an error code."* A first, unauthenticated
    probe is the normal start of the flow, not a failure, and reporting
    ``invalid_token`` for it sends clients down an error path.
    """
    pairs: list[tuple[str, str]] = [("resource_metadata", config.metadata_url)]
    if error:
        pairs.append(("error", error))
    if error_description:
        pairs.append(("error_description", error_description))
    # Least privilege: the challenge names the scope needed to do anything at
    # all, not every scope the resource supports. A client that follows the
    # specification's scope-selection strategy asks for what it is told to ask
    # for, so telling it "everything" is how an agent ends up holding the write
    # scope it never needed.
    pairs.append(("scope", Scope.READ.value))
    return {
        "scheme": "Bearer",
        "www_authenticate": _challenge_parameters(pairs),
        "resource_metadata": config.metadata_url,
        "note": (
            "RFC 9728 protected-resource metadata is published at the URL above. "
            "This server accepts a bearer token in the Authorization header only."
        ),
    }


def insufficient_scope_challenge(
    config: OAuthResourceServerConfig, required: Sequence[str]
) -> dict:
    """The ``403`` challenge for a token that authenticated but is not permitted.

    Carries **every** missing scope in one challenge, which the specification
    asks for in as many words: challenging incrementally *"forces multiple
    authorization round-trips for a single operation"*. ``server._ScopeDenied``
    already computes the complete set, so this is a matter of not throwing it
    away.
    """
    wanted = " ".join(sorted({str(item) for item in required if item}))
    pairs: list[tuple[str, str]] = [
        ("error", "insufficient_scope"),
        (
            "error_description",
            "The presented token does not carry the scope this operation needs.",
        ),
        ("resource_metadata", config.metadata_url),
    ]
    if wanted:
        pairs.append(("scope", wanted))
    return {
        "scheme": "Bearer",
        "www_authenticate": _challenge_parameters(pairs),
        "resource_metadata": config.metadata_url,
        "note": "Re-authorize for the named scopes and retry once.",
    }


def metadata_paths(config: OAuthResourceServerConfig, base: str) -> tuple[str, ...]:
    """Every well-known path THIS APPLICATION can serve the document at.

    Not the same question as "where does RFC 9728 say it lives" — see the module
    docstring. The origin-root path is unreachable for a path-mounted
    deployment, so the application serves the reachable neighbourhood of it and
    the operator supplies the advertised URL. Ordered and de-duplicated so the
    registered route list is deterministic.
    """
    resource_path = urlsplit(config.resource).path.rstrip("/")
    candidates = [f"{base}{WELL_KNOWN_PREFIX}"]
    if resource_path:
        candidates.append(f"{base}{WELL_KNOWN_PREFIX}{resource_path}")
        if base and resource_path.startswith(base):
            trimmed = resource_path[len(base) :]
            if trimmed:
                candidates.append(f"{base}{WELL_KNOWN_PREFIX}{trimmed}")
    seen: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


class ProtectedResourceMetadataApp:
    """A raw ASGI app serving one public JSON document.

    Raw ASGI, and registered as a plain Starlette ``Route``, for the same two
    reasons the MCP transport is: this package imports no web framework
    (``test_mcp_boundaries.py`` pins that), and a non-OpenAPI document must not
    appear in ISAAC's OpenAPI schema — the published operation count is asserted
    exactly, and a metadata endpoint is not an ISAAC API operation.

    **It is unauthenticated on purpose.** RFC 9728 metadata is what a client
    reads *before* it has a token; requiring one would make the flow
    unstartable. It contains only configuration an operator chose to publish —
    no record, no identity, no key material, no environment value.
    """

    #: The body a non-read method gets. A body rather than nothing, because the
    #: ``Content-Type`` says JSON and a zero-length JSON document is not one.
    _REFUSAL = json.dumps(
        {"error": "method_not_allowed", "allow": ["GET", "HEAD"]}, sort_keys=True
    ).encode("utf-8")

    def __init__(self, document: Mapping[str, Any]) -> None:
        # Serialised once. The document is fixed for the process lifetime, and a
        # byte-stable body makes the response reproducible and cacheable.
        self._body = json.dumps(dict(document), sort_keys=True).encode("utf-8")

    async def __call__(self, scope: Mapping[str, Any], receive, send) -> None:
        if scope.get("type") == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope.get("type") != "http":
            return
        method = (scope.get("method") or "").upper()
        if method == "GET":
            await self._send(send, 200, self._body, len(self._body))
        elif method == "HEAD":
            # RFC 9110 §9.3.2: identical headers to the GET, no body. So the
            # declared length is the DOCUMENT's, not zero — a HEAD advertising
            # ``content-length: 0`` tells a client the document is empty.
            await self._send(send, 200, b"", len(self._body))
        else:
            await self._send(
                send, 405, self._REFUSAL, len(self._REFUSAL), allow=True
            )

    async def _send(
        self, send, status: int, body: bytes, declared: int, *, allow: bool = False
    ):
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(declared).encode("ascii")),
            # Public, immutable-for-this-process configuration. A short cache
            # keeps a client's discovery step cheap; it holds nothing private,
            # which is exactly why it may be cached at all.
            (b"cache-control", b"public, max-age=300"),
            (b"x-content-type-options", b"nosniff"),
        ]
        if allow:
            headers.append((b"allow", b"GET, HEAD"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


# --------------------------------------------------------------------------
# The binding
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OAuthResourceServerDeployment:
    """Authenticates a caller by verifying an OAuth 2.1 bearer access token.

    THE THREE LOCAL-SERVER DEFENCES ARE ANSWERED INDIVIDUALLY, WHICH IS WHY
    ``transport.py`` SPLIT THE FLAG. ``deployment.py``'s module docstring
    predicted this binding and warned that its author would set
    ``requires_loopback_peer=False`` and thereby *silently* disable the
    proxy-header refusal and the DNS-rebinding refusal too. Rather than inherit
    that, each is declared here with its own reason:

    * :attr:`requires_loopback_peer` — ``False``. The whole point is a remote
      caller. The token is the authentication; the peer address is not evidence
      of anything and never was.
    * :attr:`refuses_proxy_headers` — ``False``. This binding is *expected* to be
      reached through a reverse proxy. Note what does **not** follow: nothing
      here starts *trusting* a forwarded header. Their values remain unread —
      ``CLAUDE.md`` records that the Service is a plain ClusterIP with no
      NetworkPolicy, so a forwarded header is forgeable by any in-cluster
      caller, and this binding's answer to that is that it does not consult one.
    * :attr:`requires_loopback_origin` — ``False``. The rebinding defence exists
      because a *local* server is otherwise reachable by any web page. This
      server refuses every request that does not carry a token this deployment's
      issuer signed, and a page on another origin cannot obtain one: it is not
      a cookie, the browser will not attach it, and no CORS policy here exposes
      the response.
    """

    config: OAuthResourceServerConfig
    name: str = OAUTH_RESOURCE_SERVER
    serves_transport: bool = True
    requires_loopback_peer: bool = False
    refuses_proxy_headers: bool = False
    requires_loopback_origin: bool = False
    #: Injectable for tests, so expiry and not-yet-valid are exercised
    #: deterministically rather than by sleeping.
    clock: Callable[[], float] = time.time

    # -- authentication -------------------------------------------------------

    def authenticate(self, credential: Credential | None) -> Principal:
        """A :class:`~.deployment.Principal`, or raise :class:`DeploymentRefused`.

        **There is no anonymous branch.** Every path out of this method either
        returns a principal built from a token that verified, or raises. A
        deployment that answered "no credential" with a read-only principal
        would be a public MCP endpoint, and it would look, in every log and every
        status surface, exactly like a working authenticated one.
        """
        if credential is None:
            raise self._refuse(
                "token_absent",
                "This resource requires an OAuth 2.1 bearer access token in the "
                "Authorization header.",
                # No `error` for a bare unauthenticated probe: RFC 6750 §3.
                error=None,
            )
        if credential.scheme.lower() != "bearer":
            # A non-Bearer scheme is refused rather than tried as a bearer token.
            # The scheme is reported through the allowlist that exists because a
            # bare credential once reached a response body through this field.
            #
            # `error=None`, and RFC 6750 §3 decides that rather than taste: the
            # sentence that omits an error code for a request lacking
            # authentication information names this case in its own parenthesis —
            # "*or attempted using an unsupported authentication method*". The
            # obvious alternative, `invalid_request`, is defined for a malformed
            # BEARER request and §3.1 pairs it with a 400; this is not a malformed
            # bearer request, it is the absence of one. The distinct `code` in the
            # body still tells a client and an operator exactly what happened.
            raise self._refuse(
                "unsupported_authentication_scheme",
                "This resource accepts the Bearer scheme only.",
                error=None,
                data={"scheme": _reportable_scheme(credential.scheme)},
            )

        try:
            key_set = self.config.key_source.keys()
            verified = verify_access_token(
                credential.token,
                keys=key_set,
                issuer=self.config.issuer,
                resource=self.config.resource,
                now=int(self.clock()),
                leeway_seconds=self.config.leeway_seconds,
            )
        except TokenRejected as rejected:
            # `rejected.message` is one of `jwt._REJECTIONS`' fixed strings. No
            # branch in that module interpolates token material, which is what
            # makes it safe to return here and to log.
            raise self._refuse(
                rejected.code,
                rejected.message,
                error=rejected.oauth_error,
            ) from rejected

        return Principal(
            subject=verified.subject,
            binding=self.name,
            scopes=self._granted(verified),
            # The ordinary workspace. A token cannot pin itself to a worked
            # example: the tutorial scope comes from the BINDING, and this
            # binding does not offer one.
            tutorial_session_id=None,
        )

    def _granted(self, verified: VerifiedToken) -> frozenset[Scope]:
        """The ISAAC scopes this token carries. Unrecognised strings are dropped.

        Dropping is correct HERE and would be wrong in configuration, and the
        asymmetry is deliberate. ``deployment._parse_scopes`` treats an unknown
        scope in an operator's own configuration as a fatal misconfiguration,
        because a silently narrowed grant is a server running with permissions
        nobody wrote down. A TOKEN legitimately carries scopes for other things —
        ``openid``, ``profile``, an unrelated resource's — and refusing the whole
        token for them would make ISAAC unusable with any ordinary issuer.

        A token that maps to NO ISAAC scope authenticates and authorizes nothing:
        every tool call then answers ``403 insufficient_scope`` with the scope it
        needed. That is the honest outcome and it is a tested one.
        """
        granted = set()
        for raw in verified.scope_strings:
            scope = parse_scope(raw)
            if scope is not None:
                granted.add(scope)
        return frozenset(granted)

    def service_identity(self, principal: Principal) -> RequestIdentity:
        """The identity-plane view of an authenticated MCP caller.

        **A service, never a person.** The token proves that a *client* holds a
        credential the issuer minted; it does not establish that a human is
        present, and this deployment has no trusted boundary that could. So the
        tier is :attr:`~..identity.TrustTier.SERVICE`, and every consequence of
        that tier follows without this module arranging any of them:
        ``require_human_actor`` refuses it with
        ``service_principal_not_attributable``, ``stamp_actor`` returns ``None``
        because it reads only the human field, and
        :class:`~..identity.ServicePrincipal` has no ``subject`` attribute for a
        stamping call site to reach for by mistake.

        The basis it cites depends on the KEY SOURCE, not on the code path: a
        fixture-verified token says ``test_fixture`` in data, forever.
        """
        return RequestIdentity.for_service(
            ServicePrincipal(
                principal_id=principal.subject,
                trust_basis=self.config.trust_basis,
            )
        )

    # -- challenges -----------------------------------------------------------

    def challenge(self) -> dict:
        """The generic ``401`` challenge, for a caller that presented nothing."""
        return bearer_challenge(self.config)

    def scope_challenge(self, required: Sequence[str]) -> dict:
        """The ``403`` challenge. Read by ``transport.py`` through ``getattr``, so
        a binding that does not define it simply emits no header."""
        return insufficient_scope_challenge(self.config, required)

    # -- discovery ------------------------------------------------------------

    def protected_resource_metadata(self) -> dict:
        """The RFC 9728 document. Its presence is what makes routes get mounted."""
        return protected_resource_metadata(self.config)

    def metadata_paths(self, base: str) -> tuple[str, ...]:
        """Where this application can actually serve that document."""
        return metadata_paths(self.config, base)

    def _refuse(
        self,
        code: str,
        message: str,
        *,
        error: str | None,
        data: dict | None = None,
    ) -> DeploymentRefused:
        return DeploymentRefused(
            code,
            message,
            data={
                "binding": self.name,
                "resource": self.config.resource,
                "resource_metadata": self.config.metadata_url,
                **(data or {}),
            },
            challenge=bearer_challenge(
                self.config, error=error, error_description=message if error else None
            ),
        )


# --------------------------------------------------------------------------
# Resolution and boot validation
# --------------------------------------------------------------------------


def _authorization_servers(env: Mapping[str, str], issuer: str) -> tuple[str, ...]:
    raw = (env.get(AUTHORIZATION_SERVERS_ENV) or "").strip()
    if not raw:
        return (issuer,)
    servers: list[str] = []
    for part in raw.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        servers.append(
            _canonical_uri(
                candidate, variable=AUTHORIZATION_SERVERS_ENV, allow_path=True
            )
        )
    if not servers:
        raise OAuthConfigProblem(
            f"{AUTHORIZATION_SERVERS_ENV} is set but names no authorization "
            "server. RFC 9728 requires at least one."
        )
    return tuple(servers)


def _key_source(env: Mapping[str, str]) -> tuple[KeySource, str]:
    """``(source, trust_basis)`` for the selected verifier, or raise."""
    raw = (env.get(TOKEN_VERIFIER_ENV) or "").strip()
    selection = raw or UNCONFIGURED_TOKEN_VERIFIER

    if selection == UNCONFIGURED_TOKEN_VERIFIER:
        raise OAuthConfigProblem(
            f"{TOKEN_VERIFIER_ENV} is unset, so this deployment has no way to "
            "verify a token and will not serve an unauthenticated MCP endpoint. "
            f"Expected one of {sorted(RECOGNISED_TOKEN_VERIFIERS)}."
        )
    if selection not in RECOGNISED_TOKEN_VERIFIERS:
        raise OAuthConfigProblem(
            f"{TOKEN_VERIFIER_ENV} names a token verifier this build does not "
            f"have. Expected one of {sorted(RECOGNISED_TOKEN_VERIFIERS)}."
        )

    if selection == FILE_TOKEN_VERIFIER:
        path = (env.get(JWKS_FILE_ENV) or "").strip()
        if not path:
            raise OAuthConfigProblem(
                f"{TOKEN_VERIFIER_ENV}='{FILE_TOKEN_VERIFIER}' requires "
                f"{JWKS_FILE_ENV} to name a readable JWKS file."
            )
        return FileKeySource(path=Path(path)), TRUST_BASIS_VERIFIED_OAUTH_ACCESS_TOKEN

    if selection == URL_TOKEN_VERIFIER:
        # THE SEAM, AND ITS DEFAULT. `JWKS_FETCHER` is `None` in this build and
        # nothing assigns it, so this selection always refuses here. Read through
        # the module global at CALL time rather than captured at import, which is
        # what lets a test install a fake fetcher and drive the whole path —
        # otherwise `FetchedKeySource` would be unreachable code asserting its own
        # correctness.
        fetcher = JWKS_FETCHER
        if fetcher is None:
            raise OAuthConfigProblem(
                f"{TOKEN_VERIFIER_ENV}='{URL_TOKEN_VERIFIER}' is refused: this "
                "build installs no JWKS fetcher and makes no outbound request. "
                f"Project the key set into the pod and use "
                f"'{FILE_TOKEN_VERIFIER}' instead."
            )
        url = _canonical_uri(
            env.get(JWKS_URL_ENV, ""), variable=JWKS_URL_ENV, allow_path=True
        )
        return (
            FetchedKeySource(url=url, fetch=fetcher),
            TRUST_BASIS_VERIFIED_OAUTH_ACCESS_TOKEN,
        )

    # test_fixture
    raw_document = (env.get(FIXTURE_JWKS_ENV) or "").strip()
    if not raw_document:
        raise OAuthConfigProblem(
            f"{TOKEN_VERIFIER_ENV}='{FIXTURE_TOKEN_VERIFIER}' requires "
            f"{FIXTURE_JWKS_ENV} to carry a JWKS document."
        )
    if len(raw_document.encode("utf-8")) > MAX_JWKS_BYTES:
        raise OAuthConfigProblem(f"{FIXTURE_JWKS_ENV} exceeds the size this build reads.")
    try:
        document = json.loads(raw_document)
    except ValueError as exc:
        raise OAuthConfigProblem(f"{FIXTURE_JWKS_ENV} is not valid JSON.") from exc
    if not isinstance(document, Mapping):
        raise OAuthConfigProblem(f"{FIXTURE_JWKS_ENV} is not a JWKS object.")
    return FixtureKeySource(document=document), TRUST_BASIS_TEST_FIXTURE


def build_config(env: Mapping[str, str], base: str) -> OAuthResourceServerConfig:
    """The validated configuration, or raise :class:`OAuthConfigProblem`.

    Every check is a refusal rather than a default. There is no
    partially-configured resource server here: the audience string, the issuer
    and the key set are each required, and a resource server missing any one of
    them is a resource server that cannot make the check the specification calls
    a MUST.
    """
    resource = _canonical_uri(
        env.get(RESOURCE_ENV, ""), variable=RESOURCE_ENV, allow_path=True
    )
    issuer = _canonical_uri(env.get(ISSUER_ENV, ""), variable=ISSUER_ENV, allow_path=True)
    servers = _authorization_servers(env, issuer)
    key_source, trust_basis = _key_source(env)

    explicit_metadata = (env.get(METADATA_URL_ENV) or "").strip()
    if explicit_metadata:
        metadata_url = _canonical_uri(
            explicit_metadata, variable=METADATA_URL_ENV, allow_path=True
        )
    else:
        if base:
            # THE TRAP THE OPERATOR REQUIREMENTS DOCUMENT NAMES, MADE A BOOT
            # FAILURE. With a base path, the RFC 9728 origin-root URL is a path
            # this application never receives, so the derived default would
            # advertise a 404. That failure surfaces at the far end of a browser
            # round-trip inside a client nobody here can debug.
            raise OAuthConfigProblem(
                f"{METADATA_URL_ENV} must be set explicitly when ISAAC_BASE_PATH "
                "is in use. This deployment is path-mounted, so it cannot serve "
                f"the RFC 9728 origin-root path '{WELL_KNOWN_PREFIX}...'; the "
                "advertised URL must point at a location that is actually "
                "served."
            )
        parts = urlsplit(resource)
        metadata_url = (
            f"{parts.scheme}://{parts.netloc}{WELL_KNOWN_PREFIX}{parts.path.rstrip('/')}"
        )

    return OAuthResourceServerConfig(
        resource=resource,
        issuer=issuer,
        authorization_servers=servers,
        metadata_url=metadata_url,
        key_source=key_source,
        trust_basis=trust_basis,
        resource_name=(env.get(RESOURCE_NAME_ENV) or "").strip(),
    )


def resolve_oauth_binding(
    env: Mapping[str, str], base: str
) -> OAuthResourceServerDeployment | str:
    """The binding, or a reason string. **Never raises.**

    Mirrors ``deployment.resolve_binding``'s contract exactly: resolution fails
    closed and reports, and a *separate* function turns a misconfiguration into
    a container that does not start. A resolver that raised would turn a manifest
    typo into a 500 on every route in the application.
    """
    try:
        config = build_config(env, base)
    except OAuthConfigProblem as problem:
        return f"misconfigured: {problem}"
    return OAuthResourceServerDeployment(config=config)


def validate_oauth_selection_or_raise(env: Mapping[str, str], base: str) -> None:
    """Raise ``RuntimeError`` when this deployment asked for OAuth and cannot have it.

    Called from ``create_app()`` only when ``ISAAC_MCP_DEPLOYMENT`` actually names
    this binding, so a deployment that never asked for MCP is untouched — which
    is every shipped one.

    TWO SEPARATE REFUSALS, AND THE SECOND IS THE ONE THAT MATTERS:

    1. **Incomplete or invalid configuration.** Fails closed at resolution
       anyway; failing at boot as well is the difference between "the operator
       finds out from a scanner" and "the operator finds out from the container".
    2. **The fixture key source, refused outright.** Recognised so a typo cannot
       be mistaken for it, and refused so no running application can be
       configured onto it — the exact asymmetry
       ``providers/config.validate_provider_config_or_raise`` uses for the
       deterministic fakes. Tests construct the binding directly; a boot is not
       a test.
    """
    selection = (env.get(TOKEN_VERIFIER_ENV) or "").strip()
    if selection == FIXTURE_TOKEN_VERIFIER:
        raise RuntimeError(
            f"{TOKEN_VERIFIER_ENV}='{FIXTURE_TOKEN_VERIFIER}' is refused: the "
            "fixture key source exists for tests and is not reachable through a "
            "running application. It performs real verification, but anything it "
            "vouches for is labelled a fixture in data, and a deployment must not "
            "be able to reach that state by setting an environment variable. Use "
            f"'{FILE_TOKEN_VERIFIER}' with a projected key set."
        )
    resolved = resolve_oauth_binding(env, base)
    if isinstance(resolved, str):
        raise RuntimeError(
            f"ISAAC_MCP_DEPLOYMENT='{OAUTH_RESOURCE_SERVER}' cannot be served: "
            f"{resolved}"
        )
