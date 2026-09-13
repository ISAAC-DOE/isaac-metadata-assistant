"""Operator preflight: why is this MCP deployment not working, answered offline.

WHAT THIS IS FOR
================
An operator who has just set ``ISAAC_MCP_DEPLOYMENT`` has four ways to get a
refusal and they look nothing like each other from the client side. This module
answers, from configuration alone, **which** of the four a given configuration
produces and **why** — so the answer comes from reading code rather than from
pointing a client at a deployment and guessing from a status code.

**NO PRODUCTION CALL IS AUTHORIZED AND THIS MODULE MAKES NONE.** Reachability
(**D1**) and the authentication model (**D2**) were DEFERRED on 2026-08-12
(``CLAUDE.md`` §15; ``docs/mcp-capability-audit.md`` §6), and no endpoint,
credential, network path or provider approval exists. Everything here is a
diagnostic over values the operator already holds. It opens no socket, resolves
no name, contacts no authorization server and reads no file — see the I/O
section below, which is narrower than "no I/O" and says so.

THE ONE FINDING THIS MODULE EXISTS TO MAKE LEGIBLE
==================================================
ISAAC's audience check is **exact string equality**::

    audiences = _audiences(claims.get("aud"))          # jwt.py:611
    if resource not in audiences:                      # jwt.py:612
        raise _reject("audience_mismatch")             # jwt.py:613

**RFC 8707 §2.2 permits an authorization server to MAP** the ``resource`` a
client requested onto a different audience value:

    "The authorization server may use the exact ``resource`` value as the
    audience or it may map from that value to a more general URI or abstract
    identifier for the given resource."

*(That quotation and section number are taken from
``docs/mcp-oauth-operator-requirements-2026-08-27.md``, which already cites
§2.2 verbatim. **This module did not re-read the RFC** and does not claim to;
an earlier revision of this docstring cited "§2" with a paraphrase, which was
less precise than what the repository already held.)*

So an AS may legitimately mint ``aud`` as the canonical form it prefers — a
trailing slash added or removed, a host lowercased, a default port elided, a
percent-triplet re-cased — and be **correct** by the RFC.

**THE TRAP ITSELF IS NOT A NEW FINDING AND MUST NOT BE PRESENTED AS ONE.** That
same document already names it (*"an AS configured to map, rewrite or normalise
the audience produces a 100%-failing deployment that looks correct from both
ends"*) and already tells an operator to confirm the claim character for
character. What did not exist is a way to *perform* that comparison — and a
mismatch reported by eye is exactly the comparison a trailing slash survives.
This module is the executable half of a warning the repository had already
written down.

ISAAC accepts none of those. ``oauth._canonical_uri`` (``oauth.py``:580)
deliberately *refuses* malformed configuration rather than *normalising* it, and
its own docstring gives the reason: *"a resource server that normalises is a
resource server that accepts a token minted for a different string, and the
``aud`` comparison downstream is exact on purpose."*

The consequence is the whole point of this module: **a deployment can be correct
at the authorization server, correct at ISAAC, and fail 100% of calls** — with a
``401`` whose message says only *"The token was not issued for this resource"*
(``jwt.py``'s ``audience_mismatch``). Nothing in either system reports that the
two strings are *nearly* the same, because neither system has both strings and a
reason to compare them charitably. :func:`audience_comparison` is the place that
does, and it says *exact-string mismatch* rather than implying the token is
invalid in general — because under RFC 8707 it may be a perfectly valid token.

WHAT IS DELIBERATELY NOT MODELLED HERE
======================================
This module models the **HTTP envelope** ladder and stops. It does not model the
JSON-RPC body ladder — protocol-era negotiation, header/``_meta`` version
agreement, batching, per-tool scope checks — and the reason is not effort:
``server.py`` already implements that ladder once, and a *second* implementation
of an authorization decision is a thing that can drift from the first while
still looking authoritative. A preflight that quietly disagreed with the server
about who may call a tool would be worse than no preflight.

For the same reason the credential row is **not modelled at all**. It is
answered by calling the binding's own :meth:`authenticate(None)
<.deployment.DeploymentBinding.authenticate>` — the real decision, on the real
object — and only :class:`~.deployment.DeploymentRefused` is caught. Any other
exception propagates: a preflight that swallowed one would report a working
deployment.

I/O, STATED NARROWLY
====================
**This module performs no I/O of its own.** That is the exact claim, and it is
narrower than it looks in two places a reader should know about:

1. **It never resolves the OAuth binding itself**, and that is not tidiness.
   ``resolve_binding`` with ``ISAAC_MCP_DEPLOYMENT=oauth-resource-server``
   reaches ``oauth.build_config``, which **probes the key set at boot**
   (``oauth.py``:1370 — ``key_source.keys()``), and ``FileKeySource.keys()``
   ``stat``s and reads a file. So resolution touches the filesystem. A preflight
   that called it would make a diagnostic's success depend on the very thing the
   operator is trying to diagnose. :func:`binding_selection` therefore classifies
   the *name* and reports ``mounts_transport=None`` — *unknown without
   resolution* — for that one name, and :func:`transport_outcome` takes an
   already-resolved binding from the caller.
2. **A binding's ``authenticate`` is the binding's code, not this module's.**
   Both shipped bindings answer a ``None`` credential without I/O (``oauth.py``
   refuses at :1037, before it reaches ``key_source``); a binding added later
   could not. The guarantee is scoped to this file.

SECRET EXPOSURE: WHAT IS ECHOED, AND THE REASONING
==================================================
**Nothing in any return value here carries a token, a signature, a key, a
client secret, an ``Authorization`` header, or any audience or resource string.**

The tempting exception was the one this module is *for*: an operator debugging an
audience mismatch already has both strings in front of them, so echoing them
back seems free, and ``"expected <resource>, got <aud>"`` is the most useful
sentence a diagnostic could print. It is not printed, for three reasons, and the
third is the deciding one:

* ``jwt.py``:106 records, as a committed design decision, that the refusal path
  never writes *"expected audience X, got Y"* because ``Y`` is attacker-supplied.
  A second code path in the same package that *does* print it invites somebody to
  route the useful one into the refusal.
* An operator-initiated local diagnostic is a defensible place to echo, and it is
  also a function signature. Nothing stops a later route, tool or log line from
  calling it with values that did not come from an operator. The safe property is
  one that holds regardless of caller.
* **Two rules with an exception invite the exception to be widened; one rule is
  auditable.** So: one rule, no knob. There is deliberately no
  ``reveal=True`` parameter, because the parameter would be the vulnerability.

What is reported instead is enough to act on and carries no content: the
**length** of each string, the **index of first divergence**, and the **set of
standard URI normalisations under which the two would be equal**. An operator
told *"your configured resource and the token's audience differ first at index
31, lengths 32 and 31, and are equal under {trailing_slash}"* knows precisely
what to fix without this module having recited either value.

One value IS echoed, through an allowlist: the ``ISAAC_MCP_DEPLOYMENT`` value,
and **only when it is one of this build's documented binding names**. Anything
else reports as ``""``. That is ``deployment._reportable_scheme``'s idiom applied
to a second field, and the reason is the same: a cap would publish the first N
characters of whatever an operator pasted into that variable, which is not a
redaction. ``deployment.UnconfiguredDeployment.supplied`` echoes the raw value
and is right to — it is a refusal an operator reads — but this module composes
reports that a caller may log, so it takes the narrower rule.

Configuration is reported as **presence only**: a boolean per variable, never a
value. ``ISAAC_MCP_OAUTH_FIXTURE_JWKS`` holds a whole JWKS document, and even
public keys are not something a diagnostic should be copying around.

THE ENVIRONMENT IS AN ARGUMENT, NOT A LOOKUP
============================================
Every function here takes the environment as a ``Mapping`` and there is no
default. Partly because a diagnostic whose answer depends on ambient state is a
diagnostic you cannot reason about — but mainly because
``test_mcp_boundaries.py::test_no_mcp_module_reads_the_environment_except_the_
deployment_boundary`` asserts that ``deployment.py`` is the **only** module in
this package that reads the environment, and that assertion is worth more than
the convenience. The caller supplies the mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from .deployment import (
    DEPLOYMENT_ENV,
    LOCAL_LOOPBACK,
    LOCAL_SCOPES_ENV,
    LOCAL_SESSION_ENV,
    OAUTH_RESOURCE_SERVER,
    RESERVED_BINDING_NAMES,
    UNCONFIGURED,
    DeploymentBinding,
    DeploymentRefused,
)
from .jwt import _audiences
# `_origin_is_loopback` is private and is imported anyway, deliberately. The
# alternative is re-deriving the rule here, and the rule has a case that is easy
# to lose: an `Origin` of `"null"` — what a sandboxed iframe and a `file://`
# document send — is REFUSED, not treated as absent. A second copy that dropped
# that would make this module report `served` for a request the transport
# refuses, which is the one kind of error a preflight must not make.
from .transport import MCP_PATH, PROXY_HEADERS, _origin_is_loopback, is_loopback_host

__all__ = [
    "ADJACENT_OUTCOMES",
    "AudienceCandidate",
    "AudienceComparison",
    "BindingSelection",
    "CLASSIFICATION_LOCAL_LOOPBACK",
    "CLASSIFICATION_OAUTH_RESOURCE_SERVER",
    "CLASSIFICATION_RESERVED",
    "CLASSIFICATION_UNRECOGNISED",
    "CLASSIFICATION_UNSET",
    "DECISION_TABLE",
    "DecisionRow",
    "MCP_PATH",
    "NORMALISATIONS",
    "OUTCOME_CREDENTIAL_REQUIRED",
    "OUTCOME_ENTRY_GUARD_REFUSED",
    "OUTCOME_METHOD_NOT_ALLOWED",
    "OUTCOME_SERVED",
    "OUTCOME_UNMOUNTED",
    "TransportOutcome",
    "VERDICT_ACCEPTED",
    "VERDICT_DIFFERENT_RESOURCE",
    "VERDICT_EXACT_STRING_MISMATCH",
    "VERDICT_NO_USABLE_AUDIENCE",
    "audience_comparison",
    "binding_selection",
    "configuration_presence",
    "configuration_variables",
    "preflight_report",
    "transport_outcome",
]


# --------------------------------------------------------------------------
# 1. The decision table
# --------------------------------------------------------------------------

#: No route is registered. The router answers, and nothing in this package runs.
OUTCOME_UNMOUNTED = "unmounted"
#: A route exists, the entry guards passed, and the verb is not ``POST``.
OUTCOME_METHOD_NOT_ALLOWED = "method_not_allowed"
#: A route exists and one of the three entry guards refused before the verb was
#: looked at — peer, proxy header, or browser origin.
OUTCOME_ENTRY_GUARD_REFUSED = "entry_guard_refused"
#: A route exists, the envelope is acceptable, and the binding wants a credential
#: this request did not carry (or carried unverifiably).
OUTCOME_CREDENTIAL_REQUIRED = "credential_required"
#: Nothing in the HTTP envelope refuses this request. What happens next is the
#: JSON-RPC body's business, which this module deliberately does not model.
OUTCOME_SERVED = "served"


@dataclass(frozen=True)
class DecisionRow:
    """One row of the operator-facing status table.

    ``evidence`` is a tuple of ``file:line`` citations, each **read** rather than
    transcribed from a brief. It is a field rather than prose so the documentation
    and the tests can be generated from one object; a table nobody can re-derive
    is a table that goes stale silently.
    """

    outcome: str
    status: int
    condition: str
    why: str
    evidence: tuple[str, ...]
    #: Whether :func:`transport_outcome` can produce this row. The four briefed
    #: rows can; the adjacent ones are documented and not modelled.
    modelled: bool = True


#: THE FOUR ROWS. Verified against the source at this commit, not transcribed.
DECISION_TABLE: tuple[DecisionRow, ...] = (
    DecisionRow(
        outcome=OUTCOME_UNMOUNTED,
        status=404,
        condition=(
            "ISAAC_MCP_DEPLOYMENT is unset, empty, unrecognised, reserved, or "
            "names a binding whose configuration does not resolve."
        ),
        why=(
            "There is no route. app.py only imports this package when the "
            "variable is non-empty, and mcp_transport_or_none returns None for "
            "any binding whose serves_transport is false, in which case app.py "
            "appends no Route at all. An unconfigured deployment must have an "
            "ABSENT path rather than a path that refuses: a 403 still answers "
            "'does ISAAC speak MCP here?' for a scanner."
        ),
        evidence=(
            "app.py:68-89 (_mcp_is_requested)",
            "app.py:313 (the mount gate)",
            "app.py:356-366 (the Route is appended only when the transport exists)",
            "transport.py:722 (serves_transport, read through getattr, default False)",
            "deployment.py:592 (resolve_binding fails closed five ways)",
        ),
    ),
    DecisionRow(
        outcome=OUTCOME_METHOD_NOT_ALLOWED,
        status=405,
        condition=(
            "The route exists, the entry guards passed, and the request is not a "
            "POST. Answered with 'Allow: POST'."
        ),
        why=(
            "This server opens no server-initiated stream, so GET subscribes to "
            "nothing, and it issues no Mcp-Session-Id, so DELETE has no session "
            "to delete. A 405 here is therefore the single most useful signal an "
            "operator has that the route IS mounted: nothing else distinguishes "
            "'mounted' from 'absent' without sending a credential."
        ),
        evidence=(
            "transport.py:388 (405, allow='POST')",
            "transport.py:26-35 (why GET and DELETE are refusals, not omissions)",
        ),
    ),
    DecisionRow(
        outcome=OUTCOME_ENTRY_GUARD_REFUSED,
        status=403,
        condition=(
            "The route exists and the binding's entry guards refused: the socket "
            "peer is not loopback, or a proxy header is present, or the browser "
            "Origin is outside loopback. Checked BEFORE the verb and before the "
            "body is read."
        ),
        why=(
            "The local-loopback binding serves loopback callers only, decided on "
            "the connection's own peer address and never on a header. The order "
            "is load-bearing and was wrong once: with the method check first, a "
            "caller from off loopback got '405 Allow: POST', which names this as "
            "an MCP endpoint to a scanner that never sent a POST."
        ),
        evidence=(
            "transport.py:349 (403 for every entry-guard refusal)",
            "transport.py:504-547 (_entry_refusal: the three guards, in order)",
            "transport.py:321-328 (why the order is before the method check)",
            "deployment.py:527-534 (local-loopback declares all four True)",
        ),
    ),
    DecisionRow(
        outcome=OUTCOME_CREDENTIAL_REQUIRED,
        status=401,
        condition=(
            "The route exists, the envelope is acceptable, and the binding "
            "requires a credential this request did not supply — or supplied one "
            "that did not verify. Includes the audience mismatch above."
        ),
        why=(
            "The OAuth binding has no anonymous branch: every path out of "
            "authenticate either returns a principal built from a token that "
            "verified, or raises. The refusal becomes a JSON-RPC envelope with "
            "code -31001, which the transport maps to 401 — the status an MCP "
            "client branches on to start an authorization flow. A challenge is "
            "attached only when the binding actually has an authorization server; "
            "neither shipped default fabricates one."
        ),
        evidence=(
            "oauth.py:1035-1041 (token_absent, and no anonymous branch)",
            "server.py:563-566 (_refusal_envelope -> DEPLOYMENT_UNCONFIGURED)",
            "server.py:258 (DEPLOYMENT_UNCONFIGURED = -31001)",
            "transport.py:595-596 (that code maps to 401)",
            "jwt.py:611-613 (the exact audience comparison a token can fail here)",
        ),
    ),
)


#: Documented, NOT modelled. An operator debugging will meet these, and they are
#: kept in a separate tuple so that "the table has four rows" stays a meaningful
#: assertion and so no reader mistakes a documented status for one
#: :func:`transport_outcome` will return.
ADJACENT_OUTCOMES: tuple[DecisionRow, ...] = (
    DecisionRow(
        outcome="token_in_query_string",
        status=400,
        condition="Any request carrying access_token, bearer_token, token or apikey in the query string.",
        why=(
            "Refused rather than served without it. This is ISAAC's own choice "
            "and not a conformance requirement: the MUST NOT is an obligation on "
            "the CLIENT, and OAuth 2.1 5.1 defines no query-parameter method for "
            "a resource server to have an opinion about. The parameter's VALUE is "
            "never read, so the refusal cannot itself log a credential."
        ),
        evidence=(
            "transport.py:392-410 (the 400)",
            "transport.py:181-206 (QUERY_TOKEN_PARAMETERS, and whose obligation it is)",
        ),
        modelled=False,
    ),
    DecisionRow(
        outcome="insufficient_scope",
        status=403,
        condition="The token verified and does not carry the ISAAC scope the tool needs.",
        why=(
            "A token that maps to no ISAAC scope authenticates successfully and "
            "authorizes nothing. This is a BODY-ladder outcome and is not "
            "modelled here; server.py decides it."
        ),
        evidence=(
            "transport.py:597-598 (INSUFFICIENT_SCOPE -> 403)",
            "oauth.py:1093-1112 (_granted: unrecognised token scopes are dropped)",
        ),
        modelled=False,
    ),
    DecisionRow(
        outcome="credential_not_verifiable",
        status=401,
        condition=(
            "A request to the local-loopback binding that carries an "
            "Authorization header at all — whatever is in it."
        ),
        why=(
            "That binding refuses a credential rather than accepting one, "
            "because accepting a token it cannot validate would let somebody "
            "point a real client at it and believe an authentication happened. "
            "THE OPERATOR TRAP: when ISAAC_UI_API_KEY is set, the application's "
            "own middleware demands that key in Authorization, the transport "
            "hands whatever is there to the binding, and the binding refuses it. "
            "The combination does not work and fails in the safe direction. "
            "Not modelled here because deciding it means handing a binding a "
            "credential, and this module accepts none."
        ),
        evidence=(
            "deployment.py:536-551 (credential_not_verifiable)",
            "transport.py:71-81 (the ISAAC_UI_API_KEY collision, and why it is safe)",
        ),
        modelled=False,
    ),
    DecisionRow(
        outcome="method_not_found",
        status=404,
        condition="A modern-era JSON-RPC request naming an RPC method this server does not implement.",
        why=(
            "A 404 that means something entirely different from the unmounted "
            "404 above, and the pair is the reason this row is written down: one "
            "comes from the router with no ISAAC code running, the other carries "
            "a JSON-RPC error body with code -32601. Distinguish them by the "
            "body, never by the status."
        ),
        evidence=("transport.py:599-608 (METHOD_NOT_FOUND, modern era only)",),
        modelled=False,
    ),
)


# --------------------------------------------------------------------------
# 2. Which binding did the operator ask for?
# --------------------------------------------------------------------------

CLASSIFICATION_UNSET = "unset"
CLASSIFICATION_UNRECOGNISED = "unrecognised"
CLASSIFICATION_RESERVED = "reserved_pending_decision"
CLASSIFICATION_LOCAL_LOOPBACK = "local_loopback"
CLASSIFICATION_OAUTH_RESOURCE_SERVER = "oauth_resource_server"

#: The binding names this build documents. Reporting is restricted to these — see
#: the module docstring on the one echoed value.
_REPORTABLE_NAMES: frozenset[str] = frozenset(
    {UNCONFIGURED, LOCAL_LOOPBACK, OAUTH_RESOURCE_SERVER, *RESERVED_BINDING_NAMES}
)


@dataclass(frozen=True)
class BindingSelection:
    """What ``ISAAC_MCP_DEPLOYMENT`` asked for, decided without resolving anything."""

    #: The supplied value, but only if it is a documented binding name. ``""``
    #: for anything else, including a typo. ``None`` when the variable is unset.
    supplied_reportable: str | None
    #: Whether MCP was asked for at all. This is exactly ``app.py``'s condition.
    requested: bool
    classification: str
    #: ``True``/``False`` when the name alone settles it; ``None`` for
    #: ``oauth-resource-server``, whose answer needs a resolution that reads a
    #: file. Unknown is reported as unknown rather than guessed either way.
    mounts_transport: bool | None
    why: str

    def as_dict(self) -> dict:
        return {
            "supplied_reportable": self.supplied_reportable,
            "requested": self.requested,
            "classification": self.classification,
            "mounts_transport": self.mounts_transport,
            "why": self.why,
        }


def binding_selection(env: Mapping[str, str]) -> BindingSelection:
    """Classify ``ISAAC_MCP_DEPLOYMENT`` without resolving a binding.

    Mirrors ``deployment.resolve_binding``'s branch order exactly — unset,
    reserved, oauth, not-local-loopback, local-loopback — because a preflight
    that reported a different classification from the resolver would be worse
    than none. The one thing it does not do is resolve, and the module docstring
    gives the reason.
    """
    raw = (env.get(DEPLOYMENT_ENV) or "").strip()
    reportable = raw if raw in _REPORTABLE_NAMES else ""

    if not raw:
        return BindingSelection(
            supplied_reportable=None,
            requested=False,
            classification=CLASSIFICATION_UNSET,
            mounts_transport=False,
            why=(
                f"{DEPLOYMENT_ENV} is unset or empty, so this application does "
                "not import the MCP package and registers no route. This is the "
                "state of every shipped deployment."
            ),
        )
    if raw in RESERVED_BINDING_NAMES:
        return BindingSelection(
            supplied_reportable=reportable,
            requested=True,
            classification=CLASSIFICATION_RESERVED,
            mounts_transport=False,
            why=(
                "This name is HELD for a decision and is deliberately not "
                "registered. It resolves to the unconfigured binding, which "
                "serves no transport. A placeholder that served traffic would be "
                "the decision."
            ),
        )
    if raw == OAUTH_RESOURCE_SERVER:
        return BindingSelection(
            supplied_reportable=reportable,
            requested=True,
            classification=CLASSIFICATION_OAUTH_RESOURCE_SERVER,
            mounts_transport=None,
            why=(
                "Whether this mounts depends on a complete, valid configuration "
                "— an issuer, a canonical resource URI and a verification key "
                "set. Deciding it requires a resolution that probes the key set "
                "on the filesystem, which this preflight does not do. Resolve the "
                "binding and pass it to transport_outcome for a definite answer."
            ),
        )
    if raw != LOCAL_LOOPBACK:
        return BindingSelection(
            supplied_reportable=reportable,
            requested=True,
            classification=CLASSIFICATION_UNRECOGNISED,
            mounts_transport=False,
            why=(
                f"{DEPLOYMENT_ENV} names no binding this build has. Resolution "
                "fails closed to the unconfigured binding, which serves no "
                "transport — so a typo and a deliberate shutdown are the same "
                "observable state, and both give the unmounted 404."
            ),
        )
    return BindingSelection(
        supplied_reportable=reportable,
        requested=True,
        classification=CLASSIFICATION_LOCAL_LOOPBACK,
        mounts_transport=True,
        why=(
            "This binding serves a transport, and refuses every request whose "
            "socket peer is not a loopback address, every request carrying a "
            "proxy header, and every browser origin outside loopback. A "
            "misconfigured scope list in the scopes variable makes it resolve to "
            "the unconfigured binding instead, which this name-only check cannot "
            "see — pass the resolved binding for certainty."
        ),
    )


def configuration_variables() -> tuple[str, ...]:
    """Every environment variable this feature reads, deployment-first.

    The OAuth names are imported here rather than at module scope for the same
    reason ``deployment.resolve_binding`` imports lazily: ``oauth.py`` reaches
    ``..identity``, which reaches Starlette, and a preflight should be importable
    from a context that has neither.
    """
    from .oauth import OAUTH_ENV_VARS

    return (DEPLOYMENT_ENV, LOCAL_SCOPES_ENV, LOCAL_SESSION_ENV, *OAUTH_ENV_VARS)


def configuration_presence(env: Mapping[str, str]) -> dict[str, bool]:
    """Which of those variables carry a non-empty value. **Presence only.**

    No value is read into the result, and that is not caution for its own sake:
    the fixture-JWKS variable holds a whole key document, and a diagnostic that
    copied it around would be a second place that document lives.
    """
    return {name: bool((env.get(name) or "").strip()) for name in configuration_variables()}


# --------------------------------------------------------------------------
# 3. What will this request get?
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TransportOutcome:
    """The decision-table row a described request lands on."""

    outcome: str
    status: int
    #: The refusal's own ``data.code``, when the source gives one; ``None`` for
    #: the unmounted case, where no ISAAC code runs at all.
    code: str | None
    why: str
    #: ``/api/mcp`` when a route exists, else ``None``. Not prefixed with the
    #: deployment base path, which this module is not given.
    path: str | None

    def as_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "status": self.status,
            "code": self.code,
            "why": self.why,
            "path": self.path,
        }


def transport_outcome(
    binding: DeploymentBinding | None,
    *,
    method: str = "POST",
    peer: str | None = None,
    origin: str | None = None,
    proxy_header_present: bool = False,
) -> TransportOutcome:
    """Which of the four outcomes a request against ``binding`` produces.

    ``binding`` is ``None`` when the caller has not resolved one, or has resolved
    one and wants to describe the deployment as the operator left it. Every
    binding attribute is read through ``getattr`` with the **safe** default,
    exactly as ``transport.py`` reads them, so a binding that forgets to declare
    a guard is modelled as having it.

    **The request modelled is one carrying NO credential**, and there is no
    parameter to say otherwise. An earlier version took ``credential_present``
    and, when it was true, fell through to ``served`` — which is **wrong for
    ``local-loopback``**, a binding that answers ``401
    credential_not_verifiable`` for *any* Authorization header. Deciding that
    case means handing a binding a credential, and this module accepts none, so
    it is documented in :data:`ADJACENT_OUTCOMES` instead of being approximated.

    The credential row is not modelled either: ``binding.authenticate(None)`` is
    called, which is the real decision on the real object. Only
    :class:`~.deployment.DeploymentRefused` is caught — anything else propagates,
    because a preflight that swallowed an exception would report a working
    deployment.
    """
    if binding is None or not getattr(binding, "serves_transport", False):
        row = _row(OUTCOME_UNMOUNTED)
        return TransportOutcome(
            outcome=row.outcome,
            status=row.status,
            code=None,
            why=row.why,
            path=None,
        )

    guard = _entry_guard_refusal(
        binding,
        peer=peer,
        origin=origin,
        proxy_header_present=proxy_header_present,
    )
    if guard is not None:
        row = _row(OUTCOME_ENTRY_GUARD_REFUSED)
        code, why = guard
        return TransportOutcome(
            outcome=row.outcome, status=row.status, code=code, why=why, path=MCP_PATH
        )

    if (method or "").upper() != "POST":
        row = _row(OUTCOME_METHOD_NOT_ALLOWED)
        return TransportOutcome(
            outcome=row.outcome,
            status=row.status,
            code="method_not_allowed",
            why=row.why,
            path=MCP_PATH,
        )

    try:
        binding.authenticate(None)
    except DeploymentRefused as refusal:
        row = _row(OUTCOME_CREDENTIAL_REQUIRED)
        return TransportOutcome(
            outcome=row.outcome,
            status=row.status,
            code=refusal.code,
            why=row.why,
            path=MCP_PATH,
        )

    return TransportOutcome(
        outcome=OUTCOME_SERVED,
        status=200,
        code=None,
        why=(
            "Nothing in the HTTP envelope refuses this request. What it receives "
            "is decided by the JSON-RPC body — protocol era, method, arguments "
            "and scope — which this preflight deliberately does not model."
        ),
        path=MCP_PATH,
    )


def _row(outcome: str) -> DecisionRow:
    for row in DECISION_TABLE:
        if row.outcome == outcome:
            return row
    raise KeyError(outcome)  # pragma: no cover - the constants are the only keys


def _entry_guard_refusal(
    binding: DeploymentBinding,
    *,
    peer: str | None,
    origin: str | None,
    proxy_header_present: bool,
) -> tuple[str, str] | None:
    """``(code, why)`` for the first guard that refuses, in ``transport.py``'s order."""
    if getattr(binding, "requires_loopback_peer", True) and not is_loopback_host(peer):
        return (
            "loopback_only",
            "This binding serves loopback callers only and this peer is not one. "
            "The check is made against the connection's own peer address, never "
            "against a header — so a forwarded address cannot satisfy it, and a "
            "request ASGI reports no peer for is refused too.",
        )
    if getattr(binding, "refuses_proxy_headers", True) and proxy_header_present:
        return (
            "proxied_request_refused",
            "A proxy header is present, so a loopback peer is a relay rather "
            "than the caller. The header's value is not read; its presence alone "
            "is the refusal. The headers whose presence counts are: "
            + ", ".join(name.decode("ascii") for name in PROXY_HEADERS)
            + ".",
        )
    if (
        getattr(binding, "requires_loopback_origin", True)
        and origin is not None
        and not _origin_is_loopback(origin)
    ):
        return (
            "cross_origin_refused",
            "A browser origin outside loopback may not call this endpoint: any "
            "page can post to 127.0.0.1, so the peer check alone is not a "
            "defence against DNS rebinding. An Origin of 'null' — what a "
            "sandboxed iframe or a file:// document sends — is refused rather "
            "than treated as absent.",
        )
    return None


# --------------------------------------------------------------------------
# 4. The audience comparison
# --------------------------------------------------------------------------

#: ISAAC accepts the token.
VERDICT_ACCEPTED = "accepted"
#: At least one audience value differs from the configured resource ONLY by a
#: standard URI normalisation. **This is the RFC 8707 mapping trap**: the
#: authorization server may be behaving correctly and ISAAC will still refuse
#: every call.
VERDICT_EXACT_STRING_MISMATCH = "exact_string_mismatch"
#: No audience value is within any known normalisation of the configured
#: resource. The token was minted for something else.
VERDICT_DIFFERENT_RESOURCE = "different_resource"
#: The ``aud`` claim is absent, or is not a string / list-of-strings. A single
#: non-string member voids the WHOLE claim — see ``jwt._audiences``.
VERDICT_NO_USABLE_AUDIENCE = "no_usable_audience_claim"

NORM_SURROUNDING_WHITESPACE = "surrounding_whitespace"
NORM_PERCENT_ENCODING = "percent_encoding"
NORM_SCHEME_AND_HOST_CASE = "scheme_and_host_case"
NORM_DEFAULT_PORT = "default_port"
NORM_TRAILING_SLASH = "trailing_slash"

#: Applied in this order when a subset is tried, so the search is deterministic.
#: Each is a normalisation RFC 3986 §6.2.2-§6.2.3 calls syntax- or
#: scheme-based — i.e. one an authorization server may legitimately apply while
#: believing it has echoed the resource back.
NORMALISATIONS: tuple[str, ...] = (
    NORM_SURROUNDING_WHITESPACE,
    NORM_PERCENT_ENCODING,
    NORM_SCHEME_AND_HOST_CASE,
    NORM_DEFAULT_PORT,
    NORM_TRAILING_SLASH,
)

_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
_DEFAULT_PORTS = {"https": "443", "http": "80"}


def _norm_surrounding_whitespace(value: str) -> str:
    return value.strip()


def _norm_percent_encoding(value: str) -> str:
    """Decode unreserved percent-triplets; upper-case the hex of the rest.

    RFC 3986 §6.2.2.2 and §6.2.2.1: both are normalisations that preserve
    meaning, which is exactly why an authorization server may apply them.
    """
    out: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        char = value[index]
        if char != "%" or index + 2 >= length:
            out.append(char)
            index += 1
            continue
        triplet = value[index + 1 : index + 3]
        try:
            code = int(triplet, 16)
        except ValueError:
            out.append(char)
            index += 1
            continue
        decoded = chr(code)
        if decoded in _UNRESERVED:
            out.append(decoded)
        else:
            out.append("%" + triplet.upper())
        index += 3
    return "".join(out)


def _norm_scheme_and_host_case(value: str) -> str:
    """Lower-case the scheme and the host. **Never the path** — RFC 3986 §6.2.2.1
    makes scheme and host case-insensitive and leaves everything else significant,
    and lowering a path would make this function report equivalences that are not
    ones."""
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value
    netloc = parts.netloc
    at = netloc.rfind("@")
    userinfo, hostport = (netloc[: at + 1], netloc[at + 1 :]) if at >= 0 else ("", netloc)
    if hostport.startswith("["):
        close = hostport.find("]")
        host, rest = (hostport[: close + 1], hostport[close + 1 :]) if close >= 0 else (hostport, "")
    else:
        colon = hostport.rfind(":")
        host, rest = (hostport[:colon], hostport[colon:]) if colon >= 0 else (hostport, "")
    return urlunsplit(
        (
            parts.scheme.lower(),
            userinfo + host.lower() + rest,
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


def _norm_default_port(value: str) -> str:
    """Drop an explicitly-written default port. RFC 3986 §6.2.3."""
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    default = _DEFAULT_PORTS.get(scheme)
    if default is None or not parts.netloc:
        return value
    suffix = ":" + default
    if not parts.netloc.endswith(suffix):
        return value
    return urlunsplit(
        (parts.scheme, parts.netloc[: -len(suffix)], parts.path, parts.query, parts.fragment)
    )


def _norm_trailing_slash(value: str) -> str:
    """Drop one trailing ``/``.

    NOT an RFC 3986 equivalence — ``https://h/mcp`` and ``https://h/mcp/`` are
    different resources — and included anyway, because it is the single most
    common way a deployment's configured resource and its issued audience
    disagree, and an operator needs to be told about it rather than protected
    from knowing. The report names the normalisation, so nobody reads it as a
    claim that the two URIs are the same.
    """
    return value[:-1] if value.endswith("/") else value


_NORMALISERS = {
    NORM_SURROUNDING_WHITESPACE: _norm_surrounding_whitespace,
    NORM_PERCENT_ENCODING: _norm_percent_encoding,
    NORM_SCHEME_AND_HOST_CASE: _norm_scheme_and_host_case,
    NORM_DEFAULT_PORT: _norm_default_port,
    NORM_TRAILING_SLASH: _norm_trailing_slash,
}


def _apply(value: str, steps: Sequence[str]) -> str:
    for name in NORMALISATIONS:
        if name in steps:
            value = _NORMALISERS[name](value)
    return value


def _minimal_equivalence(left: str, right: str) -> tuple[str, ...] | None:
    """The fewest normalisations under which ``left`` and ``right`` are equal.

    ``()`` when they are already byte-equal; ``None`` when no subset of
    :data:`NORMALISATIONS` makes them equal. Ties are broken by
    :data:`NORMALISATIONS` order, so the answer is deterministic.
    """
    if left == right:
        return ()
    for size in range(1, len(NORMALISATIONS) + 1):
        for steps in combinations(NORMALISATIONS, size):
            if _apply(left, steps) == _apply(right, steps):
                return steps
    return None


def _first_divergence(left: str, right: str) -> int | None:
    """The index of the first differing character, or of the end of the shorter
    string when one is a prefix of the other. ``None`` when equal."""
    if left == right:
        return None
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right))


@dataclass(frozen=True)
class AudienceCandidate:
    """One member of the token's ``aud`` claim, compared and never echoed.

    Carries a length, an index and a classification. It carries **no character
    of either string** — the module docstring gives the reasoning and records
    that there is deliberately no option to change it.
    """

    index: int
    length: int
    accepted: bool
    #: ``None`` when this candidate is byte-equal to the configured resource.
    first_divergence_index: int | None
    #: ``()`` byte-equal · non-empty tuple = equal only after these
    #: normalisations, i.e. the RFC 8707 mapping trap · ``None`` = unrelated.
    equivalent_under: tuple[str, ...] | None

    @property
    def classification(self) -> str:
        if self.equivalent_under == ():
            return "exact"
        if self.equivalent_under is None:
            return "unrelated"
        return "normalisation_only"

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "length": self.length,
            "accepted": self.accepted,
            "first_divergence_index": self.first_divergence_index,
            "equivalent_under": self.equivalent_under,
            "classification": self.classification,
        }


@dataclass(frozen=True)
class AudienceComparison:
    """Will ISAAC accept this token's audience, and if not, in what sense not."""

    accepted: bool
    verdict: str
    #: ``True`` when the ``aud`` claim had a usable shape at all. ``jwt._audiences``
    #: is the authority and is called directly rather than re-implemented.
    claim_usable: bool
    configured_length: int
    candidates: tuple[AudienceCandidate, ...] = field(default=())
    #: ``True`` when at least one candidate is equal to the configured resource
    #: under a non-empty set of standard normalisations. **The finding.**
    mapping_suspected: bool = False
    explanation: str = ""

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "verdict": self.verdict,
            "claim_usable": self.claim_usable,
            "configured_length": self.configured_length,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "mapping_suspected": self.mapping_suspected,
            "explanation": self.explanation,
        }


_MAPPING_EXPLANATION = (
    "EXACT-STRING MISMATCH, and the token may be perfectly valid. At least one "
    "audience value is equal to the configured resource once standard URI "
    "normalisations are applied, which means the authorization server may have "
    "MAPPED the requested resource onto its own canonical form — something RFC "
    "8707 permits it to do. ISAAC compares byte-for-byte and refuses. Both ends "
    "look correctly configured and every call fails. Fix it by making the two "
    "strings identical: either configure ISAAC's resource to the exact value the "
    "server puts in aud, or stop the server rewriting it. Do NOT 'fix' it by "
    "teaching ISAAC to normalise — a resource server that normalises accepts "
    "tokens minted for a different string."
)


def audience_comparison(configured_resource: str, token_audiences: Any) -> AudienceComparison:
    """Whether ISAAC's exact audience check will accept ``token_audiences``.

    ``configured_resource`` is the value ISAAC compares against — the
    ``OAuthResourceServerConfig.resource``, which is the configured URI with
    surrounding whitespace stripped and **nothing else changed**
    (``oauth._canonical_uri`` refuses rather than normalises).

    ``token_audiences`` is the raw ``aud`` claim in whatever shape it arrived:
    a string, a list of strings, or something else. It is passed to
    ``jwt._audiences`` rather than interpreted here, so the rule that one
    non-string member voids the whole claim cannot drift between the two.

    Neither argument appears anywhere in the return value.
    """
    resource = (configured_resource or "").strip()
    audiences = _audiences(token_audiences)

    if not audiences:
        return AudienceComparison(
            accepted=False,
            verdict=VERDICT_NO_USABLE_AUDIENCE,
            claim_usable=False,
            configured_length=len(resource),
            explanation=(
                "The aud claim is absent, empty, or not a string or list of "
                "strings. A single non-string member makes the WHOLE claim "
                "unusable rather than being filtered out, because filtering "
                "would let a wrong value plus a number read as a clean list."
            ),
        )

    candidates: list[AudienceCandidate] = []
    for index, value in enumerate(audiences):
        equivalence = _minimal_equivalence(resource, value)
        candidates.append(
            AudienceCandidate(
                index=index,
                length=len(value),
                accepted=value == resource,
                first_divergence_index=_first_divergence(resource, value),
                equivalent_under=equivalence,
            )
        )

    accepted = any(candidate.accepted for candidate in candidates)
    mapping_suspected = any(
        candidate.classification == "normalisation_only" for candidate in candidates
    )

    if accepted:
        verdict = VERDICT_ACCEPTED
        explanation = (
            "One audience value is byte-identical to the configured resource, "
            "which is what ISAAC's check requires. Nothing about the audience "
            "will refuse this token."
        )
    elif mapping_suspected:
        verdict = VERDICT_EXACT_STRING_MISMATCH
        explanation = _MAPPING_EXPLANATION
    else:
        verdict = VERDICT_DIFFERENT_RESOURCE
        explanation = (
            "No audience value is within any normalisation of the configured "
            "resource, so this token was minted for something else. ISAAC will "
            "refuse it with audience_mismatch, and that is the correct outcome: "
            "a resource server accepting a token issued for another audience is "
            "the confused-deputy problem RFC 8707 exists to close."
        )

    return AudienceComparison(
        accepted=accepted,
        verdict=verdict,
        claim_usable=True,
        configured_length=len(resource),
        candidates=tuple(candidates),
        mapping_suspected=mapping_suspected,
        explanation=explanation,
    )


# --------------------------------------------------------------------------
# 5. The composed report
# --------------------------------------------------------------------------

#: This module makes no network call, reads no file, and observes no deployment.
#: The status table is derived from source, and it is stated in the report itself
#: so a reader cannot mistake it for an observation.
PROVENANCE = (
    "Derived from this build's source at import time. No deployment was "
    "contacted, no endpoint was called, no credential was used and no file was "
    "read. Applying this to a hosted environment is an operator's act and is "
    "separately authorized; nothing here performs one."
)


def preflight_report(
    env: Mapping[str, str],
    *,
    binding: DeploymentBinding | None = None,
    method: str = "POST",
    peer: str | None = None,
    origin: str | None = None,
    proxy_header_present: bool = False,
    configured_resource: str | None = None,
    token_audiences: Any = None,
) -> dict:
    """One diagnostic object: selection, configuration presence, outcome, audience.

    Every top-level key is always present, so a caller branches on values rather
    than on membership. ``audience`` is ``None`` when no
    ``configured_resource`` was supplied — a missing comparison is reported as
    missing and never as a pass.
    """
    selection = binding_selection(env)
    outcome = transport_outcome(
        binding,
        method=method,
        peer=peer,
        origin=origin,
        proxy_header_present=proxy_header_present,
    )
    audience = (
        audience_comparison(configured_resource, token_audiences)
        if configured_resource is not None
        else None
    )
    return {
        "provenance": PROVENANCE,
        "selection": selection.as_dict(),
        "configuration_present": configuration_presence(env),
        "outcome": outcome.as_dict(),
        "audience": audience.as_dict() if audience is not None else None,
        "decision_table": [
            {
                "outcome": row.outcome,
                "status": row.status,
                "condition": row.condition,
                "why": row.why,
                "evidence": list(row.evidence),
                "modelled": row.modelled,
            }
            for row in (*DECISION_TABLE, *ADJACENT_OUTCOMES)
        ],
    }
