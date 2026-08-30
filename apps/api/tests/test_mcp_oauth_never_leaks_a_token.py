"""No credential reaches a log, a response body, a header, or another service.

THIS FILE EXISTS BECAUSE THE DEFECT IT GUARDS AGAINST ALREADY HAPPENED HERE ONCE.
``transport._credential_from`` used to split ``Authorization`` on the first space,
so a header carrying a BARE token — no ``Bearer``, no space, a shape real clients
send — put the entire credential into ``scheme``, and the loopback binding then
reported that "scheme" in the body of its ``401``. A 48-character stand-in JWT
came back to the caller verbatim. The existing test could not see it: it sent
``"Bearer s3cret-value"``, the well-formed shape, and its assertion was true of
that shape and of no other.

So the assertions here are **swept over every rejection path**, not written one
per known-bad case, and they are made against **four surfaces**: the response
body, the response headers, everything the logging system was handed (including
un-interpolated ``args``), and — the structural one — whether any object in the
system has a field a token could be stored in at all.

The last of those is what makes the no-passthrough rule hold by construction
rather than by discipline. *"MCP servers MUST NOT accept or transit any other
tokens"*: there is nowhere for a token to be kept, so there is nothing to
forward.
"""

from __future__ import annotations

import ast
import json
import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api.mcp import jwt as jwtmod
from isaac_api.mcp import oauth
from isaac_api.mcp.deployment import DEPLOYMENT_ENV, OAUTH_RESOURCE_SERVER, Credential
from isaac_api.mcp.jwt import VerifiedToken
from isaac_api.mcp.transport import MCP_PATH
import mcp_oauth_keys as keys

MCP_PACKAGE = Path(oauth.__file__).parent

ISSUER = "https://auth.example.invalid/application/o/isaac"
RESOURCE = "https://isaac.example.invalid/api/mcp"

#: Long enough that a fragment of it is unmistakable in any output, and shaped
#: like the thing an attacker would try to make leak.
SENTINEL_SECRET = "s3cret-" + "A" * 64


@pytest.fixture(scope="session")
def signing_key():
    return keys.generate("isaac-signing-1", seed=keys.SEED)


@pytest.fixture()
def served(tmp_path, monkeypatch, signing_key):
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps(keys.jwks(signing_key)), encoding="utf-8")
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    for name in oauth.OAUTH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(DEPLOYMENT_ENV, OAUTH_RESOURCE_SERVER)
    monkeypatch.setenv(oauth.RESOURCE_ENV, RESOURCE)
    monkeypatch.setenv(oauth.ISSUER_ENV, ISSUER)
    monkeypatch.setenv(oauth.TOKEN_VERIFIER_ENV, oauth.FILE_TOKEN_VERIFIER)
    monkeypatch.setenv(oauth.JWKS_FILE_ENV, str(jwks_path))

    from isaac_api.app import create_app

    app = create_app()
    return TestClient(app, client=("203.0.113.7", 44321))


def minted(signing_key, **overrides) -> str:
    body = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": SENTINEL_SECRET,
        "exp": int(time.time()) + 600,
        "scope": "isaac:read",
    }
    body.update(overrides)
    return keys.mint(signing_key, body)


def every_bad_credential(signing_key) -> dict[str, str]:
    """One credential per refusal path this module can reach over HTTP.

    Each value contains :data:`SENTINEL_SECRET`, so a leak anywhere shows up as
    the same searchable string regardless of which branch produced it.
    """
    now = int(time.time())
    other = keys.generate("attacker", seed=keys.SEED + 1)
    return {
        "bare_token_no_scheme": SENTINEL_SECRET,
        "opaque": f"Bearer {SENTINEL_SECRET}",
        "wrong_scheme": f"{SENTINEL_SECRET} abcdef",
        "basic": f"Basic {SENTINEL_SECRET}",
        "malformed_jws": f"Bearer {SENTINEL_SECRET}.{SENTINEL_SECRET}.{SENTINEL_SECRET}",
        "alg_none": "Bearer " + keys.mint_unsecured({"sub": SENTINEL_SECRET}),
        "hmac_confusion": "Bearer "
        + keys.mint_hmac_confusion(signing_key, {"sub": SENTINEL_SECRET}),
        "expired": "Bearer " + minted(signing_key, exp=now - 10_000),
        "not_yet_valid": "Bearer " + minted(signing_key, nbf=now + 10_000),
        "wrong_issuer": "Bearer " + minted(signing_key, iss="https://evil.invalid"),
        "wrong_audience": "Bearer " + minted(signing_key, aud="https://other.invalid"),
        "forged_signature": "Bearer "
        + keys.mint(signing_key, {"sub": SENTINEL_SECRET, "exp": now + 60},
                    signing_key=other),
        "tampered": "Bearer "
        + keys.mint(signing_key, {"sub": SENTINEL_SECRET, "exp": now + 60},
                    tamper_signature=True),
        "unknown_kid": "Bearer "
        + keys.mint(signing_key, {"sub": SENTINEL_SECRET, "exp": now + 60},
                    header_overrides={"kid": "rotated-away"}),
        "oversized": "Bearer " + "z" * (jwtmod.MAX_COMPACT_TOKEN_BYTES + 10),
    }


# --- 1. nothing reaches the caller -------------------------------------------


def test_no_rejection_path_echoes_the_credential_in_the_body_or_the_headers(
    served, signing_key
):
    """Swept over every branch, because the historical defect was reachable on
    exactly one shape and the test of the day covered a different one."""
    for name, header in every_bad_credential(signing_key).items():
        response = served.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": header},
        )
        assert response.status_code == 401, (name, response.status_code)
        assert SENTINEL_SECRET not in response.text, name
        for key, value in response.headers.items():
            assert SENTINEL_SECRET not in value, (name, key)


def test_a_credential_pasted_into_the_protocol_version_is_not_echoed_back(
    served, signing_key
):
    """**A NEW ECHO PATH ARRIVED WITH THE DUAL-ERA WORK, AND IT IS BOUNDED.**

    ``UnsupportedProtocolVersionError``'s ``data.requested`` is required by the
    specification's error shape — a client declaring a version in two places needs
    to know which one was rejected — so it is the first field in this surface that
    carries caller-supplied text into a response body. Every other refusal here
    states a rule instead of reflecting an input, and the historical defect this
    file exists for was exactly a credential arriving in a field nobody expected
    to be reflected.

    Pasting a bearer token into ``MCP-Protocol-Version`` is not a contrived
    attack; it is what a copy-paste into the wrong header line produces. The
    server answers ``400`` with the version error and the field replaced by a
    fixed string.

    The value is swept through **both** carriers, because ``_meta`` and the header
    are checked by the same loop and a fix applied to one would leave the other.

    ``SENTINEL_SECRET`` is used **as the pasted value itself** rather than a
    minted JWT: a compact JWS carries its claims base64-encoded, so a sentinel
    inside one would not appear literally in the response even if the whole token
    were echoed — the test would pass without establishing anything. The opaque
    shape is also the realistic one for a paste.
    """
    pasted = SENTINEL_SECRET
    carriers = (
        ("header", {"MCP-Protocol-Version": pasted}, None),
        (
            "meta",
            {},
            {"_meta": {"io.modelcontextprotocol/protocolVersion": pasted}},
        ),
    )
    for name, headers, params in carriers:
        message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        if params is not None:
            message["params"] = params
        response = served.post(
            MCP_PATH,
            json=message,
            headers={
                "Authorization": f"Bearer {minted(signing_key)}",
                **headers,
            },
        )
        assert response.status_code == 400, (name, response.text)
        assert response.json()["error"]["code"] == -32022, name
        assert SENTINEL_SECRET not in response.text, name
        for key, value in response.headers.items():
            assert SENTINEL_SECRET not in value, (name, key)


def test_the_refusal_still_says_something_useful_so_this_is_not_passing_by_silence(
    served, signing_key
):
    """The negative control for the test above. A server that returned an empty
    body would satisfy every leak assertion in this file and be useless."""
    response = served.post(
        MCP_PATH,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": "Bearer " + minted(signing_key, exp=1)},
    )
    body = response.json()
    assert body["error"]["data"]["code"] == "expired"
    assert "expired" in body["error"]["message"].lower()
    assert 'error="invalid_token"' in response.headers["www-authenticate"]


def test_a_successful_request_does_not_echo_the_credential_either(served, signing_key):
    """The path nobody thinks to check, because it is the one that worked."""
    good = minted(signing_key)
    response = served.post(
        MCP_PATH,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {good}"},
    )
    assert response.status_code == 200
    assert good not in response.text


# --- 2. nothing reaches the logs ---------------------------------------------


def test_no_rejection_path_hands_the_credential_to_the_logging_system(
    served, signing_key, caplog
):
    """Asserted over ``record.args`` and ``record.getMessage()`` BOTH.

    A ``_log.info("refused %s", token)`` produces a record whose formatted
    message contains the token and whose ``args`` contains it too; a handler that
    never formats would still ship ``args`` to a structured sink. Checking only
    the formatted message would miss half of it.
    """
    with caplog.at_level(logging.DEBUG, logger="isaac_api"):
        for header in every_bad_credential(signing_key).values():
            served.post(
                MCP_PATH,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={"Authorization": header},
            )
        credential_refusals = list(caplog.records)
        # THE VACUITY GUARD, and it is a separate request on purpose. The sweep
        # above logs NOTHING — see the next test, which asserts that as its own
        # claim — so an empty `caplog` here would be indistinguishable from a
        # logging pipeline this fixture never armed. The query-string refusal
        # DOES log, at INFO, with a fixed string; driving one proves the capture
        # is live before anything is concluded from its emptiness.
        served.post(
            f"{MCP_PATH}?access_token={SENTINEL_SECRET}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert caplog.records, "the logging capture was never armed; the sweep is vacuous"
    for record in caplog.records:
        assert SENTINEL_SECRET not in record.getMessage()
        assert SENTINEL_SECRET not in repr(record.args)
    assert credential_refusals == [], (
        "an authentication refusal wrote a log record; every one of them is "
        "reached with a credential in hand, so this is the one code path where a "
        f"log line is most likely to carry one: {credential_refusals}"
    )


def test_a_token_in_the_query_string_is_refused_without_being_logged(
    served, signing_key, caplog
):
    """The refusal for a credential in the URL must not itself be what writes the
    credential down. Only the parameter NAME is read; the value is never sliced
    out of the query string at all."""
    leaked = minted(signing_key)
    with caplog.at_level(logging.DEBUG, logger="isaac_api"):
        response = served.post(
            f"{MCP_PATH}?access_token={leaked}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    assert response.status_code == 400
    assert leaked not in response.text
    for record in caplog.records:
        assert leaked not in record.getMessage()
        assert leaked not in repr(record.args)


# --- 3. no branch can build a message out of token material ------------------


def test_every_rejection_message_is_a_constant_from_the_rejection_table():
    """The property that makes the sweeps above hold for branches they miss.

    Every ``TokenRejected`` this module raises carries a message looked up from
    ``_REJECTIONS``. If a future branch interpolated a claim value — the
    "helpful" *"expected audience X, got Y"* — the sweep might not reach it, but
    this will: the message would not be in the table.
    """
    for code, message in jwtmod._REJECTIONS.items():
        assert isinstance(message, str) and message
        assert "{" not in message and "%s" not in message


def test_no_raise_in_the_token_verifier_interpolates_anything():
    """An AST scan, so it holds for branches no test drives.

    Every ``raise TokenRejected(...)`` in ``jwt.py`` passes a constant or a
    lookup; none passes an f-string, a ``.format`` call, or a ``%``. The one
    place a message is constructed is ``FileKeySource``, which names no token.
    """
    tree = ast.parse((MCP_PACKAGE / "jwt.py").read_text(encoding="utf-8"))
    offences = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        for inner in ast.walk(node.exc):
            if isinstance(inner, ast.JoinedStr):
                offences.append(f"f-string at line {node.lineno}")
            if isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Mod):
                offences.append(f"%-format at line {node.lineno}")
            if (
                isinstance(inner, ast.Attribute)
                and inner.attr == "format"
            ):
                offences.append(f".format at line {node.lineno}")
    assert offences == [], offences


def test_the_reportable_scheme_allowlist_replaces_rather_than_truncates():
    """A 32-character prefix of a secret is not a redaction. Asserted against the
    one field a refusal is allowed to publish."""
    from isaac_api.mcp.deployment import _reportable_scheme

    assert _reportable_scheme(SENTINEL_SECRET) == ""
    assert _reportable_scheme("Bearer") == "Bearer"
    assert SENTINEL_SECRET[:8] not in _reportable_scheme(SENTINEL_SECRET)


# --- 4. no passthrough, held structurally ------------------------------------


def test_no_object_downstream_of_verification_has_a_field_holding_the_token():
    """*"MCP servers MUST NOT accept or transit any other tokens."*

    Held by construction rather than by discipline: there is nowhere to keep a
    token, so there is nothing to forward. A future field named ``token`` or
    ``credential`` on either of these turns this red before it can be read by
    anything.
    """
    from isaac_api.mcp.deployment import Principal

    for cls in (VerifiedToken, Principal):
        fields = set(getattr(cls, "__dataclass_fields__", {}))
        assert not {"token", "credential", "access_token", "bearer", "raw"} & fields, cls


def test_a_verified_token_object_does_not_contain_the_credential_anywhere(signing_key):
    """Including in ``claims``, which is a copy of the payload and never of the
    compact serialization it came from."""
    from isaac_api.mcp.jwt import jwks_from_document, verify_access_token

    compact = minted(signing_key)
    verified = verify_access_token(
        compact,
        keys=jwks_from_document(keys.jwks(signing_key)),
        issuer=ISSUER,
        resource=RESOURCE,
        now=int(time.time()),
    )
    assert compact not in repr(verified)
    assert compact not in json.dumps(verified.claims, default=str)


def test_the_binding_hands_the_client_a_principal_and_never_a_credential(
    tmp_path, signing_key
):
    """``client.py`` builds its outbound headers from the principal. The
    credential does not reach the object it is given, so an upstream request
    cannot carry it even by accident."""
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps(keys.jwks(signing_key)), encoding="utf-8")
    resolved = oauth.resolve_oauth_binding(
        {
            oauth.RESOURCE_ENV: RESOURCE,
            oauth.ISSUER_ENV: ISSUER,
            oauth.TOKEN_VERIFIER_ENV: oauth.FILE_TOKEN_VERIFIER,
            oauth.JWKS_FILE_ENV: str(jwks_path),
        },
        "",
    )
    compact = minted(signing_key)
    principal = resolved.authenticate(Credential(scheme="Bearer", token=compact))
    assert compact not in repr(principal)


# --- 5. no outbound call, and the seam that would enable one is unset --------


def test_the_jwks_fetch_seam_is_unset_and_nothing_in_the_repository_assigns_it():
    """The seam is REAL — ``jwks-url`` is a recognised selection with a written
    branch — and it is UNARMED. Asserted against the source rather than only
    against the value, so an assignment executed at import time somewhere else
    could not satisfy it."""
    assert oauth.JWKS_FETCHER is None
    for path in sorted(MCP_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == "JWKS_FETCHER":
                    value = getattr(node, "value", None)
                    assert isinstance(value, ast.Constant) and value.value is None, (
                        f"{path.name} assigns JWKS_FETCHER a non-None value"
                    )


@pytest.mark.parametrize("module", ["jwt.py", "oauth.py"])
def test_the_token_verification_modules_import_no_networking_at_all(module):
    """Not "make no call" — import nothing that could make one. ``httpx`` is
    permitted elsewhere in this package (``client.py`` reaches ISAAC's own routes
    in-process over an ASGI transport); it has no business here."""
    forbidden = {
        "socket",
        "ssl",
        "http",
        "http.client",
        "httpx",
        "urllib.request",
        "urllib.error",
        "asyncio",
        "requests",
        "ftplib",
        "smtplib",
        "telnetlib",
        "xmlrpc",
    }
    # `urllib.parse` is deliberately NOT forbidden and is deliberately not
    # matched by a prefix rule: it is a string parser with no I/O, `oauth.py`
    # uses `urlsplit` to validate a canonical URI, and forbidding the package
    # root would either ban that or force a hand-rolled URL parser — which is a
    # worse trade in a module whose whole job is refusing malformed input.
    tree = ast.parse((MCP_PACKAGE / module).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module)
            imported.add(node.module.split(".")[0])
    assert not (imported & forbidden), sorted(imported & forbidden)
    # …and the exemption is narrow, not a hole: `urllib.parse` is the ONLY
    # `urllib` submodule either module may name.
    assert not [
        name
        for name in imported
        if name.startswith("urllib") and name not in ("urllib", "urllib.parse")
    ]


def test_the_seam_is_real_and_is_only_reachable_by_installing_a_fetcher(
    monkeypatch, signing_key
):
    """A seam nothing can drive is not a seam — it is unreviewable dead code.

    Installing a callable makes the whole path work, so the shape a future
    authorized slice fills in is proven rather than asserted. The callable here
    is a Python function returning a dict: **no socket is opened by this test**,
    and none is opened by ``FetchedKeySource``, which calls whatever it was given
    and makes no I/O decision of its own.
    """
    calls: list[str] = []

    def fake_fetch(url: str):
        calls.append(url)
        return keys.jwks(signing_key)

    monkeypatch.setattr(oauth, "JWKS_FETCHER", fake_fetch)
    resolved = oauth.resolve_oauth_binding(
        {
            oauth.RESOURCE_ENV: RESOURCE,
            oauth.ISSUER_ENV: ISSUER,
            oauth.TOKEN_VERIFIER_ENV: oauth.URL_TOKEN_VERIFIER,
            oauth.JWKS_URL_ENV: "https://auth.example.invalid/jwks",
        },
        "",
    )
    assert not isinstance(resolved, str), resolved
    principal = resolved.authenticate(
        Credential(scheme="Bearer", token=minted(signing_key))
    )
    assert principal.subject == SENTINEL_SECRET
    # …and the key set is cached, so a second request does not re-fetch.
    resolved.authenticate(Credential(scheme="Bearer", token=minted(signing_key)))
    assert calls == ["https://auth.example.invalid/jwks"]


def test_a_fetcher_that_fails_refuses_every_token_and_names_nothing(
    monkeypatch, signing_key
):
    """A stale cache is deliberately NOT served on a failed refresh: a key set
    that cannot be re-fetched may be one that was revoked. And the exception is
    never interpolated — it could carry a URL, a hostname or a response body, and
    this message reaches a 401."""

    def angry_fetch(url: str):
        raise RuntimeError(f"connect to {url} failed: {SENTINEL_SECRET}")

    monkeypatch.setattr(oauth, "JWKS_FETCHER", angry_fetch)
    resolved = oauth.resolve_oauth_binding(
        {
            oauth.RESOURCE_ENV: RESOURCE,
            oauth.ISSUER_ENV: ISSUER,
            oauth.TOKEN_VERIFIER_ENV: oauth.URL_TOKEN_VERIFIER,
            oauth.JWKS_URL_ENV: "https://auth.example.invalid/jwks",
        },
        "",
    )
    from isaac_api.mcp.deployment import DeploymentRefused

    with pytest.raises(DeploymentRefused) as caught:
        resolved.authenticate(Credential(scheme="Bearer", token=minted(signing_key)))
    assert caught.value.code == "no_usable_jwks_key"
    assert SENTINEL_SECRET not in json.dumps(caught.value.data)
    assert SENTINEL_SECRET not in caught.value.message


def test_selecting_the_url_key_source_refuses_rather_than_reaching_for_one(tmp_path):
    """The end-to-end consequence: an operator who configures ``jwks-url`` gets a
    container that will not boot, naming the local alternative — not a process
    that quietly makes an outbound request at first token."""
    with pytest.raises(RuntimeError) as caught:
        oauth.validate_oauth_selection_or_raise(
            {
                oauth.RESOURCE_ENV: RESOURCE,
                oauth.ISSUER_ENV: ISSUER,
                oauth.TOKEN_VERIFIER_ENV: oauth.URL_TOKEN_VERIFIER,
                oauth.JWKS_URL_ENV: "https://auth.example.invalid/jwks",
            },
            "",
        )
    assert "makes no outbound request" in str(caught.value)
    assert oauth.FILE_TOKEN_VERIFIER in str(caught.value)


# =============================================================================
# 6. THE SAME QUESTION, ASKED OF THE WHOLE APPLICATION (added 2026-08-30)
# =============================================================================
#
# Section 5 above proves `jwt.py` and `oauth.py` import nothing that could open a
# socket. That is the right claim for the two modules that handle a credential —
# and it is silent about the other 50-odd modules in this package, any one of which
# could make an outbound call from a route. This section extends the same
# STRUCTURAL method to the whole of `apps/api/isaac_api/`, rather than adding a
# second file with a second definition of "outbound".
#
# Measured 2026-08-30 over every `.py` under the package: FOUR modules name an
# outbound-capable client, and all four are accounted for below. Nothing is
# mocked; the assertions are over the source.

API_PACKAGE = MCP_PACKAGE.parent

#: Modules that may open a socket, and the ONLY reason each may.
#:
#: * The three ``db_*`` modules use ``psycopg2`` — the deployment-mediated
#:   PostgreSQL path ``CLAUDE.md`` §15 authorizes, reachable only where the libpq
#:   environment is set, which no default deployment sets.
#: * ``mcp/client.py`` uses ``httpx`` against an **in-process ASGI transport** — it
#:   reaches ISAAC's own routes without a socket at all, which
#:   :func:`test_the_one_httpx_client_is_bound_to_the_app_and_never_to_a_host`
#:   asserts rather than assumes.
#:
#: The map is exact in BOTH directions: a module listed here that stops importing
#: its client is as much a failure as a module that starts, because a stale
#: exemption is how the next one gets waved through.
OUTBOUND_EXEMPTIONS = {
    "db_provider.py": {"psycopg2"},
    "db_recon.py": {"psycopg2"},
    "db_write.py": {"psycopg2"},
    "mcp/client.py": {"httpx"},
}

#: Every module that could carry a request off this machine. ``urllib.parse`` is
#: deliberately absent for the reason section 5 gives: it is a string parser with
#: no I/O, and banning the package root would force a hand-rolled URL parser.
OUTBOUND_CAPABLE = {
    "aiohttp",
    "boto3",
    "ftplib",
    "http",
    "http.client",
    "httpx",
    "paramiko",
    "psycopg",
    "psycopg2",
    "requests",
    "smtplib",
    "socket",
    "ssl",
    "telnetlib",
    "urllib.error",
    "urllib.request",
    "urllib3",
    "websockets",
    "xmlrpc",
}


def _imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            names.add(node.module.split(".")[0])
    return names


def test_no_module_in_the_api_package_imports_an_outbound_client_unexpectedly():
    """Package-wide, and exact in both directions.

    Every ``.py`` under ``apps/api/isaac_api/`` is parsed and its imports compared
    against :data:`OUTBOUND_CAPABLE`. A module that names one must appear in
    :data:`OUTBOUND_EXEMPTIONS` with exactly the clients it names — and a module in
    that map that no longer names its client fails too, because a stale exemption is
    how the next outbound import gets waved through.

    Measured 2026-08-30: four modules, three ``psycopg2`` and one ``httpx``, and
    nothing else in the package.

    MUTATION, both directions, both run:

    * adding ``import http.client`` to ``isaac_api/workflow.py``::

          AssertionError: unexpected outbound-capable import(s):
          {'workflow.py': ['http', 'http.client']}

    * adding a ``"workflow.py": {"requests"}`` entry to
      :data:`OUTBOUND_EXEMPTIONS` that no module earns::

          AssertionError: stale exemption(s) — the module no longer imports it:
          {'workflow.py': ['requests']}

    *``requests`` was the first choice for the first mutation and is not installed
    in this environment, so importing it failed at collection (exit 4) rather than
    at the assertion — a mutation that breaks the test run proves nothing. The
    stdlib ``http.client`` is the equivalent weakening that actually runs.*
    """
    unexpected = {}
    stale = {}
    scanned = 0
    for path in sorted(API_PACKAGE.rglob("*.py")):
        scanned += 1
        rel = str(path.relative_to(API_PACKAGE))
        found = _imported_names(path) & OUTBOUND_CAPABLE
        allowed = OUTBOUND_EXEMPTIONS.get(rel, set())
        if found - allowed:
            unexpected[rel] = sorted(found - allowed)
        if allowed - found:
            stale[rel] = sorted(allowed - found)
    assert not unexpected, f"unexpected outbound-capable import(s): {unexpected}"
    assert not stale, f"stale exemption(s) — the module no longer imports it: {stale}"
    assert scanned >= 40, scanned


def test_the_one_httpx_client_is_bound_to_the_app_and_never_to_a_host():
    """``httpx`` is in this package, and it cannot reach the network.

    ``mcp/client.py`` is the only module that imports it, and every client it
    constructs is handed an ``ASGITransport`` — which dispatches into the in-process
    FastAPI application object and opens no socket. Asserted over the AST, so a
    future ``httpx.AsyncClient(base_url="https://…")`` with no transport fails here
    rather than at the first request.

    Measured 2026-08-30: one ``ASGITransport(app=…)`` and one
    ``AsyncClient(base_url=…, timeout=…, transport=…)`` — the only two such calls in
    the module.

    MUTATION: deleting ``transport=transport`` from the ``AsyncClient(...)`` call
    turns this RED::

        AssertionError: httpx client at line 213 has no transport= — it would open
        a socket
        assert 'transport' in {'base_url', 'timeout'}
    """
    source = (API_PACKAGE / "mcp" / "client.py").read_text(encoding="utf-8")
    constructions = 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", getattr(node.func, "id", None))
        if name not in ("AsyncClient", "Client"):
            continue
        constructions += 1
        keywords = {kw.arg for kw in node.keywords if kw.arg}
        assert "transport" in keywords, (
            f"httpx client at line {node.lineno} has no transport= — "
            "it would open a socket"
        )
    assert constructions == 1, f"expected exactly one httpx client, found {constructions}"
    assert "ASGITransport" in source


def test_every_provider_seam_is_unconfigured_so_no_route_can_call_out(monkeypatch):
    """The seams that WOULD make an outbound call, reported by the application
    itself.

    ``test_providers.py`` covers the resolution rules in depth. What is asserted
    here — in the file about egress — is the one consequence that matters for this
    section: on the default environment every seam reports ``configured: false``
    with a reason, so no route has a provider to call.

    MUTATION: making every seam report itself configured (``"configured": True or
    …`` in ``providers/config.py``) turns this RED at the top-level roll-up, before
    any per-seam assertion::

        AssertionError: {'any_provider_configured': True, 'decision_reference':
        'docs/ai-integration-decision-packet.md', 'seams': [{'seam': 'assistant',
        'implementation': 'unconfigured', 'configured': True, …}]}
        assert True is False

    Note which assertion catches it: the roll-up, not the per-seam loop. A caller
    reading only ``any_provider_configured`` is the one most likely to act on it, so
    it is the one that must be right.
    """
    from isaac_api import providers

    report = providers.capabilities()
    assert report["any_provider_configured"] is False, report
    seams = {entry["seam"]: entry for entry in report["seams"]}
    assert set(seams) == set(providers.SEAMS), sorted(seams)
    for seam, entry in seams.items():
        assert entry["configured"] is False, (seam, entry)
        assert entry["is_test_double"] is False, (seam, entry)
        assert entry["reason"], (seam, entry)


def test_no_openapi_description_quotes_an_environment_value(tmp_path, monkeypatch):
    """A secret set in the environment must not surface in the published contract.

    The OpenAPI document is the largest single body this application serves and is
    entirely author-written, which makes it the easiest place for a configuration
    value to be interpolated "for clarity". Every credential-shaped variable this
    build reads is set to a sentinel, the document is generated, and the sentinel
    must appear nowhere in it.

    MUTATION: passing ``terms_of_service=os.environ.get("ISAAC_UI_API_KEY")`` to
    ``FastAPI(...)`` in ``create_app`` turns this RED::

        AssertionError: an environment value reached the OpenAPI document
        assert 's3cret-AAAA…' not in '{"openapi":…"terms_of_service":
        "s3cret-AAAA…", "version": "0.1.0"}, "paths": …'

    *The obvious mutation — interpolating the value into a ROUTE description —
    does NOT work, and the reason is worth knowing: route decorators run at IMPORT
    time, before this test's ``monkeypatch`` sets anything, so the sentinel is
    never in the environment when the string is built. Only a value read inside
    ``create_app`` can carry it. That also bounds what this test can catch: an
    import-time leak of a variable set in the real deployment's environment would
    be invisible here.*
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("PGHOST", raising=False)
    for name in (
        "ISAAC_UI_API_KEY",
        "PGPASSWORD",
        oauth.JWKS_FILE_ENV,
        oauth.JWKS_URL_ENV,
    ):
        monkeypatch.setenv(name, SENTINEL_SECRET)

    from isaac_api.app import create_app

    document = json.dumps(create_app().openapi())
    assert SENTINEL_SECRET not in document, (
        "an environment value reached the OpenAPI document"
    )
    # The document must actually have been built, or this passes on an empty string.
    assert len(document) > 100_000, len(document)
