"""Schema Proposals: drafting and tracking proposals to change the ISAAC vocabulary.

WHAT THIS IS, AND WHAT IT IS NOT
================================
A scientist who meets a term the ISAAC vocabulary does not have should be
able to say so in a form the owners of the standard can act on. The upstream ISAAC
portal ("Living Ontology" -> "Propose a Change") is where those owners review
proposals. This module lets a proposal be DRAFTED and TRACKED here and handed to the
portal unchanged.

**ISAAC does not approve, apply or forward anything.** There is no approve endpoint,
no apply endpoint, and nothing here calls the portal (a test pins both: the route
table has no such operation, and this module imports no HTTP client). The two status
values this build records are ``pending`` and ``withdrawn``. ``accepted`` and
``rejected`` are decisions the standard's owners make in the portal; they are
deliberately NOT part of this vocabulary, because a status ISAAC cannot establish is a
status it must not display.

THE UPSTREAM CONTRACT THIS MIRRORS
==================================
``portal/database.py`` (``vocabulary_proposals``) and ``portal/api.py``
(``POST /portal/api/vocabulary/proposals``) of the upstream repository:

* ``proposal_type`` is ``add_term`` or ``add_category``;
* ``add_term`` carries ``section``, ``category``, ``term``, ``description``;
* ``add_category`` carries ``section``, ``category``, ``description`` (no ``term``);
* the portal's own rules: a term is ONE token of at most 80 characters with no
  whitespace; a description is at least 20 characters; a term already in the category
  is refused; a person may have at most 50 proposals waiting.

``GET /api/schema-proposals/{id}/portal-payload`` returns exactly the body the portal
takes, so a person who can reach the portal can send it without retyping.

THE THIRD TYPE IS ISAAC'S OWN, AND IS NEVER A PORTAL PAYLOAD (2026-10-29)
=========================================================================
The portal has no proposal type for a new FIELD (read at ``a1cb1c8``: ``create_proposal``,
``apply_approved_proposal`` and the Propose a Change form know the two types above only).
``schema_change`` (kind ``add_field``) is therefore a *schema change request*: a parent block
the vendored schema declares, a field name, a type, whether it is required, and the gate-0
problem the upstream process (``governance/README.md``) requires. ``portal-payload`` refuses
it (``409 no_portal_payload``); its export is ``GET .../{id}/change-request``, a Markdown and
JSON document for the standard's owners, labelled as not a portal proposal. The rules and
both export formats live in :mod:`isaac_api.schema_proposal_rules`, which imports no web
framework, so ``isaac bundle propose-terms`` drafts in exactly this format locally.

TWO VOCABULARY SOURCES, BOTH LABELLED, NEITHER LIVE
===================================================
The portal validates a proposal against ITS OWN list (``data/vocabulary.json`` upstream:
68 term lists), and the vendored schema carries its own enums (36 lists). They overlap by
only 30. So the screen shows both, labelled, and a proposal is checked against the one
that will judge it:

* ``portal`` — a verbatim snapshot (``data/portal_vocabulary_a1cb1c8.json``, provenance in
  ``data/PORTAL_VOCABULARY_PROVENANCE.md``). A snapshot, not the live portal.
* ``schema`` — derived at request time from the vendored schema's enums (below).

``add_term`` is valid only against a portal list (the portal would refuse any other),
``add_category`` is refused for a key either source already has and for any schema field
that is not a text field. Neither source is "the official vocabulary" on its own, and the
copy says what each is.

THE SCHEMA SIDE IS DERIVED, NEVER TRANSCRIBED
=============================================
:func:`derive_vocabulary` walks the vendored ``schema/isaac_record_v1.json`` and reads
every ``enum``. A *category* is an enum-bearing property (arrays are looked through to
their ``items``); a *section* is a top-level block of the record, plus ``Record Info``
for the root fields. The category key is the dotted property path, which is the form
the portal uses (``context.environment``, ``system.technique``, and for a root field
just ``record_type``). A hand-written list would be a second definition free to drift
from the one every record is validated against.

IDENTITY IS NOT TRUSTED IN THIS BUILD
=====================================
``proposed_by`` is never read from the request body. It is filled only from
:func:`isaac_api.identity.resolve_identity_for_request`, and only when that identity is
a person vouched for by a verified edge assertion. No verifier in this build mints one,
so on every deployment this build ships, ``proposed_by`` is ``null`` and
``attribution`` is ``"unverified"``. A name typed into the body is ignored, and the
response says it was.

STORAGE: WORKSPACE FILES, TEMPORARY ON THE HOSTED SERVER
========================================================
One JSON file per proposal under ``<workspace>/_schema_proposals/<id>.json``, written
atomically with :func:`isaac_api.workspace.atomic_write_text`: the same mechanism an
import session uses, for the same reason (no migration, no database table; the
``_`` prefix keeps it out of every experiment listing). On the hosted deployment the
workspace directory is an ``emptyDir`` and does not survive a restart, so every
response says proposals on this server are temporary and should be sent to the ISAAC
portal (copy or download the payload). There is no revision token: the store has one
mutation that needs ordering (a proposal is created or withdrawn), and a single
in-process lock serialises it, which is the arrangement the workspace documents for
this single-process server.
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Path as PathParam, Query, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from isaac_records.ids import is_record_id, new_record_id
from isaac_records.official import EXPECTED_VERSION, schema_path

from . import identity as identity_module
from . import workspace as ws

# The rules and formats live in a module with no web framework, so the local-first CLI can
# draft in exactly this format (see that module's docstring). Every name this module used
# to define is re-exported here unchanged.
from .schema_proposal_rules import (  # noqa: F401  (re-exported)
    ADD_CATEGORY,
    ADD_TERM,
    ATTRIBUTION_UNVERIFIED,
    ATTRIBUTION_VERIFIED,
    LIMITS,
    PORTAL_PROPOSAL_TYPES,
    PORTAL_PROPOSALS_PATH,
    PORTAL_SNAPSHOT_COMMIT,
    PORTAL_SNAPSHOT_FILE,
    PORTAL_SNAPSHOT_LABEL,
    PROPOSAL_STATUSES,
    PROPOSAL_TYPES,
    ROOT_SECTION,
    ROOT_SECTION_LABEL,
    SCHEMA_CHANGE,
    SCHEMA_CHANGE_KINDS,
    SCHEMA_CHANGE_SCOPES,
    SCHEMA_CHANGE_VALUE_TYPES,
    STATUS_PENDING,
    STATUS_WITHDRAWN,
    TERM_SHAPE_FOR_CLIENTS,
    UPSTREAM_GOVERNANCE,
    _BODY_KEYS,
    _CATEGORY_SHAPE,
    _GATE0_FIELDS,
    _PATH_LIKE,
    _SERVER_OWNED_KEYS,
    _SNAKE_TERM,
    _TERM_SHAPE,
    _category_conflict,
    _clean_string,
    _error,
    _field_conflict,
    _find_section,
    _portal_key_exists,
    _portal_term_list,
    _safe_field_name,
    _same_proposal,
    _schema_enum,
    _section_label,
    _separator_free,
    _term_conflict,
    _text_problem,
    _validate,
    _validate_gate0,
    CHANGE_REQUEST_FORMAT,
    CHANGE_REQUEST_FORMAT_VERSION,
    NOT_A_PORTAL_PROPOSAL,
    change_request,
    combine_sources,
    derive_fields,
    derive_object_paths,
    derive_portal_vocabulary,
    derive_vocabulary,
    portal_body,
    portal_payload,
    portal_vocabulary_from_text,
    schema_vocabulary_from_text,
)

__all__ = [
    "PROPOSAL_STATUSES",
    "SCHEMA_PROPOSALS_TAG",
    "TAG_SCHEMA_PROPOSALS",
    "derive_vocabulary",
    "router",
]

# --- the contract's constants ---------------------------------------------------

TAG_SCHEMA_PROPOSALS = "Schema Proposals"

#: Registered next to ``routes.OPENAPI_TAGS`` by ``create_app``. A separate entry
#: rather than a reuse of ``Schema & Vocabulary``, whose published description says no
#: editing affordance exists: true of the schema, and misleading beside a POST.
SCHEMA_PROPOSALS_TAG: dict = {
    "name": TAG_SCHEMA_PROPOSALS,
    "description": (
        "Drafting and tracking proposals to change the ISAAC vocabulary. "
        "A proposal here is a draft for the standard's owners; it changes nothing "
        "in the schema, and ISAAC neither approves nor sends it. A new term or list is "
        "reviewed in the ISAAC portal; a schema change request through the upstream "
        "repository's change process."
    ),
}

PERSISTENCE: dict = {
    "class": "workspace_files",
    "survives_restart": "not_guaranteed",
    "message": (
        "Proposals on this server are temporary. They are kept in this server's "
        "working folder, not in a database, and on the hosted site that folder is "
        "cleared when the server restarts. Take each proposal off this server: a new term "
        "or list as its portal payload (copy it, or download it as JSON) for the ISAAC "
        "portal; a schema change request as its change-request document (Markdown or JSON) "
        "for the standard's owners."
    ),
}

REVIEW_NOTE = (
    "ISAAC drafts and tracks proposals; it does not approve, apply or send them, and it "
    "records no decision. The people who own the ISAAC standard review a new term or list "
    "in the ISAAC portal, and a schema change request through the upstream repository's "
    "own change process; any decision is recorded there, not here."
)

ATTRIBUTION_NOTE = (
    "Who is calling is not verified on this server, so a proposal records no "
    "author. Anyone who can reach this screen can see and withdraw any proposal."
)



@lru_cache(maxsize=4)
def _derive_cached(path_str: str, mtime_ns: int, size: int) -> tuple[str, str]:
    """Parse and derive once per schema file state. Returns ``(sha256, json)``."""
    vocabulary = schema_vocabulary_from_text(Path(path_str).read_text(encoding="utf-8"))
    digest = vocabulary.pop("schema_sha256")
    return digest, json.dumps(vocabulary)


@lru_cache(maxsize=4)
def _portal_cached(path_str: str, mtime_ns: int, size: int) -> tuple[str, str]:
    vocabulary = portal_vocabulary_from_text(Path(path_str).read_text(encoding="utf-8"))
    digest = vocabulary.pop("portal_sha256")
    return digest, json.dumps(vocabulary)


def _schema_file() -> Path:
    """The vendored schema. A function so a test can point it at a mutated copy."""
    return schema_path(ws.REPO_ROOT)


def _portal_file() -> Path:
    """The vendored portal snapshot. A function so a test can point it at a mutated copy."""
    return PORTAL_SNAPSHOT_FILE


def load_vocabulary() -> dict:
    """The schema-enum vocabulary for the schema file as it is NOW (cached on its stat).

    Carries ``fields`` (every property path and whether it is a text field) and
    ``object_paths`` (every place a new field could go) beside the sections, and
    ``schema_sha256``."""
    path = _schema_file()
    stat = path.stat()
    digest, payload = _derive_cached(str(path), stat.st_mtime_ns, stat.st_size)
    vocabulary = json.loads(payload)
    vocabulary["schema_sha256"] = digest
    return vocabulary


def load_portal_vocabulary() -> dict:
    """The portal snapshot as sections and categories, with ``portal_sha256``."""
    path = _portal_file()
    stat = path.stat()
    digest, payload = _portal_cached(str(path), stat.st_mtime_ns, stat.st_size)
    vocabulary = json.loads(payload)
    vocabulary["portal_sha256"] = digest
    return vocabulary


def load_sources() -> dict:
    """Both vocabulary sources and the union of their sections, for one request."""
    return combine_sources(load_vocabulary(), load_portal_vocabulary())


# --- the store ------------------------------------------------------------------

STORE_NAMESPACE = "_schema_proposals"

#: One lock for every mutation. The deployed server is a single process (see the
#: workspace's record lock), and create has to read the whole set to check a
#: duplicate and the caps, so a per-proposal lock would not cover it.
_STORE_LOCK = threading.RLock()


class ProposalStoreUnavailable(Exception):
    """The working folder could not be written."""


def store_root() -> Path:
    """``<workspace>/_schema_proposals``: normal scope only, never a worked-example session."""
    return ws.workspace_root() / STORE_NAMESPACE


def _proposal_path(proposal_id: str) -> Path | None:
    if not is_record_id(proposal_id):
        return None
    return store_root() / f"{proposal_id}.json"


def _readable(doc: Any, proposal_id: str) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("id") == proposal_id
        and doc.get("proposal_type") in PROPOSAL_TYPES
        and doc.get("status") in PROPOSAL_STATUSES
        and isinstance(doc.get("section"), str)
        and isinstance(doc.get("category"), str)
        and isinstance(doc.get("description"), str)
        and (doc.get("proposal_type") != SCHEMA_CHANGE or isinstance(doc.get("change"), dict))
    )


#: The keys of a stored schema change that a response may carry, built key by key in
#: :func:`_change_view` so an unexpected stored key never rides out.
_CHANGE_VIEW_KEYS = (
    "kind",
    "parent_path",
    "field_name",
    "path",
    "value_type",
    "unit",
    "required",
    "example",
    "scope",
    "migration",
    "parent_open_today",
)


def _change_view(doc: dict) -> dict | None:
    change = doc.get("change")
    if doc.get("proposal_type") != SCHEMA_CHANGE or not isinstance(change, dict):
        return None
    out: dict = {}
    for key in _CHANGE_VIEW_KEYS:
        value = change.get(key)
        out[key] = value if isinstance(value, (str, bool)) or value is None else None
    return out


def _load(proposal_id: str) -> dict | None:
    path = _proposal_path(proposal_id)
    if path is None or not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if _readable(doc, proposal_id) else None


def _save(doc: dict) -> None:
    path = _proposal_path(doc["id"])
    assert path is not None
    try:
        ws.atomic_write_text(path, json.dumps(doc, indent=2, ensure_ascii=True) + "\n")
    except OSError as exc:
        raise ProposalStoreUnavailable() from exc


def _all_proposals() -> list[dict]:
    """Every readable proposal, newest first. An unreadable file is skipped, so one
    corrupt document cannot empty the list for everyone."""
    root = store_root()
    if not root.is_dir():
        return []
    out: list[dict] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.suffix != ".json" or not is_record_id(entry.stem):
            continue
        doc = _load(entry.stem)
        if doc is not None:
            out.append(doc)
    # ULIDs begin with a millisecond timestamp, so id order is creation order.
    out.sort(key=lambda d: d["id"], reverse=True)
    return out


def _prune_withdrawn() -> int:
    """Remove the OLDEST withdrawn proposals beyond ``max_withdrawn_kept``; returns how many.

    A withdrawn proposal no longer counts toward the pending limit, so something has to bound
    how many are kept on disk; this keeps the newest ones and says how many it removed (the
    create response carries ``withdrawn_removed``). Pending proposals are never touched."""
    withdrawn = [d for d in _all_proposals() if d["status"] == STATUS_WITHDRAWN]
    excess = withdrawn[LIMITS["max_withdrawn_kept"] :]  # newest first, so the tail is the oldest
    removed = 0
    for doc in excess:
        path = _proposal_path(doc["id"])
        if path is None:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- views ----------------------------------------------------------------------


def _view(doc: dict) -> dict:
    """The public shape of one stored proposal. Built field by field, so an unexpected
    key in a stored file can never ride out in a response."""
    gate0 = doc.get("gate0") if isinstance(doc.get("gate0"), dict) else None
    return {
        "id": doc["id"],
        "proposal_type": doc["proposal_type"],
        "section": doc["section"],
        "category": doc["category"],
        "term": doc.get("term") if isinstance(doc.get("term"), str) else None,
        "description": doc["description"],
        "gate0": {k: gate0[k] for k in _GATE0_FIELDS if isinstance(gate0.get(k), str)} if gate0 else None,
        "status": doc["status"],
        "proposed_by": doc.get("proposed_by") if isinstance(doc.get("proposed_by"), str) else None,
        "attribution": (
            ATTRIBUTION_VERIFIED
            if doc.get("attribution") == ATTRIBUTION_VERIFIED and isinstance(doc.get("proposed_by"), str)
            else ATTRIBUTION_UNVERIFIED
        ),
        "proposed_at": doc.get("proposed_at"),
        "withdrawn_at": doc.get("withdrawn_at"),
        "schema_version": doc.get("schema_version"),
        "change": _change_view(doc),
        "sent_by_isaac": False,
    }


def _envelope(**extra: Any) -> dict:
    return {
        **extra,
        "persistence": copy.deepcopy(PERSISTENCE),
        "review_note": REVIEW_NOTE,
        "attribution_note": ATTRIBUTION_NOTE,
    }


# --- identity -------------------------------------------------------------------


def _attribution_for(request: Request) -> tuple[str | None, str]:
    """``(proposed_by, attribution)`` from the identity seam and nothing else.

    A subject is returned only for a person vouched for by a verified edge assertion.
    A fixture-attributed subject is NOT used: it is proof of a configuration, not of a
    person, and a proposal has to be able to say so about itself.
    """
    identity = identity_module.resolve_identity_for_request(request)
    subject = identity_module.stamp_actor(identity, None)
    human = getattr(identity, "human", None)
    if (
        subject
        and human is not None
        and human.trust_basis == identity_module.TRUST_BASIS_VERIFIED_EDGE_ASSERTION
    ):
        return subject, ATTRIBUTION_VERIFIED
    return None, ATTRIBUTION_UNVERIFIED


# --- the routes -----------------------------------------------------------------

class _CappedRequest(Request):
    """A request whose body is read with a ceiling, BEFORE anything parses it.

    FastAPI reads and parses the whole body before a handler runs, so a size check in the
    handler would come after the cost. This reads the stream itself, refuses on a declared
    ``Content-Length`` over the ceiling without reading, and counts the bytes of an
    undeclared (chunked) body as they arrive."""

    async def body(self) -> bytes:
        if not hasattr(self, "_body"):
            cap = LIMITS["max_body_bytes"]
            declared = self.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > cap:
                raise HTTPException(status_code=413, detail="body_too_large")
            chunks: list[bytes] = []
            total = 0
            async for chunk in self.stream():
                total += len(chunk)
                if total > cap:
                    raise HTTPException(status_code=413, detail="body_too_large")
                chunks.append(chunk)
            self._body = b"".join(chunks)
        return self._body


class _CappedRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(_CappedRequest(request.scope, request.receive))
            except HTTPException as exc:
                if exc.status_code == 413:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "body_too_large",
                            "message": f"A proposal is at most {LIMITS['max_body_bytes']} bytes; this request was larger and nothing was read or saved.",
                        },
                    )
                raise

        return handler


router = APIRouter(prefix="/api/schema-proposals", tags=[TAG_SCHEMA_PROPOSALS], route_class=_CappedRoute)

_R_UNAUTHORIZED: dict = {
    401: {
        "description": (
            "The deployment requires an API key and the request did not present a "
            "valid one. Never returned when the deployment leaves this "
            "authentication disabled, which is the default for local runs."
        )
    },
}

_R_NOT_FOUND: dict = {
    404: {
        "description": (
            "No proposal on this server has that id. A proposal on a hosted server "
            "may also be gone because the server restarted."
        )
    },
}

_R_STORE_UNAVAILABLE: dict = {
    503: {
        "description": (
            "This server's working folder could not be written, so nothing was saved."
        )
    },
}


def _refuse(status: int, error: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message, **extra})


def _not_found() -> JSONResponse:
    return _refuse(
        404,
        "proposal_not_found",
        "No proposal on this server has that id. Proposals here are temporary and may "
        "have been cleared by a restart.",
    )


def _unavailable() -> JSONResponse:
    return _refuse(
        503,
        "proposal_store_unavailable",
        "This server could not save the proposal, so nothing was saved. Try again, or "
        "copy the proposal into the ISAAC portal directly.",
    )


@router.get(
    "/vocabulary",
    summary="Browse the Vocabulary Sources",
    description=(
        "Two labelled lists of sections, categories and allowed terms. `portal` is a verbatim "
        "snapshot of the ISAAC portal's vocabulary file at a named upstream commit, the list "
        "the portal checks a proposed term against; it is a snapshot and the portal's own copy may "
        "have moved. `schema` is the enums of the vendored official record schema, read at the moment "
        "of the request, the lists a record is validated against. The two overlap only in part, "
        "and neither is the live portal.\n\n"
        "A category is a field whose value must be one of a fixed list; a section is a top-level "
        "block of the record, with the record's own root fields under Record Info. `proposal_sections` "
        "is the union a proposal may name, with the portal term lists a new term may join.\n\n"
        "`schema_change` describes the third proposal type, a new FIELD in the record schema, which the portal "
        "has no proposal type for: `object_paths` is every block of the vendored schema a field could go in "
        "(with its section, its existing fields, and whether it accepts undeclared keys today), and "
        "`upstream` names the upstream repository's own change process.\n\n"
        "The response also carries the limits a proposal is held to, so a client does not carry a second "
        "copy of them. It is read-only: nothing here changes the schema or the portal."
    ),
    response_description="Both vocabulary sources, the sections a proposal may name, and the proposal limits.",
    responses={**_R_UNAUTHORIZED},
)
def get_vocabulary() -> dict:
    sources = load_sources()
    schema_v, portal_v = sources["schema"], sources["portal"]
    schema_public = {k: schema_v[k] for k in ("sections", "section_count", "category_count", "term_count")}
    proposal_sections = []
    for sec in sources["sections"]:
        lists = [
            c["key"]
            for p in portal_v["sections"]
            if p["id"] == sec["id"]
            for c in p["categories"]
            if c["kind"] == "terms" and c["terms"]
        ]
        proposal_sections.append({**sec, "term_lists": lists})
    return {
        "schema_version": EXPECTED_VERSION,
        "default_source": "portal",
        "sources": {
            "portal": {
                "id": "portal",
                "label": PORTAL_SNAPSHOT_LABEL,
                "detail": (
                    "A copy of the ISAAC portal's vocabulary file at one upstream commit. A new term is checked "
                    "against these lists. It may be out of date: the portal's own copy is the one that decides."
                ),
                "snapshot_commit": PORTAL_SNAPSHOT_COMMIT,
                "sha256": portal_v["portal_sha256"],
                "section_count": portal_v["section_count"],
                "category_count": portal_v["category_count"],
                "term_list_count": portal_v["term_list_count"],
                "term_count": portal_v["term_count"],
                "sections": portal_v["sections"],
            },
            "schema": {
                "id": "schema",
                "label": f"Schema enums (vendored v{EXPECTED_VERSION})",
                "detail": (
                    "The fixed lists in the official record schema this build validates records against, read from "
                    "the vendored file. Only part of it is also a portal list."
                ),
                "derived_from": "schema/isaac_record_v1.json",
                "sha256": schema_v["schema_sha256"],
                **schema_public,
                "term_list_count": schema_public["category_count"],
            },
        },
        "proposal_sections": proposal_sections,
        "proposal_types": list(PROPOSAL_TYPES),
        "portal_proposal_types": list(PORTAL_PROPOSAL_TYPES),
        "schema_change": {
            "kinds": list(SCHEMA_CHANGE_KINDS),
            "value_types": list(SCHEMA_CHANGE_VALUE_TYPES),
            "scopes": list(SCHEMA_CHANGE_SCOPES),
            "object_paths": schema_v.get("object_paths") or [],
            "not_a_portal_proposal": NOT_A_PORTAL_PROPOSAL,
            "upstream": dict(UPSTREAM_GOVERNANCE),
        },
        "limits": dict(LIMITS),
        "term_shape": dict(TERM_SHAPE_FOR_CLIENTS),
        "term_rule": (
            "One word, no spaces, starting with a letter. If every existing term in the "
            "category is lowercase with underscores, a new term must be too."
        ),
        "review_note": REVIEW_NOTE,
    }


@router.post(
    "",
    status_code=201,
    summary="Draft a Schema Proposal",
    description=(
        "Saves a proposal to change the ISAAC vocabulary, in the shape the "
        "ISAAC portal takes. `proposal_type` is `add_term` (needs `section`, `category`, "
        "`term`, `description`) or `add_category` (needs `section`, `category`, "
        "`description`). An optional `gate0` object holds four free-text answers for "
        "reviewers: `problem`, `examples`, `affected_records_estimate`, `flip_list`.\n\n"
        "`schema_change` is a third type, ISAAC's own: a request for a new FIELD in the record schema "
        "(needs `section`, `description`, `gate0.problem` and a `change` object: `parent_path`, a block "
        "the vendored schema declares; `field_name`; `value_type`; `required`; optional `unit`, `example`, "
        "`scope`, `migration`). The ISAAC portal has no proposal type for this, so it has no portal "
        "payload; its export is the change-request document. A field the parent already has is "
        "`409 field_already_exists`.\n\n"
        "THIS APPROVES NOTHING AND SENDS NOTHING. The proposal is stored as `pending` "
        "on this server; the owners of the standard review it in the ISAAC portal, and "
        "any decision is recorded there. Use the portal-payload operation to get the "
        "exact body to send.\n\n"
        "Nobody is identified on this server, so `proposed_by` is `null` and "
        "`attribution` is `unverified`. A name in the request body is ignored and "
        "listed in `ignored_fields`. Proposals are temporary on a hosted server; the "
        "response says so in `persistence`.\n\n"
        "A body that fails validation is refused with `422` and an `errors` list, one "
        "entry per field (`field`, `code`, `message`), so a form can show each problem "
        "in place. A new term is checked against the portal vocabulary snapshot's list for the category "
        "(and the schema enum with the same key): one already there is `409 term_already_exists`, and a "
        "category the portal has no list for is `422`. A new category is refused with `409` when either "
        "source already has the key and with `422 category_not_a_text_field` for a schema field that "
        "does not take words. The same proposal already pending is `409 duplicate_pending_proposal`. "
        "A body over 131072 bytes is `413` and is not read."
    ),
    response_description="The saved proposal, as pending.",
    responses={
        **_R_UNAUTHORIZED,
        409: {
            "description": (
                "The term, category or field already exists in the schema, or an identical "
                "proposal is already pending."
            )
        },
        413: {"description": "The request body is larger than a proposal can be; it was not read."},
        429: {
            "description": (
                "This server already holds the maximum number of pending proposals. The "
                "limit is shared by everyone using this server (one workspace); withdrawing "
                "a proposal frees its place."
            )
        },
        **_R_STORE_UNAVAILABLE,
    },
)
def post_schema_proposal(
    request: Request,
    body: Any = Body(
        default=None,
        description=(
            "`{\"proposal_type\": \"add_term\" | \"add_category\", \"section\", "
            "\"category\", \"term\" (add_term only), \"description\", \"gate0\" "
            "(optional)}`, or `{\"proposal_type\": \"schema_change\", \"section\", \"description\", "
            "\"gate0\", \"change\"}`."
        ),
    ),
):
    if not isinstance(body, dict):
        return _refuse(422, "invalid_body", "The request body must be a JSON object.", errors=[])
    sources = load_sources()
    clean, errors, ignored = _validate(body, sources)
    if clean is None:
        return _refuse(
            422,
            errors[0]["code"],
            "The proposal needs a few changes before it can be saved.",
            errors=errors,
        )

    if clean["proposal_type"] == ADD_TERM:
        conflict = _term_conflict(sources, clean)
        if conflict is not None:
            where = "the portal vocabulary snapshot" if conflict["existing_in"] == "portal" else "the ISAAC schema"
            return _refuse(
                409,
                "term_already_exists",
                f"'{conflict['existing_term']}' is already an allowed term in this category ({where}). "
                "Use it instead of proposing it.",
                **conflict,
            )
    elif clean["proposal_type"] == SCHEMA_CHANGE:
        conflict = _field_conflict(sources, clean)
        if conflict is not None:
            return _refuse(
                409,
                "field_already_exists",
                f"The ISAAC schema already has the field {conflict['existing_field']}. Use it instead of "
                "proposing it.",
                **conflict,
            )
    else:
        conflict = _category_conflict(sources, clean)
        if conflict is not None:
            where = "the portal vocabulary snapshot" if conflict["existing_in"] == "portal" else "the ISAAC schema"
            return _refuse(
                409,
                "category_already_exists",
                f"That category or field already exists in {where}.",
                **conflict,
            )

    proposed_by, attribution = _attribution_for(request)
    doc = {
        "id": new_record_id(),
        "proposal_type": clean["proposal_type"],
        "section": clean["section"],
        "category": clean["category"],
        "term": clean["term"],
        "description": clean["description"],
        "gate0": clean["gate0"],
        "change": clean["change"],
        "status": STATUS_PENDING,
        "proposed_by": proposed_by,
        "attribution": attribution,
        "proposed_at": _now(),
        "withdrawn_at": None,
        "schema_version": EXPECTED_VERSION,
    }
    try:
        with _STORE_LOCK:
            existing = _all_proposals()
            for other in existing:
                if other["status"] == STATUS_PENDING and _same_proposal(other, doc):
                    return _refuse(
                        409,
                        "duplicate_pending_proposal",
                        "An identical proposal is already pending on this server.",
                        proposal_id=other["id"],
                    )
            pending = sum(1 for d in existing if d["status"] == STATUS_PENDING)
            if pending >= LIMITS["max_pending"]:
                return _refuse(
                    429,
                    "too_many_pending",
                    f"This server already holds {LIMITS['max_pending']} pending proposals. The limit is shared by "
                    "everyone using this server, and withdrawing a proposal frees its place. Send the pending "
                    "ones to the ISAAC portal first.",
                )
            _save(doc)
            removed = _prune_withdrawn()
    except ProposalStoreUnavailable:
        return _unavailable()
    return JSONResponse(
        status_code=201,
        content=_envelope(proposal=_view(doc), ignored_fields=ignored, withdrawn_removed=removed),
    )


@router.get(
    "",
    summary="Browse Schema Proposals",
    description=(
        "Proposals on this server, newest first, in pages. `limit` is at most 100 and "
        "`offset` counts from the newest; `status` narrows to `pending` or "
        "`withdrawn`. `total` counts every match, so a client can page without "
        "guessing.\n\n"
        "THERE ARE ONLY TWO STATUSES HERE. A decision by the standard's owners is "
        "made and recorded in the ISAAC portal, never in this list. Everyone who can "
        "reach this server sees every proposal, because nobody is identified."
    ),
    response_description="One page of proposals, newest first.",
    responses={**_R_UNAUTHORIZED},
)
def list_schema_proposals(
    limit: int = Query(25, ge=1, le=LIMITS["page_max"], description="Page size, at most 100."),
    offset: int = Query(0, ge=0, le=100_000, description="How many of the newest to skip."),
    status: str | None = Query(
        None,
        pattern="^(pending|withdrawn)$",
        description="Only proposals with this status: `pending` or `withdrawn`.",
    ),
) -> dict:
    everything = _all_proposals()
    pending_total = sum(1 for d in everything if d["status"] == STATUS_PENDING)
    items = everything
    if status is not None:
        items = [d for d in items if d["status"] == status]
    page = items[offset : offset + limit]
    end = offset + len(page)
    return _envelope(
        proposals=[_view(d) for d in page],
        total=len(items),
        limit=limit,
        offset=offset,
        next_offset=end if end < len(items) else None,
        statuses=list(PROPOSAL_STATUSES),
        capacity={
            "pending": pending_total,
            "max_pending": LIMITS["max_pending"],
            "max_withdrawn_kept": LIMITS["max_withdrawn_kept"],
            "scope": "Shared by everyone using this server (one workspace); a withdrawn proposal frees its place.",
        },
    )


@router.get(
    "/{proposal_id}",
    summary="Read One Schema Proposal",
    description=(
        "One proposal, with its status, its reviewer notes if any, and who proposed "
        "it. `proposed_by` is `null` and `attribution` is `unverified` unless a "
        "verified person made the request, which no deployment of this build "
        "provides.\n\n"
        "A proposal that is not on this server, including one cleared by a restart of "
        "a hosted server, is a `404`."
    ),
    response_description="The proposal.",
    responses={**_R_UNAUTHORIZED, **_R_NOT_FOUND},
)
def get_schema_proposal(
    proposal_id: str = PathParam(..., description="The proposal's id."),
):
    doc = _load(proposal_id)
    if doc is None:
        return _not_found()
    return _envelope(proposal=_view(doc))


@router.post(
    "/{proposal_id}/withdraw",
    summary="Withdraw a Schema Proposal",
    description=(
        "Marks a pending proposal as withdrawn. Only a proposal that is still "
        "`pending` can be withdrawn; anything else is `409 not_pending`. The proposal "
        "is kept, so the list still shows it.\n\n"
        "WITHDRAWING HERE DOES NOT RECALL A PROPOSAL ALREADY SENT TO THE PORTAL. "
        "ISAAC never sends one, so a person who sent it must withdraw or discuss it "
        "there. Nobody is identified on this server, so anyone who can reach it can "
        "withdraw any pending proposal."
    ),
    response_description="The proposal, now withdrawn.",
    responses={
        **_R_UNAUTHORIZED,
        **_R_NOT_FOUND,
        409: {"description": "The proposal is not pending, so it cannot be withdrawn."},
        **_R_STORE_UNAVAILABLE,
    },
)
def withdraw_schema_proposal(
    proposal_id: str = PathParam(..., description="The proposal's id."),
):
    try:
        with _STORE_LOCK:
            doc = _load(proposal_id)
            if doc is None:
                return _not_found()
            if doc["status"] != STATUS_PENDING:
                return _refuse(
                    409,
                    "not_pending",
                    f"Only a pending proposal can be withdrawn; this one is {doc['status']}.",
                    current_status=doc["status"],
                )
            doc["status"] = STATUS_WITHDRAWN
            doc["withdrawn_at"] = _now()
            _save(doc)
            _prune_withdrawn()
    except ProposalStoreUnavailable:
        return _unavailable()
    return _envelope(proposal=_view(doc))


@router.get(
    "/{proposal_id}/portal-payload",
    summary="Get the Portal Payload for a Proposal",
    description=(
        "The exact JSON body the ISAAC portal's proposal endpoint takes, for a person "
        "who has portal access to send. ISAAC never calls the portal and never holds "
        "portal credentials; this only prepares the text.\n\n"
        "The portal's REST endpoint accepts `add_term` proposals. An `add_category` "
        "proposal is entered in the portal's Ontology Editor with the same "
        "fields, and `portal.rest_supported` says which applies. The reviewer notes "
        "have no field upstream, so they are appended to `description` under a "
        "plain heading.\n\n"
        "A `schema_change` proposal never has a portal payload, because the portal has no proposal type "
        "for a new field: it is refused with `409 no_portal_payload`, and its export is the change-request "
        "operation."
    ),
    response_description="The portal request body and where it goes.",
    responses={
        **_R_UNAUTHORIZED,
        **_R_NOT_FOUND,
        409: {"description": "The proposal is a schema change request, which has no portal payload."},
    },
)
def get_schema_proposal_portal_payload(
    proposal_id: str = PathParam(..., description="The proposal's id."),
):
    doc = _load(proposal_id)
    if doc is None:
        return _not_found()
    if doc["proposal_type"] not in PORTAL_PROPOSAL_TYPES:
        return _refuse(
            409,
            "no_portal_payload",
            NOT_A_PORTAL_PROPOSAL + " Use the change-request document instead.",
            proposal_type=doc["proposal_type"],
        )
    return _envelope(proposal_id=doc["id"], status=doc["status"], **portal_payload(doc))


@router.get(
    "/{proposal_id}/change-request",
    summary="Get the Change-Request Document for a Schema Change",
    description=(
        "The export of a `schema_change` proposal: a document for the owners of the ISAAC "
        "standard, as Markdown (`markdown`, ready to paste into a discussion or a change file) and "
        "as JSON (`document`). IT IS NOT A PORTAL PAYLOAD: the ISAAC portal's Propose a Change has "
        "no proposal type for a new field. Its sections follow the upstream repository's own "
        "change process (`upstream`): the change, then gate 0 (the problem with counts and "
        "examples, and the flip list), then the migration plan, version and rollback a schema "
        "change needs. A section the proposer did not write says so.\n\n"
        "ISAAC never sends this anywhere and approves nothing; `sent_by_isaac` is `false`. A proposal "
        "that is a new term or list is refused with `409 not_a_schema_change` (use the portal payload)."
    ),
    response_description="The change-request document as Markdown and as JSON.",
    responses={
        **_R_UNAUTHORIZED,
        **_R_NOT_FOUND,
        409: {"description": "The proposal is a new term or list, which goes to the portal instead."},
    },
)
def get_schema_proposal_change_request(
    proposal_id: str = PathParam(..., description="The proposal's id."),
):
    doc = _load(proposal_id)
    if doc is None:
        return _not_found()
    if doc["proposal_type"] != SCHEMA_CHANGE:
        return _refuse(
            409,
            "not_a_schema_change",
            "This proposal is a new term or list, which the ISAAC portal takes: use its portal payload.",
            proposal_type=doc["proposal_type"],
        )
    exported = change_request(
        _view_for_export(doc),
        schema_version=doc.get("schema_version") or EXPECTED_VERSION,
        schema_sha256=load_vocabulary().get("schema_sha256"),
    )
    notes = [
        "ISAAC has not sent this anywhere. Someone who works with the owners of the ISAAC standard has to.",
        NOT_A_PORTAL_PROPOSAL,
        "The upstream repository records proposed changes in "
        f"{UPSTREAM_GOVERNANCE['drafts']}; its GitHub issues were turned off when this build read it "
        "(2026-10-29), so there is no issue form to file this in.",
        "The schema hash is of the copy this server holds now, which may be newer than the one this "
        "proposal was drafted against; the schema version is the one it was drafted against.",
    ]
    return _envelope(
        proposal_id=doc["id"],
        status=doc["status"],
        format=CHANGE_REQUEST_FORMAT,
        format_version=CHANGE_REQUEST_FORMAT_VERSION,
        is_portal_payload=False,
        markdown=exported["markdown"],
        document=exported["document"],
        filename_stem=f"isaac-schema-change-{doc['id']}",
        upstream=dict(UPSTREAM_GOVERNANCE),
        sent_by_isaac=False,
        notes=notes,
    )


def _view_for_export(doc: dict) -> dict:
    """The stored proposal as the export reads it: the public view, never the raw file."""
    return _view(doc)
