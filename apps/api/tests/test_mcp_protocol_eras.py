"""Two things this endpoint had to get right and did not: WHO may call, and WHICH
revision they are speaking.

WHY THE TWO ARE IN ONE FILE
===========================
They arrived as one defect. ``server.py`` answered ``ping``,
``notifications/initialized`` and the unknown-method path **above** its first
``authenticate()`` call, and that was invisible for as long as the only binding
that served a route refused non-loopback peers on the socket. The OAuth binding
sets ``requires_loopback_peer=False`` — correctly, since its whole purpose is a
remote caller — and the accident that had been covering the ordering bug went
with it. So the authorization ordering and the protocol surface are the same
question asked twice: *what does this server do before it knows who is asking?*

THE NEGATIVE CONTROLS ARE THE POINT OF SECTION 1
================================================
Every case there is a method answered ``401``. Each was measured, by line
coverage over the pre-existing suite, as a path no test reached — which is how a
``200`` for an unauthenticated caller survived 327 passing tests. A parametrized
sweep over **every** method the server implements is deliberate rather than
verbose: the defect was that ONE branch returned early, so a test naming three
methods proves three methods and the next one added is uncovered again.

SECTION 2 IS THE DUAL-ERA CONTRACT
==================================
``2026-07-28`` names the two shapes — *"**Modern**: protocol versions that convey
version, identity, and capabilities as per-request metadata (revision
``2026-07-28`` and later). **Legacy**: protocol versions that establish a session
with an ``initialize`` handshake (``2025-11-25`` and earlier)."* — and permits a
server to implement both. What must not regress is the LEGACY half:
its clients have no fall-forward mechanism (the compatibility matrix records
"Legacy client / Modern server" as *"Fails"*), so every assertion about the
handshake here is a promise to a client that cannot adapt.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from isaac_api.mcp import oauth
from isaac_api.mcp.deployment import (
    DEPLOYMENT_ENV,
    LOCAL_LOOPBACK,
    LOCAL_SCOPES_ENV,
    LOCAL_SESSION_ENV,
    OAUTH_RESOURCE_SERVER,
)
from isaac_api.mcp.policy import Scope
from isaac_api.mcp.server import (
    DEPLOYMENT_UNCONFIGURED,
    ERA_LEGACY,
    ERA_MODERN,
    HEADER_MISMATCH,
    LEGACY_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    MODERN_PROTOCOL_VERSION,
    PROTOCOL_VERSION_META_KEY,
    SUPPORTED_PROTOCOL_VERSIONS,
    UNSUPPORTED_PROTOCOL_VERSION,
    protocol_era,
)
from isaac_api.mcp.transport import MCP_PATH
import mcp_oauth_keys as keys

ISSUER = "https://auth.example.invalid/application/o/isaac"
RESOURCE = "https://isaac.example.invalid/api/mcp"

LOOPBACK_PEER = ("127.0.0.1", 51999)
ANY_PEER = ("203.0.113.7", 44321)

BOTH_SCOPES = f"{Scope.READ.value},{Scope.DRAFT_WRITE.value}"

#: Every method this server implements, in either era, plus two that it does not.
#: The unknown ones are here because the unknown-method path was ALSO answering
#: before authentication, and it published the full supported-method list while
#: doing so.
EVERY_METHOD = (
    "initialize",
    "notifications/initialized",
    "ping",
    "tools/list",
    "tools/call",
    "server/discover",
    "resources/list",
    "definitely/not/a/method",
)


def build_app():
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    for name in (
        DEPLOYMENT_ENV,
        LOCAL_SCOPES_ENV,
        LOCAL_SESSION_ENV,
        *oauth.OAUTH_ENV_VARS,
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture(scope="session")
def signing_key():
    return keys.generate("isaac-signing-1", seed=keys.SEED)


@pytest.fixture()
def protected(clean, tmp_path, signing_key):
    """An app served by the OAuth binding: no peer guard, no origin guard, a token
    or nothing."""
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps(keys.jwks(signing_key)), encoding="utf-8")
    clean.setenv(oauth.RESOURCE_ENV, RESOURCE)
    clean.setenv(oauth.ISSUER_ENV, ISSUER)
    clean.setenv(oauth.TOKEN_VERIFIER_ENV, oauth.FILE_TOKEN_VERIFIER)
    clean.setenv(oauth.JWKS_FILE_ENV, str(jwks_path))
    clean.setenv(DEPLOYMENT_ENV, OAUTH_RESOURCE_SERVER)
    return TestClient(build_app(), client=ANY_PEER)


@pytest.fixture()
def loopback(clean):
    """An app served by ``local-loopback``, which authenticates a loopback peer
    with no credential — so protocol behaviour can be exercised without a token."""
    clean.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    clean.setenv(LOCAL_SCOPES_ENV, BOTH_SCOPES)
    return TestClient(build_app(), client=LOOPBACK_PEER)


def live_token(signing_key, **overrides) -> str:
    body = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "isaac-mcp-client",
        "exp": int(time.time()) + 600,
        "scope": BOTH_SCOPES.replace(",", " "),
    }
    body.update(overrides)
    return keys.mint(signing_key, body)


def post(client, message, headers=None):
    return client.post(MCP_PATH, json=message, headers=headers or {})


def request(method, *, mid=1, params=None, notification=False):
    message = {"jsonrpc": "2.0", "method": method}
    if not notification:
        message["id"] = mid
    if params is not None:
        message["params"] = params
    return message


def modern(method, *, params=None, mid=1, name=None):
    """A conforming modern request: ``_meta`` version plus the required headers."""
    body = dict(params or {})
    meta = dict(body.get("_meta") or {})
    meta[PROTOCOL_VERSION_META_KEY] = MODERN_PROTOCOL_VERSION
    body["_meta"] = meta
    headers = {
        "MCP-Protocol-Version": MODERN_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return request(method, mid=mid, params=body), headers


# ==========================================================================
# 1. Nothing is answered before the caller is known
# ==========================================================================


@pytest.mark.parametrize("method", EVERY_METHOD)
def test_no_method_answers_an_unauthenticated_caller(protected, method):
    """**THE CONTROL THAT WAS MISSING, AND ITS ABSENCE IS WHY THE DEFECT SHIPPED.**

    ``ping`` and ``notifications/initialized`` returned ``200 {"result": {}}`` to
    a caller carrying no token, and an unknown method returned the complete list
    of methods this server implements — all three above the first
    ``authenticate()`` call. Harmless under ``local-loopback``, whose socket-peer
    guard refuses a stranger first; live under this binding, which has no such
    guard by design.

    *"Note that authorization **MUST** be included in every HTTP request from
    client to server."*
    """
    response = post(protected, request(method, params={"name": "isaac_list_runs"}))
    assert response.status_code == 401, (method, response.text)
    body = response.json()
    assert body["error"]["code"] == DEPLOYMENT_UNCONFIGURED
    assert body["error"]["data"]["code"] == "token_absent"
    # OAuth 2.1 §5.3.1 / RFC 9728: the refusal carries the challenge that tells a
    # client where to go and get a token.
    assert response.headers["www-authenticate"].startswith("Bearer ")
    assert "resource_metadata=" in response.headers["www-authenticate"]


@pytest.mark.parametrize("method", EVERY_METHOD)
def test_no_method_answers_an_unauthenticated_notification_with_202_either(
    protected, method
):
    """A notification carries no ``id``, and JSON-RPC says a notification is never
    answered. That is a rule about RESULTS, not a licence to serve an
    unauthenticated request: the old code returned ``202 Accepted`` — a success
    status — to anyone who omitted the ``id``, for every method including unknown
    ones.

    The refusal envelope carries ``id: null``, which is what JSON-RPC prescribes
    for an error raised before or instead of reading an id.
    """
    response = post(protected, request(method, notification=True))
    assert response.status_code == 401, (method, response.text)
    assert response.json()["id"] is None


def test_an_unauthenticated_refusal_names_no_method_this_server_implements(protected):
    """The unknown-method path used to publish ``data.supported`` — every method
    name — to a caller who had presented nothing. A method list is not a secret,
    and it is also not something a protected resource owes a stranger; more to the
    point, its presence was the visible symptom that the branch ran before
    authentication.
    """
    response = post(protected, request("definitely/not/a/method"))
    assert response.status_code == 401
    serialized = response.text
    for method in ("tools/call", "tools/list", "server/discover", "initialize"):
        assert method not in serialized, method


@pytest.mark.parametrize("method", ["ping", "tools/list", "initialize"])
def test_the_same_methods_are_served_once_a_token_is_presented(
    protected, signing_key, method
):
    """THE ACCEPTOR, without which the sweep above proves only that a broken
    server refuses everything."""
    response = post(
        protected,
        request(method),
        headers={"Authorization": f"Bearer {live_token(signing_key)}"},
    )
    assert response.status_code == 200, response.text
    assert "error" not in response.json(), response.text


def test_an_authenticated_notification_is_still_202_with_no_body(
    protected, signing_key
):
    """The other half: authentication moved ahead of the notification rule, it did
    not replace it. A caller who authenticates and sends a notification gets the
    ``202`` the specification asks for."""
    response = post(
        protected,
        request("notifications/initialized", notification=True),
        headers={"Authorization": f"Bearer {live_token(signing_key)}"},
    )
    assert response.status_code == 202
    assert response.content == b""


def test_a_malformed_body_is_still_refused_before_the_binding_is_consulted(protected):
    """The ordering is *structure, then authorization*, and the structural checks
    are about the JSON-RPC envelope rather than about any method. They reveal
    nothing an unauthenticated caller cannot already infer from the ``415`` and
    ``406`` this transport answers, and moving them below authentication would
    make a client's framing bug indistinguishable from an expired token."""
    response = post(protected, {"jsonrpc": "1.0", "id": 1, "method": "ping"})
    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32600


# ==========================================================================
# 2. Two eras, selected the way the specification says
# ==========================================================================


def test_the_legacy_handshake_is_unchanged(loopback):
    """The promise to a client that cannot adapt. ``initialize`` answers the
    legacy revision, with the capabilities and the ``_isaac`` block it always
    has."""
    response = post(loopback, request("initialize"))
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["protocolVersion"] == LEGACY_PROTOCOL_VERSION
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "isaac-metadata-assistant"
    assert result["_isaac"]["binding"] == LOCAL_LOOPBACK


def test_a_modern_request_is_served_statelessly_with_no_handshake(loopback):
    """*"a request carrying modern per-request ``_meta`` is served statelessly
    according to this revision"*. No ``initialize`` precedes this call."""
    message, headers = modern("tools/list")
    response = post(loopback, message, headers)
    assert response.status_code == 200, response.text
    assert [t["name"] for t in response.json()["result"]["tools"]]


def test_server_discover_is_implemented_and_answers_the_revisions_it_serves(loopback):
    """*"Servers **MUST** implement ``server/discover``."* Shape from the
    revision's ``DiscoverResult``."""
    message, headers = modern("server/discover")
    response = post(loopback, message, headers)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == list(SUPPORTED_PROTOCOL_VERSIONS)
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"] == {
        "name": "isaac-metadata-assistant",
        "title": "ISAAC Metadata Assistant",
        "version": "0.1.0",
    }
    assert "no such tool exists to be asked for" in result["instructions"]


def test_discover_and_initialize_describe_the_same_server(loopback):
    """Two eras, one server. The instruction text is a single constant precisely
    so a legacy client and a modern client cannot be told different things about
    what this endpoint will and will not do."""
    legacy = post(loopback, request("initialize")).json()["result"]
    message, headers = modern("server/discover")
    modern_result = post(loopback, message, headers).json()["result"]
    assert legacy["instructions"] == modern_result["instructions"]
    assert legacy["capabilities"] == modern_result["capabilities"]
    assert legacy["_isaac"] == modern_result["_isaac"]


def test_server_discover_is_not_advertised_to_a_legacy_client(loopback):
    """It does not exist in ``2025-06-18``, so a legacy client is never told about
    it: the method list an unknown-method refusal publishes is the ERA's, not the
    union of both.

    Naming ``server/discover`` to a client speaking ``2025-06-18`` would advertise
    a method its own revision has never heard of; naming ``initialize`` to a
    modern one would send it into a handshake this revision removed.
    """
    error = post(loopback, request("nope/nope")).json()["error"]
    assert error["data"]["era"] == ERA_LEGACY
    assert "server/discover" not in error["data"]["supported"]
    assert "initialize" in error["data"]["supported"]

    message, headers = modern("nope/nope")
    modern_error = post(loopback, message, headers).json()["error"]
    assert modern_error["data"]["era"] == ERA_MODERN
    assert "server/discover" in modern_error["data"]["supported"]
    assert "initialize" not in modern_error["data"]["supported"]


def test_a_bare_server_discover_over_http_is_a_header_mismatch_not_an_unknown_method(
    loopback,
):
    """**MEASURED, AND IT IS NOT THE ANSWER THE OBVIOUS READING GIVES.**

    ``server/discover`` names itself as a modern opening — it exists in no other
    revision — so a request for it with none of the modern headers is a modern
    request that is missing them, and the revision's Server Validation rules make
    that ``400`` + ``-32020``, not ``404``/``-32601``.

    That is the RIGHT answer for the fallback too, which is why it is pinned
    rather than smoothed over: the backward-compatibility text lists
    header-validation failures alongside ``UnsupportedProtocolVersionError`` as
    the *"recognized modern JSON-RPC error"* a client should react to by
    correcting its request rather than by falling back to ``initialize``. A
    ``404`` here would have told a dual-era client that this endpoint is not a
    modern MCP server at all.
    """
    response = post(loopback, request("server/discover"))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == HEADER_MISMATCH


def test_initialize_is_not_offered_to_a_modern_client(loopback):
    """And the mirror image: ``2026-07-28`` removed the handshake."""
    message, headers = modern("tools/list")
    message["method"] = "initialize"
    headers["Mcp-Method"] = "initialize"
    response = post(loopback, message, headers)
    # `initialize` selects LEGACY semantics unconditionally, per the revision's
    # own dual-era rule — so it is answered, not refused. What must not happen is
    # that it is answered with a MODERN error; see the next test.
    assert response.status_code == 200, response.text
    assert response.json()["result"]["protocolVersion"] == LEGACY_PROTOCOL_VERSION


# --- the version errors, and the one place they must NOT appear --------------


@pytest.mark.parametrize("carrier", ["header", "meta"])
def test_an_unsupported_version_gets_the_real_unsupported_version_error(
    loopback, carrier
):
    """*"it **MUST** respond with an ``UnsupportedProtocolVersionError`` listing
    the versions it does support"* — code ``-32022``, message
    ``"Unsupported protocol version"``, ``data.supported`` and ``data.requested``.

    Both carriers, because the revision states the requirement twice — once for
    the ``_meta`` field and once for the ``MCP-Protocol-Version`` header — and a
    server that enforced only the header would accept a body declaring anything.
    """
    if carrier == "header":
        message = request("ping")
        headers = {"MCP-Protocol-Version": "1900-01-01", "Mcp-Method": "ping"}
    else:
        message = request(
            "ping", params={"_meta": {PROTOCOL_VERSION_META_KEY: "1900-01-01"}}
        )
        headers = {}
    response = post(loopback, message, headers)
    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": UNSUPPORTED_PROTOCOL_VERSION,
        "message": "Unsupported protocol version",
        "data": {
            "supported": list(SUPPORTED_PROTOCOL_VERSIONS),
            "requested": "1900-01-01",
        },
    }


@pytest.mark.parametrize(
    "declared",
    [
        # The shape a copy-paste accident produces: a bearer token pasted into
        # the version header. Long, and not a version.
        "eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCJ9." + "A" * 400,
        # Non-printable: a header value can carry a tab.
        "2026-07-28\tinjected",
        # Exactly one character past the bound.
        "x" * 65,
    ],
)
def test_the_echoed_version_is_bounded_rather_than_reflected(loopback, declared):
    """**THE ONE PLACE CALLER TEXT REACHES A RESPONSE BODY IN THIS SURFACE.**

    ``data.requested`` is required by the specification's error shape, so it
    cannot be dropped — a client with two declarations needs to know which one was
    rejected. What is dropped is the assumption that the value IS a version: a
    caller can put anything in ``MCP-Protocol-Version``, and the first parameter
    here is the plausible accident rather than a contrived one.

    Reflecting it discloses nothing to anyone new; what it does is make this the
    single branch that breaks the rule the rest of the package holds —
    ``transport._refuse`` never interpolates caller text, ``jwt.py`` never
    interpolates token material, and the peer-address refusal deliberately does
    not name the address it saw. One exception is how that habit is lost.

    A real version is unchanged by the bound, which the negative control below
    asserts: ``1900-01-01`` comes back verbatim.
    """
    response = post(loopback, request("ping"), {"MCP-Protocol-Version": declared})
    assert response.status_code == 400
    data = response.json()["error"]["data"]
    assert data["requested"] == "<not a protocol version>"
    assert declared[:64] not in response.text
    assert data["supported"] == list(SUPPORTED_PROTOCOL_VERSIONS)

    # The control: an unsupported value that IS version-shaped is echoed exactly,
    # because a bound that mangled real input would be useless to a client.
    exact = post(loopback, request("ping"), {"MCP-Protocol-Version": "1900-01-01"})
    assert exact.json()["error"]["data"]["requested"] == "1900-01-01"


def test_the_legacy_handshake_never_produces_the_modern_error(loopback):
    """**THE ASSERTION THAT PROTECTS THE FALLBACK, AND IT IS EASY TO BREAK.**

    A dual-era client detects a legacy server by getting a ``4xx`` *without* a
    recognized modern error body and then falling back to ``initialize``. If this
    server answered a handshake declaring an old ``params.protocolVersion`` with
    ``-32022``, the client would read that as *"a modern server that cannot serve
    my version"* and retry the modern path forever instead of completing the
    handshake this server is perfectly able to serve.

    So the legacy negotiation field is deliberately never read by the version
    check: a handshake is answered with this server's legacy revision, and the
    client decides what to do about it — which is what ``2025-06-18``'s own
    negotiation rule says.
    """
    response = post(
        loopback,
        request("initialize", params={"protocolVersion": "2024-11-05"}),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    assert body["result"]["protocolVersion"] == LEGACY_PROTOCOL_VERSION


def test_a_meta_protocol_version_that_is_not_a_string_is_an_invalid_request(loopback):
    """``data.requested`` is a version string. A non-string declaration has no
    version to report, so it is a malformed request rather than an unsupported
    one — reported as ``-32602`` rather than being coerced into the version error
    with a fabricated value."""
    response = post(
        loopback, request("ping", params={"_meta": {PROTOCOL_VERSION_META_KEY: 20260728}})
    )
    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32602


# --- the modern header rules --------------------------------------------------


def test_a_modern_request_without_the_protocol_version_header_is_a_header_mismatch(
    loopback,
):
    """*"Every POST request to the MCP endpoint **MUST** include an
    ``MCP-Protocol-Version`` header."* and *"A required standard header
    (``MCP-Protocol-Version``, ``Mcp-Method``, ``Mcp-Name``) is missing"* is listed
    among the validation-failure conditions, which are ``400`` + ``-32020``."""
    message = request(
        "ping", params={"_meta": {PROTOCOL_VERSION_META_KEY: MODERN_PROTOCOL_VERSION}}
    )
    response = post(loopback, message, {"Mcp-Method": "ping"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == HEADER_MISMATCH


def test_a_header_that_disagrees_with_the_body_is_refused(loopback):
    """*"The header value **MUST** match the
    ``io.modelcontextprotocol/protocolVersion`` field carried in the request
    body's ``_meta``. If the values do not match, the server **MUST** reject the
    request with ``400 Bad Request`` and a ``HeaderMismatch`` JSON-RPC error."*

    The reason it is a MUST rather than a nicety is in the specification too:
    *"This prevents potential security vulnerabilities when different components
    in the network rely on different sources of truth (e.g., a load balancer
    routing on the header value while the MCP server executes based on the body
    value)."* Both values here are ones this server SUPPORTS — the refusal is
    about the disagreement, not about either version.
    """
    message = request(
        "ping", params={"_meta": {PROTOCOL_VERSION_META_KEY: MODERN_PROTOCOL_VERSION}}
    )
    headers = {
        "MCP-Protocol-Version": LEGACY_PROTOCOL_VERSION,
        "Mcp-Method": "ping",
    }
    response = post(loopback, message, headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == HEADER_MISMATCH


@pytest.mark.parametrize("sent", [None, "tools/list"])
def test_a_missing_or_wrong_mcp_method_header_is_refused(loopback, sent):
    """``Mcp-Method`` is REQUIRED for all requests and its source field is
    ``method``. Absent and disagreeing are the same failure with the same code, so
    both are asserted — an implementation that checks equality without checking
    presence passes on ``None == None``."""
    message, headers = modern("ping")
    if sent is None:
        headers.pop("Mcp-Method")
    else:
        headers["Mcp-Method"] = sent
    response = post(loopback, message, headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == HEADER_MISMATCH


@pytest.mark.parametrize("sent", [None, "isaac_get_run"])
def test_a_missing_or_wrong_mcp_name_header_on_a_tool_call_is_refused(loopback, sent):
    """``Mcp-Name`` is REQUIRED for ``tools/call``, sourced from ``params.name``."""
    params = {"name": "isaac_list_experiments", "arguments": {}}
    message, headers = modern("tools/call", params=params, name=sent)
    if sent is None:
        headers.pop("Mcp-Name", None)
    response = post(loopback, message, headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == HEADER_MISMATCH


def test_a_conforming_tool_call_carrying_all_three_headers_is_served(loopback):
    params = {"name": "isaac_list_experiments", "arguments": {}}
    message, headers = modern(
        "tools/call", params=params, name="isaac_list_experiments"
    )
    response = post(loopback, message, headers)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["isError"] is False


def test_a_base64_sentinel_mcp_name_is_decoded_before_it_is_compared(loopback):
    """*"Servers and intermediaries that need to inspect these values **MUST**
    decode them accordingly. In particular, servers **MUST** decode an encoded
    ``Mcp-Name`` … value before comparing it to the corresponding request body
    value during Server Validation."*

    A server that compares the raw header would reject every client that used the
    encoding correctly.
    """
    name = "isaac_list_experiments"
    encoded = "=?base64?" + base64.b64encode(name.encode()).decode() + "?="
    params = {"name": name, "arguments": {}}
    message, headers = modern("tools/call", params=params, name=encoded)
    response = post(loopback, message, headers)
    assert response.status_code == 200, response.text

    # And a sentinel whose payload is not decodable is a validation failure rather
    # than a value compared literally.
    message, headers = modern("tools/call", params=params, name="=?base64?!!!!?=")
    assert post(loopback, message, headers).status_code == 400


def test_the_legacy_path_is_not_subject_to_the_modern_header_rules(loopback):
    """The rules are the modern revision's, and a ``2025-06-18`` client sends none
    of those headers on ``initialize``. Applying them to the legacy era would
    break every client this endpoint serves today, which is the opposite of what
    dual-era support is for."""
    for message in (
        request("initialize"),
        request("ping"),
        request("tools/list"),
    ):
        assert post(loopback, message).status_code == 200, message["method"]


# --- the status the modern transport binding asks for ------------------------


def test_an_unknown_modern_method_is_404_and_an_unknown_legacy_one_is_200(loopback):
    """*"If the server does not implement the requested RPC method, it **MUST**
    respond with ``404 Not Found`` and a JSON-RPC error with code ``-32601``
    (``Method not found``). The JSON-RPC error body distinguishes this case from a
    ``404`` returned by a legacy HTTP+SSE server that does not host the modern MCP
    endpoint."*

    That is a rule of the ``2026-07-28`` transport binding. The legacy era keeps
    the ``200`` it has always returned: a JSON-RPC error means the request was
    transported fine and the application refused it, and a legacy client's own
    revision does not ask for anything else.
    """
    message, headers = modern("definitely/not/a/method")
    modern_response = post(loopback, message, headers)
    assert modern_response.status_code == 404
    assert modern_response.json()["error"]["code"] == METHOD_NOT_FOUND
    assert modern_response.json()["error"]["data"]["era"] == ERA_MODERN

    legacy_response = post(loopback, request("definitely/not/a/method"))
    assert legacy_response.status_code == 200
    assert legacy_response.json()["error"]["code"] == METHOD_NOT_FOUND
    assert legacy_response.json()["error"]["data"]["era"] == ERA_LEGACY


# ==========================================================================
# 3. Era selection, as a pure function
# ==========================================================================


@pytest.mark.parametrize(
    ("method", "params", "headers", "expected"),
    [
        # `initialize` selects legacy, unconditionally — even carrying modern
        # `_meta`, and even with a modern header. That is the sentence the whole
        # fallback rests on.
        ("initialize", {}, {}, ERA_LEGACY),
        (
            "initialize",
            {"_meta": {PROTOCOL_VERSION_META_KEY: MODERN_PROTOCOL_VERSION}},
            {"mcp-protocol-version": MODERN_PROTOCOL_VERSION},
            ERA_LEGACY,
        ),
        # `server/discover` exists only in the modern revision.
        ("server/discover", {}, {}, ERA_MODERN),
        # Per-request `_meta` is a modern opening whatever the version says…
        ("ping", {"_meta": {PROTOCOL_VERSION_META_KEY: "1900-01-01"}}, {}, ERA_MODERN),
        # …and so is a header naming a modern revision.
        ("ping", {}, {"mcp-protocol-version": MODERN_PROTOCOL_VERSION}, ERA_MODERN),
        # A header naming the LEGACY revision is not.
        ("ping", {}, {"mcp-protocol-version": LEGACY_PROTOCOL_VERSION}, ERA_LEGACY),
        # A `_meta` with no protocol version is not a modern opening: `_meta` is a
        # general-purpose extension point in both eras.
        ("ping", {"_meta": {"vendor/x": 1}}, {}, ERA_LEGACY),
        # No signal at all defaults to legacy, which is what this server did
        # before it was dual-era.
        ("tools/call", {}, {}, ERA_LEGACY),
        # No headers at all — the in-process case — reads `_meta` alone.
        ("ping", {}, None, ERA_LEGACY),
        (
            "tools/list",
            {"_meta": {PROTOCOL_VERSION_META_KEY: MODERN_PROTOCOL_VERSION}},
            None,
            ERA_MODERN,
        ),
    ],
)
def test_protocol_era_is_decided_by_how_the_client_opens(
    method, params, headers, expected
):
    """*"A dual-era server selects its behavior from how the client opens."*

    Pure and public, because ``transport.py`` reads it for the ``404``/``200``
    decision and ``server.py`` reads it for dispatch. Two layers computing the era
    from two rules is how those answers drift apart.
    """
    assert protocol_era(method, params, headers) == expected


def test_the_two_layers_read_one_era_function(loopback):
    """A mutation guard rather than a behaviour test. If ``transport.py`` grew its
    own copy of the era rule, this pair would keep passing while the pair in
    ``test_an_unknown_modern_method_is_404…`` would not — so the assertion here is
    the IDENTITY of the function object the transport imported.
    """
    from isaac_api.mcp import server as server_module
    from isaac_api.mcp import transport as transport_module

    assert transport_module.protocol_era is server_module.protocol_era
