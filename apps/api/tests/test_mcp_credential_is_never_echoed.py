"""A schemeless ``Authorization`` header came back in full in the MCP ``401``.

THE DEFECT, AND WHY THE CLAIM ABOUT IT WAS ALREADY WRITTEN DOWN
===============================================================
``deployment.Credential`` carried this sentence: *"Deliberately opaque and
deliberately never logged or echoed: the refusal bodies in this module name the
scheme at most, never the token."* It described intent accurately and behaviour
inaccurately, and the whole gap was one call two modules away::

    scheme, _, token = raw.strip().partition(" ")

``str.partition`` returns ``(whole, "", "")`` when the separator is absent. So an
``Authorization`` header carrying a BARE token — no ``Bearer``, no space, which is
a shape real clients send, and the shape a raw JWT arrives in — assigned the
**entire credential** to ``scheme`` and left ``token`` empty. That is the exact
inverse of the parse's own docstring, which already said a malformed header
produces ``scheme=""``.

``LocalLoopbackBinding.authenticate`` then reported that "scheme" in the ``data``
of its ``credential_not_verifiable`` refusal, because the scheme is the one member
it is allowed to report. Measured over the mounted transport: a 48-character
stand-in JWT came back verbatim in the body of the ``401``.

WHY THE EXISTING TEST COULD NOT SEE IT
======================================
``test_mcp_transport.py::test_a_credential_is_refused_rather_than_accepted_unvalidated``
sends ``"Bearer s3cret-value"`` and asserts ``"s3cret-value" not in response.text``.
That assertion is true, and true only of the well-formed shape it sends. The
defect lived entirely in the shape it did not send. **A test that pins the safe
case of a two-case parse reads as coverage of the parse.**

THE FIX IS TWO INDEPENDENT CONDITIONS, AND THIS FILE ASSERTS BOTH SEPARATELY
============================================================================
1. ``transport._credential_from`` now treats a delimiter-less value as a bare
   TOKEN with no scheme — which is what its own docstring always claimed.
2. ``deployment._reportable_scheme`` refuses to PUBLISH anything that is not a
   syntactic RFC 9110 ``auth-scheme``, whatever the parse produced.

They are not one condition written twice: (1) gets the parse right, (2) bounds
what may leave the process however the parse turns out — and (2) is what covers
``<secret> trailing``, which DOES have a delimiter and would otherwise put the
secret in ``scheme`` by a different route. §3 disables each and asserts the other
still holds, so neither can be deleted as redundant.
"""

from __future__ import annotations

import pytest

from isaac_api.mcp.deployment import (
    DEPLOYMENT_ENV,
    LOCAL_LOOPBACK,
    Credential,
    _reportable_scheme,
)
from isaac_api.mcp.transport import MCP_PATH, _credential_from

#: A value that looks like what it is: a bearer token somebody forgot to prefix.
BARE_JWT = "eyJhbGciOiJIUzI1NiJ9.SUPER-SECRET-JWT-BODY.c2lnbmF0dXJl"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return monkeypatch


def _mounted(monkeypatch):
    """The transport, mounted, with a loopback peer — as ``test_mcp_transport`` does."""
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app
    from test_mcp_transport import LOOPBACK_PEER

    monkeypatch.setenv(DEPLOYMENT_ENV, LOCAL_LOOPBACK)
    return TestClient(create_app(), client=LOOPBACK_PEER)


def _initialize(client, authorization: str):
    return client.post(
        MCP_PATH,
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"authorization": authorization},
    )


# =============================================================================
# 1. The reproduction, over the wire
# =============================================================================


def test_a_SCHEMELESS_bearer_token_is_not_echoed_in_the_401(workspace):
    """The measured defect, as a test. The whole token used to appear here."""
    client = _mounted(workspace)

    response = _initialize(client, BARE_JWT)

    assert response.status_code == 401, response.text
    assert response.json()["error"]["data"]["code"] == "credential_not_verifiable"
    assert BARE_JWT not in response.text, (
        "the schemeless Authorization header was echoed verbatim in the 401 body"
    )
    # Not a truncation either: a prefix of a secret is still a secret.
    assert BARE_JWT[:16] not in response.text


def test_the_refusal_still_HAPPENS_and_is_still_typed(workspace):
    """Redaction must not have been achieved by not refusing.

    The loopback binding cannot verify a credential and must go on saying so; a
    "fix" that dropped the credential would silently downgrade the request to
    anonymous, which the parse's own docstring names as the wrong direction.
    """
    client = _mounted(workspace)

    response = _initialize(client, BARE_JWT)

    assert response.status_code == 401
    data = response.json()["error"]["data"]
    assert data["code"] == "credential_not_verifiable"
    assert data["binding"] == LOCAL_LOOPBACK
    assert data["scheme"] == ""
    # And no invented challenge, exactly as before.
    assert "www-authenticate" not in {k.lower() for k in response.headers}


def test_a_WELL_FORMED_scheme_is_still_reported(workspace):
    """The negative control: the ``scheme`` member is not simply blanked.

    Reporting the scheme is useful and deliberate — it tells a caller which
    mechanism was rejected. A fix that always emitted ``""`` would pass every
    assertion above while destroying the field's purpose.
    """
    client = _mounted(workspace)

    response = _initialize(client, "Bearer s3cret-value")

    assert response.status_code == 401
    assert response.json()["error"]["data"]["scheme"] == "Bearer"
    assert "s3cret-value" not in response.text


# =============================================================================
# 2. The parse, directly
# =============================================================================


@pytest.mark.parametrize(
    "raw, scheme, token",
    [
        ("Bearer abc", "Bearer", "abc"),
        ("  Bearer   abc  ", "Bearer", "abc"),
        ("Basic dXNlcjpwdw==", "Basic", "dXNlcjpwdw=="),
        # THE DEFECT'S OWN SHAPE: no delimiter -> no scheme, and the value is the
        # TOKEN, where it is opaque and never published.
        (BARE_JWT, "", BARE_JWT),
        ("opaque-secret", "", "opaque-secret"),
    ],
)
def test_the_parse_assigns_a_schemeless_value_to_the_TOKEN(raw, scheme, token):
    credential = _credential_from({"authorization": raw})

    assert credential is not None
    assert credential.scheme == scheme
    assert credential.token == token


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_an_absent_or_empty_header_is_still_NO_CREDENTIAL(raw):
    """Unchanged behaviour, asserted so the parse edit cannot have moved it."""
    assert _credential_from({"authorization": raw} if raw is not None else {}) is None


# =============================================================================
# 3. Each condition alone — neither is redundant
# =============================================================================


@pytest.mark.parametrize(
    "scheme, reportable",
    [
        ("Bearer", "Bearer"),
        ("Basic", "Basic"),
        ("Negotiate", "Negotiate"),
        ("DPoP", "DPoP"),
        ("", ""),
        (BARE_JWT, ""),  # contains `.` and `-`, and is far too long
        ("A" * 33, ""),  # over the bound
        ("A" * 32, "A" * 32),  # at the bound
        ("1Bearer", ""),  # must start with an alpha
        ("Bearer abc", ""),  # a space is not in `token`
    ],
)
def test_reportable_scheme_publishes_only_a_real_auth_scheme(scheme, reportable):
    """Condition 2 in isolation. It is an ALLOWLIST, not a length cap.

    A cap alone would publish the first 32 characters of a secret, which is not a
    redaction; a non-scheme is replaced rather than truncated so a reader cannot
    mistake a fragment for the real header.
    """
    assert _reportable_scheme(scheme) == reportable


def test_the_PUBLISH_GUARD_holds_even_if_the_PARSE_regressed(workspace):
    """Condition 2 covers a shape condition 1 does not: ``<secret> trailing``.

    This value HAS a delimiter, so the parse — correctly — puts the first word in
    ``scheme``. Only ``_reportable_scheme`` stops it being published. If someone
    later decides the parse fix alone was sufficient, this fails.
    """
    client = _mounted(workspace)

    response = _initialize(client, f"{BARE_JWT} trailing")

    assert response.status_code == 401
    assert BARE_JWT not in response.text
    assert response.json()["error"]["data"]["scheme"] == ""


def test_the_PARSE_FIX_holds_independently_of_the_publish_guard():
    """Condition 1 in isolation, asserted on the ``Credential`` itself.

    Even with ``_reportable_scheme`` out of the picture entirely, a bare token must
    not be sitting in the ``scheme`` member — because ``scheme`` is the member this
    package's own contract says may be named.
    """
    credential = _credential_from({"authorization": BARE_JWT})

    assert credential == Credential(scheme="", token=BARE_JWT)
    assert BARE_JWT not in credential.scheme
