"""The identity/trust seam: five guards, one of them mechanical over the source.

WHAT THESE TESTS ARE FOR
------------------------
``isaac_api.identity`` claims a structural property — *a claim is only readable
through the thing that vouches for it*, so ``if header exists: trust it`` is
**unwritable** rather than merely discouraged. A docstring cannot guarantee that.
These tests are the part that can.

The one to read first is
:func:`test_five_planted_edge_headers_establish_no_identity`. The infrastructure
owner confirmed on 2026-08-12 that the Service is a plain ClusterIP with no
NetworkPolicy, so any in-cluster pod can reach this application directly and
forge the five edge headers (``docs/identity-trust-contract.md`` §2, Q4). That
test plants all five and asserts the result is ``UNTRUSTED`` with nobody in it:
**the bypass cannot become an identity.**

The last one, :func:`test_no_backend_module_names_an_identity_header`, converts a
manual invariant into a mechanical one. "The verifier is the sole header reader"
is otherwise a rule enforced by whoever happens to review the next PR.
"""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import pytest
from starlette.requests import Request

from isaac_api import identity as ident

# Imported at module scope on purpose: ``isaac_api.app`` calls ``create_app()`` at
# import time, so a deferred import inside a test that has already monkeypatched a
# deliberately-invalid env var would blow up on the IMPORT rather than on the call
# the test is measuring.
from isaac_api.app import create_app
from isaac_api.identity import (
    EDGE_INJECTED_HEADERS,
    EDGE_TRUST_VERIFIER_ENV,
    HUMAN_ACTOR_REQUIRED_ERROR,
    PERMANENTLY_UNTRUSTED_HEADERS,
    TRUST_BASIS_TEST_FIXTURE,
    EdgeAssertion,
    HumanActor,
    HumanActorRequired,
    IdentityRefusal,
    NotTraversed,
    RequestIdentity,
    ServicePrincipal,
    Traversed,
    TrustTier,
    Unconfigured,
    UnconfiguredEdgeVerifier,
    edge_trust_verifier,
    human_actor_required_handler,
    require_human_actor,
    resolve_identity_for_request,
    resolve_request_identity,
    stamp_actor,
    validate_edge_trust_verifier_or_raise,
)

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
BACKEND_SRC = _REPO / "apps" / "api" / "isaac_api"
IDENTITY_MODULE = BACKEND_SRC / "identity.py"

#: A value no honest edge would ever inject, so finding it anywhere downstream is
#: unambiguous. Deliberately separator-free — §6A records that a canary containing
#: ``,`` or ``|`` defeats segment matching and yields the wrong answer.
PLANTED = "forged-by-an-in-cluster-caller"


# --- helpers ------------------------------------------------------------------


def _request(headers: dict[str, str] | None = None) -> Request:
    """A minimal real ASGI request. Real, not a mock, so the headers genuinely arrive."""
    raw = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/experiments",
            "raw_path": b"/api/experiments",
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("10.42.0.7", 51234),
            "headers": raw,
        }
    )


class _TripwireRequest:
    """A "request" on which **every** attribute access raises.

    This is how "reads no request object" is proved rather than asserted. Any
    ``request.headers``, ``request.scope``, ``request.cookies`` — anything at all
    — detonates here instead of quietly succeeding.
    """

    def __getattribute__(self, name: str):  # noqa: ANN204 - always raises
        raise AssertionError(f"the request was read: .{name}")


@pytest.fixture(autouse=True)
def _no_verifier_selected(monkeypatch):
    """Every test starts from the shipped default: no verifier configured.

    Autouse because the fail-closed default is the state under test almost
    everywhere, and a leaked env var from another test would make the dangerous
    direction (an identity appearing) look like a pass.
    """
    monkeypatch.delenv(EDGE_TRUST_VERIFIER_ENV, raising=False)


def _fixture_assertion(**overrides) -> EdgeAssertion:
    """An assertion of the shape a real verifier would produce.

    ``trust_basis`` is ``test_fixture`` and cannot honestly be anything else here:
    no verifier in this build mints ``verified_edge_assertion``, so a test that
    used that basis would be claiming a provenance that did not happen.
    """
    fields = {
        "subject": "sfaraday",
        "display_name": "S. Faraday",
        "groups": frozenset({"researcher"}),
        "verifier_id": "fake-armed-verifier",
        "trust_basis": TRUST_BASIS_TEST_FIXTURE,
    }
    fields.update(overrides)
    return EdgeAssertion(**fields)


class _ArmedFakeVerifier:
    """A verifier that always says the boundary WAS traversed.

    It exists to prove the happy path is reachable at all — otherwise every
    assertion in this file would be satisfied by a module that simply cannot
    produce an actor, and the refusals would prove nothing.

    It records that it was handed something and **never touches it**, which is the
    property :func:`test_armed_verifier_yields_an_actor_without_reading_the_request`
    checks by handing it a :class:`_TripwireRequest`.
    """

    verifier_id = "fake-armed-verifier"

    def __init__(self, assertion: EdgeAssertion | None = None) -> None:
        self.assertion = assertion or _fixture_assertion()
        self.calls = 0
        self.received: object = None

    def verify(self, request: object):
        self.calls += 1
        self.received = request
        return Traversed(assertion=self.assertion)


def _arm(monkeypatch, verifier) -> None:
    """Register ``verifier`` under the env-selected name and select it.

    Registration goes through the module's own ``_VERIFIERS`` table rather than
    around it, so the test exercises the real selection path — including
    :func:`validate_edge_trust_verifier_or_raise`, which must accept a name the
    table knows.
    """
    monkeypatch.setitem(ident._VERIFIERS, "fake", lambda: verifier)
    monkeypatch.setenv(EDGE_TRUST_VERIFIER_ENV, "fake")


# --- 1. the bypass cannot become an identity ----------------------------------


def test_five_planted_edge_headers_establish_no_identity():
    """All five edge headers, planted by the caller, and nobody is identified.

    **This is the test that proves the in-cluster bypass cannot become an
    identity.** The headers here are exactly what a forging pod would send: the
    five the edge injects on its own path, carrying values the caller chose. The
    module never looks at them, so the answer does not depend on their contents —
    which is precisely why a forgery buys nothing.
    """
    request = _request({name: PLANTED for name in EDGE_INJECTED_HEADERS})
    # Sanity: the headers really are on the request. Without this the test could
    # pass against a request that carried nothing.
    assert request.headers["x-authentik-username"] == PLANTED
    assert len(EDGE_INJECTED_HEADERS) == 5

    identity = resolve_identity_for_request(request)

    assert identity.trust is TrustTier.UNTRUSTED
    assert identity.human is None
    assert identity.service is None
    assert identity.refusal is IdentityRefusal.NO_VERIFIER_CONFIGURED
    # The planted value is not merely unused — it is nowhere in the answer.
    assert PLANTED not in repr(identity)
    # And nothing may be attributed to it, in either scope.
    assert stamp_actor(identity, None) is None
    assert stamp_actor(identity, "tutorial-session-1") is None


def test_the_two_disqualified_headers_also_establish_no_identity():
    """Same for the permanently untrusted pair, which a client can set freely.

    ``x-isaac-edge`` is the trap worth pinning: its name implies it witnesses edge
    traversal, and §6A.2 records that it cannot, because any client can set it.
    """
    all_seven = tuple(EDGE_INJECTED_HEADERS) + tuple(PERMANENTLY_UNTRUSTED_HEADERS)
    identity = resolve_identity_for_request(_request({n: PLANTED for n in all_seven}))
    assert identity.trust is TrustTier.UNTRUSTED
    assert identity.human is None


def test_the_default_path_reads_no_request_at_all():
    """The shipped resolution does not touch the request object it is handed."""
    identity = resolve_identity_for_request(_TripwireRequest())  # type: ignore[arg-type]
    assert identity.trust is TrustTier.UNTRUSTED
    assert identity.refusal is IdentityRefusal.NO_VERIFIER_CONFIGURED


def test_the_shipped_verifier_is_the_unconfigured_one_however_the_env_is_set(monkeypatch):
    """Fail-closed selection: unset, valid, and garbage all yield no identity."""
    assert isinstance(edge_trust_verifier(), UnconfiguredEdgeVerifier)
    for value in ("unconfigured", "  unconfigured  ", "", "   ", "edge", "TRUE", "authentik"):
        monkeypatch.setenv(EDGE_TRUST_VERIFIER_ENV, value)
        assert isinstance(edge_trust_verifier(), UnconfiguredEdgeVerifier), value
        assert edge_trust_verifier().verify(_TripwireRequest()) == Unconfigured(
            verifier_id="unconfigured"
        )


def test_a_misconfigured_container_fails_to_boot(monkeypatch, tmp_path):
    """A verifier name this build does not have refuses to construct the app.

    The resolver fails closed, so without this check the deployment would boot
    looking configured while checking nothing — the failure mode the validator
    exists to make loud.
    """
    assert validate_edge_trust_verifier_or_raise() is None  # unset is fine
    monkeypatch.setenv(EDGE_TRUST_VERIFIER_ENV, "unconfigured")
    assert validate_edge_trust_verifier_or_raise() is None
    monkeypatch.setenv(EDGE_TRUST_VERIFIER_ENV, "authentik-edge")
    with pytest.raises(RuntimeError) as excinfo:
        validate_edge_trust_verifier_or_raise()
    assert EDGE_TRUST_VERIFIER_ENV in str(excinfo.value)

    # …and create_app really calls it, rather than the validator sitting unused.
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    with pytest.raises(RuntimeError):
        create_app()
    monkeypatch.delenv(EDGE_TRUST_VERIFIER_ENV)
    create_app()  # and it boots again once the misconfiguration is removed


# --- 2. the refusal -----------------------------------------------------------


def test_require_human_actor_refuses_with_the_typed_body_and_writes_nothing(tmp_path):
    """The dependency refuses every request in this build, typed, and touches no disk."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    before = sorted(p.relative_to(workspace) for p in workspace.rglob("*"))

    dependency = require_human_actor("create_experiment")
    request = _request({name: PLANTED for name in EDGE_INJECTED_HEADERS})

    with pytest.raises(HumanActorRequired) as excinfo:
        dependency(request)

    exc = excinfo.value
    assert exc.status_code == 409
    assert exc.payload == {
        "error": HUMAN_ACTOR_REQUIRED_ERROR,
        "operation": "create_experiment",
        "trust": "untrusted",
        "reason": "no_verifier_configured",
        "message": (
            "This operation records who performed it, and this deployment cannot "
            "establish who is calling: no trusted authentication boundary is "
            "configured, so nothing checked. Nothing was written."
        ),
    }
    # The refusal never echoes the caller's planted strings back at them.
    assert PLANTED not in repr(exc.payload)

    after = sorted(p.relative_to(workspace) for p in workspace.rglob("*"))
    assert after == before == []


def test_the_refusal_renders_as_its_typed_json_body():
    """The handler produces the typed body, called directly rather than through a route.

    THIS DOCSTRING USED TO END "It is NOT registered — see the class", AND THAT IS NO
    LONGER TRUE: ``create_app`` registers it, because ``POST .../submit`` consumes
    ``require_human_actor``. That end-to-end path is asserted in
    ``test_submission.py::test_the_default_build_refuses_every_submission_with_a_typed_409``,
    which is what would catch a missing registration; this one is the unit check on
    the body itself.
    """
    dependency = require_human_actor("export_record")
    with pytest.raises(HumanActorRequired) as excinfo:
        dependency(_request())
    response = asyncio.run(human_actor_required_handler(None, excinfo.value))
    assert response.status_code == 409
    assert b'"human_actor_required"' in response.body
    assert b'"export_record"' in response.body


def test_a_service_principal_is_refused_as_an_author_with_its_own_reason():
    """A service may authorize; it may never be the attributable actor.

    The reason is distinct from the untrusted one on purpose: a caller holding a
    working service credential would otherwise read the refusal as an auth failure
    and retry with the same credential indefinitely.
    """
    identity = RequestIdentity.for_service(
        ServicePrincipal(principal_id="ingest-worker", trust_basis=TRUST_BASIS_TEST_FIXTURE)
    )
    assert identity.trust is TrustTier.SERVICE
    assert identity.human is None
    assert stamp_actor(identity, None) is None
    assert not hasattr(identity.service, "subject")

    exc = HumanActorRequired(operation="create_experiment", identity=identity)
    assert exc.status_code == 409
    assert exc.payload["trust"] == "service"
    assert exc.payload["reason"] == "service_principal_not_attributable"
    assert "Nothing was written." in exc.payload["message"]


# --- 3. the armed verifier ----------------------------------------------------


def test_armed_verifier_yields_an_actor_without_reading_the_request(monkeypatch):
    """A ``Traversed`` verdict produces the actor — and the verifier reads nothing.

    The tripwire request is the load-bearing half. If the fake (or anything
    between it and the caller) touched a single attribute of the request, this
    raises instead of passing, so "the fake reads no request object" is measured
    rather than promised.
    """
    fake = _ArmedFakeVerifier()
    _arm(monkeypatch, fake)
    validate_edge_trust_verifier_or_raise()  # a registered name is a valid config

    tripwire = _TripwireRequest()
    identity = resolve_identity_for_request(tripwire)  # type: ignore[arg-type]

    assert fake.calls == 1
    # It was handed the request and did not read it. `is` on the recorded value
    # would itself be an attribute access on the tripwire, so compare identity
    # through object.__getattribute__-free means: the fake stored it verbatim.
    assert fake.received is tripwire

    assert identity.trust is TrustTier.EDGE_HUMAN
    assert identity.refusal is None
    assert identity.service is None
    actor = identity.human
    assert actor is not None
    assert actor.subject == "sfaraday"
    assert actor.subject_kind == "authentik_username"
    assert actor.display_name == "S. Faraday"
    assert actor.groups == frozenset({"researcher"})
    assert actor.trust_basis == TRUST_BASIS_TEST_FIXTURE
    # Groups are carried and not consumed, except by the one predicate.
    assert actor.is_admin() is False


def test_groups_are_carried_verbatim_and_only_admin_is_consumed(monkeypatch):
    """Beamline groups are not ISAAC roles: carried, never filtered, never read."""
    fake = _ArmedFakeVerifier(
        _fixture_assertion(groups=frozenset({"admin", "researcher", "bl152-staff"}))
    )
    _arm(monkeypatch, fake)
    actor = resolve_identity_for_request(_TripwireRequest()).human  # type: ignore[arg-type]
    assert actor is not None
    assert actor.groups == frozenset({"admin", "researcher", "bl152-staff"})
    assert actor.is_admin() is True

    no_groups = resolve_request_identity(
        Traversed(assertion=_fixture_assertion(groups=frozenset()))
    ).human
    assert no_groups is not None
    assert no_groups.is_admin() is False


def test_require_human_actor_admits_an_armed_request(monkeypatch):
    """The dependency is a gate, not a wall: an attributable actor passes it."""
    _arm(monkeypatch, _ArmedFakeVerifier())
    identity = require_human_actor("create_experiment")(_TripwireRequest())  # type: ignore[arg-type]
    assert identity.trust is TrustTier.EDGE_HUMAN
    assert identity.human is not None


# --- 4. tutorial scope never stamps -------------------------------------------


def test_a_tutorial_scoped_request_never_stamps_a_real_actor(monkeypatch):
    """Verified actor + worked-example session -> ``None``. Unconditionally.

    A worked-example session is temporary and synthetic and is never persisted as
    normal content. A real name stamped inside one would be the single durable
    trace a discardable session left behind, attached to fabricated science.

    The scope check does not consult the identity at all, which is why this holds
    for a *perfectly verified* actor and not only for the untrusted default.
    """
    _arm(monkeypatch, _ArmedFakeVerifier())
    identity = resolve_identity_for_request(_TripwireRequest())  # type: ignore[arg-type]
    assert identity.trust is TrustTier.EDGE_HUMAN  # the strongest identity available

    for scope in ("tutorial-session-1", "ts_01JABCDEFGHJKMNPQRSTVWXYZ", "", "0"):
        assert stamp_actor(identity, scope) is None, scope

    # …and in the ordinary scope the same identity DOES stamp, so the assertions
    # above are about the scope and not about a function that always returns None.
    assert stamp_actor(identity, None) == "sfaraday"


def test_stamping_needs_both_an_ordinary_scope_and_an_edge_human():
    """The two conditions are independent; neither alone is enough."""
    untrusted = RequestIdentity.untrusted(IdentityRefusal.UNVERIFIED_EDGE_TRAVERSAL)
    assert stamp_actor(untrusted, None) is None
    assert stamp_actor(untrusted, "tutorial-session-1") is None

    human = RequestIdentity.for_human(
        HumanActor(subject="sfaraday", trust_basis=TRUST_BASIS_TEST_FIXTURE)
    )
    assert stamp_actor(human, None) == "sfaraday"
    assert stamp_actor(human, "tutorial-session-1") is None


# --- 5. the mechanical source scan --------------------------------------------


def _backend_modules() -> list[Path]:
    return sorted(p for p in BACKEND_SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _code_only(path: Path) -> str:
    """The module's CODE, with every comment and docstring removed.

    Stripping is not optional here and the reason is the same one the frontend's
    equivalent scan gives: ``identity.py``'s own docstring writes the unsafe line
    ``request.headers.get("x-authentik-username")`` out in full in order to
    explain why it is unwritable. A whole-text scan would be satisfied by deleting
    the explanation instead of the dependency — the disclaimer would become the
    defect.

    ``ast.unparse`` of a docstring-stripped tree is exact rather than
    approximate: comments are not AST nodes at all, so they cannot survive, and
    every real string literal (including the header names in
    ``EDGE_INJECTED_HEADERS``) does survive, which is what makes the scan
    non-vacuous.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_no_backend_module_names_an_identity_header():
    """``x-authentik-`` appears in NO backend module except the verifier module.

    "The verifier is the sole header reader" is otherwise a rule enforced by
    whoever reviews the next PR. This makes it a build failure: the day a route,
    a middleware, or a helper reaches for ``x-authentik-username``, this test goes
    red before anyone has to notice it in a diff.
    """
    modules = _backend_modules()
    # The scan is only worth anything if it is actually looking at the codebase.
    names = {p.relative_to(BACKEND_SRC).as_posix() for p in modules}
    assert {"routes.py", "app.py", "identity.py", "auth.py"} <= names
    assert len(modules) >= 20

    offenders = [
        p.relative_to(_REPO).as_posix()
        for p in modules
        if p != IDENTITY_MODULE and "x-authentik-" in p.read_text(encoding="utf-8").lower()
    ]
    assert offenders == [], (
        "an identity header is named outside the verifier module; only "
        "isaac_api/identity.py may name one, and even there nothing reads it"
    )
    # …and the exception is real, so a scan that read nothing could not pass.
    assert "x-authentik-" in IDENTITY_MODULE.read_text(encoding="utf-8")


def test_the_verifier_module_names_headers_only_as_recorded_data():
    """Inside ``identity.py`` the header names are frozen data, nothing more.

    Parsed from the DOCSTRING-STRIPPED source: the module head quotes
    ``x-authentik-username`` in prose while explaining why nothing reads it, and a
    scan that counted prose would be asserting about the explanation instead of
    about the code.
    """
    tree = ast.parse(_code_only(IDENTITY_MODULE))
    found = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.search(r"x-authentik-|x-isaac-edge", node.value)
    }
    assert found == set(EDGE_INJECTED_HEADERS) | set(PERMANENTLY_UNTRUSTED_HEADERS)


def test_the_verifier_module_performs_no_header_access_of_any_kind():
    """No backend module reads an identity header, including the one that names them.

    The shipped verifier reads nothing, so this is currently true of the whole
    application; the scan pins the module where it would stop being true first.
    """
    raw = IDENTITY_MODULE.read_text(encoding="utf-8")
    code = _code_only(IDENTITY_MODULE)

    # The stripper kept the code…
    assert "def resolve_request_identity" in code
    assert "EDGE_INJECTED_HEADERS" in code
    # …and really did remove prose that names the thing being scanned for, so a
    # stripper returning the text unchanged would fail below and one returning ''
    # would fail above.
    assert "request.headers.get" in raw
    assert "request.headers.get" not in code

    for pattern in (
        r"\.headers\b",
        r"\.scope\b",
        r"\.cookies\b",
        r"raw_headers",
        r"\bHeader\s*\(",
        r"getheader",
    ):
        assert re.search(pattern, code) is None, f"identity.py performs header access: {pattern}"


# --- the type invariants that make the unwritable-path argument hold ----------


def test_an_untrusted_identity_cannot_carry_a_principal():
    """``refusal`` is non-None iff UNTRUSTED, and the principal agrees with the tier."""
    actor = HumanActor(subject="sfaraday", trust_basis=TRUST_BASIS_TEST_FIXTURE)
    with pytest.raises(ValueError):
        RequestIdentity(trust=TrustTier.UNTRUSTED)  # no reason given
    with pytest.raises(ValueError):
        RequestIdentity(
            trust=TrustTier.UNTRUSTED,
            human=actor,
            refusal=IdentityRefusal.NO_VERIFIER_CONFIGURED,
        )
    with pytest.raises(ValueError):
        RequestIdentity(trust=TrustTier.EDGE_HUMAN)  # claims a human, carries none
    with pytest.raises(ValueError):
        RequestIdentity(
            trust=TrustTier.EDGE_HUMAN,
            human=actor,
            refusal=IdentityRefusal.NO_VERIFIER_CONFIGURED,
        )


def test_a_claim_cannot_exist_without_naming_who_vouched_for_it():
    """An assertion refuses to be built empty, anonymous, or on an unrecognised basis."""
    with pytest.raises(ValueError):
        _fixture_assertion(subject="")
    with pytest.raises(ValueError):
        _fixture_assertion(subject="   ")
    with pytest.raises(ValueError):
        _fixture_assertion(verifier_id="")
    with pytest.raises(ValueError):
        _fixture_assertion(trust_basis="because-i-said-so")
    with pytest.raises(ValueError):
        _fixture_assertion(subject_kind="authentik_uid")  # no UID mapping, by decision
    with pytest.raises(TypeError):
        _fixture_assertion(groups={"researcher"})  # mutable set


def test_the_verdict_union_is_closed():
    """An unknown verdict raises rather than being silently downgraded.

    A ``case _: return untrusted(...)`` default would be safer per request and
    worse overall: a verdict added without a rule here would do nothing, quietly,
    while its own tests passed.
    """
    assert resolve_request_identity(
        Unconfigured(verifier_id="x")
    ).refusal is IdentityRefusal.NO_VERIFIER_CONFIGURED
    assert resolve_request_identity(
        NotTraversed(verifier_id="x", detail="no boundary evidence")
    ).refusal is IdentityRefusal.UNVERIFIED_EDGE_TRAVERSAL

    class _Rogue:
        pass

    with pytest.raises(TypeError):
        resolve_request_identity(_Rogue())  # type: ignore[arg-type]


def test_unconfigured_and_not_traversed_are_different_answers():
    """"Nothing checked" is not "this request did not come through the edge"."""
    a = resolve_request_identity(Unconfigured(verifier_id="unconfigured"))
    b = resolve_request_identity(NotTraversed(verifier_id="some-verifier"))
    assert a.refusal is not b.refusal
    assert a.trust is b.trust is TrustTier.UNTRUSTED
