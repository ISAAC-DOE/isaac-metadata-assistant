"""Temporary, read-only identity-observation probe — PURE LOGIC (no FastAPI).

WHAT THIS IS
------------
A measurement instrument, not a feature. `docs/identity-trust-contract.md` §1
establishes that **this application reads zero identity headers** and that the
Authentik forward-auth edge in front of `/krish` is configured in
`ISAAC-DOE/isaac-k8`, a repository this working tree cannot see. Questions Q1-Q4
and Q15 of that document can only be answered by *observing* one request as it
actually arrives at the pod. This module is the observation apparatus for Q15.

It answers exactly two questions, and nothing else:

1. **Which** of a fixed, compile-time list of candidate identity headers arrive
   at FastAPI at all (presence, and a coarse structural shape).
2. Whether a **client-supplied canary** planted in those headers **survived the
   edge** — i.e. whether the ingress strips or overwrites a forged copy (Q3).

WHAT IT MUST NEVER DO
---------------------
No header **value**, and nothing derived from one, may leave this module: not
truncated, not hashed, not fingerprinted, not length-reported, not
character-counted. No username, email, uid, subject, display name, group name,
or entitlement name is ever **emitted**.

**One deliberate, bounded exception, stated here rather than buried:**
`client_canary_survived` is a containment oracle. It answers "is the string in
your request body present in this header, whole or as a segment?", so an
authenticated caller can *confirm by guessing* — one bit per request — that their
own `groups` header contains `admin`. See :func:`canary_survived` for why that
trade is taken and how it is bounded (`allow_credentials=False`, own-headers
only). Nothing else in this module discloses anything derived from a value.

No `Authorization`, no `Cookie`, no session id, no token.
No raw header mapping. **No non-allowlisted header name** — the candidate list
is a *projection*, never a filter, because a filter can leak a name that was
present and a projection structurally cannot. The module never iterates over the
request's headers; the caller reads exactly the seven names published here.

Every string this module can put into a response is a compile-time constant.
`assert_only_constant_strings` enforces that mechanically over the built payload,
which is a strictly stronger guarantee than a substring leak-scan: a scan proves
that known-bad text is absent, whereas the constant-universe check proves that
*nothing but known-good text is present*.

WHY THE ROUTE IS POST AND NOT GET
---------------------------------
The canary must travel in the request **body**. `Dockerfile:50` starts uvicorn
with default access logging, which writes the request line — **including the
query string** — to the pod's stdout. A canary passed as a query parameter would
therefore be persisted into container logs, and container logs are a different
retention and access domain than an HTTP response. A request body is not written
to the access log. A header would be worse still: the canary must be sent *in*
the candidate headers as the forgery under test, so the body is the only channel
that can carry the expected value without a second copy in a logged position.

WHY `consistent_with_previous_request` IS DELIBERATELY OMITTED
--------------------------------------------------------------
An obvious third question is "does the same caller get the same identity across
requests?". It is **not implemented, on purpose.** Answering it requires
retaining a per-value fingerprint (a hash, a salted digest, anything) between
requests and comparing a later request against it. That artefact is a
**cross-request correlation surface**: it is a stored, stable derivative of a
person's identity claim, it makes the pod capable of linking two requests to one
human, and it converts a stateless presence check into a miniature session
store — with no retention policy, no owner, and no decision from Dean behind it.
Storing a *hash* rather than the value does not help; a hash of a low-entropy
claim (a SLAC username) is trivially reversible by enumeration. Since the whole
point of this probe is to answer a configuration question with the minimum
possible exposure, the correlating variant is out of scope and should stay out.

**Do not offer "just send two requests and compare the responses by eye" as the
substitute — it does not work, and an earlier revision of this docstring claimed
it did.** The response carries no identity, only presence, shape and a canary
boolean, so two responses from one caller are identical *by construction* and
would stay identical if the caller's identity changed completely between them.
Comparing them by eye answers whether the **header contract** is stable, which is
a different question. **Identity consistency is not answerable by this probe at
all, deliberately** — it is a question for the provider's configuration, not for
the pod.

Mirrors `db_recon.py`: pure, importable, no FastAPI dependency, fully unit
testable. The HTTP wiring lives in `routes.py` section 23.

Removal plan: `docs/identity-probe.md`.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any, Sequence

#: Version of the SHAPE of the probe response. Bump on a breaking change.
PROBE_CONTRACT_VERSION = 1

# --- statuses -----------------------------------------------------------------

STATUS_OK = "ok"
STATUS_DISABLED = "disabled"
STATUS_ERROR = "error"

#: Every status this probe can report. Frozen; part of the constant universe.
STATUSES: tuple[str, ...] = (STATUS_OK, STATUS_DISABLED, STATUS_ERROR)

# --- shapes -------------------------------------------------------------------

SHAPE_ABSENT = "absent"
SHAPE_MALFORMED = "malformed"
SHAPE_DUPLICATE = "duplicate"
SHAPE_LIST = "list"
SHAPE_SCALAR = "scalar"

#: Precedence for a header that IS present, highest first. Explicit rather than
#: implied by the `if` order in :func:`classify_shape`, so the ordering is a
#: testable published fact:
#:
#:   malformed > duplicate > list > scalar
#:
#: The reasoning: malformed wins because an undecodable or control-bearing value
#: means the reading itself is untrustworthy, and that matters more than how many
#: copies arrived. Duplicate outranks list because two headers is a *transport*
#: fact (something appended a second copy) while a separator is a *provider
#: formatting* fact, and the transport fact is the one the probe exists to
#: detect. `scalar` is the residual.
#:
#: **`duplicate` is not by itself proof that the ingress appended anything.** A
#: client can send two copies on its own, and under the intended operating
#: procedure it does exactly that. The shape says only that more than one copy
#: arrived; attributing the second copy to the edge requires knowing what the
#: caller sent, which is the operator's knowledge and not this response's.
SHAPE_PRECEDENCE: tuple[str, ...] = (
    SHAPE_MALFORMED,
    SHAPE_DUPLICATE,
    SHAPE_LIST,
    SHAPE_SCALAR,
)

#: Every shape value that can appear in a response.
SHAPES: tuple[str, ...] = (SHAPE_ABSENT, *SHAPE_PRECEDENCE)

#: Separators Authentik has been observed to use when joining a multi-valued
#: claim (groups, entitlements) into one header value. Both are checked because
#: the provider's choice is configuration this repository cannot see.
LIST_SEPARATORS: tuple[str, ...] = (",", "|")

#: Longest canary the probe will consider. A bound, not a security control: the
#: canary is the caller's own string and is never stored, echoed, or logged.
MAX_CANARY_LENGTH = 128


# --- the candidate allowlist ---------------------------------------------------


@dataclass(frozen=True)
class IdentityCandidate:
    """One allowlisted candidate identity header.

    `consumed_by_isaac` is **data, not a guess**: it records whether any line of
    this application reads the header for any purpose. Today every entry is
    ``False``, which is the verifiable state recorded in
    `docs/identity-trust-contract.md` §1.2 — the backend reads exactly four
    request headers (`authorization`, `If-None-Match`, `If-Match`, `X-Filename`)
    and none of them is an identity header. The probe reading a header in order
    to report its *presence* is not consumption: nothing downstream branches on
    it, no record is stamped with it, and no authorization decision uses it.

    `pii_bearing` flags a candidate whose value would be personal data about a
    named human if it were ever read. It exists so the probe's own documentation
    cannot quietly forget which of these are `docs/identity-trust-contract.md`
    §6's concern. It does not change any behaviour — no value is emitted for any
    candidate, PII-bearing or not.
    """

    claim: str
    header: str
    consumed_by_isaac: bool
    pii_bearing: bool


#: The FROZEN candidate allowlist. Seven names, chosen from evidence, never
#: discovered at runtime:
#:
#:  * `X-authentik-username` and `X-Isaac-Edge` are the two the ISAAC portal
#:    (`ISAAC-DOE/isaac-ai-ready-record`) reads, so they are the names the sibling
#:    application already assumes.
#:  * `-uid`, `-email`, `-name`, `-groups`, `-entitlements` are the remainder of
#:    the set an Authentik **proxy outpost** conventionally emits.
#:
#: This is a hypothesis under test, not a claim about the deployment. Whether any
#: of them actually arrives is precisely what the probe measures; a candidate
#: reported `absent` is a real observation, not a failure.
#:
#: DO NOT extend this by discovery. Adding "report every header we received"
#: would turn the probe into a complete ingress-configuration dump and would leak
#: header names that are not on any list here.
IDENTITY_CANDIDATES: tuple[IdentityCandidate, ...] = (
    IdentityCandidate("username", "X-authentik-username", False, True),
    IdentityCandidate("uid", "X-authentik-uid", False, True),
    IdentityCandidate("email", "X-authentik-email", False, True),
    IdentityCandidate("display_name", "X-authentik-name", False, True),
    IdentityCandidate("groups", "X-authentik-groups", False, True),
    IdentityCandidate("entitlements", "X-authentik-entitlements", False, True),
    # Not an identity claim: a bespoke marker the portal reads to tell whether a
    # request arrived through the edge. Included because "did the edge touch this
    # request at all" is the same question the probe exists to answer.
    IdentityCandidate("edge_marker", "X-Isaac-Edge", False, False),
)

#: The header names, in candidate order. The caller reads exactly these.
CANDIDATE_HEADERS: tuple[str, ...] = tuple(c.header for c in IDENTITY_CANDIDATES)


# --- shape classification (pure) ----------------------------------------------


def _decode(value: Any) -> str | None:
    """Return the value as text, or ``None`` when it is not decodable.

    Starlette hands header values back latin-1 decoded, so a `str` is the normal
    case. `bytes` is accepted so the classifier can be unit-tested against the
    "not decodable" branch, which is defined as *not valid UTF-8*.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _has_control_character(text: str) -> bool:
    """True when the text contains a C0, C1, or DEL code point."""
    for ch in text:
        code = ord(ch)
        if code < 0x20 or code == 0x7F or 0x80 <= code <= 0x9F:
            return True
    return False


def _is_malformed(value: Any) -> bool:
    text = _decode(value)
    if text is None:
        return True
    if not text.strip():
        return True
    return _has_control_character(text)


def classify_shape(values: Sequence[Any] | None) -> str:
    """Classify a header's RAW value list into exactly one shape.

    `values` is every value the header carried — Starlette's
    ``request.headers.getlist(name)`` — so a duplicated header is visible as such
    rather than collapsing to the first or last copy.

    Returns one of :data:`SHAPES`. Precedence is :data:`SHAPE_PRECEDENCE`.

    Returns a shape and nothing else: no value, no length, no count of copies.
    (A count would be a value-derived number, and two duplicates versus five is
    an ingress detail the probe has no need to disclose.)
    """
    if not values:
        return SHAPE_ABSENT
    if any(_is_malformed(v) for v in values):
        return SHAPE_MALFORMED
    if len(values) > 1:
        return SHAPE_DUPLICATE
    text = _decode(values[0])
    # Unreachable in practice: a None here would have been caught as malformed.
    if text is None:  # pragma: no cover - defensive
        return SHAPE_MALFORMED
    if any(sep in text for sep in LIST_SEPARATORS):
        return SHAPE_LIST
    return SHAPE_SCALAR


# --- canary comparison (pure) --------------------------------------------------


def canary_survived(values: Sequence[Any] | None, canary: str | None) -> bool:
    """True when the canary reached the app as a whole value OR as a list segment.

    Every value is compared, not just the first, so a duplicated header in which
    only one copy is the client's forgery is still detected — that is the exact
    signature of an ingress that *appends* its own value rather than *replacing*
    the client's, which is the most dangerous of the four possible Q3 answers.

    **The segment comparison is not belt-and-braces; without it this function
    returns the wrong answer in the unsafe direction.** An intermediary that
    *coalesces* rather than duplicates — joining the client's forged copy and the
    injected value into one header with a separator — is the same append attack
    wearing a different shape, and it is not hypothetical: joining on ``,`` or
    ``|`` is precisely what :data:`LIST_SEPARATORS` exists to model, because it is
    what Authentik does to `groups` and `entitlements`. A whole-value-only compare
    reports ``False`` there, the operator reads "the ingress strips forged
    headers", and a later authorization slice is built on a survival that actually
    happened. So each value is also split on the separators and each stripped
    segment compared.

    Comparison is :func:`hmac.compare_digest` over bytes. Returns a bare boolean —
    no position, no count, no index, no segment number, and no indication of
    *which* of the two comparisons matched.

    **THIS FIELD IS A CONTAINMENT ORACLE, AND THAT IS A DELIBERATE, BOUNDED
    TRADE — not a free win.** An earlier revision of this docstring claimed the
    segment check "widens what the probe can detect without widening what it can
    disclose". That was false and is recorded rather than deleted. Nothing
    requires the caller to have planted the string: the field does not test
    *survival*, it tests *containment of a caller-chosen string*. Whole-value
    matching was already an oracle in principle, but against a joined value an
    attacker had to guess the entire header; segment matching reduces that to
    guessing **one segment** — and for `groups` the vocabulary is two entries this
    repository publishes (`docs/deployment.md`, `docs/developer-guide-k8s.md`).
    So a caller can learn, one bit per request per header, whether their own
    `groups` header contains `admin`.

    Bounding it honestly: the disclosure is to an **authenticated caller about
    their own headers**. CORS sets ``allow_credentials=False`` (`app.py`), so no
    cross-origin page can make a victim's browser send its session and read the
    answer; an in-cluster caller bypassing the edge supplies its own headers and
    learns nothing. The trade is accepted because the alternative — whole-value
    matching only — reports "the ingress strips forged headers" when it does not,
    which is a wrong answer in the unsafe direction on the probe's central
    question.
    """
    if not canary:
        return False
    expected = canary.encode("utf-8")
    found = False
    for value in values or ():
        if isinstance(value, str):
            raw = value.encode("utf-8", errors="replace")
        elif isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
        else:  # pragma: no cover - defensive
            continue
        # Deliberately no short-circuit anywhere below: every copy and every
        # segment is compared, so the work done does not depend on what matched.
        if hmac.compare_digest(raw, expected):
            found = True
        for segment in _split_segments(raw):
            if hmac.compare_digest(segment, expected):
                found = True
    return found


def _split_segments(raw: bytes) -> list[bytes]:
    """Split a raw header value on every list separator, stripping whitespace.

    Splits on all of :data:`LIST_SEPARATORS` at once — an intermediary is not
    obliged to pick one, and a value joined with a mixture must not hide a
    segment. Returns whole-value-only when the value carries no separator, which
    the caller has already compared; a redundant compare is cheaper than a branch
    whose timing depends on the value's content.
    """
    parts = [raw]
    for separator in LIST_SEPARATORS:
        split: list[bytes] = []
        for part in parts:
            split.extend(part.split(separator.encode("utf-8")))
        parts = split
    return [part.strip() for part in parts]


# --- frozen response allowlists + projection ----------------------------------
#
# Mirrors the `_DB_RECON_*` pattern in `routes.py` exactly (see `routes.py`'s
# `_db_recon_database_block` docstring). The response is built key-by-key FROM
# the allowlist tuple, so an unlisted key can never be served regardless of
# `strict`: a projection onto a fixed allowlist cannot invent a key.

#: The FROZEN top-level key allowlist. Every response shape — ok, disabled,
#: error — carries exactly these keys and nothing else.
RESPONSE_KEYS: tuple[str, ...] = (
    "status",
    "probe_contract_version",
    "app_commit",
    "generated_at",
    "edge_path_expectation",
    "claims",
    "limitations",
)

#: The FROZEN per-claim key allowlist. Frozen for the reason G3 exists (see
#: `CLAUDE.md` §15): in the database reconnaissance slice, only the TOP-LEVEL
#: keys were frozen, so five record-derived aggregates shipped inside a nested
#: block without tripping a single contract test. A nested block that is not
#: itself allowlisted is where the next leak goes.
CLAIM_KEYS: tuple[str, ...] = (
    "claim",
    "header",
    "present",
    "shape",
    "consumed_by_isaac",
    "client_canary_survived",
)

#: Keys whose string value is NOT a compile-time constant, and is therefore
#: exempt from the constant-universe check. Both are deployment identity already
#: published unauthenticated on `GET /api/health`; neither is derived from a
#: request, a header, or the canary.
FREE_VALUE_KEYS: tuple[str, ...] = ("app_commit", "generated_at")

#: A fixed constant. States the expectation and, in the same breath, that this
#: operation cannot verify it — because it cannot. `docs/deployment.md:32-34`
#: records that pod probes reach the container port directly, bypassing the
#: ingress; `docs/identity-trust-contract.md` §2 records that anything in the
#: cluster able to reach the Service does the same, and that `ISAAC_UI_API_KEY`
#: is unset in production. A response saying `present: true` therefore does NOT
#: establish that the caller passed through Authentik.
EDGE_PATH_EXPECTATION = (
    "When served under /krish, this operation is EXPECTED to be reachable only "
    "through the Authentik forward-auth edge. This operation CANNOT VERIFY THAT "
    "AND DOES NOT ASSERT IT: pod probes reach the container port directly, and "
    "any in-cluster workload that can reach the Service bypasses the ingress "
    "and therefore bypasses Authentik entirely. Nothing in this response is "
    "evidence that the caller was authenticated."
)

#: Fixed strings, present in every response shape, saying what the probe cannot
#: establish. Constants — nothing is interpolated, so this adds no leak surface.
LIMITATIONS: tuple[str, ...] = (
    "Presence only. No header value, and nothing derived from one — no hash, "
    "no digest, no fingerprint, no length, no character count — is reported.",
    "A candidate reported absent may be absent because the Authentik provider "
    "does not emit it, because the ingress auth-response-headers annotation "
    "does not forward it, or because this request never traversed the edge. "
    "This operation cannot distinguish those three causes.",
    "The candidate list is a fixed compile-time allowlist, not a discovery. A "
    "header this deployment receives under a name not on the list is invisible "
    "here and its name is never reported.",
    "client_canary_survived reports whether the string in the request body is "
    "present in that header as a whole value OR as a separator-delimited "
    "segment. The caller need not have planted it, so this is a guess-and-check "
    "containment test over the caller's own headers, not a proof of survival: a "
    "caller can learn one bit per request about what their own header contains. "
    "False does not prove the ingress strips forged headers on every path; true "
    "proves it does not strip them on this one.",
    "Segment matching exists so that an intermediary which COALESCES the "
    "client's copy with an injected one is reported as survival rather than as a "
    "strip. A string transformed in any other way — re-encoded, case-folded, "
    "quoted, truncated — is still reported absent, so false means 'not found in "
    "either of those two forms', never 'provably removed'.",
    "A point-in-time observation. The Authentik provider's header set and the "
    "ingress annotation are configured in ISAAC-DOE/isaac-k8, outside this "
    "repository, and can change with no signal here.",
    "This probe is temporary and is intended to be removed once the header "
    "contract has been observed and recorded. See docs/identity-probe.md.",
)


class IdentityProbeError(Exception):
    """A response was built with a key the frozen allowlist does not have.

    A developer-error detector. Raised on the success path only; see
    :func:`build_response`.
    """


def _project(
    built: dict, allowlist: tuple[str, ...], *, strict: bool, what: str
) -> dict:
    """Project `built` onto `allowlist`, key-by-key.

    `strict` additionally RAISES when the builder produced a key the allowlist
    does not have, or omitted one it does — so a new field cannot be added and
    silently dropped, and a renamed field cannot silently become null.

    `strict` is set on the success path only, and deliberately NOT on the failure
    envelopes: those are what a raise degrades INTO, so if they raised too, a
    broken allowlist would escape as an unhandled 500 with a traceback instead of
    the sanitized envelope. Fail-closed has to include the closing. (Same
    reasoning as `routes.py`'s `_db_recon_database_block`; see `CLAUDE.md` §15.)
    """
    if strict:
        extra = set(built) - set(allowlist)
        if extra:
            raise IdentityProbeError(f"{what} key not on the frozen allowlist")
        missing = set(allowlist) - set(built)
        if missing:
            raise IdentityProbeError(f"{what} key missing from the built payload")
    return {key: built.get(key) for key in allowlist}


def build_claim(
    candidate: IdentityCandidate,
    values: Sequence[Any] | None,
    canary: str | None,
    *,
    strict: bool = True,
) -> dict:
    """One claim entry, projected onto :data:`CLAIM_KEYS`.

    `claim` and `header` are constants from the allowlist — never a name read
    from the request. `present`, `shape` and `client_canary_survived` are the
    only request-dependent fields, and all three are a boolean or a member of
    :data:`SHAPES`.
    """
    shape = classify_shape(values)
    built = {
        "claim": candidate.claim,
        "header": candidate.header,
        "present": shape != SHAPE_ABSENT,
        "shape": shape,
        "consumed_by_isaac": candidate.consumed_by_isaac,
        "client_canary_survived": canary_survived(values, canary),
    }
    return _project(built, CLAIM_KEYS, strict=strict, what="claim")


def build_response(
    *,
    status: str,
    claims: list[dict],
    app_commit: str | None,
    generated_at: str,
    strict: bool = True,
) -> dict:
    """A response built from the FROZEN key allowlist. Nothing else can get in."""
    built = {
        "status": status,
        "probe_contract_version": PROBE_CONTRACT_VERSION,
        "app_commit": app_commit,
        "generated_at": generated_at,
        # Constant, in EVERY shape, so the key set stays frozen and uniform.
        "edge_path_expectation": EDGE_PATH_EXPECTATION,
        "claims": claims,
        "limitations": list(LIMITATIONS),
    }
    return _project(built, RESPONSE_KEYS, strict=strict, what="response")


def observe(
    getlist,
    canary: str | None,
    *,
    app_commit: str | None,
    generated_at: str,
    strict: bool = True,
) -> dict:
    """Build the `ok` response by reading ONLY the allowlisted candidates.

    `getlist` is a callable taking one header NAME and returning every value that
    header carried (``request.headers.getlist``). It is called exactly once per
    entry in :data:`IDENTITY_CANDIDATES` and with no other name, so this function
    structurally cannot see `Authorization`, `Cookie`, `X-Filename`, or any
    header outside the allowlist. There is no iteration over the header mapping
    anywhere in this module.
    """
    trimmed = canary if canary and len(canary) <= MAX_CANARY_LENGTH else None
    claims = [
        build_claim(candidate, getlist(candidate.header), trimmed, strict=strict)
        for candidate in IDENTITY_CANDIDATES
    ]
    return build_response(
        status=STATUS_OK,
        claims=claims,
        app_commit=app_commit,
        generated_at=generated_at,
        strict=strict,
    )


def sanitized_envelope(
    status: str, *, app_commit: str | None, generated_at: str
) -> dict:
    """The refusal/error/disabled shape: the frozen top-level keys, no claims.

    Built with ``strict=False`` on purpose — this is what a strict raise degrades
    INTO, so it must not be able to raise. Carries nothing from the request: no
    header, no header name beyond the constants, no canary, no exception text.
    """
    return build_response(
        status=status,
        claims=[],
        app_commit=app_commit,
        generated_at=generated_at,
        strict=False,
    )


# --- the constant-universe guard ----------------------------------------------

#: Every string that may legitimately appear anywhere in a probe response,
#: outside :data:`FREE_VALUE_KEYS`. Assembled from the constants above, so it
#: cannot drift away from what the builders actually emit.
CONSTANT_STRINGS: frozenset[str] = frozenset(
    (
        *STATUSES,
        *SHAPES,
        *(c.claim for c in IDENTITY_CANDIDATES),
        *CANDIDATE_HEADERS,
        EDGE_PATH_EXPECTATION,
        *LIMITATIONS,
    )
)

#: Every key that may appear anywhere in a probe response.
_ALLOWED_KEYS: frozenset[str] = frozenset((*RESPONSE_KEYS, *CLAIM_KEYS))


def assert_only_constant_strings(payload: Any, *, _key: str | None = None) -> None:
    """Raise :class:`IdentityProbeError` unless EVERY string is a known constant.

    The last line of defence, and deliberately a different kind of check from
    `db_recon.scan_for_leaks`. A substring scan proves that *specific known-bad
    text* is absent; it cannot prove that an unanticipated derivative of a header
    is absent, because the scanner would have to already know what to look for.
    This check inverts that: every string in the payload must be drawn from a
    closed set of compile-time constants (plus the two deployment-identity fields
    in :data:`FREE_VALUE_KEYS`, neither of which is request-derived). A header
    value, a fragment of one, a hash of one, or a header name that is not on the
    candidate allowlist all fail it, without the guard needing to recognise them.

    Booleans, integers and ``None`` pass: the request-dependent facts the probe
    reports are exactly a boolean and a member of :data:`SHAPES`, and no integer
    in the payload is derived from a header (`probe_contract_version` is a code
    constant).
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if not isinstance(key, str) or key not in _ALLOWED_KEYS:
                raise IdentityProbeError("response key not on the frozen allowlist")
            assert_only_constant_strings(value, _key=key)
        return
    if isinstance(payload, list):
        for item in payload:
            assert_only_constant_strings(item, _key=_key)
        return
    if isinstance(payload, str):
        if _key in FREE_VALUE_KEYS:
            return
        if payload not in CONSTANT_STRINGS:
            raise IdentityProbeError("non-constant string in the probe response")
        return
    # bool is a subclass of int; both are fine, as is None.
    if payload is None or isinstance(payload, (bool, int)):
        return
    raise IdentityProbeError("unexpected value type in the probe response")
