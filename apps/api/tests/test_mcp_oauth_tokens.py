"""Access-token verification: every refusal is a defect-shaped negative control.

EACH TEST HERE NAMES AN ATTACK, NOT A BRANCH. That framing is deliberate — a test
called ``test_expired_is_refused`` reads as coverage, while a test that mints a
token whose ``exp`` has passed and asserts the server will not serve it reads as
the thing the server is for. Every case below is a token an attacker or a broken
client would actually present.

THE ONE PROPERTY THAT MAKES THE REST MEANINGFUL: the happy path in this file uses
the SAME verifier, the SAME key material and the SAME claim checks as production.
There is no bypass mode. A test double that accepted anything would make every
refusal below vacuous — it would prove that a rejector rejects, having removed the
acceptor it was supposed to be paired against.
"""

from __future__ import annotations

import json
import time

import pytest

from isaac_api.mcp import jwt as jwtmod
from isaac_api.mcp.jwt import (
    MAX_COMPACT_TOKEN_BYTES,
    SUPPORTED_ALGORITHMS,
    TokenRejected,
    jwks_from_document,
    verify_access_token,
)
import mcp_oauth_keys as keys

ISSUER = "https://auth.example.invalid/application/o/isaac"
RESOURCE = "https://isaac.example.invalid/api/mcp"
NOW = 1_800_000_000


@pytest.fixture(scope="session")
def primary():
    return keys.generate("isaac-signing-1", seed=keys.SEED)


@pytest.fixture(scope="session")
def other():
    """A second, unrelated key. The one an attacker would sign with."""
    return keys.generate("attacker-key", seed=keys.SEED + 1)


@pytest.fixture()
def key_set(primary):
    return jwks_from_document(keys.jwks(primary))


def claims(**overrides) -> dict:
    body = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "isaac-mcp-client",
        "exp": NOW + 600,
        "iat": NOW - 10,
        "scope": "isaac:read",
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not _ABSENT}


class _Absent:
    pass


_ABSENT = _Absent()


def verify(token, key_set, **overrides):
    kwargs = {
        "keys": key_set,
        "issuer": ISSUER,
        "resource": RESOURCE,
        "now": NOW,
    }
    kwargs.update(overrides)
    return verify_access_token(token, **kwargs)


def refusal(token, key_set, **overrides) -> TokenRejected:
    with pytest.raises(TokenRejected) as caught:
        verify(token, key_set, **overrides)
    return caught.value


# --- the acceptor, without which every refusal below proves nothing -----------


def test_a_correctly_issued_token_verifies_and_is_the_only_thing_that_does(
    primary, key_set
):
    verified = verify(keys.mint(primary, claims()), key_set)
    assert verified.subject == "isaac-mcp-client"
    assert verified.issuer == ISSUER
    assert verified.audiences == (RESOURCE,)
    assert verified.scope_strings == ("isaac:read",)
    assert verified.key_id == "isaac-signing-1"
    assert verified.algorithm == "RS256"


@pytest.mark.parametrize("algorithm", sorted(SUPPORTED_ALGORITHMS))
def test_every_advertised_algorithm_actually_verifies(primary, key_set, algorithm):
    """An allowlist entry nothing can satisfy is an allowlist entry that lies."""
    assert verify(keys.mint(primary, claims(), algorithm=algorithm), key_set)


# --- 1. no credential, and malformed ones ------------------------------------


@pytest.mark.parametrize("token", ["", "   ", None])
def test_an_absent_credential_is_refused_and_not_defaulted(key_set, token):
    assert refusal(token or "", key_set).code == "token_absent"


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "only.two",
        "a.b.c.d",
        "$$$.$$$.$$$",
        "..",
        ".eyJhIjoxfQ.sig",
    ],
)
def test_a_malformed_credential_is_refused_without_being_coaxed(key_set, token):
    assert refusal(token, key_set).code in {"malformed_token", "claims_malformed"}


def test_a_credential_with_a_well_formed_header_still_dies_at_the_signature(key_set):
    """The ordering guarantee, stated as a refusal CODE.

    ``eyJhbGciOiJSUzI1NiJ9..sig`` has a valid header and an empty payload. It is
    refused as ``bad_signature`` rather than as malformed, and that is correct:
    the signature is checked before the payload is looked at, so a caller cannot
    learn anything about how this server parses claims without first producing a
    signature only the issuer could produce.
    """
    assert refusal("eyJhbGciOiJSUzI1NiJ9..sig", key_set).code == "bad_signature"


def test_a_jwe_is_refused_rather_than_half_parsed(key_set):
    """Five segments is an encrypted token. This server decrypts nothing, so the
    honest answer names that rather than reporting a malformed signature."""
    assert refusal("a.b.c.d.e", key_set).code == "encrypted_token_unsupported"


def test_an_oversized_credential_is_refused_before_anything_is_decoded(key_set):
    assert refusal("x" * (MAX_COMPACT_TOKEN_BYTES + 1), key_set).code == "token_too_large"


def test_base64url_is_strict_so_a_standard_base64_segment_is_not_accepted(key_set):
    """``+`` and ``/`` are the standard alphabet, not base64url. Accepting them
    would mean two encodings of the same token, and two is one too many."""
    assert refusal("ey+/.ey+/.sig", key_set).code == "malformed_token"


# --- 2. the algorithm attacks ------------------------------------------------


def test_alg_none_is_refused_and_the_refusal_names_it(primary, key_set):
    """The oldest JWT attack there is. Named rather than merely missing from the
    allowlist, so a log line reads as an attack instead of as a typo."""
    rejected = refusal(keys.mint_unsecured(claims()), key_set)
    assert rejected.code == "algorithm_none"


@pytest.mark.parametrize("spelling", ["none", "None", "NONE", "nOnE", " none "])
def test_alg_none_is_refused_however_it_is_spelled(key_set, spelling):
    """Case-folding the comparison is what stops ``None`` sneaking past a check
    written against the lowercase literal."""
    header = keys.b64url(json.dumps({"alg": spelling}).encode())
    payload = keys.b64url(json.dumps(claims()).encode())
    assert refusal(f"{header}.{payload}.", key_set).code == "algorithm_none"


def test_hmac_algorithm_confusion_is_structurally_unreachable(primary, key_set):
    """``HS256`` MACed with the public modulus — the canonical confusion attack.

    Refused because this build implements **no** HMAC verifier: there is no code
    path that treats key material as a MAC secret, so the attack has nothing to
    reach. That is why the assertion is on ``algorithm_unsupported`` and not on a
    signature mismatch — a signature mismatch would mean the server *tried*.
    """
    rejected = refusal(keys.mint_hmac_confusion(primary, claims()), key_set)
    assert rejected.code == "algorithm_unsupported"


@pytest.mark.parametrize("algorithm", ["HS256", "HS512", "ES256", "EdDSA", "PS256", "RS1"])
def test_no_algorithm_outside_the_allowlist_is_attempted(key_set, algorithm):
    header = keys.b64url(json.dumps({"alg": algorithm}).encode())
    payload = keys.b64url(json.dumps(claims()).encode())
    assert refusal(f"{header}.{payload}.x", key_set).code == "algorithm_unsupported"


def test_a_key_that_declares_its_algorithm_binds_the_token_to_it(primary):
    """Second, independent barrier against substitution WITHIN the RSA family.

    The allowlist bounds the family; this bounds which member a given key may be
    used with, so a key published for ``RS512`` cannot be pressed into ``RS256``.
    """
    bound = jwks_from_document(keys.jwks(primary, algorithm="RS512"))
    assert verify(keys.mint(primary, claims(), algorithm="RS512"), bound)
    assert refusal(keys.mint(primary, claims(), algorithm="RS256"), bound).code == (
        "algorithm_mismatch"
    )


def test_a_crit_header_is_refused_because_this_build_understands_no_extension(
    primary, key_set
):
    token = keys.mint(primary, claims(), header_overrides={"crit": ["exp"]})
    assert refusal(token, key_set).code == "critical_header_unsupported"


def test_an_unrecognised_typ_is_refused(primary, key_set):
    token = keys.mint(primary, claims(), header_overrides={"typ": "JOSE+JSON"})
    assert refusal(token, key_set).code == "unsupported_typ"


@pytest.mark.parametrize("typ", ["at+jwt", "application/at+jwt", "JWT", "jwt", None])
def test_the_typ_values_real_issuers_mint_are_accepted(primary, key_set, typ):
    """``at+jwt`` is RFC 9068's; ``JWT`` is what most deployed servers emit.

    Accepting ``JWT`` admits the SHAPE of an OIDC ID token, which is why the
    audience check below is unconditional — that, not ``typ``, is what refuses
    one.
    """
    token = keys.mint(primary, claims(), header_overrides={"typ": typ})
    assert verify(token, key_set)


# --- 3. the signature --------------------------------------------------------


def test_a_tampered_signature_does_not_verify(primary, key_set):
    token = keys.mint(primary, claims(), tamper_signature=True)
    assert refusal(token, key_set).code == "bad_signature"


def test_a_token_signed_by_a_different_key_does_not_verify(primary, other, key_set):
    """The whole point of a signature, asserted rather than assumed."""
    token = keys.mint(primary, claims(), signing_key=other)
    assert refusal(token, key_set).code == "bad_signature"


def test_a_tampered_payload_does_not_verify_even_though_the_claims_are_valid(
    primary, key_set
):
    """Claims are read AFTER the signature verifies, so re-writing the payload of
    an otherwise-good token buys nothing. A verifier that checked ``exp`` first
    would be checking the attacker's assertion."""
    token = keys.mint(primary, claims())
    header, _, signature = token.split(".")
    forged = keys.b64url(
        json.dumps(claims(sub="somebody-else"), sort_keys=True).encode()
    )
    assert refusal(f"{header}.{forged}.{signature}", key_set).code == "bad_signature"


def test_a_signature_of_the_wrong_length_is_refused_rather_than_left_padded(
    primary, key_set
):
    """RFC 8017 §8.2.2 step 1. A lenient verifier that left-pads a short signature
    gives a different integer a second chance at verifying."""
    header, payload, signature = keys.mint(primary, claims()).split(".")
    import base64

    raw = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    short = keys.b64url(raw[1:])
    assert refusal(f"{header}.{payload}.{short}", key_set).code == "bad_signature"


def test_the_pkcs1_block_is_compared_whole_so_a_forged_encoding_cannot_parse_through(
    primary, key_set
):
    """The Bleichenbacher/BERserk class, closed by construction.

    Those forgeries work by making the recovered block *parse* as a valid
    ``DigestInfo`` with attacker-chosen trailing bytes. This verifier constructs
    the one correct block and compares it in full, so a block that merely parses
    is unequal. The assertion is on the mechanism: mutating any byte of the
    recovered encoding, at any position, refuses.
    """
    signed = b"header.payload"
    signature = primary.sign(signed)
    key = jwks_from_document(keys.jwks(primary)).keys[0]
    assert jwtmod._rsa_pkcs1_v15_verify(key, signed, signature, "sha256")
    for position in (0, 1, 20, len(signature) - 1):
        mutated = bytearray(signature)
        mutated[position] ^= 0x01
        assert not jwtmod._rsa_pkcs1_v15_verify(key, signed, bytes(mutated), "sha256")


# --- 4. key selection --------------------------------------------------------


def test_a_kid_naming_no_configured_key_is_refused_and_not_searched_for(
    primary, key_set
):
    """Never "try them all". The search succeeds during a botched rotation and
    hides it, which is the failure mode worth designing against."""
    token = keys.mint(primary, claims(), header_overrides={"kid": "rotated-away"})
    assert refusal(token, key_set).code == "key_not_found"


def test_a_token_with_no_kid_is_refused_when_the_key_set_is_ambiguous(primary, other):
    two = jwks_from_document(keys.jwks(primary, other))
    token = keys.mint(primary, claims(), header_overrides={"kid": None})
    assert refusal(token, two).code == "key_ambiguous"


def test_a_token_with_no_kid_verifies_against_a_single_key_set(primary, key_set):
    """Legal, common, and the only case where an absent ``kid`` is unambiguous."""
    assert verify(keys.mint(primary, claims(), header_overrides={"kid": None}), key_set)


def test_a_key_below_the_minimum_modulus_is_not_usable_at_all():
    """Skipped by the parser, so the document yields no usable key and the server
    refuses every token loudly — rather than serving with a forgeable signature."""
    weak = keys.generate("weak", bits=1024, seed=keys.SEED + 2)
    with pytest.raises(TokenRejected) as caught:
        jwks_from_document(keys.jwks(weak))
    assert caught.value.code == "no_usable_jwks_key"


def test_encryption_keys_and_foreign_key_types_are_skipped_not_fatal(primary):
    """A real JWKS carries keys this build cannot verify with. Refusing the whole
    document over one would make key rotation an outage."""
    document = {
        "keys": [
            {"kty": "EC", "kid": "ec", "crv": "P-256", "x": "AA", "y": "BB"},
            primary.jwk(use="enc"),
            primary.jwk(use="sig"),
        ]
    }
    parsed = jwks_from_document(document)
    assert [key.kid for key in parsed.keys] == [primary.kid]


@pytest.mark.parametrize(
    "document", [None, {}, {"keys": "not-a-list"}, {"keys": []}, [], "text"]
)
def test_an_unusable_key_set_raises_rather_than_verifying_nothing_quietly(document):
    with pytest.raises(TokenRejected):
        jwks_from_document(document)


# --- 5. the claims -----------------------------------------------------------


def test_a_token_from_another_issuer_is_refused(primary, key_set):
    token = keys.mint(primary, claims(iss="https://evil.example.invalid"))
    assert refusal(token, key_set).code == "issuer_mismatch"


def test_a_token_minted_for_another_resource_is_refused(primary, key_set):
    """RFC 8707 audience binding — the MUST that stops a token stolen from, or
    minted for, another service being replayed here."""
    token = keys.mint(primary, claims(aud="https://other.example.invalid/api/mcp"))
    assert refusal(token, key_set).code == "audience_mismatch"


def test_a_multi_audience_token_is_accepted_only_when_this_resource_is_in_it(
    primary, key_set
):
    assert verify(keys.mint(primary, claims(aud=["https://x.invalid", RESOURCE])), key_set)
    assert refusal(
        keys.mint(primary, claims(aud=["https://x.invalid", "https://y.invalid"])),
        key_set,
    ).code == "audience_mismatch"


@pytest.mark.parametrize(
    "audience",
    [
        RESOURCE + "/",
        RESOURCE.upper(),
        RESOURCE.replace("https://", "HTTPS://"),
        RESOURCE + "#frag",
        RESOURCE.replace("isaac.example.invalid", "isaac.example.invalid:443"),
    ],
)
def test_the_audience_comparison_normalises_nothing(primary, key_set, audience):
    """Exact string equality, RFC 3986 §6.2.1. Every normalisation here looks
    harmless and each one accepts a token minted for a DIFFERENT string; deciding
    which are safe is a question an attacker would otherwise get to answer."""
    assert refusal(keys.mint(primary, claims(aud=audience)), key_set).code == (
        "audience_mismatch"
    )


def test_an_id_token_shaped_credential_is_refused_by_the_audience_check(primary, key_set):
    """``typ: JWT`` with ``aud`` = a client id. This is why accepting the generic
    ``typ`` is safe: the audience check, not the media type, refuses it."""
    token = keys.mint(
        primary,
        claims(aud="isaac-connector-client-id"),
        header_overrides={"typ": "JWT"},
    )
    assert refusal(token, key_set).code == "audience_mismatch"


def test_an_expired_token_is_refused(primary, key_set):
    token = keys.mint(primary, claims(exp=NOW - 3600))
    assert refusal(token, key_set).code == "expired"


def test_a_token_with_no_expiry_is_refused_rather_than_treated_as_eternal(
    primary, key_set
):
    token = keys.mint(primary, claims(exp=_ABSENT))
    assert refusal(token, key_set).code == "missing_expiry"


@pytest.mark.parametrize("expiry", ["soon", 1.5, True, None, {"at": 1}])
def test_a_wrongly_typed_expiry_is_refused_rather_than_coerced(primary, key_set, expiry):
    """A float ``exp`` is refused rather than rounded: rounding an expiry is a
    decision about how long a dead token stays alive, and it should not be made
    implicitly. ``True`` is refused too — Python would otherwise read it as 1."""
    assert refusal(keys.mint(primary, claims(exp=expiry)), key_set).code == (
        "missing_expiry"
    )


def test_a_not_yet_valid_token_is_refused(primary, key_set):
    token = keys.mint(primary, claims(nbf=NOW + 3600))
    assert refusal(token, key_set).code == "not_yet_valid"


def test_clock_skew_is_allowed_in_both_directions_but_is_bounded(primary, key_set):
    just_expired = keys.mint(primary, claims(exp=NOW - 30))
    assert verify(just_expired, key_set, leeway_seconds=60)
    assert refusal(just_expired, key_set, leeway_seconds=0).code == "expired"

    just_early = keys.mint(primary, claims(nbf=NOW + 30))
    assert verify(just_early, key_set, leeway_seconds=60)
    assert refusal(just_early, key_set, leeway_seconds=0).code == "not_yet_valid"


def test_a_token_naming_no_subject_is_refused(primary, key_set):
    """A principal with no name is a log line that says "somebody". The SERVICE
    tier exists to name the calling service, so an unnamed one is refused."""
    for absent in (_ABSENT, "", "   ", 42, None):
        assert refusal(keys.mint(primary, claims(sub=absent)), key_set).code == (
            "missing_subject"
        )


@pytest.mark.parametrize(
    "body,expected",
    [
        ({"scope": "isaac:read isaac:draft.write"}, ("isaac:read", "isaac:draft.write")),
        ({"scope": ""}, ()),
        ({"scp": ["isaac:read", "openid"]}, ("isaac:read", "openid")),
        ({"scp": "isaac:read profile"}, ("isaac:read", "profile")),
        ({"scope": "isaac:read", "scp": ["isaac:read"]}, ("isaac:read",)),
        ({"scope": 7}, ()),
        ({"scp": [1, "isaac:read", None]}, ("isaac:read",)),
    ],
)
def test_scope_strings_are_read_from_either_claim_and_deduplicated(
    primary, key_set, body, expected
):
    """Both spellings are read because both are what real authorization servers
    emit. Unrecognised strings are carried, not rejected — a token legitimately
    carries scopes for other resources, and mapping them to ISAAC permissions is
    a separate decision made in ``oauth.py``."""
    payload = claims(scope=_ABSENT)
    payload.update(body)
    assert verify(keys.mint(primary, payload), key_set).scope_strings == expected


def test_a_payload_that_is_not_an_object_is_refused(primary, key_set):
    header = keys.b64url(json.dumps({"alg": "RS256", "kid": primary.kid}).encode())
    payload = keys.b64url(b"[1, 2, 3]")
    signature = keys.b64url(primary.sign(f"{header}.{payload}".encode("ascii")))
    assert refusal(f"{header}.{payload}.{signature}", key_set).code == "claims_malformed"


def test_the_verifier_reads_a_real_clock_only_when_asked_to(primary, key_set):
    """``now`` is a parameter, so expiry is tested by arithmetic rather than by
    sleeping — and so the production caller's clock is an injectable seam."""
    token = keys.mint(primary, claims(exp=int(time.time()) + 300))
    assert verify(token, key_set, now=int(time.time()))
