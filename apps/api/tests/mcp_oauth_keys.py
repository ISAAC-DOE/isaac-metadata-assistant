"""Synthetic RSA keys and a token minter, for the OAuth resource-server tests.

**EVERY KEY THIS MODULE PRODUCES IS GENERATED AT TEST TIME AND IS UNMISTAKABLY
FAKE.** Nothing is committed: there is no PEM, no JWKS and no private exponent in
this file or anywhere else in the repository, so no secret scanner has anything to
find and no key here can be confused for one that matters. They are generated from
a **fixed seed** so a failing test reproduces exactly, using a private
``random.Random`` instance rather than the module-level generator — ``pytest-randomly``
reseeds that one per test, which would otherwise make "deterministic" false.

Keys are 2048-bit because the verifier refuses anything smaller
(``jwt.MIN_RSA_MODULUS_BITS``), and a test suite that could only run against keys
the production path rejects would be testing a different program. Generation costs
roughly 1.5 s per key pair, which is why the fixture that builds them is
session-scoped.

**This module signs. The application never does**, and that asymmetry is the
point: the resource server has no private key, mints nothing, and would have no
use for either. Signing lives here, in test support, so that no production module
contains an RSA private operation at all.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
from dataclasses import dataclass

#: The one seed. Changing it changes every key in the suite, which is fine; what
#: must not happen is keys differing between two runs of the same commit.
SEED = 20260829


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _is_probable_prime(candidate: int, rounds: int, rnd: random.Random) -> bool:
    for small in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if candidate % small == 0:
            return candidate == small
    remainder, exponent = candidate - 1, 0
    while remainder % 2 == 0:
        remainder //= 2
        exponent += 1
    for _ in range(rounds):
        base = rnd.randrange(2, candidate - 1)
        witness = pow(base, remainder, candidate)
        if witness in (1, candidate - 1):
            continue
        for _ in range(exponent - 1):
            witness = witness * witness % candidate
            if witness == candidate - 1:
                break
        else:
            return False
    return True


def _prime(bits: int, rnd: random.Random) -> int:
    """A probable prime with its TOP TWO bits set, which is not a detail.

    Setting only the top bit gives each prime a value in ``[2^(k-1), 2^k)``, so
    the product lands anywhere in ``[2^(2k-2), 2^2k)`` — a "2048-bit" key whose
    modulus is 2047 bits about half the time. The verifier refuses a modulus
    below ``MIN_RSA_MODULUS_BITS``, so such a key silently produced "no usable
    JWKS key" in a test whose subject was something else entirely. With both top
    bits set the product is always exactly ``2k`` bits, which is why every real
    RSA key generator does the same thing.
    """
    while True:
        candidate = rnd.getrandbits(bits) | (3 << (bits - 2)) | 1
        if _is_probable_prime(candidate, 24, rnd):
            return candidate


@dataclass(frozen=True)
class SyntheticKey:
    """A synthetic RSA key pair and the JWKS entry describing its public half."""

    kid: str
    modulus: int
    public_exponent: int
    private_exponent: int

    @property
    def size_bytes(self) -> int:
        return (self.modulus.bit_length() + 7) // 8

    def jwk(self, *, algorithm: str | None = None, use: str | None = None) -> dict:
        entry = {
            "kty": "RSA",
            "kid": self.kid,
            "n": b64url(self.modulus.to_bytes(self.size_bytes, "big")),
            "e": b64url(
                self.public_exponent.to_bytes(
                    (self.public_exponent.bit_length() + 7) // 8, "big"
                )
            ),
        }
        if algorithm is not None:
            entry["alg"] = algorithm
        if use is not None:
            entry["use"] = use
        return entry

    def sign(self, signing_input: bytes, hash_name: str = "sha256") -> bytes:
        """RSASSA-PKCS1-v1_5 over ``signing_input``. Test support only."""
        prefix = {
            "sha256": bytes.fromhex("3031300d060960864801650304020105000420"),
            "sha384": bytes.fromhex("3041300d060960864801650304020205000430"),
            "sha512": bytes.fromhex("3051300d060960864801650304020305000440"),
        }[hash_name]
        digest_info = prefix + hashlib.new(hash_name, signing_input).digest()
        padding = self.size_bytes - len(digest_info) - 3
        encoded = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info
        return pow(
            int.from_bytes(encoded, "big"), self.private_exponent, self.modulus
        ).to_bytes(self.size_bytes, "big")


def generate(kid: str, *, bits: int = 2048, seed: int = SEED) -> SyntheticKey:
    rnd = random.Random(seed)
    half = bits // 2
    p = _prime(half, rnd)
    q = _prime(half, rnd)
    while q == p:  # pragma: no cover - astronomically unlikely
        q = _prime(half, rnd)
    modulus = p * q
    # The property `_prime`'s top-two-bits trick exists to guarantee, asserted so
    # a change there cannot quietly reintroduce an under-sized key.
    assert modulus.bit_length() == bits, modulus.bit_length()
    public_exponent = 65537
    private_exponent = pow(public_exponent, -1, (p - 1) * (q - 1))
    return SyntheticKey(
        kid=kid,
        modulus=modulus,
        public_exponent=public_exponent,
        private_exponent=private_exponent,
    )


def jwks(*keys: SyntheticKey, **jwk_kwargs) -> dict:
    return {"keys": [key.jwk(**jwk_kwargs) for key in keys]}


def mint(
    key: SyntheticKey,
    claims: dict,
    *,
    algorithm: str = "RS256",
    header_overrides: dict | None = None,
    signing_key: SyntheticKey | None = None,
    tamper_signature: bool = False,
) -> str:
    """A compact JWS. ``signing_key`` defaults to ``key``, so a *different* one
    produces a correctly-shaped token with a signature that will not verify."""
    hash_name = {"RS256": "sha256", "RS384": "sha384", "RS512": "sha512"}.get(
        algorithm, "sha256"
    )
    header = {"alg": algorithm, "typ": "at+jwt", "kid": key.kid}
    header.update(header_overrides or {})
    if header.get("kid") is None:
        header.pop("kid", None)
    segments = (
        b64url(json.dumps(header, sort_keys=True).encode("utf-8")),
        b64url(json.dumps(claims, sort_keys=True).encode("utf-8")),
    )
    signing_input = ".".join(segments).encode("ascii")
    signature = (signing_key or key).sign(signing_input, hash_name)
    if tamper_signature:
        signature = bytes([signature[0] ^ 0x01]) + signature[1:]
    return f"{segments[0]}.{segments[1]}.{b64url(signature)}"


def mint_unsecured(claims: dict) -> str:
    """``alg: none`` with an empty signature — RFC 7519's unsecured JWS."""
    header = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload = b64url(json.dumps(claims, sort_keys=True).encode("utf-8"))
    return f"{header}.{payload}."


def mint_hmac_confusion(key: SyntheticKey, claims: dict) -> str:
    """The classic algorithm-confusion token: ``alg: HS256``, MACed with the
    PUBLIC key's own modulus bytes as the shared secret.

    A server that picks its verifier from the token's ``alg`` and reaches for the
    configured key as an HMAC secret accepts this. ISAAC implements no HMAC
    algorithm at all, so there is nothing for it to reach.
    """
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload = b64url(json.dumps(claims, sort_keys=True).encode("utf-8"))
    signing_input = f"{header}.{payload}".encode("ascii")
    secret = key.modulus.to_bytes(key.size_bytes, "big")
    mac = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{b64url(mac)}"
