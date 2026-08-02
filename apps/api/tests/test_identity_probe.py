"""Safety tests for the TEMPORARY identity-observation probe.

``POST /api/runtime/identity/probe`` plus the pure module behind it,
``isaac_api.identity_probe``.

NO real identity, NO real header, NO network, NO Authentik. Every value planted
in a request below is an obviously-synthetic sentinel, chosen so that a leak is
unmissable in a diff and so that nothing here resembles a real SLAC username,
email, group, or token.

What these tests are for
------------------------
The probe's whole job is to report PRESENCE and nothing else. So the suite is
weighted towards proving *absence*: that no header value, no fragment of one, no
lowercase/uppercase/url-encoded/base64/sha256 derivative of one, no
`Authorization`, no `Cookie`, no canary, and no non-allowlisted header NAME can
reach the response body or the log. The functional tests (shape, precedence,
canary survival) exist to make the probe useful; the leak tests exist to make it
safe, and they are the ones that must never be weakened.

The strongest assertion in the file is not a substring scan. It is
``test_ok_response_is_exactly_the_predicted_document``: the entire response is
compared against a document built from module constants, so anything extra —
anticipated or not — fails.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from isaac_api import identity_probe, routes

PROBE_PATH = "/api/runtime/identity/probe"


# --- obviously-synthetic sentinels -------------------------------------------
# Every one of these must be absent from every response body and every log line.

S_USERNAME = "synthetic-user-aaa"
S_UID = "synthetic-uid-bbb"
S_EMAIL = "synthetic-mailbox-ccc@example.invalid"
S_NAME = "Synthetic Persona Ddd"
S_GROUPS = "grp-alpha|grp-beta"
S_ENTITLEMENTS = "ent-gamma,ent-delta"
S_EDGE = "synthetic-edge-marker-eee"

S_AUTHORIZATION = "Bearer synthetic-token-fff"
S_COOKIE = "synthetic_session=ggg-hhh"
S_UNLISTED = "synthetic-unlisted-iii"
S_CANARY = "synthetic-canary-jjj"

UNLISTED_HEADER = "X-Synthetic-Not-Allowlisted"

#: The full sentinel set, plus the two header NAMES that must never be named.
SENTINELS = (
    S_USERNAME,
    S_UID,
    S_EMAIL,
    S_NAME,
    S_GROUPS,
    S_ENTITLEMENTS,
    S_EDGE,
    S_AUTHORIZATION,
    S_COOKIE,
    S_UNLISTED,
    S_CANARY,
    UNLISTED_HEADER,
    # Distinctive fragments: a leak that split or reformatted a value still trips.
    "grp-alpha",
    "grp-beta",
    "ent-gamma",
    "ent-delta",
    "example.invalid",
    "synthetic",
)

#: Exactly what the frozen top-level allowlist promises.
EXPECTED_TOP_LEVEL_KEYS = {
    "status",
    "probe_contract_version",
    "app_commit",
    "generated_at",
    "edge_path_expectation",
    "claims",
    "limitations",
}

#: Exactly what the frozen per-claim allowlist promises.
EXPECTED_CLAIM_KEYS = {
    "claim",
    "header",
    "present",
    "shape",
    "consumed_by_isaac",
    "client_canary_survived",
}


def all_candidate_headers() -> list[tuple[str, str]]:
    """One synthetic sentinel in every allowlisted candidate header."""
    return [
        ("X-authentik-username", S_USERNAME),
        ("X-authentik-uid", S_UID),
        ("X-authentik-email", S_EMAIL),
        ("X-authentik-name", S_NAME),
        ("X-authentik-groups", S_GROUPS),
        ("X-authentik-entitlements", S_ENTITLEMENTS),
        ("X-Isaac-Edge", S_EDGE),
    ]


def leak_variants(value: str) -> list[str]:
    """The forms a value could plausibly be leaked in.

    A hash or an encoding is still a value-derived disclosure — the module
    docstring forbids "not truncated, not hashed, not fingerprinted" — so a
    response that merely *encoded* a sentinel must fail exactly as loudly as one
    that echoed it.
    """
    return [
        value,
        value.lower(),
        value.upper(),
        urllib.parse.quote(value, safe=""),
        base64.b64encode(value.encode("utf-8")).decode("ascii"),
        hashlib.sha256(value.encode("utf-8")).hexdigest(),
    ]


def assert_no_sentinel(text: str, *, where: str) -> None:
    for sentinel in SENTINELS:
        for variant in leak_variants(sentinel):
            assert variant not in text, f"{where} leaked a form of {sentinel!r}"


# --- fixtures -----------------------------------------------------------------


def _make_client(tmp_path, monkeypatch, *, enabled=True, base=None, api_key=None):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    if api_key is None:
        monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ISAAC_UI_API_KEY", api_key)
    if base is None:
        monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    else:
        monkeypatch.setenv("ISAAC_BASE_PATH", base)
    monkeypatch.delenv("ISAAC_STATIC_DIR", raising=False)
    # The switch is a KILL switch: absent means observing. `enabled=True`
    # therefore clears it rather than setting it, so the default path — the one
    # every environment actually runs — is what most of this suite exercises.
    if enabled:
        monkeypatch.delenv("ISAAC_IDENTITY_PROBE", raising=False)
    else:
        monkeypatch.setenv("ISAAC_IDENTITY_PROBE", "0")
    from isaac_api.app import create_app

    return TestClient(create_app())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The probe ENABLED — the deployment-switch-on case."""
    return _make_client(tmp_path, monkeypatch, enabled=True)


@pytest.fixture()
def disabled_client(tmp_path, monkeypatch):
    """`ISAAC_IDENTITY_PROBE=0` — the explicit opt-out. NOT the default: absent
    means observing, so this fixture models a deployment that has deliberately
    switched the probe off rather than one that simply never configured it."""
    return _make_client(tmp_path, monkeypatch, enabled=False)


def probe(client, *, headers=None, body=None):
    return client.post(PROBE_PATH, json=body if body is not None else {}, headers=headers)


def claims_by_header(payload: dict) -> dict[str, dict]:
    return {claim["header"]: claim for claim in payload["claims"]}


# --- 1. the candidate allowlist is frozen and evidence-derived ----------------


def test_candidate_allowlist_is_exactly_the_seven_evidence_derived_names():
    assert identity_probe.CANDIDATE_HEADERS == (
        "X-authentik-username",
        "X-authentik-uid",
        "X-authentik-email",
        "X-authentik-name",
        "X-authentik-groups",
        "X-authentik-entitlements",
        "X-Isaac-Edge",
    )
    assert len(identity_probe.IDENTITY_CANDIDATES) == 7


def test_no_candidate_is_consumed_by_isaac_today():
    """`consumed_by_isaac` is DATA, not a guess.

    `docs/identity-trust-contract.md` §1.2 records that the backend reads exactly
    four request headers and that none is an identity header. If a future slice
    ever does read one, this test is the thing that must be updated in the same
    change — flipping the flag without flipping the reality, or the reverse, is
    the failure mode the field exists to prevent.
    """
    assert all(not c.consumed_by_isaac for c in identity_probe.IDENTITY_CANDIDATES)


def test_pii_bearing_marks_the_six_identity_claims_and_not_the_edge_marker():
    pii = {c.header for c in identity_probe.IDENTITY_CANDIDATES if c.pii_bearing}
    assert "X-Isaac-Edge" not in pii
    assert len(pii) == 6


# --- 2. shape classification (pure) -------------------------------------------


def test_shape_absent_for_missing_and_empty_list():
    assert identity_probe.classify_shape(None) == "absent"
    assert identity_probe.classify_shape([]) == "absent"


def test_shape_scalar():
    assert identity_probe.classify_shape([S_USERNAME]) == "scalar"


@pytest.mark.parametrize("value", ["grp-alpha,grp-beta", "grp-alpha|grp-beta"])
def test_shape_list_for_both_separators(value):
    """Authentik has used both `,` and `|` to join a multi-valued claim."""
    assert identity_probe.classify_shape([value]) == "list"


def test_shape_duplicate_when_the_header_arrives_twice():
    assert identity_probe.classify_shape([S_USERNAME, S_UID]) == "duplicate"


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty
        "   ",  # whitespace only
        "\t\n ",  # whitespace only, other kinds
        "synthetic\x00null",  # C0
        "synthetic\x07bell",  # C0
        "synthetic\x7fdel",  # DEL
        "synthetic\x85nel",  # C1
    ],
)
def test_shape_malformed(value):
    assert identity_probe.classify_shape([value]) == "malformed"


def test_shape_malformed_for_undecodable_bytes():
    assert identity_probe.classify_shape([b"\xff\xfe\xfd"]) == "malformed"


# --- 3. shape PRECEDENCE ------------------------------------------------------
#
# malformed > duplicate > list > scalar. Each test below is a case where two
# rules apply at once and the published precedence decides.


def test_precedence_tuple_is_the_published_order():
    assert identity_probe.SHAPE_PRECEDENCE == ("malformed", "duplicate", "list", "scalar")


def test_malformed_outranks_duplicate():
    assert identity_probe.classify_shape([S_USERNAME, "  "]) == "malformed"
    assert identity_probe.classify_shape(["  ", S_USERNAME]) == "malformed"


def test_malformed_outranks_list():
    assert identity_probe.classify_shape(["grp-alpha,grp-beta\x07"]) == "malformed"


def test_malformed_outranks_duplicate_and_list_together():
    assert identity_probe.classify_shape(["grp-alpha|grp-beta", ""]) == "malformed"


def test_duplicate_outranks_list():
    assert identity_probe.classify_shape(["grp-alpha,grp-beta", "grp-gamma"]) == "duplicate"


def test_list_outranks_scalar():
    assert identity_probe.classify_shape(["grp-alpha,grp-beta"]) == "list"


def test_every_shape_returned_is_on_the_published_set():
    for values in (None, [], [S_USERNAME], ["a,b"], ["a", "b"], [""], [b"\xff"]):
        assert identity_probe.classify_shape(values) in identity_probe.SHAPES


# --- 4. canary comparison -----------------------------------------------------


def test_canary_survives_when_the_value_is_byte_identical():
    assert identity_probe.canary_survived([S_CANARY], S_CANARY) is True


def test_canary_does_not_survive_when_stripped():
    assert identity_probe.canary_survived([], S_CANARY) is False
    assert identity_probe.canary_survived(None, S_CANARY) is False


def test_canary_does_not_survive_when_overwritten():
    assert identity_probe.canary_survived([S_USERNAME], S_CANARY) is False


def test_canary_detected_in_only_one_of_two_duplicate_values():
    """The `append` case: the ingress added its own value and left the forgery.

    This is the most dangerous of the three possible answers to trust-contract
    Q3, so it must not be masked by only inspecting the first or last copy.
    """
    assert identity_probe.canary_survived([S_USERNAME, S_CANARY], S_CANARY) is True
    assert identity_probe.canary_survived([S_CANARY, S_USERNAME], S_CANARY) is True


def test_canary_absent_or_blank_never_reports_survival():
    assert identity_probe.canary_survived([""], "") is False
    assert identity_probe.canary_survived([S_CANARY], None) is False


def test_canary_comparison_is_prefix_safe():
    assert identity_probe.canary_survived([S_CANARY + "x"], S_CANARY) is False
    assert identity_probe.canary_survived([S_CANARY[:-1]], S_CANARY) is False


# --- 5. the module reads ONLY the allowlisted names ---------------------------


def test_observe_requests_exactly_the_allowlisted_headers_in_order():
    """A projection, never a filter. `observe` may not ask for anything else."""
    asked: list[str] = []

    def recording_getlist(name):
        asked.append(name)
        return []

    identity_probe.observe(
        recording_getlist, None, app_commit=None, generated_at="2026-01-01T00:00:00Z"
    )
    assert tuple(asked) == identity_probe.CANDIDATE_HEADERS


# --- 6. frozen allowlists + projection ----------------------------------------


def test_strict_projection_raises_on_an_unlisted_response_key(monkeypatch):
    monkeypatch.setattr(
        identity_probe, "RESPONSE_KEYS", ("status",), raising=True
    )
    with pytest.raises(identity_probe.IdentityProbeError):
        identity_probe.build_response(
            status="ok",
            claims=[],
            app_commit=None,
            generated_at="2026-01-01T00:00:00Z",
            strict=True,
        )


def test_sanitized_envelope_never_raises_even_with_a_broken_allowlist(monkeypatch):
    """The envelope is what a strict raise degrades INTO, so it must not raise.

    If it did, a broken allowlist would escape as an unhandled 500 with a
    traceback instead of the sanitized envelope. Fail-closed has to include the
    closing. (Same reasoning as `routes.py`'s `_db_recon_database_block`.)
    """
    monkeypatch.setattr(identity_probe, "RESPONSE_KEYS", ("status", "nonexistent"))
    envelope = identity_probe.sanitized_envelope(
        "error", app_commit=None, generated_at="2026-01-01T00:00:00Z"
    )
    assert envelope["status"] == "error"
    assert envelope["nonexistent"] is None


def test_claim_projection_drops_an_unlisted_key_even_without_strict(monkeypatch):
    monkeypatch.setattr(identity_probe, "CLAIM_KEYS", ("claim", "shape"))
    claim = identity_probe.build_claim(
        identity_probe.IDENTITY_CANDIDATES[0], [S_USERNAME], None, strict=False
    )
    assert set(claim) == {"claim", "shape"}


# --- 7. the constant-universe guard -------------------------------------------


def test_constant_universe_guard_accepts_a_real_response():
    payload = identity_probe.observe(
        lambda name: [S_USERNAME], S_CANARY, app_commit="deadbeef", generated_at="t"
    )
    identity_probe.assert_only_constant_strings(payload)


def test_constant_universe_guard_rejects_a_planted_header_value():
    payload = identity_probe.observe(
        lambda name: [], None, app_commit=None, generated_at="t"
    )
    payload["claims"][0]["shape"] = S_USERNAME
    with pytest.raises(identity_probe.IdentityProbeError):
        identity_probe.assert_only_constant_strings(payload)


def test_constant_universe_guard_rejects_a_hash_of_a_header_value():
    """A digest is still a value-derived disclosure."""
    payload = identity_probe.observe(
        lambda name: [], None, app_commit=None, generated_at="t"
    )
    payload["claims"][0]["claim"] = hashlib.sha256(S_UID.encode()).hexdigest()
    with pytest.raises(identity_probe.IdentityProbeError):
        identity_probe.assert_only_constant_strings(payload)


def test_constant_universe_guard_rejects_an_unlisted_key():
    payload = identity_probe.observe(
        lambda name: [], None, app_commit=None, generated_at="t"
    )
    payload["header_count"] = 7
    with pytest.raises(identity_probe.IdentityProbeError):
        identity_probe.assert_only_constant_strings(payload)


def test_constant_universe_guard_allows_only_the_two_free_value_keys():
    assert identity_probe.FREE_VALUE_KEYS == ("app_commit", "generated_at")


# --- 8. HTTP: every candidate present / every candidate absent ----------------


def test_every_candidate_present(client):
    r = probe(client, headers=all_candidate_headers(), body={"canary": S_CANARY})
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ok"
    for claim in payload["claims"]:
        assert claim["present"] is True
        assert claim["shape"] in ("scalar", "list")


def test_every_candidate_absent(client):
    r = probe(client)
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ok"
    assert len(payload["claims"]) == 7
    for claim in payload["claims"]:
        assert claim["present"] is False
        assert claim["shape"] == "absent"
        assert claim["client_canary_survived"] is False


def test_shapes_over_http(client):
    headers = [
        ("X-authentik-username", S_USERNAME),  # scalar
        ("X-authentik-groups", S_GROUPS),  # list (|)
        ("X-authentik-entitlements", S_ENTITLEMENTS),  # list (,)
        ("X-authentik-uid", "  "),  # malformed
        ("X-authentik-email", S_EMAIL),  # duplicate ...
        ("X-authentik-email", S_UID),  # ... second copy
    ]
    payload = probe(client, headers=headers).json()
    shapes = {h: c["shape"] for h, c in claims_by_header(payload).items()}
    assert shapes["X-authentik-username"] == "scalar"
    assert shapes["X-authentik-groups"] == "list"
    assert shapes["X-authentik-entitlements"] == "list"
    assert shapes["X-authentik-uid"] == "malformed"
    assert shapes["X-authentik-email"] == "duplicate"
    assert shapes["X-authentik-name"] == "absent"


def test_canary_survival_over_http(client):
    """Survived in one header, overwritten in a second, absent from a third."""
    headers = [
        ("X-authentik-username", S_CANARY),
        ("X-authentik-uid", S_UID),
    ]
    payload = probe(client, headers=headers, body={"canary": S_CANARY}).json()
    by_header = claims_by_header(payload)
    assert by_header["X-authentik-username"]["client_canary_survived"] is True
    assert by_header["X-authentik-uid"]["client_canary_survived"] is False
    assert by_header["X-authentik-email"]["client_canary_survived"] is False


def test_canary_survival_in_one_of_two_duplicates_over_http(client):
    headers = [
        ("X-authentik-groups", S_GROUPS),
        ("X-authentik-groups", S_CANARY),
    ]
    payload = probe(client, headers=headers, body={"canary": S_CANARY}).json()
    claim = claims_by_header(payload)["X-authentik-groups"]
    assert claim["shape"] == "duplicate"
    assert claim["client_canary_survived"] is True


# --- 9. LEAK TESTS — the ones that must never be weakened ---------------------


def test_no_sentinel_in_the_serialized_response(client):
    """Plant a sentinel in EVERY candidate, plus Authorization, Cookie and an
    unlisted header, then prove none of them — in any form — comes back."""
    headers = all_candidate_headers() + [
        ("Authorization", S_AUTHORIZATION),
        ("Cookie", S_COOKIE),
        (UNLISTED_HEADER, S_UNLISTED),
        ("X-Filename", S_UNLISTED),
    ]
    r = probe(client, headers=headers, body={"canary": S_CANARY})
    assert r.status_code == 200
    assert_no_sentinel(r.text, where="response body")
    assert_no_sentinel(json.dumps(r.json(), ensure_ascii=False), where="re-serialized")
    assert_no_sentinel(json.dumps(dict(r.headers)), where="response headers")


def test_response_keys_are_exactly_the_frozen_allowlist(client):
    payload = probe(client, headers=all_candidate_headers()).json()
    assert set(payload) == EXPECTED_TOP_LEVEL_KEYS
    for claim in payload["claims"]:
        assert set(claim) == EXPECTED_CLAIM_KEYS


def test_ok_response_is_exactly_the_predicted_document(client):
    """The strongest assertion here: full equality against a document built from
    module constants. Anything extra — anticipated or not — fails."""
    payload = probe(
        client,
        headers=[("X-authentik-username", S_USERNAME)],
        body={"canary": S_CANARY},
    ).json()
    payload.pop("generated_at")
    payload.pop("app_commit")
    expected_claims = []
    for candidate in identity_probe.IDENTITY_CANDIDATES:
        present = candidate.header == "X-authentik-username"
        expected_claims.append(
            {
                "claim": candidate.claim,
                "header": candidate.header,
                "present": present,
                "shape": "scalar" if present else "absent",
                "consumed_by_isaac": False,
                "client_canary_survived": False,
            }
        )
    assert payload == {
        "status": "ok",
        "probe_contract_version": identity_probe.PROBE_CONTRACT_VERSION,
        "edge_path_expectation": identity_probe.EDGE_PATH_EXPECTATION,
        "claims": expected_claims,
        "limitations": list(identity_probe.LIMITATIONS),
    }


def test_unlisted_header_makes_no_observable_difference_to_the_response(client):
    """A projection cannot leak a name; a filter could. This pins the difference."""
    without = probe(client).json()
    with_extra = probe(client, headers=[(UNLISTED_HEADER, S_UNLISTED)]).json()
    without.pop("generated_at")
    with_extra.pop("generated_at")
    assert without == with_extra


def test_unlisted_header_name_never_appears(client):
    r = probe(client, headers=[(UNLISTED_HEADER, S_UNLISTED)])
    for form in (UNLISTED_HEADER, UNLISTED_HEADER.lower(), UNLISTED_HEADER.upper()):
        assert form not in r.text


def test_no_count_of_headers_or_values_is_reported(client):
    """A count fingerprints the ingress configuration, so it is not disclosed.

    Checked structurally rather than by scanning the prose: the `limitations`
    strings legitimately contain the words "count" and "character count",
    because saying what is withheld requires naming it.
    """
    payload = probe(client, headers=all_candidate_headers()).json()

    def walk(node, key=None):
        if isinstance(node, dict):
            for k, v in node.items():
                assert "count" not in k and "length" not in k, f"suspicious key {k!r}"
                walk(v, k)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, bool) or node is None or isinstance(node, str):
            return
        elif isinstance(node, int):
            # The ONLY integer in the payload is the code-constant contract
            # version. Any other number would be derived from the request.
            assert key == "probe_contract_version", f"unexpected integer at {key!r}"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unexpected type {type(node)!r} at {key!r}")

    walk(payload)


def test_canary_is_never_echoed(client):
    r = probe(client, body={"canary": S_CANARY})
    assert S_CANARY not in r.text


def test_oversized_canary_is_refused_without_echo(client):
    oversized = "z" * (identity_probe.MAX_CANARY_LENGTH + 1)
    r = probe(client, body={"canary": oversized})
    assert r.status_code == 400
    assert r.json()["error"] == "canary_too_long"
    assert oversized not in r.text


def test_canary_at_the_limit_is_accepted(client):
    at_limit = "z" * identity_probe.MAX_CANARY_LENGTH
    r = probe(client, headers=[("X-authentik-uid", at_limit)], body={"canary": at_limit})
    assert r.status_code == 200
    assert claims_by_header(r.json())["X-authentik-uid"]["client_canary_survived"] is True


def test_extra_body_field_is_forbidden(client):
    """`extra="forbid"`.

    KNOWN AND DOCUMENTED: FastAPI's 422 for a rejected extra field echoes that
    field's value back in `detail[].input`. That reflection is the CALLER'S OWN
    input returning to the CALLER over the same connection — it is not a
    server-side disclosure, it is not logged, and it reaches no third party. It
    is pinned here so it stays visible rather than being discovered later, and
    it is why the canary's length bound is enforced in the handler instead of by
    a Pydantic `max_length`, which would route an oversized canary through this
    same echoing path. See `docs/identity-probe.md`.
    """
    r = probe(client, body={"canary": S_CANARY, "unexpected": "synthetic-extra-kkk"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "extra_forbidden"


# --- 10. logging --------------------------------------------------------------


def test_no_sentinel_reaches_any_log_record(client, caplog):
    headers = all_candidate_headers() + [
        ("Authorization", S_AUTHORIZATION),
        ("Cookie", S_COOKIE),
        (UNLISTED_HEADER, S_UNLISTED),
    ]
    with caplog.at_level(logging.DEBUG):
        r = probe(client, headers=headers, body={"canary": S_CANARY})
    assert r.status_code == 200
    assert caplog.records, "expected at least the probe's own outcome line"
    for record in caplog.records:
        assert_no_sentinel(record.getMessage(), where="log message")
        assert_no_sentinel(repr(record.args), where="log args")


def test_probe_logs_only_an_outcome(client, caplog):
    with caplog.at_level(logging.DEBUG, logger="isaac_api.identity_probe"):
        probe(client, headers=all_candidate_headers(), body={"canary": S_CANARY})
    messages = [r.getMessage() for r in caplog.records if r.name == "isaac_api.identity_probe"]
    assert messages == ["identity_probe outcome=ok"]


# --- 11. the error path -------------------------------------------------------


def test_error_path_returns_the_sanitized_envelope(client, monkeypatch, caplog):
    """An exception carrying header content must not reach the caller or the log."""

    def boom(*args, **kwargs):
        raise RuntimeError(
            f"FATAL for {S_USERNAME} <{S_EMAIL}> groups={S_GROUPS} "
            f"auth={S_AUTHORIZATION} canary={S_CANARY}"
        )

    monkeypatch.setattr(identity_probe, "observe", boom)
    with caplog.at_level(logging.DEBUG):
        r = probe(client, headers=all_candidate_headers(), body={"canary": S_CANARY})
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "error"
    assert set(payload) == EXPECTED_TOP_LEVEL_KEYS
    assert payload["claims"] == []
    assert_no_sentinel(r.text, where="error response")
    for record in caplog.records:
        assert_no_sentinel(record.getMessage(), where="error log message")
        assert_no_sentinel(repr(record.args), where="error log args")


def test_error_log_names_the_exception_class_only(client, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ValueError(S_USERNAME)

    monkeypatch.setattr(identity_probe, "observe", boom)
    with caplog.at_level(logging.DEBUG, logger="isaac_api.identity_probe"):
        probe(client)
    messages = [r.getMessage() for r in caplog.records if r.name == "isaac_api.identity_probe"]
    assert messages == ["identity_probe outcome=error type=ValueError"]


def test_leak_guard_failure_degrades_to_the_sanitized_envelope(client, monkeypatch):
    """If the constant-universe guard ever trips, the response must collapse."""

    def tripwire(payload, **kwargs):
        raise identity_probe.IdentityProbeError("tripped")

    monkeypatch.setattr(identity_probe, "assert_only_constant_strings", tripwire)
    payload = probe(client, headers=all_candidate_headers()).json()
    assert payload["status"] == "error"
    assert payload["claims"] == []


# --- 12. the deployment kill switch (default ON) ------------------------------
#
# The polarity is inverted relative to `docs/identity-trust-contract.md` §8,
# which specified default OFF. Recorded in the route's section comment: turning a
# default-OFF switch on means an `isaac-k8` edit, which the authorising
# instruction for this slice forbade, so a default-OFF probe could never observe
# anything. The switch is retained as a kill switch — disabling needs no code
# deploy — and the safety burden is carried by the response being incapable of
# carrying a value.


def test_explicitly_disabled_reports_disabled(disabled_client):
    payload = probe(disabled_client, headers=all_candidate_headers()).json()
    assert payload["status"] == "disabled"
    assert payload["claims"] == []
    assert set(payload) == EXPECTED_TOP_LEVEL_KEYS


def test_disabled_response_leaks_nothing(disabled_client):
    r = probe(
        disabled_client,
        headers=all_candidate_headers() + [("Authorization", S_AUTHORIZATION)],
        body={"canary": S_CANARY},
    )
    assert_no_sentinel(r.text, where="disabled response")


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " off "])
def test_switch_only_explicit_falsy_values_disable(value):
    assert routes._identity_probe_enabled({"ISAAC_IDENTITY_PROBE": value}) is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "", "maybe"])
def test_switch_anything_else_leaves_the_probe_observing(value):
    """An unrecognised value must fail towards ON, not OFF.

    A typo that silently muted the probe would return an empty `claims` list,
    which reads exactly like the substantive finding "no identity header
    reaches the application" — a wrong answer that looks like a real one. The
    empty string is included deliberately: `ISAAC_IDENTITY_PROBE=` in a manifest
    is a typo, not a considered decision to disable.
    """
    assert routes._identity_probe_enabled({"ISAAC_IDENTITY_PROBE": value}) is True


def test_switch_absent_is_on():
    assert routes._identity_probe_enabled({}) is True


# --- 13. deployment seams: base path and auth ---------------------------------


def test_reachable_under_a_non_empty_base_path(tmp_path, monkeypatch):
    c = _make_client(tmp_path, monkeypatch, enabled=True, base="/krish")
    r = c.post(
        "/krish/api/runtime/identity/probe",
        json={"canary": S_CANARY},
        headers=[("X-authentik-username", S_CANARY)],
    )
    assert r.status_code == 200
    assert claims_by_header(r.json())["X-authentik-username"]["client_canary_survived"] is True
    # The unprefixed path no longer exists.
    assert c.post(PROBE_PATH, json={}).status_code == 404


def test_probe_is_not_on_the_auth_middleware_open_path_list(tmp_path, monkeypatch):
    """`/api/health` stays open without credentials; the probe must not.

    The probe is an ingress-configuration oracle, so when a deployment does
    enable the shared key it must be behind it — unlike the health banner, which
    platform probes need unauthenticated.
    """
    c = _make_client(tmp_path, monkeypatch, enabled=True, api_key="demo-secret")
    assert c.get("/api/health").status_code == 200
    assert c.post(PROBE_PATH, json={}).status_code == 401
    ok = c.post(
        PROBE_PATH, json={}, headers={"Authorization": "Bearer demo-secret"}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"


def test_probe_is_read_only_get_is_not_allowed(client):
    """POST only — the canary must never travel in a logged query string."""
    assert client.get(PROBE_PATH).status_code == 405


# --- 14. the omitted field ----------------------------------------------------


def test_consistent_with_previous_request_is_not_implemented(client):
    """Deliberately absent: it would require retaining a per-value fingerprint
    across requests, which is a cross-request correlation surface. See the module
    docstring and `docs/identity-probe.md`."""
    payload = probe(client, headers=all_candidate_headers()).json()
    assert "consistent_with_previous_request" not in json.dumps(payload)
    for claim in payload["claims"]:
        assert "consistent_with_previous_request" not in claim
    assert not hasattr(identity_probe, "consistent_with_previous_request")


def test_two_identical_requests_are_indistinguishable(client):
    """No state is retained between calls, so the second response cannot differ."""
    headers = all_candidate_headers()
    first = probe(client, headers=headers).json()
    second = probe(client, headers=headers).json()
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


# --- 15. the paths the leak guard does NOT cover -------------------------------
#
# Added after independent security review. `assert_only_constant_strings` runs on
# the SUCCESS path only, so the 400 and 422 shapes are outside it. Both were
# verified clean by hand at the time; nothing pinned them, which meant a leak on
# either could have passed the whole suite. These tests close that.


def test_oversized_canary_rejection_leaks_nothing_with_all_headers_planted(client):
    """The 400 body is built from literals — pin it with every sentinel present.

    The existing over-long-canary test only checks that the canary is absent. This
    plants all seven candidate headers plus Authorization and Cookie, so a future
    edit that enriched the rejection with anything request-derived fails here.
    """
    response = client.post(
        PROBE_PATH,
        json={"canary": "z" * (identity_probe.MAX_CANARY_LENGTH + 1)},
        headers=dict(all_candidate_headers())
        | {
            "Authorization": S_AUTHORIZATION,
            "Cookie": S_COOKIE,
            UNLISTED_HEADER: S_UNLISTED,
        },
    )
    assert response.status_code == 400
    assert_no_sentinel(response.text, where="the 400 rejection body")
    assert UNLISTED_HEADER.lower() not in response.text.lower()


def test_fastapi_validation_error_never_surfaces_a_header(client):
    """FastAPI's own 422 echoes `detail[].input` — the CALLER'S OWN BODY.

    That is not a leak: same caller, same connection, no third party, and it is
    why the canary length bound is enforced in the handler rather than by a
    Pydantic `max_length` (which would route the canary through this echo). What
    must never happen is a HEADER reaching this path, since it bypasses the
    frozen projection entirely. Pinned across several malformed-body shapes.

    Note the body values below deliberately avoid the sentinel vocabulary: the
    echo of the caller's OWN body is expected here, so seeding it with a sentinel
    would make this test fail on the one behaviour it is not complaining about.
    The sentinels live only in the HEADERS, which is what is under test.
    """
    headers = dict(all_candidate_headers()) | {
        "Authorization": S_AUTHORIZATION,
        "Cookie": S_COOKIE,
        UNLISTED_HEADER: S_UNLISTED,
    }
    bodies = (
        {"canary": "ok", "extra": "caller-supplied-kkk"},
        {"canary": 12345},
        {"canary": {"nested": "caller-supplied-lll"}},
    )
    for body in bodies:
        response = client.post(PROBE_PATH, json=body, headers=headers)
        assert response.status_code == 422, body
        assert_no_sentinel(response.text, where=f"the 422 body for {body!r}")
        assert UNLISTED_HEADER.lower() not in response.text.lower()

    raw = client.post(
        PROBE_PATH, content="not json at all", headers=headers | {"Content-Type": "application/json"}
    )
    assert raw.status_code == 422
    assert_no_sentinel(raw.text, where="the 422 body for a non-JSON payload")


def test_disabled_probe_reads_no_header_at_all(disabled_client, monkeypatch):
    """`docs/identity-probe.md` §5 claims the switch is checked BEFORE any header
    is touched. Nothing pinned that — only that the response is empty, which a
    read-then-discard implementation would also satisfy. Recording every name the
    handler asks for proves the stronger claim."""
    asked: list[str] = []
    original = identity_probe.observe

    def recording_observe(getlist, *args, **kwargs):  # pragma: no cover - must not run
        asked.append("observe")
        return original(getlist, *args, **kwargs)

    monkeypatch.setattr(identity_probe, "observe", recording_observe)
    payload = probe(disabled_client, headers=all_candidate_headers()).json()
    assert payload["status"] == identity_probe.STATUS_DISABLED
    assert payload["claims"] == []
    assert asked == [], "the disabled path reached the header-reading code"


def test_a_query_string_canary_is_ignored(client):
    """The canary travels in the BODY because uvicorn's access log records the
    request line, query string included, but not the body (`Dockerfile:50`). If a
    future edit accepted `?canary=`, canaries would silently start being written
    to the pod's logs and the whole POST rationale would be defeated. Pin that a
    query-string canary has no effect."""
    headers = all_candidate_headers()
    with_query = client.post(
        f"{PROBE_PATH}?canary={S_CANARY}", json={}, headers=headers
    ).json()
    without = probe(client, headers=headers).json()
    for claim in with_query["claims"]:
        assert claim["client_canary_survived"] is False
    with_query.pop("generated_at")
    without.pop("generated_at")
    assert with_query == without


# --- 16. the coalescing case (independent review, finding I1) -----------------


def test_canary_is_detected_when_coalesced_into_a_list_value():
    """An intermediary that JOINS the client's forged copy with the injected one
    is the append attack in a different shape — and joining on `,` or `|` is
    exactly what Authentik does to groups and entitlements.

    A whole-value-only comparison reports False here. The operator would read
    "the ingress strips forged headers", record it as the answer to Q3, and a
    later authorization slice would rest on a survival that actually happened:
    the wrong answer in the unsafe direction, delivered confidently.
    """
    for value in (
        f"{S_CANARY},grp-real",
        f"grp-real|{S_CANARY}",
        f"grp-real, {S_CANARY} ,grp-other",
        f"grp-real|{S_CANARY},grp-other",
    ):
        assert identity_probe.canary_survived([value], S_CANARY) is True, value

    for value in ("grp-real,grp-other", f"prefix-{S_CANARY}-suffix", ""):
        assert identity_probe.canary_survived([value], S_CANARY) is False, value


def test_coalesced_canary_survival_is_visible_end_to_end(client):
    """The same case through the HTTP route, and still leaking nothing."""
    response = client.post(
        PROBE_PATH,
        json={"canary": S_CANARY},
        headers={"X-authentik-groups": f"grp-alpha,{S_CANARY}"},
    )
    assert response.status_code == 200
    payload = response.json()
    groups = claims_by_header(payload)["X-authentik-groups"]
    assert groups["present"] is True
    assert groups["shape"] == identity_probe.SHAPE_LIST
    assert groups["client_canary_survived"] is True
    assert S_CANARY not in response.text
    assert "grp-alpha" not in response.text
