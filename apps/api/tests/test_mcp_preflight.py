"""The operator preflight: does it tell the truth about the four outcomes?

WHAT THIS FILE IS FOR, AND THE FAILURE MODE IT IS WRITTEN AGAINST
=================================================================
``CLAUDE.md`` §11 records a slice whose central claim was pinned by **string
presence rather than behaviour**, and which passed all 25 of its tests while a
**fabricating seam returning ``{ok: true, …}`` also passed all 25**. A preflight
is exactly that shape of hazard: its whole output is prose and status numbers, so
a test that greps its text for "403" would pass over an implementation that
always says 403.

So every assertion here is over a **returned value** — an outcome constant, a
status integer, a key set, an equivalence tuple — and the two claims that matter
most are pinned twice:

1. **The four statuses are asserted against the REAL TRANSPORT**, over HTTP,
   through ``TestClient``, and then required to equal what the preflight
   predicted. A preflight that models the transport can drift from it; the only
   way to know it has not is to run both and compare. Two of the four are driven
   through a live application built by ``create_app`` (404 unmounted, 403+405 on
   ``local-loopback``), and the 401 is driven through a live application
   configured onto the OAuth binding with a real generated key set.
2. **No secret appears in any output**, asserted by planting a distinctively
   secret-shaped value in *every* input the module takes — the deployment
   variable, every OAuth variable, the configured resource, and the token's own
   ``aud`` — and then walking the whole returned structure for it. Not a
   whitelist of fields: a recursive walk, so a field added later is covered on
   the day it is added.

RED PROOFS
==========
Every guard below that could be vacuous carries a ``MUTATION:`` note recording
the false implementation that was constructed and the output it produced. They
were run; the quoted text is the actual failure, not a prediction.

NOTHING HERE CONTACTS ANYTHING
==============================
No socket is bound (unlike ``test_mcp_transport.py``'s one uvicorn case), no
name is resolved, no authorization server is contacted and no real credential
exists. The signing key is generated deterministically in-process by
``mcp_oauth_keys``; every host name is from a reserved example range.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import mcp_oauth_keys as keys
from isaac_api.mcp import preflight as pf
from isaac_api.mcp.deployment import (
    DEPLOYMENT_ENV,
    LOCAL_LOOPBACK,
    LOCAL_SCOPES_ENV,
    LOCAL_SESSION_ENV,
    OAUTH_RESOURCE_SERVER,
    RESERVED_BINDING_NAMES,
    LocalLoopbackDeployment,
    UnconfiguredDeployment,
    resolve_binding,
)
from isaac_api.mcp.jwt import verify_access_token, TokenRejected, jwks_from_document
from isaac_api.mcp.oauth import (
    FILE_TOKEN_VERIFIER,
    ISSUER_ENV,
    JWKS_FILE_ENV,
    OAUTH_ENV_VARS,
    RESOURCE_ENV,
    TOKEN_VERIFIER_ENV,
    resolve_oauth_binding,
)
from isaac_api.mcp.transport import MCP_PATH

#: A reserved-range peer, in the shape ASGI reports one. Not loopback.
REMOTE_PEER = ("203.0.113.7", 44321)
LOOPBACK_PEER = ("127.0.0.1", 51234)

RESOURCE = "https://isaac.example.org/api/mcp"
ISSUER = "https://authorization.example.org"
NOW = 1_798_000_000


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def signing_key():
    return keys.generate("isaac-preflight-1", seed=keys.SEED)


@pytest.fixture()
def jwks_file(tmp_path, signing_key):
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps(keys.jwks(signing_key)), encoding="utf-8")
    return path


@pytest.fixture()
def clean(tmp_path, monkeypatch):
    """An isolated workspace with every MCP variable cleared."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    for name in (DEPLOYMENT_ENV, LOCAL_SCOPES_ENV, LOCAL_SESSION_ENV, *OAUTH_ENV_VARS):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def build_app():
    """A fresh application for the CURRENT environment.

    Re-imported per call for the reason ``test_mcp_transport.py`` gives: the
    mount decision is made inside ``create_app``, so a test that changes the
    environment must build afterwards or it is testing the wrong configuration.
    """
    from isaac_api.app import create_app

    return create_app()


def oauth_env(jwks_file, **overrides) -> dict:
    values = {
        RESOURCE_ENV: RESOURCE,
        ISSUER_ENV: ISSUER,
        TOKEN_VERIFIER_ENV: FILE_TOKEN_VERIFIER,
        JWKS_FILE_ENV: str(jwks_file),
    }
    values.update(overrides)
    return values


def oauth_binding(jwks_file, **overrides):
    resolved = resolve_oauth_binding(oauth_env(jwks_file, **overrides), "")
    assert not isinstance(resolved, str), resolved
    return resolved


# ==========================================================================
# 1. The decision table is data, and it is complete
# ==========================================================================

def test_the_four_briefed_outcomes_are_exactly_the_modelled_rows():
    """The table has four modelled rows carrying exactly 404/405/403/401.

    Asserted as a SET of ``(outcome, status)`` pairs rather than as four
    separate lookups, so adding a fifth modelled row — or silently changing one
    status — fails here rather than passing four independent assertions.

    MUTATION: adding a fifth modelled row to ``DECISION_TABLE`` turns this RED::

        AssertionError: assert {('credential_required', 401), ... ('made_up', 418)} == {...}
        Extra items in the left set: ('made_up', 418)
    """
    modelled = {(row.outcome, row.status) for row in pf.DECISION_TABLE if row.modelled}
    assert modelled == {
        (pf.OUTCOME_UNMOUNTED, 404),
        (pf.OUTCOME_METHOD_NOT_ALLOWED, 405),
        (pf.OUTCOME_ENTRY_GUARD_REFUSED, 403),
        (pf.OUTCOME_CREDENTIAL_REQUIRED, 401),
    }
    assert len(pf.DECISION_TABLE) == 4


def test_every_row_cites_evidence_and_nothing_is_modelled_twice():
    """A row with no citation is a row nobody can re-derive.

    ``ADJACENT_OUTCOMES`` must all be ``modelled=False``: that flag is what keeps
    "the table has four rows" meaningful, and a documented status leaking into
    the modelled set would make :func:`transport_outcome`'s contract wrong.
    """
    for row in (*pf.DECISION_TABLE, *pf.ADJACENT_OUTCOMES):
        assert row.evidence, row.outcome
        assert all(":" in citation for citation in row.evidence), row.outcome
    assert [row.modelled for row in pf.ADJACENT_OUTCOMES] == [False] * len(
        pf.ADJACENT_OUTCOMES
    )
    outcomes = [row.outcome for row in (*pf.DECISION_TABLE, *pf.ADJACENT_OUTCOMES)]
    assert len(outcomes) == len(set(outcomes))


def test_the_two_different_404s_are_both_written_down():
    """The unmounted 404 and the JSON-RPC ``method_not_found`` 404 are different
    things with one status, and an operator who conflates them looks for a
    missing route that is mounted. Both must be in the published table."""
    statuses = [row.status for row in (*pf.DECISION_TABLE, *pf.ADJACENT_OUTCOMES)]
    assert statuses.count(404) == 2


# ==========================================================================
# 2. Binding selection — name only, no resolution
# ==========================================================================

@pytest.mark.parametrize(
    "raw, classification, mounts",
    [
        (None, pf.CLASSIFICATION_UNSET, False),
        ("", pf.CLASSIFICATION_UNSET, False),
        ("   ", pf.CLASSIFICATION_UNSET, False),
        ("local-loopback", pf.CLASSIFICATION_LOCAL_LOOPBACK, True),
        ("oauth-resource-server", pf.CLASSIFICATION_OAUTH_RESOURCE_SERVER, None),
        ("edge-issued-bearer", pf.CLASSIFICATION_RESERVED, False),
        ("locol-loopback", pf.CLASSIFICATION_UNRECOGNISED, False),
    ],
)
def test_selection_classifies_every_branch_resolve_binding_has(raw, classification, mounts):
    env = {} if raw is None else {DEPLOYMENT_ENV: raw}
    selection = pf.binding_selection(env)
    assert selection.classification == classification
    assert selection.mounts_transport is mounts


def test_selection_agrees_with_resolve_binding_on_what_actually_mounts():
    """The claim that matters: when selection says ``True``/``False``, the real
    resolver agrees. Not asserted for ``oauth-resource-server``, which selection
    reports as ``None`` — unknown — precisely because deciding it needs a
    resolution that reads a file.

    MUTATION: making the reserved branch report ``mounts_transport=True`` turns
    this RED::

        AssertionError: edge-issued-bearer
        assert True is False
    """
    for raw in ("", LOCAL_LOOPBACK, "locol-loopback", *RESERVED_BINDING_NAMES):
        env = {DEPLOYMENT_ENV: raw} if raw else {}
        selection = pf.binding_selection(env)
        assert selection.mounts_transport is not None, raw
        actual = getattr(resolve_binding(env), "serves_transport", False)
        assert selection.mounts_transport is actual, raw


def test_selection_requested_is_exactly_the_applications_own_mount_gate():
    """``requested`` must equal ``app._mcp_is_requested()``'s condition, because
    that is what decides whether the package is imported at all. Compared against
    the real function rather than re-stated."""
    from isaac_api import app as app_module

    for raw in ("", "  ", LOCAL_LOOPBACK, "nonsense", OAUTH_RESOURCE_SERVER):
        env = {DEPLOYMENT_ENV: raw}
        expected = bool((env.get(app_module._MCP_DEPLOYMENT_ENV) or "").strip())
        assert pf.binding_selection(env).requested is expected, raw


def test_an_unrecognised_deployment_value_is_never_echoed_back():
    """A typo in that variable may be anything an operator pasted. Only documented
    binding names are reported; everything else is replaced, not truncated.

    MUTATION: returning ``raw`` instead of ``reportable`` turns this RED::

        AssertionError: assert 'sk-live-AKIA-notatoken-0123456789' == ''
    """
    planted = "sk-live-AKIA-notatoken-0123456789"
    selection = pf.binding_selection({DEPLOYMENT_ENV: planted})
    assert selection.supplied_reportable == ""
    assert planted not in json.dumps(selection.as_dict())
    # …and a documented name IS reported, so the allowlist is not simply "never".
    assert pf.binding_selection({DEPLOYMENT_ENV: LOCAL_LOOPBACK}).supplied_reportable == (
        LOCAL_LOOPBACK
    )


def test_configuration_is_reported_as_presence_and_never_as_a_value():
    """Every variable is a bool. ``ISAAC_MCP_OAUTH_FIXTURE_JWKS`` holds a whole key
    document, so the result must not be able to carry one."""
    env = {name: f"value-of-{name}" for name in pf.configuration_variables()}
    presence = pf.configuration_presence(env)
    assert set(presence) == set(pf.configuration_variables())
    assert all(isinstance(value, bool) for value in presence.values())
    assert all(presence.values())
    assert pf.configuration_presence({}) == {
        name: False for name in pf.configuration_variables()
    }
    # Whitespace is not presence — it is what an operator leaves when they blank
    # a variable in a manifest.
    assert pf.configuration_presence({DEPLOYMENT_ENV: "   "})[DEPLOYMENT_ENV] is False


# ==========================================================================
# 3. The four outcomes, predicted AND observed
# ==========================================================================

def test_unmounted_is_predicted_and_the_live_application_really_404s(clean):
    """Row 1, both ways.

    The prediction is ``404``/``unmounted``/``path is None``; the observation is
    every verb against the real route table of an application built with the
    variable unset.
    """
    predicted = pf.transport_outcome(None)
    assert predicted.outcome == pf.OUTCOME_UNMOUNTED
    assert predicted.status == 404
    assert predicted.path is None
    assert predicted.code is None

    # A binding that exists but serves no transport reaches the same row.
    assert pf.transport_outcome(UnconfiguredDeployment()).status == 404

    client = TestClient(build_app(), client=LOOPBACK_PEER)
    for method in ("post", "get", "delete"):
        observed = getattr(client, method)(MCP_PATH)
        assert observed.status_code == predicted.status, (method, observed.status_code)


def test_a_remote_peer_is_predicted_403_and_the_live_transport_really_403s(clean):
    """Row 3, both ways — and the ORDER is the point.

    A ``GET`` from a non-loopback peer must be ``403``, not ``405``: the entry
    guard runs before the verb is looked at, so a caller this binding will not
    serve cannot learn from an ``Allow: POST`` that ISAAC speaks MCP here. The
    preflight must predict ``403`` for that same request or it has the order
    wrong.
    """
    binding = LocalLoopbackDeployment()
    predicted = pf.transport_outcome(binding, method="GET", peer=REMOTE_PEER[0])
    assert predicted.outcome == pf.OUTCOME_ENTRY_GUARD_REFUSED
    assert predicted.status == 403
    assert predicted.code == "loopback_only"
    assert predicted.path == MCP_PATH

    clean.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    client = TestClient(build_app(), client=REMOTE_PEER)
    observed = client.get(MCP_PATH)
    assert observed.status_code == predicted.status
    assert observed.json()["error"]["data"]["code"] == predicted.code


def test_a_loopback_get_is_predicted_405_and_the_live_transport_really_405s(clean):
    """Row 2, both ways, including the ``Allow`` header an operator reads."""
    binding = LocalLoopbackDeployment()
    predicted = pf.transport_outcome(binding, method="GET", peer=LOOPBACK_PEER[0])
    assert predicted.outcome == pf.OUTCOME_METHOD_NOT_ALLOWED
    assert predicted.status == 405
    assert predicted.path == MCP_PATH

    clean.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    client = TestClient(build_app(), client=LOOPBACK_PEER)
    for method in ("get", "delete"):
        observed = getattr(client, method)(MCP_PATH)
        assert observed.status_code == predicted.status, method
        assert observed.headers["allow"] == "POST"


def test_oauth_with_no_token_is_predicted_401_and_the_live_transport_really_401s(
    clean, jwks_file
):
    """Row 4, both ways, and this is the one that needed a real key set.

    The application is configured onto the OAuth binding with a generated JWKS on
    disk, so ``create_app`` boots it for real. A ``POST`` carrying no
    ``Authorization`` header must be ``401`` with ``token_absent`` — there is no
    anonymous branch — and the preflight must say so from configuration alone.
    """
    binding = oauth_binding(jwks_file)
    predicted = pf.transport_outcome(binding, peer=REMOTE_PEER[0])
    assert predicted.outcome == pf.OUTCOME_CREDENTIAL_REQUIRED
    assert predicted.status == 401
    assert predicted.code == "token_absent"
    assert predicted.path == MCP_PATH

    for name, value in oauth_env(jwks_file).items():
        clean.setenv(name, value)
    clean.setenv(DEPLOYMENT_ENV, OAUTH_RESOURCE_SERVER)
    client = TestClient(build_app(), client=REMOTE_PEER)
    observed = client.post(
        MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert observed.status_code == predicted.status
    assert observed.json()["error"]["data"]["code"] == predicted.code


def test_the_oauth_binding_does_not_refuse_a_remote_peer_and_loopback_does(jwks_file):
    """The two shipped bindings differ on exactly the guards they declare, and the
    preflight reads the declaration rather than the class.

    Same request, two bindings, two different rows. This is what makes the peer
    row attributable to the binding rather than to the fixture.
    """
    remote = {"peer": REMOTE_PEER[0]}
    assert pf.transport_outcome(LocalLoopbackDeployment(), **remote).status == 403
    assert pf.transport_outcome(oauth_binding(jwks_file), **remote).status == 401


def test_a_loopback_post_with_no_credential_is_served_by_the_loopback_binding():
    """The negative control for row 4: ``local-loopback`` authenticates a caller
    with no credential, so the credential row must NOT fire. Without this, a
    preflight that always returned 401 would pass every test above."""
    outcome = pf.transport_outcome(LocalLoopbackDeployment(), peer=LOOPBACK_PEER[0])
    assert outcome.outcome == pf.OUTCOME_SERVED
    assert outcome.status == 200


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"peer": "203.0.113.7"}, "loopback_only"),
        ({"peer": None}, "loopback_only"),
        ({"peer": "127.0.0.1", "proxy_header_present": True}, "proxied_request_refused"),
        (
            {"peer": "127.0.0.1", "origin": "https://evil.example"},
            "cross_origin_refused",
        ),
        ({"peer": "127.0.0.1", "origin": "null"}, "cross_origin_refused"),
    ],
)
def test_all_three_entry_guards_are_reachable_and_named_separately(kwargs, code):
    """Three guards, five ways in, and the codes are distinct.

    ``origin="null"`` is included because it is the case a re-implementation
    loses: a sandboxed iframe and a ``file://`` document both send it, and it
    must be REFUSED rather than treated as absent. ``peer=None`` is the case ASGI
    reports when it has no peer at all.
    """
    outcome = pf.transport_outcome(LocalLoopbackDeployment(), **kwargs)
    assert outcome.status == 403
    assert outcome.code == code


def test_a_loopback_origin_is_accepted_so_the_origin_guard_is_not_a_blanket_refusal():
    """Negative control for the origin guard."""
    for origin in ("http://127.0.0.1:5173", "http://localhost:5173", "https://[::1]"):
        outcome = pf.transport_outcome(
            LocalLoopbackDeployment(), peer="127.0.0.1", origin=origin
        )
        assert outcome.outcome == pf.OUTCOME_SERVED, origin


def test_a_binding_that_declares_no_guards_is_modelled_as_having_all_of_them():
    """``transport.py`` reads every guard through ``getattr`` with the SAFE
    default, so a binding that forgets to declare one still gets it. The preflight
    must fail closed the same way, or it would tell an operator that a
    half-written binding serves.

    MUTATION: changing the peer guard's default from ``True`` to ``False`` turns
    this RED::

        AssertionError: assert 'served' == 'entry_guard_refused'
    """

    class Bare:
        serves_transport = True

        def authenticate(self, credential):
            raise AssertionError("must not be reached: the peer guard refuses first")

    outcome = pf.transport_outcome(Bare(), peer="203.0.113.7")
    assert outcome.outcome == pf.OUTCOME_ENTRY_GUARD_REFUSED
    assert outcome.code == "loopback_only"


def test_an_exception_that_is_not_a_deployment_refusal_propagates():
    """A preflight that swallowed an arbitrary exception would report a working
    deployment. Only ``DeploymentRefused`` is caught."""

    class Broken:
        serves_transport = True
        requires_loopback_peer = False
        refuses_proxy_headers = False
        requires_loopback_origin = False

        def authenticate(self, credential):
            raise RuntimeError("the binding is broken")

    with pytest.raises(RuntimeError):
        pf.transport_outcome(Broken(), peer="203.0.113.7")


def test_there_is_no_parameter_that_claims_to_model_a_supplied_credential():
    """The removed knob, pinned so it does not come back.

    An earlier draft took ``credential_present`` and fell through to ``served``
    when it was true — which is WRONG for ``local-loopback``, a binding that
    answers ``401 credential_not_verifiable`` for any Authorization header at
    all. That outcome is documented in ``ADJACENT_OUTCOMES`` instead of being
    approximated, and the parameter must not reappear.
    """
    import inspect

    parameters = inspect.signature(pf.transport_outcome).parameters
    assert "credential_present" not in parameters
    assert "credential_not_verifiable" in {row.outcome for row in pf.ADJACENT_OUTCOMES}


# ==========================================================================
# 4. THE FINDING: a byte-different, semantically equivalent audience is refused
# ==========================================================================

@pytest.mark.parametrize(
    "audience, normalisation",
    [
        (RESOURCE + "/", pf.NORM_TRAILING_SLASH),
        ("https://ISAAC.example.org/api/mcp", pf.NORM_SCHEME_AND_HOST_CASE),
        ("HTTPS://isaac.example.org/api/mcp", pf.NORM_SCHEME_AND_HOST_CASE),
        ("https://isaac.example.org:443/api/mcp", pf.NORM_DEFAULT_PORT),
        ("https://isaac.example.org/api/%6Dcp", pf.NORM_PERCENT_ENCODING),
        (" " + RESOURCE + " ", pf.NORM_SURROUNDING_WHITESPACE),
    ],
)
def test_a_semantically_equivalent_audience_is_reported_as_an_exact_mismatch(
    audience, normalisation
):
    """THE WHOLE FINDING, one case per normalisation an AS may legitimately apply.

    Each of these is a value RFC 8707 §2.2 permits an authorization server to put
    in ``aud`` after mapping the requested resource (quotation and section number
    from ``docs/mcp-oauth-operator-requirements-2026-08-27.md``, which already
    cites it — the RFC was not re-read here) — and ISAAC refuses every one of
    them, because its comparison is byte equality. The report must say
    ``exact_string_mismatch``, must set ``mapping_suspected``, and must name the
    normalisation, so an operator reads "your two strings differ in this one
    mechanical way" rather than "your token is invalid".
    """
    comparison = pf.audience_comparison(RESOURCE, audience)
    assert comparison.accepted is False
    assert comparison.verdict == pf.VERDICT_EXACT_STRING_MISMATCH
    assert comparison.mapping_suspected is True
    assert comparison.candidates[0].classification == "normalisation_only"
    assert comparison.candidates[0].equivalent_under == (normalisation,)


@pytest.mark.parametrize(
    "audience",
    [
        RESOURCE + "/",
        "https://ISAAC.example.org/api/mcp",
        "https://isaac.example.org:443/api/mcp",
        "https://isaac.example.org/api/%6Dcp",
    ],
)
def test_the_real_verifier_really_does_refuse_every_one_of_those(
    audience, signing_key, jwks_file
):
    """THE PREFLIGHT'S CENTRAL CLAIM, CHECKED AGAINST ``jwt.verify_access_token``.

    Without this, ``audience_comparison`` would be a story about the verifier
    rather than a report on it. Each near-miss audience is put in a **real,
    correctly-signed, unexpired token** and handed to the real verifier, which
    must reject it with ``audience_mismatch`` — and the identical token with the
    exact audience must verify. That pair is what makes "the only defect is the
    string" a measured claim.
    """
    key_set = jwks_from_document(json.loads(jwks_file.read_text(encoding="utf-8")))
    claims = {
        "iss": ISSUER,
        "sub": "isaac-mcp-client",
        "exp": NOW + 600,
        "scope": "isaac:read",
    }
    verify = lambda aud: verify_access_token(  # noqa: E731 - one expression, two calls
        keys.mint(signing_key, {**claims, "aud": aud}),
        keys=key_set,
        issuer=ISSUER,
        resource=RESOURCE,
        now=NOW,
        leeway_seconds=0,
    )

    with pytest.raises(TokenRejected) as rejected:
        verify(audience)
    assert rejected.value.code == "audience_mismatch"
    # The control: the same token shape with the exact audience verifies.
    assert verify(RESOURCE).subject == "isaac-mcp-client"


def test_an_exactly_matching_audience_is_accepted_and_no_mapping_is_suspected():
    """The negative control the finding depends on. A preflight that always said
    ``exact_string_mismatch`` would pass every test above this one."""
    comparison = pf.audience_comparison(RESOURCE, RESOURCE)
    assert comparison.accepted is True
    assert comparison.verdict == pf.VERDICT_ACCEPTED
    assert comparison.mapping_suspected is False
    assert comparison.candidates[0].equivalent_under == ()
    assert comparison.candidates[0].first_divergence_index is None
    assert comparison.candidates[0].classification == "exact"


def test_a_genuinely_different_resource_is_not_reported_as_a_mapping():
    """The distinction that makes the finding actionable: ``different_resource``
    means the token was minted for something else and refusing it is CORRECT.
    Reporting that as a mapping trap would send an operator to widen their
    audience configuration in response to a confused-deputy attempt."""
    comparison = pf.audience_comparison(RESOURCE, "https://attacker.example/api/mcp")
    assert comparison.verdict == pf.VERDICT_DIFFERENT_RESOURCE
    assert comparison.mapping_suspected is False
    assert comparison.candidates[0].equivalent_under is None
    assert comparison.candidates[0].classification == "unrelated"


def test_a_path_case_difference_is_NOT_treated_as_equivalent():
    """Scheme and host are case-insensitive; **a path is not**. Lowering a path
    would make this module report equivalences that do not exist, and an operator
    would be told to expect a token that really is for a different resource."""
    comparison = pf.audience_comparison(RESOURCE, "https://isaac.example.org/API/MCP")
    assert comparison.verdict == pf.VERDICT_DIFFERENT_RESOURCE
    assert comparison.candidates[0].equivalent_under is None


def test_one_matching_member_of_a_multi_valued_audience_is_enough():
    """``aud`` is commonly a list. ISAAC's check is membership, so one exact match
    accepts — and the other members are still reported, because an operator
    debugging a fleet needs to see that a near-miss is also in there."""
    comparison = pf.audience_comparison(RESOURCE, ["https://other.example", RESOURCE])
    assert comparison.accepted is True
    assert comparison.verdict == pf.VERDICT_ACCEPTED
    assert len(comparison.candidates) == 2
    assert [candidate.accepted for candidate in comparison.candidates] == [False, True]


@pytest.mark.parametrize(
    "claim",
    [None, [], {}, 7, [RESOURCE, 7], [RESOURCE, None], b"bytes", (RESOURCE, 7)],
)
def test_an_unusable_audience_claim_is_reported_as_unusable_and_never_as_a_pass(claim):
    """``jwt._audiences`` is the authority and is CALLED, not re-implemented, so
    the rule that one non-string member voids the WHOLE claim cannot drift. A
    filtered list would let ``[<wrong>, 1]`` read as a clean list.

    ``b"bytes"`` is in this list and is worth naming: ``bytes`` IS a ``Sequence``,
    so a shape check that only asked "is it a sequence of non-strings?" would
    iterate it into integers. ``jwt._audiences`` excludes ``bytes`` explicitly.
    """
    comparison = pf.audience_comparison(RESOURCE, claim)
    assert comparison.claim_usable is False
    assert comparison.accepted is False
    assert comparison.verdict == pf.VERDICT_NO_USABLE_AUDIENCE
    assert comparison.candidates == ()


def test_the_unusable_rule_is_the_verifiers_own_rule_and_not_a_second_copy(
    signing_key, jwks_file
):
    """A list with one non-string member is refused by the REAL verifier too, and
    with ``audience_mismatch`` rather than a malformed-claim error — which is why
    the preflight has to say "unusable claim" rather than "wrong audience"."""
    key_set = jwks_from_document(json.loads(jwks_file.read_text(encoding="utf-8")))
    token = keys.mint(
        signing_key,
        {
            "iss": ISSUER,
            "aud": [RESOURCE, 7],
            "sub": "isaac-mcp-client",
            "exp": NOW + 600,
        },
    )
    with pytest.raises(TokenRejected) as rejected:
        verify_access_token(
            token,
            keys=key_set,
            issuer=ISSUER,
            resource=RESOURCE,
            now=NOW,
            leeway_seconds=0,
        )
    assert rejected.value.code == "audience_mismatch"
    assert pf.audience_comparison(RESOURCE, [RESOURCE, 7]).accepted is False


def test_an_EMPTY_STRING_audience_is_a_usable_claim_naming_a_different_resource():
    """MEASURED, and it contradicts the obvious guess.

    ``aud: ""`` is NOT an unusable claim. ``jwt._audiences("")`` returns
    ``("",)`` — a one-member tuple — so the verifier's ``resource not in
    audiences`` compares against a present-but-empty audience and refuses with
    ``audience_mismatch``. Reporting it as "no usable audience claim" would send
    an operator to look at their authorization server's claim *serialization*
    when the actual fault is a blank ``resource`` in the client's token request.
    This test was written the other way round first and the module was right.
    """
    comparison = pf.audience_comparison(RESOURCE, "")
    assert comparison.claim_usable is True
    assert comparison.accepted is False
    assert comparison.verdict == pf.VERDICT_DIFFERENT_RESOURCE
    assert comparison.candidates[0].length == 0
    assert comparison.candidates[0].first_divergence_index == 0


def test_the_divergence_index_and_lengths_are_what_an_operator_needs():
    """The substitute for echoing: a position and two lengths.

    Asserted as exact integers rather than "is not None", because an
    implementation returning ``0`` for everything would satisfy the weaker form
    and tell an operator nothing.
    """
    comparison = pf.audience_comparison(RESOURCE, RESOURCE + "/")
    candidate = comparison.candidates[0]
    assert comparison.configured_length == len(RESOURCE)
    assert candidate.length == len(RESOURCE) + 1
    # One is a prefix of the other, so divergence is at the end of the shorter.
    assert candidate.first_divergence_index == len(RESOURCE)

    comparison = pf.audience_comparison(RESOURCE, "https://ISAAC.example.org/api/mcp")
    assert comparison.candidates[0].first_divergence_index == RESOURCE.index("isaac")


def test_the_minimal_equivalence_set_is_minimal_and_deterministic():
    """Two normalisations at once must report BOTH, and repeated calls must give
    the same tuple — the search is over subsets, and a non-deterministic answer
    would make two operators reading the same report disagree."""
    audience = "https://ISAAC.example.org:443/api/mcp/"
    first = pf.audience_comparison(RESOURCE, audience).candidates[0].equivalent_under
    assert first is not None
    assert set(first) == {
        pf.NORM_SCHEME_AND_HOST_CASE,
        pf.NORM_DEFAULT_PORT,
        pf.NORM_TRAILING_SLASH,
    }
    # Reported in NORMALISATIONS order, and stable across calls.
    assert list(first) == [name for name in pf.NORMALISATIONS if name in first]
    for _ in range(3):
        assert (
            pf.audience_comparison(RESOURCE, audience).candidates[0].equivalent_under
            == first
        )


def test_the_configured_resource_is_compared_with_whitespace_stripped_only():
    """``oauth._canonical_uri`` returns the configured value with surrounding
    whitespace stripped and NOTHING else changed, so that — and only that — is
    what the preflight may tolerate on the configuration side."""
    assert pf.audience_comparison("  " + RESOURCE + "  ", RESOURCE).accepted is True
    assert pf.audience_comparison(RESOURCE + "/", RESOURCE).accepted is False


def test_the_compared_resource_is_the_one_the_oauth_config_actually_carries(jwks_file):
    """A whole-loop check: the resource the preflight is handed is the resource the
    binding will compare, character for character. If ``oauth`` ever started
    normalising, this pins that the preflight would be comparing the wrong
    string."""
    binding = oauth_binding(jwks_file)
    assert binding.config.resource == RESOURCE
    assert pf.audience_comparison(binding.config.resource, RESOURCE).accepted is True
    assert (
        pf.audience_comparison(binding.config.resource, RESOURCE + "/").verdict
        == pf.VERDICT_EXACT_STRING_MISMATCH
    )


# ==========================================================================
# 5. Nothing secret-shaped reaches any output
# ==========================================================================

#: One distinctive value planted in every input. Chosen so a substring match
#: cannot be satisfied by ordinary prose.
PLANTED = "zQ7secretzQ7-9f3a1c8e5b2d4f6a-DO-NOT-LOG"


def _strings(node) -> list[str]:
    """Every string anywhere in a nested structure, keys included.

    A recursive walk rather than a list of fields to check: a field added to the
    report later is covered on the day it is added, which is the property a
    whitelist cannot have.
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in node.items():
            found.extend(_strings(key))
            found.extend(_strings(value))
        return found
    if isinstance(node, (list, tuple, set, frozenset)):
        found = []
        for item in node:
            found.extend(_strings(item))
        return found
    return []


def test_no_input_value_reaches_any_part_of_the_report(jwks_file):
    """THE SECRET-EXPOSURE GUARD, over every input the module takes.

    The planted value is put in the deployment variable, in **every** OAuth
    variable (including the fixture-JWKS one, which really does hold key
    material), in the configured resource, and in the token's own ``aud``. Then
    the entire report is walked — keys and values, at every depth — and the
    planted value must appear nowhere.

    MUTATION 1: adding ``"supplied_raw": raw`` to ``BindingSelection.as_dict``
    turns this RED::

        AssertionError: the report carries a planted input value:
          ['zQ7secretzQ7-9f3a1c8e5b2d4f6a-DO-NOT-LOG']

    MUTATION 2: echoing the audience — adding ``"value": value`` to
    ``AudienceCandidate.as_dict`` — turns this RED with the same message, which
    is why both directions are planted in one test rather than two.
    """
    env = {name: PLANTED for name in pf.configuration_variables()}
    report = pf.preflight_report(
        env,
        binding=oauth_binding(jwks_file),
        peer="203.0.113.7",
        origin=f"https://{PLANTED}.example",
        configured_resource=PLANTED + "-resource",
        token_audiences=[PLANTED + "-audience", PLANTED + "-resource/"],
    )
    offending = [value for value in _strings(report) if PLANTED in value]
    assert offending == [], f"the report carries a planted input value: {offending}"
    # The walk must have walked something, or the assertion above is vacuous.
    assert len(_strings(report)) > 40
    # …and it really is serializable, so a caller logging it cannot get more than
    # what was checked.
    assert PLANTED not in json.dumps(report, default=str)


def test_the_walk_can_actually_find_a_planted_value():
    """The negative control for ``_strings``. Without it, a walk that returned
    ``[]`` for everything would make the guard above pass over any leak."""
    assert PLANTED in _strings({"a": [{"b": (PLANTED,)}]})
    assert PLANTED in _strings({PLANTED: 1})


def test_a_token_and_a_key_set_cannot_reach_a_report_because_neither_is_an_argument():
    """The structural half of the same claim: there is no parameter through which
    a token, a signature or a key could arrive. ``token_audiences`` takes a
    CLAIM, not a token, and it is the only token-adjacent input — so it is
    exempted BY NAME rather than by pattern, which is what makes the scan
    meaningful: adding ``token`` or ``access_token`` would fail here.
    """
    import inspect

    names = set(inspect.signature(pf.preflight_report).parameters)
    assert "token_audiences" in names
    scanned = names - {"token_audiences"}
    for forbidden in ("token", "credential", "authorization", "jwks", "key", "secret"):
        assert not [name for name in scanned if forbidden in name.lower()], forbidden
    # The scan is non-vacuous: it really would catch one.
    assert [n for n in {"access_token"} if "token" in n]


def test_the_report_discloses_that_it_observed_no_deployment(jwks_file):
    """The honesty requirement, as a value rather than as prose in a doc: a
    consumer of this report must be able to see that it is derived from source
    and that nothing was contacted."""
    report = pf.preflight_report({}, binding=oauth_binding(jwks_file))
    assert report["provenance"] == pf.PROVENANCE
    lowered = pf.PROVENANCE.lower()
    assert "no deployment was" in lowered
    assert "operator" in lowered


# ==========================================================================
# 6. The composed report
# ==========================================================================

def test_the_report_always_carries_every_top_level_key(jwks_file):
    """Asserted as an exact key SET, so a caller branches on values rather than on
    membership, and a key removed later fails here."""
    expected = {
        "provenance",
        "selection",
        "configuration_present",
        "outcome",
        "audience",
        "decision_table",
    }
    assert set(pf.preflight_report({}).keys()) == expected
    assert set(pf.preflight_report({}, binding=oauth_binding(jwks_file)).keys()) == expected


def test_a_missing_audience_comparison_is_reported_as_missing_and_not_as_a_pass():
    """The fabrication hazard this repository has been caught by: a report whose
    ``audience`` key was ``{"accepted": true}`` when no comparison was asked for.
    It must be ``None``."""
    assert pf.preflight_report({})["audience"] is None
    asked = pf.preflight_report({}, configured_resource=RESOURCE, token_audiences=RESOURCE)
    assert asked["audience"]["accepted"] is True


def test_the_report_is_importable_and_useful_with_nothing_configured():
    """A preflight that only works on a working deployment is useless. With an
    EMPTY environment and no binding it must still answer the operator's actual
    question — which outcome am I getting, and why."""
    report = pf.preflight_report({})
    assert report["selection"]["classification"] == pf.CLASSIFICATION_UNSET
    assert report["outcome"]["status"] == 404
    assert report["outcome"]["outcome"] == pf.OUTCOME_UNMOUNTED
    assert report["configuration_present"][DEPLOYMENT_ENV] is False
    assert len(report["decision_table"]) == len(pf.DECISION_TABLE) + len(
        pf.ADJACENT_OUTCOMES
    )
    assert all(row["evidence"] for row in report["decision_table"])


def test_the_published_table_marks_which_rows_the_outcome_function_can_produce(jwks_file):
    """Every ``modelled`` row must be reachable through ``transport_outcome``, and
    no unmodelled row may be. Asserted by producing all four."""
    produced = {
        pf.transport_outcome(None).outcome,
        pf.transport_outcome(LocalLoopbackDeployment(), peer="203.0.113.7").outcome,
        pf.transport_outcome(
            LocalLoopbackDeployment(), method="GET", peer="127.0.0.1"
        ).outcome,
        pf.transport_outcome(oauth_binding(jwks_file), peer="203.0.113.7").outcome,
    }
    assert produced == {row.outcome for row in pf.DECISION_TABLE if row.modelled}
    assert produced.isdisjoint({row.outcome for row in pf.ADJACENT_OUTCOMES})
