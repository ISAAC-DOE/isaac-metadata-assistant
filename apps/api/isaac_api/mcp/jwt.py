"""JWS/JWT access-token verification, in the standard library and nothing else.

WHY THIS FILE EXISTS RATHER THAN A DEPENDENCY
=============================================
``test_mcp_boundaries.py::test_the_mcp_package_adds_no_third_party_dependency``
permits exactly one third-party import in this package (``httpx``), and the
virtualenv this repository builds contains **no** ``cryptography``, ``PyJWT``,
``jose`` or ``authlib`` — measured, not assumed
(``.venv/bin/pip list``). Adding one would be a new runtime dependency in a
deployment whose image is built from ``pyproject.toml``, for a feature that is
**disabled by default and reachable in no shipped deployment**. So the choice was
between a dependency nobody has approved and a bounded implementation, and this
is the bounded implementation.

"DO NOT ROLL YOUR OWN CRYPTO" — WHY THIS IS THE EXCEPTION, STATED PRECISELY
==========================================================================
The rule is about *secret-bearing* operations: key generation, signing, key
agreement, decryption. Every one of those leaks through timing, through fault
injection, or through a bad random source. **This module performs none of them.**
It performs RSASSA-PKCS1-v1_5 *verification*, which is:

* **public-data-only** — the modulus, the exponent, the signature and the message
  are all public, so there is no secret whose timing could leak;
* **deterministic** — one modular exponentiation with a public exponent, then a
  byte comparison;
* **historically dangerous in exactly one way**, and that way is closed here by
  construction. Every Bleichenbacher-class signature forgery (BERserk and
  friends) comes from *parsing* the decrypted block — searching for ``00 01 FF …
  00``, then parsing an ASN.1 ``DigestInfo`` leniently, and ignoring trailing
  bytes. This module never parses. It **constructs** the expected encoded message
  from the digest and compares the whole block with
  :func:`hmac.compare_digest`. A forged block that "parses" cannot be equal to
  the one correct block, so the entire attack class is unreachable rather than
  defended against.

WHAT IS DELIBERATELY NOT IMPLEMENTED
====================================
* **HMAC algorithms (``HS256`` &c.) are not implemented at all.** This is the
  single most important line in the file. The classic algorithm-confusion attack
  hands a server an ``HS256`` token MACed with the *public* key bytes; a server
  that supports both families and selects the verifier from the token's own
  ``alg`` header verifies it happily. Here there is **no code path that treats
  key material as a MAC key**, so the attack has nothing to reach. Refusing
  ``HS256`` in an ``if`` would be a check somebody could reorder; not having the
  function is not.
* **``ES*``/``EdDSA``/``PS*``.** Not "unsupported" as an oversight —
  :data:`SUPPORTED_ALGORITHMS` is an allowlist and everything outside it is
  refused with a named reason. Adding ECDSA means implementing point arithmetic,
  which is a different risk conversation and a different slice.
* **``alg: none``.** Refused by the allowlist, and *also* named explicitly in
  :func:`_reject_algorithm` so the refusal reads as a decision rather than as a
  lookup miss.
* **JWE (five segments).** Refused on segment count.
* **Key discovery over the network.** This module never opens a socket. Keys
  arrive as a parsed :class:`JsonWebKeySet`; where they came from is
  ``oauth.py``'s problem and is a seam that is unset by default.

THE ``typ`` DECISION: RFC 9068 IS NOT ENFORCED, AND THAT IS THE DECISION
========================================================================
RFC 9068 §4: *"The resource server MUST verify that the 'typ' header value is
'at+jwt' or 'application/at+jwt' and reject tokens carrying any other value."*
(§2.1 puts only a SHOULD on the issuer, which is why the burden lands on the
resource server.) **This module does not enforce it**, and until 2026-08-30
``oauth.py`` advertised *"RFC 9068-shaped JWT access tokens"*, which read as
though it did. The claim is withdrawn there; the decision is recorded here,
because this is where a future author will come looking for it.

**Why the RFC is not the governing document.** MCP's authorization chapter says
*"MCP servers, acting in their role as an OAuth 2.1 resource server, **MUST**
validate access tokens as described in OAuth 2.1 Section 5.2"*, and RFC 9068 is
absent from its Standards Compliance list entirely. So there is no MCP MUST to
violate here — only an RFC this build chose not to adopt.

**Why not adopt it anyway.** Because :data:`SUPPORTED_TYP_VALUES` would then be
``{at+jwt, application/at+jwt}``, and a great many deployed authorization servers
— Authentik, the one ISAAC would actually be configured against, among them —
mint the generic ``JWT``. Every one of them would be refused, with a refusal
naming a header field rather than anything an operator can act on. The strictly
stronger rule is also the rule that makes the feature unusable against the
issuer it exists for.

**The residual risk, named rather than glossed.** Accepting ``JWT`` admits the
*shape* of an OIDC **ID token**, and the only thing standing between an ID token
and acceptance is the audience check: an ID token's ``aud`` is the ``client_id``,
never the resource URI, so the unconditional ``resource in audiences`` comparison
in :func:`verify_access_token` refuses it. **That defence has one failure mode
and it is a configuration the operator controls: a ``client_id`` that is a URL
equal to the resource identifier.** MCP's own client-registration chapter makes
URL-shaped client IDs a live possibility (Client ID Metadata Documents use an
HTTPS URL as the ``client_id``), so this is not hypothetical. The mitigation is
an operator instruction — *do not register the MCP client with a ``client_id``
equal to ``ISAAC_MCP_OAUTH_RESOURCE``* — recorded in
``docs/mcp-oauth-operator-requirements-2026-08-27.md``, because no check inside
this process can distinguish the two strings when they are the same string.

What IS enforced: a ``typ`` that is present and is **outside**
:data:`SUPPORTED_TYP_VALUES` is refused (``dpop+jwt``, ``id_token+jwt``, anything
else), and an absent ``typ`` is permitted, which RFC 7515 §4.1.9 allows.

NOTHING IN THIS MODULE EVER PUTS TOKEN MATERIAL IN AN EXCEPTION, A LOG, OR A
RETURN VALUE
============================================================================
:class:`TokenRejected` carries a fixed ``code`` and a fixed English ``message``
chosen from this file's own constants. No branch interpolates a segment, a claim
value, a signature, a header, or the token itself — including the "helpful"
ones (*"expected audience X, got Y"*), because ``Y`` is attacker-supplied and the
refusal body is returned to the caller. ``test_mcp_oauth_never_leaks_a_token.py``
asserts this over every rejection path rather than trusting the paragraph.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "MAX_COMPACT_TOKEN_BYTES",
    "MAX_SEGMENT_BYTES",
    "SUPPORTED_ALGORITHMS",
    "SUPPORTED_TYP_VALUES",
    "JsonWebKey",
    "JsonWebKeySet",
    "TokenRejected",
    "VerifiedToken",
    "jwks_from_document",
    "verify_access_token",
]

#: The only signature algorithms this build verifies. An allowlist, and RSA-only
#: on purpose — see the module docstring on algorithm confusion.
SUPPORTED_ALGORITHMS: Mapping[str, str] = {
    "RS256": "sha256",
    "RS384": "sha384",
    "RS512": "sha512",
}

#: ``typ`` header values accepted. RFC 9068 mints ``at+jwt``; a great many
#: deployed authorization servers (Authentik among them) mint the generic
#: ``JWT``, and absent is permitted by RFC 7515 §4.1.9.
#:
#: **THIS SET IS THE ``typ`` DECISION, AND THE DECISION IS "RFC 9068 §4 IS NOT
#: ENFORCED".** The module docstring's ``THE typ DECISION`` section carries the
#: argument, the rejected alternative, and the one residual risk it leaves — a
#: ``client_id`` that is a URL equal to the resource identifier, which is an
#: operator instruction rather than a check this process can make. Read it before
#: narrowing this set; narrowing it is defensible and would refuse Authentik.
SUPPORTED_TYP_VALUES: frozenset[str] = frozenset(
    {"jwt", "at+jwt", "application/at+jwt"}
)

#: RSA moduli below this are refused outright. 2048 is the floor every current
#: guideline agrees on, and a key too small to be safe must not be a key that
#: merely produces a warning nobody reads.
MIN_RSA_MODULUS_BITS = 2048

#: An ``Authorization`` value longer than this is refused before anything is
#: decoded. Real access tokens are a few kilobytes at the outside; the cap exists
#: so a hostile caller cannot make this process do base64 and JSON work
#: proportional to whatever it felt like sending.
MAX_COMPACT_TOKEN_BYTES = 8192

#: Per-segment decoded cap, applied before ``json.loads``. Deep or enormous JSON
#: is a parser problem, and the cheapest place to not have it is here.
MAX_SEGMENT_BYTES = 4096

#: base64url, no padding, no ``+``/``/``. A segment outside this alphabet is
#: malformed rather than something to coax through a lenient decoder.
_BASE64URL = re.compile(r"\A[A-Za-z0-9_-]+\Z")

#: DER ``DigestInfo`` prefixes for the three hashes, per RFC 8017 §9.2 Note 1.
#: Constants rather than a builder: these are the only three this module needs,
#: and an ASN.1 encoder written to produce three fixed byte strings is more code
#: with more ways to be subtly wrong.
_DIGEST_INFO_PREFIX: Mapping[str, bytes] = {
    "sha256": bytes.fromhex("3031300d060960864801650304020105000420"),
    "sha384": bytes.fromhex("3041300d060960864801650304020205000430"),
    "sha512": bytes.fromhex("3051300d060960864801650304020305000440"),
}


class TokenRejected(Exception):
    """This token is not acceptable, and here is a reason safe to hand back.

    ``code`` is a stable machine-readable token for tests and for a client to
    branch on. ``message`` is fixed English. **Neither is ever built by
    interpolating anything from the token**, which is the property that makes it
    safe to put this in a ``401`` body and in a log line.

    ``oauth_error`` is the RFC 6750 ``error`` code the ``WWW-Authenticate``
    challenge carries for this rejection — ``invalid_token`` for everything in
    this module, because every rejection here is about the credential itself.
    Scope insufficiency is a different decision made a layer up and carries
    ``insufficient_scope``.
    """

    oauth_error = "invalid_token"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class JsonWebKey:
    """One RSA public key from a JWKS. Parsed once, never re-parsed per request.

    ``kid`` may be empty: a JWKS with a single key and no ``kid`` is legal, and
    :func:`_select_key` handles that case *only* when the set has exactly one
    key. Guessing which of several keys signed a token by trying them all is a
    downgrade — it turns a key-rollover mistake into a silent success — so it is
    not done.
    """

    kid: str
    modulus: int
    exponent: int
    #: The algorithm this key declares, or ``""``. When declared it is BINDING:
    #: a token whose header names a different algorithm is refused, which is a
    #: second, independent barrier against algorithm substitution.
    algorithm: str

    @property
    def modulus_bits(self) -> int:
        return self.modulus.bit_length()


@dataclass(frozen=True)
class JsonWebKeySet:
    """The verification keys, and nothing about where they came from."""

    keys: tuple[JsonWebKey, ...]

    def __bool__(self) -> bool:
        return bool(self.keys)


@dataclass(frozen=True)
class VerifiedToken:
    """A token this module is willing to vouch for, and what it said.

    Deliberately not the raw token: nothing downstream of verification has any
    use for the credential itself, and a field holding it is a field something
    will eventually log.
    """

    subject: str
    issuer: str
    audiences: tuple[str, ...]
    scope_strings: tuple[str, ...]
    key_id: str
    algorithm: str
    expires_at: int
    #: Every claim, for a caller that needs one this dataclass does not name.
    #: Read-only by convention; ``verify_access_token`` builds it fresh.
    claims: Mapping[str, Any]


# --------------------------------------------------------------------------
# JWKS parsing
# --------------------------------------------------------------------------


def _b64url_to_int(raw: str) -> int:
    """A base64url ``uint`` (RFC 7518 §2) as an integer, or raise."""
    return int.from_bytes(_b64url_decode(raw, "malformed_jwks"), "big")


def _b64url_decode(segment: str, code: str) -> bytes:
    """Strict base64url with no padding. Raises :class:`TokenRejected`.

    ``binascii``'s ``Error`` and a wrong alphabet are both malformed input, and
    both are reported with the SAME fixed message: an attacker learning which of
    the two tripped is an attacker learning about the parser.
    """
    if not _BASE64URL.match(segment or ""):
        raise TokenRejected(code, _REJECTIONS[code])
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError) as exc:  # pragma: no cover - defensive
        raise TokenRejected(code, _REJECTIONS[code]) from exc


def jwks_from_document(document: Any) -> JsonWebKeySet:
    """Parse a JWKS document into the RSA signing keys this build can use.

    **Unusable entries are skipped, not fatal.** A real JWKS routinely carries
    encryption keys and key types this build does not verify, and refusing the
    whole document because one entry is an ``EC`` key would make key rotation an
    outage. What is *not* skipped is a document that yields no usable key at all:
    that raises, because a resource server with no verification key must refuse
    every token loudly rather than refuse every token as "invalid signature".

    A key below :data:`MIN_RSA_MODULUS_BITS` is skipped rather than accepted, so
    a deployment that publishes a weak key gets "no usable key" — a
    configuration failure — instead of a working server with a forgeable
    signature.
    """
    if not isinstance(document, Mapping):
        raise TokenRejected("malformed_jwks", _REJECTIONS["malformed_jwks"])
    entries = document.get("keys")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise TokenRejected("malformed_jwks", _REJECTIONS["malformed_jwks"])

    keys: list[JsonWebKey] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("kty") != "RSA":
            continue
        use = entry.get("use")
        if use is not None and use != "sig":
            continue
        algorithm = entry.get("alg")
        if algorithm is not None and (
            not isinstance(algorithm, str) or algorithm not in SUPPORTED_ALGORITHMS
        ):
            continue
        modulus_raw, exponent_raw = entry.get("n"), entry.get("e")
        if not isinstance(modulus_raw, str) or not isinstance(exponent_raw, str):
            continue
        try:
            modulus = _b64url_to_int(modulus_raw)
            exponent = _b64url_to_int(exponent_raw)
        except TokenRejected:
            continue
        if modulus.bit_length() < MIN_RSA_MODULUS_BITS:
            continue
        if exponent < 3 or exponent % 2 == 0 or exponent >= modulus:
            continue
        kid = entry.get("kid")
        keys.append(
            JsonWebKey(
                kid=kid if isinstance(kid, str) else "",
                modulus=modulus,
                exponent=exponent,
                algorithm=algorithm or "",
            )
        )

    if not keys:
        raise TokenRejected("no_usable_jwks_key", _REJECTIONS["no_usable_jwks_key"])
    return JsonWebKeySet(keys=tuple(keys))


# --------------------------------------------------------------------------
# Signature verification
# --------------------------------------------------------------------------


def _emsa_pkcs1_v15(digest: bytes, hash_name: str, modulus_bytes: int) -> bytes:
    """The one correct encoded message for this digest, per RFC 8017 §9.2.

    Built, never parsed. This is the whole defence described in the module
    docstring: there is exactly one byte string a valid signature can produce,
    and the caller compares against it in full.
    """
    suffix = _DIGEST_INFO_PREFIX[hash_name] + digest
    # 11 = 0x00 || 0x01 || at least eight 0xFF || 0x00
    padding_length = modulus_bytes - len(suffix) - 3
    if padding_length < 8:
        raise TokenRejected("key_too_small", _REJECTIONS["key_too_small"])
    return b"\x00\x01" + b"\xff" * padding_length + b"\x00" + suffix


def _rsa_pkcs1_v15_verify(
    key: JsonWebKey, signed: bytes, signature: bytes, hash_name: str
) -> bool:
    """Whether ``signature`` is ``key``'s PKCS#1 v1.5 signature over ``signed``."""
    modulus_bytes = (key.modulus_bits + 7) // 8
    # RFC 8017 §8.2.2 step 1: a signature that is not exactly k octets is
    # invalid. Left-padding a short one — which a lenient implementation does —
    # is how a signature with a different integer value gets a second chance.
    if len(signature) != modulus_bytes:
        return False
    signature_int = int.from_bytes(signature, "big")
    if signature_int >= key.modulus:
        return False
    recovered = pow(signature_int, key.exponent, key.modulus).to_bytes(
        modulus_bytes, "big"
    )
    expected = _emsa_pkcs1_v15(
        hashlib.new(hash_name, signed).digest(), hash_name, modulus_bytes
    )
    # Not required to be constant time — both operands are public — but
    # `compare_digest` also refuses to short-circuit on length, and using the
    # obviously-correct primitive costs nothing.
    return hmac.compare_digest(recovered, expected)


# --------------------------------------------------------------------------
# The verifier
# --------------------------------------------------------------------------

#: Rejection code -> the fixed message it carries. A table rather than inline
#: strings so ``test_mcp_oauth_never_leaks_a_token.py`` can assert that every
#: message a rejection can carry is a constant from this file.
_REJECTIONS: Mapping[str, str] = {
    "token_absent": "This resource requires an OAuth 2.1 bearer access token.",
    "token_too_large": "The presented credential exceeds this server's size limit.",
    "malformed_token": "The presented credential is not a well-formed JWS.",
    "encrypted_token_unsupported": (
        "This server verifies signed JWTs only and does not decrypt JWE."
    ),
    "malformed_jwks": "The configured key set is not a well-formed JWKS document.",
    "no_usable_jwks_key": (
        "The configured key set contains no RSA signing key this build can use."
    ),
    "algorithm_none": (
        "An unsecured token (alg 'none') is never accepted by this server."
    ),
    "algorithm_unsupported": (
        "The token's signature algorithm is not one this server verifies."
    ),
    "algorithm_mismatch": (
        "The token's algorithm does not match the algorithm its signing key "
        "declares."
    ),
    "unsupported_typ": "The token declares a media type this server does not accept.",
    "critical_header_unsupported": (
        "The token requires an extension this server does not implement."
    ),
    "key_not_found": "No configured signing key matches this token.",
    "key_ambiguous": (
        "The token names no key and the configured key set holds more than one."
    ),
    "key_too_small": "The signing key is smaller than this server accepts.",
    "bad_signature": "The token's signature did not verify.",
    "claims_malformed": "The token's claim set is not a JSON object.",
    "issuer_mismatch": "The token was not issued by this resource's issuer.",
    "audience_mismatch": (
        "The token was not issued for this resource. A resource server accepts "
        "only tokens whose audience is itself."
    ),
    "expired": "The token has expired.",
    "not_yet_valid": "The token is not valid yet.",
    "missing_expiry": "The token carries no expiry and is refused.",
    "missing_subject": "The token names no subject.",
}


def _reject(code: str) -> TokenRejected:
    return TokenRejected(code, _REJECTIONS[code])


def _reject_algorithm(algorithm: Any) -> TokenRejected:
    """The algorithm refusal, with ``none`` named rather than merely missing.

    ``alg: none`` failing an allowlist lookup is correct and reads, in a log, as
    a typo. Naming it makes the refusal legible to whoever is reading the log
    because somebody is attacking them.
    """
    if isinstance(algorithm, str) and algorithm.strip().lower() == "none":
        return _reject("algorithm_none")
    return _reject("algorithm_unsupported")


def _decode_segment(segment: str, code: str) -> Any:
    raw = _b64url_decode(segment, code)
    if len(raw) > MAX_SEGMENT_BYTES:
        raise _reject("token_too_large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _reject(code) from exc


def _select_key(keys: JsonWebKeySet, kid: Any) -> JsonWebKey:
    """The one key that may verify this token, or raise.

    Never "try them all". A ``kid`` that names no configured key is a refusal,
    not an invitation to search: the search succeeds during a botched rotation
    and hides it.
    """
    if isinstance(kid, str) and kid:
        matches = [key for key in keys.keys if key.kid == kid]
        if len(matches) != 1:
            raise _reject("key_not_found")
        return matches[0]
    if len(keys.keys) != 1:
        raise _reject("key_ambiguous")
    return keys.keys[0]


def _audiences(claim: Any) -> tuple[str, ...]:
    """The ``aud`` claim as a tuple. A non-string member makes the whole claim
    unusable rather than being filtered out, because filtering would let
    ``["<wrong>", 1]`` become ``["<wrong>"]`` and read as a clean list."""
    if isinstance(claim, str):
        return (claim,)
    if isinstance(claim, Sequence) and not isinstance(claim, (str, bytes)):
        if all(isinstance(item, str) for item in claim):
            return tuple(claim)
    return ()


def _scope_strings(claims: Mapping[str, Any]) -> tuple[str, ...]:
    """Scope strings from ``scope`` (RFC 6749, space-delimited) or ``scp``.

    ``scp`` is accepted because a large family of authorization servers emits it
    instead, as a JSON array. Both are read; neither is required. **An
    unrecognised scope string is not an error here** — a token may legitimately
    carry ``openid``/``profile`` — it simply maps to no ISAAC permission, and a
    token that maps to none authenticates successfully and authorizes nothing.
    """
    found: list[str] = []
    raw = claims.get("scope")
    if isinstance(raw, str):
        found.extend(part for part in raw.split(" ") if part)
    scp = claims.get("scp")
    if isinstance(scp, str):
        found.extend(part for part in scp.split(" ") if part)
    elif isinstance(scp, Sequence) and not isinstance(scp, (str, bytes)):
        found.extend(item for item in scp if isinstance(item, str) and item)
    # Order-stable de-duplication: the set is small and a stable order makes a
    # refusal body byte-reproducible across runs.
    seen: list[str] = []
    for item in found:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def verify_access_token(
    token: str,
    *,
    keys: JsonWebKeySet,
    issuer: str,
    resource: str,
    now: int,
    leeway_seconds: int = 60,
) -> VerifiedToken:
    """Verify one compact JWS access token, or raise :class:`TokenRejected`.

    THE ORDER IS DELIBERATE: **structure, then algorithm, then signature, then
    claims.** Nothing about the claim set is believed before the signature over
    it has verified, which is the difference between "the token says it expires
    tomorrow" and "the issuer says it expires tomorrow". A verifier that checks
    ``exp`` first is checking an attacker's assertion.

    ``resource`` is the canonical resource URI this server answers as, compared
    to the ``aud`` claim by **exact string equality** — RFC 3986 §6.2.1 simple
    string comparison, no scheme folding, no default-port elision, no
    trailing-slash normalisation. Normalising here would mean accepting a token
    minted for a *different* string, and "which normalisations are safe" is
    exactly the question an attacker gets to answer if the comparison is fuzzy.
    """
    if not token or not token.strip():
        raise _reject("token_absent")
    token = token.strip()
    if len(token.encode("utf-8", "surrogatepass")) > MAX_COMPACT_TOKEN_BYTES:
        raise _reject("token_too_large")

    segments = token.split(".")
    if len(segments) == 5:
        raise _reject("encrypted_token_unsupported")
    if len(segments) != 3:
        raise _reject("malformed_token")
    header_segment, payload_segment, signature_segment = segments

    header = _decode_segment(header_segment, "malformed_token")
    if not isinstance(header, Mapping):
        raise _reject("malformed_token")

    if "crit" in header:
        # RFC 7515 §4.1.11: a recipient that does not understand every listed
        # extension MUST reject. This build understands none, so any `crit` at
        # all is a refusal — including `crit: []`, which is itself invalid.
        raise _reject("critical_header_unsupported")

    typ = header.get("typ")
    if typ is not None:
        if not isinstance(typ, str) or typ.strip().lower() not in SUPPORTED_TYP_VALUES:
            raise _reject("unsupported_typ")

    algorithm = header.get("alg")
    if not isinstance(algorithm, str) or algorithm not in SUPPORTED_ALGORITHMS:
        raise _reject_algorithm(algorithm)
    hash_name = SUPPORTED_ALGORITHMS[algorithm]

    key = _select_key(keys, header.get("kid"))
    # The key's own declared algorithm is binding when it declares one. Two
    # independent barriers rather than one: the allowlist bounds the family, this
    # bounds the substitution *within* the family.
    if key.algorithm and key.algorithm != algorithm:
        raise _reject("algorithm_mismatch")
    if key.modulus_bits < MIN_RSA_MODULUS_BITS:  # pragma: no cover - parser filters
        raise _reject("key_too_small")

    signature = _b64url_decode(signature_segment, "malformed_token")
    signed = f"{header_segment}.{payload_segment}".encode("ascii")
    if not _rsa_pkcs1_v15_verify(key, signed, signature, hash_name):
        raise _reject("bad_signature")

    # --- everything below here is now the ISSUER's assertion, not the caller's

    claims = _decode_segment(payload_segment, "claims_malformed")
    if not isinstance(claims, Mapping):
        raise _reject("claims_malformed")

    if claims.get("iss") != issuer:
        raise _reject("issuer_mismatch")

    audiences = _audiences(claims.get("aud"))
    if resource not in audiences:
        raise _reject("audience_mismatch")

    expires_at = claims.get("exp")
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        # A float `exp` is refused rather than coerced. NumericDate is defined as
        # a number, but accepting a float means deciding how to round it, and
        # rounding an expiry is a decision about how long a dead token lives.
        raise _reject("missing_expiry")
    if now - leeway_seconds >= expires_at:
        raise _reject("expired")

    not_before = claims.get("nbf")
    if not_before is not None:
        if not isinstance(not_before, int) or isinstance(not_before, bool):
            raise _reject("not_yet_valid")
        if now + leeway_seconds < not_before:
            raise _reject("not_yet_valid")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        # Refused rather than defaulted. A principal with no name is a row, a log
        # line and an audit entry that says "somebody"; the whole point of the
        # SERVICE tier is that it names the calling service.
        raise _reject("missing_subject")

    return VerifiedToken(
        subject=subject.strip(),
        issuer=issuer,
        audiences=audiences,
        scope_strings=_scope_strings(claims),
        key_id=key.kid,
        algorithm=algorithm,
        expires_at=expires_at,
        claims=dict(claims),
    )
