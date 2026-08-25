"""The server-owned attribution stamp — `attribution.uploaded_by`, and nothing else.

WHAT THIS IS
============
The official schema declares one field the SERVER owns
(``schema/isaac_record_v1.json``, ``attribution.uploaded_by``)::

    "Authenticated identity that submitted this record. Set by the server; any
     client value is overwritten."

and the block-level description names the decision that put it there (D. Sokaras,
2026-06-15): *"uploaded_by is SERVER-STAMPED from the authenticated identity at
ingestion — client-supplied values are overwritten (tamper-proof attribution)."*

This module is the ingestion-side stamp that description specifies. It is the ONLY
place in the application that may write that field, and the value it writes comes
from :func:`isaac_api.identity.stamp_actor` — never from a draft, never from a
request body, never from a header.

WHY IT LIVES HERE AND NOT IN THE TRUTH CORE
===========================================
``src/isaac_records/export.py::_enforce_server_owned_invariant`` says it directly,
and this module is written to obey it rather than to work around it:

    Do NOT turn this into a server-stamp. A future stamped value (Q10,
    docs/identity-trust-contract.md §7) must be injected on the trusted server side
    at ingestion — never read from draft content, and never plumbed through this
    function as a caller-supplied argument, which would only move the same untrusted
    input one frame up.

So the truth core is unchanged in every respect. ``transform`` still emits no
``uploaded_by``; ``draft_validator`` still refuses all four draft spellings of it;
``_enforce_server_owned_invariant`` still strips it from every assembled record.
``tests/test_attribution_uploaded_by.py`` pins all of that and none of it moves.
The stamp is applied strictly AFTER the truth core has finished, to a COPY, on the
one path that writes an artifact to disk.

**The layering is the security property, not a filing convention.** A draft-borne
value and a verifier-borne value are indistinguishable once they are both "a string
in a dict"; keeping the two in different modules, reached by different call paths,
is what makes "the truth core never sees an actor" mechanically true rather than
carefully maintained.

WHAT IT STAMPS IN THIS BUILD: NOTHING, ON EVERY DEPLOYMENT SHIPPED
=================================================================
:func:`isaac_api.identity.stamp_actor` returns ``None`` unless the deployment
configured a verifier that attributed the request, and no verifier this build ships
reads anything from a request. On the hosted pod and on every default deployment
the stamp is therefore **absent**, and the field is omitted rather than written
empty — which is the honest shape, because the schema does not mark it required and
an empty string would assert an identity of "".

That is not a gap pending a credential. Dean's answer of 2026-08-12 is that the
Service is a plain ClusterIP with no NetworkPolicy, so **the presence of an
edge-injected identity header is not proof of authenticated edge traversal**
(``docs/identity-trust-contract.md`` §2, Q4).

*The header is deliberately not named here.* ``test_identity_trust`` asserts that no
module under ``apps/api/isaac_api/`` except :mod:`isaac_api.identity` names one, and it
caught this file's first draft doing exactly that. The guard is a text scan and so is
easy to satisfy dishonestly; satisfying it honestly means the name lives in one place
and every other module points at it, which is also what stops a reader here from
concluding that this module has any business with headers. It has none.

Until a trusted boundary exists (E1), there is no name this application may
truthfully stamp, and writing one anyway is the exact fabricated-actor defect the
whole seam exists to prevent. Fail-closed here means *omit*, and omitting is what
this module does.

What the slice buys, then, is that when E1 arrives the change is a verifier and a
configuration value — not a product change, not a schema change, not a migration.

WHY THE STAMP DOES NOT REFUSE THE OPERATION
===========================================
Export and submit do NOT depend on :func:`~isaac_api.identity.require_human_actor`
for this. ``uploaded_by`` is optional in the schema, every record in this repository
was exported without it, and refusing an export because the deployment cannot name
an uploader would take a working product away in exchange for a field the schema
says may be absent.

So the rule is: **fail-open on availability, fail-closed on attribution.** The
operation always proceeds; the field appears only when somebody vouched for a name.
Submission is different and stays different — it already refuses without an actor
(``routes.post_submit`` → ``require_human_actor("submit")``), because a submission
is a declaration by a person and an unattributable one is not a thing this project
wants to record.

THE DRIFT PROBLEM, WHICH IS WHY :func:`without_server_stamp` EXISTS
==================================================================
``dependencies.artifact_state`` decides whether an exported artifact is still a
faithful projection of the current draft by comparing the on-disk record against a
fresh ``transform`` of the draft. ``transform`` cannot emit ``uploaded_by`` — that
is its invariant — so a stamped artifact would differ from it on every read, and
every stamped record would report ``stale`` forever, with the offered remedy being
a destructive workspace reset.

That is not hypothetical; it is the shape ``workspace.without_sibling_links`` was
written to fix for a different field, and this follows that precedent exactly:
normalise **both sides** of the comparison, narrowly, and say what is lost. What is
lost here is that a change to the stamp alone does not stale an artifact. That is
correct rather than tolerated: the stamp is not draft content, so "the record
changed after export" is not what a differing stamp means.
"""

from __future__ import annotations

import copy
from typing import Any

from . import identity as identity_module

__all__ = [
    "SERVER_STAMPED_BLOCK",
    "SERVER_STAMPED_LEAF",
    "resolve_uploaded_by",
    "with_server_stamp",
    "without_server_stamp",
]

#: The two path segments of the one server-owned field. Split rather than spelled,
#: for the same reason ``draft_validator.UPLOADED_BY_PATH`` is: one definition, so a
#: rename cannot leave a stale literal behind in a guard that then silently passes.
SERVER_STAMPED_BLOCK = "attribution"
SERVER_STAMPED_LEAF = "uploaded_by"


def resolve_uploaded_by(identity: Any, scope: str | None) -> str | None:
    """The subject this request may be attributed to IN AN OFFICIAL RECORD, or ``None``.

    :func:`isaac_api.identity.stamp_actor` first — it is where the worked-example rule
    and the trust-tier rule are written down, and reaching past it to
    ``identity.human.subject`` is the exact shape ``identity.py``'s docstring warns
    about. A rule added there reaches this path without anybody remembering this path
    exists.

    THEN ONE FURTHER GATE, AND IT IS NOT A SECOND COPY OF ANYTHING — it is a rule that
    is true HERE and nowhere else. An independent review measured why. ``stamp_actor``
    returns a subject for any ``EDGE_HUMAN`` identity, which includes one minted by
    :class:`~isaac_api.identity.FixtureEdgeVerifier` from two environment variables.
    Every OTHER consumer of that subject writes a row that also carries
    ``trust_basis``, so a fixture-attributed row says so about itself — which is the
    mitigation ``FixtureEdgeVerifier``'s own docstring stakes its existence on:
    *"If this verifier is ever enabled somewhere it should not be, the resulting rows
    say so about themselves."*

    **An official ISAAC record has no such field.** The schema gives
    ``attribution.uploaded_by`` one meaning — *"Authenticated identity that submitted
    this record"* — and no place to qualify it. So a fixture name written there is
    permanent, immutable, and indistinguishable from a real edge attribution, in a
    document that outlives this application. Both this module and ``identity.py`` say
    the rule out loud (*"there is no name this application may truthfully stamp"*,
    *"the field appears only when somebody vouched for a name"*), and a verifier that
    read an environment variable vouched for nobody.

    Hence: only :data:`~isaac_api.identity.TRUST_BASIS_VERIFIED_EDGE_ASSERTION` may
    reach a record. **No verifier in this build mints that basis**, so the practical
    effect is that no shipped deployment stamps anything — which is the finished
    behaviour this module already documented, now enforced rather than merely true by
    accident of which verifiers exist.

    The fixture path is NOT weakened elsewhere by this: it still satisfies
    ``require_human_actor``, still attributes a submission row, and is still the way
    the seam is exercised. It simply stops short of the one artifact that cannot carry
    its own caveat.
    """
    subject = identity_module.stamp_actor(identity, scope)
    if subject is None:
        return None
    human = getattr(identity, "human", None)
    if human is None:  # pragma: no cover - stamp_actor guarantees a human above
        return None
    if human.trust_basis != identity_module.TRUST_BASIS_VERIFIED_EDGE_ASSERTION:
        return None
    return subject


def with_server_stamp(record: dict, subject: str | None) -> dict:
    """``record`` with the server-owned attribution stamp applied, as a NEW dict.

    Returns the record unchanged (by value) when ``subject`` is ``None``, which is
    every deployment this build ships. Never mutates its argument: the caller's
    ``record`` is ``export_draft``'s output, which other code reads afterwards for
    the record id and the sidecar, and a stamp is not something those readers asked
    for.

    A non-``dict`` ``attribution`` is left alone rather than replaced. A draft can
    produce one (``fields["attribution"]`` carrying a list or a scalar), and the
    honest handling is the one the truth core already chose for the same shape: do
    not silently rewrite a client's structure into something else. Such a record is
    refused by official validation as a type error, which is where that refusal
    belongs — a stamp is not a validator and must not become one.
    """
    if subject is None:
        return record
    existing = record.get(SERVER_STAMPED_BLOCK)
    if existing is not None and not isinstance(existing, dict):
        return record
    stamped = copy.deepcopy(record)
    block = stamped.get(SERVER_STAMPED_BLOCK)
    if not isinstance(block, dict):
        block = {}
        stamped[SERVER_STAMPED_BLOCK] = block
    block[SERVER_STAMPED_LEAF] = subject
    return stamped


def without_server_stamp(record: dict) -> dict:
    """``record`` with the server-owned stamp removed — the shape ``transform`` emits.

    PUBLIC, and used by one MODULE: ``dependencies``, in ``artifact_state`` and in its
    fan-out sibling, applied to BOTH sides of the freshness comparison. (An earlier
    revision said "exactly one caller" and then named two, which is the kind of small
    untruth this file is otherwise careful about.) It lives here
    because the field name it removes is defined here, and a second copy of that name
    in the freshness module would be free to drift away from what the write actually
    stamps.

    An ``attribution`` block that becomes EMPTY is dropped entirely, and that detail
    is load-bearing rather than tidy. ``transform`` emits no ``attribution`` key at
    all for a draft that carries no attribution evidence, so leaving ``{}`` behind
    would make the two sides differ on a key's presence and reintroduce the permanent
    ``stale`` this function exists to prevent — one level down, where it would be
    harder to see.

    Narrow on purpose: only this one leaf is removed, from both sides, so every other
    attribution field a draft legitimately evidences (``contributors``, ``contact``,
    anything the schema allows) still stales its artifact when it changes.
    """
    block = record.get(SERVER_STAMPED_BLOCK)
    if not isinstance(block, dict) or SERVER_STAMPED_LEAF not in block:
        return record
    stripped = copy.deepcopy(record)
    remaining = stripped[SERVER_STAMPED_BLOCK]
    del remaining[SERVER_STAMPED_LEAF]
    if not remaining:
        del stripped[SERVER_STAMPED_BLOCK]
    return stripped
