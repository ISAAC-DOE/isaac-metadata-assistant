"""The OAuth resource-server binding, end to end and over real HTTP.

THE FIRST SECTION IS THE MOST IMPORTANT ONE AND IS NOT ABOUT OAUTH AT ALL. It
asserts that a deployment which did not ask for any of this is **byte-identical
to what shipped before it existed**: no MCP route, no metadata route, nothing
added to the OpenAPI document, no OAuth code executed. A feature that is disabled
by default is only disabled if that is asserted rather than intended, and this
file's authorization to exist rests on it.

After that: configuration is fail-closed in every direction, the ``401``/``403``
distinction the specification requires is made and carries the challenges it
requires, a token in the query string is refused rather than ignored, and a
verified token becomes a SERVICE principal that can never author anything.

WHAT IS DELIBERATELY NOT TESTED HERE, BECAUSE IT IS NOT BUILT
============================================================
No authorization server, no token issuance, no client registration, no PKCE, no
redirect handling. ISAAC is the resource server; every one of those is a MUST on
the CLIENT and none of them has an implementation in this repository to test.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from isaac_api import identity
from isaac_api.mcp import oauth
from isaac_api.mcp.deployment import (
    DEPLOYMENT_ENV,
    LOCAL_LOOPBACK,
    LOCAL_SCOPES_ENV,
    LOCAL_SESSION_ENV,
    OAUTH_RESOURCE_SERVER,
    RESERVED_BINDING_NAMES,
    Credential,
    DeploymentRefused,
    UnconfiguredDeployment,
    resolve_binding,
)
from isaac_api.mcp.jwt import JsonWebKeySet, jwks_from_document
from isaac_api.mcp.policy import Scope
from isaac_api.mcp.server import DEPLOYMENT_UNCONFIGURED, INSUFFICIENT_SCOPE
from isaac_api.mcp.transport import MCP_PATH, metadata_routes_or_none
import mcp_oauth_keys as keys

ISSUER = "https://auth.example.invalid/application/o/isaac"
RESOURCE = "https://isaac.example.invalid/api/mcp"
NOW = 1_800_000_000

#: Every variable this feature reads, cleared before each test so no case can
#: pass because of a value another one set.
OAUTH_VARS = oauth.OAUTH_ENV_VARS

#: TestClient's default peer is ``("testclient", 50000)``, which is not an
#: address. The OAuth binding does not care — it refuses no peer, on purpose —
#: and passing a real one anyway keeps the difference from `local-loopback`
#: attributable to the binding rather than to the fixture.
ANY_PEER = ("203.0.113.7", 44321)


@pytest.fixture(scope="session")
def signing_key():
    return keys.generate("isaac-signing-1", seed=keys.SEED)


@pytest.fixture()
def jwks_file(tmp_path, signing_key):
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps(keys.jwks(signing_key)), encoding="utf-8")
    return path


@pytest.fixture()
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    for name in (DEPLOYMENT_ENV, LOCAL_SCOPES_ENV, LOCAL_SESSION_ENV, *OAUTH_VARS):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def env(jwks_file, **overrides) -> dict:
    values = {
        oauth.RESOURCE_ENV: RESOURCE,
        oauth.ISSUER_ENV: ISSUER,
        oauth.TOKEN_VERIFIER_ENV: oauth.FILE_TOKEN_VERIFIER,
        oauth.JWKS_FILE_ENV: str(jwks_file),
    }
    values.update({k: v for k, v in overrides.items() if v is not None})
    for key, value in list(values.items()):
        if value is None:
            values.pop(key)
    return values


def binding(jwks_file, **overrides):
    resolved = oauth.resolve_oauth_binding(env(jwks_file, **overrides), "")
    assert not isinstance(resolved, str), resolved
    return resolved


def token(signing_key, **overrides) -> str:
    body = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "isaac-mcp-client",
        "exp": NOW + 600,
        "scope": Scope.READ.value,
    }
    body.update(overrides)
    return keys.mint(signing_key, body)


def bearer(signing_key, **overrides) -> Credential:
    return Credential(scheme="Bearer", token=token(signing_key, **overrides))


def frozen(at: int = NOW):
    return lambda: float(at)


def build_app():
    from isaac_api.app import create_app

    return create_app()


def _all_paths(routes) -> list[str]:
    found: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            found.append(path)
        nested = getattr(route, "routes", None) or getattr(
            getattr(route, "original_router", None), "routes", None
        )
        if nested:
            found.extend(_all_paths(nested))
    return found


# ==========================================================================
# 1. The default deployment is unchanged. Nothing below matters without this.
# ==========================================================================


def test_the_default_deployment_mounts_no_mcp_and_no_metadata_route(clean):
    app = build_app()
    paths = _all_paths(app.routes)
    assert MCP_PATH not in paths
    assert not [p for p in paths if ".well-known" in p]


def test_the_default_deployment_serves_no_metadata_document(clean):
    """Not "a 404 from a registered path" — an absent path. A route that refuses
    still advertises that ISAAC has an OAuth story and invites a search for the
    credential that opens it."""
    client = TestClient(build_app(), client=ANY_PEER)
    for path in (
        oauth.WELL_KNOWN_PREFIX,
        f"{oauth.WELL_KNOWN_PREFIX}/api/mcp",
        "/.well-known/oauth-authorization-server",
    ):
        assert client.get(path).status_code == 404


def test_the_openapi_operation_count_is_untouched_by_this_feature(clean):
    """Both mounts are raw ASGI routes with ``include_in_schema=False``, so no
    ISAAC API operation is added, removed or renamed. The exact count is asserted
    by ``test_about_and_openapi.py``; this asserts the DELTA is zero, which is the
    claim this slice is making."""
    before = build_app().openapi()
    clean.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    after = build_app().openapi()
    assert before["paths"] == after["paths"]


def test_selecting_the_binding_without_configuring_it_opens_nothing(clean):
    """Fail-closed, and it is the RESOLUTION that fails closed — separately from
    the boot refusal, so a direct `resolve_binding` call cannot be the hole."""
    clean.setenv(DEPLOYMENT_ENV, OAUTH_RESOURCE_SERVER)
    resolved = resolve_binding()
    assert isinstance(resolved, UnconfiguredDeployment)
    assert resolved.serves_transport is False
    assert resolved.reason.startswith("misconfigured:")


def test_the_name_moved_out_of_the_reserved_table_rather_than_into_both(clean):
    """It is implemented, so it must not still read as "reserved, pending a
    decision" — a name in both tables is a document that contradicts itself."""
    assert OAUTH_RESOURCE_SERVER not in RESERVED_BINDING_NAMES
    assert "edge-issued-bearer" in RESERVED_BINDING_NAMES


def test_no_shipped_binding_publishes_a_challenge_or_a_metadata_document(clean):
    """The rule that predates this slice and survives it: a challenge pointing at
    an authorization server that does not exist is worse than no challenge."""
    for env_value in (None, LOCAL_LOOPBACK, "edge-issued-bearer", "typo"):
        if env_value is None:
            clean.delenv(DEPLOYMENT_ENV, raising=False)
        else:
            clean.setenv(DEPLOYMENT_ENV, env_value)
        resolved = resolve_binding()
        assert resolved.challenge().get("www_authenticate") is None
        assert metadata_routes_or_none(binding=resolved, base="") == ()


# ==========================================================================
# 2. Configuration is fail-closed in every direction
# ==========================================================================


@pytest.mark.parametrize(
    "override,fragment",
    [
        ({oauth.RESOURCE_ENV: ""}, "RESOURCE"),
        ({oauth.RESOURCE_ENV: "isaac.example.invalid/api/mcp"}, "absolute https"),
        ({oauth.RESOURCE_ENV: "https://isaac.example.invalid/api/mcp#f"}, "fragment"),
        ({oauth.RESOURCE_ENV: "https://isaac.example.invalid/api/mcp?a=1"}, "query"),
        ({oauth.RESOURCE_ENV: "https://u:p@isaac.example.invalid/mcp"}, "userinfo"),
        ({oauth.RESOURCE_ENV: "http://isaac.example.invalid/api/mcp"}, "loopback host"),
        ({oauth.ISSUER_ENV: ""}, "ISSUER"),
        ({oauth.ISSUER_ENV: "not-a-uri"}, "absolute https"),
        ({oauth.TOKEN_VERIFIER_ENV: ""}, "unset"),
        ({oauth.TOKEN_VERIFIER_ENV: "magic"}, "does not have"),
        ({oauth.JWKS_FILE_ENV: ""}, "readable JWKS file"),
    ],
)
def test_every_incomplete_or_invalid_configuration_refuses(jwks_file, override, fragment):
    resolved = oauth.resolve_oauth_binding(env(jwks_file, **override), "")
    assert isinstance(resolved, str), resolved
    assert fragment in resolved


def test_a_jwks_url_verifier_is_refused_because_no_fetcher_is_installed(jwks_file):
    """THE FETCH SEAM'S DEFAULT, ASSERTED. ``JWKS_FETCHER`` is ``None`` and
    nothing in this repository assigns it, so the only key sources that work are
    local. A future slice authorized to make an outbound request installs one."""
    assert oauth.JWKS_FETCHER is None
    resolved = oauth.resolve_oauth_binding(
        env(
            jwks_file,
            **{
                oauth.TOKEN_VERIFIER_ENV: oauth.URL_TOKEN_VERIFIER,
                oauth.JWKS_URL_ENV: "https://auth.example.invalid/jwks",
            },
        ),
        "",
    )
    assert isinstance(resolved, str)
    assert "makes no outbound request" in resolved


def test_a_missing_or_unreadable_key_file_refuses_every_token_rather_than_none(
    tmp_path, signing_key
):
    """Resolution succeeds — the path is syntactically fine — and every token is
    then refused. The alternative, treating an unreadable key set as "no
    verification required", is the shape this whole module exists to prevent."""
    absent = tmp_path / "not-there.json"
    resolved = binding(absent)
    with pytest.raises(DeploymentRefused) as caught:
        resolved.authenticate(bearer(signing_key))
    assert caught.value.code == "no_usable_jwks_key"


def test_the_key_file_is_reread_when_it_changes_and_not_before(tmp_path, signing_key):
    """Cached on (mtime, size), so a rotation is picked up on the next request
    while an unchanged file costs one ``stat``. A fixed-interval cache would
    either serve a revoked key for its window or re-read on every request."""
    other = keys.generate("rotated", seed=keys.SEED + 3)
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps(keys.jwks(signing_key)), encoding="utf-8")
    source = oauth.FileKeySource(path=path)
    assert [k.kid for k in source.keys().keys] == ["isaac-signing-1"]
    assert source.keys() is source.keys()  # unchanged file -> the cached object

    time.sleep(0.01)
    path.write_text(json.dumps(keys.jwks(other)), encoding="utf-8")
    assert [k.kid for k in source.keys().keys] == ["rotated"]


def test_a_path_mounted_deployment_must_name_its_metadata_url_explicitly(jwks_file):
    """THE TRAP THE OPERATOR DOCUMENT NAMES, MADE A REFUSAL. With a base path the
    RFC 9728 origin-root URL is one this application never receives, so the
    derived default would advertise a 404 — and that failure surfaces at the far
    end of a browser round-trip inside a client nobody here can debug."""
    resolved = oauth.resolve_oauth_binding(env(jwks_file), "/krish")
    assert isinstance(resolved, str)
    assert oauth.METADATA_URL_ENV in resolved

    with_url = oauth.resolve_oauth_binding(
        env(jwks_file, **{oauth.METADATA_URL_ENV: "https://isaac.example.invalid/prm"}),
        "/krish",
    )
    assert not isinstance(with_url, str)
    assert with_url.config.metadata_url == "https://isaac.example.invalid/prm"


def test_the_fixture_key_source_refuses_to_boot_however_else_it_is_configured(
    jwks_file, signing_key
):
    """Recognised so a typo cannot be mistaken for it; refused so no running
    application can be configured onto it. Exactly the asymmetry
    ``providers/config.validate_provider_config_or_raise`` uses for the fakes."""
    document = json.dumps(keys.jwks(signing_key))
    values = env(
        jwks_file,
        **{
            oauth.TOKEN_VERIFIER_ENV: oauth.FIXTURE_TOKEN_VERIFIER,
            oauth.FIXTURE_JWKS_ENV: document,
        },
    )
    with pytest.raises(RuntimeError) as caught:
        oauth.validate_oauth_selection_or_raise(values, "")
    assert oauth.FIXTURE_TOKEN_VERIFIER in str(caught.value)
    # …and it is a real verifier, not a bypass: constructed directly it performs
    # the same verification and mints a basis that says what it is.
    resolved = oauth.resolve_oauth_binding(values, "")
    assert resolved.config.trust_basis == identity.TRUST_BASIS_TEST_FIXTURE
    principal = resolved.authenticate(bearer(signing_key))
    assert principal.subject == "isaac-mcp-client"
    with pytest.raises(DeploymentRefused):
        resolved.authenticate(Credential(scheme="Bearer", token="forged.token.here"))


def test_a_bootable_verifier_mints_the_oauth_basis_and_a_fixture_one_does_not(
    jwks_file, signing_key
):
    real = binding(jwks_file)
    assert real.config.trust_basis == identity.TRUST_BASIS_VERIFIED_OAUTH_ACCESS_TOKEN
    oauth.validate_oauth_selection_or_raise(env(jwks_file), "")  # does not raise


def test_a_complete_configuration_boots_and_an_incomplete_one_does_not(jwks_file):
    oauth.validate_oauth_selection_or_raise(env(jwks_file), "")
    with pytest.raises(RuntimeError) as caught:
        oauth.validate_oauth_selection_or_raise(
            env(jwks_file, **{oauth.ISSUER_ENV: ""}), ""
        )
    assert "cannot be served" in str(caught.value)


# ==========================================================================
# 3. Authentication: no anonymous branch, ever
# ==========================================================================


def test_a_request_with_no_credential_is_refused_and_is_not_read_only(
    jwks_file, signing_key
):
    """THE DEFECT THIS ASSERTS AGAINST IS A ONE-LINE ONE: answering "no
    credential" with a read-only principal. It would produce a public MCP
    endpoint that looks, in every log and every status surface, exactly like a
    working authenticated one."""
    with pytest.raises(DeploymentRefused) as caught:
        binding(jwks_file).authenticate(None)
    assert caught.value.code == "token_absent"


def test_a_non_bearer_scheme_is_refused_rather_than_tried_as_a_bearer(jwks_file):
    with pytest.raises(DeploymentRefused) as caught:
        binding(jwks_file).authenticate(Credential(scheme="Basic", token="abcd"))
    assert caught.value.code == "unsupported_authentication_scheme"
    assert caught.value.data["scheme"] == "Basic"
    # RFC 6750 §3 names this case in the same sentence as a request with no
    # credential at all — "*or attempted using an unsupported authentication
    # method*" — so the challenge carries NO error code. `invalid_request` would
    # be the intuitive choice and is wrong twice: it is defined for a malformed
    # BEARER request, and §3.1 pairs it with a 400 rather than the 401 this is.
    assert "error=" not in caught.value.challenge["www_authenticate"]


def test_the_reported_scheme_cannot_carry_a_credential(jwks_file):
    """``_reportable_scheme``'s allowlist, exercised through this binding. A bare
    token parses with no scheme, and a long junk "scheme" is replaced rather than
    truncated — a fragment of a secret is not a redaction."""
    secret = "s3cret-" + "x" * 60
    with pytest.raises(DeploymentRefused) as caught:
        binding(jwks_file).authenticate(Credential(scheme=secret, token=""))
    assert caught.value.data["scheme"] == ""
    assert secret not in json.dumps(caught.value.data)


def test_a_verified_token_becomes_a_principal_carrying_only_its_own_scopes(
    jwks_file, signing_key
):
    resolved = binding(jwks_file)
    principal = resolved.authenticate(bearer(signing_key))
    assert principal.subject == "isaac-mcp-client"
    assert principal.binding == OAUTH_RESOURCE_SERVER
    assert principal.scopes == frozenset({Scope.READ})
    assert principal.tutorial_session_id is None


def test_expiry_is_evaluated_against_the_binding_clock(jwks_file, signing_key):
    resolved = binding(jwks_file)
    fresh = bearer(signing_key, exp=NOW + 60)
    assert resolved.authenticate(fresh)

    from dataclasses import replace

    later = replace(resolved, clock=frozen(NOW + 4000))
    with pytest.raises(DeploymentRefused) as caught:
        later.authenticate(fresh)
    assert caught.value.code == "expired"


# ==========================================================================
# 4. Scopes: mapped, never widened, and never nested
# ==========================================================================


@pytest.mark.parametrize(
    "scope_claim,expected",
    [
        ("isaac:read", {Scope.READ}),
        ("isaac:draft.write", {Scope.DRAFT_WRITE}),
        ("isaac:read isaac:draft.write", {Scope.READ, Scope.DRAFT_WRITE}),
        ("openid profile email offline_access", set()),
        ("isaac:read openid", {Scope.READ}),
        ("", set()),
    ],
)
def test_token_scopes_map_to_isaac_scopes_and_unknown_ones_are_dropped(
    jwks_file, signing_key, scope_claim, expected
):
    """Dropping is right for a TOKEN and wrong for CONFIGURATION, and the
    asymmetry is deliberate: a token legitimately carries scopes for other
    things, while an unknown scope in an operator's own configuration is a
    server running on permissions nobody wrote down."""
    principal = binding(jwks_file).authenticate(bearer(signing_key, scope=scope_claim))
    assert principal.scopes == frozenset(expected)


def test_a_token_carrying_no_isaac_scope_authenticates_and_authorizes_nothing(
    jwks_file, signing_key
):
    """The honest outcome, and the one that makes the 401/403 split meaningful:
    authentication succeeded, so this is not a 401; nothing was granted, so every
    tool is a 403."""
    principal = binding(jwks_file).authenticate(bearer(signing_key, scope="openid"))
    assert principal.scopes == frozenset()
    assert not principal.permits(Scope.READ)


@pytest.mark.parametrize("forbidden", ["isaac:submit", "isaac:export", "isaac:admin", "*"])
def test_no_token_can_grant_a_scope_this_server_does_not_express(
    jwks_file, signing_key, forbidden
):
    """A token is not a way to invent a permission. There is no scope for
    submission, export, finalisation or deletion — not withheld, ABSENT — so a
    token naming one maps to nothing at all."""
    principal = binding(jwks_file).authenticate(
        bearer(signing_key, scope=f"{forbidden} isaac:read")
    )
    assert principal.scopes == frozenset({Scope.READ})


def test_the_two_scopes_do_not_imply_each_other_in_either_direction(
    jwks_file, signing_key
):
    """THE SPECIFICATION'S SCOPE-HIERARCHY MUST, SATISFIED BY HAVING NO HIERARCHY.

    *"Servers MUST account for scope hierarchies, WHERE a broader scope implies
    narrower ones."* ISAAC's do not — ``policy.py`` records the decision and the
    reason — so there is nothing to account for and the resource server must not
    invent one. Asserted in both directions so an implication cannot be added
    later without a test going red.
    """
    resolved = binding(jwks_file)
    write_only = resolved.authenticate(bearer(signing_key, scope=Scope.DRAFT_WRITE.value))
    assert not write_only.permits(Scope.READ)
    read_only = resolved.authenticate(bearer(signing_key, scope=Scope.READ.value))
    assert not read_only.permits(Scope.DRAFT_WRITE)


# ==========================================================================
# 5. RFC 9728 metadata and RFC 6750 challenges
# ==========================================================================


def test_the_metadata_document_names_an_authorization_server_and_the_resource(
    jwks_file,
):
    document = binding(jwks_file).protected_resource_metadata()
    assert document["resource"] == RESOURCE
    assert document["authorization_servers"] == [ISSUER]
    assert document["bearer_methods_supported"] == ["header"]


def test_bearer_methods_supported_names_only_the_header(jwks_file):
    """RFC 6750 defines three ways to present a token and this server accepts
    one. Advertising the other two would be a lie a conforming client acts on."""
    document = binding(jwks_file).protected_resource_metadata()
    assert "body" not in document["bearer_methods_supported"]
    assert "query" not in document["bearer_methods_supported"]


def test_scopes_supported_is_the_minimal_set_and_never_carries_offline_access(
    jwks_file,
):
    """Two requirements at once: the specification's *"minimal set of scopes
    necessary for basic functionality"*, and its *"SHOULD NOT include
    ``offline_access``"*. The second holds structurally — the list is derived
    from ``policy.Scope`` — so it cannot regress by transcription."""
    document = binding(jwks_file).protected_resource_metadata()
    assert document["scopes_supported"] == [Scope.READ.value]
    assert "offline_access" not in document["scopes_supported"]
    assert Scope.DRAFT_WRITE.value not in document["scopes_supported"]


def test_multiple_authorization_servers_keep_their_configured_order(jwks_file):
    """A client uses the first entry, so the order is a configuration decision
    and must not be sorted, de-duplicated into a set, or otherwise rearranged."""
    resolved = binding(
        jwks_file,
        **{
            oauth.AUTHORIZATION_SERVERS_ENV: (
                f"{ISSUER}, https://second.example.invalid"
            )
        },
    )
    assert resolved.protected_resource_metadata()["authorization_servers"] == [
        ISSUER,
        "https://second.example.invalid",
    ]


def test_the_401_challenge_points_at_the_metadata_and_names_the_minimal_scope(
    jwks_file,
):
    challenge = binding(jwks_file).challenge()["www_authenticate"]
    assert challenge.startswith("Bearer ")
    assert 'resource_metadata="' in challenge
    assert f'scope="{Scope.READ.value}"' in challenge


def test_a_request_that_presented_nothing_gets_no_error_code_in_its_challenge(
    jwks_file, signing_key
):
    """RFC 6750 §3: *"If the request lacks any authentication information … the
    resource server SHOULD NOT include an error code."* An unauthenticated first
    probe is the normal start of the flow, not a failure, and reporting
    ``invalid_token`` for it sends conforming clients down an error path."""
    resolved = binding(jwks_file)
    with pytest.raises(DeploymentRefused) as caught:
        resolved.authenticate(None)
    assert "error=" not in caught.value.challenge["www_authenticate"]


def test_a_bad_credential_gets_error_invalid_token_in_its_challenge(
    jwks_file, signing_key
):
    resolved = binding(jwks_file)
    # Against the real clock, because the binding's default clock is the real
    # one. `NOW` is a fixed instant used where a frozen clock is also supplied.
    with pytest.raises(DeploymentRefused) as caught:
        resolved.authenticate(bearer(signing_key, exp=int(time.time()) - 10_000))
    assert 'error="invalid_token"' in caught.value.challenge["www_authenticate"]


def test_the_403_challenge_names_every_missing_scope_in_one_go(jwks_file):
    """*"Challenging incrementally … forces multiple authorization round-trips
    for a single operation and degrades user experience."*"""
    challenge = binding(jwks_file).scope_challenge(
        [Scope.DRAFT_WRITE.value, Scope.READ.value]
    )["www_authenticate"]
    assert 'error="insufficient_scope"' in challenge
    # Sorted, so the header is byte-reproducible across runs; a caller must not
    # read meaning into the order, and a test that pinned insertion order would
    # be pinning a dict iteration.
    assert f'scope="{Scope.DRAFT_WRITE.value} {Scope.READ.value}"' in challenge
    assert 'resource_metadata="' in challenge


def test_a_challenge_value_that_could_split_the_header_is_dropped_not_escaped(
    jwks_file,
):
    """Escaping is a second parser to get right and truncating publishes a
    fragment. A value that is not safe to emit is simply not emitted."""
    resolved = binding(jwks_file)
    from dataclasses import replace

    poisoned = replace(
        resolved.config, metadata_url='https://x.invalid/"\r\nX-Injected: 1'
    )
    challenge = oauth.bearer_challenge(poisoned)["www_authenticate"]
    assert "\r" not in challenge and "\n" not in challenge
    assert "X-Injected" not in challenge
    assert "resource_metadata" not in challenge


def test_the_metadata_paths_are_deterministic_and_deduplicated(jwks_file):
    resolved = binding(
        jwks_file, **{oauth.METADATA_URL_ENV: "https://isaac.example.invalid/prm"}
    )
    assert resolved.metadata_paths("") == (
        oauth.WELL_KNOWN_PREFIX,
        f"{oauth.WELL_KNOWN_PREFIX}/api/mcp",
    )


# ==========================================================================
# 6. Over real HTTP
# ==========================================================================


@pytest.fixture()
def served(clean, jwks_file):
    for name, value in env(jwks_file).items():
        clean.setenv(name, value)
    clean.setenv(DEPLOYMENT_ENV, OAUTH_RESOURCE_SERVER)
    app = build_app()
    return app, TestClient(app, client=ANY_PEER)


def rpc(client, method, params=None, *, headers=None, **kwargs):
    message = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        message["params"] = params
    return client.post(MCP_PATH, json=message, headers=headers or {}, **kwargs)


def test_an_unauthenticated_request_is_401_with_a_conforming_challenge(served):
    _, client = served
    response = rpc(client, "tools/list")
    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer ")
    assert 'resource_metadata="' in challenge
    assert response.json()["error"]["code"] == DEPLOYMENT_UNCONFIGURED


def test_an_expired_token_is_401_and_says_invalid_token(served, signing_key):
    _, client = served
    stale = token(signing_key, exp=int(time.time()) - 10_000)
    response = rpc(client, "tools/list", headers={"Authorization": f"Bearer {stale}"})
    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["www-authenticate"]
    assert stale not in response.text


def test_a_valid_token_is_served_and_lists_only_permitted_tools(served, signing_key):
    _, client = served
    live = token(signing_key, exp=int(time.time()) + 600)
    response = rpc(client, "tools/list", headers={"Authorization": f"Bearer {live}"})
    assert response.status_code == 200, response.text
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert "isaac_list_experiments" in names
    assert not [name for name in names if "submit" in name or "export" in name]


def test_insufficient_scope_is_403_with_the_scope_the_operation_needs(
    served, signing_key
):
    """The 401/403 distinction the specification requires, over the wire: the
    token verified (so not a 401) and does not carry the write scope (so a 403
    naming it)."""
    _, client = served
    read_only = token(signing_key, exp=int(time.time()) + 600, scope=Scope.READ.value)
    response = rpc(
        client,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": "x"}},
        headers={"Authorization": f"Bearer {read_only}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == INSUFFICIENT_SCOPE
    challenge = response.headers["www-authenticate"]
    assert 'error="insufficient_scope"' in challenge
    assert Scope.DRAFT_WRITE.value in challenge


def test_a_token_carrying_the_write_scope_gets_past_the_scope_gate(served, signing_key):
    """THE NEGATIVE CONTROL FOR THE 403 ABOVE, and the test file is weak without it.

    A server on which ``isaac_create_run`` were unreachable for any other reason
    would pass the insufficient-scope test while granting nothing, so this proves
    the scope mapping actually GRANTS rather than only withholding. The call is
    expected to fail — the experiment id does not exist — and what matters is the
    shape of the failure: a JSON-RPC ``200`` from the application layer, **not**
    a ``403`` from the authorization layer.
    """
    _, client = served
    both = token(
        signing_key,
        exp=int(time.time()) + 600,
        scope=f"{Scope.READ.value} {Scope.DRAFT_WRITE.value}",
    )
    response = rpc(
        client,
        "tools/call",
        {"name": "isaac_create_run", "arguments": {"experiment_id": "no-such-record"}},
        headers={"Authorization": f"Bearer {both}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("error", {}).get("code") != INSUFFICIENT_SCOPE
    assert Scope.DRAFT_WRITE.value not in response.text


@pytest.mark.parametrize("parameter", ["access_token", "token", "bearer_token", "apikey"])
def test_a_token_in_the_query_string_is_refused_rather_than_ignored(
    served, signing_key, parameter
):
    """*"Access tokens MUST NOT be included in the URI query string."* Ignoring
    the parameter would be conformant and useless: the credential has already
    reached every access log in front of this process, and a client doing it
    needs to be told to stop."""
    _, client = served
    live = token(signing_key, exp=int(time.time()) + 600)
    response = client.post(
        f"{MCP_PATH}?{parameter}={live}",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {live}"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["data"]["code"] == "token_in_query_string"
    assert live not in response.text


def test_an_unrelated_query_parameter_does_not_trip_the_refusal(served, signing_key):
    """The negative control. Without it the test above would pass on a transport
    that refused every query string, which is a different program."""
    _, client = served
    live = token(signing_key, exp=int(time.time()) + 600)
    response = client.post(
        f"{MCP_PATH}?trace=1",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {live}"},
    )
    assert response.status_code == 200, response.text


def test_the_metadata_document_is_served_unauthenticated_at_both_paths(served):
    """Unauthenticated on purpose: RFC 9728 metadata is what a client reads
    BEFORE it has a token, so requiring one would make the flow unstartable. It
    contains only configuration an operator chose to publish."""
    _, client = served
    for path in (oauth.WELL_KNOWN_PREFIX, f"{oauth.WELL_KNOWN_PREFIX}/api/mcp"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["resource"] == RESOURCE


def test_the_metadata_route_answers_405_for_a_write(served):
    _, client = served
    response = client.post(oauth.WELL_KNOWN_PREFIX, json={})
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD"


def test_the_metadata_document_does_not_appear_in_the_openapi_schema(served):
    app, _ = served
    assert not [p for p in app.openapi()["paths"] if ".well-known" in p]


def test_the_oauth_binding_serves_a_non_loopback_peer_and_a_foreign_origin(
    served, signing_key
):
    """The three split guards, exercised where they differ from ``local-loopback``.

    A remote peer, a proxy header and a foreign ``Origin`` are all served here and
    all refused there — which is the whole reason the single flag became three.
    The token, not the network position, is what authorizes.
    """
    _, client = served
    live = token(signing_key, exp=int(time.time()) + 600)
    response = rpc(
        client,
        "tools/list",
        headers={
            "Authorization": f"Bearer {live}",
            "X-Forwarded-For": "198.51.100.9",
            "Origin": "https://claude.ai",
        },
    )
    assert response.status_code == 200, response.text


def test_the_loopback_binding_still_refuses_all_three(clean):
    """The other half of the pair. If the split had leaked a ``False`` default
    into ``local-loopback``, this is what would go green-then-quiet."""
    clean.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    client = TestClient(build_app(), client=("127.0.0.1", 5555))
    assert rpc(client, "tools/list", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 403
    assert rpc(client, "tools/list", headers={"Origin": "https://evil.invalid"}).status_code == 403
    remote = TestClient(build_app(), client=("203.0.113.9", 5555))
    assert rpc(remote, "tools/list").status_code == 403


# ==========================================================================
# 7. A service principal is not an author
# ==========================================================================


def test_a_verified_token_yields_a_service_principal_that_can_never_be_an_author(
    jwks_file, signing_key
):
    """THE PROPERTY THE WHOLE SLICE IS GATED ON. A token proves a CLIENT holds a
    credential the issuer minted; it does not establish that a person is present,
    and this build has no boundary that could. So the tier is SERVICE, and every
    consequence follows from ``identity.py`` without this module arranging any of
    them."""
    resolved = binding(jwks_file)
    request_identity = resolved.service_identity(resolved.authenticate(bearer(signing_key)))

    assert request_identity.trust is identity.TrustTier.SERVICE
    assert request_identity.human is None
    assert request_identity.service.principal_id == "isaac-mcp-client"
    assert (
        request_identity.service.trust_basis
        == identity.TRUST_BASIS_VERIFIED_OAUTH_ACCESS_TOKEN
    )
    # No `subject` field for a stamping call site to reach for by mistake…
    assert not hasattr(request_identity.service, "subject")
    # …and the stamping function reads only the human half.
    assert identity.stamp_actor(request_identity, None) is None


def test_a_service_principal_is_refused_by_require_human_actor_with_its_own_reason(
    jwks_file, signing_key
):
    """A service token cannot submit. Refused with a DISTINCT reason, so a caller
    holding a working credential does not read it as an auth failure and retry
    with the same credential forever."""
    resolved = binding(jwks_file)
    request_identity = resolved.service_identity(resolved.authenticate(bearer(signing_key)))
    raised = identity.HumanActorRequired(
        operation="submit_record", identity=request_identity
    )
    assert raised.status_code == 409
    assert raised.payload["reason"] == "service_principal_not_attributable"
    assert raised.payload["trust"] == "service"


def test_the_oauth_basis_is_claimable_by_a_service_and_by_nothing_else(jwks_file):
    """THE ASYMMETRY, ASSERTED IN BOTH DIRECTIONS — the mirror of the existing
    ``unattributed`` one.

    Widening ``RECOGNISED_TRUST_BASES`` would have made
    ``HumanActor(trust_basis="verified_oauth_access_token")`` constructible while
    the database CHECK constraint in the owner-approved ``0003``/``0004``
    migrations still refused it: a construction-time refusal converted into a
    runtime integrity error on an append-only attributable table.
    """
    basis = identity.TRUST_BASIS_VERIFIED_OAUTH_ACCESS_TOKEN
    assert basis in identity.SERVICE_TRUST_BASES
    assert basis not in identity.RECOGNISED_TRUST_BASES
    assert identity.ServicePrincipal(principal_id="agent", trust_basis=basis)
    with pytest.raises(ValueError):
        identity.HumanActor(subject="someone", trust_basis=basis)
    with pytest.raises(ValueError):
        identity.EdgeAssertion(
            subject="someone", verifier_id="v", trust_basis=basis
        )


def test_the_oauth_basis_is_not_the_edge_basis_that_arms_record_attribution(jwks_file):
    """``record_attribution`` gates server-side stamping on
    ``verified_edge_assertion`` specifically. Reusing that name for a token would
    have armed attribution for a non-human caller — the exact defect
    ``ServicePrincipal`` exists to make unbuildable."""
    assert (
        identity.TRUST_BASIS_VERIFIED_OAUTH_ACCESS_TOKEN
        != identity.TRUST_BASIS_VERIFIED_EDGE_ASSERTION
    )


def test_every_service_basis_a_human_may_also_claim_is_still_claimable(jwks_file):
    """``SERVICE_TRUST_BASES`` is a SUPERSET, not a replacement: a
    fixture-verified service is a real state and has to stay expressible."""
    assert identity.RECOGNISED_TRUST_BASES < identity.SERVICE_TRUST_BASES
    assert identity.ServicePrincipal(
        principal_id="agent", trust_basis=identity.TRUST_BASIS_TEST_FIXTURE
    )
    with pytest.raises(ValueError):
        identity.ServicePrincipal(principal_id="agent", trust_basis="because-i-said-so")
