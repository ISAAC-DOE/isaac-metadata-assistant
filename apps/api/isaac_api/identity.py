"""The application-side identity/trust abstraction. TYPES AND A REFUSAL — no reader.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
=============================================
This module answers one question — *"is there a person this request may be
attributed to, and on whose word?"* — and in this build the answer is always
**no**. Nothing here reads a header. Nothing here is wired to a route. Nothing
here stamps anything.

It exists because the alternative is worse. ``docs/identity-trust-contract.md``
§8 reason 1 names the hazard precisely: *"a no-op abstraction invites a
non-no-op consumer … an ``identity.py`` exporting ``get_principal()`` is exactly
the affordance that lets a later slice write ``uploaded_by=principal.subject``
without reopening the trust question."* That warning is correct, and this file
is arranged so the consumer it warns about **cannot be written**, rather than
being merely discouraged from being written. See "THE UNWRITABLE PATH" below.

AUTHORIZATION, STATED PLAINLY BECAUSE IT CONTRADICTS A COMMITTED DECISION
========================================================================
``docs/identity-trust-contract.md`` §8 currently reads *"Decision: do not build
a live identity seam"*, restated 2026-08-12 as *"wire nothing until ISAAC can
distinguish an edge-traversed request from a direct in-cluster one, and refuses
to stamp on the latter."*

**This module is built on the project owner's explicit instruction, which
supersedes that decision.** §8 has NOT yet been amended, and a docs slice owes it
a recorded reversal — this comment is not that reversal, it is a pointer to the
gap. Read the two together, not either alone.

What is worth noticing is that §8's restated gate is the specification this file
implements rather than violates: the whole design is a machine for distinguishing
"the boundary vouched for this request" from "a header arrived", and for refusing
the second. The part §8 forbids — a live reader, a wired route, a stamp — is
absent.

THE FACT THAT GOVERNS EVERY LINE HERE
=====================================
From the infrastructure owner, 2026-08-12 (``docs/identity-trust-contract.md``
§2, Q4 — **operator testimony about configuration, not a measurement made by this
repository**):

    The Service is a plain ClusterIP with no NetworkPolicy. Any in-cluster pod
    can reach the application directly and can forge forwarded identity headers.

    **The presence of ``X-authentik-username`` — or of any other edge-injected
    header — does NOT prove that the request traversed the authenticated edge.**

So the edge's five injected headers are *authoritative on the edge path* and
*forgeable off it*, and the application cannot tell the two paths apart from the
headers alone. That is why a header is never an input to this module: knowing the
value tells you nothing about whether to believe it. Only something that can
witness the PATH — a verifier — can, and ISAAC has no such thing today.

THE UNWRITABLE PATH
===================
The unsafe line is ``if request.headers.get("x-authentik-username"): trust it``.
It is unwritable *through this module* because there is no function here that
accepts a header, a header mapping, or a value claiming to be a subject:

  * A :class:`HumanActor` can only be reached inside a :class:`RequestIdentity`,
    and the only function that builds one is :func:`resolve_request_identity`.
  * :func:`resolve_request_identity` takes an :class:`EdgeVerdict` — never a
    request, never a header, never a string.
  * The only verdict carrying claims is :class:`Traversed`, and it can only be
    constructed around an :class:`EdgeAssertion`, which refuses to exist without
    naming the verifier that produced it and the basis on which it is trusted.
  * The only :class:`EdgeAssertion` producer contemplated is an
    :class:`EdgeTrustVerifier`, and **the verifier is the sole header reader in
    the design**. The one verifier this build ships,
    :class:`UnconfiguredEdgeVerifier`, reads nothing at all.

A claim is therefore only readable *through the thing that vouches for it*. The
short way to say it: you cannot get a subject out of this module without first
producing something that says who checked, and today nothing checks.

Two mechanical guards back the argument up, because an argument in a docstring is
not a guarantee. ``apps/api/tests/test_identity_trust.py`` asserts (a) that the
substring ``x-authentik-`` appears in **no** module under
``apps/api/isaac_api/`` except this one, and (b) that this module performs **no
header access of any kind** — so the five names below are documentation, and no
code in the backend reads a header by them.

WHY THE HEADER NAMES ARE WRITTEN DOWN HERE AT ALL
=================================================
Same reason ``apps/web/src/lib/currentUserContract.ts`` writes them down: so the
recorded fact lives beside the types that depend on it, and so the permanent
disqualification can be DERIVED from the record rather than hand-listed twice.
:data:`EDGE_INJECTED_HEADERS` **is not an allowlist and nothing reads a header by
it.**

WHAT THIS MODULE MUST NEVER GROW INTO
=====================================
  * No stamping of ``attribution.uploaded_by``. The truth core refuses a
    draft-authored value for that field by design (commit ``bdff8f5``). Nothing
    here supplies one and nothing here may be routed there.
  * No RBAC engine. Groups are carried and exactly one predicate consumes them
    (:meth:`HumanActor.is_admin`) — see the note on that method.
  * No UID↔username mapping. Decided 2026-08-12: usernames are not reassigned,
    the username is canonical, and Q17 is not to be reopened.
  * No email. §9 disqualifies it as an identifier, and §6 records that email is
    personal data; an assertion that never carries it cannot leak it.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from starlette.requests import Request
from starlette.responses import JSONResponse

__all__ = [
    "EDGE_INJECTED_HEADERS",
    "EDGE_TRUST_VERIFIER_ENV",
    "HUMAN_ACTOR_REQUIRED_ERROR",
    "ISAAC_ADMIN_GROUP",
    "ISAAC_DEPLOYMENT_GROUPS",
    "PERMANENTLY_UNTRUSTED_HEADERS",
    "RECOGNISED_TRUST_BASES",
    "SUBJECT_KIND_AUTHENTIK_USERNAME",
    "TRUST_BASIS_TEST_FIXTURE",
    "TRUST_BASIS_VERIFIED_EDGE_ASSERTION",
    "UNCONFIGURED_VERIFIER",
    "EdgeAssertion",
    "EdgeTrustVerifier",
    "EdgeVerdict",
    "HumanActor",
    "HumanActorRequired",
    "IdentityRefusal",
    "NotTraversed",
    "RequestIdentity",
    "ServicePrincipal",
    "Traversed",
    "TrustTier",
    "Unconfigured",
    "UnconfiguredEdgeVerifier",
    "edge_trust_verifier",
    "human_actor_required_handler",
    "require_human_actor",
    "resolve_identity_for_request",
    "resolve_request_identity",
    "stamp_actor",
    "validate_edge_trust_verifier_or_raise",
]


# --------------------------------------------------------------------------
# The recorded observation. DOCUMENTATION, not configuration.
# --------------------------------------------------------------------------

#: The five headers the ``/krish`` edge injects/overwrites, per the
#: infrastructure owner's statement of 2026-08-12
#: (``docs/identity-trust-contract.md`` §6A.1). Lower-cased because HTTP header
#: names are case-insensitive and the mixed-case spellings in the document name
#: the same headers.
#:
#: **THIS IS NOT AN ALLOWLIST. NOTHING IN THIS REPOSITORY READS A HEADER BY IT**
#: — a test asserts that this module performs no header access at all. It is the
#: written-down form of the observation, kept beside the types that depend on it.
#:
#: Read the qualifications with the fact, always: this is operator testimony
#: about a manifest this repository cannot see, it is a statement about the EDGE
#: PATH ONLY (§2's in-cluster bypass never meets the edge, so nothing is
#: overwritten for it), it is point-in-time and can change with no signal here,
#: and it says nothing about headers outside these five (Q1 is only partially
#: answered).
EDGE_INJECTED_HEADERS: tuple[str, ...] = (
    "x-authentik-username",
    "x-authentik-groups",
    "x-authentik-email",
    "x-authentik-name",
    "x-authentik-uid",
)

#: The two headers disqualified **permanently** from authentication,
#: authorization, role assignment, proof that Authentik was traversed, and proof
#: that the caller is an institutional user — unless the infrastructure changes
#: and is independently re-verified (§6A.2, confirmed by the infrastructure owner
#: 2026-08-12: Q18 is closed in the "permanently untrusted" direction).
#:
#: ``x-isaac-edge`` is disqualified from *the one job its name implies*: it cannot
#: witness that a request came through the edge, because any client can set it.
#: A future verifier must not reach for it — that is the whole trap this pair
#: exists to mark.
PERMANENTLY_UNTRUSTED_HEADERS: tuple[str, ...] = (
    "x-authentik-entitlements",
    "x-isaac-edge",
)


# --------------------------------------------------------------------------
# Vocabulary. Mirrors apps/web/src/lib/currentUserContract.ts deliberately.
# --------------------------------------------------------------------------

#: The one subject kind this build recognises.
#:
#: The frontend contract carries two (``authentik_username`` and
#: ``authentik_uid``) because it was written while §6A.3 held the choice open.
#: **That is superseded**: on 2026-08-12 the infrastructure owner stated that
#: usernames are not reassigned, that the username is canonical, and that no
#: UID↔username mapping infrastructure should be introduced. One kind, not two,
#: is the whole content of that decision, and a second member here is how the
#: mapping would creep back in.
SUBJECT_KIND_AUTHENTIK_USERNAME = "authentik_username"

#: A subject minted by a test. The only basis this build can actually produce,
#: because the only shipped verifier never returns :class:`Traversed`.
TRUST_BASIS_TEST_FIXTURE = "test_fixture"

#: A subject vouched for by a verifier that observed the trusted boundary.
#: **Recognised but unproducible in this build** — no verifier mints it. It is
#: named so a future verifier has an honest label to use, and so the asymmetry is
#: visible: an actor built today must literally declare itself a fixture.
TRUST_BASIS_VERIFIED_EDGE_ASSERTION = "verified_edge_assertion"

#: Every basis a claim may cite. Validated on construction, so an actor cannot
#: exist without saying, in data, what vouched for it.
RECOGNISED_TRUST_BASES: frozenset[str] = frozenset(
    {TRUST_BASIS_TEST_FIXTURE, TRUST_BASIS_VERIFIED_EDGE_ASSERTION}
)

#: The two coarse **deployment-access** groups the edge admits
#: (``docs/identity-trust-contract.md`` §5.3, upstream ``portal/api.py:66-67``).
#: Recorded for the reader, NOT enforced: :class:`HumanActor` carries whatever
#: groups it is given, verbatim, including the ``bl152-*`` beamline groups that
#: **are not ISAAC roles**. Filtering them here would silently discard
#: information the deployment sent; the correct handling is to carry and not
#: consume.
ISAAC_DEPLOYMENT_GROUPS: frozenset[str] = frozenset({"admin", "researcher"})

#: The single group name any code in this module consumes. See
#: :meth:`HumanActor.is_admin`.
ISAAC_ADMIN_GROUP = "admin"


class TrustTier(str, Enum):
    """How much this request's identity is worth, on what evidence.

    Three tiers, and the gap between them is the point:

      * :attr:`UNTRUSTED` — no identity was established. Carries a
        :class:`IdentityRefusal` saying why. **This is every request in this
        build**, including one arriving with all five edge headers populated.
      * :attr:`SERVICE` — a non-human caller proved itself (a Bearer credential,
        in the pattern the infrastructure owner named: trusted-edge for browser
        traffic, independent Bearer validation for API traffic). It may
        *authorize* an operation. It may **never** be an attributable actor —
        see :class:`ServicePrincipal`.
      * :attr:`EDGE_HUMAN` — a person, established through a trusted boundary by
        a verifier that witnessed the boundary. The only tier
        :func:`stamp_actor` will attribute anything to.

    ``str`` mixin so the value serialises into a JSON body without a converter,
    matching how every other typed refusal in this app is built.
    """

    UNTRUSTED = "untrusted"
    SERVICE = "service"
    EDGE_HUMAN = "edge_human"


class IdentityRefusal(str, Enum):
    """Why no identity was established. Present on exactly the UNTRUSTED tier.

    Two members, and they are the two the closed :class:`EdgeVerdict` union can
    actually produce — one each. A refusal reason with no producer is a reason
    nobody can test, and this project has shipped enough unreachable states to
    have learned that.

    **There is deliberately no ``NO_SUBJECT_CLAIM``.** It would describe "the
    boundary was traversed but the assertion named nobody", and that state cannot
    arise: :class:`EdgeAssertion` refuses to exist without a non-empty subject, so
    a verifier facing an authenticated-but-subjectless request must return
    :class:`NotTraversed` rather than mint an empty claim. If a future verifier
    genuinely needs to distinguish the two, the honest change is a fourth verdict
    plus this member — not an :class:`EdgeAssertion` with an empty string in it.

    **There is deliberately no ``DISQUALIFIED_HEADER_ONLY``** (the frontend
    contract has one) because nothing here reads a header, so no code path can
    reach the state where the only claim on offer came from a disqualified one.
    """

    #: No trusted-boundary verifier is configured in this deployment, so nothing
    #: checked, so nobody is identified. The only reachable refusal today.
    NO_VERIFIER_CONFIGURED = "no_verifier_configured"

    #: A verifier ran and reported that this request did not come through the
    #: trusted boundary — the Q4 in-cluster-bypass case. Name taken verbatim from
    #: the frontend's ``CurrentUserUntrustedReason`` so the two vocabularies are
    #: one vocabulary.
    UNVERIFIED_EDGE_TRAVERSAL = "unverified_edge_traversal"


# --------------------------------------------------------------------------
# The principals
# --------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class HumanActor:
    """A person this request may be attributed to.

    Immutable, keyword-only, and validating: every field that could be wrong in a
    dangerous direction is checked at construction, because the alternative is a
    silently-empty subject reaching a persisted record.

    ``trust_basis`` is required and has no default **on purpose**. Constructing an
    actor forces the constructor to state what vouched for it, in data, and the
    only basis this build can produce is :data:`TRUST_BASIS_TEST_FIXTURE` — so
    production code that mints one has to declare it a fixture. Same device as the
    frontend's ``CurrentUserTrustBasis``, and same reason.
    """

    #: The canonical key: the Authentik username. Never rendered by this build.
    subject: str
    #: Which claim :attr:`subject` is. One recognised value; see the constant.
    subject_kind: str = SUBJECT_KIND_AUTHENTIK_USERNAME
    #: A human-readable name, or ``None``. **Display only, never a key** (§9,
    #: §9.1) — display names are not unique and are not stable.
    display_name: str | None = None
    #: Group names exactly as supplied, including any that are not ISAAC roles.
    groups: frozenset[str] = frozenset()
    #: What vouched for this actor. See :data:`RECOGNISED_TRUST_BASES`.
    trust_basis: str

    def __post_init__(self) -> None:
        if not self.subject or not self.subject.strip():
            # An empty subject is the failure that matters: it would stamp a
            # record with "" and look, downstream, exactly like an attributed one.
            raise ValueError("HumanActor.subject must be a non-empty identifier")
        if self.subject_kind != SUBJECT_KIND_AUTHENTIK_USERNAME:
            raise ValueError(
                f"HumanActor.subject_kind must be "
                f"{SUBJECT_KIND_AUTHENTIK_USERNAME!r}; got {self.subject_kind!r}"
            )
        if self.trust_basis not in RECOGNISED_TRUST_BASES:
            raise ValueError(
                f"HumanActor.trust_basis {self.trust_basis!r} is not one of "
                f"{sorted(RECOGNISED_TRUST_BASES)}"
            )
        if not isinstance(self.groups, frozenset):
            # A mutable set here would let a caller mutate an actor's groups after
            # an authorization decision read them.
            raise TypeError("HumanActor.groups must be a frozenset")

    def is_admin(self) -> bool:
        """The ONE predicate in this module that consumes a group.

        This is not an RBAC engine and must not become one. It answers a single
        yes/no about a single group name, and everything else about
        :attr:`groups` is carried and ignored.

        **What a ``True`` here means is narrower than it reads.** ``admin`` is a
        coarse *deployment-access* group — "may this person use the deployment at
        all" — not a research role and not a collaboration set
        (``docs/identity-trust-contract.md`` §5.3). Every authenticated user of
        the deployment is in one of exactly two such buckets, so keying anything
        collaborative to the other one (``researcher``) would share every
        experiment with every researcher. Do not read this predicate as
        "privileged"; read it as "in the admin admission group".

        And it is only as good as :attr:`trust_basis`: on a
        :data:`TRUST_BASIS_TEST_FIXTURE` actor this answers a question about a
        fixture.
        """
        return ISAAC_ADMIN_GROUP in self.groups


@dataclass(frozen=True, kw_only=True)
class ServicePrincipal:
    """A non-human caller that proved itself. **Never an attributable actor.**

    The distinction is the reason this class exists rather than a boolean on
    :class:`HumanActor`. A service credential can legitimately authorize an
    operation — that is the "independent Bearer validation for API/service
    traffic" half of the pattern the infrastructure owner named. It cannot be
    *attributed* an effect, because a shared credential names no person, and a
    record stamped with a service name asserts an authorship that did not happen.

    So the class deliberately has **no** ``subject``, no ``display_name`` and no
    ``groups``: there is no field on it that a stamping call site could reach for
    by mistake, and :func:`stamp_actor` reads only :attr:`RequestIdentity.human`,
    which is ``None`` on this tier. Attributability is designed out, not
    documented away.

    Nothing in this build produces one; no service verifier exists. It is defined
    so that when one is built, the tier already refuses to be an author.
    """

    #: An opaque name for the calling service. Not a person and not a username.
    principal_id: str
    #: What vouched for it. Same discipline as :attr:`HumanActor.trust_basis`.
    trust_basis: str

    def __post_init__(self) -> None:
        if not self.principal_id or not self.principal_id.strip():
            raise ValueError("ServicePrincipal.principal_id must be non-empty")
        if self.trust_basis not in RECOGNISED_TRUST_BASES:
            raise ValueError(
                f"ServicePrincipal.trust_basis {self.trust_basis!r} is not one of "
                f"{sorted(RECOGNISED_TRUST_BASES)}"
            )


@dataclass(frozen=True, kw_only=True)
class RequestIdentity:
    """The settled answer for one request. Exactly one tier, and it is consistent.

    The invariant enforced in :meth:`__post_init__` is the whole value of the
    type: **``refusal`` is non-``None`` if and only if the tier is
    ``UNTRUSTED``**, and the principal fields agree with the tier. Without it the
    type permits ``trust=EDGE_HUMAN, human=None`` — a state that reads as
    "identified" to every ``if identity.trust is EDGE_HUMAN`` in the codebase
    while carrying nobody, which is the exact shape of an attribution bug.

    Construct through the three classmethods rather than the constructor; they
    are the only combinations the invariant permits, so naming them removes the
    chance to assemble an impossible one and discover it at runtime.
    """

    trust: TrustTier
    human: HumanActor | None = None
    service: ServicePrincipal | None = None
    refusal: IdentityRefusal | None = None

    def __post_init__(self) -> None:
        if self.trust is TrustTier.UNTRUSTED:
            if self.refusal is None:
                raise ValueError("an UNTRUSTED identity must carry a refusal reason")
            if self.human is not None or self.service is not None:
                raise ValueError("an UNTRUSTED identity carries no principal")
        else:
            if self.refusal is not None:
                raise ValueError("a trusted identity must not carry a refusal reason")
        if self.trust is TrustTier.EDGE_HUMAN:
            if self.human is None or self.service is not None:
                raise ValueError("an EDGE_HUMAN identity carries exactly a human")
        if self.trust is TrustTier.SERVICE:
            if self.service is None or self.human is not None:
                raise ValueError("a SERVICE identity carries exactly a service")

    @classmethod
    def untrusted(cls, refusal: IdentityRefusal) -> RequestIdentity:
        """Nobody was identified, and here is why."""
        return cls(trust=TrustTier.UNTRUSTED, refusal=refusal)

    @classmethod
    def for_human(cls, actor: HumanActor) -> RequestIdentity:
        """A person, vouched for. Reachable only from a :class:`Traversed` verdict."""
        return cls(trust=TrustTier.EDGE_HUMAN, human=actor)

    @classmethod
    def for_service(cls, principal: ServicePrincipal) -> RequestIdentity:
        """A service, vouched for. No producer in this build; see the class."""
        return cls(trust=TrustTier.SERVICE, service=principal)


# --------------------------------------------------------------------------
# The trusted boundary: an assertion, a closed verdict union, and a verifier
# --------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class EdgeAssertion:
    """What a verifier says it *observed* at the trusted boundary.

    This is the only object in the module that carries a claim about a person,
    and it is unreachable except inside a :class:`Traversed` verdict — which is
    what makes "a claim is only readable through the thing that vouches for it"
    a structural property rather than a convention.

    :attr:`verifier_id` is required for the same reason :attr:`trust_basis` is:
    an assertion that cannot name its own author is an assertion nobody can audit
    or revoke.

    **What it deliberately does NOT carry**, though the edge injects them:

      * **email** — §9 disqualifies it as an identifier and §6 records it as
        personal data. A structure that never holds it cannot log or persist it.
      * **uid** — decided 2026-08-12: the username is canonical and no UID↔username
        mapping is to be introduced. Carrying the uid "just in case" is how the
        mapping gets built by accident.
      * **entitlements / any edge marker** — :data:`PERMANENTLY_UNTRUSTED_HEADERS`.
        There is no field they could be put in.
    """

    subject: str
    subject_kind: str = SUBJECT_KIND_AUTHENTIK_USERNAME
    display_name: str | None = None
    groups: frozenset[str] = frozenset()
    #: Which verifier produced this, so a claim is always traceable to a checker.
    verifier_id: str
    #: What makes it believable. See :data:`RECOGNISED_TRUST_BASES`.
    trust_basis: str

    def __post_init__(self) -> None:
        if not self.subject or not self.subject.strip():
            # See IdentityRefusal: a verifier with no subject must return
            # NotTraversed. It must never mint an assertion naming nobody.
            raise ValueError("EdgeAssertion.subject must be a non-empty identifier")
        if not self.verifier_id or not self.verifier_id.strip():
            raise ValueError("EdgeAssertion.verifier_id must be non-empty")
        if self.subject_kind != SUBJECT_KIND_AUTHENTIK_USERNAME:
            raise ValueError(
                f"EdgeAssertion.subject_kind must be "
                f"{SUBJECT_KIND_AUTHENTIK_USERNAME!r}; got {self.subject_kind!r}"
            )
        if self.trust_basis not in RECOGNISED_TRUST_BASES:
            raise ValueError(
                f"EdgeAssertion.trust_basis {self.trust_basis!r} is not one of "
                f"{sorted(RECOGNISED_TRUST_BASES)}"
            )
        if not isinstance(self.groups, frozenset):
            raise TypeError("EdgeAssertion.groups must be a frozenset")


@dataclass(frozen=True, kw_only=True)
class Unconfigured:
    """No verifier is configured, so the boundary was not examined.

    Distinct from :class:`NotTraversed` for the same reason the frontend's
    ``disabled`` is distinct from ``absent``: collapsing them would let a surface
    say "this request did not come through the edge" when the truth is that this
    build never looked. One is a finding; the other is the absence of a finding.
    """

    verifier_id: str


@dataclass(frozen=True, kw_only=True)
class NotTraversed:
    """A verifier examined the request and did not find the trusted boundary.

    :attr:`detail` is a short, non-identifying explanation for a log. It must
    never carry a header value, a claim, or an address — a refusal that echoes the
    forged input is a refusal that logs the attacker's chosen string.
    """

    verifier_id: str
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class Traversed:
    """The request came through the trusted boundary, and here is what it said."""

    assertion: EdgeAssertion


#: The closed union. Exhaustively matched in :func:`resolve_request_identity`,
#: which raises on anything else rather than falling through to a default —
#: adding a member must be a deliberate, reviewed act, and the safe default is
#: one that is CHOSEN rather than inherited (the reasoning
#: ``currentUserContract.canPersonalize`` uses for its switch).
EdgeVerdict = Unconfigured | NotTraversed | Traversed


class EdgeTrustVerifier(Protocol):
    """The seam that decides whether the trusted boundary was traversed.

    **A verifier is the SOLE header reader in this design.** It is handed the
    request and is the only component permitted to look at it; everything
    downstream consumes the :class:`EdgeVerdict` it returns and can never see the
    request at all. That asymmetry is what keeps the parsing and the trusting in
    one reviewable place instead of spread across every route.

    Implementing one is a security change, not a plumbing change. A real verifier
    must answer §2's question — *did this request traverse the authenticated edge,
    or did it reach the ClusterIP directly?* — and no header can answer it: not
    ``x-isaac-edge``, which any client can set (§6A.2). It needs evidence the
    forger cannot produce, and designing that needs its own review and its own
    approval.
    """

    @property
    def verifier_id(self) -> str:
        """A stable name, echoed into every verdict so a claim names its checker."""

    def verify(self, request: object) -> EdgeVerdict:
        """Examine the request and return a verdict. May read headers."""


@dataclass(frozen=True)
class UnconfiguredEdgeVerifier:
    """The only verifier this build ships. Always :class:`Unconfigured`.

    It takes no configuration, holds no state, opens no connection, and — the
    property that matters — **never touches its argument**. ``request`` is typed
    ``object`` rather than ``Request`` to say so in the signature: nothing about a
    request is usable through that type, so a future edit that starts reading one
    has to widen the annotation first, which is a visible act.

    There is no switch to flip. A different answer requires a different class,
    written deliberately and reviewed as a security change.
    """

    verifier_id: str = "unconfigured"

    def verify(self, request: object) -> EdgeVerdict:  # noqa: ARG002 - see docstring
        return Unconfigured(verifier_id=self.verifier_id)


# --------------------------------------------------------------------------
# Verifier selection. Fail-closed. Mirrors runtime_mode.py exactly.
# --------------------------------------------------------------------------

EDGE_TRUST_VERIFIER_ENV = "ISAAC_EDGE_TRUST_VERIFIER"

#: The one recognised value. Named rather than implied so a misconfiguration can
#: be *detected*, which is the only reason the env var exists at all today.
UNCONFIGURED_VERIFIER = "unconfigured"

#: Value -> factory. One entry. A future verifier is added here, and adding it is
#: the moment the whole trust question reopens.
_VERIFIERS: dict[str, Callable[[], EdgeTrustVerifier]] = {
    UNCONFIGURED_VERIFIER: UnconfiguredEdgeVerifier,
}


def _raw_verifier_selection() -> str | None:
    """The raw env value, or ``None`` if the var is unset."""
    return os.environ.get(EDGE_TRUST_VERIFIER_ENV)


def edge_trust_verifier() -> EdgeTrustVerifier:
    """Resolve the configured verifier, fail-closed. **Never raises.**

    Unset, recognised, or garbage — every path that is not an explicit, valid
    selection of a real verifier yields :class:`UnconfiguredEdgeVerifier`, which
    identifies nobody. An accident must never grant identity, exactly as an
    accident must never grant ``real`` runtime mode.

    Detecting the misconfiguration is a different job, done once at boot by
    :func:`validate_edge_trust_verifier_or_raise`. Splitting resolution from
    validation is deliberate and copied from ``runtime_mode``: a request-time
    resolver that raises turns a manifest typo into a 500 on every route, whereas
    a boot-time validator turns it into a container that does not start.
    """
    raw = _raw_verifier_selection()
    if raw is None:
        return UnconfiguredEdgeVerifier()
    factory = _VERIFIERS.get(raw.strip())
    if factory is None:
        # Unrecognised (including empty/whitespace-only) fails closed.
        return UnconfiguredEdgeVerifier()
    return factory()


def validate_edge_trust_verifier_or_raise() -> None:
    """Raise ``RuntimeError`` for a misconfigured verifier selection; else return.

    Passes when :data:`EDGE_TRUST_VERIFIER_ENV` is unset or names a verifier this
    build actually has. Raises on anything else, including empty or
    whitespace-only.

    Called at the start of ``create_app()`` so a container configured to use a
    verifier that does not exist **fails to boot** rather than running degraded.
    The degraded run is the dangerous one and is worth naming: the operator who
    set the variable believes identity is being checked, the fail-closed resolver
    above quietly returns the unconfigured verifier, and the deployment then looks
    identical to a correctly-configured one while checking nothing. Failing to
    boot is louder than any log line.
    """
    raw = _raw_verifier_selection()
    if raw is None:
        return
    if raw.strip() in _VERIFIERS:
        return
    raise RuntimeError(
        f"{EDGE_TRUST_VERIFIER_ENV}={raw!r} is invalid. Expected one of "
        f"{sorted(_VERIFIERS)} (unset defaults to '{UNCONFIGURED_VERIFIER}')."
    )


# --------------------------------------------------------------------------
# Resolution. Takes a verdict. Never a request, never a header, never a string.
# --------------------------------------------------------------------------


def resolve_request_identity(verdict: EdgeVerdict) -> RequestIdentity:
    """Turn a verifier's verdict into the settled identity for a request.

    **This signature is the security property.** It accepts an
    :class:`EdgeVerdict` and nothing else — no request, no header mapping, no
    ``str`` that might be a username. There is consequently no way to call this
    function with an unverified claim, which is what makes ``if header exists:
    trust it`` unwritable rather than merely discouraged.

    The match is exhaustive over the closed union and raises on an unknown
    member. A ``case _: return untrusted(...)`` default would be *safer* per
    request and *worse* overall: a new verdict added without a rule here would be
    silently downgraded, and the tests for the new verdict would pass while it did
    nothing.
    """
    match verdict:
        case Traversed(assertion=assertion):
            return RequestIdentity.for_human(
                HumanActor(
                    subject=assertion.subject,
                    subject_kind=assertion.subject_kind,
                    display_name=assertion.display_name,
                    groups=assertion.groups,
                    # Carried, not re-derived: the actor's believability is the
                    # assertion's believability, and a second source for it here
                    # would be a second thing to keep in step.
                    trust_basis=assertion.trust_basis,
                )
            )
        case NotTraversed():
            return RequestIdentity.untrusted(IdentityRefusal.UNVERIFIED_EDGE_TRAVERSAL)
        case Unconfigured():
            return RequestIdentity.untrusted(IdentityRefusal.NO_VERIFIER_CONFIGURED)
        case _:
            raise TypeError(f"unhandled EdgeVerdict member: {type(verdict).__name__}")


def resolve_identity_for_request(request: Request) -> RequestIdentity:
    """The settled identity for one request. The **only** function here given one.

    It does exactly one thing with the request: hands it, unread, to the
    configured verifier. It performs no attribute access on it whatsoever — a test
    passes an object that raises on every attribute access and this still returns
    a value.

    **This is not ``get_principal()``**, the affordance
    ``docs/identity-trust-contract.md`` §8 reason 1 warns about, and the
    difference is not cosmetic. ``get_principal()`` returns a principal or
    ``None``, so a call site that forgets the ``None`` case stamps a value.
    This returns a :class:`RequestIdentity` whose ``human`` is ``None`` on every
    tier but one, whose tier is ``UNTRUSTED`` in this entire build, and which
    carries a reason it can be asked for. The caller has to look at the tier to
    get anything out of it.
    """
    return resolve_request_identity(edge_trust_verifier().verify(request))


# --------------------------------------------------------------------------
# The refusal, and the dependency factory that raises it
# --------------------------------------------------------------------------

#: The ``error`` code every refusal of this shape carries. One definition,
#: because the frontend matches on it.
HUMAN_ACTOR_REQUIRED_ERROR = "human_actor_required"

#: One message per reason. Refusals are shown verbatim to users, and a single
#: generic sentence would be wrong for at least one branch — "no boundary is
#: configured" and "you did not come through the boundary" are different facts
#: and suggest different next steps. Each ends by saying nothing was written,
#: because the first thing a scientist wants to know about a refused mutation is
#: whether it half-happened.
_REFUSAL_MESSAGES: dict[str, str] = {
    IdentityRefusal.NO_VERIFIER_CONFIGURED.value: (
        "This operation records who performed it, and this deployment cannot "
        "establish who is calling: no trusted authentication boundary is "
        "configured, so nothing checked. Nothing was written."
    ),
    IdentityRefusal.UNVERIFIED_EDGE_TRAVERSAL.value: (
        "This operation records who performed it, and this request was not "
        "established through the trusted authentication boundary, so the caller "
        "cannot be attributed. Nothing was written."
    ),
    # A service credential is a valid way to authorize a call and an invalid way
    # to author a record. The message says which of the two failed, because a
    # caller holding a working credential will otherwise read this as an auth
    # failure and retry with the same credential forever.
    "service_principal_not_attributable": (
        "This operation records who performed it, and this request was "
        "authorized by a service credential rather than a person. A service "
        "cannot be recorded as the author. Nothing was written."
    ),
}


class HumanActorRequired(Exception):
    """An attributability refusal, carried out of a dependency as a typed body.

    A FastAPI dependency cannot return a response, only raise — the same
    constraint ``TutorialScopeError`` solves, and this is deliberately the same
    solution so the two refusals have one shape between them.

    **The handler below is NOT registered on the app**, because no route consumes
    :func:`require_human_actor` yet and a handler for an exception nothing raises
    is dead code that reads as wiring. The route slice that first consumes the
    dependency must register it in ``create_app`` in the same change; until then,
    raising this from a live route would surface as a 500. That is stated here
    rather than left to be discovered.
    """

    def __init__(self, *, operation: str, identity: RequestIdentity) -> None:
        super().__init__(HUMAN_ACTOR_REQUIRED_ERROR)
        reason = (
            identity.refusal.value
            if identity.refusal is not None
            else "service_principal_not_attributable"
        )
        self.status_code = 409
        self.payload: dict[str, str] = {
            "error": HUMAN_ACTOR_REQUIRED_ERROR,
            "operation": operation,
            "trust": identity.trust.value,
            "reason": reason,
            "message": _REFUSAL_MESSAGES[reason],
        }


async def human_actor_required_handler(request, exc: HumanActorRequired) -> JSONResponse:
    """Render a :class:`HumanActorRequired` as its typed JSON body. Not registered."""
    return JSONResponse(status_code=exc.status_code, content=exc.payload)


def require_human_actor(operation: str) -> Callable[[Request], RequestIdentity]:
    """A dependency that admits only a request with an attributable human actor.

    Modelled on ``routes._tutorial_scope_required``: a named operation, a typed
    ``{"error": ...}`` body, and a refusal that changes nothing. In this build it
    refuses **every** request, including one carrying all five edge headers.

    WHY 409, ARGUED AGAINST THE TWO OBVIOUS ALTERNATIVES
    ----------------------------------------------------
    **401 Unauthorized is wrong, and wrong in a way that misleads.** It means
    "authenticate and retry", and RFC 9110 §11.6.1 requires a ``WWW-Authenticate``
    challenge with it. There is no challenge to send: no credential exists that
    this build would accept, because the missing piece is a *verifier*, not a
    credential. Worse, 401 blames the caller — it says they failed to prove who
    they are, when in fact they may have authenticated perfectly at the edge and
    the server simply has no way to check (§2: an arriving header proves nothing).
    A refusal should not attribute the failure to the wrong party.

    **503 Service Unavailable is wrong because it promises a retry.** It means a
    transient inability, conventionally paired with ``Retry-After``, and clients
    and platform probes both treat it as "try again shortly". This is not
    transient: it is a deliberate, configured absence that will persist until
    somebody builds and approves a verifier. A retry loop against it is pure
    waste, and a health surface that treats it as an outage is being told
    something false. (Contrast ``storage_unavailable_handler``'s 503, which is
    correct precisely because a database outage *is* transient.)

    **409 Conflict is right**: the request conflicts with the current state of
    the deployment. The operation needs an attributable actor; this deployment
    establishes none; no header, credential, or retry changes that. It is also
    exactly the shape ``_tutorial_scope_required`` already uses for "this
    operation needs a context this deployment cannot supply here", and matching an
    existing, reviewed refusal is worth more than a marginally more precise code
    nobody else in this API uses.
    """

    def dependency(request: Request) -> RequestIdentity:
        identity = resolve_identity_for_request(request)
        if identity.trust is TrustTier.EDGE_HUMAN and identity.human is not None:
            return identity
        raise HumanActorRequired(operation=operation, identity=identity)

    return dependency


# --------------------------------------------------------------------------
# Stamping
# --------------------------------------------------------------------------


def stamp_actor(identity: RequestIdentity, scope: str | None) -> str | None:
    """The subject to attribute an effect to, or ``None``. **``None`` today, always.**

    Returns ``None`` — meaning *do not stamp anything* — in three cases, and the
    caller must treat all three the same way: write no actor, rather than write a
    placeholder.

    **1. A worked-example session, unconditionally and first.** ``scope is not
    None`` means the request operates inside a temporary, synthetic tutorial
    session, and a tutorial session is never persisted as normal content
    (``CLAUDE.md`` §15: enforced three times over on the persistence path). Real
    attribution inside it would be the one durable trace a discardable session
    left behind, and it would be attached to fabricated science. The check is
    first in the function on purpose: it must not be reachable-past, and it does
    not depend on how good the identity is — **a perfectly verified actor in a
    tutorial session still stamps nothing.**

    **2. Any tier below ``EDGE_HUMAN``.** ``UNTRUSTED`` names nobody by
    construction, and ``SERVICE`` names a credential rather than a person
    (:class:`ServicePrincipal`).

    **3. No human on an ``EDGE_HUMAN`` identity** — impossible under
    :class:`RequestIdentity`'s invariant, and re-checked anyway because this
    function's failure mode is writing a wrong name into a scientific record, and
    a redundant check is cheaper than that.

    WHERE THE RETURN VALUE MAY NOT GO
    ---------------------------------
    Not into ``attribution.uploaded_by`` via a draft. The truth core refuses a
    draft-authored value for that field by design (commit ``bdff8f5``), and this
    function is not a way around that refusal — stamping it would require a
    change *in the truth core*, reviewed on its own terms.

    Nothing calls this function. It is defined now so that the tutorial rule is
    written down in code, with a test, before the first caller exists.
    """
    if scope is not None:
        return None
    if identity.trust is not TrustTier.EDGE_HUMAN:
        return None
    if identity.human is None:  # pragma: no cover - invariant-guarded, kept anyway
        return None
    return identity.human.subject
