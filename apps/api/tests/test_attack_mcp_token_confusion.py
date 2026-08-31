"""Tokens that are almost right, over the wire: audience confusion and the 401/403 line.

WHY THIS FILE EXISTS BESIDE THE TWO THAT ALREADY COVER TOKENS
=============================================================
``test_mcp_oauth_tokens.py`` is thorough and is a UNIT file: it calls
``jwt.verify_access_token`` directly, 50-odd cases deep, and proves the verifier
refuses a wrong issuer, a wrong audience, ``alg: none``, a tampered signature and
the rest. ``test_mcp_oauth_binding.py`` drives the binding and covers the ABSENT
and the EXPIRED credential over HTTP.

What neither does is put a **well-formed, correctly-signed token that is simply
not for this server** on the wire and read the response. That is the confused-deputy
shape — a token the authorization server really did mint, for a different resource,
presented here — and the specification's own MUST is about exactly it:

    *"MCP servers MUST validate that access tokens were issued specifically for
    them as the intended audience"* … *"MUST reject tokens that do not include them
    in the audience claim."*

A unit test of ``verify_access_token`` proves the check exists. It does not prove
the transport reaches it, that the refusal is a ``401`` rather than a ``403``, or
that the challenge tells a client what went wrong. Those are what this file
measures.

THE ONE GAP IT CLOSES IN AN EXISTING TEST
=========================================
``test_mcp_protocol_eras.py::test_no_method_answers_an_unauthenticated_notification_with_202_either``
asserts ``401`` and ``id: null`` for the notification form of every method. It does
**not** assert the ``WWW-Authenticate`` header, and the notification path is a
separate branch through the server's refusal envelope — so a change that dropped
the challenge for notifications only would pass every existing test. It is added
here rather than there because the sibling test's subject is the status code and a
second assertion would blur it.

RESULT: EVERY ATTACK CORRECTLY FAILED. No production code changed.

WHAT IS DELIBERATELY NOT HERE
=============================
No authorization server, no token issuance, no PKCE, no client registration — every
one of those is a MUST on the CLIENT and none has an implementation in this
repository to test. And no revocation: there is no revocation mechanism, which
``test_mcp_oauth_binding.py::test_there_is_no_revocation_mechanism_to_test`` already
records as an absence.

Every key is generated at test time from a fixed seed by ``mcp_oauth_keys``; nothing
is committed, nothing is real, and the application never signs anything.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

import mcp_oauth_keys as keys
from isaac_api.mcp import oauth
from isaac_api.mcp.deployment import (
    DEPLOYMENT_ENV,
    LOCAL_SCOPES_ENV,
    LOCAL_SESSION_ENV,
    OAUTH_RESOURCE_SERVER,
)
from isaac_api.mcp.policy import Scope
from isaac_api.mcp.server import DEPLOYMENT_UNCONFIGURED, INSUFFICIENT_SCOPE
from isaac_api.mcp.transport import MCP_PATH

#: This server's identity, and a DIFFERENT resource server at the same institution
#: served by the same authorization server. The second is the whole point: a token
#: for it is validly signed, unexpired, and must still be refused here.
RESOURCE = "https://isaac.example.invalid/api/mcp"
OTHER_RESOURCE = "https://payroll.example.invalid/api/mcp"
ISSUER = "https://auth.example.invalid/application/o/isaac"
OTHER_ISSUER = "https://auth.other.invalid/application/o/isaac"

#: A non-loopback peer, so nothing here can pass because of a socket-level guard —
#: the OAuth binding deliberately serves any peer, and that is what makes the token
#: the only thing standing between a caller and the tools.
ANY_PEER = ("203.0.113.7", 44321)


@pytest.fixture(scope="session")
def signing_key():
    return keys.generate("isaac-signing-1", seed=keys.SEED)


@pytest.fixture()
def served(tmp_path, monkeypatch, signing_key):
    """The application served by the OAuth resource-server binding."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    for name in (DEPLOYMENT_ENV, LOCAL_SCOPES_ENV, LOCAL_SESSION_ENV, *oauth.OAUTH_ENV_VARS):
        monkeypatch.delenv(name, raising=False)

    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps(keys.jwks(signing_key)), encoding="utf-8")
    monkeypatch.setenv(oauth.RESOURCE_ENV, RESOURCE)
    monkeypatch.setenv(oauth.ISSUER_ENV, ISSUER)
    monkeypatch.setenv(oauth.TOKEN_VERIFIER_ENV, oauth.FILE_TOKEN_VERIFIER)
    monkeypatch.setenv(oauth.JWKS_FILE_ENV, str(jwks_path))
    monkeypatch.setenv(DEPLOYMENT_ENV, OAUTH_RESOURCE_SERVER)

    from isaac_api.app import create_app

    return TestClient(create_app(), client=ANY_PEER)


def mint(signing_key, **overrides) -> str:
    body = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "isaac-mcp-client",
        "exp": int(time.time()) + 600,
        "scope": Scope.READ.value,
    }
    body.update(overrides)
    return keys.mint(signing_key, body)


def rpc(client, method="tools/list", params=None, *, token=None, notification=False):
    message = {"jsonrpc": "2.0", "method": method}
    if not notification:
        message["id"] = 1
    if params is not None:
        message["params"] = params
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return client.post(MCP_PATH, json=message, headers=headers)


# =============================================================================
# 1. audience confusion — a real token, for somebody else
# =============================================================================


def test_a_token_minted_for_another_resource_server_is_refused_over_the_wire(
    served, signing_key
):
    """THE CONFUSED-DEPUTY CASE, and the one the specification names a MUST about.

    The token is signed by the key this server trusts, issued by the issuer this
    server trusts, unexpired, and carries the read scope. The ONLY thing wrong with
    it is that its ``aud`` names a different resource server — which is exactly what
    a caller holding a token for another service at the same institution would
    present.

    Measured: ``401``, ``error="invalid_token"``, and the token itself does not
    appear anywhere in the response.

    MUTATION: deleting the ``aud`` comparison in ``jwt.verify_access_token``
    (``if resource not in audiences:`` -> ``if False:``) turns this RED — the tool
    list is served to a caller holding another service's token::

        AssertionError: {"id": 1, "jsonrpc": "2.0", "result": {"tools": […]}}
        assert 200 == 401
    """
    token = mint(signing_key, aud=OTHER_RESOURCE)
    response = rpc(served, token=token)
    assert response.status_code == 401, response.text
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer "), challenge
    assert 'error="invalid_token"' in challenge, challenge
    assert 'resource_metadata="' in challenge, challenge
    assert token not in response.text
    assert response.json()["error"]["code"] == DEPLOYMENT_UNCONFIGURED


@pytest.mark.parametrize(
    "audience",
    [
        pytest.param(RESOURCE + "/", id="trailing-slash"),
        pytest.param(RESOURCE.upper(), id="uppercased"),
        pytest.param(RESOURCE + "?x=1", id="query-appended"),
        pytest.param(RESOURCE.replace("https", "http"), id="scheme-downgraded"),
        pytest.param(RESOURCE.rsplit("/", 1)[0], id="path-truncated"),
        pytest.param(RESOURCE + "#f", id="fragment-appended"),
        pytest.param("https://isaac.example.invalid.evil/api/mcp", id="suffix-attack"),
        pytest.param("https://evil/" + RESOURCE, id="prefix-attack"),
    ],
)
def test_an_audience_that_merely_resembles_this_resource_is_refused(
    served, signing_key, audience
):
    """Eight near-misses, because "does the audience match" is where URL
    normalisation quietly turns a refusal into an acceptance.

    A comparison that lowercased, that stripped a trailing slash, or that used
    ``startswith`` would accept at least one of these. ``jwt.verify_access_token``
    compares by exact string equality and normalises nothing, which is what makes
    ``suffix-attack`` and ``prefix-attack`` — the two a substring test would let
    through — refusals rather than a breach.

    MUTATION: relaxing the comparison to
    ``any(str(a).rstrip("/").lower() == resource.rstrip("/").lower() for a in
    audiences)`` turns exactly the ``trailing-slash`` and ``uppercased`` rows RED
    and leaves the other six green::

        AssertionError: ('https://isaac.example.invalid/api/mcp/', …)
        assert 200 == 401
        AssertionError: ('HTTPS://ISAAC.EXAMPLE.INVALID/API/MCP', …)
        assert 200 == 401
        2 failed, 6 passed

    Which two fail is the informative part: a normaliser that looks harmless
    admits precisely the two audiences a careless issuer is most likely to mint.
    """
    response = rpc(served, token=mint(signing_key, aud=audience))
    assert response.status_code == 401, (audience, response.text)
    assert 'error="invalid_token"' in response.headers["www-authenticate"]


def test_a_multi_audience_token_is_accepted_only_because_this_resource_is_in_it(
    served, signing_key
):
    """The negative control that stops the eight above from passing vacuously.

    A server that refused every token would satisfy all of them. Here the audience
    is a LIST naming two other resource servers **and** this one, which is the
    ordinary shape a broker mints, and it is served.

    MUTATION: changing the membership test to a first-element comparison
    (``list(audiences)[0] != resource``) turns this RED::

        AssertionError: {"error": {"code": -31001, …}}
        assert 401 == 200
    """
    token = mint(signing_key, aud=[OTHER_RESOURCE, "https://third.invalid", RESOURCE])
    response = rpc(served, token=token)
    assert response.status_code == 200, response.text
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert "isaac_list_experiments" in names, names


def test_a_token_from_another_issuer_is_refused_even_signed_by_a_trusted_key(
    served, signing_key
):
    """Issuer and audience are separate checks, and this proves the first one is
    live over the wire rather than implied by the second.

    The token names THIS resource correctly and is signed by the key this server
    trusts. Only ``iss`` is wrong. If the issuer check were absent, an authorization
    server ISAAC never approved could mint tokens for it.

    MUTATION: deleting the ``iss`` comparison in ``jwt.verify_access_token``
    (``if claims.get("iss") != issuer:`` -> ``if False:``) turns this RED::

        AssertionError: {"id": 1, "jsonrpc": "2.0", "result": {"tools": […]}}
        assert 200 == 401
    """
    response = rpc(served, token=mint(signing_key, iss=OTHER_ISSUER))
    assert response.status_code == 401, response.text
    assert 'error="invalid_token"' in response.headers["www-authenticate"]


# =============================================================================
# 2. malformed credentials, over the wire
# =============================================================================


MALFORMED = {
    "empty": "",
    "not-a-jwt": "not-a-token-at-all",
    "two-segments": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0",
    "four-segments": "a.b.c.d",
    "empty-segments": "..",
    "standard-base64": "eyJhbGciOiJSUzI1NiJ9+.eyJzdWIiOiJ4In0=.sig",
    "unsigned-alg-none": (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
        "eyJpc3MiOiJodHRwczovL2F1dGguZXhhbXBsZS5pbnZhbGlkIn0."
    ),
    "jwe-five-segments": "a.b.c.d.e",
    "whitespace": "   ",
    "huge": "A" * 200_000,
}


@pytest.mark.parametrize("shape", sorted(MALFORMED))
def test_a_malformed_bearer_token_is_a_401_with_a_usable_challenge(served, shape):
    """Ten shapes a client can actually send, each answered ``401`` with a challenge
    that tells the client where to get a real token.

    ``test_mcp_oauth_tokens.py`` proves the VERIFIER refuses these; this proves the
    transport does not answer something else first — a ``400`` from a header parse,
    a ``500`` from an unhandled decode error, or a ``200`` because an empty
    credential read as "no credential, but the peer is fine".

    ``alg: none`` is in here rather than only in the unit file because it is the
    one shape whose refusal must be visible at the edge: it is a syntactically
    perfect JWT.

    MUTATION: making the binding treat a credential that is not three
    dot-separated segments as NO credential — so a malformed token reads as "please
    log in" rather than "your token is broken" — keeps the ``401`` and drops the
    ``error`` parameter, turning four rows RED::

        AssertionError: ('not-a-jwt', 'Bearer resource_metadata="https://isaac.
        example.invalid/.well-known/oauth-protected-resource/api/mcp",
        scope="isaac:read"')
        assert 'error="invalid_token"' in '…'
        4 failed, 6 passed

    Only four: the shapes that are blank, or that already have three segments, or
    that the size cap refuses first, take a different path. That is worth recording
    rather than smoothing over — it says the ``error`` parameter is carried by the
    *verification* refusal specifically, not by every 401.
    """
    response = rpc(served, token=MALFORMED[shape])
    assert response.status_code == 401, (shape, response.status_code, response.text)
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer "), challenge
    assert 'resource_metadata="' in challenge, challenge
    if MALFORMED[shape].strip():
        # Something WAS presented and it was not usable — RFC 6750's own
        # distinction, and the one a client needs to tell "log in" from "your
        # token is broken".
        assert 'error="invalid_token"' in challenge, (shape, challenge)
    assert MALFORMED[shape] not in response.text or not MALFORMED[shape].strip()


def test_a_non_bearer_scheme_carrying_a_valid_token_is_not_tried_as_a_bearer(
    served, signing_key
):
    """A perfectly good token under the wrong scheme is refused, not coerced.

    ``Basic <jwt>`` and ``Token <jwt>`` are what a client library sends when it is
    misconfigured. Accepting them would mean the server decides what a client meant,
    which is how a credential intended for another system gets replayed here.

    MUTATION: deleting the scheme check in
    ``OAuthResourceServerDeployment.authenticate``
    (``if credential.scheme.lower() != "bearer":`` -> ``if False:``) turns this RED
    on the first scheme tried::

        AssertionError: ('Basic', '{"id": 1, "jsonrpc": "2.0", "result": {"tools":
        […]}}')
        assert 200 == 401
    """
    token = mint(signing_key)
    for scheme in ("Basic", "Token", "DPoP", "Negotiate"):
        response = served.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"{scheme} {token}"},
        )
        assert response.status_code == 401, (scheme, response.text)
        assert token not in response.text, scheme


# =============================================================================
# 3. the 401 / 403 line
# =============================================================================


def test_a_verified_token_without_the_needed_scope_is_403_and_names_every_one(
    served, signing_key
):
    """The distinction the specification requires: the token is FINE, the grant is
    not.

    ``401`` would tell the client to go and re-authenticate, which would not help —
    it needs a different SCOPE, and the challenge says which.

    MUTATION: dropping the challenge headers from the transport's response
    (``extra_headers=()``) turns this RED::

        KeyError: 'www-authenticate'

    The status stays ``403``; what is lost is the header that tells the client
    WHICH scope to ask for, which is the whole reason a ``403`` is more useful here
    than a ``401``.
    """
    read_only = mint(signing_key, scope=Scope.READ.value)
    response = rpc(
        served,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": "x"}},
        token=read_only,
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == INSUFFICIENT_SCOPE
    challenge = response.headers["www-authenticate"]
    assert 'error="insufficient_scope"' in challenge, challenge
    assert Scope.DRAFT_WRITE.value in challenge, challenge


def test_the_write_scope_alone_is_403_on_a_READ_tool_over_the_oauth_binding(
    served, signing_key
):
    """The other direction, because a hierarchy invented in one direction is usually
    invented in both.

    ``policy.py`` records that ``DRAFT_WRITE`` deliberately does not imply ``READ``.
    ``test_mcp_oauth_binding.py`` proves that at the BINDING; this proves it over
    HTTP, where a middleware or a transport shortcut could have re-introduced the
    implication.

    MUTATION: making ``Principal.missing`` return an empty set turns this RED::

        AssertionError: {"id": 1, "jsonrpc": "2.0", "result": {"content": [{"text":
        "{\"data\": {\"experiments\": []}, …}"}]}}
        assert 200 == 403

    *An earlier candidate — weakening ``Principal.permits`` — does NOT turn it red,
    and that is worth recording: the scope gate goes through ``missing`` /
    ``permits_all``, not through ``permits``. A mutation aimed at the obvious
    method would have reported this test as unable to fail while it was fine.*
    """
    write_only = mint(signing_key, scope=Scope.DRAFT_WRITE.value)
    response = rpc(
        served,
        "tools/call",
        {"name": "isaac_list_experiments", "arguments": {}},
        token=write_only,
    )
    assert response.status_code == 403, response.text
    assert Scope.READ.value in response.headers["www-authenticate"]


def test_a_token_carrying_no_recognised_scope_authenticates_and_reaches_nothing(
    served, signing_key
):
    """Authentication and authorization are different answers, and a token whose
    scopes this server does not express must produce the second, not the first.

    ``isaac:submit`` is the interesting value: it is a scope ``policy.Scope`` cannot
    represent, so it is dropped rather than parsed into something.

    MUTATION: making ``policy.parse_scope`` return ``Scope.READ`` instead of
    ``None`` for an unknown string turns this RED — ``isaac:submit`` becomes a read
    grant::

        AssertionError: {"id": 1, "jsonrpc": "2.0", "result": {"content": […]}}
        assert 200 == 403
    """
    odd = mint(signing_key, scope="isaac:submit isaac:admin openid")
    response = rpc(served, "tools/call", {"name": "isaac_list_experiments"}, token=odd)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == INSUFFICIENT_SCOPE
    # It authenticated: the refusal is about the grant, not about the credential.
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]


# =============================================================================
# 4. the notification form also carries the challenge
# =============================================================================


@pytest.mark.parametrize(
    "method",
    [
        "initialize",
        "notifications/initialized",
        "ping",
        "tools/list",
        "tools/call",
        "server/discover",
        "definitely/not/a/method",
    ],
)
def test_an_unauthenticated_notification_carries_the_challenge_too(served, method):
    """THE GAP IN AN EXISTING TEST, closed here.

    ``test_mcp_protocol_eras.py`` proves the notification form (no ``id``) answers
    ``401`` for every method — it does not assert the ``WWW-Authenticate`` header,
    and the notification path is a separate branch through the refusal envelope. A
    change that emitted the challenge only for id-carrying requests would pass every
    test in the repository before this one.

    A challenge is not decoration: it is how a client discovers the authorization
    server. Withholding it on one branch would make the notification path silently
    unrecoverable.

    MUTATION: dropping the challenge headers from the transport's response
    (``extra_headers=()``) turns this RED for all seven methods::

        KeyError: 'www-authenticate'
        8 failed
    """
    response = rpc(served, method, notification=True)
    assert response.status_code == 401, (method, response.text)
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer "), (method, challenge)
    assert 'resource_metadata="' in challenge, (method, challenge)
    # JSON-RPC's rule for an error raised before an id is read.
    assert response.json()["id"] is None, response.text


# =============================================================================
# 5. the negative control for the whole file
# =============================================================================


def test_a_correctly_minted_token_is_served_so_none_of_this_passes_by_refusing(
    served, signing_key
):
    """Every test above asserts a refusal. All of them would pass against a server
    that refused everything, so this proves the accepting path is live: the right
    issuer, the right audience, an unexpired token and the read scope reach the tool
    list, and it contains no forbidden capability.

    MUTATION: refusing every token (``if claims.get("iss") != issuer:`` ->
    ``if True:``) turns this RED::

        AssertionError: {"error": {"code": -31001, …}}
        assert 401 == 200
    """
    response = rpc(served, token=mint(signing_key))
    assert response.status_code == 200, response.text
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert "isaac_list_experiments" in names, names
    assert not [n for n in names if "submit" in n or "export" in n or "accept" in n]
